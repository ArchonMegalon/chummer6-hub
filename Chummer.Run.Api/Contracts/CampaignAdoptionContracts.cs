using System.ComponentModel.DataAnnotations;

namespace Chummer.Run.Api.Contracts;

public sealed record CampaignAdoptionWizardRequest(
    IReadOnlyList<string>? RunnerHandles,
    IReadOnlyList<string>? ActiveJobs,
    IReadOnlyList<string>? Contacts,
    IReadOnlyList<string>? HouseRules,
    IReadOnlyList<string>? UnknownHistoryMarkers,
    bool StartLedgerFromToday = true,
    [StringLength(256)] string? Note = null);

public sealed record CampaignAdoptionKnownCountsProjection(
    int Runners,
    int ActiveJobs,
    int Contacts,
    int HouseRules);

public sealed record CampaignAdoptionRecordProjection(
    string AdoptionId,
    string WorkspaceId,
    string CampaignId,
    string CampaignName,
    string Status,
    bool SafeToPlay,
    int ConfidencePercent,
    CampaignAdoptionKnownCountsProjection Known,
    IReadOnlyList<string> UnknownHistoryMarkers,
    IReadOnlyList<string> RecommendedNextActions,
    string Summary,
    string NextBestCleanupAction,
    IReadOnlyList<string> EvidenceLines,
    string InitiatedByUserId,
    DateTimeOffset AdoptedAtUtc);

public sealed record RunnerGoalUpsertRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string DossierId,
    [Required(AllowEmptyStrings = false), StringLength(128)] string GoalTitle,
    [StringLength(32)] string? UpdateKind = null,
    [StringLength(256)] string? Summary = null,
    [StringLength(256)] string? Note = null);

public sealed record CampaignAdoptionRunnerGoalProjection(
    string GoalId,
    string WorkspaceId,
    string CampaignId,
    string DossierId,
    string RunnerHandle,
    string GoalTitle,
    string Status,
    string UpdateKind,
    string Summary,
    IReadOnlyList<string> EvidenceLines,
    string InitiatedByUserId,
    DateTimeOffset UpdatedAtUtc);

public sealed record ResolutionOutcomeDeltaRequest(
    [Required(AllowEmptyStrings = false), StringLength(64)] string Kind,
    [Required(AllowEmptyStrings = false), StringLength(128)] string Subject,
    int Delta,
    [StringLength(256)] string? Summary = null);

public sealed record CampaignAdoptionResolutionReportApprovalRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string DraftPackageId,
    [StringLength(128)] string? RunId = null,
    IReadOnlyList<string>? Outcomes = null,
    int HeatDelta = 0,
    IReadOnlyList<ResolutionOutcomeDeltaRequest>? Deltas = null,
    [StringLength(160)] string? PlayerSafeHeadline = null,
    [StringLength(32)] string? SpoilerLevel = null,
    [StringLength(256)] string? Note = null);

public sealed record WorldChangeProjection(
    string Kind,
    string Subject,
    int Delta,
    string Summary);

public sealed record CampaignAdoptionWorldTickProjection(
    string WorldTickId,
    string WorkspaceId,
    string CampaignId,
    string CampaignName,
    string WorldRef,
    string TickRef,
    string Summary,
    IReadOnlyList<string> CauseRefs,
    IReadOnlyList<WorldChangeProjection> Changes,
    int HeatDelta,
    bool GmApproved,
    string SpoilerPolicy,
    IReadOnlyList<string> EvidenceLines,
    string InitiatedByUserId,
    DateTimeOffset CreatedAtUtc,
    string? WorldFrameId = null,
    string? WorldReceiptRef = null,
    string? ShadowfeedBulletinId = null,
    string? ShadowfeedBulletinReceiptRef = null);

public sealed record PlayerSafeNewsItemProjection(
    string NewsItemId,
    string WorkspaceId,
    string CampaignId,
    string CampaignName,
    string Visibility,
    string Headline,
    string Summary,
    IReadOnlyList<string> SourceRefs,
    string SpoilerLevel,
    IReadOnlyList<string> EvidenceLines,
    string InitiatedByUserId,
    DateTimeOffset PublishedAtUtc,
    string? ShadowfeedBulletinId = null,
    string? ShadowfeedBulletinReceiptRef = null);

public sealed record CampaignAdoptionResolutionReportProjection(
    string ApprovalId,
    string WorkspaceId,
    string CampaignId,
    string CampaignName,
    string DraftPackageId,
    string? RunId,
    string? RunTitle,
    string Status,
    IReadOnlyList<string> Outcomes,
    IReadOnlyList<WorldChangeProjection> Deltas,
    int HeatDelta,
    string Summary,
    IReadOnlyList<string> EvidenceLines,
    string WorldTickId,
    string NewsItemId,
    string InitiatedByUserId,
    DateTimeOffset ApprovedAtUtc,
    string? WorldResolutionReportId = null,
    string? WorldFrameId = null,
    string? ShadowfeedBulletinId = null,
    string? ResolutionConsequenceBridgeId = null,
    string? ApprovalReceiptRef = null);

public sealed record CampaignAdoptionWorkspaceStateProjection(
    string WorkspaceId,
    CampaignAdoptionRecordProjection? CampaignAdoption,
    IReadOnlyList<CampaignAdoptionRunnerGoalProjection> RunnerGoals,
    IReadOnlyList<CampaignAdoptionResolutionReportProjection> ResolutionReports,
    IReadOnlyList<CampaignAdoptionWorldTickProjection> WorldTicks,
    IReadOnlyList<PlayerSafeNewsItemProjection> NewsItems);
