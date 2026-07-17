using System.Net;
using System.Net.Http.Json;
using Chummer.Run.Contracts.Identity;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Services;

public static class HubBrowserAuthConstants
{
    public const string AccessTokenCookieName = "chummer_hub_access_token";
    public const string SubjectHintCookieName = "chummer_hub_subject_hint";
}

public class HubBrowserAuthUnavailableException : InvalidOperationException
{
    public HubBrowserAuthUnavailableException(string message, Exception? innerException = null)
        : base(message, innerException)
    {
    }
}

public sealed class HubBrowserAuthRequestFailedException : HubBrowserAuthUnavailableException
{
    public HubBrowserAuthRequestFailedException(string message, string operation, int statusCode, string? detail, Exception? innerException = null)
        : base(message, innerException)
    {
        Operation = operation;
        StatusCode = statusCode;
        Detail = detail;
    }

    public string Operation { get; }

    public int StatusCode { get; }

    public string? Detail { get; }
}

public sealed class HubBrowserAuthService
{
    private const int TransientRetryAttempts = 2;
    private const int MaxNextPathLength = 4096;
    private const int MaxInstallLinkValueLength = 256;
    private const int MaxCallbackStateValueLength = 128;
    private const string InstallLinkPath = "/account/access/install-link";
    private const string AppLocalInstallLinkCallbackPath = "/install-link/callback";
    private static readonly HashSet<string> CallbackStateKeys =
        new(StringComparer.OrdinalIgnoreCase) { "state", "nonce" };
    private readonly HttpClient _httpClient;
    private readonly IConfiguration _configuration;
    private readonly ILogger<HubBrowserAuthService> _logger;
    private readonly HubIdentityHintCookieService? _identityHintCookie;
    private readonly PublicCanonicalOriginPolicy? _publicOrigin;

    public HubBrowserAuthService(
        HttpClient httpClient,
        IConfiguration configuration,
        ILogger<HubBrowserAuthService>? logger = null,
        HubIdentityHintCookieService? identityHintCookie = null,
        PublicCanonicalOriginPolicy? publicOrigin = null)
    {
        _httpClient = httpClient;
        _configuration = configuration;
        _logger = logger ?? NullLogger<HubBrowserAuthService>.Instance;
        _identityHintCookie = identityHintCookie;
        _publicOrigin = publicOrigin;
    }

    private string BaseUrl =>
        (_configuration["IDENTITY_SERVICE_BASE_URL"] ?? "http://chummer-run-identity:8080").TrimEnd('/');

    private string? AdminKey =>
        string.IsNullOrWhiteSpace(_configuration["IDENTITY_ADMIN_KEY"])
            ? null
            : _configuration["IDENTITY_ADMIN_KEY"]!.Trim();

    public async Task<EmailAuthStartResponse> StartEmailEntryAsync(string email, string? displayName, string? nextPath, CancellationToken cancellationToken)
        => await SendAndReadAsync<EmailAuthStartResponse>(
            () => _httpClient.PostAsJsonAsync(
                $"{BaseUrl}/api/v1/identity/email/start",
                new EmailAuthStartRequest(email, displayName, nextPath),
                cancellationToken),
            operation: "email-start",
            publicMessage: "Email sign-in is unavailable right now. Try again later.",
            cancellationToken);

    public async Task<IdentitySessionIssueResponse> CompleteEmailEntryAsync(string ticketId, CancellationToken cancellationToken)
        => await SendAndReadAsync<IdentitySessionIssueResponse>(
            () => _httpClient.PostAsJsonAsync(
                $"{BaseUrl}/api/v1/identity/email/complete",
                new EmailAuthCompleteRequest(ticketId),
                cancellationToken),
            operation: "email-complete",
            publicMessage: "Email sign-in could not be completed right now. Start from the latest Chummer email and try again.",
            cancellationToken);

    public async Task<IdentitySessionIssueResponse> IssueSessionAsync(
        string subjectId,
        string? displayName,
        string? email,
        IReadOnlyList<string>? requestedRoles,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(AdminKey))
        {
            _logger.LogWarning("Hub cannot issue browser sessions because IDENTITY_ADMIN_KEY is missing.");
            throw new HubBrowserAuthUnavailableException("Sign-in could not be completed right now. Try again later.");
        }

