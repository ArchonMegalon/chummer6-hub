using Chummer.Campaign.Contracts;
using Chummer.Control.Contracts.Support;

namespace Chummer.Run.Api.Contracts;

public sealed record CampaignWorkspaceServerPlaneProjection(
    WorkspaceSummary Workspace,
    CampaignWorkspaceSummary CampaignSummary,
    RosterReadinessSummary RosterReadiness,
    IReadOnlyList<CampaignReadinessCue> ReadinessCues,
    IReadOnlyList<WorkspaceChangePacketProjection> ChangePackets,
    IReadOnlyList<DossierFreshnessCue> DossierFreshness,
    IReadOnlyList<RuleEnvironmentHealthCue> RuleEnvironmentHealth,
    RunboardSummary? Runboard,
    IReadOnlyList<ContinuityConflictCue> ContinuityConflicts,
    IReadOnlyList<RecapShelfEntry> RecapShelf,
    IReadOnlyList<SupportClosureCue> SupportClosures,
    IReadOnlyList<KnownIssueAffectingInstall> KnownIssues,
    IReadOnlyList<DecisionNotice> DecisionNotices,
    NextSafeActionCue NextSafeAction,
    DateTimeOffset GeneratedAtUtc);
