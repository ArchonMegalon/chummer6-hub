using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Contracts.Identity;
using Microsoft.AspNetCore.DataProtection;

namespace Chummer.Run.Api.Services;

public sealed class HubIdentityHintCookieService
{
    private readonly IDataProtector _protector;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web);

    public HubIdentityHintCookieService(IDataProtectionProvider dataProtectionProvider)
    {
        _protector = dataProtectionProvider.CreateProtector("Chummer.Run.Api.HubIdentityHintCookie.v1");
    }

    public void WriteCookie(HttpRequest request, HttpResponse response, IdentitySessionIssueResponse session)
    {
        if (request is null)
        {
            throw new ArgumentNullException(nameof(request));
        }

        if (response is null)
        {
            throw new ArgumentNullException(nameof(response));
        }

        HubSignedInHintCookiePayload payload = new(
            session.SubjectId,
            string.IsNullOrWhiteSpace(session.DisplayName) ? "Signed in" : session.DisplayName.Trim(),
            string.IsNullOrWhiteSpace(session.Email) ? null : session.Email.Trim(),
            session.Roles ?? Array.Empty<string>(),
            ComputeTokenHash(session.AccessToken),
            session.ExpiresAtUtc);
        string protectedPayload = _protector.Protect(JsonSerializer.Serialize(payload, _jsonOptions));
        response.Cookies.Append(
            HubBrowserAuthConstants.SubjectHintCookieName,
            protectedPayload,
            new CookieOptions
            {
                HttpOnly = true,
                Secure = HubBrowserAuthService.ShouldUseSecureCookies(request),
                SameSite = SameSiteMode.Lax,
                Expires = session.ExpiresAtUtc.UtcDateTime,
                IsEssential = true,
                Path = "/"
            });
    }

    public void ClearCookie(HttpRequest request, HttpResponse response)
    {
        if (request is null)
        {
            throw new ArgumentNullException(nameof(request));
        }

        if (response is null)
        {
            throw new ArgumentNullException(nameof(response));
        }

        response.Cookies.Delete(
            HubBrowserAuthConstants.SubjectHintCookieName,
            new CookieOptions
            {
                Path = "/",
                SameSite = SameSiteMode.Lax,
                HttpOnly = true,
                Secure = HubBrowserAuthService.ShouldUseSecureCookies(request),
                IsEssential = true
            });
    }

    public bool TryRead(HttpRequest request, out AuthenticatedHubSubject? subject)
    {
        subject = null;
        if (request is null
            || !TryExtractRequestAccessToken(request, out string? accessToken)
            || !request.Cookies.TryGetValue(HubBrowserAuthConstants.SubjectHintCookieName, out string? protectedPayload)
            || string.IsNullOrWhiteSpace(protectedPayload))
        {
            return false;
        }

        HubSignedInHintCookiePayload? payload;
        try
        {
            payload = JsonSerializer.Deserialize<HubSignedInHintCookiePayload>(_protector.Unprotect(protectedPayload), _jsonOptions);
        }
        catch
        {
            return false;
        }

        if (payload is null
            || string.IsNullOrWhiteSpace(payload.SubjectId)
            || payload.ExpiresAtUtc <= DateTimeOffset.UtcNow
            || !string.Equals(payload.AccessTokenHash, ComputeTokenHash(accessToken!), StringComparison.Ordinal))
        {
            return false;
        }

        subject = new AuthenticatedHubSubject(
            payload.SubjectId.Trim(),
            string.IsNullOrWhiteSpace(payload.DisplayName) ? "Signed in" : payload.DisplayName.Trim(),
            string.IsNullOrWhiteSpace(payload.Email) ? null : payload.Email.Trim(),
            payload.Roles?.Where(static role => !string.IsNullOrWhiteSpace(role)).ToArray() ?? Array.Empty<string>(),
            accessToken!);
        return true;
    }

    private static bool TryExtractRequestAccessToken(HttpRequest request, out string? accessToken)
    {
        accessToken = null;
        string header = request.Headers.Authorization.ToString();
        if (!string.IsNullOrWhiteSpace(header)
            && header.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase))
        {
            string token = header["Bearer ".Length..].Trim();
            if (!string.IsNullOrWhiteSpace(token))
            {
                accessToken = token;
                return true;
            }
        }

        if (request.Cookies.TryGetValue(HubBrowserAuthConstants.AccessTokenCookieName, out string? cookieToken)
            && !string.IsNullOrWhiteSpace(cookieToken))
        {
            accessToken = cookieToken.Trim();
            return true;
        }

        return false;
    }

    private static string ComputeTokenHash(string accessToken)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(accessToken)));

    private sealed record HubSignedInHintCookiePayload(
        string SubjectId,
        string DisplayName,
        string? Email,
        IReadOnlyList<string> Roles,
        string AccessTokenHash,
        DateTimeOffset ExpiresAtUtc);
}
