using Chummer.Run.Contracts.Observability;

namespace Chummer.Run.Contracts.Relay;

public sealed record SessionEventEnvelope(
    string SessionId,
    string SceneId,
    string EventType,
    string Payload,
    DateTimeOffset AtUtc,
    string EventId,
    string? SceneRevision = null,
    string? IdempotencyKey = null,
    string ContractFamily = "session_events_vnext");

public sealed record SessionRelayConvergenceDiagnostics(
    string ContractFamily,
    int SubmittedEvents,
    int AcceptedEvents,
    int DuplicateEvents,
    int IgnoredEvents,
    string SceneIdentity,
    string ProjectionFingerprint,
    bool Converged,
    DateTimeOffset EvaluatedAtUtc);

public sealed record SessionRelayMergeResponse(
    string SessionId,
    string SceneId,
    int AcceptedEvents,
    int DuplicateEvents,
    int IgnoredEvents,
    SessionEventProjectionDto Projection,
    DateTimeOffset MergedAtUtc,
    SessionRelayConvergenceDiagnostics Diagnostics);

public sealed record SessionEventProjectionDto(
    string SessionId,
    string SceneId,
    int Version,
    string ProjectionFingerprint,
    DateTimeOffset GeneratedAtUtc,
    IReadOnlyList<SessionEventEnvelope> Events,
    string ContractFamily = "session_events_vnext");

public sealed record SessionRuntimeBundleDto(
    string SessionId,
    string SceneId,
    string BundleVersion,
    bool Ready,
    int ProjectionVersion,
    string ProjectionFingerprint,
    DateTimeOffset GeneratedAtUtc,
    IReadOnlyList<string> InvalidationSignals,
    IReadOnlyList<string> IncludedEventTypes,
    bool OfflineCapable,
    string CollaborationMode,
    IReadOnlyList<string> SupportedExchangeFormats,
    string ContractFamily = "runtime_dtos_vnext",
    string RuntimeDtoKind = "session-runtime-bundle");

public sealed record OfflineSyncPrepChecklistItem(
    string ItemId,
    string Label,
    bool Completed = false,
    string? Notes = null);

public sealed record OfflineSyncPrepAsset(
    string AssetId,
    string CampaignId,
    string SessionId,
    string SceneId,
    string Title,
    string Kind,
    string Audience,
    string? Summary,
    string Body,
    IReadOnlyList<string> Tags,
    IReadOnlyList<OfflineSyncPrepChecklistItem> ChecklistItems,
    string Status,
    string? CreatedBy,
    string? RuntimeFingerprint,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? LastRevealedAtUtc = null,
    string? LastRevealChannel = null,
    int RevealCount = 0);

public sealed record OfflineSyncSnapshotRequest(
    string CampaignId,
    string SessionId,
    string SceneId,
    string ExportedBy,
    string? DeviceId = null,
    IReadOnlyList<string>? PrepAssetIds = null);

public sealed record OfflineSyncSnapshotPackage(
    string SnapshotId,
    string CampaignId,
    string SessionId,
    string SceneId,
    string ExportedBy,
    string? DeviceId,
    DateTimeOffset ExportedAtUtc,
    SessionEventProjectionDto SessionProjection,
    SessionRuntimeBundleDto RuntimeBundle,
    IReadOnlyList<OfflineSyncPrepAsset> PrepAssets,
    string SessionFingerprint,
    string PrepFingerprint,
    string PackageHash,
    string ContractFamily = "offline_sync_snapshot_v1");

public sealed record OfflineSyncConflict(
    string Surface,
    string EntityId,
    string Reason,
    string Resolution,
    string? LocalFingerprint = null,
    string? RemoteFingerprint = null);

public sealed record OfflineSyncSurfaceMergeResult(
    string Surface,
    int ImportedCount,
    int SkippedCount,
    IReadOnlyList<OfflineSyncConflict> Conflicts);

public sealed record OfflineSyncReconcileRequest(
    OfflineSyncSnapshotPackage Snapshot,
    string ReconciledBy,
    string? DeviceId = null,
    IReadOnlyList<SessionEventEnvelope>? LocalPendingEvents = null,
    IReadOnlyList<OfflineSyncPrepAsset>? LocalPrepAssets = null);

public sealed record OfflineSyncReconcileResult(
    string SnapshotId,
    string SessionId,
    string SceneId,
    string ReconciledBy,
    DateTimeOffset ReconciledAtUtc,
    SessionRelayMergeResponse SessionMerge,
    SessionRuntimeBundleDto RuntimeBundle,
    OfflineSyncSurfaceMergeResult SessionSurface,
    OfflineSyncSurfaceMergeResult PrepSurface,
    IReadOnlyList<OfflineSyncConflict> Conflicts,
    string ContractFamily = "offline_sync_snapshot_v1");

public sealed record SessionLedgerSceneBackup(
    string SessionId,
    string SceneId,
    IReadOnlyList<SessionEventEnvelope> Events);

public sealed record SessionLedgerBackupPackage(
    DateTimeOffset ExportedAtUtc,
    IReadOnlyList<SessionLedgerSceneBackup> Scenes,
    IReadOnlyList<PipelineDeadLetterEntry> DeadLetters,
    long ProcessedEvents,
    long AcceptedEvents,
    long DuplicateEvents,
    long IgnoredEvents,
    long IdempotencyReplayCount,
    DateTimeOffset? LastReplayAtUtc,
    string ContractFamily = "session_state_backup_v1");
