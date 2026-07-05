from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import types
from datetime import UTC, datetime, timedelta
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


def test_process_tail_strips_ansi_control_sequences() -> None:
    module = load_module()

    assert module.tail_lines("\x1b[1A\x1b[2K  1 passed\nok") == "  1 passed\nok"
    assert module.tail_lines(
        "(node:1) Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set.\n"
        "(Use `node --trace-warnings ...` to show where the warning was created)\n"
        "  1 passed"
    ) == "  1 passed"


def test_verify_downloads_accepts_explicit_preview_posture(monkeypatch) -> None:
    module = load_module()
    release_payload = {
        "version": "run-20260701-124648",
        "releaseVersion": "run-20260701-124648",
        "status": "published",
        "channel": "preview",
        "rolloutState": "promoted_preview",
        "supportabilityState": "preview_supported",
    }
    compatibility_payload = {
        **release_payload,
        "downloads": [{"id": "avalonia-win-x64-installer"}],
    }

    def fake_fetch(base_url, path, timeout_seconds):
        if path == "/downloads/RELEASE_CHANNEL.generated.json":
            return module.FetchResult(path, 200, {"content-type": "application/json"}, json.dumps(release_payload), f"{base_url}{path}")
        if path == "/downloads/releases.json":
            return module.FetchResult(path, 200, {"content-type": "application/json"}, json.dumps(compatibility_payload), f"{base_url}{path}")
        return module.FetchResult(
            path,
            200,
            {"content-type": "text/html"},
            '<p data-downloads-release-version>Version run-20260701-124648</p>',
            f"{base_url}{path}",
        )

    monkeypatch.setattr(module, "fetch", fake_fetch)

    result = module.verify_downloads("https://chummer.run", 1.0, expected_release_channel="preview")

    assert result["status"] == "pass"
    assert result["expected_release_rollout_state"] == "promoted_preview"
    assert result["expected_release_supportability_state"] == "preview_supported"
    assert result["compatibility_manifest_guarded_preview"] is False


def test_verify_downloads_accepts_guarded_preview_compatibility_manifest(monkeypatch) -> None:
    module = load_module()
    release_payload = {
        "version": "run-20260701-124648",
        "releaseVersion": "run-20260701-124648",
        "status": "published",
        "channel": "preview",
        "rolloutState": "promoted_preview",
        "supportabilityState": "preview_supported",
    }
    compatibility_payload = {
        "version": "run-20260701-124648",
        "status": "published",
        "channel": "preview",
        "rolloutState": "desktop_polish_needed",
        "supportabilityState": "review_required",
        "downloads": [{"id": "avalonia-win-x64-installer"}],
    }

    def fake_fetch(base_url, path, timeout_seconds):
        if path == "/downloads/RELEASE_CHANNEL.generated.json":
            return module.FetchResult(path, 200, {"content-type": "application/json"}, json.dumps(release_payload), f"{base_url}{path}")
        if path == "/downloads/releases.json":
            return module.FetchResult(path, 200, {"content-type": "application/json"}, json.dumps(compatibility_payload), f"{base_url}{path}")
        return module.FetchResult(
            path,
            200,
            {"content-type": "text/html"},
            '<p data-downloads-release-version>Version run-20260701-124648</p>',
            f"{base_url}{path}",
        )

    monkeypatch.setattr(module, "fetch", fake_fetch)

    result = module.verify_downloads("https://chummer.run", 1.0, expected_release_channel="preview")

    assert result["status"] == "pass"
    assert result["compatibility_manifest_guarded_preview"] is True
    assert result["compatibility_manifest_supportability_state"] == "review_required"
    assert result["compatibility_manifest_rollout_state"] == "desktop_polish_needed"


def test_verify_downloads_accepts_guarded_preview_release_manifest(monkeypatch) -> None:
    module = load_module()
    release_payload = {
        "version": "run-20260704-170602",
        "releaseVersion": "run-20260704-170602",
        "status": "published",
        "channel": "preview",
        "rolloutState": "coverage_incomplete",
        "supportabilityState": "review_required",
    }
    compatibility_payload = {
        "version": "run-20260704-170602",
        "releaseVersion": "run-20260704-170602",
        "status": "published",
        "channel": "preview",
        "rolloutState": "desktop_polish_needed",
        "supportabilityState": "review_required",
        "downloads": [{"id": "avalonia-win-x64-installer"}],
    }

    def fake_fetch(base_url, path, timeout_seconds):
        if path == "/downloads/RELEASE_CHANNEL.generated.json":
            return module.FetchResult(path, 200, {"content-type": "application/json"}, json.dumps(release_payload), f"{base_url}{path}")
        if path == "/downloads/releases.json":
            return module.FetchResult(path, 200, {"content-type": "application/json"}, json.dumps(compatibility_payload), f"{base_url}{path}")
        return module.FetchResult(
            path,
            200,
            {"content-type": "text/html"},
            '<p data-downloads-release-version>Version run-20260704-170602</p>',
            f"{base_url}{path}",
        )

    monkeypatch.setattr(module, "fetch", fake_fetch)

    result = module.verify_downloads("https://chummer.run", 1.0, expected_release_channel="preview")

    assert result["status"] == "pass"
    assert result["release_manifest_guarded_preview"] is True
    assert result["compatibility_manifest_guarded_preview"] is True
    assert result["release_supportability_state"] == "review_required"
    assert result["release_rollout_state"] == "coverage_incomplete"


def test_verify_downloads_still_rejects_preview_when_stable_expected(monkeypatch) -> None:
    module = load_module()
    release_payload = {
        "version": "run-20260701-124648",
        "status": "published",
        "channel": "preview",
        "rolloutState": "promoted_preview",
        "supportabilityState": "preview_supported",
    }
    compatibility_payload = {
        **release_payload,
        "downloads": [{"id": "avalonia-win-x64-installer"}],
    }

    def fake_fetch(base_url, path, timeout_seconds):
        if path == "/downloads/RELEASE_CHANNEL.generated.json":
            return module.FetchResult(path, 200, {"content-type": "application/json"}, json.dumps(release_payload), f"{base_url}{path}")
        if path == "/downloads/releases.json":
            return module.FetchResult(path, 200, {"content-type": "application/json"}, json.dumps(compatibility_payload), f"{base_url}{path}")
        return module.FetchResult(
            path,
            200,
            {"content-type": "text/html"},
            '<p data-downloads-release-version>Version run-20260701-124648</p>',
            f"{base_url}{path}",
        )

    monkeypatch.setattr(module, "fetch", fake_fetch)

    result = module.verify_downloads("https://chummer.run", 1.0)

    assert result["status"] == "fail"
    assert "release channel expected public_stable, got preview" in result["failures"]
    assert "release rollout expected public_stable, got promoted_preview" in result["failures"]
    assert "release supportability expected gold_supported, got preview_supported" in result["failures"]


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


def test_manifest_asset_paths_collects_local_manifest_assets() -> None:
    module = load_module()
    payload = {
        "icons": [
            {"src": "/pwa-icon.svg"},
            {"src": "relative.png"},
            {"src": "https://cdn.example.invalid/external.png"},
            {"src": "data:image/png;base64,abc"},
        ],
        "screenshots": [
            {"src": "./shots/mobile.svg"},
        ],
        "shortcuts": [
            {
                "name": "Roll dice",
                "icons": [
                    {"src": "/shortcut.svg"},
                    {"src": "icons/shortcut.svg?v=1#ignored"},
                    {"src": "//cdn.example.invalid/protocol-relative.svg"},
                ],
            }
        ],
    }

    assert module.manifest_asset_paths(payload) == [
        "/icons/shortcut.svg?v=1",
        "/pwa-icon.svg",
        "/relative.png",
        "/shortcut.svg",
        "/shots/mobile.svg",
    ]


def test_service_worker_declared_fetchable_paths_excludes_non_cacheable_and_external() -> None:
    module = load_module()
    service_worker = {
        "precache_urls": [
            "/mobile",
            "mobile/player?role=Player",
            "https://cdn.example.invalid/app.js",
            "data:application/json,{}",
            "/mobile/pwa/ledger.json",
        ],
        "shell_assets": [
            "/mobile",
            "/mobile.css",
            "//cdn.example.invalid/app.css",
            "/mobile/pwa/ledger.json?scope=public",
        ],
        "non_cacheable_paths": ["/mobile/pwa/ledger.json"],
    }

    assert module.service_worker_declared_fetchable_paths(service_worker) == [
        "/mobile",
        "/mobile.css",
        "/mobile/player?role=Player",
    ]


def test_pwa_static_fetches_service_worker_declared_paths(monkeypatch) -> None:
    module = load_module()
    service_worker_body = """
const CACHE_NAME = "chummer-public-v4";
const PRECACHE_URLS = ["/mobile/player", "/ready/handoff/mobile.json", "/declared-ok", "/declared-missing", "/mobile/pwa/ledger.json"];
const NON_CACHEABLE_PATHS = new Set(["/mobile/pwa/ledger.json"]);
"""

    def fake_fetch(base_url, path, timeout_seconds):
        if path == "/service-worker.js":
            return module.FetchResult(path, 200, {"content-type": "text/javascript"}, service_worker_body, f"{base_url}{path}")
        if path == "/declared-missing":
            return module.FetchResult(path, 404, {"content-type": "text/plain"}, "", f"{base_url}{path}")
        if path in module.EXPECTED_MOBILE_ROUTES:
            return module.FetchResult(path, 200, {"content-type": "text/html"}, " ".join(module.EXPECTED_MOBILE_ROUTES[path]), f"{base_url}{path}")
        if path in module.EXPECTED_MANIFESTS:
            payload = {
                "start_url": module.EXPECTED_MANIFESTS[path],
                "display": "standalone",
                "icons": [{"src": "/icon-a.svg"}, {"src": "/icon-b.svg"}],
            }
            return module.FetchResult(path, 200, {"content-type": "application/manifest+json"}, json.dumps(payload), f"{base_url}{path}")
        return module.FetchResult(path, 200, {"content-type": "text/plain"}, "ok", f"{base_url}{path}")

    monkeypatch.setattr(module, "fetch", fake_fetch)

    result = module.verify_pwa_static("https://chummer.run", 1.0)

    assert result["status"] == "fail"
    assert result["service_worker_declared_path_count"] >= 1
    assert any(
        "service-worker declared path /declared-missing expected 200, got 404" in failure
        for failure in result["failures"]
    )


def test_ready_mobile_handoff_binds_living_world_tool_to_black_ledger_heat(monkeypatch) -> None:
    module = load_module()
    payload = {
        "status": "ready",
        "pwa_route": "/mobile",
        "continuity_route": "/play/continuity",
        "boundaries": [
            "Character building stays before or after the session.",
            "Living-world updates require account opt-in and followed-world selection.",
            "GM remains final authority for table rulings, modifiers, and consequences.",
        ],
        "playtime_tools": [
            {"id": "inventory"},
            {"id": "health"},
            {"id": "ammo"},
            {"id": "modifiers"},
            {"id": "quick_rolls"},
            {
                "id": "living_world",
                "summary": "Show Black Ledger heat and followed-world updates only after account opt-in and followed-world selection.",
            },
        ],
        "packet_routes": [
            {"roleId": "player", "markdown": "/ready/packet/player.md", "json": "/ready/packet/player.json"},
            {"roleId": "gm", "markdown": "/ready/packet/gm.md", "json": "/ready/packet/gm.json"},
            {"roleId": "organizer", "markdown": "/ready/packet/organizer.md", "json": "/ready/packet/organizer.json"},
        ],
    }

    def fake_fetch(base_url, path, timeout_seconds):
        if path.endswith(".md"):
            role = path.rsplit("/", 1)[-1].removesuffix(".md")
            return module.FetchResult(path, 200, {"content-type": "text/markdown"}, f"# {role} packet\n\nReady.", f"{base_url}{path}")
        if path.endswith(".json") and path != "/ready/handoff/mobile.json":
            role = path.rsplit("/", 1)[-1].removesuffix(".json")
            packet_payload = {"verdict": {"roleId": role}, "packet": {"roleId": role}}
            return module.FetchResult(path, 200, {"content-type": "application/json"}, json.dumps(packet_payload), f"{base_url}{path}")
        return module.FetchResult(path, 200, {"content-type": "application/json"}, json.dumps(payload), f"{base_url}{path}")

    monkeypatch.setattr(module, "fetch", fake_fetch)

    result = module.verify_ready_mobile_handoff("https://chummer.run", 1.0)

    assert result["status"] == "pass"
    assert "black ledger" in result["living_world_summary"]
    assert "heat" in result["living_world_summary"]
    assert result["packet_route_count"] == 3
    assert {row["roleId"] for row in result["packet_routes"]} == {"player", "gm", "organizer"}


