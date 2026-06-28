using System.ComponentModel.DataAnnotations;

namespace Chummer.Run.Api.Contracts;

public sealed record CampaignAdoptionUpdateRequest(
    bool SafeToPlay,
    int ConfidencePercent,
    int RunnerCount,
    int ActiveJobCount,
    int ContactCount,
    int HouseRuleCount,
    [property: MaxLength(8)] IReadOnlyList<string>? ExplicitUnknowns,
    [property: MaxLength(8)] IReadOnlyList<string>? RecommendedNextActions,
    [property: Required(AllowEmptyStrings = false), StringLength(4000)] string Summary,
    [property: StringLength(1024)] string? NextSafeAction = null,
    [property: StringLength(1024)] string? Note = null);

public sealed record RunnerGoalUpdateRequest(
    [property: Required(AllowEmptyStrings = false), StringLength(128)] string DossierId,
    [property: Required(AllowEmptyStrings = false), StringLength(160)] string Label,
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string TargetKind,
    [property: Required(AllowEmptyStrings = false), StringLength(256)] string TargetReference,
    int SavedNuyen,
    int NuyenRequired,
    int KarmaReserved,
    int DowntimeDays,
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string ApprovalStatus,
    [property: StringLength(1024)] string? NextSafeAction = null,
    [property: StringLength(1024)] string? Note = null);

public sealed record ResolutionReportApprovalRequest(
    [property: StringLength(128)] string? RunId,
    [property: Required(AllowEmptyStrings = false), StringLength(4000)] string Summary,
    [property: Required(AllowEmptyStrings = false), StringLength(4000)] string WorldTickSummary,
    [property: Required(AllowEmptyStrings = false), StringLength(4000)] string ConsequenceSummary,
    [property: Required(AllowEmptyStrings = false), StringLength(160)] string NewsTitle,
    [property: Required(AllowEmptyStrings = false), StringLength(4000)] string NewsSummary,
    [property: StringLength(160)] string? NewsSource = null,
    [property: StringLength(2048)] string? NewsUrl = null,
    [property: StringLength(1024)] string? NextSafeAction = null,
    [property: StringLength(1024)] string? Note = null);
