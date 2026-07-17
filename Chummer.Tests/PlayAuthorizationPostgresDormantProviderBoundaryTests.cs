using System.Reflection;
using Chummer.Run.Api.Services.Community.Postgres;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Npgsql;
using Xunit;

namespace Chummer.Tests;

public sealed class PlayAuthorizationPostgresDormantProviderBoundaryTests
{
    private static readonly PlayAuthorizationCheckpointPublicationPolicy PublicationPolicy = new(
        claimLease: TimeSpan.FromSeconds(3),
        databaseFinalizationDeadline: TimeSpan.FromMilliseconds(100),
        clockSkew: TimeSpan.FromMilliseconds(50));

    [Fact]
    public async Task CopyFirstResolutionCannotConsumeOwnerAndCopyStillFailsAfterBinding()
    {
        var authority = new TrackingCheckpointAuthority();
        var services = new ServiceCollection();
        services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
        PlayAuthorizationPostgresDormantProviderActivationHandle activation =
            services.AddPlayAuthorizationPostgresDormantProviderBoundary(authority);

        var copiedServices = new ServiceCollection();
        foreach (ServiceDescriptor descriptor in services)
        {
            ((ICollection<ServiceDescriptor>)copiedServices).Add(descriptor);
        }

        await using ServiceProvider copiedProvider = copiedServices.BuildServiceProvider();

        Assert.Throws<InvalidOperationException>(() => copiedProvider
            .GetRequiredService<PlayAuthorizationPostgresDormantFactory>());
        Assert.Throws<InvalidOperationException>(() => copiedProvider
            .GetServices<IHostedService>()
            .ToArray());

        await using ServiceProvider intendedProvider = activation.BuildServiceProvider();
        Assert.Null(intendedProvider.GetService<
            PlayAuthorizationPostgresDormantProviderActivationHandle>());
        Assert.Null(intendedProvider.GetService<
            IPlayAuthorizationCheckpointAuthority>());
        PlayAuthorizationPostgresDormantFactory factory = intendedProvider
            .GetRequiredService<PlayAuthorizationPostgresDormantFactory>();
        IHostedService startup = Assert.Single(
            intendedProvider.GetServices<IHostedService>());
        await startup.StartAsync(CancellationToken.None);
        Assert.Same(
            factory,
            intendedProvider.GetRequiredService<
                PlayAuthorizationPostgresDormantFactory>());

        Assert.Throws<InvalidOperationException>(() => copiedProvider
            .GetRequiredService<PlayAuthorizationPostgresDormantFactory>());
        Assert.Throws<InvalidOperationException>(() => copiedProvider
            .GetServices<IHostedService>()
            .ToArray());
        Assert.Throws<InvalidOperationException>(() =>
            activation.BuildServiceProvider());

        Assert.Equal(0, authority.DisposeCount);
        Assert.Equal(0, authority.DisposeAsyncCount);
    }

    [Fact]
    public async Task ConcurrentBuildReturnsExactlyOneBoundProvider()
    {
        var authority = new TrackingCheckpointAuthority();
        var services = new ServiceCollection();
        services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
        PlayAuthorizationPostgresDormantProviderActivationHandle activation =
            services.AddPlayAuthorizationPostgresDormantProviderBoundary(authority);
        const int contenderCount = 16;
        Task<object>[] contenders = Enumerable.Range(0, contenderCount)
            .Select(_ => Task.Run<object>(() =>
            {
                try
                {
                    return activation.BuildServiceProvider();
                }
                catch (Exception exception)
                {
                    return exception;
                }
            }))
            .ToArray();

        object[] results = await Task.WhenAll(contenders);
        ServiceProvider winner = Assert.Single(results.OfType<ServiceProvider>());
        try
        {
            Assert.Equal(
                contenderCount - 1,
                results.OfType<InvalidOperationException>().Count());
            Assert.NotNull(winner.GetRequiredService<
                PlayAuthorizationPostgresDormantFactory>());
            Assert.Throws<InvalidOperationException>(() =>
                activation.BuildServiceProvider());
        }
        finally
        {
            await winner.DisposeAsync();
        }

        Assert.Equal(0, authority.DisposeCount);
        Assert.Equal(0, authority.DisposeAsyncCount);
    }

