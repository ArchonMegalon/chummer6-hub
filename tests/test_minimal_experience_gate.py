import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_minimal_experience_gate.py"
STATUS_VIEW_PATH = Path(__file__).resolve().parents[1] / "Chummer.Run.Api" / "Views" / "PublicLanding" / "Status.cshtml"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_minimal_experience_gate", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MinimalExperienceGateTests(unittest.TestCase):
    def test_status_view_uses_one_update_label(self) -> None:
        view = STATUS_VIEW_PATH.read_text(encoding="utf-8")

        self.assertIn("<h1>Updated</h1>", view)
        self.assertNotIn("<h1>Current release</h1>", view)

    def test_payload_passes_for_minimal_public_surfaces(self) -> None:
        module = load_module()
        pages = {
            "https://example.invalid/": """
                <body class="shell-body shell-public">
                    <a class="minimal-hero__visual" href="/media/promo/every-wonder-horizon-promo.mp4">
                        <img src="/media/product/chummer-desktop-runner.png" alt="Chummer desktop character sheet" />
                    </a>
                </body>
            """,
            "https://example.invalid/downloads": """
                <span hidden data-downloads-release-version>Version run-20260701-124648</span>
                <span>Updated</span>
                <article id="stable"><span>Stable</span><p>Stable release.</p></article>
                <article id="nightly"><span>Nightly</span><h2>No newer build</h2></article>
            """,
            "https://example.invalid/status": """
                <span hidden data-downloads-release-version>Version run-20260701-124648</span>
                <div class="minimal-page-hero minimal-status-pill"></div>
                <a data-analytics-event="status_next_action">Downloads</a>
                <a data-analytics-event="status_next_action">Support</a>
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
        self.assertEqual(payload["results"][0]["product_video_links"], ["/media/promo/every-wonder-horizon-promo.mp4"])
        self.assertEqual(payload["results"][1]["updated_label_count"], 1)
        self.assertEqual(payload["results"][2]["updated_label_count"], 0)

    def test_payload_rejects_repeated_dates_and_internal_release_noise(self) -> None:
        module = load_module()
        pages = {
            "https://example.invalid/": """
                <body class="shell-body shell-public">
                    <a class="minimal-hero__visual" href="/media/promo/every-wonder-horizon-promo.mp4">
                        <img src="/media/product/chummer-desktop-runner.png" alt="Chummer desktop character sheet" />
                    </a>
                </body>
            """,
            "https://example.invalid/downloads": """
                <span>Updated</span><span>Updated</span>
                <article id="stable"><span>Stable</span><p>Stable release.</p></article>
                <article id="nightly"><span>Nightly</span><h2>No newer build</h2></article>
                <p>Released 2026-06-23</p>
            """,
            "https://example.invalid/status": """
                <div class="minimal-page-hero minimal-status-pill"></div>
                <span>Updated</span><span>Updated</span>
                <p>Build run-20260623-102621</p>
                <p>Checks passed</p>
                <a data-analytics-event="status_next_action">Downloads</a>
                <a data-analytics-event="status_next_action">Support</a>
            """,
        }

        payload = module.build_payload(
            "https://example.invalid",
            html_fetcher=lambda url: pages[url],
            asset_checker=lambda _url: True,
        )

        self.assertEqual(payload["status"], "fail")
        self.assertIn("status page repeats the update date", payload["failures"])
        self.assertIn("downloads page repeats the update date", payload["failures"])
        self.assertTrue(any("internal release noise" in failure for failure in payload["failures"]))

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
