using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Chummer.Storage.Teable;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;

namespace Chummer.Tests;

public sealed class FactionTeablePersistenceTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "faction-teable-" + Guid.NewGuid().ToString("N"));
    private IConfiguration Configuration => new ConfigurationBuilder().AddInMemoryCollection(
        new Dictionary<string, string?>
        {
            ["CHUMMER_COMMUNITY_STORAGE_PROVIDER"] = "teable",
            ["CHUMMER_SUPPORT_STORE_PATH"] = Path.Combine(_root, "support.json")
        }).Build();

    private CommunityStore Store(Remote remote) => new(Configuration, NullLogger<CommunityStore>.Instance, remote.Store());

    private BlackLedgerFactionOnboardingService Factions(CommunityStore store)
    {
        // The artifact bridge shares primary custody with Community. The support
        // dependency is read-only here; no provider/publication operation occurs.
        var artifacts = new CampaignArtifactRegistryBridge(store);
        var support = new SupportStore(Configuration, NullLogger<SupportStore>.Instance);
        var campaign = new CampaignSpineService(store, new WorkspaceLifecyclePolicyService(Configuration), artifacts, support);
        return new(Configuration, new BlackLedgerPublicStatsService(), campaign, store);
    }

    private static BlackLedgerCreateFactionRequest Charter(string name, string kind = "major") => new(
        name, kind, "creator_press", ["dispatch_desk", "public_trust"],
        kind == "major" ? ["overexposed", "thin_resources"] : ["overexposed", "thin_resources", "rival_target"],
        "emerald-core", null, true);

    private static BlackLedgerFactionActionRequest Scout => new(
        ActionId: "scout", TargetDistrictId: "emerald-core", TargetFactionId: null, Stake: "pressure");

    [Fact]
    public async Task Charter_allegiance_lore_action_and_moderation_restore_without_local_state()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var user = new AccountService(writer).EnsureUser("founder");
        var factions = Factions(writer);
        var charter = factions.CreateFaction(user, Charter("Synthetic Signal Cell"));
        var action = factions.ExecuteAction(user, charter.FactionId, Scout);
        FactionAccessFixture.AddCampaign(writer, user, "campaign-synthetic");
        var lore = factions.UpsertPrivateLoreOverlay(user, "campaign-synthetic", new PrivateLoreOverlayRequest(
            "emerald-sprawl-prelude", charter.FactionId, new Dictionary<string, string> { ["district"] = "Private label" }, ["Private note"]));
        Assert.Null(factions.GetFactionDetail(charter.FactionId));
        var permission = await FactionAccessFixture.Permission(writer);
        factions.ApproveFactionForPublicProjection(permission, charter.FactionId);

        using var cold = Store(remote);
        var restored = Factions(cold);
        Assert.Equal(charter.FactionId, restored.GetAllegiance(user)!.ActiveFactionId);
        Assert.Equal("public_safe_active", restored.GetCharter(charter.FactionId)!.Status);
        Assert.NotNull(restored.GetFactionDetail(charter.FactionId));
        Assert.Equal(action.ReceiptId, Assert.Single(restored.GetActionReceipts(charter.FactionId)).ReceiptId);
        var savedLore = restored.GetPrivateLoreOverlay(user, "campaign-synthetic", charter.FactionId)!;
        Assert.Equal(lore.OverlayId, savedLore.OverlayId);
        Assert.Equal("Private label", savedLore.LabelMap["district"]);
        Assert.False(savedLore.PublicProjectionAllowed);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public async Task Existing_service_observes_remote_moderation_and_allegiance_changes()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var user = new AccountService(writer).EnsureUser("founder");
        var factions = Factions(writer);
        var charter = factions.CreateFaction(user, Charter("Synthetic Quiet Cell"));
        var permission = await FactionAccessFixture.Permission(writer);
        factions.ApproveFactionForPublicProjection(permission, charter.FactionId);
        using var reader = Store(remote);
        var observer = Factions(reader);
        Assert.NotNull(observer.GetFactionDetail(charter.FactionId));
        Assert.True(observer.HasActiveAllegiance(user.UserId));

        factions.SuppressFactionPublicProjection(permission, charter.FactionId, "Withdrawn");
        using (writer.Enter())
        {
            writer.BlackLedgerFactionOnboardingState!.Allegiances.Remove(user.UserId);
            writer.PersistLocked();
        }
        Assert.Null(observer.GetFactionDetail(charter.FactionId));
        Assert.DoesNotContain(observer.ListFactionSummaries(), item => item.FactionId == charter.FactionId);
        Assert.Equal("suppressed", observer.GetCharter(charter.FactionId)!.Status);
        Assert.False(observer.HasActiveAllegiance(user.UserId));
        Assert.Throws<InvalidOperationException>(() => observer.ExecuteAction(user, charter.FactionId, Scout));
    }

    [Fact]
    public void Lore_access_observes_persisted_owner_transfer_without_writing_on_denial()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var accounts = new AccountService(writer);
        var owner = accounts.EnsureUser("lore-owner");
        var successor = accounts.EnsureUser("lore-successor");
        var factions = Factions(writer);
        var charter = factions.CreateFaction(owner, Charter("Synthetic Private Cell"));
        FactionAccessFixture.AddCampaign(writer, owner, "campaign-synthetic");
        var lore = factions.UpsertPrivateLoreOverlay(owner, "campaign-synthetic", FactionAccessFixture.Lore(charter.FactionId));
        using var reader = Store(remote);
        var observer = Factions(reader);
        Assert.Equal(lore.OverlayId, observer.GetPrivateLoreOverlay(owner, "campaign-synthetic", charter.FactionId)!.OverlayId);
        using (writer.Enter())
        {
            var group = writer.GroupsById["group-campaign-synthetic"];
            writer.GroupsById[group.GroupId] = group with { OwnerUserId = successor.UserId };
            writer.PersistLocked();
        }
        int writes = remote.HeadPosts;
        Assert.Equal(404, Assert.Throws<Chummer.Run.Api.Services.HubRequestAuthException>(() =>
            observer.GetPrivateLoreOverlay(owner, "campaign-synthetic", charter.FactionId)).StatusCode);
        Assert.Equal(404, Assert.Throws<Chummer.Run.Api.Services.HubRequestAuthException>(() =>
            observer.UpsertPrivateLoreOverlay(owner, "campaign-synthetic", FactionAccessFixture.Lore(charter.FactionId))).StatusCode);
        Assert.Equal(writes, remote.HeadPosts);
        Assert.Equal(lore.OverlayId, observer.GetPrivateLoreOverlay(successor, "campaign-synthetic", charter.FactionId)!.OverlayId);
    }

    [Fact]
    public void Concurrent_last_action_point_commits_only_one_action_and_receipt()
    {
        using var remote = new Remote();
        using var first = Store(remote);
        var user = new AccountService(first).EnsureUser("founder");
        var factions = Factions(first);
        var charter = factions.CreateFaction(user, Charter("Synthetic Last Point"));
        factions.ExecuteAction(user, charter.FactionId, Scout);
        factions.ExecuteAction(user, charter.FactionId, Scout);
        using var second = Store(remote);
        BlackLedgerFactionActionReceiptDto? winner = null;
        remote.BeforeHeadPost = () => winner = Factions(second).ExecuteAction(user, charter.FactionId, Scout);

        Assert.Throws<TeableRevisionConflictException>(() => factions.ExecuteAction(user, charter.FactionId, Scout));
        Assert.NotNull(winner);
        Assert.Equal(0, winner.RemainingActionPoints);
        Assert.Throws<InvalidOperationException>(() => factions.GetActionReceipts(charter.FactionId));
        using var cold = Store(remote);
        var restored = Factions(cold);
        Assert.Equal(3, restored.GetActionReceipts(charter.FactionId).Count);
        Assert.Contains(restored.GetActionReceipts(charter.FactionId), item => item.ReceiptId == winner.ReceiptId);
        Assert.Throws<InvalidOperationException>(() => restored.ExecuteAction(user, charter.FactionId, Scout));
    }

    [Fact]
    public void Lost_action_commit_acknowledgement_restores_exactly_one_charge_and_receipt()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var user = new AccountService(writer).EnsureUser("founder");
        var factions = Factions(writer);
        var charter = factions.CreateFaction(user, Charter("Synthetic Uncertain Charge"));
        remote.CommitThenFailHard = true;
        Assert.Throws<TeableRequestFailureException>(() => factions.ExecuteAction(user, charter.FactionId, Scout));
        int writes = remote.HeadPosts;
        Assert.Throws<InvalidOperationException>(() => factions.ExecuteAction(user, charter.FactionId, Scout));

        using var cold = Store(remote);
        var restored = Factions(cold);
        var receipt = Assert.Single(restored.GetActionReceipts(charter.FactionId));
        Assert.Equal(2, receipt.RemainingActionPoints);
        Assert.Equal(writes, remote.HeadPosts);
    }

    [Fact]
    public void Current_remote_allegiance_enforces_cooldown_without_overwrite()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var user = new AccountService(writer).EnsureUser("member");
        using var reader = Store(remote);
        var oldService = Factions(reader);
        Assert.Null(oldService.GetAllegiance(user));
        var receipt = Factions(writer).JoinFaction(user, "ashline-circle");
        var failure = Assert.Throws<InvalidOperationException>(() => oldService.JoinFaction(user, "glass-tower-compact"));
        Assert.Contains("cooldown", failure.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Equal(receipt.ReceiptId, oldService.GetAllegiance(user)!.ReceiptId);
        Assert.Equal(1, oldService.GetAllegiance(user)!.SwitchCount);
    }

    [Fact]
    public void Charter_admission_observes_major_capacity_committed_after_service_creation()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        using var reader = Store(remote);
        var oldService = Factions(reader);
        Assert.Equal(4, oldService.BuildMajorSlotAvailability().MajorSlotsAvailable);
        for (int i = 0; i < 4; i++)
        {
            var user = new AccountService(writer).EnsureUser("founder-" + i);
            Factions(writer).CreateFaction(user, Charter("Synthetic Major " + i));
        }
        var lateUser = new AccountService(writer).EnsureUser("late-founder");
        Assert.Equal(0, oldService.BuildMajorSlotAvailability().MajorSlotsAvailable);
        var failure = Assert.Throws<InvalidOperationException>(() => oldService.CreateFaction(lateUser, Charter("Synthetic Extra Major")));
        Assert.Contains("No major charter slots", failure.Message, StringComparison.Ordinal);
        Assert.Null(oldService.GetAllegiance(lateUser));
    }

    [Fact]
    public void Nested_faction_read_preserves_pending_outer_state()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var user = new AccountService(store).EnsureUser("member");
        var factions = Factions(store);
        factions.JoinFaction(user, "ashline-circle");
        using (store.Enter())
        {
            var allegiance = store.BlackLedgerFactionOnboardingState!.Allegiances[user.UserId];
            store.BlackLedgerFactionOnboardingState.Allegiances[user.UserId] = allegiance with { SwitchCount = 7 };
            Assert.Equal(7, factions.GetAllegiance(user)!.SwitchCount);
            store.PersistLocked();
        }
        using var cold = Store(remote);
        Assert.Equal(7, Factions(cold).GetAllegiance(user)!.SwitchCount);
    }

    [Fact]
    public void Faction_outage_rejects_cached_authority_and_new_writes()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var user = new AccountService(store).EnsureUser("member");
        var factions = Factions(store);
        factions.JoinFaction(user, "ashline-circle");
        Assert.True(factions.HasActiveAllegiance(user.UserId));
        int writes = remote.HeadPosts;
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => factions.GetAllegiance(user));
        Assert.Throws<InvalidOperationException>(() => factions.ExecuteAction(user, "ashline-circle", Scout));
        Assert.Equal(writes, remote.HeadPosts);
    }

    public void Dispose()
    {
        if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
    }
}
