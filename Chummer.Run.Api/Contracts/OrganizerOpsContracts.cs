using Chummer.Control.Contracts.Support;

namespace Chummer.Run.Api.Contracts;

public sealed record OrganizerOperationsDashboardProjection(
    DateTimeOffset GeneratedAtUtc,
    IReadOnlyList<OrganizerOperationProjection> Items);

public sealed record OrganizerOperationProjection(
    string GroupId,
    string GroupName,
    string GroupType,
    string Visibility,
    string OperatorRole,
    IReadOnlyList<OrganizerRoleAssignmentProjection> Roles,
    IReadOnlyList<OrganizerPermissionProjection> Permissions,
    OrganizerRosterContractProjection Roster,
    OrganizerEventRailContractProjection EventRail,
    OrganizerArtifactPublicationContractProjection ArtifactPublication,
    OrganizerSupportEscalationContractProjection SupportEscalation,
    IReadOnlyList<string> AuditLines);

public sealed record OrganizerRoleAssignmentProjection(
    string UserId,
    string DisplayName,
    string Role,
    DateTimeOffset JoinedAtUtc,
    bool CanManageMembers,
    bool CanIssueCodes);

public sealed record OrganizerPermissionProjection(
    string Capability,
    string Label,
    string Summary);

public sealed record OrganizerRosterContractProjection(
    string Summary,
    int MemberCount,
    int ActiveCampaignCount,
    int RecentTransferCount,
    IReadOnlyList<string> CampaignNames,
    IReadOnlyList<string> RecentTransferSummaries);

public sealed record OrganizerEventRailContractProjection(
    string Summary,
    int SeasonBoardCount,
    int RecentEventCount,
    int ActiveSponsorSessionCount,
    IReadOnlyList<OrganizerSeasonLaneProjection> SeasonLanes,
    IReadOnlyList<string> RecentEventSummaries,
    IReadOnlyList<string> AuditLines);

public sealed record OrganizerSeasonLaneProjection(
    string CampaignId,
    string WorkspaceId,
    string CampaignName,
    string RunTitle,
    string LatestEventSummary,
    string NextSafeAction,
    string? RecapSummary,
    string? ConsequenceSummary,
    string? CampaignMemorySummary,
    string? WatchoutSummary,
    DateTimeOffset UpdatedAtUtc);

public sealed record OrganizerArtifactPublicationContractProjection(
    string Summary,
    int ReceiptCount,
    int ReadyOrPublishedCount,
    int DiscoverableCount,
    IReadOnlyList<OrganizerArtifactPublicationReceiptProjection> Receipts);

public sealed record OrganizerArtifactPublicationReceiptProjection(
    string EntryId,
    string Label,
    string Summary,
    string Audience,
    string? PublicationState,
    string? TrustBand,
    bool Discoverable,
    string? PublicationSummary,
    string? NextSafeAction,
    string? AuditSummary);

public sealed record OrganizerSupportEscalationContractProjection(
    string Summary,
    int OpenCaseCount,
    IReadOnlyList<OrganizerSupportCaseProjection> Cases);

public sealed record OrganizerSupportCaseProjection(
    string CaseId,
    string Kind,
    string Status,
    string Title,
    string Summary,
    string Source,
    DateTimeOffset UpdatedAtUtc,
    string? ReleaseChannel = null,
    string? Platform = null,
    string? InstallationId = null,
    string? FixedChannel = null,
    string? FixedVersion = null,
    IReadOnlyList<SupportCaseTimelineEvent>? Timeline = null);
