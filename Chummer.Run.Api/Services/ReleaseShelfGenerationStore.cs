using System.Globalization;
using System.Security.Cryptography;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Http;

namespace Chummer.Run.Api.Services;

/// <summary>
/// Resolves one immutable release-shelf generation for a request or explicit operation.
/// The legacy top-level shelf is available only before layout-v1 activation.
/// </summary>
public sealed class ReleaseShelfGenerationStore
{
    public const string LayoutMarkerFileName = ".release-shelf-layout-v1";
    public const string CurrentPointerFileName = "current.json";
    public const string GenerationsDirectoryName = "generations";
    public const string CanonicalManifestFileName = "RELEASE_CHANNEL.generated.json";
    public const string CompatibilityManifestFileName = "releases.json";

    private const string DownloadsRootKey = "CHUMMER_DOWNLOADS_SOURCE_ROOT";
    private const string PublicCanonRootKey = "CHUMMER_PUBLIC_CANON_ROOT";
    private const string LayoutV1RequiredKey = "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED";
    private const string InitialMigrationAllowedKey = "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED";
    private const string DefaultRoot = "/downloads-source";
    private const string CurrentSchemaVersion = "chummer.release-shelf.current/v1";
    private const string ActivationCandidateSchemaVersion = "chummer.release-shelf.activation-candidate/v1";
    private const string ActivationJournalDirectoryName = ".release-shelf-activation-journal";
    private const string ActivationJournalIntentFileName = "intent.json";
    private const string ActivationJournalOutcomeFileName = "outcome.json";
    private const string ActivationIntentSchemaVersion = "chummer.release-shelf.activation-intent/v1";
    private const string ActivationOutcomeSchemaVersion = "chummer.release-shelf.activation-outcome/v1";
    private const int MaximumPointerBytes = 64 * 1024;
    private const int MaximumActivationCandidateBytes = 8 * 1024 * 1024;
    private const int MaximumActivationJournalBytes = 1024 * 1024;
    public const int MaximumManifestBytes = 4 * 1024 * 1024;
    public const int MaximumAurCatalogBytes = 1024 * 1024;
    private static readonly Regex GenerationIdPattern = new(
        "\\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex Sha256Pattern = new(
        "\\A[0-9a-f]{64}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex PortableInventorySegmentPattern = new(
        "\\A[A-Za-z0-9][A-Za-z0-9._+-]{0,254}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly object RequestSnapshotKey = new();
    private static readonly JsonSerializerOptions ActivationJournalJsonOptions = new(JsonSerializerDefaults.Web)
    {
        PropertyNameCaseInsensitive = true,
        WriteIndented = true
    };

    private readonly IConfiguration _configuration;
    private readonly IHttpContextAccessor? _httpContextAccessor;
    private readonly object _cacheLock = new();
    private string? _cachedPointerDigest;
    private ReleaseShelfSnapshot? _cachedActiveSnapshot;

    public ReleaseShelfGenerationStore(IConfiguration configuration)
        : this(configuration, httpContextAccessor: null)
    {
    }

    public ReleaseShelfGenerationStore(
        IConfiguration configuration,
        IHttpContextAccessor? httpContextAccessor)
    {
        _configuration = configuration ?? throw new ArgumentNullException(nameof(configuration));
        _httpContextAccessor = httpContextAccessor;
    }

    /// <summary>
    /// Returns the request's first captured generation. Non-HTTP callers should retain
    /// the returned snapshot and pass it to generation-aware overloads for one operation.
    /// </summary>
    public ReleaseShelfSnapshot CaptureForCurrentRequest()
    {
        HttpContext? context = _httpContextAccessor?.HttpContext;
        if (context is null)
        {
            return Capture();
        }

        if (context.Items.TryGetValue(RequestSnapshotKey, out object? existing)
            && existing is ReleaseShelfSnapshot snapshot)
        {
            return snapshot;
        }

        snapshot = Capture();
        context.Items[RequestSnapshotKey] = snapshot;
        return snapshot;
    }

    public ReleaseShelfSnapshot Capture()
    {
        string downloadsRoot = Path.GetFullPath(ResolveDownloadsRoot());
        string markerPath = Path.Combine(downloadsRoot, LayoutMarkerFileName);
        string pointerPath = Path.Combine(downloadsRoot, CurrentPointerFileName);
        IReadOnlyList<string> rootEntries = EnumerateRootEntries(downloadsRoot);
        bool markerExists = HasRegularControlFile(
            rootEntries,
            LayoutMarkerFileName,
            "release shelf layout marker");
        bool pointerExists = HasRegularControlFile(
            rootEntries,
            CurrentPointerFileName,
            "release shelf current pointer");

        if (!markerExists && !pointerExists)
        {
            if (LayoutV1IsRequired())
            {
                throw new InvalidDataException(
                    $"Release shelf layout-v1 is required by {LayoutV1RequiredKey}; refusing legacy fallback after marker/pointer removal.");
            }

            bool hasGenerationFootprint = HasGenerationFootprint(rootEntries);
            if (HasCommittedActivationHistory(downloadsRoot, rootEntries))
            {
                throw new InvalidDataException(
                    $"Release shelf committed activation history exists without {CurrentPointerFileName}; refusing to reopen mutable legacy truth after layout-v1 activation.");
            }

            if (hasGenerationFootprint && !InitialMigrationIsAllowed())
            {
                throw new InvalidDataException(
                    $"Release shelf generations exist without {CurrentPointerFileName}; {InitialMigrationAllowedKey}=true is required for a controlled first activation.");
            }

            return ReleaseShelfSnapshot.Legacy(downloadsRoot);
        }

        if (!pointerExists)
        {
            throw new InvalidDataException(
                $"Release shelf layout-v1 marker exists without {CurrentPointerFileName}; refusing legacy fallback.");
        }

        if (markerExists)
        {
            EnsureRegularFile(markerPath, downloadsRoot, "release shelf layout marker");
        }
        byte[] pointerBytes = ReadBoundedFile(pointerPath, MaximumPointerBytes, "release shelf current pointer");
        string pointerDigest = Convert.ToHexStringLower(SHA256.HashData(pointerBytes));
        lock (_cacheLock)
        {
            if (string.Equals(_cachedPointerDigest, pointerDigest, StringComparison.Ordinal)
                && _cachedActiveSnapshot is not null)
            {
                return _cachedActiveSnapshot;
            }
        }

        ReleaseShelfSnapshot resolved = ValidatePointerAndGeneration(
            downloadsRoot,
            pointerBytes,
            pointerDigest);
        lock (_cacheLock)
        {
            _cachedPointerDigest = pointerDigest;
            _cachedActiveSnapshot = resolved;
        }

        return resolved;
    }

    private static IReadOnlyList<string> EnumerateRootEntries(string downloadsRoot)
    {
        if (!Directory.Exists(downloadsRoot))
        {
            return Array.Empty<string>();
        }

        try
        {
            return Directory.EnumerateFileSystemEntries(downloadsRoot).ToArray();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or System.Security.SecurityException)
        {
            throw new InvalidDataException(
                "Release shelf root could not be inspected; refusing legacy fallback.",
                ex);
        }
    }

    private static bool HasRegularControlFile(
        IReadOnlyList<string> rootEntries,
        string expectedName,
        string label)
    {
        string[] matches = rootEntries
            .Where(entry => string.Equals(
                Path.GetFileName(entry),
                expectedName,
                StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (matches.Length == 0)
        {
            return false;
        }

        if (matches.Length != 1
            || !string.Equals(Path.GetFileName(matches[0]), expectedName, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"{label} has ambiguous or noncanonical casing; refusing legacy fallback.");
        }

        try
        {
            FileAttributes attributes = File.GetAttributes(matches[0]);
            if ((attributes & (FileAttributes.Directory | FileAttributes.ReparsePoint)) != 0
                || !File.Exists(matches[0]))
            {
                throw new InvalidDataException(
                    $"{label} must be a regular file; refusing legacy fallback.");
            }

            return true;
        }
        catch (InvalidDataException)
        {
            throw;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or System.Security.SecurityException)
        {
            throw new InvalidDataException(
                $"{label} could not be inspected; refusing legacy fallback.",
                ex);
        }
    }

    private static bool HasGenerationFootprint(IReadOnlyList<string> rootEntries)
    {
        string[] matches = rootEntries
            .Where(entry => string.Equals(
                Path.GetFileName(entry),
                GenerationsDirectoryName,
                StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (matches.Length == 0)
        {
            return false;
        }

        if (matches.Length != 1
            || !string.Equals(Path.GetFileName(matches[0]), GenerationsDirectoryName, StringComparison.Ordinal))
        {
            return true;
        }

        try
        {
            string generationsEntry = matches[0];
            FileAttributes attributes = File.GetAttributes(generationsEntry);
            if ((attributes & FileAttributes.ReparsePoint) != 0
                || (attributes & FileAttributes.Directory) == 0)
            {
                return true;
            }

            return Directory.EnumerateFileSystemEntries(generationsEntry).Any();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or System.Security.SecurityException)
        {
            throw new InvalidDataException(
                "Release shelf generation footprint could not be inspected; refusing legacy fallback.",
                ex);
        }
    }

    private static bool HasCommittedActivationHistory(
        string downloadsRoot,
        IReadOnlyList<string> rootEntries)
    {
        string[] matches = rootEntries
            .Where(entry => string.Equals(
                Path.GetFileName(entry),
                ActivationJournalDirectoryName,
                StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (matches.Length == 0)
        {
            return false;
        }

        if (matches.Length != 1
            || !string.Equals(
                Path.GetFileName(matches[0]),
                ActivationJournalDirectoryName,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "Release activation journal has ambiguous or noncanonical casing.");
        }

        string journalRoot = matches[0];
        EnsureRegularDirectory(journalRoot, downloadsRoot, "release activation journal");
        bool committed = false;
        foreach (string receiptRoot in Directory.EnumerateFileSystemEntries(journalRoot))
        {
            ActivationReceiptProof proof = LoadActivationReceiptProof(
                downloadsRoot,
                journalRoot,
                receiptRoot);
            committed |= string.Equals(proof.Outcome?.State, "committed", StringComparison.Ordinal);
        }

        return committed;
    }

    private ReleaseShelfSnapshot CaptureCommittedGeneration(
        string downloadsRoot,
        string generationId)
    {
        string journalRoot = Path.Combine(downloadsRoot, ActivationJournalDirectoryName);
        if (!Directory.Exists(journalRoot))
        {
            throw new InvalidDataException(
                $"Release shelf generation '{generationId}' has no committed activation receipt.");
        }

        EnsureRegularDirectory(journalRoot, downloadsRoot, "release activation journal");
        ActivationReceiptProof[] committed = Directory.EnumerateFileSystemEntries(journalRoot)
            .Select(receiptRoot => LoadActivationReceiptProof(
                downloadsRoot,
                journalRoot,
                receiptRoot))
            .Where(proof =>
                string.Equals(proof.Outcome?.State, "committed", StringComparison.Ordinal)
                && string.Equals(
                    proof.Journal.Intent.GenerationId,
                    generationId,
                    StringComparison.Ordinal))
            .OrderByDescending(static proof => proof.Outcome!.ResolvedAtUtc)
            .ThenByDescending(
                static proof => proof.Journal.Intent.ActivationReceiptId,
                StringComparer.Ordinal)
            .ToArray();
        if (committed.Length == 0)
        {
            throw new InvalidDataException(
                $"Release shelf generation '{generationId}' is not bound to a committed activation receipt.");
        }

        ActivationReceiptProof receipt = committed[0];
        string pointerDigest = Convert.ToHexStringLower(SHA256.HashData(receipt.TargetPointerBytes));
        ReleaseShelfSnapshot snapshot = ValidatePointerAndGeneration(
            downloadsRoot,
            receipt.TargetPointerBytes,
            pointerDigest);
        if (!string.Equals(snapshot.GenerationId, generationId, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "Committed release activation receipt resolved a different generation.");
        }

        return snapshot.AsExplicitGeneration();
    }

    private static ActivationReceiptProof LoadActivationReceiptProof(
        string downloadsRoot,
        string journalRoot,
        string receiptRoot)
    {
        EnsureRegularDirectory(receiptRoot, journalRoot, "release activation receipt directory");
        string receiptId = Path.GetFileName(receiptRoot);
        if (!IsTraversalSafeGenerationId(receiptId))
        {
            throw new InvalidDataException(
                "Release activation receipt directory name is not a traversal-safe token.");
        }

        string[] entries = Directory.EnumerateFileSystemEntries(receiptRoot).ToArray();
        foreach (string entry in entries)
        {
            string name = Path.GetFileName(entry);
            if (name is not ActivationJournalIntentFileName and not ActivationJournalOutcomeFileName)
            {
                throw new InvalidDataException(
                    "Release activation receipt directory contains an unexpected entry.");
            }
        }

        string intentPath = Path.Combine(receiptRoot, ActivationJournalIntentFileName);
        byte[] intentBytes = ReadBoundedFile(
            intentPath,
            MaximumActivationJournalBytes,
            "release activation journal intent");
        JsonElement intentJson = ParseJsonObject(intentBytes, "release activation journal intent");
        RequireExactProperties(
            intentJson,
            ["schemaVersion", "state", "intent", "previousPointerBase64", "targetPointerBase64"],
            "release activation journal intent");
        if (!intentJson.TryGetProperty("intent", out JsonElement identity)
            || identity.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException("Release activation journal identity is malformed.");
        }

        RequireExactProperties(
            identity,
            [
                "operation", "previousGenerationId", "previousPointerSha256", "generationId",
                "activationReceiptId", "releaseVersion", "channel", "publishedAt",
                "inventoryDigest", "pointerSha256", "preparedAtUtc",
                "previousPointerBase64", "targetPointerBase64"
            ],
            "release activation journal identity");
        ReaderActivationJournal journal = JsonSerializer.Deserialize<ReaderActivationJournal>(
                intentBytes,
                ActivationJournalJsonOptions)
            ?? throw new InvalidDataException("Release activation journal intent is malformed.");
        ValidateActivationJournal(journal, receiptId);

        byte[] targetPointerBytes;
        try
        {
            targetPointerBytes = Convert.FromBase64String(journal.TargetPointerBase64);
        }
        catch (FormatException exception)
        {
            throw new InvalidDataException(
                "Release activation journal target pointer is not valid base64.",
                exception);
        }

        if (targetPointerBytes.Length is < 1 or > MaximumPointerBytes)
        {
            throw new InvalidDataException(
                "Release activation journal target pointer has an invalid byte length.");
        }

        if (!string.Equals(
                Convert.ToBase64String(targetPointerBytes),
                journal.TargetPointerBase64,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "Release activation journal target pointer base64 is not canonical.");
        }

        string pointerDigest = Convert.ToHexStringLower(SHA256.HashData(targetPointerBytes));
        if (!FixedTimeSha256Equals(
                RequireSha256Binding(journal.Intent.PointerSha256, "pointerSha256"),
                pointerDigest))
        {
            throw new InvalidDataException(
                "Release activation journal target pointer digest does not match its bytes.");
        }

        ValidateActivationJournalPointer(journal, targetPointerBytes);

        ReaderActivationOutcome? outcome = null;
        string outcomePath = Path.Combine(receiptRoot, ActivationJournalOutcomeFileName);
        bool outcomeEntryPresent = entries.Any(entry => string.Equals(
            Path.GetFileName(entry),
            ActivationJournalOutcomeFileName,
            StringComparison.Ordinal));
        if (outcomeEntryPresent)
        {
            byte[] outcomeBytes = ReadBoundedFile(
                outcomePath,
                MaximumActivationJournalBytes,
                "release activation journal outcome");
            JsonElement outcomeJson = ParseJsonObject(
                outcomeBytes,
                "release activation journal outcome");
            RequireExactProperties(
                outcomeJson,
                ["schemaVersion", "state", "activationReceiptId", "intentSha256", "resolvedAtUtc"],
                "release activation journal outcome");
            outcome = JsonSerializer.Deserialize<ReaderActivationOutcome>(
                    outcomeBytes,
                    ActivationJournalJsonOptions)
                ?? throw new InvalidDataException("Release activation journal outcome is malformed.");
            string computedIntentDigest = Convert.ToHexStringLower(SHA256.HashData(
                JsonSerializer.SerializeToUtf8Bytes(journal, ActivationJournalJsonOptions)));
            if (!string.Equals(outcome.SchemaVersion, ActivationOutcomeSchemaVersion, StringComparison.Ordinal)
                || outcome.State is not "committed" and not "aborted"
                || !string.Equals(outcome.ActivationReceiptId, receiptId, StringComparison.Ordinal)
                || !FixedTimeSha256Equals(
                    RequireSha256Binding(outcome.IntentSha256, "intentSha256"),
                    computedIntentDigest)
                || outcome.ResolvedAtUtc.Offset != TimeSpan.Zero)
            {
                throw new InvalidDataException(
                    "Release activation journal outcome contract is invalid.");
            }
        }

        return new ActivationReceiptProof(journal, outcome, targetPointerBytes);
    }

    private static void ValidateActivationJournal(
        ReaderActivationJournal journal,
        string receiptId)
    {
        ReaderActivationIntent intent = journal.Intent
            ?? throw new InvalidDataException("Release activation journal identity is missing.");
        if (!string.Equals(journal.SchemaVersion, ActivationIntentSchemaVersion, StringComparison.Ordinal)
            || !string.Equals(journal.State, "prepared", StringComparison.Ordinal)
            || intent.Operation is not "promotion" and not "rollback"
            || !IsTraversalSafeGenerationId(intent.GenerationId)
            || !IsTraversalSafeGenerationId(intent.ActivationReceiptId)
            || !string.Equals(intent.ActivationReceiptId, receiptId, StringComparison.Ordinal)
            || (intent.PreviousGenerationId is not null
                && !IsTraversalSafeGenerationId(intent.PreviousGenerationId))
            || (intent.PreviousGenerationId is null) != (intent.PreviousPointerSha256 is null)
            || string.IsNullOrWhiteSpace(intent.ReleaseVersion)
            || intent.ReleaseVersion.Length > 256
            || string.IsNullOrWhiteSpace(intent.Channel)
            || intent.Channel.Length > 128
            || string.IsNullOrWhiteSpace(journal.TargetPointerBase64)
            || string.IsNullOrWhiteSpace(intent.TargetPointerBase64)
            || !string.Equals(
                intent.TargetPointerBase64,
                journal.TargetPointerBase64,
                StringComparison.Ordinal)
            || !string.Equals(
                intent.PreviousPointerBase64,
                journal.PreviousPointerBase64,
                StringComparison.Ordinal)
            || intent.PublishedAt.Offset != TimeSpan.Zero
            || intent.PreparedAtUtc.Offset != TimeSpan.Zero)
        {
            throw new InvalidDataException("Release activation journal identity is invalid.");
        }

        _ = RequireSha256Binding(intent.PointerSha256, "pointerSha256");
        _ = RequireSha256Binding(intent.InventoryDigest, "inventoryDigest");
        if (intent.PreviousPointerSha256 is not null)
        {
            string previousDigest = RequireSha256Binding(
                intent.PreviousPointerSha256,
                "previousPointerSha256");
            byte[] previousPointerBytes;
            try
            {
                previousPointerBytes = Convert.FromBase64String(
                    journal.PreviousPointerBase64
                    ?? throw new InvalidDataException(
                        "Release activation journal previous pointer bytes are missing."));
            }
            catch (FormatException exception)
            {
                throw new InvalidDataException(
                    "Release activation journal previous pointer is not valid base64.",
                    exception);
            }

            if (previousPointerBytes.Length is < 1 or > MaximumPointerBytes
                || !string.Equals(
                    Convert.ToBase64String(previousPointerBytes),
                    journal.PreviousPointerBase64,
                    StringComparison.Ordinal)
                || !FixedTimeSha256Equals(
                    previousDigest,
                    Convert.ToHexStringLower(SHA256.HashData(previousPointerBytes))))
            {
                throw new InvalidDataException(
                    "Release activation journal previous pointer digest does not match its bytes.");
            }
        }
        else if (journal.PreviousPointerBase64 is not null)
        {
            throw new InvalidDataException(
                "Release activation journal unexpectedly retains previous pointer bytes.");
        }
    }

    private static void ValidateActivationJournalPointer(
        ReaderActivationJournal journal,
        byte[] pointerBytes)
    {
        JsonElement pointer = ParseJsonObject(pointerBytes, "release activation journal target pointer");
        ReaderActivationIntent intent = journal.Intent;
        string generationId = RequireString(pointer, "generationId");
        string activationReceiptId = RequireString(pointer, "activationReceiptId");
        string releaseVersion = RequireString(pointer, "releaseVersion");
        string channel = RequireString(pointer, "channel");
        DateTimeOffset publishedAt = RequireTimestamp(pointer, "publishedAt");
        _ = RequireTimestamp(pointer, "activatedAt");
        string inventoryDigest = RequireInventoryDigest(pointer, "inventoryDigest");
        if (!string.Equals(RequireString(pointer, "schemaVersion"), CurrentSchemaVersion, StringComparison.Ordinal)
            || !string.Equals(generationId, intent.GenerationId, StringComparison.Ordinal)
            || !string.Equals(activationReceiptId, intent.ActivationReceiptId, StringComparison.Ordinal)
            || !string.Equals(releaseVersion, intent.ReleaseVersion, StringComparison.Ordinal)
            || !string.Equals(channel, intent.Channel, StringComparison.Ordinal)
            || publishedAt.ToUniversalTime() != intent.PublishedAt.ToUniversalTime()
            || !FixedTimeSha256Equals(
                RequireSha256Binding(intent.InventoryDigest, "inventoryDigest"),
                inventoryDigest))
        {
            throw new InvalidDataException(
                "Release activation journal target pointer identity is invalid.");
        }
    }

    private static string RequireSha256Binding(string? value, string propertyName)
    {
        const string prefix = "sha256:";
        if (value is null
            || !value.StartsWith(prefix, StringComparison.Ordinal)
            || !Sha256Pattern.IsMatch(value[prefix.Length..]))
        {
            throw new InvalidDataException(
                $"Release activation journal {propertyName} is not a sha256: digest.");
        }

        return value[prefix.Length..];
    }

    private static void EnsureRegularDirectory(
        string path,
        string containmentRoot,
        string description)
    {
        string fullPath = Path.GetFullPath(path);
        if (!Directory.Exists(fullPath))
        {
            throw new InvalidDataException($"{description} does not exist.");
        }

        EnsureContainedPath(Path.GetFullPath(containmentRoot), fullPath, description);
        EnsureNoSymbolicLinks(containmentRoot, fullPath, description);
        FileAttributes attributes = File.GetAttributes(fullPath);
        if ((attributes & FileAttributes.Directory) == 0
            || (attributes & FileAttributes.ReparsePoint) != 0)
        {
            throw new InvalidDataException($"{description} must be a regular directory.");
        }
    }

    private static void RequireExactProperties(
        JsonElement source,
        IReadOnlyCollection<string> expected,
        string description)
    {
        string[] actual = source.EnumerateObject()
            .Select(static property => property.Name)
            .OrderBy(static name => name, StringComparer.Ordinal)
            .ToArray();
        string[] required = expected
            .OrderBy(static name => name, StringComparer.Ordinal)
            .ToArray();
        if (!actual.SequenceEqual(required, StringComparer.Ordinal))
        {
            throw new InvalidDataException($"{description} has unexpected or missing properties.");
        }
    }

    public ReleaseShelfSnapshot CaptureGeneration(string generationId)
    {
        ReleaseShelfSnapshot current = Capture();
        if (current.IsLegacy)
        {
            throw new InvalidOperationException("Version-bound generation routes are unavailable before layout-v1 activation.");
        }

        if (!IsTraversalSafeGenerationId(generationId))
        {
            throw new InvalidDataException("Release shelf generationId is not a traversal-safe opaque token.");
        }

        if (string.Equals(current.GenerationId, generationId, StringComparison.Ordinal))
        {
            return current.AsExplicitGeneration();
        }

        return CaptureCommittedGeneration(current.DownloadsRoot, generationId);
    }

    public ReleaseShelfSnapshot CaptureGenerationForCurrentRequest(string generationId)
    {
        HttpContext? context = _httpContextAccessor?.HttpContext;
        if (context is not null
            && context.Items.TryGetValue(RequestSnapshotKey, out object? existing)
            && existing is ReleaseShelfSnapshot firstSnapshot)
        {
            if (!string.Equals(firstSnapshot.GenerationId, generationId, StringComparison.Ordinal))
            {
                throw new InvalidOperationException(
                    $"This request is already pinned to release shelf generation '{firstSnapshot.GenerationId ?? "legacy"}' and cannot switch to '{generationId}'.");
            }

            return firstSnapshot;
        }

        ReleaseShelfSnapshot snapshot = CaptureGeneration(generationId);
        if (context is not null)
        {
            context.Items[RequestSnapshotKey] = snapshot;
        }

        return snapshot;
    }

    private bool LayoutV1IsRequired()
        => ReadBooleanConfiguration(LayoutV1RequiredKey, defaultValue: false);

    private bool InitialMigrationIsAllowed()
        => ReadBooleanConfiguration(InitialMigrationAllowedKey, defaultValue: false);

    private bool ReadBooleanConfiguration(string key, bool defaultValue)
    {
        string raw = (_configuration[key] ?? string.Empty).Trim();
        if (string.IsNullOrEmpty(raw))
        {
            return defaultValue;
        }

        return raw.ToLowerInvariant() switch
        {
            "1" or "true" or "yes" or "on" => true,
            "0" or "false" or "no" or "off" => false,
            _ => throw new InvalidDataException(
                $"{key} must be an explicit boolean value.")
        };
    }

    public string ResolveDownloadsRoot()
    {
        if (_configuration[DownloadsRootKey]?.Trim() is { Length: > 0 } configured)
        {
            return configured;
        }

        foreach (string candidate in ResolveDefaultDownloadsRootCandidates())
        {
            if (Directory.Exists(candidate))
            {
                return candidate;
            }
        }

        return DefaultRoot;
    }

    /// <summary>
    /// Builds the cross-language layout-v1 inventory used by the Python publishers
    /// and C# readers. The candidate and both pointer-bound manifests are excluded;
    /// manifest digests are bound separately by current.json.
    /// </summary>
    public static IReadOnlyList<ReleaseShelfInventoryEntry> BuildInventory(string generationRoot)
    {
        string root = Path.GetFullPath(generationRoot);
        var rows = new List<ReleaseShelfInventoryEntry>();
        var caseInsensitivePaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (string file in EnumerateGenerationFilesWithoutLinks(root))
        {
            string relative = Path.GetRelativePath(root, file).Replace(Path.DirectorySeparatorChar, '/');
            if (relative is "activation-candidate.json"
                or CanonicalManifestFileName
                or CompatibilityManifestFileName)
            {
                continue;
            }

            if (!IsSafeInventoryPath(relative))
            {
                throw new InvalidDataException(
                    $"Release shelf generation inventory path is not portable ASCII: '{relative}'.");
            }

            if (!caseInsensitivePaths.Add(relative))
            {
                throw new InvalidDataException(
                    $"Release shelf generation inventory contains a case-colliding path '{relative}'.");
            }

            var info = new FileInfo(file);
            rows.Add(new ReleaseShelfInventoryEntry(relative, ComputeFileSha256(file), info.Length));
        }

        return rows
            .OrderBy(static row => row.Path, StringComparer.Ordinal)
            .ToArray();
    }

    public static string ComputeInventoryDigest(string generationRoot)
        => ComputeInventoryDigest(BuildInventory(generationRoot));

    public static string ComputeInventoryDigest(IEnumerable<ReleaseShelfInventoryEntry> inventory)
    {
        JsonElement element = JsonSerializer.SerializeToElement(inventory);
        byte[] canonical = CanonicalJsonBytes(element);
        return Convert.ToHexStringLower(SHA256.HashData(canonical));
    }

    private ReleaseShelfSnapshot ValidatePointerAndGeneration(
        string downloadsRoot,
        byte[] pointerBytes,
        string pointerDigest)
    {
        JsonElement pointer = ParseJsonObject(pointerBytes, "release shelf current pointer");
        string schemaVersion = RequireString(pointer, "schemaVersion");
        if (!string.Equals(schemaVersion, CurrentSchemaVersion, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"Unsupported release shelf pointer schemaVersion '{schemaVersion}'.");
        }

        string generationId = RequireString(pointer, "generationId");
        if (!IsTraversalSafeGenerationId(generationId))
        {
            throw new InvalidDataException("Release shelf generationId is not a traversal-safe opaque token.");
        }

        string releaseVersion = RequireString(pointer, "releaseVersion");
        string channel = RequireString(pointer, "channel");
        DateTimeOffset publishedAt = RequireTimestamp(pointer, "publishedAt");
        DateTimeOffset activatedAt = RequireTimestamp(pointer, "activatedAt");
        string activationReceiptId = RequireString(pointer, "activationReceiptId");
        (string canonicalPathBinding, string canonicalSha256) = RequireManifestBinding(
            pointer,
            "canonical",
            generationId,
            CanonicalManifestFileName);
        (string compatibilityPathBinding, string compatibilitySha256) = RequireManifestBinding(
            pointer,
            "compatibility",
            generationId,
            CompatibilityManifestFileName);
        string inventoryDigest = RequireInventoryDigest(pointer, "inventoryDigest");

        string generationsRoot = Path.GetFullPath(Path.Combine(downloadsRoot, GenerationsDirectoryName));
        string generationRoot = Path.GetFullPath(Path.Combine(generationsRoot, generationId));
        EnsureContainedPath(generationsRoot, generationRoot, "release shelf generation");
        if (!Directory.Exists(generationRoot))
        {
            throw new InvalidDataException($"Release shelf generation '{generationId}' does not exist.");
        }

        EnsureNoSymbolicLinks(downloadsRoot, generationRoot, "release shelf generation");
        string activationCandidatePath = Path.Combine(generationRoot, "activation-candidate.json");
        if (!File.Exists(activationCandidatePath))
        {
            throw new InvalidDataException($"Release shelf generation '{generationId}' is missing activation-candidate.json.");
        }

        JsonElement activationCandidate = ParseJsonObject(
            ReadBoundedFile(activationCandidatePath, MaximumActivationCandidateBytes, "release shelf activation candidate"),
            "release shelf activation candidate");
        ValidateActivationCandidate(
            activationCandidate,
            generationId,
            releaseVersion,
            channel,
            publishedAt,
            activatedAt,
            activationReceiptId,
            canonicalPathBinding,
            canonicalSha256,
            compatibilityPathBinding,
            compatibilitySha256,
            inventoryDigest);

        string canonicalPath = Path.Combine(generationRoot, CanonicalManifestFileName);
        string compatibilityPath = Path.Combine(generationRoot, CompatibilityManifestFileName);
        ReleaseShelfManifestIdentity canonicalIdentity = ValidateManifest(
            canonicalPath,
            canonicalSha256,
            releaseVersion,
            channel,
            publishedAt,
            generationId,
            canonical: true);
        ReleaseShelfManifestIdentity compatibilityIdentity = ValidateManifest(
            compatibilityPath,
            compatibilitySha256,
            releaseVersion,
            channel,
            publishedAt,
            generationId,
            canonical: false);

        IReadOnlyDictionary<string, ReleaseShelfInventoryEntry> inventory = ValidateInventory(
            generationRoot,
            activationCandidate,
            inventoryDigest,
            generationId);
        inventory = BindManifestInventory(
            inventory,
            canonicalIdentity,
            compatibilityIdentity);

        return ReleaseShelfSnapshot.Active(
            downloadsRoot,
            generationRoot,
            generationId,
            releaseVersion,
            channel,
            publishedAt,
            activatedAt,
            activationReceiptId,
            canonicalSha256,
            compatibilitySha256,
            inventoryDigest,
            pointerDigest,
            inventory,
            explicitGeneration: false);
    }

    private ReleaseShelfSnapshot ValidateRetainedGeneration(
        string downloadsRoot,
        string requestedGenerationId,
        byte[] candidateBytes,
        string candidateDigest)
    {
        JsonElement candidate = ParseJsonObject(candidateBytes, "release shelf activation candidate");
        string candidateSchema = RequireString(candidate, "schemaVersion");
        if (candidateSchema is not ActivationCandidateSchemaVersion)
        {
            throw new InvalidDataException(
                $"Unsupported release shelf activation candidate schemaVersion '{candidateSchema}'.");
        }

        string generationId = RequireString(candidate, "generationId");
        if (!string.Equals(generationId, requestedGenerationId, StringComparison.Ordinal)
            || !IsTraversalSafeGenerationId(generationId))
        {
            throw new InvalidDataException("Release shelf activation candidate identity does not match its directory.");
        }

        string generationsRoot = Path.GetFullPath(Path.Combine(downloadsRoot, GenerationsDirectoryName));
        string generationRoot = Path.GetFullPath(Path.Combine(generationsRoot, generationId));
        EnsureContainedPath(generationsRoot, generationRoot, "release shelf generation");
        EnsureNoSymbolicLinks(downloadsRoot, generationRoot, "release shelf generation");

        string releaseVersion = RequireString(candidate, "releaseVersion");
        string channel = RequireString(candidate, "channel");
        DateTimeOffset publishedAt = RequireTimestamp(candidate, "publishedAt");
        (string canonicalPathBinding, string canonicalSha256) = RequireManifestBinding(
            candidate,
            "canonical",
            generationId,
            CanonicalManifestFileName);
        (string compatibilityPathBinding, string compatibilitySha256) = RequireManifestBinding(
            candidate,
            "compatibility",
            generationId,
            CompatibilityManifestFileName);
        string inventoryDigest = RequireInventoryDigest(candidate, "inventoryDigest");
        string computedInventoryDigest = ComputeCandidateInventoryDigest(candidate, generationId);
        if (!FixedTimeSha256Equals(inventoryDigest, computedInventoryDigest))
        {
            throw new InvalidDataException(
                $"Release shelf generation '{generationId}' candidate inventoryDigest does not match its inventory.");
        }

        DateTimeOffset? activatedAt = TryReadTimestamp(candidate, "activatedAt");
        string? activationReceiptId = ReadOptionalString(candidate, "activationReceiptId");
        ValidateActivationCandidate(
            candidate,
            generationId,
            releaseVersion,
            channel,
            publishedAt,
            activatedAt,
            activationReceiptId,
            canonicalPathBinding,
            canonicalSha256,
            compatibilityPathBinding,
            compatibilitySha256,
            inventoryDigest);

        ReleaseShelfManifestIdentity canonicalIdentity = ValidateManifest(
            Path.Combine(generationRoot, CanonicalManifestFileName),
            canonicalSha256,
            releaseVersion,
            channel,
            publishedAt,
            generationId,
            canonical: true);
        ReleaseShelfManifestIdentity compatibilityIdentity = ValidateManifest(
            Path.Combine(generationRoot, CompatibilityManifestFileName),
            compatibilitySha256,
            releaseVersion,
            channel,
            publishedAt,
            generationId,
            canonical: false);

        IReadOnlyDictionary<string, ReleaseShelfInventoryEntry> inventory = ValidateInventory(
            generationRoot,
            candidate,
            inventoryDigest,
            generationId);
        inventory = BindManifestInventory(inventory, canonicalIdentity, compatibilityIdentity);

        return ReleaseShelfSnapshot.Active(
            downloadsRoot,
            generationRoot,
            generationId,
            releaseVersion,
            channel,
            publishedAt,
            activatedAt,
            activationReceiptId,
            canonicalSha256,
            compatibilitySha256,
            inventoryDigest,
            candidateDigest,
            inventory,
            explicitGeneration: true);
    }

    private static void ValidateActivationCandidate(
        JsonElement candidate,
        string generationId,
        string releaseVersion,
        string channel,
        DateTimeOffset publishedAt,
        DateTimeOffset? activatedAt,
        string? activationReceiptId,
        string canonicalPath,
        string canonicalSha256,
        string compatibilityPath,
        string compatibilitySha256,
        string inventoryDigest)
    {
        string candidateSchema = RequireString(candidate, "schemaVersion");
        if (candidateSchema is not ActivationCandidateSchemaVersion
            || !string.Equals(RequireString(candidate, "generationId"), generationId, StringComparison.Ordinal))
        {
            throw new InvalidDataException("Release shelf activation-candidate.json does not match current.json.");
        }

        if (!string.Equals(RequireString(candidate, "releaseVersion"), releaseVersion, StringComparison.Ordinal)
            || !string.Equals(RequireString(candidate, "channel"), channel, StringComparison.Ordinal)
            || RequireTimestamp(candidate, "publishedAt").ToUniversalTime() != publishedAt.ToUniversalTime()
            || !FixedTimeSha256Equals(RequireInventoryDigest(candidate, "inventoryDigest"), inventoryDigest))
        {
            throw new InvalidDataException("Release shelf activation candidate immutable identity disagrees with its pointer.");
        }

        if (activatedAt is not null)
        {
            ValidateOptionalTimestamp(candidate, "activatedAt", activatedAt.Value);
        }
        if (activationReceiptId is not null)
        {
            ValidateOptionalString(candidate, "activationReceiptId", activationReceiptId);
        }

        (string candidateCanonicalPath, string candidateCanonicalSha) = RequireManifestBinding(
            candidate,
            "canonical",
            generationId,
            CanonicalManifestFileName);
        (string candidateCompatibilityPath, string candidateCompatibilitySha) = RequireManifestBinding(
            candidate,
            "compatibility",
            generationId,
            CompatibilityManifestFileName);
        if (!string.Equals(candidateCanonicalPath, canonicalPath, StringComparison.Ordinal)
            || !FixedTimeSha256Equals(candidateCanonicalSha, canonicalSha256)
            || !string.Equals(candidateCompatibilityPath, compatibilityPath, StringComparison.Ordinal)
            || !FixedTimeSha256Equals(candidateCompatibilitySha, compatibilitySha256))
        {
            throw new InvalidDataException("Release shelf activation candidate manifest bindings disagree with current.json.");
        }
    }

    private static ReleaseShelfManifestIdentity ValidateManifest(
        string path,
        string expectedSha256,
        string expectedReleaseVersion,
        string expectedChannel,
        DateTimeOffset expectedPublishedAt,
        string expectedGenerationId,
        bool canonical)
    {
        ReleaseShelfManifestIdentity identity = ReadManifestIdentity(
            path,
            expectedGenerationId,
            canonical);
        if (!FixedTimeSha256Equals(expectedSha256, identity.Sha256))
        {
            throw new InvalidDataException($"Release shelf manifest '{Path.GetFileName(path)}' digest does not match current.json.");
        }

        if (!string.Equals(identity.ReleaseVersion, expectedReleaseVersion, StringComparison.Ordinal)
            || !string.Equals(identity.Channel, expectedChannel, StringComparison.Ordinal)
            || (identity.PublishedAt is not null
                && identity.PublishedAt.Value.ToUniversalTime() != expectedPublishedAt.ToUniversalTime()))
        {
            throw new InvalidDataException($"Release shelf manifest '{Path.GetFileName(path)}' identity does not match current.json.");
        }

        return identity;
    }

    private static ReleaseShelfManifestIdentity ReadManifestIdentity(
        string path,
        string expectedGenerationId,
        bool canonical)
    {
        byte[] manifestBytes = ReadBoundedFile(
            path,
            MaximumManifestBytes,
            $"release shelf manifest '{Path.GetFileName(path)}'");
        JsonElement manifest = ParseJsonObject(
            manifestBytes,
            $"release shelf manifest '{Path.GetFileName(path)}'");
        string manifestGenerationId = RequireString(manifest, "generationId");
        if (!string.Equals(
                manifestGenerationId,
                expectedGenerationId,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"Release shelf manifest '{Path.GetFileName(path)}' generationId does not match the active generation.");
        }

        ValidateGenerationRoutes(
            manifest,
            expectedGenerationId,
            $"Release shelf manifest '{Path.GetFileName(path)}'");
        string releaseVersion = ReadFirstRequiredString(manifest, "releaseVersion", "version");
        string channel = ReadFirstRequiredString(manifest, "channelId", "channel");
        DateTimeOffset? publishedAt = TryReadTimestamp(manifest, "publishedAt")
                                      ?? TryReadTimestamp(manifest, "generatedAt");
        if (canonical && publishedAt is null)
        {
            throw new InvalidDataException("Canonical release shelf manifest must expose publishedAt.");
        }

        return new ReleaseShelfManifestIdentity(
            Path.GetFileName(path),
            releaseVersion,
            channel,
            publishedAt,
            Convert.ToHexStringLower(SHA256.HashData(manifestBytes)),
            manifestBytes.LongLength);
    }

    private IEnumerable<string> ResolveDefaultDownloadsRootCandidates()
    {
        if (_configuration[PublicCanonRootKey]?.Trim() is { Length: > 0 } canonRoot)
        {
            yield return Path.Combine(canonRoot, "Chummer.Portal", "downloads");
        }

        foreach (string candidate in ResolveAncestorPortalDownloadsRoots(Directory.GetCurrentDirectory()))
        {
            yield return candidate;
        }

        foreach (string candidate in ResolveAncestorPortalDownloadsRoots(AppContext.BaseDirectory))
        {
            yield return candidate;
        }

        yield return DefaultRoot;
    }

    private static IEnumerable<string> ResolveAncestorPortalDownloadsRoots(string start)
    {
        string? current = Path.GetFullPath(start);
        for (int depth = 0; depth < 6 && !string.IsNullOrWhiteSpace(current); depth++)
        {
            yield return Path.Combine(current, "Chummer.Portal", "downloads");
            current = Directory.GetParent(current)?.FullName;
        }
    }

    private static bool IsTraversalSafeGenerationId(string generationId)
        => GenerationIdPattern.IsMatch(generationId)
           && generationId is not "." and not ".."
           && !generationId.Contains("..", StringComparison.Ordinal)
           && !Path.IsPathFullyQualified(generationId);

    private static (string Path, string Sha256) RequireManifestBinding(
        JsonElement source,
        string bindingName,
        string generationId,
        string manifestName)
    {
        if (!source.TryGetProperty("manifests", out JsonElement manifests)
            || manifests.ValueKind != JsonValueKind.Object
            || !manifests.TryGetProperty(bindingName, out JsonElement binding)
            || binding.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException($"Release shelf pointer is missing its {bindingName} manifest binding.");
        }

        string path = RequireString(binding, "path");
        string expectedPath = $"/downloads/g/{generationId}/{manifestName}";
        if (!string.Equals(path, expectedPath, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"Release shelf {bindingName} manifest path is not generation-bound.");
        }

        return (path, RequireSha256(binding, "sha256"));
    }

    private static string RequireInventoryDigest(JsonElement source, string propertyName)
    {
        string value = RequireString(source, propertyName);
        const string prefix = "sha256:";
        if (!value.StartsWith(prefix, StringComparison.Ordinal)
            || !Sha256Pattern.IsMatch(value[prefix.Length..]))
        {
            throw new InvalidDataException($"Release shelf JSON {propertyName} is not a sha256: digest.");
        }

        return value[prefix.Length..];
    }

    private static IReadOnlyDictionary<string, ReleaseShelfInventoryEntry> ValidateInventory(
        string generationRoot,
        JsonElement activationCandidate,
        string expectedInventoryDigest,
        string generationId)
    {
        if (!activationCandidate.TryGetProperty("inventory", out JsonElement inventory)
            || inventory.ValueKind != JsonValueKind.Array
            || inventory.GetArrayLength() == 0)
        {
            throw new InvalidDataException($"Release shelf generation '{generationId}' has no activation inventory.");
        }

        var entries = new Dictionary<string, ReleaseShelfInventoryEntry>(StringComparer.Ordinal);
        var caseInsensitivePaths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        string? priorPath = null;
        foreach (JsonElement row in inventory.EnumerateArray())
        {
            if (row.ValueKind != JsonValueKind.Object)
            {
                throw new InvalidDataException("Release shelf activation inventory rows must be JSON objects.");
            }

            string relativePath = RequireString(row, "path").Replace('\\', '/');
            if (!IsSafeInventoryPath(relativePath)
                || entries.ContainsKey(relativePath)
                || !caseInsensitivePaths.Add(relativePath)
                || (priorPath is not null && string.CompareOrdinal(priorPath, relativePath) >= 0))
            {
                throw new InvalidDataException("Release shelf activation inventory paths must be unique, sorted, and traversal-safe.");
            }

            priorPath = relativePath;
            string expectedSha256 = RequireSha256(row, "sha256");
            string? filePath = ReleaseShelfSnapshot.ResolveExistingFileFromRoot(
                generationRoot,
                relativePath,
                rejectSymbolicLinks: true);
            if (filePath is null || !FixedTimeSha256Equals(expectedSha256, ComputeFileSha256(filePath)))
            {
                throw new InvalidDataException($"Release shelf activation inventory digest mismatch for '{relativePath}'.");
            }

            long actualSize = new FileInfo(filePath).Length;
            if (row.TryGetProperty("sizeBytes", out JsonElement sizeElement))
            {
                if (sizeElement.ValueKind != JsonValueKind.Number
                    || !sizeElement.TryGetInt64(out long expectedSize)
                    || expectedSize < 0
                    || actualSize != expectedSize)
                {
                    throw new InvalidDataException($"Release shelf activation inventory size mismatch for '{relativePath}'.");
                }
            }

            entries.Add(
                relativePath,
                new ReleaseShelfInventoryEntry(relativePath, expectedSha256, actualSize));
        }

        IReadOnlyList<ReleaseShelfInventoryEntry> actualInventory = BuildInventory(generationRoot);
        HashSet<string> actualPaths = actualInventory
            .Select(static row => row.Path)
            .ToHashSet(StringComparer.Ordinal);
        foreach (string candidatePath in entries.Keys)
        {
            if (!actualPaths.Contains(candidatePath))
            {
                throw new InvalidDataException(
                    $"Release shelf activation inventory contains excluded metadata or an unexpected path '{candidatePath}'.");
            }
        }

        foreach (ReleaseShelfInventoryEntry actual in actualInventory)
        {
            if (!entries.ContainsKey(actual.Path))
            {
                throw new InvalidDataException($"Release shelf activation inventory omits '{actual.Path}'.");
            }
        }

        string actualInventoryDigest = Convert.ToHexStringLower(SHA256.HashData(CanonicalJsonBytes(inventory)));
        if (!FixedTimeSha256Equals(expectedInventoryDigest, actualInventoryDigest))
        {
            throw new InvalidDataException($"Release shelf generation '{generationId}' inventory digest does not match current.json.");
        }

        return entries;
    }

    private static string ComputeCandidateInventoryDigest(JsonElement activationCandidate, string generationId)
    {
        if (!activationCandidate.TryGetProperty("inventory", out JsonElement inventory)
            || inventory.ValueKind != JsonValueKind.Array
            || inventory.GetArrayLength() == 0)
        {
            throw new InvalidDataException($"Release shelf generation '{generationId}' has no activation inventory.");
        }

        return Convert.ToHexStringLower(SHA256.HashData(CanonicalJsonBytes(inventory)));
    }

    private static IReadOnlyDictionary<string, ReleaseShelfInventoryEntry> BindManifestInventory(
        IReadOnlyDictionary<string, ReleaseShelfInventoryEntry> inventory,
        ReleaseShelfManifestIdentity canonical,
        ReleaseShelfManifestIdentity compatibility)
    {
        Dictionary<string, ReleaseShelfInventoryEntry> bound = inventory.ToDictionary(
            static entry => entry.Key,
            static entry => entry.Value,
            StringComparer.Ordinal);
        bound[CanonicalManifestFileName] = new(
            CanonicalManifestFileName,
            canonical.Sha256,
            canonical.SizeBytes);
        bound[CompatibilityManifestFileName] = new(
            CompatibilityManifestFileName,
            compatibility.Sha256,
            compatibility.SizeBytes);
        return bound;
    }

    private static bool IsSafeInventoryPath(string relativePath)
    {
        if (string.IsNullOrWhiteSpace(relativePath)
            || relativePath.StartsWith("/", StringComparison.Ordinal)
            || relativePath.Contains('\n')
            || relativePath.Contains('\r')
            || relativePath.Contains('\t'))
        {
            return false;
        }

        string[] segments = relativePath.Split('/', StringSplitOptions.None);
        return segments.Length > 0
               && segments.All(static segment => PortableInventorySegmentPattern.IsMatch(segment));
    }

    private static IEnumerable<string> EnumerateGenerationFilesWithoutLinks(string generationRoot)
    {
        var pending = new Stack<string>();
        pending.Push(generationRoot);
        while (pending.Count > 0)
        {
            string directory = pending.Pop();
            EnsureNoSymbolicLinks(generationRoot, directory, "release shelf inventory directory", allowRoot: true);
            foreach (string entry in Directory.EnumerateFileSystemEntries(directory))
            {
                FileAttributes attributes = File.GetAttributes(entry);
                if ((attributes & FileAttributes.ReparsePoint) != 0)
                {
                    throw new InvalidDataException("Release shelf generation inventory must not contain symbolic links.");
                }

                if ((attributes & FileAttributes.Directory) != 0)
                {
                    pending.Push(entry);
                }
                else
                {
                    EnsureRegularFile(entry, generationRoot, "release shelf inventory file");
                    yield return entry;
                }
            }
        }
    }

    private static byte[] CanonicalJsonBytes(JsonElement element)
    {
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream, new JsonWriterOptions
        {
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
            Indented = false
        }))
        {
            WriteCanonicalJson(writer, element);
        }

        return stream.ToArray();
    }

    private static void WriteCanonicalJson(Utf8JsonWriter writer, JsonElement element)
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                writer.WriteStartObject();
                foreach (JsonProperty property in element.EnumerateObject().OrderBy(static property => property.Name, StringComparer.Ordinal))
                {
                    writer.WritePropertyName(property.Name);
                    WriteCanonicalJson(writer, property.Value);
                }
                writer.WriteEndObject();
                break;
            case JsonValueKind.Array:
                writer.WriteStartArray();
                foreach (JsonElement item in element.EnumerateArray())
                {
                    WriteCanonicalJson(writer, item);
                }
                writer.WriteEndArray();
                break;
            case JsonValueKind.String:
                writer.WriteStringValue(element.GetString());
                break;
            case JsonValueKind.Number:
                writer.WriteRawValue(element.GetRawText(), skipInputValidation: false);
                break;
            case JsonValueKind.True:
                writer.WriteBooleanValue(true);
                break;
            case JsonValueKind.False:
                writer.WriteBooleanValue(false);
                break;
            case JsonValueKind.Null:
                writer.WriteNullValue();
                break;
            default:
                throw new InvalidDataException("Release shelf canonical JSON contains an unsupported token.");
        }
    }

    private static void ValidateOptionalString(JsonElement source, string propertyName, string expected)
    {
        if (source.TryGetProperty(propertyName, out JsonElement value)
            && (value.ValueKind != JsonValueKind.String
                || !string.Equals(value.GetString()?.Trim(), expected, StringComparison.Ordinal)))
        {
            throw new InvalidDataException($"Release shelf activation candidate {propertyName} disagrees with current.json.");
        }
    }

    private static string? ReadOptionalString(JsonElement source, string propertyName)
    {
        if (!source.TryGetProperty(propertyName, out JsonElement value))
        {
            return null;
        }

        if (value.ValueKind != JsonValueKind.String
            || value.GetString()?.Trim() is not { Length: > 0 } parsed)
        {
            throw new InvalidDataException(
                $"Release shelf JSON {propertyName} must be a non-empty string when present.");
        }

        return parsed;
    }

    private static void ValidateOptionalTimestamp(JsonElement source, string propertyName, DateTimeOffset expected)
    {
        DateTimeOffset? value = TryReadTimestamp(source, propertyName);
        if (source.TryGetProperty(propertyName, out _) && value?.ToUniversalTime() != expected.ToUniversalTime())
        {
            throw new InvalidDataException($"Release shelf activation candidate {propertyName} disagrees with current.json.");
        }
    }

    private static DateTimeOffset? TryReadTimestamp(JsonElement source, string propertyName)
    {
        if (!source.TryGetProperty(propertyName, out JsonElement value)
            || value.ValueKind != JsonValueKind.String)
        {
            return null;
        }

        return DateTimeOffset.TryParse(
            value.GetString(),
            CultureInfo.InvariantCulture,
            DateTimeStyles.RoundtripKind,
            out DateTimeOffset parsed)
            ? parsed
            : null;
    }

    private static void ValidateGenerationRoutes(
        JsonElement element,
        string generationId,
        string label,
        GenerationRouteTraversalContext context = GenerationRouteTraversalContext.ManifestRoot)
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
                foreach (JsonProperty property in element.EnumerateObject())
                {
                    if (property.NameEquals("proof_routes"))
                    {
                        throw new InvalidDataException(
                            $"{label} contains a noncanonical proof-route alias.");
                    }

                    // Only the exact top-level releaseProof.proofRoutes array is
                    // immutable Registry evidence. Nested lookalikes remain subject
                    // to the generation-bound live-route invariant.
                    if (context == GenerationRouteTraversalContext.TopLevelReleaseProof
                        && property.NameEquals("proofRoutes")
                        && property.Value.ValueKind == JsonValueKind.Array)
                    {
                        continue;
                    }

                    if (context == GenerationRouteTraversalContext.NestedReleaseProof
                        && property.NameEquals("proofRoutes"))
                    {
                        throw new InvalidDataException(
                            $"{label} contains a nested releaseProof.proofRoutes lookalike.");
                    }

                    GenerationRouteTraversalContext childContext =
                        property.NameEquals("releaseProof")
                            ? context == GenerationRouteTraversalContext.ManifestRoot
                                ? GenerationRouteTraversalContext.TopLevelReleaseProof
                                : GenerationRouteTraversalContext.NestedReleaseProof
                            : GenerationRouteTraversalContext.Other;
                    ValidateGenerationRoutes(property.Value, generationId, label, childContext);
                }
                return;
            case JsonValueKind.Array:
                foreach (JsonElement child in element.EnumerateArray())
                {
                    ValidateGenerationRoutes(
                        child,
                        generationId,
                        label,
                        GenerationRouteTraversalContext.Other);
                }
                return;
            case JsonValueKind.String:
                string? value = element.GetString();
                if (value is null)
                {
                    return;
                }

                if (!value.StartsWith("/downloads/", StringComparison.Ordinal))
                {
                    bool absoluteReleaseUrl = Uri.TryCreate(
                                                  value,
                                                  UriKind.Absolute,
                                                  out Uri? absolute)
                                              && absolute.AbsolutePath.StartsWith(
                                                  "/downloads/",
                                                  StringComparison.Ordinal);
                    bool schemeRelativeReleaseUrl = value.StartsWith("//", StringComparison.Ordinal)
                                                    && value.IndexOf(
                                                        "/downloads/",
                                                        2,
                                                        StringComparison.Ordinal) >= 2;
                    if (absoluteReleaseUrl || schemeRelativeReleaseUrl)
                    {
                        throw new InvalidDataException($"{label} release URLs must be plain generation-bound site paths.");
                    }

                    return;
                }

                string expectedPrefix = $"/downloads/g/{generationId}/";
                if (value.Contains('?')
                    || value.Contains('#')
                    || value.Contains('\\')
                    || value.Contains('%')
                    || !value.StartsWith(expectedPrefix, StringComparison.Ordinal))
                {
                    throw new InvalidDataException($"{label} contains a non-generation-bound release URL.");
                }

                string relative = value[expectedPrefix.Length..];
                string[] parts = relative.Split('/', StringSplitOptions.None);
                if (parts.Length == 0
                    || parts.Any(static part => !PortableInventorySegmentPattern.IsMatch(part)))
                {
                    throw new InvalidDataException($"{label} contains an unsafe generation-bound release URL.");
                }

                bool validShape = parts[0] switch
                {
                    CanonicalManifestFileName or CompatibilityManifestFileName => parts.Length == 1,
                    "files" => parts.Length == 2,
                    "install" => parts.Length == 2
                                 || (parts.Length == 3
                                     && parts[2] is "payload" or "metadata"),
                    "proof" or "startup-smoke" or "release-evidence" => parts.Length >= 2,
                    _ => false
                };
                if (!validShape)
                {
                    throw new InvalidDataException(
                        $"{label} contains a noncanonical generation-bound release URL shape.");
                }
                return;
        }
    }

    private enum GenerationRouteTraversalContext
    {
        ManifestRoot,
        TopLevelReleaseProof,
        NestedReleaseProof,
        Other
    }

    private static byte[] ReadBoundedFile(string path, int maximumBytes, string description)
    {
        EnsureRegularFile(path, Directory.GetParent(path)?.FullName ?? path, description);
        try
        {
            using var stream = new FileStream(
                path,
                FileMode.Open,
                FileAccess.Read,
                FileShare.Read,
                bufferSize: 64 * 1024,
                FileOptions.SequentialScan);
            long descriptorLength = stream.Length;
            if (descriptorLength <= 0 || descriptorLength > maximumBytes)
            {
                throw new InvalidDataException($"{description} has an invalid byte length.");
            }

            byte[] bytes = new byte[checked((int)descriptorLength)];
            stream.ReadExactly(bytes);
            if (stream.ReadByte() != -1 || stream.Length != descriptorLength)
            {
                throw new InvalidDataException($"{description} changed while it was being read.");
            }

            return bytes;
        }
        catch (EndOfStreamException exception)
        {
            throw new InvalidDataException($"{description} changed while it was being read.", exception);
        }
        catch (IOException exception)
        {
            throw new InvalidDataException($"{description} could not be read atomically.", exception);
        }
    }

    private static JsonElement ParseJsonObject(byte[] bytes, string description)
    {
        try
        {
            using JsonDocument document = JsonDocument.Parse(bytes, new JsonDocumentOptions
            {
                AllowTrailingCommas = false,
                CommentHandling = JsonCommentHandling.Disallow,
                MaxDepth = 32
            });
            if (document.RootElement.ValueKind != JsonValueKind.Object)
            {
                throw new InvalidDataException($"{description} must be a JSON object.");
            }

            EnsureNoDuplicateProperties(document.RootElement, description);
            return document.RootElement.Clone();
        }
        catch (JsonException exception)
        {
            throw new InvalidDataException($"{description} is malformed JSON.", exception);
        }
    }

    private static void EnsureNoDuplicateProperties(JsonElement element, string description)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (JsonProperty property in element.EnumerateObject())
            {
                if (!names.Add(property.Name))
                {
                    throw new InvalidDataException($"{description} contains duplicate JSON property '{property.Name}'.");
                }

                EnsureNoDuplicateProperties(property.Value, description);
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement child in element.EnumerateArray())
            {
                EnsureNoDuplicateProperties(child, description);
            }
        }
    }

    private static string RequireString(JsonElement source, string propertyName)
    {
        if (!source.TryGetProperty(propertyName, out JsonElement value)
            || value.ValueKind != JsonValueKind.String
            || value.GetString()?.Trim() is not { Length: > 0 } parsed)
        {
            throw new InvalidDataException($"Release shelf JSON must contain non-empty {propertyName}.");
        }

        return parsed;
    }

    private static string ReadFirstRequiredString(JsonElement source, params string[] propertyNames)
    {
        foreach (string propertyName in propertyNames)
        {
            if (source.TryGetProperty(propertyName, out JsonElement value)
                && value.ValueKind == JsonValueKind.String
                && value.GetString()?.Trim() is { Length: > 0 } parsed)
            {
                return parsed;
            }
        }

        throw new InvalidDataException($"Release shelf JSON must contain one of: {string.Join(", ", propertyNames)}.");
    }

    private static DateTimeOffset RequireTimestamp(JsonElement source, string propertyName)
    {
        string raw = RequireString(source, propertyName);
        if (!DateTimeOffset.TryParse(
                raw,
                CultureInfo.InvariantCulture,
                DateTimeStyles.RoundtripKind,
                out DateTimeOffset parsed))
        {
            throw new InvalidDataException($"Release shelf JSON {propertyName} is not an RFC 3339 timestamp.");
        }

        return parsed;
    }

    private static string RequireSha256(JsonElement source, string propertyName)
    {
        string value = RequireString(source, propertyName);
        if (!Sha256Pattern.IsMatch(value))
        {
            throw new InvalidDataException($"Release shelf JSON {propertyName} is not a SHA-256 digest.");
        }

        return value.ToLowerInvariant();
    }

    private static string ComputeFileSha256(string path)
    {
        using FileStream stream = File.OpenRead(path);
        return Convert.ToHexStringLower(SHA256.HashData(stream));
    }

    private static bool FixedTimeSha256Equals(string expected, string actual)
    {
        try
        {
            byte[] expectedBytes = Convert.FromHexString(expected);
            byte[] actualBytes = Convert.FromHexString(actual);
            return expectedBytes.Length == 32
                   && actualBytes.Length == 32
                   && CryptographicOperations.FixedTimeEquals(expectedBytes, actualBytes);
        }
        catch (FormatException)
        {
            return false;
        }
    }

    private static void EnsureContainedPath(string root, string candidate, string description)
    {
        string normalizedRoot = Path.GetFullPath(root);
        string scopedRoot = normalizedRoot.EndsWith(Path.DirectorySeparatorChar)
            ? normalizedRoot
            : normalizedRoot + Path.DirectorySeparatorChar;
        StringComparison comparison = OperatingSystem.IsWindows()
            ? StringComparison.OrdinalIgnoreCase
            : StringComparison.Ordinal;
        if (!candidate.StartsWith(scopedRoot, comparison))
        {
            throw new InvalidDataException($"{description} escapes its configured root.");
        }
    }

    private static void EnsureNoSymbolicLinks(
        string root,
        string candidate,
        string description,
        bool allowRoot = false)
    {
        string normalizedRoot = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar);
        string current = Path.GetFullPath(candidate);
        bool isRoot = string.Equals(
            current.TrimEnd(Path.DirectorySeparatorChar),
            normalizedRoot,
            PathComparison);
        if (!isRoot)
        {
            EnsureContainedPath(normalizedRoot, current, description);
        }
        else if (!allowRoot)
        {
            throw new InvalidDataException($"{description} must be beneath its configured root.");
        }
        else if (new DirectoryInfo(current).LinkTarget is not null)
        {
            throw new InvalidDataException($"{description} must not be a symbolic link.");
        }
        while (!string.Equals(current.TrimEnd(Path.DirectorySeparatorChar), normalizedRoot, PathComparison))
        {
            FileSystemInfo info = Directory.Exists(current)
                ? new DirectoryInfo(current)
                : new FileInfo(current);
            if (info.LinkTarget is not null)
            {
                throw new InvalidDataException($"{description} must not traverse a symbolic link.");
            }

            current = Directory.GetParent(current)?.FullName
                ?? throw new InvalidDataException($"{description} is not rooted beneath the downloads directory.");
        }
    }

    private static void EnsureRegularFile(string path, string containmentRoot, string description)
    {
        string fullPath = Path.GetFullPath(path);
        if (!File.Exists(fullPath))
        {
            throw new InvalidDataException($"{description} does not exist.");
        }

        EnsureNoSymbolicLinks(containmentRoot, fullPath, description);
        var info = new FileInfo(fullPath);
        if ((info.Attributes & (FileAttributes.Directory | FileAttributes.ReparsePoint)) != 0)
        {
            throw new InvalidDataException($"{description} must be a regular file.");
        }
    }

    private static StringComparison PathComparison => OperatingSystem.IsWindows()
        ? StringComparison.OrdinalIgnoreCase
        : StringComparison.Ordinal;

    private sealed record ReleaseShelfManifestIdentity(
        string FileName,
        string ReleaseVersion,
        string Channel,
        DateTimeOffset? PublishedAt,
        string Sha256,
        long SizeBytes);

    private sealed record ReaderActivationJournal(
        string SchemaVersion,
        string State,
        ReaderActivationIntent Intent,
        string? PreviousPointerBase64,
        string TargetPointerBase64);

    private sealed record ReaderActivationIntent(
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
        string? PreviousPointerBase64,
        string? TargetPointerBase64);

    private sealed record ReaderActivationOutcome(
        string SchemaVersion,
        string State,
        string ActivationReceiptId,
        string IntentSha256,
        DateTimeOffset ResolvedAtUtc);

    private sealed record ActivationReceiptProof(
        ReaderActivationJournal Journal,
        ReaderActivationOutcome? Outcome,
        byte[] TargetPointerBytes);
}

