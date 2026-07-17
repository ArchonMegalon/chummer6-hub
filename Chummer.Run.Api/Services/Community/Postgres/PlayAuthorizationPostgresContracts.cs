using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.AspNetCore.DataProtection;
using Npgsql;

namespace Chummer.Run.Api.Services.Community.Postgres;

public static class PlayAuthorizationPostgresSchema
{
    public const string Name = "play_auth";
    public const int CurrentVersion = 4;
}

public static class PlayAuthorizationPostgresDurabilityInvariants
{
    public static readonly TimeSpan ReceiptLifetime = TimeSpan.FromDays(30);
    public const string HmacAlgorithm = "HMAC-SHA-256";
    public const int HmacSizeInBytes = 32;
    public const string AuditPayloadDigestAlgorithm = "SHA-256";
    public const int AuditPayloadCanonicalVersion = 1;
    public const string CheckpointDigestAlgorithm = "SHA-256";
    public const int CheckpointCanonicalVersion = 1;
}

public sealed record PlayAuthorizationReplaySafetyPolicy
{
    public PlayAuthorizationReplaySafetyPolicy(
        TimeSpan maximumCapabilityOrReplayWindow,
        TimeSpan clockSkew)
    {
        if (maximumCapabilityOrReplayWindow <= TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(maximumCapabilityOrReplayWindow));
        }

        if (clockSkew < TimeSpan.Zero || clockSkew > TimeSpan.FromHours(24))
        {
            throw new ArgumentOutOfRangeException(nameof(clockSkew));
        }

        MaximumCapabilityOrReplayWindow = maximumCapabilityOrReplayWindow;
        ClockSkew = clockSkew;
    }

    public TimeSpan MaximumCapabilityOrReplayWindow { get; }
    public TimeSpan ClockSkew { get; }
    public TimeSpan MinimumQuarantine =>
        (MaximumCapabilityOrReplayWindow > PlayAuthorizationPostgresDurabilityInvariants.ReceiptLifetime
            ? MaximumCapabilityOrReplayWindow
            : PlayAuthorizationPostgresDurabilityInvariants.ReceiptLifetime) + ClockSkew;
}

public sealed record PlayAuthorizationCheckpointProviderCapabilities(
    TimeSpan HardDeadline,
    bool SupportsMonotonicFencing,
    string DigestAlgorithm,
    int CanonicalVersion,
    string HmacAlgorithm = PlayAuthorizationPostgresDurabilityInvariants.HmacAlgorithm,
    int HmacSizeInBytes = PlayAuthorizationPostgresDurabilityInvariants.HmacSizeInBytes);

public sealed record PlayAuthorizationCheckpointPublicationPolicy
{
    public PlayAuthorizationCheckpointPublicationPolicy(
        TimeSpan claimLease,
        TimeSpan databaseFinalizationDeadline,
        TimeSpan clockSkew)
    {
        if (claimLease <= TimeSpan.Zero
            || databaseFinalizationDeadline <= TimeSpan.Zero
            || clockSkew < TimeSpan.Zero)
        {
            throw new ArgumentOutOfRangeException(nameof(claimLease));
        }

        ClaimLease = claimLease;
        DatabaseFinalizationDeadline = databaseFinalizationDeadline;
        ClockSkew = clockSkew;
    }

    public TimeSpan ClaimLease { get; }
    public TimeSpan DatabaseFinalizationDeadline { get; }
    public TimeSpan ClockSkew { get; }
}

public enum PlayAuthorizationCapabilityKind
{
    Invite,
    Exchange,
    Grant
}

public enum PlayAuthorizationOperation
{
    RedeemInvite,
    ConsumeExchange,
    RefreshGrant,
    RevokeGrant,
    RevokeParticipant,
    BumpSessionAuthorizationVersion,
    BumpParticipantAuthorizationVersion,
    CloseSession
}

