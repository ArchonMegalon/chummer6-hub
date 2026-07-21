from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "tests" / "public" / "ui-frame-integrity.spec.ts"
RELEASE_SCRIPT_PATH = ROOT / "scripts" / "verify_chummer6_release_ready.sh"
CANDIDATE_RUNNER_PATH = RELEASE_SCRIPT_PATH


class ReleaseUiFrameIntegrityRetryTests(unittest.TestCase):
    def test_public_ui_frame_spec_retries_transient_navigation_errors(self) -> None:
        text = SPEC_PATH.read_text(encoding="utf-8")

        self.assertEqual(text.count("async function createAuditedPage("), 1)
        self.assertNotIn("async ({ browser }) => {", text)
        self.assertIn("const context = await browser.newContext({", text)
        self.assertIn("serviceWorkers: 'block'", text)
        self.assertIn("await context.route('**/*', async (requestRoute) => {", text)
        self.assertIn("await requestRoute.abort('blockedbyclient');", text)
        self.assertIn("if (method !== 'GET')", text)
        self.assertIn("if (parsed.origin !== candidateBinding.baseUrl)", text)
        self.assertIn("{ route: '/ledger/map'", text)
        self.assertNotIn("{ route: '/ledger'", text)
        self.assertIn("async function gotoWithRetry", text)
        self.assertIn("ERR_NETWORK_CHANGED", text)
        self.assertIn("net::ERR_", text)
        self.assertIn("await page.waitForTimeout(500 * attempt);", text)
        self.assertIn("const response = await gotoWithRetry(page, route);", text)

    def test_release_wrapper_keeps_whole_run_retries_around_the_playwright_probe(self) -> None:
        text = RELEASE_SCRIPT_PATH.read_text(encoding="utf-8")

        self.assertIn('timeout_seconds="${CHUMMER_UI_FRAME_TIMEOUT_SECONDS:-900}"', text)
        self.assertIn('attempts="${CHUMMER_UI_FRAME_ATTEMPTS:-3}"', text)
        self.assertIn('CHUMMER_UI_FRAME_TEST_TIMEOUT_MS="$test_timeout_ms"', text)
        self.assertIn('tests/public/ui-frame-integrity.spec.ts', text)
        self.assertIn('rg -q "Target crashed|ERR_NETWORK_CHANGED|net::ERR_', text)
        self.assertIn('HTTP 50[0-9]|Timeout"', text)
        self.assertIn('ui-frame-integrity attempt $attempt failed with transient browser/network error; retrying', text)

    def test_candidate_runner_requires_complete_binding_before_playwright(self) -> None:
        text = CANDIDATE_RUNNER_PATH.read_text(encoding="utf-8")

        for name in (
            "CHUMMER_UI_FRAME_VERIFICATION_MODE",
            "CHUMMER_UI_FRAME_AUTHORITY_ROUTE",
            "CHUMMER_UI_FRAME_EXPECTED_RELEASE_VERSION",
            "CHUMMER_UI_FRAME_EXPECTED_MANIFEST_SHA256",
            "CHUMMER_UI_FRAME_EXPECTED_AUTHORITY_SNAPSHOT_SHA256",
            "CHUMMER_UI_FRAME_EXPECTED_RELEASE_DECISION_SHA256",
            "CHUMMER_UI_FRAME_EXPECTED_RELEASE_SCOPE_SHA256",
            "CHUMMER_UI_FRAME_RELEASE_SCOPE_DECISION_PATH",
            "CHUMMER_UI_FRAME_RECEIPT_PATH",
        ):
            self.assertIn(name, text)
        self.assertIn('"${CHUMMER_UI_FRAME_VERIFICATION_MODE}" == "staged_private"', text)
        self.assertIn("CHUMMER_UI_FRAME_STAGED_PROBE_TOKEN_FILE", text)
        self.assertIn("tests/public/ui-frame-integrity.spec.ts", text)
        spec_text = SPEC_PATH.read_text(encoding="utf-8")
        self.assertIn("completedFramePayload.status !== 'pass'", spec_text)
        self.assertIn("completedLoginPayload.status !== 'pass'", spec_text)
        self.assertIn("await context.route('**/*'", spec_text)
        self.assertIn("serviceWorkers: 'block'", spec_text)
        self.assertIn("navigation redirected or changed exact route", spec_text)
        self.assertIn("network_violation_count", spec_text)
        self.assertNotIn("page.setExtraHTTPHeaders(candidateBinding.requestHeaders)", spec_text)
        login_write = spec_text.index("'LOGIN_COMPACT_FRAME.generated.json'")
        report_write = spec_text.index("writeUiFrameCandidateReport(candidateBinding")
        main_receipt_write = spec_text.index("'UI_FRAME_INTEGRITY.generated.json'", login_write)
        self.assertLess(login_write, report_write)
        self.assertLess(report_write, main_receipt_write)


if __name__ == "__main__":
    unittest.main()
