using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using Microsoft.Win32.SafeHandles;

namespace Chummer.Run.Api.Services.InstallLinking.Postgres;

internal enum InstallLinkingPostgresImportDisposition
{
    Imported,
    Reconciled,
    AlreadyMirrored,
    PreparedNotCommitted,
    CommittedPendingMirror,
    RefusedNonEmpty,
    AuthorityUnavailable
}

internal sealed record InstallLinkingPostgresImportResult(
    InstallLinkingPostgresImportDisposition Disposition,
    string Code)
{
    public bool Succeeded => Disposition is
        InstallLinkingPostgresImportDisposition.Imported
        or InstallLinkingPostgresImportDisposition.Reconciled
        or InstallLinkingPostgresImportDisposition.AlreadyMirrored;
}

/// <summary>
/// Executes the one-shot local-to-PostgreSQL cutover as a small durable protocol. The authority
/// readiness/head preflight deliberately runs before the session factory can touch local files.
/// </summary>
internal sealed class InstallLinkingPostgresImportCoordinator
{
    private readonly IInstallLinkingSnapshotAuthority _authority;
    private readonly Func<InstallLinkingOneShotImportSession> _openSession;

    public InstallLinkingPostgresImportCoordinator(
        IInstallLinkingSnapshotAuthority authority,
        Func<InstallLinkingOneShotImportSession> openSession)
    {
        _authority = authority ?? throw new ArgumentNullException(nameof(authority));
        _openSession = openSession ?? throw new ArgumentNullException(nameof(openSession));
    }

    public async Task<InstallLinkingPostgresImportResult> ExecuteAsync(
        CancellationToken cancellationToken = default)
    {
        InstallLinkingPostgresReadiness readiness =
            await _authority.CheckReadinessAsync(cancellationToken);
        if (!readiness.Ready)
        {
            return new(
                InstallLinkingPostgresImportDisposition.AuthorityUnavailable,
                "authority_not_ready");
        }

        using InstallLinkingAuthoritativeEnvelope initial =
            await _authority.ReadCurrentAsync(cancellationToken);
        if (!initial.IsEmpty && initial.Generation != 1)
        {
            return new(
                InstallLinkingPostgresImportDisposition.RefusedNonEmpty,
                "authority_not_empty");
        }

        using InstallLinkingOneShotImportSession session = _openSession();
        using InstallLinkingPostgresImportIntent? existingIntent = session.ReadIntent();
        if (!initial.IsEmpty)
        {
            if (existingIntent is null)
            {
                return session.IsExactAcknowledgedMirror(initial)
                    ? new(
                        InstallLinkingPostgresImportDisposition.AlreadyMirrored,
                        "already_mirrored")
                    : new(
                        InstallLinkingPostgresImportDisposition.RefusedNonEmpty,
                        "authority_not_empty");
            }

            if (!existingIntent.Matches(initial))
            {
                return new(
                    InstallLinkingPostgresImportDisposition.RefusedNonEmpty,
                    "authority_intent_mismatch");
            }

            return CompleteCommitted(
                session,
                existingIntent,
                initial,
                InstallLinkingPostgresImportDisposition.Reconciled);
        }

        InstallLinkingPostgresImportIntent? createdIntent = null;
        InstallLinkingPostgresImportIntent intent = existingIntent
            ?? (createdIntent = session.CreateAndPersistIntent());
        try
        {
            InstallLinkingEnvelopeCompareExchangeRequest request = intent.CreateRequest();
            try
            {
                using InstallLinkingEnvelopeCompareExchangeResult result =
                    await _authority.CompareExchangeAsync(request, cancellationToken);
                if (result.Committed
                    && result.AuthoritativeEnvelope is not null
                    && intent.Matches(result.AuthoritativeEnvelope))
                {
                    return CompleteCommitted(
                        session,
                        intent,
                        result.AuthoritativeEnvelope,
                        InstallLinkingPostgresImportDisposition.Imported);
                }
            }
            finally
            {
                ClearRequest(request);
            }

            // A dropped response can hide a durable CAS. Re-read by the immutable intent before
            // deciding whether this is merely prepared or committed-pending-mirror.
            using InstallLinkingAuthoritativeEnvelope observed =
                await _authority.ReadCurrentAsync(cancellationToken);
            if (intent.Matches(observed))
            {
                return CompleteCommitted(
                    session,
                    intent,
                    observed,
                    InstallLinkingPostgresImportDisposition.Reconciled);
            }

            return observed.IsEmpty
                ? new(
                    InstallLinkingPostgresImportDisposition.PreparedNotCommitted,
                    "prepared_not_committed")
                : new(
                    InstallLinkingPostgresImportDisposition.RefusedNonEmpty,
                    "authority_intent_mismatch");
        }
        finally
        {
            createdIntent?.Dispose();
        }
    }

