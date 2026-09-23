using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Contracts.Community;
using Chummer.Storage.Teable;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;

namespace Chummer.Tests;

public sealed class CampaignSpineTeablePersistenceTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "campaign-spine-teable-" + Guid.NewGuid().ToString("N"));
    private IConfiguration Configuration => new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
    {
        ["CHUMMER_COMMUNITY_STORAGE_PROVIDER"] = "teable",
        ["CHUMMER_SUPPORT_STORAGE_PROVIDER"] = "teable",
        ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community.json"),
        ["CHUMMER_SUPPORT_STORE_PATH"] = Path.Combine(_root, "support.json")
    }).Build();
    private CommunityStore Store(Remote remote) => new(Configuration, NullLogger<CommunityStore>.Instance, remote.Store());
    private CampaignSpineService Service(CommunityStore store, Remote remote) => new(store,
        new WorkspaceLifecyclePolicyService(Configuration), new CampaignArtifactRegistryBridge(store),
        new SupportStore(Configuration, NullLogger<SupportStore>.Instance, remote.Store()));
    private (HubUserDto User, CampaignWorkspaceProjection Workspace) Context(CommunityStore store, Remote remote)
    {
        var user = new AccountService(store).EnsureUser("synthetic-subject", "Synthetic runner");
        return (user, Service(store, remote).GetStarterWorkspace(user)!);
    }
    private static CampaignAdoptionUpdateRequest Adoption(string summary) => new(true, 80, 1, 1, 0, 0, [], [], summary);
    private static OpenRunCloseoutRequest Closeout(string summary = "Synthetic closeout") => new(
        summary, "Synthetic world tick", "Synthetic consequence", "Synthetic title", "Synthetic news");

    private OpenRunListingProjection PrepareOpenRun(CommunityStore store, Remote remote,
        HubUserDto user, CampaignWorkspaceProjection workspace)
    {
        var service = Service(store, remote);
        var listing = service.CreateOpenRun(user, workspace.WorkspaceId, new(
            workspace.Runs.First().RunId, "Synthetic open run", "Synthetic summary", "community",
            "Synthetic table contract", "request_to_join", 2, true, false,
            "manual", 60, "offline", false, "manual_markers", []));
        var join = service.SubmitOpenRunJoinRequest(user, listing.OpenRunId, new(
            workspace.Dossiers.First(item => item.OwnerUserId == user.UserId).DossierId, null, true, true, true));
        service.ReviewOpenRunJoinRequest(user, listing.OpenRunId, join.RequestId, new("accepted"));
        service.ScheduleOpenRun(user, listing.OpenRunId, new(DateTimeOffset.UtcNow.AddHours(1), "UTC"));
        service.CreateOpenRunMeetingHandoff(user, listing.OpenRunId,
            new("offline", "Synthetic table", "accepted_roster", DateTimeOffset.UtcNow.AddHours(3)));
        return listing;
    }

    [Fact]
    public void Prep_travel_adoption_and_goal_survive_cold_restore_without_local_files()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var (user, workspace) = Context(writer, remote);
        var service = Service(writer, remote);
        var run = workspace.Runs.First();
        var prep = service.RecordPrepLaunch(user, workspace, "synthetic-packet", "runbook",
            "Synthetic preparation", "Synthetic summary", run, run.Scenes.First());
        var travel = service.RecordTravelPrefetch(user, workspace,
            new("synthetic-install", "travel", "android", "synthetic-head", "internal", "Synthetic phone", "Ready"),
            "Synthetic prefetch", ["Synthetic inventory"], ["No provider operation"]);
        var adoption = service.UpsertCampaignAdoption(user, workspace, Adoption("Synthetic adoption"));
        var goal = service.UpsertRunnerGoal(user, workspace, new(
            workspace.Dossiers.First(item => item.OwnerUserId == user.UserId).DossierId,
            "Synthetic goal", "upgrade_fund", "synthetic-upgrade", 100, 1000, 2, 1, "gm_review"));
        using var cold = Store(remote);
        var restored = Service(cold, remote);
        Assert.NotNull(restored.GetWorkspaceCampaignState(user, workspace.WorkspaceId));
        Assert.NotNull(restored.GetRosterTransferPlan(user, workspace.WorkspaceId));
        Assert.NotNull(restored.GetDossierMovementPlan(user, workspace.WorkspaceId));
        Assert.NotNull(restored.GetOrganizerOperations(user));
        using (cold.Enter())
        {
            Assert.Contains(cold.PrepLaunches, row => row.LaunchId == prep.LaunchId);
            Assert.Contains(cold.TravelPrefetchReceipts, row => row.ReceiptId == travel.ReceiptId);
            Assert.Contains(cold.CampaignAdoptions, row => row.AdoptionId == adoption.AdoptionId);
            Assert.Contains(cold.RunnerGoals, row => row.GoalId == goal.GoalId);
        }
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Open_run_closeout_and_world_memory_share_one_primary_commit()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var (user, workspace) = Context(writer, remote);
        var listing = PrepareOpenRun(writer, remote, user, workspace);
        int writes = remote.HeadPosts;
        var closeout = Service(writer, remote).CloseOutOpenRun(user, listing.OpenRunId, Closeout());
        Assert.Equal(writes + 1, remote.HeadPosts);
        using var cold = Store(remote);
        var reopened = Service(cold, remote).GetOpenRun(user, listing.OpenRunId)!;
        Assert.Equal("closed", reopened.Listing.Status);
        Assert.Equal(closeout.CloseoutId, reopened.Closeout!.CloseoutId);
        using (cold.Enter())
        {
            Assert.Contains(cold.ResolutionReportApprovals, item => item.ApprovalId == closeout.ResolutionApprovalId);
            Assert.Contains(cold.WorldTicks, item => item.WorldTickId == closeout.WorldTickId);
            Assert.Contains(cold.PlayerSafeNews, item => item.NewsId == closeout.PlayerSafeNewsId);
        }
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Conflicting_closeout_leaves_no_half_approval_or_world_tick()
    {
        using var remote = new Remote();
        using var first = Store(remote);
        var (user, workspace) = Context(first, remote);
        var listing = PrepareOpenRun(first, remote, user, workspace);
        using var winner = Store(remote);
        remote.BeforeHeadPost = () =>
        {
            using var scope = winner.Enter();
            winner.UsersById[user.UserId] = winner.UsersById[user.UserId] with { DisplayName = "Winning account change" };
            winner.PersistLocked();
        };
        Assert.Throws<TeableRevisionConflictException>(() => Service(first, remote).CloseOutOpenRun(user, listing.OpenRunId, Closeout()));
        Assert.Throws<InvalidOperationException>(() => Service(first, remote).GetOpenRuns(user));
        using var cold = Store(remote);
        using var coldScope = cold.Enter();
        Assert.Empty(cold.OpenRunCloseouts);
        Assert.Empty(cold.ResolutionReportApprovals);
        Assert.Empty(cold.WorldTicks);
        Assert.Empty(cold.PlayerSafeNews);
        Assert.Equal("handoff_ready", Assert.Single(cold.OpenRuns).Status);
        Assert.Equal("Winning account change", cold.UsersById[user.UserId].DisplayName);
    }

    [Fact]
    public void Uncertain_closeout_cold_restores_every_part_without_replay()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var (user, workspace) = Context(writer, remote);
        var listing = PrepareOpenRun(writer, remote, user, workspace);
        remote.CommitThenFailHard = true;
        Assert.Throws<IOException>(() => Service(writer, remote).CloseOutOpenRun(user, listing.OpenRunId, Closeout()));
        int writes = remote.HeadPosts;
        Assert.Throws<InvalidOperationException>(() => Service(writer, remote).CloseOutOpenRun(user, listing.OpenRunId, Closeout()));
        using var cold = Store(remote);
        using var scope = cold.Enter();
        var closeout = Assert.Single(cold.OpenRunCloseouts);
        Assert.Equal(closeout.ResolutionApprovalId, Assert.Single(cold.ResolutionReportApprovals).ApprovalId);
        Assert.Equal(closeout.WorldTickId, Assert.Single(cold.WorldTicks).WorldTickId);
        Assert.Equal(closeout.PlayerSafeNewsId, Assert.Single(cold.PlayerSafeNews).NewsId);
        Assert.Equal("closed", Assert.Single(cold.OpenRuns).Status);
        Assert.Equal(writes, remote.HeadPosts);
    }

    [Fact]
    public void Invalid_closeout_rolls_back_staged_changes_without_disabling_clean_retry()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var (user, workspace) = Context(writer, remote);
        var listing = PrepareOpenRun(writer, remote, user, workspace);
        int writes = remote.HeadPosts;
        Assert.Throws<ArgumentException>(() => Service(writer, remote).CloseOutOpenRun(user, listing.OpenRunId,
            Closeout() with { NewsTitle = new string('x', 161) }));
        Assert.Equal(writes, remote.HeadPosts);
        Assert.NotNull(Service(writer, remote).CloseOutOpenRun(user, listing.OpenRunId, Closeout()));
    }

    [Fact]
    public void Current_revocation_rejects_cached_workspace_mutations_without_writes()
    {
        using var remote = new Remote();
        using var old = Store(remote);
        var (user, workspace) = Context(old, remote);
        using var other = Store(remote);
        using (other.Enter())
        {
            string groupId = other.CampaignSpinesById[workspace.CampaignId].GroupId;
            var group = other.GroupsById[groupId];
            other.GroupsById[groupId] = group with { Memberships = group.Memberships.Where(item => item.UserId != user.UserId).ToArray() };
            other.PersistLocked();
        }
        int writes = remote.HeadPosts;
        Assert.Throws<CommunityAccessDeniedException>(() => Service(old, remote).UpsertCampaignAdoption(user, workspace, Adoption("Must not save")));
        Assert.Equal(writes, remote.HeadPosts);
    }

    [Fact]
    public void Old_subject_cannot_seed_or_read_a_reassigned_primary_account()
    {
        using var remote = new Remote();
        using var old = Store(remote);
        var (user, workspace) = Context(old, remote);
        using var other = Store(remote);
        using (other.Enter())
        {
            other.UsersById[user.UserId] = user with { SubjectId = "replacement-subject", LinkedPrincipals = [] };
            other.PersistLocked();
        }
        int writes = remote.HeadPosts;
        Assert.Throws<CommunityAccessDeniedException>(() => Service(old, remote).GetAccountSummary(user));
        Assert.Throws<CommunityAccessDeniedException>(() => Service(old, remote).UpsertCampaignAdoption(user, workspace, Adoption("Must not save")));
        Assert.Equal(writes, remote.HeadPosts);
    }

    [Fact]
    public void Dossier_movement_and_transfer_plans_restore_from_current_primary_state()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var (user, workspace) = Context(store, remote);
        var accounts = new AccountService(store);
        var groups = new GroupService(store, accounts);
        var group = groups.CreateGroup(new(user.SubjectId, "Synthetic target crew", "campaign", "group", null));
        var campaign = groups.GetOrCreateCampaign(group.GroupId, "hub", "Synthetic target campaign");
        var service = Service(store, remote);
        var movement = service.MoveDossier(user, new(
            DossierId: workspace.Dossiers.First(item => item.OwnerUserId == user.UserId).DossierId,
            TargetGroupId: group.GroupId, TargetCampaignId: campaign.CampaignId,
            TargetRunTitle: "Synthetic target run", TargetSceneTitle: "Synthetic target scene"));
        using var cold = Store(remote);
        var reader = Service(cold, remote);
        var target = reader.GetAccountSummary(user).Workspaces.First(item => item.CampaignId == campaign.CampaignId);
        Assert.Contains(reader.GetDossierMovements(user, target.WorkspaceId), item => item.MovementId == movement.MovementId);
        Assert.NotNull(reader.GetDossierMovementPlan(user, target.WorkspaceId));
        Assert.NotNull(reader.GetRosterTransferPlan(user, target.WorkspaceId));
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Primary_requires_explicit_support_dependency_and_outage_never_uses_cached_campaigns()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var (user, _) = Context(store, remote);
        Assert.Throws<InvalidOperationException>(() => new CampaignSpineService(store,
            new WorkspaceLifecyclePolicyService(Configuration), new CampaignArtifactRegistryBridge(store)));
        var service = Service(store, remote);
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => service.GetOrganizerOperations(user));
        Assert.Throws<InvalidOperationException>(() => service.GetOpenRuns(user));
        Assert.False(Directory.Exists(_root));
    }

    public void Dispose()
    {
        if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
    }
}
