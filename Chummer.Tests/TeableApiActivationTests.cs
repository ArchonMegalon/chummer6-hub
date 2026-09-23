using System.Text.Json;
using System.Security.Cryptography;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking.Postgres;
using Chummer.Run.Api.Services.Teable;
using Chummer.Storage.Teable;
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
    public async Task Primary_readiness_overlaps_independent_reads_but_never_accepts_an_invalid_schema()
    {
        using var remote = new Remote();
        using var handler = new OverlappingReadiness(remote);
        using var client = new HttpClient(handler) { BaseAddress = new Uri("https://teable.example/") };
        using var store = new TeableRevisionStore(client, "tbl1234567890123456", "synthetic-token");
        var authority = new TeableInstallLinkingSnapshotAuthority(store);
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(2));
        using var current = await authority.ReadCurrentForReadinessAsync(deadline.Token);
        Assert.True(handler.HeadStarted);
        Assert.Equal(0, current.Generation);
        remote.Unique = false;
        await Assert.ThrowsAsync<InvalidDataException>(() => authority.ReadCurrentForReadinessAsync(deadline.Token));
    }

    private sealed class OverlappingReadiness(HttpMessageHandler inner) : DelegatingHandler(inner)
    {
        private readonly TaskCompletionSource _head = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public bool HeadStarted => _head.Task.IsCompletedSuccessfully;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            if (request.RequestUri!.AbsolutePath.EndsWith("/field", StringComparison.Ordinal))
                await _head.Task.WaitAsync(ct);
            else _head.TrySetResult();
            return await base.SendAsync(request, ct);
        }
    }

    [Fact]
    public void Primary_readiness_checks_schema_and_one_current_envelope_without_duplicate_payload_reads()
    {
        using var keys = new Remote();
        using var accounts = new Remote();
        using var services = Services(keys, accounts, "readiness");
        var activation = services.GetRequiredService<InstallLinkingStoreActivation>();
        var store = activation.GetRequiredStore();
        lock (store.Gate)
        {
            store.GrantsById["synthetic"] = new("synthetic", "install", InstallationGrantStates.Active,
                "synthetic-only", DateTimeOffset.UtcNow, DateTimeOffset.UtcNow.AddMinutes(1), "user", "subject");
            store.PersistLocked();
        }
        int reads = accounts.GetRequests;
        Assert.True(activation.Evaluate().Ready);
        Assert.Equal(3, accounts.GetRequests - reads); // schema, head, one bounded chunk
        accounts.Unique = false;
        Assert.False(activation.Evaluate().Ready);
        accounts.Unique = true;
        accounts.FailReads = true;
        Assert.False(activation.Evaluate().Ready);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void V2_bootstrap_does_not_recheck_remote_authority_for_every_dictionary_access(bool outageAfterCommit)
    {
        using var keys = new Remote();
        using var accounts = new Remote();
        using var services = Services(keys, accounts, "bootstrap");
        var activation = services.GetRequiredService<InstallLinkingStoreActivation>();
        var service = new InstallLinkingService(new InstallLinkingStoreAccess(activation), Configuration("bootstrap"), activation);
        using var rsa = RSA.Create(2048);
        string publicKey = Convert.ToBase64String(rsa.ExportSubjectPublicKeyInfo());
        _ = activation.GetRequiredStore();
        int approvalReads = accounts.GetRequests;
        service.IssueBrowserCallback(new(InstallationId: "android-probe", ArtifactId: "android-play-app", ApplicationVersion: "synthetic",
            ChannelId: "internal", HeadId: "android", Platform: "android", Arch: "arm64", CallbackUri: "chummer://install-link",
            PublicKey: publicKey, HostLabel: null, InstallAccessClass: InstallAccessClasses.AccountRequired), "user-probe", "subject-probe", "proof_poll_v2");
        Assert.InRange(accounts.GetRequests - approvalReads, 1, 30);
        var request = new AndroidInstallLinkProofPollV2Request("android-probe", "android", "synthetic", "internal", "android", "arm64",
            publicKey, DateTimeOffset.UtcNow.ToUnixTimeSeconds(), new string('n', 24), "", null, new string('o', 32), "proof_poll_v2");
        request = request with { Signature = Convert.ToBase64String(rsa.SignData(AndroidInstallLinkV2BootstrapProof.CreateCanonicalPayload(request),
            HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1)) };
        if (outageAfterCommit)
        {
            // Nonce commit, then grant commit, then the final fresh authority
            // check. The committed grant must not be returned on an outage.
            accounts.BeforeHeadPost = () => accounts.BeforeHeadPost = () =>
                accounts.BeforeHeadReadResponse = () => accounts.FailReads = true;
        }
        int reads = accounts.GetRequests;
        if (outageAfterCommit)
        {
            var error = Assert.Throws<InstallLinkingOperationException>(() => service.PollBrowserCallbackV2(request));
            Assert.Equal(503, error.StatusCode);
            Assert.True(accounts.FailReads);
        }
        else
        {
            var result = service.PollBrowserCallbackV2(request);
            Assert.NotNull(result.Exchange);
            Assert.False(result.Exchange.AlreadyClaimed);
            int admissionReads = accounts.GetRequests;
            var principal = service.ResolveAndroidLinkedV2Grant("android-probe",
                result.Exchange.Grant.GrantId, result.Exchange.Grant.AccessToken);
            Assert.NotNull(principal);
            Assert.True(service.TryUseAndroidLinkedV2Proof(principal.GrantId,
                new string('p', 43), DateTimeOffset.UtcNow, DateTimeOffset.UtcNow.AddMinutes(1)));
            Assert.NotNull(service.ResolveAndroidLinkedV2Principal(principal));
            int totalAdmissionReads = accounts.GetRequests - admissionReads;
            Console.WriteLine($"Signed request primary GETs: {totalAdmissionReads}");
            Assert.InRange(totalAdmissionReads, 1, 25);
            reads += totalAdmissionReads;
        }
        // Retain fresh operation admission, nonce persistence, grant CAS and
        // final authority read; do not multiply those by each field lookup.
        Assert.InRange(accounts.GetRequests - reads, 1, 45);
        Console.WriteLine($"Bootstrap primary GETs: {accounts.GetRequests - reads}; post-commit outage: {outageAfterCommit}");
        accounts.FailReads = true;
        Assert.Throws<InstallLinkingOperationException>(() => service.PollBrowserCallbackV2(request));
        accounts.FailReads = false;
        using var cold = Services(keys, accounts, "bootstrap-cold");
        var coldActivation = cold.GetRequiredService<InstallLinkingStoreActivation>();
        string grantId = Assert.Single(coldActivation.GetRequiredStore().GrantsById.Values).GrantId;
        request = request with { Nonce = new string('r', 24), Signature = "" };
        request = request with { Signature = Convert.ToBase64String(rsa.SignData(AndroidInstallLinkV2BootstrapProof.CreateCanonicalPayload(request),
            HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1)) };
        var coldService = new InstallLinkingService(new InstallLinkingStoreAccess(coldActivation), Configuration("bootstrap-cold"), coldActivation);
        var recovered = coldService.PollBrowserCallbackV2(request);
        Assert.NotNull(recovered.Exchange);
        Assert.True(recovered.Exchange.AlreadyClaimed);
        Assert.Equal(grantId, recovered.Exchange.Grant.GrantId);
        Assert.Single(coldActivation.GetRequiredStore().GrantsById);
        if (!outageAfterCommit)
        {
            var principal = coldService.ResolveAndroidLinkedV2Grant("android-probe", grantId, recovered.Exchange.Grant.AccessToken);
            Assert.NotNull(principal);
            accounts.BeforeHeadPost = () => accounts.BeforeHeadReadResponse = () => accounts.FailReads = true;
            var proofError = Assert.Throws<InstallLinkingOperationException>(() => coldService.TryUseAndroidLinkedV2Proof(
                grantId, new string('q', 43), DateTimeOffset.UtcNow, DateTimeOffset.UtcNow.AddMinutes(1)));
            Assert.Equal(503, proofError.StatusCode);
            Assert.Null(coldService.ResolveAndroidLinkedV2Principal(principal));
            accounts.FailReads = false;
            Assert.False(coldService.TryUseAndroidLinkedV2Proof(grantId, new string('q', 43),
                DateTimeOffset.UtcNow, DateTimeOffset.UtcNow.AddMinutes(1))); // committed proof cannot replay

            accounts.BeforeHeadPost = () => accounts.BeforeHeadReadResponse = () => accounts.FailReads = true;
            int revocationReads = accounts.GetRequests;
            var revokeError = Assert.Throws<InstallLinkingOperationException>(() => coldService.RevokeAndroidLinkedV2Grant(principal));
            Assert.Equal(503, revokeError.StatusCode);
            Assert.InRange(accounts.GetRequests - revocationReads, 1, 30);
            accounts.FailReads = false;
            using var afterRevoke = Services(keys, accounts, "after-revoke");
            var restored = afterRevoke.GetRequiredService<InstallLinkingStoreActivation>().GetRequiredStore();
            Assert.Equal(InstallationGrantStates.Revoked, Assert.Single(restored.GrantsById.Values).Status);
            Assert.Null(coldService.ResolveAndroidLinkedV2Grant("android-probe", grantId, recovered.Exchange.Grant.AccessToken));
        }
    }

    [Theory]
    [InlineData("activation")]
    [InlineData("fixed-access")]
    [InlineData("direct")]
    public void Signed_admission_never_skips_an_independent_readiness_probe(string access)
    {
        using var keys = new Remote();
        using var accounts = new Remote();
        using var services = Services(keys, accounts, "independent-probe");
        var activation = services.GetRequiredService<InstallLinkingStoreActivation>();
        var store = activation.GetRequiredStore();
        var probe = new UnavailableProbe();
        var configuration = Configuration("independent-probe");
        var service = access switch
        {
            "activation" => new InstallLinkingService(new InstallLinkingStoreAccess(activation), configuration, probe),
            "fixed-access" => new InstallLinkingService(new InstallLinkingStoreAccess(store), configuration, probe),
            _ => new InstallLinkingService(store, configuration, probe)
        };
        int writes = accounts.HeadPosts;
        Assert.Null(service.ResolveAndroidLinkedV2Grant("install", "grant", "token"));
        var error = Assert.Throws<InstallLinkingOperationException>(() => service.TryUseAndroidLinkedV2Proof(
            "grant", new string('p', 43), DateTimeOffset.UtcNow, DateTimeOffset.UtcNow.AddMinutes(1)));
        Assert.Equal(503, error.StatusCode);
        Assert.Equal(2, probe.Calls);
        Assert.Equal(writes, accounts.HeadPosts);
    }

    private sealed class UnavailableProbe : IInstallLinkingStoreReadinessProbe
    {
        public int Calls { get; private set; }
        public InstallLinkingStoreReadiness Evaluate()
        {
            Calls++;
            return new(false, "synthetic-independent-probe");
        }
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
    public void Primary_install_erasure_cannot_claim_success_while_private_history_remains()
    {
        using var keys = new Remote();
        using var accounts = new Remote();
        using var services = Services(keys, accounts, "erasure");
        var store = services.GetRequiredService<InstallLinkingStoreActivation>().GetRequiredStore();
        lock (store.Gate)
        {
            store.GrantsById["grant"] = new InstallationGrantDto("grant", "install", InstallationGrantStates.Active,
                "synthetic-private-token", DateTimeOffset.UtcNow, DateTimeOffset.UtcNow.AddHours(1), "user", "subject");
            store.PersistLocked();
        }
        int writes = accounts.HeadPosts;
        byte[] mirror = File.ReadAllBytes(store.StoragePath);

        Assert.Throws<InvalidOperationException>(() => store.ErasePrincipal("user", "subject"));

        Assert.Equal(writes, accounts.HeadPosts);
        Assert.Equal(mirror, File.ReadAllBytes(store.StoragePath));
        Assert.True(store.IsHealthy);
        Assert.Single(store.GrantsById);
        using var restored = Services(keys, accounts, "erasure-reopen");
        Assert.Single(restored.GetRequiredService<InstallLinkingStoreActivation>().GetRequiredStore().GrantsById);
    }

    [Theory]
    [InlineData("postgres")]
    [InlineData("teable")]
    public void Actual_append_only_authority_blocks_erasure_even_with_a_legacy_backend_label(string backend)
    {
        using var remote = new Remote();
        var coordinator = new InstallLinkingPostgresAuthorityCoordinator(new TeableInstallLinkingSnapshotAuthority(remote.Store()), backend);
        Assert.Throws<InvalidOperationException>(coordinator.EnsureAccountErasureSupported);
        Assert.Empty(remote.Rows);
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
