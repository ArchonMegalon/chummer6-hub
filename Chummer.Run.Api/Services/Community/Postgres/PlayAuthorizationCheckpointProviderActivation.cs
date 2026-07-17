using System.Security.Cryptography;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Npgsql;

namespace Chummer.Run.Api.Services.Community.Postgres;

internal enum PlayAuthorizationCheckpointProviderLaneKind
{
    Validation,
    Baseline,
    Publication
}

internal enum PlayAuthorizationCheckpointAuthorityLifecycleState
{
    Open,
    Closing,
    Closed
}

/// <summary>
/// Shared lifetime gate for every object materialized by one dormant provider boundary. Authority
/// reservations stay active until the scheduled provider invocation actually completes, even when
/// its caller has already timed out or cancelled its wait.
/// </summary>
internal sealed class PlayAuthorizationCheckpointAuthorityLifecycle
{
    private readonly object _gate = new();
    private readonly TaskCompletionSource _drained = new(
        TaskCreationOptions.RunContinuationsAsynchronously);
    private PlayAuthorizationCheckpointAuthorityLifecycleState _state =
        PlayAuthorizationCheckpointAuthorityLifecycleState.Open;
    private int _activeAuthorityCalls;

    public PlayAuthorizationCheckpointAuthorityLifecycleState State
    {
        get
        {
            lock (_gate)
            {
                return _state;
            }
        }
    }

    public void DemandOpen()
    {
        lock (_gate)
        {
            DemandOpenUnsafe();
        }
    }

    public AuthorityCallLease ReserveAuthorityCall()
    {
        lock (_gate)
        {
            DemandOpenUnsafe();
            _activeAuthorityCalls++;
            return new AuthorityCallLease(this);
        }
    }

    public Task BeginClosing()
    {
        lock (_gate)
        {
            if (_state == PlayAuthorizationCheckpointAuthorityLifecycleState.Open)
            {
                _state = PlayAuthorizationCheckpointAuthorityLifecycleState.Closing;
            }

            if (_activeAuthorityCalls == 0)
            {
                _drained.TrySetResult();
            }

            return _drained.Task;
        }
    }

    public void MarkClosed()
    {
        lock (_gate)
        {
            if (_activeAuthorityCalls != 0)
            {
                throw new InvalidOperationException(
                    "The checkpoint authority cannot close while provider calls are active.");
            }

            _state = PlayAuthorizationCheckpointAuthorityLifecycleState.Closed;
            _drained.TrySetResult();
        }
    }

    private void ReleaseAuthorityCall()
    {
        lock (_gate)
        {
            if (_activeAuthorityCalls <= 0)
            {
                throw new InvalidOperationException(
                    "The checkpoint authority call reservation was released more than once.");
            }

            _activeAuthorityCalls--;
            if (_activeAuthorityCalls == 0
                && _state != PlayAuthorizationCheckpointAuthorityLifecycleState.Open)
            {
                _drained.TrySetResult();
            }
        }
    }

    private void DemandOpenUnsafe()
    {
        if (_state != PlayAuthorizationCheckpointAuthorityLifecycleState.Open)
        {
            throw new ObjectDisposedException(
                nameof(PlayAuthorizationPostgresDormantFactory),
                "The Play authorization PostgreSQL authority boundary is closing or closed.");
        }
    }

    internal sealed class AuthorityCallLease : IDisposable
    {
        private PlayAuthorizationCheckpointAuthorityLifecycle? _owner;

        public AuthorityCallLease(PlayAuthorizationCheckpointAuthorityLifecycle owner)
        {
            _owner = owner;
        }

        public void Dispose()
        {
            PlayAuthorizationCheckpointAuthorityLifecycle? owner =
                Interlocked.Exchange(ref _owner, null);
            owner?.ReleaseAuthorityCall();
        }
    }
}

internal sealed class PlayAuthorizationCheckpointProviderCallInFlightException : Exception
{
    public PlayAuthorizationCheckpointProviderCallInFlightException(
        PlayAuthorizationCheckpointProviderLaneKind lane)
        : base($"The checkpoint provider {lane.ToString().ToLowerInvariant()} lane is already in flight.")
    {
        Lane = lane;
    }

    public PlayAuthorizationCheckpointProviderLaneKind Lane { get; }
}

internal sealed record PlayAuthorizationCheckpointBaselineProviderResult(
    bool Exact,
    bool Accepted);

internal sealed record PlayAuthorizationCheckpointPublicationProviderResult(
    bool Exact,
    bool Accepted,
    PlayAuthorizationCheckpointPublicationDisposition? Disposition);

/// <summary>
/// Opaque activated checkpoint-provider token. Its private constructor and boundary lease ensure
/// repositories and reconcilers only receive an authority activated by the dormant factory.
/// </summary>
internal sealed class PlayAuthorizationCheckpointProviderActivation
{
    private readonly IPlayAuthorizationCheckpointAuthority _authority;
    private readonly PlayAuthorizationCheckpointProviderCallRegistry.ProviderCallLanes _calls;
    private readonly PlayAuthorizationCheckpointAuthorityLifecycle _lifecycle;
    private readonly PlayAuthorizationCheckpointProviderCapabilities _capabilities;

    private PlayAuthorizationCheckpointProviderActivation(
        IPlayAuthorizationCheckpointAuthority authority,
        PlayAuthorizationCheckpointProviderCallRegistry registry,
        PlayAuthorizationCheckpointAuthorityLifecycle lifecycle)
    {
        _authority = authority ?? throw new ArgumentNullException(nameof(authority));
        ArgumentNullException.ThrowIfNull(registry);
        _capabilities = _authority.Capabilities
            ?? throw new InvalidOperationException(
                "The checkpoint provider capability contract is missing.");
        PlayAuthorizationCheckpointProviderDeadline.Validate(_capabilities);
        _calls = registry.For(_authority);
        _lifecycle = lifecycle ?? throw new ArgumentNullException(nameof(lifecycle));
    }

    internal static PlayAuthorizationCheckpointProviderActivation Create(
        object boundaryLease,
        IPlayAuthorizationCheckpointAuthority authority,
        PlayAuthorizationCheckpointProviderCallRegistry registry,
        PlayAuthorizationCheckpointAuthorityLifecycle lifecycle)
    {
        PlayAuthorizationPostgresDormantProviderBoundary
            .DemandFactoryConstructionLease(boundaryLease);
        return new(authority, registry, lifecycle);
    }

    public PlayAuthorizationCheckpointProviderCapabilities Capabilities
    {
        get
        {
            _lifecycle.DemandOpen();
            return _capabilities;
        }
    }

    public PlayAuthorizationCheckpointProviderCallDiagnostics Diagnostics
    {
        get
        {
            _lifecycle.DemandOpen();
            return new(
                _calls.Validation.ActiveCount,
                _calls.Baseline.ActiveCount,
                _calls.Publication.ActiveCount);
        }
    }

    internal void DemandOpen() => _lifecycle.DemandOpen();

