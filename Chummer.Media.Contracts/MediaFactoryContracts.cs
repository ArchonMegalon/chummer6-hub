namespace Chummer.Media.Contracts;

public enum AssetStorageClass
{
    ObjectStorage,
    LongTermObjectStorage
}

public enum AssetApprovalState
{
    Draft,
    Approved,
    Rejected
}

public enum AssetRetentionState
{
    CacheOnly,
    ApprovalPending,
    Persisted,
    Pinned,
    Rejected,
    Expired
}

public sealed record AssetLifecyclePolicy(
    TimeSpan CacheTtl,
    bool LongTermCache,
    int MaxBytes,
    bool RequiresApproval = false,
    bool PersistOnApproval = false,
    AssetStorageClass StorageClass = AssetStorageClass.ObjectStorage,
    bool AllowPersistentPinning = true);

public sealed record AssetCatalogItem(
    string AssetId,
    string Url,
    string Category,
    string Version,
    string? Source,
    AssetLifecyclePolicy? Policy,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset? ExpiresAtUtc,
    string? StorageKey = null,
    AssetStorageClass StorageClass = AssetStorageClass.ObjectStorage,
    AssetApprovalState ApprovalState = AssetApprovalState.Draft,
    AssetRetentionState RetentionState = AssetRetentionState.CacheOnly,
    bool IsPinned = false,
    int CacheHitCount = 0,
    DateTimeOffset? LastAccessedAtUtc = null,
    DateTimeOffset? ApprovedAtUtc = null);

public sealed record AssetRenderResult(
    string AssetId,
    string Url,
    AssetLifecyclePolicy? Policy = null,
    AssetApprovalState ApprovalState = AssetApprovalState.Draft,
    AssetRetentionState RetentionState = AssetRetentionState.CacheOnly,
    string? StorageKey = null,
    AssetStorageClass StorageClass = AssetStorageClass.ObjectStorage,
    bool CacheReused = false);

public sealed record AssetLifecycleMutationRequest(
    AssetApprovalState? ApprovalState = null,
    bool? Pin = null,
    bool? Persist = null,
    string? Reason = null);

public sealed record AssetLifecycleSweepResult(
    int ExpiredAssetCount,
    int ActiveAssetCount,
    DateTimeOffset SweptAtUtc);

public enum MediaRenderJobType
{
    PortraitImageVariant,
    NarrativeBriefVideo,
    CinematicPreviewImage,
    CinematicVideo,
    PersonaMessageVideo,
    DocumentPreviewImage,
    DocumentPdf,
    DocumentThumbnailImage
}

public enum MediaRenderJobState
{
    Queued,
    Running,
    Succeeded,
    Failed,
    Expired
}

public sealed record MediaRenderJobEnqueueRequest(
    MediaRenderJobType JobType,
    string DeduplicationKey,
    string Category,
    string Payload,
    string Source,
    TimeSpan? CacheTtl = null,
    int MaxBytes = 0,
    bool RequiresApproval = false,
    bool PersistOnApproval = false,
    bool AllowPersistentPinning = true);

public sealed record MediaRenderJobStatus(
    string JobId,
    MediaRenderJobType JobType,
    MediaRenderJobState State,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset? StartedAtUtc,
    DateTimeOffset? CompletedAtUtc,
    string? AssetId,
    TimeSpan? CacheTtl,
    string? Error);

public enum PacketArtifactRole
{
    Preview,
    Pdf,
    Thumbnail
}

public sealed record PacketArtifactHandle(
    PacketArtifactRole Role,
    string Category,
    string JobId,
    MediaRenderJobState JobState,
    string? AssetId = null,
    TimeSpan? CacheTtl = null);

public enum RouteCinemaArtifactRole
{
    Preview,
    Video
}

public sealed record RouteCinemaArtifactHandle(
    RouteCinemaArtifactRole Role,
    string Category,
    string JobId,
    MediaRenderJobState JobState,
    string? AssetId = null,
    TimeSpan? CacheTtl = null);

public sealed record PacketFactoryRequest(
    string Title,
    string Subject,
    string? SceneId = null,
    IReadOnlyList<string>? References = null,
    IReadOnlyList<PacketAttachmentRequest>? Attachments = null);

public enum PacketAttachmentTargetKind
{
    Campaign,
    Message,
    Export
}

public sealed record PacketAttachmentRequest(
    PacketAttachmentTargetKind TargetKind,
    string TargetId,
    string? TargetLabel = null);

public sealed record PacketAttachmentBatchRequest(
    IReadOnlyList<PacketAttachmentRequest> Attachments);

public sealed record PacketAttachmentRecord(
    string AttachmentId,
    string PacketId,
    PacketAttachmentTargetKind TargetKind,
    string TargetId,
    string? TargetLabel,
    DateTimeOffset AttachedAtUtc,
    IReadOnlyList<PacketArtifactHandle> Artifacts);

public sealed record PacketFactoryResult(
    string PacketId,
    string Title,
    string Subject,
    string Html,
    string? PreviewAssetId,
    string? PdfAssetId = null,
    string? ThumbnailAssetId = null,
    IReadOnlyList<PacketArtifactHandle>? Artifacts = null,
    IReadOnlyList<PacketAttachmentRecord>? Attachments = null,
    IReadOnlyList<string>? Evidence = null);

public sealed record RouteCinemaRequest(
    string CampaignId,
    string SourceNode,
    string TargetNode,
    string SceneContext);

public sealed record RouteCinemaResult(
    string RouteCinemaId,
    string CampaignId,
    string SourceNode,
    string TargetNode,
    string SceneContext,
    IReadOnlyList<string> Waypoints,
    IReadOnlyList<string> WaypointScript,
    string TravelSummary,
    string ProjectionFingerprint,
    AssetApprovalState ApprovalState,
    AssetRetentionState RetentionState,
    string ReviewState,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset? ExpiresAtUtc,
    string? PreviewAssetId,
    string? RouteVideoAssetId,
    string PreviewJobId,
    MediaRenderJobState PreviewJobState,
    string RouteVideoJobId,
    MediaRenderJobState RouteVideoJobState,
    IReadOnlyList<RouteCinemaArtifactHandle> Artifacts,
    TimeSpan? CacheTtl);
