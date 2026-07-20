using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Chummer.Run.Api.Services;

public sealed record ReleaseUploadCandidateIdentity(
    string Version,
    string CanonicalManifestSha256,
    string InventorySha256,
    int FileCount,
    long TotalBytes,
    string BundleIdentitySha256);

public sealed record ReleaseUploadCandidateInventoryRow(
    string Path,
    long SizeBytes,
    string Sha256);

public sealed record ReleaseUploadCandidateSessionBinding(
    string SnapshotSha256,
    string AuthoritySha256,
    string BundleIdentitySha256,
    string CanonicalManifestSha256,
    string InventorySha256);

public sealed record ReleaseUploadCandidateAuthority(
    string SnapshotId,
    string SnapshotSha256,
    string AuthoritySha256,
    DateTimeOffset ExpiresAtUtc,
    ReleaseUploadCandidateIdentity Candidate,
    byte[] CanonicalManifestBytes,
    IReadOnlyList<ReleaseUploadCandidateInventoryRow> Inventory)
{
    public ReleaseUploadCandidateSessionBinding SessionBinding => new(
        SnapshotSha256,
        AuthoritySha256,
        Candidate.BundleIdentitySha256,
        Candidate.CanonicalManifestSha256,
        Candidate.InventorySha256);
}

public sealed record ReleaseUploadSnapshotAuthority(
    bool IsConfigured,
    bool IsValid,
    string? FailureReason,
    string? SnapshotId,
    string? SnapshotSha256,
    bool ReleaseUploadAuthority,
    bool CandidateImportAuthority,
    ReleaseUploadCandidateAuthority? Candidate)
{
    internal static ReleaseUploadSnapshotAuthority Unconfigured()
        => new(false, false, null, null, null, false, false, null);

    internal static ReleaseUploadSnapshotAuthority Invalid(string reason)
        => new(true, false, reason, null, null, false, false, null);
}

/// <summary>
/// Authenticates the exact CURRENT posture used by release-upload admission.
/// A bearer credential proves caller identity only; this service proves policy.
/// </summary>
public sealed class ReleaseUploadSnapshotAuthorityService
{
    public const string CandidateAuthorityFileName =
        "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.generated.json";

    private const string CurrentFileName = "CURRENT.json";
    private const string ManifestFileName = "PUBLIC_PROJECTION_SNAPSHOT.generated.json";
    private const string CurrentContractName = "chummer.public_projection_current/v1";
    private const string SnapshotContractName = "chummer.public_projection_snapshot/v1";
    private const string CandidateContractName =
        "chummer.release-upload.candidate-import-authority/v1";
    private const string CandidateInventoryContractName =
        "chummer.release-upload.candidate-inventory/v1";
    private const int MaximumPointerBytes = 256 * 1024;
    private const int MaximumManifestBytes = 2 * 1024 * 1024;
    private const int MaximumCandidateAuthorityBytes = 32 * 1024 * 1024;
    private static readonly Regex Sha256Pattern = new(
        "^[0-9a-f]{64}$",
        RegexOptions.CultureInvariant);
    private static readonly Regex SnapshotIdPattern = new(
        "^public-projection-[0-9a-f]{64}$",
        RegexOptions.CultureInvariant);
    private static readonly Regex VersionPattern = new(
        "^[A-Za-z0-9][A-Za-z0-9._+-]{0,159}$",
        RegexOptions.CultureInvariant);
    private static readonly string[] BaseOutputNames =
    [
        "HUB_LOCAL_RELEASE_PROOF.generated.json",
        "HUB_SERVED_RELEASE_PROOF.generated.json",
        "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json",
        "NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json",
        "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json",
        "RELEASE_CHANNEL.generated.json",
        "FLAGSHIP_PRODUCT_READINESS.generated.json"
    ];
    private static readonly string[] CandidateOutputNames =
        [.. BaseOutputNames, CandidateAuthorityFileName];
    private static readonly HashSet<string> RequiredEvidencePaths = new(
        [
            "WINDOWS_NATIVE_CAPTURE.generated.json",
            "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json",
            "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json",
            "WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json",
            "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json",
            "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json",
            "startup-smoke/startup-smoke-avalonia-win-x64.receipt.json",
            "startup-smoke/startup-smoke-blazor-desktop-win-x64.receipt.json"
        ],
        StringComparer.Ordinal);

    private readonly IConfiguration _configuration;

