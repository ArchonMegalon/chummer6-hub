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
