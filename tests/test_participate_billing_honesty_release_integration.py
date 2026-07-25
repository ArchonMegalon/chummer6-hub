from __future__ import annotations

import unittest
from pathlib import Path


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
FINAL_GOLD_JANITOR = RUN_SERVICES_ROOT / "scripts" / "final_gold_janitor.py"
VERIFY_SCRIPT = RUN_SERVICES_ROOT / "scripts" / "ai" / "verify.sh"
RELEASE_READY_SCRIPT = Path("/docker/chummercomplete/scripts/release/verify_chummer6_release_ready.sh")
RELEASE_READY_MATERIALIZER = RUN_SERVICES_ROOT / "scripts" / "materialize_release_ready_receipt.py"
RELEASE_DRESS_REHEARSAL_SCRIPT = RUN_SERVICES_ROOT / "scripts" / "release_dress_rehearsal.sh"
PORTAL_E2E_SCRIPT = RUN_SERVICES_ROOT / "scripts" / "e2e-portal.cjs"
PARTIZIPATE_RUNTIME_FALLBACK_SCRIPT = RUN_SERVICES_ROOT / "scripts" / "verify_partizipate_runtime_fallback.cjs"
PUBLIC_LANDING_CONTROLLER = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs"
PUBLIC_EDGE_COMPOSE = RUN_SERVICES_ROOT / "docker-compose.public-edge.yml"


