using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.DataProtection;

namespace Chummer.Run.Api.Services;

public sealed record WindowsProofUploadTicketClaims(
    string SubjectId,
    string? DisplayName,
    string? Email,
    DateTimeOffset IssuedAtUtc,
    DateTimeOffset ExpiresAtUtc,
    string TicketId);

public sealed record WindowsProofUploadTicketIssueResult(
    string Ticket,
    WindowsProofUploadTicketClaims Claims);

/// <summary>
/// Issues a credential that is valid only for the isolated Windows proof upload lane.
/// Its Data Protection purpose and payload scope intentionally differ from canonical
/// release-upload tickets so neither credential can be replayed into the other lane.
/// </summary>
public sealed class WindowsProofUploadTicketService
{
    public const string TicketScope = "windows_proof_upload";
    private const string Purpose = "chummer.run.windows-proof-upload-ticket.v1";
    private const string RevocationEpochKey = "CHUMMER_WINDOWS_PROOF_UPLOAD_TICKET_REVOCATION_EPOCH";
    private const string DefaultRevocationEpoch = "1";
    private static readonly TimeSpan DefaultLifetime = TimeSpan.FromHours(6);

    private readonly IDataProtector _protector;
    private readonly TimeSpan _ticketLifetime;

    public WindowsProofUploadTicketService(
        IDataProtectionProvider dataProtectionProvider,
        IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(dataProtectionProvider);
        ArgumentNullException.ThrowIfNull(configuration);

        _protector = dataProtectionProvider.CreateProtector(
            Purpose,
            $"revocation-epoch:{HashRevocationEpoch(configuration[RevocationEpochKey])}");
        _ticketLifetime = ResolveTicketLifetime(configuration);
    }

    public WindowsProofUploadTicketIssueResult Issue(AuthenticatedHubSubject subject)
    {
        ArgumentNullException.ThrowIfNull(subject);

        DateTimeOffset issuedAtUtc = DateTimeOffset.UtcNow;
        var claims = new WindowsProofUploadTicketClaims(
            SubjectId: subject.SubjectId,
            DisplayName: NormalizeOptional(subject.DisplayName),
            Email: NormalizeOptional(subject.Email),
            IssuedAtUtc: issuedAtUtc,
            ExpiresAtUtc: issuedAtUtc.Add(_ticketLifetime),
            TicketId: Guid.NewGuid().ToString("N"));
        var payload = new WindowsProofUploadTicketPayload(
            claims.SubjectId,
            claims.DisplayName,
            claims.Email,
            claims.IssuedAtUtc,
            claims.ExpiresAtUtc,
            TicketScope,
            claims.TicketId);

        return new WindowsProofUploadTicketIssueResult(
            _protector.Protect(JsonSerializer.Serialize(payload)),
            claims);
    }

    public bool TryValidate(string? ticket, out WindowsProofUploadTicketClaims? claims)
    {
        claims = null;
        if (string.IsNullOrWhiteSpace(ticket))
        {
            return false;
        }

        WindowsProofUploadTicketPayload? payload;
        try
        {
            payload = JsonSerializer.Deserialize<WindowsProofUploadTicketPayload>(
                _protector.Unprotect(ticket.Trim()));
        }
        catch
        {
            return false;
        }

        if (payload is null
            || !string.Equals(payload.Scope, TicketScope, StringComparison.Ordinal)
            || string.IsNullOrWhiteSpace(payload.SubjectId)
            || !Guid.TryParseExact(payload.Nonce, "N", out _)
            || payload.IssuedAtUtc > DateTimeOffset.UtcNow.AddMinutes(1)
            || payload.ExpiresAtUtc <= DateTimeOffset.UtcNow
            || payload.ExpiresAtUtc <= payload.IssuedAtUtc)
        {
            return false;
        }

        claims = new WindowsProofUploadTicketClaims(
            payload.SubjectId,
            NormalizeOptional(payload.DisplayName),
            NormalizeOptional(payload.Email),
            payload.IssuedAtUtc,
            payload.ExpiresAtUtc,
            payload.Nonce);
        return true;
    }

    private static TimeSpan ResolveTicketLifetime(IConfiguration configuration)
    {
        string? raw = configuration["CHUMMER_WINDOWS_PROOF_UPLOAD_TICKET_LIFETIME_MINUTES"];
        return int.TryParse(raw, out int minutes)
            ? TimeSpan.FromMinutes(Math.Clamp(minutes, 10, 6 * 60))
            : DefaultLifetime;
    }

    private static string HashRevocationEpoch(string? configuredEpoch)
    {
        string epoch = string.IsNullOrWhiteSpace(configuredEpoch)
            ? DefaultRevocationEpoch
            : configuredEpoch.Trim();
        return Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(epoch)));
    }

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private sealed record WindowsProofUploadTicketPayload(
        string SubjectId,
        string? DisplayName,
        string? Email,
        DateTimeOffset IssuedAtUtc,
        DateTimeOffset ExpiresAtUtc,
        string Scope,
        string Nonce);
}
