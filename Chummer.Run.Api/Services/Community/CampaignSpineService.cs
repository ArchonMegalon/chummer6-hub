using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Campaign.Contracts;
using Chummer.Contracts.Rulesets;
using Chummer.Hub.Registry.Contracts;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Registry.Services;

namespace Chummer.Run.Api.Services.Community;

public sealed class CampaignSpineService
{
    private static readonly JsonSerializerOptions ComparisonJsonOptions = new(JsonSerializerDefaults.Web);
    private static readonly IReadOnlyList<string> DefaultPersonalPreviewCapabilities =
    [
        "can_manage_members",
        "can_issue_join_codes",
        "can_issue_boost_codes",
        "can_hold_shared_entitlements",
        "campaign_workspace",
        "build_lab",
        "rules_navigator",
        "creator_publication",
        "support_closure"
    ];

    private readonly CommunityStore _store;
    private readonly WorkspaceLifecyclePolicyService _lifecyclePolicy;
    private readonly CampaignArtifactRegistryBridge _artifactRegistry;
    private readonly IHubPublicationDraftService? _publicationDrafts;

    public CampaignSpineService(
        CommunityStore store,
        WorkspaceLifecyclePolicyService lifecyclePolicy,
        CampaignArtifactRegistryBridge artifactRegistry,
        IHubPublicationDraftService? publicationDrafts = null)
    {
        _store = store;
        _lifecyclePolicy = lifecyclePolicy;
        _artifactRegistry = artifactRegistry;
        _publicationDrafts = publicationDrafts;
    }

    public AccountCampaignSummary GetAccountSummary(HubUserDto user, InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);

        lock (_store.Gate)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            WorkspaceLifecycleCleanupResult cleanup = _lifecyclePolicy.ApplyLocked(_store, now);
            var changed = cleanup.Changed;
            changed |= EnsureSeedDataLocked(user, installLinking, now);
            if (changed)
            {
                _store.PersistLocked();
            }

