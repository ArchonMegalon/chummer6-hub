using System.Buffers;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Chummer.Run.Api.Services;

public sealed record ReleaseUploadSession(
    string SessionId,
    DateTimeOffset ExpiresAtUtc,
    string BundleRoot,
    string AuthorizationBinding = "0000000000000000000000000000000000000000000000000000000000000000",
    bool SingleUseAuthorization = false,
    bool Publishing = false,
    bool Completed = false,
    ReleaseBundlePromotionResult? CompletionResult = null,
    DateTimeOffset? AuthorizationExpiresAtUtc = null,
    ReleaseActivationIntent? ActivationIntent = null,
    bool Poisoned = false,
    string? PoisonReason = null,
    DateTimeOffset? CompletedAtUtc = null,
    DateTimeOffset? ActivationAcknowledgedAtUtc = null,
    ReleaseUploadCandidateSessionBinding? CandidateImportBinding = null);

public sealed record ReleaseUploadChunkResult(
    string RelativePath,
    int ChunkIndex,
    int TotalChunks,
    long BytesReceived,
    bool Completed);

public sealed class ReleaseBundleUploadSessionService
{
    private const string SessionsRootKey = "CHUMMER_RELEASE_UPLOAD_SESSION_ROOT";
    private const string LegacyAuthorizationBinding = "0000000000000000000000000000000000000000000000000000000000000000";
    private static readonly TimeSpan DefaultLifetime = TimeSpan.FromHours(6);
    // Copy-on-write promotion retains the active generation while constructing its
    // successor. Inventory + incoming bytes are charged separately; this margin covers
    // pointer, manifest, candidate, journal, and atomic-replacement metadata peaks.
    private const long PromotionMetadataMarginBytes = 32L * ReleaseUploadQuotaOptions.MiB;
    private const UnixFileMode OwnerDirectoryMode =
        UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute;
    private const UnixFileMode OwnerFileMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;

    private readonly IConfiguration _configuration;
    private readonly ILogger<ReleaseBundleUploadSessionService> _logger;
    private readonly ReleaseUploadQuotaOptions _options;
    private readonly IReleaseUploadStorageProbe _storageProbe;
    private readonly Action<string> _flushDirectoryEntry;

    public ReleaseBundleUploadSessionService(
        IConfiguration configuration,
        ILogger<ReleaseBundleUploadSessionService> logger)
        : this(
            configuration,
            logger,
            ReleaseUploadQuotaOptions.FromConfiguration(configuration),
            new ReleaseUploadStorageProbe(),
            FlushDirectoryEntry)
    {
    }

    public ReleaseBundleUploadSessionService(
        IConfiguration configuration,
        ILogger<ReleaseBundleUploadSessionService> logger,
        ReleaseUploadQuotaOptions options,
        IReleaseUploadStorageProbe storageProbe)
        : this(configuration, logger, options, storageProbe, FlushDirectoryEntry)
    {
    }

    internal ReleaseBundleUploadSessionService(
        IConfiguration configuration,
        ILogger<ReleaseBundleUploadSessionService> logger,
        Action<string> flushDirectoryEntry)
        : this(
            configuration,
            logger,
            ReleaseUploadQuotaOptions.FromConfiguration(configuration),
            new ReleaseUploadStorageProbe(),
            flushDirectoryEntry)
    {
    }

    internal ReleaseBundleUploadSessionService(
        IConfiguration configuration,
        ILogger<ReleaseBundleUploadSessionService> logger,
        ReleaseUploadQuotaOptions options,
        IReleaseUploadStorageProbe storageProbe,
        Action<string> flushDirectoryEntry)
    {
        _configuration = configuration ?? throw new ArgumentNullException(nameof(configuration));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
        _options = options ?? throw new ArgumentNullException(nameof(options));
        _storageProbe = storageProbe ?? throw new ArgumentNullException(nameof(storageProbe));
        _flushDirectoryEntry = flushDirectoryEntry ?? throw new ArgumentNullException(nameof(flushDirectoryEntry));
        _options.Validate();
    }

    public ReleaseUploadSession CreateSession()
        => CreateSession(LegacyAuthorizationBinding, singleUseAuthorization: false);

    public ReleaseUploadSession CreateSession(
        string authorizationBinding,
        bool singleUseAuthorization,
        DateTimeOffset? authorizationExpiresAtUtc = null,
        ReleaseUploadCandidateSessionBinding? candidateImportBinding = null)
    {
        string sessionsRoot = ResolveSessionsRoot(requireConfigured: singleUseAuthorization);
        authorizationBinding = NormalizeAuthorizationBinding(authorizationBinding);
        if (singleUseAuthorization
            && (authorizationExpiresAtUtc is null || authorizationExpiresAtUtc <= DateTimeOffset.UtcNow))
        {
            throw new InvalidDataException("release upload authorization expiry is required and must be in the future.");
        }
        if (candidateImportBinding is not null)
        {
            ValidateCandidateImportBinding(candidateImportBinding);
            if (!singleUseAuthorization)
            {
                throw new InvalidDataException(
                    "candidate import authority must be a single-use authorization.");
            }
        }

        using FileStream quotaLock = AcquireQuotaLock();
        PurgeExpiredSessionsUnderQuotaLock(sessionsRoot);
        using FileStream? authorizationLock = singleUseAuthorization
            ? AcquireAuthorizationLock(authorizationBinding)
            : null;

        if (singleUseAuthorization)
        {
            ReleaseUploadSession? existing = FindSessionForAuthorization(authorizationBinding);
            if (existing is not null)
            {
                if (existing.CandidateImportBinding != candidateImportBinding)
                {
                    throw new InvalidOperationException(
                        "release upload authorization candidate binding changed.");
                }
                if (existing.Completed)
                {
                    throw new InvalidOperationException("release upload authorization has already been consumed.");
                }

                return existing;
            }
        }

        UsageSnapshot usage = ReconcileUsage(sessionsRoot);
        if (usage.ActiveSessionCount >= _options.MaxActiveSessions)
        {
            throw new ReleaseUploadQuotaException(
                StatusCodes.Status429TooManyRequests,
                "the shared release upload active-session limit has been reached.");
        }

        int authorizationSessions = usage.ActiveSessionsByAuthorization.GetValueOrDefault(authorizationBinding);
        if (authorizationSessions >= _options.MaxActiveSessionsPerAuthorization)
        {
            throw new ReleaseUploadQuotaException(
                StatusCodes.Status429TooManyRequests,
                "the authenticated release upload active-session limit has been reached.");
        }

        EnsureCapacity(usage, sessionId: null, additionalPeakBytes: 0);
        string sessionId = Guid.NewGuid().ToString("N");
        string sessionRoot = Path.Combine(sessionsRoot, sessionId);
        string bundleRoot = Path.Combine(sessionRoot, "bundle");
        string stagingRoot = Path.Combine(sessionRoot, "staging");
        try
        {
            EnsureOwnerOnlyDirectory(sessionRoot);
            EnsureOwnerOnlyDirectory(bundleRoot);
            EnsureOwnerOnlyDirectory(stagingRoot);

            DateTimeOffset sessionExpiresAtUtc = DateTimeOffset.UtcNow.Add(DefaultLifetime);
            if (authorizationExpiresAtUtc is not null && authorizationExpiresAtUtc < sessionExpiresAtUtc)
            {
                sessionExpiresAtUtc = authorizationExpiresAtUtc.Value;
            }

            ReleaseUploadSession session = new(
                SessionId: sessionId,
                ExpiresAtUtc: sessionExpiresAtUtc,
                BundleRoot: bundleRoot,
                AuthorizationBinding: authorizationBinding,
                SingleUseAuthorization: singleUseAuthorization,
                AuthorizationExpiresAtUtc: authorizationExpiresAtUtc,
                CandidateImportBinding: candidateImportBinding);
            PersistMetadata(sessionRoot, session);
            return session;
        }
        catch
        {
            TryDeleteDirectory(sessionRoot);
            throw;
        }
    }

    public Task<long> WriteFileAsync(
        string sessionId,
        string relativePath,
        Stream content,
        CancellationToken cancellationToken)
        => WriteFileAsync(
            sessionId,
            relativePath,
            content,
            LegacyAuthorizationBinding,
            cancellationToken);

