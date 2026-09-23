using System.Buffers.Binary;
using System.Security.Cryptography;
using Chummer.Run.Api.Services.InstallLinking.Postgres;
using Chummer.Storage.Teable;

namespace Chummer.Run.Api.Services.Teable;

/// <summary>
/// Teable primary implementation of the existing protected account snapshot
/// contract. The historical DTO names do not make this PostgreSQL evidence.
/// Does not implement IInstallLinkingSnapshotReadFence: Rook remains unavailable.
/// </summary>
internal sealed class TeableInstallLinkingSnapshotAuthority(TeableRevisionStore store)
    : IInstallLinkingSnapshotAuthority
{
    private const string Stream = "install-linking";
    private const int HeaderLength = 48;

    public async Task<InstallLinkingAuthoritativeEnvelope> ReadCurrentAsync(CancellationToken cancellationToken = default)
    {
        var head = await store.ReadAsync(Stream, cancellationToken);
        try { return Decode(head); }
        finally { if (head is not null) CryptographicOperations.ZeroMemory(head.Bytes); }
    }

    public async Task<InstallLinkingPostgresReadiness> CheckReadinessAsync(CancellationToken cancellationToken = default)
    {
        using var head = await ReadCurrentForReadinessAsync(cancellationToken);
        return new(true, "teable_snapshot_authority_ready", 1, 1, head.Generation, DateTimeOffset.UtcNow);
    }

    // Schema and the validated current envelope are one readiness observation.
    // Return its envelope to the coordinator instead of downloading the same
    // protected payload a second time merely to compare the bound head.
    internal async Task<InstallLinkingAuthoritativeEnvelope> ReadCurrentForReadinessAsync(
        CancellationToken cancellationToken = default)
    {
        await store.VerifySchemaAsync(cancellationToken);
        return await ReadCurrentAsync(cancellationToken);
    }

    public async Task<InstallLinkingEnvelopeCompareExchangeResult> CompareExchangeAsync(
        InstallLinkingEnvelopeCompareExchangeRequest request, CancellationToken cancellationToken = default)
    {
        Validate(request);
        TeableRevisionStore.Head? before = null, after = null;
        byte[]? encoded = null;
        try
        {
            before = await store.ReadAsync(Stream, cancellationToken);
            using var current = Decode(before);
            if (MatchesCommitted(current, request))
                return new(InstallLinkingEnvelopeCommitDisposition.AlreadyCommitted, current.Clone(), "teable_already_committed");
            if (current.Generation != request.ExpectedGeneration || current.CommitId != request.ExpectedCommitId
                || !Same(current.EnvelopeSha256, request.ExpectedEnvelopeSha256))
                return new(InstallLinkingEnvelopeCommitDisposition.Conflict, current.Clone(), "teable_compare_exchange_conflict");

            encoded = new byte[HeaderLength + request.ProtectedEnvelope.Length];
            "CTS1"u8.CopyTo(encoded);
            BinaryPrimitives.WriteInt32LittleEndian(encoded.AsSpan(4), request.EnvelopeVersion);
            BinaryPrimitives.WriteInt64LittleEndian(encoded.AsSpan(8), DateTimeOffset.UtcNow.Ticks);
            request.SnapshotSha256.CopyTo(encoded, 16);
            request.ProtectedEnvelope.CopyTo(encoded, HeaderLength);
            after = await store.CompareExchangeAsync(Stream, before, request.CommitId, encoded, cancellationToken);
            return new(InstallLinkingEnvelopeCommitDisposition.Applied, Decode(after), "teable_committed");
        }
        catch (TeableRevisionConflictException)
        {
            return new(InstallLinkingEnvelopeCommitDisposition.Conflict, null, "teable_compare_exchange_conflict");
        }
        catch (Exception error) when (error is IOException or HttpRequestException or OperationCanceledException)
        {
            // A request might have committed. Never convert ambiguity into a safe
            // retry or fall back to an older local mirror; restart/read the authority.
            return new(InstallLinkingEnvelopeCommitDisposition.Ambiguous, null, "teable_reconciliation_required");
        }
        finally
        {
            if (encoded is not null) CryptographicOperations.ZeroMemory(encoded);
            if (before is not null) CryptographicOperations.ZeroMemory(before.Bytes);
            if (after is not null) CryptographicOperations.ZeroMemory(after.Bytes);
        }
    }

    private static InstallLinkingAuthoritativeEnvelope Decode(TeableRevisionStore.Head? head)
    {
        if (head is null) return new(0, null, null, null, null, null, DateTimeOffset.UnixEpoch);
        ReadOnlySpan<byte> bytes = head.Bytes;
        if (bytes.Length <= HeaderLength || bytes.Length - HeaderLength > InstallLinkingPostgresDurabilityInvariants.MaximumProtectedEnvelopeBytes
            || !bytes[..4].SequenceEqual("CTS1"u8)
            || BinaryPrimitives.ReadInt32LittleEndian(bytes[4..]) != InstallLinkingPostgresDurabilityInvariants.ProtectedEnvelopeVersion)
            throw new InvalidDataException("Invalid Teable account envelope.");
        long ticks = BinaryPrimitives.ReadInt64LittleEndian(bytes[8..]);
        if (ticks <= DateTimeOffset.UnixEpoch.Ticks || ticks > DateTimeOffset.MaxValue.Ticks)
            throw new InvalidDataException("Invalid Teable account envelope time.");
        byte[] envelope = bytes[HeaderLength..].ToArray();
        return new(head.Revision, head.Commit, InstallLinkingPostgresDurabilityInvariants.ProtectedEnvelopeVersion,
            bytes.Slice(16, 32).ToArray(), SHA256.HashData(envelope), envelope, new DateTimeOffset(ticks, TimeSpan.Zero));
    }

    private static void Validate(InstallLinkingEnvelopeCompareExchangeRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        if (request.ExpectedGeneration < 0 || request.ExpectedGeneration >= 9_007_199_254_740_991L
            || request.NextGeneration != request.ExpectedGeneration + 1 || request.CommitId == Guid.Empty
            || request.ExpectedGeneration == 0 && (request.ExpectedCommitId is not null || request.ExpectedEnvelopeSha256 is not null)
            || request.ExpectedGeneration > 0 && (request.ExpectedCommitId is null || request.ExpectedCommitId == Guid.Empty
                || request.ExpectedEnvelopeSha256 is not { Length: 32 })
            || request.EnvelopeVersion != InstallLinkingPostgresDurabilityInvariants.ProtectedEnvelopeVersion
            || request.SnapshotSha256 is not { Length: 32 } || request.EnvelopeSha256 is not { Length: 32 }
            || request.ProtectedEnvelope is not { Length: > 0 and <= InstallLinkingPostgresDurabilityInvariants.MaximumProtectedEnvelopeBytes }
            || !CryptographicOperations.FixedTimeEquals(SHA256.HashData(request.ProtectedEnvelope), request.EnvelopeSha256))
            throw new InvalidDataException("Invalid Teable account commit request.");
    }

    private static bool MatchesCommitted(InstallLinkingAuthoritativeEnvelope current, InstallLinkingEnvelopeCompareExchangeRequest request)
        => current.Generation == request.NextGeneration && current.CommitId == request.CommitId
            && current.EnvelopeVersion == request.EnvelopeVersion && Same(current.SnapshotSha256, request.SnapshotSha256)
            && Same(current.EnvelopeSha256, request.EnvelopeSha256);
    private static bool Same(byte[]? a, byte[]? b)
        => a is null ? b is null : b is not null && CryptographicOperations.FixedTimeEquals(a, b);
}
