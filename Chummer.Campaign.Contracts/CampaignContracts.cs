using Chummer.Contracts.Rulesets;
using System.ComponentModel.DataAnnotations;

namespace Chummer.Campaign.Contracts;

public static class DossierStatuses
{
    public const string Draft = "draft";
    public const string Active = "active";
    public const string Archived = "archived";
}

public static class CampaignStatuses
{
    public const string Active = "active";
    public const string Paused = "paused";
    public const string Archived = "archived";
}

public static class RunStatuses
{
    public const string Planned = "planned";
    public const string Active = "active";
    public const string Debrief = "debrief";
    public const string Closed = "closed";
}

public sealed record RuleEnvironmentRef(
    string EnvironmentId,
    string OwnerScope,
    string CompatibilityFingerprint,
    string ApprovalState,
    IReadOnlyList<string> SourcePacks,
    IReadOnlyList<string> HouseRulePacks,
    IReadOnlyList<string> OptionToggles);

public sealed record ContinuitySnapshotRef(
    string SnapshotId,
    DateTimeOffset CapturedAtUtc,
    string Summary,
    string RestoreState,
    string? SessionId = null,
    string? SceneId = null,
    string? RecapArtifactId = null);

public sealed record PublicationSafeProjection(
    string ProjectionId,
    string Kind,
    string Label,
    string Summary,
    string? ArtifactId = null);

public sealed record CampaignConsequenceReceipt(
    string ReceiptId,
    string SourceKind,
    string Summary);

public sealed record CampaignConsequenceProjection(
    string ConsequenceId,
    string Kind,
    string Label,
    string State,
    string Summary,
    IReadOnlyList<string> EvidenceLines,
    IReadOnlyList<CampaignConsequenceReceipt> Receipts,
    DateTimeOffset UpdatedAtUtc);

public sealed record RosterTransferProjection(
    string TransferId,
    string DossierId,
    string RunnerHandle,
    string PreviousOwnerUserId,
    string CurrentOwnerUserId,
    string SourceGroupId,
    string SourceGroupName,
    string SourceCampaignId,
    string SourceCampaignName,
    string SourceCrewId,
    string SourceCrewName,
    string TargetGroupId,
    string TargetGroupName,
    string TargetCampaignId,
    string TargetCampaignName,
    string TargetCrewId,
    string TargetCrewName,
    string InitiatedByUserId,
    string Summary,
    IReadOnlyList<string> AuditLines,
    IReadOnlyList<CampaignConsequenceReceipt> Receipts,
    DateTimeOffset TransferredAtUtc);

public sealed record RosterTransferRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string DossierId,
    [Required(AllowEmptyStrings = false), StringLength(128)] string TargetGroupId,
    [StringLength(128)] string? TargetCampaignId = null,
    [StringLength(128)] string? TargetCampaignTitle = null,
    [StringLength(128)] string? TargetOwnerUserId = null,
    [StringLength(256)] string? Note = null);

public sealed record RosterTransferCandidateProjection(
    string DossierId,
    string RunnerHandle,
    string DisplayName,
    string CurrentOwnerUserId,
    string CurrentOwnerDisplayName,
    string CurrentCampaignId,
    string CurrentCampaignName);

public sealed record RosterTransferOwnerOptionProjection(
    string UserId,
    string DisplayName,
    string Role);

public sealed record RosterTransferTargetGroupProjection(
    string GroupId,
    string GroupName,
    string GroupType,
    string OperatorRole,
    string SuggestedCampaignTitle,
    IReadOnlyList<RosterTransferOwnerOptionProjection> OwnerOptions);

public sealed record RosterTransferPlannerProjection(
    string WorkspaceId,
    string SourceGroupId,
    string SourceGroupName,
    string SourceCampaignId,
    string SourceCampaignName,
    string Summary,
    IReadOnlyList<RosterTransferCandidateProjection> DossierOptions,
    IReadOnlyList<RosterTransferTargetGroupProjection> TargetGroups);