public static class PlayAuthorizationOperationExtensions
{
    public static string ToDatabaseValue(this PlayAuthorizationOperation value)
        => value switch
        {
            PlayAuthorizationOperation.RedeemInvite => "redeem_invite",
            PlayAuthorizationOperation.ConsumeExchange => "consume_exchange",
            PlayAuthorizationOperation.RefreshGrant => "refresh_grant",
            PlayAuthorizationOperation.RevokeGrant => "revoke_grant",
            PlayAuthorizationOperation.RevokeParticipant => "revoke_participant",
            PlayAuthorizationOperation.BumpSessionAuthorizationVersion => "bump_session_version",
            PlayAuthorizationOperation.BumpParticipantAuthorizationVersion => "bump_participant_version",
            PlayAuthorizationOperation.CloseSession => "close_session",
            _ => throw new ArgumentOutOfRangeException(nameof(value), value, null)
        };
}

public static class PlayAuthorizationCapabilityKindExtensions
{
    public static string ToDatabaseValue(this PlayAuthorizationCapabilityKind value)
        => value switch
        {
            PlayAuthorizationCapabilityKind.Invite => "invite",
            PlayAuthorizationCapabilityKind.Exchange => "exchange",
            PlayAuthorizationCapabilityKind.Grant => "grant",
            _ => throw new ArgumentOutOfRangeException(nameof(value), value, null)
        };
}

public sealed record PlayAuthorizationPostgresState(
    long Epoch,
    long Generation,
    DateTimeOffset ClockHighWaterUtc,
    long AuditHeadSequence,
    byte[] AuditHeadHmac,
    byte[] ExternalCheckpoint);

public sealed record PlayAuthorizationExternalEpoch(
    long Epoch,
    long Generation,
    byte[] Checkpoint);

public sealed record PlayAuthorizationKeyedDigest(string KeyId, byte[] Digest);

public sealed record PlayAuthorizationAuditDigestInput(
    long Epoch,
    long Generation,
    long Sequence,
    byte[] PreviousHmac,
    byte[] PayloadSha256);

public interface IPlayAuthorizationEpochAuthority
{
    ValueTask<PlayAuthorizationExternalEpoch> ReadCurrentAsync(CancellationToken cancellationToken);
}

public interface IPlayAuthorizationHmacAuthority
{
    ValueTask<PlayAuthorizationKeyedDigest> ComputeCapabilityAsync(
        PlayAuthorizationCapabilityKind kind,
        string capabilityId,
        ReadOnlyMemory<byte> secret,
        string? requiredKeyId,
        CancellationToken cancellationToken);

    ValueTask<PlayAuthorizationKeyedDigest> ComputeAuditAsync(
        PlayAuthorizationAuditDigestInput input,
        CancellationToken cancellationToken);
}

public interface IPlayAuthorizationCheckpointAuthority
{
    PlayAuthorizationCheckpointProviderCapabilities Capabilities { get; }

    ValueTask ValidateAsync(
        PlayAuthorizationExternalEpoch externalEpoch,
        PlayAuthorizationPostgresState databaseState,
        CancellationToken cancellationToken);

    ValueTask<PlayAuthorizationCheckpointBaselineAcknowledgement> VerifyBaselineAsync(
        PlayAuthorizationCheckpointBaselineVerification verification,
        PlayAuthorizationExternalEpoch externalEpoch,
        CancellationToken cancellationToken);

    ValueTask<PlayAuthorizationCheckpointPublicationAcknowledgement> PublishAsync(
        PlayAuthorizationCheckpointPublicationEnvelope envelope,
        CancellationToken cancellationToken);
}

public enum PlayAuthorizationCheckpointPublicationDisposition
{
    Accepted,
    AlreadyPublished,
    RejectedOutOfOrder,
    RejectedAuthority
}

public sealed record PlayAuthorizationCheckpointPublicationAcknowledgement(
    PlayAuthorizationCheckpointPublicationDisposition Disposition,
    Guid PublicationId,
    long AcceptedFencingToken,
    byte[] PayloadDigestSha256);

public sealed record PlayAuthorizationCheckpointPublicationEnvelope(
    Guid PublicationId,
    long FencingToken,
    PlayAuthorizationPostgresState State,
    string DigestAlgorithm,
    int CanonicalVersion,
    byte[] PayloadDigestSha256);

