using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Chummer.Storage.Teable;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;

namespace Chummer.Tests;

public sealed class AuthoringLedgerTeablePersistenceTests : IDisposable
{
    private static readonly DateTimeOffset Now = new(2026, 9, 23, 7, 0, 0, TimeSpan.Zero);
    private readonly string _root = Path.Combine(Path.GetTempPath(), "authoring-ledger-primary-" + Guid.NewGuid().ToString("N"));
    private IConfiguration Config(string mode = "teable") => new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
    {
        ["CHUMMER_MYFIRSTBOOK_USAGE_STORAGE_PROVIDER"] = mode,
        ["CHUMMER_ORIGIN_PROVIDER_RESERVATION_STORAGE_PROVIDER"] = mode,
        ["CHUMMER_MYFIRSTBOOK_USAGE_STORE_PATH"] = Path.Combine(_root, "usage.json"),
        ["CHUMMER_ORIGIN_PROVIDER_RESERVATION_STORE_PATH"] = Path.Combine(_root, "reservation.json"),
        ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(_root, "billing.json"),
        ["CHUMMER_HORIZON_ARTIFACT_USAGE_STORE_PATH"] = Path.Combine(_root, "horizon.json"),
        ["CHUMMER_ORIGIN_PROVIDER_ACCOUNT_ALIASES"] = "FIRSTBOOK_TEST",
        ["CHUMMER_ORIGIN_MAX_ACTIVE_PROVIDER_RESERVATIONS"] = "1"
    }).Build();
    private MyFirstBookUsageStore Usage(Remote remote) => new(Config(), primary: remote.Store());
    private OriginDossierProviderCreditReservationStore Reservations(Remote remote) => new(Config(), remote.Store());
    private BrilliantDirectoriesBillingService Billing(MyFirstBookUsageStore usage) => new(new(Config()), usage, Config());
    private OriginDossierProviderCreditReservationService Service(OriginDossierProviderCreditReservationStore reservations,
        MyFirstBookUsageStore usage) => new(reservations, new(new(Config()), new(Config()), Billing(usage)), Config());
    private static OriginDossierProviderCreditReservationRequest Request(string project = "book") => new(
        "user", "synthetic@example.invalid", project, "runner_memoir", "runner_private", "First Book AI", "FIRSTBOOK_TEST", 1,
        SourcePacketApproved: true, ExternalProcessingConsent: true, ChronologyValidated: true,
        OutlineApproved: true, VoiceSampleApproved: true, CanonPreflightPassed: true, HumanReviewAssigned: true);

    [Fact]
    public void Monthly_usage_restores_without_local_files_and_preserves_existing_user_and_window_semantics()
    {
        using var remote = new Remote();
        using var usage = Usage(remote);
        var result = Billing(usage).ConsumeMyFirstBookQuota("User", Now);
        Assert.Equal(1, result.Quota.MonthlyUsed);
        Assert.Equal(0, result.Quota.MonthlyRemaining);
        Assert.Empty(usage.Entries);
        using var cold = Usage(remote);
        var billing = Billing(cold);
        Assert.Equal(1, billing.GetMyFirstBookQuota("USER", Now).MonthlyUsed);
        Assert.Equal(0, billing.GetMyFirstBookQuota("other", Now).MonthlyUsed);
        Assert.Equal(0, billing.GetMyFirstBookQuota("User", Now.AddMonths(1)).MonthlyUsed);
        Assert.Throws<InvalidOperationException>(() => billing.ConsumeMyFirstBookQuota("User", Now));
        Assert.Equal(1, remote.HeadPosts);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Two_instances_cannot_both_consume_the_last_monthly_slot()
    {
        using var remote = new Remote();
        using var first = Usage(remote);
        using var second = Usage(remote);
        remote.BeforeHeadPost = () => Assert.Equal(1, Billing(second).ConsumeMyFirstBookQuota("user", Now).Quota.MonthlyUsed);
        Assert.Throws<TeableRevisionConflictException>(() => Billing(first).ConsumeMyFirstBookQuota("user", Now));
        Assert.Empty(first.Entries);
        Assert.Equal(1, Billing(first).GetMyFirstBookQuota("user", Now).MonthlyUsed);
        Assert.Throws<InvalidOperationException>(() => Billing(first).ConsumeMyFirstBookQuota("user", Now));
        Assert.Equal(1, remote.HeadPosts);
    }

    [Fact]
    public void Stale_quota_observation_does_not_authorize_an_extra_consumption_after_a_fresh_scope_read()
    {
        using var remote = new Remote();
        using var first = Usage(remote);
        using var second = Usage(remote);
        // The first quota read returns its already-captured empty ledger after
        // another instance has spent the slot. The commit scope must recheck it.
        remote.BeforeHeadReadResponse = () => Billing(second).ConsumeMyFirstBookQuota("user", Now);
        Assert.Throws<InvalidOperationException>(() => Billing(first).ConsumeMyFirstBookQuota("user", Now));
        Assert.Equal(1, Billing(first).GetMyFirstBookQuota("user", Now).MonthlyUsed);
        Assert.Equal(1, remote.HeadPosts);
    }

    [Fact]
    public void A_regressed_primary_ledger_cannot_restore_spent_allowances()
    {
        using var remote = new Remote();
        using var usage = Usage(remote);
        var billing = Billing(usage);
        billing.ConsumeMyFirstBookQuota("first", Now);
        var oldRows = remote.Rows.ToDictionary(p => p.Key, p => (JsonObject)p.Value.DeepClone());
        billing.ConsumeMyFirstBookQuota("second", Now);
        remote.Rows.Clear();
        foreach (var row in oldRows) remote.Rows.Add(row.Key, row.Value);
        Assert.Throws<InvalidDataException>(() => billing.GetMyFirstBookQuota("second", Now));
        Assert.Empty(usage.Entries);
    }

    [Fact]
    public void Failed_local_persistence_does_not_publish_phantom_usage_or_reservations()
    {
        using var usage = new MyFirstBookUsageStore(Config("local"));
        Directory.CreateDirectory(usage.StoragePath); // Deliberately not a replaceable file.
        Assert.ThrowsAny<IOException>(() => Billing(usage).ConsumeMyFirstBookQuota("user", Now));
        Assert.Empty(usage.Entries);
        Assert.Equal(0, Billing(usage).GetMyFirstBookQuota("user", Now).MonthlyUsed);
        using var reservations = new OriginDossierProviderCreditReservationStore(Config("local"));
        Directory.CreateDirectory(reservations.StoragePath);
        Assert.ThrowsAny<IOException>(() => Service(reservations, usage).Reserve(Request(), Now));
        Assert.Empty(reservations.Entries);
    }

    [Fact]
    public void An_uncertain_consumption_requires_readback_and_does_not_replay_the_charge()
    {
        using var remote = new Remote { CommitThenFailHard = true };
        using var usage = Usage(remote);
        var billing = Billing(usage);
        Assert.Throws<IOException>(() => billing.ConsumeMyFirstBookQuota("user", Now));
        Assert.Empty(usage.Entries);
        Assert.Equal(1, billing.GetMyFirstBookQuota("user", Now).MonthlyUsed);
        Assert.Throws<InvalidOperationException>(() => billing.ConsumeMyFirstBookQuota("user", Now));
        Assert.Equal(1, remote.HeadPosts);
    }

    [Fact]
    public void Reservation_and_audit_restore_from_remote_without_another_write_or_provider_dispatch()
    {
        using var remote = new Remote();
        using var usage = Usage(remote);
        using var reservations = Reservations(remote);
        var first = Service(reservations, usage).Reserve(Request(), Now);
        Assert.True(first.ProviderBurnAllowed);
        Assert.Empty(reservations.Entries);
        using var coldUsage = Usage(remote);
        using var coldReservations = Reservations(remote);
        var cold = Service(coldReservations, coldUsage);
        var audit = cold.Reserve(Request() with { AuditOnly = true }, Now);
        Assert.Equal(first.ReservationId, audit.ReservationId);
        Assert.False(audit.ProviderBurnAllowed);
        Assert.True(audit.ProviderBurnWouldBeAllowed);
        var blocked = cold.Reserve(Request("second"), Now);
        Assert.False(blocked.ProviderBurnAllowed);
        Assert.Contains("active provider credit reservation limit", blocked.BlockedRequirements);
        Assert.Equal(1, remote.HeadPosts);
        Assert.Equal(0, Billing(coldUsage).GetMyFirstBookQuota("user", Now).MonthlyUsed);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Competing_reservations_cannot_both_admit_the_last_active_slot()
    {
        using var remote = new Remote();
        using var firstUsage = Usage(remote);
        using var secondUsage = Usage(remote);
        using var first = Reservations(remote);
        using var second = Reservations(remote);
        remote.BeforeHeadPost = () => Assert.True(Service(second, secondUsage).Reserve(Request("winner"), Now).ProviderBurnAllowed);
        Assert.Throws<TeableRevisionConflictException>(() => Service(first, firstUsage).Reserve(Request("loser"), Now));
        Assert.False(Service(first, firstUsage).Reserve(Request("loser"), Now).ProviderBurnAllowed);
        Assert.Equal(1, remote.HeadPosts);
    }

    [Fact]
    public void An_uncertain_reservation_restores_as_a_read_only_audit_not_a_second_reservation()
    {
        using var remote = new Remote { CommitThenFailHard = true };
        using var usage = Usage(remote);
        using var reservations = Reservations(remote);
        var service = Service(reservations, usage);
        Assert.Throws<IOException>(() => service.Reserve(Request(), Now));
        var audit = service.Reserve(Request() with { AuditOnly = true }, Now);
        Assert.NotNull(audit.ReservationId);
        Assert.False(audit.ProviderBurnAllowed);
        Assert.Equal(1, remote.HeadPosts);
    }

    [Fact]
    public void Primary_failure_never_recreates_an_empty_allowance_or_imports_an_ambient_local_file()
    {
        using var local = new MyFirstBookUsageStore(Config("local"));
        Billing(local).ConsumeMyFirstBookQuota("local-only", Now);
        using var remote = new Remote();
        using var usage = Usage(remote);
        var billing = Billing(usage);
        Assert.Equal(0, billing.GetMyFirstBookQuota("local-only", Now).MonthlyUsed);
        billing.ConsumeMyFirstBookQuota("user", Now);
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => billing.GetMyFirstBookQuota("user", Now));
        Assert.Throws<HttpRequestException>(() => billing.ConsumeMyFirstBookQuota("new-user", Now));
        Assert.Empty(usage.Entries);
        Assert.Equal(1, Billing(local).GetMyFirstBookQuota("local-only", Now).MonthlyUsed);
        remote.FailReads = false;
        Assert.Equal(1, billing.GetMyFirstBookQuota("user", Now).MonthlyUsed);
        Assert.Single(Directory.GetFiles(_root));
    }

    [Theory]
    [InlineData("usage", "duplicate")]
    [InlineData("usage", "count")]
    [InlineData("usage", "window")]
    [InlineData("reservation", "duplicate")]
    [InlineData("reservation", "owner")]
    [InlineData("reservation", "credits")]
    [InlineData("reservation", "status")]
    public async Task Corrupt_remote_ledgers_fail_without_reset_or_allowance_grant(string kind, string fault)
    {
        using var remote = new Remote();
        using var usage = Usage(remote);
        using var reservations = Reservations(remote);
        if (kind == "usage") Billing(usage).ConsumeMyFirstBookQuota("user", Now);
        else Service(reservations, usage).Reserve(Request(), Now);
        string stream = kind == "usage" ? "myfirstbook-usage" : "origin-credit-reservations";
        var head = await remote.Store().ReadAsync(stream);
        var state = JsonNode.Parse(head!.Bytes)!;
        var row = state["entries"]![0]!;
        switch (fault)
        {
            case "duplicate": state["entries"]!.AsArray().Add(row.DeepClone()); break;
            case "count": row["monthlyUsed"] = -1; break;
            case "window": row["windowStartUtc"] = Now; break;
            case "owner": row["userId"] = "other"; break;
            case "credits": row["creditsReserved"] = -1; break;
            case "status": row["status"] = "unrecognized"; break;
        }
        await remote.Store().CompareExchangeAsync(stream, head, Guid.NewGuid(), JsonSerializer.SerializeToUtf8Bytes(state));
        int posts = remote.HeadPosts;
        Assert.Throws<InvalidDataException>(() =>
        {
            if (kind == "usage") Billing(usage).ConsumeMyFirstBookQuota("user", Now);
            else Service(reservations, usage).Reserve(Request(), Now);
        });
        Assert.Empty(usage.Entries);
        Assert.Empty(reservations.Entries);
        Assert.Equal(posts, remote.HeadPosts);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Scopes_reject_unconverted_access_and_do_not_discard_nested_changes()
    {
        using var remote = new Remote();
        using var usage = Usage(remote);
        Assert.Throws<InvalidOperationException>(() => usage.Gate);
        Assert.Throws<InvalidOperationException>(() => usage.StoragePath);
        Assert.Throws<InvalidOperationException>(usage.PersistLocked);
        using (usage.Enter())
        {
            usage.Entries.Add(new("user", new(2026, 9, 1, 0, 0, 0, TimeSpan.Zero), 1, Now));
            using (usage.Enter()) Assert.Single(usage.Entries);
            usage.PersistLocked();
        }
        Assert.Empty(usage.Entries);
        Assert.Equal(1, Billing(usage).GetMyFirstBookQuota("user", Now).MonthlyUsed);
        Assert.Throws<InvalidOperationException>(usage.EnsureAccountErasureSupported);
    }

    [Fact]
    public void Explicit_registration_requires_separate_private_credentials_and_never_opens_local_ledger_files()
    {
        Assert.Throws<InvalidOperationException>(() => new MyFirstBookUsageStore(Config()));
        Assert.Throws<InvalidOperationException>(() => new OriginDossierProviderCreditReservationStore(Config()));
        Assert.Throws<InvalidOperationException>(() => new MyFirstBookUsageStore(Config("unknown")));
        if (!OperatingSystem.IsLinux() || System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture != System.Runtime.InteropServices.Architecture.X64) return;
        Directory.CreateDirectory(_root, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        string token = Path.Combine(_root, "synthetic-token");
        File.WriteAllText(token, "synthetic-only");
        File.SetUnixFileMode(token, UnixFileMode.UserRead | UnixFileMode.UserWrite);
        var config = new ConfigurationBuilder().AddConfiguration(Config()).AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_TEABLE_ORIGIN"] = "https://teable.example/",
            ["CHUMMER_MYFIRSTBOOK_USAGE_TEABLE_TABLE_ID"] = "tbl1234567890123456",
            ["CHUMMER_MYFIRSTBOOK_USAGE_TEABLE_TOKEN_FILE"] = token,
            ["CHUMMER_ORIGIN_PROVIDER_RESERVATION_TEABLE_TABLE_ID"] = "tbl1234567890123456",
            ["CHUMMER_ORIGIN_PROVIDER_RESERVATION_TEABLE_TOKEN_FILE"] = token
        }).Build();
        var services = new ServiceCollection();
        services.AddSingleton<IConfiguration>(config);
        services.AddHubAccountsAndCommunityContext();
        using var provider = services.BuildServiceProvider();
        Assert.NotNull(provider.GetRequiredService<MyFirstBookUsageStore>());
        Assert.NotNull(provider.GetRequiredService<OriginDossierProviderCreditReservationStore>());
        Assert.Single(Directory.GetFiles(_root));
    }

    public void Dispose() { if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true); }
}