public sealed record ReleaseShelfInventoryEntry(
    [property: JsonPropertyName("path")] string Path,
    [property: JsonPropertyName("sha256")] string Sha256,
    [property: JsonIgnore] long SizeBytes);

public sealed record ReleaseShelfSnapshot
{
    private static readonly IReadOnlyDictionary<string, ReleaseShelfInventoryEntry> EmptyInventory =
        new Dictionary<string, ReleaseShelfInventoryEntry>(StringComparer.Ordinal);

    private ReleaseShelfSnapshot(
        string downloadsRoot,
        string physicalRoot,
        string? generationId,
        string? releaseVersion,
        string? channel,
        DateTimeOffset? publishedAt,
        DateTimeOffset? activatedAt,
        string? activationReceiptId,
        string? canonicalManifestSha256,
        string? compatibilityManifestSha256,
        string? inventoryDigest,
        string? pointerDigest,
        IReadOnlyDictionary<string, ReleaseShelfInventoryEntry>? inventory,
        bool explicitGeneration)
    {
        DownloadsRoot = downloadsRoot;
        PhysicalRoot = physicalRoot;
        GenerationId = generationId;
        ReleaseVersion = releaseVersion;
        Channel = channel;
        PublishedAt = publishedAt;
        ActivatedAt = activatedAt;
        ActivationReceiptId = activationReceiptId;
        CanonicalManifestSha256 = canonicalManifestSha256;
        CompatibilityManifestSha256 = compatibilityManifestSha256;
        InventoryDigest = inventoryDigest;
        PointerDigest = pointerDigest;
        Inventory = inventory is null
            ? EmptyInventory
            : inventory.ToDictionary(
                static entry => entry.Key,
                static entry => entry.Value,
                StringComparer.Ordinal);
        IsExplicitGeneration = explicitGeneration;
    }

