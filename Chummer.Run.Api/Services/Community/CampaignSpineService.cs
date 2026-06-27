using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Campaign.Contracts;
using Chummer.Contracts.Receipts;
using Chummer.Contracts.Rulesets;
using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Registry.Services;
using Chummer.Run.Api.Services.Support;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Services.Community;

public sealed class CampaignSpineService
{
    private static readonly JsonSerializerOptions ComparisonJsonOptions = new(JsonSerializerDefaults.Web);
    private static readonly TimeSpan RestoreSnapshotStaleWindow = TimeSpan.FromDays(30);
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
    private const string GovernedConsequenceUpdateSourceKind = "governed_consequence_update";
    private const string ReturnLoopActionSourceKind = "return_loop_action";
    private const string ReturnLoopRouteSourceKind = "return_loop_route";
    private const string GovernedAftermathPackageSourceKind = "governed_aftermath_package";
    private const string TurnLedgerHandoffSourceKind = "turn_ledger_handoff";
    private const string RunboardStateSourceKind = "runboard_state";
    private const string ResolutionReportDraftSourceKind = "resolution_report_draft";
    private const string CampaignAdoptionSourceKind = "campaign_adoption";
    private const string RunnerGoalSourceKind = "runner_goal";
    private const string ResolutionReportApprovalSourceKind = "resolution_report_approval";
    private const string WorldTickSourceKind = "world_tick";
    private const string PlayerSafeNewsSourceKind = "player_safe_news";
    private const string OpenRunListingSourceKind = "open_run_listing";
    private const string OpenRunJoinRequestSourceKind = "open_run_join_request";
    private const string OpenRunScheduleSourceKind = "open_run_schedule";
    private const string OpenRunMeetingHandoffSourceKind = "open_run_meeting_handoff";
    private const string OpenRunCloseoutSourceKind = "open_run_closeout";

    private readonly CommunityStore _store;
    private readonly WorkspaceLifecyclePolicyService _lifecyclePolicy;
    private readonly CampaignArtifactRegistryBridge _artifactRegistry;
    private readonly IHubPublicationDraftService? _publicationDrafts;
    private readonly SupportStore _supportStore;

    public CampaignSpineService(
        CommunityStore store,
        WorkspaceLifecyclePolicyService lifecyclePolicy,
        CampaignArtifactRegistryBridge artifactRegistry,
        IHubPublicationDraftService? publicationDrafts = null)
        : this(store, lifecyclePolicy, artifactRegistry, CreateDefaultSupportStore(), publicationDrafts)
    {
    }

    public CampaignSpineService(
        CommunityStore store,
        WorkspaceLifecyclePolicyService lifecyclePolicy,
        CampaignArtifactRegistryBridge artifactRegistry,
        SupportStore supportStore,
        IHubPublicationDraftService? publicationDrafts = null)
    {
        _store = store;
        _lifecyclePolicy = lifecyclePolicy;
        _artifactRegistry = artifactRegistry;
        _supportStore = supportStore;
        _publicationDrafts = publicationDrafts;
    }