            var dossiers = _store.DossiersById.Values
                .Where(item => string.Equals(item.OwnerUserId, user.UserId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
            var campaigns = _store.CampaignSpinesById.Values
                .Where(item => item.DossierIds.Any(dossierId => dossiers.Any(dossier => string.Equals(dossier.DossierId, dossierId, StringComparison.OrdinalIgnoreCase))))
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
            var runs = _store.RunsById.Values
                .Where(item => campaigns.Any(campaign => string.Equals(campaign.CampaignId, item.CampaignId, StringComparison.OrdinalIgnoreCase)))
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
            var crews = _store.CrewsById.Values
                .Where(item => campaigns.Any(campaign => string.Equals(item.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase)))
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
            var restore = _store.RestoreByUserId.TryGetValue(user.UserId, out var existingRestore)
                ? existingRestore
                : BuildRestoreProjection(user, dossiers, campaigns, installLinking, now);
            var transfers = _store.RosterTransfers
                .OrderByDescending(static item => item.TransferredAtUtc)
                .ToArray();
            var prepLaunches = _store.PrepLaunches
                .OrderByDescending(static item => item.LaunchedAtUtc)
                .ToArray();
            var travelPrefetchReceipts = _store.TravelPrefetchReceipts
                .OrderByDescending(static item => item.StagedAtUtc)
                .ToArray();
            var aftermathPackages = _store.AftermathPackages
                .OrderByDescending(static item => item.GeneratedAtUtc)
                .ToArray();
            var workspaces = campaigns
                .Select(campaign => BuildWorkspaceProjection(campaign, dossiers, runs, crews, restore, transfers, prepLaunches, travelPrefetchReceipts, aftermathPackages))
                .OrderByDescending(static workspace => ResolveWorkspaceFreshnessUtc(workspace))
                .ThenByDescending(static workspace => ResolveWorkspaceActivityBreadth(workspace))
                .ThenByDescending(static workspace => workspace.AftermathPackages?.Count ?? 0)
                .ThenByDescending(static workspace => workspace.PrepLaunches?.Count ?? 0)
                .ThenByDescending(static workspace => workspace.TravelPrefetches?.Count ?? 0)
                .ThenByDescending(static workspace => workspace.RosterTransfers?.Count ?? 0)
                .ThenBy(static workspace => workspace.CampaignName, StringComparer.OrdinalIgnoreCase)
                .ToArray();
            var operations = _store.GroupsById.Values
                .Where(group => group.Memberships.Any(member => string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase) && IsOperatorRole(member.Role)))
                .Select(group =>
                {
                    var groupCampaigns = _store.CampaignSpinesById.Values
                        .Where(item => string.Equals(item.GroupId, group.GroupId, StringComparison.OrdinalIgnoreCase))
                        .OrderBy(item => item.Name, StringComparer.OrdinalIgnoreCase)
                        .ToArray();
                    var groupWorkspaces = workspaces
                        .Where(workspace => groupCampaigns.Any(campaign => string.Equals(campaign.CampaignId, workspace.CampaignId, StringComparison.OrdinalIgnoreCase)))
                        .OrderByDescending(static workspace => ResolveWorkspaceFreshnessUtc(workspace))
                        .ThenByDescending(static workspace => ResolveWorkspaceActivityBreadth(workspace))
                        .ThenByDescending(static workspace => workspace.AftermathPackages?.Count ?? 0)
                        .ThenByDescending(static workspace => workspace.PrepLaunches?.Count ?? 0)
                        .ThenByDescending(static workspace => workspace.TravelPrefetches?.Count ?? 0)
                        .ThenByDescending(static workspace => workspace.RosterTransfers?.Count ?? 0)
                        .ThenBy(static workspace => workspace.CampaignName, StringComparer.OrdinalIgnoreCase)
                        .ToArray();
                    var recentJoinCodes = BuildGroupRecentJoinCodes(_store.JoinCodesByValue.Values, group.GroupId, now);
                    var recentBoostCodes = BuildGroupRecentBoostCodes(_store.BoostCodesByValue.Values, groupCampaigns, group.GroupId);
                    var recentSponsorSessions = BuildGroupRecentSponsorSessions(_store.SponsorSessionsById.Values, _store.UsersById, groupCampaigns, group.GroupId);
                    var seasonBoardEntries = BuildGroupSeasonBoardEntries(groupWorkspaces);
                    var recentRosterTransfers = transfers
                        .Where(item =>
                            string.Equals(item.SourceGroupId, group.GroupId, StringComparison.OrdinalIgnoreCase)
                            || string.Equals(item.TargetGroupId, group.GroupId, StringComparison.OrdinalIgnoreCase))
                        .Take(5)
                        .ToArray();
                    return new CommunityOperatorProjection(
                        GroupId: group.GroupId,
                        GroupName: group.Name,
                        GroupType: group.GroupType,
                        Visibility: group.Visibility,
                        OperatorRole: ResolveOperatorRole(group, user.UserId),
                        CampaignVisibilitySummary: ResolveCampaignVisibilitySummary(groupCampaigns),
                        CampaignNames: groupCampaigns.Select(static item => item.Name).ToArray(),
                        RuleEnvironment: DefaultRuleEnvironment($"group:{group.GroupId}", "group"),
                        Capabilities: group.Capabilities,
                        MemberCount: group.Memberships.Count,
                        ActiveCampaignCount: groupCampaigns.Count(item => string.Equals(item.Status, CampaignStatuses.Active, StringComparison.OrdinalIgnoreCase)),
                        ActiveSponsorSessionCount: _store.SponsorSessionsById.Values.Count(item => string.Equals(item.GroupId, group.GroupId, StringComparison.OrdinalIgnoreCase) && !string.Equals(item.Status, "stopped", StringComparison.OrdinalIgnoreCase)),
                        OperationsSummary: ResolveGroupOperationsSummary(group, groupCampaigns, groupWorkspaces),
                        LeagueOperationsSummary: ResolveGroupLeagueOperationsSummary(group, groupCampaigns, groupWorkspaces, recentSponsorSessions, recentJoinCodes, recentBoostCodes, recentRosterTransfers),
                        CampaignReturnSummary: ResolveGroupCampaignReturnSummary(group, groupWorkspaces),
                        SeasonEventSummary: ResolveGroupSeasonEventSummary(group, groupCampaigns, groupWorkspaces),
                        RecentReturnSummaries: groupWorkspaces
                            .Select(static workspace => $"{workspace.CampaignName}: {workspace.ReturnSummary}")
                            .Take(3)
                            .ToArray(),
                        RecentEventSummaries: BuildGroupRecentEventSummaries(groupWorkspaces),
                        InviteCampaigns: BuildGroupInviteCampaigns(groupCampaigns),
                        RecentJoinCodes: recentJoinCodes,
                        RecentBoostCodes: recentBoostCodes,
                        RecentSponsorSessions: recentSponsorSessions,
                        RecentLeagueAuditLines: BuildGroupRecentLeagueAuditLines(recentSponsorSessions, recentJoinCodes, recentBoostCodes, seasonBoardEntries, recentRosterTransfers),
                        SeasonBoardEntries: seasonBoardEntries,
                        Watchouts: BuildGroupOperatorWatchouts(groupWorkspaces),
                        RecentRosterTransfers: recentRosterTransfers);
                })
                .OrderByDescending(static operation => ResolveCommunityOperatorFreshnessUtc(operation))
                .ThenByDescending(static operation => ResolveCommunityOperatorActivityBreadth(operation))
                .ThenByDescending(static operation => operation.ActiveCampaignCount)
                .ThenByDescending(static operation => operation.ActiveSponsorSessionCount)
                .ThenBy(static operation => operation.GroupName, StringComparer.OrdinalIgnoreCase)
                .ToArray();
            var buildLabHandoffs = BuildBuildLabHandoffs(dossiers, workspaces, restore);
            var rulesNavigator = BuildRulesNavigatorEntries(workspaces, operations);
            var migrationReceipts = BuildMigrationReceipts(dossiers, campaigns);
            var creatorPublications = AttachRegistryPublicationPosture(BuildCreatorPublications(workspaces, dossiers, buildLabHandoffs));
            workspaces = AttachCreatorPublicationPosture(workspaces, creatorPublications).ToArray();

            return new AccountCampaignSummary(
                dossiers,
                campaigns,
                runs,
                crews,
                workspaces,
                operations,
                buildLabHandoffs,
                rulesNavigator,
                migrationReceipts,
                creatorPublications,
                restore);
        }
    }

    public WorkspaceRestoreProjection GetRestoreProjection(HubUserDto user, InstallLinkingSummaryDto? installLinking = null)
        => GetAccountSummary(user, installLinking).Restore;

    public CampaignWorkspaceProjection? GetWorkspace(HubUserDto user, string workspaceId, InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentException.ThrowIfNullOrWhiteSpace(workspaceId);

        return GetAccountSummary(user, installLinking).Workspaces
            .FirstOrDefault(item => string.Equals(item.WorkspaceId, workspaceId, StringComparison.OrdinalIgnoreCase));
    }

    public CampaignWorkspaceProjection? GetStarterWorkspace(HubUserDto user, InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        return GetAccountSummary(user, installLinking).Workspaces.FirstOrDefault();
    }

    public GovernedPrepLaunchProjection RecordPrepLaunch(
        HubUserDto user,
        CampaignWorkspaceProjection workspace,
        string packetId,
        string packetKind,
        string packetTitle,
        string packetSummary,
        RunProjection? targetRun,
        SceneProjection? targetScene,
        string? note = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentNullException.ThrowIfNull(workspace);

        string normalizedPacketId = AccountService.NormalizeOptional(packetId)
            ?? throw new ArgumentException("packetId is required.", nameof(packetId));
        string normalizedPacketKind = AccountService.NormalizeOptional(packetKind)
            ?? throw new ArgumentException("packetKind is required.", nameof(packetKind));
        string normalizedPacketTitle = AccountService.NormalizeOptional(packetTitle)
            ?? throw new ArgumentException("packetTitle is required.", nameof(packetTitle));
        string normalizedPacketSummary = AccountService.NormalizeOptional(packetSummary) ?? normalizedPacketTitle;
        string? normalizedNote = AccountService.NormalizeOptional(note);

        lock (_store.Gate)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            var launch = new GovernedPrepLaunchProjection(
                LaunchId: StableId("prep-launch", $"{workspace.WorkspaceId}:{normalizedPacketId}:{targetRun?.RunId ?? "campaign"}:{targetScene?.SceneId ?? "scene"}:{now.ToUnixTimeMilliseconds()}"),
                WorkspaceId: workspace.WorkspaceId,
                CampaignId: workspace.CampaignId,
                PacketId: normalizedPacketId,
                PacketKind: normalizedPacketKind,
                PacketTitle: normalizedPacketTitle,
                TargetRunId: targetRun?.RunId,
                TargetRunTitle: targetRun?.Title,
                TargetSceneId: targetScene?.SceneId,
                TargetSceneTitle: targetScene?.Title,
                InitiatedByUserId: user.UserId,
                Summary: DescribePrepLaunchSummary(workspace, normalizedPacketTitle, targetRun, targetScene),
                AuditLines: FinalizeLines(
                [
                    $"Bound governed packet {normalizedPacketTitle} ({normalizedPacketKind}) from {workspace.CampaignName}.",
                    $"Packet summary: {normalizedPacketSummary}",
                    targetRun is null
                        ? $"Binding target stays campaign-wide on {workspace.CampaignName}."
                        : targetScene is null
                            ? $"Binding target: {targetRun.Title}."
                            : $"Binding target: {targetRun.Title} / {targetScene.Title}.",
                    $"Rule posture: {workspace.RuleEnvironment.CompatibilityFingerprint}.",
                    normalizedNote is null ? string.Empty : $"Operator note: {normalizedNote}"
                ]),
                LaunchedAtUtc: now);

            _store.PrepLaunches.Add(launch);
            if (_store.PrepLaunches.Count > 64)
            {
                _store.PrepLaunches.RemoveRange(0, _store.PrepLaunches.Count - 64);
            }

            _store.PersistLocked();
            return launch;
        }
    }

    public TravelPrefetchReceiptProjection RecordTravelPrefetch(
        HubUserDto user,
        CampaignWorkspaceProjection workspace,
        ClaimedDeviceRestoreProjection device,
        string prefetchSummary,
        IReadOnlyList<string> inventoryLines,
        IReadOnlyList<string> boundaries,
        string? note = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentNullException.ThrowIfNull(workspace);
        ArgumentNullException.ThrowIfNull(device);

        string normalizedPrefetchSummary = AccountService.NormalizeOptional(prefetchSummary)
            ?? throw new ArgumentException("prefetchSummary is required.", nameof(prefetchSummary));
        string? normalizedNote = AccountService.NormalizeOptional(note);

        lock (_store.Gate)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            var receipt = new TravelPrefetchReceiptProjection(
                ReceiptId: StableId("travel-prefetch", $"{workspace.WorkspaceId}:{device.InstallationId}:{now.ToUnixTimeMilliseconds()}"),
                WorkspaceId: workspace.WorkspaceId,
                CampaignId: workspace.CampaignId,
                InstallationId: device.InstallationId,
                DeviceRole: device.DeviceRole,
                Platform: device.Platform,
                HeadId: device.HeadId,
                Channel: device.Channel,
                PrefetchSummary: normalizedPrefetchSummary,
                InventoryLines: FinalizeLines(
                    inventoryLines.Concat(
                    [
                        normalizedNote is null ? string.Empty : $"Operator note: {normalizedNote}"
                    ])),
                Boundaries: FinalizeLines(boundaries),
                InitiatedByUserId: user.UserId,
                StagedAtUtc: now);

            _store.TravelPrefetchReceipts.Add(receipt);
            if (_store.TravelPrefetchReceipts.Count > 64)
            {
                _store.TravelPrefetchReceipts.RemoveRange(0, _store.TravelPrefetchReceipts.Count - 64);
            }

            _store.PersistLocked();
            return receipt;
        }
    }

    public AftermathRecapPackageProjection RecordAftermathRecapPackage(
        HubUserDto user,
        CampaignWorkspaceProjection workspace,
        RunProjection? run,
        string packageKind,
        string title,
        string summary,
        IReadOnlyList<string> evidenceLines)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentNullException.ThrowIfNull(workspace);

        string normalizedPackageKind = AccountService.NormalizeOptional(packageKind)
            ?? throw new ArgumentException("packageKind is required.", nameof(packageKind));
        string normalizedTitle = AccountService.NormalizeOptional(title)
            ?? throw new ArgumentException("title is required.", nameof(title));
        string normalizedSummary = AccountService.NormalizeOptional(summary)
            ?? normalizedTitle;

        lock (_store.Gate)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            string packageId = StableId("aftermath", $"{workspace.WorkspaceId}:{run?.RunId ?? "campaign"}:{normalizedPackageKind}:{now.ToUnixTimeMilliseconds()}");
            string rulesetId = ResolveArtifactRulesetId(workspace.RuleEnvironment);
            IReadOnlyList<string> finalizedEvidenceLines = FinalizeLines(evidenceLines);
            CampaignArtifactRegistration artifact = _artifactRegistry.RegisterAftermathPackage(new AftermathArtifactRegistrationRequest(
                PackageId: packageId,
                WorkspaceId: workspace.WorkspaceId,
                CampaignId: workspace.CampaignId,
                CampaignName: workspace.CampaignName,
                RunId: run?.RunId,
                RunTitle: run?.Title,
                PackageKind: normalizedPackageKind,
                Title: normalizedTitle,
                Summary: normalizedSummary,
                OwnerUserId: user.UserId,
                RulesetId: rulesetId,
                RuleEnvironmentFingerprint: workspace.RuleEnvironment.CompatibilityFingerprint,
                GeneratedAtUtc: now,
                EvidenceLines: finalizedEvidenceLines));
            var package = new AftermathRecapPackageProjection(
                PackageId: packageId,
                WorkspaceId: workspace.WorkspaceId,
                CampaignId: workspace.CampaignId,
                RunId: run?.RunId,
                RunTitle: run?.Title,
                PackageKind: normalizedPackageKind,
                Title: normalizedTitle,
                Summary: normalizedSummary,
                ArtifactId: artifact.ArtifactId,
                EvidenceLines: finalizedEvidenceLines
                    .Concat(
                    [
                        $"Registry artifact: {artifact.ArtifactId} ({artifact.ArtifactKind} {artifact.ArtifactVersion}, {artifact.ArtifactVisibility}, {artifact.ArtifactTrustTier}, {artifact.ArtifactRulesetId})."
                    ])
                    .ToArray(),
                InitiatedByUserId: user.UserId,
                GeneratedAtUtc: now,
                ArtifactKind: artifact.ArtifactKind,
                ArtifactVersion: artifact.ArtifactVersion,
                ArtifactVisibility: artifact.ArtifactVisibility,
                ArtifactTrustTier: artifact.ArtifactTrustTier,
                ArtifactRulesetId: artifact.ArtifactRulesetId,
                ProvenanceSummary: artifact.ProvenanceSummary,
                AuditSummary: artifact.AuditSummary);

            _store.AftermathPackages.Add(package);
            if (_store.AftermathPackages.Count > 64)
            {
                _store.AftermathPackages.RemoveRange(0, _store.AftermathPackages.Count - 64);
            }

            _store.PersistLocked();
            return package;
        }
    }

    public IReadOnlyList<CampaignWorkspaceDigestProjection> GetWorkspaceDigests(HubUserDto user, InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);

        AccountCampaignSummary summary = GetAccountSummary(user, installLinking);
        return summary.Workspaces
            .Select(workspace => BuildWorkspaceDigest(summary, workspace))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
    }

    public RunProjection? GetRun(HubUserDto user, string runId, InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentException.ThrowIfNullOrWhiteSpace(runId);

        return GetAccountSummary(user, installLinking).Runs
            .FirstOrDefault(item => string.Equals(item.RunId, runId, StringComparison.OrdinalIgnoreCase));
    }

    public BuildLabHandoffProjection? GetBuildLabHandoff(HubUserDto user, string handoffId, InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentException.ThrowIfNullOrWhiteSpace(handoffId);

        return GetAccountSummary(user, installLinking).BuildLabHandoffs
            .FirstOrDefault(item => string.Equals(item.HandoffId, handoffId, StringComparison.OrdinalIgnoreCase));
    }

    public RulesNavigatorAnswerProjection? GetRulesNavigatorAnswer(HubUserDto user, string entryId, InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentException.ThrowIfNullOrWhiteSpace(entryId);

        return GetAccountSummary(user, installLinking).RulesNavigator
            .FirstOrDefault(item => string.Equals(item.EntryId, entryId, StringComparison.OrdinalIgnoreCase));
    }

    public CreatorPublicationProjection? GetCreatorPublication(HubUserDto user, string publicationId, InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentException.ThrowIfNullOrWhiteSpace(publicationId);

        return GetAccountSummary(user, installLinking).CreatorPublications
            .FirstOrDefault(item => string.Equals(item.PublicationId, publicationId, StringComparison.OrdinalIgnoreCase));
    }

    public RosterTransferPlannerProjection? GetRosterTransferPlan(HubUserDto user, string workspaceId, InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentException.ThrowIfNullOrWhiteSpace(workspaceId);

        AccountCampaignSummary summary = GetAccountSummary(user, installLinking);
        CampaignWorkspaceProjection? workspace = summary.Workspaces
            .FirstOrDefault(item => string.Equals(item.WorkspaceId, workspaceId, StringComparison.OrdinalIgnoreCase));
        if (workspace is null)
        {
            return null;
        }

        IReadOnlyList<RunnerDossierProjection> workspaceDossiers = summary.Dossiers
            .Where(item => string.Equals(item.CampaignId, workspace.CampaignId, StringComparison.OrdinalIgnoreCase))
            .OrderBy(item => item.DisplayName, StringComparer.OrdinalIgnoreCase)
            .ThenBy(item => item.RunnerHandle, StringComparer.OrdinalIgnoreCase)
            .ToArray();

        lock (_store.Gate)
        {
            var sourceCampaign = _store.CampaignSpinesById.GetValueOrDefault(workspace.CampaignId);
            var sourceGroup = sourceCampaign is null
                ? null
                : _store.GroupsById.GetValueOrDefault(sourceCampaign.GroupId);
            if (sourceCampaign is null || sourceGroup is null)
            {
                return null;
            }

            var dossierOptions = workspaceDossiers
                .Select(dossier =>
                {
                    var currentOwner = _store.UsersById.GetValueOrDefault(dossier.OwnerUserId);
                    return new RosterTransferCandidateProjection(
                        DossierId: dossier.DossierId,
                        RunnerHandle: dossier.RunnerHandle,
                        DisplayName: dossier.DisplayName,
                        CurrentOwnerUserId: dossier.OwnerUserId,
                        CurrentOwnerDisplayName: currentOwner?.DisplayName ?? dossier.OwnerUserId,
                        CurrentCampaignId: sourceCampaign.CampaignId,
                        CurrentCampaignName: sourceCampaign.Name);
                })
                .ToArray();

            var targetGroups = _store.GroupsById.Values
                .Where(group => CanManageRosterGroup(group, user.UserId))
                .OrderBy(group => group.Name, StringComparer.OrdinalIgnoreCase)
                .Select(group => new RosterTransferTargetGroupProjection(
                    GroupId: group.GroupId,
                    GroupName: group.Name,
                    GroupType: group.GroupType,
                    OperatorRole: ResolveOperatorRole(group, user.UserId),
                    SuggestedCampaignTitle: ResolveSuggestedTransferCampaignTitleLocked(group),
                    OwnerOptions: group.Memberships
                        .OrderByDescending(member => OperatorRolePriority(member.Role))
                        .ThenBy(member => _store.UsersById.GetValueOrDefault(member.UserId)?.DisplayName ?? member.UserId, StringComparer.OrdinalIgnoreCase)
                        .Select(member =>
                        {
                            var memberUser = _store.UsersById.GetValueOrDefault(member.UserId);
                            return new RosterTransferOwnerOptionProjection(
                                UserId: member.UserId,
                                DisplayName: memberUser?.DisplayName ?? member.UserId,
                                Role: member.Role);
                        })
                        .DistinctBy(static item => item.UserId, StringComparer.OrdinalIgnoreCase)
                        .ToArray()))
                .ToArray();

            return new RosterTransferPlannerProjection(
                WorkspaceId: workspace.WorkspaceId,
                SourceGroupId: sourceGroup.GroupId,
                SourceGroupName: sourceGroup.Name,
                SourceCampaignId: sourceCampaign.CampaignId,
                SourceCampaignName: sourceCampaign.Name,
                Summary: "Move a governed dossier between rosters, campaigns, and owners without losing the same dossier id, continuity return, or explicit audit receipt.",
                DossierOptions: dossierOptions,
                TargetGroups: targetGroups);
        }
    }

    public RosterTransferProjection TransferRoster(HubUserDto requester, RosterTransferRequest request)
    {
        ArgumentNullException.ThrowIfNull(requester);
        ArgumentNullException.ThrowIfNull(request);

        lock (_store.Gate)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            string dossierId = ResolveRosterTransferRequestIdentity(request.DossierId, "dossier");
            var dossier = _store.DossiersById.GetValueOrDefault(dossierId)
                ?? throw new KeyNotFoundException($"Unknown dossier: {dossierId}");
            var sourceCampaign = _store.CampaignSpinesById.GetValueOrDefault(dossier.CampaignId ?? string.Empty)
                ?? throw new KeyNotFoundException($"Unknown source campaign: {dossier.CampaignId}");
            var sourceGroup = _store.GroupsById.GetValueOrDefault(sourceCampaign.GroupId)
                ?? throw new KeyNotFoundException($"Unknown source group: {sourceCampaign.GroupId}");
            if (!CanManageRosterGroup(sourceGroup, requester.UserId))
            {
                throw new CommunityAccessDeniedException("requester must be an owner, manager, admin, or gm on the source group to move roster state.");
            }

            string targetGroupId = ResolveRosterTransferRequestIdentity(request.TargetGroupId, "target group");
            var targetGroup = _store.GroupsById.GetValueOrDefault(targetGroupId)
                ?? throw new KeyNotFoundException($"Unknown target group: {targetGroupId}");
            if (!CanManageRosterGroup(targetGroup, requester.UserId))
            {
                throw new CommunityAccessDeniedException("requester must be an owner, manager, admin, or gm on the target group to move roster state.");
            }

            string previousOwnerUserId = dossier.OwnerUserId;
            var previousOwner = _store.UsersById.GetValueOrDefault(previousOwnerUserId);
            string currentOwnerUserId = AccountService.NormalizeOptional(request.TargetOwnerUserId)
                is not { } normalizedTargetOwnerUserId
                ? dossier.OwnerUserId
                : normalizedTargetOwnerUserId;
            var currentOwner = _store.UsersById.GetValueOrDefault(currentOwnerUserId)
                ?? throw new KeyNotFoundException($"Unknown target owner: {currentOwnerUserId}");
            string? targetCampaignId = AccountService.NormalizeOptional(request.TargetCampaignId);
            var targetCampaign = ResolveOrCreateTransferCampaignLocked(targetGroup, targetCampaignId, request.TargetCampaignTitle, now);
            if (!string.Equals(previousOwnerUserId, currentOwnerUserId, StringComparison.OrdinalIgnoreCase)
                && _store.DossiersById.Values.Any(item =>
                    !string.Equals(item.DossierId, dossier.DossierId, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.OwnerUserId, currentOwnerUserId, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.CampaignId, targetCampaign.CampaignId, StringComparison.OrdinalIgnoreCase)))
            {
                throw new InvalidOperationException("target owner already has a governed dossier in the selected campaign; transfer would overwrite assignment truth.");
            }
            string targetCrewId = ResolveCrewIdLocked(targetCampaign.CampaignId);
            string targetRunId = StableId("run", targetCampaign.CampaignId);
            string targetSceneId = StableId("scene", targetCampaign.CampaignId);
            var targetCrew = _store.CrewsById.GetValueOrDefault(targetCrewId);
            var sourceCrew = _store.CrewsById.GetValueOrDefault(dossier.CrewId ?? string.Empty);

            if (targetGroup.Memberships.All(member => !string.Equals(member.UserId, currentOwnerUserId, StringComparison.OrdinalIgnoreCase)))
            {
                _store.GroupsById[targetGroup.GroupId] = targetGroup with
                {
                    Memberships = targetGroup.Memberships
                        .Concat(
                        [
                            new GroupMembershipDto(
                                MembershipId: AccountService.NewId("mbr"),
                                GroupId: targetGroup.GroupId,
                                UserId: currentOwnerUserId,
                                Role: "member",
                                JoinedAtUtc: now)
                        ])
                        .ToArray(),
                    UpdatedAtUtc = now
                };
                targetGroup = _store.GroupsById[targetGroup.GroupId];
            }
            if (_store.UsersById.TryGetValue(currentOwnerUserId, out var currentOwnerRecord)
                && currentOwnerRecord.GroupIds.All(groupId => !string.Equals(groupId, targetGroup.GroupId, StringComparison.OrdinalIgnoreCase)))
            {
                _store.UsersById[currentOwnerUserId] = currentOwnerRecord with
                {
                    GroupIds = currentOwnerRecord.GroupIds.Concat([targetGroup.GroupId]).Distinct(StringComparer.OrdinalIgnoreCase).ToArray(),
                    UpdatedAtUtc = now
                };
                currentOwner = _store.UsersById[currentOwnerUserId];
            }

            var continuity = new ContinuitySnapshotRef(
                SnapshotId: StableId("snapshot", $"{dossier.DossierId}:{targetCampaign.CampaignId}:{now.ToUnixTimeSeconds()}"),
                CapturedAtUtc: now,
                Summary: $"{dossier.DisplayName} now returns through {targetCampaign.Title} under {targetGroup.Name}.",
                RestoreState: "roster_transferred",
                SessionId: targetRunId,
                SceneId: targetSceneId,
                RecapArtifactId: StableId("recap", targetCampaign.CampaignId));
            string note = string.IsNullOrWhiteSpace(request.Note) ? "" : $" Note: {request.Note.Trim()}";
            var transferredDossier = dossier with
            {
                OwnerUserId = currentOwnerUserId,
                CrewId = targetCrewId,
                CampaignId = targetCampaign.CampaignId,
                CurrentRunId = targetRunId,
                CurrentSceneId = targetSceneId,
                RuleEnvironment = DefaultRuleEnvironment($"campaign:{targetCampaign.CampaignId}", "campaign"),
                LatestContinuity = continuity,
                Projections =
                [
                    new PublicationSafeProjection(
                        ProjectionId: StableId("projection", $"{currentOwnerUserId}:{targetCampaign.CampaignId}"),
                        Kind: "campaign_recap",
                        Label: "Campaign-ready dossier",
                        Summary: "This runner can move through build, play, recap, and return without losing identity.",
                        ArtifactId: continuity.RecapArtifactId),
                    new PublicationSafeProjection(
                        ProjectionId: StableId("projection", $"{currentOwnerUserId}:{targetCampaign.CampaignId}:dossier"),
                        Kind: "dossier_card",
                        Label: "Living dossier packet",
                        Summary: "Living dossier truth, campaign continuity, and governed publication detail stay attached to one shared artifact lane.",
                        ArtifactId: dossier.DossierId),
                    new PublicationSafeProjection(
                        ProjectionId: StableId("projection", $"{currentOwnerUserId}:{targetCampaign.CampaignId}:ops"),
                        Kind: "runboard_packet",
                        Label: "Runboard continuity packet",
                        Summary: "GM-facing continuity and recap-safe state for the active campaign return.",
                        ArtifactId: StableId("ops", targetCampaign.CampaignId)),
                    new PublicationSafeProjection(
                        ProjectionId: StableId("projection", $"{currentOwnerUserId}:{targetCampaign.CampaignId}:primer"),
                        Kind: "player_primer",
                        Label: "Campaign primer",
                        Summary: "Session-zero onboarding and table-start guidance stay attached to the same governed campaign truth.",
                        ArtifactId: StableId("primer", targetCampaign.CampaignId))
                ],
                SnapshotIds = dossier.SnapshotIds.Concat([continuity.SnapshotId]).Distinct(StringComparer.OrdinalIgnoreCase).ToArray(),
                UpdatedAtUtc = now
            };
            _store.DossiersById[transferredDossier.DossierId] = transferredDossier;

            var receipt = new RosterTransferProjection(
                TransferId: StableId("transfer", $"{transferredDossier.DossierId}:{targetCampaign.CampaignId}:{now.ToUnixTimeSeconds()}"),
                DossierId: transferredDossier.DossierId,
                RunnerHandle: transferredDossier.RunnerHandle,
                PreviousOwnerUserId: previousOwnerUserId,
                CurrentOwnerUserId: currentOwnerUserId,
                SourceGroupId: sourceGroup.GroupId,
                SourceGroupName: sourceGroup.Name,
                SourceCampaignId: sourceCampaign.CampaignId,
                SourceCampaignName: sourceCampaign.Name,
                SourceCrewId: sourceCrew?.CrewId ?? ResolveCrewIdLocked(sourceCampaign.CampaignId),
                SourceCrewName: sourceCrew?.Name ?? $"{sourceGroup.Name} crew",
                TargetGroupId: targetGroup.GroupId,
                TargetGroupName: targetGroup.Name,
                TargetCampaignId: targetCampaign.CampaignId,
                TargetCampaignName: targetCampaign.Title,
                TargetCrewId: targetCrewId,
                TargetCrewName: targetCrew?.Name ?? $"{targetGroup.Name} crew",
                InitiatedByUserId: requester.UserId,
                Summary: string.Equals(previousOwnerUserId, currentOwnerUserId, StringComparison.OrdinalIgnoreCase)
                    ? $"{transferredDossier.DisplayName} moved from {sourceCampaign.Name} into {targetCampaign.Title} without losing governed ownership.{note}"
                    : $"{transferredDossier.DisplayName} moved from {sourceCampaign.Name} into {targetCampaign.Title}, and ownership transferred to {currentOwner.DisplayName}.{note}",
                AuditLines:
                [
                    $"{requester.DisplayName} initiated the move from {sourceGroup.Name} to {targetGroup.Name}.",
                    $"Campaign return now pins {transferredDossier.DisplayName} to {targetCampaign.Title}.",
                    string.Equals(previousOwnerUserId, currentOwnerUserId, StringComparison.OrdinalIgnoreCase)
                        ? $"Ownership stayed with {currentOwner.DisplayName} while roster and campaign assignment changed."
                        : $"Ownership moved from {previousOwner?.DisplayName ?? previousOwnerUserId} to {currentOwner.DisplayName} with the same dossier id preserved."
                ],
                Receipts:
                [
                    new CampaignConsequenceReceipt(
                        ReceiptId: sourceGroup.GroupId,
                        SourceKind: "source_group",
                        Summary: sourceGroup.Name),
                    new CampaignConsequenceReceipt(
                        ReceiptId: targetGroup.GroupId,
                        SourceKind: "target_group",
                        Summary: targetGroup.Name),
                    new CampaignConsequenceReceipt(
                        ReceiptId: sourceCampaign.CampaignId,
                        SourceKind: "source_campaign",
                        Summary: sourceCampaign.Name),
                    new CampaignConsequenceReceipt(
                        ReceiptId: targetCampaign.CampaignId,
                        SourceKind: "target_campaign",
                        Summary: targetCampaign.Title),
                    new CampaignConsequenceReceipt(
                        ReceiptId: continuity.SnapshotId,
                        SourceKind: "continuity",
                        Summary: continuity.Summary)
                ],
                TransferredAtUtc: now);
            _store.RosterTransfers.RemoveAll(item => string.Equals(item.TransferId, receipt.TransferId, StringComparison.OrdinalIgnoreCase));
            _store.RosterTransfers.Add(receipt);

            if (previousOwner is not null)
            {
                EnsureCampaignsLocked(previousOwner, now);
            }

            if (!string.Equals(previousOwnerUserId, currentOwnerUserId, StringComparison.OrdinalIgnoreCase))
            {
                EnsureCampaignsLocked(currentOwner, now);
            }

            _store.PersistLocked();
            return receipt;
        }
    }

    private static CampaignWorkspaceDigestProjection BuildWorkspaceDigest(
        AccountCampaignSummary summary,
        CampaignWorkspaceProjection workspace)
    {
        BuildLabHandoffProjection? leadHandoff = summary.BuildLabHandoffs
            .Where(handoff => string.Equals(handoff.CampaignId, workspace.CampaignId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static handoff => handoff.UpdatedAtUtc)
            .FirstOrDefault();
        RulesNavigatorAnswerProjection? leadRulesAnswer = summary.RulesNavigator.FirstOrDefault();

        string ruleEnvironmentSummary = $"{workspace.RuleEnvironment.OwnerScope} · {workspace.RuleEnvironment.ApprovalState} · {workspace.RuleEnvironment.CompatibilityFingerprint}";
        string deviceRoleSummary = summary.Restore.ClaimedDevices.Count == 0
            ? "No claimed device role is attached yet."
            : string.Join(
                "; ",
                summary.Restore.ClaimedDevices
                    .Take(2)
                    .Select(static item => $"{item.DeviceRole} on {item.Platform}/{item.HeadId} ({item.Channel})"));
        string supportClosureSummary = !string.IsNullOrWhiteSpace(leadHandoff?.SupportClosureSummary)
            ? leadHandoff.SupportClosureSummary!
            : leadRulesAnswer?.SupportReuseHints.FirstOrDefault(static hint => !string.IsNullOrWhiteSpace(hint))
              ?? "Support closure stays aligned with the claimed install, current channel, and the workspace you reopen here.";

        List<string> readinessHighlights = [];
        readinessHighlights.AddRange(
            workspace.ReadinessCues
                .Take(3)
                .Select(static cue => $"{cue.Title} — {cue.Summary}"));
        readinessHighlights.AddRange(
            workspace.ChangePackets?
                .Take(2)
                .Select(static packet => $"{packet.Label} — {packet.Summary}")
            ?? []);
        if (workspace.NextSessionCarryForward is not null)
        {
            readinessHighlights.Add($"Next session — {workspace.NextSessionCarryForward.Summary}");
        }
        if (workspace.FirstPlayableSession is not null)
        {
            readinessHighlights.Add($"First playable session — {workspace.FirstPlayableSession.Summary}");
            readinessHighlights.AddRange(
                workspace.FirstPlayableSession.EvidenceLines
                    .Take(2)
                    .Select(static line => $"First-session evidence — {line}"));
        }
        readinessHighlights.AddRange(
            workspace.Consequences?
                .Take(2)
                .Select(static consequence => $"{consequence.Label} — {consequence.Summary}")
            ?? []);
        readinessHighlights.AddRange(
            workspace.RosterTransfers?
                .Take(2)
                .Select(static transfer => $"Roster transfer — {transfer.Summary}")
            ?? []);
        if (!string.IsNullOrWhiteSpace(leadHandoff?.CampaignReturnSummary))
        {
            readinessHighlights.Add($"Build handoff — {leadHandoff.CampaignReturnSummary}");
        }
        if (workspace.CampaignMemory is not null)
        {
            readinessHighlights.Add($"Campaign memory — {workspace.CampaignMemory.Summary}");
            readinessHighlights.AddRange(
                workspace.CampaignMemory.EvidenceLines
                    .Take(2)
                    .Select(static line => $"Campaign memory evidence — {line}"));
        }

        List<string> watchouts = [];
        watchouts.AddRange(
            workspace.ReadinessCues
                .Where(static cue => NeedsAttention(cue.Severity))
                .Select(static cue => $"{cue.Title}: {cue.Summary}"));
        watchouts.AddRange(summary.Restore.ConflictSummaries);
        watchouts.AddRange(summary.Restore.LocalOnlyNotes);
        if (leadHandoff?.Watchouts is not null)
        {
            watchouts.AddRange(leadHandoff.Watchouts);
        }

        DateTimeOffset updatedAtUtc = new[]
            {
                workspace.LatestContinuity?.CapturedAtUtc,
                leadHandoff?.UpdatedAtUtc,
                workspace.CampaignMemory?.UpdatedAtUtc,
                workspace.RosterTransfers?.FirstOrDefault()?.TransferredAtUtc,
                summary.Restore.GeneratedAtUtc
            }
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(summary.Restore.GeneratedAtUtc)
            .Max();

        return new CampaignWorkspaceDigestProjection(
            WorkspaceId: workspace.WorkspaceId,
            CampaignId: workspace.CampaignId,
            CampaignName: workspace.CampaignName,
            ReturnSummary: workspace.ReturnSummary,
            RuleEnvironmentSummary: ruleEnvironmentSummary,
            DeviceRoleSummary: deviceRoleSummary,
            SupportClosureSummary: supportClosureSummary,
            ActiveSceneSummary: workspace.ActiveSceneSummary,
            NextSafeAction: workspace.NextSafeAction ?? "Reopen the current campaign workspace before creating another local-only fork.",
            ReadinessHighlights: FinalizeLines(readinessHighlights),
            Watchouts: FinalizeLines(watchouts),
            UpdatedAtUtc: updatedAtUtc,
            FirstPlayableSession: workspace.FirstPlayableSession,
            CampaignMemory: workspace.CampaignMemory);
    }

    private static bool CanManageRosterGroup(GroupDto group, string userId)
        => string.Equals(group.OwnerUserId, userId, StringComparison.OrdinalIgnoreCase)
            || group.Memberships.Any(member =>
                string.Equals(member.UserId, userId, StringComparison.OrdinalIgnoreCase)
                && IsOperatorRole(member.Role));

    private string ResolveSuggestedTransferCampaignTitleLocked(GroupDto targetGroup)
    {
        var activeCampaign = _store.CampaignsById.Values
            .Where(item => string.Equals(item.GroupId, targetGroup.GroupId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.Status, "active", StringComparison.OrdinalIgnoreCase))
            .OrderBy(static item => item.CreatedAtUtc)
            .ThenBy(static item => item.CampaignId, StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault();
        return activeCampaign?.Title ?? $"{targetGroup.Name} transfer campaign";
    }

    private BoostCampaignDto ResolveOrCreateTransferCampaignLocked(
        GroupDto targetGroup,
        string? targetCampaignId,
        string? targetCampaignTitle,
        DateTimeOffset now)
    {
        string? normalizedCampaignId = AccountService.NormalizeOptional(targetCampaignId);
        if (normalizedCampaignId is not null)
        {
            var existing = _store.CampaignsById.GetValueOrDefault(normalizedCampaignId)
                ?? throw new KeyNotFoundException($"Unknown target campaign: {normalizedCampaignId}");
            if (!string.Equals(existing.GroupId, targetGroup.GroupId, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidOperationException("target campaign does not belong to the requested target group.");
            }

            return existing;
        }

        var activeCampaign = _store.CampaignsById.Values
            .Where(item => string.Equals(item.GroupId, targetGroup.GroupId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.Status, "active", StringComparison.OrdinalIgnoreCase))
            .OrderBy(static item => item.CreatedAtUtc)
            .ThenBy(static item => item.CampaignId, StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault();
        if (activeCampaign is not null)
        {
            return activeCampaign;
        }

        var created = new BoostCampaignDto(
            CampaignId: AccountService.NewId("cmp"),
            GroupId: targetGroup.GroupId,
            ProjectId: "campaign-roster-transfer",
            Title: string.IsNullOrWhiteSpace(targetCampaignTitle)
                ? ResolveSuggestedTransferCampaignTitleLocked(targetGroup)
                : targetCampaignTitle.Trim(),
            Status: "active",
            CreatedAtUtc: now);
        _store.CampaignsById[created.CampaignId] = created;
        return created;
    }

    private bool EnsureSeedDataLocked(HubUserDto user, InstallLinkingSummaryDto? installLinking, DateTimeOffset now)
    {
        var changed = false;
        changed |= EnsurePersonalDossierLocked(user, now);
        changed |= EnsureCampaignsLocked(user, now);

        var dossiers = _store.DossiersById.Values
            .Where(item => string.Equals(item.OwnerUserId, user.UserId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
        var campaigns = _store.CampaignSpinesById.Values
            .Where(item => item.DossierIds.Any(dossierId => dossiers.Any(dossier => string.Equals(dossier.DossierId, dossierId, StringComparison.OrdinalIgnoreCase))))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
        _store.RestoreByUserId.TryGetValue(user.UserId, out var existingRestore);
        var restore = _lifecyclePolicy.FinalizeRestoreProjection(
            existingRestore,
            BuildRestoreProjection(user, dossiers, campaigns, installLinking, now),
            now);
        if (!ContentEquals(existingRestore, restore))
        {
            _store.RestoreByUserId[user.UserId] = restore;
            changed = true;
        }

        return changed;
    }

    private bool EnsurePersonalDossierLocked(HubUserDto user, DateTimeOffset now)
    {
        if (_store.DossiersById.Values.Any(item => string.Equals(item.OwnerUserId, user.UserId, StringComparison.OrdinalIgnoreCase)))
        {
            return false;
        }

        var dossierId = AccountService.NewId("dos");
        _store.DossiersById[dossierId] = new RunnerDossierProjection(
            DossierId: dossierId,
            RunnerHandle: user.Handle,
            DisplayName: $"{user.DisplayName} dossier",
            Status: DossierStatuses.Active,
            OwnerUserId: user.UserId,
            CrewId: null,
            CampaignId: null,
            CurrentRunId: null,
            CurrentSceneId: null,
            RuleEnvironment: DefaultRuleEnvironment($"person:{user.UserId}", "person"),
            LatestContinuity: new ContinuitySnapshotRef(
                SnapshotId: StableId("snapshot", user.UserId),
                CapturedAtUtc: now,
                Summary: "Living dossier shell created and ready for campaign continuity.",
                RestoreState: "ready"),
            BuildReceiptIds: Array.Empty<string>(),
            SnapshotIds: new[] { StableId("snapshot", user.UserId) },
            Projections:
            [
                new PublicationSafeProjection(
                    ProjectionId: StableId("projection", user.UserId),
                    Kind: "dossier_card",
                    Label: "Living dossier",
                    Summary: "Stable runner identity that can survive build, play, recap, and return.")
            ],
            CreatedAtUtc: now,
            UpdatedAtUtc: now);
        return true;
    }

    private bool EnsureCampaignsLocked(HubUserDto user, DateTimeOffset now)
    {
        var changed = false;
        var memberGroups = _store.GroupsById.Values
            .Where(group => group.Memberships.Any(member => string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)))
            .ToArray();
        var sponsorCampaigns = _store.CampaignsById.Values
            .Where(item => memberGroups.Any(group => string.Equals(group.GroupId, item.GroupId, StringComparison.OrdinalIgnoreCase)))
            .OrderBy(static item => item.CreatedAtUtc)
            .ThenBy(static item => item.CampaignId, StringComparer.OrdinalIgnoreCase)
            .ToArray();

        if (sponsorCampaigns.Length == 0)
        {
            changed |= EnsurePersonalPreviewCampaignLocked(user, now);
            memberGroups = _store.GroupsById.Values
                .Where(group => group.Memberships.Any(member => string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)))
                .ToArray();
            sponsorCampaigns = _store.CampaignsById.Values
                .Where(item => memberGroups.Any(group => string.Equals(group.GroupId, item.GroupId, StringComparison.OrdinalIgnoreCase)))
                .OrderBy(static item => item.CreatedAtUtc)
                .ThenBy(static item => item.CampaignId, StringComparer.OrdinalIgnoreCase)
                .ToArray();
        }

        foreach (var sponsorCampaign in sponsorCampaigns)
        {
            if (!_store.GroupsById.TryGetValue(sponsorCampaign.GroupId, out var group))
            {
                continue;
            }

            var crewId = ResolveCrewIdLocked(sponsorCampaign.CampaignId);
            var runId = StableId("run", sponsorCampaign.CampaignId);
            var sceneId = StableId("scene", sponsorCampaign.CampaignId);
            var objectiveId = StableId("obj", sponsorCampaign.CampaignId);
            var continuity = new ContinuitySnapshotRef(
                SnapshotId: StableId("snapshot", sponsorCampaign.CampaignId),
                CapturedAtUtc: sponsorCampaign.CreatedAtUtc,
                Summary: $"Campaign continuity is tracked for {sponsorCampaign.Title}.",
                RestoreState: "synced",
                SessionId: runId,
                SceneId: sceneId,
                RecapArtifactId: StableId("recap", sponsorCampaign.CampaignId));
            var memberDetails = group.Memberships
                .Select(member =>
                {
                    var userRecord = _store.UsersById.GetValueOrDefault(member.UserId);
                    if (userRecord is null)
                    {
                        return (Assignment: (CrewAssignmentProjection?)null, Dossier: (RunnerDossierProjection?)null);
                    }

                    var dossier = EnsureMemberDossierLocked(userRecord, sponsorCampaign.CampaignId, crewId, runId, sceneId, sponsorCampaign.Title, now);
                    return (
                        Assignment: new CrewAssignmentProjection(
                            UserId: member.UserId,
                            DossierId: dossier.DossierId,
                            Role: member.Role,
                            Availability: "active",
                            AddedAtUtc: member.JoinedAtUtc),
                        Dossier: dossier);
                })
                .Where(static detail => detail.Assignment is not null && detail.Dossier is not null)
                .ToArray();
            var memberAssignments = memberDetails
                .Select(static detail => detail.Assignment!)
                .ToArray();
            var memberDossiers = memberDetails
                .Select(static detail => detail.Dossier!)
                .GroupBy(static dossier => dossier.DossierId, StringComparer.OrdinalIgnoreCase)
                .Select(static group => group.First())
                .ToArray();

            if (memberAssignments.Length == 0)
            {
                continue;
            }

            var crew = new CrewProjection(
                CrewId: crewId,
                Name: $"{group.Name} crew",
                Visibility: group.Visibility,
                GroupId: group.GroupId,
                CampaignId: sponsorCampaign.CampaignId,
                Members: memberAssignments,
                CreatedAtUtc: sponsorCampaign.CreatedAtUtc,
                UpdatedAtUtc: _store.CrewsById.TryGetValue(crewId, out var existingCrew) ? existingCrew.UpdatedAtUtc : now);
            if (existingCrew is null || !ContentEquals(existingCrew, crew))
            {
                crew = existingCrew is null ? crew : crew with { UpdatedAtUtc = now };
                _store.CrewsById[crewId] = crew;
                changed = true;
            }

            var run = new RunProjection(
                RunId: runId,
                CampaignId: sponsorCampaign.CampaignId,
                Title: $"{sponsorCampaign.Title} kickoff",
                Status: RunStatuses.Active,
                Summary: "Briefing, planning, and first-contact continuity for the active campaign.",
                ActiveSceneId: sceneId,
                Objectives:
                [
                    new ObjectiveProjection(
                        ObjectiveId: objectiveId,
                        Title: "Keep the crew aligned",
                        Status: "open",
                        Pressure: "medium",
                        Summary: "Use the same dossier, rule environment, and recap spine across surfaces.",
                        UpdatedAtUtc: _store.RunsById.TryGetValue(runId, out var existingRunForObjective)
                            ? existingRunForObjective.Objectives.FirstOrDefault(item => string.Equals(item.ObjectiveId, objectiveId, StringComparison.OrdinalIgnoreCase))?.UpdatedAtUtc ?? now
                            : now)
                ],
                Scenes:
                [
                    new SceneProjection(
                        SceneId: sceneId,
                        RunId: runId,
                        Title: "Campaign brief",
                        Revision: "r1",
                        Status: "active",
                        Summary: "Shared entry scene for planning, continuity, and handoff.",
                        UpdatedAtUtc: existingRunForObjective is not null
                            ? existingRunForObjective.Scenes.FirstOrDefault(item => string.Equals(item.SceneId, sceneId, StringComparison.OrdinalIgnoreCase))?.UpdatedAtUtc ?? now
                            : now)
                ],
                LatestContinuity: continuity,
                CreatedAtUtc: sponsorCampaign.CreatedAtUtc,
                UpdatedAtUtc: existingRunForObjective?.UpdatedAtUtc ?? now);
            if (existingRunForObjective is null || !ContentEquals(existingRunForObjective, run))
            {
                run = existingRunForObjective is null ? run : run with { UpdatedAtUtc = now };
                _store.RunsById[runId] = run;
                changed = true;
            }

            var campaign = new CampaignProjection(
                CampaignId: sponsorCampaign.CampaignId,
                GroupId: sponsorCampaign.GroupId,
                Name: sponsorCampaign.Title,
                Status: CampaignStatuses.Active,
                Visibility: group.Visibility,
                Summary: "Campaign continuity, roster posture, and shared rule environment live together here.",
                RuleEnvironment: DefaultRuleEnvironment($"campaign:{sponsorCampaign.CampaignId}", "campaign"),
                ActiveRunId: runId,
                CrewIds: new[] { crewId },
                DossierIds: memberAssignments.Select(static item => item.DossierId).Distinct(StringComparer.OrdinalIgnoreCase).ToArray(),
                RunIds: new[] { runId },
                LatestContinuity: continuity,
                CreatedAtUtc: sponsorCampaign.CreatedAtUtc,
                UpdatedAtUtc: _store.CampaignSpinesById.TryGetValue(sponsorCampaign.CampaignId, out var existingCampaign) ? existingCampaign.UpdatedAtUtc : now,
                Consequences: BuildCampaignConsequences(
                    sponsorCampaign,
                    group,
                    crew,
                    memberDossiers,
                    run,
                    continuity));
            if (existingCampaign is null || !ContentEquals(existingCampaign, campaign))
            {
                campaign = existingCampaign is null ? campaign : campaign with { UpdatedAtUtc = now };
                _store.CampaignSpinesById[campaign.CampaignId] = campaign;
                changed = true;
            }
        }

        return changed;
    }

    private bool EnsurePersonalPreviewCampaignLocked(HubUserDto user, DateTimeOffset now)
    {
        var changed = false;
        var groupId = StableId("group", $"personal-preview:{user.UserId}");
        var campaignId = StableId("campaign", $"personal-preview:{user.UserId}");
        var seasonCampaignId = StableId("campaign", $"personal-preview:{user.UserId}:season");
        var membership = new GroupMembershipDto(
            MembershipId: StableId("membership", $"personal-preview:{user.UserId}"),
            GroupId: groupId,
            UserId: user.UserId,
            Role: "gm",
            JoinedAtUtc: user.CreatedAtUtc);

        if (!_store.GroupsById.TryGetValue(groupId, out var existingGroup))
        {
            _store.GroupsById[groupId] = new GroupDto(
                GroupId: groupId,
                GroupType: "campaign",
                Name: $"{user.DisplayName} preview crew",
                Visibility: "private",
                OwnerUserId: user.UserId,
                Capabilities: DefaultPersonalPreviewCapabilities,
                Memberships: [membership],
                CreatedAtUtc: now,
                UpdatedAtUtc: now);
            changed = true;
        }
        else
        {
            bool missingMembership = existingGroup.Memberships.All(member => !string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase));
            bool missingCapabilities = DefaultPersonalPreviewCapabilities.Except(existingGroup.Capabilities, StringComparer.OrdinalIgnoreCase).Any();
            if (missingMembership || missingCapabilities)
            {
                _store.GroupsById[groupId] = existingGroup with
                {
                    Memberships = missingMembership
                        ? existingGroup.Memberships.Concat([membership]).ToArray()
                        : existingGroup.Memberships,
                    Capabilities = missingCapabilities
                        ? existingGroup.Capabilities.Concat(DefaultPersonalPreviewCapabilities).Distinct(StringComparer.OrdinalIgnoreCase).ToArray()
                        : existingGroup.Capabilities,
                    UpdatedAtUtc = now
                };
                changed = true;
            }
        }

        if (_store.UsersById.TryGetValue(user.UserId, out var existingUser)
            && existingUser.GroupIds.All(group => !string.Equals(group, groupId, StringComparison.OrdinalIgnoreCase)))
        {
            _store.UsersById[user.UserId] = existingUser with
            {
                GroupIds = existingUser.GroupIds.Concat([groupId]).Distinct(StringComparer.OrdinalIgnoreCase).ToArray(),
                UpdatedAtUtc = now
            };
            changed = true;
        }

        if (!_store.CampaignsById.ContainsKey(campaignId))
        {
            _store.CampaignsById[campaignId] = new BoostCampaignDto(
                CampaignId: campaignId,
                GroupId: groupId,
                ProjectId: "campaign-os-preview",
                Title: $"{user.DisplayName} preview campaign",
                Status: "active",
                CreatedAtUtc: now);
            changed = true;
        }

        if (!_store.CampaignsById.ContainsKey(seasonCampaignId))
        {
            _store.CampaignsById[seasonCampaignId] = new BoostCampaignDto(
                CampaignId: seasonCampaignId,
                GroupId: groupId,
                ProjectId: "campaign-os-preview-season",
                Title: $"{user.DisplayName} preview season",
                Status: "active",
                CreatedAtUtc: now.AddMinutes(1));
            changed = true;
        }

        return changed;
    }

    private RunnerDossierProjection EnsureMemberDossierLocked(
        HubUserDto user,
        string campaignId,
        string crewId,
        string runId,
        string sceneId,
        string campaignTitle,
        DateTimeOffset now)
    {
        var existing = _store.DossiersById.Values.FirstOrDefault(item =>
                string.Equals(item.OwnerUserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.CampaignId, campaignId, StringComparison.OrdinalIgnoreCase))
            ?? _store.DossiersById.Values.FirstOrDefault(item =>
                string.Equals(item.OwnerUserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                && string.IsNullOrWhiteSpace(item.CampaignId));
        DateTimeOffset continuityCapturedAt = existing is not null
            && string.Equals(existing.CampaignId, campaignId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(existing.CurrentRunId, runId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(existing.CurrentSceneId, sceneId, StringComparison.OrdinalIgnoreCase)
            ? existing.LatestContinuity?.CapturedAtUtc ?? now
            : now;
        var continuity = new ContinuitySnapshotRef(
            SnapshotId: StableId("snapshot", $"{user.UserId}:{campaignId}"),
            CapturedAtUtc: continuityCapturedAt,
            Summary: $"Attached to {campaignTitle} with replay-safe continuity.",
            RestoreState: "campaign_bound",
            SessionId: runId,
            SceneId: sceneId,
            RecapArtifactId: StableId("recap", campaignId));

        if (existing is null)
        {
            string newDossierId = AccountService.NewId("dos");
            existing = new RunnerDossierProjection(
                DossierId: newDossierId,
                RunnerHandle: user.Handle,
                DisplayName: $"{user.DisplayName} dossier",
                Status: DossierStatuses.Active,
                OwnerUserId: user.UserId,
                CrewId: crewId,
                CampaignId: campaignId,
                CurrentRunId: runId,
                CurrentSceneId: sceneId,
                RuleEnvironment: DefaultRuleEnvironment($"campaign:{campaignId}", "campaign"),
                LatestContinuity: continuity,
                BuildReceiptIds: Array.Empty<string>(),
                SnapshotIds: new[] { continuity.SnapshotId },
                Projections:
                [
                    new PublicationSafeProjection(
                        ProjectionId: StableId("projection", $"{user.UserId}:{campaignId}"),
                        Kind: "campaign_recap",
                        Label: "Campaign-ready dossier",
                        Summary: "This runner can move through build, play, recap, and return without losing identity.",
                        ArtifactId: continuity.RecapArtifactId),
                    new PublicationSafeProjection(
                        ProjectionId: StableId("projection", $"{user.UserId}:{campaignId}:dossier"),
                        Kind: "dossier_card",
                        Label: "Living dossier packet",
                        Summary: "Living dossier truth, campaign continuity, and governed publication detail stay attached to one shared artifact lane.",
                        ArtifactId: newDossierId),
                    new PublicationSafeProjection(
                        ProjectionId: StableId("projection", $"{user.UserId}:{campaignId}:ops"),
                        Kind: "runboard_packet",
                        Label: "Runboard continuity packet",
                        Summary: "GM-facing continuity and recap-safe state for the active campaign return.",
                        ArtifactId: StableId("ops", campaignId)),
                    new PublicationSafeProjection(
                        ProjectionId: StableId("projection", $"{user.UserId}:{campaignId}:primer"),
                        Kind: "player_primer",
                        Label: "Campaign primer",
                        Summary: "Session-zero onboarding and table-start guidance stay attached to the same governed campaign truth.",
                        ArtifactId: StableId("primer", campaignId))
                ],
                CreatedAtUtc: now,
                UpdatedAtUtc: now);
        }
        else
        {
            RunnerDossierProjection candidate = existing with
            {
                CrewId = crewId,
                CampaignId = campaignId,
                CurrentRunId = runId,
                CurrentSceneId = sceneId,
                RuleEnvironment = DefaultRuleEnvironment($"campaign:{campaignId}", "campaign"),
                LatestContinuity = continuity,
                Projections =
                [
                    new PublicationSafeProjection(
                        ProjectionId: StableId("projection", $"{user.UserId}:{campaignId}"),
                        Kind: "campaign_recap",
                        Label: "Campaign-ready dossier",
                        Summary: "This runner can move through build, play, recap, and return without losing identity.",
                        ArtifactId: continuity.RecapArtifactId),
                    new PublicationSafeProjection(
                        ProjectionId: StableId("projection", $"{user.UserId}:{campaignId}:dossier"),
                        Kind: "dossier_card",
                        Label: "Living dossier packet",
                        Summary: "Living dossier truth, campaign continuity, and governed publication detail stay attached to one shared artifact lane.",
                        ArtifactId: existing.DossierId),
                    new PublicationSafeProjection(
                        ProjectionId: StableId("projection", $"{user.UserId}:{campaignId}:ops"),
                        Kind: "runboard_packet",
                        Label: "Runboard continuity packet",
                        Summary: "GM-facing continuity and recap-safe state for the active campaign return.",
                        ArtifactId: StableId("ops", campaignId)),
                    new PublicationSafeProjection(
                        ProjectionId: StableId("projection", $"{user.UserId}:{campaignId}:primer"),
                        Kind: "player_primer",
                        Label: "Campaign primer",
                        Summary: "Session-zero onboarding and table-start guidance stay attached to the same governed campaign truth.",
                        ArtifactId: StableId("primer", campaignId))
                ],
                SnapshotIds = existing.SnapshotIds.Concat(new[] { continuity.SnapshotId }).Distinct(StringComparer.OrdinalIgnoreCase).ToArray(),
                UpdatedAtUtc = existing.UpdatedAtUtc
            };

            existing = ContentEquals(existing, candidate)
                ? existing
                : candidate with { UpdatedAtUtc = now };
        }

        _store.DossiersById[existing.DossierId] = existing;
        return existing;
    }

    private string ResolveCrewIdLocked(string campaignId)
        => _store.CrewsById.Values
            .Where(item => string.Equals(item.CampaignId, campaignId, StringComparison.OrdinalIgnoreCase))
            .Select(static item => item.CrewId)
            .FirstOrDefault()
            ?? StableId("crew", campaignId);

    private static WorkspaceRestoreProjection BuildRestoreProjection(
        HubUserDto user,
        IReadOnlyList<RunnerDossierProjection> dossiers,
        IReadOnlyList<CampaignProjection> campaigns,
        InstallLinkingSummaryDto? installLinking,
        DateTimeOffset generatedAtUtc)
    {
        var conflictSummaries = new List<string>();
        var claimedInstallations = installLinking?.ClaimedInstallations ?? Array.Empty<ClaimedInstallationDto>();
        var activeGrants = installLinking?.ActiveGrants ?? Array.Empty<InstallationGrantDto>();
        if (claimedInstallations.Select(item => item.Channel).Where(static item => !string.IsNullOrWhiteSpace(item)).Distinct(StringComparer.OrdinalIgnoreCase).Count() > 1)
        {
            conflictSummaries.Add("Claimed installs are on different channels; restore should confirm which campaign posture is current.");
        }

        var ruleEnvironments = dossiers
            .Select(static dossier => dossier.RuleEnvironment)
            .Concat(campaigns.Select(static campaign => campaign.RuleEnvironment))
            .Distinct()
            .Take(6)
            .ToArray();
        if (ruleEnvironments.Select(static environment => environment.CompatibilityFingerprint).Distinct(StringComparer.OrdinalIgnoreCase).Count() > 1)
        {
            conflictSummaries.Add("Recent dossiers and campaigns carry different rule-environment fingerprints; restore should confirm the intended rules posture before applying sync.");
        }

        var recentArtifacts = (installLinking?.RecentReceipts ?? Array.Empty<DownloadReceiptDto>())
            .Where(static item => !string.IsNullOrWhiteSpace(item.ArtifactId))
            .Select(static item => new RestoreArtifactProjection(
                ArtifactId: item.ArtifactId,
                Label: item.ArtifactLabel,
                Kind: item.Kind,
                Summary: $"{item.Channel} {item.Version} for {item.Platform}/{item.Arch} remains reconnectable from the signed-in restore packet.",
                Channel: item.Channel,
                Version: item.Version))
            .Distinct()
            .Take(5)
            .ToArray();

        var entitlements = activeGrants
            .Select(grant =>
            {
                var installation = claimedInstallations.FirstOrDefault(item => string.Equals(item.InstallationId, grant.InstallationId, StringComparison.OrdinalIgnoreCase));
                var label = installation?.HostLabel ?? installation?.Platform ?? grant.InstallationId;
                var scope = installation?.HeadId ?? "desktop";
                return new RestoreEntitlementProjection(
                    EntitlementId: grant.GrantId,
                    Label: label,
                    Scope: scope,
                    Status: grant.Status,
                    Summary: $"Restore can re-establish {scope} access for {label} until {grant.ExpiresAtUtc:yyyy-MM-dd}.");
            })
            .ToArray();

        var claimedDevices = claimedInstallations
            .Select(installation =>
            {
                string deviceRole = ResolveDeviceRole(installation);
                return new ClaimedDeviceRestoreProjection(
                    InstallationId: installation.InstallationId,
                    DeviceRole: deviceRole,
                    Platform: installation.Platform ?? "unknown",
                    HeadId: installation.HeadId ?? "desktop",
                    Channel: installation.Channel,
                    HostLabel: installation.HostLabel,
                    RestoreSummary: BuildClaimedDeviceRestoreSummary(
                        installation,
                        deviceRole,
                        dossiers,
                        campaigns,
                        ruleEnvironments,
                        recentArtifacts));
            })
            .Take(4)
            .ToArray();

        return new WorkspaceRestoreProjection(
            RestoreId: StableId("restore", user.UserId),
            UserId: user.UserId,
            RecentDossiers: dossiers.Take(3).ToArray(),
            RecentCampaigns: campaigns.Take(3).ToArray(),
            RecentRuleEnvironments: ruleEnvironments,
            RecentArtifacts: recentArtifacts,
            Entitlements: entitlements,
            ClaimedDevices: claimedDevices,
            ConflictSummaries: conflictSummaries,
            LocalOnlyNotes:
            [
                "Secrets, grant tokens, and runtime caches stay install-local and are never mirrored into the roaming restore packet.",
                "Second-device restore replays dossiers, campaigns, rule environments, artifacts, and entitlements, but it still asks the target device to mint its own local cache and observer continuity token."
            ],
            GeneratedAtUtc: generatedAtUtc);
    }

    private static string BuildClaimedDeviceRestoreSummary(
        ClaimedInstallationDto installation,
        string deviceRole,
        IReadOnlyList<RunnerDossierProjection> dossiers,
        IReadOnlyList<CampaignProjection> campaigns,
        IReadOnlyList<RuleEnvironmentRef> ruleEnvironments,
        IReadOnlyList<RestoreArtifactProjection> recentArtifacts)
    {
        string baseSummary = $"{installation.Platform ?? "unknown"} · {installation.HeadId ?? "desktop"} · {installation.Version}";
        string inventory = DescribeRestorePrefetchInventory(dossiers.Count, campaigns.Count, ruleEnvironments.Count, recentArtifacts.Count);
        string laneSummary = string.Equals(deviceRole, "travel_cache", StringComparison.OrdinalIgnoreCase)
            ? "Travel-safe cache keeps"
            : "Claimed-device return keeps";
        string exactSet = DescribeRestorePrefetchSet(dossiers, campaigns, ruleEnvironments, recentArtifacts);
        return string.IsNullOrWhiteSpace(exactSet)
            ? $"{baseSummary}. {laneSummary} {inventory} ready for bounded offline use."
            : $"{baseSummary}. {laneSummary} {inventory} ready for bounded offline use. Exact set: {exactSet}.";
    }

    private static string DescribeRestorePrefetchInventory(
        int dossierCount,
        int campaignCount,
        int ruleEnvironmentCount,
        int artifactCount)
        => $"{dossierCount} dossier(s), {campaignCount} campaign(s), {ruleEnvironmentCount} rule snapshot(s), and {artifactCount} reconnectable artifact(s)";

    private static string DescribeRestorePrefetchSet(
        IReadOnlyList<RunnerDossierProjection> dossiers,
        IReadOnlyList<CampaignProjection> campaigns,
        IReadOnlyList<RuleEnvironmentRef> ruleEnvironments,
        IReadOnlyList<RestoreArtifactProjection> recentArtifacts)
    {
        List<string> segments = [];

        if (dossiers.Count > 0)
        {
            segments.Add($"dossiers {string.Join(", ", dossiers.Take(3).Select(static dossier => $"{dossier.DisplayName} ({dossier.DossierId})"))}");
        }

        if (campaigns.Count > 0)
        {
            segments.Add($"campaigns {string.Join(", ", campaigns.Take(3).Select(static campaign => $"{campaign.Name} ({campaign.CampaignId})"))}");
        }

        if (ruleEnvironments.Count > 0)
        {
            segments.Add($"rules {string.Join(", ", ruleEnvironments.Take(3).Select(environment => $"{environment.CompatibilityFingerprint} [{DescribeRuleEnvironmentLifecycleStage(ResolveRuleEnvironmentLifecycleStage(environment)).ToLowerInvariant()}]"))}");
        }

        if (recentArtifacts.Count > 0)
        {
            segments.Add($"artifacts {string.Join(", ", recentArtifacts.Take(3).Select(static artifact => $"{artifact.Label} ({artifact.ArtifactId})"))}");
        }

        return string.Join("; ", segments);
    }

    private static RuleEnvironmentRef DefaultRuleEnvironment(string environmentId, string ownerScope)
        => new(
            EnvironmentId: StableId("ruleenv", environmentId),
            OwnerScope: ownerScope,
            CompatibilityFingerprint: "sr6.preview.v1",
            ApprovalState: string.Equals(ownerScope, "person", StringComparison.OrdinalIgnoreCase) ? "self_service" : "approved",
            SourcePacks: new[] { "shadowrun-6e-core@current" },
            HouseRulePacks: Array.Empty<string>(),
            OptionToggles: new[] { "explain_everywhere", "campaign_continuity" });

    private static CampaignWorkspaceProjection BuildWorkspaceProjection(
        CampaignProjection campaign,
        IReadOnlyList<RunnerDossierProjection> dossiers,
        IReadOnlyList<RunProjection> runs,
        IReadOnlyList<CrewProjection> crews,
        WorkspaceRestoreProjection restore,
        IReadOnlyList<RosterTransferProjection> transfers,
        IReadOnlyList<GovernedPrepLaunchProjection> prepLaunches,
        IReadOnlyList<TravelPrefetchReceiptProjection> travelPrefetchReceipts,
        IReadOnlyList<AftermathRecapPackageProjection> aftermathPackages)
    {
        var workspaceCrews = crews
            .Where(item => string.Equals(item.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase))
            .ToArray();
        var workspaceRuns = runs
            .Where(item => string.Equals(item.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
        var workspaceDossiers = dossiers
            .Where(item => string.Equals(item.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
        var rosterTransfers = transfers
            .Where(item => string.Equals(item.SourceCampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase)
                || string.Equals(item.TargetCampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.TransferredAtUtc)
            .ToArray();
        string workspaceId = StableId("workspace", campaign.CampaignId);
        var workspacePrepLaunches = prepLaunches
            .Where(item => string.Equals(item.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase)
                || string.Equals(item.WorkspaceId, workspaceId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.LaunchedAtUtc)
            .ToArray();
        var workspaceTravelPrefetches = travelPrefetchReceipts
            .Where(item => string.Equals(item.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase)
                || string.Equals(item.WorkspaceId, workspaceId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.StagedAtUtc)
            .ToArray();
        var workspaceAftermathPackages = aftermathPackages
            .Where(item => string.Equals(item.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase)
                || string.Equals(item.WorkspaceId, workspaceId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.GeneratedAtUtc)
            .ToArray();

        var readinessCues = new List<CampaignReadinessCue>();
        if (restore.ConflictSummaries.Count > 0)
        {
            readinessCues.Add(new CampaignReadinessCue(
                CueId: StableId("cue", $"{campaign.CampaignId}:restore"),
                Severity: "warning",
                Title: "Restore confirmation needed",
                Summary: restore.ConflictSummaries[0]));
        }

        string lifecycleStage = DescribeRuleEnvironmentLifecycleStage(ResolveRuleEnvironmentLifecycleStage(campaign.RuleEnvironment));
        if (!string.Equals(lifecycleStage, "Campaign-approved", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(lifecycleStage, "Published", StringComparison.OrdinalIgnoreCase))
        {
            readinessCues.Add(new CampaignReadinessCue(
                CueId: StableId("cue", $"{campaign.CampaignId}:ruleenv"),
                Severity: "review",
                Title: "Rule environment needs explicit review",
                Summary: $"{campaign.RuleEnvironment.OwnerScope} scope is on the {lifecycleStage.ToLowerInvariant()} rail for {campaign.RuleEnvironment.CompatibilityFingerprint}."));
        }
        else
        {
            readinessCues.Add(new CampaignReadinessCue(
                CueId: StableId("cue", $"{campaign.CampaignId}:ruleenv"),
                Severity: "ready",
                Title: $"Rule environment is {lifecycleStage}",
                Summary: $"{campaign.RuleEnvironment.OwnerScope} scope is pinned to {campaign.RuleEnvironment.CompatibilityFingerprint} on the {lifecycleStage.ToLowerInvariant()} rail."));
        }

        var openObjectives = workspaceRuns.SelectMany(static item => item.Objectives)
            .Where(item => !string.Equals(item.Status, "closed", StringComparison.OrdinalIgnoreCase)
                && !string.Equals(item.Status, "done", StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (openObjectives.Length > 0)
        {
            readinessCues.Add(new CampaignReadinessCue(
                CueId: StableId("cue", $"{campaign.CampaignId}:objectives"),
                Severity: "attention",
                Title: "Open runboard objectives",
                Summary: $"{openObjectives.Length} objective(s) still need attention before the next safe continue point."));
        }

        if (workspaceDossiers.Any(item => item.LatestContinuity is null))
        {
            readinessCues.Add(new CampaignReadinessCue(
                CueId: StableId("cue", $"{campaign.CampaignId}:continuity"),
                Severity: "warning",
                Title: "Continuity gap detected",
                Summary: "At least one dossier is missing the latest continuity snapshot for safe campaign return."));
        }

        var consequences = campaign.Consequences?
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray()
            ?? Array.Empty<CampaignConsequenceProjection>();
        if (consequences.Length > 0)
        {
            readinessCues.Add(new CampaignReadinessCue(
                CueId: StableId("cue", $"{campaign.CampaignId}:consequences"),
                Severity: "ready",
                Title: "Consequence ledger is attached",
                Summary: $"{consequences.Length} governed faction, heat, contact, and reputation signal(s) stay attached to the shared campaign view with receipt-backed evidence."));
        }
        if (rosterTransfers.Length > 0)
        {
            readinessCues.Add(new CampaignReadinessCue(
                CueId: StableId("cue", $"{campaign.CampaignId}:transfers"),
                Severity: "ready",
                Title: "Roster transfer audit is attached",
                Summary: $"{rosterTransfers.Length} recent dossier move(s) keep source, target, and ownership receipts attached to this campaign view."));
        }
        if (workspacePrepLaunches.Length > 0)
        {
            readinessCues.Add(new CampaignReadinessCue(
                CueId: StableId("cue", $"{campaign.CampaignId}:prep-launches"),
                Severity: "ready",
                Title: "Governed prep binding is attached",
                Summary: $"{workspacePrepLaunches.Length} recent packet launch receipt(s) keep opposition and scene prep bound to this campaign without recreating local shadow prep notes."));
        }
        if (workspaceTravelPrefetches.Length > 0)
        {
            readinessCues.Add(new CampaignReadinessCue(
                CueId: StableId("cue", $"{campaign.CampaignId}:travel-prefetch"),
                Severity: "ready",
                Title: "Travel prefetch is staged",
                Summary: $"{workspaceTravelPrefetches.Length} recent travel-prefetch receipt(s) keep the exact offline inventory deliberate and reviewable per claimed device."));
        }
        if (workspaceAftermathPackages.Length > 0)
        {
            readinessCues.Add(new CampaignReadinessCue(
                CueId: StableId("cue", $"{campaign.CampaignId}:aftermath"),
                Severity: "ready",
                Title: "Aftermath package rail is attached",
                Summary: $"{workspaceAftermathPackages.Length} governed aftermath package(s) keep return, replay review, and next-session carry-forward reviewable instead of falling back to prose alone."));
        }

        var recapShelf = workspaceAftermathPackages
            .Select(BuildAftermathRecapShelfProjection)
            .Concat(workspaceDossiers
            .SelectMany(static item => item.Projections)
            .Where(item => item.Kind.Contains("recap", StringComparison.OrdinalIgnoreCase)
                || item.Kind.Contains("runboard", StringComparison.OrdinalIgnoreCase)
                || item.Kind.Contains("primer", StringComparison.OrdinalIgnoreCase)
                || item.Kind.Contains("dossier", StringComparison.OrdinalIgnoreCase)))
            .Distinct()
            .ToArray();
        var leadRun = workspaceRuns.FirstOrDefault();
        var activeScene = leadRun is null ? null : ResolveActiveScene(leadRun);
        var leadObjective = leadRun?.Objectives
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault(item => !string.Equals(item.Status, "closed", StringComparison.OrdinalIgnoreCase)
                && !string.Equals(item.Status, "done", StringComparison.OrdinalIgnoreCase));
        var activeSceneSummary = DescribeActiveSceneSummary(leadRun, activeScene, leadObjective);
        var nextSafeAction = ResolveWorkspaceNextSafeAction(campaign, restore, recapShelf, readinessCues, leadRun, activeScene, leadObjective);
        var enrichedRecapShelf = EnrichWorkspaceRecapShelf(campaign, workspaceId, recapShelf, nextSafeAction);
        var firstPlayableSession = BuildFirstPlayableSession(campaign, restore, readinessCues, workspaceCrews, workspaceDossiers, leadRun, activeScene, leadObjective, nextSafeAction, workspacePrepLaunches, workspaceTravelPrefetches, workspaceAftermathPackages);
        var nextSessionCarryForward = BuildNextSessionCarryForward(campaign, nextSafeAction, leadRun, activeScene, leadObjective, consequences, workspacePrepLaunches, workspaceTravelPrefetches, workspaceAftermathPackages);
        var campaignMemory = BuildCampaignMemory(campaign, nextSafeAction, leadRun, activeScene, leadObjective, consequences, rosterTransfers, workspacePrepLaunches, workspaceTravelPrefetches, workspaceAftermathPackages, nextSessionCarryForward);
        var changePackets = BuildWorkspaceChangePackets(campaign, enrichedRecapShelf, leadRun, activeScene, leadObjective, rosterTransfers, workspacePrepLaunches, workspaceTravelPrefetches, workspaceAftermathPackages, nextSessionCarryForward);

        return new CampaignWorkspaceProjection(
            WorkspaceId: workspaceId,
            CampaignId: campaign.CampaignId,
            CampaignName: campaign.Name,
            Visibility: campaign.Visibility,
            RuleEnvironment: campaign.RuleEnvironment,
            Crews: workspaceCrews,
            Dossiers: workspaceDossiers,
            Runs: workspaceRuns,
            RecapShelf: enrichedRecapShelf,
            ReadinessCues: readinessCues,
            LatestContinuity: campaign.LatestContinuity,
            ReturnSummary: campaign.LatestContinuity?.Summary ?? campaign.Summary,
            ActiveSceneSummary: activeSceneSummary,
            NextSafeAction: nextSafeAction,
            ChangePackets: changePackets,
            Consequences: consequences,
            RosterTransfers: rosterTransfers,
            PrepLaunches: workspacePrepLaunches,
            TravelPrefetches: workspaceTravelPrefetches,
            AftermathPackages: workspaceAftermathPackages,
            NextSessionCarryForward: nextSessionCarryForward,
            FirstPlayableSession: firstPlayableSession,
            CampaignMemory: campaignMemory);
    }

    private static bool IsOperatorRole(string role)
        => string.Equals(role, "owner", StringComparison.OrdinalIgnoreCase)
            || string.Equals(role, "admin", StringComparison.OrdinalIgnoreCase)
            || string.Equals(role, "manager", StringComparison.OrdinalIgnoreCase)
            || string.Equals(role, "gm", StringComparison.OrdinalIgnoreCase);

    private static bool NeedsAttention(string? severity)
        => !string.IsNullOrWhiteSpace(severity)
           && !severity.Equals("healthy", StringComparison.OrdinalIgnoreCase)
           && !severity.Equals("info", StringComparison.OrdinalIgnoreCase)
           && !severity.Equals("ok", StringComparison.OrdinalIgnoreCase)
           && !severity.Equals("ready", StringComparison.OrdinalIgnoreCase);

    private static int ResolveReadinessAttentionPriority(string? severity)
        => severity?.Trim().ToLowerInvariant() switch
        {
            "attention" => 3,
            "warning" => 2,
            "review" => 1,
            _ => 0
        };

    private static CampaignReadinessCue? ResolvePriorityReadinessCue(
        IReadOnlyList<CampaignReadinessCue> readinessCues,
        bool requireSummary = false)
        => readinessCues
            .Where(static cue => NeedsAttention(cue.Severity))
            .Where(cue => !requireSummary || !string.IsNullOrWhiteSpace(cue.Summary))
            .OrderByDescending(static cue => ResolveReadinessAttentionPriority(cue.Severity))
            .FirstOrDefault();

    private static string ResolveOperatorRole(GroupDto group, string userId)
        => group.Memberships
               .Where(member => string.Equals(member.UserId, userId, StringComparison.OrdinalIgnoreCase))
               .OrderByDescending(member => OperatorRolePriority(member.Role))
               .Select(static member => member.Role)
               .FirstOrDefault()
           ?? "member";

    private static string ResolveCampaignVisibilitySummary(IReadOnlyList<CampaignProjection> campaigns)
    {
        if (campaigns.Count == 0)
        {
            return "No governed campaign visibility yet";
        }

        var visibilities = campaigns
            .Select(static item => item.Visibility)
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .OrderBy(static item => item, StringComparer.OrdinalIgnoreCase)
            .ToArray();
        return visibilities.Length == 1
            ? visibilities[0]
            : string.Join(" + ", visibilities);
    }

    private static string ResolveGroupOperationsSummary(
        GroupDto group,
        IReadOnlyList<CampaignProjection> groupCampaigns,
        IReadOnlyList<CampaignWorkspaceProjection> groupWorkspaces)
    {
        if (groupWorkspaces.Count == 0)
        {
            return $"{group.Name} has operator permissions but no shared campaign return surface yet.";
        }

        int crewCount = groupWorkspaces.Sum(static workspace => workspace.Crews.Count);
        int dossierCount = groupWorkspaces.Sum(static workspace => workspace.Dossiers.Count);
        return $"{groupCampaigns.Count} governed campaign(s), {crewCount} crew(s), and {dossierCount} dossier(s) stay on one operator surface.";
    }

    private static string ResolveGroupLeagueOperationsSummary(
        GroupDto group,
        IReadOnlyList<CampaignProjection> groupCampaigns,
        IReadOnlyList<CampaignWorkspaceProjection> groupWorkspaces,
        IReadOnlyList<CommunitySponsorSessionProjection> recentSponsorSessions,
        IReadOnlyList<CommunityJoinCodeProjection> recentJoinCodes,
        IReadOnlyList<CommunityBoostCodeProjection> recentBoostCodes,
        IReadOnlyList<RosterTransferProjection> recentRosterTransfers)
    {
        if (groupCampaigns.Count == 0 || groupWorkspaces.Count == 0)
        {
            return $"{group.Name} does not have a governed league or season lane yet.";
        }

        string laneLabel = groupCampaigns.Count > 1 ? "league / season lane" : "event lane";
        string sponsorSummary = recentSponsorSessions.Count == 0
            ? "sponsor seats are quiet"
            : $"{recentSponsorSessions.Count} sponsor seat(s) are actively tracked";
        string inviteSummary = recentJoinCodes.Count == 0 && recentBoostCodes.Count == 0
            ? "invite issuance is quiet"
            : $"{recentJoinCodes.Count} join code(s) and {recentBoostCodes.Count} sponsor code(s) are still governed here";
        string transferSummary = recentRosterTransfers.Count == 0
            ? "no fresh roster handoff is pending"
            : $"{recentRosterTransfers.Count} roster move(s) remain auditable";
        return $"{groupCampaigns.Count} governed campaign lane(s) keep the {laneLabel} on the same account/control backbone; {sponsorSummary}, {inviteSummary}, and {transferSummary}.";
    }

    private static string ResolveGroupCampaignReturnSummary(
        GroupDto group,
        IReadOnlyList<CampaignWorkspaceProjection> groupWorkspaces)
    {
        if (groupWorkspaces.Count == 0)
        {
            return $"No shared campaign return is attached to {group.Name} yet.";
        }

        CampaignWorkspaceProjection leadWorkspace = groupWorkspaces[0];
        return groupWorkspaces.Count == 1
            ? $"{leadWorkspace.CampaignName}: {leadWorkspace.ReturnSummary}"
            : $"{groupWorkspaces.Count} shared campaign returns are live; latest is {leadWorkspace.CampaignName}: {leadWorkspace.ReturnSummary}";
    }

    private static string ResolveGroupSeasonEventSummary(
        GroupDto group,
        IReadOnlyList<CampaignProjection> groupCampaigns,
        IReadOnlyList<CampaignWorkspaceProjection> groupWorkspaces)
    {
        if (groupWorkspaces.Count == 0)
        {
            return $"No governed season or event rail is attached to {group.Name} yet.";
        }

        int liveRunCount = groupWorkspaces.Sum(workspace => workspace.Runs.Count(run =>
            !string.Equals(run.Status, RunStatuses.Closed, StringComparison.OrdinalIgnoreCase)));
        int carryForwardCount = groupWorkspaces.Count(workspace => workspace.NextSessionCarryForward is not null);
        int recapPackageCount = groupWorkspaces.Sum(workspace => workspace.AftermathPackages?.Count ?? 0);
        string railLabel = groupCampaigns.Count > 1 ? "season rail" : "event rail";
        string liveRunSummary = liveRunCount == 0
            ? "no live or planned run is active yet"
            : $"{liveRunCount} live or planned run(s) are already attached";
        string carryForwardSummary = carryForwardCount == 0
            ? "next-session carry-forward is still pending"
            : $"{carryForwardCount} carry-forward lane(s) are already attached";
        string aftermathSummary = recapPackageCount == 0
            ? "aftermath packaging is still pending"
            : $"{recapPackageCount} aftermath package(s) are already reviewable";
        return $"{groupWorkspaces.Count} campaign return(s) keep the governed {railLabel} on the same account/control backbone; {liveRunSummary}, {carryForwardSummary}, and {aftermathSummary}.";
    }

    private static IReadOnlyList<string> BuildGroupRecentEventSummaries(IReadOnlyList<CampaignWorkspaceProjection> groupWorkspaces)
    {
        List<(DateTimeOffset UpdatedAtUtc, string Summary)> lines = [];
        foreach (var workspace in groupWorkspaces)
        {
            var leadRun = workspace.Runs
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .FirstOrDefault();
            if (leadRun is not null)
            {
                lines.Add((leadRun.UpdatedAtUtc, $"{workspace.CampaignName}: Run {leadRun.Title} · {(string.IsNullOrWhiteSpace(workspace.ActiveSceneSummary) ? leadRun.Summary : workspace.ActiveSceneSummary)}"));
            }

            if (workspace.NextSessionCarryForward is not null)
            {
                lines.Add((workspace.NextSessionCarryForward.UpdatedAtUtc, $"{workspace.CampaignName}: {workspace.NextSessionCarryForward.Label} · {workspace.NextSessionCarryForward.Summary}"));
            }

            var leadAftermathPackage = workspace.AftermathPackages?
                .OrderByDescending(static item => item.GeneratedAtUtc)
                .FirstOrDefault();
            if (leadAftermathPackage is not null)
            {
                lines.Add((leadAftermathPackage.GeneratedAtUtc, $"{workspace.CampaignName}: {leadAftermathPackage.Title} · {leadAftermathPackage.Summary}"));
            }

            var leadChangePacket = workspace.ChangePackets?
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .FirstOrDefault();
            if (leadChangePacket is not null)
            {
                lines.Add((leadChangePacket.UpdatedAtUtc, $"{workspace.CampaignName}: {leadChangePacket.Label} · {leadChangePacket.Summary}"));
            }
        }

        return lines
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .Select(static item => item.Summary)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Take(4)
            .ToArray();
    }

    private static IReadOnlyList<string> BuildGroupRecentLeagueAuditLines(
        IReadOnlyList<CommunitySponsorSessionProjection> recentSponsorSessions,
        IReadOnlyList<CommunityJoinCodeProjection> recentJoinCodes,
        IReadOnlyList<CommunityBoostCodeProjection> recentBoostCodes,
        IReadOnlyList<CommunitySeasonBoardEntryProjection> seasonBoardEntries,
        IReadOnlyList<RosterTransferProjection> recentRosterTransfers)
    {
        List<(DateTimeOffset UpdatedAtUtc, string Summary)> lines = [];
        foreach (var entry in seasonBoardEntries)
        {
            string recapSummary = string.IsNullOrWhiteSpace(entry.RecapSummary)
                ? string.Empty
                : $" Recap: {entry.RecapSummary}";
            string memorySummary = string.IsNullOrWhiteSpace(entry.CampaignMemorySummary)
                ? string.Empty
                : $" Memory: {entry.CampaignMemorySummary}";
            string consequenceSummary = string.IsNullOrWhiteSpace(entry.ConsequenceSummary)
                ? string.Empty
                : $" Consequence: {entry.ConsequenceSummary}";
            lines.Add((entry.UpdatedAtUtc, $"{entry.CampaignName}: {entry.RunTitle} · {entry.LatestEventSummary} Next: {entry.NextSafeAction}{recapSummary}{consequenceSummary}{memorySummary}"));
        }

        foreach (var sponsorSession in recentSponsorSessions)
        {
            lines.Add((sponsorSession.UpdatedAtUtc, $"{sponsorSession.UserDisplayName}: {sponsorSession.CampaignName} · {sponsorSession.StatusSummary}"));
        }

        foreach (var joinCode in recentJoinCodes)
        {
            lines.Add((joinCode.CreatedAtUtc, $"{joinCode.Code}: member entry · {joinCode.StatusSummary}"));
        }

        foreach (var boostCode in recentBoostCodes)
        {
            lines.Add(((boostCode.RedeemedAtUtc ?? boostCode.CreatedAtUtc), $"{boostCode.Code}: sponsorship entry · {boostCode.StatusSummary}"));
        }

        foreach (var transfer in recentRosterTransfers)
        {
            lines.Add((transfer.TransferredAtUtc, $"{transfer.RunnerHandle}: {transfer.Summary}"));
        }

        return lines
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .Select(static item => item.Summary)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Take(6)
            .ToArray();
    }

    private static IReadOnlyList<CommunityInviteCampaignProjection> BuildGroupInviteCampaigns(IReadOnlyList<CampaignProjection> groupCampaigns)
        => groupCampaigns
            .Select(static campaign => new CommunityInviteCampaignProjection(
                CampaignId: campaign.CampaignId,
                CampaignName: campaign.Name,
                Status: campaign.Status))
            .ToArray();

    private static IReadOnlyList<CommunityJoinCodeProjection> BuildGroupRecentJoinCodes(
        IEnumerable<JoinCodeDto> joinCodes,
        string groupId,
        DateTimeOffset now)
        => joinCodes
            .Where(item => string.Equals(item.GroupId, groupId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.CreatedAtUtc)
            .Take(5)
            .Select(item =>
            {
                bool expired = item.ExpiresAtUtc is { } expiresAt && expiresAt <= now;
                string status = expired ? "expired" : "active";
                string statusSummary = expired
                    ? $"Expired on {item.ExpiresAtUtc:yyyy-MM-dd HH:mm} UTC. Issue a fresh member code if this lane still matters."
                    : item.ExpiresAtUtc is { } activeUntil
                        ? $"Active until {activeUntil:yyyy-MM-dd HH:mm} UTC and used {item.Uses} time(s)."
                        : $"Active with no expiry and used {item.Uses} time(s).";
                return new CommunityJoinCodeProjection(
                    JoinCodeId: item.JoinCodeId,
                    Code: item.Code,
                    Role: item.Role,
                    Status: status,
                    StatusSummary: statusSummary,
                    CreatedAtUtc: item.CreatedAtUtc,
                    ExpiresAtUtc: item.ExpiresAtUtc,
                    Uses: item.Uses);
            })
            .ToArray();

    private static IReadOnlyList<CommunityBoostCodeProjection> BuildGroupRecentBoostCodes(
        IEnumerable<BoostCodeDto> boostCodes,
        IReadOnlyList<CampaignProjection> groupCampaigns,
        string groupId)
        => boostCodes
            .Where(item => string.Equals(item.GroupId, groupId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.CreatedAtUtc)
            .Take(5)
            .Select(item =>
            {
                string campaignName = groupCampaigns
                    .FirstOrDefault(campaign => string.Equals(campaign.CampaignId, item.CampaignId, StringComparison.OrdinalIgnoreCase))
                    ?.Name
                    ?? item.CampaignId;
                bool redeemed = string.Equals(item.Status, "redeemed", StringComparison.OrdinalIgnoreCase);
                string statusSummary = redeemed
                    ? $"Redeemed on {item.RedeemedAtUtc:yyyy-MM-dd HH:mm} UTC for {campaignName}. Issue a fresh sponsor code if this lane needs another seat."
                    : $"Active for {campaignName}. Redeem it on the governed sponsorship lane instead of passing raw lane ids around.";
                return new CommunityBoostCodeProjection(
                    BoostCodeId: item.BoostCodeId,
                    Code: item.Code,
                    CampaignId: item.CampaignId,
                    CampaignName: campaignName,
                    Status: redeemed ? "redeemed" : "active",
                    StatusSummary: statusSummary,
                    CreatedAtUtc: item.CreatedAtUtc,
                    RedeemedAtUtc: item.RedeemedAtUtc);
            })
            .ToArray();

    private static IReadOnlyList<CommunitySponsorSessionProjection> BuildGroupRecentSponsorSessions(
        IEnumerable<SponsorSessionState> sponsorSessions,
        IReadOnlyDictionary<string, HubUserDto> usersById,
        IReadOnlyList<CampaignProjection> groupCampaigns,
        string groupId)
        => sponsorSessions
            .Where(item => string.Equals(item.GroupId, groupId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => DescribeSponsorSessionPriority(item.Status))
            .ThenByDescending(static item => item.AuthorizedAtUtc ?? item.UpdatedAtUtc)
            .ThenByDescending(static item => item.UpdatedAtUtc)
            .Take(5)
            .Select(item =>
            {
                usersById.TryGetValue(item.UserId, out var user);
                var campaign = groupCampaigns.FirstOrDefault(candidate => string.Equals(candidate.CampaignId, item.BoostCampaignId, StringComparison.OrdinalIgnoreCase));
                var latestEvent = item.Events
                    .OrderByDescending(static entry => entry.CreatedAtUtc)
                    .FirstOrDefault();
                return new CommunitySponsorSessionProjection(
                    SponsorSessionId: item.SponsorSessionId,
                    UserId: item.UserId,
                    UserDisplayName: user?.DisplayName ?? "Community member",
                    CampaignId: item.BoostCampaignId ?? campaign?.CampaignId ?? string.Empty,
                    CampaignName: campaign?.Name ?? groupCampaigns.FirstOrDefault()?.Name ?? "Governed sponsor lane",
                    Status: item.Status,
                    StatusSummary: DescribeSponsorSessionStatus(item),
                    RequestedLaneRole: item.RequestedLaneRole,
                    AuthorizationTier: item.AuthorizationTier,
                    LatestEventSummary: latestEvent?.Message,
                    UpdatedAtUtc: item.UpdatedAtUtc);
            })
            .ToArray();

    private static int DescribeSponsorSessionPriority(string? status)
        => (status ?? string.Empty).Trim().ToLowerInvariant() switch
        {
            "active" => 6,
            "auth_ready" => 5,
            "lane_pending" => 5,
            "pending_auth" => 5,
            "waiting_for_slot" => 4,
            "fleet_lane_created" => 4,
            "consented" => 3,
            "intent_created" => 2,
            "stopped" => 1,
            "revoked" => 0,
            _ => 1
        };

    private static string DescribeSponsorSessionStatus(SponsorSessionState item)
    {
        ArgumentNullException.ThrowIfNull(item);

        var tier = string.Equals(item.AuthorizationTier, "unknown", StringComparison.OrdinalIgnoreCase)
            ? null
            : item.AuthorizationTier.Replace('_', ' ');
        var role = string.IsNullOrWhiteSpace(item.RequestedLaneRole)
            ? "participant"
            : item.RequestedLaneRole.Replace('_', ' ');
        var status = (item.Status ?? string.Empty).Trim().ToLowerInvariant() switch
        {
            "active" => "Active on Fleet",
            "auth_ready" => "Ready for activation",
            "lane_pending" => "Lane is warming",
            "pending_auth" => "Waiting for device auth",
            "waiting_for_slot" => "Queued for the next sponsor slot",
            "fleet_lane_created" => "Fleet lane created",
            "consented" => "Consent recorded",
            "intent_created" => "Intent recorded",
            "stopped" => "Stopped",
            "revoked" => "Revoked",
            _ => System.Globalization.CultureInfo.InvariantCulture.TextInfo.ToTitleCase((item.Status ?? "tracked").Replace('_', ' '))
        };

        return tier is null
            ? $"{status} · {role} lane"
            : $"{status} · {role} lane · {tier} tier";
    }

    private static DateTimeOffset ResolveCommunityOperatorFreshnessUtc(CommunityOperatorProjection operation)
    {
        ArgumentNullException.ThrowIfNull(operation);

        return operation.SeasonBoardEntries
            .Select(static entry => (DateTimeOffset?)entry.UpdatedAtUtc)
            .Concat(operation.RecentJoinCodes.Select(static code => (DateTimeOffset?)code.CreatedAtUtc))
            .Concat(operation.RecentBoostCodes.Select(static code => (DateTimeOffset?)(code.RedeemedAtUtc ?? code.CreatedAtUtc)))
            .Concat(operation.RecentSponsorSessions.Select(static session => (DateTimeOffset?)session.UpdatedAtUtc))
            .Concat((operation.RecentRosterTransfers ?? Array.Empty<RosterTransferProjection>()).Select(static transfer => (DateTimeOffset?)transfer.TransferredAtUtc))
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(DateTimeOffset.MinValue)
            .Max();
    }

    private static int ResolveCommunityOperatorActivityBreadth(CommunityOperatorProjection operation)
    {
        ArgumentNullException.ThrowIfNull(operation);

        int inviteCapabilityCount = operation.Capabilities.Count(capability =>
            string.Equals(capability, "can_issue_join_codes", StringComparison.OrdinalIgnoreCase)
            || string.Equals(capability, "can_issue_boost_codes", StringComparison.OrdinalIgnoreCase)
            || string.Equals(capability, "can_manage_members", StringComparison.OrdinalIgnoreCase));

        return operation.ActiveCampaignCount
            + operation.ActiveSponsorSessionCount
            + operation.RecentReturnSummaries.Count
            + operation.RecentEventSummaries.Count
            + operation.SeasonBoardEntries.Count
            + operation.RecentJoinCodes.Count
            + operation.RecentBoostCodes.Count
            + operation.RecentSponsorSessions.Count
            + (operation.RecentRosterTransfers?.Count ?? 0)
            + operation.Watchouts.Count
            + inviteCapabilityCount;
    }

    private static DateTimeOffset ResolveWorkspaceFreshnessUtc(CampaignWorkspaceProjection workspace)
    {
        ArgumentNullException.ThrowIfNull(workspace);

        return new[] { workspace.LatestContinuity?.CapturedAtUtc, workspace.NextSessionCarryForward?.UpdatedAtUtc }
            .Concat((workspace.Runs ?? Array.Empty<RunProjection>()).Select(static item => (DateTimeOffset?)item.UpdatedAtUtc))
            .Concat((workspace.ChangePackets ?? Array.Empty<WorkspaceChangePacketProjection>()).Select(static item => (DateTimeOffset?)item.UpdatedAtUtc))
            .Concat((workspace.Consequences ?? Array.Empty<CampaignConsequenceProjection>()).Select(static item => (DateTimeOffset?)item.UpdatedAtUtc))
            .Concat((workspace.RosterTransfers ?? Array.Empty<RosterTransferProjection>()).Select(static item => (DateTimeOffset?)item.TransferredAtUtc))
            .Concat((workspace.PrepLaunches ?? Array.Empty<GovernedPrepLaunchProjection>()).Select(static item => (DateTimeOffset?)item.LaunchedAtUtc))
            .Concat((workspace.TravelPrefetches ?? Array.Empty<TravelPrefetchReceiptProjection>()).Select(static item => (DateTimeOffset?)item.StagedAtUtc))
            .Concat((workspace.AftermathPackages ?? Array.Empty<AftermathRecapPackageProjection>()).Select(static item => (DateTimeOffset?)item.GeneratedAtUtc))
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(DateTimeOffset.MinValue)
            .Max();
    }

    private static int ResolveWorkspaceActivityBreadth(CampaignWorkspaceProjection workspace)
    {
        ArgumentNullException.ThrowIfNull(workspace);

        return (workspace.ChangePackets?.Count ?? 0)
            + (workspace.AftermathPackages?.Count ?? 0)
            + (workspace.PrepLaunches?.Count ?? 0)
            + (workspace.TravelPrefetches?.Count ?? 0)
            + (workspace.RosterTransfers?.Count ?? 0)
            + (workspace.Consequences?.Count ?? 0)
            + (workspace.NextSessionCarryForward is null ? 0 : 1);
    }

    private static IReadOnlyList<CommunitySeasonBoardEntryProjection> BuildGroupSeasonBoardEntries(IReadOnlyList<CampaignWorkspaceProjection> groupWorkspaces)
        => groupWorkspaces
            .Select(workspace =>
            {
                var leadRun = workspace.Runs
                    .OrderByDescending(static item => item.UpdatedAtUtc)
                    .FirstOrDefault();
                var leadChangePacket = workspace.ChangePackets?
                    .OrderByDescending(static item => item.UpdatedAtUtc)
                    .FirstOrDefault();
                var leadAftermathPackage = workspace.AftermathPackages?
                    .OrderByDescending(static item => item.GeneratedAtUtc)
                    .FirstOrDefault();
                var leadRecapShelfEntry = workspace.RecapShelf?.FirstOrDefault();
                var leadConsequence = workspace.Consequences?
                    .OrderByDescending(static item => item.UpdatedAtUtc)
                    .FirstOrDefault();
                var watchout = workspace.ReadinessCues
                    .Where(static cue => NeedsAttention(cue.Severity))
                    .OrderByDescending(static cue => ResolveReadinessAttentionPriority(cue.Severity))
                    .Select(static cue => $"{cue.Title} — {cue.Summary}")
                    .FirstOrDefault();
                string latestEventSummary = leadChangePacket is not null
                    ? $"{leadChangePacket.Label} — {leadChangePacket.Summary}"
                    : workspace.NextSessionCarryForward is not null
                        ? $"{workspace.NextSessionCarryForward.Label} — {workspace.NextSessionCarryForward.Summary}"
                        : leadAftermathPackage is not null
                            ? $"{leadAftermathPackage.Title} — {leadAftermathPackage.Summary}"
                            : !string.IsNullOrWhiteSpace(workspace.ActiveSceneSummary)
                                ? workspace.ActiveSceneSummary!
                                : workspace.ReturnSummary;
                DateTimeOffset updatedAtUtc = new DateTimeOffset?[]
                    {
                        leadChangePacket?.UpdatedAtUtc,
                        workspace.NextSessionCarryForward?.UpdatedAtUtc,
                        leadConsequence?.UpdatedAtUtc,
                        workspace.CampaignMemory?.UpdatedAtUtc,
                        leadAftermathPackage?.GeneratedAtUtc,
                        leadRun?.UpdatedAtUtc,
                        workspace.LatestContinuity?.CapturedAtUtc
                    }
                    .Where(static item => item.HasValue)
                    .Select(static item => item!.Value)
                    .DefaultIfEmpty(DateTimeOffset.MinValue)
                    .Max();
                return new CommunitySeasonBoardEntryProjection(
                    CampaignId: workspace.CampaignId,
                    WorkspaceId: workspace.WorkspaceId,
                    CampaignName: workspace.CampaignName,
                    RunTitle: leadRun?.Title ?? "No live run yet",
                    LatestEventSummary: latestEventSummary,
                    RecapSummary: leadAftermathPackage is not null
                        ? $"{leadAftermathPackage.Title} — {leadAftermathPackage.Summary}"
                        : leadRecapShelfEntry is null
                            ? null
                            : $"{leadRecapShelfEntry.Label} — {leadRecapShelfEntry.Summary}",
                    ConsequenceSummary: leadConsequence is null ? null : $"{leadConsequence.Label} — {leadConsequence.Summary}",
                    CampaignMemorySummary: workspace.CampaignMemory?.Summary,
                    CampaignMemoryReturnSummary: workspace.CampaignMemory?.ReturnSummary,
                    NextSafeAction: workspace.NextSafeAction ?? "Open the shared campaign view and confirm the current return lane before you continue.",
                    WatchoutSummary: watchout,
                    UpdatedAtUtc: updatedAtUtc);
            })
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ThenBy(static item => item.CampaignName, StringComparer.OrdinalIgnoreCase)
            .ToArray();

    private static IReadOnlyList<string> BuildGroupOperatorWatchouts(IReadOnlyList<CampaignWorkspaceProjection> groupWorkspaces)
        => groupWorkspaces
            .SelectMany(workspace => workspace.ReadinessCues
                .Where(static cue => NeedsAttention(cue.Severity))
                .Select(cue => new
                {
                    Summary = $"{workspace.CampaignName}: {cue.Title} — {cue.Summary}",
                    SeverityPriority = ResolveReadinessAttentionPriority(cue.Severity),
                    WorkspaceFreshnessUtc = ResolveWorkspaceFreshnessUtc(workspace)
                }))
            .OrderByDescending(static item => item.SeverityPriority)
            .ThenByDescending(static item => item.WorkspaceFreshnessUtc)
            .Select(static item => item.Summary)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Take(4)
            .ToArray();

    private static IReadOnlyList<string> FinalizeLines(IEnumerable<string> lines)
        => lines
            .Where(static line => !string.IsNullOrWhiteSpace(line))
            .Select(static line => line.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Take(8)
            .ToArray();

    private static int OperatorRolePriority(string? role)
        => role?.Trim().ToLowerInvariant() switch
        {
            "owner" => 4,
            "admin" => 3,
            "manager" => 2,
            "gm" => 1,
            _ => 0
        };

    private static IReadOnlyList<BuildLabHandoffProjection> BuildBuildLabHandoffs(
        IReadOnlyList<RunnerDossierProjection> dossiers,
        IReadOnlyList<CampaignWorkspaceProjection> workspaces,
        WorkspaceRestoreProjection restore)
    {
        return dossiers
            .Select(dossier =>
            {
                var workspace = workspaces.FirstOrDefault(item => string.Equals(item.CampaignId, dossier.CampaignId, StringComparison.OrdinalIgnoreCase));
                var outputs = dossier.Projections
                    .Concat(workspace?.RecapShelf ?? Array.Empty<PublicationSafeProjection>())
                    .Distinct()
                    .Take(3)
                    .ToArray();
                var runtimeFingerprint = workspace?.RuleEnvironment.CompatibilityFingerprint ?? dossier.RuleEnvironment.CompatibilityFingerprint;
                var variantLabel = workspace is null ? "Living dossier carry-forward" : "Ops-first dossier carry-forward";
                var progressionLabel = workspace is null ? "Ready to seed into a campaign" : "25 / 50 / 100 Karma path stays attached to the campaign return";
                var nextSafeAction = ResolveBuildLabNextSafeAction(workspace, outputs, restore);
                var runtimeCompatibilitySummary = DescribeBuildLabRuntimeCompatibility(runtimeFingerprint, workspace, restore);
                var attachedOutputSummary = outputs.Length switch
                {
                    1 => "1 dossier or campaign-safe output is already attached to this handoff.",
                    > 1 => $"{outputs.Length} dossier or campaign-safe outputs are already attached to this handoff.",
                    _ => null
                };
                var readyOutputSummary = outputs.Length switch
                {
                    1 => "1 dossier or campaign-safe output is already ready for export and recap follow-through.",
                    > 1 => $"{outputs.Length} dossier or campaign-safe outputs are already ready for export and recap follow-through.",
                    _ => "Publication-safe outputs will appear as recap and dossier cards once the first run lands."
                };
                var campaignReturnSummary = workspace?.ReturnSummary
                    ?? "No campaign workspace is attached yet, so return still lands on the living dossier until the first governed campaign handoff exists.";
                var supportClosureSummary = DescribeBuildLabSupportClosure(runtimeFingerprint, restore);
                var watchouts = BuildBuildLabWatchouts(workspace, outputs, restore);
                var plannerCoverageSummary = BuildBuildLabPlannerCoverageSummary(workspace, outputs, restore);
                var plannerCoverageLines = BuildBuildLabPlannerCoverageLines(workspace, outputs, restore);
                return new BuildLabHandoffProjection(
                    HandoffId: StableId("buildlab", dossier.DossierId),
                    DossierId: dossier.DossierId,
                    CampaignId: dossier.CampaignId,
                    Title: $"{dossier.DisplayName} build path",
                    Summary: "The chosen build lane now lands in living dossier and campaign return truth instead of a disposable comparison card.",
                    VariantLabel: variantLabel,
                    ProgressionLabel: progressionLabel,
                    ExplainEntryId: $"buildlab.handoff.{dossier.DossierId}",
                    TradeoffLines:
                    [
                        attachedOutputSummary ?? "Role overlap stays explicit before the handoff leaves build comparison.",
                        workspace is null
                            ? "No campaign workspace is attached yet, so the handoff seeds the dossier first."
                            : $"Campaign workspace {workspace.CampaignName} keeps the downstream continuity target visible and the same upgrade path attached."
                    ],
                    ProgressionOutcomes:
                    [
                        workspace is null
                            ? "25 / 50 / 100 Karma checkpoints stay attached to the living dossier until the first governed campaign workspace exists."
                            : $"25 / 50 / 100 Karma checkpoints stay attached to {workspace.CampaignName} so the return path keeps the same upgrade plan.",
                        readyOutputSummary
                    ],
                    Outputs: outputs,
                    UpdatedAtUtc: dossier.UpdatedAtUtc,
                    NextSafeAction: nextSafeAction,
                    RuntimeCompatibilitySummary: runtimeCompatibilitySummary,
                    CampaignReturnSummary: campaignReturnSummary,
                    SupportClosureSummary: supportClosureSummary,
                    Watchouts: watchouts,
                    PlannerCoverageSummary: plannerCoverageSummary,
                    PlannerCoverageLines: plannerCoverageLines);
            })
            .Take(3)
            .ToArray();
    }

    private static string ResolveBuildLabNextSafeAction(
        CampaignWorkspaceProjection? workspace,
        IReadOnlyList<PublicationSafeProjection> outputs,
        WorkspaceRestoreProjection restore)
    {
        if (restore.ConflictSummaries.Count > 0)
        {
            return "Confirm restore conflicts and current channel posture before you export, publish, or reopen campaign continuity.";
        }

        if (workspace is null)
        {
            return "Attach this dossier to a governed campaign workspace before you trust the handoff as the table-safe return path.";
        }

        if (outputs.Count == 0)
        {
            return $"Open {workspace.CampaignName} and generate the first recap-safe output before you hand the build path back to play.";
        }

        return $"Open {workspace.CampaignName} and verify readiness cues before you hand the build path back into active play.";
    }

    private static string DescribeBuildLabRuntimeCompatibility(
        string runtimeFingerprint,
        CampaignWorkspaceProjection? workspace,
        WorkspaceRestoreProjection restore)
    {
        if (restore.ConflictSummaries.Count > 0)
        {
            return $"{runtimeFingerprint} is the active compatibility fingerprint, but restore still needs review before the handoff is campaign-safe.";
        }

        return workspace is null
            ? $"{runtimeFingerprint} is pinned on the living dossier, but the first campaign workspace still needs to confirm the same rule posture."
            : $"{runtimeFingerprint} is pinned across the dossier, workspace, and return rail for this handoff.";
    }

    private static string DescribeBuildLabSupportClosure(
        string runtimeFingerprint,
        WorkspaceRestoreProjection restore)
    {
        var claimedDevice = restore.ClaimedDevices
            .FirstOrDefault(item => string.Equals(item.Channel, "preview", StringComparison.OrdinalIgnoreCase))
            ?? restore.ClaimedDevices.FirstOrDefault();
        var artifact = restore.RecentArtifacts
            .FirstOrDefault(item => !string.IsNullOrWhiteSpace(item.Channel) && string.Equals(item.Channel, claimedDevice?.Channel, StringComparison.OrdinalIgnoreCase))
            ?? restore.RecentArtifacts.FirstOrDefault();

        if (claimedDevice is null)
        {
            return $"Support can cite the same runtime fingerprint ({runtimeFingerprint}), but no claimed install is attached yet for release-aware closure.";
        }

        if (artifact is null)
        {
            return $"Support can anchor closure on the claimed {claimedDevice.Platform} {claimedDevice.HeadId} install on {claimedDevice.Channel} and the same runtime fingerprint ({runtimeFingerprint}).";
        }

        return $"Support can anchor closure on {artifact.Channel} {artifact.Version ?? "current"} for {artifact.Label} and the same runtime fingerprint ({runtimeFingerprint}).";
    }

    private static string BuildBuildLabPlannerCoverageSummary(
        CampaignWorkspaceProjection? workspace,
        IReadOnlyList<PublicationSafeProjection> outputs,
        WorkspaceRestoreProjection restore)
    {
        const int totalCheckpoints = 4;
        var coveredCheckpoints = 0;

        if (workspace is not null)
        {
            coveredCheckpoints++;
        }

        if (outputs.Count > 0)
        {
            coveredCheckpoints++;
        }

        if (restore.ConflictSummaries.Count == 0)
        {
            coveredCheckpoints++;
        }

        if (restore.ClaimedDevices.Count > 0)
        {
            coveredCheckpoints++;
        }

        return $"{coveredCheckpoints} of {totalCheckpoints} build follow-through checkpoints are already grounded.";
    }

    private static IReadOnlyList<string> BuildBuildLabPlannerCoverageLines(
        CampaignWorkspaceProjection? workspace,
        IReadOnlyList<PublicationSafeProjection> outputs,
        WorkspaceRestoreProjection restore)
    {
        List<string> lines =
        [
            workspace is null
                ? "Campaign continuity: no governed campaign workspace is attached yet, so the handoff still lands on the living dossier first."
                : $"Campaign continuity: {workspace.CampaignName} is already attached as the governed return lane for this handoff.",
            outputs.Count switch
            {
                1 => "Outputs: 1 dossier or campaign-safe output is already attached to the handoff.",
                > 1 => $"Outputs: {outputs.Count} dossier or campaign-safe outputs are already attached to the handoff.",
                _ => "Outputs: no dossier or campaign-safe output is attached yet, so export and recap proof are still pending."
            },
            restore.ConflictSummaries.Count switch
            {
                0 => "Restore posture: no restore conflicts are currently blocking replay-safe handoff follow-through.",
                1 => "Restore posture: 1 restore conflict still needs review before the handoff is replay-safe.",
                _ => $"Restore posture: {restore.ConflictSummaries.Count} restore conflicts still need review before the handoff is replay-safe."
            },
            restore.ClaimedDevices.Count switch
            {
                0 => "Claimed install: no linked device is attached yet for install-aware follow-through.",
                1 => "Claimed install: 1 linked device is already attached for install-aware follow-through.",
                _ => $"Claimed install: {restore.ClaimedDevices.Count} linked devices are already attached for install-aware follow-through."
            }
        ];

        return lines
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .ToArray();
    }

    private static SceneProjection? ResolveActiveScene(RunProjection run)
        => run.Scenes.FirstOrDefault(item => string.Equals(item.SceneId, run.ActiveSceneId, StringComparison.OrdinalIgnoreCase))
           ?? run.Scenes.OrderByDescending(static item => item.UpdatedAtUtc).FirstOrDefault();

    private static string? DescribeActiveSceneSummary(
        RunProjection? leadRun,
        SceneProjection? activeScene,
        ObjectiveProjection? leadObjective)
    {
        if (leadRun is null)
        {
            return null;
        }

        var objectiveSummary = leadObjective is null
            ? "No open objective is pinned yet."
            : $"{leadObjective.Title} stays {leadObjective.Status} with {leadObjective.Pressure} pressure.";

        if (activeScene is null)
        {
            return $"{leadRun.Title} has no pinned live scene yet. {objectiveSummary}";
        }

        return $"{leadRun.Title} is currently on {activeScene.Title} ({activeScene.Revision}). {objectiveSummary}";
    }

    private static string ResolveWorkspaceNextSafeAction(
        CampaignProjection campaign,
        WorkspaceRestoreProjection restore,
        IReadOnlyList<PublicationSafeProjection> recapShelf,
        IReadOnlyList<CampaignReadinessCue> readinessCues,
        RunProjection? leadRun,
        SceneProjection? activeScene,
        ObjectiveProjection? leadObjective)
    {
        string? restoreConflict = restore.ConflictSummaries.FirstOrDefault(static item => !string.IsNullOrWhiteSpace(item));
        if (!string.IsNullOrWhiteSpace(restoreConflict))
        {
            return $"Resolve restore review before you reopen {campaign.Name}: {restoreConflict}";
        }

        CampaignReadinessCue? attentionCue = ResolvePriorityReadinessCue(readinessCues);
        if (attentionCue is not null)
        {
            return $"Review {attentionCue.Title} before you continue {campaign.Name}: {attentionCue.Summary}";
        }

        if (activeScene is not null && leadObjective is not null)
        {
            string runTitle = leadRun?.Title ?? campaign.Name;
            return $"Resume {activeScene.Title} in {runTitle} and clear {leadObjective.Title} before you advance the next recap-safe handoff.";
        }

        if (activeScene is not null)
        {
            string runTitle = leadRun?.Title ?? campaign.Name;
            return $"Resume {activeScene.Title} in {runTitle} and confirm the next scene-safe recap before you switch devices.";
        }

        if (recapShelf.Count == 0)
        {
            return $"Open {campaign.Name} and publish the first recap-safe output before you trust this workspace as the return lane.";
        }

        return $"Open {campaign.Name} from the latest continuity snapshot and keep the shared return lane attached to the current claimed install.";
    }

    private static FirstPlayableSessionProjection? BuildFirstPlayableSession(
        CampaignProjection campaign,
        WorkspaceRestoreProjection restore,
        IReadOnlyList<CampaignReadinessCue> readinessCues,
        IReadOnlyList<CrewProjection> workspaceCrews,
        IReadOnlyList<RunnerDossierProjection> workspaceDossiers,
        RunProjection? leadRun,
        SceneProjection? activeScene,
        ObjectiveProjection? leadObjective,
        string nextSafeAction,
        IReadOnlyList<GovernedPrepLaunchProjection> prepLaunches,
        IReadOnlyList<TravelPrefetchReceiptProjection> travelPrefetchReceipts,
        IReadOnlyList<AftermathRecapPackageProjection> aftermathPackages)
    {
        if (leadRun is null
            || activeScene is null
            || workspaceDossiers.Count == 0
            || workspaceCrews.Count == 0
            || prepLaunches.Count > 0
            || travelPrefetchReceipts.Count > 0
            || aftermathPackages.Count > 0)
        {
            return null;
        }

        int crewMemberCount = workspaceCrews.Sum(static crew => crew.Members.Count);
        CampaignReadinessCue? attentionCue = ResolvePriorityReadinessCue(readinessCues);
        ClaimedDeviceRestoreProjection? claimedDevice = restore.ClaimedDevices.FirstOrDefault();
        string rosterSummary = $"{workspaceDossiers.Count} dossier(s) and {crewMemberCount} crew member(s) are already attached to the shared return lane.";
        string readinessSummary = attentionCue is null
            ? "Rules, roster, and continuity already agree on the same kickoff lane."
            : $"{attentionCue.Title} still needs review before the first session is fully clear.";
        string summary = $"{campaign.Name} already has {leadRun.Title}, {activeScene.Title}, and {rosterSummary} {readinessSummary}";
        string campaignStartSummary = leadObjective is null
            ? $"{activeScene.Title} is the live campaign-start scene on {leadRun.Title}."
            : $"{activeScene.Title} opens {leadRun.Title} while {leadObjective.Title} stays {leadObjective.Status} with {leadObjective.Pressure} pressure.";
        string ruleReadySummary = BuildFirstPlayableRuleReadySummary(campaign.RuleEnvironment, workspaceDossiers);
        string returnLaneSummary = BuildFirstPlayableReturnLaneSummary(campaign, claimedDevice, leadRun, activeScene);
        string campaignReadySummary = BuildFirstPlayableCampaignReadySummary(workspaceDossiers.Count, crewMemberCount, leadRun, attentionCue);
        DateTimeOffset updatedAtUtc = new[]
            {
                campaign.LatestContinuity?.CapturedAtUtc,
                leadRun.UpdatedAtUtc,
                activeScene.UpdatedAtUtc,
                leadObjective?.UpdatedAtUtc,
                workspaceDossiers.Max(static item => (DateTimeOffset?)item.UpdatedAtUtc),
                restore.GeneratedAtUtc
            }
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(restore.GeneratedAtUtc)
            .Max();

        return new FirstPlayableSessionProjection(
            SessionId: StableId("first-playable", $"{campaign.CampaignId}:{leadRun.RunId}:{updatedAtUtc.ToUnixTimeMilliseconds()}"),
            Label: "First playable session",
            Summary: summary,
            CampaignStartSummary: campaignStartSummary,
            RuleReadySummary: ruleReadySummary,
            ReturnLaneSummary: returnLaneSummary,
            CampaignReadySummary: campaignReadySummary,
            NextSafeAction: nextSafeAction,
            EvidenceLines: FinalizeLines(
            [
                campaign.LatestContinuity?.Summary ?? campaign.Summary,
                $"{leadRun.Title} is active on {activeScene.Title} at {activeScene.Revision}.",
                leadObjective is null ? string.Empty : $"{leadObjective.Title} remains {leadObjective.Status} with {leadObjective.Pressure} pressure.",
                rosterSummary,
                claimedDevice?.RestoreSummary ?? "Claimed install return will attach the same kickoff lane to the reopening device.",
                attentionCue?.Summary ?? string.Empty,
                nextSafeAction
            ]),
            UpdatedAtUtc: updatedAtUtc);
    }

    private static string BuildFirstPlayableRuleReadySummary(
        RuleEnvironmentRef ruleEnvironment,
        IReadOnlyList<RunnerDossierProjection> dossiers)
    {
        int alignedCount = dossiers.Count(dossier =>
            string.Equals(
                dossier.RuleEnvironment.CompatibilityFingerprint,
                ruleEnvironment.CompatibilityFingerprint,
                StringComparison.OrdinalIgnoreCase));
        int mismatchedCount = dossiers.Count - alignedCount;
        string lifecycleStage = DescribeRuleEnvironmentLifecycleStage(ResolveRuleEnvironmentLifecycleStage(ruleEnvironment)).ToLowerInvariant();

        if (mismatchedCount == 0)
        {
            return $"{alignedCount} dossier(s) stay pinned to {ruleEnvironment.CompatibilityFingerprint} with the {lifecycleStage} {ruleEnvironment.OwnerScope} rail.";
        }

        return $"{alignedCount} dossier(s) already match {ruleEnvironment.CompatibilityFingerprint}, but {mismatchedCount} still need that {lifecycleStage} {ruleEnvironment.OwnerScope} rule lane.";
    }

    private static string BuildFirstPlayableReturnLaneSummary(
        CampaignProjection campaign,
        ClaimedDeviceRestoreProjection? claimedDevice,
        RunProjection leadRun,
        SceneProjection activeScene)
    {
        string continuitySummary = campaign.LatestContinuity?.Summary
            ?? $"{activeScene.Title} stays pinned as the shared return lane for {leadRun.Title}.";

        if (claimedDevice is null)
        {
            return $"{continuitySummary} Claimed-install return will reopen the same kickoff lane when this account links a device.";
        }

        return $"{continuitySummary} {claimedDevice.RestoreSummary}";
    }

    private static string BuildFirstPlayableCampaignReadySummary(
        int dossierCount,
        int crewMemberCount,
        RunProjection leadRun,
        CampaignReadinessCue? attentionCue)
    {
        if (attentionCue is null)
        {
            return $"{dossierCount} dossier(s) and {crewMemberCount} crew member(s) already cover {leadRun.Title} with no blocking readiness cue.";
        }

        return $"{dossierCount} dossier(s) and {crewMemberCount} crew member(s) are attached, but {attentionCue.Summary}";
    }

    private static string HumanizePhrase(string? value, string fallback)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return fallback;
        }

        return value.Trim().Replace('_', ' ');
    }

    private static NextSessionCarryForwardProjection? BuildNextSessionCarryForward(
        CampaignProjection campaign,
        string nextSafeAction,
        RunProjection? leadRun,
        SceneProjection? activeScene,
        ObjectiveProjection? leadObjective,
        IReadOnlyList<CampaignConsequenceProjection> consequences,
        IReadOnlyList<GovernedPrepLaunchProjection> prepLaunches,
        IReadOnlyList<TravelPrefetchReceiptProjection> travelPrefetchReceipts,
        IReadOnlyList<AftermathRecapPackageProjection> aftermathPackages)
    {
        ContinuitySnapshotRef? continuity = campaign.LatestContinuity;
        CampaignConsequenceProjection? leadConsequence = consequences
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        GovernedPrepLaunchProjection? leadPrepLaunch = prepLaunches
            .OrderByDescending(static item => item.LaunchedAtUtc)
            .FirstOrDefault();
        TravelPrefetchReceiptProjection? leadTravelPrefetch = travelPrefetchReceipts
            .OrderByDescending(static item => item.StagedAtUtc)
            .FirstOrDefault();
        AftermathRecapPackageProjection? leadAftermathPackage = aftermathPackages
            .OrderByDescending(static item => item.GeneratedAtUtc)
            .FirstOrDefault();

        if (continuity is null
            && leadConsequence is null
            && leadPrepLaunch is null
            && leadTravelPrefetch is null
            && leadAftermathPackage is null
            && activeScene is null
            && leadObjective is null)
        {
            return null;
        }

        string summary;
        if (leadAftermathPackage is not null && activeScene is not null && leadObjective is not null)
        {
            summary = $"{leadAftermathPackage.Title} keeps {activeScene.Title} and {leadObjective.Title} reviewable before the next session resumes.";
        }
        else if (leadAftermathPackage is not null && leadObjective is not null)
        {
            summary = $"{leadAftermathPackage.Title} keeps {leadObjective.Title} reviewable before {leadRun?.Title ?? campaign.Name} resumes.";
        }
        else if (activeScene is not null && leadObjective is not null)
        {
            summary = $"{activeScene.Title} and {leadObjective.Title} stay pinned as the governed next-session return for {leadRun?.Title ?? campaign.Name}.";
        }
        else if (leadAftermathPackage is not null)
        {
            summary = IsAftermathPackageKind(leadAftermathPackage, "replay_timeline")
                ? $"{leadAftermathPackage.Title} is pinned as the replay-safe carry-forward packet for {campaign.Name}."
                : $"{leadAftermathPackage.Title} is pinned as the recap-safe carry-forward packet for {campaign.Name}.";
        }
        else if (leadConsequence is not null)
        {
            summary = $"{leadConsequence.Label} stays attached to the next-session return for {campaign.Name}.";
        }
        else if (activeScene is not null)
        {
            summary = $"{activeScene.Title} stays pinned as the live scene for the next session return.";
        }
        else
        {
            summary = continuity?.Summary ?? campaign.Summary;
        }

        DateTimeOffset updatedAtUtc = new[]
            {
                continuity?.CapturedAtUtc,
                activeScene?.UpdatedAtUtc,
                leadObjective?.UpdatedAtUtc,
                leadConsequence?.UpdatedAtUtc,
                leadPrepLaunch?.LaunchedAtUtc,
                leadTravelPrefetch?.StagedAtUtc,
                leadAftermathPackage?.GeneratedAtUtc
            }
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(DateTimeOffset.UtcNow)
            .Max();

        string prepBindingSummary = leadPrepLaunch is null
            ? string.Empty
            : string.IsNullOrWhiteSpace(leadPrepLaunch.TargetSceneTitle)
                ? $"{leadPrepLaunch.PacketTitle} stays bound to {(leadPrepLaunch.TargetRunTitle ?? campaign.Name)}."
                : $"{leadPrepLaunch.PacketTitle} stays bound to {leadPrepLaunch.TargetRunTitle} / {leadPrepLaunch.TargetSceneTitle}.";
        string travelSummary = leadTravelPrefetch is null
            ? string.Empty
            : $"{leadTravelPrefetch.DeviceRole} on {leadTravelPrefetch.Platform} already has the staged travel packet.";

        return new NextSessionCarryForwardProjection(
            CarryForwardId: StableId("next-session", $"{campaign.CampaignId}:{updatedAtUtc.ToUnixTimeMilliseconds()}"),
            Label: "Next-session carry-forward",
            Summary: summary,
            ReturnSummary: continuity?.Summary ?? campaign.Summary,
            NextSafeAction: nextSafeAction,
            EvidenceLines: FinalizeLines(
            [
                continuity?.Summary ?? campaign.Summary,
                activeScene is null ? string.Empty : $"{activeScene.Title} is live on {leadRun?.Title ?? campaign.Name} at {activeScene.Revision}.",
                leadObjective is null ? string.Empty : $"{leadObjective.Title} stays {leadObjective.Status} with {leadObjective.Pressure} pressure.",
                leadAftermathPackage is null ? string.Empty : $"{leadAftermathPackage.Title}: {leadAftermathPackage.Summary}",
                leadConsequence?.EvidenceLines.FirstOrDefault() ?? leadConsequence?.Summary ?? string.Empty,
                prepBindingSummary,
                travelSummary,
                nextSafeAction
            ]),
            UpdatedAtUtc: updatedAtUtc);
    }

    private static CampaignMemoryProjection? BuildCampaignMemory(
        CampaignProjection campaign,
        string nextSafeAction,
        RunProjection? leadRun,
        SceneProjection? activeScene,
        ObjectiveProjection? leadObjective,
        IReadOnlyList<CampaignConsequenceProjection> consequences,
        IReadOnlyList<RosterTransferProjection> rosterTransfers,
        IReadOnlyList<GovernedPrepLaunchProjection> prepLaunches,
        IReadOnlyList<TravelPrefetchReceiptProjection> travelPrefetchReceipts,
        IReadOnlyList<AftermathRecapPackageProjection> aftermathPackages,
        NextSessionCarryForwardProjection? nextSessionCarryForward)
    {
        ContinuitySnapshotRef? continuity = campaign.LatestContinuity;
        CampaignConsequenceProjection? leadConsequence = consequences
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        RosterTransferProjection? leadTransfer = rosterTransfers
            .OrderByDescending(static item => item.TransferredAtUtc)
            .FirstOrDefault();
        GovernedPrepLaunchProjection? leadPrepLaunch = prepLaunches
            .OrderByDescending(static item => item.LaunchedAtUtc)
            .FirstOrDefault();
        TravelPrefetchReceiptProjection? leadTravelPrefetch = travelPrefetchReceipts
            .OrderByDescending(static item => item.StagedAtUtc)
            .FirstOrDefault();
        AftermathRecapPackageProjection[] orderedAftermathPackages = aftermathPackages
            .OrderByDescending(static item => item.GeneratedAtUtc)
            .ToArray();
        AftermathRecapPackageProjection? leadAftermathPackage = orderedAftermathPackages
            .FirstOrDefault(item => !IsAftermathPackageKind(item, "downtime_brief"))
            ?? orderedAftermathPackages.FirstOrDefault();
        AftermathRecapPackageProjection? leadDowntimePackage = orderedAftermathPackages
            .FirstOrDefault(item => IsAftermathPackageKind(item, "downtime_brief"));
        string? leadAftermathPackageId = leadAftermathPackage is null ? null : ResolveAftermathPackageIdentity(leadAftermathPackage);
        string? leadDowntimePackageId = leadDowntimePackage is null ? null : ResolveAftermathPackageIdentity(leadDowntimePackage);
        if (leadAftermathPackage is not null
            && leadDowntimePackage is not null
            && string.Equals(leadAftermathPackageId, leadDowntimePackageId, StringComparison.OrdinalIgnoreCase))
        {
            leadAftermathPackage = null;
        }

        if (continuity is null
            && nextSessionCarryForward is null
            && leadConsequence is null
            && leadTransfer is null
            && leadPrepLaunch is null
            && leadTravelPrefetch is null
            && leadAftermathPackage is null
            && leadDowntimePackage is null
            && activeScene is null
            && leadObjective is null)
        {
            return null;
        }

        DateTimeOffset updatedAtUtc = new[]
            {
                continuity?.CapturedAtUtc,
                nextSessionCarryForward?.UpdatedAtUtc,
                leadConsequence?.UpdatedAtUtc,
                leadTransfer?.TransferredAtUtc,
                leadPrepLaunch?.LaunchedAtUtc,
                leadTravelPrefetch?.StagedAtUtc,
                leadAftermathPackage?.GeneratedAtUtc,
                leadDowntimePackage?.GeneratedAtUtc,
                activeScene?.UpdatedAtUtc,
                leadObjective?.UpdatedAtUtc
            }
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(DateTimeOffset.UtcNow)
            .Max();

        return new CampaignMemoryProjection(
            MemoryId: StableId("campaign-memory", $"{campaign.CampaignId}:{updatedAtUtc.ToUnixTimeMilliseconds()}"),
            Label: "Campaign memory",
            Summary: BuildCampaignMemorySummary(campaign.Name, nextSessionCarryForward, leadConsequence, leadTransfer, leadPrepLaunch, leadTravelPrefetch, leadAftermathPackage, leadDowntimePackage),
            ReturnSummary: nextSessionCarryForward?.ReturnSummary ?? continuity?.Summary ?? campaign.Summary,
            NextSafeAction: nextSessionCarryForward?.NextSafeAction ?? nextSafeAction,
            EvidenceLines: FinalizeLines(
            [
                continuity?.Summary ?? campaign.Summary,
                activeScene is null ? string.Empty : $"{activeScene.Title} is still live on {(leadRun?.Title ?? campaign.Name)} at {activeScene.Revision}.",
                leadObjective is null ? string.Empty : $"{leadObjective.Title} remains {leadObjective.Status} with {leadObjective.Pressure} pressure.",
                nextSessionCarryForward?.Summary ?? string.Empty,
                leadAftermathPackage is null ? string.Empty : $"{leadAftermathPackage.Title}: {leadAftermathPackage.Summary}",
                leadDowntimePackage is null ? string.Empty : $"{leadDowntimePackage.Title}: {leadDowntimePackage.Summary}",
                leadConsequence is null ? string.Empty : $"{leadConsequence.Label}: {leadConsequence.Summary}",
                leadTransfer?.Summary ?? string.Empty,
                leadPrepLaunch?.Summary ?? string.Empty,
                leadTravelPrefetch?.PrefetchSummary ?? string.Empty,
                nextSessionCarryForward?.NextSafeAction ?? nextSafeAction
            ]),
            UpdatedAtUtc: updatedAtUtc);
    }

    private static string BuildCampaignMemorySummary(
        string campaignName,
        NextSessionCarryForwardProjection? nextSessionCarryForward,
        CampaignConsequenceProjection? leadConsequence,
        RosterTransferProjection? leadTransfer,
        GovernedPrepLaunchProjection? leadPrepLaunch,
        TravelPrefetchReceiptProjection? leadTravelPrefetch,
        AftermathRecapPackageProjection? leadAftermathPackage,
        AftermathRecapPackageProjection? leadDowntimePackage)
    {
        List<string> anchors = [];
        if (nextSessionCarryForward is not null)
        {
            anchors.Add("next-session return");
        }

        if (leadConsequence is not null)
        {
            anchors.Add("governed consequence");
        }

        if (leadAftermathPackage is not null)
        {
            anchors.Add(NormalizeAftermathPackageKind(leadAftermathPackage.PackageKind) switch
            {
                "replay_timeline" => "replay package",
                "after_action_report" => "after-action report",
                _ => "aftermath recap"
            });
        }

        if (leadDowntimePackage is not null)
        {
            anchors.Add("downtime brief");
        }

        if (leadPrepLaunch is not null)
        {
            anchors.Add("prep binding");
        }

        if (leadTravelPrefetch is not null)
        {
            anchors.Add("travel prefetch");
        }

        if (leadTransfer is not null)
        {
            anchors.Add("roster audit");
        }

        if (anchors.Count == 0)
        {
            return $"{campaignName} keeps the latest continuity snapshot on one governed memory lane, but richer recap, consequence, and prep follow-through still need their first durable receipt.";
        }

        return $"{campaignName} keeps {JoinWithOxfordComma(anchors.Take(4).ToArray())} on one governed memory lane so return, recap, and follow-through do not collapse back to one-off notes.";
    }

    private static string JoinWithOxfordComma(IReadOnlyList<string> values)
        => values.Count switch
        {
            0 => string.Empty,
            1 => values[0],
            2 => $"{values[0]} and {values[1]}",
            _ => $"{string.Join(", ", values.Take(values.Count - 1))}, and {values[^1]}"
        };

    private static IReadOnlyList<WorkspaceChangePacketProjection> BuildWorkspaceChangePackets(
        CampaignProjection campaign,
        IReadOnlyList<PublicationSafeProjection> recapShelf,
        RunProjection? leadRun,
        SceneProjection? activeScene,
        ObjectiveProjection? leadObjective,
        IReadOnlyList<RosterTransferProjection> rosterTransfers,
        IReadOnlyList<GovernedPrepLaunchProjection> prepLaunches,
        IReadOnlyList<TravelPrefetchReceiptProjection> travelPrefetchReceipts,
        IReadOnlyList<AftermathRecapPackageProjection> aftermathPackages,
        NextSessionCarryForwardProjection? nextSessionCarryForward)
    {
        List<WorkspaceChangePacketProjection> packets = [];
        if (nextSessionCarryForward is not null)
        {
            string carryForwardPacketId = ResolveChangePacketIdentity(
                nextSessionCarryForward.CarryForwardId,
                StableId("packet", $"{campaign.CampaignId}:carry-forward"));
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: carryForwardPacketId,
                Kind: "next_session_carry_forward",
                Label: nextSessionCarryForward.Label,
                Summary: nextSessionCarryForward.Summary,
                UpdatedAtUtc: nextSessionCarryForward.UpdatedAtUtc));
        }

        if (campaign.LatestContinuity is not null)
        {
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:continuity"),
                Kind: "continuity",
                Label: "Continuity snapshot",
                Summary: campaign.LatestContinuity.Summary,
                UpdatedAtUtc: campaign.LatestContinuity.CapturedAtUtc));
        }

        if (activeScene is not null && leadRun is not null)
        {
            string activeSceneId = ResolveChangePacketIdentity(
                activeScene.SceneId,
                StableId("scene", campaign.CampaignId));
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:scene:{activeSceneId}"),
                Kind: "scene",
                Label: "Active scene",
                Summary: $"{activeScene.Title} is live on {leadRun.Title} at {activeScene.Revision}.",
                UpdatedAtUtc: activeScene.UpdatedAtUtc));
        }

        if (leadObjective is not null)
        {
            string leadObjectiveId = ResolveChangePacketIdentity(
                leadObjective.ObjectiveId,
                StableId("objective", campaign.CampaignId));
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:objective:{leadObjectiveId}"),
                Kind: "objective",
                Label: "Objective pressure",
                Summary: $"{leadObjective.Title} remains {leadObjective.Status} with {leadObjective.Pressure} pressure.",
                UpdatedAtUtc: leadObjective.UpdatedAtUtc));
        }

        RosterTransferProjection? rosterTransfer = rosterTransfers
            .OrderByDescending(static item => item.TransferredAtUtc)
            .FirstOrDefault();
        if (rosterTransfer is not null)
        {
            string rosterTransferId = ResolveChangePacketIdentity(
                rosterTransfer.TransferId,
                StableId("transfer", campaign.CampaignId));
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:transfer:{rosterTransferId}"),
                Kind: "roster_transfer",
                Label: "Roster transfer",
                Summary: rosterTransfer.Summary,
                UpdatedAtUtc: rosterTransfer.TransferredAtUtc));
        }

        GovernedPrepLaunchProjection? prepLaunch = prepLaunches
            .OrderByDescending(static item => item.LaunchedAtUtc)
            .FirstOrDefault();
        if (prepLaunch is not null)
        {
            string prepLaunchId = ResolveChangePacketIdentity(
                prepLaunch.LaunchId,
                StableId("prep-launch", campaign.CampaignId));
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:prep-launch:{prepLaunchId}"),
                Kind: "prep_launch",
                Label: "GM prep launch",
                Summary: prepLaunch.Summary,
                UpdatedAtUtc: prepLaunch.LaunchedAtUtc));
        }

        TravelPrefetchReceiptProjection? travelPrefetch = travelPrefetchReceipts
            .OrderByDescending(static item => item.StagedAtUtc)
            .FirstOrDefault();
        if (travelPrefetch is not null)
        {
            string travelPrefetchReceiptId = ResolveChangePacketIdentity(
                travelPrefetch.ReceiptId,
                StableId("travel-prefetch", campaign.CampaignId));
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:travel-prefetch:{travelPrefetchReceiptId}"),
                Kind: "travel_prefetch",
                Label: "Travel prefetch staged",
                Summary: travelPrefetch.PrefetchSummary,
                UpdatedAtUtc: travelPrefetch.StagedAtUtc));
        }

        AftermathRecapPackageProjection[] orderedAftermathPackages = aftermathPackages
            .OrderByDescending(static item => item.GeneratedAtUtc)
            .ToArray();
        AftermathRecapPackageProjection? replayPackage = orderedAftermathPackages
            .FirstOrDefault(item => IsAftermathPackageKind(item, "replay_timeline"));
        AftermathRecapPackageProjection? nonReplayPackage = orderedAftermathPackages
            .FirstOrDefault(item => !IsAftermathPackageKind(item, "replay_timeline"));
        AftermathRecapPackageProjection? downtimePackage = orderedAftermathPackages
            .FirstOrDefault(item => IsAftermathPackageKind(item, "downtime_brief"));
        AftermathRecapPackageProjection? aftermathPackage = orderedAftermathPackages
            .FirstOrDefault(item =>
                !IsAftermathPackageKind(item, "replay_timeline")
                && !IsAftermathPackageKind(item, "downtime_brief"));
        foreach (AftermathRecapPackageProjection package in new[] { replayPackage, downtimePackage, aftermathPackage }
                     .Where(static item => item is not null)
                     .Cast<AftermathRecapPackageProjection>()
                     .DistinctBy(static package => ResolveAftermathPackageIdentity(package), StringComparer.OrdinalIgnoreCase))
        {
            string packageId = ResolveAftermathPackageIdentity(package);
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:aftermath:{packageId}"),
                Kind: DescribeAftermathChangePacketKind(package.PackageKind),
                Label: DescribeAftermathChangeLabel(package.PackageKind),
                Summary: package.Summary,
                UpdatedAtUtc: package.GeneratedAtUtc));
        }

        PublicationSafeProjection? recap = recapShelf.FirstOrDefault();
        if (recap is not null && nonReplayPackage is null)
        {
            string recapProjectionId = ResolveChangePacketIdentity(
                recap.ProjectionId,
                StableId("projection", campaign.CampaignId));
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:recap:{recapProjectionId}"),
                Kind: "artifact",
                Label: recap.Label,
                Summary: recap.Summary,
                UpdatedAtUtc: campaign.UpdatedAtUtc));
        }

        return packets
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .Take(6)
            .ToArray();
    }

    private static PublicationSafeProjection BuildAftermathRecapShelfProjection(AftermathRecapPackageProjection package)
        => new(
            ProjectionId: ResolveAftermathPackageIdentity(package),
            Kind: package.PackageKind,
            Label: package.Title,
            Summary: package.Summary,
            ArtifactId: package.ArtifactId,
            ProvenanceSummary: string.IsNullOrWhiteSpace(package.ProvenanceSummary)
                ? BuildAftermathRecapProvenanceSummary(package)
                : package.ProvenanceSummary,
            AuditSummary: string.IsNullOrWhiteSpace(package.AuditSummary)
                ? BuildAftermathRecapAuditSummary(package)
                : package.AuditSummary);

    private static IReadOnlyList<PublicationSafeProjection> EnrichWorkspaceRecapShelf(
        CampaignProjection campaign,
        string workspaceId,
        IReadOnlyList<PublicationSafeProjection> recapShelf,
        string nextSafeAction)
    {
        if (recapShelf.Count == 0)
        {
            return recapShelf;
        }

        const string publicationState = "preview_ready";
        var (trustBand, discoverable, _, _, _) = BuildCreatorPublicationTrustPosture(publicationState, campaign.Visibility);
        string ownershipSummary = $"Shared {campaign.Visibility.Replace('_', ' ')} publication lane stays attached to {campaign.Name}.";
        string publicationSummary = "Preview-ready shared publication keeps recap-safe outputs reviewable before they become live.";

        return recapShelf
            .Select(item => item with
            {
                Audience = string.IsNullOrWhiteSpace(item.Audience)
                    ? "campaign"
                    : item.Audience,
                OwnershipSummary = string.IsNullOrWhiteSpace(item.OwnershipSummary)
                    ? ownershipSummary
                    : item.OwnershipSummary,
                PublicationState = string.IsNullOrWhiteSpace(item.PublicationState)
                    ? publicationState
                    : item.PublicationState,
                TrustBand = string.IsNullOrWhiteSpace(item.TrustBand)
                    ? trustBand
                    : item.TrustBand,
                Discoverable = item.Discoverable || discoverable,
                PublicationSummary = string.IsNullOrWhiteSpace(item.PublicationSummary)
                    ? publicationSummary
                    : item.PublicationSummary,
                CreatorPublicationId = ResolveChangePacketIdentity(
                    item.CreatorPublicationId,
                    StableId("publication", $"{workspaceId}:{ResolveRecapProjectionIdentity(item)}")),
                NextSafeAction = string.IsNullOrWhiteSpace(item.NextSafeAction)
                    ? nextSafeAction
                    : item.NextSafeAction,
                ProvenanceSummary = item.ProvenanceSummary,
                AuditSummary = item.AuditSummary
            })
            .ToArray();
    }

    private static string DescribeAftermathChangeLabel(string packageKind)
        => packageKind.Trim().ToLowerInvariant() switch
        {
            "replay_timeline" => "Replay timeline",
            "downtime_brief" => "Downtime brief",
            "after_action_report" => "After-action report",
            _ => "Aftermath recap package"
        };

    private static string DescribeAftermathChangePacketKind(string packageKind)
        => packageKind.Trim().ToLowerInvariant() switch
        {
            "replay_timeline" => "replay_package",
            _ => "aftermath_recap"
        };

    private static bool IsAftermathPackageKind(AftermathRecapPackageProjection package, string kind)
        => string.Equals(NormalizeAftermathPackageKind(package.PackageKind), kind, StringComparison.OrdinalIgnoreCase);

    private static string ResolveChangePacketIdentity(string? identity, string fallback)
        => AccountService.NormalizeOptional(identity) ?? fallback;

    private static string ResolveRosterTransferRequestIdentity(string? identity, string fieldLabel)
        => AccountService.NormalizeOptional(identity)
            ?? throw new KeyNotFoundException($"Unknown {fieldLabel}: {identity}");

    private static string ResolveRecapProjectionIdentity(PublicationSafeProjection recap)
        => ResolveChangePacketIdentity(
            recap.ProjectionId,
            StableId("projection", $"{AccountService.NormalizeOptional(recap.Kind) ?? "recap"}:{AccountService.NormalizeOptional(recap.Label) ?? "entry"}"));

    private static string ResolveAftermathPackageIdentity(AftermathRecapPackageProjection package)
    {
        string? packageId = AccountService.NormalizeOptional(package.PackageId);
        if (packageId is not null)
        {
            return packageId;
        }

        return StableId("aftermath-package",
            $"{AccountService.NormalizeOptional(package.WorkspaceId) ?? "workspace"}:" +
            $"{AccountService.NormalizeOptional(package.CampaignId) ?? "campaign"}:" +
            $"{package.GeneratedAtUtc.ToUnixTimeMilliseconds()}:" +
            $"{NormalizeAftermathPackageKind(package.PackageKind)}:" +
            $"{AccountService.NormalizeOptional(package.ArtifactId) ?? "artifact"}");
    }

    private static string NormalizeAftermathPackageKind(string? packageKind)
        => AccountService.NormalizeOptional(packageKind)?.ToLowerInvariant() ?? string.Empty;

    private static string BuildAftermathRecapProvenanceSummary(AftermathRecapPackageProjection package)
    {
        if (!string.IsNullOrWhiteSpace(package.ProvenanceSummary))
        {
            return package.ProvenanceSummary!;
        }

        string runScope = package.EvidenceLines.FirstOrDefault(static line => line.StartsWith("Run scope:", StringComparison.OrdinalIgnoreCase))
            ?? (string.IsNullOrWhiteSpace(package.RunTitle)
                ? "Run scope: campaign-wide aftermath."
                : $"Run scope: {package.RunTitle}.");
        string continuity = package.EvidenceLines.FirstOrDefault(static line => line.StartsWith("Continuity:", StringComparison.OrdinalIgnoreCase))
            ?? "Continuity: governed return lane remains attached to the same campaign spine.";
        string artifactDescriptor = BuildAftermathArtifactDescriptor(package);
        return $"{runScope} {continuity} {artifactDescriptor} stays attached to package {ResolveAftermathPackageIdentity(package)}.";
    }

    private static string BuildAftermathRecapAuditSummary(AftermathRecapPackageProjection package)
    {
        if (!string.IsNullOrWhiteSpace(package.AuditSummary))
        {
            return package.AuditSummary!;
        }

        string packageKind = package.EvidenceLines.FirstOrDefault(static line => line.StartsWith("Package kind:", StringComparison.OrdinalIgnoreCase))
            ?? $"Package kind: {package.PackageKind}.";
        string activeScene = package.EvidenceLines.FirstOrDefault(static line => line.StartsWith("Active scene:", StringComparison.OrdinalIgnoreCase))
            ?? "Active scene: no pinned scene.";
        return $"Generated {package.GeneratedAtUtc:yyyy-MM-dd HH:mm} UTC by {package.InitiatedByUserId}. {packageKind} {activeScene} {BuildAftermathArtifactDescriptor(package)}";
    }

    private static string BuildAftermathArtifactDescriptor(AftermathRecapPackageProjection package)
    {
        if (string.IsNullOrWhiteSpace(package.ArtifactKind)
            && string.IsNullOrWhiteSpace(package.ArtifactVersion)
            && string.IsNullOrWhiteSpace(package.ArtifactVisibility)
            && string.IsNullOrWhiteSpace(package.ArtifactTrustTier)
            && string.IsNullOrWhiteSpace(package.ArtifactRulesetId))
        {
            return $"Artifact {package.ArtifactId}";
        }

        return $"Artifact {package.ArtifactId} ({package.ArtifactKind ?? "artifact"} {package.ArtifactVersion ?? "current"}, {package.ArtifactVisibility ?? "shared"}, {package.ArtifactTrustTier ?? "curated"}, {package.ArtifactRulesetId ?? "sr5"})";
    }

    private static string ResolveArtifactRulesetId(RuleEnvironmentRef ruleEnvironment)
    {
        string candidate = ruleEnvironment.CompatibilityFingerprint;
        if (string.IsNullOrWhiteSpace(candidate))
        {
            candidate = ruleEnvironment.EnvironmentId;
        }

        if (!string.IsNullOrWhiteSpace(candidate))
        {
            string[] separators = [".", ":", "/", "-", "_"];
            foreach (string separator in separators)
            {
                int index = candidate.IndexOf(separator, StringComparison.Ordinal);
                if (index > 0)
                {
                    return candidate[..index].Trim();
                }
            }

            return candidate.Trim();
        }

        return "sr5";
    }

    private static string DescribePrepLaunchSummary(
        CampaignWorkspaceProjection workspace,
        string packetTitle,
        RunProjection? targetRun,
        SceneProjection? targetScene)
    {
        if (targetRun is null)
        {
            return $"Bound {packetTitle} to {workspace.CampaignName} as campaign-wide governed prep truth.";
        }

        if (targetScene is null)
        {
            return $"Bound {packetTitle} to {targetRun.Title} without recreating local shadow prep notes.";
        }

        return $"Bound {packetTitle} to {targetRun.Title} / {targetScene.Title} without recreating local shadow prep notes.";
    }

    private static IReadOnlyList<CampaignConsequenceProjection> BuildCampaignConsequences(
        BoostCampaignDto sponsorCampaign,
        GroupDto group,
        CrewProjection crew,
        IReadOnlyList<RunnerDossierProjection> memberDossiers,
        RunProjection run,
        ContinuitySnapshotRef continuity)
    {
        SceneProjection? activeScene = ResolveActiveScene(run) ?? run.Scenes
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        ObjectiveProjection? leadObjective = run.Objectives
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        PublicationSafeProjection[] outputs = memberDossiers
            .SelectMany(static item => item.Projections)
            .Distinct()
            .ToArray();
        int artifactCount = outputs.Count(static item => !string.IsNullOrWhiteSpace(item.ArtifactId));
        DateTimeOffset dossierUpdatedAt = memberDossiers.Count == 0
            ? continuity.CapturedAtUtc
            : memberDossiers.Max(static item => item.UpdatedAtUtc);
        DateTimeOffset outputUpdatedAt = new[]
        {
            run.UpdatedAtUtc,
            continuity.CapturedAtUtc,
            dossierUpdatedAt
        }.Max();

        List<CampaignConsequenceProjection> consequences = [];

        if (leadObjective is not null && activeScene is not null)
        {
            consequences.Add(new CampaignConsequenceProjection(
                ConsequenceId: StableId("consequence", $"{sponsorCampaign.CampaignId}:heat"),
                Kind: "heat",
                Label: "Heat posture",
                State: leadObjective.Pressure,
                Summary: $"{activeScene.Title} keeps operational heat at {leadObjective.Pressure} while {leadObjective.Title} remains {leadObjective.Status}.",
                EvidenceLines:
                [
                    $"{leadObjective.Title} is {leadObjective.Status} with {leadObjective.Pressure} pressure.",
                    $"{activeScene.Title} is the live scene at revision {activeScene.Revision}.",
                    continuity.Summary
                ],
                Receipts:
                [
                    new CampaignConsequenceReceipt(
                        ReceiptId: leadObjective.ObjectiveId,
                        SourceKind: "objective",
                        Summary: leadObjective.Summary),
                    new CampaignConsequenceReceipt(
                        ReceiptId: activeScene.SceneId,
                        SourceKind: "scene",
                        Summary: activeScene.Summary),
                    new CampaignConsequenceReceipt(
                        ReceiptId: continuity.SnapshotId,
                        SourceKind: "continuity",
                        Summary: continuity.Summary)
                ],
                UpdatedAtUtc: new[] { leadObjective.UpdatedAtUtc, activeScene.UpdatedAtUtc, continuity.CapturedAtUtc }.Max()));
        }

        consequences.Add(new CampaignConsequenceProjection(
            ConsequenceId: StableId("consequence", $"{sponsorCampaign.CampaignId}:faction"),
            Kind: "faction",
            Label: "Faction standing",
            State: string.Equals(group.Visibility, "private", StringComparison.OrdinalIgnoreCase) ? "trusted" : "shared",
            Summary: $"{group.Name} remains the governed sponsor faction for {sponsorCampaign.Title}, and crew membership stays attached to that shared campaign truth.",
            EvidenceLines:
            [
                $"{crew.Name} has {crew.Members.Count} governed crew assignment(s).",
                $"{group.Name} is operating at {group.Visibility} visibility.",
                $"{sponsorCampaign.Title} keeps sponsorship and continuity in the same campaign record."
            ],
            Receipts:
            [
                new CampaignConsequenceReceipt(
                    ReceiptId: group.GroupId,
                    SourceKind: "group",
                    Summary: $"{group.Name} sponsor group"),
                new CampaignConsequenceReceipt(
                    ReceiptId: crew.CrewId,
                    SourceKind: "crew",
                    Summary: $"{crew.Members.Count} crew assignment(s) stay attached to the campaign"),
                new CampaignConsequenceReceipt(
                    ReceiptId: sponsorCampaign.CampaignId,
                    SourceKind: "campaign",
                    Summary: sponsorCampaign.Title)
            ],
            UpdatedAtUtc: new[] { crew.UpdatedAtUtc, run.UpdatedAtUtc, continuity.CapturedAtUtc }.Max()));

        consequences.Add(new CampaignConsequenceProjection(
            ConsequenceId: StableId("consequence", $"{sponsorCampaign.CampaignId}:contact"),
            Kind: "contact",
            Label: "Contact network",
            State: memberDossiers.Count >= 2 ? "networked" : "thin",
            Summary: $"{memberDossiers.Count} dossier-backed runner contact lane(s) remain attached to the same campaign return path instead of drifting into local notes.",
            EvidenceLines: memberDossiers
                .Take(3)
                .Select(static dossier => $"{dossier.DisplayName} remains pinned to the shared campaign continuity spine.")
                .Concat([continuity.Summary])
                .ToArray(),
            Receipts: memberDossiers
                .Take(3)
                .Select(static dossier => new CampaignConsequenceReceipt(
                    ReceiptId: dossier.DossierId,
                    SourceKind: "dossier",
                    Summary: $"{dossier.DisplayName} ({dossier.RunnerHandle})"))
                .Concat(
                [
                    new CampaignConsequenceReceipt(
                        ReceiptId: continuity.SnapshotId,
                        SourceKind: "continuity",
                        Summary: continuity.Summary)
                ])
                .ToArray(),
            UpdatedAtUtc: new[] { dossierUpdatedAt, continuity.CapturedAtUtc }.Max()));

        consequences.Add(new CampaignConsequenceProjection(
            ConsequenceId: StableId("consequence", $"{sponsorCampaign.CampaignId}:reputation"),
            Kind: "reputation",
            Label: "Reputation posture",
            State: artifactCount > 0 ? "tracked" : "pending",
            Summary: $"{outputs.Length} publication-safe dossier and runboard artifact(s) keep reputation changes reviewable instead of disappearing into recap prose.",
            EvidenceLines:
            [
                $"{artifactCount} artifact-backed projection(s) are already attached to the active dossiers.",
                $"{memberDossiers.Count} dossier(s) contribute publication-safe outputs to this campaign.",
                continuity.Summary
            ],
            Receipts: outputs
                .Take(3)
                .Select(static output => new CampaignConsequenceReceipt(
                    ReceiptId: output.ArtifactId ?? output.ProjectionId,
                    SourceKind: output.Kind,
                    Summary: output.Summary))
                .Concat(
                [
                    new CampaignConsequenceReceipt(
                        ReceiptId: continuity.SnapshotId,
                        SourceKind: "continuity",
                        Summary: continuity.Summary)
                ])
                .ToArray(),
            UpdatedAtUtc: outputUpdatedAt));

        return consequences
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
    }

    private static IReadOnlyList<string> BuildBuildLabWatchouts(
        CampaignWorkspaceProjection? workspace,
        IReadOnlyList<PublicationSafeProjection> outputs,
        WorkspaceRestoreProjection restore)
    {
        var watchouts = new List<string>();

        if (workspace is null)
        {
            watchouts.Add("No governed campaign workspace is attached yet, so the handoff is still dossier-first rather than table-return first.");
        }

        if (outputs.Count == 0)
        {
            watchouts.Add("No publication-safe recap or dossier output is attached yet, so return and support still rely on the dossier summary alone.");
        }

        watchouts.AddRange(restore.ConflictSummaries);

        if (restore.ClaimedDevices.Count == 0)
        {
            watchouts.Add("No claimed install is attached yet, so release-aware support closure still depends on manual install details.");
        }

        return watchouts
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static IReadOnlyList<RulesNavigatorAnswerProjection> BuildRulesNavigatorEntries(
        IReadOnlyList<CampaignWorkspaceProjection> workspaces,
        IReadOnlyList<CommunityOperatorProjection> operations)
    {
        var workspace = workspaces.FirstOrDefault();
        var operation = operations.FirstOrDefault();
        var entries = new List<RulesNavigatorAnswerProjection>();

        if (workspace is not null)
        {
            IReadOnlyList<RulesetEnvironmentDiffProjection> diffs = BuildWorkspaceRulesNavigatorDiffs(workspace);
            entries.Add(new RulesNavigatorAnswerProjection(
                EntryId: StableId("rules", workspace.WorkspaceId),
                Question: "Why is this campaign return pinned to the current rule environment?",
                ShortAnswer: "Because campaign continuity and support closure both follow the same campaign-approved compatibility fingerprint.",
                BeforeSummary: diffs[0].BeforeSummary,
                AfterSummary: diffs[0].AfterSummary,
                ExplainEntryId: $"rules.navigator.{workspace.WorkspaceId}",
                ProvenanceLabel: $"{workspace.RuleEnvironment.OwnerScope} scope · {workspace.RuleEnvironment.CompatibilityFingerprint}",
                EvidenceLines:
                [
                    $"{workspace.RuleEnvironment.CompatibilityFingerprint} is the active compatibility fingerprint.",
                    $"{workspace.ReadinessCues.Count} campaign readiness cue(s) were computed from the same campaign workspace.",
                    workspace.ReturnSummary
                ],
                SupportReuseHints:
                [
                    "Support can reuse this answer when a case asks which rules posture is live on the current channel.",
                    "Operator review can link the same evidence when deciding whether to freeze or reroute a campaign change."
                ],
                Diffs: diffs,
                Studio: BuildRuleEnvironmentStudio(
                    workspace.RuleEnvironment,
                    workspace.CampaignName,
                    $"{workspace.CampaignName} workspace",
                    $"{workspace.CampaignName} keeps {workspace.RuleEnvironment.CompatibilityFingerprint} as the governed campaign answer until the next promoted fingerprint replaces it.")));
        }

        if (operation is not null)
        {
            IReadOnlyList<RulesetEnvironmentDiffProjection> diffs = BuildOperatorRulesNavigatorDiffs(operation);
            entries.Add(new RulesNavigatorAnswerProjection(
                EntryId: StableId("rules", operation.GroupId),
                Question: "How does group visibility change the campaign operator posture?",
                ShortAnswer: "Operator permissions stay subordinate to campaign visibility and the campaign-approved rule environment.",
                BeforeSummary: diffs[0].BeforeSummary,
                AfterSummary: diffs[0].AfterSummary,
                ExplainEntryId: $"rules.navigator.group.{operation.GroupId}",
                ProvenanceLabel: $"{operation.GroupType} group · {operation.OperatorRole}",
                EvidenceLines:
                [
                    $"{operation.MemberCount} member(s) share this governed group.",
                    $"{operation.ActiveCampaignCount} active campaign(s) inherit the same operator posture.",
                    $"{operation.RuleEnvironment.CompatibilityFingerprint} is the group rule-environment fingerprint."
                ],
                SupportReuseHints:
                [
                    "Support can reuse this answer for permissions or campaign-visibility questions.",
                    "Hub can cite the same operator posture in account and organizer surfaces."
                ],
                Diffs: diffs,
                Studio: BuildRuleEnvironmentStudio(
                    operation.RuleEnvironment,
                    operation.GroupName,
                    $"{operation.GroupName} organizer rail",
                    $"{operation.GroupName} keeps {operation.RuleEnvironment.CompatibilityFingerprint} as the lineage anchor while governed operator decisions stay on one backbone.")));
        }

        return entries;
    }

    private static IReadOnlyList<RulesetEnvironmentDiffProjection> BuildWorkspaceRulesNavigatorDiffs(
        CampaignWorkspaceProjection workspace)
    {
        string explainRoot = $"rules.navigator.{workspace.WorkspaceId}";
        string readinessReason = ResolvePriorityReadinessCue(workspace.ReadinessCues, requireSummary: true)?.Summary
            ?? "The campaign workspace still computes readiness from the same governed return context.";

        return
        [
            new RulesetEnvironmentDiffProjection(
                DiffId: StableId("rules-diff", $"{workspace.WorkspaceId}:campaign-return"),
                Label: "Campaign return",
                BeforeSummary: "Before the sandbox rail is promoted, restore posture is review-heavy and support has to caveat the answer path.",
                AfterSummary: $"After campaign approval, {workspace.RuleEnvironment.CompatibilityFingerprint} becomes the grounded answer path for build, play, and support.",
                ReasonSummary: workspace.ReturnSummary,
                ExplainEntryId: $"{explainRoot}:campaign-return"),
            new RulesetEnvironmentDiffProjection(
                DiffId: StableId("rules-diff", $"{workspace.WorkspaceId}:readiness"),
                Label: "Campaign readiness",
                BeforeSummary: "Before the rule environment is explicit, readiness cues can drift away from the live return path.",
                AfterSummary: $"After campaign approval, {workspace.ReadinessCues.Count} readiness cue(s) stay tied to {workspace.RuleEnvironment.CompatibilityFingerprint} instead of a side calculation.",
                ReasonSummary: readinessReason,
                ExplainEntryId: $"{explainRoot}:readiness")
        ];
    }

    private static IReadOnlyList<RulesetEnvironmentDiffProjection> BuildOperatorRulesNavigatorDiffs(
        CommunityOperatorProjection operation)
    {
        string explainRoot = $"rules.navigator.group.{operation.GroupId}";
        string returnReason = operation.RecentReturnSummaries.FirstOrDefault(static item => !string.IsNullOrWhiteSpace(item))
            ?? operation.CampaignReturnSummary;

        return
        [
            new RulesetEnvironmentDiffProjection(
                DiffId: StableId("rules-diff", $"{operation.GroupId}:visibility"),
                Label: "Operator visibility",
                BeforeSummary: "Before visibility is explicit, group operations tend to rely on memory and side channels.",
                AfterSummary: $"After visibility is explicit, {operation.CampaignVisibilitySummary} becomes part of the grounded decision surface.",
                ReasonSummary: operation.OperationsSummary,
                ExplainEntryId: $"{explainRoot}:visibility"),
            new RulesetEnvironmentDiffProjection(
                DiffId: StableId("rules-diff", $"{operation.GroupId}:rule-environment"),
                Label: "Group rule environment",
                BeforeSummary: "Before the group rule environment is explicit, campaign operator decisions can drift into one-off interpretation.",
                AfterSummary: $"After campaign approval, {operation.RuleEnvironment.CompatibilityFingerprint} anchors {operation.ActiveCampaignCount} active campaign(s) on the same operator rail.",
                ReasonSummary: returnReason,
                ExplainEntryId: $"{explainRoot}:rule-environment")
        ];
    }

    private static RuleEnvironmentStudioProjection BuildRuleEnvironmentStudio(
        RuleEnvironmentRef environment,
        string scopeLabel,
        string rollbackScope,
        string lineageSummary)
    {
        string currentStage = ResolveRuleEnvironmentLifecycleStage(environment);
        string promotionTargetStage = ResolveRuleEnvironmentPromotionTargetStage(currentStage);
        string currentStageLabel = DescribeRuleEnvironmentLifecycleStage(currentStage);
        string promotionTargetLabel = DescribeRuleEnvironmentLifecycleStage(promotionTargetStage);
        string lifecycleLabelLower = currentStageLabel.ToLowerInvariant();

        string promotionSummary = currentStage switch
        {
            RuleEnvironmentLifecycleStages.Sandbox => $"Promote {environment.CompatibilityFingerprint} from the sandbox rail into campaign-approved truth once {scopeLabel} is ready to make one governed answer path live.",
            RuleEnvironmentLifecycleStages.CampaignApproved => $"Promote {environment.CompatibilityFingerprint} from the campaign-approved rail to the published rail only when broader governed reuse should stay visible outside {scopeLabel}.",
            RuleEnvironmentLifecycleStages.Published => $"{environment.CompatibilityFingerprint} is already on the published rail and ready for broader governed reuse.",
            _ => $"{environment.CompatibilityFingerprint} stays on the {lifecycleLabelLower} rail until the next governed promotion is explicit."
        };

        string rollbackSummary = currentStage switch
        {
            RuleEnvironmentLifecycleStages.Sandbox => $"Rollback keeps {environment.CompatibilityFingerprint} bounded to the sandbox rail for {rollbackScope} while validation and compatibility review continue.",
            _ => $"Rollback can re-pin {environment.CompatibilityFingerprint} on {rollbackScope} while the next promotion is reviewed."
        };

        return new RuleEnvironmentStudioProjection(
            CurrentStage: currentStage,
            CurrentStageLabel: currentStageLabel,
            PromotionTargetStage: promotionTargetStage,
            PromotionTargetLabel: promotionTargetLabel,
            PromotionSummary: promotionSummary,
            RollbackSummary: rollbackSummary,
            LineageSummary: lineageSummary,
            Stages: BuildRuleEnvironmentLifecycleSteps(environment, scopeLabel, currentStage, promotionTargetStage));
    }

    private static IReadOnlyList<RuleEnvironmentLifecycleStepProjection> BuildRuleEnvironmentLifecycleSteps(
        RuleEnvironmentRef environment,
        string scopeLabel,
        string currentStage,
        string promotionTargetStage)
    {
        return
        [
            BuildRuleEnvironmentLifecycleStep(
                RuleEnvironmentLifecycleStages.Sandbox,
                "Sandbox",
                $"Keep {environment.CompatibilityFingerprint} bounded while {scopeLabel} validates the next governed rules posture.",
                currentStage,
                promotionTargetStage),
            BuildRuleEnvironmentLifecycleStep(
                RuleEnvironmentLifecycleStages.CampaignApproved,
                "Campaign-approved",
                $"{scopeLabel} binds {environment.CompatibilityFingerprint} to build, play, support, and return on one governed rail.",
                currentStage,
                promotionTargetStage),
            BuildRuleEnvironmentLifecycleStep(
                RuleEnvironmentLifecycleStages.Published,
                "Published",
                $"{scopeLabel} promotes {environment.CompatibilityFingerprint} for broader governed reuse without minting a shadow rule environment.",
                currentStage,
                promotionTargetStage)
        ];
    }

    private static RuleEnvironmentLifecycleStepProjection BuildRuleEnvironmentLifecycleStep(
        string stageId,
        string label,
        string summary,
        string currentStage,
        string promotionTargetStage)
    {
        string status = string.Equals(stageId, currentStage, StringComparison.Ordinal)
            ? RuleEnvironmentLifecycleStepStatuses.Current
            : string.Equals(stageId, promotionTargetStage, StringComparison.Ordinal)
                ? RuleEnvironmentLifecycleStepStatuses.Next
                : GetRuleEnvironmentLifecycleStageOrder(stageId) < GetRuleEnvironmentLifecycleStageOrder(currentStage)
                    ? RuleEnvironmentLifecycleStepStatuses.Completed
                    : RuleEnvironmentLifecycleStepStatuses.Pending;

        return new RuleEnvironmentLifecycleStepProjection(stageId, label, status, summary);
    }

    private static string ResolveRuleEnvironmentLifecycleStage(RuleEnvironmentRef environment)
    {
        if (string.Equals(environment.ApprovalState, "published", StringComparison.OrdinalIgnoreCase))
        {
            return RuleEnvironmentLifecycleStages.Published;
        }

        if (string.Equals(environment.ApprovalState, "approved", StringComparison.OrdinalIgnoreCase))
        {
            return RuleEnvironmentLifecycleStages.CampaignApproved;
        }

        return RuleEnvironmentLifecycleStages.Sandbox;
    }

    private static string ResolveRuleEnvironmentPromotionTargetStage(string currentStage)
    {
        return currentStage switch
        {
            RuleEnvironmentLifecycleStages.Sandbox => RuleEnvironmentLifecycleStages.CampaignApproved,
            RuleEnvironmentLifecycleStages.CampaignApproved => RuleEnvironmentLifecycleStages.Published,
            RuleEnvironmentLifecycleStages.Published => RuleEnvironmentLifecycleStages.Published,
            _ => RuleEnvironmentLifecycleStages.CampaignApproved
        };
    }

    private static string DescribeRuleEnvironmentLifecycleStage(string stageId)
    {
        return stageId switch
        {
            RuleEnvironmentLifecycleStages.Sandbox => "Sandbox",
            RuleEnvironmentLifecycleStages.CampaignApproved => "Campaign-approved",
            RuleEnvironmentLifecycleStages.Published => "Published",
            _ => HumanizePhrase(stageId, "Review")
        };
    }

    private static int GetRuleEnvironmentLifecycleStageOrder(string stageId)
    {
        return stageId switch
        {
            RuleEnvironmentLifecycleStages.Sandbox => 0,
            RuleEnvironmentLifecycleStages.CampaignApproved => 1,
            RuleEnvironmentLifecycleStages.Published => 2,
            _ => -1
        };
    }

    private static IReadOnlyList<LegacyMigrationReceiptProjection> BuildMigrationReceipts(
        IReadOnlyList<RunnerDossierProjection> dossiers,
        IReadOnlyList<CampaignProjection> campaigns)
    {
        var campaignById = campaigns.ToDictionary(static item => item.CampaignId, StringComparer.OrdinalIgnoreCase);
        return dossiers
            .Select(dossier =>
            {
                campaignById.TryGetValue(dossier.CampaignId ?? string.Empty, out var campaign);
                return new LegacyMigrationReceiptProjection(
                    ReceiptId: StableId("migration", dossier.DossierId),
                    SourceKind: "legacy_character_file",
                    SourceId: $"legacy::{dossier.RunnerHandle}",
                    TargetDossierId: dossier.DossierId,
                    TargetCampaignId: dossier.CampaignId,
                    Summary: "Legacy imports now land in the living dossier and campaign spine, with risky and blocked fields called out instead of silently discarded.",
                    Fields:
                    [
                        new LegacyMigrationFieldProjection("identity", "Identity and handle", "safe", "Runner identity mapped cleanly into the living dossier."),
                        new LegacyMigrationFieldProjection("campaign-link", "Campaign continuity link", campaign is null ? "risky" : "safe", campaign is null ? "No active campaign was linked yet, so the dossier is ready but still waiting for a campaign workspace." : $"Linked to {campaign.Name} without breaking the continuity spine."),
                        new LegacyMigrationFieldProjection("legacy-notes", "Legacy notes blob", "blocked", "Opaque legacy notes require manual review before they can become provenance-backed dossier facts.")
                    ],
                    ImportedAtUtc: dossier.UpdatedAtUtc);
            })
            .Take(3)
            .ToArray();
    }

    private static IReadOnlyList<CreatorPublicationProjection> BuildCreatorPublications(
        IReadOnlyList<CampaignWorkspaceProjection> workspaces,
        IReadOnlyList<RunnerDossierProjection> dossiers,
        IReadOnlyList<BuildLabHandoffProjection> buildLabHandoffs)
    {
        return workspaces
            .SelectMany(workspace =>
            {
                var dossier = dossiers.FirstOrDefault(item => string.Equals(item.CampaignId, workspace.CampaignId, StringComparison.OrdinalIgnoreCase));
                var leadHandoff = buildLabHandoffs
                    .Where(item => string.Equals(item.CampaignId, workspace.CampaignId, StringComparison.OrdinalIgnoreCase))
                    .OrderByDescending(static item => item.UpdatedAtUtc)
                    .FirstOrDefault();
                const string publicationStatus = "preview_ready";
                var (trustBand, discoverable, trustSummary, discoverySummary, moderationSummary) = BuildCreatorPublicationTrustPosture(publicationStatus, workspace.Visibility);
                var watchouts = BuildCreatorPublicationWatchouts(workspace, leadHandoff);
                return workspace.RecapShelf
                    .Select(item => new
                    {
                        Item = item,
                        PublicationId = AccountService.NormalizeOptional(item.CreatorPublicationId)
                    })
                    .Where(static item => item.PublicationId is not null)
                    .Select(item =>
                    {
                        PublicationSafeProjection recap = item.Item;
                        string artifact = AccountService.NormalizeOptional(recap.ArtifactId)
                            ?? StableId("artifact", $"{workspace.WorkspaceId}:{ResolveRecapProjectionIdentity(recap)}");
                        string publicationKind = NormalizeCreatorPublicationKind(recap.Kind);
                        string nextSafeAction = !string.IsNullOrWhiteSpace(recap.NextSafeAction)
                            ? recap.NextSafeAction!
                            : !string.IsNullOrWhiteSpace(leadHandoff?.NextSafeAction)
                                ? leadHandoff.NextSafeAction
                                : workspace.NextSafeAction
                                    ?? "Review the grounded publication lane, then return through the shared campaign view before you publish or export it further.";
                        string campaignReturnSummary = DescribeSharedPublicationSummary(workspace, recap);
                        string supportClosureSummary = !string.IsNullOrWhiteSpace(leadHandoff?.SupportClosureSummary)
                            ? leadHandoff.SupportClosureSummary
                            : DescribeCreatorPublicationSupportClosure(workspace);
                        return new CreatorPublicationProjection(
                            PublicationId: item.PublicationId!,
                            Title: BuildCreatorPublicationTitle(workspace, dossier, recap, publicationKind),
                            Kind: publicationKind,
                            Summary: BuildCreatorPublicationSummary(workspace, recap, publicationKind),
                            CampaignId: workspace.CampaignId,
                            DossierId: dossier?.DossierId,
                            ArtifactId: artifact,
                            ProvenanceSummary: string.IsNullOrWhiteSpace(recap.ProvenanceSummary)
                                ? $"{workspace.RuleEnvironment.CompatibilityFingerprint} + {recap.Label}"
                                : recap.ProvenanceSummary!,
                            DiscoverySummary: discoverySummary,
                            Visibility: workspace.Visibility,
                            PublicationStatus: publicationStatus,
                            TrustBand: trustBand,
                            Discoverable: discoverable,
                            UpdatedAtUtc: workspace.LatestContinuity?.CapturedAtUtc ?? DateTimeOffset.UtcNow,
                            NextSafeAction: nextSafeAction,
                            CampaignReturnSummary: campaignReturnSummary,
                            SupportClosureSummary: supportClosureSummary,
                            BuildHandoffId: leadHandoff?.HandoffId,
                            Watchouts: watchouts,
                            LineageSummary: DescribeCreatorPublicationLineage(artifact, leadHandoff, workspace),
                            TrustSummary: trustSummary,
                            ComparisonSummary: DescribeCreatorPublicationComparisonSummary(leadHandoff),
                            ModerationSummary: moderationSummary);
                    });
            })
            .Where(publication => !string.IsNullOrWhiteSpace(publication.PublicationId))
            .GroupBy(static publication => publication.PublicationId, StringComparer.OrdinalIgnoreCase)
            .Select(static group => group
                .OrderByDescending(static publication => publication.UpdatedAtUtc)
                .First())
            .OrderByDescending(publication => CreatorPublicationProjectionPriority(publication.Kind))
            .ThenByDescending(static publication => publication.UpdatedAtUtc)
            .ThenBy(publication => publication.Title, StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static IReadOnlyList<CampaignWorkspaceProjection> AttachCreatorPublicationPosture(
        IReadOnlyList<CampaignWorkspaceProjection> workspaces,
        IReadOnlyList<CreatorPublicationProjection> creatorPublications)
    {
        var publicationsById = creatorPublications
            .Select(item => new
            {
                PublicationId = AccountService.NormalizeOptional(item.PublicationId),
                Publication = item
            })
            .Where(static item => item.PublicationId is not null)
            .GroupBy(static item => item.PublicationId!, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(
                static group => group.Key,
                static group => group
                    .OrderByDescending(static item => item.Publication.UpdatedAtUtc)
                    .First()
                    .Publication,
                StringComparer.OrdinalIgnoreCase);
        var publicationsByArtifactId = creatorPublications
            .Select(item => new
            {
                ArtifactId = AccountService.NormalizeOptional(item.ArtifactId),
                Publication = item
            })
            .Where(static item => item.ArtifactId is not null)
            .GroupBy(static item => item.ArtifactId!, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(
                static group => group.Key,
                static group => group
                    .OrderByDescending(static item => item.Publication.UpdatedAtUtc)
                    .First()
                    .Publication,
                StringComparer.OrdinalIgnoreCase);
        return workspaces
            .Select(workspace =>
            {
                if (creatorPublications.Count == 0)
                {
                    return workspace with
                    {
                        RecapShelf = workspace.RecapShelf
                            .Select(item => item with
                            {
                                CreatorPublicationId = AccountService.NormalizeOptional(item.CreatorPublicationId),
                                ArtifactId = AccountService.NormalizeOptional(item.ArtifactId)
                            })
                            .ToArray()
                    };
                }

                var recapShelf = workspace.RecapShelf
                    .Select(item =>
                    {
                        CreatorPublicationProjection? creatorPublication = ResolveCreatorPublicationForRecapItem(item, publicationsById, publicationsByArtifactId);
                        bool creatorLinked = creatorPublication is not null;

                        return item with
                        {
                            Audience = creatorLinked
                                ? DescribeRecapShelfAudience(item, creatorLinked)
                                : string.IsNullOrWhiteSpace(item.Audience)
                                    ? DescribeRecapShelfAudience(item, creatorLinked)
                                    : item.Audience,
                            OwnershipSummary = creatorLinked
                                ? DescribeRecapShelfOwnershipSummary(workspace, item)
                                : string.IsNullOrWhiteSpace(item.OwnershipSummary)
                                    ? DescribeRecapShelfOwnershipSummary(workspace, item)
                                    : item.OwnershipSummary,
                            PublicationState = creatorLinked
                                ? creatorPublication!.PublicationStatus
                                : string.IsNullOrWhiteSpace(item.PublicationState)
                                    ? DescribeRecapShelfPublicationState(item)
                                    : item.PublicationState,
                            TrustBand = creatorLinked ? creatorPublication!.TrustBand : item.TrustBand,
                            Discoverable = creatorLinked ? creatorPublication!.Discoverable : item.Discoverable,
                            PublicationSummary = creatorLinked
                                ? DescribeRecapShelfPublicationSummary(workspace, item, creatorPublication!, true)
                                : string.IsNullOrWhiteSpace(item.PublicationSummary)
                                    ? DescribeSharedPublicationSummary(workspace, item)
                                    : item.PublicationSummary,
                            ArtifactId = AccountService.NormalizeOptional(item.ArtifactId),
                            CreatorPublicationId = creatorLinked
                                ? creatorPublication!.PublicationId
                                : AccountService.NormalizeOptional(item.CreatorPublicationId),
                            NextSafeAction = creatorLinked
                                ? creatorPublication!.NextSafeAction ?? workspace.NextSafeAction
                                : string.IsNullOrWhiteSpace(item.NextSafeAction)
                                    ? DescribeRecapShelfNextSafeAction(workspace, item)
                                    : item.NextSafeAction,
                            ProvenanceSummary = DescribeRecapShelfProvenanceSummary(workspace, item, creatorPublication, creatorLinked),
                            AuditSummary = DescribeRecapShelfAuditSummary(workspace, item, creatorPublication, creatorLinked)
                        };
                    })
                    .ToArray();

                return workspace with { RecapShelf = recapShelf };
            })
            .ToArray();
    }

    private IReadOnlyList<CreatorPublicationProjection> AttachRegistryPublicationPosture(
        IReadOnlyList<CreatorPublicationProjection> creatorPublications)
    {
        if (_publicationDrafts is null)
        {
            return creatorPublications;
        }

        return creatorPublications
            .Select(publication =>
            {
                HubPublicationReceipt? receipt = _publicationDrafts.GetPublicationReceipt(publication.PublicationId);
                if (receipt is null)
                {
                    return publication;
                }

                string publicationStatus = MapRegistryPublicationStatus(receipt);
                var (trustBand, discoverable, trustSummary, discoverySummary, moderationSummary) =
                    BuildCreatorPublicationTrustPosture(publicationStatus, publication.Visibility);
                return publication with
                {
                    PublicationStatus = publicationStatus,
                    TrustBand = trustBand,
                    Discoverable = discoverable,
                    DiscoverySummary = discoverySummary,
                    NextSafeAction = ResolveRegistryNextSafeAction(receipt, publication.NextSafeAction),
                    TrustSummary = trustSummary,
                    ModerationSummary = moderationSummary
                };
            })
            .ToArray();
    }

    private static string MapRegistryPublicationStatus(HubPublicationReceipt receipt)
    {
        string publicationStatus = receipt.PublicationStatus.Trim().ToLowerInvariant();
        return publicationStatus switch
        {
            "review_pending" => "pending_review",
            "approved_for_publication" => "approved",
            "changes_requested" => "rejected",
            "draft" => "preview_ready",
            "archived" => "draft",
            _ => publicationStatus
        };
    }

    private static string? ResolveRegistryNextSafeAction(HubPublicationReceipt receipt, string? existing)
    {
        if (string.Equals(receipt.PublicationStatus, HubPublicationStates.Published, StringComparison.OrdinalIgnoreCase)
            || receipt.PublishedAtUtc is not null)
        {
            return "Keep the governed publication live on public discovery, lineage, and shelf surfaces while provenance and support posture stay current.";
        }

        return receipt.ReviewState switch
        {
            var state when string.Equals(state, HubReviewStates.PendingReview, StringComparison.OrdinalIgnoreCase)
                => "Hold this publication on governed publication, campaign, and moderation surfaces until the registry review resolves.",
            var state when string.Equals(state, HubReviewStates.Approved, StringComparison.OrdinalIgnoreCase)
                => "Approval is in. Publish or annotate this governed publication next so discovery and shelf posture stay honest.",
            var state when string.Equals(state, HubReviewStates.Rejected, StringComparison.OrdinalIgnoreCase)
                => "Revise this governed publication and resubmit it before you widen discovery or publication comparison.",
            _ => existing
        };
    }

    private static (string TrustBand, bool Discoverable, string TrustSummary, string DiscoverySummary, string ModerationSummary) BuildCreatorPublicationTrustPosture(string publicationStatus, string visibility)
    {
        var normalizedStatus = NormalizePublicationStatus(publicationStatus);
        var normalizedVisibility = DescribePublicationVisibility(visibility);
        var discoverable = string.Equals(normalizedStatus, "published", StringComparison.Ordinal)
            && !string.Equals(visibility, "private", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(visibility, "local_only", StringComparison.OrdinalIgnoreCase);

        var trustBand = normalizedStatus switch
        {
            "preview_ready" or "pending_review" => "review-pending",
            "approved" => "approval-backed",
            "rejected" => "needs-revision",
            "published" when discoverable => "curated-live",
            "published" => "restricted-live",
            "delisted" => "delisted-caution",
            "deprecated" => "replacement-advised",
            "superseded" => "retained-history",
            _ => "draft"
        };

        var trustSummary = normalizedStatus switch
        {
            "preview_ready" or "pending_review" => "Trust ranking is review-pending and stays anchored to governed provenance, rule fingerprint, and campaign continuity until approval clears.",
            "approved" => "Trust ranking is approval-backed and ready for governed publication without popularity-based promotion.",
            "rejected" => "Trust ranking is suspended until the creator revises the governed packet and resubmits it.",
            "published" when discoverable => "Trust ranking is live on governed discovery and stays anchored to provenance, lineage, and campaign continuity instead of popularity fog.",
            "published" => $"Trust ranking is live but discovery remains bounded to {normalizedVisibility} surfaces.",
            "delisted" => "Trust ranking is in delisted caution and should only surface with explicit moderation context.",
            "deprecated" => "Trust ranking stays retained only to steer discovery toward the governed successor.",
            "superseded" => "Trust ranking is retained for audit and install history, not active recommendation.",
            _ => "Trust ranking stays draft-scoped until governed review makes the packet comparable."
        };

        var discoverySummary = normalizedStatus switch
        {
            "preview_ready" or "pending_review" => "Keep this entry on publication, campaign, and moderation surfaces until approval completes.",
            "approved" => "Ready for governed publication, but keep it off public discovery until it is actually published.",
            "rejected" => "Hide from discovery until the creator revises and resubmits the packet.",
            "published" when discoverable => "Eligible for governed discovery, publication comparison, and shelf projection.",
            "published" => $"Keep discovery bounded to {normalizedVisibility} surfaces even though the publication is live.",
            "delisted" => "Keep it out of normal discovery and surface it only with moderation context.",
            "deprecated" => "Show successor-forward caution instead of ranking this as the preferred result.",
            "superseded" => "Retain for install and audit history, not as the preferred discovery result.",
            _ => "Draft publications stay off discovery surfaces."
        };

        var moderationSummary = normalizedStatus switch
        {
            "preview_ready" or "pending_review" => "Moderation is still waiting on approval review, so discovery stays bounded to publication, campaign, and operator surfaces.",
            "approved" => "Moderation cleared approval; publish or annotate next so discovery and shelf posture stay honest.",
            "rejected" => "Moderation requires revision before this publication can re-enter discovery or publication comparison.",
            "published" when discoverable => "Moderation watch is active but clear, so this publication can stay on discoverable public shelves until a later note changes its posture.",
            "published" => $"Moderation is clear, but visibility still keeps discovery limited to {normalizedVisibility} surfaces.",
            "delisted" => "Moderation removed this packet from normal discovery; only retained-history and explicit audit surfaces should surface it.",
            "deprecated" => "Moderation retains this packet with successor-forward caution until a replacement fully takes over.",
            "superseded" => "Moderation retains this packet as lineage-only history behind its successor.",
            _ => "Moderation has not started; keep this publication on governed internal surfaces until review begins."
        };

        return (trustBand, discoverable, trustSummary, discoverySummary, moderationSummary);
    }

    private static string NormalizePublicationStatus(string publicationStatus)
        => string.IsNullOrWhiteSpace(publicationStatus)
            ? string.Empty
            : publicationStatus.Trim().Replace('-', '_').ToLowerInvariant();

    private static string DescribePublicationVisibility(string visibility)
        => string.IsNullOrWhiteSpace(visibility)
            ? "shared"
            : visibility.Trim().Replace('_', ' ').Replace('-', ' ').ToLowerInvariant();

    private static string DescribeCreatorPublicationComparisonSummary(BuildLabHandoffProjection? leadHandoff)
        => !string.IsNullOrWhiteSpace(leadHandoff?.Title)
            ? $"Compare by provenance, visibility, trust ranking, lineage, {leadHandoff.Title} receipts, and campaign-return fit instead of popularity, install counts, or shelf age."
            : "Compare by provenance, visibility, trust ranking, lineage, and campaign-return fit instead of popularity, install counts, or shelf age.";

    private static string DescribeCreatorPublicationLineage(
        string artifactId,
        BuildLabHandoffProjection? leadHandoff,
        CampaignWorkspaceProjection workspace)
    {
        if (!string.IsNullOrWhiteSpace(leadHandoff?.HandoffId))
        {
            return $"{leadHandoff.Title} remains the current lineage anchor for artifact {artifactId} until a governed successor publication replaces it.";
        }

        return $"{workspace.CampaignName} keeps artifact {artifactId} as the current lineage anchor until a governed successor publication is promoted.";
    }

    private static bool SupportsCreatorShelfProjection(PublicationSafeProjection item)
    {
        var normalizedKind = item.Kind.Trim().ToLowerInvariant();
        return normalizedKind.Contains("recap", StringComparison.Ordinal)
            || normalizedKind.Contains("after", StringComparison.Ordinal)
            || normalizedKind.Contains("downtime", StringComparison.Ordinal)
            || normalizedKind.Contains("replay", StringComparison.Ordinal)
            || normalizedKind.Contains("dossier", StringComparison.Ordinal)
            || normalizedKind.Contains("runboard", StringComparison.Ordinal)
            || normalizedKind.Contains("campaign", StringComparison.Ordinal);
    }

    private static CreatorPublicationProjection? ResolveCreatorPublicationForRecapItem(
        PublicationSafeProjection item,
        IReadOnlyDictionary<string, CreatorPublicationProjection> publicationsById,
        IReadOnlyDictionary<string, CreatorPublicationProjection> publicationsByArtifactId)
    {
        string? publicationId = AccountService.NormalizeOptional(item.CreatorPublicationId);
        if (publicationId is not null
            && publicationsById.TryGetValue(publicationId, out CreatorPublicationProjection? creatorPublicationById))
        {
            return creatorPublicationById;
        }

        string? artifactId = AccountService.NormalizeOptional(item.ArtifactId);
        if (artifactId is not null
            && publicationsByArtifactId.TryGetValue(artifactId, out CreatorPublicationProjection? creatorPublicationByArtifact))
        {
            return creatorPublicationByArtifact;
        }

        return null;
    }

    private static string DescribeRecapShelfAudience(PublicationSafeProjection item, bool creatorLinked)
    {
        var normalizedKind = item.Kind.Trim().ToLowerInvariant();
        if (creatorLinked)
        {
            return normalizedKind.Contains("dossier", StringComparison.Ordinal)
                ? "personal,campaign,creator"
                : "campaign,creator";
        }

        if (normalizedKind.Contains("dossier", StringComparison.Ordinal)
            || normalizedKind.Contains("campaign_recap", StringComparison.Ordinal))
        {
            return "personal,campaign";
        }

        return "campaign";
    }

    private static string DescribeRecapShelfOwnershipSummary(
        CampaignWorkspaceProjection workspace,
        PublicationSafeProjection item)
    {
        var normalizedKind = item.Kind.Trim().ToLowerInvariant();
        if (normalizedKind.Contains("dossier", StringComparison.Ordinal))
        {
            return $"{workspace.CampaignName} reuses the same governed dossier artifact on the signed-in account path instead of forking a shadow copy.";
        }

        if (normalizedKind.Contains("runboard", StringComparison.Ordinal))
        {
            return $"{workspace.CampaignName} keeps this GM-facing packet on the shared campaign rail so organizer follow-through stays reviewable.";
        }

        if (normalizedKind.Contains("replay", StringComparison.Ordinal))
        {
            return $"{workspace.CampaignName} keeps this replay-safe artifact pinned to the shared continuity lane so contested turns can be reviewed without forking campaign truth.";
        }

        return $"{workspace.CampaignName} keeps this recap-safe artifact pinned to the shared continuity lane for return, audit, and reuse.";
    }

    private static string DescribeRecapShelfPublicationState(PublicationSafeProjection item)
    {
        var normalizedKind = item.Kind.Trim().ToLowerInvariant();
        if (normalizedKind.Contains("dossier", StringComparison.Ordinal))
        {
            return "personal_ready";
        }

        if (normalizedKind.Contains("runboard", StringComparison.Ordinal))
        {
            return "campaign_ready";
        }

        return "publication_safe";
    }

    private static string DescribeRecapShelfPublicationSummary(
        CampaignWorkspaceProjection workspace,
        PublicationSafeProjection item,
        CreatorPublicationProjection creatorPublication,
        bool creatorLinked)
    {
        if (creatorLinked)
        {
            var visibility = string.IsNullOrWhiteSpace(creatorPublication.Visibility)
                ? "shared"
                : creatorPublication.Visibility;
            var nextSafeAction = string.IsNullOrWhiteSpace(creatorPublication.NextSafeAction)
                ? "Open publication status before you widen the audience."
                : creatorPublication.NextSafeAction!;
            return $"{creatorPublication.Title} is already attached on the publication shelf with {visibility} visibility. {nextSafeAction}";
        }

        return DescribeSharedPublicationSummary(workspace, item);
    }

    private static string DescribeSharedPublicationSummary(
        CampaignWorkspaceProjection workspace,
        PublicationSafeProjection item)
    {
        var normalizedKind = item.Kind.Trim().ToLowerInvariant();
        if (normalizedKind.Contains("dossier", StringComparison.Ordinal))
        {
            return $"Personal and campaign views already share this {workspace.CampaignName} artifact without requiring a second export lane.";
        }

        if (normalizedKind.Contains("runboard", StringComparison.Ordinal))
        {
            return "Campaign return and GM prep reuse the same packet before shared publication opens.";
        }

        if (normalizedKind.Contains("replay", StringComparison.Ordinal))
        {
            return "Campaign return and contested-turn review reuse the same replay-safe packet before shared publication opens.";
        }

        return "Campaign return already trusts this recap-safe artifact, and shared publication can promote the same truth without rebuilding it.";
    }

    private static string DescribeRecapShelfProvenanceSummary(
        CampaignWorkspaceProjection workspace,
        PublicationSafeProjection item,
        CreatorPublicationProjection? creatorPublication,
        bool creatorLinked)
    {
        if (!string.IsNullOrWhiteSpace(item.ProvenanceSummary))
        {
            return item.ProvenanceSummary!;
        }

        if (creatorLinked && !string.IsNullOrWhiteSpace(creatorPublication?.ProvenanceSummary))
        {
            return creatorPublication.ProvenanceSummary;
        }

        return $"{workspace.RuleEnvironment.CompatibilityFingerprint} keeps {item.Label} attached to {workspace.CampaignName} without a shadow export lane.";
    }

    private static string DescribeRecapShelfAuditSummary(
        CampaignWorkspaceProjection workspace,
        PublicationSafeProjection item,
        CreatorPublicationProjection? creatorPublication,
        bool creatorLinked)
    {
        if (!string.IsNullOrWhiteSpace(item.AuditSummary))
        {
            return item.AuditSummary!;
        }

        DateTimeOffset updatedAtUtc = creatorLinked
            ? creatorPublication?.UpdatedAtUtc ?? DateTimeOffset.UtcNow
            : workspace.LatestContinuity?.CapturedAtUtc
                ?? workspace.AftermathPackages?.FirstOrDefault()?.GeneratedAtUtc
                ?? DateTimeOffset.UtcNow;
        string auditSource = creatorLinked
            ? "publication review and campaign return"
            : "campaign return";
        return $"Updated {updatedAtUtc:yyyy-MM-dd HH:mm} UTC on the governed {auditSource} lane for {workspace.CampaignName}.";
    }

    private static string DescribeRecapShelfNextSafeAction(
        CampaignWorkspaceProjection workspace,
        PublicationSafeProjection item)
    {
        var normalizedKind = item.Kind.Trim().ToLowerInvariant();
        if (normalizedKind.Contains("runboard", StringComparison.Ordinal))
        {
            return "Keep prep, aftermath, and next-session follow-through on the shared campaign rail before you branch into another export lane.";
        }

        if (normalizedKind.Contains("replay", StringComparison.Ordinal))
        {
            return "Keep contested-turn review on the shared campaign rail before you widen the replay artifact audience or publish another copy.";
        }

        if (normalizedKind.Contains("dossier", StringComparison.Ordinal))
        {
            return "Reopen the shared campaign view before you move this runner artifact into another campaign, shelf, or publication step.";
        }

        return workspace.NextSafeAction
            ?? "Open the shared campaign view before you widen the artifact audience or trust a second copy.";
    }

    private static string DescribeCreatorPublicationSupportClosure(CampaignWorkspaceProjection workspace)
    {
        if (workspace.ReadinessCues.Any(item => string.Equals(item.Severity, "warning", StringComparison.OrdinalIgnoreCase)))
        {
            return $"{workspace.RuleEnvironment.CompatibilityFingerprint} is grounded, but workspace readiness still needs review before this publication becomes the support-safe answer.";
        }

        return $"{workspace.RuleEnvironment.CompatibilityFingerprint} stays pinned across this publication, the shared return lane, and support follow-through.";
    }

    private static IReadOnlyList<string> BuildCreatorPublicationWatchouts(
        CampaignWorkspaceProjection workspace,
        BuildLabHandoffProjection? leadHandoff)
    {
        List<string> watchouts = [];

        if (leadHandoff is null)
        {
            watchouts.Add("No build handoff is attached yet, so shared publication still relies on workspace return truth alone.");
        }

        if (workspace.RecapShelf.Count == 0)
        {
            watchouts.Add("No recap-safe output is attached yet, so shared publication still depends on the live workspace summary.");
        }

        watchouts.AddRange(workspace.ReadinessCues
            .Where(item => string.Equals(item.Severity, "warning", StringComparison.OrdinalIgnoreCase))
            .Select(item => item.Summary));

        return watchouts
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static int CreatorPublicationProjectionPriority(string kind)
    {
        string normalizedKind = kind.Trim().ToLowerInvariant();
        if (normalizedKind.Contains("campaign", StringComparison.Ordinal)
            || normalizedKind.Contains("after", StringComparison.Ordinal)
            || normalizedKind.Contains("recap", StringComparison.Ordinal)
            || normalizedKind.Contains("downtime", StringComparison.Ordinal))
        {
            return 4;
        }

        if (normalizedKind.Contains("run_module", StringComparison.Ordinal)
            || normalizedKind.Contains("runboard", StringComparison.Ordinal)
            || normalizedKind.Contains("module", StringComparison.Ordinal))
        {
            return 3;
        }

        if (normalizedKind.Contains("primer", StringComparison.Ordinal)
            || normalizedKind.Contains("handbook", StringComparison.Ordinal)
            || normalizedKind.Contains("guide", StringComparison.Ordinal))
        {
            return 3;
        }

        if (normalizedKind.Contains("dossier", StringComparison.Ordinal))
        {
            return 2;
        }

        if (normalizedKind.Contains("replay", StringComparison.Ordinal))
        {
            return 1;
        }

        return 0;
    }

    private static string NormalizeCreatorPublicationKind(string kind)
    {
        string normalizedKind = kind.Trim().ToLowerInvariant();
        if (normalizedKind.Contains("runboard", StringComparison.Ordinal)
            || normalizedKind.Contains("module", StringComparison.Ordinal))
        {
            return "run_module";
        }

        if (normalizedKind.Contains("dossier", StringComparison.Ordinal))
        {
            return "dossier";
        }

        if (normalizedKind.Contains("primer", StringComparison.Ordinal)
            || normalizedKind.Contains("handbook", StringComparison.Ordinal)
            || normalizedKind.Contains("guide", StringComparison.Ordinal))
        {
            return "primer";
        }

        if (normalizedKind.Contains("campaign", StringComparison.Ordinal))
        {
            return "campaign";
        }

        return normalizedKind;
    }

    private static string BuildCreatorPublicationTitle(
        CampaignWorkspaceProjection workspace,
        RunnerDossierProjection? dossier,
        PublicationSafeProjection item,
        string publicationKind)
    {
        string normalizedKind = publicationKind.Trim().ToLowerInvariant();
        return normalizedKind switch
        {
            "dossier" => $"{dossier?.DisplayName ?? workspace.CampaignName} dossier packet",
            "primer" => $"{workspace.CampaignName} campaign primer",
            "run_module" => $"{workspace.CampaignName} run module packet",
            "campaign" => $"{workspace.CampaignName} campaign packet",
            _ when normalizedKind.Contains("replay", StringComparison.Ordinal) => $"{workspace.CampaignName} replay timeline",
            _ when normalizedKind.Contains("after", StringComparison.Ordinal) => $"{workspace.CampaignName} after-action report",
            _ when normalizedKind.Contains("downtime", StringComparison.Ordinal) => $"{workspace.CampaignName} downtime brief",
            _ when normalizedKind.Contains("recap", StringComparison.Ordinal) => $"{workspace.CampaignName} session recap",
            _ => string.IsNullOrWhiteSpace(item.Label)
                ? $"{workspace.CampaignName} publication packet"
                : $"{workspace.CampaignName} {item.Label}"
        };
    }

    private static string BuildCreatorPublicationSummary(
        CampaignWorkspaceProjection workspace,
        PublicationSafeProjection item,
        string publicationKind)
    {
        if (!string.IsNullOrWhiteSpace(item.Summary))
        {
            return item.Summary;
        }

        string normalizedKind = publicationKind.Trim().ToLowerInvariant();
        return normalizedKind switch
        {
            "dossier" => "Living dossier truth, campaign continuity, and governed publication detail stay attached to one shared artifact lane.",
            "primer" => "Primer-safe onboarding, campaign continuity, and governed publication detail stay attached to one shared artifact lane.",
            "run_module" => "Run-module prep, GM continuity, and governed publication detail stay attached to one shared artifact lane.",
            "campaign" => "Campaign recap, return cues, and governed publication detail stay attached to one shared artifact lane.",
            _ when normalizedKind.Contains("replay", StringComparison.Ordinal) => "Replay-safe turn review and governed publication detail stay attached to one shared artifact lane.",
            _ => $"{workspace.CampaignName} keeps this publication on one shared artifact lane."
        };
    }

    private static string ResolveDeviceRole(ClaimedInstallationDto installation)
    {
        if (string.Equals(installation.Platform, "android", StringComparison.OrdinalIgnoreCase)
            || string.Equals(installation.Platform, "ios", StringComparison.OrdinalIgnoreCase))
        {
            return "play_tablet";
        }

        if ((installation.HeadId?.Contains("observer", StringComparison.OrdinalIgnoreCase) ?? false)
            || (installation.HostLabel?.Contains("observer", StringComparison.OrdinalIgnoreCase) ?? false))
        {
            return "observer_screen";
        }

        if (string.Equals(installation.Channel, "preview", StringComparison.OrdinalIgnoreCase))
        {
            return "preview_scout";
        }

        if (string.Equals(installation.HeadId, "offline", StringComparison.OrdinalIgnoreCase))
        {
            return "travel_cache";
        }

        return "workstation";
    }

    private static string StableId(string prefix, string seed)
    {
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(seed));
        return $"{prefix}-{Convert.ToHexString(hash)[..12].ToLowerInvariant()}";
    }

    private static bool ContentEquals<T>(T? left, T? right)
        => string.Equals(
            JsonSerializer.Serialize(left, ComparisonJsonOptions),
            JsonSerializer.Serialize(right, ComparisonJsonOptions),
            StringComparison.Ordinal);
}
