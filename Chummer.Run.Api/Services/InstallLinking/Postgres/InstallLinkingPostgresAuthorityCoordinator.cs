using System.Security.Cryptography;
using Chummer.Run.Api.Services.Teable;
using Npgsql;

namespace Chummer.Run.Api.Services.InstallLinking.Postgres;

/// <summary>
/// Couples every InstallLinking mutation and readiness decision to the same primary
/// authority instance. Readiness is green only while the live database head exactly matches
/// the head whose protected bytes were durably mirrored and loaded into this process.
/// The historical class name is retained for source compatibility. Teable does not
/// acquire PostgreSQL's optional read fence and has separately named status codes.
/// </summary>
public sealed class InstallLinkingPostgresAuthorityCoordinator :
    IInstallLinkingSnapshotAuthority,
    IInstallLinkingRollbackAuthorityReadinessProbe
{
    private static readonly TimeSpan ReadinessDeadline = TimeSpan.FromSeconds(5);
    private readonly IInstallLinkingSnapshotAuthority _authority;
    private readonly string _backend;
    private readonly object _bindingGate = new();
    private BoundAuthorityHead? _boundHead;

    public InstallLinkingPostgresAuthorityCoordinator(
        IInstallLinkingSnapshotAuthority authority, string backend = "postgres")
    {
        _authority = authority ?? throw new ArgumentNullException(nameof(authority));
        _backend = backend is "postgres" or "teable" ? backend
            : throw new ArgumentException("Unsupported install-linking authority backend.", nameof(backend));
    }

    private string Code(string suffix) => _backend + "_" + suffix;

    internal void EnsureAccountErasureSupported()
    {
        // The Teable adapter appends snapshots. Replacing the current snapshot
        // cannot erase its older protected payloads while the keyring is retained.
        if (_backend == "teable" || _authority is TeableInstallLinkingSnapshotAuthority)
            throw new InvalidOperationException("Primary install-linking erasure requires historical payload cleanup before activation.");
    }

    public Task<InstallLinkingAuthoritativeEnvelope> ReadCurrentAsync(
        CancellationToken cancellationToken = default)
        => _authority.ReadCurrentAsync(cancellationToken);

    public Task<InstallLinkingEnvelopeCompareExchangeResult> CompareExchangeAsync(
        InstallLinkingEnvelopeCompareExchangeRequest request,
        CancellationToken cancellationToken = default)
        => _authority.CompareExchangeAsync(request, cancellationToken);

    public Task<InstallLinkingPostgresReadiness> CheckReadinessAsync(
        CancellationToken cancellationToken = default)
        => _authority.CheckReadinessAsync(cancellationToken);

    /// <summary>
    /// Runs a bounded synchronous local read only while PostgreSQL excludes concurrent CAS
    /// and the current bound mirror exactly matches that locked head. The caller must already
    /// hold the local InstallLinkingStore.Gate; order is local store gate, PostgreSQL row,
    /// then this binding/snapshot gate. The callback must not acquire a local writer gate,
    /// mutate state, or perform HTTP/async work. It may execute on another thread, so it must
    /// not reenter a thread-owned local gate. Its synchronous work cannot be preempted.
    /// Success describes this capture only, not future revocation safety or user authority.
    /// </summary>
    public InstallLinkingRollbackAuthorityReadiness ReadBoundLocalMirror(
        Action capture,
        CancellationToken cancellationToken = default)
    {
        InstallLinkingReadFenceCallback.Validate(capture);
        if (_authority is not IInstallLinkingSnapshotReadFence fence)
        {
            return new(false, Code("read_fence_unavailable"));
        }

        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(ReadinessDeadline);
        var result = new InstallLinkingRollbackAuthorityReadiness(
            false,
            Code("authority_not_bound"));
        try
        {
            fence.ReadFencedAsync(current =>
            {
                lock (_bindingGate)
                {
                    deadline.Token.ThrowIfCancellationRequested();
                    if (_boundHead is null)
                    {
                        return;
                    }

                    if (!_boundHead.Matches(current))
                    {
                        result = new(false, Code("authority_head_mismatch"));
                        return;
                    }

                    capture();
                    deadline.Token.ThrowIfCancellationRequested();
                    result = new(true, Code("authority_fenced"));
                }
            }, deadline.Token).GetAwaiter().GetResult();
            deadline.Token.ThrowIfCancellationRequested();
            return result;
        }
        catch (Exception exception) when (exception is
            NpgsqlException or
            IOException or
            HttpRequestException or
            TimeoutException or
            OperationCanceledException)
        {
            return new(false, Code("unavailable"));
        }
        catch (Exception exception) when (exception is
            InvalidDataException or
            CryptographicException or
            InvalidOperationException)
        {
            return new(false, Code("authority_invalid"));
        }
    }

    /// <summary>
    /// Binds readiness only after the caller has validated, loaded, and durably mirrored the
    /// exact authority envelope. Calling this before the mirror is durable would create a
    /// readiness-only authority and is intentionally not supported by this type.
    /// </summary>
    public void BindValidatedLocalMirror(InstallLinkingAuthoritativeEnvelope envelope)
    {
        ArgumentNullException.ThrowIfNull(envelope);
        BoundAuthorityHead next = BoundAuthorityHead.FromEnvelope(envelope);
        lock (_bindingGate)
        {
            _boundHead = next;
        }
    }

    public InstallLinkingRollbackAuthorityReadiness Evaluate()
    {
        BoundAuthorityHead? expected;
        lock (_bindingGate)
        {
            expected = _boundHead?.Copy();
        }

        if (expected is null)
        {
            return new(false, Code("authority_not_bound"));
        }

        using var deadline = new CancellationTokenSource(ReadinessDeadline);
        try
        {
            InstallLinkingPostgresReadiness readiness = CheckReadinessAsync(deadline.Token)
                .GetAwaiter()
                .GetResult();
            if (!readiness.Ready)
            {
                return new(false, readiness.Code);
            }

            using InstallLinkingAuthoritativeEnvelope current = ReadCurrentAsync(deadline.Token)
                .GetAwaiter()
                .GetResult();
            return expected.Matches(current)
                ? new(true, Code("authority_bound"))
                : new(false, Code("authority_head_mismatch"));
        }
        catch (Exception exception) when (exception is
            NpgsqlException or
            IOException or
            HttpRequestException or
            TimeoutException or
            OperationCanceledException)
        {
            return new(false, Code("unavailable"));
        }
        catch (Exception exception) when (exception is
            InvalidDataException or
            CryptographicException or
            InvalidOperationException)
        {
            return new(false, Code("authority_invalid"));
        }
    }

    private sealed record BoundAuthorityHead(
        long Generation,
        Guid? CommitId,
        int? EnvelopeVersion,
        byte[]? SnapshotSha256,
        byte[]? EnvelopeSha256)
    {
        public static BoundAuthorityHead FromEnvelope(
            InstallLinkingAuthoritativeEnvelope envelope)
        {
            if (envelope.Generation == 0)
            {
                if (!envelope.IsEmpty
                    || envelope.CommitId is not null
                    || envelope.EnvelopeVersion is not null
                    || envelope.SnapshotSha256 is not null
                    || envelope.EnvelopeSha256 is not null
                    || envelope.ProtectedEnvelope is not null)
                {
                    throw new InvalidDataException(
                        "The empty InstallLinking authority binding is invalid.");
                }

                return new(0, null, null, null, null);
            }

            if (envelope.Generation < 1
                || envelope.CommitId is null
                || envelope.CommitId == Guid.Empty
                || envelope.EnvelopeVersion
                    != InstallLinkingPostgresDurabilityInvariants.ProtectedEnvelopeVersion
                || envelope.SnapshotSha256 is not
                    { Length: InstallLinkingPostgresDurabilityInvariants.Sha256SizeInBytes }
                || envelope.EnvelopeSha256 is not
                    { Length: InstallLinkingPostgresDurabilityInvariants.Sha256SizeInBytes }
                || envelope.ProtectedEnvelope is not
                    { Length: > 0 and <= InstallLinkingPostgresDurabilityInvariants.MaximumProtectedEnvelopeBytes })
            {
                throw new InvalidDataException(
                    "The InstallLinking authority binding is invalid.");
            }

            return new(
                envelope.Generation,
                envelope.CommitId,
                envelope.EnvelopeVersion,
                envelope.SnapshotSha256.ToArray(),
                envelope.EnvelopeSha256.ToArray());
        }

        public BoundAuthorityHead Copy()
            => new(
                Generation,
                CommitId,
                EnvelopeVersion,
                SnapshotSha256?.ToArray(),
                EnvelopeSha256?.ToArray());

        public bool Matches(InstallLinkingAuthoritativeEnvelope envelope)
            => Generation == envelope.Generation
               && CommitId == envelope.CommitId
               && EnvelopeVersion == envelope.EnvelopeVersion
               && FixedEquals(SnapshotSha256, envelope.SnapshotSha256)
               && FixedEquals(EnvelopeSha256, envelope.EnvelopeSha256);

        private static bool FixedEquals(byte[]? left, byte[]? right)
        {
            if (left is null || right is null)
            {
                return left is null && right is null;
            }

            return left.Length == right.Length
                   && CryptographicOperations.FixedTimeEquals(left, right);
        }
    }
}

/// <summary>
/// A typed owner for the InstallLinking pool prevents it from colliding with other bounded
/// contexts that also use NpgsqlDataSource. The DI container disposes this pool at shutdown.
/// </summary>
internal sealed class InstallLinkingPostgresRuntime : IAsyncDisposable
{
    public InstallLinkingPostgresRuntime(string connectionString)
    {
        DataSource = NpgsqlDataSource.Create(connectionString);
    }

    public NpgsqlDataSource DataSource { get; }

    public ValueTask DisposeAsync() => DataSource.DisposeAsync();
}
