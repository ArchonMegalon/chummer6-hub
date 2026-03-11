namespace Chummer.Run.AI.Compatibility;

[Obsolete("Use Chummer.Run.Contracts.Relay.SessionEventEnvelope.")]
internal sealed record SessionEventEnvelope(
    string SessionId,
    string SceneId,
    string EventType,
    string Payload,
    DateTimeOffset AtUtc,
    string EventId,
    string? SceneRevision = null,
    string? IdempotencyKey = null,
    string ContractFamily = "session_events_vnext");

[Obsolete("Use Chummer.Run.Contracts.Relay.SessionRelayConvergenceDiagnostics.")]
internal sealed record SessionRelayConvergenceDiagnostics(
    string ContractFamily,
    int SubmittedEvents,
    int AcceptedEvents,
    int DuplicateEvents,
    int IgnoredEvents,
    string SceneIdentity,
    string ProjectionFingerprint,
    bool Converged,
    DateTimeOffset EvaluatedAtUtc);

[Obsolete("Use Chummer.Run.Contracts.Relay.SessionRelayMergeResponse.")]
internal sealed record SessionRelayMergeResponse(
    string SessionId,
    string SceneId,
    int AcceptedEvents,
    int DuplicateEvents,
    int IgnoredEvents,
    SessionEventProjectionDto Projection,
    DateTimeOffset MergedAtUtc,
    SessionRelayConvergenceDiagnostics Diagnostics);

[Obsolete("Use Chummer.Run.Contracts.Relay.SessionEventProjectionDto.")]
internal sealed record SessionEventProjectionDto(
    string SessionId,
    string SceneId,
    int Version,
    string ProjectionFingerprint,
    DateTimeOffset GeneratedAtUtc,
    IReadOnlyList<SessionEventEnvelope> Events,
    string ContractFamily = "session_events_vnext");

[Obsolete("Use Chummer.Run.Contracts.Relay.SessionRuntimeBundleDto.")]
internal sealed record SessionRuntimeBundleDto(
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

[Obsolete("Use Chummer.Run.Contracts.Relay.SessionRelayMergeResponse.")]
internal sealed record SessionRelayMergeResult(
    string SessionId,
    string SceneId,
    int AcceptedEvents,
    int DuplicateEvents,
    int IgnoredEvents,
    SessionEventProjectionDto Projection,
    DateTimeOffset MergedAtUtc,
    SessionRelayConvergenceDiagnostics Diagnostics);

[Obsolete("Use Chummer.Run.Contracts.Relay.SessionEventProjectionDto.")]
internal sealed record SessionDeltaProjection(
    string SessionId,
    string SceneId,
    int Version,
    string ProjectionFingerprint,
    DateTimeOffset GeneratedAtUtc,
    IReadOnlyList<SessionEventEnvelope> Events,
    string ContractFamily = "session_events_vnext");

[Obsolete("Use Chummer.Run.Contracts.Relay.SessionRuntimeBundleDto.")]
internal sealed record SessionRuntimeBundleResponse(
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

[Obsolete("Use Chummer.Run.Contracts.Relay.OfflineSyncPrepChecklistItem.")]
internal sealed record OfflineSyncPrepChecklistItem(
    string ItemId,
    string Label,
    bool Completed = false,
    string? Notes = null);

[Obsolete("Use Chummer.Run.Contracts.Relay.OfflineSyncPrepAsset.")]
internal sealed record OfflineSyncPrepAsset(
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

[Obsolete("Use Chummer.Run.Contracts.Relay.OfflineSyncSnapshotRequest.")]
internal sealed record OfflineSyncSnapshotRequest(
    string CampaignId,
    string SessionId,
    string SceneId,
    string ExportedBy,
    string? DeviceId = null,
    IReadOnlyList<string>? PrepAssetIds = null);

[Obsolete("Use Chummer.Run.Contracts.Relay.OfflineSyncSnapshotPackage.")]
internal sealed record OfflineSyncSnapshotPackage(
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

[Obsolete("Use Chummer.Run.Contracts.Relay.OfflineSyncConflict.")]
internal sealed record OfflineSyncConflict(
    string Surface,
    string EntityId,
    string Reason,
    string Resolution,
    string? LocalFingerprint = null,
    string? RemoteFingerprint = null);

[Obsolete("Use Chummer.Run.Contracts.Relay.OfflineSyncSurfaceMergeResult.")]
internal sealed record OfflineSyncSurfaceMergeResult(
    string Surface,
    int ImportedCount,
    int SkippedCount,
    IReadOnlyList<OfflineSyncConflict> Conflicts);

[Obsolete("Use Chummer.Run.Contracts.Relay.OfflineSyncReconcileRequest.")]
internal sealed record OfflineSyncReconcileRequest(
    OfflineSyncSnapshotPackage Snapshot,
    string ReconciledBy,
    string? DeviceId = null,
    IReadOnlyList<SessionEventEnvelope>? LocalPendingEvents = null,
    IReadOnlyList<OfflineSyncPrepAsset>? LocalPrepAssets = null);

[Obsolete("Use Chummer.Run.Contracts.Relay.OfflineSyncReconcileResult.")]
internal sealed record OfflineSyncReconcileResult(
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