    internal async Task ValidateAsync(
        PlayAuthorizationExternalEpoch externalEpoch,
        PlayAuthorizationPostgresState databaseState,
        TimeProvider timeProvider,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(externalEpoch);
        ArgumentNullException.ThrowIfNull(databaseState);
        ArgumentNullException.ThrowIfNull(timeProvider);
        PlayAuthorizationCheckpointAuthorityLifecycle.AuthorityCallLease authorityLease =
            _lifecycle.ReserveAuthorityCall();
        PlayAuthorizationCheckpointProviderCallRegistry.ProviderCallReservation<bool> reservation =
            _calls.Validation.TryReserve<bool>()
            ?? ThrowLaneInFlight<bool>(authorityLease,
                PlayAuthorizationCheckpointProviderLaneKind.Validation);
        OwnedValidationProviderCall? providerCall = null;
        try
        {
            providerCall = new OwnedValidationProviderCall(externalEpoch, databaseState);
        }
        catch
        {
            reservation.Abort();
            authorityLease.Dispose();
            throw;
        }

        if (!reservation.Schedule(() => RunValidationAsync(
                providerCall!,
                authorityLease,
                timeProvider,
                cancellationToken)))
        {
            providerCall.Dispose();
            authorityLease.Dispose();
        }

        await AwaitProviderAsync(
            reservation.Task,
            timeProvider,
            cancellationToken);
    }

    internal async Task<PlayAuthorizationCheckpointBaselineProviderResult> VerifyBaselineAsync(
        PlayAuthorizationCheckpointBaselineVerification verification,
        PlayAuthorizationExternalEpoch externalEpoch,
        TimeProvider timeProvider,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(verification);
        ArgumentNullException.ThrowIfNull(externalEpoch);
        ArgumentNullException.ThrowIfNull(timeProvider);
        PlayAuthorizationCheckpointAuthorityLifecycle.AuthorityCallLease authorityLease =
            _lifecycle.ReserveAuthorityCall();
        PlayAuthorizationCheckpointProviderCallRegistry.ProviderCallReservation<
            PlayAuthorizationCheckpointBaselineProviderResult> reservation =
            _calls.Baseline.TryReserve<PlayAuthorizationCheckpointBaselineProviderResult>()
            ?? ThrowLaneInFlight<PlayAuthorizationCheckpointBaselineProviderResult>(
                authorityLease,
                PlayAuthorizationCheckpointProviderLaneKind.Baseline);
        OwnedBaselineProviderCall? providerCall = null;
        try
        {
            providerCall = new OwnedBaselineProviderCall(verification, externalEpoch);
        }
        catch
        {
            reservation.Abort();
            authorityLease.Dispose();
            throw;
        }

        if (!reservation.Schedule(() => RunBaselineAsync(
                providerCall!,
                authorityLease,
                timeProvider,
                cancellationToken)))
        {
            providerCall.Dispose();
            authorityLease.Dispose();
        }

        return await AwaitProviderAsync(
            reservation.Task,
            timeProvider,
            cancellationToken);
    }

    internal async Task<PlayAuthorizationCheckpointPublicationProviderResult> PublishAsync(
        PlayAuthorizationCheckpointPublicationEnvelope envelope,
        TimeProvider timeProvider,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(envelope);
        ArgumentNullException.ThrowIfNull(timeProvider);
        PlayAuthorizationCheckpointAuthorityLifecycle.AuthorityCallLease authorityLease =
            _lifecycle.ReserveAuthorityCall();
        PlayAuthorizationCheckpointProviderCallRegistry.ProviderCallReservation<
            PlayAuthorizationCheckpointPublicationProviderResult> reservation =
            _calls.Publication.TryReserve<PlayAuthorizationCheckpointPublicationProviderResult>()
            ?? ThrowLaneInFlight<PlayAuthorizationCheckpointPublicationProviderResult>(
                authorityLease,
                PlayAuthorizationCheckpointProviderLaneKind.Publication);
        OwnedPublicationProviderCall? providerCall = null;
        try
        {
            providerCall = new OwnedPublicationProviderCall(envelope);
        }
        catch
        {
            reservation.Abort();
            authorityLease.Dispose();
            throw;
        }

        if (!reservation.Schedule(() => RunPublicationAsync(
                providerCall!,
                authorityLease,
                timeProvider,
                cancellationToken)))
        {
            providerCall.Dispose();
            authorityLease.Dispose();
        }

        return await AwaitProviderAsync(
            reservation.Task,
            timeProvider,
            cancellationToken);
    }

    private async Task<bool> RunValidationAsync(
        OwnedValidationProviderCall providerCall,
        PlayAuthorizationCheckpointAuthorityLifecycle.AuthorityCallLease authorityLease,
        TimeProvider timeProvider,
        CancellationToken callerToken)
    {
        using (authorityLease)
        using (providerCall)
        using (CancellationTokenSource timeout = new(_capabilities.HardDeadline, timeProvider))
        using (CancellationTokenSource deadline = CancellationTokenSource.CreateLinkedTokenSource(
                   callerToken,
                   timeout.Token))
        {
            await _authority.ValidateAsync(
                providerCall.ExternalEpoch,
                providerCall.DatabaseState,
                deadline.Token);
            return true;
        }
    }

    private async Task<PlayAuthorizationCheckpointBaselineProviderResult> RunBaselineAsync(
        OwnedBaselineProviderCall providerCall,
        PlayAuthorizationCheckpointAuthorityLifecycle.AuthorityCallLease authorityLease,
        TimeProvider timeProvider,
        CancellationToken callerToken)
    {
        using (authorityLease)
        using (providerCall)
        using (CancellationTokenSource timeout = new(_capabilities.HardDeadline, timeProvider))
        using (CancellationTokenSource deadline = CancellationTokenSource.CreateLinkedTokenSource(
                   callerToken,
                   timeout.Token))
        {
            PlayAuthorizationCheckpointBaselineAcknowledgement acknowledgement =
                await _authority.VerifyBaselineAsync(
                    providerCall.Verification,
                    providerCall.ExternalEpoch,
                    deadline.Token);
            byte[]? acknowledgementDigest = null;
            try
            {
                acknowledgementDigest = acknowledgement?.PayloadDigestSha256?.ToArray();
                bool exact = acknowledgement is not null
                    && acknowledgement.BaselineId == providerCall.Verification.BaselineId
                    && acknowledgementDigest is not null
                    && acknowledgementDigest.Length
                        == providerCall.Verification.PayloadDigestSha256.Length
                    && CryptographicOperations.FixedTimeEquals(
                        acknowledgementDigest,
                        providerCall.Verification.PayloadDigestSha256);
                return new(exact, acknowledgement?.Accepted == true);
            }
            finally
            {
                if (acknowledgementDigest is not null)
                {
                    CryptographicOperations.ZeroMemory(acknowledgementDigest);
                }
            }
        }
    }

