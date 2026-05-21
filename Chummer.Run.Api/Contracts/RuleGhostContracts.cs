using System.ComponentModel.DataAnnotations;

namespace Chummer.Run.Api.Contracts;

public sealed record RuleGhostAskRequest(
    [Required(AllowEmptyStrings = false), StringLength(2000)] string Query,
    [StringLength(16)] string? PreferredRuleset = null);

public sealed record RuleGhostCitation(
    string SourceLabel,
    string SectionHint,
    string Summary);

public sealed record RuleGhostResponse(
    string Answer,
    string Confidence,
    string RulesetId,
    bool ClarificationNeeded,
    bool Refused,
    IReadOnlyList<RuleGhostCitation> Citations,
    IReadOnlyList<string> SafeFollowUps);
