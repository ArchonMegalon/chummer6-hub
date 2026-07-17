using System.Security.Cryptography;
using System.Runtime.InteropServices;
using System.Text.Json;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking.Postgres;
using Microsoft.AspNetCore.DataProtection;

namespace Chummer.Run.Api.Services.InstallLinking;

public sealed class InstallLinkingStore : IDisposable
{
    internal const string EnvelopeFormat = "chummer.install-linking-store";
    internal const int EnvelopeVersion = 2;
    internal const int LegacyEnvelopeVersion = 1;
    internal const string DataProtectionPurpose = "Chummer.Run.Api.InstallLinkingStore.snapshot.v2";
    internal const string LegacyDataProtectionPurpose = "Chummer.Run.Api.InstallLinkingStore.snapshot.v1";
    internal const string FloorFormat = "chummer.install-linking-store.floor";
    internal const string FloorDataProtectionPurpose = "Chummer.Run.Api.InstallLinkingStore.floor.v1";
    private const string QuarantineFormat = "chummer.install-linking-store.quarantine-metadata";
    private const int MaximumQuarantineReceipts = 8;
    private const long MaximumQuarantineReceiptBytes = 64 * 1024;
    private const int MaximumQuarantineDirectoryScanEntries = 4096;
    private static readonly TimeSpan QuarantineRetention = TimeSpan.FromDays(30);
    internal const int MaxSnapshotBytes = 64 * 1024 * 1024;
    private static readonly TimeSpan PostgresOperationDeadline = TimeSpan.FromSeconds(15);
    private const UnixFileMode OwnerDirectoryMode =
        UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute;
    private const UnixFileMode OwnerFileMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;
    private static readonly HashSet<string> EnvelopePropertyNames =
        new(StringComparer.Ordinal) { "format", "version", "generation", "protectedPayload" };
    private static readonly HashSet<string> FloorEnvelopePropertyNames =
        new(StringComparer.Ordinal) { "format", "version", "protectedPayload" };
    private static readonly HashSet<string> FloorPayloadPropertyNames =
        new(StringComparer.Ordinal) { "minimumEnvelopeVersion", "generation", "snapshotSha256" };
    private static readonly HashSet<string> LegacyPropertyNames =
        new(StringComparer.Ordinal)
        {
            "receipts",
            "claimTickets",
            "browserCallbacks",
            "installations",
            "grants",
            "personalizedInstallScripts"
        };
    private readonly IDataProtector _protector;
    private readonly IDataProtector _legacyProtector;
    private readonly IDataProtector _floorProtector;
    private readonly ILogger<InstallLinkingStore> _logger;
    private readonly InstallLinkingPostgresAuthorityCoordinator? _postgresAuthority;
    private readonly string _storagePath;
    private readonly string _floorPath;
    private readonly string _writerLeasePath;
    private FileStream? _writerLease;
    private long _generation;
    private Guid? _authorityCommitId;
    private byte[]? _authorityEnvelopeSha256;
    private long _persistenceAttempts;
    private bool _terminalPersistenceFailure;
    private InstallLinkingStoreSnapshot _committedSnapshot = EmptySnapshot();
    private readonly object _gate = new();
    private readonly JsonSerializerOptions _jsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    /// <summary>
    /// Compatibility constructor for non-production callers that predate encrypted
    /// install-linking snapshots. Production must provide the shared persistent data
    /// protection authority explicitly so a restart cannot orphan protected state.
    /// </summary>
    public InstallLinkingStore(
        IConfiguration configuration,
        ILogger<InstallLinkingStore> logger)
        : this(configuration, CreateCompatibilityDataProtectionProvider(configuration), logger)
    {
    }

    public InstallLinkingStore(
        IConfiguration configuration,
        IDataProtectionProvider dataProtectionProvider,
        ILogger<InstallLinkingStore> logger)
        : this(configuration, dataProtectionProvider, logger, postgresAuthority: null)
    {
    }

    private static IDataProtectionProvider CreateCompatibilityDataProtectionProvider(
        IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        if (string.Equals(
                configuration["ASPNETCORE_ENVIRONMENT"],
                Environments.Production,
                StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(
                "Production install-linking storage requires an explicit persistent data-protection provider.");
        }

        return new EphemeralDataProtectionProvider();
    }

    internal InstallLinkingStore(
        IConfiguration configuration,
        IDataProtectionProvider dataProtectionProvider,
        ILogger<InstallLinkingStore> logger,
        InstallLinkingPostgresAuthorityCoordinator? postgresAuthority)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        ArgumentNullException.ThrowIfNull(dataProtectionProvider);
        ArgumentNullException.ThrowIfNull(logger);

        _protector = dataProtectionProvider.CreateProtector(DataProtectionPurpose);
        _legacyProtector = dataProtectionProvider.CreateProtector(LegacyDataProtectionPurpose);
        _floorProtector = dataProtectionProvider.CreateProtector(FloorDataProtectionPurpose);
        _logger = logger;
        _postgresAuthority = postgresAuthority;
        bool production = string.Equals(
            configuration["ASPNETCORE_ENVIRONMENT"],
            Environments.Production,
            StringComparison.OrdinalIgnoreCase);
        _storagePath = ResolveStoragePath(configuration);
        _floorPath = $"{_storagePath}.floor";
        _writerLeasePath = $"{_storagePath}.writer.lock";
        if (production && !LinuxSecureFile.IsSupportedPlatform)
        {
            throw new PlatformNotSupportedException("Install-linking secure storage requires Linux in production.");
        }

        EnsureSecureStorageDirectory();
        _writerLease = AcquireWriterLease(production);
        try
        {
            PruneQuarantineReceipts(
                Path.GetDirectoryName(_storagePath)!,
                Path.GetFileName(_storagePath),
                reservedReceiptSlots: 0,
                reservedReceiptBytes: 0);
            if (_postgresAuthority is null)
            {
                Load();
            }
            else
            {
                LoadFromPostgresAuthority();
            }
        }
        catch
        {
            _writerLease.Dispose();
            _writerLease = null;
            throw;
        }
    }

    public object Gate => !_terminalPersistenceFailure
        ? _gate
        : throw new InvalidOperationException("Install-linking durable store is fail-closed after a persistence failure.");
    public string StoragePath => _storagePath;
    public bool IsHealthy => !_terminalPersistenceFailure;
    internal long PersistenceAttempts => Interlocked.Read(ref _persistenceAttempts);
    public Dictionary<string, DownloadReceiptDto> ReceiptsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, InstallClaimTicketDto> ClaimTicketsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, InstallBrowserCallbackDto> BrowserCallbacksById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, ClaimedInstallationDto> InstallationsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, InstallationGrantDto> GrantsById { get; } = new(StringComparer.OrdinalIgnoreCase);
    public Dictionary<string, PersonalizedInstallScriptLinkDto> PersonalizedInstallScriptsById { get; } = new(StringComparer.OrdinalIgnoreCase);

    internal InstallLinkingEnvelopeCompareExchangeRequest CreateOneShotImportRequest()
    {
        if (_postgresAuthority is not null)
        {
            throw new InvalidOperationException(
                "An authority-backed InstallLinking store cannot be used as a legacy import source.");
        }

        lock (Gate)
        {
            InstallLinkingStoreSnapshot snapshot = BuildRetainedSnapshot(DateTimeOffset.UtcNow);
            ValidateSnapshot(snapshot);
            byte[] snapshotBytes = JsonSerializer.SerializeToUtf8Bytes(snapshot, _jsonOptions);
            try
            {
                string protectedPayload = _protector.Protect(Convert.ToBase64String(snapshotBytes));
                byte[] envelopeBytes = JsonSerializer.SerializeToUtf8Bytes(
                    new InstallLinkingStoreEnvelope(
                        EnvelopeFormat,
                        EnvelopeVersion,
                        Generation: 1,
                        ProtectedPayload: protectedPayload),
                    _jsonOptions);
                if (snapshotBytes.Length > MaxSnapshotBytes
                    || envelopeBytes.Length > MaxSnapshotBytes)
                {
                    throw new InvalidOperationException(
                        "Install-linking one-shot import payload exceeds the durable storage limit.");
                }

                return new InstallLinkingEnvelopeCompareExchangeRequest(
                    ExpectedGeneration: 0,
                    ExpectedCommitId: null,
                    ExpectedEnvelopeSha256: null,
                    NextGeneration: 1,
                    CommitId: Guid.NewGuid(),
                    EnvelopeVersion: EnvelopeVersion,
                    SnapshotSha256: SHA256.HashData(snapshotBytes),
                    EnvelopeSha256: SHA256.HashData(envelopeBytes),
                    ProtectedEnvelope: envelopeBytes);
            }
            finally
            {
                CryptographicOperations.ZeroMemory(snapshotBytes);
            }
        }
    }

