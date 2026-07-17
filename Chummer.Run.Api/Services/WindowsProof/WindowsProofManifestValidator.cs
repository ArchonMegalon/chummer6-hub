using System.Buffers.Binary;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using System.Globalization;

namespace Chummer.Run.Api.Services.WindowsProof;

/// <summary>
/// Validates the deliberately narrow, preview-only Windows proof contract before
/// any bytes enter the immutable proof store.
/// </summary>
public sealed class WindowsProofManifestValidator
{
    public const string ManifestFileName = "WINDOWS_PROOF_MANIFEST.generated.json";
    public const string ManifestSchemaVersion = "chummer.windows-proof.manifest/v2";
    public const string LegacyManifestSchemaVersion = "chummer.windows-proof.manifest/v1";
    public const int MaximumManifestBytes = 1024 * 1024;
    public const int MaximumEvidenceBytes = 4 * 1024 * 1024;
    public const int MaximumSbomBytes = 16 * 1024 * 1024;
    public const string BootstrapPayloadPolicyVersion = "chummer6.windows-bootstrap-zip-admission.v1";
    internal const long MaximumBootstrapArchiveBytes = 256L * 1024 * 1024;
    internal const int MaximumBootstrapArchiveEntries = 2048;
    internal const long MaximumBootstrapEntryBytes = 128L * 1024 * 1024;
    internal const long MaximumBootstrapTotalBytes = 512L * 1024 * 1024;
    internal const int MaximumBootstrapCompressionRatio = 100;
    internal const long MaximumBootstrapCentralDirectoryBytes = 16L * 1024 * 1024;
    internal const int MaximumBootstrapInspectableTextBytes = 16 * 1024 * 1024;
    public static readonly TimeSpan MaximumProofLifetime = TimeSpan.FromHours(24);
    public static readonly TimeSpan MaximumClockSkew = TimeSpan.FromMinutes(5);
    private const int MaximumEmbeddedMetadataTrailerBytes = 64 * 1024;

