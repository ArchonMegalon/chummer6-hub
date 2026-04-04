using System.Text.Json;
using Xunit;

namespace Chummer.Tests;

public sealed class VerificationEntryPointTests
{
    [Fact]
    public void AuditComplianceUsesSupportedVerificationScript()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "audit-compliance.sh");
        string script = File.ReadAllText(scriptPath);

        Assert.Contains("bash scripts/ai/verify.sh", script, StringComparison.Ordinal);
    }

    [Fact]
    public void ParityChecklistGeneratorFailClosesMalformedParityTokens()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "generate-parity-checklist.sh");
        string script = File.ReadAllText(scriptPath);

        Assert.Contains("normalize_required_token", script, StringComparison.Ordinal);
        Assert.Contains("parse_required_token_list", script, StringComparison.Ordinal);
        Assert.Contains("parse_catalog_token_matches", script, StringComparison.Ordinal);
        Assert.Contains("fail_on_unacknowledged_catalog_only", script, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_PARITY_DESKTOP_DIALOG_FACTORY_PATH", script, StringComparison.Ordinal);
        Assert.Contains("acknowledgedCatalogOnlyTabs", script, StringComparison.Ordinal);
        Assert.Contains("acknowledgedCatalogOnlyWorkspaceActions", script, StringComparison.Ordinal);
        Assert.Contains("acknowledgedDialogFactoryOnlyDesktopControls", script, StringComparison.Ordinal);
        Assert.Contains("desktopControls", script, StringComparison.Ordinal);
        Assert.Contains("must not contain blank token values", script, StringComparison.Ordinal);
        Assert.Contains("contains whitespace-padded token", script, StringComparison.Ordinal);
        Assert.Contains("contains non-canonical token", script, StringComparison.Ordinal);
        Assert.Contains("contains duplicate normalized token", script, StringComparison.Ordinal);
        Assert.Contains("is missing required acknowledged catalog-only", script, StringComparison.Ordinal);
        Assert.Contains("fail_on_missing_required_legacy_ids", script, StringComparison.Ordinal);
        Assert.Contains("surface_label=\"tab\"", script, StringComparison.Ordinal);
        Assert.Contains("surface_label=\"workspace action\"", script, StringComparison.Ordinal);
        Assert.Contains("is missing required legacy desktop control ids", script, StringComparison.Ordinal);
        Assert.Contains("dialog-factory-only desktop control", script, StringComparison.Ordinal);
        Assert.Contains("no longer catalog-only", script, StringComparison.Ordinal);
    }

    [Fact]
    public void AuditUiParityUsesActiveParityGeneratorInsteadOfRetiredLegacyShellFiles()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "audit-ui-parity.sh");
        string script = File.ReadAllText(scriptPath);

        Assert.Contains("scripts/generate-parity-checklist.sh", script, StringComparison.Ordinal);
        Assert.Contains("docs/PARITY_CHECKLIST.md", script, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_UI_PUBLISHED_DIR", script, StringComparison.Ordinal);
        Assert.Contains("chummer6-ui/.codex-studio/published", script, StringComparison.Ordinal);
        Assert.Contains("chummer-presentation/.codex-studio/published", script, StringComparison.Ordinal);
        Assert.Contains("resolve_receipt_path", script, StringComparison.Ordinal);
        Assert.Contains("DESKTOP_WORKFLOW_EXECUTION_GATE.generated.json", script, StringComparison.Ordinal);
        Assert.Contains("DESKTOP_VISUAL_FAMILIARITY_EXIT_GATE.generated.json", script, StringComparison.Ordinal);
        Assert.Contains("required executable receipt is missing", script, StringComparison.Ordinal);
        Assert.Contains("status must be pass/passed/ready", script, StringComparison.Ordinal);
        Assert.Contains("generatedAt/generated_at is missing", script, StringComparison.Ordinal);
        Assert.Contains("proof_freshness_max_age_seconds", script, StringComparison.Ordinal);
        Assert.Contains("proof_freshness_max_future_skew_seconds", script, StringComparison.Ordinal);
        Assert.Contains("generatedAt/generated_at is stale", script, StringComparison.Ordinal);
        Assert.Contains("generatedAt/generated_at is in the future", script, StringComparison.Ordinal);
        Assert.Contains("required_workflow_family_ids", script, StringComparison.Ordinal);
        Assert.Contains("missing_required_workflow_family_ids", script, StringComparison.Ordinal);
        Assert.Contains("flagship_required_desktop_heads", script, StringComparison.Ordinal);
        Assert.Contains("flagship_missing_or_not_ready_desktop_heads", script, StringComparison.Ordinal);
        Assert.Contains("flagship_missing_canonical_required_desktop_heads", script, StringComparison.Ordinal);
        Assert.Contains("flagship_head_missing_contract_markers", script, StringComparison.Ordinal);
        Assert.Contains("flagship_head_contract_marker_statuses", script, StringComparison.Ordinal);
        Assert.Contains("release_channel_receipt_exists", script, StringComparison.Ordinal);
        Assert.Contains("release_channel_channel_id", script, StringComparison.Ordinal);
        Assert.Contains("release_channel_version", script, StringComparison.Ordinal);
        Assert.Contains("release_channel_path", script, StringComparison.Ordinal);
        Assert.Contains("release_channel_generated_at", script, StringComparison.Ordinal);
        Assert.Contains("release-channel receipt status must be pass/passed/ready/published", script, StringComparison.Ordinal);
        Assert.Contains("release-channel channel id drifts from nested receipt", script, StringComparison.Ordinal);
        Assert.Contains("release-channel version drifts from nested receipt", script, StringComparison.Ordinal);
        Assert.Contains("release-channel generated_at drifts from nested receipt generatedAt", script, StringComparison.Ordinal);
        Assert.Contains("release-channel nested receipt generatedAt is stale", script, StringComparison.Ordinal);
        Assert.Contains("release-channel nested receipt generatedAt is in the future", script, StringComparison.Ordinal);
        Assert.Contains("release-channel nested receipt releaseProof is required", script, StringComparison.Ordinal);
        Assert.Contains("release-channel nested receipt releaseProof.status must be pass/passed/ready", script, StringComparison.Ordinal);
        Assert.Contains("alias values drift between", script, StringComparison.Ordinal);
        Assert.Contains("must be an ISO timestamp", script, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_UI_PARITY_RELEASE_PROOF_MAX_AGE_SECONDS", script, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_RELEASE_PROOF_MAX_AGE_SECONDS", script, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_UI_PARITY_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS", script, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_RELEASE_PROOF_MAX_FUTURE_SKEW_SECONDS", script, StringComparison.Ordinal);
        Assert.Contains("release-channel nested receipt releaseProof.generatedAt is stale", script, StringComparison.Ordinal);
        Assert.Contains("release-channel nested receipt releaseProof.generatedAt is in the future", script, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_UI_PARITY_ALLOWED_RELEASE_PROOF_BASE_URLS", script, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_ALLOWED_RELEASE_PROOF_BASE_URLS", script, StringComparison.Ordinal);
        Assert.Contains("must use canonical origin form with no trailing slash", script, StringComparison.Ordinal);
        Assert.Contains("must match an allowed canonical release origin", script, StringComparison.Ordinal);
        Assert.Contains("release-channel nested receipt releaseProof.journeysPassed is missing required baseline journey ids", script, StringComparison.Ordinal);
        Assert.Contains("release-channel nested receipt releaseProof.journeysPassed declares unexpected journey ids", script, StringComparison.Ordinal);
        Assert.Contains("release-channel nested receipt releaseProof.journeysPassed must use canonical lowercase journey ids", script, StringComparison.Ordinal);
        Assert.Contains("release-channel nested receipt releaseProof.journeysPassed must use canonical journey id tokens", script, StringComparison.Ordinal);
        Assert.Contains("release-channel nested receipt releaseProof.proofRoutes is missing required flagship routes", script, StringComparison.Ordinal);
        Assert.Contains("release-channel nested receipt releaseProof.proofRoutes declares unexpected flagship routes", script, StringComparison.Ordinal);
        Assert.Contains("must use canonical lowercase route casing", script, StringComparison.Ordinal);
        Assert.Contains("must not include percent-encoded or escaped path characters", script, StringComparison.Ordinal);
        Assert.Contains("workflow_parity_receipt_channel_ids", script, StringComparison.Ordinal);
        Assert.Contains("milestone-2 workflow/visual release-channel ids drift", script, StringComparison.Ordinal);
        Assert.Contains("milestone-2 workflow/visual release-channel versions drift", script, StringComparison.Ordinal);
        Assert.Contains("milestone-2 workflow/visual release-channel nested receipt paths drift", script, StringComparison.Ordinal);
        Assert.Contains("milestone-2 workflow/visual release-channel generated_at drift", script, StringComparison.Ordinal);
        Assert.Contains("flagship_gate.headProofs.status_malformed_entries", script, StringComparison.Ordinal);
        Assert.Contains("flagship_gate.headProofs.status_non_canonical_keys", script, StringComparison.Ordinal);
        Assert.Contains("flagship_gate.headProofs.status_duplicate_normalized_keys", script, StringComparison.Ordinal);
        Assert.Contains("workflow_execution_missing_receipts", script, StringComparison.Ordinal);
        Assert.Contains("workflow_execution_weak_receipts", script, StringComparison.Ordinal);
        Assert.Contains("workflow_family_missing_receipts", script, StringComparison.Ordinal);
        Assert.Contains("workflow_family_failing_receipts", script, StringComparison.Ordinal);
        Assert.Contains("workflow_family_receipt_count_checked", script, StringComparison.Ordinal);
        Assert.Contains("workflow_execution_receipt_count_checked", script, StringComparison.Ordinal);
        Assert.Contains("missing_required_workflow_family_audit_tests", script, StringComparison.Ordinal);
        Assert.Contains("sr4_workflow_parity_status", script, StringComparison.Ordinal);
        Assert.Contains("sr6_workflow_parity_status", script, StringComparison.Ordinal);
        Assert.Contains("chummer5a_workflow_parity_status", script, StringComparison.Ordinal);
        Assert.Contains("sr4_sr6_frontier_status", script, StringComparison.Ordinal);
        Assert.Contains("workflow_parity_proof_max_age_seconds", script, StringComparison.Ordinal);
        Assert.Contains("evidence path is missing", script, StringComparison.Ordinal);
        Assert.Contains("resolve_nested_receipt_path", script, StringComparison.Ordinal);
        Assert.Contains("nested receipt generatedAt is stale", script, StringComparison.Ordinal);
        Assert.Contains("nested receipt generatedAt is in the future", script, StringComparison.Ordinal);
        Assert.Contains("generated_at drifts from nested receipt generatedAt", script, StringComparison.Ordinal);
        Assert.Contains("evidence age exceeds allowed freshness window", script, StringComparison.Ordinal);
        Assert.Contains("evidence generated_at is stale", script, StringComparison.Ordinal);
        Assert.Contains("evidence generated_at is in the future", script, StringComparison.Ordinal);
        Assert.Contains("metatype-priorities-karma-entry", script, StringComparison.Ordinal);
        Assert.Contains("recovery-reload-migration-roundtrips", script, StringComparison.Ordinal);
        Assert.Contains("required_legacy_interaction_keys", script, StringComparison.Ordinal);
        Assert.Contains("missing_required_legacy_interaction_keys", script, StringComparison.Ordinal);
        Assert.Contains("reports non-pass flagship head contract markers", script, StringComparison.Ordinal);
        Assert.Contains("required_tests", script, StringComparison.Ordinal);
        Assert.Contains("must not include leading/trailing whitespace", script, StringComparison.Ordinal);
        Assert.Contains("must not be blank", script, StringComparison.Ordinal);
        Assert.Contains("must not contain duplicate ids", script, StringComparison.Ordinal);
        Assert.Contains("Desktop_shell_preserves_classic_dense_three_pane_workbench_posture", script, StringComparison.Ordinal);
        Assert.Contains("Gear_builder_preserves_familiar_browse_detail_confirm_rhythm", script, StringComparison.Ordinal);
        Assert.Contains("Cyberware_and_cyberlimb_builder_preserve_legacy_dialog_familiarity_cues", script, StringComparison.Ordinal);
        Assert.Contains("Contacts_diary_and_support_routes_execute_with_public_path_visibility", script, StringComparison.Ordinal);
        Assert.Contains("Loaded_runner_main_window_routes_navigation_palette_dialog_and_quick_action_surfaces_end_to_end", script, StringComparison.Ordinal);
        Assert.Contains("missing required milestone-2 visual tests", script, StringComparison.Ordinal);
        Assert.Contains("declares unexpected milestone-2 visual tests", script, StringComparison.Ordinal);
        Assert.Contains("required_screenshots", script, StringComparison.Ordinal);
        Assert.Contains("missing required milestone-2 screenshots", script, StringComparison.Ordinal);
        Assert.Contains("declares unexpected milestone-2 screenshots", script, StringComparison.Ordinal);
        Assert.Contains("screenshot_dir is missing", script, StringComparison.Ordinal);
        Assert.Contains("screenshot_dir does not exist", script, StringComparison.Ordinal);
        Assert.Contains("screenshot_timestamps must be a JSON object", script, StringComparison.Ordinal);
        Assert.Contains("screenshot timestamp drifts from on-disk file mtime", script, StringComparison.Ordinal);
        Assert.Contains("screenshot_receipt_skew_max_seconds", script, StringComparison.Ordinal);
        Assert.Contains("required screenshot file is missing on disk", script, StringComparison.Ordinal);
        Assert.Contains("missing_screenshots", script, StringComparison.Ordinal);
        Assert.Contains("missing_theme_tokens", script, StringComparison.Ordinal);
        Assert.Contains("flagship_theme_readability_contrast", script, StringComparison.Ordinal);
        Assert.Contains("runtime_backed_shell_menu", script, StringComparison.Ordinal);
        Assert.Contains("runtime_backed_menu_bar_labels", script, StringComparison.Ordinal);
        Assert.Contains("runtime_backed_toolstrip_actions", script, StringComparison.Ordinal);
        Assert.Contains("runtime_backed_tab_panel_only_header", script, StringComparison.Ordinal);
        Assert.Contains("runtime_backed_clickable_primary_menus", script, StringComparison.Ordinal);
        Assert.Contains("loaded_runner_tab_strip_control_present", script, StringComparison.Ordinal);
        Assert.Contains("loaded_runner_tab_posture_control_present", script, StringComparison.Ordinal);
        Assert.Contains("flagship theme/readability proof is not pass-ready", script, StringComparison.Ordinal);
        Assert.Contains("invalid_screenshots", script, StringComparison.Ordinal);
        Assert.Contains("undersized_screenshots", script, StringComparison.Ordinal);
        Assert.Contains("stale_screenshots", script, StringComparison.Ordinal);
        Assert.Contains("screenshots_older_than_flagship_receipt", script, StringComparison.Ordinal);
        Assert.Contains("runtimeBackedLegacyWorkbench", script, StringComparison.Ordinal);
        Assert.Contains("legacyDenseBuilderRhythm", script, StringComparison.Ordinal);
        Assert.Contains("legacyBrowseDetailConfirmRhythm", script, StringComparison.Ordinal);
        Assert.Contains("legacyContactsDiaryRhythm", script, StringComparison.Ordinal);
        Assert.Contains("legacyMagicWorkflowRhythm", script, StringComparison.Ordinal);
        Assert.Contains("legacyDiaryWorkflowRhythm", script, StringComparison.Ordinal);
        Assert.Contains("declares unexpected milestone-2 interaction keys", script, StringComparison.Ordinal);
        Assert.Contains("legacy_familiarity_bridge", script, StringComparison.Ordinal);
        Assert.Contains("required_visual_status_fields", script, StringComparison.Ordinal);
        Assert.Contains("{label} proof is not pass-ready", script, StringComparison.Ordinal);
        Assert.Contains("Parity audit passed", script, StringComparison.Ordinal);
        Assert.DoesNotContain("Chummer.Web/wwwroot/index.html", script, StringComparison.Ordinal);
        Assert.DoesNotContain("Chummer/Forms/ChummerMainForm.Designer.cs", script, StringComparison.Ordinal);
        Assert.DoesNotContain("required files missing", script, StringComparison.Ordinal);
    }

    [Fact]
    public void VerifyEntrypointRunsUiParityAudit()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "ai", "verify.sh");
        string script = File.ReadAllText(scriptPath);

        Assert.Contains("bash scripts/audit-ui-parity.sh", script, StringComparison.Ordinal);
        Assert.Contains("release_channel_path", script, StringComparison.Ordinal);
        Assert.Contains("DESKTOP_WORKFLOW_EXECUTION_GATE.generated.json", script, StringComparison.Ordinal);
        Assert.Contains("reject releaseProof.baseUrl outside allowed canonical release origins", script, StringComparison.Ordinal);
        Assert.Contains("reject conflicting alias values between releaseProof.baseUrl and releaseProof.base_url", script, StringComparison.Ordinal);
        Assert.Contains("reject conflicting alias values between releaseProof.proofRoutes and releaseProof.proof_routes", script, StringComparison.Ordinal);
        Assert.Contains("reject conflicting alias values between releaseProof.journeysPassed and releaseProof.journeys_passed", script, StringComparison.Ordinal);
        Assert.Contains("reject non-canonical releaseProof.baseUrl origin casing/trailing slash", script, StringComparison.Ordinal);
        Assert.Contains("reject missing releaseProof.baseUrl origin", script, StringComparison.Ordinal);
        Assert.Contains("reject non-http(s) releaseProof.baseUrl schemes", script, StringComparison.Ordinal);
        Assert.Contains("reject non-origin releaseProof.baseUrl path/query segments", script, StringComparison.Ordinal);
        Assert.Contains("reject userinfo credentials in releaseProof.baseUrl origins", script, StringComparison.Ordinal);
        Assert.Contains("reject whitespace-padded releaseProof.baseUrl values", script, StringComparison.Ordinal);
        Assert.Contains("reject percent-encoded releaseProof.proofRoutes entries", script, StringComparison.Ordinal);
        Assert.Contains("reject query/fragment releaseProof.proofRoutes entries", script, StringComparison.Ordinal);
        Assert.Contains("reject escaped-path releaseProof.proofRoutes entries", script, StringComparison.Ordinal);
        Assert.Contains("reject whitespace-padded releaseProof.proofRoutes entries", script, StringComparison.Ordinal);
        Assert.Contains("reject non-slash-led releaseProof.proofRoutes entries", script, StringComparison.Ordinal);
        Assert.Contains("reject dot-segment traversal releaseProof.proofRoutes entries", script, StringComparison.Ordinal);
        Assert.Contains("reject non-canonical uppercase releaseProof.proofRoutes entries", script, StringComparison.Ordinal);
        Assert.Contains("reject empty-segment releaseProof.proofRoutes entries", script, StringComparison.Ordinal);
        Assert.Contains("reject duplicate-normalized releaseProof.proofRoutes entries", script, StringComparison.Ordinal);
        Assert.Contains("reject missing required releaseProof.proofRoutes flagship routes", script, StringComparison.Ordinal);
        Assert.Contains("reject unexpected releaseProof.proofRoutes flagship routes", script, StringComparison.Ordinal);
        Assert.Contains("reject duplicate releaseProof.journeysPassed journey ids", script, StringComparison.Ordinal);
        Assert.Contains("reject missing required releaseProof.journeysPassed baseline journey ids", script, StringComparison.Ordinal);
        Assert.Contains("reject unexpected releaseProof.journeysPassed journey ids", script, StringComparison.Ordinal);
        Assert.Contains("reject non-canonical lowercase releaseProof.journeysPassed journey ids", script, StringComparison.Ordinal);
        Assert.Contains("reject non-canonical token shape in releaseProof.journeysPassed journey ids", script, StringComparison.Ordinal);
        Assert.Contains("reject non-passing releaseProof.status values", script, StringComparison.Ordinal);
        Assert.Contains("reject missing releaseProof payloads", script, StringComparison.Ordinal);
        Assert.Contains("reject non-array releaseProof.journeysPassed payloads", script, StringComparison.Ordinal);
        Assert.Contains("reject non-array releaseProof.proofRoutes payloads", script, StringComparison.Ordinal);
        Assert.Contains("reject non-string releaseProof.journeysPassed entries", script, StringComparison.Ordinal);
        Assert.Contains("reject non-string releaseProof.proofRoutes entries", script, StringComparison.Ordinal);
        Assert.Contains("reject whitespace-padded releaseProof.journeysPassed journey ids", script, StringComparison.Ordinal);
        Assert.Contains("reject blank releaseProof.journeysPassed journey ids", script, StringComparison.Ordinal);
        Assert.Contains("reject missing releaseProof.generatedAt timestamps", script, StringComparison.Ordinal);
        Assert.Contains("reject conflicting alias values between releaseProof.generatedAt and releaseProof.generated_at", script, StringComparison.Ordinal);
        Assert.Contains("reject stale releaseProof.generatedAt timestamps", script, StringComparison.Ordinal);
        Assert.Contains("reject invalid-format releaseProof.generatedAt timestamps", script, StringComparison.Ordinal);
        Assert.Contains("reject releaseProof.generatedAt timestamps with excessive future skew", script, StringComparison.Ordinal);
    }

    [Fact]
    public void ParityOracleTokenListsUseCanonicalStringIds()
    {
        string oraclePath = RepoPaths.FromRoot("docs", "PARITY_ORACLE.json");
        using JsonDocument oracle = JsonDocument.Parse(File.ReadAllText(oraclePath));
        JsonElement root = oracle.RootElement;

        Assert.Equal(JsonValueKind.Object, root.ValueKind);
        AssertCanonicalTokenArray(root, "tabs");
        AssertCanonicalTokenArray(root, "workspaceActions");
        AssertCanonicalTokenArray(root, "acknowledgedCatalogOnlyTabs");
        AssertCanonicalTokenArray(root, "acknowledgedCatalogOnlyWorkspaceActions");
        AssertCanonicalTokenArray(root, "acknowledgedDialogFactoryOnlyDesktopControls");
        AssertCanonicalTokenArray(root, "desktopControls");
    }

    private static void AssertCanonicalTokenArray(JsonElement root, string propertyName)
    {
        Assert.True(root.TryGetProperty(propertyName, out JsonElement values), $"{propertyName} must exist");
        Assert.Equal(JsonValueKind.Array, values.ValueKind);

        HashSet<string> normalized = new(StringComparer.Ordinal);
        int index = 0;
        foreach (JsonElement value in values.EnumerateArray())
        {
            Assert.Equal(JsonValueKind.String, value.ValueKind);

            string token = value.GetString() ?? string.Empty;
            Assert.False(string.IsNullOrWhiteSpace(token), $"{propertyName}[{index}] must not be blank");
            Assert.Equal(token.Trim(), token);
            Assert.Equal(token.ToLowerInvariant(), token);

            string normalizedToken = token.ToLowerInvariant();
            Assert.True(
                normalized.Add(normalizedToken),
                $"{propertyName}[{index}] duplicates normalized token '{token}'");
            index++;
        }
    }

    [Fact]
    public void SupportVerificationGuardAvoidsUnmatchedInstallFallback()
    {
        string presenterPath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "Support", "SupportCasePresentationService.cs");
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "SupportCasesController.cs");

        string presenter = File.ReadAllText(presenterPath);
        string controller = File.ReadAllText(controllerPath);

        Assert.Contains("best is not null && best.Score > 0", presenter, StringComparison.Ordinal);
        Assert.Contains("AllowsReporterVerification", controller, StringComparison.Ordinal);
        Assert.Contains("presented.CanVerifyFix", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void SignedInTrustProjectionSuppressesIdentityOutages()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string controller = File.ReadAllText(controllerPath);

        Assert.Contains("TryGetOptionalPublicSurfaceSubjectAsync", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void SignedInReleaseUploadHandoffIsPublishedFromPortal()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "ReleaseUpload.cshtml");
        string bootstrapPath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "artifacts", "mac-codex-release-pipeline", "bootstrap.sh");
        string wrapperPath = RepoPaths.FromRoot("scripts", "run-mac-release-bootstrap.sh");
        string maintenanceReadmePath = RepoPaths.FromRoot("..", "chummer-design", "products", "chummer", "maintenance", "MAC_CODEX_RELEASE_TO_CHUMMER_RUN.md");
        string presentationRunbookPath = RepoPaths.FromRoot("..", "chummer-presentation", "docs", "MAC_CODEX_RELEASE_TO_CHUMMER_RUN.md");
        string publicReadmePath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "artifacts", "mac-codex-release-pipeline", "readme.md");

        string controller = File.ReadAllText(controllerPath);
        string viewModel = File.ReadAllText(viewModelPath);
        string view = File.ReadAllText(viewPath);
        string bootstrap = File.ReadAllText(bootstrapPath);
        string wrapper = File.ReadAllText(wrapperPath);
        string maintenanceReadme = File.ReadAllText(maintenanceReadmePath);
        string presentationRunbook = File.ReadAllText(presentationRunbookPath);
        string publicReadme = File.ReadAllText(publicReadmePath);

        Assert.Contains("/downloads/release-upload", controller, StringComparison.Ordinal);
        Assert.Contains("/downloads/release-upload/bootstrap.sh", controller, StringComparison.Ordinal);
        Assert.Contains("bash <(curl -fsSL", controller, StringComparison.Ordinal);
        Assert.Contains("ReleaseUploadTicketService", controller, StringComparison.Ordinal);
        Assert.Contains("ReleaseUploadPageViewModel", viewModel, StringComparison.Ordinal);
        Assert.Contains("Signed-in release upload", view, StringComparison.Ordinal);
        Assert.Contains("operator source of truth", view, StringComparison.Ordinal);
        Assert.Contains("claim code", view, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("CHUMMER_RELEASE_UPLOAD_TOKEN", bootstrap, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_RELEASE_UPLOAD_URL", bootstrap, StringComparison.Ordinal);
        Assert.Contains("log_bootstrap_identity", bootstrap, StringComparison.Ordinal);
        Assert.Contains("bootstrap source:", bootstrap, StringComparison.Ordinal);
        Assert.Contains("bootstrap template not found", wrapper, StringComparison.Ordinal);
        Assert.Contains("downloads/release-upload", wrapper, StringComparison.Ordinal);
        Assert.Contains("artifacts/mac-codex-release-pipeline/bootstrap.sh", wrapper, StringComparison.Ordinal);
        Assert.DoesNotContain("/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/wwwroot/artifacts/mac-codex-release-pipeline/bootstrap.sh", wrapper, StringComparison.Ordinal);
        Assert.Contains("downloads/release-upload", maintenanceReadme, StringComparison.Ordinal);
        Assert.Contains("run-mac-release-bootstrap.sh", maintenanceReadme, StringComparison.Ordinal);
        Assert.DoesNotContain("/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/wwwroot/artifacts/mac-codex-release-pipeline/bootstrap.sh", maintenanceReadme, StringComparison.Ordinal);
        Assert.Contains("downloads/release-upload", presentationRunbook, StringComparison.Ordinal);
        Assert.Contains("run-mac-release-bootstrap.sh", presentationRunbook, StringComparison.Ordinal);
        Assert.DoesNotContain("/docker/chummercomplete/chummer.run-services/Chummer.Run.Api/wwwroot/artifacts/mac-codex-release-pipeline/bootstrap.sh", presentationRunbook, StringComparison.Ordinal);
        Assert.Contains("downloads/release-upload", publicReadme, StringComparison.Ordinal);
        Assert.Contains("run-mac-release-bootstrap.sh", publicReadme, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_MAC_RELEASE_MIN_FREE_GIB", publicReadme, StringComparison.Ordinal);
    }

    [Fact]
    public void MacDownloadsUseBootstrapScriptHandoffInsteadOfRawDmgDefault()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string downloadsControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "DownloadsCompatibilityController.cs");
        string servicePath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "ReleaseSelectionService.cs");
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");
        string downloadsViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Downloads.cshtml");
        string dispatchViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "DownloadDispatch.cshtml");

        string controller = File.ReadAllText(controllerPath);
        string downloadsController = File.ReadAllText(downloadsControllerPath);
        string service = File.ReadAllText(servicePath);
        string viewModel = File.ReadAllText(viewModelPath);
        string downloadsView = File.ReadAllText(downloadsViewPath);
        string dispatchView = File.ReadAllText(dispatchViewPath);

        Assert.Contains("/downloads/install/{artifactId}/bootstrap.command", controller, StringComparison.Ordinal);
        Assert.Contains("/downloads/install/{artifactId}/bootstrap.ps1", controller, StringComparison.Ordinal);
        Assert.Contains("/downloads/install/{artifactId}/bootstrap.sh", controller, StringComparison.Ordinal);
        Assert.Contains("RenderMacInstallBootstrapScript", controller, StringComparison.Ordinal);
        Assert.Contains("RenderWindowsInstallBootstrapScript", controller, StringComparison.Ordinal);
        Assert.Contains("RenderLinuxInstallBootstrapScript", controller, StringComparison.Ordinal);
        Assert.Contains("asks which Chummer apps to install and where to put them", controller, StringComparison.Ordinal);
        Assert.Contains("The Mac setup assistant offers Auto select", controller, StringComparison.Ordinal);
        Assert.Contains("The Windows setup assistant offers Auto select", controller, StringComparison.Ordinal);
        Assert.Contains("The Linux setup assistant offers Auto select", controller, StringComparison.Ordinal);
        Assert.Contains("whether to leave quick access in Applications only or add Desktop links", controller, StringComparison.Ordinal);
        Assert.Contains("verifies that linking actually completed", controller, StringComparison.Ordinal);
        Assert.Contains("Each selected app is started once through a short-lived environment handoff", controller, StringComparison.Ordinal);
        Assert.Contains("verify_download_digest", controller, StringComparison.Ordinal);
        Assert.Contains("perform_staged_install", controller, StringComparison.Ordinal);
        Assert.Contains("launch_bundle_binary_with_claim", controller, StringComparison.Ordinal);
        Assert.Contains("ConvertFrom-Json", controller, StringComparison.Ordinal);
        Assert.Contains("--bootstrap-install", controller, StringComparison.Ordinal);
        Assert.Contains("dpkg-deb -x", controller, StringComparison.Ordinal);
        Assert.Contains("resolve_install_state_root", controller, StringComparison.Ordinal);
        Assert.Contains("build_install_state_path", controller, StringComparison.Ordinal);
        Assert.Contains("read_install_state_field", controller, StringComparison.Ordinal);
        Assert.Contains("wait_for_claim_success", controller, StringComparison.Ordinal);
        Assert.Contains("Confirmed linked installs", controller, StringComparison.Ordinal);
        Assert.Contains("create_desktop_link", controller, StringComparison.Ordinal);
        Assert.Contains("run_privileged_script", controller, StringComparison.Ordinal);
        Assert.Contains("Current Mac architecture", controller, StringComparison.Ordinal);
        Assert.Contains("open -n \\\"$target_app\\\" >/dev/null 2>&1 || true", controller, StringComparison.Ordinal);
        Assert.Contains("kill \\\"$launch_pid\\\"", controller, StringComparison.Ordinal);
        Assert.Contains("wait \\\"$launch_pid\\\" >/dev/null 2>&1 || true", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("copies them to your clipboard", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("xattr -dr com.apple.quarantine", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("--install-claim-code", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("pkill -f \"$target_app/Contents/MacOS\"", controller, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_INSTALL_CLAIM_CODE", controller, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_API_BASE_URL", controller, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_WEB_BASE_URL", controller, StringComparison.Ordinal);
        Assert.Contains("InstallBootstrapTicketService", controller, StringComparison.Ordinal);
        Assert.Contains("QueryString.Create(\"ticket\"", controller, StringComparison.Ordinal);
        Assert.Contains("invalid_or_expired_install_ticket", controller, StringComparison.Ordinal);
        Assert.Contains("claimCode", controller, StringComparison.Ordinal);
        Assert.Contains("invalid_or_expired_claim_code", downloadsController, StringComparison.Ordinal);
        Assert.Contains("UsesMacBootstrapScript", service, StringComparison.Ordinal);
        Assert.Contains("visible_as_account_gated_setup_script_preview", service, StringComparison.Ordinal);
        Assert.Contains("DetectPreferredArchitecture", service, StringComparison.Ordinal);
        Assert.Contains("guided Mac setup assistant", service, StringComparison.Ordinal);
        Assert.Contains("verifies the published DMG digest", service, StringComparison.Ordinal);
        Assert.Contains("macOS (Apple Silicon)", service, StringComparison.Ordinal);
        Assert.Contains("BootstrapScriptDownload", viewModel, StringComparison.Ordinal);
        Assert.Contains("TerminalInstallCommand", viewModel, StringComparison.Ordinal);
        Assert.Contains("BootstrapCommandLabel", viewModel, StringComparison.Ordinal);
        Assert.Contains("BootstrapCommandIntro", viewModel, StringComparison.Ordinal);
        Assert.Contains("BootstrapCommandNote", viewModel, StringComparison.Ordinal);
        Assert.Contains("BootstrapFeatureCards", viewModel, StringComparison.Ordinal);
        Assert.Contains("CurrentReleaseSummary", viewModel, StringComparison.Ordinal);
        Assert.Contains("AutoStartDownload", viewModel, StringComparison.Ordinal);
        Assert.DoesNotContain("downloads-quicknav", downloadsView, StringComparison.Ordinal);
        Assert.Contains("Advanced download options", downloadsView, StringComparison.Ordinal);
        Assert.Contains("copy the Terminal command", downloadsView, StringComparison.Ordinal);
        Assert.Contains("BuildMacBootstrapTerminalCommand", controller, StringComparison.Ordinal);
        Assert.Contains("ResolveClaimTicketForDownload", controller, StringComparison.Ordinal);
        Assert.Contains("Copy install command", dispatchView, StringComparison.Ordinal);
        Assert.Contains("BootstrapCommandIntro", dispatchView, StringComparison.Ordinal);
        Assert.Contains("BootstrapCommandLabel", dispatchView, StringComparison.Ordinal);
        Assert.Contains("BootstrapFeatureCards", dispatchView, StringComparison.Ordinal);
        Assert.Contains("CurrentReleaseSummary", dispatchView, StringComparison.Ordinal);
        Assert.Contains("Fallbacks and recovery", dispatchView, StringComparison.Ordinal);
        Assert.Contains("Setup highlights", dispatchView, StringComparison.Ordinal);
        Assert.Contains("Recovery claim code", dispatchView, StringComparison.Ordinal);
        Assert.DoesNotContain("_PublicTrustPulsePanel.cshtml", dispatchView, StringComparison.Ordinal);
        Assert.Contains("if (autoStartDownload)", dispatchView, StringComparison.Ordinal);
        Assert.Contains("SecondaryDownloadLabel", dispatchView, StringComparison.Ordinal);
        Assert.Contains("RebindDownloadsHeaderActions", controller, StringComparison.Ordinal);
        Assert.Contains("GuestGateSecondaryHref", controller, StringComparison.Ordinal);
        Assert.Contains("GuestGatePrimaryHref", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void MacReleaseBootstrapSupportsCleanStockMacLayouts()
    {
        string bootstrapPath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "artifacts", "mac-codex-release-pipeline", "bootstrap.sh");
        string bootstrap = File.ReadAllText(bootstrapPath);

        Assert.Contains("ensure_dotnet_resolver", bootstrap, StringComparison.Ordinal);
        Assert.Contains("$HOME/.dotnet", bootstrap, StringComparison.Ordinal);
        Assert.Contains("dotnet --list-sdks", bootstrap, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_LOCAL_CAMPAIGN_CONTRACTS_PROJECT", bootstrap, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_LOCAL_HUB_REGISTRY_CONTRACTS_PROJECT", bootstrap, StringComparison.Ordinal);
        Assert.Contains("chummer6-media-factory.git", bootstrap, StringComparison.Ordinal);
        Assert.Contains("validate_publish_mode", bootstrap, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_RELEASE_UPLOAD_TOKEN", bootstrap, StringComparison.Ordinal);
        Assert.Contains("[[ \"${#app_heads[@]}\" -eq 0 ]]", bootstrap, StringComparison.Ordinal);
        Assert.Contains("upload_release_bundle_http()", bootstrap, StringComparison.Ordinal);
        Assert.Contains("write_public_promotion_evidence()", bootstrap, StringComparison.Ordinal);
        Assert.Contains("require_min_free_space_gib", bootstrap, StringComparison.Ordinal);
        Assert.Contains("log_disk_space", bootstrap, StringComparison.Ordinal);
        Assert.Contains("hdiutil create for signed repack", bootstrap, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_MAC_RELEASE_MIN_FREE_GIB", bootstrap, StringComparison.Ordinal);
        Assert.DoesNotContain("scripts/generate-public-promotion-evidence.py", bootstrap, StringComparison.Ordinal);
        Assert.DoesNotContain("bash scripts/publish-download-bundle-http.sh", bootstrap, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicEdgeComposePinsHttpsPortForLocalChummerRunRedirects()
    {
        string composePath = RepoPaths.FromRoot("docker-compose.public-edge.yml");
        string compose = File.ReadAllText(composePath);

        Assert.Contains("ASPNETCORE_HTTPS_PORT", compose, StringComparison.Ordinal);
        Assert.Contains("${ASPNETCORE_HTTPS_PORT:-443}", compose, StringComparison.Ordinal);
    }

    [Fact]
    public void HubLiveAuditSupportsReverseProxiedLocalEdgeMode()
    {
        string auditPath = RepoPaths.FromRoot("scripts", "hub-live-audit.py");
        string audit = File.ReadAllText(auditPath);

        Assert.Contains("--public-host", audit, StringComparison.Ordinal);
        Assert.Contains("--forwarded-proto", audit, StringComparison.Ordinal);
        Assert.Contains("--verify-http-redirects", audit, StringComparison.Ordinal);
        Assert.Contains("X-Forwarded-Proto", audit, StringComparison.Ordinal);
        Assert.Contains("Accept-Language", audit, StringComparison.Ordinal);
        Assert.Contains("Cache-Control", audit, StringComparison.Ordinal);
        Assert.Contains("Pragma", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=seasonops", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=seasonop", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=season-operation", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=season-operations", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=seasoncontrol", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=season%20control", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=seasoncontrols", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=seasonctrl", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=eventcontrol", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=eventcontrols", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=eventctrl", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=eventops", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=event%20ops", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=eventop", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=event-operation", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=event-operations", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=gmops", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=gm%20ops", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=gm-ops", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=gmop", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=gm-op", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=gmoperation", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=gmoperations", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=gm%20operation", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=gm-operation", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=gm%20operations", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=gm-operations", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=leagueops", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=leagueoperation", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=league-operation", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=leagueoperations", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=league-operations", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=league%20ops", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=league-ops", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=leaguecontrol", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=league%20control", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=league-control", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=leaguectrl", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=communityops", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=communityoperation", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=community-operation", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=communityoperations", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=community-operations", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=community%20ops", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=community-ops", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=communitycontrol", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=community%20control", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=community-control", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=communityctrl", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=heat", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=oppositions", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=encounter", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=enemy", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=hostile", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=adversary", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=threat", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=opfor", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=opforce", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=contact", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=contacts", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=connection", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=faction", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=journal", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=sessionlog", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=diary", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=downtime", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=aftermath", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=recap", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=return", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=memory", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=archive", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=history", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=timeline", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=ledger", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=roster", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=rostermove", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=rostermoves", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=crewmove", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=crewmoves", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=rostertransfer", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=rostertransfers", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=rosterhandoff", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=rosterhandoffs", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=crewhandoff", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=crewhandoffs", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=crewtransfer", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=crewtransfers", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=crew%20transfer", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=crew%20transfers", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=crew%20handoff", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=crew%20handoffs", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=crew%20move", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=crew%20moves", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=roster%20transfer", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=roster%20transfers", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=roster%20handoff", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=roster%20handoffs", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=roster%20move", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=roster%20moves", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=roster-move", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=crew-move", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=roster-transfer", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=crew-transfer", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=roster-handoff", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=crew-handoff", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=preplaunch", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=preplaunches", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=travelprefetch", audit, StringComparison.Ordinal);
        Assert.Contains("queryText=travelprefetches", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=seasonops", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=seasonop", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=season-operation", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=season-operations", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=seasoncontrol", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=season%20control", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=seasoncontrols", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=seasonctrl", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=eventcontrol", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=eventcontrols", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=eventctrl", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=eventops", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=event%20ops", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=eventop", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=event-operation", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=event-operations", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=gmops", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=gm%20ops", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=gm-ops", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=gmop", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=gm-op", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=gmoperation", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=gmoperations", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=gm%20operation", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=gm-operation", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=gm%20operations", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=gm-operations", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=heat", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=oppositions", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=encounter", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=enemy", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=hostile", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=adversary", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=threat", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=opfor", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=opforce", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=contact", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=contacts", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=connection", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=faction", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=journal", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=sessionlog", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=diary", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=downtime", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=aftermath", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=recap", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=return", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=memory", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=archive", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=history", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=timeline", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=ledger", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=roster", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=rostermove", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=rostermoves", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=crewmove", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=crewmoves", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=rostertransfer", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=rostertransfers", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=rosterhandoff", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=rosterhandoffs", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=crewhandoff", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=crewhandoffs", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=crewtransfer", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=crewtransfers", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=crew%20transfer", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=crew%20transfers", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=crew%20handoff", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=crew%20handoffs", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=crew%20move", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=crew%20moves", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=roster%20transfer", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=roster%20transfers", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=roster%20handoff", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=roster%20handoffs", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=roster%20move", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=roster%20moves", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=roster-move", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=crew-move", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=roster-transfer", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=crew-transfer", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=roster-handoff", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=crew-handoff", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=preplaunch", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=preplaunches", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=travelprefetch", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=travelprefetches", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=leagueops", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=leagueoperation", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=league-operation", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=leagueoperations", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=league-operations", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=league%20ops", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=league-ops", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=leaguecontrol", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=league%20control", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=league-control", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=leaguectrl", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=communityops", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=communityoperation", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=community-operation", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=communityoperations", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=community-operations", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=community%20ops", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=community-ops", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=communitycontrol", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=community%20control", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=community-control", audit, StringComparison.Ordinal);
        Assert.Contains("prepQuery=communityctrl", audit, StringComparison.Ordinal);
    }

    [Fact]
    public void HubCloseoutAndE2EUseReverseProxiedLocalEdgeAudit()
    {
        string closeoutPath = RepoPaths.FromRoot("scripts", "ai", "hub_closeout.sh");
        string e2ePath = RepoPaths.FromRoot("scripts", "e2e-hub.sh");
        string cleanupPath = RepoPaths.FromRoot("scripts", "cleanup_synthetic_support_cases.py");
        string closeout = File.ReadAllText(closeoutPath);
        string e2e = File.ReadAllText(e2ePath);
        string cleanup = File.ReadAllText(cleanupPath);

        Assert.Contains("HUB_PUBLIC_HOST", closeout, StringComparison.Ordinal);
        Assert.Contains("--forwarded-proto https", closeout, StringComparison.Ordinal);
        Assert.Contains("--verify-http-redirects", closeout, StringComparison.Ordinal);
        Assert.Contains("hub-live-audit.py", e2e, StringComparison.Ordinal);
        Assert.Contains("wait_for_hub_edge", e2e, StringComparison.Ordinal);
        Assert.Contains("--public-host \"$HUB_PUBLIC_HOST\"", e2e, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_HUB_PLAYWRIGHT_FORWARDED_PROTO", e2e, StringComparison.Ordinal);
        Assert.Contains("HUB_PUBLIC_HOST", e2e, StringComparison.Ordinal);
        Assert.Contains("--forwarded-proto https", e2e, StringComparison.Ordinal);
        Assert.Contains("--verify-http-redirects", e2e, StringComparison.Ordinal);
        Assert.Contains("--public-host", cleanup, StringComparison.Ordinal);
        Assert.Contains("--forwarded-proto", cleanup, StringComparison.Ordinal);
        Assert.Contains("X-Forwarded-Proto", cleanup, StringComparison.Ordinal);

        string playwrightPath = RepoPaths.FromRoot("scripts", "e2e-hub-playwright.cjs");
        string playwright = File.ReadAllText(playwrightPath);
        Assert.Contains("?prepQuery=seasonops", playwright, StringComparison.Ordinal);
        Assert.Contains("compact seasonops prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=seasonop", playwright, StringComparison.Ordinal);
        Assert.Contains("compact seasonop prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=season-operation", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen season-operation prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=season-operations", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen season-operations prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=seasoncontrol", playwright, StringComparison.Ordinal);
        Assert.Contains("compact seasoncontrol prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=season(?:%20|\\+)control", playwright, StringComparison.Ordinal);
        Assert.Contains("split season control prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=seasoncontrols", playwright, StringComparison.Ordinal);
        Assert.Contains("compact seasoncontrols prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=seasonctrl", playwright, StringComparison.Ordinal);
        Assert.Contains("compact seasonctrl prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=eventcontrol", playwright, StringComparison.Ordinal);
        Assert.Contains("compact eventcontrol prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=eventcontrols", playwright, StringComparison.Ordinal);
        Assert.Contains("compact eventcontrols prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=eventctrl", playwright, StringComparison.Ordinal);
        Assert.Contains("compact eventctrl prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=eventops", playwright, StringComparison.Ordinal);
        Assert.Contains("compact eventops prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=event(?:%20|\\+)ops", playwright, StringComparison.Ordinal);
        Assert.Contains("split event ops prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=eventop", playwright, StringComparison.Ordinal);
        Assert.Contains("compact eventop prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=event-operation", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen event-operation prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=event-operations", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen event-operations prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=gmops", playwright, StringComparison.Ordinal);
        Assert.Contains("compact gmops prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=gm(?:%20|\\+)ops", playwright, StringComparison.Ordinal);
        Assert.Contains("split gm ops prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=gm-ops", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen gm-ops prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=gmop", playwright, StringComparison.Ordinal);
        Assert.Contains("compact gmop prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=gm-op", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen gm-op prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=gmoperation", playwright, StringComparison.Ordinal);
        Assert.Contains("compact gmoperation prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=gmoperations", playwright, StringComparison.Ordinal);
        Assert.Contains("compact gmoperations prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=gm(?:%20|\\+)operation", playwright, StringComparison.Ordinal);
        Assert.Contains("split gm operation prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=gm-operation", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen gm-operation prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=gm(?:%20|\\+)operations", playwright, StringComparison.Ordinal);
        Assert.Contains("split gm operations prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=gm-operations", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen gm-operations prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=leagueops", playwright, StringComparison.Ordinal);
        Assert.Contains("compact leagueops prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=leagueoperation", playwright, StringComparison.Ordinal);
        Assert.Contains("compact leagueoperation prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=league-operation", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen league-operation prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=leagueoperations", playwright, StringComparison.Ordinal);
        Assert.Contains("compact leagueoperations prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=league-operations", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen league-operations prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=league(?:%20|\\+)ops", playwright, StringComparison.Ordinal);
        Assert.Contains("split league ops prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=league-ops", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen league-ops prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=leaguecontrol", playwright, StringComparison.Ordinal);
        Assert.Contains("compact leaguecontrol prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=league(?:%20|\\+)control", playwright, StringComparison.Ordinal);
        Assert.Contains("split league control prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=league-control", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen league-control prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=leaguectrl", playwright, StringComparison.Ordinal);
        Assert.Contains("compact leaguectrl prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=communityops", playwright, StringComparison.Ordinal);
        Assert.Contains("compact communityops prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=communityoperation", playwright, StringComparison.Ordinal);
        Assert.Contains("compact communityoperation prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=community-operation", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen community-operation prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=communityoperations", playwright, StringComparison.Ordinal);
        Assert.Contains("compact communityoperations prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=community-operations", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen community-operations prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=community(?:%20|\\+)ops", playwright, StringComparison.Ordinal);
        Assert.Contains("split community ops prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=community-ops", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen community-ops prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=communitycontrol", playwright, StringComparison.Ordinal);
        Assert.Contains("compact communitycontrol prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=community(?:%20|\\+)control", playwright, StringComparison.Ordinal);
        Assert.Contains("split community control prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=community-control", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen community-control prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=communityctrl", playwright, StringComparison.Ordinal);
        Assert.Contains("compact communityctrl prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=heat", playwright, StringComparison.Ordinal);
        Assert.Contains("heat continuity prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=oppositions", playwright, StringComparison.Ordinal);
        Assert.Contains("oppositions prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=encounter", playwright, StringComparison.Ordinal);
        Assert.Contains("encounter prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=enemy", playwright, StringComparison.Ordinal);
        Assert.Contains("enemy prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=hostile", playwright, StringComparison.Ordinal);
        Assert.Contains("hostile prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=adversary", playwright, StringComparison.Ordinal);
        Assert.Contains("adversary prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=threat", playwright, StringComparison.Ordinal);
        Assert.Contains("threat prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=opfor", playwright, StringComparison.Ordinal);
        Assert.Contains("opfor prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=opforce", playwright, StringComparison.Ordinal);
        Assert.Contains("opforce prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=contact", playwright, StringComparison.Ordinal);
        Assert.Contains("contact continuity prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=contacts", playwright, StringComparison.Ordinal);
        Assert.Contains("contacts continuity prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=connection", playwright, StringComparison.Ordinal);
        Assert.Contains("connection continuity prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=faction", playwright, StringComparison.Ordinal);
        Assert.Contains("faction continuity prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=journal", playwright, StringComparison.Ordinal);
        Assert.Contains("journal continuity prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=sessionlog", playwright, StringComparison.Ordinal);
        Assert.Contains("sessionlog continuity prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=diary", playwright, StringComparison.Ordinal);
        Assert.Contains("diary continuity prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=downtime", playwright, StringComparison.Ordinal);
        Assert.Contains("downtime continuity prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=aftermath", playwright, StringComparison.Ordinal);
        Assert.Contains("aftermath continuity prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=recap", playwright, StringComparison.Ordinal);
        Assert.Contains("recap continuity prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=return", playwright, StringComparison.Ordinal);
        Assert.Contains("return-loop continuity prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=memory", playwright, StringComparison.Ordinal);
        Assert.Contains("campaign-memory prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=archive", playwright, StringComparison.Ordinal);
        Assert.Contains("campaign-archive prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=history", playwright, StringComparison.Ordinal);
        Assert.Contains("campaign-history prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=timeline", playwright, StringComparison.Ordinal);
        Assert.Contains("campaign-timeline prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=ledger", playwright, StringComparison.Ordinal);
        Assert.Contains("memory-ledger prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=roster", playwright, StringComparison.Ordinal);
        Assert.Contains("roster-movement prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=rostermove", playwright, StringComparison.Ordinal);
        Assert.Contains("compact rostermove query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=rostermoves", playwright, StringComparison.Ordinal);
        Assert.Contains("compact rostermoves prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=crewmove", playwright, StringComparison.Ordinal);
        Assert.Contains("compact crewmove prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=crewmoves", playwright, StringComparison.Ordinal);
        Assert.Contains("compact crewmoves prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=rostertransfer", playwright, StringComparison.Ordinal);
        Assert.Contains("compact rostertransfer prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=rostertransfers", playwright, StringComparison.Ordinal);
        Assert.Contains("compact rostertransfers prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=rosterhandoff", playwright, StringComparison.Ordinal);
        Assert.Contains("compact rosterhandoff prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=rosterhandoffs", playwright, StringComparison.Ordinal);
        Assert.Contains("compact rosterhandoffs prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=crewhandoff", playwright, StringComparison.Ordinal);
        Assert.Contains("compact crewhandoff prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=crewhandoffs", playwright, StringComparison.Ordinal);
        Assert.Contains("compact crewhandoffs prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=crewtransfer", playwright, StringComparison.Ordinal);
        Assert.Contains("compact crewtransfer prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=crewtransfers", playwright, StringComparison.Ordinal);
        Assert.Contains("compact crewtransfers prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=crew(?:%20|\\+)transfer", playwright, StringComparison.Ordinal);
        Assert.Contains("split crew transfer prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=crew(?:%20|\\+)transfers", playwright, StringComparison.Ordinal);
        Assert.Contains("split crew transfers prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=crew(?:%20|\\+)handoff", playwright, StringComparison.Ordinal);
        Assert.Contains("split crew handoff prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=crew(?:%20|\\+)handoffs", playwright, StringComparison.Ordinal);
        Assert.Contains("split crew handoffs prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=crew(?:%20|\\+)move", playwright, StringComparison.Ordinal);
        Assert.Contains("split crew move prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=crew(?:%20|\\+)moves", playwright, StringComparison.Ordinal);
        Assert.Contains("split crew moves prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=roster(?:%20|\\+)transfer", playwright, StringComparison.Ordinal);
        Assert.Contains("split roster transfer prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=roster(?:%20|\\+)transfers", playwright, StringComparison.Ordinal);
        Assert.Contains("split roster transfers prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=roster(?:%20|\\+)handoff", playwright, StringComparison.Ordinal);
        Assert.Contains("split roster handoff prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=roster(?:%20|\\+)handoffs", playwright, StringComparison.Ordinal);
        Assert.Contains("split roster handoffs prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=roster(?:%20|\\+)move", playwright, StringComparison.Ordinal);
        Assert.Contains("split roster move prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=roster(?:%20|\\+)moves", playwright, StringComparison.Ordinal);
        Assert.Contains("split roster moves prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=roster-move", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen roster-move prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=crew-move", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen crew-move prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=roster-transfer", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen roster-transfer prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=crew-transfer", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen crew-transfer prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=roster-handoff", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen roster-handoff prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=crew-handoff", playwright, StringComparison.Ordinal);
        Assert.Contains("hyphen crew-handoff prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=preplaunch", playwright, StringComparison.Ordinal);
        Assert.Contains("compact preplaunch prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=preplaunches", playwright, StringComparison.Ordinal);
        Assert.Contains("compact preplaunches prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=travelprefetch", playwright, StringComparison.Ordinal);
        Assert.Contains("compact travelprefetch prep query", playwright, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=travelprefetches", playwright, StringComparison.Ordinal);
        Assert.Contains("compact travelprefetches prep query", playwright, StringComparison.Ordinal);
    }

    [Fact]
    public void PortalE2EUsesReverseProxiedLocalEdgeHeaders()
    {
        string shellPath = RepoPaths.FromRoot("scripts", "e2e-portal.sh");
        string nodePath = RepoPaths.FromRoot("scripts", "e2e-portal.cjs");

        string shell = File.ReadAllText(shellPath);
        string node = File.ReadAllText(nodePath);

        Assert.Contains("wait_for_portal_edge", shell, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_PORTAL_PUBLIC_HOST", shell, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_PORTAL_FORWARDED_PROTO", shell, StringComparison.Ordinal);
        Assert.Contains("X-Forwarded-Proto", node, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_PORTAL_PUBLIC_HOST", node, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_PORTAL_FORWARDED_PROTO", node, StringComparison.Ordinal);
    }

    [Fact]
    public void HubRequestObservabilityIsWiredIntoProgramAndVerification()
    {
        string programPath = RepoPaths.FromRoot("Chummer.Run.Api", "Program.cs");
        string identityProgramPath = RepoPaths.FromRoot("Chummer.Run.Identity", "Program.cs");
        string verificationProgramPath = RepoPaths.FromRoot("tests", "RunServicesVerification", "Program.cs");
        string backlogPath = RepoPaths.FromRoot("docs", "MIGRATION_BACKLOG.md");
        string middlewarePath = RepoPaths.FromRoot("Chummer.Run.Api", "HubRequestObservabilityMiddleware.cs");

        string program = File.ReadAllText(programPath);
        string identityProgram = File.ReadAllText(identityProgramPath);
        string verificationProgram = File.ReadAllText(verificationProgramPath);
        string backlog = File.ReadAllText(backlogPath);
        string middleware = File.ReadAllText(middlewarePath);

        Assert.Contains("AddHubRequestObservability", program, StringComparison.Ordinal);
        Assert.Contains("UseHubRequestObservability", program, StringComparison.Ordinal);
        Assert.Contains("HubRequestObservabilityVerification.RunAsync", verificationProgram, StringComparison.Ordinal);
        Assert.Contains("MIG-091", backlog, StringComparison.Ordinal);
        Assert.Contains("Response.OnStarting", middleware, StringComparison.Ordinal);
        Assert.Contains("IDENTITY_ENABLE_HTTPS_REDIRECTION", identityProgram, StringComparison.Ordinal);
    }

    [Fact]
    public void NowPageSurfacesCampaignOsLocalProof()
    {
        string serviceCollectionPath = RepoPaths.FromRoot("Chummer.Run.Api", "ServiceCollectionBoundedContextExtensions.cs");
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Now.cshtml");

        string serviceCollection = File.ReadAllText(serviceCollectionPath);
        string controller = File.ReadAllText(controllerPath);
        string viewModel = File.ReadAllText(viewModelPath);
        string view = File.ReadAllText(viewPath);

        Assert.Contains("CampaignOsLocalProofService", serviceCollection, StringComparison.Ordinal);
        Assert.Contains("CampaignOsProof: _campaignOsProof.LoadProof()", controller, StringComparison.Ordinal);
        Assert.Contains("CampaignOsLocalProofSnapshot? CampaignOsProof", viewModel, StringComparison.Ordinal);
        Assert.Contains("Campaign OS local proof", view, StringComparison.Ordinal);
        Assert.Contains("Source-backed local smoke contract", view, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicTrustPagesSurfaceWeeklyPulseAndCaution()
    {
        string serviceCollectionPath = RepoPaths.FromRoot("Chummer.Run.Api", "ServiceCollectionBoundedContextExtensions.cs");
        string servicePath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "PublicTrustPulseService.cs");
        string pulseArtifactServicePath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "WeeklyProductPulseArtifactService.cs");
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");
        string partialPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_PublicTrustPulsePanel.cshtml");
        string bodyPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_PublicTrustPulseBody.cshtml");

        string serviceCollection = File.ReadAllText(serviceCollectionPath);
        string service = File.ReadAllText(servicePath);
        string pulseArtifactService = File.ReadAllText(pulseArtifactServicePath);
        string controller = File.ReadAllText(controllerPath);
        string viewModel = File.ReadAllText(viewModelPath);
        string partial = File.ReadAllText(partialPath);
        string body = File.ReadAllText(bodyPath);

        Assert.Contains("PublicTrustPulseService", serviceCollection, StringComparison.Ordinal);
        Assert.Contains("WeeklyProductPulseArtifactService", serviceCollection, StringComparison.Ordinal);
        Assert.Contains("LoadWeeklyPulseJson", service, StringComparison.Ordinal);
        Assert.Contains("WEEKLY_PRODUCT_PULSE.generated.json", pulseArtifactService, StringComparison.Ordinal);
        Assert.Contains("BuildPublicTrustPulsePanel", controller, StringComparison.Ordinal);
        Assert.Contains("PublicTrustPulsePanelViewModel? TrustPulse", viewModel, StringComparison.Ordinal);
        Assert.Contains("PublicTrustPulseTrendPointViewModel", viewModel, StringComparison.Ordinal);
        Assert.Contains("Weekly trust pulse", partial, StringComparison.Ordinal);
        Assert.Contains("trust-pulse-trend", body, StringComparison.Ordinal);
        Assert.Contains("Current caution", controller, StringComparison.Ordinal);
        Assert.Contains("Closure health", controller, StringComparison.Ordinal);
        Assert.Contains("Progress trend", controller, StringComparison.Ordinal);
        Assert.Contains("BuildTrustPulseProgressTrendSummary", controller, StringComparison.Ordinal);
        Assert.Contains("BuildTrustPulseTrendSamples", controller, StringComparison.Ordinal);
        Assert.Contains("BuildTrustPulseClosureHealthSummary", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void AccountSurfaceReusesSignedInTrustStatusProjection()
    {
        string serviceCollectionPath = RepoPaths.FromRoot("Chummer.Run.Api", "ServiceCollectionBoundedContextExtensions.cs");
        string servicePath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "SignedInTrustStatusService.cs");
        string publicControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string accountControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");
        string accountViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");

        string serviceCollection = File.ReadAllText(serviceCollectionPath);
        string service = File.ReadAllText(servicePath);
        string publicController = File.ReadAllText(publicControllerPath);
        string accountController = File.ReadAllText(accountControllerPath);
        string viewModel = File.ReadAllText(viewModelPath);
        string accountView = File.ReadAllText(accountViewPath);
        string landingView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Landing.cshtml"));
        string faqView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Faq.cshtml"));
        string storyView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "ProductStory.cshtml"));
        string participateView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml"));
        string horizonsView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Horizons.cshtml"));
        string shelfView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Shelf.cshtml"));
        string featureDetailView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "FeatureDetail.cshtml"));
        string downloadDispatchView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "DownloadDispatch.cshtml"));
        string homeView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Home.cshtml"));
        string supportSubmittedView = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "SupportSubmitted.cshtml"));

        Assert.Contains("SignedInTrustStatusService", serviceCollection, StringComparison.Ordinal);
        Assert.Contains("Who can get it now", service, StringComparison.Ordinal);
        Assert.Contains("_signedInTrustStatus.Build", publicController, StringComparison.Ordinal);
        Assert.Contains("_signedInTrustStatus.Build", accountController, StringComparison.Ordinal);
        Assert.Contains("SignedInTrustStatusPanelViewModel? SignedInTrustStatus", viewModel, StringComparison.Ordinal);
        Assert.Contains("SignedInTrustStatusPanelViewModel? SignedInStatus", viewModel, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", accountView, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", landingView, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", faqView, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", storyView, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", participateView, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", horizonsView, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", shelfView, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", featureDetailView, StringComparison.Ordinal);
        Assert.DoesNotContain("_SignedInTrustStatusPanel.cshtml", downloadDispatchView, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", homeView, StringComparison.Ordinal);
        Assert.Contains("_SignedInTrustStatusPanel.cshtml", supportSubmittedView, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicProgressControllerPublishesWeeklyPulseArtifact()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicProgressController.cs");
        string servicePath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "PublicProgressService.cs");
        string auditPath = RepoPaths.FromRoot("scripts", "hub-live-audit.py");

        string controller = File.ReadAllText(controllerPath);
        string service = File.ReadAllText(servicePath);
        string audit = File.ReadAllText(auditPath);

        Assert.Contains("/api/public/weekly-pulse", controller, StringComparison.Ordinal);
        Assert.Contains("LoadWeeklyPulseJson", service, StringComparison.Ordinal);
        Assert.Contains("/api/public/weekly-pulse", audit, StringComparison.Ordinal);
        Assert.Contains("chummer.weekly_product_pulse", audit, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicTrustPagesPublishPrivacyBoundaryArtifact()
    {
        string serviceCollectionPath = RepoPaths.FromRoot("Chummer.Run.Api", "ServiceCollectionBoundedContextExtensions.cs");
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicProgressController.cs");
        string landingControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string accountControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");
        string servicePath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "PublicPrivacyBoundaryService.cs");
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");
        string partialPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_PrivacyBoundaryPanel.cshtml");
        string accountViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Accounts", "Account.cshtml");
        string auditPath = RepoPaths.FromRoot("scripts", "hub-live-audit.py");

        string serviceCollection = File.ReadAllText(serviceCollectionPath);
        string controller = File.ReadAllText(controllerPath);
        string landingController = File.ReadAllText(landingControllerPath);
        string accountController = File.ReadAllText(accountControllerPath);
        string service = File.ReadAllText(servicePath);
        string viewModel = File.ReadAllText(viewModelPath);
        string partial = File.ReadAllText(partialPath);
        string accountView = File.ReadAllText(accountViewPath);
        string audit = File.ReadAllText(auditPath);

        Assert.Contains("PublicPrivacyBoundaryService", serviceCollection, StringComparison.Ordinal);
        Assert.Contains("/api/public/privacy-boundaries", controller, StringComparison.Ordinal);
        Assert.Contains("BuildPanel(\"privacy\")", landingController, StringComparison.Ordinal);
        Assert.Contains("BuildPanel(\"help\")", landingController, StringComparison.Ordinal);
        Assert.Contains("BuildPanel(\"contact\")", landingController, StringComparison.Ordinal);
        Assert.Contains("BuildPanel(\"account\")", accountController, StringComparison.Ordinal);
        Assert.Contains("PRIVACY_AND_RETENTION_BOUNDARIES.md", service, StringComparison.Ordinal);
        Assert.Contains("PUBLIC_TRUST_CONTENT.yaml", service, StringComparison.Ordinal);
        Assert.Contains("PrivacyBoundaryPanelViewModel? PrivacyBoundary", viewModel, StringComparison.Ordinal);
        Assert.Contains("Retention window:", partial, StringComparison.Ordinal);
        Assert.Contains("Model.PrivacyBoundary", accountView, StringComparison.Ordinal);
        Assert.Contains("/api/public/privacy-boundaries", audit, StringComparison.Ordinal);
        Assert.Contains("chummer.public_privacy_boundaries", audit, StringComparison.Ordinal);
    }

    [Fact]
    public void ReleaseWorkflowPublishesApiAndDownloadsMirrorArtifacts()
    {
        string workflowPath = RepoPaths.FromRoot(".github", "workflows", "desktop-downloads-matrix.yml");
        string docsPath = RepoPaths.FromRoot("docs", "ACTIVE_HEAD_RELEASE_ARTIFACTS.md");

        string workflow = File.ReadAllText(workflowPath);
        string docs = File.ReadAllText(docsPath);

        Assert.Contains("- main", workflow, StringComparison.Ordinal);
        Assert.Contains("name: Public Edge Release Artifacts", workflow, StringComparison.Ordinal);
        Assert.Contains("name: release-api-portable", workflow, StringComparison.Ordinal);
        Assert.Contains("Stage public downloads mirror", workflow, StringComparison.Ordinal);
        Assert.Contains("desktop-download-bundle", workflow, StringComparison.Ordinal);
        Assert.DoesNotContain("Chummer.Avalonia/Chummer.Avalonia.csproj", workflow, StringComparison.Ordinal);
        Assert.DoesNotContain("Chummer.Blazor.Desktop/Chummer.Blazor.Desktop.csproj", workflow, StringComparison.Ordinal);
        Assert.Contains("release-api-portable", docs, StringComparison.Ordinal);
        Assert.Contains("checked-in public download mirror", docs, StringComparison.Ordinal);
        Assert.Contains("desktop-download-bundle", docs, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicEdgeGuardrailsDoNotReferenceMissingPortalProject()
    {
        string workflowPath = RepoPaths.FromRoot(".github", "workflows", "docker-architecture-guardrails.yml");
        string composePath = RepoPaths.FromRoot("legacy", "tooling", "docker", "docker-compose.yml");
        string runbookPath = RepoPaths.FromRoot("scripts", "runbook.sh");
        string migrationLoopPath = RepoPaths.FromRoot("scripts", "migration-loop.sh");
        string backlogPath = RepoPaths.FromRoot("docs", "MIGRATION_BACKLOG.md");

        string workflow = File.ReadAllText(workflowPath);
        string compose = File.ReadAllText(composePath);
        string runbook = File.ReadAllText(runbookPath);
        string migrationLoop = File.ReadAllText(migrationLoopPath);
        string backlog = File.ReadAllText(backlogPath);

        Assert.DoesNotContain("Chummer.Portal/Chummer.Portal.csproj", workflow, StringComparison.Ordinal);
        Assert.DoesNotContain("Chummer.Portal/appsettings.json", runbook, StringComparison.Ordinal);
        Assert.Contains("Chummer.Run.Api/Chummer.Run.Api.csproj", workflow, StringComparison.Ordinal);
        Assert.Contains("Chummer.Run.Api/Dockerfile", compose, StringComparison.Ordinal);
        Assert.Contains("chummer.run:host-gateway", compose, StringComparison.Ordinal);
        Assert.Contains("PublicLandingController.cs", runbook, StringComparison.Ordinal);
        Assert.DoesNotContain("chummer-blazor", migrationLoop, StringComparison.Ordinal);
        Assert.Contains("docker-compose.public-edge.yml", migrationLoop, StringComparison.Ordinal);
        Assert.DoesNotContain("CHUMMER_PORTAL_DEV_AUTH_ENABLED", backlog, StringComparison.Ordinal);
        Assert.DoesNotContain("CHUMMER_PORTAL_REQUIRE_AUTH", backlog, StringComparison.Ordinal);
        Assert.Contains("Chummer.Run.Api", backlog, StringComparison.Ordinal);
    }

    [Fact]
    public void WorkspaceBenchmarkGuardrailsAreOwnedByCoreEngineRepo()
    {
        string backlogPath = RepoPaths.FromRoot("docs", "MIGRATION_BACKLOG.md");
        string boundaryPath = RepoPaths.FromRoot("docs", "HOSTED_BOUNDARY.md");
        string coreEngineRoot = Path.GetFullPath(Path.Combine(RepoPaths.Root, "..", "chummer-core-engine"));
        string benchmarkWorkflowPath = Path.Combine(coreEngineRoot, ".github", "workflows", "benchmark-guardrails.yml");
        string benchmarkBudgetPath = Path.Combine(coreEngineRoot, "Chummer.Benchmarks", "workspace-benchmark-budgets.json");

        string backlog = File.ReadAllText(backlogPath);
        string boundary = File.ReadAllText(boundaryPath);

        Assert.Contains("- [x] `MIG-095`", backlog, StringComparison.Ordinal);
        Assert.Contains("../chummer-core-engine/Chummer.Benchmarks", backlog, StringComparison.Ordinal);
        Assert.Contains("Chummer.Benchmarks", boundary, StringComparison.Ordinal);
        Assert.True(File.Exists(benchmarkWorkflowPath), "Core engine owner repo should publish the benchmark CI workflow.");
        Assert.True(File.Exists(benchmarkBudgetPath), "Core engine owner repo should publish benchmark budgets.");
    }
}