    private static SupportStore CreateDefaultSupportStore()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_SUPPORT_STORE_PATH"] = Path.Combine(
                    Path.GetTempPath(),
                    "chummer6-hub",
                    "support-store",
                    $"campaign-spine-default-{Guid.NewGuid():N}.json")
            })
            .Build();

        return new SupportStore(configuration, NullLogger<SupportStore>.Instance);
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
            var campaignAdoptions = _store.CampaignAdoptions
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
            var runnerGoals = _store.RunnerGoals
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
            var resolutionReportApprovals = _store.ResolutionReportApprovals
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
            var worldTicks = _store.WorldTicks
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
            var playerSafeNews = _store.PlayerSafeNews
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
            var workspaces = campaigns
                .Select(campaign => BuildWorkspaceProjection(campaign, dossiers, runs, crews, restore, transfers, prepLaunches, travelPrefetchReceipts, aftermathPackages, campaignAdoptions, runnerGoals, resolutionReportApprovals, worldTicks, playerSafeNews))
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
                        RecentRosterTransfers: recentRosterTransfers,
                        ArtifactPublicationSummary: ResolveGroupArtifactPublicationSummary(groupWorkspaces),
                        SupportEscalationSummary: ResolveGroupSupportEscalationSummary(user));
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

    public OrganizerOperationsDashboardProjection GetOrganizerOperations(HubUserDto user, InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);

        AccountCampaignSummary summary = GetAccountSummary(user, installLinking);
        IReadOnlyList<OrganizerSupportCaseProjection> supportCases = BuildOrganizerSupportCases(user);

        lock (_store.Gate)
        {
            var items = summary.CommunityOperations
                .Select(operation => BuildOrganizerOperationProjectionLocked(user, summary, operation, supportCases))
                .OrderByDescending(static item => item.EventRail.SeasonBoardCount)
                .ThenByDescending(static item => item.Roster.ActiveCampaignCount)
                .ThenBy(static item => item.GroupName, StringComparer.OrdinalIgnoreCase)
                .ToArray();
            return new OrganizerOperationsDashboardProjection(DateTimeOffset.UtcNow, items);
        }
    }

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

    public IReadOnlyList<OpenRunListingProjection> GetOpenRuns(HubUserDto user, InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);

        AccountCampaignSummary summary = GetAccountSummary(user, installLinking);
        HashSet<string> accessibleCampaignIds = summary.Workspaces
            .Select(static item => item.CampaignId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        lock (_store.Gate)
        {
            return _store.OpenRuns
                .Where(item => IsOpenRunVisibleToUser(item, user.UserId, accessibleCampaignIds, _store.OpenRunJoinRequests, _store.OpenRunRoster))
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
        }
    }

    public OpenRunOrchestrationProjection? GetOpenRun(HubUserDto user, string openRunId, InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentException.ThrowIfNullOrWhiteSpace(openRunId);

        AccountCampaignSummary summary = GetAccountSummary(user, installLinking);
        HashSet<string> accessibleCampaignIds = summary.Workspaces
            .Select(static item => item.CampaignId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        string normalizedOpenRunId = AccountService.NormalizeOptional(openRunId)
            ?? throw new ArgumentException("openRunId is required.", nameof(openRunId));

        lock (_store.Gate)
        {
            OpenRunListingProjection? listing = _store.OpenRuns
                .FirstOrDefault(item => string.Equals(item.OpenRunId, normalizedOpenRunId, StringComparison.OrdinalIgnoreCase));
            if (listing is null
                || !IsOpenRunVisibleToUser(listing, user.UserId, accessibleCampaignIds, _store.OpenRunJoinRequests, _store.OpenRunRoster))
            {
                return null;
            }

            return BuildOpenRunOrchestrationLocked(listing);
        }
    }

    public OpenRunListingProjection CreateOpenRun(
        HubUserDto user,
        string workspaceId,
        OpenRunCreateRequest request,
        InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentException.ThrowIfNullOrWhiteSpace(workspaceId);
        ArgumentNullException.ThrowIfNull(request);

        CampaignWorkspaceProjection workspace = GetWorkspace(user, workspaceId, installLinking)
            ?? throw new KeyNotFoundException($"Unknown workspace: {workspaceId}");
        string normalizedRunId = AccountService.NormalizeOptional(request.RunId)
            ?? workspace.Runs.FirstOrDefault()?.RunId
            ?? throw new InvalidOperationException($"{workspace.CampaignName} does not have a governed run to publish.");
        RunProjection run = workspace.Runs.FirstOrDefault(item => string.Equals(item.RunId, normalizedRunId, StringComparison.OrdinalIgnoreCase))
            ?? throw new KeyNotFoundException($"Unknown run {normalizedRunId} for workspace {workspace.WorkspaceId}.");
        string normalizedListingTitle = AccountService.NormalizeOptional(request.ListingTitle)
            ?? throw new ArgumentException("open run listing_title is required.", nameof(request));
        string normalizedVisibility = AccountService.NormalizeOptional(request.Visibility) ?? "community";
        string normalizedTableContractSummary = AccountService.NormalizeOptional(request.TableContractSummary)
            ?? throw new ArgumentException("open run table_contract_summary is required.", nameof(request));
        string normalizedAdmissionMode = AccountService.NormalizeOptional(request.AdmissionMode) ?? "request_to_join";
        string normalizedSchedulingMode = AccountService.NormalizeOptional(request.SchedulingMode) ?? "lunacal_slots";
        string normalizedPlatform = AccountService.NormalizeOptional(request.Platform) ?? "discord";
        string normalizedObserverMode = AccountService.NormalizeOptional(request.ObserverMode) ?? "manual_markers";
        string? normalizedSummary = AccountService.NormalizeOptional(request.Summary);
        string? normalizedNote = AccountService.NormalizeOptional(request.Note);
        if (request.SeatsTotal <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(request), "open run seats_total must be positive.");
        }

        if (request.ExpectedDurationMinutes <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(request), "open run expected_duration_minutes must be positive.");
        }

        lock (_store.Gate)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            IReadOnlyList<string> reservedSeatRoles = FinalizeLines(request.ReservedSeatRoles ?? Array.Empty<string>());
            var joinPolicy = new OpenRunJoinPolicyProjection(
                AdmissionMode: normalizedAdmissionMode,
                SeatsTotal: request.SeatsTotal,
                ReservedSeatRoles: reservedSeatRoles,
                RequireRunnerDossier: request.RequireRunnerDossier,
                AllowQuickstartRunner: request.AllowQuickstartRunner,
                RuleEnvironmentFingerprint: workspace.RuleEnvironment.CompatibilityFingerprint,
                SchedulingMode: normalizedSchedulingMode,
                ExpectedDurationMinutes: request.ExpectedDurationMinutes,
                CommunicationPlatform: normalizedPlatform,
                VoiceRequired: request.VoiceRequired,
                ObserverMode: normalizedObserverMode,
                Summary: $"{normalizedAdmissionMode.Replace('_', ' ')} · {request.SeatsTotal} seats · {normalizedPlatform} · {workspace.RuleEnvironment.CompatibilityFingerprint}");
            var listing = new OpenRunListingProjection(
                OpenRunId: StableId("open-run", $"{workspace.WorkspaceId}:{run.RunId}:{normalizedListingTitle}:{now.ToUnixTimeMilliseconds()}"),
                WorkspaceId: workspace.WorkspaceId,
                CampaignId: workspace.CampaignId,
                RunId: run.RunId,
                RunTitle: run.Title,
                ListingTitle: normalizedListingTitle,
                Visibility: normalizedVisibility,
                Status: "listed",
                Summary: normalizedSummary ?? $"{run.Title} is open for governed recruitment, scheduling, and closeout on the shared hub lane.",
                TableContractSummary: normalizedTableContractSummary,
                JoinPolicy: joinPolicy,
                SchedulingPosture: "No scheduling receipt is attached yet; Chummer still owns the eventual session time and meeting handoff truth.",
                QuickstartAllowed: request.AllowQuickstartRunner,
                EvidenceLines: FinalizeLines(
                [
                    $"{normalizedListingTitle} attaches {run.Title} to a governed open-run listing.",
                    $"Source kind: {OpenRunListingSourceKind}.",
                    $"Table contract: {normalizedTableContractSummary}",
                    $"Join policy: {joinPolicy.Summary}",
                    $"Observer mode: {normalizedObserverMode}.",
                    "Discord, calendar, Teams, and VTT providers remain projection-only surfaces instead of run authority.",
                    normalizedNote is null ? string.Empty : $"Operator note: {normalizedNote}"
                ]),
                CreatedByUserId: user.UserId,
                CreatedAtUtc: now,
                UpdatedAtUtc: now);

            UpsertOpenRunListingLocked(_store, listing);
            _store.PersistLocked();
            return listing;
        }
    }

    public OpenRunJoinRequestProjection SubmitOpenRunJoinRequest(
        HubUserDto user,
        string openRunId,
        OpenRunJoinRequestCommand request,
        InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentException.ThrowIfNullOrWhiteSpace(openRunId);
        ArgumentNullException.ThrowIfNull(request);

        OpenRunOrchestrationProjection openRun = GetOpenRun(user, openRunId, installLinking)
            ?? throw new KeyNotFoundException($"Unknown open run: {openRunId}");
        AccountCampaignSummary summary = GetAccountSummary(user, installLinking);
        string? normalizedDossierId = AccountService.NormalizeOptional(request.DossierId);
        string? normalizedQuickstartPackId = AccountService.NormalizeOptional(request.QuickstartPackId);
        string? normalizedNote = AccountService.NormalizeOptional(request.Note);
        RunnerDossierProjection? dossier = normalizedDossierId is null
            ? null
            : summary.Dossiers.FirstOrDefault(item => string.Equals(item.DossierId, normalizedDossierId, StringComparison.OrdinalIgnoreCase));
        if (normalizedDossierId is not null && dossier is null)
        {
            throw new CommunityAccessDeniedException($"Runner dossier {normalizedDossierId} is not available on this account.");
        }

        if (dossier is null && normalizedQuickstartPackId is null)
        {
            throw new ArgumentException("join request needs a runner dossier or quickstart pack.", nameof(request));
        }

        List<string> conflicts = [];
        List<string> warnings = [];
        if (!request.TableContractAcknowledged)
        {
            conflicts.Add("The table contract still needs explicit acknowledgement before this join request can reach GM review.");
        }

        if (openRun.Listing.JoinPolicy.VoiceRequired && !request.VoiceConsentAcknowledged)
        {
            conflicts.Add("Voice participation still needs explicit acknowledgement before roster review.");
        }

        if (!request.PlatformReady)
        {
            warnings.Add("Platform readiness still needs confirmation before the meeting details can stay green.");
        }

        if (dossier is not null
            && !string.Equals(dossier.RuleEnvironment.CompatibilityFingerprint, openRun.Listing.JoinPolicy.RuleEnvironmentFingerprint, StringComparison.OrdinalIgnoreCase))
        {
            conflicts.Add($"Runner dossier {dossier.RunnerHandle} is pinned to {dossier.RuleEnvironment.CompatibilityFingerprint}, but {openRun.Listing.ListingTitle} requires {openRun.Listing.JoinPolicy.RuleEnvironmentFingerprint}.");
        }

        if (dossier is null && !openRun.Listing.QuickstartAllowed)
        {
            conflicts.Add("This open run does not allow the quickstart participation path.");
        }

        string preflightSummary = conflicts.Count == 0
            ? $"{(dossier?.RunnerHandle ?? normalizedQuickstartPackId)} clears legality, table-contract, and handoff preflight for {openRun.Listing.ListingTitle}."
            : $"{openRun.Listing.ListingTitle} still has {conflicts.Count} explainable preflight conflict(s) before GM review can accept this join request.";
        string nextSafeAction = conflicts.Count == 0
            ? "Wait for the GM to review the join request on the governed open-run lane."
            : "Resolve the explainable preflight conflicts before the GM locks the roster.";
        DateTimeOffset now = DateTimeOffset.UtcNow;
        var joinRequest = new OpenRunJoinRequestProjection(
            RequestId: StableId("open-run-request", $"{openRun.Listing.OpenRunId}:{user.UserId}"),
            OpenRunId: openRun.Listing.OpenRunId,
            ApplicantUserId: user.UserId,
            ApplicantDisplayName: user.DisplayName,
            DossierId: dossier?.DossierId,
            RunnerHandle: dossier?.RunnerHandle,
            QuickstartPackId: normalizedQuickstartPackId,
            PreflightSummary: preflightSummary,
            Conflicts: conflicts,
            Warnings: warnings,
            NextSafeAction: nextSafeAction,
            Status: conflicts.Count == 0 ? "pending_review" : "preflight_attention",
            EvidenceLines: FinalizeLines(
            [
                preflightSummary,
                $"Source kind: {OpenRunJoinRequestSourceKind}.",
                dossier is null
                    ? $"Quickstart path: {normalizedQuickstartPackId}."
                    : $"Runner dossier: {dossier.RunnerHandle} / {dossier.RuleEnvironment.CompatibilityFingerprint}.",
                $"Table contract acknowledged: {(request.TableContractAcknowledged ? "yes" : "no")}.",
                $"Voice handoff acknowledged: {(request.VoiceConsentAcknowledged ? "yes" : "no")}.",
                request.PlatformReady ? "Platform readiness is already confirmed." : "Platform readiness still needs confirmation.",
                conflicts.Count == 0 ? "No legality or consent conflicts remain on the governed preflight rail." : $"Preflight conflicts: {string.Join("; ", conflicts)}",
                warnings.Count == 0 ? string.Empty : $"Preflight warnings: {string.Join("; ", warnings)}",
                normalizedNote is null ? string.Empty : $"Applicant note: {normalizedNote}"
            ]),
            SubmittedAtUtc: now,
            UpdatedAtUtc: now);

        lock (_store.Gate)
        {
            UpsertOpenRunJoinRequestLocked(_store, joinRequest);
            _store.PersistLocked();
            return joinRequest;
        }
    }

    public OpenRunJoinRequestProjection ReviewOpenRunJoinRequest(
        HubUserDto user,
        string openRunId,
        string requestId,
        OpenRunJoinReviewRequest request,
        InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentException.ThrowIfNullOrWhiteSpace(openRunId);
        ArgumentException.ThrowIfNullOrWhiteSpace(requestId);
        ArgumentNullException.ThrowIfNull(request);

        OpenRunOrchestrationProjection openRun = GetOpenRun(user, openRunId, installLinking)
            ?? throw new KeyNotFoundException($"Unknown open run: {openRunId}");
        if (!string.Equals(openRun.Listing.CreatedByUserId, user.UserId, StringComparison.OrdinalIgnoreCase))
        {
            throw new CommunityAccessDeniedException("Only the open-run owner can review join requests.");
        }

        string normalizedRequestId = AccountService.NormalizeOptional(requestId)
            ?? throw new ArgumentException("requestId is required.", nameof(requestId));
        string normalizedDecision = AccountService.NormalizeOptional(request.Decision)?.ToLowerInvariant() switch
        {
            "accepted" => "accepted",
            "waitlisted" => "waitlisted",
            "rejected" => "rejected",
            _ => throw new ArgumentException($"Unsupported open-run review decision: {request.Decision}", nameof(request))
        };
        string? normalizedNote = AccountService.NormalizeOptional(request.Note);

        lock (_store.Gate)
        {
            OpenRunJoinRequestProjection existingRequest = _store.OpenRunJoinRequests
                .FirstOrDefault(item =>
                    string.Equals(item.OpenRunId, openRun.Listing.OpenRunId, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.RequestId, normalizedRequestId, StringComparison.OrdinalIgnoreCase))
                ?? throw new KeyNotFoundException($"Unknown join request {normalizedRequestId} for {openRun.Listing.ListingTitle}.");
            if (string.Equals(normalizedDecision, "accepted", StringComparison.OrdinalIgnoreCase) && existingRequest.Conflicts.Count > 0)
            {
                throw new InvalidOperationException("Join requests with explainable preflight conflicts cannot be accepted until the conflicts are resolved.");
            }

            DateTimeOffset now = DateTimeOffset.UtcNow;
            var reviewedRequest = existingRequest with
            {
                Status = normalizedDecision,
                EvidenceLines = FinalizeLines(existingRequest.EvidenceLines.Concat(
                [
                    $"GM review decision: {normalizedDecision}.",
                    normalizedNote is null ? string.Empty : $"GM review note: {normalizedNote}"
                ])),
                UpdatedAtUtc = now
            };
            UpsertOpenRunJoinRequestLocked(_store, reviewedRequest);

            _store.OpenRunRoster.RemoveAll(item =>
                string.Equals(item.OpenRunId, openRun.Listing.OpenRunId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.UserId, reviewedRequest.ApplicantUserId, StringComparison.OrdinalIgnoreCase));
            if (!string.Equals(normalizedDecision, "rejected", StringComparison.OrdinalIgnoreCase))
            {
                _store.OpenRunRoster.Add(new OpenRunRosterEntryProjection(
                    EntryId: StableId("open-run-roster", $"{openRun.Listing.OpenRunId}:{reviewedRequest.ApplicantUserId}"),
                    OpenRunId: openRun.Listing.OpenRunId,
                    UserId: reviewedRequest.ApplicantUserId,
                    DisplayName: reviewedRequest.ApplicantDisplayName,
                    DossierId: reviewedRequest.DossierId,
                    RunnerHandle: reviewedRequest.RunnerHandle,
                    SeatStatus: normalizedDecision,
                    SeatSummary: string.Equals(normalizedDecision, "accepted", StringComparison.OrdinalIgnoreCase)
                        ? $"{reviewedRequest.ApplicantDisplayName} is accepted onto the governed roster for {openRun.Listing.ListingTitle}."
                        : $"{reviewedRequest.ApplicantDisplayName} stays waitlisted on the governed roster for {openRun.Listing.ListingTitle}.",
                    UpdatedAtUtc: now));
                _store.OpenRunRoster.Sort(static (left, right) => right.UpdatedAtUtc.CompareTo(left.UpdatedAtUtc));
            }

            int acceptedCount = _store.OpenRunRoster.Count(item =>
                string.Equals(item.OpenRunId, openRun.Listing.OpenRunId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.SeatStatus, "accepted", StringComparison.OrdinalIgnoreCase));
            string listingStatus = acceptedCount >= openRun.Listing.JoinPolicy.SeatsTotal
                ? "roster_locked"
                : acceptedCount > 0
                    ? "roster_forming"
                    : "listed";
            UpsertOpenRunListingLocked(_store, openRun.Listing with
            {
                Status = listingStatus,
                UpdatedAtUtc = now
            });

            _store.PersistLocked();
            return reviewedRequest;
        }
    }

    public OpenRunScheduleReceiptProjection ScheduleOpenRun(
        HubUserDto user,
        string openRunId,
        OpenRunScheduleRequest request,
        InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentException.ThrowIfNullOrWhiteSpace(openRunId);
        ArgumentNullException.ThrowIfNull(request);

        OpenRunOrchestrationProjection openRun = GetOpenRun(user, openRunId, installLinking)
            ?? throw new KeyNotFoundException($"Unknown open run: {openRunId}");
        if (!string.Equals(openRun.Listing.CreatedByUserId, user.UserId, StringComparison.OrdinalIgnoreCase))
        {
            throw new CommunityAccessDeniedException("Only the open-run owner can schedule this run.");
        }

        string normalizedTimezone = AccountService.NormalizeOptional(request.Timezone) ?? "UTC";
        string? normalizedNote = AccountService.NormalizeOptional(request.Note);
        if (request.StartsAtUtc <= DateTimeOffset.UtcNow.AddMinutes(-1))
        {
            throw new ArgumentOutOfRangeException(nameof(request), "open run schedule must stay in the future.");
        }

        IReadOnlyList<OpenRunRosterEntryProjection> acceptedRoster = openRun.Roster
            .Where(item => string.Equals(item.SeatStatus, "accepted", StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (acceptedRoster.Count == 0)
        {
            throw new InvalidOperationException("Open runs need at least one accepted roster entry before scheduling.");
        }

        DateTimeOffset now = DateTimeOffset.UtcNow;
        var receipt = new OpenRunScheduleReceiptProjection(
            ReceiptId: StableId("open-run-schedule", openRun.Listing.OpenRunId),
            OpenRunId: openRun.Listing.OpenRunId,
            SchedulingMode: openRun.Listing.JoinPolicy.SchedulingMode,
            StartsAtUtc: request.StartsAtUtc,
            ExpectedDurationMinutes: openRun.Listing.JoinPolicy.ExpectedDurationMinutes,
            Platform: openRun.Listing.JoinPolicy.CommunicationPlatform,
            Timezone: normalizedTimezone,
            Summary: $"{openRun.Listing.ListingTitle} is scheduled for {request.StartsAtUtc:yyyy-MM-dd HH:mm} {normalizedTimezone} with {acceptedRoster.Count} accepted seat(s) on the governed {openRun.Listing.JoinPolicy.CommunicationPlatform} lane.",
            EvidenceLines: FinalizeLines(
            [
                $"Source kind: {OpenRunScheduleSourceKind}.",
                $"Accepted roster: {acceptedRoster.Count} seat(s).",
                $"Scheduling mode: {openRun.Listing.JoinPolicy.SchedulingMode}.",
                $"Platform: {openRun.Listing.JoinPolicy.CommunicationPlatform}.",
                normalizedNote is null ? string.Empty : $"GM scheduling note: {normalizedNote}"
            ]),
            ScheduledByUserId: user.UserId,
            ScheduledAtUtc: now,
            Envelope: ReceiptEnvelopeFactory.Runtime(
                receiptKind: "open_run_schedule",
                ownerScope: "community.open_run",
                exposureClass: ReceiptExposureClasses.SignedIn,
                evidenceRef: openRun.Listing.OpenRunId,
                reviewState: "scheduled"));

        lock (_store.Gate)
        {
            UpsertOpenRunScheduleLocked(_store, receipt);
            UpsertOpenRunListingLocked(_store, openRun.Listing with
            {
                Status = "scheduled",
                SchedulingPosture = receipt.Summary,
                UpdatedAtUtc = now
            });
            _store.PersistLocked();
            return receipt;
        }
    }

    public OpenRunMeetingHandoffProjection CreateOpenRunMeetingHandoff(
        HubUserDto user,
        string openRunId,
        OpenRunMeetingHandoffRequest request,
        InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentException.ThrowIfNullOrWhiteSpace(openRunId);
        ArgumentNullException.ThrowIfNull(request);

        OpenRunOrchestrationProjection openRun = GetOpenRun(user, openRunId, installLinking)
            ?? throw new KeyNotFoundException($"Unknown open run: {openRunId}");
        if (!string.Equals(openRun.Listing.CreatedByUserId, user.UserId, StringComparison.OrdinalIgnoreCase))
        {
            throw new CommunityAccessDeniedException("Only the open-run owner can issue a meeting handoff.");
        }

        OpenRunScheduleReceiptProjection schedule = openRun.Schedule
            ?? throw new InvalidOperationException("Open runs need a governed scheduling receipt before meeting handoff.");
        string normalizedProviderKind = AccountService.NormalizeOptional(request.ProviderKind)
            ?? throw new ArgumentException("meeting handoff provider_kind is required.", nameof(request));
        string normalizedProviderLabel = AccountService.NormalizeOptional(request.ProviderLabel)
            ?? throw new ArgumentException("meeting handoff provider_label is required.", nameof(request));
        string normalizedAccessPolicy = AccountService.NormalizeOptional(request.AccessPolicy)
            ?? throw new ArgumentException("meeting handoff access_policy is required.", nameof(request));
        string? normalizedNote = AccountService.NormalizeOptional(request.Note);
        if (request.ExpiresAtUtc <= DateTimeOffset.UtcNow)
        {
            throw new ArgumentOutOfRangeException(nameof(request), "meeting handoff expiry must stay in the future.");
        }

        IReadOnlyList<string> acceptedUserIds = openRun.Roster
            .Where(item => string.Equals(item.SeatStatus, "accepted", StringComparison.OrdinalIgnoreCase))
            .Select(static item => item.UserId)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
        if (acceptedUserIds.Count == 0)
        {
            throw new InvalidOperationException("Meeting details require at least one accepted roster seat.");
        }

        DateTimeOffset now = DateTimeOffset.UtcNow;
        var handoff = new OpenRunMeetingHandoffProjection(
            HandoffId: StableId("open-run-handoff", openRun.Listing.OpenRunId),
            OpenRunId: openRun.Listing.OpenRunId,
            ProviderKind: normalizedProviderKind,
            ProviderLabel: normalizedProviderLabel,
            AccessPolicy: normalizedAccessPolicy,
            ExpiresAtUtc: request.ExpiresAtUtc,
            AcceptedUserIds: acceptedUserIds,
            Summary: $"{normalizedProviderLabel} is the projection-only meeting handoff for {openRun.Listing.ListingTitle}; accepted roster and consent truth stay in Chummer until {request.ExpiresAtUtc:yyyy-MM-dd HH:mm} UTC.",
            EvidenceLines: FinalizeLines(
            [
                $"Source kind: {OpenRunMeetingHandoffSourceKind}.",
                $"Provider kind: {normalizedProviderKind}.",
                $"Access policy: {normalizedAccessPolicy}.",
                $"Scheduling anchor: {schedule.Summary}",
                $"Accepted users: {string.Join(", ", acceptedUserIds)}.",
                normalizedNote is null ? string.Empty : $"GM handoff note: {normalizedNote}"
            ]),
            CreatedByUserId: user.UserId,
            CreatedAtUtc: now);

        lock (_store.Gate)
        {
            UpsertOpenRunMeetingHandoffLocked(_store, handoff);
            UpsertOpenRunListingLocked(_store, openRun.Listing with
            {
                Status = "handoff_ready",
                UpdatedAtUtc = now
            });
            _store.PersistLocked();
            return handoff;
        }
    }

    public OpenRunCloseoutProjection CloseOutOpenRun(
        HubUserDto user,
        string openRunId,
        OpenRunCloseoutRequest request,
        InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentException.ThrowIfNullOrWhiteSpace(openRunId);
        ArgumentNullException.ThrowIfNull(request);

        OpenRunOrchestrationProjection openRun = GetOpenRun(user, openRunId, installLinking)
            ?? throw new KeyNotFoundException($"Unknown open run: {openRunId}");
        if (!string.Equals(openRun.Listing.CreatedByUserId, user.UserId, StringComparison.OrdinalIgnoreCase))
        {
            throw new CommunityAccessDeniedException("Only the open-run owner can close out this run.");
        }

        if (openRun.Schedule is null || openRun.MeetingHandoff is null)
        {
            throw new InvalidOperationException("Open run closeout requires scheduling and meeting handoff receipts before world-memory promotion.");
        }

        CampaignWorkspaceProjection workspace = GetWorkspace(user, openRun.Listing.WorkspaceId, installLinking)
            ?? throw new KeyNotFoundException($"Unknown workspace: {openRun.Listing.WorkspaceId}");
        ResolutionReportApprovalProjection approval = ApproveResolutionReport(user, workspace, new ResolutionReportApprovalRequest(
            RunId: openRun.Listing.RunId,
            Summary: request.Summary,
            WorldTickSummary: request.WorldTickSummary,
            ConsequenceSummary: request.ConsequenceSummary,
            NewsTitle: request.NewsTitle,
            NewsSummary: request.NewsSummary,
            NewsSource: request.NewsSource,
            NewsUrl: request.NewsUrl,
            NextSafeAction: request.NextSafeAction,
            Note: request.Note));

        lock (_store.Gate)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            var closeout = new OpenRunCloseoutProjection(
                CloseoutId: StableId("open-run-closeout", openRun.Listing.OpenRunId),
                OpenRunId: openRun.Listing.OpenRunId,
                ResolutionApprovalId: approval.ApprovalId,
                WorldTickId: approval.WorldTickId,
                PlayerSafeNewsId: approval.NewsId,
                Summary: request.Summary,
                EvidenceLines: FinalizeLines(
                [
                    request.Summary,
                    $"Source kind: {OpenRunCloseoutSourceKind}.",
                    $"Resolution approval: {approval.ApprovalId}.",
                    $"WorldTick: {approval.WorldTickId}.",
                    $"Player-safe news: {approval.NewsId}.",
                    "Closeout feeds world-memory and player-safe follow-through without making meeting or calendar providers authoritative."
                ]),
                ClosedByUserId: user.UserId,
                ClosedAtUtc: now);

            UpsertOpenRunCloseoutLocked(_store, closeout);
            UpsertOpenRunListingLocked(_store, openRun.Listing with
            {
                Status = "closed",
                UpdatedAtUtc = now
            });
            _store.PersistLocked();
            return closeout;
        }
    }

    public CampaignAdoptionLoopProjection? GetCampaignAdoptionLoop(HubUserDto user, string workspaceId, InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentException.ThrowIfNullOrWhiteSpace(workspaceId);

        return GetWorkspace(user, workspaceId, installLinking)?.CampaignAdoptionLoop;
    }

    public CampaignAdoptionWorkspaceStateProjection? GetWorkspaceCampaignState(
        HubUserDto user,
        string workspaceId,
        InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentException.ThrowIfNullOrWhiteSpace(workspaceId);

        CampaignWorkspaceProjection workspace = GetWorkspace(user, workspaceId, installLinking)
            ?? throw new KeyNotFoundException($"Unknown workspace: {workspaceId}");

        lock (_store.Gate)
        {
            CampaignAdoptionProjection? adoption = _store.CampaignAdoptions
                .Where(item => string.Equals(item.WorkspaceId, workspace.WorkspaceId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .FirstOrDefault();
            RunnerGoalProjection[] runnerGoals = _store.RunnerGoals
                .Where(item => string.Equals(item.WorkspaceId, workspace.WorkspaceId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
            ResolutionReportApprovalProjection[] approvals = _store.ResolutionReportApprovals
                .Where(item => string.Equals(item.WorkspaceId, workspace.WorkspaceId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
            WorldTickProjection[] worldTicks = _store.WorldTicks
                .Where(item => string.Equals(item.WorkspaceId, workspace.WorkspaceId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
            PlayerSafeNewsProjection[] newsItems = _store.PlayerSafeNews
                .Where(item => string.Equals(item.WorkspaceId, workspace.WorkspaceId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();

            if (adoption is null
                && runnerGoals.Length == 0
                && approvals.Length == 0
                && worldTicks.Length == 0
                && newsItems.Length == 0)
            {
                return null;
            }

            return new CampaignAdoptionWorkspaceStateProjection(
                WorkspaceId: workspace.WorkspaceId,
                CampaignAdoption: adoption is null ? null : BuildCampaignAdoptionRecordProjection(workspace, adoption),
                RunnerGoals: runnerGoals.Select(BuildCampaignAdoptionRunnerGoalProjection).ToArray(),
                ResolutionReports: approvals.Select(approval => BuildCampaignAdoptionResolutionReportProjection(workspace, approval, worldTicks)).ToArray(),
                WorldTicks: worldTicks.Select(worldTick => BuildCampaignAdoptionWorldTickProjection(workspace, worldTick)).ToArray(),
                NewsItems: newsItems.Select(newsItem => BuildPlayerSafeNewsItemProjection(workspace, newsItem)).ToArray());
        }
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
            string receiptId = StableId("travel-prefetch", $"{workspace.WorkspaceId}:{device.InstallationId}:{now.ToUnixTimeMilliseconds()}");
            var receipt = new TravelPrefetchReceiptProjection(
                ReceiptId: receiptId,
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
                StagedAtUtc: now,
                Envelope: BuildCampaignReceiptEnvelope("travel_prefetch", receiptId));

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

            if (_store.CampaignSpinesById.TryGetValue(workspace.CampaignId, out var campaign))
            {
                CampaignConsequenceProjection? aftermathConsequence = BuildAftermathConsequenceProjection(workspace, run, package);
                _store.CampaignSpinesById[campaign.CampaignId] = campaign with
                {
                    UpdatedAtUtc = now,
                    Consequences = UpsertGovernedCampaignConsequence(campaign.Consequences, aftermathConsequence),
                };
            }

            _store.PersistLocked();
            return package;
        }
    }

    public CampaignConsequenceProjection UpsertCampaignConsequence(
        HubUserDto user,
        CampaignWorkspaceProjection workspace,
        CampaignConsequenceUpdateRequest request)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentNullException.ThrowIfNull(workspace);
        ArgumentNullException.ThrowIfNull(request);

        string normalizedKind = NormalizeGovernedConsequenceKind(request.Kind);
        string normalizedState = AccountService.NormalizeOptional(request.State)
            ?? throw new ArgumentException("campaign consequence state is required.", nameof(request));
        string normalizedSummary = AccountService.NormalizeOptional(request.Summary)
            ?? throw new ArgumentException("campaign consequence summary is required.", nameof(request));
        string? normalizedNote = AccountService.NormalizeOptional(request.Note);

        lock (_store.Gate)
        {
            if (!_store.CampaignSpinesById.TryGetValue(workspace.CampaignId, out var campaign))
            {
                throw new KeyNotFoundException($"Unknown campaign: {workspace.CampaignId}");
            }

            DateTimeOffset observedAtUtc = DateTimeOffset.UtcNow;
            CampaignConsequenceProjection consequence = BuildGovernedCampaignConsequenceProjection(
                workspace,
                normalizedKind,
                normalizedState,
                normalizedSummary,
                request.ReturnLoopAction,
                request.ReturnLoopRoute,
                normalizedNote,
                observedAtUtc);

            _store.CampaignSpinesById[campaign.CampaignId] = campaign with
            {
                UpdatedAtUtc = observedAtUtc,
                Consequences = UpsertGovernedCampaignConsequence(campaign.Consequences, consequence),
            };

            _store.PersistLocked();
            return consequence;
        }
    }

    public RunboardContinuityProjection UpsertRunboardContinuity(
        HubUserDto user,
        CampaignWorkspaceProjection workspace,
        RunboardContinuityUpdateRequest request)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentNullException.ThrowIfNull(workspace);
        ArgumentNullException.ThrowIfNull(request);

        string normalizedRunId = AccountService.NormalizeOptional(request.RunId)
            ?? workspace.Runs.FirstOrDefault()?.RunId
            ?? throw new InvalidOperationException($"{workspace.CampaignName} does not have a governed run to persist.");
        string normalizedTurnLedgerSummary = AccountService.NormalizeOptional(request.TurnLedgerSummary)
            ?? throw new ArgumentException("turn-ledger summary is required.", nameof(request));
        string normalizedRunboardStateSummary = AccountService.NormalizeOptional(request.RunboardStateSummary)
            ?? throw new ArgumentException("runboard state summary is required.", nameof(request));
        string normalizedResolutionStatus = AccountService.NormalizeOptional(request.ResolutionReportStatus)
            ?? throw new ArgumentException("resolution-report status is required.", nameof(request));
        string normalizedResolutionSummary = AccountService.NormalizeOptional(request.ResolutionReportSummary)
            ?? throw new ArgumentException("resolution-report summary is required.", nameof(request));
        string? normalizedNextSafeAction = AccountService.NormalizeOptional(request.NextSafeAction);
        string? normalizedNote = AccountService.NormalizeOptional(request.Note);

        lock (_store.Gate)
        {
            if (!_store.RunsById.TryGetValue(normalizedRunId, out var storedRun)
                || !string.Equals(storedRun.CampaignId, workspace.CampaignId, StringComparison.OrdinalIgnoreCase))
            {
                throw new KeyNotFoundException($"Unknown run {normalizedRunId} for workspace {workspace.WorkspaceId}.");
            }

            if (!_store.CampaignSpinesById.TryGetValue(workspace.CampaignId, out var campaign))
            {
                throw new KeyNotFoundException($"Unknown campaign: {workspace.CampaignId}");
            }

            string? normalizedSceneId = AccountService.NormalizeOptional(request.ActiveSceneId);
            SceneProjection? activeScene = normalizedSceneId is null
                ? storedRun.Scenes.FirstOrDefault(item => string.Equals(item.SceneId, storedRun.ActiveSceneId, StringComparison.OrdinalIgnoreCase))
                    ?? storedRun.Scenes.OrderByDescending(static item => item.UpdatedAtUtc).FirstOrDefault()
                : storedRun.Scenes.FirstOrDefault(item => string.Equals(item.SceneId, normalizedSceneId, StringComparison.OrdinalIgnoreCase));
            if (normalizedSceneId is not null && activeScene is null)
            {
                throw new KeyNotFoundException($"Run {storedRun.RunId} does not contain scene {normalizedSceneId}.");
            }

            DateTimeOffset now = DateTimeOffset.UtcNow;
            IReadOnlyList<string> objectiveLines = FinalizeLines(
                (request.ObjectiveLines ?? Array.Empty<string>())
                    .Concat(
                        storedRun.Objectives
                            .Where(static item => !string.Equals(item.Status, "closed", StringComparison.OrdinalIgnoreCase)
                                && !string.Equals(item.Status, "done", StringComparison.OrdinalIgnoreCase))
                            .Select(static item => $"{item.Title} stays {item.Status} with {item.Pressure} pressure.")));
            IReadOnlyList<string> blockerLines = FinalizeLines(
                (request.Blockers ?? Array.Empty<string>())
                    .Concat(
                        storedRun.Objectives
                            .Where(static item => !string.Equals(item.Status, "closed", StringComparison.OrdinalIgnoreCase)
                                && !string.Equals(item.Status, "done", StringComparison.OrdinalIgnoreCase))
                            .Select(static item => $"Clear {item.Title} before you close the current runboard handoff.")));
            string nextSafeAction = normalizedNextSafeAction
                ?? $"Open ResolutionReport for {storedRun.Title} and keep the next governed return on /account/work.";
            IReadOnlyList<string> turnLedgerEvidenceLines = FinalizeLines(
                new[]
                {
                    normalizedTurnLedgerSummary,
                    $"Source kind: {TurnLedgerHandoffSourceKind}.",
                    activeScene is null
                        ? $"Turn ledger handoff stays pinned to {storedRun.Title} without replaying engine math inside hub."
                        : $"Turn ledger handoff stays pinned to {storedRun.Title} / {activeScene.Title} without replaying engine math inside hub.",
                    normalizedNote is null ? string.Empty : $"Operator note: {normalizedNote}"
                }.Concat(request.TurnLedgerEvidenceLines ?? Array.Empty<string>()));
            IReadOnlyList<string> runboardStateEvidenceLines = FinalizeLines(
            [
                normalizedRunboardStateSummary,
                $"Source kind: {RunboardStateSourceKind}.",
                $"{objectiveLines.Count} objective line(s) and {blockerLines.Count} blocker line(s) stay on the same governed campaign spine.",
                $"Next safe action: {nextSafeAction}"
            ]);
            IReadOnlyList<string> resolutionNotes = FinalizeLines(
                new[]
                {
                    normalizedResolutionSummary
                }.Concat(request.ResolutionNotes ?? Array.Empty<string>()));
            IReadOnlyList<string> resolutionEvidenceLines = FinalizeLines(
            [
                normalizedResolutionSummary,
                $"Source kind: {ResolutionReportDraftSourceKind}.",
                $"ResolutionReport draft remains {normalizedResolutionStatus} for {storedRun.Title} on the hub continuity lane.",
                $"Next safe action: {nextSafeAction}"
            ]);

            var continuity = new RunboardContinuityProjection(
                ContinuityId: StableId("runboard-continuity", $"{workspace.WorkspaceId}:{storedRun.RunId}"),
                WorkspaceId: workspace.WorkspaceId,
                CampaignId: workspace.CampaignId,
                RunId: storedRun.RunId,
                RunTitle: storedRun.Title,
                ActiveSceneId: activeScene?.SceneId,
                ActiveSceneTitle: activeScene?.Title,
                TurnLedgerHandoff: new TurnLedgerHandoffProjection(
                    HandoffId: StableId("turn-ledger", $"{workspace.WorkspaceId}:{storedRun.RunId}"),
                    Summary: normalizedTurnLedgerSummary,
                    EvidenceLines: turnLedgerEvidenceLines,
                    UpdatedAtUtc: now),
                RunboardState: new RunboardStateProjection(
                    StateId: StableId("runboard-state", $"{workspace.WorkspaceId}:{storedRun.RunId}"),
                    Summary: normalizedRunboardStateSummary,
                    ObjectiveLines: objectiveLines,
                    Blockers: blockerLines,
                    NextSafeAction: nextSafeAction,
                    EvidenceLines: runboardStateEvidenceLines,
                    UpdatedAtUtc: now),
                ResolutionReportDraft: new ResolutionReportDraftProjection(
                    DraftId: StableId("resolution-report-draft", $"{workspace.WorkspaceId}:{storedRun.RunId}"),
                    Status: normalizedResolutionStatus,
                    Summary: normalizedResolutionSummary,
                    Notes: resolutionNotes,
                    NextSafeAction: nextSafeAction,
                    EvidenceLines: resolutionEvidenceLines,
                    UpdatedAtUtc: now),
                Summary: $"{storedRun.Title} keeps a persisted turn-ledger handoff, runboard state, and ResolutionReport draft on the reviewed hub path.",
                EvidenceLines: FinalizeLines(
                [
                    $"Turn ledger handoff: {normalizedTurnLedgerSummary}",
                    $"Runboard state: {normalizedRunboardStateSummary}",
                    $"ResolutionReport draft: {normalizedResolutionSummary}",
                    $"Boundary: hub persists continuity and draft posture without replaying engine math.",
                    activeScene is null ? string.Empty : $"Active scene: {activeScene.Title}.",
                    $"Next safe action: {nextSafeAction}",
                    normalizedNote is null ? string.Empty : $"Operator note: {normalizedNote}"
                ]),
                UpdatedByUserId: user.UserId,
                UpdatedAtUtc: now);

            _store.RunsById[storedRun.RunId] = storedRun with
            {
                ActiveSceneId = activeScene?.SceneId ?? storedRun.ActiveSceneId,
                UpdatedAtUtc = now,
                RunboardContinuity = continuity,
            };
            _store.CampaignSpinesById[campaign.CampaignId] = campaign with
            {
                ActiveRunId = storedRun.RunId,
                UpdatedAtUtc = now,
            };

            _store.PersistLocked();
            return continuity;
        }
    }

    public CampaignAdoptionProjection UpsertCampaignAdoption(
        HubUserDto user,
        CampaignWorkspaceProjection workspace,
        CampaignAdoptionUpdateRequest request)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentNullException.ThrowIfNull(workspace);
        ArgumentNullException.ThrowIfNull(request);

        string normalizedSummary = AccountService.NormalizeOptional(request.Summary)
            ?? throw new ArgumentException("campaign adoption summary is required.", nameof(request));
        string? normalizedNextSafeAction = AccountService.NormalizeOptional(request.NextSafeAction);
        string? normalizedNote = AccountService.NormalizeOptional(request.Note);
        if (request.ConfidencePercent is < 0 or > 100)
        {
            throw new ArgumentOutOfRangeException(nameof(request), "campaign adoption confidence_percent must stay within 0..100.");
        }

        if (request.RunnerCount < 0 || request.ActiveJobCount < 0 || request.ContactCount < 0 || request.HouseRuleCount < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(request), "campaign adoption counts cannot be negative.");
        }

        lock (_store.Gate)
        {
            if (!_store.CampaignSpinesById.TryGetValue(workspace.CampaignId, out var campaign))
            {
                throw new KeyNotFoundException($"Unknown campaign: {workspace.CampaignId}");
            }

            DateTimeOffset now = DateTimeOffset.UtcNow;
            IReadOnlyList<string> explicitUnknowns = FinalizeLines(request.ExplicitUnknowns ?? Array.Empty<string>());
            IReadOnlyList<string> recommendedNextActions = FinalizeLines(request.RecommendedNextActions ?? Array.Empty<string>());
            string nextSafeAction = normalizedNextSafeAction
                ?? recommendedNextActions.FirstOrDefault()
                ?? (request.SafeToPlay
                    ? "Open the reviewed workspace return on /account/work."
                    : "Resolve the adoption unknowns before reopening the shared campaign return on /account/work.");

            var adoption = new CampaignAdoptionProjection(
                AdoptionId: StableId("campaign-adoption", workspace.WorkspaceId),
                WorkspaceId: workspace.WorkspaceId,
                CampaignId: workspace.CampaignId,
                SafeToPlay: request.SafeToPlay,
                ConfidencePercent: request.ConfidencePercent,
                RunnerCount: request.RunnerCount,
                ActiveJobCount: request.ActiveJobCount,
                ContactCount: request.ContactCount,
                HouseRuleCount: request.HouseRuleCount,
                ExplicitUnknowns: explicitUnknowns,
                RecommendedNextActions: recommendedNextActions,
                Summary: normalizedSummary,
                NextSafeAction: nextSafeAction,
                EvidenceLines: FinalizeLines(
                [
                    normalizedSummary,
                    $"Source kind: {CampaignAdoptionSourceKind}.",
                    $"Safe to play: {(request.SafeToPlay ? "yes" : "not yet")}.",
                    $"Confidence: {request.ConfidencePercent}%.",
                    $"Known counts: {request.RunnerCount} runner(s), {request.ActiveJobCount} active job(s), {request.ContactCount} contact(s), {request.HouseRuleCount} house-rule pack(s).",
                    explicitUnknowns.Count == 0 ? "Unknown provenance remains empty for the current adoption pass." : $"Explicit unknowns: {string.Join("; ", explicitUnknowns)}",
                    recommendedNextActions.Count == 0 ? string.Empty : $"Recommended next actions: {string.Join("; ", recommendedNextActions)}",
                    $"Next safe action: {nextSafeAction}",
                    normalizedNote is null ? string.Empty : $"Operator note: {normalizedNote}"
                ]),
                UpdatedByUserId: user.UserId,
                UpdatedAtUtc: now);

            _store.CampaignAdoptions.RemoveAll(item => string.Equals(item.AdoptionId, adoption.AdoptionId, StringComparison.OrdinalIgnoreCase));
            _store.CampaignAdoptions.Add(adoption);
            _store.CampaignAdoptions.Sort(static (left, right) => right.UpdatedAtUtc.CompareTo(left.UpdatedAtUtc));
            if (_store.CampaignAdoptions.Count > 64)
            {
                _store.CampaignAdoptions.RemoveRange(64, _store.CampaignAdoptions.Count - 64);
            }

            _store.CampaignSpinesById[campaign.CampaignId] = campaign with
            {
                UpdatedAtUtc = now,
            };

            _store.PersistLocked();
            return adoption;
        }
    }

    public RunnerGoalProjection UpsertRunnerGoal(
        HubUserDto user,
        CampaignWorkspaceProjection workspace,
        RunnerGoalUpdateRequest request)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentNullException.ThrowIfNull(workspace);
        ArgumentNullException.ThrowIfNull(request);

        string normalizedDossierId = AccountService.NormalizeOptional(request.DossierId)
            ?? throw new ArgumentException("runner goal dossier_id is required.", nameof(request));
        string normalizedLabel = AccountService.NormalizeOptional(request.Label)
            ?? throw new ArgumentException("runner goal label is required.", nameof(request));
        string normalizedTargetKind = AccountService.NormalizeOptional(request.TargetKind)
            ?? throw new ArgumentException("runner goal target_kind is required.", nameof(request));
        string normalizedTargetReference = AccountService.NormalizeOptional(request.TargetReference)
            ?? throw new ArgumentException("runner goal target_reference is required.", nameof(request));
        string normalizedApprovalStatus = AccountService.NormalizeOptional(request.ApprovalStatus)
            ?? throw new ArgumentException("runner goal approval_status is required.", nameof(request));
        string? normalizedNextSafeAction = AccountService.NormalizeOptional(request.NextSafeAction);
        string? normalizedNote = AccountService.NormalizeOptional(request.Note);
        if (request.SavedNuyen < 0 || request.NuyenRequired < 0 || request.KarmaReserved < 0 || request.DowntimeDays < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(request), "runner goal resource values cannot be negative.");
        }

        lock (_store.Gate)
        {
            if (!_store.CampaignSpinesById.TryGetValue(workspace.CampaignId, out var campaign))
            {
                throw new KeyNotFoundException($"Unknown campaign: {workspace.CampaignId}");
            }

            if (!_store.DossiersById.TryGetValue(normalizedDossierId, out var dossier)
                || !string.Equals(dossier.CampaignId, workspace.CampaignId, StringComparison.OrdinalIgnoreCase))
            {
                throw new KeyNotFoundException($"Unknown dossier {normalizedDossierId} for workspace {workspace.WorkspaceId}.");
            }

            DateTimeOffset now = DateTimeOffset.UtcNow;
            string nextSafeAction = normalizedNextSafeAction
                ?? $"Advance {dossier.RunnerHandle}'s goal pin on /account/work#runner-goals before the next governed closeout.";
            var goal = new RunnerGoalProjection(
                GoalId: StableId("runner-goal", $"{workspace.WorkspaceId}:{normalizedDossierId}:{normalizedTargetKind}:{normalizedTargetReference}"),
                WorkspaceId: workspace.WorkspaceId,
                CampaignId: workspace.CampaignId,
                DossierId: dossier.DossierId,
                RunnerHandle: dossier.RunnerHandle,
                Label: normalizedLabel,
                TargetKind: normalizedTargetKind,
                TargetReference: normalizedTargetReference,
                SavedNuyen: request.SavedNuyen,
                NuyenRequired: request.NuyenRequired,
                KarmaReserved: request.KarmaReserved,
                DowntimeDays: request.DowntimeDays,
                RuleEnvironmentFingerprint: workspace.RuleEnvironment.CompatibilityFingerprint,
                ApprovalStatus: normalizedApprovalStatus,
                NextSafeAction: nextSafeAction,
                EvidenceLines: FinalizeLines(
                [
                    $"{dossier.RunnerHandle}: {normalizedLabel}.",
                    $"Source kind: {RunnerGoalSourceKind}.",
                    $"Target: {normalizedTargetKind} / {normalizedTargetReference}.",
                    $"Resources: {request.SavedNuyen}/{request.NuyenRequired} nuyen saved, {request.KarmaReserved} karma reserved, {request.DowntimeDays} downtime day(s).",
                    $"Rule environment: {workspace.RuleEnvironment.CompatibilityFingerprint}.",
                    $"Approval posture: {normalizedApprovalStatus}.",
                    $"Next safe action: {nextSafeAction}",
                    normalizedNote is null ? string.Empty : $"Operator note: {normalizedNote}"
                ]),
                UpdatedByUserId: user.UserId,
                UpdatedAtUtc: now);

            _store.RunnerGoals.RemoveAll(item => string.Equals(item.GoalId, goal.GoalId, StringComparison.OrdinalIgnoreCase));
            _store.RunnerGoals.Add(goal);
            _store.RunnerGoals.Sort(static (left, right) => right.UpdatedAtUtc.CompareTo(left.UpdatedAtUtc));
            if (_store.RunnerGoals.Count > 128)
            {
                _store.RunnerGoals.RemoveRange(128, _store.RunnerGoals.Count - 128);
            }

            _store.CampaignSpinesById[campaign.CampaignId] = campaign with
            {
                UpdatedAtUtc = now,
            };

            _store.PersistLocked();
            return goal;
        }
    }

    public ResolutionReportApprovalProjection ApproveResolutionReport(
        HubUserDto user,
        CampaignWorkspaceProjection workspace,
        ResolutionReportApprovalRequest request)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentNullException.ThrowIfNull(workspace);
        ArgumentNullException.ThrowIfNull(request);

        string normalizedRunId = AccountService.NormalizeOptional(request.RunId)
            ?? workspace.Runs.FirstOrDefault()?.RunId
            ?? throw new InvalidOperationException($"{workspace.CampaignName} does not have a governed run to close out.");
        string normalizedSummary = AccountService.NormalizeOptional(request.Summary)
            ?? throw new ArgumentException("resolution-report approval summary is required.", nameof(request));
        string normalizedWorldTickSummary = AccountService.NormalizeOptional(request.WorldTickSummary)
            ?? throw new ArgumentException("world-tick summary is required.", nameof(request));
        string normalizedConsequenceSummary = AccountService.NormalizeOptional(request.ConsequenceSummary)
            ?? throw new ArgumentException("consequence summary is required.", nameof(request));
        string normalizedNewsTitle = AccountService.NormalizeOptional(request.NewsTitle)
            ?? throw new ArgumentException("news title is required.", nameof(request));
        string normalizedNewsSummary = AccountService.NormalizeOptional(request.NewsSummary)
            ?? throw new ArgumentException("news summary is required.", nameof(request));
        string normalizedNewsSource = AccountService.NormalizeOptional(request.NewsSource) ?? "BLACK LEDGER";
        string normalizedNewsUrl = AccountService.NormalizeOptional(request.NewsUrl)
            ?? $"https://example.invalid/chummer/world-tick/{workspace.CampaignId}/{normalizedRunId}";
        string? normalizedNextSafeAction = AccountService.NormalizeOptional(request.NextSafeAction);
        string? normalizedNote = AccountService.NormalizeOptional(request.Note);

        lock (_store.Gate)
        {
            if (!_store.RunsById.TryGetValue(normalizedRunId, out var storedRun)
                || !string.Equals(storedRun.CampaignId, workspace.CampaignId, StringComparison.OrdinalIgnoreCase))
            {
                throw new KeyNotFoundException($"Unknown run {normalizedRunId} for workspace {workspace.WorkspaceId}.");
            }

            if (!_store.CampaignSpinesById.TryGetValue(workspace.CampaignId, out var campaign))
            {
                throw new KeyNotFoundException($"Unknown campaign: {workspace.CampaignId}");
            }

            DateTimeOffset now = DateTimeOffset.UtcNow;
            string nextSafeAction = normalizedNextSafeAction
                ?? "Review the first governed WorldTick and player-safe news item on /account/work before reopening the shared runboard.";
            string worldTickId = StableId("world-tick", $"{workspace.WorkspaceId}:{storedRun.RunId}");
            string newsId = StableId("player-safe-news", $"{workspace.WorkspaceId}:{storedRun.RunId}");
            string approvalId = StableId("resolution-report-approval", $"{workspace.WorkspaceId}:{storedRun.RunId}");
            string worldResolutionReportId = StableId("resolution-report", $"{workspace.WorkspaceId}:{storedRun.RunId}");
            string worldFrameId = StableId("world-frame", workspace.CampaignId);
            string shadowfeedBulletinId = StableId("shadowfeed-bulletin", $"{workspace.WorkspaceId}:{storedRun.RunId}");
            string consequenceBridgeId = StableId("resolution-consequence-bridge", $"{workspace.WorkspaceId}:{storedRun.RunId}");
            string approvalReceiptRef = $"campaign-spine:resolution-report-approval/{approvalId}";
            string worldTickReceiptRef = $"campaign-spine:world-tick/{worldTickId}";
            string shadowfeedBulletinReceiptRef = $"campaign-spine:shadowfeed-bulletin/{shadowfeedBulletinId}";
            string consequenceBridgeReceiptRef = $"campaign-spine:resolution-consequence-bridge/{consequenceBridgeId}";

            var worldResolutionReport = new Chummer.World.Contracts.ResolutionReport(
                ResolutionReportId: worldResolutionReportId,
                RunId: storedRun.RunId,
                Summary: normalizedSummary,
                ConsequenceMarkers: FinalizeLines([normalizedConsequenceSummary]),
                ResolvedAtUtc: now,
                ApprovalReceiptRef: approvalReceiptRef,
                WorldFrameId: worldFrameId);

            var worldTickContract = new Chummer.World.Contracts.WorldTick(
                WorldTickId: worldTickId,
                WorldFrameId: worldFrameId,
                Summary: normalizedWorldTickSummary,
                ConsequenceMarkers: worldResolutionReport.ConsequenceMarkers,
                ReceiptRef: worldTickReceiptRef,
                IssuedAtUtc: now);

            var shadowfeedBulletin = new Chummer.World.Contracts.ShadowfeedBulletin(
                BulletinId: shadowfeedBulletinId,
                WorldTickId: worldTickContract.WorldTickId,
                Audience: "players",
                Summary: normalizedNewsSummary,
                TopicTags: FinalizeLines(["player-safe-preview", "campaign-closeout"]),
                FactionTags: Array.Empty<string>(),
                ReceiptRef: shadowfeedBulletinReceiptRef);

            var consequenceBridge = new Chummer.World.Contracts.ResolutionConsequenceBridge(
                BridgeId: consequenceBridgeId,
                ResolutionReportId: worldResolutionReport.ResolutionReportId,
                WorldTickId: worldTickContract.WorldTickId,
                BulletinId: shadowfeedBulletin.BulletinId,
                Summary: normalizedConsequenceSummary,
                ReceiptRef: consequenceBridgeReceiptRef);

            var worldTick = new WorldTickProjection(
                WorldTickId: worldTickId,
                WorkspaceId: workspace.WorkspaceId,
                CampaignId: workspace.CampaignId,
                RunId: storedRun.RunId,
                RunTitle: storedRun.Title,
                Summary: normalizedWorldTickSummary,
                ConsequenceSummary: normalizedConsequenceSummary,
                EvidenceLines: FinalizeLines(
                [
                    normalizedWorldTickSummary,
                    $"Source kind: {WorldTickSourceKind}.",
                    $"GM-approved closeout anchors the first BLACK LEDGER tick for {storedRun.Title}.",
                    $"World frame: {worldFrameId}.",
                    $"World receipt: {worldTickContract.ReceiptRef}.",
                    $"Shadowfeed bulletin: {shadowfeedBulletin.BulletinId}.",
                    $"Consequence proof: {normalizedConsequenceSummary}",
                    $"Next safe action: {nextSafeAction}",
                    normalizedNote is null ? string.Empty : $"Operator note: {normalizedNote}"
                ]),
                UpdatedByUserId: user.UserId,
                UpdatedAtUtc: now,
                WorldFrameId: worldFrameId,
                WorldReceiptRef: worldTickContract.ReceiptRef,
                ShadowfeedBulletinId: shadowfeedBulletin.BulletinId,
                ShadowfeedBulletinReceiptRef: shadowfeedBulletin.ReceiptRef);

            var playerSafeNews = new PlayerSafeNewsProjection(
                NewsId: newsId,
                WorkspaceId: workspace.WorkspaceId,
                CampaignId: workspace.CampaignId,
                WorldTickId: worldTickId,
                Title: normalizedNewsTitle,
                Source: normalizedNewsSource,
                Summary: normalizedNewsSummary,
                Url: normalizedNewsUrl,
                SpoilerPolicy: "player_safe_preview_only",
                PublicationSummary: "Player-safe news stays previewable for runners without becoming world state.",
                EvidenceLines: FinalizeLines(
                [
                    $"{normalizedNewsTitle}: {normalizedNewsSummary}",
                    $"Source kind: {PlayerSafeNewsSourceKind}.",
                    $"Origin: {normalizedNewsSource}.",
                    "Spoiler policy: player-safe preview only; rendered news is not world state.",
                    $"WorldTick anchor: {worldTickId}.",
                    $"Shadowfeed bulletin: {shadowfeedBulletin.BulletinId}.",
                    $"Shadowfeed receipt: {shadowfeedBulletin.ReceiptRef}.",
                    $"Next safe action: {nextSafeAction}",
                    normalizedNote is null ? string.Empty : $"Operator note: {normalizedNote}"
                ]),
                UpdatedByUserId: user.UserId,
                UpdatedAtUtc: now,
                BulletinId: shadowfeedBulletin.BulletinId,
                BulletinReceiptRef: shadowfeedBulletin.ReceiptRef);

            var approval = new ResolutionReportApprovalProjection(
                ApprovalId: approvalId,
                WorkspaceId: workspace.WorkspaceId,
                CampaignId: workspace.CampaignId,
                RunId: storedRun.RunId,
                RunTitle: storedRun.Title,
                Summary: normalizedSummary,
                NextSafeAction: nextSafeAction,
                WorldTickId: worldTickId,
                NewsId: newsId,
                EvidenceLines: FinalizeLines(
                [
                    normalizedSummary,
                    $"Source kind: {ResolutionReportApprovalSourceKind}.",
                    $"Resolution report: {worldResolutionReport.ResolutionReportId}.",
                    $"WorldTick: {normalizedWorldTickSummary}",
                    $"Player-safe news: {normalizedNewsTitle}",
                    $"Consequence bridge: {consequenceBridge.BridgeId}.",
                    $"Approval receipt: {approvalReceiptRef}.",
                    $"Next safe action: {nextSafeAction}",
                    normalizedNote is null ? string.Empty : $"Operator note: {normalizedNote}"
                ]),
                UpdatedByUserId: user.UserId,
                UpdatedAtUtc: now,
                WorldResolutionReportId: worldResolutionReport.ResolutionReportId,
                WorldFrameId: worldFrameId,
                ShadowfeedBulletinId: shadowfeedBulletin.BulletinId,
                ResolutionConsequenceBridgeId: consequenceBridge.BridgeId,
                ApprovalReceiptRef: approvalReceiptRef);

            RunboardContinuityProjection? updatedContinuity = storedRun.RunboardContinuity is null
                ? null
                : storedRun.RunboardContinuity with
                {
                    ResolutionReportDraft = storedRun.RunboardContinuity.ResolutionReportDraft with
                    {
                        Status = "approved",
                        Summary = normalizedSummary,
                        Notes = FinalizeLines(
                            storedRun.RunboardContinuity.ResolutionReportDraft.Notes.Concat(
                            [
                                normalizedWorldTickSummary,
                                normalizedNewsSummary,
                                normalizedNote is null ? string.Empty : $"Operator note: {normalizedNote}"
                            ])),
                        NextSafeAction = nextSafeAction,
                        EvidenceLines = FinalizeLines(
                            storedRun.RunboardContinuity.ResolutionReportDraft.EvidenceLines.Concat(
                            [
                                $"ResolutionReport approval: {normalizedSummary}",
                                $"Source kind: {ResolutionReportApprovalSourceKind}.",
                                $"First WorldTick: {normalizedWorldTickSummary}",
                                $"Player-safe news: {normalizedNewsTitle}",
                                $"Next safe action: {nextSafeAction}"
                            ])),
                        UpdatedAtUtc = now
                    },
                    Summary = $"{storedRun.Title} keeps an approved ResolutionReport, first WorldTick, and player-safe news item on the reviewed hub path.",
                    EvidenceLines = FinalizeLines(
                        storedRun.RunboardContinuity.EvidenceLines.Concat(
                        [
                            $"ResolutionReport approval: {normalizedSummary}",
                            $"WorldTick: {normalizedWorldTickSummary}",
                            $"Player-safe news: {normalizedNewsTitle}",
                            "Boundary: player-safe news previews stay separate from world state.",
                            $"Next safe action: {nextSafeAction}"
                        ])),
                    UpdatedByUserId = user.UserId,
                    UpdatedAtUtc = now
                };

            CampaignConsequenceProjection consequence = BuildGovernedCampaignConsequenceProjection(
                workspace,
                "heat",
                "escalated",
                normalizedConsequenceSummary,
                "Review BLACK LEDGER fallout",
                null,
                normalizedNote,
                now);

            _store.RunsById[storedRun.RunId] = storedRun with
            {
                UpdatedAtUtc = now,
                RunboardContinuity = updatedContinuity
            };
            _store.CampaignSpinesById[campaign.CampaignId] = campaign with
            {
                ActiveRunId = storedRun.RunId,
                UpdatedAtUtc = now,
                Consequences = UpsertGovernedCampaignConsequence(campaign.Consequences, consequence),
            };

            _store.ResolutionReportApprovals.RemoveAll(item => string.Equals(item.ApprovalId, approval.ApprovalId, StringComparison.OrdinalIgnoreCase));
            _store.ResolutionReportApprovals.Add(approval);
            _store.ResolutionReportApprovals.Sort(static (left, right) => right.UpdatedAtUtc.CompareTo(left.UpdatedAtUtc));
            if (_store.ResolutionReportApprovals.Count > 64)
            {
                _store.ResolutionReportApprovals.RemoveRange(64, _store.ResolutionReportApprovals.Count - 64);
            }

            _store.WorldTicks.RemoveAll(item => string.Equals(item.WorldTickId, worldTick.WorldTickId, StringComparison.OrdinalIgnoreCase));
            _store.WorldTicks.Add(worldTick);
            _store.WorldTicks.Sort(static (left, right) => right.UpdatedAtUtc.CompareTo(left.UpdatedAtUtc));
            if (_store.WorldTicks.Count > 64)
            {
                _store.WorldTicks.RemoveRange(64, _store.WorldTicks.Count - 64);
            }

            _store.PlayerSafeNews.RemoveAll(item => string.Equals(item.NewsId, playerSafeNews.NewsId, StringComparison.OrdinalIgnoreCase));
            _store.PlayerSafeNews.Add(playerSafeNews);
            _store.PlayerSafeNews.Sort(static (left, right) => right.UpdatedAtUtc.CompareTo(left.UpdatedAtUtc));
            if (_store.PlayerSafeNews.Count > 64)
            {
                _store.PlayerSafeNews.RemoveRange(64, _store.PlayerSafeNews.Count - 64);
            }

            _store.PersistLocked();
            return approval;
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

    public DossierMovementPlannerProjection? GetDossierMovementPlan(HubUserDto user, string workspaceId, InstallLinkingSummaryDto? installLinking = null)
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
                .Select(group => new DossierMovementTargetGroupProjection(
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
                        .ToArray(),
                    CampaignOptions: _store.CampaignsById.Values
                        .Where(item => string.Equals(item.GroupId, group.GroupId, StringComparison.OrdinalIgnoreCase))
                        .OrderBy(item => item.CreatedAtUtc)
                        .ThenBy(item => item.CampaignId, StringComparer.OrdinalIgnoreCase)
                        .Select(item => new DossierMovementTargetCampaignProjection(
                            CampaignId: item.CampaignId,
                            CampaignName: item.Title,
                            Status: item.Status,
                            Suggested: string.Equals(item.Status, CampaignStatuses.Active, StringComparison.OrdinalIgnoreCase),
                            EventOptions: BuildDossierMovementEventOptionsLocked(item)))
                        .ToArray()))
                .ToArray();

            return new DossierMovementPlannerProjection(
                WorkspaceId: workspace.WorkspaceId,
                SourceGroupId: sourceGroup.GroupId,
                SourceGroupName: sourceGroup.Name,
                SourceCampaignId: sourceCampaign.CampaignId,
                SourceCampaignName: sourceCampaign.Name,
                Summary: "Move a governed dossier between rosters, campaigns, runs, scenes, and owners without losing the same dossier id or explicit continuity receipts.",
                DossierOptions: dossierOptions,
                TargetGroups: targetGroups);
        }
    }

    public IReadOnlyList<DossierMovementReceiptProjection> GetDossierMovements(HubUserDto user, string workspaceId, InstallLinkingSummaryDto? installLinking = null)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentException.ThrowIfNullOrWhiteSpace(workspaceId);

        CampaignWorkspaceProjection? workspace = GetWorkspace(user, workspaceId, installLinking);
        if (workspace is null)
        {
            return Array.Empty<DossierMovementReceiptProjection>();
        }

        lock (_store.Gate)
        {
            return _store.DossierMovements
                .Where(item =>
                    string.Equals(item.SourceCampaignId, workspace.CampaignId, StringComparison.OrdinalIgnoreCase)
                    || string.Equals(item.TargetCampaignId, workspace.CampaignId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(item => item.MovedAtUtc)
                .ThenBy(item => item.MovementId, StringComparer.OrdinalIgnoreCase)
                .ToArray();
        }
    }

    public DossierMovementReceiptProjection MoveDossier(HubUserDto requester, DossierMovementRequest request)
    {
        ArgumentNullException.ThrowIfNull(requester);
        ArgumentNullException.ThrowIfNull(request);

        var command = new DossierMovementCommand(
            DossierId: ResolveRosterTransferRequestIdentity(request.DossierId, "dossier"),
            TargetGroupId: ResolveRosterTransferRequestIdentity(request.TargetGroupId, "target group"),
            TargetCampaignId: AccountService.NormalizeOptional(request.TargetCampaignId),
            TargetCampaignTitle: AccountService.NormalizeOptional(request.TargetCampaignTitle),
            TargetRunId: AccountService.NormalizeOptional(request.TargetRunId),
            TargetRunTitle: AccountService.NormalizeOptional(request.TargetRunTitle),
            TargetSceneId: AccountService.NormalizeOptional(request.TargetSceneId),
            TargetSceneTitle: AccountService.NormalizeOptional(request.TargetSceneTitle),
            TargetOwnerUserId: AccountService.NormalizeOptional(request.TargetOwnerUserId),
            Note: AccountService.NormalizeOptional(request.Note));

        lock (_store.Gate)
        {
            MovementResolution movement = ExecuteDossierMovementLocked(requester, command);
            bool groupChanged = !string.Equals(movement.SourceGroup.GroupId, movement.TargetGroup.GroupId, StringComparison.OrdinalIgnoreCase);
            bool campaignChanged = !string.Equals(movement.SourceCampaign.CampaignId, movement.TargetCampaign.CampaignId, StringComparison.OrdinalIgnoreCase);
            bool ownershipChanged = !string.Equals(movement.PreviousOwnerUserId, movement.CurrentOwnerUserId, StringComparison.OrdinalIgnoreCase);
            bool eventChanged = !string.Equals(movement.SourceRun?.RunId, movement.TargetEvent.Run.RunId, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(movement.SourceScene?.SceneId, movement.TargetEvent.Scene.SceneId, StringComparison.OrdinalIgnoreCase);
            string note = string.IsNullOrWhiteSpace(command.Note) ? string.Empty : $" Note: {command.Note}";

            List<CampaignConsequenceReceipt> movementReceipts =
            [
                CampaignConsequence(
                    ReceiptId: movement.SourceGroup.GroupId,
                    SourceKind: "source_group",
                    Summary: movement.SourceGroup.Name),
                CampaignConsequence(
                    ReceiptId: movement.TargetGroup.GroupId,
                    SourceKind: "target_group",
                    Summary: movement.TargetGroup.Name),
                CampaignConsequence(
                    ReceiptId: movement.SourceCampaign.CampaignId,
                    SourceKind: "source_campaign",
                    Summary: movement.SourceCampaign.Name),
                CampaignConsequence(
                    ReceiptId: movement.TargetCampaign.CampaignId,
                    SourceKind: "target_campaign",
                    Summary: movement.TargetCampaign.Title),
                CampaignConsequence(
                    ReceiptId: movement.TargetEvent.Run.RunId,
                    SourceKind: "target_run",
                    Summary: movement.TargetEvent.Run.Title),
                CampaignConsequence(
                    ReceiptId: movement.TargetEvent.Scene.SceneId,
                    SourceKind: "target_scene",
                    Summary: movement.TargetEvent.Scene.Title),
                CampaignConsequence(
                    ReceiptId: movement.Continuity.SnapshotId,
                    SourceKind: "continuity",
                    Summary: movement.Continuity.Summary)
            ];

            var receipt = new DossierMovementReceiptProjection(
                MovementId: StableId("movement", $"{movement.TransferredDossier.DossierId}:{movement.TargetCampaign.CampaignId}:{movement.TargetEvent.Run.RunId}:{movement.TargetEvent.Scene.SceneId}:{movement.Now.ToUnixTimeSeconds()}"),
                DossierId: movement.TransferredDossier.DossierId,
                RunnerHandle: movement.TransferredDossier.RunnerHandle,
                PreviousOwnerUserId: movement.PreviousOwnerUserId,
                CurrentOwnerUserId: movement.CurrentOwnerUserId,
                SourceGroupId: movement.SourceGroup.GroupId,
                SourceGroupName: movement.SourceGroup.Name,
                SourceCampaignId: movement.SourceCampaign.CampaignId,
                SourceCampaignName: movement.SourceCampaign.Name,
                SourceRunId: movement.SourceRun?.RunId,
                SourceRunTitle: movement.SourceRun?.Title,
                SourceSceneId: movement.SourceScene?.SceneId,
                SourceSceneTitle: movement.SourceScene?.Title,
                TargetGroupId: movement.TargetGroup.GroupId,
                TargetGroupName: movement.TargetGroup.Name,
                TargetCampaignId: movement.TargetCampaign.CampaignId,
                TargetCampaignName: movement.TargetCampaign.Title,
                TargetRunId: movement.TargetEvent.Run.RunId,
                TargetRunTitle: movement.TargetEvent.Run.Title,
                TargetSceneId: movement.TargetEvent.Scene.SceneId,
                TargetSceneTitle: movement.TargetEvent.Scene.Title,
                OwnershipChanged: ownershipChanged,
                CampaignChanged: campaignChanged,
                GroupChanged: groupChanged,
                EventChanged: eventChanged,
                InitiatedByUserId: requester.UserId,
                Summary: ownershipChanged
                    ? $"{movement.TransferredDossier.DisplayName} moved into {movement.TargetCampaign.Title} / {movement.TargetEvent.Run.Title} / {movement.TargetEvent.Scene.Title}, and ownership transferred to {movement.CurrentOwner.DisplayName}.{note}"
                    : $"{movement.TransferredDossier.DisplayName} moved into {movement.TargetCampaign.Title} / {movement.TargetEvent.Run.Title} / {movement.TargetEvent.Scene.Title} without losing governed ownership.{note}",
                AuditLines: FinalizeLines(
                [
                    $"{requester.DisplayName} initiated the dossier move from {movement.SourceGroup.Name} to {movement.TargetGroup.Name}.",
                    $"Campaign return now pins {movement.TransferredDossier.DisplayName} to {movement.TargetCampaign.Title}.",
                    $"Run continuity now lands on {movement.TargetEvent.Run.Title}.",
                    $"Scene continuity now lands on {movement.TargetEvent.Scene.Title}.",
                    ownershipChanged
                        ? $"Ownership moved from {movement.PreviousOwner?.DisplayName ?? movement.PreviousOwnerUserId} to {movement.CurrentOwner.DisplayName} with the same dossier id preserved."
                        : $"Ownership stayed with {movement.CurrentOwner.DisplayName} while campaign continuity moved.",
                    command.Note is null ? string.Empty : $"Operator note: {command.Note}"
                ]),
                Receipts: movementReceipts,
                MovedAtUtc: movement.Now,
                TransferReceipt: movement.TransferReceipt,
                Envelope: ReceiptEnvelopeFactory.Runtime(
                    receiptKind: "dossier_movement",
                    ownerScope: "community.campaign_spine",
                    exposureClass: ReceiptExposureClasses.SignedIn,
                    evidenceRef: movement.TransferredDossier.DossierId,
                    reviewState: "moved"));
            _store.DossierMovements.RemoveAll(item => string.Equals(item.MovementId, receipt.MovementId, StringComparison.OrdinalIgnoreCase));
            _store.DossierMovements.Add(receipt);
            _store.PersistLocked();
            return receipt;
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
            var sourceRun = string.IsNullOrWhiteSpace(dossier.CurrentRunId)
                ? null
                : _store.RunsById.GetValueOrDefault(dossier.CurrentRunId);
            var sourceScene = sourceRun?.Scenes.FirstOrDefault(item => string.Equals(item.SceneId, dossier.CurrentSceneId, StringComparison.OrdinalIgnoreCase));

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

            List<CampaignConsequenceReceipt> transferReceipts =
            [
                CampaignConsequence(
                    ReceiptId: sourceGroup.GroupId,
                    SourceKind: "source_group",
                    Summary: sourceGroup.Name),
                CampaignConsequence(
                    ReceiptId: targetGroup.GroupId,
                    SourceKind: "target_group",
                    Summary: targetGroup.Name),
                CampaignConsequence(
                    ReceiptId: sourceCampaign.CampaignId,
                    SourceKind: "source_campaign",
                    Summary: sourceCampaign.Name),
                CampaignConsequence(
                    ReceiptId: targetCampaign.CampaignId,
                    SourceKind: "target_campaign",
                    Summary: targetCampaign.Title),
                CampaignConsequence(
                    ReceiptId: continuity.SnapshotId,
                    SourceKind: "continuity",
                    Summary: continuity.Summary)
            ];
            if (sourceRun is not null)
            {
                transferReceipts.Add(CampaignConsequence(
                    ReceiptId: sourceRun.RunId,
                    SourceKind: "target_run",
                    Summary: sourceRun.Title));
            }
            if (sourceScene is not null)
            {
                transferReceipts.Add(CampaignConsequence(
                    ReceiptId: sourceScene.SceneId,
                    SourceKind: "target_scene",
                    Summary: sourceScene.Title));
            }

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
                Receipts: transferReceipts,
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

            var targetRun = _store.RunsById.GetValueOrDefault(targetRunId);
            var targetScene = targetRun?.Scenes.FirstOrDefault(item => string.Equals(item.SceneId, targetSceneId, StringComparison.OrdinalIgnoreCase));
            string targetRunTitle = targetRun?.Title ?? $"{targetCampaign.Title} kickoff";
            string targetSceneTitle = targetScene?.Title ?? "Campaign brief";
            bool movementEventChanged = !string.Equals(sourceRun?.RunId, targetRunId, StringComparison.OrdinalIgnoreCase)
                || !string.Equals(sourceScene?.SceneId, targetSceneId, StringComparison.OrdinalIgnoreCase);
            var movementReceipt = new DossierMovementReceiptProjection(
                MovementId: StableId("movement", receipt.TransferId),
                DossierId: transferredDossier.DossierId,
                RunnerHandle: transferredDossier.RunnerHandle,
                PreviousOwnerUserId: previousOwnerUserId,
                CurrentOwnerUserId: currentOwnerUserId,
                SourceGroupId: sourceGroup.GroupId,
                SourceGroupName: sourceGroup.Name,
                SourceCampaignId: sourceCampaign.CampaignId,
                SourceCampaignName: sourceCampaign.Name,
                SourceRunId: sourceRun?.RunId,
                SourceRunTitle: sourceRun?.Title,
                SourceSceneId: sourceScene?.SceneId,
                SourceSceneTitle: sourceScene?.Title,
                TargetGroupId: targetGroup.GroupId,
                TargetGroupName: targetGroup.Name,
                TargetCampaignId: targetCampaign.CampaignId,
                TargetCampaignName: targetCampaign.Title,
                TargetRunId: targetRunId,
                TargetRunTitle: targetRunTitle,
                TargetSceneId: targetSceneId,
                TargetSceneTitle: targetSceneTitle,
                OwnershipChanged: !string.Equals(previousOwnerUserId, currentOwnerUserId, StringComparison.OrdinalIgnoreCase),
                CampaignChanged: !string.Equals(sourceCampaign.CampaignId, targetCampaign.CampaignId, StringComparison.OrdinalIgnoreCase),
                GroupChanged: !string.Equals(sourceGroup.GroupId, targetGroup.GroupId, StringComparison.OrdinalIgnoreCase),
                EventChanged: movementEventChanged,
                InitiatedByUserId: requester.UserId,
                Summary: receipt.Summary,
                AuditLines: receipt.AuditLines,
                Receipts: receipt.Receipts,
                MovedAtUtc: now,
                TransferReceipt: receipt,
                Envelope: ReceiptEnvelopeFactory.Runtime(
                    receiptKind: "dossier_movement",
                    ownerScope: "community.campaign_spine",
                    exposureClass: ReceiptExposureClasses.SignedIn,
                    evidenceRef: transferredDossier.DossierId,
                    reviewState: "moved"));
            _store.DossierMovements.RemoveAll(item => string.Equals(item.MovementId, movementReceipt.MovementId, StringComparison.OrdinalIgnoreCase));
            _store.DossierMovements.Add(movementReceipt);

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
                .OrderByDescending(static cue => ResolveReadinessAttentionPriority(cue.Severity))
                .ThenBy(static cue => cue.Title, StringComparer.OrdinalIgnoreCase)
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

    private IReadOnlyList<DossierMovementEventProjection> BuildDossierMovementEventOptionsLocked(BoostCampaignDto campaign)
    {
        RunProjection? run = _store.RunsById.Values
            .Where(item => string.Equals(item.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(item => item.UpdatedAtUtc)
            .ThenBy(item => item.RunId, StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault();
        SceneProjection? scene = run?.Scenes.FirstOrDefault(item => string.Equals(item.SceneId, run.ActiveSceneId, StringComparison.OrdinalIgnoreCase))
            ?? run?.Scenes.FirstOrDefault();

        if (run is null)
        {
            return
            [
                new DossierMovementEventProjection(
                    RunId: StableId("run", campaign.CampaignId),
                    RunTitle: $"{campaign.Title} kickoff",
                    RunStatus: RunStatuses.Active,
                    SceneId: StableId("scene", campaign.CampaignId),
                    SceneTitle: "Campaign brief",
                    SceneStatus: "active",
                    SceneRevision: "r1",
                    Active: true)
            ];
        }

        scene ??= new SceneProjection(
            SceneId: StableId("scene", campaign.CampaignId),
            RunId: run.RunId,
            Title: "Campaign brief",
            Revision: "r1",
            Status: "active",
            Summary: "Shared entry scene for planning, continuity, and handoff.",
            UpdatedAtUtc: run.UpdatedAtUtc);
        return
        [
            new DossierMovementEventProjection(
                RunId: run.RunId,
                RunTitle: run.Title,
                RunStatus: run.Status,
                SceneId: scene.SceneId,
                SceneTitle: scene.Title,
                SceneStatus: scene.Status,
                SceneRevision: scene.Revision,
                Active: string.Equals(run.ActiveSceneId, scene.SceneId, StringComparison.OrdinalIgnoreCase))
        ];
    }

    private MovementResolution ExecuteDossierMovementLocked(HubUserDto requester, DossierMovementCommand command)
    {
        DateTimeOffset now = DateTimeOffset.UtcNow;
        var dossier = _store.DossiersById.GetValueOrDefault(command.DossierId)
            ?? throw new KeyNotFoundException($"Unknown dossier: {command.DossierId}");
        var sourceCampaign = _store.CampaignSpinesById.GetValueOrDefault(dossier.CampaignId ?? string.Empty)
            ?? throw new KeyNotFoundException($"Unknown source campaign: {dossier.CampaignId}");
        var sourceGroup = _store.GroupsById.GetValueOrDefault(sourceCampaign.GroupId)
            ?? throw new KeyNotFoundException($"Unknown source group: {sourceCampaign.GroupId}");
        if (!CanManageRosterGroup(sourceGroup, requester.UserId))
        {
            throw new CommunityAccessDeniedException("requester must be an owner, manager, admin, or gm on the source group to move dossier state.");
        }

        var targetGroup = _store.GroupsById.GetValueOrDefault(command.TargetGroupId)
            ?? throw new KeyNotFoundException($"Unknown target group: {command.TargetGroupId}");
        if (!CanManageRosterGroup(targetGroup, requester.UserId))
        {
            throw new CommunityAccessDeniedException("requester must be an owner, manager, admin, or gm on the target group to move dossier state.");
        }

        string previousOwnerUserId = dossier.OwnerUserId;
        var previousOwner = _store.UsersById.GetValueOrDefault(previousOwnerUserId);
        string currentOwnerUserId = command.TargetOwnerUserId ?? dossier.OwnerUserId;
        var currentOwner = _store.UsersById.GetValueOrDefault(currentOwnerUserId)
            ?? throw new KeyNotFoundException($"Unknown target owner: {currentOwnerUserId}");
        var targetCampaign = ResolveOrCreateTransferCampaignLocked(targetGroup, command.TargetCampaignId, command.TargetCampaignTitle, now);
        if (!string.Equals(previousOwnerUserId, currentOwnerUserId, StringComparison.OrdinalIgnoreCase)
            && _store.DossiersById.Values.Any(item =>
                !string.Equals(item.DossierId, dossier.DossierId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.OwnerUserId, currentOwnerUserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.CampaignId, targetCampaign.CampaignId, StringComparison.OrdinalIgnoreCase)))
        {
            throw new InvalidOperationException("target owner already has a governed dossier in the selected campaign; transfer would overwrite assignment truth.");
        }

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

        var sourceCrew = _store.CrewsById.GetValueOrDefault(dossier.CrewId ?? string.Empty);
        var sourceRun = string.IsNullOrWhiteSpace(dossier.CurrentRunId)
            ? null
            : _store.RunsById.GetValueOrDefault(dossier.CurrentRunId);
        var sourceScene = sourceRun?.Scenes.FirstOrDefault(item => string.Equals(item.SceneId, dossier.CurrentSceneId, StringComparison.OrdinalIgnoreCase));
        MovementTargetEvent targetEvent = ResolveOrCreateMovementTargetEventLocked(
            targetCampaign,
            command.TargetRunId,
            command.TargetRunTitle,
            command.TargetSceneId,
            command.TargetSceneTitle,
            now);

        var continuity = new ContinuitySnapshotRef(
            SnapshotId: StableId("snapshot", $"{dossier.DossierId}:{targetCampaign.CampaignId}:{targetEvent.Run.RunId}:{targetEvent.Scene.SceneId}:{now.ToUnixTimeSeconds()}"),
            CapturedAtUtc: now,
            Summary: $"{dossier.DisplayName} now returns through {targetCampaign.Title} / {targetEvent.Run.Title} / {targetEvent.Scene.Title}.",
            RestoreState: "dossier_moved",
            SessionId: targetEvent.Run.RunId,
            SceneId: targetEvent.Scene.SceneId,
            RecapArtifactId: StableId("recap", targetCampaign.CampaignId));
        string targetCrewId = ResolveCrewIdLocked(targetCampaign.CampaignId);
        var transferredDossier = dossier with
        {
            OwnerUserId = currentOwnerUserId,
            CrewId = targetCrewId,
            CampaignId = targetCampaign.CampaignId,
            CurrentRunId = targetEvent.Run.RunId,
            CurrentSceneId = targetEvent.Scene.SceneId,
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

        if (previousOwner is not null)
        {
            EnsureCampaignsLocked(previousOwner, now);
        }

        if (!string.Equals(previousOwnerUserId, currentOwnerUserId, StringComparison.OrdinalIgnoreCase))
        {
            EnsureCampaignsLocked(currentOwner, now);
        }

        targetEvent = ResolveOrCreateMovementTargetEventLocked(
            targetCampaign,
            command.TargetRunId,
            command.TargetRunTitle,
            command.TargetSceneId,
            command.TargetSceneTitle,
            now);
        bool eventChanged = !string.Equals(sourceRun?.RunId, targetEvent.Run.RunId, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(sourceScene?.SceneId, targetEvent.Scene.SceneId, StringComparison.OrdinalIgnoreCase);
        transferredDossier = _store.DossiersById[transferredDossier.DossierId] with
        {
            CurrentRunId = targetEvent.Run.RunId,
            CurrentSceneId = targetEvent.Scene.SceneId,
            LatestContinuity = continuity with
            {
                SessionId = targetEvent.Run.RunId,
                SceneId = targetEvent.Scene.SceneId
            },
            UpdatedAtUtc = now
        };
        _store.DossiersById[transferredDossier.DossierId] = transferredDossier;

        List<CampaignConsequenceReceipt> transferReceipts =
        [
            CampaignConsequence(
                ReceiptId: sourceGroup.GroupId,
                SourceKind: "source_group",
                Summary: sourceGroup.Name),
            CampaignConsequence(
                ReceiptId: targetGroup.GroupId,
                SourceKind: "target_group",
                Summary: targetGroup.Name),
            CampaignConsequence(
                ReceiptId: sourceCampaign.CampaignId,
                SourceKind: "source_campaign",
                Summary: sourceCampaign.Name),
            CampaignConsequence(
                ReceiptId: targetCampaign.CampaignId,
                SourceKind: "target_campaign",
                Summary: targetCampaign.Title),
            CampaignConsequence(
                ReceiptId: targetEvent.Run.RunId,
                SourceKind: "target_run",
                Summary: targetEvent.Run.Title),
            CampaignConsequence(
                ReceiptId: targetEvent.Scene.SceneId,
                SourceKind: "target_scene",
                Summary: targetEvent.Scene.Title),
            CampaignConsequence(
                ReceiptId: continuity.SnapshotId,
                SourceKind: "continuity",
                Summary: continuity.Summary)
        ];
        string note = string.IsNullOrWhiteSpace(command.Note) ? string.Empty : $" Note: {command.Note}";
        var transferReceipt = new RosterTransferProjection(
            TransferId: StableId("transfer", $"{transferredDossier.DossierId}:{targetCampaign.CampaignId}:{targetEvent.Run.RunId}:{targetEvent.Scene.SceneId}:{now.ToUnixTimeSeconds()}"),
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
            TargetCrewName: $"{targetGroup.Name} crew",
            InitiatedByUserId: requester.UserId,
            Summary: string.Equals(previousOwnerUserId, currentOwnerUserId, StringComparison.OrdinalIgnoreCase)
                ? $"{transferredDossier.DisplayName} moved from {sourceCampaign.Name} into {targetCampaign.Title} / {targetEvent.Run.Title} / {targetEvent.Scene.Title} without losing governed ownership.{note}"
                : $"{transferredDossier.DisplayName} moved from {sourceCampaign.Name} into {targetCampaign.Title} / {targetEvent.Run.Title} / {targetEvent.Scene.Title}, and ownership transferred to {currentOwner.DisplayName}.{note}",
            AuditLines:
            [
                $"{requester.DisplayName} initiated the move from {sourceGroup.Name} to {targetGroup.Name}.",
                $"Campaign return now pins {transferredDossier.DisplayName} to {targetCampaign.Title}.",
                $"Run continuity now lands on {targetEvent.Run.Title}.",
                $"Scene continuity now lands on {targetEvent.Scene.Title}.",
                string.Equals(previousOwnerUserId, currentOwnerUserId, StringComparison.OrdinalIgnoreCase)
                    ? $"Ownership stayed with {currentOwner.DisplayName} while campaign, run, and scene assignment changed."
                    : $"Ownership moved from {previousOwner?.DisplayName ?? previousOwnerUserId} to {currentOwner.DisplayName} with the same dossier id preserved."
            ],
            Receipts: transferReceipts,
            TransferredAtUtc: now);
        return new MovementResolution(
            Now: now,
            SourceGroup: sourceGroup,
            TargetGroup: targetGroup,
            SourceCampaign: sourceCampaign,
            TargetCampaign: targetCampaign,
            SourceRun: sourceRun,
            SourceScene: sourceScene,
            TargetEvent: targetEvent,
            EventChanged: eventChanged,
            PreviousOwnerUserId: previousOwnerUserId,
            CurrentOwnerUserId: currentOwnerUserId,
            PreviousOwner: previousOwner,
            CurrentOwner: currentOwner,
            Continuity: continuity,
            TransferredDossier: transferredDossier,
            TransferReceipt: transferReceipt);
    }

    private MovementTargetEvent ResolveOrCreateMovementTargetEventLocked(
        BoostCampaignDto targetCampaign,
        string? targetRunId,
        string? targetRunTitle,
        string? targetSceneId,
        string? targetSceneTitle,
        DateTimeOffset now)
    {
        string runId = AccountService.NormalizeOptional(targetRunId) ?? StableId("run", targetCampaign.CampaignId);
        string sceneId = AccountService.NormalizeOptional(targetSceneId) ?? StableId("scene", targetCampaign.CampaignId);
        string runTitle = string.IsNullOrWhiteSpace(targetRunTitle) ? $"{targetCampaign.Title} kickoff" : targetRunTitle.Trim();
        string sceneTitle = string.IsNullOrWhiteSpace(targetSceneTitle) ? "Campaign brief" : targetSceneTitle.Trim();
        _store.RunsById.TryGetValue(runId, out var existingRun);
        SceneProjection? existingScene = existingRun?.Scenes.FirstOrDefault(item => string.Equals(item.SceneId, sceneId, StringComparison.OrdinalIgnoreCase));
        string objectiveId = existingRun?.Objectives.FirstOrDefault()?.ObjectiveId ?? StableId("obj", $"{targetCampaign.CampaignId}:{runId}");
        var scene = new SceneProjection(
            SceneId: sceneId,
            RunId: runId,
            Title: sceneTitle,
            Revision: existingScene?.Revision ?? "r1",
            Status: "active",
            Summary: $"{sceneTitle} keeps governed dossier continuity visible on the shared campaign plane.",
            UpdatedAtUtc: now);
        var runContinuity = existingRun?.LatestContinuity is null
            ? new ContinuitySnapshotRef(
                SnapshotId: StableId("snapshot", $"{targetCampaign.CampaignId}:{runId}"),
                CapturedAtUtc: now,
                Summary: $"{runTitle} keeps governed dossier continuity active for {targetCampaign.Title}.",
                RestoreState: "synced",
                SessionId: runId,
                SceneId: sceneId,
                RecapArtifactId: StableId("recap", targetCampaign.CampaignId))
            : existingRun.LatestContinuity with
            {
                CapturedAtUtc = now,
                Summary = $"{runTitle} keeps governed dossier continuity active for {targetCampaign.Title}.",
                RestoreState = "synced",
                SessionId = runId,
                SceneId = sceneId,
                RecapArtifactId = existingRun.LatestContinuity.RecapArtifactId ?? StableId("recap", targetCampaign.CampaignId)
            };
        var run = new RunProjection(
            RunId: runId,
            CampaignId: targetCampaign.CampaignId,
            Title: runTitle,
            Status: RunStatuses.Active,
            Summary: $"{runTitle} anchors governed dossier continuity for {targetCampaign.Title}.",
            ActiveSceneId: sceneId,
            Objectives: existingRun?.Objectives is { Count: > 0 }
                ? existingRun.Objectives
                :
                [
                    new ObjectiveProjection(
                        ObjectiveId: objectiveId,
                        Title: "Keep the crew aligned",
                        Status: "open",
                        Pressure: "medium",
                        Summary: "Use the same dossier, rule environment, and recap spine across surfaces.",
                        UpdatedAtUtc: now)
                ],
            Scenes: (existingRun?.Scenes ?? Array.Empty<SceneProjection>())
                .Where(item => !string.Equals(item.SceneId, sceneId, StringComparison.OrdinalIgnoreCase))
                .Concat([scene])
                .ToArray(),
            LatestContinuity: runContinuity,
            CreatedAtUtc: existingRun?.CreatedAtUtc ?? now,
            UpdatedAtUtc: now);
        _store.RunsById[runId] = run;

        var targetGroup = _store.GroupsById.GetValueOrDefault(targetCampaign.GroupId);
        if (_store.CampaignSpinesById.TryGetValue(targetCampaign.CampaignId, out var existingCampaign))
        {
            _store.CampaignSpinesById[targetCampaign.CampaignId] = existingCampaign with
            {
                ActiveRunId = runId,
                RunIds = existingCampaign.RunIds.Concat([runId]).Distinct(StringComparer.OrdinalIgnoreCase).ToArray(),
                LatestContinuity = existingCampaign.LatestContinuity is null
                    ? runContinuity
                    : existingCampaign.LatestContinuity with
                    {
                        CapturedAtUtc = now,
                        Summary = runContinuity.Summary,
                        RestoreState = runContinuity.RestoreState,
                        SessionId = runId,
                        SceneId = sceneId,
                        RecapArtifactId = existingCampaign.LatestContinuity.RecapArtifactId ?? runContinuity.RecapArtifactId
                    },
                UpdatedAtUtc = now
            };
        }
        else if (targetGroup is not null)
        {
            _store.CampaignSpinesById[targetCampaign.CampaignId] = new CampaignProjection(
                CampaignId: targetCampaign.CampaignId,
                GroupId: targetGroup.GroupId,
                Name: targetCampaign.Title,
                Status: CampaignStatuses.Active,
                Visibility: targetGroup.Visibility,
                Summary: "Campaign continuity, roster posture, and shared rule environment live together here.",
                RuleEnvironment: DefaultRuleEnvironment($"campaign:{targetCampaign.CampaignId}", "campaign"),
                ActiveRunId: runId,
                CrewIds: [ResolveCrewIdLocked(targetCampaign.CampaignId)],
                DossierIds: Array.Empty<string>(),
                RunIds: [runId],
                LatestContinuity: runContinuity,
                CreatedAtUtc: targetCampaign.CreatedAtUtc,
                UpdatedAtUtc: now,
                Consequences: null);
        }

        return new MovementTargetEvent(run, scene);
    }

    private sealed record DossierMovementCommand(
        string DossierId,
        string TargetGroupId,
        string? TargetCampaignId,
        string? TargetCampaignTitle,
        string? TargetRunId,
        string? TargetRunTitle,
        string? TargetSceneId,
        string? TargetSceneTitle,
        string? TargetOwnerUserId,
        string? Note);

    private sealed record MovementTargetEvent(
        RunProjection Run,
        SceneProjection Scene);

    private sealed record MovementResolution(
        DateTimeOffset Now,
        GroupDto SourceGroup,
        GroupDto TargetGroup,
        CampaignProjection SourceCampaign,
        BoostCampaignDto TargetCampaign,
        RunProjection? SourceRun,
        SceneProjection? SourceScene,
        MovementTargetEvent TargetEvent,
        bool EventChanged,
        string PreviousOwnerUserId,
        string CurrentOwnerUserId,
        HubUserDto? PreviousOwner,
        HubUserDto CurrentOwner,
        ContinuitySnapshotRef Continuity,
        RunnerDossierProjection TransferredDossier,
        RosterTransferProjection TransferReceipt);

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

            _store.CampaignSpinesById.TryGetValue(sponsorCampaign.CampaignId, out var existingCampaign);
            IReadOnlyList<CampaignConsequenceProjection> baselineConsequences = BuildCampaignConsequences(
                sponsorCampaign,
                group,
                crew,
                memberDossiers,
                run,
                continuity);
            IReadOnlyList<CampaignConsequenceProjection> mergedConsequences =
                MergeCampaignConsequencesWithReceiptCarryForward(
                    baselineConsequences,
                    existingCampaign?.Consequences);

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
                UpdatedAtUtc: existingCampaign?.UpdatedAtUtc ?? now,
                Consequences: mergedConsequences);
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
        if (activeGrants.Any(grant =>
                !string.Equals(grant.Status, InstallationGrantStates.Active, StringComparison.OrdinalIgnoreCase)
                || grant.ExpiresAtUtc <= generatedAtUtc))
        {
            conflictSummaries.Add("Entitlement replay includes stale or expired grants; relink before trusting restored access on another device.");
        }
        if (claimedInstallations.Any(installation =>
                !string.Equals(installation.Status, ClaimedInstallationStates.Active, StringComparison.OrdinalIgnoreCase)
                || generatedAtUtc - installation.UpdatedAtUtc > RestoreSnapshotStaleWindow))
        {
            conflictSummaries.Add("Claimed-installation replay includes stale or inactive device state; confirm and relink before continuing.");
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

        var provenanceReceipts = BuildRestoreProvenanceReceipts(
            user.UserId,
            claimedInstallations: claimedInstallations,
            activeGrants: activeGrants,
            recentArtifacts: recentArtifacts,
            ruleEnvironments: ruleEnvironments,
            dossiers: dossiers,
            campaigns: campaigns,
            observedAtUtc: generatedAtUtc);
        var conflictReceipts = BuildRestoreConflictReceipts(
            user.UserId,
            claimedInstallations,
            activeGrants,
            recentArtifacts,
            ruleEnvironments,
            conflictSummaries,
            generatedAtUtc);

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
            ProvenanceReceipts: provenanceReceipts,
            ConflictReceipts: conflictReceipts,
            GeneratedAtUtc: generatedAtUtc);
    }

    private static IReadOnlyList<WorkspaceRestoreProvenanceReceipt> BuildRestoreProvenanceReceipts(
        string userId,
        IReadOnlyList<ClaimedInstallationDto> claimedInstallations,
        IReadOnlyList<InstallationGrantDto> activeGrants,
        IReadOnlyList<RestoreArtifactProjection> recentArtifacts,
        IReadOnlyList<RuleEnvironmentRef> ruleEnvironments,
        IReadOnlyList<RunnerDossierProjection> dossiers,
        IReadOnlyList<CampaignProjection> campaigns,
        DateTimeOffset observedAtUtc)
    {
        List<WorkspaceRestoreProvenanceReceipt> receipts = [];
        Dictionary<string, ClaimedInstallationDto> installationsById = claimedInstallations
            .Where(static item => !string.IsNullOrWhiteSpace(item.InstallationId))
            .GroupBy(static item => item.InstallationId, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(static group => group.Key, static group => group.First(), StringComparer.OrdinalIgnoreCase);

        int installationIndex = 0;
        foreach (ClaimedInstallationDto installation in claimedInstallations)
        {
            string artifactLabel = installation.ArtifactId;
            if (!string.IsNullOrWhiteSpace(installation.HostLabel))
            {
                artifactLabel = $"{artifactLabel} ({installation.HostLabel})";
            }

            string? grantId = activeGrants
                .FirstOrDefault(item => string.Equals(item.InstallationId, installation.InstallationId, StringComparison.OrdinalIgnoreCase))
                ?.GrantId;

            receipts.Add(new WorkspaceRestoreProvenanceReceipt(
                ReceiptId: StableId("restore-provenance", $"{userId}:{installation.InstallationId}:installation:{installationIndex}:{installation.Channel}"),
                Kind: "claimed_installation",
                SubjectId: installation.InstallationId,
                Surface: "workspace_restore",
                Summary: $"Restore packet retains claim for {artifactLabel} on {installation.Channel} ({installation.Platform ?? "unknown"}/{installation.Arch ?? "any"}) and binds to surface-bound continuity routing.",
                Proof: string.IsNullOrWhiteSpace(grantId)
                    ? $"artifact:{installation.ArtifactId}"
                    : $"artifact:{installation.ArtifactId}; grant:{grantId}",
                ObservedAtUtc: observedAtUtc,
                Authority: "hub_registry_install_linking",
                RecoveryHint: "Open Installs from this install when the restore rail needs a fresh claim or relink receipt."));
            installationIndex++;
        }

        foreach (InstallationGrantDto grant in activeGrants)
        {
            bool matchedInstallation = installationsById.ContainsKey(grant.InstallationId);
            string label = matchedInstallation
                ? $"device:{grant.InstallationId}"
                : $"orphan-installation:{grant.InstallationId}";
            receipts.Add(new WorkspaceRestoreProvenanceReceipt(
                ReceiptId: StableId("restore-provenance", $"{userId}:{grant.GrantId}:entitlement:{grant.Status}"),
                Kind: matchedInstallation ? "active_entitlement" : "orphan_entitlement",
                SubjectId: grant.GrantId,
                Surface: "entitlement_sync",
                Summary: $"Entitlement grant {grant.GrantId} ({grant.Status}) on {label} is replayable to the restore plane until {grant.ExpiresAtUtc:yyyy-MM-dd}.",
                Proof: $"status:{grant.Status};issued:{grant.IssuedAtUtc:O}",
                ObservedAtUtc: observedAtUtc,
                Authority: "hub_entitlement_ledger",
                RecoveryHint: matchedInstallation
                    ? "If this grant expires or drifts, refresh account access on the same claimed install before continuing."
                    : "Resolve the orphaned grant in account access before trusting replay on a second device."));
        }

        if (activeGrants.Count > 0)
        {
            int matchedGrantCount = activeGrants.Count(grant => installationsById.ContainsKey(grant.InstallationId));
            int orphanGrantCount = activeGrants.Count - matchedGrantCount;
            receipts.Add(new WorkspaceRestoreProvenanceReceipt(
                ReceiptId: StableId("restore-provenance", $"{userId}:entitlement-replication:{matchedGrantCount}:{orphanGrantCount}"),
                Kind: "entitlement_replication",
                SubjectId: userId,
                Surface: "entitlement_sync",
                Summary: $"Entitlement replication snapshot carries {matchedGrantCount} grant(s) bound to claimed installs and {orphanGrantCount} orphaned grant(s) that must be reconciled before roaming restore is trusted.",
                Proof: $"matched:{matchedGrantCount};orphaned:{orphanGrantCount}",
                ObservedAtUtc: observedAtUtc,
                Authority: "hub_entitlement_ledger",
                RecoveryHint: "Open account access to refresh entitlement replication receipts before continuing from a second device when counts or claim posture drift."));
        }

        foreach (RestoreArtifactProjection artifact in recentArtifacts)
        {
            receipts.Add(new WorkspaceRestoreProvenanceReceipt(
                ReceiptId: StableId("restore-provenance", $"{userId}:{artifact.ArtifactId}:artifact:{artifact.Kind}"),
                Kind: "recent_artifact",
                SubjectId: artifact.ArtifactId,
                Surface: "entitlement_sync",
                Summary: $"Recent artifact {artifact.Label} ({artifact.ArtifactId}) is explicit in restore with kind {artifact.Kind} and channel {artifact.Channel ?? "unknown"} {artifact.Version}.",
                Proof: $"{artifact.Channel ?? "unknown"}::{artifact.Version ?? "rev"}::{artifact.Kind}",
                ObservedAtUtc: observedAtUtc,
                Authority: "hub_registry_release_receipts",
                RecoveryHint: "Redownload or refresh the signed-in install rail if this artifact receipt no longer matches the device you are restoring."));
        }

        foreach (ClaimedInstallationDto installation in claimedInstallations)
        {
            RestoreArtifactProjection? artifactEvidence = recentArtifacts.FirstOrDefault(
                item => !string.IsNullOrWhiteSpace(item.ArtifactId)
                    && string.Equals(item.ArtifactId, installation.ArtifactId, StringComparison.OrdinalIgnoreCase));

            if (artifactEvidence is not null
                && (HasRestoreDrift(installation.Channel, artifactEvidence.Channel)
                    || HasRestoreDrift(installation.Version, artifactEvidence.Version)))
            {
                receipts.Add(new WorkspaceRestoreProvenanceReceipt(
                    ReceiptId: StableId("restore-provenance", $"{userId}:{installation.InstallationId}:artifact-drift:{artifactEvidence.ArtifactId}"),
                    Kind: "entitlement_artifact_drift",
                    SubjectId: installation.InstallationId,
                    Surface: "entitlement_sync",
                    Summary: $"Restore provenance records artifact drift for claimed install {installation.InstallationId}: device reports {installation.Channel ?? "unknown"} {installation.Version ?? "unknown"}, while reconnectable receipt {artifactEvidence.ArtifactId} carries {artifactEvidence.Channel ?? "unknown"} {artifactEvidence.Version ?? "unknown"}.",
                    Proof: $"device:{installation.Channel ?? "unknown"}:{installation.Version ?? "unknown"};artifact:{artifactEvidence.Channel ?? "unknown"}:{artifactEvidence.Version ?? "unknown"}",
                    ObservedAtUtc: observedAtUtc,
                    Authority: "hub_registry_release_receipts",
                    RecoveryHint: "Refresh the signed-in download or install rail before continuing so entitlement replay and artifact truth match."));
            }

            if (!string.Equals(installation.Status, ClaimedInstallationStates.Active, StringComparison.OrdinalIgnoreCase)
                || observedAtUtc - installation.UpdatedAtUtc > RestoreSnapshotStaleWindow)
            {
                receipts.Add(new WorkspaceRestoreProvenanceReceipt(
                    ReceiptId: StableId("restore-provenance", $"{userId}:{installation.InstallationId}:claimed-installation-stale:{installation.Status}"),
                    Kind: "claimed_installation_stale",
                    SubjectId: installation.InstallationId,
                    Surface: "workspace_restore",
                    Summary: $"Restore provenance records stale claimed-install state for {installation.InstallationId}: status {installation.Status}, last refreshed {installation.UpdatedAtUtc:O}.",
                    Proof: $"status:{installation.Status};updated:{installation.UpdatedAtUtc:O}",
                    ObservedAtUtc: observedAtUtc,
                    Authority: "hub_registry_install_linking",
                    RecoveryHint: "Open account access and relink this claimed install before editing shared workspace state on another device."));
            }
        }

        foreach (InstallationGrantDto grant in activeGrants)
        {
            if (installationsById.TryGetValue(grant.InstallationId, out ClaimedInstallationDto? claimedInstallation)
                && (!string.Equals(claimedInstallation.Status, ClaimedInstallationStates.Active, StringComparison.OrdinalIgnoreCase)
                    || observedAtUtc - claimedInstallation.UpdatedAtUtc > RestoreSnapshotStaleWindow))
            {
                receipts.Add(new WorkspaceRestoreProvenanceReceipt(
                    ReceiptId: StableId("restore-provenance", $"{userId}:{grant.GrantId}:entitlement-replication-stale-claim:{claimedInstallation.InstallationId}"),
                    Kind: "entitlement_replication_stale_claim",
                    SubjectId: grant.GrantId,
                    Surface: "entitlement_sync",
                    Summary: $"Entitlement replication provenance records grant {grant.GrantId} pointing at stale claimed install {claimedInstallation.InstallationId}.",
                    Proof: $"grant:{grant.GrantId};claim:{claimedInstallation.InstallationId};claim-status:{claimedInstallation.Status};claim-updated:{claimedInstallation.UpdatedAtUtc:O}",
                    ObservedAtUtc: observedAtUtc,
                    Authority: "hub_entitlement_ledger",
                    RecoveryHint: "Refresh account access so the claimed install and entitlement replication receipt are minted from the same current state."));
            }
        }

        foreach (RuleEnvironmentRef environment in ruleEnvironments.Take(4))
        {
            string environmentLabel = $"{environment.CompatibilityFingerprint} [{environment.OwnerScope}/{environment.ApprovalState}]";
            receipts.Add(new WorkspaceRestoreProvenanceReceipt(
                ReceiptId: StableId("restore-provenance", $"{userId}:{environment.EnvironmentId}:ruleenv"),
                Kind: "rule_environment",
                SubjectId: environment.EnvironmentId,
                Surface: "workspace_restore",
                Summary: $"Restore retains rule environment {environmentLabel} with {environment.SourcePacks.Count} source pack(s) and {environment.HouseRulePacks.Count} house rule(s).",
                Proof: $"{environment.CompatibilityFingerprint}:{environment.ApprovalState}",
                ObservedAtUtc: observedAtUtc,
                Authority: "core_rule_environment_receipts",
                RecoveryHint: "Review packs and governed approval state before computing against a different rule environment on this device."));
        }

        if (dossiers.Count > 0 || campaigns.Count > 0)
        {
            string inventory = $"{dossiers.Count} dossier(s), {campaigns.Count} campaign(s)";
            receipts.Add(new WorkspaceRestoreProvenanceReceipt(
                ReceiptId: StableId("restore-provenance", $"{userId}:inventory:{dossiers.Count}:{campaigns.Count}"),
                Kind: "restore_inventory_snapshot",
                SubjectId: userId,
                Surface: "workspace_restore",
                Summary: $"Restore plane inventory snapshot includes {inventory} for immediate continue readiness.",
                Proof: inventory,
                ObservedAtUtc: observedAtUtc,
                Authority: "hub_campaign_spine_projection",
                RecoveryHint: "If this inventory does not match the device you expected, stop before editing and review the restore plane first."));
        }

        return receipts
            .GroupBy(static receipt => receipt.ReceiptId, StringComparer.OrdinalIgnoreCase)
            .Select(static group => group.First())
            .Select(receipt => receipt with
            {
                Envelope = ReceiptEnvelopeFactory.Runtime(
                    receiptKind: "workspace_restore_provenance",
                    ownerScope: "community.workspace_restore",
                    exposureClass: ReceiptExposureClasses.SignedIn,
                    evidenceRef: receipt.SubjectId,
                    reviewState: receipt.Kind)
            })
            .ToArray();
    }

    private static IReadOnlyList<WorkspaceRestoreConflictReceipt> BuildRestoreConflictReceipts(
        string userId,
        IReadOnlyList<ClaimedInstallationDto> claimedInstallations,
        IReadOnlyList<InstallationGrantDto> activeGrants,
        IReadOnlyList<RestoreArtifactProjection> recentArtifacts,
        IReadOnlyList<RuleEnvironmentRef> ruleEnvironments,
        IReadOnlyList<string> conflictSummaries,
        DateTimeOffset observedAtUtc)
    {
        List<WorkspaceRestoreConflictReceipt> receipts = [];

        if (conflictSummaries.Count > 0)
        {
            int conflictIndex = 0;
            foreach (string summary in conflictSummaries.Take(2))
            {
                receipts.Add(new WorkspaceRestoreConflictReceipt(
                    ReceiptId: StableId("restore-conflict", $"{userId}:{conflictIndex}:{summary}"),
                    Severity: "warning",
                    Kind: "restore_summary_conflict",
                    SubjectId: "restore-plane",
                    Summary: summary,
                    Resolution: "Open the restore plane and confirm intended posture before editing or continuing this workspace on a different device.",
                    ObservedAtUtc: observedAtUtc,
                    Surface: "workspace_restore",
                    BlocksContinue: true));
                conflictIndex++;
            }
        }

        Dictionary<string, InstallationGrantDto> grantsByInstallation = activeGrants
            .Where(static item => !string.IsNullOrWhiteSpace(item.InstallationId))
            .GroupBy(static item => item.InstallationId, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(static group => group.Key, static group => group.First(), StringComparer.OrdinalIgnoreCase);
        Dictionary<string, ClaimedInstallationDto> claimedInstallationsById = claimedInstallations
            .Where(static item => !string.IsNullOrWhiteSpace(item.InstallationId))
            .GroupBy(static item => item.InstallationId, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(static group => group.Key, static group => group.First(), StringComparer.OrdinalIgnoreCase);
        HashSet<string> claimedInstallationIds = claimedInstallations
            .Select(static item => item.InstallationId)
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        foreach (IGrouping<string, InstallationGrantDto> duplicateGrantGroup in activeGrants
            .Where(static item => !string.IsNullOrWhiteSpace(item.InstallationId))
            .Where(static item => string.Equals(item.Status, InstallationGrantStates.Active, StringComparison.OrdinalIgnoreCase))
            .GroupBy(static item => item.InstallationId, StringComparer.OrdinalIgnoreCase)
            .Where(static group => group.Count() > 1))
        {
            string[] grantIds = duplicateGrantGroup
                .Select(static item => item.GrantId)
                .Where(static item => !string.IsNullOrWhiteSpace(item))
                .OrderBy(static item => item, StringComparer.OrdinalIgnoreCase)
                .ToArray();
            receipts.Add(new WorkspaceRestoreConflictReceipt(
                ReceiptId: StableId("restore-conflict", $"{userId}:{duplicateGrantGroup.Key}:duplicate-entitlement-grants:{string.Join(":", grantIds)}"),
                Severity: "blocking",
                Kind: "entitlement_replication_duplicate_grant",
                SubjectId: duplicateGrantGroup.Key,
                Summary: $"Entitlement replication has {duplicateGrantGroup.Count()} active grant receipts for claimed install {duplicateGrantGroup.Key}: {string.Join(", ", grantIds)}.",
                Resolution: "Open account access and rotate duplicate entitlement grants before restoring this workspace on another device.",
                ObservedAtUtc: observedAtUtc,
                Surface: "entitlement_sync",
                BlocksContinue: true));
        }

        foreach (InstallationGrantDto grant in activeGrants)
        {
            if (!string.Equals(grant.Status, InstallationGrantStates.Active, StringComparison.OrdinalIgnoreCase))
            {
                receipts.Add(new WorkspaceRestoreConflictReceipt(
                    ReceiptId: StableId("restore-conflict", $"{userId}:{grant.GrantId}:status-{grant.Status}"),
                    Severity: "attention",
                    Kind: "entitlement_status_mismatch",
                    SubjectId: grant.GrantId,
                    Summary: $"Entitlement {grant.GrantId} is `{grant.Status}` and cannot be replayed as active restore access.",
                    Resolution: "Rotate the install claim or refresh grant status in account access before restoring this workspace.",
                    ObservedAtUtc: observedAtUtc,
                    Surface: "entitlement_sync",
                    BlocksContinue: true));
            }

            if (grant.ExpiresAtUtc <= observedAtUtc)
            {
                receipts.Add(new WorkspaceRestoreConflictReceipt(
                    ReceiptId: StableId("restore-conflict", $"{userId}:{grant.GrantId}:expired"),
                    Severity: "attention",
                    Kind: "entitlement_expired",
                    SubjectId: grant.GrantId,
                    Summary: $"Entitlement {grant.GrantId} expired at {grant.ExpiresAtUtc:O} and is stale for restore replay.",
                    Resolution: "Refresh install linking to mint a current entitlement before continuing on this device.",
                    ObservedAtUtc: observedAtUtc,
                    Surface: "entitlement_sync",
                    BlocksContinue: true));
            }

            if (!claimedInstallationIds.Contains(grant.InstallationId))
            {
                receipts.Add(new WorkspaceRestoreConflictReceipt(
                    ReceiptId: StableId("restore-conflict", $"{userId}:{grant.GrantId}:orphan-grant"),
                    Severity: "attention",
                    Kind: "entitlement_orphan",
                    SubjectId: grant.GrantId,
                    Summary: $"Active entitlement {grant.GrantId} is not tied to a claimed installation ({grant.InstallationId}) in the roaming restore packet.",
                    Resolution: "Resolve by reclaiming the install on this account or rotating the stale entitlement before reusing this device.",
                    ObservedAtUtc: observedAtUtc,
                    Surface: "entitlement_sync",
                    BlocksContinue: true));
            }

            if (claimedInstallationsById.TryGetValue(grant.InstallationId, out ClaimedInstallationDto? claimedInstallation)
                && (!string.Equals(claimedInstallation.Status, ClaimedInstallationStates.Active, StringComparison.OrdinalIgnoreCase)
                    || observedAtUtc - claimedInstallation.UpdatedAtUtc > RestoreSnapshotStaleWindow))
            {
                receipts.Add(new WorkspaceRestoreConflictReceipt(
                    ReceiptId: StableId("restore-conflict", $"{userId}:{grant.GrantId}:replication-stale-claim"),
                    Severity: "blocking",
                    Kind: "entitlement_replication_stale_claim",
                    SubjectId: grant.GrantId,
                    Summary: $"Entitlement replication for {grant.GrantId} points at claimed install {claimedInstallation.InstallationId}, but that claim is {claimedInstallation.Status} and last refreshed at {claimedInstallation.UpdatedAtUtc:O}.",
                    Resolution: "Refresh the claimed install and entitlement replication receipts in account access before restoring this workspace on another device.",
                    ObservedAtUtc: observedAtUtc,
                    Surface: "entitlement_sync",
                    BlocksContinue: true));
            }
        }

        foreach (ClaimedInstallationDto installation in claimedInstallations)
        {
            RestoreArtifactProjection? artifactEvidence = recentArtifacts.FirstOrDefault(
                item => !string.IsNullOrWhiteSpace(item.ArtifactId)
                    && string.Equals(item.ArtifactId, installation.ArtifactId, StringComparison.OrdinalIgnoreCase));

            if (!string.Equals(installation.Status, ClaimedInstallationStates.Active, StringComparison.OrdinalIgnoreCase))
            {
                receipts.Add(new WorkspaceRestoreConflictReceipt(
                    ReceiptId: StableId("restore-conflict", $"{userId}:{installation.InstallationId}:status-{installation.Status}"),
                    Severity: "attention",
                    Kind: "claimed_installation_inactive",
                    SubjectId: installation.InstallationId,
                    Summary: $"Claimed install {installation.InstallationId} is `{installation.Status}` and needs relink before restore replay.",
                    Resolution: "Reclaim the installation from account access so restore continuity only references active devices.",
                    ObservedAtUtc: observedAtUtc,
                    Surface: "workspace_restore",
                    BlocksContinue: true));
            }

            if (observedAtUtc - installation.UpdatedAtUtc > RestoreSnapshotStaleWindow)
            {
                receipts.Add(new WorkspaceRestoreConflictReceipt(
                    ReceiptId: StableId("restore-conflict", $"{userId}:{installation.InstallationId}:stale-claimed-install"),
                    Severity: "blocking",
                    Kind: "claimed_installation_stale",
                    SubjectId: installation.InstallationId,
                    Summary: $"Claimed install {installation.InstallationId} has not refreshed since {installation.UpdatedAtUtc:O}; restore evidence may be stale.",
                    Resolution: "Reopen the install from account access and relink to refresh claim and entitlement replay evidence.",
                    ObservedAtUtc: observedAtUtc,
                    Surface: "workspace_restore",
                    BlocksContinue: true));
            }

            if (artifactEvidence is not null
                && (HasRestoreDrift(installation.Channel, artifactEvidence.Channel)
                    || HasRestoreDrift(installation.Version, artifactEvidence.Version)))
            {
                receipts.Add(new WorkspaceRestoreConflictReceipt(
                    ReceiptId: StableId("restore-conflict", $"{userId}:{installation.InstallationId}:artifact-drift"),
                    Severity: "attention",
                    Kind: "entitlement_artifact_drift",
                    SubjectId: installation.InstallationId,
                    Summary: $"Claimed install {installation.InstallationId} now reports {installation.Channel ?? "unknown"} {installation.Version ?? "unknown"}, but restore only has artifact replay proof for {artifactEvidence.Channel ?? "unknown"} {artifactEvidence.Version ?? "unknown"}.",
                    Resolution: "Refresh the signed-in install rail or redownload the current release before you continue on another device so entitlement replay matches the install you are carrying forward.",
                    ObservedAtUtc: observedAtUtc,
                    Surface: "entitlement_sync",
                    BlocksContinue: true));
            }

            if (!grantsByInstallation.ContainsKey(installation.InstallationId)
                && !string.Equals(string.Empty, installation.InstallationId, StringComparison.Ordinal))
            {
                receipts.Add(new WorkspaceRestoreConflictReceipt(
                    ReceiptId: StableId("restore-conflict", $"{userId}:{installation.InstallationId}:missing-grant"),
                    Severity: "warning",
                    Kind: "entitlement_missing",
                    SubjectId: installation.InstallationId,
                    Summary: $"Claimed install {installation.InstallationId} lacks an active entitlement grant in this roaming snapshot.",
                    Resolution: "Refresh install linking or rotate local claim state so entitlement replay remains bounded and verifiable.",
                    ObservedAtUtc: observedAtUtc,
                    Surface: "entitlement_sync",
                    BlocksContinue: true));
            }

            bool hasArtifactEvidence = recentArtifacts.Any(
                item => !string.IsNullOrWhiteSpace(item.ArtifactId)
                    && string.Equals(item.ArtifactId, installation.ArtifactId, StringComparison.OrdinalIgnoreCase));
            if (!hasArtifactEvidence)
            {
                receipts.Add(new WorkspaceRestoreConflictReceipt(
                    ReceiptId: StableId("restore-conflict", $"{userId}:{installation.InstallationId}:missing-artifact"),
                    Severity: "warning",
                    Kind: "restore_artifact_missing",
                    SubjectId: installation.InstallationId,
                    Summary: $"Restore snapshot has no reconnectable artifact receipt for {installation.InstallationId}; stale install claims can silently lose continuity.",
                    Resolution: "Open account claim/restore flow and refresh downloadable artifact receipts before proceeding.",
                    ObservedAtUtc: observedAtUtc,
                    Surface: "workspace_restore",
                    BlocksContinue: false));
            }
        }

        if (ruleEnvironments.Select(static environment => environment.CompatibilityFingerprint).Distinct(StringComparer.OrdinalIgnoreCase).Count() > 1)
        {
            receipts.Add(new WorkspaceRestoreConflictReceipt(
                ReceiptId: StableId("restore-conflict", $"{userId}:rule-environment-mismatch"),
                Severity: "attention",
                Kind: "workspace_rule_environment_mismatch",
                SubjectId: "rule-environment",
                Summary: "Restore includes mixed rule-environment fingerprints across dossier and campaign projections.",
                Resolution: "Review rule packs and choose a single active set before the next continue step.",
                ObservedAtUtc: observedAtUtc,
                Surface: "workspace_restore",
                BlocksContinue: true));
        }

        return receipts
            .Select(receipt => receipt with
            {
                Envelope = ReceiptEnvelopeFactory.Runtime(
                    receiptKind: "workspace_restore_conflict",
                    ownerScope: "community.workspace_restore",
                    exposureClass: ReceiptExposureClasses.SignedIn,
                    evidenceRef: receipt.SubjectId,
                    reviewState: receipt.Kind)
            })
            .ToArray();
    }

    private static bool HasRestoreDrift(string? left, string? right)
    {
        string? normalizedLeft = AccountService.NormalizeOptional(left);
        string? normalizedRight = AccountService.NormalizeOptional(right);
        return normalizedLeft is not null
            && normalizedRight is not null
            && !string.Equals(normalizedLeft, normalizedRight, StringComparison.OrdinalIgnoreCase);
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
        IReadOnlyList<AftermathRecapPackageProjection> aftermathPackages,
        IReadOnlyList<CampaignAdoptionProjection> campaignAdoptions,
        IReadOnlyList<RunnerGoalProjection> runnerGoals,
        IReadOnlyList<ResolutionReportApprovalProjection> resolutionReportApprovals,
        IReadOnlyList<WorldTickProjection> worldTicks,
        IReadOnlyList<PlayerSafeNewsProjection> playerSafeNews)
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
        var workspaceCampaignAdoptions = campaignAdoptions
            .Where(item => string.Equals(item.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase)
                || string.Equals(item.WorkspaceId, workspaceId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
        var workspaceRunnerGoals = runnerGoals
            .Where(item => string.Equals(item.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase)
                || string.Equals(item.WorkspaceId, workspaceId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
        var workspaceResolutionReportApprovals = resolutionReportApprovals
            .Where(item => string.Equals(item.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase)
                || string.Equals(item.WorkspaceId, workspaceId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
        var workspaceWorldTicks = worldTicks
            .Where(item => string.Equals(item.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase)
                || string.Equals(item.WorkspaceId, workspaceId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
        var workspacePlayerSafeNews = playerSafeNews
            .Where(item => string.Equals(item.CampaignId, campaign.CampaignId, StringComparison.OrdinalIgnoreCase)
                || string.Equals(item.WorkspaceId, workspaceId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
        CampaignAdoptionLoopProjection? campaignAdoptionLoop = BuildCampaignAdoptionLoopProjection(
            workspaceId,
            campaign,
            workspaceCampaignAdoptions,
            workspaceRunnerGoals,
            workspaceResolutionReportApprovals,
            workspaceWorldTicks,
            workspacePlayerSafeNews);

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
                Summary: $"{consequences.Length} governed faction, heat, contact, and reputation signal(s) stay attached to the shared campaign view with receipt-backed evidence and explicit return-loop actions.")); // .Replace(
        }
        if (rosterTransfers.Length > 0)
        {
            readinessCues.Add(new CampaignReadinessCue(
                CueId: StableId("cue", $"{campaign.CampaignId}:transfers"),
                Severity: "ready",
                Title: "Roster transfer history is attached",
                Summary: $"{rosterTransfers.Length} recent dossier move(s) keep source, target, and ownership history attached to this campaign view."));
        }
        if (workspacePrepLaunches.Length > 0)
        {
            readinessCues.Add(new CampaignReadinessCue(
                CueId: StableId("cue", $"{campaign.CampaignId}:prep-launches"),
                Severity: "ready",
                Title: "Governed prep binding is attached",
                Summary: $"{workspacePrepLaunches.Length} recent packet launch(es) keep opposition and scene prep bound to this campaign without recreating local shadow prep notes."));
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
        if (campaignAdoptionLoop?.Adoption is not null)
        {
            readinessCues.Add(new CampaignReadinessCue(
                CueId: StableId("cue", $"{campaign.CampaignId}:adoption"),
                Severity: campaignAdoptionLoop.Adoption.SafeToPlay && campaignAdoptionLoop.Adoption.ConfidencePercent >= 70 ? "ready" : "review",
                Title: "Campaign adoption wizard is attached",
                Summary: $"{campaignAdoptionLoop.Adoption.ConfidencePercent}% confidence with explicit unknown provenance kept on the governed adoption lane for {campaign.Name}."));
        }
        if (campaignAdoptionLoop?.RunnerGoals.Count > 0)
        {
            readinessCues.Add(new CampaignReadinessCue(
                CueId: StableId("cue", $"{campaign.CampaignId}:runner-goals"),
                Severity: "ready",
                Title: "Runner goal pins are attached",
                Summary: $"{campaignAdoptionLoop.RunnerGoals.Count} governed runner goal pin(s) stay attached to the shared workspace instead of local-only notes."));
        }
        if (campaignAdoptionLoop?.ResolutionReportApproval is not null)
        {
            readinessCues.Add(new CampaignReadinessCue(
                CueId: StableId("cue", $"{campaign.CampaignId}:world-tick"),
                Severity: "ready",
                Title: "BLACK LEDGER follow-through is attached",
                Summary: "ResolutionReport approval, first WorldTick, and player-safe news stay on one reviewed hub path without turning preview copy into world state."));
        }

        var recapShelf = workspaceAftermathPackages
            .Select(BuildAftermathRecapShelfProjection)
            .Concat(workspacePlayerSafeNews.Select(BuildPlayerSafeNewsRecapShelfProjection))
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
        var nextSessionCarryForward = BuildNextSessionCarryForward(campaign, nextSafeAction, leadRun, activeScene, leadObjective, consequences, workspacePrepLaunches, workspaceTravelPrefetches, workspaceAftermathPackages, campaignAdoptionLoop);
        var campaignMemory = BuildCampaignMemory(campaign, nextSafeAction, leadRun, activeScene, leadObjective, consequences, rosterTransfers, workspacePrepLaunches, workspaceTravelPrefetches, workspaceAftermathPackages, nextSessionCarryForward, campaignAdoptionLoop);
        var changePackets = BuildWorkspaceChangePackets(campaign, enrichedRecapShelf, leadRun, activeScene, leadObjective, rosterTransfers, workspacePrepLaunches, workspaceTravelPrefetches, workspaceAftermathPackages, nextSessionCarryForward, campaignAdoptionLoop);

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
            CampaignMemory: campaignMemory,
            CampaignAdoptionLoop: campaignAdoptionLoop);
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

    private static string ResolveGroupArtifactPublicationSummary(IReadOnlyList<CampaignWorkspaceProjection> groupWorkspaces)
    {
        var shelfEntries = groupWorkspaces
            .SelectMany(static workspace => workspace.RecapShelf)
            .ToArray();
        if (shelfEntries.Length == 0)
        {
            return "No governed artifact publication receipt is attached to this maintainer path yet.";
        }

        int readyCount = shelfEntries.Count(static item =>
            string.Equals(item.PublicationState, "ready", StringComparison.OrdinalIgnoreCase)
            || string.Equals(item.PublicationState, HubPublicationStates.Published, StringComparison.OrdinalIgnoreCase));
        int discoverableCount = shelfEntries.Count(static item => item.Discoverable);
        PublicationSafeProjection latest = shelfEntries[0];
        string latestSummary = string.IsNullOrWhiteSpace(latest.PublicationSummary)
            ? latest.Summary
            : latest.PublicationSummary!;
        return $"{shelfEntries.Length} governed artifact receipt(s) stay on the same maintainer path; {readyCount} ready or published, {discoverableCount} discoverable, latest is {latest.Label}: {latestSummary}";
    }

    private string ResolveGroupSupportEscalationSummary(HubUserDto user)
    {
        lock (_supportStore.Gate)
        {
            var cases = _supportStore.CasesById.Values
                .Where(item =>
                    string.Equals(item.ReporterUserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                    && !string.Equals(item.Status, SupportCaseStatuses.UserNotified, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
            if (cases.Length == 0)
            {
                return "No tracked support escalation is blocking this maintainer path right now.";
            }

            SupportCaseProjection latest = cases[0];
            return $"{cases.Length} tracked support case(s) stay on the same maintainer path; latest is {HumanizeSupportValue(latest.Kind)} ({HumanizeSupportValue(latest.Status)}).";
        }
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

    private static string HumanizeSupportValue(string? value)
    {
        var normalized = AccountService.NormalizeOptional(value);
        return normalized is null
            ? "Unknown"
            : string.Join(' ', normalized.Split('_', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries));
    }

    private static IReadOnlyList<CommunityInviteCampaignProjection> BuildGroupInviteCampaigns(IReadOnlyList<CampaignProjection> groupCampaigns)
        => groupCampaigns
            .Select(static campaign => new CommunityInviteCampaignProjection(
                CampaignId: campaign.CampaignId,
                CampaignName: campaign.Name,
                Status: campaign.Status))
            .ToArray();

    private OrganizerOperationProjection BuildOrganizerOperationProjectionLocked(
        HubUserDto user,
        AccountCampaignSummary summary,
        CommunityOperatorProjection operation,
        IReadOnlyList<OrganizerSupportCaseProjection> supportCases)
    {
        ArgumentNullException.ThrowIfNull(user);
        ArgumentNullException.ThrowIfNull(summary);
        ArgumentNullException.ThrowIfNull(operation);
        ArgumentNullException.ThrowIfNull(supportCases);

        var group = _store.GroupsById.GetValueOrDefault(operation.GroupId);
        var groupCampaignIds = _store.CampaignSpinesById.Values
            .Where(item => string.Equals(item.GroupId, operation.GroupId, StringComparison.OrdinalIgnoreCase))
            .Select(static item => item.CampaignId)
            .Concat(operation.SeasonBoardEntries.Select(static entry => entry.CampaignId))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        var groupWorkspaces = summary.Workspaces
            .Where(workspace => groupCampaignIds.Contains(workspace.CampaignId))
            .OrderByDescending(static workspace => ResolveWorkspaceFreshnessUtc(workspace))
            .ToArray();
        var roles = BuildOrganizerRoleAssignmentsLocked(group);
        var permissions = BuildOrganizerPermissions(operation);
        var publicationReceipts = BuildOrganizerArtifactPublicationReceipts(groupWorkspaces);
        var seasonLanes = operation.SeasonBoardEntries
            .Select(static entry => new OrganizerSeasonLaneProjection(
                CampaignId: entry.CampaignId,
                WorkspaceId: entry.WorkspaceId,
                CampaignName: entry.CampaignName,
                RunTitle: entry.RunTitle,
                LatestEventSummary: entry.LatestEventSummary,
                NextSafeAction: entry.NextSafeAction,
                RecapSummary: entry.RecapSummary,
                ConsequenceSummary: entry.ConsequenceSummary,
                CampaignMemorySummary: entry.CampaignMemorySummary,
                WatchoutSummary: entry.WatchoutSummary,
                UpdatedAtUtc: entry.UpdatedAtUtc))
            .ToArray();
        var roster = new OrganizerRosterContractProjection(
            Summary: $"{operation.OperationsSummary} {operation.CampaignReturnSummary}",
            MemberCount: operation.MemberCount,
            ActiveCampaignCount: operation.ActiveCampaignCount,
            RecentTransferCount: operation.RecentRosterTransfers?.Count ?? 0,
            CampaignNames: operation.CampaignNames,
            RecentTransferSummaries: (operation.RecentRosterTransfers ?? Array.Empty<RosterTransferProjection>())
                .Select(static transfer => $"{transfer.RunnerHandle}: {transfer.Summary}")
                .Take(5)
                .ToArray());
        var eventRail = new OrganizerEventRailContractProjection(
            Summary: $"{operation.LeagueOperationsSummary} {operation.SeasonEventSummary}",
            SeasonBoardCount: operation.SeasonBoardEntries.Count,
            RecentEventCount: operation.RecentEventSummaries.Count,
            ActiveSponsorSessionCount: operation.ActiveSponsorSessionCount,
            SeasonLanes: seasonLanes,
            RecentEventSummaries: operation.RecentEventSummaries,
            AuditLines: operation.RecentLeagueAuditLines);
        var artifactPublication = new OrganizerArtifactPublicationContractProjection(
            Summary: operation.ArtifactPublicationSummary ?? ResolveGroupArtifactPublicationSummary(groupWorkspaces),
            ReceiptCount: publicationReceipts.Count,
            ReadyOrPublishedCount: publicationReceipts.Count(static receipt =>
                string.Equals(receipt.PublicationState, "ready", StringComparison.OrdinalIgnoreCase)
                || string.Equals(receipt.PublicationState, "published", StringComparison.OrdinalIgnoreCase)),
            DiscoverableCount: publicationReceipts.Count(static receipt => receipt.Discoverable),
            Receipts: publicationReceipts);
        var supportEscalation = new OrganizerSupportEscalationContractProjection(
            Summary: operation.SupportEscalationSummary ?? ResolveGroupSupportEscalationSummary(user),
            OpenCaseCount: supportCases.Count,
            Cases: supportCases);
        return new OrganizerOperationProjection(
            GroupId: operation.GroupId,
            GroupName: operation.GroupName,
            GroupType: operation.GroupType,
            Visibility: operation.Visibility,
            OperatorRole: operation.OperatorRole,
            Roles: roles,
            Permissions: permissions,
            Roster: roster,
            EventRail: eventRail,
            ArtifactPublication: artifactPublication,
            SupportEscalation: supportEscalation,
            AuditLines: BuildOrganizerAuditLines(operation, publicationReceipts, supportCases));
    }

    private IReadOnlyList<OrganizerSupportCaseProjection> BuildOrganizerSupportCases(HubUserDto user)
    {
        lock (_supportStore.Gate)
        {
            return _supportStore.CasesById.Values
                .Where(item =>
                    string.Equals(item.ReporterUserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                    && !string.Equals(item.Status, SupportCaseStatuses.UserNotified, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .Take(5)
                .Select(static item => new OrganizerSupportCaseProjection(
                    CaseId: item.CaseId,
                    Kind: item.Kind,
                    Status: item.Status,
                    Title: item.Title,
                    Summary: item.Summary,
                    Source: item.Source,
                    UpdatedAtUtc: item.UpdatedAtUtc,
                    ReleaseChannel: item.ReleaseChannel,
                    Platform: item.Platform,
                    InstallationId: item.InstallationId,
                    FixedChannel: item.FixedChannel,
                    FixedVersion: item.FixedVersion,
                    Timeline: item.Timeline))
                .ToArray();
        }
    }

    private IReadOnlyList<OrganizerRoleAssignmentProjection> BuildOrganizerRoleAssignmentsLocked(GroupDto? group)
    {
        if (group is null)
        {
            return Array.Empty<OrganizerRoleAssignmentProjection>();
        }

        return group.Memberships
            .OrderByDescending(static membership => OperatorRolePriority(membership.Role))
            .ThenBy(membership => _store.UsersById.GetValueOrDefault(membership.UserId)?.DisplayName ?? membership.UserId, StringComparer.OrdinalIgnoreCase)
            .Select(membership =>
            {
                var memberUser = _store.UsersById.GetValueOrDefault(membership.UserId);
                bool canManageMembers = string.Equals(membership.Role, "owner", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(membership.Role, "organizer", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(membership.Role, "gm", StringComparison.OrdinalIgnoreCase);
                bool canIssueCodes = canManageMembers
                    || string.Equals(membership.Role, "booster", StringComparison.OrdinalIgnoreCase);
                return new OrganizerRoleAssignmentProjection(
                    UserId: membership.UserId,
                    DisplayName: memberUser?.DisplayName ?? membership.UserId,
                    Role: membership.Role,
                    JoinedAtUtc: membership.JoinedAtUtc,
                    CanManageMembers: canManageMembers,
                    CanIssueCodes: canIssueCodes);
            })
            .ToArray();
    }

    private static IReadOnlyList<OrganizerPermissionProjection> BuildOrganizerPermissions(CommunityOperatorProjection operation)
        => operation.Capabilities
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Select(static capability => new OrganizerPermissionProjection(
                Capability: capability,
                Label: capability.Replace('_', ' '),
                Summary: capability switch
                {
                    "can_manage_members" => "Manage organizer roles, roster authority, and member recovery on the same governed account rail.",
                    "can_issue_join_codes" => "Issue governed join codes for league, convention, and season entry without chat-only recovery.",
                    "can_issue_boost_codes" => "Issue sponsorship codes that stay attached to the governed community lane.",
                    "can_hold_shared_entitlements" => "Carry community-scale entitlements without collapsing them into personal install state.",
                    "campaign_workspace" => "Open shared campaign workspaces and multi-campaign season boards from the same operator contract.",
                    "creator_publication" => "Track artifact-publication posture and public-safe publication follow-through on the maintainer path.",
                    "support_closure" => "Keep human escalation and tracked support closure visible on the same operator contract.",
                    _ => "Keep this governed operator permission explicit instead of burying it in ad hoc admin folklore."
                }))
            .ToArray();

    private static IReadOnlyList<OrganizerArtifactPublicationReceiptProjection> BuildOrganizerArtifactPublicationReceipts(
        IReadOnlyList<CampaignWorkspaceProjection> groupWorkspaces)
        => groupWorkspaces
            .SelectMany(static workspace => workspace.RecapShelf)
            .OrderByDescending(static entry => entry.Label, StringComparer.OrdinalIgnoreCase)
            .Take(5)
            .Select(static entry => new OrganizerArtifactPublicationReceiptProjection(
                EntryId: entry.ProjectionId,
                Label: entry.Label,
                Summary: entry.Summary,
                Audience: entry.Audience,
                PublicationState: entry.PublicationState,
                TrustBand: entry.TrustBand,
                Discoverable: entry.Discoverable,
                PublicationSummary: entry.PublicationSummary,
                NextSafeAction: entry.NextSafeAction,
                AuditSummary: entry.AuditSummary,
                Envelope: ReceiptEnvelopeFactory.Runtime(
                    receiptKind: "organizer_artifact_publication",
                    ownerScope: "community.organizer_ops",
                    exposureClass: entry.Discoverable
                        ? ReceiptExposureClasses.PublicSafe
                        : ReceiptExposureClasses.SignedIn,
                    lifecycleState: string.Equals(entry.PublicationState, "published", StringComparison.OrdinalIgnoreCase)
                        ? ReceiptLifecycleStates.Published
                        : ReceiptLifecycleStates.Verified,
                    evidenceRef: entry.CreatorPublicationId ?? entry.ProjectionId,
                    reviewState: entry.PublicationState ?? "bounded")))
            .ToArray();

    private static IReadOnlyList<string> BuildOrganizerAuditLines(
        CommunityOperatorProjection operation,
        IReadOnlyList<OrganizerArtifactPublicationReceiptProjection> publicationReceipts,
        IReadOnlyList<OrganizerSupportCaseProjection> supportCases)
    {
        List<string> lines =
        [
            $"Roles: {operation.OperatorRole} across {operation.MemberCount} member(s).",
            $"Permissions: {(operation.Capabilities.Count == 0 ? "none" : string.Join(", ", operation.Capabilities))}.",
            $"Roster: {(operation.RecentRosterTransfers?.Count ?? 0)} recent transfer(s) across {operation.ActiveCampaignCount} active campaign(s).",
            $"Events: {operation.SeasonBoardEntries.Count} season lane(s) and {operation.RecentEventSummaries.Count} recent event summary line(s).",
            $"Publication status: {publicationReceipts.Count} publication note(s) on the maintainer path.",
            $"Support escalation: {supportCases.Count} tracked case(s) remain attached to the same account-bound closure lane."
        ];
        return lines;
    }

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
                var explainReceiptId = $"buildlab.handoff.{dossier.DossierId}";
                var runtimeFingerprint = workspace?.RuleEnvironment.CompatibilityFingerprint ?? dossier.RuleEnvironment.CompatibilityFingerprint;
                var ruleEnvironmentDiff = BuildBuildLabRuleEnvironmentDiff(dossier.RuleEnvironment, workspace?.RuleEnvironment);
                var outputs = BuildBuildLabOutputs(dossier, workspace, runtimeFingerprint, explainReceiptId, ruleEnvironmentDiff);
                var variantLabel = workspace is null ? "Living dossier carry-forward" : "Ops-first dossier carry-forward";
                var progressionLabel = workspace is null ? "Ready to seed into a campaign" : "25 / 50 / 100 Karma path stays attached to the campaign return";
                var nextSafeAction = ResolveBuildLabNextSafeAction(workspace, outputs, restore);
                var runtimeCompatibilitySummary = DescribeBuildLabRuntimeCompatibility(runtimeFingerprint, workspace, restore);
                var attachedOutputSummary = outputs.Count switch
                {
                    1 => "1 dossier or campaign-safe output is already attached to this build.",
                    > 1 => $"{outputs.Count} dossier or campaign-safe outputs are already attached to this build.",
                    _ => null
                };
                var readyOutputSummary = outputs.Count switch
                {
                    1 => "1 dossier or campaign-safe output is already ready for export, exchange, recap follow-through, and artifact follow-through.",
                    > 1 => $"{outputs.Count} dossier or campaign-safe outputs are already ready for export, exchange, recap follow-through, and artifact follow-through.",
                    _ => "Publication-safe outputs will appear as replay, recap, module, and dossier cards once the first run lands so recap follow-through stays explicit."
                };
                var campaignReturnSummary = workspace?.ReturnSummary
                    ?? "No campaign workspace is attached yet, so return still lands on the living dossier until the first governed campaign handoff exists.";
                var supportClosureSummary = DescribeBuildLabSupportClosure(runtimeFingerprint, restore);
                var watchouts = BuildBuildLabWatchouts(workspace, outputs, restore);
                var crewFitSummary = BuildBuildLabCrewFitSummary(dossier, workspace);
                var plannerCoverageSummary = BuildBuildLabPlannerCoverageSummary(dossier, workspace, outputs, restore);
                var plannerCoverageLines = BuildBuildLabPlannerCoverageLines(dossier, workspace, outputs, restore);
                var conditionalStateSummary = BuildBuildLabConditionalStateSummary(dossier, workspace);
                var conditionalStateLines = BuildBuildLabConditionalStateLines(dossier, workspace);
                var sourceHintSummary = BuildBuildLabSourceHintSummary(dossier, workspace);
                var sourceHintLines = BuildBuildLabSourceHintLines(dossier, workspace);
                var buildSurfaceSummary = BuildBuildLabSurfaceSummary(dossier, workspace, ruleEnvironmentDiff);
                var buildSurfaceLines = BuildBuildLabSurfaceLines(dossier, workspace, ruleEnvironmentDiff);
                var exchangeParitySummary = BuildBuildLabExchangeParitySummary(outputs);
                var exchangeParityLines = BuildBuildLabExchangeParityLines(outputs);
                var portabilityPillarSummary = BuildBuildLabPortabilityPillarSummary(outputs);
                var portabilityPillarLines = BuildBuildLabPortabilityPillarLines(outputs);
                return new BuildLabHandoffProjection(
                    HandoffId: StableId("buildlab", dossier.DossierId),
                    DossierId: dossier.DossierId,
                    CampaignId: dossier.CampaignId,
                    Title: $"{dossier.DisplayName} build path",
                    Summary: "The chosen character path now lands in the dossier and campaign return point instead of a disposable comparison card.",
                    VariantLabel: variantLabel,
                    ProgressionLabel: progressionLabel,
                    ExplainEntryId: explainReceiptId,
                    TradeoffLines:
                    [
                        attachedOutputSummary ?? "Role overlap stays explicit before the build leaves build comparison.",
                        workspace is null
                            ? "No campaign workspace is attached yet, so the build seeds the dossier first."
                            : $"Campaign workspace {workspace.CampaignName} keeps the downstream continuity target visible and the same upgrade path attached.",
                        ruleEnvironmentDiff.Summary
                    ],
                    ProgressionOutcomes:
                    [
                        workspace is null
                            ? "25 / 50 / 100 Karma checkpoints stay attached to the living dossier until the first reviewed campaign workspace exists."
                            : $"25 / 50 / 100 Karma checkpoints stay attached to {workspace.CampaignName} so the return path keeps the same upgrade plan.",
                        readyOutputSummary,
                        $"Explain receipt {explainReceiptId} stays attached across character-template, JSON exchange, Foundry-class exchange, sheet-viewer checks, print-ready PDF export, replay timeline, session recap, and run-module artifact follow-through."
                    ],
                    Outputs: outputs,
                    UpdatedAtUtc: dossier.UpdatedAtUtc,
                    NextSafeAction: nextSafeAction,
                    RuntimeCompatibilitySummary: runtimeCompatibilitySummary,
                    CampaignReturnSummary: campaignReturnSummary,
                    SupportClosureSummary: supportClosureSummary,
                    RuleEnvironmentDiff: ruleEnvironmentDiff,
                    Watchouts: watchouts,
                    PlannerCoverageSummary: plannerCoverageSummary,
                    PlannerCoverageLines: plannerCoverageLines,
                    CrewFitSummary: crewFitSummary,
                    ConditionalStateSummary: conditionalStateSummary,
                    ConditionalStateLines: conditionalStateLines,
                    SourceHintSummary: sourceHintSummary,
                    SourceHintLines: sourceHintLines,
                    BuildSurfaceSummary: buildSurfaceSummary,
                    BuildSurfaceLines: buildSurfaceLines,
                    ExchangeParitySummary: exchangeParitySummary,
                    ExchangeParityLines: exchangeParityLines,
                    PortabilityPillarSummary: portabilityPillarSummary,
                    PortabilityPillarLines: portabilityPillarLines);
            })
            .Take(3)
            .ToArray();
    }

    private static IReadOnlyList<PublicationSafeProjection> BuildBuildLabOutputs(
        RunnerDossierProjection dossier,
        CampaignWorkspaceProjection? workspace,
        string runtimeFingerprint,
        string explainReceiptId,
        BuildLabRuleEnvironmentDiffProjection ruleEnvironmentDiff)
    {
        const int maxOutputs = 8;
        var activeEnvironment = workspace?.RuleEnvironment ?? dossier.RuleEnvironment;
        string sourceHintAuditToken = BuildBuildLabSourceHintAuditToken(activeEnvironment);
        var governedExports = new[]
        {
            BuildBuildLabGovernedOutput(
                dossier,
                projectionIdSuffix: "character-template",
                kind: "character_template",
                label: "Character template export",
                summary: "Save this character path as a reusable template without forking dossier truth.",
                runtimeFingerprint: runtimeFingerprint,
                explainReceiptId: explainReceiptId,
                ruleEnvironmentDiff: ruleEnvironmentDiff,
                sourceHintAuditToken: sourceHintAuditToken,
                nextSafeAction: "Open character template export when you are ready to save this path."),
            BuildBuildLabGovernedOutput(
                dossier,
                projectionIdSuffix: "json-exchange",
                kind: "json_exchange",
                label: "Governed JSON exchange export",
                summary: "Prepare a governed JSON exchange payload from this build handoff before external handoff or replay ingest.",
                runtimeFingerprint: runtimeFingerprint,
                explainReceiptId: explainReceiptId,
                ruleEnvironmentDiff: ruleEnvironmentDiff,
                sourceHintAuditToken: sourceHintAuditToken,
                nextSafeAction: "Open JSON exchange export before publishing a transfer file."),
            BuildBuildLabGovernedOutput(
                dossier,
                projectionIdSuffix: "foundry-export",
                kind: "foundry_exchange",
                label: "Foundry-class exchange export",
                summary: "Prepare a governed Foundry-class exchange payload from this build handoff.",
                runtimeFingerprint: runtimeFingerprint,
                explainReceiptId: explainReceiptId,
                ruleEnvironmentDiff: ruleEnvironmentDiff,
                sourceHintAuditToken: sourceHintAuditToken,
                nextSafeAction: "Open Foundry exchange export before publishing a transfer file."),
            BuildBuildLabGovernedOutput(
                dossier,
                projectionIdSuffix: "sheet-viewer",
                kind: "sheet_viewer",
                label: "Sheet viewer export check",
                summary: "Review the same handoff in the governed sheet viewer before print/export decisions.",
                runtimeFingerprint: runtimeFingerprint,
                explainReceiptId: explainReceiptId,
                ruleEnvironmentDiff: ruleEnvironmentDiff,
                sourceHintAuditToken: sourceHintAuditToken,
                nextSafeAction: "Open character sheet preview before print or export."),
            BuildBuildLabGovernedOutput(
                dossier,
                projectionIdSuffix: "print-pdf-export",
                kind: "print_pdf_export",
                label: "Print-ready PDF export",
                summary: "Export a governed print-ready PDF from the same handoff without forking rule-environment or explain truth.",
                runtimeFingerprint: runtimeFingerprint,
                explainReceiptId: explainReceiptId,
                ruleEnvironmentDiff: ruleEnvironmentDiff,
                sourceHintAuditToken: sourceHintAuditToken,
                nextSafeAction: "Open PDF export to generate the current print-ready sheet."),
            BuildBuildLabGovernedOutput(
                dossier,
                projectionIdSuffix: "replay-timeline",
                kind: "replay_timeline",
                label: "Replay timeline artifact",
                summary: "Generate a governed replay timeline artifact from this build handoff before contested-turn review or replay publication.",
                runtimeFingerprint: runtimeFingerprint,
                explainReceiptId: explainReceiptId,
                ruleEnvironmentDiff: ruleEnvironmentDiff,
                sourceHintAuditToken: sourceHintAuditToken,
                nextSafeAction: "Open replay timeline export before publishing the replay."),
            BuildBuildLabGovernedOutput(
                dossier,
                projectionIdSuffix: "session-recap",
                kind: "session_recap",
                label: "Session recap artifact",
                summary: "Generate a governed session recap artifact from this build handoff so return, audit, and support closure keep one truth lane.",
                runtimeFingerprint: runtimeFingerprint,
                explainReceiptId: explainReceiptId,
                ruleEnvironmentDiff: ruleEnvironmentDiff,
                sourceHintAuditToken: sourceHintAuditToken,
                nextSafeAction: "Open session recap export before publishing the recap."),
            BuildBuildLabGovernedOutput(
                dossier,
                projectionIdSuffix: "run-module",
                kind: "run_module",
                label: "Run module artifact",
                summary: "Package a governed run-module artifact from this build handoff so prep, exchange, and publication reuse one lineage.",
                runtimeFingerprint: runtimeFingerprint,
                explainReceiptId: explainReceiptId,
                ruleEnvironmentDiff: ruleEnvironmentDiff,
                sourceHintAuditToken: sourceHintAuditToken,
                nextSafeAction: "Open run module export before publishing the module.")
        };

        var carryForwardOutputs = dossier.Projections
            .Concat(workspace?.RecapShelf ?? Array.Empty<PublicationSafeProjection>())
            .Where(static output => !IsBuildLabGovernedOutputKind(output.Kind))
            .Distinct()
            .Take(Math.Max(0, maxOutputs - governedExports.Length));

        return governedExports
            .Concat(carryForwardOutputs)
            .Distinct()
            .Take(maxOutputs)
            .ToArray();
    }

    private static bool IsBuildLabGovernedOutputKind(string? kind)
        => kind?.Trim().ToLowerInvariant() switch
        {
            "character_template" => true,
            "json_exchange" => true,
            "foundry_exchange" => true,
            "sheet_viewer" => true,
            "print_pdf_export" => true,
            "replay_timeline" => true,
            "session_recap" => true,
            "run_module" => true,
            _ => false
        };

    private static readonly string[] RequiredBuildLabOutputKinds =
    [
        "character_template",
        "json_exchange",
        "foundry_exchange",
        "sheet_viewer",
        "print_pdf_export",
        "replay_timeline",
        "session_recap",
        "run_module"
    ];

    private static string BuildBuildLabOutputLaneLabel(string? kind)
        => kind?.Trim().ToLowerInvariant() switch
        {
            "character_template" => "character-template",
            "json_exchange" => "json-exchange",
            "foundry_exchange" => "foundry-exchange",
            "sheet_viewer" => "sheet-viewer",
            "print_pdf_export" => "print-pdf-export",
            "replay_timeline" => "replay-timeline",
            "session_recap" => "session-recap",
            "run_module" => "run-module",
            _ => "governed-output"
        };

    private static string BuildBuildLabOutputLaneCoverageLine(IReadOnlyList<PublicationSafeProjection> outputs)
    {
        List<string> laneStatuses = [];
        foreach (string requiredKind in RequiredBuildLabOutputKinds)
        {
            var output = outputs.FirstOrDefault(item => string.Equals(item.Kind, requiredKind, StringComparison.OrdinalIgnoreCase));
            string status = output is null
                ? "missing"
                : string.Equals(output.PublicationState, "ready", StringComparison.OrdinalIgnoreCase)
                    && string.Equals(output.TrustBand, "governed", StringComparison.OrdinalIgnoreCase)
                    ? "ready"
                    : "review";
            laneStatuses.Add($"{BuildBuildLabOutputLaneLabel(requiredKind)}={status}");
        }

        return $"Output lane coverage: {string.Join("; ", laneStatuses)}.";
    }

    private static PublicationSafeProjection BuildBuildLabGovernedOutput(
        RunnerDossierProjection dossier,
        string projectionIdSuffix,
        string kind,
        string label,
        string summary,
        string runtimeFingerprint,
        string explainReceiptId,
        BuildLabRuleEnvironmentDiffProjection ruleEnvironmentDiff,
        string sourceHintAuditToken,
        string nextSafeAction)
    {
        string laneLabel = BuildBuildLabOutputLaneLabel(kind);
        return new PublicationSafeProjection(
            ProjectionId: StableId("buildlab-output", $"{dossier.DossierId}:{projectionIdSuffix}"),
            Kind: kind,
            Label: label,
            Summary: summary,
            ArtifactId: null,
            Audience: "campaign",
            OwnershipSummary: "build-lab-governed",
            PublicationState: "ready",
            TrustBand: "governed",
            Discoverable: true,
            PublicationSummary: $"Lane {laneLabel} is ready on {runtimeFingerprint} with explain receipt {explainReceiptId}; rule diff {ruleEnvironmentDiff.BeforeFingerprint} -> {ruleEnvironmentDiff.AfterFingerprint} ({ruleEnvironmentDiff.Status}); source hints {sourceHintAuditToken}.",
            CreatorPublicationId: null,
            NextSafeAction: nextSafeAction,
            ProvenanceSummary: $"Explain receipt {explainReceiptId} governs this character follow-through.",
            AuditSummary: $"lane:{kind}; rule-environment:{ruleEnvironmentDiff.BeforeFingerprint}->{ruleEnvironmentDiff.AfterFingerprint} ({ruleEnvironmentDiff.Status}); runtime:{runtimeFingerprint}; explain:{explainReceiptId}; source-hints:{sourceHintAuditToken}",
            CompatibilitySummary: $"Compatibility stays pinned to {runtimeFingerprint} with rule diff {ruleEnvironmentDiff.BeforeFingerprint} -> {ruleEnvironmentDiff.AfterFingerprint} ({ruleEnvironmentDiff.Status}) and source hints {sourceHintAuditToken}.",
            LineageSummary: $"{dossier.DossierId} keeps {kind} on the governed character path with explain receipt {explainReceiptId}.");
    }

    private static BuildLabRuleEnvironmentDiffProjection BuildBuildLabRuleEnvironmentDiff(
        RuleEnvironmentRef dossierRuleEnvironment,
        RuleEnvironmentRef? workspaceRuleEnvironment)
    {
        if (workspaceRuleEnvironment is null)
        {
            return new BuildLabRuleEnvironmentDiffProjection(
                Status: "pending",
                Summary: $"Rule-environment diff is pending: dossier is pinned to {dossierRuleEnvironment.CompatibilityFingerprint} until the first campaign workspace binds the same fingerprint.",
                BeforeFingerprint: dossierRuleEnvironment.CompatibilityFingerprint,
                AfterFingerprint: dossierRuleEnvironment.CompatibilityFingerprint,
                BeforeScope: dossierRuleEnvironment.OwnerScope,
                AfterScope: "campaign-pending",
                Changed: false);
        }

        if (string.Equals(
                dossierRuleEnvironment.CompatibilityFingerprint,
                workspaceRuleEnvironment.CompatibilityFingerprint,
                StringComparison.OrdinalIgnoreCase))
        {
            return new BuildLabRuleEnvironmentDiffProjection(
                Status: "clear",
                Summary: $"Rule-environment diff is clear: dossier and campaign workspace both pin {workspaceRuleEnvironment.CompatibilityFingerprint}.",
                BeforeFingerprint: dossierRuleEnvironment.CompatibilityFingerprint,
                AfterFingerprint: workspaceRuleEnvironment.CompatibilityFingerprint,
                BeforeScope: dossierRuleEnvironment.OwnerScope,
                AfterScope: workspaceRuleEnvironment.OwnerScope,
                Changed: false);
        }

        return new BuildLabRuleEnvironmentDiffProjection(
            Status: "requires_review",
            Summary: $"Rule-environment diff requires review: dossier pins {dossierRuleEnvironment.CompatibilityFingerprint} while campaign workspace pins {workspaceRuleEnvironment.CompatibilityFingerprint}.",
            BeforeFingerprint: dossierRuleEnvironment.CompatibilityFingerprint,
            AfterFingerprint: workspaceRuleEnvironment.CompatibilityFingerprint,
            BeforeScope: dossierRuleEnvironment.OwnerScope,
            AfterScope: workspaceRuleEnvironment.OwnerScope,
            Changed: true);
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
            return "Attach this dossier to a reviewed campaign workspace before you trust the build as the table-safe return path.";
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
            return $"{runtimeFingerprint} is the active compatibility fingerprint, but restore still needs review before the build is campaign-safe.";
        }

        return workspace is null
            ? $"{runtimeFingerprint} is pinned on the living dossier, but the first campaign workspace still needs to confirm the same rule posture."
            : $"{runtimeFingerprint} is pinned across the dossier, workspace, and return path for this build.";
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

    private static string BuildBuildLabCrewFitSummary(
        RunnerDossierProjection dossier,
        CampaignWorkspaceProjection? workspace)
    {
        if (workspace is null)
        {
            return "Crew-fit is pending: attach this build path to a reviewed campaign workspace before role-overlap and roster-fit checks can be grounded.";
        }

        int crewCount = workspace.Crews.Count;
        int crewMemberCount = workspace.Crews.Sum(static crew => crew.Members.Count);
        bool dossierAssigned = workspace.Crews
            .SelectMany(static crew => crew.Members)
            .Any(member => string.Equals(member.DossierId, dossier.DossierId, StringComparison.OrdinalIgnoreCase));

        if (!dossierAssigned)
        {
            return $"{dossier.DisplayName} is not yet assigned to a governed crew lane in {workspace.CampaignName}, so crew-fit still needs review.";
        }

        return $"{dossier.DisplayName} is assigned across {crewCount} crew lane(s) with {crewMemberCount} governed assignment(s) in {workspace.CampaignName}.";
    }

    private static string BuildBuildLabPlannerCoverageSummary(
        RunnerDossierProjection dossier,
        CampaignWorkspaceProjection? workspace,
        IReadOnlyList<PublicationSafeProjection> outputs,
        WorkspaceRestoreProjection restore)
    {
        const int totalCheckpoints = 5;
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

        if (workspace is not null
            && workspace.Crews.SelectMany(static crew => crew.Members)
                .Any(member => string.Equals(member.DossierId, dossier.DossierId, StringComparison.OrdinalIgnoreCase)))
        {
            coveredCheckpoints++;
        }

        return $"{coveredCheckpoints} of {totalCheckpoints} build follow-through checkpoints are already grounded.";
    }

    private static string BuildBuildLabConditionalStateSummary(
        RunnerDossierProjection dossier,
        CampaignWorkspaceProjection? workspace)
    {
        var signals = ResolveBuildLabConditionalStateSignals(dossier, workspace);
        if (signals.Count == 0)
        {
            return workspace is null
                ? "Conditional state rail is pending: attach a campaign workspace to verify drugs, foci, sustained effects, acquisition timing, and reputation spends before final export."
                : $"Conditional state rail in {workspace.CampaignName} is in review: no explicit conditional toggles are active yet, so drugs, foci, sustained effects, acquisition timing, and reputation spends still need explicit checks.";
        }

        string signalSummary = string.Join(", ", signals.Select(signal => signal.label));
        return workspace is null
            ? $"Conditional state rail is attached to the living dossier and currently tracks {signalSummary}."
            : $"Conditional state rail in {workspace.CampaignName} currently tracks {signalSummary}.";
    }

    private static IReadOnlyList<string> BuildBuildLabConditionalStateLines(
        RunnerDossierProjection dossier,
        CampaignWorkspaceProjection? workspace)
    {
        var signals = ResolveBuildLabConditionalStateSignals(dossier, workspace);
        if (signals.Count == 0)
        {
            return
            [
                workspace is null
                    ? "Current conditions: campaign workspace is not attached yet, so state checks are still dossier-first."
                    : "Current conditions: campaign workspace is attached, but explicit conditional toggles are not active yet.",
                "Conditional checks pending: drugs and temporary chemistry modifiers.",
                "Conditional checks pending: foci bonding and sustained effects.",
                "Conditional checks pending: acquisition timing and reputation spends."
            ];
        }

        List<string> lines =
        [
            workspace is null
                ? "Current conditions: living dossier conditions are active before campaign return handoff."
                : $"Current conditions: {workspace.CampaignName} is carrying conditional checks on the reviewed return path."
        ];

        lines.AddRange(signals.Select(static signal => signal.line));
        return lines;
    }

    private static IReadOnlyList<(string key, string label, string line)> ResolveBuildLabConditionalStateSignals(
        RunnerDossierProjection dossier,
        CampaignWorkspaceProjection? workspace)
    {
        var activeEnvironment = workspace?.RuleEnvironment ?? dossier.RuleEnvironment;
        var toggles = activeEnvironment.OptionToggles
            .Concat(activeEnvironment.SourcePacks)
            .Concat(activeEnvironment.HouseRulePacks)
            .Select(static value => value?.Trim().ToLowerInvariant())
            .Where(static value => !string.IsNullOrWhiteSpace(value))
            .Cast<string>()
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();

        List<(string key, string label, string line)> signals = [];
        if (toggles.Any(static token => token.Contains("drug", StringComparison.OrdinalIgnoreCase) || token.Contains("chem", StringComparison.OrdinalIgnoreCase)))
        {
            signals.Add(("drugs", "drug modifiers", "Conditional check: drug and chemistry modifiers stay explicit on this build."));
        }

        if (toggles.Any(static token => token.Contains("focus", StringComparison.OrdinalIgnoreCase) || token.Contains("foci", StringComparison.OrdinalIgnoreCase)))
        {
            signals.Add(("foci", "foci bindings", "Conditional check: focus/foci bonding state is pinned to this build path."));
        }

        if (toggles.Any(static token => token.Contains("sustain", StringComparison.OrdinalIgnoreCase)))
        {
            signals.Add(("sustained", "sustained effects", "Conditional check: sustained effects remain visible instead of collapsing into final totals."));
        }

        if (toggles.Any(static token => token.Contains("acquisition", StringComparison.OrdinalIgnoreCase) || token.Contains("availability", StringComparison.OrdinalIgnoreCase) || token.Contains("downtime", StringComparison.OrdinalIgnoreCase)))
        {
            signals.Add(("acquisition", "acquisition timing", "Conditional check: acquisition timing and availability posture remain reviewable."));
        }

        if (toggles.Any(static token => token.Contains("reputation", StringComparison.OrdinalIgnoreCase) || token.Contains("street_cred", StringComparison.OrdinalIgnoreCase) || token.Contains("notoriety", StringComparison.OrdinalIgnoreCase)))
        {
            signals.Add(("reputation", "reputation spends", "Conditional check: reputation/spend assumptions stay attached to this variant."));
        }

        return signals;
    }

    private static string BuildBuildLabSourceHintSummary(
        RunnerDossierProjection dossier,
        CampaignWorkspaceProjection? workspace)
    {
        var activeEnvironment = workspace?.RuleEnvironment ?? dossier.RuleEnvironment;
        IReadOnlyList<string> sourcePacks = NormalizeBuildLabHintValues(activeEnvironment.SourcePacks);
        IReadOnlyList<string> houseRulePacks = NormalizeBuildLabHintValues(activeEnvironment.HouseRulePacks);
        if (sourcePacks.Count == 0 && houseRulePacks.Count == 0)
        {
            return workspace is null
                ? "Source-linked hints are pending: attach a campaign workspace to confirm source packs and house-rule overlays before final export."
                : $"Source-linked hints in {workspace.CampaignName} need review: no active source packs or house-rule overlays are pinned yet.";
        }

        return workspace is null
            ? $"Source-linked hints on the living dossier pin {sourcePacks.Count} source pack(s) and {houseRulePacks.Count} house-rule overlay(s)."
            : $"Source-linked hints in {workspace.CampaignName} pin {sourcePacks.Count} source pack(s) and {houseRulePacks.Count} house-rule overlay(s).";
    }

    private static IReadOnlyList<string> BuildBuildLabSourceHintLines(
        RunnerDossierProjection dossier,
        CampaignWorkspaceProjection? workspace)
    {
        var activeEnvironment = workspace?.RuleEnvironment ?? dossier.RuleEnvironment;
        IReadOnlyList<string> sourcePacks = NormalizeBuildLabHintValues(activeEnvironment.SourcePacks);
        IReadOnlyList<string> houseRulePacks = NormalizeBuildLabHintValues(activeEnvironment.HouseRulePacks);

        List<string> lines =
        [
            workspace is null
                ? $"Source-linked lane: living dossier is pinned to {activeEnvironment.CompatibilityFingerprint} before campaign return binds."
                : $"Source-linked lane: {workspace.CampaignName} is pinned to {activeEnvironment.CompatibilityFingerprint} for governed return and export."
        ];

        if (sourcePacks.Count > 0)
        {
            lines.Add($"Source-linked hint: source packs -> {DescribeBuildLabHintValues(sourcePacks)}.");
        }

        if (houseRulePacks.Count > 0)
        {
            lines.Add($"Source-linked hint: house-rule overlays -> {DescribeBuildLabHintValues(houseRulePacks)}.");
        }

        if (sourcePacks.Count == 0 && houseRulePacks.Count == 0)
        {
            lines.Add("Source-linked hint: no source packs or house-rule overlays are active yet.");
        }

        return lines;
    }

    private static IReadOnlyList<string> NormalizeBuildLabHintValues(IReadOnlyList<string> values)
        => values
            .Where(static value => !string.IsNullOrWhiteSpace(value))
            .Select(static value => value.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();

    private static string DescribeBuildLabHintValues(IReadOnlyList<string> values)
    {
        if (values.Count <= 3)
        {
            return string.Join(", ", values);
        }

        return $"{string.Join(", ", values.Take(3))} (+{values.Count - 3} more)";
    }

    private static string BuildBuildLabSourceHintAuditToken(RuleEnvironmentRef environment)
    {
        IReadOnlyList<string> sourcePacks = NormalizeBuildLabHintValues(environment.SourcePacks);
        IReadOnlyList<string> houseRulePacks = NormalizeBuildLabHintValues(environment.HouseRulePacks);
        string sourceToken = sourcePacks.Count == 0
            ? "none"
            : string.Join("+", sourcePacks.Select(static value => value.Replace(' ', '_')));
        string houseRuleToken = houseRulePacks.Count == 0
            ? "none"
            : string.Join("+", houseRulePacks.Select(static value => value.Replace(' ', '_')));
        return $"sources:{sourceToken}|house-rules:{houseRuleToken}";
    }

    private static IReadOnlyList<string> BuildBuildLabPlannerCoverageLines(
        RunnerDossierProjection dossier,
        CampaignWorkspaceProjection? workspace,
        IReadOnlyList<PublicationSafeProjection> outputs,
        WorkspaceRestoreProjection restore)
    {
        bool dossierAssignedToCrew = workspace is not null
            && workspace.Crews.SelectMany(static crew => crew.Members)
                .Any(member => string.Equals(member.DossierId, dossier.DossierId, StringComparison.OrdinalIgnoreCase));

        List<string> lines =
        [
            workspace is null
                ? "Campaign continuity: no reviewed campaign workspace is attached yet, so the build still lands on the living dossier first."
                : $"Campaign continuity: {workspace.CampaignName} is already attached as the reviewed return path for this build.",
            outputs.Count switch
            {
                1 => "Outputs: 1 dossier or campaign-safe output is already attached to the build.",
                > 1 => $"Outputs: {outputs.Count} dossier or campaign-safe outputs are already attached to the build.",
                _ => "Outputs: no dossier or campaign-safe output is attached yet, so export, exchange, replay, and recap review is still pending."
            },
            BuildBuildLabOutputLaneCoverageLine(outputs),
            restore.ConflictSummaries.Count switch
            {
                0 => "Restore posture: no restore conflicts are currently blocking replay-safe handoff follow-through.",
                1 => "Restore posture: 1 restore conflict still needs review before the build is replay-safe.",
                _ => $"Restore posture: {restore.ConflictSummaries.Count} restore conflicts still need review before the build is replay-safe."
            },
            restore.ClaimedDevices.Count switch
            {
                0 => "Claimed install: no linked install is attached yet for install-aware follow-through.",
                1 => "Claimed install: 1 linked install is already attached for install-aware follow-through.",
                _ => $"Claimed install: {restore.ClaimedDevices.Count} linked installs are already attached for install-aware follow-through."
            },
            workspace is null
                ? "Crew-fit: no campaign workspace is attached yet, so role-overlap and roster-fit grounding are still pending."
                : dossierAssignedToCrew
                    ? $"Crew-fit: {dossier.DisplayName} is already assigned to a governed crew lane in {workspace.CampaignName}."
                    : $"Crew-fit: {dossier.DisplayName} is not yet assigned to a governed crew lane in {workspace.CampaignName}."
        ];

        return lines
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .ToArray();
    }

    private static string BuildBuildLabSurfaceSummary(
        RunnerDossierProjection dossier,
        CampaignWorkspaceProjection? workspace,
        BuildLabRuleEnvironmentDiffProjection ruleEnvironmentDiff)
    {
        var coverage = ResolveBuildLabSurfaceCoverage(dossier, workspace, ruleEnvironmentDiff);
        int covered = coverage.Count(static lane => lane.status);
        return $"{covered} of 4 build-surface lanes are grounded on one handoff (creation, compare, advancement, crew-fit).";
    }

    private static IReadOnlyList<string> BuildBuildLabSurfaceLines(
        RunnerDossierProjection dossier,
        CampaignWorkspaceProjection? workspace,
        BuildLabRuleEnvironmentDiffProjection ruleEnvironmentDiff)
    {
        var coverage = ResolveBuildLabSurfaceCoverage(dossier, workspace, ruleEnvironmentDiff);
        return coverage
            .Select(static lane => $"{lane.label}: {(lane.status ? "grounded" : "pending")} — {lane.detail}")
            .ToArray();
    }

    private static IReadOnlyList<(string label, bool status, string detail)> ResolveBuildLabSurfaceCoverage(
        RunnerDossierProjection dossier,
        CampaignWorkspaceProjection? workspace,
        BuildLabRuleEnvironmentDiffProjection ruleEnvironmentDiff)
    {
        bool creationGrounded = dossier.BuildReceiptIds.Count > 0;
        bool hasRuleEnvironmentDiffPosture = !string.Equals(ruleEnvironmentDiff.Status, "pending", StringComparison.OrdinalIgnoreCase);
        bool compareGrounded = dossier.Projections.Any(static projection => IsBuildLabCompareProjectionKind(projection.Kind))
            || hasRuleEnvironmentDiffPosture;
        bool advancementGrounded = workspace is not null;
        bool crewFitGrounded = workspace is not null
            && workspace.Crews.SelectMany(static crew => crew.Members)
                .Any(member => string.Equals(member.DossierId, dossier.DossierId, StringComparison.OrdinalIgnoreCase));

        return
        [
            (
                "Creation lane",
                creationGrounded,
                creationGrounded
                    ? $"Build receipts are attached ({dossier.BuildReceiptIds.Count})."
                    : "No build receipt is attached yet."
            ),
            (
                "Compare lane",
                compareGrounded,
                compareGrounded
                    ? "Variant comparison evidence is attached through compare cards or rule-environment diff posture."
                    : "No compare evidence is attached yet."
            ),
            (
                "Advancement lane",
                advancementGrounded,
                advancementGrounded
                    ? $"Campaign workspace {workspace!.CampaignName} is attached for progression planning."
                    : "Campaign workspace is not attached yet."
            ),
            (
                "Crew-fit lane",
                crewFitGrounded,
                crewFitGrounded
                    ? $"{dossier.DisplayName} is assigned to a governed crew lane."
                    : "Runner is not yet assigned to a governed crew lane."
            )
        ];
    }

    private static bool IsBuildLabCompareProjectionKind(string? kind)
    {
        if (string.IsNullOrWhiteSpace(kind))
        {
            return false;
        }

        string normalized = kind.Trim().ToLowerInvariant();
        return normalized.Contains("compare", StringComparison.Ordinal)
            || normalized.Contains("variant", StringComparison.Ordinal)
            || normalized.Contains("build_idea", StringComparison.Ordinal)
            || normalized.Contains("build-idea", StringComparison.Ordinal);
    }

    private static string BuildBuildLabExchangeParitySummary(IReadOnlyList<PublicationSafeProjection> outputs)
    {
        var parity = ResolveBuildLabExchangeParity(outputs);
        int readyCount = parity.Count(static lane => lane.ready);
        return $"{readyCount} of {parity.Count} sheet/print/export/viewer and adjacent exchange parity lanes are release-ready.";
    }

    private static IReadOnlyList<string> BuildBuildLabExchangeParityLines(IReadOnlyList<PublicationSafeProjection> outputs)
        => ResolveBuildLabExchangeParity(outputs)
            .Select(static lane => $"{lane.label}: {(lane.ready ? "ready" : "pending")} — {lane.detail}")
            .ToArray();

    private static IReadOnlyList<(string label, bool ready, string detail)> ResolveBuildLabExchangeParity(IReadOnlyList<PublicationSafeProjection> outputs)
    {
        static (string label, bool ready, string detail) Lane(string label, string kind, IReadOnlyList<PublicationSafeProjection> outputs)
        {
            var output = outputs.FirstOrDefault(item => string.Equals(item.Kind, kind, StringComparison.OrdinalIgnoreCase));
            if (output is null)
            {
                return (label, false, "Required file is missing from this build.");
            }

            bool ready = string.Equals(output.PublicationState, "ready", StringComparison.OrdinalIgnoreCase)
                && string.Equals(output.TrustBand, "governed", StringComparison.OrdinalIgnoreCase);
            return (label, ready, ready
                ? $"Governed {label.ToLowerInvariant()} artifact is attached."
                : $"Artifact is attached but still needs publication/trust review ({output.PublicationState ?? "unknown"} / {output.TrustBand ?? "unknown"}).");
        }

        return
        [
            Lane("Sheet viewer", "sheet_viewer", outputs),
            Lane("Print PDF export", "print_pdf_export", outputs),
            Lane("JSON exchange", "json_exchange", outputs),
            Lane("Foundry exchange", "foundry_exchange", outputs),
            Lane("Character template export", "character_template", outputs)
        ];
    }

    private static string BuildBuildLabPortabilityPillarSummary(IReadOnlyList<PublicationSafeProjection> outputs)
    {
        var lanes = ResolveBuildLabPortabilityPillar(outputs);
        int readyCount = lanes.Count(static lane => lane.ready);
        return $"{readyCount} of {lanes.Count} dossier/exchange/replay/recap/module portability lanes are release-ready.";
    }

    private static IReadOnlyList<string> BuildBuildLabPortabilityPillarLines(IReadOnlyList<PublicationSafeProjection> outputs)
        => ResolveBuildLabPortabilityPillar(outputs)
            .Select(static lane => $"{lane.label}: {(lane.ready ? "ready" : "pending")} — {lane.detail}")
            .ToArray();

    private static IReadOnlyList<(string label, bool ready, string detail)> ResolveBuildLabPortabilityPillar(IReadOnlyList<PublicationSafeProjection> outputs)
    {
        static (string label, bool ready, string detail) Lane(string label, string kind, IReadOnlyList<PublicationSafeProjection> outputs)
        {
            var output = outputs.FirstOrDefault(item => string.Equals(item.Kind, kind, StringComparison.OrdinalIgnoreCase));
            if (output is null)
            {
                return (label, false, "Required file is missing from this build.");
            }

            bool ready = string.Equals(output.PublicationState, "ready", StringComparison.OrdinalIgnoreCase)
                && string.Equals(output.TrustBand, "governed", StringComparison.OrdinalIgnoreCase);
            return (label, ready, ready
                ? $"Governed {label.ToLowerInvariant()} artifact is attached."
                : $"Artifact is attached but still needs publication/trust review ({output.PublicationState ?? "unknown"} / {output.TrustBand ?? "unknown"}).");
        }

        return
        [
            Lane("Dossier exchange", "character_template", outputs),
            Lane("JSON exchange", "json_exchange", outputs),
            Lane("Foundry exchange", "foundry_exchange", outputs),
            Lane("Replay timeline", "replay_timeline", outputs),
            Lane("Session recap", "session_recap", outputs),
            Lane("Run module", "run_module", outputs)
        ];
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

    private static CampaignAdoptionRecordProjection BuildCampaignAdoptionRecordProjection(
        CampaignWorkspaceProjection workspace,
        CampaignAdoptionProjection adoption)
    {
        string status = adoption.SafeToPlay
            ? "playable_with_review"
            : adoption.ExplicitUnknowns.Count == 0
                ? "review_required"
                : "history_gaps_open";

        return new CampaignAdoptionRecordProjection(
            AdoptionId: adoption.AdoptionId,
            WorkspaceId: adoption.WorkspaceId,
            CampaignId: adoption.CampaignId,
            CampaignName: workspace.CampaignName,
            Status: status,
            SafeToPlay: adoption.SafeToPlay,
            ConfidencePercent: adoption.ConfidencePercent,
            Known: new CampaignAdoptionKnownCountsProjection(
                Runners: adoption.RunnerCount,
                ActiveJobs: adoption.ActiveJobCount,
                Contacts: adoption.ContactCount,
                HouseRules: adoption.HouseRuleCount),
            UnknownHistoryMarkers: adoption.ExplicitUnknowns,
            RecommendedNextActions: adoption.RecommendedNextActions,
            Summary: adoption.Summary,
            NextBestCleanupAction: adoption.NextSafeAction,
            EvidenceLines: adoption.EvidenceLines,
            InitiatedByUserId: adoption.UpdatedByUserId,
            AdoptedAtUtc: adoption.UpdatedAtUtc);
    }

    private static CampaignAdoptionRunnerGoalProjection BuildCampaignAdoptionRunnerGoalProjection(RunnerGoalProjection goal)
        => new(
            GoalId: goal.GoalId,
            WorkspaceId: goal.WorkspaceId,
            CampaignId: goal.CampaignId,
            DossierId: goal.DossierId,
            RunnerHandle: goal.RunnerHandle,
            GoalTitle: goal.Label,
            Status: goal.ApprovalStatus,
            UpdateKind: goal.TargetKind,
            Summary: $"{goal.Label} targets {goal.TargetKind} / {goal.TargetReference}. {goal.NextSafeAction}",
            EvidenceLines: goal.EvidenceLines,
            InitiatedByUserId: goal.UpdatedByUserId,
            UpdatedAtUtc: goal.UpdatedAtUtc);

    private static WorldChangeProjection BuildCampaignAdoptionWorldChangeProjection(
        string kind,
        string subject,
        int delta,
        string summary)
        => new(
            Kind: kind,
            Subject: subject,
            Delta: delta,
            Summary: summary);

    private static CampaignAdoptionWorldTickProjection BuildCampaignAdoptionWorldTickProjection(
        CampaignWorkspaceProjection workspace,
        WorldTickProjection worldTick)
        => new(
            WorldTickId: worldTick.WorldTickId,
            WorkspaceId: worldTick.WorkspaceId,
            CampaignId: worldTick.CampaignId,
            CampaignName: workspace.CampaignName,
            WorldRef: workspace.CampaignId,
            TickRef: worldTick.RunId,
            Summary: worldTick.Summary,
            CauseRefs: FinalizeLines([worldTick.RunId, worldTick.RunTitle]),
            Changes:
            [
                BuildCampaignAdoptionWorldChangeProjection(
                    kind: "world_tick",
                    subject: worldTick.RunTitle,
                    delta: 0,
                    summary: worldTick.ConsequenceSummary)
            ],
            HeatDelta: 0,
            GmApproved: true,
            SpoilerPolicy: "player_safe_preview_only",
            EvidenceLines: worldTick.EvidenceLines,
            InitiatedByUserId: worldTick.UpdatedByUserId,
            CreatedAtUtc: worldTick.UpdatedAtUtc,
            WorldFrameId: worldTick.WorldFrameId,
            WorldReceiptRef: worldTick.WorldReceiptRef,
            ShadowfeedBulletinId: worldTick.ShadowfeedBulletinId,
            ShadowfeedBulletinReceiptRef: worldTick.ShadowfeedBulletinReceiptRef);

    private static CampaignAdoptionResolutionReportProjection BuildCampaignAdoptionResolutionReportProjection(
        CampaignWorkspaceProjection workspace,
        ResolutionReportApprovalProjection approval,
        IReadOnlyList<WorldTickProjection> worldTicks)
    {
        WorldTickProjection? matchingWorldTick = worldTicks
            .FirstOrDefault(item => string.Equals(item.WorldTickId, approval.WorldTickId, StringComparison.OrdinalIgnoreCase));

        WorldChangeProjection[] deltas = matchingWorldTick is null
            ? Array.Empty<WorldChangeProjection>()
            : [
                BuildCampaignAdoptionWorldChangeProjection(
                    kind: "world_tick",
                    subject: matchingWorldTick.RunTitle,
                    delta: 0,
                    summary: matchingWorldTick.ConsequenceSummary)
            ];

        return new CampaignAdoptionResolutionReportProjection(
            ApprovalId: approval.ApprovalId,
            WorkspaceId: approval.WorkspaceId,
            CampaignId: approval.CampaignId,
            CampaignName: workspace.CampaignName,
            DraftPackageId: approval.ApprovalId,
            RunId: approval.RunId,
            RunTitle: approval.RunTitle,
            Status: "approved",
            Outcomes: FinalizeLines([approval.Summary]),
            Deltas: deltas,
            HeatDelta: 0,
            Summary: approval.Summary,
            EvidenceLines: approval.EvidenceLines,
            WorldTickId: approval.WorldTickId,
            NewsItemId: approval.NewsId,
            InitiatedByUserId: approval.UpdatedByUserId,
            ApprovedAtUtc: approval.UpdatedAtUtc,
            WorldResolutionReportId: approval.WorldResolutionReportId,
            WorldFrameId: approval.WorldFrameId,
            ShadowfeedBulletinId: approval.ShadowfeedBulletinId,
            ResolutionConsequenceBridgeId: approval.ResolutionConsequenceBridgeId,
            ApprovalReceiptRef: approval.ApprovalReceiptRef);
    }

    private static PlayerSafeNewsItemProjection BuildPlayerSafeNewsItemProjection(
        CampaignWorkspaceProjection workspace,
        PlayerSafeNewsProjection newsItem)
        => new(
            NewsItemId: newsItem.NewsId,
            WorkspaceId: newsItem.WorkspaceId,
            CampaignId: newsItem.CampaignId,
            CampaignName: workspace.CampaignName,
            Visibility: "player_safe_preview_only",
            Headline: newsItem.Title,
            Summary: newsItem.Summary,
            SourceRefs: FinalizeLines([newsItem.Source, newsItem.Url, newsItem.WorldTickId]),
            SpoilerLevel: newsItem.SpoilerPolicy,
            EvidenceLines: newsItem.EvidenceLines,
            InitiatedByUserId: newsItem.UpdatedByUserId,
            PublishedAtUtc: newsItem.UpdatedAtUtc,
            ShadowfeedBulletinId: newsItem.BulletinId,
            ShadowfeedBulletinReceiptRef: newsItem.BulletinReceiptRef);

    private static CampaignAdoptionLoopProjection? BuildCampaignAdoptionLoopProjection(
        string workspaceId,
        CampaignProjection campaign,
        IReadOnlyList<CampaignAdoptionProjection> campaignAdoptions,
        IReadOnlyList<RunnerGoalProjection> runnerGoals,
        IReadOnlyList<ResolutionReportApprovalProjection> resolutionReportApprovals,
        IReadOnlyList<WorldTickProjection> worldTicks,
        IReadOnlyList<PlayerSafeNewsProjection> playerSafeNews)
    {
        CampaignAdoptionProjection? adoption = campaignAdoptions
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        RunnerGoalProjection[] orderedGoals = runnerGoals
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
        ResolutionReportApprovalProjection? approval = resolutionReportApprovals
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        WorldTickProjection[] orderedWorldTicks = worldTicks
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
        PlayerSafeNewsProjection[] orderedPlayerSafeNews = playerSafeNews
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
        if (adoption is null
            && orderedGoals.Length == 0
            && approval is null
            && orderedWorldTicks.Length == 0
            && orderedPlayerSafeNews.Length == 0)
        {
            return null;
        }

        DateTimeOffset updatedAtUtc = new[]
            {
                adoption?.UpdatedAtUtc,
                orderedGoals.FirstOrDefault()?.UpdatedAtUtc,
                approval?.UpdatedAtUtc,
                orderedWorldTicks.FirstOrDefault()?.UpdatedAtUtc,
                orderedPlayerSafeNews.FirstOrDefault()?.UpdatedAtUtc
            }
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(DateTimeOffset.UtcNow)
            .Max();
        string nextSafeAction = approval?.NextSafeAction
            ?? orderedGoals.FirstOrDefault()?.NextSafeAction
            ?? adoption?.NextSafeAction
            ?? "Open the reviewed workspace return on /account/work.";
        string summary = approval is not null
            ? $"{campaign.Name} keeps campaign adoption, runner-goal pins, ResolutionReport closeout, and the first BLACK LEDGER WorldTick on one reviewed return path."
            : adoption is not null && orderedGoals.Length > 0
                ? $"{campaign.Name} keeps campaign adoption and {orderedGoals.Length} runner-goal pin(s) on one reviewed return path."
                : adoption?.Summary
                    ?? $"{campaign.Name} keeps the adoption loop attached to the shared workspace.";

        return new CampaignAdoptionLoopProjection(
            WorkspaceId: workspaceId,
            CampaignId: campaign.CampaignId,
            Summary: summary,
            NextSafeAction: nextSafeAction,
            Adoption: adoption,
            RunnerGoals: orderedGoals,
            ResolutionReportApproval: approval,
            WorldTicks: orderedWorldTicks,
            PlayerSafeNews: orderedPlayerSafeNews,
            EvidenceLines: FinalizeLines(
            new[]
            {
                adoption?.Summary ?? string.Empty,
                adoption is null ? string.Empty : $"Adoption confidence: {adoption.ConfidencePercent}% with {(adoption.SafeToPlay ? "safe-to-play" : "not-safe-yet")} posture.",
                orderedGoals.FirstOrDefault() is null ? string.Empty : $"{orderedGoals[0].RunnerHandle}: {orderedGoals[0].Label}.",
                approval?.Summary ?? string.Empty,
                orderedWorldTicks.FirstOrDefault()?.Summary ?? string.Empty,
                orderedPlayerSafeNews.FirstOrDefault() is null ? string.Empty : $"{orderedPlayerSafeNews[0].Title}: {orderedPlayerSafeNews[0].Summary}",
                $"Next safe action: {nextSafeAction}"
            }),
            UpdatedAtUtc: updatedAtUtc);
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
        IReadOnlyList<AftermathRecapPackageProjection> aftermathPackages,
        CampaignAdoptionLoopProjection? campaignAdoptionLoop)
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
        CampaignAdoptionProjection? leadAdoption = campaignAdoptionLoop?.Adoption;
        RunnerGoalProjection? leadRunnerGoal = campaignAdoptionLoop?.RunnerGoals
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        ResolutionReportApprovalProjection? leadResolutionApproval = campaignAdoptionLoop?.ResolutionReportApproval;
        WorldTickProjection? leadWorldTick = campaignAdoptionLoop?.WorldTicks
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        PlayerSafeNewsProjection? leadPlayerSafeNews = campaignAdoptionLoop?.PlayerSafeNews
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();

        if (continuity is null
            && leadConsequence is null
            && leadPrepLaunch is null
            && leadTravelPrefetch is null
            && leadAftermathPackage is null
            && leadAdoption is null
            && leadRunnerGoal is null
            && leadResolutionApproval is null
            && leadWorldTick is null
            && leadPlayerSafeNews is null
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
        else if (leadResolutionApproval is not null && leadWorldTick is not null)
        {
            summary = $"{leadWorldTick.Summary} stays pinned with player-safe follow-through before {leadRun?.Title ?? campaign.Name} resumes.";
        }
        else if (leadRunnerGoal is not null)
        {
            summary = $"{leadRunnerGoal.RunnerHandle} keeps {leadRunnerGoal.Label} pinned for the next governed return.";
        }
        else if (leadAdoption is not null)
        {
            summary = leadAdoption.Summary;
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
                leadAftermathPackage?.GeneratedAtUtc,
                leadAdoption?.UpdatedAtUtc,
                leadRunnerGoal?.UpdatedAtUtc,
                leadResolutionApproval?.UpdatedAtUtc,
                leadWorldTick?.UpdatedAtUtc,
                leadPlayerSafeNews?.UpdatedAtUtc
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
        IReadOnlyList<string> returnLoopEvidenceLines = BuildGovernedConsequenceReturnLoopEvidenceLines(consequences);

        return new NextSessionCarryForwardProjection(
            CarryForwardId: StableId("next-session", $"{campaign.CampaignId}:{updatedAtUtc.ToUnixTimeMilliseconds()}"),
            Label: "Next-session carry-forward",
            Summary: summary,
            ReturnSummary: continuity?.Summary ?? campaign.Summary,
            NextSafeAction: nextSafeAction,
            EvidenceLines: FinalizeLines(
            new[] { continuity?.Summary ?? campaign.Summary }
            .Concat(returnLoopEvidenceLines)
            .Concat(new[]
            {
                activeScene is null ? string.Empty : $"{activeScene.Title} is live on {leadRun?.Title ?? campaign.Name} at {activeScene.Revision}.",
                leadObjective is null ? string.Empty : $"{leadObjective.Title} stays {leadObjective.Status} with {leadObjective.Pressure} pressure.",
                leadAftermathPackage is null ? string.Empty : $"{leadAftermathPackage.Title}: {leadAftermathPackage.Summary}",
                campaignAdoptionLoop?.Summary ?? string.Empty,
                leadRunnerGoal is null ? string.Empty : $"{leadRunnerGoal.RunnerHandle}: {leadRunnerGoal.Label} ({leadRunnerGoal.SavedNuyen}/{leadRunnerGoal.NuyenRequired} nuyen).",
                leadResolutionApproval?.Summary ?? string.Empty,
                leadWorldTick?.Summary ?? string.Empty,
                leadPlayerSafeNews is null ? string.Empty : $"{leadPlayerSafeNews.Title}: {leadPlayerSafeNews.Summary}",
                leadConsequence?.EvidenceLines.FirstOrDefault() ?? leadConsequence?.Summary ?? string.Empty,
                prepBindingSummary,
                travelSummary,
                nextSafeAction
            })),
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
        NextSessionCarryForwardProjection? nextSessionCarryForward,
        CampaignAdoptionLoopProjection? campaignAdoptionLoop)
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
        CampaignAdoptionProjection? leadAdoption = campaignAdoptionLoop?.Adoption;
        RunnerGoalProjection? leadRunnerGoal = campaignAdoptionLoop?.RunnerGoals
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        WorldTickProjection? leadWorldTick = campaignAdoptionLoop?.WorldTicks
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        PlayerSafeNewsProjection? leadPlayerSafeNews = campaignAdoptionLoop?.PlayerSafeNews
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();

        if (continuity is null
            && nextSessionCarryForward is null
            && leadConsequence is null
            && leadTransfer is null
            && leadPrepLaunch is null
            && leadTravelPrefetch is null
            && leadAftermathPackage is null
            && leadDowntimePackage is null
            && leadAdoption is null
            && leadRunnerGoal is null
            && leadWorldTick is null
            && leadPlayerSafeNews is null
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
                leadAdoption?.UpdatedAtUtc,
                leadRunnerGoal?.UpdatedAtUtc,
                leadWorldTick?.UpdatedAtUtc,
                leadPlayerSafeNews?.UpdatedAtUtc,
                activeScene?.UpdatedAtUtc,
                leadObjective?.UpdatedAtUtc
            }
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(DateTimeOffset.UtcNow)
            .Max();
        IReadOnlyList<string> returnLoopEvidenceLines = BuildGovernedConsequenceReturnLoopEvidenceLines(consequences);

        return new CampaignMemoryProjection(
            MemoryId: StableId("campaign-memory", $"{campaign.CampaignId}:{updatedAtUtc.ToUnixTimeMilliseconds()}"),
            Label: "Campaign memory",
            Summary: BuildCampaignMemorySummary(campaign.Name, nextSessionCarryForward, leadConsequence, leadTransfer, leadPrepLaunch, leadTravelPrefetch, leadAftermathPackage, leadDowntimePackage, leadAdoption, leadRunnerGoal, leadWorldTick, leadPlayerSafeNews),
            ReturnSummary: nextSessionCarryForward?.ReturnSummary ?? continuity?.Summary ?? campaign.Summary,
            NextSafeAction: nextSessionCarryForward?.NextSafeAction ?? nextSafeAction,
            EvidenceLines: FinalizeLines(
            new[] { continuity?.Summary ?? campaign.Summary }
            .Concat(returnLoopEvidenceLines)
            .Concat(new[]
            {
                activeScene is null ? string.Empty : $"{activeScene.Title} is still live on {(leadRun?.Title ?? campaign.Name)} at {activeScene.Revision}.",
                leadObjective is null ? string.Empty : $"{leadObjective.Title} remains {leadObjective.Status} with {leadObjective.Pressure} pressure.",
                nextSessionCarryForward?.Summary ?? string.Empty,
                leadAftermathPackage is null ? string.Empty : $"{leadAftermathPackage.Title}: {leadAftermathPackage.Summary}",
                leadDowntimePackage is null ? string.Empty : $"{leadDowntimePackage.Title}: {leadDowntimePackage.Summary}",
                campaignAdoptionLoop?.Summary ?? string.Empty,
                leadRunnerGoal is null ? string.Empty : $"{leadRunnerGoal.RunnerHandle}: {leadRunnerGoal.Label}.",
                leadWorldTick?.Summary ?? string.Empty,
                leadPlayerSafeNews is null ? string.Empty : $"{leadPlayerSafeNews.Title}: {leadPlayerSafeNews.Summary}",
                leadConsequence is null ? string.Empty : $"{leadConsequence.Label}: {leadConsequence.Summary}",
                leadTransfer?.Summary ?? string.Empty,
                leadPrepLaunch?.Summary ?? string.Empty,
                leadTravelPrefetch?.PrefetchSummary ?? string.Empty,
                nextSessionCarryForward?.NextSafeAction ?? nextSafeAction
            })),
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
        AftermathRecapPackageProjection? leadDowntimePackage,
        CampaignAdoptionProjection? leadAdoption,
        RunnerGoalProjection? leadRunnerGoal,
        WorldTickProjection? leadWorldTick,
        PlayerSafeNewsProjection? leadPlayerSafeNews)
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

        if (leadAdoption is not null)
        {
            anchors.Add("adoption wizard");
        }

        if (leadRunnerGoal is not null)
        {
            anchors.Add("runner goal pins");
        }

        if (leadWorldTick is not null)
        {
            anchors.Add("BLACK LEDGER world turn");
        }

        if (leadPlayerSafeNews is not null)
        {
            anchors.Add("player-safe news");
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
        NextSessionCarryForwardProjection? nextSessionCarryForward,
        CampaignAdoptionLoopProjection? campaignAdoptionLoop)
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

        if (leadRun?.RunboardContinuity is not null)
        {
            string continuityId = ResolveChangePacketIdentity(
                leadRun.RunboardContinuity.ContinuityId,
                StableId("runboard-continuity", campaign.CampaignId));
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:runboard:{continuityId}"),
                Kind: "runboard_continuity",
                Label: "Runboard continuity",
                Summary: leadRun.RunboardContinuity.Summary,
                UpdatedAtUtc: leadRun.RunboardContinuity.UpdatedAtUtc));
        }

        if (campaignAdoptionLoop?.Adoption is not null)
        {
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:campaign-adoption:{campaignAdoptionLoop.Adoption.AdoptionId}"),
                Kind: "campaign_adoption",
                Label: "Campaign adoption",
                Summary: campaignAdoptionLoop.Adoption.Summary,
                UpdatedAtUtc: campaignAdoptionLoop.Adoption.UpdatedAtUtc));
        }

        RunnerGoalProjection? runnerGoal = campaignAdoptionLoop?.RunnerGoals
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        if (runnerGoal is not null)
        {
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:runner-goal:{runnerGoal.GoalId}"),
                Kind: "runner_goal",
                Label: "Runner goal pin",
                Summary: $"{runnerGoal.RunnerHandle}: {runnerGoal.Label}.",
                UpdatedAtUtc: runnerGoal.UpdatedAtUtc));
        }

        if (campaignAdoptionLoop?.ResolutionReportApproval is not null)
        {
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:resolution-approval:{campaignAdoptionLoop.ResolutionReportApproval.ApprovalId}"),
                Kind: "resolution_report_approval",
                Label: "ResolutionReport approval",
                Summary: campaignAdoptionLoop.ResolutionReportApproval.Summary,
                UpdatedAtUtc: campaignAdoptionLoop.ResolutionReportApproval.UpdatedAtUtc));
        }

        WorldTickProjection? worldTick = campaignAdoptionLoop?.WorldTicks
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        if (worldTick is not null)
        {
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:world-tick:{worldTick.WorldTickId}"),
                Kind: "world_tick",
                Label: "WorldTick",
                Summary: worldTick.Summary,
                UpdatedAtUtc: worldTick.UpdatedAtUtc));
        }

        PlayerSafeNewsProjection? playerSafeNews = campaignAdoptionLoop?.PlayerSafeNews
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        if (playerSafeNews is not null)
        {
            packets.Add(new WorkspaceChangePacketProjection(
                PacketId: StableId("packet", $"{campaign.CampaignId}:player-safe-news:{playerSafeNews.NewsId}"),
                Kind: "player_safe_news",
                Label: playerSafeNews.Title,
                Summary: playerSafeNews.Summary,
                UpdatedAtUtc: playerSafeNews.UpdatedAtUtc));
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

    private static PublicationSafeProjection BuildPlayerSafeNewsRecapShelfProjection(PlayerSafeNewsProjection item)
        => new(
            ProjectionId: item.NewsId,
            Kind: "player_safe_news",
            Label: item.Title,
            Summary: item.Summary,
            ArtifactId: item.NewsId,
            Audience: "campaign, creator",
            OwnershipSummary: "Player-safe news preview stays attached to the shared campaign return without becoming world state.",
            PublicationState: "preview_ready",
            TrustBand: "player-safe-preview",
            Discoverable: false,
            PublicationSummary: item.PublicationSummary,
            NextSafeAction: "Review the player-safe preview before you reopen the shared runboard.",
            ProvenanceSummary: $"{item.Source} preview stays anchored to WorldTick {item.WorldTickId}.",
            AuditSummary: item.SpoilerPolicy,
            CompatibilitySummary: "Player-safe preview only; rendered news remains separate from world state.",
            LineageSummary: $"WorldTick lineage: {item.WorldTickId}.");

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
            ?? "Continuity: reviewed return path remains attached to the same campaign spine.";
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

    private OpenRunOrchestrationProjection BuildOpenRunOrchestrationLocked(OpenRunListingProjection listing)
    {
        OpenRunJoinRequestProjection[] joinRequests = _store.OpenRunJoinRequests
            .Where(item => string.Equals(item.OpenRunId, listing.OpenRunId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
        OpenRunRosterEntryProjection[] roster = _store.OpenRunRoster
            .Where(item => string.Equals(item.OpenRunId, listing.OpenRunId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
        OpenRunScheduleReceiptProjection? schedule = _store.OpenRunSchedules
            .Where(item => string.Equals(item.OpenRunId, listing.OpenRunId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.ScheduledAtUtc)
            .FirstOrDefault();
        OpenRunMeetingHandoffProjection? handoff = _store.OpenRunMeetingHandoffs
            .Where(item => string.Equals(item.OpenRunId, listing.OpenRunId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.CreatedAtUtc)
            .FirstOrDefault();
        OpenRunCloseoutProjection? closeout = _store.OpenRunCloseouts
            .Where(item => string.Equals(item.OpenRunId, listing.OpenRunId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.ClosedAtUtc)
            .FirstOrDefault();

        return new OpenRunOrchestrationProjection(
            Listing: listing,
            JoinRequests: joinRequests,
            Roster: roster,
            Schedule: schedule,
            MeetingHandoff: handoff,
            Closeout: closeout);
    }

    private static bool IsOpenRunVisibleToUser(
        OpenRunListingProjection listing,
        string userId,
        IReadOnlySet<string> accessibleCampaignIds,
        IReadOnlyList<OpenRunJoinRequestProjection> joinRequests,
        IReadOnlyList<OpenRunRosterEntryProjection> roster)
    {
        if (string.Equals(listing.CreatedByUserId, userId, StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        if (accessibleCampaignIds.Contains(listing.CampaignId))
        {
            return true;
        }

        if (joinRequests.Any(item =>
                string.Equals(item.OpenRunId, listing.OpenRunId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.ApplicantUserId, userId, StringComparison.OrdinalIgnoreCase)))
        {
            return true;
        }

        if (roster.Any(item =>
                string.Equals(item.OpenRunId, listing.OpenRunId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.UserId, userId, StringComparison.OrdinalIgnoreCase)))
        {
            return true;
        }

        return AccountService.NormalizeOptional(listing.Visibility)?.ToLowerInvariant() switch
        {
            "community" => true,
            "public" => true,
            "public_preview" => true,
            _ => false
        };
    }

    private static void UpsertOpenRunListingLocked(CommunityStore store, OpenRunListingProjection listing)
    {
        store.OpenRuns.RemoveAll(item => string.Equals(item.OpenRunId, listing.OpenRunId, StringComparison.OrdinalIgnoreCase));
        store.OpenRuns.Add(listing);
        store.OpenRuns.Sort(static (left, right) => right.UpdatedAtUtc.CompareTo(left.UpdatedAtUtc));
        if (store.OpenRuns.Count > 128)
        {
            store.OpenRuns.RemoveRange(128, store.OpenRuns.Count - 128);
        }
    }

    private static void UpsertOpenRunJoinRequestLocked(CommunityStore store, OpenRunJoinRequestProjection joinRequest)
    {
        store.OpenRunJoinRequests.RemoveAll(item => string.Equals(item.RequestId, joinRequest.RequestId, StringComparison.OrdinalIgnoreCase));
        store.OpenRunJoinRequests.Add(joinRequest);
        store.OpenRunJoinRequests.Sort(static (left, right) => right.UpdatedAtUtc.CompareTo(left.UpdatedAtUtc));
        if (store.OpenRunJoinRequests.Count > 256)
        {
            store.OpenRunJoinRequests.RemoveRange(256, store.OpenRunJoinRequests.Count - 256);
        }
    }

    private static void UpsertOpenRunScheduleLocked(CommunityStore store, OpenRunScheduleReceiptProjection schedule)
    {
        store.OpenRunSchedules.RemoveAll(item => string.Equals(item.ReceiptId, schedule.ReceiptId, StringComparison.OrdinalIgnoreCase));
        store.OpenRunSchedules.Add(schedule);
        store.OpenRunSchedules.Sort(static (left, right) => right.ScheduledAtUtc.CompareTo(left.ScheduledAtUtc));
        if (store.OpenRunSchedules.Count > 128)
        {
            store.OpenRunSchedules.RemoveRange(128, store.OpenRunSchedules.Count - 128);
        }
    }

    private static void UpsertOpenRunMeetingHandoffLocked(CommunityStore store, OpenRunMeetingHandoffProjection handoff)
    {
        store.OpenRunMeetingHandoffs.RemoveAll(item => string.Equals(item.HandoffId, handoff.HandoffId, StringComparison.OrdinalIgnoreCase));
        store.OpenRunMeetingHandoffs.Add(handoff);
        store.OpenRunMeetingHandoffs.Sort(static (left, right) => right.CreatedAtUtc.CompareTo(left.CreatedAtUtc));
        if (store.OpenRunMeetingHandoffs.Count > 128)
        {
            store.OpenRunMeetingHandoffs.RemoveRange(128, store.OpenRunMeetingHandoffs.Count - 128);
        }
    }

    private static void UpsertOpenRunCloseoutLocked(CommunityStore store, OpenRunCloseoutProjection closeout)
    {
        store.OpenRunCloseouts.RemoveAll(item => string.Equals(item.CloseoutId, closeout.CloseoutId, StringComparison.OrdinalIgnoreCase));
        store.OpenRunCloseouts.Add(closeout);
        store.OpenRunCloseouts.Sort(static (left, right) => right.ClosedAtUtc.CompareTo(left.ClosedAtUtc));
        if (store.OpenRunCloseouts.Count > 128)
        {
            store.OpenRunCloseouts.RemoveRange(128, store.OpenRunCloseouts.Count - 128);
        }
    }

    private static CampaignConsequenceProjection BuildGovernedCampaignConsequenceProjection(
        CampaignWorkspaceProjection workspace,
        string normalizedKind,
        string normalizedState,
        string normalizedSummary,
        string? returnLoopAction,
        string? returnLoopRoute,
        string? note,
        DateTimeOffset observedAtUtc)
    {
        string label = ResolveGovernedConsequenceLabel(normalizedKind);
        string normalizedAction = AccountService.NormalizeOptional(returnLoopAction) ?? ResolveGovernedConsequenceReturnLoopAction(normalizedKind);
        string? normalizedRoute = NormalizeGovernedConsequenceReturnLoopRoute(normalizedKind, returnLoopRoute);

        return new CampaignConsequenceProjection(
            ConsequenceId: StableId("consequence", $"{workspace.CampaignId}:{normalizedKind}"),
            Kind: normalizedKind,
            Label: label,
            State: normalizedState,
            Summary: normalizedSummary,
            EvidenceLines: FinalizeLines(
            [
                normalizedSummary,
                $"Return-loop action: {normalizedAction}.",
                $"Return-loop route: {normalizedRoute}.",
                $"Workspace: {workspace.CampaignName}.",
                note is null ? string.Empty : $"Operator note: {note}"
            ]),
            Receipts:
            [
                CampaignConsequence(
                    ReceiptId: StableId("consequence-update", $"{workspace.WorkspaceId}:{normalizedKind}:{observedAtUtc.ToUnixTimeMilliseconds()}"),
                    SourceKind: GovernedConsequenceUpdateSourceKind,
                    Summary: normalizedSummary),
                CampaignConsequence(
                    ReceiptId: StableId("consequence-return-loop-action", $"{workspace.WorkspaceId}:{normalizedKind}:{normalizedAction}"),
                    SourceKind: ReturnLoopActionSourceKind,
                    Summary: normalizedAction),
                CampaignConsequence(
                    ReceiptId: normalizedRoute,
                    SourceKind: ReturnLoopRouteSourceKind,
                    Summary: $"Return-loop route: {normalizedRoute}.")
            ],
            UpdatedAtUtc: observedAtUtc);
    }

    private static CampaignConsequenceProjection? BuildAftermathConsequenceProjection(
        CampaignWorkspaceProjection workspace,
        RunProjection? run,
        AftermathRecapPackageProjection package)
    {
        string normalizedPackageKind = NormalizeAftermathPackageKind(package.PackageKind);
        string? normalizedKind = normalizedPackageKind switch
        {
            "downtime_brief" => "downtime",
            "session_recap" or "after_action_report" or "replay_timeline" => "aftermath",
            _ => null
        };
        if (normalizedKind is null)
        {
            return null;
        }

        string label = string.Equals(normalizedKind, "downtime", StringComparison.OrdinalIgnoreCase)
            ? "Downtime posture"
            : "Aftermath posture";
        string state = string.Equals(normalizedKind, "downtime", StringComparison.OrdinalIgnoreCase)
            ? "queued"
            : "reviewable";
        string summary = string.Equals(normalizedKind, "downtime", StringComparison.OrdinalIgnoreCase)
            ? $"{package.Title} keeps downtime obligations reviewable for {run?.Title ?? workspace.CampaignName}."
            : $"{package.Title} keeps aftermath follow-through reviewable for {run?.Title ?? workspace.CampaignName}.";

        var evidenceLines = new List<string>(package.EvidenceLines);
        if (string.Equals(normalizedKind, "downtime", StringComparison.OrdinalIgnoreCase)
            || string.Equals(normalizedKind, "aftermath", StringComparison.OrdinalIgnoreCase))
        {
            evidenceLines.Add("Return-loop route: /account/work#aftermath-packages.");
        }

        evidenceLines.Add("Return-loop action: Review downtime obligations.");

        return new CampaignConsequenceProjection(
            ConsequenceId: StableId("consequence", $"{workspace.CampaignId}:{normalizedKind}"),
            Kind: normalizedKind,
            Label: label,
            State: state,
            Summary: summary,
            EvidenceLines: FinalizeLines(evidenceLines),
            Receipts:
            [
                CampaignConsequence(
                    ReceiptId: package.PackageId,
                    SourceKind: GovernedAftermathPackageSourceKind,
                    Summary: package.Summary),
                CampaignConsequence(
                    ReceiptId: StableId("consequence-return-loop-action", $"{workspace.WorkspaceId}:{normalizedKind}:review_downtime_obligations"),
                    SourceKind: ReturnLoopActionSourceKind,
                    Summary: "Review downtime obligations"),
                CampaignConsequence(
                    ReceiptId: "/account/work#aftermath-packages",
                    SourceKind: ReturnLoopRouteSourceKind,
                    Summary: "Return-loop route: /account/work#aftermath-packages.")
            ],
            UpdatedAtUtc: package.GeneratedAtUtc);
    }

    private static IReadOnlyList<CampaignConsequenceProjection> UpsertGovernedCampaignConsequence(
        IReadOnlyList<CampaignConsequenceProjection>? consequences,
        CampaignConsequenceProjection? consequence)
    {
        IReadOnlyList<CampaignConsequenceProjection> existingConsequences = consequences ?? Array.Empty<CampaignConsequenceProjection>();
        if (consequence is null)
        {
            return existingConsequences
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
        }

        CampaignConsequenceProjection? existing = existingConsequences
            .FirstOrDefault(item => string.Equals(item.Kind, consequence.Kind, StringComparison.OrdinalIgnoreCase));
        CampaignConsequenceProjection mergedConsequence = existing is null
            ? consequence
            : consequence with
            {
                EvidenceLines = FinalizeLines(existing.EvidenceLines.Concat(consequence.EvidenceLines)),
                Receipts = existing.Receipts
                    .Concat(consequence.Receipts)
                    .GroupBy(static item => $"{item.SourceKind}|{item.ReceiptId}|{item.Summary}", StringComparer.OrdinalIgnoreCase)
                    .Select(static group => group.Last())
                    .ToArray()
            };

        return existingConsequences
            .Where(item => !string.Equals(item.Kind, mergedConsequence.Kind, StringComparison.OrdinalIgnoreCase))
            .Concat([mergedConsequence])
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
    }

    private static IReadOnlyList<CampaignConsequenceProjection> MergeCampaignConsequencesWithReceiptCarryForward(
        IReadOnlyList<CampaignConsequenceProjection> baselineConsequences,
        IReadOnlyList<CampaignConsequenceProjection>? persistedConsequences)
    {
        if (persistedConsequences is not { Count: > 0 })
        {
            return baselineConsequences
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
        }

        Dictionary<string, CampaignConsequenceProjection> persistedByKind = persistedConsequences
            .GroupBy(static item => item.Kind, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(static group => group.Key, static group => group.Last(), StringComparer.OrdinalIgnoreCase);

        HashSet<string> baselineKinds = new(StringComparer.OrdinalIgnoreCase);
        List<CampaignConsequenceProjection> merged = [];
        foreach (CampaignConsequenceProjection baselineConsequence in baselineConsequences)
        {
            baselineKinds.Add(baselineConsequence.Kind);
            if (!persistedByKind.TryGetValue(baselineConsequence.Kind, out CampaignConsequenceProjection? persistedConsequence))
            {
                merged.Add(baselineConsequence);
                continue;
            }

            CampaignConsequenceProjection winningConsequence = HasGovernedConsequenceUpdateReceipt(persistedConsequence)
                ? persistedConsequence
                : baselineConsequence;
            merged.Add(winningConsequence with
            {
                EvidenceLines = FinalizeLines(baselineConsequence.EvidenceLines.Concat(persistedConsequence.EvidenceLines)),
                Receipts = MergeCampaignConsequenceReceiptsWithCarryForward(baselineConsequence.Receipts, persistedConsequence.Receipts)
            });
        }

        merged.AddRange(persistedConsequences
            .Where(consequence => !baselineKinds.Contains(consequence.Kind)));

        return merged
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToArray();
    }

    private static IReadOnlyList<CampaignConsequenceReceipt> MergeCampaignConsequenceReceiptsWithCarryForward(
        IReadOnlyList<CampaignConsequenceReceipt> baselineReceipts,
        IReadOnlyList<CampaignConsequenceReceipt> persistedReceipts)
    {
        Dictionary<string, CampaignConsequenceReceipt> persistedByKey = persistedReceipts
            .GroupBy(ResolveCampaignConsequenceReceiptKey, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(static group => group.Key, static group => group.Last(), StringComparer.OrdinalIgnoreCase);
        HashSet<string> baselineKeys = new(StringComparer.OrdinalIgnoreCase);

        CampaignConsequenceReceipt[] mergedBaselineReceipts = baselineReceipts
            .Select(receipt =>
            {
                string key = ResolveCampaignConsequenceReceiptKey(receipt);
                baselineKeys.Add(key);
                return persistedByKey.TryGetValue(key, out CampaignConsequenceReceipt? persistedReceipt)
                    ? persistedReceipt
                    : receipt;
            })
            .ToArray();

        return mergedBaselineReceipts
            .Concat(persistedReceipts.Where(receipt => !baselineKeys.Contains(ResolveCampaignConsequenceReceiptKey(receipt))))
            .GroupBy(ResolveCampaignConsequenceReceiptKey, StringComparer.OrdinalIgnoreCase)
            .Select(static group => group.First())
            .ToArray();
    }

    private static bool HasGovernedConsequenceUpdateReceipt(CampaignConsequenceProjection consequence)
        => consequence.Receipts.Any(static receipt =>
            string.Equals(receipt.SourceKind, GovernedConsequenceUpdateSourceKind, StringComparison.OrdinalIgnoreCase));

    private static string ResolveCampaignConsequenceReceiptKey(CampaignConsequenceReceipt receipt)
        => $"{NormalizeReceiptKeyPart(receipt.SourceKind)}|{NormalizeReceiptKeyPart(receipt.ReceiptId)}|{NormalizeReceiptKeyPart(receipt.Summary)}";

    private static string NormalizeReceiptKeyPart(string value)
        => string.Join(" ", value.Trim().Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries));

    private static IReadOnlyList<string> BuildGovernedConsequenceReturnLoopEvidenceLines(
        IEnumerable<CampaignConsequenceProjection> consequences)
        => consequences
            .SelectMany(static consequence => consequence.Receipts)
            .Where(static receipt =>
                string.Equals(receipt.SourceKind, ReturnLoopActionSourceKind, StringComparison.OrdinalIgnoreCase)
                || string.Equals(receipt.SourceKind, ReturnLoopRouteSourceKind, StringComparison.OrdinalIgnoreCase))
            .Select(static receipt => receipt.Summary)
            .Where(static summary => !string.IsNullOrWhiteSpace(summary))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();

    private static string ResolveGovernedConsequenceLabel(string normalizedKind)
        => normalizedKind switch
        {
            "heat" => "Heat posture",
            "faction" => "Faction standing",
            "contact" => "Contact network",
            "reputation" => "Reputation posture",
            "downtime" => "Downtime posture",
            "aftermath" => "Aftermath posture",
            _ => "Governed consequence"
        };

    private static string ResolveGovernedConsequenceReturnLoopAction(string normalizedKind)
        => normalizedKind switch
        {
            "heat" => "Review heat fallout",
            "faction" => "Confirm faction standing",
            "contact" => "Review contact fallout",
            "reputation" => "Review reputation fallout",
            "downtime" or "aftermath" => "Review downtime obligations",
            _ => "Review governed consequence"
        };

    private static string NormalizeGovernedConsequenceKind(string kind)
        => AccountService.NormalizeOptional(kind)?.ToLowerInvariant() switch
        {
            "heat" => "heat",
            "faction" => "faction",
            "contact" => "contact",
            "reputation" => "reputation",
            "downtime" => "downtime",
            "aftermath" => "aftermath",
            "downtime_brief" => "downtime",
            "session_recap" or "after_action_report" or "replay_timeline" => "aftermath",
            _ => throw new ArgumentException($"campaign consequence kind is not supported: {kind}", nameof(kind))
        };

    private static string NormalizeGovernedConsequenceReturnLoopRoute(string consequenceKind, string? returnLoopRoute)
    {
        string canonicalRoute = consequenceKind switch
        {
            "downtime" or "aftermath" => "/account/work#aftermath-packages",
            _ => "/account/work"
        };

        string? normalizedRoute = AccountService.NormalizeOptional(returnLoopRoute);
        if (normalizedRoute is null)
        {
            return canonicalRoute;
        }

        if (!string.Equals(normalizedRoute, canonicalRoute, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException($"campaign consequence return-loop route must stay on the governed local route {canonicalRoute} for {consequenceKind}.");
        }

        return canonicalRoute;
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
                    CampaignConsequence(
                        ReceiptId: leadObjective.ObjectiveId,
                        SourceKind: "objective",
                        Summary: leadObjective.Summary),
                    CampaignConsequence(
                        ReceiptId: activeScene.SceneId,
                        SourceKind: "scene",
                        Summary: activeScene.Summary),
                    CampaignConsequence(
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
                CampaignConsequence(
                    ReceiptId: group.GroupId,
                    SourceKind: "group",
                    Summary: $"{group.Name} sponsor group"),
                CampaignConsequence(
                    ReceiptId: crew.CrewId,
                    SourceKind: "crew",
                    Summary: $"{crew.Members.Count} crew assignment(s) stay attached to the campaign"),
                CampaignConsequence(
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
                .Select(static dossier => CampaignConsequence(
                    ReceiptId: dossier.DossierId,
                    SourceKind: "dossier",
                    Summary: $"{dossier.DisplayName} ({dossier.RunnerHandle})"))
                .Concat(
                [
                    CampaignConsequence(
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
                .Select(static output => CampaignConsequence(
                    ReceiptId: output.ArtifactId ?? output.ProjectionId,
                    SourceKind: output.Kind,
                    Summary: output.Summary))
                .Concat(
                [
                    CampaignConsequence(
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

    private static CampaignConsequenceReceipt CampaignConsequence(
        string ReceiptId,
        string SourceKind,
        string Summary)
        => new(
            ReceiptId,
            SourceKind,
            Summary,
            BuildCampaignReceiptEnvelope("campaign_consequence", ReceiptId));

    private static ReceiptEnvelope BuildCampaignReceiptEnvelope(
        string receiptKind,
        string receiptId,
        string ownerScope = "campaign.workspace")
        => ReceiptEnvelopeFactory.Runtime(
            receiptKind: receiptKind,
            ownerScope: ownerScope,
            exposureClass: ReceiptExposureClasses.SignedIn,
            evidenceRef: receiptId,
            reviewState: "verified");

    private static IReadOnlyList<string> BuildBuildLabWatchouts(
        CampaignWorkspaceProjection? workspace,
        IReadOnlyList<PublicationSafeProjection> outputs,
        WorkspaceRestoreProjection restore)
    {
        var watchouts = new List<string>();

        if (workspace is null)
        {
            watchouts.Add("No reviewed campaign workspace is attached yet, so the build is still dossier-first rather than table-return first.");
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
                AfterSummary: $"After campaign approval, {operation.RuleEnvironment.CompatibilityFingerprint} anchors {operation.ActiveCampaignCount} active campaign(s) on the same maintainer path.",
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
                $"{scopeLabel} binds {environment.CompatibilityFingerprint} to build, play, support, and return on one reviewed path.",
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
                    ImportedAtUtc: dossier.UpdatedAtUtc,
                    Envelope: ReceiptEnvelopeFactory.Runtime(
                        receiptKind: "legacy_migration",
                        ownerScope: "community.campaign_spine",
                        exposureClass: ReceiptExposureClasses.SignedIn,
                        evidenceRef: dossier.DossierId,
                        reviewState: campaign is null ? "risky" : "safe"));
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
                            AuditSummary = DescribeRecapShelfAuditSummary(workspace, item, creatorPublication, creatorLinked),
                            CompatibilitySummary = DescribeRecapShelfCompatibilitySummary(workspace, item, creatorPublication, creatorLinked),
                            LineageSummary = DescribeRecapShelfLineageSummary(workspace, item, creatorPublication, creatorLinked)
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
    {
        if (leadHandoff is null)
        {
            return "Compare by provenance, visibility, trust ranking, lineage, explicit rule-environment before/after diff evidence, and campaign-return fit instead of popularity, install counts, or shelf age.";
        }

        string exchangeParity = AccountService.NormalizeOptional(leadHandoff.ExchangeParitySummary)
            ?? "sheet/print/export/viewer and adjacent exchange parity lanes are still pending explicit readiness evidence";
        string portabilityPillar = AccountService.NormalizeOptional(leadHandoff.PortabilityPillarSummary)
            ?? "dossier/exchange/replay/recap/module portability lanes are still pending explicit readiness evidence";
        string ruleEnvironmentDiff = leadHandoff.RuleEnvironmentDiff is null
            ? "rule-environment before/after diff evidence is still pending explicit handoff receipts"
            : $"rule-environment diff {leadHandoff.RuleEnvironmentDiff.BeforeFingerprint} -> {leadHandoff.RuleEnvironmentDiff.AfterFingerprint} ({leadHandoff.RuleEnvironmentDiff.Status})";

        return $"Compare by provenance, visibility, trust ranking, lineage, {leadHandoff.Title} receipts, {ruleEnvironmentDiff}, {exchangeParity}, {portabilityPillar}, and campaign-return fit instead of popularity, install counts, or shelf age.";
    }

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
            return $"{workspace.CampaignName} reuses the same governed dossier artifact on the account path instead of forking a shadow copy.";
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
        string auditSummary;
        if (!string.IsNullOrWhiteSpace(item.AuditSummary))
        {
            auditSummary = item.AuditSummary!;
        }
        else
        {
            DateTimeOffset updatedAtUtc = creatorLinked
            ? creatorPublication?.UpdatedAtUtc ?? DateTimeOffset.UtcNow
            : workspace.LatestContinuity?.CapturedAtUtc
                ?? workspace.AftermathPackages?.FirstOrDefault()?.GeneratedAtUtc
                ?? DateTimeOffset.UtcNow;
            string auditSource = creatorLinked
            ? "publication review and campaign return"
            : "campaign return";
            auditSummary = $"Updated {updatedAtUtc:yyyy-MM-dd HH:mm} UTC on the governed {auditSource} lane for {workspace.CampaignName}.";
        }

        return creatorLinked
            ? EnsureManifestBackedAuditSummary(auditSummary)
            : auditSummary;
    }

    private static string EnsureManifestBackedAuditSummary(string auditSummary)
    {
        string normalized = auditSummary.Trim();
        return normalized.Contains("manifest-authority-backed", StringComparison.OrdinalIgnoreCase)
            ? normalized
            : $"manifest-authority-backed; {normalized}";
    }

    private static string DescribeRecapShelfCompatibilitySummary(
        CampaignWorkspaceProjection workspace,
        PublicationSafeProjection item,
        CreatorPublicationProjection? creatorPublication,
        bool creatorLinked)
    {
        if (!string.IsNullOrWhiteSpace(item.CompatibilitySummary))
        {
            return item.CompatibilitySummary!;
        }

        if (creatorLinked && creatorPublication is not null)
        {
            return $"{workspace.RuleEnvironment.CompatibilityFingerprint} stays pinned across {item.Label}, campaign return, and creator publication {creatorPublication.PublicationId} ({creatorPublication.PublicationStatus}).";
        }

        return $"{workspace.RuleEnvironment.CompatibilityFingerprint} stays pinned across {item.Label} and campaign return before wider publication handoff.";
    }

    private static string DescribeRecapShelfLineageSummary(
        CampaignWorkspaceProjection workspace,
        PublicationSafeProjection item,
        CreatorPublicationProjection? creatorPublication,
        bool creatorLinked)
    {
        if (!string.IsNullOrWhiteSpace(item.LineageSummary))
        {
            return item.LineageSummary!;
        }

        if (creatorLinked && !string.IsNullOrWhiteSpace(creatorPublication?.LineageSummary))
        {
            return creatorPublication!.LineageSummary!;
        }

        if (creatorLinked && creatorPublication is not null)
        {
            return $"{item.Label} keeps one lineage lane from {workspace.CampaignId} through publication {creatorPublication.PublicationId} without a shadow export copy.";
        }

        string artifactToken = string.IsNullOrWhiteSpace(item.ArtifactId)
            ? item.ProjectionId
            : item.ArtifactId!;
        return $"{item.Label} keeps lineage anchored to {artifactToken} on {workspace.CampaignName} so return, replay, and recap stay on one governed truth lane.";
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