    private static readonly Regex PortableIdPattern = new(
        "\\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex PortableSegmentPattern = new(
        "\\A[A-Za-z0-9][A-Za-z0-9._+-]{0,254}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex Sha256Pattern = new(
        "\\A[0-9a-f]{64}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex GitObjectIdPattern = new(
        "\\A[0-9a-f]{40}\\z",
        RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex PrivateKeyMarkerPattern = new(
        "-----BEGIN(?:[ \\t]+[A-Z0-9]+)*[ \\t]+PRIVATE[ \\t]+KEY(?:[ \\t]+BLOCK)?-----",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex AuthorizationBearerPattern = new(
        "authorization[\\\"']?[ \\t]*[:=][ \\t]*[\\\"']?bearer[ \\t]+[^\\x00-\\x20\\\"']",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex TokenAssignmentPattern = new(
        "(?:\\A|[^A-Za-z0-9])(?:bearer(?:[_-]?token)?|refresh[_-]?token|access[_-]?token|client[_-]?secret|private[_-]?key(?:[_-]?id)?)[\\\"']?[ \\t]*[:=][ \\t]*(?:[\\\"'][ \\t]*[^\\x00-\\x20\\\"']|[^\\x00-\\x20\\\"'])",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly Regex ConnectionAssignmentPattern = new(
        "(?:\\A|[^A-Za-z0-9])(?:connection[_-]?strings?(?:(?:__|:)[A-Za-z0-9_.-]+)?|default[_-]?connection)[\\\"']?[ \\t]*[:=][ \\t]*(?:[\\\"'][ \\t]*[^\\x00-\\x20\\\"']|[^\\x00-\\x20\\\"'])",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant | RegexOptions.NonBacktracking);
    private static readonly HashSet<string> SensitiveJsonKeys = new(
        [
            "authorization", "bearer", "bearertoken", "refreshtoken", "accesstoken",
            "clientsecret", "privatekey", "privatekeyid", "connectionstring",
            "connectionstrings", "defaultconnection"
        ],
        StringComparer.Ordinal);
    private static readonly HashSet<string> SensitiveArchiveExtensions = new(
        [".key", ".jks", ".keystore", ".p12", ".pfx", ".pk8", ".pkcs12", ".ppk", ".snk"],
        StringComparer.OrdinalIgnoreCase);
    private static readonly HashSet<char> WindowsInvalidEntryNameCharacters =
        ['<', '>', ':', '"', '\\', '|', '?', '*'];
    private static readonly HashSet<string> WindowsReservedDeviceStems = new(
        [
            "con", "prn", "aux", "nul",
            "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
            "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9"
        ],
        StringComparer.OrdinalIgnoreCase);
    private static readonly uint[] BootstrapCrc32Table = CreateBootstrapCrc32Table();
    private static readonly JsonSerializerOptions JsonOptions = CreateJsonOptions();
    private readonly TimeProvider _timeProvider;

    public WindowsProofManifestValidator(TimeProvider? timeProvider = null)
    {
        _timeProvider = timeProvider ?? TimeProvider.System;
    }

    internal readonly record struct BootstrapPayloadPolicy(
        long MaximumArchiveBytes,
        int MaximumEntries,
        long MaximumEntryBytes,
        long MaximumTotalBytes,
        int MaximumCompressionRatio,
        long MaximumCentralDirectoryBytes,
        int MaximumInspectableTextBytes)
    {
        internal static BootstrapPayloadPolicy Default => new(
            WindowsProofManifestValidator.MaximumBootstrapArchiveBytes,
            WindowsProofManifestValidator.MaximumBootstrapArchiveEntries,
            WindowsProofManifestValidator.MaximumBootstrapEntryBytes,
            WindowsProofManifestValidator.MaximumBootstrapTotalBytes,
            WindowsProofManifestValidator.MaximumBootstrapCompressionRatio,
            WindowsProofManifestValidator.MaximumBootstrapCentralDirectoryBytes,
            WindowsProofManifestValidator.MaximumBootstrapInspectableTextBytes);
    }

    private readonly record struct BootstrapZipEntryHeader(
        uint Crc32,
        string NameSha256);

    public WindowsProofValidatedSource ValidateSource(
        string sourceRoot,
        string expectedManifestSha256,
        bool allowStoreInventory = false,
        bool allowLegacyV1Delivery = false)
    {
        if (string.IsNullOrWhiteSpace(sourceRoot))
        {
            throw new ArgumentException("Windows proof source root is required.", nameof(sourceRoot));
        }

        RequireSha256(expectedManifestSha256, nameof(expectedManifestSha256));
        string root = Path.GetFullPath(sourceRoot);
        EnsureDirectoryWithoutLinks(root, "Windows proof source root");

        IReadOnlyList<string> sourceFiles = EnumerateRegularFilesWithoutLinks(root);
        EnsureNoCaseCollisions(sourceFiles.Select(path => ToRelativePath(root, path)));
        string[] manifestMatches = sourceFiles
            .Where(path => string.Equals(
                Path.GetFileName(path),
                ManifestFileName,
                StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (manifestMatches.Length != 1
            || !string.Equals(Path.GetFileName(manifestMatches[0]), ManifestFileName, StringComparison.Ordinal)
            || !string.Equals(ToRelativePath(root, manifestMatches[0]), ManifestFileName, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"Windows proof source must contain exactly one root {ManifestFileName} with canonical casing.");
        }

        byte[] manifestBytes = ReadBoundedFile(
            manifestMatches[0],
            MaximumManifestBytes,
            "Windows proof manifest");
        string manifestSha256 = Convert.ToHexStringLower(SHA256.HashData(manifestBytes));
        if (!CryptographicOperations.FixedTimeEquals(
                Convert.FromHexString(manifestSha256),
                Convert.FromHexString(expectedManifestSha256)))
        {
            throw new InvalidDataException("Windows proof manifest SHA-256 does not match the admitted digest.");
        }

        WindowsProofManifest manifest = ParseManifest(manifestBytes);
        ValidateManifest(manifest, allowLegacyV1Delivery, _timeProvider.GetUtcNow());

        var resolvedFiles = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (WindowsProofInventoryEntry entry in manifest.Artifacts)
        {
            string path = ResolveContainedPath(root, entry.RelativePath);
            EnsureRegularFileWithoutLinks(path, root, $"Windows proof {entry.Kind} artifact");
            ValidateFileBinding(path, entry);
            resolvedFiles.Add(entry.RelativePath, path);
        }

        var expectedPaths = new HashSet<string>(
            manifest.Artifacts.Select(static entry => entry.RelativePath),
            StringComparer.Ordinal)
        {
            ManifestFileName
        };
        if (allowStoreInventory)
        {
            expectedPaths.Add(WindowsProofGenerationStore.InventoryFileName);
        }
        string[] undeclared = sourceFiles
            .Select(path => ToRelativePath(root, path))
            .Where(path => !expectedPaths.Contains(path))
            .OrderBy(static path => path, StringComparer.Ordinal)
            .ToArray();
        if (undeclared.Length > 0)
        {
            throw new InvalidDataException(
                $"Windows proof source contains undeclared file '{undeclared[0]}'.");
        }

        ValidateEvidenceDocuments(manifest, resolvedFiles);
        return new WindowsProofValidatedSource(
            root,
            manifest,
            manifestBytes,
            manifestSha256,
            resolvedFiles);
    }

    public WindowsProofManifest ParseAndValidate(
        ReadOnlySpan<byte> manifestBytes,
        bool allowLegacyV1Delivery = false)
    {
        if (manifestBytes.Length == 0 || manifestBytes.Length > MaximumManifestBytes)
        {
            throw new InvalidDataException("Windows proof manifest size is invalid.");
        }

        WindowsProofManifest manifest = ParseManifest(manifestBytes);
        ValidateManifest(manifest, allowLegacyV1Delivery, _timeProvider.GetUtcNow());
        return manifest;
    }

    internal static void ValidateManifest(
        WindowsProofManifest manifest,
        bool allowLegacyV1Delivery = false,
        DateTimeOffset? now = null)
    {
        ArgumentNullException.ThrowIfNull(manifest);
        bool isLegacyV1 = string.Equals(
            manifest.SchemaVersion,
            LegacyManifestSchemaVersion,
            StringComparison.Ordinal);
        if (!string.Equals(manifest.SchemaVersion, ManifestSchemaVersion, StringComparison.Ordinal)
            && !(allowLegacyV1Delivery && isLegacyV1))
        {
            throw new InvalidDataException(
                $"Windows proof schemaVersion must equal '{ManifestSchemaVersion}'.");
        }

        if (!isLegacyV1)
        {
            ValidateFreshness(manifest, now ?? DateTimeOffset.UtcNow);
        }
        RequirePortableId(manifest.CandidateVersion, "candidateVersion");
        RequireExact(manifest.Channel, "preview", "channel");
        RequireExact(manifest.ReleaseScope, "proof_only", "releaseScope");
        RequireExact(manifest.SupportabilityState, "review_required", "supportabilityState");
        RequireExact(manifest.PublicTrustPosture, "blocked", "publicTrustPosture");
        if (!manifest.CfAccessGated)
        {
            throw new InvalidDataException("Windows proof manifest must record cfAccessGated=true.");
        }

        if (manifest.Revoked)
        {
            throw new InvalidDataException("A revoked Windows proof manifest cannot be prepared or activated.");
        }

        if (manifest.ProofOnlyPolicy is null
            || !manifest.ProofOnlyPolicy.Enabled
            || !manifest.ProofOnlyPolicy.UnsignedPreviewAllowed
            || !manifest.ProofOnlyPolicy.NativeWindowsValidationRequired)
        {
            throw new InvalidDataException(
                "Windows proof manifest must record the complete proof-only unsigned-preview policy and native-Windows follow-up requirement.");
        }

        if (manifest.Signing is null)
        {
            throw new InvalidDataException("Windows proof manifest signing evidence is required.");
        }

        if (manifest.Signing.Status is not ("pass" or "skipped_preview"))
        {
            throw new InvalidDataException("Windows proof signing status must be pass or skipped_preview.");
        }

        if (manifest.Signing.Status == "skipped_preview"
            && !manifest.Signing.ProofOnlyPolicyRecorded)
        {
            throw new InvalidDataException(
                "skipped_preview signing is allowed only when proofOnlyPolicyRecorded=true.");
        }

        if (manifest.CompatibilitySmoke is null
            || manifest.CompatibilitySmoke.Status != "pass"
            || manifest.CompatibilitySmoke.ExecutionEnvironment != "wine_compatibility"
            || manifest.CompatibilitySmoke.NativeWindows
            || manifest.CompatibilitySmoke.PayloadAcquisitionMode != "embedded")
        {
            throw new InvalidDataException(
                "Windows proof compatibility smoke must pass under wine_compatibility with nativeWindows=false and payloadAcquisitionMode=embedded.");
        }

        if (manifest.VisualExitGate is null
            || manifest.VisualExitGate.Status != "external_only")
        {
            throw new InvalidDataException("Windows proof visual exit gate must remain external_only.");
        }

        if (manifest.NativeHostHandoff is null
            || manifest.NativeHostHandoff.Status != "ready_for_windows_host"
            || manifest.NativeHostHandoff.OnlyBlocker != "visual_proof"
            || !manifest.NativeHostHandoff.OnlyBlockerIsVisualProof)
        {
            throw new InvalidDataException(
                "Windows proof native-host handoff must be ready_for_windows_host with visual_proof as its only blocker.");
        }

        if (manifest.Artifacts is null || manifest.Artifacts.Count == 0)
        {
            throw new InvalidDataException("Windows proof manifest artifacts are required.");
        }

        ValidateInventoryRows(manifest, requireBuildProvenance: !isLegacyV1);
    }

    private static void ValidateFreshness(WindowsProofManifest manifest, DateTimeOffset now)
    {
        if (manifest.GeneratedAt is null || manifest.ExpiresAt is null)
        {
            throw new InvalidDataException(
                "Windows proof v2 manifests must record generatedAt and expiresAt.");
        }

        DateTimeOffset generatedAt = manifest.GeneratedAt.Value;
        DateTimeOffset expiresAt = manifest.ExpiresAt.Value;
        if (generatedAt.Offset != TimeSpan.Zero || expiresAt.Offset != TimeSpan.Zero)
        {
            throw new InvalidDataException(
                "Windows proof generatedAt and expiresAt must use UTC (Z).");
        }

        if (generatedAt > now.Add(MaximumClockSkew))
        {
            throw new InvalidDataException(
                "Windows proof generatedAt is unreasonably far in the future.");
        }

        if (expiresAt <= generatedAt
            || expiresAt - generatedAt > MaximumProofLifetime)
        {
            throw new InvalidDataException(
                "Windows proof freshness lifetime must be positive and no longer than 24 hours.");
        }

        if (expiresAt <= now)
        {
            throw new InvalidDataException("Windows proof manifest has expired.");
        }
    }

    private static WindowsProofManifest ParseManifest(ReadOnlySpan<byte> bytes)
    {
        try
        {
            using JsonDocument document = JsonDocument.Parse(
                bytes.ToArray(),
                new JsonDocumentOptions { MaxDepth = 32 });
            RejectDuplicateProperties(document.RootElement, "manifest");
            if (string.Equals(
                    TryGetString(document.RootElement, "schemaVersion"),
                    ManifestSchemaVersion,
                    StringComparison.Ordinal))
            {
                RequireUtcZuluJsonTimestamp(document.RootElement, "generatedAt", "manifest");
                RequireUtcZuluJsonTimestamp(document.RootElement, "expiresAt", "manifest");
            }
            return JsonSerializer.Deserialize<WindowsProofManifest>(bytes, JsonOptions)
                   ?? throw new InvalidDataException("Windows proof manifest must be a JSON object.");
        }
        catch (InvalidDataException)
        {
            throw;
        }
        catch (Exception ex) when (ex is JsonException or NotSupportedException)
        {
            throw new InvalidDataException("Windows proof manifest is invalid JSON or has an invalid shape.", ex);
        }
    }

    private static void ValidateInventoryRows(
        WindowsProofManifest manifest,
        bool requireBuildProvenance)
    {
        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var fileNames = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var kinds = new Dictionary<WindowsProofArtifactKind, WindowsProofInventoryEntry>();
        string? artifactId = null;
        string? head = null;
        string? rid = null;

        foreach (WindowsProofInventoryEntry entry in manifest.Artifacts)
        {
            if (entry is null)
            {
                throw new InvalidDataException("Windows proof inventory cannot contain null rows.");
            }

            RequirePortableId(entry.ArtifactId, "artifacts[].artifactId");
            RequirePortableId(entry.Head, "artifacts[].head");
            RequirePortableId(entry.Rid, "artifacts[].rid");
            if (!string.Equals(entry.Rid, "win-x64", StringComparison.Ordinal))
            {
                throw new InvalidDataException("Windows proof inventory rid must be win-x64.");
            }

            ValidatePortableRelativePath(entry.RelativePath, "artifacts[].relativePath");
            ValidatePortableFileName(entry.FileName, "artifacts[].fileName");
            if (!string.Equals(
                    Path.GetFileName(entry.RelativePath),
                    entry.FileName,
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    "Windows proof inventory fileName must exactly match relativePath basename.");
            }

            if (entry.Size < 0)
            {
                throw new InvalidDataException("Windows proof inventory size cannot be negative.");
            }

            RequireSha256(entry.Sha256, "artifacts[].sha256");
            if (!paths.Add(entry.RelativePath) || !fileNames.Add(entry.FileName))
            {
                throw new InvalidDataException(
                    "Windows proof inventory contains a path or filename collision under portable case-insensitive comparison.");
            }

            if (!kinds.TryAdd(entry.Kind, entry))
            {
                throw new InvalidDataException(
                    $"Windows proof inventory contains duplicate {entry.Kind} rows.");
            }

            artifactId ??= entry.ArtifactId;
            head ??= entry.Head;
            rid ??= entry.Rid;
            if (entry.ArtifactId != artifactId || entry.Head != head || entry.Rid != rid)
            {
                throw new InvalidDataException(
                    "Every Windows proof inventory row must bind the same artifactId/head/rid identity.");
            }

            ValidateKindPathAndContentType(entry);
        }

        var requiredKinds = new List<WindowsProofArtifactKind>
                 {
                     WindowsProofArtifactKind.Installer,
                     WindowsProofArtifactKind.BootstrapPayload,
                     WindowsProofArtifactKind.BootstrapMetadata,
                     WindowsProofArtifactKind.SigningReceipt,
                     WindowsProofArtifactKind.StartupSmokeReceipt,
                     WindowsProofArtifactKind.VisualHandoff
                 };
        if (requireBuildProvenance)
        {
            requiredKinds.Add(WindowsProofArtifactKind.BuildProvenanceReceipt);
            requiredKinds.Add(WindowsProofArtifactKind.Sbom);
        }

        foreach (WindowsProofArtifactKind required in requiredKinds)
        {
            if (!kinds.ContainsKey(required))
            {
                throw new InvalidDataException($"Windows proof inventory requires one {required} row.");
            }
        }

        if (kinds.ContainsKey(WindowsProofArtifactKind.BootstrapPayload)
            != kinds.ContainsKey(WindowsProofArtifactKind.BootstrapMetadata))
        {
            throw new InvalidDataException(
                "Windows proof bootstrap payload and metadata must either both be present or both be absent.");
        }

        WindowsProofInventoryEntry installer = kinds[WindowsProofArtifactKind.Installer];
        string expectedArtifactId = $"{installer.Head}-{installer.Rid}-installer";
        if (installer.ArtifactId != expectedArtifactId
            || !installer.FileName.EndsWith("-installer.exe", StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "Windows proof installer identity or filename is not canonical for its head/rid.");
        }

        RequireExact(manifest.Signing.ReceiptArtifactId, installer.ArtifactId, "signing.receiptArtifactId");
        RequireExact(
            manifest.CompatibilitySmoke.ReceiptArtifactId,
            installer.ArtifactId,
            "compatibilitySmoke.receiptArtifactId");
        RequireExact(
            manifest.NativeHostHandoff.HandoffArtifactId,
            installer.ArtifactId,
            "nativeHostHandoff.handoffArtifactId");
        if (manifest.VisualExitGate.EvidenceArtifactId is not null)
        {
            RequireExact(
                manifest.VisualExitGate.EvidenceArtifactId,
                installer.ArtifactId,
                "visualExitGate.evidenceArtifactId");
            if (!kinds.ContainsKey(WindowsProofArtifactKind.VisualExitEvidence))
            {
                throw new InvalidDataException(
                    "visualExitGate.evidenceArtifactId requires a visual_exit_evidence inventory row.");
            }
        }
        else if (kinds.ContainsKey(WindowsProofArtifactKind.VisualExitEvidence))
        {
            throw new InvalidDataException(
                "A visual_exit_evidence row requires visualExitGate.evidenceArtifactId.");
        }
    }

    private static void ValidateKindPathAndContentType(WindowsProofInventoryEntry entry)
    {
        (string prefix, string contentType, string? suffix) = entry.Kind switch
        {
            WindowsProofArtifactKind.Installer => ("files/", "application/vnd.microsoft.portable-executable", ".exe"),
            WindowsProofArtifactKind.BootstrapPayload => ("files/", "application/zip", ".zip"),
            WindowsProofArtifactKind.BootstrapMetadata => ("files/", "application/json", ".json"),
            WindowsProofArtifactKind.SigningReceipt => ("signing/", "application/json", ".json"),
            WindowsProofArtifactKind.StartupSmokeReceipt => ("startup-smoke/", "application/json", ".json"),
            WindowsProofArtifactKind.BuildProvenanceReceipt => (
                "proof/build-provenance/v1/invocations/",
                "application/json",
                ".json"),
            WindowsProofArtifactKind.Sbom => (
                "proof/build-provenance/v1/sbom/",
                "application/vnd.cyclonedx+json",
                ".cdx.json"),
            WindowsProofArtifactKind.VisualHandoff => ("proof/", "application/json", ".json"),
            WindowsProofArtifactKind.VisualExitEvidence => ("proof/", "application/json", ".json"),
            _ => throw new InvalidDataException("Windows proof inventory kind is unsupported.")
        };
        if (!entry.RelativePath.StartsWith(prefix, StringComparison.Ordinal)
            || (suffix is not null && !entry.FileName.EndsWith(suffix, StringComparison.OrdinalIgnoreCase))
            || !string.Equals(entry.ContentType, contentType, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"Windows proof {entry.Kind} row has a noncanonical path, filename, or content type.");
        }
    }

    private static void ValidateFileBinding(string path, WindowsProofInventoryEntry entry)
    {
        var info = new FileInfo(path);
        if (info.Length != entry.Size)
        {
            throw new InvalidDataException(
                $"Windows proof file '{entry.RelativePath}' size does not match its manifest binding.");
        }

        string actualDigest = ComputeSha256(path);
        if (!FixedTimeHexEquals(actualDigest, entry.Sha256))
        {
            throw new InvalidDataException(
                $"Windows proof file '{entry.RelativePath}' SHA-256 does not match its manifest binding.");
        }
    }

    internal static void ValidateBootstrapPayloadArchive(
        string path,
        string displayPath,
        BootstrapPayloadPolicy? policyOverride = null)
    {
        BootstrapPayloadPolicy policy = policyOverride ?? BootstrapPayloadPolicy.Default;
        if (policy.MaximumArchiveBytes <= 0
            || policy.MaximumEntries <= 0
            || policy.MaximumEntryBytes <= 0
            || policy.MaximumTotalBytes <= 0
            || policy.MaximumCompressionRatio <= 0
            || policy.MaximumCentralDirectoryBytes <= 0
            || policy.MaximumInspectableTextBytes <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(policyOverride));
        }

        try
        {
            var archiveInfo = new FileInfo(path);
            if (archiveInfo.Length <= 0 || archiveInfo.Length > policy.MaximumArchiveBytes)
            {
                throw BootstrapPayloadError(displayPath, "archive.size");
            }

            using FileStream stream = new(
                path,
                FileMode.Open,
                FileAccess.Read,
                FileShare.Read,
                bufferSize: 64 * 1024,
                FileOptions.SequentialScan);
            IReadOnlyList<BootstrapZipEntryHeader> headers = ValidateCanonicalZipHeaders(
                stream,
                displayPath,
                policy.MaximumEntries,
                policy.MaximumCentralDirectoryBytes);
            stream.Position = 0;
            using var archive = new ZipArchive(stream, ZipArchiveMode.Read, leaveOpen: false);
            IReadOnlyList<ZipArchiveEntry> entries = archive.Entries;
            if (entries.Count == 0 || entries.Count > policy.MaximumEntries)
            {
                throw BootstrapPayloadError(displayPath, "archive.entry_count");
            }
            if (entries.Count != headers.Count)
            {
                throw BootstrapPayloadError(displayPath, "archive.directory_binding");
            }

            var exactPaths = new HashSet<string>(StringComparer.Ordinal);
            var portablePaths = new HashSet<string>(StringComparer.Ordinal);
            long totalUncompressed = 0;
            long totalCompressed = 0;
            for (int entryIndex = 0; entryIndex < entries.Count; entryIndex++)
            {
                ZipArchiveEntry entry = entries[entryIndex];
                BootstrapZipEntryHeader header = headers[entryIndex];
                int entryOrdinal = entryIndex + 1;
                BootstrapPayloadValidationException EntryError(string ruleId)
                    => BootstrapPayloadError(
                        displayPath,
                        ruleId,
                        entryOrdinal,
                        header.NameSha256);

                (string normalizedPath, bool pathIsDirectory) = NormalizeBootstrapEntryPath(
                    entry.FullName,
                    displayPath,
                    entryOrdinal,
                    header.NameSha256);
                if (!exactPaths.Add(normalizedPath))
                {
                    throw EntryError("path.duplicate");
                }
                string portablePath = BootstrapCollisionKey(
                    normalizedPath,
                    displayPath,
                    entryOrdinal,
                    header.NameSha256);
                if (!portablePaths.Add(portablePath))
                {
                    throw EntryError("path.portable_collision");
                }
                if (HasSensitiveBootstrapEntryName(normalizedPath))
                {
                    throw EntryError("name.sensitive");
                }

                int unixMode = (entry.ExternalAttributes >> 16) & 0xffff;
                int unixType = unixMode & 0xf000;
                if (unixType == 0xa000)
                {
                    throw EntryError("entry.symlink");
                }
                if (unixType is not (0 or 0x4000 or 0x8000))
                {
                    throw EntryError("entry.regular_type");
                }
                if ((pathIsDirectory && unixType == 0x8000)
                    || (!pathIsDirectory && unixType == 0x4000))
                {
                    throw EntryError("entry.directory");
                }

                long entryLength;
                long compressedLength;
                try
                {
                    entryLength = entry.Length;
                    compressedLength = entry.CompressedLength;
                }
                catch (Exception ex) when (IsZipFailure(ex))
                {
                    throw EntryError("entry.metadata_integrity");
                }
                if (entryLength < 0 || entryLength > policy.MaximumEntryBytes)
                {
                    throw EntryError("entry.decompressed_size");
                }
                if (compressedLength < 0)
                {
                    throw EntryError("entry.compressed_size");
                }
                if (entryLength > 0
                    && (compressedLength == 0
                        || entryLength > compressedLength * policy.MaximumCompressionRatio))
                {
                    throw EntryError("entry.compression_ratio");
                }

                totalUncompressed = checked(totalUncompressed + entryLength);
                totalCompressed = checked(totalCompressed + compressedLength);
                if (totalUncompressed > policy.MaximumTotalBytes)
                {
                    throw EntryError("archive.decompressed_size");
                }
                ScanBootstrapPayloadEntry(
                    entry,
                    displayPath,
                    policy,
                    header.Crc32,
                    entryOrdinal,
                    header.NameSha256);
            }

            if (totalUncompressed <= 0)
            {
                throw BootstrapPayloadError(displayPath, "archive.non_empty");
            }
            if (totalCompressed <= 0
                || totalUncompressed > totalCompressed * policy.MaximumCompressionRatio)
            {
                throw BootstrapPayloadError(displayPath, "archive.compression_ratio");
            }
        }
        catch (BootstrapPayloadValidationException ex)
        {
            throw new InvalidDataException(ex.Message);
        }
        catch (Exception ex) when (IsZipFailure(ex))
        {
            throw new InvalidDataException(
                BootstrapPayloadError(displayPath, "archive.format").Message);
        }
    }

    private static IReadOnlyList<BootstrapZipEntryHeader> ValidateCanonicalZipHeaders(
        FileStream stream,
        string displayPath,
        int maximumEntries,
        long maximumCentralDirectoryBytes)
    {
        const uint endOfCentralDirectorySignature = 0x06054b50;
        const uint centralDirectoryEntrySignature = 0x02014b50;
        const uint localEntrySignature = 0x04034b50;
        const int endOfCentralDirectoryBytes = 22;
        const int centralDirectoryEntryBytes = 46;
        const int localEntryBytes = 30;
        const ushort encryptionFlags = 0x0041;

        int tailLength = checked((int)Math.Min(stream.Length, 65_535 + endOfCentralDirectoryBytes));
        byte[] tail = new byte[tailLength];
        stream.Position = stream.Length - tailLength;
        stream.ReadExactly(tail);
        long tailOffset = stream.Length - tailLength;
        int endIndex = -1;
        for (int index = tail.Length - endOfCentralDirectoryBytes; index >= 0; index--)
        {
            if (BinaryPrimitives.ReadUInt32LittleEndian(tail.AsSpan(index, sizeof(uint)))
                    != endOfCentralDirectorySignature)
            {
                continue;
            }
            ushort commentLength = BinaryPrimitives.ReadUInt16LittleEndian(tail.AsSpan(index + 20, sizeof(ushort)));
            if (tailOffset + index + endOfCentralDirectoryBytes + commentLength == stream.Length)
            {
                endIndex = index;
                break;
            }
        }
        if (endIndex < 0)
        {
            throw BootstrapPayloadError(displayPath, "archive.format");
        }

        ReadOnlySpan<byte> end = tail.AsSpan(endIndex, endOfCentralDirectoryBytes);
        ushort diskNumber = BinaryPrimitives.ReadUInt16LittleEndian(end[4..]);
        ushort centralDirectoryDisk = BinaryPrimitives.ReadUInt16LittleEndian(end[6..]);
        ushort diskEntries = BinaryPrimitives.ReadUInt16LittleEndian(end[8..]);
        ushort totalEntries = BinaryPrimitives.ReadUInt16LittleEndian(end[10..]);
        uint centralDirectorySize = BinaryPrimitives.ReadUInt32LittleEndian(end[12..]);
        uint centralDirectoryOffset = BinaryPrimitives.ReadUInt32LittleEndian(end[16..]);
        long endOffset = tailOffset + endIndex;
        if (diskNumber != 0
            || centralDirectoryDisk != 0
            || diskEntries != totalEntries
            || totalEntries == ushort.MaxValue
            || centralDirectorySize == uint.MaxValue
            || centralDirectoryOffset == uint.MaxValue
            || (long)centralDirectoryOffset + centralDirectorySize != endOffset)
        {
            throw BootstrapPayloadError(displayPath, "archive.single_disk_directory");
        }
        if (centralDirectorySize > maximumCentralDirectoryBytes)
        {
            throw BootstrapPayloadError(displayPath, "archive.central_directory_size");
        }
        if (totalEntries == 0 || totalEntries > maximumEntries)
        {
            throw BootstrapPayloadError(displayPath, "archive.entry_count");
        }

        long cursor = centralDirectoryOffset;
        long centralDirectoryEnd = cursor + centralDirectorySize;
        byte[] centralHeader = new byte[centralDirectoryEntryBytes];
        byte[] localHeader = new byte[localEntryBytes];
        var headers = new List<BootstrapZipEntryHeader>(totalEntries);
        for (int entryIndex = 0; entryIndex < totalEntries; entryIndex++)
        {
            int entryOrdinal = entryIndex + 1;
            if (cursor < 0 || cursor + centralHeader.Length > centralDirectoryEnd)
            {
                throw BootstrapPayloadError(
                    displayPath,
                    "archive.directory_bounds",
                    entryOrdinal);
            }
            stream.Position = cursor;
            stream.ReadExactly(centralHeader);
            if (BinaryPrimitives.ReadUInt32LittleEndian(centralHeader) != centralDirectoryEntrySignature)
            {
                throw BootstrapPayloadError(
                    displayPath,
                    "entry.central_header",
                    entryOrdinal);
            }

            ushort fileNameLength = BinaryPrimitives.ReadUInt16LittleEndian(centralHeader.AsSpan(28));
            ushort extraLength = BinaryPrimitives.ReadUInt16LittleEndian(centralHeader.AsSpan(30));
            ushort commentLength = BinaryPrimitives.ReadUInt16LittleEndian(centralHeader.AsSpan(32));
            long nextCursor = checked(
                cursor
                + centralDirectoryEntryBytes
                + fileNameLength
                + extraLength
                + commentLength);
            if (nextCursor > centralDirectoryEnd)
            {
                throw BootstrapPayloadError(
                    displayPath,
                    "archive.directory_bounds",
                    entryOrdinal);
            }
            byte[] centralName = new byte[fileNameLength];
            stream.Position = cursor + centralDirectoryEntryBytes;
            stream.ReadExactly(centralName);
            string nameSha256 = Convert.ToHexStringLower(SHA256.HashData(centralName));
            BootstrapPayloadValidationException EntryError(string ruleId)
                => BootstrapPayloadError(displayPath, ruleId, entryOrdinal, nameSha256);

            ushort flags = BinaryPrimitives.ReadUInt16LittleEndian(centralHeader.AsSpan(8));
            if ((flags & encryptionFlags) != 0)
            {
                throw EntryError("entry.encrypted");
            }
            ushort compressionMethod = BinaryPrimitives.ReadUInt16LittleEndian(centralHeader.AsSpan(10));
            if (compressionMethod is not (0 or 8))
            {
                throw EntryError("entry.compression_method");
            }
            uint crc32 = BinaryPrimitives.ReadUInt32LittleEndian(centralHeader.AsSpan(16));
            uint localOffset = BinaryPrimitives.ReadUInt32LittleEndian(centralHeader.AsSpan(42));
            if (localOffset == uint.MaxValue
                || (long)localOffset + localHeader.Length > centralDirectoryOffset)
            {
                throw EntryError("entry.local_header_bounds");
            }

            stream.Position = localOffset;
            stream.ReadExactly(localHeader);
            if (BinaryPrimitives.ReadUInt32LittleEndian(localHeader) != localEntrySignature)
            {
                throw EntryError("entry.local_header");
            }
            ushort localFlags = BinaryPrimitives.ReadUInt16LittleEndian(localHeader.AsSpan(6));
            if ((localFlags & encryptionFlags) != 0)
            {
                throw EntryError("entry.encrypted");
            }
            if (localFlags != flags)
            {
                throw EntryError("entry.flags_binding");
            }
            ushort localCompressionMethod = BinaryPrimitives.ReadUInt16LittleEndian(localHeader.AsSpan(8));
            if (localCompressionMethod != compressionMethod)
            {
                throw EntryError("entry.compression_binding");
            }
            ushort localNameLength = BinaryPrimitives.ReadUInt16LittleEndian(localHeader.AsSpan(26));
            ushort localExtraLength = BinaryPrimitives.ReadUInt16LittleEndian(localHeader.AsSpan(28));
            if ((long)localOffset + localEntryBytes + localNameLength + localExtraLength > centralDirectoryOffset)
            {
                throw EntryError("entry.local_header_bounds");
            }
            byte[] localName = new byte[localNameLength];
            stream.Position = localOffset + localEntryBytes;
            stream.ReadExactly(localName);
            if (!centralName.AsSpan().SequenceEqual(localName))
            {
                throw EntryError("entry.name_binding");
            }

            headers.Add(new BootstrapZipEntryHeader(crc32, nameSha256));
            cursor = nextCursor;
        }
        if (cursor != centralDirectoryEnd)
        {
            throw BootstrapPayloadError(displayPath, "archive.directory_bounds");
        }
        return headers;
    }

    private static (string NormalizedPath, bool IsDirectory) NormalizeBootstrapEntryPath(
        string name,
        string displayPath,
        int entryOrdinal,
        string nameSha256)
    {
        BootstrapPayloadValidationException PathError(string ruleId)
            => BootstrapPayloadError(displayPath, ruleId, entryOrdinal, nameSha256);

        if (string.IsNullOrEmpty(name) || name.Contains('\0', StringComparison.Ordinal))
        {
            throw PathError("path.non_empty");
        }
        if (name.Any(static character => character is < ' ' or > '~'))
        {
            throw PathError("path.ascii_printable");
        }
        if (name.Contains('\\', StringComparison.Ordinal))
        {
            throw PathError("path.forward_slash");
        }
        if (name.Length > 1024)
        {
            throw PathError("path.length");
        }
        if (name[0] == '/'
            || (name.Length >= 2 && char.IsAsciiLetter(name[0]) && name[1] == ':'))
        {
            throw PathError("path.relative");
        }

        bool isDirectory = name[^1] == '/';
        string candidate = isDirectory ? name[..^1] : name;
        string[] segments = candidate.Split('/', StringSplitOptions.None);
        if (candidate.Length == 0
            || segments.Any(static segment => segment.Length == 0 || segment is "." or ".."))
        {
            throw PathError("path.relative");
        }
        foreach (string segment in segments)
        {
            if (segment.Length > 255)
            {
                throw PathError("path.segment_length");
            }
            if (segment.Any(WindowsInvalidEntryNameCharacters.Contains)
                || segment[^1] is '.' or ' ')
            {
                throw PathError("path.windows_invalid_segment");
            }
            string stem = segment.Split('.', 2)[0];
            if (WindowsReservedDeviceStems.Contains(stem))
            {
                throw PathError("path.windows_reserved_device");
            }
        }
        return (string.Join('/', segments), isDirectory);
    }

    private static string BootstrapCollisionKey(
        string normalizedPath,
        string displayPath,
        int entryOrdinal,
        string nameSha256)
    {
        // Printable ASCII admission makes invariant casing deterministic across
        // runtimes and operating systems.
        return normalizedPath.ToUpperInvariant();
    }

    private static bool HasSensitiveBootstrapEntryName(string normalizedPath)
    {
        foreach (string segment in normalizedPath.Split('/'))
        {
            string lowered = segment.ToLowerInvariant();
            string extension = Path.GetExtension(lowered);
            if (lowered == ".env" || lowered.StartsWith(".env.", StringComparison.Ordinal))
            {
                return true;
            }
            if (SensitiveArchiveExtensions.Contains(extension))
            {
                return true;
            }
            string collapsed = string.Concat(lowered.Where(
                static character => character is not ('-' or '_' or '.' or ' ')));
            string collapsedStem = string.Concat(Path.GetFileNameWithoutExtension(lowered).Where(
                static character => character is not ('-' or '_' or '.' or ' ')));
            if (collapsed.Contains("privatekeyid", StringComparison.Ordinal)
                || collapsed.Contains("serviceaccount", StringComparison.Ordinal)
                || (extension == ".pem"
                    && collapsedStem.Contains("privatekey", StringComparison.Ordinal))
                || collapsed is "applicationdefaultcredentialsjson"
                    or "gcpcredentialsjson"
                    or "googlecredentialsjson")
            {
                return true;
            }
        }
        return false;
    }

    private static void ScanBootstrapPayloadEntry(
        ZipArchiveEntry entry,
        string displayPath,
        BootstrapPayloadPolicy policy,
        uint expectedCrc32,
        int entryOrdinal,
        string nameSha256)
    {
        BootstrapPayloadValidationException EntryError(string ruleId)
            => BootstrapPayloadError(displayPath, ruleId, entryOrdinal, nameSha256);

        MemoryStream? collected = entry.Length <= policy.MaximumInspectableTextBytes
            ? new MemoryStream(checked((int)entry.Length))
            : null;
        using (collected)
        {
            byte[] buffer = new byte[64 * 1024];
            byte[] tail = [];
            var prefix = new MemoryStream(capacity: 4096);
            long observed = 0;
            uint crc32 = uint.MaxValue;
            string? streamedSensitiveRule = null;
            try
            {
                using Stream stream = entry.Open();
                while (true)
                {
                    int read = stream.Read(buffer, 0, buffer.Length);
                    if (read == 0)
                    {
                        break;
                    }
                    observed += read;
                    if (observed > entry.Length || observed > policy.MaximumEntryBytes)
                    {
                        throw EntryError("entry.decompressed_size");
                    }
                    crc32 = UpdateBootstrapCrc32(crc32, buffer.AsSpan(0, read));
                    if (prefix.Length < 4096)
                    {
                        int prefixByteCount = Math.Min(read, 4096 - checked((int)prefix.Length));
                        prefix.Write(buffer, 0, prefixByteCount);
                    }
                    collected?.Write(buffer, 0, read);

                    byte[] scanBytes = new byte[tail.Length + read];
                    Buffer.BlockCopy(tail, 0, scanBytes, 0, tail.Length);
                    Buffer.BlockCopy(buffer, 0, scanBytes, tail.Length, read);
                    string scanText = Encoding.Latin1.GetString(scanBytes);
                    if (PrivateKeyMarkerPattern.IsMatch(scanText))
                    {
                        throw EntryError("content.private_key_marker");
                    }
                    if (AuthorizationBearerPattern.IsMatch(scanText))
                    {
                        streamedSensitiveRule ??= "content.bearer_assignment";
                    }
                    if (TokenAssignmentPattern.IsMatch(scanText))
                    {
                        streamedSensitiveRule ??= "content.credential_assignment";
                    }
                    if (ConnectionAssignmentPattern.IsMatch(scanText))
                    {
                        streamedSensitiveRule ??= "content.connection_string_assignment";
                    }
                    int tailLength = Math.Min(4096, scanBytes.Length);
                    tail = scanBytes[^tailLength..];
                }
            }
            catch (BootstrapPayloadValidationException)
            {
                throw;
            }
            catch (Exception ex) when (IsZipFailure(ex))
            {
                throw EntryError("entry.integrity");
            }

            if (observed != entry.Length)
            {
                throw EntryError("entry.declared_size");
            }
            if ((crc32 ^ uint.MaxValue) != expectedCrc32)
            {
                throw EntryError("entry.crc32");
            }

            byte[] prefixBytes = prefix.ToArray();
            bool looksLikeJson = LooksLikeJson(prefixBytes);
            if (collected is null)
            {
                if (looksLikeJson)
                {
                    throw EntryError("content.json_inspection_size");
                }
                if (streamedSensitiveRule is not null)
                {
                    throw EntryError(streamedSensitiveRule);
                }
                if (HasKnownBinaryMagic(prefixBytes))
                {
                    return;
                }
                // Unknown large content cannot be safely treated as binary:
                // streamed secret checks completed, but text/JSON decoding
                // would be incomplete.
                throw EntryError("content.text_inspection_size");
            }

            byte[] content = collected.ToArray();
            if (looksLikeJson)
            {
                bool parsedJson = false;
                try
                {
                    ReadOnlyMemory<byte> json = StripUtf8Bom(content);
                    using JsonDocument document = JsonDocument.Parse(
                        json,
                        new JsonDocumentOptions { MaxDepth = 32 });
                    parsedJson = true;
                    if (ContainsGoogleServiceAccount(document.RootElement, depth: 0))
                    {
                        throw EntryError("content.google_service_account_json");
                    }
                    if (ContainsSensitiveJsonValue(document.RootElement, depth: 0))
                    {
                        throw EntryError(
                            streamedSensitiveRule ?? "content.sensitive_json_value");
                    }
                }
                catch (BootstrapPayloadValidationException)
                {
                    throw;
                }
                catch (JsonException)
                {
                    // A non-JSON text file may legitimately begin with a brace.
                }
                if (parsedJson)
                {
                    // Valid JSON is decided structurally so null, empty-string,
                    // empty-object, and empty-array values remain genuinely empty.
                    return;
                }
            }

            if (streamedSensitiveRule is not null)
            {
                throw EntryError(streamedSensitiveRule);
            }

            string? text = DecodeText(content);
            if (text is null)
            {
                return;
            }
            string normalizedText = text.Replace("\0", string.Empty, StringComparison.Ordinal);
            if (AuthorizationBearerPattern.IsMatch(normalizedText))
            {
                throw EntryError("content.bearer_assignment");
            }
            if (TokenAssignmentPattern.IsMatch(normalizedText))
            {
                throw EntryError("content.credential_assignment");
            }
            if (ConnectionAssignmentPattern.IsMatch(normalizedText))
            {
                throw EntryError("content.connection_string_assignment");
            }
        }
    }

    private static bool LooksLikeJson(ReadOnlySpan<byte> bytes)
    {
        int index = StartsWithBytes(bytes, 0xef, 0xbb, 0xbf) ? 3 : 0;
        while (index < bytes.Length && bytes[index] is (byte)' ' or (byte)'\t' or (byte)'\r' or (byte)'\n')
        {
            index++;
        }
        return index < bytes.Length && bytes[index] is (byte)'{' or (byte)'[';
    }

    private static ReadOnlyMemory<byte> StripUtf8Bom(byte[] bytes)
        => StartsWithBytes(bytes, 0xef, 0xbb, 0xbf)
            ? bytes.AsMemory(3)
            : bytes;

    private static bool HasKnownBinaryMagic(ReadOnlySpan<byte> bytes)
        => bytes.StartsWith("MZ"u8)
           || StartsWithBytes(bytes, 0x7f, (byte)'E', (byte)'L', (byte)'F')
           || StartsWithBytes(bytes, 0x89, (byte)'P', (byte)'N', (byte)'G')
           || StartsWithBytes(bytes, 0xff, 0xd8, 0xff)
           || bytes.StartsWith("%PDF"u8);

    private static string? DecodeText(byte[] bytes)
    {
        ReadOnlySpan<byte> sample = bytes.AsSpan(0, Math.Min(bytes.Length, 64 * 1024));
        if (sample.Length == 0)
        {
            return string.Empty;
        }
        if (HasKnownBinaryMagic(sample))
        {
            return null;
        }

        string? decoded = null;
        try
        {
            decoded = new UTF8Encoding(false, true).GetString(bytes);
        }
        catch (DecoderFallbackException)
        {
            // Try a BOM-marked or clearly NUL-delimited UTF-16 text payload below.
        }
        if (decoded is null
            && (StartsWithBytes(sample, 0xff, 0xfe)
                || StartsWithBytes(sample, 0xfe, 0xff)
                || CountZeroBytes(sample) > sample.Length / 10))
        {
            try
            {
                decoded = StartsWithBytes(sample, 0xfe, 0xff)
                    ? new UnicodeEncoding(bigEndian: true, byteOrderMark: true, throwOnInvalidBytes: true).GetString(bytes)
                    : new UnicodeEncoding(bigEndian: false, byteOrderMark: true, throwOnInvalidBytes: true).GetString(bytes);
            }
            catch (DecoderFallbackException)
            {
                return null;
            }
        }
        if (decoded is null || decoded.Length == 0)
        {
            return decoded;
        }
        int acceptable = decoded.Count(
            static character => !char.IsControl(character) || character is '\r' or '\n' or '\t');
        return acceptable * 100L >= decoded.Length * 95L ? decoded : null;
    }

    private static int CountZeroBytes(ReadOnlySpan<byte> bytes)
    {
        int count = 0;
        foreach (byte value in bytes)
        {
            if (value == 0)
            {
                count++;
            }
        }
        return count;
    }

    private static uint UpdateBootstrapCrc32(uint crc32, ReadOnlySpan<byte> bytes)
    {
        foreach (byte value in bytes)
        {
            crc32 = BootstrapCrc32Table[(byte)(crc32 ^ value)] ^ (crc32 >> 8);
        }
        return crc32;
    }

    private static uint[] CreateBootstrapCrc32Table()
    {
        var table = new uint[256];
        for (int index = 0; index < table.Length; index++)
        {
            uint value = (uint)index;
            for (int bit = 0; bit < 8; bit++)
            {
                value = (value & 1) != 0
                    ? 0xedb88320U ^ (value >> 1)
                    : value >> 1;
            }
            table[index] = value;
        }
        return table;
    }

    private static bool StartsWithBytes(ReadOnlySpan<byte> bytes, params byte[] prefix)
        => bytes.StartsWith(prefix);

    private static bool IsZipFailure(Exception exception)
        => exception is InvalidDataException
            or IOException
            or NotSupportedException
            or ArgumentException
            or OverflowException;

    private static bool ContainsGoogleServiceAccount(JsonElement element, int depth)
    {
        if (depth > 32)
        {
            return false;
        }
        if (element.ValueKind == JsonValueKind.Object)
        {
            var keys = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            string? type = null;
            foreach (JsonProperty property in element.EnumerateObject())
            {
                keys.Add(property.Name);
                if (string.Equals(property.Name, "type", StringComparison.OrdinalIgnoreCase)
                    && property.Value.ValueKind == JsonValueKind.String)
                {
                    type = property.Value.GetString();
                }
            }
            bool typedServiceAccount = string.Equals(type, "service_account", StringComparison.OrdinalIgnoreCase)
                                       && keys.IsSupersetOf(["private_key", "private_key_id", "client_email", "token_uri"]);
            bool structuralServiceAccount = keys.IsSupersetOf(
                ["private_key", "client_email", "token_uri", "project_id"]);
            if (typedServiceAccount || structuralServiceAccount)
            {
                return true;
            }
            return element.EnumerateObject().Any(
                property => ContainsGoogleServiceAccount(property.Value, depth + 1));
        }
        if (element.ValueKind == JsonValueKind.Array)
        {
            return element.EnumerateArray().Any(child => ContainsGoogleServiceAccount(child, depth + 1));
        }
        return false;
    }

    private static bool ContainsSensitiveJsonValue(JsonElement element, int depth)
    {
        if (depth > 32)
        {
            return false;
        }
        if (element.ValueKind == JsonValueKind.Object)
        {
            foreach (JsonProperty property in element.EnumerateObject())
            {
                string collapsedKey = string.Concat(
                    property.Name
                        .ToLowerInvariant()
                        .Where(static character => character is not ('-' or '_' or '.' or ' ')));
                if ((SensitiveJsonKeys.Contains(collapsedKey)
                     || collapsedKey.StartsWith("connectionstrings", StringComparison.Ordinal))
                    && JsonValueIsNonEmpty(property.Value))
                {
                    return true;
                }
                if (ContainsSensitiveJsonValue(property.Value, depth + 1))
                {
                    return true;
                }
            }
            return false;
        }
        return element.ValueKind == JsonValueKind.Array
               && element.EnumerateArray().Any(child => ContainsSensitiveJsonValue(child, depth + 1));
    }

    private static bool JsonValueIsNonEmpty(JsonElement element)
        => element.ValueKind switch
        {
            JsonValueKind.Null or JsonValueKind.Undefined => false,
            JsonValueKind.String => !string.IsNullOrWhiteSpace(element.GetString()),
            JsonValueKind.Object => element.EnumerateObject().Any(),
            JsonValueKind.Array => element.EnumerateArray().Any(),
            _ => true
        };

    private static BootstrapPayloadValidationException BootstrapPayloadError(
        string displayPath,
        string ruleId,
        int? entryOrdinal = null,
        string? entryNameSha256 = null)
    {
        string boundedPath = BoundDiagnosticPath(displayPath);
        var diagnostic = new StringBuilder(
            $"Windows bootstrap payload '{boundedPath}' violates policy={BootstrapPayloadPolicyVersion} rule={ruleId}");
        if (entryOrdinal is not null)
        {
            diagnostic.Append(" entry_ordinal=").Append(entryOrdinal.Value);
        }
        if (entryNameSha256 is not null)
        {
            diagnostic.Append(" entry_name_sha256=").Append(
                entryNameSha256.Length <= 64
                    ? entryNameSha256
                    : entryNameSha256[..64]);
        }
        diagnostic.Append('.');
        return new BootstrapPayloadValidationException(diagnostic.ToString());
    }

    private static string BoundDiagnosticPath(string? value)
    {
        string printable = new((value ?? string.Empty)
            .Select(static character => char.IsControl(character) ? '?' : character)
            .Take(256)
            .ToArray());
        return printable;
    }

    private sealed class BootstrapPayloadValidationException(string message)
        : Exception(message);

    private static void ValidateEvidenceDocuments(
        WindowsProofManifest manifest,
        IReadOnlyDictionary<string, string> files)
    {
        var byKind = manifest.Artifacts.ToDictionary(static entry => entry.Kind);
        WindowsProofInventoryEntry installer = byKind[WindowsProofArtifactKind.Installer];
        using JsonDocument signing = ReadEvidence(
            files[byKind[WindowsProofArtifactKind.SigningReceipt].RelativePath],
            "Windows signing receipt");
        JsonElement signingRoot = signing.RootElement;
        RequireJsonString(signingRoot, "contractName", "chummer6-ui.desktop_artifact_signing", "signing receipt");
        RequireJsonString(signingRoot, "platform", "windows", "signing receipt");
        RequireJsonString(signingRoot, "app", installer.Head, "signing receipt");
        RequireJsonString(signingRoot, "rid", installer.Rid, "signing receipt");
        RequireJsonString(signingRoot, "releaseChannel", "preview", "signing receipt");
        RequireJsonString(signingRoot, "releaseVersion", manifest.CandidateVersion, "signing receipt");
        RequireJsonString(signingRoot, "signingStatus", manifest.Signing.Status, "signing receipt");
        JsonElement signingArtifacts = RequireJsonArray(signingRoot, "artifacts", "signing receipt");
        JsonElement[] installerSigningRows = signingArtifacts.EnumerateArray()
            .Where(row => row.ValueKind == JsonValueKind.Object
                          && TryGetString(row, "fileName") == installer.FileName)
            .ToArray();
        if (installerSigningRows.Length != 1)
        {
            throw new InvalidDataException("Windows signing receipt must bind exactly one installer row.");
        }

        RequireDigestJson(
            installerSigningRows[0],
            "sha256",
            installer.Sha256,
            "signing receipt installer row");
        RequireJsonString(
            installerSigningRows[0],
            "signingStatus",
            manifest.Signing.Status,
            "signing receipt installer row");

        using JsonDocument smoke = ReadEvidence(
            files[byKind[WindowsProofArtifactKind.StartupSmokeReceipt].RelativePath],
            "Windows compatibility smoke receipt");
        JsonElement smokeRoot = smoke.RootElement;
        RequireJsonString(smokeRoot, "status", "pass", "startup smoke receipt");
        RequireJsonString(smokeRoot, "headId", installer.Head, "startup smoke receipt");
        RequireJsonString(smokeRoot, "version", manifest.CandidateVersion, "startup smoke receipt");
        RequireJsonString(smokeRoot, "releaseVersion", manifest.CandidateVersion, "startup smoke receipt");
        RequireJsonString(smokeRoot, "channelId", "preview", "startup smoke receipt");
        RequireJsonString(smokeRoot, "platform", "windows", "startup smoke receipt");
        RequireJsonString(smokeRoot, "rid", installer.Rid, "startup smoke receipt");
        RequireJsonString(
            smokeRoot,
            "artifactId",
            installer.ArtifactId,
            "startup smoke receipt");
        RequireJsonString(
            smokeRoot,
            "artifactFileName",
            installer.FileName,
            "startup smoke receipt");
        RequireJsonString(
            smokeRoot,
            "artifactRelativePath",
            installer.RelativePath,
            "startup smoke receipt");
        RequireDigestJson(smokeRoot, "artifactDigest", installer.Sha256, "startup smoke receipt");
        RequireDigestJson(smokeRoot, "artifactSha256", installer.Sha256, "startup smoke receipt");
        RequireJsonString(
            smokeRoot,
            "executionEnvironment",
            manifest.CompatibilitySmoke.ExecutionEnvironment,
            "startup smoke receipt");
        RequireJsonString(
            smokeRoot,
            "bootstrapPayloadAcquisitionMode",
            manifest.CompatibilitySmoke.PayloadAcquisitionMode,
            "startup smoke receipt");
        RequireJsonString(
            smokeRoot,
            "verificationScope",
            "windows_compatibility_startup",
            "startup smoke receipt");
        JsonElement nativeHost = RequireJsonObject(smokeRoot, "nativeHostEvidence", "startup smoke receipt");
        RequireJsonString(
            nativeHost,
            "contractName",
            "chummer6-ui.native_windows_host_evidence",
            "startup smoke receipt.nativeHostEvidence");
        RequireJsonString(
            nativeHost,
            "status",
            "not_native",
            "startup smoke receipt.nativeHostEvidence");
        RequireJsonString(
            nativeHost,
            "runner",
            "wine",
            "startup smoke receipt.nativeHostEvidence");
        if (!nativeHost.TryGetProperty("isNativeWindows", out JsonElement isNative)
            || isNative.ValueKind is not (JsonValueKind.True or JsonValueKind.False)
            || isNative.GetBoolean())
        {
            throw new InvalidDataException(
                "Windows compatibility smoke receipt must record nativeHostEvidence.isNativeWindows=false.");
        }

        WindowsProofInventoryEntry payload = byKind[WindowsProofArtifactKind.BootstrapPayload];
        WindowsProofInventoryEntry metadataRow = byKind[WindowsProofArtifactKind.BootstrapMetadata];
        ValidateBootstrapPayloadArchive(
            files[payload.RelativePath],
            payload.RelativePath);
        RequireJsonString(
            smokeRoot,
            "bootstrapPayloadFileName",
            payload.FileName,
            "startup smoke receipt");
        RequireDigestJson(
            smokeRoot,
            "bootstrapPayloadSha256",
            payload.Sha256,
            "startup smoke receipt");
        RequireJsonInt64(
            smokeRoot,
            "bootstrapPayloadSizeBytes",
            payload.Size,
            "startup smoke receipt");

        string expectedPayloadUrl =
            $"https://chummer.run/downloads/proof/windows/candidates/{manifest.CandidateVersion}/files/{payload.FileName}";
        using JsonDocument metadata = ReadEvidence(
            files[metadataRow.RelativePath],
            "Windows bootstrap payload metadata");
        JsonElement metadataRoot = metadata.RootElement;
        RequireJsonString(
            metadataRoot,
            "contractName",
            "chummer6-ui.windows_bootstrap_payload",
            "bootstrap payload metadata");
        RequireJsonString(metadataRoot, "fileName", payload.FileName, "bootstrap payload metadata");
        RequireJsonString(metadataRoot, "downloadUrl", expectedPayloadUrl, "bootstrap payload metadata");
        RequireDigestJson(metadataRoot, "sha256", payload.Sha256, "bootstrap payload metadata");
        RequireJsonInt64(metadataRoot, "sizeBytes", payload.Size, "bootstrap payload metadata");
        RequireJsonString(
            metadataRoot,
            "payloadAcquisitionMode",
            "embedded",
            "bootstrap payload metadata");
        RequireJsonString(
            metadataRoot,
            "installerFileName",
            installer.FileName,
            "bootstrap payload metadata");
        RequireJsonString(
            metadataRoot,
            "releaseVersion",
            manifest.CandidateVersion,
            "bootstrap payload metadata");
        ValidateEmbeddedInstallerMetadata(
            files[installer.RelativePath],
            installer,
            payload,
            expectedPayloadUrl);

        if (string.Equals(manifest.SchemaVersion, ManifestSchemaVersion, StringComparison.Ordinal))
        {
            ValidateBuildProvenanceDocuments(manifest, files, byKind, installer);
        }

        using JsonDocument handoff = ReadEvidence(
            files[byKind[WindowsProofArtifactKind.VisualHandoff].RelativePath],
            "Windows native-host handoff");
        JsonElement handoffRoot = handoff.RootElement;
        RequireJsonString(
            handoffRoot,
            "contract_name",
            "chummer6-ui.windows_installer_visual_proof_handoff",
            "native-host handoff");
        RequireJsonBoolean(handoffRoot, "handoff_only", expected: true, "native-host handoff");
        RequireJsonString(
            handoffRoot,
            "handoff_scope",
            "staged_nightly_windows_visual_proof",
            "native-host handoff");
        RequireJsonBoolean(
            handoffRoot,
            "stable_release_unchanged",
            expected: true,
            "native-host handoff");
        RequireJsonBoolean(
            handoffRoot,
            "requires_separate_publish_lane",
            expected: true,
            "native-host handoff");
        RequireJsonString(handoffRoot, "status", "ready_for_windows_host", "native-host handoff");
        RequireJsonString(handoffRoot, "only_blocker", "visual_proof", "native-host handoff");
        RequireJsonBoolean(
            handoffRoot,
            "only_blocker_is_visual_proof",
            expected: true,
            "native-host handoff");
        JsonElement blockers = RequireJsonArray(handoffRoot, "blockers", "native-host handoff");
        if (blockers.GetArrayLength() != 0)
        {
            throw new InvalidDataException(
                "native-host handoff.blockers must be empty; visual proof is the only permitted outstanding gate.");
        }
        JsonElement release = RequireJsonObject(handoffRoot, "release", "native-host handoff");
        RequireJsonString(release, "channel_id", "preview", "native-host handoff.release");
        RequireJsonString(release, "version", manifest.CandidateVersion, "native-host handoff.release");
        RequireJsonString(
            release,
            "release_version",
            manifest.CandidateVersion,
            "native-host handoff.release");
        RequireJsonString(release, "release_scope", "proof_only", "native-host handoff.release");
        RequireJsonString(
            release,
            "supportability_state",
            "review_required",
            "native-host handoff.release");
        RequireJsonString(
            release,
            "public_trust_posture",
            "blocked",
            "native-host handoff.release");
        RequireJsonBoolean(
            release,
            "cf_access_gated",
            expected: true,
            "native-host handoff.release");
        JsonElement handoffInstaller = RequireJsonObject(
            handoffRoot,
            "windows_installer",
            "native-host handoff");
        RequireJsonString(
            handoffInstaller,
            "artifact_id",
            installer.ArtifactId,
            "native-host handoff.windows_installer");
        RequireJsonString(
            handoffInstaller,
            "file_name",
            installer.FileName,
            "native-host handoff.windows_installer");
        RequireDigestJson(
            handoffInstaller,
            "sha256",
            installer.Sha256,
            "native-host handoff.windows_installer");
        WindowsProofInventoryEntry smokeRow = byKind[WindowsProofArtifactKind.StartupSmokeReceipt];
        string? smokePath = TryGetString(handoffRoot, "startup_smoke_path");
        if (Path.GetFileName(smokePath) != smokeRow.FileName)
        {
            throw new InvalidDataException(
                "native-host handoff.startup_smoke_path does not name its bound receipt.");
        }

        JsonElement embeddedSmoke = RequireJsonObject(
            handoffRoot,
            "startup_smoke",
            "native-host handoff");
        RequireJsonString(embeddedSmoke, "status", "pass", "native-host handoff.startup_smoke");
        RequireJsonString(
            embeddedSmoke,
            "version",
            manifest.CandidateVersion,
            "native-host handoff.startup_smoke");
        RequireJsonString(
            embeddedSmoke,
            "release_version",
            manifest.CandidateVersion,
            "native-host handoff.startup_smoke");
        RequireJsonString(
            embeddedSmoke,
            "artifact_id",
            installer.ArtifactId,
            "native-host handoff.startup_smoke");
        RequireJsonString(
            embeddedSmoke,
            "artifact_file_name",
            installer.FileName,
            "native-host handoff.startup_smoke");
        RequireDigestJson(
            embeddedSmoke,
            "artifact_digest",
            installer.Sha256,
            "native-host handoff.startup_smoke");
        RequireJsonString(
            embeddedSmoke,
            "receipt_file_name",
            smokeRow.FileName,
            "native-host handoff.startup_smoke");
        RequireDigestJson(
            embeddedSmoke,
            "receipt_sha256",
            smokeRow.Sha256,
            "native-host handoff.startup_smoke");
        RequireJsonString(
            embeddedSmoke,
            "bootstrap_payload_acquisition_mode",
            "embedded",
            "native-host handoff.startup_smoke");
        foreach (string property in new[]
                 {
                     "matches_release_version",
                     "matches_artifact_file_name",
                     "matches_artifact_digest"
                 })
        {
            RequireJsonBoolean(
                embeddedSmoke,
                property,
                expected: true,
                "native-host handoff.startup_smoke");
        }

        if (byKind.TryGetValue(
                WindowsProofArtifactKind.VisualExitEvidence,
                out WindowsProofInventoryEntry? exitEvidence))
        {
            using JsonDocument gate = ReadEvidence(
                files[exitEvidence.RelativePath],
                "Windows visual exit evidence");
            JsonElement gateRoot = gate.RootElement;
            string? contract = TryGetString(gateRoot, "contractName")
                               ?? TryGetString(gateRoot, "contract_name");
            if (contract != "chummer6-ui.windows_desktop_exit_gate")
            {
                throw new InvalidDataException("Windows visual exit evidence contract is invalid.");
            }

            RequireJsonString(gateRoot, "status", "failed", "visual exit evidence");
            string? blockingMode = TryGetString(gateRoot, "blockingMode")
                                   ?? TryGetString(gateRoot, "blocking_mode");
            if (blockingMode != "external_only")
            {
                throw new InvalidDataException("Windows visual exit evidence must use external_only blocking mode.");
            }
        }
    }

    private static void ValidateBuildProvenanceDocuments(
        WindowsProofManifest manifest,
        IReadOnlyDictionary<string, string> files,
        IReadOnlyDictionary<WindowsProofArtifactKind, WindowsProofInventoryEntry> byKind,
        WindowsProofInventoryEntry installer)
    {
        string filesRoot = Path.GetDirectoryName(files[installer.RelativePath])
            ?? throw new InvalidDataException("Windows proof installer directory is invalid.");
        string bundleRoot = Directory.GetParent(filesRoot)?.FullName
            ?? throw new InvalidDataException("Windows proof bundle root is invalid.");
        var canonicalManifest = new JsonObject
        {
            ["artifacts"] = new JsonArray
            {
                new JsonObject
                {
                    ["artifactId"] = installer.ArtifactId,
                    ["platform"] = "windows",
                    ["head"] = installer.Head,
                    ["fileName"] = installer.FileName,
                    ["sha256"] = installer.Sha256,
                    ["sizeBytes"] = installer.Size
                }
            }
        };
        global::Chummer.Run.Api.Services.ReleaseBuildProvenanceValidator.Validate(
            canonicalManifest,
            filesRoot,
            Path.Combine(bundleRoot, "proof"));

        WindowsProofInventoryEntry provenanceRow =
            byKind[WindowsProofArtifactKind.BuildProvenanceReceipt];
        WindowsProofInventoryEntry sbomRow = byKind[WindowsProofArtifactKind.Sbom];
        using JsonDocument provenance = ReadEvidence(
            files[provenanceRow.RelativePath],
            "Windows build provenance receipt");
        JsonElement root = provenance.RootElement;
        RequireJsonString(
            root,
            "contract_name",
            "chummer6.build_provenance.v1",
            "build provenance receipt");
        RequireJsonString(root, "receipt_kind", "invocation", "build provenance receipt");
        RequireJsonString(root, "status", "pass", "build provenance receipt");
        RequireJsonString(
            root,
            "builder_id",
            "chummer-windows-release-bootstrap",
            "build provenance receipt");
        RequireJsonString(
            root,
            "build_type",
            "windows-desktop-release",
            "build provenance receipt");
        RequireJsonString(
            root,
            "release_version",
            manifest.CandidateVersion,
            "build provenance receipt");
        DateTimeOffset buildStartedAt = RequireJsonUtcDateTimeOffset(
            root,
            "build_started_at_utc",
            "build provenance receipt");
        _ = RequireJsonUtcDateTimeOffset(
            root,
            "generated_at_utc",
            "build provenance receipt");
        if (manifest.GeneratedAt is null || manifest.GeneratedAt.Value < buildStartedAt)
        {
            throw new InvalidDataException(
                "Windows proof manifest.generatedAt must not predate its bound build invocation.");
        }
        string invocationId = RequireJsonPortableId(
            root,
            "invocation_id",
            "build provenance receipt");
        JsonElement failures = RequireJsonArray(root, "failures", "build provenance receipt");
        if (failures.GetArrayLength() != 0)
        {
            throw new InvalidDataException("build provenance receipt.failures must be empty.");
        }

        JsonElement invocation = RequireJsonObject(root, "invocation", "build provenance receipt");
        RequireJsonBoolean(
            invocation,
            "subject_declared_before_build",
            expected: true,
            "build provenance receipt.invocation");
        RequireJsonBoolean(
            invocation,
            "source_identity_stable",
            expected: true,
            "build provenance receipt.invocation");
        RequireJsonSha256(
            invocation,
            "state_sha256",
            "build provenance receipt.invocation");
        JsonElement state = RequireJsonObject(
            invocation,
            "state",
            "build provenance receipt.invocation");
        RequireJsonString(
            state,
            "state_contract_name",
            "chummer6.build_provenance_invocation_state.v1",
            "build provenance receipt.invocation.state");
        RequireJsonString(
            state,
            "builder_id",
            "chummer-windows-release-bootstrap",
            "build provenance receipt.invocation.state");
        RequireJsonString(
            state,
            "build_type",
            "windows-desktop-release",
            "build provenance receipt.invocation.state");
        RequireJsonString(
            state,
            "invocation_id",
            invocationId,
            "build provenance receipt.invocation.state");

        JsonElement source = RequireJsonObject(
            state,
            "source",
            "build provenance receipt.invocation.state");
        string sourceRepository = RequireJsonPortableId(
            source,
            "repository",
            "build provenance receipt.invocation.state.source");
        string sourceCommit = RequireJsonGitObjectId(
            source,
            "commit",
            "build provenance receipt.invocation.state.source");
        string sourceTree = RequireJsonGitObjectId(
            source,
            "tree",
            "build provenance receipt.invocation.state.source");
        RequireJsonBoolean(
            source,
            "tracked_worktree_dirty",
            expected: false,
            "build provenance receipt.invocation.state.source");

        JsonElement sourceMaterials = RequireJsonArray(
            state,
            "source_materials",
            "build provenance receipt.invocation.state");
        if (sourceMaterials.GetArrayLength() == 0)
        {
            throw new InvalidDataException(
                "build provenance receipt.invocation.state.source_materials must not be empty.");
        }
        foreach (JsonElement material in sourceMaterials.EnumerateArray())
        {
            if (material.ValueKind != JsonValueKind.Object)
            {
                throw new InvalidDataException(
                    "build provenance source material rows must be objects.");
            }
            _ = RequireJsonPortableId(material, "repository", "build provenance source material");
            _ = RequireJsonGitObjectId(material, "commit", "build provenance source material");
            _ = RequireJsonGitObjectId(material, "tree", "build provenance source material");
            RequireJsonBoolean(
                material,
                "tracked_worktree_dirty",
                expected: false,
                "build provenance source material");
        }

        JsonElement buildInputs = RequireJsonArray(
            state,
            "build_inputs",
            "build provenance receipt.invocation.state");
        if (buildInputs.GetArrayLength() == 0)
        {
            throw new InvalidDataException(
                "build provenance receipt.invocation.state.build_inputs must not be empty.");
        }
        foreach (JsonElement input in buildInputs.EnumerateArray())
        {
            if (input.ValueKind != JsonValueKind.Object)
            {
                throw new InvalidDataException("build provenance input rows must be objects.");
            }
            _ = RequireJsonPortableId(input, "label", "build provenance input");
            RequireJsonSha256(input, "sha256", "build provenance input");
        }

        JsonElement tools = RequireJsonObject(
            state,
            "build_tools",
            "build provenance receipt.invocation.state");
        RequireJsonSha256(
            tools,
            "provenance_generator_sha256",
            "build provenance receipt.invocation.state.build_tools");
        RequireJsonSha256(
            tools,
            "supply_chain_verifier_sha256",
            "build provenance receipt.invocation.state.build_tools");

        string expectedTargetId = $"desktop-{installer.Head}";
        JsonElement declaration = RequireJsonObject(
            state,
            "subject_declaration",
            "build provenance receipt.invocation.state");
        RequireJsonString(
            declaration,
            "artifact_id",
            installer.ArtifactId,
            "build provenance subject declaration");
        RequireJsonString(
            declaration,
            "artifact_kind",
            "desktop_download",
            "build provenance subject declaration");
        RequireJsonString(
            declaration,
            "artifact_name",
            installer.FileName,
            "build provenance subject declaration");
        RequireJsonString(
            declaration,
            "artifact_binding_type",
            "file",
            "build provenance subject declaration");
        RequireJsonString(
            declaration,
            "target_id",
            expectedTargetId,
            "build provenance subject declaration");
        JsonElement prebuild = RequireJsonObject(
            declaration,
            "prebuild",
            "build provenance subject declaration");
        RequireJsonBoolean(
            prebuild,
            "exists",
            expected: false,
            "build provenance subject declaration.prebuild");

        JsonElement stateSbom = RequireJsonObject(
            state,
            "sbom",
            "build provenance receipt.invocation.state");
        RequireDigestJson(
            stateSbom,
            "sha256",
            sbomRow.Sha256,
            "build provenance receipt.invocation.state.sbom");

        JsonElement subjects = RequireJsonArray(root, "subjects", "build provenance receipt");
        if (subjects.GetArrayLength() != 1
            || subjects[0].ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException(
                "Windows build provenance must bind exactly one installer subject.");
        }

        JsonElement subject = subjects[0];
        RequireJsonString(subject, "artifact_id", installer.ArtifactId, "build provenance subject");
        RequireJsonString(subject, "artifact_kind", "desktop_download", "build provenance subject");
        RequireJsonString(subject, "artifact_name", installer.FileName, "build provenance subject");
        RequireJsonString(
            subject,
            "release_version",
            manifest.CandidateVersion,
            "build provenance subject");
        RequireDigestJson(subject, "artifact_sha256", installer.Sha256, "build provenance subject");
        RequireJsonInt64(subject, "artifact_size_bytes", installer.Size, "build provenance subject");
        RequireJsonString(subject, "target_id", expectedTargetId, "build provenance subject");
        RequireJsonString(
            subject,
            "source_repository",
            sourceRepository,
            "build provenance subject");
        RequireJsonString(subject, "source_commit", sourceCommit, "build provenance subject");
        RequireJsonString(subject, "source_tree", sourceTree, "build provenance subject");
        RequireJsonBoolean(
            subject,
            "source_tracked_worktree_dirty",
            expected: false,
            "build provenance subject");
        RequireDigestJson(subject, "sbom_sha256", sbomRow.Sha256, "build provenance subject");
        RequireJsonString(subject, "invocation_id", invocationId, "build provenance subject");
        RequireJsonBoolean(
            subject,
            "produced_during_invocation",
            expected: true,
            "build provenance subject");

        using JsonDocument sbom = ReadEvidence(
            files[sbomRow.RelativePath],
            "Windows CycloneDX SBOM",
            MaximumSbomBytes);
        JsonElement sbomRoot = sbom.RootElement;
        RequireJsonString(sbomRoot, "bomFormat", "CycloneDX", "Windows CycloneDX SBOM");
        RequireJsonString(sbomRoot, "specVersion", "1.5", "Windows CycloneDX SBOM");
        if (!sbomRoot.TryGetProperty("version", out JsonElement sbomVersion)
            || !sbomVersion.TryGetInt32(out int version)
            || version < 1)
        {
            throw new InvalidDataException("Windows CycloneDX SBOM.version must be a positive integer.");
        }
        JsonElement metadata = RequireJsonObject(sbomRoot, "metadata", "Windows CycloneDX SBOM");
        JsonElement component = RequireJsonObject(
            metadata,
            "component",
            "Windows CycloneDX SBOM.metadata");
        RequireJsonString(component, "type", "application", "Windows CycloneDX SBOM component");
        RequireJsonString(component, "name", expectedTargetId, "Windows CycloneDX SBOM component");
        RequireJsonString(
            component,
            "version",
            manifest.CandidateVersion,
            "Windows CycloneDX SBOM component");
        _ = RequireJsonArray(sbomRoot, "components", "Windows CycloneDX SBOM");
        _ = RequireJsonArray(sbomRoot, "dependencies", "Windows CycloneDX SBOM");
    }

    private static void ValidateEmbeddedInstallerMetadata(
        string installerPath,
        WindowsProofInventoryEntry installer,
        WindowsProofInventoryEntry payload,
        string expectedPayloadUrl)
    {
        var info = new FileInfo(installerPath);
        int tailLength = checked((int)Math.Min(info.Length, MaximumEmbeddedMetadataTrailerBytes));
        byte[] tail = new byte[tailLength];
        using (var stream = new FileStream(
                   installerPath,
                   FileMode.Open,
                   FileAccess.Read,
                   FileShare.Read,
                   bufferSize: 4096,
                   FileOptions.SequentialScan))
        {
            stream.Seek(-tailLength, SeekOrigin.End);
            stream.ReadExactly(tail);
        }

        string expectedTrailer =
            "\nCHUMMER6_BOOTSTRAP_METADATA\n"
            + $"payloadFileName={payload.FileName}\n"
            + $"payloadDownloadUrl={expectedPayloadUrl}\n"
            + $"payloadSha256={payload.Sha256}\n"
            + $"payloadSizeBytes={payload.Size}\n"
            + "payloadAcquisitionMode=embedded\n";
        string observedTail = Encoding.UTF8.GetString(tail);
        if (!observedTail.EndsWith(expectedTrailer, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                $"Windows proof installer '{installer.RelativePath}' must end with the exact embedded-payload metadata trailer.");
        }
    }

    private static JsonDocument ReadEvidence(
        string path,
        string label,
        int maximumBytes = MaximumEvidenceBytes)
    {
        byte[] bytes = ReadBoundedFile(path, maximumBytes, label);
        try
        {
            JsonDocument document = JsonDocument.Parse(
                bytes,
                new JsonDocumentOptions { MaxDepth = 64 });
            RejectDuplicateProperties(document.RootElement, label);
            if (document.RootElement.ValueKind != JsonValueKind.Object)
            {
                document.Dispose();
                throw new InvalidDataException($"{label} must be a JSON object.");
            }

            return document;
        }
        catch (InvalidDataException)
        {
            throw;
        }
        catch (JsonException ex)
        {
            throw new InvalidDataException($"{label} is invalid JSON.", ex);
        }
    }

    internal static IReadOnlyList<string> EnumerateRegularFilesWithoutLinks(string root)
    {
        var result = new List<string>();
        var pending = new Stack<string>();
        pending.Push(Path.GetFullPath(root));
        while (pending.Count > 0)
        {
            string directory = pending.Pop();
            EnsureDirectoryWithoutLinks(directory, "Windows proof directory");
            foreach (string entry in Directory.EnumerateFileSystemEntries(directory))
            {
                FileAttributes attributes;
                try
                {
                    attributes = File.GetAttributes(entry);
                }
                catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
                {
                    throw new InvalidDataException("Windows proof filesystem entry could not be inspected.", ex);
                }

                if ((attributes & FileAttributes.ReparsePoint) != 0
                    || new FileInfo(entry).LinkTarget is not null
                    || new DirectoryInfo(entry).LinkTarget is not null)
                {
                    throw new InvalidDataException("Windows proof trees must not contain symbolic links or reparse points.");
                }

                if ((attributes & FileAttributes.Directory) != 0)
                {
                    pending.Push(entry);
                }
                else
                {
                    result.Add(entry);
                }
            }
        }

        return result;
    }

    internal static string ResolveContainedPath(string root, string relativePath)
    {
        ValidatePortableRelativePath(relativePath, nameof(relativePath));
        string fullRoot = Path.GetFullPath(root);
        string fullPath = Path.GetFullPath(
            Path.Combine(fullRoot, relativePath.Replace('/', Path.DirectorySeparatorChar)));
        string prefix = fullRoot.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
        StringComparison comparison = OperatingSystem.IsWindows()
            ? StringComparison.OrdinalIgnoreCase
            : StringComparison.Ordinal;
        if (!fullPath.StartsWith(prefix, comparison))
        {
            throw new InvalidDataException("Windows proof path escapes its configured root.");
        }

        return fullPath;
    }

    internal static void EnsureRegularFileWithoutLinks(string path, string root, string label)
    {
        string fullRoot = Path.GetFullPath(root);
        string fullPath = Path.GetFullPath(path);
        string relative = Path.GetRelativePath(fullRoot, fullPath);
        if (relative.StartsWith("..", StringComparison.Ordinal)
            || Path.IsPathFullyQualified(relative))
        {
            throw new InvalidDataException($"{label} escapes its configured root.");
        }

        string current = fullRoot;
        foreach (string segment in relative.Split(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar))
        {
            current = Path.Combine(current, segment);
            FileAttributes attributes;
            try
            {
                attributes = File.GetAttributes(current);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            {
                throw new InvalidDataException($"{label} is missing or inaccessible.", ex);
            }

            if ((attributes & FileAttributes.ReparsePoint) != 0)
            {
                throw new InvalidDataException($"{label} must not traverse symbolic links or reparse points.");
            }
        }

        FileAttributes finalAttributes = File.GetAttributes(fullPath);
        if ((finalAttributes & FileAttributes.Directory) != 0 || !File.Exists(fullPath))
        {
            throw new InvalidDataException($"{label} must be a regular file.");
        }
    }

    internal static string ComputeSha256(string path)
    {
        using var stream = new FileStream(
            path,
            FileMode.Open,
            FileAccess.Read,
            FileShare.Read,
            1024 * 1024,
            FileOptions.SequentialScan);
        return Convert.ToHexStringLower(SHA256.HashData(stream));
    }

    internal static bool FixedTimeHexEquals(string left, string right)
        => Sha256Pattern.IsMatch(left)
           && Sha256Pattern.IsMatch(right)
           && CryptographicOperations.FixedTimeEquals(
               Convert.FromHexString(left),
               Convert.FromHexString(right));

    internal static void RequireSha256(string? value, string field)
    {
        if (value is null || !Sha256Pattern.IsMatch(value))
        {
            throw new InvalidDataException($"Windows proof {field} must be a bare lowercase SHA-256 digest.");
        }
    }

    internal static void RequirePortableId(string? value, string field)
    {
        if (value is null
            || !PortableIdPattern.IsMatch(value)
            || value is "." or ".."
            || value.Contains("..", StringComparison.Ordinal))
        {
            throw new InvalidDataException($"Windows proof {field} is not a portable identifier.");
        }
    }

    private static void ValidatePortableRelativePath(string? value, string field)
    {
        if (string.IsNullOrWhiteSpace(value)
            || value.StartsWith("/", StringComparison.Ordinal)
            || value.EndsWith("/", StringComparison.Ordinal)
            || value.Contains('\\')
            || value.Contains(':')
            || Path.IsPathFullyQualified(value))
        {
            throw new InvalidDataException($"Windows proof {field} is not a portable relative path.");
        }

        string[] segments = value.Split('/');
        if (segments.Length is < 2 or > 16
            || segments.Any(segment => !PortableSegmentPattern.IsMatch(segment)
                                       || segment is "." or ".."))
        {
            throw new InvalidDataException($"Windows proof {field} is not a portable relative path.");
        }
    }

    private static void ValidatePortableFileName(string? value, string field)
    {
        if (value is null
            || !PortableSegmentPattern.IsMatch(value)
            || value is "." or "..")
        {
            throw new InvalidDataException($"Windows proof {field} is not a portable filename.");
        }
    }

    private static void EnsureDirectoryWithoutLinks(string path, string label)
    {
        if (!Directory.Exists(path))
        {
            throw new InvalidDataException($"{label} does not exist.");
        }

        FileAttributes attributes = File.GetAttributes(path);
        if ((attributes & FileAttributes.ReparsePoint) != 0
            || (attributes & FileAttributes.Directory) == 0
            || new DirectoryInfo(path).LinkTarget is not null)
        {
            throw new InvalidDataException($"{label} must be a non-symlink directory.");
        }
    }

    private static void EnsureNoCaseCollisions(IEnumerable<string> relativePaths)
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (string path in relativePaths)
        {
            if (!seen.Add(path))
            {
                throw new InvalidDataException(
                    "Windows proof source contains a portable case-insensitive path collision.");
            }
        }
    }

    private static string ToRelativePath(string root, string path)
        => Path.GetRelativePath(root, path).Replace(Path.DirectorySeparatorChar, '/');

    private static byte[] ReadBoundedFile(string path, int maximumBytes, string label)
    {
        var info = new FileInfo(path);
        if (!info.Exists || info.Length <= 0 || info.Length > maximumBytes)
        {
            throw new InvalidDataException($"{label} size is invalid.");
        }

        byte[] bytes = File.ReadAllBytes(path);
        if (bytes.LongLength != info.Length)
        {
            throw new InvalidDataException($"{label} changed while it was read.");
        }

        return bytes;
    }

    private static void RejectDuplicateProperties(JsonElement element, string label)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (JsonProperty property in element.EnumerateObject())
            {
                if (!names.Add(property.Name))
                {
                    throw new InvalidDataException(
                        $"{label} contains duplicate or case-colliding JSON property '{property.Name}'.");
                }

                RejectDuplicateProperties(property.Value, label);
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement child in element.EnumerateArray())
            {
                RejectDuplicateProperties(child, label);
            }
        }
    }

    private static JsonElement RequireJsonObject(JsonElement root, string property, string label)
    {
        if (!root.TryGetProperty(property, out JsonElement value)
            || value.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException($"{label}.{property} must be an object.");
        }

        return value;
    }

    private static JsonElement RequireJsonArray(JsonElement root, string property, string label)
    {
        if (!root.TryGetProperty(property, out JsonElement value)
            || value.ValueKind != JsonValueKind.Array)
        {
            throw new InvalidDataException($"{label}.{property} must be an array.");
        }

        return value;
    }

    private static void RequireJsonString(
        JsonElement root,
        string property,
        string expected,
        string label)
    {
        string? value = TryGetString(root, property);
        if (!string.Equals(value, expected, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{label}.{property} must equal '{expected}'.");
        }
    }

    private static void RequireJsonBoolean(
        JsonElement root,
        string property,
        bool expected,
        string label)
    {
        if (!root.TryGetProperty(property, out JsonElement value)
            || value.ValueKind is not (JsonValueKind.True or JsonValueKind.False)
            || value.GetBoolean() != expected)
        {
            throw new InvalidDataException($"{label}.{property} must equal {expected.ToString().ToLowerInvariant()}.");
        }
    }

    private static void RequireJsonInt64(
        JsonElement root,
        string property,
        long expected,
        string label)
    {
        if (!root.TryGetProperty(property, out JsonElement value)
            || !value.TryGetInt64(out long actual)
            || actual != expected)
        {
            throw new InvalidDataException($"{label}.{property} does not match the bound file size.");
        }
    }

    private static string RequireJsonPortableId(
        JsonElement root,
        string property,
        string label)
    {
        string? value = TryGetString(root, property);
        if (value is null
            || !PortableIdPattern.IsMatch(value)
            || value is "." or ".."
            || value.Contains("..", StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{label}.{property} must be a portable identifier.");
        }

        return value;
    }

    private static string RequireJsonGitObjectId(
        JsonElement root,
        string property,
        string label)
    {
        string? value = TryGetString(root, property);
        if (value is null || !GitObjectIdPattern.IsMatch(value))
        {
            throw new InvalidDataException(
                $"{label}.{property} must be a lowercase 40-character Git object id.");
        }

        return value;
    }

    private static DateTimeOffset RequireJsonUtcDateTimeOffset(
        JsonElement root,
        string property,
        string label)
    {
        string? raw = TryGetString(root, property);
        if (raw is null
            || !DateTimeOffset.TryParse(
                raw,
                CultureInfo.InvariantCulture,
                DateTimeStyles.RoundtripKind,
                out DateTimeOffset value)
            || value.Offset != TimeSpan.Zero)
        {
            throw new InvalidDataException($"{label}.{property} must be a UTC timestamp.");
        }

        return value;
    }

    private static DateTimeOffset RequireUtcZuluJsonTimestamp(
        JsonElement root,
        string property,
        string label)
    {
        string? raw = TryGetString(root, property);
        if (raw is null || !raw.EndsWith('Z'))
        {
            throw new InvalidDataException(
                $"{label}.{property} must be an RFC 3339 UTC timestamp ending in Z.");
        }

        return RequireJsonUtcDateTimeOffset(root, property, label);
    }

    private static void RequireJsonSha256(
        JsonElement root,
        string property,
        string label)
    {
        string? value = TryGetString(root, property);
        if (value is null || !Sha256Pattern.IsMatch(value))
        {
            throw new InvalidDataException(
                $"{label}.{property} must be a bare lowercase SHA-256 digest.");
        }
    }

    private static void RequireDigestJson(
        JsonElement root,
        string property,
        string expected,
        string label)
    {
        string? raw = TryGetString(root, property);
        string normalized = raw?.StartsWith("sha256:", StringComparison.Ordinal) == true
            ? raw["sha256:".Length..]
            : raw ?? string.Empty;
        if (!FixedTimeHexEquals(normalized, expected))
        {
            throw new InvalidDataException($"{label}.{property} does not match the bound file SHA-256.");
        }
    }

    private static string? TryGetString(JsonElement root, string property)
        => root.TryGetProperty(property, out JsonElement value)
           && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;

    private static void RequireExact(string? actual, string expected, string field)
    {
        if (!string.Equals(actual, expected, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"Windows proof {field} must equal '{expected}'.");
        }
    }

    private static JsonSerializerOptions CreateJsonOptions()
    {
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web)
        {
            PropertyNameCaseInsensitive = false,
            UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
            MaxDepth = 32
        };
        options.Converters.Add(new JsonStringEnumConverter(
            JsonNamingPolicy.SnakeCaseLower,
            allowIntegerValues: false));
        return options;
    }
}

public sealed record WindowsProofValidatedSource(
    string SourceRoot,
    WindowsProofManifest Manifest,
    byte[] ManifestBytes,
    string ManifestSha256,
    IReadOnlyDictionary<string, string> ArtifactFiles);