def test_ready_mobile_handoff_fails_when_packet_json_role_mismatches(monkeypatch) -> None:
    module = load_module()
    payload = {
        "status": "ready",
        "pwa_route": "/mobile",
        "continuity_route": "/play/continuity",
        "boundaries": [
            "Character building stays before or after the session.",
            "Living-world updates require account opt-in and followed-world selection.",
            "GM remains final authority for table rulings, modifiers, and consequences.",
        ],
        "playtime_tools": [
            {"id": "inventory"},
            {"id": "health"},
            {"id": "ammo"},
            {"id": "modifiers"},
            {"id": "quick_rolls"},
            {
                "id": "living_world",
                "summary": "Show Black Ledger heat and followed-world updates only after account opt-in and followed-world selection.",
            },
        ],
        "packet_routes": [
            {"roleId": "player", "markdown": "/ready/packet/player.md", "json": "/ready/packet/player.json"},
        ],
    }

    def fake_fetch(base_url, path, timeout_seconds):
        if path.endswith(".md"):
            return module.FetchResult(path, 200, {"content-type": "text/markdown"}, "# Player packet\n\nReady.", f"{base_url}{path}")
        if path.endswith(".json") and path != "/ready/handoff/mobile.json":
            return module.FetchResult(
                path,
                200,
                {"content-type": "application/json"},
                json.dumps({"verdict": {"roleId": "gm"}, "packet": {"roleId": "player"}}),
                f"{base_url}{path}",
            )
        return module.FetchResult(path, 200, {"content-type": "application/json"}, json.dumps(payload), f"{base_url}{path}")

    monkeypatch.setattr(module, "fetch", fake_fetch)

    result = module.verify_ready_mobile_handoff("https://chummer.run", 1.0)

    assert result["status"] == "fail"
    assert any("verdict roleId expected player, got gm" in failure for failure in result["failures"])


