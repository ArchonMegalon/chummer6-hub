using Chummer.Media.Contracts;
using Chummer.Run.Contracts.Media;

namespace Chummer.Run.AI.Compatibility;

[Obsolete("Use Chummer.Run.Contracts.Media.PortraitForgeRequest.")]
internal sealed record PortraitForgeRequest(
    string EntityId,
    string Style,
    string? Notes = null,
    bool AllowUnderscover = false,
    string? RerollOfPortraitId = null);

[Obsolete("Use Chummer.Run.Contracts.Media.PortraitVariant.")]
internal sealed record PortraitVariant(
    string Variant,
    string JobId,
    string? AssetId,
    string PromptLineage,
    string? StyleToken = null,
    AssetApprovalState ApprovalState = AssetApprovalState.Pending,
    AssetRetentionState RetentionState = AssetRetentionState.ApprovalPending,
    bool IsCanonical = false);

[Obsolete("Use Chummer.Run.Contracts.Media.PortraitReviewRecord.")]
internal sealed record PortraitReviewRecord(
    string Action,
    string Variant,
    string? AssetId,
    string Actor,
    DateTimeOffset AtUtc,
    string? Notes = null,
    string? PreviousCanonicalPortraitId = null,
    string? ResultingCanonicalPortraitId = null);

[Obsolete("Use Chummer.Run.Contracts.Media.PortraitApprovalRequest.")]
internal sealed record PortraitApprovalRequest(
    string Variant,
    string ApprovedBy,
    string? Notes = null,
    bool PinCanonical = true);

[Obsolete("Use Chummer.Run.Contracts.Media.PortraitForgeResult.")]
internal sealed record PortraitForgeResult(
    string PortraitDraftId,
    string PortraitIdentityId,
    string EntityId,
    string? CanonicalPortraitId,
    string DraftState,
    IReadOnlyList<PortraitVariant> Variants,
    TimeSpan? CacheTtl,
    double Confidence,
    DateTimeOffset CreatedAtUtc,
    string? RerollOfPortraitId = null,
    string? RerollRootPortraitId = null,
    int RerollDepth = 0,
    IReadOnlyList<PortraitReviewRecord>? ReviewHistory = null);

[Obsolete("Use Chummer.Media.Contracts.AssetStorageClass.")]
internal enum AssetStorageClass
{
    ObjectStorage,
    LongTermObjectStorage
}

[Obsolete("Use Chummer.Media.Contracts.AssetApprovalState.")]
internal enum AssetApprovalState
{
    Pending,
    Approved,
    Rejected
}

[Obsolete("Use Chummer.Media.Contracts.AssetRetentionState.")]
internal enum AssetRetentionState
{
    CacheOnly,
    ApprovalPending,
    Persisted,
    Pinned,
    Rejected,
    Expired
}

[Obsolete("Use Chummer.Media.Contracts.AssetLifecyclePolicy.")]
internal sealed record AssetLifecyclePolicy(
    TimeSpan CacheTtl,
    bool LongTermCache,
    int MaxBytes,
    bool RequiresApproval = false,
    bool PersistOnApproval = false,
    AssetStorageClass StorageClass = AssetStorageClass.ObjectStorage,
    bool AllowPersistentPinning = true);

[Obsolete("Use Chummer.Media.Contracts.AssetCatalogItem.")]
internal sealed record AssetCatalogItem(
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
    AssetApprovalState ApprovalState = AssetApprovalState.Pending,
    AssetRetentionState RetentionState = AssetRetentionState.CacheOnly,
    bool IsPinned = false,
    int CacheHitCount = 0,
    DateTimeOffset? LastAccessedAtUtc = null,
    DateTimeOffset? ApprovedAtUtc = null);

[Obsolete("Use Chummer.Media.Contracts.AssetRenderResult.")]
internal sealed record AssetRenderResult(
    string AssetId,
    string Url,
    AssetLifecyclePolicy? Policy = null,
    AssetApprovalState ApprovalState = AssetApprovalState.Pending,
    AssetRetentionState RetentionState = AssetRetentionState.CacheOnly,
    string? StorageKey = null,
    AssetStorageClass StorageClass = AssetStorageClass.ObjectStorage,
    bool CacheReused = false);

[Obsolete("Use Chummer.Media.Contracts.AssetLifecycleMutationRequest.")]
internal sealed record AssetLifecycleMutationRequest(
    AssetApprovalState? ApprovalState = null,
    bool? Pin = null,
    bool? Persist = null,
    string? Reason = null);

