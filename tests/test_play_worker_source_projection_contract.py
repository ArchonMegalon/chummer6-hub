from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVED_WORKER = REPO_ROOT / "Chummer.Run.Api" / "wwwroot" / "service-worker.js"


def _play_source_worker() -> Path:
    configured = os.environ.get("CHUMMER_PLAY_SOURCE_ROOT", "").strip()
    candidates = []
    if configured:
        candidates.append(Path(configured))
    candidates.append(REPO_ROOT.parent / "chummer-play")

    for root in candidates:
        worker = root / "src" / "Chummer.Play.Web" / "wwwroot" / "service-worker.js"
        if worker.is_file():
            return worker

    pytest.skip(
        "The actual chummer-play source checkout is not available; set CHUMMER_PLAY_SOURCE_ROOT "
        "to enable the source-versus-served worker contract check."
    )


def _constant(script: str, name: str) -> str:
    match = re.search(rf'^const {re.escape(name)} = "([^"]+)";', script, flags=re.MULTILINE)
    assert match is not None, f"missing {name}"
    return match.group(1)


def _run_critical_asset_fetch(worker: Path, failures_before_success: int) -> dict[str, object]:
    probe = r"""
const fs = require("fs");
const failuresBeforeSuccess = Number(process.argv[2]);
let attempts = 0;
global.self = {
  registration: { scope: "https://chummer.run/mobile/" },
  location: { origin: "https://chummer.run" },
  addEventListener: () => {}
};
global.Request = class Request {
  constructor(path, options = {}) {
    this.url = new URL(path, self.location.origin).toString();
    this.method = options.method || "GET";
    this.mode = "cors";
  }
};
global.fetch = async (request) => {
  attempts += 1;
  if (attempts <= failuresBeforeSuccess) {
    throw new TypeError("transient asset fetch failure");
  }
  const response = new Response("ok", {
    status: 200,
    headers: {
      "Content-Type": "application/javascript",
      "Cache-Control": "public, max-age=300, must-revalidate"
    }
  });
  Object.defineProperty(response, "url", { value: request.url });
  return response;
};
global.caches = {};
global.setTimeout = (callback) => { callback(); return 1; };
eval(fs.readFileSync(process.argv[1], "utf8"));
fetchCriticalShellAsset("/mobile-install-shell.js")
  .then(() => process.stdout.write(JSON.stringify({ attempts, recovered: true })))
  .catch(() => process.stdout.write(JSON.stringify({ attempts, recovered: false })));
"""
    result = subprocess.run(
        ["node", "-e", probe, str(worker), str(failures_before_success)],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _assert_shared_privacy_semantics(script: str, expected_cache_version: str) -> None:
    assert f'const CACHE_VERSION = "{expected_cache_version}";' in script
    assert '`${CACHE_FAMILY}-static-${CACHE_CONTRACT}-${CACHE_VERSION}`' in script
    assert '`${CACHE_FAMILY}-media-${CACHE_CONTRACT}-${CACHE_VERSION}`' in script
    assert '`${CACHE_FAMILY}-media-meta-${CACHE_CONTRACT}-${CACHE_VERSION}`' in script
    assert '`${CACHE_FAMILY}-static-`' in script
    assert '`${CACHE_FAMILY}-media-`' in script
    assert '`${CACHE_FAMILY}-media-meta-`' in script
    assert "isManagedWorkerCache(key)" in script
    assert "isLegacyPrivateCache(key)" in script
    assert "PUBLIC_CACHEABLE_ASSETS = new Map" in script
    assert "isExpectedPublicAssetResponse" in script
    assert "CRITICAL_SHELL_ASSETS" in script
    assert "const CRITICAL_SHELL_FETCH_ATTEMPTS = 3;" in script
    assert "const CRITICAL_SHELL_FETCH_RETRY_DELAYS_MS = [250, 750];" in script
    assert "CRITICAL_SHELL_ASSETS.map(fetchCriticalShellAsset)" in script
    assert "attempt < CRITICAL_SHELL_FETCH_ATTEMPTS" in script
    assert "attempt + 1 < CRITICAL_SHELL_FETCH_ATTEMPTS" in script
    assert "Promise.allSettled" not in script
    assert "caches.match(" not in script
    assert "caches.open(SHELL_CACHE).then((cache) => cache.match(request))" in script

    fetch_handler = script.split('self.addEventListener("fetch"', 1)[1]
    build_bypass = fetch_handler.index("if (isBuildOwnedRequest(url))")
    api_boundary = fetch_handler.index('if (url.pathname.startsWith("/api/play/"))')
    navigation_boundary = fetch_handler.index('if (request.mode === "navigate")')
    assert build_bypass < api_boundary < navigation_boundary
    assert 'url.pathname === "/blazor" || url.pathname.startsWith("/blazor/")' in script

    navigation_handler = script.split("async function handleNavigationRequest", 1)[1].split(
        "function offlineNavigationResponse", 1
    )[0]
    assert "fetch(request)" in navigation_handler
    assert "offlineNavigationResponse(url.pathname)" in navigation_handler
    assert "caches.match" not in navigation_handler
    assert "cache.put" not in navigation_handler

    runtime_policy = script.split("function isPublicRuntimeCacheableRequest", 1)[1].split(
        "function shouldCacheResponse", 1
    )[0]
    assert "if (url.search)" in runtime_policy
    assert 'if (request.mode === "navigate") return false;' in runtime_policy
    cache_control_is_normalized = (
        'const cacheControl = String(response.headers.get("Cache-Control") || "").toLowerCase();' in script
    )
    assert 'cacheControl.toLowerCase().includes("private")' in script or (
        cache_control_is_normalized and 'cacheControl.includes("private")' in script
    )
    assert 'cacheControl.toLowerCase().includes("no-store")' in script or (
        cache_control_is_normalized and 'cacheControl.includes("no-store")' in script
    )
    assert "play_api_network_unavailable" in script
    assert "status: 503" in script
    assert (
        '"cache-control": "no-store"' in script
        or '"cache-control": "private, no-store"' in script
    )
    assert '"content-security-policy": "default-src \'none\'' in script
    assert '"x-content-type-options": "nosniff"' in script


def test_actual_play_source_and_served_projection_use_distinct_cache_contracts_with_shared_privacy_semantics() -> None:
    source = _play_source_worker().read_text(encoding="utf-8")
    served = SERVED_WORKER.read_text(encoding="utf-8")

    _assert_shared_privacy_semantics(source, "v21")
    _assert_shared_privacy_semantics(served, "v19")
    assert served.count('"cache-control": "private, no-store"') == 3

    source_contract = _constant(source, "CACHE_CONTRACT")
    served_contract = _constant(served, "CACHE_CONTRACT")
    source_version = _constant(source, "CACHE_VERSION")
    served_version = _constant(served, "CACHE_VERSION")
    assert source_contract == "play-source-v2"
    assert served_contract == "run-api-projection-v2"
    assert source_contract != served_contract
    assert source_version == "v21"
    assert served_version == "v19"

    source_shell_name = f"chummer-public-root-static-{source_contract}-{source_version}"
    served_shell_name = f"chummer-public-root-static-{served_contract}-{served_version}"
    assert source_shell_name != served_shell_name

    # The source host owns manifest.webmanifest; the runsite mirror intentionally
    # publishes the byte-identical Play base manifest under a non-conflicting name.
    assert '["/manifest.webmanifest",' in source
    assert '"/manifest.webmanifest",' in source
    assert '["/manifest.play.webmanifest",' in served
    assert '"/manifest.play.webmanifest",' in served
    assert '["/manifest.webmanifest",' not in served
    assert '["/mobile-turn-companion.js",' not in served


def test_source_and_projection_retry_transient_critical_asset_fetches_with_a_closed_budget() -> None:
    source = _play_source_worker()

    for worker in (source, SERVED_WORKER):
        assert _run_critical_asset_fetch(worker, failures_before_success=2) == {
            "attempts": 3,
            "recovered": True,
        }
        assert _run_critical_asset_fetch(worker, failures_before_success=5) == {
            "attempts": 3,
            "recovered": False,
        }
