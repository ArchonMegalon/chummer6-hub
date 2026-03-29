using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Campaign.Contracts;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public sealed class CampaignSpineService
{
    private static readonly JsonSerializerOptions ComparisonJsonOptions = new(JsonSerializerDefaults.Web);
    private static readonly IReadOnlyList<string> DefaultPersonalPreviewCapabilities =
    [
        "campaign_workspace",
        "build_lab",
        "rules_navigator",
        "creator_publication",
        "support_closure"
    ];

    private readonly CommunityStore _store;
    private readonly WorkspaceLifecyclePolicyService _lifecyclePolicy;

    public CampaignSpineService(CommunityStore store, WorkspaceLifecyclePolicyService lifecyclePolicy)
    {
        _store = store;
        _lifecyclePolicy = lifecyclePolicy;
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
                .OrderBy(group => group.Name, StringComparer.OrdinalIgnoreCase)
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
                        CampaignReturnSummary: ResolveGroupCampaignReturnSummary(group, groupWorkspaces),
                        SeasonEventSummary: ResolveGroupSeasonEventSummary(group, groupCampaigns, groupWorkspaces),
                        RecentReturnSummaries: groupWorkspaces
                            .Select(static workspace => $"{workspace.CampaignName}: {workspace.ReturnSummary}")
                            .Take(3)
                            .ToArray(),
                        RecentEventSummaries: BuildGroupRecentEventSummaries(groupWorkspaces),
                        SeasonBoardEntries: BuildGroupSeasonBoardEntries(groupWorkspaces),
                        Watchouts: BuildGroupOperatorWatchouts(groupWorkspaces),
                        RecentRosterTransfers: transfers
                            .Where(item =>
                                string.Equals(item.SourceGroupId, group.GroupId, StringComparison.OrdinalIgnoreCase)
                                || string.Equals(item.TargetGroupId, group.GroupId, StringComparison.OrdinalIgnoreCase))
                            .Take(5)
                            .ToArray());
                })
                .ToArray();
            var buildLabHandoffs = BuildBuildLabHandoffs(dossiers, workspaces, restore);
            var rulesNavigator = BuildRulesNavigatorEntries(workspaces, operations);
            var migrationReceipts = BuildMigrationReceipts(dossiers, campaigns);
            var creatorPublications = BuildCreatorPublications(workspaces, dossiers, buildLabHandoffs);

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
                _store.PrepLaunches.RemoveRange(64, _store.PrepLaunches.Count - 64);
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
                _store.TravelPrefetchReceipts.RemoveRange(64, _store.TravelPrefetchReceipts.Count - 64);
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
            var package = new AftermathRecapPackageProjection(
                PackageId: StableId("aftermath", $"{workspace.WorkspaceId}:{run?.RunId ?? "campaign"}:{normalizedPackageKind}:{now.ToUnixTimeMilliseconds()}"),
                WorkspaceId: workspace.WorkspaceId,
                CampaignId: workspace.CampaignId,
                RunId: run?.RunId,
                RunTitle: run?.Title,
                PackageKind: normalizedPackageKind,
                Title: normalizedTitle,
                Summary: normalizedSummary,
                ArtifactId: StableId("artifact", $"{workspace.WorkspaceId}:{normalizedPackageKind}:{now.ToUnixTimeMilliseconds()}"),
                EvidenceLines: FinalizeLines(evidenceLines),
                InitiatedByUserId: user.UserId,
                GeneratedAtUtc: now);

            _store.AftermathPackages.Add(package);
            if (_store.AftermathPackages.Count > 64)
            {
                _store.AftermathPackages.RemoveRange(64, _store.AftermathPackages.Count - 64);
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
            var dossier = _store.DossiersById.GetValueOrDefault(request.DossierId)
                ?? throw new KeyNotFoundException($"Unknown dossier: {request.DossierId}");
            var sourceCampaign = _store.CampaignSpinesById.GetValueOrDefault(dossier.CampaignId ?? string.Empty)
                ?? throw new KeyNotFoundException($"Unknown source campaign: {dossier.CampaignId}");
            var sourceGroup = _store.GroupsById.GetValueOrDefault(sourceCampaign.GroupId)
                ?? throw new KeyNotFoundException($"Unknown source group: {sourceCampaign.GroupId}");
            if (!CanManageRosterGroup(sourceGroup, requester.UserId))
            {
                throw new CommunityAccessDeniedException("requester must be an owner, manager, admin, or gm on the source group to move roster state.");
            }

            var targetGroup = _store.GroupsById.GetValueOrDefault(request.TargetGroupId)
                ?? throw new KeyNotFoundException($"Unknown target group: {request.TargetGroupId}");
            if (!CanManageRosterGroup(targetGroup, requester.UserId))
            {
                throw new CommunityAccessDeniedException("requester must be an owner, manager, admin, or gm on the target group to move roster state.");
            }

            string previousOwnerUserId = dossier.OwnerUserId;
            var previousOwner = _store.UsersById.GetValueOrDefault(previousOwnerUserId);
            string currentOwnerUserId = string.IsNullOrWhiteSpace(request.TargetOwnerUserId)
                ? dossier.OwnerUserId
                : request.TargetOwnerUserId.Trim();
            var currentOwner = _store.UsersById.GetValueOrDefault(currentOwnerUserId)
                ?? throw new KeyNotFoundException($"Unknown target owner: {currentOwnerUserId}");
            var targetCampaign = ResolveOrCreateTransferCampaignLocked(targetGroup, request.TargetCampaignId, request.TargetCampaignTitle, now);
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
                        ProjectionId: StableId("projection", $"{currentOwnerUserId}:{targetCampaign.CampaignId}:ops"),
                        Kind: "runboard_packet",
                        Label: "Runboard continuity packet",
                        Summary: "GM-facing continuity and recap-safe state for the active campaign return.",
                        ArtifactId: StableId("ops", targetCampaign.CampaignId))
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
            UpdatedAtUtc: updatedAtUtc);
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
        else if (existingGroup.Memberships.All(member => !string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)))
        {
            _store.GroupsById[groupId] = existingGroup with
            {
                Memberships = existingGroup.Memberships.Concat([membership]).ToArray(),
                UpdatedAtUtc = now
            };
            changed = true;
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
            existing = new RunnerDossierProjection(
                DossierId: AccountService.NewId("dos"),
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
                        ProjectionId: StableId("projection", $"{user.UserId}:{campaignId}:ops"),
                        Kind: "runboard_packet",
                        Label: "Runboard continuity packet",
                        Summary: "GM-facing continuity and recap-safe state for the active campaign return.",
                        ArtifactId: StableId("ops", campaignId))
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
                        ProjectionId: StableId("projection", $"{user.UserId}:{campaignId}:ops"),
                        Kind: "runboard_packet",
                        Label: "Runboard continuity packet",
                        Summary: "GM-facing continuity and recap-safe state for the active campaign return.",
                        ArtifactId: StableId("ops", campaignId))
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
            segments.Add($"rules {string.Join(", ", ruleEnvironments.Take(3).Select(static environment => $"{environment.CompatibilityFingerprint} [{environment.ApprovalState}]"))}");
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

        if (!string.Equals(campaign.RuleEnvironment.ApprovalState, "approved", StringComparison.OrdinalIgnoreCase))
        {
            readinessCues.Add(new CampaignReadinessCue(
                CueId: StableId("cue", $"{campaign.CampaignId}:ruleenv"),
                Severity: "review",
                Title: "Rule environment needs explicit review",
                Summary: $"{campaign.RuleEnvironment.OwnerScope} scope is {campaign.RuleEnvironment.ApprovalState} on {campaign.RuleEnvironment.CompatibilityFingerprint}."));
        }
        else
        {
            readinessCues.Add(new CampaignReadinessCue(
                CueId: StableId("cue", $"{campaign.CampaignId}:ruleenv"),
                Severity: "ready",
                Title: "Rule environment is approved",
                Summary: $"{campaign.RuleEnvironment.OwnerScope} scope is pinned to {campaign.RuleEnvironment.CompatibilityFingerprint}."));
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
                Title: "Aftermath recap package is attached",
                Summary: $"{workspaceAftermathPackages.Length} governed recap package(s) keep run aftermath and next-session return reviewable instead of falling back to prose alone."));
        }

        var recapShelf = workspaceAftermathPackages
            .Select(BuildAftermathRecapShelfProjection)
            .Concat(workspaceDossiers
            .SelectMany(static item => item.Projections)
            .Where(item => item.Kind.Contains("recap", StringComparison.OrdinalIgnoreCase)
                || item.Kind.Contains("runboard", StringComparison.OrdinalIgnoreCase)
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
        var nextSessionCarryForward = BuildNextSessionCarryForward(campaign, nextSafeAction, leadRun, activeScene, leadObjective, consequences, workspacePrepLaunches, workspaceTravelPrefetches, workspaceAftermathPackages);
        var changePackets = BuildWorkspaceChangePackets(campaign, recapShelf, leadRun, activeScene, leadObjective, rosterTransfers, workspacePrepLaunches, workspaceTravelPrefetches, workspaceAftermathPackages, nextSessionCarryForward);

        return new CampaignWorkspaceProjection(
            WorkspaceId: workspaceId,
            CampaignId: campaign.CampaignId,
            CampaignName: campaign.Name,
            Visibility: campaign.Visibility,
            RuleEnvironment: campaign.RuleEnvironment,
            Crews: workspaceCrews,
            Dossiers: workspaceDossiers,
            Runs: workspaceRuns,
            RecapShelf: recapShelf,
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
            NextSessionCarryForward: nextSessionCarryForward);
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
        string recapSummary = recapPackageCount == 0
            ? "recap packaging is still pending"
            : $"{recapPackageCount} recap package(s) are already reviewable";
        return $"{groupWorkspaces.Count} campaign return(s) keep the governed {railLabel} on the same account/control backbone; {liveRunSummary}, {carryForwardSummary}, and {recapSummary}.";
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
                var watchout = workspace.ReadinessCues
                    .Where(static cue => NeedsAttention(cue.Severity))
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
                .Select(cue => $"{workspace.CampaignName}: {cue.Title} — {cue.Summary}"))
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
                    Watchouts: watchouts);
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

        CampaignReadinessCue? attentionCue = readinessCues.FirstOrDefault(static cue =>
            !string.Equals(cue.Severity, "ready", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(cue.Severity, "healthy", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(cue.Severity, "ok", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(cue.Severity, "info", StringComparison.OrdinalIgnoreCase));
        if (attentionCue is not null)
        {
            return $"Review {attentionCue.Title} before you continue {campaign.Name}: {attentionCue.Summary}";
        }

        if (activeScene is not null && leadObjective is not null)
        {
            return $"Resume {activeScene.Title} in {leadRun!.Title} and clear {leadObjective.Title} before you advance the next recap-safe handoff.";
        }

        if (activeScene is not null)
        {
            return $"Resume {activeScene.Title} in {leadRun!.Title} and confirm the next scene-safe recap before you switch devices.";
        }

        if (recapShelf.Count == 0)
        {
            return $"Open {campaign.Name} and publish the first recap-safe output before you trust this workspace as the return lane.";
        }

        return $"Open {campaign.Name} from the latest continuity snapshot and keep the shared return lane attached to the current claimed install.";
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
        CampaignConsequenceProjection? leadConsequence = consequences.FirstOrDefault();
        GovernedPrepLaunchProjection? leadPrepLaunch = prepLaunches.FirstOrDefault();
        TravelPrefetchReceiptProjection? leadTravelPrefetch = travelPrefetchReceipts.FirstOrDefault();
        AftermathRecapPackageProjection? leadAftermathPackage = aftermathPackages.FirstOrDefault();

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
            summary = $"{activeScene.Title} and {leadObjective.Title} stay pinned as the governed next-session return for {leadRun!.Title}.";
        }
        else if (leadAftermathPackage is not null)
        {
            summary = $"{leadAftermathPackage.Title} is pinned as the recap-safe carry-forward packet for {campaign.Name}.";
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
                activeScene is null ? string.Empty : $"{activeScene.Title} is live on {leadRun!.Title} at {activeScene.Revision}.",
                leadObjective is null ? string.Empty : $"{leadObjective.Title} stays {leadObjective.Status} with {leadObjective.Pressure} pressure.",
                leadAftermathPackage is null ? string.Empty : $"{leadAftermathPackage.Title}: {leadAftermathPackage.Summary}",
                leadConsequence?.EvidenceLines.FirstOrDefault() ?? leadConsequence?.Summary ?? string.Empty,
                prepBindingSummary,
                travelSummary,
                nextSafeAction
            ]),
            UpdatedAtUtc: updatedAtUtc);
    }

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
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: nextSessionCarryForward.CarryForwardId,
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
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:scene:{activeScene.SceneId}"),
                Kind: "scene",
                Label: "Active scene",
                Summary: $"{activeScene.Title} is live on {leadRun.Title} at {activeScene.Revision}.",
                UpdatedAtUtc: activeScene.UpdatedAtUtc));
        }

        if (leadObjective is not null)
        {
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:objective:{leadObjective.ObjectiveId}"),
                Kind: "objective",
                Label: "Objective pressure",
                Summary: $"{leadObjective.Title} remains {leadObjective.Status} with {leadObjective.Pressure} pressure.",
                UpdatedAtUtc: leadObjective.UpdatedAtUtc));
        }

        RosterTransferProjection? rosterTransfer = rosterTransfers.FirstOrDefault();
        if (rosterTransfer is not null)
        {
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:transfer:{rosterTransfer.TransferId}"),
                Kind: "roster_transfer",
                Label: "Roster transfer",
                Summary: rosterTransfer.Summary,
                UpdatedAtUtc: rosterTransfer.TransferredAtUtc));
        }

        GovernedPrepLaunchProjection? prepLaunch = prepLaunches.FirstOrDefault();
        if (prepLaunch is not null)
        {
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:prep-launch:{prepLaunch.LaunchId}"),
                Kind: "prep_launch",
                Label: "GM prep launch",
                Summary: prepLaunch.Summary,
                UpdatedAtUtc: prepLaunch.LaunchedAtUtc));
        }

        TravelPrefetchReceiptProjection? travelPrefetch = travelPrefetchReceipts.FirstOrDefault();
        if (travelPrefetch is not null)
        {
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:travel-prefetch:{travelPrefetch.ReceiptId}"),
                Kind: "travel_prefetch",
                Label: "Travel prefetch staged",
                Summary: travelPrefetch.PrefetchSummary,
                UpdatedAtUtc: travelPrefetch.StagedAtUtc));
        }

        AftermathRecapPackageProjection? aftermathPackage = aftermathPackages.FirstOrDefault();
        if (aftermathPackage is not null)
        {
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:aftermath:{aftermathPackage.PackageId}"),
                Kind: "aftermath_recap",
                Label: DescribeAftermathChangeLabel(aftermathPackage.PackageKind),
                Summary: aftermathPackage.Summary,
                UpdatedAtUtc: aftermathPackage.GeneratedAtUtc));
        }

        PublicationSafeProjection? recap = recapShelf.FirstOrDefault();
        if (recap is not null && aftermathPackage is null)
        {
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:recap:{recap.ProjectionId}"),
                Kind: "artifact",
                Label: recap.Label,
                Summary: recap.Summary,
                UpdatedAtUtc: campaign.UpdatedAtUtc));
        }

        return packets
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .Take(4)
            .ToArray();
    }

    private static PublicationSafeProjection BuildAftermathRecapShelfProjection(AftermathRecapPackageProjection package)
        => new(
            ProjectionId: package.PackageId,
            Kind: package.PackageKind,
            Label: package.Title,
            Summary: package.Summary,
            ArtifactId: package.ArtifactId);

    private static string DescribeAftermathChangeLabel(string packageKind)
        => packageKind.Trim().ToLowerInvariant() switch
        {
            "downtime_brief" => "Downtime brief",
            "after_action_report" => "After-action report",
            _ => "Aftermath recap package"
        };

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
            entries.Add(new RulesNavigatorAnswerProjection(
                EntryId: StableId("rules", workspace.WorkspaceId),
                Question: "Why is this campaign return pinned to the current rule environment?",
                ShortAnswer: "Because campaign continuity and support closure both follow the same approved compatibility fingerprint.",
                BeforeSummary: "Before approval, restore posture is review-heavy and support has to caveat the answer path.",
                AfterSummary: $"After approval, {workspace.RuleEnvironment.CompatibilityFingerprint} becomes the grounded answer path for build, play, and support.",
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
                ]));
        }

        if (operation is not null)
        {
            entries.Add(new RulesNavigatorAnswerProjection(
                EntryId: StableId("rules", operation.GroupId),
                Question: "How does group visibility change the campaign operator posture?",
                ShortAnswer: "Operator permissions stay subordinate to campaign visibility and the approved rule environment.",
                BeforeSummary: "Before visibility is explicit, group operations tend to rely on memory and side channels.",
                AfterSummary: $"After visibility is explicit, {operation.CampaignVisibilitySummary} becomes part of the grounded decision surface.",
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
                ]));
        }

        return entries;
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
            .Select(workspace =>
            {
                var dossier = dossiers.FirstOrDefault(item => string.Equals(item.CampaignId, workspace.CampaignId, StringComparison.OrdinalIgnoreCase));
                var artifact = workspace.RecapShelf.FirstOrDefault()?.ArtifactId ?? StableId("artifact", workspace.WorkspaceId);
                var leadHandoff = buildLabHandoffs
                    .Where(item => string.Equals(item.CampaignId, workspace.CampaignId, StringComparison.OrdinalIgnoreCase))
                    .OrderByDescending(static item => item.UpdatedAtUtc)
                    .FirstOrDefault();
                var nextSafeAction = !string.IsNullOrWhiteSpace(leadHandoff?.NextSafeAction)
                    ? leadHandoff.NextSafeAction
                    : workspace.NextSafeAction
                        ?? "Review the grounded creator packet, then return through the shared campaign view before you publish or export it further.";
                var campaignReturnSummary = !string.IsNullOrWhiteSpace(leadHandoff?.CampaignReturnSummary)
                    ? leadHandoff.CampaignReturnSummary
                    : workspace.ReturnSummary;
                var supportClosureSummary = !string.IsNullOrWhiteSpace(leadHandoff?.SupportClosureSummary)
                    ? leadHandoff.SupportClosureSummary
                    : DescribeCreatorPublicationSupportClosure(workspace);
                var watchouts = BuildCreatorPublicationWatchouts(workspace, leadHandoff);
                return new CreatorPublicationProjection(
                    PublicationId: StableId("publication", workspace.WorkspaceId),
                    Title: $"{workspace.CampaignName} creator packet",
                    Kind: "campaign_packet",
                    Summary: "Campaign recap, dossier-safe briefings, and creator-ready outputs now share one governed publication posture.",
                    CampaignId: workspace.CampaignId,
                    DossierId: dossier?.DossierId,
                    ArtifactId: artifact,
                    ProvenanceSummary: $"{workspace.RuleEnvironment.CompatibilityFingerprint} + recap-safe output shelf",
                    DiscoverySummary: $"{workspace.Visibility} visibility with grounded provenance and one truthful next action.",
                    Visibility: workspace.Visibility,
                    PublicationStatus: "preview_ready",
                    UpdatedAtUtc: workspace.LatestContinuity?.CapturedAtUtc ?? DateTimeOffset.UtcNow,
                    NextSafeAction: nextSafeAction,
                    CampaignReturnSummary: campaignReturnSummary,
                    SupportClosureSummary: supportClosureSummary,
                    BuildHandoffId: leadHandoff?.HandoffId,
                    Watchouts: watchouts);
            })
            .Take(3)
            .ToArray();
    }

    private static string DescribeCreatorPublicationSupportClosure(CampaignWorkspaceProjection workspace)
    {
        if (workspace.ReadinessCues.Any(item => string.Equals(item.Severity, "warning", StringComparison.OrdinalIgnoreCase)))
        {
            return $"{workspace.RuleEnvironment.CompatibilityFingerprint} is grounded, but workspace readiness still needs review before this creator packet becomes the support-safe answer.";
        }

        return $"{workspace.RuleEnvironment.CompatibilityFingerprint} stays pinned across the creator packet, shared return lane, and support follow-through.";
    }

    private static IReadOnlyList<string> BuildCreatorPublicationWatchouts(
        CampaignWorkspaceProjection workspace,
        BuildLabHandoffProjection? leadHandoff)
    {
        List<string> watchouts = [];

        if (leadHandoff is null)
        {
            watchouts.Add("No build handoff is attached yet, so creator publication still relies on workspace return truth alone.");
        }

        if (workspace.RecapShelf.Count == 0)
        {
            watchouts.Add("No recap-safe output is attached yet, so creator publication still depends on the live workspace summary.");
        }

        watchouts.AddRange(workspace.ReadinessCues
            .Where(item => string.Equals(item.Severity, "warning", StringComparison.OrdinalIgnoreCase))
            .Select(item => item.Summary));

        return watchouts
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
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
