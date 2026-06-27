using Chummer.Hub.Registry.Contracts.InstallLinking;

namespace Chummer.Run.Api.Services.InstallLinking;

public sealed class InstallLinkedWorkspaceSnapshotService
{
    public const int MaxUpsertRequestBodyBytes = 768 * 1024;
    public const int MaxUpsertPayloadCharacters = 512 * 1024;
    private const int MaxWorkspaceIdLength = 128;
    private const int MaxRulesetIdLength = 64;
    private const int MaxFormatLength = 64;
    private const int MaxPayloadKindLength = 64;
    private const int MaxOriginInstallationIdLength = 64;
    private const int MaxDisplayNameLength = 160;
    private const int MaxTraitLength = 64;
    private readonly InstallLinkedWorkspaceSnapshotStore _store;

    public InstallLinkedWorkspaceSnapshotService(InstallLinkedWorkspaceSnapshotStore store)
    {
        _store = store;
    }

    public IReadOnlyList<InstallLinkedWorkspaceSnapshotRecord> ListForInstallation(ClaimedInstallationDto installation)
    {
        ArgumentNullException.ThrowIfNull(installation);

        string ownerKey = ResolveOwnerKey(installation);
        lock (_store.Gate)
        {
            return _store.SnapshotsByKey.Values
                .Where(item => string.Equals(item.OwnerKey, ownerKey, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
        }
    }

    public InstallLinkedWorkspaceSnapshotRecord UpsertForInstallation(
        ClaimedInstallationDto installation,
        InstallLinkedWorkspaceSnapshotRecord snapshot)
    {
        ArgumentNullException.ThrowIfNull(installation);
        ArgumentNullException.ThrowIfNull(snapshot);

        string ownerKey = ResolveOwnerKey(installation);
        InstallLinkedWorkspaceSnapshotRecord normalized = snapshot with
        {
            OwnerKey = ownerKey,
            WorkspaceId = NormalizeRequired(snapshot.WorkspaceId, "workspace id", MaxWorkspaceIdLength),
            RulesetId = NormalizeRequired(snapshot.RulesetId, "ruleset id", MaxRulesetIdLength),
            Format = NormalizeRequired(snapshot.Format, "format", MaxFormatLength),
            PayloadKind = NormalizeRequired(snapshot.PayloadKind, "payload kind", MaxPayloadKindLength),
            Payload = NormalizePayload(snapshot.Payload),
            OriginInstallationId = NormalizeOptional(snapshot.OriginInstallationId, "origin installation id", MaxOriginInstallationIdLength) ?? installation.InstallationId,
            Name = NormalizeOptional(snapshot.Name, "name", MaxDisplayNameLength),
            Alias = NormalizeOptional(snapshot.Alias, "alias", MaxDisplayNameLength),
            Metatype = NormalizeOptional(snapshot.Metatype, "metatype", MaxTraitLength),
            BuildMethod = NormalizeOptional(snapshot.BuildMethod, "build method", MaxTraitLength),
            CreatedVersion = NormalizeOptional(snapshot.CreatedVersion, "created version", MaxTraitLength),
            AppVersion = NormalizeOptional(snapshot.AppVersion, "app version", MaxTraitLength)
        };

        lock (_store.Gate)
        {
            string key = InstallLinkedWorkspaceSnapshotStore.ComposeKey(ownerKey, normalized.WorkspaceId);
            if (_store.SnapshotsByKey.TryGetValue(key, out InstallLinkedWorkspaceSnapshotRecord? existing)
                && existing.UpdatedAtUtc >= normalized.UpdatedAtUtc)
            {
                return existing;
            }

            _store.SnapshotsByKey[key] = normalized;
            _store.PersistLocked();
            return normalized;
        }
    }

    private static string ResolveOwnerKey(ClaimedInstallationDto installation)
    {
        string? subjectId = string.IsNullOrWhiteSpace(installation.SubjectId) ? null : installation.SubjectId.Trim();
        if (!string.IsNullOrWhiteSpace(subjectId))
        {
            return $"subject:{subjectId}";
        }

        string? userId = string.IsNullOrWhiteSpace(installation.UserId) ? null : installation.UserId.Trim();
        if (!string.IsNullOrWhiteSpace(userId))
        {
            return $"user:{userId}";
        }

        throw new InvalidOperationException("claimed installation has no user or subject identity.");
    }

    private static string NormalizeRequired(string? value, string label, int maxLength)
        => NormalizeOptional(value, label, maxLength) ?? throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest, $"{label} is required.");

    private static string? NormalizeOptional(string? value, string label, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string normalized = value.Trim();
        if (normalized.Length > maxLength)
        {
            throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest, $"{label} exceeds the maximum length of {maxLength} characters.");
        }

        return normalized;
    }

    private static string NormalizePayload(string? payload)
    {
        string normalized = payload ?? string.Empty;
        if (normalized.Length > MaxUpsertPayloadCharacters)
        {
            throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest, $"payload exceeds the maximum length of {MaxUpsertPayloadCharacters} characters.");
        }

        return normalized;
    }
}