    private async Task<PlayAuthorizationCheckpointPublicationProviderResult> RunPublicationAsync(
        OwnedPublicationProviderCall providerCall,
        PlayAuthorizationCheckpointAuthorityLifecycle.AuthorityCallLease authorityLease,
        TimeProvider timeProvider,
        CancellationToken callerToken)
    {
        using (authorityLease)
        using (providerCall)
        using (CancellationTokenSource timeout = new(_capabilities.HardDeadline, timeProvider))
        using (CancellationTokenSource deadline = CancellationTokenSource.CreateLinkedTokenSource(
                   callerToken,
                   timeout.Token))
        {
            PlayAuthorizationCheckpointPublicationAcknowledgement acknowledgement =
                await _authority.PublishAsync(providerCall.Envelope, deadline.Token);
            byte[]? acknowledgementDigest = null;
            try
            {
                acknowledgementDigest = acknowledgement?.PayloadDigestSha256?.ToArray();
                PlayAuthorizationCheckpointPublicationDisposition? disposition =
                    acknowledgement?.Disposition;
                bool exact = acknowledgement is not null
                    && acknowledgement.PublicationId == providerCall.Envelope.PublicationId
                    && acknowledgement.AcceptedFencingToken
                        == providerCall.Envelope.FencingToken
                    && acknowledgementDigest is not null
                    && acknowledgementDigest.Length
                        == providerCall.Envelope.PayloadDigestSha256.Length
                    && CryptographicOperations.FixedTimeEquals(
                        acknowledgementDigest,
                        providerCall.Envelope.PayloadDigestSha256);
                bool accepted = disposition is
                    PlayAuthorizationCheckpointPublicationDisposition.Accepted
                    or PlayAuthorizationCheckpointPublicationDisposition.AlreadyPublished;
                return new(exact, accepted, disposition);
            }
            finally
            {
                if (acknowledgementDigest is not null)
                {
                    CryptographicOperations.ZeroMemory(acknowledgementDigest);
                }
            }
        }
    }

    private async Task<T> AwaitProviderAsync<T>(
        Task<T> providerTask,
        TimeProvider timeProvider,
        CancellationToken cancellationToken)
    {
        try
        {
            return await providerTask.WaitAsync(
                _capabilities.HardDeadline,
                timeProvider,
                cancellationToken);
        }
        catch (TimeoutException)
        {
            throw new PlayAuthorizationProviderDeadlineExceededException();
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            throw new PlayAuthorizationProviderDeadlineExceededException();
        }
    }

    private static PlayAuthorizationCheckpointProviderCallRegistry.ProviderCallReservation<T>
        ThrowLaneInFlight<T>(
        PlayAuthorizationCheckpointAuthorityLifecycle.AuthorityCallLease authorityLease,
        PlayAuthorizationCheckpointProviderLaneKind lane)
    {
        authorityLease.Dispose();
        throw new PlayAuthorizationCheckpointProviderCallInFlightException(lane);
    }

    private static PlayAuthorizationPostgresState CopyState(PlayAuthorizationPostgresState state)
    {
        byte[] auditHeadHmac = state.AuditHeadHmac.ToArray();
        byte[]? externalCheckpoint = null;
        try
        {
            externalCheckpoint = state.ExternalCheckpoint.ToArray();
            return new(
                state.Epoch,
                state.Generation,
                state.ClockHighWaterUtc,
                state.AuditHeadSequence,
                auditHeadHmac,
                externalCheckpoint);
        }
        catch
        {
            CryptographicOperations.ZeroMemory(auditHeadHmac);
            if (externalCheckpoint is not null)
            {
                CryptographicOperations.ZeroMemory(externalCheckpoint);
            }

            throw;
        }
    }

    private static void ZeroState(PlayAuthorizationPostgresState state)
    {
        CryptographicOperations.ZeroMemory(state.AuditHeadHmac);
        CryptographicOperations.ZeroMemory(state.ExternalCheckpoint);
    }

    private sealed class OwnedValidationProviderCall : IDisposable
    {
        private int _disposed;

        public OwnedValidationProviderCall(
            PlayAuthorizationExternalEpoch externalEpoch,
            PlayAuthorizationPostgresState databaseState)
        {
            byte[]? checkpoint = null;
            PlayAuthorizationPostgresState? state = null;
            try
            {
                checkpoint = externalEpoch.Checkpoint.ToArray();
                state = CopyState(databaseState);
                ExternalEpoch = new(
                    externalEpoch.Epoch,
                    externalEpoch.Generation,
                    checkpoint);
                DatabaseState = state;
            }
            catch
            {
                if (checkpoint is not null)
                {
                    CryptographicOperations.ZeroMemory(checkpoint);
                }

                if (state is not null)
                {
                    ZeroState(state);
                }

                throw;
            }
        }

        public PlayAuthorizationExternalEpoch ExternalEpoch { get; }
        public PlayAuthorizationPostgresState DatabaseState { get; }

        public void Dispose()
        {
            if (Interlocked.Exchange(ref _disposed, 1) != 0)
            {
                return;
            }

            CryptographicOperations.ZeroMemory(ExternalEpoch.Checkpoint);
            ZeroState(DatabaseState);
        }
    }

    private sealed class OwnedBaselineProviderCall : IDisposable
    {
        private int _disposed;

        public OwnedBaselineProviderCall(
            PlayAuthorizationCheckpointBaselineVerification source,
            PlayAuthorizationExternalEpoch externalEpoch)
        {
            PlayAuthorizationPostgresState? state = null;
            byte[]? payloadDigest = null;
            byte[]? checkpoint = null;
            try
            {
                state = CopyState(source.State);
                payloadDigest = source.PayloadDigestSha256.ToArray();
                checkpoint = externalEpoch.Checkpoint.ToArray();
                Verification = new(
                    source.BaselineId,
                    state,
                    source.DigestAlgorithm,
                    source.CanonicalVersion,
                    payloadDigest);
                ExternalEpoch = new(
                    externalEpoch.Epoch,
                    externalEpoch.Generation,
                    checkpoint);
            }
            catch
            {
                if (state is not null)
                {
                    ZeroState(state);
                }

                if (payloadDigest is not null)
                {
                    CryptographicOperations.ZeroMemory(payloadDigest);
                }

                if (checkpoint is not null)
                {
                    CryptographicOperations.ZeroMemory(checkpoint);
                }

                throw;
            }
        }

        public PlayAuthorizationCheckpointBaselineVerification Verification { get; }
        public PlayAuthorizationExternalEpoch ExternalEpoch { get; }

        public void Dispose()
        {
            if (Interlocked.Exchange(ref _disposed, 1) != 0)
            {
                return;
            }

            ZeroState(Verification.State);
            CryptographicOperations.ZeroMemory(Verification.PayloadDigestSha256);
            CryptographicOperations.ZeroMemory(ExternalEpoch.Checkpoint);
        }
    }

    private sealed class OwnedPublicationProviderCall : IDisposable
    {
        private int _disposed;

        public OwnedPublicationProviderCall(
            PlayAuthorizationCheckpointPublicationEnvelope source)
        {
            PlayAuthorizationPostgresState? state = null;
            byte[]? payloadDigest = null;
            try
            {
                state = CopyState(source.State);
                payloadDigest = source.PayloadDigestSha256.ToArray();
                Envelope = new(
                    source.PublicationId,
                    source.FencingToken,
                    state,
                    source.DigestAlgorithm,
                    source.CanonicalVersion,
                    payloadDigest);
            }
            catch
            {
                if (state is not null)
                {
                    ZeroState(state);
                }

                if (payloadDigest is not null)
                {
                    CryptographicOperations.ZeroMemory(payloadDigest);
                }

                throw;
            }
        }

