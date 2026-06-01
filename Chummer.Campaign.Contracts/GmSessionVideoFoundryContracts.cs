namespace Chummer.Campaign.Contracts;

public sealed record GmSessionVideoFoundryHomeProjection(
    string CampaignId,
    string ProviderAccountRole,
    string ProviderAccountStatus,
    string QueueIsolationStatus,
    IReadOnlyList<string> Routes,
    IReadOnlyList<PromptDraftProjection> PromptDrafts,
    IReadOnlyList<SessionVideoRenderJobProjection> RenderJobs,
    GmVideoUsageSummaryProjection Usage);

public sealed record FaceAssetProjection(
    string Id,
    string OwnerGmUserId,
    string OwnerWorkspaceId,
    string? CampaignId,
    string DisplayName,
    string Metatype,
    IReadOnlyList<string> RoleTags,
    string SourceType,
    string VisibilityScope,
    IReadOnlyList<string> AllowedUserIds,
    string ConsentState,
    bool PublicShareAllowed,
    string StorageObjectId,
    string ThumbnailObjectId,
    string? ProviderReferenceIdEncrypted,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc);

public sealed record CreateFaceAssetRequest(
    string DisplayName,
    string Metatype = "unknown",
    IReadOnlyList<string>? RoleTags = null,
    string SourceType = "ai_generated",
    string VisibilityScope = "private_gm",
    IReadOnlyList<string>? AllowedUserIds = null,
    string ConsentState = "not_required",
    bool PublicShareAllowed = false);

public sealed record PromptDraftProjection(
    string Id,
    string CampaignId,
    string? SessionId,
    string GmUserId,
    string VideoType,
    string Audience,
    string SpoilerLevel,
    string Tone,
    IReadOnlyList<string> SelectedFaceAssetIds,
    IReadOnlyList<string> AllowedFacts,
    IReadOnlyList<string> ForbiddenFacts,
    string GeneratedPrompt,
    string NegativePrompt,
    IReadOnlyDictionary<string, string> ProviderSettings,
    GmVideoUsageEstimateProjection EstimatedUsage,
    IReadOnlyList<string> PrivacyWarnings,
    string PrivacyScanStatus,
    string Status,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset? ApprovedAtUtc);

public sealed record CreatePromptDraftRequest(
    string VideoType,
    string Audience,
    string SpoilerLevel,
    string Tone,
    IReadOnlyList<string>? SelectedFaceAssetIds = null,
    IReadOnlyList<string>? AllowedFacts = null,
    IReadOnlyList<string>? ForbiddenFacts = null,
    int DurationSeconds = 30,
    string AspectRatio = "16:9");

public sealed record EditPromptDraftRequest(
    string GeneratedPrompt,
    string NegativePrompt,
    string? Tone = null);

public sealed record ApprovePromptDraftRequest(
    bool Approved,
    string ApprovalNote = "");

public sealed record PromptVersionProjection(
    string PromptDraftId,
    int VersionNumber,
    string EditorUserId,
    string PromptTextHash,
    string NegativePromptHash,
    string PrivacyScanStatus,
    GmVideoUsageEstimateProjection UsageEstimate,
    DateTimeOffset CreatedAtUtc);

public sealed record GmVideoUsageEstimateProjection(
    int RenderUnits,
    string DurationPreset,
    string QueueSlot,
    int GmMonthlyRemaining,
    int CampaignMonthlyRemaining,
    int GroupMonthlyRemaining);

public sealed record SessionVideoRenderJobProjection(
    string Id,
    string PromptDraftId,
    string CampaignId,
    string? SessionId,
    string GmUserId,
    string GroupId,
    string ProviderAccountId,
    string Origin,
    string VideoType,
    string Audience,
    string Status,
    int RenderUnitsEstimated,
    int RenderUnitsReserved,
    int RenderUnitsConsumed,
    string? ProviderJobId,
    IReadOnlyList<string> AssetIds,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc);

public sealed record RenderUsageLedgerEntryProjection(
    string Id,
    string GmUserId,
    string GroupId,
    string CampaignId,
    string? RenderJobId,
    string ProviderAccountId,
    string EventType,
    int Units,
    string Reason,
    DateTimeOffset CreatedAtUtc,
    string CreatedBy);

public sealed record GmVideoUsageSummaryProjection(
    string GmUserId,
    string GroupId,
    string CampaignId,
    int GmMonthlyLimit,
    int GroupMonthlyLimit,
    int CampaignMonthlyLimit,
    int GmMonthlyConsumed,
    int GroupMonthlyConsumed,
    int CampaignMonthlyConsumed,
    int GmMonthlyReserved,
    int GroupMonthlyReserved,
    int CampaignMonthlyReserved);

public sealed record TablePulseMediaPacketProjection(
    string CampaignId,
    string GmUserId,
    string? SessionId,
    string Audience,
    string VideoType,
    IReadOnlyList<string> AllowedFacts,
    IReadOnlyList<string> ForbiddenFacts,
    string HeatSummary,
    string FactionSummary,
    string LocationAlias,
    IReadOnlyList<string> CastAssetIds,
    string Tone,
    string SpoilerLevel,
    string PrivacyScanStatus);
