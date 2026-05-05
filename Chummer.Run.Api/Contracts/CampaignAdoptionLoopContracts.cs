namespace Chummer.Run.Api.Contracts;

public sealed record CampaignAdoptionUpdateRequest(
    bool SafeToPlay,
    int ConfidencePercent,
    int RunnerCount,
    int ActiveJobCount,
    int ContactCount,
    int HouseRuleCount,
    IReadOnlyList<string>? ExplicitUnknowns,
    IReadOnlyList<string>? RecommendedNextActions,
    string Summary,
    string? NextSafeAction = null,
    string? Note = null);

public sealed record RunnerGoalUpdateRequest(
    string DossierId,
    string Label,
    string TargetKind,
    string TargetReference,
    int SavedNuyen,
    int NuyenRequired,
    int KarmaReserved,
    int DowntimeDays,
    string ApprovalStatus,
    string? NextSafeAction = null,
    string? Note = null);

public sealed record ResolutionReportApprovalRequest(
    string? RunId,
    string Summary,
    string WorldTickSummary,
    string ConsequenceSummary,
    string NewsTitle,
    string NewsSummary,
    string? NewsSource = null,
    string? NewsUrl = null,
    string? NextSafeAction = null,
    string? Note = null);
