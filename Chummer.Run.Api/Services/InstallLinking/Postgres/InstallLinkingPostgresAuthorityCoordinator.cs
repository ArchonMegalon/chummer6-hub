using System.Security.Cryptography;
using Npgsql;

namespace Chummer.Run.Api.Services.InstallLinking.Postgres;

/// <summary>
/// Couples every InstallLinking mutation and readiness decision to the same PostgreSQL
/// authority instance. Readiness is green only while the live database head exactly matches
/// the head whose protected bytes were durably mirrored and loaded into this process.
/// </summary>
public sealed class InstallLinkingPostgresAuthorityCoordinator :
    IInstallLinkingSnapshotAuthority,
    IInstallLinkingRollbackAuthorityReadinessProbe
{
    private static readonly TimeSpan ReadinessDeadline = TimeSpan.FromSeconds(5);
    private readonly IInstallLinkingSnapshotAuthority _authority;
    private readonly object _bindingGate = new();
    private BoundAuthorityHead? _boundHead;

    public InstallLinkingPostgresAuthorityCoordinator(
        IInstallLinkingSnapshotAuthority authority)
    {
        _authority = authority ?? throw new ArgumentNullException(nameof(authority));
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
            return new(false, "postgres_authority_not_bound");
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
                ? new(true, "postgres_authority_bound")
                : new(false, "postgres_authority_head_mismatch");
        }
        catch (Exception exception) when (exception is
            NpgsqlException or
            IOException or
            TimeoutException or
            OperationCanceledException)
        {
            return new(false, "postgres_unavailable");
        }
        catch (Exception exception) when (exception is
            InvalidDataException or
            CryptographicException or
            InvalidOperationException)
        {
            return new(false, "postgres_authority_invalid");
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
