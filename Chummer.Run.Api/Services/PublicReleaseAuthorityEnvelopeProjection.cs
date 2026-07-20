using System.Security.Cryptography;
using System.Globalization;
using System.Text.Json;
using Chummer.Run.Contracts.PublicSurface;

namespace Chummer.Run.Api.Services;

/// <summary>
/// Projects the exact Registry authority envelope that was copied into, and sealed by,
/// one immutable Hub release-shelf generation. Any partial or contradictory envelope is
/// rejected rather than being interpreted as legacy release truth.
/// </summary>
internal static class PublicReleaseAuthorityEnvelopeProjection
{
    internal const string CurrentInventoryPath = "release-evidence/CURRENT.json";
    internal const string SnapshotInventoryPath = "release-evidence/SNAPSHOT.json";
    internal const string AuthorityContract = "chummer.release-authority-snapshot/v2";
    internal const string RegistryRepository = "ArchonMegalon/chummer6-hub-registry";
    internal const string ManifestPath = "RELEASE_CHANNEL.json";
    internal const string ReleaseDecisionPath = "RELEASE_DECISION.json";
    internal const string PreviewDecisionContract = "chummer.preview-release-decision/v1";
    internal const string StableDecisionContract = "chummer.final_gold_graph";
    internal const int StableDecisionContractVersion = 2;

    private const int MaximumCurrentBytes = 64 * 1024;
    private const int MaximumSnapshotBytes = 4 * 1024 * 1024;
    private const int MaximumDecisionBytes = 4 * 1024 * 1024;
    private const int MaximumTokenLength = 128;
    private const int MaximumSupportOwnerLength = 256;
    private const int MaximumActionLength = 512;
    private const int MaximumActionCount = 32;
    private const int MaximumPlatformCount = 16;
    private const int MaximumArtifactCount = 256;
    private const int MaximumKnownIssueSummaryLength = 512;
    private const int MaximumUrlLength = 2048;

    private static readonly HashSet<string> AllowedDecisionStatuses =
        ["review_required", "preview_ready", "stable_ready"];
    private static readonly HashSet<string> AllowedAccessClasses =
        ["open_public", "account_recommended", "account_required"];
    private static readonly HashSet<string> SentinelTokens =
        [PublicReleaseTruthProjectionDto.Unknown, PublicReleaseTruthProjectionDto.Missing, PublicReleaseTruthProjectionDto.Invalid];
    private static readonly HashSet<string> CurrentFields =
        ["releaseVersion", "snapshotSha256", "decisionSha256", "status"];
    private static readonly HashSet<string> SnapshotFields =
    [
        "authorityContract", "releaseVersion", "channel", "status", "rolloutState",
        "supportabilityState", "availablePlatforms", "primaryHeadByPlatform",
        "artifactCount", "downloadAccessPosture", "knownIssueSummary", "manifestSha256",
        "registryRepository", "registryCommit", "releaseDecisionStatus", "releaseDecisionSha256", "supportOwner",
        "nextActions", "artifacts", "manifestPath", "releaseDecisionPath"
    ];
    private static readonly HashSet<string> ArtifactFields =
    [
        "artifactId", "head", "platform", "rid", "arch", "kind", "downloadUrl", "sha256",
        "sizeBytes", "compatibilityState", "promotionState", "publicationScope", "revokeState",
        "publicInstallRoute", "installAccessClass"
    ];
    private static readonly HashSet<string> PreviewDecisionFields =
    [
        "contractName", "generatedAt", "status", "releaseDecisionStatus", "verdict",
        "releaseVersion", "channel", "platforms", "primaryHeadByPlatform",
        "fallbackHeadsByPlatform", "artifactAccessClass", "supportOwner", "nextActions",
        "registryCommit", "manifestSha256", "authoritySnapshotSha256",
        "candidateDecisionStatus", "candidateDecisionSha256", "manifestGeneratedAt",
        "scorecardSha256", "convergenceSha256", "blockingFindings"
    ];
    private static readonly HashSet<string> StableDecisionFields =
    [
        "contract_name", "contract_version", "product", "generated_at_utc", "status",
        "verdict", "releaseDecisionStatus", "releaseVersion", "spine_ref", "design_ref",
        "live_release", "release_authority", "required_loops", "required_surfaces",
        "required_truth_domains", "required_horizon_lanes", "required_feature_lanes",
        "projection_adapter_policy", "proof_inputs", "completion_audit",
        "blocking_findings", "advisory_findings", "principle"
    ];
    private static readonly HashSet<string> StableLiveReleaseFields =
    [
        "version", "channel", "status", "rollout_state", "supportability_state",
        "available_platforms", "primary_head_by_platform", "artifact_count",
        "download_access_posture", "known_issue_summary", "manifest_sha256",
        "registry_commit", "release_decision_status", "release_decision_sha256",
        "status_endpoint", "release_manifest_endpoint"
    ];
    private static readonly HashSet<string> StableReleaseAuthorityFields =
    [
        "contract", "snapshot_path", "snapshot_sha256", "manifest_sha256",
        "registry_commit", "release_decision_status", "release_decision_sha256"
    ];
    private static readonly HashSet<string> StableProjectionAdapterPolicyFields =
        ["status", "adapters_are_projection_only", "adapters"];
    private static readonly HashSet<string> StableCompletionAuditFields =
        ["status", "requirement_count", "passed_count", "failed_count", "requirements"];
    private static readonly HashSet<string> StableCompletionRequirementFields =
        ["id", "status", "proof_kinds", "missing_or_failed_proof_kinds"];
    private static readonly HashSet<string> DecisionFindingFields =
        ["id", "severity", "summary"];
    private static readonly string[] StableRequiredLoops =
        ["build_correctly", "run_reliably", "remember_campaign", "explain_everything", "publish_projections"];
    private static readonly string[] StableRequiredSurfaces =
        ["runner_workbench", "gm_cockpit", "campaign_memory", "living_city", "publishing_studio", "admin_proof"];
    private static readonly string[] StableRequiredTruthDomains =
        ["rules_truth", "character_truth", "campaign_truth", "world_state_truth", "media_projection_truth"];
    private static readonly string[] StableRequiredHorizonLanes =
        ["alice", "karma-forge", "jackpoint", "runsite", "runbook-press", "table-pulse", "black-ledger"];
    private static readonly string[] StableRequiredFeatureLanes =
        ["nexus-pan", "run-control", "edition-studio", "community-hub", "quicksilver", "ghostwire", "local-co-processor"];
    private static readonly string[] StableProjectionAdapters = ["rafter", "pixefy", "magicfit"];
    private static readonly HashSet<string> StableProofKinds =
    [
        "design_spine", "horizon_registry", "feature_registry", "release_policy",
        "rule_authority_human_boundaries", "parity_registry", "campaign_operability_scorecard",
        "journey_gates", "fleet_flagship_readiness", "operator_release_dashboard",
        "final_gold_janitor", "flagship_product_readiness_gate", "google_oauth_linking_proof",
        "public_edge_postdeploy_gate", "black_ledger_live_media_proof",
        "ui_localization_release_gate", "release_ready_matrix", "ea_release_critical_readiness",
        "registry_release_authority", "registry_stable_posture", "live_status",
        "live_release_manifest"
    ];
    private static readonly HashSet<string> StableBaseProofFields = ["kind", "path", "status"];
    private static readonly HashSet<string> StableParityProofFields = ["kind", "path", "status", "family_count"];
    private static readonly HashSet<string> StableCampaignProofFields =
    [
        "kind", "path", "status", "generated_at", "cell_count", "release_version",
        "snapshot_sha256", "manifest_sha256", "release_decision_sha256"
    ];
    private static readonly HashSet<string> StableJourneyProofFields = ["kind", "path", "status", "generated_at"];
    private static readonly HashSet<string> StableReceiptProofFields =
    [
        "kind", "path", "status", "generated_at", "release_version", "snapshot_sha256",
        "manifest_sha256", "release_decision_sha256"
    ];
    private static readonly HashSet<string> StableReleaseReadyProofFields =
    [
        "kind", "path", "status", "generated_at", "required_gate_count", "completed_gate_count",
        "release_version", "snapshot_sha256", "manifest_sha256", "release_decision_sha256"
    ];
    private static readonly HashSet<string> StableEaProofFields =
    [
        "kind", "path", "status", "generated_at", "required_component_keys",
        "optional_blocked_component_keys"
    ];
    private static readonly HashSet<string> StableRegistryAuthorityProofFields =
    [
        "kind", "path", "status", "snapshot_sha256", "manifest_sha256", "registry_commit",
        "release_decision_status", "release_decision_sha256"
    ];
    private static readonly HashSet<string> StableLiveManifestProofFields = ["kind", "path", "status", "generated_at"];
    private static readonly HashSet<string> StableReceiptProofKinds =
    [
        "fleet_flagship_readiness", "operator_release_dashboard", "final_gold_janitor",
        "flagship_product_readiness_gate", "google_oauth_linking_proof",
        "public_edge_postdeploy_gate", "black_ledger_live_media_proof",
        "ui_localization_release_gate"
    ];
    private static readonly HashSet<string> StableReleaseBoundProofKinds =
    [
        "campaign_operability_scorecard", "operator_release_dashboard", "final_gold_janitor",
        "flagship_product_readiness_gate", "public_edge_postdeploy_gate", "release_ready_matrix"
    ];
    private static readonly IReadOnlyDictionary<string, string[]> StableCompletionRequirements =
        new Dictionary<string, string[]>(StringComparer.Ordinal)
        {
            ["authoritative_design"] = ["design_spine", "horizon_registry", "feature_registry", "release_policy"],
            ["release_control"] = ["registry_release_authority", "registry_stable_posture", "release_ready_matrix", "final_gold_janitor", "flagship_product_readiness_gate"],
            ["journey_truth"] = ["journey_gates", "campaign_operability_scorecard"],
            ["legacy_and_adjacent_parity"] = ["parity_registry", "fleet_flagship_readiness"],
            ["security_and_privacy"] = ["release_ready_matrix", "google_oauth_linking_proof", "ea_release_critical_readiness"],
            ["localization"] = ["ui_localization_release_gate"],
            ["campaign_operability"] = ["campaign_operability_scorecard"],
            ["installer_and_update"] = ["release_ready_matrix", "registry_release_authority", "registry_stable_posture", "live_release_manifest"],
            ["support_and_closure"] = ["campaign_operability_scorecard", "operator_release_dashboard", "live_status"],
            ["provider_posture"] = ["ea_release_critical_readiness", "black_ledger_live_media_proof"],
            ["ui_quality_and_accessibility"] = ["campaign_operability_scorecard", "public_edge_postdeploy_gate", "ui_localization_release_gate"],
            ["live_runtime"] = ["public_edge_postdeploy_gate", "live_status", "live_release_manifest"]
        };
    private static readonly JsonDocumentOptions JsonOptions = new()
    {
        AllowTrailingCommas = false,
        CommentHandling = JsonCommentHandling.Disallow,
        MaxDepth = 32
    };

