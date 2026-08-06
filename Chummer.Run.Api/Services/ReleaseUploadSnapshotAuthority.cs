using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using System.Text.RegularExpressions;
using Chummer.Run.Contracts.PublicSurface;

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

public sealed record ReleaseUploadCandidateIncumbentBinding(
    string SnapshotSha256,
    string FullShelfInventorySha256,
    string ActiveInventorySha256,
    string CanonicalManifestSha256,
    string CompatibilityManifestSha256);

public sealed record ReleaseUploadCandidateNativeEvidenceBinding(
    string EvidenceSha256,
    string CaptureInventorySha256,
    string SourceCommit,
    string BundleIdentitySha256,
    string CanonicalManifestSha256,
    string InventorySha256);

public sealed record ReleaseUploadCandidatePublicationReadinessBinding(
    string ReceiptSha256,
    string SourceCandidateAuthoritySha256,
    string SourceCanonicalManifestSha256,
    string SourceCompatibilityManifestSha256,
    string ReadyCanonicalManifestSha256,
    string ReadyCompatibilityManifestSha256);

public sealed record ReleaseUploadCandidateSessionBinding(
    string SnapshotSha256,
    string AuthoritySha256,
    string BundleIdentitySha256,
    string CanonicalManifestSha256,
    string InventorySha256,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    bool ExactIncomingDesktopScopeIsFreshDelta = false,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    ReleaseUploadCandidateIncumbentBinding? IncumbentBinding = null,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    ReleaseUploadCandidateNativeEvidenceBinding? NativeEvidenceBinding = null,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    ReleaseUploadCandidatePublicationReadinessBinding? PublicationReadinessBinding = null);

