using System.Net;
using System.Net.Http.Json;
using Chummer.Run.Contracts.Identity;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Logging.Abstractions;
using System.Collections.Concurrent;

namespace Chummer.Run.Api.Services;

public sealed record AuthenticatedHubSubject(
    string SubjectId,
    string? DisplayName,
    string? Email,
    IReadOnlyList<string> Roles,
    string AccessToken);

public sealed class HubRequestAuthException : Exception
{
    public HubRequestAuthException(int statusCode, string message)
        : base(message)
    {
        StatusCode = statusCode;
    }

    public int StatusCode { get; }
}

public sealed class HubIdentitySubjectCache
{
    private sealed record CachedAuthenticatedHubSubject(
        AuthenticatedHubSubject Subject,
        DateTimeOffset ExpiresAtUtc);

    private readonly ConcurrentDictionary<string, CachedAuthenticatedHubSubject> _entries = new(StringComparer.Ordinal);

    public bool TryGet(string cacheScope, string accessToken, out AuthenticatedHubSubject? subject)
    {
        string cacheKey = BuildCacheKey(cacheScope, accessToken);
        DateTimeOffset now = DateTimeOffset.UtcNow;
        if (_entries.TryGetValue(cacheKey, out CachedAuthenticatedHubSubject? cached)
            && cached.ExpiresAtUtc >= now)
        {
            subject = cached.Subject;
            return true;
        }

        if (cached is not null)
        {
            _entries.TryRemove(cacheKey, out _);
        }

        subject = null;
        return false;
    }

    public void Set(string cacheScope, string accessToken, AuthenticatedHubSubject subject, TimeSpan ttl)
    {
        if (ttl <= TimeSpan.Zero)
        {
            return;
        }

        _entries[BuildCacheKey(cacheScope, accessToken)] = new CachedAuthenticatedHubSubject(subject, DateTimeOffset.UtcNow.Add(ttl));
    }

    private static string BuildCacheKey(string cacheScope, string accessToken)
        => string.Concat(cacheScope, "|", accessToken);
}

public sealed class HubIdentityClient
{
    private readonly HttpClient _httpClient;
    private readonly IConfiguration _configuration;
    private readonly ILogger<HubIdentityClient> _logger;
    private readonly HubIdentitySubjectCache _subjectCache;
    private const string IdentityUnavailableMessage = "Identity is unavailable right now. Try again later.";

    public HubIdentityClient(
        HttpClient httpClient,
        IConfiguration configuration,
        ILogger<HubIdentityClient>? logger = null,
        HubIdentitySubjectCache? subjectCache = null)
    {
        _httpClient = httpClient;
        _configuration = configuration;
        _logger = logger ?? NullLogger<HubIdentityClient>.Instance;
        _subjectCache = subjectCache ?? new HubIdentitySubjectCache();
    }

    private string BaseUrl =>
        (_configuration["IDENTITY_SERVICE_BASE_URL"] ?? "http://chummer-run-identity:8080").TrimEnd('/');

    private TimeSpan SubjectCacheTtl
    {
        get
        {
            if (int.TryParse(_configuration["CHUMMER_IDENTITY_SUBJECT_CACHE_SECONDS"], out int seconds))
            {
                seconds = Math.Clamp(seconds, 0, 300);
                return TimeSpan.FromSeconds(seconds);
            }

            return TimeSpan.FromSeconds(30);
        }
    }

    public async Task<AuthenticatedHubSubject> RequireSubjectAsync(HttpRequest request, CancellationToken cancellationToken)
    {
        var accessToken = ExtractBearerToken(request);
        if (_subjectCache.TryGet(BaseUrl, accessToken, out AuthenticatedHubSubject? cachedSubject))
        {
            return cachedSubject!;
        }

        var introspection = await IntrospectAsync(accessToken, cancellationToken);
        if (!introspection.Active || string.IsNullOrWhiteSpace(introspection.SubjectId))
        {
            throw new HubRequestAuthException(StatusCodes.Status401Unauthorized, "active identity session required.");
        }

        var profile = await TryGetSubjectAsync(introspection.SubjectId!, cancellationToken);
        AuthenticatedHubSubject subject = new(
            introspection.SubjectId!,
            profile?.DisplayName,
            profile?.Email,
            introspection.Roles ?? Array.Empty<string>(),
            accessToken);
        _subjectCache.Set(BaseUrl, accessToken, subject, SubjectCacheTtl);
        return subject;
    }

    public async Task<AuthenticatedHubSubject> RequireMatchingSubjectAsync(
        HttpRequest request,
        string? claimedSubjectId,
        CancellationToken cancellationToken)
    {
        var subject = await RequireSubjectAsync(request, cancellationToken);
        var claimed = string.IsNullOrWhiteSpace(claimedSubjectId) ? null : claimedSubjectId.Trim();
        if (claimed is not null && !string.Equals(claimed, subject.SubjectId, StringComparison.OrdinalIgnoreCase))
        {
            throw new HubRequestAuthException(StatusCodes.Status403Forbidden, "subject mismatch for authenticated session.");
        }

        return subject;
    }