        public PlayAuthorizationCheckpointPublicationEnvelope Envelope { get; }

        public void Dispose()
        {
            if (Interlocked.Exchange(ref _disposed, 1) != 0)
            {
                return;
            }

            ZeroState(Envelope.State);
            CryptographicOperations.ZeroMemory(Envelope.PayloadDigestSha256);
        }
    }
}

/// <summary>
/// Opaque, one-use provider builder retained by the trusted composition root. It owns construction
/// of the exact Microsoft DI provider that may materialize the dormant boundary without exposing
/// either the authority or a candidate-provider activation surface. The provider is bound before
/// it escapes this handle; copied descriptors can therefore never win the construction decision.
/// </summary>
public sealed class PlayAuthorizationPostgresDormantProviderActivationHandle
{
    private const int BuildStateUnused = 0;
    private const int BuildStateBuilding = 1;
    private const int BuildStateBound = 2;
    private const int BuildStateFailed = 3;

    private readonly IServiceCollection _services;
    private readonly object _providerConstructionLease;
    private Func<object, IServiceCollection, ServiceProviderOptions, ServiceProvider>? _build;
    private int _buildState = BuildStateUnused;

    internal PlayAuthorizationPostgresDormantProviderActivationHandle(
        IServiceCollection services,
        object providerConstructionLease,
        Func<object, IServiceCollection, ServiceProviderOptions, ServiceProvider> build)
    {
        _services = services ?? throw new ArgumentNullException(nameof(services));
        _providerConstructionLease = providerConstructionLease
            ?? throw new ArgumentNullException(nameof(providerConstructionLease));
        _build = build ?? throw new ArgumentNullException(nameof(build));
    }

    /// <summary>
    /// Builds and binds the terminal service collection exactly once. No provider supplied by a
    /// caller can participate in this decision. A failed or concurrent attempt is terminal for
    /// this handle and can never return a second provider.
    /// </summary>
    public ServiceProvider BuildServiceProvider(ServiceProviderOptions? options = null)
    {
        int observed = Interlocked.CompareExchange(
            ref _buildState,
            BuildStateBuilding,
            BuildStateUnused);
        if (observed != BuildStateUnused)
        {
            throw new InvalidOperationException(observed switch
            {
                BuildStateBuilding =>
                    "The Play authorization PostgreSQL provider build is already in progress.",
                BuildStateBound =>
                    "The Play authorization PostgreSQL provider was already built and bound.",
                BuildStateFailed =>
                    "The Play authorization PostgreSQL provider build already failed and cannot be replayed.",
                _ => "The Play authorization PostgreSQL provider build state is invalid."
            });
        }

        var effectiveOptions = new ServiceProviderOptions
        {
            ValidateOnBuild = options?.ValidateOnBuild ?? false,
            ValidateScopes = options?.ValidateScopes ?? false
        };
        try
        {
            Func<object, IServiceCollection, ServiceProviderOptions, ServiceProvider> build =
                Volatile.Read(ref _build)
                ?? throw new InvalidOperationException(
                    "The Play authorization PostgreSQL provider builder is unavailable.");
            ServiceProvider provider = build(
                _providerConstructionLease,
                _services,
                effectiveOptions);
            Volatile.Write(ref _buildState, BuildStateBound);
            _ = Interlocked.Exchange(ref _build, null);
            return provider;
        }
        catch
        {
            Volatile.Write(ref _buildState, BuildStateFailed);
            _ = Interlocked.Exchange(ref _build, null);
            throw;
        }
    }
}

/// <summary>
/// Mandatory, but dormant, composition boundary for the PostgreSQL authorization provider.
/// Program intentionally does not call this extension until the durability slice is activated.
/// The trusted composition root must register this terminally and use the returned handle to build
/// its provider before resolving hosted services or the dormant factory. The handle constructs and
/// binds the exact provider internally, so providers built from copied descriptors always fail.
/// </summary>
public static class PlayAuthorizationPostgresDormantProviderBoundary
{
    private static readonly object FactoryConstructionLease =
        new FactoryConstructionLeaseMarker();

    /// <summary>
    /// Captures an externally owned authority without adding it to the service collection.
    /// The caller remains responsible for disposing the authority.
    /// This terminal composition step must run after all other service registrations.
    /// </summary>
    public static PlayAuthorizationPostgresDormantProviderActivationHandle
        AddPlayAuthorizationPostgresDormantProviderBoundary(
        this IServiceCollection services,
        IPlayAuthorizationCheckpointAuthority externallyOwnedAuthority)
    {
        ArgumentNullException.ThrowIfNull(externallyOwnedAuthority);
        return AddBoundary(
            services,
            new BoundaryAuthoritySource(externallyOwnedAuthority));
    }

    /// <summary>
    /// Captures an authority construction factory without registering that factory or its result
    /// as a service. The dormant factory owns and disposes the single materialized authority.
    /// This terminal composition step must run after all other service registrations.
    /// </summary>
    public static PlayAuthorizationPostgresDormantProviderActivationHandle
        AddPlayAuthorizationPostgresDormantProviderBoundary(
        this IServiceCollection services,
        Func<IServiceProvider, IPlayAuthorizationCheckpointAuthority> authorityFactory)
    {
        ArgumentNullException.ThrowIfNull(authorityFactory);
        return AddBoundary(services, new BoundaryAuthoritySource(authorityFactory));
    }

    private static PlayAuthorizationPostgresDormantProviderActivationHandle AddBoundary(
        IServiceCollection services,
        BoundaryAuthoritySource authoritySource)
    {
        ArgumentNullException.ThrowIfNull(services);
        if (services.Any(static descriptor =>
                descriptor.ServiceType == typeof(PlayAuthorizationPostgresDormantFactory)))
        {
            throw new InvalidOperationException(
                "The Play authorization PostgreSQL provider boundary is already registered.");
        }

        PlayAuthorizationCheckpointProviderActivationContract
            .ValidateNoDirectRawAuthorityRegistration(services);
        ServiceDescriptor suppliedRegistryDescriptor =
            PlayAuthorizationCheckpointProviderActivationContract
                .ValidateRegistryRegistration(services);
        int registryIndex = services.IndexOf(suppliedRegistryDescriptor);
        var registry = new PlayAuthorizationCheckpointProviderCallRegistry();
        ServiceDescriptor registryDescriptor = ServiceDescriptor.Singleton(
            typeof(PlayAuthorizationCheckpointProviderCallRegistry),
            registry);
        services[registryIndex] = registryDescriptor;
        ServiceDescriptor providerIdentityDescriptor = ServiceDescriptor.Singleton(
            typeof(BoundProviderIdentity),
            static _ => new BoundProviderIdentity());
        services.Add(providerIdentityDescriptor);
        var lifecycle = new PlayAuthorizationCheckpointAuthorityLifecycle();
        var providerConstructionLease = new ProviderConstructionLeaseMarker();
        var registration = new BoundaryRegistration(
            services,
            authoritySource,
            registry,
            registryDescriptor,
            providerIdentityDescriptor,
            providerConstructionLease,
            lifecycle);
        ServiceDescriptor factoryDescriptor = ServiceDescriptor.Singleton(
            typeof(PlayAuthorizationPostgresDormantFactory),
            registration.CreateFactory);
        ServiceDescriptor startupDescriptor = ServiceDescriptor.Singleton(
            typeof(IHostedService),
            registration.CreateStartupValidation);
        services.Add(factoryDescriptor);
        services.Add(startupDescriptor);
        registration.Seal(factoryDescriptor, startupDescriptor);
        return new(
            services,
            providerConstructionLease,
            registration.BuildServiceProvider);
    }