    public string DownloadsRoot { get; }
    public string PhysicalRoot { get; }
    public string? GenerationId { get; }
    public string? ReleaseVersion { get; }
    public string? Channel { get; }
    public DateTimeOffset? PublishedAt { get; }
    public DateTimeOffset? ActivatedAt { get; }
    public string? ActivationReceiptId { get; }
    public string? CanonicalManifestSha256 { get; }
    public string? CompatibilityManifestSha256 { get; }
    public string? InventoryDigest { get; }
    public string? PointerDigest { get; }
    public IReadOnlyDictionary<string, ReleaseShelfInventoryEntry> Inventory { get; }
    public bool IsExplicitGeneration { get; }
    public bool IsLegacy => GenerationId is null;
    public string CacheKey => IsLegacy
        ? $"legacy:{DownloadsRoot}"
        : IsExplicitGeneration
            ? $"generation-bound:{GenerationId}"
            : $"generation-current:{GenerationId}";

    public string? ResolveLegacyFilePath(string relativePath)
    {
        if (!IsLegacy)
        {
            throw new InvalidOperationException(
                "Layout-v1 snapshots cannot expose verified bytes as reopenable paths; use OpenVerifiedFile or ReadVerifiedFileBytes.");
        }

        return ResolveExistingFileFromRoot(PhysicalRoot, relativePath, rejectSymbolicLinks: false);
    }

