#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import yaml


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("CHUMMER_ARTIFACT_FACTORY_ROOT", DEFAULT_ROOT))
QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_ARTIFACT_FACTORY_QUEUE_STAGING",
        "/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
DESIGN_QUEUE_STAGING_PATH = Path(
    os.environ.get(
        "CHUMMER_ARTIFACT_FACTORY_DESIGN_QUEUE_STAGING",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml",
    )
)
SUCCESSOR_REGISTRY_PATH = Path(
    os.environ.get(
        "CHUMMER_ARTIFACT_FACTORY_SUCCESSOR_REGISTRY",
        "/docker/chummercomplete/chummer-design/products/chummer/NEXT_90_DAY_PRODUCT_ADVANCE_REGISTRY.yaml",
    )
)

SOURCE_MARKERS: dict[str, list[str]] = {
    "scripts/verify_artifact_factory_orchestration.py": [
        "CHUMMER_ARTIFACT_FACTORY_DESIGN_QUEUE_STAGING",
        "DESIGN_QUEUE_STAGING_PATH",
        '"frontier_id": 1421219975',
        '"wave": "W9"',
        '"completion_action": "verify_closed_package_only"',
        '"do_not_reopen_reason": DO_NOT_REOPEN_REASON',
        "verify_queue_authority(missing, queue_path)",
        "queue staging must contain exactly one package_id",
        "successor registry must contain exactly one milestone",
        "successor registry must contain exactly one work task",
        "verify_queue_mirror_alignment(missing, queue_paths)",
        "queue mirror drift",
        "FORBIDDEN_PROOF_MARKERS",
        "reject_forbidden_proof_markers(",
        "item_lower = item.lower()",
        "marker.lower() in item_lower",
    ],
    "scripts/ai/verify.sh": [
        "python3 scripts/verify_artifact_factory_orchestration.py",
        "python3 -m unittest tests/test_artifact_factory_orchestration.py",
        "python3 -m unittest tests/test_artifact_factory_source_pack_launcher.py",
    ],
    "scripts/launch_artifact_factory_source_pack_batch.py": [
        'DEFAULT_BATCH_PATH = "/api/internal/artifact-factory/source-pack-batches"',
        'DEFAULT_RECIPES_PATH = "/api/internal/artifact-factory/recipes"',
        'EXPECTED_CONTRACT_NAME = "chummer.run.artifact_factory.recipe_job.v1"',
        'EXPECTED_RECIPE_VERSION = "2026-04-15"',
        "load_recipe_catalog(base_url, args.token, args.public_host, args.forwarded_proto)",
        "validate_recipe_catalog_contract(response)",
        "def validate_recipe_catalog_contract(response: Any) -> None:",
        "artifact-factory recipe catalog response contractName must stay",
        "artifact-factory recipe catalog response recipeVersion must stay",
        "payload = normalize_launch_payload(read_request_payload(args.request_file), recipe_catalog)",
        "validate_batch_launch_response(response, recipe_catalog, payload)",
        "def validate_batch_launch_response(",
        "artifact-factory source-pack batch response contractName must match the recipe catalog contractName.",
        "artifact-factory source-pack batch response recipeVersion must match the recipe catalog recipeVersion.",
        "artifact-factory source-pack batch response must include a non-empty state.",
        'required_families = normalize_string_list(response.get("requiredFamilies"), "requiredFamilies")',
        'expected_required_families = normalize_string_list(',
        "artifact-factory source-pack batch response requiredFamilies must match the launch request requiredFamilies.",
        'families = normalize_string_list(response.get("families"), "families")',
        "artifact-factory source-pack batch response families must match the launch request requiredFamilies.",
        'source_pack_ids = normalize_string_list(response.get("sourcePackIds"), "sourcePackIds")',
        "expected_source_pack_ids_for_families(",
        "artifact-factory source-pack batch response sourcePackIds must match the launch request source packs for the requested recipe families.",
        'recipe_ids = normalize_string_list(response.get("recipeIds"), "recipeIds")',
        "artifact-factory source-pack batch response recipeIds must include at least one non-empty recipe id.",
        'expected_recipe_ids = sorted(',
        'and recipe.get("family", "").strip().replace("-", "_").lower() in expected_required_families',
        "artifact-factory source-pack batch response recipeIds must match the launch request requiredFamilies.",
        "artifact-factory source-pack batch response jobCount must be a positive integer.",
        "artifact-factory source-pack batch response jobs length must match jobCount.",
        "artifact-factory source-pack batch response mediaFactoryRequests length must match jobCount.",
        "artifact-factory source-pack batch response jobIds length must match jobCount.",
        "artifact-factory source-pack batch response jobCount must match the launch request requiredFamilies.",
        "validate_job_response_shape(response, expected_required_families, job_ids)",
        "def validate_job_response_shape(",
        "artifact-factory source-pack batch response jobs jobId values must match response jobIds.",
        "artifact-factory source-pack batch response jobs family values must match the launch request requiredFamilies.",
        "def normalize_job_field_list(jobs: list[Any], field_name: str, label: str) -> list[str]:",
        "artifact-factory source-pack batch response jobs must only contain objects.",
        "artifact-factory source-pack batch response {label} values must be non-empty strings.",
        "def normalize_string_list(value: Any, field_name: str) -> list[str]:",
        "artifact-factory source-pack batch response {field_name} must be a non-empty array of strings.",
        "artifact-factory source-pack batch response {field_name} must only contain non-empty strings.",
        "recipe_can_launch_from_source_packs(family, recipe, source_packs)",
        "if not recipe_can_launch_from_source_packs(family, recipe_map[family], source_packs)",
        "artifact-factory source-pack batch request sourcePacks must already be approved.",
        "PROVIDER_SPECIFIC_REF_PREFIXES",
        "validate_source_pack_refs(source_pack)",
        "def validate_source_pack_refs(source_pack: dict[str, Any]) -> None:",
        "validate_campaign_public_shelf_ref(source_pack, family)",
        "def validate_campaign_public_shelf_ref(source_pack: dict[str, Any], family: str) -> None:",
        "def campaign_surface_shelf_ref_is_allowed(public_shelf_ref: str, expected_prefix: str, expected_surface: str) -> bool:",
        "must resolve to {expected_prefix}{{id}}/{expected_surface} for audience-safe campaign artifact requests.",
        "def reject_provider_specific_ref(source_pack_id: str, value: str, field_name: str) -> None:",
        "def reject_non_local_public_shelf_ref(source_pack_id: str, value: str, field_name: str) -> None:",
        "jobs must launch from approved source-pack receipts instead of one-off provider flows.",
        "artifact factory output refs must stay on the Chummer public proof shelf.",
        "artifact-factory source-pack batch request requestedFormats contains family",
    ],
    "tests/test_artifact_factory_source_pack_launcher.py": [
        '"/api/internal/artifact-factory/recipes": "GET"',
        '"/api/internal/artifact-factory/source-pack-batches": "POST"',
        '"recipeId": "release-proof-shelf-bundle"',
        '"requiredFamilies": ["release"]',
        '"host": "chummer.run"',
        '"forwarded_proto": "https"',
        'self.assertEqual(1, len(_RecordingHandler.requests))',
        '"no approved source packs for required recipe family/families: release"',
        "test_fails_when_recipe_catalog_contract_drifts",
        "test_fails_when_batch_response_contract_drifts_from_recipe_catalog",
        "test_fails_when_batch_response_required_families_drift_from_request",
        "test_fails_when_batch_response_source_pack_ids_drift_from_request",
        "test_fails_when_batch_response_recipe_ids_drift_from_required_families",
        "test_fails_when_batch_response_job_ids_drift_from_jobs",
        "test_fails_when_batch_response_job_families_drift_from_request",
        '"contractName": "chummer.run.artifact_factory.recipe_job.v2"',
        '"must match the recipe catalog"',
        '"launch request requiredFamilies"',
        '"requested recipe families"',
        "test_accepts_family_scoped_source_pack_ids_when_request_contains_extra_approved_packs",
        '"jobs jobId values must match response jobIds"',
        '"jobs family values must match the launch request requiredFamilies"',
        '"support-case-proof-packet"',
        "test_fails_provider_specific_source_pack_refs_before_launch",
        "test_fails_external_public_shelf_evidence_before_launch",
        "test_fails_campaign_briefing_preflight_when_public_shelf_skips_surface",
        "provider-specific provenanceRef",
        "non-local public proof shelf evidenceRef",
        '"/artifacts/campaigns/{id}/cold-open"',
    ],
    "Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs": [
        'private const string ContractName = "chummer.run.artifact_factory.recipe_job.v1";',
        "public sealed record ArtifactFactoryRecipeCatalogResult(",
        "public sealed record ArtifactFactoryRecipeDefinition(",
        "public ArtifactFactoryRecipeCatalogResult ListRecipes()",
        "new ArtifactFactoryRecipeDefinition(",
        "RequiredAnchorDescription: item.Value.RequiredAnchorDescription",
        "public sealed record ArtifactFactoryJobBatchLaunchRequest(",
        "IReadOnlyList<string>? RequiredFamilies = null",
        "public sealed record ArtifactFactorySourcePackBatchLaunchRequest(",
        "public sealed record ArtifactFactoryFamilyFormatOverride(",
        "IReadOnlyList<ApprovedArtifactSourcePack> SourcePacks,",
        "public sealed record ArtifactFactoryJobBatchLaunchResult(",
        "IReadOnlyList<string> RequiredFamilies,",
        "public ArtifactFactoryJobBatchLaunchResult LaunchJobs(ArtifactFactoryJobBatchLaunchRequest request)",
        "public ArtifactFactoryJobBatchLaunchResult LaunchSourcePackBatch(ArtifactFactorySourcePackBatchLaunchRequest request)",
        "source-pack batchId is required.",
        "RejectUnsafeBatchId(request.BatchId);",
        "ValidateSourcePackBatchSourcePacks(request.SourcePacks)",
        "BuildJobFromApprovedSourcePackBatch(request, family, requestedFormatsByFamily)",
        "SourcePackCanFeedRecipe(sourcePack, recipe)",
        "private static void ValidateSourcePackBatchSourcePacks(IReadOnlyList<ApprovedArtifactSourcePack> sourcePacks)",
        "artifact factory source-pack batch contains an empty approved source pack.",
        "sourcePackId is required for every source-pack batch pack.",
        "duplicate source pack id '{normalizedSourcePackId}' is not allowed in source-pack batch.",
        "source pack '{normalizedSourcePackId}' is not approved for source-pack batch launch.",
        "RejectProviderSpecificRef(normalizedSourcePackId, evidenceRef, \"evidenceRef\");",
        "RejectNonLocalPublicShelfEvidenceRef(normalizedSourcePackId, evidenceRef);",
        "NormalizeFamilyFormatOverrides(request.RequestedFormats)",
        "RejectRequestedFormatOverridesOutsideRequiredFamilies(request.BatchId, requestedFormatsByFamily, requiredFamilies)",
        "private static void RejectRequestedFormatOverridesOutsideRequiredFamilies(",
        "requested formats for family/families not required by the batch",
        "artifact factory source-pack batch '{request.BatchId.Trim()}' has no approved source packs matching required recipe family",
        "string[] requiredFamilies = NormalizeRequiredBatchFamilies(request.RequiredFamilies);",
        "missing required recipe family job(s)",
        "RequiredFamilies: requiredFamilies,",
        "private static string[] NormalizeRequiredBatchFamilies(IReadOnlyList<string>? requiredFamilies)",
        "return Recipes.Keys",
        ".Where(static family => DefaultBatchFamilies.Contains(family))",
        ".Order(StringComparer.OrdinalIgnoreCase)",
        '["campaign_cold_open"] = new(',
        'RecipeId: "campaign-cold-open-bundle"',
        'RequiredReceiptPrefixes: ["campaign", "primer", "audience", "locale"]',
        '["mission_briefing"] = new(',
        'RecipeId: "mission-briefing-reel"',
        'RequiredReceiptPrefixes: ["mission", "briefing", "audience", "locale"]',
        "artifact factory batch required recipe families cannot be empty.",
        'RejectProviderSpecificRef("batch-request", family, "requiredFamily");',
        'RejectUnsafeJobToken(family, "requiredFamily", allowComma: false);',
        "artifact factory batch requires unsupported recipe family",
        "ArtifactFactoryJobLaunchRequest normalizedRequest;",
        "if (string.IsNullOrWhiteSpace(jobRequest.RequestedBy))",
        "jobRequest with { RequestedBy = requestedBy }",
        "string jobRequestedBy = NormalizeRequestedBy(jobRequest.RequestedBy);",
        "job requestedBy '{jobRequestedBy}' must match batch requestedBy '{requestedBy}'.",
        "jobRequest with { RequestedBy = jobRequestedBy }",
        "string requestedBy = NormalizeRequestedBy(request.RequestedBy);",
        'throw new InvalidDataException($"duplicate artifact factory job \'{job.JobId}\' is not allowed in batch \'{request.BatchId.Trim()}\'.");',
        "IReadOnlyList<string> RecipeIds,",
        "string[] recipeIds = jobs",
        ".Select(static job => job.RecipeId)",
        "IReadOnlyList<string> SourcePackIds,",
        "string[] sourcePackIds = jobs",
        ".SelectMany(static job => job.SourcePackIds)",
        "ArtifactFactoryJobLaunchResult[] orderedJobs = jobs",
        "JobIds: orderedJobs.Select(static job => job.JobId).ToArray()",
        "RecipeIds: recipeIds,",
        "SourcePackIds: sourcePackIds,",
        "Jobs: orderedJobs,",
        "MediaFactoryRequests: orderedJobs.Select(static job => job.MediaFactoryRequest).ToArray())",
        "private static void RejectUnsafeBatchId(string batchId)",
        "batch ids must be stable orchestration receipt ids, not provider paths.",
        "batch ids must not contain traversal, encoded provider delimiters, or encoded path separators.",
        "batch ids must use stable orchestration receipt segment characters.",
        "string audience = NormalizeAudience(request.Audience);",
        "string locale = NormalizeLocale(request.Locale);",
        "private static string NormalizeAudience(string? value)",
        "private static string NormalizeRequestedBy(string? value)",
        "private static string NormalizeLocale(string? value)",
        'RejectProviderSpecificRef("job-request", audience, "audience");',
        'RejectProviderSpecificRef("job-request", requestedBy, "requestedBy");',
        'RejectProviderSpecificRef("job-request", locale, "locale");',
        'RejectProviderSpecificRef("job-request", format, "outputFormat");',
        'RejectUnsafeJobToken(requestedBy, "requestedBy", allowComma: false);',
        'RejectUnsafeJobToken(format, "outputFormat", allowComma: false);',
        "private static void RejectUnsafeJobToken(string value, string fieldName, bool allowComma)",
        "ProviderSpecificRefPrefixes.Contains(normalized)",
        "!IsExternalPublicShelfEvidenceRef(normalized, fieldName) && ContainsProviderSpecificToken(normalized)",
        "private static bool ContainsProviderSpecificToken(string normalized)",
        "private static bool IsExternalPublicShelfEvidenceRef(string normalized, string fieldName)",
        "private static bool ContainsDelimitedToken(string value, string token)",
        "private static bool IsProviderTokenBoundary(string value, int index)",
        "job metadata must be stable source-pack tokens, not provider paths or URIs.",
        "job metadata must not contain traversal or encoded path separators.",
        "job metadata must use stable token characters.",
        '["release"] = new(',
        'RecipeId: "release-proof-shelf-bundle"',
        '["fix"] = new(',
        'RecipeId: "fix-followthrough-bundle"',
        '["support"] = new(',
        'RecipeId: "support-case-proof-packet"',
        '["publication"] = new(',
        'RecipeId: "publication-proof-shelf-bundle"',
        'RequiredReceiptPrefixes: ["release", "promotion", "public-shelf"]',
        'RequiredReceiptPrefixes: ["fix", "install", "support"]',
        'RequiredReceiptPrefixes: ["support", "privacy", "install"]',
        'RequiredReceiptPrefixes: ["publication", "moderation", "public-shelf"]',
        "ReceiptRefMatchesRequiredPrefix(receipt, prefix)",
        "private static bool ReceiptRefMatchesRequiredPrefix(string receiptRef, string requiredPrefix)",
        'normalizedReceiptRef.StartsWith($"{requiredPrefix}:", StringComparison.OrdinalIgnoreCase)',
        'RejectProviderSpecificRef(sourcePack.SourcePackId, evidenceRef, "evidenceRef");',
        'RejectNonLocalPublicShelfRef(sourcePack.SourcePackId, sourcePack.PublicShelfRef, "publicShelfRef");',
        'RejectPublicShelfRefOutsideRecipeRoutes(sourcePack.SourcePackId, family, sourcePack.PublicShelfRef, "publicShelfRef");',
        'RejectNonLocalPublicShelfEvidenceRef(sourcePack.SourcePackId, evidenceRef);',
        'RejectPublicShelfEvidenceRefOutsideRecipeRoutes(sourcePack.SourcePackId, family, evidenceRef);',
        "string normalizedSourcePackId = sourcePack.SourcePackId.Trim();",
        "if (!sourcePackIds.Add(normalizedSourcePackId))",
        'throw new InvalidDataException("artifact factory job contains an empty approved source pack.");',
        'throw new InvalidDataException($"duplicate source pack id \'{normalizedSourcePackId}\' is not allowed.");',
        "SourcePackId: normalizedSourcePackId,",
        "private static int FirstRefPrefixSeparatorIndex(string normalized)",
        "int slashIndex = normalized.IndexOf('/');",
        "if (IsAbsoluteHttpRef(normalized) || IsUriLikeExternalRef(normalized, fieldName))",
        "external absolute URI",
        "private static bool IsAbsoluteHttpRef(string normalized)",
        "Uri.TryCreate(normalized, UriKind.Absolute, out Uri? uri)",
        "uri.Scheme.Equals(Uri.UriSchemeHttp, StringComparison.OrdinalIgnoreCase)",
        "uri.Scheme.Equals(Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase)",
        "private static bool IsUriLikeExternalRef(string normalized, string fieldName)",
        "private static bool IsPublicShelfEvidenceRef(string normalized, string fieldName)",
        '!IsPublicShelfEvidenceRef(normalized, fieldName)',
        'normalized.StartsWith("public-shelf:", StringComparison.OrdinalIgnoreCase)',
        'normalized.Contains("://", StringComparison.Ordinal)',
        "private static void RejectPublicShelfRefOutsideRecipeRoutes(string sourcePackId, string family, string value, string fieldName)",
        "private static void RejectUnsafePublicShelfRef(string sourcePackId, string publicShelfRef, string fieldName)",
        "RejectUnsafePublicPathId(sourcePack.SourcePackId, sourcePack.ReleaseArtifactId, \"releaseArtifactId\");",
        "RejectUnsafePublicPathId(sourcePack.SourcePackId, sourcePack.SupportCaseId, \"supportCaseId\");",
        "RejectUnsafePublicPathId(sourcePack.SourcePackId, sourcePack.PublicationId, \"publicationId\");",
        "RejectProviderSpecificRef(sourcePack.SourcePackId, sourcePack.SourcePackId, \"sourcePackId\");",
        "RejectUnsafeSourcePackId(sourcePack.SourcePackId);",
        "private static void RejectUnsafeSourcePackId(string sourcePackId)",
        "approved source-pack ids must be stable receipt ids, not provider paths.",
        "approved source-pack ids must not contain traversal, encoded provider delimiters, or encoded path separators.",
        "approved source-pack ids must use stable receipt segment characters.",
        "private static void RejectUnsafePublicPathId(string sourcePackId, string? value, string fieldName)",
        "RejectProviderSpecificRef(sourcePackId, value, fieldName);",
        "RejectProviderSpecificRef(sourcePackId, value, fieldName);\n\n        string pathId = value.Trim();",
        "artifact factory path ids must be stable public proof shelf segments.",
        "artifact factory path ids must not contain traversal, encoded provider delimiters, or encoded path separators.",
        "artifact factory path ids must use stable public proof shelf segment characters.",
        "artifact factory bundle refs must be stable shelf paths without query strings or fragments.",
        "artifact factory bundle refs must not contain traversal or encoded path separators.",
        "artifact factory bundle refs must use stable public proof shelf segment characters.",
        "private static bool IsStablePublicShelfSegment(string value)",
        "character is '-' or '_' or '.'",
        '"/downloads/install/", "/artifacts/release-bundles/"',
        "RejectRecipeShelfAnchorShape(sourcePackId, family, publicShelfRef, fieldName);",
        "private static void RejectRecipeShelfAnchorShape(string sourcePackId, string family, string publicShelfRef, string fieldName)",
        "private static void RejectReleaseBundleShelfAnchorShape(string sourcePackId, string publicShelfRef, string fieldName)",
        "release bundle anchors must resolve to exactly one release artifact segment.",
        "publication bundle anchors must resolve to one publication segment with an optional bundles shelf.",
        "support bundle anchors must resolve to exactly one support case segment.",
        "fix bundle anchors must resolve to exactly one support case or release artifact segment.",
        'HasResourceSurfaceShelfAnchorShape(publicShelfRef, "/artifacts/campaigns/", "cold-open", allowBundlesSuffix: true)',
        'HasResourceSurfaceShelfAnchorShape(publicShelfRef, "/artifacts/missions/", "briefing", allowBundlesSuffix: true)',
        "campaign cold-open anchors must resolve to /artifacts/campaigns/{{campaignId}}/cold-open with an optional bundles shelf.",
        "mission briefing anchors must resolve to /artifacts/missions/{{missionId}}/briefing with an optional bundles shelf.",
        "private static bool HasAnyResourceShelfAnchorShape(string publicShelfRef, IReadOnlyList<string> prefixes, bool allowBundlesSuffix)",
        "private static bool HasResourceShelfAnchorShape(string publicShelfRef, string prefix, bool allowBundlesSuffix)",
        "private static bool HasResourceSurfaceShelfAnchorShape(string publicShelfRef, string prefix, string surfaceSegment, bool allowBundlesSuffix)",
        '"/account/support/", "/account/support-packets/"',
        '"/artifacts/publications/"',
        "outside recipe {family} shelf routes",
        "artifact factory output refs must stay on the Chummer public proof shelf.",
        'artifact factory jobs must launch from approved source-pack receipts instead of one-off provider flows.',
        "private static ArtifactFactoryMediaSourcePack SelectOutputAnchor(",
        '"release" => !string.IsNullOrWhiteSpace(pack.ReleaseArtifactId)',
        '|| !string.IsNullOrWhiteSpace(pack.PublicShelfRef),',
        'return $"/artifacts/release-bundles/{Uri.EscapeDataString(anchor.ReleaseArtifactId)}";',
        'return $"/account/{supportPath}/{Uri.EscapeDataString(anchor.SupportCaseId)}";',
        'return $"/artifacts/publications/{Uri.EscapeDataString(anchor.PublicationId)}/bundles";',
        "publicProofShelfRefs.AddRange(BuildOutputShelfRefs(outputBindings));",
        "private static IEnumerable<string> BuildOutputShelfRefs(IReadOnlyList<ArtifactFactoryOutputBinding> outputBindings)",
        "yield return binding.PublicRef[..separatorIndex];",
        'string shelfRef = anchor.PublicShelfRef.Trim().TrimEnd(\'/\');',
        '&& TryBuildReleaseBundleRefFromDownloadShelfRef(shelfRef, out string? releaseBundleRef)',
        '&& shelfRef.StartsWith("/artifacts/release-bundles/", StringComparison.OrdinalIgnoreCase)',
        "private static bool TryBuildReleaseBundleRefFromDownloadShelfRef(string shelfRef, out string releaseBundleRef)",
        'const string downloadInstallPrefix = "/downloads/install/";',
        'return shelfRef.EndsWith("/bundles", StringComparison.OrdinalIgnoreCase)',
    ],
    "Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs": [
        '[HttpGet("/api/internal/artifact-factory/recipes")]',
        "ListRecipes()",
        "ArtifactFactoryRecipeCatalogResult",
        "return Ok(_orchestration.ListRecipes());",
        '[HttpPost("/api/internal/artifact-factory/jobs")]',
        '[HttpPost("/api/internal/artifact-factory/job-batches")]',
        "LaunchJobBatch([FromBody] ArtifactFactoryJobBatchLaunchRequest? request)",
        '[HttpPost("/api/internal/artifact-factory/source-pack-batches")]',
        "LaunchSourcePackBatch([FromBody] ArtifactFactorySourcePackBatchLaunchRequest? request)",
        "https://chummer.run/problems/artifact-factory/source-pack-batch-rejected",
        "Artifact factory batch rejected",
        "https://chummer.run/problems/artifact-factory/batch-rejected",
        "RequireInternalAutomationAuth();",
        '"FLEET_INTERNAL_API_TOKEN"',
        "CryptographicOperations.FixedTimeEquals",
        'https://chummer.run/problems/artifact-factory/rejected',
    ],
    "Chummer.Run.Api/Controllers/PublicLandingController.cs": [
        '[HttpGet("/artifacts/release-bundles/{releaseArtifactId}")]',
        '[HttpGet("/artifacts/release-bundles/{releaseArtifactId}/{format}")]',
        "ReleaseArtifactBundleProof([FromRoute] string releaseArtifactId)",
        "ReleaseArtifactBundleOutputProof([FromRoute] string releaseArtifactId, [FromRoute] string format)",
        "BuildReleaseArtifactBundleProof(releaseArtifactId, requestedFormat: null)",
        "BuildReleaseArtifactBundleProof(releaseArtifactId, format)",
        'contractName = "chummer.run.public_proof_shelf.release_bundle.v1"',
        "publicProofShelfRef = normalizedFormat is null ? bundleRef : outputRefs[normalizedFormat]",
        'canonicalInstallRef = installRef',
        'requiredReceiptRefs = new[]',
        '$"public-shelf:{bundleRef}"',
        'private static string? NormalizeArtifactFactoryOutputFormat(string? format)',
        'format.Trim().Replace(\'-\', \'_\').ToLowerInvariant()',
    ],
    "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs": [
        "public static IServiceCollection AddHubInstallAndOrchestrationAdapters(this IServiceCollection services)",
        "services.AddSingleton<ArtifactFactoryOrchestrationService>();",
    ],
    "Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs": [
        "ListRecipesPublishesApprovedSourcePackContractsForEveryFamily",
        "ControllerListRecipesRequiresInternalToken",
        "ControllerListRecipesReturnsApprovedRecipeCatalog",
        "LaunchJobBuildsReleaseRecipeFromApprovedSourcePacks",
        "LaunchJobBuildsPublicationProofShelfRoute",
        "LaunchJobBindsOutputsToApprovedAnchoredPackWhenSourcePacksAreMixed",
        "LaunchJobBuildsSupportAndFixJobsFromAnchoredApprovedPacks",
        "LaunchJobBatchDefaultsToCompleteSuccessorRecipeSet",
        "LaunchJobBatchRejectsPartialWaveWhenRequiredFamiliesAreOmitted",
        "LaunchJobBatchRejectsExplicitBlankRequiredFamilies",
        "LaunchSourcePackBatchRejectsMissingBatchIdBeforeSourcePackSelection",
        "LaunchSourcePackBatchBuildsRequiredRecipeJobsFromApprovedSourcePacks",
        "LaunchSourcePackBatchRejectsFormatOverridesOutsideRequiredFamilies",
        "LaunchSourcePackBatchRejectsDuplicatePackIdsBeforeFamilySelection",
        "LaunchSourcePackBatchRejectsProviderRefsBeforeFamilySelection",
        "ControllerLaunchSourcePackBatchReturnsRecipeJobs",
        "next90-m107-artifact-factory-wave",
        "next90-m107-source-pack-wave",
        "next90-m107-source-pack-controller",
        "next90-m107-artifact-factory-partial",
        "next90-m107-artifact-factory-blank-families",
        'Assert.Equal(["campaign_cold_open", "fix", "mission_briefing", "publication", "release", "support"], catalog.Recipes.Select(recipe => recipe.Family).ToArray());',
        'Assert.Equal(["fix", "publication", "release", "support"], result.RequiredFamilies);',
        'string.Equals(recipe.Family, "campaign_cold_open", StringComparison.Ordinal)',
        'string.Equals(recipe.RecipeId, "campaign-cold-open-bundle", StringComparison.Ordinal)',
        'string.Equals(recipe.Family, "mission_briefing", StringComparison.Ordinal)',
        'string.Equals(recipe.RecipeId, "mission-briefing-reel", StringComparison.Ordinal)',
        'Assert.Equal(["release-proof-shelf-bundle"], result.RecipeIds);',
        "LaunchJobRejectsDuplicateSourcePackIds",
        "LaunchJobRejectsWhitespacePaddedDuplicateSourcePackIds",
        "LaunchJobBindsReleaseOutputsToApprovedPublicShelfRefWhenArtifactIdIsAbsent",
        "LaunchJobBindsReleaseDownloadShelfAnchorToReleaseBundleShelf",
        "LaunchJobBindsPublicationOutputsToApprovedPublicShelfRefWhenPublicationIdIsAbsent",
        "ControllerLaunchJobRequiresInternalToken",
        "LaunchJobRejectsExternalAbsoluteEvidenceRefs",
        "LaunchJobRejectsNonHttpUriLikeEvidenceRefs",
        "LaunchJobRejectsUriLikeProvenanceRefs",
        "LaunchJobRejectsProviderSpecificEvidenceRefs",
        "LaunchJobRejectsProviderSpecificSlashEvidenceRefs",
        "LaunchJobRejectsProviderSpecificTokenizedSourcePackIds",
        "LaunchJobRejectsProviderSpecificOutputFormats",
        "LaunchJobRejectsProviderSpecificRequestedByTokens",
        'Assert.Contains("provider-specific outputFormat", ex.Message, StringComparison.OrdinalIgnoreCase);',
        'Assert.Contains("one-off provider flows", ex.Message, StringComparison.OrdinalIgnoreCase);',
        "LaunchJobRejectsExternalPublicShelfRefs",
        "LaunchJobRejectsExternalPublicShelfEvidenceRefs",
        "LaunchJobRejectsProviderSpecificPublicShelfEvidenceRefs",
        "LaunchJobRejectsCrossRecipePublicShelfRefs",
        "LaunchJobRejectsCrossRecipePublicShelfEvidenceRefs",
        "LaunchJobRejectsUnsafePublicShelfRefs",
        "LaunchJobRejectsUnsafePublicShelfEvidenceRefs",
        "LaunchJobRejectsUnsafeReleaseArtifactPathIds",
        "LaunchJobRejectsEncodedSeparatorInPublicationPathIds",
        "LaunchJobRejectsRecipeWhenApprovedPackLacksRequiredReceiptEvidence",
        'Assert.Equal("chummer.run.artifact_factory.recipe_job.v1", result.MediaFactoryRequest.ContractName);',
        'string.Equals(binding.PublicRef, "/artifacts/release-bundles/avalonia-osx-arm64-installer/preview_card", StringComparison.Ordinal)',
        'Assert.Contains("/account/support/11709", support.PublicProofShelfRefs);',
        'Assert.Contains("/account/support/11709", fix.MediaFactoryRequest.PublicProofShelfRefs);',
        'Assert.Contains("/account/fix-followthrough/11709", fix.PublicProofShelfRefs);',
        'Assert.Contains("/account/fix-followthrough/11709", fix.MediaFactoryRequest.PublicProofShelfRefs);',
        'Assert.Contains("/artifacts/release-bundles/avalonia-osx-arm64-installer", result.MediaFactoryRequest.PublicProofShelfRefs);',
        'Assert.Contains("/artifacts/release-bundles/avalonia-linux-x64-installer", result.MediaFactoryRequest.PublicProofShelfRefs);',
    ],
    "tests/test_artifact_factory_orchestration.py": [
        "test_verifier_fails_closed_when_queue_package_is_duplicated",
        "test_verifier_fails_closed_when_structured_frontier_id_is_missing",
        "test_verifier_fails_closed_when_source_pack_batch_response_contract_guard_is_removed",
        "test_verifier_fails_closed_when_duplicate_source_pack_guard_is_removed",
        "test_verifier_fails_closed_when_normalized_duplicate_source_pack_guard_is_removed",
        "test_verifier_fails_closed_when_external_absolute_uri_guard_is_removed",
        "test_verifier_fails_closed_when_queue_guard_commit_pin_is_missing",
        "test_verifier_fails_closed_when_current_duplicate_queue_guard_proof_is_missing",
        "test_verifier_fails_closed_when_fleet_and_design_queue_rows_drift",
        "commit cfd5d208",
        "commit 60125d9e",
        "commit c98a49f2",
        "commit 28d3e13f",
        "commit 76b0c410",
        "commit e5e2e57f",
        "commit f0bdfcb9",
        "commit 66b1a1c7",
        "commit 51623cd3",
        "commit 2b8a9431",
        "commit a20aa910",
        "commit 7ce86602",
        "commit 326db197",
        "commit bd67b5ff",
        "commit 6851982b",
        "commit 5b901df5",
        "commit cbae3cdd",
        "commit f0142482",
        "commit a66a06bb",
        "commit 9a8e56f0",
        "commit a929cc7d",
        "commit ff3100b4",
        "commit 94f0c9e1",
        "commit f22ce5a5",
        "commit b15c2193",
        "commit 9b032c87",
        "commit f1ca6c1a",
        "commit a91ea733",
        "commit c31258fa",
        "commit 45d3d498",
        "commit c3aaf05a",
        "commit 285e97be",
        "commit ce1c6611",
        "commit 67ae7dab",
        "commit 65ac67a8",
        "commit e0121780",
        "commit 700343bc",
        "test_verifier_fails_closed_when_proof_commit_anchor_is_not_on_current_branch",
        "test_verifier_fails_closed_when_branch_guard_commit_pin_is_missing",
        "test_verifier_fails_closed_when_output_shelf_pin_commit_is_missing",
        "test_verifier_fails_closed_when_current_output_shelf_proof_pin_is_missing",
        "test_verifier_fails_closed_when_current_artifact_shelf_proof_floor_is_missing",
        "test_verifier_fails_closed_when_current_duplicate_queue_proof_guard_is_missing",
        "test_verifier_fails_closed_when_current_m107_guard_floor_is_missing",
        "test_verifier_fails_closed_when_source_pack_id_proof_pin_is_missing",
        "test_verifier_fails_closed_when_source_pack_stable_segment_guard_is_removed",
        "test_verifier_fails_closed_when_public_shelf_stable_segment_guard_is_removed",
        "test_verifier_fails_closed_when_batch_stable_segment_guard_is_removed",
        "test_verifier_fails_closed_when_artifact_path_id_guard_pin_is_missing",
        "test_verifier_fails_closed_when_artifact_path_guard_proof_pin_is_missing",
        "test_verifier_fails_closed_when_public_path_id_provider_guard_is_removed",
        "test_verifier_fails_closed_when_receipt_ref_guard_pin_is_missing",
        "test_verifier_fails_closed_when_receipt_prefix_boundary_guard_is_removed",
        "test_verifier_fails_closed_when_requested_by_guard_is_removed",
        "test_verifier_fails_closed_when_batch_requested_by_consistency_guard_is_removed",
        "test_verifier_fails_closed_when_batch_media_requests_are_not_sorted_with_jobs",
        "test_verifier_fails_closed_when_batch_required_families_guard_is_removed",
        "test_verifier_fails_closed_when_blank_required_families_guard_is_removed",
        "test_verifier_fails_closed_when_source_pack_batch_id_guard_is_removed",
        "test_verifier_fails_closed_when_source_pack_batch_preflight_guard_is_removed",
        "test_verifier_fails_closed_when_source_pack_batch_format_scope_guard_is_removed",
        "test_verifier_fails_closed_when_batch_required_families_result_is_removed",
        "test_verifier_fails_closed_when_release_bundle_anchor_shape_guard_is_removed",
        "test_verifier_fails_closed_when_non_release_shelf_anchor_shape_guard_is_removed",
        "test_verifier_fails_closed_when_latest_proof_floor_pin_is_missing",
        "test_verifier_fails_closed_when_current_proof_floor_pin_is_missing",
        "test_verifier_fails_closed_when_current_pinned_proof_floor_is_missing",
        "test_verifier_fails_closed_when_current_guard_floor_pin_is_missing",
        "test_verifier_fails_closed_when_refreshed_guard_floor_pin_is_missing",
        "test_verifier_fails_closed_when_latest_refreshed_guard_floor_pin_is_missing",
        "test_verifier_fails_closed_when_pinned_refreshed_proof_floor_is_missing",
        "test_verifier_fails_closed_when_external_uri_guard_proof_floor_is_missing",
        "test_verifier_fails_closed_when_current_format_scope_proof_floor_is_missing",
        "test_verifier_fails_closed_when_exact_provider_token_guard_is_removed",
        "test_verifier_fails_closed_when_provider_token_segment_guard_is_removed",
        "test_verifier_fails_closed_when_release_bundle_public_route_is_removed",
        "test_verifier_fails_closed_when_release_bundle_format_route_is_removed",
        "test_verifier_fails_closed_when_campaign_surface_shelf_shape_guard_is_removed",
        "HasResourceSurfaceShelfAnchorShape",
        "test_verifier_fails_closed_when_recipe_catalog_endpoint_is_removed",
        "test_verifier_fails_closed_when_recipe_catalog_contract_is_removed",
    ],
}

