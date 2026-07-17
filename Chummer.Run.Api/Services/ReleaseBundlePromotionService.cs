using System.Globalization;
using System.IO.Compression;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

public sealed record ReleaseBundlePromotionResult(
    string Version,
    string Channel,
    DateTimeOffset PublishedAt,
    IReadOnlyList<string> PromotedArtifactIds,
    string DownloadsUrl,
    IReadOnlyList<string> InstallDispatchUrls,
    IReadOnlyList<string> DirectFileUrls,
    IReadOnlyList<ReleasePromotionInstallClaim>? SignedInInstallClaims = null,
    string? GenerationId = null,
    string? ActivationReceiptId = null,
    DateTimeOffset? ActivatedAt = null,
    string? InventoryDigest = null,
    string? DurabilityWarning = null,
    string? CanonicalManifestSha256 = null,
    string? CompatibilityManifestSha256 = null);

public sealed record ReleasePromotionInstallClaim(
    string ArtifactId,
    string InstallDispatchUrl,
    string ClaimCode,
    DateTimeOffset? ClaimCodeExpiresAtUtc);

public sealed record ReleaseActivationIntent(
    string Operation,
    string? PreviousGenerationId,
    string? PreviousPointerSha256,
    string GenerationId,
    string ActivationReceiptId,
    string ReleaseVersion,
    string Channel,
    DateTimeOffset PublishedAt,
    string InventoryDigest,
    string PointerSha256,
    DateTimeOffset PreparedAtUtc,
    string? PreviousPointerBase64 = null,
    string? TargetPointerBase64 = null);

public sealed class ReleaseActivationOutcomeUnknownException : IOException
{
    public ReleaseActivationOutcomeUnknownException(
        ReleaseActivationIntent intent,
        Exception innerException)
        : base(
            "Release activation outcome is unknown; reconcile the durable activation receipt before retrying.",
            innerException)
    {
        Intent = intent;
    }

    public ReleaseActivationIntent Intent { get; }
}

public sealed class ReleaseActivationAbortedException : IOException
{
    public ReleaseActivationAbortedException(
        ReleaseActivationIntent intent,
        Exception innerException)
        : base(
            "Release activation was durably aborted before the public shelf pointer changed.",
            innerException)
    {
        Intent = intent;
    }

    public ReleaseActivationIntent Intent { get; }
}

/// <summary>
/// Test-only fault used to model process death at a durable checkpoint. Unlike a
/// normal exception, it deliberately bypasses in-process compensation so a fresh
/// service instance must reconcile the exact bytes left on disk.
/// </summary>
internal sealed class ReleaseActivationProcessTerminationSimulationException : IOException
{
    public ReleaseActivationProcessTerminationSimulationException(string message)
        : base(message)
    {
    }
}