class ParticipateBillingHonestyReleaseIntegrationTests(unittest.TestCase):
    def test_verify_script_materializes_participate_billing_honesty(self) -> None:
        text = VERIFY_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('python3 scripts/materialize_participate_billing_honesty.py --completion-dir "$CHUMMER_COMPLETION_DIR"', text)
        self.assertIn('python3 "$ROOT_DIR/scripts/materialize_participate_billing_honesty.py" --completion-dir "$CHUMMER_COMPLETION_DIR" >/dev/null', text)
        self.assertIn('python3 "$ROOT_DIR/scripts/verify_participate_billing_honesty.py" --completion-dir "$CHUMMER_COMPLETION_DIR" >/dev/null', text)
        self.assertIn('python3 -m unittest discover -s "$ROOT_DIR/tests" -p \'test_account_handoff_runtime_config.py\' >/dev/null', text)
        self.assertIn('python3 "$ROOT_DIR/scripts/verify_account_handoff_runtime_config.py" >/dev/null', text)
        self.assertIn('python3 -m pytest "$ROOT_DIR/tests/test_public_minimal_humanized_surface.py" "$ROOT_DIR/tests/test_participate_codex_guest_fallback.py" -q >/dev/null', text)
        self.assertIn('CHUMMER_PORTAL_BASE_URL="${CHUMMER_HUB_PUBLIC_ORIGIN_GATE_BASE_URL:-https://chummer.run}"', text)
        self.assertIn('python3 "$ROOT_DIR/scripts/materialize_windows_installer_visual_audit_intake_request.py" --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json >/dev/null', text)
        self.assertIn('python3 "$ROOT_DIR/scripts/verify_windows_installer_visual_audit_intake_request.py" >/dev/null', text)
        self.assertIn('run_expected_external_artifact_gate \\\n  "Native Windows installer visual proof is waiting.', text)
        self.assertIn('python3 "$ROOT_DIR/scripts/auto_import_windows_installer_gold_proof.py" \\', text)
        self.assertIn('--intake-request .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json', text)
        self.assertIn('--output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json', text)
        self.assertIn('AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG="${CHUMMER_AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG:-$ROOT_DIR/.state/auth_signin_automation_paused.flag}"', text)
        self.assertIn('if [[ -f "$AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG" ]]; then', text)
        self.assertIn('echo "skipping google oauth auth automation in verify.sh: auth/sign-in automation is paused at $AUTH_SIGNIN_AUTOMATION_PAUSE_FLAG" >&2', text)
        self.assertIn('python3 "$ROOT_DIR/scripts/materialize_google_oauth_linking_operator_evidence_request.py" --base-url "${CHUMMER_HUB_PUBLIC_ORIGIN_GATE_BASE_URL:-https://chummer.run}" >/dev/null', text)
        self.assertIn('python3 "$ROOT_DIR/scripts/verify_google_oauth_linking_operator_evidence_request.py" >/dev/null', text)
        self.assertIn('run_expected_external_artifact_gate \\\n    "Google OAuth operator evidence is waiting.', text)
        self.assertIn('python3 "$ROOT_DIR/scripts/auto_import_google_oauth_linking_operator_evidence.py" \\', text)
        self.assertIn('--intake-request .codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json', text)
        self.assertIn('--output .codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT.generated.json', text)
        self.assertIn('python3 "$ROOT_DIR/scripts/materialize_google_oauth_linking_proof.py" --base-url "${CHUMMER_HUB_PUBLIC_ORIGIN_GATE_BASE_URL:-https://chummer.run}" >/dev/null', text)
        self.assertIn('python3 "$ROOT_DIR/scripts/verify_google_oauth_linking_proof.py" >/dev/null', text)
        self.assertIn('CHUMMER_PORTAL_REQUIRE_BLAZOR="${CHUMMER_HUB_PUBLIC_REQUIRE_BLAZOR:-1}"', text)
        self.assertIn('node "$ROOT_DIR/scripts/e2e-portal.cjs" >/dev/null', text)
        self.assertIn('node "$ROOT_DIR/scripts/verify_partizipate_runtime_fallback.cjs" --base-url "${CHUMMER_HUB_PUBLIC_ORIGIN_GATE_BASE_URL:-https://chummer.run}" >/dev/null', text)
        self.assertIn('python3 "$ROOT_DIR/scripts/materialize_release_ready_receipt.py" --force-global-verifier >/dev/null', text)
        self.assertIn('env -u PYTHONPATH PATH=/usr/bin:/bin python3 "$ROOT_DIR/scripts/materialize_release_ready_receipt.py" --force-global-verifier', text)
        self.assertIn('run_slice_safe_dotnet_test "FullyQualifiedName~HubPageChromeServiceTests"', text)
        self.assertLess(
            text.index('python3 "$ROOT_DIR/scripts/materialize_google_oauth_linking_proof.py" --base-url "${CHUMMER_HUB_PUBLIC_ORIGIN_GATE_BASE_URL:-https://chummer.run}" >/dev/null'),
            text.index('python3 "$ROOT_DIR/scripts/materialize_release_ready_receipt.py" --force-global-verifier >/dev/null'),
        )
        self.assertLess(
            text.index('node "$ROOT_DIR/scripts/verify_partizipate_runtime_fallback.cjs" --base-url "${CHUMMER_HUB_PUBLIC_ORIGIN_GATE_BASE_URL:-https://chummer.run}" >/dev/null'),
            text.index('python3 "$ROOT_DIR/scripts/materialize_release_ready_receipt.py" --force-global-verifier >/dev/null'),
        )
        self.assertLess(
            text.index('python3 "$ROOT_DIR/scripts/materialize_release_ready_receipt.py" --force-global-verifier >/dev/null'),
            text.index('run_slice_safe_dotnet_test "FullyQualifiedName~HubPageChromeServiceTests"'),
        )

    def test_release_ready_script_runs_participate_billing_honesty_gate(self) -> None:
        launcher = RELEASE_READY_SCRIPT.read_text(encoding="utf-8")
        materializer = RELEASE_READY_MATERIALIZER.read_text(encoding="utf-8")

        # The root entrypoint is intentionally a tiny, fail-closed launcher. The
        # delegated materializer owns the governed gate declarations and runner.
        self.assertIn('if sys.flags.isolated != 1:', launcher)
        self.assertIn('MATERIALIZER = ROOT / "chummer.run-services/scripts/materialize_release_ready_receipt.py"', launcher)
        self.assertIn('"--run-authoritative-controller"', launcher)
        self.assertIn("os.execve(", launcher)
        self.assertIn("FORBIDDEN_CODE_LOADING_ENV", launcher)

        required_gate_names = (
            "verify_live_surface_parity",
            "verify_windows_installer_visual_audit_intake_request",
            "verify_flagship_product_readiness",
            "verify_public_edge_postdeploy_gate",
            "verify_public_portal_e2e",
            "verify_partizipate_runtime_fallback",
            "verify_participate_billing_honesty",
            "verify_account_handoff_runtime_config",
            "verify_google_oauth_linking_operator_evidence_request",
            "verify_google_oauth_linking_proof",
            "verify_ea_operator_readiness",
            "verify_mymedia_public_surface",
            "verify_teable_important_work_sync",
            "verify_operator_release_dashboard",
        )
        for gate_name in required_gate_names:
            self.assertIn(f'"{gate_name}"', materializer)

        required_entrypoints = (
            "verify_live_surface_parity.py",
            "materialize_windows_installer_visual_audit_intake_request.py",
            "verify_windows_installer_visual_audit_intake_request.py",
            "auto_import_windows_installer_gold_proof.py",
            "verify_flagship_product_readiness_gate.py",
            "verify_public_edge_postdeploy_gate.py",
            "e2e-portal.cjs",
            "verify_partizipate_runtime_fallback.cjs",
            "materialize_participate_billing_honesty.py",
            "verify_participate_billing_honesty.py",
            "verify_account_handoff_runtime_config.py",
            "materialize_google_oauth_linking_operator_evidence_request.py",
            "verify_google_oauth_linking_operator_evidence_request.py",
            "auto_import_google_oauth_linking_operator_evidence.py",
            "materialize_google_oauth_linking_proof.py",
            "verify_google_oauth_linking_proof.py",
            "materialize_ea_operator_readiness.py",
            "verify_ea_operator_readiness.py",
            "materialize_mymedia_public_surface.py",
            "verify_mymedia_public_surface.py",
            "sync_important_work_to_teable.py",
        )
        for entrypoint in required_entrypoints:
            self.assertIn(entrypoint, materializer)

        self.assertIn('"CHUMMER_RELEASE_READY_GATE_TIMEOUT_SECONDS": "900"', materializer)
        self.assertIn('"CHUMMER_RELEASE_READY_GUIDE_GATE_TIMEOUT_SECONDS": "1800"', materializer)
        self.assertIn("START {gate_name} timeout={gate['timeout_seconds']}s", materializer)
        self.assertIn("FAIL {gate_name}: timed out after {gate['timeout_seconds']}s", materializer)
        self.assertIn("PASS {gate_name} execution_binding_sha256=", materializer)
        self.assertIn("--require-downloads-status-playwright", materializer)
        self.assertIn("--require-mobile-pwa-viewport-playwright", materializer)
        self.assertIn("--require-pwa-offline-cache-playwright", materializer)
        self.assertIn("--require-frontdoor-navigation-playwright", materializer)

        gate_declaration = materializer[
            materializer.index("REQUIRED_RELEASE_VERIFIER_GATES = ("):
            materializer.index("\ndef isolated_python_argv(")
        ]
        for earlier, later in zip(required_gate_names, required_gate_names[1:]):
            self.assertLess(gate_declaration.index(f'"{earlier}"'), gate_declaration.index(f'"{later}"'))

    def test_release_dress_rehearsal_refreshes_mymedia_public_surface_before_dashboard(self) -> None:
        text = RELEASE_DRESS_REHEARSAL_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("python3 scripts/materialize_windows_installer_visual_audit_intake_request.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json", text)
        self.assertIn("python3 scripts/verify_windows_installer_visual_audit_intake_request.py", text)
        self.assertIn("python3 scripts/auto_import_windows_installer_gold_proof.py --intake-request .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json --wait-seconds 0", text)
        self.assertIn("python3 scripts/materialize_google_oauth_linking_operator_evidence_request.py --base-url \"$BASE_URL\"", text)
        self.assertIn("python3 scripts/verify_google_oauth_linking_operator_evidence_request.py", text)
        self.assertIn("python3 scripts/auto_import_google_oauth_linking_operator_evidence.py --intake-request .codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json --output .codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT.generated.json --wait-seconds 0", text)
        self.assertIn("python3 scripts/materialize_google_oauth_linking_proof.py --base-url \"$BASE_URL\"", text)
        self.assertIn("python3 scripts/verify_google_oauth_linking_proof.py", text)
        self.assertIn("python3 scripts/materialize_mymedia_public_surface.py", text)
        self.assertIn("python3 scripts/verify_mymedia_public_surface.py", text)
        self.assertIn("python3 scripts/sync_important_work_to_teable.py --sync", text)
        self.assertIn("python3 scripts/materialize_release_ready_receipt.py --force-global-verifier", text)
        self.assertIn("env -u PYTHONPATH PATH=/usr/bin:/bin python3 scripts/materialize_release_ready_receipt.py --force-global-verifier", text)
        self.assertLess(
            text.index("python3 scripts/materialize_windows_installer_visual_audit_intake_request.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"),
            text.index("python3 scripts/materialize_operator_release_dashboard.py"),
        )
        self.assertLess(
            text.index("python3 scripts/verify_windows_installer_visual_audit_intake_request.py"),
            text.index("python3 scripts/auto_import_windows_installer_gold_proof.py --intake-request .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json --wait-seconds 0"),
        )
        self.assertLess(
            text.index("python3 scripts/auto_import_windows_installer_gold_proof.py --intake-request .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json --wait-seconds 0"),
            text.index("python3 scripts/materialize_operator_release_dashboard.py"),
        )
        self.assertLess(
            text.index("python3 scripts/materialize_google_oauth_linking_operator_evidence_request.py --base-url \"$BASE_URL\""),
            text.index("python3 scripts/verify_google_oauth_linking_operator_evidence_request.py"),
        )
        self.assertLess(
            text.index("python3 scripts/verify_google_oauth_linking_operator_evidence_request.py"),
            text.index("python3 scripts/auto_import_google_oauth_linking_operator_evidence.py --intake-request .codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json --output .codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT.generated.json --wait-seconds 0"),
        )
        self.assertLess(
            text.index("python3 scripts/auto_import_google_oauth_linking_operator_evidence.py --intake-request .codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json --output .codex-studio/published/GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT.generated.json --wait-seconds 0"),
            text.index("python3 scripts/materialize_google_oauth_linking_proof.py --base-url \"$BASE_URL\""),
        )
        self.assertLess(
            text.index("python3 scripts/verify_google_oauth_linking_proof.py"),
            text.index("python3 scripts/materialize_operator_release_dashboard.py"),
        )
        self.assertLess(
            text.index("python3 scripts/sync_important_work_to_teable.py --sync"),
            text.index("python3 scripts/materialize_operator_release_dashboard.py"),
        )
        self.assertLess(
            text.index("python3 scripts/materialize_release_ready_receipt.py --force-global-verifier"),
            text.index("python3 scripts/materialize_operator_release_dashboard.py"),
        )
        self.assertLess(
            text.index("python3 scripts/materialize_mymedia_public_surface.py"),
            text.index("python3 scripts/materialize_operator_release_dashboard.py"),
        )
        self.assertLess(
            text.index("python3 scripts/verify_mymedia_public_surface.py"),
            text.index("python3 scripts/materialize_operator_release_dashboard.py"),
        )

    def test_public_edge_requires_brilliant_directories_checkout_by_default(self) -> None:
        text = PUBLIC_EDGE_COMPOSE.read_text(encoding="utf-8")

        self.assertIn(
            "CHUMMER_REQUIRE_BRILLIANT_DIRECTORIES_CHECKOUT: ${CHUMMER_REQUIRE_BRILLIANT_DIRECTORIES_CHECKOUT:-true}",
            text,
        )
        self.assertIn("BRILLIANT_DIRECTORIES_SUPPORTER_PLAN_URL: ${BRILLIANT_DIRECTORIES_SUPPORTER_PLAN_URL:-}", text)
        self.assertIn("BRILLIANT_DIRECTORIES_MEMBER_PORTAL_URL: ${BRILLIANT_DIRECTORIES_MEMBER_PORTAL_URL:-}", text)

    def test_final_gold_janitor_requires_and_materializes_participate_billing_honesty(self) -> None:
        text = FINAL_GOLD_JANITOR.read_text(encoding="utf-8")
        self.assertIn('"participate_billing_honesty"', text)
        self.assertIn('PUBLISHED_ROOT / "PARTICIPATE_BILLING_HONESTY.generated.json"', text)
        self.assertIn('"CHUMMER_FINAL_GOLD_PARTICIPATE_BILLING_TIMEOUT_SECONDS"', text)
        self.assertIn('"300"', text)
        self.assertIn('"scripts/materialize_participate_billing_honesty.py"', text)
        self.assertIn('"--reuse-existing-receipts"', text)
        self.assertIn('"--reuse-receipt-max-age-hours"', text)
        self.assertIn('str(RECRAWL_MAX_AGE_HOURS)', text)
        self.assertIn('"account_handoff_runtime_config"', text)
        self.assertIn('PUBLISHED_ROOT / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json"', text)
        self.assertIn('["python3", "scripts/verify_account_handoff_runtime_config.py"]', text)

    def test_portal_e2e_covers_public_participate_surface(self) -> None:
        text = PORTAL_E2E_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("text.includes('Download Chummer')", text)
        self.assertIn("text.includes('Sign in first')", text)
        self.assertIn("text.includes('site-open-chummer-menu__button--disabled')", text)
        self.assertIn("text.includes('Detail gallery')", text)
        self.assertIn("text.includes('Use this page for dossiers, recaps, and release details.')", text)
        self.assertIn("text.includes('Download script')", text)
        self.assertIn("url: `${baseUrl}/participate`", text)
        self.assertIn("text.includes('Participate')", text)
        self.assertIn("!text.includes('Public requests, clear bugs, useful ideas.')", text)
        self.assertIn("(text.includes('data-chummer-participate-frame') || text.includes('Board offline right now'))", text)
        self.assertIn("url: `${baseUrl}/participate/board?embed=1`", text)
        self.assertIn("text.includes('<base href=\"/participate/board/\"')", text)
        self.assertIn("!text.includes('productlift.dev')", text)
        self.assertIn("!text.includes('data-chummer-board-skin')", text)
        self.assertIn("!text.includes('ProductLift')", text)

    def test_portal_e2e_covers_help_status_contact_and_public_billing(self) -> None:
        text = PORTAL_E2E_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("url: `${baseUrl}/help`", text)
        self.assertIn("text.includes('How can we help?')", text)
        self.assertIn("text.includes('Account recovery')", text)
        self.assertIn("url: `${baseUrl}/status`", text)
        self.assertIn("function hasStatusDecisionSurface(text)", text)
        self.assertIn("text.includes('Preview downloads')", text)
        self.assertIn("text.includes('Stable downloads')", text)
        self.assertIn("text.includes('Downloads paused')", text)
        self.assertIn("text.includes('Version ')", text)
        self.assertIn("url: `${baseUrl}/contact`", text)
        self.assertIn("text.includes('Chummer5 Discord')", text)
        self.assertIn("!text.includes('Send support request')", text)
        self.assertIn("url: `${baseUrl}/account/billing`", text)
        self.assertIn("function isGuestBillingSurface(text)", text)
        self.assertIn("assert: text => isGuestBillingSurface(text)", text)

    def test_portal_e2e_reports_delegated_blazor_without_blocking_required_routes(self) -> None:
        text = PORTAL_E2E_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("const requireBlazor =", text)
        self.assertIn("process.env.CHUMMER_PORTAL_REQUIRE_BLAZOR", text)
        self.assertIn("url: `${baseUrl}/blazor/`", text)
        self.assertIn("label: requireBlazor ? 'blazor' : 'delegated-blazor'", text)
        self.assertIn("required: requireBlazor", text)
        self.assertIn("function isBlazorReady(text)", text)
        self.assertIn("function isBlazorRootRouteReady(response)", text)
        self.assertIn("resolvedUrl.includes('command=character_roster')", text)
        self.assertIn("function isBlazorFallback(text)", text)
        self.assertIn("isBlazorRootRouteReady(response)", text)
        self.assertIn("requireBlazor ? isBlazorReady(text) : (isBlazorReady(text) || isBlazorFallback(text))", text)
        self.assertIn("delegated-not-ready:", text)
        self.assertIn("portal E2E completed with delegated warnings", text)

    def test_portal_e2e_covers_blazor_new_runner_menu_interaction(self) -> None:
        text = PORTAL_E2E_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("url: `${baseUrl}/blazor/app?command=new_character`", text)
        self.assertIn("async function runBlazorNewRunnerMenuCheck(page, check)", text)
        self.assertIn("await page.waitForSelector('#dialogBackdrop[data-dialog-id=\"dialog.new_character\"]', { timeout: 60000 });", text)
        self.assertIn("label[data-field-id=\"newCharacterBuildMethod\"] select", text)
        self.assertIn("button.menu-btn.classic-menu-button", text)
        self.assertIn("button.menu-item.classic-menu-item", text)
        self.assertIn("Expected File menu to expand while the startup dialog is open", text)
        self.assertIn("Expected File -> New runner to reopen the startup dialog with Priority selected", text)
        self.assertIn("Expected File menu to collapse after selecting New runner", text)

    def test_partizipate_runtime_fallback_gate_forces_vendor_error_state(self) -> None:
        text = PARTIZIPATE_RUNTIME_FALLBACK_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("HOSTED_BOARD_SHELL_VISIBLE_BUDGET_MS = 6000", text)
        self.assertIn("HOSTED_BOARD_DETAIL_FETCH_BUDGET_MS = 4000", text)
        self.assertIn("chromium.launch", text)
        self.assertIn("'--no-sandbox'", text)
        self.assertIn("assertBoardShell(page, '/participate')", text)
        self.assertIn("assertBoardShell(page, '/participate/board')", text)
        self.assertIn("visibleDurationMs <=", text)
        self.assertIn("detailResponse.durationMs <=", text)
        self.assertIn("timings.detailFetchMs = detailResponse.durationMs", text)
        self.assertIn("participateShellVisibleMs", text)
        self.assertIn("participateBoardShellVisibleMs", text)
        self.assertIn("Something went wrong|Could not load posts|Network error|support@productlift", text)
        self.assertIn("should host the same-origin ProductLift board frame", text)
        self.assertIn("should resolve to the embedded first-party board document", text)
        self.assertIn("instead of nesting another frame", text)
        self.assertIn("request detail should provide a first-party way back to the request list", text)
        self.assertIn("provider menubar must stay hidden in the proxied request detail", text)
        self.assertIn("provider search mount must stay hidden in the proxied request detail", text)
        self.assertIn("vendor error copy must not be visible in the proxied request detail", text)

    def test_hosted_board_wrapper_uses_throttled_dom_scrub_passes(self) -> None:
        text = PUBLIC_LANDING_CONTROLLER.read_text(encoding="utf-8")

        self.assertIn("let chromePassScheduled = false;", text)
        self.assertIn("const scheduleChromePass = function () {", text)
        self.assertIn("window.requestAnimationFrame(function () {", text)
        self.assertIn("window.setTimeout(function () {", text)
        self.assertIn("runChromePass(true);", text)
        self.assertIn("let failurePassScheduled = false;", text)
        self.assertIn("const scheduleFailurePass = function () {", text)
        self.assertIn("document.body.innerText", text)
        self.assertIn("window.setTimeout(suppressHostedError, 1500);", text)


if __name__ == "__main__":
    unittest.main()