public sealed record PlayAuthorizationCheckpointBaselineVerification(
    Guid BaselineId,
    PlayAuthorizationPostgresState State,
    string DigestAlgorithm,
    int CanonicalVersion,
    byte[] PayloadDigestSha256);

public sealed record PlayAuthorizationCheckpointBaselineAcknowledgement(
    bool Accepted,
    Guid BaselineId,
    byte[] PayloadDigestSha256);

public sealed record PlayAuthorizationCheckpointReconciliationResult(
    int PublishedCount,
    long PendingCount,
    long? OldestPendingSequence,
    string Code)
{
    public bool Complete => PendingCount == 0;
}

public sealed record PlayAuthorizationCheckpointProviderCallDiagnostics(
    int ValidationCallsInFlight,
    int BaselineCallsInFlight,
    int PublicationCallsInFlight)
{
    public int TotalCallsInFlight => checked(
        ValidationCallsInFlight + BaselineCallsInFlight + PublicationCallsInFlight);
}

public interface IPlayAuthorizationCheckpointPublicationReconciler
{
    Task<PlayAuthorizationCheckpointReconciliationResult> ReconcileAsync(
        int maximumPublications,
        CancellationToken cancellationToken = default);

    Task<bool> IsPublishedAsync(
        long auditSequence,
        long epoch,
        long generation,
        CancellationToken cancellationToken = default);
}

public sealed record PlayAuthorizationReceiptPruneResult(
    int ScrubbedCount,
    int DeletedCount,
    DateTimeOffset EffectiveDatabaseTimeUtc);

public interface IPlayAuthorizationIdempotencyReceiptPruner
{
    Task<PlayAuthorizationReceiptPruneResult> PruneExpiredAsync(
        int maximumReceipts,
        CancellationToken cancellationToken = default);
}

public sealed class PlayAuthorizationExternalAuthorityUnavailableException : Exception
{
    public PlayAuthorizationExternalAuthorityUnavailableException(string authority)
        : base($"The external Play authorization {authority} authority is unavailable.")
    {
    }
}

/// <summary>
/// Safe defaults for dormant composition roots. These contain no keys or checkpoints and always
/// reject use; production composition must supply independently backed authorities explicitly.
/// </summary>
public sealed class UnavailablePlayAuthorizationExternalAuthorities :
    IPlayAuthorizationEpochAuthority,
    IPlayAuthorizationHmacAuthority,
    IPlayAuthorizationCheckpointAuthority
{
    public PlayAuthorizationCheckpointProviderCapabilities Capabilities { get; } = new(
        TimeSpan.Zero,
        SupportsMonotonicFencing: false,
        PlayAuthorizationPostgresDurabilityInvariants.CheckpointDigestAlgorithm,
        PlayAuthorizationPostgresDurabilityInvariants.CheckpointCanonicalVersion,
        PlayAuthorizationPostgresDurabilityInvariants.HmacAlgorithm,
        PlayAuthorizationPostgresDurabilityInvariants.HmacSizeInBytes);

    public ValueTask<PlayAuthorizationExternalEpoch> ReadCurrentAsync(CancellationToken cancellationToken)
        => ValueTask.FromException<PlayAuthorizationExternalEpoch>(
            new PlayAuthorizationExternalAuthorityUnavailableException("epoch"));

    public ValueTask<PlayAuthorizationKeyedDigest> ComputeCapabilityAsync(
        PlayAuthorizationCapabilityKind kind,
        string capabilityId,
        ReadOnlyMemory<byte> secret,
        string? requiredKeyId,
        CancellationToken cancellationToken)
        => ValueTask.FromException<PlayAuthorizationKeyedDigest>(
            new PlayAuthorizationExternalAuthorityUnavailableException("HMAC"));

    public ValueTask<PlayAuthorizationKeyedDigest> ComputeAuditAsync(
        PlayAuthorizationAuditDigestInput input,
        CancellationToken cancellationToken)
        => ValueTask.FromException<PlayAuthorizationKeyedDigest>(
            new PlayAuthorizationExternalAuthorityUnavailableException("HMAC"));

    public ValueTask ValidateAsync(
        PlayAuthorizationExternalEpoch externalEpoch,
        PlayAuthorizationPostgresState databaseState,
        CancellationToken cancellationToken)
        => ValueTask.FromException(
            new PlayAuthorizationExternalAuthorityUnavailableException("checkpoint"));

    public ValueTask<PlayAuthorizationCheckpointBaselineAcknowledgement> VerifyBaselineAsync(
        PlayAuthorizationCheckpointBaselineVerification verification,
        PlayAuthorizationExternalEpoch externalEpoch,
        CancellationToken cancellationToken)
        => ValueTask.FromException<PlayAuthorizationCheckpointBaselineAcknowledgement>(
            new PlayAuthorizationExternalAuthorityUnavailableException("checkpoint"));

    public ValueTask<PlayAuthorizationCheckpointPublicationAcknowledgement> PublishAsync(
        PlayAuthorizationCheckpointPublicationEnvelope envelope,
        CancellationToken cancellationToken)
        => ValueTask.FromException<PlayAuthorizationCheckpointPublicationAcknowledgement>(
            new PlayAuthorizationExternalAuthorityUnavailableException("checkpoint"));
}