    public ReleaseShelfVerifiedFile? OpenVerifiedFile(string relativePath)
    {
        string? normalized = NormalizeRelativePath(relativePath);
        if (normalized is null)
        {
            return null;
        }

        string? candidate = ResolveExistingFileFromRoot(
            PhysicalRoot,
            normalized,
            rejectSymbolicLinks: !IsLegacy);
        if (candidate is null)
        {
            return null;
        }

        if (IsLegacy)
        {
            try
            {
                var legacyStream = new FileStream(
                    candidate,
                    FileMode.Open,
                    FileAccess.Read,
                    FileShare.Read,
                    bufferSize: 64 * 1024,
                    FileOptions.SequentialScan);
                return new ReleaseShelfVerifiedFile(
                    candidate,
                    normalized,
                    expectedSha256: null,
                    legacyStream.Length,
                    legacyStream);
            }
            catch (IOException)
            {
                return null;
            }
            catch (UnauthorizedAccessException)
            {
                return null;
            }
        }

        if (!Inventory.TryGetValue(normalized, out ReleaseShelfInventoryEntry? expected))
        {
            return null;
        }

        FileStream? stream = null;
        try
        {
            stream = new FileStream(
                candidate,
                FileMode.Open,
                FileAccess.Read,
                FileShare.Read,
                bufferSize: 64 * 1024,
                FileOptions.SequentialScan);
            if (stream.Length != expected.SizeBytes)
            {
                stream.Dispose();
                return null;
            }

            string actualSha256 = Convert.ToHexStringLower(SHA256.HashData(stream));
            if (!FixedTimeDigestEquals(expected.Sha256, actualSha256)
                || stream.Length != expected.SizeBytes)
            {
                stream.Dispose();
                return null;
            }

            stream.Position = 0;
            return new ReleaseShelfVerifiedFile(
                candidate,
                normalized,
                expected.Sha256,
                expected.SizeBytes,
                stream);
        }
        catch (IOException)
        {
            stream?.Dispose();
            return null;
        }
        catch (UnauthorizedAccessException)
        {
            stream?.Dispose();
            return null;
        }
    }

