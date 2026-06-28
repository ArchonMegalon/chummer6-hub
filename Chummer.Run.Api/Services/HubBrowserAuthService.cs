using System.Net;
using System.Net.Http.Json;
using Chummer.Run.Contracts.Identity;
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
    private readonly HttpClient _httpClient;
    private readonly IConfiguration _configuration;
    private readonly ILogger<HubBrowserAuthService> _logger;
    private readonly HubIdentityHintCookieService? _identityHintCookie;

    public HubBrowserAuthService(
        HttpClient httpClient,
        IConfiguration configuration,
        ILogger<HubBrowserAuthService>? logger = null,
        HubIdentityHintCookieService? identityHintCookie = null)
    {
        _httpClient = httpClient;
        _configuration = configuration;
        _logger = logger ?? NullLogger<HubBrowserAuthService>.Instance;
        _identityHintCookie = identityHintCookie;
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
        var secure = ShouldUseSecureCookies(request);
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
        var secure = ShouldUseSecureCookies(request);
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
        if (string.IsNullOrWhiteSpace(nextPath))
        {
            return fallback;
        }

        var trimmed = nextPath.Trim();
        return trimmed.StartsWith("/", StringComparison.Ordinal) && !trimmed.StartsWith("//", StringComparison.Ordinal)
            ? trimmed
            : fallback;
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
        try
        {
            var response = await sendAsync();
            if (response.IsSuccessStatusCode)
            {
                return response;
            }

            var detail = await SafeReadBodyAsync(response, cancellationToken);
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
