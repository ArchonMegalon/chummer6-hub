#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from writable_temp_root import subprocess_env
from verify_windows_installer_visual_audit_intake_request import (
    verify as verify_windows_visual_intake_request_receipt,
)


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = ROOT.parent
VERIFIER_PATH = Path(__file__).resolve()
PUBLISHED_ROOT = ROOT / ".codex-studio" / "published"


def downloads_root_has_promoted_windows_bytes(downloads_root: Path) -> bool:
    def norm(value: Any) -> str:
        return str(value or "").strip().lower()

    manifest_path = downloads_root / "RELEASE_CHANNEL.generated.json"
    files_root = downloads_root / "files"
    if not manifest_path.is_file() or not files_root.is_dir():
        return False
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return False
    rows = payload.get("artifacts") or payload.get("downloads") or []
    if not isinstance(rows, list):
        return False
    for item in rows:
        if not isinstance(item, dict):
            continue
        artifact_id = norm(item.get("artifactId") or item.get("id"))
        platform = norm(item.get("platform"))
        file_name = str(item.get("fileName") or "").strip()
        if not file_name:
            continue
        if (artifact_id == "avalonia-win-x64-installer" or platform == "windows") and (files_root / file_name).is_file():
            return True
    return False


def resolve_default_downloads_root() -> Path:
    explicit = (
        os.environ.get("CHUMMER_WINDOWS_INSTALLER_VISUAL_AUDIT_DOWNLOADS_ROOT")
        or os.environ.get("CHUMMER_RELEASE_DOWNLOADS_ROOT")
        or os.environ.get("CHUMMER_PORTAL_DOWNLOADS_ROOT")
    )
    if explicit:
        return Path(explicit).expanduser()

    candidates = [
        ROOT / "Chummer.Portal" / "downloads",
        ROOT.parent / "chummer.run-services" / "Chummer.Portal" / "downloads",
        Path("/docker/chummercomplete/chummer.run-services/Chummer.Portal/downloads"),
        Path("/docker/chummercomplete/chummer-presentation/Docker/Downloads"),
    ]
    for candidate in candidates:
        if downloads_root_has_promoted_windows_bytes(candidate):
            return candidate
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


DEFAULT_DOWNLOADS_ROOT = resolve_default_downloads_root()
DEFAULT_OUTPUT = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"
DEFAULT_SOURCE = DEFAULT_DOWNLOADS_ROOT / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
DEFAULT_STARTUP_RECEIPT = DEFAULT_DOWNLOADS_ROOT / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
DEFAULT_PORTAL_RELEASE_CHANNEL = DEFAULT_DOWNLOADS_ROOT / "RELEASE_CHANNEL.generated.json"
DEFAULT_HUB_REGISTRY_ROOT = Path(
    os.environ.get("CHUMMER_HUB_REGISTRY_ROOT")
    or WORKSPACE_ROOT / "chummer-hub-registry"
)
DEFAULT_HUB_RELEASE_CHANNEL = (
    DEFAULT_HUB_REGISTRY_ROOT / ".codex-studio" / "published" / "RELEASE_CHANNEL.generated.json"
)


def select_authoritative_release_channel_path(
    hub_release_channel: Path,
    portal_release_channel: Path,
) -> Path:
    """Use registry truth whenever it exists; the portal is only a fallback projection."""

    return hub_release_channel if hub_release_channel.is_file() else portal_release_channel


DEFAULT_RELEASE_CHANNEL = select_authoritative_release_channel_path(
    DEFAULT_HUB_RELEASE_CHANNEL,
    DEFAULT_PORTAL_RELEASE_CHANNEL,
)
DEFAULT_WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
DEFAULT_WINDOWS_VISUAL_AUDIT_AUTO_IMPORT = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
DEFAULT_WINDOWS_WATCHER_STATE = ROOT / ".state" / "windows_installer_gold_proof_watcher.generated.json"
AUTO_IMPORT_SIDE_EFFECTS_PAUSE_FLAG = ROOT / ".state" / "windows_installer_visual_audit_paused.flag"
DEFAULT_TELEGRAM_TEXT_DELIVERY_ROOT = WORKSPACE_ROOT / "_completion" / "telegram_text_delivery"
REQUIRED_SURFACES = ("install-progress", "completion")
CAPTURE_SCRIPT = "scripts/capture_windows_installer_visual_audit.ps1"
GOLD_PROOF_SCRIPT = "scripts/capture_windows_installer_gold_proof.ps1"
CONTRACT_NAME = "chummer.windows_installer_visual_audit"
VERIFIER_EXECUTION_MODE = "observational_default"


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> tuple[dict[str, Any], str]:
    if not path.is_file():
        return {}, "missing"
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}, "invalid"
    if not isinstance(loaded, dict):
        return {}, "invalid"
    return loaded, "loaded"


def auto_import_side_effects_paused() -> bool:
    return AUTO_IMPORT_SIDE_EFFECTS_PAUSE_FLAG.is_file()


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def is_sha256(value: Any) -> bool:
    normalized_value = str(value or "").strip().lower()
    return len(normalized_value) == 64 and all(
        character in "0123456789abcdef" for character in normalized_value
    )


def verifier_binding(expected_sha256: str = "") -> tuple[dict[str, Any], list[str]]:
    normalized_expected = str(expected_sha256 or "").strip().lower()
    actual_sha256 = sha256_file(VERIFIER_PATH)
    expected_is_valid = not normalized_expected or is_sha256(normalized_expected)
    sha256_matches = (
        actual_sha256 == normalized_expected if normalized_expected else None
    )
    failures: list[str] = []
    if not expected_is_valid:
        failures.append("Windows visual-audit verifier expected SHA-256 is invalid")
    elif normalized_expected and not sha256_matches:
        failures.append(
            "Windows visual-audit verifier bytes do not match the SHA-256-bound intake request"
        )
    return {
        "path": str(VERIFIER_PATH),
        "contract_name": CONTRACT_NAME,
        "execution_mode": VERIFIER_EXECUTION_MODE,
        "expected_sha256": normalized_expected,
        "actual_sha256": actual_sha256,
        "expected_sha256_valid": expected_is_valid,
        "sha256_matches": sha256_matches,
        "status": "pass" if not failures else "fail",
    }, failures


def normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def path_exists(path_value: Any) -> bool:
    text = str(path_value or "").strip()
    if not text:
        return False
    try:
        return Path(text).is_file()
    except OSError:
        return False


def text_sha256(path_value: Any) -> str:
    text = str(path_value or "").strip()
    if not text:
        return ""
    try:
        path = Path(text)
        if not path.is_file():
            return ""
        return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest().lower()
    except (OSError, UnicodeDecodeError):
        return ""


def sample_paths(rows: Any, *, limit: int = 2) -> list[str]:
    if not isinstance(rows, list):
        return []
    paths: list[str] = []
    for row in rows:
        path = ""
        if isinstance(row, dict):
            path = str(row.get("path") or "").strip()
        else:
            path = str(row).strip()
        if not path or path in paths:
            continue
        paths.append(path)
        if len(paths) >= limit:
            break
    return paths


def watcher_state_details(path_value: Any) -> dict[str, Any]:
    text = str(path_value or "").strip()
    path = Path(text) if text else DEFAULT_WINDOWS_WATCHER_STATE
    payload, load_status = load_json(path)
    matching_process_pids = (
        list(payload.get("matching_process_pids"))
        if isinstance(payload.get("matching_process_pids"), list)
        else []
    )
    duplicate_process_pids = (
        list(payload.get("duplicate_process_pids"))
        if isinstance(payload.get("duplicate_process_pids"), list)
        else []
    )
    status = str(payload.get("status") or "").strip()
    duplicate_count = int(payload.get("duplicate_process_count") or len(duplicate_process_pids))
    return {
        "watcher_state_receipt_path": str(path),
        "watcher_state_receipt_exists": path.is_file(),
        "watcher_state_receipt_load_status": load_status,
        "watcher_state_receipt_generated_at_utc": str(payload.get("generated_at_utc") or "").strip(),
        "watcher_status": status,
        "watcher_pid": payload.get("pid"),
        "watcher_process_alive": bool(payload.get("process_alive")),
        "watcher_matching_process_pids": matching_process_pids,
        "watcher_matching_process_count": int(payload.get("matching_process_count") or len(matching_process_pids)),
        "watcher_duplicate_process_pids": duplicate_process_pids,
        "watcher_duplicate_process_count": duplicate_count,
        "watcher_note": str(payload.get("note") or "").strip(),
        "watcher_attention_required": status != "running" or duplicate_count > 0,
    }