[Obsolete("Use Chummer.Media.Contracts.AssetLifecycleSweepResult.")]
internal sealed record AssetLifecycleSweepResult(
    int ExpiredAssetCount,
    int ActiveAssetCount,
    DateTimeOffset SweptAtUtc);

[Obsolete("Use Chummer.Media.Contracts.MediaRenderJobType.")]
internal enum MediaRenderJobType
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

[Obsolete("Use Chummer.Media.Contracts.MediaRenderJobState.")]
internal enum MediaRenderJobState
{
    Queued,
    Running,
    Succeeded,
    Failed,
    Expired
}

[Obsolete("Use Chummer.Media.Contracts.MediaRenderJobEnqueueRequest.")]
internal sealed record MediaRenderJobEnqueueRequest(
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

[Obsolete("Use Chummer.Media.Contracts.MediaRenderJobStatus.")]
internal sealed record MediaRenderJobStatus(
    string JobId,
    MediaRenderJobType JobType,
    MediaRenderJobState State,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset? StartedAtUtc,
    DateTimeOffset? CompletedAtUtc,
    string? AssetId,
    TimeSpan? CacheTtl,
    string? Error);

[Obsolete("Use Chummer.Media.Contracts.PacketFactoryRequest.")]
internal sealed record PacketFactoryRequest(
    string Title,
    string Subject,
    IReadOnlyList<string>? References = null,
    IReadOnlyList<PacketAttachmentRequest>? Attachments = null);

[Obsolete("Use Chummer.Media.Contracts.PacketArtifactRole.")]
internal enum PacketArtifactRole
{
    Preview,
    Pdf,
    Thumbnail
}

[Obsolete("Use Chummer.Media.Contracts.PacketAttachmentTargetKind.")]
internal enum PacketAttachmentTargetKind
{
    Route,
    Message,
    Export
}

[Obsolete("Use Chummer.Media.Contracts.PacketArtifactHandle.")]
internal sealed record PacketArtifactHandle(
    PacketArtifactRole Role,
    string Category,
    string JobId,
    MediaRenderJobState JobState,
    string? AssetId = null,
    TimeSpan? CacheTtl = null);

[Obsolete("Use Chummer.Media.Contracts.PacketAttachmentRequest.")]
internal sealed record PacketAttachmentRequest(
    PacketAttachmentTargetKind TargetKind,
    string TargetId,
    string? TargetLabel = null);

[Obsolete("Use Chummer.Media.Contracts.PacketAttachmentBatchRequest.")]
internal sealed record PacketAttachmentBatchRequest(
    IReadOnlyList<PacketAttachmentRequest> Attachments);

[Obsolete("Use Chummer.Media.Contracts.PacketAttachmentRecord.")]
internal sealed record PacketAttachmentRecord(
    string AttachmentId,
    string PacketId,
    PacketAttachmentTargetKind TargetKind,
    string TargetId,
    string? TargetLabel,
    DateTimeOffset AttachedAtUtc,
    IReadOnlyList<PacketArtifactHandle> Artifacts);

[Obsolete("Use Chummer.Media.Contracts.PacketFactoryResult.")]
internal sealed record PacketFactoryResult(
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

[Obsolete("Use Chummer.Media.Contracts.RouteCinemaRequest.")]
internal sealed record RouteCinemaRequest(
    string SourceNode,
    string TargetNode);

[Obsolete("Use Chummer.Media.Contracts.RouteCinemaArtifactRole.")]
internal enum RouteCinemaArtifactRole
{
    Preview,
    Video
}

[Obsolete("Use Chummer.Media.Contracts.RouteCinemaArtifactHandle.")]
internal sealed record RouteCinemaArtifactHandle(
    RouteCinemaArtifactRole Role,
    string Category,
    string JobId,
    MediaRenderJobState JobState,
    string? AssetId = null,
    TimeSpan? CacheTtl = null);

[Obsolete("Use Chummer.Media.Contracts.RouteCinemaResult.")]
internal sealed record RouteCinemaResult(
    string RouteCinemaId,
    string SourceNode,
    string TargetNode,
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

[Obsolete("Use Chummer.Run.Contracts.Media.NewsItem.")]
internal sealed record NewsItem(
    string Title,
    string Source,
    string Summary,
    string Url);

[Obsolete("Use Chummer.Run.Contracts.Media.NewsFact.")]
internal sealed record NewsFact(
    string FactId,
    string Category,
    string Summary,
    IReadOnlyList<SessionMemoryEvidence> Evidence);

[Obsolete("Use Chummer.Run.Contracts.Media.NewsBriefRequest.")]
internal sealed record NewsBriefRequest(
    string CampaignId,
    string? SessionId = null,
    string? SceneId = null,
    string? SceneRevision = null,
    string? Transcript = null,
    string? Notes = null,
    IReadOnlyList<string>? ApprovedNotes = null,
    IReadOnlyList<string>? PlayerMessages = null,
    IReadOnlyList<NewsItem>? SeedItems = null,
    bool IncludeVideo = true);

[Obsolete("Use Chummer.Run.Contracts.Media.NewsBriefResult.")]
internal sealed record NewsBriefResult(
    string NewsBriefId,
    string CampaignId,
    string? SessionId,
    string? SceneId,
    string? SceneRevision,
    string ShortRecap,
    string LongRecap,
    string InUniverseBulletin,
    string FalloutSummary,
    IReadOnlyList<NewsFact> Facts,
    string RecapAssetId,
    AssetApprovalState ApprovalState,
    AssetRetentionState RetentionState,
    string ProjectionFingerprint,
    string DeliveryState,
    IReadOnlyList<string> DeliveryMessageIds,
    DateTimeOffset GeneratedAtUtc,
    string? VideoAssetId = null,
    string? VideoJobId = null,
    MediaRenderJobState? VideoJobState = null);

[Obsolete("Use Chummer.Run.Contracts.Media.NewsBriefDeliveryRequest.")]
internal sealed record NewsBriefDeliveryRequest(
    string SessionId,
    string SceneId,
    string SceneRevision,
    string RequestedBy,
    string Channel = "players",
    bool Archive = true,
    string? ApprovalState = null,
    string? Notes = null);

[Obsolete("Use Chummer.Run.Contracts.Media.NewsBriefDeliveryResult.")]
internal sealed record NewsBriefDeliveryResult(
    string NewsBriefId,
    string Outcome,
    string ApprovalState,
    string DeliveryState,
    IReadOnlyList<DeliveryOutboxMessage> Messages);

[Obsolete("Use Chummer.Run.Contracts.Media.ShadowfeedRequest.")]
internal sealed record ShadowfeedRequest(
    string CampaignId,
    string SceneId,
    string? Region,
    string? District,
    IReadOnlyList<string>? Hooks = null,
    string? PersonaStyle = null);

[Obsolete("Use Chummer.Run.Contracts.Media.ShadowfeedResult.")]
internal sealed record ShadowfeedResult(
    string CampaignId,
    string SceneId,
    string Region,
    string District,
    IReadOnlyList<string> Headline,
    IReadOnlyList<string> RumorFeed,
    IReadOnlyList<string> PoliceChatter,
    IReadOnlyList<string> MatrixPosts,
    string? ApprovedPayloadAssetId);

[Obsolete("Use Chummer.Run.Contracts.Media.NpcVideoMessageRequest.")]
internal sealed record NpcVideoMessageRequest(
    string SessionId,
    string SceneId,
    string NpcId,
    string MessageText,
    string? Style = null);

[Obsolete("Use Chummer.Run.Contracts.Media.NpcVideoMessageResult.")]
internal sealed record NpcVideoMessageResult(
    string MessageId,
    string SessionId,
    string SceneId,
    string NpcId,
    string? VideoAssetId,
    string VideoJobId,
    MediaRenderJobState VideoJobState,
    string Script,
    double Confidence,
    TimeSpan? CacheTtl,
    AssetApprovalState ApprovalState,
    AssetRetentionState RetentionState,
    string PublishState,
    IReadOnlyList<string> PublishedMessageIds,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset? ExpiresAtUtc);

[Obsolete("Use Chummer.Run.Contracts.Media.NpcVideoMessagePublishRequest.")]
internal sealed record NpcVideoMessagePublishRequest(
    string SessionId,
    string SceneId,
    string SceneRevision,
    string RequestedBy,
    IReadOnlyList<string>? Surfaces = null,
    bool Archive = true,
    string? ApprovalState = null,
    string? Notes = null);

[Obsolete("Use Chummer.Run.Contracts.Media.NpcVideoMessagePublishResult.")]
internal sealed record NpcVideoMessagePublishResult(
    string MessageId,
    string Outcome,
    string ApprovalState,
    string PublishState,
    IReadOnlyList<DeliveryOutboxMessage> Messages);