public sealed record GovernedPrepLaunchRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string PacketId,
    [StringLength(128)] string? TargetRunId = null,
    [StringLength(128)] string? TargetSceneId = null,
    [StringLength(256)] string? Note = null);

public sealed record GovernedPrepLaunchProjection(
    string LaunchId,
    string WorkspaceId,
    string CampaignId,
    string PacketId,
    string PacketKind,
    string PacketTitle,
    string? TargetRunId,
    string? TargetRunTitle,
    string? TargetSceneId,
    string? TargetSceneTitle,
    string InitiatedByUserId,
    string Summary,
    IReadOnlyList<string> AuditLines,
    DateTimeOffset LaunchedAtUtc);

public sealed record TravelPrefetchStageRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string InstallationId,
    [StringLength(256)] string? Note = null);

public sealed record TravelPrefetchReceiptProjection(
    string ReceiptId,
    string WorkspaceId,
    string CampaignId,
    string InstallationId,
    string DeviceRole,
    string Platform,
    string HeadId,
    string Channel,
    string PrefetchSummary,
    IReadOnlyList<string> InventoryLines,
    IReadOnlyList<string> Boundaries,
    string InitiatedByUserId,
    DateTimeOffset StagedAtUtc);

public sealed record AftermathRecapPackageRequest(
    [StringLength(128)] string? RunId,
    [Required(AllowEmptyStrings = false), StringLength(64)] string PackageKind,
    [StringLength(128)] string? Title = null,
    [StringLength(256)] string? Note = null);

public sealed record AftermathRecapPackageProjection(
    string PackageId,
    string WorkspaceId,
    string CampaignId,
    string? RunId,
    string? RunTitle,
    string PackageKind,
    string Title,
    string Summary,
    string ArtifactId,
    IReadOnlyList<string> EvidenceLines,
    string InitiatedByUserId,
    DateTimeOffset GeneratedAtUtc);

public sealed record RunnerDossierProjection(
    string DossierId,
    string RunnerHandle,
    string DisplayName,
    string Status,
    string OwnerUserId,
    string? CrewId,
    string? CampaignId,
    string? CurrentRunId,
    string? CurrentSceneId,
    RuleEnvironmentRef RuleEnvironment,
    ContinuitySnapshotRef? LatestContinuity,
    IReadOnlyList<string> BuildReceiptIds,
    IReadOnlyList<string> SnapshotIds,
    IReadOnlyList<PublicationSafeProjection> Projections,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc);

public sealed record CrewAssignmentProjection(
    string UserId,
    string DossierId,
    string Role,
    string Availability,
    DateTimeOffset AddedAtUtc);

public sealed record CrewProjection(
    string CrewId,
    string Name,
    string Visibility,
    string GroupId,
    string CampaignId,
    IReadOnlyList<CrewAssignmentProjection> Members,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc);

public sealed record ObjectiveProjection(
    string ObjectiveId,
    string Title,
    string Status,
    string Pressure,
    string Summary,
    DateTimeOffset UpdatedAtUtc);

public sealed record SceneProjection(
    string SceneId,
    string RunId,
    string Title,
    string Revision,
    string Status,
    string Summary,
    DateTimeOffset UpdatedAtUtc);

public sealed record RunProjection(
    string RunId,
    string CampaignId,
    string Title,
    string Status,
    string Summary,
    string? ActiveSceneId,
    IReadOnlyList<ObjectiveProjection> Objectives,
    IReadOnlyList<SceneProjection> Scenes,
    ContinuitySnapshotRef? LatestContinuity,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc);