def test_mobile_ledger_contract_binds_opt_in_to_heat_followed_world_and_session(monkeypatch) -> None:
    module = load_module()
    payload = {
        "mode": "mobile_pwa_living_world",
        "status": "opt_in_required",
        "summary": "Black Ledger heat and session continuity updates are available only after account opt-in and followed-world selection.",
        "legal_posture": "Public lane stays aggregate only. No private run table state, world heat, followed-world selection, or session continuity payload is published before opt-in.",
        "opt_in_route": "/account",
        "world_gate": "account_opt_in_and_followed_world_selection",
        "heat_visibility": "hidden_until_opt_in",
        "session_visibility": "hidden_until_opt_in",
        "opt_in_required_for": ["black_ledger_heat", "followed_world_updates", "session_continuity"],
        "updates_route": "/mobile/pwa/ledger.json",
    }
    headers = {
        "cache-control": "private, no-store, no-cache, max-age=0",
        "vary": "Cookie, Authorization",
        "pragma": "no-cache",
    }

    def fake_fetch(base_url, path, timeout_seconds):
        return module.FetchResult(path, 200, headers, json.dumps(payload), f"{base_url}{path}")

    monkeypatch.setattr(module, "fetch", fake_fetch)

    result = module.verify_mobile_ledger("https://chummer.run", 1.0)

    assert result["status"] == "pass"
    assert result["black_ledger_bound"] is True
    assert result["heat_bound"] is True
    assert result["followed_world_bound"] is True
    assert result["session_continuity_bound"] is True
    assert result["private_table_state_hidden"] is True
    assert set(result["opt_in_required_for"]) == {
        "black_ledger_heat",
        "followed_world_updates",
        "session_continuity",
    }


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
            "packet_route_count": 3,
        },
        "mobileLedger": {
            "status": "pass",
            "payload_status": "opt_in_required",
            "cache_control": "private, no-store, no-cache",
            "black_ledger_bound": True,
            "heat_bound": True,
            "followed_world_bound": True,
            "session_continuity_bound": True,
            "private_table_state_hidden": True,
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
    assert any("mobile ledger does not bind hidden heat tracking" in failure for failure in result["failures"])
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
        assert env["npm_config_cache"] == str(tmp_path / ".npm-cache")
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


def test_resolve_playwright_command_falls_back_to_declared_package_version(monkeypatch, tmp_path) -> None:
    module = load_module()

    (tmp_path / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "node_modules/playwright": {
                        "version": "1.60.0",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.delenv("CHUMMER_PLAYWRIGHT_BIN", raising=False)
    monkeypatch.delenv("CHUMMER_PLAYWRIGHT_PACKAGE_SPEC", raising=False)
    monkeypatch.delenv("CHUMMER_PLAYWRIGHT_NODE_MODULES_ROOT", raising=False)
    monkeypatch.setattr(module, "resolve_playwright_node_modules_root", lambda: None)

    assert module.resolve_playwright_command() == ["npx", "--yes", "playwright@1.60.0"]


def test_resolve_playwright_command_prefers_shared_node_modules_root(monkeypatch, tmp_path) -> None:
    module = load_module()
    shared_root = tmp_path / "shared-node-modules"
    bin_dir = shared_root / ".bin"
    bin_dir.mkdir(parents=True)
    (bin_dir / "playwright").write_text("#!/bin/sh\n", encoding="utf-8")

    monkeypatch.setattr(module, "ROOT", tmp_path / "clean-clone")
    monkeypatch.setenv("CHUMMER_PLAYWRIGHT_NODE_MODULES_ROOT", str(shared_root))
    monkeypatch.delenv("CHUMMER_PLAYWRIGHT_BIN", raising=False)

    assert module.resolve_playwright_command() == [str(bin_dir / "playwright")]
    assert module.resolve_playwright_node_modules_root() == shared_root


def test_playwright_browser_proofs_delete_stale_artifacts_before_running(monkeypatch, tmp_path) -> None:
    module = load_module()
    stale_artifact_path = tmp_path / "DOWNLOADS_STATUS_E2E.generated.json"
    stale_artifact_path.write_text(
        json.dumps(
            {
                "contractName": "chummer.downloads_status_e2e.v1",
                "status": "pass",
                "base_url": "https://stale.example.invalid",
            }
        ),
        encoding="utf-8",
    )

    def fake_run(command, cwd, env, text, capture_output, timeout, check):
        assert env["npm_config_cache"] == str(tmp_path / ".npm-cache")
        assert not stale_artifact_path.exists()
        return subprocess.CompletedProcess(command, 1, stdout="", stderr="playwright failed")

    monkeypatch.setattr(module, "resolve_playwright_command", lambda: ["playwright"])
    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.run_playwright_browser_proofs("https://chummer.run", ["downloadsStatus"], 1.0, tmp_path)

    assert result["status"] == "fail"
    assert result["runs"]["downloadsStatus"]["returnCode"] == 1
    assert result["artifacts"]["downloadsStatus"]["status"] == "missing"
    assert any(
        "downloadsStatus did not write DOWNLOADS_STATUS_E2E.generated.json" in failure
        for failure in result["failures"]
    )


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


# Orchestrated flagship gate coverage retained from the integration branch.
def passing_receipts():
    return (
        {
            "contractName": "chummer.public_edge_deploy_preflight.v1",
            "status": "pass",
            "overlayRoot": "/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app",
            "overlayBuildInfoSourceFingerprint": {
                "aggregateMatchesCurrentSource": True,
                "recordedAggregateSha256": "a" * 64,
                "expectedAggregateSha256": "a" * 64,
                "missingKeys": [],
                "mismatchedKeys": [],
            },
            "activeLockCount": 0,
            "foreignLockCount": 0,
            "ignoredForeignLockCount": 0,
            "staleLookingLockCount": 0,
            "foreignLocksIgnored": False,
            "allowForeignBuildLocks": False,
            "staleForeignLockCount": 0,
            "staleForeignLocksIgnored": False,
            "allowStaleForeignBuildLocks": False,
            "findings": [],
        },
        {
            "contractName": "chummer.downloads_version_marker.v1",
            "status": "pass",
            "base_url": "https://chummer.run",
            "downloads_has_marker": True,
            "status_redirect_has_marker": True,
            "status_redirect_heading": "Stable downloads",
            "status_redirect_heading_recognized": True,
            "status_redirect_heading_expected": "Stable downloads",
            "status_redirect_heading_matches_release_channel": True,
            "status_redirect_heading_uses_generic_updated_copy": False,
            "visible_version": "Version run-20260630",
            "status_redirect_version": "Version run-20260630",
            "downloads_version_marker_value": "Version run-20260630",
            "status_redirect_version_marker_value": "Version run-20260630",
            "downloads_version_marker_matches_release_channel": True,
            "status_redirect_version_marker_matches_release_channel": True,
            "visible_version_matches_release_channel": True,
            "status_redirect_version_matches_release_channel": True,
            "expected_release_status": "published",
            "expected_release_channel": "public_stable",
            "expected_release_supportability_state": "gold_supported",
            "expected_release_rollout_state": "public_stable",
            "release_manifest_http_status": 200,
            "release_manifest_status": "published",
            "release_manifest_status_matches_release_channel": True,
            "release_manifest_channel": "public_stable",
            "release_manifest_channel_matches_release_channel": True,
            "release_manifest_version": "run-20260630",
            "release_manifest_version_matches_release_channel": True,
            "release_manifest_supportability_state": "gold_supported",
            "release_manifest_supportability_matches_release_channel": True,
            "release_manifest_rollout_state": "public_stable",
            "release_manifest_rollout_matches_release_channel": True,
            "public_release_copy_safe": True,
            "public_release_unsafe_copy_markers": [],
            "public_release_has_preview_or_review_caveat": False,
            "release_manifest_copy_safe": True,
            "release_manifest_unsafe_copy_markers": [],
            "release_manifest_has_preview_or_review_caveat": False,
            "release_manifest_parse_error": None,
        },
        {
            "contractName": "chummer.public_pwa_static_assets.v1",
            "status": "pass",
            "base_url": "https://chummer.run",
            "manifests": [{}, {}, {}],
            "role_manifests": [
                {
                    "path": "/manifest.player.webmanifest",
                    "role": "Player",
                    "id": "/mobile/player",
                    "start_url": "/mobile/player?role=Player",
                    "display": "standalone",
                },
                {
                    "path": "/manifest.gm.webmanifest",
                    "role": "GameMaster",
                    "id": "/mobile/gm",
                    "start_url": "/mobile/gm?role=GameMaster",
                    "display": "standalone",
                },
            ],
            "assets": [{} for _ in range(11)],
            "service_worker": {
                "worker_kind": "play",
                "cache_version": "play-shell-v15",
                "ledger_stream_non_cacheable": True,
                "ledger_stream_precached": False,
            },
        },
        {
            "contractName": "chummer.mobile_pwa_ledger_boundary.v1",
            "status": "pass",
            "base_url": "https://chummer.run",
            "payload_status": "opt_in_required",
            "cache_control": "private, no-store, no-cache, max-age=0",
            "vary": "Cookie, Authorization",
        },
        {
            "contractName": "chummer.ready_mobile_handoff_contract.v1",
            "status": "pass",
            "base_url": "https://chummer.run",
            "tool_ids": ["inventory", "health", "ammo", "modifiers", "quick_rolls", "living_world"],
            "packet_roles": ["player", "gm", "organizer"],
            "frontdoor_launch_route": "/mobile/player",
            "role_routes": [
                {
                    "role": "Player",
                    "mode": "player",
                    "route": "/mobile/player",
                    "manifest_path": "/manifest.player.webmanifest",
                    "manifest_id": "/mobile/player",
                    "manifest_start_url": "/mobile/player?role=Player",
                    "session_handoff_route_template": "/mobile/player?sessionId={sessionId}&role=Player",
                    "frontdoor_default": True,
                },
                {
                    "role": "GameMaster",
                    "mode": "gm",
                    "route": "/mobile/gm",
                    "manifest_path": "/manifest.gm.webmanifest",
                    "manifest_id": "/mobile/gm",
                    "manifest_start_url": "/mobile/gm?role=GameMaster",
                    "session_handoff_route_template": "/mobile/gm?sessionId={sessionId}&role=GameMaster",
                    "frontdoor_default": False,
                },
            ],
        },
        {
            "contractName": "chummer.participate_iframe_shell.v1",
            "status": "pass",
            "base_url": "https://chummer.run",
            "route_count": 2,
            "iframe_route_count": 2,
            "offline_fallback_route_count": 0,
        },
    )


def passing_role_alias_routes() -> dict[str, object]:
    return {
        "contractName": "chummer.public_role_alias_routes.v1",
        "status": "pass",
        "baseUrl": "https://chummer.run",
        "results": [
            {
                "aliasPath": "/player",
                "requestedUrl": "https://chummer.run/player",
                "httpStatus": 200,
                "finalUrl": "https://chummer.run/mobile/player",
                "finalRoute": "/mobile/player",
                "expectedFinalRoute": "/mobile/player",
                "pass": True,
                "error": "",
            },
            {
                "aliasPath": "/gm",
                "requestedUrl": "https://chummer.run/gm",
                "httpStatus": 200,
                "finalUrl": "https://chummer.run/mobile/gm",
                "finalRoute": "/mobile/gm",
                "expectedFinalRoute": "/mobile/gm",
                "pass": True,
                "error": "",
            },
            {
                "aliasPath": "/observer",
                "requestedUrl": "https://chummer.run/observer",
                "httpStatus": 200,
                "finalUrl": "https://chummer.run/mobile/observer",
                "finalRoute": "/mobile/observer",
                "expectedFinalRoute": "/mobile/observer",
                "pass": True,
                "error": "",
            },
        ],
        "drift": [],
    }


def test_postdeploy_gate_passes_when_all_child_receipts_pass() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
        role_alias_routes=passing_role_alias_routes(),
    )

    assert result["status"] == "pass"
    assert result["baseUrl"] == "https://chummer.run"
    assert result["expectedReleaseVersion"] == "run-20260630"
    assert result["preflightOverlayRoot"] == "/docker/chummercomplete/chummer.run-services/.state/public-edge-portal-overlay/app"
    assert result["preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource"] is True
    assert result["preflightOverlayBuildInfoSourceFingerprintRecordedAggregateSha256"] == "a" * 64
    assert result["preflightOverlayBuildInfoSourceFingerprintExpectedAggregateSha256"] == "a" * 64
    assert result["preflightOverlayBuildInfoSourceFingerprintMissingKeys"] == []
    assert result["preflightOverlayBuildInfoSourceFingerprintMismatchedKeys"] == []
    assert result["visibleVersionMatchesReleaseChannel"] is True
    assert result["statusRedirectVersion"] == "Version run-20260630"
    assert result["statusRedirectVersionMatchesReleaseChannel"] is True
    assert result["expectedReleaseStatus"] == "published"
    assert result["expectedReleaseChannel"] == "public_stable"
    assert result["releaseManifestStatus"] == "published"
    assert result["releaseManifestStatusMatchesReleaseChannel"] is True
    assert result["releaseManifestChannel"] == "public_stable"
    assert result["releaseManifestChannelMatchesReleaseChannel"] is True
    assert result["expectedReleaseSupportabilityState"] == "gold_supported"
    assert result["releaseManifestSupportabilityState"] == "gold_supported"
    assert result["releaseManifestSupportabilityMatchesReleaseChannel"] is True
    assert result["expectedReleaseRolloutState"] == "public_stable"
    assert result["releaseManifestRolloutState"] == "public_stable"
    assert result["releaseManifestRolloutMatchesReleaseChannel"] is True
    assert result["preflightBlockingLockCount"] == 0
    assert result["preflightFindingCount"] == 0
    assert result["preflightStaleLookingLockCount"] == 0
    assert result["preflightStaleForeignLockCount"] == 0
    assert result["preflightStaleForeignLocksIgnored"] is False
    assert result["downloadsHasMarker"] is True
    assert result["statusRedirectHeading"] == "Stable downloads"
    assert result["statusRedirectHeadingRecognized"] is True
    assert result["statusRedirectHeadingExpected"] == "Stable downloads"
    assert result["statusRedirectHeadingMatchesReleaseChannel"] is True
    assert result["statusRedirectHeadingUsesGenericUpdatedCopy"] is False
    assert result["downloadsVersionMarkerValue"] == "Version run-20260630"
    assert result["statusRedirectVersionMarkerValue"] == "Version run-20260630"
    assert result["downloadsVersionMarkerMatchesReleaseChannel"] is True
    assert result["statusRedirectVersionMarkerMatchesReleaseChannel"] is True
    assert result["ledgerStreamNonCacheable"] is True
    assert result["ledgerStreamPrecached"] is False
    assert result["pwaRootWorkerKind"] == "play"
    assert result["pwaRootWorkerCacheVersion"] == "play-shell-v15"
    assert result["rolePwaManifestCount"] == 2
    assert {
        (entry["role"], entry["id"], entry["start_url"])
        for entry in result["rolePwaManifests"]
    } == {
        ("Player", "/mobile/player", "/mobile/player?role=Player"),
        ("GameMaster", "/mobile/gm", "/mobile/gm?role=GameMaster"),
    }
    assert result["mobileLedgerStatus"] == "pass"
    assert result["mobileLedgerPayloadStatus"] == "opt_in_required"
    assert result["mobileLedgerCacheControl"] == "private, no-store, no-cache, max-age=0"
    assert result["readyMobileHandoffStatus"] == "pass"
    assert "quick_rolls" in result["readyMobileHandoffToolIds"]
    assert "player" in result["readyMobileHandoffPacketRoles"]
    assert result["readyMobileHandoffFrontdoorLaunchRoute"] == "/mobile/player"
    assert {
        (entry["role"], entry["route"], entry["manifest_path"])
        for entry in result["readyMobileHandoffRoleRoutes"]
    } == {
        ("Player", "/mobile/player", "/manifest.player.webmanifest"),
        ("GameMaster", "/mobile/gm", "/manifest.gm.webmanifest"),
    }
    assert result["participateIframeShellStatus"] == "pass"
    assert result["participateIframeRouteCount"] == 2
    assert result["participateIframeRouteIframeCount"] == 2
    assert result["roleAliasRouteStatus"] == "pass"
    assert result["roleAliasRouteContract"] == "chummer.public_role_alias_routes.v1"
    assert result["roleAliasRouteDrift"] == []
    assert {
        (entry["aliasPath"], entry["finalRoute"], entry["expectedFinalRoute"])
        for entry in result["roleAliasRouteResults"]
    } == {
        ("/player", "/mobile/player", "/mobile/player"),
        ("/gm", "/mobile/gm", "/mobile/gm"),
        ("/observer", "/mobile/observer", "/mobile/observer"),
    }
    assert result["coreChildContracts"]["preflight"] == "chummer.public_edge_deploy_preflight.v1"
    assert result["coreChildContracts"]["downloads"] == "chummer.downloads_version_marker.v1"
    assert result["coreChildContracts"]["pwaStatic"] == "chummer.public_pwa_static_assets.v1"
    assert result["failures"] == []


def test_postdeploy_gate_fails_when_public_role_aliases_drift() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    alias_routes = passing_role_alias_routes()
    alias_routes["status"] = "fail"
    alias_routes["results"][0].update(  # type: ignore[index, union-attr]
        {
            "finalUrl": "https://chummer.run/play?role=player",
            "finalRoute": "/play?role=player",
            "expectedFinalRoute": "/mobile/player",
            "pass": False,
        }
    )
    alias_routes["drift"] = [alias_routes["results"][0]]  # type: ignore[index]

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        role_alias_routes=alias_routes,
    )

    assert result["status"] == "fail"
    assert result["roleAliasRouteStatus"] == "fail"
    assert result["roleAliasRouteDrift"][0]["aliasPath"] == "/player"
    assert "role alias route redirects drifted" in result["failures"]
    assert "/player resolved to /play?role=player instead of /mobile/player" in result["failures"]


def test_postdeploy_gate_fails_when_core_child_contract_is_wrong() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["contractName"] = "chummer.downloads_version_marker.preview"

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["coreChildContracts"]["downloads"] == "chummer.downloads_version_marker.preview"
    assert "downloads child receipt contract is not chummer.downloads_version_marker.v1" in result["failures"]


def test_postdeploy_gate_fails_when_preflight_or_downloads_fail() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    preflight["status"] = "fail"
    preflight["activeLockCount"] = 3
    preflight["foreignLockCount"] = 2
    preflight["ignoredForeignLockCount"] = 0
    preflight["staleLookingLockCount"] = 2
    preflight["foreignLocksIgnored"] = False
    preflight["allowForeignBuildLocks"] = False
    preflight["staleForeignLockCount"] = 1
    preflight["findings"] = [
        {"id": "active_build_lane", "detail": "local source build"},
        {"id": "verification_error", "detail": "ps failed"},
    ]
    downloads["status"] = "fail"
    downloads["downloads_has_marker"] = False

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["preflightActiveLockCount"] == 3
    assert result["preflightBlockingLockCount"] == 1
    assert result["preflightForeignLockCount"] == 2
    assert result["preflightIgnoredForeignLockCount"] == 0
    assert result["preflightFindingCount"] == 2
    assert result["preflightForeignLocksIgnored"] is False
    assert result["preflightAllowForeignBuildLocks"] is False
    assert result["preflightStaleLookingLockCount"] == 2
    assert result["preflightStaleForeignLockCount"] == 1
    assert "public-edge deploy preflight is not pass" in result["failures"]
    assert "downloads version marker proof is not pass" in result["failures"]


def test_postdeploy_gate_surfaces_preflight_overlay_fingerprint_drift() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    preflight["status"] = "fail"
    preflight["findings"] = [
        {
            "id": "public_edge_overlay_source_fingerprint_mismatch",
            "detail": "overlay build info source fingerprint does not match current source: landing",
        }
    ]
    preflight["overlayBuildInfoSourceFingerprint"] = {
        "aggregateMatchesCurrentSource": False,
        "recordedAggregateSha256": "b" * 64,
        "expectedAggregateSha256": "a" * 64,
        "missingKeys": [],
        "mismatchedKeys": ["landing"],
    }

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource"] is False
    assert result["preflightOverlayBuildInfoSourceFingerprintRecordedAggregateSha256"] == "b" * 64
    assert result["preflightOverlayBuildInfoSourceFingerprintExpectedAggregateSha256"] == "a" * 64
    assert result["preflightOverlayBuildInfoSourceFingerprintMissingKeys"] == []
    assert result["preflightOverlayBuildInfoSourceFingerprintMismatchedKeys"] == ["landing"]
    assert "public-edge preflight overlay build info source fingerprint does not match current source: landing" in result["failures"]


def test_postdeploy_gate_fails_when_downloads_semantics_contradict_pass() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["downloads_has_marker"] = False
    downloads["status_redirect_has_marker"] = False
    downloads["visible_version"] = ""
    downloads["status_redirect_version"] = ""

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["downloadsStatus"] == "pass"
    assert "downloads receipt does not prove /downloads version marker" in result["failures"]
    assert "downloads receipt does not prove /status version marker" in result["failures"]
    assert "downloads receipt missing visible Version text" in result["failures"]
    assert "downloads receipt missing /status visible Version text" in result["failures"]


def test_postdeploy_gate_fails_when_status_redirect_heading_is_stale_generic_copy() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["status_redirect_heading"] = "Updated"
    downloads["status_redirect_heading_recognized"] = False
    downloads["status_redirect_heading_expected"] = "Stable downloads"
    downloads["status_redirect_heading_matches_release_channel"] = False
    downloads["status_redirect_heading_uses_generic_updated_copy"] = True

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["statusRedirectHeading"] == "Updated"
    assert "downloads receipt does not prove a recognized /status decision heading" in result["failures"]
    assert "downloads receipt still proves the stale generic Updated /status heading" in result["failures"]
    assert "downloads receipt does not prove the /status heading matches release posture" in result["failures"]


def test_postdeploy_gate_fails_when_downloads_marker_values_are_empty() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["status"] = "fail"
    downloads["failures"] = [
        "/downloads data-downloads-release-version is empty",
        "/status data-downloads-release-version is empty",
    ]
    downloads["downloads_version_marker_value"] = ""
    downloads["status_redirect_version_marker_value"] = ""
    downloads["downloads_version_marker_matches_release_channel"] = False
    downloads["status_redirect_version_marker_matches_release_channel"] = False
    downloads["visible_version_matches_release_channel"] = False
    downloads["status_redirect_version_matches_release_channel"] = False

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
    )

    assert result["status"] == "fail"
    assert result["downloadsStatus"] == "fail"
    assert result["downloadsVersionMarkerValue"] == ""
    assert result["statusRedirectVersionMarkerValue"] == ""
    assert result["visibleVersionMatchesReleaseChannel"] is False
    assert result["statusRedirectVersionMatchesReleaseChannel"] is False
    assert result["downloadsVersionMarkerMatchesReleaseChannel"] is False
    assert result["statusRedirectVersionMarkerMatchesReleaseChannel"] is False
    assert "downloads version marker proof is not pass" in result["failures"]
    assert "downloads receipt missing /downloads version marker value" in result["failures"]
    assert "downloads receipt missing /status version marker value" in result["failures"]
    assert "downloads version marker data does not match release channel" in result["failures"]
    assert "status redirect version marker data does not match release channel" in result["failures"]