QUEUE_MARKERS = [
    "package_id: next90-m107-hub-artifact-factory",
    "milestone_id: 107",
    "status: complete",
    "landed_commit: b9e6b52e",
    "Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
    "Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
    "scripts/launch_artifact_factory_source_pack_batch.py",
    "tests/test_artifact_factory_source_pack_launcher.py",
    "python3 -m unittest tests/test_artifact_factory_source_pack_launcher.py",
    "dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
    "artifact_factory:orchestration",
    "public_proof_shelf:release_bundles",
    "/docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards",
    "/docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution",
    "/docker/chummercomplete/chummer6-hub commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof",
    "/docker/chummercomplete/chummer6-hub commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence",
    "/docker/chummercomplete/chummer6-hub commit 60125d9e tightens M107 artifact factory proof guard",
    "/docker/chummercomplete/chummer6-hub commit c98a49f2 tightens M107 artifact factory closeout proof",
    "/docker/chummercomplete/chummer6-hub commit 28d3e13f tightens M107 artifact factory closeout guard",
    "/docker/chummercomplete/chummer6-hub commit 76b0c410 tightens M107 artifact factory release-bundle output refs",
    "/docker/chummercomplete/chummer6-hub commit e5e2e57f tightens M107 artifact factory telemetry proof guard",
    "/docker/chummercomplete/chummer6-hub commit f0bdfcb9 tightens M107 artifact factory duplicate queue/package proof guard",
    "/docker/chummercomplete/chummer6-hub commit 66b1a1c7 tightens M107 artifact factory duplicate queue proof guard",
    "/docker/chummercomplete/chummer6-hub commit 51623cd3 pins M107 artifact factory duplicate queue guard proof",
    "/docker/chummercomplete/chummer6-hub commit 2b8a9431 tightens the current M107 duplicate queue proof guard",
    "/docker/chummercomplete/chummer6-hub commit a20aa910 tightens M107 artifact factory public shelf ref safety",
    "/docker/chummercomplete/chummer6-hub commit 7ce86602 pins M107 artifact factory shelf safety proof",
    "/docker/chummercomplete/chummer6-hub commit 326db197 tightens M107 artifact factory source-pack proof",
    "/docker/chummercomplete/chummer6-hub commit bd67b5ff tightens M107 artifact factory structured frontier proof",
    "/docker/chummercomplete/chummer6-hub commit 6851982b tightens M107 artifact factory proof hygiene",
    "/docker/chummercomplete/chummer6-hub commit 5b901df5 tightens M107 artifact factory proof branch guard",
    "/docker/chummercomplete/chummer6-hub commit cbae3cdd tightens M107 artifact factory output shelf proof",
    "/docker/chummercomplete/chummer6-hub commit f0142482 pins M107 artifact factory output shelf proof",
    "/docker/chummercomplete/chummer6-hub commit a66a06bb tightens M107 artifact output shelf proof pin",
    "/docker/chummercomplete/chummer6-hub commit 9a8e56f0 tightens M107 artifact shelf proof floor",
    "/docker/chummercomplete/chummer6-hub commit a929cc7d pins M107 artifact shelf proof floor",
    "/docker/chummercomplete/chummer6-hub commit ff3100b4 requires the current M107 artifact shelf proof floor",
    "/docker/chummercomplete/chummer6-hub commit 94f0c9e1 pins M107 current duplicate queue guard",
    "/docker/chummercomplete/chummer6-hub commit f22ce5a5 tightens M107 artifact factory source-pack id normalization",
    "/docker/chummercomplete/chummer6-hub commit b15c2193 pins M107 source pack id proof",
    "/docker/chummercomplete/chummer6-hub commit 9b032c87 tightens M107 artifact path id guards",
    "/docker/chummercomplete/chummer6-hub commit f1ca6c1a pins M107 artifact path guard proof",
    "/docker/chummercomplete/chummer6-hub commit a91ea733 tightens M107 artifact factory receipt refs",
    "/docker/chummercomplete/chummer6-hub commit c31258fa tightens M107 artifact factory proof floor",
    "/docker/chummercomplete/chummer6-hub commit 45d3d498 tightens M107 artifact factory proof floor",
    "/docker/chummercomplete/chummer6-hub commit c3aaf05a pins M107 artifact factory proof floor",
    "/docker/chummercomplete/chummer6-hub commit 285e97be tightens the current M107 artifact factory proof floor guard",
    "/docker/chummercomplete/chummer6-hub commit ce1c6611 pins M107 artifact factory proof floor guard",
    "/docker/chummercomplete/chummer6-hub commit 67ae7dab requires refreshed M107 proof floor",
    "/docker/chummercomplete/chummer6-hub commit 65ac67a8 pins M107 refreshed artifact factory proof floor",
    "/docker/chummercomplete/chummer6-hub commit e0121780 tightens M107 artifact factory external URI guard",
    "/docker/chummercomplete/chummer6-hub commit 9349395d tightens M107 source-pack batch preflight proof",
    "/docker/chummercomplete/chummer6-hub commit a7c54b30 tightens M107 source-pack batch format-scope proof",
    "/docker/chummercomplete/chummer6-hub commit 700343bc pins M107 format scope proof floor",
    "successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention",
]