    internal static void DemandFactoryConstructionLease(object candidate)
    {
        if (!ReferenceEquals(candidate, FactoryConstructionLease))
        {
            throw new InvalidOperationException(
                "Play authorization PostgreSQL objects can only be created by the dormant provider boundary.");
        }
    }

    private sealed class FactoryConstructionLeaseMarker
    {
    }

    private sealed class ProviderConstructionLeaseMarker
    {
    }

    /// <summary>
    /// Each built Microsoft DI provider materializes its own singleton marker, even when another
    /// service collection reuses the same descriptors. This is the provider-local identity bound
    /// by the trusted activation handle; factory delegates may receive the root scope facade rather
    /// than the public ServiceProvider object, so comparing IServiceProvider objects is incorrect.
    /// </summary>
    private sealed class BoundProviderIdentity
    {
    }

    private sealed class BoundaryAuthoritySource
    {
        public BoundaryAuthoritySource(
            IPlayAuthorizationCheckpointAuthority externallyOwnedAuthority)
        {
            Authority = externallyOwnedAuthority;
            OwnsAuthority = false;
        }

        public BoundaryAuthoritySource(
            Func<IServiceProvider, IPlayAuthorizationCheckpointAuthority> factory)
        {
            Factory = factory;
            OwnsAuthority = true;
        }

        public IPlayAuthorizationCheckpointAuthority? Authority { get; }
        public Func<IServiceProvider, IPlayAuthorizationCheckpointAuthority>? Factory { get; }
        public bool OwnsAuthority { get; }
    }