    [Fact]
    public void BindFailureDisposesPartialProviderAndCannotBeReplayed()
    {
        Type providerIdentityType = typeof(PlayAuthorizationPostgresDormantProviderBoundary)
            .GetNestedType("BoundProviderIdentity", BindingFlags.NonPublic)
            ?? throw new InvalidOperationException("Missing private provider identity type.");
        var services = new ServiceCollection();
        services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
        var disposalProbe = new ProviderDisposalProbe();
        services.AddSingleton(_ => disposalProbe);
        ((ICollection<ServiceDescriptor>)services).Add(
            ServiceDescriptor.Singleton(providerIdentityType, serviceProvider =>
            {
                _ = serviceProvider.GetRequiredService<ProviderDisposalProbe>();
                return Activator.CreateInstance(providerIdentityType, nonPublic: true)
                    ?? throw new InvalidOperationException("Could not forge the test identity.");
            }));
        var authority = new TrackingCheckpointAuthority();
        int authorityFactoryCalls = 0;
        PlayAuthorizationPostgresDormantProviderActivationHandle activation =
            services.AddPlayAuthorizationPostgresDormantProviderBoundary(_ =>
            {
                Interlocked.Increment(ref authorityFactoryCalls);
                return authority;
            });

        Assert.Throws<InvalidOperationException>(() =>
            activation.BuildServiceProvider());
        Assert.Equal(1, disposalProbe.DisposeCount);
        Assert.Equal(0, authorityFactoryCalls);
        Assert.Equal(0, authority.DisposeCount);
        Assert.Equal(0, authority.DisposeAsyncCount);
        Assert.Throws<InvalidOperationException>(() =>
            activation.BuildServiceProvider());
        Assert.Equal(1, disposalProbe.DisposeCount);
    }

    [Fact]
    public void FactoryConstructionFailureDisposesOwnedAuthorityExactlyOnce()
    {
        var authority = new InvalidCapabilitiesCheckpointAuthority();
        var services = new ServiceCollection();
        services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
        int authorityFactoryCalls = 0;
        PlayAuthorizationPostgresDormantProviderActivationHandle activation =
            services.AddPlayAuthorizationPostgresDormantProviderBoundary(_ =>
            {
                Interlocked.Increment(ref authorityFactoryCalls);
                return authority;
            });
        using ServiceProvider provider = activation.BuildServiceProvider();

        Assert.Throws<InvalidOperationException>(() => provider
            .GetRequiredService<PlayAuthorizationPostgresDormantFactory>());
        provider.Dispose();
        provider.Dispose();
        Assert.Equal(1, authorityFactoryCalls);
        Assert.Equal(1, authority.DisposeCount);
        Assert.Equal(0, authority.DisposeAsyncCount);
    }

    [Fact]
    public async Task ThrowingAuthoritySourceIsSingleAttemptAndTerminalAcrossRetries()
    {
        var forbiddenRecoveryAuthority = new TrackingCheckpointAuthority();
        var services = new ServiceCollection();
        services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
        int sourceCalls = 0;
        PlayAuthorizationPostgresDormantProviderActivationHandle activation =
            services.AddPlayAuthorizationPostgresDormantProviderBoundary(_ =>
            {
                if (Interlocked.Increment(ref sourceCalls) == 1)
                {
                    throw new EffectfulAuthoritySourceException();
                }

                return forbiddenRecoveryAuthority;
            });
        using ServiceProvider provider = activation.BuildServiceProvider();

        Assert.Throws<EffectfulAuthoritySourceException>(() => provider
            .GetRequiredService<PlayAuthorizationPostgresDormantFactory>());
        Exception[] retries = await ResolveFactoryConcurrently(provider);
        Assert.All(retries, exception => Assert.IsType<ObjectDisposedException>(exception));
        Assert.Throws<ObjectDisposedException>(() => provider
            .GetRequiredService<PlayAuthorizationPostgresDormantFactory>());
        provider.Dispose();
        Assert.Equal(1, sourceCalls);
        Assert.Equal(0, forbiddenRecoveryAuthority.DisposeCount);
        Assert.Equal(0, forbiddenRecoveryAuthority.DisposeAsyncCount);
    }