def refresh_watcher_state(watcher_status_command: str, watcher_path: Path) -> dict[str, Any]:
    if auto_import_side_effects_paused():
        return watcher_state_details(watcher_path)
    command_text = str(watcher_status_command or "").strip()
    if command_text:
        try:
            subprocess.run(
                shlex.split(command_text),
                cwd=ROOT,
                env=subprocess_env(workspace_root=ROOT.parent),
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
        except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
            pass
    return watcher_state_details(watcher_path)


def refresh_auto_import_state(auto_import_command: str, auto_import_path: Path) -> tuple[dict[str, Any], str]:
    if auto_import_side_effects_paused():
        return load_json(auto_import_path)
    command_text = str(auto_import_command or "").strip()
    if command_text:
        try:
            subprocess.run(
                shlex.split(command_text),
                cwd=ROOT,
                env=subprocess_env(workspace_root=ROOT.parent),
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
        except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
            pass
    return load_json(auto_import_path)


def telegram_delivery_receipt_details(receipt_name: Any) -> dict[str, Any]:
    normalized_receipt_name = str(receipt_name or "").strip()
    receipt_path = DEFAULT_TELEGRAM_TEXT_DELIVERY_ROOT / normalized_receipt_name if normalized_receipt_name else None
    receipt_exists = bool(receipt_path and receipt_path.is_file())
    payload, _ = load_json(receipt_path) if receipt_exists and receipt_path is not None else ({}, "missing")
    return {
        "operator_ask_delivery_receipt_path": str(receipt_path) if receipt_path is not None else "",
        "operator_ask_delivery_receipt_exists": receipt_exists,
        "operator_ask_delivery_status": str(payload.get("status") or "").strip(),
        "operator_ask_delivery_generated_at_utc": str(payload.get("generated_at_utc") or "").strip(),
        "operator_ask_delivery_message_ids": list(payload.get("message_ids")) if isinstance(payload.get("message_ids"), list) else [],
        "operator_ask_delivery_text_sha256": str(payload.get("text_sha256") or "").strip(),
        "operator_ask_delivery_text_preview": str(payload.get("text_preview") or "").strip(),
    }


def windows_operator_request_artifacts(*, refresh_operator_state: bool = False) -> dict[str, Any]:
    request_payload, _ = load_json(DEFAULT_WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST)
    operator_draft = request_payload.get("operator_telegram_draft") if isinstance(request_payload.get("operator_telegram_draft"), dict) else {}
    artifact_intake = request_payload.get("artifact_intake") if isinstance(request_payload.get("artifact_intake"), dict) else {}
    operator_ask_text_path = str(
        operator_draft.get("current_message_path")
        or operator_draft.get("message_path")
        or ""
    ).strip()
    operator_ask_metadata_path = str(
        operator_draft.get("current_metadata_path")
        or operator_draft.get("metadata_path")
        or ""
    ).strip()
    operator_ask_receipt_name = str(operator_draft.get("receipt_name") or "").strip()
    delivery_receipt = telegram_delivery_receipt_details(operator_ask_receipt_name)
    operator_ask_message_sha256 = text_sha256(operator_ask_text_path)
    delivery_text_sha256 = str(delivery_receipt.get("operator_ask_delivery_text_sha256") or "").strip()
    delivery_text_comparable = bool(operator_ask_message_sha256 and delivery_text_sha256)
    delivery_matches_current_text = bool(
        delivery_text_comparable and operator_ask_message_sha256 == delivery_text_sha256
    )
    delivery_needs_resend = bool(delivery_text_comparable and not delivery_matches_current_text)
    failures: list[str] = []
    request_receipt_exists = DEFAULT_WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST.is_file()
    operator_ask_text_exists = path_exists(operator_ask_text_path)
    operator_ask_metadata_exists = path_exists(operator_ask_metadata_path)
    operator_ask_send_command = str(operator_draft.get("send_command") or "").strip()
    preferred_drop_path = str(
        request_payload.get("preferred_drop_path")
        or operator_draft.get("preferred_drop_path")
        or ""
    ).strip()
    auto_import_command = str(artifact_intake.get("auto_import_command") or "").strip()
    import_command = str(artifact_intake.get("import_command") or "").strip()
    auto_import_watch_command = str(artifact_intake.get("auto_import_watch_command") or "").strip()
    watcher_launch_mode = str(artifact_intake.get("watcher_launch_mode") or "").strip()
    watcher_state_path = str(artifact_intake.get("watcher_state_path") or "").strip()
    watcher_pid_file = str(artifact_intake.get("watcher_pid_file") or "").strip()
    watcher_log_path = str(artifact_intake.get("watcher_log_path") or "").strip()
    watcher_start_command = str(artifact_intake.get("watcher_start_command") or "").strip()
    watcher_status_command = str(artifact_intake.get("watcher_status_command") or "").strip()
    watcher_stop_command = str(artifact_intake.get("watcher_stop_command") or "").strip()
    watcher_path = Path(watcher_state_path) if watcher_state_path else DEFAULT_WINDOWS_WATCHER_STATE
    intake_verifier: dict[str, Any] = {}
    if request_receipt_exists:
        try:
            _ok, verified = verify_windows_visual_intake_request_receipt(
                DEFAULT_WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST,
                require_pass=False,
            )
            intake_verifier = dict(verified) if isinstance(verified, dict) else {}
        except Exception as exc:
            intake_verifier = {
                "status": "fail",
                "recovery_pack_pass": False,
                "runtime_refresh_commands_trusted": False,
                "issues": [f"windows_visual_intake_request_verifier_failed:{type(exc).__name__}"],
            }
    runtime_refresh_authorized = (
        str(intake_verifier.get("status") or "").strip().lower() == "pass"
        and intake_verifier.get("recovery_pack_pass") is True
        and intake_verifier.get("runtime_refresh_commands_trusted") is True
        and not list(intake_verifier.get("issues") or [])
    )
    if refresh_operator_state and runtime_refresh_authorized:
        auto_import_payload, auto_import_load_status = refresh_auto_import_state(
            auto_import_command,
            DEFAULT_WINDOWS_VISUAL_AUDIT_AUTO_IMPORT,
        )
        watcher_state = refresh_watcher_state(watcher_status_command, watcher_path)
    else:
        if refresh_operator_state:
            failures.append(
                "operator state refresh refused because intake receipt commands are not trusted"
            )
        auto_import_payload, auto_import_load_status = load_json(DEFAULT_WINDOWS_VISUAL_AUDIT_AUTO_IMPORT)
        watcher_state = watcher_state_details(watcher_path)
    discover_command = str(artifact_intake.get("discover_command") or "").strip()
    post_import_verify_command = str(artifact_intake.get("post_import_verify_command") or "").strip()
    post_import_verify_note = str(artifact_intake.get("post_import_verify_note") or "").strip()
    promoted_installer_sha256 = str(
        request_payload.get("promoted_installer_sha256")
        or operator_draft.get("promoted_installer_sha256")
        or ""
    ).strip()
    request_status = str(request_payload.get("status") or "").strip()
    preferred_zip_name = str(
        request_payload.get("preferred_zip_name")
        or operator_draft.get("preferred_zip_name")
        or ""
    ).strip()
    required_zip_filename = str(
        request_payload.get("required_zip_filename")
        or operator_draft.get("required_zip_filename")
        or ""
    ).strip()
    preferred_drop_path_exists = path_exists(preferred_drop_path)
    if not request_receipt_exists:
        failures.append("request receipt missing")
    if not operator_ask_text_exists:
        failures.append("operator ask text missing")
    if not operator_ask_metadata_exists:
        failures.append("operator ask metadata missing")
    if not operator_ask_send_command:
        failures.append("operator ask send command missing")
    if not preferred_drop_path:
        failures.append("preferred drop path missing")
    if not import_command:
        failures.append("import command missing")
    if not auto_import_watch_command:
        failures.append("auto import watch command missing")
    if not promoted_installer_sha256:
        failures.append("promoted installer sha256 missing")
    if delivery_needs_resend:
        failures.append("operator ask delivery no longer matches current text")
    return {
        "request_receipt_path": str(DEFAULT_WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST),
        "request_receipt_exists": request_receipt_exists,
        "request_status": request_status,
        "operator_ask_text_path": operator_ask_text_path,
        "operator_ask_text_exists": operator_ask_text_exists,
        "operator_ask_metadata_path": operator_ask_metadata_path,
        "operator_ask_metadata_exists": operator_ask_metadata_exists,
        "operator_ask_send_command": operator_ask_send_command,
        "operator_ask_resend_command": operator_ask_send_command if delivery_needs_resend else "",
        "operator_ask_receipt_name": operator_ask_receipt_name,
        "operator_ask_message_preview": str(operator_draft.get("message_preview") or "").strip(),
        "operator_ask_message_sha256": operator_ask_message_sha256,
        "operator_ask_delivery_current_text_comparable": delivery_text_comparable,
        "operator_ask_delivery_matches_current_text": delivery_matches_current_text,
        "operator_ask_delivery_needs_resend": delivery_needs_resend,
        "preferred_drop_path": preferred_drop_path,
        "preferred_drop_path_exists": preferred_drop_path_exists,
        "preferred_zip_name": preferred_zip_name,
        "required_zip_filename": required_zip_filename,
        "startup_receipt_bundle_required": bool(request_payload.get("startup_receipt_bundle_required")),
        "discover_command": discover_command,
        "auto_import_command": auto_import_command,
        "import_command": import_command,
        "auto_import_watch_command": auto_import_watch_command,
        "watcher_launch_mode": watcher_launch_mode,
        "watcher_state_path": watcher_state_path,
        "watcher_pid_file": watcher_pid_file,
        "watcher_log_path": watcher_log_path,
        "watcher_start_command": watcher_start_command,
        "watcher_status_command": watcher_status_command,
        "watcher_stop_command": watcher_stop_command,
        **watcher_state,
        "post_import_verify_command": post_import_verify_command,
        "post_import_verify_note": post_import_verify_note,
        "promoted_installer_sha256": promoted_installer_sha256,
        "auto_import_receipt_path": str(DEFAULT_WINDOWS_VISUAL_AUDIT_AUTO_IMPORT),
        "operator_state_refresh_requested": refresh_operator_state,
        "runtime_refresh_authorized": runtime_refresh_authorized,
        "intake_receipt_verifier": intake_verifier,
        "auto_import_receipt_exists": DEFAULT_WINDOWS_VISUAL_AUDIT_AUTO_IMPORT.is_file(),
        "auto_import_receipt_load_status": auto_import_load_status,
        "auto_import_receipt_generated_at_utc": str(auto_import_payload.get("generated_at_utc") or "").strip(),
        "auto_import_receipt_status": str(auto_import_payload.get("status") or "").strip(),
        "auto_import_actionable_candidate_count": int(auto_import_payload.get("actionable_candidate_count") or 0),
        "auto_import_stage_visual_proof_receipt_count": int(auto_import_payload.get("stage_visual_proof_receipt_count") or 0),
        "auto_import_matching_promoted_stage_visual_proof_receipt_count": int(auto_import_payload.get("matching_promoted_stage_visual_proof_receipt_count") or 0),
        "auto_import_stale_stage_visual_proof_receipt_count": int(auto_import_payload.get("stale_stage_visual_proof_receipt_count") or 0),
        "auto_import_stage_startup_smoke_receipt_count": int(auto_import_payload.get("stage_startup_smoke_receipt_count") or 0),
        "auto_import_matching_promoted_stage_startup_smoke_receipt_count": int(auto_import_payload.get("matching_promoted_stage_startup_smoke_receipt_count") or 0),
        "auto_import_stale_stage_startup_smoke_receipt_count": int(auto_import_payload.get("stale_stage_startup_smoke_receipt_count") or 0),
        "auto_import_stage_visual_proof_receipt_note": str(auto_import_payload.get("stage_visual_proof_receipt_note") or "").strip(),
        "auto_import_stage_startup_smoke_receipt_note": str(auto_import_payload.get("stage_startup_smoke_receipt_note") or "").strip(),
        "auto_import_stage_visual_proof_receipt_sample_paths": sample_paths(
            auto_import_payload.get("stale_stage_visual_proof_receipts")
        ),
        "auto_import_matching_promoted_stage_startup_smoke_receipt_sample_paths": sample_paths(
            auto_import_payload.get("matching_promoted_stage_startup_smoke_receipts")
        ),
        "pass": not failures,
        "failures": failures,
        **delivery_receipt,
    }


def normalized_surface(value: Any) -> str:
    surface = normalized(value).replace("_", "-").replace(" ", "-")
    aliases = {
        "progress": "install-progress",
        "install": "install-progress",
        "splash": "install-progress",
        "install-splash": "install-progress",
        "complete": "completion",
        "install-complete": "completion",
    }
    return aliases.get(surface, surface)


def is_default_dpi(value: Any) -> bool:
    return str(value) in {"1", "1.0", "100", "100%"}


def windows_installer_artifact(release_channel: dict[str, Any]) -> dict[str, Any]:
    for item in release_channel.get("artifacts") or release_channel.get("downloads") or []:
        if not isinstance(item, dict):
            continue
        artifact_id = normalized(item.get("artifactId") or item.get("id"))
        platform = normalized(item.get("platform"))
        kind = normalized(item.get("kind"))
        if artifact_id == "avalonia-win-x64-installer" or (platform == "windows" and kind == "installer"):
            return item
    return {}


def effective_promoted_artifact_sha256(artifact: dict[str, Any], actual_artifact_sha: str) -> str:
    manifest_sha = normalized(artifact.get("sha256")).removeprefix("sha256:")
    # RELEASE_CHANNEL is the promotion authority. Shelf bytes are verification
    # evidence and must never silently replace the manifest's promoted binding.
    return manifest_sha if is_sha256(manifest_sha) else ""


def release_windows_binding(release_channel: dict[str, Any]) -> dict[str, Any]:
    artifact = windows_installer_artifact(release_channel)
    return {
        "version": str(
            release_channel.get("version")
            or release_channel.get("releaseVersion")
            or ""
        ).strip(),
        "channel": normalized(
            release_channel.get("channelId") or release_channel.get("channel")
        ),
        "artifact_id": str(artifact.get("artifactId") or artifact.get("id") or "").strip(),
        "file_name": str(artifact.get("fileName") or "").strip(),
        "sha256": normalized(artifact.get("sha256")).removeprefix("sha256:"),
    }


def source_screenshot_path(source_path: Path, raw_path: Any) -> Path:
    candidate = Path(str(raw_path or "").strip())
    if not candidate:
        return candidate
    if candidate.is_absolute():
        return candidate
    return source_path.parent / candidate


def screenshot_rows(source_path: Path, source: dict[str, Any]) -> list[dict[str, Any]]:
    rows = source.get("screenshots")
    if not isinstance(rows, list):
        return []
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = source_screenshot_path(source_path, row.get("path"))
        surface = normalized_surface(row.get("surface"))
        screenshot_sha = sha256_file(path) if path.is_file() else ""
        normalized_rows.append(
            {
                "path": str(path),
                "exists": path.is_file(),
                "sha256": screenshot_sha,
                "dpiScale": row.get("dpiScale"),
                "surface": str(row.get("surface") or "").strip(),
                "canonicalSurface": surface,
                "clippingStatus": normalized(row.get("clippingStatus")),
                "readabilityStatus": normalized(row.get("readabilityStatus")),
                "hostClass": str(row.get("hostClass") or "").strip(),
                "captureMode": normalized(row.get("captureMode")),
                "captureBounds": row.get("captureBounds") if isinstance(row.get("captureBounds"), dict) else {},
                "reusedFrom": str(row.get("reusedFrom") or "").strip(),
                "windowTitle": str(row.get("windowTitle") or "").strip(),
            }
        )
    return normalized_rows


def capture_bounds_look_like_desktop_fallback(row: dict[str, Any]) -> bool:
    mode = normalized(row.get("captureMode"))
    if mode not in {"window-bounds", "reused-same-surface"}:
        return False
    if row.get("canonicalSurface") not in REQUIRED_SURFACES:
        return False

    bounds = row.get("captureBounds")
    if not isinstance(bounds, dict):
        return False
    try:
        left = int(bounds.get("left", 0))
        top = int(bounds.get("top", 0))
        width = int(bounds.get("width", 0))
        height = int(bounds.get("height", 0))
    except (TypeError, ValueError):
        return False

    # A real Chummer installer window is compact even at scaled DPI. 1024x768 from
    # (0,0) is the Windows runner's virtual desktop fallback, not a dialog.
    return left == 0 and top == 0 and width >= 1000 and height >= 700


def build_payload(
    *,
    release_channel_path: Path,
    downloads_root: Path,
    startup_receipt_path: Path,
    source_path: Path,
    portal_release_channel_path: Path | None = None,
    refresh_operator_state: bool = False,
    expected_verifier_sha256: str = "",
) -> dict[str, Any]:
    release_channel, release_channel_load_status = load_json(release_channel_path)
    startup_receipt, startup_receipt_load_status = load_json(startup_receipt_path)
    source, source_load_status = load_json(source_path)
    artifact = windows_installer_artifact(release_channel)
    failures: list[str] = []
    current_verifier_binding, verifier_binding_failures = verifier_binding(
        expected_verifier_sha256
    )
    failures.extend(verifier_binding_failures)

    authority_binding = release_windows_binding(release_channel)
    projection_check: dict[str, Any] = {
        "path": str(portal_release_channel_path or ""),
        "loadStatus": "not_configured",
        "authorityPath": str(release_channel_path),
        "authorityBinding": authority_binding,
        "projectionBinding": {},
        "matchesAuthority": None,
        "status": "not_configured",
    }
    if portal_release_channel_path is not None:
        try:
            same_release_channel = (
                portal_release_channel_path.resolve() == release_channel_path.resolve()
            )
        except OSError:
            same_release_channel = portal_release_channel_path == release_channel_path
        if same_release_channel:
            projection_check.update(
                {
                    "loadStatus": release_channel_load_status,
                    "projectionBinding": authority_binding,
                    "matchesAuthority": True,
                    "status": "authority_is_portal_projection",
                }
            )
        else:
            portal_release_channel, portal_load_status = load_json(
                portal_release_channel_path
            )
            projection_binding = release_windows_binding(portal_release_channel)
            projection_matches = bool(
                release_channel_load_status == "loaded"
                and portal_load_status == "loaded"
                and authority_binding == projection_binding
            )
            projection_check.update(
                {
                    "loadStatus": portal_load_status,
                    "projectionBinding": projection_binding,
                    "matchesAuthority": projection_matches,
                    "status": "aligned" if projection_matches else "disagrees",
                }
            )
            if portal_load_status == "missing":
                failures.append(
                    f"Portal release channel projection is missing: {portal_release_channel_path}"
                )
            elif portal_load_status == "invalid":
                failures.append(
                    f"Portal release channel projection is malformed: {portal_release_channel_path}"
                )
            elif not projection_matches:
                failures.append(
                    "Portal release channel Windows installer binding disagrees with authoritative release channel"
                )

    if release_channel_load_status == "missing":
        failures.append(f"Release channel receipt is missing: {release_channel_path}")
    elif release_channel_load_status == "invalid":
        failures.append(f"Release channel receipt is malformed: {release_channel_path}")

    artifact_path = downloads_root / "files" / str(artifact.get("fileName") or "")
    artifact_sha = normalized(artifact.get("sha256")).removeprefix("sha256:")
    actual_artifact_sha = sha256_file(artifact_path) if artifact_path.is_file() else ""
    effective_artifact_sha = effective_promoted_artifact_sha256(artifact, actual_artifact_sha)

    if not artifact:
        failures.append("promoted Windows installer artifact is missing from release channel")
    elif not is_sha256(artifact_sha):
        failures.append("promoted Windows installer manifest sha256 is missing or invalid")
    if not artifact_path.is_file():
        failures.append("promoted Windows installer artifact file is missing")
    if is_sha256(artifact_sha) and actual_artifact_sha and artifact_sha != actual_artifact_sha:
        failures.append("promoted Windows installer manifest sha256 does not match artifact bytes")

    startup_status = normalized(startup_receipt.get("status"))
    startup_disposition = normalized(startup_receipt.get("verificationDisposition"))
    startup_skip_class = normalized(startup_receipt.get("skipClass"))
    startup_digest = normalized(startup_receipt.get("artifactDigest")).removeprefix("sha256:")
    startup_incompatible_host = startup_disposition == "incompatible_host" or startup_skip_class == "incompatible_host"
    if startup_receipt_load_status == "missing":
        failures.append("Windows startup receipt is missing")
    elif startup_receipt_load_status == "invalid":
        failures.append("Windows startup receipt is malformed")
    elif startup_incompatible_host:
        failures.append("Windows startup receipt is an incompatible-host skip, not native proof")
    elif startup_status != "pass":
        failures.append("Windows startup receipt is not a native pass")
    elif not is_sha256(startup_digest):
        failures.append("Windows startup receipt artifact digest is missing or invalid")
    if effective_artifact_sha and is_sha256(startup_digest) and startup_digest != effective_artifact_sha:
        failures.append("Windows startup receipt digest does not match promoted installer")

    source_status = normalized(source.get("status"))
    source_platform = normalized(source.get("platform"))
    source_host_class = normalized(source.get("hostClass"))
    source_artifact_sha = normalized(source.get("artifactSha256") or source.get("artifactDigest")).removeprefix("sha256:")
    source_digest_matches_promoted = bool(
        effective_artifact_sha and source_artifact_sha and source_artifact_sha == effective_artifact_sha
    )
    screenshots = screenshot_rows(source_path, source)
    default_dpi = [row for row in screenshots if is_default_dpi(row.get("dpiScale"))]
    scaled_dpi = [
        row
        for row in screenshots
        if str(row.get("dpiScale")) not in {"", "1", "1.0", "100", "100%"}
    ]

    if source_load_status == "missing":
        failures.append(f"Windows installer visual audit source is missing: {source_path}")
    elif source_load_status == "invalid":
        failures.append(f"Windows installer visual audit source is malformed: {source_path}")
    elif source_status != "pass":
        failures.append("Windows installer visual audit source is not pass")
    if source and source_platform != "windows":
        failures.append("Windows installer visual audit source platform is not windows")
    if source and "windows" not in source_host_class and source_host_class != "native":
        failures.append("Windows installer visual audit source is not marked as a native Windows host")
    if source and not is_sha256(source_artifact_sha):
        failures.append("Windows installer visual audit source artifact digest is missing or invalid")
    if effective_artifact_sha and is_sha256(source_artifact_sha) and source_artifact_sha != effective_artifact_sha:
        failures.append("Windows installer visual audit source digest does not match promoted installer")
        failures.append(
            "windows installer visual audit source still targets "
            f"{source_artifact_sha} instead of promoted digest {effective_artifact_sha}: {source_path}"
        )
    if source and not source_artifact_sha:
        failures.append("Windows installer visual audit source does not record artifactSha256")
    if not screenshots:
        failures.append("Windows installer visual audit has no screenshots")
    if screenshots and not default_dpi:
        failures.append("Windows installer visual audit has no default-DPI screenshot")
    if screenshots and not scaled_dpi:
        failures.append("Windows installer visual audit has no scaled-DPI screenshot")
    for surface in REQUIRED_SURFACES:
        surface_rows = [row for row in screenshots if row.get("canonicalSurface") == surface]
        if not surface_rows:
            failures.append(f"Windows installer visual audit has no {surface} screenshot")
            continue
        if not any(is_default_dpi(row.get("dpiScale")) for row in surface_rows):
            failures.append(f"Windows installer visual audit has no default-DPI {surface} screenshot")
        if not any(not is_default_dpi(row.get("dpiScale")) and str(row.get("dpiScale")) for row in surface_rows):
            failures.append(f"Windows installer visual audit has no scaled-DPI {surface} screenshot")
    for row in screenshots:
        if not row["exists"]:
            failures.append(f"Windows installer screenshot is missing: {row['path']}")
        if row["clippingStatus"] != "pass":
            failures.append(f"Windows installer screenshot clipping check is not pass: {row['path']}")
        if row["readabilityStatus"] != "pass":
            failures.append(f"Windows installer screenshot readability check is not pass: {row['path']}")
        if capture_bounds_look_like_desktop_fallback(row):
            failures.append(
                "Windows installer screenshot used full-desktop fallback bounds instead of the installer window: "
                f"{row['path']}"
            )
    rows_by_hash: dict[str, set[str]] = {}
    for row in screenshots:
        screenshot_sha = str(row.get("sha256") or "")
        surface = str(row.get("canonicalSurface") or "")
        if screenshot_sha and surface in REQUIRED_SURFACES:
            rows_by_hash.setdefault(screenshot_sha, set()).add(surface)
    for screenshot_sha, surfaces in sorted(rows_by_hash.items()):
        if len(surfaces) > 1:
            failures.append(
                "Windows installer screenshots for distinct required surfaces are byte-identical: "
                f"{screenshot_sha} covers {', '.join(sorted(surfaces))}"
            )

    startup_needs_native_proof = (
        not startup_receipt
        or startup_status != "pass"
        or startup_disposition == "incompatible_host"
        or startup_skip_class == "incompatible_host"
        or bool(effective_artifact_sha and startup_digest and startup_digest != effective_artifact_sha)
    )
    visual_audit_needs_recapture = any(
        failure.startswith("Windows installer visual audit")
        or failure.startswith("Windows installer screenshot")
        or "distinct required surfaces" in failure
        for failure in failures
    )
    operator_request_artifacts = windows_operator_request_artifacts(
        refresh_operator_state=refresh_operator_state,
    )
    operator_request_digest = normalized(operator_request_artifacts.get("promoted_installer_sha256"))
    operator_request_raw_status = normalized(operator_request_artifacts.get("request_status"))
    operator_request_matches_artifact = bool(
        effective_artifact_sha and operator_request_digest and operator_request_digest == effective_artifact_sha
    )
    preferred_drop_path = str(operator_request_artifacts.get("preferred_drop_path") or "").strip()
    import_command = str(operator_request_artifacts.get("import_command") or "").strip()
    operator_request_effective_status = "external_artifact_required" if failures else "not_required"
    operator_request_artifacts["request_effective_status"] = operator_request_effective_status
    operator_request_artifacts["operator_action_still_required"] = (
        operator_request_effective_status == "external_artifact_required"
    )
    if (
        operator_request_matches_artifact
        and operator_request_effective_status == "external_artifact_required"
        and preferred_drop_path
        and not bool(operator_request_artifacts.get("preferred_drop_path_exists"))
    ):
        failures.append(f"windows installer gold proof artifact is still missing: {preferred_drop_path}")
    next_actions: list[str] = []
    if failures:
        if operator_request_matches_artifact:
            stage_visual_proof_receipt_count = int(operator_request_artifacts.get("auto_import_stage_visual_proof_receipt_count") or 0)
            stage_startup_smoke_receipt_count = int(operator_request_artifacts.get("auto_import_stage_startup_smoke_receipt_count") or 0)
            stage_visual_proof_receipt_note = str(
                operator_request_artifacts.get("auto_import_stage_visual_proof_receipt_note") or ""
            ).strip()
            stage_startup_smoke_receipt_note = str(
                operator_request_artifacts.get("auto_import_stage_startup_smoke_receipt_note") or ""
            ).strip()
            stage_hint_parts = [
                part
                for part in (stage_visual_proof_receipt_note, stage_startup_smoke_receipt_note)
                if part
            ]
            if stage_visual_proof_receipt_count or stage_startup_smoke_receipt_count or stage_hint_parts:
                review_hint = (
                    "Review surfaced Windows stage/nightly proof hints in "
                    f"{operator_request_artifacts.get('auto_import_receipt_path')}; "
                    f"visual-proof receipts={stage_visual_proof_receipt_count}, "
                    f"startup-smoke receipts={stage_startup_smoke_receipt_count}."
                )
                if stage_hint_parts:
                    review_hint += " " + " ".join(stage_hint_parts)
                review_hint += " Use them only to locate old capture output for recapture or bundle packaging."
                next_actions.append(review_hint)
            stage_visual_proof_receipt_sample_paths = list(
                operator_request_artifacts.get("auto_import_stage_visual_proof_receipt_sample_paths") or []
            )
            if stage_visual_proof_receipt_sample_paths:
                next_actions.append(
                    "Sample stale Windows proof hint paths: "
                    + "; ".join(stage_visual_proof_receipt_sample_paths)
                )
        if source_artifact_sha and effective_artifact_sha and source_artifact_sha != effective_artifact_sha:
            next_actions.append(
                "Recapture the Windows installer visual audit for the promoted installer digest "
                f"{effective_artifact_sha}; the current visual source records {source_artifact_sha}."
            )
        elif visual_audit_needs_recapture:
            next_actions.append("Capture fresh Windows installer visual audit evidence for the promoted installer.")

        if startup_needs_native_proof:
            next_actions.append(
                "Run the promoted Windows installer on a native Windows host and capture native startup plus installer progress/completion surfaces."
            )
        elif visual_audit_needs_recapture:
            next_actions.append(
                "Keep the current Windows startup-smoke receipt; it already matches the promoted installer digest."
            )

        next_actions.extend(
            [
                "Preferred remote path: run the native Windows proof runner from a controlled Windows host; it captures native Windows evidence only and does not publish downloads.",
                f"Use PowerShell: {GOLD_PROOF_SCRIPT} -LaunchInstaller -CaptureVisualAudit -ScaledDpiScale 1.5",
                f"Use PowerShell: {CAPTURE_SCRIPT} -LaunchInstaller -CaptureRequiredSet -ScaledDpiScale 1.5 -ClippingStatus pass -ReadabilityStatus pass",
                f"If you need manual capture, run {CAPTURE_SCRIPT} once per surface/DPI for install-progress and completion at default plus scaled DPI.",
                "If progress and completion screenshots are byte-identical, rerun manual capture with the progress dialog visible before accepting the completion dialog.",
                "If proof came from a remote Windows runner, import it with: "
                + (
                    import_command
                    or (
                        "python3 scripts/import_windows_installer_gold_proof_artifact.py "
                        "windows-installer-gold-proof.zip "
                        "--intake-request .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json "
                        "--verify"
                    )
                ),
                "That --verify import reruns the full intake-request post-import gate chain, not just the first verifier.",
                f"Commit the generated source receipt and screenshots under {source_path.parent}.",
            ]
        )
        if startup_needs_native_proof:
            next_actions.append(
                "Replace or refresh the Windows startup-smoke receipt with a native Windows pass for the same promoted installer digest."
            )

    summary = (
        "Native Windows visual audit matches the promoted installer."
        if not failures
        else "Native Windows visual audit still failing: " + failures[0]
    )

    return {
        "contract_name": CONTRACT_NAME,
        "verifier_binding": current_verifier_binding,
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "summary": summary,
        "required_promoted_digest": effective_artifact_sha,
        "actual_artifact_sha256": actual_artifact_sha,
        "manifest_promoted_digest": artifact_sha,
        "source_digest": source_artifact_sha,
        "source_digest_matches_promoted": source_digest_matches_promoted,
        "expected_bundle_path": preferred_drop_path,
        "expected_bundle_path_exists": bool(operator_request_artifacts.get("preferred_drop_path_exists")),
        "required_zip_filename": str(operator_request_artifacts.get("required_zip_filename") or "").strip(),
        "preferred_zip_name": str(operator_request_artifacts.get("preferred_zip_name") or "").strip(),
        "proof_request_status": operator_request_effective_status,
        "proof_request_raw_status": operator_request_raw_status,
        "operator_ask_delivery_receipt_path": str(operator_request_artifacts.get("operator_ask_delivery_receipt_path") or "").strip(),
        "operator_ask_delivery_receipt_exists": bool(operator_request_artifacts.get("operator_ask_delivery_receipt_exists")),
        "operator_ask_delivery_status": str(operator_request_artifacts.get("operator_ask_delivery_status") or "").strip(),
        "operator_ask_delivery_generated_at_utc": str(
            operator_request_artifacts.get("operator_ask_delivery_generated_at_utc") or ""
        ).strip(),
        "operator_ask_delivery_message_ids": list(operator_request_artifacts.get("operator_ask_delivery_message_ids") or []),
        "operator_ask_delivery_current_text_comparable": bool(
            operator_request_artifacts.get("operator_ask_delivery_current_text_comparable")
        ),
        "operator_ask_delivery_matches_current_text": bool(
            operator_request_artifacts.get("operator_ask_delivery_matches_current_text")
        ),
        "operator_ask_delivery_needs_resend": bool(
            operator_request_artifacts.get("operator_ask_delivery_needs_resend")
        ),
        "operator_ask_resend_command": str(operator_request_artifacts.get("operator_ask_resend_command") or "").strip(),
        "release": {
            "path": str(release_channel_path),
            "loadStatus": release_channel_load_status,
            "version": release_channel.get("version") or release_channel.get("releaseVersion"),
            "channel": release_channel.get("channelId") or release_channel.get("channel"),
            "bindingAuthority": "release_channel_manifest",
            "windowsInstallerBinding": authority_binding,
        },
        "releaseProjection": projection_check,
        "artifact": {
            "artifactId": artifact.get("artifactId") or artifact.get("id"),
            "fileName": artifact.get("fileName"),
            "path": str(artifact_path),
            "sha256": artifact_sha,
            "actualSha256": actual_artifact_sha,
            "effectiveSha256": effective_artifact_sha,
        },
        "startupReceipt": {
            "path": str(startup_receipt_path),
            "exists": startup_receipt_path.is_file(),
            "loadStatus": startup_receipt_load_status,
            "status": startup_receipt.get("status"),
            "verificationDisposition": startup_receipt.get("verificationDisposition"),
            "skipClass": startup_receipt.get("skipClass"),
            "artifactDigest": startup_receipt.get("artifactDigest"),
            "artifactDigestMatchesPromoted": bool(
                effective_artifact_sha and startup_digest and startup_digest == effective_artifact_sha
            ),
            "requiresNativeRefresh": startup_needs_native_proof,
        },
        "visualAuditSource": {
            "path": str(source_path),
            "exists": source_path.is_file(),
            "loadStatus": source_load_status,
            "status": source.get("status"),
            "platform": source.get("platform"),
            "hostClass": source.get("hostClass"),
            "artifactSha256": source.get("artifactSha256") or source.get("artifactDigest"),
            "artifactDigestMatchesPromoted": source_digest_matches_promoted,
            "requiresRecapture": visual_audit_needs_recapture,
            "sourceUpdatedAtUtc": source.get("sourceUpdatedAtUtc") or source.get("generatedAt") or source.get("generated_at"),
            "screenshotCount": len(screenshots),
            "defaultDpiScreenshotCount": len(default_dpi),
            "scaledDpiScreenshotCount": len(scaled_dpi),
            "requiredSurfaces": list(REQUIRED_SURFACES),
        },
        "screenshots": screenshots,
        "operator_request_artifacts": operator_request_artifacts,
        "failures": failures,
        "nextActions": next_actions,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify native Windows installer visual/DPI audit proof.")
    parser.add_argument("--release-channel", type=Path, default=DEFAULT_RELEASE_CHANNEL)
    parser.add_argument(
        "--portal-release-channel",
        type=Path,
        default=DEFAULT_PORTAL_RELEASE_CHANNEL,
        help=(
            "Portal projection checked independently against the authoritative "
            "release-channel Windows binding."
        ),
    )
    parser.add_argument("--downloads-root", type=Path, default=DEFAULT_DOWNLOADS_ROOT)
    parser.add_argument("--startup-receipt", type=Path, default=DEFAULT_STARTUP_RECEIPT)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--expected-verifier-sha256",
        default="",
        help=(
            "Expected SHA-256 of this verifier's exact bytes. A supplied mismatch "
            "fails before the receipt can pass."
        ),
    )
    parser.add_argument(
        "--refresh-operator-state",
        action="store_true",
        help=(
            "Explicitly run the configured auto-import and watcher-status refresh commands before verification. "
            "By default verification only reads existing receipts."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_payload(
        release_channel_path=args.release_channel,
        portal_release_channel_path=args.portal_release_channel,
        downloads_root=args.downloads_root,
        startup_receipt_path=args.startup_receipt,
        source_path=args.source,
        refresh_operator_state=args.refresh_operator_state,
        expected_verifier_sha256=args.expected_verifier_sha256,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if payload["status"] != "pass":
        print("windows_installer_visual_audit:fail")
        return 1
    print("windows_installer_visual_audit:pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
