using System.Text;
using System.Text.Json.Nodes;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Contracts.Community;
using Chummer.Storage.Teable;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;

namespace Chummer.Tests;

public sealed class CampaignArtifactTeablePersistenceTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "campaign-artifact-teable-" + Guid.NewGuid().ToString("N"));
    private IConfiguration Configuration => new ConfigurationBuilder().AddInMemoryCollection(
        new Dictionary<string, string?>
        {
            ["CHUMMER_COMMUNITY_STORAGE_PROVIDER"] = "teable",
            ["CHUMMER_SUPPORT_STORE_PATH"] = Path.Combine(_root, "support.json")
        }).Build();

    private CommunityStore Store(Remote remote) => new(Configuration, NullLogger<CommunityStore>.Instance, remote.Store());
    private CampaignSpineService Service(CommunityStore store) => new(store,
        new WorkspaceLifecyclePolicyService(Configuration), new CampaignArtifactRegistryBridge(store),
        new SupportStore(Configuration, NullLogger<SupportStore>.Instance));

    private static AftermathArtifactRegistrationRequest Request(string id) => new(
        id, "workspace-synthetic", "campaign-synthetic", "Synthetic campaign", null, null,
        "session_recap", "Synthetic recap", "Synthetic private summary", "synthetic-owner", "sr5",
        "synthetic-rule-fingerprint", DateTimeOffset.UtcNow, ["Continuity: synthetic only"]);

    private (HubUserDto User, CampaignWorkspaceProjection Workspace) Context(CommunityStore store)
    {
        var user = new AccountService(store).EnsureUser("synthetic-subject");
        return (user, Service(store).GetStarterWorkspace(user)!);
    }

    private AftermathRecapPackageProjection Record(CommunityStore store, HubUserDto user, CampaignWorkspaceProjection workspace, string title)
        => Service(store).RecordAftermathRecapPackage(user, workspace, workspace.Runs.First(),
            "session_recap", title, "Synthetic private summary", ["Continuity: synthetic only"]);

    [Fact]
    public void Aftermath_and_artifact_restore_together_from_one_commit_without_local_files()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var (user, workspace) = Context(writer);
        int writes = remote.HeadPosts;
        var package = Record(writer, user, workspace, "Synthetic recap");
        Assert.Equal(writes + 1, remote.HeadPosts);

        using var cold = Store(remote);
        using (cold.Enter())
        {
            Assert.Equal(package.PackageId, Assert.Single(cold.AftermathPackages).PackageId);
            var artifact = Assert.Single(cold.CampaignArtifactRegistry!.Artifacts);
            Assert.Equal(package.ArtifactId, artifact.Id);
            Assert.Equal(package.ArtifactVersion, artifact.Version);
            Assert.Equal(user.UserId, artifact.Owner);
            Assert.Contains("Synthetic private summary", artifact.Summary, StringComparison.Ordinal);
        }
        Assert.False(Directory.Exists(_root));
    }

    [Fact]
    public void Existing_bridge_refreshes_metadata_before_registering_another_artifact()
    {
        using var remote = new Remote();
        using var first = Store(remote);
        var earlyBridge = new CampaignArtifactRegistryBridge(first);
        using var second = Store(remote);
        var winner = new CampaignArtifactRegistryBridge(second).RegisterAftermathPackage(Request("first"));
        var later = earlyBridge.RegisterAftermathPackage(Request("second"));
        using var cold = Store(remote);
        using var scope = cold.Enter();
        Assert.Equal(2, cold.CampaignArtifactRegistry!.Artifacts.Count);
        Assert.Contains(cold.CampaignArtifactRegistry.Artifacts, item => item.Id == winner.ArtifactId);
        Assert.Contains(cold.CampaignArtifactRegistry.Artifacts, item => item.Id == later.ArtifactId);
    }

    [Fact]
    public void Callback_failure_even_after_staged_persist_rolls_back_without_remote_write()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var user = new AccountService(store).EnsureUser("synthetic-subject");
        var bridge = new CampaignArtifactRegistryBridge(store);
        int writes = remote.HeadPosts;
        Assert.Throws<IOException>(() => bridge.ExecuteAftermathRegistrationTransaction<int>(Request("failed"), _ =>
        {
            store.UsersById[user.UserId] = user with { DisplayName = "Must not commit" };
            store.PersistLocked();
            throw new IOException("synthetic failure after staged persist");
        }));
        Assert.Equal(writes, remote.HeadPosts);
        Assert.Equal(user.DisplayName, new AccountService(store).GetById(user.UserId)!.DisplayName);
        var recovered = bridge.RegisterAftermathPackage(Request("recovered"));
        using var cold = Store(remote);
        using var scope = cold.Enter();
        Assert.Equal(recovered.ArtifactId, Assert.Single(cold.CampaignArtifactRegistry!.Artifacts).Id);
    }

    [Fact]
    public void Aftermath_failure_restores_projection_and_artifact_then_allows_a_clean_retry()
    {
        using var remote = new Remote();
        using var store = Store(remote);
        var (user, workspace) = Context(store);
        int writes = remote.HeadPosts;
        store.AftermathPersistenceFaultInjector = () => throw new IOException("synthetic projection failure");
        Assert.Throws<IOException>(() => Record(store, user, workspace, "Failed recap"));
        Assert.Equal(writes, remote.HeadPosts);
        using (store.Enter())
        {
            Assert.Empty(store.AftermathPackages);
            Assert.Null(store.CampaignArtifactRegistry);
        }
        store.AftermathPersistenceFaultInjector = null;
        var result = Record(store, user, workspace, "Recovered recap");
        using var cold = Store(remote);
        using var scope = cold.Enter();
        Assert.Equal(result.ArtifactId, Assert.Single(cold.AftermathPackages).ArtifactId);
        Assert.Equal(result.ArtifactId, Assert.Single(cold.CampaignArtifactRegistry!.Artifacts).Id);
    }

    [Fact]
    public void Competing_afterthought_commit_cannot_leave_a_loser_artifact_or_projection()
    {
        using var remote = new Remote();
        using var first = Store(remote);
        var (user, workspace) = Context(first);
        using var second = Store(remote);
        AftermathRecapPackageProjection? winner = null;
        remote.BeforeHeadPost = () => winner = Record(second, user, workspace, "Winning recap");
        Assert.Throws<TeableRevisionConflictException>(() => Record(first, user, workspace, "Losing recap"));
        Assert.NotNull(winner);
        Assert.Throws<InvalidOperationException>(() => Service(first).GetAccountSummary(user));
        using var cold = Store(remote);
        using var scope = cold.Enter();
        Assert.Equal(winner.PackageId, Assert.Single(cold.AftermathPackages).PackageId);
        Assert.Equal(winner.ArtifactId, Assert.Single(cold.CampaignArtifactRegistry!.Artifacts).Id);
    }

    [Fact]
    public void Uncertain_commit_cold_restores_both_parts_without_compensating_overwrite()
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var (user, workspace) = Context(writer);
        remote.CommitThenFailHard = true;
        Assert.Throws<IOException>(() => Record(writer, user, workspace, "Uncertain recap"));
        int writes = remote.HeadPosts;
        Assert.Throws<InvalidOperationException>(() => Record(writer, user, workspace, "Do not retry"));
        using var cold = Store(remote);
        using var scope = cold.Enter();
        Assert.Equal(Assert.Single(cold.AftermathPackages).ArtifactId, Assert.Single(cold.CampaignArtifactRegistry!.Artifacts).Id);
        Assert.Equal(writes, remote.HeadPosts);
    }

    [Theory]
    [InlineData("old-schema")]
    [InlineData("missing-artifacts")]
    [InlineData("foreign-contract")]
    [InlineData("duplicate-id")]
    public async Task Invalid_or_incomplete_primary_metadata_is_rejected_on_cold_restore(string corruption)
    {
        using var remote = new Remote();
        using var writer = Store(remote);
        var (user, workspace) = Context(writer);
        Record(writer, user, workspace, "Original recap");
        using var transport = remote.Store();
        var head = (await transport.ReadAsync("community", CancellationToken.None))!;
        var payload = JsonNode.Parse(head.Bytes)!;
        var backup = payload["snapshot"]!["campaignArtifactRegistry"]!;
        if (corruption == "old-schema") payload["schema"] = "chummer.hub.community-primary/v1";
        else if (corruption == "missing-artifacts") payload["snapshot"]!["campaignArtifactRegistry"] = null;
        else if (corruption == "foreign-contract") backup["contractFamily"] = "foreign_registry";
        else backup["artifacts"]!.AsArray().Add(backup["artifacts"]![0]!.DeepClone());
        await transport.CompareExchangeAsync("community", head, Guid.NewGuid(), Encoding.UTF8.GetBytes(payload.ToJsonString()), CancellationToken.None);
        int writes = remote.HeadPosts;
        Assert.Throws<InvalidDataException>(() => Store(remote));
        Assert.Equal(writes, remote.HeadPosts);
    }

    [Fact]
    public void Primary_outage_never_falls_back_to_local_registry_or_stale_memory()
    {
        var localPath = Path.Combine(_root, "community.json");
        var legacy = new CampaignArtifactRegistryBridge(localPath).RegisterAftermathPackage(Request("local-only"));
        string file = Path.Combine(_root, "campaign-artifact-registry.json");
        byte[] before = File.ReadAllBytes(file);
        using var remote = new Remote();
        using var primary = Store(remote);
        var bridge = new CampaignArtifactRegistryBridge(primary);
        var current = bridge.RegisterAftermathPackage(Request("primary-only"));
        using (primary.Enter())
        {
            Assert.Equal(current.ArtifactId, Assert.Single(primary.CampaignArtifactRegistry!.Artifacts).Id);
            Assert.DoesNotContain(primary.CampaignArtifactRegistry.Artifacts, item => item.Id == legacy.ArtifactId);
        }
        remote.FailReads = true;
        Assert.Throws<HttpRequestException>(() => bridge.RegisterAftermathPackage(Request("must-fail")));
        Assert.Throws<InvalidOperationException>(() => bridge.RegisterAftermathPackage(Request("must-not-retry")));
        Assert.Equal(before, File.ReadAllBytes(file));
    }

    public void Dispose()
    {
        if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
    }
}
