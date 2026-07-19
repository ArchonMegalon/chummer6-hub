#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import shutil
import stat
import tempfile
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    # Keep isolated-mode authority independent of PYTHONPATH while allowing audited siblings.
    sys.path.insert(0, str(SCRIPTS))

try:
    from scripts.publish_public_edge_portal_overlay import (
        FRONTDOOR_PLAYWRIGHT_PROOF_CLOSURE_ALGORITHM,
        FRONTDOOR_PLAYWRIGHT_PROOF_CLOSURE_CONTRACT_NAME,
        FRONTDOOR_PLAYWRIGHT_PROOF_CLOSURE_RELATIVE_ROOT,
        full_deployment_digest,
        source_fingerprint,
        staged_payload_fingerprint,
        validate_frontdoor_playwright_proof_closure,
        validate_payload_modes_against_receipt,
    )
except ModuleNotFoundError:  # Direct `python3 scripts/...` execution.
    from publish_public_edge_portal_overlay import (
        FRONTDOOR_PLAYWRIGHT_PROOF_CLOSURE_ALGORITHM,
        FRONTDOOR_PLAYWRIGHT_PROOF_CLOSURE_CONTRACT_NAME,
        FRONTDOOR_PLAYWRIGHT_PROOF_CLOSURE_RELATIVE_ROOT,
        full_deployment_digest,
        source_fingerprint,
        staged_payload_fingerprint,
        validate_frontdoor_playwright_proof_closure,
        validate_payload_modes_against_receipt,
    )

try:
    from scripts.strict_json_contract import StrictJsonContractError, strict_json_object
except ModuleNotFoundError:  # Direct `python3 scripts/...` execution.
    from strict_json_contract import StrictJsonContractError, strict_json_object


POSTDEPLOY_VERIFIER_LOADED_SHA256 = hashlib.sha256(
    Path(__file__).read_bytes()
).hexdigest()

import verify_participate_iframe_shell  # noqa: E402
import verify_mobile_pwa_service_worker_boundary  # noqa: E402


EXPECTED_PLAYTIME_TOOLS = {
    "inventory",
    "health",
    "ammo",
    "modifiers",
    "quick_rolls",
    "living_world",
}
EXPECTED_LEDGER_OPT_IN_KEYS = {
    "black_ledger_heat",
    "followed_world_updates",
    "session_continuity",
}
EXPECTED_READY_ROLES = {"player", "gm", "organizer"}
EXPECTED_MOBILE_ROUTES = {
    "/mobile": ('data-blazor-shell="interactive-server"', 'data-role="Player"', "manifest.player.webmanifest"),
    "/mobile/player": ('data-blazor-shell="interactive-server"', 'data-role="Player"', "manifest.player.webmanifest"),
    "/mobile/gm": ('data-blazor-shell="interactive-server"', 'data-role="GameMaster"', "manifest.gm.webmanifest"),
    "/mobile/observer": ('data-blazor-shell="interactive-server"', 'data-role="Observer"', "manifest.webmanifest"),
    "/play": ("Player entry",),
    "/play/continuity": ("NEXUS-PAN continuity",),
}
EXPECTED_ASSETS = [
    "/pwa-icon.svg",
    "/pwa-maskable.svg",
    "/pwa-screenshot-mobile.svg",
    "/pwa-screenshot-wide.svg",
    "/apple-touch-icon.png",
    "/favicon.ico",
    "/favicon.svg",
]
EXPECTED_MANIFESTS = {
    "/manifest.json": "/mobile",
    "/manifest.webmanifest": "/mobile",
    "/site.webmanifest": "/mobile",
    "/manifest.player.webmanifest": "/mobile/player",
    "/manifest.gm.webmanifest": "/mobile/gm",
}
PLAYWRIGHT_REQUIREMENTS = {
    "downloadsStatus": {
        "spec": "tests/public/downloads-status.spec.ts",
        "artifact": "DOWNLOADS_STATUS_E2E.generated.json",
    },
    "mobilePwaViewport": {
        "spec": "tests/public/mobile-pwa-viewport-smoke.spec.ts",
        "artifact": "MOBILE_PWA_VIEWPORT_SMOKE.generated.json",
    },
    "frontdoorNavigation": {
        "spec": "tests/public/frontdoor-mobile-launch.spec.ts",
        "artifact": "FRONTDOOR_MOBILE_LAUNCH.generated.json",
    },
}
ANSI_CONTROL_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
EXPECTED_FLAGSHIP_HORIZONS = {
    "near_term_stabilization": {
        "title": "Near-term stabilization",
        "requiredReceipts": [
            "downloads",
            "navigation",
            "pwaStatic",
            "readyMobileHandoff",
            "mobilePwaServiceWorkerBoundary",
            "participateIframeShell",
            "portalRuntimeImage",
        ],
    },
    "mid_term_pwa_session_utility": {
        "title": "Mid-term PWA/session utility",
        "requiredReceipts": [
            "pwaStatic",
            "readyMobileHandoff",
            "browserPlaywright",
        ],
        "requiredRoutes": [
            "/mobile",
            "/mobile/player",
            "/mobile/gm",
            "/mobile/observer",
            "/play/continuity",
        ],
        "requiredTools": sorted(EXPECTED_PLAYTIME_TOOLS - {"living_world"}),
    },
    "long_term_living_world_expansion": {
        "title": "Long-term living-world expansion",
        "requiredReceipts": [
            "readyMobileHandoff",
            "mobileLedger",
            "mobilePwaServiceWorkerBoundary",
        ],
        "requiredTools": ["living_world"],
        "requiredLedgerStatus": "opt_in_required",
    },
}
DEFAULT_PORTAL_CONTAINER = "chummer6-hub-chummer-portal-1"
DEFAULT_PORTAL_IMAGE_TAG = "chummer-run-api:local"


@dataclass(frozen=True)
class FetchResult:
    path: str
    status_code: int
    headers: dict[str, str]
    body: str
    final_url: str

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.body.encode("utf-8")).hexdigest()


def require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def clean_process_text(value: Any) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value or "")
    return ANSI_CONTROL_RE.sub("", text)


def tail_lines(value: Any, max_lines: int = 80) -> str:
    lines = []
    skip_next_trace_hint = False
    for line in clean_process_text(value).splitlines():
        if "Warning: The 'NO_COLOR' env is ignored due to the 'FORCE_COLOR' env being set." in line:
            skip_next_trace_hint = True
            continue
        if skip_next_trace_hint and line.startswith("(Use `node --trace-warnings"):
            skip_next_trace_hint = False
            continue
        skip_next_trace_hint = False
        lines.append(line)
    return "\n".join(lines[-max_lines:])


def normalize_token(value: Any) -> str:
    return str(value or "").strip().casefold()