    private sealed class BoundaryRegistration :
        IPlayAuthorizationCheckpointAuthorityLifetime
    {
        private readonly object _gate = new();
        private readonly IServiceCollection _services;
        private readonly BoundaryAuthoritySource _source;
        private readonly PlayAuthorizationCheckpointProviderCallRegistry _registry;
        private readonly ServiceDescriptor _registryDescriptor;
        private readonly ServiceDescriptor _providerIdentityDescriptor;
        private readonly object _providerConstructionLease;
        private readonly PlayAuthorizationCheckpointAuthorityLifecycle _lifecycle;
        private readonly object _boundaryIdentity = new BoundaryIdentityMarker();
        private ServiceDescriptor[]? _sealedDescriptors;
        private ServiceDescriptor? _factoryDescriptor;
        private ServiceDescriptor? _startupDescriptor;
        private BoundProviderIdentity? _boundProviderIdentity;
        private IPlayAuthorizationCheckpointAuthority? _authority;
        private PlayAuthorizationPostgresDormantFactory? _factory;
        private bool _materializing;
        private bool _disposalClaimed;
        private readonly TaskCompletionSource _disposalCompleted = new(
            TaskCreationOptions.RunContinuationsAsynchronously);

        public BoundaryRegistration(
            IServiceCollection services,
            BoundaryAuthoritySource source,
            PlayAuthorizationCheckpointProviderCallRegistry registry,
            ServiceDescriptor registryDescriptor,
            ServiceDescriptor providerIdentityDescriptor,
            object providerConstructionLease,
            PlayAuthorizationCheckpointAuthorityLifecycle lifecycle)
        {
            _services = services;
            _source = source;
            _registry = registry;
            _registryDescriptor = registryDescriptor;
            _providerIdentityDescriptor = providerIdentityDescriptor;
            _providerConstructionLease = providerConstructionLease;
            _lifecycle = lifecycle;
            _authority = source.Authority;
        }

        public void Seal(
            ServiceDescriptor factoryDescriptor,
            ServiceDescriptor startupDescriptor)
        {
            lock (_gate)
            {
                if (_sealedDescriptors is not null)
                {
                    throw new InvalidOperationException(
                        "The Play authorization PostgreSQL boundary is already sealed.");
                }

                _factoryDescriptor = factoryDescriptor;
                _startupDescriptor = startupDescriptor;
                _sealedDescriptors = _services.ToArray();
            }
        }

        public ServiceProvider BuildServiceProvider(
            object providerConstructionLease,
            IServiceCollection services,
            ServiceProviderOptions options)
        {
            DemandProviderConstructionLease(providerConstructionLease);
            if (!ReferenceEquals(services, _services))
            {
                throw new InvalidOperationException(
                    "The provider builder received a foreign service collection.");
            }

            ServiceProvider? provider = null;
            try
            {
                lock (_gate)
                {
                    _lifecycle.DemandOpen();
                    ValidateSealedDescriptors();
                }

                provider = ServiceCollectionContainerBuilderExtensions.BuildServiceProvider(
                    services,
                    options);
                BindBuiltProvider(providerConstructionLease, provider);
                return provider;
            }
            catch (Exception exception)
            {
                var cleanupExceptions = new List<Exception>();
                if (provider is not null)
                {
                    try
                    {
                        provider.Dispose();
                    }
                    catch (Exception cleanupException)
                    {
                        cleanupExceptions.Add(cleanupException);
                    }
                }

                try
                {
                    FailProviderConstruction(providerConstructionLease);
                }
                catch (Exception cleanupException)
                {
                    cleanupExceptions.Add(cleanupException);
                }

                if (cleanupExceptions.Count != 0)
                {
                    cleanupExceptions.Insert(0, exception);
                    throw new AggregateException(
                        "The Play authorization PostgreSQL provider build failed and cleanup also reported failures.",
                        cleanupExceptions);
                }

                throw;
            }
        }

        private void BindBuiltProvider(
            object providerConstructionLease,
            IServiceProvider builtServiceProvider)
        {
            DemandProviderConstructionLease(providerConstructionLease);
            lock (_gate)
            {
                _lifecycle.DemandOpen();
                ValidateSealedDescriptors();
                if (_boundProviderIdentity is not null)
                {
                    throw new InvalidOperationException(
                        "The Play authorization PostgreSQL boundary already bound a provider.");
                }

                PlayAuthorizationCheckpointProviderCallRegistry[] registries =
                    builtServiceProvider
                        .GetServices<PlayAuthorizationCheckpointProviderCallRegistry>()
                        .ToArray();
                if (registries.Length != 1
                    || !ReferenceEquals(registries[0], _registry))
                {
                    throw new InvalidOperationException(
                        "The built provider does not contain the boundary-owned checkpoint call registry.");
                }

                BoundProviderIdentity[] providerIdentities = builtServiceProvider
                    .GetServices<BoundProviderIdentity>()
                    .ToArray();
                if (providerIdentities.Length != 1)
                {
                    throw new InvalidOperationException(
                        "The built provider does not contain exactly one boundary-owned provider identity.");
                }

                _boundProviderIdentity = providerIdentities[0];
            }
        }

        private void FailProviderConstruction(object providerConstructionLease)
        {
            DemandProviderConstructionLease(providerConstructionLease);
            lock (_gate)
            {
                DisposeAfterConstructionFailureSynchronously();
            }
        }

        private void DemandProviderConstructionLease(object candidate)
        {
            if (!ReferenceEquals(candidate, _providerConstructionLease))
            {
                throw new InvalidOperationException(
                    "The Play authorization PostgreSQL provider construction lease crossed its boundary.");
            }
        }

        public object CreateFactory(IServiceProvider serviceProvider)
        {
            lock (_gate)
            {
                _lifecycle.DemandOpen();
                ValidateSealedDescriptors();
                DemandBoundServiceProvider(serviceProvider);
                if (_factory is not null)
                {
                    return _factory;
                }

                try
                {
                    IPlayAuthorizationCheckpointAuthority authority =
                        GetOrCreateAuthority(serviceProvider);
                    PlayAuthorizationCheckpointProviderCallRegistry registry =
                        serviceProvider.GetRequiredService<
                            PlayAuthorizationCheckpointProviderCallRegistry>();
                    if (!ReferenceEquals(registry, _registry))
                    {
                        throw new InvalidOperationException(
                            "The checkpoint call registry crossed its dormant provider boundary.");
                    }

                    ValidateSealedDescriptors();
                    PlayAuthorizationCheckpointProviderActivation activation =
                        PlayAuthorizationCheckpointProviderActivation.Create(
                            FactoryConstructionLease,
                            authority,
                            registry,
                            _lifecycle);
                    _factory = PlayAuthorizationPostgresDormantFactory.Create(
                        FactoryConstructionLease,
                        _boundaryIdentity,
                        activation,
                        this);
                    return _factory;
                }
                catch
                {
                    DisposeAfterConstructionFailureSynchronously();
                    throw;
                }
            }
        }

        public object CreateStartupValidation(IServiceProvider serviceProvider)
        {
            lock (_gate)
            {
                _lifecycle.DemandOpen();
                ValidateSealedDescriptors();
                DemandBoundServiceProvider(serviceProvider);
                return new StartupValidation(this, serviceProvider);
            }
        }

        public void ValidateStartup(IServiceProvider serviceProvider)
        {
            lock (_gate)
            {
                _lifecycle.DemandOpen();
                ValidateSealedDescriptors();
                DemandBoundServiceProvider(serviceProvider);
            }

            PlayAuthorizationPostgresDormantFactory factory =
                serviceProvider.GetRequiredService<
                    PlayAuthorizationPostgresDormantFactory>();
            lock (_gate)
            {
                ValidateSealedDescriptors();
                if (!ReferenceEquals(_factory, factory))
                {
                    throw new InvalidOperationException(
                        "The Play authorization PostgreSQL factory descriptor was replaced or crossed a boundary.");
                }

                factory.DemandBoundaryIdentity(_boundaryIdentity);
            }
        }

        public void Dispose()
        {
            Task drained = _lifecycle.BeginClosing();
            if (!drained.IsCompletedSuccessfully)
            {
                throw new InvalidOperationException(
                    "Synchronous checkpoint-authority disposal cannot wait for active provider calls; call DisposeAsync to drain them.");
            }

            IPlayAuthorizationCheckpointAuthority? authority = null;
            bool ownsDisposal = false;
            Task completion;
            lock (_gate)
            {
                if (!_disposalClaimed)
                {
                    if (_source.OwnsAuthority
                        && _authority is IAsyncDisposable
                        && _authority is not IDisposable)
                    {
                        throw new InvalidOperationException(
                            "The checkpoint authority supports asynchronous disposal only; call DisposeAsync.");
                    }

                    _disposalClaimed = true;
                    ownsDisposal = true;
                    if (_source.OwnsAuthority)
                    {
                        authority = _authority;
                    }

                    _authority = null;
                }

                completion = _disposalCompleted.Task;
            }

            if (!ownsDisposal)
            {
                if (!completion.IsCompleted)
                {
                    throw new InvalidOperationException(
                        "Asynchronous checkpoint-authority disposal is already in progress.");
                }

                completion.GetAwaiter().GetResult();
                return;
            }

            try
            {
                if (authority is IDisposable disposable)
                {
                    disposable.Dispose();
                }

                _lifecycle.MarkClosed();
                _disposalCompleted.TrySetResult();
            }
            catch (Exception exception)
            {
                _disposalCompleted.TrySetException(exception);
                throw;
            }
        }

        public async ValueTask DisposeAsync()
        {
            await _lifecycle.BeginClosing().ConfigureAwait(false);
            IPlayAuthorizationCheckpointAuthority? authority = null;
            bool ownsDisposal = false;
            Task completion;
            lock (_gate)
            {
                if (!_disposalClaimed)
                {
                    _disposalClaimed = true;
                    ownsDisposal = true;
                    if (_source.OwnsAuthority)
                    {
                        authority = _authority;
                    }

                    _authority = null;
                }

                completion = _disposalCompleted.Task;
            }

            if (!ownsDisposal)
            {
                await completion.ConfigureAwait(false);
                return;
            }

            try
            {
                if (authority is IAsyncDisposable asyncDisposable)
                {
                    await asyncDisposable.DisposeAsync().ConfigureAwait(false);
                }
                else if (authority is IDisposable disposable)
                {
                    disposable.Dispose();
                }

                _lifecycle.MarkClosed();
                _disposalCompleted.TrySetResult();
            }
            catch (Exception exception)
            {
                _disposalCompleted.TrySetException(exception);
                throw;
            }
        }

        private IPlayAuthorizationCheckpointAuthority GetOrCreateAuthority(
            IServiceProvider serviceProvider)
        {
            if (_authority is not null)
            {
                return _authority;
            }

            if (_materializing)
            {
                throw new InvalidOperationException(
                    "The checkpoint authority construction factory recursively resolved its dormant boundary.");
            }

            Func<IServiceProvider, IPlayAuthorizationCheckpointAuthority> factory =
                _source.Factory
                ?? throw new InvalidOperationException(
                    "The checkpoint authority construction source is missing.");
            _materializing = true;
            try
            {
                _authority = factory(serviceProvider)
                    ?? throw new InvalidOperationException(
                        "The checkpoint authority construction factory returned null.");
                return _authority;
            }
            finally
            {
                _materializing = false;
            }
        }

        private void ValidateSealedDescriptors()
        {
            ServiceDescriptor[] expected = _sealedDescriptors
                ?? throw new InvalidOperationException(
                    "The Play authorization PostgreSQL boundary was not sealed.");
            if (_services.Count != expected.Length)
            {
                throw new InvalidOperationException(
                    "The Play authorization PostgreSQL service collection changed after boundary registration.");
            }

            for (int index = 0; index < expected.Length; index++)
            {
                if (!ReferenceEquals(_services[index], expected[index]))
                {
                    throw new InvalidOperationException(
                        "The Play authorization PostgreSQL service collection descriptors were replaced or reordered after boundary registration.");
                }
            }

            if (!expected.Any(descriptor =>
                    ReferenceEquals(_registryDescriptor, descriptor))
                || !expected.Any(descriptor =>
                    ReferenceEquals(_providerIdentityDescriptor, descriptor))
                || !expected.Any(descriptor =>
                    ReferenceEquals(_factoryDescriptor, descriptor))
                || !expected.Any(descriptor =>
                    ReferenceEquals(_startupDescriptor, descriptor)))
            {
                throw new InvalidOperationException(
                    "The Play authorization PostgreSQL boundary descriptor identities are invalid.");
            }
        }

        private void DemandBoundServiceProvider(IServiceProvider serviceProvider)
        {
            BoundProviderIdentity? intendedIdentity = _boundProviderIdentity;
            if (intendedIdentity is null)
            {
                throw new InvalidOperationException(
                    "The Play authorization PostgreSQL boundary must be explicitly activated before resolving its services.");
            }

            BoundProviderIdentity[] candidateIdentities = serviceProvider
                .GetServices<BoundProviderIdentity>()
                .ToArray();
            if (candidateIdentities.Length != 1
                || !ReferenceEquals(intendedIdentity, candidateIdentities[0]))
            {
                throw new InvalidOperationException(
                    "The Play authorization PostgreSQL boundary descriptors cannot be reused across service providers.");
            }
        }

        private void DisposeAfterConstructionFailureSynchronously()
        {
            _ = _lifecycle.BeginClosing();
            if (_disposalClaimed)
            {
                return;
            }

            _disposalClaimed = true;
            IPlayAuthorizationCheckpointAuthority? authority = _source.OwnsAuthority
                ? _authority
                : null;
            _authority = null;
            try
            {
                if (authority is IDisposable disposable)
                {
                    disposable.Dispose();
                }
                else if (authority is IAsyncDisposable asyncDisposable)
                {
                    Task.Run(async () =>
                            await asyncDisposable.DisposeAsync().ConfigureAwait(false))
                        .GetAwaiter()
                        .GetResult();
                }

                _lifecycle.MarkClosed();
                _disposalCompleted.TrySetResult();
            }
            catch (Exception exception)
            {
                _disposalCompleted.TrySetException(exception);
                throw;
            }
        }

        private sealed class BoundaryIdentityMarker
        {
        }

        private sealed class StartupValidation : IHostedService
        {
            private readonly BoundaryRegistration _registration;
            private readonly IServiceProvider _serviceProvider;

            public StartupValidation(
                BoundaryRegistration registration,
                IServiceProvider serviceProvider)
            {
                _registration = registration;
                _serviceProvider = serviceProvider;
            }

            public Task StartAsync(CancellationToken cancellationToken)
            {
                cancellationToken.ThrowIfCancellationRequested();
                _registration.ValidateStartup(_serviceProvider);
                return Task.CompletedTask;
            }

            public Task StopAsync(CancellationToken cancellationToken) =>
                Task.CompletedTask;
        }
    }
}