    public ReleaseUploadSnapshotAuthorityService(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public ReleaseUploadSnapshotAuthority Load()
    {
        SnapshotRootResolution rootResolution = ResolveSnapshotRoot();
        if (!rootResolution.IsConfigured)
        {
            return ReleaseUploadSnapshotAuthority.Unconfigured();
        }
        if (string.IsNullOrWhiteSpace(rootResolution.Path))
        {
            return ReleaseUploadSnapshotAuthority.Invalid(
                "current public projection snapshot is unavailable");
        }

        try
        {
            string root = Path.GetFullPath(rootResolution.Path);
            using PublicProjectionDescriptorReader reader =
                PublicProjectionDescriptorReader.Open(root);
            byte[] pointerBytes = reader.ReadRootFile(
                CurrentFileName,
                MaximumPointerBytes,
                "release upload CURRENT pointer");
            using JsonDocument pointerDocument = ParseStrictObject(
                pointerBytes,
                "release upload CURRENT pointer");
            JsonElement pointer = pointerDocument.RootElement;
            RequireExactString(pointer, "contractName", CurrentContractName);
            AuthorityPosture posture = ParsePosture(pointer);
            string snapshotId = RequireString(pointer, "snapshotId");
            string snapshotSha256 = RequireSha256(pointer, "snapshotSha256");
            string manifestSha256 = RequireSha256(pointer, "manifestSha256");
            if (!SnapshotIdPattern.IsMatch(snapshotId)
                || !string.Equals(
                    snapshotId,
                    $"public-projection-{snapshotSha256}",
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException("release upload CURRENT digest binding drifted");
            }
            RequireExactString(
                pointer,
                "manifestRelativePath",
                $"{snapshotId}/{ManifestFileName}");
            string[] outputNames = posture.CandidateImportAuthority
                ? CandidateOutputNames
                : BaseOutputNames;
            ValidatePointerOutputs(pointer, snapshotId, outputNames);

            using PublicProjectionDescriptorReader.PublicProjectionDescriptorDirectory snapshot =
                reader.OpenDirectory(snapshotId, "release upload CURRENT snapshot");
            byte[] manifestBytes = snapshot.ReadFile(
                ManifestFileName,
                MaximumManifestBytes,
                "release upload CURRENT manifest");
            RequireDigest(manifestBytes, manifestSha256, "release upload CURRENT manifest");
            using JsonDocument manifestDocument = ParseStrictObject(
                manifestBytes,
                "release upload CURRENT manifest");
            JsonElement manifest = manifestDocument.RootElement;
            RequireExactString(manifest, "contractName", SnapshotContractName);
            RequireExactString(manifest, "status", posture.Status);
            AuthorityPosture manifestPosture = ParsePosture(manifest);
            if (manifestPosture != posture)
            {
                throw new InvalidDataException("release upload CURRENT authority posture drifted");
            }
            RequireExactString(manifest, "snapshotId", snapshotId);
            RequireExactString(manifest, "snapshotSha256", snapshotSha256);

            JsonElement outputs = RequireObject(manifest, "outputs");
            if (!ExactPropertySet(outputs, new HashSet<string>(outputNames, StringComparer.Ordinal)))
            {
                throw new InvalidDataException("release upload CURRENT output inventory drifted");
            }
            var outputDigests = new Dictionary<string, string>(StringComparer.Ordinal);
            var outputSizes = new Dictionary<string, long>(StringComparer.Ordinal);
            foreach (string name in outputNames)
            {
                JsonElement entry = RequireObject(outputs, name);
                RequireExactString(entry, "relativePath", name);
                outputDigests[name] = RequireSha256(entry, "sha256");
                outputSizes[name] = RequireNonNegativeInt64(entry, "sizeBytes");
            }
            if (!string.Equals(
                    ComputeSnapshotDigest(outputDigests, outputNames),
                    snapshotSha256,
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException("release upload CURRENT aggregate digest drifted");
            }
            if (!string.Equals(
                    outputDigests[BaseOutputNames[0]],
                    outputDigests[BaseOutputNames[1]],
                    StringComparison.Ordinal)
                || outputSizes[BaseOutputNames[0]] != outputSizes[BaseOutputNames[1]])
            {
                throw new InvalidDataException("release upload CURRENT Hub proofs disagree");
            }

            ReleaseUploadCandidateAuthority? candidate = null;
            if (posture.CandidateImportAuthority)
            {
                byte[] authorityBytes = snapshot.ReadFile(
                    CandidateAuthorityFileName,
                    MaximumCandidateAuthorityBytes,
                    "candidate import authority");
                if (authorityBytes.LongLength != outputSizes[CandidateAuthorityFileName])
                {
                    throw new InvalidDataException("candidate import authority size drifted");
                }
                RequireDigest(
                    authorityBytes,
                    outputDigests[CandidateAuthorityFileName],
                    "candidate import authority");
                candidate = ParseCandidateAuthority(
                    snapshotId,
                    snapshotSha256,
                    outputDigests[CandidateAuthorityFileName],
                    authorityBytes);
            }

            byte[] pointerAfter = reader.ReadRootFile(
                CurrentFileName,
                MaximumPointerBytes,
                "release upload CURRENT pointer");
            if (!CryptographicOperations.FixedTimeEquals(pointerBytes, pointerAfter))
            {
                throw new InvalidDataException("release upload CURRENT advanced during authentication");
            }
            snapshot.VerifyPathIdentity();
            reader.VerifyRootPathIdentity();
            return new ReleaseUploadSnapshotAuthority(
                true,
                true,
                null,
                snapshotId,
                snapshotSha256,
                posture.ReleaseUploadAuthority,
                posture.CandidateImportAuthority,
                candidate);
        }
        catch (Exception exception) when (exception is InvalidDataException
                                          or IOException
                                          or UnauthorizedAccessException
                                          or JsonException
                                          or NotSupportedException
                                          or ArgumentException
                                          or CryptographicException
                                          or FormatException)
        {
            return ReleaseUploadSnapshotAuthority.Invalid(
                "current public projection snapshot failed release-upload authentication");
        }
    }

    private static AuthorityPosture ParsePosture(JsonElement value)
    {
        string status = RequireString(value, "status");
        AuthorityPosture posture = status switch
        {
            "pass" => new(status, "release_upload_ready", true, true, false),
            "review_required" => new(
                status,
                "code_deploy_review_required",
                true,
                false,
                false),
            "candidate_import_ready" => new(
                status,
                "candidate_import_ready",
                false,
                false,
                true),
            _ => throw new InvalidDataException("release upload CURRENT status is invalid")
        };
        RequireExactString(value, "projectionStage", posture.Stage);
        RequireBoolean(value, "codeDeploymentAuthority", posture.CodeDeploymentAuthority);
        RequireBoolean(value, "releaseUploadAuthority", posture.ReleaseUploadAuthority);
        RequireBoolean(value, "candidateImportAuthority", posture.CandidateImportAuthority);
        ValidateGateFindings(value, posture.Status);
        return posture;
    }

    private static void ValidateGateFindings(JsonElement parent, string status)
    {
        if (!parent.TryGetProperty("releaseGateFindings", out JsonElement findings)
            || findings.ValueKind != JsonValueKind.Array)
        {
            throw new InvalidDataException("release upload CURRENT gate findings are invalid");
        }
        if (status == "pass")
        {
            if (findings.GetArrayLength() != 0)
            {
                throw new InvalidDataException("release upload CURRENT pass records blockers");
            }
            return;
        }
        if (status == "candidate_import_ready")
        {
            if (findings.GetArrayLength() != 1)
            {
                throw new InvalidDataException("candidate import live-verification blocker drifted");
            }
            JsonElement finding = findings[0];
            RequireExactString(
                finding,
                "gate",
                "live release convergence after candidate import");
            RequireExactString(finding, "status", "postdeploy_required");
            RequireExactString(
                finding,
                "reason",
                "candidate bytes require live verification before release upload authority can be restored");
            return;
        }
        if (findings.GetArrayLength() == 0)
        {
            throw new InvalidDataException("review-required CURRENT omits release blockers");
        }
    }

    private static ReleaseUploadCandidateAuthority ParseCandidateAuthority(
        string snapshotId,
        string snapshotSha256,
        string authoritySha256,
        byte[] payload)
    {
        using JsonDocument document = ParseStrictObject(payload, "candidate import authority");
        JsonElement root = document.RootElement;
        RequireExactString(root, "contractName", CandidateContractName);
        RequireExactInt32(root, "contractVersion", 1);
        RequireExactString(root, "status", "candidate_import_ready");
        DateTimeOffset generatedAt = RequireUtcTimestamp(root, "generatedAtUtc");
        DateTimeOffset expiresAt = RequireUtcTimestamp(root, "expiresAtUtc");
        DateTimeOffset now = DateTimeOffset.UtcNow;
        if (generatedAt > now.AddMinutes(5)
            || expiresAt <= now
            || expiresAt > now.AddHours(6).AddMinutes(5))
        {
            throw new InvalidDataException("candidate import authority is expired or future-dated");
        }

        JsonElement candidateElement = RequireObject(root, "candidate");
        string version = RequireString(candidateElement, "version");
        if (!VersionPattern.IsMatch(version))
        {
            throw new InvalidDataException("candidate import version is invalid");
        }
        var candidate = new ReleaseUploadCandidateIdentity(
            version,
            RequireSha256(candidateElement, "canonicalManifestSha256"),
            RequireSha256(candidateElement, "inventorySha256"),
            RequirePositiveInt32(candidateElement, "fileCount"),
            RequireNonNegativeInt64(candidateElement, "totalBytes"),
            RequireSha256(candidateElement, "bundleIdentitySha256"));
        if (!string.Equals(
                ComputeBundleIdentity(candidate),
                candidate.BundleIdentitySha256,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException("candidate bundle identity drifted");
        }

        JsonElement custody = RequireObject(root, "custody");
        byte[] canonicalManifest = DecodeEmbedded(
            RequireObject(custody, "canonicalManifest"),
            "candidate canonical manifest");
        if (!string.Equals(
                Sha256(canonicalManifest),
                candidate.CanonicalManifestSha256,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException("candidate canonical manifest custody drifted");
        }
        byte[] inventoryBytes = DecodeEmbedded(
            RequireObject(custody, "inventory"),
            "candidate upload inventory");
        IReadOnlyList<ReleaseUploadCandidateInventoryRow> inventory =
            ParseCandidateInventory(inventoryBytes);
        if (inventory.Count != candidate.FileCount
            || inventory.Sum(static row => row.SizeBytes) != candidate.TotalBytes
            || !string.Equals(
                ComputeInventoryDigest(inventory),
                candidate.InventorySha256,
                StringComparison.Ordinal)
            || !inventory.Any(row =>
                string.Equals(
                    row.Path,
                    "RELEASE_CHANNEL.generated.json",
                    StringComparison.Ordinal)
                && string.Equals(
                    row.Sha256,
                    candidate.CanonicalManifestSha256,
                    StringComparison.Ordinal)))
        {
            throw new InvalidDataException("candidate upload inventory summary drifted");
        }

        JsonElement native = RequireObject(custody, "nativeWindowsFinalizedEvidence");
        RequireExactString(native, "status", "passed");
        string reviewer = RequireString(native, "reviewer");
        JsonElement captureSource = RequireObject(native, "captureSource");
        JsonElement finalizationSource = RequireObject(native, "finalizationSource");
        RequireExactString(captureSource, "actor", "github-actions[bot]");
        RequireExactString(
            captureSource,
            "workflow",
            ".github/workflows/windows-native-evidence-capture.yml");
        RequireExactString(finalizationSource, "actor", reviewer);
        RequireExactString(
            finalizationSource,
            "workflow",
            ".github/workflows/windows-native-evidence-finalize.yml");
        if (!native.TryGetProperty("files", out JsonElement files)
            || files.ValueKind != JsonValueKind.Array
            || files.GetArrayLength() < RequiredEvidencePaths.Count)
        {
            throw new InvalidDataException("candidate native-Windows custody is incomplete");
        }
        var paths = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonElement entry in files.EnumerateArray())
        {
            string path = RequireString(entry, "path");
            if (!paths.Add(path))
            {
                throw new InvalidDataException("candidate native-Windows custody path is duplicated");
            }
            byte[] evidenceBytes = DecodeEmbedded(entry, $"candidate native-Windows {path}");
            using JsonDocument _ = ParseStrictObject(
                evidenceBytes,
                $"candidate native-Windows {path}");
        }
        if (!RequiredEvidencePaths.IsSubsetOf(paths))
        {
            throw new InvalidDataException("candidate native-Windows custody is incomplete");
        }

        return new ReleaseUploadCandidateAuthority(
            snapshotId,
            snapshotSha256,
            authoritySha256,
            expiresAt,
            candidate,
            canonicalManifest,
            inventory);
    }

    private static IReadOnlyList<ReleaseUploadCandidateInventoryRow> ParseCandidateInventory(
        byte[] payload)
    {
        using JsonDocument document = ParseStrictObject(payload, "candidate upload inventory");
        JsonElement root = document.RootElement;
        RequireExactString(root, "contractName", CandidateInventoryContractName);
        RequireExactInt32(root, "contractVersion", 1);
        if (!root.TryGetProperty("files", out JsonElement files)
            || files.ValueKind != JsonValueKind.Array
            || files.GetArrayLength() == 0)
        {
            throw new InvalidDataException("candidate upload inventory is empty");
        }
        var rows = new List<ReleaseUploadCandidateInventoryRow>();
        string? previous = null;
        foreach (JsonElement row in files.EnumerateArray())
        {
            string path = RequireString(row, "path");
            if (!IsCanonicalRelativePath(path)
                || previous is not null
                   && string.CompareOrdinal(previous, path) >= 0)
            {
                throw new InvalidDataException("candidate upload inventory path drifted");
            }
            rows.Add(new ReleaseUploadCandidateInventoryRow(
                path,
                RequireNonNegativeInt64(row, "sizeBytes"),
                RequireSha256(row, "sha256")));
            previous = path;
        }
        return rows;
    }

    private static byte[] DecodeEmbedded(JsonElement entry, string label)
    {
        string sha256 = RequireSha256(entry, "sha256");
        long size = RequireNonNegativeInt64(entry, "sizeBytes");
        string encoded = RequireString(entry, "base64");
        byte[] bytes;
        try
        {
            bytes = Convert.FromBase64String(encoded);
        }
        catch (FormatException ex)
        {
            throw new InvalidDataException($"{label} base64 is invalid", ex);
        }
        if (bytes.LongLength != size || !string.Equals(Sha256(bytes), sha256, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{label} embedded bytes drifted");
        }
        return bytes;
    }

    internal static string ComputeInventoryDigest(
        IEnumerable<ReleaseUploadCandidateInventoryRow> rows)
    {
        using IncrementalHash digest = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        foreach (ReleaseUploadCandidateInventoryRow row in rows)
        {
            byte[] path = Encoding.UTF8.GetBytes(row.Path);
            digest.AppendData(ToBigEndian(path.LongLength));
            digest.AppendData(path);
            digest.AppendData(ToBigEndian(row.SizeBytes));
            digest.AppendData(Convert.FromHexString(row.Sha256));
        }
        return Convert.ToHexStringLower(digest.GetHashAndReset());
    }

    internal static string ComputeBundleIdentity(ReleaseUploadCandidateIdentity candidate)
    {
        string material =
            $"{{\"canonicalManifestSha256\":\"{candidate.CanonicalManifestSha256}\"," +
            $"\"fileCount\":{candidate.FileCount}," +
            $"\"inventorySha256\":\"{candidate.InventorySha256}\"," +
            $"\"totalBytes\":{candidate.TotalBytes}," +
            $"\"version\":\"{candidate.Version}\"}}";
        return Sha256(Encoding.UTF8.GetBytes(material));
    }

    private SnapshotRootResolution ResolveSnapshotRoot()
    {
        if (_configuration[PublicProjectionSnapshotService.SnapshotRootConfigurationKey]?.Trim()
            is { Length: > 0 } configured)
        {
            return new SnapshotRootResolution(true, configured);
        }
        bool required = ParseBoolean(
            _configuration[PublicProjectionSnapshotService.SnapshotRequiredConfigurationKey]);
        string relative = Path.Combine(".codex-studio", "published");
        string? canonRoot = _configuration["CHUMMER_PUBLIC_CANON_ROOT"]?.Trim();
        string? discovered = new[]
            {
                !string.IsNullOrWhiteSpace(canonRoot) ? Path.Combine(canonRoot, relative) : null,
                Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), relative)),
                Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "..", relative)),
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, relative)),
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", relative))
            }
            .Where(static candidate => !string.IsNullOrWhiteSpace(candidate))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault(static candidate => File.Exists(Path.Combine(candidate!, CurrentFileName)));
        return discovered is not null
            ? new SnapshotRootResolution(true, discovered)
            : new SnapshotRootResolution(required, null);
    }

    private static JsonDocument ParseStrictObject(byte[] payload, string label)
    {
        JsonDocument document = JsonDocument.Parse(
            payload,
            new JsonDocumentOptions
            {
                AllowTrailingCommas = false,
                CommentHandling = JsonCommentHandling.Disallow,
                MaxDepth = 48
            });
        if (document.RootElement.ValueKind != JsonValueKind.Object
            || !HasUniqueProperties(document.RootElement))
        {
            document.Dispose();
            throw new InvalidDataException($"{label} is not a strict JSON object");
        }
        return document;
    }

    private static bool HasUniqueProperties(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.Ordinal);
            return value.EnumerateObject().All(property =>
                names.Add(property.Name) && HasUniqueProperties(property.Value));
        }
        return value.ValueKind != JsonValueKind.Array
               || value.EnumerateArray().All(HasUniqueProperties);
    }

    private static void ValidatePointerOutputs(
        JsonElement pointer,
        string snapshotId,
        IReadOnlyCollection<string> outputNames)
    {
        JsonElement outputs = RequireObject(pointer, "outputs");
        var expected = new HashSet<string>(outputNames, StringComparer.Ordinal);
        if (!ExactPropertySet(outputs, expected))
        {
            throw new InvalidDataException("release upload CURRENT pointer inventory drifted");
        }
        foreach (string name in outputNames)
        {
            RequireExactString(outputs, name, $"{snapshotId}/{name}");
        }
    }

    private static string ComputeSnapshotDigest(
        IReadOnlyDictionary<string, string> digests,
        IEnumerable<string> outputNames)
    {
        using IncrementalHash digest = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        foreach (string name in outputNames)
        {
            digest.AppendData(Encoding.UTF8.GetBytes(name));
            digest.AppendData([0]);
            digest.AppendData(Encoding.ASCII.GetBytes(digests[name]));
            digest.AppendData([(byte)'\n']);
        }
        return Convert.ToHexStringLower(digest.GetHashAndReset());
    }

    private static byte[] ToBigEndian(long value)
    {
        byte[] bytes = BitConverter.GetBytes(value);
        if (BitConverter.IsLittleEndian)
        {
            Array.Reverse(bytes);
        }
        return bytes;
    }

    private static bool IsCanonicalRelativePath(string value)
        => value.Length > 0
           && !value.StartsWith("/", StringComparison.Ordinal)
           && !value.Contains('\\')
           && value.Split('/').All(static segment =>
               segment.Length > 0 && segment is not "." and not ".." && !segment.Contains(':'));

    private static void RequireDigest(byte[] payload, string expected, string label)
    {
        if (!CryptographicOperations.FixedTimeEquals(
            SHA256.HashData(payload),
            Convert.FromHexString(expected)))
        {
            throw new InvalidDataException($"{label} digest drifted");
        }
    }

    private static string Sha256(byte[] payload)
        => Convert.ToHexStringLower(SHA256.HashData(payload));

    private static JsonElement RequireObject(JsonElement parent, string property)
        => parent.TryGetProperty(property, out JsonElement value)
           && value.ValueKind == JsonValueKind.Object
            ? value
            : throw new InvalidDataException($"release upload {property} is invalid");

    private static string RequireString(JsonElement parent, string property)
        => parent.TryGetProperty(property, out JsonElement value)
           && value.ValueKind == JsonValueKind.String
           && value.GetString() is { Length: > 0 } text
            ? text
            : throw new InvalidDataException($"release upload {property} is invalid");

    private static string RequireSha256(JsonElement parent, string property)
    {
        string value = RequireString(parent, property);
        return Sha256Pattern.IsMatch(value)
            ? value
            : throw new InvalidDataException($"release upload {property} is invalid");
    }

    private static long RequireNonNegativeInt64(JsonElement parent, string property)
        => parent.TryGetProperty(property, out JsonElement value)
           && value.ValueKind == JsonValueKind.Number
           && value.TryGetInt64(out long parsed)
           && parsed >= 0
            ? parsed
            : throw new InvalidDataException($"release upload {property} is invalid");

    private static int RequirePositiveInt32(JsonElement parent, string property)
        => parent.TryGetProperty(property, out JsonElement value)
           && value.ValueKind == JsonValueKind.Number
           && value.TryGetInt32(out int parsed)
           && parsed > 0
            ? parsed
            : throw new InvalidDataException($"release upload {property} is invalid");

    private static void RequireExactInt32(JsonElement parent, string property, int expected)
    {
        if (!parent.TryGetProperty(property, out JsonElement value)
            || !value.TryGetInt32(out int parsed)
            || parsed != expected)
        {
            throw new InvalidDataException($"release upload {property} drifted");
        }
    }

    private static DateTimeOffset RequireUtcTimestamp(JsonElement parent, string property)
    {
        if (!DateTimeOffset.TryParse(
                RequireString(parent, property),
                System.Globalization.CultureInfo.InvariantCulture,
                System.Globalization.DateTimeStyles.RoundtripKind,
                out DateTimeOffset parsed)
            || parsed.Offset != TimeSpan.Zero)
        {
            throw new InvalidDataException($"release upload {property} is invalid");
        }
        return parsed;
    }

    private static void RequireExactString(JsonElement parent, string property, string expected)
    {
        if (!string.Equals(RequireString(parent, property), expected, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"release upload {property} drifted");
        }
    }

    private static void RequireBoolean(JsonElement parent, string property, bool expected)
    {
        if (!parent.TryGetProperty(property, out JsonElement value)
            || value.ValueKind is not JsonValueKind.True and not JsonValueKind.False
            || value.GetBoolean() != expected)
        {
            throw new InvalidDataException($"release upload {property} drifted");
        }
    }

    private static bool ExactPropertySet(JsonElement value, IReadOnlySet<string> expected)
    {
        string[] actual = value.EnumerateObject().Select(static property => property.Name).ToArray();
        return actual.Length == expected.Count && actual.All(expected.Contains);
    }

    private static bool ParseBoolean(string? value)
        => value?.Trim().ToLowerInvariant() is "1" or "true" or "yes" or "on";

    private sealed record AuthorityPosture(
        string Status,
        string Stage,
        bool CodeDeploymentAuthority,
        bool ReleaseUploadAuthority,
        bool CandidateImportAuthority);

    private sealed record SnapshotRootResolution(bool IsConfigured, string? Path);
}