SUCCESSOR_REGISTRY_MARKERS = [
    "program_wave: next_90_day_product_advance",
    "  - id: 107",
    "title: Artifact factory and public proof shelf",
    "      - id: 107.1",
    "owner: chummer6-hub",
    "title: Orchestrate recipe-backed artifact jobs from approved release, support, and publication packs.",
    "status: complete",
    "/docker/chummercomplete/chummer6-hub commit e25842ac tightens mixed source-pack output anchoring",
    "/docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards",
    "/docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution",
    "/docker/chummercomplete/chummer6-hub commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring",
    "/docker/chummercomplete/chummer6-hub commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence",
    "/docker/chummercomplete/chummer6-hub commit 60125d9e tightens M107 artifact factory proof guard",
    "/docker/chummercomplete/chummer6-hub commit c98a49f2 tightens M107 artifact factory closeout proof",
    "/docker/chummercomplete/chummer6-hub commit 28d3e13f tightens M107 artifact factory closeout guard",
    "/docker/chummercomplete/chummer6-hub commit 76b0c410 tightens M107 artifact factory release-bundle output refs",
    "/docker/chummercomplete/chummer6-hub commit f0bdfcb9 tightens M107 artifact factory duplicate queue/package proof guard",
    "/docker/chummercomplete/chummer6-hub commit 66b1a1c7 tightens M107 artifact factory duplicate queue proof guard",
    "/docker/chummercomplete/chummer6-hub commit 51623cd3 pins M107 artifact factory duplicate queue guard proof",
    "/docker/chummercomplete/chummer6-hub commit 2b8a9431 tightens the current M107 duplicate queue proof guard",
    "/docker/chummercomplete/chummer6-hub commit a20aa910 tightens M107 artifact factory public shelf ref safety",
    "/docker/chummercomplete/chummer6-hub commit 7ce86602 pins M107 artifact factory shelf safety proof",
    "/docker/chummercomplete/chummer6-hub commit 326db197 tightens M107 artifact factory source-pack proof",
    "/docker/chummercomplete/chummer6-hub commit bd67b5ff tightens M107 artifact factory structured frontier proof",
    "/docker/chummercomplete/chummer6-hub commit 5b901df5 tightens M107 artifact factory proof branch guard",
    "/docker/chummercomplete/chummer6-hub commit cbae3cdd tightens M107 artifact factory output shelf proof",
    "/docker/chummercomplete/chummer6-hub commit f0142482 pins M107 artifact factory output shelf proof",
    "/docker/chummercomplete/chummer6-hub commit a66a06bb tightens M107 artifact output shelf proof pin",
    "/docker/chummercomplete/chummer6-hub commit 9a8e56f0 tightens M107 artifact shelf proof floor",
    "/docker/chummercomplete/chummer6-hub commit a929cc7d pins M107 artifact shelf proof floor",
    "/docker/chummercomplete/chummer6-hub commit ff3100b4 requires the current M107 artifact shelf proof floor",
    "/docker/chummercomplete/chummer6-hub commit 94f0c9e1 pins M107 current duplicate queue guard",
    "/docker/chummercomplete/chummer6-hub commit f22ce5a5 tightens M107 artifact factory source-pack id normalization",
    "/docker/chummercomplete/chummer6-hub commit b15c2193 pins M107 source pack id proof",
    "/docker/chummercomplete/chummer6-hub commit 9b032c87 tightens M107 artifact path id guards",
    "/docker/chummercomplete/chummer6-hub commit f1ca6c1a pins M107 artifact path guard proof",
    "/docker/chummercomplete/chummer6-hub commit a91ea733 tightens M107 artifact factory receipt refs",
    "/docker/chummercomplete/chummer6-hub commit c31258fa tightens M107 artifact factory proof floor",
    "/docker/chummercomplete/chummer6-hub commit 45d3d498 tightens M107 artifact factory proof floor",
    "/docker/chummercomplete/chummer6-hub commit c3aaf05a pins M107 artifact factory proof floor",
    "/docker/chummercomplete/chummer6-hub commit 285e97be tightens the current M107 artifact factory proof floor guard",
    "/docker/chummercomplete/chummer6-hub commit ce1c6611 pins M107 artifact factory proof floor guard",
    "/docker/chummercomplete/chummer6-hub commit 65ac67a8 pins M107 refreshed artifact factory proof floor",
    "/docker/chummercomplete/chummer6-hub commit e0121780 tightens M107 artifact factory external URI guard",
    "/docker/chummercomplete/chummer6-hub commit 9349395d tightens M107 source-pack batch preflight proof",
    "/docker/chummercomplete/chummer6-hub commit a7c54b30 tightens M107 source-pack batch format-scope proof",
    "/docker/chummercomplete/chummer6-hub commit 700343bc pins M107 format scope proof floor",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs rejects unapproved or provider-specific source packs",
    "successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention",
    "/docker/chummercomplete/chummer6-hub/scripts/launch_artifact_factory_source_pack_batch.py preflights approved source-pack batches against the internal recipe catalog before launch.",
    "python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py exits 0.",
    "python3 -m unittest tests/test_artifact_factory_orchestration.py exits 0.",
    "python3 -m unittest tests/test_artifact_factory_source_pack_launcher.py exits 0.",
    "dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore exits 0.",
]