    public async Task<long> WriteFileAsync(
        string sessionId,
        string relativePath,
        Stream content,
        string authorizationBinding,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(content);
        sessionId = CanonicalizeSessionId(sessionId);
        string normalizedPath = NormalizeRelativePath(relativePath);

        using FileStream quotaLock = AcquireQuotaLock();
        using FileStream sessionLock = AcquireSessionLock(sessionId);
        ReleaseUploadSession session = ReadSessionMetadata(
            sessionId,
            authorizationBinding,
            allowCompleted: false);
        string targetPath = ResolveBundleTarget(session, normalizedPath);
        string stagingDirectory = ResolveStagingDirectory(session, normalizedPath);
        EnsureSafeParentPath(session.BundleRoot, targetPath);
        EnsureOwnerOnlyDirectory(Path.GetDirectoryName(targetPath)!);
        EnsureOwnerOnlyDirectory(stagingDirectory);
        EnsureStagingPathBinding(stagingDirectory, normalizedPath);
        if (File.Exists(Path.Combine(stagingDirectory, "chunk-state.json"))
            || File.Exists(Path.Combine(stagingDirectory, "payload.partial")))
        {
            throw new InvalidOperationException("a chunked upload is already active for this bundle path.");
        }

        UsageSnapshot usage = ReconcileUsage(ResolveSessionsRoot());
        EnsureLogicalFileAdmission(usage, session, normalizedPath, targetPath, stagingDirectory);
        long? expectedLength = TryGetRemainingLength(content);
        if (expectedLength is <= 0)
        {
            throw new InvalidDataException("release upload payload must not be empty.");
        }

        if (expectedLength > _options.MaxChunkBytes)
        {
            throw PayloadTooLarge("file upload payload", _options.MaxChunkBytes);
        }

        if (expectedLength is not null)
        {
            EnsureCapacity(usage, sessionId, expectedLength.Value);
        }

        string temporaryPath = Path.Combine(stagingDirectory, $"direct-{Guid.NewGuid():N}.tmp");
        string backupPath = Path.Combine(stagingDirectory, $"backup-{Guid.NewGuid():N}.tmp");
        bool targetChanged = false;
        bool destinationExisted = File.Exists(targetPath);
        try
        {
            long copied = await CopyToNewStagingFileAsync(
                content,
                temporaryPath,
                _options.MaxChunkBytes,
                usage,
                sessionId,
                peakMultiplier: 1,
                cancellationToken);

            if (destinationExisted)
            {
                File.Replace(temporaryPath, targetPath, backupPath, ignoreMetadataErrors: true);
            }
            else
            {
                File.Move(temporaryPath, targetPath);
            }

            targetChanged = true;
            EnsureOwnerOnlyFile(targetPath);
            _flushDirectoryEntry(Path.GetDirectoryName(targetPath)!);
            if (File.Exists(backupPath))
            {
                File.Delete(backupPath);
            }

            if (!TryDeleteDirectory(stagingDirectory))
            {
                PoisonSession(session, "direct_staging_cleanup_failed");
            }
            return copied;
        }
        catch
        {
            if (targetChanged)
            {
                try
                {
                    if (File.Exists(backupPath))
                    {
                        File.Move(backupPath, targetPath, overwrite: true);
                    }
                    else if (!destinationExisted && File.Exists(targetPath))
                    {
                        File.Delete(targetPath);
                    }

                    _flushDirectoryEntry(Path.GetDirectoryName(targetPath)!);
                    targetChanged = false;
                }
                catch
                {
                    PoisonSession(session, "direct_write_rollback_failed");
                }
            }

            throw;
        }
        finally
        {
            bool cleanupFailed = !TryDeleteFile(temporaryPath) | !TryDeleteFile(backupPath);
            if (cleanupFailed)
            {
                PoisonSession(session, "direct_write_cleanup_failed");
            }
            else if (!targetChanged && !TryDeleteDirectory(stagingDirectory))
            {
                PoisonSession(session, "direct_staging_cleanup_failed");
            }
        }
    }

    public Task<ReleaseUploadChunkResult> AppendChunkAsync(
        string sessionId,
        string relativePath,
        int chunkIndex,
        int totalChunks,
        Stream content,
        CancellationToken cancellationToken)
        => AppendChunkAsync(
            sessionId,
            relativePath,
            chunkIndex,
            totalChunks,
            content,
            LegacyAuthorizationBinding,
            cancellationToken);

    public async Task<ReleaseUploadChunkResult> AppendChunkAsync(
        string sessionId,
        string relativePath,
        int chunkIndex,
        int totalChunks,
        Stream content,
        string authorizationBinding,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(content);
        ValidateChunkCoordinates(chunkIndex, totalChunks);
        sessionId = CanonicalizeSessionId(sessionId);
        string normalizedPath = NormalizeRelativePath(relativePath);

        using FileStream quotaLock = AcquireQuotaLock();
        using FileStream sessionLock = AcquireSessionLock(sessionId);
        ReleaseUploadSession session = ReadSessionMetadata(
            sessionId,
            authorizationBinding,
            allowCompleted: false);
        string targetPath = ResolveBundleTarget(session, normalizedPath);
        string stagingDirectory = ResolveStagingDirectory(session, normalizedPath);
        EnsureSafeParentPath(session.BundleRoot, targetPath);
        EnsureOwnerOnlyDirectory(Path.GetDirectoryName(targetPath)!);

        string statePath = Path.Combine(stagingDirectory, "chunk-state.json");
        string partialPath = Path.Combine(stagingDirectory, "payload.partial");
        bool hadDurableChunkState = File.Exists(statePath) || File.Exists(partialPath);
        ChunkUploadState state = LoadChunkState(statePath)
            ?? new ChunkUploadState(normalizedPath, totalChunks, 0);
        ValidateChunkBinding(state, normalizedPath, totalChunks);
        if (state.NextChunkIndex == state.TotalChunks && File.Exists(targetPath) && !File.Exists(partialPath))
        {
            return new ReleaseUploadChunkResult(
                normalizedPath,
                Math.Max(0, state.TotalChunks - 1),
                state.TotalChunks,
                new FileInfo(targetPath).Length,
                Completed: true);
        }
        if (state.NextChunkIndex != chunkIndex)
        {
            throw new InvalidDataException(
                $"expected chunk {state.NextChunkIndex} but received {chunkIndex} for {normalizedPath}.");
        }
        EnsureOwnerOnlyDirectory(stagingDirectory);
        EnsureStagingPathBinding(stagingDirectory, normalizedPath);

        long priorLength = File.Exists(partialPath) ? new FileInfo(partialPath).Length : 0;
        long? expectedLength = TryGetRemainingLength(content);
        if (expectedLength is <= 0)
        {
            throw new InvalidDataException("release upload chunk must not be empty.");
        }

        if (expectedLength > _options.MaxChunkBytes)
        {
            throw PayloadTooLarge("chunk upload payload", _options.MaxChunkBytes);
        }

        if (expectedLength is not null && priorLength + expectedLength > _options.MaxFileBytes)
        {
            throw PayloadTooLarge("cumulative file upload", _options.MaxFileBytes);
        }

        UsageSnapshot usage = ReconcileUsage(ResolveSessionsRoot());
        EnsureLogicalFileAdmission(usage, session, normalizedPath, targetPath, stagingDirectory);
        if (expectedLength is not null)
        {
            EnsureCapacity(usage, sessionId, checked(expectedLength.Value * 2));
        }

        string chunkTemporaryPath = Path.Combine(stagingDirectory, $"chunk-{chunkIndex:D4}-{Guid.NewGuid():N}.tmp");
        bool partialAdvanced = false;
        long chunkLength = 0;
        try
        {
            chunkLength = await CopyToNewStagingFileAsync(
                content,
                chunkTemporaryPath,
                _options.MaxChunkBytes,
                usage,
                sessionId,
                peakMultiplier: 2,
                cancellationToken);
            if (priorLength + chunkLength > _options.MaxFileBytes)
            {
                throw PayloadTooLarge("cumulative file upload", _options.MaxFileBytes);
            }

            await using (FileStream partial = OpenOwnerOnlyAsyncFile(
                             partialPath,
                             FileMode.OpenOrCreate,
                             FileAccess.ReadWrite))
            await using (FileStream chunk = new(
                             chunkTemporaryPath,
                             FileMode.Open,
                             FileAccess.Read,
                             FileShare.Read,
                             bufferSize: 81920,
                             useAsync: true))
            {
                if (partial.Length != priorLength)
                {
                    throw new InvalidDataException("chunk partial length disagrees with its durable state.");
                }

                partial.Position = priorLength;
                await chunk.CopyToAsync(partial, cancellationToken);
                await partial.FlushAsync(cancellationToken);
                partial.Flush(flushToDisk: true);
                partialAdvanced = true;
            }

            bool completed = chunkIndex + 1 == totalChunks;
            if (!completed)
            {
                PersistChunkState(statePath, state with { NextChunkIndex = chunkIndex + 1 });
                TryDeleteFile(chunkTemporaryPath);
                return new ReleaseUploadChunkResult(
                    normalizedPath,
                    chunkIndex,
                    totalChunks,
                    priorLength + chunkLength,
                    Completed: false);
            }

            PersistChunkState(statePath, state with { NextChunkIndex = totalChunks });
            FinalizeChunkedPayload(partialPath, targetPath, stagingDirectory);
            TryDeleteFile(statePath);
            TryDeleteFile(chunkTemporaryPath);
            if (!TryDeleteDirectory(stagingDirectory))
            {
                PoisonSession(session, "chunk_staging_cleanup_failed");
            }
            return new ReleaseUploadChunkResult(
                normalizedPath,
                chunkIndex,
                totalChunks,
                priorLength + chunkLength,
                Completed: true);
        }
        catch
        {
            if (partialAdvanced)
            {
                try
                {
                    using FileStream rollback = OpenOwnerOnlyFile(
                        partialPath,
                        FileMode.OpenOrCreate,
                        FileAccess.ReadWrite,
                        FileShare.None);
                    rollback.SetLength(priorLength);
                    rollback.Flush(flushToDisk: true);
                    PersistChunkState(statePath, state);
                }
                catch
                {
                    PoisonSession(session, "chunk_rollback_failed");
                }
            }

            throw;
        }
        finally
        {
            if (!TryDeleteFile(chunkTemporaryPath))
            {
                PoisonSession(session, "chunk_cleanup_failed");
            }
            else if (!partialAdvanced
                     && !hadDurableChunkState
                     && !TryDeleteDirectory(stagingDirectory))
            {
                PoisonSession(session, "chunk_staging_cleanup_failed");
            }
        }
    }