def resolve_playwright_package_spec() -> str:
    override = str(os.environ.get("CHUMMER_PLAYWRIGHT_PACKAGE_SPEC") or "").strip()
    if override:
        return override

    package_lock_path = ROOT / "package-lock.json"
    if package_lock_path.is_file():
        try:
            package_lock = json.loads(package_lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            package_lock = {}
        packages = package_lock.get("packages")
        if isinstance(packages, dict):
            playwright_package = packages.get("node_modules/playwright")
            if isinstance(playwright_package, dict):
                version = str(playwright_package.get("version") or "").strip()
                if version:
                    return f"playwright@{version}"

    package_json_path = ROOT / "package.json"
    if package_json_path.is_file():
        try:
            package_json = json.loads(package_json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            package_json = {}
        for field in ("dependencies", "devDependencies"):
            dependencies = package_json.get(field)
            if not isinstance(dependencies, dict):
                continue
            version_spec = str(dependencies.get("playwright") or "").strip()
            if version_spec:
                return f"playwright@{version_spec}"

    return "playwright"


def resolve_playwright_node_modules_root() -> Path | None:
    override_root = str(os.environ.get("CHUMMER_PLAYWRIGHT_NODE_MODULES_ROOT") or "").strip()
    candidates = []
    if override_root:
        candidates.append(Path(override_root).expanduser())
    candidates.extend(
        [
            ROOT / "node_modules",
            ROOT.parent / "chummer.run-services" / "node_modules",
            Path("/docker/chummercomplete/chummer.run-services/node_modules"),
        ]
    )

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if (candidate / ".bin" / "playwright").is_file():
            return candidate
    return None


def resolve_playwright_command() -> list[str]:
    override_bin = str(os.environ.get("CHUMMER_PLAYWRIGHT_BIN") or "").strip()
    if override_bin:
        return [override_bin]

    node_modules_root = resolve_playwright_node_modules_root()
    if node_modules_root is not None:
        return [str(node_modules_root / ".bin" / "playwright")]

    return ["npx", "--yes", resolve_playwright_package_spec()]


def _assert_no_symlink_path(path: Path, *, label: str) -> None:
    normalized = Path(os.path.abspath(os.fspath(path.expanduser())))
    current = Path(normalized.anchor)
    for component in normalized.parts[1:]:
        current /= component
        try:
            identity = current.lstat()
        except OSError as exc:
            raise RuntimeError(f"{label} is unavailable") from exc
        if stat.S_ISLNK(identity.st_mode):
            raise RuntimeError(f"{label} contains a symlink component")


def _read_runtime_regular_file(path: Path, *, label: str, max_bytes: int) -> bytes:
    _assert_no_symlink_path(path, label=label)
    identity = path.lstat()
    if (
        not stat.S_ISREG(identity.st_mode)
        or identity.st_nlink != 1
        or identity.st_size <= 0
        or identity.st_size > max_bytes
    ):
        raise RuntimeError(f"{label} is not one bounded regular file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(64 * 1024, max_bytes - total + 1))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise RuntimeError(f"{label} exceeds its size limit")
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    expected_identity = (
        identity.st_dev,
        identity.st_ino,
        identity.st_size,
        identity.st_mtime_ns,
        identity.st_ctime_ns,
        identity.st_nlink,
    )
    if expected_identity != (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
        before.st_nlink,
    ) or expected_identity != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        after.st_nlink,
    ) or total != identity.st_size:
        raise RuntimeError(f"{label} changed while it was read")
    return b"".join(chunks)


def resolve_pinned_playwright_node_modules_root() -> Path | None:
    """Resolve only repository-controlled dependency roots for the proof lane."""

    candidates = (
        ROOT / "node_modules",
        ROOT.parent / "chummer.run-services" / "node_modules",
        Path("/docker/chummercomplete/chummer.run-services/node_modules"),
    )
    seen: set[str] = set()
    for candidate in candidates:
        normalized = Path(os.path.abspath(os.fspath(candidate)))
        key = str(normalized)
        if key in seen:
            continue
        seen.add(key)
        if (
            (normalized / "playwright" / "package.json").is_file()
            and (normalized / "playwright" / "cli.js").is_file()
        ):
            return normalized
    return None


def resolve_pinned_playwright_runtime(expected_version: str) -> dict[str, Any]:
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?", expected_version) is None:
        raise RuntimeError("sealed Playwright closure has no exact package version")
    node_modules_root = resolve_pinned_playwright_node_modules_root()
    if node_modules_root is None:
        raise RuntimeError("validated local Playwright node_modules root is unavailable")
    node_modules_root = Path(os.path.abspath(os.fspath(node_modules_root.expanduser())))
    _assert_no_symlink_path(node_modules_root, label="Playwright node_modules root")
    if not stat.S_ISDIR(node_modules_root.lstat().st_mode):
        raise RuntimeError("Playwright node_modules root is not a directory")
    package_root = node_modules_root / "playwright"
    package_json_path = package_root / "package.json"
    cli_path = package_root / "cli.js"
    package_json_bytes = _read_runtime_regular_file(
        package_json_path,
        label="installed Playwright package metadata",
        max_bytes=256 * 1024,
    )
    cli_bytes = _read_runtime_regular_file(
        cli_path,
        label="installed Playwright CLI",
        max_bytes=4 * 1024 * 1024,
    )
    try:
        package_json = strict_json_object(
            package_json_bytes,
            label="installed Playwright package metadata",
        )
    except StrictJsonContractError as exc:
        raise RuntimeError("installed Playwright package metadata is invalid") from exc
    installed_version = str(package_json.get("version") or "").strip()
    if installed_version != expected_version:
        raise RuntimeError(
            "installed Playwright package version does not match the sealed package lock"
        )
    node_binary = next(
        (
            str(candidate)
            for candidate in (Path("/usr/bin/node"), Path("/usr/local/bin/node"))
            if candidate.is_file()
        ),
        None,
    ) or shutil.which("node")
    if not node_binary:
        raise RuntimeError("Node.js runtime is unavailable for the sealed Playwright proof")
    node_path = Path(node_binary)
    _assert_no_symlink_path(node_path, label="Node.js runtime")
    return {
        "status": "pass",
        "resolutionMode": "validated_local_node_modules_exact_lock_version",
        "nodeModulesRoot": str(node_modules_root),
        "nodeBinary": str(node_path),
        "playwrightCliPath": str(cli_path),
        "playwrightPackageVersion": installed_version,
        "packageJsonSha256": hashlib.sha256(package_json_bytes).hexdigest(),
        "playwrightCliSha256": hashlib.sha256(cli_bytes).hexdigest(),
        "commandPrefix": [str(node_path), str(cli_path)],
    }


def expected_release_posture(expected_release_channel: str) -> dict[str, str]:
    normalized = normalize_token(expected_release_channel) or "public_stable"
    if normalized in {"preview", "nightly", "promoted_preview"}:
        return {
            "channel": "preview",
            "rollout": "promoted_preview",
            "supportability": "preview_supported",
        }
    return {
        "channel": "public_stable",
        "rollout": "public_stable",
        "supportability": "gold_supported",
    }


def fetch(base_url: str, path: str, timeout_seconds: float) -> FetchResult:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    request = Request(url, headers={"User-Agent": "ChummerPublicEdgePostdeployGate/1.0"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="replace")
            headers = {key.lower(): value for key, value in response.headers.items()}
            return FetchResult(path, response.status, headers, body, response.geturl())
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        headers = {key.lower(): value for key, value in error.headers.items()}
        return FetchResult(path, error.code, headers, body, error.geturl())
    except URLError as error:
        raise RuntimeError(f"{url}: {error}") from error


def parse_json(result: FetchResult, failures: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(result.body)
    except json.JSONDecodeError as error:
        failures.append(f"{result.path} returned invalid JSON: {error}")
        return {}
    return value if isinstance(value, dict) else {}


def normalize_manifest_asset_src(src: Any) -> str:
    value = str(src or "").strip().replace("\\", "/")
    if not value:
        return ""

    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return ""

    path = parsed.path.strip()
    if not path:
        return ""

    normalized_path = posixpath.normpath(path if path.startswith("/") else f"/{path}")
    if normalized_path == "/.":
        return ""
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    if parsed.query:
        return f"{normalized_path}?{parsed.query}"
    return normalized_path


def manifest_asset_paths(payload: dict[str, Any]) -> list[str]:
    paths: set[str] = set()

    def collect_icon_sources(rows: Any) -> None:
        if not isinstance(rows, list):
            return
        for item in rows:
            if not isinstance(item, dict):
                continue
            path = normalize_manifest_asset_src(item.get("src"))
            if path:
                paths.add(path)

    collect_icon_sources(payload.get("icons"))
    collect_icon_sources(payload.get("screenshots"))
    shortcuts = payload.get("shortcuts") if isinstance(payload.get("shortcuts"), list) else []
    for shortcut in shortcuts:
        if isinstance(shortcut, dict):
            collect_icon_sources(shortcut.get("icons"))

    return sorted(paths)


def extract_quoted_values(text: str, pattern: str) -> set[str]:
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        return set()
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def service_worker_declared_fetchable_paths(service_worker: dict[str, Any]) -> list[str]:
    raw_paths: list[Any] = []
    for key in ("precache_urls", "shell_assets"):
        values = service_worker.get(key)
        if isinstance(values, list):
            raw_paths.extend(values)

    non_cacheable_paths: set[str] = set()
    for value in service_worker.get("non_cacheable_paths", []):
        normalized_path = normalize_manifest_asset_src(value)
        if normalized_path:
            non_cacheable_paths.add(normalized_path)
    non_cacheable_bases = {path.split("?", 1)[0] for path in non_cacheable_paths}

    paths: set[str] = set()
    for raw_path in raw_paths:
        path = normalize_manifest_asset_src(raw_path)
        if not path:
            continue
        if path in non_cacheable_paths or path.split("?", 1)[0] in non_cacheable_bases:
            continue
        paths.add(path.split("?", 1)[0])
    return sorted(paths)


def inspect_service_worker(body: str, failures: list[str]) -> dict[str, Any]:
    cache_name_match = re.search(r'const CACHE_NAME = "([^"]+)";', body)
    cache_version_match = re.search(r'const CACHE_VERSION = "([^"]+)";', body)
    precache_urls = extract_quoted_values(body, r"const PRECACHE_URLS = \[(.*?)\];")
    shell_assets = extract_quoted_values(body, r"const SHELL_ASSETS = \[(.*?)\];")
    non_cacheable_paths = extract_quoted_values(body, r"const NON_CACHEABLE_PATHS = new Set\(\[(.*?)\]\);")
    worker_kind = "play" if cache_version_match and "SHELL_ASSETS" in body else "portal"

    if worker_kind == "play":
        for listener in ['"install"', '"activate"', '"fetch"']:
            require(f"self.addEventListener({listener}" in body, failures, f"service worker missing {listener} listener")
        for path in [
            "/mobile",
            "/mobile/player",
            "/mobile/gm",
            "/mobile/observer",
            "/_framework/blazor.web.js",
            "/mobile.css",
            "/mobile-turn-companion.js",
            "/manifest.webmanifest",
            "/manifest.player.webmanifest",
            "/manifest.gm.webmanifest",
        ]:
            require(path in shell_assets, failures, f"service worker missing play shell asset {path}")
        require("/mobile/pwa/ledger.json" in non_cacheable_paths, failures, "service worker must keep mobile ledger stream non-cacheable")
        require("/mobile/pwa/ledger.json" not in shell_assets, failures, "service worker must not precache mobile ledger stream")
        require('url.pathname.startsWith("/api/play/")' in body, failures, "service worker must keep private play API network-only")
        require("play_public_route_network_unavailable" in body, failures, "service worker missing typed non-cacheable route offline failure")
    else:
        require(cache_name_match and cache_name_match.group(1) == "chummer-public-v4", failures, "service worker cache name is not chummer-public-v4")
        for required_path in ["/mobile/player", "/mobile/gm", "/mobile/observer", "/ready/handoff/mobile.json"]:
            require(required_path in body, failures, f"service worker missing {required_path}")
        require('"/mobile/pwa/ledger.json"' in body and "NON_CACHEABLE_PATHS" in body, failures, "service worker does not mark mobile ledger stream non-cacheable")

    return {
        "worker_kind": worker_kind,
        "cache_name": cache_name_match.group(1) if cache_name_match else "",
        "cache_version": cache_version_match.group(1) if cache_version_match else "",
        "precache_urls": sorted(precache_urls),
        "shell_assets": sorted(shell_assets),
        "non_cacheable_paths": sorted(non_cacheable_paths),
        "ledger_stream_non_cacheable": "/mobile/pwa/ledger.json" in non_cacheable_paths,
        "ledger_stream_precached": "/mobile/pwa/ledger.json" in (shell_assets if worker_kind == "play" else precache_urls),
        "play_shell_asset_count": len(shell_assets),
    }


def extract_downloads_version_marker(html: str) -> str:
    match = re.search(r"<[^>]+data-downloads-release-version[^>]*>\s*(Version\s+[^<\s]+)", html, re.IGNORECASE)
    return match.group(1).strip() if match else ""


def verify_downloads(base_url: str, timeout_seconds: float, expected_release_channel: str = "public_stable") -> dict[str, Any]:
    failures: list[str] = []
    expected_posture = expected_release_posture(expected_release_channel)
    downloads = fetch(base_url, "/downloads", timeout_seconds)
    status = fetch(base_url, "/status", timeout_seconds)
    release = fetch(base_url, "/downloads/RELEASE_CHANNEL.generated.json", timeout_seconds)
    compatibility = fetch(base_url, "/downloads/releases.json", timeout_seconds)
    release_payload = parse_json(release, failures) if release.status_code == 200 else {}
    compatibility_payload = parse_json(compatibility, failures) if compatibility.status_code == 200 else {}

    downloads_version = extract_downloads_version_marker(downloads.body)
    status_version = extract_downloads_version_marker(status.body)
    release_version = str(release_payload.get("releaseVersion") or release_payload.get("version") or "")
    release_status = str(release_payload.get("status") or "")
    release_channel = str(release_payload.get("channel") or release_payload.get("channelId") or "")
    release_rollout = str(release_payload.get("rolloutState") or "")
    release_supportability = str(release_payload.get("supportabilityState") or "")
    compatibility_version = str(compatibility_payload.get("releaseVersion") or compatibility_payload.get("version") or "")
    compatibility_status = str(compatibility_payload.get("status") or "")
    compatibility_channel = str(compatibility_payload.get("channel") or compatibility_payload.get("channelId") or "")
    compatibility_rollout = str(compatibility_payload.get("rolloutState") or "")
    compatibility_supportability = str(compatibility_payload.get("supportabilityState") or "")
    compatibility_download_count = len(compatibility_payload.get("downloads") or [])
    release_guarded_preview = (
        expected_posture["channel"] == "preview"
        and normalize_token(release_supportability) == "review_required"
        and normalize_token(release_rollout) in {"coverage_incomplete", "desktop_polish_needed", "readiness_review_required"}
    )
    compatibility_guarded_preview = (
        expected_posture["channel"] == "preview"
        and normalize_token(compatibility_supportability) == "review_required"
        and normalize_token(compatibility_rollout) in {"desktop_polish_needed", "readiness_review_required"}
    )

    require(downloads.status_code == 200, failures, f"/downloads expected 200, got {downloads.status_code}")
    require(status.status_code == 200, failures, f"/status expected 200, got {status.status_code}")
    require(release.status_code == 200, failures, f"/downloads/RELEASE_CHANNEL.generated.json expected 200, got {release.status_code}")
    require(compatibility.status_code == 200, failures, f"/downloads/releases.json expected 200, got {compatibility.status_code}")
    require(bool(downloads_version), failures, "/downloads missing data-downloads-release-version marker")
    require(bool(status_version), failures, "/status missing data-downloads-release-version marker")
    if release_version:
        require(downloads_version.endswith(release_version), failures, "/downloads version marker does not match release channel version")
        require(status_version.endswith(release_version), failures, "/status version marker does not match release channel version")
        require(compatibility_version == release_version, failures, "/downloads/releases.json version does not match release channel version")
    require(release_status == "published", failures, f"release status expected published, got {release_status or '<empty>'}")
    require(compatibility_status == "published", failures, f"compatibility manifest status expected published, got {compatibility_status or '<empty>'}")
    require(compatibility_download_count > 0, failures, "compatibility manifest exposes no downloads")
    require(
        normalize_token(release_channel) == expected_posture["channel"],
        failures,
        f"release channel expected {expected_posture['channel']}, got {release_channel or '<empty>'}",
    )
    require(
        normalize_token(compatibility_channel) == expected_posture["channel"],
        failures,
        f"compatibility manifest channel expected {expected_posture['channel']}, got {compatibility_channel or '<empty>'}",
    )
    if not release_guarded_preview:
        require(
            normalize_token(release_rollout) == expected_posture["rollout"],
            failures,
            f"release rollout expected {expected_posture['rollout']}, got {release_rollout or '<empty>'}",
        )
        require(
            normalize_token(release_supportability) == expected_posture["supportability"],
            failures,
            f"release supportability expected {expected_posture['supportability']}, got {release_supportability or '<empty>'}",
        )
    if not compatibility_guarded_preview:
        require(
            normalize_token(compatibility_rollout) == expected_posture["rollout"],
            failures,
            f"compatibility manifest rollout expected {expected_posture['rollout']}, got {compatibility_rollout or '<empty>'}",
        )
        require(
            normalize_token(compatibility_supportability) == expected_posture["supportability"],
            failures,
            f"compatibility manifest supportability expected {expected_posture['supportability']}, got {compatibility_supportability or '<empty>'}",
        )

    return {
        "contractName": "chummer.downloads_version_marker.v1",
        "status": "pass" if not failures else "fail",
        "downloads_status": downloads.status_code,
        "status_status": status.status_code,
        "release_manifest_status": release.status_code,
        "compatibility_manifest_status": compatibility.status_code,
        "visible_version": downloads_version,
        "status_redirect_version": status_version,
        "release_version": release_version,
        "compatibility_manifest_version": compatibility_version,
        "release_channel": release_channel,
        "compatibility_manifest_channel": compatibility_channel,
        "expected_release_channel": expected_posture["channel"],
        "expected_release_rollout_state": expected_posture["rollout"],
        "expected_release_supportability_state": expected_posture["supportability"],
        "release_rollout_state": release_rollout,
        "release_status": release_status,
        "release_supportability_state": release_supportability,
        "release_manifest_guarded_preview": release_guarded_preview,
        "compatibility_manifest_rollout_state": compatibility_rollout,
        "compatibility_manifest_supportability_state": compatibility_supportability,
        "compatibility_manifest_download_count": compatibility_download_count,
        "compatibility_manifest_guarded_preview": compatibility_guarded_preview,
        "failures": failures,
    }


def verify_navigation(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    failures: list[str] = []
    home = fetch(base_url, "/", timeout_seconds)
    require(home.status_code == 200, failures, f"/ expected 200, got {home.status_code}")
    require("site-open-chummer-menu" in home.body, failures, "homepage missing Open Chummer dropdown")
    require('href="/mobile/player"' in home.body, failures, "homepage Open Chummer menu missing public Play link")
    require('data-analytics-label="Build">Build</button>' in home.body or ">Build</button>" in home.body, failures, "homepage Build action is not gated as a disabled button")
    require('href="/build"' not in home.body, failures, "homepage leaks public Build link before sign-in")
    return {
        "contractName": "chummer.public_navigation_open_chummer.v1",
        "status": "pass" if not failures else "fail",
        "status_code": home.status_code,
        "sha256": home.sha256,
        "failures": failures,
    }


def verify_pwa_static(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    failures: list[str] = []
    route_results: list[dict[str, Any]] = []
    for path, expected_terms in EXPECTED_MOBILE_ROUTES.items():
        result = fetch(base_url, path, timeout_seconds)
        has_expected = all(term in result.body for term in expected_terms)
        require(result.status_code == 200, failures, f"{path} expected 200, got {result.status_code}")
        require(has_expected, failures, f"{path} missing expected mobile shell text")
        route_results.append(
            {
                "path": path,
                "status_code": result.status_code,
                "content_type": result.content_type,
                "sha256": result.sha256,
                "expected_text_found": has_expected,
            }
        )

    manifest_results: list[dict[str, Any]] = []
    manifest_declared_asset_paths: list[str] = []
    for path, expected_start_prefix in EXPECTED_MANIFESTS.items():
        result = fetch(base_url, path, timeout_seconds)
        manifest_failures: list[str] = []
        payload = parse_json(result, manifest_failures) if result.status_code == 200 else {}
        start_url = str(payload.get("start_url") or "")
        display = str(payload.get("display") or "")
        icons = payload.get("icons") if isinstance(payload.get("icons"), list) else []
        declared_asset_paths = manifest_asset_paths(payload)
        manifest_declared_asset_paths.extend(declared_asset_paths)
        require(result.status_code == 200, failures, f"{path} expected 200, got {result.status_code}")
        require(start_url.startswith(expected_start_prefix), failures, f"{path} start_url expected {expected_start_prefix}, got {start_url or '<empty>'}")
        require(display == "standalone", failures, f"{path} display expected standalone, got {display or '<empty>'}")
        require(len(icons) >= 2, failures, f"{path} expected at least two icons")
        failures.extend(f"{path}: {item}" for item in manifest_failures)
        manifest_results.append(
            {
                "path": path,
                "status_code": result.status_code,
                "content_type": result.content_type,
                "start_url": start_url,
                "display": display,
                "icon_count": len(icons),
                "manifest_declared_asset_count": len(declared_asset_paths),
                "manifest_declared_assets": declared_asset_paths,
                "sha256": result.sha256,
            }
        )

    asset_results: list[dict[str, Any]] = []
    for path in EXPECTED_ASSETS:
        result = fetch(base_url, path, timeout_seconds)
        require(result.status_code == 200, failures, f"{path} expected 200, got {result.status_code}")
        require(len(result.body) > 0, failures, f"{path} returned an empty body")
        asset_results.append(
            {
                "path": path,
                "status_code": result.status_code,
                "content_type": result.content_type,
                "bytes": len(result.body.encode("utf-8")),
                "sha256": result.sha256,
            }
        )

    manifest_declared_asset_results: list[dict[str, Any]] = []
    for path in sorted(set(manifest_declared_asset_paths)):
        result = fetch(base_url, path, timeout_seconds)
        require(result.status_code == 200, failures, f"manifest-declared asset {path} expected 200, got {result.status_code}")
        require(len(result.body) > 0, failures, f"manifest-declared asset {path} returned an empty body")
        manifest_declared_asset_results.append(
            {
                "path": path,
                "status_code": result.status_code,
                "content_type": result.content_type,
                "bytes": len(result.body.encode("utf-8")),
                "sha256": result.sha256,
            }
        )

    service_worker = fetch(base_url, "/service-worker.js", timeout_seconds)
    require(service_worker.status_code == 200, failures, f"/service-worker.js expected 200, got {service_worker.status_code}")
    service_worker_result = inspect_service_worker(service_worker.body, failures)
    service_worker_declared_paths = service_worker_declared_fetchable_paths(service_worker_result)
    service_worker_declared_path_results: list[dict[str, Any]] = []
    for path in service_worker_declared_paths:
        result = fetch(base_url, path, timeout_seconds)
        require(result.status_code == 200, failures, f"service-worker declared path {path} expected 200, got {result.status_code}")
        require(len(result.body) > 0, failures, f"service-worker declared path {path} returned an empty body")
        service_worker_declared_path_results.append(
            {
                "path": path,
                "status_code": result.status_code,
                "content_type": result.content_type,
                "bytes": len(result.body.encode("utf-8")),
                "sha256": result.sha256,
            }
        )

    return {
        "contractName": "chummer.public_pwa_static_assets.v1",
        "status": "pass" if not failures else "fail",
        "route_count": len(route_results),
        "manifest_count": len(manifest_results),
        "asset_count": len(asset_results),
        "manifest_declared_asset_count": len(manifest_declared_asset_results),
        "service_worker_declared_path_count": len(service_worker_declared_path_results),
        "routes": route_results,
        "manifests": manifest_results,
        "assets": asset_results,
        "manifest_declared_assets": manifest_declared_asset_results,
        "service_worker_declared_paths": service_worker_declared_path_results,
        "service_worker": {
            "status_code": service_worker.status_code,
            "content_type": service_worker.content_type,
            **service_worker_result,
            "sha256": service_worker.sha256,
        },
        "failures": failures,
    }


def verify_ready_mobile_handoff(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    failures: list[str] = []
    result = fetch(base_url, "/ready/handoff/mobile.json", timeout_seconds)
    payload = parse_json(result, failures) if result.status_code == 200 else {}
    tools = payload.get("playtime_tools") if isinstance(payload.get("playtime_tools"), list) else []
    tool_ids = {str(item.get("id") or "") for item in tools if isinstance(item, dict)}
    living_world_tool = next(
        (item for item in tools if isinstance(item, dict) and str(item.get("id") or "") == "living_world"),
        {},
    )
    living_world_summary = str(living_world_tool.get("summary") or "").lower() if isinstance(living_world_tool, dict) else ""
    packet_routes = payload.get("packet_routes") if isinstance(payload.get("packet_routes"), list) else []
    roles = {str(item.get("roleId") or "") for item in packet_routes if isinstance(item, dict)}
    boundaries = payload.get("boundaries") if isinstance(payload.get("boundaries"), list) else []
    boundary_text = " ".join(str(item) for item in boundaries).lower()
    frontdoor_launch_route = str(payload.get("frontdoor_launch_route") or "").strip()
    role_routes = payload.get("role_routes") if isinstance(payload.get("role_routes"), list) else []
    role_routes_by_role = {
        str(item.get("role") or "").strip(): item
        for item in role_routes
        if isinstance(item, dict) and str(item.get("role") or "").strip()
    }
    packet_route_results: list[dict[str, Any]] = []

    require(result.status_code == 200, failures, f"/ready/handoff/mobile.json expected 200, got {result.status_code}")
    require(payload.get("status") == "ready", failures, "mobile handoff status is not ready")
    require(payload.get("pwa_route") == "/mobile", failures, "mobile handoff pwa_route is not /mobile")
    require(payload.get("continuity_route") == "/play/continuity", failures, "mobile handoff continuity_route is not /play/continuity")
    require(EXPECTED_PLAYTIME_TOOLS.issubset(tool_ids), failures, f"mobile handoff missing playtime tools: {sorted(EXPECTED_PLAYTIME_TOOLS - tool_ids)}")
    require(EXPECTED_READY_ROLES.issubset(roles), failures, f"mobile handoff missing packet roles: {sorted(EXPECTED_READY_ROLES - roles)}")
    require("character building" in boundary_text and "before or after" in boundary_text, failures, "mobile handoff missing character-building boundary")
    require("opt-in" in boundary_text or "opt in" in boundary_text, failures, "mobile handoff missing living-world opt-in boundary")
    require("gm remains final authority" in boundary_text, failures, "mobile handoff missing GM authority boundary")
    require("black ledger" in living_world_summary, failures, "living-world tool summary is not bound to Black Ledger")
    require("heat" in living_world_summary, failures, "living-world tool summary is not bound to heat tracking")
    require("followed-world" in living_world_summary or "followed world" in living_world_summary, failures, "living-world tool summary is not bound to followed-world selection")
    require("opt-in" in living_world_summary or "opt in" in living_world_summary, failures, "living-world tool summary is not bound to account opt-in")
    require(
        frontdoor_launch_route == REQUIRED_READY_MOBILE_FRONTDOOR_LAUNCH_ROUTE,
        failures,
        "mobile handoff frontdoor_launch_route is not " + REQUIRED_READY_MOBILE_FRONTDOOR_LAUNCH_ROUTE,
    )
    for role_name, expected in REQUIRED_READY_MOBILE_ROLE_ROUTES.items():
        role_route = role_routes_by_role.get(role_name)
        require(role_route is not None, failures, f"mobile handoff missing role route {role_name}")
        if not isinstance(role_route, dict):
            continue
        for field in (
            "mode",
            "route",
            "manifest_path",
            "manifest_id",
            "manifest_start_url",
            "session_handoff_route_template",
        ):
            require(
                role_route.get(field) == expected[field],
                failures,
                f"mobile handoff {role_name} {field} is not {expected[field]}",
            )
        require(
            role_route.get("frontdoor_default") is expected["frontdoor_default"],
            failures,
            "mobile handoff "
            f"{role_name} frontdoor_default is not {str(expected['frontdoor_default']).lower()}",
        )

    for packet_route in packet_routes:
        if not isinstance(packet_route, dict):
            failures.append("mobile handoff packet route row is not an object")
            continue

        role_id = str(packet_route.get("roleId") or "").strip()
        markdown_path = str(packet_route.get("markdown") or "").strip()
        json_path = str(packet_route.get("json") or "").strip()
        require(bool(role_id), failures, "mobile handoff packet route is missing roleId")
        require(markdown_path.startswith("/ready/packet/"), failures, f"mobile handoff packet route for {role_id or '<empty>'} has invalid markdown path")
        require(json_path.startswith("/ready/packet/"), failures, f"mobile handoff packet route for {role_id or '<empty>'} has invalid json path")

        markdown_result = fetch(base_url, markdown_path, timeout_seconds) if markdown_path.startswith("/") else None
        json_result = fetch(base_url, json_path, timeout_seconds) if json_path.startswith("/") else None
        packet_failures: list[str] = []
        packet_payload = parse_json(json_result, packet_failures) if json_result is not None and json_result.status_code == 200 else {}
        verdict = packet_payload.get("verdict") if isinstance(packet_payload.get("verdict"), dict) else {}
        packet = packet_payload.get("packet") if isinstance(packet_payload.get("packet"), dict) else {}
        verdict_role_id = str(verdict.get("roleId") or "")
        packet_role_id = str(packet.get("roleId") or "")

        if markdown_result is None:
            require(False, failures, f"{role_id or '<empty>'} markdown packet route was not fetched")
        else:
            require(markdown_result.status_code == 200, failures, f"{markdown_path} expected 200, got {markdown_result.status_code}")
            require(len(markdown_result.body.strip()) > 0, failures, f"{markdown_path} returned an empty body")
            require("markdown" in markdown_result.content_type.lower() or "text/plain" in markdown_result.content_type.lower(), failures, f"{markdown_path} is not markdown/text")
            require(f"# {role_id}".lower() in markdown_result.body.lower(), failures, f"{markdown_path} does not identify role {role_id}")

        if json_result is None:
            require(False, failures, f"{role_id or '<empty>'} json packet route was not fetched")
        else:
            require(json_result.status_code == 200, failures, f"{json_path} expected 200, got {json_result.status_code}")
            require("json" in json_result.content_type.lower(), failures, f"{json_path} is not JSON")
            require(len(json_result.body.strip()) > 0, failures, f"{json_path} returned an empty body")
            require(verdict_role_id == role_id, failures, f"{json_path} verdict roleId expected {role_id}, got {verdict_role_id or '<empty>'}")
            require(packet_role_id == role_id, failures, f"{json_path} packet roleId expected {role_id}, got {packet_role_id or '<empty>'}")
            failures.extend(f"{json_path}: {item}" for item in packet_failures)

        packet_route_results.append(
            {
                "roleId": role_id,
                "markdown": markdown_path,
                "markdown_status": markdown_result.status_code if markdown_result else 0,
                "markdown_content_type": markdown_result.content_type if markdown_result else "",
                "markdown_bytes": len(markdown_result.body.encode("utf-8")) if markdown_result else 0,
                "json": json_path,
                "json_status": json_result.status_code if json_result else 0,
                "json_content_type": json_result.content_type if json_result else "",
                "json_bytes": len(json_result.body.encode("utf-8")) if json_result else 0,
                "json_verdict_role_id": verdict_role_id,
                "json_packet_role_id": packet_role_id,
            }
        )

    return {
        "contractName": "chummer.ready_mobile_handoff_contract.v1",
        "status": "pass" if not failures else "fail",
        "status_code": result.status_code,
        "pwa_route": payload.get("pwa_route"),
        "continuity_route": payload.get("continuity_route"),
        "frontdoor_launch_route": frontdoor_launch_route,
        "tool_ids": sorted(tool_ids),
        "living_world_summary": living_world_summary,
        "packet_roles": sorted(roles),
        "role_routes": role_routes,
        "packet_route_count": len(packet_route_results),
        "packet_routes": packet_route_results,
        "failures": failures,
    }


def verify_mobile_ledger(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    failures: list[str] = []
    result = fetch(base_url, "/mobile/pwa/ledger.json", timeout_seconds)
    payload = parse_json(result, failures) if result.status_code == 200 else {}
    cache_control = result.headers.get("cache-control", "")
    vary = result.headers.get("vary", "")
    pragma = result.headers.get("pragma", "")
    summary = str(payload.get("summary") or "").lower()
    legal_posture = str(payload.get("legal_posture") or "").lower()
    opt_in_required_for = {
        str(item or "").strip()
        for item in (payload.get("opt_in_required_for") if isinstance(payload.get("opt_in_required_for"), list) else [])
        if str(item or "").strip()
    }
    black_ledger_bound = "black ledger" in summary
    heat_bound = "heat" in summary and payload.get("heat_visibility") == "hidden_until_opt_in"
    followed_world_bound = (
        ("followed-world" in summary or "followed world" in summary)
        and payload.get("world_gate") == "account_opt_in_and_followed_world_selection"
    )
    session_continuity_bound = (
        ("session continuity" in summary or "continuity" in summary)
        and payload.get("session_visibility") == "hidden_until_opt_in"
    )
    private_table_state_hidden = (
        "aggregate only" in legal_posture
        and "no private run table state" in legal_posture
        and "world heat" in legal_posture
        and "session continuity" in legal_posture
    )

    require(result.status_code == 200, failures, f"/mobile/pwa/ledger.json expected 200, got {result.status_code}")
    require(payload.get("mode") == "mobile_pwa_living_world", failures, "mobile ledger payload mode is wrong")
    require(payload.get("status") == "opt_in_required", failures, "mobile ledger should require opt-in for anonymous access")
    require(payload.get("opt_in_route") == "/account", failures, "mobile ledger opt_in_route is not /account")
    require(black_ledger_bound, failures, "mobile ledger opt-in boundary is not bound to Black Ledger")
    require(heat_bound, failures, "mobile ledger opt-in boundary is not bound to hidden heat tracking")
    require(followed_world_bound, failures, "mobile ledger opt-in boundary is not bound to followed-world selection")
    require(session_continuity_bound, failures, "mobile ledger opt-in boundary is not bound to hidden session continuity")
    require(EXPECTED_LEDGER_OPT_IN_KEYS.issubset(opt_in_required_for), failures, f"mobile ledger missing opt-in-required keys: {sorted(EXPECTED_LEDGER_OPT_IN_KEYS - opt_in_required_for)}")
    require(private_table_state_hidden, failures, "mobile ledger legal posture does not hide private table state, world heat, and session continuity")
    require(payload.get("updates_route") == "/mobile/pwa/ledger.json", failures, "mobile ledger updates_route is wrong")
    require("private" in cache_control.lower(), failures, "mobile ledger response is not private")
    require("no-store" in cache_control.lower(), failures, "mobile ledger response is not no-store")
    require("no-cache" in cache_control.lower(), failures, "mobile ledger response is not no-cache")
    require("cookie" in vary.lower() and "authorization" in vary.lower(), failures, "mobile ledger response does not vary on Cookie and Authorization")
    require("no-cache" in pragma.lower(), failures, "mobile ledger response missing Pragma no-cache")

    return {
        "contractName": "chummer.mobile_pwa_ledger_boundary.v1",
        "status": "pass" if not failures else "fail",
        "status_code": result.status_code,
        "payload_status": payload.get("status"),
        "opt_in_route": payload.get("opt_in_route"),
        "world_gate": payload.get("world_gate"),
        "heat_visibility": payload.get("heat_visibility"),
        "session_visibility": payload.get("session_visibility"),
        "opt_in_required_for": sorted(opt_in_required_for),
        "black_ledger_bound": black_ledger_bound,
        "heat_bound": heat_bound,
        "followed_world_bound": followed_world_bound,
        "session_continuity_bound": session_continuity_bound,
        "private_table_state_hidden": private_table_state_hidden,
        "cache_control": cache_control,
        "vary": vary,
        "pragma": pragma,
        "failures": failures,
    }


def receipt_is_pass(receipt: dict[str, Any] | None) -> bool:
    return isinstance(receipt, dict) and str(receipt.get("status") or "") == "pass"


def verify_flagship_horizons(child_receipts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    failures: list[str] = []
    horizon_rows: list[dict[str, Any]] = []

    route_rows = child_receipts.get("pwaStatic", {}).get("routes")
    route_statuses = {
        str(row.get("path") or ""): str(row.get("status_code") or "")
        for row in route_rows
        if isinstance(row, dict)
    } if isinstance(route_rows, list) else {}
    tool_ids = set(child_receipts.get("readyMobileHandoff", {}).get("tool_ids") or [])
    packet_roles = set(child_receipts.get("readyMobileHandoff", {}).get("packet_roles") or [])
    packet_route_count = int(child_receipts.get("readyMobileHandoff", {}).get("packet_route_count") or 0)
    browser_receipt = child_receipts.get("browserPlaywright", {})
    browser_required_proofs = set(browser_receipt.get("requiredProofs") or [])
    browser_skipped = bool(browser_receipt.get("skipped"))
    browser_status = str(browser_receipt.get("status") or "")
    required_browser_proofs = set(PLAYWRIGHT_REQUIREMENTS)
    browser_proof_coverage = (
        "full"
        if browser_status == "pass" and required_browser_proofs.issubset(browser_required_proofs)
        else "skipped"
        if browser_skipped
        else "partial"
    )

    for horizon_id, config in EXPECTED_FLAGSHIP_HORIZONS.items():
        row_failures: list[str] = []
        required_receipts = list(config.get("requiredReceipts") or [])
        for receipt_name in required_receipts:
            if not receipt_is_pass(child_receipts.get(receipt_name)):
                row_failures.append(f"{receipt_name} receipt is not pass")

        required_routes = set(config.get("requiredRoutes") or [])
        missing_routes = sorted(path for path in required_routes if route_statuses.get(path) != "200")
        if missing_routes:
            row_failures.append(f"missing deployed routes: {', '.join(missing_routes)}")

        required_tools = set(config.get("requiredTools") or [])
        missing_tools = sorted(required_tools - tool_ids)
        if missing_tools:
            row_failures.append(f"missing playtime tools: {', '.join(missing_tools)}")

        if horizon_id == "mid_term_pwa_session_utility":
            if not {"player", "gm", "organizer"}.issubset(packet_roles):
                row_failures.append("ready handoff is missing player/gm/organizer packet roles")
            if packet_route_count < len(EXPECTED_READY_ROLES):
                row_failures.append("ready handoff packet routes are not fully verified")
            if browser_status not in {"pass", ""}:
                row_failures.append("browser proof receipt is not pass")

        if horizon_id == "long_term_living_world_expansion":
            mobile_ledger = child_receipts.get("mobileLedger", {})
            cache_control = str(mobile_ledger.get("cache_control") or "").lower()
            service_worker_mode = (
                child_receipts.get("mobilePwaServiceWorkerBoundary", {})
                .get("mobileRuntime", {})
                .get("serviceWorkerBoundaryMode", "")
            )
            if mobile_ledger.get("payload_status") != config.get("requiredLedgerStatus"):
                row_failures.append("mobile ledger does not enforce opt-in-required status")
            for key, label in [
                ("black_ledger_bound", "Black Ledger heat"),
                ("heat_bound", "hidden heat tracking"),
                ("followed_world_bound", "followed-world selection"),
                ("session_continuity_bound", "session continuity"),
                ("private_table_state_hidden", "private table state"),
            ]:
                if not bool(mobile_ledger.get(key)):
                    row_failures.append(f"mobile ledger does not bind {label}")
            if "private" not in cache_control or "no-store" not in cache_control:
                row_failures.append("mobile ledger is not private/no-store")
            if service_worker_mode != "shared_portal_root_worker":
                row_failures.append("mobile service-worker boundary is not shared_portal_root_worker")

        horizon_rows.append(
            {
                "id": horizon_id,
                "title": config.get("title", horizon_id),
                "status": "pass" if not row_failures else "fail",
                "requiredReceipts": required_receipts,
                "requiredRoutes": sorted(required_routes),
                "requiredTools": sorted(required_tools),
                "failures": row_failures,
            }
        )
        failures.extend(f"{horizon_id}: {failure}" for failure in row_failures)

    return {
        "contractName": "chummer.flagship_horizons_gate.v1",
        "status": "pass" if not failures else "fail",
        "horizonCount": len(horizon_rows),
        "horizons": horizon_rows,
        "browserProofCoverage": browser_proof_coverage,
        "browserProofsRequiredForReleaseClaims": sorted(required_browser_proofs),
        "browserProofsPresent": sorted(browser_required_proofs),
        "toolIds": sorted(tool_ids),
        "packetRoles": sorted(packet_roles),
        "packetRouteCount": packet_route_count,
        "routeStatuses": route_statuses,
        "failures": failures,
    }


def verify_preflight(skip_preflight: bool) -> dict[str, Any]:
    if skip_preflight:
        return {
            "contractName": "chummer.public_edge_deploy_preflight.v1",
            "status": "pass",
            "skipped": True,
            "activePortalBuildProcesses": [],
            "failures": [],
        }

    completed = subprocess.run(
        ["pgrep", "-af", r"docker (compose .*build chummer-portal|build.*chummer-run-api:local)"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    failures: list[str] = []
    if lines:
        failures.append("portal image build/deploy process is active")
    return {
        "contractName": "chummer.public_edge_deploy_preflight.v1",
        "status": "pass" if not failures else "fail",
        "skipped": False,
        "activePortalBuildProcesses": lines,
        "failures": failures,
    }


def normalize_image_id(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if re.fullmatch(r"[0-9a-fA-F]{64}", normalized):
        return f"sha256:{normalized.lower()}"
    if normalized.startswith("sha256:"):
        prefix, digest = normalized.split(":", 1)
        return f"{prefix}:{digest.lower()}"
    return normalized


def run_docker_inspect(args: list[str]) -> tuple[int, str, str]:
    completed = subprocess.run(
        ["docker", *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def verify_portal_runtime_image(
    expected_image_id: str,
    portal_container: str,
    portal_image_tag: str,
) -> dict[str, Any]:
    expected = normalize_image_id(expected_image_id)
    if not expected:
        return {
            "contractName": "chummer.public_edge_portal_runtime_image.v1",
            "status": "pass",
            "skipped": True,
            "portalContainer": portal_container,
            "portalImageTag": portal_image_tag,
            "expectedImageId": "",
            "failures": [],
        }

    failures: list[str] = []
    container_code, container_stdout, container_stderr = run_docker_inspect(
        ["inspect", "--format", "{{.Image}} {{.Config.Image}}", portal_container]
    )
    image_code, image_stdout, image_stderr = run_docker_inspect(
        ["image", "inspect", "--format", "{{.Id}}", portal_image_tag]
    )

    actual_container_image = ""
    configured_image = ""
    actual_tag_image = ""
    if container_code != 0:
        failures.append(f"docker inspect {portal_container} failed")
    else:
        parts = container_stdout.split(maxsplit=1)
        actual_container_image = normalize_image_id(parts[0] if parts else "")
        configured_image = parts[1] if len(parts) > 1 else ""
        if actual_container_image != expected:
            failures.append(
                f"portal container image {actual_container_image or '<empty>'} does not match expected {expected}"
            )

    if image_code != 0:
        failures.append(f"docker image inspect {portal_image_tag} failed")
    else:
        actual_tag_image = normalize_image_id(image_stdout)
        if actual_tag_image != expected:
            failures.append(
                f"portal image tag {portal_image_tag} points at {actual_tag_image or '<empty>'}, expected {expected}"
            )

    return {
        "contractName": "chummer.public_edge_portal_runtime_image.v1",
        "status": "pass" if not failures else "fail",
        "skipped": False,
        "portalContainer": portal_container,
        "portalImageTag": portal_image_tag,
        "expectedImageId": expected,
        "containerImageId": actual_container_image,
        "configuredImage": configured_image,
        "tagImageId": actual_tag_image,
        "containerInspectExitCode": container_code,
        "imageInspectExitCode": image_code,
        "containerInspectStderr": container_stderr,
        "imageInspectStderr": image_stderr,
        "failures": failures,
    }


def summarize_child(name: str, child: dict[str, Any], failures: list[str]) -> str:
    status = str(child.get("status") or "fail")
    if status != "pass":
        failures.append(f"{name} proof is not pass")
    return status


def run_playwright_browser_proofs(
    base_url: str,
    required_proofs: list[str],
    timeout_seconds: float,
    artifact_dir: Path | None,
) -> dict[str, Any]:
    if not required_proofs:
        return {
            "contractName": "chummer.public_edge_browser_playwright.v1",
            "status": "pass",
            "skipped": True,
            "requiredProofs": [],
            "artifacts": {},
            "failures": [],
        }

    failures: list[str] = []
    unknown = [item for item in required_proofs if item not in PLAYWRIGHT_REQUIREMENTS]
    if unknown:
        failures.append(f"unknown Playwright proof requirements: {', '.join(sorted(unknown))}")

    proof_specs = [PLAYWRIGHT_REQUIREMENTS[item]["spec"] for item in required_proofs if item in PLAYWRIGHT_REQUIREMENTS]
    if not proof_specs:
        return {
            "contractName": "chummer.public_edge_browser_playwright.v1",
            "status": "fail",
            "skipped": False,
            "requiredProofs": required_proofs,
            "specs": [],
            "artifacts": {},
            "failures": failures or ["no Playwright specs were selected"],
        }

    completion_dir = artifact_dir or Path(tempfile.mkdtemp(prefix="chummer-public-edge-browser-proof-"))
    completion_dir.mkdir(parents=True, exist_ok=True)

    for proof_id in required_proofs:
        if proof_id not in PLAYWRIGHT_REQUIREMENTS:
            continue
        artifact_name = str(PLAYWRIGHT_REQUIREMENTS[proof_id]["artifact"])
        artifact_path = completion_dir / artifact_name
        if artifact_path.exists():
            artifact_path.unlink()

    playwright_command = resolve_playwright_command()
    playwright_env = {**os.environ}
    playwright_env.pop("FORCE_COLOR", None)
    playwright_env.pop("NO_COLOR", None)
    playwright_env["BASE_URL"] = base_url
    playwright_env["CHUMMER_COMPLETION_DIR"] = str(completion_dir)
    npm_cache_dir = completion_dir / ".npm-cache"
    npm_cache_dir.mkdir(parents=True, exist_ok=True)
    playwright_env.setdefault("npm_config_cache", str(npm_cache_dir))
    playwright_node_modules_root = resolve_playwright_node_modules_root()
    if playwright_node_modules_root is not None:
        existing_node_path = str(playwright_env.get("NODE_PATH") or "").strip()
        playwright_env["NODE_PATH"] = (
            f"{playwright_node_modules_root}{os.pathsep}{existing_node_path}"
            if existing_node_path
            else str(playwright_node_modules_root)
        )
    started = datetime.now(UTC)
    runs: dict[str, Any] = {}
    for proof_id in required_proofs:
        if proof_id not in PLAYWRIGHT_REQUIREMENTS:
            continue
        spec = str(PLAYWRIGHT_REQUIREMENTS[proof_id]["spec"])
        command = [
            *playwright_command,
            "test",
            spec,
            "--workers=1",
            "--reporter=line",
        ]
        proof_started = datetime.now(UTC)
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                env=playwright_env,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )
            proof_run = {
                "spec": spec,
                "startedAtUtc": proof_started.isoformat(),
                "completedAtUtc": datetime.now(UTC).isoformat(),
                "returnCode": completed.returncode,
                "stdoutTail": tail_lines(completed.stdout),
                "stderrTail": tail_lines(completed.stderr),
            }
            if completed.returncode != 0:
                failures.append(f"{proof_id} Playwright proof exited {completed.returncode}")
        except subprocess.TimeoutExpired as error:
            proof_run = {
                "spec": spec,
                "startedAtUtc": proof_started.isoformat(),
                "completedAtUtc": datetime.now(UTC).isoformat(),
                "returnCode": None,
                "stdoutTail": tail_lines(error.stdout),
                "stderrTail": tail_lines(error.stderr),
            }
            failures.append(f"{proof_id} Playwright proof timed out after {timeout_seconds:.0f}s")
        runs[proof_id] = proof_run

    artifacts: dict[str, Any] = {}
    for proof_id in required_proofs:
        if proof_id not in PLAYWRIGHT_REQUIREMENTS:
            continue
        artifact_name = str(PLAYWRIGHT_REQUIREMENTS[proof_id]["artifact"])
        path = completion_dir / artifact_name
        if not path.is_file():
            failures.append(f"{proof_id} did not write {artifact_name}")
            artifacts[proof_id] = {
                "path": str(path),
                "exists": False,
                "status": "missing",
            }
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            failures.append(f"{proof_id} wrote invalid JSON: {error}")
            artifacts[proof_id] = {
                "path": str(path),
                "exists": True,
                "status": "invalid_json",
            }
            continue
        status = str(payload.get("status") or "pass")
        if status != "pass":
            failures.append(f"{proof_id} artifact status is {status}")
        artifacts[proof_id] = {
            "path": str(path),
            "exists": True,
            "status": status,
            "contractName": payload.get("contractName"),
            "base_url": payload.get("base_url"),
        }

    return {
        "contractName": "chummer.public_edge_browser_playwright.v1",
        "status": "pass" if not failures else "fail",
        "skipped": False,
        "requiredProofs": required_proofs,
        "specs": proof_specs,
        "artifactDir": str(completion_dir),
        "startedAtUtc": started.isoformat(),
        "completedAtUtc": datetime.now(UTC).isoformat(),
        "runs": runs,
        "artifacts": artifacts,
        "failures": failures,
    }


def verify(
    base_url: str,
    timeout_seconds: float,
    skip_preflight: bool,
    expected_release_channel: str = "public_stable",
    playwright_requirements: list[str] | None = None,
    playwright_timeout_seconds: float = 420.0,
    playwright_artifact_dir: Path | None = None,
    expected_portal_image_id: str = "",
    portal_container: str = DEFAULT_PORTAL_CONTAINER,
    portal_image_tag: str = DEFAULT_PORTAL_IMAGE_TAG,
) -> dict[str, Any]:
    normalized_base_url = base_url.rstrip("/")
    child_receipts = {
        "downloads": verify_downloads(normalized_base_url, timeout_seconds, expected_release_channel),
        "navigation": verify_navigation(normalized_base_url, timeout_seconds),
        "pwaStatic": verify_pwa_static(normalized_base_url, timeout_seconds),
        "readyMobileHandoff": verify_ready_mobile_handoff(normalized_base_url, timeout_seconds),
        "mobileLedger": verify_mobile_ledger(normalized_base_url, timeout_seconds),
        "mobilePwaServiceWorkerBoundary": verify_mobile_pwa_service_worker_boundary.verify(normalized_base_url, timeout_seconds),
        "participateIframeShell": verify_participate_iframe_shell.verify(normalized_base_url, timeout_seconds),
        "preflight": verify_preflight(skip_preflight),
        "portalRuntimeImage": verify_portal_runtime_image(
            expected_portal_image_id,
            portal_container,
            portal_image_tag,
        ),
        "browserPlaywright": run_playwright_browser_proofs(
            normalized_base_url,
            playwright_requirements or [],
            playwright_timeout_seconds,
            playwright_artifact_dir,
        ),
    }
    child_receipts["flagshipHorizons"] = verify_flagship_horizons(child_receipts)

    failures: list[str] = []
    statuses = {name: summarize_child(name, child, failures) for name, child in child_receipts.items()}

    return {
        "contractName": "chummer.public_edge_postdeploy_gate.v1",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "baseUrl": normalized_base_url,
        "status": "pass" if not failures else "fail",
        "childStatuses": statuses,
        "downloadsStatus": statuses["downloads"],
        "navigationStatus": statuses["navigation"],
        "pwaStaticStatus": statuses["pwaStatic"],
        "readyMobileHandoffStatus": statuses["readyMobileHandoff"],
        "mobileLedgerStatus": statuses["mobileLedger"],
        "mobilePwaServiceWorkerBoundaryStatus": statuses["mobilePwaServiceWorkerBoundary"],
        "participateIframeShellStatus": statuses["participateIframeShell"],
        "preflightStatus": statuses["preflight"],
        "portalRuntimeImageStatus": statuses["portalRuntimeImage"],
        "browserPlaywrightStatus": statuses["browserPlaywright"],
        "flagshipHorizonsStatus": statuses["flagshipHorizons"],
        "readyMobileHandoffToolIds": child_receipts["readyMobileHandoff"].get("tool_ids", []),
        "readyMobileHandoffPacketRoles": child_receipts["readyMobileHandoff"].get("packet_roles", []),
        "mobileLedgerPayloadStatus": child_receipts["mobileLedger"].get("payload_status", ""),
        "mobileLedgerCacheControl": child_receipts["mobileLedger"].get("cache_control", ""),
        "mobilePwaServiceWorkerBoundaryMode": child_receipts["mobilePwaServiceWorkerBoundary"].get("mobileRuntime", {}).get("serviceWorkerBoundaryMode", ""),
        "browserPlaywrightRequiredProofs": child_receipts["browserPlaywright"].get("requiredProofs", []),
        "flagshipHorizonIds": [row.get("id") for row in child_receipts["flagshipHorizons"].get("horizons", [])],
        "flagshipHorizonsBrowserProofCoverage": child_receipts["flagshipHorizons"].get("browserProofCoverage", ""),
        "portalRuntimeImageExpectedImageId": child_receipts["portalRuntimeImage"].get("expectedImageId", ""),
        "portalRuntimeImageContainerImageId": child_receipts["portalRuntimeImage"].get("containerImageId", ""),
        "participateIframeRouteCount": child_receipts["participateIframeShell"].get("iframe_route_count", 0),
        "visibleVersion": child_receipts["downloads"].get("visible_version", ""),
        "releaseManifestVersion": child_receipts["downloads"].get("release_version", ""),
        "childReceipts": child_receipts,
        "failures": failures,
    }


def self_contained_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify public-edge deployment after Chummer portal publish.")
    parser.add_argument("--base-url", default="https://chummer.run")
    parser.add_argument("--timeout-seconds", type=float, default=25.0)
    parser.add_argument("--skip-preflight", action="store_true", help="Skip active-build process checks for post-fact live verification.")
    parser.add_argument(
        "--expected-release-channel",
        default="public_stable",
        choices=["public_stable", "stable", "preview", "nightly"],
        help="Expected published release posture. Stable remains the default; nightly handoff verification must opt into preview.",
    )
    parser.add_argument("--require-downloads-status-playwright", action="store_true", help="Run the downloads/status public browser proof and include its receipt.")
    parser.add_argument("--require-mobile-pwa-viewport-playwright", action="store_true", help="Run the mobile PWA viewport browser proof and include its receipt.")
    parser.add_argument("--require-frontdoor-navigation-playwright", action="store_true", help="Run the frontdoor Open Chummer mobile browser proof and include its receipt.")
    parser.add_argument("--playwright-timeout-seconds", type=float, default=420.0)
    parser.add_argument("--playwright-artifact-dir")
    parser.add_argument("--expected-portal-image-id", default="", help="Optional Docker image id required for the live portal container and mutable local image tag.")
    parser.add_argument("--portal-container", default=DEFAULT_PORTAL_CONTAINER)
    parser.add_argument("--portal-image-tag", default=DEFAULT_PORTAL_IMAGE_TAG)
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    playwright_requirements: list[str] = []
    if args.require_downloads_status_playwright:
        playwright_requirements.append("downloadsStatus")
    if args.require_mobile_pwa_viewport_playwright:
        playwright_requirements.append("mobilePwaViewport")
    if args.require_frontdoor_navigation_playwright:
        playwright_requirements.append("frontdoorNavigation")

    result = verify(
        args.base_url,
        args.timeout_seconds,
        args.skip_preflight,
        args.expected_release_channel,
        playwright_requirements,
        args.playwright_timeout_seconds,
        Path(args.playwright_artifact_dir) if args.playwright_artifact_dir else None,
        args.expected_portal_image_id,
        args.portal_container,
        args.portal_image_tag,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if result["status"] == "pass" else 1


# Orchestrated flagship verification retained from the integration branch.
RUN_SERVICES_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RELEASE_CHANNEL_RECEIPT = WORKSPACE_ROOT / "chummer-hub-registry" / ".codex-studio" / "published" / "RELEASE_CHANNEL.generated.json"
DEFAULT_PUBLIC_EDGE_OVERLAY_ROOT = RUN_SERVICES_ROOT / ".state" / "public-edge-portal-overlay" / "app"
OVERLAY_BUILD_INFO_RELATIVE_PATH = (
    Path(".codex-studio")
    / "runtime"
    / "PUBLIC_EDGE_PORTAL_OVERLAY_BUILD_INFO.generated.json"
)
MAX_OVERLAY_BUILD_INFO_BYTES = 1024 * 1024
CORE_CHILD_CONTRACTS = {
    "preflight": "chummer.public_edge_deploy_preflight.v1",
    "downloads": "chummer.downloads_version_marker.v1",
    "pwaStatic": "chummer.public_pwa_static_assets.v1",
    "mobileLedger": "chummer.mobile_pwa_ledger_boundary.v1",
    "readyMobileHandoff": "chummer.ready_mobile_handoff_contract.v1",
    "participateIframeShell": "chummer.participate_iframe_shell.v1",
}
ONLINE_LAUNCH_CONTRACT = "chummer.online_character_roster_launch.v1"
ONLINE_LAUNCH_PATH = "/app"
ONLINE_LAUNCH_COMMAND = "character_roster"
ONLINE_LAUNCH_ALLOWED_FINAL_PATHS = {"/app", "/blazor/app"}
OPTIONAL_PLAYWRIGHT_CONTRACTS = {
    "downloadsStatusBrowser": "chummer.downloads_status_e2e.v1",
    "mobilePwaViewport": "chummer.mobile_pwa_viewport_smoke.v1",
    "pwaOfflineCache": "chummer.pwa_offline_cache.v2",
    "blazorNewRunnerMenu": "chummer.blazor_new_runner_menu.v1",
    "frontdoorNavigationMobile": "chummer.frontdoor_mobile_install_boundary.v2",
    "frontdoorNavigationLedger": "chummer.black_ledger_globe_frontdoor.v1",
    "frontdoorNavigationAnchor": "chummer.frontdoor_mobile_anchor_redirect.v2",
}
DEFAULT_PLAYWRIGHT_REUSE_MAX_AGE_HOURS = float(
    os.environ.get("CHUMMER_PUBLIC_EDGE_PLAYWRIGHT_REUSE_MAX_AGE_HOURS", "24")
)
REQUIRED_READY_MOBILE_TOOLS = {"inventory", "health", "ammo", "modifiers", "quick_rolls", "living_world"}
REQUIRED_READY_MOBILE_PACKET_ROLES = {"player", "gm", "organizer"}
REQUIRED_READY_MOBILE_FRONTDOOR_LAUNCH_ROUTE = "/mobile/player"
REQUIRED_READY_MOBILE_ROLE_ROUTES = {
    "Player": {
        "mode": "player",
        "route": "/mobile/player",
        "manifest_path": "/manifest.player.webmanifest",
        "manifest_id": "/mobile/player",
        "manifest_start_url": "/mobile/player",
        "session_handoff_route_template": "/mobile/player?sessionId={sessionId}&role=Player",
        "frontdoor_default": True,
    },
    "GameMaster": {
        "mode": "gm",
        "route": "/mobile/gm",
        "manifest_path": "/manifest.gm.webmanifest",
        "manifest_id": "/mobile/gm",
        "manifest_start_url": "/mobile/gm",
        "session_handoff_route_template": "/mobile/gm?sessionId={sessionId}&role=GameMaster",
        "frontdoor_default": False,
    },
}
REQUIRED_LEDGER_CACHE_CONTROL_TOKENS = {"private", "no-store", "no-cache", "max-age=0"}
REQUIRED_LEDGER_VARY_TOKENS = {"cookie", "authorization"}
REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES = {
    "/build",
    "/mobile",
    "/mobile/player",
    "/mobile/gm",
    "/mobile/observer",
    "/play",
    "/play/continuity",
}
REQUIRED_MOBILE_PWA_VIEWPORTS = {
    "phone-390": {"width": 390, "height": 844, "buildLayout": "compact"},
    "tablet": {"width": 768, "height": 1024, "buildLayout": "compact"},
    "desktop-1366": {"width": 1366, "height": 768, "buildLayout": "workspace"},
}
REQUIRED_MOBILE_PWA_RESULT_FIELDS = {
    "route",
    "viewport",
    "width",
    "height",
    "status",
    "overflow_x",
    "navigation_error",
}
REQUIRED_BUILD_PWA_RESULT_FIELDS = {
    "final_url",
    "build_layout_source",
    "build_layout_preference",
    "build_layout_effective",
    "build_layout_override_checked",
}
REQUIRED_BUILD_PWA_FINAL_ROUTE = "/blazor/app?command=character_roster"
REQUIRED_PWA_MANIFEST_COUNT = 3
MINIMUM_PWA_ASSET_COUNT = 1
MINIMUM_PARTICIPATE_IFRAME_ROUTES = 2
MINIMUM_MOBILE_PWA_VIEWPORTS = len(REQUIRED_MOBILE_PWA_VIEWPORTS)
REQUIRED_PWA_OFFLINE_STATIC_PATHS = {
    "/manifest.player.webmanifest",
    "/manifest.gm.webmanifest",
    "/mobile.css",
    "/mobile-turn-companion.js",
}
REQUIRED_PWA_OFFLINE_LEGACY_PRIVATE_CACHE_PREFIXES = {
    "chummer-shell-play-shell-",
    "chummer-media-play-shell-",
    "chummer-media-meta-play-shell-",
}
REQUIRED_PWA_OFFLINE_ROLE_FALLBACKS = {
    "Player": "/mobile/player",
    "GameMaster": "/mobile/gm",
}
REQUIRED_ROLE_PWA_MANIFESTS = {
    "Player": ("/manifest.player.webmanifest", "/mobile/player", "/mobile/player"),
    "GameMaster": ("/manifest.gm.webmanifest", "/mobile/gm", "/mobile/gm"),
}
ROLE_ALIAS_EXPECTED_FINAL_ROUTES = {
    "/player": "/mobile/player",
    "/jammer": "/mobile/player",
    "/gm": "/mobile/gm",
    "/observer": "/mobile/observer",
}
ROLE_ALIAS_SYNTHETIC_PRIVATE_VALUE = "synthetic-role-alias-proof"
ROLE_ALIAS_REQUIRED_CACHE_CONTROL_TOKENS = {
    "private",
    "no-store",
    "no-cache",
    "max-age=0",
}
ROLE_ALIAS_CANONICAL_MAX_BODY_BYTES = 256 * 1024
ROLE_ALIAS_INSTALL_ONLY_SHELL_PATTERN = re.compile(
    rb"<main\b[^>]*\bdata-play-surface\s*=\s*['\"]install-only['\"][^>]*>",
    re.IGNORECASE,
)
RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE = "gold_supported"
RELEASE_CHANNEL_PREVIEW_SUPPORTABILITY_STATE = "preview_supported"
RELEASE_CHANNEL_STABLE_CHANNELS = {"public_stable", "stable", "docker"}
RELEASE_CHANNEL_BLOCKING_ROLLOUT_STATES = {
    "coverage_incomplete",
    "release_review_required",
    "public_release_review_required",
    "desktop_polish_needed",
    "revoked",
}
FRONTDOOR_ANCHOR_CANONICAL_SUFFIX = "/#turn-runsite-card"
FRONTDOOR_ANCHOR_LEGACY_SUFFIX = "/#turn-runsite-card?"
FRONTDOOR_REDACTED_PRIVATE_VALUE = "[redacted]"
FRONTDOOR_PRIVATE_QUERY_KEYS = {"sessionid", "deviceid"}
FRONTDOOR_PRIVATE_QUERY_ASSIGNMENT = re.compile(
    r"(?i)((?:[?&]|\b)(?:sessionId|deviceId)[\"']?\s*[:=]\s*[\"']?)([^&#,}\s\"']*)"
)


def require_full_deployment_digest(value: object, *, label: str) -> str:
    normalized = str(value or "").strip()
    if re.fullmatch(r"[0-9a-f]{64}", normalized) is None:
        raise RuntimeError(f"{label} is not a lowercase SHA-256 digest")
    return normalized


def load_expected_deployment_identity(
    build_info_path: Path,
    *,
    source_root: Path = RUN_SERVICES_ROOT,
    overlay_root: Path | None = None,
) -> dict[str, Any]:
    normalized = Path(os.path.abspath(os.fspath(build_info_path.expanduser())))
    current = Path(normalized.anchor)
    for component in normalized.parts[1:]:
        current /= component
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise RuntimeError("trusted overlay build-info is unavailable") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise RuntimeError("trusted overlay build-info contains a symlink component")
    path_stat = normalized.lstat()
    if (
        not stat.S_ISREG(path_stat.st_mode)
        or path_stat.st_size <= 0
        or path_stat.st_size > MAX_OVERLAY_BUILD_INFO_BYTES
    ):
        raise RuntimeError("trusted overlay build-info is not a bounded regular file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(normalized, flags)
    try:
        before = os.fstat(descriptor)
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, 64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_OVERLAY_BUILD_INFO_BYTES:
                raise RuntimeError("trusted overlay build-info exceeds its size limit")
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        or total != before.st_size
    ):
        raise RuntimeError("trusted overlay build-info changed while being read")
    try:
        path_after = normalized.lstat()
    except OSError as exc:
        raise RuntimeError("trusted overlay build-info pathname changed after read") from exc
    if (
        not stat.S_ISREG(path_after.st_mode)
        or (
            path_after.st_dev,
            path_after.st_ino,
            path_after.st_size,
            path_after.st_mtime_ns,
            path_after.st_ctime_ns,
        )
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    ):
        raise RuntimeError("trusted overlay build-info pathname changed after read")

    try:
        payload = strict_json_object(
            b"".join(chunks),
            label="trusted overlay build-info",
        )
    except StrictJsonContractError as exc:
        raise RuntimeError("trusted overlay build-info is not strict UTF-8 JSON") from exc
    recorded_source_fingerprint = payload.get("sourceFingerprint")
    recorded_staged_payload_fingerprint = payload.get("stagedPayloadFingerprint")
    recorded_payload_mode_receipt = payload.get("payloadModeReceipt")
    recorded_digest = payload.get("fullDeploymentDigest")
    recorded_frontdoor_playwright_closure = payload.get(
        "frontdoorPlaywrightProofClosure"
    )
    if (
        not isinstance(recorded_source_fingerprint, dict)
        or not isinstance(recorded_staged_payload_fingerprint, dict)
        or not isinstance(recorded_payload_mode_receipt, dict)
        or not isinstance(recorded_digest, dict)
        or not isinstance(recorded_frontdoor_playwright_closure, dict)
    ):
        raise RuntimeError("trusted overlay build-info deployment identity is incomplete")
    current_source_fingerprint = source_fingerprint(
        Path(os.path.abspath(os.fspath(source_root.expanduser())))
    )
    selected_overlay_root = Path(
        os.path.abspath(os.fspath(overlay_root or normalized.parents[2]))
    )
    current_staged_payload_fingerprint = staged_payload_fingerprint(
        selected_overlay_root
    )
    payload_mode_binding = validate_payload_modes_against_receipt(
        selected_overlay_root,
        recorded_payload_mode_receipt,
    )
    current_frontdoor_playwright_closure = (
        validate_frontdoor_playwright_proof_closure(
            selected_overlay_root
            / FRONTDOOR_PLAYWRIGHT_PROOF_CLOSURE_RELATIVE_ROOT
        )
    )
    recomputed_digest = full_deployment_digest(
        current_source_fingerprint,
        current_staged_payload_fingerprint,
    )
    recorded_postdeploy_verifier_sha256 = str(
        (recorded_source_fingerprint.get("files") or {})
        .get("postdeployVerifier", {})
        .get("sha256", "")
    )
    if (
        recorded_source_fingerprint != current_source_fingerprint
        or recorded_staged_payload_fingerprint != current_staged_payload_fingerprint
        or payload_mode_binding.get("status") != "pass"
        or recorded_digest != recomputed_digest
        or recorded_frontdoor_playwright_closure
        != current_frontdoor_playwright_closure
        or re.fullmatch(r"[0-9a-f]{64}", recorded_postdeploy_verifier_sha256)
        is None
        or recorded_postdeploy_verifier_sha256
        != POSTDEPLOY_VERIFIER_LOADED_SHA256
    ):
        raise RuntimeError("trusted overlay build-info full deployment digest is invalid")
    return {
        "fullDeploymentDigestSha256": require_full_deployment_digest(
            recomputed_digest.get("sha256"),
            label="trusted overlay build-info full deployment digest",
        ),
        "frontdoorPlaywrightProofClosure": current_frontdoor_playwright_closure,
        "postdeployVerifierSha256": recorded_postdeploy_verifier_sha256,
    }


def load_expected_full_deployment_digest(
    build_info_path: Path,
    *,
    source_root: Path = RUN_SERVICES_ROOT,
    overlay_root: Path | None = None,
) -> str:
    identity = load_expected_deployment_identity(
        build_info_path,
        source_root=source_root,
        overlay_root=overlay_root,
    )
    return str(identity["fullDeploymentDigestSha256"])


def frontdoor_anchor_entry_url_matches_contract(entry_url: str) -> bool:
    normalized = str(entry_url or "").strip()
    return normalized.endswith(FRONTDOOR_ANCHOR_CANONICAL_SUFFIX) or normalized.endswith(FRONTDOOR_ANCHOR_LEGACY_SUFFIX)


def supportability_state_supported_for_channel(channel: str, supportability_state: str) -> bool:
    normalized_channel = (channel or "").lower()
    normalized_state = (supportability_state or "").lower()
    if normalized_channel in RELEASE_CHANNEL_STABLE_CHANNELS:
        return normalized_state == RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE
    if normalized_channel == "preview":
        return normalized_state in {
            RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE,
            RELEASE_CHANNEL_PREVIEW_SUPPORTABILITY_STATE,
        }
    return bool(normalized_state)


def is_published_stable_release(
    expected_release_status: str,
    expected_release_channel: str,
    expected_supportability_state: str,
    expected_rollout_state: str,
) -> bool:
    normalized_status = str(expected_release_status or "").strip().lower()
    normalized_channel = str(expected_release_channel or "").strip().lower()
    normalized_supportability_state = str(expected_supportability_state or "").strip().lower()
    normalized_rollout_state = str(expected_rollout_state or "").strip().lower()
    stable_lane_published = (
        normalized_channel in RELEASE_CHANNEL_STABLE_CHANNELS
        or normalized_rollout_state == "public_stable"
    )
    status_allows_stable_release = not normalized_status or normalized_status == "published"
    return (
        stable_lane_published
        and normalized_supportability_state == RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE
        and status_allows_stable_release
    )


def expected_visible_version_candidates(
    expected_release_version: str,
    expected_release_status: str = "",
    expected_release_channel: str = "",
    expected_supportability_state: str = "",
    expected_rollout_state: str = "",
) -> list[str]:
    normalized = str(expected_release_version or "").strip()
    if not normalized:
        return []

    posture_known = any(
        (
            str(expected_release_status or "").strip(),
            str(expected_release_channel or "").strip(),
            str(expected_supportability_state or "").strip(),
            str(expected_rollout_state or "").strip(),
        )
    )
    stable_release = is_published_stable_release(
        expected_release_status,
        expected_release_channel,
        expected_supportability_state,
        expected_rollout_state,
    )
    candidates: list[str] = [f"Version {normalized}"]
    if normalized.lower().startswith("run-") and len(normalized) >= 12:
        stamp = normalized[4:12]
        if stamp.isdigit():
            stable_label = f"Version {stamp[0:4]}.{stamp[4:6]}.{stamp[6:8]}"
            preview_label = f"{stable_label} (Preview)"
            candidates.insert(0, stable_label if stable_release else preview_label)
            if not posture_known:
                candidates.insert(1, preview_label)
                candidates.insert(2, stable_label)
        else:
            candidates.insert(0, "Version" if stable_release else "Version Preview")
            if not posture_known:
                candidates.insert(1, "Version")
                candidates.insert(2, "Version Preview")

    return list(dict.fromkeys(candidate for candidate in candidates if candidate))


def expected_homepage_lane_text(
    expected_release_status: str,
    expected_release_version: str,
    expected_release_channel: str,
    expected_supportability_state: str,
    expected_rollout_state: str,
) -> str | None:
    normalized_status = (expected_release_status or "").strip().lower()
    normalized_version = (expected_release_version or "").strip()
    normalized_channel = (expected_release_channel or "").strip().lower()
    normalized_supportability_state = (expected_supportability_state or "").strip().lower()
    normalized_rollout_state = (expected_rollout_state or "").strip().lower()

    if not any(
        (
            normalized_status,
            normalized_version,
            normalized_channel,
            normalized_supportability_state,
            normalized_rollout_state,
        )
    ):
        return None

    if normalized_status and normalized_status != "published":
        return "Current public lane: Downloads paused."

    if is_published_stable_release(
        normalized_status,
        normalized_channel,
        normalized_supportability_state,
        normalized_rollout_state,
    ):
        return "Current public lane: Stable."

    if (
        normalized_channel == "preview"
        or normalized_rollout_state == "promoted_preview"
        or normalized_supportability_state == RELEASE_CHANNEL_PREVIEW_SUPPORTABILITY_STATE
        or normalized_channel in RELEASE_CHANNEL_STABLE_CHANNELS
        or normalized_rollout_state == "public_stable"
        or normalized_supportability_state == RELEASE_CHANNEL_GOLD_SUPPORTABILITY_STATE
        or normalized_version
    ):
        return "Current public lane: Preview. Review required."

    return None


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_with_status(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, "missing"
    try:
        payload = load_json(path)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}, "invalid"
    if not isinstance(payload, dict):
        return {}, "invalid"
    return payload, "loaded"


def load_optional_json(path: Path) -> dict[str, Any]:
    payload, load_status = load_json_with_status(path)
    return payload if load_status == "loaded" else {}


def resolve_public_edge_overlay_root(configured_root: str = "") -> Path:
    configured = (configured_root or os.environ.get("CHUMMER_PUBLIC_PORTAL_APP_OVERLAY_DIR") or "").strip()
    return Path(configured).resolve() if configured else DEFAULT_PUBLIC_EDGE_OVERLAY_ROOT.resolve()


def receipt_contract(payload: dict[str, Any]) -> str:
    return str(payload.get("contractName") or payload.get("contract_name") or "").strip()


def list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def string_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip() for item in value if str(item).strip()}


def string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def contains_tokens(value: Any, required_tokens: set[str]) -> bool:
    normalized = str(value or "").lower()
    return all(token in normalized for token in required_tokens)


def mobile_pwa_viewport_route_set(artifact: dict[str, Any]) -> set[str]:
    routes = string_set(artifact.get("routes"))
    results = artifact.get("results") if isinstance(artifact.get("results"), list) else []
    for result in results:
        if not isinstance(result, dict):
            continue
        route = str(result.get("route") or "").strip()
        if route:
            routes.add(route)
    return routes


def route_from_url(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if not parsed.scheme and not parsed.netloc:
        return text
    route = parsed.path or "/"
    return route + (f"?{parsed.query}" if parsed.query else "")


def artifact_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def blazor_new_runner_workbench_route(artifact: dict[str, Any]) -> dict[str, Any]:
    return artifact_object(artifact.get("workbench_fallback_route"))


def blazor_new_runner_app_roster_transition(artifact: dict[str, Any]) -> dict[str, Any]:
    return artifact_object(artifact.get("app_roster_transition"))


def artifact_value_with_fallback(
    artifact: dict[str, Any],
    key: str,
    nested: dict[str, Any] | None = None,
) -> Any:
    value = artifact.get(key)
    if value not in (None, ""):
        return value
    nested_payload = nested if nested is not None else artifact
    value = nested_payload.get(key)
    if value not in (None, ""):
        return value
    return None


def role_alias_route_results(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    results = value.get("results")
    if not isinstance(results, list):
        return []
    return [item for item in results if isinstance(item, dict)]


class _RoleAliasNoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


def open_role_alias_without_redirects(request: Request, timeout: float):
    opener = build_opener(_RoleAliasNoRedirectHandler())
    try:
        return opener.open(request, timeout=timeout)
    except HTTPError as exc:
        # urllib represents a deliberately un-followed 3xx response as HTTPError.
        return exc


def open_role_alias_first_hop(request: Request, timeout: float):
    return open_role_alias_without_redirects(request, timeout)


def open_role_alias_canonical_target(request: Request, timeout: float):
    return open_role_alias_without_redirects(request, timeout)


def role_alias_response_status(response: Any) -> int:
    return int(getattr(response, "status", 0) or getattr(response, "code", 0) or 0)


def role_alias_header(headers: Any, name: str) -> str:
    if headers is None:
        return ""
    value = headers.get(name) if hasattr(headers, "get") else None
    if value in (None, "") and isinstance(headers, dict):
        lowered = name.lower()
        value = next(
            (item for key, item in headers.items() if str(key).lower() == lowered),
            "",
        )
    return str(value or "").strip()


def role_alias_origin(value: str) -> tuple[str, str, int] | None:
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError:
        return None
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if scheme not in {"http", "https"} or not host:
        return None
    return scheme, host, port or (443 if scheme == "https" else 80)


def role_alias_safe_base_url(value: str) -> str:
    origin = role_alias_origin(value)
    if origin is None:
        return ""
    scheme, host, port = origin
    display_host = f"[{host}]" if ":" in host else host
    default_port = 443 if scheme == "https" else 80
    port_suffix = "" if port == default_port else f":{port}"
    return f"{scheme}://{display_host}{port_suffix}"


def role_alias_final_url_matches(
    base_url: str,
    final_url: str,
    expected_path: str,
) -> bool:
    try:
        parsed = urlparse(final_url)
    except ValueError:
        return False
    return (
        parsed.username is None
        and parsed.password is None
        and role_alias_origin(final_url) == role_alias_origin(base_url)
        and parsed.path == expected_path
        and not parsed.query
        and not parsed.fragment
        and "?" not in final_url.split("#", 1)[0]
    )


def role_alias_canonical_target_result_matches(
    result: Any,
    expected_final_route: str,
) -> bool:
    if not isinstance(result, dict):
        return False
    cache_tokens = {
        token.strip().lower()
        for token in str(result.get("cacheControl") or "").split(",")
        if token.strip()
    }
    body_bytes_read = result.get("bodyBytesRead")
    return (
        str(result.get("route") or "") == expected_final_route
        and int_value(result.get("status")) == 200
        and str(result.get("contentType") or "").split(";", 1)[0].strip().lower()
        == "text/html"
        and ROLE_ALIAS_REQUIRED_CACHE_CONTROL_TOKENS <= cache_tokens
        and str(result.get("pragma") or "").strip().lower() == "no-cache"
        and str(result.get("expires") or "").strip() == "0"
        and str(result.get("referrerPolicy") or "").strip().lower() == "no-referrer"
        and str(result.get("contentTypeOptions") or "").strip().lower() == "nosniff"
        and type(body_bytes_read) is int
        and 0 < body_bytes_read <= ROLE_ALIAS_CANONICAL_MAX_BODY_BYTES
        and result.get("responseUrlExact") is True
        and result.get("noRedirectLocation") is True
        and result.get("bodyWithinLimit") is True
        and result.get("installOnlyShell") is True
        and result.get("pass") is True
        and not str(result.get("error") or "").strip()
    )


def role_alias_requested_url_matches(
    base_url: str,
    requested_url: str,
    expected_alias_path: str,
) -> bool:
    try:
        parsed = urlparse(requested_url)
    except ValueError:
        return False
    return (
        parsed.username is None
        and parsed.password is None
        and role_alias_origin(requested_url) == role_alias_origin(base_url)
        and parsed.path == expected_alias_path
        and parsed.query == "sessionId=[redacted]&deviceId=[redacted]"
        and not parsed.fragment
        and "#" not in requested_url
    )


def role_alias_first_hop_result_matches(
    result: Any,
    expected_method: str,
    expected_location: str,
) -> bool:
    if not isinstance(result, dict):
        return False
    cache_tokens = {
        token.strip().lower()
        for token in str(result.get("cacheControl") or "").split(",")
        if token.strip()
    }
    return (
        str(result.get("method") or "").upper() == expected_method
        and int_value(result.get("status")) == 302
        and str(result.get("location") or "") == expected_location
        and ROLE_ALIAS_REQUIRED_CACHE_CONTROL_TOKENS <= cache_tokens
        and str(result.get("pragma") or "").strip().lower() == "no-cache"
        and str(result.get("expires") or "").strip() == "0"
        and str(result.get("referrerPolicy") or "").strip().lower() == "no-referrer"
        and result.get("pass") is True
        and not str(result.get("error") or "").strip()
    )


def role_alias_result_matches_contract(
    result: Any,
    base_url: str,
    expected_alias_path: str,
    expected_final_route: str,
) -> bool:
    if not isinstance(result, dict):
        return False
    expected_location = f"{expected_final_route}#"
    first_hops = result.get("firstHopResults")
    if not isinstance(first_hops, list) or len(first_hops) != 2:
        return False
    by_method = {
        str(item.get("method") or "").upper(): item
        for item in first_hops
        if isinstance(item, dict)
    }
    return (
        set(by_method) == {"GET", "HEAD"}
        and all(
            role_alias_first_hop_result_matches(
                by_method[method],
                method,
                expected_location,
            )
            for method in ("GET", "HEAD")
        )
        and str(result.get("expectedFirstHopLocation") or "") == expected_location
        and str(result.get("aliasPath") or "") == expected_alias_path
        and str(result.get("expectedFinalRoute") or "") == expected_final_route
        and role_alias_requested_url_matches(
            base_url,
            str(result.get("requestedUrl") or ""),
            expected_alias_path,
        )
        and result.get("firstHopsPass") is True
        and result.get("finalUrlPass") is True
        and int_value(result.get("httpStatus")) == 200
        and role_alias_canonical_target_result_matches(
            result.get("canonicalTarget"),
            expected_final_route,
        )
        and role_alias_final_url_matches(
            base_url,
            str(result.get("finalUrl") or ""),
            expected_final_route,
        )
        and str(result.get("finalRoute") or "") == expected_final_route
        and result.get("pass") is True
        and not str(result.get("error") or "").strip()
        and not artifact_contains_raw_private_identity(result)
    )


def inspect_role_alias_first_hop(
    requested_url: str,
    expected_location: str,
    method: str,
    timeout: float,
) -> dict[str, Any]:
    response = None
    error = ""
    status = 0
    location = ""
    cache_control = ""
    pragma = ""
    expires = ""
    referrer_policy = ""
    try:
        request = Request(
            requested_url,
            headers={"User-Agent": "chummer-public-edge-postdeploy-gate/1.0"},
            method=method,
        )
        response = open_role_alias_first_hop(request, timeout)
        status = role_alias_response_status(response)
        headers = getattr(response, "headers", None)
        location = role_alias_header(headers, "Location")
        cache_control = role_alias_header(headers, "Cache-Control")
        pragma = role_alias_header(headers, "Pragma")
        expires = role_alias_header(headers, "Expires")
        referrer_policy = role_alias_header(headers, "Referrer-Policy")
    except (TimeoutError, URLError, OSError, ValueError) as exc:
        # Do not persist exception text: urllib errors can contain the raw request URL.
        error = f"{type(exc).__name__}: first-hop request failed"
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()

    cache_tokens = {
        token.strip().lower()
        for token in cache_control.split(",")
        if token.strip()
    }
    checks = {
        "exact302": status == 302,
        "exactLocation": location == expected_location,
        "privateNoCache": ROLE_ALIAS_REQUIRED_CACHE_CONTROL_TOKENS <= cache_tokens,
        "pragmaNoCache": pragma.lower() == "no-cache",
        "expiresZero": expires == "0",
        "noReferrer": referrer_policy.lower() == "no-referrer",
        "requestSucceeded": not error,
    }
    recorded_location = (
        location
        if checks["exactLocation"]
        else "[invalid]" if location else ""
    )
    return {
        "method": method,
        "status": status,
        "location": recorded_location,
        "cacheControl": cache_control,
        "pragma": pragma,
        "expires": expires,
        "referrerPolicy": referrer_policy,
        "checks": checks,
        "pass": all(checks.values()),
        "error": error,
    }


def inspect_role_alias_canonical_target(
    base_url: str,
    expected_final_route: str,
    timeout: float,
) -> dict[str, Any]:
    normalized_base_url = base_url.rstrip("/") + "/"
    target_url = urljoin(normalized_base_url, expected_final_route.lstrip("/"))
    status = 0
    response_url_exact = False
    content_type = ""
    cache_control = ""
    pragma = ""
    expires = ""
    referrer_policy = ""
    content_type_options = ""
    location = ""
    body_bytes_read = 0
    body_within_limit = False
    install_only_shell = False
    error = ""
    response = None

    if not role_alias_final_url_matches(base_url, target_url, expected_final_route):
        error = "canonical target construction failed"
    else:
        try:
            request = Request(
                target_url,
                headers={"User-Agent": "chummer-public-edge-postdeploy-gate/1.0"},
                method="GET",
            )
            response = open_role_alias_canonical_target(request, timeout)
            status = role_alias_response_status(response)
            response_url = str(response.geturl() or "")
            response_url_exact = role_alias_final_url_matches(
                base_url,
                response_url,
                expected_final_route,
            )
            headers = getattr(response, "headers", None)
            content_type = role_alias_header(headers, "Content-Type")
            cache_control = role_alias_header(headers, "Cache-Control")
            pragma = role_alias_header(headers, "Pragma")
            expires = role_alias_header(headers, "Expires")
            referrer_policy = role_alias_header(headers, "Referrer-Policy")
            content_type_options = role_alias_header(headers, "X-Content-Type-Options")
            location = role_alias_header(headers, "Location")

            if status == 200:
                declared_length_text = role_alias_header(headers, "Content-Length")
                declared_length = (
                    int(declared_length_text)
                    if declared_length_text.isdigit()
                    else None
                )
                if (
                    declared_length is not None
                    and declared_length > ROLE_ALIAS_CANONICAL_MAX_BODY_BYTES
                ):
                    body_bytes_read = 0
                else:
                    body = response.read(ROLE_ALIAS_CANONICAL_MAX_BODY_BYTES + 1)
                    if not isinstance(body, bytes):
                        body = bytes(body or b"")
                    body_bytes_read = len(body)
                    body_within_limit = (
                        body_bytes_read <= ROLE_ALIAS_CANONICAL_MAX_BODY_BYTES
                    )
                    if body_within_limit:
                        install_only_shell = bool(
                            ROLE_ALIAS_INSTALL_ONLY_SHELL_PATTERN.search(body)
                        )
        except (TimeoutError, URLError, OSError, ValueError, TypeError) as exc:
            # Do not persist exception text: urllib errors can contain a raw URL.
            error = f"{type(exc).__name__}: canonical target request failed"
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()

    cache_tokens = {
        token.strip().lower()
        for token in cache_control.split(",")
        if token.strip()
    }
    checks = {
        "exact200": status == 200,
        "responseUrlExact": response_url_exact,
        "noRedirectLocation": not location,
        "htmlContentType": content_type.split(";", 1)[0].strip().lower() == "text/html",
        "privateNoCache": ROLE_ALIAS_REQUIRED_CACHE_CONTROL_TOKENS <= cache_tokens,
        "pragmaNoCache": pragma.lower() == "no-cache",
        "expiresZero": expires == "0",
        "noReferrer": referrer_policy.lower() == "no-referrer",
        "noSniff": content_type_options.lower() == "nosniff",
        "bodyWithinLimit": body_within_limit,
        "installOnlyShell": install_only_shell,
        "requestSucceeded": not error,
    }
    return {
        "route": expected_final_route,
        "status": status,
        "contentType": content_type,
        "cacheControl": cache_control,
        "pragma": pragma,
        "expires": expires,
        "referrerPolicy": referrer_policy,
        "contentTypeOptions": content_type_options,
        "bodyBytesRead": body_bytes_read,
        "responseUrlExact": response_url_exact,
        "noRedirectLocation": not location,
        "bodyWithinLimit": body_within_limit,
        "installOnlyShell": install_only_shell,
        "checks": checks,
        "pass": all(checks.values()),
        "error": error,
    }


def probe_role_alias_routes(base_url: str, timeout_seconds: float) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    normalized_base_url = base_url.rstrip("/") + "/"
    timeout = max(1.0, timeout_seconds)
    for alias_path, expected_final_route in ROLE_ALIAS_EXPECTED_FINAL_ROUTES.items():
        requested_url = (
            urljoin(normalized_base_url, alias_path.lstrip("/"))
            + f"?sessionId={ROLE_ALIAS_SYNTHETIC_PRIVATE_VALUE}"
            + f"&deviceId={ROLE_ALIAS_SYNTHETIC_PRIVATE_VALUE}"
        )
        expected_location = f"{expected_final_route}#"
        first_hops = [
            inspect_role_alias_first_hop(
                requested_url,
                expected_location,
                method,
                timeout,
            )
            for method in ("GET", "HEAD")
        ]
        first_hops_pass = len(first_hops) == 2 and all(
            hop.get("pass") is True for hop in first_hops
        )
        canonical_target: dict[str, Any] = {
            "route": expected_final_route,
            "status": 0,
            "pass": False,
            "error": "first-hop contract failed; canonical target probe skipped",
        }
        if first_hops_pass:
            canonical_target = inspect_role_alias_canonical_target(
                base_url,
                expected_final_route,
                timeout,
            )
        http_status = int_value(canonical_target.get("status"))
        final_url_pass = role_alias_canonical_target_result_matches(
            canonical_target,
            expected_final_route,
        )
        final_url = (
            urljoin(normalized_base_url, expected_final_route.lstrip("/"))
            if canonical_target.get("responseUrlExact") is True
            else ""
        )
        final_route = expected_final_route if final_url_pass else ""
        error = str(canonical_target.get("error") or "")
        raw_result = {
            "aliasPath": alias_path,
            "requestedUrl": requested_url,
            "expectedFirstHopLocation": expected_location,
            "firstHopResults": first_hops,
            "httpStatus": http_status,
            "finalUrl": final_url,
            "finalRoute": final_route,
            "canonicalTarget": canonical_target,
            "expectedFinalRoute": expected_final_route,
            "firstHopsPass": first_hops_pass,
            "finalUrlPass": final_url_pass,
            "pass": first_hops_pass and final_url_pass,
            "error": error,
        }
        results.append(redact_private_identity(raw_result))
    drift = [result for result in results if result.get("pass") is not True]
    return {
        "contractName": "chummer.public_role_alias_routes.v1",
        "status": "pass" if not drift and len(results) == len(ROLE_ALIAS_EXPECTED_FINAL_ROUTES) else "fail",
        "baseUrl": role_alias_safe_base_url(base_url),
        "results": results,
        "drift": drift,
    }


def coerce_output(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def run_playwright_command(command: list[str], env: dict[str, str], timeout_seconds: int) -> tuple[int, str, str, bool]:
    execution_root = Path(
        str(env.get("CHUMMER_PLAYWRIGHT_EXECUTION_ROOT") or RUN_SERVICES_ROOT)
    )
    execution_root = Path(
        os.path.abspath(os.fspath(execution_root.expanduser()))
    )
    if env.get("CHUMMER_PLAYWRIGHT_EXECUTION_ROOT"):
        _assert_no_symlink_path(
            execution_root,
            label="Playwright execution root",
        )
        if not stat.S_ISDIR(execution_root.lstat().st_mode):
            raise RuntimeError("Playwright execution root is not a directory")
    try:
        completed = subprocess.run(
            command,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=execution_root,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return 124, coerce_output(exc.output), coerce_output(exc.stderr), True
    return completed.returncode, coerce_output(completed.stdout), coerce_output(completed.stderr), False


CHILD_RAW_DIAGNOSTIC_FIELDS = {
    "argv",
    "childargv",
    "childcommand",
    "childstderr",
    "childstderrtail",
    "childstdout",
    "childstdouttail",
    "command",
    "stderr",
    "stderrtail",
    "stdout",
    "stdouttail",
}
CHILD_TEXT_DIAGNOSTIC_FIELDS = {
    "detail",
    "error",
    "errors",
    "failure",
    "failures",
    "message",
    "messages",
    "reason",
    "reasons",
}
CHILD_UNSAFE_DIAGNOSTIC_TEXT = re.compile(
    r"(?:\?|[&][^\s&#=]{1,128}=|\b(?:argv|command|stderr|stdout)\b)",
    re.IGNORECASE,
)
CHILD_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\.py")


def child_verifier_identifier(command: list[str]) -> str:
    """Return a bounded, query-free identifier without serializing child argv."""
    for argument in command:
        candidate = Path(str(argument)).name
        if CHILD_IDENTIFIER.fullmatch(candidate):
            return candidate.removesuffix(".py")
    return "child-verifier"


def sanitize_child_diagnostic_text(value: str) -> str:
    """Keep query-free messages while failing closed on command/output-like text."""
    if CHILD_UNSAFE_DIAGNOSTIC_TEXT.search(value):
        return "[child diagnostic redacted]"
    return value


def sanitize_child_receipt(value: Any, *, diagnostic_context: bool = False) -> Any:
    """Remove raw execution diagnostics before a child receipt can be persisted."""
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if (
                normalized_key in CHILD_RAW_DIAGNOSTIC_FIELDS
                or any(
                    raw_name in normalized_key
                    for raw_name in ("argv", "command", "stderr", "stdout")
                )
            ):
                continue
            sanitized[key] = sanitize_child_receipt(
                item,
                diagnostic_context=(
                    diagnostic_context
                    or normalized_key in CHILD_TEXT_DIAGNOSTIC_FIELDS
                ),
            )
        return sanitized
    if isinstance(value, list):
        return [
            sanitize_child_receipt(item, diagnostic_context=diagnostic_context)
            for item in value
        ]
    if isinstance(value, tuple):
        return tuple(
            sanitize_child_receipt(item, diagnostic_context=diagnostic_context)
            for item in value
        )
    if diagnostic_context and isinstance(value, str):
        return sanitize_child_diagnostic_text(value)
    return value


def normalize_base_url(value: Any) -> str:
    return str(value or "").strip().rstrip("/")


def artifact_base_url_matches(artifact: dict[str, Any], base_url: str) -> bool:
    artifact_base_url = normalize_base_url(artifact.get("base_url") or artifact.get("baseUrl"))
    requested_base_url = normalize_base_url(base_url)
    return not artifact_base_url or artifact_base_url == requested_base_url


def artifact_generated_at_text(artifact: dict[str, Any]) -> str:
    return str(
        artifact.get("generated_at_utc")
        or artifact.get("generatedAtUtc")
        or artifact.get("generated_at")
        or artifact.get("generatedAt")
        or ""
    ).strip()


def artifact_age_hours(artifact: dict[str, Any]) -> float | None:
    generated_at = artifact_generated_at_text(artifact)
    if not generated_at:
        return None

    try:
        parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)

    age_hours = (datetime.now(UTC) - parsed).total_seconds() / 3600.0
    return max(age_hours, 0.0)


def mobile_pwa_viewport_artifact_contract_failures(
    artifact: dict[str, Any],
    *,
    expected_base_url: str = "",
) -> list[str]:
    failures: list[str] = []
    expected_contract = OPTIONAL_PLAYWRIGHT_CONTRACTS["mobilePwaViewport"]
    if receipt_contract(artifact) != expected_contract:
        failures.append(
            "mobile PWA viewport Playwright artifact contract is not "
            + expected_contract
        )
    if str(artifact.get("status") or "").strip().lower() != "pass":
        failures.append("mobile PWA viewport Playwright artifact status is not pass")

    artifact_base_url = normalize_base_url(
        artifact.get("base_url") or artifact.get("baseUrl")
    )
    normalized_expected_base_url = normalize_base_url(expected_base_url)
    if not artifact_base_url:
        failures.append("mobile PWA viewport Playwright artifact base URL is missing")
    elif (
        normalized_expected_base_url
        and artifact_base_url != normalized_expected_base_url
    ):
        failures.append(
            "mobile PWA viewport Playwright artifact base URL does not match the requested base URL"
        )

    routes_value = artifact.get("routes")
    routes = string_set(routes_value)
    if (
        not isinstance(routes_value, list)
        or len(routes) != len(routes_value)
        or any(not isinstance(route, str) or not route.strip() for route in routes_value)
    ):
        failures.append(
            "mobile PWA viewport Playwright routes must be unique non-empty strings"
        )
    route_count = artifact.get("route_count")
    if type(route_count) is not int or route_count != len(routes):
        failures.append(
            "mobile PWA viewport Playwright route count does not match its unique routes"
        )
    if type(route_count) is not int or route_count < len(
        REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES
    ):
        failures.append(
            "mobile PWA viewport Playwright route count is below required mobile routes"
        )
    missing_routes = sorted(REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES - routes)
    if missing_routes:
        failures.append(
            "mobile PWA viewport Playwright proof is missing required routes: "
            + ", ".join(missing_routes)
        )

    viewport_count = artifact.get("viewport_count")
    if type(viewport_count) is not int or viewport_count < MINIMUM_MOBILE_PWA_VIEWPORTS:
        failures.append(
            "mobile PWA viewport Playwright viewport count is below required viewports"
        )

    results_value = artifact.get("results")
    results = results_value if isinstance(results_value, list) else []
    if not isinstance(results_value, list):
        failures.append("mobile PWA viewport Playwright results must be an array")
    required_results: dict[tuple[str, str], dict[str, Any]] = {}
    for index, result in enumerate(results):
        if not isinstance(result, dict):
            failures.append(
                f"mobile PWA viewport Playwright result {index} is not an object"
            )
            continue
        route = str(result.get("route") or "").strip()
        viewport = str(result.get("viewport") or "").strip()
        key = (route, viewport)
        if (
            route not in REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES
            or viewport not in REQUIRED_MOBILE_PWA_VIEWPORTS
        ):
            continue
        if key in required_results:
            failures.append(
                "mobile PWA viewport Playwright proof duplicates required result "
                f"{route}@{viewport}"
            )
            continue
        required_results[key] = result

        required_fields = set(REQUIRED_MOBILE_PWA_RESULT_FIELDS)
        if route == "/build":
            required_fields.update(REQUIRED_BUILD_PWA_RESULT_FIELDS)
        missing_fields = sorted(required_fields - set(result))
        if missing_fields:
            failures.append(
                "mobile PWA viewport Playwright result "
                f"{route}@{viewport} is missing required fields: "
                + ", ".join(missing_fields)
            )

        expected_viewport = REQUIRED_MOBILE_PWA_VIEWPORTS[viewport]
        if (
            type(result.get("width")) is not int
            or result.get("width") != expected_viewport["width"]
            or type(result.get("height")) is not int
            or result.get("height") != expected_viewport["height"]
        ):
            failures.append(
                "mobile PWA viewport Playwright result "
                f"{route}@{viewport} has wrong viewport dimensions"
            )
        status = result.get("status")
        if type(status) is not int or not 200 <= status < 400:
            failures.append(
                "mobile PWA viewport Playwright result "
                f"{route}@{viewport} did not prove a successful HTTP response"
            )
        overflow = result.get("overflow_x")
        if (
            isinstance(overflow, bool)
            or not isinstance(overflow, (int, float))
            or not 0 <= overflow <= 1
        ):
            failures.append(
                "mobile PWA viewport Playwright result "
                f"{route}@{viewport} did not prove bounded horizontal overflow"
            )
        if result.get("navigation_error") != "":
            failures.append(
                "mobile PWA viewport Playwright result "
                f"{route}@{viewport} contains a navigation error"
            )

        if route != "/build":
            continue
        final_url = str(result.get("final_url") or "").strip()
        try:
            parsed_final_url = urlparse(final_url)
        except ValueError:
            parsed_final_url = None
        final_route = route_from_url(final_url) if parsed_final_url else ""
        final_origin = (
            normalize_base_url(
                f"{parsed_final_url.scheme}://{parsed_final_url.netloc}"
            )
            if parsed_final_url
            and parsed_final_url.scheme in {"http", "https"}
            and parsed_final_url.netloc
            else ""
        )
        if (
            final_route != REQUIRED_BUILD_PWA_FINAL_ROUTE
            or not final_origin
            or final_origin != artifact_base_url
            or (parsed_final_url is not None and bool(parsed_final_url.fragment))
        ):
            failures.append(
                "mobile PWA viewport Playwright result "
                f"/build@{viewport} did not prove the canonical roster-first Build PWA URL"
            )
        expected_layout = str(expected_viewport["buildLayout"])
        expected_override = (
            "workspace" if expected_layout == "compact" else "compact"
        )
        expected_build_fields = {
            "build_layout_source": "browser-media-query",
            "build_layout_preference": "auto",
            "build_layout_effective": expected_layout,
            "build_layout_override_checked": expected_override,
        }
        for field, expected_value in expected_build_fields.items():
            if result.get(field) != expected_value:
                failures.append(
                    "mobile PWA viewport Playwright result "
                    f"/build@{viewport} has invalid {field}"
                )

    missing_result_keys = sorted(
        (route, viewport)
        for route in REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES
        for viewport in REQUIRED_MOBILE_PWA_VIEWPORTS
        if (route, viewport) not in required_results
    )
    if missing_result_keys:
        failures.append(
            "mobile PWA viewport Playwright proof is missing required results: "
            + ", ".join(
                f"{route}@{viewport}" for route, viewport in missing_result_keys
            )
        )
    if artifact.get("failures") != []:
        failures.append(
            "mobile PWA viewport Playwright artifact failures must be an empty array"
        )
    return failures


def mobile_pwa_viewport_artifact_matches_current_contract(
    artifact: dict[str, Any],
    *,
    expected_base_url: str = "",
) -> bool:
    return not mobile_pwa_viewport_artifact_contract_failures(
        artifact,
        expected_base_url=expected_base_url,
    )


def private_identity_value_is_redacted(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return normalized in {
        FRONTDOOR_REDACTED_PRIVATE_VALUE,
        "%5bredacted%5d",
        "%3credacted%3e",
        "<redacted>",
        "redacted",
    }


def text_contains_raw_private_query_value(value: Any) -> bool:
    text = str(value or "")
    for match in FRONTDOOR_PRIVATE_QUERY_ASSIGNMENT.finditer(text):
        raw_value = match.group(2)
        if raw_value and not private_identity_value_is_redacted(raw_value):
            return True
    return False


def artifact_contains_raw_private_identity(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if (
                normalized_key in FRONTDOOR_PRIVATE_QUERY_KEYS
                and item not in (None, "")
                and not private_identity_value_is_redacted(item)
            ):
                return True
            if artifact_contains_raw_private_identity(item):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(artifact_contains_raw_private_identity(item) for item in value)
    return isinstance(value, str) and text_contains_raw_private_query_value(value)


def redact_private_identity(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized_key in FRONTDOOR_PRIVATE_QUERY_KEYS and item not in (None, ""):
                redacted[key] = FRONTDOOR_REDACTED_PRIVATE_VALUE
            else:
                redacted[key] = redact_private_identity(item)
        return redacted
    if isinstance(value, list):
        return [redact_private_identity(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_private_identity(item) for item in value)
    if isinstance(value, str):
        redacted = FRONTDOOR_PRIVATE_QUERY_ASSIGNMENT.sub(
            lambda match: match.group(1) + FRONTDOOR_REDACTED_PRIVATE_VALUE,
            value,
        )
        return redacted.replace(
            ROLE_ALIAS_SYNTHETIC_PRIVATE_VALUE,
            FRONTDOOR_REDACTED_PRIVATE_VALUE,
        )
    return value


def visible_role_url_is_path_only(value: Any, expected_path: str, expected_hash: str = "") -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        parsed = urlparse(text)
    except ValueError:
        return False
    return (
        parsed.path == expected_path
        and not parsed.query
        and not parsed.params
        and parsed.fragment == expected_hash.lstrip("#")
    )


def redacted_handoff_url_matches_contract(value: Any, expected_path: str, expected_role: str) -> bool:
    text = str(value or "").strip()
    if not text or artifact_contains_raw_private_identity(text):
        return False
    try:
        parsed = urlparse(text)
    except ValueError:
        return False
    query_items = {}
    for item in parsed.query.split("&") if parsed.query else []:
        key, separator, raw_value = item.partition("=")
        if not separator or key in query_items:
            return False
        query_items[key] = raw_value
    return (
        parsed.path == expected_path
        and not parsed.fragment
        and set(query_items) == {"sessionId", "role"}
        and private_identity_value_is_redacted(query_items.get("sessionId"))
        and query_items.get("role") == expected_role
    )


def frontdoor_mobile_artifact_matches_privacy_contract(mobile_artifact: dict[str, Any]) -> bool:
    return (
        receipt_contract(mobile_artifact) == OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationMobile"]
        and not artifact_contains_raw_private_identity(mobile_artifact)
        and string_list(mobile_artifact.get("public_install_targets"))
        == ["/build", "/mobile/player"]
        and str(mobile_artifact.get("device_routing") or "").strip()
        == "auto_ua_ch_mobile_direct"
        and str(mobile_artifact.get("play_surface") or "").strip() == "install-only"
        and str(mobile_artifact.get("play_authority") or "").strip() == "none"
        and str(mobile_artifact.get("live_session") or "").strip() == "unavailable"
        and str(mobile_artifact.get("pwa_manifest_path") or "").strip()
        == "/manifest.player.webmanifest"
        and mobile_artifact.get("live_turn_companion_shell") is False
        and all(
            type(mobile_artifact.get(field)) is int
            and mobile_artifact.get(field) == 0
            for field in (
                "private_browser_state_keys",
                "play_api_requests",
                "blazor_circuit_requests",
                "analytics_requests",
                "private_query_requests",
            )
        )
        and mobile_artifact.get("page_errors") == []
    )


def pwa_offline_artifact_matches_privacy_contract(artifact: dict[str, Any]) -> bool:
    static_paths = string_set(artifact.get("static_paths"))
    purged_prefixes = string_set(artifact.get("legacy_private_cache_prefixes_purged"))
    role_results = artifact.get("offline_role_fallbacks") if isinstance(artifact.get("offline_role_fallbacks"), list) else []
    role_results_by_role = {
        str(item.get("role") or "").strip(): item
        for item in role_results
        if isinstance(item, dict)
    }
    role_fallbacks_safe = all(
        (result := role_results_by_role.get(role)) is not None
        and result.get("path") == path
        and int_value(result.get("status")) == 503
        and "no-store" in str(result.get("cache_control") or "").lower()
        and result.get("private_projection_restored") is False
        for role, path in REQUIRED_PWA_OFFLINE_ROLE_FALLBACKS.items()
    )
    return (
        receipt_contract(artifact) == OPTIONAL_PLAYWRIGHT_CONTRACTS["pwaOfflineCache"]
        and str(artifact.get("status") or "").strip().lower() == "pass"
        and artifact.get("cache_version") == "v17"
        and artifact.get("navigation_policy") == "network_only"
        and artifact.get("private_state_scope") == "open_tab_only"
        and artifact.get("query_bearing_requests_cached") is False
        and artifact.get("private_navigation_cached") is False
        and artifact.get("private_api_cached") is False
        and artifact.get("personalized_ledger_cached") is False
        and artifact.get("unrelated_cache_preserved") is True
        and REQUIRED_PWA_OFFLINE_STATIC_PATHS <= static_paths
        and REQUIRED_PWA_OFFLINE_LEGACY_PRIVATE_CACHE_PREFIXES <= purged_prefixes
        and role_fallbacks_safe
    )


def frontdoor_ledger_artifact_matches_current_contract(ledger_artifact: dict[str, Any]) -> bool:
    return (
        receipt_contract(ledger_artifact)
        == OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationLedger"]
        and not artifact_contains_raw_private_identity(ledger_artifact)
        and str(ledger_artifact.get("route") or "").strip() == "/"
        and string_list(ledger_artifact.get("open_menu_targets"))
        == [
            "/build",
            "/mobile/player",
            "/login?next=%2Faccount%2Faccess",
        ]
        and ledger_artifact.get("gated_targets") == []
        and string_list(ledger_artifact.get("public_targets")) == ["Build", "Play"]
        and ledger_artifact.get("ledger_primary") is False
    )


def frontdoor_anchor_artifact_matches_current_contract(anchor_artifact: dict[str, Any]) -> bool:
    final_path = str(anchor_artifact.get("final_pathname") or "").strip()
    final_search = str(anchor_artifact.get("final_search") or "")
    final_hash = str(anchor_artifact.get("final_hash") or "").strip()
    return (
        receipt_contract(anchor_artifact) == OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationAnchor"]
        and not artifact_contains_raw_private_identity(anchor_artifact)
        and anchor_artifact.get("entry_had_query") is True
        and final_path == "/mobile/player"
        and final_search == ""
        and final_hash == "#turn-runsite-card"
    )


def maybe_reuse_playwright_artifact(
    *,
    artifact_path: Path,
    expected_contract: str,
    base_url: str,
    timeout_seconds: int,
    reuse_artifact_max_age_hours: float | None,
) -> dict[str, Any] | None:
    if not artifact_path.is_file():
        return None

    artifact, artifact_load_status = load_json_with_status(artifact_path)
    if artifact_load_status != "loaded":
        return None
    artifact_contract = receipt_contract(artifact)
    artifact_status = str(artifact.get("status") or "").strip().lower()
    base_url_matches = artifact_base_url_matches(artifact, base_url)
    generated_at = artifact_generated_at_text(artifact)
    age_hours = artifact_age_hours(artifact)
    artifact_fresh = (
        True
        if reuse_artifact_max_age_hours is None
        else age_hours is not None and age_hours <= reuse_artifact_max_age_hours
    )
    artifact_pass = (
        artifact_status == "pass"
        and artifact_contract == expected_contract
        and base_url_matches
        and artifact_fresh
    )
    if not artifact_pass:
        return None

    return {
        "status": "pass",
        "exitCode": 0,
        "timedOut": False,
        "timeoutSeconds": timeout_seconds,
        "artifactPath": str(artifact_path),
        "artifactContract": artifact_contract,
        "expectedArtifactContract": expected_contract,
        "artifactBaseUrlMatchesRequested": base_url_matches,
        "artifactGeneratedAtUtc": generated_at or None,
        "artifactAgeHours": age_hours,
        "artifactFresh": artifact_fresh,
        "artifactMaxAgeHours": reuse_artifact_max_age_hours,
        "artifact": artifact,
        "artifactReused": True,
        "playwrightExecuted": False,
        "stdoutTail": "",
        "stderrTail": "",
    }


def run_child(command: list[str], output_path: Path, allow_failure: bool = False) -> dict[str, Any]:
    resolved_command = list(command)
    child_id = child_verifier_identifier(resolved_command)
    if len(resolved_command) >= 2 and resolved_command[1].startswith("scripts/"):
        resolved_command[1] = str(RUN_SERVICES_ROOT / resolved_command[1])
    try:
        completed = subprocess.run(
            resolved_command + ["--output", str(output_path)],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=RUN_SERVICES_ROOT,
        )
    except (OSError, subprocess.SubprocessError):
        synthetic = {
            "status": "fail",
            "failures": [f"child verifier {child_id} could not execute"],
            "childId": child_id,
            "childExitCode": None,
        }
        if not allow_failure:
            raise RuntimeError(
                f"child verifier {child_id} could not execute"
            ) from None
        return synthetic
    if completed.returncode != 0 and not allow_failure:
        raise RuntimeError(
            f"child verifier {child_id} failed with exit code {completed.returncode}"
        )
    if not output_path.is_file():
        synthetic = {
            "status": "fail",
            "failures": [f"child verifier {child_id} did not write its receipt"],
            "childId": child_id,
            "childExitCode": completed.returncode,
        }
        if not allow_failure:
            raise RuntimeError(
                f"child verifier {child_id} did not write its receipt"
            )
        return synthetic
    payload, load_status = load_json_with_status(output_path)
    if load_status == "loaded":
        return sanitize_child_receipt(payload)
    synthetic = {
        "status": "fail",
        "failures": [f"child verifier {child_id} wrote an invalid receipt"],
        "childId": child_id,
        "childExitCode": completed.returncode,
    }
    if not allow_failure:
        raise RuntimeError(
            f"child verifier {child_id} wrote an invalid receipt"
        )
    return synthetic


def compose_status(
    preflight: dict[str, Any],
    downloads: dict[str, Any],
    pwa_static: dict[str, Any],
    mobile_ledger: dict[str, Any],
    ready_mobile_handoff: dict[str, Any],
    participate_iframe_shell: dict[str, Any],
    downloads_status_browser: dict[str, Any] | None = None,
    mobile_pwa_viewport: dict[str, Any] | None = None,
    frontdoor_navigation: dict[str, Any] | None = None,
    pwa_offline_cache: dict[str, Any] | None = None,
    blazor_new_runner_menu: dict[str, Any] | None = None,
    expected_release_version: str | None = None,
    require_launch_supported_release_channel: bool = True,
    role_alias_routes: dict[str, Any] | None = None,
    online_launch: dict[str, Any] | None = None,
    expected_full_deployment_digest_sha256: str = "",
) -> dict[str, Any]:
    failures: list[str] = []
    core_child_receipts = {
        "preflight": preflight,
        "downloads": downloads,
        "pwaStatic": pwa_static,
        "mobileLedger": mobile_ledger,
        "readyMobileHandoff": ready_mobile_handoff,
        "participateIframeShell": participate_iframe_shell,
    }
    for name, expected_contract in CORE_CHILD_CONTRACTS.items():
        child = core_child_receipts[name]
        actual_contract = str(child.get("contractName") or child.get("contract_name") or "").strip()
        if actual_contract != expected_contract:
            failures.append(f"{name} child receipt contract is not {expected_contract}")
    if preflight.get("status") != "pass":
        failures.append("public-edge deploy preflight is not pass")
    if downloads.get("status") != "pass":
        failures.append("downloads version marker proof is not pass")
    if pwa_static.get("status") != "pass":
        failures.append("public PWA static asset proof is not pass")
    if mobile_ledger.get("status") != "pass":
        failures.append("mobile PWA ledger boundary proof is not pass")
    if ready_mobile_handoff.get("status") != "pass":
        failures.append("Ready mobile handoff proof is not pass")
    if participate_iframe_shell.get("status") != "pass":
        failures.append("Participate iframe shell proof is not pass")
    if online_launch is not None:
        online_launch_contract = receipt_contract(online_launch)
        if online_launch_contract != ONLINE_LAUNCH_CONTRACT:
            failures.append(f"onlineLaunch child receipt contract is not {ONLINE_LAUNCH_CONTRACT}")
        if online_launch.get("status") != "pass":
            failures.append("Chummer Online launch proof is not pass")
        launch_url = str(online_launch.get("launch_url") or "").strip()
        final_url = str(online_launch.get("final_url") or "").strip()
        launch_url_parsed = urlparse(launch_url) if launch_url else None
        final_url_parsed = urlparse(final_url) if final_url else None
        if not launch_url_parsed or launch_url_parsed.path != ONLINE_LAUNCH_PATH:
            failures.append("Chummer Online launch proof did not request /app")
        elif launch_url_parsed.query != f"command={ONLINE_LAUNCH_COMMAND}":
            failures.append("Chummer Online launch proof did not request character_roster")
        if online_launch.get("http_status") != 200:
            failures.append("Chummer Online launch proof did not return HTTP 200")
        if not final_url_parsed or final_url_parsed.path not in ONLINE_LAUNCH_ALLOWED_FINAL_PATHS:
            failures.append("Chummer Online launch proof did not land on /app or /blazor/app")
        elif final_url_parsed.query != f"command={ONLINE_LAUNCH_COMMAND}":
            failures.append("Chummer Online launch proof did not preserve character_roster")
        if online_launch.get("has_blazor_marker") is not True:
            failures.append("Chummer Online launch proof did not prove the Blazor shell")

    service_worker = pwa_static.get("service_worker") if isinstance(pwa_static.get("service_worker"), dict) else {}
    pwa_deployment_identity = (
        pwa_static.get("deploymentIdentity")
        if isinstance(pwa_static.get("deploymentIdentity"), dict)
        else {}
    )
    pwa_full_deployment_digest_sha256 = str(
        pwa_deployment_identity.get("fullDeploymentDigestSha256") or ""
    ).strip()
    normalized_expected_full_deployment_digest = str(
        expected_full_deployment_digest_sha256 or ""
    ).strip()
    pwa_full_deployment_digest_matches_expected = bool(
        pwa_deployment_identity.get("matchesExpectedFullDeploymentDigest") is True
        and re.fullmatch(r"[0-9a-f]{64}", pwa_full_deployment_digest_sha256)
        is not None
        and (
            not normalized_expected_full_deployment_digest
            or pwa_full_deployment_digest_sha256
            == normalized_expected_full_deployment_digest
        )
    )
    if not pwa_full_deployment_digest_matches_expected:
        failures.append("public PWA static proof is not bound to the expected full deployment digest")
    if downloads.get("downloads_has_marker") is not True:
        failures.append("downloads receipt does not prove /downloads version marker")
    if downloads.get("status_redirect_has_marker") is not True:
        failures.append("downloads receipt does not prove /status version marker")
    visible_version = str(downloads.get("visible_version") or "").strip()
    status_redirect_version = str(downloads.get("status_redirect_version") or "").strip()
    downloads_version_marker_value = str(downloads.get("downloads_version_marker_value") or "").strip()
    status_redirect_version_marker_value = str(downloads.get("status_redirect_version_marker_value") or "").strip()
    downloads_version_marker_matches_release_channel = downloads.get("downloads_version_marker_matches_release_channel")
    status_redirect_version_marker_matches_release_channel = downloads.get("status_redirect_version_marker_matches_release_channel")
    status_redirect_heading = str(downloads.get("status_redirect_heading") or "").strip()
    status_redirect_heading_recognized = downloads.get("status_redirect_heading_recognized")
    status_redirect_heading_expected = str(downloads.get("status_redirect_heading_expected") or "").strip()
    status_redirect_heading_matches_release_channel = downloads.get("status_redirect_heading_matches_release_channel")
    status_redirect_heading_uses_generic_updated_copy = downloads.get("status_redirect_heading_uses_generic_updated_copy")
    if not visible_version.startswith("Version "):
        failures.append("downloads receipt missing visible Version text")
    if not status_redirect_version.startswith("Version "):
        failures.append("downloads receipt missing /status visible Version text")
    if not downloads_version_marker_value.startswith("Version "):
        failures.append("downloads receipt missing /downloads version marker value")
    if not status_redirect_version_marker_value.startswith("Version "):
        failures.append("downloads receipt missing /status version marker value")
    if not status_redirect_heading:
        failures.append("downloads receipt missing /status decision heading")
    if status_redirect_heading_recognized is not True:
        failures.append("downloads receipt does not prove a recognized /status decision heading")
    if status_redirect_heading_uses_generic_updated_copy is True:
        failures.append("downloads receipt still proves the stale generic Updated /status heading")
    if status_redirect_heading_expected and status_redirect_heading_matches_release_channel is not True:
        failures.append("downloads receipt does not prove the /status heading matches release posture")
    expected_release_status = str(downloads.get("expected_release_status") or "").strip()
    expected_release_channel = str(downloads.get("expected_release_channel") or "").strip()
    expected_release_supportability_state = str(downloads.get("expected_release_supportability_state") or "").strip()
    expected_release_rollout_state = str(downloads.get("expected_release_rollout_state") or "").strip()
    expected_release_version = str(expected_release_version or "").strip()
    require_release_channel_parity = bool(expected_release_version)
    expected_visible_versions = expected_visible_version_candidates(
        expected_release_version,
        expected_release_status,
        expected_release_channel,
        expected_release_supportability_state,
        expected_release_rollout_state,
    )
    visible_version_matches_release_channel = (
        downloads.get("visible_version_matches_release_channel")
        if isinstance(downloads.get("visible_version_matches_release_channel"), bool)
        else visible_version in expected_visible_versions
        if expected_release_version
        else None
    )
    status_redirect_version_matches_release_channel = (
        downloads.get("status_redirect_version_matches_release_channel")
        if isinstance(downloads.get("status_redirect_version_matches_release_channel"), bool)
        else status_redirect_version in expected_visible_versions
        if expected_release_version
        else None
    )
    if expected_release_version and downloads_version_marker_matches_release_channel is not True:
        failures.append("downloads version marker data does not match release channel")
    if expected_release_version and status_redirect_version_marker_matches_release_channel is not True:
        failures.append("status redirect version marker data does not match release channel")
    if expected_release_version and not visible_version_matches_release_channel:
        failures.append("downloads visible Version text does not match release channel")
    if expected_release_version and not status_redirect_version_matches_release_channel:
        failures.append("status redirect visible Version text does not match release channel")
    release_manifest_http_status = downloads.get("release_manifest_http_status")
    release_manifest_status_matches_release_channel = downloads.get("release_manifest_status_matches_release_channel")
    release_manifest_channel_matches_release_channel = downloads.get("release_manifest_channel_matches_release_channel")
    release_manifest_version_matches_release_channel = downloads.get("release_manifest_version_matches_release_channel")
    release_manifest_supportability_matches_release_channel = downloads.get("release_manifest_supportability_matches_release_channel")
    release_manifest_rollout_matches_release_channel = downloads.get("release_manifest_rollout_matches_release_channel")
    public_release_copy_safe = downloads.get("public_release_copy_safe")
    release_manifest_copy_safe = downloads.get("release_manifest_copy_safe")
    if require_release_channel_parity:
        if not expected_release_status:
            failures.append("downloads receipt missing expected release status")
        elif expected_release_status.lower() != "published":
            failures.append("downloads receipt expected release status is not published")
        if not expected_release_channel:
            failures.append("downloads receipt missing expected release channel")
        if not expected_release_supportability_state:
            failures.append("downloads receipt missing expected release supportability state")
        elif (
            require_launch_supported_release_channel
            and not supportability_state_supported_for_channel(
                expected_release_channel,
                expected_release_supportability_state,
            )
        ):
            failures.append("downloads receipt expected release supportability is not launch-supported")
        if not expected_release_rollout_state:
            failures.append("downloads receipt missing expected release rollout state")
        elif (
            require_launch_supported_release_channel
            and expected_release_rollout_state.lower() in RELEASE_CHANNEL_BLOCKING_ROLLOUT_STATES
        ):
            failures.append(f"downloads receipt expected release rollout is blocking: {expected_release_rollout_state.lower()}")
        if release_manifest_http_status != 200:
            failures.append("downloads receipt does not prove live release manifest HTTP 200")
        if release_manifest_status_matches_release_channel is not True:
            failures.append("downloads receipt live release manifest status does not match release channel")
        if release_manifest_channel_matches_release_channel is not True:
            failures.append("downloads receipt live release manifest channel does not match release channel")
        if release_manifest_version_matches_release_channel is not True:
            failures.append("downloads receipt live release manifest version does not match release channel")
        if release_manifest_supportability_matches_release_channel is not True:
            failures.append("downloads receipt live release manifest supportability does not match release channel")
        if release_manifest_rollout_matches_release_channel is not True:
            failures.append("downloads receipt live release manifest rollout does not match release channel")
        if public_release_copy_safe is not True:
            failures.append("downloads receipt static public release manifest copy is not safe")
        if release_manifest_copy_safe is not True:
            failures.append("downloads receipt live release manifest copy is not safe")

    pwa_manifest_count = list_count(pwa_static.get("manifests"))
    role_manifests = pwa_static.get("role_manifests") if isinstance(pwa_static.get("role_manifests"), list) else []
    role_manifest_count = len(role_manifests)
    role_manifests_by_role = {
        str(entry.get("role") or "").strip(): entry
        for entry in role_manifests
        if isinstance(entry, dict)
    }
    pwa_asset_count = list_count(pwa_static.get("assets"))
    if pwa_manifest_count < REQUIRED_PWA_MANIFEST_COUNT:
        failures.append("public PWA static proof does not include all manifests")
    for role, (path, expected_id, expected_start_url) in REQUIRED_ROLE_PWA_MANIFESTS.items():
        manifest = role_manifests_by_role.get(role)
        if not manifest:
            failures.append(f"public PWA static proof does not include the {role} role manifest")
            continue
        if str(manifest.get("path") or "").strip() != path:
            failures.append(f"public PWA static proof {role} manifest path is not {path}")
        if str(manifest.get("id") or "").strip() != expected_id:
            failures.append(f"public PWA static proof {role} manifest id is not {expected_id}")
        if str(manifest.get("start_url") or "").strip() != expected_start_url:
            failures.append(
                f"public PWA static proof {role} manifest start_url is not {expected_start_url}"
            )
        if str(manifest.get("display") or "").strip() != "standalone":
            failures.append(f"public PWA static proof {role} manifest display is not standalone")
    if pwa_asset_count < MINIMUM_PWA_ASSET_COUNT:
        failures.append("public PWA static proof does not include required assets")
    if service_worker.get("ledger_stream_non_cacheable") is not True:
        failures.append("public PWA static proof does not keep ledger stream non-cacheable")
    if service_worker.get("ledger_stream_precached") is not False:
        failures.append("public PWA static proof precaches personalized ledger stream")
    if service_worker.get("worker_kind") != "play":
        failures.append("public PWA static proof does not use the Play root service worker")

    if mobile_ledger.get("payload_status") != "opt_in_required":
        failures.append("mobile ledger receipt payload is not opt_in_required")
    if not contains_tokens(mobile_ledger.get("cache_control"), REQUIRED_LEDGER_CACHE_CONTROL_TOKENS):
        failures.append("mobile ledger cache-control is missing private/no-store/no-cache/max-age=0")
    if not contains_tokens(mobile_ledger.get("vary"), REQUIRED_LEDGER_VARY_TOKENS):
        failures.append("mobile ledger vary is missing Cookie and Authorization")

    tool_ids = string_set(ready_mobile_handoff.get("tool_ids"))
    missing_tools = sorted(REQUIRED_READY_MOBILE_TOOLS - tool_ids)
    if missing_tools:
        failures.append("Ready mobile handoff is missing required tools: " + ", ".join(missing_tools))
    packet_roles = string_set(ready_mobile_handoff.get("packet_roles"))
    missing_roles = sorted(REQUIRED_READY_MOBILE_PACKET_ROLES - packet_roles)
    if missing_roles:
        failures.append("Ready mobile handoff is missing required packet roles: " + ", ".join(missing_roles))
    frontdoor_launch_route = str(ready_mobile_handoff.get("frontdoor_launch_route") or "").strip()
    if frontdoor_launch_route != REQUIRED_READY_MOBILE_FRONTDOOR_LAUNCH_ROUTE:
        failures.append(
            "Ready mobile handoff frontdoor launch route is not " + REQUIRED_READY_MOBILE_FRONTDOOR_LAUNCH_ROUTE
        )
    role_routes = ready_mobile_handoff.get("role_routes") if isinstance(ready_mobile_handoff.get("role_routes"), list) else []
    role_routes_by_role = {
        str(item.get("role") or "").strip(): item
        for item in role_routes
        if isinstance(item, dict)
    }
    for role_name, expected in REQUIRED_READY_MOBILE_ROLE_ROUTES.items():
        route = role_routes_by_role.get(role_name)
        if not route:
            failures.append(f"Ready mobile handoff is missing the {role_name} role route")
            continue
        if str(route.get("mode") or "").strip() != expected["mode"]:
            failures.append(f"Ready mobile handoff {role_name} mode is not {expected['mode']}")
        if str(route.get("route") or "").strip() != expected["route"]:
            failures.append(f"Ready mobile handoff {role_name} route is not {expected['route']}")
        if str(route.get("manifest_path") or "").strip() != expected["manifest_path"]:
            failures.append(f"Ready mobile handoff {role_name} manifest path is not {expected['manifest_path']}")
        if str(route.get("manifest_id") or "").strip() != expected["manifest_id"]:
            failures.append(f"Ready mobile handoff {role_name} manifest id is not {expected['manifest_id']}")
        if str(route.get("manifest_start_url") or "").strip() != expected["manifest_start_url"]:
            failures.append(
                f"Ready mobile handoff {role_name} manifest start_url is not {expected['manifest_start_url']}"
            )
        if (
            str(route.get("session_handoff_route_template") or "").strip()
            != expected["session_handoff_route_template"]
        ):
            failures.append(
                "Ready mobile handoff "
                f"{role_name} session handoff route template is not {expected['session_handoff_route_template']}"
            )
        if route.get("frontdoor_default") is not expected["frontdoor_default"]:
            failures.append(
                "Ready mobile handoff "
                f"{role_name} frontdoor_default is not {str(expected['frontdoor_default']).lower()}"
            )

    participate_route_count = int_value(participate_iframe_shell.get("route_count"))
    participate_iframe_count = int_value(participate_iframe_shell.get("iframe_route_count"))
    participate_offline_count = int_value(participate_iframe_shell.get("offline_fallback_route_count"))
    if participate_route_count < MINIMUM_PARTICIPATE_IFRAME_ROUTES:
        failures.append("Participate iframe shell route count is below required public routes")
    if participate_iframe_count < MINIMUM_PARTICIPATE_IFRAME_ROUTES:
        failures.append("Participate iframe shell does not prove both iframe routes")
    if participate_offline_count != 0:
        failures.append("Participate iframe shell is using offline fallback routes")

    if downloads_status_browser and downloads_status_browser.get("status") != "pass":
        failures.append("downloads-status Playwright proof is not pass")
    if mobile_pwa_viewport and mobile_pwa_viewport.get("status") != "pass":
        failures.append("mobile PWA viewport Playwright proof is not pass")
    if frontdoor_navigation and frontdoor_navigation.get("status") != "pass":
        failures.append("front-door navigation Playwright proof is not pass")
    if pwa_offline_cache and pwa_offline_cache.get("status") != "pass":
        failures.append("PWA offline cache Playwright proof is not pass")
    if blazor_new_runner_menu and blazor_new_runner_menu.get("status") != "pass":
        failures.append("Blazor new-runner Playwright proof is not pass")
    role_alias_route_result_rows = role_alias_route_results(role_alias_routes)
    role_alias_route_results_by_alias = {
        str(result.get("aliasPath") or "").strip(): result
        for result in role_alias_route_result_rows
    }
    role_alias_route_drift: list[dict[str, Any]] = []
    if role_alias_routes is not None:
        if role_alias_routes.get("status") != "pass":
            failures.append("role alias route redirects drifted")
        role_alias_base_url = str(role_alias_routes.get("baseUrl") or "").strip()
        for alias_path, expected_final_route in ROLE_ALIAS_EXPECTED_FINAL_ROUTES.items():
            route_result = role_alias_route_results_by_alias.get(alias_path)
            if not route_result:
                failures.append(f"{alias_path} alias route proof is missing")
                role_alias_route_drift.append(
                    {
                        "aliasPath": alias_path,
                        "finalRoute": "",
                        "expectedFinalRoute": expected_final_route,
                        "pass": False,
                        "error": "missing result",
                    }
                )
                continue
            final_route = str(route_result.get("finalRoute") or route_from_url(route_result.get("finalUrl"))).strip()
            if not role_alias_result_matches_contract(
                route_result,
                role_alias_base_url,
                alias_path,
                expected_final_route,
            ):
                failures.append(
                    f"{alias_path} alias route proof does not satisfy the exact GET/HEAD private redirect contract"
                )
            if final_route != expected_final_route or route_result.get("pass") is not True:
                drift_result = dict(route_result)
                role_alias_route_drift.append(drift_result)
                failures.append(f"{alias_path} resolved to {final_route or '<missing>'} instead of {expected_final_route}")
    if downloads_status_browser:
        artifact = downloads_status_browser.get("artifact") if isinstance(downloads_status_browser.get("artifact"), dict) else {}
        artifact_contract = receipt_contract(artifact)
        if artifact_contract != OPTIONAL_PLAYWRIGHT_CONTRACTS["downloadsStatusBrowser"]:
            failures.append(
                "downloads-status Playwright artifact contract is not "
                + OPTIONAL_PLAYWRIGHT_CONTRACTS["downloadsStatusBrowser"]
            )
        else:
            browser_status_heading = str(artifact.get("status_redirect_heading") or "").strip()
            browser_status_heading_expected = str(artifact.get("status_redirect_heading_expected") or "").strip()
            browser_status_heading_recognized = artifact.get("status_redirect_heading_recognized")
            browser_status_heading_matches_release_channel = artifact.get("status_redirect_heading_matches_release_channel")
            browser_status_heading_uses_generic_updated_copy = artifact.get("status_redirect_heading_uses_generic_updated_copy")
            if not browser_status_heading:
                failures.append("downloads-status Playwright proof does not record a /status heading")
            if browser_status_heading_recognized is not True:
                failures.append("downloads-status Playwright proof does not prove a recognized /status decision heading")
            if not browser_status_heading_expected:
                failures.append("downloads-status Playwright proof does not record the expected /status heading")
            if browser_status_heading_uses_generic_updated_copy is True:
                failures.append("downloads-status Playwright proof still uses stale generic Updated heading")
            if browser_status_heading_expected and browser_status_heading_matches_release_channel is not True:
                failures.append("downloads-status Playwright proof does not prove the /status heading matches release posture")
    mobile_pwa_viewport_artifact_failures: list[str] = []
    mobile_pwa_viewport_artifact_current_contract_satisfied = False
    if mobile_pwa_viewport:
        artifact = mobile_pwa_viewport.get("artifact") if isinstance(mobile_pwa_viewport.get("artifact"), dict) else {}
        mobile_pwa_viewport_routes = mobile_pwa_viewport_route_set(artifact)
        missing_mobile_pwa_viewport_routes = sorted(REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES - mobile_pwa_viewport_routes)
        expected_mobile_pwa_base_url = str(
            downloads.get("base_url")
            or downloads.get("baseUrl")
            or pwa_static.get("base_url")
            or pwa_static.get("baseUrl")
            or ""
        )
        mobile_pwa_viewport_artifact_failures = (
            mobile_pwa_viewport_artifact_contract_failures(
                artifact,
                expected_base_url=expected_mobile_pwa_base_url,
            )
        )
        mobile_pwa_viewport_artifact_current_contract_satisfied = not (
            mobile_pwa_viewport_artifact_failures
        )
        failures.extend(mobile_pwa_viewport_artifact_failures)
    else:
        mobile_pwa_viewport_routes = set()
        missing_mobile_pwa_viewport_routes = sorted(REQUIRED_MOBILE_PWA_VIEWPORT_ROUTES)
    if pwa_offline_cache:
        artifact = pwa_offline_cache.get("artifact") if isinstance(pwa_offline_cache.get("artifact"), dict) else {}
        if receipt_contract(artifact) != OPTIONAL_PLAYWRIGHT_CONTRACTS["pwaOfflineCache"]:
            failures.append(
                "PWA offline cache Playwright artifact contract is not "
                + OPTIONAL_PLAYWRIGHT_CONTRACTS["pwaOfflineCache"]
            )
        static_paths = string_set(artifact.get("static_paths"))
        for expected_path in sorted(REQUIRED_PWA_OFFLINE_STATIC_PATHS):
            if expected_path not in static_paths:
                failures.append(f"PWA offline cache proof did not cache {expected_path}")
        if artifact.get("cache_version") != "v17":
            failures.append("PWA offline cache proof cache version is not v17")
        if artifact.get("navigation_policy") != "network_only":
            failures.append("PWA offline cache proof navigation policy is not network_only")
        if artifact.get("private_state_scope") != "open_tab_only":
            failures.append("PWA offline cache proof private state scope is not open_tab_only")
        if artifact.get("query_bearing_requests_cached") is not False:
            failures.append("PWA offline cache proof cached a query-bearing request")
        if artifact.get("private_navigation_cached") is not False:
            failures.append("PWA offline cache proof cached private role navigation")
        if artifact.get("private_api_cached") is not False:
            failures.append("PWA offline cache proof cached private Play API data")
        if artifact.get("personalized_ledger_cached") is not False:
            failures.append("PWA offline cache proof cached the personalized ledger stream")
        purged_prefixes = string_set(artifact.get("legacy_private_cache_prefixes_purged"))
        missing_purged_prefixes = sorted(REQUIRED_PWA_OFFLINE_LEGACY_PRIVATE_CACHE_PREFIXES - purged_prefixes)
        if missing_purged_prefixes:
            failures.append(
                "PWA offline cache proof did not purge legacy private cache prefixes: "
                + ", ".join(missing_purged_prefixes)
            )
        if artifact.get("unrelated_cache_preserved") is not True:
            failures.append("PWA offline cache proof did not preserve an unrelated cache")
        role_results = artifact.get("offline_role_fallbacks") if isinstance(artifact.get("offline_role_fallbacks"), list) else []
        role_results_by_role = {
            str(item.get("role") or "").strip(): item
            for item in role_results
            if isinstance(item, dict)
        }
        for role, path in REQUIRED_PWA_OFFLINE_ROLE_FALLBACKS.items():
            result = role_results_by_role.get(role)
            if not result:
                failures.append(f"PWA offline cache proof is missing {role} fail-closed role fallback")
                continue
            if result.get("path") != path:
                failures.append(f"PWA offline cache proof {role} fallback path is not {path}")
            if int_value(result.get("status")) != 503:
                failures.append(f"PWA offline cache proof {role} fallback did not return HTTP 503")
            if "no-store" not in str(result.get("cache_control") or "").lower():
                failures.append(f"PWA offline cache proof {role} fallback is not no-store")
            if result.get("private_projection_restored") is not False:
                failures.append(f"PWA offline cache proof {role} fallback restored private projection state")
    if blazor_new_runner_menu:
        artifact = artifact_object(blazor_new_runner_menu.get("artifact"))
        app_roster_transition = blazor_new_runner_app_roster_transition(artifact)
        workbench_fallback_route = blazor_new_runner_workbench_route(artifact)
        if receipt_contract(artifact) != OPTIONAL_PLAYWRIGHT_CONTRACTS["blazorNewRunnerMenu"]:
            failures.append(
                "Blazor new-runner Playwright artifact contract is not "
                + OPTIONAL_PLAYWRIGHT_CONTRACTS["blazorNewRunnerMenu"]
            )
        expected_app_href = "app?command=new_character"
        expected_app_final_suffix = "/blazor/app?command=new_character"
        app_resolved_href = str(app_roster_transition.get("resolved_new_runner_href") or "").strip()
        app_final_url = str(app_roster_transition.get("final_url") or "").strip()
        app_active_workflow = str(app_roster_transition.get("active_workflow") or "").strip()
        app_command = str(app_roster_transition.get("command") or "").strip()
        app_startup_command = str(app_roster_transition.get("startup_command") or "").strip()
        app_dialog_count = int_value(app_roster_transition.get("dialog_count"))
        app_headline = str(app_roster_transition.get("headline") or "").strip()
        app_workflow_heading = str(app_roster_transition.get("workflow_heading") or "").strip()
        app_file_menu_locked = app_roster_transition.get("file_menu_locked_during_dialog")
        app_new_tool_locked = app_roster_transition.get("new_tool_locked_during_dialog")
        if not app_roster_transition:
            failures.append("Blazor new-runner Playwright proof is missing the app roster transition artifact")
        else:
            if app_resolved_href != expected_app_href:
                failures.append("Blazor new-runner Playwright proof did not preserve the app roster new-character href")
            if not app_final_url.endswith(expected_app_final_suffix):
                failures.append("Blazor new-runner Playwright proof did not land on the hosted app new-character route")
            if app_active_workflow != "build-lab":
                failures.append("Blazor new-runner Playwright proof did not transition app roster into the Build Lab workflow")
            if app_command != "new-character":
                failures.append("Blazor new-runner Playwright proof did not switch app roster to command=new-character")
            if app_startup_command != "new_character":
                failures.append("Blazor new-runner Playwright proof did not preserve startup command new_character on app roster transition")
            if app_dialog_count != 1:
                failures.append("Blazor new-runner Playwright proof did not reopen exactly one startup dialog on the app roster route")
            if app_headline != "New runner":
                failures.append("Blazor new-runner Playwright proof did not render the New runner heading on app roster transition")
            if app_workflow_heading != "Build Lab shell":
                failures.append("Blazor new-runner Playwright proof did not render the Build Lab shell heading on app roster transition")
            if app_file_menu_locked is not True:
                failures.append("Blazor new-runner Playwright proof did not lock the File menu during the app roster startup dialog")
            if app_new_tool_locked is not True:
                failures.append("Blazor new-runner Playwright proof did not lock the New tool during the app roster startup dialog")
        expected_href = "workbench?workspace=blue-workspace&tab=tab-create&command=new_character"
        expected_final_suffix = "/blazor/workbench?workspace=blue-workspace&tab=tab-create&command=new_character"
        resolved_href = str(artifact_value_with_fallback(artifact, "resolved_new_runner_href", workbench_fallback_route) or "").strip()
        final_url = str(artifact_value_with_fallback(artifact, "final_url", workbench_fallback_route) or "").strip()
        reopened_data_command = str(artifact_value_with_fallback(artifact, "reopened_data_command", workbench_fallback_route) or "").strip()
        reopened_data_tab = str(artifact_value_with_fallback(artifact, "reopened_data_tab", workbench_fallback_route) or "").strip()
        dialog_count = int_value(artifact_value_with_fallback(artifact, "dialog_count", workbench_fallback_route))
        dialog_title = str(artifact_value_with_fallback(artifact, "dialog_title", workbench_fallback_route) or "").strip()
        if resolved_href != expected_href:
            failures.append("Blazor new-runner Playwright proof did not preserve the new-character href")
        if not final_url.endswith(expected_final_suffix):
            failures.append("Blazor new-runner Playwright proof did not preserve the hosted workbench dialog route")
        if reopened_data_command != "new_character":
            failures.append("Blazor new-runner Playwright proof did not keep command=new_character after reopen")
        if reopened_data_tab != "tab-create":
            failures.append("Blazor new-runner Playwright proof did not keep tab=tab-create after reopen")
        if dialog_count != 1:
            failures.append("Blazor new-runner Playwright proof did not reopen exactly one dialog")
        if dialog_title != "New runner":
            failures.append("Blazor new-runner Playwright proof did not reopen the New runner dialog")
    if frontdoor_navigation:
        raw_mobile_artifact = artifact_object(frontdoor_navigation.get("mobileArtifact"))
        raw_ledger_artifact = artifact_object(frontdoor_navigation.get("ledgerArtifact"))
        raw_anchor_artifact = artifact_object(frontdoor_navigation.get("anchorArtifact"))
        mobile_artifact = redact_private_identity(raw_mobile_artifact)
        ledger_artifact = redact_private_identity(raw_ledger_artifact)
        anchor_artifact = redact_private_identity(raw_anchor_artifact)
        frontdoor_navigation_stderr_tail = str(
            redact_private_identity(frontdoor_navigation.get("stderrTail") or "")
        ).strip()
        frontdoor_navigation_artifacts_missing = (
            not mobile_artifact and not ledger_artifact and not anchor_artifact
        )
        mobile_artifact_privacy_contract_satisfied = (
            frontdoor_mobile_artifact_matches_privacy_contract(raw_mobile_artifact)
        )
        ledger_artifact_current_contract_satisfied = (
            frontdoor_ledger_artifact_matches_current_contract(raw_ledger_artifact)
        )
        frontdoor_anchor_current_contract_satisfied = (
            frontdoor_anchor_artifact_matches_current_contract(raw_anchor_artifact)
        )
        frontdoor_proof_closure_sha256 = str(
            frontdoor_navigation.get("proofClosureSha256") or ""
        ).strip()
        frontdoor_proof_closure_status = str(
            frontdoor_navigation.get("proofClosureStatus") or ""
        ).strip()
        frontdoor_proof_closure = artifact_object(
            frontdoor_navigation.get("proofClosure")
        )
        frontdoor_playwright_runtime = artifact_object(
            frontdoor_navigation.get("playwrightRuntime")
        )
        frontdoor_proof_closure_receipt_matches = (
            frontdoor_proof_closure.get("contractName")
            == FRONTDOOR_PLAYWRIGHT_PROOF_CLOSURE_CONTRACT_NAME
            and frontdoor_proof_closure.get("algorithm")
            == FRONTDOOR_PLAYWRIGHT_PROOF_CLOSURE_ALGORITHM
            and frontdoor_proof_closure.get("status") == "pass"
            and frontdoor_proof_closure.get("aggregateSha256")
            == frontdoor_proof_closure_sha256
        )
        frontdoor_runtime_matches_closure = (
            frontdoor_playwright_runtime.get("status") == "pass"
            and frontdoor_playwright_runtime.get("resolutionMode")
            == "validated_local_node_modules_exact_lock_version"
            and frontdoor_playwright_runtime.get("playwrightPackageVersion")
            == frontdoor_proof_closure.get("playwrightPackageVersion")
        )
        frontdoor_artifact_closure_digests = {
            str(artifact.get("proof_closure_sha256") or "").strip()
            for artifact in (
                raw_mobile_artifact,
                raw_ledger_artifact,
                raw_anchor_artifact,
            )
            if artifact
        }
        frontdoor_homepage_lane_text = str(
            mobile_artifact.get("homepage_lane_text") or ""
        ).strip()
        expected_frontdoor_homepage_lane_text = expected_homepage_lane_text(
            expected_release_status,
            expected_release_version,
            expected_release_channel,
            expected_release_supportability_state,
            expected_release_rollout_state,
        )
        frontdoor_homepage_lane_matches_release_channel = (
            frontdoor_homepage_lane_text == expected_frontdoor_homepage_lane_text
            if expected_frontdoor_homepage_lane_text
            else None
        )
        if frontdoor_navigation_artifacts_missing:
            if frontdoor_navigation_stderr_tail:
                normalized_stderr_tail = (
                    frontdoor_navigation_stderr_tail.replace("\\r\\n", "\n")
                    .replace("\\n", "\n")
                    .replace("\\r", "\n")
                )
                first_line = normalized_stderr_tail.splitlines()[0].strip()
                if first_line:
                    failures.append(
                        "front-door navigation Playwright proof failed before artifacts were written: "
                        + first_line
                    )
        else:
            if (
                frontdoor_proof_closure_status != "pass"
                or re.fullmatch(r"[0-9a-f]{64}", frontdoor_proof_closure_sha256)
                is None
                or not frontdoor_proof_closure_receipt_matches
            ):
                failures.append(
                    "front-door navigation Playwright proof closure is not digest-bound"
                )
            if frontdoor_artifact_closure_digests != {
                frontdoor_proof_closure_sha256
            }:
                failures.append(
                    "front-door navigation artifacts do not match the executed proof closure"
                )
            if not frontdoor_runtime_matches_closure:
                failures.append(
                    "front-door navigation Playwright runtime is not exact-version validated"
                )
            if receipt_contract(mobile_artifact) != OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationMobile"]:
                failures.append(
                    "front-door navigation mobile artifact contract is not "
                    + OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationMobile"]
                )
            if receipt_contract(ledger_artifact) != OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationLedger"]:
                failures.append(
                    "front-door navigation ledger artifact contract is not "
                    + OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationLedger"]
                )
            if receipt_contract(anchor_artifact) != OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationAnchor"]:
                failures.append(
                    "front-door navigation anchor artifact contract is not "
                    + OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationAnchor"]
                )
            if artifact_contains_raw_private_identity(raw_mobile_artifact):
                failures.append(
                    "front-door navigation mobile artifact contains raw private session or device identity"
                )
            if artifact_contains_raw_private_identity(raw_ledger_artifact):
                failures.append(
                    "front-door navigation ledger artifact contains raw private session or device identity"
                )
            if artifact_contains_raw_private_identity(raw_anchor_artifact):
                failures.append(
                    "front-door navigation anchor artifact contains raw private session or device identity"
                )
            if (
                receipt_contract(mobile_artifact)
                == OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationMobile"]
                and not mobile_artifact_privacy_contract_satisfied
            ):
                failures.append(
                    "front-door navigation mobile artifact does not satisfy the default-denied public install contract"
                )
            if (
                receipt_contract(ledger_artifact)
                == OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationLedger"]
                and not ledger_artifact_current_contract_satisfied
            ):
                failures.append(
                    "front-door navigation ledger artifact does not expose public Build and Play handoffs"
                )
            if (
                receipt_contract(anchor_artifact)
                == OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationAnchor"]
                and not frontdoor_anchor_current_contract_satisfied
            ):
                failures.append(
                    "front-door navigation anchor artifact does not satisfy the query-dropping redirect contract"
                )
            anchor_failure_stage = str(anchor_artifact.get("failure_stage") or "").strip()
            anchor_failure_type = str(anchor_artifact.get("failure_type") or "").strip()
            if anchor_failure_type:
                failures.append(
                    "front-door navigation anchor proof failed"
                    + (f" at {anchor_failure_stage}" if anchor_failure_stage else "")
                    + f": {anchor_failure_type}"
                )
            if not frontdoor_homepage_lane_text:
                failures.append(
                    "front-door navigation homepage does not disclose current public lane"
                )
            if (
                expected_frontdoor_homepage_lane_text
                and frontdoor_homepage_lane_matches_release_channel is not True
            ):
                failures.append(
                    "front-door navigation homepage current public lane copy does not match release posture"
                )

    preflight_findings = preflight.get("findings") if isinstance(preflight.get("findings"), list) else []
    preflight_overlay_fingerprint = (
        preflight.get("overlayBuildInfoSourceFingerprint")
        if isinstance(preflight.get("overlayBuildInfoSourceFingerprint"), dict)
        else {}
    )
    preflight_overlay_fingerprint_missing_keys = string_list(preflight_overlay_fingerprint.get("missingKeys"))
    preflight_overlay_fingerprint_mismatched_keys = string_list(preflight_overlay_fingerprint.get("mismatchedKeys"))
    preflight_overlay_fingerprint_aggregate_matches = (
        preflight_overlay_fingerprint.get("aggregateMatchesCurrentSource")
        if isinstance(preflight_overlay_fingerprint.get("aggregateMatchesCurrentSource"), bool)
        else None
    )
    if preflight_overlay_fingerprint_missing_keys:
        failures.append(
            "public-edge preflight overlay build info is missing source fingerprint fields: "
            + ", ".join(preflight_overlay_fingerprint_missing_keys)
        )
    if preflight_overlay_fingerprint_mismatched_keys:
        failures.append(
            "public-edge preflight overlay build info source fingerprint does not match current source: "
            + ", ".join(preflight_overlay_fingerprint_mismatched_keys)
        )
    result = {
        "contractName": "chummer.public_edge_postdeploy_gate.v1",
        "generatedAtUtc": datetime.now(UTC).isoformat(),
        "status": "pass" if not failures else "fail",
        "baseUrl": downloads.get("base_url") or pwa_static.get("base_url") or "",
        "preflightStatus": preflight.get("status"),
        "preflightActiveLockCount": preflight.get("activeLockCount"),
        "preflightBlockingLockCount": sum(1 for finding in preflight_findings if isinstance(finding, dict) and finding.get("id") == "active_build_lane"),
        "preflightForeignLockCount": preflight.get("foreignLockCount"),
        "preflightIgnoredForeignLockCount": preflight.get("ignoredForeignLockCount"),
        "preflightFindingCount": len(preflight_findings),
        "preflightForeignLocksIgnored": preflight.get("foreignLocksIgnored"),
        "preflightAllowForeignBuildLocks": preflight.get("allowForeignBuildLocks"),
        "preflightStaleLookingLockCount": preflight.get("staleLookingLockCount"),
        "preflightStaleForeignLockCount": preflight.get("staleForeignLockCount"),
        "preflightStaleForeignLocksIgnored": preflight.get("staleForeignLocksIgnored"),
        "preflightAllowStaleForeignBuildLocks": preflight.get("allowStaleForeignBuildLocks"),
        "preflightOverlayRoot": preflight.get("overlayRoot"),
        "preflightOverlayBuildInfoSourceFingerprintAggregateMatchesCurrentSource": preflight_overlay_fingerprint_aggregate_matches,
        "preflightOverlayBuildInfoSourceFingerprintRecordedAggregateSha256": preflight_overlay_fingerprint.get("recordedAggregateSha256"),
        "preflightOverlayBuildInfoSourceFingerprintExpectedAggregateSha256": preflight_overlay_fingerprint.get("expectedAggregateSha256"),
        "preflightOverlayBuildInfoSourceFingerprintMissingKeys": preflight_overlay_fingerprint_missing_keys,
        "preflightOverlayBuildInfoSourceFingerprintMismatchedKeys": preflight_overlay_fingerprint_mismatched_keys,
        "downloadsStatus": downloads.get("status"),
        "downloadsHasMarker": downloads.get("downloads_has_marker"),
        "statusRedirectHasMarker": downloads.get("status_redirect_has_marker"),
        "visibleVersion": downloads.get("visible_version"),
        "statusRedirectVersion": downloads.get("status_redirect_version"),
        "downloadsVersionMarkerValue": downloads.get("downloads_version_marker_value"),
        "statusRedirectVersionMarkerValue": downloads.get("status_redirect_version_marker_value"),
        "downloadsVersionMarkerMatchesReleaseChannel": downloads_version_marker_matches_release_channel,
        "statusRedirectVersionMarkerMatchesReleaseChannel": status_redirect_version_marker_matches_release_channel,
        "statusRedirectHeading": status_redirect_heading,
        "statusRedirectHeadingRecognized": status_redirect_heading_recognized,
        "statusRedirectHeadingExpected": status_redirect_heading_expected,
        "statusRedirectHeadingMatchesReleaseChannel": status_redirect_heading_matches_release_channel,
        "statusRedirectHeadingUsesGenericUpdatedCopy": status_redirect_heading_uses_generic_updated_copy,
        "expectedReleaseVersion": expected_release_version,
        "visibleVersionMatchesReleaseChannel": visible_version_matches_release_channel,
        "statusRedirectVersionMatchesReleaseChannel": status_redirect_version_matches_release_channel,
        "expectedReleaseStatus": expected_release_status,
        "expectedReleaseChannel": expected_release_channel,
        "expectedReleaseSupportabilityState": expected_release_supportability_state,
        "expectedReleaseRolloutState": expected_release_rollout_state,
        "releaseManifestHttpStatus": release_manifest_http_status,
        "releaseManifestStatus": downloads.get("release_manifest_status"),
        "releaseManifestStatusMatchesReleaseChannel": release_manifest_status_matches_release_channel,
        "releaseManifestChannel": downloads.get("release_manifest_channel"),
        "releaseManifestChannelMatchesReleaseChannel": release_manifest_channel_matches_release_channel,
        "releaseManifestVersion": downloads.get("release_manifest_version"),
        "releaseManifestVersionMatchesReleaseChannel": release_manifest_version_matches_release_channel,
        "releaseManifestSupportabilityState": downloads.get("release_manifest_supportability_state"),
        "releaseManifestSupportabilityMatchesReleaseChannel": release_manifest_supportability_matches_release_channel,
        "releaseManifestRolloutState": downloads.get("release_manifest_rollout_state"),
        "releaseManifestRolloutMatchesReleaseChannel": release_manifest_rollout_matches_release_channel,
        "publicReleaseManifestCopySafe": public_release_copy_safe,
        "publicReleaseManifestUnsafeCopyMarkers": downloads.get("public_release_unsafe_copy_markers"),
        "publicReleaseManifestHasPreviewOrReviewCaveat": downloads.get("public_release_has_preview_or_review_caveat"),
        "releaseManifestCopySafe": release_manifest_copy_safe,
        "releaseManifestUnsafeCopyMarkers": downloads.get("release_manifest_unsafe_copy_markers"),
        "releaseManifestHasPreviewOrReviewCaveat": downloads.get("release_manifest_has_preview_or_review_caveat"),
        "releaseManifestParseError": downloads.get("release_manifest_parse_error"),
        "pwaStaticStatus": pwa_static.get("status"),
        "pwaManifestCount": pwa_manifest_count,
        "rolePwaManifestCount": role_manifest_count,
        "rolePwaManifests": role_manifests,
        "pwaAssetCount": pwa_asset_count,
        "ledgerStreamNonCacheable": service_worker.get("ledger_stream_non_cacheable"),
        "ledgerStreamPrecached": service_worker.get("ledger_stream_precached"),
        "pwaRootWorkerKind": service_worker.get("worker_kind"),
        "pwaRootWorkerCacheVersion": service_worker.get("cache_version"),
        "pwaDeploymentIdentity": pwa_deployment_identity,
        "expectedPwaFullDeploymentDigestSha256": normalized_expected_full_deployment_digest,
        "pwaFullDeploymentDigestSha256": pwa_full_deployment_digest_sha256,
        "pwaFullDeploymentDigestMatchesExpected": pwa_full_deployment_digest_matches_expected,
        "mobileLedgerStatus": mobile_ledger.get("status"),
        "mobileLedgerPayloadStatus": mobile_ledger.get("payload_status"),
        "mobileLedgerCacheControl": mobile_ledger.get("cache_control"),
        "mobileLedgerVary": mobile_ledger.get("vary"),
        "readyMobileHandoffStatus": ready_mobile_handoff.get("status"),
        "readyMobileHandoffToolIds": ready_mobile_handoff.get("tool_ids"),
        "readyMobileHandoffPacketRoles": ready_mobile_handoff.get("packet_roles"),
        "readyMobileHandoffFrontdoorLaunchRoute": ready_mobile_handoff.get("frontdoor_launch_route"),
        "readyMobileHandoffRoleRoutes": ready_mobile_handoff.get("role_routes"),
        "participateIframeShellStatus": participate_iframe_shell.get("status"),
        "participateIframeRouteCount": participate_route_count,
        "participateIframeRouteIframeCount": participate_iframe_count,
        "participateIframeRouteOfflineFallbackCount": participate_offline_count,
        "coreChildContracts": {
            name: str(child.get("contractName") or child.get("contract_name") or "").strip()
            for name, child in core_child_receipts.items()
        },
        "failures": failures,
        "childReceipts": {
            "preflight": preflight,
            "downloads": downloads,
            "pwaStatic": pwa_static,
            "mobileLedger": mobile_ledger,
            "readyMobileHandoff": ready_mobile_handoff,
            "participateIframeShell": participate_iframe_shell,
        },
    }
    if online_launch is not None:
        result["onlineLaunchStatus"] = online_launch.get("status")
        result["onlineLaunchContract"] = receipt_contract(online_launch)
        result["onlineLaunchLaunchUrl"] = online_launch.get("launch_url")
        result["onlineLaunchFinalUrl"] = online_launch.get("final_url")
        result["onlineLaunchHttpStatus"] = online_launch.get("http_status")
        result["onlineLaunchHasBlazorMarker"] = online_launch.get("has_blazor_marker")
        result["onlineLaunchHasRosterMarker"] = online_launch.get("has_roster_marker")
        result["childReceipts"]["onlineLaunch"] = online_launch
    if role_alias_routes is not None:
        result["roleAliasRouteStatus"] = role_alias_routes.get("status")
        result["roleAliasRouteContract"] = receipt_contract(role_alias_routes)
        result["roleAliasRouteResults"] = redact_private_identity(role_alias_route_result_rows)
        result["roleAliasRouteDrift"] = redact_private_identity(role_alias_route_drift)
    if downloads_status_browser:
        artifact = downloads_status_browser.get("artifact") if isinstance(downloads_status_browser.get("artifact"), dict) else {}
        result["downloadsStatusBrowserStatus"] = downloads_status_browser.get("status")
        result["downloadsStatusBrowserExitCode"] = downloads_status_browser.get("exitCode")
        result["downloadsStatusBrowserArtifactDir"] = downloads_status_browser.get("artifactDir")
        result["downloadsStatusBrowserArtifactContract"] = receipt_contract(artifact)
        result["downloadsStatusBrowserStatusRedirectHeading"] = artifact.get("status_redirect_heading")
        result["downloadsStatusBrowserStatusRedirectHeadingRecognized"] = artifact.get("status_redirect_heading_recognized")
        result["downloadsStatusBrowserStatusRedirectHeadingExpected"] = artifact.get("status_redirect_heading_expected")
        result["downloadsStatusBrowserStatusRedirectHeadingMatchesReleaseChannel"] = artifact.get("status_redirect_heading_matches_release_channel")
        result["downloadsStatusBrowserStatusRedirectHeadingUsesGenericUpdatedCopy"] = artifact.get("status_redirect_heading_uses_generic_updated_copy")
        result["childReceipts"]["downloadsStatusBrowser"] = downloads_status_browser
    if mobile_pwa_viewport:
        artifact = mobile_pwa_viewport.get("artifact") if isinstance(mobile_pwa_viewport.get("artifact"), dict) else {}
        result["mobilePwaViewportStatus"] = mobile_pwa_viewport.get("status")
        result["mobilePwaViewportExitCode"] = mobile_pwa_viewport.get("exitCode")
        result["mobilePwaViewportArtifactDir"] = mobile_pwa_viewport.get("artifactDir")
        result["mobilePwaViewportArtifactContract"] = receipt_contract(artifact)
        result["mobilePwaViewportRouteCount"] = artifact.get("route_count")
        result["mobilePwaViewportViewportCount"] = artifact.get("viewport_count")
        result["mobilePwaViewportRoutes"] = sorted(mobile_pwa_viewport_routes)
        result["mobilePwaViewportMissingRoutes"] = missing_mobile_pwa_viewport_routes
        result["mobilePwaViewportArtifactCurrentContractSatisfied"] = (
            mobile_pwa_viewport_artifact_current_contract_satisfied
        )
        result["mobilePwaViewportArtifactContractFailures"] = (
            mobile_pwa_viewport_artifact_failures
        )
        result["childReceipts"]["mobilePwaViewport"] = mobile_pwa_viewport
    if frontdoor_navigation:
        result["frontdoorNavigationStatus"] = frontdoor_navigation.get("status")
        result["frontdoorNavigationExitCode"] = frontdoor_navigation.get("exitCode")
        result["frontdoorNavigationArtifactDir"] = frontdoor_navigation.get("artifactDir")
        result["frontdoorNavigationMobileArtifactContract"] = receipt_contract(mobile_artifact)
        result["frontdoorNavigationLedgerArtifactContract"] = receipt_contract(ledger_artifact)
        result["frontdoorNavigationAnchorArtifactContract"] = receipt_contract(anchor_artifact)
        result["frontdoorNavigationHomepageLaneText"] = mobile_artifact.get("homepage_lane_text")
        result["frontdoorNavigationHomepageLaneExpected"] = expected_frontdoor_homepage_lane_text
        result["frontdoorNavigationHomepageLaneMatchesReleaseChannel"] = frontdoor_homepage_lane_matches_release_channel
        result["frontdoorNavigationPublicInstallTargets"] = mobile_artifact.get("public_install_targets")
        result["frontdoorNavigationDeviceRouting"] = mobile_artifact.get("device_routing")
        result["frontdoorNavigationPlaySurface"] = mobile_artifact.get("play_surface")
        result["frontdoorNavigationPlayAuthority"] = mobile_artifact.get("play_authority")
        result["frontdoorNavigationLiveSession"] = mobile_artifact.get("live_session")
        result["frontdoorNavigationPwaManifestPath"] = mobile_artifact.get("pwa_manifest_path")
        result["frontdoorNavigationLiveTurnCompanionShell"] = mobile_artifact.get("live_turn_companion_shell")
        result["frontdoorNavigationPrivateBrowserStateKeys"] = mobile_artifact.get("private_browser_state_keys")
        result["frontdoorNavigationPlayApiRequests"] = mobile_artifact.get("play_api_requests")
        result["frontdoorNavigationBlazorCircuitRequests"] = mobile_artifact.get("blazor_circuit_requests")
        result["frontdoorNavigationAnalyticsRequests"] = mobile_artifact.get("analytics_requests")
        result["frontdoorNavigationPrivateQueryRequests"] = mobile_artifact.get("private_query_requests")
        result["frontdoorNavigationPageErrors"] = mobile_artifact.get("page_errors")
        result["frontdoorNavigationMobileArtifactInstallContractSatisfied"] = mobile_artifact_privacy_contract_satisfied
        result["frontdoorNavigationLedgerRoute"] = ledger_artifact.get("route")
        result["frontdoorNavigationLedgerOpenMenuTargets"] = ledger_artifact.get("open_menu_targets")
        result["frontdoorNavigationLedgerGatedTargets"] = ledger_artifact.get("gated_targets")
        result["frontdoorNavigationLedgerPublicTargets"] = ledger_artifact.get("public_targets")
        result["frontdoorNavigationLedgerPrimary"] = ledger_artifact.get("ledger_primary")
        result["frontdoorNavigationLedgerArtifactCurrentContractSatisfied"] = ledger_artifact_current_contract_satisfied
        result["frontdoorNavigationAnchorEntryHadQuery"] = anchor_artifact.get("entry_had_query")
        result["frontdoorNavigationAnchorFinalPath"] = anchor_artifact.get("final_pathname")
        result["frontdoorNavigationAnchorFinalSearch"] = anchor_artifact.get("final_search")
        result["frontdoorNavigationAnchorFinalHash"] = anchor_artifact.get("final_hash")
        result["frontdoorNavigationAnchorFailureStage"] = anchor_artifact.get("failure_stage")
        result["frontdoorNavigationAnchorFailureType"] = anchor_artifact.get("failure_type")
        result["frontdoorNavigationAnchorArtifactCurrentContractSatisfied"] = frontdoor_anchor_current_contract_satisfied
        result["frontdoorNavigationProofClosureStatus"] = frontdoor_navigation.get("proofClosureStatus")
        result["frontdoorNavigationProofClosureSha256"] = frontdoor_navigation.get("proofClosureSha256")
        result["frontdoorNavigationPlaywrightRuntimeResolutionMode"] = (
            artifact_object(frontdoor_navigation.get("playwrightRuntime")).get(
                "resolutionMode"
            )
        )
        result["frontdoorNavigationPlaywrightPackageVersion"] = (
            artifact_object(frontdoor_navigation.get("playwrightRuntime")).get(
                "playwrightPackageVersion"
            )
        )
        result["frontdoorNavigationPlaywrightPackageJsonSha256"] = (
            artifact_object(frontdoor_navigation.get("playwrightRuntime")).get(
                "packageJsonSha256"
            )
        )
        result["frontdoorNavigationPlaywrightCliSha256"] = (
            artifact_object(frontdoor_navigation.get("playwrightRuntime")).get(
                "playwrightCliSha256"
            )
        )
        result["childReceipts"]["frontdoorNavigation"] = redact_private_identity(frontdoor_navigation)
    if pwa_offline_cache:
        artifact = pwa_offline_cache.get("artifact") if isinstance(pwa_offline_cache.get("artifact"), dict) else {}
        result["pwaOfflineCacheStatus"] = pwa_offline_cache.get("status")
        result["pwaOfflineCacheExitCode"] = pwa_offline_cache.get("exitCode")
        result["pwaOfflineCacheArtifactDir"] = pwa_offline_cache.get("artifactDir")
        result["pwaOfflineCacheArtifactContract"] = receipt_contract(artifact)
        result["pwaOfflineCacheCacheVersion"] = artifact.get("cache_version")
        result["pwaOfflineCacheNavigationPolicy"] = artifact.get("navigation_policy")
        result["pwaOfflineCachePrivateStateScope"] = artifact.get("private_state_scope")
        result["pwaOfflineCacheStaticPaths"] = artifact.get("static_paths")
        result["pwaOfflineCacheOfflineRoleFallbacks"] = artifact.get("offline_role_fallbacks")
        result["pwaOfflineCacheQueryBearingRequestsCached"] = artifact.get("query_bearing_requests_cached")
        result["pwaOfflineCachePrivateNavigationCached"] = artifact.get("private_navigation_cached")
        result["pwaOfflineCachePrivateApiCached"] = artifact.get("private_api_cached")
        result["pwaOfflineCachePersonalizedLedgerCached"] = artifact.get("personalized_ledger_cached")
        result["pwaOfflineCacheLegacyPrivateCachePrefixesPurged"] = artifact.get("legacy_private_cache_prefixes_purged")
        result["pwaOfflineCacheUnrelatedCachePreserved"] = artifact.get("unrelated_cache_preserved")
        result["childReceipts"]["pwaOfflineCache"] = pwa_offline_cache
    if blazor_new_runner_menu:
        artifact = artifact_object(blazor_new_runner_menu.get("artifact"))
        app_roster_transition = blazor_new_runner_app_roster_transition(artifact)
        workbench_fallback_route = blazor_new_runner_workbench_route(artifact)
        result["blazorNewRunnerMenuStatus"] = blazor_new_runner_menu.get("status")
        result["blazorNewRunnerMenuExitCode"] = blazor_new_runner_menu.get("exitCode")
        result["blazorNewRunnerMenuArtifactDir"] = blazor_new_runner_menu.get("artifactDir")
        result["blazorNewRunnerMenuArtifactContract"] = receipt_contract(artifact)
        result["blazorNewRunnerMenuAppResolvedHref"] = app_roster_transition.get("resolved_new_runner_href")
        result["blazorNewRunnerMenuAppFinalUrl"] = app_roster_transition.get("final_url")
        result["blazorNewRunnerMenuAppActiveWorkflow"] = app_roster_transition.get("active_workflow")
        result["blazorNewRunnerMenuAppCommand"] = app_roster_transition.get("command")
        result["blazorNewRunnerMenuAppStartupCommand"] = app_roster_transition.get("startup_command")
        result["blazorNewRunnerMenuAppDialogCount"] = app_roster_transition.get("dialog_count")
        result["blazorNewRunnerMenuAppHeadline"] = app_roster_transition.get("headline")
        result["blazorNewRunnerMenuAppWorkflowHeading"] = app_roster_transition.get("workflow_heading")
        result["blazorNewRunnerMenuAppFileMenuLockedDuringDialog"] = app_roster_transition.get("file_menu_locked_during_dialog")
        result["blazorNewRunnerMenuAppNewToolLockedDuringDialog"] = app_roster_transition.get("new_tool_locked_during_dialog")
        result["blazorNewRunnerMenuResolvedHref"] = artifact_value_with_fallback(artifact, "resolved_new_runner_href", workbench_fallback_route)
        result["blazorNewRunnerMenuFinalUrl"] = artifact_value_with_fallback(artifact, "final_url", workbench_fallback_route)
        result["blazorNewRunnerMenuReopenedDataCommand"] = artifact_value_with_fallback(artifact, "reopened_data_command", workbench_fallback_route)
        result["blazorNewRunnerMenuReopenedDataTab"] = artifact_value_with_fallback(artifact, "reopened_data_tab", workbench_fallback_route)
        result["blazorNewRunnerMenuDialogCount"] = artifact_value_with_fallback(artifact, "dialog_count", workbench_fallback_route)
        result["blazorNewRunnerMenuDialogTitle"] = artifact_value_with_fallback(artifact, "dialog_title", workbench_fallback_route)
        result["childReceipts"]["blazorNewRunnerMenu"] = blazor_new_runner_menu
    return result


def run_downloads_status_playwright(
    base_url: str,
    artifact_dir: Path,
    timeout_seconds: float,
    reuse_existing_artifact: bool = False,
    reuse_artifact_max_age_hours: float | None = DEFAULT_PLAYWRIGHT_REUSE_MAX_AGE_HOURS,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "DOWNLOADS_STATUS_E2E.generated.json"
    expected_contract = OPTIONAL_PLAYWRIGHT_CONTRACTS["downloadsStatusBrowser"]
    playwright_timeout_seconds = max(120, int(timeout_seconds) + 60)
    if reuse_existing_artifact:
        reused = maybe_reuse_playwright_artifact(
            artifact_path=artifact_path,
            expected_contract=expected_contract,
            base_url=base_url,
            timeout_seconds=playwright_timeout_seconds,
            reuse_artifact_max_age_hours=reuse_artifact_max_age_hours,
        )
        if reused is not None:
            reused["artifactDir"] = str(artifact_dir)
            return reused

    env = os.environ.copy()
    env["BASE_URL"] = base_url
    env["CHUMMER_COMPLETION_DIR"] = str(artifact_dir)
    command = [
        "npx",
        "playwright",
        "test",
        "tests/public/downloads-status.spec.ts",
        "--workers=1",
        "--reporter=line",
    ]
    exit_code, stdout, stderr, timed_out = run_playwright_command(command, env, playwright_timeout_seconds)
    artifact, artifact_load_status = load_json_with_status(artifact_path)
    artifact_contract = receipt_contract(artifact)
    artifact_pass = artifact_load_status == "loaded" and artifact.get("status") == "pass" and artifact_contract == expected_contract
    return {
        "status": "pass" if exit_code == 0 and artifact_pass else "fail",
        "exitCode": exit_code,
        "timedOut": timed_out,
        "timeoutSeconds": playwright_timeout_seconds,
        "artifactDir": str(artifact_dir),
        "artifactPath": str(artifact_path),
        "artifactLoadStatus": artifact_load_status,
        "artifactContract": artifact_contract,
        "expectedArtifactContract": expected_contract,
        "artifact": artifact,
        "artifactBaseUrlMatchesRequested": artifact_base_url_matches(artifact, base_url),
        "artifactReused": False,
        "playwrightExecuted": True,
        "stdoutTail": stdout[-2000:],
        "stderrTail": stderr[-2000:],
    }


def run_mobile_pwa_viewport_playwright(
    base_url: str,
    artifact_dir: Path,
    timeout_seconds: float,
    reuse_existing_artifact: bool = False,
    reuse_artifact_max_age_hours: float | None = DEFAULT_PLAYWRIGHT_REUSE_MAX_AGE_HOURS,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "MOBILE_PWA_VIEWPORT_SMOKE.generated.json"
    expected_contract = OPTIONAL_PLAYWRIGHT_CONTRACTS["mobilePwaViewport"]
    playwright_timeout_seconds = max(300, int(timeout_seconds) + 180)
    if reuse_existing_artifact:
        reused = maybe_reuse_playwright_artifact(
            artifact_path=artifact_path,
            expected_contract=expected_contract,
            base_url=base_url,
            timeout_seconds=playwright_timeout_seconds,
            reuse_artifact_max_age_hours=reuse_artifact_max_age_hours,
        )
        if reused is not None and mobile_pwa_viewport_artifact_matches_current_contract(
            artifact_object(reused.get("artifact")),
            expected_base_url=base_url,
        ):
            reused["artifactDir"] = str(artifact_dir)
            reused["artifactCurrentContractSatisfied"] = True
            reused["artifactContractFailures"] = []
            return reused

    env = os.environ.copy()
    env["BASE_URL"] = base_url
    env["CHUMMER_COMPLETION_DIR"] = str(artifact_dir)
    try:
        artifact_path.unlink()
    except FileNotFoundError:
        pass
    command = [
        "npx",
        "playwright",
        "test",
        "tests/public/mobile-pwa-viewport-smoke.spec.ts",
        "--workers=1",
        "--reporter=line",
    ]
    exit_code, stdout, stderr, timed_out = run_playwright_command(command, env, playwright_timeout_seconds)
    artifact, artifact_load_status = load_json_with_status(artifact_path)
    artifact_contract = receipt_contract(artifact)
    artifact_contract_failures = mobile_pwa_viewport_artifact_contract_failures(
        artifact,
        expected_base_url=base_url,
    )
    artifact_current_contract_satisfied = not artifact_contract_failures
    artifact_pass = (
        artifact_load_status == "loaded"
        and artifact_current_contract_satisfied
    )
    return {
        "status": "pass" if exit_code == 0 and artifact_pass else "fail",
        "exitCode": exit_code,
        "timedOut": timed_out,
        "timeoutSeconds": playwright_timeout_seconds,
        "artifactDir": str(artifact_dir),
        "artifactPath": str(artifact_path),
        "artifactLoadStatus": artifact_load_status,
        "artifactContract": artifact_contract,
        "expectedArtifactContract": expected_contract,
        "artifact": artifact,
        "artifactBaseUrlMatchesRequested": artifact_base_url_matches(artifact, base_url),
        "artifactCurrentContractSatisfied": artifact_current_contract_satisfied,
        "artifactContractFailures": artifact_contract_failures,
        "artifactReused": False,
        "playwrightExecuted": True,
        "stdoutTail": stdout[-2000:],
        "stderrTail": stderr[-2000:],
    }


def run_pwa_offline_cache_playwright(
    base_url: str,
    artifact_dir: Path,
    timeout_seconds: float,
    reuse_existing_artifact: bool = False,
    reuse_artifact_max_age_hours: float | None = DEFAULT_PLAYWRIGHT_REUSE_MAX_AGE_HOURS,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "PWA_OFFLINE_CACHE.generated.json"
    expected_contract = OPTIONAL_PLAYWRIGHT_CONTRACTS["pwaOfflineCache"]
    playwright_timeout_seconds = max(180, int(timeout_seconds) + 120)
    if reuse_existing_artifact:
        reused = maybe_reuse_playwright_artifact(
            artifact_path=artifact_path,
            expected_contract=expected_contract,
            base_url=base_url,
            timeout_seconds=playwright_timeout_seconds,
            reuse_artifact_max_age_hours=reuse_artifact_max_age_hours,
        )
        if reused is not None and pwa_offline_artifact_matches_privacy_contract(
            artifact_object(reused.get("artifact"))
        ):
            reused["artifactDir"] = str(artifact_dir)
            return reused

    env = os.environ.copy()
    env["BASE_URL"] = base_url
    env["CHUMMER_COMPLETION_DIR"] = str(artifact_dir)
    command = [
        "npx",
        "playwright",
        "test",
        "tests/public/pwa-offline-cache.spec.ts",
        "--workers=1",
        "--reporter=line",
    ]
    exit_code, stdout, stderr, timed_out = run_playwright_command(command, env, playwright_timeout_seconds)
    artifact, artifact_load_status = load_json_with_status(artifact_path)
    contract = receipt_contract(artifact)
    contract_ok = contract == expected_contract
    privacy_contract_ok = pwa_offline_artifact_matches_privacy_contract(artifact)
    return {
        "status": "pass" if exit_code == 0 and artifact_load_status == "loaded" and artifact.get("status") == "pass" and contract_ok and privacy_contract_ok else "fail",
        "exitCode": exit_code,
        "timedOut": timed_out,
        "timeoutSeconds": playwright_timeout_seconds,
        "artifactDir": str(artifact_dir),
        "artifactPath": str(artifact_path),
        "artifactLoadStatus": artifact_load_status,
        "artifactContract": contract,
        "expectedArtifactContract": expected_contract,
        "artifact": artifact,
        "artifactBaseUrlMatchesRequested": artifact_base_url_matches(artifact, base_url),
        "artifactPrivacyContractSatisfied": privacy_contract_ok,
        "artifactReused": False,
        "playwrightExecuted": True,
        "stdoutTail": stdout[-2000:],
        "stderrTail": stderr[-2000:],
    }


def run_blazor_new_runner_menu_playwright(
    base_url: str,
    artifact_dir: Path,
    timeout_seconds: float,
    reuse_existing_artifact: bool = False,
    reuse_artifact_max_age_hours: float | None = DEFAULT_PLAYWRIGHT_REUSE_MAX_AGE_HOURS,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "BLAZOR_NEW_RUNNER_MENU.generated.json"
    expected_contract = OPTIONAL_PLAYWRIGHT_CONTRACTS["blazorNewRunnerMenu"]
    playwright_timeout_seconds = max(180, int(timeout_seconds) + 120)
    if reuse_existing_artifact:
        reused = maybe_reuse_playwright_artifact(
            artifact_path=artifact_path,
            expected_contract=expected_contract,
            base_url=base_url,
            timeout_seconds=playwright_timeout_seconds,
            reuse_artifact_max_age_hours=reuse_artifact_max_age_hours,
        )
        if reused is not None:
            reused["artifactDir"] = str(artifact_dir)
            return reused

    env = os.environ.copy()
    env["BASE_URL"] = base_url
    env["CHUMMER_COMPLETION_DIR"] = str(artifact_dir)
    command = [
        "npx",
        "playwright",
        "test",
        "tests/public/blazor-new-runner-menu.spec.ts",
        "--workers=1",
        "--reporter=line",
    ]
    exit_code, stdout, stderr, timed_out = run_playwright_command(command, env, playwright_timeout_seconds)
    artifact, artifact_load_status = load_json_with_status(artifact_path)
    artifact_contract = receipt_contract(artifact)
    artifact_pass = artifact_load_status == "loaded" and artifact.get("status") == "pass" and artifact_contract == expected_contract
    return {
        "status": "pass" if exit_code == 0 and artifact_pass else "fail",
        "exitCode": exit_code,
        "timedOut": timed_out,
        "timeoutSeconds": playwright_timeout_seconds,
        "artifactDir": str(artifact_dir),
        "artifactPath": str(artifact_path),
        "artifactLoadStatus": artifact_load_status,
        "artifactContract": artifact_contract,
        "expectedArtifactContract": expected_contract,
        "artifact": artifact,
        "artifactBaseUrlMatchesRequested": artifact_base_url_matches(artifact, base_url),
        "artifactReused": False,
        "playwrightExecuted": True,
        "stdoutTail": stdout[-2000:],
        "stderrTail": stderr[-2000:],
    }


def run_frontdoor_navigation_playwright(
    base_url: str,
    artifact_dir: Path,
    timeout_seconds: float,
    reuse_existing_artifact: bool = False,
    reuse_artifact_max_age_hours: float | None = DEFAULT_PLAYWRIGHT_REUSE_MAX_AGE_HOURS,
    expected_homepage_lane_text: str = "",
    proof_closure_root: Path | None = None,
    expected_proof_closure: dict[str, Any] | None = None,
) -> dict[str, Any]:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    mobile_artifact_path = artifact_dir / "FRONTDOOR_MOBILE_LAUNCH.generated.json"
    ledger_artifact_path = artifact_dir / "BLACK_LEDGER_GLOBE_FRONTDOOR.generated.json"
    anchor_artifact_path = artifact_dir / "FRONTDOOR_MOBILE_ANCHOR_REDIRECT.generated.json"
    expected_mobile_contract = OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationMobile"]
    expected_ledger_contract = OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationLedger"]
    expected_anchor_contract = OPTIONAL_PLAYWRIGHT_CONTRACTS["frontdoorNavigationAnchor"]
    playwright_timeout_seconds = max(180, int(timeout_seconds) + 120)
    if proof_closure_root is None:
        return {
            "status": "fail",
            "reason": "frontdoor_playwright_proof_closure_unavailable",
            "exitCode": None,
            "timedOut": False,
            "timeoutSeconds": playwright_timeout_seconds,
            "artifactDir": str(artifact_dir),
            "proofClosureStatus": "fail",
            "proofClosureSha256": "",
            "playwrightExecuted": False,
            "artifactReused": False,
            "stdoutTail": "",
            "stderrTail": "frontdoor Playwright proof closure is required",
        }
    proof_closure_root = Path(
        os.path.abspath(os.fspath(Path(proof_closure_root).expanduser()))
    )
    try:
        proof_closure = validate_frontdoor_playwright_proof_closure(
            proof_closure_root
        )
        proof_closure_sha256 = str(
            proof_closure.get("aggregateSha256") or ""
        ).strip()
        if not isinstance(expected_proof_closure, dict) or (
            proof_closure != expected_proof_closure
        ):
            raise RuntimeError(
                "frontdoor Playwright proof closure does not match trusted build-info"
            )
        playwright_runtime = resolve_pinned_playwright_runtime(
            str(proof_closure.get("playwrightPackageVersion") or "").strip()
        )
    except (OSError, RuntimeError) as exc:
        return {
            "status": "fail",
            "reason": "frontdoor_playwright_proof_closure_invalid",
            "exitCode": None,
            "timedOut": False,
            "timeoutSeconds": playwright_timeout_seconds,
            "artifactDir": str(artifact_dir),
            "proofClosureStatus": "fail",
            "proofClosureSha256": "",
            "playwrightRuntime": {},
            "playwrightExecuted": False,
            "artifactReused": False,
            "stdoutTail": "",
            "stderrTail": str(exc),
        }

    def artifact_matches_proof_closure(artifact: dict[str, Any]) -> bool:
        return (
            str(artifact.get("proof_closure_sha256") or "").strip()
            == proof_closure_sha256
        )

    if reuse_existing_artifact and mobile_artifact_path.is_file() and ledger_artifact_path.is_file() and anchor_artifact_path.is_file():
        mobile_artifact, mobile_artifact_load_status = load_json_with_status(mobile_artifact_path)
        ledger_artifact, ledger_artifact_load_status = load_json_with_status(ledger_artifact_path)
        anchor_artifact, anchor_artifact_load_status = load_json_with_status(anchor_artifact_path)
        if (
            mobile_artifact_load_status == "loaded"
            and ledger_artifact_load_status == "loaded"
            and anchor_artifact_load_status == "loaded"
        ):
            mobile_contract = receipt_contract(mobile_artifact)
            ledger_contract = receipt_contract(ledger_artifact)
            anchor_contract = receipt_contract(anchor_artifact)
            mobile_generated_at = artifact_generated_at_text(mobile_artifact)
            ledger_generated_at = artifact_generated_at_text(ledger_artifact)
            anchor_generated_at = artifact_generated_at_text(anchor_artifact)
            mobile_age_hours = artifact_age_hours(mobile_artifact)
            ledger_age_hours = artifact_age_hours(ledger_artifact)
            anchor_age_hours = artifact_age_hours(anchor_artifact)
            anchor_current_contract = frontdoor_anchor_artifact_matches_current_contract(anchor_artifact)
            mobile_privacy_contract = frontdoor_mobile_artifact_matches_privacy_contract(mobile_artifact)
            ledger_current_contract = frontdoor_ledger_artifact_matches_current_contract(ledger_artifact)
            mobile_homepage_lane_text = str(mobile_artifact.get("homepage_lane_text") or "").strip()
            mobile_homepage_lane_matches_expected = (
                mobile_homepage_lane_text == expected_homepage_lane_text
                if expected_homepage_lane_text
                else True
            )
            mobile_fresh = (
                True
                if reuse_artifact_max_age_hours is None
                else mobile_age_hours is not None and mobile_age_hours <= reuse_artifact_max_age_hours
            )
            ledger_fresh = (
                True
                if reuse_artifact_max_age_hours is None
                else ledger_age_hours is not None and ledger_age_hours <= reuse_artifact_max_age_hours
            )
            anchor_fresh = (
                True
                if reuse_artifact_max_age_hours is None
                else anchor_age_hours is not None and anchor_age_hours <= reuse_artifact_max_age_hours
            )
            mobile_pass = (
                str(mobile_artifact.get("status") or "").strip().lower() == "pass"
                and mobile_contract == expected_mobile_contract
                and artifact_base_url_matches(mobile_artifact, base_url)
                and mobile_fresh
                and mobile_homepage_lane_matches_expected
                and mobile_privacy_contract
                and artifact_matches_proof_closure(mobile_artifact)
            )
            ledger_pass = (
                str(ledger_artifact.get("status") or "").strip().lower() == "pass"
                and ledger_contract == expected_ledger_contract
                and artifact_base_url_matches(ledger_artifact, base_url)
                and ledger_fresh
                and ledger_current_contract
                and artifact_matches_proof_closure(ledger_artifact)
            )
            anchor_pass = (
                str(anchor_artifact.get("status") or "").strip().lower() == "pass"
                and anchor_contract == expected_anchor_contract
                and artifact_base_url_matches(anchor_artifact, base_url)
                and anchor_fresh
                and anchor_current_contract
                and artifact_matches_proof_closure(anchor_artifact)
            )
            if mobile_pass and ledger_pass and anchor_pass:
                return {
                    "status": "pass",
                    "exitCode": 0,
                    "timedOut": False,
                    "timeoutSeconds": playwright_timeout_seconds,
                    "artifactDir": str(artifact_dir),
                    "mobileArtifactPath": str(mobile_artifact_path),
                    "ledgerArtifactPath": str(ledger_artifact_path),
                    "anchorArtifactPath": str(anchor_artifact_path),
                    "mobileArtifactLoadStatus": mobile_artifact_load_status,
                    "ledgerArtifactLoadStatus": ledger_artifact_load_status,
                    "anchorArtifactLoadStatus": anchor_artifact_load_status,
                    "mobileArtifactContract": mobile_contract,
                    "expectedMobileArtifactContract": expected_mobile_contract,
                    "ledgerArtifactContract": ledger_contract,
                    "expectedLedgerArtifactContract": expected_ledger_contract,
                    "anchorArtifactContract": anchor_contract,
                    "expectedAnchorArtifactContract": expected_anchor_contract,
                    "mobileArtifact": redact_private_identity(mobile_artifact),
                    "ledgerArtifact": redact_private_identity(ledger_artifact),
                    "anchorArtifact": redact_private_identity(anchor_artifact),
                    "mobileArtifactBaseUrlMatchesRequested": artifact_base_url_matches(mobile_artifact, base_url),
                    "ledgerArtifactBaseUrlMatchesRequested": artifact_base_url_matches(ledger_artifact, base_url),
                    "anchorArtifactBaseUrlMatchesRequested": artifact_base_url_matches(anchor_artifact, base_url),
                    "mobileArtifactGeneratedAtUtc": mobile_generated_at or None,
                    "ledgerArtifactGeneratedAtUtc": ledger_generated_at or None,
                    "anchorArtifactGeneratedAtUtc": anchor_generated_at or None,
                    "mobileArtifactAgeHours": mobile_age_hours,
                    "ledgerArtifactAgeHours": ledger_age_hours,
                    "anchorArtifactAgeHours": anchor_age_hours,
                    "mobileArtifactFresh": mobile_fresh,
                    "ledgerArtifactFresh": ledger_fresh,
                    "anchorArtifactFresh": anchor_fresh,
                    "mobileHomepageLaneMatchesExpected": mobile_homepage_lane_matches_expected,
                    "mobileArtifactPrivacyContractSatisfied": mobile_privacy_contract,
                    "ledgerArtifactCurrentContractSatisfied": ledger_current_contract,
                    "anchorArtifactCurrentContractSatisfied": anchor_current_contract,
                    "proofClosureStatus": "pass",
                    "proofClosureSha256": proof_closure_sha256,
                    "proofClosure": proof_closure,
                    "playwrightRuntime": playwright_runtime,
                    "artifactMaxAgeHours": reuse_artifact_max_age_hours,
                    "artifactReused": True,
                    "playwrightExecuted": False,
                    "stdoutTail": "",
                    "stderrTail": "",
                }

    env = os.environ.copy()
    env["BASE_URL"] = base_url
    env["CHUMMER_COMPLETION_DIR"] = str(artifact_dir)
    env["CHUMMER_FRONTDOOR_PLAYWRIGHT_PROOF_CLOSURE_SHA256"] = (
        proof_closure_sha256
    )
    env["CHUMMER_PLAYWRIGHT_EXECUTION_ROOT"] = str(proof_closure_root)
    node_modules_root = str(playwright_runtime["nodeModulesRoot"])
    # The proof subprocess may inherit operational browser settings, but not
    # Node's ambient preloading/module-resolution hooks.  Its executable specs
    # and dependency root are selected by the validated closure above.
    for untrusted_code_loading_name in (
        "CHUMMER_PLAYWRIGHT_BIN",
        "CHUMMER_PLAYWRIGHT_NODE_MODULES_ROOT",
        "CHUMMER_PLAYWRIGHT_PACKAGE_SPEC",
        "NODE_OPTIONS",
        "NODE_PATH",
        "PW_TEST_REPORTER",
        "PW_TEST_SOURCE_TRANSFORM",
        "PW_TEST_SOURCE_TRANSFORM_SCOPE",
    ):
        env.pop(untrusted_code_loading_name, None)
    env["NODE_PATH"] = node_modules_root
    for artifact_path in (mobile_artifact_path, ledger_artifact_path, anchor_artifact_path):
        try:
            artifact_path.unlink()
        except FileNotFoundError:
            pass
    command = [
        *playwright_runtime["commandPrefix"],
        "test",
        "tests/public/frontdoor-mobile-launch.spec.ts",
        "tests/public/black-ledger-frontdoor.spec.ts",
        "--config=playwright.config.ts",
        f"--output={artifact_dir / '.playwright-output'}",
        "--workers=1",
        "--reporter=line",
    ]
    exit_code, stdout, stderr, timed_out = run_playwright_command(command, env, playwright_timeout_seconds)
    mobile_artifact, mobile_artifact_load_status = load_json_with_status(mobile_artifact_path)
    ledger_artifact, ledger_artifact_load_status = load_json_with_status(ledger_artifact_path)
    anchor_artifact, anchor_artifact_load_status = load_json_with_status(anchor_artifact_path)
    mobile_contract = receipt_contract(mobile_artifact)
    ledger_contract = receipt_contract(ledger_artifact)
    anchor_contract = receipt_contract(anchor_artifact)
    mobile_contract_ok = mobile_contract == expected_mobile_contract
    ledger_contract_ok = ledger_contract == expected_ledger_contract
    anchor_contract_ok = anchor_contract == expected_anchor_contract
    mobile_privacy_contract = frontdoor_mobile_artifact_matches_privacy_contract(mobile_artifact)
    ledger_current_contract = frontdoor_ledger_artifact_matches_current_contract(ledger_artifact)
    anchor_current_contract = frontdoor_anchor_artifact_matches_current_contract(anchor_artifact)
    mobile_base_url_matches = artifact_base_url_matches(mobile_artifact, base_url)
    ledger_base_url_matches = artifact_base_url_matches(ledger_artifact, base_url)
    anchor_base_url_matches = artifact_base_url_matches(anchor_artifact, base_url)
    mobile_homepage_lane_text = str(mobile_artifact.get("homepage_lane_text") or "").strip()
    mobile_homepage_lane_matches_expected = (
        mobile_homepage_lane_text == expected_homepage_lane_text
        if expected_homepage_lane_text
        else True
    )
    proof_passed = (
        exit_code == 0
        and mobile_artifact_load_status == "loaded"
        and ledger_artifact_load_status == "loaded"
        and anchor_artifact_load_status == "loaded"
        and mobile_artifact.get("status") == "pass"
        and ledger_artifact.get("status") == "pass"
        and anchor_artifact.get("status") == "pass"
        and mobile_contract_ok
        and ledger_contract_ok
        and anchor_contract_ok
        and mobile_base_url_matches
        and ledger_base_url_matches
        and anchor_base_url_matches
        and mobile_homepage_lane_matches_expected
        and mobile_privacy_contract
        and ledger_current_contract
        and anchor_current_contract
        and artifact_matches_proof_closure(mobile_artifact)
        and artifact_matches_proof_closure(ledger_artifact)
        and artifact_matches_proof_closure(anchor_artifact)
    )
    return {
        "status": "pass" if proof_passed else "fail",
        "exitCode": exit_code,
        "timedOut": timed_out,
        "timeoutSeconds": playwright_timeout_seconds,
        "artifactDir": str(artifact_dir),
        "mobileArtifactPath": str(mobile_artifact_path),
        "ledgerArtifactPath": str(ledger_artifact_path),
        "anchorArtifactPath": str(anchor_artifact_path),
        "mobileArtifactLoadStatus": mobile_artifact_load_status,
        "ledgerArtifactLoadStatus": ledger_artifact_load_status,
        "anchorArtifactLoadStatus": anchor_artifact_load_status,
        "mobileArtifactContract": mobile_contract,
        "expectedMobileArtifactContract": expected_mobile_contract,
        "ledgerArtifactContract": ledger_contract,
        "expectedLedgerArtifactContract": expected_ledger_contract,
        "anchorArtifactContract": anchor_contract,
        "expectedAnchorArtifactContract": expected_anchor_contract,
        "mobileArtifact": redact_private_identity(mobile_artifact),
        "ledgerArtifact": redact_private_identity(ledger_artifact),
        "anchorArtifact": redact_private_identity(anchor_artifact),
        "mobileArtifactBaseUrlMatchesRequested": mobile_base_url_matches,
        "ledgerArtifactBaseUrlMatchesRequested": ledger_base_url_matches,
        "anchorArtifactBaseUrlMatchesRequested": anchor_base_url_matches,
        "mobileHomepageLaneMatchesExpected": mobile_homepage_lane_matches_expected,
        "mobileArtifactPrivacyContractSatisfied": mobile_privacy_contract,
        "ledgerArtifactCurrentContractSatisfied": ledger_current_contract,
        "anchorArtifactCurrentContractSatisfied": anchor_current_contract,
        "proofClosureStatus": "pass",
        "proofClosureSha256": proof_closure_sha256,
        "proofClosure": proof_closure,
        "playwrightRuntime": playwright_runtime,
        "artifactReused": False,
        "playwrightExecuted": True,
        "stdoutTail": redact_private_identity(stdout[-2000:]),
        "stderrTail": redact_private_identity(stderr[-2000:]),
    }


def orchestrated_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the non-mutating public-edge postdeploy gate.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output")
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--skip-preflight", action="store_true", help="Use only for post-fact canonical checks where local build lanes are irrelevant.")
    parser.add_argument("--strict-preflight", action="store_true", help="Run the child public-edge preflight without foreign or stale build-lock allowances.")
    parser.add_argument("--require-downloads-status-playwright", action="store_true", help="Require the focused browser proof for /downloads and /status.")
    parser.add_argument("--playwright-artifact-dir", help="Artifact directory for the downloads-status Playwright proof.")
    parser.add_argument("--require-mobile-pwa-viewport-playwright", action="store_true", help="Require the focused browser proof for core mobile PWA route viewports.")
    parser.add_argument("--mobile-pwa-viewport-artifact-dir", help="Artifact directory for the mobile PWA viewport Playwright proof.")
    parser.add_argument("--require-pwa-offline-cache-playwright", action="store_true", help="Require the focused browser proof for offline Player and GM mobile PWA routes.")
    parser.add_argument("--pwa-offline-cache-artifact-dir", help="Artifact directory for the PWA offline cache Playwright proof.")
    parser.add_argument("--require-blazor-new-runner-menu-playwright", action="store_true", help="Require the focused browser proof for the Blazor File > New runner workbench route.")
    parser.add_argument("--blazor-new-runner-menu-artifact-dir", help="Artifact directory for the Blazor new-runner Playwright proof.")
    parser.add_argument("--require-frontdoor-navigation-playwright", action="store_true", help="Require the focused browser proof for front-door Build/Play navigation and Black Ledger de-emphasis.")
    parser.add_argument("--frontdoor-navigation-artifact-dir", help="Artifact directory for the front-door navigation Playwright proof.")
    parser.add_argument("--reuse-existing-playwright-artifacts", action="store_true", help="Reuse existing Playwright-generated receipts from the supplied artifact directories instead of rerunning browser proofs.")
    parser.add_argument("--reuse-artifact-max-age-hours", type=float, default=DEFAULT_PLAYWRIGHT_REUSE_MAX_AGE_HOURS, help="Maximum age for reused Playwright receipts before the browser proof must rerun.")
    parser.add_argument("--release-channel-receipt", default=str(DEFAULT_RELEASE_CHANNEL_RECEIPT), help="Release-channel receipt used to require visible downloads version parity.")
    parser.add_argument(
        "--release-channel-receipt-sha256",
        default="",
        help="Independent lowercase SHA-256 for the release-channel receipt used by strict preflight.",
    )
    parser.add_argument(
        "--public-projection-snapshot-root",
        default="",
        help="Authenticated CURRENT public projection root used by strict preflight.",
    )
    parser.add_argument(
        "--runtime-proof-bind-source-sha256",
        default="",
        help="Independent lowercase SHA-256 for the CURRENT Hub runtime proof output.",
    )
    parser.add_argument("--skip-release-version-match", action="store_true", help="Do not require public visible Version text to match the release-channel version.")
    parser.add_argument("--overlay-root", default="", help="Mounted /app overlay root that public-edge preflight must validate.")
    parser.add_argument(
        "--expected-build-info",
        default="",
        help="Trusted active overlay build-info used to derive the expected full deployment digest.",
    )
    parser.add_argument(
        "--expected-full-deployment-digest-sha256",
        default="",
        help="Independently selected expected full deployment digest; cross-checked against preflight when it runs.",
    )
    parser.add_argument(
        "--expected-pwa-asset-inventory-sha256",
        default="",
        help="Sealed preflight PWA asset inventory digest; mandatory when preflight is skipped.",
    )
    args = parser.parse_args(argv)
    if args.skip_preflight and args.strict_preflight:
        parser.error("--strict-preflight cannot be combined with --skip-preflight")
    if not args.skip_preflight:
        if not args.public_projection_snapshot_root:
            parser.error(
                "postdeploy preflight requires --public-projection-snapshot-root"
            )
        if re.fullmatch(r"[0-9a-f]{64}", args.runtime_proof_bind_source_sha256) is None:
            parser.error(
                "postdeploy preflight requires --runtime-proof-bind-source-sha256"
            )
        if re.fullmatch(r"[0-9a-f]{64}", args.release_channel_receipt_sha256) is None:
            parser.error(
                "postdeploy preflight requires --release-channel-receipt-sha256"
            )
    release_channel = {} if args.skip_release_version_match else load_optional_json(Path(args.release_channel_receipt))
    expected_release_version = "" if args.skip_release_version_match else str(release_channel.get("version") or "").strip()
    expected_release_status = "" if args.skip_release_version_match else str(release_channel.get("status") or "").strip()
    expected_release_channel = "" if args.skip_release_version_match else str(
        release_channel.get("channel") or release_channel.get("channelId") or release_channel.get("channel_id") or ""
    ).strip()
    expected_release_supportability_state = "" if args.skip_release_version_match else str(
        release_channel.get("supportabilityState") or release_channel.get("supportability_state") or ""
    ).strip()
    expected_release_rollout_state = "" if args.skip_release_version_match else str(
        release_channel.get("rolloutState") or release_channel.get("rollout_state") or ""
    ).strip()
    expected_frontdoor_homepage_lane = expected_homepage_lane_text(
        expected_release_status,
        expected_release_version,
        expected_release_channel,
        expected_release_supportability_state,
        expected_release_rollout_state,
    ) or ""
    overlay_root = resolve_public_edge_overlay_root(args.overlay_root)
    expected_source_root = Path(
        os.environ.get("CHUMMER_RUN_SERVICES_SOURCE") or RUN_SERVICES_ROOT
    ).resolve()

    with tempfile.TemporaryDirectory(prefix="chummer-public-edge-postdeploy-") as temp_dir:
        temp = Path(temp_dir)
        if args.skip_preflight:
            preflight = {
                "contractName": "chummer.public_edge_deploy_preflight.v1",
                "status": "pass",
                "activeLockCount": 0,
                "staleForeignLockCount": 0,
                "staleLookingLockCount": 0,
                "staleForeignLocksIgnored": False,
                "allowStaleForeignBuildLocks": False,
                "skipped": True,
                "findings": [],
            }
        else:
            preflight_command = [
                sys.executable,
                "scripts/check_public_edge_deploy_preflight.py",
                "--overlay-root",
                str(overlay_root),
                "--public-projection-snapshot-root",
                args.public_projection_snapshot_root,
                "--runtime-proof-bind-source-sha256",
                args.runtime_proof_bind_source_sha256,
                "--release-channel-receipt",
                args.release_channel_receipt,
                "--release-channel-receipt-sha256",
                args.release_channel_receipt_sha256,
            ]
            if not args.strict_preflight:
                preflight_command[2:2] = [
                    "--allow-foreign-build-locks",
                    "--allow-stale-foreign-build-locks",
                ]
            preflight = run_child(
                preflight_command,
                temp / "preflight.json",
                allow_failure=True,
            )

        configured_expected_digest = str(
            args.expected_full_deployment_digest_sha256 or ""
        ).strip()
        configured_pwa_inventory_digest = str(
            args.expected_pwa_asset_inventory_sha256 or ""
        ).strip()
        if configured_pwa_inventory_digest and re.fullmatch(
            r"[0-9a-f]{64}", configured_pwa_inventory_digest
        ) is None:
            parser.error("configured PWA asset inventory digest must be lowercase SHA-256")
        if configured_expected_digest:
            try:
                configured_expected_digest = require_full_deployment_digest(
                    configured_expected_digest,
                    label="configured full deployment digest",
                )
            except RuntimeError as exc:
                parser.error(str(exc))
        if args.skip_preflight:
            if not configured_pwa_inventory_digest:
                parser.error(
                    "--skip-preflight requires --expected-pwa-asset-inventory-sha256 from a sealed preflight receipt"
                )
            expected_pwa_asset_inventory_sha256 = configured_pwa_inventory_digest
            if configured_expected_digest:
                expected_full_deployment_digest_sha256 = configured_expected_digest
                if args.expected_build_info:
                    try:
                        build_info_digest = load_expected_full_deployment_digest(
                            Path(args.expected_build_info),
                            source_root=expected_source_root,
                            overlay_root=overlay_root,
                        )
                    except RuntimeError as exc:
                        parser.error(str(exc))
                    if build_info_digest != configured_expected_digest:
                        parser.error(
                            "configured full deployment digest does not match trusted build-info"
                        )
            else:
                expected_build_info_path = (
                    Path(args.expected_build_info)
                    if args.expected_build_info
                    else overlay_root / OVERLAY_BUILD_INFO_RELATIVE_PATH
                )
                try:
                    expected_full_deployment_digest_sha256 = (
                        load_expected_full_deployment_digest(
                            expected_build_info_path,
                            source_root=expected_source_root,
                            overlay_root=overlay_root,
                        )
                    )
                except RuntimeError as exc:
                    parser.error(str(exc))
        else:
            preflight_pwa = preflight.get("publicPwaStaticProof")
            preflight_pwa_inventory = (
                preflight_pwa.get("assetDigestInventory")
                if isinstance(preflight_pwa, dict)
                and isinstance(preflight_pwa.get("assetDigestInventory"), dict)
                else {}
            )
            expected_pwa_asset_inventory_sha256 = str(
                preflight_pwa_inventory.get("sha256") or ""
            ).strip()
            if re.fullmatch(
                r"[0-9a-f]{64}", expected_pwa_asset_inventory_sha256
            ) is None:
                parser.error("preflight PWA asset inventory digest is missing or invalid")
            if (
                configured_pwa_inventory_digest
                and configured_pwa_inventory_digest
                != expected_pwa_asset_inventory_sha256
            ):
                parser.error(
                    "configured PWA asset inventory digest does not match the sealed preflight"
                )
            preflight_binding = preflight.get("overlayBuildInfoSourceFingerprint")
            preflight_digest = (
                preflight_binding.get("expectedFullDeploymentDigestSha256")
                if isinstance(preflight_binding, dict)
                else None
            )
            try:
                expected_full_deployment_digest_sha256 = require_full_deployment_digest(
                    preflight_digest,
                    label="preflight full deployment digest",
                )
            except RuntimeError as exc:
                parser.error(str(exc))
            if (
                configured_expected_digest
                and configured_expected_digest
                != expected_full_deployment_digest_sha256
            ):
                parser.error(
                    "configured full deployment digest does not match the trusted preflight"
                )
            if args.expected_build_info:
                try:
                    build_info_digest = load_expected_full_deployment_digest(
                        Path(args.expected_build_info),
                        source_root=expected_source_root,
                        overlay_root=overlay_root,
                    )
                except RuntimeError as exc:
                    parser.error(str(exc))
                if build_info_digest != expected_full_deployment_digest_sha256:
                    parser.error(
                        "trusted build-info full deployment digest does not match preflight"
                    )

        expected_frontdoor_playwright_proof_closure: dict[str, Any] = {}
        if args.require_frontdoor_navigation_playwright:
            trusted_build_info_path = (
                Path(args.expected_build_info)
                if args.expected_build_info
                else overlay_root / OVERLAY_BUILD_INFO_RELATIVE_PATH
            )
            try:
                trusted_deployment_identity = load_expected_deployment_identity(
                    trusted_build_info_path,
                    source_root=expected_source_root,
                    overlay_root=overlay_root,
                )
            except RuntimeError as exc:
                parser.error(str(exc))
            if (
                trusted_deployment_identity["fullDeploymentDigestSha256"]
                != expected_full_deployment_digest_sha256
            ):
                parser.error(
                    "trusted build-info full deployment digest does not match selected deployment identity"
                )
            expected_frontdoor_playwright_proof_closure = dict(
                trusted_deployment_identity["frontdoorPlaywrightProofClosure"]
            )

        downloads_command = [
            sys.executable,
            "scripts/verify_downloads_version_marker.py",
            "--base-url",
            args.base_url,
            "--timeout-seconds",
            str(args.timeout_seconds),
            "--release-channel-receipt",
            args.release_channel_receipt,
        ]
        if args.skip_release_version_match:
            downloads_command.append("--skip-release-version-match")
        else:
            downloads_command.append("--allow-non-launch-supported-release-channel")
        downloads = run_child(
            downloads_command,
            temp / "downloads.json",
            allow_failure=True,
        )
        pwa_static = run_child(
            [
                sys.executable,
                "scripts/verify_public_pwa_static_assets.py",
                "--base-url",
                args.base_url,
                "--timeout-seconds",
                str(args.timeout_seconds),
                "--expected-full-deployment-digest-sha256",
                expected_full_deployment_digest_sha256,
                "--expected-asset-inventory-sha256",
                expected_pwa_asset_inventory_sha256,
            ],
            temp / "pwa-static.json",
            allow_failure=True,
        )
        mobile_ledger = run_child(
            [
                sys.executable,
                "scripts/verify_mobile_pwa_ledger_boundary.py",
                "--base-url",
                args.base_url,
                "--timeout-seconds",
                str(args.timeout_seconds),
            ],
            temp / "mobile-ledger.json",
            allow_failure=True,
        )
        ready_mobile_handoff = run_child(
            [
                sys.executable,
                "scripts/verify_ready_mobile_handoff_contract.py",
                "--base-url",
                args.base_url,
                "--timeout-seconds",
                str(args.timeout_seconds),
            ],
            temp / "ready-mobile-handoff.json",
            allow_failure=True,
        )
        participate_iframe_shell = run_child(
            [
                sys.executable,
                "scripts/verify_participate_iframe_shell.py",
                "--base-url",
                args.base_url,
                "--timeout-seconds",
                str(args.timeout_seconds),
            ],
            temp / "participate-iframe-shell.json",
            allow_failure=True,
        )
        online_launch = run_child(
            [
                sys.executable,
                "scripts/verify_chummer_online_launch.py",
                "--base-url",
                args.base_url,
            ],
            temp / "online-launch.json",
            allow_failure=True,
        )

    downloads_status_browser = None
    if args.require_downloads_status_playwright:
        artifact_dir = Path(args.playwright_artifact_dir) if args.playwright_artifact_dir else Path(tempfile.mkdtemp(prefix="chummer-downloads-status-browser-"))
        downloads_status_browser = run_downloads_status_playwright(
            args.base_url.rstrip("/"),
            artifact_dir,
            args.timeout_seconds,
            reuse_existing_artifact=args.reuse_existing_playwright_artifacts,
            reuse_artifact_max_age_hours=args.reuse_artifact_max_age_hours,
        )
    mobile_pwa_viewport = None
    if args.require_mobile_pwa_viewport_playwright:
        artifact_dir = Path(args.mobile_pwa_viewport_artifact_dir) if args.mobile_pwa_viewport_artifact_dir else Path(tempfile.mkdtemp(prefix="chummer-mobile-pwa-viewport-"))
        mobile_pwa_viewport = run_mobile_pwa_viewport_playwright(
            args.base_url.rstrip("/"),
            artifact_dir,
            args.timeout_seconds,
            reuse_existing_artifact=args.reuse_existing_playwright_artifacts,
            reuse_artifact_max_age_hours=args.reuse_artifact_max_age_hours,
        )
    pwa_offline_cache = None
    if args.require_pwa_offline_cache_playwright:
        artifact_dir = Path(args.pwa_offline_cache_artifact_dir) if args.pwa_offline_cache_artifact_dir else Path(tempfile.mkdtemp(prefix="chummer-pwa-offline-cache-"))
        pwa_offline_cache = run_pwa_offline_cache_playwright(
            args.base_url.rstrip("/"),
            artifact_dir,
            args.timeout_seconds,
            reuse_existing_artifact=args.reuse_existing_playwright_artifacts,
            reuse_artifact_max_age_hours=args.reuse_artifact_max_age_hours,
        )
    blazor_new_runner_menu = None
    if args.require_blazor_new_runner_menu_playwright:
        artifact_dir = Path(args.blazor_new_runner_menu_artifact_dir) if args.blazor_new_runner_menu_artifact_dir else Path(tempfile.mkdtemp(prefix="chummer-blazor-new-runner-menu-"))
        blazor_new_runner_menu = run_blazor_new_runner_menu_playwright(
            args.base_url.rstrip("/"),
            artifact_dir,
            args.timeout_seconds,
            reuse_existing_artifact=args.reuse_existing_playwright_artifacts,
            reuse_artifact_max_age_hours=args.reuse_artifact_max_age_hours,
        )
    frontdoor_navigation = None
    if args.require_frontdoor_navigation_playwright:
        artifact_dir = Path(args.frontdoor_navigation_artifact_dir) if args.frontdoor_navigation_artifact_dir else Path(tempfile.mkdtemp(prefix="chummer-frontdoor-navigation-"))
        frontdoor_navigation = run_frontdoor_navigation_playwright(
            args.base_url.rstrip("/"),
            artifact_dir,
            args.timeout_seconds,
            reuse_existing_artifact=args.reuse_existing_playwright_artifacts,
            reuse_artifact_max_age_hours=args.reuse_artifact_max_age_hours,
            expected_homepage_lane_text=expected_frontdoor_homepage_lane,
            proof_closure_root=(
                overlay_root / FRONTDOOR_PLAYWRIGHT_PROOF_CLOSURE_RELATIVE_ROOT
            ),
            expected_proof_closure=expected_frontdoor_playwright_proof_closure,
        )
    role_alias_routes = probe_role_alias_routes(args.base_url.rstrip("/"), args.timeout_seconds)

    result = compose_status(
        preflight,
        downloads,
        pwa_static,
        mobile_ledger,
        ready_mobile_handoff,
        participate_iframe_shell,
        downloads_status_browser,
        mobile_pwa_viewport,
        frontdoor_navigation,
        pwa_offline_cache,
        blazor_new_runner_menu,
        expected_release_version,
        False,
        role_alias_routes,
        online_launch=online_launch,
        expected_full_deployment_digest_sha256=(
            expected_full_deployment_digest_sha256
        ),
    )
    result["skipPreflight"] = args.skip_preflight
    result["skipReleaseVersionMatch"] = args.skip_release_version_match
    result["strictPreflight"] = args.strict_preflight and args.skip_preflight is False
    result["strictInvocation"] = (args.skip_preflight is False and args.skip_release_version_match is False)
    result["strictNoAllowanceInvocation"] = (
        args.skip_preflight is False
        and args.skip_release_version_match is False
        and args.strict_preflight is True
    )
    result["expectedFullDeploymentDigestSha256"] = (
        expected_full_deployment_digest_sha256
    )
    result["expectedPwaAssetInventorySha256"] = (
        expected_pwa_asset_inventory_sha256
    )
    pwa_inventory_receipt = (
        pwa_static.get("assetDigestInventory")
        if isinstance(pwa_static.get("assetDigestInventory"), dict)
        else {}
    )
    pwa_inventory_anchor_matches = (
        pwa_inventory_receipt.get("sealedExpectedSha256")
        == expected_pwa_asset_inventory_sha256
        and pwa_inventory_receipt.get("matchesExpected") is True
        and pwa_inventory_receipt.get("sourceStable") is True
    )
    result["pwaAssetInventoryAnchorMatches"] = pwa_inventory_anchor_matches
    if not pwa_inventory_anchor_matches:
        result["failures"].append(
            "PWA asset inventory did not remain bound to the sealed preflight digest"
        )
        result["status"] = "fail"
    if not args.skip_release_version_match and not expected_release_version:
        result["expectedReleaseVersion"] = ""
        result["visibleVersionMatchesReleaseChannel"] = False
        result["statusRedirectVersionMatchesReleaseChannel"] = False
        result["failures"].append("release channel version is missing")
        result["status"] = "fail"
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if result["status"] == "pass" else 1

def main(argv: list[str] | None = None) -> int:
    """Run the orchestrated flagship gate, with the upstream direct verifier available explicitly."""
    effective_argv = list(sys.argv[1:] if argv is None else argv)
    if "--self-contained-direct" in effective_argv:
        direct_argv = [value for value in effective_argv if value != "--self-contained-direct"]
        return self_contained_main(direct_argv)
    return orchestrated_main(effective_argv)


if __name__ == "__main__":
    raise SystemExit(main())