def test_postdeploy_gate_fails_when_visible_version_mismatches_release_channel() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["visible_version"] = "Version 0.0.0.1"
    downloads["visible_version_matches_release_channel"] = False

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
    )

    assert result["status"] == "fail"
    assert result["expectedReleaseVersion"] == "run-20260630"
    assert result["visibleVersionMatchesReleaseChannel"] is False
    assert "downloads visible Version text does not match release channel" in result["failures"]


def test_postdeploy_gate_fails_when_status_redirect_version_mismatches_release_channel() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["status_redirect_version"] = "Version 0.0.0.1"
    downloads["status_redirect_version_matches_release_channel"] = False

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
    )

    assert result["status"] == "fail"
    assert result["expectedReleaseVersion"] == "run-20260630"
    assert result["visibleVersionMatchesReleaseChannel"] is True
    assert result["statusRedirectVersionMatchesReleaseChannel"] is False
    assert "status redirect visible Version text does not match release channel" in result["failures"]


def test_postdeploy_gate_fails_when_live_release_manifest_posture_mismatches_release_channel() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["release_manifest_status"] = "draft"
    downloads["release_manifest_status_matches_release_channel"] = False
    downloads["release_manifest_channel"] = "preview"
    downloads["release_manifest_channel_matches_release_channel"] = False
    downloads["release_manifest_supportability_state"] = "review_required"
    downloads["release_manifest_supportability_matches_release_channel"] = False
    downloads["release_manifest_rollout_state"] = "coverage_incomplete"
    downloads["release_manifest_rollout_matches_release_channel"] = False

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
    )

    assert result["status"] == "fail"
    assert result["releaseManifestStatus"] == "draft"
    assert result["releaseManifestChannel"] == "preview"
    assert result["releaseManifestSupportabilityState"] == "review_required"
    assert result["releaseManifestRolloutState"] == "coverage_incomplete"
    assert "downloads receipt live release manifest status does not match release channel" in result["failures"]
    assert "downloads receipt live release manifest channel does not match release channel" in result["failures"]
    assert "downloads receipt live release manifest supportability does not match release channel" in result["failures"]
    assert "downloads receipt live release manifest rollout does not match release channel" in result["failures"]


def test_postdeploy_gate_fails_when_expected_release_posture_is_not_launch_gold() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["expected_release_status"] = "draft"
    downloads["expected_release_channel"] = ""
    downloads["expected_release_supportability_state"] = "review_required"
    downloads["expected_release_rollout_state"] = "coverage_incomplete"
    downloads["release_manifest_status"] = "draft"
    downloads["release_manifest_status_matches_release_channel"] = True
    downloads["release_manifest_supportability_state"] = "review_required"
    downloads["release_manifest_rollout_state"] = "coverage_incomplete"
    downloads["release_manifest_supportability_matches_release_channel"] = True
    downloads["release_manifest_rollout_matches_release_channel"] = True

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
    )

    assert result["status"] == "fail"
    assert result["expectedReleaseStatus"] == "draft"
    assert result["expectedReleaseChannel"] == ""
    assert result["expectedReleaseSupportabilityState"] == "review_required"
    assert result["expectedReleaseRolloutState"] == "coverage_incomplete"
    assert "downloads receipt expected release status is not published" in result["failures"]
    assert "downloads receipt missing expected release channel" in result["failures"]
    assert "downloads receipt expected release rollout is blocking: coverage_incomplete" in result["failures"]


def test_postdeploy_gate_rejects_stable_channel_with_non_launch_supportability() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["expected_release_status"] = "published"
    downloads["expected_release_channel"] = "public_stable"
    downloads["expected_release_supportability_state"] = "preview_supported"
    downloads["expected_release_rollout_state"] = "public_stable"
    downloads["release_manifest_status"] = "published"
    downloads["release_manifest_status_matches_release_channel"] = True
    downloads["release_manifest_supportability_state"] = "preview_supported"
    downloads["release_manifest_supportability_matches_release_channel"] = True
    downloads["release_manifest_rollout_state"] = "public_stable"
    downloads["release_manifest_rollout_matches_release_channel"] = True

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
    )

    assert result["status"] == "fail"
    assert result["expectedReleaseChannel"] == "public_stable"
    assert result["expectedReleaseSupportabilityState"] == "preview_supported"
    assert "downloads receipt expected release supportability is not launch-supported" in result["failures"]


def test_postdeploy_gate_fails_when_release_manifest_copy_is_unsafe() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    downloads["expected_release_channel"] = "preview"
    downloads["expected_release_supportability_state"] = "preview_supported"
    downloads["expected_release_rollout_state"] = "promoted_preview"
    downloads["release_manifest_channel"] = "preview"
    downloads["release_manifest_supportability_state"] = "preview_supported"
    downloads["release_manifest_rollout_state"] = "promoted_preview"
    downloads["public_release_copy_safe"] = False
    downloads["public_release_unsafe_copy_markers"] = ["checks are clear"]
    downloads["release_manifest_copy_safe"] = False
    downloads["release_manifest_unsafe_copy_markers"] = ["checks are clear"]

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        expected_release_version="run-20260630",
    )

    assert result["status"] == "fail"
    assert result["publicReleaseManifestCopySafe"] is False
    assert result["releaseManifestCopySafe"] is False
    assert "downloads receipt static public release manifest copy is not safe" in result["failures"]
    assert "downloads receipt live release manifest copy is not safe" in result["failures"]


def test_postdeploy_gate_fails_when_pwa_static_fails() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    pwa_static["status"] = "fail"

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert "public PWA static asset proof is not pass" in result["failures"]


def test_postdeploy_gate_fails_when_pwa_static_semantics_contradict_pass() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    pwa_static["manifests"] = [{}]
    pwa_static["role_manifests"] = []
    pwa_static["assets"] = []
    pwa_static["service_worker"] = {
        "worker_kind": "portal",
        "cache_name": "chummer-public-v4",
        "ledger_stream_non_cacheable": False,
        "ledger_stream_precached": True,
    }

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["pwaStaticStatus"] == "pass"
    assert result["pwaManifestCount"] == 1
    assert result["rolePwaManifestCount"] == 0
    assert result["pwaAssetCount"] == 0
    assert result["pwaRootWorkerKind"] == "portal"
    assert "public PWA static proof does not include all manifests" in result["failures"]
    assert "public PWA static proof does not include the Player role manifest" in result["failures"]
    assert "public PWA static proof does not include the GameMaster role manifest" in result["failures"]
    assert "public PWA static proof does not include required assets" in result["failures"]
    assert "public PWA static proof does not keep ledger stream non-cacheable" in result["failures"]
    assert "public PWA static proof precaches personalized ledger stream" in result["failures"]
    assert "public PWA static proof does not use the Play root service worker" in result["failures"]


def test_postdeploy_gate_fails_when_mobile_ledger_boundary_fails() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    mobile_ledger["status"] = "fail"

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["mobileLedgerStatus"] == "fail"
    assert "mobile PWA ledger boundary proof is not pass" in result["failures"]


def test_postdeploy_gate_fails_when_mobile_ledger_semantics_contradict_pass() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    mobile_ledger["payload_status"] = "live"
    mobile_ledger["cache_control"] = "public, max-age=3600"
    mobile_ledger["vary"] = "Accept-Encoding"

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["mobileLedgerStatus"] == "pass"
    assert result["mobileLedgerPayloadStatus"] == "live"
    assert "mobile ledger receipt payload is not opt_in_required" in result["failures"]
    assert "mobile ledger cache-control is missing private/no-store/no-cache/max-age=0" in result["failures"]
    assert "mobile ledger vary is missing Cookie and Authorization" in result["failures"]


def test_postdeploy_gate_fails_when_ready_mobile_handoff_fails() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    ready_mobile_handoff["status"] = "fail"

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["readyMobileHandoffStatus"] == "fail"
    assert "Ready mobile handoff proof is not pass" in result["failures"]


def test_postdeploy_gate_fails_when_ready_mobile_handoff_semantics_contradict_pass() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    ready_mobile_handoff["tool_ids"] = ["inventory", "health"]
    ready_mobile_handoff["packet_roles"] = ["player"]
    ready_mobile_handoff["frontdoor_launch_route"] = "/mobile"
    ready_mobile_handoff["role_routes"] = [
        {
            "role": "Player",
            "mode": "player",
            "route": "/mobile/player",
        }
    ]

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["readyMobileHandoffStatus"] == "pass"
    assert "Ready mobile handoff is missing required tools: ammo, living_world, modifiers, quick_rolls" in result["failures"]
    assert "Ready mobile handoff is missing required packet roles: gm, organizer" in result["failures"]
    assert "Ready mobile handoff frontdoor launch route is not /mobile/player" in result["failures"]
    assert "Ready mobile handoff Player manifest path is not /manifest.player.webmanifest" in result["failures"]
    assert "Ready mobile handoff is missing the GameMaster role route" in result["failures"]


def test_postdeploy_gate_fails_when_participate_iframe_shell_fails() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    participate_iframe_shell["status"] = "fail"
    participate_iframe_shell["route_count"] = 2
    participate_iframe_shell["iframe_route_count"] = 0

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["participateIframeShellStatus"] == "fail"
    assert result["participateIframeRouteCount"] == 2
    assert result["participateIframeRouteIframeCount"] == 0
    assert "Participate iframe shell proof is not pass" in result["failures"]


def test_postdeploy_gate_fails_when_participate_iframe_semantics_contradict_pass() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    participate_iframe_shell["route_count"] = 1
    participate_iframe_shell["iframe_route_count"] = 1
    participate_iframe_shell["offline_fallback_route_count"] = 1

    result = module.compose_status(preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell)

    assert result["status"] == "fail"
    assert result["participateIframeShellStatus"] == "pass"
    assert result["participateIframeRouteCount"] == 1
    assert result["participateIframeRouteOfflineFallbackCount"] == 1
    assert "Participate iframe shell route count is below required public routes" in result["failures"]
    assert "Participate iframe shell does not prove both iframe routes" in result["failures"]
    assert "Participate iframe shell is using offline fallback routes" in result["failures"]


def test_postdeploy_gate_can_require_downloads_status_browser_proof() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-downloads-status-browser",
            "artifact": {
                "contractName": "chummer.downloads_status_e2e.v1",
                "status_redirect_heading": "Stable downloads",
                "status_redirect_heading_recognized": True,
                "status_redirect_heading_expected": "Stable downloads",
                "status_redirect_heading_matches_release_channel": True,
                "status_redirect_heading_uses_generic_updated_copy": False,
            },
        },
    )

    assert result["status"] == "pass"
    assert result["downloadsStatusBrowserStatus"] == "pass"
    assert result["downloadsStatusBrowserArtifactContract"] == "chummer.downloads_status_e2e.v1"
    assert result["downloadsStatusBrowserStatusRedirectHeading"] == "Stable downloads"
    assert result["downloadsStatusBrowserStatusRedirectHeadingMatchesReleaseChannel"] is True

    failing = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        {
            "status": "fail",
            "exitCode": 1,
            "artifactDir": "/tmp/chummer-downloads-status-browser",
            "artifact": {
                "contractName": "chummer.downloads_status_e2e.v1",
                "status_redirect_heading": "Stable downloads",
                "status_redirect_heading_recognized": True,
                "status_redirect_heading_expected": "Stable downloads",
                "status_redirect_heading_matches_release_channel": True,
                "status_redirect_heading_uses_generic_updated_copy": False,
            },
        },
    )

    assert failing["status"] == "fail"
    assert failing["downloadsStatusBrowserStatus"] == "fail"
    assert failing["downloadsStatusBrowserExitCode"] == 1
    assert "downloads-status Playwright proof is not pass" in failing["failures"]


def test_postdeploy_gate_rejects_downloads_status_browser_proof_when_status_heading_semantics_drift() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-downloads-status-browser",
            "artifact": {
                "contractName": "chummer.downloads_status_e2e.v1",
                "status_redirect_heading": "Updated",
                "status_redirect_heading_recognized": False,
                "status_redirect_heading_expected": "Stable downloads",
                "status_redirect_heading_matches_release_channel": False,
                "status_redirect_heading_uses_generic_updated_copy": True,
            },
        },
    )

    assert result["status"] == "fail"
    assert result["downloadsStatusBrowserStatus"] == "pass"
    assert result["downloadsStatusBrowserStatusRedirectHeading"] == "Updated"
    assert result["downloadsStatusBrowserStatusRedirectHeadingRecognized"] is False
    assert result["downloadsStatusBrowserStatusRedirectHeadingMatchesReleaseChannel"] is False
    assert result["downloadsStatusBrowserStatusRedirectHeadingUsesGenericUpdatedCopy"] is True
    assert "downloads-status Playwright proof does not prove a recognized /status decision heading" in result["failures"]
    assert "downloads-status Playwright proof still uses stale generic Updated heading" in result["failures"]
    assert "downloads-status Playwright proof does not prove the /status heading matches release posture" in result["failures"]