    public string ResolveBundleRoot(string sessionId)
        => ResolveBundleRoot(sessionId, LegacyAuthorizationBinding);

    public string ResolveBundleRoot(string sessionId, string authorizationBinding)
    {
        using FileStream quotaLock = AcquireQuotaLock();
        using FileStream sessionLock = AcquireSessionLock(CanonicalizeSessionId(sessionId));
        return ReadSessionMetadata(sessionId, authorizationBinding, allowCompleted: false).BundleRoot;
    }

    public ReleaseUploadSessionCompletionLease BeginCompletion(
        string sessionId,
        string authorizationBinding)
        => BeginCompletionCore(
            sessionId,
            authorizationBinding,
            privilegedReconciliation: false);

    public ReleaseUploadSessionCompletionLease BeginPrivilegedReconciliation(
        string sessionId)
        => BeginCompletionCore(
            sessionId,
            authorizationBinding: null,
            privilegedReconciliation: true);

    private ReleaseUploadSessionCompletionLease BeginCompletionCore(
        string sessionId,
        string? authorizationBinding,
        bool privilegedReconciliation)
    {
        sessionId = CanonicalizeSessionId(sessionId);
        FileStream quotaLock = AcquireQuotaLock();
        FileStream? sessionLock = null;
        try
        {
            sessionLock = AcquireSessionLock(sessionId);
            ReleaseUploadSession session = ReadSessionMetadata(
                sessionId,
                authorizationBinding,
                allowCompleted: true,
                privilegedReconciliation);
            return new ReleaseUploadSessionCompletionLease(
                this,
                quotaLock,
                sessionLock,
                session,
                privilegedReconciliation);
        }
        catch
        {
            sessionLock?.Dispose();
            quotaLock.Dispose();
            throw;
        }
    }

    public void DeleteSession(string sessionId)
    {
        if (!TryCanonicalizeSessionId(sessionId, out string canonicalSessionId))
        {
            _logger.LogWarning("Release upload session delete rejected invalid session id.");
            return;
        }

        using FileStream quotaLock = AcquireQuotaLock();
        using FileStream? sessionLock = TryAcquireSessionLockForPurge(canonicalSessionId);
        if (sessionLock is null)
        {
            return;
        }

        DeleteSessionPath(Path.Combine(ResolveSessionsRoot(), canonicalSessionId), canonicalSessionId);
    }

    public void PurgeExpiredSessions()
    {
        string sessionsRoot = ResolveSessionsRoot();
        using FileStream? quotaLock = TryAcquireQuotaLock(
            TimeSpan.FromMilliseconds(250),
            CancellationToken.None);
        if (quotaLock is null)
        {
            return;
        }
        PurgeExpiredSessionsUnderQuotaLock(sessionsRoot);
    }

    internal ReleaseUploadStorageReadiness EvaluateStorageReadiness(CancellationToken cancellationToken)
    {
        try
        {
            string root = ResolveSessionsRoot();
            using FileStream? quotaLock = TryAcquireQuotaLock(TimeSpan.FromMilliseconds(250), cancellationToken);
            if (quotaLock is null)
            {
                return new ReleaseUploadStorageReadiness(false, "upload_admission_exhausted");
            }
            return EvaluateStorageReadinessUnderQuotaLock(root);
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException)
        {
            return new ReleaseUploadStorageReadiness(false, "upload_session_root_unavailable");
        }
    }

    private ReleaseUploadStorageReadiness EvaluateStorageReadinessUnderQuotaLock(string root)
    {
        UsageSnapshot usage = ReconcileUsage(root);
        ReleaseUploadStorageSpace space = _storageProbe.GetSpace(root);
        if (space.TotalBytes < 0
            || space.AvailableBytes < 0
            || space.AvailableBytes > space.TotalBytes)
        {
            return new ReleaseUploadStorageReadiness(false, "upload_session_root_unavailable");
        }
        long reserve = Math.Max(
            _options.MinimumFreeBytes,
            checked((long)Math.Ceiling(space.TotalBytes * _options.MinimumFreeFraction)));
        if (usage.SharedBytes >= _options.MaxSharedBytes)
        {
            return new ReleaseUploadStorageReadiness(false, "upload_shared_quota_exhausted");
        }

        if (space.AvailableBytes <= reserve)
        {
            return new ReleaseUploadStorageReadiness(false, "upload_storage_reserve_exhausted");
        }

        return new ReleaseUploadStorageReadiness(true, "ready");
    }

    internal ReleaseUploadStorageReadiness EvaluatePublicationDestinationReadiness(
        ReleaseShelfSnapshot snapshot,
        string? completionBundleRoot,
        CancellationToken cancellationToken)
    {
        try
        {
            ArgumentNullException.ThrowIfNull(snapshot);
            cancellationToken.ThrowIfCancellationRequested();
            string root = Path.GetFullPath(snapshot.DownloadsRoot);
            if (!Directory.Exists(root))
            {
                return new ReleaseUploadStorageReadiness(false, "publication_destination_unavailable");
            }

            FileAttributes attributes = File.GetAttributes(root);
            if ((attributes & FileAttributes.Directory) == 0
                || (attributes & FileAttributes.ReparsePoint) != 0)
            {
                return new ReleaseUploadStorageReadiness(false, "publication_destination_unavailable");
            }

            VerifyPublicationDestinationWritable(root, cancellationToken);
            ReleaseUploadStorageSpace space = _storageProbe.GetSpace(root);
            if (space.TotalBytes < 0
                || space.AvailableBytes < 0
                || space.AvailableBytes > space.TotalBytes)
            {
                return new ReleaseUploadStorageReadiness(
                    false,
                    "publication_destination_unavailable");
            }
            long reserve = Math.Max(
                _options.MinimumFreeBytes,
                checked((long)Math.Ceiling(space.TotalBytes * _options.MinimumFreeFraction)));
            long activeInventoryBytes = 0;
            foreach (ReleaseShelfInventoryEntry entry in snapshot.Inventory.Values)
            {
                if (entry.SizeBytes < 0)
                {
                    throw new InvalidDataException(
                        "release shelf inventory contains a negative size.");
                }
                activeInventoryBytes = checked(activeInventoryBytes + entry.SizeBytes);
            }

            long incomingBytes = completionBundleRoot is null
                ? _options.MaxSessionBytes
                : MeasureTree(completionBundleRoot, countFiles: false).Bytes;
            long conservativePromotionFootprint = checked(
                activeInventoryBytes + incomingBytes + PromotionMetadataMarginBytes);
            if (space.AvailableBytes < reserve
                || space.AvailableBytes - reserve < conservativePromotionFootprint)
            {
                return new ReleaseUploadStorageReadiness(
                    false,
                    "publication_destination_capacity_exhausted");
            }

            return new ReleaseUploadStorageReadiness(true, "ready");
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (UnauthorizedAccessException)
        {
            return new ReleaseUploadStorageReadiness(false, "publication_destination_not_writable");
        }
        catch (OverflowException)
        {
            return new ReleaseUploadStorageReadiness(
                false,
                "publication_destination_capacity_exhausted");
        }
        catch (Exception ex) when (ex is IOException or InvalidDataException or NotSupportedException)
        {
            return new ReleaseUploadStorageReadiness(false, "publication_destination_unavailable");
        }
    }

    internal ReleaseUploadStorageReadiness EvaluateActivationProtocolReadiness(
        CancellationToken cancellationToken)
    {
        try
        {
            string root = ResolveSessionsRoot();
            using FileStream? quotaLock = TryAcquireQuotaLock(TimeSpan.FromMilliseconds(250), cancellationToken);
            if (quotaLock is null)
            {
                return new ReleaseUploadStorageReadiness(false, "activation_session_admission_busy");
            }
            return EvaluateActivationProtocolReadinessUnderQuotaLock(root, cancellationToken);
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or InvalidDataException)
        {
            return new ReleaseUploadStorageReadiness(false, "activation_session_state_invalid");
        }
    }

    private ReleaseUploadStorageReadiness EvaluateActivationProtocolReadinessUnderQuotaLock(
        string root,
        CancellationToken cancellationToken)
    {
        foreach (string sessionRoot in Directory.EnumerateDirectories(root))
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (!TryCanonicalizeSessionId(
                    Path.GetFileName(sessionRoot),
                    out string canonicalSessionId))
            {
                continue;
            }

            RejectReparsePoint(sessionRoot);
            string metadataPath = Path.Combine(sessionRoot, "session.json");
            if (!File.Exists(metadataPath))
            {
                return new ReleaseUploadStorageReadiness(false, "activation_session_state_invalid");
            }
            RejectReparsePoint(metadataPath);

            ReleaseUploadSession? session;
            try
            {
                session = JsonSerializer.Deserialize<ReleaseUploadSession>(File.ReadAllText(metadataPath));
            }
            catch (JsonException)
            {
                return new ReleaseUploadStorageReadiness(false, "activation_session_state_invalid");
            }

            if (session is null)
            {
                return new ReleaseUploadStorageReadiness(false, "activation_session_state_invalid");
            }

            try
            {
                _ = ValidateDurableSessionState(session, canonicalSessionId);
            }
            catch (InvalidDataException)
            {
                return new ReleaseUploadStorageReadiness(false, "activation_session_state_invalid");
            }

            if (session.Publishing
                || session.Completed
                   && session.ActivationIntent is not null
                   && session.ActivationAcknowledgedAtUtc is null)
            {
                return new ReleaseUploadStorageReadiness(false, "activation_session_unresolved");
            }
        }

        return new ReleaseUploadStorageReadiness(true, "ready");
    }