    [Fact]
    public async Task NullAuthoritySourceIsSingleAttemptAndTerminalAcrossRetries()
    {
        var forbiddenRecoveryAuthority = new TrackingCheckpointAuthority();
        var services = new ServiceCollection();
        services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
        int sourceCalls = 0;
        PlayAuthorizationPostgresDormantProviderActivationHandle activation =
            services.AddPlayAuthorizationPostgresDormantProviderBoundary(_ =>
            {
                if (Interlocked.Increment(ref sourceCalls) == 1)
                {
                    return null!;
                }

                return forbiddenRecoveryAuthority;
            });
        using ServiceProvider provider = activation.BuildServiceProvider();

        InvalidOperationException firstFailure = Assert.Throws<InvalidOperationException>(() =>
            provider.GetRequiredService<PlayAuthorizationPostgresDormantFactory>());
        Assert.Contains("returned null", firstFailure.Message, StringComparison.Ordinal);
        Exception[] retries = await ResolveFactoryConcurrently(provider);
        Assert.All(retries, exception => Assert.IsType<ObjectDisposedException>(exception));
        Assert.Throws<ObjectDisposedException>(() => provider
            .GetRequiredService<PlayAuthorizationPostgresDormantFactory>());
        provider.Dispose();
        Assert.Equal(1, sourceCalls);
        Assert.Equal(0, forbiddenRecoveryAuthority.DisposeCount);
        Assert.Equal(0, forbiddenRecoveryAuthority.DisposeAsyncCount);
    }

    [Fact]
    public async Task RecursiveAuthoritySourceIsSingleAttemptAndTerminalAcrossRetries()
    {
        var forbiddenRecoveryAuthority = new TrackingCheckpointAuthority();
        var services = new ServiceCollection();
        services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
        int sourceCalls = 0;
        PlayAuthorizationPostgresDormantProviderActivationHandle activation =
            services.AddPlayAuthorizationPostgresDormantProviderBoundary(serviceProvider =>
            {
                Interlocked.Increment(ref sourceCalls);
                _ = serviceProvider.GetRequiredService<
                    PlayAuthorizationPostgresDormantFactory>();
                return forbiddenRecoveryAuthority;
            });
        using ServiceProvider provider = activation.BuildServiceProvider();

        Assert.Throws<InvalidOperationException>(() => provider
            .GetRequiredService<PlayAuthorizationPostgresDormantFactory>());
        Exception[] retries = await ResolveFactoryConcurrently(provider);
        Assert.All(retries, exception => Assert.IsType<ObjectDisposedException>(exception));
        provider.Dispose();
        Assert.Equal(1, sourceCalls);
        Assert.Equal(0, forbiddenRecoveryAuthority.DisposeCount);
        Assert.Equal(0, forbiddenRecoveryAuthority.DisposeAsyncCount);
    }

