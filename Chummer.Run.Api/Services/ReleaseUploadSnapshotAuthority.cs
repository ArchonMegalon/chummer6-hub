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
    public const string CandidateExactIncomingDesktopScope =
        "avalonia:windows:win-x64";

    private const string CurrentFileName = "CURRENT.json";
    private const string ManifestFileName = "PUBLIC_PROJECTION_SNAPSHOT.generated.json";
    private const string CurrentContractName = "chummer.public_projection_current/v1";
    private const string SnapshotContractName = "chummer.public_projection_snapshot/v1";
    private const string CandidateContractName =
        "chummer.release-upload.candidate-import-authority/v2";
    private const string UnsignedCandidateContractName =
        "chummer.release-upload.candidate-import-authority/v3";
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
    private static readonly Regex HeadPattern = new(
        "^[a-z0-9][a-z0-9-]{0,63}$",
        RegexOptions.CultureInvariant);
    private static readonly Regex CommitPattern = new(
        "^[0-9a-f]{40}$",
        RegexOptions.CultureInvariant);
    private static readonly Regex ReviewerPattern = new(
        "^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,38})$",
        RegexOptions.CultureInvariant);
    private static readonly Regex GitHubLoginPattern = new(
        "^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?|github-actions\\[bot\\])$",
        RegexOptions.CultureInvariant);
    private static readonly Regex PositiveIntegerPattern = new(
        "^[1-9][0-9]*$",
        RegexOptions.CultureInvariant);
    private static readonly Regex GitHubTimestampPattern = new(
        "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$",
        RegexOptions.CultureInvariant);
    private static readonly Regex ExportRunnerLabelPattern = new(
        "^chummer-preview-nightly-export-[a-z0-9]{12,64}$",
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
    private const string CaptureFileName = "WINDOWS_NATIVE_CAPTURE.generated.json";
    private const string CaptureInventoryFileName =
        "WINDOWS_NATIVE_CAPTURE_INVENTORY.generated.json";
    private const string FinalizationFileName =
        "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json";
    private const string FinalizedInventoryFileName =
        "WINDOWS_NATIVE_FINALIZED_INVENTORY.generated.json";
    private const string CandidateProvenanceInventoryFileName =
        "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json";
    private const string CandidateProvenanceExportFileName =
        "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json";
    private const string CandidateUploadContentInventoryFileName =
        "PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json";
    private const string CandidateUploadExportFileName =
        "PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json";
    private const string CaptureWorkflow =
        ".github/workflows/windows-native-evidence-capture.yml";
    private const string FinalizationWorkflow =
        ".github/workflows/windows-native-evidence-finalize.yml";
    private const string ProducerWorkflow =
        ".github/workflows/preview-nightly-candidate-export.yml";
    private const string UiRepository = "ArchonMegalon/chummer6-ui";
    private const string UiRef = "refs/heads/main";
    private const string WindowsRid = "win-x64";
    private static readonly string[] PromotedHeads = ["avalonia"];
    private static readonly TimeSpan MaximumNativeProofAge = TimeSpan.FromHours(24);

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
        if (root.TryGetProperty("contractName", out JsonElement contractName)
            && contractName.ValueKind == JsonValueKind.String
            && string.Equals(
                contractName.GetString(),
                UnsignedCandidateContractName,
                StringComparison.Ordinal))
        {
            return ParseUnsignedCandidateAuthority(
                snapshotId,
                snapshotSha256,
                authoritySha256,
                root);
        }
        if (!ExactPropertySet(
                root,
                new HashSet<string>(
                    [
                        "contractName",
                        "contractVersion",
                        "status",
                        "candidateImportAuthority",
                        "candidateReviewAuthority",
                        "publicationEligible",
                        "releaseUploadAuthority",
                        "deployAuthority",
                        "routeAuthority",
                        "exactIncomingDesktopScope",
                        "generatedAtUtc",
                        "expiresAtUtc",
                        "candidate",
                        "custody"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException("candidate import authority property set drifted");
        }
        RequireExactString(root, "contractName", CandidateContractName);
        RequireExactInt32(root, "contractVersion", 2);
        RequireExactString(root, "status", "candidate_import_ready");
        RequireBoolean(root, "candidateImportAuthority", expected: true);
        RequireBoolean(root, "candidateReviewAuthority", expected: true);
        RequireBoolean(root, "publicationEligible", expected: false);
        RequireBoolean(root, "releaseUploadAuthority", expected: false);
        RequireBoolean(root, "deployAuthority", expected: false);
        RequireBoolean(root, "routeAuthority", expected: false);
        RequireExactString(
            root,
            "exactIncomingDesktopScope",
            CandidateExactIncomingDesktopScope);
        DateTimeOffset generatedAt = RequireUtcTimestamp(root, "generatedAtUtc");
        DateTimeOffset expiresAt = RequireUtcTimestamp(root, "expiresAtUtc");
        DateTimeOffset now = DateTimeOffset.UtcNow;
        if (generatedAt > now.AddMinutes(5)
            || generatedAt < now.AddHours(-6).AddMinutes(-5)
            || expiresAt <= now
            || expiresAt > now.AddHours(6).AddMinutes(5)
            || expiresAt <= generatedAt
            || expiresAt > generatedAt.AddHours(6))
        {
            throw new InvalidDataException("candidate import authority is expired or future-dated");
        }

        JsonElement candidateElement = RequireObject(root, "candidate");
        if (!ExactPropertySet(
                candidateElement,
                new HashSet<string>(
                    [
                        "version",
                        "canonicalManifestSha256",
                        "inventorySha256",
                        "fileCount",
                        "totalBytes",
                        "bundleIdentitySha256"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException("candidate import identity property set drifted");
        }
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
        if (!ExactPropertySet(
                custody,
                new HashSet<string>(
                    [
                        "canonicalManifest",
                        "compatibilityManifest",
                        "inventory",
                        "nativeWindowsFinalizedEvidence",
                        "finalizedPublicationEvidence",
                        "registryPrepareCandidateReceipt",
                        "registryFinalizeAuthority",
                        "registryFinalizeReceipt",
                        "registryFinalization"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException("candidate import custody property set drifted");
        }
        byte[] canonicalManifest = DecodeEmbedded(
            RequireObject(custody, "canonicalManifest"),
            "candidate canonical manifest",
            "RELEASE_CHANNEL.generated.json");
        if (!string.Equals(
                Sha256(canonicalManifest),
                candidate.CanonicalManifestSha256,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException("candidate canonical manifest custody drifted");
        }
        byte[] compatibilityManifest = DecodeEmbedded(
            RequireObject(custody, "compatibilityManifest"),
            "candidate compatibility manifest",
            "releases.json");
        using JsonDocument compatibilityDocument = ParseStrictObject(
            compatibilityManifest,
            "candidate compatibility release manifest");
        byte[] inventoryBytes = DecodeEmbedded(
            RequireObject(custody, "inventory"),
            "candidate upload inventory",
            "CANDIDATE_UPLOAD_INVENTORY.generated.json");
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
                    StringComparison.Ordinal))
            || !inventory.Any(row =>
                string.Equals(row.Path, "releases.json", StringComparison.Ordinal)
                && string.Equals(
                    row.Sha256,
                    Sha256(compatibilityManifest),
                    StringComparison.Ordinal)
                && row.SizeBytes == compatibilityManifest.LongLength))
        {
            throw new InvalidDataException("candidate upload inventory summary drifted");
        }

        using JsonDocument canonicalDocument = ParseStrictObject(
            canonicalManifest,
            "candidate canonical release manifest");
        CandidateNativePackage nativePackage = ValidateCandidateNativeEvidence(
            RequireObject(custody, "nativeWindowsFinalizedEvidence"),
            canonicalDocument.RootElement,
            candidate,
            inventory,
            now);
        ValidateFinalizedPublicationAndRegistry(
            custody,
            canonicalDocument.RootElement,
            canonicalManifest,
            compatibilityManifest,
            candidate,
            inventory,
            nativePackage);

        return new ReleaseUploadCandidateAuthority(
            snapshotId,
            snapshotSha256,
            authoritySha256,
            expiresAt,
            candidate,
            canonicalManifest,
            inventory);
    }

    private static ReleaseUploadCandidateAuthority ParseUnsignedCandidateAuthority(
        string snapshotId,
        string snapshotSha256,
        string authoritySha256,
        JsonElement root)
    {
        if (!ExactPropertySet(
                root,
                new HashSet<string>(
                    [
                        "candidate",
                        "candidateImportAuthority",
                        "candidateReviewAuthority",
                        "codeDeploymentAuthority",
                        "contractName",
                        "contractVersion",
                        "crossRunBitReproducible",
                        "custody",
                        "deployAuthority",
                        "exactIncomingDesktopScope",
                        "expiresAtUtc",
                        "generatedAtUtc",
                        "platformScope",
                        "publicationAuthorized",
                        "publicationEligible",
                        "releaseUploadAuthority",
                        "routeAuthority",
                        "signaturePolicy",
                        "status"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned candidate import authority property set drifted");
        }
        RequireExactString(root, "contractName", UnsignedCandidateContractName);
        RequireExactInt32(root, "contractVersion", 3);
        RequireExactString(root, "status", "candidate_import_ready");
        RequireBoolean(root, "candidateImportAuthority", expected: true);
        RequireBoolean(root, "candidateReviewAuthority", expected: true);
        RequireBoolean(root, "publicationAuthorized", expected: false);
        RequireBoolean(root, "publicationEligible", expected: false);
        RequireBoolean(root, "releaseUploadAuthority", expected: false);
        RequireBoolean(root, "deployAuthority", expected: false);
        RequireBoolean(root, "routeAuthority", expected: false);
        RequireBoolean(root, "codeDeploymentAuthority", expected: false);
        RequireBoolean(root, "crossRunBitReproducible", expected: false);
        RequireExactString(root, "platformScope", "windows_only");
        RequireExactString(
            root,
            "exactIncomingDesktopScope",
            CandidateExactIncomingDesktopScope);
        ValidateUnsignedSignaturePolicy(RequireObject(root, "signaturePolicy"));

        DateTimeOffset generatedAt = RequireUtcTimestamp(root, "generatedAtUtc");
        DateTimeOffset expiresAt = RequireUtcTimestamp(root, "expiresAtUtc");
        DateTimeOffset now = DateTimeOffset.UtcNow;
        if (generatedAt > now.AddMinutes(5)
            || generatedAt < now.AddHours(-6).AddMinutes(-5)
            || expiresAt <= now
            || expiresAt > now.AddHours(6).AddMinutes(5)
            || expiresAt <= generatedAt
            || expiresAt > generatedAt.AddHours(6))
        {
            throw new InvalidDataException(
                "unsigned candidate import authority is expired or future-dated");
        }

        JsonElement candidateElement = RequireObject(root, "candidate");
        if (!ExactPropertySet(
                candidateElement,
                new HashSet<string>(
                    [
                        "version",
                        "canonicalManifestSha256",
                        "inventorySha256",
                        "fileCount",
                        "totalBytes",
                        "bundleIdentitySha256"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException("unsigned candidate identity property set drifted");
        }
        string version = RequireString(candidateElement, "version");
        if (!VersionPattern.IsMatch(version))
        {
            throw new InvalidDataException("unsigned candidate version is invalid");
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
            throw new InvalidDataException("unsigned candidate bundle identity drifted");
        }

        JsonElement custody = RequireObject(root, "custody");
        if (!ExactPropertySet(
                custody,
                new HashSet<string>(
                    [
                        "canonicalManifest",
                        "compatibilityManifest",
                        "inventory",
                        "registryFinalization",
                        "registryFinalizeAuthority",
                        "registryFinalizeReceipt",
                        "registryPrepareCandidateReceipt",
                        "unsignedPublicationEvidence"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException("unsigned candidate custody property set drifted");
        }
        byte[] canonicalManifest = DecodeEmbedded(
            RequireObject(custody, "canonicalManifest"),
            "unsigned candidate canonical manifest",
            "RELEASE_CHANNEL.generated.json");
        if (!string.Equals(
                Sha256(canonicalManifest),
                candidate.CanonicalManifestSha256,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException("unsigned candidate canonical custody drifted");
        }
        byte[] compatibilityManifest = DecodeEmbedded(
            RequireObject(custody, "compatibilityManifest"),
            "unsigned candidate compatibility manifest",
            "releases.json");
        using JsonDocument compatibilityDocument = ParseStrictObject(
            compatibilityManifest,
            "unsigned candidate compatibility manifest");
        byte[] inventoryBytes = DecodeEmbedded(
            RequireObject(custody, "inventory"),
            "unsigned candidate upload inventory",
            "CANDIDATE_UPLOAD_INVENTORY.generated.json");
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
                    StringComparison.Ordinal)
                && row.SizeBytes == canonicalManifest.LongLength)
            || !inventory.Any(row =>
                string.Equals(row.Path, "releases.json", StringComparison.Ordinal)
                && string.Equals(
                    row.Sha256,
                    Sha256(compatibilityManifest),
                    StringComparison.Ordinal)
                && row.SizeBytes == compatibilityManifest.LongLength))
        {
            throw new InvalidDataException("unsigned candidate inventory summary drifted");
        }

        using JsonDocument canonicalDocument = ParseStrictObject(
            canonicalManifest,
            "unsigned candidate canonical manifest");
        ValidateUnsignedManifestIdentity(
            canonicalDocument.RootElement,
            candidate.Version,
            "unsigned candidate canonical manifest");
        ValidateUnsignedManifestIdentity(
            compatibilityDocument.RootElement,
            candidate.Version,
            "unsigned candidate compatibility manifest");
        ValidateUnsignedPublicationAndRegistry(
            custody,
            canonicalDocument.RootElement,
            canonicalManifest,
            compatibilityManifest,
            candidate,
            inventory);
        return new ReleaseUploadCandidateAuthority(
            snapshotId,
            snapshotSha256,
            authoritySha256,
            expiresAt,
            candidate,
            canonicalManifest,
            inventory);
    }

    private static void ValidateUnsignedSignaturePolicy(JsonElement policy)
    {
        if (!ExactPropertySet(
                policy,
                new HashSet<string>(
                    ["signatureStatus", "signingRequired", "unsignedReason"],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException("unsigned candidate signature policy drifted");
        }
        RequireExactString(policy, "signatureStatus", "unsigned");
        RequireBoolean(policy, "signingRequired", expected: false);
        RequireExactString(policy, "unsignedReason", "preview_policy");
    }

    private static void ValidateUnsignedPublicationAndRegistry(
        JsonElement custody,
        JsonElement canonical,
        byte[] canonicalBytes,
        byte[] compatibilityBytes,
        ReleaseUploadCandidateIdentity candidate,
        IReadOnlyList<ReleaseUploadCandidateInventoryRow> inventory)
    {
        JsonElement evidence = RequireObject(custody, "unsignedPublicationEvidence");
        if (!ExactPropertySet(
                evidence,
                new HashSet<string>(
                    [
                        "crossRunBitReproducible",
                        "exactIncomingDesktopScope",
                        "files",
                        "freshDeltaSha256",
                        "fullShelfInventorySha256",
                        "incumbentInventorySha256",
                        "platformScope",
                        "provenance",
                        "publicationScopeSha256",
                        "retainedInventorySha256",
                        "signaturePolicy",
                        "sourceSha",
                        "status"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException("unsigned publication evidence property set drifted");
        }
        RequireExactString(evidence, "status", "passed");
        RequireExactString(
            evidence,
            "exactIncomingDesktopScope",
            CandidateExactIncomingDesktopScope);
        RequireExactString(evidence, "platformScope", "windows_only");
        RequireBoolean(evidence, "crossRunBitReproducible", expected: false);
        ValidateUnsignedSignaturePolicy(RequireObject(evidence, "signaturePolicy"));
        string sourceSha = RequireString(evidence, "sourceSha");
        if (!CommitPattern.IsMatch(sourceSha))
        {
            throw new InvalidDataException("unsigned publication source revision drifted");
        }
        _ = RequireSha256(evidence, "publicationScopeSha256");
        _ = RequireSha256(evidence, "incumbentInventorySha256");
        _ = RequireSha256(evidence, "fullShelfInventorySha256");
        _ = RequireSha256(evidence, "retainedInventorySha256");
        _ = RequireSha256(evidence, "freshDeltaSha256");

        var documents = new Dictionary<string, CandidateEvidenceDocument>(
            StringComparer.Ordinal);
        try
        {
            foreach (JsonElement entry in RequireArray(evidence, "files").EnumerateArray())
            {
                string path = RequireString(entry, "path");
                if (!IsCanonicalRelativePath(path) || documents.ContainsKey(path))
                {
                    throw new InvalidDataException("unsigned publication evidence path drifted");
                }
                byte[] bytes = DecodeEmbedded(entry, $"unsigned publication {path}", path);
                documents.Add(
                    path,
                    new CandidateEvidenceDocument(
                        ParseStrictObject(bytes, $"unsigned publication {path}"),
                        bytes,
                        RequireSha256(entry, "sha256"),
                        RequireNonNegativeInt64(entry, "sizeBytes")));
            }
            const string scopePath = "PREVIEW_NIGHTLY_UNSIGNED_SCOPE.proposed.json";
            const string packageLockPath = "provenance/config/package-plane.lock.json";
            const string packageReceiptPath =
                "provenance/UI_FRESH_PACKAGE_PLANE.generated.json";
            const string retainedManifestPath =
                "provenance/retained-windows-publish-closure/manifest.json";
            const string nativeLockPath =
                "provenance/config/windows-native-bootstrap-toolchain.lock.json";
            var expectedPaths = new HashSet<string>(
                [
                    scopePath,
                    "RELEASE_CHANNEL.generated.json",
                    "releases.json",
                    packageLockPath,
                    packageReceiptPath,
                    retainedManifestPath,
                    nativeLockPath
                ],
                StringComparer.Ordinal);
            if (!expectedPaths.SetEquals(documents.Keys)
                || !CryptographicOperations.FixedTimeEquals(
                    documents["RELEASE_CHANNEL.generated.json"].Bytes,
                    canonicalBytes)
                || !CryptographicOperations.FixedTimeEquals(
                    documents["releases.json"].Bytes,
                    compatibilityBytes))
            {
                throw new InvalidDataException("unsigned publication evidence custody drifted");
            }
            CandidateEvidenceDocument scopeDocument = documents[scopePath];
            RequireExactString(evidence, "publicationScopeSha256", scopeDocument.Sha256);
            JsonElement scope = scopeDocument.Root;
            ValidateUnsignedScope(
                scope,
                sourceSha,
                candidate,
                inventory,
                canonical,
                canonicalBytes,
                compatibilityBytes,
                documents,
                packageLockPath,
                packageReceiptPath,
                retainedManifestPath,
                nativeLockPath);
            ValidateUnsignedRegistry(
                custody,
                scope,
                scopeDocument.Bytes,
                evidence,
                canonical,
                canonicalBytes,
                compatibilityBytes,
                candidate,
                documents,
                packageLockPath,
                packageReceiptPath,
                retainedManifestPath,
                nativeLockPath);
        }
        finally
        {
            foreach (CandidateEvidenceDocument document in documents.Values)
            {
                document.Dispose();
            }
        }
    }

    private static void ValidateUnsignedScope(
        JsonElement scope,
        string sourceSha,
        ReleaseUploadCandidateIdentity candidate,
        IReadOnlyList<ReleaseUploadCandidateInventoryRow> inventory,
        JsonElement canonical,
        byte[] canonicalBytes,
        byte[] compatibilityBytes,
        IReadOnlyDictionary<string, CandidateEvidenceDocument> documents,
        string packageLockPath,
        string packageReceiptPath,
        string retainedManifestPath,
        string nativeLockPath)
    {
        if (!ExactPropertySet(
                scope,
                new HashSet<string>(
                    [
                        "compatibilityManifest",
                        "contractName",
                        "contractVersion",
                        "crossRunBitReproducible",
                        "deployAuthorized",
                        "freshDelta",
                        "fullShelfInventory",
                        "fullShelfInventorySha256",
                        "incumbentInventorySha256",
                        "platformScope",
                        "provenance",
                        "publicationAuthorized",
                        "publicationManifest",
                        "release",
                        "retainedFromIncumbent",
                        "signature",
                        "sourceSha",
                        "status",
                        "uploadAuthorized"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException("unsigned UI scope property set drifted");
        }
        RequireExactString(
            scope,
            "contractName",
            "chummer6-ui.preview-nightly-unsigned-publication-scope");
        RequireExactInt32(scope, "contractVersion", 3);
        RequireExactString(scope, "status", "prepared");
        RequireExactString(scope, "platformScope", "windows_only");
        RequireBoolean(scope, "crossRunBitReproducible", expected: false);
        RequireBoolean(scope, "publicationAuthorized", expected: false);
        RequireBoolean(scope, "uploadAuthorized", expected: false);
        RequireBoolean(scope, "deployAuthorized", expected: false);
        RequireExactString(scope, "sourceSha", sourceSha);
        JsonElement release = RequireObject(scope, "release");
        if (!ExactPropertySet(
                release,
                new HashSet<string>(["channel", "version"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException("unsigned UI release property set drifted");
        }
        RequireExactString(release, "channel", "preview");
        RequireExactString(release, "version", candidate.Version);
        JsonElement signature = RequireObject(scope, "signature");
        if (!ExactPropertySet(
                signature,
                new HashSet<string>(["policy", "required", "status"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException("unsigned UI signature property set drifted");
        }
        RequireExactString(signature, "policy", "preview_policy");
        RequireBoolean(signature, "required", expected: false);
        RequireExactString(signature, "status", "unsigned");
        ValidateUnsignedByteReference(
            RequireObject(scope, "publicationManifest"),
            "RELEASE_CHANNEL.generated.json",
            canonicalBytes,
            "unsigned UI publication manifest");
        ValidateUnsignedByteReference(
            RequireObject(scope, "compatibilityManifest"),
            "releases.json",
            compatibilityBytes,
            "unsigned UI compatibility manifest");

        var inventoryByPath = inventory.ToDictionary(
            static row => row.Path,
            StringComparer.Ordinal);
        JsonElement fullInventory = RequireArray(scope, "fullShelfInventory");
        if (fullInventory.GetArrayLength() != inventory.Count)
        {
            throw new InvalidDataException("unsigned UI full shelf inventory count drifted");
        }
        var modeByPath = new Dictionary<string, int>(StringComparer.Ordinal);
        string? previous = null;
        foreach (JsonElement row in fullInventory.EnumerateArray())
        {
            if (!ExactPropertySet(
                    row,
                    new HashSet<string>(
                        ["mode", "path", "sha256", "sizeBytes"],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException("unsigned UI inventory row drifted");
            }
            string path = RequireString(row, "path");
            long mode = RequireNonNegativeInt64(row, "mode");
            long size = RequireNonNegativeInt64(row, "sizeBytes");
            string digest = RequireSha256(row, "sha256");
            if (!IsCanonicalRelativePath(path)
                || previous is not null && string.CompareOrdinal(previous, path) >= 0
                || mode > 0x1ff
                || !inventoryByPath.TryGetValue(
                    path,
                    out ReleaseUploadCandidateInventoryRow? held)
                || held.SizeBytes != size
                || !string.Equals(held.Sha256, digest, StringComparison.Ordinal))
            {
                throw new InvalidDataException("unsigned UI inventory byte binding drifted");
            }
            modeByPath.Add(path, checked((int)mode));
            previous = path;
        }
        RequireExactString(
            scope,
            "fullShelfInventorySha256",
            UnsignedCompactSha256(fullInventory));
        _ = RequireSha256(scope, "incumbentInventorySha256");

        JsonElement fresh = RequireArray(scope, "freshDelta");
        if (fresh.GetArrayLength() != 2)
        {
            throw new InvalidDataException("unsigned UI fresh delta cardinality drifted");
        }
        string[] roles = ["installer", "bootstrap_payload"];
        string[] names =
        [
            "chummer-avalonia-win-x64-installer.exe",
            "chummer-avalonia-win-x64-payload.zip"
        ];
        var freshPaths = new HashSet<string>(StringComparer.Ordinal);
        for (int index = 0; index < roles.Length; index++)
        {
            JsonElement row = fresh[index];
            if (!ExactPropertySet(
                    row,
                    new HashSet<string>(
                        [
                            "artifactRole",
                            "fileName",
                            "head",
                            "mode",
                            "path",
                            "platform",
                            "rid",
                            "sha256",
                            "sizeBytes"
                        ],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException("unsigned UI fresh delta row drifted");
            }
            RequireExactString(row, "artifactRole", roles[index]);
            RequireExactString(row, "fileName", names[index]);
            RequireExactString(row, "head", "avalonia");
            RequireExactString(row, "platform", "windows");
            RequireExactString(row, "rid", WindowsRid);
            string path = RequireString(row, "path");
            if (!string.Equals(path, $"files/{names[index]}", StringComparison.Ordinal)
                || !freshPaths.Add(path)
                || !inventoryByPath.TryGetValue(
                    path,
                    out ReleaseUploadCandidateInventoryRow? held)
                || RequireNonNegativeInt64(row, "mode") != modeByPath[path]
                || RequireNonNegativeInt64(row, "sizeBytes") != held.SizeBytes
                || !string.Equals(
                    RequireSha256(row, "sha256"),
                    held.Sha256,
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException("unsigned UI fresh delta bytes drifted");
            }
        }
        ValidateUnsignedCanonicalWindows(canonical, inventoryByPath, fresh);

        var expectedPaths = new HashSet<string>(
            ["RELEASE_CHANNEL.generated.json", "releases.json", .. freshPaths],
            StringComparer.Ordinal);
        JsonElement retained = RequireArray(scope, "retainedFromIncumbent");
        previous = null;
        foreach (JsonElement row in retained.EnumerateArray())
        {
            if (!ExactPropertySet(
                    row,
                    new HashSet<string>(
                        ["mode", "path", "retentionKind", "sha256", "sizeBytes"],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException("unsigned UI retained row drifted");
            }
            string path = RequireString(row, "path");
            string kind = RequireString(row, "retentionKind");
            if (!IsCanonicalRelativePath(path)
                || previous is not null && string.CompareOrdinal(previous, path) >= 0
                || !expectedPaths.Add(path)
                || kind is not "managed_artifact" and not "ancillary"
                || !inventoryByPath.TryGetValue(
                    path,
                    out ReleaseUploadCandidateInventoryRow? held)
                || RequireNonNegativeInt64(row, "mode") != modeByPath[path]
                || RequireNonNegativeInt64(row, "sizeBytes") != held.SizeBytes
                || !string.Equals(
                    RequireSha256(row, "sha256"),
                    held.Sha256,
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException("unsigned UI retained bytes drifted");
            }
            previous = path;
        }
        if (!expectedPaths.SetEquals(inventoryByPath.Keys))
        {
            throw new InvalidDataException("unsigned UI retained/fresh partition drifted");
        }

        JsonElement provenance = RequireObject(scope, "provenance");
        var provenancePaths = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["packagePlaneLock"] = packageLockPath,
            ["packagePlaneReceipt"] = packageReceiptPath,
            ["retainedManifest"] = retainedManifestPath,
            ["nativeToolchainLock"] = nativeLockPath
        };
        if (!ExactPropertySet(
                provenance,
                new HashSet<string>(provenancePaths.Keys, StringComparer.Ordinal)))
        {
            throw new InvalidDataException("unsigned UI provenance property set drifted");
        }
        foreach ((string name, string path) in provenancePaths)
        {
            ValidateUnsignedOpaqueBinding(
                RequireObject(provenance, name),
                documents[path].Bytes,
                $"unsigned UI provenance {name}");
        }
        ValidateUnsignedProvenanceSemantics(
            documents,
            sourceSha,
            candidate.Version,
            packageLockPath,
            packageReceiptPath,
            retainedManifestPath,
            nativeLockPath);
    }

    internal static void ValidateUnsignedCanonicalWindows(
        JsonElement canonical,
        IReadOnlyDictionary<string, ReleaseUploadCandidateInventoryRow> inventory,
        JsonElement fresh)
    {
        int windowsCount = 0;
        foreach (JsonElement artifact in RequireArray(canonical, "artifacts").EnumerateArray())
        {
            string platform = RequireString(artifact, "platform");
            string artifactPath = $"files/{RequireString(artifact, "fileName")}";
            if (!inventory.TryGetValue(
                    artifactPath,
                    out ReleaseUploadCandidateInventoryRow? artifactInventory)
                || !string.Equals(
                    RequireSha256(artifact, "sha256"),
                    artifactInventory.Sha256,
                    StringComparison.Ordinal)
                || RequireNonNegativeInt64(artifact, "sizeBytes")
                   != artifactInventory.SizeBytes)
            {
                throw new InvalidDataException("unsigned canonical artifact bytes drifted");
            }
            if (!string.Equals(platform, "windows", StringComparison.Ordinal))
            {
                continue;
            }
            windowsCount++;
            RequireExactString(artifact, "head", "avalonia");
            RequireExactString(artifact, "rid", WindowsRid);
            RequireExactString(artifact, "kind", "installer");
            RequireExactString(artifact, "installerMode", "bootstrap");
            RequireExactString(artifact, "payloadAcquisitionMode", "download");
            string installerPath = artifactPath;
            string payloadPath = $"files/{RequireString(artifact, "payloadFileName")}";
            if (!inventory.TryGetValue(
                    payloadPath,
                    out ReleaseUploadCandidateInventoryRow? payload)
                || !string.Equals(
                    RequireSha256(artifact, "payloadSha256"),
                    payload.Sha256,
                    StringComparison.Ordinal)
                || RequireNonNegativeInt64(artifact, "payloadSizeBytes") != payload.SizeBytes
                || !string.Equals(
                    RequireString(fresh[0], "path"),
                    installerPath,
                    StringComparison.Ordinal)
                || !string.Equals(
                    RequireString(fresh[1], "path"),
                    payloadPath,
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException("unsigned canonical Windows bytes drifted");
            }
        }
        if (windowsCount != 1)
        {
            throw new InvalidDataException("unsigned canonical Windows scope drifted");
        }
    }

    internal static void ValidateUnsignedManifestIdentity(
        JsonElement canonical,
        string version,
        string label)
    {
        string manifestVersion = RequireMatchingAlias(
            canonical,
            "version",
            "releaseVersion",
            $"{label} release version");
        if (!string.Equals(manifestVersion, version, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{label} release version drifted");
        }
        string channel = RequireMatchingAlias(
            canonical,
            "channel",
            "channelId",
            $"{label} release channel");
        if (!string.Equals(channel, "preview", StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{label} release channel drifted");
        }
    }

    private static void ValidateUnsignedByteReference(
        JsonElement reference,
        string path,
        byte[] bytes,
        string label)
    {
        if (!ExactPropertySet(
                reference,
                new HashSet<string>(["path", "sha256", "sizeBytes"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException($"{label} property set drifted");
        }
        RequireExactString(reference, "path", path);
        RequireExactString(reference, "sha256", Sha256(bytes));
        if (RequireNonNegativeInt64(reference, "sizeBytes") != bytes.LongLength)
        {
            throw new InvalidDataException($"{label} size drifted");
        }
    }

    private static void ValidateUnsignedOpaqueBinding(
        JsonElement reference,
        byte[] bytes,
        string label)
    {
        if (!ExactPropertySet(
                reference,
                new HashSet<string>(["sha256", "sizeBytes"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException($"{label} property set drifted");
        }
        RequireExactString(reference, "sha256", Sha256(bytes));
        if (RequireNonNegativeInt64(reference, "sizeBytes") != bytes.LongLength)
        {
            throw new InvalidDataException($"{label} size drifted");
        }
    }

    private static void ValidateUnsignedProvenanceSemantics(
        IReadOnlyDictionary<string, CandidateEvidenceDocument> documents,
        string sourceSha,
        string version,
        string packageLockPath,
        string packageReceiptPath,
        string retainedManifestPath,
        string nativeLockPath)
    {
        JsonElement packageLock = documents[packageLockPath].Root;
        RequireExactString(
            packageLock,
            "contractName",
            "chummer6-ui.fresh-package-plane-lock");
        RequireExactInt32(packageLock, "contractVersion", 8);
        JsonElement approvedSources = RequireArray(packageLock, "approvedPackageSources");
        if (approvedSources.GetArrayLength() != 1
            || !string.Equals(
                approvedSources[0].GetString(),
                "same-run-local-feed",
                StringComparison.Ordinal))
        {
            throw new InvalidDataException("unsigned package-plane source policy drifted");
        }

        JsonElement receipt = documents[packageReceiptPath].Root;
        RequireExactString(
            receipt,
            "contractName",
            "chummer6-ui.fresh-package-plane-verification");
        RequireExactInt32(receipt, "contractVersion", 8);
        RequireExactString(receipt, "status", "passed");
        RequireExactString(receipt, "consumerCommit", sourceSha);
        RequireExactString(receipt, "mode", "integration");
        RequireBoolean(receipt, "localCompatibilityTree", expected: false);
        RequireBoolean(receipt, "packageCacheWasFresh", expected: true);
        RequireBoolean(receipt, "stubPackagesAllowed", expected: false);
        JsonElement packageSources = RequireArray(receipt, "packageSources");
        if (packageSources.GetArrayLength() != 1
            || !string.Equals(
                packageSources[0].GetString(),
                "same-run-local-feed",
                StringComparison.Ordinal))
        {
            throw new InvalidDataException("unsigned package-plane receipt source drifted");
        }
        ValidateUnsignedOpaqueBinding(
            RequireObject(receipt, "consumerPackagePlaneLock"),
            documents[packageLockPath].Bytes,
            "unsigned package receipt lock binding");

        JsonElement retained = documents[retainedManifestPath].Root;
        RequireExactString(
            retained,
            "contractName",
            "chummer6-ui.retained-windows-publish-closure");
        RequireExactInt32(retained, "contractVersion", 2);
        RequireExactString(retained, "status", "passed");
        RequireExactString(retained, "consumerCommit", sourceSha);
        RequireBoolean(retained, "atomicallyRetained", expected: true);
        RequireBoolean(retained, "authoritative", expected: true);
        RequireBoolean(retained, "deterministicRepacking", expected: false);
        JsonElement retainedRelease = RequireObject(retained, "release");
        RequireExactString(retainedRelease, "channel", "preview");
        RequireExactString(retainedRelease, "version", version);
        JsonElement publish = RequireObject(retained, "publish");
        RequireExactString(publish, "status", "passed");
        RequireExactString(publish, "releaseChannel", "preview");
        RequireExactString(publish, "releaseVersion", version);
        RequireBoolean(
            RequireObject(retained, "releaseEligibility"),
            "eligible",
            expected: false);
        ValidateUnsignedOpaqueBinding(
            RequireObject(retained, "packagePlaneLock"),
            documents[packageLockPath].Bytes,
            "unsigned retained manifest lock binding");

        JsonElement pointer = RequireObject(receipt, "retainedWindowsBundle");
        RequireExactString(
            pointer,
            "contractName",
            "chummer6-ui.retained-windows-publish-closure-pointer");
        RequireExactInt32(pointer, "contractVersion", 2);
        RequireExactString(pointer, "status", "passed");
        RequireExactString(pointer, "consumerCommit", sourceSha);
        RequireBoolean(pointer, "atomicallyRetained", expected: true);
        RequireBoolean(pointer, "authority", expected: false);
        RequireBoolean(pointer, "manifestIsAuthoritative", expected: true);
        JsonElement pointerRelease = RequireObject(pointer, "release");
        RequireExactString(pointerRelease, "channel", "preview");
        RequireExactString(pointerRelease, "version", version);
        ValidateUnsignedOpaqueBinding(
            RequireObject(pointer, "manifest"),
            documents[retainedManifestPath].Bytes,
            "unsigned retained pointer manifest binding");

        JsonElement native = documents[nativeLockPath].Root;
        if (!ExactPropertySet(
                native,
                new HashSet<string>(
                    [
                        "container_image",
                        "contract_name",
                        "debian_snapshot",
                        "packages",
                        "platform",
                        "schema_version"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException("unsigned native toolchain property set drifted");
        }
        RequireExactString(
            native,
            "contract_name",
            "chummer6-ui.windows_native_bootstrap_toolchain_lock");
        RequireExactInt32(native, "schema_version", 1);
        JsonElement platform = RequireObject(native, "platform");
        RequireExactString(platform, "os", "linux");
        RequireExactString(platform, "architecture", "amd64");
        JsonElement snapshot = RequireObject(native, "debian_snapshot");
        RequireBoolean(snapshot, "include_recommends", expected: false);
        JsonElement installRoots = RequireArray(snapshot, "install_roots");
        if (installRoots.GetArrayLength() != 2
            || !string.Equals(installRoots[0].GetString(), "nsis", StringComparison.Ordinal)
            || !string.Equals(
                installRoots[1].GetString(),
                "p7zip-full",
                StringComparison.Ordinal))
        {
            throw new InvalidDataException("unsigned native toolchain roots drifted");
        }
        JsonElement packages = RequireArray(native, "packages");
        if (packages.GetArrayLength() == 0)
        {
            throw new InvalidDataException("unsigned native toolchain package set is empty");
        }
        foreach (JsonElement package in packages.EnumerateArray())
        {
            _ = RequireSha256(package, "sha256");
            _ = RequirePositiveInt64(package, "size");
            _ = RequireString(package, "name");
            _ = RequireString(package, "version");
            _ = RequireString(package, "architecture");
        }
    }

    private static void ValidateUnsignedRegistry(
        JsonElement custody,
        JsonElement scope,
        byte[] scopeBytes,
        JsonElement evidence,
        JsonElement canonical,
        byte[] canonicalBytes,
        byte[] compatibilityBytes,
        ReleaseUploadCandidateIdentity candidate,
        IReadOnlyDictionary<string, CandidateEvidenceDocument> documents,
        string packageLockPath,
        string packageReceiptPath,
        string retainedManifestPath,
        string nativeLockPath)
    {
        if (!CryptographicOperations.FixedTimeEquals(
                scopeBytes,
                RenderUnsignedJson(scope, indented: true, trailingLf: true)))
        {
            throw new InvalidDataException(
                "unsigned UI scope is not pretty sorted JSON plus LF");
        }
        JsonElement scopeFull = RequireArray(scope, "fullShelfInventory");
        JsonElement scopeFresh = RequireArray(scope, "freshDelta");
        JsonElement scopeRetained = RequireArray(scope, "retainedFromIncumbent");
        RequireExactString(
            evidence,
            "fullShelfInventorySha256",
            RequireSha256(scope, "fullShelfInventorySha256"));
        RequireExactString(
            evidence,
            "incumbentInventorySha256",
            RequireSha256(scope, "incumbentInventorySha256"));
        RequireExactString(
            evidence,
            "freshDeltaSha256",
            UnsignedCompactSha256(scopeFresh));
        RequireExactString(
            evidence,
            "retainedInventorySha256",
            UnsignedCompactSha256(scopeRetained));
        if (!JsonSemanticEquals(
                RequireObject(evidence, "provenance"),
                RequireObject(scope, "provenance")))
        {
            throw new InvalidDataException(
                "unsigned publication evidence provenance drifted");
        }

        const string candidatePath = "PREVIEW_PUBLICATION_DELTA_CANDIDATE.json";
        const string authorityPath = "PREVIEW_PUBLICATION_DELTA_AUTHORITY.json";
        const string finalizePath = "PREVIEW_PUBLICATION_DELTA_FINALIZE.json";
        const string compositionPath =
            "PREVIEW_NIGHTLY_UNSIGNED_COMPOSITION.proposed.json";
        const string scopePath = "PREVIEW_NIGHTLY_UNSIGNED_SCOPE.proposed.json";
        byte[] candidateBytes = DecodeEmbedded(
            RequireObject(custody, "registryPrepareCandidateReceipt"),
            "unsigned Registry PREPARE candidate",
            candidatePath);
        byte[] authorityBytes = DecodeEmbedded(
            RequireObject(custody, "registryFinalizeAuthority"),
            "unsigned Registry FINALIZE authority",
            authorityPath);
        byte[] finalizeBytes = DecodeEmbedded(
            RequireObject(custody, "registryFinalizeReceipt"),
            "unsigned Registry FINALIZE receipt",
            finalizePath);
        using JsonDocument candidateDocument = ParseStrictObject(
            candidateBytes,
            "unsigned Registry PREPARE candidate");
        using JsonDocument authorityDocument = ParseStrictObject(
            authorityBytes,
            "unsigned Registry FINALIZE authority");
        using JsonDocument finalizeDocument = ParseStrictObject(
            finalizeBytes,
            "unsigned Registry FINALIZE receipt");
        JsonElement registryCandidate = candidateDocument.RootElement;
        JsonElement registryAuthority = authorityDocument.RootElement;
        JsonElement registryFinalize = finalizeDocument.RootElement;
        RequireUnsignedCanonicalDocument(
            candidateBytes,
            registryCandidate,
            "unsigned Registry PREPARE candidate");
        RequireUnsignedCanonicalDocument(
            authorityBytes,
            registryAuthority,
            "unsigned Registry FINALIZE authority");
        RequireUnsignedCanonicalDocument(
            finalizeBytes,
            registryFinalize,
            "unsigned Registry FINALIZE receipt");

        var candidateKeys = new HashSet<string>(
            [
                "canonicalManifest",
                "channel",
                "codeDeploymentAuthority",
                "compatibilityManifest",
                "compositionInput",
                "compositionInputDocument",
                "contractName",
                "contractVersion",
                "crossRunBitReproducible",
                "deltaPlatforms",
                "deployAuthority",
                "evidencePlatforms",
                "fullShelfInventory",
                "fullShelfInventorySha256",
                "incumbentDirectoryModesSha256",
                "incumbentInventorySha256",
                "incumbentSnapshotSha256",
                "platformScope",
                "projectionInputs",
                "proposedDirectoryModesSha256",
                "provenance",
                "publicationAuthorized",
                "publicationEligible",
                "publicationStatus",
                "releaseUploadAuthority",
                "releaseVersion",
                "retainedInventorySha256",
                "retainedPlatforms",
                "routeAuthority",
                "shelfPlatforms",
                "signaturePolicy",
                "sourceSha",
                "windowsDelta"
            ],
            StringComparer.Ordinal);
        if (!ExactPropertySet(registryCandidate, candidateKeys))
        {
            throw new InvalidDataException(
                "unsigned Registry PREPARE candidate property set drifted");
        }
        RequireExactString(
            registryCandidate,
            "contractName",
            "chummer.registry.preview-publication-delta-candidate");
        RequireExactInt32(registryCandidate, "contractVersion", 2);
        RequireExactString(registryCandidate, "channel", "preview");
        RequireExactString(registryCandidate, "releaseVersion", candidate.Version);
        RequireExactString(registryCandidate, "publicationStatus", "review_required");
        RequireExactString(registryCandidate, "platformScope", "windows_only");
        RequireBoolean(registryCandidate, "crossRunBitReproducible", expected: false);
        ValidateUnsignedSignaturePolicy(
            RequireObject(registryCandidate, "signaturePolicy"));
        RequireExactString(
            registryCandidate,
            "sourceSha",
            RequireString(scope, "sourceSha"));
        RequireBoolean(registryCandidate, "publicationAuthorized", expected: false);
        RequireBoolean(registryCandidate, "publicationEligible", expected: false);
        RequireBoolean(registryCandidate, "releaseUploadAuthority", expected: false);
        RequireBoolean(registryCandidate, "deployAuthority", expected: false);
        RequireBoolean(registryCandidate, "routeAuthority", expected: false);
        RequireBoolean(registryCandidate, "codeDeploymentAuthority", expected: false);
        RequireUnsignedStringArray(registryCandidate, "deltaPlatforms", ["windows"]);
        RequireUnsignedStringArray(registryCandidate, "evidencePlatforms", []);
        ValidateUnsignedByteReference(
            RequireObject(registryCandidate, "canonicalManifest"),
            "RELEASE_CHANNEL.generated.json",
            canonicalBytes,
            "unsigned Registry candidate canonical manifest");
        ValidateUnsignedByteReference(
            RequireObject(registryCandidate, "compatibilityManifest"),
            "releases.json",
            compatibilityBytes,
            "unsigned Registry candidate compatibility manifest");
        JsonElement registryFull = RequireArray(
            registryCandidate,
            "fullShelfInventory");
        _ = ValidateUnsignedInventory(
            registryFull,
            "unsigned Registry full shelf",
            allowEmpty: false,
            retained: false);
        if (!JsonSemanticEquals(registryFull, scopeFull)
            || !string.Equals(
                RequireSha256(registryCandidate, "fullShelfInventorySha256"),
                UnsignedCompactSha256(registryFull),
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "unsigned Registry PREPARE inventory graph drifted");
        }

        JsonElement composition = RequireObject(
            registryCandidate,
            "compositionInputDocument");
        var compositionKeys = new HashSet<string>(
            [
                "contractName",
                "contractVersion",
                "crossRunBitReproducible",
                "deployAuthorized",
                "freshDelta",
                "incumbentSnapshot",
                "platformScope",
                "proposedCanonicalManifest",
                "proposedCompatibilityManifest",
                "proposedDirectoryModes",
                "proposedDirectoryModesSha256",
                "proposedShelfInventory",
                "proposedShelfInventorySha256",
                "provenance",
                "publicationAuthorized",
                "release",
                "retainedFromIncumbent",
                "signature",
                "sourceSha",
                "status",
                "uploadAuthorized"
            ],
            StringComparer.Ordinal);
        if (!ExactPropertySet(composition, compositionKeys))
        {
            throw new InvalidDataException(
                "unsigned composition request property set drifted");
        }
        RequireExactString(
            composition,
            "contractName",
            "chummer6-ui.preview-nightly-unsigned-composition-request");
        RequireExactInt32(composition, "contractVersion", 3);
        RequireExactString(composition, "status", "prepared");
        RequireExactString(composition, "platformScope", "windows_only");
        RequireBoolean(composition, "crossRunBitReproducible", expected: false);
        RequireBoolean(composition, "publicationAuthorized", expected: false);
        RequireBoolean(composition, "uploadAuthorized", expected: false);
        RequireBoolean(composition, "deployAuthorized", expected: false);
        RequireExactString(
            composition,
            "sourceSha",
            RequireString(scope, "sourceSha"));
        if (!JsonSemanticEquals(
                RequireObject(composition, "signature"),
                RequireObject(scope, "signature")))
        {
            throw new InvalidDataException("unsigned composition signature drifted");
        }
        JsonElement compositionRelease = RequireObject(composition, "release");
        if (!ExactPropertySet(
                compositionRelease,
                new HashSet<string>(["channel", "version"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned composition release property set drifted");
        }
        RequireExactString(compositionRelease, "channel", "preview");
        RequireExactString(compositionRelease, "version", candidate.Version);
        byte[] compositionBytes = RenderUnsignedJson(
            composition,
            indented: true,
            trailingLf: true);
        ValidateUnsignedByteReference(
            RequireObject(registryCandidate, "compositionInput"),
            compositionPath,
            compositionBytes,
            "unsigned Registry composition request");
        ValidateUnsignedByteReference(
            RequireObject(composition, "proposedCanonicalManifest"),
            "RELEASE_CHANNEL.generated.json",
            canonicalBytes,
            "unsigned composition canonical manifest");
        ValidateUnsignedByteReference(
            RequireObject(composition, "proposedCompatibilityManifest"),
            "releases.json",
            compatibilityBytes,
            "unsigned composition compatibility manifest");
        JsonElement proposedInventory = RequireArray(
            composition,
            "proposedShelfInventory");
        _ = ValidateUnsignedInventory(
            proposedInventory,
            "unsigned composition proposed shelf",
            allowEmpty: false,
            retained: false);
        JsonElement proposedModes = RequireArray(
            composition,
            "proposedDirectoryModes");
        ValidateUnsignedDirectoryModes(
            proposedModes,
            "unsigned composition proposed");
        if (!JsonSemanticEquals(proposedInventory, scopeFull)
            || !string.Equals(
                RequireSha256(composition, "proposedShelfInventorySha256"),
                UnsignedCompactSha256(proposedInventory),
                StringComparison.Ordinal)
            || !string.Equals(
                RequireSha256(composition, "proposedDirectoryModesSha256"),
                UnsignedCompactSha256(proposedModes),
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "unsigned composition proposed shelf graph drifted");
        }

        JsonElement incumbent = RequireObject(composition, "incumbentSnapshot");
        if (!ExactPropertySet(
                incumbent,
                new HashSet<string>(
                    [
                        "canonicalManifest",
                        "compatibilityManifest",
                        "directoryModes",
                        "directoryModesSha256",
                        "fullShelfInventory",
                        "fullShelfInventorySha256",
                        "snapshotSha256"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned composition incumbent snapshot property set drifted");
        }
        ValidateUnsignedUnheldReference(
            RequireObject(incumbent, "canonicalManifest"),
            "RELEASE_CHANNEL.generated.json",
            "unsigned incumbent canonical manifest");
        ValidateUnsignedUnheldReference(
            RequireObject(incumbent, "compatibilityManifest"),
            "releases.json",
            "unsigned incumbent compatibility manifest");
        JsonElement incumbentInventory = RequireArray(
            incumbent,
            "fullShelfInventory");
        IReadOnlyDictionary<string, JsonElement> incumbentByPath =
            ValidateUnsignedInventory(
                incumbentInventory,
                "unsigned composition incumbent shelf",
                allowEmpty: false,
                retained: false);
        JsonElement incumbentModes = RequireArray(incumbent, "directoryModes");
        ValidateUnsignedDirectoryModes(
            incumbentModes,
            "unsigned composition incumbent");
        if (!string.Equals(
                RequireSha256(incumbent, "fullShelfInventorySha256"),
                UnsignedCompactSha256(incumbentInventory),
                StringComparison.Ordinal)
            || !string.Equals(
                RequireSha256(incumbent, "directoryModesSha256"),
                UnsignedCompactSha256(incumbentModes),
                StringComparison.Ordinal)
            || !string.Equals(
                RequireSha256(incumbent, "snapshotSha256"),
                UnsignedCompactSha256WithoutProperty(incumbent, "snapshotSha256"),
                StringComparison.Ordinal)
            || !string.Equals(
                RequireSha256(incumbent, "fullShelfInventorySha256"),
                RequireSha256(scope, "incumbentInventorySha256"),
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "unsigned composition incumbent digest graph drifted");
        }
        JsonElement compositionRetained = RequireArray(
            composition,
            "retainedFromIncumbent");
        if (!JsonSemanticEquals(compositionRetained, scopeRetained))
        {
            throw new InvalidDataException(
                "unsigned composition retained inventory drifted");
        }
        IReadOnlyDictionary<string, JsonElement> proposedByPath =
            ValidateUnsignedInventory(
                proposedInventory,
                "unsigned composition proposed shelf",
                allowEmpty: false,
                retained: false);
        foreach (JsonElement retainedRow in scopeRetained.EnumerateArray())
        {
            string path = RequireString(retainedRow, "path");
            if (!incumbentByPath.TryGetValue(path, out JsonElement incumbentRow)
                || !proposedByPath.TryGetValue(path, out JsonElement proposedRow)
                || RequireNonNegativeInt64(retainedRow, "mode")
                   != RequireNonNegativeInt64(incumbentRow, "mode")
                || RequireNonNegativeInt64(retainedRow, "mode")
                   != RequireNonNegativeInt64(proposedRow, "mode")
                || RequireNonNegativeInt64(retainedRow, "sizeBytes")
                   != RequireNonNegativeInt64(incumbentRow, "sizeBytes")
                || RequireNonNegativeInt64(retainedRow, "sizeBytes")
                   != RequireNonNegativeInt64(proposedRow, "sizeBytes")
                || !string.Equals(
                    RequireSha256(retainedRow, "sha256"),
                    RequireSha256(incumbentRow, "sha256"),
                    StringComparison.Ordinal)
                || !string.Equals(
                    RequireSha256(retainedRow, "sha256"),
                    RequireSha256(proposedRow, "sha256"),
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    "unsigned retained bytes differ across shelves");
            }
        }

        JsonElement compositionFresh = RequireArray(composition, "freshDelta");
        if (compositionFresh.GetArrayLength() != scopeFresh.GetArrayLength())
        {
            throw new InvalidDataException(
                "unsigned composition fresh delta cardinality drifted");
        }
        JsonElement? windowsArtifact = null;
        var shelfPlatforms = new SortedSet<string>(StringComparer.Ordinal);
        foreach (JsonElement artifact in RequireArray(canonical, "artifacts").EnumerateArray())
        {
            string platform = RequireString(artifact, "platform");
            if (platform is not "linux" and not "macos" and not "windows")
            {
                throw new InvalidDataException(
                    "unsigned canonical artifact platform drifted");
            }
            shelfPlatforms.Add(platform);
            if (platform == "windows"
                && string.Equals(
                    RequireString(artifact, "head"),
                    "avalonia",
                    StringComparison.Ordinal)
                && string.Equals(
                    RequireString(artifact, "rid"),
                    WindowsRid,
                    StringComparison.Ordinal))
            {
                if (windowsArtifact is not null)
                {
                    throw new InvalidDataException(
                        "unsigned canonical Windows artifact is duplicated");
                }
                windowsArtifact = artifact;
            }
        }
        if (windowsArtifact is null)
        {
            throw new InvalidDataException(
                "unsigned canonical Windows artifact is missing");
        }
        string manifestRowSha256 = UnsignedCompactSha256(windowsArtifact.Value);
        string[] freshKeys =
        [
            "artifactRole",
            "fileName",
            "head",
            "mode",
            "path",
            "platform",
            "rid",
            "sha256",
            "sizeBytes"
        ];
        for (int index = 0; index < scopeFresh.GetArrayLength(); index++)
        {
            JsonElement held = scopeFresh[index];
            JsonElement row = compositionFresh[index];
            var keys = new HashSet<string>(freshKeys, StringComparer.Ordinal)
            {
                "manifestRowSha256"
            };
            if (!ExactPropertySet(row, keys)
                || !string.Equals(
                    RequireSha256(row, "manifestRowSha256"),
                    manifestRowSha256,
                    StringComparison.Ordinal)
                || freshKeys.Any(key =>
                    !row.TryGetProperty(key, out JsonElement value)
                    || !held.TryGetProperty(key, out JsonElement expected)
                    || !JsonSemanticEquals(value, expected)))
            {
                throw new InvalidDataException(
                    "unsigned composition fresh byte graph drifted");
            }
        }

        var provenancePaths = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["packagePlaneLock"] = packageLockPath,
            ["packagePlaneReceipt"] = packageReceiptPath,
            ["retainedManifest"] = retainedManifestPath,
            ["nativeToolchainLock"] = nativeLockPath
        };
        JsonElement compositionProvenance = RequireObject(
            composition,
            "provenance");
        if (!ExactPropertySet(
                compositionProvenance,
                new HashSet<string>(provenancePaths.Keys, StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned composition provenance property set drifted");
        }
        foreach ((string name, string path) in provenancePaths)
        {
            ValidateUnsignedByteReference(
                RequireObject(compositionProvenance, name),
                path,
                documents[path].Bytes,
                $"unsigned composition provenance ${name}");
        }
        JsonElement candidateProvenance = RequireObject(
            registryCandidate,
            "provenance");
        if (!JsonSemanticEquals(candidateProvenance, compositionProvenance))
        {
            throw new InvalidDataException(
                "unsigned Registry PREPARE provenance graph drifted");
        }
        ValidateUnsignedProjectionInputs(
            RequireObject(registryCandidate, "projectionInputs"));
        RequireExactString(
            registryCandidate,
            "incumbentInventorySha256",
            RequireSha256(incumbent, "fullShelfInventorySha256"));
        RequireExactString(
            registryCandidate,
            "incumbentSnapshotSha256",
            RequireSha256(incumbent, "snapshotSha256"));
        RequireExactString(
            registryCandidate,
            "incumbentDirectoryModesSha256",
            RequireSha256(incumbent, "directoryModesSha256"));
        RequireExactString(
            registryCandidate,
            "proposedDirectoryModesSha256",
            RequireSha256(composition, "proposedDirectoryModesSha256"));
        RequireExactString(
            registryCandidate,
            "retainedInventorySha256",
            UnsignedCompactSha256(scopeRetained));
        RequireUnsignedStringArray(
            registryCandidate,
            "retainedPlatforms",
            shelfPlatforms.Where(static platform => platform != "windows").ToArray());
        RequireUnsignedStringArray(
            registryCandidate,
            "shelfPlatforms",
            shelfPlatforms.ToArray());
        ValidateUnsignedWindowsDelta(
            RequireObject(registryCandidate, "windowsDelta"),
            scopeFresh);

        var mixedGraph = new Dictionary<string, int>(StringComparer.Ordinal)
        {
            ["authorityContractVersion"] = 2,
            ["candidateReceiptContractVersion"] = 2,
            ["compositionRequestContractVersion"] = 3,
            ["finalizeReceiptContractVersion"] = 2,
            ["sourceScopeContractVersion"] = 3
        };
        var authorityKeys = new HashSet<string>(
            [
                "candidateImportAuthority",
                "candidateReceipt",
                "candidateReviewAuthority",
                "canonicalManifest",
                "channel",
                "codeDeploymentAuthority",
                "compatibilityManifest",
                "compositionRequest",
                "contractName",
                "contractVersion",
                "crossRunBitReproducible",
                "deltaPlatforms",
                "deployAuthority",
                "evidencePlatforms",
                "fullShelfInventorySha256",
                "incumbentInventorySha256",
                "incumbentSnapshotSha256",
                "mixedVersionGraph",
                "platformScope",
                "projectionInputs",
                "proposedDirectoryModesSha256",
                "provenance",
                "publicationAuthorized",
                "publicationEligible",
                "releaseUploadAuthority",
                "releaseVersion",
                "retainedInventorySha256",
                "retainedPlatforms",
                "routeAuthority",
                "shelfPlatforms",
                "signaturePolicy",
                "sourceScope",
                "sourceSha",
                "windowsDelta"
            ],
            StringComparer.Ordinal);
        if (!ExactPropertySet(registryAuthority, authorityKeys))
        {
            throw new InvalidDataException(
                "unsigned Registry FINALIZE authority property set drifted");
        }
        RequireExactString(
            registryAuthority,
            "contractName",
            "chummer.registry.preview-publication-delta-authority");
        RequireExactInt32(registryAuthority, "contractVersion", 2);
        ValidateUnsignedRegistryPosture(
            registryAuthority,
            candidate.Version,
            scope,
            mixedGraph,
            includeReviewAuthority: true);
        ValidateUnsignedByteReference(
            RequireObject(registryAuthority, "candidateReceipt"),
            candidatePath,
            candidateBytes,
            "unsigned Registry authority candidate receipt");
        ValidateUnsignedByteReference(
            RequireObject(registryAuthority, "canonicalManifest"),
            "RELEASE_CHANNEL.generated.json",
            canonicalBytes,
            "unsigned Registry authority canonical manifest");
        ValidateUnsignedByteReference(
            RequireObject(registryAuthority, "compatibilityManifest"),
            "releases.json",
            compatibilityBytes,
            "unsigned Registry authority compatibility manifest");
        ValidateUnsignedByteReference(
            RequireObject(registryAuthority, "compositionRequest"),
            compositionPath,
            compositionBytes,
            "unsigned Registry authority composition request");
        ValidateUnsignedByteReference(
            RequireObject(registryAuthority, "sourceScope"),
            scopePath,
            scopeBytes,
            "unsigned Registry authority source scope");
        foreach (string name in new[]
                 {
                     "fullShelfInventorySha256",
                     "incumbentInventorySha256",
                     "incumbentSnapshotSha256",
                     "proposedDirectoryModesSha256",
                     "retainedInventorySha256"
                 })
        {
            RequireExactString(
                registryAuthority,
                name,
                RequireSha256(registryCandidate, name));
        }
        if (!JsonSemanticEquals(
                RequireArray(registryAuthority, "retainedPlatforms"),
                RequireArray(registryCandidate, "retainedPlatforms"))
            || !JsonSemanticEquals(
                RequireArray(registryAuthority, "shelfPlatforms"),
                RequireArray(registryCandidate, "shelfPlatforms"))
            || !JsonSemanticEquals(
                RequireObject(registryAuthority, "projectionInputs"),
                RequireObject(registryCandidate, "projectionInputs"))
            || !JsonSemanticEquals(
                RequireObject(registryAuthority, "provenance"),
                candidateProvenance)
            || !JsonSemanticEquals(
                RequireObject(registryAuthority, "windowsDelta"),
                RequireObject(registryCandidate, "windowsDelta")))
        {
            throw new InvalidDataException(
                "unsigned Registry FINALIZE/PREPARE custody graph drifted");
        }
        ValidateUnsignedProjectionInputs(
            RequireObject(registryAuthority, "projectionInputs"));

        var finalizeKeys = new HashSet<string>(
            [
                "authority",
                "candidateBytesMutated",
                "candidateImportAuthority",
                "candidateReceipt",
                "candidateReviewAuthority",
                "canonicalManifest",
                "channel",
                "codeDeploymentAuthority",
                "compatibilityManifest",
                "compositionRequest",
                "contractName",
                "contractVersion",
                "deployAuthority",
                "fullShelfInventorySha256",
                "mixedVersionGraph",
                "platformScope",
                "provenance",
                "publicationAuthorized",
                "publicationEligible",
                "releaseUploadAuthority",
                "releaseVersion",
                "routeAuthority",
                "signaturePolicy",
                "sourceScope",
                "verificationStatus",
                "windowsDelta"
            ],
            StringComparer.Ordinal);
        if (!ExactPropertySet(registryFinalize, finalizeKeys))
        {
            throw new InvalidDataException(
                "unsigned Registry FINALIZE receipt property set drifted");
        }
        RequireExactString(
            registryFinalize,
            "contractName",
            "chummer.registry.preview-publication-delta-finalize");
        RequireExactInt32(registryFinalize, "contractVersion", 2);
        RequireExactString(registryFinalize, "verificationStatus", "finalized");
        RequireBoolean(registryFinalize, "candidateBytesMutated", expected: false);
        ValidateUnsignedRegistryPosture(
            registryFinalize,
            candidate.Version,
            scope,
            mixedGraph,
            includeReviewAuthority: true);
        RequireExactString(
            registryFinalize,
            "fullShelfInventorySha256",
            RequireSha256(registryCandidate, "fullShelfInventorySha256"));
        if (!JsonSemanticEquals(
                RequireObject(registryFinalize, "provenance"),
                candidateProvenance)
            || !JsonSemanticEquals(
                RequireObject(registryFinalize, "windowsDelta"),
                RequireObject(registryCandidate, "windowsDelta")))
        {
            throw new InvalidDataException(
                "unsigned Registry FINALIZE receipt custody graph drifted");
        }
        foreach ((string name, string path, byte[] bytes) in new[]
                 {
                     ("authority", authorityPath, authorityBytes),
                     ("candidateReceipt", candidatePath, candidateBytes),
                     ("canonicalManifest", "RELEASE_CHANNEL.generated.json", canonicalBytes),
                     ("compatibilityManifest", "releases.json", compatibilityBytes),
                     ("compositionRequest", compositionPath, compositionBytes),
                     ("sourceScope", scopePath, scopeBytes)
                 })
        {
            ValidateUnsignedByteReference(
                RequireObject(registryFinalize, name),
                path,
                bytes,
                $"unsigned Registry finalize ${name}");
        }
        ValidateUnsignedRegistrySummary(
            RequireObject(custody, "registryFinalization"),
            candidateBytes,
            authorityBytes,
            finalizeBytes);
    }

    private static void ValidateUnsignedWindowsDelta(
        JsonElement value,
        JsonElement fresh)
    {
        string[] roles = ["installer", "bootstrap_payload"];
        if (!ExactPropertySet(
                value,
                new HashSet<string>(roles, StringComparer.Ordinal))
            || fresh.GetArrayLength() != roles.Length)
        {
            throw new InvalidDataException("unsigned Registry Windows delta drifted");
        }
        for (int index = 0; index < roles.Length; index++)
        {
            JsonElement reference = RequireObject(value, roles[index]);
            JsonElement row = fresh[index];
            if (!ExactPropertySet(
                    reference,
                    new HashSet<string>(
                        ["path", "sha256", "sizeBytes"],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException(
                    "unsigned Registry Windows delta reference drifted");
            }
            RequireExactString(reference, "path", RequireString(row, "path"));
            RequireExactString(reference, "sha256", RequireSha256(row, "sha256"));
            if (RequireNonNegativeInt64(reference, "sizeBytes")
                != RequireNonNegativeInt64(row, "sizeBytes"))
            {
                throw new InvalidDataException(
                    "unsigned Registry Windows delta bytes drifted");
            }
        }
    }

    private static void ValidateUnsignedRegistryPosture(
        JsonElement value,
        string version,
        JsonElement scope,
        IReadOnlyDictionary<string, int> mixedGraph,
        bool includeReviewAuthority)
    {
        RequireExactString(value, "channel", "preview");
        RequireExactString(value, "releaseVersion", version);
        RequireExactString(value, "platformScope", "windows_only");
        RequireBoolean(value, "candidateImportAuthority", expected: true);
        if (includeReviewAuthority)
        {
            RequireBoolean(value, "candidateReviewAuthority", expected: true);
        }
        RequireBoolean(value, "publicationAuthorized", expected: false);
        RequireBoolean(value, "publicationEligible", expected: false);
        RequireBoolean(value, "releaseUploadAuthority", expected: false);
        RequireBoolean(value, "deployAuthority", expected: false);
        RequireBoolean(value, "routeAuthority", expected: false);
        RequireBoolean(value, "codeDeploymentAuthority", expected: false);
        ValidateUnsignedSignaturePolicy(RequireObject(value, "signaturePolicy"));
        JsonElement graph = RequireObject(value, "mixedVersionGraph");
        if (!ExactPropertySet(
                graph,
                new HashSet<string>(mixedGraph.Keys, StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned Registry mixed-version graph drifted");
        }
        foreach ((string name, int expected) in mixedGraph)
        {
            RequireExactInt32(graph, name, expected);
        }
        if (value.TryGetProperty("crossRunBitReproducible", out _))
        {
            RequireBoolean(value, "crossRunBitReproducible", expected: false);
            RequireExactString(
                value,
                "sourceSha",
                RequireString(scope, "sourceSha"));
            RequireUnsignedStringArray(value, "deltaPlatforms", ["windows"]);
            RequireUnsignedStringArray(value, "evidencePlatforms", []);
        }
    }

    private static void ValidateUnsignedRegistrySummary(
        JsonElement summary,
        byte[] candidateBytes,
        byte[] authorityBytes,
        byte[] finalizeBytes)
    {
        if (!ExactPropertySet(
                summary,
                new HashSet<string>(
                    [
                        "authoritySha256",
                        "candidateImportAuthority",
                        "candidateReceiptSha256",
                        "candidateReviewAuthority",
                        "codeDeploymentAuthority",
                        "deployAuthority",
                        "exactIncomingDesktopScope",
                        "finalizeReceiptSha256",
                        "publicationAuthorized",
                        "publicationEligible",
                        "releaseUploadAuthority",
                        "routeAuthority",
                        "scope",
                        "signaturePolicy",
                        "status"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned Registry finalization summary property set drifted");
        }
        RequireExactString(summary, "status", "finalized");
        RequireExactString(summary, "scope", "windows_only");
        RequireExactString(
            summary,
            "exactIncomingDesktopScope",
            CandidateExactIncomingDesktopScope);
        RequireBoolean(summary, "candidateImportAuthority", expected: true);
        RequireBoolean(summary, "candidateReviewAuthority", expected: true);
        RequireBoolean(summary, "publicationAuthorized", expected: false);
        RequireBoolean(summary, "publicationEligible", expected: false);
        RequireBoolean(summary, "releaseUploadAuthority", expected: false);
        RequireBoolean(summary, "deployAuthority", expected: false);
        RequireBoolean(summary, "routeAuthority", expected: false);
        RequireBoolean(summary, "codeDeploymentAuthority", expected: false);
        ValidateUnsignedSignaturePolicy(RequireObject(summary, "signaturePolicy"));
        RequireExactString(summary, "candidateReceiptSha256", Sha256(candidateBytes));
        RequireExactString(summary, "authoritySha256", Sha256(authorityBytes));
        RequireExactString(summary, "finalizeReceiptSha256", Sha256(finalizeBytes));
    }

    private static byte[] RenderUnsignedJson(
        JsonElement value,
        bool indented,
        bool trailingLf)
    {
        var builder = new StringBuilder();
        AppendUnsignedJson(builder, value, indented, 0);
        if (trailingLf)
        {
            builder.Append('\n');
        }
        return Encoding.UTF8.GetBytes(builder.ToString());
    }

    private static void AppendUnsignedJson(
        StringBuilder builder,
        JsonElement value,
        bool indented,
        int depth)
    {
        switch (value.ValueKind)
        {
            case JsonValueKind.Object:
            {
                JsonProperty[] properties = value.EnumerateObject()
                    .OrderBy(static property => property.Name, StringComparer.Ordinal)
                    .ToArray();
                builder.Append('{');
                if (properties.Length > 0)
                {
                    if (indented)
                    {
                        builder.Append('\n');
                    }
                    for (int index = 0; index < properties.Length; index++)
                    {
                        if (indented)
                        {
                            builder.Append(' ', checked((depth + 1) * 2));
                        }
                        AppendUnsignedJsonString(builder, properties[index].Name);
                        builder.Append(indented ? ": " : ":");
                        AppendUnsignedJson(
                            builder,
                            properties[index].Value,
                            indented,
                            depth + 1);
                        if (index + 1 < properties.Length)
                        {
                            builder.Append(',');
                        }
                        if (indented)
                        {
                            builder.Append('\n');
                        }
                    }
                    if (indented)
                    {
                        builder.Append(' ', checked(depth * 2));
                    }
                }
                builder.Append('}');
                break;
            }
            case JsonValueKind.Array:
            {
                JsonElement[] items = value.EnumerateArray().ToArray();
                builder.Append('[');
                if (items.Length > 0)
                {
                    if (indented)
                    {
                        builder.Append('\n');
                    }
                    for (int index = 0; index < items.Length; index++)
                    {
                        if (indented)
                        {
                            builder.Append(' ', checked((depth + 1) * 2));
                        }
                        AppendUnsignedJson(builder, items[index], indented, depth + 1);
                        if (index + 1 < items.Length)
                        {
                            builder.Append(',');
                        }
                        if (indented)
                        {
                            builder.Append('\n');
                        }
                    }
                    if (indented)
                    {
                        builder.Append(' ', checked(depth * 2));
                    }
                }
                builder.Append(']');
                break;
            }
            case JsonValueKind.String:
                AppendUnsignedJsonString(builder, value.GetString()!);
                break;
            case JsonValueKind.Number:
                builder.Append(value.GetRawText());
                break;
            case JsonValueKind.True:
                builder.Append("true");
                break;
            case JsonValueKind.False:
                builder.Append("false");
                break;
            case JsonValueKind.Null:
                builder.Append("null");
                break;
            default:
                throw new InvalidDataException("unsigned JSON contains an invalid value");
        }
    }

    private static void AppendUnsignedJsonString(StringBuilder builder, string value)
    {
        builder.Append('"');
        foreach (char character in value)
        {
            switch (character)
            {
                case '"':
                    builder.Append("\\\"");
                    break;
                case '\\':
                    builder.Append("\\\\");
                    break;
                case '\b':
                    builder.Append("\\b");
                    break;
                case '\f':
                    builder.Append("\\f");
                    break;
                case '\n':
                    builder.Append("\\n");
                    break;
                case '\r':
                    builder.Append("\\r");
                    break;
                case '\t':
                    builder.Append("\\t");
                    break;
                default:
                    if (character < 0x20 || character > 0x7e)
                    {
                        builder.Append("\\u");
                        builder.Append(((int)character).ToString(
                            "x4",
                            System.Globalization.CultureInfo.InvariantCulture));
                    }
                    else
                    {
                        builder.Append(character);
                    }
                    break;
            }
        }
        builder.Append('"');
    }

    private static string UnsignedCompactSha256(JsonElement value)
        => Sha256(RenderUnsignedJson(value, indented: false, trailingLf: false));

    private static string UnsignedCompactSha256WithoutProperty(
        JsonElement value,
        string excludedProperty)
    {
        JsonProperty[] properties = value.EnumerateObject()
            .Where(property => !string.Equals(
                property.Name,
                excludedProperty,
                StringComparison.Ordinal))
            .OrderBy(static property => property.Name, StringComparer.Ordinal)
            .ToArray();
        var builder = new StringBuilder();
        builder.Append('{');
        for (int index = 0; index < properties.Length; index++)
        {
            if (index > 0)
            {
                builder.Append(',');
            }
            AppendUnsignedJsonString(builder, properties[index].Name);
            builder.Append(':');
            AppendUnsignedJson(builder, properties[index].Value, indented: false, depth: 1);
        }
        builder.Append('}');
        return Sha256(Encoding.UTF8.GetBytes(builder.ToString()));
    }

    private static void RequireUnsignedCanonicalDocument(
        byte[] bytes,
        JsonElement value,
        string label)
    {
        if (!CryptographicOperations.FixedTimeEquals(
                bytes,
                RenderUnsignedJson(value, indented: false, trailingLf: true)))
        {
            throw new InvalidDataException($"${label} is not canonical compact JSON plus LF");
        }
    }

    private static void ValidateUnsignedProjectionInputs(JsonElement value)
    {
        var paths = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["materializer"] = "scripts/materialize_unsigned_preview_publication_delta.py",
            ["schema"] = "contracts/preview-publication-delta-v2.schema.json"
        };
        if (!ExactPropertySet(
                value,
                new HashSet<string>(paths.Keys, StringComparer.Ordinal)))
        {
            throw new InvalidDataException("unsigned Registry projection inputs drifted");
        }
        foreach ((string name, string path) in paths)
        {
            JsonElement reference = RequireObject(value, name);
            if (!ExactPropertySet(
                    reference,
                    new HashSet<string>(
                        ["path", "sha256", "sizeBytes"],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException(
                    $"unsigned Registry projection input ${name} drifted");
            }
            RequireExactString(reference, "path", path);
            _ = RequireSha256(reference, "sha256");
            _ = RequirePositiveInt64(reference, "sizeBytes");
        }
    }

    private static void ValidateUnsignedUnheldReference(
        JsonElement reference,
        string path,
        string label)
    {
        if (!ExactPropertySet(
                reference,
                new HashSet<string>(
                    ["path", "sha256", "sizeBytes"],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException($"${label} property set drifted");
        }
        RequireExactString(reference, "path", path);
        _ = RequireSha256(reference, "sha256");
        _ = RequirePositiveInt64(reference, "sizeBytes");
    }

    private static void RequireUnsignedStringArray(
        JsonElement parent,
        string property,
        IReadOnlyList<string> expected)
    {
        JsonElement value = RequireArray(parent, property);
        string[] actual = value.EnumerateArray()
            .Select(static item => item.ValueKind == JsonValueKind.String
                ? item.GetString()
                : null)
            .Where(static item => item is not null)
            .Cast<string>()
            .ToArray();
        if (actual.Length != value.GetArrayLength()
            || !actual.SequenceEqual(expected, StringComparer.Ordinal))
        {
            throw new InvalidDataException($"unsigned Registry ${property} drifted");
        }
    }

    private static IReadOnlyDictionary<string, JsonElement> ValidateUnsignedInventory(
        JsonElement value,
        string label,
        bool allowEmpty,
        bool retained)
    {
        if (value.ValueKind != JsonValueKind.Array
            || !allowEmpty && value.GetArrayLength() == 0
            || value.GetArrayLength() > 100_000)
        {
            throw new InvalidDataException($"${label} inventory is invalid");
        }
        var rows = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
        string? previous = null;
        foreach (JsonElement row in value.EnumerateArray())
        {
            var keys = new HashSet<string>(
                ["mode", "path", "sha256", "sizeBytes"],
                StringComparer.Ordinal);
            if (retained)
            {
                keys.Add("retentionKind");
            }
            string path = RequireString(row, "path");
            long mode = RequireNonNegativeInt64(row, "mode");
            if (!ExactPropertySet(row, keys)
                || !IsCanonicalRelativePath(path)
                || previous is not null && string.CompareOrdinal(previous, path) >= 0
                || mode > 0x1ff
                || !rows.TryAdd(path, row))
            {
                throw new InvalidDataException($"${label} inventory row drifted");
            }
            _ = RequireSha256(row, "sha256");
            _ = RequireNonNegativeInt64(row, "sizeBytes");
            if (retained
                && RequireString(row, "retentionKind")
                    is not "managed_artifact" and not "ancillary")
            {
                throw new InvalidDataException(
                    $"${label} retention classification drifted");
            }
            previous = path;
        }
        return rows;
    }

    private static void ValidateUnsignedDirectoryModes(JsonElement value, string label)
    {
        if (value.ValueKind != JsonValueKind.Array
            || value.GetArrayLength() == 0
            || value.GetArrayLength() > 100_000)
        {
            throw new InvalidDataException($"${label} directory modes are invalid");
        }
        string? previous = null;
        foreach (JsonElement row in value.EnumerateArray())
        {
            if (!ExactPropertySet(
                    row,
                    new HashSet<string>(["mode", "path"], StringComparer.Ordinal)))
            {
                throw new InvalidDataException(
                    $"${label} directory mode row drifted");
            }
            string path = RequireString(row, "path");
            long mode = RequireNonNegativeInt64(row, "mode");
            if (!IsCanonicalRelativePath(path)
                || previous is not null && string.CompareOrdinal(previous, path) >= 0
                || mode > 0x1ff)
            {
                throw new InvalidDataException(
                    $"${label} directory mode row is invalid");
            }
            previous = path;
        }
    }

    private static void ValidateFinalizedPublicationAndRegistry(
        JsonElement custody,
        JsonElement canonical,
        byte[] canonicalBytes,
        byte[] compatibilityBytes,
        ReleaseUploadCandidateIdentity candidate,
        IReadOnlyList<ReleaseUploadCandidateInventoryRow> inventory,
        CandidateNativePackage nativePackage)
    {
        JsonElement finalized = RequireObject(custody, "finalizedPublicationEvidence");
        if (!ExactPropertySet(
                finalized,
                new HashSet<string>(
                    [
                        "status",
                        "exactIncomingDesktopScope",
                        "publicationScopeSha256",
                        "scopeDecisionSha256",
                        "signingReceiptSha256",
                        "nativeEvidenceSha256",
                        "authenticodeVerificationSha256",
                        "approvalSha256",
                        "visualApprovalSha256",
                        "actors",
                        "files"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "candidate finalized publication evidence property set drifted");
        }
        RequireExactString(finalized, "status", "passed");
        RequireExactString(
            finalized,
            "exactIncomingDesktopScope",
            CandidateExactIncomingDesktopScope);
        var documents = new Dictionary<string, CandidateEvidenceDocument>(StringComparer.Ordinal);
        try
        {
            foreach (JsonElement entry in RequireArray(finalized, "files").EnumerateArray())
            {
                string path = RequireString(entry, "path");
                if (!IsCanonicalRelativePath(path) || documents.ContainsKey(path))
                {
                    throw new InvalidDataException(
                        "candidate finalized publication evidence path drifted");
                }
                byte[] bytes = DecodeEmbedded(
                    entry,
                    $"candidate finalized publication {path}",
                    path);
                documents.Add(
                    path,
                    new CandidateEvidenceDocument(
                        ParseStrictObject(bytes, $"candidate finalized publication {path}"),
                        bytes,
                        RequireSha256(entry, "sha256"),
                        RequireNonNegativeInt64(entry, "sizeBytes")));
            }

            const string scopePath = "PREVIEW_NIGHTLY_PUBLICATION_SCOPE.generated.json";
            if (!documents.TryGetValue(scopePath, out CandidateEvidenceDocument? scopeDocument))
            {
                throw new InvalidDataException("candidate finalized publication scope is absent");
            }
            RequireExactString(finalized, "publicationScopeSha256", scopeDocument.Sha256);
            JsonElement scope = scopeDocument.Root;
            if (!ExactPropertySet(
                    scope,
                    new HashSet<string>(
                        [
                            "approval",
                            "approvalIndependent",
                            "authenticodeRequired",
                            "authenticodeVerificationSha256",
                            "buildEvidenceTuples",
                            "contractName",
                            "contractVersion",
                            "deployAuthorized",
                            "fullShelfCompatibilityManifestSha256",
                            "fullShelfInventory",
                            "fullShelfInventorySha256",
                            "fullShelfManifestSha256",
                            "incumbentSnapshot",
                            "incumbentSnapshotSha256",
                            "macosSoak",
                            "nativeEvidenceComposite",
                            "nativeEvidenceSha256",
                            "nonPublishedEvidenceTuples",
                            "postPublicationShelfTuples",
                            "publicationDeltaTuples",
                            "publicationEligible",
                            "registryPrepare",
                            "registryFinalizeEligible",
                            "release",
                            "retainedTuples",
                            "scopeDecision",
                            "scopeDecisionSha256",
                            "signingReceipt",
                            "signingReceiptSha256",
                            "status",
                            "uploadAuthorized",
                            "visualApprovalSha256"
                        ],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException(
                    "candidate finalized publication scope property set drifted");
            }
            RequireExactString(
                scope,
                "contractName",
                "chummer6-ui.preview-nightly-windows-publication-scope");
            RequireExactInt32(scope, "contractVersion", 2);
            RequireExactString(scope, "status", "validated");
            RequireBoolean(scope, "approvalIndependent", expected: true);
            RequireBoolean(scope, "authenticodeRequired", expected: true);
            RequireBoolean(scope, "registryFinalizeEligible", expected: true);
            RequireBoolean(scope, "publicationEligible", expected: false);
            RequireBoolean(scope, "uploadAuthorized", expected: false);
            RequireBoolean(scope, "deployAuthorized", expected: false);
            JsonElement release = RequireObject(scope, "release");
            RequireExactString(release, "channel", "preview");
            RequireExactString(release, "version", candidate.Version);
            RequireExactString(scope, "fullShelfManifestSha256", Sha256(canonicalBytes));
            RequireExactString(
                scope,
                "fullShelfCompatibilityManifestSha256",
                Sha256(compatibilityBytes));
            RequireExactString(
                finalized,
                "scopeDecisionSha256",
                RequireSha256(scope, "scopeDecisionSha256"));

            JsonElement delta = RequireArray(scope, "publicationDeltaTuples");
            if (delta.GetArrayLength() != 2)
            {
                throw new InvalidDataException(
                    "candidate publication delta is not the exact Windows pair");
            }
            ValidateFinalScopeTuple(delta[0], "installer", "windows", WindowsRid);
            ValidateFinalScopeTuple(delta[1], "payload", "windows", WindowsRid);
            CandidateWindowsScope canonicalScope = ParseCandidateWindowsScope(
                canonical,
                candidate,
                inventory);
            CandidateHeadArtifacts expectedWindows = canonicalScope.Artifacts["avalonia"];
            ValidateFinalScopeArtifact(delta[0], expectedWindows.Installer);
            ValidateFinalScopeArtifact(delta[1], expectedWindows.Payload);

            var expectedUploadPaths = new HashSet<string>(
                ["RELEASE_CHANNEL.generated.json", "releases.json"],
                StringComparer.Ordinal);
            foreach (JsonElement row in RequireArray(
                         scope,
                         "postPublicationShelfTuples").EnumerateArray())
            {
                ValidateFinalScopeTuple(
                    row,
                    RequireString(row, "artifactRole"),
                    RequireString(row, "platform"),
                    RequireString(row, "rid"));
                expectedUploadPaths.Add(RequireString(row, "path"));
            }
            if (!expectedUploadPaths.SetEquals(
                    inventory.Select(static row => row.Path)))
            {
                throw new InvalidDataException(
                    "candidate inventory differs from the finalized Run upload allowlist");
            }
            ValidateFinalScopeInventory(scope, inventory);

            JsonElement signingReference = RequireObject(scope, "signingReceipt");
            string signingPath = RequireString(signingReference, "path");
            string approvalPath = RequireString(RequireObject(scope, "approval"), "path");
            string visualPath =
                $"WINDOWS_INSTALLER_VISUAL_PROOF-avalonia-{WindowsRid}.generated.json";
            const string nativePath = "NATIVE_WINDOWS_EVIDENCE.generated.json";
            const string nativeFinalizationPath =
                "WINDOWS_NATIVE_EVIDENCE_FINALIZATION.generated.json";
            const string authenticodePath =
                "proof/windows-native/authenticode/"
                + "AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json";
            var expectedEvidencePaths = new HashSet<string>(
                [
                    scopePath,
                    signingPath,
                    approvalPath,
                    visualPath,
                    nativePath,
                    nativeFinalizationPath,
                    authenticodePath
                ],
                StringComparer.Ordinal);
            if (!expectedEvidencePaths.SetEquals(documents.Keys))
            {
                throw new InvalidDataException(
                    "candidate finalized publication evidence file scope drifted");
            }
            JsonElement composite = RequireObject(scope, "nativeEvidenceComposite");
            if (!ExactPropertySet(
                    composite,
                    new HashSet<string>(
                        [
                            "authenticodeVerification",
                            "nativeFinalization",
                            "visualProof",
                            "wrapper"
                        ],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException(
                    "candidate native evidence composite property set drifted");
            }
            ValidateNativeContractReference(
                composite,
                "wrapper",
                "chummer6-ui.preview-nightly-native-windows-evidence",
                1,
                nativePath,
                documents[nativePath]);
            ValidateNativeContractReference(
                composite,
                "nativeFinalization",
                "chummer6-ui.preview-nightly-native-windows-finalization",
                2,
                nativeFinalizationPath,
                documents[nativeFinalizationPath]);
            ValidateNativeContractReference(
                composite,
                "visualProof",
                "chummer6-ui.windows_installer_visual_proof",
                1,
                visualPath,
                documents[visualPath]);
            ValidateNativeContractReference(
                composite,
                "authenticodeVerification",
                "chummer6-ui.windows-authenticode-verification",
                1,
                authenticodePath,
                documents[authenticodePath]);
            ValidatePublicationDigestAlias(
                finalized,
                scope,
                "signingReceiptSha256",
                documents[signingPath]);
            ValidatePublicationDigestAlias(
                finalized,
                scope,
                "nativeEvidenceSha256",
                documents[nativePath]);
            ValidatePublicationDigestAlias(
                finalized,
                scope,
                "authenticodeVerificationSha256",
                documents[authenticodePath]);
            RequireExactString(finalized, "approvalSha256", documents[approvalPath].Sha256);
            JsonElement visualDigests = RequireArray(finalized, "visualApprovalSha256");
            if (visualDigests.GetArrayLength() != 1
                || visualDigests[0].ValueKind != JsonValueKind.String
                || !string.Equals(
                    visualDigests[0].GetString(),
                    documents[visualPath].Sha256,
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    "candidate finalized visual evidence digest drifted");
            }
            JsonElement actors = RequireObject(finalized, "actors");
            string[] actorNames =
                ["candidateProducer", "nativeCapture", "visualReviewer", "scopeApprover"];
            if (!ExactPropertySet(
                    actors,
                    new HashSet<string>(actorNames, StringComparer.Ordinal)))
            {
                throw new InvalidDataException(
                    "candidate finalized publication actor property set drifted");
            }
            string[] actorValues = actorNames.Select(name => RequireString(actors, name)).ToArray();
            string candidateActor = RequireString(actors, "candidateProducer");
            string captureActor = RequireString(actors, "nativeCapture");
            string visualActor = RequireString(actors, "visualReviewer");
            string scopeActor = RequireString(actors, "scopeApprover");
            if (actorValues.Any(actor => !GitHubLoginPattern.IsMatch(actor))
                || !string.Equals(visualActor, scopeActor, StringComparison.OrdinalIgnoreCase)
                || string.Equals(candidateActor, scopeActor, StringComparison.OrdinalIgnoreCase)
                || string.Equals(captureActor, scopeActor, StringComparison.OrdinalIgnoreCase))
            {
                throw new InvalidDataException(
                    "candidate finalized publication review owner is not independent");
            }
            ValidateFinalNativeEvidenceDocuments(
                documents,
                candidate,
                actors,
                expectedWindows.Installer,
                nativePackage,
                nativePath,
                nativeFinalizationPath,
                visualPath,
                authenticodePath);

            byte[] candidateReceiptBytes = DecodeEmbedded(
                RequireObject(custody, "registryPrepareCandidateReceipt"),
                "Registry PREPARE candidate receipt",
                "PREVIEW_PUBLICATION_DELTA_CANDIDATE.json");
            byte[] registryAuthorityBytes = DecodeEmbedded(
                RequireObject(custody, "registryFinalizeAuthority"),
                "Registry FINALIZE authority",
                "PREVIEW_PUBLICATION_DELTA_AUTHORITY.json");
            byte[] finalizeBytes = DecodeEmbedded(
                RequireObject(custody, "registryFinalizeReceipt"),
                "Registry FINALIZE receipt",
                "PREVIEW_PUBLICATION_DELTA_FINALIZE.json");
            using JsonDocument candidateReceiptDocument = ParseStrictObject(
                candidateReceiptBytes,
                "Registry PREPARE candidate receipt");
            using JsonDocument registryAuthorityDocument = ParseStrictObject(
                registryAuthorityBytes,
                "Registry FINALIZE authority");
            using JsonDocument finalizeDocument = ParseStrictObject(
                finalizeBytes,
                "Registry FINALIZE receipt");
            ValidateRegistryCandidateReceipt(
                candidateReceiptDocument.RootElement,
                candidateReceiptBytes,
                canonicalBytes,
                compatibilityBytes,
                candidate,
                scope);
            ValidateRegistryFinalizeAuthority(
                registryAuthorityDocument.RootElement,
                candidateReceiptBytes,
                canonicalBytes,
                compatibilityBytes,
                scopeDocument.Bytes,
                candidate,
                documents);
            ValidateRegistryFinalizeReceipt(
                finalizeDocument.RootElement,
                registryAuthorityBytes,
                candidateReceiptBytes,
                canonicalBytes,
                compatibilityBytes,
                scopeDocument.Bytes,
                candidate);
            ValidateRegistryFinalizationSummary(
                RequireObject(custody, "registryFinalization"),
                candidateReceiptBytes,
                registryAuthorityBytes,
                finalizeBytes);
        }
        finally
        {
            foreach (CandidateEvidenceDocument evidence in documents.Values)
            {
                evidence.Dispose();
            }
        }
    }

    private static void ValidateFinalScopeTuple(
        JsonElement row,
        string role,
        string platform,
        string rid)
    {
        var keys = new HashSet<string>(
            [
                "artifactRole",
                "consumerCommit",
                "fileName",
                "head",
                "manifestRowSha256",
                "path",
                "platform",
                "rid",
                "sha256",
                "sizeBytes",
                "sourceReceipt"
            ],
            StringComparer.Ordinal);
        if (!ExactPropertySet(row, keys))
        {
            throw new InvalidDataException("candidate final scope tuple property set drifted");
        }
        RequireExactString(row, "head", "avalonia");
        RequireExactString(row, "artifactRole", role);
        RequireExactString(row, "platform", platform);
        RequireExactString(row, "rid", rid);
        if (!CommitPattern.IsMatch(RequireString(row, "consumerCommit")))
        {
            throw new InvalidDataException("candidate final scope tuple commit drifted");
        }
        _ = RequireSha256(row, "manifestRowSha256");
        _ = RequireSha256(row, "sha256");
        long size = RequireNonNegativeInt64(row, "sizeBytes");
        string fileName = RequireString(row, "fileName");
        string path = RequireString(row, "path");
        if (size <= 0
            || !IsCanonicalRelativePath(path)
            || !string.Equals(path, $"files/{fileName}", StringComparison.Ordinal))
        {
            throw new InvalidDataException("candidate final scope tuple byte binding drifted");
        }
        JsonElement source = RequireObject(row, "sourceReceipt");
        if (!ExactPropertySet(
                source,
                new HashSet<string>(
                    ["contractName", "contractVersion", "path", "sha256"],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException("candidate final scope source receipt drifted");
        }
        _ = RequireString(source, "contractName");
        _ = RequirePositiveInt32(source, "contractVersion");
        if (!IsCanonicalRelativePath(RequireString(source, "path")))
        {
            throw new InvalidDataException("candidate final scope source path drifted");
        }
        _ = RequireSha256(source, "sha256");
    }

    private static void ValidateFinalScopeArtifact(JsonElement row, CandidateArtifact expected)
    {
        if (!string.Equals(RequireString(row, "path"), expected.Path, StringComparison.Ordinal)
            || !string.Equals(
                RequireString(row, "fileName"),
                expected.FileName,
                StringComparison.Ordinal)
            || !string.Equals(RequireSha256(row, "sha256"), expected.Sha256, StringComparison.Ordinal)
            || RequireNonNegativeInt64(row, "sizeBytes") != expected.SizeBytes)
        {
            throw new InvalidDataException(
                "candidate final scope Windows tuple differs from canonical manifest");
        }
    }

    private static void ValidateFinalScopeInventory(
        JsonElement scope,
        IReadOnlyList<ReleaseUploadCandidateInventoryRow> inventory)
    {
        JsonElement rows = RequireArray(scope, "fullShelfInventory");
        if (rows.GetArrayLength() != inventory.Count)
        {
            throw new InvalidDataException("candidate final scope inventory count drifted");
        }
        var expected = inventory.ToDictionary(static row => row.Path, StringComparer.Ordinal);
        foreach (JsonElement row in rows.EnumerateArray())
        {
            if (!ExactPropertySet(
                    row,
                    new HashSet<string>(
                        ["mode", "path", "sha256", "sizeBytes"],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException("candidate final scope inventory row drifted");
            }
            string path = RequireString(row, "path");
            if (row.GetProperty("mode").ValueKind != JsonValueKind.Number
                || !expected.TryGetValue(path, out ReleaseUploadCandidateInventoryRow? exact)
                || exact != new ReleaseUploadCandidateInventoryRow(
                    path,
                    RequireNonNegativeInt64(row, "sizeBytes"),
                    RequireSha256(row, "sha256")))
            {
                throw new InvalidDataException("candidate final scope inventory byte drifted");
            }
        }
        _ = RequireSha256(scope, "fullShelfInventorySha256");
    }

    private static void ValidatePublicationDigestAlias(
        JsonElement summary,
        JsonElement scope,
        string property,
        CandidateEvidenceDocument document)
    {
        RequireExactString(summary, property, document.Sha256);
        RequireExactString(scope, property, document.Sha256);
    }

    private static void ValidateNativeContractReference(
        JsonElement composite,
        string property,
        string contractName,
        int contractVersion,
        string path,
        CandidateEvidenceDocument document)
    {
        JsonElement reference = RequireObject(composite, property);
        if (!ExactPropertySet(
                reference,
                new HashSet<string>(
                    ["contractName", "contractVersion", "path", "sha256", "sizeBytes"],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                $"candidate native evidence {property} reference property set drifted");
        }
        RequireExactString(reference, "contractName", contractName);
        RequireExactInt32(reference, "contractVersion", contractVersion);
        RequireExactString(reference, "path", path);
        RequireExactString(reference, "sha256", document.Sha256);
        if (RequirePositiveInt64(reference, "sizeBytes") != document.SizeBytes)
        {
            throw new InvalidDataException(
                $"candidate native evidence {property} reference size drifted");
        }
    }

    private static void ValidateFinalNativeEvidenceDocuments(
        IReadOnlyDictionary<string, CandidateEvidenceDocument> documents,
        ReleaseUploadCandidateIdentity candidate,
        JsonElement actors,
        CandidateArtifact installer,
        CandidateNativePackage nativePackage,
        string nativePath,
        string finalizationPath,
        string visualPath,
        string authenticodePath)
    {
        CandidateEvidenceDocument nativeDocument = documents[nativePath];
        CandidateEvidenceDocument finalizationDocument = documents[finalizationPath];
        CandidateEvidenceDocument visualDocument = documents[visualPath];
        CandidateEvidenceDocument authenticodeDocument = documents[authenticodePath];
        JsonElement native = nativeDocument.Root;
        if (!ExactPropertySet(
                native,
                new HashSet<string>(
                    [
                        "archivePath",
                        "archiveSha256",
                        "authenticodeVerification",
                        "candidateProvenance",
                        "captureInventorySha256",
                        "captureSource",
                        "contractName",
                        "contractVersion",
                        "fileCount",
                        "finalizationSha256",
                        "finalizationSource",
                        "finalizedInventorySha256",
                        "githubActionsProvenance",
                        "nativeFinalization",
                        "progressLogSha256",
                        "release",
                        "scopeApproval",
                        "startupReceiptSha256",
                        "status",
                        "treeSha256",
                        "visualProof",
                        "visualProofSha256",
                        "visualReviewers"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "candidate final native wrapper property set drifted");
        }
        RequireExactString(
            native,
            "contractName",
            "chummer6-ui.preview-nightly-native-windows-evidence");
        RequireExactInt32(native, "contractVersion", 1);
        RequireExactString(native, "status", "passed");
        JsonElement release = RequireObject(native, "release");
        RequireExactString(release, "channel", "preview");
        RequireExactString(release, "version", candidate.Version);
        _ = RequireSha256(native, "archiveSha256");
        RequireExactString(
            native,
            "captureInventorySha256",
            nativePackage.CaptureInventorySha256);
        RequireExactString(native, "finalizationSha256", finalizationDocument.Sha256);
        _ = RequireSha256(native, "finalizedInventorySha256");
        _ = RequireSha256(native, "treeSha256");
        _ = RequirePositiveInt64(native, "fileCount");
        if (!IsCanonicalRelativePath(RequireString(native, "archivePath")))
        {
            throw new InvalidDataException("candidate final native archive path drifted");
        }
        ValidateByteReference(
            native,
            "nativeFinalization",
            finalizationPath,
            finalizationDocument.Bytes);
        if (!CryptographicOperations.FixedTimeEquals(
                finalizationDocument.Bytes,
                nativePackage.FinalizationBytes))
        {
            throw new InvalidDataException(
                "candidate final native finalization differs from raw v2 custody");
        }
        ValidateByteReference(native, "visualProof", visualPath, visualDocument.Bytes);

        JsonElement candidateProvenance = RequireObject(native, "candidateProvenance");
        JsonElement nativeCandidate = RequireObject(candidateProvenance, "candidate");
        if (!JsonSemanticEquals(nativeCandidate, nativePackage.Candidate))
        {
            throw new InvalidDataException(
                "candidate final native provenance differs from raw v2 capture");
        }
        RequireExactString(
            nativeCandidate,
            "actor",
            RequireString(actors, "candidateProducer"));
        JsonElement captureSource = RequireObject(native, "captureSource");
        if (!JsonSemanticEquals(captureSource, nativePackage.CaptureSource))
        {
            throw new InvalidDataException(
                "candidate final native capture source differs from raw v2 custody");
        }
        RequireExactString(captureSource, "actor", RequireString(actors, "nativeCapture"));
        JsonElement finalizationSource = RequireObject(native, "finalizationSource");
        if (!JsonSemanticEquals(finalizationSource, nativePackage.FinalizationSource))
        {
            throw new InvalidDataException(
                "candidate final native finalization source differs from raw v2 custody");
        }
        RequireExactString(
            finalizationSource,
            "actor",
            RequireString(actors, "scopeApprover"));
        JsonElement visualDigests = RequireObject(native, "visualProofSha256");
        JsonElement visualReviewers = RequireObject(native, "visualReviewers");
        if (!ExactPropertySet(
                visualDigests,
                new HashSet<string>(["avalonia"], StringComparer.Ordinal))
            || !ExactPropertySet(
                visualReviewers,
                new HashSet<string>(["avalonia"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException("candidate final native visual map drifted");
        }
        RequireExactString(visualDigests, "avalonia", visualDocument.Sha256);
        RequireExactString(
            visualReviewers,
            "avalonia",
            RequireString(actors, "visualReviewer"));
        JsonElement nativeAuthenticode = RequireObject(native, "authenticodeVerification");
        if (!ExactPropertySet(
                nativeAuthenticode,
                new HashSet<string>(
                    [
                        "path",
                        "sha256",
                        "signerCertificateSha256",
                        "signerSpkiSha256",
                        "sizeBytes",
                        "timestampUtc"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "candidate final native Authenticode binding drifted");
        }
        RequireExactString(nativeAuthenticode, "path", authenticodePath);
        RequireExactString(nativeAuthenticode, "sha256", authenticodeDocument.Sha256);
        if (RequirePositiveInt64(nativeAuthenticode, "sizeBytes")
            != authenticodeDocument.SizeBytes)
        {
            throw new InvalidDataException(
                "candidate final native Authenticode size drifted");
        }
        _ = RequireSha256(nativeAuthenticode, "signerCertificateSha256");
        _ = RequireSha256(nativeAuthenticode, "signerSpkiSha256");
        _ = RequireUtcTimestamp(nativeAuthenticode, "timestampUtc");
        if (!JsonSemanticEquals(
                nativeAuthenticode,
                RequireObject(
                    visualDocument.Root,
                    "authenticodeVerification")))
        {
            throw new InvalidDataException(
                "candidate final portable visual Authenticode binding drifted");
        }

        JsonElement finalization = finalizationDocument.Root;
        if (!ExactPropertySet(
                finalization,
                new HashSet<string>(
                    [
                        "authenticodeVerification",
                        "captureInventorySha256",
                        "captureSource",
                        "contractName",
                        "contractVersion",
                        "finalizationSource",
                        "generatedAt",
                        "humanReviewConfirmed",
                        "proofs",
                        "reviewer",
                        "reviewerWasCaptureActor",
                        "scopeApproval",
                        "status"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "candidate final native finalization property set drifted");
        }
        RequireExactString(
            finalization,
            "contractName",
            "chummer6-ui.preview-nightly-native-windows-finalization");
        RequireExactInt32(finalization, "contractVersion", 2);
        RequireExactString(finalization, "status", "passed");
        RequireBoolean(finalization, "humanReviewConfirmed", expected: true);
        RequireBoolean(finalization, "reviewerWasCaptureActor", expected: false);
        RequireExactString(
            finalization,
            "reviewer",
            RequireString(actors, "scopeApprover"));
        RequireExactString(
            finalization,
            "captureInventorySha256",
            RequireSha256(native, "captureInventorySha256"));
        if (!JsonSemanticEquals(RequireObject(finalization, "captureSource"), captureSource)
            || !JsonSemanticEquals(
                RequireObject(finalization, "finalizationSource"),
                finalizationSource))
        {
            throw new InvalidDataException(
                "candidate final native workflow sources drifted");
        }
        _ = RequireUtcTimestamp(finalization, "generatedAt");
        JsonElement proofs = RequireArray(finalization, "proofs");
        if (proofs.GetArrayLength() != 1
            || !ExactPropertySet(
                proofs[0],
                new HashSet<string>(["headId", "path", "sha256"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "candidate final native visual proof binding drifted");
        }
        RequireExactString(proofs[0], "headId", "avalonia");
        RequireExactString(proofs[0], "path", visualPath);
        _ = RequireSha256(proofs[0], "sha256");
        JsonElement finalizationScope = RequireObject(finalization, "scopeApproval");
        if (!ExactPropertySet(
                finalizationScope,
                new HashSet<string>(
                    ["approver", "path", "scopeDecisionSha256", "sha256"],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "candidate final native scope approval property set drifted");
        }
        RequireExactString(
            finalizationScope,
            "approver",
            RequireString(actors, "scopeApprover"));
        RequireExactString(
            finalizationScope,
            "path",
            "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_APPROVAL.generated.json");
        _ = RequireSha256(finalizationScope, "scopeDecisionSha256");
        _ = RequireSha256(finalizationScope, "sha256");

        JsonElement visual = visualDocument.Root;
        if (!ExactPropertySet(
                visual,
                new HashSet<string>(
                    [
                        "artifactDigest",
                        "artifactFileName",
                        "authenticodeVerification",
                        "captureBinding",
                        "channel",
                        "channelId",
                        "checks",
                        "clippingReview",
                        "contractName",
                        "contractVersion",
                        "contrastReview",
                        "finalizationBinding",
                        "generatedAt",
                        "head",
                        "headId",
                        "platform",
                        "readabilityReview",
                        "releaseVersion",
                        "review",
                        "rid",
                        "screenshots",
                        "status",
                        "version"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "candidate final portable visual proof property set drifted");
        }
        RequireExactString(
            visual,
            "contractName",
            "chummer6-ui.windows_installer_visual_proof");
        RequireExactInt32(visual, "contractVersion", 1);
        RequireExactString(visual, "status", "passed");
        RequireExactString(visual, "version", candidate.Version);
        RequireExactString(visual, "releaseVersion", candidate.Version);
        RequireExactString(visual, "channel", "preview");
        RequireExactString(visual, "channelId", "preview");
        RequireExactString(visual, "head", "avalonia");
        RequireExactString(visual, "headId", "avalonia");
        RequireExactString(visual, "platform", "windows");
        RequireExactString(visual, "rid", WindowsRid);
        RequireExactString(visual, "artifactFileName", installer.FileName);
        RequireExactString(
            visual,
            "artifactDigest",
            $"sha256:{installer.Sha256}");
        _ = RequireUtcTimestamp(visual, "generatedAt");
        JsonElement checks = RequireObject(visual, "checks");
        if (!ExactPropertySet(
                checks,
                new HashSet<string>(
                    ["capture_mode", "human_review_confirmed"],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "candidate final portable visual checks property set drifted");
        }
        RequireExactString(checks, "capture_mode", "interactive");
        RequireBoolean(checks, "human_review_confirmed", expected: true);
        string visualReviewer = RequireString(actors, "visualReviewer");
        ValidatePassedReview(visual, "readabilityReview", visualReviewer);
        ValidatePassedReview(visual, "contrastReview", visualReviewer);
        ValidatePassedReview(visual, "clippingReview", visualReviewer);
        JsonElement review = RequireObject(visual, "review");
        if (!ExactPropertySet(
                review,
                new HashSet<string>(
                    [
                        "allowlistSource",
                        "authenticatedReviewer",
                        "captureActor",
                        "explicitConfirmations"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "candidate final portable visual review property set drifted");
        }
        RequireExactString(
            review,
            "authenticatedReviewer",
            visualReviewer);
        RequireExactString(
            review,
            "captureActor",
            RequireString(actors, "nativeCapture"));
        RequireExactString(
            review,
            "allowlistSource",
            "repository variable plus protected environment");
        JsonElement confirmations = RequireObject(review, "explicitConfirmations");
        if (!ExactPropertySet(
                confirmations,
                new HashSet<string>(
                    ["clipping", "contrast", "readability"],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "candidate final portable visual confirmations property set drifted");
        }
        foreach (string confirmation in new[] { "clipping", "contrast", "readability" })
        {
            RequireExactString(confirmations, confirmation, "passed");
        }
        JsonElement captureBinding = RequireObject(visual, "captureBinding");
        var captureBindingKeys = new HashSet<string>(
            [
                "artifactName",
                "inventorySha256",
                "ref",
                "repository",
                "runAttempt",
                "runId",
                "sha",
                "workflow"
            ],
            StringComparer.Ordinal);
        if (!ExactPropertySet(captureBinding, captureBindingKeys))
        {
            throw new InvalidDataException(
                "candidate final portable visual capture binding property set drifted");
        }
        foreach (string property in captureBindingKeys.Where(
                     static name => name != "inventorySha256"))
        {
            RequireExactString(
                captureBinding,
                property,
                RequireString(nativePackage.CaptureSource, property));
        }
        RequireExactString(
            captureBinding,
            "inventorySha256",
            nativePackage.CaptureInventorySha256);
        if (!JsonSemanticEquals(
                RequireObject(visual, "finalizationBinding"),
                finalizationSource))
        {
            throw new InvalidDataException(
                "candidate final native visual finalization binding drifted");
        }
        JsonElement screenshots = RequireArray(visual, "screenshots");
        if (screenshots.GetArrayLength() != nativePackage.Screenshots.Count)
        {
            throw new InvalidDataException(
                "candidate final portable visual screenshot count drifted");
        }
        string? previousDigest = null;
        for (int index = 0; index < nativePackage.Screenshots.Count; index++)
        {
            JsonElement screenshot = screenshots[index];
            CandidateScreenshotBinding rawScreenshot = nativePackage.Screenshots[index];
            if (!ExactPropertySet(
                    screenshot,
                    new HashSet<string>(["path", "role", "sha256"], StringComparer.Ordinal)))
            {
                throw new InvalidDataException(
                    "candidate final portable visual screenshot property set drifted");
            }
            RequireExactString(screenshot, "role", rawScreenshot.Role);
            RequireExactString(
                screenshot,
                "path",
                $"proof/windows-native/{rawScreenshot.Path}");
            string digest = RequireSha256(screenshot, "sha256");
            if (!string.Equals(digest, rawScreenshot.Sha256, StringComparison.Ordinal)
                || string.Equals(previousDigest, digest, StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    "candidate final portable visual screenshot digest drifted");
            }
            previousDigest = digest;
        }

        foreach (string property in new[]
                 {
                     "sha256",
                     "signerCertificateSha256",
                     "signerSpkiSha256",
                     "timestampUtc"
                 })
        {
            RequireExactString(
                nativeAuthenticode,
                property,
                RequireString(nativePackage.AuthenticodeVerification, property));
        }
        if (RequirePositiveInt64(nativeAuthenticode, "sizeBytes")
            != RequirePositiveInt64(nativePackage.AuthenticodeVerification, "sizeBytes"))
        {
            throw new InvalidDataException(
                "candidate final portable Authenticode size differs from raw v2 custody");
        }
    }

    private static void ValidateRegistryCandidateReceipt(
        JsonElement receipt,
        byte[] receiptBytes,
        byte[] canonicalBytes,
        byte[] compatibilityBytes,
        ReleaseUploadCandidateIdentity candidate,
        JsonElement scope)
    {
        if (!ExactPropertySet(
                receipt,
                new HashSet<string>(
                    [
                        "canonicalManifest",
                        "channel",
                        "compatibilityManifest",
                        "compositionInput",
                        "compositionInputDocument",
                        "contractName",
                        "contractVersion",
                        "deltaPlatforms",
                        "deployAuthority",
                        "evidencePlatforms",
                        "fullShelfInventory",
                        "fullShelfInventorySha256",
                        "incumbentDesktopTupleSetSha256",
                        "incumbentCanonicalManifestBytesBase64",
                        "incumbentSnapshotSha256",
                        "nonPublishedEvidenceTupleSetSha256",
                        "postPublicationTupleSetSha256",
                        "publicationDeltaTupleSetSha256",
                        "publicationEligible",
                        "publicationStatus",
                        "registryProjectionInputs",
                        "releaseUploadAuthority",
                        "routeAuthority",
                        "releaseVersion",
                        "retainedPlatforms",
                        "retainedTupleSetSha256",
                        "shelfPlatforms"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "Registry PREPARE candidate property set drifted");
        }
        RequireExactString(
            receipt,
            "contractName",
            "chummer.registry.preview-publication-delta-candidate");
        RequireExactInt32(receipt, "contractVersion", 1);
        RequireExactString(receipt, "channel", "preview");
        RequireExactString(receipt, "releaseVersion", candidate.Version);
        RequireExactString(receipt, "publicationStatus", "review_required");
        RequireBoolean(receipt, "publicationEligible", expected: false);
        RequireBoolean(receipt, "releaseUploadAuthority", expected: false);
        RequireBoolean(receipt, "deployAuthority", expected: false);
        RequireBoolean(receipt, "routeAuthority", expected: false);
        ValidateExactStringArray(receipt, "deltaPlatforms", ["windows"]);
        ValidateExactStringArray(receipt, "evidencePlatforms", ["linux"]);
        ValidateByteReference(
            receipt,
            "canonicalManifest",
            "RELEASE_CHANNEL.generated.json",
            canonicalBytes);
        ValidateByteReference(
            receipt,
            "compatibilityManifest",
            "releases.json",
            compatibilityBytes);
        _ = RequireSha256(receipt, "fullShelfInventorySha256");
        _ = RequireSha256(receipt, "incumbentDesktopTupleSetSha256");
        _ = RequireSha256(receipt, "incumbentSnapshotSha256");
        _ = RequireSha256(receipt, "nonPublishedEvidenceTupleSetSha256");
        _ = RequireSha256(receipt, "postPublicationTupleSetSha256");
        _ = RequireSha256(receipt, "publicationDeltaTupleSetSha256");
        _ = RequireSha256(receipt, "retainedTupleSetSha256");
        JsonElement projectionInputs = RequireObject(receipt, "registryProjectionInputs");
        var projectionPaths = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["materializer"] = "scripts/materialize_preview_publication_delta.py",
            ["releaseChannelMaterializer"] = "scripts/materialize_public_release_channel.py",
            ["schema"] = "contracts/preview-publication-delta-v1.schema.json",
            ["verifier"] = "scripts/verify_public_release_channel.py"
        };
        if (!ExactPropertySet(
                projectionInputs,
                new HashSet<string>(projectionPaths.Keys, StringComparer.Ordinal)))
        {
            throw new InvalidDataException("Registry projection input property set drifted");
        }
        foreach ((string name, string path) in projectionPaths)
        {
            ValidateByteReferenceShape(
                RequireObject(projectionInputs, name),
                path,
                $"Registry projection {name}");
        }
        JsonElement prepare = RequireObject(scope, "registryPrepare");
        RequireExactString(prepare, "candidateReceiptSha256", Sha256(receiptBytes));
        RequireExactString(prepare, "status", "review_required");
        RequireBoolean(prepare, "wholeDirectoryVerified", expected: true);
        RequireBoolean(prepare, "finalizeAvailable", expected: true);
        if (!prepare.TryGetProperty("finalizeReceipt", out JsonElement unavailableFinalize)
            || unavailableFinalize.ValueKind != JsonValueKind.Null)
        {
            throw new InvalidDataException(
                "Registry PREPARE binding claims an early finalize receipt");
        }
        foreach (string name in new[]
                 {
                     "publicationEligible",
                     "releaseUploadAuthority",
                     "deployAuthority",
                     "routeAuthority"
                 })
        {
            RequireBoolean(prepare, name, expected: false);
        }
    }

    private static void ValidateRegistryFinalizeAuthority(
        JsonElement authority,
        byte[] candidateReceiptBytes,
        byte[] canonicalBytes,
        byte[] compatibilityBytes,
        byte[] scopeBytes,
        ReleaseUploadCandidateIdentity candidate,
        IReadOnlyDictionary<string, CandidateEvidenceDocument> evidenceDocuments)
    {
        if (!ExactPropertySet(
                authority,
                new HashSet<string>(
                    [
                        "candidateImportAuthority",
                        "candidateReceipt",
                        "candidateReviewAuthority",
                        "canonicalManifest",
                        "channel",
                        "compatibilityManifest",
                        "compositionInputSha256",
                        "contractName",
                        "contractVersion",
                        "deltaPlatforms",
                        "deployAuthority",
                        "dispositions",
                        "evidence",
                        "evidencePlatforms",
                        "fullShelfInventorySha256",
                        "incumbentSnapshotSha256",
                        "nonPublishedEvidenceTupleSetSha256",
                        "postPublicationTupleSetSha256",
                        "publicationDeltaTupleSetSha256",
                        "publicationEligible",
                        "releaseUploadAuthority",
                        "releaseVersion",
                        "retainedPlatforms",
                        "retainedTupleSetSha256",
                        "routeAuthority",
                        "scope",
                        "shelfPlatforms",
                        "sourceScope"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException("Registry FINALIZE authority property set drifted");
        }
        RequireExactString(
            authority,
            "contractName",
            "chummer.registry.preview-publication-delta-authority");
        RequireExactInt32(authority, "contractVersion", 1);
        RequireExactString(authority, "channel", "preview");
        RequireExactString(authority, "releaseVersion", candidate.Version);
        RequireExactString(authority, "scope", "windows_only");
        RequireBoolean(authority, "candidateImportAuthority", expected: true);
        RequireBoolean(authority, "candidateReviewAuthority", expected: true);
        RequireBoolean(authority, "publicationEligible", expected: false);
        RequireBoolean(authority, "releaseUploadAuthority", expected: false);
        RequireBoolean(authority, "deployAuthority", expected: false);
        RequireBoolean(authority, "routeAuthority", expected: false);
        ValidateExactStringArray(authority, "deltaPlatforms", ["windows"]);
        ValidateExactStringArray(authority, "evidencePlatforms", ["linux"]);
        ValidateByteReference(
            authority,
            "candidateReceipt",
            "PREVIEW_PUBLICATION_DELTA_CANDIDATE.json",
            candidateReceiptBytes);
        ValidateByteReference(
            authority,
            "canonicalManifest",
            "RELEASE_CHANNEL.generated.json",
            canonicalBytes);
        ValidateByteReference(
            authority,
            "compatibilityManifest",
            "releases.json",
            compatibilityBytes);
        ValidateByteReference(
            authority,
            "sourceScope",
            "PREVIEW_NIGHTLY_PUBLICATION_SCOPE.generated.json",
            scopeBytes);
        _ = RequireSha256(authority, "compositionInputSha256");
        foreach (string property in new[]
                 {
                     "fullShelfInventorySha256",
                     "incumbentSnapshotSha256",
                     "nonPublishedEvidenceTupleSetSha256",
                     "postPublicationTupleSetSha256",
                     "publicationDeltaTupleSetSha256",
                     "retainedTupleSetSha256"
                 })
        {
            _ = RequireSha256(authority, property);
        }
        JsonElement dispositions = RequireArray(authority, "dispositions");
        int deltaCount = 0;
        foreach (JsonElement row in dispositions.EnumerateArray())
        {
            if (!ExactPropertySet(
                    row,
                    new HashSet<string>(
                        [
                            "artifactId",
                            "disposition",
                            "head",
                            "platform",
                            "rid",
                            "sha256",
                            "sizeBytes",
                            "sourceManifestSha256",
                            "sourceReleaseVersion",
                            "sourceSnapshotSha256"
                        ],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException(
                    "Registry FINALIZE disposition property set drifted");
            }
            string disposition = RequireString(row, "disposition");
            if (disposition == "delta")
            {
                deltaCount++;
                RequireExactString(row, "platform", "windows");
                RequireExactString(row, "rid", WindowsRid);
            }
            else if (disposition == "retained_incumbent")
            {
                string platform = RequireString(row, "platform");
                if (platform is not "linux" and not "macos")
                {
                    throw new InvalidDataException(
                        "Registry retained disposition is not non-Windows");
                }
            }
            else
            {
                throw new InvalidDataException("Registry disposition is invalid");
            }
            RequireExactString(row, "head", "avalonia");
            _ = RequireString(row, "artifactId");
            _ = RequireSha256(row, "sha256");
            _ = RequirePositiveInt64(row, "sizeBytes");
            _ = RequireSha256(row, "sourceManifestSha256");
            _ = RequireString(row, "sourceReleaseVersion");
            _ = RequireSha256(row, "sourceSnapshotSha256");
        }
        if (dispositions.GetArrayLength() == 0 || deltaCount != 1)
        {
            throw new InvalidDataException(
                "Registry FINALIZE authority lacks one Windows delta");
        }
        JsonElement evidence = RequireObject(authority, "evidence");
        if (!ExactPropertySet(
                evidence,
                new HashSet<string>(
                    ["approval", "nativeEvidence", "signingReceipt", "visualEvidence"],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException("Registry FINALIZE evidence set drifted");
        }
        ValidateEvidenceByteReference(
            evidence,
            "approval",
            evidenceDocuments);
        ValidateEvidenceByteReference(
            evidence,
            "nativeEvidence",
            evidenceDocuments);
        ValidateEvidenceByteReference(
            evidence,
            "signingReceipt",
            evidenceDocuments);
        JsonElement visuals = RequireArray(evidence, "visualEvidence");
        if (visuals.GetArrayLength() != 1)
        {
            throw new InvalidDataException("Registry FINALIZE visual evidence set drifted");
        }
        ValidateEvidenceByteReference(visuals[0], evidenceDocuments, "Registry visual evidence");
    }

    private static void ValidateRegistryFinalizeReceipt(
        JsonElement receipt,
        byte[] authorityBytes,
        byte[] candidateReceiptBytes,
        byte[] canonicalBytes,
        byte[] compatibilityBytes,
        byte[] scopeBytes,
        ReleaseUploadCandidateIdentity candidate)
    {
        if (!ExactPropertySet(
                receipt,
                new HashSet<string>(
                    [
                        "authority",
                        "candidateBytesMutated",
                        "candidateImportAuthority",
                        "candidateReceipt",
                        "candidateReviewAuthority",
                        "canonicalManifest",
                        "channel",
                        "compatibilityManifest",
                        "contractName",
                        "contractVersion",
                        "deployAuthority",
                        "fullShelfInventorySha256",
                        "publicationEligible",
                        "releaseUploadAuthority",
                        "releaseVersion",
                        "routeAuthority",
                        "sourceScope",
                        "verificationStatus"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException("Registry FINALIZE receipt property set drifted");
        }
        RequireExactString(
            receipt,
            "contractName",
            "chummer.registry.preview-publication-delta-finalize");
        RequireExactInt32(receipt, "contractVersion", 1);
        RequireExactString(receipt, "channel", "preview");
        RequireExactString(receipt, "releaseVersion", candidate.Version);
        RequireExactString(receipt, "verificationStatus", "finalized");
        RequireBoolean(receipt, "candidateBytesMutated", expected: false);
        RequireBoolean(receipt, "candidateImportAuthority", expected: true);
        RequireBoolean(receipt, "candidateReviewAuthority", expected: true);
        RequireBoolean(receipt, "publicationEligible", expected: false);
        RequireBoolean(receipt, "releaseUploadAuthority", expected: false);
        RequireBoolean(receipt, "deployAuthority", expected: false);
        RequireBoolean(receipt, "routeAuthority", expected: false);
        _ = RequireSha256(receipt, "fullShelfInventorySha256");
        ValidateByteReference(
            receipt,
            "authority",
            "PREVIEW_PUBLICATION_DELTA_AUTHORITY.json",
            authorityBytes);
        ValidateByteReference(
            receipt,
            "candidateReceipt",
            "PREVIEW_PUBLICATION_DELTA_CANDIDATE.json",
            candidateReceiptBytes);
        ValidateByteReference(
            receipt,
            "canonicalManifest",
            "RELEASE_CHANNEL.generated.json",
            canonicalBytes);
        ValidateByteReference(
            receipt,
            "compatibilityManifest",
            "releases.json",
            compatibilityBytes);
        ValidateByteReference(
            receipt,
            "sourceScope",
            "PREVIEW_NIGHTLY_PUBLICATION_SCOPE.generated.json",
            scopeBytes);
    }

    private static void ValidateRegistryFinalizationSummary(
        JsonElement summary,
        byte[] candidateReceiptBytes,
        byte[] authorityBytes,
        byte[] finalizeBytes)
    {
        if (!ExactPropertySet(
                summary,
                new HashSet<string>(
                    [
                        "status",
                        "candidateImportAuthority",
                        "candidateReviewAuthority",
                        "publicationEligible",
                        "releaseUploadAuthority",
                        "deployAuthority",
                        "routeAuthority",
                        "scope",
                        "exactIncomingDesktopScope",
                        "candidateReceiptSha256",
                        "authoritySha256",
                        "finalizeReceiptSha256"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException("Registry finalization summary property set drifted");
        }
        RequireExactString(summary, "status", "finalized");
        RequireExactString(summary, "scope", "windows_only");
        RequireExactString(
            summary,
            "exactIncomingDesktopScope",
            CandidateExactIncomingDesktopScope);
        RequireBoolean(summary, "candidateImportAuthority", expected: true);
        RequireBoolean(summary, "candidateReviewAuthority", expected: true);
        RequireBoolean(summary, "publicationEligible", expected: false);
        RequireBoolean(summary, "releaseUploadAuthority", expected: false);
        RequireBoolean(summary, "deployAuthority", expected: false);
        RequireBoolean(summary, "routeAuthority", expected: false);
        RequireExactString(summary, "candidateReceiptSha256", Sha256(candidateReceiptBytes));
        RequireExactString(summary, "authoritySha256", Sha256(authorityBytes));
        RequireExactString(summary, "finalizeReceiptSha256", Sha256(finalizeBytes));
    }

    private static void ValidateExactStringArray(
        JsonElement parent,
        string property,
        IReadOnlyList<string> expected)
    {
        JsonElement values = RequireArray(parent, property);
        string[] actual = values.EnumerateArray().Select(value =>
            value.ValueKind == JsonValueKind.String && value.GetString() is { } text
                ? text
                : throw new InvalidDataException($"{property} contains a non-string")).ToArray();
        if (!actual.SequenceEqual(expected, StringComparer.Ordinal))
        {
            throw new InvalidDataException($"{property} scope drifted");
        }
    }

    private static void ValidateByteReference(
        JsonElement parent,
        string property,
        string expectedPath,
        byte[] expectedBytes)
    {
        JsonElement reference = RequireObject(parent, property);
        ValidateByteReferenceShape(reference, expectedPath, property);
        RequireExactString(reference, "sha256", Sha256(expectedBytes));
        if (RequirePositiveInt64(reference, "sizeBytes") != expectedBytes.LongLength)
        {
            throw new InvalidDataException($"{property} byte-reference size drifted");
        }
    }

    private static void ValidateByteReferenceShape(
        JsonElement reference,
        string expectedPath,
        string label)
    {
        if (!ExactPropertySet(
                reference,
                new HashSet<string>(["path", "sha256", "sizeBytes"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException($"{label} byte-reference property set drifted");
        }
        RequireExactString(reference, "path", expectedPath);
        _ = RequireSha256(reference, "sha256");
        _ = RequirePositiveInt64(reference, "sizeBytes");
    }

    private static void ValidateEvidenceByteReference(
        JsonElement parent,
        string property,
        IReadOnlyDictionary<string, CandidateEvidenceDocument> documents)
        => ValidateEvidenceByteReference(
            RequireObject(parent, property),
            documents,
            $"Registry evidence {property}");

    private static void ValidateEvidenceByteReference(
        JsonElement reference,
        IReadOnlyDictionary<string, CandidateEvidenceDocument> documents,
        string label)
    {
        if (!ExactPropertySet(
                reference,
                new HashSet<string>(["path", "sha256", "sizeBytes"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException($"{label} byte-reference property set drifted");
        }
        string path = RequireString(reference, "path");
        if (!documents.TryGetValue(path, out CandidateEvidenceDocument? document))
        {
            throw new InvalidDataException($"{label} is absent from final UI custody");
        }
        RequireExactString(reference, "sha256", document.Sha256);
        if (RequirePositiveInt64(reference, "sizeBytes") != document.SizeBytes)
        {
            throw new InvalidDataException($"{label} size drifted");
        }
    }

    private static CandidateNativePackage ValidateCandidateNativeEvidence(
        JsonElement native,
        JsonElement canonical,
        ReleaseUploadCandidateIdentity candidate,
        IReadOnlyList<ReleaseUploadCandidateInventoryRow> candidateInventory,
        DateTimeOffset now)
    {
        var requiredNative = new HashSet<string>(
            [
                "status",
                "captureGeneratedAtUtc",
                "finalizationGeneratedAtUtc",
                "reviewer",
                "captureSource",
                "finalizationSource",
                "candidateContentInventorySha256",
                "candidateContentInventory",
                "files"
            ],
            StringComparer.Ordinal);
        if (!ExactPropertySet(native, requiredNative))
        {
            throw new InvalidDataException("candidate native-Windows custody property set drifted");
        }
        RequireExactString(native, "status", "passed");
        string reviewer = RequireString(native, "reviewer");
        if (!ReviewerPattern.IsMatch(reviewer))
        {
            throw new InvalidDataException("candidate native-Windows reviewer is invalid");
        }
        DateTimeOffset summaryCaptureAt = RequireFreshUtcTimestamp(
            native,
            "captureGeneratedAtUtc",
            now);
        DateTimeOffset summaryFinalizationAt = RequireFreshUtcTimestamp(
            native,
            "finalizationGeneratedAtUtc",
            now);
        JsonElement captureSource = RequireObject(native, "captureSource");
        JsonElement finalizationSource = RequireObject(native, "finalizationSource");
        ValidateEvidenceSource(captureSource, "candidate capture source", CaptureWorkflow);
        ValidateEvidenceSource(
            finalizationSource,
            "candidate finalization source",
            FinalizationWorkflow);
        if (!string.Equals(
                RequireString(captureSource, "actor"),
                "github-actions[bot]",
                StringComparison.Ordinal)
            || !string.Equals(
                RequireString(finalizationSource, "actor"),
                reviewer,
                StringComparison.Ordinal)
            || string.Equals(reviewer, RequireString(captureSource, "actor"), StringComparison.Ordinal)
            || !string.Equals(
                RequireString(captureSource, "sha"),
                RequireString(finalizationSource, "sha"),
                StringComparison.Ordinal))
        {
            throw new InvalidDataException("candidate protected reviewer provenance drifted");
        }

        JsonElement files = RequireArray(native, "files");
        var documents = new Dictionary<string, CandidateEvidenceDocument>(StringComparer.Ordinal);
        try
        {
            foreach (JsonElement entry in files.EnumerateArray())
            {
                string path = RequireString(entry, "path");
                if (!IsCanonicalRelativePath(path) || documents.ContainsKey(path))
                {
                    throw new InvalidDataException("candidate native-Windows evidence path drifted");
                }
                byte[] bytes = DecodeEmbedded(
                    entry,
                    $"candidate native-Windows {path}",
                    path);
                documents.Add(
                    path,
                    new CandidateEvidenceDocument(
                        ParseStrictObject(bytes, $"candidate native-Windows {path}"),
                        bytes,
                        RequireSha256(entry, "sha256"),
                        RequireNonNegativeInt64(entry, "sizeBytes")));
            }

            CandidateWindowsScope scope = ParseCandidateWindowsScope(
                canonical,
                candidate,
                candidateInventory);
            var fixedPaths = new HashSet<string>(
                [
                    CaptureFileName,
                    CaptureInventoryFileName,
                    FinalizationFileName,
                    FinalizedInventoryFileName,
                    CandidateProvenanceInventoryFileName,
                    CandidateProvenanceExportFileName,
                    .. scope.Heads.Select(
                        head => $"startup-smoke/startup-smoke-{head}-{WindowsRid}.receipt.json")
                ],
                StringComparer.Ordinal);
            if (!fixedPaths.IsSubsetOf(documents.Keys))
            {
                throw new InvalidDataException("candidate native-Windows custody is incomplete");
            }

            JsonElement finalizedInventory = documents[FinalizedInventoryFileName].Root;
            if (!ExactPropertySet(
                    finalizedInventory,
                    new HashSet<string>(
                        ["contractName", "contractVersion", "captureInventorySha256", "files"],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException(
                    "candidate finalized native-Windows inventory property set drifted");
            }
            RequireExactString(
                finalizedInventory,
                "contractName",
                "chummer6-ui.preview-nightly-native-windows-finalized-inventory");
            RequireExactInt32(finalizedInventory, "contractVersion", 1);
            IReadOnlyList<ReleaseUploadCandidateInventoryRow> finalizedRows =
                ParseEvidenceInventoryRows(
                    RequireArray(finalizedInventory, "files"),
                    "candidate finalized native-Windows inventory",
                    allowEmpty: false);
            var finalizedByPath = finalizedRows.ToDictionary(static row => row.Path, StringComparer.Ordinal);
            foreach ((string path, CandidateEvidenceDocument evidence) in documents)
            {
                if (string.Equals(path, FinalizedInventoryFileName, StringComparison.Ordinal))
                {
                    continue;
                }
                if (!finalizedByPath.TryGetValue(path, out ReleaseUploadCandidateInventoryRow? row)
                    || row != new ReleaseUploadCandidateInventoryRow(
                        path,
                        evidence.SizeBytes,
                        evidence.Sha256))
                {
                    throw new InvalidDataException(
                        "candidate embedded evidence disagrees with finalized inventory");
                }
            }

            CandidateEvidenceDocument provenanceDocument =
                documents[CandidateProvenanceInventoryFileName];
            JsonElement provenance = provenanceDocument.Root;
            RequireExactString(
                provenance,
                "contractName",
                "chummer6-ui.preview-nightly-candidate-content-inventory");
            RequireExactInt32(provenance, "contractVersion", 2);
            JsonElement release = RequireObject(provenance, "release");
            RequireExactString(release, "channel", scope.Channel);
            RequireExactString(release, "version", scope.Version);
            JsonElement manifest = RequireObject(provenance, "manifest");
            RequireExactString(manifest, "path", "RELEASE_CHANNEL.generated.json");
            RequireExactString(manifest, "sha256", candidate.CanonicalManifestSha256);
            IReadOnlyList<ReleaseUploadCandidateInventoryRow> provenanceRows =
                ParseEvidenceInventoryRows(
                    RequireArray(provenance, "files"),
                    "candidate native-Windows content inventory",
                    allowEmpty: false);
            if (!JsonSemanticEquals(
                    provenance,
                    RequireObject(native, "candidateContentInventory"))
                || !string.Equals(
                    Sha256(provenanceDocument.Bytes),
                    RequireSha256(native, "candidateContentInventorySha256"),
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    "candidate native-Windows content inventory binding drifted");
            }
            var candidateByPath = candidateInventory.ToDictionary(static row => row.Path, StringComparer.Ordinal);
            var provenanceByPath = provenanceRows.ToDictionary(
                static row => row.Path,
                StringComparer.Ordinal);
            if (candidateByPath.Any(pair =>
                    !provenanceByPath.TryGetValue(
                        pair.Key,
                        out ReleaseUploadCandidateInventoryRow? exact)
                    || exact != pair.Value))
            {
                throw new InvalidDataException("candidate native-Windows content bytes drifted");
            }
            CandidateEvidenceDocument captureDocument = documents[CaptureFileName];
            JsonElement capture = captureDocument.Root;
            if (!ExactPropertySet(
                    capture,
                    new HashSet<string>(
                        [
                            "authenticodeVerification",
                            "candidate",
                            "captureMode",
                            "channelId",
                            "contractName",
                            "contractVersion",
                            "generatedAt",
                            "heads",
                            "source",
                            "status",
                            "version"
                        ],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException(
                    "candidate Windows-only native capture property set drifted");
            }
            RequireExactString(
                capture,
                "contractName",
                "chummer6-ui.preview-nightly-native-windows-capture");
            RequireExactInt32(capture, "contractVersion", 2);
            RequireExactString(capture, "status", "captured");
            RequireExactString(capture, "captureMode", "interactive");
            RequireExactString(capture, "version", scope.Version);
            RequireExactString(capture, "channelId", scope.Channel);
            if (!JsonSemanticEquals(RequireObject(capture, "source"), captureSource)
                || RequireFreshUtcTimestamp(capture, "generatedAt", now) != summaryCaptureAt)
            {
                throw new InvalidDataException("candidate native-Windows capture receipt drifted");
            }
            JsonElement captureCandidate = ValidateCaptureCandidateBinding(
                RequireObject(capture, "candidate"),
                captureSource,
                documents,
                finalizedByPath,
                candidate.CanonicalManifestSha256,
                summaryCaptureAt);
            JsonElement captureAuthenticode = RequireObject(
                capture,
                "authenticodeVerification");
            ValidateAuthenticodeInventoryBinding(
                captureAuthenticode,
                "authenticode/AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json",
                finalizedByPath,
                "candidate capture Authenticode verification");
            IReadOnlyDictionary<string, IReadOnlyList<CandidateScreenshotBinding>>
                captureScreenshots = ValidateCaptureHeads(
                RequireArray(capture, "heads"),
                scope,
                finalizedByPath,
                captureAuthenticode);

            CandidateEvidenceDocument captureInventoryDocument =
                documents[CaptureInventoryFileName];
            JsonElement captureInventory = captureInventoryDocument.Root;
            if (!ExactPropertySet(
                    captureInventory,
                    new HashSet<string>(
                        [
                            "contractName",
                            "contractVersion",
                            "captureContract",
                            "captureManifestSha256",
                            "files"
                        ],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException(
                    "candidate native-Windows capture inventory property set drifted");
            }
            RequireExactString(
                captureInventory,
                "contractName",
                "chummer6-ui.preview-nightly-native-windows-capture-inventory");
            RequireExactInt32(captureInventory, "contractVersion", 2);
            RequireExactString(
                captureInventory,
                "captureContract",
                "chummer6-ui.preview-nightly-native-windows-capture");
            RequireExactString(
                captureInventory,
                "captureManifestSha256",
                Sha256(captureDocument.Bytes));
            IReadOnlyList<ReleaseUploadCandidateInventoryRow> captureRows =
                ParseEvidenceInventoryRows(
                RequireArray(captureInventory, "files"),
                "candidate native-Windows capture inventory",
                allowEmpty: false);
            string[] expectedCapturePaths = finalizedByPath.Keys
                .Where(path => path is not CaptureInventoryFileName
                    and not FinalizationFileName
                    and not "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_APPROVAL.generated.json"
                    && !path.StartsWith(
                        "WINDOWS_INSTALLER_VISUAL_PROOF-",
                        StringComparison.Ordinal))
                .Order(StringComparer.Ordinal)
                .ToArray();
            if (!captureRows.Select(static row => row.Path).SequenceEqual(expectedCapturePaths)
                || captureRows.Any(row =>
                    !finalizedByPath.TryGetValue(
                        row.Path,
                        out ReleaseUploadCandidateInventoryRow? finalizedRow)
                    || finalizedRow != row))
            {
                throw new InvalidDataException(
                    "candidate native-Windows capture inventory differs from its finalized capture tree");
            }
            string captureInventorySha256 = Sha256(captureInventoryDocument.Bytes);
            RequireExactString(
                finalizedInventory,
                "captureInventorySha256",
                captureInventorySha256);

            JsonElement finalization = documents[FinalizationFileName].Root;
            if (!ExactPropertySet(
                    finalization,
                    new HashSet<string>(
                        [
                            "authenticodeVerification",
                            "captureInventorySha256",
                            "captureSource",
                            "contractName",
                            "contractVersion",
                            "finalizationSource",
                            "generatedAt",
                            "humanReviewConfirmed",
                            "proofs",
                            "reviewer",
                            "reviewerWasCaptureActor",
                            "scopeApproval",
                            "status"
                        ],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException(
                    "candidate Windows-only native finalization property set drifted");
            }
            RequireExactString(
                finalization,
                "contractName",
                "chummer6-ui.preview-nightly-native-windows-finalization");
            RequireExactInt32(finalization, "contractVersion", 2);
            RequireExactString(finalization, "status", "passed");
            RequireBoolean(finalization, "humanReviewConfirmed", expected: true);
            RequireBoolean(finalization, "reviewerWasCaptureActor", expected: false);
            RequireExactString(finalization, "reviewer", reviewer);
            RequireExactString(
                finalization,
                "captureInventorySha256",
                captureInventorySha256);
            if (!JsonSemanticEquals(RequireObject(finalization, "captureSource"), captureSource)
                || !JsonSemanticEquals(
                    RequireObject(finalization, "finalizationSource"),
                    finalizationSource)
                || RequireFreshUtcTimestamp(finalization, "generatedAt", now)
                   != summaryFinalizationAt)
            {
                throw new InvalidDataException("candidate native-Windows finalization receipt drifted");
            }
            if (!JsonSemanticEquals(
                    RequireObject(finalization, "authenticodeVerification"),
                    captureAuthenticode))
            {
                throw new InvalidDataException(
                    "candidate native-Windows Authenticode finalization binding drifted");
            }
            JsonElement scopeApproval = RequireObject(finalization, "scopeApproval");
            if (!ExactPropertySet(
                    scopeApproval,
                    new HashSet<string>(
                        ["approver", "path", "scopeDecisionSha256", "sha256"],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException(
                    "candidate native-Windows scope approval binding drifted");
            }
            RequireExactString(scopeApproval, "approver", reviewer);
            RequireExactString(
                scopeApproval,
                "path",
                "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_APPROVAL.generated.json");
            _ = RequireSha256(scopeApproval, "scopeDecisionSha256");
            _ = RequireSha256(scopeApproval, "sha256");
            JsonElement proofs = RequireArray(finalization, "proofs");
            if (proofs.GetArrayLength() != scope.Heads.Count)
            {
                throw new InvalidDataException("candidate visual proof head scope drifted");
            }
            var proofsByHead = new Dictionary<string, CandidateVisualProof>(StringComparer.Ordinal);
            foreach (JsonElement row in proofs.EnumerateArray())
            {
                if (!ExactPropertySet(
                        row,
                        new HashSet<string>(["headId", "path", "sha256"], StringComparer.Ordinal)))
                {
                    throw new InvalidDataException("candidate visual proof binding drifted");
                }
                string head = RequireString(row, "headId");
                string path = RequireString(row, "path");
                if (!scope.Heads.Contains(head, StringComparer.Ordinal)
                    || !IsCanonicalRelativePath(path)
                    || !documents.TryGetValue(path, out CandidateEvidenceDocument? proofDocument)
                    || !proofsByHead.TryAdd(
                        head,
                        new CandidateVisualProof(path, proofDocument.Root, proofDocument.Bytes))
                    || !string.Equals(
                        RequireSha256(row, "sha256"),
                        Sha256(proofDocument.Bytes),
                        StringComparison.Ordinal))
                {
                    throw new InvalidDataException("candidate visual proof head or digest drifted");
                }
            }
            var expectedFinalizedPaths = new HashSet<string>(
                captureRows.Select(static row => row.Path),
                StringComparer.Ordinal)
            {
                CaptureInventoryFileName,
                FinalizationFileName,
                "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_APPROVAL.generated.json"
            };
            expectedFinalizedPaths.UnionWith(
                proofsByHead.Values.Select(static proof => proof.Path));
            if (!expectedFinalizedPaths.SetEquals(finalizedByPath.Keys))
            {
                throw new InvalidDataException(
                    "candidate finalized native-Windows inventory file scope drifted");
            }
            fixedPaths.UnionWith(proofsByHead.Values.Select(static proof => proof.Path));
            if (!fixedPaths.SetEquals(documents.Keys))
            {
                throw new InvalidDataException("candidate native-Windows evidence file scope drifted");
            }

            JsonElement export = documents[CandidateProvenanceExportFileName].Root;
            ValidateCandidateExportReceipt(
                export,
                captureCandidate,
                candidate.CanonicalManifestSha256,
                scope);

            foreach (string head in scope.Heads)
            {
                CandidateHeadArtifacts headArtifacts = scope.Artifacts[head];
                string startupPath =
                    $"startup-smoke/startup-smoke-{head}-{WindowsRid}.receipt.json";
                JsonElement startup = documents[startupPath].Root;
                RequireExactString(startup, "status", "pass");
                RequireExactString(startup, "readyCheckpoint", "pre_ui_event_loop");
                RequireExactString(startup, "executionEnvironment", "native_windows");
                RequireExactString(startup, "headId", head);
                RequireExactString(startup, "platform", "windows");
                RequireExactString(startup, "rid", WindowsRid);
                RequireExactString(startup, "releaseVersion", scope.Version);
                RequireExactString(startup, "channelId", scope.Channel);
                RequireExactString(
                    startup,
                    "artifactFileName",
                    headArtifacts.Installer.FileName);
                RequireExactString(
                    startup,
                    "artifactDigest",
                    $"sha256:{headArtifacts.Installer.Sha256}");
                RequireExactString(startup, "bootstrapPayloadAcquisitionMode", "download");
                RequireExactString(
                    startup,
                    "bootstrapPayloadFileName",
                    headArtifacts.Payload.FileName);
                RequireExactString(
                    startup,
                    "bootstrapPayloadSha256",
                    headArtifacts.Payload.Sha256);
                if (RequireNonNegativeInt64(startup, "bootstrapPayloadSizeBytes")
                    != headArtifacts.Payload.SizeBytes)
                {
                    throw new InvalidDataException("candidate startup payload size drifted");
                }
                JsonElement nativeHost = RequireObject(startup, "nativeHostEvidence");
                RequireExactString(
                    nativeHost,
                    "contractName",
                    "chummer6-ui.native_windows_host_evidence");
                RequireExactString(nativeHost, "status", "verified");
                RequireBoolean(nativeHost, "isNativeWindows", expected: true);
                RequireExactString(nativeHost, "hostPlatform", "windows");
                string runner = RequireString(nativeHost, "runner");
                if (string.IsNullOrWhiteSpace(runner)
                    || runner.Contains("wine", StringComparison.OrdinalIgnoreCase))
                {
                    throw new InvalidDataException("candidate startup runner is not native Windows");
                }

                JsonElement proof = proofsByHead[head].Root;
                if (!ExactPropertySet(
                        proof,
                        new HashSet<string>(
                            [
                                "artifactDigest",
                                "artifactFileName",
                                "authenticodeVerification",
                                "captureBinding",
                                "channel",
                                "channelId",
                                "checks",
                                "clippingReview",
                                "contractName",
                                "contractVersion",
                                "contrastReview",
                                "finalizationBinding",
                                "generatedAt",
                                "head",
                                "headId",
                                "platform",
                                "readabilityReview",
                                "releaseVersion",
                                "review",
                                "rid",
                                "screenshots",
                                "status",
                                "version"
                            ],
                            StringComparer.Ordinal)))
                {
                    throw new InvalidDataException(
                        "candidate raw visual proof property set drifted");
                }
                RequireExactString(
                    proof,
                    "contractName",
                    "chummer6-ui.windows_installer_visual_proof");
                RequireExactInt32(proof, "contractVersion", 1);
                RequireExactString(proof, "status", "passed");
                RequireExactString(proof, "version", scope.Version);
                RequireExactString(proof, "headId", head);
                RequireExactString(proof, "head", head);
                RequireExactString(proof, "platform", "windows");
                RequireExactString(proof, "rid", WindowsRid);
                RequireExactString(proof, "releaseVersion", scope.Version);
                RequireExactString(proof, "channel", scope.Channel);
                RequireExactString(proof, "channelId", scope.Channel);
                RequireExactString(
                    proof,
                    "artifactFileName",
                    headArtifacts.Installer.FileName);
                RequireExactString(
                    proof,
                    "artifactDigest",
                    $"sha256:{headArtifacts.Installer.Sha256}");
                _ = RequireFreshUtcTimestamp(proof, "generatedAt", now);
                JsonElement checks = RequireObject(proof, "checks");
                if (!ExactPropertySet(
                        checks,
                        new HashSet<string>(
                            ["capture_mode", "human_review_confirmed"],
                            StringComparer.Ordinal)))
                {
                    throw new InvalidDataException("candidate visual checks property set drifted");
                }
                RequireExactString(checks, "capture_mode", "interactive");
                RequireBoolean(checks, "human_review_confirmed", expected: true);
                ValidatePassedReview(proof, "readabilityReview", reviewer);
                ValidatePassedReview(proof, "contrastReview", reviewer);
                ValidatePassedReview(proof, "clippingReview", reviewer);
                JsonElement review = RequireObject(proof, "review");
                if (!ExactPropertySet(
                        review,
                        new HashSet<string>(
                            [
                                "authenticatedReviewer",
                                "captureActor",
                                "allowlistSource",
                                "explicitConfirmations"
                            ],
                            StringComparer.Ordinal)))
                {
                    throw new InvalidDataException("candidate visual review property set drifted");
                }
                RequireExactString(review, "authenticatedReviewer", reviewer);
                RequireExactString(
                    review,
                    "captureActor",
                    RequireString(captureSource, "actor"));
                RequireExactString(
                    review,
                    "allowlistSource",
                    "repository variable plus protected environment");
                JsonElement confirmations = RequireObject(
                    review,
                    "explicitConfirmations");
                if (!ExactPropertySet(
                        confirmations,
                        new HashSet<string>(
                            ["readability", "contrast", "clipping"],
                            StringComparer.Ordinal)))
                {
                    throw new InvalidDataException(
                        "candidate visual confirmations property set drifted");
                }
                foreach (string confirmation in new[]
                         {
                             "readability",
                             "contrast",
                             "clipping"
                         })
                {
                    RequireExactString(confirmations, confirmation, "passed");
                }
                JsonElement captureBinding = RequireObject(proof, "captureBinding");
                var captureBindingKeys = new HashSet<string>(
                    [
                        "repository",
                        "workflow",
                        "runId",
                        "runAttempt",
                        "ref",
                        "sha",
                        "artifactName",
                        "inventorySha256"
                    ],
                    StringComparer.Ordinal);
                if (!ExactPropertySet(captureBinding, captureBindingKeys))
                {
                    throw new InvalidDataException(
                        "candidate visual capture binding property set drifted");
                }
                foreach (string property in captureBindingKeys.Where(
                             static name => name != "inventorySha256"))
                {
                    RequireExactString(
                        captureBinding,
                        property,
                        RequireString(captureSource, property));
                }
                RequireExactString(
                    captureBinding,
                    "inventorySha256",
                    Sha256(captureInventoryDocument.Bytes));
                if (!JsonSemanticEquals(
                        RequireObject(proof, "finalizationBinding"),
                        finalizationSource))
                {
                    throw new InvalidDataException("candidate visual finalization binding drifted");
                }
                if (!JsonSemanticEquals(
                        RequireObject(proof, "authenticodeVerification"),
                        captureAuthenticode))
                {
                    throw new InvalidDataException(
                        "candidate visual Authenticode binding drifted");
                }
                JsonElement screenshots = RequireArray(proof, "screenshots");
                if (screenshots.GetArrayLength() != 2)
                {
                    throw new InvalidDataException("candidate visual screenshot set drifted");
                }
                var visualScreenshots = new List<CandidateScreenshotBinding>(2);
                foreach (JsonElement screenshot in screenshots.EnumerateArray())
                {
                    if (!ExactPropertySet(
                            screenshot,
                            new HashSet<string>(["role", "path", "sha256"], StringComparer.Ordinal)))
                    {
                        throw new InvalidDataException("candidate visual screenshot binding drifted");
                    }
                    string role = RequireString(screenshot, "role");
                    string path = RequireString(screenshot, "path");
                    string digest = RequireSha256(screenshot, "sha256");
                    string expectedPath =
                        $"screenshots/windows-installer-{head}-{WindowsRid}-{role}.png";
                    if (role is not "progress" and not "completion"
                        || !IsCanonicalRelativePath(path)
                        || !string.Equals(path, expectedPath, StringComparison.Ordinal)
                        || !finalizedByPath.TryGetValue(
                            path,
                            out ReleaseUploadCandidateInventoryRow? screenshotRow)
                        || !string.Equals(screenshotRow.Sha256, digest, StringComparison.Ordinal))
                    {
                        throw new InvalidDataException("candidate visual screenshot proof drifted");
                    }
                    visualScreenshots.Add(new CandidateScreenshotBinding(role, path, digest));
                }
                if (!visualScreenshots.SequenceEqual(captureScreenshots[head]))
                {
                    throw new InvalidDataException(
                        "candidate visual screenshots differ from the capture head");
                }
            }

            return new CandidateNativePackage(
                captureInventorySha256,
                documents[FinalizationFileName].Bytes.ToArray(),
                captureCandidate.Clone(),
                captureSource.Clone(),
                finalizationSource.Clone(),
                captureAuthenticode.Clone(),
                captureScreenshots["avalonia"].ToArray());
        }
        finally
        {
            foreach (CandidateEvidenceDocument document in documents.Values)
            {
                document.Dispose();
            }
        }
    }

    private static CandidateWindowsScope ParseCandidateWindowsScope(
        JsonElement canonical,
        ReleaseUploadCandidateIdentity candidate,
        IReadOnlyList<ReleaseUploadCandidateInventoryRow> candidateInventory)
    {
        string version = RequireMatchingAlias(
            canonical,
            "version",
            "releaseVersion",
            "candidate release version");
        string channel = RequireMatchingAlias(
            canonical,
            "channelId",
            "channel",
            "candidate release channel");
        if (!string.Equals(version, candidate.Version, StringComparison.Ordinal))
        {
            throw new InvalidDataException("candidate release version differs from its identity");
        }
        JsonElement headsElement = RequireArray(
            RequireObject(canonical, "desktopTupleCoverage"),
            "requiredDesktopHeads");
        var heads = new List<string>();
        var headSet = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonElement headElement in headsElement.EnumerateArray())
        {
            if (headElement.ValueKind != JsonValueKind.String
                || headElement.GetString() is not { } head
                || !HeadPattern.IsMatch(head)
                || !headSet.Add(head))
            {
                throw new InvalidDataException("candidate requiredDesktopHeads is invalid");
            }
            heads.Add(head);
        }
        if (!heads.SequenceEqual(PromotedHeads, StringComparer.Ordinal))
        {
            throw new InvalidDataException(
                "candidate requiredDesktopHeads differs from the promoted Avalonia head");
        }
        JsonElement artifactsElement = RequireArray(canonical, "artifacts");
        var candidateByPath = candidateInventory.ToDictionary(
            static row => row.Path,
            StringComparer.Ordinal);
        var expectedFilePaths = new HashSet<string>(StringComparer.Ordinal);
        var windowsArtifacts = new List<JsonElement>();
        foreach (JsonElement artifact in artifactsElement.EnumerateArray())
        {
            if (artifact.ValueKind != JsonValueKind.Object)
            {
                throw new InvalidDataException(
                    "candidate release manifest contains a non-object artifact");
            }
            if (!artifact.TryGetProperty("head", out JsonElement artifactHead)
                || artifactHead.ValueKind != JsonValueKind.String
                || artifactHead.GetString() is not { } head
                || !headSet.Contains(head))
            {
                throw new InvalidDataException(
                    "candidate release manifest contains a desktop artifact outside "
                    + "requiredDesktopHeads");
            }
            string platform = RequireString(artifact, "platform");
            string rid = RequireString(artifact, "rid");
            if (!HasExactString(artifact, "kind", "installer")
                || (platform switch
                    {
                        "windows" => !string.Equals(rid, WindowsRid, StringComparison.Ordinal),
                        "linux" => !string.Equals(rid, "linux-x64", StringComparison.Ordinal),
                        "macos" => rid is not "osx-arm64" and not "osx-x64",
                        _ => true
                    }))
            {
                throw new InvalidDataException(
                    "candidate release manifest contains an artifact outside "
                    + "the exact finalized desktop shelf scope");
            }
            string fileName = RequireString(artifact, "fileName");
            string digest = RequireSha256(artifact, "sha256");
            long size = RequireNonNegativeInt64(artifact, "sizeBytes");
            string path = $"files/{fileName}";
            if (fileName.Contains('/')
                || fileName.Contains('\\')
                || size <= 0
                || !expectedFilePaths.Add(path)
                || !candidateByPath.TryGetValue(
                    path,
                    out ReleaseUploadCandidateInventoryRow? exact)
                || exact != new ReleaseUploadCandidateInventoryRow(path, size, digest))
            {
                throw new InvalidDataException(
                    "candidate desktop artifact differs from upload inventory");
            }
            if (string.Equals(platform, "windows", StringComparison.Ordinal))
            {
                windowsArtifacts.Add(artifact);
            }
        }
        var artifacts = new Dictionary<string, CandidateHeadArtifacts>(StringComparer.Ordinal);
        foreach (string head in heads)
        {
            JsonElement[] matching = windowsArtifacts
                .Where(artifact => HasExactString(artifact, "head", head))
                .ToArray();
            if (matching.Length != 1)
            {
                throw new InvalidDataException(
                    $"candidate manifest must name one Windows installer row for {head}");
            }
            JsonElement installer = matching[0];
            RequireExactString(installer, "installerMode", "bootstrap");
            RequireExactString(installer, "payloadAcquisitionMode", "download");
            artifacts.Add(
                head,
                new CandidateHeadArtifacts(
                    ParseCandidateArtifact(
                        installer,
                        head,
                        "installer",
                        "fileName",
                        "sha256",
                        "sizeBytes",
                        candidateByPath),
                    ParseCandidateArtifact(
                        installer,
                        head,
                        "payload",
                        "payloadFileName",
                        "payloadSha256",
                        "payloadSizeBytes",
                        candidateByPath)));
        }
        expectedFilePaths.UnionWith(
            artifacts.Values.SelectMany(
                static value => new[] { value.Installer.Path, value.Payload.Path }));
        var expectedCandidatePaths = expectedFilePaths
            .Append("RELEASE_CHANNEL.generated.json")
            .Append("releases.json")
            .ToHashSet(StringComparer.Ordinal);
        var actualCandidatePaths = candidateInventory
            .Select(static row => row.Path)
            .ToHashSet(StringComparer.Ordinal);
        if (!actualCandidatePaths.SetEquals(expectedCandidatePaths))
        {
            throw new InvalidDataException(
                "candidate upload inventory differs from the exact finalized desktop shelf");
        }
        return new CandidateWindowsScope(version, channel, heads, artifacts);
    }

    private static CandidateArtifact ParseCandidateArtifact(
        JsonElement artifact,
        string head,
        string role,
        string fileNameProperty,
        string digestProperty,
        string sizeProperty,
        IReadOnlyDictionary<string, ReleaseUploadCandidateInventoryRow> candidateByPath)
    {
        string fileName = RequireString(artifact, fileNameProperty);
        string digest = RequireSha256(artifact, digestProperty);
        long size = RequireNonNegativeInt64(artifact, sizeProperty);
        if (fileName.Contains('/')
            || fileName.Contains('\\')
            || size <= 0
            || role == "installer" && !fileName.EndsWith(".exe", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException($"candidate {head} {role} metadata is invalid");
        }
        string path = $"files/{fileName}";
        if (!candidateByPath.TryGetValue(path, out ReleaseUploadCandidateInventoryRow? row)
            || row != new ReleaseUploadCandidateInventoryRow(path, size, digest))
        {
            throw new InvalidDataException(
                $"candidate {head} {role} manifest bytes differ from upload inventory");
        }
        return new CandidateArtifact(path, fileName, digest, size);
    }

    private static IReadOnlyDictionary<string, IReadOnlyList<CandidateScreenshotBinding>>
        ValidateCaptureHeads(
        JsonElement heads,
        CandidateWindowsScope scope,
        IReadOnlyDictionary<string, ReleaseUploadCandidateInventoryRow> finalizedByPath,
        JsonElement authenticodeVerification)
    {
        if (heads.GetArrayLength() != PromotedHeads.Length)
        {
            throw new InvalidDataException(
                "candidate capture must contain exactly one Avalonia head");
        }
        var result = new Dictionary<string, IReadOnlyList<CandidateScreenshotBinding>>(
            StringComparer.Ordinal);
        int index = 0;
        foreach (JsonElement row in heads.EnumerateArray())
        {
            string head = PromotedHeads[index++];
            if (!ExactPropertySet(
                    row,
                    new HashSet<string>(
                        [
                            "headId",
                            "rid",
                            "installer",
                            "payload",
                            "receipt",
                            "progressLog",
                            "screenshots",
                            "authenticodeVerification"
                        ],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException("candidate capture head property set drifted");
            }
            RequireExactString(row, "headId", head);
            RequireExactString(row, "rid", WindowsRid);
            CandidateHeadArtifacts artifacts = scope.Artifacts[head];
            ValidateExportArtifactBinding(RequireObject(row, "installer"), artifacts.Installer);
            ValidateExportArtifactBinding(RequireObject(row, "payload"), artifacts.Payload);
            if (!JsonSemanticEquals(
                    RequireObject(row, "authenticodeVerification"),
                    authenticodeVerification))
            {
                throw new InvalidDataException(
                    "candidate capture head Authenticode binding drifted");
            }

            ValidateCaptureEvidenceBinding(
                RequireObject(row, "receipt"),
                $"startup-smoke/startup-smoke-{head}-{WindowsRid}.receipt.json",
                finalizedByPath,
                "candidate capture startup receipt");
            ValidateCaptureEvidenceBinding(
                RequireObject(row, "progressLog"),
                $"startup-smoke/windows-installer-progress-{head}-{WindowsRid}.log",
                finalizedByPath,
                "candidate capture progress log");

            JsonElement screenshots = RequireArray(row, "screenshots");
            if (screenshots.GetArrayLength() != 2)
            {
                throw new InvalidDataException("candidate capture screenshot set drifted");
            }
            string? previousDigest = null;
            var bindings = new List<CandidateScreenshotBinding>(2);
            int screenshotIndex = 0;
            foreach (JsonElement screenshot in screenshots.EnumerateArray())
            {
                string role = screenshotIndex++ == 0 ? "progress" : "completion";
                if (!ExactPropertySet(
                        screenshot,
                        new HashSet<string>(
                            ["role", "path", "sha256", "width", "height"],
                            StringComparer.Ordinal)))
                {
                    throw new InvalidDataException(
                        "candidate capture screenshot binding drifted");
                }
                RequireExactString(screenshot, "role", role);
                string path =
                    $"screenshots/windows-installer-{head}-{WindowsRid}-{role}.png";
                RequireExactString(screenshot, "path", path);
                string digest = RequireSha256(screenshot, "sha256");
                int width = RequirePositiveInt32(screenshot, "width");
                int height = RequirePositiveInt32(screenshot, "height");
                if (width is < 320 or > 16384
                    || height is < 200 or > 16384
                    || !finalizedByPath.TryGetValue(
                        path,
                        out ReleaseUploadCandidateInventoryRow? inventoryRow)
                    || inventoryRow.SizeBytes < 1
                    || !string.Equals(inventoryRow.Sha256, digest, StringComparison.Ordinal)
                    || string.Equals(previousDigest, digest, StringComparison.Ordinal))
                {
                    throw new InvalidDataException(
                        "candidate capture screenshot differs from finalized inventory");
                }
                previousDigest = digest;
                bindings.Add(new CandidateScreenshotBinding(role, path, digest));
            }
            result.Add(head, bindings);
        }
        return result;
    }

    private static void ValidateAuthenticodeInventoryBinding(
        JsonElement binding,
        string expectedPath,
        IReadOnlyDictionary<string, ReleaseUploadCandidateInventoryRow> finalizedByPath,
        string label)
    {
        if (!ExactPropertySet(
                binding,
                new HashSet<string>(
                    [
                        "path",
                        "sha256",
                        "signerCertificateSha256",
                        "signerSpkiSha256",
                        "sizeBytes",
                        "timestampUtc"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException($"{label} property set drifted");
        }
        RequireExactString(binding, "path", expectedPath);
        string digest = RequireSha256(binding, "sha256");
        long size = RequirePositiveInt64(binding, "sizeBytes");
        _ = RequireSha256(binding, "signerCertificateSha256");
        _ = RequireSha256(binding, "signerSpkiSha256");
        _ = RequireUtcTimestamp(binding, "timestampUtc");
        if (!finalizedByPath.TryGetValue(
                expectedPath,
                out ReleaseUploadCandidateInventoryRow? inventoryRow)
            || inventoryRow.SizeBytes != size
            || !string.Equals(inventoryRow.Sha256, digest, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{label} differs from finalized inventory");
        }
    }

    private static void ValidateCaptureEvidenceBinding(
        JsonElement binding,
        string expectedPath,
        IReadOnlyDictionary<string, ReleaseUploadCandidateInventoryRow> finalizedByPath,
        string label)
    {
        if (!ExactPropertySet(
                binding,
                new HashSet<string>(["path", "sha256"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException($"{label} property set drifted");
        }
        RequireExactString(binding, "path", expectedPath);
        string digest = RequireSha256(binding, "sha256");
        if (!finalizedByPath.TryGetValue(
                expectedPath,
                out ReleaseUploadCandidateInventoryRow? inventoryRow)
            || inventoryRow.SizeBytes < 1
            || !string.Equals(inventoryRow.Sha256, digest, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{label} differs from finalized inventory");
        }
    }

    private static JsonElement ValidateCaptureCandidateBinding(
        JsonElement captureCandidate,
        JsonElement captureSource,
        IReadOnlyDictionary<string, CandidateEvidenceDocument> documents,
        IReadOnlyDictionary<string, ReleaseUploadCandidateInventoryRow> finalizedByPath,
        string canonicalManifestSha256,
        DateTimeOffset captureGeneratedAt)
    {
        var required = new HashSet<string>(
            [
                "actor",
                "artifactCreatedAt",
                "artifactExpiresAt",
                "artifactId",
                "artifactName",
                "artifactSha256",
                "authenticatedApiSha256",
                "contentInventory",
                "contentInventorySha256",
                "exportReceipt",
                "exportReceiptSha256",
                "fullShelfCompatibilityManifest",
                "fullShelfCompatibilityManifestPath",
                "fullShelfCompatibilityManifestSha256",
                "fullShelfManifest",
                "fullShelfManifestPath",
                "fullShelfManifestSha256",
                "handoffSha256",
                "manifestPath",
                "manifestSha256",
                "publicationScope",
                "publicationScopePath",
                "publicationScopeSha256",
                "ref",
                "registryPrepareFiles",
                "registryPrepareSha256",
                "repository",
                "runAttempt",
                "runId",
                "scopeDecisionSha256",
                "sha",
                "signingReceipt",
                "signingReceiptPath",
                "signingReceiptSha256",
                "supplyChain",
                "workflow"
            ],
            StringComparer.Ordinal);
        if (!ExactPropertySet(captureCandidate, required))
        {
            throw new InvalidDataException("candidate capture binding property set drifted");
        }
        RequireExactString(captureCandidate, "repository", UiRepository);
        RequireExactString(captureCandidate, "workflow", ProducerWorkflow);
        RequireExactString(captureCandidate, "ref", UiRef);
        if (!CommitPattern.IsMatch(RequireString(captureCandidate, "sha"))
            || !GitHubLoginPattern.IsMatch(RequireString(captureCandidate, "actor")))
        {
            throw new InvalidDataException("candidate capture producer provenance drifted");
        }
        string runId = RequirePositiveGitHubIntegerString(captureCandidate, "runId");
        string runAttempt = RequirePositiveGitHubIntegerString(captureCandidate, "runAttempt");
        _ = RequirePositiveGitHubIntegerString(captureCandidate, "artifactId");
        RequireExactString(
            captureCandidate,
            "artifactName",
            $"preview-nightly-candidate-{runId}-{runAttempt}");
        foreach (string property in new[]
                 {
                     "artifactSha256",
                     "authenticatedApiSha256",
                     "contentInventorySha256",
                     "exportReceiptSha256",
                     "fullShelfCompatibilityManifestSha256",
                     "fullShelfManifestSha256",
                     "handoffSha256",
                     "manifestSha256",
                     "publicationScopeSha256",
                     "registryPrepareSha256",
                     "scopeDecisionSha256",
                     "signingReceiptSha256"
                 })
        {
            _ = RequireSha256(captureCandidate, property);
        }
        RequireExactString(
            captureCandidate,
            "manifestPath",
            "RELEASE_CHANNEL.generated.json");
        RequireExactString(
            captureCandidate,
            "manifestSha256",
            canonicalManifestSha256);
        DateTimeOffset createdAt = RequireGitHubTimestamp(
            captureCandidate,
            "artifactCreatedAt");
        DateTimeOffset expiresAt = RequireGitHubTimestamp(
            captureCandidate,
            "artifactExpiresAt");
        if (createdAt >= expiresAt
            || createdAt > captureGeneratedAt.AddMinutes(5)
            || expiresAt <= captureGeneratedAt)
        {
            throw new InvalidDataException("candidate capture artifact lifetime drifted");
        }
        foreach (string property in new[] { "repository", "ref", "sha" })
        {
            if (!string.Equals(
                    RequireString(captureCandidate, property),
                    RequireString(captureSource, property),
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    "candidate capture revision differs from capture source");
            }
        }

        ValidateCaptureDocumentBinding(
            captureCandidate,
            "contentInventory",
            "contentInventorySha256",
            CandidateProvenanceInventoryFileName,
            documents);
        ValidateCaptureDocumentBinding(
            captureCandidate,
            "exportReceipt",
            "exportReceiptSha256",
            CandidateProvenanceExportFileName,
            documents);
        ValidateCaptureInventoryBinding(
            captureCandidate,
            "fullShelfManifest",
            "fullShelfManifestPath",
            "fullShelfManifestSha256",
            "RELEASE_CHANNEL.generated.json",
            "candidate-provenance/RELEASE_CHANNEL.generated.json",
            finalizedByPath);
        RequireExactString(
            captureCandidate,
            "fullShelfManifestSha256",
            canonicalManifestSha256);
        ValidateCaptureInventoryBinding(
            captureCandidate,
            "fullShelfCompatibilityManifest",
            "fullShelfCompatibilityManifestPath",
            "fullShelfCompatibilityManifestSha256",
            "releases.json",
            "candidate-provenance/releases.json",
            finalizedByPath);
        ValidateCaptureInventoryBinding(
            captureCandidate,
            "publicationScope",
            "publicationScopePath",
            "publicationScopeSha256",
            "publication-scope/PREVIEW_NIGHTLY_PUBLICATION_SCOPE_PROPOSAL.generated.json",
            "candidate-provenance/publication-scope/"
                + "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_PROPOSAL.generated.json",
            finalizedByPath);
        ValidateCaptureInventoryBinding(
            captureCandidate,
            "signingReceipt",
            "signingReceiptPath",
            "signingReceiptSha256",
            "signing/signing-avalonia-win-x64.receipt.json",
            "candidate-provenance/signing/signing-avalonia-win-x64.receipt.json",
            finalizedByPath);
        _ = RequireArray(captureCandidate, "registryPrepareFiles");
        _ = RequireObject(captureCandidate, "supplyChain");
        return captureCandidate;
    }

    private static void ValidateCaptureInventoryBinding(
        JsonElement captureCandidate,
        string property,
        string pathProperty,
        string digestProperty,
        string shelfPath,
        string custodyPath,
        IReadOnlyDictionary<string, ReleaseUploadCandidateInventoryRow> finalizedByPath)
    {
        JsonElement binding = RequireObject(captureCandidate, property);
        if (!ExactPropertySet(
                binding,
                new HashSet<string>(["path", "sha256", "sizeBytes"], StringComparer.Ordinal))
            || !finalizedByPath.TryGetValue(
                custodyPath,
                out ReleaseUploadCandidateInventoryRow? inventoryRow))
        {
            throw new InvalidDataException($"candidate capture {property} custody drifted");
        }
        RequireExactString(captureCandidate, pathProperty, shelfPath);
        RequireExactString(binding, "path", custodyPath);
        RequireExactString(binding, "sha256", inventoryRow.Sha256);
        RequireExactString(captureCandidate, digestProperty, inventoryRow.Sha256);
        if (RequirePositiveInt64(binding, "sizeBytes") != inventoryRow.SizeBytes)
        {
            throw new InvalidDataException($"candidate capture {property} size drifted");
        }
    }

    private static void ValidateCaptureDocumentBinding(
        JsonElement captureCandidate,
        string property,
        string digestProperty,
        string expectedPath,
        IReadOnlyDictionary<string, CandidateEvidenceDocument> documents)
    {
        JsonElement binding = RequireObject(captureCandidate, property);
        if (!ExactPropertySet(
                binding,
                new HashSet<string>(["path", "sha256", "sizeBytes"], StringComparer.Ordinal))
            || !documents.TryGetValue(expectedPath, out CandidateEvidenceDocument? document))
        {
            throw new InvalidDataException($"candidate capture {property} custody drifted");
        }
        RequireExactString(binding, "path", expectedPath);
        RequireExactString(binding, "sha256", document.Sha256);
        RequireExactString(captureCandidate, digestProperty, document.Sha256);
        if (document.SizeBytes <= 0
            || RequireNonNegativeInt64(binding, "sizeBytes") != document.SizeBytes)
        {
            throw new InvalidDataException($"candidate capture {property} custody drifted");
        }
    }

    private static void ValidateCandidateExportReceipt(
        JsonElement export,
        JsonElement captureCandidate,
        string canonicalManifestSha256,
        CandidateWindowsScope scope)
    {
        var required = new HashSet<string>(
            [
                "candidateManifest",
                "contentInventory",
                "contractName",
                "contractVersion",
                "heads",
                "publicationScope",
                "release",
                "source",
                "status",
                "supplyChain",
                "supplyChainVerification"
            ],
            StringComparer.Ordinal);
        if (!ExactPropertySet(export, required))
        {
            throw new InvalidDataException("candidate export receipt property set drifted");
        }
        RequireExactString(
            export,
            "contractName",
            "chummer6-ui.preview-nightly-candidate-export");
        RequireExactInt32(export, "contractVersion", 2);
        RequireExactString(export, "status", "exported");

        JsonElement publicationScope = RequireObject(export, "publicationScope");
        if (!ExactPropertySet(
                publicationScope,
                new HashSet<string>(["registryPrepareSha256"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "candidate export publication scope property set drifted");
        }
        RequireExactString(
            publicationScope,
            "registryPrepareSha256",
            RequireSha256(captureCandidate, "registryPrepareSha256"));
        if (!JsonSemanticEquals(
                RequireObject(export, "supplyChain"),
                RequireObject(captureCandidate, "supplyChain")))
        {
            throw new InvalidDataException("candidate export supply-chain binding drifted");
        }
        JsonElement supplyChainVerification = RequireObject(
            export,
            "supplyChainVerification");
        if (!ExactPropertySet(
                supplyChainVerification,
                new HashSet<string>(
                    ["mode", "releaseAuthoritative"],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "candidate export supply-chain verification property set drifted");
        }
        RequireExactString(
            supplyChainVerification,
            "mode",
            "release_authoritative");
        RequireBoolean(
            supplyChainVerification,
            "releaseAuthoritative",
            expected: true);

        JsonElement release = RequireObject(export, "release");
        if (!ExactPropertySet(
                release,
                new HashSet<string>(["channel", "version"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException("candidate export release binding drifted");
        }
        RequireExactString(release, "channel", scope.Channel);
        RequireExactString(release, "version", scope.Version);

        JsonElement manifest = RequireObject(export, "candidateManifest");
        JsonElement inventory = RequireObject(export, "contentInventory");
        var documentBindingKeys = new HashSet<string>(["path", "sha256"], StringComparer.Ordinal);
        if (!ExactPropertySet(manifest, documentBindingKeys)
            || !ExactPropertySet(inventory, documentBindingKeys))
        {
            throw new InvalidDataException("candidate export document binding drifted");
        }
        RequireExactString(manifest, "path", "RELEASE_CHANNEL.generated.json");
        RequireExactString(manifest, "sha256", canonicalManifestSha256);
        RequireExactString(
            inventory,
            "path",
            "PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json");
        RequireExactString(
            inventory,
            "sha256",
            RequireSha256(captureCandidate, "contentInventorySha256"));

        JsonElement source = RequireObject(export, "source");
        var sourceKeys = new HashSet<string>(
            [
                "actor",
                "artifactName",
                "ref",
                "repository",
                "runAttempt",
                "runId",
                "runnerLabel",
                "sha",
                "workflow"
            ],
            StringComparer.Ordinal);
        if (!ExactPropertySet(source, sourceKeys))
        {
            throw new InvalidDataException("candidate export source property set drifted");
        }
        foreach (string property in sourceKeys.Where(static name => name != "runnerLabel"))
        {
            if (!string.Equals(
                    RequireString(source, property),
                    RequireString(captureCandidate, property),
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    "candidate export source differs from capture authority");
            }
        }
        if (!ExportRunnerLabelPattern.IsMatch(RequireString(source, "runnerLabel")))
        {
            throw new InvalidDataException("candidate export runner label drifted");
        }

        JsonElement heads = RequireArray(export, "heads");
        if (heads.GetArrayLength() != scope.Heads.Count)
        {
            throw new InvalidDataException("candidate export required-head scope drifted");
        }
        int index = 0;
        foreach (JsonElement head in heads.EnumerateArray())
        {
            string expectedHead = scope.Heads[index++];
            if (!ExactPropertySet(
                    head,
                    new HashSet<string>(
                        ["headId", "rid", "installer", "payload"],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException("candidate export head binding drifted");
            }
            RequireExactString(head, "headId", expectedHead);
            RequireExactString(head, "rid", WindowsRid);
            CandidateHeadArtifacts artifacts = scope.Artifacts[expectedHead];
            ValidateExportArtifactBinding(
                RequireObject(head, "installer"),
                artifacts.Installer);
            ValidateExportArtifactBinding(
                RequireObject(head, "payload"),
                artifacts.Payload);
        }
    }

    private static void ValidateExportArtifactBinding(
        JsonElement binding,
        CandidateArtifact artifact)
    {
        if (!ExactPropertySet(
                binding,
                new HashSet<string>(
                    ["relativePath", "fileName", "sha256", "sizeBytes"],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException("candidate export artifact property set drifted");
        }
        RequireExactString(binding, "relativePath", artifact.Path);
        RequireExactString(binding, "fileName", artifact.FileName);
        RequireExactString(binding, "sha256", artifact.Sha256);
        if (RequireNonNegativeInt64(binding, "sizeBytes") != artifact.SizeBytes)
        {
            throw new InvalidDataException("candidate export artifact size drifted");
        }
    }

    private static IReadOnlyList<ReleaseUploadCandidateInventoryRow> ParseEvidenceInventoryRows(
        JsonElement files,
        string label,
        bool allowEmpty)
    {
        if (files.ValueKind != JsonValueKind.Array
            || !allowEmpty && files.GetArrayLength() == 0)
        {
            throw new InvalidDataException($"{label} is invalid");
        }
        var rows = new List<ReleaseUploadCandidateInventoryRow>();
        string? previous = null;
        foreach (JsonElement row in files.EnumerateArray())
        {
            if (!ExactPropertySet(
                    row,
                    new HashSet<string>(["path", "sha256", "sizeBytes"], StringComparer.Ordinal)))
            {
                throw new InvalidDataException($"{label} row drifted");
            }
            string path = RequireString(row, "path");
            if (!IsCanonicalRelativePath(path)
                || previous is not null && string.CompareOrdinal(previous, path) >= 0)
            {
                throw new InvalidDataException($"{label} path drifted");
            }
            rows.Add(new ReleaseUploadCandidateInventoryRow(
                path,
                RequireNonNegativeInt64(row, "sizeBytes"),
                RequireSha256(row, "sha256")));
            previous = path;
        }
        return rows;
    }

    private static void ValidateEvidenceSource(
        JsonElement source,
        string label,
        string workflow)
    {
        var required = new HashSet<string>(
            [
                "repository",
                "workflow",
                "runId",
                "runAttempt",
                "ref",
                "sha",
                "actor",
                "artifactName"
            ],
            StringComparer.Ordinal);
        if (!ExactPropertySet(source, required))
        {
            throw new InvalidDataException($"{label} property set drifted");
        }
        RequireExactString(source, "repository", UiRepository);
        RequireExactString(source, "workflow", workflow);
        RequireExactString(source, "ref", UiRef);
        if (!CommitPattern.IsMatch(RequireString(source, "sha")))
        {
            throw new InvalidDataException($"{label} revision drifted");
        }
        string runId = RequirePositiveGitHubIntegerString(source, "runId");
        string runAttempt = RequirePositiveGitHubIntegerString(source, "runAttempt");
        string actor = RequireString(source, "actor");
        Regex actorPattern = string.Equals(workflow, CaptureWorkflow, StringComparison.Ordinal)
            ? GitHubLoginPattern
            : ReviewerPattern;
        if (!actorPattern.IsMatch(actor))
        {
            throw new InvalidDataException($"{label} actor drifted");
        }
        string expectedArtifactName = string.Equals(
            workflow,
            CaptureWorkflow,
            StringComparison.Ordinal)
            ? $"windows-native-evidence-{runId}-{runAttempt}"
            : $"windows-native-evidence-finalized-{runId}-{runAttempt}";
        if (!string.Equals(
                RequireString(source, "artifactName"),
                expectedArtifactName,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{label} artifact identity drifted");
        }
    }

    private static void ValidatePassedReview(JsonElement proof, string name, string reviewer)
    {
        JsonElement review = RequireObject(proof, name);
        if (!ExactPropertySet(
                review,
                new HashSet<string>(["status", "reviewer"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException($"candidate visual {name} property set drifted");
        }
        RequireExactString(review, "status", "passed");
        RequireExactString(review, "reviewer", reviewer);
    }

    private static DateTimeOffset RequireFreshUtcTimestamp(
        JsonElement parent,
        string property,
        DateTimeOffset now)
    {
        DateTimeOffset parsed = RequireUtcTimestamp(parent, property);
        if (parsed > now.AddMinutes(5) || now - parsed > MaximumNativeProofAge)
        {
            throw new InvalidDataException($"release upload {property} is stale or future-dated");
        }
        return parsed;
    }

    private static string RequireMatchingAlias(
        JsonElement parent,
        string first,
        string second,
        string label)
    {
        bool firstPresent = parent.TryGetProperty(first, out JsonElement firstElement);
        bool secondPresent = parent.TryGetProperty(second, out JsonElement secondElement);
        if (firstPresent && firstElement.ValueKind != JsonValueKind.String
            || secondPresent && secondElement.ValueKind != JsonValueKind.String)
        {
            throw new InvalidDataException($"{label} alias type drifted");
        }
        string? firstValue = firstPresent ? firstElement.GetString() : null;
        string? secondValue = secondPresent ? secondElement.GetString() : null;
        if (firstValue is not null
            && secondValue is not null
            && !string.Equals(firstValue, secondValue, StringComparison.Ordinal))
        {
            throw new InvalidDataException($"{label} aliases disagree");
        }
        return firstValue ?? secondValue
            ?? throw new InvalidDataException($"{label} is missing");
    }

    private static bool HasExactString(JsonElement parent, string property, string expected)
        => parent.TryGetProperty(property, out JsonElement value)
           && value.ValueKind == JsonValueKind.String
           && string.Equals(value.GetString(), expected, StringComparison.Ordinal);

    private static bool JsonSemanticEquals(JsonElement left, JsonElement right)
    {
        if (left.ValueKind != right.ValueKind)
        {
            return false;
        }
        return left.ValueKind switch
        {
            JsonValueKind.Object =>
                left.EnumerateObject().Count() == right.EnumerateObject().Count()
                && left.EnumerateObject().All(property =>
                    right.TryGetProperty(property.Name, out JsonElement other)
                    && JsonSemanticEquals(property.Value, other)),
            JsonValueKind.Array => left.EnumerateArray()
                .Zip(right.EnumerateArray())
                .All(pair => JsonSemanticEquals(pair.First, pair.Second))
                && left.GetArrayLength() == right.GetArrayLength(),
            JsonValueKind.String => string.Equals(
                left.GetString(),
                right.GetString(),
                StringComparison.Ordinal),
            JsonValueKind.Number => string.Equals(
                left.GetRawText(),
                right.GetRawText(),
                StringComparison.Ordinal),
            JsonValueKind.True or JsonValueKind.False => left.GetBoolean() == right.GetBoolean(),
            JsonValueKind.Null => true,
            _ => false
        };
    }

    private static JsonElement RequireArray(JsonElement parent, string property)
        => parent.TryGetProperty(property, out JsonElement value)
           && value.ValueKind == JsonValueKind.Array
            ? value
            : throw new InvalidDataException($"release upload {property} is invalid");

    private static IReadOnlyList<ReleaseUploadCandidateInventoryRow> ParseCandidateInventory(
        byte[] payload)
    {
        using JsonDocument document = ParseStrictObject(payload, "candidate upload inventory");
        JsonElement root = document.RootElement;
        if (!ExactPropertySet(
                root,
                new HashSet<string>(
                    ["contractName", "contractVersion", "files"],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException("candidate upload inventory property set drifted");
        }
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
            if (!ExactPropertySet(
                    row,
                    new HashSet<string>(
                        ["path", "sha256", "sizeBytes"],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException("candidate upload inventory row drifted");
            }
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

    private static byte[] DecodeEmbedded(
        JsonElement entry,
        string label,
        string expectedPath)
    {
        if (!ExactPropertySet(
                entry,
                new HashSet<string>(
                    ["path", "sha256", "sizeBytes", "base64"],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException($"{label} custody binding drifted");
        }
        RequireExactString(entry, "path", expectedPath);
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
           && HasCanonicalNonNegativeIntegerToken(value)
           && value.TryGetInt64(out long parsed)
           && parsed >= 0
            ? parsed
            : throw new InvalidDataException($"release upload {property} is invalid");

    private static long RequirePositiveInt64(JsonElement parent, string property)
    {
        long value = RequireNonNegativeInt64(parent, property);
        return value > 0
            ? value
            : throw new InvalidDataException($"release upload {property} is invalid");
    }

    private static int RequirePositiveInt32(JsonElement parent, string property)
        => parent.TryGetProperty(property, out JsonElement value)
           && value.ValueKind == JsonValueKind.Number
           && HasCanonicalNonNegativeIntegerToken(value)
           && value.TryGetInt32(out int parsed)
           && parsed > 0
            ? parsed
            : throw new InvalidDataException($"release upload {property} is invalid");

    private static string RequirePositiveGitHubIntegerString(
        JsonElement parent,
        string property)
    {
        string value = RequireString(parent, property);
        if (!PositiveIntegerPattern.IsMatch(value)
            || !long.TryParse(
                value,
                System.Globalization.NumberStyles.None,
                System.Globalization.CultureInfo.InvariantCulture,
                out long parsed)
            || parsed > 9_007_199_254_740_991L)
        {
            throw new InvalidDataException(
                $"release upload {property} is not an exact positive GitHub integer string");
        }
        return value;
    }

    private static void RequireExactInt32(JsonElement parent, string property, int expected)
    {
        if (!parent.TryGetProperty(property, out JsonElement value)
            || value.ValueKind != JsonValueKind.Number
            || !HasCanonicalNonNegativeIntegerToken(value)
            || !value.TryGetInt32(out int parsed)
            || parsed != expected)
        {
            throw new InvalidDataException($"release upload {property} drifted");
        }
    }

    private static bool HasCanonicalNonNegativeIntegerToken(JsonElement value)
    {
        string raw = value.GetRawText();
        if (raw.Length == 1)
        {
            return raw[0] is >= '0' and <= '9';
        }
        return raw.Length > 1
               && raw[0] is >= '1' and <= '9'
               && raw.AsSpan(1).IndexOfAnyExceptInRange('0', '9') < 0;
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

    private static DateTimeOffset RequireGitHubTimestamp(
        JsonElement parent,
        string property)
    {
        string value = RequireString(parent, property);
        if (!GitHubTimestampPattern.IsMatch(value)
            || !DateTimeOffset.TryParseExact(
                value,
                "yyyy-MM-dd'T'HH:mm:ss'Z'",
                System.Globalization.CultureInfo.InvariantCulture,
                System.Globalization.DateTimeStyles.AssumeUniversal
                | System.Globalization.DateTimeStyles.AdjustToUniversal,
                out DateTimeOffset parsed)
            || parsed.Offset != TimeSpan.Zero)
        {
            throw new InvalidDataException(
                $"release upload {property} is not an exact UTC GitHub timestamp");
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

    private sealed record CandidateArtifact(
        string Path,
        string FileName,
        string Sha256,
        long SizeBytes);

    private sealed record CandidateHeadArtifacts(
        CandidateArtifact Installer,
        CandidateArtifact Payload);

    private sealed record CandidateWindowsScope(
        string Version,
        string Channel,
        IReadOnlyList<string> Heads,
        IReadOnlyDictionary<string, CandidateHeadArtifacts> Artifacts);

    private sealed record CandidateVisualProof(
        string Path,
        JsonElement Root,
        byte[] Bytes);

    private sealed record CandidateScreenshotBinding(
        string Role,
        string Path,
        string Sha256);

    private sealed record CandidateNativePackage(
        string CaptureInventorySha256,
        byte[] FinalizationBytes,
        JsonElement Candidate,
        JsonElement CaptureSource,
        JsonElement FinalizationSource,
        JsonElement AuthenticodeVerification,
        IReadOnlyList<CandidateScreenshotBinding> Screenshots);

    private sealed class CandidateEvidenceDocument : IDisposable
    {
        private readonly JsonDocument _document;

        public CandidateEvidenceDocument(
            JsonDocument document,
            byte[] bytes,
            string sha256,
            long sizeBytes)
        {
            _document = document;
            Bytes = bytes;
            Sha256 = sha256;
            SizeBytes = sizeBytes;
        }

        public JsonElement Root => _document.RootElement;
        public byte[] Bytes { get; }
        public string Sha256 { get; }
        public long SizeBytes { get; }

        public void Dispose() => _document.Dispose();
    }

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
        var expectedDirectories = new HashSet<string>(StringComparer.Ordinal);
        foreach (ReleaseUploadCandidateInventoryRow row in authority.Inventory)
        {
            string? parent = Path.GetDirectoryName(row.Path.Replace('/', Path.DirectorySeparatorChar));
            while (!string.IsNullOrEmpty(parent))
            {
                expectedDirectories.Add(parent.Replace('\\', '/'));
                parent = Path.GetDirectoryName(parent);
            }
        }
        var actualDirectories = new HashSet<string>(StringComparer.Ordinal);
        var rows = new List<ReleaseUploadCandidateInventoryRow>();
        var pending = new Stack<string>();
        pending.Push(root);
        while (pending.TryPop(out string? directory))
        {
            var directoryBefore = new DirectoryInfo(directory);
            directoryBefore.Refresh();
            if (!directoryBefore.Exists
                || (directoryBefore.Attributes & FileAttributes.ReparsePoint) != 0)
            {
                throw new InvalidDataException(
                    "candidate upload bundle contains a forbidden directory link");
            }
            string[] entries = Directory.EnumerateFileSystemEntries(
                    directory,
                    "*",
                    SearchOption.TopDirectoryOnly)
                .Order(StringComparer.Ordinal)
                .ToArray();
            foreach (string path in entries)
            {
                FileAttributes attributes = File.GetAttributes(path);
                if ((attributes & FileAttributes.ReparsePoint) != 0)
                {
                    throw new InvalidDataException(
                        "candidate upload bundle contains a forbidden link");
                }
                string relative = Path.GetRelativePath(root, path).Replace('\\', '/');
                if (relative.Length == 0
                    || relative.StartsWith("/", StringComparison.Ordinal)
                    || relative.Contains('\\')
                    || relative.Split('/').Any(static segment =>
                        segment.Length == 0
                        || segment is "." or ".."
                        || segment.Contains(':')))
                {
                    throw new InvalidDataException(
                        "candidate upload bundle contains a non-canonical path");
                }
                if ((attributes & FileAttributes.Directory) != 0)
                {
                    if (!actualDirectories.Add(relative))
                    {
                        throw new InvalidDataException(
                            "candidate upload bundle directory is duplicated");
                    }
                    pending.Push(path);
                    continue;
                }
                var before = new FileInfo(path);
                before.Refresh();
                string sha256;
                using (FileStream stream = new(
                           path,
                           FileMode.Open,
                           FileAccess.Read,
                           FileShare.Read))
                {
                    sha256 = Convert.ToHexStringLower(SHA256.HashData(stream));
                }
                var after = new FileInfo(path);
                after.Refresh();
                if (!after.Exists
                    || (after.Attributes & FileAttributes.ReparsePoint) != 0
                    || before.Length != after.Length
                    || before.LastWriteTimeUtc != after.LastWriteTimeUtc)
                {
                    throw new InvalidDataException(
                        "candidate upload bundle changed during validation");
                }
                string pathSha256;
                using (FileStream stream = new(
                           path,
                           FileMode.Open,
                           FileAccess.Read,
                           FileShare.Read))
                {
                    pathSha256 = Convert.ToHexStringLower(SHA256.HashData(stream));
                }
                if (!string.Equals(sha256, pathSha256, StringComparison.Ordinal))
                {
                    throw new InvalidDataException(
                        "candidate upload bundle changed during validation");
                }
                rows.Add(new ReleaseUploadCandidateInventoryRow(
                    relative,
                    after.Length,
                    sha256));
            }
            var directoryAfter = new DirectoryInfo(directory);
            directoryAfter.Refresh();
            if (!directoryAfter.Exists
                || (directoryAfter.Attributes & FileAttributes.ReparsePoint) != 0
                || directoryAfter.LastWriteTimeUtc != directoryBefore.LastWriteTimeUtc)
            {
                throw new InvalidDataException(
                    "candidate upload bundle directory changed during validation");
            }
        }
        rows.Sort(static (left, right) => string.CompareOrdinal(left.Path, right.Path));
        if (!actualDirectories.SetEquals(expectedDirectories)
            || !rows.SequenceEqual(authority.Inventory)
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
