using Chummer.Contracts.Rulesets;

namespace Chummer.Contracts.AI;

public sealed record BuildIdeaCard(
    string IdeaId,
    string RulesetId,
    string Title,
    string Summary,
    IReadOnlyList<string> RoleTags,
    IReadOnlyList<string> CompatibleProfileIds,
    string CoreLoop,
    IReadOnlyList<string> EarlyPriorities,
    IReadOnlyList<string> KarmaMilestones,
    IReadOnlyList<string> Strengths,
    IReadOnlyList<string> Weaknesses,
    IReadOnlyList<string> TrapChoices,
    IReadOnlyList<string> LinkedContentIds,
    double CommunityScore = 0,
    string Provenance = "build-idea-card",
    string? TitleKey = null,
    IReadOnlyList<RulesetExplainParameter>? TitleParameters = null,
    string? SummaryKey = null,
    IReadOnlyList<RulesetExplainParameter>? SummaryParameters = null,
    string? CoreLoopKey = null,
    IReadOnlyList<RulesetExplainParameter>? CoreLoopParameters = null);