    internal static PublicReleaseTruthProjectionDto? TryProject(
        ReleaseShelfSnapshot shelf,
        PublicReleaseManifestDto manifest,
        string? immutableManifestSha256,
        ReadOnlyMemory<byte>? immutableManifestBytes,
        out string? authoritySnapshotSha256)
    {
        authoritySnapshotSha256 = null;
        ArgumentNullException.ThrowIfNull(shelf);
        ArgumentNullException.ThrowIfNull(manifest);
        if (shelf.IsLegacy)
        {
            return null;
        }

        bool hasCurrent = HasExactInventoryPath(shelf, CurrentInventoryPath);
        bool hasSnapshot = HasExactInventoryPath(shelf, SnapshotInventoryPath);
        RejectNoncanonicalInventoryPath(shelf, CurrentInventoryPath, hasCurrent);
        RejectNoncanonicalInventoryPath(shelf, SnapshotInventoryPath, hasSnapshot);
        if (!hasCurrent && !hasSnapshot)
        {
            return null;
        }

        if (!hasCurrent || !hasSnapshot)
        {
            throw Invalid("Registry authority evidence is incomplete in the release-shelf inventory.");
        }

        byte[] currentBytes = shelf.ReadVerifiedFileBytes(CurrentInventoryPath, MaximumCurrentBytes)
            ?? throw Invalid("Registry CURRENT.json no longer matches its release-shelf inventory binding.");
        byte[] snapshotBytes = shelf.ReadVerifiedFileBytes(SnapshotInventoryPath, MaximumSnapshotBytes)
            ?? throw Invalid("Registry SNAPSHOT.json no longer matches its release-shelf inventory binding.");
        string decisionInventoryPath = ResolveSiblingInventoryPath(
            SnapshotInventoryPath,
            ReadReleaseDecisionPath(snapshotBytes));
        bool hasDecision = HasExactInventoryPath(shelf, decisionInventoryPath);
        RejectNoncanonicalInventoryPath(shelf, decisionInventoryPath, hasDecision);
        if (!hasDecision)
        {
            throw Invalid("Registry authority evidence omits the decision sibling declared by SNAPSHOT.json.");
        }

        byte[] decisionBytes = shelf.ReadVerifiedFileBytes(decisionInventoryPath, MaximumDecisionBytes)
            ?? throw Invalid("Registry RELEASE_DECISION.json no longer matches its release-shelf inventory binding.");
        PublicReleaseTruthProjectionDto projection = Project(
            currentBytes,
            snapshotBytes,
            decisionBytes,
            manifest,
            immutableManifestSha256,
            immutableManifestBytes);
        authoritySnapshotSha256 = Convert.ToHexStringLower(SHA256.HashData(snapshotBytes));
        return projection;
    }

    internal static PublicReleaseTruthProjectionDto Project(
        ReadOnlyMemory<byte> currentBytes,
        ReadOnlyMemory<byte> snapshotBytes,
        ReadOnlyMemory<byte> decisionBytes,
        PublicReleaseManifestDto manifest,
        string? immutableManifestSha256,
        ReadOnlyMemory<byte>? immutableManifestBytes)
    {
        ArgumentNullException.ThrowIfNull(manifest);
        if (currentBytes.IsEmpty || currentBytes.Length > MaximumCurrentBytes)
        {
            throw Invalid("Registry CURRENT.json has an invalid byte length.");
        }

        if (snapshotBytes.IsEmpty || snapshotBytes.Length > MaximumSnapshotBytes)
        {
            throw Invalid("Registry SNAPSHOT.json has an invalid byte length.");
        }

        if (decisionBytes.IsEmpty || decisionBytes.Length > MaximumDecisionBytes)
        {
            throw Invalid("Registry RELEASE_DECISION.json has an invalid byte length.");
        }

        using JsonDocument currentDocument = ParseStrict(currentBytes, "Registry CURRENT.json");
        using JsonDocument snapshotDocument = ParseStrict(snapshotBytes, "Registry SNAPSHOT.json");
        using JsonDocument decisionDocument = ParseStrict(decisionBytes, "Registry RELEASE_DECISION.json");
        JsonElement current = currentDocument.RootElement;
        JsonElement snapshot = snapshotDocument.RootElement;
        JsonElement decision = decisionDocument.RootElement;
        RequireExactObject(current, CurrentFields, "Registry CURRENT.json");
        RequireExactObject(snapshot, SnapshotFields, "Registry SNAPSHOT.json");

        string currentReleaseVersion = RequirePortableIdentifier(
            current,
            "releaseVersion",
            "Registry CURRENT.json");
        string currentSnapshotSha256 = RequireSha256(
            current,
            "snapshotSha256",
            "Registry CURRENT.json");
        string currentDecisionSha256 = RequireSha256(
            current,
            "decisionSha256",
            "Registry CURRENT.json");
        string currentStatus = RequireDecisionStatus(current, "status", "Registry CURRENT.json");
        RequireDigestMatchesBytes(
            currentSnapshotSha256,
            snapshotBytes.Span,
            "Registry CURRENT.json snapshotSha256");

        string authorityContract = RequireString(snapshot, "authorityContract", MaximumTokenLength, "Registry SNAPSHOT.json");
        if (!string.Equals(authorityContract, AuthorityContract, StringComparison.Ordinal))
        {
            throw Invalid($"Registry SNAPSHOT.json authorityContract must be {AuthorityContract}.");
        }

        string releaseVersion = RequirePortableIdentifier(snapshot, "releaseVersion", "Registry SNAPSHOT.json");
        string channel = RequireCanonicalToken(snapshot, "channel", "Registry SNAPSHOT.json");
        string releaseStatus = RequireCanonicalToken(snapshot, "status", "Registry SNAPSHOT.json");
        string rolloutState = RequireCanonicalToken(snapshot, "rolloutState", "Registry SNAPSHOT.json");
        string supportabilityState = RequireCanonicalToken(snapshot, "supportabilityState", "Registry SNAPSHOT.json");
        string knownIssueSummary = RequireString(
            snapshot,
            "knownIssueSummary",
            MaximumKnownIssueSummaryLength,
            "Registry SNAPSHOT.json");
        string manifestSha256 = RequireSha256(snapshot, "manifestSha256", "Registry SNAPSHOT.json");
        string registryRepository = RequireString(
            snapshot,
            "registryRepository",
            MaximumSupportOwnerLength,
            "Registry SNAPSHOT.json");
        if (!string.Equals(registryRepository, RegistryRepository, StringComparison.Ordinal))
        {
            throw Invalid($"Registry SNAPSHOT.json registryRepository must be {RegistryRepository}.");
        }
        string registryCommit = RequireLowerHex(snapshot, "registryCommit", 40, "Registry SNAPSHOT.json");
        string releaseDecisionStatus = RequireDecisionStatus(
            snapshot,
            "releaseDecisionStatus",
            "Registry SNAPSHOT.json");
        string releaseDecisionSha256 = RequireSha256(
            snapshot,
            "releaseDecisionSha256",
            "Registry SNAPSHOT.json");
        RequireDigestMatchesBytes(
            releaseDecisionSha256,
            decisionBytes.Span,
            "Registry SNAPSHOT.json releaseDecisionSha256");
        string supportOwner = RequireString(snapshot, "supportOwner", MaximumSupportOwnerLength, "Registry SNAPSHOT.json");
        int nextActionCount = RequireNextActions(snapshot.GetProperty("nextActions"));
        if (releaseDecisionStatus == "review_required" && nextActionCount == 0)
        {
            throw Invalid("Registry SNAPSHOT.json review_required decisions must publish at least one next action.");
        }
        RequireFixedPath(snapshot, "manifestPath", ManifestPath);
        RequireFixedPath(snapshot, "releaseDecisionPath", ReleaseDecisionPath);

        if (!string.Equals(currentReleaseVersion, releaseVersion, StringComparison.Ordinal)
            || !string.Equals(currentStatus, releaseDecisionStatus, StringComparison.Ordinal)
            || !FixedTimeDigestEquals(currentDecisionSha256, releaseDecisionSha256))
        {
            throw Invalid("Registry CURRENT.json does not bind the same release decision as SNAPSHOT.json.");
        }

        string normalizedManifestDigest = PublicReleaseTruthProjectionService.NormalizeSha256(
            immutableManifestSha256);
        string verifiedManifestDigest = PublicReleaseTruthProjectionService.VerifyAuthorityManifestDigest(
            normalizedManifestDigest,
            immutableManifestBytes);
        if (!FixedTimeDigestEquals(manifestSha256, verifiedManifestDigest))
        {
            throw Invalid("Registry SNAPSHOT.json manifestSha256 does not bind the immutable Hub authority manifest bytes.");
        }

        if (!string.Equals(
                releaseVersion,
                PublicReleaseTruthProjectionService.NormalizeIdentifier(manifest.Version),
                StringComparison.Ordinal)
            || !string.Equals(channel, NormalizeExactToken(manifest.Channel), StringComparison.Ordinal)
            || !string.Equals(releaseStatus, NormalizeExactToken(manifest.Status), StringComparison.Ordinal)
            || !string.Equals(rolloutState, NormalizeExactToken(manifest.RolloutState), StringComparison.Ordinal)
            || !string.Equals(supportabilityState, NormalizeExactToken(manifest.SupportabilityState), StringComparison.Ordinal)
            || !string.Equals(knownIssueSummary, PublicReleaseTruthProjectionService.NormalizeSummary(manifest.KnownIssueSummary), StringComparison.Ordinal))
        {
            throw Invalid("Registry SNAPSHOT.json release fields contradict the final Hub release manifest projection.");
        }

        AuthorityArtifact[] authorityArtifacts = RequireAuthorityArtifacts(snapshot.GetProperty("artifacts"));
        int artifactCount = RequireNonnegativeInt(snapshot, "artifactCount", "Registry SNAPSHOT.json");
        if (artifactCount != authorityArtifacts.Length || artifactCount != manifest.Downloads.Count)
        {
            throw Invalid("Registry SNAPSHOT.json artifactCount contradicts its artifacts or the final Hub public shelf.");
        }

        CompareArtifactBindings(authorityArtifacts, manifest.Downloads);
        string[] availablePlatforms = RequireAvailablePlatforms(snapshot.GetProperty("availablePlatforms"));
        string[] derivedPlatforms = authorityArtifacts
            .Select(static artifact => artifact.Platform)
            .Distinct(StringComparer.Ordinal)
            .OrderBy(static platform => platform, StringComparer.Ordinal)
            .ToArray();
        if (!availablePlatforms.SequenceEqual(derivedPlatforms, StringComparer.Ordinal))
        {
            throw Invalid("Registry SNAPSHOT.json availablePlatforms does not equal the promoted artifact platform set.");
        }

        SortedDictionary<string, string> primaryHeads = RequirePrimaryHeads(
            snapshot.GetProperty("primaryHeadByPlatform"),
            availablePlatforms,
            authorityArtifacts);
        string downloadAccessPosture = RequireString(
            snapshot,
            "downloadAccessPosture",
            MaximumTokenLength,
            "Registry SNAPSHOT.json");
        string derivedPosture = DeriveAccessPosture(authorityArtifacts);
        if (!string.Equals(downloadAccessPosture, derivedPosture, StringComparison.Ordinal))
        {
            throw Invalid("Registry SNAPSHOT.json downloadAccessPosture contradicts the promoted artifacts.");
        }

        ValidateReleaseDecision(
            decision,
            releaseVersion,
            channel,
            releaseStatus,
            rolloutState,
            supportabilityState,
            availablePlatforms,
            primaryHeads,
            authorityArtifacts,
            artifactCount,
            downloadAccessPosture,
            knownIssueSummary,
            manifestSha256,
            registryCommit,
            releaseDecisionStatus,
            supportOwner);

        if (artifactCount == 0)
        {
            if (releaseDecisionStatus != "review_required"
                || downloadAccessPosture != "unavailable"
                || availablePlatforms.Length != 0
                || primaryHeads.Count != 0)
            {
                throw Invalid("An empty public shelf is valid only as review_required with unavailable access.");
            }
        }
        else if (releaseDecisionStatus is "preview_ready" or "stable_ready"
                 && downloadAccessPosture == "unavailable")
        {
            throw Invalid("A ready release decision cannot publish an unavailable non-empty shelf.");
        }

        return new PublicReleaseTruthProjectionDto(
            ContractName: PublicReleaseTruthProjectionDto.Schema,
            ReleaseVersion: releaseVersion,
            Channel: channel,
            ReleaseStatus: releaseStatus,
            RolloutState: rolloutState,
            SupportabilityState: supportabilityState,
            AvailablePlatforms: availablePlatforms,
            PrimaryHeadByPlatform: primaryHeads,
            ArtifactCount: artifactCount,
            DownloadAccessPosture: downloadAccessPosture,
            KnownIssueSummary: knownIssueSummary,
            ManifestSha256: manifestSha256,
            RegistryCommit: registryCommit,
            ReleaseDecisionStatus: releaseDecisionStatus,
            ReleaseDecisionSha256: releaseDecisionSha256);
    }

