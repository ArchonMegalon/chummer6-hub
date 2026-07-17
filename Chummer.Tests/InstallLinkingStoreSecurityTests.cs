using System.Text.Json;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class InstallLinkingStoreSecurityTests
{
    private const string SecretMarker = "install-link-secret-marker-3f5f50eb";
    private const string FailClosedMessage =
        "Install-linking durable state validation failed; startup is fail-closed.";
    private const UnixFileMode OwnerDirectoryMode =
        UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute;
    private const UnixFileMode OwnerFileMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;

    [Fact]
    public void Store_requires_an_explicit_data_protection_provider()
    {
        System.Reflection.ConstructorInfo constructor = Assert.Single(typeof(InstallLinkingStore).GetConstructors());
        Type[] parameterTypes = constructor.GetParameters().Select(static parameter => parameter.ParameterType).ToArray();

        Assert.Equal(
            [typeof(IConfiguration), typeof(IDataProtectionProvider), typeof(ILogger<InstallLinkingStore>)],
            parameterTypes);
    }

    [Fact]
    public void Protected_snapshot_survives_restart_without_plaintext_markers_or_temp_residue()
    {
        using StoreFixture fixture = new();
        IDataProtectionProvider firstProvider = fixture.CreateProvider("stable-keys");
        using InstallLinkingStore first = fixture.CreateStore(firstProvider);
        InstallationGrantDto grant = CreateGrant(SecretMarker);

        lock (first.Gate)
        {
            first.GrantsById[grant.GrantId] = grant;
            first.PersistLocked();
        }

        string durableText = File.ReadAllText(fixture.StorePath);
        Assert.DoesNotContain(SecretMarker, durableText, StringComparison.Ordinal);
        using (JsonDocument envelope = JsonDocument.Parse(durableText))
        {
            Assert.Equal("chummer.install-linking-store", envelope.RootElement.GetProperty("format").GetString());
            Assert.Equal(2, envelope.RootElement.GetProperty("version").GetInt32());
            Assert.Equal(1, envelope.RootElement.GetProperty("generation").GetInt64());
            Assert.False(string.IsNullOrWhiteSpace(envelope.RootElement.GetProperty("protectedPayload").GetString()));
            Assert.Equal(4, envelope.RootElement.EnumerateObject().Count());
        }

        first.Dispose();
        IDataProtectionProvider restartedProvider = fixture.CreateProvider("stable-keys");
        using InstallLinkingStore restarted = fixture.CreateStore(restartedProvider);
        InstallationGrantDto reloaded = Assert.Single(restarted.GrantsById.Values);
        Assert.Equal(SecretMarker, reloaded.AccessToken);
        Assert.Empty(Directory.GetFiles(fixture.Root, ".install-linking-store.json.tmp-*"));

        if (!OperatingSystem.IsWindows())
        {
            Assert.Equal(OwnerDirectoryMode, File.GetUnixFileMode(fixture.Root));
            Assert.Equal(OwnerFileMode, File.GetUnixFileMode(fixture.StorePath));
        }
    }

    [Fact]
    public void Legacy_plaintext_is_restricted_loaded_and_immediately_migrated()
    {
        using StoreFixture fixture = new();
        InstallationGrantDto grant = CreateGrant(SecretMarker);
        File.WriteAllText(
            fixture.StorePath,
            JsonSerializer.Serialize(
                new
                {
                    receipts = Array.Empty<object>(),
                    claimTickets = Array.Empty<object>(),
                    browserCallbacks = Array.Empty<object>(),
                    installations = Array.Empty<object>(),
                    grants = new[] { grant },
                    personalizedInstallScripts = Array.Empty<object>()
                },
                new JsonSerializerOptions(JsonSerializerDefaults.Web)));
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(
                fixture.StorePath,
                UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.GroupRead | UnixFileMode.OtherRead);
        }

        using InstallLinkingStore migrated = fixture.CreateStore(fixture.CreateProvider("migration-keys"));

        Assert.Equal(SecretMarker, Assert.Single(migrated.GrantsById.Values).AccessToken);
        string migratedText = File.ReadAllText(fixture.StorePath);
        Assert.Contains("\"format\": \"chummer.install-linking-store\"", migratedText, StringComparison.Ordinal);
        Assert.DoesNotContain(SecretMarker, migratedText, StringComparison.Ordinal);
        Assert.Empty(Directory.GetFiles(fixture.Root, ".install-linking-store.json.tmp-*"));
        if (!OperatingSystem.IsWindows())
        {
            Assert.Equal(OwnerDirectoryMode, File.GetUnixFileMode(fixture.Root));
            Assert.Equal(OwnerFileMode, File.GetUnixFileMode(fixture.StorePath));
        }
    }

    [Fact]
    public void Wrong_key_fails_closed_preserves_source_and_writes_owner_only_quarantine()
    {
        using StoreFixture fixture = new();
        using InstallLinkingStore first = fixture.CreateStore(fixture.CreateProvider("first-keys"));
        InstallationGrantDto grant = CreateGrant(SecretMarker);
        lock (first.Gate)
        {
            first.GrantsById[grant.GrantId] = grant;
            first.PersistLocked();
        }

        string protectedSource = File.ReadAllText(fixture.StorePath);
        first.Dispose();
        CapturingLogger logger = new();
        InvalidOperationException failure = Assert.Throws<InvalidOperationException>(() =>
            fixture.CreateStore(fixture.CreateProvider("wrong-keys"), logger));

        Assert.Equal(FailClosedMessage, failure.Message);
        Assert.Equal(protectedSource, File.ReadAllText(fixture.StorePath));
        string quarantine = Assert.Single(Directory.GetFiles(fixture.Root, ".install-linking-store.json.quarantine-*.json"));
        string quarantineText = File.ReadAllText(quarantine);
        Assert.Contains("chummer.install-linking-store.quarantine-metadata", quarantineText, StringComparison.Ordinal);
        Assert.DoesNotContain(protectedSource, quarantineText, StringComparison.Ordinal);
        Assert.DoesNotContain("protectedPayload", quarantineText, StringComparison.Ordinal);
        Assert.DoesNotContain(SecretMarker, string.Join("\n", logger.Messages), StringComparison.Ordinal);
        Assert.Empty(Directory.GetFiles(fixture.Root, ".install-linking-store.json.tmp-*"));
        if (!OperatingSystem.IsWindows())
        {
            Assert.Equal(OwnerFileMode, File.GetUnixFileMode(quarantine));
            Assert.Equal(OwnerFileMode, File.GetUnixFileMode(fixture.StorePath));
        }
    }

    [Fact]
    public void Corrupt_envelope_fails_closed_with_fixed_secret_safe_error()
    {
        using StoreFixture fixture = new();
        const string corruptMarker = "corrupt-payload-marker-must-not-be-logged";
        string corruptEnvelope = $$"""
            {
              "format": "chummer.install-linking-store",
              "version": 1,
              "protectedPayload": "not-a-protected-payload",
              "debugGrantToken": "{{corruptMarker}}"
            }
            """;
        File.WriteAllText(fixture.StorePath, corruptEnvelope);
        CapturingLogger logger = new();

        InvalidOperationException failure = Assert.Throws<InvalidOperationException>(() =>
            fixture.CreateStore(fixture.CreateProvider("corrupt-keys"), logger));

        Assert.Equal(FailClosedMessage, failure.Message);
        string scrubbed = File.ReadAllText(fixture.StorePath);
        Assert.NotEqual(corruptEnvelope, scrubbed);
        Assert.Contains("chummer.install-linking-store.failure", scrubbed, StringComparison.Ordinal);
        Assert.DoesNotContain(corruptMarker, scrubbed, StringComparison.Ordinal);
        Assert.Single(Directory.GetFiles(fixture.Root, ".install-linking-store.json.quarantine-*"));
        Assert.DoesNotContain(corruptMarker, string.Join("\n", logger.Messages), StringComparison.Ordinal);
        Assert.All(logger.Messages, static message => Assert.DoesNotContain("protectedPayload", message, StringComparison.Ordinal));
    }

    [Fact]
    public void Legacy_plaintext_cannot_be_reintroduced_after_the_migration_floor_exists()
    {
        using StoreFixture fixture = new();
        string legacy = JsonSerializer.Serialize(
            new
            {
                receipts = Array.Empty<object>(),
                claimTickets = Array.Empty<object>(),
                browserCallbacks = Array.Empty<object>(),
                installations = Array.Empty<object>(),
                grants = new[] { CreateGrant(SecretMarker) },
                personalizedInstallScripts = Array.Empty<object>()
            },
            new JsonSerializerOptions(JsonSerializerDefaults.Web));
        File.WriteAllText(fixture.StorePath, legacy);
        IDataProtectionProvider provider = fixture.CreateProvider("floor-keys");
        using (InstallLinkingStore migrated = fixture.CreateStore(provider))
        {
            Assert.Single(migrated.GrantsById);
        }

        File.WriteAllText(fixture.StorePath, legacy);
        InvalidOperationException failure = Assert.Throws<InvalidOperationException>(() => fixture.CreateStore(provider));

        Assert.Equal(FailClosedMessage, failure.Message);
        Assert.DoesNotContain(SecretMarker, File.ReadAllText(fixture.StorePath), StringComparison.Ordinal);
    }

    [Fact]
    public void Older_envelope_is_rejected_when_the_local_floor_has_advanced()
    {
        using StoreFixture fixture = new();
        IDataProtectionProvider provider = fixture.CreateProvider("rollback-keys");
        using InstallLinkingStore store = fixture.CreateStore(provider);
        lock (store.Gate)
        {
            store.GrantsById["grant-one"] = CreateGrant("token-one") with { GrantId = "grant-one" };
            store.PersistLocked();
        }

        byte[] generationOne = File.ReadAllBytes(fixture.StorePath);
        lock (store.Gate)
        {
            store.GrantsById["grant-two"] = CreateGrant("token-two") with { GrantId = "grant-two" };
            store.PersistLocked();
        }

        store.Dispose();
        File.WriteAllBytes(fixture.StorePath, generationOne);
        InvalidOperationException failure = Assert.Throws<InvalidOperationException>(() => fixture.CreateStore(provider));
        Assert.Equal(FailClosedMessage, failure.Message);
    }

    [Fact]
    public void Null_floor_digest_uses_fixed_fail_closed_error_and_metadata_only_quarantine()
    {
        using StoreFixture fixture = new();
        IDataProtectionProvider provider = fixture.CreateProvider("null-floor-keys");
        using (InstallLinkingStore store = fixture.CreateStore(provider))
        {
            lock (store.Gate)
            {
                store.GrantsById["grant-one"] = CreateGrant("token-one") with { GrantId = "grant-one" };
                store.PersistLocked();
            }
        }

        IDataProtector floorProtector = provider.CreateProtector("Chummer.Run.Api.InstallLinkingStore.floor.v1");
        byte[] invalidPayload = JsonSerializer.SerializeToUtf8Bytes(
            new
            {
                minimumEnvelopeVersion = 2,
                generation = 1,
                snapshotSha256 = (string?)null
            });
        string protectedPayload = floorProtector.Protect(Convert.ToBase64String(invalidPayload));
        string floorPath = $"{fixture.StorePath}.floor";
        File.WriteAllText(
            floorPath,
            JsonSerializer.Serialize(new
            {
                format = "chummer.install-linking-store.floor",
                version = 1,
                protectedPayload
            }));
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(floorPath, OwnerFileMode);
        }

        InvalidOperationException failure = Assert.Throws<InvalidOperationException>(() =>
            fixture.CreateStore(provider));

        Assert.Equal(FailClosedMessage, failure.Message);
        string quarantine = Assert.Single(
            Directory.GetFiles(fixture.Root, ".install-linking-store.json.quarantine-*.json"));
        Assert.Contains("quarantine-metadata", File.ReadAllText(quarantine), StringComparison.Ordinal);
    }

    [Fact]
    public void Writer_lease_rejects_a_second_live_store_instance()
    {
        if (!OperatingSystem.IsLinux())
        {
            return;
        }

        using StoreFixture fixture = new();
        IDataProtectionProvider provider = fixture.CreateProvider("lease-keys");
        using InstallLinkingStore first = fixture.CreateStore(provider);

        IOException failure = Assert.Throws<IOException>(() => fixture.CreateStore(provider));

        Assert.Equal("Install-linking writer lease is already held.", failure.Message);
    }

    [Fact]
    public void Startup_prunes_all_hostile_preexisting_quarantine_receipts_to_global_caps()
    {
        using StoreFixture fixture = new();
        for (int index = 0; index < 64; index++)
        {
            string path = Path.Combine(
                fixture.Root,
                $".install-linking-store.json.quarantine-hostile-{index:D3}.json");
            File.WriteAllBytes(path, new byte[1024]);
            File.SetLastWriteTimeUtc(path, DateTime.UtcNow.AddMinutes(-index));
        }

        using InstallLinkingStore store = fixture.CreateStore(fixture.CreateProvider("quarantine-cap-keys"));

        FileInfo[] retained = new DirectoryInfo(fixture.Root)
            .EnumerateFiles(".install-linking-store.json.quarantine-*.json", SearchOption.TopDirectoryOnly)
            .ToArray();
        Assert.True(store.IsHealthy);
        Assert.True(retained.Length <= 8);
        Assert.True(retained.Sum(static file => file.Length) <= 64 * 1024);
    }

    [Fact]
    public void Failure_receipt_reserves_its_exact_bytes_at_the_existing_global_byte_boundary()
    {
        using StoreFixture fixture = new();
        using (InstallLinkingStore first = fixture.CreateStore(fixture.CreateProvider("quarantine-source-keys")))
        {
            lock (first.Gate)
            {
                first.GrantsById["grant-quarantine-boundary"] = CreateGrant("boundary-secret") with
                {
                    GrantId = "grant-quarantine-boundary"
                };
                first.PersistLocked();
            }
        }

        for (int index = 0; index < 7; index++)
        {
            int length = index == 6 ? 16 * 1024 : 8 * 1024;
            string path = Path.Combine(
                fixture.Root,
                $".install-linking-store.json.quarantine-boundary-{index:D3}.json");
            File.WriteAllBytes(path, new byte[length]);
            File.SetLastWriteTimeUtc(path, DateTime.UtcNow.AddMinutes(-index));
        }

        InvalidOperationException failure = Assert.Throws<InvalidOperationException>(() =>
            fixture.CreateStore(fixture.CreateProvider("quarantine-wrong-keys")));

        Assert.Equal(FailClosedMessage, failure.Message);
        FileInfo[] retained = new DirectoryInfo(fixture.Root)
            .EnumerateFiles(".install-linking-store.json.quarantine-*.json", SearchOption.TopDirectoryOnly)
            .ToArray();
        Assert.True(retained.Length <= 8);
        Assert.True(retained.Sum(static file => file.Length) <= 64 * 1024);
        Assert.Contains(
            retained,
            static file => file.Name.StartsWith(
                ".install-linking-store.json.quarantine-validation_failed-",
                StringComparison.Ordinal));
    }

    [Fact]
    public void Failed_persist_restores_the_last_durable_in_memory_snapshot()
    {
        using StoreFixture fixture = new();
        using InstallLinkingStore store = fixture.CreateStore(fixture.CreateProvider("transaction-keys"));
        InstallationGrantDto committed = CreateGrant("committed-token");
        lock (store.Gate)
        {
            store.GrantsById[committed.GrantId] = committed;
            store.PersistLocked();
            store.GrantsById["invalid-grant"] = committed with
            {
                GrantId = "invalid-grant",
                AccessToken = string.Empty
            };

            Assert.Throws<InvalidDataException>(() => store.PersistLocked());
            Assert.Single(store.GrantsById);
            Assert.Equal("committed-token", store.GrantsById[committed.GrantId].AccessToken);
        }
    }

    [Fact]
    public void Store_rejects_a_symbolic_link_target()
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        using StoreFixture fixture = new(createStoreFile: false);
        string target = Path.Combine(fixture.Root, "link-target.json");
        File.WriteAllText(target, "{}");
        File.CreateSymbolicLink(fixture.StorePath, target);

        InvalidOperationException failure = Assert.ThrowsAny<InvalidOperationException>(() =>
            fixture.CreateStore(fixture.CreateProvider("link-keys")));

        Assert.Equal("Install-linking durable state path cannot contain links.", failure.Message);
    }

    private static InstallationGrantDto CreateGrant(string accessToken)
    {
        DateTimeOffset issuedAt = DateTimeOffset.UtcNow;
        return new InstallationGrantDto(
            GrantId: "grant-security-test",
            InstallationId: "installation-security-test",
            Status: InstallationGrantStates.Active,
            AccessToken: accessToken,
            IssuedAtUtc: issuedAt,
            ExpiresAtUtc: issuedAt.AddHours(8),
            UserId: "user-security-test",
            SubjectId: "subject-security-test");
    }

    private sealed class StoreFixture : IDisposable
    {
        public StoreFixture(bool createStoreFile = false)
        {
            Root = Path.Combine(Path.GetTempPath(), "chummer-install-linking-security", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(Root);
            StorePath = Path.Combine(Root, "install-linking-store.json");
            if (createStoreFile)
            {
                File.WriteAllText(StorePath, "{}");
            }

            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = StorePath
                })
                .Build();
        }

        public string Root { get; }
        public string StorePath { get; }
        public IConfiguration Configuration { get; }

        public IDataProtectionProvider CreateProvider(string directoryName)
            => DataProtectionProvider.Create(new DirectoryInfo(Path.Combine(Root, directoryName)));

        public InstallLinkingStore CreateStore(
            IDataProtectionProvider provider,
            ILogger<InstallLinkingStore>? logger = null)
            => new(Configuration, provider, logger ?? NullLogger<InstallLinkingStore>.Instance);

        public void Dispose()
        {
            if (Directory.Exists(Root))
            {
                Directory.Delete(Root, recursive: true);
            }
        }
    }

    private sealed class CapturingLogger : ILogger<InstallLinkingStore>
    {
        public List<string> Messages { get; } = [];

        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => NoopScope.Instance;

        public bool IsEnabled(LogLevel logLevel) => true;

        public void Log<TState>(
            LogLevel logLevel,
            EventId eventId,
            TState state,
            Exception? exception,
            Func<TState, Exception?, string> formatter)
            => Messages.Add(formatter(state, exception));

        private sealed class NoopScope : IDisposable
        {
            public static NoopScope Instance { get; } = new();
            public void Dispose()
            {
            }
        }
    }
}