        return await SendAndReadAsync<IdentitySessionIssueResponse>(async () =>
            {
                using var request = new HttpRequestMessage(HttpMethod.Post, $"{BaseUrl}/api/v1/identity/sessions")
                {
                    Content = JsonContent.Create(new IdentitySessionIssueRequest(
                        SubjectId: subjectId,
                        DisplayName: displayName,
                        Email: email,
                        RequestedRoles: requestedRoles))
                };
                request.Headers.Add("X-Identity-Admin-Key", AdminKey);
                return await _httpClient.SendAsync(request, cancellationToken);
            },
            operation: "issue-session",
            publicMessage: "Sign-in could not be completed right now. Try again later.",
            cancellationToken);
    }

    public async Task RevokeCookieSessionAsync(HttpRequest request, CancellationToken cancellationToken)
    {
        if (!request.Cookies.TryGetValue(HubBrowserAuthConstants.AccessTokenCookieName, out var accessToken)
            || string.IsNullOrWhiteSpace(accessToken))
        {
            return;
        }

        await SendWithoutResultAsync(
            () => _httpClient.PostAsJsonAsync(
                $"{BaseUrl}/api/v1/identity/sessions/revoke",
                new IdentitySessionRevokeRequest(accessToken),
                cancellationToken),
            operation: "revoke-session",
            publicMessage: "Sign-out could not be completed right now. Try again later.",
            cancellationToken);
    }

    public void WriteCookie(HttpRequest request, HttpResponse response, IdentitySessionIssueResponse session)
    {
        var secure = ShouldUseSecureCookies(request, _publicOrigin);
        response.Cookies.Append(
            HubBrowserAuthConstants.AccessTokenCookieName,
            session.AccessToken,
            new CookieOptions
            {
                HttpOnly = true,
                Secure = secure,
                SameSite = SameSiteMode.Lax,
                Expires = session.ExpiresAtUtc.UtcDateTime,
                IsEssential = true,
                Path = "/"
            });
        _identityHintCookie?.WriteCookie(request, response, session);
    }

    public void ClearCookie(HttpRequest request, HttpResponse response)
    {
        var secure = ShouldUseSecureCookies(request, _publicOrigin);
        response.Cookies.Delete(
            HubBrowserAuthConstants.AccessTokenCookieName,
            new CookieOptions
            {
                Path = "/",
                SameSite = SameSiteMode.Lax,
                HttpOnly = true,
                Secure = secure,
                IsEssential = true
            });
        _identityHintCookie?.ClearCookie(request, response);
    }

    public static string SanitizeNextPath(string? nextPath, string fallback = "/home")
    {
        string safeFallback = IsSafeLocalPath(fallback) ? fallback : "/home";
        if (!IsSafeLocalPath(nextPath))
        {
            return safeFallback;
        }

        string candidate = nextPath!;
        int queryIndex = candidate.IndexOf('?');
        string path = queryIndex < 0 ? candidate : candidate[..queryIndex];
        string? decodedPath = DecodeLocalPathForInspection(path);
        if (!string.Equals(decodedPath, InstallLinkPath, StringComparison.OrdinalIgnoreCase))
        {
            return candidate;
        }

        IReadOnlyDictionary<string, Microsoft.Extensions.Primitives.StringValues> query =
            QueryHelpers.ParseQuery(queryIndex < 0 ? string.Empty : candidate[queryIndex..]);
        string? callbackUri = SingleQueryValue(query, "installLinkCallbackUri");
        string? sanitizedCallback = SanitizeInstallLinkCallbackUri(callbackUri);
        if (sanitizedCallback is null)
        {
            return safeFallback;
        }

        return BuildInstallLinkingNextPath(
            SingleQueryValue(query, "installationId"),
            SingleQueryValue(query, "headId"),
            SingleQueryValue(query, "applicationVersion"),
            SingleQueryValue(query, "releaseChannel"),
            SingleQueryValue(query, "platform"),
            SingleQueryValue(query, "arch"),
            sanitizedCallback);
    }

    public static string BuildInstallLinkingNextPath(
        string? installationId,
        string? headId,
        string? applicationVersion,
        string? releaseChannel,
        string? platform,
        string? arch,
        string installLinkCallbackUri)
    {
        string? callback = SanitizeInstallLinkCallbackUri(installLinkCallbackUri)
            ?? throw new ArgumentException("Install-link callback URI is invalid.", nameof(installLinkCallbackUri));
        var values = new Dictionary<string, string?>(StringComparer.Ordinal)
        {
            ["installationId"] = SanitizeInstallLinkValue(installationId),
            ["headId"] = SanitizeInstallLinkValue(headId),
            ["applicationVersion"] = SanitizeInstallLinkValue(applicationVersion),
            ["releaseChannel"] = SanitizeInstallLinkValue(releaseChannel),
            ["platform"] = SanitizeInstallLinkValue(platform),
            ["arch"] = SanitizeInstallLinkValue(arch),
            ["installLinkCallbackUri"] = callback
        };
        return QueryHelpers.AddQueryString(
            InstallLinkPath,
            values.Where(static item => item.Value is not null)
                .ToDictionary(static item => item.Key, static item => item.Value, StringComparer.Ordinal));
    }

    public static string? SanitizeInstallLinkCallbackUri(string? callbackUri)
    {
        if (string.IsNullOrWhiteSpace(callbackUri)
            || callbackUri.Length > MaxNextPathLength
            || HasControlOrBackslash(callbackUri)
            || !Uri.TryCreate(callbackUri, UriKind.Absolute, out Uri? parsed)
            || !string.IsNullOrEmpty(parsed.UserInfo))
        {
            return null;
        }

        bool customScheme = string.Equals(parsed.Scheme, "chummer", StringComparison.OrdinalIgnoreCase)
            && string.Equals(parsed.Host, "install-link", StringComparison.OrdinalIgnoreCase)
            && (string.IsNullOrEmpty(parsed.AbsolutePath) || string.Equals(parsed.AbsolutePath, "/", StringComparison.Ordinal));
        bool loopbackHttp = (string.Equals(parsed.Scheme, Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase)
                || string.Equals(parsed.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
            && IsLoopbackHost(parsed.Host)
            && IsInstallLinkCallbackPath(parsed.AbsolutePath);
        if (!customScheme && !loopbackHttp)
        {
            return null;
        }

        string baseUri;
        if (customScheme)
        {
            baseUri = "chummer://install-link";
        }
        else
        {
            var builder = new UriBuilder(parsed) { Query = string.Empty, Fragment = string.Empty };
            baseUri = builder.Uri.GetLeftPart(UriPartial.Path);
        }

        var preserved = new Dictionary<string, string?>(StringComparer.OrdinalIgnoreCase);
        IReadOnlyDictionary<string, Microsoft.Extensions.Primitives.StringValues> query =
            QueryHelpers.ParseQuery(parsed.Query);
        foreach (string key in CallbackStateKeys)
        {
            string? value = SingleQueryValue(query, key);
            if (IsSafeCallbackStateValue(value))
            {
                preserved[key] = value;
            }
        }

        // Fragments never reach the server and are intentionally discarded. Keeping arbitrary
        // fragment/query material here would turn the login continuation into a credential relay.
        return preserved.Count == 0 ? baseUri : QueryHelpers.AddQueryString(baseUri, preserved);
    }

    private static bool IsSafeLocalPath(string? path)
    {
        if (string.IsNullOrEmpty(path)
            || path.Length > MaxNextPathLength
            || !string.Equals(path, path.Trim(), StringComparison.Ordinal)
            || HasControlOrBackslash(path))
        {
            return false;
        }

        return DecodeLocalPathForInspection(path) is not null;
    }

    private static string? DecodeLocalPathForInspection(string path)
    {
        string decoded = path;
        for (int pass = 0; pass < 16; pass++)
        {
            if (!decoded.StartsWith("/", StringComparison.Ordinal)
                || decoded.StartsWith("//", StringComparison.Ordinal)
                || decoded.StartsWith("/\\", StringComparison.Ordinal)
                || HasControlOrBackslash(decoded))
            {
                return null;
            }

            string next;
            try
            {
                next = Uri.UnescapeDataString(decoded);
            }
            catch (UriFormatException)
            {
                return null;
            }

            if (string.Equals(next, decoded, StringComparison.Ordinal))
            {
                return decoded;
            }

            decoded = next;
        }

        // Excessively nested escaping is not a legitimate navigation requirement and can be
        // decoded again by downstream proxies. Reject instead of guessing their decode depth.
        return null;
    }

    private static string? SingleQueryValue(
        IReadOnlyDictionary<string, Microsoft.Extensions.Primitives.StringValues> query,
        string key)
    {
        if (!query.TryGetValue(key, out Microsoft.Extensions.Primitives.StringValues values)
            || values.Count != 1)
        {
            return null;
        }

        return values[0];
    }

    private static string? SanitizeInstallLinkValue(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string trimmed = value.Trim();
        return trimmed.Length <= MaxInstallLinkValueLength && !HasControlOrBackslash(trimmed)
            ? trimmed
            : null;
    }

    private static bool IsSafeCallbackStateValue(string? value)
        => !string.IsNullOrEmpty(value)
            && value.Length <= MaxCallbackStateValueLength
            && value.All(static character =>
                character is >= 'a' and <= 'z'
                or >= 'A' and <= 'Z'
                or >= '0' and <= '9'
                or '-' or '_' or '.' or '~');

    private static bool HasControlOrBackslash(string value)
        => value.Any(static character => char.IsControl(character) || character == '\\');

    private static bool IsLoopbackHost(string host)
        => string.Equals(host, "localhost", StringComparison.OrdinalIgnoreCase)
            || (IPAddress.TryParse(host, out IPAddress? address) && IPAddress.IsLoopback(address));

    private static bool IsInstallLinkCallbackPath(string path)
    {
        string normalized = path;
        while (normalized.Length > AppLocalInstallLinkCallbackPath.Length
               && normalized.EndsWith("/", StringComparison.Ordinal))
        {
            normalized = normalized[..^1];
        }

        return string.Equals(normalized, AppLocalInstallLinkCallbackPath, StringComparison.Ordinal);
    }

    public static bool ShouldExposeInlinePreviewLink(HttpRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        if (request.Host.Host is { Length: > 0 } host
            && (string.Equals(host, "localhost", StringComparison.OrdinalIgnoreCase)
                || string.Equals(host, "127.0.0.1", StringComparison.OrdinalIgnoreCase)
                || string.Equals(host, "::1", StringComparison.OrdinalIgnoreCase)))
        {
            return true;
        }

        IPAddress? remote = request.HttpContext.Connection.RemoteIpAddress;
        IPAddress? local = request.HttpContext.Connection.LocalIpAddress;
        if (remote is null)
        {
            return false;
        }

        return IPAddress.IsLoopback(remote);
    }

    internal static bool ShouldUseSecureCookies(HttpRequest request)
    {
        if (request.IsHttps)
        {
            return true;
        }

        if (request.Headers.TryGetValue("X-Forwarded-Proto", out var forwardedProtoValues))
        {
            foreach (var forwardedProto in forwardedProtoValues)
            {
                if (string.Equals(forwardedProto, "https", StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
        }

        var host = request.Host.Host;
        if (string.Equals(host, "localhost", StringComparison.OrdinalIgnoreCase)
            || string.Equals(host, "127.0.0.1", StringComparison.OrdinalIgnoreCase)
            || string.Equals(host, "::1", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        return true;
    }

    internal static bool ShouldUseSecureCookies(
        HttpRequest request,
        PublicCanonicalOriginPolicy? publicOrigin)
        => publicOrigin?.UsesHttps ?? ShouldUseSecureCookies(request);

    private async Task<T> SendAndReadAsync<T>(
        Func<Task<HttpResponseMessage>> sendAsync,
        string operation,
        string publicMessage,
        CancellationToken cancellationToken)
    {
        using var response = await SendAsync(sendAsync, operation, publicMessage, cancellationToken);
        try
        {
            var payload = await response.Content.ReadFromJsonAsync<T>(cancellationToken: cancellationToken);
            if (payload is null)
            {
                _logger.LogWarning("Identity browser auth operation {Operation} returned an empty payload.", operation);
                throw new HubBrowserAuthUnavailableException(publicMessage);
            }

            return payload;
        }
        catch (Exception ex) when (ex is System.Text.Json.JsonException or NotSupportedException)
        {
            _logger.LogWarning(ex, "Identity browser auth operation {Operation} returned an unreadable payload.", operation);
            throw new HubBrowserAuthUnavailableException(publicMessage, ex);
        }
    }

    private async Task SendWithoutResultAsync(
        Func<Task<HttpResponseMessage>> sendAsync,
        string operation,
        string publicMessage,
        CancellationToken cancellationToken)
    {
        using var response = await SendAsync(sendAsync, operation, publicMessage, cancellationToken);
        _ = response;
    }

    private async Task<HttpResponseMessage> SendAsync(
        Func<Task<HttpResponseMessage>> sendAsync,
        string operation,
        string publicMessage,
        CancellationToken cancellationToken)
    {
        for (int attempt = 1; ; attempt++)
        {
            try
            {
                var response = await sendAsync();
                if (response.IsSuccessStatusCode)
                {
                    return response;
                }

                var detail = await SafeReadBodyAsync(response, cancellationToken);
                if (attempt < TransientRetryAttempts && IsTransientStatusCode(response.StatusCode))
                {
                    _logger.LogWarning(
                        "Identity browser auth operation {Operation} returned transient status {StatusCode} on attempt {Attempt}. Retrying. Detail: {Detail}",
                        operation,
                        (int)response.StatusCode,
                        attempt,
                        string.IsNullOrWhiteSpace(detail) ? "<empty>" : detail);
                    response.Dispose();
                    await DelayBeforeRetryAsync(attempt, cancellationToken);
                    continue;
                }

                _logger.LogWarning(
                    "Identity browser auth operation {Operation} failed with status {StatusCode}. Detail: {Detail}",
                    operation,
                    (int)response.StatusCode,
                    string.IsNullOrWhiteSpace(detail) ? "<empty>" : detail);
                response.Dispose();
                throw new HubBrowserAuthRequestFailedException(
                    publicMessage,
                    operation,
                    (int)response.StatusCode,
                    detail);
            }
            catch (HttpRequestException ex) when (attempt < TransientRetryAttempts)
            {
                _logger.LogWarning(ex, "Identity browser auth operation {Operation} failed on attempt {Attempt}. Retrying.", operation, attempt);
                await DelayBeforeRetryAsync(attempt, cancellationToken);
            }
            catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested && attempt < TransientRetryAttempts)
            {
                _logger.LogWarning(ex, "Identity browser auth operation {Operation} timed out on attempt {Attempt}. Retrying.", operation, attempt);
                await DelayBeforeRetryAsync(attempt, cancellationToken);
            }
            catch (HttpRequestException ex)
            {
                _logger.LogWarning(ex, "Identity browser auth operation {Operation} failed.", operation);
                throw new HubBrowserAuthUnavailableException(publicMessage, ex);
            }
            catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
            {
                _logger.LogWarning(ex, "Identity browser auth operation {Operation} timed out.", operation);
                throw new HubBrowserAuthUnavailableException(publicMessage, ex);
            }
        }
    }

    private static bool IsTransientStatusCode(HttpStatusCode statusCode)
        => statusCode == HttpStatusCode.RequestTimeout
           || statusCode == HttpStatusCode.TooManyRequests
           || statusCode == HttpStatusCode.BadGateway
           || statusCode == HttpStatusCode.ServiceUnavailable
           || statusCode == HttpStatusCode.GatewayTimeout
           || (int)statusCode >= 500;

    private static Task DelayBeforeRetryAsync(int attempt, CancellationToken cancellationToken)
        => Task.Delay(TimeSpan.FromMilliseconds(200 * Math.Max(1, attempt)), cancellationToken);

    private static async Task<string> SafeReadBodyAsync(HttpResponseMessage response, CancellationToken cancellationToken)
    {
        try
        {
            return await response.Content.ReadAsStringAsync(cancellationToken);
        }
        catch
        {
            return string.Empty;
        }
    }
}
