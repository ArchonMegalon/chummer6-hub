using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text;

namespace Chummer.Run.Api.Services.Community.Postgres;

/// <summary>
/// Canonical checkpoint payload v1. The byte stream is the length-prefixed ASCII domain tag,
/// a big-endian 32-bit version, the length-prefixed UTF-8 algorithm name, a network-order UUID,
/// four big-endian 64-bit values (epoch, generation, sequence, UTC ticks), then length-prefixed
/// audit-HMAC and external-checkpoint bytes. The ephemeral fencing token is deliberately excluded.
/// </summary>
public static class PlayAuthorizationCheckpointCanonicalizer
{
    private const string DomainTag = "chummer.play-authorization.checkpoint-payload";
    private const int MaximumAlgorithmBytes = 32;
    private const int MaximumExternalCheckpointBytes = 4096;

    public static byte[] ComputePayloadDigest(
        Guid publicationId,
        PlayAuthorizationPostgresState state,
        string digestAlgorithm,
        int canonicalVersion)
    {
        ArgumentNullException.ThrowIfNull(state);
        if (publicationId == Guid.Empty
            || state.Epoch <= 0
            || state.Generation <= 0
            || state.AuditHeadSequence < 0
            || state.AuditHeadHmac is null
            || state.AuditHeadHmac.Length
                != PlayAuthorizationPostgresDurabilityInvariants.HmacSizeInBytes
            || state.ExternalCheckpoint is null
            || state.ExternalCheckpoint.Length is < 1 or > MaximumExternalCheckpointBytes
            || !string.Equals(
                digestAlgorithm,
                PlayAuthorizationPostgresDurabilityInvariants.CheckpointDigestAlgorithm,
                StringComparison.Ordinal)
            || canonicalVersion != PlayAuthorizationPostgresDurabilityInvariants.CheckpointCanonicalVersion)
        {
            throw new ArgumentException("The checkpoint payload cannot be canonicalized.", nameof(state));
        }

        byte[] domain = Encoding.ASCII.GetBytes(DomainTag);
        byte[] algorithm = Encoding.UTF8.GetBytes(digestAlgorithm);
        byte[] uuid = new byte[16];
        try
        {
            if (algorithm.Length is < 1 or > MaximumAlgorithmBytes)
            {
                throw new ArgumentException(
                    "The checkpoint digest algorithm is invalid.",
                    nameof(digestAlgorithm));
            }

            using IncrementalHash hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            AppendLengthPrefixed(hash, domain);
            AppendInt32(hash, canonicalVersion);
            AppendLengthPrefixed(hash, algorithm);

            if (!publicationId.TryWriteBytes(uuid, bigEndian: true, out int uuidBytes)
                || uuidBytes != uuid.Length)
            {
                throw new InvalidOperationException("The checkpoint publication UUID cannot be encoded.");
            }

            hash.AppendData(uuid);
            AppendInt64(hash, state.Epoch);
            AppendInt64(hash, state.Generation);
            AppendInt64(hash, state.AuditHeadSequence);
            AppendInt64(hash, state.ClockHighWaterUtc.UtcDateTime.Ticks);
            AppendLengthPrefixed(hash, state.AuditHeadHmac);
            AppendLengthPrefixed(hash, state.ExternalCheckpoint);

            return hash.GetHashAndReset();
        }
        finally
        {
            CryptographicOperations.ZeroMemory(domain);
            CryptographicOperations.ZeroMemory(algorithm);
            CryptographicOperations.ZeroMemory(uuid);
        }
    }

    private static void AppendLengthPrefixed(IncrementalHash hash, ReadOnlySpan<byte> value)
    {
        AppendInt32(hash, value.Length);
        hash.AppendData(value);
    }

    private static void AppendInt32(IncrementalHash hash, int value)
    {
        Span<byte> bytes = stackalloc byte[sizeof(int)];
        BinaryPrimitives.WriteInt32BigEndian(bytes, value);
        hash.AppendData(bytes);
        CryptographicOperations.ZeroMemory(bytes);
    }

    private static void AppendInt64(IncrementalHash hash, long value)
    {
        Span<byte> bytes = stackalloc byte[sizeof(long)];
        BinaryPrimitives.WriteInt64BigEndian(bytes, value);
        hash.AppendData(bytes);
        CryptographicOperations.ZeroMemory(bytes);
    }
}

/// <summary>
/// Canonical audit payload v1. The byte stream is a length-prefixed ASCII domain tag, a
/// big-endian 32-bit version, a network-order audit event UUID, three big-endian 64-bit values
/// (epoch, generation, sequence), four length-prefixed UTF-8 identity fields, then length-prefixed
/// scope, idempotency-key, request-fingerprint, and plaintext-response SHA-256 values. Only the
/// response digest is committed; plaintext is never stored.
/// </summary>
public static class PlayAuthorizationAuditPayloadCanonicalizer
{
    private const string DomainTag = "chummer.play-authorization.audit-payload";
    private const int MaximumIdentityBytes = 512;

