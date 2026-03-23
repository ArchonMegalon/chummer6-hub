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

    private string? AdminKey =>
        string.IsNullOrWhiteSpace(_configuration["IDENTITY_ADMIN_KEY"])
            ? null
            : _configuration["IDENTITY_ADMIN_KEY"]!.Trim();

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

    public async Task<IdentitySessionIssueResponse> IssueSessionAsync(
        string subjectId,
        string? displayName,
        string? email,
        IReadOnlyList<string>? requestedRoles,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(AdminKey))
        {
            throw new InvalidOperationException("IDENTITY_ADMIN_KEY must be configured before Hub can issue browser sessions for external auth.");
        }

        using var request = new HttpRequestMessage(HttpMethod.Post, $"{BaseUrl}/api/v1/identity/sessions")
        {
            Content = JsonContent.Create(new IdentitySessionIssueRequest(
                SubjectId: subjectId,
                DisplayName: displayName,
                Email: email,
                RequestedRoles: requestedRoles))
        };
        request.Headers.Add("X-Identity-Admin-Key", AdminKey);

        using var response = await _httpClient.SendAsync(request, cancellationToken);
        response.EnsureSuccessStatusCode();
        return await response.Content.ReadFromJsonAsync<IdentitySessionIssueResponse>(cancellationToken: cancellationToken)
            ?? throw new InvalidOperationException("Identity session issuance response was empty.");
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

    public void WriteCookie(HttpRequest request, HttpResponse response, IdentitySessionIssueResponse session)
    {
        var secure = request.IsHttps
            || !string.Equals(_configuration["ASPNETCORE_ENVIRONMENT"], "Development", StringComparison.OrdinalIgnoreCase);
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
    }

    public void ClearCookie(HttpRequest request, HttpResponse response)
    {
        var secure = request.IsHttps
            || !string.Equals(_configuration["ASPNETCORE_ENVIRONMENT"], "Development", StringComparison.OrdinalIgnoreCase);
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
