using System.Security.Cryptography;
using System.Text;

namespace Chummer.Run.Api.Services.InstallLinking;

public static class PersonalizedInstallScriptStates
{
    public const string Pending = "pending";
    public const string Consumed = "consumed";
    public const string Expired = "expired";
    public const string Revoked = "revoked";
}

public sealed record PersonalizedInstallScriptLinkDto(
    string ScriptId,
    string ArtifactId,
    IReadOnlyList<string> AllowedArtifactIds,
    string Platform,
    DateTimeOffset IssuedAtUtc,
    DateTimeOffset ExpiresAtUtc,
    string Status,
    string? UserId = null,
    string? SubjectId = null,
    string? RenderedScript = null,
    string? RenderedScriptSha256 = null,
    DateTimeOffset? ConsumedAtUtc = null);

public enum PersonalizedInstallScriptConsumeStatus
{
    Missing = 0,
    Consumed = 1,
    Expired = 2,
    Revoked = 3,
    Success = 4,
    DigestMismatch = 5,
}

public sealed record PersonalizedInstallScriptIssueResult(
    string ScriptId,
    PersonalizedInstallScriptLinkDto Link);

public sealed record PersonalizedInstallScriptConsumeResult(
    PersonalizedInstallScriptConsumeStatus Status,
    PersonalizedInstallScriptLinkDto? Link);

public sealed class PersonalizedInstallScriptService
{
    private static readonly TimeSpan DefaultLifetime = TimeSpan.FromDays(1);
    private const int DefaultMaxPendingPerPrincipal = 8;
    private const int DefaultMaxIssuedPerPrincipalPerHour = 24;
    private const int MaxIdentifierLength = 256;
    private const int Sha256HexLength = 64;
    private const int MaxRenderedScriptBytes = 1024 * 1024;
    private readonly Func<InstallLinkingStore> _storeAccessor;
    private InstallLinkingStore _store => _storeAccessor();
    private readonly TimeSpan _scriptLifetime;
    private readonly int _maxPendingPerPrincipal;
    private readonly int _maxIssuedPerPrincipalPerHour;
    private readonly IInstallLinkingStoreReadinessProbe? _readinessProbe;

    public PersonalizedInstallScriptService(
        InstallLinkingStore store,
        IConfiguration configuration,
        IInstallLinkingStoreReadinessProbe? readinessProbe = null)
        : this(
            () => store ?? throw new ArgumentNullException(nameof(store)),
            configuration,
            readinessProbe)
    {
    }

    public PersonalizedInstallScriptService(
        InstallLinkingStoreAccess storeAccess,
        IConfiguration configuration,
        IInstallLinkingStoreReadinessProbe readinessProbe)
        : this(
            (storeAccess ?? throw new ArgumentNullException(nameof(storeAccess))).GetRequired,
            configuration,
            readinessProbe)
    {
    }

    private PersonalizedInstallScriptService(
        Func<InstallLinkingStore> storeAccessor,
        IConfiguration configuration,
        IInstallLinkingStoreReadinessProbe? readinessProbe)
    {
        _storeAccessor = storeAccessor;
        ArgumentNullException.ThrowIfNull(configuration);
        _readinessProbe = readinessProbe;
        _scriptLifetime = ResolveLifetime(configuration);
        _maxPendingPerPrincipal = ResolveBoundedLimit(
            configuration["CHUMMER_PERSONALIZED_INSTALL_SCRIPT_MAX_PENDING_PER_PRINCIPAL"],
            DefaultMaxPendingPerPrincipal,
            maximum: 32);
        _maxIssuedPerPrincipalPerHour = ResolveBoundedLimit(
            configuration["CHUMMER_PERSONALIZED_INSTALL_SCRIPT_MAX_ISSUED_PER_PRINCIPAL_PER_HOUR"],
            DefaultMaxIssuedPerPrincipalPerHour,
            maximum: 128);
    }