    internal void CompleteOneShotImportMirror(
        InstallLinkingAuthoritativeEnvelope authoritativeEnvelope)
    {
        ArgumentNullException.ThrowIfNull(authoritativeEnvelope);
        if (_postgresAuthority is not null
            || authoritativeEnvelope.Generation != 1
            || authoritativeEnvelope.EnvelopeVersion != EnvelopeVersion
            || authoritativeEnvelope.ProtectedEnvelope is null
            || authoritativeEnvelope.SnapshotSha256 is null
            || authoritativeEnvelope.EnvelopeSha256 is null)
        {
            throw new InvalidDataException(
                "The InstallLinking one-shot import authority result is invalid.");
        }

        lock (Gate)
        {
            byte[] envelopeBytes = authoritativeEnvelope.ProtectedEnvelope.ToArray();
            byte[]? snapshotBytes = null;
            try
            {
                byte[] actualEnvelopeSha256 = SHA256.HashData(envelopeBytes);
                try
                {
                    if (!FixedEquals(
                            actualEnvelopeSha256,
                            authoritativeEnvelope.EnvelopeSha256))
                    {
                        throw new CryptographicException(
                            "The InstallLinking one-shot import envelope digest does not match.");
                    }
                }
                finally
                {
                    CryptographicOperations.ZeroMemory(actualEnvelopeSha256);
                }

                using JsonDocument document = JsonDocument.Parse(envelopeBytes);
                ProtectedEnvelopeDescriptor descriptor =
                    ReadStrictProtectedPayload(document.RootElement);
                if (descriptor.Version != EnvelopeVersion
                    || descriptor.Generation != authoritativeEnvelope.Generation)
                {
                    throw new InvalidDataException(
                        "The InstallLinking one-shot import envelope generation is invalid.");
                }

                snapshotBytes = Convert.FromBase64String(
                    _protector.Unprotect(descriptor.ProtectedPayload));
                byte[] actualSnapshotSha256 = SHA256.HashData(snapshotBytes);
                try
                {
                    if (!FixedEquals(
                            actualSnapshotSha256,
                            authoritativeEnvelope.SnapshotSha256))
                    {
                        throw new CryptographicException(
                            "The InstallLinking one-shot import snapshot digest does not match.");
                    }
                }
                finally
                {
                    CryptographicOperations.ZeroMemory(actualSnapshotSha256);
                }

                InstallLinkingStoreSnapshot snapshot = DeserializeSnapshot(snapshotBytes);
                ValidateSnapshot(snapshot);
                // This is the only code path permitted to lower a legacy local generation: the
                // operator explicitly confirmed an empty PostgreSQL authority, and the exact
                // generation-one bytes have already committed there.
                PersistBytesAtomically(_storagePath, envelopeBytes);
                PersistFloor(authoritativeEnvelope.Generation, snapshotBytes);
                _generation = authoritativeEnvelope.Generation;
                ApplySnapshotLocked(snapshot);
                _committedSnapshot = snapshot;
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
    }

    public void PersistLocked()
    {
        Interlocked.Increment(ref _persistenceAttempts);
        if (_terminalPersistenceFailure)
        {
            throw new InvalidOperationException("Install-linking durable store is fail-closed after a persistence failure.");
        }

        try
        {
            InstallLinkingStoreSnapshot snapshot = BuildRetainedSnapshot(DateTimeOffset.UtcNow);
            PersistSnapshot(snapshot);
            ApplySnapshotLocked(snapshot);
            _committedSnapshot = snapshot;
        }
        catch
        {
            // Callers mutate the public dictionaries while holding Gate. Restore the last
            // durable view so a failed serialization/fsync/CAS cannot leave oversized or
            // partially-authorized state live in memory.
            ApplySnapshotLocked(_committedSnapshot);
            _terminalPersistenceFailure = true;
            throw;
        }
    }

    private InstallLinkingStoreSnapshot BuildRetainedSnapshot(DateTimeOffset now)
        => BuildRetainedSnapshot(
            new InstallLinkingStoreSnapshot(
                ReceiptsById.Values.ToArray(),
                ClaimTicketsById.Values.ToArray(),
                BrowserCallbacksById.Values.ToArray(),
                InstallationsById.Values.ToArray(),
                GrantsById.Values.ToArray(),
                PersonalizedInstallScriptsById.Values.ToArray()),
            now);

    internal static InstallLinkingStoreSnapshot BuildRetainedSnapshot(
        InstallLinkingStoreSnapshot source,
        DateTimeOffset now)
    {
        ArgumentNullException.ThrowIfNull(source);
        InstallClaimTicketDto[] retainedTickets = (source.ClaimTickets ?? [])
            .Select(item => SanitizeTicketForRetention(item, now))
            .Where(item => item.ExpiresAtUtc >= now.AddDays(-7))
            .OrderByDescending(static item => item.CreatedAtUtc)
            .Take(2048)
            .ToArray();
        IReadOnlyDictionary<string, InstallClaimTicketDto> retainedTicketsById = retainedTickets
            .ToDictionary(static item => item.TicketId, StringComparer.OrdinalIgnoreCase);

        return new InstallLinkingStoreSnapshot(
            Receipts: (source.Receipts ?? [])
                .Select(item => SanitizeReceiptForRetention(item, retainedTicketsById, now))
                .OrderByDescending(static item => item.IssuedAtUtc)
                .Take(4096)
                .ToArray(),
            ClaimTickets: retainedTickets,
            BrowserCallbacks: (source.BrowserCallbacks ?? [])
                .Select(item => SanitizeCallbackForRetention(item, now))
                .Where(item => item.ExpiresAtUtc >= now.AddDays(-7))
                .OrderByDescending(static item => item.CreatedAtUtc)
                .Take(2048)
                .ToArray(),
            Installations: (source.Installations ?? [])
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .Take(2048)
                .ToArray(),
            Grants: (source.Grants ?? [])
                .Select(item => SanitizeGrantForRetention(item, now))
                .Where(item => item.ExpiresAtUtc >= now.AddDays(-31))
                .OrderByDescending(static item => item.IssuedAtUtc)
                .Take(4096)
                .ToArray(),
            PersonalizedInstallScripts: (source.PersonalizedInstallScripts ?? [])
                .Select(item => SanitizeScriptForRetention(item, now))
                .Where(item => item.ExpiresAtUtc >= now.AddDays(-7))
                .OrderByDescending(static item => item.IssuedAtUtc)
                .Take(1024)
                .ToArray());
    }

    private void PersistSnapshot(InstallLinkingStoreSnapshot snapshot)
    {
        ValidateSnapshot(snapshot);
        byte[] snapshotBytes = JsonSerializer.SerializeToUtf8Bytes(snapshot, _jsonOptions);
        try
        {
            if (snapshotBytes.Length > MaxSnapshotBytes)
            {
                throw new InvalidOperationException("Install-linking snapshot exceeds the durable storage limit.");
            }

            if (_postgresAuthority is not null)
            {
                PersistSnapshotToPostgres(snapshotBytes);
                return;
            }

            VerifyCurrentGenerationForCompareAndSwap();
            long nextGeneration = checked(_generation + 1);
            string protectedPayload = _protector.Protect(Convert.ToBase64String(snapshotBytes));
            byte[] envelopeBytes = JsonSerializer.SerializeToUtf8Bytes(
                new InstallLinkingStoreEnvelope(EnvelopeFormat, EnvelopeVersion, nextGeneration, protectedPayload),
                _jsonOptions);
            try
            {
                if (envelopeBytes.Length > MaxSnapshotBytes)
                {
                    throw new InvalidOperationException("Install-linking protected envelope exceeds the durable storage limit.");
                }

                PersistBytesAtomically(_storagePath, envelopeBytes);
                PersistFloor(nextGeneration, snapshotBytes);
                _generation = nextGeneration;
            }
            finally
            {
                CryptographicOperations.ZeroMemory(envelopeBytes);
            }
        }
        finally
        {
            CryptographicOperations.ZeroMemory(snapshotBytes);
        }
    }

    private void PersistSnapshotToPostgres(byte[] snapshotBytes)
    {
        InstallLinkingPostgresAuthorityCoordinator authority = _postgresAuthority
            ?? throw new InvalidOperationException("Install-linking PostgreSQL authority is unavailable.");
        VerifyCurrentGenerationForCompareAndSwap();
        long nextGeneration = checked(_generation + 1);
        string protectedPayload = _protector.Protect(Convert.ToBase64String(snapshotBytes));
        byte[] envelopeBytes = JsonSerializer.SerializeToUtf8Bytes(
            new InstallLinkingStoreEnvelope(
                EnvelopeFormat,
                EnvelopeVersion,
                nextGeneration,
                protectedPayload),
            _jsonOptions);
        if (envelopeBytes.Length > MaxSnapshotBytes)
        {
            throw new InvalidOperationException(
                "Install-linking protected envelope exceeds the durable storage limit.");
        }

        byte[] snapshotSha256 = SHA256.HashData(snapshotBytes);
        byte[] envelopeSha256 = SHA256.HashData(envelopeBytes);
        InstallLinkingEnvelopeCompareExchangeRequest? request = null;
        try
        {
            request = new InstallLinkingEnvelopeCompareExchangeRequest(
                ExpectedGeneration: _generation,
                ExpectedCommitId: _authorityCommitId,
                ExpectedEnvelopeSha256: _authorityEnvelopeSha256?.ToArray(),
                NextGeneration: nextGeneration,
                CommitId: Guid.NewGuid(),
                EnvelopeVersion: EnvelopeVersion,
                SnapshotSha256: snapshotSha256.ToArray(),
                EnvelopeSha256: envelopeSha256.ToArray(),
                ProtectedEnvelope: envelopeBytes.ToArray());
            using InstallLinkingEnvelopeCompareExchangeResult result =
                ExecuteAuthorityOperation(token =>
                    authority.CompareExchangeAsync(request, token));
            InstallLinkingAuthoritativeEnvelope committed = result.AuthoritativeEnvelope
                ?? throw new InvalidOperationException(
                    "Install-linking PostgreSQL compare-and-swap did not return an authoritative head.");
            if (!result.Committed || !MatchesCommittedRequest(committed, request))
            {
                throw new InvalidOperationException(
                    $"Install-linking PostgreSQL compare-and-swap failed ({SafeAuthorityCode(result.Code)}).");
            }

            // PostgreSQL has already committed at this point. Readiness remains bound to the
            // previous head until these exact database-returned bytes and their local floor are
            // durable. A mirror failure therefore terminalizes this process and cannot be
            // mistaken for an uncommitted mutation; the next startup repairs from PostgreSQL.
            PersistBytesAtomically(_storagePath, committed.ProtectedEnvelope!);
            PersistFloor(committed.Generation, snapshotBytes);
            _generation = committed.Generation;
            _authorityCommitId = committed.CommitId;
            ReplaceAuthorityEnvelopeDigest(committed.EnvelopeSha256);
            authority.BindValidatedLocalMirror(committed);
        }
        finally
        {
            if (request?.ExpectedEnvelopeSha256 is not null)
            {
                CryptographicOperations.ZeroMemory(request.ExpectedEnvelopeSha256);
            }

            if (request is not null)
            {
                CryptographicOperations.ZeroMemory(request.SnapshotSha256);
                CryptographicOperations.ZeroMemory(request.EnvelopeSha256);
                CryptographicOperations.ZeroMemory(request.ProtectedEnvelope);
            }

            CryptographicOperations.ZeroMemory(snapshotSha256);
            CryptographicOperations.ZeroMemory(envelopeSha256);
            CryptographicOperations.ZeroMemory(envelopeBytes);
        }
    }

    private void PersistBytesAtomically(string destinationPath, ReadOnlySpan<byte> envelopeBytes)
    {
        EnsureSecureStorageDirectory();
        RejectUnsafePath(destinationPath);

        string directory = Path.GetDirectoryName(destinationPath)!;
        string fileName = Path.GetFileName(destinationPath);
        string tempPath = Path.Combine(directory, $".{fileName}.tmp-{Guid.NewGuid():N}");
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

            using (FileStream stream = new(tempPath, options))
            {
                stream.Write(envelopeBytes);
                stream.Flush(flushToDisk: true);
            }

            TightenFileMode(tempPath);
            RejectUnsafePath(destinationPath);
            MoveDurably(tempPath, destinationPath);
            TightenFileMode(destinationPath);
            FlushDirectory(directory);
        }
        finally
        {
            TryDeleteTemporaryFile(tempPath);
        }
    }

    private void LoadFromPostgresAuthority()
    {
        InstallLinkingPostgresAuthorityCoordinator authority = _postgresAuthority
            ?? throw new InvalidOperationException("Install-linking PostgreSQL authority is unavailable.");
        lock (Gate)
        {
            InstallLinkingPostgresReadiness schemaReadiness = ExecuteAuthorityOperation(
                token => authority.CheckReadinessAsync(token));
            if (!schemaReadiness.Ready)
            {
                throw new InvalidOperationException(
                    $"Install-linking PostgreSQL authority is not ready ({SafeAuthorityCode(schemaReadiness.Code)}).");
            }

            using InstallLinkingAuthoritativeEnvelope head = ExecuteAuthorityOperation(
                token => authority.ReadCurrentAsync(token));
            if (head.IsEmpty)
            {
                RejectUnsafeStorageFile();
                RejectUnsafePath(_floorPath);
                if (File.Exists(_storagePath) || File.Exists(_floorPath))
                {
                    // Local state is never promoted implicitly. The one-shot operator import
                    // lane must prove an empty authority and is the only permitted transition.
                    throw new InvalidOperationException(
                        "Install-linking local durable state requires an explicit one-shot PostgreSQL import.");
                }

                _generation = 0;
                _authorityCommitId = null;
                ReplaceAuthorityEnvelopeDigest(null);
                ClearSnapshotLocked();
                _committedSnapshot = EmptySnapshot();
                authority.BindValidatedLocalMirror(head);
                RequireCurrentAuthorityBinding(authority);
                _logger.LogInformation(
                    "InstallLinkingStore started from an empty PostgreSQL authority.");
                return;
            }

            byte[] envelopeBytes = head.ProtectedEnvelope?.ToArray()
                ?? throw new InvalidDataException(
                    "The InstallLinking PostgreSQL authority envelope is missing.");
            byte[]? snapshotBytes = null;
            try
            {
                using JsonDocument document = JsonDocument.Parse(
                    envelopeBytes,
                    new JsonDocumentOptions
                    {
                        AllowTrailingCommas = false,
                        CommentHandling = JsonCommentHandling.Disallow,
                        MaxDepth = 128
                    });
                ProtectedEnvelopeDescriptor descriptor =
                    ReadStrictProtectedPayload(document.RootElement);
                if (descriptor.Version != EnvelopeVersion
                    || descriptor.Generation != head.Generation)
                {
                    throw new InvalidDataException(
                        "The InstallLinking PostgreSQL authority envelope generation is invalid.");
                }

                string encodedSnapshot = _protector.Unprotect(descriptor.ProtectedPayload);
                snapshotBytes = Convert.FromBase64String(encodedSnapshot);
                byte[] actualSnapshotSha256 = SHA256.HashData(snapshotBytes);
                try
                {
                    if (head.SnapshotSha256 is null
                        || actualSnapshotSha256.Length != head.SnapshotSha256.Length
                        || !CryptographicOperations.FixedTimeEquals(
                            actualSnapshotSha256,
                            head.SnapshotSha256))
                    {
                        throw new CryptographicException(
                            "The InstallLinking PostgreSQL snapshot digest does not match.");
                    }
                }
                finally
                {
                    CryptographicOperations.ZeroMemory(actualSnapshotSha256);
                }

                InstallLinkingStoreSnapshot snapshot = DeserializeSnapshot(snapshotBytes);
                ValidateSnapshot(snapshot);
                EnsureLocalMirrorDoesNotLead(head.Generation);

                // PostgreSQL is the only source of truth. Missing, behind, or damaged mirror
                // bytes are replaced with the exact validated authority bytes without advancing
                // the generation or running the ordinary mutation path.
                PersistBytesAtomically(_storagePath, envelopeBytes);
                PersistFloor(head.Generation, snapshotBytes);
                _generation = head.Generation;
                _authorityCommitId = head.CommitId;
                ReplaceAuthorityEnvelopeDigest(head.EnvelopeSha256);
                ApplySnapshotLocked(snapshot);
                _committedSnapshot = snapshot;
                authority.BindValidatedLocalMirror(head);
                RequireCurrentAuthorityBinding(authority);

                _logger.LogInformation(
                    "InstallLinkingStore loaded PostgreSQL authority generation {Generation} with {ReceiptCount} receipts, {TicketCount} claim tickets, {InstallCount} claimed installs, and {ScriptCount} personalized install scripts.",
                    head.Generation,
                    ReceiptsById.Count,
                    ClaimTicketsById.Count,
                    InstallationsById.Count,
                    PersonalizedInstallScriptsById.Count);
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
    }

    private void EnsureLocalMirrorDoesNotLead(long authorityGeneration)
    {
        RejectUnsafeStorageFile();
        RejectUnsafePath(_floorPath);
        long? localGeneration = TryReadLocalEnvelopeGeneration();
        if (localGeneration > authorityGeneration)
        {
            throw new InvalidDataException(
                "The InstallLinking local mirror is ahead of its PostgreSQL authority.");
        }

        long? floorGeneration = TryReadLocalFloorGeneration();
        if (floorGeneration > authorityGeneration)
        {
            throw new InvalidDataException(
                "The InstallLinking local floor is ahead of its PostgreSQL authority.");
        }
    }

    private long? TryReadLocalEnvelopeGeneration()
    {
        if (!File.Exists(_storagePath))
        {
            return null;
        }

        try
        {
            byte[] bytes = ReadSecureStorageBytes(_storagePath, repairOwnerMode: true);
            using JsonDocument document = JsonDocument.Parse(bytes);
            if (!ContainsAnyEnvelopeProperty(document.RootElement))
            {
                return null;
            }

            return ReadStrictProtectedPayload(document.RootElement).Generation;
        }
        catch (Exception exception) when (
            IsDurableStateFailure(exception)
            && exception is not UnsafeDurableStatePathException)
        {
            // PostgreSQL remains authoritative. A malformed local mirror carries no usable
            // generation claim and is repaired only after the authority envelope is validated.
            return null;
        }
    }

    private long? TryReadLocalFloorGeneration()
    {
        if (!File.Exists(_floorPath))
        {
            return null;
        }

        try
        {
            return ReadFloor().Generation;
        }
        catch (Exception exception) when (
            IsDurableStateFailure(exception)
            && exception is not UnsafeDurableStatePathException)
        {
            return null;
        }
    }

    private static void RequireCurrentAuthorityBinding(
        InstallLinkingPostgresAuthorityCoordinator authority)
    {
        InstallLinkingRollbackAuthorityReadiness readiness = authority.Evaluate();
        if (!readiness.Ready)
        {
            throw new InvalidOperationException(
                $"Install-linking PostgreSQL authority binding failed ({SafeAuthorityCode(readiness.Code)}).");
        }
    }

    private static T ExecuteAuthorityOperation<T>(
        Func<CancellationToken, Task<T>> operation)
    {
        using var deadline = new CancellationTokenSource(PostgresOperationDeadline);
        return operation(deadline.Token).GetAwaiter().GetResult();
    }

    private static bool MatchesCommittedRequest(
        InstallLinkingAuthoritativeEnvelope head,
        InstallLinkingEnvelopeCompareExchangeRequest request)
        => head.Generation == request.NextGeneration
           && head.CommitId == request.CommitId
           && head.EnvelopeVersion == request.EnvelopeVersion
           && FixedEquals(head.SnapshotSha256, request.SnapshotSha256)
           && FixedEquals(head.EnvelopeSha256, request.EnvelopeSha256)
           && FixedEquals(head.ProtectedEnvelope, request.ProtectedEnvelope);

    private static bool FixedEquals(byte[]? left, byte[]? right)
    {
        if (left is null || right is null)
        {
            return left is null && right is null;
        }

        return left.Length == right.Length
               && CryptographicOperations.FixedTimeEquals(left, right);
    }

    private void ReplaceAuthorityEnvelopeDigest(byte[]? digest)
    {
        if (_authorityEnvelopeSha256 is not null)
        {
            CryptographicOperations.ZeroMemory(_authorityEnvelopeSha256);
        }

        _authorityEnvelopeSha256 = digest?.ToArray();
    }

    private static string SafeAuthorityCode(string? code)
    {
        if (string.IsNullOrWhiteSpace(code)
            || code.Length > 64
            || code.Any(character => character != '_'
                && (character < 'a' || character > 'z')))
        {
            return "authority_failure";
        }

        return code;
    }

    private void Load()
    {
        lock (Gate)
        {
            byte[]? durableBytes = null;
            try
            {
                RejectUnsafeStorageFile();
                if (!File.Exists(_storagePath))
                {
                    if (File.Exists(_floorPath))
                    {
                        throw new InvalidOperationException("Install-linking durable state is missing below its migration floor.");
                    }

                    _committedSnapshot = EmptySnapshot();
                    _logger.LogInformation("InstallLinkingStore started with no durable snapshot.");
                    return;
                }

                durableBytes = ReadSecureStorageBytes(_storagePath, repairOwnerMode: true);
                InstallLinkingStoreSnapshot snapshot;
                bool legacyPlaintext;
                bool legacyEnvelope;
                long loadedGeneration;
                using (JsonDocument document = JsonDocument.Parse(
                           durableBytes,
                           new JsonDocumentOptions
                           {
                               AllowTrailingCommas = false,
                               CommentHandling = JsonCommentHandling.Disallow,
                               MaxDepth = 128
                           }))
                {
                    JsonElement root = document.RootElement;
                    if (ContainsAnyEnvelopeProperty(root))
                    {
                        ProtectedEnvelopeDescriptor descriptor = ReadStrictProtectedPayload(root);
                        string encodedSnapshot = descriptor.Version == LegacyEnvelopeVersion
                            ? _legacyProtector.Unprotect(descriptor.ProtectedPayload)
                            : _protector.Unprotect(descriptor.ProtectedPayload);
                        byte[] snapshotBytes = Convert.FromBase64String(encodedSnapshot);
                        snapshot = DeserializeSnapshot(snapshotBytes);
                        legacyPlaintext = false;
                        legacyEnvelope = descriptor.Version == LegacyEnvelopeVersion;
                        loadedGeneration = descriptor.Generation;
                    }
                    else
                    {
                        if (File.Exists(_floorPath))
                        {
                            throw new InvalidDataException("Install-linking plaintext is below the durable migration floor.");
                        }

                        ValidateLegacySnapshotShape(root);
                        snapshot = DeserializeSnapshot(durableBytes);
                        legacyPlaintext = true;
                        legacyEnvelope = false;
                        loadedGeneration = 0;
                    }
                }

                bool floorMissingBeforeLoad = !File.Exists(_floorPath);
                ValidateSnapshot(snapshot);
                ValidateOrRepairFloor(loadedGeneration, snapshot, legacyEnvelope || legacyPlaintext);
                _generation = loadedGeneration;
                ApplySnapshotLocked(snapshot);
                _committedSnapshot = snapshot;
                InstallLinkingStoreSnapshot retained = BuildRetainedSnapshot(DateTimeOffset.UtcNow);
                bool retentionChanged = !JsonSerializer.SerializeToUtf8Bytes(snapshot, _jsonOptions)
                    .AsSpan()
                    .SequenceEqual(JsonSerializer.SerializeToUtf8Bytes(retained, _jsonOptions));
                if (legacyPlaintext || legacyEnvelope || floorMissingBeforeLoad || retentionChanged)
                {
                    // The legacy file was restricted before it was read. Replace it immediately so
                    // no successful startup leaves install claims or grants in plaintext at rest.
                    PersistLocked();
                }

                _logger.LogInformation(
                    "InstallLinkingStore loaded {ReceiptCount} receipts, {TicketCount} claim tickets, {InstallCount} claimed installs, and {ScriptCount} personalized install scripts.",
                    ReceiptsById.Count,
                    ClaimTicketsById.Count,
                    InstallationsById.Count,
                    PersonalizedInstallScriptsById.Count);
            }
            catch (Exception exception) when (
                IsDurableStateFailure(exception)
                && exception is not UnsafeDurableStatePathException)
            {
                ClearSnapshotLocked();
                TryWriteQuarantineReceipt(durableBytes);
                if (durableBytes is { Length: > 0 } && !LooksLikeProtectedEnvelope(durableBytes))
                {
                    TryScrubUnsafeSource();
                }
                _logger.LogError("InstallLinkingStore refused invalid protected durable state; startup is fail-closed.");
                throw new InvalidOperationException(
                    "Install-linking durable state validation failed; startup is fail-closed.");
            }
        }
    }

    private static bool IsDurableStateFailure(Exception exception)
        => exception is JsonException
            or CryptographicException
            or InvalidDataException
            or FormatException
            or IOException
            or UnauthorizedAccessException
            or NotSupportedException
            or InvalidOperationException
            or ArgumentException
            or KeyNotFoundException;

    internal static bool ContainsAnyEnvelopeProperty(JsonElement root)
    {
        if (root.ValueKind != JsonValueKind.Object)
        {
            return false;
        }

        foreach (JsonProperty property in root.EnumerateObject())
        {
            if (EnvelopePropertyNames.Contains(property.Name))
            {
                return true;
            }
        }

        return false;
    }

    internal static ProtectedEnvelopeDescriptor ReadStrictProtectedPayload(JsonElement root)
    {
        if (root.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException("Install-linking protected envelope must be an object.");
        }

        HashSet<string> seen = new(StringComparer.Ordinal);
        foreach (JsonProperty property in root.EnumerateObject())
        {
            if (!EnvelopePropertyNames.Contains(property.Name) || !seen.Add(property.Name))
            {
                throw new InvalidDataException("Install-linking protected envelope shape is invalid.");
            }
        }

        if (root.GetProperty("format").ValueKind != JsonValueKind.String
            || !string.Equals(root.GetProperty("format").GetString(), EnvelopeFormat, StringComparison.Ordinal)
            || root.GetProperty("version").ValueKind != JsonValueKind.Number
            || !root.GetProperty("version").TryGetInt32(out int version)
            || root.GetProperty("protectedPayload").ValueKind != JsonValueKind.String)
        {
            throw new InvalidDataException("Install-linking protected envelope version is unsupported.");
        }

        long generation;
        if (version == LegacyEnvelopeVersion)
        {
            if (seen.Count != 3 || seen.Contains("generation"))
            {
                throw new InvalidDataException("Install-linking protected envelope version is unsupported.");
            }

            generation = 0;
        }
        else if (version == EnvelopeVersion)
        {
            if (seen.Count != EnvelopePropertyNames.Count
                || root.GetProperty("generation").ValueKind != JsonValueKind.Number
                || !root.GetProperty("generation").TryGetInt64(out generation)
                || generation < 1)
            {
                throw new InvalidDataException("Install-linking protected envelope generation is invalid.");
            }
        }
        else
        {
            throw new InvalidDataException("Install-linking protected envelope version is unsupported.");
        }

        string? protectedPayload = root.GetProperty("protectedPayload").GetString();
        if (string.IsNullOrWhiteSpace(protectedPayload) || protectedPayload.Length > MaxSnapshotBytes)
        {
            throw new InvalidDataException("Install-linking protected envelope payload is invalid.");
        }

        return new ProtectedEnvelopeDescriptor(version, generation, protectedPayload);
    }

    internal static void ValidateLegacySnapshotShape(JsonElement root)
    {
        if (root.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException("Install-linking legacy snapshot must be an object.");
        }

        HashSet<string> seen = new(StringComparer.Ordinal);
        foreach (JsonProperty property in root.EnumerateObject())
        {
            if (!LegacyPropertyNames.Contains(property.Name)
                || !seen.Add(property.Name)
                || property.Value.ValueKind is not (JsonValueKind.Array or JsonValueKind.Null))
            {
                throw new InvalidDataException("Install-linking legacy snapshot shape is invalid.");
            }
        }

        if (!seen.Contains("receipts")
            || !seen.Contains("claimTickets")
            || !seen.Contains("installations")
            || !seen.Contains("grants"))
        {
            throw new InvalidDataException("Install-linking legacy snapshot is incomplete.");
        }
    }

    private InstallLinkingStoreSnapshot DeserializeSnapshot(ReadOnlySpan<byte> snapshotBytes)
    {
        if (snapshotBytes.Length is <= 0 or > MaxSnapshotBytes)
        {
            throw new InvalidDataException("Install-linking snapshot payload has an invalid size.");
        }

        return JsonSerializer.Deserialize<InstallLinkingStoreSnapshot>(snapshotBytes, _jsonOptions)
            ?? throw new InvalidDataException("Install-linking snapshot payload is invalid.");
    }

    internal static InstallLinkingStoreSnapshot DeserializeImportSnapshot(
        ReadOnlySpan<byte> snapshotBytes,
        JsonSerializerOptions jsonOptions)
    {
        if (snapshotBytes.Length is <= 0 or > MaxSnapshotBytes)
        {
            throw new InvalidDataException("Install-linking snapshot payload has an invalid size.");
        }

        return JsonSerializer.Deserialize<InstallLinkingStoreSnapshot>(snapshotBytes, jsonOptions)
            ?? throw new InvalidDataException("Install-linking snapshot payload is invalid.");
    }

    private void VerifyCurrentGenerationForCompareAndSwap()
    {
        if (!File.Exists(_storagePath))
        {
            if (_generation != 0)
            {
                throw new InvalidOperationException("Install-linking durable generation changed unexpectedly.");
            }

            return;
        }

        byte[] current = ReadSecureStorageBytes(_storagePath, repairOwnerMode: false);
        using JsonDocument document = JsonDocument.Parse(current);
        JsonElement root = document.RootElement;
        if (!ContainsAnyEnvelopeProperty(root))
        {
            if (_generation == 0 && !File.Exists(_floorPath))
            {
                return;
            }

            throw new InvalidOperationException("Install-linking durable generation changed unexpectedly.");
        }

        ProtectedEnvelopeDescriptor descriptor = ReadStrictProtectedPayload(root);
        if (descriptor.Generation != _generation)
        {
            throw new InvalidOperationException("Install-linking durable generation changed unexpectedly.");
        }
    }

    private void PersistFloor(long generation, ReadOnlySpan<byte> snapshotBytes)
    {
        string digest = Convert.ToHexString(SHA256.HashData(snapshotBytes)).ToLowerInvariant();
        byte[] floorPayload = JsonSerializer.SerializeToUtf8Bytes(
            new InstallLinkingStoreFloorPayload(
                MinimumEnvelopeVersion: EnvelopeVersion,
                Generation: generation,
                SnapshotSha256: digest),
            _jsonOptions);
        string protectedPayload = _floorProtector.Protect(Convert.ToBase64String(floorPayload));
        byte[] floorBytes = JsonSerializer.SerializeToUtf8Bytes(
            new InstallLinkingStoreFloorEnvelope(FloorFormat, 1, protectedPayload),
            _jsonOptions);
        PersistBytesAtomically(_floorPath, floorBytes);
    }

    private void ValidateOrRepairFloor(
        long loadedGeneration,
        InstallLinkingStoreSnapshot snapshot,
        bool migrating)
    {
        if (!File.Exists(_floorPath))
        {
            if (!migrating && loadedGeneration > 0)
            {
                byte[] missingFloorSnapshotBytes = JsonSerializer.SerializeToUtf8Bytes(snapshot, _jsonOptions);
                PersistFloor(loadedGeneration, missingFloorSnapshotBytes);
            }

            return;
        }

        if (migrating)
        {
            throw new InvalidDataException("Install-linking durable state is below its migration floor.");
        }

        InstallLinkingStoreFloorPayload floor = ReadFloor();
        if (floor.MinimumEnvelopeVersion > EnvelopeVersion
            || loadedGeneration < floor.Generation)
        {
            throw new InvalidDataException("Install-linking durable state generation is below its local floor.");
        }

        byte[] snapshotBytes = JsonSerializer.SerializeToUtf8Bytes(snapshot, _jsonOptions);
        string digest = Convert.ToHexString(SHA256.HashData(snapshotBytes)).ToLowerInvariant();
        if (loadedGeneration == floor.Generation
            && !CryptographicOperations.FixedTimeEquals(
                Convert.FromHexString(digest),
                Convert.FromHexString(floor.SnapshotSha256!)))
        {
            throw new InvalidDataException("Install-linking durable state digest does not match its local floor.");
        }

        if (loadedGeneration > floor.Generation)
        {
            // Crash recovery: the envelope is published before the floor. Advancing only in this
            // direction preserves the monotonic local rollback boundary.
            PersistFloor(loadedGeneration, snapshotBytes);
        }
    }

    private InstallLinkingStoreFloorPayload ReadFloor()
    {
        byte[] bytes = ReadSecureStorageBytes(_floorPath, repairOwnerMode: false);
        using JsonDocument document = JsonDocument.Parse(bytes);
        JsonElement root = document.RootElement;
        ValidateExactObjectProperties(root, FloorEnvelopePropertyNames, "Install-linking local floor envelope");
        if (root.GetProperty("format").ValueKind != JsonValueKind.String
            || root.GetProperty("format").GetString() != FloorFormat
            || root.GetProperty("version").ValueKind != JsonValueKind.Number
            || !root.GetProperty("version").TryGetInt32(out int floorVersion)
            || floorVersion != 1
            || root.GetProperty("protectedPayload").ValueKind != JsonValueKind.String)
        {
            throw new InvalidDataException("Install-linking local floor is invalid.");
        }

        string? protectedPayload = root.GetProperty("protectedPayload").GetString();
        if (string.IsNullOrWhiteSpace(protectedPayload))
        {
            throw new InvalidDataException("Install-linking local floor is invalid.");
        }

        byte[] payload = Convert.FromBase64String(_floorProtector.Unprotect(protectedPayload));
        try
        {
            using JsonDocument payloadDocument = JsonDocument.Parse(payload);
            ValidateExactObjectProperties(
                payloadDocument.RootElement,
                FloorPayloadPropertyNames,
                "Install-linking local floor payload");
            InstallLinkingStoreFloorPayload floor = JsonSerializer.Deserialize<InstallLinkingStoreFloorPayload>(payload, _jsonOptions)
                ?? throw new InvalidDataException("Install-linking local floor is invalid.");
            if (floor.MinimumEnvelopeVersion < EnvelopeVersion
                || floor.Generation < 1
                || string.IsNullOrWhiteSpace(floor.SnapshotSha256)
                || floor.SnapshotSha256.Length != 64
                || !floor.SnapshotSha256.All(Uri.IsHexDigit))
            {
                throw new InvalidDataException("Install-linking local floor is invalid.");
            }

            return floor;
        }
        finally
        {
            CryptographicOperations.ZeroMemory(payload);
        }
    }

    private static void ValidateExactObjectProperties(
        JsonElement root,
        IReadOnlySet<string> expected,
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

    private byte[] ReadSecureStorageBytes(string path, bool repairOwnerMode)
    {
        if (LinuxSecureFile.IsSupportedPlatform)
        {
            return LinuxSecureFile.ReadOwnerOnlyRegularFile(path, MaxSnapshotBytes, repairOwnerMode);
        }

        RejectUnsafePath(path);
        FileInfo file = new(path);
        if (file.Length is <= 0 or > MaxSnapshotBytes)
        {
            throw new InvalidDataException("Install-linking durable state has an invalid size.");
        }

        if (repairOwnerMode)
        {
            TightenFileMode(path);
        }

        return File.ReadAllBytes(path);
    }

    private FileStream AcquireWriterLease(bool production)
    {
        RejectUnsafePath(_writerLeasePath);
        if (LinuxSecureFile.IsSupportedPlatform)
        {
            return LinuxSecureFile.AcquireOwnerOnlyWriterLease(_writerLeasePath);
        }

        if (production)
        {
            throw new PlatformNotSupportedException("Install-linking single-writer locking requires Linux in production.");
        }

        FileStreamOptions options = new()
        {
            Mode = FileMode.OpenOrCreate,
            Access = FileAccess.ReadWrite,
            Share = FileShare.None,
            BufferSize = 1,
            Options = FileOptions.WriteThrough
        };
        return new FileStream(_writerLeasePath, options);
    }

    private void TryWriteQuarantineReceipt(byte[]? durableBytes)
    {
        if (durableBytes is not { Length: > 0 })
        {
            return;
        }

        string directory = Path.GetDirectoryName(_storagePath)!;
        string fileName = Path.GetFileName(_storagePath);
        string digest = Convert.ToHexString(SHA256.HashData(durableBytes)).ToLowerInvariant();
        string quarantinePath = Path.Combine(
            directory,
            $".{fileName}.quarantine-validation_failed-{digest[..24]}.json");
        byte[] receiptBytes = JsonSerializer.SerializeToUtf8Bytes(
            new InstallLinkingQuarantineReceipt(
                Format: QuarantineFormat,
                Version: 1,
                Reason: "validation_failed",
                SourceSha256: digest,
                SourceBytes: durableBytes.Length,
                ObservedAtUtc: DateTimeOffset.UtcNow),
            _jsonOptions);
        bool quarantineSecured = false;
        bool quarantineCreated = false;
        try
        {
            PruneQuarantineReceipts(
                directory,
                fileName,
                reservedReceiptSlots: 1,
                reservedReceiptBytes: receiptBytes.Length);
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

            using (FileStream quarantine = new(quarantinePath, options))
            {
                quarantineCreated = true;
                quarantine.Write(receiptBytes);
                quarantine.Flush(flushToDisk: true);
            }

            TightenFileMode(quarantinePath);
            quarantineSecured = true;
            FlushDirectory(directory);
        }
        catch (Exception exception) when (exception is IOException
            or UnauthorizedAccessException
            or InvalidOperationException
            or NotSupportedException)
        {
            if (quarantineCreated && !quarantineSecured)
            {
                TryDeleteTemporaryFile(quarantinePath);
            }
        }
    }

    private static void PruneQuarantineReceipts(
        string directory,
        string fileName,
        int reservedReceiptSlots,
        long reservedReceiptBytes)
    {
        int retainedReceiptLimit = MaximumQuarantineReceipts - reservedReceiptSlots;
        if (retainedReceiptLimit is < 0 or > MaximumQuarantineReceipts)
        {
            throw new ArgumentOutOfRangeException(nameof(reservedReceiptSlots));
        }

        long retainedByteLimit = MaximumQuarantineReceiptBytes - reservedReceiptBytes;
        if (retainedByteLimit is < 0 or > MaximumQuarantineReceiptBytes)
        {
            throw new ArgumentOutOfRangeException(nameof(reservedReceiptBytes));
        }

        DateTimeOffset cutoff = DateTimeOffset.UtcNow.Subtract(QuarantineRetention);
        string receiptPrefix = $".{fileName}.quarantine-";
        var receipts = new List<FileInfo>();
        int scannedEntries = 0;
        foreach (FileSystemInfo entry in new DirectoryInfo(directory)
                     .EnumerateFileSystemInfos("*", SearchOption.TopDirectoryOnly))
        {
            scannedEntries++;
            if (scannedEntries > MaximumQuarantineDirectoryScanEntries)
            {
                throw new InvalidOperationException(
                    "Install-linking quarantine inventory exceeds the secure scan limit.");
            }

            if (entry is FileInfo file
                && file.Name.StartsWith(receiptPrefix, StringComparison.Ordinal)
                && file.Name.EndsWith(".json", StringComparison.Ordinal))
            {
                receipts.Add(file);
            }
        }

        FileInfo[] orderedReceipts = receipts
            .OrderByDescending(static file => file.LastWriteTimeUtc)
            .ToArray();
        long retainedBytes = 0;
        for (int index = 0; index < orderedReceipts.Length; index++)
        {
            FileInfo receipt = orderedReceipts[index];
            bool retain = receipt.LinkTarget is null
                && index < retainedReceiptLimit
                && receipt.LastWriteTimeUtc >= cutoff.UtcDateTime
                && receipt.Length <= MaximumQuarantineReceiptBytes
                && retainedBytes + receipt.Length <= retainedByteLimit;
            if (retain)
            {
                retainedBytes += receipt.Length;
                continue;
            }

            File.Delete(receipt.FullName);
            if (File.Exists(receipt.FullName))
            {
                throw new IOException("Install-linking quarantine receipt pruning failed.");
            }
        }
    }

    private static bool LooksLikeProtectedEnvelope(byte[] bytes)
    {
        try
        {
            using JsonDocument document = JsonDocument.Parse(bytes);
            _ = ReadStrictProtectedPayload(document.RootElement);
            return true;
        }
        catch (Exception exception) when (exception is JsonException
            or InvalidDataException
            or InvalidOperationException
            or KeyNotFoundException)
        {
            return false;
        }
    }

    private void TryScrubUnsafeSource()
    {
        try
        {
            byte[] marker = JsonSerializer.SerializeToUtf8Bytes(
                new InstallLinkingFailureMarker(
                    "chummer.install-linking-store.failure",
                    1,
                    "validation_failed"),
                _jsonOptions);
            PersistBytesAtomically(_storagePath, marker);
        }
        catch
        {
            // The fixed startup failure remains authoritative. Never copy the unsafe source.
        }
    }

    private static DownloadReceiptDto SanitizeReceiptForRetention(
        DownloadReceiptDto receipt,
        IReadOnlyDictionary<string, InstallClaimTicketDto> retainedTicketsById,
        DateTimeOffset now)
    {
        if (string.IsNullOrWhiteSpace(receipt.ClaimCode))
        {
            return receipt with { ClaimCode = null };
        }

        bool retainClaimCode = receipt.ClaimTicketExpiresAtUtc is { } expiresAtUtc
            && expiresAtUtc > now
            && !string.IsNullOrWhiteSpace(receipt.ClaimTicketId)
            && retainedTicketsById.TryGetValue(receipt.ClaimTicketId, out InstallClaimTicketDto? ticket)
            && string.Equals(ticket.Status, InstallClaimTicketStates.Pending, StringComparison.OrdinalIgnoreCase)
            && ticket.ExpiresAtUtc == expiresAtUtc
            && string.Equals(ticket.ClaimCode, receipt.ClaimCode, StringComparison.Ordinal);
        return retainClaimCode ? receipt : receipt with { ClaimCode = null };
    }

    private static InstallClaimTicketDto SanitizeTicketForRetention(InstallClaimTicketDto ticket, DateTimeOffset now)
    {
        bool expired = ticket.ExpiresAtUtc <= now;
        string status = expired && string.Equals(ticket.Status, InstallClaimTicketStates.Pending, StringComparison.OrdinalIgnoreCase)
            ? InstallClaimTicketStates.Expired
            : ticket.Status;
        return !string.Equals(status, InstallClaimTicketStates.Pending, StringComparison.OrdinalIgnoreCase)
            ? ticket with { Status = status, ClaimCode = string.Empty }
            : ticket;
    }

    private static InstallBrowserCallbackDto SanitizeCallbackForRetention(InstallBrowserCallbackDto callback, DateTimeOffset now)
    {
        bool expired = callback.ExpiresAtUtc <= now;
        string status = expired && string.Equals(callback.Status, InstallBrowserCallbackStates.Pending, StringComparison.OrdinalIgnoreCase)
            ? InstallBrowserCallbackStates.Expired
            : callback.Status;
        bool retryableRedemption = !expired
            && string.Equals(status, InstallBrowserCallbackStates.Redeemed, StringComparison.OrdinalIgnoreCase)
            && !string.IsNullOrWhiteSpace(callback.GrantId);
        if (string.Equals(status, InstallBrowserCallbackStates.Pending, StringComparison.OrdinalIgnoreCase))
        {
            return callback;
        }

        // A desktop may retry a completed callback when the first response is lost. Keep the
        // encrypted high-entropy code only for its original bounded lifetime so the service's
        // idempotent redemption branch remains reachable, while dropping the no-longer-needed URI.
        // Pre-binding snapshots have no immutable grant id and are revoked during retention so an
        // older callback can never inherit whichever grant happens to be current after upgrade.
        return retryableRedemption
            ? callback with { Status = status, CallbackUri = null }
            : callback with
            {
                Status = string.Equals(
                    status,
                    InstallBrowserCallbackStates.Redeemed,
                    StringComparison.OrdinalIgnoreCase)
                    && string.IsNullOrWhiteSpace(callback.GrantId)
                        ? InstallBrowserCallbackStates.Revoked
                        : status,
                CallbackCode = string.Empty,
                CallbackUri = null
            };
    }

    private static InstallationGrantDto SanitizeGrantForRetention(InstallationGrantDto grant, DateTimeOffset now)
    {
        bool expired = grant.ExpiresAtUtc <= now;
        string status = expired && string.Equals(grant.Status, InstallationGrantStates.Active, StringComparison.OrdinalIgnoreCase)
            ? InstallationGrantStates.Expired
            : grant.Status;
        return !string.Equals(status, InstallationGrantStates.Active, StringComparison.OrdinalIgnoreCase)
            ? grant with { Status = status, AccessToken = string.Empty }
            : grant;
    }

    private static PersonalizedInstallScriptLinkDto SanitizeScriptForRetention(
        PersonalizedInstallScriptLinkDto script,
        DateTimeOffset now)
    {
        bool expired = script.ExpiresAtUtc <= now;
        string status = expired && string.Equals(script.Status, PersonalizedInstallScriptStates.Pending, StringComparison.OrdinalIgnoreCase)
            ? PersonalizedInstallScriptStates.Expired
            : script.Status;
        return !string.Equals(status, PersonalizedInstallScriptStates.Pending, StringComparison.OrdinalIgnoreCase)
            ? script with { Status = status, RenderedScript = null }
            : script;
    }

    internal static void ValidateSnapshot(InstallLinkingStoreSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        DownloadReceiptDto[] receipts = ValidateCollection(snapshot.Receipts, 4096, static item => item.ReceiptId, "receipt");
        InstallClaimTicketDto[] tickets = ValidateCollection(snapshot.ClaimTickets, 2048, static item => item.TicketId, "claim ticket");
        IReadOnlyDictionary<string, InstallClaimTicketDto> ticketsById = tickets
            .ToDictionary(static item => item.TicketId, StringComparer.OrdinalIgnoreCase);
        InstallBrowserCallbackDto[] callbacks = ValidateCollection(snapshot.BrowserCallbacks ?? [], 2048, static item => item.CallbackId, "browser callback");
        ClaimedInstallationDto[] installations = ValidateCollection(snapshot.Installations, 2048, static item => item.InstallationId, "installation");
        InstallationGrantDto[] grants = ValidateCollection(snapshot.Grants, 4096, static item => item.GrantId, "grant");
        PersonalizedInstallScriptLinkDto[] scripts = ValidateCollection(snapshot.PersonalizedInstallScripts ?? [], 1024, static item => item.ScriptId, "personalized script");

        foreach (DownloadReceiptDto item in receipts)
        {
            ValidateIdentifier(item.ArtifactId, "receipt artifact");
            ValidateTimestamp(item.IssuedAtUtc, "receipt issued timestamp");

            bool hasTicketId = !string.IsNullOrWhiteSpace(item.ClaimTicketId);
            bool hasTicketExpiry = item.ClaimTicketExpiresAtUtc.HasValue;
            bool hasClaimCode = !string.IsNullOrWhiteSpace(item.ClaimCode);
            if (hasTicketId != hasTicketExpiry || (!hasTicketId && hasClaimCode))
            {
                throw new InvalidDataException("Install-linking receipt claim binding is invalid.");
            }

            if (item.ClaimTicketExpiresAtUtc is { } receiptExpiry
                && receiptExpiry < item.IssuedAtUtc)
            {
                throw new InvalidDataException("Install-linking receipt claim expiry is invalid.");
            }

            if (hasClaimCode)
            {
                ValidateSecret(item.ClaimCode!, "receipt claim code");
                if (!ticketsById.TryGetValue(item.ClaimTicketId!, out InstallClaimTicketDto? referencedTicket)
                    || !string.Equals(
                        referencedTicket.Status,
                        InstallClaimTicketStates.Pending,
                        StringComparison.OrdinalIgnoreCase)
                    || referencedTicket.ExpiresAtUtc != item.ClaimTicketExpiresAtUtc
                    || !string.Equals(referencedTicket.ClaimCode, item.ClaimCode, StringComparison.Ordinal))
                {
                    throw new InvalidDataException("Install-linking receipt claim secret is not bound to a pending ticket.");
                }
            }
        }

        foreach (InstallClaimTicketDto item in tickets)
        {
            ValidateStatus(item.Status, InstallClaimTicketStates.Pending, InstallClaimTicketStates.Redeemed, InstallClaimTicketStates.Expired, InstallClaimTicketStates.Revoked);
            ValidateTimestampRange(item.CreatedAtUtc, item.ExpiresAtUtc, "claim ticket");
            if (string.Equals(item.Status, InstallClaimTicketStates.Pending, StringComparison.OrdinalIgnoreCase))
            {
                ValidateSecret(item.ClaimCode, "claim ticket code");
            }
        }

        foreach (InstallBrowserCallbackDto item in callbacks)
        {
            ValidateStatus(item.Status, InstallBrowserCallbackStates.Pending, InstallBrowserCallbackStates.Redeemed, InstallBrowserCallbackStates.Expired, InstallBrowserCallbackStates.Revoked);
            ValidateTimestampRange(item.CreatedAtUtc, item.ExpiresAtUtc, "browser callback");
            if (!string.IsNullOrWhiteSpace(item.GrantId))
            {
                ValidateIdentifier(item.GrantId, "browser callback grant");
            }

            if (string.Equals(item.Status, InstallBrowserCallbackStates.Pending, StringComparison.OrdinalIgnoreCase))
            {
                ValidateSecret(item.CallbackCode, "browser callback code");
            }
            else if (string.Equals(item.Status, InstallBrowserCallbackStates.Redeemed, StringComparison.OrdinalIgnoreCase)
                     && !string.IsNullOrWhiteSpace(item.GrantId)
                     && !string.IsNullOrEmpty(item.CallbackCode))
            {
                ValidateSecret(item.CallbackCode, "browser callback code");
            }
        }

        foreach (ClaimedInstallationDto item in installations)
        {
            ValidateStatus(item.Status, ClaimedInstallationStates.Active, ClaimedInstallationStates.Revoked);
            ValidateTimestampRange(item.CreatedAtUtc, item.UpdatedAtUtc, "installation");
        }

        foreach (InstallationGrantDto item in grants)
        {
            ValidateIdentifier(item.InstallationId, "grant installation");
            ValidateStatus(item.Status, InstallationGrantStates.Active, InstallationGrantStates.Revoked, InstallationGrantStates.Expired);
            ValidateTimestampRange(item.IssuedAtUtc, item.ExpiresAtUtc, "grant");
            if (string.Equals(item.Status, InstallationGrantStates.Active, StringComparison.OrdinalIgnoreCase))
            {
                ValidateSecret(item.AccessToken, "grant token");
            }
        }

        foreach (PersonalizedInstallScriptLinkDto item in scripts)
        {
            ValidateIdentifier(item.ArtifactId, "personalized script artifact");
            ValidateStatus(item.Status, PersonalizedInstallScriptStates.Pending, PersonalizedInstallScriptStates.Consumed, PersonalizedInstallScriptStates.Expired, PersonalizedInstallScriptStates.Revoked);
            ValidateTimestampRange(item.IssuedAtUtc, item.ExpiresAtUtc, "personalized script");
            if (item.AllowedArtifactIds is null || item.AllowedArtifactIds.Count is < 1 or > 32)
            {
                throw new InvalidDataException("Install-linking personalized script artifact bounds are invalid.");
            }

            foreach (string artifactId in item.AllowedArtifactIds)
            {
                ValidateIdentifier(artifactId, "personalized script allowed artifact");
            }

            if (item.RenderedScript is { Length: > 1024 * 1024 })
            {
                throw new InvalidDataException("Install-linking personalized script payload is too large.");
            }
        }
    }

    private static T[] ValidateCollection<T>(
        IReadOnlyList<T>? values,
        int maximumCount,
        Func<T, string> idSelector,
        string label)
        where T : class
    {
        if (values is null || values.Count > maximumCount)
        {
            throw new InvalidDataException($"Install-linking {label} collection is invalid.");
        }

        var ids = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var result = new T[values.Count];
        for (int index = 0; index < values.Count; index++)
        {
            T? item = values[index];
            if (item is null)
            {
                throw new InvalidDataException($"Install-linking {label} entry is invalid.");
            }

            string id = idSelector(item);
            ValidateIdentifier(id, label);
            if (!ids.Add(id))
            {
                throw new InvalidDataException($"Install-linking {label} identifiers must be unique.");
            }

            result[index] = item;
        }

        return result;
    }

    private static void ValidateIdentifier(string? value, string label)
    {
        if (string.IsNullOrWhiteSpace(value)
            || value.Length > 256
            || value.Any(char.IsControl))
        {
            throw new InvalidDataException($"Install-linking {label} identifier is invalid.");
        }
    }

    private static void ValidateSecret(string? value, string label)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Length > 512 || value.Any(char.IsControl))
        {
            throw new InvalidDataException($"Install-linking active {label} is invalid.");
        }
    }

    private static void ValidateStatus(string? status, params string[] allowed)
    {
        if (status is null || !allowed.Contains(status, StringComparer.OrdinalIgnoreCase))
        {
            throw new InvalidDataException("Install-linking entry status is invalid.");
        }
    }

    private static void ValidateTimestamp(DateTimeOffset timestamp, string label)
    {
        if (timestamp == default || timestamp.Year is < 2020 or > 2200)
        {
            throw new InvalidDataException($"Install-linking {label} is invalid.");
        }
    }

    private static void ValidateTimestampRange(DateTimeOffset start, DateTimeOffset end, string label)
    {
        ValidateTimestamp(start, $"{label} start timestamp");
        ValidateTimestamp(end, $"{label} end timestamp");
        if (end < start)
        {
            throw new InvalidDataException($"Install-linking {label} timestamp range is invalid.");
        }
    }

    private void EnsureSecureStorageDirectory()
    {
        string directory = Path.GetDirectoryName(_storagePath)!;
        RejectReparsePath(directory, includeLeafAsFile: false);
        Directory.CreateDirectory(directory);
        RejectReparsePath(directory, includeLeafAsFile: false);
        if (LinuxSecureFile.IsSupportedPlatform)
        {
            LinuxSecureFile.PrepareOwnerOnlyDirectory(directory);
        }
        else
        {
            TightenDirectoryMode(directory);
        }
    }

    private void RejectUnsafeStorageFile()
    {
        RejectUnsafePath(_storagePath);
    }

    private static void RejectUnsafePath(string path)
    {
        RejectReparsePath(path, includeLeafAsFile: true);
        if (Directory.Exists(path))
        {
            throw new UnsafeDurableStatePathException(
                "Install-linking durable state path must be a regular file.");
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
                throw new UnsafeDurableStatePathException(
                    "Install-linking durable state path cannot contain links.");
            }
        }
        catch (PlatformNotSupportedException)
        {
            // Attribute validation below remains available on platforms without LinkTarget.
        }

        if (!entry.Exists)
        {
            return;
        }

        if ((entry.Attributes & FileAttributes.ReparsePoint) != 0)
        {
            throw new UnsafeDurableStatePathException(
                "Install-linking durable state path cannot contain reparse points.");
        }
    }

    private sealed class UnsafeDurableStatePathException : InvalidOperationException
    {
        public UnsafeDurableStatePathException(string message)
            : base(message)
        {
        }
    }

    private static void TightenDirectoryMode(string path)
    {
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(path, OwnerDirectoryMode);
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
            // Windows durable publication uses MoveFileEx with MOVEFILE_WRITE_THROUGH.
            return;
        }

        int descriptor = NativeOpen(directory, 0);
        if (descriptor < 0)
        {
            throw new IOException("Install-linking storage directory could not be opened for durable synchronization.");
        }

        try
        {
            if (NativeFsync(descriptor) != 0)
            {
                throw new IOException("Install-linking storage directory could not be durably synchronized.");
            }
        }
        finally
        {
            _ = NativeClose(descriptor);
        }
    }