PACKAGE_ID = "next90-m107-hub-artifact-factory"
MILESTONE_ID = 107
WORK_TASK_ID = 107.1
DO_NOT_REOPEN_REASON = (
    "M107 chummer6-hub artifact factory orchestration is complete; future shards must verify this receipt, "
    "registry row, Fleet queue row, and design queue row instead of reopening the artifact-factory orchestration "
    "and public proof shelf release-bundles package."
)
REQUIRED_QUEUE_FIELDS = {
    "title": "Stand up artifact-factory orchestration for release, support, and publication bundles",
    "task": "Launch recipe-backed release, fix, support, and publication artifact jobs from approved source packs instead of one-off provider flows.",
    "wave": "W9",
    "repo": "chummer6-hub",
    "status": "complete",
    "landed_commit": "b9e6b52e",
    "frontier_id": 1421219975,
    "completion_action": "verify_closed_package_only",
    "do_not_reopen_reason": DO_NOT_REOPEN_REASON,
}
REQUIRED_ALLOWED_PATHS = {"Chummer.Run.Api", "scripts", "tests"}
REQUIRED_OWNED_SURFACES = {"artifact_factory:orchestration", "public_proof_shelf:release_bundles"}
QUEUE_MIRROR_FIELDS = (
    "title",
    "task",
    "package_id",
    "milestone_id",
    "wave",
    "repo",
    "status",
    "frontier_id",
    "landed_commit",
    "completion_action",
    "do_not_reopen_reason",
    "proof",
    "allowed_paths",
    "owned_surfaces",
)
REQUIRED_QUEUE_PROOF = {
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
    "/docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs",
    "/docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
    "/docker/chummercomplete/chummer6-hub/scripts/launch_artifact_factory_source_pack_batch.py",
    "/docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_source_pack_launcher.py",
    "python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py",
    "python3 -m unittest tests/test_artifact_factory_orchestration.py",
    "python3 -m unittest tests/test_artifact_factory_source_pack_launcher.py",
    "dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore",
    "/docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards.",
    "/docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution.",
    "/docker/chummercomplete/chummer6-hub commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
    "/docker/chummercomplete/chummer6-hub commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
    "/docker/chummercomplete/chummer6-hub commit 60125d9e tightens M107 artifact factory proof guard.",
    "/docker/chummercomplete/chummer6-hub commit c98a49f2 tightens M107 artifact factory closeout proof.",
    "/docker/chummercomplete/chummer6-hub commit 28d3e13f tightens M107 artifact factory closeout guard.",
    "/docker/chummercomplete/chummer6-hub commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
    "/docker/chummercomplete/chummer6-hub commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
    "/docker/chummercomplete/chummer6-hub commit f0bdfcb9 tightens M107 artifact factory duplicate queue/package proof guard.",
    "/docker/chummercomplete/chummer6-hub commit 66b1a1c7 tightens M107 artifact factory duplicate queue proof guard.",
    "/docker/chummercomplete/chummer6-hub commit 51623cd3 pins M107 artifact factory duplicate queue guard proof.",
    "/docker/chummercomplete/chummer6-hub commit 2b8a9431 tightens the current M107 duplicate queue proof guard.",
    "/docker/chummercomplete/chummer6-hub commit a20aa910 tightens M107 artifact factory public shelf ref safety.",
    "/docker/chummercomplete/chummer6-hub commit 7ce86602 pins M107 artifact factory shelf safety proof.",
    "/docker/chummercomplete/chummer6-hub commit 326db197 tightens M107 artifact factory source-pack proof.",
    "/docker/chummercomplete/chummer6-hub commit bd67b5ff tightens M107 artifact factory structured frontier proof.",
    "/docker/chummercomplete/chummer6-hub commit 6851982b tightens M107 artifact factory proof hygiene.",
    "/docker/chummercomplete/chummer6-hub commit 5b901df5 tightens M107 artifact factory proof branch guard.",
    "/docker/chummercomplete/chummer6-hub commit cbae3cdd tightens M107 artifact factory output shelf proof.",
    "/docker/chummercomplete/chummer6-hub commit f0142482 pins M107 artifact factory output shelf proof.",
    "/docker/chummercomplete/chummer6-hub commit a66a06bb tightens M107 artifact output shelf proof pin.",
    "/docker/chummercomplete/chummer6-hub commit 9a8e56f0 tightens M107 artifact shelf proof floor.",
    "/docker/chummercomplete/chummer6-hub commit a929cc7d pins M107 artifact shelf proof floor.",
    "/docker/chummercomplete/chummer6-hub commit ff3100b4 requires the current M107 artifact shelf proof floor.",
    "/docker/chummercomplete/chummer6-hub commit 94f0c9e1 pins M107 current duplicate queue guard.",
    "/docker/chummercomplete/chummer6-hub commit f22ce5a5 tightens M107 artifact factory source-pack id normalization.",
    "/docker/chummercomplete/chummer6-hub commit b15c2193 pins M107 source pack id proof.",
    "/docker/chummercomplete/chummer6-hub commit 9b032c87 tightens M107 artifact path id guards.",
    "/docker/chummercomplete/chummer6-hub commit f1ca6c1a pins M107 artifact path guard proof.",
    "/docker/chummercomplete/chummer6-hub commit a91ea733 tightens M107 artifact factory receipt refs.",
    "/docker/chummercomplete/chummer6-hub commit c31258fa tightens M107 artifact factory proof floor.",
    "/docker/chummercomplete/chummer6-hub commit 45d3d498 tightens M107 artifact factory proof floor.",
    "/docker/chummercomplete/chummer6-hub commit c3aaf05a pins M107 artifact factory proof floor.",
    "/docker/chummercomplete/chummer6-hub commit 285e97be tightens the current M107 artifact factory proof floor guard.",
    "/docker/chummercomplete/chummer6-hub commit ce1c6611 pins M107 artifact factory proof floor guard.",
    "/docker/chummercomplete/chummer6-hub commit 67ae7dab requires refreshed M107 proof floor.",
    "/docker/chummercomplete/chummer6-hub commit 65ac67a8 pins M107 refreshed artifact factory proof floor.",
    "/docker/chummercomplete/chummer6-hub commit e0121780 tightens M107 artifact factory external URI guard.",
    "/docker/chummercomplete/chummer6-hub commit 9349395d tightens M107 source-pack batch preflight proof.",
    "/docker/chummercomplete/chummer6-hub commit a7c54b30 tightens M107 source-pack batch format-scope proof.",
    "/docker/chummercomplete/chummer6-hub commit 700343bc pins M107 format scope proof floor.",
    "successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
}
REQUIRED_REGISTRY_EVIDENCE = {
    "/docker/chummercomplete/chummer6-hub commit cda8849a binds release, fix, support, and publication recipe jobs to stable public proof shelf output refs.",
    "/docker/chummercomplete/chummer6-hub commit e25842ac tightens mixed source-pack output anchoring so release bundle refs always bind to an approved artifact-bearing source pack.",
    "/docker/chummercomplete/chummer6-hub commit b9e6b52e tightens recipe-specific public proof shelf route guards so approved local refs cannot cross from release or publication recipes onto the wrong shelf family.",
    "/docker/chummercomplete/chummer6-hub commit 7331cd26 tightens artifact-factory queue and registry proof-anchor resolution so stale file or commit anchors cannot keep the completed package green.",
    "/docker/chummercomplete/chummer6-hub commit 0eac80b6 tightens design-owned queue source verification and standard Hub verify wiring for the M107 artifact-factory proof.",
    "/docker/chummercomplete/chummer6-hub commit cfd5d208 pins the completed M107 artifact-factory proof guard evidence.",
    "/docker/chummercomplete/chummer6-hub commit 60125d9e tightens M107 artifact factory proof guard.",
    "/docker/chummercomplete/chummer6-hub commit c98a49f2 tightens M107 artifact factory closeout proof.",
    "/docker/chummercomplete/chummer6-hub commit 28d3e13f tightens M107 artifact factory closeout guard.",
    "/docker/chummercomplete/chummer6-hub commit 76b0c410 tightens M107 artifact factory release-bundle output refs.",
    "/docker/chummercomplete/chummer6-hub commit e5e2e57f tightens M107 artifact factory telemetry proof guard.",
    "/docker/chummercomplete/chummer6-hub commit f0bdfcb9 tightens M107 artifact factory duplicate queue/package proof guard.",
    "/docker/chummercomplete/chummer6-hub commit 66b1a1c7 tightens M107 artifact factory duplicate queue proof guard.",
    "/docker/chummercomplete/chummer6-hub commit 51623cd3 pins M107 artifact factory duplicate queue guard proof.",
    "/docker/chummercomplete/chummer6-hub commit 2b8a9431 tightens the current M107 duplicate queue proof guard.",
    "/docker/chummercomplete/chummer6-hub commit a20aa910 tightens M107 artifact factory public shelf ref safety.",
    "/docker/chummercomplete/chummer6-hub commit 7ce86602 pins M107 artifact factory shelf safety proof.",
    "/docker/chummercomplete/chummer6-hub commit 326db197 tightens M107 artifact factory source-pack proof.",
    "/docker/chummercomplete/chummer6-hub commit bd67b5ff tightens M107 artifact factory structured frontier proof.",
    "/docker/chummercomplete/chummer6-hub commit 6851982b tightens M107 artifact factory proof hygiene.",
    "/docker/chummercomplete/chummer6-hub commit 5b901df5 tightens M107 artifact factory proof branch guard.",
    "/docker/chummercomplete/chummer6-hub commit cbae3cdd tightens M107 artifact factory output shelf proof.",
    "/docker/chummercomplete/chummer6-hub commit f0142482 pins M107 artifact factory output shelf proof.",
    "/docker/chummercomplete/chummer6-hub commit a66a06bb tightens M107 artifact output shelf proof pin.",
    "/docker/chummercomplete/chummer6-hub commit 9a8e56f0 tightens M107 artifact shelf proof floor.",
    "/docker/chummercomplete/chummer6-hub commit a929cc7d pins M107 artifact shelf proof floor.",
    "/docker/chummercomplete/chummer6-hub commit ff3100b4 requires the current M107 artifact shelf proof floor.",
    "/docker/chummercomplete/chummer6-hub commit 94f0c9e1 pins M107 current duplicate queue guard.",
    "/docker/chummercomplete/chummer6-hub commit f22ce5a5 tightens M107 artifact factory source-pack id normalization.",
    "/docker/chummercomplete/chummer6-hub commit b15c2193 pins M107 source pack id proof.",
    "/docker/chummercomplete/chummer6-hub commit 9b032c87 tightens M107 artifact path id guards.",
    "/docker/chummercomplete/chummer6-hub commit f1ca6c1a pins M107 artifact path guard proof.",
    "/docker/chummercomplete/chummer6-hub commit a91ea733 tightens M107 artifact factory receipt refs.",
    "/docker/chummercomplete/chummer6-hub commit c31258fa tightens M107 artifact factory proof floor.",
    "/docker/chummercomplete/chummer6-hub commit 45d3d498 tightens M107 artifact factory proof floor.",
    "/docker/chummercomplete/chummer6-hub commit c3aaf05a pins M107 artifact factory proof floor.",
    "/docker/chummercomplete/chummer6-hub commit 285e97be tightens the current M107 artifact factory proof floor guard.",
    "/docker/chummercomplete/chummer6-hub commit ce1c6611 pins M107 artifact factory proof floor guard.",
    "/docker/chummercomplete/chummer6-hub commit 67ae7dab requires refreshed M107 proof floor.",
    "/docker/chummercomplete/chummer6-hub commit 65ac67a8 pins M107 refreshed artifact factory proof floor.",
    "/docker/chummercomplete/chummer6-hub commit e0121780 tightens M107 artifact factory external URI guard.",
    "/docker/chummercomplete/chummer6-hub commit 9349395d tightens M107 source-pack batch preflight proof.",
    "/docker/chummercomplete/chummer6-hub commit a7c54b30 tightens M107 source-pack batch format-scope proof.",
    "/docker/chummercomplete/chummer6-hub commit 700343bc pins M107 format scope proof floor.",
    "successor frontier 1421219975 pinned for next90-m107-hub-artifact-factory repeat prevention.",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs rejects unapproved or provider-specific source packs and emits media-factory output bindings for preview, caption, packet, audio, and video formats.",
    "/docker/chummercomplete/chummer6-hub/Chummer.Run.Api/Controllers/InternalArtifactFactoryController.cs and Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs bind the recipe-backed job launcher to the internal authenticated Hub orchestration endpoint.",
    "/docker/chummercomplete/chummer6-hub/Chummer.Tests/ArtifactFactoryOrchestrationServiceTests.cs proves release, support, fix, and publication bundles route through approved source-pack receipts.",
    "/docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py fail-closes missing recipe families, internal endpoint auth, public proof shelf bundle refs, and anchored source-pack output selection.",
    "/docker/chummercomplete/chummer6-hub/scripts/launch_artifact_factory_source_pack_batch.py preflights approved source-pack batches against the internal recipe catalog before launch.",
    "python3 /docker/chummercomplete/chummer6-hub/scripts/verify_artifact_factory_orchestration.py exits 0.",
    "python3 -m unittest tests/test_artifact_factory_orchestration.py exits 0.",
    "python3 -m unittest tests/test_artifact_factory_source_pack_launcher.py exits 0.",
    "dotnet test /docker/chummercomplete/chummer6-hub/Chummer.Tests/Chummer.Tests.csproj --filter ArtifactFactoryOrchestrationServiceTests --no-restore exits 0.",
}
REPO_ABSOLUTE_PREFIX = "/docker/chummercomplete/chummer6-hub/"
ABSOLUTE_CITATION_PATTERN = re.compile(r"/docker/[A-Za-z0-9._/\-]+")
FORBIDDEN_PROOF_MARKERS = [
    "/var/lib/codex-fleet",
    "TASK_LOCAL_TELEMETRY",
    "ACTIVE_RUN_HANDOFF",
    "active-run helper",
    "operator telemetry",
    "run_ooda_design_supervisor_until_quiet",
    "ooda_design_supervisor.py",
    "python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_orchestration.py",
    "python3 -m unittest /docker/chummercomplete/chummer6-hub/tests/test_artifact_factory_source_pack_launcher.py",
]


