using Chummer.Hub.Registry.Contracts.InstallLinking;

namespace Chummer.Run.Api.Services.InstallLinking;

public sealed class InstallLinkedWorkspaceSnapshotService
{
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
            WorkspaceId = NormalizeRequired(snapshot.WorkspaceId, "workspace id"),
            RulesetId = NormalizeRequired(snapshot.RulesetId, "ruleset id"),
            Format = NormalizeRequired(snapshot.Format, "format"),
            PayloadKind = NormalizeRequired(snapshot.PayloadKind, "payload kind"),
            Payload = snapshot.Payload ?? string.Empty,
            OriginInstallationId = NormalizeOptional(snapshot.OriginInstallationId) ?? installation.InstallationId,
            Name = NormalizeOptional(snapshot.Name),
            Alias = NormalizeOptional(snapshot.Alias),
            Metatype = NormalizeOptional(snapshot.Metatype),
            BuildMethod = NormalizeOptional(snapshot.BuildMethod),
            CreatedVersion = NormalizeOptional(snapshot.CreatedVersion),
            AppVersion = NormalizeOptional(snapshot.AppVersion)
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
        string? subjectId = NormalizeOptional(installation.SubjectId);
        if (!string.IsNullOrWhiteSpace(subjectId))
        {
            return $"subject:{subjectId}";
        }

        string? userId = NormalizeOptional(installation.UserId);
        if (!string.IsNullOrWhiteSpace(userId))
        {
            return $"user:{userId}";
        }

        throw new InvalidOperationException("claimed installation has no user or subject identity.");
    }

    private static string NormalizeRequired(string? value, string label)
        => NormalizeOptional(value) ?? throw new InstallLinkingOperationException(StatusCodes.Status400BadRequest, $"{label} is required.");

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
