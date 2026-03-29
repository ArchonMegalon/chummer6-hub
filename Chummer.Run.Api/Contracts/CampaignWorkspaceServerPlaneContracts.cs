using Chummer.Campaign.Contracts;
using Chummer.Control.Contracts.Support;

namespace Chummer.Run.Api.Contracts;

public sealed record CampaignWorkspaceServerPlaneProjection(
    WorkspaceSummary Workspace,
    CampaignWorkspaceSummary CampaignSummary,
    WorkspaceStateSummary WorkspaceState,
    RosterReadinessSummary RosterReadiness,
    IReadOnlyList<CampaignReadinessCue> ReadinessCues,
    IReadOnlyList<WorkspaceChangePacketProjection> ChangePackets,
    IReadOnlyList<CampaignConsequenceProjection> Consequences,
    IReadOnlyList<RosterTransferProjection> RosterTransfers,
    IReadOnlyList<DossierFreshnessCue> DossierFreshness,
    IReadOnlyList<RuleEnvironmentHealthCue> RuleEnvironmentHealth,
    RunboardSummary? Runboard,
    IReadOnlyList<ContinuityConflictCue> ContinuityConflicts,
    IReadOnlyList<RecapShelfEntry> RecapShelf,
    IReadOnlyList<SupportClosureCue> SupportClosures,
    IReadOnlyList<KnownIssueAffectingInstall> KnownIssues,
    IReadOnlyList<DecisionNotice> DecisionNotices,
    CampaignPrepLibrarySummary PrepLibrary,
    IReadOnlyList<GovernedPrepLaunchProjection> PrepLaunches,
    TravelModeReadinessSummary TravelMode,
    IReadOnlyList<TravelPrefetchReceiptProjection> TravelPrefetches,
    IReadOnlyList<AftermathRecapPackageProjection> AftermathPackages,
    CampaignMemoryProjection? CampaignMemory,
    NextSessionCarryForwardProjection? NextSessionCarryForward,
    NextSafeActionCue NextSafeAction,
    DateTimeOffset GeneratedAtUtc);

public sealed record WorkspaceStateSummary(
    string Status,
    string Label,
    string Summary,
    IReadOnlyList<string> EvidenceLines);

public sealed record CampaignPrepLibrarySummary(
    string Summary,
    string BindingSummary,
    string SearchSummary,
    int ReusablePacketCount,
    int SearchablePacketCount,
    IReadOnlyList<GovernedPrepPacketSummary> Packets);

public sealed record GovernedPrepPacketSummary(
    string PacketId,
    string Kind,
    string Title,
    string Summary,
    string BindingSummary,
    bool Reusable,
    IReadOnlyList<string> SearchTerms,
    IReadOnlyList<string> EvidenceLines,
    DateTimeOffset UpdatedAtUtc);

public sealed record CampaignPrepLibrarySearchResponse(
    string WorkspaceId,
    string CampaignId,
    string? QueryText,
    IReadOnlyList<GovernedPrepPacketSummary> Items,
    int TotalCount);

public sealed record TravelModeReadinessSummary(
    string Status,
    string Summary,
    string PrefetchInventorySummary,
    int ClaimedDeviceCount,
    int TravelReadyDeviceCount,
    IReadOnlyList<TravelModeDeviceReadinessCue> Devices,
    IReadOnlyList<string> Boundaries);

public sealed record TravelModeDeviceReadinessCue(
    string InstallationId,
    string DeviceRole,
    string Platform,
    string HeadId,
    string Channel,
    string Status,
    string Summary);