    public PersonalizedInstallScriptIssueResult IssueMacScript(
        string artifactId,
        IEnumerable<string>? allowedArtifactIds,
        string? userId,
        string? subjectId,
        string? renderedScript = null,
        string? renderedScriptSha256 = null)
    {
        EnsureDurableStoreReady();
        string normalizedArtifactId = NormalizeRequired(artifactId, nameof(artifactId));
        string[] normalizedAllowedArtifactIds = NormalizeAllowedArtifactIds(normalizedArtifactId, allowedArtifactIds);
        string? normalizedUserId = NormalizeOptionalIdentifier(userId, nameof(userId));
        string? normalizedSubjectId = NormalizeOptionalIdentifier(subjectId, nameof(subjectId));
        string? normalizedRenderedScript = NormalizeRenderedScript(renderedScript);
        string? normalizedRenderedScriptSha256 = NormalizeOptional(renderedScriptSha256)?.ToLowerInvariant();
        if (normalizedRenderedScript is not null)
        {
            normalizedRenderedScriptSha256 = ComputeSha256Hex(normalizedRenderedScript);
        }
        else if (normalizedRenderedScriptSha256 is not null && !IsSha256(normalizedRenderedScriptSha256))
        {
            throw new ArgumentException("rendered script digest is invalid", nameof(renderedScriptSha256));
        }
        if (normalizedUserId is null && normalizedSubjectId is null)
        {
            throw new ArgumentException("personalized install script requires a user id or subject id.");
        }

        DateTimeOffset now = DateTimeOffset.UtcNow;
        PersonalizedInstallScriptLinkDto link = new(
            ScriptId: NewScriptId(),
            ArtifactId: normalizedArtifactId,
            AllowedArtifactIds: normalizedAllowedArtifactIds,
            Platform: "macos",
            IssuedAtUtc: now,
            ExpiresAtUtc: now.Add(_scriptLifetime),
            Status: PersonalizedInstallScriptStates.Pending,
            UserId: normalizedUserId,
            SubjectId: normalizedSubjectId,
            RenderedScript: normalizedRenderedScript,
            RenderedScriptSha256: normalizedRenderedScriptSha256);

        lock (_store.Gate)
        {
            ExpireLinksLocked(now);
            EnforceIssuanceLimitLocked(normalizedUserId, normalizedSubjectId, now);
            _store.PersonalizedInstallScriptsById[link.ScriptId] = link;
            _store.PersistLocked();
        }

        return new PersonalizedInstallScriptIssueResult(link.ScriptId, link);
    }

