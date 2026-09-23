using System.Text.Json.Nodes;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Chummer.Storage.Teable;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;

namespace Chummer.Tests;

public sealed class CommunityTeablePersistenceTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "community-teable-" + Guid.NewGuid().ToString("N"));
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

    public void Dispose() { if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true); }
}