internal static class PlayAuthorizationCheckpointProviderActivationContract
{
    internal static void ValidateNoDirectRawAuthorityRegistration(
        IServiceCollection services)
    {
        if (services.Any(static descriptor =>
                TypeDirectlyExposesAuthority(descriptor.ServiceType)
                || TypeDirectlyExposesAuthority(
                    descriptor.IsKeyedService
                        ? descriptor.KeyedImplementationType
                        : descriptor.ImplementationType)
                || (descriptor.IsKeyedService
                        ? descriptor.KeyedImplementationInstance
                        : descriptor.ImplementationInstance)
                    is IPlayAuthorizationCheckpointAuthority))
        {
            throw new InvalidOperationException(
                "The raw checkpoint authority must be supplied directly to the trusted dormant boundary and cannot be registered directly in the service collection.");
        }
    }

    internal static ServiceDescriptor ValidateRegistryRegistration(
        IServiceCollection services)
    {
        ServiceDescriptor[] descriptors = services
            .Where(static descriptor =>
                descriptor.ServiceType
                    == typeof(PlayAuthorizationCheckpointProviderCallRegistry))
            .ToArray();
        if (descriptors.Length != 1
            || descriptors[0].Lifetime != ServiceLifetime.Singleton
            || descriptors[0].IsKeyedService)
        {
            throw new InvalidOperationException(
                "Play authorization checkpoint activation requires exactly one unkeyed singleton PlayAuthorizationCheckpointProviderCallRegistry registration.");
        }
        return descriptors[0];
    }

    private static bool TypeDirectlyExposesAuthority(Type? type) =>
        type is not null
        && (type == typeof(IPlayAuthorizationCheckpointAuthority)
            || typeof(IPlayAuthorizationCheckpointAuthority).IsAssignableFrom(type)
            || (type.ContainsGenericParameters
                && type.GetInterfaces().Any(static candidate =>
                    candidate == typeof(IPlayAuthorizationCheckpointAuthority)
                    || typeof(IPlayAuthorizationCheckpointAuthority)
                        .IsAssignableFrom(candidate))));
}

internal interface IPlayAuthorizationCheckpointAuthorityLifetime :
    IDisposable,
    IAsyncDisposable
{
}

