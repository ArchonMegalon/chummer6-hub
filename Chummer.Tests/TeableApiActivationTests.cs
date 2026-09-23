using System.Text.Json;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking.Postgres;
using Chummer.Run.Api.Services.Teable;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Xunit;
using Remote = Chummer.Tests.TeableRevisionStoreTests.Remote;

namespace Chummer.Tests;

public sealed class TeableApiActivationTests : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "teable-api-activation-" + Guid.NewGuid().ToString("N"));
    private IConfiguration Configuration(string host = "host-a", Dictionary<string, string?>? changes = null)
    {
        var values = new Dictionary<string, string?>
        {
            ["CHUMMER_INSTALL_LINKING_STORAGE_PROVIDER"] = "teable",
            ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, host, "install-linking.json"),
            ["CHUMMER_DATA_PROTECTION_KEY_PROTECTION_MODE"] = "teable_primary",
            ["CHUMMER_DATA_PROTECTION_KEYS_PATH"] = Path.Combine(_root, host, "keys-must-not-exist"),
            ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] = Path.Combine(_root, "downloads"),
            ["CHUMMER_RELEASE_REGISTRY_MANIFEST_FILE"] = Path.Combine(_root, "no-release-manifest.json")
        };
        if (changes is not null) foreach (var pair in changes) values[pair.Key] = pair.Value;
        return new ConfigurationBuilder().AddInMemoryCollection(values).Build();
    }
    private sealed class Host(string environment = "Production") : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = environment;
        public string ApplicationName { get; set; } = "Chummer.Run.Api";
        public string ContentRootPath { get; set; } = Path.GetTempPath();
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }

    private ServiceProvider Services(Remote keys, Remote accounts, string host)
    {
        var configuration = Configuration(host);
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddSingleton(configuration);
        services.AddSingleton<IHostEnvironment>(new Host());
        var status = DataProtectionKeyProtectionConfigurator.ConfigureTeablePrimary(
            services.AddDataProtection().SetApplicationName("Chummer.Run.Api"), keys.Store(), ownsStore: true);
        Assert.True(status.Ready);
        services.AddSingleton(status);
        services.AddHubInstallAndOrchestrationAdapters(configuration, new Host());
        // Only the transport is replaced. Production activation, the coordinator,
        // protected snapshots and key providers use the real registrations.
        services.Replace(ServiceDescriptor.Singleton<TeableInstallLinkingRuntime>(_ => new(accounts.Store())));
        return services.BuildServiceProvider();
    }

    [Fact]
    public void Production_DI_restores_remote_keys_and_account_state_then_rejects_a_stale_grant_mirror()
    {
        using var keys = new Remote();
        using var accounts = new Remote();
        using var first = Services(keys, accounts, "host-a");
        var firstActivation = first.GetRequiredService<InstallLinkingStoreActivation>();
        var firstStore = firstActivation.GetRequiredStore();
        Assert.Equal("teable_authority_bound", firstActivation.Evaluate().Code);
        lock (firstStore.Gate)
        {
            firstStore.GrantsById["grant"] = new InstallationGrantDto("grant", "install", InstallationGrantStates.Active,
                "synthetic-private-token", DateTimeOffset.UtcNow, DateTimeOffset.UtcNow.AddHours(1), "user", "subject");
            firstStore.PersistLocked();
        }
        using var second = Services(keys, accounts, "cold-host-b");
        var secondStore = second.GetRequiredService<InstallLinkingStoreActivation>().GetRequiredStore();
        Assert.Equal("synthetic-private-token", Assert.Single(secondStore.GrantsById.Values).AccessToken);
        Assert.DoesNotContain("synthetic-private-token", File.ReadAllText(Configuration("cold-host-b")["CHUMMER_INSTALL_LINKING_STORE_PATH"]!));
        lock (secondStore.Gate)
        {
            secondStore.GrantsById.Remove("grant");
            secondStore.PersistLocked();
        }
        Assert.Equal(new InstallLinkingStoreReadiness(false, "teable_authority_head_mismatch"), firstActivation.Evaluate());
        Assert.Throws<InvalidOperationException>(firstActivation.GetRequiredStore);
        using var third = Services(keys, accounts, "cold-host-c");
        Assert.Empty(third.GetRequiredService<InstallLinkingStoreActivation>().GetRequiredStore().GrantsById);
        Assert.Null(first.GetService<NpgsqlInstallLinkingSnapshotAuthority>());
        Assert.False(Directory.Exists(Configuration()["CHUMMER_DATA_PROTECTION_KEYS_PATH"]));
        Assert.False(Directory.Exists(Configuration("cold-host-b")["CHUMMER_DATA_PROTECTION_KEYS_PATH"]));
    }

    [Fact]
    public void Actual_remote_key_custody_has_a_live_readiness_probe_not_a_local_directory_probe()
    {
        using var keys = new Remote();
        using var accounts = new Remote();
        using var services = Services(keys, accounts, "readiness");
        var configuration = Configuration("readiness");
        var shelf = new ReleaseShelfGenerationStore(configuration);
        var readiness = new HubDeepReadinessService(configuration, new Host(), new(configuration, shelf), shelf,
            dataProtectionKeyProtection: services.GetRequiredService<DataProtectionKeyProtectionStatus>(),
            primaryKeyReadiness: services.GetRequiredService<IDataProtectionPrimaryReadinessProbe>());
        var check = Assert.Single(readiness.Evaluate().Checks, c => c.Name == "data_protection_storage");
        Assert.True(check.Passed);
        Assert.Equal("teable_primary_key_ring", check.Code);
        keys.FailReads = true;
        check = Assert.Single(readiness.Evaluate().Checks, c => c.Name == "data_protection_storage");
        Assert.False(check.Passed);
        Assert.Equal("teable_key_ring_unavailable", check.Code);
        Assert.False(Directory.Exists(configuration["CHUMMER_DATA_PROTECTION_KEYS_PATH"]));
    }

    [Fact]
    public void Remote_key_ready_status_without_the_actual_primary_probe_is_rejected()
    {
        var configuration = Configuration();
        var shelf = new ReleaseShelfGenerationStore(configuration);
        var readiness = new HubDeepReadinessService(configuration, new Host(), new(configuration, shelf), shelf,
            dataProtectionKeyProtection: new(true, "teable_primary_key_ring"));
        var check = Assert.Single(readiness.Evaluate().Checks, c => c.Name == "data_protection_storage");
        Assert.False(check.Passed);
        Assert.Equal("teable_key_ring_probe_missing", check.Code);
        Assert.False(Directory.Exists(configuration["CHUMMER_DATA_PROTECTION_KEYS_PATH"]));
    }

    [Fact]
    public async Task Remote_key_configuration_rejects_old_encrypted_history_without_creating_replacement_keys()
    {
        using var keys = new Remote();
        await keys.Store().CompareExchangeAsync("data-protection-keys", null, Guid.NewGuid(),
            JsonSerializer.SerializeToUtf8Bytes(new[] { "<key version=\"1\"><encryptedSecret>retained</encryptedSecret></key>" }));
        int writes = keys.HeadPosts;
        var services = new ServiceCollection();
        var status = DataProtectionKeyProtectionConfigurator.ConfigureTeablePrimary(
            services.AddDataProtection(), keys.Store(), ownsStore: true);
        Assert.False(status.Ready);
        Assert.Equal("teable_key_ring_configuration_invalid", status.Code);
        Assert.Equal(writes, keys.HeadPosts);
        using var provider = services.BuildServiceProvider();
        Assert.Null(provider.GetService<IDataProtectionPrimaryReadinessProbe>());
    }

    [Theory]
    [InlineData("CHUMMER_DATA_PROTECTION_CERTIFICATE_PATH", "old.pfx", "data_protection_conflicting_key_protection_modes")]
    [InlineData("CHUMMER_DATA_PROTECTION_CERTIFICATE_PASSWORD", "not-allowed", "plaintext_certificate_password_rejected")]
    [InlineData("CHUMMER_DATA_PROTECTION_TEABLE_TOKEN_FILE", "/missing/token", "teable_key_ring_configuration_invalid")]
    public void Teable_key_mode_never_falls_back_to_local_keys(string setting, string value, string expected)
    {
        var configuration = Configuration(changes: new() { [setting] = value });
        var status = DataProtectionKeyProtectionConfigurator.Configure(new ServiceCollection(), configuration,
            new Host(), configuration["CHUMMER_DATA_PROTECTION_KEYS_PATH"]!);
        Assert.False(status.Ready);
        Assert.Equal(expected, status.Code);
        Assert.False(Directory.Exists(_root));
    }

    [Theory]
    [InlineData("CHUMMER_INSTALL_LINKING_STORAGE_PROVIDER", "unknown")]
    [InlineData("CHUMMER_DATA_PROTECTION_KEY_PROTECTION_MODE", "owner_only_local")]
    [InlineData("CHUMMER_PUBLIC_DOWNLOAD_ONLY", "true")]
    [InlineData("CHUMMER_INSTALL_LINKING_POSTGRES_CONNECTION_STRING_FILE", "/competing/file")]
    [InlineData("CHUMMER_INSTALL_LINKING_POSTGRES_CONNECTION_STRING", "competing-inline")]
    public void Competing_or_incomplete_primary_registration_is_rejected(string setting, string value)
    {
        var configuration = Configuration(changes: new() { [setting] = value });
        Assert.Throws<InvalidOperationException>(() => new ServiceCollection()
            .AddHubInstallAndOrchestrationAdapters(configuration, new Host()));
    }

    [Fact]
    public void Development_mode_cannot_discard_the_requested_remote_account_authority()
    {
        Assert.Throws<InvalidOperationException>(() => new ServiceCollection()
            .AddHubInstallAndOrchestrationAdapters(Configuration(), new Host(Environments.Development)));
    }

    [Fact]
    public async Task Teable_coordinator_does_not_claim_PostgreSQL_read_fences_and_reports_outages_safely()
    {
        using var remote = new Remote();
        var coordinator = new InstallLinkingPostgresAuthorityCoordinator(new TeableInstallLinkingSnapshotAuthority(remote.Store()), "teable");
        using var head = await coordinator.ReadCurrentAsync();
        coordinator.BindValidatedLocalMirror(head);
        Assert.Equal(new InstallLinkingRollbackAuthorityReadiness(true, "teable_authority_bound"), coordinator.Evaluate());
        bool captured = false;
        Assert.Equal(new InstallLinkingRollbackAuthorityReadiness(false, "teable_read_fence_unavailable"),
            coordinator.ReadBoundLocalMirror(() => captured = true));
        Assert.False(captured);
        remote.FailReads = true;
        Assert.Equal(new InstallLinkingRollbackAuthorityReadiness(false, "teable_unavailable"), coordinator.Evaluate());
    }

    public void Dispose() { if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true); }
}
