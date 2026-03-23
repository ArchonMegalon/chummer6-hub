using System.Security.Cryptography;
using System.Text.Json;
using Chummer.Run.Contracts.Identity;
using Microsoft.AspNetCore.DataProtection;

namespace Chummer.Run.Api.Services;

public sealed record HubEmailLinkVerificationPayload(
    string AccountSubjectId,
    string Email,
    string NextPath,
    DateTimeOffset ExpiresAtUtc);

public sealed class HubEmailLinkVerificationService
{
    private readonly IDataProtector _protector;

    public HubEmailLinkVerificationService(IDataProtectionProvider dataProtectionProvider)
    {
        _protector = dataProtectionProvider.CreateProtector("chummer.hub.email-link");
    }

    public string CreateVerificationToken(string accountSubjectId, string email, string nextPath)
    {
        var payload = new HubEmailLinkVerificationPayload(
            AccountSubjectId: accountSubjectId.Trim(),
            Email: email.Trim().ToLowerInvariant(),
            NextPath: HubBrowserAuthService.SanitizeNextPath(nextPath),
            ExpiresAtUtc: DateTimeOffset.UtcNow.AddMinutes(20));
        return _protector.Protect(JsonSerializer.Serialize(payload));
    }

    public HubEmailLinkVerificationPayload ReadVerificationToken(string token)
    {
        if (string.IsNullOrWhiteSpace(token))
        {
            throw new InvalidOperationException("Email verification token was missing.");
        }

        try
        {
            var payload = JsonSerializer.Deserialize<HubEmailLinkVerificationPayload>(_protector.Unprotect(token))
                ?? throw new InvalidOperationException("Email verification token payload was empty.");
            if (payload.ExpiresAtUtc <= DateTimeOffset.UtcNow)
            {
                throw new InvalidOperationException("Email verification token expired.");
            }

            return payload with
            {
                AccountSubjectId = payload.AccountSubjectId.Trim(),
                Email = payload.Email.Trim().ToLowerInvariant(),
                NextPath = HubBrowserAuthService.SanitizeNextPath(payload.NextPath)
            };
        }
        catch (Exception ex) when (ex is CryptographicException or JsonException or InvalidOperationException)
        {
            throw new InvalidOperationException("Email verification token was not valid anymore.", ex);
        }
    }

    public string BuildVerificationCallbackPath(string token)
        => $"/auth/email/link/callback?token={Uri.EscapeDataString(token)}";

    public bool MatchesVerifiedEmailSubject(HubEmailLinkVerificationPayload payload, string subjectId)
        => string.Equals(
            IdentitySubjectDerivation.FromEmail(payload.Email),
            subjectId?.Trim(),
            StringComparison.OrdinalIgnoreCase);
}