    [Fact]
    public async Task AuthorityLeaseOutlivesCallerDeadlineAndAsyncCloseDrainsCompletion()
    {
        var authority = new BlockingCheckpointAuthority();
        (ServiceProvider provider,
            PlayAuthorizationPostgresDormantFactory factory,
            PlayAuthorizationCheckpointProviderActivation checkpointProvider) =
            BuildOwnedBoundary(authority);
        try
        {
            byte[] checkpoint = Enumerable.Repeat((byte)0x5a, 32).ToArray();
            var external = new PlayAuthorizationExternalEpoch(1, 1, checkpoint.ToArray());
            var state = new PlayAuthorizationPostgresState(
                1,
                1,
                DateTimeOffset.UtcNow,
                0,
                new byte[32],
                checkpoint.ToArray());
            try
            {
                Task validation = checkpointProvider.ValidateAsync(
                    external,
                    state,
                    TimeProvider.System,
                    CancellationToken.None);
                await authority.Started.WaitAsync(TimeSpan.FromSeconds(2));
                await Assert.ThrowsAsync<PlayAuthorizationProviderDeadlineExceededException>(
                    () => validation);
                Assert.Equal(
                    1,
                    factory.ProviderCallDiagnostics.ValidationCallsInFlight);

                Task closing = ((IAsyncDisposable)factory).DisposeAsync().AsTask();
                await Task.Yield();
                Assert.False(closing.IsCompleted);
                Assert.Throws<ObjectDisposedException>(() =>
                    _ = factory.ProviderCallDiagnostics);
                await Assert.ThrowsAsync<ObjectDisposedException>(() =>
                    checkpointProvider.ValidateAsync(
                        external,
                        state,
                        TimeProvider.System,
                        CancellationToken.None));

                authority.Release();
                await closing.WaitAsync(TimeSpan.FromSeconds(2));
                Assert.Equal(1, authority.CompletedCount);
                Assert.Equal(0, authority.DisposeCount);
                Assert.Equal(1, authority.DisposeAsyncCount);
                await ((IAsyncDisposable)factory).DisposeAsync();
                Assert.Equal(1, authority.DisposeAsyncCount);
                Assert.Throws<ObjectDisposedException>(() =>
                    _ = checkpointProvider.Capabilities);
            }
            finally
            {
                authority.Release();
                Array.Clear(checkpoint);
                Array.Clear(external.Checkpoint);
                Array.Clear(state.AuditHeadHmac);
                Array.Clear(state.ExternalCheckpoint);
            }
        }
        finally
        {
            await provider.DisposeAsync();
        }
    }

    [Fact]
    public async Task OwnedAndExternalAuthorityDisposalHonorsOwnershipAndExactlyOnce()
    {
        var ownedAsync = new TrackingCheckpointAuthority();
        (ServiceProvider asyncProvider,
            PlayAuthorizationPostgresDormantFactory asyncFactory,
            _) = BuildOwnedBoundary(ownedAsync);
        Task[] concurrentAsyncDisposals = Enumerable.Range(0, 16)
            .Select(_ => ((IAsyncDisposable)asyncFactory).DisposeAsync().AsTask())
            .ToArray();
        await Task.WhenAll(concurrentAsyncDisposals);
        await asyncProvider.DisposeAsync();
        Assert.Equal(0, ownedAsync.DisposeCount);
        Assert.Equal(1, ownedAsync.DisposeAsyncCount);

        var ownedSync = new TrackingCheckpointAuthority();
        (ServiceProvider syncProvider,
            PlayAuthorizationPostgresDormantFactory syncFactory,
            _) = BuildOwnedBoundary(ownedSync);
        ((IDisposable)syncFactory).Dispose();
        ((IDisposable)syncFactory).Dispose();
        syncProvider.Dispose();
        Assert.Equal(1, ownedSync.DisposeCount);
        Assert.Equal(0, ownedSync.DisposeAsyncCount);

        var external = new TrackingCheckpointAuthority();
        (ServiceProvider externalProvider,
            PlayAuthorizationPostgresDormantFactory externalFactory,
            _) = BuildExternalBoundary(external);
        await ((IAsyncDisposable)externalFactory).DisposeAsync();
        await externalProvider.DisposeAsync();
        Assert.Equal(0, external.DisposeCount);
        Assert.Equal(0, external.DisposeAsyncCount);
        external.Dispose();
        Assert.Equal(1, external.DisposeCount);
    }

    [Fact]
    public async Task AsyncOnlyAuthorityRejectsSyncCloseThenCanBeDrainedAsynchronously()
    {
        var authority = new AsyncOnlyCheckpointAuthority();
        (ServiceProvider provider,
            PlayAuthorizationPostgresDormantFactory factory,
            _) = BuildOwnedBoundary(authority);
        try
        {
            Assert.Throws<InvalidOperationException>(() =>
                ((IDisposable)factory).Dispose());
            Assert.Throws<ObjectDisposedException>(() =>
                _ = factory.ProviderCallDiagnostics);
            await ((IAsyncDisposable)factory).DisposeAsync();
            await ((IAsyncDisposable)factory).DisposeAsync();
            Assert.Equal(1, authority.DisposeAsyncCount);
        }
        finally
        {
            await provider.DisposeAsync();
        }
    }

