from __future__ import annotations

import unittest
from pathlib import Path


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
FINAL_GOLD_JANITOR = RUN_SERVICES_ROOT / "scripts" / "final_gold_janitor.py"
VERIFY_SCRIPT = RUN_SERVICES_ROOT / "scripts" / "ai" / "verify.sh"
RELEASE_READY_SCRIPT = Path("/docker/chummercomplete/scripts/release/verify_chummer6_release_ready.sh")
PORTAL_E2E_SCRIPT = RUN_SERVICES_ROOT / "scripts" / "e2e-portal.cjs"
PARTIZIPATE_RUNTIME_FALLBACK_SCRIPT = RUN_SERVICES_ROOT / "scripts" / "verify_partizipate_runtime_fallback.cjs"
PUBLIC_LANDING_CONTROLLER = RUN_SERVICES_ROOT / "Chummer.Run.Api" / "Controllers" / "PublicLandingController.cs"


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
        self.assertIn('CHUMMER_PORTAL_REQUIRE_BLAZOR="${CHUMMER_HUB_PUBLIC_REQUIRE_BLAZOR:-0}"', text)
        self.assertIn('node "$ROOT_DIR/scripts/e2e-portal.cjs" >/dev/null', text)
        self.assertIn('node "$ROOT_DIR/scripts/verify_partizipate_runtime_fallback.cjs" --base-url "${CHUMMER_HUB_PUBLIC_ORIGIN_GATE_BASE_URL:-https://chummer.run}" >/dev/null', text)
        self.assertIn('run_slice_safe_dotnet_test "FullyQualifiedName~HubPageChromeServiceTests"', text)

    def test_release_ready_script_runs_participate_billing_honesty_gate(self) -> None:
        text = RELEASE_READY_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("verify_live_surface_parity", text)
        self.assertIn("python3 scripts/verify_live_surface_parity.py --base-url ${CHUMMER_PUBLIC_BASE_URL:-https://chummer.run}", text)
        self.assertIn("verify_public_portal_e2e", text)
        self.assertIn("CHUMMER_PORTAL_BASE_URL=${CHUMMER_PUBLIC_BASE_URL:-https://chummer.run}", text)
        self.assertIn("CHUMMER_PORTAL_REQUIRE_BLAZOR=${CHUMMER_PUBLIC_REQUIRE_BLAZOR:-0}", text)
        self.assertIn("node scripts/e2e-portal.cjs", text)
        self.assertIn("verify_partizipate_runtime_fallback", text)
        self.assertIn("node scripts/verify_partizipate_runtime_fallback.cjs --base-url ${CHUMMER_PUBLIC_BASE_URL:-https://chummer.run}", text)
        self.assertIn("verify_participate_billing_honesty", text)
        self.assertIn("python3 scripts/materialize_participate_billing_honesty.py --completion-dir .codex-studio/published", text)
        self.assertIn("python3 scripts/verify_participate_billing_honesty.py --completion-dir .codex-studio/published", text)
        self.assertIn("verify_account_handoff_runtime_config", text)
        self.assertIn("python3 scripts/verify_account_handoff_runtime_config.py", text)

    def test_final_gold_janitor_requires_and_materializes_participate_billing_honesty(self) -> None:
        text = FINAL_GOLD_JANITOR.read_text(encoding="utf-8")
        self.assertIn('"participate_billing_honesty"', text)
        self.assertIn('PUBLISHED_ROOT / "PARTICIPATE_BILLING_HONESTY.generated.json"', text)
        self.assertIn('["python3", "scripts/materialize_participate_billing_honesty.py", "--completion-dir", str(PUBLISHED_ROOT)]', text)
        self.assertIn('"account_handoff_runtime_config"', text)
        self.assertIn('PUBLISHED_ROOT / "ACCOUNT_HANDOFF_RUNTIME_CONFIG.generated.json"', text)
        self.assertIn('["python3", "scripts/verify_account_handoff_runtime_config.py"]', text)

    def test_portal_e2e_covers_public_participate_surface(self) -> None:
        text = PORTAL_E2E_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("text.includes('Download Chummer')", text)
        self.assertIn("text.includes('Current public installer')", text)
        self.assertIn("text.includes('Watch 90 sec')", text)
        self.assertIn("text.includes('Detail gallery')", text)
        self.assertIn("text.includes('Use this page for dossiers, recaps, and release details.')", text)
        self.assertIn("text.includes('Download script')", text)
        self.assertIn("url: `${baseUrl}/participate`", text)
        self.assertIn("text.includes('What should Chummer do next?')", text)
        self.assertIn("text.includes('Public requests, clear bugs, useful ideas.')", text)
        self.assertIn("text.includes('Current requests')", text)
        self.assertIn("text.includes('Board is live.')", text)
        self.assertIn("text.includes('data-chummer-participate-frame')", text)
        self.assertIn("url: `${baseUrl}/participate/frame`", text)
        self.assertIn("text.includes('<base href=\"/participate/board/\"')", text)
        self.assertIn("!text.includes('productlift.dev')", text)
        self.assertIn("!text.includes('data-chummer-board-skin')", text)
        self.assertIn("!text.includes('ProductLift')", text)

    def test_portal_e2e_covers_help_status_contact_and_public_billing(self) -> None:
        text = PORTAL_E2E_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("url: `${baseUrl}/help`", text)
        self.assertIn("text.includes('What is wrong?')", text)
        self.assertIn("text.includes('Account recovery')", text)
        self.assertIn("url: `${baseUrl}/status`", text)
        self.assertIn("text.includes('Windows and Linux downloads are live.')", text)
        self.assertIn("!text.includes('Checks passed')", text)
        self.assertIn("url: `${baseUrl}/contact`", text)
        self.assertIn("text.includes('Discord')", text)
        self.assertIn("text.includes('Send support request')", text)
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
        self.assertIn("function isBlazorFallback(text)", text)
        self.assertIn("requireBlazor ? isBlazorReady(text) : (isBlazorReady(text) || isBlazorFallback(text))", text)
        self.assertIn("delegated-not-ready:", text)
        self.assertIn("portal E2E completed with delegated warnings", text)

    def test_partizipate_runtime_fallback_gate_forces_vendor_error_state(self) -> None:
        text = PARTIZIPATE_RUNTIME_FALLBACK_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("HOSTED_BOARD_SHELL_VISIBLE_BUDGET_MS = 2500", text)
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
        self.assertIn("iframe[data-chummer-participate-frame]", text)
        self.assertIn("should keep the hosted board inside the first-party shell", text)
        self.assertIn("should keep the request entry point visible", text)
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
