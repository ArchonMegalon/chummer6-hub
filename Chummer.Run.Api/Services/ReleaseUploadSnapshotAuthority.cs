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
        if (!ExactPropertySet(
                root,
                new HashSet<string>(
                    [
                        "contractName",
                        "contractVersion",
                        "status",
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
        RequireExactInt32(root, "contractVersion", 1);
        RequireExactString(root, "status", "candidate_import_ready");
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
                        "inventory",
                        "nativeWindowsFinalizedEvidence"
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
                    StringComparison.Ordinal)))
        {
            throw new InvalidDataException("candidate upload inventory summary drifted");
        }

        using JsonDocument canonicalDocument = ParseStrictObject(
            canonicalManifest,
            "candidate canonical release manifest");
        ValidateCandidateNativeEvidence(
            RequireObject(custody, "nativeWindowsFinalizedEvidence"),
            canonicalDocument.RootElement,
            candidate,
            inventory,
            now);

        return new ReleaseUploadCandidateAuthority(
            snapshotId,
            snapshotSha256,
            authoritySha256,
            expiresAt,
            candidate,
            canonicalManifest,
            inventory);
    }

    private static void ValidateCandidateNativeEvidence(
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
            RequireExactInt32(provenance, "contractVersion", 1);
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
            string[] expectedContentPaths =
            [
                "RELEASE_CHANNEL.generated.json",
                .. scope.Heads.SelectMany(head => new[]
                {
                    scope.Artifacts[head].Installer.Path,
                    scope.Artifacts[head].Payload.Path
                }).Order(StringComparer.Ordinal)
            ];
            if (!provenanceRows.Select(static row => row.Path).SequenceEqual(expectedContentPaths)
                || !JsonSemanticEquals(
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
            if (provenanceRows.Any(row =>
                    !candidateByPath.TryGetValue(row.Path, out ReleaseUploadCandidateInventoryRow? exact)
                    || exact != row))
            {
                throw new InvalidDataException("candidate native-Windows content bytes drifted");
            }
            if (!candidateByPath.TryGetValue(
                    CandidateUploadContentInventoryFileName,
                    out ReleaseUploadCandidateInventoryRow? uploadedInventory)
                || uploadedInventory != new ReleaseUploadCandidateInventoryRow(
                    CandidateUploadContentInventoryFileName,
                    provenanceDocument.SizeBytes,
                    provenanceDocument.Sha256))
            {
                throw new InvalidDataException(
                    "candidate uploaded content inventory differs from native-Windows provenance");
            }

            CandidateEvidenceDocument captureDocument = documents[CaptureFileName];
            JsonElement capture = captureDocument.Root;
            RequireExactString(
                capture,
                "contractName",
                "chummer6-ui.preview-nightly-native-windows-capture");
            RequireExactInt32(capture, "contractVersion", 1);
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
                candidate.CanonicalManifestSha256,
                summaryCaptureAt);
            IReadOnlyDictionary<string, IReadOnlyList<CandidateScreenshotBinding>>
                captureScreenshots = ValidateCaptureHeads(
                RequireArray(capture, "heads"),
                scope,
                finalizedByPath);

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
            RequireExactInt32(captureInventory, "contractVersion", 1);
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
            string[] expectedCapturePaths =
            [
                CaptureFileName,
                CandidateProvenanceInventoryFileName,
                CandidateProvenanceExportFileName,
                .. scope.Heads.SelectMany(head => new[]
                {
                    $"startup-smoke/startup-smoke-{head}-{WindowsRid}.receipt.json",
                    $"startup-smoke/windows-installer-progress-{head}-{WindowsRid}.log",
                    $"screenshots/windows-installer-{head}-{WindowsRid}-progress.png",
                    $"screenshots/windows-installer-{head}-{WindowsRid}-completion.png"
                })
            ];
            Array.Sort(expectedCapturePaths, StringComparer.Ordinal);
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
            RequireExactString(
                finalization,
                "contractName",
                "chummer6-ui.preview-nightly-native-windows-finalization");
            RequireExactInt32(finalization, "contractVersion", 1);
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
                FinalizationFileName
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
            CandidateEvidenceDocument exportDocument =
                documents[CandidateProvenanceExportFileName];
            if (!candidateByPath.TryGetValue(
                    CandidateUploadExportFileName,
                    out ReleaseUploadCandidateInventoryRow? uploadedExport)
                || uploadedExport != new ReleaseUploadCandidateInventoryRow(
                    CandidateUploadExportFileName,
                    exportDocument.SizeBytes,
                    exportDocument.Sha256))
            {
                throw new InvalidDataException(
                    "candidate uploaded export receipt differs from native-Windows provenance");
            }
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
        var windowsArtifacts = new List<JsonElement>();
        foreach (JsonElement artifact in artifactsElement.EnumerateArray())
        {
            if (artifact.ValueKind != JsonValueKind.Object
                || !HasExactString(artifact, "platform", "windows"))
            {
                continue;
            }
            if (!artifact.TryGetProperty("head", out JsonElement artifactHead)
                || artifactHead.ValueKind != JsonValueKind.String
                || artifactHead.GetString() is not { } head
                || !headSet.Contains(head))
            {
                throw new InvalidDataException(
                    "candidate release manifest contains a Windows artifact outside "
                    + "requiredDesktopHeads");
            }
            if (!HasExactString(artifact, "rid", WindowsRid)
                || !HasExactString(artifact, "kind", "installer"))
            {
                throw new InvalidDataException(
                    "candidate release manifest contains a Windows artifact outside "
                    + "the exact required desktop tuple scope");
            }
            windowsArtifacts.Add(artifact);
        }
        var candidateByPath = candidateInventory.ToDictionary(static row => row.Path, StringComparer.Ordinal);
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
        var expectedFilePaths = artifacts.Values
            .SelectMany(static value => new[] { value.Installer.Path, value.Payload.Path })
            .ToHashSet(StringComparer.Ordinal);
        var expectedCandidatePaths = expectedFilePaths
            .Append("RELEASE_CHANNEL.generated.json")
            .Append(CandidateUploadContentInventoryFileName)
            .Append(CandidateUploadExportFileName)
            .ToHashSet(StringComparer.Ordinal);
        var actualCandidatePaths = candidateInventory
            .Select(static row => row.Path)
            .ToHashSet(StringComparer.Ordinal);
        if (!actualCandidatePaths.SetEquals(expectedCandidatePaths))
        {
            throw new InvalidDataException(
                "candidate upload inventory differs from the exact Avalonia UI export tree");
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
        IReadOnlyDictionary<string, ReleaseUploadCandidateInventoryRow> finalizedByPath)
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
                            "screenshots"
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
                "handoffSha256",
                "manifestPath",
                "manifestSha256",
                "ref",
                "repository",
                "runAttempt",
                "runId",
                "sha",
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
                     "handoffSha256",
                     "manifestSha256"
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
        return captureCandidate;
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
                "release",
                "source",
                "status"
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
        RequireExactInt32(export, "contractVersion", 1);
        RequireExactString(export, "status", "exported");

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
