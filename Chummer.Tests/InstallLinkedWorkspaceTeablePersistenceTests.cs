using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Contracts.Workspaces;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Storage.Teable;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;
using Fixtures = Chummer.Tests.InstallLinkedWorkspaceSnapshotTransferTests;

namespace Chummer.Tests;

public sealed class InstallLinkedWorkspaceTeablePersistenceTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "linked-workspace-primary-" + Guid.NewGuid().ToString("N"));
    private IConfiguration Configuration(string provider = "teable") => new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
    {
        ["CHUMMER_INSTALL_LINKED_WORKSPACE_STORAGE_PROVIDER"] = provider,
        ["CHUMMER_INSTALL_LINKED_WORKSPACE_SNAPSHOT_STORE_PATH"] = Path.Combine(_root, "snapshots.json")
    }).Build();
    private InstallLinkedWorkspaceSnapshotStore Store(Remote remote) => new(Configuration(), remote.Store());
    private static ClaimedInstallationDto Installation(string subject = "subject", string id = "ins-transfer") => new(
        id, "fixture", "internal", "fixture", "account_required", "active",
        DateTimeOffset.UtcNow, DateTimeOffset.UtcNow, UserId: "user", SubjectId: subject);
    private static InstallLinkedWorkspaceSnapshotRecord Request() => Fixtures.ToContinuationRecord(Fixtures.SampleContinuation(), includeProjection: true);

    [Fact]
    public async Task Slow_roster_read_does_not_block_another_owner_or_retain_their_data()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var service = new InstallLinkedWorkspaceSnapshotService(store);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var release = new ManualResetEventSlim();
        remote.BeforeHeadReadResponse = () =>
        {
            entered.SetResult();
            Assert.True(release.Wait(TimeSpan.FromSeconds(10)));
        };
        // This read deliberately blocks. Give it its own thread so a busy test
        // runner's pool cannot prevent the controlled interleaving from starting.
        var slow = Task.Factory.StartNew(() => service.ListForInstallation(Installation()),
            CancellationToken.None, TaskCreationOptions.LongRunning, TaskScheduler.Default);
        Task<IReadOnlyList<InstallLinkedWorkspaceSnapshotRecord>>? other = null;
        try
        {
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            other = Task.Factory.StartNew(() => service.ListForInstallation(Installation("other")),
                CancellationToken.None, TaskCreationOptions.LongRunning, TaskScheduler.Default);
            Assert.Empty(await other.WaitAsync(TimeSpan.FromSeconds(2)));
            Assert.False(slow.IsCompleted);
        }
        finally
        {
            release.Set();
            await slow;
            if (other is not null) await other;
        }
        Assert.Empty(store.SnapshotsByKey);
        Assert.Equal(0, remote.HeadPosts);
    }

    [Fact]
    public void Roster_read_cannot_replace_an_inflight_writers_expected_primary_revision()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        using var competitor = Store(remote);
        var service = new InstallLinkedWorkspaceSnapshotService(store);
        var other = new InstallLinkedWorkspaceSnapshotService(competitor);
        var initial = service.UpsertForInstallation(Installation(), Request(), 0);
        using (store.Enter("subject:subject"))
        {
            string key = InstallLinkedWorkspaceSnapshotStore.ComposeKey("subject:subject", initial.WorkspaceId);
            store.SnapshotsByKey[key] = initial with { Name = "Uncommitted local edit" };
            var winner = other.UpsertForInstallation(Installation(), Request() with { Name = "Winner" },
                initial.RemoteRevision, initial.ServerToken);
            Assert.Equal(winner.ServerToken, Assert.Single(service.ListForInstallation(Installation())).ServerToken);
            Assert.Equal("Uncommitted local edit", store.SnapshotsByKey[key].Name);
            Assert.Equal(409, Assert.Throws<InstallLinkingOperationException>(store.PersistLocked).StatusCode);
        }
        Assert.Equal("Winner", Assert.Single(service.ListForInstallation(Installation())).Name);
        Assert.Equal(2, remote.HeadPosts);
    }

    [Fact]
    public async Task Late_roster_response_cannot_regress_a_newer_observed_primary_revision()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        using var competitor = Store(remote);
        var service = new InstallLinkedWorkspaceSnapshotService(store);
        var initial = service.UpsertForInstallation(Installation(), Request(), 0);
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var release = new ManualResetEventSlim();
        remote.BeforeHeadReadResponse = () =>
        {
            entered.SetResult();
            Assert.True(release.Wait(TimeSpan.FromSeconds(10)));
        };
        var slow = Task.Factory.StartNew(() => Record.Exception(() => service.ListForInstallation(Installation())),
            CancellationToken.None, TaskCreationOptions.LongRunning, TaskScheduler.Default);
        Task<IReadOnlyList<InstallLinkedWorkspaceSnapshotRecord>>? current = null;
        try
        {
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
            var winner = new InstallLinkedWorkspaceSnapshotService(competitor).UpsertForInstallation(
                Installation(), Request() with { Name = "Newer remote edit" }, initial.RemoteRevision, initial.ServerToken);
            current = Task.Factory.StartNew(() => service.ListForInstallation(Installation()),
                CancellationToken.None, TaskCreationOptions.LongRunning, TaskScheduler.Default);
            Assert.Equal(winner.ServerToken, Assert.Single(await current.WaitAsync(TimeSpan.FromSeconds(2))).ServerToken);
        }
        finally
        {
            release.Set();
            await slow;
            if (current is not null) await current;
        }
        Assert.Equal(503, Assert.IsType<InstallLinkingOperationException>(await slow).StatusCode);
        Assert.Empty(store.SnapshotsByKey);
    }

    [Fact]
    public void Full_character_and_career_history_restore_on_a_fresh_store_without_local_files()
    {
        using var remote = new Remote();
        using var first = Store(remote);
        var request = Request();
        var committed = new InstallLinkedWorkspaceSnapshotService(first).UpsertForInstallation(Installation(), request, 0);
        Assert.Empty(first.SnapshotsByKey); // No retained outside-scope shadow.
        using var cold = Store(remote);
        var restored = Assert.Single(new InstallLinkedWorkspaceSnapshotService(cold).ListForInstallation(Installation(id: "another-install")));
        Assert.Equal(committed.RemoteRevision, restored.RemoteRevision);
        Assert.Equal(committed.ServerToken, restored.ServerToken);
        Assert.Equal(committed.Payload, restored.Payload);
        Assert.Equal(committed.WorkspaceSnapshotDigest, restored.WorkspaceSnapshotDigest);
        Assert.Equal(committed.WorkspaceContinuationDigest, restored.WorkspaceContinuationDigest);
        Assert.True(JsonElement.DeepEquals(committed.WorkspaceContinuation!.Value, restored.WorkspaceContinuation!.Value));
        Assert.True(JsonElement.DeepEquals(committed.WorkspaceSnapshot!.Value, restored.WorkspaceSnapshot!.Value));
        var decoded = InstallLinkedWorkspaceSnapshotTransfer.Decode(restored.WorkspaceSnapshot.Value);
        Assert.NotNull(decoded.Document.AuxiliaryState.CharacterCreationFinalizationArchive);
        Assert.Equal("Straßenkind — live choice", decoded.Document.AuxiliaryState.CharacterCreationFoundationDraft!.FollowUpValues["story"]);
        Assert.Empty(cold.SnapshotsByKey);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Exact_opaque_subjects_and_user_fallback_do_not_share_primary_streams()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var service = new InstallLinkedWorkspaceSnapshotService(store);
        var projection = Fixtures.ToRecord(Fixtures.SampleSnapshot());
        var first = service.UpsertForInstallation(Installation("Subject"), projection, 0);
        foreach (string other in new[] { "subject", " Subject", "Subject " })
        {
            Assert.Empty(service.ListForInstallation(Installation(other)));
            var separate = service.UpsertForInstallation(Installation(other), projection, 0);
            Assert.NotEqual(first.ServerToken, separate.ServerToken);
        }
        var fallback = Installation() with { SubjectId = null, UserId = "Subject" };
        Assert.Empty(service.ListForInstallation(fallback));
        var fallbackSaved = service.UpsertForInstallation(fallback, projection, 0);
        using var cold = Store(remote);
        var restored = new InstallLinkedWorkspaceSnapshotService(cold);
        Assert.Equal(first.ServerToken, Assert.Single(restored.ListForInstallation(Installation("Subject"))).ServerToken);
        Assert.Equal(fallbackSaved.ServerToken, Assert.Single(restored.ListForInstallation(fallback)).ServerToken);
    }

    [Fact]
    public void Different_owners_can_commit_without_false_conflicts_or_cross_owner_rows()
    {
        using var remote = new Remote();
        using var first = Store(remote);
        using var second = Store(remote);
        var firstService = new InstallLinkedWorkspaceSnapshotService(first);
        var secondService = new InstallLinkedWorkspaceSnapshotService(second);
        var projection = Fixtures.ToRecord(Fixtures.SampleSnapshot());
        remote.BeforeHeadPost = () => secondService.UpsertForInstallation(Installation("other"), projection, 0);
        var committed = firstService.UpsertForInstallation(Installation(), projection, 0);
        Assert.Equal(2, remote.HeadPosts);
        Assert.Equal(committed.ServerToken, Assert.Single(firstService.ListForInstallation(Installation())).ServerToken);
        Assert.Equal("subject:other", Assert.Single(secondService.ListForInstallation(Installation("other"))).OwnerKey);
    }

    [Fact]
    public void Competing_same_owner_writes_require_new_reads_without_losing_the_winner()
    {
        using var remote = new Remote();
        using var first = Store(remote);
        using var second = Store(remote);
        var firstService = new InstallLinkedWorkspaceSnapshotService(first);
        var secondService = new InstallLinkedWorkspaceSnapshotService(second);
        var projection = Fixtures.ToRecord(Fixtures.SampleSnapshot());
        var other = Fixtures.ToRecord(Fixtures.SampleSnapshot() with { Id = new CharacterWorkspaceId("other-workspace") });
        remote.BeforeHeadPost = () => secondService.UpsertForInstallation(Installation(), other, 0);
        Assert.Equal(409, Assert.Throws<InstallLinkingOperationException>(() => firstService.UpsertForInstallation(Installation(), projection, 0)).StatusCode);
        Assert.Empty(first.SnapshotsByKey);
        Assert.Equal("other-workspace", Assert.Single(firstService.ListForInstallation(Installation())).WorkspaceId);
        firstService.UpsertForInstallation(Installation(), projection, 0);
        Assert.Equal(2, firstService.ListForInstallation(Installation()).Count);
        Assert.Equal(2, remote.HeadPosts);
    }

    [Fact]
    public void Lost_commit_acknowledgement_is_reconciled_by_read_not_mutation_replay()
    {
        using var remote = new Remote { CommitThenFailHard = true };
        using var store = Store(remote);
        var service = new InstallLinkedWorkspaceSnapshotService(store);
        var request = Request();
        Assert.Equal(503, Assert.Throws<InstallLinkingOperationException>(() => service.UpsertForInstallation(Installation(), request, 0)).StatusCode);
        Assert.Empty(store.SnapshotsByKey);
        var current = Assert.Single(service.ListForInstallation(Installation()));
        Assert.Equal(1, current.RemoteRevision);
        Assert.Equal(409, Assert.Throws<InstallLinkingOperationException>(() => service.UpsertForInstallation(Installation(), request, 0)).StatusCode);
        var reconciled = service.UpsertForInstallation(Installation(), request, current.RemoteRevision, current.ServerToken);
        Assert.Equal(current.ServerToken, reconciled.ServerToken);
        Assert.Equal(1, remote.HeadPosts);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Remote_update_preserves_preconditions_and_rejects_complete_snapshot_downgrade()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var service = new InstallLinkedWorkspaceSnapshotService(store);
        var request = Request();
        var first = service.UpsertForInstallation(Installation(), request, 0);
        var changed = request with { Name = "Changed summary" };
        Assert.Equal(428, Assert.Throws<InstallLinkingOperationException>(() => service.UpsertForInstallation(Installation(), changed)).StatusCode);
        var next = service.UpsertForInstallation(Installation(), changed, first.RemoteRevision, first.ServerToken);
        Assert.Equal(2, next.RemoteRevision);
        Assert.NotEqual(first.ServerToken, next.ServerToken);
        Assert.Equal(409, Assert.Throws<InstallLinkingOperationException>(() => service.UpsertForInstallation(Installation(), request,
            first.RemoteRevision, first.ServerToken)).StatusCode);
        var downgraded = changed with { WorkspaceContinuation = null, WorkspaceContinuationDigest = null };
        Assert.Equal(409, Assert.Throws<InstallLinkingOperationException>(() => service.UpsertForInstallation(Installation(), downgraded,
            next.RemoteRevision, next.ServerToken)).StatusCode);
        Assert.Equal(next.ServerToken, Assert.Single(service.ListForInstallation(Installation())).ServerToken);
    }

    [Fact]
    public void Outage_never_reads_cached_or_legacy_local_character_state()
    {
        using var local = new InstallLinkedWorkspaceSnapshotStore(Configuration("local"));
        var localService = new InstallLinkedWorkspaceSnapshotService(local);
        var savedLocal = localService.UpsertForInstallation(Installation(), Request(), 0);
        using var remote = new Remote();
        using var store = Store(remote);
        var service = new InstallLinkedWorkspaceSnapshotService(store);
        Assert.Empty(service.ListForInstallation(Installation()));
        var savedRemote = service.UpsertForInstallation(Installation(), Request(), 0);
        remote.FailReads = true;
        Assert.Equal(503, Assert.Throws<InstallLinkingOperationException>(() => service.ListForInstallation(Installation())).StatusCode);
        Assert.Empty(store.SnapshotsByKey);
        Assert.Equal(savedLocal.ServerToken, Assert.Single(localService.ListForInstallation(Installation())).ServerToken);
        remote.FailReads = false;
        Assert.Equal(savedRemote.ServerToken, Assert.Single(service.ListForInstallation(Installation())).ServerToken);
        Assert.Single(Directory.GetFiles(_root));
    }

    [Theory]
    [InlineData("owner")]
    [InlineData("duplicate")]
    [InlineData("revision")]
    [InlineData("token")]
    [InlineData("foreign-continuation")]
    public async Task Corrupt_primary_identity_or_complete_history_is_never_repaired_from_another_source(string fault)
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var service = new InstallLinkedWorkspaceSnapshotService(store);
        service.UpsertForInstallation(Installation(), Request(), 0);
        string stream = InstallLinkedWorkspaceSnapshotStore.OwnerStream("subject:subject");
        var head = await remote.Store().ReadAsync(stream);
        var snapshot = JsonNode.Parse(head!.Bytes)!;
        var record = snapshot["snapshots"]![0]!;
        switch (fault)
        {
            case "owner": record["ownerKey"] = "subject:other"; break;
            case "duplicate": snapshot["snapshots"]!.AsArray().Add(record.DeepClone()); break;
            case "revision": record["remoteRevision"] = 0; break;
            case "token": record["serverToken"] = null; break;
            case "foreign-continuation":
                var foreign = Fixtures.ToContinuationRecord(Fixtures.SampleContinuation("other"));
                record["workspaceContinuation"] = JsonNode.Parse(foreign.WorkspaceContinuation!.Value.GetRawText());
                record["workspaceContinuationDigest"] = foreign.WorkspaceContinuationDigest;
                break;
        }
        await remote.Store().CompareExchangeAsync(stream, head, Guid.NewGuid(), JsonSerializer.SerializeToUtf8Bytes(snapshot));
        int writes = remote.HeadPosts;
        Assert.Equal(503, Assert.Throws<InstallLinkingOperationException>(
            () => service.ListForInstallation(Installation())).StatusCode);
        Assert.Empty(store.SnapshotsByKey);
        Assert.Equal(writes, remote.HeadPosts);
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Same_instance_remembers_owner_authority_across_owner_switches_and_detects_rollback()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var service = new InstallLinkedWorkspaceSnapshotService(store);
        var request = Request();
        var first = service.UpsertForInstallation(Installation(), request, 0);
        var oldRows = remote.Rows.ToDictionary(p => p.Key, p => (JsonObject)p.Value.DeepClone());
        service.UpsertForInstallation(Installation(), request with { Name = "New" }, first.RemoteRevision, first.ServerToken);
        Assert.Empty(service.ListForInstallation(Installation("other")));
        remote.Rows.Clear();
        foreach (var pair in oldRows) remote.Rows.Add(pair.Key, pair.Value);
        Assert.Equal(503, Assert.Throws<InstallLinkingOperationException>(() => service.ListForInstallation(Installation())).StatusCode);
        Assert.Empty(store.SnapshotsByKey);
    }

    [Fact]
    public void Primary_scopes_reject_legacy_gate_cross_owner_nesting_and_historical_erasure_claims()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        Assert.Throws<InvalidOperationException>(() => store.Gate);
        Assert.Throws<InvalidOperationException>(store.PersistLocked);
        using (store.Enter("subject:subject"))
        {
            using (store.Enter("subject:subject")) Assert.NotNull(store.Gate);
            Assert.Throws<InvalidOperationException>(() => store.Enter("subject:other"));
            Assert.NotNull(store.Gate);
        }
        Assert.Throws<InvalidOperationException>(store.EnsureAccountErasureSupported);
        Assert.Empty(remote.Rows);
    }

    [Fact]
    public void Explicit_runtime_registration_does_not_open_local_state_or_an_ambient_secret()
    {
        Assert.Throws<InvalidOperationException>(() => new InstallLinkedWorkspaceSnapshotStore(Configuration()));
        Assert.Throws<InvalidOperationException>(() => new InstallLinkedWorkspaceSnapshotStore(Configuration("unknown")));
        using var remote = new Remote();
        Assert.Throws<InvalidOperationException>(() => new InstallLinkedWorkspaceSnapshotStore(Configuration("local"), remote.Store()));
        if (!OperatingSystem.IsLinux() || System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture != System.Runtime.InteropServices.Architecture.X64) return;
        Directory.CreateDirectory(_root, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        string file = Path.Combine(_root, "synthetic-token");
        File.WriteAllText(file, "synthetic-only");
        File.SetUnixFileMode(file, UnixFileMode.UserRead | UnixFileMode.UserWrite);
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["CHUMMER_INSTALL_LINKING_STORAGE_PROVIDER"] = "teable",
            ["CHUMMER_DATA_PROTECTION_KEY_PROTECTION_MODE"] = "teable_primary",
            ["CHUMMER_INSTALL_LINKED_WORKSPACE_STORAGE_PROVIDER"] = "teable",
            ["CHUMMER_TEABLE_ORIGIN"] = "https://teable.example/",
            ["CHUMMER_INSTALL_LINKED_WORKSPACE_TEABLE_TABLE_ID"] = "tbl1234567890123456",
            ["CHUMMER_INSTALL_LINKED_WORKSPACE_TEABLE_TOKEN_FILE"] = file
        }).Build();
        var services = new ServiceCollection();
        services.AddSingleton<IConfiguration>(config);
        services.AddHubInstallAndOrchestrationAdapters(config, new Host());
        using var provider = services.BuildServiceProvider();
        Assert.NotNull(provider.GetRequiredService<InstallLinkedWorkspaceSnapshotService>());
        Assert.Empty(Directory.GetDirectories(_root));
    }

    private sealed class Host : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = Environments.Production;
        public string ApplicationName { get; set; } = "Chummer.Run.Api";
        public string ContentRootPath { get; set; } = Path.GetTempPath();
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }
    public void Dispose() { if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true); }
}
