using Chummer.Play.Contracts.Memory;
using Chummer.Play.Contracts.Spider;
using Chummer.Media.Contracts;

namespace Chummer.Run.Contracts.Media;

public sealed record PortraitForgeRequest(
    string EntityId,
    string Style,
    string? Notes = null,
    bool AllowUnderscover = false,
    string? RerollOfPortraitId = null);

public sealed record PortraitVariant(
    string Variant,
    string JobId,
    string? AssetId,
    string PromptLineage,
    string? StyleToken = null,
    AssetApprovalState ApprovalState = AssetApprovalState.Pending,
    AssetRetentionState RetentionState = AssetRetentionState.ApprovalPending,
    bool IsCanonical = false);

public sealed record PortraitReviewRecord(
    string Action,
    string Variant,
    string? AssetId,
    string Actor,
    DateTimeOffset AtUtc,
    string? Notes = null,
    string? PreviousCanonicalPortraitId = null,
    string? ResultingCanonicalPortraitId = null);

public sealed record PortraitApprovalRequest(
    string Variant,
    string ApprovedBy,
    string? Notes = null,
    bool PinCanonical = true);

public sealed record PortraitForgeResult(
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

public sealed record NewsItem(
    string Title,
    string Source,
    string Summary,
    string Url);

public sealed record NewsFact(
    string FactId,
    string Category,
    string Summary,
    IReadOnlyList<SessionMemoryEvidence> Evidence);

public sealed record NewsBriefRequest(
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

public sealed record NewsBriefResult(
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

public sealed record NewsBriefDeliveryRequest(
    string SessionId,
    string SceneId,
    string SceneRevision,
    string RequestedBy,
    string Channel = "players",
    bool Archive = true,
    string? ApprovalState = null,
    string? Notes = null);

public sealed record NewsBriefDeliveryResult(
    string NewsBriefId,
    string Outcome,
    string ApprovalState,
    string DeliveryState,
    IReadOnlyList<DeliveryOutboxMessage> Messages);

public sealed record ShadowfeedRequest(
    string CampaignId,
    string SceneId,
    string? Region,
    string? District,
    IReadOnlyList<string>? Hooks = null,
    string? PersonaStyle = null);

public sealed record ShadowfeedResult(
    string CampaignId,
    string SceneId,
    string Region,
    string District,
    IReadOnlyList<string> Headline,
    IReadOnlyList<string> RumorFeed,
    IReadOnlyList<string> PoliceChatter,
    IReadOnlyList<string> MatrixPosts,
    string? ApprovedPayloadAssetId);

public sealed record NpcVideoMessageRequest(
    string SessionId,
    string SceneId,
    string NpcId,
    string MessageText,
    string? Style = null);

public sealed record NpcVideoMessageResult(
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

public sealed record NpcVideoMessagePublishRequest(
    string SessionId,
    string SceneId,
    string SceneRevision,
    string RequestedBy,
    IReadOnlyList<string>? Surfaces = null,
    bool Archive = true,
    string? ApprovalState = null,
    string? Notes = null);

public sealed record NpcVideoMessagePublishResult(
    string MessageId,
    string Outcome,
    string ApprovalState,
    string PublishState,
    IReadOnlyList<DeliveryOutboxMessage> Messages);
