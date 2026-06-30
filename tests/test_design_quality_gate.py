import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "materialize_design_quality_gate.py"


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_design_quality_gate", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DesignQualityGateTests(unittest.TestCase):
    def test_design_gate_requires_bounded_icanpreneur_lane(self) -> None:
        module = load_module()
        payload = module.build_payload()

        check = payload["checks"]["icanpreneur_design_lane"]
        self.assertTrue(check["pass"], payload["failures"])
        self.assertEqual(check["status"], "tracked")
        self.assertEqual(check["lane_status"], "pass")
        self.assertEqual(check["license_tier"], "Tier 3")
        self.assertFalse(check["runtime_ready"])

    def test_design_gate_accepts_local_visual_receipts_when_live_public_receipts_pass(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="design-gate-") as temp_dir:
            root = Path(temp_dir)
            published = root / "published"
            completion = root / "completion"
            presentation = root / "presentation"
            published.mkdir(parents=True, exist_ok=True)
            completion.mkdir(parents=True, exist_ok=True)
            presentation.mkdir(parents=True, exist_ok=True)

            (published / "LIVE_PUBLIC_WEB_RECRAWL.generated.json").write_text(
                json.dumps({"status": "pass", "results": [{}, {}, {}, {}, {}, {}]}),
                encoding="utf-8",
            )
            (published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json").write_text(
                json.dumps({"status": "pass", "summary": {"route_count": 165, "failed_count": 0, "negative_path_failed_count": 0}}),
                encoding="utf-8",
            )
            (published / "LIVE_SURFACE_PARITY.generated.json").write_text(
                json.dumps({"status": "pass", "failures": []}),
                encoding="utf-8",
            )
            (published / "LTD_OPTIMIZATION_STACK.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "failures": [],
                        "checks": {
                            "icanpreneur_discovery_interview": {
                                "pass": True,
                                "status": "tracked",
                                "lane_status": "pass",
                                "license_tier": "Tier 3",
                                "runtime_ready": False,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            (published / "PREMIUM_UI_DESIGN_EXIT_GATE.generated.json").write_text(
                json.dumps({"status": "pass", "verdict": "PREMIUM_UI_READY", "failures": [], "reference_systems": [{}, {}, {}, {}]}),
                encoding="utf-8",
            )
            (completion / "UI_FRAME_INTEGRITY.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "base_url": "http://127.0.0.1:5099",
                        "summary": {"checked_pages": 66, "failure_count": 0},
                    }
                ),
                encoding="utf-8",
            )
            (completion / "SCREENSHOT_QA.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "base_url": "http://127.0.0.1:5099",
                        "failures": [],
                        "homepage_results": [
                            {"viewport": viewport, "status": "pass"}
                            for viewport in ["390x844", "412x915", "768x1024", "1366x768", "1440x900", "1920x1080"]
                        ],
                        "surface_results": [
                            {"surface": surface, "viewport": viewport, "status": "pass"}
                            for surface in ["downloads", "status", "ledger-map"]
                            for viewport in ["390x844", "1366x768"]
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (completion / "CTA_HIERARCHY.generated.json").write_text(json.dumps({"status": "pass", "failures": []}), encoding="utf-8")
            (completion / "MINIMAL_EXPERIENCE_GATE.generated.json").write_text(
                json.dumps({"status": "pass", "base_url": "http://127.0.0.1:5099", "failures": []}),
                encoding="utf-8",
            )
            (completion / "PUBLIC_ASSET_QUALITY_GATE.generated.json").write_text(
                json.dumps({"status": "pass", "raster_image_count": 1, "failure_count": 0}),
                encoding="utf-8",
            )
            (completion / "CONTRAST_AUDIT.generated.json").write_text(json.dumps({"status": "pass"}), encoding="utf-8")
            (completion / "NOISE_BUDGET_REPORT.md").write_text("- Status: pass\n", encoding="utf-8")
            (completion / "FINAL_CHUMMER_RUN_UX_VERDICT.md").write_text("Verdict: `FLAGSHIP_FRONT_READY`\n", encoding="utf-8")
            (presentation / "UI_GOLD_PROOF_DEPTH_GATE.generated.json").write_text(
                json.dumps({"status": "pass", "verdict": "UI_GOLD_PROOF_DEPTH_READY"}),
                encoding="utf-8",
            )
            design_review = root / "FINAL_PRODUCT_DESIGN_REVIEW.md"
            design_review.write_text(
                "\n".join(
                    [
                        "## Surface Hierarchy",
                        "## Installation and First-Run",
                        "## Status and Support",
                        "## Desktop",
                        "## Black Ledger",
                        "## Human Acceptance",
                        "## Media Acceptance",
                        "## Product Modes",
                        "- [x] first impression communicates Chummer in under five seconds",
                        "- [x] Black Ledger has a large command-map centerpiece",
                        "- [x] public copy is free of proof-dashboard language",
                        "- [x] downloads keep account setup optional",
                        "- [x] desktop surfaces do not present inert actions as ready",
                        "- [x] provider and proof lanes stay out of the primary user journey",
                        "Verdict: `DESIGN_READY`",
                    ]
                ),
                encoding="utf-8",
            )

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "PRESENTATION_PUBLISHED_ROOT", presentation), \
                mock.patch.object(module, "LIVE_RECRAWL_PATH", published / "LIVE_PUBLIC_WEB_RECRAWL.generated.json"), \
                mock.patch.object(module, "PUBLIC_ROUTE_PROOF_PATH", published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json"), \
                mock.patch.object(module, "LIVE_SURFACE_PARITY_PATH", published / "LIVE_SURFACE_PARITY.generated.json"), \
                mock.patch.object(module, "LTD_OPTIMIZATION_STACK_PATH", published / "LTD_OPTIMIZATION_STACK.generated.json"), \
                mock.patch.object(module, "PREMIUM_UI_DESIGN_EXIT_GATE_PATH", published / "PREMIUM_UI_DESIGN_EXIT_GATE.generated.json"), \
                mock.patch.object(module, "MINIMAL_EXPERIENCE_GATE_PATH", completion / "MINIMAL_EXPERIENCE_GATE.generated.json"), \
                mock.patch.object(module, "DESIGN_REVIEW_PATH", design_review):
                payload = module.build_payload()

        self.assertEqual("pass", payload["status"], payload["failures"])
        self.assertTrue(payload["checks"]["ui_frame_integrity"]["pass"])
        self.assertTrue(payload["checks"]["screenshot_qa"]["pass"])
        self.assertTrue(payload["checks"]["minimal_experience_gate"]["pass"])
        self.assertTrue(payload["checks"]["premium_ui_design_exit_gate"]["pass"])


if __name__ == "__main__":
    unittest.main()
