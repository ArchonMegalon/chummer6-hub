using System.Text.Json;
using Microsoft.AspNetCore.DataProtection;

namespace Chummer.Run.Api.Services;

public sealed record ReleaseUploadTicketClaims(
    string SubjectId,
    string? DisplayName,
    string? Email,
    DateTimeOffset IssuedAtUtc,
    DateTimeOffset ExpiresAtUtc);

public sealed record ReleaseUploadTicketIssueResult(
    string Ticket,
    ReleaseUploadTicketClaims Claims);

public sealed class ReleaseUploadTicketService
{
    private const string Purpose = "chummer.run.release-upload-ticket.v1";
    private static readonly TimeSpan DefaultLifetime = TimeSpan.FromHours(12);
    private readonly IDataProtector _protector;
    private readonly TimeSpan _ticketLifetime;

    public ReleaseUploadTicketService(
        IDataProtectionProvider dataProtectionProvider,
        IConfiguration configuration)
    {
        _protector = dataProtectionProvider.CreateProtector(Purpose);
        _ticketLifetime = ResolveTicketLifetime(configuration);
    }

    public ReleaseUploadTicketIssueResult Issue(AuthenticatedHubSubject subject)
    {
        ArgumentNullException.ThrowIfNull(subject);

        DateTimeOffset issuedAtUtc = DateTimeOffset.UtcNow;
        ReleaseUploadTicketClaims claims = new(
            SubjectId: subject.SubjectId,
            DisplayName: NormalizeOptional(subject.DisplayName),
            Email: NormalizeOptional(subject.Email),
            IssuedAtUtc: issuedAtUtc,
            ExpiresAtUtc: issuedAtUtc.Add(_ticketLifetime));

        ReleaseUploadTicketPayload payload = new(
            SubjectId: claims.SubjectId,
            DisplayName: claims.DisplayName,
            Email: claims.Email,
            IssuedAtUtc: claims.IssuedAtUtc,
            ExpiresAtUtc: claims.ExpiresAtUtc,
            Scope: "release_bundle_upload",
            Nonce: Guid.NewGuid().ToString("N"));

        string ticket = _protector.Protect(JsonSerializer.Serialize(payload));
        return new ReleaseUploadTicketIssueResult(ticket, claims);
    }

    public bool TryValidate(string? ticket, out ReleaseUploadTicketClaims? claims)
    {
        claims = null;
        if (string.IsNullOrWhiteSpace(ticket))
        {
            return false;
        }

        ReleaseUploadTicketPayload? payload;
        try
        {
            payload = JsonSerializer.Deserialize<ReleaseUploadTicketPayload>(_protector.Unprotect(ticket.Trim()));
        }
        catch
        {
            return false;
        }

        if (payload is null
            || !string.Equals(payload.Scope, "release_bundle_upload", StringComparison.Ordinal)
            || string.IsNullOrWhiteSpace(payload.SubjectId)
            || payload.ExpiresAtUtc <= DateTimeOffset.UtcNow)
        {
            return false;
        }

        claims = new ReleaseUploadTicketClaims(
            SubjectId: payload.SubjectId,
            DisplayName: NormalizeOptional(payload.DisplayName),
            Email: NormalizeOptional(payload.Email),
            IssuedAtUtc: payload.IssuedAtUtc,
            ExpiresAtUtc: payload.ExpiresAtUtc);
        return true;
    }

    private static TimeSpan ResolveTicketLifetime(IConfiguration configuration)
    {
        string? configured = configuration["CHUMMER_RELEASE_UPLOAD_TICKET_LIFETIME_MINUTES"];
        if (int.TryParse(configured, out int minutes))
        {
            minutes = Math.Clamp(minutes, 10, 12 * 60);
            return TimeSpan.FromMinutes(minutes);
        }

        return DefaultLifetime;
    }

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private sealed record ReleaseUploadTicketPayload(
        string SubjectId,
        string? DisplayName,
        string? Email,
        DateTimeOffset IssuedAtUtc,
        DateTimeOffset ExpiresAtUtc,
        string Scope,
        string Nonce);
}