    private async Task<IdentityIntrospectionResponse> IntrospectAsync(string accessToken, CancellationToken cancellationToken)
    {
        HttpResponseMessage response;
        try
        {
            response = await _httpClient.PostAsJsonAsync(
                $"{BaseUrl}/api/v1/identity/introspect",
                new IdentityIntrospectionRequest(accessToken),
                cancellationToken);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogWarning(ex, "Identity introspection request failed.");
            throw new HubRequestAuthException(StatusCodes.Status503ServiceUnavailable, IdentityUnavailableMessage);
        }
        catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogWarning(ex, "Identity introspection request timed out.");
            throw new HubRequestAuthException(StatusCodes.Status503ServiceUnavailable, IdentityUnavailableMessage);
        }

        using (response)
        {
            if (!response.IsSuccessStatusCode)
            {
                if (response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden or HttpStatusCode.BadRequest)
                {
                    throw new HubRequestAuthException(StatusCodes.Status401Unauthorized, "active identity session required.");
                }

                if (response.StatusCode is HttpStatusCode.TooManyRequests
                    or HttpStatusCode.BadGateway
                    or HttpStatusCode.ServiceUnavailable
                    or HttpStatusCode.GatewayTimeout
                    || (int)response.StatusCode >= 500)
                {
                    var detail = await SafeReadBodyAsync(response, cancellationToken);
                    _logger.LogWarning(
                        "Identity introspection returned status {StatusCode}. Detail: {Detail}",
                        (int)response.StatusCode,
                        string.IsNullOrWhiteSpace(detail) ? "<empty>" : detail);
                    throw new HubRequestAuthException(StatusCodes.Status503ServiceUnavailable, IdentityUnavailableMessage);
                }

                throw new HubRequestAuthException(StatusCodes.Status401Unauthorized, "identity introspection failed.");
            }

            try
            {
                var payload = await response.Content.ReadFromJsonAsync<IdentityIntrospectionResponse>(cancellationToken: cancellationToken);
                return payload ?? new IdentityIntrospectionResponse(false, null, null, null, null);
            }
            catch (Exception ex) when (ex is System.Text.Json.JsonException or NotSupportedException)
            {
                _logger.LogWarning(ex, "Identity introspection returned an unreadable payload.");
                throw new HubRequestAuthException(StatusCodes.Status503ServiceUnavailable, IdentityUnavailableMessage);
            }
        }
    }

    private async Task<IdentitySubjectResponse?> TryGetSubjectAsync(string subjectId, CancellationToken cancellationToken)
    {
        HttpResponseMessage response;
        try
        {
            response = await _httpClient.GetAsync(
                $"{BaseUrl}/api/v1/identity/subjects/{Uri.EscapeDataString(subjectId)}",
                cancellationToken);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogWarning(ex, "Identity subject lookup failed for {SubjectId}.", subjectId);
            return null;
        }
        catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogWarning(ex, "Identity subject lookup timed out for {SubjectId}.", subjectId);
            return null;
        }

        using (response)
        {
            if (response.StatusCode == HttpStatusCode.NotFound || !response.IsSuccessStatusCode)
            {
                if ((int)response.StatusCode >= 500)
                {
                    var detail = await SafeReadBodyAsync(response, cancellationToken);
                    _logger.LogWarning(
                        "Identity subject lookup for {SubjectId} returned status {StatusCode}. Detail: {Detail}",
                        subjectId,
                        (int)response.StatusCode,
                        string.IsNullOrWhiteSpace(detail) ? "<empty>" : detail);
                }

                return null;
            }

            try
            {
                return await response.Content.ReadFromJsonAsync<IdentitySubjectResponse>(cancellationToken: cancellationToken);
            }
            catch (Exception ex) when (ex is System.Text.Json.JsonException or NotSupportedException)
            {
                _logger.LogWarning(ex, "Identity subject lookup for {SubjectId} returned an unreadable payload.", subjectId);
                return null;
            }
        }
    }

    private static string ExtractBearerToken(HttpRequest request)
    {
        if (request is null)
        {
            throw new HubRequestAuthException(StatusCodes.Status401Unauthorized, "bearer access token required.");
        }

        var header = request.Headers.Authorization.ToString();
        if (!string.IsNullOrWhiteSpace(header)
            && header.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase))
        {
            var token = header["Bearer ".Length..].Trim();
            if (!string.IsNullOrWhiteSpace(token))
            {
                return token;
            }
        }

        if (request.Cookies.TryGetValue(HubBrowserAuthConstants.AccessTokenCookieName, out var cookieToken)
            && !string.IsNullOrWhiteSpace(cookieToken))
        {
            return cookieToken.Trim();
        }

        throw new HubRequestAuthException(StatusCodes.Status401Unauthorized, "bearer access token required.");
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
