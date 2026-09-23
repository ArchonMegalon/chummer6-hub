using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Billing;
using Chummer.Storage.Teable;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;

namespace Chummer.Tests;

public sealed class HorizonTeablePersistenceTests : IDisposable
{
    private static readonly DateTimeOffset Now = new(2026, 9, 23, 9, 0, 0, TimeSpan.Zero);
    private readonly string _root = Path.Combine(Path.GetTempPath(), "horizon-primary-" + Guid.NewGuid().ToString("N"));
    private IConfiguration Config(string mode = "teable") => new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
    {
        ["CHUMMER_HORIZON_ARTIFACT_USAGE_STORAGE_PROVIDER"] = mode,
        ["CHUMMER_HORIZON_REQUEST_RECEIPT_STORAGE_PROVIDER"] = mode,
        ["CHUMMER_MYFIRSTBOOK_USAGE_STORAGE_PROVIDER"] = mode,
        ["CHUMMER_BILLING_MEMBERSHIP_STORAGE_PROVIDER"] = mode,
        ["CHUMMER_HORIZON_ARTIFACT_USAGE_STORE_PATH"] = Path.Combine(_root, "horizon.json"),
        ["CHUMMER_HORIZON_ARTIFACT_REQUEST_RECEIPT_STORE_PATH"] = Path.Combine(_root, "receipts.json"),
        ["CHUMMER_MYFIRSTBOOK_USAGE_STORE_PATH"] = Path.Combine(_root, "usage.json"),
        ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(_root, "billing.json"),
        ["BRILLIANT_DIRECTORIES_SYNC_SECRET"] = "synthetic-only",
        ["BRILLIANT_DIRECTORIES_SUPPORTER_PLAN_URL"] = "https://billing.example.invalid/supporter"
    }).Build();
    private BrilliantDirectoriesBillingService Billing(Remote remote) => new(
        new(Config(), primary: remote.Store()), new(Config(), primary: remote.Store()), Config());
    private HorizonArtifactQuotaService Quota(Remote remote, HorizonArtifactUsageStore? store = null)
        => new(store ?? new(Config(), remote.Store()), new(Config()), Billing(remote));
    private HorizonArtifactRequestService Requests(Remote remote, HorizonArtifactRequestReceiptStore receipts)
        => new(new(Config()), Quota(remote), receipts);
    private static HorizonArtifactQuotaRequest UsageRequest(string kind = "tour", int units = 1)
        => new("user", "runsite", kind, UnitsRequested: units);
    private static HorizonArtifactRequestCreateRequest Request(string kind = "tour", string user = "user")
        => new("runsite", kind, user, "runsite:synthetic-preview", "private", true);

    [Fact]
    public void Weekly_usage_restores_without_files_and_keeps_owner_capability_and_window_boundaries()
    {
        using var remote = new Remote();
        var first = Quota(remote).Consume(UsageRequest(), Now);
        var cold = Quota(remote);
        Assert.Equal(first, cold.GetQuota(UsageRequest(), Now));
        Assert.Equal(0, cold.GetQuota(UsageRequest("map"), Now).WindowUsed);
        Assert.Equal(0, cold.GetQuota(UsageRequest() with { UserId = "other" }, Now).WindowUsed);
        Assert.Equal(0, cold.GetQuota(UsageRequest(), Now.AddDays(7)).WindowUsed);
        Assert.Throws<InvalidOperationException>(() => cold.Consume(UsageRequest(), Now));
        Assert.Equal(1, remote.HeadPosts);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Competing_weekly_consumers_cannot_both_charge_the_last_slot()
    {
        using var remote = new Remote();
        var first = Quota(remote);
        var second = Quota(remote);
        remote.BeforeHeadPost = () => second.Consume(UsageRequest(), Now);
        Assert.Throws<TeableRevisionConflictException>(() => first.Consume(UsageRequest(), Now));
        Assert.Equal(1, first.GetQuota(UsageRequest(), Now).WindowUsed);
        Assert.Equal(1, remote.HeadPosts);
    }

    [Fact]
    public void Monthly_multi_unit_request_is_one_commit_not_a_loop_of_partial_charges()
    {
        using var remote = new Remote();
        var billing = Billing(remote);
        billing.SyncMember(new BrilliantDirectoriesMemberSyncRequest("user", "member", "user@example.invalid",
            "supporter", "Supporter", "active", true, Now), "synthetic-only");
        int before = remote.HeadPosts;
        var request = new HorizonArtifactQuotaRequest("user", "origin-dossier", "premium_authoring_credit", UnitsRequested: 2);
        var consumed = Quota(remote).Consume(request, Now);
        Assert.Equal(2, consumed.WindowUsed);
        Assert.Equal(0, consumed.WindowRemaining);
        Assert.Equal(before + 1, remote.HeadPosts);
        Assert.Equal(2, Billing(remote).GetMyFirstBookQuota("user", Now).MonthlyUsed);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Competing_monthly_batch_does_not_leave_a_partial_charge()
    {
        using var remote = new Remote();
        Billing(remote).SyncMember(new BrilliantDirectoriesMemberSyncRequest("user", "member", "user@example.invalid",
            "supporter", "Supporter", "active", true, Now), "synthetic-only");
        int before = remote.HeadPosts;
        var first = Quota(remote);
        remote.BeforeHeadPost = () => Billing(remote).ConsumeMyFirstBookQuota("user", Now);
        Assert.Throws<TeableRevisionConflictException>(() => first.Consume(new("user", "origin-dossier", "premium_authoring_credit", UnitsRequested: 2), Now));
        Assert.Equal(1, Billing(remote).GetMyFirstBookQuota("user", Now).MonthlyUsed);
        Assert.Equal(before + 1, remote.HeadPosts);
    }

    [Fact]
    public void Huge_weekly_request_cannot_overflow_allowance_checks_even_in_legacy_local_mode()
    {
        var config = Config("local");
        using var usage = new HorizonArtifactUsageStore(config);
        var quota = new HorizonArtifactQuotaService(usage, new(config), new(new(config), new(config), config));
        quota.Consume(UsageRequest(), Now);
        Assert.Throws<InvalidOperationException>(() => quota.Consume(UsageRequest(units: int.MaxValue), Now));
        Assert.Equal(1, quota.GetQuota(UsageRequest(), Now).WindowUsed);
    }

    [Fact]
    public void Accepted_and_blocked_receipts_restore_with_owner_filters_and_without_reconsuming_quota()
    {
        using var remote = new Remote();
        using var receipts = new HorizonArtifactRequestReceiptStore(Config(), remote.Store());
        var service = Requests(remote, receipts);
        var accepted = service.BuildRequest(Request(), Now, consumeQuota: true);
        var blocked = service.BuildRequest(Request() with { ExternalProcessingConsent = false }, Now.AddSeconds(1), consumeQuota: true);
        Assert.Equal("accepted", accepted.Status);
        Assert.Equal("blocked", blocked.Status);
        using var coldStore = new HorizonArtifactRequestReceiptStore(Config(), remote.Store());
        var cold = Requests(remote, coldStore);
        Assert.Equal(JsonSerializer.Serialize(accepted), JsonSerializer.Serialize(cold.FindReceiptForUser(accepted.RequestId, "USER")));
        Assert.Null(cold.FindReceiptForUser(accepted.RequestId, "other"));
        Assert.Null(cold.FindAcceptedPublicSafeReceipt(accepted.RequestId));
        Assert.Equal(2, cold.ListRecentReceipts("runsite", "user", "tour").Count);
        Assert.Empty(cold.ListRecentReceipts("runsite", "other"));
        Assert.Equal(1, Quota(remote).GetQuota(UsageRequest(), Now).WindowUsed);
        Assert.Equal(3, remote.HeadPosts);
        Assert.Empty(coldStore.Receipts);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Governed_render_receipt_restoration_neither_enables_the_provider_nor_consumes_allowance()
    {
        using var remote = new Remote();
        using var receipts = new HorizonArtifactRequestReceiptStore(Config(), remote.Store());
        var request = Request("scene_render") with
        {
            GovernedRenderRequest = new("synthetic-work", "user", "Approved preview", "account-owner", "de-DE",
                TruthRefs: ["runsite:synthetic-preview"], EvidenceRefs: ["review:synthetic"],
                Artifacts: [new("scene", "preview", "runsite/scene", "{\"prompt_ref\":\"runsite:synthetic-preview\"}", "png", "synthetic-scene")])
        };
        var original = Requests(remote, receipts).BuildRequest(request, Now, consumeQuota: false);
        Assert.Equal("blocked", original.Status); // Capability remains disabled.
        Assert.NotNull(original.GovernedRenderRequest);
        Assert.Null(original.Quota);
        using var cold = new HorizonArtifactRequestReceiptStore(Config(), remote.Store());
        Assert.Equal(JsonSerializer.Serialize(original), JsonSerializer.Serialize(cold.FindByRequestId(original.RequestId)));
        Assert.False(new HorizonCapabilityService(Config()).GetCapability("runsite", "scene_render").Enabled);
        Assert.Equal(1, remote.HeadPosts);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Concurrent_receipt_append_preserves_the_winner_and_requires_a_new_read()
    {
        using var remote = new Remote();
        using var first = new HorizonArtifactRequestReceiptStore(Config(), remote.Store());
        using var second = new HorizonArtifactRequestReceiptStore(Config(), remote.Store());
        var composer = new HorizonArtifactRequestService(new(Config()));
        var winner = composer.BuildRequest(Request("map"), Now);
        var loser = composer.BuildRequest(Request(), Now);
        remote.BeforeHeadPost = () => second.Append(winner);
        Assert.Throws<TeableRevisionConflictException>(() => first.Append(loser));
        Assert.NotNull(first.FindByRequestId(winner.RequestId));
        Assert.Null(first.FindByRequestId(loser.RequestId));
        first.Append(loser);
        Assert.Equal(2, first.ListRecent().Count);
        Assert.Equal(2, remote.HeadPosts);
    }

    [Fact]
    public void Unknown_receipt_commit_is_found_by_readback_without_another_write()
    {
        using var remote = new Remote { CommitThenFailHard = true };
        using var receipts = new HorizonArtifactRequestReceiptStore(Config(), remote.Store());
        var original = new HorizonArtifactRequestService(new(Config())).BuildRequest(Request(), Now);
        Assert.Throws<IOException>(() => receipts.Append(original));
        Assert.Equal(original.RequestId, receipts.FindByRequestId(original.RequestId)!.RequestId);
        Assert.Equal(1, remote.HeadPosts);
    }

    [Theory]
    [InlineData("receipt-owner")]
    [InlineData("receipt-status")]
    [InlineData("receipt-quota")]
    [InlineData("usage-duplicate")]
    [InlineData("usage-count")]
    public async Task Invalid_primary_data_never_becomes_a_receipt_or_a_fresh_allowance(string fault)
    {
        using var remote = new Remote();
        using var receipts = new HorizonArtifactRequestReceiptStore(Config(), remote.Store());
        Requests(remote, receipts).BuildRequest(Request(), Now, consumeQuota: true);
        string stream = fault.StartsWith("receipt", StringComparison.Ordinal) ? "horizon-request-receipts" : "horizon-artifact-usage";
        var head = await remote.Store().ReadAsync(stream);
        var state = JsonNode.Parse(head!.Bytes)!;
        var row = state["entries"]![0]!;
        switch (fault)
        {
            case "receipt-owner": row["requestedByUserId"] = "other"; break;
            case "receipt-status": row["status"] = "complete"; break;
            case "receipt-quota": row["quota"]!["userId"] = "other"; break;
            case "usage-duplicate": state["entries"]!.AsArray().Add(row.DeepClone()); break;
            case "usage-count": row["used"] = -1; break;
        }
        await remote.Store().CompareExchangeAsync(stream, head, Guid.NewGuid(), JsonSerializer.SerializeToUtf8Bytes(state));
        int posts = remote.HeadPosts;
        Assert.Throws<InvalidDataException>(() =>
        {
            if (fault.StartsWith("receipt", StringComparison.Ordinal)) receipts.ListRecent();
            else Quota(remote).GetQuota(UsageRequest(), Now);
        });
        Assert.Equal(posts, remote.HeadPosts);
    }

    [Fact]
    public void Failure_to_read_usage_or_receipts_does_not_fall_back_to_cached_or_empty_state()
    {
        using var remote = new Remote();
        using var receipts = new HorizonArtifactRequestReceiptStore(Config(), remote.Store());
        var service = Requests(remote, receipts);
        var saved = service.BuildRequest(Request(), Now, consumeQuota: true);
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => receipts.FindByRequestId(saved.RequestId));
        Assert.Throws<HttpRequestException>(() => Quota(remote).GetQuota(UsageRequest(), Now));
        Assert.Empty(receipts.Receipts);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Both_primary_registrations_require_private_explicit_credentials_and_reject_erasure_claims()
    {
        Assert.Throws<InvalidOperationException>(() => new HorizonArtifactUsageStore(Config()));
        Assert.Throws<InvalidOperationException>(() => new HorizonArtifactRequestReceiptStore(Config()));
        using var remote = new Remote();
        using var usage = new HorizonArtifactUsageStore(Config(), remote.Store());
        using var receipts = new HorizonArtifactRequestReceiptStore(Config(), remote.Store());
        Assert.Throws<InvalidOperationException>(usage.EnsureAccountErasureSupported);
        Assert.Throws<InvalidOperationException>(receipts.EnsureAccountErasureSupported);
        if (!OperatingSystem.IsLinux() || System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture != System.Runtime.InteropServices.Architecture.X64) return;
        Directory.CreateDirectory(_root, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        string token = Path.Combine(_root, "synthetic-token");
        File.WriteAllText(token, "synthetic-only");
        File.SetUnixFileMode(token, UnixFileMode.UserRead | UnixFileMode.UserWrite);
        var config = new ConfigurationBuilder().AddConfiguration(Config()).AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_TEABLE_ORIGIN"] = "https://teable.example/",
            ["CHUMMER_HORIZON_ARTIFACT_USAGE_TEABLE_TABLE_ID"] = "tbl1234567890123456",
            ["CHUMMER_HORIZON_ARTIFACT_USAGE_TEABLE_TOKEN_FILE"] = token,
            ["CHUMMER_HORIZON_REQUEST_RECEIPT_TEABLE_TABLE_ID"] = "tbl1234567890123456",
            ["CHUMMER_HORIZON_REQUEST_RECEIPT_TEABLE_TOKEN_FILE"] = token
        }).Build();
        var services = new ServiceCollection();
        services.AddSingleton<IConfiguration>(config);
        services.AddHubAccountsAndCommunityContext();
        using var provider = services.BuildServiceProvider();
        Assert.NotNull(provider.GetRequiredService<HorizonArtifactUsageStore>());
        Assert.NotNull(provider.GetRequiredService<HorizonArtifactRequestReceiptStore>());
        Assert.Single(Directory.GetFiles(_root));
    }

    public void Dispose() { if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true); }
}