    private static JsonDocument ParseStrict(ReadOnlyMemory<byte> bytes, string label)
    {
        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(bytes, JsonOptions);
        }
        catch (JsonException error)
        {
            throw Invalid($"{label} is not strict JSON.", error);
        }

        try
        {
            RejectDuplicatePropertyNames(document.RootElement, label, 0);
            return document;
        }
        catch
        {
            document.Dispose();
            throw;
        }
    }

    private static string ReadReleaseDecisionPath(ReadOnlyMemory<byte> snapshotBytes)
    {
        using JsonDocument document = ParseStrict(snapshotBytes, "Registry SNAPSHOT.json");
        JsonElement snapshot = document.RootElement;
        RequireExactObject(snapshot, SnapshotFields, "Registry SNAPSHOT.json");
        string decisionPath = RequireString(
            snapshot,
            "releaseDecisionPath",
            MaximumTokenLength,
            "Registry SNAPSHOT.json");
        if (!string.Equals(decisionPath, ReleaseDecisionPath, StringComparison.Ordinal))
        {
            throw Invalid($"Registry SNAPSHOT.json releaseDecisionPath must be {ReleaseDecisionPath}.");
        }

        return decisionPath;
    }

    private static string ResolveSiblingInventoryPath(string snapshotInventoryPath, string siblingName)
    {
        if (Path.GetFileName(siblingName) != siblingName
            || siblingName.Contains('/')
            || siblingName.Contains('\\'))
        {
            throw Invalid("Registry SNAPSHOT.json releaseDecisionPath must name one sibling file.");
        }

        string? directory = Path.GetDirectoryName(snapshotInventoryPath)?.Replace('\\', '/');
        return string.IsNullOrEmpty(directory)
            ? siblingName
            : directory + "/" + siblingName;
    }

    private static void RejectDuplicatePropertyNames(JsonElement value, string label, int depth)
    {
        if (depth > JsonOptions.MaxDepth)
        {
            throw Invalid($"{label} exceeds the permitted JSON nesting depth.");
        }

        if (value.ValueKind == JsonValueKind.Object)
        {
            var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (JsonProperty property in value.EnumerateObject())
            {
                if (!names.Add(property.Name))
                {
                    throw Invalid($"{label} contains duplicate property '{property.Name}'.");
                }

                RejectDuplicatePropertyNames(property.Value, label, depth + 1);
            }
        }
        else if (value.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement item in value.EnumerateArray())
            {
                RejectDuplicatePropertyNames(item, label, depth + 1);
            }
        }
    }

    private static void ValidateReleaseDecision(
        JsonElement decision,
        string releaseVersion,
        string channel,
        string releaseStatus,
        string rolloutState,
        string supportabilityState,
        IReadOnlyList<string> availablePlatforms,
        IReadOnlyDictionary<string, string> primaryHeads,
        IReadOnlyList<AuthorityArtifact> artifacts,
        int artifactCount,
        string downloadAccessPosture,
        string knownIssueSummary,
        string manifestSha256,
        string registryCommit,
        string releaseDecisionStatus,
        string supportOwner)
    {
        if (decision.ValueKind != JsonValueKind.Object)
        {
            throw Invalid("Registry RELEASE_DECISION.json must be a JSON object.");
        }

        if (decision.TryGetProperty("contractName", out JsonElement previewContract))
        {
            ValidatePreviewDecision(
                decision,
                previewContract,
                releaseVersion,
                channel,
                availablePlatforms,
                primaryHeads,
                artifacts,
                artifactCount,
                downloadAccessPosture,
                manifestSha256,
                registryCommit,
                releaseDecisionStatus,
                supportOwner);
            return;
        }

        if (decision.TryGetProperty("contract_name", out JsonElement stableContract))
        {
            ValidateStableDecision(
                decision,
                stableContract,
                releaseVersion,
                channel,
                releaseStatus,
                rolloutState,
                supportabilityState,
                availablePlatforms,
                primaryHeads,
                artifacts,
                artifactCount,
                downloadAccessPosture,
                knownIssueSummary,
                manifestSha256,
                registryCommit,
                releaseDecisionStatus);
            return;
        }

        throw Invalid("Registry RELEASE_DECISION.json must use an accepted preview or stable decision contract.");
    }

    private static void ValidatePreviewDecision(
        JsonElement decision,
        JsonElement contract,
        string releaseVersion,
        string channel,
        IReadOnlyList<string> availablePlatforms,
        IReadOnlyDictionary<string, string> primaryHeads,
        IReadOnlyList<AuthorityArtifact> artifacts,
        int artifactCount,
        string downloadAccessPosture,
        string manifestSha256,
        string registryCommit,
        string releaseDecisionStatus,
        string supportOwner)
    {
        if (contract.ValueKind != JsonValueKind.String
            || !string.Equals(contract.GetString(), PreviewDecisionContract, StringComparison.Ordinal)
            || decision.TryGetProperty("contract_name", out _)
            || decision.TryGetProperty("contract_version", out _)
            || decision.TryGetProperty("release_authority", out _))
        {
            throw Invalid("Registry RELEASE_DECISION.json preview contract discriminator is invalid or ambiguous.");
        }
        RequireExactObject(decision, PreviewDecisionFields, "Registry RELEASE_DECISION.json preview decision");

        string decisionStatus = RequireDecisionString(decision, "releaseDecisionStatus");
        if (decisionStatus is not ("review_required" or "preview_ready")
            || !string.Equals(decisionStatus, releaseDecisionStatus, StringComparison.Ordinal))
        {
            throw Invalid("Registry RELEASE_DECISION.json preview status must be review_required or preview_ready and match SNAPSHOT.json.");
        }

        string verdict = RequireDecisionString(decision, "verdict");
        int blockingFindingCount = RequireDecisionFindings(
            decision,
            "blockingFindings",
            expectedSeverity: "release_truth",
            sequentialIdPrefix: "preview_");
        if (decisionStatus == "preview_ready")
        {
            if (!string.Equals(verdict, "PREVIEW_READY", StringComparison.Ordinal)
                || blockingFindingCount != 0)
            {
                throw Invalid("Registry RELEASE_DECISION.json preview-ready verdict must be PREVIEW_READY with no blocking findings.");
            }
            RequireDecisionUtcTimestamp(decision, "generatedAt");
            RequireDecisionUtcTimestamp(decision, "manifestGeneratedAt");
        }
        else if (!string.Equals(verdict, "PREVIEW_RELEASE_REVIEW_REQUIRED", StringComparison.Ordinal)
                 || blockingFindingCount == 0)
        {
            throw Invalid("Registry RELEASE_DECISION.json review verdict must be PREVIEW_RELEASE_REVIEW_REQUIRED with blocking findings.");
        }

        if (!string.Equals(RequireDecisionString(decision, "status"), decisionStatus, StringComparison.Ordinal)
            || !string.Equals(RequireDecisionString(decision, "releaseVersion"), releaseVersion, StringComparison.Ordinal)
            || !FixedTimeDigestEquals(RequireDecisionSha256(decision, "manifestSha256"), manifestSha256)
            || !string.Equals(RequireDecisionString(decision, "channel"), channel, StringComparison.Ordinal)
            || !string.Equals(RequireDecisionLowerHex(decision, "registryCommit", 40), registryCommit, StringComparison.Ordinal)
            || !string.Equals(RequireDecisionString(decision, "supportOwner"), supportOwner, StringComparison.Ordinal))
        {
            throw Invalid("Registry RELEASE_DECISION.json preview release, manifest, channel, registry, or support binding contradicts SNAPSHOT.json.");
        }

        string[] platforms = RequireDecisionStringArray(decision, "platforms", allowEmpty: decisionStatus == "review_required");
        SortedDictionary<string, string> heads = RequireDecisionHeadMap(decision, "primaryHeadByPlatform", platforms);
        if (!platforms.SequenceEqual(availablePlatforms, StringComparer.Ordinal)
            || !StringMapEquals(heads, primaryHeads))
        {
            throw Invalid("Registry RELEASE_DECISION.json preview platforms and primary heads must exactly match SNAPSHOT.json.");
        }

        IReadOnlyDictionary<string, string[]> fallbacks = RequireDecisionFallbackMap(
            decision,
            "fallbackHeadsByPlatform",
            platforms,
            heads);
        foreach (string platform in platforms)
        {
            string[] expectedFallbacks = artifacts
                .Where(artifact => string.Equals(artifact.Platform, platform, StringComparison.Ordinal)
                    && !string.Equals(artifact.Head, heads[platform], StringComparison.Ordinal))
                .Select(static artifact => artifact.Head)
                .Distinct(StringComparer.Ordinal)
                .OrderBy(static head => head, StringComparer.Ordinal)
                .ToArray();
            string[] actualFallbacks = fallbacks.TryGetValue(platform, out string[]? declaredFallbacks)
                ? declaredFallbacks
                : [];
            if (!actualFallbacks.SequenceEqual(expectedFallbacks, StringComparer.Ordinal))
            {
                throw Invalid("Registry RELEASE_DECISION.json preview fallback heads contradict the promoted artifact shelf.");
            }
        }

        string expectedAccess = decisionStatus == "review_required" && artifactCount == 0
            ? "review_required"
            : downloadAccessPosture;
        if (!string.Equals(RequireDecisionString(decision, "artifactAccessClass"), expectedAccess, StringComparison.Ordinal))
        {
            throw Invalid("Registry RELEASE_DECISION.json preview artifactAccessClass contradicts SNAPSHOT.json.");
        }

        _ = RequireDecisionTextArray(
            decision,
            "nextActions",
            maximumCount: MaximumActionCount,
            allowEmpty: false);

        string generatedAt = RequireDecisionString(decision, "generatedAt");
        string manifestGeneratedAt = RequireDecisionStringAllowEmpty(decision, "manifestGeneratedAt");
        string scorecardSha256 = RequireDecisionStringAllowEmpty(decision, "scorecardSha256");
        string convergenceSha256 = RequireDecisionStringAllowEmpty(decision, "convergenceSha256");
        if ((scorecardSha256.Length > 0 && !IsLowerHex(scorecardSha256, 64))
            || (convergenceSha256.Length > 0 && !IsLowerHex(convergenceSha256, 64)))
        {
            throw Invalid("Registry RELEASE_DECISION.json preview proof digests must be empty or canonical SHA-256 values.");
        }
        if (decisionStatus == "preview_ready"
            && (generatedAt == "unknown"
                || manifestGeneratedAt.Length == 0
                || !IsLowerHex(scorecardSha256, 64)
                || !IsLowerHex(convergenceSha256, 64)))
        {
            throw Invalid("Registry RELEASE_DECISION.json preview-ready proof timestamps and digests must be complete.");
        }

        string authoritySnapshotSha256 = RequireDecisionStringAllowEmpty(decision, "authoritySnapshotSha256");
        string candidateDecisionStatus = RequireDecisionStringAllowEmpty(decision, "candidateDecisionStatus");
        string candidateDecisionSha256 = RequireDecisionStringAllowEmpty(decision, "candidateDecisionSha256");
        bool emptyCandidate = authoritySnapshotSha256.Length == 0
            && candidateDecisionStatus.Length == 0
            && candidateDecisionSha256.Length == 0;
        if (emptyCandidate)
        {
            if (decisionStatus != "review_required")
            {
                throw Invalid("Registry RELEASE_DECISION.json preview-ready candidate closure cannot be empty.");
            }
        }
        else if (!IsLowerHex(authoritySnapshotSha256, 64)
                 || candidateDecisionStatus is not ("review_required" or "preview_ready")
                 || !IsLowerHex(candidateDecisionSha256, 64))
        {
            throw Invalid("Registry RELEASE_DECISION.json candidate closure must be either an empty review seed or a complete predecessor triple.");
        }
    }

    private static void ValidateStableDecision(
        JsonElement decision,
        JsonElement contract,
        string releaseVersion,
        string channel,
        string releaseStatus,
        string rolloutState,
        string supportabilityState,
        IReadOnlyList<string> availablePlatforms,
        IReadOnlyDictionary<string, string> primaryHeads,
        IReadOnlyList<AuthorityArtifact> artifacts,
        int artifactCount,
        string downloadAccessPosture,
        string knownIssueSummary,
        string manifestSha256,
        string registryCommit,
        string releaseDecisionStatus)
    {
        if (contract.ValueKind != JsonValueKind.String
            || !string.Equals(contract.GetString(), StableDecisionContract, StringComparison.Ordinal)
            || decision.TryGetProperty("contractName", out _)
            || decision.TryGetProperty("manifestSha256", out _)
            || !decision.TryGetProperty("contract_version", out JsonElement version)
            || version.ValueKind != JsonValueKind.Number
            || !version.TryGetInt32(out int contractVersion)
            || contractVersion != StableDecisionContractVersion)
        {
            throw Invalid("Registry RELEASE_DECISION.json stable contract discriminator/version is invalid or ambiguous.");
        }
        RequireExactObject(decision, StableDecisionFields, "Registry RELEASE_DECISION.json stable decision");

        if (!string.Equals(RequireDecisionString(decision, "releaseVersion"), releaseVersion, StringComparison.Ordinal)
            || !string.Equals(RequireDecisionString(decision, "releaseDecisionStatus"), "stable_ready", StringComparison.Ordinal)
            || !string.Equals(releaseDecisionStatus, "stable_ready", StringComparison.Ordinal)
            || !string.Equals(RequireDecisionString(decision, "status"), "pass", StringComparison.Ordinal)
            || !string.Equals(RequireDecisionString(decision, "verdict"), "GOLD_READY", StringComparison.Ordinal)
            || !string.Equals(RequireDecisionString(decision, "product"), "chummer", StringComparison.Ordinal))
        {
            throw Invalid("Registry RELEASE_DECISION.json stable status, verdict, version, product, and SNAPSHOT.json decision must be final-gold stable_ready.");
        }
        RequireDecisionUtcTimestamp(decision, "generated_at_utc");
        if (!string.Equals(
                RequireDecisionString(decision, "spine_ref"),
                "products/chummer/PRODUCT_SPINE.yaml",
                StringComparison.Ordinal)
            || !string.Equals(
                RequireDecisionString(decision, "design_ref"),
                "products/chummer/PRODUCT_SPINE_REDESIGN.md",
                StringComparison.Ordinal))
        {
            throw Invalid("Registry RELEASE_DECISION.json stable design references are not canonical.");
        }
        RequireDecisionExactTextArray(decision, "required_loops", StableRequiredLoops);
        RequireDecisionExactTextArray(decision, "required_surfaces", StableRequiredSurfaces);
        RequireDecisionExactTextArray(decision, "required_truth_domains", StableRequiredTruthDomains);
        RequireDecisionExactTextArray(decision, "required_horizon_lanes", StableRequiredHorizonLanes);
        RequireDecisionExactTextArray(decision, "required_feature_lanes", StableRequiredFeatureLanes);
        ValidateStableProjectionAdapterPolicy(decision);
        ValidateStableCompletionAudit(decision);
        if (RequireDecisionFindings(decision, "blocking_findings", expectedSeverity: "release_truth") != 0)
        {
            throw Invalid("Registry RELEASE_DECISION.json stable-ready graph cannot contain blocking findings.");
        }
        _ = RequireDecisionFindings(decision, "advisory_findings", expectedSeverity: "advisory");
        _ = RequireDecisionString(decision, "principle");

        JsonElement live = RequireDecisionObject(decision, "live_release");
        JsonElement authority = RequireDecisionObject(decision, "release_authority");
        RequireExactObject(live, StableLiveReleaseFields, "Registry RELEASE_DECISION.json stable live_release");
        RequireExactObject(authority, StableReleaseAuthorityFields, "Registry RELEASE_DECISION.json stable release_authority");
        string authorityDecisionSha256 = RequireDecisionSha256(authority, "release_decision_sha256");
        string authoritySnapshotSha256 = RequireDecisionSha256(authority, "snapshot_sha256");
        _ = RequireDecisionString(authority, "snapshot_path");
        string liveDecisionSha256 = RequireDecisionSha256(live, "release_decision_sha256");
        if (!FixedTimeDigestEquals(liveDecisionSha256, authorityDecisionSha256))
        {
            throw Invalid("Registry RELEASE_DECISION.json stable live and authority decision digests contradict each other.");
        }
        ValidateStableProofInputs(
            decision,
            releaseVersion,
            manifestSha256,
            registryCommit,
            authoritySnapshotSha256,
            authorityDecisionSha256);
        string[] platforms = RequireDecisionStringArray(live, "available_platforms", allowEmpty: false);
        SortedDictionary<string, string> heads = RequireDecisionHeadMap(live, "primary_head_by_platform", platforms);
        if (artifacts.Any(artifact =>
                !primaryHeads.TryGetValue(artifact.Platform, out string? primary)
                || !string.Equals(primary, artifact.Head, StringComparison.Ordinal)))
        {
            throw Invalid("Registry RELEASE_DECISION.json stable authority cannot omit eligible fallback heads.");
        }
        if (!string.Equals(RequireDecisionString(live, "version"), releaseVersion, StringComparison.Ordinal)
            || !string.Equals(RequireDecisionString(live, "channel"), channel, StringComparison.Ordinal)
            || !string.Equals(RequireDecisionString(live, "status"), releaseStatus, StringComparison.Ordinal)
            || !string.Equals(RequireDecisionString(live, "rollout_state"), rolloutState, StringComparison.Ordinal)
            || !string.Equals(RequireDecisionString(live, "supportability_state"), supportabilityState, StringComparison.Ordinal)
            || !FixedTimeDigestEquals(RequireDecisionSha256(live, "manifest_sha256"), manifestSha256)
            || !string.Equals(RequireDecisionLowerHex(live, "registry_commit", 40), registryCommit, StringComparison.Ordinal)
            || !platforms.SequenceEqual(availablePlatforms, StringComparer.Ordinal)
            || !StringMapEquals(heads, primaryHeads)
            || RequireDecisionInt(live, "artifact_count") != artifactCount
            || !string.Equals(RequireDecisionString(live, "download_access_posture"), downloadAccessPosture, StringComparison.Ordinal)
            || !string.Equals(RequireDecisionString(live, "known_issue_summary"), knownIssueSummary, StringComparison.Ordinal)
            || !string.Equals(RequireDecisionString(live, "release_decision_status"), "stable_ready", StringComparison.Ordinal)
            || !IsCanonicalStableEndpoint(RequireDecisionString(live, "status_endpoint"), "/status")
            || !IsCanonicalStableEndpoint(
                RequireDecisionString(live, "release_manifest_endpoint"),
                "/downloads/releases.json"))
        {
            throw Invalid("Registry RELEASE_DECISION.json stable live_release contradicts SNAPSHOT.json.");
        }

        if (!string.Equals(RequireDecisionString(authority, "contract"), AuthorityContract, StringComparison.Ordinal)
            || !FixedTimeDigestEquals(RequireDecisionSha256(authority, "manifest_sha256"), manifestSha256)
            || !string.Equals(RequireDecisionLowerHex(authority, "registry_commit", 40), registryCommit, StringComparison.Ordinal)
            || !string.Equals(RequireDecisionString(authority, "release_decision_status"), "stable_ready", StringComparison.Ordinal))
        {
            throw Invalid("Registry RELEASE_DECISION.json stable release_authority contradicts SNAPSHOT.json.");
        }
    }

    private static JsonElement RequireDecisionObject(JsonElement source, string propertyName)
    {
        if (!source.TryGetProperty(propertyName, out JsonElement value)
            || value.ValueKind != JsonValueKind.Object)
        {
            throw Invalid($"Registry RELEASE_DECISION.json {propertyName} must be an object.");
        }

        return value;
    }

    private static string RequireDecisionString(JsonElement source, string propertyName)
    {
        if (!source.TryGetProperty(propertyName, out JsonElement property)
            || property.ValueKind != JsonValueKind.String)
        {
            throw Invalid($"Registry RELEASE_DECISION.json {propertyName} must be a string.");
        }

        string? value = property.GetString();
        if (string.IsNullOrWhiteSpace(value)
            || !string.Equals(value, value.Trim(), StringComparison.Ordinal)
            || value.Length > MaximumActionLength)
        {
            throw Invalid($"Registry RELEASE_DECISION.json {propertyName} is empty, noncanonical, or oversized.");
        }

        return value;
    }

    private static string RequireDecisionStringAllowEmpty(JsonElement source, string propertyName)
    {
        if (!source.TryGetProperty(propertyName, out JsonElement property)
            || property.ValueKind != JsonValueKind.String)
        {
            throw Invalid($"Registry RELEASE_DECISION.json {propertyName} must be a string.");
        }

        string value = property.GetString() ?? string.Empty;
        if (!string.Equals(value, value.Trim(), StringComparison.Ordinal)
            || value.Length > MaximumActionLength)
        {
            throw Invalid($"Registry RELEASE_DECISION.json {propertyName} is noncanonical or oversized.");
        }

        return value;
    }

    private static string RequireDecisionSha256(JsonElement source, string propertyName)
        => RequireDecisionLowerHex(source, propertyName, 64);

    private static string RequireDecisionLowerHex(JsonElement source, string propertyName, int length)
    {
        string value = RequireDecisionString(source, propertyName);
        if (!IsLowerHex(value, length))
        {
            throw Invalid($"Registry RELEASE_DECISION.json {propertyName} is not canonical lower-case hexadecimal.");
        }

        return value;
    }

    private static bool IsLowerHex(string value, int length)
        => value.Length == length && value.All(static character =>
            character is >= '0' and <= '9' or >= 'a' and <= 'f');

    private static int RequireDecisionInt(JsonElement source, string propertyName)
    {
        if (!source.TryGetProperty(propertyName, out JsonElement property)
            || property.ValueKind != JsonValueKind.Number
            || !property.TryGetInt32(out int value)
            || value < 0
            || value > MaximumArtifactCount)
        {
            throw Invalid($"Registry RELEASE_DECISION.json {propertyName} must be a bounded non-negative integer.");
        }

        return value;
    }

    private static void RequireDecisionUtcTimestamp(JsonElement source, string propertyName)
    {
        string value = RequireDecisionString(source, propertyName);
        int timeSeparator = value.IndexOf('T');
        bool hasExplicitOffset = value.EndsWith('Z')
            || timeSeparator >= 0 && value.LastIndexOf('+') > timeSeparator
            || timeSeparator >= 0 && value.LastIndexOf('-') > timeSeparator;
        if (!hasExplicitOffset
            || !DateTimeOffset.TryParse(
                value,
                CultureInfo.InvariantCulture,
                DateTimeStyles.None,
                out _))
        {
            throw Invalid($"Registry RELEASE_DECISION.json {propertyName} must be an explicit ISO-8601 timestamp.");
        }
    }

    private static string[] RequireDecisionTextArray(
        JsonElement source,
        string propertyName,
        int maximumCount,
        bool allowEmpty)
    {
        if (!source.TryGetProperty(propertyName, out JsonElement array)
            || array.ValueKind != JsonValueKind.Array
            || array.GetArrayLength() > maximumCount
            || !allowEmpty && array.GetArrayLength() == 0)
        {
            throw Invalid($"Registry RELEASE_DECISION.json {propertyName} must be a bounded array.");
        }

        var result = new List<string>(array.GetArrayLength());
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonElement item in array.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.String)
            {
                throw Invalid($"Registry RELEASE_DECISION.json {propertyName} entries must be strings.");
            }

            string value = item.GetString() ?? string.Empty;
            if (string.IsNullOrWhiteSpace(value)
                || !string.Equals(value, value.Trim(), StringComparison.Ordinal)
                || value.Length > MaximumActionLength
                || !seen.Add(value))
            {
                throw Invalid($"Registry RELEASE_DECISION.json {propertyName} entries must be unique canonical bounded strings.");
            }
            result.Add(value);
        }

        return result.ToArray();
    }

    private static void RequireDecisionExactTextArray(
        JsonElement source,
        string propertyName,
        IReadOnlyList<string> expected)
    {
        string[] observed = RequireDecisionTextArray(
            source,
            propertyName,
            maximumCount: expected.Count,
            allowEmpty: false);
        if (!observed.SequenceEqual(expected, StringComparer.Ordinal))
        {
            throw Invalid($"Registry RELEASE_DECISION.json {propertyName} does not match the generator contract.");
        }
    }

    private static int RequireDecisionFindings(
        JsonElement source,
        string propertyName,
        string expectedSeverity,
        string? sequentialIdPrefix = null)
    {
        if (!source.TryGetProperty(propertyName, out JsonElement findings)
            || findings.ValueKind != JsonValueKind.Array
            || findings.GetArrayLength() > MaximumArtifactCount)
        {
            throw Invalid($"Registry RELEASE_DECISION.json {propertyName} must be a bounded array.");
        }

        int index = 0;
        var ids = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonElement finding in findings.EnumerateArray())
        {
            RequireExactObject(
                finding,
                DecisionFindingFields,
                $"Registry RELEASE_DECISION.json {propertyName} finding");
            string id = RequireDecisionString(finding, "id");
            string severity = RequireDecisionString(finding, "severity");
            _ = RequireDecisionString(finding, "summary");
            index++;
            if (!IsCanonicalDecisionToken(id)
                || !ids.Add(id)
                || !string.Equals(severity, expectedSeverity, StringComparison.Ordinal)
                || sequentialIdPrefix is not null
                   && !string.Equals(id, $"{sequentialIdPrefix}{index}", StringComparison.Ordinal))
            {
                throw Invalid($"Registry RELEASE_DECISION.json {propertyName} finding identity or severity is invalid.");
            }
        }

        return index;
    }

    private static void ValidateStableProjectionAdapterPolicy(JsonElement decision)
    {
        JsonElement policy = RequireDecisionObject(decision, "projection_adapter_policy");
        RequireExactObject(
            policy,
            StableProjectionAdapterPolicyFields,
            "Registry RELEASE_DECISION.json projection_adapter_policy");
        if (!string.Equals(RequireDecisionString(policy, "status"), "pass", StringComparison.Ordinal)
            || !policy.TryGetProperty("adapters_are_projection_only", out JsonElement projectionOnly)
            || projectionOnly.ValueKind is not (JsonValueKind.True or JsonValueKind.False)
            || !projectionOnly.GetBoolean())
        {
            throw Invalid("Registry RELEASE_DECISION.json projection adapter policy must pass and remain projection-only.");
        }
        RequireDecisionExactTextArray(policy, "adapters", StableProjectionAdapters);
    }

    private static void ValidateStableProofInputs(
        JsonElement decision,
        string releaseVersion,
        string manifestSha256,
        string registryCommit,
        string authoritySnapshotSha256,
        string authorityDecisionSha256)
    {
        if (!decision.TryGetProperty("proof_inputs", out JsonElement proofInputs)
            || proofInputs.ValueKind != JsonValueKind.Array
            || proofInputs.GetArrayLength() != StableProofKinds.Count)
        {
            throw Invalid("Registry RELEASE_DECISION.json proof_inputs must contain the exact generator proof set.");
        }

        var observed = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonElement proof in proofInputs.EnumerateArray())
        {
            if (proof.ValueKind != JsonValueKind.Object)
            {
                throw Invalid("Registry RELEASE_DECISION.json proof_inputs entries must be objects.");
            }
            string kind = RequireDecisionString(proof, "kind");
            _ = RequireDecisionString(proof, "path");
            if (!StableProofKinds.Contains(kind)
                || !observed.Add(kind)
                || !string.Equals(RequireDecisionString(proof, "status"), "pass", StringComparison.Ordinal))
            {
                throw Invalid("Registry RELEASE_DECISION.json proof_inputs must contain unique passing generator proofs.");
            }

            HashSet<string> expectedFields = kind switch
            {
                "parity_registry" => StableParityProofFields,
                "campaign_operability_scorecard" => StableCampaignProofFields,
                "journey_gates" => StableJourneyProofFields,
                "release_ready_matrix" => StableReleaseReadyProofFields,
                "ea_release_critical_readiness" => StableEaProofFields,
                "registry_release_authority" => StableRegistryAuthorityProofFields,
                "live_release_manifest" => StableLiveManifestProofFields,
                _ when StableReceiptProofKinds.Contains(kind) => StableReceiptProofFields,
                _ => StableBaseProofFields
            };
            RequireExactObject(
                proof,
                expectedFields,
                $"Registry RELEASE_DECISION.json proof_inputs {kind}");

            if (kind == "parity_registry" && RequireDecisionInt(proof, "family_count") == 0)
            {
                throw Invalid("Registry RELEASE_DECISION.json parity proof must cover at least one family.");
            }
            if (kind == "campaign_operability_scorecard"
                && RequireDecisionInt(proof, "cell_count") != 36)
            {
                throw Invalid("Registry RELEASE_DECISION.json campaign proof must cover the exact 36-cell scorecard.");
            }
            if (kind == "release_ready_matrix")
            {
                int requiredGateCount = RequireDecisionInt(proof, "required_gate_count");
                int completedGateCount = RequireDecisionInt(proof, "completed_gate_count");
                if (requiredGateCount == 0 || completedGateCount != requiredGateCount)
                {
                    throw Invalid("Registry RELEASE_DECISION.json release-ready proof must complete every required gate.");
                }
            }
            if (kind == "ea_release_critical_readiness")
            {
                _ = RequireDecisionTextArray(
                    proof,
                    "required_component_keys",
                    maximumCount: MaximumActionCount,
                    allowEmpty: false);
                _ = RequireDecisionTextArray(
                    proof,
                    "optional_blocked_component_keys",
                    maximumCount: MaximumActionCount,
                    allowEmpty: true);
            }

            if (expectedFields.Contains("generated_at"))
            {
                _ = RequireDecisionStringAllowEmpty(proof, "generated_at");
                if (StableReleaseBoundProofKinds.Contains(kind))
                {
                    RequireDecisionUtcTimestamp(proof, "generated_at");
                }
            }
            if (expectedFields.Contains("release_version"))
            {
                string proofReleaseVersion = RequireDecisionStringAllowEmpty(proof, "release_version");
                string proofSnapshotSha256 = RequireDecisionStringAllowEmpty(proof, "snapshot_sha256");
                string proofManifestSha256 = RequireDecisionStringAllowEmpty(proof, "manifest_sha256");
                string proofDecisionSha256 = RequireDecisionStringAllowEmpty(proof, "release_decision_sha256");
                if (new[] { proofSnapshotSha256, proofManifestSha256, proofDecisionSha256 }
                    .Any(value => value.Length > 0 && !IsLowerHex(value, 64)))
                {
                    throw Invalid("Registry RELEASE_DECISION.json proof binding digests must be empty or canonical SHA-256 values.");
                }
                if (StableReleaseBoundProofKinds.Contains(kind)
                    && (!string.Equals(proofReleaseVersion, releaseVersion, StringComparison.Ordinal)
                        || !FixedTimeDigestEquals(proofSnapshotSha256, authoritySnapshotSha256)
                        || !FixedTimeDigestEquals(proofManifestSha256, manifestSha256)
                        || !FixedTimeDigestEquals(proofDecisionSha256, authorityDecisionSha256)))
                {
                    throw Invalid("Registry RELEASE_DECISION.json release-bound proof contradicts stable release authority.");
                }
            }
            if (kind == "registry_release_authority"
                && (!FixedTimeDigestEquals(
                        RequireDecisionSha256(proof, "snapshot_sha256"),
                        authoritySnapshotSha256)
                    || !FixedTimeDigestEquals(
                        RequireDecisionSha256(proof, "manifest_sha256"),
                        manifestSha256)
                    || !string.Equals(
                        RequireDecisionLowerHex(proof, "registry_commit", 40),
                        registryCommit,
                        StringComparison.Ordinal)
                    || !string.Equals(
                        RequireDecisionString(proof, "release_decision_status"),
                        "stable_ready",
                        StringComparison.Ordinal)
                    || !FixedTimeDigestEquals(
                        RequireDecisionSha256(proof, "release_decision_sha256"),
                        authorityDecisionSha256)))
            {
                throw Invalid("Registry RELEASE_DECISION.json registry authority proof contradicts the stable authority block.");
            }
        }
        if (!observed.SetEquals(StableProofKinds))
        {
            throw Invalid("Registry RELEASE_DECISION.json proof_inputs omit a required generator proof.");
        }
    }

    private static void ValidateStableCompletionAudit(JsonElement decision)
    {
        JsonElement audit = RequireDecisionObject(decision, "completion_audit");
        RequireExactObject(
            audit,
            StableCompletionAuditFields,
            "Registry RELEASE_DECISION.json completion_audit");
        if (!string.Equals(RequireDecisionString(audit, "status"), "pass", StringComparison.Ordinal)
            || RequireDecisionInt(audit, "requirement_count") != StableCompletionRequirements.Count
            || RequireDecisionInt(audit, "passed_count") != StableCompletionRequirements.Count
            || RequireDecisionInt(audit, "failed_count") != 0
            || !audit.TryGetProperty("requirements", out JsonElement requirements)
            || requirements.ValueKind != JsonValueKind.Array
            || requirements.GetArrayLength() != StableCompletionRequirements.Count)
        {
            throw Invalid("Registry RELEASE_DECISION.json completion audit must prove every generator requirement passed.");
        }

        var observed = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonElement requirement in requirements.EnumerateArray())
        {
            RequireExactObject(
                requirement,
                StableCompletionRequirementFields,
                "Registry RELEASE_DECISION.json completion requirement");
            string id = RequireDecisionString(requirement, "id");
            if (!StableCompletionRequirements.TryGetValue(id, out string[]? expectedProofKinds)
                || !observed.Add(id)
                || !string.Equals(RequireDecisionString(requirement, "status"), "pass", StringComparison.Ordinal))
            {
                throw Invalid("Registry RELEASE_DECISION.json completion requirement identity or status is invalid.");
            }
            RequireDecisionExactTextArray(requirement, "proof_kinds", expectedProofKinds);
            if (RequireDecisionTextArray(
                    requirement,
                    "missing_or_failed_proof_kinds",
                    maximumCount: StableProofKinds.Count,
                    allowEmpty: true).Length != 0)
            {
                throw Invalid("Registry RELEASE_DECISION.json passing completion requirements cannot name missing proofs.");
            }
        }
        if (!observed.SetEquals(StableCompletionRequirements.Keys))
        {
            throw Invalid("Registry RELEASE_DECISION.json completion audit omits a generator requirement.");
        }
    }

    private static bool IsCanonicalStableEndpoint(string value, string expectedPath)
        => Uri.TryCreate(value, UriKind.Absolute, out Uri? endpoint)
           && string.Equals(endpoint.Scheme, Uri.UriSchemeHttps, StringComparison.Ordinal)
           && string.Equals(endpoint.Host, "chummer.run", StringComparison.OrdinalIgnoreCase)
           && endpoint.IsDefaultPort
           && string.Equals(endpoint.AbsolutePath, expectedPath, StringComparison.Ordinal)
           && string.IsNullOrEmpty(endpoint.Query)
           && string.IsNullOrEmpty(endpoint.Fragment);

    private static string[] RequireDecisionStringArray(
        JsonElement source,
        string propertyName,
        bool allowEmpty)
    {
        if (!source.TryGetProperty(propertyName, out JsonElement array)
            || array.ValueKind != JsonValueKind.Array
            || array.GetArrayLength() > MaximumPlatformCount
            || (!allowEmpty && array.GetArrayLength() == 0))
        {
            throw Invalid($"Registry RELEASE_DECISION.json {propertyName} must be a bounded non-empty ordered array.");
        }

        var result = new List<string>(array.GetArrayLength());
        string? prior = null;
        foreach (JsonElement item in array.EnumerateArray())
        {
            if (item.ValueKind != JsonValueKind.String)
            {
                throw Invalid($"Registry RELEASE_DECISION.json {propertyName} entries must be strings.");
            }

            string value = item.GetString() ?? string.Empty;
            if (!IsCanonicalDecisionToken(value)
                || prior is not null && string.CompareOrdinal(prior, value) >= 0)
            {
                throw Invalid($"Registry RELEASE_DECISION.json {propertyName} must contain unique canonical IDs in ordinal order.");
            }

            result.Add(value);
            prior = value;
        }

        return result.ToArray();
    }

    private static SortedDictionary<string, string> RequireDecisionHeadMap(
        JsonElement source,
        string propertyName,
        IReadOnlyList<string> platforms)
    {
        JsonElement map = RequireDecisionObject(source, propertyName);
        var result = new SortedDictionary<string, string>(StringComparer.Ordinal);
        string? prior = null;
        foreach (JsonProperty property in map.EnumerateObject())
        {
            if (property.Value.ValueKind != JsonValueKind.String
                || !IsCanonicalDecisionToken(property.Name)
                || !IsCanonicalDecisionToken(property.Value.GetString() ?? string.Empty)
                || prior is not null && string.CompareOrdinal(prior, property.Name) >= 0)
            {
                throw Invalid($"Registry RELEASE_DECISION.json {propertyName} must be an ordered canonical string map.");
            }

            result.Add(property.Name, property.Value.GetString()!);
            prior = property.Name;
        }

        if (!result.Keys.SequenceEqual(platforms, StringComparer.Ordinal))
        {
            throw Invalid($"Registry RELEASE_DECISION.json {propertyName} keys must exactly match its platform list.");
        }

        return result;
    }

    private static IReadOnlyDictionary<string, string[]> RequireDecisionFallbackMap(
        JsonElement source,
        string propertyName,
        IReadOnlyList<string> platforms,
        IReadOnlyDictionary<string, string> primaryHeads)
    {
        JsonElement map = RequireDecisionObject(source, propertyName);
        var result = new SortedDictionary<string, string[]>(StringComparer.Ordinal);
        string? priorPlatform = null;
        foreach (JsonProperty property in map.EnumerateObject())
        {
            if (!IsCanonicalDecisionToken(property.Name)
                || property.Value.ValueKind != JsonValueKind.Array
                || !primaryHeads.TryGetValue(property.Name, out string? primary)
                || priorPlatform is not null && string.CompareOrdinal(priorPlatform, property.Name) >= 0)
            {
                throw Invalid($"Registry RELEASE_DECISION.json {propertyName} must be an ordered platform map.");
            }

            var heads = new List<string>();
            string? priorHead = null;
            foreach (JsonElement item in property.Value.EnumerateArray())
            {
                if (item.ValueKind != JsonValueKind.String)
                {
                    throw Invalid($"Registry RELEASE_DECISION.json {propertyName} entries must be strings.");
                }

                string head = item.GetString() ?? string.Empty;
                if (!IsCanonicalDecisionToken(head)
                    || priorHead is not null && string.CompareOrdinal(priorHead, head) >= 0
                    || string.Equals(primary, head, StringComparison.Ordinal))
                {
                    throw Invalid($"Registry RELEASE_DECISION.json {propertyName} fallback heads must be unique, ordered, canonical, and non-primary.");
                }

                heads.Add(head);
                priorHead = head;
            }

            result.Add(property.Name, heads.ToArray());
            priorPlatform = property.Name;
        }

        return result;
    }

    private static bool IsCanonicalDecisionToken(string value)
        => value.Length is > 0 and <= MaximumTokenLength
           && char.IsAsciiLetterOrDigit(value[0])
           && string.Equals(value, value.ToLowerInvariant(), StringComparison.Ordinal)
           && value.All(static character => char.IsAsciiLetterOrDigit(character)
               || character is '.' or '_' or '-');

    private static bool StringMapEquals(
        IReadOnlyDictionary<string, string> left,
        IReadOnlyDictionary<string, string> right)
        => left.Count == right.Count
           && left.All(pair => right.TryGetValue(pair.Key, out string? value)
               && string.Equals(pair.Value, value, StringComparison.Ordinal));

    private static void RequireExactObject(JsonElement value, HashSet<string> expected, string label)
    {
        if (value.ValueKind != JsonValueKind.Object)
        {
            throw Invalid($"{label} must be a JSON object.");
        }

        string[] observed = value.EnumerateObject().Select(static property => property.Name).ToArray();
        string[] missing = expected.Except(observed, StringComparer.Ordinal).OrderBy(static name => name, StringComparer.Ordinal).ToArray();
        string[] unknown = observed.Except(expected, StringComparer.Ordinal).OrderBy(static name => name, StringComparer.Ordinal).ToArray();
        if (missing.Length > 0 || unknown.Length > 0)
        {
            throw Invalid($"{label} has missing [{string.Join(", ", missing)}] or unknown [{string.Join(", ", unknown)}] fields.");
        }
    }

    private static string RequireString(JsonElement source, string propertyName, int maximumLength, string label)
    {
        JsonElement property = source.GetProperty(propertyName);
        if (property.ValueKind != JsonValueKind.String)
        {
            throw Invalid($"{label} {propertyName} must be a string.");
        }

        string? value = property.GetString();
        if (string.IsNullOrWhiteSpace(value)
            || !string.Equals(value, value.Trim(), StringComparison.Ordinal)
            || value.Length > maximumLength)
        {
            throw Invalid($"{label} {propertyName} is empty, noncanonical, or oversized.");
        }

        return value;
    }

    private static string RequirePortableIdentifier(JsonElement source, string propertyName, string label)
    {
        string value = RequireString(source, propertyName, MaximumTokenLength, label);
        if (!char.IsAsciiLetterOrDigit(value[0])
            || value.Any(static character => !char.IsAsciiLetterOrDigit(character)
                && character is not '.' and not '_' and not '-' and not '+'))
        {
            throw Invalid($"{label} {propertyName} is not a portable identifier.");
        }

        return value;
    }

    private static string RequireCanonicalToken(JsonElement source, string propertyName, string label)
    {
        string value = RequireString(source, propertyName, MaximumTokenLength, label);
        if (!char.IsAsciiLetterOrDigit(value[0])
            || value.Any(static character => !char.IsAsciiLetterOrDigit(character)
                && character is not '.' and not '_' and not '-'))
        {
            throw Invalid($"{label} {propertyName} is not a canonical token.");
        }

        if (!string.Equals(value, value.ToLowerInvariant(), StringComparison.Ordinal))
        {
            throw Invalid($"{label} {propertyName} must be lower-case.");
        }

        return value;
    }

    private static string RequireDecisionStatus(JsonElement source, string propertyName, string label)
    {
        string value = RequireCanonicalToken(source, propertyName, label);
        if (!AllowedDecisionStatuses.Contains(value))
        {
            throw Invalid($"{label} {propertyName} is not an allowed release decision status.");
        }

        return value;
    }

    private static string RequireAuthorityToken(JsonElement source, string propertyName, string label)
    {
        string value = RequireCanonicalToken(source, propertyName, label);
        if (SentinelTokens.Contains(value))
        {
            throw Invalid($"{label} {propertyName} cannot use a release-truth sentinel.");
        }

        return value;
    }

    private static string RequireSha256(JsonElement source, string propertyName, string label)
        => RequireLowerHex(source, propertyName, 64, label);

    private static string RequireLowerHex(JsonElement source, string propertyName, int length, string label)
    {
        string value = RequireString(source, propertyName, length, label);
        if (value.Length != length || value.Any(static character =>
                character is not (>= '0' and <= '9') and not (>= 'a' and <= 'f')))
        {
            throw Invalid($"{label} {propertyName} is not a canonical lower-case hexadecimal value.");
        }

        return value;
    }

    private static int RequireNonnegativeInt(JsonElement source, string propertyName, string label)
    {
        JsonElement property = source.GetProperty(propertyName);
        if (property.ValueKind != JsonValueKind.Number
            || !property.TryGetInt32(out int value)
            || value < 0
            || value > MaximumArtifactCount)
        {
            throw Invalid($"{label} {propertyName} must be a bounded non-negative integer.");
        }

        return value;
    }

    private static int RequireNextActions(JsonElement actions)
    {
        if (actions.ValueKind != JsonValueKind.Array
            || actions.GetArrayLength() > MaximumActionCount)
        {
            throw Invalid("Registry SNAPSHOT.json nextActions must be a bounded array.");
        }

        var observed = new HashSet<string>(StringComparer.Ordinal);
        foreach (JsonElement action in actions.EnumerateArray())
        {
            if (action.ValueKind != JsonValueKind.String)
            {
                throw Invalid("Registry SNAPSHOT.json nextActions entries must be strings.");
            }

            string? value = action.GetString();
            if (string.IsNullOrWhiteSpace(value)
                || !string.Equals(value, value.Trim(), StringComparison.Ordinal)
                || value.Length > MaximumActionLength
                || !observed.Add(value))
            {
                throw Invalid("Registry SNAPSHOT.json nextActions entries must be unique, canonical, and bounded.");
            }
        }

        return actions.GetArrayLength();
    }

    private static void RequireFixedPath(JsonElement source, string propertyName, string expected)
    {
        string value = RequireString(source, propertyName, MaximumTokenLength, "Registry SNAPSHOT.json");
        if (!string.Equals(value, expected, StringComparison.Ordinal))
        {
            throw Invalid($"Registry SNAPSHOT.json {propertyName} must be {expected}.");
        }
    }

    private static AuthorityArtifact[] RequireAuthorityArtifacts(JsonElement artifacts)
    {
        if (artifacts.ValueKind != JsonValueKind.Array
            || artifacts.GetArrayLength() > MaximumArtifactCount)
        {
            throw Invalid("Registry SNAPSHOT.json artifacts must be a bounded array.");
        }

        var result = new List<AuthorityArtifact>(artifacts.GetArrayLength());
        string? priorId = null;
        foreach (JsonElement artifact in artifacts.EnumerateArray())
        {
            RequireExactObject(artifact, ArtifactFields, "Registry SNAPSHOT.json artifact");
            string artifactId = RequireAuthorityToken(artifact, "artifactId", "Registry SNAPSHOT.json artifact");
            if (priorId is not null && string.CompareOrdinal(priorId, artifactId) >= 0)
            {
                throw Invalid("Registry SNAPSHOT.json artifact IDs must be unique and in ordinal order.");
            }

            priorId = artifactId;
            string head = RequireAuthorityToken(artifact, "head", "Registry SNAPSHOT.json artifact");
            string platform = RequireAuthorityToken(artifact, "platform", "Registry SNAPSHOT.json artifact");
            string rid = RequireAuthorityToken(artifact, "rid", "Registry SNAPSHOT.json artifact");
            string arch = RequireAuthorityToken(artifact, "arch", "Registry SNAPSHOT.json artifact");
            string kind = RequireCanonicalToken(artifact, "kind", "Registry SNAPSHOT.json artifact");
            if (kind != "installer")
            {
                throw Invalid("Registry SNAPSHOT.json eligible artifact kind must be installer.");
            }
            string downloadUrl = RequireString(
                artifact,
                "downloadUrl",
                MaximumUrlLength,
                "Registry SNAPSHOT.json artifact");
            string sha256 = RequireSha256(artifact, "sha256", "Registry SNAPSHOT.json artifact");
            long sizeBytes = RequirePositiveLong(artifact, "sizeBytes", "Registry SNAPSHOT.json artifact");
            RequireExactArtifactState(artifact, "compatibilityState", "compatible");
            RequireExactArtifactState(artifact, "promotionState", "promoted");
            RequireExactArtifactState(artifact, "publicationScope", "signed-in-and-public");
            RequireExactArtifactState(artifact, "revokeState", "not_revoked");
            string publicInstallRoute = RequirePublicInstallRoute(artifact);
            string accessClass = RequireCanonicalToken(
                artifact,
                "installAccessClass",
                "Registry SNAPSHOT.json artifact");
            if (!AllowedAccessClasses.Contains(accessClass))
            {
                throw Invalid("Registry SNAPSHOT.json artifact installAccessClass is not supported.");
            }
            bool routesEqual = string.Equals(
                publicInstallRoute,
                downloadUrl,
                StringComparison.Ordinal);
            if (accessClass == "open_public" ? routesEqual : !routesEqual)
            {
                throw Invalid(
                    "Registry SNAPSHOT.json artifact routes contradict installAccessClass: " +
                    "open_public bytes require a distinct install dispatch, while protected bytes " +
                    "must use their generation-bound install route.");
            }

            result.Add(new(
                artifactId,
                head,
                platform,
                rid,
                arch,
                kind,
                downloadUrl,
                sha256,
                sizeBytes,
                publicInstallRoute,
                accessClass));
        }

        return result.ToArray();
    }

    private static string[] RequireAvailablePlatforms(JsonElement platforms)
    {
        if (platforms.ValueKind != JsonValueKind.Array
            || platforms.GetArrayLength() > MaximumPlatformCount)
        {
            throw Invalid("Registry SNAPSHOT.json availablePlatforms must be a bounded array.");
        }

        var result = new List<string>(platforms.GetArrayLength());
        string? prior = null;
        foreach (JsonElement platform in platforms.EnumerateArray())
        {
            if (platform.ValueKind != JsonValueKind.String)
            {
                throw Invalid("Registry SNAPSHOT.json availablePlatforms entries must be strings.");
            }

            string? value = platform.GetString();
            if (string.IsNullOrWhiteSpace(value)
                || !string.Equals(value, value.Trim(), StringComparison.Ordinal)
                || !string.Equals(value, value.ToLowerInvariant(), StringComparison.Ordinal)
                || value.Length > MaximumTokenLength
                || !char.IsAsciiLetterOrDigit(value[0])
                || value.Any(static character => !char.IsAsciiLetterOrDigit(character)
                    && character is not '.' and not '_' and not '-')
                || SentinelTokens.Contains(value)
                || (prior is not null && string.CompareOrdinal(prior, value) >= 0))
            {
                throw Invalid("Registry SNAPSHOT.json availablePlatforms must be unique lower-case IDs in ordinal order.");
            }

            result.Add(value);
            prior = value;
        }

        return result.ToArray();
    }

    private static long RequirePositiveLong(JsonElement source, string propertyName, string label)
    {
        JsonElement property = source.GetProperty(propertyName);
        if (property.ValueKind != JsonValueKind.Number
            || !property.TryGetInt64(out long value)
            || value <= 0)
        {
            throw Invalid($"{label} {propertyName} must be a positive integer.");
        }

        return value;
    }

    private static void RequireExactArtifactState(
        JsonElement artifact,
        string propertyName,
        string expected)
    {
        string value = RequireCanonicalToken(
            artifact,
            propertyName,
            "Registry SNAPSHOT.json artifact");
        if (!string.Equals(value, expected, StringComparison.Ordinal))
        {
            throw Invalid($"Registry SNAPSHOT.json artifact {propertyName} must be {expected}.");
        }
    }

    private static string RequirePublicInstallRoute(JsonElement artifact)
    {
        string route = RequireString(
            artifact,
            "publicInstallRoute",
            MaximumUrlLength,
            "Registry SNAPSHOT.json artifact");
        string[] segments = route.Split('/', StringSplitOptions.RemoveEmptyEntries);
        bool hasUnsafeDecodedSegment;
        try
        {
            hasUnsafeDecodedSegment = segments.Any(static segment =>
            {
                string decoded = Uri.UnescapeDataString(segment);
                return decoded is "." or ".."
                       || decoded.Contains('/')
                       || decoded.Contains('\\')
                       || decoded.Any(char.IsControl)
                       || decoded.Any(char.IsWhiteSpace);
            });
        }
        catch (UriFormatException)
        {
            hasUnsafeDecodedSegment = true;
        }

        if (!route.StartsWith("/", StringComparison.Ordinal)
            || route.StartsWith("//", StringComparison.Ordinal)
            || route.Contains("//", StringComparison.Ordinal)
            || segments.Length == 0
            || route.Contains('?')
            || route.Contains('#')
            || route.Contains('\\')
            || route.Any(char.IsWhiteSpace)
            || hasUnsafeDecodedSegment)
        {
            throw Invalid("Registry SNAPSHOT.json artifact publicInstallRoute must be a query-free, fragment-free root-relative public path.");
        }

        return route;
    }

    private static SortedDictionary<string, string> RequirePrimaryHeads(
        JsonElement primaryHeads,
        IReadOnlyList<string> availablePlatforms,
        IReadOnlyList<AuthorityArtifact> artifacts)
    {
        if (primaryHeads.ValueKind != JsonValueKind.Object)
        {
            throw Invalid("Registry SNAPSHOT.json primaryHeadByPlatform must be an object.");
        }

        var result = new SortedDictionary<string, string>(StringComparer.Ordinal);
        string? prior = null;
        foreach (JsonProperty property in primaryHeads.EnumerateObject())
        {
            if (prior is not null && string.CompareOrdinal(prior, property.Name) >= 0)
            {
                throw Invalid("Registry SNAPSHOT.json primaryHeadByPlatform keys must be in ordinal order.");
            }

            if (property.Value.ValueKind != JsonValueKind.String)
            {
                throw Invalid("Registry SNAPSHOT.json primaryHeadByPlatform values must be strings.");
            }

            string? head = property.Value.GetString();
            if (string.IsNullOrWhiteSpace(head)
                || !string.Equals(head, head.Trim(), StringComparison.Ordinal)
                || !string.Equals(head, head.ToLowerInvariant(), StringComparison.Ordinal)
                || head.Length > MaximumTokenLength
                || !char.IsAsciiLetterOrDigit(head[0])
                || head.Any(static character => !char.IsAsciiLetterOrDigit(character)
                    && character is not '.' and not '_' and not '-')
                || SentinelTokens.Contains(head))
            {
                throw Invalid("Registry SNAPSHOT.json primaryHeadByPlatform values must be canonical lower-case heads.");
            }

            if (!artifacts.Any(artifact =>
                    string.Equals(artifact.Platform, property.Name, StringComparison.Ordinal)
                    && string.Equals(artifact.Head, head, StringComparison.Ordinal)))
            {
                throw Invalid("Registry SNAPSHOT.json primaryHeadByPlatform does not resolve to a promoted artifact.");
            }

            result.Add(property.Name, head);
            prior = property.Name;
        }

        if (!result.Keys.SequenceEqual(availablePlatforms, StringComparer.Ordinal))
        {
            throw Invalid("Registry SNAPSHOT.json primaryHeadByPlatform keys must exactly equal availablePlatforms.");
        }

        return result;
    }

    private static void CompareArtifactBindings(
        IReadOnlyList<AuthorityArtifact> authorityArtifacts,
        IReadOnlyList<PublicReleaseArtifactDto> publicArtifacts)
    {
        var hubById = new Dictionary<string, PublicReleaseArtifactDto>(StringComparer.Ordinal);
        foreach (PublicReleaseArtifactDto artifact in publicArtifacts)
        {
            string id = (artifact.Id ?? string.Empty).Trim();
            if (id.Length == 0 || !hubById.TryAdd(id, artifact))
            {
                throw Invalid("The final Hub public shelf contains empty or duplicate artifact IDs.");
            }
        }

        if (!authorityArtifacts.Select(static artifact => artifact.ArtifactId)
                .SequenceEqual(hubById.Keys.OrderBy(static id => id, StringComparer.Ordinal), StringComparer.Ordinal))
        {
            throw Invalid("Registry SNAPSHOT.json artifacts do not exactly equal the final Hub public artifact shelf.");
        }

        foreach (AuthorityArtifact authority in authorityArtifacts)
        {
            PublicReleaseArtifactDto hub = hubById[authority.ArtifactId];
            string hubSha256 = (hub.Sha256 ?? string.Empty).Trim().ToLowerInvariant();
            if (!string.Equals(authority.Head, NormalizeExactToken(hub.Head), StringComparison.Ordinal)
                || !string.Equals(authority.Platform, PublicReleaseTruthProjectionService.ResolvePlatformId(hub), StringComparison.Ordinal)
                || !string.Equals(authority.Rid, NormalizeExactToken(hub.Rid), StringComparison.Ordinal)
                || !string.Equals(authority.Arch, NormalizeExactToken(hub.Arch), StringComparison.Ordinal)
                || !string.Equals(authority.Kind, "installer", StringComparison.Ordinal)
                || !string.Equals(NormalizeExactToken(hub.Kind), "installer", StringComparison.Ordinal)
                || !string.Equals(authority.DownloadUrl, (hub.Url ?? string.Empty).Trim(), StringComparison.Ordinal)
                || !string.Equals(authority.Sha256, hubSha256, StringComparison.Ordinal)
                || hub.SizeBytes != authority.SizeBytes
                || !string.Equals(
                    "compatible",
                    NormalizeExactToken(hub.CompatibilityState),
                    StringComparison.Ordinal)
                || !string.Equals(authority.InstallAccessClass, NormalizeExactToken(hub.InstallAccessClass), StringComparison.Ordinal))
            {
                throw Invalid($"Registry SNAPSHOT.json artifact '{authority.ArtifactId}' contradicts the final Hub public binding.");
            }
        }
    }

    private static string NormalizeExactToken(string? value)
        => string.IsNullOrWhiteSpace(value)
            ? PublicReleaseTruthProjectionDto.Unknown
            : value.Trim().ToLowerInvariant();

    private static string DeriveAccessPosture(IReadOnlyList<AuthorityArtifact> artifacts)
    {
        if (artifacts.Count == 0)
        {
            return "unavailable";
        }

        string[] classes = artifacts
            .Select(static artifact => artifact.InstallAccessClass)
            .Distinct(StringComparer.Ordinal)
            .ToArray();
        return classes.Length == 1 ? classes[0] : "mixed";
    }

    private static void RequireDigestMatchesBytes(string expected, ReadOnlySpan<byte> bytes, string label)
    {
        Span<byte> actual = stackalloc byte[32];
        SHA256.HashData(bytes, actual);
        byte[] expectedBytes = Convert.FromHexString(expected);
        if (!CryptographicOperations.FixedTimeEquals(expectedBytes, actual))
        {
            throw Invalid($"{label} does not match the exact authority bytes.");
        }
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

    private static bool HasExactInventoryPath(ReleaseShelfSnapshot shelf, string expected)
        => shelf.Inventory.ContainsKey(expected);

    private static void RejectNoncanonicalInventoryPath(
        ReleaseShelfSnapshot shelf,
        string expected,
        bool hasExact)
    {
        if (hasExact)
        {
            return;
        }

        if (shelf.Inventory.Keys.Any(path => string.Equals(path, expected, StringComparison.OrdinalIgnoreCase)))
        {
            throw Invalid($"Release-shelf authority evidence path must use exact casing: {expected}.");
        }
    }

    private static InvalidDataException Invalid(string message, Exception? inner = null)
        => inner is null ? new InvalidDataException(message) : new InvalidDataException(message, inner);

    private sealed record AuthorityArtifact(
        string ArtifactId,
        string Head,
        string Platform,
        string Rid,
        string Arch,
        string Kind,
        string DownloadUrl,
        string Sha256,
        long SizeBytes,
        string PublicInstallRoute,
        string InstallAccessClass);
}