public sealed record CampaignProjection(
    string CampaignId,
    string GroupId,
    string Name,
    string Status,
    string Visibility,
    string Summary,
    RuleEnvironmentRef RuleEnvironment,
    string? ActiveRunId,
    IReadOnlyList<string> CrewIds,
    IReadOnlyList<string> DossierIds,
    IReadOnlyList<string> RunIds,
    ContinuitySnapshotRef? LatestContinuity,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    IReadOnlyList<CampaignConsequenceProjection>? Consequences = null);

public sealed record WorkspaceRestoreProjection(
    string RestoreId,
    string UserId,
    IReadOnlyList<RunnerDossierProjection> RecentDossiers,
    IReadOnlyList<CampaignProjection> RecentCampaigns,
    IReadOnlyList<RuleEnvironmentRef> RecentRuleEnvironments,
    IReadOnlyList<RestoreArtifactProjection> RecentArtifacts,
    IReadOnlyList<RestoreEntitlementProjection> Entitlements,
    IReadOnlyList<ClaimedDeviceRestoreProjection> ClaimedDevices,
    IReadOnlyList<string> ConflictSummaries,
    IReadOnlyList<string> LocalOnlyNotes,
    DateTimeOffset GeneratedAtUtc);

public sealed record CommunityOperatorProjection(
    string GroupId,
    string GroupName,
    string GroupType,
    string Visibility,
    string OperatorRole,
    string CampaignVisibilitySummary,
    IReadOnlyList<string> CampaignNames,
    RuleEnvironmentRef RuleEnvironment,
    IReadOnlyList<string> Capabilities,
    int MemberCount,
    int ActiveCampaignCount,
    int ActiveSponsorSessionCount,
    string OperationsSummary,
    string LeagueOperationsSummary,
    string CampaignReturnSummary,
    string SeasonEventSummary,
    IReadOnlyList<string> RecentReturnSummaries,
    IReadOnlyList<string> RecentEventSummaries,
    IReadOnlyList<CommunityInviteCampaignProjection> InviteCampaigns,
    IReadOnlyList<CommunityJoinCodeProjection> RecentJoinCodes,
    IReadOnlyList<CommunityBoostCodeProjection> RecentBoostCodes,
    IReadOnlyList<CommunitySponsorSessionProjection> RecentSponsorSessions,
    IReadOnlyList<string> RecentLeagueAuditLines,
    IReadOnlyList<CommunitySeasonBoardEntryProjection> SeasonBoardEntries,
    IReadOnlyList<string> Watchouts,
    IReadOnlyList<RosterTransferProjection>? RecentRosterTransfers = null);

public sealed record CommunityInviteCampaignProjection(
    string CampaignId,
    string CampaignName,
    string Status);

public sealed record CommunityJoinCodeProjection(
    string JoinCodeId,
    string Code,
    string Role,
    string Status,
    string StatusSummary,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset? ExpiresAtUtc,
    int Uses);

public sealed record CommunityBoostCodeProjection(
    string BoostCodeId,
    string Code,
    string CampaignId,
    string CampaignName,
    string Status,
    string StatusSummary,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset? RedeemedAtUtc);

public sealed record CommunitySponsorSessionProjection(
    string SponsorSessionId,
    string UserId,
    string UserDisplayName,
    string CampaignId,
    string CampaignName,
    string Status,
    string StatusSummary,
    string RequestedLaneRole,
    string AuthorizationTier,
    string? LatestEventSummary,
    DateTimeOffset UpdatedAtUtc);

public sealed record CommunitySeasonBoardEntryProjection(
    string CampaignId,
    string WorkspaceId,
    string CampaignName,
    string RunTitle,
    string LatestEventSummary,
    string? CampaignMemorySummary,
    string? CampaignMemoryReturnSummary,
    string NextSafeAction,
    string? WatchoutSummary,
    DateTimeOffset UpdatedAtUtc);

public sealed record CampaignReadinessCue(
    string CueId,
    string Severity,
    string Title,
    string Summary);