def test_downloads_status_browser_timeout_returns_failed_receipt(monkeypatch, tmp_path) -> None:
    module = load_module()

    def timeout_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=["npx", "playwright"],
            timeout=120,
            output="partial stdout",
            stderr="partial stderr",
        )

    monkeypatch.setattr(module.subprocess, "run", timeout_run)

    result = module.run_downloads_status_playwright("https://chummer.run", tmp_path, 20)

    assert result["status"] == "fail"
    assert result["exitCode"] == 124
    assert result["timedOut"] is True
    assert result["timeoutSeconds"] == 120
    assert result["artifact"] == {}
    assert result["stdoutTail"] == "partial stdout"
    assert result["stderrTail"] == "partial stderr"


def test_downloads_status_browser_can_reuse_existing_artifact(monkeypatch, tmp_path) -> None:
    module = load_module()
    artifact_path = tmp_path / "DOWNLOADS_STATUS_E2E.generated.json"
    artifact_path.write_text(
        json.dumps(
            {
                "contractName": "chummer.downloads_status_e2e.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
        ),
        encoding="utf-8",
    )

    def unexpected_run(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("Playwright should not run when a reusable artifact already exists.")

    monkeypatch.setattr(module, "run_playwright_command", unexpected_run)

    result = module.run_downloads_status_playwright(
        "https://chummer.run",
        tmp_path,
        20,
        reuse_existing_artifact=True,
    )

    assert result["status"] == "pass"
    assert result["exitCode"] == 0
    assert result["artifactReused"] is True
    assert result["playwrightExecuted"] is False
    assert result["artifactBaseUrlMatchesRequested"] is True
    assert result["artifactContract"] == "chummer.downloads_status_e2e.v1"
    assert result["artifactFresh"] is True


def test_postdeploy_gate_rejects_downloads_status_wrong_artifact_contract() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-downloads-status-browser",
            "artifact": {
                "contractName": "chummer.downloads_status_e2e.preview",
            },
        },
    )

    assert result["status"] == "fail"
    assert result["downloadsStatusBrowserArtifactContract"] == "chummer.downloads_status_e2e.preview"
    assert "downloads-status Playwright artifact contract is not chummer.downloads_status_e2e.v1" in result["failures"]


def test_downloads_status_browser_stale_artifact_reruns_playwright(monkeypatch, tmp_path) -> None:
    module = load_module()
    artifact_path = tmp_path / "DOWNLOADS_STATUS_E2E.generated.json"
    artifact_path.write_text(
        json.dumps(
            {
                "contractName": "chummer.downloads_status_e2e.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": (datetime.now(UTC) - timedelta(hours=48)).isoformat().replace("+00:00", "Z"),
            }
        ),
        encoding="utf-8",
    )
    invoked: dict[str, object] = {}

    def fake_run(command, env, timeout_seconds):  # noqa: ANN001
        invoked["command"] = command
        invoked["env"] = env
        invoked["timeout_seconds"] = timeout_seconds
        artifact_path.write_text(
            json.dumps(
                {
                    "contractName": "chummer.downloads_status_e2e.v1",
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                }
            ),
            encoding="utf-8",
        )
        return 0, "fresh run", "", False

    monkeypatch.setattr(module, "run_playwright_command", fake_run)

    result = module.run_downloads_status_playwright(
        "https://chummer.run",
        tmp_path,
        20,
        reuse_existing_artifact=True,
    )

    assert result["status"] == "pass"
    assert result["artifactReused"] is False
    assert result["playwrightExecuted"] is True
    assert invoked["timeout_seconds"] == 120


def test_postdeploy_gate_can_require_mobile_pwa_viewport_browser_proof() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    mobile_routes = sorted(module.REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES)

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-mobile-pwa-viewport",
            "artifact": {
                "contractName": "chummer.mobile_pwa_viewport_smoke.v1",
                "routes": mobile_routes,
                "route_count": len(mobile_routes),
                "viewport_count": 3,
            },
        },
    )

    assert result["status"] == "pass"
    assert result["mobilePwaViewportStatus"] == "pass"
    assert result["mobilePwaViewportArtifactContract"] == "chummer.mobile_pwa_viewport_smoke.v1"
    assert result["mobilePwaViewportRouteCount"] == 6
    assert result["mobilePwaViewportViewportCount"] == 3
    assert result["mobilePwaViewportRoutes"] == mobile_routes
    assert result["mobilePwaViewportMissingRoutes"] == []

    failing = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        {
            "status": "fail",
            "exitCode": 1,
            "artifactDir": "/tmp/chummer-mobile-pwa-viewport",
            "artifact": {
                "contractName": "chummer.mobile_pwa_viewport_smoke.v1",
                "routes": mobile_routes,
                "route_count": len(mobile_routes),
                "viewport_count": 3,
            },
        },
    )

    assert failing["status"] == "fail"
    assert failing["mobilePwaViewportStatus"] == "fail"
    assert "mobile PWA viewport Playwright proof is not pass" in failing["failures"]


def test_postdeploy_gate_rejects_mobile_pwa_viewport_missing_role_routes() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    mobile_routes = sorted(module.REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES - {"/mobile/gm"})

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-mobile-pwa-viewport",
            "artifact": {
                "contractName": "chummer.mobile_pwa_viewport_smoke.v1",
                "routes": mobile_routes,
                "route_count": len(mobile_routes),
                "viewport_count": 3,
            },
        },
    )

    assert result["status"] == "fail"
    assert result["mobilePwaViewportMissingRoutes"] == ["/mobile/gm"]
    assert "mobile PWA viewport Playwright route count is below required mobile routes" in result["failures"]
    assert "mobile PWA viewport Playwright proof is missing required routes: /mobile/gm" in result["failures"]


def test_postdeploy_gate_can_require_pwa_offline_cache_browser_proof() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        None,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-pwa-offline-cache",
            "artifact": {
                "contractName": "chummer.pwa_offline_cache.v1",
                "offline_reload": "pass",
                "cached_paths": [
                    "/manifest.player.webmanifest",
                    "/manifest.gm.webmanifest",
                    "/mobile.css",
                    "/mobile-turn-companion.js",
                    "/mobile/player",
                    "/mobile/gm",
                ],
                "offline_role_routes": [
                    {
                        "name": "player",
                        "cached_path": "/mobile/player",
                        "role": "Player",
                        "manifest": "/manifest.player.webmanifest",
                        "offline_reload": "pass",
                    },
                    {
                        "name": "gm",
                        "cached_path": "/mobile/gm",
                        "role": "GameMaster",
                        "manifest": "/manifest.gm.webmanifest",
                        "offline_reload": "pass",
                    },
                ],
                "personalized_ledger_cached": False,
            },
        },
    )

    assert result["status"] == "pass"
    assert result["pwaOfflineCacheStatus"] == "pass"
    assert result["pwaOfflineCacheArtifactContract"] == "chummer.pwa_offline_cache.v1"
    assert result["pwaOfflineCacheOfflineReload"] == "pass"
    assert "/mobile/player" in result["pwaOfflineCacheCachedPaths"]
    assert "/mobile/gm" in result["pwaOfflineCacheCachedPaths"]
    assert result["pwaOfflineCachePersonalizedLedgerCached"] is False
    assert {item["name"] for item in result["pwaOfflineCacheOfflineRoleRoutes"]} == {"player", "gm"}

    failing = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        None,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-pwa-offline-cache",
            "artifact": {
                "contractName": "chummer.pwa_offline_cache.preview",
                "offline_reload": "fail",
                "cached_paths": ["/mobile"],
                "offline_role_routes": [],
                "personalized_ledger_cached": True,
            },
        },
    )

    assert failing["status"] == "fail"
    assert "PWA offline cache Playwright artifact contract is not chummer.pwa_offline_cache.v1" in failing["failures"]
    assert "PWA offline cache proof did not cache /manifest.player.webmanifest" in failing["failures"]
    assert "PWA offline cache proof did not cache /mobile/player" in failing["failures"]
    assert "PWA offline cache proof did not cache /mobile/gm" in failing["failures"]
    assert "PWA offline cache proof cached the personalized ledger stream" in failing["failures"]
    assert "PWA offline cache proof is missing player offline role route" in failing["failures"]
    assert "PWA offline cache proof is missing gm offline role route" in failing["failures"]


def test_postdeploy_gate_rejects_mobile_pwa_viewport_wrong_artifact_contract() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    mobile_routes = sorted(module.REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES)

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-mobile-pwa-viewport",
            "artifact": {
                "contractName": "chummer.mobile_pwa_viewport_smoke.preview",
                "routes": mobile_routes,
                "route_count": len(mobile_routes),
                "viewport_count": 3,
            },
        },
    )

    assert result["status"] == "fail"
    assert result["mobilePwaViewportArtifactContract"] == "chummer.mobile_pwa_viewport_smoke.preview"
    assert "mobile PWA viewport Playwright artifact contract is not chummer.mobile_pwa_viewport_smoke.v1" in result["failures"]