    private static InstallLinkingPostgresImportResult CompleteCommitted(
        InstallLinkingOneShotImportSession session,
        InstallLinkingPostgresImportIntent intent,
        InstallLinkingAuthoritativeEnvelope authoritativeEnvelope,
        InstallLinkingPostgresImportDisposition successDisposition)
    {
        if (!intent.Matches(authoritativeEnvelope))
        {
            return new(
                InstallLinkingPostgresImportDisposition.RefusedNonEmpty,
                "authority_intent_mismatch");
        }

        try
        {
            session.MarkCommittedPendingMirror(intent);
            session.CompleteExactMirror(authoritativeEnvelope);
            session.DeleteIntent();
            return new(successDisposition, successDisposition == InstallLinkingPostgresImportDisposition.Imported
                ? "imported"
                : "reconciled");
        }
        catch (Exception exception) when (IsDurableImportFailure(exception))
        {
            // The immutable intent remains the recovery authority. It may still say prepared if
            // the state-marker write itself failed; an exact PostgreSQL head makes that state
            // equivalent to committed-pending-mirror on the next invocation.
            return new(
                InstallLinkingPostgresImportDisposition.CommittedPendingMirror,
                "committed_pending_mirror");
        }
    }

    private static bool IsDurableImportFailure(Exception exception)
        => exception is IOException
            or UnauthorizedAccessException
            or InvalidDataException
            or InvalidOperationException
            or CryptographicException
            or JsonException
            or NotSupportedException;

    private static void ClearRequest(InstallLinkingEnvelopeCompareExchangeRequest request)
    {
        if (request.ExpectedEnvelopeSha256 is not null)
        {
            CryptographicOperations.ZeroMemory(request.ExpectedEnvelopeSha256);
        }

        CryptographicOperations.ZeroMemory(request.SnapshotSha256);
        CryptographicOperations.ZeroMemory(request.EnvelopeSha256);
        CryptographicOperations.ZeroMemory(request.ProtectedEnvelope);
    }
}

internal enum InstallLinkingImportMirrorStage
{
    BeforeStoreWrite,
    AfterStoreWrite,
    AfterFloorWrite
}

