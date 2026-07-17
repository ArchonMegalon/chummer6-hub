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


def frame_integrity_payload(module, base_url: str = "http://127.0.0.1:5099", omit_route: str | None = None) -> dict:
    install_link_route = (
        module.REQUIRED_FRAME_INSTALL_LINK_ROUTE_PREFIX
        + "installationId=ins-ui-gate&headId=avalonia&applicationVersion=run-test"
    )
    route_matrix = [
        {"route": route, "viewportNames": sorted(module.REQUIRED_FRAME_FULL_VIEWPORT_NAMES)}
        for route in sorted(module.REQUIRED_FRAME_FULL_ROUTES)
        if route != omit_route
    ]
    route_matrix.extend(
        {
            "route": route,
            "viewportNames": sorted(module.REQUIRED_FRAME_COMPACT_VIEWPORT_NAMES),
        }
        for route in sorted(module.REQUIRED_FRAME_COMPACT_ROUTES)
        if route != omit_route
    )
    if omit_route != install_link_route:
        route_matrix.append(
            {
                "route": install_link_route,
                "viewportNames": sorted(module.REQUIRED_FRAME_COMPACT_VIEWPORT_NAMES),
            }
        )

    pages = [
        {
            "route": item["route"],
            "viewport": viewport,
            "status": 200,
            "failure_count": 0,
        }
        for item in route_matrix
        for viewport in item["viewportNames"]
    ]
    return {
        "status": "pass",
        "base_url": base_url,
        "route_viewport_matrix": route_matrix,
        "summary": {"checked_pages": len(pages), "failure_count": 0},
        "pages": pages,
    }