public enum PlayAuthorizationReceiptKind
{
    Session,
    Participant,
    InviteIssued,
    ExchangeIssued,
    GrantIssued,
    Grant,
    Problem
}

public sealed record PlayAuthorizationReceiptEnvelope(
    int SchemaVersion,
    PlayAuthorizationReceiptKind Kind,
    int StatusCode,
    string ContentType,
    byte[] Body)
{
    public const int CurrentSchemaVersion = 1;

    public static PlayAuthorizationReceiptEnvelope Json(
        PlayAuthorizationReceiptKind kind,
        int statusCode,
        byte[] body)
        => new(CurrentSchemaVersion, kind, statusCode, "application/json; charset=utf-8", body);
}

public sealed record PlayAuthorizationProtectedReceipt(
    byte[] Ciphertext,
    byte[] PlaintextSha256,
    string ResponseType);

public interface IPlayAuthorizationReceiptCipher
{
    PlayAuthorizationProtectedReceipt Protect(PlayAuthorizationReceiptEnvelope envelope);

    PlayAuthorizationReceiptEnvelope Unprotect(
        ReadOnlySpan<byte> ciphertext,
        ReadOnlySpan<byte> expectedPlaintextSha256,
        string expectedResponseType);
}

public sealed class DataProtectionPlayAuthorizationReceiptCipher : IPlayAuthorizationReceiptCipher
{
    private const string Purpose = "Chummer.PlayAuthorization.Postgres.IdempotencyReceipt.v1";
    private static readonly JsonSerializerOptions SerializerOptions = new(JsonSerializerDefaults.Web);
    private readonly IDataProtector _protector;

    public DataProtectionPlayAuthorizationReceiptCipher(IDataProtectionProvider provider)
    {
        ArgumentNullException.ThrowIfNull(provider);
        _protector = provider.CreateProtector(Purpose);
    }

    public PlayAuthorizationProtectedReceipt Protect(PlayAuthorizationReceiptEnvelope envelope)
    {
        ValidateEnvelope(envelope);
        byte[] plaintext = JsonSerializer.SerializeToUtf8Bytes(envelope, SerializerOptions);
        try
        {
            return new PlayAuthorizationProtectedReceipt(
                _protector.Protect(plaintext),
                SHA256.HashData(plaintext),
                envelope.Kind.ToString());
        }
        finally
        {
            CryptographicOperations.ZeroMemory(plaintext);
        }
    }

