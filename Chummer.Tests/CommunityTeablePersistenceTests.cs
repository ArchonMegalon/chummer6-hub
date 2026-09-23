using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Ledger;
using Chummer.Storage.Teable;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
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
