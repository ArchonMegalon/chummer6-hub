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
    IReadOnlyList<string> RecentArtifactIds,
    IReadOnlyList<string> ConflictSummaries,
    DateTimeOffset GeneratedAtUtc);

public sealed record CommunityOperatorProjection(
    string GroupId,
    string GroupName,
    string GroupType,
    string Visibility,
    IReadOnlyList<string> Capabilities,
    int MemberCount,
    int ActiveCampaignCount,
    int ActiveSponsorSessionCount);

public sealed record AccountCampaignSummary(
    IReadOnlyList<RunnerDossierProjection> Dossiers,
    IReadOnlyList<CampaignProjection> Campaigns,
    IReadOnlyList<CommunityOperatorProjection> CommunityOperations,
    WorkspaceRestoreProjection Restore);
