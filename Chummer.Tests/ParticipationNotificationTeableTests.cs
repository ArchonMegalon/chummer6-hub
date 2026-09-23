using System.Net;
using System.Text.Json;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;

namespace Chummer.Tests;

public sealed class ParticipationNotificationTeableTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "participation-primary-" + Guid.NewGuid().ToString("N"));
    private readonly List<HttpClient> _clients = [];
    private IConfiguration Configuration(bool enabled) => new ConfigurationBuilder().AddInMemoryCollection(
        new Dictionary<string, string?>
        {
            ["CHUMMER_COMMUNITY_STORAGE_PROVIDER"] = "teable",
            ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community.json"),
            ["CHUMMER_OPERATOR_PARTICIPATION_NOTIFY_ENABLED"] = enabled ? "true" : "false",
            ["CHUMMER_OPERATOR_PARTICIPATION_NOTIFY_TO"] = "operator@example.invalid",
            ["CHUMMER_OPERATOR_PARTICIPATION_EA_API_TOKEN"] = "synthetic-notification-token",
            ["CHUMMER_OPERATOR_PARTICIPATION_EA_PRINCIPAL_ID"] = "synthetic-principal",
            ["CHUMMER_OPERATOR_PARTICIPATION_EA_BINDING_ID"] = "synthetic-binding",
            ["CHUMMER_OPERATOR_PARTICIPATION_EA_BASE_URL"] = "https://ea.example.invalid"
        }).Build();
    private CommunityStore Store(Remote remote) => new(Configuration(false), NullLogger<CommunityStore>.Instance,
        remote.Store(), ownsPrimary: true);
    private ParticipationOperatorNotificationService Service(CommunityStore store, Delivery delivery, bool enabled = true)
    {
        var client = new HttpClient(delivery, disposeHandler: false);
        _clients.Add(client);
        return new(client, store, Configuration(enabled));
    }
    private static HubUserDto User(CommunityStore store) => new AccountService(store)
        .EnsureUser("synthetic-subject", "Synthetic runner", "runner@example.invalid");
    private static Task<ParticipationOperatorNotificationReceipt?> Notify(ParticipationOperatorNotificationService service,
        HubUserDto user) => service.NotifyFirstActionIfNeededAsync(user, user.Email, "package", "/packages", "email", CancellationToken.None);

    [Fact]
    public async Task Account_receipts_restore_without_local_files_or_external_dispatch()
    {
        using var remote = new Remote();
        using var delivery = new Delivery();
        using var writer = Store(remote);
        var user = User(writer);
        var receipt = await Notify(Service(writer, delivery, enabled: false), user);
        Assert.Equal("suppressed_disabled", receipt!.Status);
        using var cold = Store(remote);
        var restored = Assert.Single(Service(cold, delivery, enabled: false).ListReceiptsForUser(user.UserId));
        Assert.Equal(receipt.ReceiptId, restored.ReceiptId);
        Assert.Equal(receipt.EmailHash, restored.EmailHash);
        Assert.Empty(Service(cold, delivery, enabled: false).ListReceiptsForUser("foreign-user"));
        Assert.Equal(0, delivery.Calls);
        Assert.False(Directory.Exists(_root));
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => Service(cold, delivery).ListReceiptsForUser(user.UserId));
    }

    [Fact]
    public async Task Successful_dispatch_has_a_durable_pending_claim_before_sending_and_a_cold_final_receipt()
    {
        using var remote = new Remote();
        using var delivery = new Delivery();
        using var store = Store(remote);
        var user = User(store);
        delivery.BeforeResponse = () =>
        {
            using var observer = Store(remote);
            var pending = Assert.Single(Service(observer, delivery).ListReceiptsForUser(user.UserId));
            Assert.Equal("pending", pending.Status);
            Assert.DoesNotContain(user.Email, delivery.Body!, StringComparison.Ordinal);
        };
        var receipt = await Notify(Service(store, delivery), user);
        Assert.Equal("sent", receipt!.Status);
        Assert.Equal("synthetic-delivery", receipt.DeliveryRef);
        using var cold = Store(remote);
        var duplicate = await Notify(Service(cold, delivery), user);
        Assert.Equal(receipt.ReceiptId, duplicate!.ReceiptId);
        Assert.Equal("sent", duplicate.Status);
        Assert.Equal(1, delivery.Calls);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public async Task Suppressed_receipt_can_dispatch_once_after_configuration_is_completed()
    {
        using var remote = new Remote();
        using var delivery = new Delivery();
        using var store = Store(remote);
        var user = User(store);
        var suppressed = await Notify(Service(store, delivery, enabled: false), user);
        using var cold = Store(remote);
        var sent = await Notify(Service(cold, delivery), user);
        Assert.Equal(suppressed!.ReceiptId, sent!.ReceiptId);
        Assert.Equal("sent", sent.Status);
        Assert.Equal(1, delivery.Calls);
    }

    [Theory]
    [InlineData("failed_delivery")]
    [InlineData("pending")]
    public async Task Historical_ambiguous_receipts_never_resend_automatically(string status)
    {
        using var remote = new Remote();
        using var delivery = new Delivery();
        using var store = Store(remote);
        var user = User(store);
        var receipt = await Notify(Service(store, delivery, enabled: false), user);
        using (store.Enter())
        {
            store.ParticipationNotificationReceipts[0] = receipt! with { Status = status };
            store.PersistLocked();
        }
        using var cold = Store(remote);
        Assert.Equal(status, (await Notify(Service(cold, delivery), user))!.Status);
        Assert.Equal(0, delivery.Calls);
    }

    [Fact]
    public async Task Failed_bridge_response_is_unknown_and_never_replayed_or_copied_into_account_receipts()
    {
        using var remote = new Remote();
        using var delivery = new Delivery { Status = HttpStatusCode.ServiceUnavailable };
        using var store = Store(remote);
        var user = User(store);
        var result = await Notify(Service(store, delivery), user);
        Assert.Equal("delivery_unknown", result!.Status);
        Assert.Equal("ea_delivery_outcome_unknown", result.FailureReason);
        Assert.DoesNotContain("synthetic-sensitive-response", JsonSerializer.Serialize(result), StringComparison.Ordinal);
        using var cold = Store(remote);
        Assert.Equal("delivery_unknown", (await Notify(Service(cold, delivery), user))!.Status);
        Assert.Equal(1, delivery.Calls);
    }

    [Fact]
    public async Task Lost_claim_acknowledgement_never_sends_or_replays_after_cold_restore()
    {
        using var remote = new Remote();
        using var delivery = new Delivery();
        using var store = Store(remote);
        var user = User(store);
        remote.CommitThenFailHard = true;
        await Assert.ThrowsAsync<IOException>(() => Notify(Service(store, delivery), user));
        using var cold = Store(remote);
        Assert.Equal("pending", (await Notify(Service(cold, delivery), user))!.Status);
        Assert.Equal(0, delivery.Calls);
    }

    [Fact]
    public async Task Competing_admission_cannot_send_before_winning_the_primary_claim()
    {
        using var remote = new Remote();
        using var delivery = new Delivery();
        using var store = Store(remote);
        var user = User(store);
        using var competitor = Store(remote);
        var rival = Service(competitor, delivery);
        remote.BeforeHeadPost = () => Assert.Equal("sent", Notify(rival, user).GetAwaiter().GetResult()!.Status);
        await Assert.ThrowsAsync<Chummer.Storage.Teable.TeableRevisionConflictException>(() => Notify(Service(store, delivery), user));
        Assert.Equal(1, delivery.Calls);
        using var cold = Store(remote);
        Assert.Equal("sent", Assert.Single(Service(cold, delivery).ListReceiptsForUser(user.UserId)).Status);
    }

    [Theory]
    [InlineData("removed")]
    [InlineData("receipt_changed")]
    [InlineData("owner_changed")]
    public async Task Delayed_reply_cannot_resurrect_a_removed_or_changed_account_receipt(string mutation)
    {
        using var remote = new Remote();
        using var delivery = new Delivery { Hold = true };
        using var store = Store(remote);
        var user = User(store);
        Task<ParticipationOperatorNotificationReceipt?> pending = Notify(Service(store, delivery), user);
        await delivery.Entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        try
        {
            // A different instance/thread can change authority while the network wait is pending.
            await Task.Run(() =>
            {
                using var writer = Store(remote);
                using (writer.Enter())
                {
                    if (mutation == "removed") writer.ParticipationNotificationReceipts.Clear();
                    else if (mutation == "receipt_changed") writer.ParticipationNotificationReceipts[0] =
                        writer.ParticipationNotificationReceipts[0] with { Status = "revoked" };
                    else writer.UsersById[user.UserId] = user with
                    {
                        SubjectId = "new-owner", LinkedPrincipals = ["new-owner"], UpdatedAtUtc = user.UpdatedAtUtc.AddSeconds(1)
                    };
                    writer.PersistLocked();
                }
            });
        }
        finally { delivery.Release.TrySetResult(); }
        await Assert.ThrowsAsync<InvalidOperationException>(() => pending);
        using var cold = Store(remote);
        var receipts = Service(cold, delivery).ListReceiptsForUser(user.UserId);
        if (mutation == "removed") Assert.Empty(receipts);
        else Assert.Equal(mutation == "receipt_changed" ? "revoked" : "pending", Assert.Single(receipts).Status);
        Assert.Equal(1, delivery.Calls);
    }

    [Fact]
    public async Task Successful_delivery_with_uncertain_final_commit_does_not_trigger_an_error_rewrite_or_resend()
    {
        using var remote = new Remote();
        using var delivery = new Delivery { BeforeResponse = () => remote.CommitThenFailHard = true };
        using var store = Store(remote);
        var user = User(store);
        int before = remote.HeadPosts;
        await Assert.ThrowsAsync<IOException>(() => Notify(Service(store, delivery), user));
        Assert.Equal(before + 2, remote.HeadPosts);
        using var cold = Store(remote);
        Assert.Equal("sent", (await Notify(Service(cold, delivery), user))!.Status);
        Assert.Equal(1, delivery.Calls);
    }

    [Fact]
    public async Task Stale_owner_input_cannot_create_or_send_a_new_receipt()
    {
        using var remote = new Remote();
        using var delivery = new Delivery();
        using var store = Store(remote);
        var user = User(store);
        using (store.Enter())
        {
            store.UsersById[user.UserId] = user with { SubjectId = "new-owner", LinkedPrincipals = ["new-owner"] };
            store.PersistLocked();
        }
        await Assert.ThrowsAsync<InvalidOperationException>(() => Notify(Service(store, delivery), user));
        Assert.Empty(Service(store, delivery).ListReceiptsForUser(user.UserId));
        Assert.Equal(0, delivery.Calls);
    }

    public void Dispose()
    {
        foreach (var client in _clients) client.Dispose();
        if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
    }

    private sealed class Delivery : HttpMessageHandler
    {
        public int Calls { get; private set; }
        public string? Body { get; private set; }
        public HttpStatusCode Status { get; init; } = HttpStatusCode.OK;
        public Action? BeforeResponse { get; set; }
        public bool Hold { get; init; }
        public TaskCompletionSource Entered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Release { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            Calls++;
            Body = await request.Content!.ReadAsStringAsync(ct);
            Assert.DoesNotContain("synthetic-notification-token", Body, StringComparison.Ordinal);
            Entered.TrySetResult();
            if (Hold) await Release.Task.WaitAsync(TimeSpan.FromSeconds(5), ct);
            BeforeResponse?.Invoke();
            return new(Status) { Content = new StringContent(Status == HttpStatusCode.OK
                ? """{"target_ref":"synthetic-delivery"}""" : "synthetic-sensitive-response") };
        }
    }
}
