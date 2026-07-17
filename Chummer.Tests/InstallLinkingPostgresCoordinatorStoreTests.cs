using System.Security.Cryptography;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking.Postgres;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class InstallLinkingPostgresCoordinatorStoreTests
{
    [Fact]
    public void Readiness_requires_an_exact_head_that_was_bound_after_local_mirroring()
    {
        using var authority = new FakeSnapshotAuthority();
        var coordinator = new InstallLinkingPostgresAuthorityCoordinator(authority);

        Assert.Equal(
            new InstallLinkingRollbackAuthorityReadiness(
                false,
                "postgres_authority_not_bound"),
            coordinator.Evaluate());

        using InstallLinkingAuthoritativeEnvelope empty = authority.CloneCurrent();
        coordinator.BindValidatedLocalMirror(empty);
        Assert.Equal(
            new InstallLinkingRollbackAuthorityReadiness(
                true,
                "postgres_authority_bound"),
            coordinator.Evaluate());

        InstallLinkingEnvelopeCompareExchangeRequest request = RequestForEmptyHead();
        authority.SetCurrent(request);
        Assert.Equal(
            new InstallLinkingRollbackAuthorityReadiness(
                false,
                "postgres_authority_head_mismatch"),
            coordinator.Evaluate());
        ClearRequest(request);
    }

    [Fact]
    public void Authority_backed_store_CASes_then_repairs_a_missing_local_mirror_from_Postgres()
    {
        using var fixture = new StoreFixture();
        using var authority = new FakeSnapshotAuthority();
        var coordinator = new InstallLinkingPostgresAuthorityCoordinator(authority);
        using (InstallLinkingStore store = fixture.CreateAuthorityStore(coordinator))
        {
            InstallationGrantDto grant = CreateGrant("postgres-authority-token");
            lock (store.Gate)
            {
                store.GrantsById[grant.GrantId] = grant;
                store.PersistLocked();
            }

            Assert.True(store.IsHealthy);
            Assert.Equal(1, authority.CloneCurrent().Generation);
            Assert.True(coordinator.Evaluate().Ready);
        }

        byte[] exactAuthorityBytes;
        using (InstallLinkingAuthoritativeEnvelope committed = authority.CloneCurrent())
        {
            exactAuthorityBytes = committed.ProtectedEnvelope!.ToArray();
        }

        File.Delete(fixture.StorePath);
        File.Delete($"{fixture.StorePath}.floor");
        var restartedCoordinator =
            new InstallLinkingPostgresAuthorityCoordinator(authority);
        using InstallLinkingStore restarted =
            fixture.CreateAuthorityStore(restartedCoordinator);

        Assert.Equal(
            "postgres-authority-token",
            Assert.Single(restarted.GrantsById.Values).AccessToken);
        Assert.Equal(exactAuthorityBytes, File.ReadAllBytes(fixture.StorePath));
        Assert.True(restartedCoordinator.Evaluate().Ready);
    }

    [Fact]
    public void Authority_backed_store_zeroes_every_request_buffer_after_each_persist()
    {
        using var fixture = new StoreFixture();
        using var authority = new FakeSnapshotAuthority();
        var coordinator = new InstallLinkingPostgresAuthorityCoordinator(authority);
        using InstallLinkingStore store = fixture.CreateAuthorityStore(coordinator);

        lock (store.Gate)
        {
            store.GrantsById["grant-generation-one"] =
                CreateGrant("token-generation-one") with
                {
                    GrantId = "grant-generation-one",
                    InstallationId = "installation-generation-one"
                };
            store.PersistLocked();
        }

        InstallLinkingEnvelopeCompareExchangeRequest first =
            Assert.Single(authority.ObservedRequests);
        Assert.Null(first.ExpectedEnvelopeSha256);
        AssertZeroed(first.SnapshotSha256);
        AssertZeroed(first.EnvelopeSha256);
        AssertZeroed(first.ProtectedEnvelope);
        using (InstallLinkingAuthoritativeEnvelope committed = authority.CloneCurrent())
        {
            Assert.Equal(1, committed.Generation);
            Assert.Contains(committed.SnapshotSha256!, static value => value != 0);
            Assert.Contains(committed.EnvelopeSha256!, static value => value != 0);
            Assert.Contains(committed.ProtectedEnvelope!, static value => value != 0);
        }

        lock (store.Gate)
        {
            store.GrantsById["grant-generation-two"] =
                CreateGrant("token-generation-two") with
                {
                    GrantId = "grant-generation-two",
                    InstallationId = "installation-generation-two"
                };
            store.PersistLocked();
        }

        Assert.Equal(2, authority.ObservedRequests.Count);
        InstallLinkingEnvelopeCompareExchangeRequest second =
            authority.ObservedRequests[1];
        Assert.NotNull(second.ExpectedEnvelopeSha256);
        AssertZeroed(second.ExpectedEnvelopeSha256);
        AssertZeroed(second.SnapshotSha256);
        AssertZeroed(second.EnvelopeSha256);
        AssertZeroed(second.ProtectedEnvelope);
        using InstallLinkingAuthoritativeEnvelope generationTwo =
            authority.CloneCurrent();
        Assert.Equal(2, generationTwo.Generation);
        Assert.Contains(generationTwo.SnapshotSha256!, static value => value != 0);
        Assert.Contains(generationTwo.EnvelopeSha256!, static value => value != 0);
        Assert.Contains(generationTwo.ProtectedEnvelope!, static value => value != 0);
    }

    [Fact]
    public void Authority_conflict_restores_memory_and_terminalizes_the_store()
    {
        using var fixture = new StoreFixture();
        using var authority = new FakeSnapshotAuthority { ForceConflict = true };
        var coordinator = new InstallLinkingPostgresAuthorityCoordinator(authority);
        using InstallLinkingStore store = fixture.CreateAuthorityStore(coordinator);
        InstallationGrantDto grant = CreateGrant("must-not-survive-conflict");

        lock (store.Gate)
        {
            store.GrantsById[grant.GrantId] = grant;
            Assert.Throws<InvalidOperationException>(store.PersistLocked);
        }

        Assert.False(store.IsHealthy);
        Assert.Empty(store.GrantsById);
        using InstallLinkingAuthoritativeEnvelope current = authority.CloneCurrent();
        Assert.True(current.IsEmpty);
        Assert.False(File.Exists(fixture.StorePath));
    }

    [Fact]
    public void Valid_local_generation_ahead_of_Postgres_is_never_repaired_downward()
    {
        using var fixture = new StoreFixture();
        InstallLinkingEnvelopeCompareExchangeRequest databaseGenerationOne;
        using (InstallLinkingStore local = fixture.CreateLocalStore())
        {
            lock (local.Gate)
            {
                local.GrantsById["grant-one"] = CreateGrant("token-one") with
                {
                    GrantId = "grant-one"
                };
                local.PersistLocked();
            }

            databaseGenerationOne = local.CreateOneShotImportRequest();
            lock (local.Gate)
            {
                local.GrantsById["grant-two"] = CreateGrant("token-two") with
                {
                    GrantId = "grant-two"
                };
                local.PersistLocked();
            }
        }

        using var authority = new FakeSnapshotAuthority();
        authority.SetCurrent(databaseGenerationOne);
        var coordinator = new InstallLinkingPostgresAuthorityCoordinator(authority);

        Assert.Throws<InvalidDataException>(() =>
            fixture.CreateAuthorityStore(coordinator));
        ClearRequest(databaseGenerationOne);
    }

    private static InstallLinkingEnvelopeCompareExchangeRequest RequestForEmptyHead()
    {
        byte[] envelope = "authority-envelope"u8.ToArray();
        return new(
            ExpectedGeneration: 0,
            ExpectedCommitId: null,
            ExpectedEnvelopeSha256: null,
            NextGeneration: 1,
            CommitId: Guid.NewGuid(),
            EnvelopeVersion:
                InstallLinkingPostgresDurabilityInvariants.ProtectedEnvelopeVersion,
            SnapshotSha256: SHA256.HashData("snapshot"u8),
            EnvelopeSha256: SHA256.HashData(envelope),
            ProtectedEnvelope: envelope);
    }

    private static InstallationGrantDto CreateGrant(string accessToken)
    {
        DateTimeOffset now = DateTimeOffset.UtcNow;
        return new(
            GrantId: "grant-postgres-store-test",
            InstallationId: "installation-postgres-store-test",
            Status: InstallationGrantStates.Active,
            AccessToken: accessToken,
            IssuedAtUtc: now,
            ExpiresAtUtc: now.AddHours(8),
            UserId: "user-postgres-store-test",
            SubjectId: "subject-postgres-store-test");
    }

    private static void ClearRequest(
        InstallLinkingEnvelopeCompareExchangeRequest request)
    {
        CryptographicOperations.ZeroMemory(request.SnapshotSha256);
        CryptographicOperations.ZeroMemory(request.EnvelopeSha256);
        CryptographicOperations.ZeroMemory(request.ProtectedEnvelope);
    }

    private static void AssertZeroed(byte[] bytes)
        => Assert.All(bytes, static value => Assert.Equal(0, value));

    private sealed class StoreFixture : IDisposable
    {
        private readonly IDataProtectionProvider _provider;

        public StoreFixture()
        {
            Root = Path.Combine(
                Path.GetTempPath(),
                "install-linking-postgres-store-tests",
                Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(Root);
            StorePath = Path.Combine(Root, "install-linking-store.json");
            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = StorePath,
                    ["ASPNETCORE_ENVIRONMENT"] = "Testing"
                })
                .Build();
            _provider = DataProtectionProvider.Create(
                new DirectoryInfo(Path.Combine(Root, "keys")));
        }

        public string Root { get; }
        public string StorePath { get; }
        public IConfiguration Configuration { get; }

        public InstallLinkingStore CreateLocalStore()
            => new(
                Configuration,
                _provider,
                NullLogger<InstallLinkingStore>.Instance);

        public InstallLinkingStore CreateAuthorityStore(
            InstallLinkingPostgresAuthorityCoordinator coordinator)
            => new(
                Configuration,
                _provider,
                NullLogger<InstallLinkingStore>.Instance,
                coordinator);

        public void Dispose()
        {
            (_provider as IDisposable)?.Dispose();
            if (Directory.Exists(Root))
            {
                Directory.Delete(Root, recursive: true);
            }
        }
    }

    private sealed class FakeSnapshotAuthority :
        IInstallLinkingSnapshotAuthority,
        IDisposable
    {
        private readonly object _gate = new();
        private InstallLinkingAuthoritativeEnvelope _current = Empty();

        public bool ForceConflict { get; init; }
        public List<InstallLinkingEnvelopeCompareExchangeRequest> ObservedRequests { get; } = [];

        public Task<InstallLinkingAuthoritativeEnvelope> ReadCurrentAsync(
            CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            return Task.FromResult(CloneCurrent());
        }

        public Task<InstallLinkingEnvelopeCompareExchangeResult> CompareExchangeAsync(
            InstallLinkingEnvelopeCompareExchangeRequest request,
            CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            lock (_gate)
            {
                ObservedRequests.Add(request);
                if (ForceConflict
                    || _current.Generation != request.ExpectedGeneration
                    || _current.CommitId != request.ExpectedCommitId
                    || !FixedEquals(
                        _current.EnvelopeSha256,
                        request.ExpectedEnvelopeSha256))
                {
                    return Task.FromResult(
                        new InstallLinkingEnvelopeCompareExchangeResult(
                            InstallLinkingEnvelopeCommitDisposition.Conflict,
                            _current.Clone(),
                            "compare_exchange_conflict"));
                }

                SetCurrentLocked(request);
                return Task.FromResult(
                    new InstallLinkingEnvelopeCompareExchangeResult(
                        InstallLinkingEnvelopeCommitDisposition.Applied,
                        _current.Clone(),
                        "committed"));
            }
        }

        public Task<InstallLinkingPostgresReadiness> CheckReadinessAsync(
            CancellationToken cancellationToken = default)
        {
            cancellationToken.ThrowIfCancellationRequested();
            lock (_gate)
            {
                return Task.FromResult(new InstallLinkingPostgresReadiness(
                    true,
                    _current.IsEmpty ? "empty_authority_ready" : "ready",
                    InstallLinkingPostgresSchema.CurrentVersion,
                    InstallLinkingPostgresSchema.CurrentVersion,
                    _current.Generation,
                    DateTimeOffset.UtcNow));
            }
        }

        public InstallLinkingAuthoritativeEnvelope CloneCurrent()
        {
            lock (_gate)
            {
                return _current.Clone();
            }
        }

        public void SetCurrent(InstallLinkingEnvelopeCompareExchangeRequest request)
        {
            lock (_gate)
            {
                SetCurrentLocked(request);
            }
        }

        private void SetCurrentLocked(
            InstallLinkingEnvelopeCompareExchangeRequest request)
        {
            _current.Dispose();
            _current = new InstallLinkingAuthoritativeEnvelope(
                request.NextGeneration,
                request.CommitId,
                request.EnvelopeVersion,
                request.SnapshotSha256.ToArray(),
                request.EnvelopeSha256.ToArray(),
                request.ProtectedEnvelope.ToArray(),
                DateTimeOffset.UtcNow);
        }

        private static InstallLinkingAuthoritativeEnvelope Empty()
            => new(0, null, null, null, null, null, DateTimeOffset.UnixEpoch);

        private static bool FixedEquals(byte[]? left, byte[]? right)
        {
            if (left is null || right is null)
            {
                return left is null && right is null;
            }

            return left.Length == right.Length
                   && CryptographicOperations.FixedTimeEquals(left, right);
        }

        public void Dispose()
        {
            lock (_gate)
            {
                _current.Dispose();
                _current = Empty();
            }
        }
    }
}
