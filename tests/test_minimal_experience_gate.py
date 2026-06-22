import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_minimal_experience_gate.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_minimal_experience_gate", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MinimalExperienceGateTests(unittest.TestCase):
    def test_payload_passes_for_minimal_public_surfaces(self) -> None:
        module = load_module()
        pages = {
            "https://example.invalid/": """
                <body class="shell-body shell-public">
                    <img src="/media/promo/chummer6-flagship-promo-poster.png" alt="Chummer product workflow preview" />
                </body>
            """,
            "https://example.invalid/downloads": """
                <article id="stable"><h2>Current stable build</h2></article>
                <article id="nightly"><span>Nightly</span></article>
            """,
            "https://example.invalid/status": """
                <div class="minimal-status-pill"></div>
                <a data-analytics-event="status_next_action">Downloads</a>
                <a data-analytics-event="status_next_action">Support</a>
                <a data-analytics-event="status_next_action">Release notes</a>
            """,
        }

        payload = module.build_payload(
            "https://example.invalid",
            html_fetcher=lambda url: pages[url],
            asset_checker=lambda _url: True,
        )

        self.assertEqual(payload["status"], "pass")
        self.assertEqual(payload["base_url"], "https://example.invalid")
        self.assertFalse(payload["results"][0]["nav_panel_open"])
        self.assertTrue(payload["results"][0]["hero_image_loaded"])
        self.assertTrue(payload["results"][0]["product_video_retired"])

    def test_main_writes_receipt_and_report(self) -> None:
        module = load_module()
        payload = {
            "generated_at_utc": "2026-06-21T00:00:00.000Z",
            "base_url": "https://example.invalid",
            "status": "pass",
            "verdict": "READY",
            "failures": [],
            "results": [{"surface": "home"}],
        }
        with tempfile.TemporaryDirectory(prefix="minimal-experience-") as temp_dir:
            with mock.patch.object(module, "build_payload", return_value=payload):
                with mock.patch("sys.argv", ["verify_minimal_experience_gate.py", "--completion-dir", temp_dir]):
                    self.assertEqual(module.main(), 0)

            receipt = json.loads((Path(temp_dir) / "MINIMAL_EXPERIENCE_GATE.generated.json").read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "pass")
            self.assertTrue((Path(temp_dir) / "MINIMAL_EXPERIENCE_GATE.md").is_file())


if __name__ == "__main__":
    unittest.main()