    private static void MoveDurably(string sourcePath, string destinationPath)
    {
        if (!OperatingSystem.IsWindows())
        {
            File.Move(sourcePath, destinationPath, overwrite: true);
            return;
        }

        const int moveFileReplaceExisting = 0x1;
        const int moveFileWriteThrough = 0x8;
        if (!NativeMoveFileEx(
                sourcePath,
                destinationPath,
                moveFileReplaceExisting | moveFileWriteThrough))
        {
            throw new IOException("Install-linking protected snapshot could not be atomically published.");
        }
    }

    private static void TryDeleteTemporaryFile(string path)
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
            // The primary persistence error remains authoritative.
        }
    }

    [DllImport("libc", EntryPoint = "open", SetLastError = true)]
    private static extern int NativeOpen(string path, int flags);

    [DllImport("libc", EntryPoint = "fsync", SetLastError = true)]
    private static extern int NativeFsync(int descriptor);

    [DllImport("libc", EntryPoint = "close", SetLastError = true)]
    private static extern int NativeClose(int descriptor);

    [DllImport("kernel32.dll", EntryPoint = "MoveFileExW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool NativeMoveFileEx(string existingPath, string newPath, int flags);

    private void ClearSnapshotLocked()
        => ApplySnapshotLocked(EmptySnapshot());

    private static InstallLinkingStoreSnapshot EmptySnapshot()
        => new([], [], [], [], [], []);

    private void ApplySnapshotLocked(InstallLinkingStoreSnapshot snapshot)
    {
        ReceiptsById.Clear();
        ClaimTicketsById.Clear();
        BrowserCallbacksById.Clear();
        InstallationsById.Clear();
        GrantsById.Clear();
        PersonalizedInstallScriptsById.Clear();

        foreach (DownloadReceiptDto receipt in snapshot.Receipts ?? Array.Empty<DownloadReceiptDto>())
        {
            ReceiptsById[receipt.ReceiptId] = receipt;
        }

        foreach (InstallClaimTicketDto ticket in snapshot.ClaimTickets ?? Array.Empty<InstallClaimTicketDto>())
        {
            ClaimTicketsById[ticket.TicketId] = ticket;
        }

        foreach (InstallBrowserCallbackDto callback in snapshot.BrowserCallbacks ?? Array.Empty<InstallBrowserCallbackDto>())
        {
            BrowserCallbacksById[callback.CallbackId] = callback;
        }

        foreach (ClaimedInstallationDto installation in snapshot.Installations ?? Array.Empty<ClaimedInstallationDto>())
        {
            InstallationsById[installation.InstallationId] = installation;
        }

        foreach (InstallationGrantDto grant in snapshot.Grants ?? Array.Empty<InstallationGrantDto>())
        {
            GrantsById[grant.GrantId] = grant;
        }

        foreach (PersonalizedInstallScriptLinkDto script in snapshot.PersonalizedInstallScripts ?? Array.Empty<PersonalizedInstallScriptLinkDto>())
        {
            PersonalizedInstallScriptsById[script.ScriptId] = script;
        }
    }

    internal static string ResolveStoragePath(IConfiguration configuration)
    {
        string? configured = configuration["CHUMMER_INSTALL_LINKING_STORE_PATH"]
            ?? configuration["InstallLinking:StorePath"];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured);
        }

        string? environment = configuration["ASPNETCORE_ENVIRONMENT"];
        bool temporaryFallbackAllowed = string.Equals(
                environment,
                Environments.Development,
                StringComparison.OrdinalIgnoreCase)
            || string.Equals(environment, "Test", StringComparison.OrdinalIgnoreCase)
            || string.Equals(environment, "Testing", StringComparison.OrdinalIgnoreCase);
        if (!temporaryFallbackAllowed)
        {
            throw new InvalidOperationException(
                "Install-linking durable storage path must be explicitly configured outside development and tests.");
        }

        return Path.Combine(Path.GetTempPath(), "chummer6-hub", "install-linking-store.json");
    }

    public void Dispose()
    {
        ReplaceAuthorityEnvelopeDigest(null);
        _writerLease?.Dispose();
        _writerLease = null;
    }
}