    public static byte[] ComputePayloadDigest(
        Guid eventId,
        long epoch,
        long generation,
        long sequence,
        string operation,
        string aggregateKind,
        string aggregateId,
        string actorDigestSha256,
        ReadOnlySpan<byte> scopeSha256,
        ReadOnlySpan<byte> idempotencyKeySha256,
        ReadOnlySpan<byte> requestFingerprintSha256,
        ReadOnlySpan<byte> responsePlaintextSha256,
        int canonicalVersion)
    {
        if (eventId == Guid.Empty
            || epoch <= 0
            || generation <= 0
            || sequence <= 0
            || canonicalVersion
                != PlayAuthorizationPostgresDurabilityInvariants.AuditPayloadCanonicalVersion
            || !IsIdentity(operation, 64)
            || !IsIdentity(aggregateKind, 64)
            || !IsIdentity(aggregateId, 128)
            || !IsLowerSha256(actorDigestSha256)
            || scopeSha256.Length != SHA256.HashSizeInBytes
            || idempotencyKeySha256.Length != SHA256.HashSizeInBytes
            || requestFingerprintSha256.Length != SHA256.HashSizeInBytes
            || responsePlaintextSha256.Length != SHA256.HashSizeInBytes)
        {
            throw new ArgumentException("The audit payload cannot be canonicalized.");
        }

        byte[] domain = Encoding.ASCII.GetBytes(DomainTag);
        byte[] uuid = new byte[16];
        try
        {
            using IncrementalHash hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            AppendLengthPrefixed(hash, domain);
            AppendInt32(hash, canonicalVersion);
            if (!eventId.TryWriteBytes(uuid, bigEndian: true, out int uuidBytes)
                || uuidBytes != uuid.Length)
            {
                throw new InvalidOperationException("The audit event UUID cannot be encoded.");
            }

            hash.AppendData(uuid);
            AppendInt64(hash, epoch);
            AppendInt64(hash, generation);
            AppendInt64(hash, sequence);
            AppendUtf8(hash, operation);
            AppendUtf8(hash, aggregateKind);
            AppendUtf8(hash, aggregateId);
            AppendUtf8(hash, actorDigestSha256);
            AppendLengthPrefixed(hash, scopeSha256);
            AppendLengthPrefixed(hash, idempotencyKeySha256);
            AppendLengthPrefixed(hash, requestFingerprintSha256);
            AppendLengthPrefixed(hash, responsePlaintextSha256);
            return hash.GetHashAndReset();
        }
        finally
        {
            CryptographicOperations.ZeroMemory(domain);
            CryptographicOperations.ZeroMemory(uuid);
        }
    }

    private static bool IsIdentity(string? value, int maximumCharacters)
        => !string.IsNullOrWhiteSpace(value)
           && value.Length <= maximumCharacters
           && Encoding.UTF8.GetByteCount(value) <= MaximumIdentityBytes;

    private static bool IsLowerSha256(string? value)
        => value is not null
           && value.Length == SHA256.HashSizeInBytes * 2
           && value.All(static character =>
               character is >= '0' and <= '9' or >= 'a' and <= 'f');

    private static void AppendUtf8(IncrementalHash hash, string value)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(value);
        try
        {
            AppendLengthPrefixed(hash, bytes);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(bytes);
        }
    }

    private static void AppendLengthPrefixed(IncrementalHash hash, ReadOnlySpan<byte> value)
    {
        AppendInt32(hash, value.Length);
        hash.AppendData(value);
    }

    private static void AppendInt32(IncrementalHash hash, int value)
    {
        Span<byte> bytes = stackalloc byte[sizeof(int)];
        BinaryPrimitives.WriteInt32BigEndian(bytes, value);
        hash.AppendData(bytes);
        CryptographicOperations.ZeroMemory(bytes);
    }

    private static void AppendInt64(IncrementalHash hash, long value)
    {
        Span<byte> bytes = stackalloc byte[sizeof(long)];
        BinaryPrimitives.WriteInt64BigEndian(bytes, value);
        hash.AppendData(bytes);
        CryptographicOperations.ZeroMemory(bytes);
    }
}

internal sealed class PlayAuthorizationProviderDeadlineExceededException : Exception
{
}

internal static class PlayAuthorizationCheckpointProviderDeadline
{
    private static readonly TimeSpan MaximumHardDeadline = TimeSpan.FromMinutes(1);

    public static void Validate(PlayAuthorizationCheckpointProviderCapabilities capabilities)
    {
        ArgumentNullException.ThrowIfNull(capabilities);
        if (capabilities.HardDeadline <= TimeSpan.Zero
            || capabilities.HardDeadline > MaximumHardDeadline
            || !capabilities.SupportsMonotonicFencing
            || !string.Equals(
                capabilities.DigestAlgorithm,
                PlayAuthorizationPostgresDurabilityInvariants.CheckpointDigestAlgorithm,
                StringComparison.Ordinal)
            || capabilities.CanonicalVersion
                != PlayAuthorizationPostgresDurabilityInvariants.CheckpointCanonicalVersion
            || !string.Equals(
                capabilities.HmacAlgorithm,
                PlayAuthorizationPostgresDurabilityInvariants.HmacAlgorithm,
                StringComparison.Ordinal)
            || capabilities.HmacSizeInBytes
                != PlayAuthorizationPostgresDurabilityInvariants.HmacSizeInBytes)
        {
            throw new InvalidOperationException(
                "The checkpoint provider does not declare the required deadline, fencing, digest, and HMAC-SHA-256 contract.");
        }
    }

}
