using System.Security.Cryptography;
using System.Text;
using Chummer.Run.AI.Services.Ops;
using Chummer.Run.Contracts.Ops;

namespace Chummer.Run.AI.Services.Session;

public interface IOfflineSyncService
{
    OfflineSyncSnapshotPackage CreateSnapshot(OfflineSyncSnapshotRequest request);
    Task<OfflineSyncReconcileResult> ReconcileAsync(OfflineSyncReconcileRequest request, CancellationToken cancellationToken = default);
}

public sealed class OfflineSyncService : IOfflineSyncService
{
    private readonly ISessionLedgerService _ledger;
    private readonly ISessionRuntimeBundleService _runtimeBundles;
    private readonly IGmOpsBoardService _opsBoard;

    public OfflineSyncService(
        ISessionLedgerService ledger,
        ISessionRuntimeBundleService runtimeBundles,
        IGmOpsBoardService opsBoard)
    {
        _ledger = ledger;
        _runtimeBundles = runtimeBundles;
        _opsBoard = opsBoard;
    }

    public OfflineSyncSnapshotPackage CreateSnapshot(OfflineSyncSnapshotRequest request)
    {
        var projection = _ledger.GetProjection(request.SessionId.Trim(), request.SceneId.Trim());
        var runtimeBundle = _runtimeBundles.ResolveBundle(request.SessionId.Trim(), request.SceneId.Trim());
        var prepAssets = _opsBoard
            .ExportPortableAssets(
                request.CampaignId.Trim(),
                request.SessionId.Trim(),
                request.SceneId.Trim(),
                request.PrepAssetIds)
            .Select(ToPortableAsset)
            .OrderBy(static item => item.AssetId, StringComparer.Ordinal)
            .ToArray();
        var exportedAt = DateTimeOffset.UtcNow;
        var snapshotId = $"offline_{Guid.NewGuid():N}";
        var sessionFingerprint = ComputeSessionFingerprint(projection.Events);
        var prepFingerprint = ComputePrepFingerprint(prepAssets);
        var packageHash = ComputeHash($"{snapshotId}|{sessionFingerprint}|{prepFingerprint}|{projection.ProjectionFingerprint}|{runtimeBundle.BundleVersion}");

        return new OfflineSyncSnapshotPackage(
            SnapshotId: snapshotId,
            CampaignId: request.CampaignId.Trim(),
            SessionId: request.SessionId.Trim(),
            SceneId: request.SceneId.Trim(),
            ExportedBy: request.ExportedBy.Trim(),
            DeviceId: NormalizeOptional(request.DeviceId),
            ExportedAtUtc: exportedAt,
            SessionProjection: projection,
            RuntimeBundle: runtimeBundle,
            PrepAssets: prepAssets,
            SessionFingerprint: sessionFingerprint,
            PrepFingerprint: prepFingerprint,
            PackageHash: packageHash);
    }