def read_text(path: Path) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"missing required file: {path}")
    return path.read_text(encoding="utf-8")


def load_yaml(path: Path) -> object:
    return yaml.safe_load(read_text(path))


def find_queue_item(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValueError("queue staging root must be a mapping.")
    items = data.get("items")
    if not isinstance(items, list):
        raise ValueError("queue staging is missing an items list.")

    matches = [
        item
        for item in items
        if isinstance(item, dict) and item.get("package_id") == PACKAGE_ID
    ]
    if not matches:
        raise ValueError(f"queue staging is missing package_id {PACKAGE_ID}.")
    if len(matches) > 1:
        raise ValueError(
            f"queue staging must contain exactly one package_id {PACKAGE_ID}; found {len(matches)}."
        )
    return matches[0]


def find_successor_task(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValueError("successor registry root must be a mapping.")
    milestones = data.get("milestones")
    if not isinstance(milestones, list):
        raise ValueError("successor registry is missing a milestones list.")

    matching_milestones = [
        item
        for item in milestones
        if isinstance(item, dict) and item.get("id") == MILESTONE_ID
    ]
    if not matching_milestones:
        raise ValueError(f"successor registry is missing milestone {MILESTONE_ID}.")
    if len(matching_milestones) > 1:
        raise ValueError(
            f"successor registry must contain exactly one milestone {MILESTONE_ID}; found {len(matching_milestones)}."
        )
    milestone = matching_milestones[0]

    work_tasks = milestone.get("work_tasks")
    if not isinstance(work_tasks, list):
        raise ValueError(f"milestone {MILESTONE_ID} is missing work_tasks.")

    matching_tasks = [
        item
        for item in work_tasks
        if isinstance(item, dict) and float(item.get("id", -1)) == WORK_TASK_ID
    ]
    if not matching_tasks:
        raise ValueError(f"milestone {MILESTONE_ID} is missing work task {WORK_TASK_ID}.")
    if len(matching_tasks) > 1:
        raise ValueError(
            f"successor registry must contain exactly one work task {WORK_TASK_ID} under milestone {MILESTONE_ID}; found {len(matching_tasks)}."
        )
    return matching_tasks[0]


def require_exact_set(missing: list[str], label: str, actual: object, expected: set[str]) -> None:
    if not isinstance(actual, list):
        missing.append(f"{label}: expected list")
        return
    actual_set = {str(item) for item in actual}
    for item in sorted(expected - actual_set):
        missing.append(f"{label}: missing {item}")
    for item in sorted(actual_set - expected):
        missing.append(f"{label}: unexpected {item}")


def require_contains_set(missing: list[str], label: str, actual: object, expected: set[str]) -> None:
    if not isinstance(actual, list):
        missing.append(f"{label}: expected list")
        return
    actual_set = {str(item) for item in actual}
    for item in sorted(expected - actual_set):
        missing.append(f"{label}: missing {item}")


def repo_relative_anchor_path(proof_item: str) -> Path | None:
    candidate = proof_item.strip().split(maxsplit=1)[0].rstrip(".,")
    if not candidate.startswith(REPO_ABSOLUTE_PREFIX):
        return None
    return ROOT / candidate.removeprefix(REPO_ABSOLUTE_PREFIX)


def commit_anchor(proof_item: str) -> str | None:
    prefix = f"{REPO_ABSOLUTE_PREFIX.rstrip('/')} commit "
    if not proof_item.startswith(prefix):
        return None
    remainder = proof_item.removeprefix(prefix).strip()
    if not remainder:
        return None
    return remainder.split(maxsplit=1)[0].rstrip(".,")


def verify_proof_anchors_resolve(missing: list[str], label: str, proof_items: object) -> None:
    if not isinstance(proof_items, list):
        missing.append(f"{label}: expected list")
        return

    for raw_item in proof_items:
        item = str(raw_item)
        anchor_path = repo_relative_anchor_path(item)
        if anchor_path is not None and not anchor_path.is_file():
            missing.append(f"{label}: proof anchor does not resolve: {item}")

        commit = commit_anchor(item)
        if commit is None or not (ROOT / ".git").exists():
            continue
        result = subprocess.run(
            ["git", "-C", str(ROOT), "cat-file", "-e", f"{commit}^{{commit}}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0:
            missing.append(f"{label}: commit proof anchor does not resolve: {item}")
            continue

        result = subprocess.run(
            ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", commit, "HEAD"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0:
            missing.append(f"{label}: commit proof anchor is not on the current branch: {item}")


def reject_forbidden_proof_markers(missing: list[str], label: str, proof_items: object) -> None:
    if not isinstance(proof_items, list):
        return

    for raw_item in proof_items:
        item = str(raw_item)
        item_lower = item.lower()
        for marker in FORBIDDEN_PROOF_MARKERS:
            if marker.lower() in item_lower:
                missing.append(f"{label}: forbidden active-run proof marker: {marker}")


def reject_out_of_scope_repo_citations(missing: list[str], label: str, proof_items: object) -> None:
    if not isinstance(proof_items, list):
        return

    for raw_item in proof_items:
        item = str(raw_item)
        for citation in ABSOLUTE_CITATION_PATTERN.findall(item):
            normalized = citation.rstrip(".,)")
            if normalized.startswith(REPO_ABSOLUTE_PREFIX.rstrip("/")):
                continue
            missing.append(
                f"{label}: out-of-scope repo citation {normalized}; "
                f"completed package proof must stay inside {REPO_ABSOLUTE_PREFIX.rstrip('/')}."
            )


def verify_queue_authority(missing: list[str], path: Path) -> None:
    try:
        item = find_queue_item(load_yaml(path))
    except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
        missing.append(f"{path}: {exc}")
        return

    if item.get("milestone_id") != MILESTONE_ID:
        missing.append(f"{path}: {PACKAGE_ID} milestone_id must be {MILESTONE_ID}")
    for field, expected in REQUIRED_QUEUE_FIELDS.items():
        if item.get(field) != expected:
            missing.append(f"{path}: {PACKAGE_ID} {field} must be {expected!r}")
    require_exact_set(missing, f"{path}: {PACKAGE_ID} allowed_paths", item.get("allowed_paths"), REQUIRED_ALLOWED_PATHS)
    require_exact_set(missing, f"{path}: {PACKAGE_ID} owned_surfaces", item.get("owned_surfaces"), REQUIRED_OWNED_SURFACES)
    require_contains_set(missing, f"{path}: {PACKAGE_ID} proof", item.get("proof"), REQUIRED_QUEUE_PROOF)
    reject_forbidden_proof_markers(missing, f"{path}: {PACKAGE_ID} proof", item.get("proof"))
    reject_out_of_scope_repo_citations(missing, f"{path}: {PACKAGE_ID} proof", item.get("proof"))
    verify_proof_anchors_resolve(missing, f"{path}: {PACKAGE_ID} proof", item.get("proof"))


def verify_queue_mirror_alignment(missing: list[str], queue_paths: list[Path]) -> None:
    if len(queue_paths) < 2:
        return

    queue_items: list[tuple[Path, dict]] = []
    for path in queue_paths:
        try:
            queue_items.append((path, find_queue_item(load_yaml(path))))
        except (FileNotFoundError, ValueError, yaml.YAMLError):
            return

    baseline_path, baseline_item = queue_items[0]
    for path, item in queue_items[1:]:
        for field in QUEUE_MIRROR_FIELDS:
            if item.get(field) != baseline_item.get(field):
                missing.append(
                    f"{path}: queue mirror drift for {PACKAGE_ID} field {field}; "
                    f"must match {baseline_path} exactly."
                )


def verify_successor_registry_authority(missing: list[str], path: Path) -> None:
    try:
        task = find_successor_task(load_yaml(path))
    except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:
        missing.append(f"{path}: {exc}")
        return

    if task.get("owner") != "chummer6-hub":
        missing.append(f"{path}: milestone {MILESTONE_ID} task {WORK_TASK_ID} owner must be chummer6-hub")
    if task.get("status") != "complete":
        missing.append(f"{path}: milestone {MILESTONE_ID} task {WORK_TASK_ID} status must be complete")
    if task.get("title") != "Orchestrate recipe-backed artifact jobs from approved release, support, and publication packs.":
        missing.append(f"{path}: milestone {MILESTONE_ID} task {WORK_TASK_ID} title drifted")
    require_contains_set(
        missing,
        f"{path}: milestone {MILESTONE_ID} task {WORK_TASK_ID} evidence",
        task.get("evidence"),
        REQUIRED_REGISTRY_EVIDENCE,
    )
    reject_forbidden_proof_markers(
        missing,
        f"{path}: milestone {MILESTONE_ID} task {WORK_TASK_ID} evidence",
        task.get("evidence"),
    )
    reject_out_of_scope_repo_citations(
        missing,
        f"{path}: milestone {MILESTONE_ID} task {WORK_TASK_ID} evidence",
        task.get("evidence"),
    )
    verify_proof_anchors_resolve(
        missing,
        f"{path}: milestone {MILESTONE_ID} task {WORK_TASK_ID} evidence",
        task.get("evidence"),
    )


def verify_campaign_recipes_are_catalog_published(missing: list[str], service_text: str) -> None:
    list_recipes_start = service_text.find("public ArtifactFactoryRecipeCatalogResult ListRecipes()")
    default_batch_start = service_text.find("public static IReadOnlyList<string> GetAllowedFormats", list_recipes_start)
    if list_recipes_start < 0 or default_batch_start < 0:
        missing.append("Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs: cannot locate ListRecipes catalog body")
        return

    list_recipes_body = service_text[list_recipes_start:default_batch_start]
    if ".Where(static item => DefaultBatchFamilies.Contains(item.Key))" in list_recipes_body:
        missing.append(
            "Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs: ListRecipes must publish campaign_cold_open and mission_briefing recipes instead of filtering to default release/support families."
        )


def main() -> int:
    missing: list[str] = []

    for relative_path, markers in SOURCE_MARKERS.items():
        try:
            text = read_text(ROOT / relative_path)
        except FileNotFoundError as exc:
            missing.append(str(exc))
            continue

        for marker in markers:
            if marker not in text:
                missing.append(f"{relative_path}: {marker}")
        if relative_path == "Chummer.Run.Api/Services/ArtifactFactoryOrchestrationService.cs":
            verify_campaign_recipes_are_catalog_published(missing, text)

    queue_paths: list[Path] = []
    for queue_path in (QUEUE_STAGING_PATH, DESIGN_QUEUE_STAGING_PATH):
        if queue_path not in queue_paths:
            queue_paths.append(queue_path)

    for queue_path in queue_paths:
        try:
            queue_text = read_text(queue_path)
        except FileNotFoundError as exc:
            missing.append(str(exc))
        else:
            for marker in QUEUE_MARKERS:
                if marker not in queue_text:
                    missing.append(f"{queue_path}: {marker}")
            verify_queue_authority(missing, queue_path)

    verify_queue_mirror_alignment(missing, queue_paths)

    try:
        registry_text = read_text(SUCCESSOR_REGISTRY_PATH)
    except FileNotFoundError as exc:
        missing.append(str(exc))
    else:
        for marker in SUCCESSOR_REGISTRY_MARKERS:
            if marker not in registry_text:
                missing.append(f"{SUCCESSOR_REGISTRY_PATH}: {marker}")
        verify_successor_registry_authority(missing, SUCCESSOR_REGISTRY_PATH)

    if missing:
        for item in missing:
            print(f"artifact_factory_orchestration_missing: {item}", file=sys.stderr)
        return 1

    print("artifact factory orchestration proof passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