public sealed record ReleaseUploadCandidateAuthority(
    string SnapshotId,
    string SnapshotSha256,
    string AuthoritySha256,
    DateTimeOffset ExpiresAtUtc,
    ReleaseUploadCandidateIdentity Candidate,
    byte[] CanonicalManifestBytes,
    IReadOnlyList<ReleaseUploadCandidateInventoryRow> Inventory,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    bool ExactIncomingDesktopScopeIsFreshDelta = false,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    ReleaseUploadCandidateIncumbentBinding? IncumbentBinding = null,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    ReleaseUploadCandidateNativeEvidenceBinding? NativeEvidenceBinding = null,
    [property: JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    ReleaseUploadCandidatePublicationReadinessBinding? PublicationReadinessBinding = null)
{
    public ReleaseUploadCandidateSessionBinding SessionBinding => new(
        SnapshotSha256,
        AuthoritySha256,
        Candidate.BundleIdentitySha256,
        Candidate.CanonicalManifestSha256,
        Candidate.InventorySha256,
        ExactIncomingDesktopScopeIsFreshDelta,
        IncumbentBinding,
        NativeEvidenceBinding,
        PublicationReadinessBinding);
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
    private const string UnsignedWindowsFreshDeltaProjectionProfile =
        "v3_unsigned_windows_fresh_delta";
    private const string UnsignedWindowsCodeDeployReviewContract =
        "chummer.registry.preview-publication-delta-code-deploy-review/v1";

    private const string CurrentFileName = "CURRENT.json";
    private const string ManifestFileName = "PUBLIC_PROJECTION_SNAPSHOT.generated.json";
    private const string CurrentContractName = "chummer.public_projection_current/v1";
    private const string SnapshotContractName = "chummer.public_projection_snapshot/v1";
    private const string CandidateContractName =
        "chummer.release-upload.candidate-import-authority/v2";
    private const string UnsignedCandidateContractName =
        "chummer.release-upload.candidate-import-authority/v3";
    private const string UnsignedNativeCandidateContractName =
        "chummer.release-upload.candidate-import-authority/v4";
    private const string UnsignedNativeGenerationCandidateContractName =
        "chummer.release-upload.candidate-import-authority/v5";
    private const string UnsignedPreviewReadyCandidateContractName =
        "chummer.release-upload.candidate-import-authority/v6";
    private const string UnsignedWindowsPreviewReadyProjectionProfile =
        "v4_unsigned_windows_preview_ready";
    private const string PreviewPublicationReadinessContractName =
        "chummer.registry.preview-publication-readiness/v1";
    private const string NativeStageGenerationProjectionContractName =
        "chummer.release-upload.native-stage-generation-projection/v1";
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
    private static readonly Regex UnsignedExportRunnerNoncePattern = new(
        "^[a-z0-9]{12,64}$",
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
    private const string UnsignedCaptureFileName =
        "UNSIGNED_WINDOWS_PREVIEW_NATIVE_CAPTURE.generated.json";
    private const string UnsignedCaptureInventoryFileName =
        "UNSIGNED_WINDOWS_PREVIEW_NATIVE_CAPTURE_INVENTORY.generated.json";
    private const string UnsignedFinalizationFileName =
        "UNSIGNED_WINDOWS_PREVIEW_NATIVE_FINALIZATION.generated.json";
    private const string UnsignedFinalizedInventoryFileName =
        "UNSIGNED_WINDOWS_PREVIEW_NATIVE_FINALIZED_INVENTORY.generated.json";
    private const string CandidateProvenanceInventoryFileName =
        "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json";
    private const string CandidateProvenanceExportFileName =
        "candidate-provenance/PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json";
    private const string UnsignedCandidateProvenanceInventoryFileName =
        "candidate-provenance/PREVIEW_NIGHTLY_UNSIGNED_CANDIDATE_CONTENT_INVENTORY.generated.json";
    private const string UnsignedCandidateProvenanceExportFileName =
        "candidate-provenance/PREVIEW_NIGHTLY_UNSIGNED_CANDIDATE_EXPORT.generated.json";
    private const string CandidateUploadContentInventoryFileName =
        "PREVIEW_NIGHTLY_CANDIDATE_CONTENT_INVENTORY.generated.json";
    private const string CandidateUploadExportFileName =
        "PREVIEW_NIGHTLY_CANDIDATE_EXPORT.generated.json";
    private const string PackagePlaneLockBindingPath =
        "config/package-plane.lock.json";
    private const string CaptureWorkflow =
        ".github/workflows/windows-native-evidence-capture.yml";
    private const string FinalizationWorkflow =
        ".github/workflows/windows-native-evidence-finalize.yml";
    private const string UnsignedCaptureWorkflow =
        ".github/workflows/unsigned-windows-preview-native-evidence-capture.yml";
    private const string UnsignedFinalizationWorkflow =
        ".github/workflows/unsigned-windows-preview-native-evidence-finalize.yml";
    private const string ProducerWorkflow =
        ".github/workflows/preview-nightly-candidate-export.yml";
    private const string UnsignedProducerWorkflow =
        ".github/workflows/unsigned-windows-preview-nightly-candidate-export.yml";
    private const string UiRepository = "ArchonMegalon/chummer6-ui";
    private const string UiRef = "refs/heads/main";
    private const string WindowsRid = "win-x64";
    private static readonly string[] PromotedHeads = ["avalonia"];
    private static readonly HashSet<string> RetainedDesktopHeads = new(
        ["avalonia", "blazor-desktop"],
        StringComparer.Ordinal);
    private static readonly string[] UnsignedRetainedArtifactIds =
    [
        "avalonia-linux-x64-installer"
    ];
    private static readonly string[] LegacyUnsignedRetainedArtifactIds =
    [
        "avalonia-osx-arm64-installer",
        "blazor-desktop-osx-arm64-installer",
        "avalonia-osx-arm64-archive",
        "blazor-desktop-osx-arm64-archive"
    ];
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
                                          or InvalidOperationException
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

    internal static ReleaseUploadCandidateAuthority ParseCandidateAuthority(
        string snapshotId,
        string snapshotSha256,
        string authoritySha256,
        byte[] payload,
        DateTimeOffset? evaluatedAtUtc = null)
    {
        DateTimeOffset now = evaluatedAtUtc ?? DateTimeOffset.UtcNow;
        using JsonDocument document = ParseStrictObject(payload, "candidate import authority");
        JsonElement root = document.RootElement;
        if (root.TryGetProperty("contractName", out JsonElement readyContractName)
            && readyContractName.ValueKind == JsonValueKind.String
            && string.Equals(
                readyContractName.GetString(),
                UnsignedPreviewReadyCandidateContractName,
                StringComparison.Ordinal))
        {
            return ParseUnsignedPreviewReadyCandidateAuthority(
                snapshotId,
                snapshotSha256,
                authoritySha256,
                root,
                now);
        }
        if (root.TryGetProperty("contractName", out JsonElement contractName)
            && contractName.ValueKind == JsonValueKind.String
            && contractName.GetString() is { } unsignedContract
            && unsignedContract is UnsignedCandidateContractName
                or UnsignedNativeCandidateContractName
                or UnsignedNativeGenerationCandidateContractName)
        {
            return ParseUnsignedCandidateAuthority(
                snapshotId,
                snapshotSha256,
                authoritySha256,
                root,
                ownerNativeFinalizationBridge:
                    unsignedContract is UnsignedNativeCandidateContractName
                        or UnsignedNativeGenerationCandidateContractName,
                ownerNativeStageAuthoritySeedBridge:
                    string.Equals(
                        unsignedContract,
                        UnsignedNativeGenerationCandidateContractName,
                        StringComparison.Ordinal),
                now: now);
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

    internal static ReleaseUploadCandidateNativeEvidenceBinding
        ValidateUnsignedNativeEvidenceContract(
        byte[] payload,
        byte[] canonicalManifest,
        ReleaseUploadCandidateIdentity candidate,
        IReadOnlyList<ReleaseUploadCandidateInventoryRow> inventory,
        DateTimeOffset now)
    {
        using JsonDocument nativeDocument = ParseStrictObject(
            payload,
            "unsigned native-Windows finalized evidence");
        using JsonDocument canonicalDocument = ParseStrictObject(
            canonicalManifest,
            "unsigned candidate canonical manifest");
        CandidateNativePackage nativePackage = ValidateCandidateNativeEvidence(
            nativeDocument.RootElement,
            canonicalDocument.RootElement,
            candidate,
            inventory,
            now,
            allowUnsigned: true);
        return new ReleaseUploadCandidateNativeEvidenceBinding(
            Sha256(JsonSerializer.SerializeToUtf8Bytes(nativeDocument.RootElement)),
            nativePackage.CaptureInventorySha256,
            RequireString(nativePackage.CaptureSource, "sha"),
            candidate.BundleIdentitySha256,
            candidate.CanonicalManifestSha256,
            candidate.InventorySha256);
    }

    private static ReleaseUploadCandidateAuthority ParseUnsignedCandidateAuthority(
        string snapshotId,
        string snapshotSha256,
        string authoritySha256,
        JsonElement root,
        bool ownerNativeFinalizationBridge,
        bool ownerNativeStageAuthoritySeedBridge,
        DateTimeOffset now)
    {
        var rootProperties = new HashSet<string>(
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
            StringComparer.Ordinal);
        if (ownerNativeFinalizationBridge)
        {
            rootProperties.Add("ownerNativeFinalizationBridgeAuthority");
        }
        if (ownerNativeStageAuthoritySeedBridge)
        {
            rootProperties.Add("ownerNativeStageAuthoritySeedBridgeAuthority");
        }
        if (!ExactPropertySet(root, rootProperties))
        {
            throw new InvalidDataException(
                "unsigned candidate import authority property set drifted");
        }
        RequireExactString(
            root,
            "contractName",
            ownerNativeStageAuthoritySeedBridge
                ? UnsignedNativeGenerationCandidateContractName
                : ownerNativeFinalizationBridge
                ? UnsignedNativeCandidateContractName
                : UnsignedCandidateContractName);
        RequireExactInt32(
            root,
            "contractVersion",
            ownerNativeStageAuthoritySeedBridge
                ? 5
                : ownerNativeFinalizationBridge ? 4 : 3);
        if (ownerNativeFinalizationBridge)
        {
            RequireBoolean(
                root,
                "ownerNativeFinalizationBridgeAuthority",
                expected: true);
        }
        if (ownerNativeStageAuthoritySeedBridge)
        {
            RequireBoolean(
                root,
                "ownerNativeStageAuthoritySeedBridgeAuthority",
                expected: true);
        }
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
        var custodyProperties = new HashSet<string>(
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
            StringComparer.Ordinal);
        if (ownerNativeFinalizationBridge)
        {
            custodyProperties.Add("nativeWindowsFinalizedEvidence");
        }
        if (ownerNativeStageAuthoritySeedBridge)
        {
            custodyProperties.Add("generationProjection");
        }
        if (!ExactPropertySet(custody, custodyProperties))
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
        bool unsignedWindowsFreshDeltaProfile =
            ValidateUnsignedWindowsFreshDeltaManifestPair(
                canonicalDocument.RootElement,
                compatibilityDocument.RootElement,
                candidate.Version,
                allowGenerationProjection: ownerNativeStageAuthoritySeedBridge);
        ReleaseUploadCandidateIncumbentBinding incumbentBinding =
            ValidateUnsignedPublicationAndRegistry(
            custody,
            canonicalDocument.RootElement,
            canonicalManifest,
                compatibilityManifest,
                candidate,
                inventory,
                unsignedWindowsFreshDeltaProfile,
                ownerNativeFinalizationBridge,
                ownerNativeStageAuthoritySeedBridge);
        ReleaseUploadCandidateNativeEvidenceBinding? nativeEvidenceBinding = null;
        if (ownerNativeFinalizationBridge)
        {
            JsonElement unsignedPublicationEvidence = RequireObject(
                custody,
                "unsignedPublicationEvidence");
            string producerSourceCommit = RequireString(
                unsignedPublicationEvidence,
                "sourceSha");
            byte[] sourceCanonicalManifest =
                DecodeUnsignedPublicationEvidenceFile(
                    unsignedPublicationEvidence,
                    "transport/source-publication/RELEASE_CHANNEL.generated.json");
            byte[] sourceCompatibilityManifest =
                DecodeUnsignedPublicationEvidenceFile(
                    unsignedPublicationEvidence,
                    "transport/source-publication/releases.json");
            IReadOnlyDictionary<string, ReleaseUploadCandidateInventoryRow>
                expectedNativeContentRows =
                    BuildExpectedUnsignedNativeContentRows(
                        unsignedPublicationEvidence,
                        inventory);
            JsonElement nativeEvidence = RequireObject(
                custody,
                "nativeWindowsFinalizedEvidence");
            CandidateNativePackage nativePackage = ValidateCandidateNativeEvidence(
                nativeEvidence,
                canonicalDocument.RootElement,
                candidate,
                inventory,
                now,
                allowUnsigned: true,
                unsignedSourceCanonicalManifest: sourceCanonicalManifest,
                unsignedSourceCompatibilityManifest: sourceCompatibilityManifest,
                expectedUnsignedProducerSourceSha: producerSourceCommit,
                expectedUnsignedContentRows: expectedNativeContentRows);
            string nativeSourceCommit = RequireString(
                nativePackage.CaptureSource,
                "sha");
            if (!string.Equals(
                    RequireString(nativePackage.FinalizationSource, "sha"),
                    nativeSourceCommit,
                    StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    "unsigned native capture and finalization sources differ.");
            }
            nativeEvidenceBinding = new ReleaseUploadCandidateNativeEvidenceBinding(
                Sha256(JsonSerializer.SerializeToUtf8Bytes(nativeEvidence)),
                nativePackage.CaptureInventorySha256,
                nativeSourceCommit,
                candidate.BundleIdentitySha256,
                candidate.CanonicalManifestSha256,
                candidate.InventorySha256);
        }
        return new ReleaseUploadCandidateAuthority(
            snapshotId,
            snapshotSha256,
            authoritySha256,
            expiresAt,
            candidate,
            canonicalManifest,
            inventory,
            ExactIncomingDesktopScopeIsFreshDelta: true,
            IncumbentBinding: incumbentBinding,
            NativeEvidenceBinding: nativeEvidenceBinding);
    }

    private static byte[] DecodeUnsignedPublicationEvidenceFile(
        JsonElement evidence,
        string expectedPath)
    {
        byte[]? result = null;
        foreach (JsonElement entry in RequireArray(evidence, "files").EnumerateArray())
        {
            if (!string.Equals(
                    RequireString(entry, "path"),
                    expectedPath,
                    StringComparison.Ordinal))
            {
                continue;
            }
            if (result is not null)
            {
                throw new InvalidDataException(
                    "unsigned publication source-manifest custody is ambiguous.");
            }
            result = DecodeEmbedded(
                entry,
                $"unsigned publication {expectedPath}",
                expectedPath);
        }
        return result
            ?? throw new InvalidDataException(
                "unsigned publication source-manifest custody is incomplete.");
    }

    private static ReleaseUploadCandidateAuthority ParseUnsignedPreviewReadyCandidateAuthority(
        string snapshotId,
        string snapshotSha256,
        string authoritySha256,
        JsonElement root,
        DateTimeOffset now)
    {
        RequireExactProperties(
            root,
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
                "ownerNativeFinalizationBridgeAuthority",
                "ownerNativeStageAuthoritySeedBridgeAuthority",
                "platformScope",
                "previewPublicationReadinessBridgeAuthority",
                "publicationAuthorized",
                "publicationEligible",
                "releaseUploadAuthority",
                "routeAuthority",
                "signaturePolicy",
                "status"
            ],
            "preview-ready candidate import authority");
        RequireExactString(root, "contractName", UnsignedPreviewReadyCandidateContractName);
        RequireExactInt32(root, "contractVersion", 6);
        RequireExactString(root, "status", "candidate_import_ready");
        RequireBoolean(root, "candidateImportAuthority", expected: true);
        RequireBoolean(root, "candidateReviewAuthority", expected: true);
        RequireBoolean(root, "ownerNativeFinalizationBridgeAuthority", expected: true);
        RequireBoolean(root, "ownerNativeStageAuthoritySeedBridgeAuthority", expected: true);
        RequireBoolean(root, "previewPublicationReadinessBridgeAuthority", expected: true);
        RequireBoolean(root, "publicationAuthorized", expected: false);
        RequireBoolean(root, "publicationEligible", expected: false);
        RequireBoolean(root, "releaseUploadAuthority", expected: false);
        RequireBoolean(root, "deployAuthority", expected: false);
        RequireBoolean(root, "routeAuthority", expected: false);
        RequireBoolean(root, "codeDeploymentAuthority", expected: false);
        RequireBoolean(root, "crossRunBitReproducible", expected: false);
        RequireExactString(root, "platformScope", "windows_only");
        RequireExactString(root, "exactIncomingDesktopScope", CandidateExactIncomingDesktopScope);
        ValidateUnsignedSignaturePolicy(RequireObject(root, "signaturePolicy"));

        DateTimeOffset generatedAt = RequireUtcTimestamp(root, "generatedAtUtc");
        DateTimeOffset expiresAt = RequireUtcTimestamp(root, "expiresAtUtc");
        if (generatedAt > now.AddMinutes(5)
            || generatedAt < now.AddHours(-6).AddMinutes(-5)
            || expiresAt <= now
            || expiresAt > now.AddHours(6).AddMinutes(5)
            || expiresAt <= generatedAt
            || expiresAt > generatedAt.AddHours(6))
        {
            throw new InvalidDataException(
                "preview-ready candidate import authority is expired or future-dated");
        }

        JsonElement candidateElement = RequireObject(root, "candidate");
        RequireExactProperties(
            candidateElement,
            [
                "bundleIdentitySha256",
                "canonicalManifestSha256",
                "fileCount",
                "inventorySha256",
                "totalBytes",
                "version"
            ],
            "preview-ready candidate identity");
        string version = RequireString(candidateElement, "version");
        if (!VersionPattern.IsMatch(version))
        {
            throw new InvalidDataException("preview-ready candidate version is invalid");
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
            throw new InvalidDataException("preview-ready candidate bundle identity drifted");
        }

        JsonElement custody = RequireObject(root, "custody");
        RequireExactProperties(
            custody,
            [
                "canonicalManifest",
                "compatibilityManifest",
                "generationProjection",
                "inventory",
                "nativeWindowsFinalizedEvidence",
                "preprojectionCanonicalManifest",
                "preprojectionCompatibilityManifest",
                "publicationReadinessReceipt",
                "sourceCandidateAuthority"
            ],
            "preview-ready candidate custody");
        byte[] canonicalManifest = DecodeEmbedded(
            RequireObject(custody, "canonicalManifest"),
            "preview-ready canonical manifest",
            "RELEASE_CHANNEL.generated.json");
        byte[] compatibilityManifest = DecodeEmbedded(
            RequireObject(custody, "compatibilityManifest"),
            "preview-ready compatibility manifest",
            "releases.json");
        byte[] inventoryBytes = DecodeEmbedded(
            RequireObject(custody, "inventory"),
            "preview-ready candidate inventory",
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
                string.Equals(row.Path, "RELEASE_CHANNEL.generated.json", StringComparison.Ordinal)
                && string.Equals(row.Sha256, candidate.CanonicalManifestSha256, StringComparison.Ordinal)
                && row.SizeBytes == canonicalManifest.LongLength)
            || !inventory.Any(row =>
                string.Equals(row.Path, "releases.json", StringComparison.Ordinal)
                && string.Equals(row.Sha256, Sha256(compatibilityManifest), StringComparison.Ordinal)
                && row.SizeBytes == compatibilityManifest.LongLength))
        {
            throw new InvalidDataException("preview-ready candidate inventory summary drifted");
        }

        byte[] sourceAuthorityBytes = DecodeEmbedded(
            RequireObject(custody, "sourceCandidateAuthority"),
            "source v4 candidate authority",
            "RELEASE_UPLOAD_CANDIDATE_AUTHORITY.source-v4.generated.json");
        string sourceAuthoritySha256 = Sha256(sourceAuthorityBytes);
        ReleaseUploadCandidateAuthority sourceAuthority = ParseCandidateAuthority(
            snapshotId,
            snapshotSha256,
            sourceAuthoritySha256,
            sourceAuthorityBytes,
            now);
        if (sourceAuthority.NativeEvidenceBinding is null
            || sourceAuthority.IncumbentBinding is null
            || sourceAuthority.PublicationReadinessBinding is not null
            || expiresAt > sourceAuthority.ExpiresAtUtc)
        {
            throw new InvalidDataException(
                "preview-ready authority is not bounded by one fresh native v4 predecessor");
        }

        using JsonDocument sourceAuthorityDocument = ParseStrictObject(
            sourceAuthorityBytes,
            "source v4 candidate authority");
        JsonElement sourceCustody = RequireObject(sourceAuthorityDocument.RootElement, "custody");
        byte[] sourceCompatibilityManifest = DecodeEmbedded(
            RequireObject(sourceCustody, "compatibilityManifest"),
            "source v4 compatibility manifest",
            "releases.json");
        byte[] nativeEvidenceBytes = DecodeEmbedded(
            RequireObject(custody, "nativeWindowsFinalizedEvidence"),
            "preview-ready native Windows evidence",
            "proof/windows-native/UNSIGNED_WINDOWS_PREVIEW_NATIVE_FINALIZED_EVIDENCE.generated.json");
        using JsonDocument nativeEvidenceDocument = ParseStrictObject(
            nativeEvidenceBytes,
            "preview-ready native Windows evidence");
        JsonNode? heldNative = JsonNode.Parse(
            JsonSerializer.SerializeToUtf8Bytes(
                RequireObject(sourceCustody, "nativeWindowsFinalizedEvidence")));
        JsonNode? suppliedNative = JsonNode.Parse(nativeEvidenceBytes);
        if (heldNative is null
            || suppliedNative is null
            || !JsonNode.DeepEquals(heldNative, suppliedNative))
        {
            throw new InvalidDataException(
                "preview-ready authority substituted different native Windows evidence");
        }

        byte[] readinessReceiptBytes = DecodeEmbedded(
            RequireObject(custody, "publicationReadinessReceipt"),
            "Registry preview publication readiness receipt",
            "PREVIEW_PUBLICATION_READINESS.generated.json");
        using JsonDocument readinessReceiptDocument = ParseStrictObject(
            readinessReceiptBytes,
            "Registry preview publication readiness receipt");
        JsonElement readiness = readinessReceiptDocument.RootElement;
        RequireExactProperties(
            readiness,
            [
                "canonicalManifest",
                "compatibilityManifest",
                "contractName",
                "contractVersion",
                "deployAuthority",
                "generatedAtUtc",
                "localizationGateSha256",
                "nativeWindowsEvidenceSha256",
                "platforms",
                "publicationEligible",
                "registryCommit",
                "releaseProofSha256",
                "releaseUploadAuthority",
                "releaseVersion",
                "routeAuthority",
                "sourceCandidateAuthoritySha256",
                "sourceCanonicalManifestSha256",
                "sourceCompatibilityManifestSha256",
                "status"
            ],
            "Registry preview publication readiness receipt");
        RequireExactString(readiness, "contractName", PreviewPublicationReadinessContractName);
        RequireExactInt32(readiness, "contractVersion", 1);
        RequireExactString(readiness, "status", "preview_ready");
        RequireExactString(readiness, "releaseVersion", candidate.Version);
        RequireExactString(readiness, "sourceCandidateAuthoritySha256", sourceAuthoritySha256);
        RequireExactString(
            readiness,
            "sourceCanonicalManifestSha256",
            Sha256(sourceAuthority.CanonicalManifestBytes));
        RequireExactString(
            readiness,
            "sourceCompatibilityManifestSha256",
            Sha256(sourceCompatibilityManifest));
        RequireExactString(readiness, "nativeWindowsEvidenceSha256", Sha256(nativeEvidenceBytes));
        _ = RequireSha256(readiness, "releaseProofSha256");
        _ = RequireSha256(readiness, "localizationGateSha256");
        string registryCommit = RequireString(readiness, "registryCommit");
        if (registryCommit.Length != 40
            || registryCommit.Any(static character =>
                character is not (>= '0' and <= '9') and not (>= 'a' and <= 'f')))
        {
            throw new InvalidDataException("Registry readiness commit is invalid");
        }
        JsonElement platforms = RequireArray(readiness, "platforms");
        if (platforms.GetArrayLength() != 2
            || platforms[0].GetString() != "linux"
            || platforms[1].GetString() != "windows")
        {
            throw new InvalidDataException("Registry readiness platform scope drifted");
        }
        RequireBoolean(readiness, "publicationEligible", expected: true);
        RequireBoolean(readiness, "routeAuthority", expected: true);
        RequireBoolean(readiness, "releaseUploadAuthority", expected: false);
        RequireBoolean(readiness, "deployAuthority", expected: false);
        DateTimeOffset readinessGeneratedAt = RequireUtcTimestamp(readiness, "generatedAtUtc");
        if (readinessGeneratedAt > generatedAt
            || generatedAt - readinessGeneratedAt > TimeSpan.FromHours(6))
        {
            throw new InvalidDataException("Registry readiness receipt is stale or future-dated");
        }

        byte[] preprojectionCanonical = DecodeEmbedded(
            RequireObject(custody, "preprojectionCanonicalManifest"),
            "preview-ready preprojection canonical manifest",
            "preprojection/RELEASE_CHANNEL.generated.json");
        byte[] preprojectionCompatibility = DecodeEmbedded(
            RequireObject(custody, "preprojectionCompatibilityManifest"),
            "preview-ready preprojection compatibility manifest",
            "preprojection/releases.json");
        ValidateReadinessOutputReference(
            RequireObject(readiness, "canonicalManifest"),
            "RELEASE_CHANNEL.generated.json",
            preprojectionCanonical,
            "canonical manifest");
        ValidateReadinessOutputReference(
            RequireObject(readiness, "compatibilityManifest"),
            "releases.json",
            preprojectionCompatibility,
            "compatibility manifest");

        using var sourceCanonical = new CandidateEvidenceDocument(
            ParseStrictObject(preprojectionCanonical, "preview-ready preprojection canonical manifest"),
            preprojectionCanonical,
            Sha256(preprojectionCanonical),
            preprojectionCanonical.LongLength);
        using var sourceCompatibility = new CandidateEvidenceDocument(
            ParseStrictObject(preprojectionCompatibility, "preview-ready preprojection compatibility manifest"),
            preprojectionCompatibility,
            Sha256(preprojectionCompatibility),
            preprojectionCompatibility.LongLength);
        _ = ValidateNativeStageGenerationProjection(
            RequireObject(custody, "generationProjection"),
            sourceCanonical,
            sourceCompatibility,
            ParseStrictObject(canonicalManifest, "preview-ready canonical manifest").RootElement,
            canonicalManifest,
            compatibilityManifest,
            inventory);

        using JsonDocument canonicalDocument = ParseStrictObject(
            canonicalManifest,
            "preview-ready canonical manifest");
        using JsonDocument compatibilityDocument = ParseStrictObject(
            compatibilityManifest,
            "preview-ready compatibility manifest");
        ValidatePreviewReadyManifestPair(
            canonicalDocument.RootElement,
            compatibilityDocument.RootElement,
            candidate.Version);

        var readinessBinding = new ReleaseUploadCandidatePublicationReadinessBinding(
            Sha256(readinessReceiptBytes),
            sourceAuthoritySha256,
            Sha256(sourceAuthority.CanonicalManifestBytes),
            Sha256(sourceCompatibilityManifest),
            Sha256(preprojectionCanonical),
            Sha256(preprojectionCompatibility));
        ReleaseUploadCandidateNativeEvidenceBinding sourceNative =
            sourceAuthority.NativeEvidenceBinding!;
        var nativeBinding = new ReleaseUploadCandidateNativeEvidenceBinding(
            Sha256(nativeEvidenceBytes),
            sourceNative.CaptureInventorySha256,
            sourceNative.SourceCommit,
            candidate.BundleIdentitySha256,
            candidate.CanonicalManifestSha256,
            candidate.InventorySha256);
        return new ReleaseUploadCandidateAuthority(
            snapshotId,
            snapshotSha256,
            authoritySha256,
            expiresAt,
            candidate,
            canonicalManifest,
            inventory,
            ExactIncomingDesktopScopeIsFreshDelta: true,
            IncumbentBinding: sourceAuthority.IncumbentBinding,
            NativeEvidenceBinding: nativeBinding,
            PublicationReadinessBinding: readinessBinding);
    }

    private static void ValidateReadinessOutputReference(
        JsonElement reference,
        string path,
        byte[] payload,
        string label)
    {
        RequireExactProperties(reference, ["path", "sha256", "sizeBytes"], label);
        RequireExactString(reference, "path", path);
        RequireExactString(reference, "sha256", Sha256(payload));
        if (RequireNonNegativeInt64(reference, "sizeBytes") != payload.LongLength)
        {
            throw new InvalidDataException($"Registry readiness {label} size drifted");
        }
    }

    private static void RequireExactProperties(
        JsonElement value,
        IEnumerable<string> expected,
        string label)
    {
        if (!ExactPropertySet(value, expected.ToHashSet(StringComparer.Ordinal)))
        {
            throw new InvalidDataException($"{label} property set drifted");
        }
    }

    internal static void ValidatePreviewReadyManifestPair(
        JsonElement canonical,
        JsonElement compatibility,
        string version)
    {
        foreach ((string label, JsonElement manifest) in new[]
                 {
                     ("canonical", canonical),
                     ("compatibility", compatibility)
                 })
        {
            ValidateUnsignedManifestIdentity(manifest, version, $"preview-ready {label} manifest");
            RequireExactString(manifest, "projectionProfile", UnsignedWindowsPreviewReadyProjectionProfile);
            RequireExactString(manifest, "status", "published");
            RequireExactString(manifest, "rolloutState", "promoted_preview");
            RequireExactString(manifest, "supportabilityState", "preview_supported");
            RequireBoolean(manifest, "publicationEligible", expected: true);
            RequireBoolean(manifest, "routeAuthority", expected: true);
            RequireBoolean(manifest, "releaseUploadAuthority", expected: false);
            RequireBoolean(manifest, "deployAuthority", expected: false);
            JsonElement proof = RequireObject(manifest, "releaseProof");
            string proofStatus = RequireString(proof, "status");
            if (proofStatus is not "pass" and not "passed" and not "ready")
            {
                throw new InvalidDataException(
                    $"preview-ready {label} manifest release proof is not passing");
            }
        }

        JsonElement coverage = RequireObject(canonical, "desktopTupleCoverage");
        RequireBoolean(coverage, "complete", expected: true);
        RequireBoolean(coverage, "routeAuthority", expected: true);
        foreach (string field in new[]
                 {
                     "missingRequiredPlatforms",
                     "missingRequiredHeads",
                     "missingRequiredPlatformHeadPairs",
                     "missingRequiredPlatformHeadRidTuples"
                 })
        {
            if (RequireArray(coverage, field).GetArrayLength() != 0)
            {
                throw new InvalidDataException(
                    $"preview-ready desktop coverage still reports {field}");
            }
        }
        JsonElement routes = RequireArray(coverage, "desktopRouteTruth");
        var readyPlatforms = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonElement route in routes.EnumerateArray())
        {
            if (RequireString(route, "routeRole") != "primary")
            {
                continue;
            }
            RequireExactString(route, "head", "avalonia");
            RequireExactString(route, "promotionState", "promoted");
            RequireExactString(route, "publicationState", "published");
            RequireExactString(route, "updateEligibility", "eligible");
            RequireExactString(route, "installPosture", "installer_first");
            RequireExactString(route, "revokeState", "not_revoked");
            RequireBoolean(route, "routeAuthority", expected: true);
            _ = RequireString(route, "artifactId");
            _ = RequireString(route, "publicInstallRoute");
            readyPlatforms.Add(RequireString(route, "platform"));
        }
        if (!readyPlatforms.SetEquals(["linux", "windows"]))
        {
            throw new InvalidDataException(
                "preview-ready manifest does not authorize exactly Linux and Windows primary routes");
        }

        JsonElement artifacts = RequireArray(canonical, "artifacts");
        var artifactIds = artifacts.EnumerateArray()
            .Select(artifact => RequireString(artifact, "artifactId"))
            .ToHashSet(StringComparer.Ordinal);
        if (!artifactIds.SetEquals(
                ["avalonia-linux-x64-installer", "avalonia-win-x64-installer"]))
        {
            throw new InvalidDataException(
                "preview-ready manifest artifact scope drifted");
        }
        JsonElement bindings = RequireArray(canonical, "artifactPublicationBindings");
        var publishedBindings = bindings.EnumerateArray()
            .Where(binding => RequireString(binding, "publicationState") == "published")
            .Select(binding => RequireString(binding, "artifactId"))
            .ToHashSet(StringComparer.Ordinal);
        if (!publishedBindings.SetEquals(artifactIds))
        {
            throw new InvalidDataException(
                "preview-ready manifest has an unpublished artifact binding");
        }
    }

    private static IReadOnlyDictionary<string, ReleaseUploadCandidateInventoryRow>
        BuildExpectedUnsignedNativeContentRows(
        JsonElement evidence,
        IReadOnlyList<ReleaseUploadCandidateInventoryRow> candidateInventory)
    {
        var result = new Dictionary<string, ReleaseUploadCandidateInventoryRow>(
            StringComparer.Ordinal);
        foreach ((string evidencePath, string contentPath) in new[]
                 {
                     (
                         "PREVIEW_NIGHTLY_UNSIGNED_COMPOSITION.proposed.json",
                         "PREVIEW_NIGHTLY_UNSIGNED_COMPOSITION.proposed.json"),
                     (
                         "provenance/UI_FRESH_PACKAGE_PLANE.generated.json",
                         "provenance/UI_FRESH_PACKAGE_PLANE.generated.json"),
                     (
                         "provenance/config/package-plane.lock.json",
                         "provenance/config/package-plane.lock.json"),
                     (
                         "provenance/config/windows-native-bootstrap-toolchain.lock.json",
                         "provenance/config/windows-native-bootstrap-toolchain.lock.json"),
                     (
                         "provenance/retained-windows-publish-closure/manifest.json",
                         "provenance/retained-windows-publish-closure/manifest.json"),
                     (
                         "transport/source-publication/RELEASE_CHANNEL.generated.json",
                         "publication/RELEASE_CHANNEL.generated.json"),
                     (
                         "transport/source-publication/releases.json",
                         "publication/releases.json")
                 })
        {
            byte[] bytes = DecodeUnsignedPublicationEvidenceFile(
                evidence,
                evidencePath);
            result.Add(
                contentPath,
                new ReleaseUploadCandidateInventoryRow(
                    contentPath,
                    bytes.LongLength,
                    Sha256(bytes)));
        }
        foreach (string candidatePath in new[]
                 {
                     "files/chummer-avalonia-win-x64-installer.exe",
                     "files/chummer-avalonia-win-x64-payload.zip",
                     "files/chummer-avalonia-win-x64-payload.zip.json"
                 })
        {
            ReleaseUploadCandidateInventoryRow candidateRow =
                candidateInventory.Single(row => string.Equals(
                    row.Path,
                    candidatePath,
                    StringComparison.Ordinal));
            string contentPath = $"publication/{candidatePath}";
            result.Add(
                contentPath,
                candidateRow with { Path = contentPath });
        }
        return result;
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

    private static ReleaseUploadCandidateIncumbentBinding ValidateUnsignedPublicationAndRegistry(
        JsonElement custody,
        JsonElement canonical,
        byte[] canonicalBytes,
        byte[] compatibilityBytes,
        ReleaseUploadCandidateIdentity candidate,
        IReadOnlyList<ReleaseUploadCandidateInventoryRow> inventory,
        bool unsignedWindowsFreshDeltaProfile,
        bool ownerNativeFinalizationBridge,
        bool ownerNativeStageAuthoritySeedBridge)
    {
        JsonElement evidence = RequireObject(custody, "unsignedPublicationEvidence");
        var evidenceKeys = new HashSet<string>(
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
                    StringComparer.Ordinal);
        if (unsignedWindowsFreshDeltaProfile)
        {
            evidenceKeys.Add("projectionProfile");
        }
        if (!ExactPropertySet(evidence, evidenceKeys))
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
        if (unsignedWindowsFreshDeltaProfile)
        {
            RequireExactString(
                evidence,
                "projectionProfile",
                UnsignedWindowsFreshDeltaProjectionProfile);
        }
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
            const string sourceCanonicalPath =
                "transport/source-publication/RELEASE_CHANNEL.generated.json";
            const string sourceCompatibilityPath =
                "transport/source-publication/releases.json";
            const string nativeCompositionPath =
                "PREVIEW_NIGHTLY_UNSIGNED_COMPOSITION.proposed.json";
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
            if (unsignedWindowsFreshDeltaProfile)
            {
                expectedPaths.Add(sourceCanonicalPath);
                expectedPaths.Add(sourceCompatibilityPath);
            }
            if (ownerNativeFinalizationBridge)
            {
                expectedPaths.Add(nativeCompositionPath);
            }
            if (!expectedPaths.SetEquals(documents.Keys)
                || !ownerNativeStageAuthoritySeedBridge
                && (!CryptographicOperations.FixedTimeEquals(
                        documents["RELEASE_CHANNEL.generated.json"].Bytes,
                        canonicalBytes)
                    || !CryptographicOperations.FixedTimeEquals(
                        documents["releases.json"].Bytes,
                        compatibilityBytes)))
            {
                throw new InvalidDataException("unsigned publication evidence custody drifted");
            }
            CandidateEvidenceDocument scopeDocument = documents[scopePath];
            RequireExactString(evidence, "publicationScopeSha256", scopeDocument.Sha256);
            JsonElement scope = scopeDocument.Root;
            JsonElement validationCanonical = canonical;
            byte[] validationCanonicalBytes = canonicalBytes;
            byte[] validationCompatibilityBytes = compatibilityBytes;
            IReadOnlyList<ReleaseUploadCandidateInventoryRow> validationInventory = inventory;
            if (ownerNativeStageAuthoritySeedBridge)
            {
                CandidateEvidenceDocument sourceCanonical =
                    documents["RELEASE_CHANNEL.generated.json"];
                CandidateEvidenceDocument sourceCompatibility =
                    documents["releases.json"];
                validationCanonical = sourceCanonical.Root;
                validationCanonicalBytes = sourceCanonical.Bytes;
                validationCompatibilityBytes = sourceCompatibility.Bytes;
                validationInventory = ValidateNativeStageGenerationProjection(
                    RequireObject(custody, "generationProjection"),
                    sourceCanonical,
                    sourceCompatibility,
                    canonical,
                    canonicalBytes,
                    compatibilityBytes,
                    inventory);
            }
            ValidateUnsignedScope(
                scope,
                sourceSha,
                candidate,
                validationInventory,
                validationCanonical,
                validationCanonicalBytes,
                validationCompatibilityBytes,
                documents,
                packageLockPath,
                packageReceiptPath,
                retainedManifestPath,
                nativeLockPath,
                unsignedWindowsFreshDeltaProfile);
            return ValidateUnsignedRegistry(
                custody,
                scope,
                scopeDocument.Bytes,
                evidence,
                validationCanonical,
                validationCanonicalBytes,
                validationCompatibilityBytes,
                candidate,
                documents,
                packageLockPath,
                packageReceiptPath,
                retainedManifestPath,
                nativeLockPath,
                unsignedWindowsFreshDeltaProfile,
                sourceCanonicalPath,
                sourceCompatibilityPath);
        }
        finally
        {
            foreach (CandidateEvidenceDocument document in documents.Values)
            {
                document.Dispose();
            }
        }
    }

    private static IReadOnlyList<ReleaseUploadCandidateInventoryRow>
        ValidateNativeStageGenerationProjection(
            JsonElement projection,
            CandidateEvidenceDocument sourceCanonical,
            CandidateEvidenceDocument sourceCompatibility,
            JsonElement projectedCanonical,
            byte[] projectedCanonicalBytes,
            byte[] projectedCompatibilityBytes,
            IReadOnlyList<ReleaseUploadCandidateInventoryRow> inventory)
    {
        if (!ExactPropertySet(
                projection,
                new HashSet<string>(
                    [
                        "contractName",
                        "contractVersion",
                        "status",
                        "generationId",
                        "evaluatedAtUtc",
                        "sourceCanonicalManifestSha256",
                        "sourceCompatibilityManifestSha256",
                        "projectedCanonicalManifestSha256",
                        "projectedCompatibilityManifestSha256",
                        "authoritySeed"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "native-stage generation projection property set drifted");
        }
        RequireExactString(
            projection,
            "contractName",
            NativeStageGenerationProjectionContractName);
        RequireExactInt32(projection, "contractVersion", 1);
        RequireExactString(projection, "status", "passed");
        string generationId = RequireString(projection, "generationId");
        _ = RequireUtcTimestamp(projection, "evaluatedAtUtc");
        RequireExactString(
            projection,
            "sourceCanonicalManifestSha256",
            sourceCanonical.Sha256);
        RequireExactString(
            projection,
            "sourceCompatibilityManifestSha256",
            sourceCompatibility.Sha256);
        RequireExactString(
            projection,
            "projectedCanonicalManifestSha256",
            Sha256(projectedCanonicalBytes));
        RequireExactString(
            projection,
            "projectedCompatibilityManifestSha256",
            Sha256(projectedCompatibilityBytes));
        RequireExactString(projectedCanonical, "generationId", generationId);

        PublicReleaseManifestDto sourcePublicManifest =
            JsonSerializer.Deserialize<PublicReleaseManifestDto>(
                sourceCompatibility.Bytes,
                new JsonSerializerOptions(JsonSerializerDefaults.Web)
                {
                    PropertyNameCaseInsensitive = true
                })
            ?? throw new InvalidDataException(
                "native-stage source compatibility manifest is invalid");
        JsonObject sourceCanonicalObject = JsonNode.Parse(sourceCanonical.Bytes)
            as JsonObject
            ?? throw new InvalidDataException(
                "native-stage source canonical manifest is invalid");
        JsonObject sourceCompatibilityObject =
            JsonNode.Parse(sourceCompatibility.Bytes) as JsonObject
            ?? throw new InvalidDataException(
                "native-stage source compatibility manifest is invalid");
        byte[] expectedCanonical =
            ReleaseBundlePromotionService.ProjectRegistryManifestForGeneration(
                sourceCanonicalObject,
                generationId,
                sourcePublicManifest);
        byte[] expectedCompatibility =
            ReleaseBundlePromotionService.ProjectRegistryManifestForGeneration(
                sourceCompatibilityObject,
                generationId,
                sourcePublicManifest);
        if (!CryptographicOperations.FixedTimeEquals(
                expectedCanonical,
                projectedCanonicalBytes)
            || !CryptographicOperations.FixedTimeEquals(
                expectedCompatibility,
                projectedCompatibilityBytes))
        {
            throw new InvalidDataException(
                "native-stage manifests are not the exact server generation projection");
        }

        var inventoryByPath = inventory.ToDictionary(
            static row => row.Path,
            StringComparer.Ordinal);
        JsonElement authoritySeed = RequireObject(projection, "authoritySeed");
        var seedPaths = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["CURRENT.json"] = "release-evidence/CURRENT.json",
            ["RELEASE_DECISION.json"] = "release-evidence/RELEASE_DECISION.json",
            ["SNAPSHOT.json"] = "release-evidence/SNAPSHOT.json"
        };
        if (!ExactPropertySet(
                authoritySeed,
                new HashSet<string>(seedPaths.Keys, StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "native-stage authority seed property set drifted");
        }
        foreach ((string name, string path) in seedPaths)
        {
            JsonElement reference = RequireObject(authoritySeed, name);
            if (!ExactPropertySet(
                    reference,
                    new HashSet<string>(
                        ["path", "sha256", "sizeBytes"],
                        StringComparer.Ordinal))
                || !inventoryByPath.TryGetValue(
                    path,
                    out ReleaseUploadCandidateInventoryRow? held))
            {
                throw new InvalidDataException(
                    "native-stage authority seed inventory drifted");
            }
            RequireExactString(reference, "path", path);
            RequireExactString(reference, "sha256", held.Sha256);
            if (RequireNonNegativeInt64(reference, "sizeBytes") != held.SizeBytes)
            {
                throw new InvalidDataException(
                    "native-stage authority seed size drifted");
            }
        }
        string[] unexpectedEvidence = inventoryByPath.Keys
            .Where(static path => path.StartsWith(
                "release-evidence/",
                StringComparison.Ordinal))
            .Except(seedPaths.Values, StringComparer.Ordinal)
            .ToArray();
        if (unexpectedEvidence.Length != 0)
        {
            throw new InvalidDataException(
                "native-stage candidate contains unbounded release evidence");
        }

        return inventory
            .Where(row => !seedPaths.Values.Contains(row.Path, StringComparer.Ordinal))
            .Select(row => row.Path switch
            {
                "RELEASE_CHANNEL.generated.json" => row with
                {
                    Sha256 = sourceCanonical.Sha256,
                    SizeBytes = sourceCanonical.SizeBytes
                },
                "releases.json" => row with
                {
                    Sha256 = sourceCompatibility.Sha256,
                    SizeBytes = sourceCompatibility.SizeBytes
                },
                _ => row
            })
            .OrderBy(static row => row.Path, StringComparer.Ordinal)
            .ToArray();
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
        string nativeLockPath,
        bool unsignedWindowsFreshDeltaProfile)
    {
        var scopeKeys = new HashSet<string>(
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
                    StringComparer.Ordinal);
        if (unsignedWindowsFreshDeltaProfile)
        {
            scopeKeys.Add("projectionProfile");
        }
        if (!ExactPropertySet(scope, scopeKeys))
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
        if (unsignedWindowsFreshDeltaProfile)
        {
            RequireExactString(
                scope,
                "projectionProfile",
                UnsignedWindowsFreshDeltaProjectionProfile);
        }
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
        if (fresh.GetArrayLength() != (unsignedWindowsFreshDeltaProfile ? 3 : 2))
        {
            throw new InvalidDataException("unsigned UI fresh delta cardinality drifted");
        }
        string[] roles = unsignedWindowsFreshDeltaProfile
            ? ["installer", "bootstrap_payload", "bootstrap_payload_sidecar"]
            : ["installer", "bootstrap_payload"];
        string[] names = unsignedWindowsFreshDeltaProfile
            ?
            [
                "chummer-avalonia-win-x64-installer.exe",
                "chummer-avalonia-win-x64-payload.zip",
                "chummer-avalonia-win-x64-payload.zip.json"
            ]
            :
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
        IReadOnlySet<string> managedRetainedPaths =
            ValidateUnsignedCanonicalWindows(canonical, inventoryByPath, fresh);

        var expectedPaths = new HashSet<string>(
            ["RELEASE_CHANNEL.generated.json", "releases.json", .. freshPaths],
            StringComparer.Ordinal);
        var retainedPaths = new HashSet<string>(StringComparer.Ordinal);
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
                || !retainedPaths.Add(path)
                || !string.Equals(
                    kind,
                    managedRetainedPaths.Contains(path)
                        ? "managed_artifact"
                        : "ancillary",
                    StringComparison.Ordinal)
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
        if (!expectedPaths.SetEquals(inventoryByPath.Keys)
            || !managedRetainedPaths.IsSubsetOf(retainedPaths))
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

    internal static IReadOnlySet<string> ValidateUnsignedCanonicalWindows(
        JsonElement canonical,
        IReadOnlyDictionary<string, ReleaseUploadCandidateInventoryRow> inventory,
        JsonElement fresh)
    {
        JsonElement artifacts = RequireArray(canonical, "artifacts");
        var manifestPaths = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonElement artifact in artifacts.EnumerateArray())
        {
            string fileName = RequireString(artifact, "fileName");
            string artifactPath = $"files/{fileName}";
            if (fileName.Contains('/')
                || fileName.Contains('\\')
                || !manifestPaths.Add(artifactPath)
                || !inventory.TryGetValue(
                    artifactPath,
                    out ReleaseUploadCandidateInventoryRow? artifactInventory)
                || !string.Equals(
                    RequireSha256(artifact, "sha256"),
                    artifactInventory.Sha256,
                    StringComparison.Ordinal)
                || RequireNonNegativeInt64(artifact, "sizeBytes")
                   != artifactInventory.SizeBytes
                || artifactInventory.SizeBytes <= 0)
            {
                throw new InvalidDataException("unsigned canonical artifact bytes drifted");
            }
        }

        string[] requiredHeads = RequirePromotedDesktopHeads(canonical);
        var requiredHeadSet = new HashSet<string>(requiredHeads, StringComparer.Ordinal);
        var managedRetainedPaths = new HashSet<string>(StringComparer.Ordinal);
        int windowsCount = 0;
        foreach (JsonElement artifact in artifacts.EnumerateArray())
        {
            string head = RequireString(artifact, "head");
            string platform = RequireString(artifact, "platform");
            string rid = RequireString(artifact, "rid");
            string kind = RequireString(artifact, "kind");
            string fileName = RequireString(artifact, "fileName");
            string artifactPath = $"files/{fileName}";
            if (!HeadPattern.IsMatch(head) || !RetainedDesktopHeads.Contains(head))
            {
                throw new InvalidDataException(
                    "unsigned canonical artifact head is invalid");
            }
            if (string.Equals(platform, "windows", StringComparison.Ordinal)
                && !requiredHeadSet.Contains(head))
            {
                throw new InvalidDataException(
                    "unsigned canonical Windows artifact is outside requiredDesktopHeads");
            }
            bool validTuple = platform switch
            {
                "windows" => string.Equals(rid, WindowsRid, StringComparison.Ordinal)
                             && string.Equals(kind, "installer", StringComparison.Ordinal),
                "linux" => string.Equals(rid, "linux-x64", StringComparison.Ordinal)
                           && kind is "installer" or "archive",
                "macos" => rid is "osx-arm64" or "osx-x64"
                           && kind is "installer" or "archive",
                _ => false
            };
            if (!validTuple)
            {
                throw new InvalidDataException(
                    "unsigned canonical artifact is outside the exact desktop shelf scope");
            }
            if (!string.Equals(platform, "windows", StringComparison.Ordinal))
            {
                managedRetainedPaths.Add(artifactPath);
                continue;
            }
            windowsCount++;
            RequireExactString(artifact, "head", requiredHeads[0]);
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
        return managedRetainedPaths;
    }

    internal static bool ValidateUnsignedWindowsFreshDeltaManifestPair(
        JsonElement canonical,
        JsonElement compatibility,
        string expectedVersion,
        bool allowGenerationProjection = false)
    {
        string canonicalProfile = string.Empty;
        if (canonical.TryGetProperty(
                "projectionProfile",
                out JsonElement canonicalProfileElement))
        {
            if (canonicalProfileElement.ValueKind != JsonValueKind.String)
            {
                throw new InvalidDataException(
                    "unsigned canonical projectionProfile type drifted");
            }
            canonicalProfile = canonicalProfileElement.GetString()?.Trim()
                ?? string.Empty;
        }
        string compatibilityProfile = string.Empty;
        if (compatibility.TryGetProperty(
                "projectionProfile",
                out JsonElement compatibilityProfileElement))
        {
            if (compatibilityProfileElement.ValueKind != JsonValueKind.String)
            {
                throw new InvalidDataException(
                    "unsigned compatibility projectionProfile type drifted");
            }
            compatibilityProfile = compatibilityProfileElement.GetString()?.Trim()
                ?? string.Empty;
        }
        if (canonicalProfile.Length == 0 && compatibilityProfile.Length == 0)
        {
            return false;
        }
        if (!string.Equals(
                canonicalProfile,
                UnsignedWindowsFreshDeltaProjectionProfile,
                StringComparison.Ordinal)
            || !string.Equals(
                compatibilityProfile,
                UnsignedWindowsFreshDeltaProjectionProfile,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "unsigned candidate manifests publish a mismatched or unsupported projectionProfile");
        }

        JsonElement? sharedProof = null;
        JsonElement? sharedReview = null;
        JsonElement? sharedProvenance = null;
        foreach ((string label, JsonElement manifest) in new[]
                 {
                     ("canonical", canonical),
                     ("compatibility", compatibility)
                 })
        {
            RequireExactString(manifest, "version", expectedVersion);
            RequireExactString(manifest, "releaseVersion", expectedVersion);
            RequireExactString(manifest, "channel", "preview");
            RequireExactString(manifest, "channelId", "preview");
            RequireExactString(manifest, "platformScope", "windows_only");
            RequireExactString(manifest, "previewPolicy", "preview_policy");
            RequireExactString(manifest, "projectionStage", "prepared_candidate");
            RequireExactString(manifest, "status", "published");
            RequireExactString(manifest, "releaseDecisionStatus", "review_required");
            RequireExactString(manifest, "rolloutState", "coverage_incomplete");
            RequireExactString(manifest, "supportabilityState", "review_required");
            RequireBoolean(manifest, "crossRunBitReproducible", expected: false);
            foreach (string field in new[]
                     {
                         "publicationAuthorized",
                         "publicationEligible",
                         "releaseUploadAuthority",
                         "deployAuthority",
                         "deployAuthorized",
                         "uploadAuthorized",
                         "routeAuthority",
                         "codeDeploymentAuthority"
                     })
            {
                RequireBoolean(manifest, field, expected: false);
            }
            ValidateUnsignedManifestSignature(RequireObject(manifest, "signature"));
            ValidateUnsignedRecursiveAuthorityPosture(manifest, $"unsigned {label} manifest");

            string generatedAt = RequireMatchingAlias(
                manifest,
                "generatedAt",
                "generated_at",
                $"unsigned {label} generated time");
            _ = manifest.TryGetProperty("generatedAt", out _)
                ? RequireUtcTimestamp(manifest, "generatedAt")
                : RequireUtcTimestamp(manifest, "generated_at");

            JsonElement proof = RequireObject(manifest, "releaseProof");
            if (!ExactPropertySet(
                    proof,
                    new HashSet<string>(
                        ["baseUrl", "generatedAt", "journeysPassed", "proofRoutes", "status"],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException(
                    $"unsigned {label} releaseProof property set drifted");
            }
            RequireExactString(proof, "baseUrl", "https://chummer.run");
            RequireExactString(proof, "status", "review_required");
            _ = RequireUtcTimestamp(proof, "generatedAt");
            RequireExactString(proof, "generatedAt", generatedAt);
            if (RequireArray(proof, "journeysPassed").GetArrayLength() != 0
                || RequireArray(proof, "proofRoutes").GetArrayLength() != 0)
            {
                throw new InvalidDataException(
                    $"unsigned {label} releaseProof must remain minimal and review-required");
            }
            if (sharedProof.HasValue
                && !JsonSemanticEquals(sharedProof.Value, proof))
            {
                throw new InvalidDataException(
                    "unsigned manifest releaseProof documents disagree");
            }
            sharedProof = proof.Clone();

            string registryCommit = RequireMatchingAlias(
                manifest,
                "registryCommit",
                "registry_commit",
                $"unsigned {label} Registry commit");
            if (!CommitPattern.IsMatch(registryCommit))
            {
                throw new InvalidDataException(
                    $"unsigned {label} Registry commit is invalid");
            }
            JsonElement review = RequireObject(
                manifest,
                "codeDeployCurrentShelfAuthority");
            if (!ExactPropertySet(
                    review,
                    new HashSet<string>(
                        [
                            "authority",
                            "contract",
                            "evaluatedAt",
                            "incumbentSnapshotSha256",
                            "projectedArtifactCount",
                            "projectedArtifactInventorySha256",
                            "projectionProfile",
                            "registryCommit",
                            "sourceCanonicalManifestSha256",
                            "sourceCompatibilityManifestSha256",
                            "sourceShelfInventorySha256",
                            "status"
                        ],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException(
                    $"unsigned {label} code-deploy review shape drifted");
            }
            RequireBoolean(review, "authority", expected: false);
            RequireExactString(
                review,
                "contract",
                UnsignedWindowsCodeDeployReviewContract);
            RequireExactString(
                review,
                "projectionProfile",
                UnsignedWindowsFreshDeltaProjectionProfile);
            RequireExactString(review, "registryCommit", registryCommit);
            RequireExactString(review, "status", "review_required");
            _ = RequireUtcTimestamp(review, "evaluatedAt");
            RequireExactString(review, "evaluatedAt", generatedAt);
            _ = RequireSha256(review, "incumbentSnapshotSha256");
            _ = RequireSha256(review, "projectedArtifactInventorySha256");
            _ = RequireSha256(review, "sourceCanonicalManifestSha256");
            _ = RequireSha256(review, "sourceCompatibilityManifestSha256");
            _ = RequireSha256(review, "sourceShelfInventorySha256");
            _ = RequirePositiveInt64(review, "projectedArtifactCount");
            JsonElement provenance = RequireObject(
                manifest,
                "retainedIncumbentProvenance");
            if (sharedReview.HasValue
                && !JsonSemanticEquals(sharedReview.Value, review)
                || sharedProvenance.HasValue
                && !JsonSemanticEquals(sharedProvenance.Value, provenance))
            {
                throw new InvalidDataException(
                    "unsigned manifest review/provenance projections disagree");
            }
            sharedReview = review.Clone();
            sharedProvenance = provenance.Clone();
        }

        string? generationId = null;
        if (allowGenerationProjection)
        {
            generationId = RequireString(canonical, "generationId");
            RequireExactString(compatibility, "generationId", generationId);
        }
        JsonElement canonicalWindows = RequireSingleUnsignedWindowsArtifact(
            RequireArray(canonical, "artifacts"),
            compatibility: false,
            expectedVersion,
            generationId);
        JsonElement compatibilityWindows = RequireSingleUnsignedWindowsArtifact(
            RequireArray(compatibility, "downloads"),
            compatibility: true,
            expectedVersion,
            generationId);
        foreach (string field in new[]
                 {
                     "sha256", "sizeBytes", "payloadSha256", "payloadSizeBytes"
                 })
        {
            if (!canonicalWindows.TryGetProperty(field, out JsonElement canonicalValue)
                || !compatibilityWindows.TryGetProperty(field, out JsonElement compatibilityValue)
                || !JsonSemanticEquals(canonicalValue, compatibilityValue))
            {
                throw new InvalidDataException(
                    $"unsigned Windows manifest pair disagrees about {field}");
            }
        }
        if (!sharedReview.HasValue)
        {
            throw new InvalidDataException(
                "unsigned projected code-deploy review is missing");
        }
        if (!sharedProvenance.HasValue)
        {
            throw new InvalidDataException(
                "unsigned retained incumbent provenance is missing");
        }
        if (!allowGenerationProjection)
        {
            _ = ValidateUnsignedRetainedProjectedBindings(
                sharedProvenance.Value,
                canonical,
                compatibility);
        }
        ValidateUnsignedProjectedArtifactInventory(canonical, sharedReview.Value);
        return true;
    }

    private static void ValidateUnsignedProjectedArtifactInventory(
        JsonElement canonical,
        JsonElement review)
    {
        var inventory = new JsonArray();
        foreach (JsonElement artifact in RequireArray(canonical, "artifacts").EnumerateArray())
        {
            var row = new JsonObject
            {
                ["artifactId"] = RequireString(artifact, "artifactId"),
                ["head"] = RequireString(artifact, "head"),
                ["platform"] = RequireString(artifact, "platform"),
                ["rid"] = RequireString(artifact, "rid"),
                ["arch"] = RequireString(artifact, "arch"),
                ["kind"] = RequireString(artifact, "kind"),
                ["fileName"] = RequireString(artifact, "fileName"),
                ["sha256"] = RequireSha256(artifact, "sha256"),
                ["sizeBytes"] = RequirePositiveInt64(artifact, "sizeBytes")
            };
            bool hasPayloadFile = artifact.TryGetProperty(
                "payloadFileName",
                out JsonElement payloadFile)
                && payloadFile.ValueKind != JsonValueKind.Null;
            bool hasPayloadSha = artifact.TryGetProperty(
                "payloadSha256",
                out JsonElement payloadSha)
                && payloadSha.ValueKind != JsonValueKind.Null;
            bool hasPayloadSize = artifact.TryGetProperty(
                "payloadSizeBytes",
                out JsonElement payloadSize)
                && payloadSize.ValueKind != JsonValueKind.Null;
            if (hasPayloadFile || hasPayloadSha || hasPayloadSize)
            {
                if (!hasPayloadFile || !hasPayloadSha || !hasPayloadSize)
                {
                    throw new InvalidDataException(
                        "unsigned projected artifact inventory has a partial payload binding");
                }
                row["payloadFileName"] = RequireString(artifact, "payloadFileName");
                row["payloadSha256"] = RequireSha256(artifact, "payloadSha256");
                row["payloadSizeBytes"] = RequirePositiveInt64(
                    artifact,
                    "payloadSizeBytes");
            }
            inventory.Add(row);
        }
        using JsonDocument inventoryDocument = JsonDocument.Parse(
            Encoding.UTF8.GetBytes(inventory.ToJsonString()));
        if (RequirePositiveInt64(review, "projectedArtifactCount") != inventory.Count
            || !string.Equals(
                RequireSha256(review, "projectedArtifactInventorySha256"),
                UnsignedCompactSha256(inventoryDocument.RootElement),
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "unsigned projected artifact inventory review binding drifted");
        }
    }

    private static JsonElement RequireSingleUnsignedWindowsArtifact(
        JsonElement artifacts,
        bool compatibility,
        string expectedVersion,
        string? generationId)
    {
        JsonElement[] matches = artifacts.EnumerateArray()
            .Where(row =>
            {
                if (row.ValueKind != JsonValueKind.Object)
                {
                    return false;
                }
                string? artifactId;
                if (row.TryGetProperty("id", out JsonElement id))
                {
                    artifactId = id.ValueKind == JsonValueKind.String
                        ? id.GetString()
                        : null;
                }
                else if (row.TryGetProperty(
                             "artifactId",
                             out JsonElement directArtifactId))
                {
                    artifactId = directArtifactId.ValueKind == JsonValueKind.String
                        ? directArtifactId.GetString()
                        : null;
                }
                else
                {
                    artifactId = null;
                }
                return string.Equals(
                    artifactId,
                    "avalonia-win-x64-installer",
                    StringComparison.Ordinal);
            })
            .ToArray();
        if (matches.Length != 1)
        {
            throw new InvalidDataException(
                "unsigned Windows manifest artifact cardinality drifted");
        }
        JsonElement artifact = matches[0];
        RequireExactString(artifact, "artifactId", "avalonia-win-x64-installer");
        RequireExactString(artifact, "id", "avalonia-win-x64-installer");
        RequireExactString(artifact, "head", "avalonia");
        RequireExactString(artifact, "platform", "windows");
        RequireExactString(artifact, "arch", "x64");
        RequireExactString(artifact, "rid", WindowsRid);
        RequireExactString(artifact, "kind", "installer");
        RequireExactString(
            artifact,
            "fileName",
            "chummer-avalonia-win-x64-installer.exe");
        RequireExactString(
            artifact,
            "payloadFileName",
            "chummer-avalonia-win-x64-payload.zip");
        RequireExactString(artifact, "installerMode", "bootstrap");
        RequireExactString(artifact, "payloadAcquisitionMode", "download");
        RequireExactString(artifact, "channel", "preview");
        RequireExactString(artifact, "channelId", "preview");
        RequireExactString(artifact, "version", expectedVersion);
        RequireExactString(artifact, "releaseVersion", expectedVersion);
        RequireExactString(artifact, "platformScope", "windows_only");
        RequireExactString(artifact, "previewPolicy", "preview_policy");
        RequireExactString(artifact, "installAccessClass", "open_public");
        RequireBoolean(artifact, "crossRunBitReproducible", expected: false);
        RequireExactString(artifact, "publicationDisposition", "delta");
        ValidateUnsignedManifestSignature(RequireObject(artifact, "signature"));
        string routePrefix = generationId is null
            ? "/downloads/files"
            : $"/downloads/g/{generationId}/files";
        RequireExactString(
            artifact,
            "downloadUrl",
            $"{routePrefix}/chummer-avalonia-win-x64-installer.exe");
        RequireExactString(
            artifact,
            "payloadDownloadUrl",
            $"{routePrefix}/chummer-avalonia-win-x64-payload.zip");
        if (compatibility)
        {
            RequireExactString(artifact, "platformId", "windows-x64");
            RequireExactString(
                artifact,
                "url",
                $"{routePrefix}/chummer-avalonia-win-x64-installer.exe");
        }
        else
        {
            RequireExactString(artifact, "artifactByteVisibility", "public");
        }
        _ = RequireSha256(artifact, "sha256");
        _ = RequirePositiveInt64(artifact, "sizeBytes");
        _ = RequireSha256(artifact, "payloadSha256");
        _ = RequirePositiveInt64(artifact, "payloadSizeBytes");
        return artifact;
    }

    private static void ValidateUnsignedManifestSignature(JsonElement signature)
    {
        if (!ExactPropertySet(
                signature,
                new HashSet<string>(["policy", "required", "status"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException("unsigned manifest signature shape drifted");
        }
        RequireExactString(signature, "policy", "preview_policy");
        RequireBoolean(signature, "required", expected: false);
        RequireExactString(signature, "status", "unsigned");
    }

    private static void ValidateUnsignedRecursiveAuthorityPosture(
        JsonElement value,
        string label)
    {
        var authorityFields = new HashSet<string>(
            [
                "authority",
                "authoritative",
                "candidateImportAuthority",
                "candidateReviewAuthority",
                "codeDeploymentAuthority",
                "deployAuthority",
                "deployAuthorized",
                "manifestIsAuthoritative",
                "publicationAuthority",
                "publicationAuthorized",
                "publicationEligible",
                "releaseUploadAuthority",
                "releaseUploadAuthorized",
                "routeAuthority",
                "routeAuthorized",
                "uploadAuthority",
                "uploadAuthorized"
            ],
            StringComparer.Ordinal);
        var pending = new Stack<(JsonElement Value, string Path)>();
        pending.Push((value, label));
        while (pending.TryPop(out (JsonElement Value, string Path) current))
        {
            if (current.Value.ValueKind == JsonValueKind.Object)
            {
                foreach (JsonProperty property in current.Value.EnumerateObject())
                {
                    string path = $"{current.Path} {property.Name}";
                    if (authorityFields.Contains(property.Name)
                        && property.Value.ValueKind != JsonValueKind.False)
                    {
                        throw new InvalidDataException($"{path} must be exactly false");
                    }
                    if (property.Value.ValueKind is JsonValueKind.Object or JsonValueKind.Array)
                    {
                        pending.Push((property.Value, path));
                    }
                }
            }
            else if (current.Value.ValueKind == JsonValueKind.Array)
            {
                int index = 0;
                foreach (JsonElement child in current.Value.EnumerateArray())
                {
                    if (child.ValueKind is JsonValueKind.Object or JsonValueKind.Array)
                    {
                        pending.Push((child, $"{current.Path}[{index}]"));
                    }
                    index++;
                }
            }
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
        ValidateUnsignedProducerBindings(
            receipt,
            retained,
            documents[packageLockPath].Bytes,
            documents[retainedManifestPath].Bytes);

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

    internal static void ValidateUnsignedProducerBindings(
        JsonElement receipt,
        JsonElement retained,
        byte[] packageLockBytes,
        byte[] retainedManifestBytes)
    {
        ValidateUnsignedByteReference(
            RequireObject(receipt, "consumerPackagePlaneLock"),
            PackagePlaneLockBindingPath,
            packageLockBytes,
            "unsigned package receipt lock binding");
        ValidateUnsignedByteReference(
            RequireObject(retained, "packagePlaneLock"),
            PackagePlaneLockBindingPath,
            packageLockBytes,
            "unsigned retained manifest lock binding");
        JsonElement pointer = RequireObject(receipt, "retainedWindowsBundle");
        if (!ExactPropertySet(
                pointer,
                new HashSet<string>(
                    [
                        "atomicallyRetained",
                        "authority",
                        "bundleInventoryCount",
                        "bundleInventorySha256",
                        "consumerCommit",
                        "contractName",
                        "contractVersion",
                        "manifest",
                        "manifestIsAuthoritative",
                        "release",
                        "status",
                        "targetPath"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned retained bundle pointer property set drifted");
        }
        _ = RequirePositiveInt64(pointer, "bundleInventoryCount");
        _ = RequireSha256(pointer, "bundleInventorySha256");
        string pointerTarget = RequireCanonicalAbsolutePosixPath(
            pointer,
            "targetPath",
            "unsigned retained pointer target path");
        string retainedTarget = RequireCanonicalAbsolutePosixPath(
            retained,
            "targetPath",
            "unsigned retained manifest target path");
        if (!string.Equals(pointerTarget, retainedTarget, StringComparison.Ordinal))
        {
            throw new InvalidDataException("unsigned retained bundle target path drifted");
        }
        ValidateUnsignedByteReference(
            RequireObject(pointer, "manifest"),
            $"{pointerTarget}/manifest.json",
            retainedManifestBytes,
            "unsigned retained pointer manifest binding");
    }

    private static ReleaseUploadCandidateIncumbentBinding ValidateUnsignedRegistry(
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
        string nativeLockPath,
        bool unsignedWindowsFreshDeltaProfile,
        string sourceCanonicalPath,
        string sourceCompatibilityPath)
    {
        bool profileRetainsIncumbent = false;
        using JsonDocument projectedCompatibilityDocument = ParseStrictObject(
            compatibilityBytes,
            "unsigned projected compatibility manifest");
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
        if (unsignedWindowsFreshDeltaProfile)
        {
            candidateKeys.UnionWith(
            [
                "codeDeployCurrentShelfAuthority",
                "privacyLaunchGateSnapshot",
                "privacyLaunchGateSnapshotSha256",
                "projectionProfile",
                "registryCommit",
                "registry_commit",
                "retainedIncumbentProvenance",
                "sourceCanonicalManifest",
                "sourceCompatibilityManifest",
                "sourceShelfInventorySha256"
            ]);
        }
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
        if (unsignedWindowsFreshDeltaProfile)
        {
            ValidateUnsignedRecursiveAuthorityPosture(
                registryCandidate,
                "unsigned Registry PREPARE candidate");
            RequireExactString(
                registryCandidate,
                "projectionProfile",
                UnsignedWindowsFreshDeltaProjectionProfile);
            string registryCommit = RequireMatchingAlias(
                registryCandidate,
                "registryCommit",
                "registry_commit",
                "unsigned Registry PREPARE Registry commit");
            if (!CommitPattern.IsMatch(registryCommit)
                || !string.Equals(
                    registryCommit,
                    RequireMatchingAlias(
                        canonical,
                        "registryCommit",
                        "registry_commit",
                        "unsigned canonical Registry commit"),
                    StringComparison.Ordinal)
                || !JsonSemanticEquals(
                    RequireObject(registryCandidate, "codeDeployCurrentShelfAuthority"),
                    RequireObject(canonical, "codeDeployCurrentShelfAuthority"))
                || !JsonSemanticEquals(
                    RequireObject(registryCandidate, "retainedIncumbentProvenance"),
                    RequireObject(canonical, "retainedIncumbentProvenance")))
            {
                throw new InvalidDataException(
                    "unsigned Registry PREPARE profile graph drifted");
            }
            ValidateUnsignedPrivacyLaunchGateSnapshot(
                RequireObject(registryCandidate, "privacyLaunchGateSnapshot"),
                RequireSha256(registryCandidate, "privacyLaunchGateSnapshotSha256"));
        }
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
        byte[]? sourceCanonicalBytes = null;
        byte[]? sourceCompatibilityBytes = null;
        if (unsignedWindowsFreshDeltaProfile)
        {
            sourceCanonicalBytes = documents[sourceCanonicalPath].Bytes;
            sourceCompatibilityBytes = documents[sourceCompatibilityPath].Bytes;
            ValidateUnsignedByteReference(
                RequireObject(registryCandidate, "sourceCanonicalManifest"),
                sourceCanonicalPath,
                sourceCanonicalBytes,
                "unsigned Registry source canonical manifest");
            ValidateUnsignedByteReference(
                RequireObject(registryCandidate, "sourceCompatibilityManifest"),
                sourceCompatibilityPath,
                sourceCompatibilityBytes,
                "unsigned Registry source compatibility manifest");
        }
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
        if (unsignedWindowsFreshDeltaProfile)
        {
            compositionKeys.Add("projectionProfile");
        }
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
        if (unsignedWindowsFreshDeltaProfile)
        {
            RequireExactString(
                composition,
                "projectionProfile",
                UnsignedWindowsFreshDeltaProjectionProfile);
        }
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
            unsignedWindowsFreshDeltaProfile
                ? sourceCanonicalBytes!
                : canonicalBytes,
            "unsigned composition canonical manifest");
        ValidateUnsignedByteReference(
            RequireObject(composition, "proposedCompatibilityManifest"),
            "releases.json",
            unsignedWindowsFreshDeltaProfile
                ? sourceCompatibilityBytes!
                : compatibilityBytes,
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
        if (!string.Equals(
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
        if (unsignedWindowsFreshDeltaProfile)
        {
            IReadOnlyDictionary<string, JsonElement> sourceByPath =
                ValidateUnsignedInventory(
                    proposedInventory,
                    "unsigned composition source shelf",
                    allowEmpty: false,
                    retained: false);
            IReadOnlyDictionary<string, JsonElement> projectedByPath =
                ValidateUnsignedInventory(
                    scopeFull,
                    "unsigned projected shelf",
                    allowEmpty: false,
                    retained: false);
            if (!sourceByPath.Keys.Order(StringComparer.Ordinal).SequenceEqual(
                    projectedByPath.Keys.Order(StringComparer.Ordinal),
                    StringComparer.Ordinal))
            {
                throw new InvalidDataException(
                    "unsigned source/projected shelf paths drifted");
            }
            foreach (string path in sourceByPath.Keys)
            {
                JsonElement sourceRow = sourceByPath[path];
                JsonElement projectedRow = projectedByPath[path];
                if (path is not "RELEASE_CHANNEL.generated.json" and not "releases.json")
                {
                    if (!JsonSemanticEquals(sourceRow, projectedRow))
                    {
                        throw new InvalidDataException(
                            "unsigned profile changed a non-manifest shelf byte");
                    }
                    continue;
                }
                byte[] sourceBytes = path == "RELEASE_CHANNEL.generated.json"
                    ? sourceCanonicalBytes!
                    : sourceCompatibilityBytes!;
                byte[] projectedBytes = path == "RELEASE_CHANNEL.generated.json"
                    ? canonicalBytes
                    : compatibilityBytes;
                if (RequireNonNegativeInt64(sourceRow, "mode")
                    != RequireNonNegativeInt64(projectedRow, "mode")
                    || !string.Equals(
                        RequireSha256(sourceRow, "sha256"),
                        Sha256(sourceBytes),
                        StringComparison.Ordinal)
                    || RequireNonNegativeInt64(sourceRow, "sizeBytes")
                    != sourceBytes.LongLength
                    || !string.Equals(
                        RequireSha256(projectedRow, "sha256"),
                        Sha256(projectedBytes),
                        StringComparison.Ordinal)
                    || RequireNonNegativeInt64(projectedRow, "sizeBytes")
                    != projectedBytes.LongLength
                    || string.Equals(
                        RequireSha256(sourceRow, "sha256"),
                        RequireSha256(projectedRow, "sha256"),
                        StringComparison.Ordinal))
                {
                    throw new InvalidDataException(
                        "unsigned source/projected manifest custody drifted");
                }
            }
        }
        else if (!JsonSemanticEquals(proposedInventory, scopeFull))
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
        JsonElement incumbentCanonical = RequireObject(
            incumbent,
            "canonicalManifest");
        JsonElement incumbentCompatibility = RequireObject(
            incumbent,
            "compatibilityManifest");
        ValidateUnsignedUnheldReference(
            incumbentCanonical,
            "RELEASE_CHANNEL.generated.json",
            "unsigned incumbent canonical manifest");
        ValidateUnsignedUnheldReference(
            incumbentCompatibility,
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
        string incumbentActiveInventorySha256 =
            ReleaseShelfGenerationStore.ComputeInventoryDigest(
                incumbentByPath
                    .Where(static row => row.Key is not
                        "activation-candidate.json"
                        and not "RELEASE_CHANNEL.generated.json"
                        and not "releases.json")
                    .OrderBy(static row => row.Key, StringComparer.Ordinal)
                    .Select(row => new ReleaseShelfInventoryEntry(
                        row.Key,
                        RequireSha256(row.Value, "sha256"),
                        RequireNonNegativeInt64(row.Value, "sizeBytes"))));
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
        if (unsignedWindowsFreshDeltaProfile)
        {
            JsonElement review = RequireObject(
                canonical,
                "codeDeployCurrentShelfAuthority");
            RequireExactString(
                registryCandidate,
                "sourceShelfInventorySha256",
                RequireSha256(composition, "proposedShelfInventorySha256"));
            RequireExactString(
                review,
                "sourceCanonicalManifestSha256",
                Sha256(sourceCanonicalBytes!));
            RequireExactString(
                review,
                "sourceCompatibilityManifestSha256",
                Sha256(sourceCompatibilityBytes!));
            RequireExactString(
                review,
                "sourceShelfInventorySha256",
                RequireSha256(registryCandidate, "sourceShelfInventorySha256"));
            RequireExactString(
                review,
                "incumbentSnapshotSha256",
                RequireSha256(incumbent, "snapshotSha256"));
            profileRetainsIncumbent = ValidateUnsignedRetainedIncumbentProvenance(
                RequireObject(canonical, "retainedIncumbentProvenance"),
                canonical,
                projectedCompatibilityDocument.RootElement,
                documents[sourceCanonicalPath].Root,
                documents[sourceCompatibilityPath].Root,
                incumbent,
                scopeRetained);
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
        if (unsignedWindowsFreshDeltaProfile)
        {
            var sourceWindowsArtifacts = new List<JsonElement>();
            foreach (JsonElement artifact in RequireArray(
                         documents[sourceCanonicalPath].Root,
                         "artifacts").EnumerateArray())
            {
                if (artifact.ValueKind != JsonValueKind.Object)
                {
                    throw new InvalidDataException(
                        "unsigned composition source artifact is not an object");
                }
                if (string.Equals(
                        RequireString(artifact, "head"),
                        "avalonia",
                        StringComparison.Ordinal)
                    && string.Equals(
                        RequireString(artifact, "platform"),
                        "windows",
                        StringComparison.Ordinal)
                    && string.Equals(
                        RequireString(artifact, "rid"),
                        WindowsRid,
                        StringComparison.Ordinal))
                {
                    sourceWindowsArtifacts.Add(artifact);
                }
            }
            if (sourceWindowsArtifacts.Count != 1)
            {
                throw new InvalidDataException(
                    "unsigned composition source Windows artifact drifted");
            }
            manifestRowSha256 = UnsignedCompactSha256(sourceWindowsArtifacts[0]);
            RequireExactString(
                windowsArtifact.Value,
                "sourceManifestRowSha256",
                manifestRowSha256);
        }
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
            RequireObject(registryCandidate, "projectionInputs"),
            unsignedWindowsFreshDeltaProfile);
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
        string retainedProfilePlatform = shelfPlatforms
            .SingleOrDefault(static platform => platform != "windows")
            ?? string.Empty;
        string[] expectedProfileShelfPlatforms = profileRetainsIncumbent
            ? [retainedProfilePlatform, "windows"]
            : ["windows"];
        string[] expectedProfileRetainedPlatforms = profileRetainsIncumbent
            ? [retainedProfilePlatform]
            : [];
        if (unsignedWindowsFreshDeltaProfile
            && (!shelfPlatforms.SetEquals(expectedProfileShelfPlatforms)
                || !shelfPlatforms.Where(static platform => platform != "windows")
                    .SequenceEqual(
                        expectedProfileRetainedPlatforms,
                        StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned Registry profile shelf platforms drifted");
        }
        ValidateUnsignedWindowsDelta(
            RequireObject(registryCandidate, "windowsDelta"),
            scopeFresh,
            unsignedWindowsFreshDeltaProfile);

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
        if (unsignedWindowsFreshDeltaProfile)
        {
            authorityKeys.UnionWith(
            [
                "codeDeployCurrentShelfAuthority",
                "privacyLaunchGateSnapshot",
                "privacyLaunchGateSnapshotSha256",
                "projectionProfile",
                "registryCommit",
                "registry_commit",
                "retainedIncumbentProvenance",
                "sourceCanonicalManifest",
                "sourceCompatibilityManifest",
                "sourceShelfInventorySha256"
            ]);
        }
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
        if (unsignedWindowsFreshDeltaProfile)
        {
            ValidateUnsignedRegistryProfileFields(
                registryAuthority,
                registryCandidate,
                canonical,
                sourceCanonicalBytes!,
                sourceCompatibilityBytes!,
                sourceCanonicalPath,
                sourceCompatibilityPath,
                "unsigned Registry FINALIZE authority");
        }
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
            RequireObject(registryAuthority, "projectionInputs"),
            unsignedWindowsFreshDeltaProfile);

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
        if (unsignedWindowsFreshDeltaProfile)
        {
            finalizeKeys.UnionWith(
            [
                "codeDeployCurrentShelfAuthority",
                "privacyLaunchGateSnapshot",
                "privacyLaunchGateSnapshotSha256",
                "projectionProfile",
                "registryCommit",
                "registry_commit",
                "retainedIncumbentProvenance",
                "sourceCanonicalManifest",
                "sourceCompatibilityManifest",
                "sourceShelfInventorySha256"
            ]);
        }
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
        if (unsignedWindowsFreshDeltaProfile)
        {
            ValidateUnsignedRegistryProfileFields(
                registryFinalize,
                registryCandidate,
                canonical,
                sourceCanonicalBytes!,
                sourceCompatibilityBytes!,
                sourceCanonicalPath,
                sourceCompatibilityPath,
                "unsigned Registry FINALIZE receipt");
        }
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
        return new ReleaseUploadCandidateIncumbentBinding(
            SnapshotSha256: RequireSha256(incumbent, "snapshotSha256"),
            FullShelfInventorySha256: RequireSha256(
                incumbent,
                "fullShelfInventorySha256"),
            ActiveInventorySha256: incumbentActiveInventorySha256,
            CanonicalManifestSha256: RequireSha256(
                incumbentCanonical,
                "sha256"),
            CompatibilityManifestSha256: RequireSha256(
                incumbentCompatibility,
                "sha256"));
    }

    private static void ValidateUnsignedRegistryProfileFields(
        JsonElement value,
        JsonElement registryCandidate,
        JsonElement canonical,
        byte[] sourceCanonicalBytes,
        byte[] sourceCompatibilityBytes,
        string sourceCanonicalPath,
        string sourceCompatibilityPath,
        string label)
    {
        RequireExactString(
            value,
            "projectionProfile",
            UnsignedWindowsFreshDeltaProjectionProfile);
        string registryCommit = RequireMatchingAlias(
            value,
            "registryCommit",
            "registry_commit",
            $"{label} Registry commit");
        if (!CommitPattern.IsMatch(registryCommit)
            || !string.Equals(
                registryCommit,
                RequireMatchingAlias(
                    registryCandidate,
                    "registryCommit",
                    "registry_commit",
                    "Registry PREPARE Registry commit"),
                StringComparison.Ordinal)
            || !JsonSemanticEquals(
                RequireObject(value, "codeDeployCurrentShelfAuthority"),
                RequireObject(canonical, "codeDeployCurrentShelfAuthority"))
            || !JsonSemanticEquals(
                RequireObject(value, "retainedIncumbentProvenance"),
                RequireObject(canonical, "retainedIncumbentProvenance"))
            || !JsonSemanticEquals(
                RequireObject(value, "privacyLaunchGateSnapshot"),
                RequireObject(registryCandidate, "privacyLaunchGateSnapshot")))
        {
            throw new InvalidDataException($"{label} profile graph drifted");
        }
        string privacyDigest = RequireSha256(value, "privacyLaunchGateSnapshotSha256");
        RequireExactString(
            registryCandidate,
            "privacyLaunchGateSnapshotSha256",
            privacyDigest);
        ValidateUnsignedPrivacyLaunchGateSnapshot(
            RequireObject(value, "privacyLaunchGateSnapshot"),
            privacyDigest);
        RequireExactString(
            value,
            "sourceShelfInventorySha256",
            RequireSha256(registryCandidate, "sourceShelfInventorySha256"));
        ValidateUnsignedByteReference(
            RequireObject(value, "sourceCanonicalManifest"),
            sourceCanonicalPath,
            sourceCanonicalBytes,
            $"{label} source canonical manifest");
        ValidateUnsignedByteReference(
            RequireObject(value, "sourceCompatibilityManifest"),
            sourceCompatibilityPath,
            sourceCompatibilityBytes,
            $"{label} source compatibility manifest");
    }

    private static void ValidateUnsignedPrivacyLaunchGateSnapshot(
        JsonElement snapshot,
        string expectedDigest)
    {
        if (!ExactPropertySet(
                snapshot,
                new HashSet<string>(
                    [
                        "blockedClaims",
                        "blocksLaunch",
                        "capabilityContractName",
                        "capabilityContractVersion",
                        "contractName",
                        "contractVersion",
                        "facts",
                        "prohibitedClaims",
                        "reason",
                        "reviewRequired",
                        "scope",
                        "status"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned privacy launch-gate snapshot property set drifted");
        }
        RequireUnsignedStringArray(
            snapshot,
            "blockedClaims",
            [
                "flagship_launch",
                "public_release_supportability",
                "hosted_build_recovery_and_erasure"
            ]);
        RequireBoolean(snapshot, "blocksLaunch", expected: true);
        RequireExactString(
            snapshot,
            "capabilityContractName",
            "chummer.hosted_build_privacy_lifecycle");
        RequireExactInt32(snapshot, "capabilityContractVersion", 1);
        RequireExactString(
            snapshot,
            "contractName",
            "chummer.privacy_launch_gate");
        RequireExactInt32(snapshot, "contractVersion", 1);
        RequireUnsignedStringArray(
            snapshot,
            "facts",
            [
                "active-record-delete",
                "memory-only-recovery",
                "no-delete-replay",
                "no-owner-erasure",
                "production-recovery-unverified"
            ]);
        RequireUnsignedStringArray(
            snapshot,
            "prohibitedClaims",
            ["permanent-delete", "durable-recovery", "account-erasure"]);
        RequireExactString(
            snapshot,
            "reason",
            "Hosted Build backup and point-in-time-recovery retention, tombstone or lineage retention, deletion replay, and whole-account erasure are not launch-approved or production-verified.");
        RequireBoolean(snapshot, "reviewRequired", expected: true);
        RequireExactString(
            snapshot,
            "scope",
            "flagship_launch_and_release_supportability");
        RequireExactString(snapshot, "status", "review_required");
        if (!string.Equals(
                UnsignedCompactSha256(snapshot),
                expectedDigest,
                StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "unsigned privacy launch-gate snapshot digest drifted");
        }
    }

    private static (
        JsonElement[] CanonicalRows,
        JsonElement[] CompatibilityRows,
        HashSet<string> RetainedIds) ValidateUnsignedRetainedProjectedBindings(
            JsonElement provenance,
            JsonElement canonical,
            JsonElement compatibility)
    {
        if (!ExactPropertySet(
                provenance,
                new HashSet<string>(
                    [
                        "contractName",
                        "contractVersion",
                        "incumbentCanonicalManifestSha256",
                        "incumbentCompatibilityManifestSha256",
                        "incumbentFullShelfInventorySha256",
                        "incumbentSnapshotSha256",
                        "retainedArtifactBindings",
                        "retainedArtifactBindingsSha256",
                        "retainedCompatibilityBindings",
                        "retainedCompatibilityBindingsSha256",
                        "retainedInventorySha256"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned retained incumbent provenance property set drifted");
        }
        RequireExactString(
            provenance,
            "contractName",
            "chummer.registry.retained-incumbent-provenance");
        RequireExactInt32(provenance, "contractVersion", 1);
        foreach (string field in new[]
                 {
                     "incumbentCanonicalManifestSha256",
                     "incumbentCompatibilityManifestSha256",
                     "incumbentFullShelfInventorySha256",
                     "incumbentSnapshotSha256",
                     "retainedInventorySha256"
                 })
        {
            _ = RequireSha256(provenance, field);
        }

        JsonElement[] allCanonicalRows = RequireArray(canonical, "artifacts")
            .EnumerateArray()
            .ToArray();
        JsonElement[] allCompatibilityRows = RequireArray(compatibility, "downloads")
            .EnumerateArray()
            .ToArray();
        string[] canonicalArtifactIds = allCanonicalRows
            .Select(RequireUnsignedArtifactIdentity)
            .ToArray();
        string[] compatibilityArtifactIds = allCompatibilityRows
            .Select(RequireUnsignedArtifactIdentity)
            .ToArray();
        string[] windowsOnlyArtifactIds = ["avalonia-win-x64-installer"];
        string[] retainedLinuxArtifactIds =
            [.. UnsignedRetainedArtifactIds, "avalonia-win-x64-installer"];
        string[] legacyRetainedMacosArtifactIds =
            [.. LegacyUnsignedRetainedArtifactIds, "avalonia-win-x64-installer"];
        bool exactWindowsOnly = canonicalArtifactIds.SequenceEqual(
                windowsOnlyArtifactIds,
                StringComparer.Ordinal)
            && compatibilityArtifactIds.SequenceEqual(
                windowsOnlyArtifactIds,
                StringComparer.Ordinal);
        bool exactRetainedLinux = canonicalArtifactIds.SequenceEqual(
                retainedLinuxArtifactIds,
                StringComparer.Ordinal)
            && compatibilityArtifactIds.SequenceEqual(
                retainedLinuxArtifactIds,
                StringComparer.Ordinal);
        bool exactLegacyRetainedMacos = canonicalArtifactIds.SequenceEqual(
                legacyRetainedMacosArtifactIds,
                StringComparer.Ordinal)
            && compatibilityArtifactIds.SequenceEqual(
                legacyRetainedMacosArtifactIds,
                StringComparer.Ordinal);
        if (!exactWindowsOnly && !exactRetainedLinux && !exactLegacyRetainedMacos)
        {
            throw new InvalidDataException(
                "unsigned projected manifest artifact identities or order drifted");
        }

        JsonElement[] canonicalRows = allCanonicalRows
            .Where(row => !string.Equals(
                RequireString(row, "platform"),
                "windows",
                StringComparison.Ordinal))
            .ToArray();
        if (canonicalRows.Any(row => !string.Equals(
                RequireString(row, "platform"),
                exactLegacyRetainedMacos ? "macos" : "linux",
                StringComparison.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned retained canonical platform differs from its exact profile");
        }
        JsonElement canonicalBindings = RequireArray(
            provenance,
            "retainedArtifactBindings");
        ValidateUnsignedRetainedBindingDigest(
            provenance,
            "retainedArtifactBindingsSha256",
            canonicalBindings);
        if (canonicalBindings.GetArrayLength() != canonicalRows.Length)
        {
            throw new InvalidDataException(
                "unsigned retained canonical binding cardinality drifted");
        }
        var canonicalByFile = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
        var retainedIds = new HashSet<string>(StringComparer.Ordinal);
        for (int index = 0; index < canonicalRows.Length; index++)
        {
            JsonElement row = canonicalRows[index];
            JsonElement binding = canonicalBindings[index];
            ValidateUnsignedRetainedBinding(binding, row, index, "canonical");
            string fileName = RequireString(row, "fileName");
            string artifactId = RequireString(binding, "artifactId");
            if (!canonicalByFile.TryAdd(fileName, row) || !retainedIds.Add(artifactId))
            {
                throw new InvalidDataException(
                    "unsigned retained canonical identity is duplicated");
            }
        }

        JsonElement[] compatibilityRows = RequireArray(compatibility, "downloads")
            .EnumerateArray()
            .Where(row => canonicalByFile.ContainsKey(RequireString(row, "fileName")))
            .ToArray();
        JsonElement compatibilityBindings = RequireArray(
            provenance,
            "retainedCompatibilityBindings");
        ValidateUnsignedRetainedBindingDigest(
            provenance,
            "retainedCompatibilityBindingsSha256",
            compatibilityBindings);
        if (compatibilityRows.Length != canonicalRows.Length
            || compatibilityBindings.GetArrayLength() != compatibilityRows.Length)
        {
            throw new InvalidDataException(
                "unsigned retained compatibility binding cardinality drifted");
        }
        var compatibilityIds = new HashSet<string>(StringComparer.Ordinal);
        for (int index = 0; index < compatibilityRows.Length; index++)
        {
            JsonElement row = compatibilityRows[index];
            JsonElement canonicalRow = canonicalByFile[RequireString(row, "fileName")];
            JsonElement binding = compatibilityBindings[index];
            ValidateUnsignedRetainedBinding(binding, row, index, "compatibility");
            string artifactId = RequireString(binding, "artifactId");
            if (!string.Equals(
                    artifactId,
                    RequireString(canonicalRow, "artifactId"),
                    StringComparison.Ordinal)
                || !string.Equals(
                    RequireSha256(row, "sha256"),
                    RequireSha256(canonicalRow, "sha256"),
                    StringComparison.Ordinal)
                || RequirePositiveInt64(row, "sizeBytes")
                   != RequirePositiveInt64(canonicalRow, "sizeBytes")
                || !compatibilityIds.Add(artifactId))
            {
                throw new InvalidDataException(
                    "unsigned retained compatibility binding is not canonical-bijective");
            }
        }
        if (!compatibilityIds.SetEquals(retainedIds))
        {
            throw new InvalidDataException(
                "unsigned retained compatibility/canonical identities differ");
        }
        return (canonicalRows, compatibilityRows, retainedIds);
    }

    private static string RequireUnsignedArtifactIdentity(JsonElement row)
    {
        if (row.ValueKind != JsonValueKind.Object)
        {
            throw new InvalidDataException(
                "unsigned projected manifest contains a non-object artifact");
        }
        string artifactId = row.TryGetProperty("artifactId", out JsonElement directId)
            && directId.ValueKind == JsonValueKind.String
            && !string.IsNullOrWhiteSpace(directId.GetString())
                ? directId.GetString()!
                : RequireString(row, "id");
        if (row.TryGetProperty("id", out JsonElement id)
            && (id.ValueKind != JsonValueKind.String
                || !string.Equals(id.GetString(), artifactId, StringComparison.Ordinal))
            || directId.ValueKind is not JsonValueKind.Undefined
                and not JsonValueKind.Null
                and not JsonValueKind.String
            || directId.ValueKind == JsonValueKind.String
                && !string.Equals(
                    directId.GetString(),
                    artifactId,
                    StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "unsigned projected manifest artifact aliases drifted");
        }
        return artifactId;
    }

    private static bool ValidateUnsignedRetainedIncumbentProvenance(
        JsonElement provenance,
        JsonElement canonical,
        JsonElement compatibility,
        JsonElement sourceCanonical,
        JsonElement sourceCompatibility,
        JsonElement incumbent,
        JsonElement retainedInventory)
    {
        if (!ExactPropertySet(
                provenance,
                new HashSet<string>(
                    [
                        "contractName",
                        "contractVersion",
                        "incumbentCanonicalManifestSha256",
                        "incumbentCompatibilityManifestSha256",
                        "incumbentFullShelfInventorySha256",
                        "incumbentSnapshotSha256",
                        "retainedArtifactBindings",
                        "retainedArtifactBindingsSha256",
                        "retainedCompatibilityBindings",
                        "retainedCompatibilityBindingsSha256",
                        "retainedInventorySha256"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned retained incumbent provenance property set drifted");
        }
        RequireExactString(
            provenance,
            "contractName",
            "chummer.registry.retained-incumbent-provenance");
        RequireExactInt32(provenance, "contractVersion", 1);
        RequireExactString(
            provenance,
            "incumbentCanonicalManifestSha256",
            RequireSha256(RequireObject(incumbent, "canonicalManifest"), "sha256"));
        RequireExactString(
            provenance,
            "incumbentCompatibilityManifestSha256",
            RequireSha256(RequireObject(incumbent, "compatibilityManifest"), "sha256"));
        RequireExactString(
            provenance,
            "incumbentFullShelfInventorySha256",
            RequireSha256(incumbent, "fullShelfInventorySha256"));
        RequireExactString(
            provenance,
            "incumbentSnapshotSha256",
            RequireSha256(incumbent, "snapshotSha256"));
        RequireExactString(
            provenance,
            "retainedInventorySha256",
            UnsignedCompactSha256(retainedInventory));

        JsonElement[] canonicalRows = RequireArray(canonical, "artifacts")
            .EnumerateArray()
            .Where(row => !string.Equals(
                RequireString(row, "platform"),
                "windows",
                StringComparison.Ordinal))
            .ToArray();
        string[] retainedIdsInOrder = canonicalRows
            .Select(RequireUnsignedArtifactIdentity)
            .ToArray();
        bool retainsLinux = retainedIdsInOrder.SequenceEqual(
            UnsignedRetainedArtifactIds,
            StringComparer.Ordinal);
        bool retainsLegacyMacos = retainedIdsInOrder.SequenceEqual(
            LegacyUnsignedRetainedArtifactIds,
            StringComparer.Ordinal);
        if (retainedIdsInOrder.Length != 0 && !retainsLinux && !retainsLegacyMacos)
        {
            throw new InvalidDataException(
                "unsigned retained canonical identities or order drifted");
        }
        if (canonicalRows.Any(row => !string.Equals(
                RequireString(row, "platform"),
                retainsLegacyMacos ? "macos" : "linux",
                StringComparison.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned retained canonical platform differs from its exact profile");
        }
        JsonElement canonicalBindings = RequireArray(
            provenance,
            "retainedArtifactBindings");
        ValidateUnsignedRetainedBindingDigest(
            provenance,
            "retainedArtifactBindingsSha256",
            canonicalBindings);
        if (canonicalBindings.GetArrayLength() != canonicalRows.Length)
        {
            throw new InvalidDataException(
                "unsigned retained canonical binding cardinality drifted");
        }
        var canonicalByFile = new Dictionary<string, JsonElement>(StringComparer.Ordinal);
        var retainedIds = new HashSet<string>(StringComparer.Ordinal);
        for (int index = 0; index < canonicalRows.Length; index++)
        {
            JsonElement row = canonicalRows[index];
            JsonElement binding = canonicalBindings[index];
            ValidateUnsignedRetainedBinding(binding, row, index, "canonical");
            string fileName = RequireString(row, "fileName");
            string artifactId = RequireString(binding, "artifactId");
            if (!canonicalByFile.TryAdd(fileName, row) || !retainedIds.Add(artifactId))
            {
                throw new InvalidDataException(
                    "unsigned retained canonical identity is duplicated");
            }
        }

        JsonElement[] compatibilityRows = RequireArray(compatibility, "downloads")
            .EnumerateArray()
            .Where(row => canonicalByFile.ContainsKey(RequireString(row, "fileName")))
            .ToArray();
        JsonElement compatibilityBindings = RequireArray(
            provenance,
            "retainedCompatibilityBindings");
        ValidateUnsignedRetainedBindingDigest(
            provenance,
            "retainedCompatibilityBindingsSha256",
            compatibilityBindings);
        if (compatibilityRows.Length != canonicalRows.Length
            || compatibilityBindings.GetArrayLength() != compatibilityRows.Length)
        {
            throw new InvalidDataException(
                "unsigned retained compatibility binding cardinality drifted");
        }
        var compatibilityIds = new HashSet<string>(StringComparer.Ordinal);
        for (int index = 0; index < compatibilityRows.Length; index++)
        {
            JsonElement row = compatibilityRows[index];
            JsonElement canonicalRow = canonicalByFile[RequireString(row, "fileName")];
            JsonElement binding = compatibilityBindings[index];
            ValidateUnsignedRetainedBinding(binding, row, index, "compatibility");
            string artifactId = RequireString(binding, "artifactId");
            if (!string.Equals(
                    artifactId,
                    RequireString(canonicalRow, "artifactId"),
                    StringComparison.Ordinal)
                || !string.Equals(
                    RequireSha256(row, "sha256"),
                    RequireSha256(canonicalRow, "sha256"),
                    StringComparison.Ordinal)
                || RequirePositiveInt64(row, "sizeBytes")
                   != RequirePositiveInt64(canonicalRow, "sizeBytes")
                || !compatibilityIds.Add(artifactId))
            {
                throw new InvalidDataException(
                    "unsigned retained compatibility binding is not canonical-bijective");
            }
        }
        if (!compatibilityIds.SetEquals(retainedIds))
        {
            throw new InvalidDataException(
                "unsigned retained compatibility/canonical identities differ");
        }
        RequireRetainedRowsMatchSource(
            RequireArray(sourceCanonical, "artifacts"),
            canonicalRows,
            retainedIds,
            "canonical");
        RequireRetainedRowsMatchSource(
            RequireArray(sourceCompatibility, "downloads"),
            compatibilityRows,
            retainedIds,
            "compatibility");
        return retainsLinux || retainsLegacyMacos;
    }

    private static void ValidateUnsignedRetainedBindingDigest(
        JsonElement provenance,
        string digestField,
        JsonElement bindings)
    {
        RequireExactString(
            provenance,
            digestField,
            UnsignedCompactSha256(bindings));
    }

    private static void ValidateUnsignedRetainedBinding(
        JsonElement binding,
        JsonElement row,
        int index,
        string label)
    {
        if (!ExactPropertySet(
                binding,
                new HashSet<string>(
                    ["artifactId", "manifestRowSha256", "sha256", "sizeBytes"],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                $"unsigned retained {label} binding[{index}] shape drifted");
        }
        string artifactId = row.TryGetProperty("artifactId", out JsonElement directId)
            && directId.ValueKind == JsonValueKind.String
            && !string.IsNullOrWhiteSpace(directId.GetString())
                ? directId.GetString()!
                : RequireString(row, "id");
        if (!string.Equals(
                RequireString(binding, "artifactId"),
                artifactId,
                StringComparison.Ordinal)
            || !string.Equals(
                RequireSha256(binding, "manifestRowSha256"),
                UnsignedCompactSha256(row),
                StringComparison.Ordinal)
            || !string.Equals(
                RequireSha256(binding, "sha256"),
                RequireSha256(row, "sha256"),
                StringComparison.Ordinal)
            || RequirePositiveInt64(binding, "sizeBytes")
               != RequirePositiveInt64(row, "sizeBytes"))
        {
            throw new InvalidDataException(
                $"unsigned retained {label} binding[{index}] differs");
        }
    }

    private static void RequireRetainedRowsMatchSource(
        JsonElement sourceRows,
        IReadOnlyList<JsonElement> projectedRows,
        IReadOnlySet<string> retainedIds,
        string label)
    {
        var retainedSource = new List<JsonElement>();
        foreach (JsonElement row in sourceRows.EnumerateArray())
        {
            if (row.ValueKind != JsonValueKind.Object)
            {
                throw new InvalidDataException(
                    $"unsigned retained {label} source row is not an object");
            }
            if (retainedIds.Contains(RequireUnsignedArtifactIdentity(row)))
            {
                retainedSource.Add(row);
            }
        }
        if (retainedSource.Count != projectedRows.Count
            || retainedSource.Where((row, index) =>
                    !JsonSemanticEquals(row, projectedRows[index]))
                .Any())
        {
            throw new InvalidDataException(
                $"unsigned retained {label} rows differ from source custody");
        }
    }

    private static void ValidateUnsignedWindowsDelta(
        JsonElement value,
        JsonElement fresh,
        bool unsignedWindowsFreshDeltaProfile = false)
    {
        string[] roles = unsignedWindowsFreshDeltaProfile
            ? ["installer", "bootstrap_payload", "bootstrap_payload_sidecar"]
            : ["installer", "bootstrap_payload"];
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

    private static void ValidateUnsignedProjectionInputs(
        JsonElement value,
        bool unsignedWindowsFreshDeltaProfile = false)
    {
        var paths = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["materializer"] = "scripts/materialize_unsigned_preview_publication_delta.py",
            ["schema"] = "contracts/preview-publication-delta-v2.schema.json"
        };
        if (unsignedWindowsFreshDeltaProfile)
        {
            paths["releaseChannelMaterializer"] =
                "scripts/materialize_public_release_channel.py";
            paths["releaseChannelVerifier"] =
                "scripts/verify_public_release_channel.py";
        }
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
        DateTimeOffset now,
        bool allowUnsigned = false,
        byte[]? unsignedSourceCanonicalManifest = null,
        byte[]? unsignedSourceCompatibilityManifest = null,
        string? expectedUnsignedProducerSourceSha = null,
        IReadOnlyDictionary<string, ReleaseUploadCandidateInventoryRow>?
            expectedUnsignedContentRows = null)
    {
        bool hasUnsignedSourceBinding =
            unsignedSourceCanonicalManifest is not null
            || unsignedSourceCompatibilityManifest is not null
            || expectedUnsignedProducerSourceSha is not null
            || expectedUnsignedContentRows is not null;
        if (hasUnsignedSourceBinding
            && (!allowUnsigned
                || unsignedSourceCanonicalManifest is null
                || unsignedSourceCompatibilityManifest is null
                || expectedUnsignedProducerSourceSha is null
                || expectedUnsignedContentRows is null
                || !CommitPattern.IsMatch(expectedUnsignedProducerSourceSha)))
        {
            throw new InvalidDataException(
                "unsigned native source-publication binding is incomplete.");
        }
        string captureFileName = allowUnsigned
            ? UnsignedCaptureFileName
            : CaptureFileName;
        string captureInventoryFileName = allowUnsigned
            ? UnsignedCaptureInventoryFileName
            : CaptureInventoryFileName;
        string finalizationFileName = allowUnsigned
            ? UnsignedFinalizationFileName
            : FinalizationFileName;
        string finalizedInventoryFileName = allowUnsigned
            ? UnsignedFinalizedInventoryFileName
            : FinalizedInventoryFileName;
        string candidateProvenanceInventoryFileName = allowUnsigned
            ? UnsignedCandidateProvenanceInventoryFileName
            : CandidateProvenanceInventoryFileName;
        string candidateProvenanceExportFileName = allowUnsigned
            ? UnsignedCandidateProvenanceExportFileName
            : CandidateProvenanceExportFileName;
        string captureContract = allowUnsigned
            ? "chummer6-ui.unsigned-preview-native-windows-capture"
            : "chummer6-ui.preview-nightly-native-windows-capture";
        string captureInventoryContract = allowUnsigned
            ? "chummer6-ui.unsigned-preview-native-windows-capture-inventory"
            : "chummer6-ui.preview-nightly-native-windows-capture-inventory";
        string finalizationContract = allowUnsigned
            ? "chummer6-ui.unsigned-preview-native-windows-finalization"
            : "chummer6-ui.preview-nightly-native-windows-finalization";
        string finalizedInventoryContract = allowUnsigned
            ? "chummer6-ui.unsigned-preview-native-windows-finalized-inventory"
            : "chummer6-ui.preview-nightly-native-windows-finalized-inventory";
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
        ValidateEvidenceSource(
            captureSource,
            "candidate capture source",
            allowUnsigned ? UnsignedCaptureWorkflow : CaptureWorkflow,
            captureSource: true,
            allowUnsigned);
        ValidateEvidenceSource(
            finalizationSource,
            "candidate finalization source",
            allowUnsigned ? UnsignedFinalizationWorkflow : FinalizationWorkflow,
            captureSource: false,
            allowUnsigned);
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
                    path,
                    allowUnsigned ? "bytesBase64" : "base64");
                documents.Add(
                    path,
                    new CandidateEvidenceDocument(
                        path.EndsWith(".json", StringComparison.Ordinal)
                            ? ParseStrictObject(
                                bytes,
                                $"candidate native-Windows {path}")
                            : null,
                        bytes,
                        RequireSha256(entry, "sha256"),
                        RequireNonNegativeInt64(entry, "sizeBytes")));
            }
            if (allowUnsigned)
            {
                ValidateUnsignedScreenshotDocuments(documents);
                ValidateUnsignedNativeLogDocuments(documents);
            }

            CandidateWindowsScope scope = ParseCandidateWindowsScope(
                canonical,
                candidate,
                candidateInventory,
                allowUnsigned);
            var fixedPaths = new HashSet<string>(
                [
                    captureFileName,
                    captureInventoryFileName,
                    finalizationFileName,
                    finalizedInventoryFileName,
                    candidateProvenanceInventoryFileName,
                    candidateProvenanceExportFileName,
                    .. scope.Heads.Select(
                        head => $"startup-smoke/startup-smoke-{head}-{WindowsRid}.receipt.json")
                ],
                StringComparer.Ordinal);
            if (allowUnsigned)
            {
                fixedPaths.Add(
                    "startup-visual/windows-application-avalonia-win-x64-startup.receipt.json");
                fixedPaths.Add(
                    "screenshots/windows-application-avalonia-win-x64-startup.png");
            }
            if (!fixedPaths.IsSubsetOf(documents.Keys))
            {
                throw new InvalidDataException("candidate native-Windows custody is incomplete");
            }

            JsonElement finalizedInventory = documents[finalizedInventoryFileName].Root;
            var finalizedInventoryProperties = new HashSet<string>(
                ["contractName", "contractVersion", "captureInventorySha256", "files"],
                StringComparer.Ordinal);
            if (allowUnsigned)
            {
                finalizedInventoryProperties.UnionWith(
                    [
                        "deployAuthorized",
                        "finalization",
                        "policy",
                        "publicationAuthorized",
                        "status",
                        "uiUploadAuthorized",
                        "uploadAuthorized"
                    ]);
            }
            if (!ExactPropertySet(
                    finalizedInventory,
                    finalizedInventoryProperties))
            {
                throw new InvalidDataException(
                    "candidate finalized native-Windows inventory property set drifted");
            }
            RequireExactString(
                finalizedInventory,
                "contractName",
                finalizedInventoryContract);
            RequireExactInt32(finalizedInventory, "contractVersion", 1);
            if (allowUnsigned)
            {
                RequireUnsignedEvidenceOnlyPolicy(
                    RequireObject(finalizedInventory, "policy"),
                    "candidate finalized native-Windows inventory");
                RequireNoUnsignedPublicationAuthority(
                    finalizedInventory,
                    "candidate finalized native-Windows inventory");
                RequireExactString(finalizedInventory, "status", "passed");
                ValidateEvidenceByteReference(
                    RequireObject(finalizedInventory, "finalization"),
                    documents,
                    "candidate finalized native-Windows finalization");
                RequireExactString(
                    RequireObject(finalizedInventory, "finalization"),
                    "path",
                    finalizationFileName);
            }
            IReadOnlyList<ReleaseUploadCandidateInventoryRow> finalizedRows =
                ParseEvidenceInventoryRows(
                    RequireArray(finalizedInventory, "files"),
                    "candidate finalized native-Windows inventory",
                    allowEmpty: false);
            var finalizedByPath = finalizedRows.ToDictionary(static row => row.Path, StringComparer.Ordinal);
            foreach ((string path, CandidateEvidenceDocument evidence) in documents)
            {
                if (string.Equals(path, finalizedInventoryFileName, StringComparison.Ordinal))
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
                documents[candidateProvenanceInventoryFileName];
            JsonElement provenance = provenanceDocument.Root;
            ValidateCandidateContentInventoryHeader(
                provenance,
                scope,
                candidate,
                allowUnsigned,
                expectedUnsignedProducerSourceSha);
            IReadOnlyList<ReleaseUploadCandidateInventoryRow> provenanceRows =
                ParseEvidenceInventoryRows(
                    RequireArray(provenance, "files"),
                    "candidate native-Windows content inventory",
                    allowEmpty: false);
            if (allowUnsigned)
            {
                string[] expectedUnsignedPaths =
                [
                    "PREVIEW_NIGHTLY_UNSIGNED_COMPOSITION.proposed.json",
                    "provenance/UI_FRESH_PACKAGE_PLANE.generated.json",
                    "provenance/config/package-plane.lock.json",
                    "provenance/config/windows-native-bootstrap-toolchain.lock.json",
                    "provenance/retained-windows-publish-closure/manifest.json",
                    "publication/RELEASE_CHANNEL.generated.json",
                    "publication/files/chummer-avalonia-win-x64-installer.exe",
                    "publication/files/chummer-avalonia-win-x64-payload.zip",
                    "publication/files/chummer-avalonia-win-x64-payload.zip.json",
                    "publication/releases.json"
                ];
                if (!provenanceRows.Select(static row => row.Path)
                        .SequenceEqual(
                            expectedUnsignedPaths.Order(StringComparer.Ordinal),
                            StringComparer.Ordinal))
                {
                    throw new InvalidDataException(
                        "unsigned candidate content inventory path scope drifted");
                }
                if (expectedUnsignedContentRows is not null
                    && !provenanceRows.SequenceEqual(
                        expectedUnsignedContentRows.Values.OrderBy(
                            static row => row.Path,
                            StringComparer.Ordinal)))
                {
                    throw new InvalidDataException(
                        "unsigned candidate content differs from exact producer and candidate custody");
                }
            }
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
            bool contentBytesDrifted;
            if (allowUnsigned)
            {
                ReleaseUploadCandidateInventoryRow candidateCanonicalRow =
                    candidateByPath["RELEASE_CHANNEL.generated.json"];
                ReleaseUploadCandidateInventoryRow candidateCompatibilityRow =
                    candidateByPath["releases.json"];
                string expectedSourceCanonicalSha256 =
                    unsignedSourceCanonicalManifest is null
                        ? candidateCanonicalRow.Sha256
                        : Sha256(unsignedSourceCanonicalManifest);
                long expectedSourceCanonicalSize =
                    unsignedSourceCanonicalManifest?.LongLength
                    ?? candidateCanonicalRow.SizeBytes;
                string expectedSourceCompatibilitySha256 =
                    unsignedSourceCompatibilityManifest is null
                        ? candidateCompatibilityRow.Sha256
                        : Sha256(unsignedSourceCompatibilityManifest);
                long expectedSourceCompatibilitySize =
                    unsignedSourceCompatibilityManifest?.LongLength
                    ?? candidateCompatibilityRow.SizeBytes;
                contentBytesDrifted =
                    !provenanceByPath.TryGetValue(
                        "publication/RELEASE_CHANNEL.generated.json",
                        out ReleaseUploadCandidateInventoryRow? sourceCanonicalRow)
                    || sourceCanonicalRow.SizeBytes != expectedSourceCanonicalSize
                    || !string.Equals(
                        sourceCanonicalRow.Sha256,
                        expectedSourceCanonicalSha256,
                        StringComparison.Ordinal)
                    || !provenanceByPath.TryGetValue(
                        "publication/releases.json",
                        out ReleaseUploadCandidateInventoryRow? sourceCompatibilityRow)
                    || sourceCompatibilityRow.SizeBytes != expectedSourceCompatibilitySize
                    || !string.Equals(
                        sourceCompatibilityRow.Sha256,
                        expectedSourceCompatibilitySha256,
                        StringComparison.Ordinal);
                string[] stagedPublicationPaths =
                [
                    "files/chummer-avalonia-win-x64-installer.exe",
                    "files/chummer-avalonia-win-x64-payload.zip",
                    "files/chummer-avalonia-win-x64-payload.zip.json"
                ];
                contentBytesDrifted |= stagedPublicationPaths.Any(path =>
                    !candidateByPath.TryGetValue(
                        path,
                        out ReleaseUploadCandidateInventoryRow? staged)
                    || !provenanceByPath.TryGetValue(
                        $"publication/{path}",
                        out ReleaseUploadCandidateInventoryRow? exported)
                    || exported.SizeBytes != staged.SizeBytes
                    || !string.Equals(
                        exported.Sha256,
                        staged.Sha256,
                        StringComparison.Ordinal));
            }
            else
            {
                contentBytesDrifted = candidateByPath.Any(pair =>
                    !provenanceByPath.TryGetValue(
                        pair.Key,
                        out ReleaseUploadCandidateInventoryRow? exact)
                    || exact.SizeBytes != pair.Value.SizeBytes
                    || !string.Equals(
                        exact.Sha256,
                        pair.Value.Sha256,
                        StringComparison.Ordinal));
            }
            if (contentBytesDrifted)
            {
                throw new InvalidDataException("candidate native-Windows content bytes drifted");
            }
            CandidateEvidenceDocument captureDocument = documents[captureFileName];
            JsonElement capture = captureDocument.Root;
            var captureProperties = new HashSet<string>(
                [
                    "authenticodeVerification",
                    "candidate",
                    "captureMode",
                    "contractName",
                    "contractVersion",
                    "generatedAt",
                    "heads",
                    "source",
                    "status"
                ],
                StringComparer.Ordinal);
            if (allowUnsigned)
            {
                captureProperties.UnionWith(
                    [
                        "deployAuthorized",
                        "nativeEvidence",
                        "policy",
                        "preservedCandidateFiles",
                        "publicationAuthorized",
                        "uiUploadAuthorized",
                        "uploadAuthorized"
                    ]);
            }
            else
            {
                captureProperties.UnionWith(["channelId", "version"]);
            }
            if (!ExactPropertySet(
                    capture,
                    captureProperties))
            {
                throw new InvalidDataException(
                    "candidate Windows-only native capture property set drifted");
            }
            RequireExactString(
                capture,
                "contractName",
                captureContract);
            RequireExactInt32(capture, "contractVersion", allowUnsigned ? 1 : 2);
            RequireExactString(capture, "status", "captured");
            RequireExactString(
                capture,
                "captureMode",
                allowUnsigned ? "hosted_native_windows" : "interactive");
            if (!allowUnsigned)
            {
                RequireExactString(capture, "version", scope.Version);
                RequireExactString(capture, "channelId", scope.Channel);
            }
            else
            {
                RequireUnsignedEvidenceOnlyPolicy(
                    RequireObject(capture, "policy"),
                    "candidate native-Windows capture");
                RequireNoUnsignedPublicationAuthority(
                    capture,
                    "candidate native-Windows capture");
            }
            JsonElement captureReceiptSource = RequireObject(capture, "source");
            if (allowUnsigned)
            {
                ValidateUnsignedFullEvidenceSource(
                    captureReceiptSource,
                    captureSource,
                    captureActor: true,
                    reviewer);
            }
            else if (!JsonSemanticEquals(captureReceiptSource, captureSource))
            {
                throw new InvalidDataException(
                    "candidate native-Windows capture source drifted");
            }
            if (RequireFreshUtcTimestamp(capture, "generatedAt", now) != summaryCaptureAt)
            {
                throw new InvalidDataException("candidate native-Windows capture receipt drifted");
            }
            JsonElement captureCandidate = allowUnsigned
                ? ValidateUnsignedCaptureCandidateBinding(
                    RequireObject(capture, "candidate"),
                    documents,
                    finalizedByPath,
                    provenanceRows,
                    scope,
                    candidateProvenanceInventoryFileName,
                    candidateProvenanceExportFileName,
                    unsignedSourceCanonicalManifest is null
                        ? candidate.CanonicalManifestSha256
                        : Sha256(unsignedSourceCanonicalManifest),
                    unsignedSourceCanonicalManifest?.LongLength
                        ?? candidateByPath["RELEASE_CHANNEL.generated.json"].SizeBytes,
                    expectedUnsignedProducerSourceSha)
                : ValidateCaptureCandidateBinding(
                    RequireObject(capture, "candidate"),
                    captureSource,
                    documents,
                    finalizedByPath,
                    candidate.CanonicalManifestSha256,
                    summaryCaptureAt,
                    candidateProvenanceInventoryFileName,
                    candidateProvenanceExportFileName);
            JsonElement captureAuthenticode = RequireObject(
                capture,
                "authenticodeVerification");
            ValidateAuthenticodeInventoryBinding(
                captureAuthenticode,
                "authenticode/AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json",
                finalizedByPath,
                "candidate capture Authenticode verification",
                allowUnsigned);
            IReadOnlyDictionary<string, IReadOnlyList<CandidateScreenshotBinding>>
                captureScreenshots = ValidateCaptureHeads(
                RequireArray(capture, "heads"),
                scope,
                finalizedByPath,
                captureAuthenticode,
                allowUnsigned);
            if (allowUnsigned)
            {
                ValidateUnsignedAuthenticodeReceipt(
                    documents[
                        "authenticode/AUTHENTICODE_VERIFICATION-avalonia-win-x64.generated.json"]
                        .Root,
                    captureCandidate,
                    captureReceiptSource,
                    now);
                ValidateUnsignedCaptureNativeEvidence(
                    RequireObject(capture, "nativeEvidence"),
                    capture,
                    captureCandidate,
                    captureReceiptSource,
                    documents,
                    finalizedByPath,
                    captureScreenshots["avalonia"],
                    now);
                ValidateUnsignedPreservedCandidateFiles(
                    RequireArray(capture, "preservedCandidateFiles"),
                    documents,
                    candidateProvenanceInventoryFileName,
                    candidateProvenanceExportFileName);
            }

            CandidateEvidenceDocument captureInventoryDocument =
                documents[captureInventoryFileName];
            JsonElement captureInventory = captureInventoryDocument.Root;
            var captureInventoryProperties = new HashSet<string>(
                [
                    "contractName",
                    "contractVersion",
                    "files"
                ],
                StringComparer.Ordinal);
            if (allowUnsigned)
            {
                captureInventoryProperties.UnionWith(
                    [
                        "captureManifest",
                        "deployAuthorized",
                        "policy",
                        "publicationAuthorized",
                        "status",
                        "uiUploadAuthorized",
                        "uploadAuthorized"
                    ]);
            }
            else
            {
                captureInventoryProperties.UnionWith(
                    ["captureContract", "captureManifestSha256"]);
            }
            if (!ExactPropertySet(
                    captureInventory,
                    captureInventoryProperties))
            {
                throw new InvalidDataException(
                    "candidate native-Windows capture inventory property set drifted");
            }
            RequireExactString(
                captureInventory,
                "contractName",
                captureInventoryContract);
            RequireExactInt32(captureInventory, "contractVersion", allowUnsigned ? 1 : 2);
            if (allowUnsigned)
            {
                RequireExactString(captureInventory, "status", "captured");
                RequireUnsignedEvidenceOnlyPolicy(
                    RequireObject(captureInventory, "policy"),
                    "candidate native-Windows capture inventory");
                RequireNoUnsignedPublicationAuthority(
                    captureInventory,
                    "candidate native-Windows capture inventory");
                ValidateEvidenceByteReference(
                    RequireObject(captureInventory, "captureManifest"),
                    documents,
                    "candidate native-Windows capture manifest");
                RequireExactString(
                    RequireObject(captureInventory, "captureManifest"),
                    "path",
                    captureFileName);
            }
            else
            {
                RequireExactString(
                    captureInventory,
                    "captureContract",
                    captureContract);
                RequireExactString(
                    captureInventory,
                    "captureManifestSha256",
                    Sha256(captureDocument.Bytes));
            }
            IReadOnlyList<ReleaseUploadCandidateInventoryRow> captureRows =
                ParseEvidenceInventoryRows(
                RequireArray(captureInventory, "files"),
                "candidate native-Windows capture inventory",
                allowEmpty: false);
            string[] expectedCapturePaths = finalizedByPath.Keys
                .Where(path => !string.Equals(
                        path,
                        captureInventoryFileName,
                        StringComparison.Ordinal)
                    && !string.Equals(
                        path,
                        finalizationFileName,
                        StringComparison.Ordinal)
                    && !string.Equals(
                        path,
                        "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_APPROVAL.generated.json",
                        StringComparison.Ordinal)
                    && !path.StartsWith(
                        "WINDOWS_INSTALLER_VISUAL_PROOF-",
                        StringComparison.Ordinal)
                    && !path.StartsWith(
                        "UNSIGNED_WINDOWS_PREVIEW_VISUAL_PROOF-",
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

            JsonElement finalization = documents[finalizationFileName].Root;
            var finalizationProperties = new HashSet<string>(
                [
                    "authenticodeVerification",
                    "captureInventorySha256",
                    "captureSource",
                    "contractName",
                    "contractVersion",
                    "finalizationSource",
                    "generatedAt",
                    "proofs",
                    "reviewer",
                    "reviewerWasCaptureActor",
                    "status"
                ],
                StringComparer.Ordinal);
            if (allowUnsigned)
            {
                finalizationProperties.Add("accountableReviewConfirmed");
                finalizationProperties.Add("captureArtifact");
                finalizationProperties.Add("confirmations");
                finalizationProperties.Add("deployAuthorized");
                finalizationProperties.Add("policy");
                finalizationProperties.Add("publicationAuthorized");
                finalizationProperties.Add("reviewerKind");
                finalizationProperties.Add("uiUploadAuthorized");
                finalizationProperties.Add("uploadAuthorized");
            }
            else
            {
                finalizationProperties.Add("humanReviewConfirmed");
                finalizationProperties.Add("scopeApproval");
            }
            if (!ExactPropertySet(
                    finalization,
                    finalizationProperties))
            {
                throw new InvalidDataException(
                    "candidate Windows-only native finalization property set drifted");
            }
            RequireExactString(
                finalization,
                "contractName",
                finalizationContract);
            RequireExactInt32(finalization, "contractVersion", allowUnsigned ? 1 : 2);
            RequireExactString(finalization, "status", "passed");
            RequireBoolean(
                finalization,
                allowUnsigned
                    ? "accountableReviewConfirmed"
                    : "humanReviewConfirmed",
                expected: true);
            RequireBoolean(finalization, "reviewerWasCaptureActor", expected: false);
            RequireExactString(finalization, "reviewer", reviewer);
            if (allowUnsigned)
            {
                RequireExactString(finalization, "reviewer", "ArchonMegalon");
                RequireExactString(
                    finalization,
                    "reviewerKind",
                    "authenticated_account_owner_delegated_operator");
                RequireUnsignedEvidenceOnlyPolicy(
                    RequireObject(finalization, "policy"),
                    "candidate native-Windows finalization");
                RequireNoUnsignedPublicationAuthority(
                    finalization,
                    "candidate native-Windows finalization");
                JsonElement captureArtifact = RequireObject(
                    finalization,
                    "captureArtifact");
                if (!ExactPropertySet(
                        captureArtifact,
                        new HashSet<string>(["id", "name", "sha256"], StringComparer.Ordinal)))
                {
                    throw new InvalidDataException(
                        "candidate native-Windows capture artifact binding drifted");
                }
                _ = RequirePositiveGitHubIntegerString(captureArtifact, "id");
                RequireExactString(
                    captureArtifact,
                    "name",
                    RequireString(captureReceiptSource, "artifactName"));
                _ = RequireSha256(captureArtifact, "sha256");
            }
            RequireExactString(
                finalization,
                "captureInventorySha256",
                captureInventorySha256);
            JsonElement finalizationReceiptCaptureSource = RequireObject(
                finalization,
                "captureSource");
            JsonElement finalizationReceiptSource = RequireObject(
                finalization,
                "finalizationSource");
            if (allowUnsigned)
            {
                if (!JsonSemanticEquals(
                        finalizationReceiptCaptureSource,
                        captureReceiptSource))
                {
                    throw new InvalidDataException(
                        "candidate native-Windows finalization capture source drifted");
                }
                ValidateUnsignedFullEvidenceSource(
                    finalizationReceiptSource,
                    finalizationSource,
                    captureActor: false,
                    reviewer);
            }
            else if (!JsonSemanticEquals(
                         finalizationReceiptCaptureSource,
                         captureSource)
                     || !JsonSemanticEquals(
                         finalizationReceiptSource,
                         finalizationSource))
            {
                throw new InvalidDataException(
                    "candidate native-Windows finalization source drifted");
            }
            if (RequireFreshUtcTimestamp(finalization, "generatedAt", now)
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
            if (allowUnsigned)
            {
                JsonElement confirmations = RequireObject(
                    finalization,
                    "confirmations");
                RequirePassedUnsignedNativeConfirmations(
                    confirmations,
                    "candidate native-Windows finalization");
            }
            else
            {
                JsonElement scopeApproval = RequireObject(
                    finalization,
                    "scopeApproval");
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
            }
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
                if (allowUnsigned
                    && !string.Equals(
                        path,
                        $"UNSIGNED_WINDOWS_PREVIEW_VISUAL_PROOF-{head}-{WindowsRid}.generated.json",
                        StringComparison.Ordinal)
                    || !scope.Heads.Contains(head, StringComparer.Ordinal)
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
                captureInventoryFileName,
                finalizationFileName
            };
            if (!allowUnsigned)
            {
                expectedFinalizedPaths.Add(
                    "PREVIEW_NIGHTLY_PUBLICATION_SCOPE_APPROVAL.generated.json");
            }
            expectedFinalizedPaths.UnionWith(
                proofsByHead.Values.Select(static proof => proof.Path));
            if (!expectedFinalizedPaths.SetEquals(finalizedByPath.Keys))
            {
                throw new InvalidDataException(
                    "candidate finalized native-Windows inventory file scope drifted");
            }
            var expectedDocumentPaths = new HashSet<string>(
                finalizedByPath.Keys,
                StringComparer.Ordinal)
            {
                finalizedInventoryFileName
            };
            if (!expectedDocumentPaths.SetEquals(documents.Keys))
            {
                throw new InvalidDataException("candidate native-Windows evidence file scope drifted");
            }

            JsonElement export = documents[candidateProvenanceExportFileName].Root;
            if (!allowUnsigned)
            {
                ValidateCandidateExportReceipt(
                    export,
                    captureCandidate,
                    candidate.CanonicalManifestSha256,
                    scope);
            }
            else
            {
                ValidateUnsignedCandidateExportReceipt(
                    export,
                    captureCandidate,
                    provenance,
                    provenanceRows,
                    scope);
            }

            foreach (string head in scope.Heads)
            {
                CandidateHeadArtifacts headArtifacts = scope.Artifacts[head];
                string startupPath =
                    $"startup-smoke/startup-smoke-{head}-{WindowsRid}.receipt.json";
                JsonElement startup = documents[startupPath].Root;
                if (allowUnsigned)
                {
                    ValidateUnsignedStartupReceipt(
                        startup,
                        head,
                        scope.Version,
                        scope.Channel,
                        headArtifacts.Installer.FileName,
                        headArtifacts.Installer.Sha256,
                        headArtifacts.Payload.FileName,
                        headArtifacts.Payload.Sha256,
                        headArtifacts.Payload.SizeBytes,
                        now);
                }
                else
                {
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
                        throw new InvalidDataException(
                            "candidate startup payload size drifted");
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
                        throw new InvalidDataException(
                            "candidate startup runner is not native Windows");
                    }
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
                    allowUnsigned
                        ? "chummer6-ui.unsigned-preview-windows-installer-visual-proof"
                        : "chummer6-ui.windows_installer_visual_proof");
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
                var checkProperties = allowUnsigned
                    ? new HashSet<string>(
                        ["accountable_review_confirmed", "capture_mode"],
                        StringComparer.Ordinal)
                    : new HashSet<string>(
                        ["capture_mode", "human_review_confirmed"],
                        StringComparer.Ordinal);
                if (!ExactPropertySet(
                        checks,
                        checkProperties))
                {
                    throw new InvalidDataException("candidate visual checks property set drifted");
                }
                RequireExactString(
                    checks,
                    "capture_mode",
                    allowUnsigned ? "hosted_native_windows" : "interactive");
                RequireBoolean(
                    checks,
                    allowUnsigned
                        ? "accountable_review_confirmed"
                        : "human_review_confirmed",
                    expected: true);
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
                    allowUnsigned
                        ? "pinned contract identity plus protected environment and authenticated workflow actor"
                        : "repository variable plus protected environment");
                JsonElement confirmations = RequireObject(
                    review,
                    "explicitConfirmations");
                if (allowUnsigned)
                {
                    RequirePassedUnsignedNativeConfirmations(
                        confirmations,
                        "candidate visual review");
                }
                else
                {
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
                if (allowUnsigned)
                {
                    captureBindingKeys.Add("rerunPolicy");
                    captureBindingKeys.Add("triggeringActor");
                }
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
                        RequireString(
                            allowUnsigned
                                ? captureReceiptSource
                                : captureSource,
                            property));
                }
                RequireExactString(
                    captureBinding,
                    "inventorySha256",
                    Sha256(captureInventoryDocument.Bytes));
                if (!JsonSemanticEquals(
                        RequireObject(proof, "finalizationBinding"),
                        allowUnsigned
                            ? finalizationReceiptSource
                            : finalizationSource))
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
                string[] expectedRoles = allowUnsigned
                    ? ["startup", "progress", "completion"]
                    : ["progress", "completion"];
                if (screenshots.GetArrayLength() != expectedRoles.Length)
                {
                    throw new InvalidDataException("candidate visual screenshot set drifted");
                }
                var visualScreenshots =
                    new List<CandidateScreenshotBinding>(expectedRoles.Length);
                int screenshotIndex = 0;
                foreach (JsonElement screenshot in screenshots.EnumerateArray())
                {
                    if (!ExactPropertySet(
                            screenshot,
                            new HashSet<string>(["role", "path", "sha256"], StringComparer.Ordinal)))
                    {
                        throw new InvalidDataException("candidate visual screenshot binding drifted");
                    }
                    string role = RequireString(screenshot, "role");
                    string expectedRole = expectedRoles[screenshotIndex++];
                    string path = RequireString(screenshot, "path");
                    string digest = RequireSha256(screenshot, "sha256");
                    string expectedPath = string.Equals(
                            expectedRole,
                            "startup",
                            StringComparison.Ordinal)
                        ? "screenshots/windows-application-avalonia-win-x64-startup.png"
                        : $"screenshots/windows-installer-{head}-{WindowsRid}-{expectedRole}.png";
                    if (!string.Equals(role, expectedRole, StringComparison.Ordinal)
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
                bool screenshotsMatch = allowUnsigned
                    ? visualScreenshots.Skip(1).SequenceEqual(captureScreenshots[head])
                    : visualScreenshots.SequenceEqual(captureScreenshots[head]);
                if (!screenshotsMatch)
                {
                    throw new InvalidDataException(
                        "candidate visual screenshots differ from the capture head");
                }
            }

            return new CandidateNativePackage(
                captureInventorySha256,
                documents[finalizationFileName].Bytes.ToArray(),
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

    internal static void ValidateUnsignedStartupReceipt(
        JsonElement startup,
        string head,
        string version,
        string channel,
        string installerFileName,
        string installerSha256,
        string payloadFileName,
        string payloadSha256,
        long payloadSizeBytes,
        DateTimeOffset now)
    {
        var legacyKeys = new HashSet<string>(
            [
                "artifactDigest",
                "artifactFileName",
                "bootstrapPayloadAcquisitionMode",
                "bootstrapPayloadFileName",
                "bootstrapPayloadSha256",
                "bootstrapPayloadSizeBytes",
                "channelId",
                "executionEnvironment",
                "headId",
                "nativeHostEvidence",
                "platform",
                "readyCheckpoint",
                "releaseVersion",
                "rid",
                "status"
            ],
            StringComparer.Ordinal);
        var currentKeys = new HashSet<string>(legacyKeys, StringComparer.Ordinal)
        {
            "arch",
            "artifactDigestSource",
            "artifactId",
            "artifactInstallMode",
            "artifactPath",
            "artifactPathDisclosure",
            "artifactRelativePath",
            "artifactSha256",
            "bootstrapPayloadDownloadUrl",
            "completedAtUtc",
            "fileName",
            "framework",
            "hostClass",
            "installLinkingInstallationId",
            "installLinkingLaunchCount",
            "installLinkingPromptReason",
            "installLinkingPromptRequired",
            "installLinkingStatus",
            "operatingSystem",
            "processPath",
            "processPathDisclosure",
            "recordedAtUtc",
            "startedAtUtc",
            "verificationScope",
            "version"
        };
        bool current = ExactPropertySet(startup, currentKeys);
        if (!current && !ExactPropertySet(startup, legacyKeys))
        {
            throw new InvalidDataException(
                "unsigned startup receipt property set drifted");
        }

        RequireExactString(startup, "status", "pass");
        RequireExactString(startup, "readyCheckpoint", "pre_ui_event_loop");
        RequireExactString(startup, "executionEnvironment", "native_windows");
        RequireExactString(startup, "headId", head);
        RequireExactString(startup, "platform", "windows");
        RequireExactString(startup, "rid", WindowsRid);
        RequireExactString(startup, "releaseVersion", version);
        RequireExactString(startup, "channelId", channel);
        RequireExactString(startup, "artifactFileName", installerFileName);
        RequireExactString(
            startup,
            "artifactDigest",
            $"sha256:{installerSha256}");
        RequireExactString(startup, "bootstrapPayloadAcquisitionMode", "download");
        RequireExactString(startup, "bootstrapPayloadFileName", payloadFileName);
        RequireExactString(startup, "bootstrapPayloadSha256", payloadSha256);
        if (RequireNonNegativeInt64(startup, "bootstrapPayloadSizeBytes")
            != payloadSizeBytes)
        {
            throw new InvalidDataException("candidate startup payload size drifted");
        }

        JsonElement nativeHost = RequireObject(startup, "nativeHostEvidence");
        if (!ExactPropertySet(
                nativeHost,
                new HashSet<string>(
                    [
                        "contractName",
                        "evidenceSource",
                        "hostKernel",
                        "hostPlatform",
                        "isNativeWindows",
                        "runner",
                        "status"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned startup native host property set drifted");
        }
        RequireExactString(
            nativeHost,
            "contractName",
            "chummer6-ui.native_windows_host_evidence");
        RequireExactString(nativeHost, "status", "verified");
        RequireBoolean(nativeHost, "isNativeWindows", expected: true);
        RequireExactString(nativeHost, "hostPlatform", "windows");
        string hostKernel = RequireString(nativeHost, "hostKernel");
        string runner = RequireString(nativeHost, "runner");
        if (current)
        {
            RequireExactString(
                nativeHost,
                "evidenceSource",
                "host_kernel_and_runner_selection");
            RequireExactString(nativeHost, "runner", "pwsh");
            if (!Regex.IsMatch(
                    hostKernel,
                    @"\A(?:MINGW64|MSYS|CYGWIN)_NT-[0-9]+\.[0-9]+(?:-[0-9]+)?\z",
                    RegexOptions.CultureInvariant))
            {
                throw new InvalidDataException(
                    "unsigned startup native host kernel drifted");
            }
        }
        else
        {
            RequireExactString(
                nativeHost,
                "evidenceSource",
                "GitHub-hosted windows-latest");
            RequireExactString(nativeHost, "runner", "powershell.exe");
            if (string.IsNullOrWhiteSpace(hostKernel))
            {
                throw new InvalidDataException(
                    "unsigned startup native host kernel drifted");
            }
        }
        if (string.IsNullOrWhiteSpace(runner)
            || runner.Contains("wine", StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidDataException(
                "candidate startup runner is not native Windows");
        }

        if (!current)
        {
            return;
        }

        string installerPath = $"files/{installerFileName}";
        RequireExactString(startup, "arch", "x64");
        RequireExactString(startup, "version", version);
        RequireExactString(
            startup,
            "hostClass",
            "github-hosted-windows-latest-native");
        RequireExactString(
            startup,
            "verificationScope",
            "native_windows_startup");
        RequireExactString(startup, "artifactDigestSource", "environment");
        RequireExactString(
            startup,
            "artifactInstallMode",
            "nsis_bootstrap_installer");
        RequireExactString(startup, "artifactPath", installerPath);
        RequireExactString(
            startup,
            "artifactPathDisclosure",
            "artifact_shelf_relative_path");
        RequireExactString(startup, "artifactRelativePath", installerPath);
        RequireExactString(startup, "artifactSha256", installerSha256);
        RequireExactString(startup, "fileName", installerFileName);
        RequireExactString(startup, "artifactId", $"{head}-{WindowsRid}-installer");

        string payloadUrlText = RequireString(
            startup,
            "bootstrapPayloadDownloadUrl");
        if (!Uri.TryCreate(payloadUrlText, UriKind.Absolute, out Uri? payloadUrl)
            || !string.Equals(payloadUrl.Scheme, Uri.UriSchemeHttp, StringComparison.Ordinal)
            || !string.Equals(payloadUrl.Host, "127.0.0.1", StringComparison.Ordinal)
            || payloadUrl.Port is < 1 or > 65535
            || !string.Equals(
                payloadUrl.AbsolutePath,
                $"/{payloadFileName}",
                StringComparison.Ordinal)
            || payloadUrl.Query.Length != 0
            || payloadUrl.Fragment.Length != 0
            || payloadUrl.UserInfo.Length != 0)
        {
            throw new InvalidDataException(
                "unsigned startup payload download URL drifted");
        }

        RequireExactString(startup, "processPathDisclosure", "file_name_only");
        RequireExactString(startup, "processPath", "Chummer.Avalonia.exe");
        string framework = RequireString(startup, "framework");
        if (!Regex.IsMatch(
                framework,
                @"\A\.NET [0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9._-]+)?\z",
                RegexOptions.CultureInvariant))
        {
            throw new InvalidDataException(
                "unsigned startup framework identity drifted");
        }
        string operatingSystem = RequireString(startup, "operatingSystem");
        if (!Regex.IsMatch(
                operatingSystem,
                @"\AMicrosoft Windows [0-9]+(?:\.[0-9]+){1,3}\z",
                RegexOptions.CultureInvariant))
        {
            throw new InvalidDataException(
                "unsigned startup operating-system identity drifted");
        }
        RequireExactString(startup, "installLinkingStatus", "guest");
        RequireBoolean(startup, "installLinkingPromptRequired", expected: true);
        RequireExactString(
            startup,
            "installLinkingPromptReason",
            "claim_required");
        RequireExactInt32(startup, "installLinkingLaunchCount", 1);
        string installationId = RequireString(
            startup,
            "installLinkingInstallationId");
        if (!Regex.IsMatch(
                installationId,
                @"\Ains-[0-9a-f]{32}\z",
                RegexOptions.CultureInvariant))
        {
            throw new InvalidDataException(
                "unsigned startup installation identity drifted");
        }

        DateTimeOffset started = RequireFreshUtcTimestamp(
            startup,
            "startedAtUtc",
            now);
        DateTimeOffset recorded = RequireFreshUtcTimestamp(
            startup,
            "recordedAtUtc",
            now);
        DateTimeOffset completed = RequireFreshUtcTimestamp(
            startup,
            "completedAtUtc",
            now);
        if (started > recorded
            || recorded > completed
            || completed - started > TimeSpan.FromMinutes(10))
        {
            throw new InvalidDataException(
                "unsigned startup timestamp sequence drifted");
        }
    }

    private static CandidateWindowsScope ParseCandidateWindowsScope(
        JsonElement canonical,
        ReleaseUploadCandidateIdentity candidate,
        IReadOnlyList<ReleaseUploadCandidateInventoryRow> candidateInventory,
        bool allowAdditionalRetainedShelfFiles = false)
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
        string[] heads = RequirePromotedDesktopHeads(canonical);
        var headSet = new HashSet<string>(heads, StringComparer.Ordinal);
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
            string head = RequireString(artifact, "head");
            string platform = RequireString(artifact, "platform");
            string rid = RequireString(artifact, "rid");
            string kind = RequireString(artifact, "kind");
            bool incomingWindows =
                string.Equals(platform, "windows", StringComparison.Ordinal);
            if (!HeadPattern.IsMatch(head)
                || !headSet.Contains(head)
                    && (!allowAdditionalRetainedShelfFiles || incomingWindows))
            {
                throw new InvalidDataException(
                    "candidate release manifest contains a desktop artifact outside "
                    + "requiredDesktopHeads");
            }
            bool validTuple = platform switch
            {
                "windows" =>
                    string.Equals(kind, "installer", StringComparison.Ordinal)
                    && string.Equals(rid, WindowsRid, StringComparison.Ordinal),
                "linux" =>
                    (string.Equals(kind, "installer", StringComparison.Ordinal)
                        || allowAdditionalRetainedShelfFiles
                            && string.Equals(kind, "archive", StringComparison.Ordinal))
                    && string.Equals(rid, "linux-x64", StringComparison.Ordinal),
                "macos" =>
                    (string.Equals(kind, "installer", StringComparison.Ordinal)
                        || allowAdditionalRetainedShelfFiles
                            && string.Equals(kind, "archive", StringComparison.Ordinal))
                    && rid is "osx-arm64" or "osx-x64",
                _ => false
            };
            if (!validTuple)
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
        bool inventoryMatches = allowAdditionalRetainedShelfFiles
            ? expectedCandidatePaths.IsSubsetOf(actualCandidatePaths)
            : actualCandidatePaths.SetEquals(expectedCandidatePaths);
        if (!inventoryMatches)
        {
            throw new InvalidDataException(
                "candidate upload inventory differs from the exact finalized desktop shelf");
        }
        return new CandidateWindowsScope(version, channel, heads, artifacts);
    }

    private static string[] RequirePromotedDesktopHeads(JsonElement canonical)
    {
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
        return heads.ToArray();
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
        JsonElement authenticodeVerification,
        bool allowUnsigned)
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
            if (allowUnsigned)
            {
                ValidateUnsignedCaptureArtifactBinding(
                    RequireObject(row, "installer"),
                    artifacts.Installer,
                    "candidate capture installer");
                ValidateUnsignedCaptureArtifactBinding(
                    RequireObject(row, "payload"),
                    artifacts.Payload,
                    "candidate capture payload");
            }
            else
            {
                ValidateExportArtifactBinding(
                    RequireObject(row, "installer"),
                    artifacts.Installer);
                ValidateExportArtifactBinding(
                    RequireObject(row, "payload"),
                    artifacts.Payload);
            }
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

    private static void ValidateUnsignedCaptureArtifactBinding(
        JsonElement binding,
        CandidateArtifact artifact,
        string label)
    {
        if (!ExactPropertySet(
                binding,
                new HashSet<string>(
                    ["fileName", "sha256", "sizeBytes"],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException($"{label} property set drifted");
        }
        RequireExactString(binding, "fileName", artifact.FileName);
        RequireExactString(binding, "sha256", artifact.Sha256);
        if (RequirePositiveInt64(binding, "sizeBytes") != artifact.SizeBytes)
        {
            throw new InvalidDataException($"{label} bytes drifted");
        }
    }

    private static void ValidateAuthenticodeInventoryBinding(
        JsonElement binding,
        string expectedPath,
        IReadOnlyDictionary<string, ReleaseUploadCandidateInventoryRow> finalizedByPath,
        string label,
        bool allowUnsigned)
    {
        var expectedProperties = new HashSet<string>(
            [
                        "path",
                        "sha256",
                        "sizeBytes"
            ],
            StringComparer.Ordinal);
        if (allowUnsigned)
        {
            expectedProperties.UnionWith(
                ["signatureStatus", "signingRequired", "unsignedReason"]);
        }
        else
        {
            expectedProperties.UnionWith(
                ["signerCertificateSha256", "signerSpkiSha256", "timestampUtc"]);
        }
        if (!ExactPropertySet(binding, expectedProperties))
        {
            throw new InvalidDataException($"{label} property set drifted");
        }
        RequireExactString(binding, "path", expectedPath);
        string digest = RequireSha256(binding, "sha256");
        long size = RequirePositiveInt64(binding, "sizeBytes");
        if (allowUnsigned)
        {
            RequireExactString(binding, "signatureStatus", "unsigned");
            RequireBoolean(binding, "signingRequired", expected: false);
            RequireExactString(binding, "unsignedReason", "preview_policy");
        }
        else
        {
            _ = RequireSha256(binding, "signerCertificateSha256");
            _ = RequireSha256(binding, "signerSpkiSha256");
            _ = RequireUtcTimestamp(binding, "timestampUtc");
        }
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
        DateTimeOffset captureGeneratedAt,
        string contentInventoryPath,
        string exportReceiptPath)
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
            contentInventoryPath,
            documents);
        ValidateCaptureDocumentBinding(
            captureCandidate,
            "exportReceipt",
            "exportReceiptSha256",
            exportReceiptPath,
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

    private static JsonElement ValidateUnsignedCaptureCandidateBinding(
        JsonElement captureCandidate,
        IReadOnlyDictionary<string, CandidateEvidenceDocument> documents,
        IReadOnlyDictionary<string, ReleaseUploadCandidateInventoryRow> finalizedByPath,
        IReadOnlyList<ReleaseUploadCandidateInventoryRow> provenanceRows,
        CandidateWindowsScope scope,
        string contentInventoryDocumentPath,
        string exportReceiptDocumentPath,
        string expectedSourceCanonicalSha256,
        long expectedSourceCanonicalSize,
        string? expectedProducerSourceSha)
    {
        if (!ExactPropertySet(
                captureCandidate,
                new HashSet<string>(
                    [
                        "artifact",
                        "compositionRequest",
                        "contentInventory",
                        "exportReceipt",
                        "installer",
                        "manifest",
                        "payload",
                        "platformScope",
                        "release",
                        "signature",
                        "source",
                        "sourceSha",
                        "validatedInventoryFileCount",
                        "validatedProposalSha256",
                        "validatedProposalSourceSha"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned candidate capture binding property set drifted");
        }

        JsonElement source = RequireObject(captureCandidate, "source");
        var sourceProperties = new HashSet<string>(
            ["actor", "ref", "repository", "runAttempt", "runId", "sha", "workflow"],
            StringComparer.Ordinal);
        if (!ExactPropertySet(source, sourceProperties))
        {
            throw new InvalidDataException(
                "unsigned candidate producer source property set drifted");
        }
        RequireExactString(source, "repository", UiRepository);
        RequireExactString(source, "workflow", UnsignedProducerWorkflow);
        RequireExactString(source, "ref", UiRef);
        string sourceSha = RequireString(source, "sha");
        if (!CommitPattern.IsMatch(sourceSha)
            || expectedProducerSourceSha is not null
                && !string.Equals(
                    sourceSha,
                    expectedProducerSourceSha,
                    StringComparison.Ordinal)
            || !GitHubLoginPattern.IsMatch(RequireString(source, "actor")))
        {
            throw new InvalidDataException(
                "unsigned candidate producer provenance drifted");
        }
        string producerRunId = RequirePositiveGitHubIntegerString(source, "runId");
        string producerRunAttempt = RequirePositiveGitHubIntegerString(
            source,
            "runAttempt");

        JsonElement artifact = RequireObject(captureCandidate, "artifact");
        if (!ExactPropertySet(
                artifact,
                new HashSet<string>(["id", "name", "sha256"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned candidate transport artifact binding drifted");
        }
        _ = RequirePositiveGitHubIntegerString(artifact, "id");
        RequireExactString(
            artifact,
            "name",
            $"unsigned-windows-preview-nightly-candidate-{producerRunId}-{producerRunAttempt}");
        _ = RequireSha256(artifact, "sha256");

        RequireExactString(captureCandidate, "platformScope", "windows_only");
        RequireExactString(captureCandidate, "sourceSha", sourceSha);
        RequireExactString(
            captureCandidate,
            "validatedProposalSourceSha",
            sourceSha);
        ValidateUnsignedManifestSignature(
            RequireObject(captureCandidate, "signature"));
        JsonElement release = RequireObject(captureCandidate, "release");
        if (!ExactPropertySet(
                release,
                new HashSet<string>(["channel", "version"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned candidate capture release binding drifted");
        }
        RequireExactString(release, "channel", "preview");
        RequireExactString(release, "version", scope.Version);

        ValidateUnsignedCandidateDocumentBinding(
            RequireObject(captureCandidate, "contentInventory"),
            UnsignedCandidateProvenanceInventoryFileName[
                "candidate-provenance/".Length..],
            contentInventoryDocumentPath,
            documents,
            "unsigned candidate content inventory");
        ValidateUnsignedCandidateDocumentBinding(
            RequireObject(captureCandidate, "exportReceipt"),
            UnsignedCandidateProvenanceExportFileName[
                "candidate-provenance/".Length..],
            exportReceiptDocumentPath,
            documents,
            "unsigned candidate export receipt");

        var provenanceByPath = provenanceRows.ToDictionary(
            static row => row.Path,
            StringComparer.Ordinal);
        ValidateUnsignedCandidateRowBinding(
            RequireObject(captureCandidate, "compositionRequest"),
            "PREVIEW_NIGHTLY_UNSIGNED_COMPOSITION.proposed.json",
            provenanceByPath,
            "unsigned candidate composition request");
        RequireExactString(
            captureCandidate,
            "validatedProposalSha256",
            provenanceByPath[
                "PREVIEW_NIGHTLY_UNSIGNED_COMPOSITION.proposed.json"].Sha256);
        if (RequirePositiveInt32(
                captureCandidate,
                "validatedInventoryFileCount") != provenanceRows.Count)
        {
            throw new InvalidDataException(
                "unsigned candidate validated file count drifted");
        }

        CandidateHeadArtifacts artifacts = scope.Artifacts["avalonia"];
        ValidateUnsignedCandidateArtifactBinding(
            RequireObject(captureCandidate, "installer"),
            $"publication/{artifacts.Installer.Path}",
            artifacts.Installer,
            provenanceByPath,
            includeFileName: true,
            "unsigned candidate installer");
        ValidateUnsignedCandidateArtifactBinding(
            RequireObject(captureCandidate, "payload"),
            $"publication/{artifacts.Payload.Path}",
            artifacts.Payload,
            provenanceByPath,
            includeFileName: true,
            "unsigned candidate payload");
        JsonElement manifest = RequireObject(captureCandidate, "manifest");
        if (!ExactPropertySet(
                manifest,
                new HashSet<string>(["path", "sha256", "sizeBytes"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned candidate manifest binding property set drifted");
        }
        const string manifestPath = "publication/RELEASE_CHANNEL.generated.json";
        RequireExactString(manifest, "path", manifestPath);
        RequireExactString(
            manifest,
            "sha256",
            expectedSourceCanonicalSha256);
        if (!provenanceByPath.TryGetValue(
                manifestPath,
                out ReleaseUploadCandidateInventoryRow? manifestRow)
            || !string.Equals(
                manifestRow.Sha256,
                expectedSourceCanonicalSha256,
                StringComparison.Ordinal)
            || manifestRow.SizeBytes != expectedSourceCanonicalSize
            || manifestRow.SizeBytes != RequirePositiveInt64(manifest, "sizeBytes")
            || !finalizedByPath.TryGetValue(
                contentInventoryDocumentPath,
                out ReleaseUploadCandidateInventoryRow? inventoryDocumentRow)
            || inventoryDocumentRow.SizeBytes < 1)
        {
            throw new InvalidDataException("unsigned candidate manifest custody drifted");
        }
        return captureCandidate;
    }

    private static void ValidateUnsignedCandidateDocumentBinding(
        JsonElement binding,
        string expectedBindingPath,
        string documentPath,
        IReadOnlyDictionary<string, CandidateEvidenceDocument> documents,
        string label)
    {
        if (!ExactPropertySet(
                binding,
                new HashSet<string>(["path", "sha256", "sizeBytes"], StringComparer.Ordinal))
            || !documents.TryGetValue(
                documentPath,
                out CandidateEvidenceDocument? document))
        {
            throw new InvalidDataException($"{label} custody drifted");
        }
        RequireExactString(binding, "path", expectedBindingPath);
        RequireExactString(binding, "sha256", document.Sha256);
        if (RequirePositiveInt64(binding, "sizeBytes") != document.SizeBytes)
        {
            throw new InvalidDataException($"{label} size drifted");
        }
    }

    private static void ValidateUnsignedCandidateRowBinding(
        JsonElement binding,
        string expectedPath,
        IReadOnlyDictionary<string, ReleaseUploadCandidateInventoryRow> rows,
        string label)
    {
        if (!ExactPropertySet(
                binding,
                new HashSet<string>(["path", "sha256", "sizeBytes"], StringComparer.Ordinal))
            || !rows.TryGetValue(
                expectedPath,
                out ReleaseUploadCandidateInventoryRow? row))
        {
            throw new InvalidDataException($"{label} custody drifted");
        }
        RequireExactString(binding, "path", expectedPath);
        RequireExactString(binding, "sha256", row.Sha256);
        if (RequirePositiveInt64(binding, "sizeBytes") != row.SizeBytes)
        {
            throw new InvalidDataException($"{label} size drifted");
        }
    }

    private static void ValidateUnsignedCandidateArtifactBinding(
        JsonElement binding,
        string expectedPath,
        CandidateArtifact artifact,
        IReadOnlyDictionary<string, ReleaseUploadCandidateInventoryRow> rows,
        bool includeFileName,
        string label)
    {
        var expectedProperties = new HashSet<string>(
            ["path", "sha256", "sizeBytes"],
            StringComparer.Ordinal);
        if (includeFileName)
        {
            expectedProperties.Add("fileName");
        }
        if (!ExactPropertySet(binding, expectedProperties)
            || !rows.TryGetValue(
                expectedPath,
                out ReleaseUploadCandidateInventoryRow? row))
        {
            throw new InvalidDataException($"{label} custody drifted");
        }
        RequireExactString(binding, "path", expectedPath);
        if (includeFileName)
        {
            RequireExactString(binding, "fileName", artifact.FileName);
        }
        RequireExactString(binding, "sha256", artifact.Sha256);
        if (RequirePositiveInt64(binding, "sizeBytes") != artifact.SizeBytes
            || row.Sha256 != artifact.Sha256
            || row.SizeBytes != artifact.SizeBytes)
        {
            throw new InvalidDataException($"{label} bytes drifted");
        }
    }

    private static void RequireUnsignedEvidenceOnlyPolicy(
        JsonElement policy,
        string label)
    {
        if (!ExactPropertySet(
                policy,
                new HashSet<string>(
                    [
                        "authenticodeRequired",
                        "evidenceOnly",
                        "releaseChannel",
                        "signingRequirement"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException($"{label} policy property set drifted");
        }
        RequireBoolean(policy, "authenticodeRequired", expected: false);
        RequireBoolean(policy, "evidenceOnly", expected: true);
        RequireExactString(policy, "releaseChannel", "preview");
        RequireExactString(
            policy,
            "signingRequirement",
            "preview_unsigned_allowed");
    }

    private static void RequireNoUnsignedPublicationAuthority(
        JsonElement parent,
        string label)
    {
        foreach (string property in new[]
                 {
                     "deployAuthorized",
                     "publicationAuthorized",
                     "uiUploadAuthorized",
                     "uploadAuthorized"
                 })
        {
            if (!parent.TryGetProperty(property, out JsonElement value)
                || value.ValueKind != JsonValueKind.False)
            {
                throw new InvalidDataException(
                    $"{label} {property} must be exactly false");
            }
        }
    }

    private static void ValidateUnsignedFullEvidenceSource(
        JsonElement source,
        JsonElement projection,
        bool captureActor,
        string reviewer)
    {
        var properties = new HashSet<string>(
            [
                "actor",
                "artifactName",
                "ref",
                "repository",
                "rerunPolicy",
                "runAttempt",
                "runId",
                "sha",
                "triggeringActor",
                "workflow"
            ],
            StringComparer.Ordinal);
        if (!ExactPropertySet(source, properties))
        {
            throw new InvalidDataException(
                "unsigned native-Windows source property set drifted");
        }
        foreach (string property in new[]
                 {
                     "actor",
                     "artifactName",
                     "ref",
                     "repository",
                     "runAttempt",
                     "runId",
                     "sha",
                     "workflow"
                 })
        {
            RequireExactString(
                source,
                property,
                RequireString(projection, property));
        }
        RequireExactString(source, "rerunPolicy", "same-actor-only");
        string expectedActor = captureActor ? "github-actions[bot]" : reviewer;
        RequireExactString(source, "actor", expectedActor);
        RequireExactString(source, "triggeringActor", expectedActor);
    }

    private static void ValidateUnsignedPreservedCandidateFiles(
        JsonElement files,
        IReadOnlyDictionary<string, CandidateEvidenceDocument> documents,
        string inventoryPath,
        string exportPath)
    {
        string[] expectedPaths = [inventoryPath, exportPath];
        if (files.GetArrayLength() != expectedPaths.Length)
        {
            throw new InvalidDataException(
                "unsigned preserved candidate file scope drifted");
        }
        int index = 0;
        foreach (JsonElement row in files.EnumerateArray())
        {
            string expectedPath = expectedPaths[index++];
            ValidateEvidenceByteReference(
                row,
                documents,
                "unsigned preserved candidate file");
            RequireExactString(row, "path", expectedPath);
        }
    }

    private static void ValidateUnsignedAuthenticodeReceipt(
        JsonElement receipt,
        JsonElement captureCandidate,
        JsonElement captureSource,
        DateTimeOffset now)
    {
        if (!ExactPropertySet(
                receipt,
                new HashSet<string>(
                    [
                        "artifact",
                        "contractName",
                        "contractVersion",
                        "generatedAt",
                        "nativeHostEvidence",
                        "signatureStatus",
                        "signingRequired",
                        "source",
                        "status",
                        "unsignedReason",
                        "verifier"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned Authenticode receipt property set drifted");
        }
        RequireExactString(
            receipt,
            "contractName",
            "chummer6-ui.unsigned-preview-windows-authenticode-verification");
        RequireExactInt32(receipt, "contractVersion", 1);
        RequireExactString(receipt, "status", "verified");
        RequireExactString(receipt, "signatureStatus", "unsigned");
        RequireBoolean(receipt, "signingRequired", expected: false);
        RequireExactString(receipt, "unsignedReason", "preview_policy");
        _ = RequireFreshUtcTimestamp(receipt, "generatedAt", now);
        if (!JsonSemanticEquals(
                RequireObject(receipt, "artifact"),
                RequireObject(captureCandidate, "installer"))
            || !JsonSemanticEquals(
                RequireObject(receipt, "source"),
                captureSource))
        {
            throw new InvalidDataException(
                "unsigned Authenticode artifact or source binding drifted");
        }
        ValidateUnsignedNativeHost(
            RequireObject(receipt, "nativeHostEvidence"),
            "unsigned Authenticode receipt");
        JsonElement verifier = RequireObject(receipt, "verifier");
        if (!ExactPropertySet(
                verifier,
                new HashSet<string>(
                    [
                        "authenticodeStatus",
                        "implementation",
                        "platform",
                        "securityDirectoryEmpty"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned Authenticode verifier property set drifted");
        }
        RequireExactString(verifier, "authenticodeStatus", "NotSigned");
        RequireExactString(
            verifier,
            "implementation",
            "scripts/verify_unsigned_windows_preview_authenticode.ps1");
        RequireExactString(verifier, "platform", "windows");
        RequireBoolean(verifier, "securityDirectoryEmpty", expected: true);
    }

    private static void ValidateUnsignedScreenshotDocuments(
        IReadOnlyDictionary<string, CandidateEvidenceDocument> documents)
    {
        var dimensions = new Dictionary<string, (int Width, int Height)>(
            StringComparer.Ordinal);
        foreach ((string path, CandidateEvidenceDocument document) in documents)
        {
            if (!path.StartsWith("screenshots/", StringComparison.Ordinal)
                || !path.EndsWith(".png", StringComparison.Ordinal))
            {
                continue;
            }
            dimensions.Add(
                path,
                ValidateUnsignedPng(document.Bytes));
        }

        void ValidateDeclaredDimensions(JsonElement screenshot)
        {
            string path = RequireString(screenshot, "path");
            if (!dimensions.TryGetValue(path, out (int Width, int Height) actual)
                || RequirePositiveInt32(screenshot, "width") != actual.Width
                || RequirePositiveInt32(screenshot, "height") != actual.Height)
            {
                throw new InvalidDataException(
                    "unsigned screenshot declared dimensions differ from PNG IHDR");
            }
        }

        JsonElement capture = documents[UnsignedCaptureFileName].Root;
        foreach (JsonElement head in RequireArray(capture, "heads").EnumerateArray())
        {
            foreach (JsonElement screenshot in RequireArray(
                         head,
                         "screenshots").EnumerateArray())
            {
                ValidateDeclaredDimensions(screenshot);
            }
        }
        JsonElement native = RequireObject(capture, "nativeEvidence");
        foreach (JsonElement screenshot in RequireArray(
                     native,
                     "screenshots").EnumerateArray())
        {
            ValidateDeclaredDimensions(screenshot);
        }
        ValidateDeclaredDimensions(
            RequireObject(
                RequireObject(native, "startupVisual"),
                "screenshot"));
        ValidateDeclaredDimensions(
            RequireObject(
                documents[
                    "startup-visual/windows-application-avalonia-win-x64-startup.receipt.json"]
                    .Root,
                "startupScreenshot"));
    }

    private static void ValidateUnsignedNativeLogDocuments(
        IReadOnlyDictionary<string, CandidateEvidenceDocument> documents)
    {
        var pathsAndMarkers =
            new Dictionary<string, string[]>(StringComparer.Ordinal)
            {
                [
                    "startup-smoke/startup-smoke-avalonia-win-x64.log"
                ] = ["native startup passed"],
                [
                    "startup-smoke/startup-smoke-payload-http-avalonia-win-x64.log"
                ] = ["candidate payload download passed"],
                [
                    "startup-smoke/windows-installer-progress-avalonia-win-x64.log"
                ] =
                [
                    "Bootstrap temp root:",
                    "Payload download target:",
                    "Downloading application files",
                    "Verifying payload size",
                    "Verifying payload checksum",
                    "Extracting application files",
                    "Install complete"
                ]
            };
        foreach ((string path, string[] markers) in pathsAndMarkers)
        {
            byte[] bytes = documents[path].Bytes;
            if (bytes.Length is < 1 or > 1024 * 1024
                || bytes[^1] != (byte)'\n')
            {
                throw new InvalidDataException(
                    "unsigned native log framing drifted");
            }
            string text;
            try
            {
                text = new UTF8Encoding(
                    encoderShouldEmitUTF8Identifier: false,
                    throwOnInvalidBytes: true).GetString(bytes);
            }
            catch (DecoderFallbackException exception)
            {
                throw new InvalidDataException(
                    "unsigned native log is not UTF-8",
                    exception);
            }
            if (text.Any(character =>
                    character < 0x20
                    && character is not '\r' and not '\n' and not '\t'))
            {
                throw new InvalidDataException(
                    "unsigned native log contains control bytes");
            }
            int offset = 0;
            foreach (string marker in markers)
            {
                int markerOffset = text.IndexOf(
                    marker,
                    offset,
                    StringComparison.Ordinal);
                if (markerOffset < 0)
                {
                    throw new InvalidDataException(
                        "unsigned native log omits a required checkpoint");
                }
                offset = markerOffset + marker.Length;
            }
        }
    }

    private static (int Width, int Height) ValidateUnsignedPng(byte[] payload)
    {
        ReadOnlySpan<byte> signature =
            [0x89, (byte)'P', (byte)'N', (byte)'G', 0x0d, 0x0a, 0x1a, 0x0a];
        ReadOnlySpan<byte> bytes = payload;
        if (bytes.Length < 57 || !bytes[..8].SequenceEqual(signature))
        {
            throw new InvalidDataException(
                "unsigned screenshot evidence is not a complete PNG");
        }
        int offset = 8;
        int width = 0;
        int height = 0;
        int bitDepth = -1;
        int colorType = -1;
        bool sawHeader = false;
        bool sawData = false;
        bool sawEnd = false;
        using var compressed = new MemoryStream();
        while (offset < bytes.Length)
        {
            if (offset > bytes.Length - 12)
            {
                throw new InvalidDataException(
                    "unsigned screenshot PNG chunk framing drifted");
            }
            uint lengthValue = ReadBigEndianUInt32(bytes.Slice(offset, 4));
            if (lengthValue > int.MaxValue)
            {
                throw new InvalidDataException(
                    "unsigned screenshot PNG chunk is unbounded");
            }
            int length = (int)lengthValue;
            int dataStart = checked(offset + 8);
            int dataEnd = checked(dataStart + length);
            int crcEnd = checked(dataEnd + 4);
            if (crcEnd > bytes.Length)
            {
                throw new InvalidDataException(
                    "unsigned screenshot PNG chunk length drifted");
            }
            ReadOnlySpan<byte> type = bytes.Slice(offset + 4, 4);
            ReadOnlySpan<byte> data = bytes.Slice(dataStart, length);
            uint expectedCrc = ReadBigEndianUInt32(bytes.Slice(dataEnd, 4));
            if (ComputePngCrc(type, data) != expectedCrc)
            {
                throw new InvalidDataException(
                    "unsigned screenshot PNG chunk CRC drifted");
            }
            if (!sawHeader)
            {
                if (!type.SequenceEqual("IHDR"u8) || length != 13)
                {
                    throw new InvalidDataException(
                        "unsigned screenshot PNG IHDR drifted");
                }
                width = checked((int)ReadBigEndianUInt32(data[..4]));
                height = checked((int)ReadBigEndianUInt32(data.Slice(4, 4)));
                bitDepth = data[8];
                colorType = data[9];
                if (data[10] != 0 || data[11] != 0 || data[12] != 0)
                {
                    throw new InvalidDataException(
                        "unsigned screenshot PNG encoding mode drifted");
                }
                sawHeader = true;
            }
            else if (type.SequenceEqual("IHDR"u8))
            {
                throw new InvalidDataException(
                    "unsigned screenshot PNG repeats IHDR");
            }
            else if (type.SequenceEqual("IDAT"u8))
            {
                if (sawEnd)
                {
                    throw new InvalidDataException(
                        "unsigned screenshot PNG data follows IEND");
                }
                sawData = true;
                compressed.Write(data);
            }
            else if (type.SequenceEqual("IEND"u8))
            {
                if (length != 0 || !sawData || crcEnd != bytes.Length)
                {
                    throw new InvalidDataException(
                        "unsigned screenshot PNG IEND drifted");
                }
                sawEnd = true;
            }
            offset = crcEnd;
        }
        if (!sawHeader || !sawData || !sawEnd
            || width is < 320 or > 16384
            || height is < 200 or > 16384)
        {
            throw new InvalidDataException(
                "unsigned screenshot PNG structure or dimensions drifted");
        }
        int channels = colorType switch
        {
            0 => 1,
            2 => 3,
            3 => 1,
            4 => 2,
            6 => 4,
            _ => throw new InvalidDataException(
                "unsigned screenshot PNG color type drifted")
        };
        bool validDepth = colorType switch
        {
            0 => bitDepth is 1 or 2 or 4 or 8 or 16,
            2 => bitDepth is 8 or 16,
            3 => bitDepth is 1 or 2 or 4 or 8,
            4 or 6 => bitDepth is 8 or 16,
            _ => false
        };
        if (!validDepth)
        {
            throw new InvalidDataException(
                "unsigned screenshot PNG bit depth drifted");
        }
        long rowBytes = checked(((long)width * channels * bitDepth + 7) / 8);
        long decodedSize = checked((rowBytes + 1) * height);
        if (decodedSize > 256L * 1024 * 1024 || decodedSize > int.MaxValue)
        {
            throw new InvalidDataException(
                "unsigned screenshot PNG decoded size is unbounded");
        }
        compressed.Position = 0;
        using var inflater = new System.IO.Compression.ZLibStream(
            compressed,
            System.IO.Compression.CompressionMode.Decompress,
            leaveOpen: false);
        byte[] decoded = new byte[(int)decodedSize];
        int total = 0;
        while (total < decoded.Length)
        {
            int read = inflater.Read(decoded, total, decoded.Length - total);
            if (read == 0)
            {
                break;
            }
            total += read;
        }
        if (total != decoded.Length
            || inflater.ReadByte() != -1
            || Enumerable.Range(0, height).Any(
                row => decoded[checked(row * (int)(rowBytes + 1))] > 4))
        {
            throw new InvalidDataException(
                "unsigned screenshot PNG decoded scanlines drifted");
        }
        return (width, height);
    }

    private static uint ReadBigEndianUInt32(ReadOnlySpan<byte> value)
        => (uint)value[0] << 24
           | (uint)value[1] << 16
           | (uint)value[2] << 8
           | value[3];

    private static uint ComputePngCrc(
        ReadOnlySpan<byte> type,
        ReadOnlySpan<byte> data)
    {
        uint crc = uint.MaxValue;
        foreach (byte value in type)
        {
            crc = UpdatePngCrc(crc, value);
        }
        foreach (byte value in data)
        {
            crc = UpdatePngCrc(crc, value);
        }
        return ~crc;
    }

    private static uint UpdatePngCrc(uint crc, byte value)
    {
        crc ^= value;
        for (int bit = 0; bit < 8; bit++)
        {
            crc = (crc & 1) != 0
                ? 0xedb88320U ^ crc >> 1
                : crc >> 1;
        }
        return crc;
    }

    private static void ValidateUnsignedNativeHost(JsonElement native, string label)
    {
        if (!ExactPropertySet(
                native,
                new HashSet<string>(
                    [
                        "contractName",
                        "evidenceSource",
                        "hostPlatform",
                        "isNativeWindows",
                        "runner",
                        "status"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException($"{label} native host property set drifted");
        }
        RequireExactString(
            native,
            "contractName",
            "chummer6-ui.native_windows_host_evidence");
        RequireExactString(native, "evidenceSource", "GitHub-hosted windows-latest");
        RequireExactString(native, "hostPlatform", "windows");
        RequireBoolean(native, "isNativeWindows", expected: true);
        RequireExactString(native, "runner", "pwsh");
        RequireExactString(native, "status", "verified");
    }

    private static void ValidateUnsignedCaptureNativeEvidence(
        JsonElement native,
        JsonElement capture,
        JsonElement captureCandidate,
        JsonElement captureSource,
        IReadOnlyDictionary<string, CandidateEvidenceDocument> documents,
        IReadOnlyDictionary<string, ReleaseUploadCandidateInventoryRow> finalizedByPath,
        IReadOnlyList<CandidateScreenshotBinding> captureScreenshots,
        DateTimeOffset now)
    {
        if (!ExactPropertySet(
                native,
                new HashSet<string>(
                    [
                        "authenticodeVerification",
                        "head",
                        "payloadHttpLog",
                        "screenshots",
                        "startupLog",
                        "startupVisual"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned capture native evidence property set drifted");
        }
        if (!JsonSemanticEquals(
                RequireObject(native, "authenticodeVerification"),
                RequireObject(capture, "authenticodeVerification")))
        {
            throw new InvalidDataException(
                "unsigned capture native Authenticode binding drifted");
        }
        JsonElement heads = RequireArray(capture, "heads");
        if (heads.GetArrayLength() != 1
            || !JsonSemanticEquals(
                RequireObject(native, "head"),
                heads[0]))
        {
            throw new InvalidDataException(
                "unsigned capture native head binding drifted");
        }
        JsonElement startupLog = RequireObject(native, "startupLog");
        ValidateEvidenceByteReference(
            startupLog,
            documents,
            "unsigned capture startup log");
        RequireExactString(
            startupLog,
            "path",
            "startup-smoke/startup-smoke-avalonia-win-x64.log");
        JsonElement payloadHttpLog = RequireObject(native, "payloadHttpLog");
        ValidateEvidenceByteReference(
            payloadHttpLog,
            documents,
            "unsigned capture payload HTTP log");
        RequireExactString(
            payloadHttpLog,
            "path",
            "startup-smoke/startup-smoke-payload-http-avalonia-win-x64.log");

        const string startupScreenshotPath =
            "screenshots/windows-application-avalonia-win-x64-startup.png";
        string[] roles = ["startup", "progress", "completion"];
        JsonElement screenshots = RequireArray(native, "screenshots");
        if (screenshots.GetArrayLength() != roles.Length)
        {
            throw new InvalidDataException(
                "unsigned capture native screenshot scope drifted");
        }
        var nativeScreenshots = new List<CandidateScreenshotBinding>(roles.Length);
        int index = 0;
        foreach (JsonElement screenshot in screenshots.EnumerateArray())
        {
            if (!ExactPropertySet(
                    screenshot,
                    new HashSet<string>(
                        ["height", "path", "role", "sha256", "width"],
                        StringComparer.Ordinal)))
            {
                throw new InvalidDataException(
                    "unsigned capture native screenshot property set drifted");
            }
            string role = roles[index++];
            RequireExactString(screenshot, "role", role);
            string expectedPath = string.Equals(role, "startup", StringComparison.Ordinal)
                ? startupScreenshotPath
                : $"screenshots/windows-installer-avalonia-win-x64-{role}.png";
            RequireExactString(screenshot, "path", expectedPath);
            string digest = RequireSha256(screenshot, "sha256");
            if (RequirePositiveInt32(screenshot, "width") is < 320 or > 16384
                || RequirePositiveInt32(screenshot, "height") is < 200 or > 16384
                || !finalizedByPath.TryGetValue(
                    expectedPath,
                    out ReleaseUploadCandidateInventoryRow? row)
                || row.SizeBytes < 1
                || !string.Equals(row.Sha256, digest, StringComparison.Ordinal))
            {
                throw new InvalidDataException(
                    "unsigned capture native screenshot bytes drifted");
            }
            nativeScreenshots.Add(
                new CandidateScreenshotBinding(role, expectedPath, digest));
        }
        if (!nativeScreenshots.Skip(1).SequenceEqual(captureScreenshots)
            || nativeScreenshots.Select(static row => row.Sha256).Distinct().Count()
               != nativeScreenshots.Count)
        {
            throw new InvalidDataException(
                "unsigned capture screenshot sets drifted");
        }

        const string startupReceiptPath =
            "startup-visual/windows-application-avalonia-win-x64-startup.receipt.json";
        JsonElement startupReceipt = documents[startupReceiptPath].Root;
        ValidateUnsignedStartupVisualReceipt(
            startupReceipt,
            captureCandidate,
            captureSource,
            finalizedByPath,
            now);
        JsonElement startupVisual = RequireObject(native, "startupVisual");
        if (!ExactPropertySet(
                startupVisual,
                new HashSet<string>(
                    ["installedExecutable", "receipt", "screenshot"],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned startup visual binding property set drifted");
        }
        ValidateEvidenceByteReference(
            RequireObject(startupVisual, "receipt"),
            documents,
            "unsigned startup visual receipt");
        RequireExactString(
            RequireObject(startupVisual, "receipt"),
            "path",
            startupReceiptPath);
        if (!JsonSemanticEquals(
                RequireObject(startupVisual, "installedExecutable"),
                RequireObject(startupReceipt, "installedExecutable"))
            || !JsonSemanticEquals(
                RequireObject(startupVisual, "screenshot"),
                RequireObject(startupReceipt, "startupScreenshot")))
        {
            throw new InvalidDataException(
                "unsigned startup visual receipt projection drifted");
        }
    }

    private static void ValidateUnsignedStartupVisualReceipt(
        JsonElement receipt,
        JsonElement captureCandidate,
        JsonElement captureSource,
        IReadOnlyDictionary<string, ReleaseUploadCandidateInventoryRow> finalizedByPath,
        DateTimeOffset now)
    {
        if (!ExactPropertySet(
                receipt,
                new HashSet<string>(
                    [
                        "candidate",
                        "contractName",
                        "contractVersion",
                        "generatedAtUtc",
                        "installedExecutable",
                        "nativeHostEvidence",
                        "source",
                        "startupScreenshot",
                        "status"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned startup visual receipt property set drifted");
        }
        RequireExactString(
            receipt,
            "contractName",
            "chummer6-ui.unsigned-preview-windows-startup-visual");
        RequireExactInt32(receipt, "contractVersion", 1);
        RequireExactString(receipt, "status", "captured");
        _ = RequireFreshUtcTimestamp(receipt, "generatedAtUtc", now);
        if (!JsonSemanticEquals(RequireObject(receipt, "source"), captureSource))
        {
            throw new InvalidDataException(
                "unsigned startup visual source binding drifted");
        }
        JsonElement receiptCandidate = RequireObject(receipt, "candidate");
        if (!ExactPropertySet(
                receiptCandidate,
                new HashSet<string>(
                    ["installer", "payload", "release", "signature", "sourceSha"],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned startup visual candidate property set drifted");
        }
        foreach (string property in new[]
                 {
                     "installer",
                     "payload",
                     "release",
                     "signature"
                 })
        {
            if (!JsonSemanticEquals(
                    RequireObject(receiptCandidate, property),
                    RequireObject(captureCandidate, property)))
            {
                throw new InvalidDataException(
                    "unsigned startup visual candidate binding drifted");
            }
        }
        RequireExactString(
            receiptCandidate,
            "sourceSha",
            RequireString(captureCandidate, "sourceSha"));
        ValidateUnsignedNativeHost(
            RequireObject(receipt, "nativeHostEvidence"),
            "unsigned startup visual receipt");

        JsonElement executable = RequireObject(receipt, "installedExecutable");
        if (!ExactPropertySet(
                executable,
                new HashSet<string>(
                    ["fileName", "payloadEntry", "sha256", "sizeBytes"],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned startup executable property set drifted");
        }
        RequireExactString(executable, "fileName", "Chummer.Avalonia.exe");
        if (!IsCanonicalRelativePath(RequireString(executable, "payloadEntry")))
        {
            throw new InvalidDataException(
                "unsigned startup executable payload entry drifted");
        }
        _ = RequireSha256(executable, "sha256");
        _ = RequirePositiveInt64(executable, "sizeBytes");

        JsonElement screenshot = RequireObject(receipt, "startupScreenshot");
        if (!ExactPropertySet(
                screenshot,
                new HashSet<string>(
                    ["height", "path", "sha256", "width"],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned startup screenshot property set drifted");
        }
        const string path =
            "screenshots/windows-application-avalonia-win-x64-startup.png";
        RequireExactString(screenshot, "path", path);
        string digest = RequireSha256(screenshot, "sha256");
        if (RequirePositiveInt32(screenshot, "width") is < 320 or > 16384
            || RequirePositiveInt32(screenshot, "height") is < 200 or > 16384
            || !finalizedByPath.TryGetValue(
                path,
                out ReleaseUploadCandidateInventoryRow? row)
            || row.SizeBytes < 1
            || !string.Equals(row.Sha256, digest, StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "unsigned startup screenshot bytes drifted");
        }
    }

    private static void ValidateUnsignedCandidateExportReceipt(
        JsonElement export,
        JsonElement captureCandidate,
        JsonElement contentInventory,
        IReadOnlyList<ReleaseUploadCandidateInventoryRow> contentRows,
        CandidateWindowsScope scope)
    {
        if (!ExactPropertySet(
                export,
                new HashSet<string>(
                    [
                        "compositionRequest",
                        "contractName",
                        "contractVersion",
                        "crossRunBitReproducible",
                        "deployAuthorized",
                        "exportedContent",
                        "githubArtifactTransport",
                        "inventory",
                        "platformScope",
                        "publicationAuthorized",
                        "release",
                        "runnerNonce",
                        "signature",
                        "source",
                        "status",
                        "uiUploadAuthorized",
                        "uploadAuthorized"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned candidate export receipt property set drifted");
        }
        RequireExactString(
            export,
            "contractName",
            "chummer6-ui.preview-nightly-unsigned-candidate-export");
        RequireExactInt32(export, "contractVersion", 1);
        RequireExactString(export, "status", "exported");
        RequireBoolean(export, "crossRunBitReproducible", expected: false);
        RequireExactString(
            export,
            "githubArtifactTransport",
            "ephemeral_candidate_only");
        RequireExactString(export, "platformScope", "windows_only");
        RequireNoUnsignedPublicationAuthority(
            export,
            "unsigned candidate export receipt");
        string runnerNonce = RequireString(export, "runnerNonce");
        if (!UnsignedExportRunnerNoncePattern.IsMatch(runnerNonce))
        {
            throw new InvalidDataException(
                "unsigned candidate export runner nonce drifted");
        }
        JsonElement release = RequireObject(export, "release");
        if (!ExactPropertySet(
                release,
                new HashSet<string>(["channel", "version"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned candidate export release binding drifted");
        }
        RequireExactString(release, "channel", "preview");
        RequireExactString(release, "version", scope.Version);
        if (!JsonSemanticEquals(
                release,
                RequireObject(captureCandidate, "release"))
            || !JsonSemanticEquals(
                RequireObject(export, "signature"),
                RequireObject(captureCandidate, "signature"))
            || !JsonSemanticEquals(
                RequireObject(export, "source"),
                RequireObject(captureCandidate, "source"))
            || !JsonSemanticEquals(
                RequireObject(export, "inventory"),
                RequireObject(captureCandidate, "contentInventory"))
            || !JsonSemanticEquals(
                RequireObject(export, "compositionRequest"),
                RequireObject(captureCandidate, "compositionRequest")))
        {
            throw new InvalidDataException(
                "unsigned candidate export authority binding drifted");
        }

        JsonElement exportedContent = RequireArray(export, "exportedContent");
        JsonElement inventoryFiles = RequireArray(contentInventory, "files");
        if (!JsonSemanticEquals(exportedContent, inventoryFiles)
            || exportedContent.GetArrayLength() != contentRows.Count)
        {
            throw new InvalidDataException(
                "unsigned candidate exported content bytes drifted");
        }
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

    private static void ValidateCandidateContentInventoryHeader(
        JsonElement inventory,
        CandidateWindowsScope scope,
        ReleaseUploadCandidateIdentity candidate,
        bool allowUnsigned,
        string? expectedUnsignedProducerSourceSha = null)
    {
        if (!allowUnsigned)
        {
            RequireExactString(
                inventory,
                "contractName",
                "chummer6-ui.preview-nightly-candidate-content-inventory");
            RequireExactInt32(inventory, "contractVersion", 2);
            JsonElement release = RequireObject(inventory, "release");
            RequireExactString(release, "channel", scope.Channel);
            RequireExactString(release, "version", scope.Version);
            JsonElement manifest = RequireObject(inventory, "manifest");
            RequireExactString(
                manifest,
                "path",
                "RELEASE_CHANNEL.generated.json");
            RequireExactString(
                manifest,
                "sha256",
                candidate.CanonicalManifestSha256);
            return;
        }

        if (!ExactPropertySet(
                inventory,
                new HashSet<string>(
                    [
                        "contractName",
                        "contractVersion",
                        "crossRunBitReproducible",
                        "files",
                        "platformScope",
                        "release",
                        "signature",
                        "sourceSha"
                    ],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned candidate content inventory property set drifted");
        }
        RequireExactString(
            inventory,
            "contractName",
            "chummer6-ui.preview-nightly-unsigned-candidate-content-inventory");
        RequireExactInt32(inventory, "contractVersion", 1);
        RequireBoolean(inventory, "crossRunBitReproducible", expected: false);
        RequireExactString(inventory, "platformScope", "windows_only");
        string sourceSha = RequireString(inventory, "sourceSha");
        if (!CommitPattern.IsMatch(sourceSha)
            || expectedUnsignedProducerSourceSha is not null
                && !string.Equals(
                    sourceSha,
                    expectedUnsignedProducerSourceSha,
                    StringComparison.Ordinal))
        {
            throw new InvalidDataException(
                "unsigned candidate content source revision drifted");
        }
        JsonElement unsignedRelease = RequireObject(inventory, "release");
        if (!ExactPropertySet(
                unsignedRelease,
                new HashSet<string>(["channel", "version"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned candidate content release binding drifted");
        }
        RequireExactString(unsignedRelease, "channel", "preview");
        RequireExactString(unsignedRelease, "version", scope.Version);
        JsonElement signature = RequireObject(inventory, "signature");
        if (!ExactPropertySet(
                signature,
                new HashSet<string>(["policy", "required", "status"], StringComparer.Ordinal)))
        {
            throw new InvalidDataException(
                "unsigned candidate content signature policy drifted");
        }
        RequireExactString(signature, "status", "unsigned");
        RequireBoolean(signature, "required", expected: false);
        RequireExactString(signature, "policy", "preview_policy");
    }

    private static void ValidateEvidenceSource(
        JsonElement source,
        string label,
        string workflow,
        bool captureSource,
        bool allowUnsigned)
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
        Regex actorPattern = captureSource
            ? GitHubLoginPattern
            : ReviewerPattern;
        if (!actorPattern.IsMatch(actor))
        {
            throw new InvalidDataException($"{label} actor drifted");
        }
        string artifactStem = allowUnsigned
            ? "unsigned-windows-preview-native-evidence"
            : "windows-native-evidence";
        string expectedArtifactName = captureSource
            ? $"{artifactStem}-{runId}-{runAttempt}"
            : $"{artifactStem}-finalized-{runId}-{runAttempt}";
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

    private static void RequirePassedUnsignedNativeConfirmations(
        JsonElement confirmations,
        string label)
    {
        string[] requiredConfirmations =
        [
            "clipping",
            "completion",
            "contrast",
            "progress",
            "readability",
            "startup"
        ];
        if (!ExactPropertySet(
                confirmations,
                requiredConfirmations.ToHashSet(StringComparer.Ordinal)))
        {
            throw new InvalidDataException($"{label} confirmation scope drifted");
        }
        foreach (string confirmation in requiredConfirmations)
        {
            RequireExactString(confirmations, confirmation, "passed");
        }
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
        string expectedPath,
        string encodedProperty = "base64")
    {
        if (!ExactPropertySet(
                entry,
                new HashSet<string>(
                    ["path", "sha256", "sizeBytes", encodedProperty],
                    StringComparer.Ordinal)))
        {
            throw new InvalidDataException($"{label} custody binding drifted");
        }
        RequireExactString(entry, "path", expectedPath);
        string sha256 = RequireSha256(entry, "sha256");
        long size = RequireNonNegativeInt64(entry, "sizeBytes");
        string encoded = RequireString(entry, encodedProperty);
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

    private static string RequireCanonicalAbsolutePosixPath(
        JsonElement parent,
        string property,
        string label)
    {
        string value = RequireString(parent, property);
        if (value.Length < 2
            || !value.StartsWith("/", StringComparison.Ordinal)
            || value.EndsWith("/", StringComparison.Ordinal)
            || value.Contains("\\", StringComparison.Ordinal)
            || value.Any(static character => character < ' ' || character == '\u007f')
            || value.Split('/').Skip(1).Any(static segment =>
                segment.Length == 0 || segment is "." or ".."))
        {
            throw new InvalidDataException($"{label} is not a canonical absolute path");
        }
        return value;
    }

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
        private readonly JsonDocument? _document;

        public CandidateEvidenceDocument(
            JsonDocument? document,
            byte[] bytes,
            string sha256,
            long sizeBytes)
        {
            _document = document;
            Bytes = bytes;
            Sha256 = sha256;
            SizeBytes = sizeBytes;
        }

        public JsonElement Root => _document?.RootElement
            ?? throw new InvalidDataException(
                "candidate native-Windows binary evidence was used as JSON");
        public byte[] Bytes { get; }
        public string Sha256 { get; }
        public long SizeBytes { get; }

        public void Dispose() => _document?.Dispose();
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
