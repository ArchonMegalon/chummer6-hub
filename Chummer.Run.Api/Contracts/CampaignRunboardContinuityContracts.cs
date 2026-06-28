using System.ComponentModel.DataAnnotations;

namespace Chummer.Run.Api.Contracts;

public sealed record RunboardContinuityUpdateRequest(
    [property: StringLength(128)] string? RunId,
    [property: StringLength(128)] string? ActiveSceneId,
    [property: Required(AllowEmptyStrings = false), StringLength(4000)] string TurnLedgerSummary,
    [property: MaxLength(8)] IReadOnlyList<string>? TurnLedgerEvidenceLines,
    [property: Required(AllowEmptyStrings = false), StringLength(4000)] string RunboardStateSummary,
    [property: MaxLength(8)] IReadOnlyList<string>? ObjectiveLines,
    [property: MaxLength(8)] IReadOnlyList<string>? Blockers,
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string ResolutionReportStatus,
    [property: Required(AllowEmptyStrings = false), StringLength(4000)] string ResolutionReportSummary,
    [property: MaxLength(8)] IReadOnlyList<string>? ResolutionNotes,
    [property: StringLength(1024)] string? NextSafeAction = null,
    [property: StringLength(1024)] string? Note = null);
