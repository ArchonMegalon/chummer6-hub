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

public sealed class MembershipTeablePersistenceTests : IDisposable
{
    private static readonly DateTimeOffset Now = new(2026, 9, 23, 9, 0, 0, TimeSpan.Zero);
    private readonly string _root = Path.Combine(Path.GetTempPath(), "membership-primary-" + Guid.NewGuid().ToString("N"));
    private IConfiguration Config(string mode = "teable", bool customStatus = false) => new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
    {
        ["CHUMMER_BILLING_MEMBERSHIP_STORAGE_PROVIDER"] = mode,
        ["CHUMMER_MYFIRSTBOOK_USAGE_STORAGE_PROVIDER"] = mode,
        ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(_root, "billing.json"),
        ["CHUMMER_MYFIRSTBOOK_USAGE_STORE_PATH"] = Path.Combine(_root, "usage.json"),
        ["BRILLIANT_DIRECTORIES_SYNC_SECRET"] = "synthetic-only",
        ["BRILLIANT_DIRECTORIES_SUPPORTER_PLAN_URL"] = "https://billing.example.invalid/supporter",
        ["BRILLIANT_DIRECTORIES_SUPPORTED_MEMBERSHIP_STATUSES"] = customStatus ? "active, trial, cancelled" : null,
        ["BRILLIANT_DIRECTORIES_ACTIVE_MEMBERSHIP_STATUSES"] = customStatus ? "active, trial" : null
    }).Build();
    private BrilliantDirectoriesBillingStore Membership(Remote remote, bool customStatus = false)
        => new(Config(customStatus: customStatus), primary: remote.Store());
    private MyFirstBookUsageStore Usage(Remote remote) => new(Config(), primary: remote.Store());
    private BrilliantDirectoriesBillingService Service(BrilliantDirectoriesBillingStore membership,
        MyFirstBookUsageStore usage, bool customStatus = false) => new(membership, usage, Config(customStatus: customStatus));
    private static BrilliantDirectoriesMemberSyncRequest Request(string user = "user", string status = "active", bool active = true)
        => new(user, "member-" + user, user + "@example.invalid", "supporter", "ignored provider label", status, active, Now);

    [Fact]
    public void Membership_and_consumed_allowance_restore_together_without_local_files()
    {
        using var remote = new Remote();
        using var membership = Membership(remote);
        using var usage = Usage(remote);
        var service = Service(membership, usage);
        service.SyncMember(Request(), "synthetic-only");
        var expected = service.GetAccount("user");
        var consumed = service.ConsumeMyFirstBookQuota("user", Now);
        Assert.Equal(1, consumed.Quota.MonthlyRemaining);
        Assert.Empty(membership.Members);
        using var coldMembership = Membership(remote);
        using var coldUsage = Usage(remote);
        var restored = Service(coldMembership, coldUsage);
        Assert.Equal(expected, restored.GetAccount("USER"));
        Assert.Equal(expected, restored.GetAccountByEmail(" USER@EXAMPLE.INVALID "));
        Assert.Equal(consumed.Quota, restored.GetMyFirstBookQuota("user", Now));
        Assert.Equal(1, restored.GetMyFirstBookQuota("other", Now).MonthlyLimit);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Another_instances_downgrade_is_visible_before_the_next_allowance_read()
    {
        using var remote = new Remote();
        using var first = Membership(remote);
        using var second = Membership(remote);
        using var usage = Usage(remote);
        var service = Service(first, usage);
        service.SyncMember(Request(), "synthetic-only");
        service.ConsumeMyFirstBookQuota("user", Now);
        Service(second, usage).SyncMember(Request(status: "expired", active: false), "synthetic-only");
        var quota = service.GetMyFirstBookQuota("user", Now);
        Assert.False(quota.SupporterActive);
        Assert.Equal(1, quota.MonthlyLimit);
        Assert.Equal(0, quota.MonthlyRemaining);
        Assert.Throws<InvalidOperationException>(() => service.ConsumeMyFirstBookQuota("user", Now));
    }

    [Fact]
    public void Invalid_sync_auth_or_plan_status_never_touches_the_primary()
    {
        using var remote = new Remote { FailReads = true };
        using var membership = Membership(remote);
        using var usage = Usage(remote);
        var service = Service(membership, usage);
        Assert.Throws<UnauthorizedAccessException>(() => service.SyncMember(Request(), "wrong"));
        Assert.Throws<InvalidOperationException>(() => service.SyncMember(Request(active: false), "synthetic-only"));
        Assert.Throws<InvalidOperationException>(() => service.SyncMember(Request() with { PlanKey = "invented" }, "synthetic-only"));
        Assert.Empty(remote.Rows);
        Assert.Empty(membership.Members);
    }

    [Fact]
    public void Conflicting_membership_sync_requires_new_read_and_does_not_drop_the_winner()
    {
        using var remote = new Remote();
        using var first = Membership(remote);
        using var second = Membership(remote);
        using var usage = Usage(remote);
        var service = Service(first, usage);
        remote.BeforeHeadPost = () => Service(second, usage).SyncMember(Request("winner"), "synthetic-only");
        Assert.Throws<TeableRevisionConflictException>(() => service.SyncMember(Request("loser"), "synthetic-only"));
        Assert.Empty(first.Members);
        Assert.NotNull(service.GetAccount("winner"));
        Assert.Null(service.GetAccount("loser"));
        service.SyncMember(Request("loser"), "synthetic-only");
        Assert.NotNull(service.GetAccount("winner"));
        Assert.NotNull(service.GetAccount("loser"));
        Assert.Equal(2, remote.HeadPosts);
    }

    [Fact]
    public void Lost_sync_acknowledgement_requires_readback_without_replaying_the_sync()
    {
        using var remote = new Remote { CommitThenFailHard = true };
        using var membership = Membership(remote);
        using var usage = Usage(remote);
        var service = Service(membership, usage);
        Assert.Throws<IOException>(() => service.SyncMember(Request(), "synthetic-only"));
        Assert.Empty(membership.Members);
        Assert.True(service.GetAccount("user")!.SupporterActive);
        Assert.Equal(2, service.GetMyFirstBookQuota("user", Now).MonthlyLimit);
        Assert.Equal(1, remote.HeadPosts);
    }

    [Fact]
    public void Outage_cannot_serve_cached_or_ambient_memberships_or_silently_assume_free()
    {
        using var localMembership = new BrilliantDirectoriesBillingStore(Config("local"));
        using var localUsage = new MyFirstBookUsageStore(Config("local"));
        var local = Service(localMembership, localUsage);
        local.SyncMember(Request("local-only"), "synthetic-only");
        using var remote = new Remote();
        using var membership = Membership(remote);
        using var usage = Usage(remote);
        var service = Service(membership, usage);
        Assert.Null(service.GetAccount("local-only"));
        service.SyncMember(Request(), "synthetic-only");
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => service.GetAccount("user"));
        Assert.Throws<HttpRequestException>(() => service.GetMyFirstBookQuota("user", Now));
        Assert.Empty(membership.Members);
        Assert.True(local.GetAccount("local-only")!.SupporterActive);
        Assert.Single(Directory.GetFiles(_root));
    }

    [Fact]
    public void Configured_status_mapping_is_shared_by_sync_and_restore_and_drift_requires_reconciliation()
    {
        using var remote = new Remote();
        using var membership = Membership(remote, customStatus: true);
        using var usage = Usage(remote);
        var service = Service(membership, usage, customStatus: true);
        service.SyncMember(Request(status: "Trial"), "synthetic-only");
        using var cold = Membership(remote, customStatus: true);
        Assert.Equal(2, Service(cold, usage, customStatus: true).GetMyFirstBookQuota("user", Now).MonthlyLimit);
        using var incompatible = Membership(remote);
        Assert.Throws<InvalidDataException>(() => Service(incompatible, usage).GetAccount("user"));
        Assert.Equal(1, remote.HeadPosts);
    }

    [Theory]
    [InlineData("duplicate")]
    [InlineData("plan")]
    [InlineData("status")]
    [InlineData("active")]
    [InlineData("timestamp")]
    public async Task Corrupt_membership_is_rejected_without_repair_or_entitlement_inference(string fault)
    {
        using var remote = new Remote();
        using var membership = Membership(remote);
        using var usage = Usage(remote);
        var service = Service(membership, usage);
        service.SyncMember(Request(), "synthetic-only");
        var head = await remote.Store().ReadAsync("billing-membership");
        var state = JsonNode.Parse(head!.Bytes)!;
        var row = state["entries"]![0]!;
        switch (fault)
        {
            case "duplicate": state["entries"]!.AsArray().Add(row.DeepClone()); break;
            case "plan": row["planKey"] = "invented"; break;
            case "status": row["membershipStatus"] = "invented"; break;
            case "active": row["supporterActive"] = false; break;
            case "timestamp": row["syncedAtUtc"] = default(DateTimeOffset); break;
        }
        await remote.Store().CompareExchangeAsync("billing-membership", head, Guid.NewGuid(), JsonSerializer.SerializeToUtf8Bytes(state));
        int posts = remote.HeadPosts;
        Assert.Throws<InvalidDataException>(() => service.GetMyFirstBookQuota("user", Now));
        Assert.Empty(membership.Members);
        Assert.Equal(posts, remote.HeadPosts);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Failed_local_sync_does_not_publish_an_uncommitted_upgrade()
    {
        using var membership = new BrilliantDirectoriesBillingStore(Config("local"));
        using var usage = new MyFirstBookUsageStore(Config("local"));
        Directory.CreateDirectory(membership.StoragePath);
        var service = Service(membership, usage);
        Assert.ThrowsAny<IOException>(() => service.SyncMember(Request(), "synthetic-only"));
        Assert.Empty(membership.Members);
        Assert.Equal(1, service.GetMyFirstBookQuota("user", Now).MonthlyLimit);
    }

    [Fact]
    public void Primary_registration_rejects_ambient_configuration_and_has_no_local_path_or_history_erasure_claim()
    {
        Assert.Throws<InvalidOperationException>(() => new BrilliantDirectoriesBillingStore(Config()));
        Assert.Throws<InvalidOperationException>(() => new BrilliantDirectoriesBillingStore(Config("unknown")));
        using var remote = new Remote();
        using var membership = Membership(remote);
        Assert.Throws<InvalidOperationException>(() => membership.Gate);
        Assert.Throws<InvalidOperationException>(() => membership.StoragePath);
        Assert.Throws<InvalidOperationException>(membership.EnsureAccountErasureSupported);
        if (!OperatingSystem.IsLinux() || System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture != System.Runtime.InteropServices.Architecture.X64) return;
        Directory.CreateDirectory(_root, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        string token = Path.Combine(_root, "synthetic-token");
        File.WriteAllText(token, "synthetic-only");
        File.SetUnixFileMode(token, UnixFileMode.UserRead | UnixFileMode.UserWrite);
        var config = new ConfigurationBuilder().AddConfiguration(Config()).AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_TEABLE_ORIGIN"] = "https://teable.example/",
            ["CHUMMER_BILLING_MEMBERSHIP_TEABLE_TABLE_ID"] = "tbl1234567890123456",
            ["CHUMMER_BILLING_MEMBERSHIP_TEABLE_TOKEN_FILE"] = token
        }).Build();
        var services = new ServiceCollection();
        services.AddSingleton<IConfiguration>(config);
        services.AddHubAccountsAndCommunityContext();
        using var provider = services.BuildServiceProvider();
        Assert.NotNull(provider.GetRequiredService<BrilliantDirectoriesBillingStore>());
        Assert.Single(Directory.GetFiles(_root));
    }

    public void Dispose() { if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true); }
}