internal sealed record InstallLinkingStoreEnvelope(
    string Format,
    int Version,
    long Generation,
    string ProtectedPayload);

internal sealed record ProtectedEnvelopeDescriptor(
    int Version,
    long Generation,
    string ProtectedPayload);

internal sealed record InstallLinkingStoreFloorEnvelope(
    string Format,
    int Version,
    string ProtectedPayload);

internal sealed record InstallLinkingStoreFloorPayload(
    int MinimumEnvelopeVersion,
    long Generation,
    string? SnapshotSha256);

internal sealed record InstallLinkingQuarantineReceipt(
    string Format,
    int Version,
    string Reason,
    string SourceSha256,
    long SourceBytes,
    DateTimeOffset ObservedAtUtc);

internal sealed record InstallLinkingFailureMarker(
    string Format,
    int Version,
    string Reason);

internal sealed record InstallLinkingStoreSnapshot(
    IReadOnlyList<DownloadReceiptDto> Receipts,
    IReadOnlyList<InstallClaimTicketDto> ClaimTickets,
    IReadOnlyList<InstallBrowserCallbackDto>? BrowserCallbacks,
    IReadOnlyList<ClaimedInstallationDto> Installations,
    IReadOnlyList<InstallationGrantDto> Grants,
    IReadOnlyList<PersonalizedInstallScriptLinkDto>? PersonalizedInstallScripts = null);