def test_postdeploy_gate_can_require_frontdoor_navigation_browser_proof() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-frontdoor-navigation",
            "mobileArtifact": {
                "contractName": "chummer.frontdoor_mobile_launch.v1",
                "gated_targets": ["Build", "Play"],
                "public_targets": [],
                "homepage_lane_text": "Current public lane: Stable.",
                "play_route": "/mobile/player",
                "play_sign_in_route": "/login?next=%2Fmobile%2Fplayer",
                "direct_player_route": "/mobile/player",
                "direct_player_http_status": 200,
                "final_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player",
                "live_turn_companion_shell": True,
                "pwa_manifest_path": "/manifest.player.webmanifest",
                "pwa_role": "Player",
                "blazor_shell": "interactive-server",
                "rybbit_configured": True,
                "rybbit_tag": "mobile_play_shell",
                "rybbit_route": "/mobile/player",
                "rybbit_mode": "player",
                "rybbit_role": "Player",
                "rybbit_site_id_present": True,
                "rybbit_script_url_present": True,
                "rybbit_script_url_allowed": True,
                "rybbit_skip_patterns": ["/mobile/**"],
                "rybbit_mask_patterns": ["/api/play/**", "/mobile/**"],
                "rybbit_skip_mobile_paths": True,
                "rybbit_mask_mobile_paths": True,
                "rybbit_masks_private_play_routes": True,
                "rybbit_replay_block_selector": "[data-turn-root]",
                "rybbit_replay_blocks_turn_root": True,
                "player_session_handoff_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player",
                "player_session_handoff_status": "Session handoff is ready in the link above.",
                "player_session_handoff_link_text": "Open session handoff link",
                "player_session_handoff_preserves_session": True,
                "player_session_handoff_preserves_role": True,
                "player_session_handoff_strips_device": True,
                "player_session_handoff_sender_device_id_present": True,
                "gm_route": "/mobile/gm?sessionId=session-main&role=GameMaster",
                "gm_http_status": 200,
                "gm_final_url": "https://chummer.run/mobile/gm?sessionId=session-main&role=GameMaster",
                "gm_live_turn_companion_shell": True,
                "gm_pwa_manifest_path": "/manifest.gm.webmanifest",
                "gm_pwa_role": "GameMaster",
                "gm_blazor_shell": "interactive-server",
                "gm_rybbit_configured": True,
                "gm_rybbit_tag": "mobile_play_shell",
                "gm_rybbit_route": "/mobile/gm",
                "gm_rybbit_mode": "gm",
                "gm_rybbit_role": "GameMaster",
                "gm_rybbit_site_id_present": True,
                "gm_rybbit_script_url_present": True,
                "gm_rybbit_script_url_allowed": True,
                "gm_rybbit_skip_patterns": ["/mobile/**"],
                "gm_rybbit_mask_patterns": ["/api/play/**", "/mobile/**"],
                "gm_rybbit_skip_mobile_paths": True,
                "gm_rybbit_mask_mobile_paths": True,
                "gm_rybbit_masks_private_play_routes": True,
                "gm_rybbit_replay_block_selector": "[data-turn-root]",
                "gm_rybbit_replay_blocks_turn_root": True,
                "gm_session_handoff_url": "https://chummer.run/mobile/gm?sessionId=session-main&role=GameMaster",
                "gm_session_handoff_status": "Session handoff is ready in the link above.",
                "gm_session_handoff_link_text": "Open session handoff link",
                "gm_session_handoff_preserves_session": True,
                "gm_session_handoff_preserves_role": True,
                "gm_session_handoff_strips_device": True,
                "gm_session_handoff_sender_device_id_present": True,
            },
            "ledgerArtifact": {
                "contractName": "chummer.black_ledger_globe_frontdoor.v1",
                "ledger_primary": False,
            },
            "anchorArtifact": {
                "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                "entry_url": "https://chummer.run/#turn-runsite-card",
                "final_url": "https://chummer.run/mobile/player?sessionId=session-main&deviceId=device-player-main&role=Player#turn-runsite-card",
                "final_pathname": "/mobile/player",
                "final_hash": "#turn-runsite-card",
                "pwa_manifest_path": "/manifest.player.webmanifest",
                "pwa_role": "Player",
                "blazor_shell": "interactive-server",
                "session_id_present": True,
                "device_id_present": True,
                "failure": "",
            },
        },
    )

    assert result["status"] == "pass"
    assert result["frontdoorNavigationStatus"] == "pass"
    assert result["frontdoorNavigationMobileArtifactContract"] == "chummer.frontdoor_mobile_launch.v1"
    assert result["frontdoorNavigationLedgerArtifactContract"] == "chummer.black_ledger_globe_frontdoor.v1"
    assert result["frontdoorNavigationAnchorArtifactContract"] == "chummer.frontdoor_mobile_anchor_redirect.v1"
    assert result["frontdoorNavigationGatedTargets"] == ["Build", "Play"]
    assert result["frontdoorNavigationPublicTargets"] == []
    assert result["frontdoorNavigationHomepageLaneText"] == "Current public lane: Stable."
    assert result["frontdoorNavigationHomepageLaneExpected"] == "Current public lane: Stable."
    assert result["frontdoorNavigationHomepageLaneMatchesReleaseChannel"] is True
    assert result["frontdoorNavigationPlayRoute"] == "/mobile/player"
    assert result["frontdoorNavigationPlaySignInRoute"] == "/login?next=%2Fmobile%2Fplayer"
    assert result["frontdoorNavigationDirectPlayerRoute"] == "/mobile/player"
    assert result["frontdoorNavigationDirectPlayerHttpStatus"] == 200
    assert result["frontdoorNavigationFinalUrl"] == "https://chummer.run/mobile/player?sessionId=session-main&role=Player"
    assert result["frontdoorNavigationLiveTurnCompanionShell"] is True
    assert result["frontdoorNavigationPwaManifestPath"] == "/manifest.player.webmanifest"
    assert result["frontdoorNavigationPwaRole"] == "Player"
    assert result["frontdoorNavigationBlazorShell"] == "interactive-server"
    assert result["frontdoorNavigationRybbitConfigured"] is True
    assert result["frontdoorNavigationRybbitTag"] == "mobile_play_shell"
    assert result["frontdoorNavigationRybbitRoute"] == "/mobile/player"
    assert result["frontdoorNavigationRybbitMode"] == "player"
    assert result["frontdoorNavigationRybbitRole"] == "Player"
    assert result["frontdoorNavigationRybbitSiteIdPresent"] is True
    assert result["frontdoorNavigationRybbitScriptUrlPresent"] is True
    assert result["frontdoorNavigationRybbitScriptUrlAllowed"] is True
    assert result["frontdoorNavigationRybbitSkipPatterns"] == ["/mobile/**"]
    assert result["frontdoorNavigationRybbitMaskPatterns"] == ["/api/play/**", "/mobile/**"]
    assert result["frontdoorNavigationRybbitSkipMobilePaths"] is True
    assert result["frontdoorNavigationRybbitMaskMobilePaths"] is True
    assert result["frontdoorNavigationRybbitMasksPrivatePlayRoutes"] is True
    assert result["frontdoorNavigationRybbitReplayBlockSelector"] == "[data-turn-root]"
    assert result["frontdoorNavigationRybbitReplayBlocksTurnRoot"] is True
    assert result["frontdoorNavigationPlayerSessionHandoffUrl"] == "https://chummer.run/mobile/player?sessionId=session-main&role=Player"
    assert result["frontdoorNavigationPlayerSessionHandoffStatus"] == "Session handoff is ready in the link above."
    assert result["frontdoorNavigationPlayerSessionHandoffLinkText"] == "Open session handoff link"
    assert result["frontdoorNavigationPlayerSessionHandoffPreservesSession"] is True
    assert result["frontdoorNavigationPlayerSessionHandoffPreservesRole"] is True
    assert result["frontdoorNavigationPlayerSessionHandoffStripsDevice"] is True
    assert result["frontdoorNavigationPlayerSessionHandoffSenderDeviceIdPresent"] is True
    assert result["frontdoorNavigationGmRoute"] == "/mobile/gm?sessionId=session-main&role=GameMaster"
    assert result["frontdoorNavigationGmHttpStatus"] == 200
    assert result["frontdoorNavigationGmFinalUrl"] == "https://chummer.run/mobile/gm?sessionId=session-main&role=GameMaster"
    assert result["frontdoorNavigationGmLiveTurnCompanionShell"] is True
    assert result["frontdoorNavigationGmPwaManifestPath"] == "/manifest.gm.webmanifest"
    assert result["frontdoorNavigationGmPwaRole"] == "GameMaster"
    assert result["frontdoorNavigationGmBlazorShell"] == "interactive-server"
    assert result["frontdoorNavigationGmRybbitConfigured"] is True
    assert result["frontdoorNavigationGmRybbitTag"] == "mobile_play_shell"
    assert result["frontdoorNavigationGmRybbitRoute"] == "/mobile/gm"
    assert result["frontdoorNavigationGmRybbitMode"] == "gm"
    assert result["frontdoorNavigationGmRybbitRole"] == "GameMaster"
    assert result["frontdoorNavigationGmRybbitSiteIdPresent"] is True
    assert result["frontdoorNavigationGmRybbitScriptUrlPresent"] is True
    assert result["frontdoorNavigationGmRybbitScriptUrlAllowed"] is True
    assert result["frontdoorNavigationGmRybbitSkipPatterns"] == ["/mobile/**"]
    assert result["frontdoorNavigationGmRybbitMaskPatterns"] == ["/api/play/**", "/mobile/**"]
    assert result["frontdoorNavigationGmRybbitSkipMobilePaths"] is True
    assert result["frontdoorNavigationGmRybbitMaskMobilePaths"] is True
    assert result["frontdoorNavigationGmRybbitMasksPrivatePlayRoutes"] is True
    assert result["frontdoorNavigationGmRybbitReplayBlockSelector"] == "[data-turn-root]"
    assert result["frontdoorNavigationGmRybbitReplayBlocksTurnRoot"] is True
    assert result["frontdoorNavigationGmSessionHandoffUrl"] == "https://chummer.run/mobile/gm?sessionId=session-main&role=GameMaster"
    assert result["frontdoorNavigationGmSessionHandoffStatus"] == "Session handoff is ready in the link above."
    assert result["frontdoorNavigationGmSessionHandoffLinkText"] == "Open session handoff link"
    assert result["frontdoorNavigationGmSessionHandoffPreservesSession"] is True
    assert result["frontdoorNavigationGmSessionHandoffPreservesRole"] is True
    assert result["frontdoorNavigationGmSessionHandoffStripsDevice"] is True
    assert result["frontdoorNavigationGmSessionHandoffSenderDeviceIdPresent"] is True
    assert result["frontdoorNavigationLedgerPrimary"] is False
    assert result["frontdoorNavigationAnchorEntryUrl"] == "https://chummer.run/#turn-runsite-card"
    assert result["frontdoorNavigationAnchorFinalPath"] == "/mobile/player"
    assert result["frontdoorNavigationAnchorFinalHash"] == "#turn-runsite-card"
    assert result["frontdoorNavigationAnchorPwaManifestPath"] == "/manifest.player.webmanifest"
    assert result["frontdoorNavigationAnchorPwaRole"] == "Player"
    assert result["frontdoorNavigationAnchorBlazorShell"] == "interactive-server"
    assert result["frontdoorNavigationAnchorSessionIdPresent"] is True
    assert result["frontdoorNavigationAnchorDeviceIdPresent"] is True
    assert result["frontdoorNavigationAnchorFailure"] == ""
    assert result["frontdoorNavigationAnchorArtifactCurrentContractSatisfied"] is True

    failing = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        {
            "status": "fail",
            "exitCode": 1,
            "artifactDir": "/tmp/chummer-frontdoor-navigation",
            "mobileArtifact": {},
            "ledgerArtifact": {},
            "anchorArtifact": {},
        },
    )

    assert failing["status"] == "fail"
    assert failing["frontdoorNavigationStatus"] == "fail"
    assert "front-door navigation Playwright proof is not pass" in failing["failures"]
    assert failing["frontdoorNavigationAnchorFailure"] is None


def test_postdeploy_gate_surfaces_frontdoor_anchor_failure_detail() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    failing = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        {
            "status": "fail",
            "exitCode": 1,
            "artifactDir": "/tmp/chummer-frontdoor-navigation",
            "mobileArtifact": {},
            "ledgerArtifact": {},
            "anchorArtifact": {
                "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                "entry_url": "https://chummer.run/#turn-runsite-card?",
                "final_url": "https://chummer.run/#turn-runsite-card",
                "final_pathname": "/",
                "final_hash": "#turn-runsite-card",
                "pwa_manifest_path": "/manifest.json",
                "pwa_role": None,
                "blazor_shell": None,
                "session_id_present": False,
                "device_id_present": False,
                "failure": "page.waitForURL: Timeout 60000ms exceeded.",
            },
        },
    )

    assert failing["frontdoorNavigationAnchorFailure"] == "page.waitForURL: Timeout 60000ms exceeded."
    assert "front-door navigation homepage anchor proof failed: page.waitForURL: Timeout 60000ms exceeded." in failing["failures"]


def test_postdeploy_gate_accepts_canonical_frontdoor_anchor_entry_url() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-frontdoor-navigation",
            "mobileArtifact": {
                "contractName": "chummer.frontdoor_mobile_launch.v1",
                "gated_targets": ["Build", "Play"],
                "public_targets": [],
                "homepage_lane_text": "Current public lane: Stable.",
                "play_route": "/mobile/player",
                "play_sign_in_route": "/login?next=%2Fmobile%2Fplayer",
                "direct_player_http_status": 200,
                "direct_player_route": "/mobile/player",
                "final_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player",
                "live_turn_companion_shell": True,
                "pwa_manifest_path": "/manifest.player.webmanifest",
                "pwa_role": "Player",
                "blazor_shell": "interactive-server",
                "rybbit_configured": True,
                "rybbit_tag": "mobile_play_shell",
                "rybbit_route": "/mobile/player",
                "rybbit_mode": "player",
                "rybbit_role": "Player",
                "rybbit_site_id_present": True,
                "rybbit_script_url_present": True,
                "rybbit_script_url_allowed": True,
                "rybbit_skip_patterns": ["/mobile/**"],
                "rybbit_mask_patterns": ["/api/play/**", "/mobile/**"],
                "rybbit_skip_mobile_paths": True,
                "rybbit_mask_mobile_paths": True,
                "rybbit_masks_private_play_routes": True,
                "rybbit_replay_block_selector": "[data-turn-root]",
                "rybbit_replay_blocks_turn_root": True,
                "player_session_handoff_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player",
                "player_session_handoff_status": "Session handoff is ready in the link above.",
                "player_session_handoff_link_text": "Open session handoff link",
                "player_session_handoff_preserves_session": True,
                "player_session_handoff_preserves_role": True,
                "player_session_handoff_strips_device": True,
                "player_session_handoff_sender_device_id_present": True,
                "gm_route": "/mobile/gm?sessionId=session-main&role=GameMaster",
                "gm_http_status": 200,
                "gm_final_url": "https://chummer.run/mobile/gm?sessionId=session-main&role=GameMaster",
                "gm_live_turn_companion_shell": True,
                "gm_pwa_manifest_path": "/manifest.gm.webmanifest",
                "gm_pwa_role": "GameMaster",
                "gm_blazor_shell": "interactive-server",
                "gm_rybbit_configured": True,
                "gm_rybbit_tag": "mobile_play_shell",
                "gm_rybbit_route": "/mobile/gm",
                "gm_rybbit_mode": "gm",
                "gm_rybbit_role": "GameMaster",
                "gm_rybbit_site_id_present": True,
                "gm_rybbit_script_url_present": True,
                "gm_rybbit_script_url_allowed": True,
                "gm_rybbit_skip_patterns": ["/mobile/**"],
                "gm_rybbit_mask_patterns": ["/api/play/**", "/mobile/**"],
                "gm_rybbit_skip_mobile_paths": True,
                "gm_rybbit_mask_mobile_paths": True,
                "gm_rybbit_masks_private_play_routes": True,
                "gm_rybbit_replay_block_selector": "[data-turn-root]",
                "gm_rybbit_replay_blocks_turn_root": True,
                "gm_session_handoff_url": "https://chummer.run/mobile/gm?sessionId=session-main&role=GameMaster",
                "gm_session_handoff_status": "Session handoff is ready in the link above.",
                "gm_session_handoff_link_text": "Open session handoff link",
                "gm_session_handoff_preserves_session": True,
                "gm_session_handoff_preserves_role": True,
                "gm_session_handoff_strips_device": True,
                "gm_session_handoff_sender_device_id_present": True,
            },
            "ledgerArtifact": {
                "contractName": "chummer.black_ledger_globe_frontdoor.v1",
                "ledger_primary": False,
            },
            "anchorArtifact": {
                "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                "entry_url": "https://chummer.run/#turn-runsite-card",
                "final_url": "https://chummer.run/mobile/player?sessionId=session-main&deviceId=device-player-main&role=Player#turn-runsite-card",
                "final_pathname": "/mobile/player",
                "final_hash": "#turn-runsite-card",
                "pwa_manifest_path": "/manifest.player.webmanifest",
                "pwa_role": "Player",
                "blazor_shell": "interactive-server",
                "session_id_present": True,
                "device_id_present": True,
                "failure": "",
            },
        },
    )

    assert result["status"] == "pass"
    assert result["frontdoorNavigationAnchorEntryUrl"] == "https://chummer.run/#turn-runsite-card"
    assert "front-door navigation homepage anchor proof did not start from /#turn-runsite-card" not in result["failures"]