    public PersonalizedInstallScriptConsumeResult Consume(string? scriptId)
    {
        EnsureDurableStoreReady();
        string? normalizedScriptId = NormalizeOptional(scriptId);
        if (normalizedScriptId is null)
        {
            return new PersonalizedInstallScriptConsumeResult(PersonalizedInstallScriptConsumeStatus.Missing, null);
        }

        lock (_store.Gate)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            ExpireLinksLocked(now);
            if (!_store.PersonalizedInstallScriptsById.TryGetValue(normalizedScriptId, out PersonalizedInstallScriptLinkDto? link))
            {
                return new PersonalizedInstallScriptConsumeResult(PersonalizedInstallScriptConsumeStatus.Missing, null);
            }

            if (string.Equals(link.Status, PersonalizedInstallScriptStates.Consumed, StringComparison.OrdinalIgnoreCase))
            {
                return new PersonalizedInstallScriptConsumeResult(PersonalizedInstallScriptConsumeStatus.Consumed, link);
            }

            if (string.Equals(link.Status, PersonalizedInstallScriptStates.Revoked, StringComparison.OrdinalIgnoreCase))
            {
                return new PersonalizedInstallScriptConsumeResult(PersonalizedInstallScriptConsumeStatus.Revoked, link);
            }

            if (string.Equals(link.Status, PersonalizedInstallScriptStates.Expired, StringComparison.OrdinalIgnoreCase)
                || link.ExpiresAtUtc <= now)
            {
                if (!string.Equals(link.Status, PersonalizedInstallScriptStates.Expired, StringComparison.OrdinalIgnoreCase))
                {
                    link = link with { Status = PersonalizedInstallScriptStates.Expired, RenderedScript = null };
                    _store.PersonalizedInstallScriptsById[link.ScriptId] = link;
                    _store.PersistLocked();
                }

                return new PersonalizedInstallScriptConsumeResult(PersonalizedInstallScriptConsumeStatus.Expired, link);
            }

            PersonalizedInstallScriptLinkDto consumed = link with
            {
                Status = PersonalizedInstallScriptStates.Consumed,
                ConsumedAtUtc = now
            };
            _store.PersonalizedInstallScriptsById[consumed.ScriptId] = consumed with { RenderedScript = null };
            _store.PersistLocked();
            return new PersonalizedInstallScriptConsumeResult(PersonalizedInstallScriptConsumeStatus.Success, consumed);
        }
    }

    public PersonalizedInstallScriptConsumeResult Resolve(string? scriptId, string? expectedRenderedScriptSha256 = null)
    {
        EnsureDurableStoreReady();
        string? normalizedScriptId = NormalizeOptional(scriptId);
        if (normalizedScriptId is null)
        {
            return new PersonalizedInstallScriptConsumeResult(PersonalizedInstallScriptConsumeStatus.Missing, null);
        }

        string? normalizedExpectedRenderedScriptSha256 = NormalizeOptional(expectedRenderedScriptSha256)?.ToLowerInvariant();
        if (normalizedExpectedRenderedScriptSha256 is not null && !IsSha256(normalizedExpectedRenderedScriptSha256))
        {
            return new PersonalizedInstallScriptConsumeResult(
                PersonalizedInstallScriptConsumeStatus.DigestMismatch,
                null);
        }

        lock (_store.Gate)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            ExpireLinksLocked(now);
            if (!_store.PersonalizedInstallScriptsById.TryGetValue(normalizedScriptId, out PersonalizedInstallScriptLinkDto? link))
            {
                return new PersonalizedInstallScriptConsumeResult(PersonalizedInstallScriptConsumeStatus.Missing, null);
            }

            if (string.Equals(link.Status, PersonalizedInstallScriptStates.Revoked, StringComparison.OrdinalIgnoreCase))
            {
                return new PersonalizedInstallScriptConsumeResult(PersonalizedInstallScriptConsumeStatus.Revoked, link);
            }

            if (string.Equals(link.Status, PersonalizedInstallScriptStates.Expired, StringComparison.OrdinalIgnoreCase)
                || link.ExpiresAtUtc <= now)
            {
                if (!string.Equals(link.Status, PersonalizedInstallScriptStates.Expired, StringComparison.OrdinalIgnoreCase))
                {
                    link = link with { Status = PersonalizedInstallScriptStates.Expired, RenderedScript = null };
                    _store.PersonalizedInstallScriptsById[link.ScriptId] = link;
                    _store.PersistLocked();
                }

                return new PersonalizedInstallScriptConsumeResult(PersonalizedInstallScriptConsumeStatus.Expired, link);
            }

            string? actualRenderedScriptSha256 = NormalizeOptional(link.RenderedScriptSha256)?.ToLowerInvariant();
            if (link.RenderedScript is not null)
            {
                string renderedScriptDigest = ComputeSha256Hex(link.RenderedScript);
                if (actualRenderedScriptSha256 is null
                    || !IsSha256(actualRenderedScriptSha256)
                    || !string.Equals(renderedScriptDigest, actualRenderedScriptSha256, StringComparison.Ordinal))
                {
                    string? repairedRenderedScript = actualRenderedScriptSha256 is not null
                        && IsSha256(actualRenderedScriptSha256)
                        ? TryRestoreLegacyTrimmedRenderedScript(link.RenderedScript, actualRenderedScriptSha256)
                        : null;
                    if (repairedRenderedScript is not null)
                    {
                        link = link with { RenderedScript = repairedRenderedScript };
                        _store.PersonalizedInstallScriptsById[link.ScriptId] = link;
                        _store.PersistLocked();
                    }
                    else
                    {
                        return new PersonalizedInstallScriptConsumeResult(
                            PersonalizedInstallScriptConsumeStatus.DigestMismatch,
                            null);
                    }
                }
            }

            if (normalizedExpectedRenderedScriptSha256 is not null
                && !string.Equals(actualRenderedScriptSha256, normalizedExpectedRenderedScriptSha256, StringComparison.Ordinal))
            {
                return new PersonalizedInstallScriptConsumeResult(
                    PersonalizedInstallScriptConsumeStatus.DigestMismatch,
                    null);
            }

            return new PersonalizedInstallScriptConsumeResult(PersonalizedInstallScriptConsumeStatus.Success, link);
        }
    }

    private void ExpireLinksLocked(DateTimeOffset now)
    {
        bool dirty = false;
        foreach (PersonalizedInstallScriptLinkDto link in _store.PersonalizedInstallScriptsById.Values.ToArray())
        {
            if (!string.Equals(link.Status, PersonalizedInstallScriptStates.Pending, StringComparison.OrdinalIgnoreCase)
                || link.ExpiresAtUtc > now)
            {
                continue;
            }

            _store.PersonalizedInstallScriptsById[link.ScriptId] = link with
            {
                Status = PersonalizedInstallScriptStates.Expired,
                RenderedScript = null
            };
            dirty = true;
        }

        if (dirty)
        {
            _store.PersistLocked();
        }
    }

    private void EnforceIssuanceLimitLocked(string? userId, string? subjectId, DateTimeOffset now)
    {
        int pending = 0;
        int issuedLastHour = 0;
        DateTimeOffset cutoff = now.AddHours(-1);
        foreach (PersonalizedInstallScriptLinkDto link in _store.PersonalizedInstallScriptsById.Values)
        {
            bool matches = (!string.IsNullOrWhiteSpace(userId)
                    && string.Equals(link.UserId, userId, StringComparison.OrdinalIgnoreCase))
                || (!string.IsNullOrWhiteSpace(subjectId)
                    && string.Equals(link.SubjectId, subjectId, StringComparison.OrdinalIgnoreCase));
            if (!matches)
            {
                continue;
            }

            if (link.IssuedAtUtc >= cutoff)
            {
                issuedLastHour++;
            }

            if (string.Equals(link.Status, PersonalizedInstallScriptStates.Pending, StringComparison.OrdinalIgnoreCase)
                && link.ExpiresAtUtc > now)
            {
                pending++;
            }

            if (pending >= _maxPendingPerPrincipal
                || issuedLastHour >= _maxIssuedPerPrincipalPerHour)
            {
                throw new InvalidOperationException("Personalized install script issuance limit reached.");
            }
        }
    }

    private static int ResolveBoundedLimit(string? configured, int fallback, int maximum)
        => int.TryParse(configured, out int parsed)
            ? Math.Clamp(parsed, 1, maximum)
            : fallback;

    private void EnsureDurableStoreReady()
    {
        bool ready;
        try
        {
            ready = (_readinessProbe?.Evaluate().Ready ?? true) && _store.IsHealthy;
        }
        catch
        {
            ready = false;
        }

        if (!ready)
        {
            throw new InstallLinkingOperationException(
                StatusCodes.Status503ServiceUnavailable,
                "Install-linking is temporarily unavailable.");
        }
    }

    private static TimeSpan ResolveLifetime(IConfiguration configuration)
    {
        string? configuredHours = configuration["CHUMMER_PERSONALIZED_INSTALL_SCRIPT_LIFETIME_HOURS"];
        if (int.TryParse(configuredHours, out int hours))
        {
            hours = Math.Clamp(hours, 1, 7 * 24);
            return TimeSpan.FromHours(hours);
        }

        string? configuredMinutes = configuration["CHUMMER_PERSONALIZED_INSTALL_SCRIPT_LIFETIME_MINUTES"];
        if (int.TryParse(configuredMinutes, out int minutes))
        {
            minutes = Math.Clamp(minutes, 30, 7 * 24 * 60);
            return TimeSpan.FromMinutes(minutes);
        }

        return DefaultLifetime;
    }

    private static string NormalizeRequired(string? value, string paramName)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            throw new ArgumentException("required value missing", paramName);
        }

        string normalized = value.Trim();
        if (normalized.Length > MaxIdentifierLength || normalized.Any(char.IsControl))
        {
            throw new ArgumentException("identifier limit exceeded", paramName);
        }

        return normalized;
    }

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
                if (normalized.Count > 32)
                {
                    throw new ArgumentException("personalized install script artifact limit exceeded.", nameof(allowedArtifactIds));
                }
            }
        }

        return normalized
            .OrderBy(static value => value, StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static string NewScriptId()
        => Convert.ToHexString(RandomNumberGenerator.GetBytes(12)).ToLowerInvariant();

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string? NormalizeOptionalIdentifier(string? value, string paramName)
        => string.IsNullOrWhiteSpace(value) ? null : NormalizeRequired(value, paramName);

    private static bool IsSha256(string value)
        => value.Length == Sha256HexLength && value.All(Uri.IsHexDigit);

    private static string? NormalizeRenderedScript(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        if (Encoding.UTF8.GetByteCount(value) > MaxRenderedScriptBytes)
        {
            throw new ArgumentException("personalized install script payload limit exceeded.", nameof(value));
        }

        return value;
    }

    private static string ComputeSha256Hex(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    private static string? TryRestoreLegacyTrimmedRenderedScript(string renderedScript, string expectedSha256)
    {
        foreach (string suffix in new[] { "\n", "\r\n" })
        {
            string candidate = renderedScript + suffix;
            if (string.Equals(ComputeSha256Hex(candidate), expectedSha256, StringComparison.Ordinal))
            {
                return candidate;
            }
        }

        return null;
    }
}
