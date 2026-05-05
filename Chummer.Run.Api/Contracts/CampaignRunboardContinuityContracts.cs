namespace Chummer.Run.Api.Contracts;

public sealed record RunboardContinuityUpdateRequest(
    string? RunId,
    string? ActiveSceneId,
    string TurnLedgerSummary,
    IReadOnlyList<string>? TurnLedgerEvidenceLines,
    string RunboardStateSummary,
    IReadOnlyList<string>? ObjectiveLines,
    IReadOnlyList<string>? Blockers,
    string ResolutionReportStatus,
    string ResolutionReportSummary,
    IReadOnlyList<string>? ResolutionNotes,
    string? NextSafeAction = null,
    string? Note = null);