    private void ValidateChunkCoordinates(int chunkIndex, int totalChunks)
    {
        if (chunkIndex < 0)
        {
            throw new InvalidDataException("chunk index must be zero or greater.");
        }

        if (totalChunks <= 0)
        {
            throw new InvalidDataException("total chunks must be greater than zero.");
        }

        if (totalChunks > _options.MaxChunksPerFile)
        {
            throw PayloadTooLarge("total chunks per file", _options.MaxChunksPerFile);
        }

        if (chunkIndex >= totalChunks)
        {
            throw new InvalidDataException("chunk index must be less than total chunks.");
        }
    }

    private static void ValidateChunkBinding(
        ChunkUploadState state,
        string normalizedPath,
        int totalChunks)
    {
        if (!string.Equals(state.RelativePath, normalizedPath, StringComparison.Ordinal))
        {
            throw new InvalidDataException("chunk upload state path mismatch.");
        }

        if (state.TotalChunks != totalChunks)
        {
            throw new InvalidDataException("chunk upload total mismatch.");
        }

    }

    private async Task<long> CopyToNewStagingFileAsync(
        Stream source,
        string destinationPath,
        long payloadLimit,
        UsageSnapshot baseline,
        string sessionId,
        int peakMultiplier,
        CancellationToken cancellationToken)
    {
        byte[] buffer = ArrayPool<byte>.Shared.Rent(81920);
        long copied = 0;
        try
        {
            await using FileStream destination = OpenOwnerOnlyAsyncFile(
                destinationPath,
                FileMode.CreateNew,
                FileAccess.Write);
            while (true)
            {
                int read = await source.ReadAsync(buffer.AsMemory(0, buffer.Length), cancellationToken);
                if (read == 0)
                {
                    break;
                }

                copied = checked(copied + read);
                if (copied > payloadLimit)
                {
                    throw PayloadTooLarge("release upload payload", payloadLimit);
                }

                EnsureCapacity(baseline, sessionId, checked(copied * peakMultiplier));
                await destination.WriteAsync(buffer.AsMemory(0, read), cancellationToken);
            }

            await destination.FlushAsync(cancellationToken);
            destination.Flush(flushToDisk: true);
            EnsureOwnerOnlyFile(destinationPath);
            return copied;
        }
        finally
        {
            ArrayPool<byte>.Shared.Return(buffer);
        }
    }

    private void FinalizeChunkedPayload(
        string partialPath,
        string targetPath,
        string stagingDirectory)
    {
        string backupPath = Path.Combine(stagingDirectory, $"final-backup-{Guid.NewGuid():N}.tmp");
        bool destinationExisted = File.Exists(targetPath);
        bool targetChanged = false;
        try
        {
            if (destinationExisted)
            {
                File.Replace(partialPath, targetPath, backupPath, ignoreMetadataErrors: true);
            }
            else
            {
                File.Move(partialPath, targetPath);
            }

            targetChanged = true;
            EnsureOwnerOnlyFile(targetPath);
            _flushDirectoryEntry(Path.GetDirectoryName(targetPath)!);
            TryDeleteFile(backupPath);
        }
        catch
        {
            if (targetChanged)
            {
                if (File.Exists(backupPath))
                {
                    if (File.Exists(targetPath))
                    {
                        File.Move(targetPath, partialPath, overwrite: true);
                    }
                    File.Move(backupPath, targetPath, overwrite: true);
                }
                else if (!destinationExisted && File.Exists(targetPath))
                {
                    File.Move(targetPath, partialPath, overwrite: true);
                }
            }

            throw;
        }
        finally
        {
            TryDeleteFile(backupPath);
        }
    }

    private void EnsureLogicalFileAdmission(
        UsageSnapshot usage,
        ReleaseUploadSession session,
        string normalizedPath,
        string targetPath,
        string stagingDirectory)
    {
        SessionUsage sessionUsage = usage.Sessions.GetValueOrDefault(session.SessionId)
            ?? new SessionUsage(0, 0);
        int logicalFiles = sessionUsage.LogicalFiles;
        if (File.Exists(targetPath)
            && Directory.Exists(stagingDirectory)
            && Directory.EnumerateFileSystemEntries(stagingDirectory).Any())
        {
            logicalFiles--;
        }

        if (logicalFiles > _options.MaxFilesPerSession)
        {
            throw PayloadTooLarge("files per upload session", _options.MaxFilesPerSession);
        }
    }

    private void EnsureCapacity(
        UsageSnapshot usage,
        string? sessionId,
        long additionalPeakBytes)
    {
        if (additionalPeakBytes < 0)
        {
            throw new OverflowException("release upload capacity reservation overflowed.");
        }

        long sessionBytes = sessionId is null
            ? 0
            : usage.Sessions.GetValueOrDefault(sessionId)?.Bytes ?? 0;
        if (sessionId is not null
            && (sessionBytes > _options.MaxSessionBytes - additionalPeakBytes))
        {
            throw PayloadTooLarge("upload session storage", _options.MaxSessionBytes);
        }

        if (usage.SharedBytes > _options.MaxSharedBytes - additionalPeakBytes)
        {
            throw new ReleaseUploadQuotaException(
                StatusCodes.Status507InsufficientStorage,
                "release upload shared storage quota would be exceeded.");
        }

        string sessionsRoot = ResolveSessionsRoot();
        ReleaseUploadStorageSpace space = _storageProbe.GetSpace(sessionsRoot);
        if (space.TotalBytes < 0
            || space.AvailableBytes < 0
            || space.AvailableBytes > space.TotalBytes)
        {
            throw new ReleaseUploadQuotaException(
                StatusCodes.Status507InsufficientStorage,
                "release upload storage capacity could not be verified.");
        }
        long reserve = Math.Max(
            _options.MinimumFreeBytes,
            checked((long)Math.Ceiling(space.TotalBytes * _options.MinimumFreeFraction)));
        if (space.AvailableBytes - additionalPeakBytes < reserve)
        {
            throw new ReleaseUploadQuotaException(
                StatusCodes.Status507InsufficientStorage,
                "release upload would consume the configured free-space reserve.");
        }
    }

    private UsageSnapshot ReconcileUsage(string sessionsRoot)
    {
        long sharedBytes = 0;
        int activeSessionCount = 0;
        var activeByAuthorization = new Dictionary<string, int>(StringComparer.Ordinal);
        var sessions = new Dictionary<string, SessionUsage>(StringComparer.Ordinal);
        foreach (string sessionRoot in Directory.EnumerateDirectories(sessionsRoot))
        {
            string sessionId = Path.GetFileName(sessionRoot);
            if (!TryCanonicalizeSessionId(sessionId, out string canonicalSessionId))
            {
                continue;
            }

            RejectReparsePoint(sessionRoot);
            TreeUsage bundle = MeasureTree(Path.Combine(sessionRoot, "bundle"), countFiles: true);
            TreeUsage staging = MeasureTree(Path.Combine(sessionRoot, "staging"), countFiles: false);
            int stagedLogicalFiles = CountNonEmptyStagingDirectories(Path.Combine(sessionRoot, "staging"));
            long sessionBytes = checked(bundle.Bytes + staging.Bytes);
            sharedBytes = checked(sharedBytes + sessionBytes);
            sessions[canonicalSessionId] = new SessionUsage(
                sessionBytes,
                checked(bundle.Files + stagedLogicalFiles));

            string metadataPath = Path.Combine(sessionRoot, "session.json");
            if (!File.Exists(metadataPath))
            {
                throw new InvalidDataException(
                    "release upload storage contains a session without durable metadata.");
            }

            RejectReparsePoint(metadataPath);
            ReleaseUploadSession? session;
            try
            {
                session = JsonSerializer.Deserialize<ReleaseUploadSession>(File.ReadAllText(metadataPath));
            }
            catch (JsonException ex)
            {
                throw new InvalidDataException(
                    "release upload storage contains malformed session metadata.",
                    ex);
            }

            if (session is null)
            {
                throw new InvalidDataException(
                    "release upload storage contains mismatched session metadata.");
            }

            string binding = ValidateDurableSessionState(session, canonicalSessionId);
            if (!session.Completed && EffectiveExpiry(session) > DateTimeOffset.UtcNow)
            {
                activeSessionCount++;
                activeByAuthorization[binding] =
                    activeByAuthorization.GetValueOrDefault(binding) + 1;
            }
        }

        return new UsageSnapshot(sharedBytes, activeSessionCount, activeByAuthorization, sessions);
    }