    public PlayAuthorizationReceiptEnvelope Unprotect(
        ReadOnlySpan<byte> ciphertext,
        ReadOnlySpan<byte> expectedPlaintextSha256,
        string expectedResponseType)
    {
        if (ciphertext.IsEmpty || expectedPlaintextSha256.Length != SHA256.HashSizeInBytes)
        {
            throw new CryptographicException("The durable Play authorization receipt is malformed.");
        }

        byte[] plaintext = _protector.Unprotect(ciphertext.ToArray());
        byte[] actualHash = SHA256.HashData(plaintext);
        try
        {
            if (!CryptographicOperations.FixedTimeEquals(actualHash, expectedPlaintextSha256))
            {
                throw new CryptographicException("The durable Play authorization receipt digest does not match.");
            }

            PlayAuthorizationReceiptEnvelope envelope = JsonSerializer.Deserialize<PlayAuthorizationReceiptEnvelope>(
                plaintext,
                SerializerOptions) ?? throw new CryptographicException("The durable Play authorization receipt is empty.");
            ValidateEnvelope(envelope);
            if (!string.Equals(envelope.Kind.ToString(), expectedResponseType, StringComparison.Ordinal))
            {
                throw new CryptographicException("The durable Play authorization receipt type does not match.");
            }

            return envelope;
        }
        catch (JsonException exception)
        {
            throw new CryptographicException("The durable Play authorization receipt cannot be decoded.", exception);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(plaintext);
            CryptographicOperations.ZeroMemory(actualHash);
        }
    }

    private static void ValidateEnvelope(PlayAuthorizationReceiptEnvelope envelope)
    {
        ArgumentNullException.ThrowIfNull(envelope);
        if (envelope.SchemaVersion != PlayAuthorizationReceiptEnvelope.CurrentSchemaVersion
            || envelope.StatusCode is < 100 or > 599
            || string.IsNullOrWhiteSpace(envelope.ContentType)
            || envelope.ContentType.Length > 128
            || envelope.Body is null
            || envelope.Body.Length > 64 * 1024)
        {
            throw new ArgumentException("The durable Play authorization response envelope is invalid.", nameof(envelope));
        }
    }
}

public sealed record PlayAuthorizationDurableRequest(
    string Scope,
    string IdempotencyKey,
    string FingerprintSha256,
    PlayAuthorizationReceiptEnvelope Response,
    PlayAuthorizationOperation Operation);

public enum PlayAuthorizationPostgresOutcomeCode
{
    Applied,
    Replayed,
    FingerprintConflict,
    ReceiptBindingConflict,
    CheckpointPending,
    NotFound,
    Expired,
    AlreadyConsumed,
    VersionMismatch,
    InvalidLifecycle,
    AuthorityUnavailable,
    PersistenceUnavailable
}

public sealed record PlayAuthorizationPostgresMutationResult(
    PlayAuthorizationPostgresOutcomeCode Code,
    PlayAuthorizationReceiptEnvelope? Response = null)
{
    public bool Succeeded => Code is PlayAuthorizationPostgresOutcomeCode.Applied
        or PlayAuthorizationPostgresOutcomeCode.Replayed;
}

public sealed record PlayAuthorizationRedeemMutation(
    PlayAuthorizationDurableRequest DurableRequest,
    string InviteId,
    string ExchangeId,
    string SessionId,
    string ParticipantId,
    string UserId,
    string Role,
    byte[] PresentedInviteSecret,
    byte[] NewExchangeSecret,
    string DeviceThumbprint,
    long ExpectedSessionAuthorizationVersion,
    long ExpectedParticipantAuthorizationVersion,
    DateTimeOffset ExchangeExpiresAtUtc,
    string ActorDigestSha256);

public sealed record PlayAuthorizationConsumeMutation(
    PlayAuthorizationDurableRequest DurableRequest,
    string ExchangeId,
    string GrantId,
    string SessionId,
    string ParticipantId,
    string UserId,
    string Role,
    byte[] PresentedExchangeSecret,
    byte[] NewGrantSecret,
    string DeviceThumbprint,
    long ExpectedSessionAuthorizationVersion,
    long ExpectedParticipantAuthorizationVersion,
    DateTimeOffset GrantExpiresAtUtc,
    DateTimeOffset RefreshUntilUtc,
    string ActorDigestSha256);