public sealed record CampaignMemoryProjection(
    string MemoryId,
    string Label,
    string Summary,
    string ReturnSummary,
    string NextSafeAction,
    IReadOnlyList<string> EvidenceLines,
    DateTimeOffset UpdatedAtUtc);

public sealed record WorkspaceChangePacketProjection(
    string PacketId,
    string Kind,
    string Label,
    string Summary,
    DateTimeOffset UpdatedAtUtc);

public sealed record NextSessionCarryForwardProjection(
    string CarryForwardId,
    string Label,
    string Summary,
    string ReturnSummary,
    string NextSafeAction,
    IReadOnlyList<string> EvidenceLines,
    DateTimeOffset UpdatedAtUtc);

public sealed record CampaignWorkspaceProjection(
    string WorkspaceId,
    string CampaignId,
    string CampaignName,
    string Visibility,
    RuleEnvironmentRef RuleEnvironment,
    IReadOnlyList<CrewProjection> Crews,
    IReadOnlyList<RunnerDossierProjection> Dossiers,
    IReadOnlyList<RunProjection> Runs,
    IReadOnlyList<PublicationSafeProjection> RecapShelf,
    IReadOnlyList<CampaignReadinessCue> ReadinessCues,
    ContinuitySnapshotRef? LatestContinuity,
    string ReturnSummary,
    string? ActiveSceneSummary = null,
    string? NextSafeAction = null,
    IReadOnlyList<WorkspaceChangePacketProjection>? ChangePackets = null,
    IReadOnlyList<CampaignConsequenceProjection>? Consequences = null,
    IReadOnlyList<RosterTransferProjection>? RosterTransfers = null,
    IReadOnlyList<GovernedPrepLaunchProjection>? PrepLaunches = null,
    IReadOnlyList<TravelPrefetchReceiptProjection>? TravelPrefetches = null,
    IReadOnlyList<AftermathRecapPackageProjection>? AftermathPackages = null,
    NextSessionCarryForwardProjection? NextSessionCarryForward = null,
    CampaignMemoryProjection? CampaignMemory = null);

public sealed record CampaignWorkspaceDigestProjection(
    string WorkspaceId,
    string CampaignId,
    string CampaignName,
    string ReturnSummary,
    string RuleEnvironmentSummary,
    string DeviceRoleSummary,
    string SupportClosureSummary,
    string? ActiveSceneSummary,
    string NextSafeAction,
    IReadOnlyList<string> ReadinessHighlights,
    IReadOnlyList<string> Watchouts,
    DateTimeOffset UpdatedAtUtc,
    CampaignMemoryProjection? CampaignMemory = null);

public sealed record WorkspaceSummary(
    string WorkspaceId,
    string CampaignId,
    string CampaignName,
    string Visibility,
    string ReturnSummary,
    string DeviceRoleSummary,
    string SupportClosureSummary,
    string? ActiveSceneSummary,
    DateTimeOffset UpdatedAtUtc);

public sealed record CampaignWorkspaceSummary(
    string WorkspaceId,
    string CampaignId,
    string CampaignName,
    string RuleEnvironmentSummary,
    string SessionReadinessSummary,
    string RestoreSummary,
    string PublicationSummary,
    string NextSafeAction,
    DateTimeOffset UpdatedAtUtc);

public sealed record RosterReadinessSummary(
    string Summary,
    int ReadyDossierCount,
    int NeedsAttentionCount,
    int CrewCount,
    int RunCount,
    IReadOnlyList<string> Highlights);

public sealed record DossierFreshnessCue(
    string DossierId,
    string RunnerHandle,
    string Status,
    string Severity,
    string Summary);

public sealed record RuleEnvironmentHealthCue(
    string EnvironmentId,
    string Severity,
    string Title,
    string Summary);

public sealed record RunboardSummary(
    string RunId,
    string Title,
    string Status,
    string? ActiveSceneId,
    string? ActiveSceneSummary,
    string ObjectiveSummary,
    IReadOnlyList<string> Blockers,
    string ReturnSummary);

