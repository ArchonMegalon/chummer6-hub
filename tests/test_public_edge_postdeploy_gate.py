from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_public_edge_postdeploy_gate.py"


def load_module():
    spec = importlib.util.spec_from_file_location("verify_public_edge_postdeploy_gate", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_postdeploy_gate_is_self_contained() -> None:
    text = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "_release_gate_bridge" not in text
    assert "verify_participate_iframe_shell.verify" in text
    assert "productlift.dev" not in text.lower()


def test_extract_downloads_version_marker() -> None:
    module = load_module()
    html = '<p class="downloads-release-version" data-downloads-release-version>Version run-20260627-005402</p>'

    assert module.extract_downloads_version_marker(html) == "Version run-20260627-005402"
    assert module.extract_downloads_version_marker("<p>No marker</p>") == ""


def test_status_aggregation_adds_child_failure() -> None:
    module = load_module()
    failures: list[str] = []

    assert module.summarize_child("pwaStatic", {"status": "fail"}, failures) == "fail"
    assert failures == ["pwaStatic proof is not pass"]


def test_ready_handoff_contract_constants_cover_playtime_tools() -> None:
    module = load_module()

    assert {
        "inventory",
        "health",
        "ammo",
        "modifiers",
        "quick_rolls",
        "living_world",
    }.issubset(module.EXPECTED_PLAYTIME_TOOLS)
    assert {"player", "gm", "organizer"}.issubset(module.EXPECTED_READY_ROLES)


def test_flagship_horizons_gate_maps_phases_to_deployed_evidence() -> None:
    module = load_module()
    child_receipts = {
        "downloads": {"status": "pass"},
        "navigation": {"status": "pass"},
        "pwaStatic": {
            "status": "pass",
            "routes": [
                {"path": "/mobile", "status_code": 200},
                {"path": "/mobile/player", "status_code": 200},
                {"path": "/mobile/gm", "status_code": 200},
                {"path": "/mobile/observer", "status_code": 200},
                {"path": "/play/continuity", "status_code": 200},
            ],
        },
        "readyMobileHandoff": {
            "status": "pass",
            "tool_ids": ["inventory", "health", "ammo", "modifiers", "quick_rolls", "living_world"],
            "packet_roles": ["player", "gm", "organizer"],
        },
        "mobileLedger": {
            "status": "pass",
            "payload_status": "opt_in_required",
            "cache_control": "private, no-store, no-cache",
        },
        "mobilePwaServiceWorkerBoundary": {
            "status": "pass",
            "mobileRuntime": {"serviceWorkerBoundaryMode": "shared_portal_root_worker"},
        },
        "participateIframeShell": {"status": "pass"},
        "portalRuntimeImage": {"status": "pass"},
        "browserPlaywright": {
            "status": "pass",
            "requiredProofs": ["downloadsStatus", "mobilePwaViewport", "frontdoorNavigation"],
        },
    }

    result = module.verify_flagship_horizons(child_receipts)

    assert result["status"] == "pass"
    assert result["horizonCount"] == 3
    assert result["browserProofCoverage"] == "full"
    assert {row["id"] for row in result["horizons"]} == {
        "near_term_stabilization",
        "mid_term_pwa_session_utility",
        "long_term_living_world_expansion",
    }


def test_flagship_horizons_gate_fails_when_living_world_opt_in_boundary_regresses() -> None:
    module = load_module()
    child_receipts = {
        "downloads": {"status": "pass"},
        "navigation": {"status": "pass"},
        "pwaStatic": {"status": "pass", "routes": []},
        "readyMobileHandoff": {"status": "pass", "tool_ids": ["living_world"], "packet_roles": []},
        "mobileLedger": {"status": "pass", "payload_status": "open", "cache_control": "public"},
        "mobilePwaServiceWorkerBoundary": {
            "status": "pass",
            "mobileRuntime": {"serviceWorkerBoundaryMode": "play_root_worker"},
        },
        "participateIframeShell": {"status": "pass"},
        "portalRuntimeImage": {"status": "pass"},
        "browserPlaywright": {"status": "pass", "skipped": True, "requiredProofs": []},
    }

    result = module.verify_flagship_horizons(child_receipts)

    assert result["status"] == "fail"
    assert any("mobile ledger does not enforce opt-in-required status" in failure for failure in result["failures"])
    assert any("mobile service-worker boundary is not shared_portal_root_worker" in failure for failure in result["failures"])


def test_mobile_routes_use_structural_pwa_markers_not_legacy_copy() -> None:
    module = load_module()

    assert 'data-blazor-shell="interactive-server"' in module.EXPECTED_MOBILE_ROUTES["/mobile/player"]
    assert "manifest.player.webmanifest" in module.EXPECTED_MOBILE_ROUTES["/mobile/player"]
    assert "Player entry" not in module.EXPECTED_MOBILE_ROUTES["/mobile/player"]


def test_playwright_browser_proofs_skip_when_not_required(tmp_path) -> None:
    module = load_module()

    result = module.run_playwright_browser_proofs("https://chummer.run", [], 1.0, tmp_path)

    assert result["status"] == "pass"
    assert result["skipped"] is True
    assert result["requiredProofs"] == []


def test_playwright_browser_proofs_reject_unknown_requirements(tmp_path) -> None:
    module = load_module()

    result = module.run_playwright_browser_proofs("https://chummer.run", ["unknown"], 1.0, tmp_path)

    assert result["status"] == "fail"
    assert result["specs"] == []
    assert "unknown Playwright proof requirements: unknown" in result["failures"]


def test_playwright_browser_proofs_collect_artifact_status(monkeypatch, tmp_path) -> None:
    module = load_module()

    def fake_run(command, cwd, env, text, capture_output, timeout, check):
        artifact_path = Path(env["CHUMMER_COMPLETION_DIR"]) / "DOWNLOADS_STATUS_E2E.generated.json"
        artifact_path.write_text(
            json.dumps(
                {
                    "contractName": "chummer.downloads_status_e2e.v1",
                    "status": "pass",
                    "base_url": env["BASE_URL"],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.run_playwright_browser_proofs("https://chummer.run", ["downloadsStatus"], 1.0, tmp_path)

    assert result["status"] == "pass"
    assert result["runs"]["downloadsStatus"]["returnCode"] == 0
    assert result["artifacts"]["downloadsStatus"]["status"] == "pass"


def test_portal_runtime_image_guard_skips_without_expected_image() -> None:
    module = load_module()

    result = module.verify_portal_runtime_image("", "portal", "chummer-run-api:local")

    assert result["status"] == "pass"
    assert result["skipped"] is True


def test_normalize_image_id_accepts_bare_sha() -> None:
    module = load_module()

    digest = "A" * 64

    assert module.normalize_image_id(digest) == f"sha256:{digest.lower()}"
    assert module.normalize_image_id(f"sha256:{digest}") == f"sha256:{digest.lower()}"


def test_portal_runtime_image_guard_passes_matching_container_and_tag(monkeypatch) -> None:
    module = load_module()
    image_id = "sha256:" + "1" * 64

    def fake_inspect(args):
        if args == ["inspect", "--format", "{{.Image}} {{.Config.Image}}", "portal"]:
            return 0, f"{image_id} chummer-run-api:local", ""
        if args == ["image", "inspect", "--format", "{{.Id}}", "chummer-run-api:local"]:
            return 0, image_id, ""
        return 1, "", "unexpected command"

    monkeypatch.setattr(module, "run_docker_inspect", fake_inspect)

    result = module.verify_portal_runtime_image(image_id, "portal", "chummer-run-api:local")

    assert result["status"] == "pass"
    assert result["containerImageId"] == image_id
    assert result["tagImageId"] == image_id


def test_portal_runtime_image_guard_fails_on_mutable_tag_drift(monkeypatch) -> None:
    module = load_module()
    expected = "sha256:" + "1" * 64
    actual = "sha256:" + "2" * 64

    def fake_inspect(args):
        if args == ["inspect", "--format", "{{.Image}} {{.Config.Image}}", "portal"]:
            return 0, f"{expected} chummer-run-api:local", ""
        if args == ["image", "inspect", "--format", "{{.Id}}", "chummer-run-api:local"]:
            return 0, actual, ""
        return 1, "", "unexpected command"

    monkeypatch.setattr(module, "run_docker_inspect", fake_inspect)

    result = module.verify_portal_runtime_image(expected, "portal", "chummer-run-api:local")

    assert result["status"] == "fail"
    assert any("portal image tag chummer-run-api:local points at" in failure for failure in result["failures"])