    [Fact]
    public async Task ClosingInvalidatesFactoryRepositoryReconcilerAndReadinessObjects()
    {
        var authority = new TrackingCheckpointAuthority();
        (ServiceProvider provider,
            PlayAuthorizationPostgresDormantFactory factory,
            PlayAuthorizationCheckpointProviderActivation activation) =
            BuildExternalBoundary(authority);
        await using NpgsqlDataSource dataSource = NpgsqlDataSource.Create(
            "Host=127.0.0.1;Port=1;Database=unused;Username=unused;Password=unused;Timeout=1;Pooling=false");
        var epochAuthority = new NeverUsedEpochAuthority();
        factory.BindCheckpointReconciliation(
            dataSource,
            epochAuthority,
            PublicationPolicy,
            TimeProvider.System);
        var receiptCipher = new NeverUsedReceiptCipher();
        NpgsqlPlayAuthorizationRepository repository = factory.CreateRepository(
            dataSource,
            new NpgsqlPlayAuthorizationUnitOfWorkFactory(dataSource),
            epochAuthority,
            new NeverUsedHmacAuthority(),
            PublicationPolicy,
            receiptCipher,
            new NoOpPlayAuthorizationCommitObserver(),
            TimeProvider.System);
        PlayAuthorizationPostgresReadinessProbe readiness = factory.CreateReadinessProbe(
            dataSource,
            new PlayAuthorizationPostgresMigrator(dataSource),
            epochAuthority,
            PublicationPolicy,
            new PlayAuthorizationReplaySafetyPolicy(
                maximumCapabilityOrReplayWindow: TimeSpan.FromDays(1),
                clockSkew: TimeSpan.FromMinutes(1)),
            TimeProvider.System);
        var reconciler = Assert.IsType<
            NpgsqlPlayAuthorizationCheckpointPublicationReconciler>(
                ReadPrivate(factory, "_reconciler"));

        await ((IAsyncDisposable)factory).DisposeAsync();

        Assert.Throws<ObjectDisposedException>(() =>
            _ = factory.ProviderCallDiagnostics);
        Assert.Throws<ObjectDisposedException>(() =>
            factory.BindCheckpointReconciliation(
                dataSource,
                epochAuthority,
                PublicationPolicy,
                TimeProvider.System));
        Assert.Throws<ObjectDisposedException>(() =>
        {
            _ = repository.RedeemInviteAsync(null!);
        });
        await Assert.ThrowsAsync<ObjectDisposedException>(() =>
            repository.LookupIdempotencyReceiptAsync(null!));
        await Assert.ThrowsAsync<ObjectDisposedException>(() =>
            reconciler.ReconcileAsync(1));
        await Assert.ThrowsAsync<ObjectDisposedException>(() =>
            reconciler.IsPublishedAsync(1, 1, 1));
        Assert.Throws<ObjectDisposedException>(() =>
            _ = reconciler.ProviderCallDiagnostics);
        await Assert.ThrowsAsync<ObjectDisposedException>(() =>
            readiness.CheckAsync());
        Assert.Throws<ObjectDisposedException>(() =>
            _ = activation.Diagnostics);

        await provider.DisposeAsync();
        Assert.Equal(0, authority.DisposeCount);
        Assert.Equal(0, authority.DisposeAsyncCount);
    }

