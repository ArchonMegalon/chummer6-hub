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
    GmOperationsReadinessSummary GmOperations,
    CampaignPrepLibrarySummary PrepLibrary,
    IReadOnlyList<GovernedPrepLaunchProjection> PrepLaunches,
    TravelModeReadinessSummary TravelMode,
    IReadOnlyList<TravelPrefetchReceiptProjection> TravelPrefetches,
    IReadOnlyList<AftermathRecapPackageProjection> AftermathPackages,
    FirstPlayableSessionProjection? FirstPlayableSession,
    CampaignMemoryProjection? CampaignMemory,
    NextSessionCarryForwardProjection? NextSessionCarryForward,
    NextSafeActionCue NextSafeAction,
    WorkspaceRestoreReceiptStatusProjection RestoreReceiptStatus,
    IReadOnlyList<WorkspaceRestoreReceiptSurfaceProjection> RestoreReceiptSurfaces,
    IReadOnlyList<WorkspaceRestoreProvenanceReceipt> RestoreProvenanceReceipts,
    IReadOnlyList<WorkspaceRestoreProvenanceRecoveryProjection> RestoreProvenanceRecoveryReceipts,
    IReadOnlyList<WorkspaceRestoreConflictReceiptProjection> RestoreConflictReceipts,
    DateTimeOffset GeneratedAtUtc);

public sealed record WorkspaceRestoreReceiptSurfaceProjection(
    string Surface,
    string Label,
    WorkspaceRestoreReceiptStatusProjection Status);

public sealed record WorkspaceRestoreReceiptStatusProjection(
    string Summary,
    string ProvenanceSummary,
    string ConflictSummary,
    string StalenessPosture,
    string ConflictPosture,
    string RecoverabilityPosture,
    string ContinuePosture,
    string LeadReceiptId,
    string LeadSurface,
    string LeadAuthority,
    string LeadKind,
    string LeadSubjectId,
    string LeadRecoveryHint,
    DateTimeOffset LeadObservedAtUtc,
    DateTimeOffset LatestReceiptObservedAtUtc,
    string RecoveryRoute,
    string RecoveryActionLabel,
    string RecoverySummary,
    int CurrentProvenanceReceiptCount,
    int StaleOrDriftProvenanceReceiptCount,
    int WorkspaceRestoreProvenanceCount,
    int EntitlementSyncProvenanceCount,
    int WorkspaceRestoreConflictCount,
    int EntitlementSyncConflictCount,
    int SafeToContinueWithReceiptCount,
    int RefreshBeforeContinueCount,
    int ReviewBeforeContinueConflictCount,
    int BlockingConflictCount);

public sealed record WorkspaceRestoreProvenanceRecoveryProjection(
    string ReceiptId,
    string Kind,
    string SubjectId,
    string Surface,
    string Summary,
    string? Proof,
    DateTimeOffset ObservedAtUtc,
    string Authority,
    string StalenessPosture,
    string RecoverabilityPosture,
    string RecoveryHint,
    string RecoveryRoute,
    string RecoverySummary,
    string ContinuePosture);

public sealed record WorkspaceRestoreConflictReceiptProjection(
    string ReceiptId,
    string Severity,
    string Kind,
    string Surface,
    string Authority,
    string SubjectId,
    string Summary,
    string? Resolution,
    string ConflictPosture,
    string RecoverabilityPosture,
    string RecoveryRoute,
    string RecoveryHint,
    string RecoverySummary,
    string ContinuePosture,
    DateTimeOffset ObservedAtUtc,
    bool BlocksContinue);

public sealed record GmOperationsReadinessSummary(
    string Status,
    string Summary,
    string AccountBackboneSummary,
    int OppositionSignalCount,
    int RosterMovementSignalCount,
    int PrepPacketCount,
    int PrepLaunchCount,
    int EventControlSignalCount,
    IReadOnlyList<GmOperationsLaneCue> LaneCues);

public sealed record GmOperationsLaneCue(
    string Lane,
    string Status,
    int SignalCount,
    string Summary);

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
    string CacheFreshnessSummary,
    string OfflineActionabilitySummary,
    IReadOnlyList<TravelOfflineLaneCue> OfflineLaneCues,
    int ClaimedDeviceCount,
    int TravelReadyDeviceCount,
    int FreshCacheDeviceCount,
    int StaleCacheDeviceCount,
    IReadOnlyList<TravelModeDeviceReadinessCue> Devices,
    IReadOnlyList<string> Boundaries);

public sealed record TravelOfflineLaneCue(
    string Lane,
    string Status,
    int SignalCount,
    string Summary);

public sealed record TravelModeDeviceReadinessCue(
    string InstallationId,
    string DeviceRole,
    string Platform,
    string HeadId,
    string Channel,
    string Status,
    string Summary);