public static class ReleaseUploadCandidateBundleValidator
{
    public static void Validate(
        string bundleRoot,
        ReleaseUploadCandidateAuthority authority)
    {
        ArgumentNullException.ThrowIfNull(authority);
        string root = Path.GetFullPath(bundleRoot);
        if (!Directory.Exists(root)
            || (File.GetAttributes(root) & FileAttributes.ReparsePoint) != 0)
        {
            throw new InvalidDataException("candidate upload bundle root is invalid");
        }
        var rows = new List<ReleaseUploadCandidateInventoryRow>();
        foreach (string path in Directory.EnumerateFiles(root, "*", SearchOption.AllDirectories))
        {
            if ((File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0)
            {
                throw new InvalidDataException("candidate upload bundle contains a forbidden link");
            }
            string relative = Path.GetRelativePath(root, path).Replace('\\', '/');
            FileInfo before = new(path);
            string sha256;
            using (FileStream stream = new(path, FileMode.Open, FileAccess.Read, FileShare.Read))
            {
                sha256 = Convert.ToHexStringLower(SHA256.HashData(stream));
            }
            FileInfo after = new(path);
            if (before.Length != after.Length || before.LastWriteTimeUtc != after.LastWriteTimeUtc)
            {
                throw new InvalidDataException("candidate upload bundle changed during validation");
            }
            rows.Add(new ReleaseUploadCandidateInventoryRow(relative, after.Length, sha256));
        }
        rows.Sort(static (left, right) => string.CompareOrdinal(left.Path, right.Path));
        if (!rows.SequenceEqual(authority.Inventory)
            || rows.Count != authority.Candidate.FileCount
            || rows.Sum(static row => row.SizeBytes) != authority.Candidate.TotalBytes
            || !string.Equals(
                ReleaseUploadSnapshotAuthorityService.ComputeInventoryDigest(rows),
                authority.Candidate.InventorySha256,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "staged upload files do not match the exact candidate authority inventory");
        }
        string canonicalPath = Path.Combine(root, "RELEASE_CHANNEL.generated.json");
        byte[] canonical = File.ReadAllBytes(canonicalPath);
        if (!CryptographicOperations.FixedTimeEquals(
            canonical,
            authority.CanonicalManifestBytes))
        {
            throw new InvalidDataException(
                "staged canonical manifest bytes do not match candidate authority custody");
        }
        if (!string.Equals(
                ReleaseUploadSnapshotAuthorityService.ComputeBundleIdentity(authority.Candidate),
                authority.Candidate.BundleIdentitySha256,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException("staged candidate bundle identity drifted");
        }
    }
}
