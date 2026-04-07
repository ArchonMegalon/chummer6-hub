using System.Text.Json;
using Microsoft.AspNetCore.DataProtection;

namespace Chummer.Run.Api.Services;

public sealed record InstallBootstrapTicketClaims(
    string ArtifactId,
    IReadOnlyList<string> AllowedArtifactIds,
    string? UserId,
    string? SubjectId,
    DateTimeOffset IssuedAtUtc,
    DateTimeOffset ExpiresAtUtc);

public sealed record InstallBootstrapTicketIssueResult(
    string Ticket,
    InstallBootstrapTicketClaims Claims);

public sealed class InstallBootstrapTicketService
{
    private const string Purpose = "chummer.run.install-bootstrap-ticket.v1";
    private static readonly TimeSpan DefaultLifetime = TimeSpan.FromMinutes(30);
    private readonly IDataProtector _protector;
    private readonly TimeSpan _ticketLifetime;

    public InstallBootstrapTicketService(
        IDataProtectionProvider dataProtectionProvider,
        IConfiguration configuration)
    {
        _protector = dataProtectionProvider.CreateProtector(Purpose);
        _ticketLifetime = ResolveTicketLifetime(configuration);
    }

    public InstallBootstrapTicketIssueResult Issue(
        string artifactId,
        IEnumerable<string>? allowedArtifactIds,
        string? userId,
        string? subjectId)
    {
        string normalizedArtifactId = NormalizeRequired(artifactId, nameof(artifactId));
        string[] normalizedAllowedArtifactIds = NormalizeAllowedArtifactIds(normalizedArtifactId, allowedArtifactIds);
        string? normalizedUserId = NormalizeOptional(userId);
        string? normalizedSubjectId = NormalizeOptional(subjectId);
        if (normalizedUserId is null && normalizedSubjectId is null)
        {
            throw new ArgumentException("install bootstrap ticket requires a user id or subject id.");
        }

        DateTimeOffset issuedAtUtc = DateTimeOffset.UtcNow;
        InstallBootstrapTicketClaims claims = new(
            ArtifactId: normalizedArtifactId,
            AllowedArtifactIds: normalizedAllowedArtifactIds,
            UserId: normalizedUserId,
            SubjectId: normalizedSubjectId,
            IssuedAtUtc: issuedAtUtc,
            ExpiresAtUtc: issuedAtUtc.Add(_ticketLifetime));

        InstallBootstrapTicketPayload payload = new(
            ArtifactId: claims.ArtifactId,
            AllowedArtifactIds: normalizedAllowedArtifactIds,
            UserId: claims.UserId,
            SubjectId: claims.SubjectId,
            IssuedAtUtc: claims.IssuedAtUtc,
            ExpiresAtUtc: claims.ExpiresAtUtc,
            Scope: "install_bootstrap",
            Nonce: Guid.NewGuid().ToString("N"));

        string ticket = _protector.Protect(JsonSerializer.Serialize(payload));
        return new InstallBootstrapTicketIssueResult(ticket, claims);
    }

    public InstallBootstrapTicketIssueResult Issue(
        string artifactId,
        string? userId,
        string? subjectId)
        => Issue(artifactId, allowedArtifactIds: null, userId, subjectId);

    public bool TryValidate(string? ticket, out InstallBootstrapTicketClaims? claims)
    {
        claims = null;
        if (string.IsNullOrWhiteSpace(ticket))
        {
            return false;
        }

        InstallBootstrapTicketPayload? payload;
        try
        {
            payload = JsonSerializer.Deserialize<InstallBootstrapTicketPayload>(_protector.Unprotect(ticket.Trim()));
        }
        catch
        {
            return false;
        }

        if (payload is null
            || !string.Equals(payload.Scope, "install_bootstrap", StringComparison.Ordinal)
            || string.IsNullOrWhiteSpace(payload.ArtifactId)
            || (string.IsNullOrWhiteSpace(payload.UserId) && string.IsNullOrWhiteSpace(payload.SubjectId))
            || payload.ExpiresAtUtc <= DateTimeOffset.UtcNow)
        {
            return false;
        }

        string normalizedArtifactId = NormalizeRequired(payload.ArtifactId, nameof(payload.ArtifactId));
        string[] normalizedAllowedArtifactIds = NormalizeAllowedArtifactIds(normalizedArtifactId, payload.AllowedArtifactIds);
        claims = new InstallBootstrapTicketClaims(
            ArtifactId: normalizedArtifactId,
            AllowedArtifactIds: normalizedAllowedArtifactIds,
            UserId: NormalizeOptional(payload.UserId),
            SubjectId: NormalizeOptional(payload.SubjectId),
            IssuedAtUtc: payload.IssuedAtUtc,
            ExpiresAtUtc: payload.ExpiresAtUtc);
        return true;
    }

    public bool TryValidateForArtifact(string? ticket, string artifactId, out InstallBootstrapTicketClaims? claims)
    {
        claims = null;
        if (!TryValidate(ticket, out InstallBootstrapTicketClaims? validatedClaims)
            || validatedClaims is null)
        {
            return false;
        }

        string normalizedArtifactId = NormalizeRequired(artifactId, nameof(artifactId));
        if (!validatedClaims.AllowedArtifactIds.Contains(normalizedArtifactId, StringComparer.OrdinalIgnoreCase))
        {
            return false;
        }

        claims = validatedClaims;
        return true;
    }

    private static TimeSpan ResolveTicketLifetime(IConfiguration configuration)
    {
        string? configured = configuration["CHUMMER_INSTALL_BOOTSTRAP_TICKET_LIFETIME_MINUTES"];
        if (int.TryParse(configured, out int minutes))
        {
            minutes = Math.Clamp(minutes, 5, 12 * 60);
            return TimeSpan.FromMinutes(minutes);
        }

        return DefaultLifetime;
    }

    private static string NormalizeRequired(string? value, string paramName)
        => string.IsNullOrWhiteSpace(value)
            ? throw new ArgumentException("required value missing", paramName)
            : value.Trim();

    private static string[] NormalizeAllowedArtifactIds(string primaryArtifactId, IEnumerable<string>? allowedArtifactIds)
    {
        HashSet<string> normalized = new(StringComparer.OrdinalIgnoreCase)
        {
            NormalizeRequired(primaryArtifactId, nameof(primaryArtifactId))
        };

        if (allowedArtifactIds is not null)
        {
            foreach (string candidate in allowedArtifactIds)
            {
                normalized.Add(NormalizeRequired(candidate, nameof(allowedArtifactIds)));
            }
        }

        return normalized
            .OrderBy(static value => value, StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private sealed record InstallBootstrapTicketPayload(
        string ArtifactId,
        IReadOnlyList<string> AllowedArtifactIds,
        string? UserId,
        string? SubjectId,
        DateTimeOffset IssuedAtUtc,
        DateTimeOffset ExpiresAtUtc,
        string Scope,
        string Nonce);
}
