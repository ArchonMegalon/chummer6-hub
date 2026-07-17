using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.Support;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class StoreCorruptionRecoveryTests
{
    [Fact]
    public void SupportStoreQuarantinesCorruptSnapshotAndStartsEmpty()
    {
        using TempStoreFile temp = new("support-store.json");
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?> { ["CHUMMER_SUPPORT_STORE_PATH"] = temp.Path })
            .Build();

        SupportStore store = new(configuration, NullLogger<SupportStore>.Instance);

        Assert.Empty(store.CasesById);
        Assert.Empty(store.IncidentsById);
        Assert.Single(Directory.GetFiles(temp.Root, "support-store.json.corrupt-*"));
        Assert.False(File.Exists(temp.Path));
    }

    [Fact]
    public void InstallLinkingStoreQuarantinesCorruptSnapshotAndFailsClosed()
    {
        using TempStoreFile temp = new("install-linking-store.json");
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?> { ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = temp.Path })
            .Build();

        InvalidOperationException failure = Assert.Throws<InvalidOperationException>(() =>
            new InstallLinkingStore(
                configuration,
                DataProtectionProvider.Create(Path.Combine(temp.Root, "install-linking-keys")),
                NullLogger<InstallLinkingStore>.Instance));

        Assert.Equal("Install-linking durable state validation failed; startup is fail-closed.", failure.Message);
        Assert.Single(Directory.GetFiles(temp.Root, ".install-linking-store.json.quarantine-*"));
        Assert.True(File.Exists(temp.Path));
    }

    [Fact]
    public void PublicConciergeStoreQuarantinesCorruptSnapshotAndStartsEmpty()
    {
        using TempStoreFile temp = new("public-concierge-store.json");
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?> { ["CHUMMER_PUBLIC_CONCIERGE_STORE_PATH"] = temp.Path })
            .Build();

        PublicConciergeStore store = new(configuration, NullLogger<PublicConciergeStore>.Instance);

        Assert.Empty(store.BranchReceiptsById);
        Assert.Empty(store.WebhookReceiptsById);
        Assert.Single(Directory.GetFiles(temp.Root, "public-concierge-store.json.corrupt-*"));
        Assert.False(File.Exists(temp.Path));
    }

    [Fact]
    public void CommunityStoreQuarantinesCorruptSnapshotAndStartsEmpty()
    {
        using TempStoreFile temp = new("community-store.json");
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?> { ["CHUMMER_COMMUNITY_STORE_PATH"] = temp.Path })
            .Build();

        CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);

        Assert.Empty(store.UsersById);
        Assert.Empty(store.GroupsById);
        Assert.Single(Directory.GetFiles(temp.Root, "community-store.json.corrupt-*"));
        Assert.False(File.Exists(temp.Path));
    }

    [Fact]
    public void BrilliantDirectoriesBillingStoreQuarantinesCorruptSnapshotAndStartsEmpty()
    {
        using TempStoreFile temp = new("brilliant-directories-billing-store.json");
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?> { ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = temp.Path })
            .Build();

        BrilliantDirectoriesBillingStore store = new(configuration);

        Assert.Empty(store.Members);
        Assert.Single(Directory.GetFiles(temp.Root, "brilliant-directories-billing-store.json.corrupt-*"));
        Assert.False(File.Exists(temp.Path));
    }

    [Fact]
    public void MyFirstBookUsageStoreQuarantinesCorruptSnapshotAndStartsEmpty()
    {
        using TempStoreFile temp = new("myfirstbook-usage-store.json");
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?> { ["CHUMMER_MYFIRSTBOOK_USAGE_STORE_PATH"] = temp.Path })
            .Build();

        MyFirstBookUsageStore store = new(configuration);

        Assert.Empty(store.Entries);
        Assert.Single(Directory.GetFiles(temp.Root, "myfirstbook-usage-store.json.corrupt-*"));
        Assert.False(File.Exists(temp.Path));
    }

    private sealed class TempStoreFile : IDisposable
    {
        public TempStoreFile(string fileName)
        {
            Root = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "chummer-store-corruption-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(Root);
            Path = System.IO.Path.Combine(Root, fileName);
            File.WriteAllText(Path, "{ definitely-not-json", System.Text.Encoding.UTF8);
        }

        public string Root { get; }
        public string Path { get; }

        public void Dispose()
        {
            if (Directory.Exists(Root))
            {
                Directory.Delete(Root, recursive: true);
            }
        }
    }
}