    public byte[]? ReadVerifiedFileBytes(string relativePath, int maximumBytes)
    {
        if (maximumBytes <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(maximumBytes));
        }

        using ReleaseShelfVerifiedFile? verified = OpenVerifiedFile(relativePath);
        if (verified is null || verified.SizeBytes <= 0 || verified.SizeBytes > maximumBytes)
        {
            return null;
        }

        byte[] bytes = new byte[checked((int)verified.SizeBytes)];
        verified.Stream.ReadExactly(bytes);
        return bytes;
    }

    public ReleaseShelfSnapshot AsExplicitGeneration()
    {
        if (IsLegacy || IsExplicitGeneration)
        {
            return this;
        }

        return new ReleaseShelfSnapshot(
            DownloadsRoot,
            PhysicalRoot,
            GenerationId,
            ReleaseVersion,
            Channel,
            PublishedAt,
            ActivatedAt,
            ActivationReceiptId,
            CanonicalManifestSha256,
            CompatibilityManifestSha256,
            InventoryDigest,
            PointerDigest,
            Inventory,
            explicitGeneration: true);
    }

    private static string? NormalizeRelativePath(string relativePath)
    {
        if (string.IsNullOrWhiteSpace(relativePath) || Path.IsPathFullyQualified(relativePath))
        {
            return null;
        }

        string normalized = relativePath.Trim().Replace('\\', '/').TrimStart('/');
        string[] segments = normalized.Split('/', StringSplitOptions.RemoveEmptyEntries);
        return segments.Length == 0 || segments.Any(static segment => segment is "." or "..")
            ? null
            : string.Join('/', segments);
    }

    private static bool FixedTimeDigestEquals(string expected, string actual)
    {
        try
        {
            byte[] expectedBytes = Convert.FromHexString(expected);
            byte[] actualBytes = Convert.FromHexString(actual);
            return expectedBytes.Length == 32
                   && actualBytes.Length == 32
                   && CryptographicOperations.FixedTimeEquals(expectedBytes, actualBytes);
        }
        catch (FormatException)
        {
            return false;
        }
    }

    internal static string? ResolveExistingFileFromRoot(
        string physicalRoot,
        string relativePath,
        bool rejectSymbolicLinks)
    {
        if (string.IsNullOrWhiteSpace(relativePath)
            || Path.IsPathFullyQualified(relativePath))
        {
            return null;
        }

        string normalized = relativePath.Trim().Replace('\\', '/').TrimStart('/');
        string[] segments = normalized.Split('/', StringSplitOptions.RemoveEmptyEntries);
        if (segments.Length == 0 || segments.Any(static segment => segment is "." or ".."))
        {
            return null;
        }

        string root = Path.GetFullPath(physicalRoot);
        string candidate = Path.GetFullPath(Path.Combine(root, Path.Combine(segments)));
        try
        {
            ReleaseShelfGenerationStorePathGuard.EnsureContained(root, candidate);
            if (!File.Exists(candidate))
            {
                return null;
            }

            if (rejectSymbolicLinks)
            {
                ReleaseShelfGenerationStorePathGuard.EnsureNoLinks(root, candidate);
            }

            return candidate;
        }
        catch (InvalidDataException)
        {
            return null;
        }
    }

    internal static ReleaseShelfSnapshot Legacy(string downloadsRoot)
        => new(
            downloadsRoot,
            downloadsRoot,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            null,
            inventory: null,
            explicitGeneration: false);

    internal static ReleaseShelfSnapshot Active(
        string downloadsRoot,
        string physicalRoot,
        string generationId,
        string releaseVersion,
        string channel,
        DateTimeOffset publishedAt,
        DateTimeOffset? activatedAt,
        string? activationReceiptId,
        string canonicalManifestSha256,
        string compatibilityManifestSha256,
        string inventoryDigest,
        string pointerDigest,
        IReadOnlyDictionary<string, ReleaseShelfInventoryEntry> inventory,
        bool explicitGeneration)
        => new(
            downloadsRoot,
            physicalRoot,
            generationId,
            releaseVersion,
            channel,
            publishedAt,
            activatedAt,
            activationReceiptId,
            canonicalManifestSha256,
            compatibilityManifestSha256,
            inventoryDigest,
            pointerDigest,
            inventory,
            explicitGeneration);
}

