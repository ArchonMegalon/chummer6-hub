from __future__ import annotations

import unittest
from pathlib import Path


SPEC_PATH = Path("/docker/chummercomplete/chummer.run-services/tests/public/ui-frame-integrity.spec.ts")
RELEASE_SCRIPT_PATH = Path("/docker/chummercomplete/scripts/release/verify_public_ui_frame_integrity.sh")


class ReleaseUiFrameIntegrityRetryTests(unittest.TestCase):
    def test_public_ui_frame_spec_retries_transient_navigation_errors(self) -> None:
        text = SPEC_PATH.read_text(encoding="utf-8")

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
        self.assertIn('tests/public/blazor-new-runner-menu.spec.ts', text)
        self.assertIn('rg -q "Target crashed|ERR_NETWORK_CHANGED|net::ERR_|Timeout"', text)
        self.assertIn('ui-frame-integrity attempt $attempt failed with transient browser/network error; retrying', text)


if __name__ == "__main__":
    unittest.main()