def write_passing_design_inputs(module, root: Path, frame_payload: dict) -> tuple[Path, Path, Path, Path]:
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
        json.dumps(
            {
                "status": "pass",
                "failures": [],
                "release_posture": {
                    "status": "published",
                    "version": "run-test",
                    "channel": "public_stable",
                    "supportability_state": "gold_supported",
                    "rollout_state": "public_stable",
                    "expected_status": "published",
                    "expected_version": "run-test",
                    "expected_channel": "public_stable",
                    "expected_supportability_state": "gold_supported",
                    "expected_rollout_state": "public_stable",
                    "status_matches_expected": True,
                    "version_matches_expected": True,
                    "channel_matches_expected": True,
                    "supportability_matches_expected": True,
                    "rollout_matches_expected": True,
                    "expected_failures": [],
                },
            }
        ),
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
    (completion / "UI_FRAME_INTEGRITY.generated.json").write_text(json.dumps(frame_payload), encoding="utf-8")
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
    return published, completion, presentation, design_review


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
            frame_payload = frame_integrity_payload(module)
            published, completion, presentation, design_review = write_passing_design_inputs(module, root, frame_payload)

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "PRESENTATION_PUBLISHED_ROOT", presentation), \
                mock.patch.object(module, "LIVE_RECRAWL_PATH", published / "LIVE_PUBLIC_WEB_RECRAWL.generated.json"), \
                mock.patch.object(module, "PUBLIC_ROUTE_PROOF_PATH", published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json"), \
                mock.patch.object(module, "LIVE_SURFACE_PARITY_PATH", published / "LIVE_SURFACE_PARITY.generated.json"), \
                mock.patch.object(module, "LTD_OPTIMIZATION_STACK_PATH", published / "LTD_OPTIMIZATION_STACK.generated.json"), \
                mock.patch.object(module, "MINIMAL_EXPERIENCE_GATE_PATH", completion / "MINIMAL_EXPERIENCE_GATE.generated.json"), \
                mock.patch.object(module, "DESIGN_REVIEW_PATH", design_review):
                payload = module.build_payload()

        self.assertEqual("pass", payload["status"], payload["failures"])
        self.assertTrue(payload["checks"]["ui_frame_integrity"]["pass"])
        self.assertEqual(66, payload["checks"]["ui_frame_integrity"]["checked_pages"])
        self.assertEqual(66, payload["checks"]["ui_frame_integrity"]["required_checked_pages"])
        self.assertEqual({}, payload["checks"]["ui_frame_integrity"]["missing_route_viewports"])
        self.assertTrue(payload["checks"]["screenshot_qa"]["pass"])
        self.assertTrue(payload["checks"]["minimal_experience_gate"]["pass"])

    def test_design_gate_rejects_live_surface_parity_without_release_posture_match(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="design-gate-live-posture-") as temp_dir:
            root = Path(temp_dir)
            frame_payload = frame_integrity_payload(module)
            published, completion, presentation, design_review = write_passing_design_inputs(module, root, frame_payload)
            (published / "LIVE_SURFACE_PARITY.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "failures": [],
                        "release_posture": {
                            "status": "published",
                            "version": "run-test",
                            "channel": "public_stable",
                            "supportability_state": "review_required",
                            "rollout_state": "coverage_incomplete",
                            "expected_status": "published",
                            "expected_version": "run-test",
                            "expected_channel": "public_stable",
                            "expected_supportability_state": "gold_supported",
                            "expected_rollout_state": "public_stable",
                            "status_matches_expected": True,
                            "version_matches_expected": True,
                            "channel_matches_expected": True,
                            "supportability_matches_expected": False,
                            "rollout_matches_expected": False,
                            "expected_failures": [
                                "live release manifest supportabilityState does not match expected release channel",
                                "live release manifest rolloutState does not match expected release channel",
                            ],
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

        live_surface = payload["checks"]["live_surface_parity"]
        self.assertEqual("fail", payload["status"])
        self.assertFalse(live_surface["pass"])
        self.assertIn("live surface parity is missing or failing", payload["failures"])
        self.assertIn(
            "live release manifest supportabilityState does not match expected release channel",
            live_surface["semantic_failures"],
        )
        self.assertIn(
            "live surface parity release rollout does not match expected release channel",
            live_surface["semantic_failures"],
        )

    def test_design_gate_allows_live_surface_parity_against_truthful_blocking_expected_release_rollout(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="design-gate-live-non-gold-") as temp_dir:
            root = Path(temp_dir)
            frame_payload = frame_integrity_payload(module)
            published, completion, presentation, design_review = write_passing_design_inputs(module, root, frame_payload)
            live_surface = json.loads((published / "LIVE_SURFACE_PARITY.generated.json").read_text(encoding="utf-8"))
            live_surface["release_posture"].update(
                {
                    "supportability_state": "review_required",
                    "rollout_state": "coverage_incomplete",
                    "expected_supportability_state": "review_required",
                    "expected_rollout_state": "coverage_incomplete",
                    "supportability_matches_expected": True,
                    "rollout_matches_expected": True,
                    "expected_failures": [],
                }
            )
            (published / "LIVE_SURFACE_PARITY.generated.json").write_text(json.dumps(live_surface), encoding="utf-8")

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "COMPLETION_ROOT", completion), \
                mock.patch.object(module, "PRESENTATION_PUBLISHED_ROOT", presentation), \
                mock.patch.object(module, "LIVE_RECRAWL_PATH", published / "LIVE_PUBLIC_WEB_RECRAWL.generated.json"), \
                mock.patch.object(module, "PUBLIC_ROUTE_PROOF_PATH", published / "CHUMMER_PUBLIC_ROUTE_PROOF.generated.json"), \
                mock.patch.object(module, "LIVE_SURFACE_PARITY_PATH", published / "LIVE_SURFACE_PARITY.generated.json"), \
                mock.patch.object(module, "LTD_OPTIMIZATION_STACK_PATH", published / "LTD_OPTIMIZATION_STACK.generated.json"), \
                mock.patch.object(module, "MINIMAL_EXPERIENCE_GATE_PATH", completion / "MINIMAL_EXPERIENCE_GATE.generated.json"), \
                mock.patch.object(module, "DESIGN_REVIEW_PATH", design_review):
                payload = module.build_payload()

        live_surface_check = payload["checks"]["live_surface_parity"]
        self.assertEqual("pass", payload["status"])
        self.assertTrue(live_surface_check["pass"])
        self.assertNotIn("live surface parity expected release supportability is not gold_supported", live_surface_check["semantic_failures"])
        self.assertNotIn("live surface parity expected release rollout is blocking: coverage_incomplete", live_surface_check["semantic_failures"])
        self.assertTrue(payload["checks"]["screenshot_qa"]["pass"])
        self.assertTrue(payload["checks"]["minimal_experience_gate"]["pass"])
        self.assertTrue(payload["checks"]["premium_ui_design_exit_gate"]["pass"])


if __name__ == "__main__":
    unittest.main()