public sealed class ReleaseShelfVerifiedFile : IDisposable
{
    internal ReleaseShelfVerifiedFile(
        string physicalPath,
        string relativePath,
        string? expectedSha256,
        long sizeBytes,
        FileStream stream)
    {
        PhysicalPath = physicalPath;
        RelativePath = relativePath;
        ExpectedSha256 = expectedSha256;
        SizeBytes = sizeBytes;
        Stream = stream;
    }

    public string PhysicalPath { get; }
    public string RelativePath { get; }
    public string? ExpectedSha256 { get; }
    public long SizeBytes { get; }
    public FileStream Stream { get; }

    public void Dispose() => Stream.Dispose();
}

internal static class ReleaseShelfGenerationStorePathGuard
{
    public static void EnsureContained(string root, string candidate)
    {
        string normalizedRoot = Path.GetFullPath(root);
        string scopedRoot = normalizedRoot.EndsWith(Path.DirectorySeparatorChar)
            ? normalizedRoot
            : normalizedRoot + Path.DirectorySeparatorChar;
        StringComparison comparison = OperatingSystem.IsWindows()
            ? StringComparison.OrdinalIgnoreCase
            : StringComparison.Ordinal;
        if (!candidate.StartsWith(scopedRoot, comparison))
        {
            throw new InvalidDataException("Release shelf path escapes the captured generation.");
        }
    }

    public static void EnsureNoLinks(string root, string candidate)
    {
        string normalizedRoot = Path.GetFullPath(root).TrimEnd(Path.DirectorySeparatorChar);
        string current = Path.GetFullPath(candidate);
        EnsureContained(normalizedRoot, current);
        StringComparison comparison = OperatingSystem.IsWindows()
            ? StringComparison.OrdinalIgnoreCase
            : StringComparison.Ordinal;
        while (!string.Equals(current.TrimEnd(Path.DirectorySeparatorChar), normalizedRoot, comparison))
        {
            FileSystemInfo info = Directory.Exists(current)
                ? new DirectoryInfo(current)
                : new FileInfo(current);
            if (info.LinkTarget is not null)
            {
                throw new InvalidDataException("Release shelf paths must not traverse symbolic links.");
            }

            current = Directory.GetParent(current)?.FullName
                ?? throw new InvalidDataException("Release shelf path is outside its captured generation.");
        }
    }
}