public sealed record PlayAuthorizationRefreshMutation(
    PlayAuthorizationDurableRequest DurableRequest,
    string GrantId,
    string SessionId,
    string ParticipantId,
    string UserId,
    string Role,
    byte[] PresentedGrantSecret,
    byte[] NewGrantSecret,
    string DeviceThumbprint,
    long ExpectedSessionAuthorizationVersion,
    long ExpectedParticipantAuthorizationVersion,
    DateTimeOffset GrantExpiresAtUtc,
    string ActorDigestSha256);

public sealed record PlayAuthorizationGrantMutation(
    PlayAuthorizationDurableRequest DurableRequest,
    string GrantId,
    string SessionId,
    long ExpectedSessionAuthorizationVersion,
    string ActorDigestSha256);

public sealed record PlayAuthorizationParticipantMutation(
    PlayAuthorizationDurableRequest DurableRequest,
    string ParticipantId,
    string SessionId,
    long ExpectedSessionAuthorizationVersion,
    long ExpectedParticipantAuthorizationVersion,
    string ActorDigestSha256);

public sealed record PlayAuthorizationSessionMutation(
    PlayAuthorizationDurableRequest DurableRequest,
    string SessionId,
    long ExpectedSessionAuthorizationVersion,
    string ActorDigestSha256);

public sealed record PlayAuthorizationPostgresReadiness(
    bool Ready,
    string Code,
    int ExpectedSchemaVersion,
    int AppliedSchemaVersion,
    long? Epoch,
    long? Generation,
    DateTimeOffset CheckedAtUtc);

public interface IPlayAuthorizationPostgresRepository
{
    Task<PlayAuthorizationPostgresMutationResult> RedeemInviteAsync(
        PlayAuthorizationRedeemMutation mutation,
        CancellationToken cancellationToken = default);

    Task<PlayAuthorizationPostgresMutationResult> ConsumeExchangeAsync(
        PlayAuthorizationConsumeMutation mutation,
        CancellationToken cancellationToken = default);

    Task<PlayAuthorizationPostgresMutationResult> RefreshGrantAsync(
        PlayAuthorizationRefreshMutation mutation,
        CancellationToken cancellationToken = default);

    Task<PlayAuthorizationPostgresMutationResult> RevokeGrantAsync(
        PlayAuthorizationGrantMutation mutation,
        CancellationToken cancellationToken = default);

    Task<PlayAuthorizationPostgresMutationResult> RevokeParticipantAsync(
        PlayAuthorizationParticipantMutation mutation,
        CancellationToken cancellationToken = default);

    Task<PlayAuthorizationPostgresMutationResult> BumpSessionAuthorizationVersionAsync(
        PlayAuthorizationSessionMutation mutation,
        CancellationToken cancellationToken = default);

    Task<PlayAuthorizationPostgresMutationResult> BumpParticipantAuthorizationVersionAsync(
        PlayAuthorizationParticipantMutation mutation,
        CancellationToken cancellationToken = default);

    Task<PlayAuthorizationPostgresMutationResult> CloseSessionAsync(
        PlayAuthorizationSessionMutation mutation,
        CancellationToken cancellationToken = default);

    Task<PlayAuthorizationPostgresMutationResult?> LookupIdempotencyReceiptAsync(
        PlayAuthorizationDurableRequest request,
        CancellationToken cancellationToken = default);
}

public interface IPlayAuthorizationPostgresUnitOfWork : IAsyncDisposable
{
    NpgsqlConnection Connection { get; }
    NpgsqlTransaction Transaction { get; }
    Task CommitAsync(CancellationToken cancellationToken);
    Task RollbackAsync(CancellationToken cancellationToken);
}

public interface IPlayAuthorizationPostgresUnitOfWorkFactory
{
    ValueTask<IPlayAuthorizationPostgresUnitOfWork> BeginAsync(CancellationToken cancellationToken);
}

public interface IPlayAuthorizationCommitObserver
{
    ValueTask AfterCommitAsync(CancellationToken cancellationToken);
}

public sealed class NoOpPlayAuthorizationCommitObserver : IPlayAuthorizationCommitObserver
{
    public ValueTask AfterCommitAsync(CancellationToken cancellationToken) => ValueTask.CompletedTask;
}