    public async Task<OfflineSyncReconcileResult> ReconcileAsync(OfflineSyncReconcileRequest request, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();

        var allEvents = request.Snapshot.SessionProjection.Events
            .Concat(request.LocalPendingEvents ?? Array.Empty<SessionEventEnvelope>())
            .ToArray();
        var merge = await _ledger.MergeEventsAsync(allEvents, cancellationToken);

        var prepSurface = _opsBoard.ReconcilePortableAssets(
            request.Snapshot.PrepAssets.Concat(request.LocalPrepAssets ?? Array.Empty<OfflineSyncPrepAsset>()).ToArray());
        var runtimeBundle = _runtimeBundles.ResolveBundle(request.Snapshot.SessionId, request.Snapshot.SceneId);

        var conflicts = new List<OfflineSyncConflict>(prepSurface.Conflicts);
        if (!string.Equals(request.Snapshot.PackageHash, RecomputePackageHash(request.Snapshot), StringComparison.Ordinal))
        {
            conflicts.Add(new OfflineSyncConflict(
                Surface: "package",
                EntityId: request.Snapshot.SnapshotId,
                Reason: "package-hash-mismatch",
                Resolution: "accepted-with-warning",
                LocalFingerprint: request.Snapshot.PackageHash,
                RemoteFingerprint: RecomputePackageHash(request.Snapshot)));
        }

        var sessionSurface = new OfflineSyncSurfaceMergeResult(
            Surface: "session-ledger",
            ImportedCount: merge.AcceptedEvents,
            SkippedCount: merge.DuplicateEvents + merge.IgnoredEvents,
            Conflicts: Array.Empty<OfflineSyncConflict>());

        return new OfflineSyncReconcileResult(
            SnapshotId: request.Snapshot.SnapshotId,
            SessionId: request.Snapshot.SessionId,
            SceneId: request.Snapshot.SceneId,
            ReconciledBy: request.ReconciledBy.Trim(),
            ReconciledAtUtc: DateTimeOffset.UtcNow,
            SessionMerge: merge,
            RuntimeBundle: runtimeBundle,
            SessionSurface: sessionSurface,
            PrepSurface: prepSurface,
            Conflicts: conflicts);
    }

    private static OfflineSyncPrepAsset ToPortableAsset(GmPrepAssetRecord asset)
    {
        return new OfflineSyncPrepAsset(
            AssetId: asset.AssetId,
            CampaignId: asset.CampaignId,
            SessionId: asset.SessionId ?? string.Empty,
            SceneId: asset.SceneId ?? string.Empty,
            Title: asset.Title,
            Kind: asset.Kind.ToString(),
            Audience: asset.Audience.ToString(),
            Summary: asset.Summary,
            Body: asset.Body,
            Tags: asset.Tags,
            ChecklistItems: asset.ChecklistItems.Select(static item => new OfflineSyncPrepChecklistItem(
                ItemId: item.ItemId,
                Label: item.Label,
                Completed: item.Completed,
                Notes: item.Notes)).ToArray(),
            Status: asset.Status,
            CreatedBy: asset.CreatedBy,
            RuntimeFingerprint: asset.RuntimeFingerprint,
            CreatedAtUtc: asset.CreatedAtUtc,
            UpdatedAtUtc: asset.UpdatedAtUtc,
            LastRevealedAtUtc: asset.LastRevealedAtUtc,
            LastRevealChannel: asset.LastRevealChannel,
            RevealCount: asset.RevealCount);
    }

    private static string RecomputePackageHash(OfflineSyncSnapshotPackage snapshot)
    {
        return ComputeHash($"{snapshot.SnapshotId}|{snapshot.SessionFingerprint}|{snapshot.PrepFingerprint}|{snapshot.SessionProjection.ProjectionFingerprint}|{snapshot.RuntimeBundle.BundleVersion}");
    }

    private static string ComputeSessionFingerprint(IReadOnlyList<SessionEventEnvelope> events)
    {
        var payload = string.Join('|', events
            .OrderBy(static item => item.AtUtc)
            .ThenBy(static item => item.EventId, StringComparer.Ordinal)
            .Select(static item => $"{item.EventId}:{item.EventType}:{item.AtUtc:O}:{item.SceneRevision}:{item.Payload}"));
        return ComputeHash(payload);
    }

    private static string ComputePrepFingerprint(IReadOnlyList<OfflineSyncPrepAsset> assets)
    {
        var payload = string.Join('|', assets
            .OrderBy(static item => item.AssetId, StringComparer.Ordinal)
            .Select(static item => $"{item.AssetId}:{item.Kind}:{item.Status}:{item.UpdatedAtUtc:O}:{string.Join(",", item.Tags)}"));
        return ComputeHash(payload);
    }

    private static string ComputeHash(string payload)
    {
        using var sha = SHA256.Create();
        var bytes = Encoding.UTF8.GetBytes(payload);
        return Convert.ToHexString(sha.ComputeHash(bytes));
    }

    private static string? NormalizeOptional(string? value) =>
        string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