def test_postdeploy_gate_rejects_frontdoor_navigation_when_homepage_lane_disclosure_is_missing() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-frontdoor-navigation",
            "mobileArtifact": {
                "contractName": "chummer.frontdoor_mobile_launch.v1",
                "gated_targets": ["Build", "Play"],
                "public_targets": [],
                "homepage_lane_text": "",
                "play_route": "/mobile/player",
                "play_sign_in_route": "/login?next=%2Fmobile%2Fplayer",
                "direct_player_route": "/mobile/player",
                "direct_player_http_status": 200,
                "final_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player",
                "live_turn_companion_shell": True,
                "pwa_manifest_path": "/manifest.player.webmanifest",
                "pwa_role": "Player",
                "blazor_shell": "interactive-server",
                "rybbit_configured": True,
                "rybbit_tag": "mobile_play_shell",
                "rybbit_route": "/mobile/player",
                "rybbit_mode": "player",
                "rybbit_role": "Player",
                "rybbit_site_id_present": True,
                "rybbit_script_url_present": True,
                "rybbit_script_url_allowed": True,
                "rybbit_skip_patterns": ["/mobile/**"],
                "rybbit_mask_patterns": ["/api/play/**", "/mobile/**"],
                "rybbit_skip_mobile_paths": True,
                "rybbit_mask_mobile_paths": True,
                "rybbit_masks_private_play_routes": True,
                "rybbit_replay_block_selector": "[data-turn-root]",
                "rybbit_replay_blocks_turn_root": True,
                "player_session_handoff_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player",
                "player_session_handoff_status": "Session handoff is ready in the link above.",
                "player_session_handoff_link_text": "Open session handoff link",
                "player_session_handoff_preserves_session": True,
                "player_session_handoff_preserves_role": True,
                "player_session_handoff_strips_device": True,
                "player_session_handoff_sender_device_id_present": True,
                "gm_route": "/mobile/gm?sessionId=session-main&role=GameMaster",
                "gm_http_status": 200,
                "gm_final_url": "https://chummer.run/mobile/gm?sessionId=session-main&role=GameMaster",
                "gm_live_turn_companion_shell": True,
                "gm_pwa_manifest_path": "/manifest.gm.webmanifest",
                "gm_pwa_role": "GameMaster",
                "gm_blazor_shell": "interactive-server",
                "gm_rybbit_configured": True,
                "gm_rybbit_tag": "mobile_play_shell",
                "gm_rybbit_route": "/mobile/gm",
                "gm_rybbit_mode": "gm",
                "gm_rybbit_role": "GameMaster",
                "gm_rybbit_site_id_present": True,
                "gm_rybbit_script_url_present": True,
                "gm_rybbit_script_url_allowed": True,
                "gm_rybbit_skip_patterns": ["/mobile/**"],
                "gm_rybbit_mask_patterns": ["/api/play/**", "/mobile/**"],
                "gm_rybbit_skip_mobile_paths": True,
                "gm_rybbit_mask_mobile_paths": True,
                "gm_rybbit_masks_private_play_routes": True,
                "gm_rybbit_replay_block_selector": "[data-turn-root]",
                "gm_rybbit_replay_blocks_turn_root": True,
                "gm_session_handoff_url": "https://chummer.run/mobile/gm?sessionId=session-main&role=GameMaster",
                "gm_session_handoff_status": "Session handoff is ready in the link above.",
                "gm_session_handoff_link_text": "Open session handoff link",
                "gm_session_handoff_preserves_session": True,
                "gm_session_handoff_preserves_role": True,
                "gm_session_handoff_strips_device": True,
                "gm_session_handoff_sender_device_id_present": True,
            },
            "ledgerArtifact": {
                "contractName": "chummer.black_ledger_globe_frontdoor.v1",
                "ledger_primary": False,
            },
        },
    )

    assert result["status"] == "fail"
    assert result["frontdoorNavigationHomepageLaneText"] == ""
    assert result["frontdoorNavigationHomepageLaneExpected"] == "Current public lane: Stable."
    assert result["frontdoorNavigationHomepageLaneMatchesReleaseChannel"] is False
    assert "front-door navigation homepage does not disclose current public lane" in result["failures"]
    assert "front-door navigation homepage current public lane copy does not match release posture" in result["failures"]


def test_postdeploy_gate_surfaces_frontdoor_playwright_stderr_without_cascading_missing_artifact_failures() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        {
            "status": "fail",
            "exitCode": 1,
            "artifactDir": "/tmp/chummer-frontdoor-navigation",
            "mobileArtifact": {},
            "ledgerArtifact": {},
            "anchorArtifact": {},
            "stderrTail": "Error: Homepage still serves legacy release posture copy: Current release: Preview build.\\n    at assertProof (...)",
        },
    )

    assert result["status"] == "fail"
    assert result["frontdoorNavigationStatus"] == "fail"
    assert "front-door navigation Playwright proof is not pass" in result["failures"]
    assert (
        "front-door navigation Playwright proof failed before artifacts were written: "
        "Error: Homepage still serves legacy release posture copy: Current release: Preview build."
    ) in result["failures"]
    assert "front-door navigation does not gate Build" not in result["failures"]
    assert "front-door navigation mobile artifact contract is not chummer.frontdoor_mobile_launch.v1" not in result["failures"]


def test_postdeploy_gate_rejects_frontdoor_navigation_wrong_artifact_contracts() -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()

    result = module.compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        None,
        None,
        {
            "status": "pass",
            "exitCode": 0,
            "artifactDir": "/tmp/chummer-frontdoor-navigation",
            "mobileArtifact": {
                "contractName": "chummer.frontdoor_mobile_launch.preview",
                "gated_targets": ["Build", "Play"],
                "public_targets": [],
                "play_route": "/mobile/player",
                "play_sign_in_route": "/login?next=%2Fmobile%2Fplayer",
                "direct_player_route": "/mobile/player",
            },
            "ledgerArtifact": {
                "contractName": "chummer.black_ledger_globe_frontdoor.preview",
                "ledger_primary": False,
            },
        },
    )

    assert result["status"] == "fail"
    assert "front-door navigation mobile artifact contract is not chummer.frontdoor_mobile_launch.v1" in result["failures"]
    assert "front-door navigation ledger artifact contract is not chummer.black_ledger_globe_frontdoor.v1" in result["failures"]


def test_main_passes_custom_release_channel_receipt_to_downloads_child(monkeypatch, tmp_path) -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    release_channel = tmp_path / "custom-release-channel.json"
    release_channel.write_text('{"version":"run-20260630"}', encoding="utf-8")
    output = tmp_path / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"
    commands: list[list[str]] = []

    def fake_run_child(command, output_path, allow_failure=False):  # noqa: ANN001
        commands.append(command)
        command_text = " ".join(command)
        if "check_public_edge_deploy_preflight.py" in command_text:
            return preflight
        if "verify_downloads_version_marker.py" in command_text:
            return downloads
        if "verify_public_pwa_static_assets.py" in command_text:
            return pwa_static
        if "verify_mobile_pwa_ledger_boundary.py" in command_text:
            return mobile_ledger
        if "verify_ready_mobile_handoff_contract.py" in command_text:
            return ready_mobile_handoff
        if "verify_participate_iframe_shell.py" in command_text:
            return participate_iframe_shell
        raise AssertionError(f"unexpected child command: {command_text}")

    monkeypatch.setattr(module, "run_child", fake_run_child)
    monkeypatch.setattr(module, "probe_role_alias_routes", lambda base_url, timeout_seconds: passing_role_alias_routes())

    exit_code = module.main(
        [
            "--base-url",
            "https://chummer.run",
            "--release-channel-receipt",
            str(release_channel),
            "--output",
            str(output),
        ]
    )

    downloads_command = next(
        command
        for command in commands
        if any("verify_downloads_version_marker.py" in item for item in command)
    )
    preflight_command = next(
        command
        for command in commands
        if any("check_public_edge_deploy_preflight.py" in item for item in command)
    )
    assert exit_code == 0
    assert "--allow-foreign-build-locks" in preflight_command
    assert "--allow-stale-foreign-build-locks" in preflight_command
    assert "--overlay-root" in preflight_command
    assert preflight_command[preflight_command.index("--overlay-root") + 1] == str(module.DEFAULT_PUBLIC_EDGE_OVERLAY_ROOT.resolve())
    assert "--release-channel-receipt" in downloads_command
    assert downloads_command[downloads_command.index("--release-channel-receipt") + 1] == str(release_channel)
    assert "--skip-release-version-match" not in downloads_command


def test_main_passes_custom_overlay_root_to_preflight_child(monkeypatch, tmp_path) -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    output = tmp_path / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"
    overlay_root = tmp_path / "overlay" / "app"
    commands: list[list[str]] = []

    def fake_run_child(command, output_path, allow_failure=False):  # noqa: ANN001
        commands.append(command)
        command_text = " ".join(command)
        if "check_public_edge_deploy_preflight.py" in command_text:
            return preflight
        if "verify_downloads_version_marker.py" in command_text:
            return downloads
        if "verify_public_pwa_static_assets.py" in command_text:
            return pwa_static
        if "verify_mobile_pwa_ledger_boundary.py" in command_text:
            return mobile_ledger
        if "verify_ready_mobile_handoff_contract.py" in command_text:
            return ready_mobile_handoff
        if "verify_participate_iframe_shell.py" in command_text:
            return participate_iframe_shell
        raise AssertionError(f"unexpected child command: {command_text}")

    monkeypatch.setattr(module, "run_child", fake_run_child)
    monkeypatch.setattr(module, "probe_role_alias_routes", lambda base_url, timeout_seconds: passing_role_alias_routes())

    exit_code = module.main(
        [
            "--base-url",
            "https://chummer.run",
            "--overlay-root",
            str(overlay_root),
            "--output",
            str(output),
        ]
    )

    preflight_command = next(
        command
        for command in commands
        if any("check_public_edge_deploy_preflight.py" in item for item in command)
    )
    assert exit_code == 0
    assert "--allow-foreign-build-locks" in preflight_command
    assert "--overlay-root" in preflight_command
    assert preflight_command[preflight_command.index("--overlay-root") + 1] == str(overlay_root.resolve())


def test_main_passes_release_match_skip_to_downloads_child(monkeypatch, tmp_path) -> None:
    module = load_module()
    preflight, downloads, pwa_static, mobile_ledger, ready_mobile_handoff, participate_iframe_shell = passing_receipts()
    output = tmp_path / "PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json"
    commands: list[list[str]] = []

    def fake_run_child(command, output_path, allow_failure=False):  # noqa: ANN001
        commands.append(command)
        command_text = " ".join(command)
        if "check_public_edge_deploy_preflight.py" in command_text:
            return preflight
        if "verify_downloads_version_marker.py" in command_text:
            return downloads
        if "verify_public_pwa_static_assets.py" in command_text:
            return pwa_static
        if "verify_mobile_pwa_ledger_boundary.py" in command_text:
            return mobile_ledger
        if "verify_ready_mobile_handoff_contract.py" in command_text:
            return ready_mobile_handoff
        if "verify_participate_iframe_shell.py" in command_text:
            return participate_iframe_shell
        raise AssertionError(f"unexpected child command: {command_text}")

    monkeypatch.setattr(module, "run_child", fake_run_child)
    monkeypatch.setattr(module, "probe_role_alias_routes", lambda base_url, timeout_seconds: passing_role_alias_routes())

    exit_code = module.main(
        [
            "--base-url",
            "https://chummer.run",
            "--skip-release-version-match",
            "--output",
            str(output),
        ]
    )

    downloads_command = next(
        command
        for command in commands
        if any("verify_downloads_version_marker.py" in item for item in command)
    )
    assert exit_code == 0
    assert "--skip-release-version-match" in downloads_command


