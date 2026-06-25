from __future__ import annotations

import unittest
from pathlib import Path


RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
FINAL_GOLD_JANITOR = RUN_SERVICES_ROOT / "scripts" / "final_gold_janitor.py"
VERIFY_SCRIPT = RUN_SERVICES_ROOT / "scripts" / "ai" / "verify.sh"
RELEASE_READY_SCRIPT = Path("/docker/chummercomplete/scripts/release/verify_chummer6_release_ready.sh")
PORTAL_E2E_SCRIPT = RUN_SERVICES_ROOT / "scripts" / "e2e-portal.cjs"
PARTIZIPATE_RUNTIME_FALLBACK_SCRIPT = RUN_SERVICES_ROOT / "scripts" / "verify_partizipate_runtime_fallback.cjs"


class ParticipateBillingHonestyReleaseIntegrationTests(unittest.TestCase):
    def test_verify_script_materializes_participate_billing_honesty(self) -> None:
        text = VERIFY_SCRIPT.read_text(encoding="utf-8")
        self.assertIn('python3 scripts/materialize_participate_billing_honesty.py --completion-dir "$CHUMMER_COMPLETION_DIR"', text)
        self.assertIn('python3 "$ROOT_DIR/scripts/materialize_participate_billing_honesty.py" --completion-dir "$CHUMMER_COMPLETION_DIR" >/dev/null', text)
        self.assertIn('python3 "$ROOT_DIR/scripts/verify_participate_billing_honesty.py" --completion-dir "$CHUMMER_COMPLETION_DIR" >/dev/null', text)
        self.assertIn('python3 -m pytest "$ROOT_DIR/tests/test_public_minimal_humanized_surface.py" "$ROOT_DIR/tests/test_participate_codex_guest_fallback.py" -q >/dev/null', text)
        self.assertIn('CHUMMER_PORTAL_BASE_URL="${CHUMMER_HUB_PUBLIC_ORIGIN_GATE_BASE_URL:-https://chummer.run}"', text)
        self.assertIn('node "$ROOT_DIR/scripts/e2e-portal.cjs" >/dev/null', text)
        self.assertIn('node "$ROOT_DIR/scripts/verify_partizipate_runtime_fallback.cjs" --base-url "${CHUMMER_HUB_PUBLIC_ORIGIN_GATE_BASE_URL:-https://chummer.run}" >/dev/null', text)
        self.assertIn('run_slice_safe_dotnet_test "FullyQualifiedName~HubPageChromeServiceTests"', text)

    def test_release_ready_script_runs_participate_billing_honesty_gate(self) -> None:
        text = RELEASE_READY_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("verify_live_surface_parity", text)
        self.assertIn("python3 scripts/verify_live_surface_parity.py --base-url ${CHUMMER_PUBLIC_BASE_URL:-https://chummer.run}", text)
        self.assertIn("verify_public_portal_e2e", text)
        self.assertIn("CHUMMER_PORTAL_BASE_URL=${CHUMMER_PUBLIC_BASE_URL:-https://chummer.run}", text)
        self.assertIn("node scripts/e2e-portal.cjs", text)
        self.assertIn("verify_partizipate_runtime_fallback", text)
        self.assertIn("node scripts/verify_partizipate_runtime_fallback.cjs --base-url ${CHUMMER_PUBLIC_BASE_URL:-https://chummer.run}", text)
        self.assertIn("verify_participate_billing_honesty", text)
        self.assertIn("python3 scripts/materialize_participate_billing_honesty.py --completion-dir .codex-studio/published", text)
        self.assertIn("python3 scripts/verify_participate_billing_honesty.py --completion-dir .codex-studio/published", text)

    def test_final_gold_janitor_requires_and_materializes_participate_billing_honesty(self) -> None:
        text = FINAL_GOLD_JANITOR.read_text(encoding="utf-8")
        self.assertIn('"participate_billing_honesty"', text)
        self.assertIn('PUBLISHED_ROOT / "PARTICIPATE_BILLING_HONESTY.generated.json"', text)
        self.assertIn('["python3", "scripts/materialize_participate_billing_honesty.py", "--completion-dir", str(PUBLISHED_ROOT)]', text)

    def test_portal_e2e_covers_public_participate_surface(self) -> None:
        text = PORTAL_E2E_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("text.includes('Download Chummer')", text)
        self.assertIn("text.includes('Current public installer')", text)
        self.assertIn("text.includes('Watch 90 sec')", text)
        self.assertIn("text.includes('Detail gallery')", text)
        self.assertIn("text.includes('Use this page for dossiers, recaps, and release details.')", text)
        self.assertIn("text.includes('Current release')", text)
        self.assertIn("text.includes('Updated')", text)
        self.assertIn("url: `${baseUrl}/participate`", text)
        self.assertIn("!text.includes('Requests, votes, and shipped work.')", text)
        self.assertIn("text.includes('participate-board')", text)
        self.assertIn("!text.includes('ProductLift')", text)

    def test_portal_e2e_reports_delegated_blazor_without_blocking_required_routes(self) -> None:
        text = PORTAL_E2E_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("url: `${baseUrl}/blazor/`", text)
        self.assertIn("required: false", text)
        self.assertIn("label: 'delegated-blazor'", text)
        self.assertIn("delegated-not-ready:", text)
        self.assertIn("portal E2E completed with delegated warnings", text)

    def test_partizipate_runtime_fallback_gate_forces_vendor_error_state(self) -> None:
        text = PARTIZIPATE_RUNTIME_FALLBACK_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("chromium.launch", text)
        self.assertIn("'--no-sandbox'", text)
        self.assertIn("context.route('**/participate/board**'", text)
        self.assertIn("Something went wrong on our side.", text)
        self.assertIn("Could not load posts.", text)
        self.assertIn("Network error while loading tab configuration.", text)
        self.assertIn("support@productlift.dev", text)
        self.assertIn("fallback.waitFor({ state: 'visible' })", text)
        self.assertIn("embedded board should be hidden after vendor error copy appears", text)
        self.assertIn("vendor error copy must not be visible", text)


if __name__ == "__main__":
    unittest.main()
