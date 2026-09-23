using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Teable;
using Chummer.Run.Contracts.Community;
using Chummer.Storage.Teable;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.DataProtection.KeyManagement;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;

namespace Chummer.Tests;

public sealed class CampaignCollaborationTeablePersistenceTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "campaign-collaboration-teable-" + Guid.NewGuid().ToString("N"));
    private CommunityStore Store(Remote remote) => new(new ConfigurationBuilder().AddInMemoryCollection(
        new Dictionary<string, string?>
        {
            ["CHUMMER_COMMUNITY_STORAGE_PROVIDER"] = "teable",
            ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community.json")
        }).Build(), NullLogger<CommunityStore>.Instance, remote.Store());

    private static ServiceProvider Keys(Remote remote)
    {
        var services = new ServiceCollection();
        services.AddDataProtection().SetApplicationName("Chummer.Run.Api");
        services.Configure<KeyManagementOptions>(options =>
        {
            options.XmlRepository = new TeableDataProtectionKeyRepository(remote.Store());
            options.XmlEncryptor = null;
        });
        return services.BuildServiceProvider();
    }

    private static CampaignCollaborationService Service(CommunityStore store, IServiceProvider keys, TimeProvider? clock = null)
        => new(store, new UnavailableCoreGmCharacterEditGateway(), keys.GetRequiredService<IDataProtectionProvider>(), clock ?? TimeProvider.System);

    private static HubUserDto User(CommunityStore store, string name)
        => new AccountService(store).EnsureUser("subject-" + name, "Synthetic " + name);

    private static CampaignCollaborationProjection Create(CampaignCollaborationService service, HubUserDto gm)
        => service.CreateCampaign(gm, new("Synthetic campaign", "synthetic-create", Visibility: "private"));

    private static RunnerDossierProjection Character(CommunityStore store, HubUserDto owner)
    {
        using var scope = store.Enter();
        var now = DateTimeOffset.UtcNow;
        string id = "dossier-" + owner.UserId;
        var dossier = new RunnerDossierProjection(id, "Synthetic runner", "Synthetic runner", DossierStatuses.Active,
            owner.UserId, null, null, null, null,
            new RuleEnvironmentRef("environment-" + id, "owner-" + owner.UserId, "fingerprint-" + id, "draft", [], [], []),
            null, [], [], [new PublicationSafeProjection("identity", "identity", "Identity", "Synthetic identity")], now, now);
        store.DossiersById[id] = dossier;
        store.PersistLocked();
        return dossier;
    }

    private static RedeemCampaignInviteRequest Redeem(CampaignInviteSecretProjection invite, RunnerDossierProjection dossier, string key = "synthetic-redeem")
        => new(invite.LinkSecret, dossier.DossierId, dossier.DossierId, 1, true, key);

    [Fact]
    public void Campaign_and_protected_invitation_replay_restore_with_independent_remote_key_providers()
    {
        using var remote = new Remote();
        using var first = Store(remote);
        using var firstKeys = Keys(remote);
        var gm = User(first, "gm");
        var service = Service(first, firstKeys);
        var campaign = Create(service, gm);
        var request = new CreateCampaignInviteRequest("synthetic-invite");
        var invite = service.CreateInvite(gm, campaign.CampaignId, request);
        int writes = remote.HeadPosts;
        using var cold = Store(remote);
        using var coldKeys = Keys(remote);
        var restored = Service(cold, coldKeys);
        Assert.Equal(campaign.CampaignId, Create(restored, gm).CampaignId);
        Assert.Equal(invite, restored.CreateInvite(gm, campaign.CampaignId, request));
        Assert.Equal(campaign.CampaignId, Assert.Single(restored.ListCampaigns(gm)).CampaignId);
        Assert.Equal(writes, remote.HeadPosts);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Membership_invite_consumption_and_runsite_restore_without_local_files()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        using var keys = Keys(remote);
        var gm = User(store, "gm");
        var player = User(store, "player");
        var dossier = Character(store, player);
        var service = Service(store, keys);
        var campaign = Create(service, gm);
        var invite = service.CreateInvite(gm, campaign.CampaignId, new("synthetic-invite"));
        int writes = remote.HeadPosts;
        var joined = service.RedeemJoinCode(player, new(invite.ShortCode, dossier.DossierId, dossier.DossierId, 1, true, "synthetic-join"));
        Assert.Equal(writes + 1, remote.HeadPosts);
        string runId = Assert.Single(campaign.RunIds);
        var draft = service.UpsertRunsiteDraft(gm, campaign.CampaignId, runId,
            new(0, "synthetic-draft", "Synthetic location", "Synthetic summary", [new("Approach", "Synthetic route")], "Synthetic GM secret"));
        var publication = service.PublishRunsite(gm, campaign.CampaignId, runId, new(draft.Revision, "synthetic-publish"));
        using var cold = Store(remote);
        var reader = Service(cold, keys);
        Assert.Equal(joined.DossierId, Assert.Single(reader.GetRoster(player, campaign.CampaignId)).DossierId);
        Assert.Equal(dossier.RunnerHandle, reader.GetSharedSheet(player, campaign.CampaignId, dossier.DossierId).RunnerHandle);
        Assert.Equal(publication.Title, reader.GetPublishedRunsite(player, campaign.CampaignId, runId)!.Title);
        Assert.Throws<CampaignCollaborationAccessDeniedException>(() => reader.GetRunsiteDraft(player, campaign.CampaignId, runId));
        using (cold.Enter()) Assert.Equal(1, cold.CampaignCollaborationInvitesById[invite.InviteId].Uses);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Competing_last_invite_use_admits_only_one_membership()
    {
        using var remote = new Remote();
        using var first = Store(remote);
        using var keys = Keys(remote);
        var gm = User(first, "gm");
        var player = User(first, "player");
        var winner = User(first, "winner");
        var playerDossier = Character(first, player);
        var winnerDossier = Character(first, winner);
        var service = Service(first, keys);
        var campaign = Create(service, gm);
        var invite = service.CreateInvite(gm, campaign.CampaignId, new("synthetic-invite"));
        using var other = Store(remote);
        remote.BeforeHeadPost = () => Service(other, keys).RedeemInvite(winner, invite.InviteId, Redeem(invite, winnerDossier));
        Assert.Throws<TeableRevisionConflictException>(() => service.RedeemInvite(player, invite.InviteId, Redeem(invite, playerDossier)));
        Assert.Throws<InvalidOperationException>(() => service.ListCampaigns(gm));
        using var cold = Store(remote);
        var reader = Service(cold, keys);
        Assert.Equal(winnerDossier.DossierId, Assert.Single(reader.GetRoster(gm, campaign.CampaignId)).DossierId);
        Assert.Null(reader.GetCampaign(player, campaign.CampaignId));
        Assert.Throws<CampaignInviteRejectedException>(() => reader.RedeemInvite(player, invite.InviteId, Redeem(invite, playerDossier)));
    }

    [Fact]
    public void Lost_acknowledgement_restores_membership_and_idempotent_result_without_second_consumption()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        using var keys = Keys(remote);
        var gm = User(writer, "gm");
        var player = User(writer, "player");
        var dossier = Character(writer, player);
        var service = Service(writer, keys);
        var campaign = Create(service, gm);
        var invite = service.CreateInvite(gm, campaign.CampaignId, new("synthetic-invite"));
        var request = Redeem(invite, dossier);
        remote.CommitThenFailHard = true;
        Assert.Throws<IOException>(() => service.RedeemInvite(player, invite.InviteId, request));
        int writes = remote.HeadPosts;
        using var cold = Store(remote);
        var replay = Service(cold, keys).RedeemInvite(player, invite.InviteId, request);
        Assert.True(replay.AlreadyJoined);
        Assert.Equal(writes, remote.HeadPosts);
        using (cold.Enter()) Assert.Equal(1, cold.CampaignCollaborationInvitesById[invite.InviteId].Uses);
    }

    [Fact]
    public void Failed_invite_attempt_budget_survives_restart_and_success_clears_it_in_the_membership_commit()
    {
        using var remote = new Remote();
        using var initial = Store(remote);
        using var keys = Keys(remote);
        var clock = new Clock();
        var gm = User(initial, "gm");
        var player = User(initial, "player");
        var dossier = Character(initial, player);
        var service = Service(initial, keys, clock);
        var campaign = Create(service, gm);
        var invite = service.CreateInvite(gm, campaign.CampaignId, new("synthetic-invite"));
        for (int attempt = 0; attempt < 10; attempt++)
        {
            using var replica = Store(remote);
            Assert.Throws<CampaignInviteRejectedException>(() => Service(replica, keys, clock).RedeemJoinCode(player,
                new("CM" + new string('A', 26), dossier.DossierId, dossier.DossierId, 1, true, "synthetic-invalid")));
            using (replica.Enter()) Assert.Equal(attempt + 1, replica.CampaignInviteAttemptsByUserId[player.UserId].Failures);
        }
        using var final = Store(remote);
        var reader = Service(final, keys, clock);
        Assert.Throws<CampaignInviteThrottledException>(() => reader.RedeemInvite(player, invite.InviteId, Redeem(invite, dossier)));
        clock.Now = clock.Now.AddMinutes(11);
        int writes = remote.HeadPosts;
        Assert.NotNull(reader.RedeemInvite(player, invite.InviteId, Redeem(invite, dossier)));
        Assert.Equal(writes + 1, remote.HeadPosts);
        using var cold = Store(remote);
        using (cold.Enter()) Assert.Empty(cold.CampaignInviteAttemptsByUserId);
    }

    [Fact]
    public void Revoked_invite_and_reassigned_principal_are_observed_by_existing_services()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        using var keys = Keys(remote);
        var gm = User(writer, "gm");
        var player = User(writer, "player");
        var dossier = Character(writer, player);
        var service = Service(writer, keys);
        var campaign = Create(service, gm);
        var invite = service.CreateInvite(gm, campaign.CampaignId, new("synthetic-invite"));
        using var other = Store(remote);
        Service(other, keys).RevokeInvite(gm, campaign.CampaignId, invite.InviteId);
        Assert.Throws<CampaignInviteRejectedException>(() => service.RedeemInvite(player, invite.InviteId, Redeem(invite, dossier)));
        using (other.Enter())
        {
            other.UsersById[gm.UserId] = gm with { SubjectId = "replacement-subject", LinkedPrincipals = [] };
            other.PersistLocked();
        }
        int writes = remote.HeadPosts;
        Assert.Throws<CampaignCollaborationAccessDeniedException>(() => service.ListCampaigns(gm));
        Assert.Throws<CampaignCollaborationAccessDeniedException>(() => Create(service, gm));
        Assert.Throws<CampaignCollaborationAccessDeniedException>(() => service.CreateInvite(gm, campaign.CampaignId, new("another-invite")));
        Assert.Equal(writes, remote.HeadPosts);
    }

    [Fact]
    public void Validation_callback_rollback_leaves_no_partial_campaign_and_allows_clean_retry()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        using var keys = Keys(remote);
        var gm = User(store, "gm");
        var service = Service(store, keys);
        int writes = remote.HeadPosts;
        store.CampaignCollaborationPersistenceFaultInjector = () => throw new InvalidDataException("Synthetic callback failure");
        Assert.Throws<InvalidDataException>(() => Create(service, gm));
        Assert.Equal(writes, remote.HeadPosts);
        store.CampaignCollaborationPersistenceFaultInjector = null;
        Assert.Empty(service.ListCampaigns(gm));
        Assert.NotNull(Create(service, gm));
    }

    [Fact]
    public void Primary_rejects_ephemeral_invite_keys_unfenced_core_edits_and_cached_reads_on_outage()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        using var keys = Keys(remote);
        var gm = User(store, "gm");
        Assert.Throws<InvalidOperationException>(() => new CampaignCollaborationService(store));
        var service = Service(store, keys);
        var campaign = Create(service, gm);
        Assert.Throws<InvalidOperationException>(() => service.UpdateSharedSheet(gm, campaign.CampaignId, "synthetic-dossier",
            new(1, "Synthetic", "Synthetic", "active", "Synthetic reason", "synthetic-edit")));
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => service.ListCampaigns(gm));
        Assert.Throws<InvalidOperationException>(() => service.GetCampaign(gm, campaign.CampaignId));
        Assert.False(Directory.Exists(_root));
    }

    [Theory]
    [InlineData("old-schema")]
    [InlineData("missing-window")]
    [InlineData("foreign-owner")]
    [InlineData("invalid-count")]
    public async Task Primary_restore_rejects_lost_or_invalid_invitation_admission_state(string corruption)
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var user = User(store, "synthetic");
        using var transport = remote.Store();
        var head = (await transport.ReadAsync("community", CancellationToken.None))!;
        var payload = JsonNode.Parse(head.Bytes)!;
        var snapshot = payload["snapshot"]!;
        if (corruption == "old-schema") payload["schema"] = "chummer.hub.community-primary/v2";
        else if (corruption == "missing-window") snapshot["campaignInviteAttempts"] = null;
        else snapshot["campaignInviteAttempts"]![corruption == "foreign-owner" ? "missing-user" : user.UserId] =
            JsonSerializer.SerializeToNode(new CampaignInviteAttemptWindow(DateTimeOffset.UtcNow,
                corruption == "invalid-count" ? 11 : 1), new JsonSerializerOptions(JsonSerializerDefaults.Web));
        await transport.CompareExchangeAsync("community", head, Guid.NewGuid(),
            Encoding.UTF8.GetBytes(payload.ToJsonString()), CancellationToken.None);
        int writes = remote.HeadPosts;
        Assert.Throws<InvalidDataException>(() => Store(remote));
        Assert.Equal(writes, remote.HeadPosts);
        Assert.False(Directory.Exists(_root));
    }

    private sealed class Clock : TimeProvider
    {
        internal DateTimeOffset Now { get; set; } = DateTimeOffset.UtcNow;
        public override DateTimeOffset GetUtcNow() => Now;
    }

    public void Dispose()
    {
        if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
    }
}