public sealed class PlayAuthorizationPostgresDormantFactory :
    IPlayAuthorizationCheckpointPublicationReconciler,
    IDisposable,
    IAsyncDisposable
{
    private readonly object _gate = new();
    private readonly object _boundaryIdentity;
    private readonly PlayAuthorizationCheckpointProviderActivation _provider;
    private readonly IPlayAuthorizationCheckpointAuthorityLifetime _authorityLifetime;
    private readonly object _constructionLease;
    private NpgsqlPlayAuthorizationCheckpointPublicationReconciler? _reconciler;
    private NpgsqlDataSource? _reconcilerDataSource;
    private IPlayAuthorizationEpochAuthority? _reconcilerEpochAuthority;
    private PlayAuthorizationCheckpointPublicationPolicy? _reconcilerPolicy;
    private TimeProvider? _reconcilerTimeProvider;

    private PlayAuthorizationPostgresDormantFactory(
        object boundaryIdentity,
        PlayAuthorizationCheckpointProviderActivation provider,
        IPlayAuthorizationCheckpointAuthorityLifetime authorityLifetime)
    {
        _boundaryIdentity = boundaryIdentity
            ?? throw new ArgumentNullException(nameof(boundaryIdentity));
        _provider = provider ?? throw new ArgumentNullException(nameof(provider));
        _authorityLifetime = authorityLifetime
            ?? throw new ArgumentNullException(nameof(authorityLifetime));
        _constructionLease = new ConstructionLease(this, provider);
    }

    internal static PlayAuthorizationPostgresDormantFactory Create(
        object boundaryLease,
        object boundaryIdentity,
        PlayAuthorizationCheckpointProviderActivation provider,
        IPlayAuthorizationCheckpointAuthorityLifetime authorityLifetime)
    {
        PlayAuthorizationPostgresDormantProviderBoundary
            .DemandFactoryConstructionLease(boundaryLease);
        return new(boundaryIdentity, provider, authorityLifetime);
    }

    internal void DemandBoundaryIdentity(object candidate)
    {
        if (!ReferenceEquals(_boundaryIdentity, candidate))
        {
            throw new InvalidOperationException(
                "The Play authorization PostgreSQL factory belongs to another dormant boundary.");
        }
    }

    internal static void DemandConstructionLease(
        object candidate,
        PlayAuthorizationCheckpointProviderActivation provider)
    {
        if (candidate is not ConstructionLease lease
            || !ReferenceEquals(lease.Owner._constructionLease, candidate)
            || !ReferenceEquals(lease.Provider, provider)
            || !ReferenceEquals(lease.Owner._provider, provider))
        {
            throw new InvalidOperationException(
                "Play authorization PostgreSQL construction requires its owning dormant factory lease and activation.");
        }
    }

    internal static void DemandOwnedReconciler(
        object candidate,
        PlayAuthorizationCheckpointProviderActivation provider,
        NpgsqlPlayAuthorizationCheckpointPublicationReconciler reconciler)
    {
        DemandConstructionLease(candidate, provider);
        var lease = (ConstructionLease)candidate;
        lock (lease.Owner._gate)
        {
            if (!ReferenceEquals(lease.Owner._reconciler, reconciler))
            {
                throw new InvalidOperationException(
                    "Play authorization PostgreSQL objects must share their dormant factory's single reconciler.");
            }
        }
    }

    public PlayAuthorizationCheckpointProviderCallDiagnostics ProviderCallDiagnostics
    {
        get
        {
            _provider.DemandOpen();
            return _provider.Diagnostics;
        }
    }

    public PlayAuthorizationPostgresDormantFactory BindCheckpointReconciliation(
        NpgsqlDataSource dataSource,
        IPlayAuthorizationEpochAuthority epochAuthority,
        PlayAuthorizationCheckpointPublicationPolicy policy,
        TimeProvider timeProvider)
    {
        _provider.DemandOpen();
        _ = GetOrCreateReconciler(dataSource, epochAuthority, policy, timeProvider);
        return this;
    }

    public Task<PlayAuthorizationCheckpointReconciliationResult> ReconcileAsync(
        int maximumPublications,
        CancellationToken cancellationToken = default)
    {
        _provider.DemandOpen();
        return GetBoundReconciler().ReconcileAsync(maximumPublications, cancellationToken);
    }

    public Task<bool> IsPublishedAsync(
        long auditSequence,
        long epoch,
        long generation,
        CancellationToken cancellationToken = default)
    {
        _provider.DemandOpen();
        return GetBoundReconciler().IsPublishedAsync(
            auditSequence,
            epoch,
            generation,
            cancellationToken);
    }

    public NpgsqlPlayAuthorizationRepository CreateRepository(
        NpgsqlDataSource dataSource,
        IPlayAuthorizationPostgresUnitOfWorkFactory unitOfWorkFactory,
        IPlayAuthorizationEpochAuthority epochAuthority,
        IPlayAuthorizationHmacAuthority hmacAuthority,
        PlayAuthorizationCheckpointPublicationPolicy publicationPolicy,
        IPlayAuthorizationReceiptCipher receiptCipher,
        IPlayAuthorizationCommitObserver commitObserver,
        TimeProvider timeProvider)
    {
        _provider.DemandOpen();
        NpgsqlPlayAuthorizationCheckpointPublicationReconciler reconciler =
            GetOrCreateReconciler(
                dataSource,
                epochAuthority,
                publicationPolicy,
                timeProvider);
        return NpgsqlPlayAuthorizationRepository.Create(
            _constructionLease,
            _provider,
            dataSource,
            unitOfWorkFactory,
            epochAuthority,
            hmacAuthority,
            reconciler,
            receiptCipher,
            commitObserver,
            timeProvider);
    }

    public PlayAuthorizationPostgresReadinessProbe CreateReadinessProbe(
        NpgsqlDataSource dataSource,
        PlayAuthorizationPostgresMigrator migrator,
        IPlayAuthorizationEpochAuthority epochAuthority,
        PlayAuthorizationCheckpointPublicationPolicy publicationPolicy,
        PlayAuthorizationReplaySafetyPolicy replaySafetyPolicy,
        TimeProvider timeProvider)
    {
        _provider.DemandOpen();
        NpgsqlPlayAuthorizationCheckpointPublicationReconciler reconciler =
            GetOrCreateReconciler(
                dataSource,
                epochAuthority,
                publicationPolicy,
                timeProvider);
        return PlayAuthorizationPostgresReadinessProbe.Create(
            _constructionLease,
            _provider,
            dataSource,
            migrator,
            epochAuthority,
            reconciler,
            replaySafetyPolicy,
            timeProvider);
    }

    private NpgsqlPlayAuthorizationCheckpointPublicationReconciler GetOrCreateReconciler(
        NpgsqlDataSource dataSource,
        IPlayAuthorizationEpochAuthority epochAuthority,
        PlayAuthorizationCheckpointPublicationPolicy policy,
        TimeProvider timeProvider)
    {
        _provider.DemandOpen();
        ArgumentNullException.ThrowIfNull(dataSource);
        ArgumentNullException.ThrowIfNull(epochAuthority);
        ArgumentNullException.ThrowIfNull(policy);
        ArgumentNullException.ThrowIfNull(timeProvider);
        lock (_gate)
        {
            if (_reconciler is null)
            {
                _reconciler =
                    NpgsqlPlayAuthorizationCheckpointPublicationReconciler.Create(
                        _constructionLease,
                        _provider,
                        dataSource,
                        epochAuthority,
                        policy,
                        timeProvider);
                _reconcilerDataSource = dataSource;
                _reconcilerEpochAuthority = epochAuthority;
                _reconcilerPolicy = policy;
                _reconcilerTimeProvider = timeProvider;
                return _reconciler;
            }

            if (!ReferenceEquals(_reconcilerDataSource, dataSource)
                || !ReferenceEquals(_reconcilerEpochAuthority, epochAuthority)
                || !ReferenceEquals(_reconcilerPolicy, policy)
                || !ReferenceEquals(_reconcilerTimeProvider, timeProvider))
            {
                throw new InvalidOperationException(
                    "A dormant Play authorization PostgreSQL factory cannot be rebound to a different reconciler configuration.");
            }

            return _reconciler;
        }
    }

    private NpgsqlPlayAuthorizationCheckpointPublicationReconciler GetBoundReconciler()
    {
        _provider.DemandOpen();
        lock (_gate)
        {
            return _reconciler
                ?? throw new InvalidOperationException(
                    "The dormant Play authorization PostgreSQL factory has not been bound to a reconciler configuration.");
        }
    }

    private sealed record ConstructionLease(
        PlayAuthorizationPostgresDormantFactory Owner,
        PlayAuthorizationCheckpointProviderActivation Provider);

    void IDisposable.Dispose() => _authorityLifetime.Dispose();

    ValueTask IAsyncDisposable.DisposeAsync() =>
        _authorityLifetime.DisposeAsync();
}