public sealed record ContinuityConflictCue(
    string CueId,
    string Severity,
    string Summary,
    string ResolutionAction);

public sealed record RecapShelfEntry(
    string EntryId,
    string Kind,
    string Label,
    string Summary,
    string? ArtifactId,
    DateTimeOffset UpdatedAtUtc);

public sealed record RestoreArtifactProjection(
    string ArtifactId,
    string Label,
    string Kind,
    string Summary,
    string? Channel = null,
    string? Version = null);

public sealed record RestoreEntitlementProjection(
    string EntitlementId,
    string Label,
    string Scope,
    string Status,
    string Summary);

public sealed record ClaimedDeviceRestoreProjection(
    string InstallationId,
    string DeviceRole,
    string Platform,
    string HeadId,
    string Channel,
    string? HostLabel,
    string RestoreSummary);

public sealed record BuildLabHandoffProjection(
    string HandoffId,
    string DossierId,
    string? CampaignId,
    string Title,
    string Summary,
    string VariantLabel,
    string ProgressionLabel,
    string ExplainEntryId,
    IReadOnlyList<string> TradeoffLines,
    IReadOnlyList<string> ProgressionOutcomes,
    IReadOnlyList<PublicationSafeProjection> Outputs,
    DateTimeOffset UpdatedAtUtc,
    string? NextSafeAction = null,
    string? RuntimeCompatibilitySummary = null,
    string? CampaignReturnSummary = null,
    string? SupportClosureSummary = null,
    IReadOnlyList<string>? Watchouts = null);

public sealed record RulesNavigatorAnswerProjection(
    string EntryId,
    string Question,
    string ShortAnswer,
    string BeforeSummary,
    string AfterSummary,
    string ExplainEntryId,
    string ProvenanceLabel,
    IReadOnlyList<string> EvidenceLines,
    IReadOnlyList<string> SupportReuseHints,
    IReadOnlyList<RulesetEnvironmentDiffProjection>? Diffs = null);

public sealed record LegacyMigrationFieldProjection(
    string FieldId,
    string Label,
    string Status,
    string Summary);

public sealed record LegacyMigrationReceiptProjection(
    string ReceiptId,
    string SourceKind,
    string SourceId,
    string TargetDossierId,
    string? TargetCampaignId,
    string Summary,
    IReadOnlyList<LegacyMigrationFieldProjection> Fields,
    DateTimeOffset ImportedAtUtc);

public sealed record CreatorPublicationProjection(
    string PublicationId,
    string Title,
    string Kind,
    string Summary,
    string CampaignId,
    string? DossierId,
    string ArtifactId,
    string ProvenanceSummary,
    string DiscoverySummary,
    string Visibility,
    string PublicationStatus,
    DateTimeOffset UpdatedAtUtc,
    string? NextSafeAction = null,
    string? CampaignReturnSummary = null,
    string? SupportClosureSummary = null,
    string? BuildHandoffId = null,
    IReadOnlyList<string>? Watchouts = null);

public sealed record AccountCampaignSummary(
    IReadOnlyList<RunnerDossierProjection> Dossiers,
    IReadOnlyList<CampaignProjection> Campaigns,
    IReadOnlyList<RunProjection> Runs,
    IReadOnlyList<CrewProjection> Crews,
    IReadOnlyList<CampaignWorkspaceProjection> Workspaces,
    IReadOnlyList<CommunityOperatorProjection> CommunityOperations,
    IReadOnlyList<BuildLabHandoffProjection> BuildLabHandoffs,
    IReadOnlyList<RulesNavigatorAnswerProjection> RulesNavigator,
    IReadOnlyList<LegacyMigrationReceiptProjection> MigrationReceipts,
    IReadOnlyList<CreatorPublicationProjection> CreatorPublications,
    WorkspaceRestoreProjection Restore);