def test_run_child_executes_from_repo_root_and_resolves_script_paths(monkeypatch, tmp_path) -> None:
    module = load_module()
    output = tmp_path / "child.json"
    output.write_text(json.dumps({"contractName": "child", "status": "pass"}), encoding="utf-8")
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        captured["command"] = command
        captured["cwd"] = kwargs.get("cwd")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.run_child(
        [sys.executable, "scripts/check_public_edge_deploy_preflight.py", "--allow-stale-foreign-build-locks"],
        output,
        allow_failure=True,
    )

    assert payload["status"] == "pass"
    assert captured["cwd"] == module.RUN_SERVICES_ROOT
    command = captured["command"]
    assert isinstance(command, list)
    assert command[1] == str(module.RUN_SERVICES_ROOT / "scripts/check_public_edge_deploy_preflight.py")
    assert command[-2:] == ["--output", str(output)]


def test_run_child_returns_synthetic_failure_when_output_is_missing(monkeypatch, tmp_path) -> None:
    module = load_module()
    output = tmp_path / "missing.json"

    def fake_run(command, **kwargs):  # noqa: ANN001
        return types.SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    payload = module.run_child(
        [sys.executable, "scripts/verify_public_pwa_static_assets.py", "--base-url", "http://127.0.0.1:8091"],
        output,
        allow_failure=True,
    )

    assert payload["status"] == "fail"
    assert payload["failures"] == ["child verifier did not write output: missing.json"]
    assert "verify_public_pwa_static_assets.py" in payload["childCommand"]
    assert payload["childExitCode"] == 0


def test_run_playwright_command_executes_from_repo_root(monkeypatch) -> None:
    module = load_module()
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        captured["command"] = command
        captured["cwd"] = kwargs.get("cwd")
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    exit_code, stdout, stderr, timed_out = module.run_playwright_command(
        ["npx", "playwright", "test", "tests/public/mobile-pwa-viewport-smoke.spec.ts"],
        {"BASE_URL": "https://chummer.run"},
        30,
    )

    assert exit_code == 0
    assert stdout == ""
    assert stderr == ""
    assert timed_out is False
    assert captured["cwd"] == module.RUN_SERVICES_ROOT


def test_frontdoor_navigation_probe_uses_playwright_click_for_gm_switch(monkeypatch, tmp_path) -> None:
    module = load_module()
    captured: dict[str, object] = {}

    def fake_run_playwright_command(command, env, timeout_seconds):  # noqa: ANN001
        probe_path = tmp_path / "frontdoor-navigation-proof.cjs"
        captured["command"] = command
        captured["env"] = env
        captured["timeout_seconds"] = timeout_seconds
        captured["script"] = probe_path.read_text(encoding="utf-8")
        return 1, "", "", False

    monkeypatch.setattr(module, "run_playwright_command", fake_run_playwright_command)

    result = module.run_frontdoor_navigation_playwright("http://127.0.0.1:58182", tmp_path, 20.0)

    script = captured["script"]
    assert isinstance(script, str)
    assert "const playButton = openMenu.locator('button.site-open-chummer-menu__button[data-disabled-target=\"/mobile/player\"]'" in script
    assert "const playLink = openMenu.locator('a.site-open-chummer-menu__button[href=\"/mobile/player\"]'" not in script
    assert "gmLink.click({ noWaitAfter: true })" in script
    assert "gmLink.evaluate((element) => element.click())" not in script
    assert "const proofTimeoutMs = 180000;" in script
    assert "page.waitForURL('**/mobile/gm**', { timeout: proofTimeoutMs })" in script
    assert "await page.close({ runBeforeUnload: false }).catch(() => undefined);" in script
    assert "const anchorPage = await browser.newPage({ viewport: mobileViewport });" in script
    assert "const anchorEntryUrl = new URL('/#turn-runsite-card', baseUrl).toString();" in script
    assert "await anchorPage.waitForFunction(() => {" in script
    assert "}, null, { timeout: proofTimeoutMs });" in script
    assert "currentUrl.pathname === '/mobile/player'" in script
    assert "currentUrl.hash === '#turn-runsite-card';" in script
    assert "const legacyHomepageLaneMatch = heroText.match(/Current release:\\s*(Stable\\.|Preview build\\.|Downloads paused\\.)/);" in script
    assert "Homepage still serves legacy release posture copy:" in script
    assert "status: anchorStatus," in script
    assert "failure: anchorFailure," in script
    assert "page_errors: anchorPageErrors," in script
    assert "if (anchorFailure) {" in script
    assert "writeJson('FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json'" in script
    assert result["status"] == "fail"


def test_frontdoor_navigation_can_reuse_existing_artifacts(monkeypatch, tmp_path) -> None:
    module = load_module()
    (tmp_path / "FRONTDOOR_MOBILE_LAUNCH.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.frontdoor_mobile_launch.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.black_ledger_globe_frontdoor.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "entry_url": "https://chummer.run/#turn-runsite-card?",
                "final_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player#turn-runsite-card",
                "final_pathname": "/mobile/player",
                "final_hash": "#turn-runsite-card",
                "pwa_manifest_path": "/manifest.player.webmanifest",
                "pwa_role": "Player",
                "blazor_shell": "interactive-server",
                "session_id_present": True,
                "device_id_present": True,
            }
        ),
        encoding="utf-8",
    )

    def unexpected_run(*args, **kwargs):  # noqa: ANN001
        raise AssertionError("Playwright should not run when reusable frontdoor artifacts already exist.")

    monkeypatch.setattr(module, "run_playwright_command", unexpected_run)

    result = module.run_frontdoor_navigation_playwright(
        "https://chummer.run",
        tmp_path,
        20.0,
        reuse_existing_artifact=True,
    )

    assert result["status"] == "pass"
    assert result["exitCode"] == 0
    assert result["artifactReused"] is True
    assert result["playwrightExecuted"] is False
    assert result["mobileArtifactContract"] == "chummer.frontdoor_mobile_launch.v1"
    assert result["ledgerArtifactContract"] == "chummer.black_ledger_globe_frontdoor.v1"
    assert result["anchorArtifactContract"] == "chummer.frontdoor_mobile_anchor_redirect.v1"
    assert result["mobileArtifactBaseUrlMatchesRequested"] is True
    assert result["ledgerArtifactBaseUrlMatchesRequested"] is True
    assert result["anchorArtifactBaseUrlMatchesRequested"] is True
    assert result["mobileArtifactFresh"] is True
    assert result["ledgerArtifactFresh"] is True
    assert result["anchorArtifactFresh"] is True
    assert result["anchorArtifactCurrentContractSatisfied"] is True


def test_frontdoor_navigation_reuses_canonical_anchor_artifact(monkeypatch, tmp_path) -> None:
    module = load_module()
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    (tmp_path / "FRONTDOOR_MOBILE_LAUNCH.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.frontdoor_mobile_launch.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": generated_at,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.black_ledger_globe_frontdoor.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": generated_at,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                "status": "pass",
                "base_url": "https://chummer.run",
                "generated_at_utc": generated_at,
                "entry_url": "https://chummer.run/#turn-runsite-card",
                "final_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player#turn-runsite-card",
                "final_pathname": "/mobile/player",
                "final_hash": "#turn-runsite-card",
                "pwa_manifest_path": "/manifest.player.webmanifest",
                "pwa_role": "Player",
                "blazor_shell": "interactive-server",
                "session_id_present": True,
                "device_id_present": True,
            }
        ),
        encoding="utf-8",
    )

    captured: dict[str, object] = {}

    def fake_run_playwright_command(command, env, timeout_seconds):  # noqa: ANN001
        captured["command"] = command
        (tmp_path / "FRONTDOOR_MOBILE_LAUNCH.generated.json").write_text(
            json.dumps(
                {
                    "contractName": "chummer.frontdoor_mobile_launch.v1",
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "generated_at_utc": generated_at,
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / "BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json").write_text(
            json.dumps(
                {
                    "contractName": "chummer.black_ledger_globe_frontdoor.v1",
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "generated_at_utc": generated_at,
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / "FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json").write_text(
            json.dumps(
                {
                    "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                    "status": "pass",
                    "base_url": "https://chummer.run",
                    "generated_at_utc": generated_at,
                    "entry_url": "https://chummer.run/#turn-runsite-card?",
                    "final_url": "https://chummer.run/mobile/player?sessionId=session-main&role=Player#turn-runsite-card",
                    "final_pathname": "/mobile/player",
                    "final_hash": "#turn-runsite-card",
                    "pwa_manifest_path": "/manifest.player.webmanifest",
                    "pwa_role": "Player",
                    "blazor_shell": "interactive-server",
                    "session_id_present": True,
                    "device_id_present": True,
                }
            ),
            encoding="utf-8",
        )
        return 0, "", "", False

    monkeypatch.setattr(module, "run_playwright_command", fake_run_playwright_command)

    result = module.run_frontdoor_navigation_playwright(
        "https://chummer.run",
        tmp_path,
        20.0,
        reuse_existing_artifact=True,
    )

    assert "command" not in captured
    assert result["status"] == "pass"
    assert result["artifactReused"] is True
    assert result["playwrightExecuted"] is False
    assert result["anchorArtifact"]["entry_url"] == "https://chummer.run/#turn-runsite-card"
    assert result["anchorArtifactCurrentContractSatisfied"] is True


def test_frontdoor_navigation_clears_stale_artifacts_and_surfaces_failed_anchor_artifact(monkeypatch, tmp_path) -> None:
    module = load_module()
    (tmp_path / "FRONTDOOR_MOBILE_LAUNCH.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.frontdoor_mobile_launch.v1",
                "status": "pass",
                "base_url": "https://stale.example",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.black_ledger_globe_frontdoor.v1",
                "status": "pass",
                "base_url": "https://stale.example",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json").write_text(
        json.dumps(
            {
                "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                "status": "pass",
                "base_url": "https://stale.example",
            }
        ),
        encoding="utf-8",
    )

    def fake_run_playwright_command(command, env, timeout_seconds):  # noqa: ANN001
        (tmp_path / "FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json").write_text(
            json.dumps(
                {
                    "contractName": "chummer.frontdoor_mobile_anchor_redirect.v1",
                    "status": "fail",
                    "base_url": "https://chummer.run",
                    "entry_url": "https://chummer.run/#turn-runsite-card?",
                    "final_url": "https://chummer.run/#turn-runsite-card",
                    "final_pathname": "/",
                    "final_hash": "#turn-runsite-card",
                    "pwa_manifest_path": "/manifest.webmanifest",
                    "pwa_role": None,
                    "blazor_shell": None,
                    "session_id_present": False,
                    "device_id_present": False,
                    "failure": "Homepage anchor redirect did not land on /mobile/player",
                }
            ),
            encoding="utf-8",
        )
        return 1, "", "anchor failed\n", False

    monkeypatch.setattr(module, "run_playwright_command", fake_run_playwright_command)

    result = module.run_frontdoor_navigation_playwright("https://chummer.run", tmp_path, 20.0)

    assert result["status"] == "fail"
    assert result["mobileArtifactContract"] == ""
    assert result["ledgerArtifactContract"] == ""
    assert result["anchorArtifactContract"] == "chummer.frontdoor_mobile_anchor_redirect.v1"
    assert result["anchorArtifactBaseUrlMatchesRequested"] is True
    assert result["anchorArtifact"]["status"] == "fail"
    assert result["anchorArtifact"]["final_pathname"] == "/"
    assert result["anchorArtifact"]["final_hash"] == "#turn-runsite-card"


def test_mobile_rybbit_smoke_asset_exists_for_local_frontdoor_probe() -> None:
    asset_path = REPO_ROOT / "Chummer.Run.Api" / "wwwroot" / "mobile-rybbit-smoke.js"
    script = asset_path.read_text(encoding="utf-8")

    assert asset_path.is_file()
    assert "window.rybbit" in script
    assert "track: function () {}" in script
    assert "event: function () {}" in script
