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
    private readonly InstallLinkingStore _store;
    private readonly TimeSpan _scriptLifetime;

    public PersonalizedInstallScriptService(InstallLinkingStore store, IConfiguration configuration)
    {
        _store = store;
        _scriptLifetime = ResolveLifetime(configuration);
    }

    public PersonalizedInstallScriptIssueResult IssueMacScript(
        string artifactId,
        IEnumerable<string>? allowedArtifactIds,
        string? userId,
        string? subjectId,
        string? renderedScript = null,
        string? renderedScriptSha256 = null)
    {
        string normalizedArtifactId = NormalizeRequired(artifactId, nameof(artifactId));
        string[] normalizedAllowedArtifactIds = NormalizeAllowedArtifactIds(normalizedArtifactId, allowedArtifactIds);
        string? normalizedUserId = NormalizeOptional(userId);
        string? normalizedSubjectId = NormalizeOptional(subjectId);
        string? normalizedRenderedScript = NormalizeRenderedScript(renderedScript);
        string? normalizedRenderedScriptSha256 = NormalizeOptional(renderedScriptSha256)?.ToLowerInvariant();
        if (normalizedRenderedScript is not null)
        {
            string renderedScriptDigest = ComputeSha256Hex(normalizedRenderedScript);
            if (!string.Equals(normalizedRenderedScriptSha256, renderedScriptDigest, StringComparison.Ordinal))
            {
                normalizedRenderedScriptSha256 = renderedScriptDigest;
            }
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
            _store.PersonalizedInstallScriptsById[link.ScriptId] = link;
            _store.PersistLocked();
        }

        return new PersonalizedInstallScriptIssueResult(link.ScriptId, link);
    }

    public PersonalizedInstallScriptConsumeResult Consume(string? scriptId)
    {
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
                    link = link with { Status = PersonalizedInstallScriptStates.Expired };
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
            _store.PersonalizedInstallScriptsById[consumed.ScriptId] = consumed;
            _store.PersistLocked();
            return new PersonalizedInstallScriptConsumeResult(PersonalizedInstallScriptConsumeStatus.Success, consumed);
        }
    }

    public PersonalizedInstallScriptConsumeResult Resolve(string? scriptId, string? expectedRenderedScriptSha256 = null)
    {
        string? normalizedScriptId = NormalizeOptional(scriptId);
        if (normalizedScriptId is null)
        {
            return new PersonalizedInstallScriptConsumeResult(PersonalizedInstallScriptConsumeStatus.Missing, null);
        }

        string? normalizedExpectedRenderedScriptSha256 = NormalizeOptional(expectedRenderedScriptSha256)?.ToLowerInvariant();

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
                    link = link with { Status = PersonalizedInstallScriptStates.Expired };
                    _store.PersonalizedInstallScriptsById[link.ScriptId] = link;
                    _store.PersistLocked();
                }

                return new PersonalizedInstallScriptConsumeResult(PersonalizedInstallScriptConsumeStatus.Expired, link);
            }

            string? actualRenderedScriptSha256 = NormalizeOptional(link.RenderedScriptSha256)?.ToLowerInvariant();
            if (link.RenderedScript is not null && actualRenderedScriptSha256 is not null)
            {
                string renderedScriptDigest = ComputeSha256Hex(link.RenderedScript);
                if (!string.Equals(renderedScriptDigest, actualRenderedScriptSha256, StringComparison.Ordinal))
                {
                    string? repairedRenderedScript = TryRestoreLegacyTrimmedRenderedScript(link.RenderedScript, actualRenderedScriptSha256);
                    if (repairedRenderedScript is not null)
                    {
                        link = link with { RenderedScript = repairedRenderedScript };
                        _store.PersonalizedInstallScriptsById[link.ScriptId] = link;
                        _store.PersistLocked();
                    }
                    else
                    {
                        actualRenderedScriptSha256 = renderedScriptDigest;
                    }
                }
            }

            if (normalizedExpectedRenderedScriptSha256 is not null
                && !string.Equals(actualRenderedScriptSha256, normalizedExpectedRenderedScriptSha256, StringComparison.Ordinal))
            {
                return new PersonalizedInstallScriptConsumeResult(PersonalizedInstallScriptConsumeStatus.DigestMismatch, link);
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
                Status = PersonalizedInstallScriptStates.Expired
            };
            dirty = true;
        }

        if (dirty)
        {
            _store.PersistLocked();
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

    private static string NewScriptId()
        => Convert.ToHexString(RandomNumberGenerator.GetBytes(12)).ToLowerInvariant();

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string? NormalizeRenderedScript(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value;

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