    private static TreeUsage MeasureTree(string root, bool countFiles)
    {
        if (!Directory.Exists(root))
        {
            return new TreeUsage(0, 0);
        }

        RejectReparsePoint(root);
        long bytes = 0;
        int files = 0;
        var pending = new Stack<string>();
        pending.Push(root);
        while (pending.Count > 0)
        {
            string directory = pending.Pop();
            foreach (string entry in Directory.EnumerateFileSystemEntries(directory))
            {
                FileAttributes attributes = File.GetAttributes(entry);
                if ((attributes & FileAttributes.ReparsePoint) != 0)
                {
                    throw new InvalidDataException("release upload storage contains a forbidden link or reparse point.");
                }

                if ((attributes & FileAttributes.Directory) != 0)
                {
                    pending.Push(entry);
                    continue;
                }

                bytes = checked(bytes + new FileInfo(entry).Length);
                if (countFiles)
                {
                    files++;
                }
            }
        }

        return new TreeUsage(bytes, files);
    }

    private static int CountNonEmptyStagingDirectories(string stagingRoot)
    {
        if (!Directory.Exists(stagingRoot))
        {
            return 0;
        }

        RejectReparsePoint(stagingRoot);
        int count = 0;
        foreach (string directory in Directory.EnumerateDirectories(stagingRoot))
        {
            RejectReparsePoint(directory);
            if (Directory.EnumerateFileSystemEntries(directory).Any())
            {
                count++;
            }
        }

        return count;
    }

    private string ResolveBundleTarget(ReleaseUploadSession session, string normalizedPath)
    {
        string fullPath = Path.GetFullPath(Path.Combine(
            session.BundleRoot,
            normalizedPath.Replace('/', Path.DirectorySeparatorChar)));
        EnsureContainedPath(session.BundleRoot, fullPath);
        return fullPath;
    }