    [Fact]
    public void ActivationHandleOwnsBuildAndHasNoCandidateProviderSurface()
    {
        Assert.Empty(typeof(PlayAuthorizationPostgresDormantProviderActivationHandle)
            .GetConstructors(BindingFlags.Instance | BindingFlags.Public));
        MethodInfo build = Assert.Single(
            typeof(PlayAuthorizationPostgresDormantProviderActivationHandle)
                .GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.DeclaredOnly));
        Assert.Equal(
            nameof(PlayAuthorizationPostgresDormantProviderActivationHandle.BuildServiceProvider),
            build.Name);
        Assert.Equal(typeof(ServiceProvider), build.ReturnType);
        Assert.Equal(
            typeof(ServiceProviderOptions),
            Assert.Single(build.GetParameters()).ParameterType);
        Assert.DoesNotContain(
            typeof(PlayAuthorizationPostgresDormantProviderActivationHandle)
                .GetMethods(BindingFlags.Instance | BindingFlags.Public),
            method => method.GetParameters().Any(parameter =>
                typeof(IServiceProvider).IsAssignableFrom(parameter.ParameterType)
                || typeof(Delegate).IsAssignableFrom(parameter.ParameterType)));
    }

    [Fact]
    public void DormantBoundaryRemainsUnwiredFromProgramComposition()
    {
        string programSource = File.ReadAllText(
            RepoPaths.FromRoot("Chummer.Run.Api", "Program.cs"));
        Assert.DoesNotContain(
            nameof(PlayAuthorizationPostgresDormantProviderBoundary
                .AddPlayAuthorizationPostgresDormantProviderBoundary),
            programSource,
            StringComparison.Ordinal);
        Assert.DoesNotContain(
            "new NpgsqlPlayAuthorizationRepository",
            programSource,
            StringComparison.Ordinal);
        Assert.DoesNotContain(
            "new NpgsqlPlayAuthorizationCheckpointPublicationReconciler",
            programSource,
            StringComparison.Ordinal);
        Assert.DoesNotContain(
            "new PlayAuthorizationPostgresReadinessProbe",
            programSource,
            StringComparison.Ordinal);
    }

    private static (ServiceProvider Provider,
        PlayAuthorizationPostgresDormantFactory Factory,
        PlayAuthorizationCheckpointProviderActivation Activation)
        BuildOwnedBoundary(IPlayAuthorizationCheckpointAuthority authority)
    {
        var services = new ServiceCollection();
        services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
        PlayAuthorizationPostgresDormantProviderActivationHandle activation =
            services.AddPlayAuthorizationPostgresDormantProviderBoundary(_ => authority);
        ServiceProvider provider = activation.BuildServiceProvider();
        PlayAuthorizationPostgresDormantFactory factory = provider
            .GetRequiredService<PlayAuthorizationPostgresDormantFactory>();
        return (provider, factory, Assert.IsType<
            PlayAuthorizationCheckpointProviderActivation>(
                ReadPrivate(factory, "_provider")));
    }

    private static (ServiceProvider Provider,
        PlayAuthorizationPostgresDormantFactory Factory,
        PlayAuthorizationCheckpointProviderActivation Activation)
        BuildExternalBoundary(IPlayAuthorizationCheckpointAuthority authority)
    {
        var services = new ServiceCollection();
        services.AddSingleton<PlayAuthorizationCheckpointProviderCallRegistry>();
        PlayAuthorizationPostgresDormantProviderActivationHandle activation =
            services.AddPlayAuthorizationPostgresDormantProviderBoundary(authority);
        ServiceProvider provider = activation.BuildServiceProvider();
        PlayAuthorizationPostgresDormantFactory factory = provider
            .GetRequiredService<PlayAuthorizationPostgresDormantFactory>();
        return (provider, factory, Assert.IsType<
            PlayAuthorizationCheckpointProviderActivation>(
                ReadPrivate(factory, "_provider")));
    }

    private static object ReadPrivate(object target, string fieldName) =>
        target.GetType()
            .GetField(fieldName, BindingFlags.Instance | BindingFlags.NonPublic)
            ?.GetValue(target)
        ?? throw new InvalidOperationException($"Missing private field {fieldName}.");

    private static Task<Exception[]> ResolveFactoryConcurrently(
        ServiceProvider provider,
        int contenderCount = 16) =>
        Task.WhenAll(Enumerable.Range(0, contenderCount)
            .Select(_ => Task.Run(() =>
            {
                try
                {
                    provider.GetRequiredService<
                        PlayAuthorizationPostgresDormantFactory>();
                    return new InvalidOperationException(
                        "A terminal authority construction unexpectedly recovered.");
                }
                catch (Exception exception)
                {
                    return exception;
                }
            })));

    private sealed class EffectfulAuthoritySourceException : Exception
    {
    }

    private sealed class ProviderDisposalProbe : IDisposable
    {
        private int _disposeCount;

        public int DisposeCount => Volatile.Read(ref _disposeCount);

        public void Dispose() => Interlocked.Increment(ref _disposeCount);
    }

    private class TrackingCheckpointAuthority :
        IPlayAuthorizationCheckpointAuthority,
        IDisposable,
        IAsyncDisposable
    {
        private int _disposeCount;
        private int _disposeAsyncCount;

        public virtual PlayAuthorizationCheckpointProviderCapabilities Capabilities { get; } =
            new(
                TimeSpan.FromMilliseconds(100),
                SupportsMonotonicFencing: true,
                PlayAuthorizationPostgresDurabilityInvariants.CheckpointDigestAlgorithm,
                PlayAuthorizationPostgresDurabilityInvariants.CheckpointCanonicalVersion,
                PlayAuthorizationPostgresDurabilityInvariants.HmacAlgorithm,
                PlayAuthorizationPostgresDurabilityInvariants.HmacSizeInBytes);

        public int DisposeCount => Volatile.Read(ref _disposeCount);
        public int DisposeAsyncCount => Volatile.Read(ref _disposeAsyncCount);

        public virtual ValueTask ValidateAsync(
            PlayAuthorizationExternalEpoch externalEpoch,
            PlayAuthorizationPostgresState databaseState,
            CancellationToken cancellationToken) => ValueTask.CompletedTask;

        public virtual ValueTask<PlayAuthorizationCheckpointBaselineAcknowledgement>
            VerifyBaselineAsync(
                PlayAuthorizationCheckpointBaselineVerification verification,
                PlayAuthorizationExternalEpoch externalEpoch,
                CancellationToken cancellationToken) =>
            ValueTask.FromException<PlayAuthorizationCheckpointBaselineAcknowledgement>(
                new NotSupportedException());

        public virtual ValueTask<PlayAuthorizationCheckpointPublicationAcknowledgement>
            PublishAsync(
                PlayAuthorizationCheckpointPublicationEnvelope envelope,
                CancellationToken cancellationToken) =>
            ValueTask.FromException<PlayAuthorizationCheckpointPublicationAcknowledgement>(
                new NotSupportedException());

        public void Dispose() => Interlocked.Increment(ref _disposeCount);

        public ValueTask DisposeAsync()
        {
            Interlocked.Increment(ref _disposeAsyncCount);
            return ValueTask.CompletedTask;
        }
    }

    private sealed class InvalidCapabilitiesCheckpointAuthority :
        TrackingCheckpointAuthority
    {
        public override PlayAuthorizationCheckpointProviderCapabilities Capabilities { get; } =
            null!;
    }

    private sealed class BlockingCheckpointAuthority : TrackingCheckpointAuthority
    {
        private readonly TaskCompletionSource _started = new(
            TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource _release = new(
            TaskCreationOptions.RunContinuationsAsynchronously);
        private int _completedCount;

        public override PlayAuthorizationCheckpointProviderCapabilities Capabilities { get; } =
            new(
                TimeSpan.FromMilliseconds(50),
                SupportsMonotonicFencing: true,
                PlayAuthorizationPostgresDurabilityInvariants.CheckpointDigestAlgorithm,
                PlayAuthorizationPostgresDurabilityInvariants.CheckpointCanonicalVersion,
                PlayAuthorizationPostgresDurabilityInvariants.HmacAlgorithm,
                PlayAuthorizationPostgresDurabilityInvariants.HmacSizeInBytes);

        public Task Started => _started.Task;
        public int CompletedCount => Volatile.Read(ref _completedCount);

        public override async ValueTask ValidateAsync(
            PlayAuthorizationExternalEpoch externalEpoch,
            PlayAuthorizationPostgresState databaseState,
            CancellationToken cancellationToken)
        {
            _started.TrySetResult();
            await _release.Task.ConfigureAwait(false);
            Interlocked.Increment(ref _completedCount);
        }

        public void Release() => _release.TrySetResult();
    }

    private sealed class AsyncOnlyCheckpointAuthority :
        IPlayAuthorizationCheckpointAuthority,
        IAsyncDisposable
    {
        private int _disposeAsyncCount;

        public PlayAuthorizationCheckpointProviderCapabilities Capabilities { get; } =
            new(
                TimeSpan.FromMilliseconds(100),
                SupportsMonotonicFencing: true,
                PlayAuthorizationPostgresDurabilityInvariants.CheckpointDigestAlgorithm,
                PlayAuthorizationPostgresDurabilityInvariants.CheckpointCanonicalVersion,
                PlayAuthorizationPostgresDurabilityInvariants.HmacAlgorithm,
                PlayAuthorizationPostgresDurabilityInvariants.HmacSizeInBytes);

        public int DisposeAsyncCount => Volatile.Read(ref _disposeAsyncCount);

        public ValueTask ValidateAsync(
            PlayAuthorizationExternalEpoch externalEpoch,
            PlayAuthorizationPostgresState databaseState,
            CancellationToken cancellationToken) => ValueTask.CompletedTask;

        public ValueTask<PlayAuthorizationCheckpointBaselineAcknowledgement>
            VerifyBaselineAsync(
                PlayAuthorizationCheckpointBaselineVerification verification,
                PlayAuthorizationExternalEpoch externalEpoch,
                CancellationToken cancellationToken) =>
            ValueTask.FromException<PlayAuthorizationCheckpointBaselineAcknowledgement>(
                new NotSupportedException());

        public ValueTask<PlayAuthorizationCheckpointPublicationAcknowledgement>
            PublishAsync(
                PlayAuthorizationCheckpointPublicationEnvelope envelope,
                CancellationToken cancellationToken) =>
            ValueTask.FromException<PlayAuthorizationCheckpointPublicationAcknowledgement>(
                new NotSupportedException());

        public ValueTask DisposeAsync()
        {
            Interlocked.Increment(ref _disposeAsyncCount);
            return ValueTask.CompletedTask;
        }
    }

    private sealed class NeverUsedEpochAuthority : IPlayAuthorizationEpochAuthority
    {
        public ValueTask<PlayAuthorizationExternalEpoch> ReadCurrentAsync(
            CancellationToken cancellationToken) =>
            ValueTask.FromException<PlayAuthorizationExternalEpoch>(
                new InvalidOperationException("The closed object reached its epoch authority."));
    }

    private sealed class NeverUsedHmacAuthority : IPlayAuthorizationHmacAuthority
    {
        public ValueTask<PlayAuthorizationKeyedDigest> ComputeCapabilityAsync(
            PlayAuthorizationCapabilityKind kind,
            string capabilityId,
            ReadOnlyMemory<byte> secret,
            string? requiredKeyId,
            CancellationToken cancellationToken) =>
            ValueTask.FromException<PlayAuthorizationKeyedDigest>(
                new InvalidOperationException("The closed object reached its HMAC authority."));

        public ValueTask<PlayAuthorizationKeyedDigest> ComputeAuditAsync(
            PlayAuthorizationAuditDigestInput input,
            CancellationToken cancellationToken) =>
            ValueTask.FromException<PlayAuthorizationKeyedDigest>(
                new InvalidOperationException("The closed object reached its HMAC authority."));
    }

    private sealed class NeverUsedReceiptCipher : IPlayAuthorizationReceiptCipher
    {
        public PlayAuthorizationProtectedReceipt Protect(
            PlayAuthorizationReceiptEnvelope envelope) =>
            throw new InvalidOperationException("The closed object reached its receipt cipher.");

        public PlayAuthorizationReceiptEnvelope Unprotect(
            ReadOnlySpan<byte> ciphertext,
            ReadOnlySpan<byte> expectedPlaintextSha256,
            string expectedResponseType) =>
            throw new InvalidOperationException("The closed object reached its receipt cipher.");
    }
}