public sealed class ReleaseBundlePromotionService
{
    private const string DownloadsRootKey = "CHUMMER_DOWNLOADS_SOURCE_ROOT";
    private const string DefaultDownloadsRoot = "/downloads-source";
    private const string CompatibilityManifestName = "releases.json";
    private const string CanonicalManifestName = "RELEASE_CHANNEL.generated.json";
    private const string RegistryContractName = "Chummer.Hub.Registry.Contracts";
    private const string ActivationCandidateName = "activation-candidate.json";
    private const string CurrentPointerName = "current.json";
    private const string LayoutMarkerName = ".release-shelf-layout-v1";
    private const string GenerationsDirectoryName = "generations";
    private const string LayoutMarkerContents = "chummer.release-shelf-layout/v1\n";
    private const string CurrentPointerSchema = "chummer.release-shelf.current/v1";
    private const string ActivationCandidateSchema = "chummer.release-shelf.activation-candidate/v1";
    private const string PromotionLockName = ".release-shelf-promotion.lock";
    private const string ActivationIntentName = ".release-shelf-activation-intent.json";
    private const string ActivationJournalDirectoryName = ".release-shelf-activation-journal";
    private const string ActivationJournalIntentName = "intent.json";
    private const string ActivationJournalOutcomeName = "outcome.json";
    private const string WriterPolicyName = ".release-shelf-writer-policy.json";
    private const string WriterPolicySchema = "chummer.release-shelf.writer-policy/v1";
    private const string WriterPolicyMode = "server-journal-v1";
    private const string InitialMigrationAllowedKey = "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED";
    private const string PromotionEvidenceRelativePath = "release-evidence/public-promotion.json";
    private const string PublicBaseUrlKey = "GOOGLE_OIDC_REDIRECT_URI";
    private static readonly TimeSpan MaximumReleaseProofPublicationLag = TimeSpan.FromHours(24);
    private static readonly TimeSpan MaximumReleaseProofPublicationClockSkew = TimeSpan.FromMinutes(5);
    private static readonly TimeSpan MaximumStartupSmokeAge = TimeSpan.FromDays(7);
    private static readonly TimeSpan MaximumStartupSmokeClockSkew = TimeSpan.FromMinutes(5);
    private static readonly string[] RequiredDesktopPlatforms = ["linux", "windows", "macos"];
    private static readonly string[] RequiredDesktopHeads = ["avalonia"];
    private static readonly string[] RequiredDesktopPlatformHeadRidTuples =
    [
        "avalonia:linux-x64:linux",
        "avalonia:osx-arm64:macos",
        "avalonia:win-x64:windows"
    ];
    private static readonly string[] DesktopRouteTruthHeads = ["avalonia", "blazor-desktop"];
    private static readonly IReadOnlyDictionary<string, string> DesktopRouteRoles = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
    {
        ["avalonia"] = "primary",
        ["blazor-desktop"] = "fallback"
    };
    private static readonly IReadOnlyDictionary<string, string> AppLabels = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
    {
        ["avalonia"] = "Avalonia Desktop",
        ["blazor-desktop"] = "Blazor Desktop"
    };
    private static readonly IReadOnlyDictionary<string, string[]> DefaultRequiredDesktopPlatformRids = new Dictionary<string, string[]>(StringComparer.OrdinalIgnoreCase)
    {
        ["linux"] = ["linux-x64"],
        ["windows"] = ["win-x64"],
        ["macos"] = ["osx-arm64"]
    };
    private static readonly IReadOnlyDictionary<string, (string Platform, string Arch)> RidToPlatformArch = new Dictionary<string, (string Platform, string Arch)>(StringComparer.OrdinalIgnoreCase)
    {
        ["linux-x64"] = ("linux", "x64"),
        ["linux-arm64"] = ("linux", "arm64"),
        ["win-x64"] = ("windows", "x64"),
        ["win-arm64"] = ("windows", "arm64"),
        ["osx-arm64"] = ("macos", "arm64"),
        ["osx-x64"] = ("macos", "x64")
    };
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = true,
        WriteIndented = true
    };
    private static readonly JsonSerializerOptions CanonicalManifestJsonOptions = new()
    {
        Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        WriteIndented = false
    };

    private readonly IConfiguration _configuration;
    private readonly ILogger<ReleaseBundlePromotionService> _logger;
    private readonly Action<PromotionCheckpoint>? _promotionCheckpoint;
    private readonly TimeProvider _timeProvider;
    private readonly PrivacyLaunchGateSnapshot _privacyLaunchGate;
    private readonly Action<string> _postActivationDirectoryFlush;
    private readonly Action<ActivationJournalCheckpoint>? _activationJournalCheckpoint;

    internal enum PromotionCheckpoint
    {
        StagedShelfValidated,
        ActivationIntentRecorded,
        GenerationDirectoryDurable,
        GenerationPrepared,
        PointerPrepared,
        PointerActivated,
        CompatibilityMirrorsUpdated,
        // Retained as source-compatible aliases for older focused tests. They are
        // never emitted by the layout-v1 writer because top-level entries are not
        // authoritative commit points anymore.
        FilesReplaced,
        StartupSmokeReplaced,
        ProofReplaced,
        CanonicalManifestReplaced,
        CompatibilityManifestReplaced
    }

    internal enum ActivationJournalCheckpoint
    {
        ActiveIntentDurable,
        ReceiptTempDirectoryDurable,
        ReceiptIntentDurable,
        ReceiptHistoryPublished,
        ReceiptHistoryParentDurable
    }

    public ReleaseBundlePromotionService(
        IConfiguration configuration,
        ILogger<ReleaseBundlePromotionService> logger)
        : this(
            configuration,
            logger,
            promotionCheckpoint: null,
            TimeProvider.System,
            PrivacyLaunchGate.Current,
            postActivationDirectoryFlush: null)
    {
    }

    internal ReleaseBundlePromotionService(
        IConfiguration configuration,
        ILogger<ReleaseBundlePromotionService> logger,
        Action<PromotionCheckpoint>? promotionCheckpoint)
        : this(
            configuration,
            logger,
            promotionCheckpoint,
            TimeProvider.System,
            PrivacyLaunchGate.Current,
            postActivationDirectoryFlush: null)
    {
    }

    internal ReleaseBundlePromotionService(
        IConfiguration configuration,
        ILogger<ReleaseBundlePromotionService> logger,
        Action<PromotionCheckpoint>? promotionCheckpoint,
        TimeProvider timeProvider)
        : this(
            configuration,
            logger,
            promotionCheckpoint,
            timeProvider,
            PrivacyLaunchGate.Current,
            postActivationDirectoryFlush: null)
    {
    }

    internal ReleaseBundlePromotionService(
        IConfiguration configuration,
        ILogger<ReleaseBundlePromotionService> logger,
        Action<PromotionCheckpoint>? promotionCheckpoint,
        TimeProvider timeProvider,
        PrivacyLaunchGateSnapshot privacyLaunchGate,
        Action<string>? postActivationDirectoryFlush = null,
        Action<ActivationJournalCheckpoint>? activationJournalCheckpoint = null)
    {
        _configuration = configuration;
        _logger = logger;
        _promotionCheckpoint = promotionCheckpoint;
        _timeProvider = timeProvider ?? throw new ArgumentNullException(nameof(timeProvider));
        _privacyLaunchGate = privacyLaunchGate ?? throw new ArgumentNullException(nameof(privacyLaunchGate));
        _postActivationDirectoryFlush = postActivationDirectoryFlush ?? FlushDirectoryDurably;
        _activationJournalCheckpoint = activationJournalCheckpoint;
    }

    public async Task<ReleaseBundlePromotionResult> PromoteAsync(
        string? uploadedFileName,
        Stream bundleStream,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(bundleStream);

        string downloadsRoot = ResolveDownloadsRoot();
        EnsureDownloadsRootWritable(downloadsRoot);

        string tempRoot = Path.Combine(Path.GetTempPath(), "chummer-release-bundles", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        try
        {
            string bundleFileName = string.IsNullOrWhiteSpace(uploadedFileName) ? "bundle.zip" : Path.GetFileName(uploadedFileName);
            string bundlePath = Path.Combine(tempRoot, bundleFileName);
            await using (FileStream fileStream = File.Create(bundlePath))
            {
                await bundleStream.CopyToAsync(fileStream, cancellationToken);
            }

            string extractRoot = Path.Combine(tempRoot, "bundle");
            ZipFile.ExtractToDirectory(bundlePath, extractRoot);

            string bundleRoot = ResolveBundleRoot(extractRoot);
            return await PromotePreparedBundleAsync(
                bundleRoot,
                downloadsRoot,
                recordActivationIntent: null,
                cancellationToken);
        }
        finally
        {
            try
            {
                if (Directory.Exists(tempRoot))
                {
                    Directory.Delete(tempRoot, recursive: true);
                }
            }
            catch (Exception ex)
            {
                _logger.LogWarning(ex, "Release bundle promotion cleanup failed for {TempRoot}.", tempRoot);
            }
        }
    }

    public async Task<ReleaseBundlePromotionResult> PromoteDirectoryAsync(
        string bundleRoot,
        CancellationToken cancellationToken)
        => await PromoteDirectoryAsync(bundleRoot, recordActivationIntent: null, cancellationToken);

    public async Task<ReleaseBundlePromotionResult> PromoteDirectoryAsync(
        string bundleRoot,
        Action<ReleaseActivationIntent>? recordActivationIntent,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(bundleRoot))
        {
            throw new InvalidDataException("bundle root is required.");
        }

        cancellationToken.ThrowIfCancellationRequested();
        string downloadsRoot = ResolveDownloadsRoot();
        EnsureDownloadsRootWritable(downloadsRoot);
        return await PromotePreparedBundleAsync(
            bundleRoot,
            downloadsRoot,
            recordActivationIntent,
            cancellationToken);
    }

    /// <summary>
    /// Runs every deterministic, bundle-local validation while the upload-session
    /// lock still prevents further writes. Callers can then persist the irreversible
    /// publishing boundary immediately before entering the live-shelf transaction.
    /// </summary>
    public Task ValidateDirectoryAsync(
        string bundleRoot,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(bundleRoot))
        {
            throw new InvalidDataException("bundle root is required.");
        }

        cancellationToken.ThrowIfCancellationRequested();
        _ = PrepareBundle(bundleRoot);
        return Task.CompletedTask;
    }

    /// <summary>
    /// Performs the one-time legacy-to-layout-v1 cutover during host startup. The
    /// legacy shelf is treated as the prepared Registry bundle and enters the same
    /// durable server-journal transaction as an HTTP upload; no second upload is
    /// required merely to establish the first immutable generation.
    /// </summary>
    public async Task<ReleaseBundlePromotionResult?> EnsureInitialLegacyMigrationAsync(
        CancellationToken cancellationToken)
    {
        if (!_configuration.GetValue(InitialMigrationAllowedKey, false))
        {
            return null;
        }

        string downloadsRoot = ResolveDownloadsRoot();
        EnsureDownloadsRootWritable(downloadsRoot);
        string activeIntentPath = Path.Combine(downloadsRoot, ActivationIntentName);
        if (File.Exists(activeIntentPath))
        {
            ReleaseActivationJournalDocument active = LoadActivationJournalFile(activeIntentPath);
            if (TryReconcileActivation(active.Intent, out ReleaseBundlePromotionResult? reconciled))
            {
                return reconciled;
            }
        }

        ReleaseShelfSnapshot snapshot = new ReleaseShelfGenerationStore(_configuration).Capture();
        if (!snapshot.IsLegacy)
        {
            using FileStream promotionLock = AcquirePromotionLock(downloadsRoot);
            EnsureServerWriterPolicy(downloadsRoot);
            return null;
        }

        return await PromotePreparedBundleAsync(
            downloadsRoot,
            downloadsRoot,
            recordActivationIntent: null,
            cancellationToken);
    }

    internal ReleaseShelfPublicationReadinessProbeResult EvaluateActivationProtocolReadiness(
        ReleaseShelfSnapshot snapshot,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        string downloadsRoot = ResolveDownloadsRoot();
        try
        {
            cancellationToken.ThrowIfCancellationRequested();
            string policyPath = Path.Combine(downloadsRoot, WriterPolicyName);
            if (!File.Exists(policyPath))
            {
                return new ReleaseShelfPublicationReadinessProbeResult(false, "writer_policy_missing");
            }

            ValidateServerWriterPolicy(policyPath);
            cancellationToken.ThrowIfCancellationRequested();
            string activePath = Path.Combine(downloadsRoot, ActivationIntentName);
            ReleaseActivationJournalDocument? active = File.Exists(activePath)
                ? LoadActivationJournalFile(activePath)
                : null;
            string historyRoot = ActivationJournalHistoryRoot(downloadsRoot);
            if (!Directory.Exists(historyRoot))
            {
                return active is null
                    ? new ReleaseShelfPublicationReadinessProbeResult(true, "ready")
                    : new ReleaseShelfPublicationReadinessProbeResult(false, "activation_journal_unresolved");
            }

            EnsureRegularDirectory(historyRoot, "release activation journal history");
            foreach (string receiptRoot in Directory.EnumerateFileSystemEntries(historyRoot))
            {
                cancellationToken.ThrowIfCancellationRequested();
                if (!Directory.Exists(receiptRoot))
                {
                    return new ReleaseShelfPublicationReadinessProbeResult(false, "activation_protocol_invalid");
                }

                EnsureRegularDirectory(receiptRoot, "release activation journal receipt directory");
                string receiptId = Path.GetFileName(receiptRoot);
                ReleaseActivationJournalDocument journal = LoadActivationHistoryJournal(downloadsRoot, receiptId);
                ReleaseActivationOutcomeDocument? outcome = TryLoadActivationOutcome(downloadsRoot, journal);
                if (outcome is null)
                {
                    return new ReleaseShelfPublicationReadinessProbeResult(false, "activation_journal_unresolved");
                }
            }

            if (active is not null)
            {
                return new ReleaseShelfPublicationReadinessProbeResult(false, "activation_ack_pending");
            }

            return new ReleaseShelfPublicationReadinessProbeResult(true, "ready");
        }
        catch (OperationCanceledException)
        {
            throw;
        }
        catch
        {
            return new ReleaseShelfPublicationReadinessProbeResult(false, "activation_protocol_invalid");
        }
    }

    public bool TryReconcileActivation(
        ReleaseActivationIntent intent,
        out ReleaseBundlePromotionResult? result)
    {
        ArgumentNullException.ThrowIfNull(intent);
        ValidateActivationIntent(intent);
        result = null;

        string downloadsRoot = ResolveDownloadsRoot();
        EnsureDownloadsRootWritable(downloadsRoot);
        using FileStream promotionLock = AcquirePromotionLock(downloadsRoot);
        EnsureServerWriterPolicy(downloadsRoot);
        string activePath = Path.Combine(downloadsRoot, ActivationIntentName);
        ReleaseActivationJournalDocument? active = File.Exists(activePath)
            ? LoadActivationJournalFile(activePath)
            : null;
        if (active is not null)
        {
            if (active.Intent != intent)
            {
                throw new ReleaseActivationOutcomeUnknownException(
                    intent,
                    new InvalidDataException(
                        "active release activation barrier does not match the session-bound intent."));
            }

            // This is intentionally called even when intent.json is already visible:
            // its existing-receipt branch re-fsyncs the history parent before an
            // outcome may be written and the active barrier removed.
            EnsureHistoryForActivePartial(downloadsRoot, active);
        }

        string receiptRoot = ActivationJournalReceiptRoot(downloadsRoot, intent.ActivationReceiptId);
        if (!Directory.Exists(receiptRoot) && !File.Exists(receiptRoot))
        {
            if (!string.Equals(intent.Operation, "promotion", StringComparison.Ordinal))
            {
                throw new ReleaseActivationOutcomeUnknownException(
                    intent,
                    new InvalidDataException(
                        "rollback activation cannot be reconciled without immutable journal history."));
            }

            try
            {
                RemoveNeverActivatedGenerationDurably(
                    downloadsRoot,
                    intent,
                    requireAbortedHistory: false);
            }
            catch (Exception ex) when (ex is not ReleaseActivationOutcomeUnknownException)
            {
                throw new ReleaseActivationOutcomeUnknownException(intent, ex);
            }

            return false;
        }

        ReleaseActivationJournalDocument journal = LoadActivationHistoryJournal(downloadsRoot, intent.ActivationReceiptId);
        if (journal.Intent != intent)
        {
            throw new InvalidDataException("release activation reconciliation intent does not match its immutable journal history.");
        }

        ReleaseActivationOutcomeDocument? existingOutcome = TryLoadActivationOutcome(downloadsRoot, journal);
        if (existingOutcome is not null)
        {
            if (string.Equals(existingOutcome.State, "aborted", StringComparison.Ordinal))
            {
                ResolveActivationIntentDurably(downloadsRoot, journal, state: "aborted");
                if (string.Equals(intent.Operation, "promotion", StringComparison.Ordinal))
                {
                    RemoveNeverActivatedGenerationDurably(
                        downloadsRoot,
                        intent,
                        requireAbortedHistory: true);
                }

                return false;
            }

            result = BuildPromotionResultFromCommittedJournal(downloadsRoot, journal);
            AcknowledgeActivationCompletionUnderLock(downloadsRoot, intent);
            return true;
        }

        string pointerPath = Path.Combine(downloadsRoot, CurrentPointerName);
        byte[]? currentPointerBytes = ReadRegularFileBytesOrNull(pointerPath, "release shelf current pointer");
        string? currentPointerSha256 = Sha256BindingForBytes(currentPointerBytes);
        if (string.Equals(currentPointerSha256, intent.PointerSha256, StringComparison.Ordinal))
        {
            byte[] targetPointerBytes = DecodeRequiredPointerBytes(journal.TargetPointerBase64, "target");
            if (currentPointerBytes is null
                || !CryptographicOperations.FixedTimeEquals(currentPointerBytes, targetPointerBytes))
            {
                throw new ReleaseActivationOutcomeUnknownException(
                    intent,
                    new InvalidDataException("live release shelf pointer bytes do not match the unresolved activation intent."));
            }

            try
            {
                _ = BuildPromotionResultFromCommittedJournal(downloadsRoot, journal);
                _postActivationDirectoryFlush(downloadsRoot);
                ResolveActivationIntentDurably(downloadsRoot, journal, state: "committed");
                AcknowledgeActivationCompletionUnderLock(downloadsRoot, intent);
            }
            catch (Exception ex) when (ex is not ReleaseActivationOutcomeUnknownException)
            {
                throw new ReleaseActivationOutcomeUnknownException(intent, ex);
            }

            result = BuildPromotionResultFromCommittedJournal(downloadsRoot, journal);
            return true;
        }

        if (string.Equals(currentPointerSha256, intent.PreviousPointerSha256, StringComparison.Ordinal))
        {
            byte[]? previousPointerBytes = DecodeOptionalPointerBytes(journal.PreviousPointerBase64);
            if (!BytesEqual(currentPointerBytes, previousPointerBytes))
            {
                throw new ReleaseActivationOutcomeUnknownException(
                    intent,
                    new InvalidDataException("current.json digest matched, but its exact bytes did not match the retained previous pointer."));
            }

            if (currentPointerBytes is null)
            {
                RemoveUnactivatedLayoutMarkerDurably(downloadsRoot);
            }

            FlushDirectoryDurably(downloadsRoot);
            ResolveActivationIntentDurably(downloadsRoot, journal, state: "aborted");
            if (string.Equals(intent.Operation, "promotion", StringComparison.Ordinal))
            {
                RemoveNeverActivatedGenerationDurably(
                    downloadsRoot,
                    intent,
                    requireAbortedHistory: true);
            }

            return false;
        }

        throw new ReleaseActivationOutcomeUnknownException(
            intent,
            new InvalidDataException("current.json matches neither the previous nor target activation pointer digest."));
    }

    private void RemoveNeverActivatedGenerationDurably(
        string downloadsRoot,
        ReleaseActivationIntent intent,
        bool requireAbortedHistory)
    {
        ValidateActivationIntent(intent);
        if (!string.Equals(intent.Operation, "promotion", StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "only a never-activated promotion generation may be removed.");
        }

        string activePath = Path.Combine(downloadsRoot, ActivationIntentName);
        if (File.Exists(activePath))
        {
            ReleaseActivationJournalDocument active = LoadActivationJournalFile(activePath);
            if (active.Intent != intent)
            {
                throw new InvalidDataException(
                    "another release activation intent is active while reconciling an unactivated generation.");
            }

            ReleaseActivationOutcomeDocument? activeOutcome = TryLoadActivationOutcome(downloadsRoot, active);
            if (activeOutcome is null || !string.Equals(activeOutcome.State, "aborted", StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    "release activation intent is not durably aborted before generation cleanup.");
            }
        }

        byte[]? expectedPreviousPointerBytes;
        string receiptRoot = ActivationJournalReceiptRoot(downloadsRoot, intent.ActivationReceiptId);
        if (requireAbortedHistory)
        {
            ReleaseActivationJournalDocument journal = LoadActivationHistoryJournal(
                downloadsRoot,
                intent.ActivationReceiptId);
            if (journal.Intent != intent)
            {
                throw new InvalidDataException(
                    "aborted release activation history does not match generation cleanup intent.");
            }

            ReleaseActivationOutcomeDocument outcome = TryLoadActivationOutcome(downloadsRoot, journal)
                ?? throw new InvalidDataException(
                    "release activation outcome is missing before generation cleanup.");
            if (!string.Equals(outcome.State, "aborted", StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    "a committed release activation generation cannot be removed.");
            }

            expectedPreviousPointerBytes = DecodeOptionalPointerBytes(journal.PreviousPointerBase64);
        }
        else
        {
            if (Directory.Exists(receiptRoot) || File.Exists(receiptRoot))
            {
                throw new InvalidDataException(
                    "unjournaled activation reconciliation found a receipt path.");
            }

            if (File.Exists(activePath))
            {
                throw new InvalidDataException(
                    "unjournaled activation reconciliation found an active journal barrier.");
            }

            expectedPreviousPointerBytes = DecodeOptionalPointerBytes(
                intent.PreviousPointerBase64);
        }

        string pointerPath = Path.Combine(downloadsRoot, CurrentPointerName);
        byte[]? currentPointerBytes = ReadRegularFileBytesOrNull(
            pointerPath,
            "release shelf current pointer");
        if (!string.Equals(
                Sha256BindingForBytes(currentPointerBytes),
                intent.PreviousPointerSha256,
                StringComparison.Ordinal)
            || !BytesEqual(currentPointerBytes, expectedPreviousPointerBytes))
        {
            throw new InvalidDataException(
                "live release shelf pointer is not byte-identical to the activation intent's previous pointer.");
        }

        EnsureNoCommittedOrConflictingTargetHistory(
            downloadsRoot,
            intent,
            allowMatchingAbortedReceipt: requireAbortedHistory);

        string generationsRoot = Path.GetFullPath(
            Path.Combine(downloadsRoot, GenerationsDirectoryName));
        string generationRoot = Path.GetFullPath(
            Path.Combine(generationsRoot, intent.GenerationId));
        string containedPrefix = generationsRoot.EndsWith(Path.DirectorySeparatorChar)
            ? generationsRoot
            : generationsRoot + Path.DirectorySeparatorChar;
        if (!generationRoot.StartsWith(
                containedPrefix,
                OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal))
        {
            throw new InvalidDataException("release activation target generation path escapes its governed root.");
        }

        if (!Directory.Exists(generationRoot))
        {
            return;
        }

        ValidateNeverActivatedGeneration(generationRoot, intent);
        MakeGenerationDeletable(generationRoot);
        Directory.Delete(generationRoot, recursive: true);
        FlushDirectoryDurably(generationsRoot);
    }

    private static void EnsureNoCommittedOrConflictingTargetHistory(
        string downloadsRoot,
        ReleaseActivationIntent intent,
        bool allowMatchingAbortedReceipt)
    {
        string historyRoot = ActivationJournalHistoryRoot(downloadsRoot);
        if (!Directory.Exists(historyRoot))
        {
            return;
        }

        EnsureRegularDirectory(historyRoot, "release activation journal history");
        foreach (string entry in Directory.EnumerateFileSystemEntries(historyRoot))
        {
            if (!Directory.Exists(entry))
            {
                throw new InvalidDataException(
                    "release activation journal history contains a non-directory entry.");
            }

            string receiptId = Path.GetFileName(entry);
            ReleaseActivationJournalDocument journal = LoadActivationHistoryJournal(downloadsRoot, receiptId);
            if (!string.Equals(
                    journal.Intent.GenerationId,
                    intent.GenerationId,
                    StringComparison.Ordinal)
                && !string.Equals(
                    journal.Intent.ActivationReceiptId,
                    intent.ActivationReceiptId,
                    StringComparison.Ordinal))
            {
                continue;
            }

            ReleaseActivationOutcomeDocument? outcome = TryLoadActivationOutcome(downloadsRoot, journal);
            bool allowedAborted = allowMatchingAbortedReceipt
                                  && journal.Intent == intent
                                  && outcome is not null
                                  && string.Equals(outcome.State, "aborted", StringComparison.Ordinal);
            if (!allowedAborted)
            {
                throw new InvalidDataException(
                    "release activation target generation has conflicting or committed history.");
            }
        }
    }

    private static void ValidateNeverActivatedGeneration(
        string generationRoot,
        ReleaseActivationIntent intent)
    {
        EnsureRegularDirectory(generationRoot, "never-activated release generation");
        string candidatePath = Path.Combine(generationRoot, ActivationCandidateName);
        EnsureRegularFile(candidatePath, "never-activated release generation candidate");
        ActivationCandidateDocument candidate = JsonSerializer.Deserialize<ActivationCandidateDocument>(
                File.ReadAllText(candidatePath),
                JsonOptions)
            ?? throw new InvalidDataException(
                "never-activated release generation candidate is malformed.");
        IReadOnlyList<ActivationInventoryEntry> inventory = BuildActivationInventory(generationRoot);
        if (!string.Equals(candidate.SchemaVersion, ActivationCandidateSchema, StringComparison.Ordinal)
            || !string.Equals(candidate.GenerationId, intent.GenerationId, StringComparison.Ordinal)
            || !string.Equals(candidate.ReleaseVersion, intent.ReleaseVersion, StringComparison.Ordinal)
            || !string.Equals(candidate.Channel, intent.Channel, StringComparison.Ordinal)
            || !DateTimeOffset.TryParse(
                candidate.PublishedAt,
                CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal,
                out DateTimeOffset publishedAt)
            || publishedAt.ToUniversalTime() != intent.PublishedAt
            || !string.Equals(candidate.InventoryDigest, intent.InventoryDigest, StringComparison.Ordinal)
            || candidate.Inventory is null
            || !candidate.Inventory.SequenceEqual(inventory))
        {
            throw new InvalidDataException(
                "never-activated release generation does not match its recorded activation intent.");
        }
    }

    private static void MakeGenerationDeletable(string generationRoot)
    {
        foreach (string filePath in EnumerateRegularFilesWithoutLinks(generationRoot))
        {
            if (OperatingSystem.IsWindows())
            {
                File.SetAttributes(filePath, FileAttributes.Normal);
            }
            else
            {
                File.SetUnixFileMode(
                    filePath,
                    UnixFileMode.UserRead | UnixFileMode.UserWrite);
            }
        }

        if (!OperatingSystem.IsWindows())
        {
            UnixFileMode directoryMode = UnixFileMode.UserRead
                                         | UnixFileMode.UserWrite
                                         | UnixFileMode.UserExecute;
            foreach (string directory in Directory.EnumerateDirectories(
                         generationRoot,
                         "*",
                         SearchOption.AllDirectories))
            {
                File.SetUnixFileMode(directory, directoryMode);
            }

            File.SetUnixFileMode(generationRoot, directoryMode);
        }
    }

    /// <summary>
    /// Clears the active activation barrier only after the owning upload session has
    /// durably stored its completed result. The immutable receipt history is retained.
    /// </summary>
    public void AcknowledgeActivationCompletion(ReleaseActivationIntent intent)
    {
        ArgumentNullException.ThrowIfNull(intent);
        ValidateActivationIntent(intent);
        string downloadsRoot = ResolveDownloadsRoot();
        EnsureDownloadsRootWritable(downloadsRoot);
        using FileStream promotionLock = AcquirePromotionLock(downloadsRoot);
        EnsureServerWriterPolicy(downloadsRoot);
        AcknowledgeActivationCompletionUnderLock(downloadsRoot, intent);
    }

    /// <summary>
    /// Atomically re-activates an already validated immutable generation. Rollback
    /// never rewrites generation bytes; its sole authority mutation is current.json.
    /// </summary>
    public Task<ReleaseBundlePromotionResult> RollbackToGenerationAsync(
        string generationId,
        CancellationToken cancellationToken)
    {
        if (!IsSafeGenerationId(generationId))
        {
            throw new InvalidDataException("rollback generationId is not a traversal-safe opaque token.");
        }

        string downloadsRoot = ResolveDownloadsRoot();
        EnsureDownloadsRootWritable(downloadsRoot);
        using FileStream promotionLock = AcquirePromotionLock(downloadsRoot);
        EnsureServerWriterPolicy(downloadsRoot);
        EnsureNoUnresolvedActivationIntent(downloadsRoot);
        ReleaseShelfSnapshot activeShelf = new ReleaseShelfGenerationStore(_configuration).Capture();
        if (activeShelf.IsLegacy)
        {
            throw new InvalidOperationException("release shelf rollback requires an activated layout-v1 generation.");
        }

        string generationsRoot = Path.GetFullPath(Path.Combine(downloadsRoot, GenerationsDirectoryName));
        string generationRoot = Path.GetFullPath(Path.Combine(generationsRoot, generationId));
        string containedPrefix = generationsRoot.EndsWith(Path.DirectorySeparatorChar)
            ? generationsRoot
            : generationsRoot + Path.DirectorySeparatorChar;
        if (!generationRoot.StartsWith(
                containedPrefix,
                OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal)
            || !Directory.Exists(generationRoot))
        {
            throw new InvalidDataException($"retained release shelf generation does not exist: {generationId}");
        }

        RequireCommittedGenerationHistory(downloadsRoot, generationId);

        ActivationCandidateDocument candidate = JsonSerializer.Deserialize<ActivationCandidateDocument>(
                File.ReadAllText(Path.Combine(generationRoot, ActivationCandidateName)),
                JsonOptions)
            ?? throw new InvalidDataException("retained release shelf activation candidate is malformed.");
        if (!string.Equals(candidate.SchemaVersion, ActivationCandidateSchema, StringComparison.Ordinal)
            || !string.Equals(candidate.GenerationId, generationId, StringComparison.Ordinal)
            || string.IsNullOrWhiteSpace(candidate.ReleaseVersion)
            || string.IsNullOrWhiteSpace(candidate.Channel)
            || string.IsNullOrWhiteSpace(candidate.PublishedAt)
            || candidate.Manifests is null
            || string.IsNullOrWhiteSpace(candidate.InventoryDigest))
        {
            throw new InvalidDataException("retained release shelf activation candidate identity is invalid.");
        }

        ValidateCandidateManifestBindings(generationRoot, generationId, candidate.Manifests);
        PublicReleaseManifestDto compatibilityManifest = LoadCompatibilityManifest(
            Path.Combine(generationRoot, CompatibilityManifestName));
        if (!DateTimeOffset.TryParse(
                candidate.PublishedAt,
                CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal,
                out DateTimeOffset candidatePublishedAt)
            || !string.Equals(candidate.ReleaseVersion, compatibilityManifest.Version, StringComparison.Ordinal)
            || !string.Equals(candidate.Channel, compatibilityManifest.Channel, StringComparison.Ordinal)
            || candidatePublishedAt.ToUniversalTime() != compatibilityManifest.PublishedAt.ToUniversalTime())
        {
            throw new InvalidDataException("retained release shelf activation candidate identity disagrees with its manifests.");
        }

        IReadOnlyList<string> artifactIds = compatibilityManifest.Downloads
            .Select(static artifact => artifact.Id)
            .Where(static id => !string.IsNullOrWhiteSpace(id))
            .ToArray();

        IReadOnlyList<ActivationInventoryEntry> inventory = BuildActivationInventory(generationRoot);
        string inventoryDigest = ComputeInventoryDigest(inventory);
        if (!candidate.Inventory.SequenceEqual(inventory)
            || !string.Equals(candidate.InventoryDigest, $"sha256:{inventoryDigest}", StringComparison.Ordinal))
        {
            throw new InvalidDataException("retained release shelf activation inventory no longer matches immutable bytes.");
        }

        DateTimeOffset activatedAt = _timeProvider.GetUtcNow().ToUniversalTime();
        string activationReceiptId = $"activation-{Guid.NewGuid():N}";
        CurrentPointerDocument pointer = BuildCurrentPointer(
            generationId,
            activationReceiptId,
            activatedAt,
            compatibilityManifest,
            generationRoot,
            inventoryDigest);
        ValidatePreparedGeneration(generationRoot, pointer, inventory, artifactIds);
        cancellationToken.ThrowIfCancellationRequested();

        string baseUrl = ResolvePublicBaseUrl();
        ReleaseBundlePromotionResult result = new(
            compatibilityManifest.Version,
            compatibilityManifest.Channel,
            compatibilityManifest.PublishedAt,
            artifactIds,
            $"{baseUrl}/downloads/",
            compatibilityManifest.Downloads
                .Where(static artifact => !string.IsNullOrWhiteSpace(artifact.Id))
                .Select(artifact => BuildGenerationArtifactUrl(baseUrl, generationId, artifact))
                .ToArray(),
            compatibilityManifest.Downloads
                .Select(download => BuildGenerationArtifactUrl(baseUrl, generationId, download))
                .ToArray(),
            GenerationId: generationId,
            ActivationReceiptId: activationReceiptId,
            ActivatedAt: activatedAt,
            InventoryDigest: $"sha256:{inventoryDigest}");

        string? pointerTempPath = null;
        bool pointerActivated = false;
        ReleaseActivationIntent? activationIntent = null;
        bool activationJournalPrepared = false;
        try
        {
            pointerTempPath = PrepareCurrentPointerFile(downloadsRoot, pointer);
            activationIntent = BuildActivationIntent(
                "rollback",
                activeShelf,
                result,
                pointerTempPath);
            PrepareActivationIntentDurably(downloadsRoot, activationIntent, pointerTempPath);
            activationJournalPrepared = true;
            NotifyCheckpoint(PromotionCheckpoint.PointerPrepared);
            cancellationToken.ThrowIfCancellationRequested();
            ActivateCurrentPointer(pointerTempPath, Path.Combine(downloadsRoot, CurrentPointerName));
            pointerTempPath = null;
            pointerActivated = true;

            ConfirmActivationDirectoryDurability(downloadsRoot, activationIntent);
            try
            {
                AcknowledgeActivationCompletionUnderLock(downloadsRoot, activationIntent);
            }
            catch (Exception ex)
            {
                throw new ReleaseActivationOutcomeUnknownException(activationIntent, ex);
            }
            NotifyPostActivationCheckpoint(PromotionCheckpoint.PointerActivated);
            TryUpdateCompatibilityMirrors(generationRoot, downloadsRoot);
            NotifyPostActivationCheckpoint(PromotionCheckpoint.CompatibilityMirrorsUpdated);
            return Task.FromResult(result);
        }
        catch (Exception ex)
        {
            if (ex is ReleaseActivationProcessTerminationSimulationException)
            {
                throw;
            }

            if (!pointerActivated && activationJournalPrepared && activationIntent is not null)
            {
                AbortPreparedActivationIntent(downloadsRoot, activationIntent);
                throw new ReleaseActivationAbortedException(activationIntent, ex);
            }

            throw;
        }
        finally
        {
            if (!pointerActivated && !string.IsNullOrWhiteSpace(pointerTempPath))
            {
                TryDeleteFile(pointerTempPath);
            }
        }
    }

    private Task<ReleaseBundlePromotionResult> PromotePreparedBundleAsync(
        string bundleRoot,
        string downloadsRoot,
        Action<ReleaseActivationIntent>? recordActivationIntent,
        CancellationToken cancellationToken)
    {
        PreparedReleaseBundle prepared = PrepareBundle(bundleRoot);
        PublicReleaseManifestDto incomingCompatibilityManifest = prepared.CompatibilityManifest;
        JsonObject incomingCompatibilityManifestObject = prepared.CompatibilityManifestObject;
        JsonObject incomingCanonicalManifest = prepared.CanonicalManifest;
        string filesRoot = prepared.FilesRoot;
        string? startupSmokeRoot = prepared.StartupSmokeRoot;
        string? signingRoot = prepared.SigningRoot;
        string? proofRoot = prepared.ProofRoot;
        string? releaseEvidenceRoot = prepared.ReleaseEvidenceRoot;
        string? aurPackagesPath = prepared.AurPackagesPath;
        IReadOnlyList<string> promotedArtifactIds = prepared.PromotedArtifactIds;

        using FileStream promotionLock = AcquirePromotionLock(downloadsRoot);
        EnsureServerWriterPolicy(downloadsRoot);
        EnsureNoUnresolvedActivationIntent(downloadsRoot);
        ReleaseShelfSnapshot activeShelf = new ReleaseShelfGenerationStore(_configuration).Capture();
        string activeShelfRoot = activeShelf.PhysicalRoot;
        string liveCanonicalManifestPath = Path.Combine(activeShelfRoot, CanonicalManifestName);
        JsonObject? existingCanonicalManifest = File.Exists(liveCanonicalManifestPath)
            ? LoadJsonObject(liveCanonicalManifestPath)
            : null;

        ValidateNoDesktopInstallTupleRegression(existingCanonicalManifest, incomingCanonicalManifest);
        DateTimeOffset activatedAt = _timeProvider.GetUtcNow().ToUniversalTime();
        string generationId = NewGenerationId(activatedAt);
        string activationReceiptId = $"activation-{Guid.NewGuid():N}";
        string transactionRoot = Path.Combine(downloadsRoot, $".release-promotion-transaction-{Guid.NewGuid():N}");
        string stagedRoot = Path.Combine(transactionRoot, "generation");
        string generationsRoot = Path.Combine(downloadsRoot, GenerationsDirectoryName);
        string generationRoot = Path.Combine(generationsRoot, generationId);
        string? pointerTempPath = null;
        bool pointerActivated = false;
        ReleaseActivationIntent? activationIntent = null;
        bool activationJournalPrepared = false;
        try
        {
            PrepareStagedShelf(
                stagedRoot,
                activeShelf,
                filesRoot,
                startupSmokeRoot,
                signingRoot,
                proofRoot,
                releaseEvidenceRoot,
                aurPackagesPath,
                incomingCompatibilityManifest,
                incomingCompatibilityManifestObject,
                incomingCanonicalManifest,
                generationId,
                cancellationToken);

            ValidatePreparedArtifactDeliveryContracts(stagedRoot, generationId);

            string stagedCompatibilityManifestPath = Path.Combine(stagedRoot, CompatibilityManifestName);
            string stagedCanonicalManifestPath = Path.Combine(stagedRoot, CanonicalManifestName);
            string compatibilityManifestSha256 = Sha256For(stagedCompatibilityManifestPath);
            string canonicalManifestSha256 = Sha256For(stagedCanonicalManifestPath);
            PublicReleaseManifestDto publicShelfManifest = ValidatePublicShelfCoherence(
                stagedRoot,
                stagedCompatibilityManifestPath,
                stagedCanonicalManifestPath,
                promotedArtifactIds,
                generationId,
                compatibilityManifestSha256,
                canonicalManifestSha256);
            IReadOnlyList<ActivationInventoryEntry> inventory = BuildActivationInventory(stagedRoot);
            string inventoryDigest = ComputeInventoryDigest(inventory);
            WriteJsonFile(
                Path.Combine(stagedRoot, ActivationCandidateName),
                new ActivationCandidateDocument(
                    ActivationCandidateSchema,
                    generationId,
                    publicShelfManifest.Version,
                    publicShelfManifest.Channel,
                    FormatTimestamp(publicShelfManifest.PublishedAt),
                    BuildManifestBindings(generationId, stagedRoot),
                    $"sha256:{inventoryDigest}",
                    inventory));

            CurrentPointerDocument pointer = BuildCurrentPointer(
                generationId,
                activationReceiptId,
                activatedAt,
                incomingCompatibilityManifest,
                stagedRoot,
                inventoryDigest);
            ValidatePreparedGeneration(stagedRoot, pointer, inventory, promotedArtifactIds);
            FlushTreeDurably(stagedRoot);
            NotifyCheckpoint(PromotionCheckpoint.StagedShelfValidated);
            cancellationToken.ThrowIfCancellationRequested();

            string baseUrl = ResolvePublicBaseUrl();
            ReleaseBundlePromotionResult result = new(
                Version: incomingCompatibilityManifest.Version,
                Channel: incomingCompatibilityManifest.Channel,
                PublishedAt: incomingCompatibilityManifest.PublishedAt,
                PromotedArtifactIds: promotedArtifactIds,
                DownloadsUrl: $"{baseUrl}/downloads/",
                InstallDispatchUrls: promotedArtifactIds
                    .Select(id => incomingCompatibilityManifest.Downloads.First(artifact =>
                        string.Equals(artifact.Id, id, StringComparison.OrdinalIgnoreCase)))
                    .Select(artifact => BuildGenerationArtifactUrl(baseUrl, generationId, artifact))
                    .ToArray(),
                DirectFileUrls: incomingCompatibilityManifest.Downloads
                    .Where(download => promotedArtifactIds.Contains(download.Id, StringComparer.OrdinalIgnoreCase))
                    .Select(download => BuildGenerationArtifactUrl(baseUrl, generationId, download))
                    .ToArray(),
                GenerationId: generationId,
                ActivationReceiptId: activationReceiptId,
                ActivatedAt: activatedAt,
                InventoryDigest: $"sha256:{inventoryDigest}",
                CanonicalManifestSha256: $"sha256:{canonicalManifestSha256}",
                CompatibilityManifestSha256: $"sha256:{compatibilityManifestSha256}");

            pointerTempPath = PrepareCurrentPointerFile(downloadsRoot, pointer);
            activationIntent = BuildActivationIntent(
                "promotion",
                activeShelf,
                result,
                pointerTempPath);
            if (recordActivationIntent is not null)
            {
                recordActivationIntent(activationIntent);
                NotifyCheckpoint(PromotionCheckpoint.ActivationIntentRecorded);
            }

            PrepareActivationIntentDurably(downloadsRoot, activationIntent, pointerTempPath);
            activationJournalPrepared = true;

            Directory.CreateDirectory(generationsRoot);
            if (Directory.Exists(generationRoot) || File.Exists(generationRoot))
            {
                throw new InvalidOperationException($"release shelf generation ID has already been used: {generationId}");
            }

            Directory.Move(stagedRoot, generationRoot);
            MakeGenerationReadOnly(generationRoot);
            FlushDirectoryDurably(generationsRoot);
            NotifyCheckpoint(PromotionCheckpoint.GenerationDirectoryDurable);
            NotifyCheckpoint(PromotionCheckpoint.GenerationPrepared);
            cancellationToken.ThrowIfCancellationRequested();
            NotifyCheckpoint(PromotionCheckpoint.PointerPrepared);
            cancellationToken.ThrowIfCancellationRequested();

            ActivateCurrentPointer(pointerTempPath, Path.Combine(downloadsRoot, CurrentPointerName));
            pointerTempPath = null;
            pointerActivated = true;

            ConfirmActivationDirectoryDurability(downloadsRoot, activationIntent);
            if (recordActivationIntent is null)
            {
                try
                {
                    AcknowledgeActivationCompletionUnderLock(downloadsRoot, activationIntent);
                }
                catch (Exception ex)
                {
                    throw new ReleaseActivationOutcomeUnknownException(activationIntent, ex);
                }
            }

            if (activeShelf.IsLegacy)
            {
                TryCreateLayoutMarkerAfterActivation(downloadsRoot);
            }
            NotifyPostActivationCheckpoint(PromotionCheckpoint.PointerActivated);
            TryUpdateCompatibilityMirrors(generationRoot, downloadsRoot);
            NotifyPostActivationCheckpoint(PromotionCheckpoint.CompatibilityMirrorsUpdated);
            return Task.FromResult(result);
        }
        catch (Exception ex)
        {
            if (ex is ReleaseActivationProcessTerminationSimulationException)
            {
                throw;
            }

            if (!pointerActivated
                && activationIntent is not null
                && ex is ReleaseActivationAbortedException alreadyAborted
                && alreadyAborted.Intent == activationIntent)
            {
                try
                {
                    RemoveNeverActivatedGenerationDurably(
                        downloadsRoot,
                        activationIntent,
                        requireAbortedHistory: true);
                }
                catch (Exception cleanup)
                {
                    throw new ReleaseActivationOutcomeUnknownException(
                        activationIntent,
                        new AggregateException(ex, cleanup));
                }

                throw;
            }

            if (!pointerActivated && activationJournalPrepared && activationIntent is not null)
            {
                try
                {
                    AbortPreparedActivationIntent(downloadsRoot, activationIntent);
                    RemoveNeverActivatedGenerationDurably(
                        downloadsRoot,
                        activationIntent,
                        requireAbortedHistory: true);
                }
                catch (Exception recovery)
                {
                    throw new ReleaseActivationOutcomeUnknownException(
                        activationIntent,
                        new AggregateException(ex, recovery));
                }

                throw new ReleaseActivationAbortedException(activationIntent, ex);
            }

            throw;
        }
        finally
        {
            if (!string.IsNullOrWhiteSpace(pointerTempPath))
            {
                TryDeleteFile(pointerTempPath);
            }

            TryDeletePromotionTransaction(transactionRoot);
        }
    }

    private PreparedReleaseBundle PrepareBundle(string bundleRoot)
    {
        string compatibilityManifestPath = RequireSingleFile(bundleRoot, CompatibilityManifestName);
        string canonicalManifestPath = RequireSingleFile(bundleRoot, CanonicalManifestName);
        string filesRoot = RequireSiblingDirectory(compatibilityManifestPath, "files");
        string? startupSmokeRoot = ResolveSiblingDirectory(compatibilityManifestPath, "startup-smoke");
        string? signingRoot = ResolveSiblingDirectory(compatibilityManifestPath, "signing");
        string? proofRoot = ResolveSiblingDirectory(compatibilityManifestPath, "proof");
        string? releaseEvidenceRoot = ResolveSiblingDirectory(compatibilityManifestPath, "release-evidence");
        string? aurPackagesPath = ResolveOptionalFile(bundleRoot, "aur-packages.json");
        string? promotionEvidencePath = ResolveOptionalFile(bundleRoot, PromotionEvidenceRelativePath);

        byte[] incomingCompatibilityBytes = ReadManifestBytes(
            compatibilityManifestPath,
            CompatibilityManifestName);
        byte[] incomingCanonicalBytes = ReadManifestBytes(
            canonicalManifestPath,
            CanonicalManifestName);
        JsonObject incomingCompatibilityManifestObject = LoadJsonObject(
            incomingCompatibilityBytes,
            compatibilityManifestPath);
        PublicReleaseManifestDto incomingCompatibilityManifest = LoadCompatibilityManifest(
            incomingCompatibilityBytes,
            compatibilityManifestPath);
        JsonObject incomingCanonicalManifest = LoadJsonObject(
            incomingCanonicalBytes,
            canonicalManifestPath);
        ValidateIncomingManifestIdentity(
            incomingCompatibilityManifestObject,
            incomingCompatibilityManifest,
            incomingCanonicalManifest,
            allowReviewRequiredProof: true);
        ValidatePassedReleaseProofPublicationWindow(incomingCompatibilityManifest);

        IReadOnlyList<CanonicalArtifactRecord> incomingCanonicalArtifacts = LoadCanonicalArtifacts(incomingCanonicalManifest);
        ValidateRegistryAuthoredManifestPair(
            incomingCompatibilityManifestObject,
            incomingCanonicalManifest,
            incomingCompatibilityManifest,
            incomingCanonicalArtifacts);
        ValidateIncomingBundle(
            incomingCompatibilityManifest,
            incomingCanonicalArtifacts,
            filesRoot,
            startupSmokeRoot,
            promotionEvidencePath,
            _timeProvider.GetUtcNow());
        ReleaseBuildProvenanceValidator.Validate(incomingCanonicalManifest, filesRoot, proofRoot);

        IReadOnlyList<string> promotedArtifactIds = incomingCompatibilityManifest.Downloads
            .Select(static artifact => artifact.Id)
            .Where(static id => !string.IsNullOrWhiteSpace(id))
            .ToArray();

        return new PreparedReleaseBundle(
            incomingCompatibilityManifest,
            incomingCompatibilityManifestObject,
            incomingCanonicalManifest,
            filesRoot,
            startupSmokeRoot,
            signingRoot,
            proofRoot,
            releaseEvidenceRoot,
            aurPackagesPath,
            promotedArtifactIds);
    }

    private sealed record PreparedReleaseBundle(
        PublicReleaseManifestDto CompatibilityManifest,
        JsonObject CompatibilityManifestObject,
        JsonObject CanonicalManifest,
        string FilesRoot,
        string? StartupSmokeRoot,
        string? SigningRoot,
        string? ProofRoot,
        string? ReleaseEvidenceRoot,
        string? AurPackagesPath,
        IReadOnlyList<string> PromotedArtifactIds);

    private string ResolveDownloadsRoot()
        => _configuration[DownloadsRootKey]?.Trim() is { Length: > 0 } configured
            ? configured
            : DefaultDownloadsRoot;

    private string ResolvePublicBaseUrl()
    {
        string? configured = _configuration[PublicBaseUrlKey]?.Trim();
        if (Uri.TryCreate(configured, UriKind.Absolute, out Uri? redirectUri))
        {
            return $"{redirectUri.Scheme}://{redirectUri.Authority}";
        }

        return "https://chummer.run";
    }

    private static void EnsureDownloadsRootWritable(string downloadsRoot)
    {
        Directory.CreateDirectory(downloadsRoot);
        string probePath = Path.Combine(downloadsRoot, $".release-promotion-write-probe-{Guid.NewGuid():N}");
        try
        {
            File.WriteAllText(probePath, "ok");
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            throw new InvalidOperationException($"downloads root is not writable: {downloadsRoot}", ex);
        }
        finally
        {
            if (File.Exists(probePath))
            {
                File.Delete(probePath);
            }
        }
    }

    private static FileStream AcquirePromotionLock(string downloadsRoot)
    {
        string lockPath = Path.Combine(downloadsRoot, PromotionLockName);
        try
        {
            var options = new FileStreamOptions
            {
                Mode = FileMode.OpenOrCreate,
                Access = FileAccess.ReadWrite,
                Share = FileShare.None
            };
            if (!OperatingSystem.IsWindows())
            {
                options.UnixCreateMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;
            }

            FileStream promotionLock = new(lockPath, options);
            try
            {
                if (!OperatingSystem.IsWindows())
                {
                    File.SetUnixFileMode(lockPath, UnixFileMode.UserRead | UnixFileMode.UserWrite);
                }

                return promotionLock;
            }
            catch
            {
                promotionLock.Dispose();
                throw;
            }
        }
        catch (IOException ex)
        {
            throw new InvalidOperationException("another release bundle promotion is already in progress.", ex);
        }
    }

    private static void EnsureServerWriterPolicy(string downloadsRoot)
    {
        string path = Path.Combine(downloadsRoot, WriterPolicyName);
        if (!File.Exists(path))
        {
            WriteOwnerOnlyJsonAtomicallyDurable(
                path,
                new ReleaseShelfWriterPolicyDocument(WriterPolicySchema, WriterPolicyMode),
                overwrite: false);
            return;
        }

        ValidateServerWriterPolicy(path);
    }

    private static void ValidateServerWriterPolicy(string path)
    {
        EnsureOwnerOnlyRegularFile(path, "release shelf writer policy");
        JsonObject json = LoadStrictJsonObject(path);
        RequireExactProperties(json, ["schemaVersion", "mode"], "release shelf writer policy");
        ReleaseShelfWriterPolicyDocument policy = json.Deserialize<ReleaseShelfWriterPolicyDocument>(JsonOptions)
            ?? throw new InvalidDataException("release shelf writer policy is malformed.");
        if (!string.Equals(policy.SchemaVersion, WriterPolicySchema, StringComparison.Ordinal)
            || !string.Equals(policy.Mode, WriterPolicyMode, StringComparison.Ordinal))
        {
            throw new InvalidDataException("release shelf writer policy is unsupported or noncanonical.");
        }
    }

    private static void PrepareStagedShelf(
        string stagedRoot,
        ReleaseShelfSnapshot activeShelf,
        string filesRoot,
        string? startupSmokeRoot,
        string? signingRoot,
        string? proofRoot,
        string? releaseEvidenceRoot,
        string? aurPackagesPath,
        PublicReleaseManifestDto compatibilityManifest,
        JsonObject compatibilityManifestObject,
        JsonObject canonicalManifest,
        string generationId,
        CancellationToken cancellationToken)
    {
        string activeShelfRoot = activeShelf.PhysicalRoot;
        string stagedFilesRoot = Path.Combine(stagedRoot, "files");
        string stagedStartupSmokeRoot = Path.Combine(stagedRoot, "startup-smoke");
        string stagedSigningRoot = Path.Combine(stagedRoot, "signing");
        string stagedProofRoot = Path.Combine(stagedRoot, "proof");
        Directory.CreateDirectory(stagedFilesRoot);
        Directory.CreateDirectory(stagedStartupSmokeRoot);
        Directory.CreateDirectory(stagedSigningRoot);
        Directory.CreateDirectory(stagedProofRoot);

        CopyDirectoryContents(filesRoot, stagedFilesRoot, cancellationToken);
        RejectCaseCollidingPaths(stagedFilesRoot, "release artifact shelf");
        PruneUnreferencedArtifactFiles(stagedFilesRoot, compatibilityManifest);
        ValidateFilesAreManifestBound(stagedFilesRoot, compatibilityManifest);

        if (!string.IsNullOrWhiteSpace(startupSmokeRoot) && Directory.Exists(startupSmokeRoot))
        {
            CopyDirectoryContents(startupSmokeRoot, stagedStartupSmokeRoot, cancellationToken);
        }

        if (!string.IsNullOrWhiteSpace(signingRoot) && Directory.Exists(signingRoot))
        {
            CopyDirectoryContents(signingRoot, stagedSigningRoot, cancellationToken);
            RejectCaseCollidingPaths(stagedSigningRoot, "release signing receipt shelf");
        }

        if (!string.IsNullOrWhiteSpace(proofRoot) && Directory.Exists(proofRoot))
        {
            CopyDirectoryContents(proofRoot, stagedProofRoot, cancellationToken);
        }

        string stagedReleaseEvidenceRoot = Path.Combine(stagedRoot, "release-evidence");
        if (!string.IsNullOrWhiteSpace(releaseEvidenceRoot) && Directory.Exists(releaseEvidenceRoot))
        {
            CopyDirectoryContents(
                releaseEvidenceRoot,
                stagedReleaseEvidenceRoot,
                cancellationToken);
        }

        string activeAurPackagesPath = Path.Combine(activeShelfRoot, "aur-packages.json");
        string stagedAurPackagesPath = Path.Combine(stagedRoot, "aur-packages.json");
        if (!string.IsNullOrWhiteSpace(aurPackagesPath) && File.Exists(aurPackagesPath))
        {
            File.Copy(aurPackagesPath, stagedAurPackagesPath);
        }
        else if (File.Exists(activeAurPackagesPath))
        {
            File.Copy(activeAurPackagesPath, stagedAurPackagesPath);
        }

        RewritePayloadSidecarsForGeneration(
            stagedFilesRoot,
            compatibilityManifest,
            generationId);

        byte[] projectedCompatibilityBytes = ProjectRegistryManifestForGeneration(
            compatibilityManifestObject,
            generationId,
            compatibilityManifest);
        byte[] projectedCanonicalBytes = ProjectRegistryManifestForGeneration(
            canonicalManifest,
            generationId,
            compatibilityManifest);

        cancellationToken.ThrowIfCancellationRequested();
        File.WriteAllBytes(
            Path.Combine(stagedRoot, CompatibilityManifestName),
            projectedCompatibilityBytes);
        cancellationToken.ThrowIfCancellationRequested();
        File.WriteAllBytes(
            Path.Combine(stagedRoot, CanonicalManifestName),
            projectedCanonicalBytes);
        cancellationToken.ThrowIfCancellationRequested();
    }

    private static void RewritePayloadSidecarsForGeneration(
        string filesRoot,
        PublicReleaseManifestDto compatibilityManifest,
        string generationId)
    {
        foreach (PublicReleaseArtifactDto artifact in compatibilityManifest.Downloads)
        {
            if (string.IsNullOrWhiteSpace(artifact.PayloadFileName))
            {
                continue;
            }

            string artifactId = RequireArtifactToken(artifact.Id, "compatibility artifact id");
            string payloadFileName = RequirePortableArtifactFileName(
                artifact.PayloadFileName,
                artifactId,
                "compatibility payloadFileName");
            string installerFileName = RequirePortableArtifactFileName(
                artifact.FileName,
                artifactId,
                "compatibility fileName");
            string payloadSha256 = RequireArtifactSha256(
                artifact.PayloadSha256,
                artifactId,
                "compatibility payload");
            long payloadSizeBytes = RequireArtifactSize(
                artifact.PayloadSizeBytes,
                artifactId,
                "compatibility payload");
            string immutablePayloadUrl =
                $"/downloads/g/{generationId}/install/{Uri.EscapeDataString(artifactId)}/payload";
            string sidecarPath = Path.Combine(filesRoot, payloadFileName + ".json");
            if (!File.Exists(sidecarPath))
            {
                throw new InvalidDataException(
                    $"prepared generation is missing payload metadata for {artifactId}.");
            }

            EnsureRegularFile(sidecarPath, $"prepared payload metadata for {artifactId}");
            var sidecarInfo = new FileInfo(sidecarPath);
            if (sidecarInfo.Length <= 0 || sidecarInfo.Length > 64 * 1024)
            {
                throw new InvalidDataException(
                    $"prepared payload metadata size is invalid for {artifactId}.");
            }

            byte[] existingSidecar = File.ReadAllBytes(sidecarPath);
            if (!PayloadSidecarContractValidator.TryValidate(
                    existingSidecar,
                    installerFileName,
                    payloadFileName,
                    artifact.PayloadDownloadUrl,
                    payloadSha256,
                    payloadSizeBytes,
                    compatibilityManifest.Version,
                    allowMutableIncomingUrl: true,
                    out string? failure))
            {
                throw new InvalidDataException(
                    $"prepared payload metadata contract is invalid for {artifactId}: {failure}");
            }

            var normalizedSidecar = new JsonObject
            {
                ["contractName"] = "chummer6-ui.windows_bootstrap_payload",
                ["fileName"] = payloadFileName,
                ["downloadUrl"] = immutablePayloadUrl,
                ["sha256"] = payloadSha256,
                ["sizeBytes"] = payloadSizeBytes,
                ["installerFileName"] = installerFileName,
                ["releaseVersion"] = compatibilityManifest.Version
            };
            WriteJsonFile(
                sidecarPath,
                normalizedSidecar);
        }
    }

    private static void ValidatePreparedArtifactDeliveryContracts(
        string stagedRoot,
        string generationId)
    {
        string compatibilityPath = Path.Combine(stagedRoot, CompatibilityManifestName);
        PublicReleaseManifestDto manifest = LoadCompatibilityManifest(compatibilityPath);
        IReadOnlyList<CanonicalArtifactRecord> canonicalArtifacts = LoadCanonicalArtifacts(
            LoadJsonObject(Path.Combine(stagedRoot, CanonicalManifestName)));
        Dictionary<string, PublicReleaseArtifactDto> compatibilityById =
            BuildUniqueCompatibilityArtifacts(manifest.Downloads);
        Dictionary<string, CanonicalArtifactRecord> canonicalById =
            BuildUniqueCanonicalArtifacts(canonicalArtifacts);
        if (compatibilityById.Count != canonicalById.Count
            || compatibilityById.Keys.Any(artifactId => !canonicalById.ContainsKey(artifactId)))
        {
            throw new InvalidDataException(
                "prepared generation manifests publish different artifact id sets.");
        }

        foreach ((string artifactId, CanonicalArtifactRecord canonicalArtifact) in canonicalById)
        {
            NormalizedArtifactContract canonicalContract = NormalizeCanonicalArtifactContract(
                canonicalArtifact,
                requireIncomingUrls: false);
            NormalizedArtifactContract compatibilityContract = NormalizeCompatibilityArtifactContract(
                compatibilityById[artifactId],
                requireIncomingUrls: false);
            if (canonicalContract != compatibilityContract)
            {
                throw new InvalidDataException(
                    $"prepared generation manifests disagree about delivery/security contract for artifact {artifactId}.");
            }
        }

        string filesRoot = Path.Combine(stagedRoot, "files");
        foreach (PublicReleaseArtifactDto artifact in manifest.Downloads)
        {
            string artifactId = RequireArtifactToken(artifact.Id, "prepared artifact id");
            string fileName = RequirePortableArtifactFileName(
                artifact.FileName,
                artifactId,
                "prepared fileName");
            string sha256 = RequireArtifactSha256(artifact.Sha256, artifactId, "prepared artifact");
            long sizeBytes = RequireArtifactSize(artifact.SizeBytes, artifactId, "prepared artifact");
            ValidateBoundFileBytes(filesRoot, fileName, sha256, sizeBytes, artifactId, "artifact");

            if (string.IsNullOrWhiteSpace(artifact.PayloadFileName))
            {
                if (!string.IsNullOrWhiteSpace(artifact.PayloadDownloadUrl)
                    || !string.IsNullOrWhiteSpace(artifact.PayloadSha256)
                    || artifact.PayloadSizeBytes is not null)
                {
                    throw new InvalidDataException(
                        $"prepared payload contract is partial for {artifactId}.");
                }

                continue;
            }

            string payloadFileName = RequirePortableArtifactFileName(
                artifact.PayloadFileName,
                artifactId,
                "prepared payloadFileName");
            string payloadSha256 = RequireArtifactSha256(
                artifact.PayloadSha256,
                artifactId,
                "prepared payload");
            long payloadSizeBytes = RequireArtifactSize(
                artifact.PayloadSizeBytes,
                artifactId,
                "prepared payload");
            ValidateBoundFileBytes(
                filesRoot,
                payloadFileName,
                payloadSha256,
                payloadSizeBytes,
                artifactId,
                "payload");

            ValidatePayloadSidecar(
                filesRoot,
                artifactId,
                fileName,
                payloadFileName,
                $"/downloads/g/{generationId}/install/{Uri.EscapeDataString(artifactId)}/payload",
                payloadSha256,
                payloadSizeBytes,
                manifest.Version,
                allowMutableIncomingUrl: false);
        }
    }

    private static void PruneUnreferencedArtifactFiles(
        string filesRoot,
        PublicReleaseManifestDto compatibilityManifest)
    {
        HashSet<string> retained = BuildManifestBoundArtifactPaths(compatibilityManifest);
        foreach (string path in EnumerateRegularFilesWithoutLinks(filesRoot).ToArray())
        {
            string relativePath = Path.GetRelativePath(filesRoot, path)
                .Replace(Path.DirectorySeparatorChar, '/');
            if (!retained.Contains(relativePath))
            {
                File.Delete(path);
            }
        }

        foreach (string directory in Directory.EnumerateDirectories(filesRoot, "*", SearchOption.AllDirectories)
                     .OrderByDescending(static path => path.Length))
        {
            if (!Directory.EnumerateFileSystemEntries(directory).Any())
            {
                Directory.Delete(directory);
            }
        }
    }

    private static void ValidateFilesAreManifestBound(
        string filesRoot,
        PublicReleaseManifestDto compatibilityManifest)
    {
        RejectCaseCollidingPaths(filesRoot, "release bundle files");
        HashSet<string> retained = BuildManifestBoundArtifactPaths(compatibilityManifest);
        foreach (string path in EnumerateRegularFilesWithoutLinks(filesRoot))
        {
            string relativePath = Path.GetRelativePath(filesRoot, path)
                .Replace(Path.DirectorySeparatorChar, '/');
            if (!retained.Contains(relativePath))
            {
                throw new InvalidDataException(
                    $"release bundle file '{relativePath}' is not bound by the compatibility manifest.");
            }
        }
    }

    private static HashSet<string> BuildManifestBoundArtifactPaths(
        PublicReleaseManifestDto compatibilityManifest)
    {
        var retained = new HashSet<string>(StringComparer.Ordinal);
        foreach (PublicReleaseArtifactDto artifact in compatibilityManifest.Downloads)
        {
            retained.Add(ResolveDownloadFileName(artifact));
            if (string.IsNullOrWhiteSpace(artifact.PayloadFileName))
            {
                continue;
            }

            string payloadFileName = Path.GetFileName(artifact.PayloadFileName.Trim());
            retained.Add(payloadFileName);
            retained.Add(payloadFileName + ".json");
        }

        return retained;
    }

    private static void RejectCaseCollidingPaths(string root, string description)
    {
        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (string path in EnumerateRegularFilesWithoutLinks(root))
        {
            string relativePath = Path.GetRelativePath(root, path)
                .Replace(Path.DirectorySeparatorChar, '/');
            ValidatePortableInventoryPath(relativePath, description);
            if (!paths.Add(relativePath))
            {
                throw new InvalidDataException(
                    $"{description} contains a case-colliding path '{relativePath}'.");
            }
        }
    }

    private static void ValidatePortableInventoryPath(string relativePath, string description)
    {
        string[] segments = relativePath.Split('/', StringSplitOptions.None);
        if (segments.Length == 0 || segments.Any(static segment =>
                segment.Length is < 1 or > 255
                || !IsAsciiAlphaNumeric(segment[0])
                || segment.Skip(1).Any(static character =>
                    !IsAsciiAlphaNumeric(character)
                    && character is not '.' and not '_' and not '+' and not '-')))
        {
            throw new InvalidDataException(
                $"{description} contains a non-portable inventory path '{relativePath}'.");
        }
    }

    private static bool IsAsciiAlphaNumeric(char character)
        => character is >= 'A' and <= 'Z'
            or >= 'a' and <= 'z'
            or >= '0' and <= '9';

    /// <summary>
    /// Materializes the Registry-owned layout-v1 generation projection. The
    /// incoming Registry document remains the truth source; this deterministic
    /// projection only binds that truth to one immutable generation identity and
    /// its access-class-aware delivery paths. Python/object-storage publishers
    /// implement and golden-test the same canonical byte contract.
    /// </summary>
    internal static byte[] ProjectRegistryManifestForGeneration(
        JsonObject registryManifest,
        string generationId,
        PublicReleaseManifestDto compatibilityManifest)
    {
        ArgumentNullException.ThrowIfNull(registryManifest);
        ArgumentNullException.ThrowIfNull(compatibilityManifest);
        if (!IsSafeGenerationId(generationId))
        {
            throw new InvalidDataException(
                "release shelf generationId is not a traversal-safe opaque token.");
        }

        Dictionary<string, GenerationArtifactRoute> artifactRoutes = compatibilityManifest.Downloads
            .Where(static artifact => !string.IsNullOrWhiteSpace(artifact.Id))
            .Select(artifact => new GenerationArtifactRoute(
                RequireArtifactToken(artifact.Id, "compatibility artifact id"),
                RequirePortableArtifactFileName(
                    artifact.FileName,
                    artifact.Id,
                    "compatibility fileName"),
                string.IsNullOrWhiteSpace(artifact.PayloadFileName)
                    ? null
                    : RequirePortableArtifactFileName(
                        artifact.PayloadFileName,
                        artifact.Id,
                        "compatibility payloadFileName"),
                string.Equals(
                    artifact.InstallAccessClass?.Trim(),
                    "open_public",
                    StringComparison.OrdinalIgnoreCase)))
            .ToDictionary(
                static route => route.ArtifactId,
                static route => route,
                StringComparer.OrdinalIgnoreCase);

        JsonObject projected = (JsonObject)registryManifest.DeepClone();
        RejectProofRouteLookalikes(projected);
        ValidateRegistryProjectionSourceRoutes(
            projected,
            generationId,
            artifactRoutes);
        projected["generationId"] = generationId;
        ProjectArtifactDownloadRoutes(projected, artifactRoutes);
        NormalizeManifestForGeneration(projected, generationId, artifactRoutes);
        JsonNode canonical = CanonicalizeManifestNode(projected);
        byte[] body = JsonSerializer.SerializeToUtf8Bytes(
            canonical,
            CanonicalManifestJsonOptions);
        byte[] terminated = new byte[body.Length + 1];
        body.CopyTo(terminated, 0);
        terminated[^1] = (byte)'\n';
        return terminated;
    }

    private static void ValidateRegistryProjectionSourceRoutes(
        JsonObject manifest,
        string generationId,
        IReadOnlyDictionary<string, GenerationArtifactRoute> artifactRoutes)
    {
        JsonNode? canonicalProofRoutes = manifest["releaseProof"]?["proofRoutes"] is JsonArray routes
            ? routes
            : null;
        foreach (string value in EnumerateGenerationBoundStrings(manifest, canonicalProofRoutes))
        {
            _ = RewriteReleaseUrl(value, generationId, artifactRoutes);
        }
    }

    private static void ProjectArtifactDownloadRoutes(
        JsonObject manifest,
        IReadOnlyDictionary<string, GenerationArtifactRoute> artifactRoutes)
    {
        foreach (string collectionName in new[] { "artifacts", "downloads" })
        {
            if (manifest[collectionName] is not JsonArray rows)
            {
                continue;
            }

            foreach (JsonObject row in rows.OfType<JsonObject>())
            {
                string? artifactId = GetJsonString(row["artifactId"])
                                     ?? GetJsonString(row["id"]);
                if (string.IsNullOrWhiteSpace(artifactId)
                    || !artifactRoutes.TryGetValue(
                        artifactId.Trim(),
                        out GenerationArtifactRoute? route))
                {
                    continue;
                }

                string primary = route.IsOpenPublic
                    ? $"/downloads/g/{GetJsonString(manifest["generationId"])}/files/{route.FileName}"
                    : $"/downloads/g/{GetJsonString(manifest["generationId"])}/install/{route.ArtifactId}";
                if (row.ContainsKey("downloadUrl"))
                {
                    row["downloadUrl"] = primary;
                }

                if (row.ContainsKey("url"))
                {
                    row["url"] = primary;
                }

                if (row.ContainsKey("payloadDownloadUrl")
                    && !string.IsNullOrWhiteSpace(route.PayloadFileName))
                {
                    row["payloadDownloadUrl"] =
                        $"/downloads/g/{GetJsonString(manifest["generationId"])}/install/{route.ArtifactId}/payload";
                }
            }
        }
    }

    private static JsonNode CanonicalizeManifestNode(JsonNode node)
    {
        if (node is JsonObject jsonObject)
        {
            var canonical = new JsonObject();
            foreach ((string key, JsonNode? value) in jsonObject
                         .OrderBy(static property => property.Key, StringComparer.Ordinal))
            {
                canonical[key] = value is null
                    ? null
                    : CanonicalizeManifestNode(value);
            }

            return canonical;
        }

        if (node is JsonArray jsonArray)
        {
            var canonical = new JsonArray();
            foreach (JsonNode? value in jsonArray)
            {
                canonical.Add(value is null
                    ? null
                    : CanonicalizeManifestNode(value));
            }

            return canonical;
        }

        return node.DeepClone();
    }

    private static void RejectProofRouteLookalikes(JsonObject root)
    {
        static void Visit(JsonNode node, IReadOnlyList<string> path)
        {
            if (node is JsonObject jsonObject)
            {
                foreach ((string key, JsonNode? child) in jsonObject)
                {
                    bool isNestedReleaseProofLookalike = path.Count > 1
                                                        && string.Equals(
                                                            path[^1],
                                                            "releaseProof",
                                                            StringComparison.Ordinal)
                                                        && string.Equals(
                                                            key,
                                                            "proofRoutes",
                                                            StringComparison.Ordinal);
                    if (string.Equals(key, "proof_routes", StringComparison.Ordinal)
                        || isNestedReleaseProofLookalike)
                    {
                        throw new InvalidDataException(
                            "Registry generation projection rejects nested releaseProof.proofRoutes lookalikes and noncanonical aliases.");
                    }

                    if (child is not null)
                    {
                        Visit(child, path.Append(key).ToArray());
                    }
                }

                return;
            }

            if (node is JsonArray jsonArray)
            {
                foreach (JsonNode? child in jsonArray)
                {
                    if (child is not null)
                    {
                        Visit(child, path.Append("[]").ToArray());
                    }
                }
            }
        }

        Visit(root, Array.Empty<string>());
    }

    private static void NormalizeManifestForGeneration(
        JsonObject manifest,
        string generationId,
        IReadOnlyDictionary<string, GenerationArtifactRoute> artifactRoutes)
    {
        manifest["generationId"] = generationId;
        JsonNode? proofRoutesCandidate =
            (manifest["releaseProof"] as JsonObject)?["proofRoutes"];
        JsonNode? canonicalProofRoutes = proofRoutesCandidate is JsonArray
            ? proofRoutesCandidate
            : null;
        NormalizeManifestNode(
            manifest,
            generationId,
            artifactRoutes,
            canonicalProofRoutes);
        ValidateGenerationBoundManifestRoutes(manifest, generationId);
    }

    private static void NormalizeManifestNode(
        JsonNode node,
        string generationId,
        IReadOnlyDictionary<string, GenerationArtifactRoute> artifactRoutes,
        JsonNode? canonicalProofRoutes)
    {
        if (node is JsonObject jsonObject)
        {
            foreach (string key in jsonObject.Select(static property => property.Key).ToArray())
            {
                JsonNode? child = jsonObject[key];
                // Only the exact top-level releaseProof.proofRoutes node is immutable
                // Registry evidence describing the canonical route contract that was
                // exercised. Node identity deliberately prevents a nested object named
                // releaseProof from inheriting this exemption.
                if (ReferenceEquals(child, canonicalProofRoutes))
                {
                    continue;
                }

                if (child is JsonValue value && value.TryGetValue(out string? text))
                {
                    string? rewritten = RewriteReleaseUrl(text, generationId, artifactRoutes);
                    if (rewritten is null)
                    {
                        jsonObject.Remove(key);
                    }
                    else
                    {
                        jsonObject[key] = rewritten;
                    }
                }
                else if (child is not null)
                {
                    NormalizeManifestNode(
                        child,
                        generationId,
                        artifactRoutes,
                        canonicalProofRoutes);
                }
            }

            return;
        }

        if (node is JsonArray jsonArray)
        {
            for (int index = jsonArray.Count - 1; index >= 0; index--)
            {
                JsonNode? child = jsonArray[index];
                if (child is JsonValue value && value.TryGetValue(out string? text))
                {
                    string? rewritten = RewriteReleaseUrl(text, generationId, artifactRoutes);
                    if (rewritten is null)
                    {
                        jsonArray.RemoveAt(index);
                    }
                    else
                    {
                        jsonArray[index] = rewritten;
                    }
                }
                else if (child is not null)
                {
                    NormalizeManifestNode(
                        child,
                        generationId,
                        artifactRoutes,
                        canonicalProofRoutes);
                }
            }
        }
    }

    private static string? RewriteReleaseUrl(
        string value,
        string generationId,
        IReadOnlyDictionary<string, GenerationArtifactRoute> artifactRoutes)
    {
        if (!TryGetReleasePath(value, out string path))
        {
            return value;
        }

        string generationPrefix = $"/downloads/g/{generationId}/";
        string relative;
        const string priorGenerationPrefix = "/downloads/g/";
        if (path.StartsWith(priorGenerationPrefix, StringComparison.Ordinal))
        {
            string remainder = path[priorGenerationPrefix.Length..];
            int separator = remainder.IndexOf('/');
            if (separator <= 0 || separator == remainder.Length - 1)
            {
                throw new InvalidDataException($"manifest contains a malformed generation-bound release URL: {value}");
            }

            relative = remainder[(separator + 1)..];
        }
        else
        {
            relative = path["/downloads/".Length..];
        }

        const string filesPrefix = "files/";
        if (relative.StartsWith(filesPrefix, StringComparison.Ordinal))
        {
            return BindFileRoute(relative[filesPrefix.Length..], generationPrefix, artifactRoutes);
        }

        foreach (string dispatchRoot in new[] { "install", "get", "file" })
        {
            string prefix = dispatchRoot + "/";
            if (relative.StartsWith(prefix, StringComparison.Ordinal))
            {
                return BindArtifactRoute(
                    relative[prefix.Length..],
                    generationPrefix,
                    artifactRoutes);
            }
        }

        if (string.Equals(relative, CanonicalManifestName, StringComparison.Ordinal)
            || string.Equals(relative, CompatibilityManifestName, StringComparison.Ordinal))
        {
            return generationPrefix + relative;
        }

        foreach (string routeRoot in new[] { "proof", "startup-smoke", "release-evidence" })
        {
            if (relative.StartsWith(routeRoot + "/", StringComparison.Ordinal))
            {
                return generationPrefix + relative;
            }
        }

        throw new InvalidDataException($"manifest retains a non-generation-bound release URL: {value}");
    }

    private static string? BindArtifactRoute(
        string artifactId,
        string generationPrefix,
        IReadOnlyDictionary<string, GenerationArtifactRoute> artifactRoutes)
    {
        string role = ArtifactDeliveryRoles.Primary;
        string normalizedArtifactId = artifactId;
        if (artifactId.EndsWith("/payload", StringComparison.Ordinal))
        {
            role = ArtifactDeliveryRoles.Payload;
            normalizedArtifactId = artifactId[..^"/payload".Length];
        }
        else if (artifactId.EndsWith("/metadata", StringComparison.Ordinal))
        {
            role = ArtifactDeliveryRoles.PayloadMetadata;
            normalizedArtifactId = artifactId[..^"/metadata".Length];
        }

        if (!artifactRoutes.TryGetValue(normalizedArtifactId, out GenerationArtifactRoute? route))
        {
            // Historic proof-route arrays include baseline installer journeys that
            // are not bytes in every release. They were validated as input proof,
            // but are not immutable generation objects and must not retain a mutable
            // current-shelf alias in the authoritative manifests.
            return null;
        }

        if (role != ArtifactDeliveryRoles.Primary)
        {
            if (string.IsNullOrWhiteSpace(route.PayloadFileName))
            {
                throw new InvalidDataException(
                    $"manifest role route references missing payload bytes for '{normalizedArtifactId}'.");
            }

            string suffix = role == ArtifactDeliveryRoles.Payload ? "payload" : "metadata";
            return generationPrefix + "install/" + Uri.EscapeDataString(route.ArtifactId) + "/" + suffix;
        }

        return route.IsOpenPublic
            ? generationPrefix + "files/" + Uri.EscapeDataString(route.FileName)
            : generationPrefix + "install/" + Uri.EscapeDataString(route.ArtifactId);
    }

    private static string BindFileRoute(
        string requestedFile,
        string generationPrefix,
        IReadOnlyDictionary<string, GenerationArtifactRoute> artifactRoutes)
    {
        string fileName = Path.GetFileName(requestedFile);
        if (string.IsNullOrWhiteSpace(fileName)
            || !string.Equals(fileName, requestedFile, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"manifest file URL has a noncanonical basename '{requestedFile}'.");
        }

        GenerationArtifactRoute[] matches = artifactRoutes.Values.Where(candidate =>
                string.Equals(candidate.FileName, fileName, StringComparison.Ordinal)
                || string.Equals(candidate.PayloadFileName, fileName, StringComparison.Ordinal)
                || (!string.IsNullOrWhiteSpace(candidate.PayloadFileName)
                    && string.Equals(candidate.PayloadFileName + ".json", fileName, StringComparison.Ordinal)))
            .ToArray();
        if (matches.Length != 1)
        {
            throw new InvalidDataException(
                $"manifest file URL references unknown or ambiguous artifact bytes '{fileName}'.");
        }

        GenerationArtifactRoute route = matches[0];
        if (string.Equals(route.PayloadFileName, fileName, StringComparison.Ordinal))
        {
            return generationPrefix + "install/" + Uri.EscapeDataString(route.ArtifactId) + "/payload";
        }

        if (!string.IsNullOrWhiteSpace(route.PayloadFileName)
            && string.Equals(route.PayloadFileName + ".json", fileName, StringComparison.Ordinal))
        {
            return generationPrefix + "install/" + Uri.EscapeDataString(route.ArtifactId) + "/metadata";
        }

        return route.IsOpenPublic
            ? generationPrefix + "files/" + Uri.EscapeDataString(fileName)
            : generationPrefix + "install/" + Uri.EscapeDataString(route.ArtifactId);
    }

    private static bool TryGetReleasePath(string value, out string path)
    {
        path = string.Empty;
        if (value.StartsWith("/downloads/", StringComparison.Ordinal))
        {
            if (value.Contains('?')
                || value.Contains('#')
                || value.Contains('\\')
                || value.Contains('%'))
            {
                throw new InvalidDataException(
                    $"release URL must be a canonical unencoded site path without query, fragment, or backslash: {value}");
            }

            path = value;
            return true;
        }

        if (Uri.TryCreate(value, UriKind.Absolute, out Uri? absolute)
            && absolute.AbsolutePath.StartsWith("/downloads/", StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"release URL must be a plain canonical site path, not an absolute URL: {value}");
        }

        if (value.StartsWith("//", StringComparison.Ordinal))
        {
            int pathStart = value.IndexOf('/', 2);
            if (pathStart >= 0
                && value[pathStart..].StartsWith("/downloads/", StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    $"release URL must be a plain canonical site path, not a scheme-relative URL: {value}");
            }
        }

        if (value.Contains('%'))
        {
            string decoded;
            try
            {
                decoded = Uri.UnescapeDataString(value);
            }
            catch (UriFormatException ex)
            {
                throw new InvalidDataException(
                    $"release URL contains malformed percent encoding: {value}",
                    ex);
            }

            if (decoded.StartsWith("/downloads/", StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    $"release URL cannot hide a download path behind percent encoding: {value}");
            }
        }

        return false;
    }

    private static void ValidateGenerationBoundManifestRoutes(JsonObject node, string generationId)
    {
        if (!string.Equals(
                GetJsonString(node["generationId"]),
                generationId,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "authoritative generation manifest must bind the active generationId.");
        }

        string expectedPrefix = $"/downloads/g/{generationId}/";
        JsonNode? proofRoutesCandidate = node["releaseProof"]?["proofRoutes"];
        JsonNode? canonicalProofRoutes = proofRoutesCandidate is JsonArray
            ? proofRoutesCandidate
            : null;
        foreach (string value in EnumerateGenerationBoundStrings(node, canonicalProofRoutes))
        {
            if (!TryGetReleasePath(value, out string path))
            {
                continue;
            }

            if (!path.StartsWith(expectedPrefix, StringComparison.Ordinal))
            {
                throw new InvalidDataException($"manifest retains a non-generation-bound release URL: {value}");
            }

            string relative = path[expectedPrefix.Length..];
            string[] parts = relative.Split('/', StringSplitOptions.None);
            if (parts.Length == 0
                || parts.Any(static part => string.IsNullOrEmpty(part) || part is "." or "..")
                || parts[0] is not CanonicalManifestName
                    and not CompatibilityManifestName
                    and not "files"
                    and not "install"
                    and not "proof"
                    and not "startup-smoke"
                    and not "release-evidence")
            {
                throw new InvalidDataException($"manifest contains an unsafe generation-bound release URL: {value}");
            }

            bool invalidShape = parts[0] switch
            {
                CanonicalManifestName or CompatibilityManifestName => parts.Length != 1,
                "files" => parts.Length != 2,
                "install" => parts.Length != 2
                             && (parts.Length != 3
                                 || parts[2] is not "payload" and not "metadata"),
                "proof" or "startup-smoke" or "release-evidence" => parts.Length < 2,
                _ => true
            };
            if (invalidShape)
            {
                throw new InvalidDataException(
                    $"manifest generation URL has a noncanonical route shape: {value}");
            }
        }
    }

    private static IEnumerable<string> EnumerateGenerationBoundStrings(
        JsonNode node,
        JsonNode? canonicalProofRoutes)
    {
        if (node is JsonValue value && value.TryGetValue(out string? text))
        {
            yield return text;
            yield break;
        }

        if (node is JsonObject jsonObject)
        {
            foreach ((_, JsonNode? child) in jsonObject)
            {
                if (child is null
                    || ReferenceEquals(child, canonicalProofRoutes))
                {
                    continue;
                }

                foreach (string nested in EnumerateGenerationBoundStrings(
                             child,
                             canonicalProofRoutes))
                {
                    yield return nested;
                }
            }

            yield break;
        }

        if (node is JsonArray jsonArray)
        {
            foreach (JsonNode? child in jsonArray)
            {
                if (child is null)
                {
                    continue;
                }

                foreach (string nested in EnumerateGenerationBoundStrings(
                             child,
                             canonicalProofRoutes))
                {
                    yield return nested;
                }
            }
        }
    }

    private static IEnumerable<string> EnumerateStrings(JsonNode node)
    {
        if (node is JsonValue value && value.TryGetValue(out string? text))
        {
            yield return text;
            yield break;
        }

        if (node is JsonObject jsonObject)
        {
            foreach ((_, JsonNode? child) in jsonObject)
            {
                if (child is not null)
                {
                    foreach (string nested in EnumerateStrings(child))
                    {
                        yield return nested;
                    }
                }
            }

            yield break;
        }

        if (node is JsonArray jsonArray)
        {
            foreach (JsonNode? child in jsonArray)
            {
                if (child is not null)
                {
                    foreach (string nested in EnumerateStrings(child))
                    {
                        yield return nested;
                    }
                }
            }
        }
    }

    private static IReadOnlyList<ActivationInventoryEntry> BuildActivationInventory(string generationRoot)
    {
        string root = Path.GetFullPath(generationRoot);
        List<ActivationInventoryEntry> inventory = [];
        var caseInsensitivePaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (string filePath in EnumerateRegularFilesWithoutLinks(root))
        {
            string relativePath = Path.GetRelativePath(root, filePath)
                .Replace(Path.DirectorySeparatorChar, '/');
            if (relativePath is ActivationCandidateName or CanonicalManifestName or CompatibilityManifestName)
            {
                continue;
            }

            if (relativePath.Contains('\n') || relativePath.Contains('\r') || relativePath.Contains('\t'))
            {
                throw new InvalidDataException("release shelf generation contains an unsafe inventory path.");
            }

            ValidatePortableInventoryPath(relativePath, "release shelf generation inventory");

            if (!caseInsensitivePaths.Add(relativePath))
            {
                throw new InvalidDataException(
                    $"release shelf generation inventory contains a case-colliding path '{relativePath}'.");
            }

            inventory.Add(new ActivationInventoryEntry(relativePath, Sha256For(filePath)));
        }

        ActivationInventoryEntry[] sorted = inventory
            .OrderBy(static row => row.Path, StringComparer.Ordinal)
            .ToArray();
        if (sorted.Length == 0)
        {
            throw new InvalidDataException("release shelf activation inventory must not be empty.");
        }

        return sorted;
    }

    private static string ComputeInventoryDigest(IReadOnlyList<ActivationInventoryEntry> inventory)
        => ReleaseShelfGenerationStore.ComputeInventoryDigest(
            inventory.Select(static row => new ReleaseShelfInventoryEntry(
                row.Path,
                row.Sha256,
                SizeBytes: 0)));

    private static CurrentPointerDocument BuildCurrentPointer(
        string generationId,
        string activationReceiptId,
        DateTimeOffset activatedAt,
        PublicReleaseManifestDto manifest,
        string generationRoot,
        string inventoryDigest)
    {
        return new CurrentPointerDocument(
            CurrentPointerSchema,
            generationId,
            manifest.Version,
            manifest.Channel,
            FormatTimestamp(manifest.PublishedAt),
            BuildManifestBindings(generationId, generationRoot),
            $"sha256:{inventoryDigest}",
            FormatTimestamp(activatedAt),
            activationReceiptId);
    }

    private static CurrentManifestBindings BuildManifestBindings(string generationId, string generationRoot)
        => new(
            new CurrentManifestBinding(
                $"/downloads/g/{generationId}/{CanonicalManifestName}",
                Sha256For(Path.Combine(generationRoot, CanonicalManifestName))),
            new CurrentManifestBinding(
                $"/downloads/g/{generationId}/{CompatibilityManifestName}",
                Sha256For(Path.Combine(generationRoot, CompatibilityManifestName))));

    private static void ValidateCandidateManifestBindings(
        string generationRoot,
        string generationId,
        CurrentManifestBindings bindings)
    {
        CurrentManifestBindings expected = BuildManifestBindings(generationId, generationRoot);
        if (bindings.Canonical is null
            || bindings.Compatibility is null
            || !string.Equals(bindings.Canonical.Path, expected.Canonical.Path, StringComparison.Ordinal)
            || !string.Equals(bindings.Canonical.Sha256, expected.Canonical.Sha256, StringComparison.Ordinal)
            || !string.Equals(bindings.Compatibility.Path, expected.Compatibility.Path, StringComparison.Ordinal)
            || !string.Equals(bindings.Compatibility.Sha256, expected.Compatibility.Sha256, StringComparison.Ordinal))
        {
            throw new InvalidDataException("retained release shelf activation candidate manifest binding mismatch.");
        }
    }

    private static string BuildGenerationArtifactUrl(
        string baseUrl,
        string generationId,
        PublicReleaseArtifactDto artifact)
    {
        string generationPrefix = $"{baseUrl}/downloads/g/{Uri.EscapeDataString(generationId)}";
        return string.Equals(
                artifact.InstallAccessClass?.Trim(),
                "open_public",
                StringComparison.OrdinalIgnoreCase)
            ? $"{generationPrefix}/files/{Uri.EscapeDataString(ResolveDownloadFileName(artifact))}"
            : $"{generationPrefix}/install/{Uri.EscapeDataString(artifact.Id)}";
    }

    private void ValidatePreparedGeneration(
        string generationRoot,
        CurrentPointerDocument pointer,
        IReadOnlyList<ActivationInventoryEntry> expectedInventory,
        IReadOnlyList<string> promotedArtifactIds)
    {
        PublicReleaseManifestDto manifest = ValidatePublicShelfCoherence(
            generationRoot,
            Path.Combine(generationRoot, CompatibilityManifestName),
            Path.Combine(generationRoot, CanonicalManifestName),
            promotedArtifactIds,
            pointer.GenerationId,
            pointer.Manifests.Compatibility.Sha256,
            pointer.Manifests.Canonical.Sha256);
        if (!string.Equals(manifest.Version, pointer.ReleaseVersion, StringComparison.Ordinal)
            || !string.Equals(manifest.Channel, pointer.Channel, StringComparison.Ordinal)
            || manifest.PublishedAt.ToUniversalTime()
                != DateTimeOffset.Parse(pointer.PublishedAt, CultureInfo.InvariantCulture).ToUniversalTime())
        {
            throw new InvalidDataException("release shelf pointer identity disagrees with its manifests.");
        }

        ActivationCandidateDocument candidate = JsonSerializer.Deserialize<ActivationCandidateDocument>(
                File.ReadAllText(Path.Combine(generationRoot, ActivationCandidateName)),
                JsonOptions)
            ?? throw new InvalidDataException("release shelf activation candidate is malformed.");
        if (!string.Equals(candidate.SchemaVersion, ActivationCandidateSchema, StringComparison.Ordinal)
            || !string.Equals(candidate.GenerationId, pointer.GenerationId, StringComparison.Ordinal)
            || !string.Equals(candidate.ReleaseVersion, pointer.ReleaseVersion, StringComparison.Ordinal)
            || !string.Equals(candidate.Channel, pointer.Channel, StringComparison.Ordinal)
            || !string.Equals(candidate.PublishedAt, pointer.PublishedAt, StringComparison.Ordinal)
            || !string.Equals(candidate.InventoryDigest, pointer.InventoryDigest, StringComparison.Ordinal)
            || !candidate.Inventory.SequenceEqual(expectedInventory))
        {
            throw new InvalidDataException("release shelf activation candidate disagrees with prepared generation identity or inventory.");
        }

        ValidateCandidateManifestBindings(generationRoot, pointer.GenerationId, candidate.Manifests);

        if (!string.Equals(
                Sha256For(Path.Combine(generationRoot, CanonicalManifestName)),
                pointer.Manifests.Canonical.Sha256,
                StringComparison.Ordinal)
            || !string.Equals(
                Sha256For(Path.Combine(generationRoot, CompatibilityManifestName)),
                pointer.Manifests.Compatibility.Sha256,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException("release shelf manifest binding digest mismatch.");
        }

        IReadOnlyList<ActivationInventoryEntry> actualInventory = BuildActivationInventory(generationRoot);
        if (!expectedInventory.SequenceEqual(actualInventory)
            || !string.Equals(
                pointer.InventoryDigest,
                $"sha256:{ComputeInventoryDigest(actualInventory)}",
                StringComparison.Ordinal))
        {
            throw new InvalidDataException("release shelf activation inventory digest mismatch.");
        }
    }

    private static string NewGenerationId(DateTimeOffset instant)
        => $"gen-{instant.ToUniversalTime():yyyyMMdd'T'HHmmss'Z'}-{Guid.NewGuid().ToString("N")[..16]}";

    private static bool IsSafeGenerationId(string? value)
        => value is { Length: > 0 and <= 128 }
           && char.IsLetterOrDigit(value[0])
           && value.All(static character => char.IsLetterOrDigit(character) || character is '.' or '_' or '-')
           && value is not "." and not ".."
           && !value.Contains("..", StringComparison.Ordinal)
           && !Path.IsPathFullyQualified(value);

    private static string FormatTimestamp(DateTimeOffset instant)
        => instant.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture);

    private static void WriteJsonFile<T>(string path, T payload)
    {
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(payload, JsonOptions);
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        using var stream = new FileStream(
            path,
            FileMode.Create,
            FileAccess.Write,
            FileShare.None,
            bufferSize: 64 * 1024,
            FileOptions.WriteThrough);
        stream.Write(bytes);
        stream.WriteByte((byte)'\n');
        stream.Flush(flushToDisk: true);
    }

    private static string PrepareCurrentPointerFile(string downloadsRoot, CurrentPointerDocument pointer)
    {
        string tempPath = Path.Combine(downloadsRoot, $".{CurrentPointerName}.{Guid.NewGuid():N}.tmp");
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(pointer, JsonOptions);
        using (var stream = new FileStream(
                   tempPath,
                   FileMode.CreateNew,
                   FileAccess.Write,
                   FileShare.None,
                   bufferSize: 64 * 1024,
                   FileOptions.WriteThrough))
        {
            stream.Write(bytes);
            stream.WriteByte((byte)'\n');
            stream.Flush(flushToDisk: true);
        }

        FlushDirectoryDurably(downloadsRoot);
        return tempPath;
    }

    private static void ActivateCurrentPointer(string tempPath, string pointerPath)
    {
        if (!string.Equals(
                Path.GetDirectoryName(Path.GetFullPath(tempPath)),
                Path.GetDirectoryName(Path.GetFullPath(pointerPath)),
                OperatingSystem.IsWindows() ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal))
        {
            throw new InvalidOperationException("current pointer replacement must remain on one filesystem.");
        }

        File.Move(tempPath, pointerPath, overwrite: true);
    }

    private static void CreateLayoutMarkerDurably(string downloadsRoot)
    {
        string markerPath = Path.Combine(downloadsRoot, LayoutMarkerName);
        if (File.Exists(markerPath))
        {
            throw new InvalidOperationException("release shelf layout marker appeared during activation.");
        }

        string tempPath = Path.Combine(downloadsRoot, $".{LayoutMarkerName}.{Guid.NewGuid():N}.tmp");
        try
        {
            byte[] bytes = Encoding.UTF8.GetBytes(LayoutMarkerContents);
            using (var stream = new FileStream(
                       tempPath,
                       FileMode.CreateNew,
                       FileAccess.Write,
                       FileShare.None,
                       bufferSize: 4096,
                       FileOptions.WriteThrough))
            {
                stream.Write(bytes);
                stream.Flush(flushToDisk: true);
            }

            File.Move(tempPath, markerPath);
            FlushDirectoryDurably(downloadsRoot);
        }
        finally
        {
            TryDeleteFile(tempPath);
        }
    }

    private void TryRemoveUnactivatedLayoutMarker(string downloadsRoot)
    {
        try
        {
            string markerPath = Path.Combine(downloadsRoot, LayoutMarkerName);
            if (File.Exists(markerPath) && !File.Exists(Path.Combine(downloadsRoot, CurrentPointerName)))
            {
                File.Delete(markerPath);
                FlushDirectoryDurably(downloadsRoot);
            }
        }
        catch (Exception ex)
        {
            _logger.LogCritical(
                ex,
                "Unactivated release shelf layout marker could not be removed from {DownloadsRoot}; readers will fail closed.",
                downloadsRoot);
        }
    }

    private ReleaseActivationIntent BuildActivationIntent(
        string operation,
        ReleaseShelfSnapshot activeShelf,
        ReleaseBundlePromotionResult result,
        string preparedPointerPath)
    {
        if (string.IsNullOrWhiteSpace(result.GenerationId)
            || string.IsNullOrWhiteSpace(result.ActivationReceiptId)
            || string.IsNullOrWhiteSpace(result.InventoryDigest))
        {
            throw new InvalidDataException("release activation intent requires complete target generation identity.");
        }

        string? previousPointerSha256 = string.IsNullOrWhiteSpace(activeShelf.PointerDigest)
            ? null
            : $"sha256:{activeShelf.PointerDigest}";
        byte[]? previousPointerBytes = ReadRegularFileBytesOrNull(
            Path.Combine(ResolveDownloadsRoot(), CurrentPointerName),
            "release shelf current pointer");
        if (!string.Equals(
                Sha256BindingForBytes(previousPointerBytes),
                previousPointerSha256,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "active release shelf pointer bytes changed while preparing activation intent.");
        }

        byte[] targetPointerBytes = ReadRequiredRegularFileBytes(
            preparedPointerPath,
            "prepared release shelf current pointer");
        return new ReleaseActivationIntent(
            Operation: operation,
            PreviousGenerationId: activeShelf.GenerationId,
            PreviousPointerSha256: previousPointerSha256,
            GenerationId: result.GenerationId,
            ActivationReceiptId: result.ActivationReceiptId,
            ReleaseVersion: result.Version,
            Channel: result.Channel,
            PublishedAt: result.PublishedAt.ToUniversalTime(),
            InventoryDigest: NormalizeSha256Binding(result.InventoryDigest),
            PointerSha256: Sha256BindingForBytes(targetPointerBytes)
                ?? throw new InvalidDataException("prepared current pointer digest is missing."),
            PreparedAtUtc: _timeProvider.GetUtcNow().ToUniversalTime(),
            PreviousPointerBase64: previousPointerBytes is null
                ? null
                : Convert.ToBase64String(previousPointerBytes),
            TargetPointerBase64: Convert.ToBase64String(targetPointerBytes));
    }

    private static string NormalizeSha256Binding(string value)
    {
        string normalized = value.Trim().ToLowerInvariant();
        return normalized.StartsWith("sha256:", StringComparison.Ordinal)
            ? normalized
            : $"sha256:{normalized}";
    }

    private void PrepareActivationIntentDurably(
        string downloadsRoot,
        ReleaseActivationIntent intent,
        string preparedPointerPath)
    {
        ValidateActivationIntent(intent);
        EnsureNoUnresolvedActivationIntent(downloadsRoot);

        byte[]? previousPointerBytes = DecodeOptionalPointerBytes(intent.PreviousPointerBase64);
        byte[]? livePreviousPointerBytes = ReadRegularFileBytesOrNull(
            Path.Combine(downloadsRoot, CurrentPointerName),
            "release shelf current pointer");
        if (!BytesEqual(livePreviousPointerBytes, previousPointerBytes)
            || !string.Equals(
                Sha256BindingForBytes(livePreviousPointerBytes),
                intent.PreviousPointerSha256,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "release activation intent previous pointer digest changed before journaling.");
        }

        byte[] targetPointerBytes = DecodeRequiredPointerBytes(
            intent.TargetPointerBase64,
            "target");
        byte[] preparedTargetPointerBytes = ReadRequiredRegularFileBytes(
            preparedPointerPath,
            "prepared release shelf current pointer");
        if (!BytesEqual(preparedTargetPointerBytes, targetPointerBytes)
            || !string.Equals(
                Sha256BindingForBytes(preparedTargetPointerBytes),
                intent.PointerSha256,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException("prepared current pointer bytes do not match the activation intent digest.");
        }

        var journal = new ReleaseActivationJournalDocument(
            SchemaVersion: "chummer.release-shelf.activation-intent/v1",
            State: "prepared",
            Intent: intent,
            PreviousPointerBase64: intent.PreviousPointerBase64,
            TargetPointerBase64: intent.TargetPointerBase64!);
        _ = ValidateActivationJournalTarget(journal);

        string historyRoot = ActivationJournalHistoryRoot(downloadsRoot);
        EnsureOwnerOnlyDirectory(historyRoot);
        string activePath = Path.Combine(downloadsRoot, ActivationIntentName);
        WriteOwnerOnlyJsonAtomicallyDurable(activePath, journal, overwrite: false);
        _activationJournalCheckpoint?.Invoke(ActivationJournalCheckpoint.ActiveIntentDurable);
        try
        {
            PublishActivationHistoryIntentDurably(downloadsRoot, journal, _activationJournalCheckpoint);
        }
        catch (Exception original)
        {
            if (original is ReleaseActivationProcessTerminationSimulationException)
            {
                throw;
            }

            try
            {
                EnsureHistoryForActivePartial(downloadsRoot, journal);
                AbortPreparedActivationIntent(downloadsRoot, intent);
            }
            catch (Exception recovery)
            {
                throw new ReleaseActivationOutcomeUnknownException(
                    intent,
                    new AggregateException(original, recovery));
            }

            throw new ReleaseActivationAbortedException(intent, original);
        }
    }

    private static void ResolveActivationIntentDurably(
        string downloadsRoot,
        ReleaseActivationJournalDocument journal,
        string state)
    {
        if (state is not "committed" and not "aborted")
        {
            throw new InvalidDataException("release activation outcome state is invalid.");
        }

        ReleaseActivationJournalDocument retained = LoadActivationHistoryJournal(
            downloadsRoot,
            journal.Intent.ActivationReceiptId);
        if (retained != journal)
        {
            throw new InvalidDataException("release activation history changed before outcome resolution.");
        }

        string outcomePath = Path.Combine(
            ActivationJournalReceiptRoot(downloadsRoot, journal.Intent.ActivationReceiptId),
            ActivationJournalOutcomeName);
        var outcome = new ReleaseActivationOutcomeDocument(
            SchemaVersion: "chummer.release-shelf.activation-outcome/v1",
            State: state,
            ActivationReceiptId: journal.Intent.ActivationReceiptId,
            IntentSha256: ComputeActivationIntentDigest(journal),
            ResolvedAtUtc: DateTimeOffset.UtcNow);
        if (File.Exists(outcomePath))
        {
            ReleaseActivationOutcomeDocument existing = LoadActivationOutcome(outcomePath, journal);
            if (!string.Equals(existing.State, state, StringComparison.Ordinal))
            {
                throw new InvalidDataException("release activation history already has a conflicting outcome.");
            }
        }
        else
        {
            WriteOwnerOnlyJsonAtomicallyDurable(outcomePath, outcome, overwrite: false);
        }

        if (string.Equals(state, "aborted", StringComparison.Ordinal))
        {
            string activePath = Path.Combine(downloadsRoot, ActivationIntentName);
            if (File.Exists(activePath))
            {
                ReleaseActivationJournalDocument active = LoadActivationJournalFile(activePath);
                if (active != journal)
                {
                    throw new InvalidDataException("active release activation intent changed before outcome resolution.");
                }

                File.Delete(activePath);
                FlushDirectoryDurably(downloadsRoot);
            }
        }
    }

    private static void AcknowledgeActivationCompletionUnderLock(
        string downloadsRoot,
        ReleaseActivationIntent intent)
    {
        ReleaseActivationJournalDocument journal = LoadActivationHistoryJournal(
            downloadsRoot,
            intent.ActivationReceiptId);
        if (journal.Intent != intent)
        {
            throw new InvalidDataException("release activation completion acknowledgement does not match immutable history.");
        }

        ReleaseActivationOutcomeDocument outcome = TryLoadActivationOutcome(downloadsRoot, journal)
            ?? throw new InvalidOperationException("release activation cannot be acknowledged before a durable outcome exists.");
        if (!string.Equals(outcome.State, "committed", StringComparison.Ordinal))
        {
            throw new InvalidOperationException("only a committed release activation can be acknowledged as completed.");
        }

        string activePath = Path.Combine(downloadsRoot, ActivationIntentName);
        if (!File.Exists(activePath))
        {
            return;
        }

        ReleaseActivationJournalDocument active = LoadActivationJournalFile(activePath);
        if (active != journal)
        {
            throw new InvalidDataException("active release activation intent changed before completion acknowledgement.");
        }

        File.Delete(activePath);
        FlushDirectoryDurably(downloadsRoot);
    }

    private static void WriteOwnerOnlyJsonAtomicallyDurable<T>(
        string path,
        T payload,
        bool overwrite = true)
    {
        string directory = Path.GetDirectoryName(path)
            ?? throw new InvalidDataException("activation journal parent directory is missing.");
        EnsureOwnerOnlyDirectory(directory);
        string tempPath = Path.Combine(directory, $".{Path.GetFileName(path)}.{Guid.NewGuid():N}.tmp");
        byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(payload, JsonOptions);
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
                options.UnixCreateMode = UnixFileMode.UserRead | UnixFileMode.UserWrite;
            }

            using (var stream = new FileStream(tempPath, options))
            {
                stream.Write(bytes);
                stream.WriteByte((byte)'\n');
                stream.Flush(flushToDisk: true);
            }

            File.Move(tempPath, path, overwrite);
            if (!OperatingSystem.IsWindows())
            {
                File.SetUnixFileMode(path, UnixFileMode.UserRead | UnixFileMode.UserWrite);
            }

            FlushDirectoryDurably(directory);
        }
        finally
        {
            TryDeleteFile(tempPath);
        }
    }

    private static void EnsureNoUnresolvedActivationIntent(string downloadsRoot)
    {
        string activePath = Path.Combine(downloadsRoot, ActivationIntentName);
        ReleaseActivationJournalDocument? active = File.Exists(activePath)
            ? LoadActivationJournalFile(activePath)
            : null;
        if (active is not null)
        {
            string activeHistoryPath = Path.Combine(
                ActivationJournalReceiptRoot(downloadsRoot, active.Intent.ActivationReceiptId),
                ActivationJournalIntentName);
            if (!File.Exists(activeHistoryPath))
            {
                EnsureHistoryForActivePartial(downloadsRoot, active);
                byte[]? currentPointerBytes = ReadRegularFileBytesOrNull(
                    Path.Combine(downloadsRoot, CurrentPointerName),
                    "release shelf current pointer");
                byte[]? previousPointerBytes = DecodeOptionalPointerBytes(active.PreviousPointerBase64);
                if (BytesEqual(currentPointerBytes, previousPointerBytes)
                    && string.Equals(
                        Sha256BindingForBytes(currentPointerBytes),
                        active.Intent.PreviousPointerSha256,
                        StringComparison.Ordinal))
                {
                    if (currentPointerBytes is null)
                    {
                        RemoveUnactivatedLayoutMarkerDurably(downloadsRoot);
                    }

                    FlushDirectoryDurably(downloadsRoot);
                    ResolveActivationIntentDurably(downloadsRoot, active, state: "aborted");
                    active = null;
                }
            }
        }

        string historyRoot = ActivationJournalHistoryRoot(downloadsRoot);
        if (!Directory.Exists(historyRoot))
        {
            if (active is not null)
            {
                throw new InvalidDataException("active release activation intent has no immutable history.");
            }

            return;
        }

        EnsureRegularDirectory(historyRoot, "release activation journal history");
        List<ReleaseActivationJournalDocument> unresolved = [];
        foreach (string entry in Directory.EnumerateFileSystemEntries(historyRoot))
        {
            if (!Directory.Exists(entry))
            {
                throw new InvalidDataException("release activation journal history contains a non-directory entry.");
            }

            EnsureRegularDirectory(entry, "release activation journal receipt directory");
            string receiptId = Path.GetFileName(entry);
            ReleaseActivationJournalDocument journal = LoadActivationHistoryJournal(downloadsRoot, receiptId);
            ReleaseActivationOutcomeDocument? outcome = TryLoadActivationOutcome(downloadsRoot, journal);
            if (outcome is null)
            {
                unresolved.Add(journal);
            }
        }

        if (unresolved.Count > 1)
        {
            throw new InvalidDataException("release activation journal contains multiple unresolved intents.");
        }

        if (active is not null)
        {
            ReleaseActivationJournalDocument matchingHistory = LoadActivationHistoryJournal(
                downloadsRoot,
                active.Intent.ActivationReceiptId);
            if (matchingHistory != active)
            {
                throw new InvalidDataException("active release activation intent does not match immutable history.");
            }

            ReleaseActivationOutcomeDocument? activeOutcome = TryLoadActivationOutcome(downloadsRoot, active);
            if (activeOutcome is not null && string.Equals(activeOutcome.State, "aborted", StringComparison.Ordinal))
            {
                File.Delete(activePath);
                FlushDirectoryDurably(downloadsRoot);
                active = null;
            }
            else if (activeOutcome is not null)
            {
                throw new InvalidOperationException(
                    $"committed release activation '{active.Intent.ActivationReceiptId}' awaits durable upload-session completion acknowledgement.");
            }
        }

        if (unresolved.Count == 0)
        {
            if (active is not null)
            {
                throw new InvalidDataException("active release activation intent is not unresolved in immutable history.");
            }

            return;
        }

        ReleaseActivationJournalDocument pending = unresolved[0];
        if (active is not null && active != pending)
        {
            throw new InvalidDataException("active release activation intent identifies a different unresolved history entry.");
        }

        throw new InvalidOperationException(
            $"release activation intent for generation '{pending.Intent.GenerationId}' is unresolved; reconcile it before another promotion or rollback.");
    }

    private static void EnsureHistoryForActivePartial(
        string downloadsRoot,
        ReleaseActivationJournalDocument active)
    {
        string historyRoot = ActivationJournalHistoryRoot(downloadsRoot);
        EnsureOwnerOnlyDirectory(historyRoot);
        string receiptRoot = ActivationJournalReceiptRoot(
            downloadsRoot,
            active.Intent.ActivationReceiptId);
        if (File.Exists(receiptRoot) && !Directory.Exists(receiptRoot))
        {
            throw new InvalidDataException("release activation receipt history path is not a directory.");
        }

        string intentPath = Path.Combine(receiptRoot, ActivationJournalIntentName);
        if (File.Exists(intentPath))
        {
            ReleaseActivationJournalDocument retained = LoadActivationJournalFile(intentPath);
            if (retained != active)
            {
                throw new InvalidDataException("partial release activation history conflicts with the active intent.");
            }

            // A prior process may have stopped after the receipt-directory rename and
            // before it could prove the parent-directory entry durable. Re-flushing the
            // parent is harmless and closes that recovery window before callers may
            // resolve the intent and remove the active barrier.
            FlushDirectoryDurably(historyRoot);
            return;
        }

        if (Directory.Exists(receiptRoot))
        {
            throw new InvalidDataException(
                "partial release activation receipt directory was exposed without a complete intent.");
        }

        string tempPrefix = $".release-shelf-activation-receipt-{active.Intent.ActivationReceiptId}-";
        foreach (string entry in Directory.EnumerateFileSystemEntries(downloadsRoot))
        {
            string name = Path.GetFileName(entry);
            if (!name.StartsWith(tempPrefix, StringComparison.Ordinal)
                || !name.EndsWith(".tmp", StringComparison.Ordinal))
            {
                continue;
            }

            EnsureRegularDirectory(entry, "partial release activation receipt transaction");
            Directory.Delete(entry, recursive: true);
        }

        FlushDirectoryDurably(downloadsRoot);
        PublishActivationHistoryIntentDurably(downloadsRoot, active, checkpoint: null);
    }

    private static void PublishActivationHistoryIntentDurably(
        string downloadsRoot,
        ReleaseActivationJournalDocument journal,
        Action<ActivationJournalCheckpoint>? checkpoint)
    {
        string historyRoot = ActivationJournalHistoryRoot(downloadsRoot);
        EnsureOwnerOnlyDirectory(historyRoot);
        string receiptRoot = ActivationJournalReceiptRoot(
            downloadsRoot,
            journal.Intent.ActivationReceiptId);
        if (Directory.Exists(receiptRoot) || File.Exists(receiptRoot))
        {
            throw new InvalidDataException(
                $"release activation receipt history already exists: {journal.Intent.ActivationReceiptId}");
        }

        string tempReceiptRoot = Path.Combine(
            downloadsRoot,
            $".release-shelf-activation-receipt-{journal.Intent.ActivationReceiptId}-{Guid.NewGuid():N}.tmp");
        try
        {
            EnsureOwnerOnlyDirectory(tempReceiptRoot);
            checkpoint?.Invoke(ActivationJournalCheckpoint.ReceiptTempDirectoryDurable);
            WriteOwnerOnlyJsonAtomicallyDurable(
                Path.Combine(tempReceiptRoot, ActivationJournalIntentName),
                journal,
                overwrite: false);
            checkpoint?.Invoke(ActivationJournalCheckpoint.ReceiptIntentDurable);
            FlushDirectoryDurably(tempReceiptRoot);
            Directory.Move(tempReceiptRoot, receiptRoot);
            FlushDirectoryDurably(historyRoot);
            checkpoint?.Invoke(ActivationJournalCheckpoint.ReceiptHistoryPublished);
            checkpoint?.Invoke(ActivationJournalCheckpoint.ReceiptHistoryParentDurable);
        }
        finally
        {
            if (Directory.Exists(tempReceiptRoot))
            {
                Directory.Delete(tempReceiptRoot, recursive: true);
                FlushDirectoryDurably(downloadsRoot);
            }
        }
    }

    private static ReleaseActivationJournalDocument LoadActivationHistoryJournal(
        string downloadsRoot,
        string activationReceiptId)
    {
        if (!IsSafeGenerationId(activationReceiptId))
        {
            throw new InvalidDataException("release activation receipt id is not a traversal-safe token.");
        }

        string path = Path.Combine(
            ActivationJournalReceiptRoot(downloadsRoot, activationReceiptId),
            ActivationJournalIntentName);
        if (!File.Exists(path))
        {
            throw new InvalidDataException("release activation intent history is missing.");
        }

        ReleaseActivationJournalDocument journal = LoadActivationJournalFile(path);
        if (!string.Equals(journal.Intent.ActivationReceiptId, activationReceiptId, StringComparison.Ordinal))
        {
            throw new InvalidDataException("release activation receipt directory and intent disagree.");
        }

        return journal;
    }

    private static ReleaseActivationJournalDocument LoadActivationJournalFile(string path)
    {
        EnsureOwnerOnlyRegularFile(path, "release activation journal");
        JsonObject json = LoadStrictJsonObject(path);
        RequireExactProperties(
            json,
            ["schemaVersion", "state", "intent", "previousPointerBase64", "targetPointerBase64"],
            "release activation journal");
        if (json["intent"] is not JsonObject intentJson)
        {
            throw new InvalidDataException("release activation journal intent is malformed.");
        }

        RequireExactProperties(
            intentJson,
            [
                "operation", "previousGenerationId", "previousPointerSha256", "generationId",
                "activationReceiptId", "releaseVersion", "channel", "publishedAt",
                "inventoryDigest", "pointerSha256", "preparedAtUtc",
                "previousPointerBase64", "targetPointerBase64"
            ],
            "release activation intent");
        ReleaseActivationJournalDocument journal = json.Deserialize<ReleaseActivationJournalDocument>(JsonOptions)
            ?? throw new InvalidDataException("release activation journal is malformed.");
        if (!string.Equals(
                journal.SchemaVersion,
                "chummer.release-shelf.activation-intent/v1",
                StringComparison.Ordinal)
            || !string.Equals(journal.State, "prepared", StringComparison.Ordinal)
            || journal.Intent is null)
        {
            throw new InvalidDataException("release activation journal contract is invalid.");
        }

        ValidateActivationIntent(journal.Intent);
        if (!string.Equals(
                journal.PreviousPointerBase64,
                journal.Intent.PreviousPointerBase64,
                StringComparison.Ordinal)
            || !string.Equals(
                journal.TargetPointerBase64,
                journal.Intent.TargetPointerBase64,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "release activation journal pointer bytes disagree with the session-bound intent.");
        }

        byte[]? previousPointerBytes = string.IsNullOrWhiteSpace(journal.PreviousPointerBase64)
            ? null
            : Convert.FromBase64String(journal.PreviousPointerBase64);
        string? previousPointerSha256 = previousPointerBytes is null
            ? null
            : $"sha256:{Convert.ToHexStringLower(SHA256.HashData(previousPointerBytes))}";
        if (!string.Equals(
                previousPointerSha256,
                journal.Intent.PreviousPointerSha256,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException("release activation journal previous pointer bytes do not match their digest.");
        }

        _ = ValidateActivationJournalTarget(journal);

        return journal;
    }

    private static ReleaseActivationOutcomeDocument? TryLoadActivationOutcome(
        string downloadsRoot,
        ReleaseActivationJournalDocument journal)
    {
        string path = Path.Combine(
            ActivationJournalReceiptRoot(downloadsRoot, journal.Intent.ActivationReceiptId),
            ActivationJournalOutcomeName);
        return File.Exists(path) ? LoadActivationOutcome(path, journal) : null;
    }

    private static ReleaseActivationOutcomeDocument LoadActivationOutcome(
        string path,
        ReleaseActivationJournalDocument journal)
    {
        EnsureOwnerOnlyRegularFile(path, "release activation outcome");
        JsonObject json = LoadStrictJsonObject(path);
        RequireExactProperties(
            json,
            ["schemaVersion", "state", "activationReceiptId", "intentSha256", "resolvedAtUtc"],
            "release activation outcome");
        ReleaseActivationOutcomeDocument outcome = json.Deserialize<ReleaseActivationOutcomeDocument>(JsonOptions)
            ?? throw new InvalidDataException("release activation outcome is malformed.");
        if (!string.Equals(outcome.SchemaVersion, "chummer.release-shelf.activation-outcome/v1", StringComparison.Ordinal)
            || outcome.State is not "committed" and not "aborted"
            || !string.Equals(outcome.ActivationReceiptId, journal.Intent.ActivationReceiptId, StringComparison.Ordinal)
            || !string.Equals(outcome.IntentSha256, ComputeActivationIntentDigest(journal), StringComparison.Ordinal)
            || outcome.ResolvedAtUtc.Offset != TimeSpan.Zero)
        {
            throw new InvalidDataException("release activation outcome contract is invalid.");
        }

        return outcome;
    }

    private static void ValidateActivationIntent(ReleaseActivationIntent intent)
    {
        if (intent.Operation is not "promotion" and not "rollback"
            || !IsSafeGenerationId(intent.GenerationId)
            || (intent.PreviousGenerationId is not null && !IsSafeGenerationId(intent.PreviousGenerationId))
            || !IsSafeGenerationId(intent.ActivationReceiptId)
            || string.IsNullOrWhiteSpace(intent.ReleaseVersion) || intent.ReleaseVersion.Length > 256
            || string.IsNullOrWhiteSpace(intent.Channel) || intent.Channel.Length > 128
            || (intent.PreviousGenerationId is null) != (intent.PreviousPointerSha256 is null)
            || !IsSha256Binding(intent.InventoryDigest)
            || !IsSha256Binding(intent.PointerSha256)
            || (intent.PreviousPointerSha256 is not null && !IsSha256Binding(intent.PreviousPointerSha256))
            || intent.PublishedAt.Offset != TimeSpan.Zero
            || intent.PreparedAtUtc.Offset != TimeSpan.Zero)
        {
            throw new InvalidDataException("release activation intent identity is invalid.");
        }

        byte[]? previousPointerBytes;
        byte[] targetPointerBytes;
        try
        {
            previousPointerBytes = DecodeOptionalPointerBytes(intent.PreviousPointerBase64);
            targetPointerBytes = DecodeRequiredPointerBytes(intent.TargetPointerBase64, "target");
        }
        catch (FormatException ex)
        {
            throw new InvalidDataException("release activation intent pointer bytes are malformed.", ex);
        }

        if ((previousPointerBytes is null) != (intent.PreviousPointerSha256 is null)
            || (previousPointerBytes is not null
                && !string.Equals(
                    Convert.ToBase64String(previousPointerBytes),
                    intent.PreviousPointerBase64,
                    StringComparison.Ordinal))
            || !string.Equals(
                Convert.ToBase64String(targetPointerBytes),
                intent.TargetPointerBase64,
                StringComparison.Ordinal)
            || (previousPointerBytes?.Length ?? 0) > 64 * 1024
            || targetPointerBytes.Length > 64 * 1024
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

    private static bool IsSha256Binding(string? value)
    {
        if (string.IsNullOrWhiteSpace(value)
            || !value.StartsWith("sha256:", StringComparison.Ordinal))
        {
            return false;
        }

        string digest = value[7..];
        return digest.Length == 64
               && digest.All(static character => character is >= '0' and <= '9' or >= 'a' and <= 'f');
    }

    private ReleaseBundlePromotionResult BuildPromotionResultFromCommittedJournal(
        string downloadsRoot,
        ReleaseActivationJournalDocument journal)
    {
        CurrentPointerDocument pointer = ValidateActivationJournalTarget(journal);
        string generationRoot = Path.Combine(downloadsRoot, GenerationsDirectoryName, journal.Intent.GenerationId);
        if (!Directory.Exists(generationRoot))
        {
            throw new InvalidDataException("release activation target generation is missing.");
        }

        PublicReleaseManifestDto manifest = LoadCompatibilityManifest(
            Path.Combine(generationRoot, CompatibilityManifestName));
        string[] artifactIds = manifest.Downloads
            .Select(static artifact => artifact.Id)
            .Where(static artifactId => !string.IsNullOrWhiteSpace(artifactId))
            .ToArray();
        IReadOnlyList<ActivationInventoryEntry> inventory = BuildActivationInventory(generationRoot);
        ValidatePreparedGeneration(generationRoot, pointer, inventory, artifactIds);
        if (!string.Equals(journal.Intent.ReleaseVersion, manifest.Version, StringComparison.Ordinal)
            || !string.Equals(journal.Intent.Channel, manifest.Channel, StringComparison.Ordinal)
            || journal.Intent.PublishedAt != manifest.PublishedAt.ToUniversalTime())
        {
            throw new InvalidDataException("release activation journal identity disagrees with its immutable generation.");
        }

        string baseUrl = ResolvePublicBaseUrl();
        return new ReleaseBundlePromotionResult(
            manifest.Version,
            manifest.Channel,
            manifest.PublishedAt,
            artifactIds,
            $"{baseUrl}/downloads/",
            manifest.Downloads
                .Where(static artifact => !string.IsNullOrWhiteSpace(artifact.Id))
                .Select(artifact => BuildGenerationArtifactUrl(baseUrl, journal.Intent.GenerationId, artifact))
                .ToArray(),
            manifest.Downloads
                .Select(download => $"{baseUrl}{NormalizePublicPath(download.Url)}")
                .ToArray(),
            GenerationId: journal.Intent.GenerationId,
            ActivationReceiptId: journal.Intent.ActivationReceiptId,
            ActivatedAt: DateTimeOffset.Parse(pointer.ActivatedAt, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal),
            InventoryDigest: journal.Intent.InventoryDigest);
    }

    private void RequireCommittedGenerationHistory(string downloadsRoot, string generationId)
    {
        string historyRoot = ActivationJournalHistoryRoot(downloadsRoot);
        if (!Directory.Exists(historyRoot))
        {
            throw new InvalidDataException("rollback target has no committed activation history.");
        }

        EnsureRegularDirectory(historyRoot, "release activation journal history");
        foreach (string receiptRoot in Directory.EnumerateDirectories(historyRoot))
        {
            string receiptId = Path.GetFileName(receiptRoot);
            ReleaseActivationJournalDocument journal = LoadActivationHistoryJournal(downloadsRoot, receiptId);
            if (!string.Equals(journal.Intent.GenerationId, generationId, StringComparison.Ordinal))
            {
                continue;
            }

            ReleaseActivationOutcomeDocument? outcome = TryLoadActivationOutcome(downloadsRoot, journal);
            if (outcome is not null && string.Equals(outcome.State, "committed", StringComparison.Ordinal))
            {
                _ = BuildPromotionResultFromCommittedJournal(downloadsRoot, journal);
                return;
            }
        }

        throw new InvalidDataException("rollback target was never durably committed.");
    }

    private static CurrentPointerDocument ValidateActivationJournalTarget(
        ReleaseActivationJournalDocument journal)
    {
        byte[] targetPointerBytes = DecodeRequiredPointerBytes(journal.TargetPointerBase64, "target");
        if (!string.Equals(Sha256BindingForBytes(targetPointerBytes), journal.Intent.PointerSha256, StringComparison.Ordinal))
        {
            throw new InvalidDataException("release activation journal target pointer bytes do not match their digest.");
        }

        CurrentPointerDocument pointer = JsonSerializer.Deserialize<CurrentPointerDocument>(targetPointerBytes, JsonOptions)
            ?? throw new InvalidDataException("release activation journal target pointer is malformed.");
        if (!string.Equals(pointer.SchemaVersion, CurrentPointerSchema, StringComparison.Ordinal)
            || !string.Equals(pointer.GenerationId, journal.Intent.GenerationId, StringComparison.Ordinal)
            || !string.Equals(pointer.ActivationReceiptId, journal.Intent.ActivationReceiptId, StringComparison.Ordinal)
            || !string.Equals(pointer.ReleaseVersion, journal.Intent.ReleaseVersion, StringComparison.Ordinal)
            || !string.Equals(pointer.Channel, journal.Intent.Channel, StringComparison.Ordinal)
            || !DateTimeOffset.TryParse(pointer.PublishedAt, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out DateTimeOffset publishedAt)
            || publishedAt.ToUniversalTime() != journal.Intent.PublishedAt
            || !string.Equals(NormalizeSha256Binding(pointer.InventoryDigest), journal.Intent.InventoryDigest, StringComparison.Ordinal)
            || !DateTimeOffset.TryParse(pointer.ActivatedAt, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out _))
        {
            throw new InvalidDataException("release activation journal target pointer identity is invalid.");
        }

        return pointer;
    }

    private static string ComputeActivationIntentDigest(ReleaseActivationJournalDocument journal)
        => $"sha256:{Convert.ToHexStringLower(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(journal, JsonOptions)))}";

    private static string ActivationJournalHistoryRoot(string downloadsRoot)
        => Path.Combine(downloadsRoot, ActivationJournalDirectoryName);

    private static string ActivationJournalReceiptRoot(string downloadsRoot, string activationReceiptId)
        => Path.Combine(ActivationJournalHistoryRoot(downloadsRoot), activationReceiptId);

    private static byte[] ReadRequiredRegularFileBytes(string path, string description)
        => ReadRegularFileBytesOrNull(path, description)
           ?? throw new InvalidDataException($"{description} is missing.");

    private static byte[]? ReadRegularFileBytesOrNull(string path, string description)
    {
        if (!File.Exists(path))
        {
            return null;
        }

        EnsureRegularFile(path, description);
        return File.ReadAllBytes(path);
    }

    private static string? Sha256BindingForBytes(byte[]? bytes)
        => bytes is null ? null : $"sha256:{Convert.ToHexStringLower(SHA256.HashData(bytes))}";

    private static byte[] DecodeRequiredPointerBytes(string? encoded, string description)
        => DecodeOptionalPointerBytes(encoded)
           ?? throw new InvalidDataException($"release activation journal {description} pointer bytes are missing.");

    private static byte[]? DecodeOptionalPointerBytes(string? encoded)
    {
        if (string.IsNullOrWhiteSpace(encoded))
        {
            return null;
        }

        try
        {
            return Convert.FromBase64String(encoded);
        }
        catch (FormatException ex)
        {
            throw new InvalidDataException("release activation journal pointer bytes are not valid base64.", ex);
        }
    }

    private static bool BytesEqual(byte[]? left, byte[]? right)
        => left is null || right is null
            ? left is null && right is null
            : CryptographicOperations.FixedTimeEquals(left, right);

    private static JsonObject LoadStrictJsonObject(string path)
    {
        try
        {
            return JsonNode.Parse(File.ReadAllBytes(path)) as JsonObject
                   ?? throw new InvalidDataException($"JSON document is not an object: {path}");
        }
        catch (JsonException ex)
        {
            throw new InvalidDataException($"JSON document is malformed: {path}", ex);
        }
    }

    private static void RequireExactProperties(
        JsonObject value,
        IReadOnlyCollection<string> expected,
        string description)
    {
        string[] actual = value.Select(static property => property.Key).Order(StringComparer.Ordinal).ToArray();
        string[] required = expected.Order(StringComparer.Ordinal).ToArray();
        if (!actual.SequenceEqual(required, StringComparer.Ordinal))
        {
            throw new InvalidDataException($"{description} property set is noncanonical.");
        }
    }

    private static void EnsureOwnerOnlyRegularFile(string path, string description)
    {
        EnsureRegularFile(path, description);
        if (!OperatingSystem.IsWindows())
        {
            UnixFileMode forbidden = UnixFileMode.GroupRead | UnixFileMode.GroupWrite | UnixFileMode.GroupExecute
                                     | UnixFileMode.OtherRead | UnixFileMode.OtherWrite | UnixFileMode.OtherExecute;
            if ((File.GetUnixFileMode(path) & forbidden) != 0)
            {
                throw new InvalidDataException($"{description} must be owner-only.");
            }
        }
    }

    private static void EnsureRegularFile(string path, string description)
    {
        FileAttributes attributes = File.GetAttributes(path);
        if ((attributes & (FileAttributes.Directory | FileAttributes.ReparsePoint)) != 0)
        {
            throw new InvalidDataException($"{description} must be a regular file and cannot be a link.");
        }
    }

    private static void EnsureRegularDirectory(string path, string description)
    {
        FileAttributes attributes = File.GetAttributes(path);
        if ((attributes & FileAttributes.Directory) == 0 || (attributes & FileAttributes.ReparsePoint) != 0)
        {
            throw new InvalidDataException($"{description} must be a directory and cannot be a link.");
        }
    }

    private static void EnsureOwnerOnlyDirectory(string path)
    {
        if (Directory.Exists(path))
        {
            EnsureRegularDirectory(path, "release activation journal directory");
        }
        else
        {
            Directory.CreateDirectory(path);
            EnsureRegularDirectory(path, "release activation journal directory");
            FlushDirectoryDurably(Path.GetDirectoryName(path)
                ?? throw new InvalidDataException("release activation journal directory has no parent."));
        }

        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(path, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
        }
    }

    private static void RemoveUnactivatedLayoutMarkerDurably(string downloadsRoot)
    {
        string markerPath = Path.Combine(downloadsRoot, LayoutMarkerName);
        if (!File.Exists(Path.Combine(downloadsRoot, CurrentPointerName)) && File.Exists(markerPath))
        {
            File.Delete(markerPath);
            FlushDirectoryDurably(downloadsRoot);
        }
    }

    private void ConfirmActivationDirectoryDurability(
        string downloadsRoot,
        ReleaseActivationIntent intent)
    {
        try
        {
            _postActivationDirectoryFlush(downloadsRoot);
            ReleaseActivationJournalDocument journal = LoadActivationHistoryJournal(
                downloadsRoot,
                intent.ActivationReceiptId);
            if (journal.Intent != intent)
            {
                throw new InvalidDataException("release activation intent changed before commit confirmation.");
            }

            ResolveActivationIntentDurably(downloadsRoot, journal, state: "committed");
        }
        catch (Exception ex)
        {
            _logger.LogCritical(
                ex,
                "Release shelf current.json was renamed, but activation durability could not be confirmed for {GenerationId}.",
                intent.GenerationId);
            throw new ReleaseActivationOutcomeUnknownException(intent, ex);
        }
    }

    private static void AbortPreparedActivationIntent(
        string downloadsRoot,
        ReleaseActivationIntent intent)
    {
        try
        {
            ReleaseActivationJournalDocument journal = LoadActivationHistoryJournal(
                downloadsRoot,
                intent.ActivationReceiptId);
            if (journal.Intent != intent)
            {
                throw new InvalidDataException("release activation intent changed before durable abort.");
            }

            byte[]? currentPointerBytes = ReadRegularFileBytesOrNull(
                Path.Combine(downloadsRoot, CurrentPointerName),
                "release shelf current pointer");
            byte[]? previousPointerBytes = DecodeOptionalPointerBytes(journal.PreviousPointerBase64);
            if (!BytesEqual(currentPointerBytes, previousPointerBytes)
                || !string.Equals(
                    Sha256BindingForBytes(currentPointerBytes),
                    intent.PreviousPointerSha256,
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    "release activation cannot be aborted because current.json no longer matches the retained previous pointer.");
            }

            if (currentPointerBytes is null)
            {
                RemoveUnactivatedLayoutMarkerDurably(downloadsRoot);
            }

            FlushDirectoryDurably(downloadsRoot);
            ResolveActivationIntentDurably(downloadsRoot, journal, state: "aborted");
        }
        catch (Exception ex) when (ex is not ReleaseActivationOutcomeUnknownException)
        {
            throw new ReleaseActivationOutcomeUnknownException(intent, ex);
        }
    }

    private void TryCreateLayoutMarkerAfterActivation(string downloadsRoot)
    {
        try
        {
            string markerPath = Path.Combine(downloadsRoot, LayoutMarkerName);
            if (!File.Exists(markerPath))
            {
                CreateLayoutMarkerDurably(downloadsRoot);
            }
        }
        catch (Exception ex)
        {
            _logger.LogCritical(
                ex,
                "Release shelf activation committed, but the optional layout marker could not be materialized.");
        }
    }

    private void NotifyPostActivationCheckpoint(PromotionCheckpoint checkpoint)
    {
        try
        {
            _promotionCheckpoint?.Invoke(checkpoint);
        }
        catch (Exception ex)
        {
            _logger.LogWarning(
                ex,
                "Post-activation release promotion checkpoint {Checkpoint} failed; publication remains committed.",
                checkpoint);
        }
    }

    private void TryUpdateCompatibilityMirrors(string generationRoot, string downloadsRoot)
    {
        try
        {
            foreach (string directoryName in new[] { "files", "startup-smoke", "signing", "proof", "release-evidence" })
            {
                string source = Path.Combine(generationRoot, directoryName);
                string destination = Path.Combine(downloadsRoot, directoryName);
                if (Directory.Exists(source))
                {
                    MirrorDirectoryContents(source, destination, CancellationToken.None);
                }
                else if (Directory.Exists(destination))
                {
                    Directory.Delete(destination, recursive: true);
                }
            }

            foreach (string manifestName in new[] { CanonicalManifestName, CompatibilityManifestName })
            {
                string destination = Path.Combine(downloadsRoot, manifestName);
                if (File.Exists(destination))
                {
                    File.Delete(destination);
                }

                File.Copy(Path.Combine(generationRoot, manifestName), destination);
                MakeCompatibilityMirrorFileWritable(destination);
            }

            string generationAurPackages = Path.Combine(generationRoot, "aur-packages.json");
            string mirrorAurPackages = Path.Combine(downloadsRoot, "aur-packages.json");
            if (File.Exists(mirrorAurPackages))
            {
                File.Delete(mirrorAurPackages);
            }

            if (File.Exists(generationAurPackages))
            {
                File.Copy(generationAurPackages, mirrorAurPackages);
                MakeCompatibilityMirrorFileWritable(mirrorAurPackages);
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(
                ex,
                "Release shelf generation activated, but non-authoritative top-level compatibility mirrors could not be refreshed.");
        }
    }

    private static void MakeCompatibilityMirrorFileWritable(string path)
    {
        if (OperatingSystem.IsWindows())
        {
            File.SetAttributes(path, File.GetAttributes(path) & ~FileAttributes.ReadOnly);
            return;
        }

        File.SetUnixFileMode(
            path,
            UnixFileMode.UserRead
            | UnixFileMode.UserWrite
            | UnixFileMode.GroupRead
            | UnixFileMode.OtherRead);
    }

    private static void FlushTreeDurably(string root)
    {
        foreach (string filePath in EnumerateRegularFilesWithoutLinks(root))
        {
            using var stream = new FileStream(filePath, FileMode.Open, FileAccess.ReadWrite, FileShare.Read);
            stream.Flush(flushToDisk: true);
        }

        foreach (string directory in Directory.EnumerateDirectories(root, "*", SearchOption.AllDirectories)
                     .OrderByDescending(static path => path.Length))
        {
            FlushDirectoryDurably(directory);
        }

        FlushDirectoryDurably(root);
    }

    private static IEnumerable<string> EnumerateRegularFilesWithoutLinks(string root)
    {
        var pending = new Stack<string>();
        pending.Push(Path.GetFullPath(root));
        while (pending.Count > 0)
        {
            string directory = pending.Pop();
            if (new DirectoryInfo(directory).LinkTarget is not null)
            {
                throw new InvalidDataException("release shelf generation must not contain symbolic links.");
            }

            foreach (string entry in Directory.EnumerateFileSystemEntries(directory))
            {
                FileAttributes attributes = File.GetAttributes(entry);
                if ((attributes & FileAttributes.ReparsePoint) != 0)
                {
                    throw new InvalidDataException("release shelf generation must not contain symbolic links.");
                }

                if ((attributes & FileAttributes.Directory) != 0)
                {
                    pending.Push(entry);
                }
                else
                {
                    yield return entry;
                }
            }
        }
    }

    private static void MakeGenerationReadOnly(string generationRoot)
    {
        if (OperatingSystem.IsWindows())
        {
            foreach (string filePath in EnumerateRegularFilesWithoutLinks(generationRoot))
            {
                File.SetAttributes(filePath, File.GetAttributes(filePath) | FileAttributes.ReadOnly);
            }

            return;
        }

        UnixFileMode fileMode = UnixFileMode.UserRead | UnixFileMode.GroupRead | UnixFileMode.OtherRead;
        UnixFileMode directoryMode = fileMode
                                     | UnixFileMode.UserExecute
                                     | UnixFileMode.GroupExecute
                                     | UnixFileMode.OtherExecute;
        foreach (string filePath in EnumerateRegularFilesWithoutLinks(generationRoot))
        {
            File.SetUnixFileMode(filePath, fileMode);
        }

        foreach (string directory in Directory.EnumerateDirectories(generationRoot, "*", SearchOption.AllDirectories)
                     .OrderByDescending(static path => path.Length))
        {
            File.SetUnixFileMode(directory, directoryMode);
        }

        File.SetUnixFileMode(generationRoot, directoryMode);
    }

    private static void FlushDirectoryDurably(string path)
    {
        if (OperatingSystem.IsWindows())
        {
            return;
        }

        int descriptor = NativeOpen(path, 0);
        if (descriptor < 0)
        {
            throw new IOException(
                $"could not open directory for fsync: {path}",
                new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error()));
        }

        try
        {
            if (NativeFsync(descriptor) != 0)
            {
                throw new IOException(
                    $"could not fsync directory: {path}",
                    new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error()));
            }
        }
        finally
        {
            _ = NativeClose(descriptor);
        }
    }

    private static void TryDeleteFile(string path)
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
            // Best effort for a non-authoritative temporary file.
        }
    }

    [DllImport("libc", EntryPoint = "open", SetLastError = true)]
    private static extern int NativeOpen(string path, int flags);

    [DllImport("libc", EntryPoint = "fsync", SetLastError = true)]
    private static extern int NativeFsync(int fileDescriptor);

    [DllImport("libc", EntryPoint = "close", SetLastError = true)]
    private static extern int NativeClose(int fileDescriptor);

    private void NotifyCheckpoint(PromotionCheckpoint checkpoint)
        => _promotionCheckpoint?.Invoke(checkpoint);

    private void TryDeletePromotionTransaction(string transactionRoot)
    {
        try
        {
            if (Directory.Exists(transactionRoot))
            {
                Directory.Delete(transactionRoot, recursive: true);
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Release bundle promotion transaction cleanup failed for {TransactionRoot}.", transactionRoot);
        }
    }

    private static void CopyDirectoryContents(
        string sourceRoot,
        string destinationRoot,
        CancellationToken cancellationToken)
    {
        Directory.CreateDirectory(destinationRoot);
        foreach (string sourcePath in EnumerateRegularFilesWithoutLinks(sourceRoot))
        {
            cancellationToken.ThrowIfCancellationRequested();
            string relativePath = Path.GetRelativePath(sourceRoot, sourcePath);
            string destinationPath = Path.Combine(destinationRoot, relativePath);
            string? destinationDirectory = Path.GetDirectoryName(destinationPath);
            if (!string.IsNullOrWhiteSpace(destinationDirectory))
            {
                Directory.CreateDirectory(destinationDirectory);
            }

            using FileStream source = File.OpenRead(sourcePath);
            using var destination = new FileStream(
                destinationPath,
                FileMode.Create,
                FileAccess.Write,
                FileShare.None);
            source.CopyTo(destination);
        }
    }

    private static void MirrorDirectoryContents(
        string sourceRoot,
        string destinationRoot,
        CancellationToken cancellationToken)
    {
        if (Directory.Exists(destinationRoot))
        {
            Directory.Delete(destinationRoot, recursive: true);
        }

        CopyDirectoryContents(sourceRoot, destinationRoot, cancellationToken);
    }

    private static string ResolveBundleRoot(string extractRoot)
    {
        string directCompatibilityManifest = Path.Combine(extractRoot, CompatibilityManifestName);
        string directCanonicalManifest = Path.Combine(extractRoot, CanonicalManifestName);
        if (File.Exists(directCompatibilityManifest) && File.Exists(directCanonicalManifest))
        {
            return extractRoot;
        }

        string[] children = Directory.GetDirectories(extractRoot);
        if (children.Length == 1)
        {
            string childCompatibilityManifest = Path.Combine(children[0], CompatibilityManifestName);
            string childCanonicalManifest = Path.Combine(children[0], CanonicalManifestName);
            if (File.Exists(childCompatibilityManifest) && File.Exists(childCanonicalManifest))
            {
                return children[0];
            }
        }

        return extractRoot;
    }

    private static string RequireSingleFile(string root, string fileName)
    {
        string[] matches = Directory.GetFiles(root, fileName, SearchOption.AllDirectories);
        return matches.Length switch
        {
            0 => throw new InvalidDataException($"bundle is missing required file: {fileName}"),
            > 1 => throw new InvalidDataException($"bundle contains more than one {fileName}; expected a single manifest"),
            _ => matches[0]
        };
    }

    private static string? ResolveOptionalFile(string root, string relativePath)
    {
        string directPath = Path.Combine(root, relativePath.Replace('/', Path.DirectorySeparatorChar));
        if (File.Exists(directPath))
        {
            return directPath;
        }

        string fileName = Path.GetFileName(relativePath);
        return Directory.GetFiles(root, fileName, SearchOption.AllDirectories).FirstOrDefault();
    }

    private static string RequireSiblingDirectory(string path, string siblingName)
    {
        string? root = Path.GetDirectoryName(path);
        if (root is null)
        {
            throw new InvalidDataException($"cannot resolve sibling directory {siblingName} for {path}");
        }

        string siblingPath = Path.Combine(root, siblingName);
        if (!Directory.Exists(siblingPath))
        {
            throw new InvalidDataException($"bundle is missing required directory: {siblingName}");
        }

        return siblingPath;
    }

    private static string? ResolveSiblingDirectory(string path, string siblingName)
    {
        string? root = Path.GetDirectoryName(path);
        if (root is null)
        {
            return null;
        }

        string siblingPath = Path.Combine(root, siblingName);
        return Directory.Exists(siblingPath) ? siblingPath : null;
    }

    private static PublicReleaseManifestDto LoadCompatibilityManifest(string manifestPath)
        => LoadCompatibilityManifest(
            ReadManifestBytes(manifestPath, CompatibilityManifestName),
            manifestPath);

    private static PublicReleaseManifestDto LoadCompatibilityManifest(
        byte[] manifestBytes,
        string manifestPath)
    {
        CompatibilityManifestPayload? parsed = JsonSerializer.Deserialize<CompatibilityManifestPayload>(
            DecodeManifestUtf8(manifestBytes, manifestPath),
            JsonOptions);
        PublicReleaseManifestDto? manifest = parsed is null
            ? null
            : new PublicReleaseManifestDto(
                Version: parsed.Version ?? "unpublished",
                Channel: parsed.Channel ?? parsed.ChannelId ?? "preview",
                PublishedAt: parsed.PublishedAt ?? DateTimeOffset.UtcNow,
                Downloads: parsed.Downloads ?? [],
                Source: parsed.Source ?? "manifest",
                Status: parsed.Status ?? "published",
                Message: parsed.Message,
                HasFallbackSource: parsed.HasFallbackSource,
                RolloutState: parsed.RolloutState,
                RolloutReason: parsed.RolloutReason,
                SupportabilityState: parsed.SupportabilityState,
                SupportabilitySummary: parsed.SupportabilitySummary,
                KnownIssueSummary: parsed.KnownIssueSummary,
                FixAvailabilitySummary: parsed.FixAvailabilitySummary,
                ProofStatus: parsed.ReleaseProof?.Status,
                ProofGeneratedAt: parsed.ReleaseProof?.GeneratedAt,
                ProofBaseUrl: parsed.ReleaseProof?.BaseUrl,
                ProofJourneys: parsed.ReleaseProof?.JourneysPassed,
                ProofRoutes: parsed.ReleaseProof?.ProofRoutes,
                GeneratedAt: parsed.GeneratedAt ?? parsed.GeneratedAtAlias,
                ContractName: string.IsNullOrWhiteSpace(parsed.ContractName)
                    ? parsed.ContractNameAlias
                    : parsed.ContractName)
            {
                ProofUiLocalizationReleaseGate = parsed.ReleaseProof?.UiLocalizationReleaseGate is JsonElement uiLocalizationReleaseGate
                    ? uiLocalizationReleaseGate.Clone()
                    : null,
                ProofFlagshipReadiness = parsed.ReleaseProof?.FlagshipReadiness is JsonElement flagshipReadiness
                    ? flagshipReadiness.Clone()
                    : null,
                DesktopTupleCoverage = parsed.DesktopTupleCoverage is JsonElement desktopTupleCoverage
                    ? desktopTupleCoverage.Clone()
                    : null,
                RegistryBoundaryCoverage = parsed.RegistryBoundaryCoverage is JsonElement registryBoundaryCoverage
                    ? registryBoundaryCoverage.Clone()
                    : null,
                PublicTrustMetrics = parsed.PublicTrustMetrics is JsonElement publicTrustMetrics
                    ? publicTrustMetrics.Clone()
                    : null
            };
        return manifest ?? throw new InvalidDataException($"compatibility release manifest could not be parsed: {manifestPath}");
    }

    private static JsonObject LoadJsonObject(string path)
        => LoadJsonObject(ReadManifestBytes(path, Path.GetFileName(path)), path);

    private static JsonObject LoadJsonObject(byte[] bytes, string path)
    {
        JsonNode? parsed = JsonNode.Parse(DecodeManifestUtf8(bytes, path));
        return parsed?.AsObject() ?? throw new InvalidDataException($"json object could not be parsed: {path}");
    }

    private static byte[] ReadManifestBytes(string path, string label)
    {
        try
        {
            using var stream = new FileStream(
                path,
                FileMode.Open,
                FileAccess.Read,
                FileShare.Read,
                bufferSize: 64 * 1024,
                FileOptions.SequentialScan);
            long length = stream.Length;
            if (length <= 0 || length > ReleaseShelfGenerationStore.MaximumManifestBytes)
            {
                throw new InvalidDataException($"{label} exceeds the permitted manifest byte length.");
            }

            byte[] bytes = new byte[checked((int)length)];
            stream.ReadExactly(bytes);
            if (stream.ReadByte() != -1 || stream.Length != length)
            {
                throw new InvalidDataException($"{label} changed while it was being read.");
            }

            _ = DecodeManifestUtf8(bytes, label);
            return bytes;
        }
        catch (EndOfStreamException exception)
        {
            throw new InvalidDataException($"{label} changed while it was being read.", exception);
        }
    }

    private static string DecodeManifestUtf8(byte[] bytes, string label)
    {
        try
        {
            return new UTF8Encoding(encoderShouldEmitUTF8Identifier: false, throwOnInvalidBytes: true)
                .GetString(bytes);
        }
        catch (DecoderFallbackException exception)
        {
            throw new InvalidDataException($"{label} is not valid UTF-8.", exception);
        }
    }

    private static void ValidateIncomingManifestIdentity(
        JsonObject compatibilityObject,
        PublicReleaseManifestDto compatibilityManifest,
        JsonObject canonicalManifest,
        bool allowReviewRequiredProof = false,
        bool releaseProofAlreadyValidatedBeforeGenerationBinding = false)
    {
        string compatibilityVersion = (GetJsonString(compatibilityObject["version"]) ?? string.Empty).Trim();
        string canonicalVersion = (GetJsonString(canonicalManifest["version"]) ?? string.Empty).Trim();
        RequireMatchingManifestValue("version", compatibilityVersion, canonicalVersion, normalize: false);

        string compatibilityChannel = NormalizeToken(
            GetJsonString(compatibilityObject["channel"])
            ?? GetJsonString(compatibilityObject["channelId"]));
        string compatibilityChannelId = NormalizeToken(GetJsonString(compatibilityObject["channelId"]));
        if (!string.IsNullOrWhiteSpace(compatibilityChannelId)
            && !string.Equals(compatibilityChannel, compatibilityChannelId, StringComparison.Ordinal))
        {
            throw new InvalidDataException("releases.json channel and channelId disagree.");
        }

        string canonicalChannel = NormalizeToken(
            GetJsonString(canonicalManifest["channel"])
            ?? GetJsonString(canonicalManifest["channelId"]));
        string canonicalChannelId = NormalizeToken(GetJsonString(canonicalManifest["channelId"]));
        if (!string.IsNullOrWhiteSpace(canonicalChannelId)
            && !string.Equals(canonicalChannel, canonicalChannelId, StringComparison.Ordinal))
        {
            throw new InvalidDataException("RELEASE_CHANNEL.generated.json channel and channelId disagree.");
        }

        RequireMatchingManifestValue("channel", compatibilityChannel, canonicalChannel, normalize: true);

        string compatibilityStatus = NormalizeToken(GetJsonString(compatibilityObject["status"]));
        string canonicalStatus = NormalizeToken(GetJsonString(canonicalManifest["status"]));
        RequireMatchingManifestValue("status", compatibilityStatus, canonicalStatus, normalize: true);

        if (!TryGetJsonDateTimeOffset(compatibilityObject["publishedAt"]).HasValue
            || !TryGetJsonDateTimeOffset(canonicalManifest["publishedAt"]).HasValue)
        {
            throw new InvalidDataException("bundle manifests must both publish a valid publishedAt timestamp.");
        }

        DateTimeOffset compatibilityPublishedAt = TryGetJsonDateTimeOffset(compatibilityObject["publishedAt"])!.Value;
        DateTimeOffset canonicalPublishedAt = TryGetJsonDateTimeOffset(canonicalManifest["publishedAt"])!.Value;
        if (compatibilityPublishedAt.ToUniversalTime() != canonicalPublishedAt.ToUniversalTime()
            || compatibilityManifest.PublishedAt.ToUniversalTime() != compatibilityPublishedAt.ToUniversalTime())
        {
            throw new InvalidDataException("bundle manifests disagree about publishedAt.");
        }

        JsonObject? compatibilityProof = compatibilityObject["releaseProof"] as JsonObject;
        JsonObject? canonicalProof = canonicalManifest["releaseProof"] as JsonObject;
        string compatibilityProofStatus = NormalizeReleaseProofStatus(GetJsonString(compatibilityProof?["status"]));
        string canonicalProofStatus = NormalizeReleaseProofStatus(GetJsonString(canonicalProof?["status"]));
        if ((compatibilityProof is null) != (canonicalProof is null)
            || (compatibilityProof is not null && string.IsNullOrWhiteSpace(compatibilityProofStatus))
            || (canonicalProof is not null && string.IsNullOrWhiteSpace(canonicalProofStatus))
            || !string.Equals(compatibilityProofStatus, canonicalProofStatus, StringComparison.Ordinal))
        {
            throw new InvalidDataException("bundle manifests disagree about normalized releaseProof.status.");
        }

        if (compatibilityProof is null
            || canonicalProof is null
            || !ReleaseProofsAreSemanticallyEqual(compatibilityProof, canonicalProof))
        {
            throw new InvalidDataException("bundle manifests must contain semantically identical releaseProof evidence.");
        }

        JsonObject proofForTrust = canonicalProof;
        if (allowReviewRequiredProof
            && string.Equals(canonicalProofStatus, "review_required", StringComparison.Ordinal))
        {
            RequireReviewGatedSerializedProof(compatibilityObject, canonicalManifest);
            proofForTrust = canonicalProof.DeepClone().AsObject();
            proofForTrust["status"] = "passed";
        }

        if (releaseProofAlreadyValidatedBeforeGenerationBinding)
        {
            return;
        }

        ReleaseProofTrustEvaluation proofTrust = ReleaseProofTrustEvaluator.Validate(proofForTrust);
        if (!proofTrust.IsValid)
        {
            throw new InvalidDataException($"bundle releaseProof is not Registry-compatible: {proofTrust.Reason}.");
        }
    }

    private static bool ReleaseProofsAreSemanticallyEqual(
        JsonObject compatibilityProof,
        JsonObject canonicalProof)
    {
        JsonObject normalizedCompatibility = compatibilityProof.DeepClone().AsObject();
        JsonObject normalizedCanonical = canonicalProof.DeepClone().AsObject();
        if (!NormalizeProofTimestamp(normalizedCompatibility)
            || !NormalizeProofTimestamp(normalizedCanonical))
        {
            return false;
        }

        return JsonNode.DeepEquals(normalizedCompatibility, normalizedCanonical);
    }

    private static void ValidatePassedReleaseProofPublicationWindow(
        PublicReleaseManifestDto manifest)
    {
        if (!string.Equals(
                NormalizeReleaseProofStatus(manifest.ProofStatus),
                "passed",
                StringComparison.Ordinal))
        {
            return;
        }

        DateTimeOffset generatedAt = manifest.ProofGeneratedAt
            ?? throw new InvalidDataException("passed releaseProof must expose generatedAt.");
        TimeSpan publicationLag = manifest.PublishedAt.ToUniversalTime() - generatedAt.ToUniversalTime();
        if (publicationLag > MaximumReleaseProofPublicationLag
            || publicationLag < -MaximumReleaseProofPublicationClockSkew)
        {
            throw new InvalidDataException(
                "passed releaseProof falls outside the permitted publication window; Registry must review-gate it before upload.");
        }
    }

    private static bool NormalizeProofTimestamp(JsonObject proof)
    {
        DateTimeOffset? generatedAt = TryGetJsonDateTimeOffset(proof["generatedAt"]);
        if (generatedAt is null)
        {
            return false;
        }

        proof["generatedAt"] = generatedAt.Value
            .ToUniversalTime()
            .ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture);
        return true;
    }

    private static void RequireReviewGatedSerializedProof(
        JsonObject compatibilityManifest,
        JsonObject canonicalManifest)
    {
        foreach ((string name, JsonObject manifest) in new[]
                 {
                     ("releases.json", compatibilityManifest),
                     ("RELEASE_CHANNEL.generated.json", canonicalManifest)
                 })
        {
            if (!string.Equals(
                    NormalizeToken(GetJsonString(manifest["supportabilityState"])),
                    "review_required",
                    StringComparison.Ordinal)
                || NormalizeToken(GetJsonString(manifest["rolloutState"])) is not
                    ("public_release_review_required" or "coverage_incomplete" or "blocked"))
            {
                throw new InvalidDataException(
                    $"{name} may publish releaseProof.status='review_required' only with a review-gated release posture.");
            }
        }
    }

    private static void RequireMatchingManifestValue(
        string fieldName,
        string compatibilityValue,
        string canonicalValue,
        bool normalize)
    {
        if (string.IsNullOrWhiteSpace(compatibilityValue) || string.IsNullOrWhiteSpace(canonicalValue))
        {
            throw new InvalidDataException($"bundle manifests must both publish {fieldName}.");
        }

        StringComparison comparison = normalize
            ? StringComparison.OrdinalIgnoreCase
            : StringComparison.Ordinal;
        if (!string.Equals(compatibilityValue, canonicalValue, comparison))
        {
            throw new InvalidDataException($"bundle manifests disagree about {fieldName}.");
        }
    }

    private static IReadOnlyList<CanonicalArtifactRecord> LoadCanonicalArtifacts(JsonObject manifest)
    {
        JsonNode? artifactsNode = manifest["artifacts"];
        if (artifactsNode is not JsonArray artifactsArray)
        {
            throw new InvalidDataException("canonical release manifest is missing artifacts.");
        }

        List<CanonicalArtifactRecord> artifacts = new(artifactsArray.Count);
        foreach (JsonNode? artifactNode in artifactsArray)
        {
            CanonicalArtifactRecord? artifact = artifactNode?.Deserialize<CanonicalArtifactRecord>(JsonOptions);
            if (artifact is null || string.IsNullOrWhiteSpace(artifact.ArtifactId))
            {
                throw new InvalidDataException("canonical release manifest contains an invalid artifact row.");
            }

            artifacts.Add(artifact);
        }

        return artifacts;
    }

    private static void ValidateRegistryAuthoredManifestPair(
        JsonObject compatibility,
        JsonObject canonical,
        PublicReleaseManifestDto compatibilityManifest,
        IReadOnlyList<CanonicalArtifactRecord> canonicalArtifacts)
    {
        RequireRegistryContract(compatibility, CompatibilityManifestName);
        RequireRegistryContract(canonical, CanonicalManifestName);
        if (!string.Equals(
                NormalizeToken(GetJsonString(compatibility["source"])),
                "registry",
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"{CompatibilityManifestName} must identify Registry as its source.");
        }

        string canonicalVersion = RequireAliasString(
            canonical,
            "version",
            "releaseVersion",
            CanonicalManifestName);
        string canonicalChannel = RequireAliasString(
            canonical,
            "channel",
            "channelId",
            CanonicalManifestName);
        RequireEqual(compatibilityManifest.Version, canonicalVersion, "release version");
        RequireEqual(
            compatibilityManifest.Channel,
            canonicalChannel,
            "release channel projection");
        RequireEqual(
            NormalizeToken(compatibilityManifest.Status),
            NormalizeToken(GetJsonString(canonical["status"])),
            "publication status");

        DateTimeOffset canonicalPublishedAt = RequireTimestamp(
            canonical,
            "publishedAt",
            CanonicalManifestName);
        if (canonicalPublishedAt.ToUniversalTime() != compatibilityManifest.PublishedAt.ToUniversalTime())
        {
            throw new InvalidDataException(
                "Registry canonical and compatibility manifests disagree about publishedAt.");
        }

        foreach (string fieldName in new[]
                 {
                     "rolloutState",
                     "rolloutReason",
                     "supportabilityState",
                     "supportabilitySummary",
                     "knownIssueSummary",
                     "fixAvailabilitySummary"
                 })
        {
            RequireEqual(
                GetJsonString(compatibility[fieldName]),
                GetJsonString(canonical[fieldName]),
                fieldName);
        }

        RequireEqualJsonProjection(
            compatibility["releaseProof"],
            canonical["releaseProof"],
            "releaseProof");
        RequireEqualJsonProjection(
            compatibility["desktopTupleCoverage"],
            canonical["desktopTupleCoverage"],
            "desktopTupleCoverage");
        ValidateRegistryArtifactProjection(compatibility, canonical);
        ValidateCanonicalPlatformFloor(canonical, canonicalArtifacts);
    }

    private static void RequireRegistryContract(JsonObject manifest, string label)
    {
        string contractName = GetJsonString(manifest["contractName"]) ?? string.Empty;
        string contractNameAlias = GetJsonString(manifest["contract_name"]) ?? string.Empty;
        if (!string.Equals(contractName, RegistryContractName, StringComparison.Ordinal)
            || !string.Equals(contractNameAlias, RegistryContractName, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"{label} must be materialized by {RegistryContractName} and preserve both contract aliases.");
        }
    }

    private static string RequireAliasString(
        JsonObject source,
        string firstName,
        string secondName,
        string label)
    {
        string first = GetJsonString(source[firstName])?.Trim() ?? string.Empty;
        string second = GetJsonString(source[secondName])?.Trim() ?? string.Empty;
        if (first.Length == 0 || second.Length == 0 || !string.Equals(first, second, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"{label} must preserve equal non-empty {firstName}/{secondName} aliases.");
        }

        return first;
    }

    private static DateTimeOffset RequireTimestamp(JsonObject source, string propertyName, string label)
    {
        string raw = GetJsonString(source[propertyName])?.Trim() ?? string.Empty;
        if (!DateTimeOffset.TryParse(
                raw,
                CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal,
                out DateTimeOffset parsed))
        {
            throw new InvalidDataException($"{label} {propertyName} must be an ISO-8601 timestamp.");
        }

        return parsed;
    }

    private static void RequireEqual(string? left, string? right, string fieldName)
    {
        if (!string.Equals(left?.Trim(), right?.Trim(), StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"Registry canonical and compatibility manifests disagree about {fieldName}.");
        }
    }

    private static void RequireEqualJsonProjection(JsonNode? left, JsonNode? right, string fieldName)
    {
        if (left is null || right is null || !JsonNode.DeepEquals(left, right))
        {
            throw new InvalidDataException(
                $"Registry canonical and compatibility manifests disagree about {fieldName}.");
        }
    }

    private static void ValidateRegistryArtifactProjection(JsonObject compatibility, JsonObject canonical)
    {
        if (compatibility["downloads"] is not JsonArray downloads
            || canonical["artifacts"] is not JsonArray artifacts)
        {
            throw new InvalidDataException(
                "Registry manifest pair must contain compatibility downloads and canonical artifacts.");
        }

        Dictionary<string, JsonObject> compatibilityById = IndexArtifactRows(
            downloads,
            CompatibilityManifestName);
        Dictionary<string, JsonObject> canonicalById = IndexArtifactRows(
            artifacts,
            CanonicalManifestName);
        if (!compatibilityById.Keys.Order(StringComparer.Ordinal).SequenceEqual(
                canonicalById.Keys.Order(StringComparer.Ordinal),
                StringComparer.Ordinal))
        {
            throw new InvalidDataException(
                "Registry canonical and compatibility manifests expose different artifact ids.");
        }

        foreach ((string artifactId, JsonObject canonicalArtifact) in canonicalById)
        {
            JsonObject compatibilityArtifact = compatibilityById[artifactId];
            RequireArtifactFieldEqual(canonicalArtifact, compatibilityArtifact, "head", artifactId);
            RequireArtifactFieldEqual(canonicalArtifact, compatibilityArtifact, "platform", artifactId);
            RequireArtifactFieldEqual(canonicalArtifact, compatibilityArtifact, "rid", artifactId);
            RequireArtifactFieldEqual(canonicalArtifact, compatibilityArtifact, "arch", artifactId);
            RequireArtifactFieldEqual(canonicalArtifact, compatibilityArtifact, "kind", artifactId);
            RequireArtifactFieldEqual(canonicalArtifact, compatibilityArtifact, "fileName", artifactId, normalize: false);
            RequireArtifactFieldEqual(canonicalArtifact, compatibilityArtifact, "sha256", artifactId);
            RequireArtifactFieldEqual(canonicalArtifact, compatibilityArtifact, "installAccessClass", artifactId);
            RequireArtifactAliasFieldEqual(
                canonicalArtifact,
                compatibilityArtifact,
                "downloadUrl",
                "url",
                artifactId,
                normalize: false);
            RequireArtifactAliasFieldEqual(
                canonicalArtifact,
                compatibilityArtifact,
                "version",
                "version",
                artifactId,
                normalize: false);
            RequireArtifactAliasFieldEqual(
                canonicalArtifact,
                compatibilityArtifact,
                "channelId",
                "channelId",
                artifactId);
            long canonicalSize = GetJsonInt64(canonicalArtifact["sizeBytes"]);
            long compatibilitySize = GetJsonInt64(compatibilityArtifact["sizeBytes"]);
            if (canonicalSize <= 0 || canonicalSize != compatibilitySize)
            {
                throw new InvalidDataException(
                    $"Registry canonical and compatibility manifests disagree about artifact {artifactId} sizeBytes.");
            }
        }
    }

    private static Dictionary<string, JsonObject> IndexArtifactRows(JsonArray rows, string label)
    {
        var indexed = new Dictionary<string, JsonObject>(StringComparer.Ordinal);
        foreach (JsonObject row in rows.OfType<JsonObject>())
        {
            string artifactId = (GetJsonString(row["artifactId"])
                                 ?? GetJsonString(row["id"])
                                 ?? string.Empty).Trim();
            if (artifactId.Length == 0 || !indexed.TryAdd(artifactId, row))
            {
                throw new InvalidDataException($"{label} contains a missing or duplicate artifact id.");
            }
        }

        if (indexed.Count != rows.Count)
        {
            throw new InvalidDataException($"{label} contains a non-object artifact row.");
        }

        return indexed;
    }

    private static void RequireArtifactFieldEqual(
        JsonObject canonical,
        JsonObject compatibility,
        string fieldName,
        string artifactId,
        bool normalize = true)
        => RequireArtifactAliasFieldEqual(
            canonical,
            compatibility,
            fieldName,
            fieldName,
            artifactId,
            normalize);

    private static void RequireArtifactAliasFieldEqual(
        JsonObject canonical,
        JsonObject compatibility,
        string canonicalFieldName,
        string compatibilityFieldName,
        string artifactId,
        bool normalize = true)
    {
        string canonicalValue = GetJsonString(canonical[canonicalFieldName])?.Trim() ?? string.Empty;
        string compatibilityValue = GetJsonString(compatibility[compatibilityFieldName])?.Trim() ?? string.Empty;
        if (normalize)
        {
            canonicalValue = NormalizeToken(canonicalValue);
            compatibilityValue = NormalizeToken(compatibilityValue);
        }

        if (canonicalValue.Length == 0
            || !string.Equals(canonicalValue, compatibilityValue, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"Registry canonical and compatibility manifests disagree about artifact {artifactId} {canonicalFieldName}.");
        }
    }

    private static void ValidateCanonicalPlatformFloor(
        JsonObject canonical,
        IReadOnlyList<CanonicalArtifactRecord> canonicalArtifacts)
    {
        JsonObject coverage = canonical["desktopTupleCoverage"] as JsonObject
            ?? throw new InvalidDataException(
                $"{CanonicalManifestName} must contain Registry desktopTupleCoverage.");
        RequireExactStringArray(
            coverage,
            "requiredDesktopPlatforms",
            RequiredDesktopPlatforms,
            "canonical desktop platform floor");
        RequireExactStringArray(
            coverage,
            "requiredDesktopHeads",
            RequiredDesktopHeads,
            "canonical desktop head floor");
        RequireExactStringArray(
            coverage,
            "requiredDesktopPlatformHeadRidTuples",
            RequiredDesktopPlatformHeadRidTuples,
            "canonical desktop platform/head/RID floor");

        HashSet<string> promotedPlatforms = new(StringComparer.Ordinal);
        HashSet<string> promotedHeads = new(StringComparer.Ordinal);
        HashSet<string> promotedPairs = new(StringComparer.Ordinal);
        HashSet<string> promotedRequiredTuples = new(StringComparer.Ordinal);
        HashSet<string> promotedAllTuples = new(StringComparer.Ordinal);
        HashSet<string> promotedInstallerTupleIds = new(StringComparer.Ordinal);
        foreach (CanonicalArtifactRecord artifact in canonicalArtifacts)
        {
            string platform = NormalizePlatform(artifact.Platform);
            string head = NormalizeToken(artifact.Head);
            string rid = NormalizeToken(artifact.Rid);
            if (rid.Length == 0)
            {
                rid = RidForPlatformAndArch(platform, NormalizeToken(artifact.Arch));
            }

            if (!RequiredDesktopPlatforms.Contains(platform, StringComparer.Ordinal)
                || !IsPromotedDesktopInstaller(artifact, platform)
                || head.Length == 0
                || rid.Length == 0)
            {
                continue;
            }

            promotedPlatforms.Add(platform);
            promotedHeads.Add(head);
            promotedPairs.Add($"{head}:{platform}");
            promotedAllTuples.Add($"{head}:{rid}:{platform}");
            promotedInstallerTupleIds.Add($"{head}:{platform}:{rid}");
            if (RequiredDesktopHeads.Contains(head, StringComparer.Ordinal))
            {
                promotedRequiredTuples.Add($"{head}:{rid}:{platform}");
            }
        }

        string[] missingPlatforms = RequiredDesktopPlatforms
            .Where(platform => !promotedPlatforms.Contains(platform))
            .ToArray();
        string[] missingHeads = RequiredDesktopHeads
            .Where(head => !promotedHeads.Contains(head))
            .ToArray();
        string[] missingPairs = RequiredDesktopPlatforms
            .SelectMany(platform => RequiredDesktopHeads.Select(head => $"{head}:{platform}"))
            .Where(pair => !promotedPairs.Contains(pair))
            .ToArray();
        string[] missingTuples = RequiredDesktopPlatformHeadRidTuples
            .Where(tuple => !promotedRequiredTuples.Contains(tuple))
            .ToArray();

        RequireExactStringArray(coverage, "missingRequiredPlatforms", missingPlatforms, "missing platform truth");
        RequireExactStringArray(coverage, "missingRequiredHeads", missingHeads, "missing head truth");
        RequireExactStringArray(coverage, "missingRequiredPlatformHeadPairs", missingPairs, "missing platform/head truth");
        RequireExactStringArray(coverage, "missingRequiredPlatformHeadRidTuples", missingTuples, "missing platform/head/RID truth");
        RequireExactStringArray(
            coverage,
            "promotedPlatformHeadRidTuples",
            promotedAllTuples.Order(StringComparer.Ordinal).ToArray(),
            "promoted platform/head/RID truth");

        string[] reportedInstallerTupleIds = ReadObjectStringArray(
                coverage,
                "promotedInstallerTuples",
                "tupleId")
            .Order(StringComparer.Ordinal)
            .ToArray();
        if (!reportedInstallerTupleIds.SequenceEqual(
                promotedInstallerTupleIds.Order(StringComparer.Ordinal),
                StringComparer.Ordinal))
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} desktopTupleCoverage.promotedInstallerTuples disagrees with Registry artifacts.");
        }

        bool expectedComplete = missingTuples.Length == 0;
        if (!TryGetJsonBoolean(coverage["complete"], out bool reportedComplete)
            || reportedComplete != expectedComplete)
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} desktopTupleCoverage.complete disagrees with the canonical platform floor.");
        }

        ValidateCanonicalPostureFloors(canonical, expectedComplete);
    }

    private static bool IsPromotedDesktopInstaller(CanonicalArtifactRecord artifact, string platform)
    {
        if (NormalizeToken(artifact.Status) == "revoked"
            || NormalizeToken(artifact.RolloutState) == "revoked"
            || NormalizeToken(artifact.RevokeState) == "revoked")
        {
            return false;
        }

        string kind = NormalizeToken(artifact.Kind);
        return platform == "macos"
            ? kind is "installer" or "dmg" or "pkg"
            : kind == "installer";
    }

    private static string RidForPlatformAndArch(string platform, string arch)
        => (platform, arch) switch
        {
            ("linux", "arm64") => "linux-arm64",
            ("linux", _) => "linux-x64",
            ("windows", "arm64") => "win-arm64",
            ("windows", _) => "win-x64",
            ("macos", "x64") => "osx-x64",
            ("macos", _) => "osx-arm64",
            _ => string.Empty
        };

    private static void ValidateCanonicalPostureFloors(JsonObject canonical, bool desktopCoverageComplete)
    {
        string status = NormalizeToken(GetJsonString(canonical["status"]));
        if (status != "published")
        {
            return;
        }

        string rolloutState = NormalizeToken(GetJsonString(canonical["rolloutState"]));
        string supportabilityState = NormalizeToken(GetJsonString(canonical["supportabilityState"]));
        JsonObject publicTrustMetrics = canonical["publicTrustMetrics"] as JsonObject
            ?? throw new InvalidDataException($"{CanonicalManifestName} must contain publicTrustMetrics.");
        JsonObject trustReleaseChannel = publicTrustMetrics["releaseChannel"] as JsonObject
            ?? throw new InvalidDataException(
                $"{CanonicalManifestName} must contain publicTrustMetrics.releaseChannel.");
        JsonObject proofFreshness = publicTrustMetrics["proofFreshness"] as JsonObject
            ?? throw new InvalidDataException(
                $"{CanonicalManifestName} must contain publicTrustMetrics.proofFreshness.");
        JsonObject registryBoundary = canonical["registryBoundaryCoverage"] as JsonObject
            ?? throw new InvalidDataException($"{CanonicalManifestName} must contain registryBoundaryCoverage.");
        if (NormalizeToken(GetJsonString(registryBoundary["owner"])) != "chummer6-hub-registry"
            || NormalizeToken(GetJsonString(registryBoundary["status"])) != "closed")
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} registryBoundaryCoverage must be closed and owned by chummer6-hub-registry.");
        }

        JsonObject registryReleaseChannel = registryBoundary["releaseChannel"] as JsonObject
            ?? throw new InvalidDataException(
                $"{CanonicalManifestName} must contain registryBoundaryCoverage.releaseChannel.");

        string trustSupportability = NormalizeToken(GetJsonString(trustReleaseChannel["supportabilityState"]));
        string registrySupportability = NormalizeToken(GetJsonString(registryReleaseChannel["supportabilityState"]));
        if (supportabilityState.Length == 0
            || trustSupportability != supportabilityState
            || registrySupportability != supportabilityState)
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} supportabilityState must agree across Registry truth projections.");
        }

        if (!TryGetJsonBoolean(registryReleaseChannel["desktopTupleComplete"], out bool registryComplete)
            || registryComplete != desktopCoverageComplete)
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} registryBoundaryCoverage.releaseChannel.desktopTupleComplete disagrees with desktopTupleCoverage.");
        }

        if (!desktopCoverageComplete)
        {
            if (rolloutState != "coverage_incomplete" || supportabilityState != "review_required")
            {
                throw new InvalidDataException(
                    $"{CanonicalManifestName} must remain coverage_incomplete/review_required while the canonical desktop floor is incomplete.");
            }

            return;
        }

        string freshnessStatus = NormalizeToken(GetJsonString(proofFreshness["status"]));
        if (freshnessStatus is not "stale" and not "missing")
        {
            return;
        }

        if (rolloutState != "public_release_review_required"
            || supportabilityState != "review_required"
            || NormalizeToken(GetJsonString(trustReleaseChannel["posture"])) != "blocked"
            || NormalizeToken(GetJsonString(registryReleaseChannel["publicTrustPosture"])) != "blocked")
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} stale or missing proof freshness must stay review-required with blocked public trust posture.");
        }

        foreach (string fieldName in new[]
                 {
                     "rolloutReason",
                     "supportabilitySummary",
                     "knownIssueSummary",
                     "fixAvailabilitySummary"
                 })
        {
            if (!(GetJsonString(canonical[fieldName]) ?? string.Empty).Contains(
                    "stale or incomplete proof receipts",
                    StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException(
                    $"{CanonicalManifestName} {fieldName} must explain stale or incomplete proof receipts.");
            }
        }
    }

    private static void RequireExactStringArray(
        JsonObject source,
        string propertyName,
        IReadOnlyList<string> expected,
        string description)
    {
        string[] actual = ReadStringArray(source, propertyName);
        if (!actual.SequenceEqual(expected, StringComparer.Ordinal))
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} desktopTupleCoverage.{propertyName} does not match {description}.");
        }
    }

    private static string[] ReadStringArray(JsonObject source, string propertyName)
    {
        if (source[propertyName] is not JsonArray array)
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} desktopTupleCoverage.{propertyName} must be an array.");
        }

        string[] values = array
            .Select(GetJsonString)
            .Where(static value => value is not null)
            .Select(static value => value!.Trim())
            .ToArray();
        if (values.Length != array.Count || values.Any(static value => value.Length == 0))
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} desktopTupleCoverage.{propertyName} must contain non-empty strings.");
        }

        return values;
    }

    private static string[] ReadObjectStringArray(
        JsonObject source,
        string propertyName,
        string childPropertyName)
    {
        if (source[propertyName] is not JsonArray array)
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} desktopTupleCoverage.{propertyName} must be an array.");
        }

        string[] values = array
            .OfType<JsonObject>()
            .Select(row => GetJsonString(row[childPropertyName])?.Trim() ?? string.Empty)
            .ToArray();
        if (values.Length != array.Count || values.Any(static value => value.Length == 0))
        {
            throw new InvalidDataException(
                $"{CanonicalManifestName} desktopTupleCoverage.{propertyName} contains an invalid row.");
        }

        return values;
    }

    private static bool TryGetJsonBoolean(JsonNode? node, out bool value)
    {
        value = false;
        if (node is JsonValue jsonValue && jsonValue.TryGetValue<bool>(out value))
        {
            return true;
        }

        return bool.TryParse(GetJsonString(node), out value);
    }

    private static long GetJsonInt64(JsonNode? node)
    {
        if (node is JsonValue jsonValue && jsonValue.TryGetValue<long>(out long value))
        {
            return value;
        }

        return long.TryParse(GetJsonString(node), out value) ? value : 0;
    }

    private static void ValidateIncomingBundle(
        PublicReleaseManifestDto compatibilityManifest,
        IReadOnlyList<CanonicalArtifactRecord> canonicalArtifacts,
        string filesRoot,
        string? startupSmokeRoot,
        string? promotionEvidencePath,
        DateTimeOffset evaluatedAtUtc)
    {
        if (compatibilityManifest.Downloads.Count == 0)
        {
            throw new InvalidDataException("bundle contains no downloadable artifacts.");
        }

        ValidateFilesAreManifestBound(filesRoot, compatibilityManifest);

        Dictionary<string, PublicReleaseArtifactDto> compatibilityById = BuildUniqueCompatibilityArtifacts(
            compatibilityManifest.Downloads);
        Dictionary<string, CanonicalArtifactRecord> canonicalById = BuildUniqueCanonicalArtifacts(canonicalArtifacts);
        if (compatibilityById.Count != canonicalById.Count
            || compatibilityById.Keys.Any(artifactId => !canonicalById.ContainsKey(artifactId)))
        {
            throw new InvalidDataException("bundle manifests publish different artifact id sets.");
        }

        foreach ((string artifactId, CanonicalArtifactRecord artifact) in canonicalById)
        {
            PublicReleaseArtifactDto compatibility = compatibilityById[artifactId];
            NormalizedArtifactContract canonicalContract = NormalizeCanonicalArtifactContract(artifact);
            NormalizedArtifactContract compatibilityContract = NormalizeCompatibilityArtifactContract(compatibility);
            if (canonicalContract != compatibilityContract)
            {
                throw new InvalidDataException(
                    $"bundle manifests disagree about delivery/security contract for artifact {artifactId}.");
            }

            ValidateArtifactBytes(filesRoot, canonicalContract, compatibilityManifest.Version);
        }

        List<CanonicalArtifactRecord> installerArtifacts = canonicalArtifacts.Where(IsInstallerArtifact).ToList();
        if (installerArtifacts.Count == 0)
        {
            return;
        }

        if (string.IsNullOrWhiteSpace(startupSmokeRoot) || !Directory.Exists(startupSmokeRoot))
        {
            throw new InvalidDataException("bundle is missing startup-smoke receipts for installer promotion.");
        }

        IReadOnlyList<StartupSmokeReceipt> startupSmokeReceipts = LoadStartupSmokeReceipts(startupSmokeRoot);
        PromotionEvidenceDocument promotionEvidence = LoadPromotionEvidence(promotionEvidencePath);

        foreach (CanonicalArtifactRecord artifact in installerArtifacts)
        {
            ValidateStartupSmokeReceipt(
                artifact,
                startupSmokeReceipts,
                compatibilityManifest.Version,
                compatibilityManifest.Channel,
                evaluatedAtUtc);
            ValidatePromotionEvidence(artifact, promotionEvidence, compatibilityManifest.Channel);
        }
    }

    private static Dictionary<string, PublicReleaseArtifactDto> BuildUniqueCompatibilityArtifacts(
        IReadOnlyList<PublicReleaseArtifactDto> artifacts)
    {
        var byId = new Dictionary<string, PublicReleaseArtifactDto>(StringComparer.OrdinalIgnoreCase);
        foreach (PublicReleaseArtifactDto artifact in artifacts)
        {
            string id = RequireArtifactToken(artifact.Id, "compatibility artifact id");
            if (!byId.TryAdd(id, artifact))
            {
                throw new InvalidDataException($"releases.json contains duplicate artifact id {id}.");
            }
        }

        return byId;
    }

    private static Dictionary<string, CanonicalArtifactRecord> BuildUniqueCanonicalArtifacts(
        IReadOnlyList<CanonicalArtifactRecord> artifacts)
    {
        var byId = new Dictionary<string, CanonicalArtifactRecord>(StringComparer.OrdinalIgnoreCase);
        foreach (CanonicalArtifactRecord artifact in artifacts)
        {
            string id = RequireArtifactToken(artifact.ArtifactId, "canonical artifact id");
            if (!byId.TryAdd(id, artifact))
            {
                throw new InvalidDataException(
                    $"RELEASE_CHANNEL.generated.json contains duplicate artifact id {id}.");
            }
        }

        return byId;
    }

    private static NormalizedArtifactContract NormalizeCanonicalArtifactContract(
        CanonicalArtifactRecord artifact,
        bool requireIncomingUrls = true)
    {
        string artifactId = RequireArtifactToken(artifact.ArtifactId, "canonical artifact id");
        string fileName = RequirePortableArtifactFileName(artifact.FileName, artifactId, "canonical fileName");
        string downloadUrl = requireIncomingUrls
            ? RequireGovernedIncomingArtifactUrl(artifact.DownloadUrl, fileName, artifactId)
            : RequireNonEmptyArtifactUrl(artifact.DownloadUrl, artifactId, "canonical downloadUrl");
        string sha256 = RequireArtifactSha256(artifact.Sha256, artifactId, "canonical artifact");
        long sizeBytes = RequireArtifactSize(artifact.SizeBytes, artifactId, "canonical artifact");
        string platform = NormalizePlatform(RequireArtifactToken(artifact.Platform, "canonical platform"));
        string arch = RequireArtifactToken(artifact.Arch, "canonical arch");
        string rid = RequireArtifactToken(artifact.Rid, "canonical rid");
        string expectedPlatformId = $"{platform}-{arch}";
        string accessClass = RequireInstallAccessClass(artifact.InstallAccessClass, artifactId);
        (string? payloadFileName, string? payloadUrl, string? payloadSha256, long? payloadSizeBytes) =
            NormalizePayloadContract(
                artifact.PayloadFileName,
                artifact.PayloadDownloadUrl,
                artifact.PayloadSha256,
                artifact.PayloadSizeBytes,
                artifactId,
                "canonical",
                requireIncomingUrls);
        return new NormalizedArtifactContract(
            artifactId,
            fileName,
            downloadUrl,
            sha256,
            sizeBytes,
            RequireArtifactToken(artifact.Head, "canonical head"),
            expectedPlatformId,
            RequireArtifactLabel(artifact.PlatformLabel, artifactId, "canonical platformLabel"),
            arch,
            rid,
            RequireArtifactToken(artifact.Kind, "canonical kind"),
            accessClass,
            NormalizeOptionalToken(artifact.InstallerMode),
            payloadFileName,
            payloadUrl,
            payloadSha256,
            payloadSizeBytes);
    }

    private static NormalizedArtifactContract NormalizeCompatibilityArtifactContract(
        PublicReleaseArtifactDto artifact,
        bool requireIncomingUrls = true)
    {
        string artifactId = RequireArtifactToken(artifact.Id, "compatibility artifact id");
        string fileName = RequirePortableArtifactFileName(artifact.FileName, artifactId, "compatibility fileName");
        string downloadUrl = requireIncomingUrls
            ? RequireGovernedIncomingArtifactUrl(artifact.Url, fileName, artifactId)
            : RequireNonEmptyArtifactUrl(artifact.Url, artifactId, "compatibility downloadUrl");
        string sha256 = RequireArtifactSha256(artifact.Sha256, artifactId, "compatibility artifact");
        long sizeBytes = RequireArtifactSize(artifact.SizeBytes, artifactId, "compatibility artifact");
        string platformId = RequireArtifactToken(artifact.PlatformId, "compatibility platformId");
        string arch = RequireArtifactToken(artifact.Arch, "compatibility arch");
        string normalizedPlatformId = $"{NormalizePlatform(platformId)}-{arch}";
        string accessClass = RequireInstallAccessClass(artifact.InstallAccessClass, artifactId);
        (string? payloadFileName, string? payloadUrl, string? payloadSha256, long? payloadSizeBytes) =
            NormalizePayloadContract(
                artifact.PayloadFileName,
                artifact.PayloadDownloadUrl,
                artifact.PayloadSha256,
                artifact.PayloadSizeBytes,
                artifactId,
                "compatibility",
                requireIncomingUrls);
        return new NormalizedArtifactContract(
            artifactId,
            fileName,
            downloadUrl,
            sha256,
            sizeBytes,
            RequireArtifactToken(artifact.Head, "compatibility head"),
            normalizedPlatformId,
            RequireArtifactLabel(artifact.PlatformLabel, artifactId, "compatibility platformLabel"),
            arch,
            RequireArtifactToken(artifact.Rid, "compatibility rid"),
            RequireArtifactToken(artifact.Kind, "compatibility kind"),
            accessClass,
            NormalizeOptionalToken(artifact.InstallerMode),
            payloadFileName,
            payloadUrl,
            payloadSha256,
            payloadSizeBytes);
    }

    private static void ValidateArtifactBytes(
        string filesRoot,
        NormalizedArtifactContract artifact,
        string releaseVersion)
    {
        ValidateBoundFileBytes(
            filesRoot,
            artifact.FileName,
            artifact.Sha256,
            artifact.SizeBytes,
            artifact.ArtifactId,
            "artifact");
        if (artifact.PayloadFileName is not null)
        {
            ValidateBoundFileBytes(
                filesRoot,
                artifact.PayloadFileName,
                artifact.PayloadSha256!,
                artifact.PayloadSizeBytes!.Value,
                artifact.ArtifactId,
                "payload");
            ValidatePayloadSidecar(
                filesRoot,
                artifact,
                releaseVersion,
                allowMutableIncomingUrl: true);
        }
    }

    private static void ValidatePayloadSidecar(
        string filesRoot,
        NormalizedArtifactContract artifact,
        string releaseVersion,
        bool allowMutableIncomingUrl)
        => ValidatePayloadSidecar(
            filesRoot,
            artifact.ArtifactId,
            artifact.FileName,
            artifact.PayloadFileName!,
            artifact.PayloadDownloadUrl,
            artifact.PayloadSha256,
            artifact.PayloadSizeBytes,
            releaseVersion,
            allowMutableIncomingUrl);

    private static void ValidatePayloadSidecar(
        string filesRoot,
        string artifactId,
        string installerFileName,
        string payloadFileName,
        string? payloadDownloadUrl,
        string? payloadSha256,
        long? payloadSizeBytes,
        string releaseVersion,
        bool allowMutableIncomingUrl)
    {
        string sidecarFileName = payloadFileName + ".json";
        string sidecarPath = Path.Combine(filesRoot, sidecarFileName);
        if (!File.Exists(sidecarPath))
        {
            throw new InvalidDataException(
                $"bundle is missing payload metadata file {sidecarFileName} for {artifactId}.");
        }

        EnsureRegularFile(sidecarPath, $"release payload metadata file for {artifactId}");
        var sidecarInfo = new FileInfo(sidecarPath);
        if (sidecarInfo.Length <= 0 || sidecarInfo.Length > 64 * 1024)
        {
            throw new InvalidDataException(
                $"payload metadata size is invalid for {artifactId}.");
        }

        byte[] bytes = File.ReadAllBytes(sidecarPath);
        if (!PayloadSidecarContractValidator.TryValidate(
                bytes,
                installerFileName,
                payloadFileName,
                payloadDownloadUrl,
                payloadSha256,
                payloadSizeBytes,
                releaseVersion,
                allowMutableIncomingUrl,
                out string? failure))
        {
            throw new InvalidDataException(
                $"payload metadata contract is invalid for {artifactId}: {failure}");
        }
    }

    private static void ValidateBoundFileBytes(
        string filesRoot,
        string fileName,
        string sha256,
        long sizeBytes,
        string artifactId,
        string role)
    {
        string filePath = Path.Combine(filesRoot, fileName);
        if (!File.Exists(filePath))
        {
            throw new InvalidDataException(
                $"bundle is missing {role} file {fileName} for {artifactId}.");
        }

        EnsureRegularFile(filePath, $"release {role} file for {artifactId}");
        long actualSize = new FileInfo(filePath).Length;
        if (sizeBytes != actualSize)
        {
            throw new InvalidDataException(
                $"{role} size mismatch for {artifactId}: expected {sizeBytes}, got {actualSize}.");
        }

        string actualSha = Sha256For(filePath);
        if (!string.Equals(sha256, actualSha, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{role} digest mismatch for {artifactId}.");
        }
    }

    private static (string? FileName, string? Url, string? Sha256, long? SizeBytes) NormalizePayloadContract(
        string? fileName,
        string? url,
        string? sha256,
        long? sizeBytes,
        string artifactId,
        string manifest,
        bool requireIncomingUrl = true)
    {
        bool present = !string.IsNullOrWhiteSpace(fileName)
                       || !string.IsNullOrWhiteSpace(url)
                       || !string.IsNullOrWhiteSpace(sha256)
                       || sizeBytes.HasValue;
        if (!present)
        {
            return (null, null, null, null);
        }

        string normalizedFileName = RequirePortableArtifactFileName(
            fileName,
            artifactId,
            $"{manifest} payloadFileName");
        return (
            normalizedFileName,
            requireIncomingUrl
                ? RequireGovernedIncomingArtifactUrl(url, normalizedFileName, artifactId)
                : RequireNonEmptyArtifactUrl(url, artifactId, $"{manifest} payloadDownloadUrl"),
            RequireArtifactSha256(sha256, artifactId, $"{manifest} payload"),
            RequireArtifactSize(sizeBytes, artifactId, $"{manifest} payload"));
    }

    private static string RequireNonEmptyArtifactUrl(
        string? value,
        string artifactId,
        string field)
    {
        string url = (value ?? string.Empty).Trim();
        if (url.Length == 0)
        {
            throw new InvalidDataException($"artifact {artifactId} {field} is required.");
        }

        return url;
    }

    private static string RequireGovernedIncomingArtifactUrl(
        string? value,
        string fileName,
        string artifactId)
    {
        string url = (value ?? string.Empty).Trim();
        string expected = $"/downloads/files/{fileName}";
        bool hasSchemeOrAuthority = url.StartsWith("//", StringComparison.Ordinal)
            || (!url.StartsWith("/", StringComparison.Ordinal)
                && Uri.TryCreate(url, UriKind.Absolute, out Uri? absoluteUri)
                && (!string.IsNullOrEmpty(absoluteUri.Scheme)
                    || !string.IsNullOrEmpty(absoluteUri.Authority)));
        if (url.Contains('?', StringComparison.Ordinal)
            || url.Contains('#', StringComparison.Ordinal)
            || url.Contains('\\', StringComparison.Ordinal)
            || hasSchemeOrAuthority
            || !string.Equals(url, expected, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"artifact {artifactId} URL must be the governed incoming path {expected}.");
        }

        return url;
    }

    private static string RequirePortableArtifactFileName(
        string? value,
        string artifactId,
        string field)
    {
        string fileName = (value ?? string.Empty).Trim();
        if (fileName.Length == 0
            || !string.Equals(fileName, Path.GetFileName(fileName), StringComparison.Ordinal)
            || fileName is "." or "..")
        {
            throw new InvalidDataException($"artifact {artifactId} {field} is not a portable basename.");
        }

        ValidatePortableInventoryPath(fileName, $"artifact {artifactId} {field}");
        return fileName;
    }

    private static string RequireArtifactSha256(string? value, string artifactId, string field)
    {
        string normalized = NormalizeArtifactDigest(value);
        if (normalized.Length != 64
            || normalized.Any(static character => character is not (>= '0' and <= '9' or >= 'a' and <= 'f')))
        {
            throw new InvalidDataException($"artifact {artifactId} {field} sha256 is invalid.");
        }

        return normalized;
    }

    private static long RequireArtifactSize(long? value, string artifactId, string field)
    {
        if (value is null or < 0)
        {
            throw new InvalidDataException($"artifact {artifactId} {field} sizeBytes is invalid.");
        }

        return value.Value;
    }

    private static string RequireInstallAccessClass(string? value, string artifactId)
    {
        string normalized = NormalizeToken(value);
        if (normalized is not "open_public" and not "account_required" and not "account_recommended")
        {
            throw new InvalidDataException(
                $"artifact {artifactId} installAccessClass is missing or unsupported.");
        }

        return normalized;
    }

    private static string RequireArtifactToken(string? value, string field)
    {
        string normalized = NormalizeToken(value);
        if (string.IsNullOrWhiteSpace(normalized))
        {
            throw new InvalidDataException($"{field} is required.");
        }

        return normalized;
    }

    private static string RequireArtifactLabel(string? value, string artifactId, string field)
    {
        string label = (value ?? string.Empty).Trim();
        if (label.Length == 0)
        {
            throw new InvalidDataException($"artifact {artifactId} {field} is required.");
        }

        return label;
    }

    private static string? NormalizeOptionalToken(string? value)
    {
        string normalized = NormalizeToken(value);
        return normalized.Length == 0 ? null : normalized;
    }

    private static IReadOnlyList<StartupSmokeReceipt> LoadStartupSmokeReceipts(string startupSmokeRoot)
    {
        List<StartupSmokeReceipt> receipts = new();
        foreach (string path in Directory.GetFiles(startupSmokeRoot, "startup-smoke-*.receipt.json", SearchOption.AllDirectories))
        {
            StartupSmokeReceipt? receipt;
            try
            {
                receipt = JsonSerializer.Deserialize<StartupSmokeReceipt>(File.ReadAllText(path), JsonOptions);
            }
            catch (JsonException ex)
            {
                throw new InvalidDataException(
                    $"startup smoke receipt {Path.GetFileName(path)} is malformed.",
                    ex);
            }

            if (receipt is null
                || string.IsNullOrWhiteSpace(receipt.HeadId)
                || string.IsNullOrWhiteSpace(receipt.Platform)
                || string.IsNullOrWhiteSpace(receipt.Arch))
            {
                throw new InvalidDataException(
                    $"startup smoke receipt {Path.GetFileName(path)} is missing its head/platform/arch identity.");
            }

            receipts.Add(receipt);
        }

        return receipts;
    }

    private static PromotionEvidenceDocument LoadPromotionEvidence(string? promotionEvidencePath)
    {
        if (string.IsNullOrWhiteSpace(promotionEvidencePath) || !File.Exists(promotionEvidencePath))
        {
            throw new InvalidDataException("bundle is missing release-evidence/public-promotion.json.");
        }

        PromotionEvidenceDocument? evidence = JsonSerializer.Deserialize<PromotionEvidenceDocument>(File.ReadAllText(promotionEvidencePath), JsonOptions);
        if (evidence is null
            || !string.Equals(evidence.ContractName, "chummer.run.desktop_release_publication", StringComparison.Ordinal))
        {
            throw new InvalidDataException("bundle promotion evidence is missing or malformed.");
        }

        return evidence;
    }

    private static void ValidateStartupSmokeReceipt(
        CanonicalArtifactRecord artifact,
        IReadOnlyList<StartupSmokeReceipt> receipts,
        string releaseVersion,
        string channel,
        DateTimeOffset evaluatedAtUtc)
    {
        string expectedPlatform = NormalizePlatform(artifact.Platform);
        string expectedArch = (artifact.Arch ?? string.Empty).Trim().ToLowerInvariant();
        string expectedHead = (artifact.Head ?? string.Empty).Trim();
        string expectedRid = NormalizeToken(artifact.Rid);
        string expectedDigest = NormalizeArtifactDigest(artifact.Sha256);
        string expectedFileName = ResolveArtifactFileName(artifact.FileName, artifact.DownloadUrl);

        List<StartupSmokeReceipt> matches = receipts
            .Where(receipt =>
                string.Equals(receipt.HeadId, expectedHead, StringComparison.OrdinalIgnoreCase)
                && string.Equals(NormalizePlatform(receipt.Platform), expectedPlatform, StringComparison.OrdinalIgnoreCase)
                && string.Equals(receipt.Arch, expectedArch, StringComparison.OrdinalIgnoreCase))
            .ToList();
        if (matches.Count == 0)
        {
            throw new InvalidDataException($"startup smoke receipt is missing for {artifact.ArtifactId}.");
        }

        if (matches.Count != 1)
        {
            throw new InvalidDataException(
                $"startup smoke receipt identity is ambiguous for {artifact.ArtifactId}.");
        }

        StartupSmokeReceipt receipt = matches[0];
        string status = NormalizeToken(receipt.Status);
        if (status is not ("pass" or "passed" or "ready"))
        {
            throw new InvalidDataException(
                $"startup smoke receipt status is not passing for {artifact.ArtifactId}.");
        }

        RequireStartupSmokeExact(
            receipt.ReleaseVersion,
            releaseVersion,
            artifact.ArtifactId,
            "releaseVersion");
        RequireStartupSmokeExact(
            receipt.Version,
            releaseVersion,
            artifact.ArtifactId,
            "version");
        if (!string.IsNullOrWhiteSpace(receipt.Channel))
        {
            RequireStartupSmokeToken(
                receipt.Channel,
                channel,
                artifact.ArtifactId,
                "channel");
        }
        RequireStartupSmokeToken(
            receipt.ChannelId,
            channel,
            artifact.ArtifactId,
            "channelId");
        RequireStartupSmokeExact(
            receipt.ArtifactId,
            artifact.ArtifactId,
            artifact.ArtifactId,
            "artifactId");
        RequireStartupSmokeExact(
            receipt.ArtifactFileName,
            expectedFileName,
            artifact.ArtifactId,
            "artifactFileName");
        RequireStartupSmokeExact(
            receipt.FileName,
            expectedFileName,
            artifact.ArtifactId,
            "fileName");
        RequireStartupSmokeToken(
            receipt.Rid,
            expectedRid,
            artifact.ArtifactId,
            "rid");
        RequireStartupSmokeToken(
            receipt.ReadyCheckpoint,
            "pre_ui_event_loop",
            artifact.ArtifactId,
            "readyCheckpoint");
        ValidateStartupSmokeArtifactPath(receipt, expectedFileName, artifact.ArtifactId);

        string receiptDigest = NormalizeArtifactDigest(receipt.ArtifactDigest);
        string receiptSha256 = NormalizeArtifactDigest(receipt.ArtifactSha256);
        if (expectedDigest.Length == 0
            || (receiptDigest.Length == 0 && receiptSha256.Length == 0)
            || (receiptDigest.Length > 0
                && !string.Equals(receiptDigest, expectedDigest, StringComparison.OrdinalIgnoreCase))
            || (receiptSha256.Length > 0
                && !string.Equals(receiptSha256, expectedDigest, StringComparison.OrdinalIgnoreCase)))
        {
            throw new InvalidDataException($"startup smoke receipts for {artifact.ArtifactId} do not match the uploaded artifact digest.");
        }

        ValidateStartupSmokeTimestamps(receipt, artifact.ArtifactId, evaluatedAtUtc);
        ValidateStartupSmokeHost(receipt, artifact.ArtifactId, expectedPlatform);
        if (string.Equals(expectedPlatform, "windows", StringComparison.Ordinal))
        {
            ValidateNativeWindowsStartupSmoke(receipt, artifact.ArtifactId);
        }
    }

    private static void RequireStartupSmokeExact(
        string? actual,
        string expected,
        string artifactId,
        string field)
    {
        if (string.IsNullOrWhiteSpace(actual)
            || !string.Equals(actual.Trim(), expected.Trim(), StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"startup smoke receipt {field} does not match {artifactId}.");
        }
    }

    private static void RequireStartupSmokeToken(
        string? actual,
        string expected,
        string artifactId,
        string field)
    {
        if (NormalizeToken(actual) != NormalizeToken(expected))
        {
            throw new InvalidDataException(
                $"startup smoke receipt {field} does not match {artifactId}.");
        }
    }

    private static void ValidateStartupSmokeArtifactPath(
        StartupSmokeReceipt receipt,
        string expectedFileName,
        string artifactId)
    {
        string expectedRelativePath = $"files/{expectedFileName}";
        string relativePath = NormalizeStartupSmokePath(receipt.ArtifactRelativePath);
        if (!string.Equals(relativePath, expectedRelativePath, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"startup smoke receipt artifactRelativePath does not match {artifactId}.");
        }

        string artifactPath = NormalizeStartupSmokePath(receipt.ArtifactPath);
        if (artifactPath.Length == 0
            || artifactPath.Split('/', StringSplitOptions.RemoveEmptyEntries)
                .Any(static segment => segment is "." or "..")
            || (!string.Equals(artifactPath, expectedRelativePath, StringComparison.Ordinal)
                && !artifactPath.EndsWith($"/{expectedRelativePath}", StringComparison.Ordinal)))
        {
            throw new InvalidDataException(
                $"startup smoke receipt artifactPath does not match {artifactId}.");
        }
    }

    private static string NormalizeStartupSmokePath(string? value)
        => (value ?? string.Empty).Trim().Replace('\\', '/');

    private static void ValidateStartupSmokeTimestamps(
        StartupSmokeReceipt receipt,
        string artifactId,
        DateTimeOffset evaluatedAtUtc)
    {
        DateTimeOffset startedAtUtc = RequireStartupSmokeTimestamp(
            receipt.StartedAtUtc,
            artifactId,
            "startedAtUtc");
        DateTimeOffset recordedAtUtc = RequireStartupSmokeTimestamp(
            receipt.RecordedAtUtc,
            artifactId,
            "recordedAtUtc");
        DateTimeOffset completedAtUtc = RequireStartupSmokeTimestamp(
            receipt.CompletedAtUtc,
            artifactId,
            "completedAtUtc");

        if (startedAtUtc > recordedAtUtc || recordedAtUtc > completedAtUtc)
        {
            throw new InvalidDataException(
                $"startup smoke receipt timestamps are not ordered for {artifactId}.");
        }

        List<(string Field, DateTimeOffset Timestamp)> timestamps =
        [
            ("startedAtUtc", startedAtUtc),
            ("recordedAtUtc", recordedAtUtc),
            ("completedAtUtc", completedAtUtc)
        ];
        if (!string.IsNullOrWhiteSpace(receipt.SourceUpdatedAtUtc))
        {
            timestamps.Add((
                "sourceUpdatedAtUtc",
                RequireStartupSmokeTimestamp(receipt.SourceUpdatedAtUtc, artifactId, "sourceUpdatedAtUtc")));
        }

        DateTimeOffset normalizedEvaluationInstant = evaluatedAtUtc.ToUniversalTime();
        foreach ((string field, DateTimeOffset timestamp) in timestamps)
        {
            if (timestamp > normalizedEvaluationInstant + MaximumStartupSmokeClockSkew)
            {
                throw new InvalidDataException(
                    $"startup smoke receipt {field} is too far in the future for {artifactId}.");
            }

            if (timestamp < normalizedEvaluationInstant - MaximumStartupSmokeAge)
            {
                throw new InvalidDataException(
                    $"startup smoke receipt {field} is stale for {artifactId}.");
            }
        }
    }

    private static DateTimeOffset RequireStartupSmokeTimestamp(
        string? value,
        string artifactId,
        string field)
    {
        if (!DateTimeOffset.TryParse(
                value,
                CultureInfo.InvariantCulture,
                DateTimeStyles.AllowWhiteSpaces | DateTimeStyles.AssumeUniversal,
                out DateTimeOffset parsed))
        {
            throw new InvalidDataException(
                $"startup smoke receipt {field} is missing or invalid for {artifactId}.");
        }

        return parsed.ToUniversalTime();
    }

    private static void ValidateStartupSmokeHost(
        StartupSmokeReceipt receipt,
        string artifactId,
        string expectedPlatform)
    {
        string hostClass = NormalizeToken(receipt.HostClass);
        string operatingSystem = NormalizeToken(receipt.OperatingSystem);
        if (hostClass.Length == 0)
        {
            throw new InvalidDataException(
                $"startup smoke receipt hostClass is missing for {artifactId}.");
        }

        if (operatingSystem.Length == 0)
        {
            throw new InvalidDataException(
                $"startup smoke receipt operatingSystem is missing for {artifactId}.");
        }

        string[] expectedHostTokens = expectedPlatform switch
        {
            "windows" => ["win", "windows"],
            "macos" => ["mac", "macos", "osx", "darwin"],
            "linux" => ["linux"],
            _ => [expectedPlatform]
        };
        string[] hostTokens = hostClass.Split(
            ['-', '_', '/', ' '],
            StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        bool hostMatches = hostTokens.Any(token =>
            expectedHostTokens.Contains(token, StringComparer.Ordinal));
        if (!hostMatches
            && !(string.Equals(expectedPlatform, "windows", StringComparison.Ordinal)
                && hostClass.Contains("wine", StringComparison.Ordinal)
                && operatingSystem.Contains("windows", StringComparison.Ordinal)))
        {
            throw new InvalidDataException(
                $"startup smoke receipt hostClass does not identify the {expectedPlatform} host for {artifactId}.");
        }
    }

    private static void ValidateNativeWindowsStartupSmoke(
        StartupSmokeReceipt receipt,
        string artifactId)
    {
        if (NormalizeToken(receipt.ExecutionEnvironment) != "native_windows")
        {
            throw new InvalidDataException(
                $"canonical Windows promotion requires native Windows startup smoke for {artifactId}; compatibility execution is insufficient.");
        }

        NativeWindowsHostEvidence? evidence = receipt.NativeHostEvidence;
        if (evidence is null
            || !string.Equals(
                evidence.ContractName?.Trim(),
                "chummer6-ui.native_windows_host_evidence",
                StringComparison.Ordinal)
            || NormalizeToken(evidence.Status) != "verified"
            || evidence.IsNativeWindows is not true
            || NormalizePlatform(evidence.HostPlatform) != "windows")
        {
            throw new InvalidDataException(
                $"startup smoke receipt nativeHostEvidence is not verified native Windows evidence for {artifactId}.");
        }

        string hostKernel = NormalizeToken(evidence.HostKernel);
        string runner = NormalizeToken(evidence.Runner);
        if (!new[] { "windows", "mingw", "msys", "cygwin" }
                .Any(token => hostKernel.Contains(token, StringComparison.Ordinal))
            || runner.Length == 0
            || runner.Contains("wine", StringComparison.Ordinal)
            || NormalizeToken(evidence.EvidenceSource).Length == 0)
        {
            throw new InvalidDataException(
                $"startup smoke receipt nativeHostEvidence is internally inconsistent for {artifactId}.");
        }
    }

    private static void ValidatePromotionEvidence(CanonicalArtifactRecord artifact, PromotionEvidenceDocument evidence, string? channel)
    {
        PromotionArtifactEvidence? artifactEvidence = evidence.Artifacts.FirstOrDefault(item =>
            string.Equals(item.ArtifactId, artifact.ArtifactId, StringComparison.OrdinalIgnoreCase)
            || string.Equals(item.FileName, ResolveArtifactFileName(artifact.FileName, artifact.DownloadUrl), StringComparison.OrdinalIgnoreCase));
        if (artifactEvidence is null)
        {
            throw new InvalidDataException($"promotion evidence is missing for {artifact.ArtifactId}.");
        }

        if (!string.Equals(artifactEvidence.PromotionStatus, "pass", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException($"promotion evidence did not pass for {artifact.ArtifactId}.");
        }

        if (!string.Equals(artifactEvidence.StartupSmokeStatus, "pass", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(artifactEvidence.StartupSmokeStatus, "skipped_incompatible_host", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException($"startup smoke evidence did not pass for {artifact.ArtifactId}.");
        }

        string platform = NormalizePlatform(artifact.Platform);
        if (string.Equals(platform, "windows", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(artifactEvidence.SigningStatus, "pass", StringComparison.OrdinalIgnoreCase))
        {
            bool previewUnsignedAllowed =
                string.Equals(channel, "preview", StringComparison.OrdinalIgnoreCase)
                && string.Equals(artifactEvidence.SigningStatus, "skipped_preview", StringComparison.OrdinalIgnoreCase);
            bool explicitUnsignedReleaseAllowed =
                !string.Equals(channel, "preview", StringComparison.OrdinalIgnoreCase)
                && string.Equals(artifactEvidence.SigningStatus, "unsigned_public_release", StringComparison.OrdinalIgnoreCase);

            if (!previewUnsignedAllowed && !explicitUnsignedReleaseAllowed)
            {
                throw new InvalidDataException($"windows promotion requires signing proof for {artifact.ArtifactId}.");
            }
        }

        if (string.Equals(platform, "macos", StringComparison.OrdinalIgnoreCase))
        {
            bool previewUnsignedAllowed =
                string.Equals(channel, "preview", StringComparison.OrdinalIgnoreCase)
                && string.Equals(artifactEvidence.SigningStatus, "skipped_preview", StringComparison.OrdinalIgnoreCase)
                && string.Equals(artifactEvidence.NotarizationStatus, "skipped_preview", StringComparison.OrdinalIgnoreCase);

            if (previewUnsignedAllowed)
            {
                return;
            }

            if (!string.Equals(artifactEvidence.SigningStatus, "pass", StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException($"macOS promotion requires signing proof for {artifact.ArtifactId}.");
            }

            if (!string.Equals(artifactEvidence.NotarizationStatus, "pass", StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException($"macOS promotion requires notarization proof for {artifact.ArtifactId}.");
            }
        }
    }

    private static PublicReleaseManifestDto MergeCompatibilityManifest(
        PublicReleaseManifestDto? existingManifest,
        PublicReleaseManifestDto incomingManifest)
    {
        return incomingManifest;
    }

    private static JsonObject MergeCanonicalManifest(JsonObject? existingManifest, JsonObject incomingManifest)
    {
        return incomingManifest.DeepClone().AsObject();
    }

    private static void ValidateNoDesktopInstallTupleRegression(
        JsonObject? existingManifest,
        JsonObject incomingManifest)
    {
        if (existingManifest?["artifacts"] is not JsonArray existingArtifacts
            || incomingManifest["artifacts"] is not JsonArray incomingArtifacts)
        {
            return;
        }

        HashSet<string> existingTuples = DesktopInstallTupleIds(existingArtifacts);
        if (existingTuples.Count == 0)
        {
            return;
        }

        HashSet<string> incomingTuples = DesktopInstallTupleIds(incomingArtifacts);
        string[] missingTuples = existingTuples
            .Except(incomingTuples, StringComparer.OrdinalIgnoreCase)
            .OrderBy(static tupleId => tupleId, StringComparer.Ordinal)
            .ToArray();
        if (missingTuples.Length == 0)
        {
            return;
        }

        throw new InvalidDataException(
            "incoming authoritative release bundle would drop existing desktop install tuple(s): "
            + string.Join(", ", missingTuples)
            + ". Scoped updates and explicit removals are not supported yet; upload a complete shelf containing every existing desktop install tuple.");
    }

    private static HashSet<string> DesktopInstallTupleIds(JsonArray artifacts)
        => ExtractCanonicalArtifactRows(artifacts)
            .Where(static artifact =>
                !string.IsNullOrWhiteSpace(artifact.Head)
                && !string.IsNullOrWhiteSpace(artifact.Platform)
                && !string.IsNullOrWhiteSpace(artifact.Rid)
                && IsDesktopInstallMedia(artifact.Platform, artifact.Kind))
            .Select(static artifact => $"{artifact.Head}:{artifact.Platform}:{artifact.Rid}")
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

    private static (PublicReleaseManifestDto CompatibilityManifest, JsonObject CanonicalManifest) NormalizeMergedShelfProjection(
        PublicReleaseManifestDto mergedCompatibilityManifest,
        JsonObject mergedCanonicalManifest,
        DateTimeOffset evaluationInstant,
        PrivacyLaunchGateSnapshot privacyLaunchGate)
    {
        string proofFreshnessStatus = NormalizeProofFreshnessForPublication(
            mergedCanonicalManifest,
            mergedCompatibilityManifest.PublishedAt,
            evaluationInstant);
        string normalizedProofStatus = NormalizeReleaseProofForPublication(
            mergedCanonicalManifest,
            mergedCompatibilityManifest.PublishedAt);
        string canonicalChannel = NormalizeToken(mergedCompatibilityManifest.Channel);
        string canonicalVersion = mergedCompatibilityManifest.Version?.Trim() ?? string.Empty;
        JsonArray mergedArtifacts = mergedCanonicalManifest["artifacts"] as JsonArray ?? [];
        JsonObject coverage = BuildDesktopTupleCoverage(
            mergedArtifacts,
            mergedCompatibilityManifest.DesktopTupleCoverage,
            channelStatus: mergedCompatibilityManifest.Status,
            rolloutState: mergedCompatibilityManifest.RolloutState,
            rolloutReason: mergedCompatibilityManifest.RolloutReason,
            knownIssueSummary: mergedCompatibilityManifest.KnownIssueSummary);

        bool desktopCoverageComplete = DesktopTupleCoverageIsComplete(coverage);
        string proofStatus = normalizedProofStatus;
        IReadOnlyList<string> proofJourneys = ExtractProofJourneys(mergedCanonicalManifest);
        bool proofPassed = ProofPassed(proofStatus);
        string rolloutState = DeriveRolloutState(
            mergedCompatibilityManifest.Channel,
            mergedCompatibilityManifest.Status,
            proofPassed,
            desktopCoverageComplete,
            proofFreshnessStatus,
            privacyLaunchGate);
        string rolloutReason = DeriveRolloutReason(
            mergedCompatibilityManifest.Channel,
            mergedCompatibilityManifest.Status,
            proofPassed,
            desktopCoverageComplete,
            coverage,
            proofFreshnessStatus,
            privacyLaunchGate);
        string supportabilityState = DeriveSupportabilityState(
            mergedCompatibilityManifest.Channel,
            mergedCompatibilityManifest.Status,
            proofPassed,
            desktopCoverageComplete,
            proofFreshnessStatus,
            privacyLaunchGate);
        string supportabilitySummary = DeriveSupportabilitySummary(
            mergedCompatibilityManifest.Channel,
            mergedCompatibilityManifest.Status,
            proofPassed,
            desktopCoverageComplete,
            coverage,
            proofJourneys,
            proofFreshnessStatus,
            privacyLaunchGate);
        string knownIssueSummary = DeriveKnownIssueSummary(
            mergedCompatibilityManifest.Channel,
            mergedCompatibilityManifest.Status,
            proofPassed,
            desktopCoverageComplete,
            coverage,
            proofJourneys,
            proofFreshnessStatus,
            privacyLaunchGate);
        string fixAvailabilitySummary = DeriveFixAvailabilitySummary(
            mergedCompatibilityManifest.Status,
            proofPassed,
            desktopCoverageComplete,
            proofFreshnessStatus,
            privacyLaunchGate);

        PublicReleaseManifestDto normalizedCompatibilityManifest = mergedCompatibilityManifest with
        {
            RolloutState = rolloutState,
            RolloutReason = rolloutReason,
            SupportabilityState = supportabilityState,
            SupportabilitySummary = supportabilitySummary,
            KnownIssueSummary = knownIssueSummary,
            FixAvailabilitySummary = fixAvailabilitySummary,
            ProofStatus = string.IsNullOrWhiteSpace(proofStatus)
                ? null
                : proofStatus,
            DesktopTupleCoverage = JsonSerializer.SerializeToElement(coverage, JsonOptions)
        };

        JsonObject normalizedCanonicalManifest = mergedCanonicalManifest.DeepClone().AsObject();
        JsonArray normalizedArtifacts = normalizedCanonicalManifest["artifacts"] as JsonArray ?? [];
        if (!string.IsNullOrWhiteSpace(canonicalChannel))
        {
            normalizedCanonicalManifest["channel"] = canonicalChannel;
            normalizedCanonicalManifest["channelId"] = canonicalChannel;
            foreach (JsonObject artifact in normalizedArtifacts.OfType<JsonObject>())
            {
                artifact["channel"] = canonicalChannel;
                artifact["channelId"] = canonicalChannel;
            }
        }

        if (!string.IsNullOrWhiteSpace(canonicalVersion))
        {
            normalizedCanonicalManifest["version"] = canonicalVersion;
            foreach (JsonObject artifact in normalizedArtifacts.OfType<JsonObject>())
            {
                artifact["version"] = canonicalVersion;
                artifact["releaseVersion"] = canonicalVersion;
            }
        }

        normalizedCanonicalManifest["desktopTupleCoverage"] = coverage.DeepClone();
        normalizedCanonicalManifest["installAwareArtifactRegistry"] = BuildInstallAwareArtifactRegistry(
            normalizedArtifacts,
            coverage,
            canonicalChannel,
            canonicalVersion);
        normalizedCanonicalManifest["rolloutState"] = rolloutState;
        normalizedCanonicalManifest["rolloutReason"] = rolloutReason;
        normalizedCanonicalManifest["supportabilityState"] = supportabilityState;
        normalizedCanonicalManifest["supportabilitySummary"] = supportabilitySummary;
        normalizedCanonicalManifest["knownIssueSummary"] = knownIssueSummary;
        normalizedCanonicalManifest["fixAvailabilitySummary"] = fixAvailabilitySummary;
        JsonObject publicTrustMetrics = normalizedCanonicalManifest["publicTrustMetrics"] as JsonObject ?? new JsonObject();
        publicTrustMetrics["privacyReadiness"] = privacyLaunchGate.ToJsonObject();
        normalizedCanonicalManifest["publicTrustMetrics"] = publicTrustMetrics;
        RefreshPublicTrustReleaseChannelMetrics(
            normalizedCanonicalManifest,
            coverage,
            canonicalChannel,
            GetJsonString(normalizedCanonicalManifest["status"]) ?? normalizedCompatibilityManifest.Status ?? string.Empty,
            rolloutState,
            supportabilityState);
        JsonObject registryBoundaryCoverage = NormalizeRegistryBoundaryCoverage(
            normalizedCanonicalManifest["registryBoundaryCoverage"] as JsonObject,
            normalizedCompatibilityManifest.Downloads.Count,
            normalizedCanonicalManifest,
            coverage,
            canonicalChannel,
            canonicalVersion,
            GetJsonString(normalizedCanonicalManifest["status"]) ?? normalizedCompatibilityManifest.Status ?? string.Empty,
            rolloutState,
            supportabilityState);
        normalizedCanonicalManifest["registryBoundaryCoverage"] = registryBoundaryCoverage.DeepClone();
        normalizedCompatibilityManifest = normalizedCompatibilityManifest with
        {
            RegistryBoundaryCoverage = JsonSerializer.SerializeToElement(registryBoundaryCoverage, JsonOptions),
            PublicTrustMetrics = JsonSerializer.SerializeToElement(
                normalizedCanonicalManifest["publicTrustMetrics"],
                JsonOptions)
        };

        return (normalizedCompatibilityManifest, normalizedCanonicalManifest);
    }

    private static void RefreshPublicTrustReleaseChannelMetrics(
        JsonObject manifest,
        JsonObject coverage,
        string channelId,
        string status,
        string rolloutState,
        string supportabilityState)
    {
        JsonObject metrics = manifest["publicTrustMetrics"] as JsonObject ?? new JsonObject();
        JsonObject releaseChannel = metrics["releaseChannel"] as JsonObject ?? new JsonObject();
        JsonObject adoptionHealth = metrics["adoptionHealth"] as JsonObject ?? new JsonObject();
        JsonObject revocationFacts = metrics["revocationFacts"] as JsonObject ?? new JsonObject();
        string proofFreshnessStatus = NormalizeToken(GetJsonString((metrics["proofFreshness"] as JsonObject)?["status"]));
        bool privacyReadinessBlocks = PrivacyReadinessBlocksOutputReadiness(
            metrics["privacyReadiness"] as JsonObject);
        string normalizedChannel = NormalizeToken(channelId);
        string normalizedStatus = NormalizeToken(status);
        string normalizedRollout = NormalizeToken(rolloutState);
        string normalizedSupportability = NormalizeToken(supportabilityState);
        string posture = ReleaseChannelPublicPosture(
            normalizedStatus,
            normalizedRollout,
            normalizedSupportability);
        bool channelRevoked =
            string.Equals(normalizedStatus, "revoked", StringComparison.Ordinal)
            || string.Equals(normalizedRollout, "revoked", StringComparison.Ordinal);

        int recommendedRouteCount = GetMetricCount(
            adoptionHealth,
            "primaryPromotedCount",
            GetJsonInt32(releaseChannel["recommendedRouteCount"]));
        int fallbackRouteCount = GetMetricCount(
            adoptionHealth,
            "fallbackRecoveryCount",
            GetJsonInt32(releaseChannel["fallbackRecoveryRouteCount"]));
        int blockedRouteCount = GetMetricCount(
            adoptionHealth,
            "blockedRouteCount",
            GetJsonInt32(releaseChannel["blockedRouteCount"]));
        int revokedRouteCount = GetMetricCount(
            revocationFacts,
            "activeRevocationCount",
            GetJsonInt32(releaseChannel["revokedRouteCount"]));
        int publicInstallCount = GetMetricCount(adoptionHealth, "publicInstallCount", 0);
        int accountLinkedInstallCount = GetMetricCount(adoptionHealth, "accountLinkedInstallCount", 0);
        string adoptionStatus = NormalizeToken(GetJsonString(adoptionHealth["status"]));
        JsonArray activeRevocations = revocationFacts["activeRevocations"] as JsonArray ?? new JsonArray();

        if (coverage["desktopRouteTruth"] is JsonArray routeTruth)
        {
            List<JsonObject> rows = routeTruth.OfType<JsonObject>().ToList();
            List<JsonObject> recommendedRoutes = rows
                .Where(RouteTruthIsRecommendedPrimary)
                .ToList();
            List<JsonObject> fallbackRoutes = rows
                .Where(RouteTruthIsFallbackRecovery)
                .ToList();
            List<JsonObject> blockedRoutes = rows
                .Where(RouteTruthIsBlocked)
                .ToList();
            List<JsonObject> revokedRoutes = rows
                .Where(RouteTruthIsRevoked)
                .ToList();

            Dictionary<string, JsonObject> artifactsById = (manifest["artifacts"] as JsonArray ?? new JsonArray())
                .OfType<JsonObject>()
                .Select(artifact => new
                {
                    Artifact = artifact,
                    ArtifactId = (GetJsonString(artifact["artifactId"]) ?? GetJsonString(artifact["id"]) ?? string.Empty).Trim()
                })
                .Where(static item => !string.IsNullOrWhiteSpace(item.ArtifactId))
                .ToDictionary(static item => item.ArtifactId, static item => item.Artifact, StringComparer.OrdinalIgnoreCase);

            recommendedRouteCount = recommendedRoutes.Count;
            fallbackRouteCount = fallbackRoutes.Count;
            blockedRouteCount = blockedRoutes.Count;
            revokedRouteCount = revokedRoutes.Count;

            publicInstallCount = 0;
            accountLinkedInstallCount = 0;
            foreach (JsonObject row in recommendedRoutes)
            {
                string artifactId = (GetJsonString(row["artifactId"]) ?? string.Empty).Trim();
                if (!artifactsById.TryGetValue(artifactId, out JsonObject? artifact))
                {
                    continue;
                }

                string installAccessClass = NormalizeToken(GetJsonString(artifact["installAccessClass"]));
                if (string.Equals(installAccessClass, "account_required", StringComparison.Ordinal))
                {
                    accountLinkedInstallCount += 1;
                }
                else
                {
                    publicInstallCount += 1;
                }
            }

            activeRevocations = new JsonArray();
            foreach (JsonObject row in revokedRoutes)
            {
                activeRevocations.Add(new JsonObject
                {
                    ["tupleId"] = (GetJsonString(row["tupleId"]) ?? string.Empty).Trim(),
                    ["head"] = NormalizeToken(GetJsonString(row["head"])),
                    ["platform"] = NormalizePlatform(GetJsonString(row["platform"])),
                    ["rid"] = NormalizeToken(GetJsonString(row["rid"])),
                    ["artifactId"] = string.IsNullOrWhiteSpace(GetJsonString(row["artifactId"])) ? null : GetJsonString(row["artifactId"])!.Trim(),
                    ["revokeSource"] = NormalizeToken(GetJsonString(row["revokeSource"])),
                    ["revokeReasonCode"] = NormalizeToken(GetJsonString(row["revokeReasonCode"])),
                    ["revokeReason"] = (GetJsonString(row["revokeReason"]) ?? string.Empty).Trim(),
                    ["publicInstallRoute"] = string.IsNullOrWhiteSpace(GetJsonString(row["publicInstallRoute"])) ? null : GetJsonString(row["publicInstallRoute"])!.Trim(),
                });
            }

            adoptionStatus = recommendedRouteCount == 0
                ? "blocked"
                : blockedRouteCount > 0
                  || revokedRouteCount > 0
                  || ProofFreshnessBlocksOutputReadiness(proofFreshnessStatus)
                  || privacyReadinessBlocks
                    ? "limited"
                    : "healthy";
        }

        releaseChannel["channelId"] = normalizedChannel;
        releaseChannel["posture"] = posture;
        releaseChannel["publicationStatus"] = normalizedStatus;
        releaseChannel["rolloutState"] = normalizedRollout;
        releaseChannel["supportabilityState"] = normalizedSupportability;
        releaseChannel["recommendedRouteCount"] = recommendedRouteCount;
        releaseChannel["fallbackRecoveryRouteCount"] = fallbackRouteCount;
        releaseChannel["blockedRouteCount"] = blockedRouteCount;
        releaseChannel["revokedRouteCount"] = revokedRouteCount;
        releaseChannel["summary"] =
            $"Channel {normalizedChannel} is {posture} with {recommendedRouteCount} recommended primary routes, " +
            $"{fallbackRouteCount} promoted fallback recovery routes, {blockedRouteCount} blocked routes, " +
            $"and {revokedRouteCount} active revocations.";

        adoptionHealth["status"] = string.IsNullOrWhiteSpace(adoptionStatus)
            ? recommendedRouteCount == 0 ? "blocked" : "healthy"
            : adoptionStatus;
        adoptionHealth["primaryPromotedCount"] = recommendedRouteCount;
        adoptionHealth["publicInstallCount"] = publicInstallCount;
        adoptionHealth["accountLinkedInstallCount"] = accountLinkedInstallCount;
        adoptionHealth["fallbackRecoveryCount"] = fallbackRouteCount;
        adoptionHealth["blockedRouteCount"] = blockedRouteCount;
        adoptionHealth["revokedRouteCount"] = revokedRouteCount;
        adoptionHealth["summary"] =
            $"{recommendedRouteCount} primary routes are promoted; {publicInstallCount} are guest-readable, " +
            $"{accountLinkedInstallCount} require account-linked install handoff, {fallbackRouteCount} fallback recovery routes are promoted, " +
            $"and {blockedRouteCount} routes are still blocked on proof.";

        revocationFacts["status"] = channelRevoked || revokedRouteCount > 0 ? "revoked" : "clear";
        revocationFacts["channelRevoked"] = channelRevoked;
        revocationFacts["activeRevocationCount"] = revokedRouteCount;
        revocationFacts["activeRevocations"] = activeRevocations;
        revocationFacts["summary"] = channelRevoked || revokedRouteCount > 0
            ? $"{revokedRouteCount} active route revocations are present on channel {normalizedChannel}."
            : $"No channel or route revocations are active on channel {normalizedChannel}.";

        metrics["releaseChannel"] = releaseChannel;
        metrics["adoptionHealth"] = adoptionHealth;
        metrics["revocationFacts"] = revocationFacts;
        manifest["publicTrustMetrics"] = metrics;
    }

    private static bool ProofFreshnessBlocksOutputReadiness(string proofFreshnessStatus)
        => !string.Equals(NormalizeToken(proofFreshnessStatus), "fresh", StringComparison.Ordinal);

    private static bool PrivacyReadinessBlocksOutputReadiness(JsonObject? privacyReadiness)
    {
        if (privacyReadiness is null)
        {
            return true;
        }

        string contractName = GetJsonString(privacyReadiness["contractName"]) ?? string.Empty;
        int contractVersion = GetJsonInt32(privacyReadiness["contractVersion"]);
        string status = NormalizeToken(GetJsonString(privacyReadiness["status"]));
        bool reviewRequired = GetJsonBoolean(privacyReadiness["reviewRequired"]);
        return !string.Equals(contractName, PrivacyLaunchGate.ContractName, StringComparison.Ordinal)
            || contractVersion != PrivacyLaunchGate.ContractVersion
            || reviewRequired
            || !string.Equals(status, "documented", StringComparison.Ordinal);
    }

    private static bool RouteTruthIsRecommendedPrimary(JsonObject row)
        => string.Equals(NormalizeToken(GetJsonString(row["routeRole"])), "primary", StringComparison.Ordinal)
            && string.Equals(NormalizeToken(GetJsonString(row["promotionState"])), "promoted", StringComparison.Ordinal)
            && !RouteTruthIsRevoked(row);

    private static bool RouteTruthIsFallbackRecovery(JsonObject row)
        => string.Equals(NormalizeToken(GetJsonString(row["routeRole"])), "fallback", StringComparison.Ordinal)
            && string.Equals(NormalizeToken(GetJsonString(row["promotionState"])), "promoted", StringComparison.Ordinal)
            && !RouteTruthIsRevoked(row);

    private static bool RouteTruthIsBlocked(JsonObject row)
        => string.Equals(NormalizeToken(GetJsonString(row["promotionState"])), "proof_required", StringComparison.Ordinal)
            && !RouteTruthIsPreviewOnlyFallback(row)
            && !RouteTruthIsRevoked(row);

    private static bool RouteTruthIsRevoked(JsonObject row)
        => string.Equals(NormalizeToken(GetJsonString(row["revokeState"])), "revoked", StringComparison.Ordinal)
            || string.Equals(NormalizeToken(GetJsonString(row["promotionState"])), "revoked", StringComparison.Ordinal);

    private static bool RouteTruthIsPreviewOnlyFallback(JsonObject row)
        => string.Equals(NormalizeToken(GetJsonString(row["routeRole"])), "fallback", StringComparison.Ordinal)
            && string.Equals(NormalizeToken(GetJsonString(row["promotionState"])), "proof_required", StringComparison.Ordinal)
            && string.Equals(NormalizeToken(GetJsonString(row["parityPosture"])), "explicit_fallback", StringComparison.Ordinal)
            && !string.Equals(NormalizeToken(GetJsonString(row["revokeState"])), "revoked", StringComparison.Ordinal);

    private static string ReleaseChannelPublicPosture(
        string status,
        string rolloutState,
        string supportabilityState)
    {
        string normalizedStatus = NormalizeToken(status);
        string normalizedRollout = NormalizeToken(rolloutState);
        string normalizedSupportability = NormalizeToken(supportabilityState);
        if (string.Equals(normalizedStatus, "revoked", StringComparison.Ordinal)
            || string.Equals(normalizedRollout, "revoked", StringComparison.Ordinal))
        {
            return "revoked";
        }

        if (!string.Equals(normalizedStatus, "published", StringComparison.Ordinal))
        {
            return "blocked";
        }

        if (string.Equals(normalizedRollout, "public_stable", StringComparison.Ordinal)
            && normalizedSupportability is "gold_supported" or "supported")
        {
            return "live";
        }

        if (normalizedRollout is "promoted_preview" or "preview"
            && string.Equals(normalizedSupportability, "preview_supported", StringComparison.Ordinal))
        {
            return "preview";
        }

        return "blocked";
    }

    private static JsonObject NormalizeRegistryBoundaryCoverage(
        JsonObject? sourceCoverage,
        int publishedArtifactCount,
        JsonObject manifest,
        JsonObject desktopTupleCoverage,
        string channelId,
        string releaseVersion,
        string status,
        string rolloutState,
        string supportabilityState)
    {
        JsonObject coverage = sourceCoverage?.DeepClone().AsObject() ?? new JsonObject();
        JsonObject releaseChannel = coverage["releaseChannel"] as JsonObject ?? new JsonObject();
        JsonArray routeTruth = desktopTupleCoverage["desktopRouteTruth"] as JsonArray ?? [];
        JsonArray promotedInstallerTuples = desktopTupleCoverage["promotedInstallerTuples"] as JsonArray ?? [];
        string normalizedChannel = NormalizeToken(channelId);
        string normalizedVersion = string.IsNullOrWhiteSpace(releaseVersion)
            ? GetJsonString(manifest["version"]) ?? string.Empty
            : releaseVersion;
        string normalizedRollout = NormalizeToken(rolloutState);
        string publicTrustPosture = ReleaseChannelPublicPosture(
            status,
            normalizedRollout,
            supportabilityState);

        releaseChannel["publicationStatus"] = NormalizeToken(status);
        releaseChannel["rolloutState"] = normalizedRollout;
        releaseChannel["supportabilityState"] = NormalizeToken(supportabilityState);
        releaseChannel["desktopTupleComplete"] = GetJsonBoolean(desktopTupleCoverage["complete"]);
        releaseChannel["promotedInstallerTupleCount"] = promotedInstallerTuples.Count;
        releaseChannel["desktopRouteTruthCount"] = routeTruth.Count;
        releaseChannel["publicTrustPosture"] = NormalizeToken(publicTrustPosture);
        releaseChannel["summary"] =
            $"Release-channel truth for {normalizedChannel}/{normalizedVersion} keeps " +
            $"{promotedInstallerTuples.Count} promoted installer tuples and " +
            $"{routeTruth.Count} explicit desktop route-truth rows under " +
            $"{normalizedRollout} rollout posture.";
        coverage["releaseChannel"] = releaseChannel;

        JsonObject compatibility = coverage["compatibility"] as JsonObject ?? new JsonObject();
        int compatibleRuntimeBundleHeadCount = GetJsonInt32(compatibility["compatibleRuntimeBundleHeadCount"]);
        int compatibleExchangeArtifactCount = GetJsonInt32(compatibility["compatibleExchangeArtifactCount"]);
        int unknownRuntimeBundleHeadCount = GetJsonInt32(compatibility["unknownRuntimeBundleHeadCount"]);
        compatibility["compatibleArtifactCount"] = publishedArtifactCount;
        compatibility["compatibleRuntimeBundleHeadCount"] = compatibleRuntimeBundleHeadCount;
        compatibility["compatibleExchangeArtifactCount"] = compatibleExchangeArtifactCount;
        compatibility["unknownArtifactCount"] = 0;
        compatibility["unknownRuntimeBundleHeadCount"] = unknownRuntimeBundleHeadCount;
        compatibility["summary"] =
            $"Compatibility boundary tracks {publishedArtifactCount} compatible artifacts, " +
            $"{compatibleRuntimeBundleHeadCount} compatible runtime bundle heads, and " +
            $"{compatibleExchangeArtifactCount} compatible exchange-lineage rows while " +
            $"0 artifact rows and {unknownRuntimeBundleHeadCount} runtime bundle heads remain unknown.";
        coverage["compatibility"] = compatibility;
        return coverage;
    }

    private static int GetJsonInt32(JsonNode? node)
    {
        if (node is null)
        {
            return 0;
        }

        if (node is JsonValue jsonValue && jsonValue.TryGetValue<int>(out int value))
        {
            return value;
        }

        return int.TryParse(GetJsonString(node), out value) ? value : 0;
    }

    private static int GetMetricCount(JsonObject? section, string propertyName, int fallbackValue)
    {
        if (section is null || !section.TryGetPropertyValue(propertyName, out JsonNode? node))
        {
            return fallbackValue;
        }

        return GetJsonInt32(node);
    }

    private static bool GetJsonBoolean(JsonNode? node)
    {
        if (node is null)
        {
            return false;
        }

        if (node is JsonValue jsonValue && jsonValue.TryGetValue<bool>(out bool value))
        {
            return value;
        }

        return bool.TryParse(GetJsonString(node), out value) && value;
    }

    private static JsonArray BuildInstallAwareArtifactRegistry(
        JsonArray artifacts,
        JsonObject coverage,
        string channelId,
        string releaseVersion)
    {
        if (coverage["desktopRouteTruth"] is not JsonArray desktopRouteTruth)
        {
            return [];
        }

        Dictionary<string, CanonicalArtifactState> artifactById = ExtractCanonicalArtifactRows(artifacts)
            .Where(static artifact => !string.IsNullOrWhiteSpace(artifact.ArtifactId))
            .GroupBy(static artifact => NormalizeToken(artifact.ArtifactId), StringComparer.OrdinalIgnoreCase)
            .ToDictionary(
                static group => group.Key,
                static group => group.OrderBy(static artifact => artifact.Kind, StringComparer.Ordinal).First(),
                StringComparer.OrdinalIgnoreCase);

        List<JsonObject> rows = [];
        foreach (JsonObject routeRow in desktopRouteTruth.OfType<JsonObject>())
        {
            string artifactId = ExpectedInstallerArtifactIdForRoute(routeRow);
            if (string.IsNullOrWhiteSpace(artifactId))
            {
                continue;
            }

            string head = NormalizeToken(GetJsonString(routeRow["head"]));
            string platform = NormalizePlatform(GetJsonString(routeRow["platform"]));
            string rid = NormalizeToken(GetJsonString(routeRow["rid"]));
            string arch = NormalizeToken(GetJsonString(routeRow["arch"]));
            if (string.IsNullOrWhiteSpace(arch)
                && RidToPlatformArch.TryGetValue(rid, out (string Platform, string Arch) platformArch))
            {
                arch = platformArch.Arch;
            }

            string installedBuildSelector = InstallAwareInstalledBuildSelector(
                channelId,
                releaseVersion,
                head,
                platform,
                arch);
            string tupleId = (GetJsonString(routeRow["tupleId"]) ?? string.Empty).Trim();
            string kind = InstallAwareArtifactKind(artifactById, artifactId);
            bool currentForInstalledBuild =
                string.Equals(NormalizeToken(GetJsonString(routeRow["promotionState"])), "promoted", StringComparison.Ordinal)
                && !string.Equals(NormalizeToken(GetJsonString(routeRow["revokeState"])), "revoked", StringComparison.Ordinal);

            JsonArray recoveryProofRefs =
            [
                (GetJsonString(routeRow["publicInstallRoute"]) ?? string.Empty).Trim(),
                $"startup-smoke/startup-smoke-{head}-{rid}.receipt.json",
                $"desktopTupleCoverage.desktopRouteTruth[{tupleId}]",
            ];

            JsonObject conciergeAssetRefs = new()
            {
                ["releaseExplainerPacket"] = $"concierge/release/{channelId}/{releaseVersion}/{artifactId}",
                ["supportClosurePacket"] = $"concierge/support/{channelId}/{releaseVersion}/{artifactId}",
                ["publicTrustWrapper"] = (GetJsonString(routeRow["publicInstallRoute"]) ?? string.Empty).Trim(),
            };

            rows.Add(new JsonObject
            {
                ["registryId"] = $"concierge:{channelId}:{releaseVersion}:{artifactId}",
                ["artifactId"] = artifactId,
                ["channelId"] = channelId,
                ["releaseVersion"] = releaseVersion,
                ["tupleId"] = tupleId,
                ["head"] = head,
                ["platform"] = platform,
                ["rid"] = rid,
                ["arch"] = arch,
                ["kind"] = kind,
                ["installedBuildSelector"] = installedBuildSelector,
                ["currentForInstalledBuild"] = currentForInstalledBuild,
                ["channelRationale"] = InstallAwareChannelRationale(routeRow, channelId, installedBuildSelector),
                ["correctnessReason"] = InstallAwareCorrectnessReason(routeRow, artifactId, installedBuildSelector),
                ["recoveryProofRefs"] = new JsonArray(
                    recoveryProofRefs
                        .Select(GetJsonString)
                        .Where(static value => !string.IsNullOrWhiteSpace(value))
                        .Select(static value => JsonValue.Create(value))
                        .ToArray()),
                ["conciergeAssetRefs"] = conciergeAssetRefs,
            });
        }

        return new JsonArray(
            rows.OrderBy(static row => NormalizePlatform(GetJsonString(row["platform"])), StringComparer.Ordinal)
                .ThenBy(static row => NormalizeToken(GetJsonString(row["head"])), StringComparer.Ordinal)
                .ThenBy(static row => NormalizeToken(GetJsonString(row["rid"])), StringComparer.Ordinal)
                .ThenBy(static row => NormalizeToken(GetJsonString(row["artifactId"])), StringComparer.Ordinal)
                .Select(static row => (JsonNode)row)
                .ToArray());
    }

    private static string ExpectedInstallerArtifactIdForRoute(JsonObject routeRow)
    {
        string artifactId = NormalizeToken(GetJsonString(routeRow["artifactId"]));
        if (!string.IsNullOrWhiteSpace(artifactId))
        {
            return artifactId;
        }

        string head = NormalizeToken(GetJsonString(routeRow["head"]));
        string rid = NormalizeToken(GetJsonString(routeRow["rid"]));
        return string.IsNullOrWhiteSpace(head) || string.IsNullOrWhiteSpace(rid)
            ? string.Empty
            : $"{head}-{rid}-installer";
    }

    private static string InstallAwareArtifactKind(
        IReadOnlyDictionary<string, CanonicalArtifactState> artifactById,
        string artifactId)
        => artifactById.TryGetValue(NormalizeToken(artifactId), out CanonicalArtifactState? artifact)
            ? NormalizeToken(artifact.Kind) switch
            {
                { Length: > 0 } kind => kind,
                _ => "installer",
            }
            : "installer";

    private static string InstallAwareInstalledBuildSelector(
        string channelId,
        string releaseVersion,
        string head,
        string platform,
        string arch)
        => $"{channelId}/{releaseVersion}/{head}/{platform}/{arch}";

    private static string InstallAwareChannelRationale(
        JsonObject routeRow,
        string channelId,
        string installedBuildSelector)
    {
        string tupleId = (GetJsonString(routeRow["tupleId"]) ?? string.Empty).Trim();
        string routeRole = NormalizeToken(GetJsonString(routeRow["routeRole"]));
        string promotionState = NormalizeToken(GetJsonString(routeRow["promotionState"]));
        string revokeState = NormalizeToken(GetJsonString(routeRow["revokeState"]));
        if (string.Equals(revokeState, "revoked", StringComparison.Ordinal))
        {
            return $"Published {channelId} channel blocks {routeRole}-route {tupleId} for installed build selector {installedBuildSelector} because registry revoke truth is active.";
        }

        if (string.Equals(promotionState, "promoted", StringComparison.Ordinal))
        {
            return string.Equals(routeRole, "fallback", StringComparison.Ordinal)
                ? $"Published {channelId} channel keeps fallback route {tupleId} current for installed build selector {installedBuildSelector} as recovery/manual routing."
                : $"Published {channelId} channel keeps primary-route {tupleId} current for installed build selector {installedBuildSelector}.";
        }

        return $"Published {channelId} channel keeps {routeRole}-route {tupleId} blocked for installed build selector {installedBuildSelector} until installer and startup verification are present.";
    }

    private static string InstallAwareCorrectnessReason(
        JsonObject routeRow,
        string artifactId,
        string installedBuildSelector)
    {
        string tupleId = (GetJsonString(routeRow["tupleId"]) ?? string.Empty).Trim();
        string promotionState = NormalizeToken(GetJsonString(routeRow["promotionState"]));
        string revokeState = NormalizeToken(GetJsonString(routeRow["revokeState"]));
        return string.Equals(promotionState, "promoted", StringComparison.Ordinal)
               && !string.Equals(revokeState, "revoked", StringComparison.Ordinal)
            ? $"Offer {artifactId} to installed build selector {installedBuildSelector} because tuple {tupleId} is currently promoted for this channel."
            : $"Do not offer {artifactId} to installed build selector {installedBuildSelector} because tuple {tupleId} is not currently promoted for this channel.";
    }

    private static string NormalizeReleaseProofForPublication(
        JsonObject manifest,
        DateTimeOffset publishedAt)
    {
        JsonObject? proof = manifest["releaseProof"] as JsonObject;
        string proofStatus = NormalizeReleaseProofStatus(ExtractProofStatus(manifest));
        if (proof is not null && !string.IsNullOrWhiteSpace(proofStatus))
        {
            proof["status"] = proofStatus;
        }

        if (!ProofPassed(proofStatus))
        {
            return proofStatus;
        }

        DateTimeOffset? proofGeneratedAt = TryGetJsonDateTimeOffset(proof?["generatedAt"]);
        if (proofGeneratedAt is null
            || publishedAt - proofGeneratedAt.Value > MaximumReleaseProofPublicationLag
            || proofGeneratedAt.Value - publishedAt > MaximumReleaseProofPublicationClockSkew)
        {
            if (proof is not null)
            {
                proof["status"] = "review_required";
            }

            return "review_required";
        }

        return proofStatus;
    }

    private static string NormalizeProofFreshnessForPublication(
        JsonObject manifest,
        DateTimeOffset publishedAt,
        DateTimeOffset evaluationInstant)
    {
        JsonObject publicTrustMetrics = manifest["publicTrustMetrics"] as JsonObject ?? new JsonObject();
        JsonObject proofFreshness = publicTrustMetrics["proofFreshness"] as JsonObject ?? new JsonObject();
        ReleaseProofFreshnessEvaluation evaluation = ReleaseProofFreshnessEvaluator.Evaluate(
            proofFreshness,
            manifest["releaseProof"] as JsonObject,
            publishedAt,
            evaluationInstant);
        proofFreshness["status"] = evaluation.MaterializedStatus;
        publicTrustMetrics["proofFreshness"] = proofFreshness;
        manifest["publicTrustMetrics"] = publicTrustMetrics;
        return evaluation.MaterializedStatus;
    }

    private static JsonObject BuildDesktopTupleCoverage(
        JsonArray artifacts,
        JsonElement? sourceCoverageElement,
        string? channelStatus,
        string? rolloutState,
        string? rolloutReason,
        string? knownIssueSummary)
    {
        JsonObject? sourceCoverage = sourceCoverageElement is JsonElement coverageElement
            && coverageElement.ValueKind == JsonValueKind.Object
            ? JsonNode.Parse(coverageElement.GetRawText())?.AsObject()
            : null;

        List<CanonicalArtifactState> artifactRows = ExtractCanonicalArtifactRows(artifacts);
        List<string> requiredDesktopPlatforms = [.. RequiredDesktopPlatforms];
        List<string> requiredDesktopHeads = [.. RequiredDesktopHeads];
        List<Dictionary<string, string>> promotedInstallerTuples = [];
        HashSet<string> promotedHeadTokens = new(StringComparer.OrdinalIgnoreCase);
        HashSet<string> promotedPlatformTokens = new(StringComparer.OrdinalIgnoreCase);
        HashSet<string> promotedPairs = new(StringComparer.OrdinalIgnoreCase);
        HashSet<string> promotedPlatformHeadRidTuples = new(StringComparer.OrdinalIgnoreCase);
        Dictionary<string, List<string>> promotedPlatformHeads = requiredDesktopPlatforms.ToDictionary(
            static platform => platform,
            static _ => new List<string>(),
            StringComparer.OrdinalIgnoreCase);
        Dictionary<string, HashSet<string>> promotedPlatformHeadsSeen = requiredDesktopPlatforms.ToDictionary(
            static platform => platform,
            static _ => new HashSet<string>(StringComparer.OrdinalIgnoreCase),
            StringComparer.OrdinalIgnoreCase);

        foreach (CanonicalArtifactState artifact in artifactRows)
        {
            if (!requiredDesktopPlatforms.Contains(artifact.Platform, StringComparer.OrdinalIgnoreCase)
                || !IsDesktopInstallMedia(artifact.Platform, artifact.Kind))
            {
                continue;
            }

            string tupleId = $"{artifact.Head}:{artifact.Platform}:{artifact.Rid}";
            promotedInstallerTuples.Add(new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["tupleId"] = tupleId,
                ["head"] = artifact.Head,
                ["platform"] = artifact.Platform,
                ["rid"] = artifact.Rid,
                ["arch"] = artifact.Arch,
                ["kind"] = artifact.Kind,
                ["artifactId"] = artifact.ArtifactId
            });
            if (!string.IsNullOrWhiteSpace(artifact.Head))
            {
                promotedHeadTokens.Add(artifact.Head);
                promotedPairs.Add($"{artifact.Head}:{artifact.Platform}");
                if (promotedPlatformHeadsSeen[artifact.Platform].Add(artifact.Head))
                {
                    promotedPlatformHeads[artifact.Platform].Add(artifact.Head);
                }
            }

            if (!string.IsNullOrWhiteSpace(artifact.Head) && !string.IsNullOrWhiteSpace(artifact.Rid))
            {
                promotedPlatformHeadRidTuples.Add($"{artifact.Head}:{artifact.Rid}:{artifact.Platform}");
            }

            promotedPlatformTokens.Add(artifact.Platform);
        }

        promotedInstallerTuples = promotedInstallerTuples
            .OrderBy(static row => row["platform"], StringComparer.Ordinal)
            .ThenBy(static row => row["head"], StringComparer.Ordinal)
            .ThenBy(static row => row["rid"], StringComparer.Ordinal)
            .ThenBy(static row => row["artifactId"], StringComparer.Ordinal)
            .ToList();
        foreach (string platform in requiredDesktopPlatforms)
        {
            promotedPlatformHeads[platform] = promotedPlatformHeads[platform]
                .OrderBy(static value => value, StringComparer.Ordinal)
                .ToList();
        }

        List<string> missingRequiredPlatforms = requiredDesktopPlatforms
            .Where(platform => !promotedPlatformTokens.Contains(platform))
            .ToList();
        List<string> missingRequiredHeads = requiredDesktopHeads
            .Where(head => !promotedHeadTokens.Contains(head))
            .ToList();
        List<string> missingRequiredPlatformHeadPairs = requiredDesktopPlatforms
            .SelectMany(platform => requiredDesktopHeads.Select(head => $"{head}:{platform}"))
            .Where(pair => !promotedPairs.Contains(pair))
            .ToList();

        List<string> sourceRequiredDesktopPlatformHeadRidTuples = ReadSourceCoverageStringList(
            sourceCoverage,
            "requiredDesktopPlatformHeadRidTuples")
            .Where(tupleId =>
            {
                string[] parts = tupleId.Split(':', 3, StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
                return parts.Length == 3
                    && requiredDesktopHeads.Contains(parts[0], StringComparer.OrdinalIgnoreCase)
                    && requiredDesktopPlatforms.Contains(parts[2], StringComparer.OrdinalIgnoreCase)
                    && RidToPlatformArch.TryGetValue(parts[1], out (string Platform, string Arch) mapping)
                    && string.Equals(mapping.Platform, parts[2], StringComparison.OrdinalIgnoreCase);
            })
            .ToList();
        List<string> canonicalRequiredDesktopPlatformHeadRidTuples = requiredDesktopPlatforms
            .SelectMany(platform =>
            {
                IEnumerable<string> rids = DefaultRequiredDesktopPlatformRids.GetValueOrDefault(platform, []);
                return requiredDesktopHeads.SelectMany(head =>
                    rids.Where(static rid => !string.IsNullOrWhiteSpace(rid))
                        .Select(rid => $"{head}:{rid}:{platform}"));
            })
            .ToList();
        List<string> requiredDesktopPlatformHeadRidTuples = canonicalRequiredDesktopPlatformHeadRidTuples
            .Concat(sourceRequiredDesktopPlatformHeadRidTuples)
            .OrderBy(static value => value, StringComparer.Ordinal)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();
        List<string> promotedDesktopPlatformHeadRidTuples = promotedPlatformHeadRidTuples
            .OrderBy(static value => value, StringComparer.Ordinal)
            .ToList();
        HashSet<string> promotedTupleSet = new(promotedDesktopPlatformHeadRidTuples, StringComparer.OrdinalIgnoreCase);
        List<string> missingRequiredPlatformHeadRidTuples = requiredDesktopPlatformHeadRidTuples
            .Where(tupleId => !promotedTupleSet.Contains(tupleId))
            .ToList();
        HashSet<string> missingTupleSet = new(missingRequiredPlatformHeadRidTuples, StringComparer.OrdinalIgnoreCase);

        JsonObject coverage = new()
        {
            ["requiredDesktopPlatforms"] = JsonSerializer.SerializeToNode(requiredDesktopPlatforms, JsonOptions),
            ["requiredDesktopHeads"] = JsonSerializer.SerializeToNode(requiredDesktopHeads, JsonOptions),
            ["promotedInstallerTuples"] = JsonSerializer.SerializeToNode(promotedInstallerTuples, JsonOptions),
            ["promotedPlatformHeads"] = JsonSerializer.SerializeToNode(promotedPlatformHeads, JsonOptions),
            ["requiredDesktopPlatformHeadRidTuples"] = JsonSerializer.SerializeToNode(requiredDesktopPlatformHeadRidTuples, JsonOptions),
            ["promotedPlatformHeadRidTuples"] = JsonSerializer.SerializeToNode(promotedDesktopPlatformHeadRidTuples, JsonOptions),
            ["missingRequiredPlatforms"] = JsonSerializer.SerializeToNode(missingRequiredPlatforms, JsonOptions),
            ["missingRequiredHeads"] = JsonSerializer.SerializeToNode(missingRequiredHeads, JsonOptions),
            ["missingRequiredPlatformHeadPairs"] = JsonSerializer.SerializeToNode(missingRequiredPlatformHeadPairs, JsonOptions),
            ["missingRequiredPlatformHeadRidTuples"] = JsonSerializer.SerializeToNode(missingRequiredPlatformHeadRidTuples, JsonOptions),
            ["externalProofRequests"] = FilterExternalProofRequests(sourceCoverage, missingTupleSet),
            ["desktopRouteTruth"] = JsonSerializer.SerializeToNode(
                BuildDesktopRouteTruth(
                    artifactRows,
                    requiredDesktopPlatforms,
                    NormalizeToken(channelStatus),
                    NormalizeToken(rolloutState),
                    rolloutReason?.Trim() ?? string.Empty,
                    knownIssueSummary?.Trim() ?? string.Empty),
                JsonOptions),
            ["complete"] = missingRequiredPlatforms.Count == 0
                && missingRequiredHeads.Count == 0
                && missingRequiredPlatformHeadPairs.Count == 0
                && missingRequiredPlatformHeadRidTuples.Count == 0
        };

        return coverage;
    }

    private static List<string> ReadSourceCoverageStringList(JsonObject? sourceCoverage, string propertyName)
    {
        if (sourceCoverage?[propertyName] is not JsonArray values)
        {
            return [];
        }

        return values
            .Select(static value => NormalizeToken(GetJsonString(value)))
            .Where(static value => !string.IsNullOrWhiteSpace(value))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .OrderBy(static value => value, StringComparer.Ordinal)
            .ToList();
    }

    private static JsonArray FilterExternalProofRequests(JsonObject? sourceCoverage, HashSet<string> missingTupleIds)
    {
        JsonArray filtered = [];
        if (missingTupleIds.Count == 0)
        {
            return filtered;
        }

        if (sourceCoverage?["externalProofRequests"] is not JsonArray requests)
        {
            return filtered;
        }

        foreach (JsonNode? node in requests)
        {
            if (node is not JsonObject request)
            {
                continue;
            }

            string tupleId = NormalizeToken(GetJsonString(request["tupleId"]));
            if (string.IsNullOrWhiteSpace(tupleId) || !missingTupleIds.Contains(tupleId))
            {
                continue;
            }

            filtered.Add(request.DeepClone());
        }

        return filtered;
    }

    private static List<Dictionary<string, string>> BuildDesktopRouteTruth(
        IReadOnlyList<CanonicalArtifactState> artifacts,
        IReadOnlyList<string> requiredDesktopPlatforms,
        string channelStatus,
        string rolloutState,
        string rolloutReason,
        string knownIssueSummary)
    {
        Dictionary<string, CanonicalArtifactState> promotedByPlatformHeadRid = new(StringComparer.OrdinalIgnoreCase);
        Dictionary<string, HashSet<string>> requiredRidsByPlatform = requiredDesktopPlatforms.ToDictionary(
            static platform => platform,
            static platform => new HashSet<string>(
                DefaultRequiredDesktopPlatformRids.TryGetValue(platform, out string[]? rids) ? rids : [],
                StringComparer.OrdinalIgnoreCase),
            StringComparer.OrdinalIgnoreCase);

        foreach (CanonicalArtifactState artifact in artifacts)
        {
            if (!requiredDesktopPlatforms.Contains(artifact.Platform, StringComparer.OrdinalIgnoreCase)
                || !DesktopRouteTruthHeads.Contains(artifact.Head, StringComparer.OrdinalIgnoreCase)
                || string.IsNullOrWhiteSpace(artifact.Rid)
                || !IsDesktopInstallMedia(artifact.Platform, artifact.Kind))
            {
                continue;
            }

            requiredRidsByPlatform[artifact.Platform].Add(artifact.Rid);
            string key = $"{artifact.Platform}|{artifact.Head}|{artifact.Rid}";
            if (!promotedByPlatformHeadRid.TryGetValue(key, out CanonicalArtifactState? current)
                || CompareArtifactSelectionKey(artifact, current) < 0)
            {
                promotedByPlatformHeadRid[key] = artifact;
            }
        }

        List<Dictionary<string, string>> rows = [];
        foreach (string platform in requiredDesktopPlatforms)
        {
            IEnumerable<string> rids = requiredRidsByPlatform.TryGetValue(platform, out HashSet<string>? ridSet)
                ? ridSet.OrderBy(static value => value, StringComparer.Ordinal)
                : Enumerable.Empty<string>();
            foreach (string rid in rids)
            {
                foreach (string head in DesktopRouteTruthHeads)
                {
                    promotedByPlatformHeadRid.TryGetValue($"{platform}|{head}|{rid}", out CanonicalArtifactState? artifact);
                    string routeRole = DesktopRouteRoles[head];
                    string arch = artifact?.Arch
                        ?? (RidToPlatformArch.TryGetValue(rid, out (string Platform, string Arch) platformArch) ? platformArch.Arch : string.Empty);
                    string artifactId = artifact?.ArtifactId ?? string.Empty;
                    bool promoted = artifact is not null;
                    string tupleLabel = $"{platform}/{rid}";
                    string routeTupleLabel = $"{head}:{platform}:{rid}";
                    string fallbackRouteTupleLabel = $"blazor-desktop:{platform}:{rid}";
                    (string RevokeState, string RevokeReason) revoke = DesktopRouteRevokePosture(
                        artifact,
                        channelStatus,
                        rolloutState,
                        rolloutReason,
                        knownIssueSummary);
                    string revokeSource = artifact is null
                        ? string.Equals(revoke.RevokeState, "revoked", StringComparison.Ordinal)
                            ? "channel"
                            : "none"
                        : DesktopRouteArtifactIsRevoked(artifact)
                            ? "artifact"
                            : string.Equals(revoke.RevokeState, "revoked", StringComparison.Ordinal)
                                ? "channel"
                                : "none";
                    string revokeReason = revoke.RevokeState == "revoked"
                        ? $"Registry revoke marker is active for {routeTupleLabel}: {revoke.RevokeReason}"
                        : $"No registry revoke marker is active for {routeTupleLabel}.";

                    string promotionState;
                    string promotionReasonCode;
                    string promotionReason;
                    string installPosture;
                    string installPostureReason;
                    if (promoted)
                    {
                        promotionState = "promoted";
                        promotionReasonCode = "installer_smoke_and_release_proof_passed";
                        string promotionSubject = DesktopRoutePromotionSubject(head);
                        promotionReason = routeRole == "primary"
                            ? $"{promotionSubject} tuple {routeTupleLabel} for {tupleLabel} is promoted because the flagship head is present on the registry shelf and passed independent startup verification and release verification gates for this channel."
                            : $"{promotionSubject} tuple {routeTupleLabel} for {tupleLabel} is promoted for recovery/manual routing because it is present on the registry shelf and passed the current startup verification and release verification gates for this channel.";
                        installPosture = "installer_first";
                        installPostureReason = $"Promoted installer media {artifactId} is present for {AppLabels[head]} tuple {routeTupleLabel} on {tupleLabel}.";
                    }
                    else
                    {
                        promotionState = "proof_required";
                        promotionReasonCode = "missing_artifact_or_startup_smoke_proof";
                        string promotionSubject = DesktopRoutePromotionSubject(head);
                        promotionReason = routeRole == "primary"
                            ? $"{promotionSubject} tuple {routeTupleLabel} for {tupleLabel} is not promoted until the flagship head has matching artifact bytes and fresh startup verification for this channel."
                            : $"{promotionSubject} tuple {routeTupleLabel} for {tupleLabel} is retained for recovery/manual routing on {tupleLabel} but is not promoted until matching artifact bytes and fresh startup verification are present.";
                        installPosture = "proof_capture_required";
                        installPostureReason = $"Do not present {routeTupleLabel} as installable until the missing tuple proof is captured.";
                    }

                    string parityPosture;
                    string updateEligibility;
                    string updateEligibilityReason;
                    string rollbackState;
                    string rollbackReasonCode;
                    string rollbackReason;
                    if (routeRole == "primary")
                    {
                        parityPosture = "flagship_primary";
                        if (promoted)
                        {
                            updateEligibility = "eligible";
                            updateEligibilityReason = $"Primary-route {AppLabels[head]} tuple {routeTupleLabel} is promoted for {tupleLabel}.";
                        }
                        else
                        {
                            updateEligibility = "blocked_missing_proof";
                            updateEligibilityReason = $"Primary-route updates are blocked until {routeTupleLabel} is promoted.";
                        }

                        promotedByPlatformHeadRid.TryGetValue($"{platform}|blazor-desktop|{rid}", out CanonicalArtifactState? fallbackArtifact);
                        bool fallbackRevoked = DesktopRouteArtifactIsRevoked(fallbackArtifact);
                        bool fallbackPromoted = fallbackArtifact is not null && !fallbackRevoked;
                        if (fallbackPromoted)
                        {
                            rollbackState = "fallback_available";
                            rollbackReasonCode = "promoted_fallback_available";
                            rollbackReason = $"A promoted fallback route {fallbackRouteTupleLabel} exists for primary route {routeTupleLabel} on {tupleLabel}.";
                        }
                        else if (fallbackRevoked)
                        {
                            (string _, string FallbackRevokeReason) = DesktopRouteRevokePosture(
                                fallbackArtifact,
                                channelStatus,
                                rolloutState,
                                rolloutReason,
                                knownIssueSummary);
                            string fallbackRevokeReason = $"Registry revoke marker is active for {fallbackRouteTupleLabel}: {FallbackRevokeReason}";
                            rollbackState = "manual_recovery_required";
                            rollbackReasonCode = "fallback_revoked_for_tuple";
                            rollbackReason = $"Fallback route {fallbackRouteTupleLabel} is revoked for {tupleLabel}, so primary route {routeTupleLabel} requires manual recovery: {fallbackRevokeReason}";
                        }
                        else
                        {
                            if (promoted)
                            {
                                rollbackState = "primary_reinstall_available";
                                rollbackReasonCode = "primary_installer_reinstall_available";
                                rollbackReason = $"Fallback route {fallbackRouteTupleLabel} remains an unpromoted compatibility lane for {tupleLabel}; recover {routeTupleLabel} from the promoted primary installer {artifactId} until a separately proved fallback is published.";
                            }
                            else
                            {
                                rollbackState = "manual_recovery_required";
                                rollbackReasonCode = "fallback_missing_artifact_or_startup_smoke_proof";
                                rollbackReason = $"Fallback route {fallbackRouteTupleLabel} is not promoted for {tupleLabel} because matching artifact bytes and fresh startup verification are still required; primary route {routeTupleLabel} therefore requires manual recovery.";
                            }
                        }
                    }
                    else
                    {
                        parityPosture = "explicit_fallback";
                        if (promoted)
                        {
                            updateEligibility = "manual_fallback";
                            updateEligibilityReason = $"Fallback {AppLabels[head]} tuple {routeTupleLabel} is promoted for {tupleLabel} recovery/manual selection, not automatic primary updates.";
                            rollbackState = "fallback_available";
                            rollbackReasonCode = "fallback_promoted_for_recovery";
                            rollbackReason = $"Fallback {AppLabels[head]} tuple {routeTupleLabel} is promoted for {tupleLabel} rollback or recovery routing.";
                        }
                        else
                        {
                            updateEligibility = "blocked_missing_proof";
                            updateEligibilityReason = $"Fallback route {routeTupleLabel} is not update-eligible until promoted.";
                            rollbackState = "fallback_not_promoted";
                            rollbackReasonCode = "fallback_missing_artifact_or_startup_smoke_proof";
                            rollbackReason = $"Fallback route {routeTupleLabel} needs artifact and startup verification before rollback use.";
                        }
                    }

                    if (revoke.RevokeState == "revoked")
                    {
                        string routeRoleLabel = routeRole == "primary" ? "primary-route" : "fallback";
                        promotionState = "revoked";
                        promotionReasonCode = "registry_revoke_marker_active";
                        promotionReason = $"Registry revoke truth blocks {routeRoleLabel} promotion for {routeTupleLabel}: {revokeReason}";
                        updateEligibility = "blocked_revoked";
                        updateEligibilityReason = $"Updates are blocked because {routeTupleLabel} is revoked in registry truth: {revokeReason}";
                        rollbackState = "revoked";
                        rollbackReasonCode = "registry_revoke_marker_active";
                        rollbackReason = $"Do not use {routeTupleLabel} for rollback while its registry revoke marker is active: {revokeReason}";
                        installPosture = "revoked";
                        installPostureReason = $"Do not present {routeTupleLabel} as installable while revoked: {revokeReason}";
                    }

                    rows.Add(new Dictionary<string, string>(StringComparer.Ordinal)
                    {
                        ["tupleId"] = routeTupleLabel,
                        ["head"] = head,
                        ["platform"] = platform,
                        ["rid"] = rid,
                        ["arch"] = arch,
                        ["artifactId"] = artifactId,
                        ["routeRole"] = routeRole,
                        ["routeRoleReasonCode"] = DesktopRouteRoleReasonCode(head),
                        ["routeRoleReason"] = DesktopRouteRoleReason(head, platform, rid),
                        ["promotionState"] = promotionState,
                        ["promotionReasonCode"] = promotionReasonCode,
                        ["promotionReason"] = promotionReason,
                        ["parityPosture"] = parityPosture,
                        ["updateEligibility"] = updateEligibility,
                        ["updateEligibilityReason"] = updateEligibilityReason,
                        ["rollbackState"] = rollbackState,
                        ["rollbackReasonCode"] = rollbackReasonCode,
                        ["rollbackReason"] = rollbackReason,
                        ["revokeState"] = revoke.RevokeState,
                        ["revokeSource"] = revokeSource,
                        ["revokeReasonCode"] = revoke.RevokeState == "revoked"
                            ? "registry_revoke_marker_active"
                            : "no_registry_revoke_marker",
                        ["revokeReason"] = revokeReason,
                        ["installPosture"] = installPosture,
                        ["installPostureReason"] = installPostureReason,
                        ["publicInstallRoute"] = $"/downloads/install/{head}-{rid}-installer"
                    });
                }
            }
        }

        return rows
            .OrderBy(static row => row["platform"], StringComparer.Ordinal)
            .ThenBy(static row => row["head"], StringComparer.Ordinal)
            .ThenBy(static row => row["rid"], StringComparer.Ordinal)
            .ThenBy(static row => row["tupleId"], StringComparer.Ordinal)
            .ToList();
    }

    private static string DeriveRolloutState(
        string? channel,
        string? status,
        bool proofPassed,
        bool desktopCoverageComplete,
        string proofFreshnessStatus,
        PrivacyLaunchGateSnapshot privacyLaunchGate)
    {
        string normalizedStatus = NormalizeToken(status);
        if (!string.Equals(normalizedStatus, "published", StringComparison.Ordinal))
        {
            return "unpublished";
        }

        if (!desktopCoverageComplete)
        {
            return "coverage_incomplete";
        }

        if (ReleaseReadinessBlockerClause(proofFreshnessStatus, privacyLaunchGate) is not null)
        {
            return "public_release_review_required";
        }

        string normalizedChannel = NormalizeToken(channel);
        if (proofPassed)
        {
            if (normalizedChannel is "stable" or "public_stable" or "docker")
            {
                return "public_stable";
            }

            return normalizedChannel == "preview"
                ? "promoted_preview"
                : normalizedChannel;
        }

        return normalizedChannel == "preview"
            ? "promoted_preview"
            : normalizedChannel;
    }

    private static string DeriveRolloutReason(
        string? channel,
        string? status,
        bool proofPassed,
        bool desktopCoverageComplete,
        JsonObject coverage,
        string proofFreshnessStatus,
        PrivacyLaunchGateSnapshot privacyLaunchGate)
    {
        string normalizedStatus = NormalizeToken(status);
        if (!string.Equals(normalizedStatus, "published", StringComparison.Ordinal))
        {
            return "No published artifact shelf exists yet.";
        }

        if (!desktopCoverageComplete)
        {
            return "Current shelf is published, but promotion stays blocked because "
                + DesktopTupleCoverageGapSummary(coverage)
                + ".";
        }

        string? readinessBlocker = ReleaseReadinessBlockerClause(
            proofFreshnessStatus,
            privacyLaunchGate);
        if (readinessBlocker is not null)
        {
            return "Current shelf is published, but release posture stays review-required because "
                + readinessBlocker
                + ".";
        }

        if (proofPassed)
        {
            return "Current release shelf passed the local release run before publication.";
        }

        return string.Equals(NormalizeToken(channel), "preview", StringComparison.Ordinal)
            ? "Current preview shelf is published, but the release run should be repeated before widening trust claims."
            : "Current release shelf is published.";
    }

    private static string DeriveSupportabilityState(
        string? channel,
        string? status,
        bool proofPassed,
        bool desktopCoverageComplete,
        string proofFreshnessStatus,
        PrivacyLaunchGateSnapshot privacyLaunchGate)
    {
        string normalizedStatus = NormalizeToken(status);
        if (!string.Equals(normalizedStatus, "published", StringComparison.Ordinal))
        {
            return "unpublished";
        }

        if (!desktopCoverageComplete)
        {
            return "review_required";
        }

        if (ReleaseReadinessBlockerClause(proofFreshnessStatus, privacyLaunchGate) is not null)
        {
            return "review_required";
        }

        return proofPassed
            ? NormalizeToken(channel) switch
            {
                "public_stable" => "gold_supported",
                "stable" => "gold_supported",
                "docker" => "gold_supported",
                _ => "preview_supported",
            }
            : "review_required";
    }

    private static string DeriveSupportabilitySummary(
        string? channel,
        string? status,
        bool proofPassed,
        bool desktopCoverageComplete,
        JsonObject coverage,
        IReadOnlyList<string>? proofJourneys,
        string proofFreshnessStatus,
        PrivacyLaunchGateSnapshot privacyLaunchGate)
    {
        string normalizedStatus = NormalizeToken(status);
        if (!string.Equals(normalizedStatus, "published", StringComparison.Ordinal))
        {
            return "No published channel support posture exists because no release page is live.";
        }

        if (!desktopCoverageComplete)
        {
            return "Treat the current release as review-required because "
                + DesktopTupleCoverageGapSummary(coverage)
                + ".";
        }

        string? readinessBlocker = ReleaseReadinessBlockerClause(
            proofFreshnessStatus,
            privacyLaunchGate);
        if (readinessBlocker is not null)
        {
            return "Treat the current release as review-required because "
                + readinessBlocker
                + ".";
        }

        if (!proofPassed)
        {
            return "Treat the current release as review-required until release status and support closure are ready.";
        }

        List<string> journeys = proofJourneys?
            .Select(NormalizeToken)
            .Where(static value => !string.IsNullOrWhiteSpace(value))
            .ToList()
            ?? [];
        if (journeys.Count == 0)
        {
            return NormalizeToken(channel) is "public_stable" or "stable" or "docker"
                ? "Current public release is supported on the promoted routes. Recent coverage includes install, bounded offline prefetch, and current support follow-up."
                : "Current preview release is supported on the promoted routes. Recent coverage includes install, bounded offline prefetch, and current support follow-up.";
        }

        List<string> proofNotes = [];
        if (journeys.Contains("build_explain_publish", StringComparer.Ordinal))
        {
            proofNotes.Add("install guidance");
        }

        if (journeys.Contains("campaign_session_recover_recap", StringComparer.Ordinal))
        {
            proofNotes.Add("session recovery");
        }

        if (journeys.Contains("install_claim_restore_continue", StringComparer.Ordinal))
        {
            proofNotes.Add("account return");
        }

        if (journeys.Contains("report_cluster_release_notify", StringComparer.Ordinal))
        {
            proofNotes.Add("release updates");
        }

        if (journeys.Contains("organize_community_and_close_loop", StringComparer.Ordinal))
        {
            proofNotes.Add("community wrap-up");
        }

        string proofNoteClause = proofNotes.Count > 0
            ? " Recent coverage includes " + string.Join(", ", proofNotes) + ","
            : " Recent coverage includes install,";
        return (NormalizeToken(channel) is "public_stable" or "stable" or "docker"
                ? "Current public release is supported on the promoted routes."
                : "Current preview release is supported on the promoted routes.")
            + proofNoteClause
            + " bounded offline prefetch, and current support follow-up.";
    }

    private static string DeriveKnownIssueSummary(
        string? channel,
        string? status,
        bool proofPassed,
        bool desktopCoverageComplete,
        JsonObject coverage,
        IReadOnlyList<string>? proofJourneys,
        string proofFreshnessStatus,
        PrivacyLaunchGateSnapshot privacyLaunchGate)
    {
        string normalizedStatus = NormalizeToken(status);
        if (!string.Equals(normalizedStatus, "published", StringComparison.Ordinal))
        {
            return "No active channel issues are published because the release page is still empty.";
        }

        if (!desktopCoverageComplete)
        {
            return "Known issue: " + DesktopTupleCoverageGapSummary(coverage) + ".";
        }

        string? readinessBlocker = ReleaseReadinessBlockerClause(
            proofFreshnessStatus,
            privacyLaunchGate);
        if (readinessBlocker is not null)
        {
            return "Known issue: " + readinessBlocker + ".";
        }

        if (!proofPassed)
        {
            return $"The {NormalizeToken(channel)} release page is visible, but known-issue review should stay front-and-center until the current verification is refreshed.";
        }

        List<string> journeys = proofJourneys?
            .Select(NormalizeToken)
            .Where(static value => !string.IsNullOrWhiteSpace(value))
            .ToList()
            ?? [];
        List<string> proofNotes = [];
        if (journeys.Contains("install_claim_restore_continue", StringComparer.Ordinal))
        {
            proofNotes.Add("account return");
        }

        if (journeys.Contains("report_cluster_release_notify", StringComparer.Ordinal))
        {
            proofNotes.Add("release updates");
        }

        if (journeys.Contains("organize_community_and_close_loop", StringComparer.Ordinal))
        {
            proofNotes.Add("community wrap-up");
        }

        string proofNoteClause = proofNotes.Count > 0
            ? ", " + string.Join(", ", proofNotes)
            : string.Empty;
        if (NormalizeToken(channel) is "public_stable" or "stable" or "docker")
        {
            return "No blocking release caveat is mirrored for the current public release. The promoted routes have recent install"
                + proofNoteClause
                + ", bounded offline prefetch, and current support follow-up coverage.";
        }

        return "Preview caveats still apply, but the current release has recent install"
            + proofNoteClause
            + ", bounded offline prefetch, and current support follow-up coverage.";
    }

    private static string DeriveFixAvailabilitySummary(
        string? status,
        bool proofPassed,
        bool desktopCoverageComplete,
        string proofFreshnessStatus,
        PrivacyLaunchGateSnapshot privacyLaunchGate)
    {
        string normalizedStatus = NormalizeToken(status);
        if (!string.Equals(normalizedStatus, "published", StringComparison.Ordinal))
        {
            return "Fix notices should stay pending until a published release exists.";
        }

        if (!desktopCoverageComplete)
        {
            return "Do not send fixed notices until required desktop build coverage is complete for the promoted release.";
        }

        string? readinessBlocker = ReleaseReadinessBlockerClause(
            proofFreshnessStatus,
            privacyLaunchGate);
        if (readinessBlocker is not null)
        {
            if (privacyLaunchGate.BlocksReleaseSupportability)
            {
                return ProofFreshnessBlocksOutputReadiness(proofFreshnessStatus)
                    ? "Only send fixed notices after stale or incomplete proof receipts and Hosted Build privacy, retention, recovery, and erasure blockers are cleared and the affected install can receive the published channel artifact now on the release page."
                    : "Only send fixed notices after Hosted Build privacy, retention, recovery, and erasure review clears and the affected install can receive the published channel artifact now on the release page.";
            }

            return "Only send fixed notices after stale or incomplete proof receipts are cleared and the affected "
                + "install can receive the published channel artifact now on the release page.";
        }

        return proofPassed
            ? "Only send fixed notices after the affected install can receive the published channel artifact now on the release page."
            : "Check the live release page before sending a fixed notice.";
    }

    private static string? ReleaseReadinessBlockerClause(
        string proofFreshnessStatus,
        PrivacyLaunchGateSnapshot privacyLaunchGate)
    {
        bool proofFreshnessBlocks = ProofFreshnessBlocksOutputReadiness(proofFreshnessStatus);
        bool privacyBlocks = privacyLaunchGate.BlocksReleaseSupportability;
        return (proofFreshnessBlocks, privacyBlocks) switch
        {
            (true, true) => "stale or incomplete proof receipts and Hosted Build privacy, retention, recovery, and erasure review still block launch-readiness claims",
            (true, false) => "stale or incomplete proof receipts still block launch-readiness claims",
            (false, true) => "Hosted Build privacy, retention, recovery, and erasure review still blocks launch-readiness claims",
            _ => null,
        };
    }

    private static bool DesktopTupleCoverageIsComplete(JsonObject coverage)
        => ToJsonStringList(coverage["missingRequiredPlatforms"]).Count == 0
            && ToJsonStringList(coverage["missingRequiredHeads"]).Count == 0
            && ToJsonStringList(coverage["missingRequiredPlatformHeadPairs"]).Count == 0
            && ToJsonStringList(coverage["missingRequiredPlatformHeadRidTuples"]).Count == 0;

    private static string DesktopTupleCoverageGapSummary(JsonObject? coverage)
    {
        if (coverage is null)
        {
            return "required desktop build coverage is unavailable";
        }

        List<string> details = [];
        List<string> missingPlatforms = ToJsonStringList(coverage["missingRequiredPlatforms"]);
        List<string> missingHeads = ToJsonStringList(coverage["missingRequiredHeads"]);
        List<string> missingPairs = ToJsonStringList(coverage["missingRequiredPlatformHeadPairs"]);
        List<string> missingTuples = ToJsonStringList(coverage["missingRequiredPlatformHeadRidTuples"]);
        if (missingPlatforms.Count > 0)
        {
            details.Add("platforms: " + string.Join(", ", missingPlatforms));
        }

        if (missingHeads.Count > 0)
        {
            details.Add("heads: " + string.Join(", ", missingHeads));
        }

        if (missingPairs.Count > 0)
        {
            details.Add("pairs: " + string.Join(", ", missingPairs));
        }

        if (missingTuples.Count > 0)
        {
            details.Add("build combinations: " + string.Join(", ", missingTuples));
        }

        return details.Count == 0
            ? "required desktop build coverage is complete"
            : "required desktop build coverage is incomplete (" + string.Join("; ", details) + ")";
    }

    private static bool ProofPassed(string? proofStatus)
        => string.Equals(NormalizeReleaseProofStatus(proofStatus), "passed", StringComparison.Ordinal);

    private static string NormalizeReleaseProofStatus(string? proofStatus)
        => NormalizeToken(proofStatus).Replace('-', '_') switch
        {
            "pass" or "passed" or "ready" => "passed",
            "reviewrequired" or "review_required" => "review_required",
            string normalized => normalized
        };

    private static DateTimeOffset? TryGetJsonDateTimeOffset(JsonNode? node)
    {
        string? raw = GetJsonString(node);
        return DateTimeOffset.TryParse(raw, out DateTimeOffset parsed)
            ? parsed
            : null;
    }

    private static string ExtractProofStatus(JsonObject manifest)
        => NormalizeToken(GetJsonString((manifest["releaseProof"] as JsonObject)?["status"]));

    private static IReadOnlyList<string> ExtractProofJourneys(JsonObject manifest)
        => ToJsonStringList((manifest["releaseProof"] as JsonObject)?["journeysPassed"])
            .Select(NormalizeToken)
            .Where(static value => !string.IsNullOrWhiteSpace(value))
            .ToArray();

    private static (string RevokeState, string RevokeReason) DesktopRouteRevokePosture(
        CanonicalArtifactState? artifact,
        string channelStatus,
        string rolloutState,
        string rolloutReason,
        string knownIssueSummary)
    {
        if (string.Equals(channelStatus, "revoked", StringComparison.Ordinal)
            || string.Equals(rolloutState, "revoked", StringComparison.Ordinal))
        {
            string reason = !string.IsNullOrWhiteSpace(rolloutReason)
                ? rolloutReason
                : !string.IsNullOrWhiteSpace(knownIssueSummary)
                    ? knownIssueSummary
                    : "The release channel is revoked for this desktop tuple.";
            return ("revoked", reason);
        }

        if (DesktopRouteArtifactIsRevoked(artifact))
        {
            string reason = artifact?.RevokeReason
                ?? artifact?.ArtifactRolloutReason
                ?? artifact?.CompatibilityReason
                ?? artifact?.ArtifactKnownIssueSummary
                ?? knownIssueSummary;
            if (string.IsNullOrWhiteSpace(reason))
            {
                reason = "The artifact registry state is revoked for this desktop tuple.";
            }

            return ("revoked", reason);
        }

        return ("not_revoked", "No registry revoke marker is active for this channel tuple.");
    }

    private static bool DesktopRouteArtifactIsRevoked(CanonicalArtifactState? artifact)
        => artifact is not null
            && (
                string.Equals(artifact.ArtifactStatus, "revoked", StringComparison.Ordinal)
                || string.Equals(artifact.ArtifactRolloutState, "revoked", StringComparison.Ordinal)
                || string.Equals(artifact.CompatibilityState, "revoked", StringComparison.Ordinal)
            );

    private static int CompareArtifactSelectionKey(CanonicalArtifactState left, CanonicalArtifactState right)
    {
        int revokedComparison = (DesktopRouteArtifactIsRevoked(left) ? 1 : 0)
            .CompareTo(DesktopRouteArtifactIsRevoked(right) ? 1 : 0);
        if (revokedComparison != 0)
        {
            return revokedComparison;
        }

        return string.Compare(left.ArtifactId, right.ArtifactId, StringComparison.Ordinal);
    }

    private static string DesktopRouteRoleReason(string head, string platform, string rid)
    {
        string tupleLabel = string.IsNullOrWhiteSpace(rid) ? platform : $"{platform}/{rid}";
        string routeTupleLabel = string.IsNullOrWhiteSpace(rid) ? $"{head}:{platform}" : $"{head}:{platform}:{rid}";
        if (string.Equals(DesktopRouteRoles[head], "primary", StringComparison.Ordinal))
        {
            return $"{AppLabels[head]} route {routeTupleLabel} is the flagship desktop route for {tupleLabel} and must carry independent startup verification before promotion.";
        }

        return $"{AppLabels[head]} route {routeTupleLabel} is retained as an explicit fallback route for {tupleLabel}; it cannot satisfy the primary-route promise.";
    }

    private static string DesktopRouteRoleReasonCode(string head)
        => string.Equals(DesktopRouteRoles[head], "primary", StringComparison.Ordinal)
            ? "primary_flagship_head"
            : "fallback_recovery_head";

    private static string DesktopRoutePromotionSubject(string head)
        => string.Equals(DesktopRouteRoles[head], "primary", StringComparison.Ordinal)
            ? $"Primary-route {AppLabels[head]}"
            : $"Fallback {AppLabels[head]}";

    private static bool IsDesktopInstallMedia(string platform, string kind)
        => string.Equals(platform, "macos", StringComparison.Ordinal)
            ? kind is "installer" or "dmg" or "pkg"
            : string.Equals(kind, "installer", StringComparison.Ordinal);

    private static List<CanonicalArtifactState> ExtractCanonicalArtifactRows(JsonArray artifacts)
    {
        List<CanonicalArtifactState> rows = [];
        foreach (JsonNode? node in artifacts)
        {
            if (node is not JsonObject artifact)
            {
                continue;
            }

            string rid = NormalizeToken(GetJsonString(artifact["rid"]));
            string platform = NormalizePlatformToken(GetJsonString(artifact["platform"]));
            if (string.IsNullOrWhiteSpace(platform)
                && RidToPlatformArch.TryGetValue(rid, out (string Platform, string Arch) platformArch))
            {
                platform = platformArch.Platform;
            }

            string arch = NormalizeToken(GetJsonString(artifact["arch"]));
            if (string.IsNullOrWhiteSpace(arch)
                && RidToPlatformArch.TryGetValue(rid, out (string Platform, string Arch) archMapping))
            {
                arch = archMapping.Arch;
            }
            if (string.IsNullOrWhiteSpace(rid))
            {
                rid = InferRid(platform, arch);
            }

            rows.Add(new CanonicalArtifactState(
                ArtifactId: NormalizeToken(GetJsonString(artifact["artifactId"]) ?? GetJsonString(artifact["id"])),
                Head: NormalizeToken(GetJsonString(artifact["head"])),
                Platform: platform,
                Rid: rid,
                Arch: arch,
                Kind: NormalizeToken(GetJsonString(artifact["kind"])),
                ArtifactStatus: NormalizeToken(GetJsonString(artifact["status"])),
                ArtifactRolloutState: NormalizeToken(GetJsonString(artifact["rolloutState"]) ?? GetJsonString(artifact["rollout_state"])),
                ArtifactRolloutReason: (GetJsonString(artifact["rolloutReason"]) ?? GetJsonString(artifact["rollout_reason"]) ?? string.Empty).Trim(),
                RevokeReason: (GetJsonString(artifact["revokeReason"]) ?? GetJsonString(artifact["revoke_reason"]) ?? string.Empty).Trim(),
                CompatibilityState: NormalizeToken(GetJsonString(artifact["compatibilityState"]) ?? GetJsonString(artifact["compatibility_state"])),
                CompatibilityReason: (GetJsonString(artifact["compatibilityReason"]) ?? GetJsonString(artifact["compatibility_reason"]) ?? string.Empty).Trim(),
                ArtifactKnownIssueSummary: (GetJsonString(artifact["knownIssueSummary"]) ?? GetJsonString(artifact["known_issue_summary"]) ?? string.Empty).Trim()));
        }

        return rows;
    }

    private static string NormalizeToken(string? value)
        => string.IsNullOrWhiteSpace(value)
            ? string.Empty
            : value.Trim().ToLowerInvariant();

    private static string NormalizePlatformToken(string? value)
    {
        string normalized = NormalizeToken(value);
        return normalized switch
        {
            "win" => "windows",
            "osx" => "macos",
            _ => normalized
        };
    }

    private static string InferRid(string platform, string arch)
        => platform switch
        {
            "windows" when string.Equals(arch, "arm64", StringComparison.Ordinal) => "win-arm64",
            "windows" => "win-x64",
            "macos" when string.Equals(arch, "x64", StringComparison.Ordinal) => "osx-x64",
            "macos" => "osx-arm64",
            "linux" when string.Equals(arch, "arm64", StringComparison.Ordinal) => "linux-arm64",
            "linux" => "linux-x64",
            _ => string.Empty
        };

    private static string? GetJsonString(JsonNode? node)
        => node switch
        {
            null => null,
            JsonValue value => value.TryGetValue<string>(out string? stringValue)
                ? stringValue
                : value.ToJsonString().Trim('"'),
            _ => node.ToJsonString()
        };

    private static List<string> ToJsonStringList(JsonNode? node)
    {
        if (node is not JsonArray array)
        {
            return [];
        }

        return array
            .Select(GetJsonString)
            .Where(static value => !string.IsNullOrWhiteSpace(value))
            .Select(static value => value!.Trim())
            .ToList();
    }

    private static JsonArray MergeArrayById(JsonArray? existingArray, JsonArray? incomingArray, string idProperty)
    {
        JsonArray merged = new();
        if (incomingArray is null)
        {
            if (existingArray is not null)
            {
                foreach (JsonNode? item in existingArray)
                {
                    merged.Add(item?.DeepClone());
                }
            }

            return merged;
        }

        Dictionary<string, JsonObject> incomingById = incomingArray
            .OfType<JsonObject>()
            .Where(item => item[idProperty]?.GetValue<string>() is { Length: > 0 })
            .ToDictionary(item => item[idProperty]!.GetValue<string>(), item => item, StringComparer.OrdinalIgnoreCase);

        HashSet<string> seen = new(StringComparer.OrdinalIgnoreCase);
        if (existingArray is not null)
        {
            foreach (JsonObject existingItem in existingArray.OfType<JsonObject>())
            {
                string? id = existingItem[idProperty]?.GetValue<string>();
                if (!string.IsNullOrWhiteSpace(id) && incomingById.TryGetValue(id, out JsonObject? replacement))
                {
                    merged.Add(replacement.DeepClone());
                    seen.Add(id);
                    continue;
                }

                merged.Add(existingItem.DeepClone());
                if (!string.IsNullOrWhiteSpace(id))
                {
                    seen.Add(id);
                }
            }
        }

        foreach ((string id, JsonObject item) in incomingById)
        {
            if (!seen.Contains(id))
            {
                merged.Add(item.DeepClone());
            }
        }

        return merged;
    }

    private static void WriteJsonAtomically<T>(string path, T payload)
    {
        string tempPath = $"{path}.{Guid.NewGuid():N}.tmp";
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        File.WriteAllText(tempPath, JsonSerializer.Serialize(payload, JsonOptions));
        File.Move(tempPath, path, overwrite: true);
    }

    private static string ResolveDownloadFileName(PublicReleaseArtifactDto artifact)
        => ResolveArtifactFileName(artifact.FileName, artifact.Url);

    private static string ResolveArtifactFileName(string? fileName, string? url)
    {
        if (!string.IsNullOrWhiteSpace(fileName))
        {
            return Path.GetFileName(fileName.Trim());
        }

        string normalizedUrl = NormalizePublicPath(url);
        string candidate = Path.GetFileName(normalizedUrl);
        if (!string.IsNullOrWhiteSpace(candidate))
        {
            return candidate;
        }

        throw new InvalidDataException("artifact is missing fileName/url.");
    }

    private static string NormalizePublicPath(string? url)
    {
        string raw = (url ?? string.Empty).Trim();
        if (raw.Length == 0)
        {
            return "/";
        }

        if (Uri.TryCreate(raw, UriKind.Absolute, out Uri? absoluteUri))
        {
            string pathAndQuery = absoluteUri.PathAndQuery;
            return string.IsNullOrWhiteSpace(pathAndQuery) ? "/" : pathAndQuery;
        }

        return raw.StartsWith("/") ? raw : $"/{raw}";
    }

    private static bool IsInstallerArtifact(CanonicalArtifactRecord artifact)
    {
        string kind = (artifact.Kind ?? string.Empty).Trim();
        if (kind.Length > 0)
        {
            return kind.Equals("installer", StringComparison.OrdinalIgnoreCase)
                || kind.Equals("dmg", StringComparison.OrdinalIgnoreCase)
                || kind.Equals("pkg", StringComparison.OrdinalIgnoreCase)
                || kind.Equals("msix", StringComparison.OrdinalIgnoreCase);
        }

        string fileName = ResolveArtifactFileName(artifact.FileName, artifact.DownloadUrl);
        return fileName.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)
               || fileName.EndsWith(".deb", StringComparison.OrdinalIgnoreCase)
               || fileName.EndsWith(".dmg", StringComparison.OrdinalIgnoreCase)
               || fileName.EndsWith(".pkg", StringComparison.OrdinalIgnoreCase)
               || fileName.EndsWith(".msix", StringComparison.OrdinalIgnoreCase);
    }

    private static string NormalizePlatform(string? platform)
    {
        string normalized = (platform ?? string.Empty).Trim().ToLowerInvariant();
        if (normalized.Length > 0)
        {
            int separatorIndex = normalized.IndexOfAny(new[] { '-', '_', '/', ' ' });
            if (separatorIndex >= 0)
            {
                normalized = normalized[..separatorIndex];
            }
        }

        return normalized switch
        {
            "mac" or "macos" or "osx" or "darwin" => "macos",
            "win" or "windows" => "windows",
            "linux" => "linux",
            _ => normalized
        };
    }

    private static string NormalizeArtifactDigest(string? digest)
    {
        string normalized = (digest ?? string.Empty).Trim().ToLowerInvariant();
        return normalized.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase)
            ? normalized[7..]
            : normalized;
    }

    private static string Sha256For(string path)
    {
        using var sha = System.Security.Cryptography.SHA256.Create();
        using FileStream stream = File.OpenRead(path);
        return Convert.ToHexString(sha.ComputeHash(stream)).ToLowerInvariant();
    }

    private static string Sha256For(byte[] bytes)
        => Convert.ToHexStringLower(SHA256.HashData(bytes));

    private PublicReleaseManifestDto ValidatePublicShelfCoherence(
        string downloadsRoot,
        string liveCompatibilityManifestPath,
        string liveCanonicalManifestPath,
        IReadOnlyList<string> promotedArtifactIds,
        string expectedGenerationId,
        string expectedCompatibilitySha256,
        string expectedCanonicalSha256)
    {
        if (!File.Exists(liveCompatibilityManifestPath))
        {
            throw new InvalidOperationException("promotion wrote no compatibility manifest.");
        }

        if (!File.Exists(liveCanonicalManifestPath))
        {
            throw new InvalidOperationException("promotion wrote no canonical manifest.");
        }

        if (!FixedTimeDigestEquals(Sha256For(liveCompatibilityManifestPath), expectedCompatibilitySha256))
        {
            throw new InvalidDataException(
                "public compatibility manifest bytes do not match the Registry-verified activation digest.");
        }

        if (!FixedTimeDigestEquals(Sha256For(liveCanonicalManifestPath), expectedCanonicalSha256))
        {
            throw new InvalidDataException(
                "public canonical manifest bytes do not match the Registry-verified activation digest.");
        }

        JsonObject liveCompatibilityManifestObject = LoadJsonObject(liveCompatibilityManifestPath);
        ValidateGenerationBoundManifestRoutes(
            liveCompatibilityManifestObject,
            expectedGenerationId);
        PublicReleaseManifestDto liveCompatibilityManifest = LoadCompatibilityManifest(liveCompatibilityManifestPath);
        HashSet<string> liveCompatibilityIds = liveCompatibilityManifest.Downloads
            .Select(static artifact => artifact.Id)
            .Where(static id => !string.IsNullOrWhiteSpace(id))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        JsonObject liveCanonicalManifest = LoadJsonObject(liveCanonicalManifestPath);
        ValidateGenerationBoundManifestRoutes(
            liveCanonicalManifest,
            expectedGenerationId);
        ValidateIncomingManifestIdentity(
            liveCompatibilityManifestObject,
            liveCompatibilityManifest,
            liveCanonicalManifest,
            allowReviewRequiredProof: true,
            releaseProofAlreadyValidatedBeforeGenerationBinding: true);
        IReadOnlyList<CanonicalArtifactRecord> liveCanonicalArtifacts = LoadCanonicalArtifacts(liveCanonicalManifest);
        ValidateRegistryAuthoredManifestPair(
            liveCompatibilityManifestObject,
            liveCanonicalManifest,
            liveCompatibilityManifest,
            liveCanonicalArtifacts);
        HashSet<string> liveCanonicalIds = liveCanonicalArtifacts
            .Select(static artifact => artifact.ArtifactId)
            .Where(static id => !string.IsNullOrWhiteSpace(id))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        foreach (string artifactId in promotedArtifactIds)
        {
            if (!liveCompatibilityIds.Contains(artifactId))
            {
                throw new InvalidOperationException($"public compatibility manifest is missing promoted artifact {artifactId}.");
            }

            if (!liveCanonicalIds.Contains(artifactId))
            {
                throw new InvalidOperationException($"public canonical manifest is missing promoted artifact {artifactId}.");
            }
        }

        string filesRoot = Path.Combine(downloadsRoot, "files");
        foreach (PublicReleaseArtifactDto artifact in liveCompatibilityManifest.Downloads.Where(download => promotedArtifactIds.Contains(download.Id, StringComparer.OrdinalIgnoreCase)))
        {
            string fileName = ResolveDownloadFileName(artifact);
            string artifactPath = Path.Combine(filesRoot, fileName);
            if (!File.Exists(artifactPath))
            {
                throw new InvalidOperationException($"public downloads root is missing promoted artifact file {fileName}.");
            }
        }

        ValidatePrivacyReadinessCoherence(liveCompatibilityManifest, liveCanonicalManifest);
        ValidateRegistryBoundaryCompatibilityCounts(liveCompatibilityManifest, liveCanonicalManifest);
        ReleaseSelectionService releaseSelection = new(new PublicCanonFileLoader(_configuration));
        return releaseSelection.ApplyAccessPolicy(liveCompatibilityManifest);
    }

    private static bool FixedTimeDigestEquals(string left, string right)
    {
        try
        {
            return CryptographicOperations.FixedTimeEquals(
                Convert.FromHexString(left),
                Convert.FromHexString(right));
        }
        catch (FormatException)
        {
            return false;
        }
    }

    private void ValidatePrivacyReadinessCoherence(
        PublicReleaseManifestDto compatibilityManifest,
        JsonObject canonicalManifest)
    {
        JsonObject? canonicalMetrics = canonicalManifest["publicTrustMetrics"] as JsonObject;
        JsonObject? privacyReadiness = canonicalMetrics?["privacyReadiness"] as JsonObject;
        if (privacyReadiness is null
            || !string.Equals(
                GetJsonString(privacyReadiness["contractName"]),
                PrivacyLaunchGate.ContractName,
                StringComparison.Ordinal)
            || GetJsonInt32(privacyReadiness["contractVersion"]) != PrivacyLaunchGate.ContractVersion)
        {
            throw new InvalidOperationException(
                "RELEASE_CHANNEL.generated.json is missing the supported privacy launch-gate contract.");
        }

        if (!JsonNode.DeepEquals(privacyReadiness, _privacyLaunchGate.ToJsonObject()))
        {
            throw new InvalidOperationException(
                "release shelf privacyReadiness does not match the active privacy launch-gate snapshot.");
        }

        JsonObject? compatibilityMetrics = compatibilityManifest.PublicTrustMetrics is JsonElement metricsElement
            && metricsElement.ValueKind == JsonValueKind.Object
            ? JsonNode.Parse(metricsElement.GetRawText())?.AsObject()
            : null;
        if (!JsonNode.DeepEquals(
                compatibilityMetrics?["privacyReadiness"],
                privacyReadiness))
        {
            throw new InvalidOperationException(
                "release manifests disagree about publicTrustMetrics.privacyReadiness.");
        }

        if (!PrivacyReadinessBlocksOutputReadiness(privacyReadiness))
        {
            return;
        }

        RequirePrivacyReviewSupportability(
            compatibilityManifest.SupportabilityState,
            "releases.json supportabilityState");
        RequirePrivacyReviewSupportability(
            GetJsonString(canonicalManifest["supportabilityState"]),
            "RELEASE_CHANNEL.generated.json supportabilityState");

        JsonObject? publicReleaseChannel = canonicalMetrics?["releaseChannel"] as JsonObject;
        JsonObject? registryReleaseChannel =
            (canonicalManifest["registryBoundaryCoverage"] as JsonObject)?["releaseChannel"] as JsonObject;
        RequirePrivacyReviewSupportability(
            GetJsonString(publicReleaseChannel?["supportabilityState"]),
            "publicTrustMetrics.releaseChannel.supportabilityState");
        RequirePrivacyReviewSupportability(
            GetJsonString(registryReleaseChannel?["supportabilityState"]),
            "registryBoundaryCoverage.releaseChannel.supportabilityState");
        if (!string.Equals(
                NormalizeToken(GetJsonString(publicReleaseChannel?["posture"])),
                "blocked",
                StringComparison.Ordinal)
            || !string.Equals(
                NormalizeToken(GetJsonString(registryReleaseChannel?["publicTrustPosture"])),
                "blocked",
                StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                "privacy review-required release must keep public trust postures blocked.");
        }
    }

    private static void RequirePrivacyReviewSupportability(string? value, string fieldName)
    {
        if (!string.Equals(NormalizeToken(value), "review_required", StringComparison.Ordinal))
        {
            throw new InvalidOperationException(
                $"privacy review-required release must set {fieldName}='review_required'.");
        }
    }

    private static void ValidateRegistryBoundaryCompatibilityCounts(
        PublicReleaseManifestDto compatibilityManifest,
        JsonObject canonicalManifest)
    {
        int publishedArtifactCount = compatibilityManifest.Downloads.Count;
        JsonObject? canonicalCoverage = canonicalManifest["registryBoundaryCoverage"] as JsonObject;
        JsonObject? canonicalCompatibility = canonicalCoverage?["compatibility"] as JsonObject;
        JsonObject? compatibilityCoverage = compatibilityManifest.RegistryBoundaryCoverage is JsonElement compatibilityCoverageElement
            && compatibilityCoverageElement.ValueKind == JsonValueKind.Object
            ? JsonNode.Parse(compatibilityCoverageElement.GetRawText())?.AsObject()
            : null;
        JsonObject? compatibilityBoundary = compatibilityCoverage?["compatibility"] as JsonObject;
        int canonicalCompatible = GetJsonInt32(canonicalCompatibility?["compatibleArtifactCount"]);
        int compatibilityCompatible = GetJsonInt32(compatibilityBoundary?["compatibleArtifactCount"]);
        if (canonicalCompatible != publishedArtifactCount)
        {
            throw new InvalidOperationException(
                $"RELEASE_CHANNEL.generated.json preview_supported release must keep registryBoundaryCoverage.compatibility.compatibleArtifactCount equal to published artifact count ({publishedArtifactCount}), got {canonicalCompatible}");
        }

        if (compatibilityCompatible != publishedArtifactCount)
        {
            throw new InvalidOperationException(
                $"dist/releases.json preview_supported release must keep registryBoundaryCoverage.compatibility.compatibleArtifactCount equal to published artifact count ({publishedArtifactCount}), got {compatibilityCompatible}");
        }
    }

    private sealed record CanonicalArtifactState(
        string ArtifactId,
        string Head,
        string Platform,
        string Rid,
        string Arch,
        string Kind,
        string ArtifactStatus,
        string ArtifactRolloutState,
        string ArtifactRolloutReason,
        string RevokeReason,
        string CompatibilityState,
        string CompatibilityReason,
        string ArtifactKnownIssueSummary);

    private sealed record ActivationInventoryEntry(
        [property: JsonPropertyName("path")] string Path,
        [property: JsonPropertyName("sha256")] string Sha256);

    private sealed record GenerationArtifactRoute(
        string ArtifactId,
        string FileName,
        string? PayloadFileName,
        bool IsOpenPublic);

    private sealed record ActivationCandidateDocument(
        string SchemaVersion,
        string GenerationId,
        string ReleaseVersion,
        string Channel,
        string PublishedAt,
        CurrentManifestBindings Manifests,
        string InventoryDigest,
        IReadOnlyList<ActivationInventoryEntry> Inventory);

    private sealed record ReleaseActivationJournalDocument(
        string SchemaVersion,
        string State,
        ReleaseActivationIntent Intent,
        string? PreviousPointerBase64,
        string TargetPointerBase64);

    private sealed record ReleaseActivationOutcomeDocument(
        string SchemaVersion,
        string State,
        string ActivationReceiptId,
        string IntentSha256,
        DateTimeOffset ResolvedAtUtc);

    private sealed record ReleaseShelfWriterPolicyDocument(
        string SchemaVersion,
        string Mode);

    private sealed record CurrentManifestBinding(
        string Path,
        string Sha256);

    private sealed record CurrentManifestBindings(
        CurrentManifestBinding Canonical,
        CurrentManifestBinding Compatibility);

    private sealed record CurrentPointerDocument(
        string SchemaVersion,
        string GenerationId,
        string ReleaseVersion,
        string Channel,
        string PublishedAt,
        CurrentManifestBindings Manifests,
        string InventoryDigest,
        string ActivatedAt,
        string ActivationReceiptId);

    private sealed record CompatibilityManifestPayload(
        string? Version,
        string? Channel,
        string? ChannelId,
        DateTimeOffset? PublishedAt,
        IReadOnlyList<PublicReleaseArtifactDto>? Downloads,
        string? Source,
        string? Status,
        string? Message,
        bool HasFallbackSource,
        string? RolloutState,
        string? RolloutReason,
        string? SupportabilityState,
        string? SupportabilitySummary,
        string? KnownIssueSummary,
        string? FixAvailabilitySummary,
        CompatibilityProofPayload? ReleaseProof,
        DateTimeOffset? GeneratedAt,
        [property: JsonPropertyName("generated_at")] DateTimeOffset? GeneratedAtAlias,
        string? ContractName,
        [property: JsonPropertyName("contract_name")] string? ContractNameAlias,
        JsonElement? DesktopTupleCoverage,
        JsonElement? RegistryBoundaryCoverage,
        JsonElement? PublicTrustMetrics);

    private sealed record CompatibilityProofPayload(
        string? Status,
        DateTimeOffset? GeneratedAt,
        string? BaseUrl,
        IReadOnlyList<string>? JourneysPassed,
        IReadOnlyList<string>? ProofRoutes,
        JsonElement? UiLocalizationReleaseGate,
        JsonElement? FlagshipReadiness);

    private sealed record CanonicalArtifactRecord(
        [property: JsonPropertyName("artifactId")] string ArtifactId,
        [property: JsonPropertyName("head")] string? Head,
        [property: JsonPropertyName("rid")] string? Rid,
        [property: JsonPropertyName("platform")] string? Platform,
        [property: JsonPropertyName("arch")] string? Arch,
        [property: JsonPropertyName("kind")] string? Kind,
        [property: JsonPropertyName("status")] string? Status,
        [property: JsonPropertyName("rolloutState")] string? RolloutState,
        [property: JsonPropertyName("revokeState")] string? RevokeState,
        [property: JsonPropertyName("fileName")] string? FileName,
        [property: JsonPropertyName("downloadUrl")] string? DownloadUrl,
        [property: JsonPropertyName("sha256")] string? Sha256,
        [property: JsonPropertyName("sizeBytes")] long? SizeBytes,
        [property: JsonPropertyName("platformLabel")] string? PlatformLabel,
        [property: JsonPropertyName("installAccessClass")] string? InstallAccessClass,
        [property: JsonPropertyName("installerMode")] string? InstallerMode,
        [property: JsonPropertyName("payloadFileName")] string? PayloadFileName,
        [property: JsonPropertyName("payloadDownloadUrl")] string? PayloadDownloadUrl,
        [property: JsonPropertyName("payloadSha256")] string? PayloadSha256,
        [property: JsonPropertyName("payloadSizeBytes")] long? PayloadSizeBytes);

    private sealed record NormalizedArtifactContract(
        string ArtifactId,
        string FileName,
        string DownloadUrl,
        string Sha256,
        long SizeBytes,
        string Head,
        string Platform,
        string PlatformLabel,
        string Arch,
        string Rid,
        string Kind,
        string InstallAccessClass,
        string? InstallerMode,
        string? PayloadFileName,
        string? PayloadDownloadUrl,
        string? PayloadSha256,
        long? PayloadSizeBytes);

    private sealed record StartupSmokeReceipt(
        [property: JsonPropertyName("status")] string? Status,
        [property: JsonPropertyName("headId")] string? HeadId,
        [property: JsonPropertyName("version")] string? Version,
        [property: JsonPropertyName("releaseVersion")] string? ReleaseVersion,
        [property: JsonPropertyName("channel")] string? Channel,
        [property: JsonPropertyName("channelId")] string? ChannelId,
        [property: JsonPropertyName("platform")] string? Platform,
        [property: JsonPropertyName("arch")] string? Arch,
        [property: JsonPropertyName("rid")] string? Rid,
        [property: JsonPropertyName("readyCheckpoint")] string? ReadyCheckpoint,
        [property: JsonPropertyName("hostClass")] string? HostClass,
        [property: JsonPropertyName("operatingSystem")] string? OperatingSystem,
        [property: JsonPropertyName("artifactDigest")] string? ArtifactDigest,
        [property: JsonPropertyName("artifactSha256")] string? ArtifactSha256,
        [property: JsonPropertyName("artifactId")] string? ArtifactId,
        [property: JsonPropertyName("artifactFileName")] string? ArtifactFileName,
        [property: JsonPropertyName("fileName")] string? FileName,
        [property: JsonPropertyName("artifactPath")] string? ArtifactPath,
        [property: JsonPropertyName("artifactRelativePath")] string? ArtifactRelativePath,
        [property: JsonPropertyName("startedAtUtc")] string? StartedAtUtc,
        [property: JsonPropertyName("recordedAtUtc")] string? RecordedAtUtc,
        [property: JsonPropertyName("completedAtUtc")] string? CompletedAtUtc,
        [property: JsonPropertyName("sourceUpdatedAtUtc")] string? SourceUpdatedAtUtc,
        [property: JsonPropertyName("executionEnvironment")] string? ExecutionEnvironment,
        [property: JsonPropertyName("nativeHostEvidence")] NativeWindowsHostEvidence? NativeHostEvidence);

    private sealed record NativeWindowsHostEvidence(
        [property: JsonPropertyName("contractName")] string? ContractName,
        [property: JsonPropertyName("status")] string? Status,
        [property: JsonPropertyName("isNativeWindows")] bool? IsNativeWindows,
        [property: JsonPropertyName("hostPlatform")] string? HostPlatform,
        [property: JsonPropertyName("hostKernel")] string? HostKernel,
        [property: JsonPropertyName("runner")] string? Runner,
        [property: JsonPropertyName("evidenceSource")] string? EvidenceSource);

    private sealed record PromotionEvidenceDocument(
        [property: JsonPropertyName("contractName")] string ContractName,
        [property: JsonPropertyName("generatedAt")] DateTimeOffset GeneratedAt,
        [property: JsonPropertyName("artifacts")] IReadOnlyList<PromotionArtifactEvidence> Artifacts);

    private sealed record PromotionArtifactEvidence(
        [property: JsonPropertyName("artifactId")] string ArtifactId,
        [property: JsonPropertyName("fileName")] string? FileName,
        [property: JsonPropertyName("platform")] string? Platform,
        [property: JsonPropertyName("promotionStatus")] string PromotionStatus,
        [property: JsonPropertyName("startupSmokeStatus")] string StartupSmokeStatus,
        [property: JsonPropertyName("signingStatus")] string? SigningStatus,
        [property: JsonPropertyName("notarizationStatus")] string? NotarizationStatus);
}