/// <summary>
/// Holds the local writer lease and reads legacy/protected state without running ordinary store
/// startup, retention persistence, floor repair, quarantine, or plaintext migration.
/// </summary>
internal sealed class InstallLinkingOneShotImportSession : IDisposable
{
    private const string IntentSuffix = ".postgres-import.intent";
    private readonly IDataProtector _protector;
    private readonly IDataProtector _legacyProtector;
    private readonly IDataProtector _floorProtector;
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };
    private readonly TimeProvider _timeProvider;
    private readonly Action<InstallLinkingImportMirrorStage>? _mirrorObserver;
    private readonly FileStream _writerLease;

    private InstallLinkingOneShotImportSession(
        string storagePath,
        IDataProtectionProvider dataProtectionProvider,
        bool production,
        TimeProvider timeProvider,
        Action<InstallLinkingImportMirrorStage>? mirrorObserver)
    {
        StoragePath = storagePath;
        FloorPath = $"{storagePath}.floor";
        IntentPath = $"{storagePath}{IntentSuffix}";
        _protector = dataProtectionProvider.CreateProtector(
            InstallLinkingStore.DataProtectionPurpose);
        _legacyProtector = dataProtectionProvider.CreateProtector(
            InstallLinkingStore.LegacyDataProtectionPurpose);
        _floorProtector = dataProtectionProvider.CreateProtector(
            InstallLinkingStore.FloorDataProtectionPurpose);
        _timeProvider = timeProvider;
        _mirrorObserver = mirrorObserver;
        InstallLinkingImportFileSystem.PrepareStorageDirectory(storagePath, production);
        _writerLease = InstallLinkingImportFileSystem.AcquireWriterLease(
            $"{storagePath}.writer.lock",
            production);
    }

    public string StoragePath { get; }
    public string FloorPath { get; }
    public string IntentPath { get; }

    public static InstallLinkingOneShotImportSession Open(
        IConfiguration configuration,
        IDataProtectionProvider dataProtectionProvider,
        IHostEnvironment environment,
        TimeProvider? timeProvider = null,
        Action<InstallLinkingImportMirrorStage>? mirrorObserver = null)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        ArgumentNullException.ThrowIfNull(dataProtectionProvider);
        ArgumentNullException.ThrowIfNull(environment);
        return new(
            InstallLinkingStore.ResolveStoragePath(configuration),
            dataProtectionProvider,
            environment.IsProduction(),
            timeProvider ?? TimeProvider.System,
            mirrorObserver);
    }

    public InstallLinkingPostgresImportIntent? ReadIntent()
    {
        if (!File.Exists(IntentPath))
        {
            return null;
        }

        byte[] bytes = InstallLinkingImportFileSystem.ReadOwnerOnlyFile(
            IntentPath,
            InstallLinkingPostgresImportIntent.MaximumSerializedBytes);
        try
        {
            return InstallLinkingPostgresImportIntent.Deserialize(bytes, _jsonOptions);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(bytes);
        }
    }

    public InstallLinkingPostgresImportIntent CreateAndPersistIntent()
    {
        InstallLinkingEnvelopeCompareExchangeRequest request = CreateReadOnlyRequest();
        try
        {
            InstallLinkingPostgresImportIntent intent =
                InstallLinkingPostgresImportIntent.FromRequest(
                    request,
                    _timeProvider.GetUtcNow());
            try
            {
                byte[] bytes = intent.Serialize(_jsonOptions);
                try
                {
                    InstallLinkingImportFileSystem.WriteOwnerOnlyFileAtomically(
                        IntentPath,
                        bytes,
                        overwrite: false);
                }
                finally
                {
                    CryptographicOperations.ZeroMemory(bytes);
                }

                return intent;
            }
            catch
            {
                intent.Dispose();
                throw;
            }
        }
        finally
        {
            ClearRequest(request);
        }
    }

    public void MarkCommittedPendingMirror(InstallLinkingPostgresImportIntent intent)
    {
        ArgumentNullException.ThrowIfNull(intent);
        intent.MarkCommittedPendingMirror();
        byte[] bytes = intent.Serialize(_jsonOptions);
        try
        {
            InstallLinkingImportFileSystem.WriteOwnerOnlyFileAtomically(
                IntentPath,
                bytes,
                overwrite: true);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(bytes);
        }
    }

    public void CompleteExactMirror(
        InstallLinkingAuthoritativeEnvelope authoritativeEnvelope)
    {
        ArgumentNullException.ThrowIfNull(authoritativeEnvelope);
        ValidateGenerationOneAuthority(authoritativeEnvelope);
        byte[] envelopeBytes = authoritativeEnvelope.ProtectedEnvelope!.ToArray();
        byte[]? snapshotBytes = null;
        try
        {
            using JsonDocument document = StrictDocument(envelopeBytes);
            ProtectedEnvelopeDescriptor descriptor =
                InstallLinkingStore.ReadStrictProtectedPayload(document.RootElement);
            if (descriptor.Version != InstallLinkingStore.EnvelopeVersion
                || descriptor.Generation != 1)
            {
                throw new InvalidDataException(
                    "The InstallLinking import envelope generation is invalid.");
            }

            snapshotBytes = Convert.FromBase64String(
                _protector.Unprotect(descriptor.ProtectedPayload));
            InstallLinkingStoreSnapshot snapshot =
                InstallLinkingStore.DeserializeImportSnapshot(snapshotBytes, _jsonOptions);
            InstallLinkingStore.ValidateSnapshot(snapshot);
            RequireDigest(
                envelopeBytes,
                authoritativeEnvelope.EnvelopeSha256!,
                "envelope");
            RequireDigest(
                snapshotBytes,
                authoritativeEnvelope.SnapshotSha256!,
                "snapshot");

            _mirrorObserver?.Invoke(InstallLinkingImportMirrorStage.BeforeStoreWrite);
            InstallLinkingImportFileSystem.WriteOwnerOnlyFileAtomically(
                StoragePath,
                envelopeBytes,
                overwrite: true);
            _mirrorObserver?.Invoke(InstallLinkingImportMirrorStage.AfterStoreWrite);
            WriteFloor(authoritativeEnvelope.Generation, snapshotBytes);
            _mirrorObserver?.Invoke(InstallLinkingImportMirrorStage.AfterFloorWrite);
            if (!IsExactAcknowledgedMirror(authoritativeEnvelope))
            {
                throw new IOException(
                    "The InstallLinking import mirror acknowledgement is incomplete.");
            }
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

    public bool IsExactAcknowledgedMirror(
        InstallLinkingAuthoritativeEnvelope authoritativeEnvelope)
    {
        try
        {
            ValidateGenerationOneAuthority(authoritativeEnvelope);
            if (!File.Exists(StoragePath) || !File.Exists(FloorPath))
            {
                return false;
            }

            byte[] envelopeBytes = InstallLinkingImportFileSystem.ReadOwnerOnlyFile(
                StoragePath,
                InstallLinkingStore.MaxSnapshotBytes);
            byte[]? snapshotBytes = null;
            try
            {
                if (!FixedEquals(envelopeBytes, authoritativeEnvelope.ProtectedEnvelope)
                    || !DigestMatches(envelopeBytes, authoritativeEnvelope.EnvelopeSha256!))
                {
                    return false;
                }

                using JsonDocument document = StrictDocument(envelopeBytes);
                ProtectedEnvelopeDescriptor descriptor =
                    InstallLinkingStore.ReadStrictProtectedPayload(document.RootElement);
                if (descriptor.Version != InstallLinkingStore.EnvelopeVersion
                    || descriptor.Generation != authoritativeEnvelope.Generation)
                {
                    return false;
                }

                snapshotBytes = Convert.FromBase64String(
                    _protector.Unprotect(descriptor.ProtectedPayload));
                InstallLinkingStoreFloorPayload floor = ReadFloor();
                byte[] floorDigest = Convert.FromHexString(floor.SnapshotSha256!);
                try
                {
                    return DigestMatches(
                               snapshotBytes,
                               authoritativeEnvelope.SnapshotSha256!)
                           && floor.Generation == authoritativeEnvelope.Generation
                           && FixedEquals(
                               floorDigest,
                               authoritativeEnvelope.SnapshotSha256);
                }
                finally
                {
                    CryptographicOperations.ZeroMemory(floorDigest);
                }
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
        catch (Exception exception) when (exception is
            IOException or UnauthorizedAccessException or InvalidDataException
            or InvalidOperationException or CryptographicException or JsonException
            or FormatException or NotSupportedException)
        {
            return false;
        }
    }

    public void DeleteIntent()
        => InstallLinkingImportFileSystem.DeleteOwnerOnlyFileDurably(
            IntentPath,
            InstallLinkingPostgresImportIntent.MaximumSerializedBytes);

    private InstallLinkingEnvelopeCompareExchangeRequest CreateReadOnlyRequest()
    {
        if (!File.Exists(StoragePath))
        {
            throw new InvalidOperationException(
                "There is no local InstallLinking state to import.");
        }

        byte[] durableBytes = InstallLinkingImportFileSystem.ReadOwnerOnlyFile(
            StoragePath,
            InstallLinkingStore.MaxSnapshotBytes);
        byte[]? snapshotBytes = null;
        try
        {
            bool migrating;
            long loadedGeneration;
            InstallLinkingStoreSnapshot sourceSnapshot;
            using (JsonDocument document = StrictDocument(durableBytes))
            {
                JsonElement root = document.RootElement;
                if (InstallLinkingStore.ContainsAnyEnvelopeProperty(root))
                {
                    ProtectedEnvelopeDescriptor descriptor =
                        InstallLinkingStore.ReadStrictProtectedPayload(root);
                    string encodedSnapshot = descriptor.Version
                        == InstallLinkingStore.LegacyEnvelopeVersion
                        ? _legacyProtector.Unprotect(descriptor.ProtectedPayload)
                        : _protector.Unprotect(descriptor.ProtectedPayload);
                    snapshotBytes = Convert.FromBase64String(encodedSnapshot);
                    sourceSnapshot = InstallLinkingStore.DeserializeImportSnapshot(
                        snapshotBytes,
                        _jsonOptions);
                    migrating = descriptor.Version
                        == InstallLinkingStore.LegacyEnvelopeVersion;
                    loadedGeneration = descriptor.Generation;
                }
                else
                {
                    InstallLinkingStore.ValidateLegacySnapshotShape(root);
                    snapshotBytes = durableBytes.ToArray();
                    sourceSnapshot = InstallLinkingStore.DeserializeImportSnapshot(
                        snapshotBytes,
                        _jsonOptions);
                    migrating = true;
                    loadedGeneration = 0;
                }
            }

            InstallLinkingStore.ValidateSnapshot(sourceSnapshot);
            ValidateFloorReadOnly(
                loadedGeneration,
                sourceSnapshot,
                migrating);
            InstallLinkingStoreSnapshot retained =
                InstallLinkingStore.BuildRetainedSnapshot(
                    sourceSnapshot,
                    _timeProvider.GetUtcNow());
            InstallLinkingStore.ValidateSnapshot(retained);
            byte[] retainedBytes = JsonSerializer.SerializeToUtf8Bytes(
                retained,
                _jsonOptions);
            try
            {
                string protectedPayload = _protector.Protect(
                    Convert.ToBase64String(retainedBytes));
                byte[] envelopeBytes = JsonSerializer.SerializeToUtf8Bytes(
                    new InstallLinkingStoreEnvelope(
                        InstallLinkingStore.EnvelopeFormat,
                        InstallLinkingStore.EnvelopeVersion,
                        Generation: 1,
                        ProtectedPayload: protectedPayload),
                    _jsonOptions);
                if (retainedBytes.Length > InstallLinkingStore.MaxSnapshotBytes
                    || envelopeBytes.Length > InstallLinkingStore.MaxSnapshotBytes)
                {
                    CryptographicOperations.ZeroMemory(envelopeBytes);
                    throw new InvalidOperationException(
                        "Install-linking one-shot import payload exceeds the durable storage limit.");
                }

                return new InstallLinkingEnvelopeCompareExchangeRequest(
                    ExpectedGeneration: 0,
                    ExpectedCommitId: null,
                    ExpectedEnvelopeSha256: null,
                    NextGeneration: 1,
                    CommitId: Guid.NewGuid(),
                    EnvelopeVersion: InstallLinkingStore.EnvelopeVersion,
                    SnapshotSha256: SHA256.HashData(retainedBytes),
                    EnvelopeSha256: SHA256.HashData(envelopeBytes),
                    ProtectedEnvelope: envelopeBytes);
            }
            finally
            {
                CryptographicOperations.ZeroMemory(retainedBytes);
            }
        }
        finally
        {
            CryptographicOperations.ZeroMemory(durableBytes);
            if (snapshotBytes is not null)
            {
                CryptographicOperations.ZeroMemory(snapshotBytes);
            }
        }
    }

    private void ValidateFloorReadOnly(
        long loadedGeneration,
        InstallLinkingStoreSnapshot snapshot,
        bool migrating)
    {
        if (!File.Exists(FloorPath))
        {
            return;
        }

        if (migrating)
        {
            throw new InvalidDataException(
                "Install-linking durable state is below its migration floor.");
        }

        InstallLinkingStoreFloorPayload floor = ReadFloor();
        if (floor.MinimumEnvelopeVersion > InstallLinkingStore.EnvelopeVersion
            || loadedGeneration < floor.Generation)
        {
            throw new InvalidDataException(
                "Install-linking durable state generation is below its local floor.");
        }

        if (loadedGeneration == floor.Generation)
        {
            byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(snapshot, _jsonOptions);
            byte[] digest = SHA256.HashData(bytes);
            byte[] expectedDigest = Convert.FromHexString(floor.SnapshotSha256!);
            try
            {
                if (!FixedEquals(digest, expectedDigest))
                {
                    throw new InvalidDataException(
                        "Install-linking durable state digest does not match its local floor.");
                }
            }
            finally
            {
                CryptographicOperations.ZeroMemory(bytes);
                CryptographicOperations.ZeroMemory(digest);
                CryptographicOperations.ZeroMemory(expectedDigest);
            }
        }
    }

    private InstallLinkingStoreFloorPayload ReadFloor()
    {
        byte[] bytes = InstallLinkingImportFileSystem.ReadOwnerOnlyFile(
            FloorPath,
            InstallLinkingStore.MaxSnapshotBytes);
        try
        {
            using JsonDocument document = StrictDocument(bytes);
            JsonElement root = document.RootElement;
            RequireExactProperties(
                root,
                ["format", "version", "protectedPayload"],
                "Install-linking local floor envelope");
            if (root.GetProperty("format").GetString()
                    != InstallLinkingStore.FloorFormat
                || !root.GetProperty("version").TryGetInt32(out int version)
                || version != 1)
            {
                throw new InvalidDataException(
                    "Install-linking local floor is invalid.");
            }

            string? protectedPayload =
                root.GetProperty("protectedPayload").GetString();
            if (string.IsNullOrWhiteSpace(protectedPayload))
            {
                throw new InvalidDataException(
                    "Install-linking local floor is invalid.");
            }

            byte[] payload = Convert.FromBase64String(
                _floorProtector.Unprotect(protectedPayload));
            try
            {
                using JsonDocument payloadDocument = StrictDocument(payload);
                RequireExactProperties(
                    payloadDocument.RootElement,
                    ["minimumEnvelopeVersion", "generation", "snapshotSha256"],
                    "Install-linking local floor payload");
                InstallLinkingStoreFloorPayload floor =
                    JsonSerializer.Deserialize<InstallLinkingStoreFloorPayload>(
                        payload,
                        _jsonOptions)
                    ?? throw new InvalidDataException(
                        "Install-linking local floor is invalid.");
                if (floor.MinimumEnvelopeVersion < InstallLinkingStore.EnvelopeVersion
                    || floor.Generation < 1
                    || string.IsNullOrWhiteSpace(floor.SnapshotSha256)
                    || floor.SnapshotSha256.Length != 64
                    || !floor.SnapshotSha256.All(Uri.IsHexDigit))
                {
                    throw new InvalidDataException(
                        "Install-linking local floor is invalid.");
                }

                return floor;
            }
            finally
            {
                CryptographicOperations.ZeroMemory(payload);
            }
        }
        finally
        {
            CryptographicOperations.ZeroMemory(bytes);
        }
    }

    private void WriteFloor(long generation, ReadOnlySpan<byte> snapshotBytes)
    {
        byte[] snapshotDigest = SHA256.HashData(snapshotBytes);
        byte[] floorPayload = JsonSerializer.SerializeToUtf8Bytes(
            new InstallLinkingStoreFloorPayload(
                InstallLinkingStore.EnvelopeVersion,
                generation,
                Convert.ToHexString(snapshotDigest).ToLowerInvariant()),
            _jsonOptions);
        byte[]? floorBytes = null;
        try
        {
            string protectedPayload = _floorProtector.Protect(
                Convert.ToBase64String(floorPayload));
            floorBytes = JsonSerializer.SerializeToUtf8Bytes(
                new InstallLinkingStoreFloorEnvelope(
                    InstallLinkingStore.FloorFormat,
                    1,
                    protectedPayload),
                _jsonOptions);
            InstallLinkingImportFileSystem.WriteOwnerOnlyFileAtomically(
                FloorPath,
                floorBytes,
                overwrite: true);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(snapshotDigest);
            CryptographicOperations.ZeroMemory(floorPayload);
            if (floorBytes is not null)
            {
                CryptographicOperations.ZeroMemory(floorBytes);
            }
        }
    }

    private static void ValidateGenerationOneAuthority(
        InstallLinkingAuthoritativeEnvelope envelope)
    {
        if (envelope.Generation != 1
            || envelope.CommitId is null
            || envelope.CommitId == Guid.Empty
            || envelope.EnvelopeVersion != InstallLinkingStore.EnvelopeVersion
            || envelope.SnapshotSha256 is not { Length: SHA256.HashSizeInBytes }
            || envelope.EnvelopeSha256 is not { Length: SHA256.HashSizeInBytes }
            || envelope.ProtectedEnvelope is not
                { Length: > 0 and <= InstallLinkingStore.MaxSnapshotBytes })
        {
            throw new InvalidDataException(
                "The InstallLinking one-shot import authority result is invalid.");
        }
    }

    private static void RequireDigest(
        ReadOnlySpan<byte> bytes,
        byte[] expected,
        string label)
    {
        if (!DigestMatches(bytes, expected))
        {
            throw new CryptographicException(
                $"The InstallLinking import {label} digest does not match.");
        }
    }

    private static bool DigestMatches(
        ReadOnlySpan<byte> bytes,
        byte[] expected)
    {
        byte[] actual = SHA256.HashData(bytes);
        try
        {
            return FixedEquals(actual, expected);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(actual);
        }
    }

    private static JsonDocument StrictDocument(ReadOnlyMemory<byte> bytes)
        => JsonDocument.Parse(
            bytes,
            new JsonDocumentOptions
            {
                AllowTrailingCommas = false,
                CommentHandling = JsonCommentHandling.Disallow,
                MaxDepth = 128
            });

    private static void RequireExactProperties(
        JsonElement root,
        IReadOnlyCollection<string> expected,
        string label)
    {
        if (root.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException($"{label} is invalid.");
        }

        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonProperty property in root.EnumerateObject())
        {
            if (!expected.Contains(property.Name) || !seen.Add(property.Name))
            {
                throw new InvalidDataException($"{label} is invalid.");
            }
        }

        if (seen.Count != expected.Count)
        {
            throw new InvalidDataException($"{label} is invalid.");
        }
    }

    private static bool FixedEquals(byte[]? left, byte[]? right)
    {
        if (left is null || right is null)
        {
            return left is null && right is null;
        }

        return left.Length == right.Length
               && CryptographicOperations.FixedTimeEquals(left, right);
    }

    private static void ClearRequest(InstallLinkingEnvelopeCompareExchangeRequest request)
    {
        if (request.ExpectedEnvelopeSha256 is not null)
        {
            CryptographicOperations.ZeroMemory(request.ExpectedEnvelopeSha256);
        }

        CryptographicOperations.ZeroMemory(request.SnapshotSha256);
        CryptographicOperations.ZeroMemory(request.EnvelopeSha256);
        CryptographicOperations.ZeroMemory(request.ProtectedEnvelope);
    }

    public void Dispose() => _writerLease.Dispose();
}

internal sealed class InstallLinkingPostgresImportIntent : IDisposable
{
    public const int MaximumSerializedBytes =
        (InstallLinkingStore.MaxSnapshotBytes * 3 / 2) + (64 * 1024);
    private const string Format = "chummer.install-linking-postgres-import-intent";
    private const int Version = 1;
    private const string PreparedState = "prepared";
    private const string CommittedPendingMirrorState = "committed_pending_mirror";

    private InstallLinkingPostgresImportIntent(
        string state,
        Guid commitId,
        byte[] snapshotSha256,
        byte[] envelopeSha256,
        byte[] protectedEnvelope,
        DateTimeOffset createdAtUtc)
    {
        State = state;
        CommitId = commitId;
        SnapshotSha256 = snapshotSha256;
        EnvelopeSha256 = envelopeSha256;
        ProtectedEnvelope = protectedEnvelope;
        CreatedAtUtc = createdAtUtc;
    }

    public string State { get; private set; }
    public Guid CommitId { get; }
    public byte[] SnapshotSha256 { get; }
    public byte[] EnvelopeSha256 { get; }
    public byte[] ProtectedEnvelope { get; }
    public DateTimeOffset CreatedAtUtc { get; }

    public static InstallLinkingPostgresImportIntent FromRequest(
        InstallLinkingEnvelopeCompareExchangeRequest request,
        DateTimeOffset createdAtUtc)
    {
        ValidateRequest(request);
        return new(
            PreparedState,
            request.CommitId,
            request.SnapshotSha256.ToArray(),
            request.EnvelopeSha256.ToArray(),
            request.ProtectedEnvelope.ToArray(),
            createdAtUtc);
    }

    public InstallLinkingEnvelopeCompareExchangeRequest CreateRequest()
        => new(
            ExpectedGeneration: 0,
            ExpectedCommitId: null,
            ExpectedEnvelopeSha256: null,
            NextGeneration: 1,
            CommitId,
            EnvelopeVersion: InstallLinkingStore.EnvelopeVersion,
            SnapshotSha256: SnapshotSha256.ToArray(),
            EnvelopeSha256: EnvelopeSha256.ToArray(),
            ProtectedEnvelope: ProtectedEnvelope.ToArray());

    public bool Matches(InstallLinkingAuthoritativeEnvelope envelope)
        => envelope.Generation == 1
           && envelope.CommitId == CommitId
           && envelope.EnvelopeVersion == InstallLinkingStore.EnvelopeVersion
           && FixedEquals(envelope.SnapshotSha256, SnapshotSha256)
           && FixedEquals(envelope.EnvelopeSha256, EnvelopeSha256)
           && FixedEquals(envelope.ProtectedEnvelope, ProtectedEnvelope);

    public void MarkCommittedPendingMirror()
        => State = CommittedPendingMirrorState;

    public byte[] Serialize(JsonSerializerOptions options)
    {
        Validate();
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(
            new InstallLinkingPostgresImportIntentModel(
                Format,
                Version,
                State,
                ExpectedGeneration: 0,
                NextGeneration: 1,
                CommitId,
                EnvelopeVersion: InstallLinkingStore.EnvelopeVersion,
                SnapshotSha256,
                EnvelopeSha256,
                ProtectedEnvelope,
                CreatedAtUtc),
            options);
        if (bytes.Length > MaximumSerializedBytes)
        {
            CryptographicOperations.ZeroMemory(bytes);
            throw new InvalidDataException(
                "The InstallLinking import intent is too large.");
        }

        return bytes;
    }

    public static InstallLinkingPostgresImportIntent Deserialize(
        ReadOnlyMemory<byte> bytes,
        JsonSerializerOptions options)
    {
        using JsonDocument document = JsonDocument.Parse(
            bytes,
            new JsonDocumentOptions
            {
                AllowTrailingCommas = false,
                CommentHandling = JsonCommentHandling.Disallow,
                MaxDepth = 32
            });
        RequireExactProperties(document.RootElement);
        InstallLinkingPostgresImportIntentModel model =
            JsonSerializer.Deserialize<InstallLinkingPostgresImportIntentModel>(
                bytes.Span,
                options)
            ?? throw new InvalidDataException(
                "The InstallLinking import intent is invalid.");
        if (model.Format != Format
            || model.Version != Version
            || model.ExpectedGeneration != 0
            || model.NextGeneration != 1
            || model.EnvelopeVersion != InstallLinkingStore.EnvelopeVersion)
        {
            ClearModel(model);
            throw new InvalidDataException(
                "The InstallLinking import intent is invalid.");
        }

        var intent = new InstallLinkingPostgresImportIntent(
            model.State,
            model.CommitId,
            model.SnapshotSha256,
            model.EnvelopeSha256,
            model.ProtectedEnvelope,
            model.CreatedAtUtc);
        try
        {
            intent.Validate();
            return intent;
        }
        catch
        {
            intent.Dispose();
            throw;
        }
    }

    private void Validate()
    {
        if (State is not (PreparedState or CommittedPendingMirrorState)
            || CommitId == Guid.Empty
            || SnapshotSha256.Length != SHA256.HashSizeInBytes
            || EnvelopeSha256.Length != SHA256.HashSizeInBytes
            || ProtectedEnvelope.Length is <= 0 or > InstallLinkingStore.MaxSnapshotBytes
            || CreatedAtUtc == default
            || !DigestMatches(ProtectedEnvelope, EnvelopeSha256))
        {
            throw new InvalidDataException(
                "The InstallLinking import intent is invalid.");
        }
    }

    private static void ValidateRequest(
        InstallLinkingEnvelopeCompareExchangeRequest request)
    {
        if (request.ExpectedGeneration != 0
            || request.ExpectedCommitId is not null
            || request.ExpectedEnvelopeSha256 is not null
            || request.NextGeneration != 1
            || request.CommitId == Guid.Empty
            || request.EnvelopeVersion != InstallLinkingStore.EnvelopeVersion
            || request.SnapshotSha256.Length != SHA256.HashSizeInBytes
            || request.EnvelopeSha256.Length != SHA256.HashSizeInBytes
            || request.ProtectedEnvelope.Length is <= 0 or > InstallLinkingStore.MaxSnapshotBytes
            || !DigestMatches(request.ProtectedEnvelope, request.EnvelopeSha256))
        {
            throw new InvalidDataException(
                "The InstallLinking import request is invalid.");
        }
    }

    private static bool DigestMatches(ReadOnlySpan<byte> bytes, byte[] expected)
    {
        byte[] actual = SHA256.HashData(bytes);
        try
        {
            return FixedEquals(actual, expected);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(actual);
        }
    }

    private static bool FixedEquals(byte[]? left, byte[]? right)
    {
        if (left is null || right is null)
        {
            return left is null && right is null;
        }

        return left.Length == right.Length
               && CryptographicOperations.FixedTimeEquals(left, right);
    }

    private static void RequireExactProperties(JsonElement root)
    {
        string[] names =
        [
            "format", "version", "state", "expectedGeneration", "nextGeneration",
            "commitId", "envelopeVersion", "snapshotSha256", "envelopeSha256",
            "protectedEnvelope", "createdAtUtc"
        ];
        var expected = new HashSet<string>(names, StringComparer.Ordinal);
        var seen = new HashSet<string>(StringComparer.Ordinal);
        if (root.ValueKind != JsonValueKind.Object
            || root.EnumerateObject().Any(property =>
                !expected.Contains(property.Name) || !seen.Add(property.Name))
            || seen.Count != expected.Count)
        {
            throw new InvalidDataException(
                "The InstallLinking import intent shape is invalid.");
        }
    }

    private static void ClearModel(InstallLinkingPostgresImportIntentModel model)
    {
        CryptographicOperations.ZeroMemory(model.SnapshotSha256);
        CryptographicOperations.ZeroMemory(model.EnvelopeSha256);
        CryptographicOperations.ZeroMemory(model.ProtectedEnvelope);
    }

    public void Dispose()
    {
        CryptographicOperations.ZeroMemory(SnapshotSha256);
        CryptographicOperations.ZeroMemory(EnvelopeSha256);
        CryptographicOperations.ZeroMemory(ProtectedEnvelope);
    }
}

internal sealed record InstallLinkingPostgresImportIntentModel(
    string Format,
    int Version,
    string State,
    long ExpectedGeneration,
    long NextGeneration,
    Guid CommitId,
    int EnvelopeVersion,
    byte[] SnapshotSha256,
    byte[] EnvelopeSha256,
    byte[] ProtectedEnvelope,
    DateTimeOffset CreatedAtUtc);

internal static class InstallLinkingImportFileSystem
{
    private const UnixFileMode OwnerDirectoryMode =
        UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute;
    private const UnixFileMode OwnerFileMode =
        UnixFileMode.UserRead | UnixFileMode.UserWrite;

    public static void PrepareStorageDirectory(string storagePath, bool production)
    {
        string directory = Path.GetDirectoryName(storagePath)
            ?? throw new InvalidOperationException(
                "The InstallLinking storage directory is invalid.");
        RejectReparsePath(directory, includeLeafAsFile: false);
        Directory.CreateDirectory(directory);
        RejectReparsePath(directory, includeLeafAsFile: false);
        if (LinuxSecureFile.IsSupportedPlatform)
        {
            LinuxSecureFile.PrepareOwnerOnlyDirectory(directory);
        }
        else
        {
            if (production)
            {
                throw new PlatformNotSupportedException(
                    "Install-linking secure import requires Linux in production.");
            }

            if (!OperatingSystem.IsWindows())
            {
                File.SetUnixFileMode(directory, OwnerDirectoryMode);
            }
        }
    }

    public static FileStream AcquireWriterLease(string path, bool production)
    {
        RejectUnsafeFilePath(path);
        if (LinuxSecureFile.IsSupportedPlatform)
        {
            return LinuxSecureFile.AcquireOwnerOnlyWriterLease(path);
        }

        if (production)
        {
            throw new PlatformNotSupportedException(
                "Install-linking secure import locking requires Linux.");
        }

        return new FileStream(
            path,
            new FileStreamOptions
            {
                Mode = FileMode.OpenOrCreate,
                Access = FileAccess.ReadWrite,
                Share = FileShare.None,
                BufferSize = 1,
                Options = FileOptions.WriteThrough
            });
    }

    public static byte[] ReadOwnerOnlyFile(string path, int maximumBytes)
    {
        if (LinuxSecureFile.IsSupportedPlatform)
        {
            return LinuxSecureFile.ReadOwnerOnlyRegularFile(
                path,
                maximumBytes,
                repairOwnerMode: false);
        }

        RejectUnsafeFilePath(path);
        FileInfo file = new(path);
        if (!file.Exists
            || file.LinkTarget is not null
            || file.Length is <= 0
            || file.Length > maximumBytes)
        {
            throw new InvalidDataException(
                "The InstallLinking import file is invalid.");
        }

        return File.ReadAllBytes(path);
    }

    public static void WriteOwnerOnlyFileAtomically(
        string destinationPath,
        ReadOnlySpan<byte> bytes,
        bool overwrite)
    {
        if (bytes.Length <= 0)
        {
            throw new InvalidDataException(
                "The InstallLinking import file cannot be empty.");
        }

        RejectUnsafeFilePath(destinationPath);
        string directory = Path.GetDirectoryName(destinationPath)!;
        string fileName = Path.GetFileName(destinationPath);
        string temporaryPath = Path.Combine(
            directory,
            $".{fileName}.tmp-{Guid.NewGuid():N}");
        try
        {
            FileStreamOptions options = new()
            {
                Mode = FileMode.CreateNew,
                Access = FileAccess.Write,
                Share = FileShare.None,
                BufferSize = 64 * 1024,
                Options = FileOptions.WriteThrough
            };
            if (!OperatingSystem.IsWindows())
            {
                options.UnixCreateMode = OwnerFileMode;
            }

            using (FileStream stream = new(temporaryPath, options))
            {
                stream.Write(bytes);
                stream.Flush(flushToDisk: true);
            }

            TightenFileMode(temporaryPath);
            RejectUnsafeFilePath(destinationPath);
            File.Move(temporaryPath, destinationPath, overwrite);
            TightenFileMode(destinationPath);
            FlushDirectory(directory);
        }
        finally
        {
            TryDelete(temporaryPath);
        }
    }

    public static void DeleteOwnerOnlyFileDurably(
        string path,
        int maximumBytes)
    {
        if (!File.Exists(path))
        {
            return;
        }

        byte[] bytes = ReadOwnerOnlyFile(path, maximumBytes);
        try
        {
            File.Delete(path);
            if (File.Exists(path))
            {
                throw new IOException(
                    "The InstallLinking import intent could not be deleted.");
            }

            FlushDirectory(Path.GetDirectoryName(path)!);
        }
        finally
        {
            CryptographicOperations.ZeroMemory(bytes);
        }
    }

    private static void RejectUnsafeFilePath(string path)
    {
        RejectReparsePath(path, includeLeafAsFile: true);
        if (Directory.Exists(path))
        {
            throw new InvalidOperationException(
                "The InstallLinking import path must be a regular file.");
        }
    }

    private static void RejectReparsePath(string path, bool includeLeafAsFile)
    {
        FileSystemInfo leaf = includeLeafAsFile
            ? new FileInfo(path)
            : new DirectoryInfo(path);
        RejectReparsePoint(leaf);
        DirectoryInfo? directory = includeLeafAsFile
            ? new FileInfo(path).Directory
            : new DirectoryInfo(path).Parent;
        while (directory is not null)
        {
            RejectReparsePoint(directory);
            directory = directory.Parent;
        }
    }

    private static void RejectReparsePoint(FileSystemInfo entry)
    {
        entry.Refresh();
        try
        {
            if (entry.LinkTarget is not null)
            {
                throw new InvalidOperationException(
                    "The InstallLinking import path cannot contain links.");
            }
        }
        catch (PlatformNotSupportedException)
        {
            // Attribute validation remains available on platforms without LinkTarget.
        }

        if (entry.Exists
            && (entry.Attributes & FileAttributes.ReparsePoint) != 0)
        {
            throw new InvalidOperationException(
                "The InstallLinking import path cannot contain reparse points.");
        }
    }

    private static void TightenFileMode(string path)
    {
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(path, OwnerFileMode);
        }
    }

    private static void FlushDirectory(string directory)
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        int descriptor = NativeOpen(directory, 0);
        if (descriptor < 0)
        {
            throw new IOException(
                "The InstallLinking import directory could not be synchronized.");
        }

        using var handle = new SafeFileHandle((IntPtr)descriptor, ownsHandle: true);
        if (NativeFsync(descriptor) != 0)
        {
            throw new IOException(
                "The InstallLinking import directory could not be synchronized.");
        }
    }

    private static void TryDelete(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch
        {
            // Preserve the primary persistence failure.
        }
    }

    [DllImport("libc", EntryPoint = "open", SetLastError = true)]
    private static extern int NativeOpen(string path, int flags);

    [DllImport("libc", EntryPoint = "fsync", SetLastError = true)]
    private static extern int NativeFsync(int descriptor);
}
