using System.Net.Http.Json;
using Chummer.Run.Contracts.Identity;

namespace Chummer.Run.Api.Services;

public static class HubBrowserAuthConstants
{
    public const string AccessTokenCookieName = "chummer_hub_access_token";
}

public sealed class HubBrowserAuthService
{
    private readonly HttpClient _httpClient;
    private readonly IConfiguration _configuration;

    public HubBrowserAuthService(HttpClient httpClient, IConfiguration configuration)
    {
        _httpClient = httpClient;
        _configuration = configuration;
    }

    private string BaseUrl =>
        (_configuration["IDENTITY_SERVICE_BASE_URL"] ?? "http://chummer-run-identity:8080").TrimEnd('/');

    public async Task<EmailAuthStartResponse> StartEmailEntryAsync(string email, string? displayName, string? nextPath, CancellationToken cancellationToken)
    {
        using var response = await _httpClient.PostAsJsonAsync(
            $"{BaseUrl}/api/v1/identity/email/start",
            new EmailAuthStartRequest(email, displayName, nextPath),
            cancellationToken);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<EmailAuthStartResponse>(cancellationToken: cancellationToken)
            ?? throw new InvalidOperationException("Identity email-start response was empty.");
    }

    public async Task<IdentitySessionIssueResponse> CompleteEmailEntryAsync(string ticketId, CancellationToken cancellationToken)
    {
        using var response = await _httpClient.PostAsJsonAsync(
            $"{BaseUrl}/api/v1/identity/email/complete",
            new EmailAuthCompleteRequest(ticketId),
            cancellationToken);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<IdentitySessionIssueResponse>(cancellationToken: cancellationToken)
            ?? throw new InvalidOperationException("Identity email-complete response was empty.");
    }

    public async Task RevokeCookieSessionAsync(HttpRequest request, CancellationToken cancellationToken)
    {
        if (!request.Cookies.TryGetValue(HubBrowserAuthConstants.AccessTokenCookieName, out var accessToken)
            || string.IsNullOrWhiteSpace(accessToken))
        {
            return;
        }

        using var response = await _httpClient.PostAsJsonAsync(
            $"{BaseUrl}/api/v1/identity/sessions/revoke",
            new IdentitySessionRevokeRequest(accessToken),
            cancellationToken);
        response.EnsureSuccessStatusCode();
    }

    public void WriteCookie(HttpResponse response, IdentitySessionIssueResponse session)
    {
        response.Cookies.Append(
            HubBrowserAuthConstants.AccessTokenCookieName,
            session.AccessToken,
            new CookieOptions
            {
                HttpOnly = true,
                Secure = false,
                SameSite = SameSiteMode.Lax,
                Expires = session.ExpiresAtUtc.UtcDateTime,
                IsEssential = true,
                Path = "/"
            });
    }

    public void ClearCookie(HttpResponse response)
    {
        response.Cookies.Delete(
            HubBrowserAuthConstants.AccessTokenCookieName,
            new CookieOptions
            {
                Path = "/",
                SameSite = SameSiteMode.Lax,
                HttpOnly = true,
                Secure = false,
                IsEssential = true
            });
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
}
