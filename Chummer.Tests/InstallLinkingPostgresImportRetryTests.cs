using System.Security.Cryptography;
using System.Text.Json;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking.Postgres;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class InstallLinkingPostgresImportRetryTests
{
    [Fact]
    public async Task Failed_readiness_never_opens_or_reads_the_local_source()
    {
        using var fixture = new ImportFixture();
        fixture.WriteExpiredLegacySnapshot();
        byte[] before = File.ReadAllBytes(fixture.StorePath);
        using var authority = new FakeSnapshotAuthority { Ready = false };
        bool opened = false;
        var coordinator = new InstallLinkingPostgresImportCoordinator(
            authority,
            () =>
            {
                opened = true;
                return fixture.OpenSession();
            });

        InstallLinkingPostgresImportResult result = await coordinator.ExecuteAsync();

        Assert.Equal(
            InstallLinkingPostgresImportDisposition.AuthorityUnavailable,
            result.Disposition);
        Assert.False(opened);
        Assert.Equal(0, authority.ReadCount);
        Assert.Equal(before, File.ReadAllBytes(fixture.StorePath));
        Assert.False(File.Exists(fixture.FloorPath));
        Assert.False(File.Exists(fixture.IntentPath));
    }

    [Fact]
    public async Task Readiness_and_head_are_checked_before_the_local_session_can_touch_disk()
    {
        using var fixture = new ImportFixture();
        fixture.WriteExpiredLegacySnapshot();
        byte[] before = File.ReadAllBytes(fixture.StorePath);
        using var authority = new FakeSnapshotAuthority();
        authority.SeedNonMatching(generation: 2);
        bool opened = false;
        var coordinator = new InstallLinkingPostgresImportCoordinator(
            authority,
            () =>
            {
                opened = true;
                return fixture.OpenSession();
            });

        InstallLinkingPostgresImportResult result = await coordinator.ExecuteAsync();

        Assert.Equal(
            InstallLinkingPostgresImportDisposition.RefusedNonEmpty,
            result.Disposition);
        Assert.False(opened);
        Assert.Equal(before, File.ReadAllBytes(fixture.StorePath));
        Assert.False(File.Exists(fixture.FloorPath));
        Assert.False(File.Exists(fixture.IntentPath));
    }

    [Fact]
    public async Task Nonmatching_generation_one_authority_leaves_store_and_floor_byte_exact()
    {
        using var fixture = new ImportFixture();
        fixture.WriteProtectedStoreAndFloor();
        byte[] storeBefore = File.ReadAllBytes(fixture.StorePath);
        byte[] floorBefore = File.ReadAllBytes(fixture.FloorPath);
        using var authority = new FakeSnapshotAuthority();
        authority.SeedNonMatching(generation: 1);
        var coordinator = fixture.CreateCoordinator(authority);

        InstallLinkingPostgresImportResult result = await coordinator.ExecuteAsync();

        Assert.Equal(
            InstallLinkingPostgresImportDisposition.RefusedNonEmpty,
            result.Disposition);
        Assert.Equal(storeBefore, File.ReadAllBytes(fixture.StorePath));
        Assert.Equal(floorBefore, File.ReadAllBytes(fixture.FloorPath));
        Assert.False(File.Exists(fixture.IntentPath));
        Assert.Equal(0, authority.CompareCount);
    }

    [Fact]
    public async Task Prepared_retry_reuses_the_exact_fsynced_intent_before_committing()
    {
        using var fixture = new ImportFixture();
        fixture.WriteExpiredLegacySnapshot();
        byte[] sourceBefore = File.ReadAllBytes(fixture.StorePath);
        using var authority = new FakeSnapshotAuthority
        {
            CommitCompareExchange = false
        };

        InstallLinkingPostgresImportResult first =
            await fixture.CreateCoordinator(authority).ExecuteAsync();

        Assert.Equal(
            InstallLinkingPostgresImportDisposition.PreparedNotCommitted,
            first.Disposition);
        Assert.Equal(sourceBefore, File.ReadAllBytes(fixture.StorePath));
        Assert.False(File.Exists(fixture.FloorPath));
        Assert.True(File.Exists(fixture.IntentPath));
        AssertOwnerOnly(fixture.IntentPath);
        byte[] intentBefore = File.ReadAllBytes(fixture.IntentPath);

        authority.CommitCompareExchange = true;
        InstallLinkingPostgresImportResult second =
            await fixture.CreateCoordinator(authority).ExecuteAsync();

        Assert.Equal(InstallLinkingPostgresImportDisposition.Imported, second.Disposition);
        Assert.Equal(2, authority.CompareCount);
        AssertRequestsEqual(authority.Requests[0], authority.Requests[1]);
        Assert.False(File.Exists(fixture.IntentPath));
        Assert.True(File.Exists(fixture.FloorPath));
        using InstallLinkingAuthoritativeEnvelope committed = authority.CloneCurrent();
        Assert.Equal(1, committed.Generation);
        Assert.Equal(committed.ProtectedEnvelope, File.ReadAllBytes(fixture.StorePath));

        CryptographicOperations.ZeroMemory(sourceBefore);
        CryptographicOperations.ZeroMemory(intentBefore);
    }

    [Fact]
    public async Task Commit_then_mirror_failure_reconciles_the_exact_generation_one_intent()
    {
        using var fixture = new ImportFixture();
        fixture.WriteExpiredLegacySnapshot();
        using var authority = new FakeSnapshotAuthority();
        int failOnce = 1;
        var firstCoordinator = fixture.CreateCoordinator(
            authority,
            stage =>
            {
                if (stage == InstallLinkingImportMirrorStage.AfterStoreWrite
                    && Interlocked.Exchange(ref failOnce, 0) == 1)
                {
                    throw new IOException("injected mirror failure");
                }
            });

        InstallLinkingPostgresImportResult first = await firstCoordinator.ExecuteAsync();

        Assert.Equal(
            InstallLinkingPostgresImportDisposition.CommittedPendingMirror,
            first.Disposition);
        Assert.Equal(1, authority.CompareCount);
        Assert.True(File.Exists(fixture.IntentPath));
        Assert.False(File.Exists(fixture.FloorPath));
        using JsonDocument pendingIntent = JsonDocument.Parse(
            File.ReadAllBytes(fixture.IntentPath));
        Assert.Equal(
            "committed_pending_mirror",
            pendingIntent.RootElement.GetProperty("state").GetString());
        Guid intendedCommit = pendingIntent.RootElement
            .GetProperty("commitId")
            .GetGuid();
        string intendedEnvelopeDigest = pendingIntent.RootElement
            .GetProperty("envelopeSha256")
            .GetString()!;

        InstallLinkingPostgresImportResult second =
            await fixture.CreateCoordinator(authority).ExecuteAsync();

        Assert.Equal(
            InstallLinkingPostgresImportDisposition.Reconciled,
            second.Disposition);
        Assert.Equal(1, authority.CompareCount);
        Assert.False(File.Exists(fixture.IntentPath));
        Assert.True(File.Exists(fixture.FloorPath));
        using InstallLinkingAuthoritativeEnvelope committed = authority.CloneCurrent();
        Assert.Equal(1, committed.Generation);
        Assert.Equal(intendedCommit, committed.CommitId);
        Assert.Equal(
            intendedEnvelopeDigest,
            Convert.ToBase64String(committed.EnvelopeSha256!));
        Assert.Equal(committed.ProtectedEnvelope, File.ReadAllBytes(fixture.StorePath));

        using JsonDocument localEnvelope = JsonDocument.Parse(
            File.ReadAllBytes(fixture.StorePath));
        Assert.Equal(1, localEnvelope.RootElement.GetProperty("generation").GetInt64());
        InstallationGrantDto retainedGrant = Assert.Single(
            fixture.ReadMirroredSnapshot().Grants);
        Assert.Equal(InstallationGrantStates.Expired, retainedGrant.Status);
        Assert.Empty(retainedGrant.AccessToken);
    }

    private static void AssertRequestsEqual(
        CapturedRequest expected,
        CapturedRequest actual)
    {
        Assert.Equal(expected.ExpectedGeneration, actual.ExpectedGeneration);
        Assert.Equal(expected.ExpectedCommitId, actual.ExpectedCommitId);
        Assert.Equal(expected.NextGeneration, actual.NextGeneration);
        Assert.Equal(expected.CommitId, actual.CommitId);
        Assert.Equal(expected.EnvelopeVersion, actual.EnvelopeVersion);
        Assert.Equal(expected.ExpectedEnvelopeSha256, actual.ExpectedEnvelopeSha256);
        Assert.Equal(expected.SnapshotSha256, actual.SnapshotSha256);
        Assert.Equal(expected.EnvelopeSha256, actual.EnvelopeSha256);
        Assert.Equal(expected.ProtectedEnvelope, actual.ProtectedEnvelope);
    }

    private static void AssertOwnerOnly(string path)
    {
        if (!OperatingSystem.IsWindows())
        {
            UnixFileMode mode = File.GetUnixFileMode(path);
            Assert.Equal(
                UnixFileMode.UserRead | UnixFileMode.UserWrite,
                mode & (UnixFileMode.UserRead
                        | UnixFileMode.UserWrite
                        | UnixFileMode.UserExecute
                        | UnixFileMode.GroupRead
                        | UnixFileMode.GroupWrite
                        | UnixFileMode.GroupExecute
                        | UnixFileMode.OtherRead
                        | UnixFileMode.OtherWrite
                        | UnixFileMode.OtherExecute));
        }
    }

    private sealed class ImportFixture : IDisposable
    {
        private readonly IDataProtectionProvider _provider;
        private readonly TestHostEnvironment _environment;

        public ImportFixture()
        {
            Root = Path.Combine(
                Path.GetTempPath(),
                "install-linking-postgres-import-tests",
                Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(Root);
            StorePath = Path.Combine(Root, "install-linking-store.json");
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = StorePath,
                    ["ASPNETCORE_ENVIRONMENT"] = Environments.Development
                })
                .Build();
            _provider = DataProtectionProvider.Create(
                new DirectoryInfo(Path.Combine(Root, "keys")));
            _environment = new TestHostEnvironment
            {
                ContentRootPath = Root
            };
        }

        public string Root { get; }
        public string StorePath { get; }
        public string FloorPath => $"{StorePath}.floor";
        public string IntentPath => $"{StorePath}.postgres-import.intent";
        public IConfiguration Configuration { get; }

        public void WriteExpiredLegacySnapshot()
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            var snapshot = new InstallLinkingStoreSnapshot(
                Receipts: [],
                ClaimTickets: [],
                BrowserCallbacks: [],
                Installations: [],
                Grants:
                [
                    new InstallationGrantDto(
                        GrantId: "expired-import-grant",
                        InstallationId: "expired-import-installation",
                        Status: InstallationGrantStates.Active,
                        AccessToken: "must-be-redacted-by-retention",
                        IssuedAtUtc: now.AddHours(-2),
                        ExpiresAtUtc: now.AddHours(-1),
                        UserId: "import-user",
                        SubjectId: "import-subject")
                ],
                PersonalizedInstallScripts: []);
            byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(
                snapshot,
                new JsonSerializerOptions(JsonSerializerDefaults.Web)
                {
                    WriteIndented = true
                });
            try
            {
                File.WriteAllBytes(StorePath, bytes);
                TightenMode(StorePath);
            }
            finally
            {
                CryptographicOperations.ZeroMemory(bytes);
            }
        }

        public void WriteProtectedStoreAndFloor()
        {
            using var store = new InstallLinkingStore(
                Configuration,
                _provider,
                NullLogger<InstallLinkingStore>.Instance);
            DateTimeOffset now = DateTimeOffset.UtcNow;
            lock (store.Gate)
            {
                store.GrantsById["protected-local-grant"] =
                    new InstallationGrantDto(
                        GrantId: "protected-local-grant",
                        InstallationId: "protected-local-installation",
                        Status: InstallationGrantStates.Active,
                        AccessToken: "protected-local-token",
                        IssuedAtUtc: now,
                        ExpiresAtUtc: now.AddHours(4),
                        UserId: "protected-user",
                        SubjectId: "protected-subject");
                store.PersistLocked();
            }
        }

        public InstallLinkingStoreSnapshot ReadMirroredSnapshot()
        {
            byte[] envelopeBytes = File.ReadAllBytes(StorePath);
            byte[]? snapshotBytes = null;
            try
            {
                using JsonDocument document = JsonDocument.Parse(envelopeBytes);
                ProtectedEnvelopeDescriptor descriptor =
                    InstallLinkingStore.ReadStrictProtectedPayload(
                        document.RootElement);
                IDataProtector protector = _provider.CreateProtector(
                    InstallLinkingStore.DataProtectionPurpose);
                snapshotBytes = Convert.FromBase64String(
                    protector.Unprotect(descriptor.ProtectedPayload));
                return InstallLinkingStore.DeserializeImportSnapshot(
                    snapshotBytes,
                    new JsonSerializerOptions(JsonSerializerDefaults.Web));
            }
            finally
            {
                CryptographicOperations.ZeroMemory(envelopeBytes);
                if (snapshotBytes is not null)
                {
                    CryptographicOperations.ZeroMemory(snapshotBytes);
                }
            }
        }

        public InstallLinkingOneShotImportSession OpenSession(
            Action<InstallLinkingImportMirrorStage>? observer = null)
            => InstallLinkingOneShotImportSession.Open(
                Configuration,
                _provider,
                _environment,
                mirrorObserver: observer);

        public InstallLinkingPostgresImportCoordinator CreateCoordinator(
            IInstallLinkingSnapshotAuthority authority,
            Action<InstallLinkingImportMirrorStage>? observer = null)
            => new(authority, () => OpenSession(observer));

        public void Dispose()
        {
            (_provider as IDisposable)?.Dispose();
            if (Directory.Exists(Root))
            {
                Directory.Delete(Root, recursive: true);
            }
        }

        private static void TightenMode(string path)
        {
            if (!OperatingSystem.IsWindows())
            {
                File.SetUnixFileMode(
                    path,
                    UnixFileMode.UserRead | UnixFileMode.UserWrite);
            }
        }
    }

    private sealed class TestHostEnvironment : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = Environments.Development;
        public string ApplicationName { get; set; } = "Chummer.Tests";
        public string ContentRootPath { get; set; } = string.Empty;
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }

    private sealed class FakeSnapshotAuthority :
        IInstallLinkingSnapshotAuthority,
        IDisposable
    {
        private readonly object _gate = new();
        private InstallLinkingAuthoritativeEnvelope _current = Empty();

        public bool Ready { get; set; } = true;
        public bool CommitCompareExchange { get; set; } = true;
        public int CompareCount { get; private set; }
        public int ReadCount { get; private set; }
        public List<CapturedRequest> Requests { get; } = [];

        public Task<InstallLinkingPostgresReadiness> CheckReadinessAsync(
            CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            lock (_gate)
            {
                return Task.FromResult(new InstallLinkingPostgresReadiness(
                    Ready,
                    Ready
                        ? _current.IsEmpty ? "empty_authority_ready" : "ready"
                        : "injected_not_ready",
                    InstallLinkingPostgresSchema.CurrentVersion,
                    InstallLinkingPostgresSchema.CurrentVersion,
                    _current.Generation,
                    DateTimeOffset.UtcNow));
            }
        }

        public Task<InstallLinkingAuthoritativeEnvelope> ReadCurrentAsync(
            CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            lock (_gate)
            {
                ReadCount++;
                return Task.FromResult(_current.Clone());
            }
        }

        public Task<InstallLinkingEnvelopeCompareExchangeResult> CompareExchangeAsync(
            InstallLinkingEnvelopeCompareExchangeRequest request,
            CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            lock (_gate)
            {
                CompareCount++;
                Requests.Add(CapturedRequest.From(request));
                if (!CommitCompareExchange)
                {
                    return Task.FromResult(
                        new InstallLinkingEnvelopeCompareExchangeResult(
                            InstallLinkingEnvelopeCommitDisposition.Unavailable,
                            null,
                            "injected_unavailable"));
                }

                _current.Dispose();
                _current = new InstallLinkingAuthoritativeEnvelope(
                    request.NextGeneration,
                    request.CommitId,
                    request.EnvelopeVersion,
                    request.SnapshotSha256.ToArray(),
                    request.EnvelopeSha256.ToArray(),
                    request.ProtectedEnvelope.ToArray(),
                    DateTimeOffset.UtcNow);
                return Task.FromResult(
                    new InstallLinkingEnvelopeCompareExchangeResult(
                        InstallLinkingEnvelopeCommitDisposition.Applied,
                        _current.Clone(),
                        "committed"));
            }
        }

        public InstallLinkingAuthoritativeEnvelope CloneCurrent()
        {
            lock (_gate)
            {
                return _current.Clone();
            }
        }

        public void SeedNonMatching(long generation)
        {
            byte[] envelope = "nonmatching-authority-envelope"u8.ToArray();
            byte[] snapshot = "nonmatching-authority-snapshot"u8.ToArray();
            try
            {
                lock (_gate)
                {
                    _current.Dispose();
                    _current = new InstallLinkingAuthoritativeEnvelope(
                        generation,
                        Guid.NewGuid(),
                        InstallLinkingStore.EnvelopeVersion,
                        SHA256.HashData(snapshot),
                        SHA256.HashData(envelope),
                        envelope.ToArray(),
                        DateTimeOffset.UtcNow);
                }
            }
            finally
            {
                CryptographicOperations.ZeroMemory(envelope);
                CryptographicOperations.ZeroMemory(snapshot);
            }
        }

        public void Dispose()
        {
            lock (_gate)
            {
                _current.Dispose();
                _current = Empty();
                foreach (CapturedRequest request in Requests)
                {
                    request.Dispose();
                }

                Requests.Clear();
            }
        }

        private static InstallLinkingAuthoritativeEnvelope Empty()
            => new(0, null, null, null, null, null, DateTimeOffset.UnixEpoch);
    }

    private sealed record CapturedRequest(
        long ExpectedGeneration,
        Guid? ExpectedCommitId,
        byte[]? ExpectedEnvelopeSha256,
        long NextGeneration,
        Guid CommitId,
        int EnvelopeVersion,
        byte[] SnapshotSha256,
        byte[] EnvelopeSha256,
        byte[] ProtectedEnvelope) : IDisposable
    {
        public static CapturedRequest From(
            InstallLinkingEnvelopeCompareExchangeRequest request)
            => new(
                request.ExpectedGeneration,
                request.ExpectedCommitId,
                request.ExpectedEnvelopeSha256?.ToArray(),
                request.NextGeneration,
                request.CommitId,
                request.EnvelopeVersion,
                request.SnapshotSha256.ToArray(),
                request.EnvelopeSha256.ToArray(),
                request.ProtectedEnvelope.ToArray());

        public void Dispose()
        {
            if (ExpectedEnvelopeSha256 is not null)
            {
                CryptographicOperations.ZeroMemory(ExpectedEnvelopeSha256);
            }

            CryptographicOperations.ZeroMemory(SnapshotSha256);
            CryptographicOperations.ZeroMemory(EnvelopeSha256);
            CryptographicOperations.ZeroMemory(ProtectedEnvelope);
        }
    }
}
