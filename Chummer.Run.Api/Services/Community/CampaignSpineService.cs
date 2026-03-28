using System.Security.Cryptography;
using System.Text;
using Chummer.Campaign.Contracts;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Community;

public sealed class CampaignSpineService
{
    private static readonly IReadOnlyList<string> DefaultPersonalPreviewCapabilities =
    [
        "campaign_workspace",
        "build_lab",
        "rules_navigator",
        "creator_publication",
        "support_closure"
    ];

    private readonly CommunityStore _store;

    public CampaignSpineService(CommunityStore store)
    {
        _store = store;
    }

    public AccountCampaignSummary GetAccountSummary(HubUserDto user, InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);

        lock (_store.Gate)
        {
            var changed = EnsureSeedDataLocked(user, installLinking);
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
                : BuildRestoreProjection(user, dossiers, campaigns, installLinking);
            var workspaces = campaigns
                .Select(campaign => BuildWorkspaceProjection(campaign, dossiers, runs, crews, restore))
                .OrderByDescending(static workspace => workspace.LatestContinuity?.CapturedAtUtc ?? DateTimeOffset.MinValue)
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
                        ActiveSponsorSessionCount: _store.SponsorSessionsById.Values.Count(item => string.Equals(item.GroupId, group.GroupId, StringComparison.OrdinalIgnoreCase) && !string.Equals(item.Status, "stopped", StringComparison.OrdinalIgnoreCase)));
                })
                .ToArray();
            var buildLabHandoffs = BuildBuildLabHandoffs(dossiers, workspaces, restore);
            var rulesNavigator = BuildRulesNavigatorEntries(workspaces, operations);
            var migrationReceipts = BuildMigrationReceipts(dossiers, campaigns);
            var creatorPublications = BuildCreatorPublications(workspaces, dossiers);

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

    private bool EnsureSeedDataLocked(HubUserDto user, InstallLinkingSummaryDto? installLinking)
    {
        var changed = false;
        changed |= EnsurePersonalDossierLocked(user);
        changed |= EnsureCampaignsLocked(user);

        var dossiers = _store.DossiersById.Values
            .Where(item => string.Equals(item.OwnerUserId, user.UserId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
        var campaigns = _store.CampaignSpinesById.Values
            .Where(item => item.DossierIds.Any(dossierId => dossiers.Any(dossier => string.Equals(dossier.DossierId, dossierId, StringComparison.OrdinalIgnoreCase))))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
        var restore = BuildRestoreProjection(user, dossiers, campaigns, installLinking);
        if (!_store.RestoreByUserId.TryGetValue(user.UserId, out var existingRestore) || !Equals(existingRestore, restore))
        {
            _store.RestoreByUserId[user.UserId] = restore;
            changed = true;
        }

        return changed;
    }

    private bool EnsurePersonalDossierLocked(HubUserDto user)
    {
        if (_store.DossiersById.Values.Any(item => string.Equals(item.OwnerUserId, user.UserId, StringComparison.OrdinalIgnoreCase)))
        {
            return false;
        }

        var now = DateTimeOffset.UtcNow;
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

    private bool EnsureCampaignsLocked(HubUserDto user)
    {
        var changed = false;
        var memberGroups = _store.GroupsById.Values
            .Where(group => group.Memberships.Any(member => string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)))
            .ToArray();
        var sponsorCampaigns = _store.CampaignsById.Values
            .Where(item => memberGroups.Any(group => string.Equals(group.GroupId, item.GroupId, StringComparison.OrdinalIgnoreCase)))
            .ToArray();

        if (sponsorCampaigns.Length == 0)
        {
            changed |= EnsurePersonalPreviewCampaignLocked(user);
            memberGroups = _store.GroupsById.Values
                .Where(group => group.Memberships.Any(member => string.Equals(member.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)))
                .ToArray();
            sponsorCampaigns = _store.CampaignsById.Values
                .Where(item => memberGroups.Any(group => string.Equals(group.GroupId, item.GroupId, StringComparison.OrdinalIgnoreCase)))
                .ToArray();
        }

        foreach (var sponsorCampaign in sponsorCampaigns)
        {
            if (!_store.GroupsById.TryGetValue(sponsorCampaign.GroupId, out var group))
            {
                continue;
            }

            var crewId = StableId("crew", sponsorCampaign.GroupId);
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
            var memberAssignments = group.Memberships
                .Select(member =>
                {
                    var userRecord = _store.UsersById.GetValueOrDefault(member.UserId);
                    if (userRecord is null)
                    {
                        return null;
                    }

                    var dossier = EnsureMemberDossierLocked(userRecord, sponsorCampaign.CampaignId, crewId, runId, sceneId, sponsorCampaign.Title);
                    return new CrewAssignmentProjection(
                        UserId: member.UserId,
                        DossierId: dossier.DossierId,
                        Role: member.Role,
                        Availability: "active",
                        AddedAtUtc: member.JoinedAtUtc);
                })
                .Where(static assignment => assignment is not null)
                .Cast<CrewAssignmentProjection>()
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
                UpdatedAtUtc: DateTimeOffset.UtcNow);
            if (!_store.CrewsById.TryGetValue(crewId, out var existingCrew) || !Equals(existingCrew, crew))
            {
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
                        UpdatedAtUtc: DateTimeOffset.UtcNow)
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
                        UpdatedAtUtc: DateTimeOffset.UtcNow)
                ],
                LatestContinuity: continuity,
                CreatedAtUtc: sponsorCampaign.CreatedAtUtc,
                UpdatedAtUtc: DateTimeOffset.UtcNow);
            if (!_store.RunsById.TryGetValue(runId, out var existingRun) || !Equals(existingRun, run))
            {
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
                UpdatedAtUtc: DateTimeOffset.UtcNow);
            if (!_store.CampaignSpinesById.TryGetValue(campaign.CampaignId, out var existingCampaign) || !Equals(existingCampaign, campaign))
            {
                _store.CampaignSpinesById[campaign.CampaignId] = campaign;
                changed = true;
            }
        }

        return changed;
    }

    private bool EnsurePersonalPreviewCampaignLocked(HubUserDto user)
    {
        var changed = false;
        var now = DateTimeOffset.UtcNow;
        var groupId = StableId("group", $"personal-preview:{user.UserId}");
        var campaignId = StableId("campaign", $"personal-preview:{user.UserId}");
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

        return changed;
    }

    private RunnerDossierProjection EnsureMemberDossierLocked(
        HubUserDto user,
        string campaignId,
        string crewId,
        string runId,
        string sceneId,
        string campaignTitle)
    {
        var existing = _store.DossiersById.Values.FirstOrDefault(item => string.Equals(item.OwnerUserId, user.UserId, StringComparison.OrdinalIgnoreCase));
        var continuity = new ContinuitySnapshotRef(
            SnapshotId: StableId("snapshot", $"{user.UserId}:{campaignId}"),
            CapturedAtUtc: DateTimeOffset.UtcNow,
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
                CreatedAtUtc: DateTimeOffset.UtcNow,
                UpdatedAtUtc: DateTimeOffset.UtcNow);
        }
        else
        {
            existing = existing with
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
                UpdatedAtUtc = DateTimeOffset.UtcNow
            };
        }

        _store.DossiersById[existing.DossierId] = existing;
        return existing;
    }

    private static WorkspaceRestoreProjection BuildRestoreProjection(
        HubUserDto user,
        IReadOnlyList<RunnerDossierProjection> dossiers,
        IReadOnlyList<CampaignProjection> campaigns,
        InstallLinkingSummaryDto? installLinking)
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
            .Select(static installation => new ClaimedDeviceRestoreProjection(
                InstallationId: installation.InstallationId,
                DeviceRole: ResolveDeviceRole(installation),
                Platform: installation.Platform ?? "unknown",
                HeadId: installation.HeadId ?? "desktop",
                Channel: installation.Channel,
                HostLabel: installation.HostLabel,
                RestoreSummary: $"{installation.Platform ?? "unknown"} · {installation.HeadId ?? "desktop"} · {installation.Version}"))
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
            GeneratedAtUtc: DateTimeOffset.UtcNow);
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
        WorkspaceRestoreProjection restore)
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

        var recapShelf = workspaceDossiers
            .SelectMany(static item => item.Projections)
            .Where(item => item.Kind.Contains("recap", StringComparison.OrdinalIgnoreCase)
                || item.Kind.Contains("runboard", StringComparison.OrdinalIgnoreCase)
                || item.Kind.Contains("dossier", StringComparison.OrdinalIgnoreCase))
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
        var changePackets = BuildWorkspaceChangePackets(campaign, recapShelf, leadRun, activeScene, leadObjective);

        return new CampaignWorkspaceProjection(
            WorkspaceId: StableId("workspace", campaign.CampaignId),
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
            ChangePackets: changePackets);
    }

    private static bool IsOperatorRole(string role)
        => string.Equals(role, "owner", StringComparison.OrdinalIgnoreCase)
            || string.Equals(role, "admin", StringComparison.OrdinalIgnoreCase)
            || string.Equals(role, "manager", StringComparison.OrdinalIgnoreCase)
            || string.Equals(role, "gm", StringComparison.OrdinalIgnoreCase);

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
                        "Role overlap stays explicit before the handoff leaves build comparison.",
                        workspace is null
                            ? "No campaign workspace is attached yet, so the handoff seeds the dossier first."
                            : $"Campaign workspace {workspace.CampaignName} keeps the downstream continuity target visible."
                    ],
                    ProgressionOutcomes:
                    [
                        "Chosen variant keeps the next safe upgrade checkpoints attached to the dossier.",
                        outputs.Length > 0
                            ? "Export targets already point at dossier and campaign-safe outputs."
                            : "Publication-safe outputs will appear as recap and dossier cards once the first run lands."
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

    private static IReadOnlyList<WorkspaceChangePacketProjection> BuildWorkspaceChangePackets(
        CampaignProjection campaign,
        IReadOnlyList<PublicationSafeProjection> recapShelf,
        RunProjection? leadRun,
        SceneProjection? activeScene,
        ObjectiveProjection? leadObjective)
    {
        List<WorkspaceChangePacketProjection> packets = [];
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

        PublicationSafeProjection? recap = recapShelf.FirstOrDefault();
        if (recap is not null)
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
        IReadOnlyList<RunnerDossierProjection> dossiers)
    {
        return workspaces
            .Select(workspace =>
            {
                var dossier = dossiers.FirstOrDefault(item => string.Equals(item.CampaignId, workspace.CampaignId, StringComparison.OrdinalIgnoreCase));
                var artifact = workspace.RecapShelf.FirstOrDefault()?.ArtifactId ?? StableId("artifact", workspace.WorkspaceId);
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
                    UpdatedAtUtc: workspace.LatestContinuity?.CapturedAtUtc ?? DateTimeOffset.UtcNow);
            })
            .Take(3)
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
}