    private string ResolveStagingDirectory(ReleaseUploadSession session, string normalizedPath)
    {
        string sessionRoot = Path.Combine(ResolveSessionsRoot(), session.SessionId);
        string stagingRoot = Path.Combine(sessionRoot, "staging");
        string pathDigest = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(normalizedPath)));
        string directory = Path.GetFullPath(Path.Combine(stagingRoot, pathDigest));
        EnsureContainedPath(stagingRoot, directory);

        string bindingPath = Path.Combine(directory, "path-binding.json");
        if (Directory.Exists(directory) && File.Exists(bindingPath))
        {
            PathBinding? binding = JsonSerializer.Deserialize<PathBinding>(File.ReadAllText(bindingPath));
            if (binding is null || !string.Equals(binding.RelativePath, normalizedPath, StringComparison.Ordinal))
            {
                throw new InvalidDataException("release upload staging path binding is invalid.");
            }
        }
        else if (Directory.Exists(directory)
                 && Directory.EnumerateFileSystemEntries(directory).Any())
        {
            throw new InvalidDataException("release upload staging path has no durable path binding.");
        }

        return directory;
    }

    private void EnsureStagingPathBinding(string directory, string normalizedPath)
    {
        string bindingPath = Path.Combine(directory, "path-binding.json");
        if (File.Exists(bindingPath))
        {
            PathBinding? binding = JsonSerializer.Deserialize<PathBinding>(File.ReadAllText(bindingPath));
            if (binding is null || !string.Equals(binding.RelativePath, normalizedPath, StringComparison.Ordinal))
            {
                throw new InvalidDataException("release upload staging path binding is invalid.");
            }
            return;
        }

        WriteOwnerOnlyTextAtomically(bindingPath, JsonSerializer.Serialize(new PathBinding(normalizedPath)));
    }

    private static void EnsureContainedPath(string root, string candidate)
    {
        string fullRoot = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar);
        StringComparison comparison = OperatingSystem.IsWindows()
            ? StringComparison.OrdinalIgnoreCase
            : StringComparison.Ordinal;
        if (!candidate.StartsWith(fullRoot + Path.DirectorySeparatorChar, comparison))
        {
            throw new InvalidDataException("upload path escapes its governed root.");
        }
    }

    private static void EnsureSafeParentPath(string root, string candidate)
    {
        EnsureContainedPath(root, candidate);
        RejectReparsePoint(root);
        string relative = Path.GetRelativePath(root, Path.GetDirectoryName(candidate)!);
        string current = Path.GetFullPath(root);
        foreach (string segment in relative.Split(Path.DirectorySeparatorChar, StringSplitOptions.RemoveEmptyEntries))
        {
            current = Path.Combine(current, segment);
            if (Directory.Exists(current) || File.Exists(current))
            {
                RejectReparsePoint(current);
            }
        }
    }

    private string NormalizeRelativePath(string relativePath)
    {
        if (string.IsNullOrWhiteSpace(relativePath))
        {
            throw new InvalidDataException("upload path is required.");
        }

        string normalized = relativePath.Replace('\\', '/').Trim();
        if (Encoding.UTF8.GetByteCount(normalized) > _options.MaxPathBytes)
        {
            throw PayloadTooLarge("upload path metadata", _options.MaxPathBytes);
        }

        if (normalized.StartsWith("/", StringComparison.Ordinal) || normalized.Contains('\0'))
        {
            throw new InvalidDataException("upload path must be a safe relative path.");
        }

        string[] segments = normalized.Split('/', StringSplitOptions.RemoveEmptyEntries);
        if (segments.Length == 0
            || segments.Any(static segment =>
                segment is "." or ".."
                || segment.Contains(':')
                || segment.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0))
        {
            throw new InvalidDataException("upload path contains an invalid segment.");
        }

        return string.Join('/', segments);
    }

    private ReleaseUploadSession ReadSessionMetadata(
        string sessionId,
        string? authorizationBinding,
        bool allowCompleted,
        bool privilegedReconciliation = false)
    {
        sessionId = CanonicalizeSessionId(sessionId);
        string? normalizedAuthorizationBinding = privilegedReconciliation
            ? null
            : NormalizeAuthorizationBinding(authorizationBinding);
        string sessionRoot = Path.Combine(ResolveSessionsRoot(), sessionId);
        RejectReparsePoint(sessionRoot);
        string path = Path.Combine(sessionRoot, "session.json");
        if (!File.Exists(path))
        {
            throw new InvalidDataException("upload session was not found.");
        }

        RejectReparsePoint(path);
        ReleaseUploadSession? session = JsonSerializer.Deserialize<ReleaseUploadSession>(File.ReadAllText(path));
        if (session is null || !string.Equals(session.SessionId, sessionId, StringComparison.Ordinal))
        {
            throw new InvalidDataException("upload session metadata is invalid.");
        }

        string expectedBundleRoot = Path.GetFullPath(Path.Combine(sessionRoot, "bundle"));
        string actualBundleRoot = Path.GetFullPath(session.BundleRoot);
        StringComparison pathComparison = OperatingSystem.IsWindows()
            ? StringComparison.OrdinalIgnoreCase
            : StringComparison.Ordinal;
        if (!string.Equals(actualBundleRoot, expectedBundleRoot, pathComparison))
        {
            throw new InvalidDataException("upload session metadata is invalid.");
        }

        string storedAuthorizationBinding = ValidateDurableSessionState(session, sessionId);
        bool unresolvedActivation = session.Publishing
                                    || session.Completed
                                       && session.ActivationIntent is not null
                                       && session.ActivationAcknowledgedAtUtc is null;
        if (privilegedReconciliation)
        {
            if (!unresolvedActivation)
            {
                throw new InvalidOperationException(
                    "upload session has no unresolved activation eligible for privileged reconciliation.");
            }
        }
        else if (!string.Equals(
                     storedAuthorizationBinding,
                     normalizedAuthorizationBinding,
                     StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "upload session authorization does not match its creator.");
        }

        if (session.Poisoned)
        {
            throw new InvalidDataException("upload session storage is poisoned and requires operator reconciliation.");
        }

        if (EffectiveExpiry(session) <= DateTimeOffset.UtcNow)
        {
            DeleteSessionPath(sessionRoot, sessionId);
            throw new InvalidDataException("upload session has expired.");
        }

        if ((session.Completed || session.Publishing) && !allowCompleted)
        {
            throw new InvalidDataException(
                session.Completed
                    ? "upload session has already been completed."
                    : "upload session publication outcome requires reconciliation.");
        }

        return session;
    }

    private ReleaseUploadSession RecordActivationIntent(
        ReleaseUploadSession session,
        ReleaseActivationIntent intent)
    {
        ArgumentNullException.ThrowIfNull(intent);
        ValidateActivationIntent(intent);
        if (session.Completed)
        {
            throw new InvalidOperationException("upload session has already been completed.");
        }

        if (session.ActivationIntent is not null)
        {
            if (session.ActivationIntent == intent && session.Publishing)
            {
                return session;
            }

            throw new InvalidOperationException("upload session activation intent is immutable once recorded.");
        }

        if (session.Publishing)
        {
            throw new InvalidDataException("publishing upload session is missing its activation intent.");
        }

        ReleaseUploadSession publishing = session with
        {
            Publishing = true,
            ActivationIntent = intent
        };
        PersistMetadata(Path.Combine(ResolveSessionsRoot(), session.SessionId), publishing);
        return publishing;
    }

    private ReleaseUploadSession ResetAbortedActivation(
        ReleaseUploadSession session,
        ReleaseActivationIntent intent)
    {
        if (!session.Publishing || session.ActivationIntent != intent || session.Completed)
        {
            throw new InvalidOperationException("only the exact durable aborted activation may reset this upload session.");
        }

        ReleaseUploadSession retryable = session with
        {
            Publishing = false,
            ActivationIntent = null
        };
        PersistMetadata(Path.Combine(ResolveSessionsRoot(), session.SessionId), retryable);
        return retryable;
    }

    private void MarkSessionCompleted(
        ReleaseUploadSession session,
        ReleaseBundlePromotionResult result)
    {
        if (!session.Publishing || session.ActivationIntent is null)
        {
            throw new InvalidOperationException("upload session activation intent must be durable before completion.");
        }

        ValidateCompletionMatchesIntent(result, session.ActivationIntent);
        ReleaseBundlePromotionResult durableResult = result with { SignedInInstallClaims = null };
        ReleaseUploadSession completed = session with
        {
            Publishing = false,
            Completed = true,
            CompletionResult = durableResult,
            CompletedAtUtc = DateTimeOffset.UtcNow
        };
        string sessionRoot = Path.Combine(ResolveSessionsRoot(), session.SessionId);
        PersistMetadata(sessionRoot, completed);
        CleanupCompletedPayload(sessionRoot, session.SessionId);
    }

    private static void ValidateActivationIntent(ReleaseActivationIntent intent)
    {
        if (intent.Operation is not "promotion" and not "rollback"
            || !IsSafeActivationIdentifier(intent.GenerationId)
            || !IsSafeActivationIdentifier(intent.ActivationReceiptId)
            || (intent.PreviousGenerationId is not null
                && !IsSafeActivationIdentifier(intent.PreviousGenerationId))
            || string.IsNullOrWhiteSpace(intent.ReleaseVersion)
            || intent.ReleaseVersion.Length > 256
            || string.IsNullOrWhiteSpace(intent.Channel)
            || intent.Channel.Length > 128
            || !IsSha256Binding(intent.InventoryDigest)
            || !IsSha256Binding(intent.PointerSha256)
            || (intent.PreviousPointerSha256 is not null
                && !IsSha256Binding(intent.PreviousPointerSha256))
            || (intent.PreviousGenerationId is null) != (intent.PreviousPointerSha256 is null)
            || intent.PublishedAt.Offset != TimeSpan.Zero
            || intent.PreparedAtUtc.Offset != TimeSpan.Zero)
        {
            throw new InvalidDataException("release activation intent is incomplete.");
        }

        byte[]? previousPointerBytes;
        byte[]? targetPointerBytes;
        try
        {
            previousPointerBytes = string.IsNullOrWhiteSpace(intent.PreviousPointerBase64)
                ? null
                : Convert.FromBase64String(intent.PreviousPointerBase64);
            targetPointerBytes = string.IsNullOrWhiteSpace(intent.TargetPointerBase64)
                ? null
                : Convert.FromBase64String(intent.TargetPointerBase64);
        }
        catch (FormatException ex)
        {
            throw new InvalidDataException(
                "release activation intent pointer bytes are malformed.",
                ex);
        }

        if ((previousPointerBytes is null) != (intent.PreviousPointerSha256 is null)
            || targetPointerBytes is null
            || !string.Equals(
                Sha256BindingForBytes(previousPointerBytes),
                intent.PreviousPointerSha256,
                StringComparison.Ordinal)
            || !string.Equals(
                Sha256BindingForBytes(targetPointerBytes),
                intent.PointerSha256,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "release activation intent pointer bytes do not match their digest bindings.");
        }
    }

    private static bool IsSafeActivationIdentifier(string? value)
        => value is { Length: > 0 and <= 128 }
           && char.IsLetterOrDigit(value[0])
           && value.All(static character => char.IsLetterOrDigit(character) || character is '.' or '_' or '-')
           && value is not "." and not ".."
           && !value.Contains("..", StringComparison.Ordinal)
           && !Path.IsPathFullyQualified(value);

    private static bool IsSha256Binding(string? value)
        => value is { Length: 71 }
           && value.StartsWith("sha256:", StringComparison.Ordinal)
           && value[7..].All(static character => character is >= '0' and <= '9' or >= 'a' and <= 'f');

    private static string? Sha256BindingForBytes(byte[]? bytes)
        => bytes is null
            ? null
            : $"sha256:{Convert.ToHexStringLower(SHA256.HashData(bytes))}";

    private static void ValidateCompletionMatchesIntent(
        ReleaseBundlePromotionResult result,
        ReleaseActivationIntent intent)
    {
        if (!string.Equals(result.GenerationId, intent.GenerationId, StringComparison.Ordinal)
            || !string.Equals(result.ActivationReceiptId, intent.ActivationReceiptId, StringComparison.Ordinal)
            || !string.Equals(result.Version, intent.ReleaseVersion, StringComparison.Ordinal)
            || !string.Equals(result.Channel, intent.Channel, StringComparison.Ordinal)
            || result.PublishedAt.ToUniversalTime() != intent.PublishedAt.ToUniversalTime()
            || !string.Equals(result.InventoryDigest, intent.InventoryDigest, StringComparison.Ordinal))
        {
            throw new InvalidDataException("release promotion result does not match the durable activation intent.");
        }
    }

    private static string ValidateDurableSessionState(
        ReleaseUploadSession session,
        string expectedSessionId)
    {
        string authorizationBinding = NormalizeAuthorizationBinding(session.AuthorizationBinding);
        if (!string.Equals(session.AuthorizationBinding, authorizationBinding, StringComparison.Ordinal)
            || !string.Equals(session.SessionId, expectedSessionId, StringComparison.Ordinal)
            || session.Completed && session.Publishing
            || session.Completed && session.CompletionResult is null
            || !session.Completed && session.CompletionResult is not null
            || session.SingleUseAuthorization && session.AuthorizationExpiresAtUtc is null
            || session.Publishing && session.ActivationIntent is null
            || !session.Publishing && !session.Completed && session.ActivationIntent is not null
            || !session.Completed && session.CompletedAtUtc is not null
            || !session.Completed && session.ActivationAcknowledgedAtUtc is not null
            || session.ActivationAcknowledgedAtUtc is not null && session.ActivationIntent is null
            || session.Poisoned != !string.IsNullOrWhiteSpace(session.PoisonReason))
        {
            throw new InvalidDataException("upload session metadata is invalid.");
        }

        if (session.CandidateImportBinding is not null)
        {
            ValidateCandidateImportBinding(session.CandidateImportBinding);
            if (!session.SingleUseAuthorization || session.AuthorizationExpiresAtUtc is null)
            {
                throw new InvalidDataException("upload session candidate binding is invalid.");
            }
        }

        if (session.ActivationIntent is not null)
        {
            ValidateActivationIntent(session.ActivationIntent);
            if (session.Completed)
            {
                ValidateCompletionMatchesIntent(
                    session.CompletionResult!,
                    session.ActivationIntent);
            }
        }

        return authorizationBinding;
    }

    private static void ValidateCandidateImportBinding(
        ReleaseUploadCandidateSessionBinding binding)
    {
        if (!IsBareSha256(binding.SnapshotSha256)
            || !IsBareSha256(binding.AuthoritySha256)
            || !IsBareSha256(binding.BundleIdentitySha256)
            || !IsBareSha256(binding.CanonicalManifestSha256)
            || !IsBareSha256(binding.InventorySha256))
        {
            throw new InvalidDataException("upload session candidate binding is invalid.");
        }
    }

    private static bool IsBareSha256(string? value)
        => value is { Length: 64 }
           && value.All(static character => character is >= '0' and <= '9'
               or >= 'a' and <= 'f');

    private void CleanupCompletedPayload(string sessionRoot, string sessionId)
    {
        foreach (string name in new[] { "bundle", "staging" })
        {
            string path = Path.Combine(sessionRoot, name);
            if (!Directory.Exists(path))
            {
                continue;
            }

            try
            {
                Directory.Delete(path, recursive: true);
            }
            catch (Exception ex)
            {
                _logger.LogWarning(
                    "Completed release upload payload cleanup failed for {SessionId} ({ExceptionType}).",
                    sessionId,
                    ex.GetType().Name);
            }
        }

        _flushDirectoryEntry(sessionRoot);
    }

    private void PoisonSession(ReleaseUploadSession session, string reason)
    {
        try
        {
            PersistMetadata(
                Path.Combine(ResolveSessionsRoot(), session.SessionId),
                session with { Poisoned = true, PoisonReason = reason });
        }
        catch (Exception ex)
        {
            _logger.LogError(
                "Release upload session {SessionId} could not persist poison state ({ExceptionType}).",
                session.SessionId,
                ex.GetType().Name);
        }
    }

    private void PurgeExpiredSessionsUnderQuotaLock(string sessionsRoot)
    {
        IEnumerable<string> roots;
        try
        {
            roots = Directory.EnumerateDirectories(sessionsRoot).ToArray();
        }
        catch
        {
            return;
        }

        foreach (string sessionRoot in roots)
        {
            string sessionId = Path.GetFileName(sessionRoot);
            if (!TryCanonicalizeSessionId(sessionId, out string canonicalSessionId))
            {
                continue;
            }

            using FileStream? sessionLock = TryAcquireSessionLockForPurge(canonicalSessionId);
            if (sessionLock is null)
            {
                continue;
            }

            try
            {
                string metadataPath = Path.Combine(sessionRoot, "session.json");
                if (!File.Exists(metadataPath))
                {
                    throw new InvalidDataException(
                        "release upload session metadata is missing.");
                }

                RejectReparsePoint(metadataPath);
                ReleaseUploadSession? candidate =
                    JsonSerializer.Deserialize<ReleaseUploadSession>(File.ReadAllText(metadataPath));
                if (candidate is null
                    || !string.Equals(candidate.SessionId, canonicalSessionId, StringComparison.Ordinal))
                {
                    throw new InvalidDataException(
                        "release upload session metadata identity is invalid.");
                }

                _ = ValidateDurableSessionState(candidate, canonicalSessionId);
                if (EffectiveExpiry(candidate) <= DateTimeOffset.UtcNow)
                {
                    DeleteSessionPath(sessionRoot, canonicalSessionId);
                }
            }
            catch (Exception ex) when (ex is JsonException
                                       or InvalidDataException
                                       or IOException
                                       or UnauthorizedAccessException
                                       or NotSupportedException)
            {
                _logger.LogWarning(
                    "Release upload session {SessionId} has unverifiable metadata and was retained for operator reconciliation ({ExceptionType}).",
                    canonicalSessionId,
                    ex.GetType().Name);
            }
        }
    }

    private void DeleteSessionPath(string sessionRoot, string sessionIdForLog)
    {
        if (!Directory.Exists(sessionRoot))
        {
            return;
        }

        try
        {
            Directory.Delete(sessionRoot, recursive: true);
            _flushDirectoryEntry(ResolveSessionsRoot());
        }
        catch (Exception ex)
        {
            _logger.LogWarning(
                "Release upload session cleanup failed for {SessionId} ({ExceptionType}).",
                sessionIdForLog,
                ex.GetType().Name);
        }
    }

    private ReleaseUploadSession? FindSessionForAuthorization(string authorizationBinding)
    {
        foreach (string sessionRoot in Directory.EnumerateDirectories(ResolveSessionsRoot()))
        {
            string sessionId = Path.GetFileName(sessionRoot);
            if (!TryCanonicalizeSessionId(sessionId, out _))
            {
                continue;
            }

            try
            {
                ReleaseUploadSession session = ReadSessionMetadata(
                    sessionId,
                    authorizationBinding,
                    allowCompleted: true);
                return session;
            }
            catch (InvalidDataException)
            {
                // Different, invalid and expired sessions are not reusable.
            }
        }

        return null;
    }

    private string ResolveSessionsRoot()
        => ResolveSessionsRoot(requireConfigured: false);

    private string ResolveSessionsRoot(bool requireConfigured)
    {
        string configured = (_configuration[SessionsRootKey] ?? string.Empty).Trim();
        if (requireConfigured && string.IsNullOrWhiteSpace(configured))
        {
            throw new InvalidOperationException(
                $"{SessionsRootKey} must be configured on durable shared storage for signed-in release upload tickets.");
        }

        string root = string.IsNullOrWhiteSpace(configured)
            ? Path.Combine(Path.GetTempPath(), "chummer-release-upload-sessions")
            : configured;
        EnsureOwnerOnlyDirectory(root);
        RejectReparsePoint(root);
        return Path.GetFullPath(root);
    }

    private FileStream AcquireQuotaLock()
    {
        string path = Path.Combine(ResolveSessionsRoot(), ".quota.lock");
        for (int attempt = 0; attempt < 500; attempt++)
        {
            try
            {
                return OpenOwnerOnlyFile(path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
            }
            catch (IOException) when (attempt < 499)
            {
                Thread.Sleep(10);
            }
        }

        throw new InvalidOperationException("release upload quota authority is busy.");
    }

    private FileStream? TryAcquireQuotaLock(TimeSpan maximumWait, CancellationToken cancellationToken)
    {
        string path = Path.Combine(ResolveSessionsRoot(), ".quota.lock");
        DateTimeOffset deadline = DateTimeOffset.UtcNow.Add(maximumWait);
        while (DateTimeOffset.UtcNow < deadline)
        {
            cancellationToken.ThrowIfCancellationRequested();
            try
            {
                return OpenOwnerOnlyFile(path, FileMode.OpenOrCreate, FileAccess.ReadWrite, FileShare.None);
            }
            catch (IOException)
            {
                cancellationToken.WaitHandle.WaitOne(TimeSpan.FromMilliseconds(10));
            }
        }

        return null;
    }

    private FileStream AcquireSessionLock(string sessionId)
    {
        string sessionRoot = Path.Combine(ResolveSessionsRoot(), CanonicalizeSessionId(sessionId));
        if (!Directory.Exists(sessionRoot))
        {
            throw new InvalidDataException("upload session was not found.");
        }

        try
        {
            return OpenOwnerOnlyFile(
                Path.Combine(sessionRoot, ".session.lock"),
                FileMode.OpenOrCreate,
                FileAccess.ReadWrite,
                FileShare.None);
        }
        catch (IOException ex)
        {
            throw new InvalidOperationException("upload session is already being modified or completed.", ex);
        }
    }

    private FileStream AcquireAuthorizationLock(string authorizationBinding)
    {
        string root = Path.Combine(ResolveSessionsRoot(), ".authorization-locks");
        EnsureOwnerOnlyDirectory(root);
        try
        {
            return OpenOwnerOnlyFile(
                Path.Combine(root, authorizationBinding + ".lock"),
                FileMode.OpenOrCreate,
                FileAccess.ReadWrite,
                FileShare.None);
        }
        catch (IOException ex)
        {
            throw new InvalidOperationException("release upload authorization is already creating a session.", ex);
        }
    }

    private FileStream? TryAcquireSessionLockForPurge(string sessionId)
    {
        try
        {
            return AcquireSessionLock(sessionId);
        }
        catch (Exception ex) when (ex is InvalidDataException or InvalidOperationException or IOException or UnauthorizedAccessException)
        {
            return null;
        }
    }

    private DateTimeOffset EffectiveExpiry(ReleaseUploadSession session)
    {
        if (session.Publishing || session.Completed && session.ActivationAcknowledgedAtUtc is null)
        {
            return DateTimeOffset.MaxValue;
        }

        if (session.Completed)
        {
            DateTimeOffset retentionExpiry =
                session.ActivationAcknowledgedAtUtc!.Value.Add(
                    _options.CompletedReceiptRetention);
            if (session.SingleUseAuthorization
                && session.AuthorizationExpiresAtUtc is { } authorizationExpiry
                && authorizationExpiry > retentionExpiry)
            {
                return authorizationExpiry;
            }

            return retentionExpiry;
        }

        return session.ExpiresAtUtc;
    }

    private static bool TryCanonicalizeSessionId(string? sessionId, out string canonicalSessionId)
    {
        canonicalSessionId = string.Empty;
        if (string.IsNullOrWhiteSpace(sessionId) || !Guid.TryParse(sessionId, out Guid parsed))
        {
            return false;
        }

        canonicalSessionId = parsed.ToString("N");
        return true;
    }

    private static string CanonicalizeSessionId(string sessionId)
        => TryCanonicalizeSessionId(sessionId, out string canonical)
            ? canonical
            : throw new InvalidDataException("upload session id is required and must be a valid GUID.");

    private static string NormalizeAuthorizationBinding(string? authorizationBinding)
    {
        string normalized = (authorizationBinding ?? string.Empty).Trim().ToLowerInvariant();
        if (normalized.Length != 64 || normalized.Any(static value => !Uri.IsHexDigit(value)))
        {
            throw new InvalidDataException("upload session authorization binding must be a SHA-256 digest.");
        }

        return normalized;
    }

    private static long? TryGetRemainingLength(Stream content)
    {
        if (!content.CanSeek)
        {
            return null;
        }

        long remaining = content.Length - content.Position;
        return remaining < 0 ? null : remaining;
    }

    private static ReleaseUploadQuotaException PayloadTooLarge(string subject, long maximum)
        => new(
            StatusCodes.Status413PayloadTooLarge,
            $"{subject} exceeds its {maximum}-byte limit.");

    private void PersistMetadata(string sessionRoot, ReleaseUploadSession session)
    {
        EnsureOwnerOnlyDirectory(sessionRoot);
        WriteOwnerOnlyTextAtomically(
            Path.Combine(sessionRoot, "session.json"),
            JsonSerializer.Serialize(session));
    }

    private static ChunkUploadState? LoadChunkState(string statePath)
    {
        if (!File.Exists(statePath))
        {
            return null;
        }

        RejectReparsePoint(statePath);
        return JsonSerializer.Deserialize<ChunkUploadState>(File.ReadAllText(statePath));
    }

    private void PersistChunkState(string statePath, ChunkUploadState state)
        => WriteOwnerOnlyTextAtomically(statePath, JsonSerializer.Serialize(state));

    private static FileStream OpenOwnerOnlyFile(
        string path,
        FileMode mode,
        FileAccess access,
        FileShare share)
    {
        var options = new FileStreamOptions
        {
            Mode = mode,
            Access = access,
            Share = share,
            Options = FileOptions.WriteThrough
        };
        if (!OperatingSystem.IsWindows())
        {
            options.UnixCreateMode = OwnerFileMode;
        }

        FileStream stream = new(path, options);
        try
        {
            EnsureOwnerOnlyFile(path);
            return stream;
        }
        catch
        {
            stream.Dispose();
            throw;
        }
    }

    private static FileStream OpenOwnerOnlyAsyncFile(
        string path,
        FileMode mode,
        FileAccess access)
    {
        var options = new FileStreamOptions
        {
            Mode = mode,
            Access = access,
            Share = FileShare.None,
            Options = FileOptions.Asynchronous | FileOptions.WriteThrough,
            BufferSize = 81920
        };
        if (!OperatingSystem.IsWindows())
        {
            options.UnixCreateMode = OwnerFileMode;
        }

        FileStream stream = new(path, options);
        try
        {
            EnsureOwnerOnlyFile(path);
            return stream;
        }
        catch
        {
            stream.Dispose();
            throw;
        }
    }

    private void WriteOwnerOnlyTextAtomically(string path, string value)
    {
        string directory = Path.GetDirectoryName(path)
            ?? throw new InvalidDataException("upload session state path has no parent directory.");
        EnsureOwnerOnlyDirectory(directory);
        string temporaryPath = Path.Combine(directory, $".{Path.GetFileName(path)}.{Guid.NewGuid():N}.tmp");
        try
        {
            using (FileStream stream = OpenOwnerOnlyFile(
                       temporaryPath,
                       FileMode.CreateNew,
                       FileAccess.Write,
                       FileShare.None))
            using (var writer = new StreamWriter(
                       stream,
                       new UTF8Encoding(encoderShouldEmitUTF8Identifier: false),
                       bufferSize: 1024,
                       leaveOpen: true))
            {
                writer.Write(value);
                writer.Flush();
                stream.Flush(flushToDisk: true);
            }

            File.Move(temporaryPath, path, overwrite: true);
            EnsureOwnerOnlyFile(path);
            _flushDirectoryEntry(directory);
        }
        finally
        {
            TryDeleteFile(temporaryPath);
        }
    }

    private static void EnsureOwnerOnlyDirectory(string path)
    {
        if (Directory.Exists(path))
        {
            RejectReparsePoint(path);
        }

        Directory.CreateDirectory(path);
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(path, OwnerDirectoryMode);
        }
    }

    private static void EnsureOwnerOnlyFile(string path)
    {
        RejectReparsePoint(path);
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(path, OwnerFileMode);
        }
    }

    private static void RejectReparsePoint(string path)
    {
        if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
        {
            throw new InvalidDataException("release upload storage contains a forbidden link or reparse point.");
        }
    }

    private static bool TryDeleteFile(string path)
    {
        if (!File.Exists(path))
        {
            return true;
        }

        try
        {
            File.Delete(path);
            return true;
        }
        catch
        {
            return false;
        }
    }

    private static bool TryDeleteDirectory(string path)
    {
        try
        {
            if (Directory.Exists(path))
            {
                Directory.Delete(path, recursive: true);
            }
            return true;
        }
        catch
        {
            // The authoritative scanner keeps any orphan bytes charged.
            return false;
        }
    }

    private static void TryDeleteEmptyDirectory(string path)
    {
        try
        {
            if (Directory.Exists(path) && !Directory.EnumerateFileSystemEntries(path).Any())
            {
                Directory.Delete(path);
            }
        }
        catch
        {
            // Empty directory cleanup is best effort and carries no user bytes.
        }
    }

    private static void FlushDirectoryEntry(string directory)
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        int descriptor = NativeOpen(directory, 0);
        if (descriptor < 0)
        {
            throw new IOException(
                $"could not open release upload directory for fsync: {directory}",
                new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error()));
        }

        try
        {
            if (NativeFsync(descriptor) != 0)
            {
                throw new IOException(
                    $"could not fsync release upload directory: {directory}",
                    new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error()));
            }
        }
        finally
        {
            _ = NativeClose(descriptor);
        }
    }

    [DllImport("libc", EntryPoint = "open", SetLastError = true)]
    private static extern int NativeOpen(string path, int flags);

    [DllImport("libc", EntryPoint = "fsync", SetLastError = true)]
    private static extern int NativeFsync(int fileDescriptor);

    [DllImport("libc", EntryPoint = "close", SetLastError = true)]
    private static extern int NativeClose(int fileDescriptor);

    private static void VerifyPublicationDestinationWritable(
        string root,
        CancellationToken cancellationToken)
    {
        string probePath = Path.Combine(
            root,
            $".release-publication-readiness-{Environment.ProcessId}-{Guid.NewGuid():N}.tmp");
        bool created = false;
        try
        {
            var options = new FileStreamOptions
            {
                Mode = FileMode.CreateNew,
                Access = FileAccess.Write,
                Share = FileShare.None,
                Options = FileOptions.WriteThrough
            };
            if (!OperatingSystem.IsWindows())
            {
                options.UnixCreateMode = OwnerFileMode;
            }

            cancellationToken.ThrowIfCancellationRequested();
            using (FileStream probe = new(probePath, options))
            {
                created = true;
                probe.WriteByte(0);
                probe.Flush(flushToDisk: true);
            }

            File.Delete(probePath);
            created = false;
            FlushDirectoryEntry(root);
            cancellationToken.ThrowIfCancellationRequested();
        }
        finally
        {
            if (created)
            {
                try
                {
                    File.Delete(probePath);
                }
                catch
                {
                    // The readiness result remains fail-closed; the unique one-byte probe is
                    // intentionally never mistaken for a release generation or control file.
                }
            }
        }
    }

    public sealed class ReleaseUploadSessionCompletionLease : IDisposable
    {
        private readonly ReleaseBundleUploadSessionService _owner;
        private FileStream? _quotaLock;
        private FileStream? _sessionLock;
        private ReleaseUploadSession _session;

        internal ReleaseUploadSessionCompletionLease(
            ReleaseBundleUploadSessionService owner,
            FileStream quotaLock,
            FileStream sessionLock,
            ReleaseUploadSession session,
            bool recoveryOnly)
        {
            _owner = owner;
            _quotaLock = quotaLock;
            _sessionLock = sessionLock;
            _session = session;
            RecoveryOnly = recoveryOnly;
        }

        public string BundleRoot => _session.BundleRoot;
        public ReleaseUploadCandidateSessionBinding? CandidateImportBinding
            => _session.CandidateImportBinding;
        public ReleaseActivationIntent? ActivationIntent => _session.ActivationIntent;
        public ReleaseBundlePromotionResult? CompletedResult
            => _session.Completed ? _session.CompletionResult : null;
        public bool PublicationOutcomeUnknown => _session.Publishing && !_session.Completed;
        public bool RecoveryOnly { get; }

        public ReleaseUploadStorageReadiness EvaluateUploadStorageReadiness()
            => _owner.EvaluateStorageReadinessUnderQuotaLock(_owner.ResolveSessionsRoot());

        public ReleaseUploadStorageReadiness EvaluatePublicationDestinationReadiness(
            ReleaseShelfSnapshot snapshot,
            CancellationToken cancellationToken)
            => _owner.EvaluatePublicationDestinationReadiness(
                snapshot,
                _session.BundleRoot,
                cancellationToken);

        public ReleaseUploadStorageReadiness EvaluateSessionActivationReadiness(
            CancellationToken cancellationToken)
            => _owner.EvaluateActivationProtocolReadinessUnderQuotaLock(
                _owner.ResolveSessionsRoot(),
                cancellationToken);

        public void RecordActivationIntent(ReleaseActivationIntent intent)
            => _session = _owner.RecordActivationIntent(_session, intent);

        public void ResetAbortedActivation(ReleaseActivationIntent intent)
            => _session = _owner.ResetAbortedActivation(_session, intent);

        public void MarkPublishing()
            => throw new InvalidOperationException(
                "publishing requires a durable activation intent recorded by the promotion transaction.");

        public void MarkCompleted(ReleaseBundlePromotionResult result)
        {
            ArgumentNullException.ThrowIfNull(result);
            _owner.MarkSessionCompleted(_session, result);
            _session = _session with
            {
                Publishing = false,
                Completed = true,
                CompletionResult = result with { SignedInInstallClaims = null },
                CompletedAtUtc = DateTimeOffset.UtcNow
            };
        }

        public void MarkActivationAcknowledged()
        {
            if (!_session.Completed || _session.CompletionResult is null || _session.ActivationIntent is null)
            {
                throw new InvalidOperationException("only a durably completed activation may be acknowledged.");
            }

            if (_session.ActivationAcknowledgedAtUtc is not null)
            {
                return;
            }

            _session = _session with { ActivationAcknowledgedAtUtc = DateTimeOffset.UtcNow };
            _owner.PersistMetadata(
                Path.Combine(_owner.ResolveSessionsRoot(), _session.SessionId),
                _session);
        }

        public void Dispose()
        {
            _sessionLock?.Dispose();
            _sessionLock = null;
            _quotaLock?.Dispose();
            _quotaLock = null;
        }
    }

    private sealed record ChunkUploadState(string RelativePath, int TotalChunks, int NextChunkIndex);
    private sealed record PathBinding(string RelativePath);
    private sealed record TreeUsage(long Bytes, int Files);
    private sealed record SessionUsage(long Bytes, int LogicalFiles);
    private sealed record UsageSnapshot(
        long SharedBytes,
        int ActiveSessionCount,
        IReadOnlyDictionary<string, int> ActiveSessionsByAuthorization,
        IReadOnlyDictionary<string, SessionUsage> Sessions);
}

public sealed record ReleaseUploadStorageReadiness(bool Ready, string Code);
