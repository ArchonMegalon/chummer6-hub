namespace Chummer.Campaign.Contracts;

public sealed record TurnLedgerHandoffProjection(
    string HandoffId,
    string Summary,
    IReadOnlyList<string> EvidenceLines,
    DateTimeOffset UpdatedAtUtc);

public sealed record RunboardStateProjection(
    string StateId,
    string Summary,
    IReadOnlyList<string> ObjectiveLines,
    IReadOnlyList<string> Blockers,
    string NextSafeAction,
    IReadOnlyList<string> EvidenceLines,
    DateTimeOffset UpdatedAtUtc);

public sealed record ResolutionReportDraftProjection(
    string DraftId,
    string Status,
    string Summary,
    IReadOnlyList<string> Notes,
    string NextSafeAction,
    IReadOnlyList<string> EvidenceLines,
    DateTimeOffset UpdatedAtUtc);

public sealed record RunboardContinuityProjection(
    string ContinuityId,
    string WorkspaceId,
    string CampaignId,
    string RunId,
    string RunTitle,
    string? ActiveSceneId,
    string? ActiveSceneTitle,
    TurnLedgerHandoffProjection TurnLedgerHandoff,
    RunboardStateProjection RunboardState,
    ResolutionReportDraftProjection ResolutionReportDraft,
    string Summary,
    IReadOnlyList<string> EvidenceLines,
    string UpdatedByUserId,
    DateTimeOffset UpdatedAtUtc);
