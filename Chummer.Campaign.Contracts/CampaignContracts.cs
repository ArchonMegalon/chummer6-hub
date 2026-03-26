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
    DateTimeOffset UpdatedAtUtc);

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
    int ActiveSponsorSessionCount);

public sealed record CampaignReadinessCue(
    string CueId,
    string Severity,
    string Title,
    string Summary);

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
    string ReturnSummary);

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
    DateTimeOffset UpdatedAtUtc);

public sealed record RulesNavigatorAnswerProjection(
    string EntryId,
    string Question,
    string ShortAnswer,
    string BeforeSummary,
    string AfterSummary,
    string ExplainEntryId,
    string ProvenanceLabel,
    IReadOnlyList<string> EvidenceLines,
    IReadOnlyList<string> SupportReuseHints);

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
    DateTimeOffset UpdatedAtUtc);

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
