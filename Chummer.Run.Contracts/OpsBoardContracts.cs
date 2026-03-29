using System.ComponentModel.DataAnnotations;
using Chummer.Contracts.Hub;
using Chummer.Play.Contracts.Spider;

namespace Chummer.Run.Contracts.Ops;

public enum GmPrepAssetKind
{
    Note,
    Checklist,
    RevealSurface,
    PlayerScreen
}

public enum GmPrepAssetAudience
{
    GameMaster,
    Players,
    Shared
}

public sealed record OpsBoardProjection(
    string SessionId,
    string SceneId,
    string SceneRevision,
    string ProjectionFingerprint,
    int LedgerVersion,
    DateTimeOffset GeneratedAtUtc,
    IReadOnlyList<OpsBoardRecentEvent> RecentEvents,
    IReadOnlyList<OpsBoardUnresolvedItem> UnresolvedItems,
    IReadOnlyList<OpsBoardTacticalCardSummary> TacticalCards,
    IReadOnlyList<GmPrepAssetSummary> PrepAssets,
    IReadOnlyList<OpsBoardRevealSurface> RevealSurfaces,
    OpsBoardChecklistSummary ChecklistSummary);

public sealed record OpsBoardRecentEvent(
    string EventId,
    string EventType,
    string Payload,
    DateTimeOffset AtUtc,
    string? SceneRevision = null);

public sealed record OpsBoardUnresolvedItem(
    string ItemId,
    string Summary,
    string Severity,
    IReadOnlyList<EvidencePointer> Evidence);

public sealed record OpsBoardTacticalCardSummary(
    string MessageId,
    string Channel,
    string ApprovalState,
    string AutonomyMode,
    string? CardKind,
    string Title,
    string Summary,
    DateTimeOffset EnqueuedAtUtc,
    DateTimeOffset? HiddenUntilUtc = null);

public sealed record OpsBoardRevealSurface(
    string AssetId,
    string Title,
    GmPrepAssetKind Kind,
    GmPrepAssetAudience Audience,
    string Status,
    string? LastChannel,
    DateTimeOffset? LastRevealedAtUtc,
    int RevealCount);

public sealed record OpsBoardChecklistSummary(
    int TotalItems,
    int CompletedItems,
    int OpenItems);

public sealed record GmPrepChecklistItem(
    string ItemId,
    [Required(AllowEmptyStrings = false), StringLength(240)] string Label,
    bool Completed = false,
    string? Notes = null);

public sealed record GmPrepAssetCreateRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string CampaignId,
    [StringLength(128)] string? SessionId,
    [StringLength(128)] string? SceneId,
    [Required(AllowEmptyStrings = false), StringLength(160)] string Title,
    GmPrepAssetKind Kind,
    GmPrepAssetAudience Audience,
    string? Summary,
    [Required(AllowEmptyStrings = false)] string Body,
    IReadOnlyList<string>? Tags = null,
    IReadOnlyList<GmPrepChecklistItem>? ChecklistItems = null,
    IReadOnlyList<string>? SourceEventIds = null,
    bool Reusable = true,
    string? CreatedBy = null,
    string? RuntimeFingerprint = null);

public sealed record GmPrepAssetGovernedProjectReference(
    string ProjectKind,
    string ProjectId,
    string Title,
    string RulesetId,
    string LinkTarget,
    string TrustTier,
    string? RuntimeFingerprint = null);

public sealed record GmPrepAssetCatalogImportRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string CampaignId,
    [StringLength(128)] string? SessionId,
    [StringLength(128)] string? SceneId,
    [Required] HubProjectDetailProjection Project,
    GmPrepAssetAudience Audience = GmPrepAssetAudience.GameMaster,
    bool Reusable = true,
    IReadOnlyList<string>? AdditionalTags = null,
    string? CreatedBy = null,
    string? RuntimeFingerprint = null);

public sealed record GmPrepAssetRecord(
    string AssetId,
    string CampaignId,
    string? SessionId,
    string? SceneId,
    string Title,
    GmPrepAssetKind Kind,
    GmPrepAssetAudience Audience,
    string? Summary,
    string Body,
    IReadOnlyList<string> Tags,
    IReadOnlyList<GmPrepChecklistItem> ChecklistItems,
    IReadOnlyList<EvidencePointer> Evidence,
    bool Reusable,
    string Status,
    string? CreatedBy,
    string? RuntimeFingerprint,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? LastRevealedAtUtc = null,
    string? LastRevealChannel = null,
    int RevealCount = 0,
    GmPrepAssetGovernedProjectReference? GovernedProject = null);

public sealed record GmPrepAssetSummary(
    string AssetId,
    string CampaignId,
    string? SessionId,
    string? SceneId,
    string Title,
    GmPrepAssetKind Kind,
    GmPrepAssetAudience Audience,
    string Status,
    IReadOnlyList<string> Tags,
    bool Reusable,
    int ChecklistItemCount,
    int ChecklistCompletedCount,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? LastRevealedAtUtc = null,
    GmPrepAssetGovernedProjectReference? GovernedProject = null);

public sealed record GmPrepAssetListResponse(
    IReadOnlyList<GmPrepAssetSummary> Items,
    int TotalCount);

public sealed record GmPrepChecklistUpdateRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string UpdatedBy,
    IReadOnlyList<GmPrepChecklistItem> ChecklistItems,
    string? Notes = null);

public sealed record GmPrepAssetRevealRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SessionId,
    [Required(AllowEmptyStrings = false), StringLength(128)] string SceneId,
    [Required(AllowEmptyStrings = false), StringLength(128)] string SceneRevision,
    [Required(AllowEmptyStrings = false), StringLength(128)] string RequestedBy,
    string Channel = "player-screen",
    string ApprovalState = "approved",
    string AutonomyMode = "gm-approved",
    bool Archive = false,
    string? Notes = null);

public sealed record GmPrepAssetRevealResult(
    string AssetId,
    string Outcome,
    string ApprovalState,
    string Status,
    string? MessageId,
    string? Channel,
    DateTimeOffset ProcessedAtUtc,
    DeliveryOutboxMessage? Message = null);
