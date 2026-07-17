using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.DataProtection;

namespace Chummer.Run.Api.Services;

public sealed record InstallBootstrapArtifactBinding(
    string ArtifactId,
    string Sha256,
    string Role = ArtifactDeliveryRoles.Primary);

public sealed record InstallBootstrapTicketClaims(
    string ArtifactId,
    IReadOnlyList<string> AllowedArtifactIds,
    string? UserId,
    string? SubjectId,
    DateTimeOffset IssuedAtUtc,
    DateTimeOffset ExpiresAtUtc,
    string? GenerationId = null,
    IReadOnlyList<InstallBootstrapArtifactBinding>? ArtifactBindings = null);

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
        return IssueCore(
            normalizedArtifactId,
            normalizedAllowedArtifactIds,
            generationId: null,
            artifactBindings: Array.Empty<InstallBootstrapArtifactBinding>(),
            userId,
            subjectId);
    }

    public InstallBootstrapTicketIssueResult IssueBound(
        string artifactId,
        IEnumerable<InstallBootstrapArtifactBinding> artifactBindings,
        string generationId,
        string? userId,
        string? subjectId)
    {
        string normalizedArtifactId = NormalizeRequired(artifactId, nameof(artifactId));
        string normalizedGenerationId = NormalizeRequired(generationId, nameof(generationId));
        InstallBootstrapArtifactBinding[] normalizedBindings = NormalizeArtifactBindings(
            normalizedArtifactId,
            artifactBindings,
            requireBindings: true);
        return IssueCore(
            normalizedArtifactId,
            normalizedBindings.Select(static binding => binding.ArtifactId).ToArray(),
            normalizedGenerationId,
            normalizedBindings,
            userId,
            subjectId);
    }

    private InstallBootstrapTicketIssueResult IssueCore(
        string normalizedArtifactId,
        string[] normalizedAllowedArtifactIds,
        string? generationId,
        InstallBootstrapArtifactBinding[] artifactBindings,
        string? userId,
        string? subjectId)
    {
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
            ExpiresAtUtc: issuedAtUtc.Add(_ticketLifetime),
            GenerationId: generationId,
            ArtifactBindings: artifactBindings);

        InstallBootstrapTicketPayload payload = new(
            ArtifactId: claims.ArtifactId,
            AllowedArtifactIds: normalizedAllowedArtifactIds,
            UserId: claims.UserId,
            SubjectId: claims.SubjectId,
            IssuedAtUtc: claims.IssuedAtUtc,
            ExpiresAtUtc: claims.ExpiresAtUtc,
            Scope: "install_bootstrap",
            Nonce: Guid.NewGuid().ToString("N"),
            GenerationId: claims.GenerationId,
            ArtifactBindings: artifactBindings);

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

        string normalizedArtifactId;
        string[] normalizedAllowedArtifactIds;
        string? normalizedGenerationId;
        InstallBootstrapArtifactBinding[] normalizedBindings;
        try
        {
            normalizedArtifactId = NormalizeRequired(payload.ArtifactId, nameof(payload.ArtifactId));
            normalizedAllowedArtifactIds = NormalizeAllowedArtifactIds(normalizedArtifactId, payload.AllowedArtifactIds);
            normalizedGenerationId = NormalizeOptional(payload.GenerationId);
            normalizedBindings = NormalizeArtifactBindings(
                normalizedArtifactId,
                payload.ArtifactBindings,
                requireBindings: normalizedGenerationId is not null);
        }
        catch (ArgumentException)
        {
            return false;
        }

        if (normalizedGenerationId is null)
        {
            if (normalizedBindings.Length != 0)
            {
                return false;
            }
        }
        else if (!normalizedAllowedArtifactIds.ToHashSet(StringComparer.OrdinalIgnoreCase)
                     .SetEquals(normalizedBindings.Select(static binding => binding.ArtifactId)))
        {
            return false;
        }

        claims = new InstallBootstrapTicketClaims(
            ArtifactId: normalizedArtifactId,
            AllowedArtifactIds: normalizedAllowedArtifactIds,
            UserId: NormalizeOptional(payload.UserId),
            SubjectId: NormalizeOptional(payload.SubjectId),
            IssuedAtUtc: payload.IssuedAtUtc,
            ExpiresAtUtc: payload.ExpiresAtUtc,
            GenerationId: normalizedGenerationId,
            ArtifactBindings: normalizedBindings);
        return true;
    }

    public bool TryValidateForArtifact(
        string? ticket,
        string artifactId,
        string? generationId,
        string? artifactSha256,
        bool allowLegacyUnbound,
        out InstallBootstrapTicketClaims? claims)
        => TryValidateForArtifactRole(
            ticket,
            artifactId,
            ArtifactDeliveryRoles.Primary,
            generationId,
            artifactSha256,
            allowLegacyUnbound,
            out claims);

    public bool TryValidateForArtifactRole(
        string? ticket,
        string artifactId,
        string role,
        string? generationId,
        string? artifactSha256,
        bool allowLegacyUnbound,
        out InstallBootstrapTicketClaims? claims)
    {
        claims = null;
        if (!TryValidate(ticket, out InstallBootstrapTicketClaims? validatedClaims)
            || validatedClaims is null)
        {
            return false;
        }

        string normalizedArtifactId = NormalizeRequired(artifactId, nameof(artifactId));
        string normalizedRole;
        try
        {
            normalizedRole = NormalizeRole(role, nameof(role));
        }
        catch (ArgumentException)
        {
            return false;
        }

        if (!validatedClaims.AllowedArtifactIds.Contains(normalizedArtifactId, StringComparer.OrdinalIgnoreCase))
        {
            return false;
        }

        string? normalizedRequestedGenerationId = NormalizeOptional(generationId);
        if (validatedClaims.GenerationId is null)
        {
            if (!allowLegacyUnbound
                || normalizedRequestedGenerationId is not null
                || !string.Equals(normalizedRole, ArtifactDeliveryRoles.Primary, StringComparison.Ordinal))
            {
                return false;
            }

            claims = validatedClaims;
            return true;
        }

        if (normalizedRequestedGenerationId is null
            || !string.Equals(validatedClaims.GenerationId, normalizedRequestedGenerationId, StringComparison.Ordinal))
        {
            return false;
        }

        string normalizedArtifactSha256;
        try
        {
            normalizedArtifactSha256 = NormalizeSha256(artifactSha256, nameof(artifactSha256));
        }
        catch (ArgumentException)
        {
            return false;
        }

        InstallBootstrapArtifactBinding? binding = validatedClaims.ArtifactBindings?
            .FirstOrDefault(item =>
                string.Equals(item.ArtifactId, normalizedArtifactId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.Role, normalizedRole, StringComparison.Ordinal));
        if (binding is null || !FixedTimeEquals(binding.Sha256, normalizedArtifactSha256))
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

    private static InstallBootstrapArtifactBinding[] NormalizeArtifactBindings(
        string primaryArtifactId,
        IEnumerable<InstallBootstrapArtifactBinding>? artifactBindings,
        bool requireBindings)
    {
        Dictionary<(string ArtifactId, string Role), string> normalized = new();
        foreach (InstallBootstrapArtifactBinding binding in artifactBindings ?? Array.Empty<InstallBootstrapArtifactBinding>())
        {
            string artifactId = NormalizeRequired(binding.ArtifactId, nameof(binding.ArtifactId));
            string sha256 = NormalizeSha256(binding.Sha256, nameof(binding.Sha256));
            string role = NormalizeRole(binding.Role, nameof(binding.Role));
            var key = (artifactId.ToLowerInvariant(), role);
            if (normalized.TryGetValue(key, out string? existingSha256)
                && !FixedTimeEquals(existingSha256, sha256))
            {
                throw new ArgumentException(
                    $"conflicting SHA-256 bindings for artifact role '{artifactId}/{role}'.",
                    nameof(artifactBindings));
            }

            normalized[key] = sha256;
        }

        if (requireBindings
            && !normalized.ContainsKey((primaryArtifactId.ToLowerInvariant(), ArtifactDeliveryRoles.Primary)))
        {
            throw new ArgumentException("primary artifact binding is required.", nameof(artifactBindings));
        }

        return normalized
            .OrderBy(static item => item.Key.ArtifactId, StringComparer.Ordinal)
            .ThenBy(static item => item.Key.Role, StringComparer.Ordinal)
            .Select(static item => new InstallBootstrapArtifactBinding(
                item.Key.ArtifactId,
                item.Value,
                item.Key.Role))
            .ToArray();
    }

    private static string NormalizeRole(string? value, string paramName)
    {
        string normalized = NormalizeRequired(value, paramName).Trim().ToLowerInvariant();
        return ArtifactDeliveryRoles.IsKnown(normalized)
            ? normalized
            : throw new ArgumentException("artifact delivery role is invalid", paramName);
    }

    private static string NormalizeSha256(string? value, string paramName)
    {
        string normalized = NormalizeRequired(value, paramName).ToLowerInvariant();
        if (normalized.Length != 64 || normalized.Any(static character => !Uri.IsHexDigit(character)))
        {
            throw new ArgumentException("SHA-256 must be exactly 64 hexadecimal characters.", paramName);
        }

        return normalized;
    }

    private static bool FixedTimeEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.ASCII.GetBytes(left);
        byte[] rightBytes = Encoding.ASCII.GetBytes(right);
        return leftBytes.Length == rightBytes.Length
            && CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
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
        string Nonce,
        string? GenerationId = null,
        IReadOnlyList<InstallBootstrapArtifactBinding>? ArtifactBindings = null);
}
