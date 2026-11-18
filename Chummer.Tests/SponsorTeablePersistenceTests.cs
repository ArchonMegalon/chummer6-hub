using System.Net;
using System.Text;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Boosters;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;

namespace Chummer.Tests;

public sealed class SponsorTeablePersistenceTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "sponsor-teable-" + Guid.NewGuid().ToString("N"));
    private readonly List<HttpClient> _clients = [];
    private IConfiguration Configuration(string provider = "teable") => new ConfigurationBuilder().AddInMemoryCollection(
        new Dictionary<string, string?>
        {
            ["CHUMMER_COMMUNITY_STORAGE_PROVIDER"] = provider,
            ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community.json"),
            ["FLEET_CONTROLLER_BASE_URL"] = "https://fleet.example.invalid",
            ["FLEET_INTERNAL_API_TOKEN"] = "synthetic-only"
        }).Build();

    private CommunityStore Store(Remote remote) => new(Configuration(), NullLogger<CommunityStore>.Instance, remote.Store());
    private BoostSessionService Service(CommunityStore store, FleetHandler handler)
    {
        var accounts = new AccountService(store);
        var client = new HttpClient(handler, disposeHandler: false);
        _clients.Add(client);
        return new(store, accounts, new GroupService(store, accounts),
            new FleetBridgeService(client, Configuration(), NullLogger<FleetBridgeService>.Instance), new RewardService(store));
    }

    private static SponsorSessionStatusDto Pending(BoostSessionService service, CommunityStore store)
    {
        var created = service.Create(new CreateSponsorSessionRequest("synthetic-subject", "synthetic-project"));
        service.RecordConsent(created.SponsorSessionId);
        using (store.Enter())
        {
            var state = store.SponsorSessionsById[created.SponsorSessionId];
            state.FleetLaneId = "synthetic-lane";
            state.Status = "pending_auth";
            store.PersistLocked();
        }
        return service.Get(created.SponsorSessionId)!;
    }

    private static void Revoke(CommunityStore store, string sessionId)
    {
        using var scope = store.Enter();
        var state = store.SponsorSessionsById[sessionId];
        state.Status = "revoked";
        state.StoppedAtUtc = DateTimeOffset.UtcNow;
        state.UpdatedAtUtc = DateTimeOffset.UtcNow;
        state.Events.Add(new SponsorSessionEventDto("synthetic-revocation", "revoked", "Synthetic local revocation", DateTimeOffset.UtcNow));
        store.PersistLocked();
    }

    [Fact]
    public void Intent_consent_and_queries_restore_from_primary_without_local_files_or_Fleet_calls()
    {
        using var remote = new Remote();
        using var fleet = new FleetHandler();
        using var writer = Store(remote);
        var service = Service(writer, fleet);
        var intent = service.Create(new CreateSponsorSessionRequest("synthetic-subject", "synthetic-project"));
        var consent = service.RecordConsent(intent.SponsorSessionId);
        using var cold = Store(remote);
        var restored = Service(cold, fleet);
        Assert.Equal("consented", restored.Get(intent.SponsorSessionId)!.Status);
        Assert.Equal(consent.ConsentedAtUtc, restored.Get(intent.SponsorSessionId)!.ConsentedAtUtc);
        Assert.Equal(intent.SponsorSessionId, restored.FindMostRelevantForUser("synthetic-subject")!.SponsorSessionId);
        Assert.Empty(restored.ListReceipts(intent.SponsorSessionId));
        Assert.Empty(restored.ListBadgesForSessionUser(intent.SponsorSessionId));
        Assert.False(Directory.Exists(_root));
        Assert.Equal(0, fleet.Calls);
    }

    [Fact]
    public async Task Current_Fleet_status_is_saved_on_the_fresh_primary_instance()
    {
        using var remote = new Remote();
        using var fleet = new FleetHandler();
        using var writer = Store(remote);
        var service = Service(writer, fleet);
        var pending = Pending(service, writer);
        var result = await service.RefreshAsync(pending.SponsorSessionId, CancellationToken.None);
        Assert.Equal("active", result.Session.Status);
        Assert.NotNull(result.Session.AuthorizedAtUtc);
        Assert.Equal(1, fleet.Calls);
        using var cold = Store(remote);
        var restored = Service(cold, fleet);
        Assert.Equal("active", restored.Get(pending.SponsorSessionId)!.Status);
        Assert.Contains(restored.ListBadgesForSessionUser(pending.SponsorSessionId), badge => badge.Key == "contributor-ready");
    }

    [Theory]
    [InlineData("revoke")]
    [InlineData("rebind-lane")]
    [InlineData("account-owner")]
    [InlineData("account-aba")]
    public async Task Delayed_Fleet_reply_cannot_overwrite_changed_session_or_account(string change)
    {
        using var remote = new Remote();
        using var fleet = new FleetHandler { Hold = true };
        using var reader = Store(remote);
        var service = Service(reader, fleet);
        var pending = Pending(service, reader);
        using var writer = Store(remote);
        Task<(SponsorSessionStatusDto Session, JsonObject? Fleet)> observation = service.RefreshAsync(pending.SponsorSessionId, CancellationToken.None);
        await fleet.Entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        try
        {
            await Task.Run(() =>
            {
                if (change == "revoke") Revoke(writer, pending.SponsorSessionId);
                else
                {
                    using var scope = writer.Enter();
                    if (change == "rebind-lane") writer.SponsorSessionsById[pending.SponsorSessionId].FleetLaneId = "other-lane";
                    else
                    {
                        var user = writer.UsersById[pending.UserId];
                        writer.UsersById[user.UserId] = user with { SubjectId = "new-subject", LinkedPrincipals = ["new-subject"], UpdatedAtUtc = user.UpdatedAtUtc.AddTicks(1) };
                        writer.PersistLocked();
                        if (change == "account-aba") writer.UsersById[user.UserId] = user with { UpdatedAtUtc = user.UpdatedAtUtc.AddTicks(2) };
                    }
                    writer.PersistLocked();
                }
            }).WaitAsync(TimeSpan.FromSeconds(5));
        }
        finally { fleet.Release.TrySetResult(); }
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => observation);
        Assert.Contains("changed during Fleet observation", error.Message, StringComparison.Ordinal);
        using var cold = Store(remote);
        Assert.NotEqual("active", Service(cold, fleet).Get(pending.SponsorSessionId)!.Status);
        Assert.Equal(1, fleet.Calls);
    }

    [Fact]
    public async Task Same_local_store_is_not_locked_during_Fleet_wait_and_revocation_wins()
    {
        using var local = new CommunityStore(Configuration("local"), NullLogger<CommunityStore>.Instance);
        using var fleet = new FleetHandler { Hold = true };
        var service = Service(local, fleet);
        var pending = Pending(service, local);
        var observation = service.RefreshAsync(pending.SponsorSessionId, CancellationToken.None);
        await fleet.Entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        try { await Task.Run(() => Revoke(local, pending.SponsorSessionId)).WaitAsync(TimeSpan.FromSeconds(5)); }
        finally { fleet.Release.TrySetResult(); }
        await Assert.ThrowsAsync<InvalidOperationException>(() => observation);
        Assert.Equal("revoked", service.Get(pending.SponsorSessionId)!.Status);
    }

    [Fact]
    public async Task Wrong_lane_reply_is_rejected_without_persisting_or_awarding()
    {
        using var remote = new Remote();
        using var fleet = new FleetHandler { LaneId = "wrong-lane" };
        using var store = Store(remote);
        var service = Service(store, fleet);
        var pending = Pending(service, store);
        int writes = remote.HeadPosts;
        await Assert.ThrowsAsync<InvalidDataException>(() => service.RefreshAsync(pending.SponsorSessionId, CancellationToken.None));
        Assert.Equal(writes, remote.HeadPosts);
        Assert.Equal("synthetic-lane", service.Get(pending.SponsorSessionId)!.FleetLaneId);
        Assert.Empty(service.ListBadgesForSessionUser(pending.SponsorSessionId));
    }

    [Fact]
    public async Task Primary_status_observation_never_dispatches_automatic_activation()
    {
        using var remote = new Remote();
        using var fleet = new FleetHandler { Status = "pending_auth", AuthReady = true };
        using var store = Store(remote);
        var service = Service(store, fleet);
        var pending = Pending(service, store);
        var result = await service.RefreshAsync(pending.SponsorSessionId, CancellationToken.None);
        Assert.Equal("lane_pending", result.Session.Status);
        Assert.Equal(1, fleet.Calls);
        Assert.Null(result.Session.ActivatedAtUtc);
    }

    [Fact]
    public async Task Local_status_observation_preserves_existing_automatic_activation()
    {
        using var local = new CommunityStore(Configuration("local"), NullLogger<CommunityStore>.Instance);
        using var fleet = new FleetHandler { Status = "pending_auth", AuthReady = true, AllowActivation = true };
        var service = Service(local, fleet);
        var pending = Pending(service, local);
        var result = await service.RefreshAsync(pending.SponsorSessionId, CancellationToken.None);
        Assert.Equal("active", result.Session.Status);
        Assert.NotNull(result.Session.ActivatedAtUtc);
        Assert.Equal(2, fleet.Calls);
    }

    [Fact]
    public async Task Concurrent_commit_cannot_admit_stale_status_or_recognition()
    {
        using var remote = new Remote();
        using var fleet = new FleetHandler();
        using var first = Store(remote);
        var service = Service(first, fleet);
        var pending = Pending(service, first);
        using var second = Store(remote);
        remote.BeforeHeadPost = () => Revoke(second, pending.SponsorSessionId);
        await Assert.ThrowsAsync<Chummer.Storage.Teable.TeableRevisionConflictException>(
            () => service.RefreshAsync(pending.SponsorSessionId, CancellationToken.None));
        Assert.Throws<InvalidOperationException>(() => service.Get(pending.SponsorSessionId));
        using var cold = Store(remote);
        var restored = Service(cold, fleet);
        Assert.Equal("revoked", restored.Get(pending.SponsorSessionId)!.Status);
        Assert.Empty(restored.ListBadgesForSessionUser(pending.SponsorSessionId));
        Assert.Equal(1, fleet.Calls);
    }

    [Fact]
    public async Task Primary_outage_after_external_read_cannot_use_the_captured_snapshot()
    {
        using var remote = new Remote();
        using var fleet = new FleetHandler { Hold = true };
        using var store = Store(remote);
        var service = Service(store, fleet);
        var pending = Pending(service, store);
        var observation = service.RefreshAsync(pending.SponsorSessionId, CancellationToken.None);
        await fleet.Entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        int writes = remote.HeadPosts;
        remote.FailReads = true;
        fleet.Release.TrySetResult();
        await Assert.ThrowsAsync<HttpRequestException>(() => observation);
        Assert.Throws<InvalidOperationException>(() => service.Get(pending.SponsorSessionId));
        Assert.Equal(writes, remote.HeadPosts);
        Assert.Equal(1, fleet.Calls);
    }

    [Fact]
    public async Task Primary_external_mutations_reject_before_any_Fleet_or_store_write()
    {
        using var remote = new Remote();
        using var fleet = new FleetHandler();
        using var store = Store(remote);
        var service = Service(store, fleet);
        var pending = Pending(service, store);
        int writes = remote.HeadPosts;
        await Assert.ThrowsAsync<NotSupportedException>(() => service.StartContributionAsync(new("synthetic-subject", "synthetic-project"), CancellationToken.None));
        await Assert.ThrowsAsync<NotSupportedException>(() => service.StartDeviceAuthAsync(pending.SponsorSessionId, CancellationToken.None));
        await Assert.ThrowsAsync<NotSupportedException>(() => service.ActivateAsync(pending.SponsorSessionId, CancellationToken.None));
        await Assert.ThrowsAsync<NotSupportedException>(() => service.StopAsync(pending.SponsorSessionId, true, CancellationToken.None));
        Assert.Equal(writes, remote.HeadPosts);
        Assert.Equal(0, fleet.Calls);
    }

    [Fact]
    public async Task Terminal_session_cannot_be_reconsented_or_refreshed_from_Fleet()
    {
        using var remote = new Remote();
        using var fleet = new FleetHandler();
        using var store = Store(remote);
        var service = Service(store, fleet);
        var pending = Pending(service, store);
        Revoke(store, pending.SponsorSessionId);
        int writes = remote.HeadPosts;
        Assert.Throws<InvalidOperationException>(() => service.RecordConsent(pending.SponsorSessionId));
        var result = await service.RefreshAsync(pending.SponsorSessionId, CancellationToken.None);
        Assert.Equal("revoked", result.Session.Status);
        Assert.Null(result.Fleet);
        Assert.Equal(0, fleet.Calls);
        Assert.Equal(writes, remote.HeadPosts);
    }

    [Fact]
    public void Repeated_consent_does_not_reset_a_session_or_duplicate_its_event()
    {
        using var remote = new Remote();
        using var fleet = new FleetHandler();
        using var store = Store(remote);
        var service = Service(store, fleet);
        var pending = Pending(service, store);
        int writes = remote.HeadPosts;
        var repeat = service.RecordConsent(pending.SponsorSessionId);
        Assert.Equal("pending_auth", repeat.Status);
        Assert.Equal(pending.Events.Count, repeat.Events.Count);
        Assert.Equal(writes, remote.HeadPosts);
    }

    [Fact]
    public void Primary_outage_does_not_serve_cached_sponsor_state()
    {
        using var remote = new Remote();
        using var fleet = new FleetHandler();
        using var store = Store(remote);
        var service = Service(store, fleet);
        var pending = Pending(service, store);
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => service.Get(pending.SponsorSessionId));
        Assert.Throws<InvalidOperationException>(() => service.RecordConsent(pending.SponsorSessionId));
        Assert.Equal(0, fleet.Calls);
    }

    private sealed class FleetHandler : HttpMessageHandler
    {
        public bool Hold { get; init; }
        public string Status { get; init; } = "active";
        public string LaneId { get; init; } = "synthetic-lane";
        public bool AuthReady { get; init; }
        public bool AllowActivation { get; init; }
        public int Calls { get; private set; }
        public TaskCompletionSource Entered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Release { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Calls++;
            Assert.Equal("fleet.example.invalid", request.RequestUri!.Host);
            bool activate = AllowActivation && request.Method == HttpMethod.Post;
            if (activate) Assert.EndsWith("/activate", request.RequestUri.AbsolutePath, StringComparison.Ordinal);
            else Assert.Equal(HttpMethod.Get, request.Method);
            Entered.TrySetResult();
            if (Hold) await Release.Task.WaitAsync(ct);
            var payload = new JsonObject { ["lane"] = new JsonObject {
                ["lane_id"] = LaneId, ["status"] = activate ? "active" : Status,
                ["device_auth"] = new JsonObject { ["auth_ready"] = AuthReady }
            } };
            return new(HttpStatusCode.OK) { Content = new StringContent(payload.ToJsonString(), Encoding.UTF8, "application/json") };
        }
    }

    public void Dispose()
    {
        foreach (var client in _clients) client.Dispose();
        if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
    }
}
