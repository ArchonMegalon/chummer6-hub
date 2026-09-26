using System.Text.Json.Nodes;
using Chummer.Run.Api;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Ledger;
using Chummer.Storage.Teable;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;

namespace Chummer.Tests;

public sealed class CommunityTeablePersistenceTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "community-teable-" + Guid.NewGuid().ToString("N"));
    private readonly List<IDisposable> _authorities = [];
    private IConfiguration Configuration(string provider = "teable") => new ConfigurationBuilder().AddInMemoryCollection(
        new Dictionary<string, string?>
        {
            ["CHUMMER_COMMUNITY_STORAGE_PROVIDER"] = provider,
            ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community.json")
        }).Build();
    private CommunityStore Store(Remote remote) => new(Configuration(), NullLogger<CommunityStore>.Instance, remote.Store());

    [Fact]
    public void Explicit_primary_registration_restores_accounts_through_fresh_service_containers()
    {
        using var remote = new Remote();
        ServiceProvider Services()
        {
            var services = new ServiceCollection().AddLogging().AddSingleton(Configuration());
            services.AddHubAccountsAndCommunityContext();
            services.AddKeyedSingleton<TeableRevisionStore>(ServiceCollectionBoundedContextExtensions.CommunityPrimaryStoreKey,
                (_, _) => remote.Store());
            return services.BuildServiceProvider();
        }
        string userId;
        using (var first = Services())
        {
            Assert.True(first.GetRequiredService<CommunityStore>().IsPrimary);
            userId = first.GetRequiredService<AccountService>().EnsureUser("primary-principal", "Private runner").UserId;
            Assert.Same(first.GetRequiredService<CommunityStore>(), first.GetRequiredService<CommunityStore>());
        }
        using (var cold = Services())
        {
            var accounts = cold.GetRequiredService<AccountService>();
            Assert.Equal(userId, accounts.GetBySubject("primary-principal")!.UserId);
            Assert.Null(accounts.GetBySubject("foreign-principal"));
            Assert.False(cold.GetRequiredService<TeableUserProjectionService>().GetDashboard().Configured);
        }
        Assert.False(Directory.Exists(_root));
    }

    [Theory]
    [InlineData("outage")]
    [InlineData("corrupt")]
    public async Task Primary_registration_rejects_unreadable_authority_before_returning_account_services(string failure)
    {
        using var remote = new Remote();
        if (failure == "outage") remote.FailReads = true;
        else
        {
            using var transport = remote.Store();
            await transport.CompareExchangeAsync("community", null, Guid.NewGuid(), "{}"u8.ToArray());
        }
        var services = new ServiceCollection().AddLogging().AddSingleton(Configuration());
        services.AddHubAccountsAndCommunityContext();
        services.AddKeyedSingleton<TeableRevisionStore>(ServiceCollectionBoundedContextExtensions.CommunityPrimaryStoreKey,
            (_, _) => remote.Store());
        using var provider = services.BuildServiceProvider();
        if (failure == "outage") Assert.Throws<HttpRequestException>(() => provider.GetRequiredService<AccountService>());
        else Assert.Throws<InvalidDataException>(() => provider.GetRequiredService<AccountService>());
        Assert.False(Directory.Exists(_root));
    }

    [Theory]
    [InlineData("table")]
    [InlineData("token")]
    [InlineData("provider")]
    public void Registration_does_not_inherit_broad_credentials_or_fall_back_to_a_local_account_file(string missing)
    {
        var values = new Dictionary<string, string?>
        {
            ["CHUMMER_COMMUNITY_STORAGE_PROVIDER"] = missing == "provider" ? "unknown" : "teable",
            ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community.json"),
            ["CHUMMER_TEABLE_ORIGIN"] = "https://teable.example/",
            ["CHUMMER_COMMUNITY_TEABLE_TABLE_ID"] = missing == "table" ? null : "tbl1234567890123456",
            ["TEABLE_API_KEY"] = "broad-synthetic-token-must-not-be-used",
            ["CHUMMER_TEABLE_API_KEY"] = "broad-synthetic-token-must-not-be-used"
        };
        var services = new ServiceCollection().AddLogging().AddSingleton<IConfiguration>(
            new ConfigurationBuilder().AddInMemoryCollection(values).Build());
        services.AddHubAccountsAndCommunityContext();
        using var provider = services.BuildServiceProvider();
        Assert.Throws<InvalidOperationException>(() => provider.GetRequiredService<AccountService>());
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Local_registration_keeps_its_existing_file_without_resolving_a_remote_transport()
    {
        using (var existing = new CommunityStore(Configuration("local"), NullLogger<CommunityStore>.Instance))
            new AccountService(existing).EnsureUser("local-principal");
        var services = new ServiceCollection().AddLogging().AddSingleton(Configuration("local"));
        services.AddHubAccountsAndCommunityContext();
        services.AddKeyedSingleton<TeableRevisionStore>(ServiceCollectionBoundedContextExtensions.CommunityPrimaryStoreKey,
            (_, _) => throw new InvalidOperationException("Local mode must not resolve a remote transport."));
        using var provider = services.BuildServiceProvider();
        Assert.False(provider.GetRequiredService<CommunityStore>().IsPrimary);
        Assert.NotNull(provider.GetRequiredService<AccountService>().GetBySubject("local-principal"));
    }

    [Fact]
    public void Profile_and_group_restore_on_a_fresh_host_without_local_files()
    {
        using var remote = new Remote();
        using var first = Store(remote);
        var accounts = new AccountService(first);
        var user = accounts.EnsureUser("principal-a", "Synthetic runner", "runner@example.invalid");
        var group = new GroupService(first, accounts).CreateGroup(new CreateGroupRequest(
            SubjectId: "principal-a", Name: "Synthetic group", GroupType: "booster", Visibility: "private", Capabilities: []));
        using var cold = Store(remote);
        var restored = new AccountService(cold).GetBySubject("principal-a");
        Assert.NotNull(restored);
        Assert.Equal(user.UserId, restored.UserId);
        Assert.Equal(user.Email, restored.Email);
        Assert.Contains(group.GroupId, restored.GroupIds);
        Assert.Null(new AccountService(cold).GetBySubject("principal-b"));
        var restoredGroup = new GroupService(cold, new AccountService(cold)).GetGroup(group.GroupId);
        Assert.Equal(user.UserId, restoredGroup!.OwnerUserId);
        Assert.Equal(group.Memberships.Single(), restoredGroup.Memberships.Single());
        Assert.False(Directory.Exists(_root));
        Assert.Throws<InvalidOperationException>(() => cold.StoragePath);
    }

    [Fact]
    public void Group_access_list_uses_one_current_read_and_observes_membership_removal()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var accounts = new AccountService(writer);
        var user = accounts.EnsureUser("principal-a");
        accounts.EnsureUser("principal-b");
        var groups = new GroupService(writer, accounts);
        for (int index = 0; index < 3; index++)
            groups.CreateGroup(new CreateGroupRequest("principal-a", "Group " + index,
                GroupType: "campaign", Visibility: "private", Capabilities: []));
        using var reader = Store(remote);
        var reads = new GroupService(reader, new AccountService(reader));
        int baseline = remote.GetRequests;
        int writes = remote.HeadPosts;
        var views = reads.ListGroupAccessForUser("principal-a");
        Assert.Equal(1, remote.GetRequests - baseline); // Small test state is inline.
        Assert.Equal(writes, remote.HeadPosts);
        Assert.Equal(3, views.Count);
        Assert.All(views, view =>
        {
            Assert.Equal(user.UserId, view.Membership.UserId);
            Assert.True(view.CanManage);
        });
        Assert.Empty(reads.ListGroupAccessForUser("principal-b"));
        using (writer.Enter())
        {
            foreach (var view in views)
                writer.GroupsById[view.Group.GroupId] = view.Group with { Memberships = [] };
            writer.PersistLocked();
        }
        Assert.Empty(reads.ListGroupAccessForUser("principal-a"));
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => reads.ListGroupAccessForUser("principal-a"));
    }

    [Fact]
    public void An_existing_reader_observes_current_mapping_not_cached_authority()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var user = new AccountService(writer).EnsureUser("principal-a");
        using var reader = Store(remote);
        var accounts = new AccountService(reader);
        Assert.Equal(user.UserId, accounts.GetExistingCanonicalUserIdBySubject("principal-a"));
        using (writer.Enter())
        {
            writer.UsersById[user.UserId] = user with { SubjectId = "principal-b", LinkedPrincipals = ["principal-b"] };
            writer.PersistLocked();
        }
        Assert.Null(accounts.GetExistingCanonicalUserIdBySubject("principal-a"));
        Assert.Equal(user.UserId, accounts.GetExistingCanonicalUserIdBySubject("principal-b"));
    }

    [Fact]
    public void Nested_account_reads_do_not_discard_the_outer_uncommitted_mutation()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var accounts = new AccountService(store);
        var user = accounts.EnsureUser("principal");
        using (store.Enter())
        {
            store.UsersById[user.UserId] = user with { DisplayName = "Changed inside transaction" };
            Assert.Equal("Changed inside transaction", accounts.GetById(user.UserId)!.DisplayName);
            store.PersistLocked();
        }
        using var cold = Store(remote);
        Assert.Equal("Changed inside transaction", new AccountService(cold).GetById(user.UserId)!.DisplayName);
    }

    [Fact]
    public void Concurrent_winner_is_not_overwritten_and_failed_instance_cannot_serve_mutated_memory()
    {
        using var remote = new Remote();
        using var first = Store(remote);
        using var second = Store(remote);
        remote.BeforeHeadPost = () => new AccountService(second).EnsureUser("winner");
        Assert.Throws<TeableRevisionConflictException>(() => new AccountService(first).EnsureUser("loser"));
        Assert.Throws<InvalidOperationException>(() => new AccountService(first).GetBySubject("loser"));
        using var cold = Store(remote);
        Assert.NotNull(new AccountService(cold).GetBySubject("winner"));
        Assert.Null(new AccountService(cold).GetBySubject("loser"));
    }

    [Fact]
    public void Lost_commit_response_is_reconciled_cold_without_replaying_a_write()
    {
        using var remote = new Remote();
        using var first = Store(remote);
        remote.CommitThenFailHard = true;
        Assert.Throws<IOException>(() => new AccountService(first).EnsureUser("principal"));
        int writes = remote.HeadPosts;
        Assert.Throws<InvalidOperationException>(() => new AccountService(first).GetBySubject("principal"));
        using var cold = Store(remote);
        Assert.NotNull(new AccountService(cold).GetBySubject("principal"));
        Assert.Equal(writes, remote.HeadPosts);
    }

    [Fact]
    public void Outage_does_not_authorize_from_cache_or_import_a_local_snapshot()
    {
        using var local = new CommunityStore(Configuration("local"), NullLogger<CommunityStore>.Instance);
        new AccountService(local).EnsureUser("local-principal");
        string path = local.StoragePath;
        byte[] localBytes = File.ReadAllBytes(path);
        using var remote = new Remote();
        using var primary = Store(remote);
        var accounts = new AccountService(primary);
        Assert.Null(accounts.GetBySubject("local-principal"));
        accounts.EnsureUser("remote-principal");
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => accounts.GetBySubject("remote-principal"));
        Assert.Throws<InvalidOperationException>(() => accounts.GetBySubject("remote-principal"));
        Assert.Equal(localBytes, File.ReadAllBytes(path));
    }

    [Fact]
    public async Task Corrupt_snapshot_and_ambiguous_principal_ownership_fail_closed()
    {
        using var corrupt = new Remote();
        await corrupt.Store().CompareExchangeAsync("community", null, Guid.NewGuid(), "{}"u8.ToArray());
        Assert.Throws<InvalidDataException>(() => Store(corrupt));

        using var remote = new Remote();
        using var first = Store(remote);
        new AccountService(first).EnsureUser("one");
        new AccountService(first).EnsureUser("two");
        var head = (await remote.Store().ReadAsync("community"))!;
        var envelope = JsonNode.Parse(head.Bytes)!;
        var users = envelope["snapshot"]!["users"]!.AsArray();
        users[1]!["linkedPrincipals"] = new JsonArray(users[0]!["subjectId"]!.GetValue<string>());
        await remote.Store().CompareExchangeAsync("community", head, Guid.NewGuid(),
            System.Text.Encoding.UTF8.GetBytes(envelope.ToJsonString()));
        Assert.Throws<InvalidDataException>(() => Store(remote));
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Missing_remote_head_cannot_reset_an_existing_instance()
    {
        using var remote = new Remote();
        using var first = Store(remote);
        var accounts = new AccountService(first);
        accounts.EnsureUser("principal");
        remote.Rows.Clear();
        Assert.Throws<InvalidDataException>(() => accounts.GetBySubject("principal"));
        Assert.Throws<InvalidOperationException>(() => accounts.EnsureUser("principal"));
    }

    [Fact]
    public void No_legacy_gate_local_path_or_false_erasure_is_allowed_in_primary_mode()
    {
        using var remote = new Remote();
        using var primary = Store(remote);
        new AccountService(primary).EnsureUser("principal");
        Assert.Throws<InvalidOperationException>(() => primary.Gate);
        Assert.Throws<InvalidOperationException>(() => primary.StoragePath);
        Assert.Throws<InvalidOperationException>(() => primary.PersistLocked());
        int writes = remote.HeadPosts;
        Assert.Throws<InvalidOperationException>(() => new CommunityAccountErasureService(primary).Erase("principal"));
        Assert.Equal(writes, remote.HeadPosts);
        Assert.NotNull(new AccountService(primary).GetBySubject("principal"));
        Assert.Throws<InvalidOperationException>(() => new CommunityStore(Configuration(), NullLogger<CommunityStore>.Instance));
        Assert.Throws<InvalidOperationException>(() => new CommunityStore(Configuration("wrong"), NullLogger<CommunityStore>.Instance));
    }

    [Fact]
    public void Recognition_projections_restore_and_observe_remote_public_consent_withdrawal()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var accounts = new AccountService(writer);
        var user = accounts.EnsureUser("principal", "Synthetic contributor");
        using (writer.Enter())
        {
            writer.UsersById[user.UserId] = user with { Visibility = "public" };
            writer.PersistLocked();
        }
        var experience = new UserExperienceService(writer, accounts);
        experience.Upsert(new UpsertHubUserExperienceRequest(SubjectId: "principal", PublicContributionProfileOptIn: true));
        new LedgerService(writer, new(writer), new(writer)).Ingest(new ContributionReceiptDto(
            ReceiptId: "synthetic-receipt", EventKind: "slice_landed", LaneId: "lane", ProjectId: "project",
            UserId: user.UserId, GroupId: null, SponsorSessionId: null, ParticipantCodexCode: "participant-a",
            AuthClass: "operator", LaneType: "direct", Verified: true, ParticipantTotalTokens: 100));
        using var reader = Store(remote);
        var boards = new LeaderboardService(reader);
        int writes = remote.HeadPosts;
        Assert.Equal(user.UserId, Assert.Single(boards.IndividualLeaderboard(publicOnly: true)).UserId);
        Assert.Equal(user.UserId, Assert.Single(boards.SponsorRankLeaderboard(publicOnly: true)).UserId);
        Assert.Equal(user.UserId, Assert.Single(boards.CodexUsageLeaderboard(publicOnly: true)).UserId);
        Assert.Empty(boards.GroupLeaderboard(publicOnly: true));
        Assert.Equal(1, boards.UserRecognitionSummary(user.UserId).ContributionCount);
        Assert.Equal(2, boards.Quests().Count);
        Assert.Equal(writes, remote.HeadPosts);

        experience.Upsert(new UpsertHubUserExperienceRequest(SubjectId: "principal", PublicContributionProfileOptIn: false));
        Assert.Empty(boards.IndividualLeaderboard(publicOnly: true));
        Assert.Empty(boards.SponsorRankLeaderboard(publicOnly: true));
        Assert.Empty(boards.CodexUsageLeaderboard(publicOnly: true));
        Assert.Equal(user.UserId, Assert.Single(boards.IndividualLeaderboard()).UserId);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Nested_recognition_read_retains_the_outer_pending_snapshot()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var user = new AccountService(store).EnsureUser("principal", "Original");
        using (store.Enter())
        {
            store.UsersById[user.UserId] = user with { DisplayName = "Pending transaction" };
            Assert.Equal("Pending transaction", Assert.Single(new LeaderboardService(store).IndividualLeaderboard()).DisplayName);
            store.PersistLocked();
        }
        using var cold = Store(remote);
        Assert.Equal("Pending transaction", Assert.Single(new LeaderboardService(cold).IndividualLeaderboard()).DisplayName);
    }

    private TeableUserProjectionService Projection(CommunityStore store, NoHttp factory)
        => new(store, Configuration(), factory, NullLogger<TeableUserProjectionService>.Instance);

    [Fact]
    public void Operator_user_projection_reads_primary_changes_without_enabling_remote_projection()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var user = new AccountService(writer).EnsureUser("principal", "Original");
        using var reader = Store(remote);
        var factory = new NoHttp();
        var projection = Projection(reader, factory);
        Assert.Equal(user.UserId, Assert.Single(projection.GetDashboard().Users).UserId);
        using (writer.Enter())
        {
            writer.UsersById[user.UserId] = user with { DisplayName = "Fresh primary name" };
            writer.PersistLocked();
        }
        Assert.Equal("Fresh primary name", Assert.Single(projection.GetDashboard().Users).DisplayName);
        Assert.Equal(0, factory.Calls);
        Assert.False(Directory.Exists(_root));
    }

    private CommunityCreatorHorizonsService Summaries(CommunityStore store)
    {
        // Exercise the supported unready-installation path, not a null legacy store.
        var activation = new InstallLinkingStoreActivation(Configuration(), new EphemeralDataProtectionProvider(),
            new UnconfiguredProductionHost(), NullLoggerFactory.Instance, []);
        _authorities.Add(activation);
        return new(store, new InstallLinkingStoreAccess(activation), null!); // No publication lookup in these summaries.
    }

    [Fact]
    public void Passport_and_signal_summaries_restore_current_notification_counts_without_local_files()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var user = new AccountService(writer).EnsureUser("principal");
        using (writer.Enter())
        {
            var now = DateTimeOffset.UtcNow;
            writer.ParticipationNotificationReceipts.Add(new("synthetic", "participation", "event", user.UserId,
                "synthetic-hash", "redacted", "synthetic-hash", "Runner", "join", "/community", "email",
                "recorded", true, now, now));
            writer.PersistLocked();
        }
        using var reader = Store(remote);
        var summaries = Summaries(reader);
        Assert.Equal(1, summaries.BuildPassportSummary().ParticipationNotificationCount);
        Assert.Equal(1, summaries.BuildSignalDeckSummary().ParticipationNotificationCount);
        Assert.Empty(summaries.BuildCommunitySummary().OpenRuns);
        using (writer.Enter())
        {
            writer.ParticipationNotificationReceipts.Clear();
            writer.PersistLocked(); // Current-view update only, not historical erasure.
        }
        Assert.Equal(0, summaries.BuildPassportSummary().ParticipationNotificationCount);
        Assert.Equal(0, summaries.BuildSignalDeckSummary().ParticipationNotificationCount);
        Assert.False(Directory.Exists(_root));
    }

    [Theory]
    [InlineData("recognition")]
    [InlineData("operator")]
    [InlineData("passport")]
    public void Primary_projection_outage_never_returns_cached_account_data(string surface)
    {
        using var remote = new Remote();
        using var store = Store(remote);
        new AccountService(store).EnsureUser("principal");
        Action observe = surface switch
        {
            "recognition" => () => new LeaderboardService(store).IndividualLeaderboard(),
            "operator" => () => Projection(store, new NoHttp()).GetDashboard(),
            _ => () => Summaries(store).BuildPassportSummary()
        };
        observe();
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(observe);
        Assert.Throws<InvalidOperationException>(observe);
    }

    [Theory]
    [InlineData("false", "synthetic-unused-key", "disabled")]
    [InlineData("true", "", "unconfigured")]
    public async Task Inactive_important_work_sync_does_not_read_primary_state(string enabled, string key, string expected)
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var factory = new NoHttp();
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_TEABLE_IMPORTANT_WORK_ENABLED"] = enabled,
            ["CHUMMER_TEABLE_IMPORTANT_WORK_API_KEY"] = key
        }).Build();
        var service = new TeableImportantWorkService(store, config, factory, NullLogger<TeableImportantWorkService>.Instance);
        remote.FailReads = true;

        var result = await service.SyncAllAsync();

        Assert.Equal(expected, result.State);
        Assert.Equal(0, result.AttemptedCount);
        Assert.Equal(0, factory.Calls);
        Assert.Equal(0, remote.HeadPosts);
    }

    [Fact]
    public void Important_work_records_restore_and_existing_readers_observe_current_primary_state()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        using var reader = Store(remote);
        var factory = new NoHttp();
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_TEABLE_IMPORTANT_WORK_ENABLED"] = "false"
        }).Build();
        TeableImportantWorkService Service(CommunityStore store) => new(store, config, factory, NullLogger<TeableImportantWorkService>.Instance);
        var writeService = Service(writer);
        var readService = Service(reader);
        var request = new ImportantWorkItemRequest("workflow", "chummer.run", "Initial", "Synthetic only", "open", "normal", ItemId: "primary-work");
        var initial = writeService.Record(request);
        Assert.Equivalent(initial, Assert.Single(readService.GetDashboard().Items), strict: true);
        var updated = writeService.Record(request with { Summary = "Updated" });
        Assert.Equal(initial.CreatedAtUtc, updated.CreatedAtUtc);
        Assert.Equivalent(updated, Assert.Single(readService.GetDashboard().Items), strict: true);
        using var cold = Store(remote);
        Assert.Equivalent(updated, Assert.Single(Service(cold).GetDashboard().Items), strict: true);
        Assert.Equal(0, factory.Calls);
        Assert.False(Directory.Exists(_root));

        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => readService.GetDashboard());
    }

    [Fact]
    public void Important_work_conflict_cannot_overwrite_a_concurrent_primary_winner()
    {
        using var remote = new Remote();
        using var first = Store(remote);
        using var second = Store(remote);
        var config = new ConfigurationBuilder().Build();
        TeableImportantWorkService Service(CommunityStore store) => new(store, config, new NoHttp(), NullLogger<TeableImportantWorkService>.Instance);
        var request = new ImportantWorkItemRequest("workflow", "chummer.run", "Synthetic", "Only a test", "open", "normal", ItemId: "winner");
        remote.BeforeHeadPost = () => Service(second).Record(request);
        Assert.Throws<TeableRevisionConflictException>(() => Service(first).Record(request with { ItemId = "loser" }));
        using var cold = Store(remote);
        Assert.Equal("winner", Assert.Single(Service(cold).GetDashboard().Items).ItemId);
        Assert.Throws<InvalidOperationException>(() => Service(first).GetDashboard());
    }

    [Theory]
    [InlineData(null)]
    [InlineData("false")]
    [InlineData("invalid")]
    public async Task Disabled_news_worker_finishes_without_primary_reads_or_delivery(string? enabled)
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED"] = enabled
        }).Build();
        // No notification collaborator may be used when its lane is disabled.
        using var worker = new BlackLedgerTickNewsDispatchWorker(store, null!, config);
        remote.FailReads = true;
        await worker.StartAsync(CancellationToken.None);
        await worker.ExecuteTask!.WaitAsync(TimeSpan.FromSeconds(3));
        Assert.True(worker.ExecuteTask.IsCompletedSuccessfully);
        Assert.Equal(0, remote.HeadPosts);
        Assert.False(Directory.Exists(_root));
    }

    private sealed class NoHttp : IHttpClientFactory
    {
        internal int Calls { get; private set; }
        public HttpClient CreateClient(string name) { Calls++; throw new InvalidOperationException("No external calls allowed."); }
    }

    private sealed class UnconfiguredProductionHost : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = Environments.Production;
        public string ApplicationName { get; set; } = "Synthetic.Community.Primary";
        public string ContentRootPath { get; set; } = Path.GetTempPath();
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }

    public void Dispose()
    {
        foreach (var authority in _authorities) authority.Dispose();
        if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
    }
}
