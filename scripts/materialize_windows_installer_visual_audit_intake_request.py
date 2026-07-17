#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "scripts"))
import verify_windows_installer_visual_audit as visual_audit  # noqa: E402
from published_path_hygiene import portable_command_text, portable_path_text, published_command_text

PUBLISHED_ROOT = ROOT / ".codex-studio" / "published"
DEFAULT_OUTPUT = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
CONTRACT_NAME = "chummer.windows_installer_visual_audit_intake_request.v1"
BLOCKED_MISSING_PROMOTED_INSTALLER_STATUS = (
    "blocked_missing_promoted_installer_binding"
)
VISUAL_AUDIT_VERIFIER_RELATIVE_PATH = Path(
    "scripts/verify_windows_installer_visual_audit.py"
)
DEFAULT_DEDICATED_DROP_ROOT = ROOT / ".state" / "incoming_windows_installer_gold_proof"
DEFAULT_OPERATOR_DRAFT_ROOT = Path(
    os.environ.get("CHUMMER_WINDOWS_VISUAL_AUDIT_OPERATOR_DRAFT_ROOT")
    or ROOT / "_completion" / "windows_installer_visual_audit"
)
CURRENT_OPERATOR_ASK_TEXT_NAME = "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"
CURRENT_OPERATOR_ASK_METADATA_NAME = "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"
DEFAULT_HUB_LOCAL_RELEASE_PROOF_PATH = ROOT / ".codex-studio" / "published" / "HUB_LOCAL_RELEASE_PROOF.generated.json"
DEFAULT_LOCAL_PUBLIC_BASE_URL = "http://127.0.0.1:8091"
DEFAULT_PUBLISHED_PUBLIC_BASE_URL = str(os.environ.get("CHUMMER_PUBLIC_BASE_URL") or "").strip() or "https://chummer.run"
DEFAULT_PUBLIC_EDGE_COMPOSE_FILE = "docker-compose.public-edge.yml"
DEFAULT_PUBLIC_EDGE_TIMEOUT_SECONDS = 300
DEFAULT_WATCHER_STATE_PATH = ROOT / ".state" / "windows_installer_gold_proof_watcher.generated.json"
DEFAULT_WATCHER_PID_FILE = ROOT / ".state" / "windows_installer_gold_proof_watcher.pid"
DEFAULT_WATCHER_LOG_FILE = ROOT / ".state" / "windows_installer_gold_proof_auto_import_watch.log"
DEFAULT_DISCOVERY_ROOTS = (
    DEFAULT_DEDICATED_DROP_ROOT,
    Path("/tmp"),
)
DISCOVERY_MAX_DEPTH = 6
DEFAULT_GOLD_PROOF_PATTERN = "*windows-installer-gold-proof*.zip"
DEFAULT_VISUAL_SOURCE_PATTERN = "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
DEFAULT_NIGHTLY_ROOT = Path("/docker/chummercomplete/_staging")
DEFAULT_NIGHTLY_VISUAL_PROOF_RECEIPT = "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"
POST_IMPORT_VERIFY_NOTE = (
    "The --verify import reruns the full intake-request post-import gate chain, "
    "not just the first verifier."
)
PASS_STATUSES = {"pass", "passed", "ready"}


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest().lower()


def is_sha256(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return len(normalized) == 64 and all(
        character in "0123456789abcdef" for character in normalized
    )


def visual_audit_verifier_binding() -> dict[str, Any]:
    verifier_path = (ROOT / VISUAL_AUDIT_VERIFIER_RELATIVE_PATH).resolve()
    return {
        "path": str(verifier_path),
        "relative_path": str(VISUAL_AUDIT_VERIFIER_RELATIVE_PATH),
        "contract_name": str(visual_audit.CONTRACT_NAME),
        "execution_mode": str(visual_audit.VERIFIER_EXECUTION_MODE),
        "sha256": sha256_file(verifier_path),
    }


def build_bound_visual_audit_verify_command(binding: dict[str, Any]) -> str:
    verifier_sha256 = str(binding.get("sha256") or "").strip().lower()
    if not is_sha256(verifier_sha256):
        raise ValueError("visual audit verifier binding SHA-256 is invalid")
    return (
        "python3 scripts/verify_windows_installer_visual_audit.py "
        f"--expected-verifier-sha256 {verifier_sha256} "
        "--output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"
    )


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def unique_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(path)
    return result


def artifact_discovery_roots(dedicated_drop_root: Path) -> list[Path]:
    home = Path.home()
    roots = [
        dedicated_drop_root,
        Path("/tmp"),
        home / "Downloads",
        home / "pCloud Drive" / "EA",
    ]
    return unique_paths(roots)


def is_gitignored_runtime_root(path: Path) -> bool:
    normalized = path.expanduser()
    roots = [
        ROOT / ".state",
        WORKSPACE_ROOT / ".state",
    ]
    for root in roots:
        try:
            if normalized.is_relative_to(root):
                return True
        except ValueError:
            continue
    return False


def normalize_digest(value: Any) -> str:
    return str(value or "").strip().lower().removeprefix("sha256:")


def text_preview(value: str, limit: int = 220) -> str:
    normalized = " ".join(str(value or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def read_release_context(release_channel_path: Path) -> dict[str, str]:
    payload = load_json(release_channel_path)
    return {
        "path": str(release_channel_path),
        "version": str(payload.get("version") or payload.get("releaseVersion") or "").strip(),
        "channel": str(payload.get("channelId") or payload.get("channel") or "").strip(),
        "supportability_state": str(payload.get("supportabilityState") or "").strip(),
        "rollout_state": str(payload.get("rolloutState") or "").strip(),
        "published_at": str(payload.get("publishedAt") or payload.get("published_at") or "").strip(),
    }


def operator_ask_stem(promoted_digest: str) -> str:
    token = promoted_digest[:12] if is_sha256(promoted_digest) else "binding-required"
    return f"windows-installer-gold-proof-{token}-operator-ask"


def current_operator_ask_text_path(operator_draft_root: Path | None = None) -> Path:
    return (operator_draft_root or DEFAULT_OPERATOR_DRAFT_ROOT) / CURRENT_OPERATOR_ASK_TEXT_NAME


def current_operator_ask_metadata_path(operator_draft_root: Path | None = None) -> Path:
    return (operator_draft_root or DEFAULT_OPERATOR_DRAFT_ROOT) / CURRENT_OPERATOR_ASK_METADATA_NAME


def shell_quote_path(value: Path | str) -> str:
    return shlex.quote(portable_path_text(value))


def build_import_command(preferred_drop_path: Path, intake_request_path: Path) -> str:
    return (
        "python3 scripts/import_windows_installer_gold_proof_artifact.py "
        f"{shell_quote_path(preferred_drop_path)} "
        f"--intake-request {shell_quote_path(intake_request_path)} "
        "--verify"
    )


def operator_summary_for_windows_gold_proof(
    *,
    startup_receipt_matches_promoted: bool,
    startup_receipt_bundle_required: bool,
    nightly_visual_requires_native_upgrade: bool,
) -> str:
    if startup_receipt_matches_promoted and not startup_receipt_bundle_required:
        summary = (
            "Provide the native Windows gold proof bundle for the promoted installer. "
            "Native Windows startup already matches the promoted digest; the remaining gap is digest-bound visual proof for install-progress and completion."
        )
    else:
        summary = "Run the promoted Windows installer on a native Windows host and provide the gold proof bundle."

    if nightly_visual_requires_native_upgrade:
        summary += (
            " The latest staged nightly visual proof is still a proxy or incomplete artifact and does not satisfy the native Windows gold audit."
        )

    return summary


def build_operator_telegram_text(
    *,
    promoted_digest: str,
    installer_file_name: str,
    preferred_drop_path: Path | None,
    preferred_extracted_visual_dir: Path | None = None,
    import_command: str,
    auto_import_watch_command: str = "",
    discover_visual_source_command: str = "",
    operator_summary: str,
    current_failure: str,
    required_surfaces: list[str],
    required_dpi_scales: list[str],
    release_context: dict[str, str],
    startup_receipt_matches_promoted: bool = False,
    startup_receipt_bundle_required: bool = True,
    current_visual_source_path: str = "",
    current_visual_source_artifact_sha256: str = "",
    promoted_binding_ready: bool = True,
) -> str:
    surface_summary = ", ".join(required_surfaces) if required_surfaces else "install-progress and completion"
    dpi_summary = ", ".join(required_dpi_scales) if required_dpi_scales else "1.0 and 1.5"
    release_summary = (
        f"{release_context.get('version') or 'unknown'}"
        f" | channel={release_context.get('channel') or 'unknown'}"
        f" | rollout={release_context.get('rollout_state') or 'unknown'}"
        f" | supportability={release_context.get('supportability_state') or 'unknown'}"
    )
    if not promoted_binding_ready:
        return "\n".join(
            [
                "Chummer Windows proof intake is paused internally.",
                "",
                (
                    "The current release manifest does not expose both a concrete "
                    "promoted Windows installer filename and its SHA-256."
                ),
                "Do not run, capture, package, import, or send a Windows proof bundle yet.",
                "",
                f"Current release tuple: {release_summary}",
                (
                    "Current blocker: "
                    + (
                        current_failure
                        or "promoted Windows installer binding is incomplete"
                    )
                ),
                "The release binding must be repaired before a native Windows operator request is actionable.",
            ]
        ).strip() + "\n"
    if preferred_drop_path is None:
        raise ValueError("preferred drop path is required for an actionable Windows proof request")
    lines = [
        "Chummer flagship blocker: native Windows installer gold proof is still missing.",
        "",
        operator_summary,
        "",
        f"Current promoted release tuple: {release_summary}",
        f"Promoted installer SHA256: {promoted_digest}",
        f"Installer file: {installer_file_name or 'chummer-avalonia-win-x64-installer.exe'}",
        f"Current blocker: {current_failure or 'Windows installer visual audit source digest does not match the promoted installer.'}",
    ]
    if startup_receipt_matches_promoted:
        lines.append("Current startup-smoke receipt already matches the promoted installer digest.")
    if startup_receipt_matches_promoted and not startup_receipt_bundle_required:
        lines.append("Native Windows startup is already confirmed for the promoted digest; the remaining gap is the matching visual proof bundle.")
    if current_visual_source_artifact_sha256:
        lines.append(
            "Current visual source digest: "
            f"{current_visual_source_artifact_sha256}"
            + (f" ({current_visual_source_path})" if current_visual_source_path else "")
        )
    capture_step = (
        f"1. If you already captured the promoted install on Windows, package those screenshots; otherwise rerun the promoted installer and capture visual proof for: {surface_summary}."
        if startup_receipt_matches_promoted and not startup_receipt_bundle_required
        else f"1. Run the promoted installer and capture visual proof for: {surface_summary}."
    )
    bundle_step = (
        f"3. Zip the startup-smoke receipt plus Chummer.Portal/downloads/visual-audit/windows-installer as {preferred_drop_path.name}."
        if startup_receipt_bundle_required
        else (
            f"3. Either zip Chummer.Portal/downloads/visual-audit/windows-installer as {preferred_drop_path.name}"
            + (
                f" or copy that folder extracted to {preferred_extracted_visual_dir}"
                if preferred_extracted_visual_dir is not None
                else ""
            )
            + ". "
            "The current startup-smoke receipt already covers promoted launch proof, so you only need to include it again if you recapture startup on the Windows host."
        )
    )
    lines.extend(
        [
            "",
            "Needed from a native Windows host:",
            capture_step,
        f"2. Capture both DPI scales: {dpi_summary}.",
        bundle_step,
        f"4. If you use the zip route, drop it here: {preferred_drop_path}",
        "",
        f"After the bundle is available, import it with: {import_command}",
        POST_IMPORT_VERIFY_NOTE,
        ]
    )
    if discover_visual_source_command and startup_receipt_matches_promoted and not startup_receipt_bundle_required:
        lines.append(
            f"If you use the extracted-directory route, discover it with: {discover_visual_source_command}"
        )
    if auto_import_watch_command:
        lines.append(f"Or watch for the bundle automatically with: {auto_import_watch_command}")
    return "\n".join(lines).strip() + "\n"


def build_operator_telegram_draft(
    *,
    promoted_digest: str,
    installer_file_name: str,
    preferred_drop_path: Path | None,
    preferred_extracted_visual_dir: Path | None = None,
    import_command: str,
    auto_import_watch_command: str = "",
    discover_visual_source_command: str = "",
    operator_summary: str,
    current_failure: str,
    required_surfaces: list[str],
    required_dpi_scales: list[str],
    release_context: dict[str, str] | None = None,
    request_receipt_path: Path | None = None,
    current_blocker_receipt_path: Path | None = None,
    current_visual_source_path: str = "",
    current_visual_source_artifact_sha256: str = "",
    startup_receipt_matches_promoted: bool = False,
    startup_receipt_bundle_required: bool = True,
    promoted_binding_ready: bool = True,
) -> dict[str, Any]:
    stem = operator_ask_stem(promoted_digest)
    message_path = DEFAULT_OPERATOR_DRAFT_ROOT / f"{stem}.txt"
    metadata_path = DEFAULT_OPERATOR_DRAFT_ROOT / f"{stem}.generated.json"
    current_message_path = current_operator_ask_text_path()
    current_metadata_path = current_operator_ask_metadata_path()
    receipt_name = f"{stem}.receipt.json"
    message_text = build_operator_telegram_text(
        promoted_digest=promoted_digest,
        installer_file_name=installer_file_name,
        preferred_drop_path=preferred_drop_path,
        preferred_extracted_visual_dir=preferred_extracted_visual_dir,
        import_command=import_command,
        auto_import_watch_command=auto_import_watch_command,
        discover_visual_source_command=discover_visual_source_command,
        operator_summary=operator_summary,
        current_failure=current_failure,
        required_surfaces=required_surfaces,
        required_dpi_scales=required_dpi_scales,
        release_context=release_context or {},
        startup_receipt_matches_promoted=startup_receipt_matches_promoted,
        startup_receipt_bundle_required=startup_receipt_bundle_required,
        current_visual_source_path=current_visual_source_path,
        current_visual_source_artifact_sha256=current_visual_source_artifact_sha256,
        promoted_binding_ready=promoted_binding_ready,
    )
    preferred_drop_path_text = (
        str(preferred_drop_path) if preferred_drop_path is not None else ""
    )
    return {
        "status": (
            "prepared_not_sent" if promoted_binding_ready else "blocked_not_sendable"
        ),
        "message_path": str(message_path),
        "metadata_path": str(metadata_path),
        "current_message_path": str(current_message_path),
        "current_metadata_path": str(current_metadata_path),
        "message_text": message_text,
        "message_sha256": sha256_text(message_text),
        "message_preview": text_preview(message_text),
        "receipt_name": receipt_name,
        "send_command": (
            (
                "python3 scripts/send_telegram_message_via_ea.py "
                f"--text-file {current_message_path} --receipt-name {receipt_name}"
            )
            if promoted_binding_ready
            else ""
        ),
        "request_receipt_path": str(request_receipt_path) if request_receipt_path else "",
        "promoted_installer_sha256": promoted_digest,
        "preferred_drop_path": preferred_drop_path_text,
        "preferred_zip_name": (
            preferred_drop_path.name if preferred_drop_path is not None else ""
        ),
        "preferred_extracted_visual_dir": str(preferred_extracted_visual_dir) if preferred_extracted_visual_dir else "",
        "import_command": import_command,
        "auto_import_watch_command": auto_import_watch_command,
        "discover_visual_source_command": discover_visual_source_command,
        "release_channel_receipt_path": str((release_context or {}).get("path") or ""),
        "release_version": str((release_context or {}).get("version") or ""),
        "release_channel": str((release_context or {}).get("channel") or ""),
        "release_supportability_state": str((release_context or {}).get("supportability_state") or ""),
        "release_rollout_state": str((release_context or {}).get("rollout_state") or ""),
        "release_published_at": str((release_context or {}).get("published_at") or ""),
        "current_blocker_receipt_path": str(current_blocker_receipt_path) if current_blocker_receipt_path else "",
        "current_visual_source_path": current_visual_source_path,
        "current_visual_source_artifact_sha256": current_visual_source_artifact_sha256,
        "startup_receipt_matches_promoted": startup_receipt_matches_promoted,
        "startup_receipt_bundle_required": startup_receipt_bundle_required,
        "direct_send_allowed": False,
        "direct_send_reason": (
            "Not sent without an explicit operator-send instruction in this turn."
            if promoted_binding_ready
            else "Not sendable until the promoted Windows installer filename and SHA-256 are bound."
        ),
        "promoted_installer_binding_ready": promoted_binding_ready,
    }


def build_auto_import_command(
    intake_request_path: Path = DEFAULT_OUTPUT,
    *,
    wait_seconds: float | None = None,
    poll_seconds: float | None = None,
    refresh_intake_request: bool = False,
) -> str:
    command = (
        "python3 scripts/auto_import_windows_installer_gold_proof.py "
        f"--intake-request {shell_quote_path(intake_request_path)}"
    )
    if wait_seconds is not None:
        command += f" --wait-seconds {int(wait_seconds)}"
    if poll_seconds is not None:
        command += f" --poll-seconds {int(poll_seconds)}"
    if refresh_intake_request:
        command += " --refresh-intake-request"
    return command


def build_watcher_manager_command(
    action: str,
    intake_request_path: Path = DEFAULT_OUTPUT,
    *,
    state_path: Path = DEFAULT_WATCHER_STATE_PATH,
    pid_file: Path = DEFAULT_WATCHER_PID_FILE,
    log_file: Path = DEFAULT_WATCHER_LOG_FILE,
    wait_seconds: float = 43200,
    poll_seconds: float = 30,
    refresh_intake_request: bool = True,
) -> str:
    command = (
        "python3 scripts/manage_windows_installer_gold_proof_watcher.py "
        f"{shlex.quote(action)} "
        f"--intake-request {shell_quote_path(intake_request_path)} "
        f"--state-path {shell_quote_path(state_path)} "
        f"--pid-file {shell_quote_path(pid_file)} "
        f"--log-file {shell_quote_path(log_file)}"
    )
    if action == "start":
        command += f" --wait-seconds {int(wait_seconds)} --poll-seconds {int(poll_seconds)}"
        command += " --refresh-intake-request" if refresh_intake_request else " --no-refresh-intake-request"
    return command


def materialize_operator_telegram_draft(draft: dict[str, Any]) -> dict[str, Any]:
    message_path = Path(str(draft.get("message_path") or "").strip())
    metadata_path = Path(str(draft.get("metadata_path") or "").strip())
    current_message_path = Path(str(draft.get("current_message_path") or "").strip())
    current_metadata_path = Path(str(draft.get("current_metadata_path") or "").strip())
    message_text = str(draft.get("message_text") or "")
    if message_path and message_text:
        message_path.parent.mkdir(parents=True, exist_ok=True)
        message_path.write_text(message_text, encoding="utf-8")
    if current_message_path and message_text:
        current_message_path.parent.mkdir(parents=True, exist_ok=True)
        current_message_path.write_text(message_text, encoding="utf-8")
    metadata_payload = {
        "generated_at_utc": now_iso(),
        "status": str(draft.get("status") or "prepared_not_sent"),
        "message_path": str(message_path),
        "current_message_path": str(current_message_path),
        "message_sha256": str(draft.get("message_sha256") or ""),
        "message_preview": str(draft.get("message_preview") or ""),
        "receipt_name": str(draft.get("receipt_name") or ""),
        "send_command": str(draft.get("send_command") or ""),
        "operator_ask_text_path": str(current_message_path),
        "operator_ask_metadata_path": str(current_metadata_path),
        "operator_ask_send_command": str(draft.get("send_command") or ""),
        "operator_ask_receipt_name": str(draft.get("receipt_name") or ""),
        "request_receipt_path": str(draft.get("request_receipt_path") or ""),
        "promoted_installer_sha256": str(draft.get("promoted_installer_sha256") or ""),
        "preferred_drop_path": str(draft.get("preferred_drop_path") or ""),
        "preferred_zip_name": str(draft.get("preferred_zip_name") or ""),
        "import_command": str(draft.get("import_command") or ""),
        "auto_import_watch_command": str(draft.get("auto_import_watch_command") or ""),
        "release_channel_receipt_path": str(draft.get("release_channel_receipt_path") or ""),
        "release_version": str(draft.get("release_version") or ""),
        "release_channel": str(draft.get("release_channel") or ""),
        "release_supportability_state": str(draft.get("release_supportability_state") or ""),
        "release_rollout_state": str(draft.get("release_rollout_state") or ""),
        "release_published_at": str(draft.get("release_published_at") or ""),
        "current_blocker_receipt_path": str(draft.get("current_blocker_receipt_path") or ""),
        "current_visual_source_path": str(draft.get("current_visual_source_path") or ""),
        "current_visual_source_artifact_sha256": str(draft.get("current_visual_source_artifact_sha256") or ""),
        "startup_receipt_matches_promoted": bool(draft.get("startup_receipt_matches_promoted")),
        "startup_receipt_bundle_required": bool(draft.get("startup_receipt_bundle_required", True)),
        "promoted_installer_binding_ready": bool(
            draft.get("promoted_installer_binding_ready")
        ),
        "direct_send_allowed": bool(draft.get("direct_send_allowed")),
        "direct_send_reason": str(draft.get("direct_send_reason") or ""),
        "secrets_redacted": True,
    }
    if metadata_path:
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata_payload, indent=2) + "\n", encoding="utf-8")
    if current_metadata_path:
        current_metadata_path.parent.mkdir(parents=True, exist_ok=True)
        current_metadata_payload = {
            **metadata_payload,
            "message_path": str(current_message_path),
            "current_message_path": str(current_message_path),
            "source_message_path": str(message_path),
            "source_metadata_path": str(metadata_path),
        }
        current_metadata_path.write_text(json.dumps(current_metadata_payload, indent=2) + "\n", encoding="utf-8")
    return metadata_payload


def file_row(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "name": path.name,
        "size_bytes": stat.st_size,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }


def walk_candidate_files(search_root: Path, *, max_depth: int = DISCOVERY_MAX_DEPTH):
    if search_root.is_file():
        yield search_root
        return
    try:
        resolved_root = search_root.resolve()
    except OSError:
        resolved_root = search_root
    root_depth = len(resolved_root.parts)
    for dirpath, dirnames, filenames in os.walk(search_root, followlinks=False):
        current = Path(dirpath)
        try:
            resolved_current = current.resolve()
        except OSError:
            resolved_current = current
        if len(resolved_current.parts) - root_depth >= max_depth:
            dirnames[:] = []
        for filename in filenames:
            yield current / filename


def top_level_files(search_root: Path):
    try:
        for candidate in search_root.iterdir():
            if candidate.is_file():
                yield candidate
    except OSError:
        return


def paths_match(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left == right


def should_recurse_root(search_root: Path, recursive_roots: list[Path]) -> bool:
    return any(paths_match(search_root, root) for root in recursive_roots)


def discover_files(pattern: str, roots: list[Path], *, recursive_roots: list[Path] | None = None) -> list[Path]:
    results: list[Path] = []
    seen: set[Path] = set()
    recursive_roots = unique_paths(list(roots if recursive_roots is None else recursive_roots))
    for root in roots:
        if not root.exists():
            continue
        candidates = (
            walk_candidate_files(root)
            if root.is_dir() and should_recurse_root(root, recursive_roots)
            else (top_level_files(root) if root.is_dir() else [root])
        )
        for candidate in candidates:
            if not candidate.is_file():
                continue
            if not fnmatch.fnmatch(candidate.name, pattern):
                continue
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            results.append(candidate)
    return sorted(results, key=lambda item: item.stat().st_mtime, reverse=True)


def visual_source_row(path: Path, promoted_digest: str) -> dict[str, Any]:
    payload = load_json(path)
    digest = normalize_digest(payload.get("artifactSha256") or payload.get("artifactDigest"))
    screenshots = payload.get("screenshots") if isinstance(payload.get("screenshots"), list) else []
    row = file_row(path)
    row.update(
        {
            "status": payload.get("status"),
            "platform": payload.get("platform"),
            "host_class": payload.get("hostClass"),
            "artifact_sha256": digest,
            "matches_promoted_installer": bool(promoted_digest and digest == promoted_digest),
            "screenshot_count": len(screenshots),
            "source_sha256": sha256_file(path),
            "source_updated_at_utc": payload.get("sourceUpdatedAtUtc")
            or payload.get("generatedAt")
            or payload.get("generated_at"),
        }
    )
    return row


def latest_nightly_handoff(nightly_root: Path) -> dict[str, Any]:
    if not nightly_root.exists():
        return {}
    matches = sorted(
        nightly_root.glob("nightly-run-*/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json"),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for match in matches:
        payload = load_json(match)
        if payload:
            return {"path": str(match), **payload}
    return {}


def latest_nightly_visual_proof_row(path: Path, promoted_digest: str) -> dict[str, Any]:
    payload = load_json(path)
    readability = payload.get("readabilityReview") if isinstance(payload.get("readabilityReview"), dict) else {}
    contrast = payload.get("contrastReview") if isinstance(payload.get("contrastReview"), dict) else {}
    clipping = payload.get("clippingReview") if isinstance(payload.get("clippingReview"), dict) else {}
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    screenshots = payload.get("screenshots") if isinstance(payload.get("screenshots"), list) else []
    artifact_digest = normalize_digest(payload.get("artifactDigest") or payload.get("artifactSha256"))
    capture_mode = str(checks.get("capture_mode") or checks.get("captureMode") or "").strip()
    notes = str(payload.get("notes") or "").strip()
    screenshot_roles = sorted(
        {
            str(item.get("role") or item.get("surface") or "").strip()
            for item in screenshots
            if isinstance(item, dict) and str(item.get("role") or item.get("surface") or "").strip()
        }
    )
    native_gold_audit_gaps: list[str] = []
    if promoted_digest and artifact_digest != promoted_digest:
        native_gold_audit_gaps.append("latest nightly visual proof digest does not match the promoted installer")
    if len(screenshots) < len(visual_audit.REQUIRED_SURFACES) * 2:
        native_gold_audit_gaps.append(
            "latest nightly visual proof does not include default and scaled DPI captures for both required surfaces"
        )
    reviewer_tokens = {
        str(readability.get("reviewer") or "").strip().lower(),
        str(contrast.get("reviewer") or "").strip().lower(),
        str(clipping.get("reviewer") or "").strip().lower(),
    }
    notes_lower = notes.lower()
    capture_mode_lower = capture_mode.lower()
    if (
        "local_wine_capture" in reviewer_tokens
        or "temporary proxy proof" in notes_lower
        or "manual_fallback" in capture_mode_lower
    ):
        native_gold_audit_gaps.append(
            "latest nightly visual proof is explicitly a proxy or fallback capture, not native Windows gold evidence"
        )
    row = file_row(path)
    row.update(
        {
            "status": payload.get("status"),
            "contract_name": payload.get("contract_name") or payload.get("contractName"),
            "release_version": payload.get("releaseVersion") or payload.get("version"),
            "head": payload.get("head") or payload.get("headId"),
            "platform": payload.get("platform"),
            "rid": payload.get("rid"),
            "artifact_sha256": artifact_digest,
            "matches_promoted_installer": bool(promoted_digest and artifact_digest == promoted_digest),
            "screenshot_count": len(screenshots),
            "screenshot_roles": screenshot_roles,
            "readability_status": readability.get("status"),
            "readability_reviewer": readability.get("reviewer"),
            "contrast_status": contrast.get("status"),
            "clipping_status": clipping.get("status"),
            "capture_mode": capture_mode,
            "notes": notes,
            "suffices_for_native_gold_audit": not native_gold_audit_gaps,
            "native_gold_audit_gaps": native_gold_audit_gaps,
        }
    )
    return row


def build_request(
    *,
    release_channel: Path,
    portal_release_channel: Path | None = None,
    downloads_root: Path,
    startup_receipt: Path,
    source: Path,
    request_output: Path = DEFAULT_OUTPUT,
    discovery_roots: list[Path],
    nightly_root: Path,
    dedicated_drop_root: Path = DEFAULT_DEDICATED_DROP_ROOT,
    auto_import_roots: list[Path] | None = None,
    recursive_scan_roots: list[Path] | None = None,
) -> dict[str, Any]:
    dedicated_drop_root.mkdir(parents=True, exist_ok=True)
    scan_roots = unique_paths(list(discovery_roots))
    watch_roots = unique_paths(list(auto_import_roots or scan_roots))
    recursive_scan_roots = unique_paths(list(scan_roots if recursive_scan_roots is None else recursive_scan_roots))
    audit = visual_audit.build_payload(
        release_channel_path=release_channel,
        portal_release_channel_path=portal_release_channel,
        downloads_root=downloads_root,
        startup_receipt_path=startup_receipt,
        source_path=source,
    )
    release_context = read_release_context(release_channel)
    artifact = audit.get("artifact") if isinstance(audit.get("artifact"), dict) else {}
    visual_source = audit.get("visualAuditSource") if isinstance(audit.get("visualAuditSource"), dict) else {}
    installer_file_name = str(artifact.get("fileName") or "").strip()
    promoted_digest = normalize_digest(
        audit.get("required_promoted_digest")
        or artifact.get("effectiveSha256")
        or artifact.get("actualSha256")
        or artifact.get("sha256")
    )
    promoted_binding_failures: list[str] = []
    if not is_sha256(promoted_digest):
        promoted_binding_failures.append("promoted_installer_sha256_missing_or_invalid")
    if (
        not installer_file_name
        or installer_file_name.lower() in {"none", "null"}
        or Path(installer_file_name).name != installer_file_name
    ):
        promoted_binding_failures.append("promoted_installer_filename_missing_or_invalid")
    promoted_installer_binding_ready = not promoted_binding_failures
    verifier_binding = visual_audit_verifier_binding()
    bound_visual_audit_verify_command = build_bound_visual_audit_verify_command(
        verifier_binding
    )
    visual_digest = normalize_digest(visual_source.get("artifactSha256"))
    gold_proof_candidates = discover_files(
        DEFAULT_GOLD_PROOF_PATTERN,
        scan_roots,
        recursive_roots=recursive_scan_roots,
    )
    visual_source_candidates = discover_files(
        DEFAULT_VISUAL_SOURCE_PATTERN,
        scan_roots,
        recursive_roots=recursive_scan_roots,
    )
    importable_visual_sources = [
        visual_source_row(path, promoted_digest)
        for path in visual_source_candidates
        if path.resolve() != source.resolve()
    ]
    matching_visual_sources = [row for row in importable_visual_sources if row["matches_promoted_installer"]]
    nightly = latest_nightly_handoff(nightly_root)
    latest_nightly = {}
    if nightly:
        nightly_visual_proof_receipt_path = Path(str(nightly.get("visual_proof_receipt_path") or "").strip())
        nightly_visual_proof = (
            latest_nightly_visual_proof_row(nightly_visual_proof_receipt_path, promoted_digest)
            if nightly_visual_proof_receipt_path.is_file()
            else {}
        )
        latest_nightly = {
            "status": nightly.get("status"),
            "summary": nightly.get("summary"),
            "handoff_path": nightly.get("path"),
            "release_shelf_root": nightly.get("release_shelf_root"),
            "release_channel_manifest_path": nightly.get("release_channel_manifest_path"),
            "visual_proof_receipt_path": nightly.get("visual_proof_receipt_path"),
            "only_blocker_is_visual_proof": nightly.get("only_blocker_is_visual_proof"),
            "windows_gate_status": nightly.get("windows_gate_status"),
            "windows_gate_reasons": nightly.get("windows_gate_reasons"),
            "windows_installer": nightly.get("windows_installer"),
            "required_screenshots": nightly.get("required_screenshots"),
            "next_actions": nightly.get("next_actions"),
            "visual_proof_receipt": nightly_visual_proof,
        }

    startup_receipt = audit.get("startupReceipt") if isinstance(audit.get("startupReceipt"), dict) else {}
    audit_failed_gates = audit.get("failed_gates") if isinstance(audit.get("failed_gates"), list) else []
    audit_failures = audit.get("failures") if isinstance(audit.get("failures"), list) else []
    audit_raw_status = str(audit.get("status") or "").strip().lower()
    audit_effective_pass = (
        audit_raw_status in PASS_STATUSES
        and not audit_failures
        and not audit_failed_gates
        and audit.get("pass") is not False
        and audit.get("source_digest_matches_promoted") is not False
        and (
            not startup_receipt
            or (
                str(startup_receipt.get("status") or "").strip().lower() in PASS_STATUSES
                and startup_receipt.get("artifactDigestMatchesPromoted") is not False
            )
        )
        and (
            not visual_source
            or (
                str(visual_source.get("status") or "").strip().lower() in PASS_STATUSES
                and visual_source.get("artifactDigestMatchesPromoted") is not False
            )
        )
    )
    status = (
        "not_required"
        if audit_effective_pass
        else (
            "external_artifact_required"
            if promoted_installer_binding_ready
            else BLOCKED_MISSING_PROMOTED_INSTALLER_STATUS
        )
    )
    current_failure = "; ".join(str(item) for item in audit.get("failures") or [])
    command_root = "${REPO_ROOT}"
    preferred_zip_name = (
        f"windows-installer-gold-proof-{promoted_digest[:12]}.zip"
        if promoted_installer_binding_ready
        else ""
    )
    preferred_drop_path = (
        dedicated_drop_root / preferred_zip_name
        if promoted_installer_binding_ready
        else None
    )
    preferred_extracted_visual_dir = dedicated_drop_root / "windows-installer"
    import_command = (
        build_import_command(preferred_drop_path, request_output)
        if preferred_drop_path is not None
        else ""
    )
    discover_command = (
        "python3 ~/.codex/skills/ea-artifact-intake/scripts/artifact_intake.py discover "
        "--pattern '*windows-installer-gold-proof*.zip' "
        + " ".join(f"--root {json.dumps(portable_path_text(path))}" for path in watch_roots)
    )
    discover_visual_source_command = (
        "python3 ~/.codex/skills/ea-artifact-intake/scripts/artifact_intake.py discover "
        f"--pattern {json.dumps(DEFAULT_VISUAL_SOURCE_PATTERN)} "
        + " ".join(f"--root {json.dumps(portable_path_text(path))}" for path in watch_roots)
    )
    nightly_visual_proof = latest_nightly.get("visual_proof_receipt") if isinstance(latest_nightly.get("visual_proof_receipt"), dict) else {}
    nightly_visual_requires_native_upgrade = bool(nightly_visual_proof) and not bool(
        nightly_visual_proof.get("suffices_for_native_gold_audit")
    )
    startup_receipt_matches_promoted = bool(startup_receipt.get("artifactDigestMatchesPromoted"))
    startup_receipt_bundle_required = bool(startup_receipt.get("requiresNativeRefresh"))
    operator_summary = operator_summary_for_windows_gold_proof(
        startup_receipt_matches_promoted=startup_receipt_matches_promoted,
        startup_receipt_bundle_required=startup_receipt_bundle_required,
        nightly_visual_requires_native_upgrade=nightly_visual_requires_native_upgrade,
    )
    if not promoted_installer_binding_ready:
        operator_summary = (
            "Windows proof intake is blocked until the current release manifest "
            "binds a concrete promoted Windows installer filename and SHA-256."
        )
    operator_telegram_draft = build_operator_telegram_draft(
        promoted_digest=promoted_digest,
        installer_file_name=installer_file_name,
        preferred_drop_path=preferred_drop_path,
        preferred_extracted_visual_dir=preferred_extracted_visual_dir,
        import_command=import_command,
        auto_import_watch_command=build_auto_import_command(
            request_output,
            wait_seconds=900,
            poll_seconds=10,
            refresh_intake_request=True,
        ),
        discover_visual_source_command=portable_command_text(discover_visual_source_command),
        operator_summary=operator_summary,
        current_failure=current_failure,
        required_surfaces=list(visual_audit.REQUIRED_SURFACES),
        required_dpi_scales=["1.0", "1.5"],
        release_context=release_context,
        request_receipt_path=request_output,
        current_blocker_receipt_path=PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
        current_visual_source_path=str(visual_source.get("path") or ""),
        current_visual_source_artifact_sha256=visual_digest,
        startup_receipt_matches_promoted=startup_receipt_matches_promoted,
        startup_receipt_bundle_required=startup_receipt_bundle_required,
        promoted_binding_ready=promoted_installer_binding_ready,
    )
    bundle_archive_command = (
        f"Compress-Archive -Path {command_root}\\Chummer.Portal\\downloads\\startup-smoke\\startup-smoke-avalonia-win-x64.receipt.json,"
        f"{command_root}\\Chummer.Portal\\downloads\\visual-audit\\windows-installer\\* "
        f"-DestinationPath windows-installer-gold-proof-{promoted_digest[:12] or 'promoted'}.zip -Force"
        if promoted_installer_binding_ready and startup_receipt_bundle_required
        else (
            f"Compress-Archive -Path {command_root}\\Chummer.Portal\\downloads\\visual-audit\\windows-installer\\* "
            f"-DestinationPath windows-installer-gold-proof-{promoted_digest[:12]}.zip -Force"
            if promoted_installer_binding_ready
            else ""
        )
    )
    hub_local_release_proof_command = published_command_text(
        (
            "python3 scripts/materialize_hub_local_release_proof.py "
            f"{DEFAULT_HUB_LOCAL_RELEASE_PROOF_PATH} {DEFAULT_LOCAL_PUBLIC_BASE_URL} "
            f"{DEFAULT_PUBLIC_EDGE_COMPOSE_FILE} {DEFAULT_PUBLIC_EDGE_TIMEOUT_SECONDS} true"
        ),
        public_base_url=DEFAULT_PUBLISHED_PUBLIC_BASE_URL,
    )
    payload = {
        "contract_name": CONTRACT_NAME,
        "visual_audit_verifier_binding": verifier_binding,
        "generated_at_utc": now_iso(),
        "status": status,
        "provider": "native_windows_operator",
        "artifact_kind": "windows_installer_gold_proof_bundle",
        "release_channel_receipt_path": release_context.get("path") or str(release_channel),
        "release_channel_binding_authority": "release_channel_manifest",
        "portal_release_channel_projection": audit.get("releaseProjection"),
        "portal_release_channel_projection_matches_authority": (
            dict(audit.get("releaseProjection") or {}).get("matchesAuthority")
        ),
        "release_version": release_context.get("version") or None,
        "release_channel": release_context.get("channel") or None,
        "release_supportability_state": release_context.get("supportability_state") or None,
        "release_rollout_state": release_context.get("rollout_state") or None,
        "release_published_at": release_context.get("published_at") or None,
        "request_receipt_path": str(request_output),
        "promoted_installer_sha256": promoted_digest,
        "promoted_installer_binding_ready": promoted_installer_binding_ready,
        "promoted_installer_binding_failures": promoted_binding_failures,
        "startup_receipt_bundle_required": startup_receipt_bundle_required,
        "preferred_drop_folder": str(dedicated_drop_root),
        "preferred_zip_name": preferred_zip_name,
        "required_zip_filename": preferred_zip_name,
        "preferred_drop_path": (
            str(preferred_drop_path) if preferred_drop_path is not None else ""
        ),
        "preferred_extracted_visual_dir": str(preferred_extracted_visual_dir),
        "promoted_installer": {
            "file_name": installer_file_name or None,
            "sha256": promoted_digest,
            "path": artifact.get("path"),
            "manifest_sha256": artifact.get("sha256"),
            "actual_sha256": artifact.get("actualSha256"),
        },
        "current_blocker": {
            "receipt": str(PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"),
            "failure": current_failure,
            "current_visual_source_artifact_sha256": visual_digest,
            "current_visual_source_matches_promoted": bool(promoted_digest and visual_digest == promoted_digest),
            "current_visual_source_path": visual_source.get("path"),
            "current_visual_source_sha256": sha256_file(source) if source.is_file() else "",
        },
        "operator_request": {
            "summary": operator_summary,
            "actionable": promoted_installer_binding_ready,
            "promoted_installer_binding_ready": promoted_installer_binding_ready,
            "promoted_installer_binding_failures": promoted_binding_failures,
            "preferred_drop_folder": str(dedicated_drop_root),
            "preferred_zip_name": preferred_zip_name,
            "preferred_drop_path": (
                str(preferred_drop_path) if preferred_drop_path is not None else ""
            ),
            "preferred_extracted_visual_dir": str(preferred_extracted_visual_dir),
            "copy_to_windows": (
                [
                    "Copy the repository checkout or at least Chummer.Portal/downloads/files, Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json, and scripts to the Windows host.",
                    "Do not mark screenshots pass until a human has inspected clipping/readability.",
                    (
                        "The published startup-smoke receipt already matches the promoted installer digest, so you may either zip only the visual-audit/windows-installer folder or copy it extracted to the preferred extracted visual-proof directory."
                        if not startup_receipt_bundle_required
                        else "Include the startup-smoke receipt in the bundle because the current published launch proof still needs a native refresh."
                    ),
                ]
                if promoted_installer_binding_ready
                else []
            ),
            "powershell_commands": (
                [
                    f"{command_root}\\scripts\\capture_windows_installer_gold_proof.ps1 -InstallerPath {command_root}\\Chummer.Portal\\downloads\\files\\{installer_file_name} -DownloadsRoot {command_root}\\Chummer.Portal\\downloads -LaunchInstaller -CaptureVisualAudit -ScaledDpiScale 1.5 -VisualClippingStatus pass -VisualReadabilityStatus pass",
                    bundle_archive_command,
                ]
                if promoted_installer_binding_ready
                else []
            ),
            "discover_visual_source_command": portable_command_text(discover_visual_source_command),
            "required_surfaces": list(visual_audit.REQUIRED_SURFACES),
            "required_dpi_scales": ["1.0", "1.5"],
            "required_host_class_prefix": "native-windows",
            "startup_receipt_bundle_required": startup_receipt_bundle_required,
        },
        "operator_telegram_draft": operator_telegram_draft,
        "artifact_intake": {
            "dedicated_drop_root": str(dedicated_drop_root),
            "dedicated_drop_root_gitignored": is_gitignored_runtime_root(dedicated_drop_root),
            "preferred_drop_path": (
                str(preferred_drop_path) if preferred_drop_path is not None else ""
            ),
            "preferred_extracted_visual_dir": str(preferred_extracted_visual_dir),
            "watcher_launch_mode": "python_subprocess_start_new_session",
            "watcher_state_path": str(DEFAULT_WATCHER_STATE_PATH),
            "watcher_pid_file": str(DEFAULT_WATCHER_PID_FILE),
            "watcher_log_path": str(DEFAULT_WATCHER_LOG_FILE),
            "startup_receipt_bundle_required": startup_receipt_bundle_required,
            "expected_patterns": [
                item
                for item in (
                    DEFAULT_GOLD_PROOF_PATTERN,
                    preferred_zip_name,
                    DEFAULT_VISUAL_SOURCE_PATTERN,
                )
                if item
            ],
            "discover_command": portable_command_text(discover_command),
            "discover_visual_source_command": portable_command_text(discover_visual_source_command),
            "import_command": import_command,
            "auto_import_command": build_auto_import_command(request_output),
            "auto_import_watch_command": build_auto_import_command(
                request_output,
                wait_seconds=900,
                poll_seconds=10,
                refresh_intake_request=True,
            ),
            "watcher_start_command": build_watcher_manager_command(
                "start",
                request_output,
            ),
            "watcher_status_command": build_watcher_manager_command(
                "status",
                request_output,
            ),
            "watcher_stop_command": build_watcher_manager_command(
                "stop",
                request_output,
            ),
            "auto_import_roots": [portable_path_text(path) for path in watch_roots],
            "post_import_verify_command": bound_visual_audit_verify_command,
            "post_import_verify_note": POST_IMPORT_VERIFY_NOTE,
        },
        "expected_artifact_patterns": [
            item
            for item in (
                DEFAULT_GOLD_PROOF_PATTERN,
                preferred_zip_name,
                DEFAULT_VISUAL_SOURCE_PATTERN,
            )
            if item
        ],
        "discover_visual_source_command": portable_command_text(discover_visual_source_command),
        "drop_roots_checked": [portable_path_text(path) for path in scan_roots],
        "last_discovery": {
            "gold_proof_zip": {
                "status": "found" if gold_proof_candidates else "not_found",
                "count": len(gold_proof_candidates),
                "files": [file_row(path) for path in gold_proof_candidates[:20]],
            },
            "visual_sources": {
                "status": "found" if importable_visual_sources else "not_found",
                "count": len(importable_visual_sources),
                "matching_promoted_count": len(matching_visual_sources),
                "files": importable_visual_sources[:20],
            },
        },
        "latest_nightly_visual_proof_handoff": latest_nightly,
        "import_command": import_command,
        "post_import_gates": [
            bound_visual_audit_verify_command,
            "python3 scripts/materialize_windows_installer_visual_audit_intake_request.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
            "python3 scripts/verify_windows_installer_visual_audit_intake_request.py",
            "python3 scripts/verify_flagship_product_readiness_gate.py --summary-output .codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json",
            "python3 scripts/materialize_google_oauth_linking_operator_evidence_request.py --base-url https://chummer.run",
            "python3 scripts/materialize_google_oauth_linking_proof.py --base-url https://chummer.run",
            "python3 scripts/verify_google_oauth_linking_proof.py",
            "python3 scripts/materialize_ea_operator_readiness.py",
            "python3 scripts/verify_ea_operator_readiness.py",
            "python3 scripts/materialize_mymedia_public_surface.py",
            "python3 scripts/verify_mymedia_public_surface.py",
            "python3 scripts/sync_important_work_to_teable.py --sync",
            "python3 scripts/materialize_release_ready_receipt.py --force-global-verifier",
            "python3 scripts/materialize_operator_release_dashboard.py",
            hub_local_release_proof_command,
            "python3 scripts/final_gold_janitor.py --skip-materializers",
            "python3 ../scripts/release/_release_gate_common.py",
            "python3 ../scripts/attempt_flagship_public_stable_promotion.py --output ../.codex-studio/published/FLAGSHIP_PUBLIC_STABLE_PROMOTION_ATTEMPT.generated.json",
            "python3 ../scripts/materialize_chummer_flagship_surface_stack.py --output ../.codex-studio/published/CHUMMER_FLAGSHIP_SURFACE_STACK.generated.json",
            "python3 ../scripts/verify_chummer_flagship_surface_stack.py --receipt ../.codex-studio/published/CHUMMER_FLAGSHIP_SURFACE_STACK.generated.json --require-flagship-pass",
            "python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp \"$(date --iso-8601=seconds)\"",
        ],
        "secrets_redacted": True,
        "direct_telegram_sent": False,
        "direct_telegram_reason": "Not sent without an explicit operator-send instruction in this turn.",
    }
    payload["summary"] = payload["operator_request"]["summary"]
    payload["artifact"] = payload["promoted_installer"]
    payload["intake"] = payload["artifact_intake"]
    payload["preferredDropPath"] = payload["preferred_drop_path"]
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize an operator intake request for the native Windows installer visual audit.")
    parser.add_argument("--release-channel", type=Path, default=visual_audit.DEFAULT_RELEASE_CHANNEL)
    parser.add_argument(
        "--portal-release-channel",
        type=Path,
        default=visual_audit.DEFAULT_PORTAL_RELEASE_CHANNEL,
    )
    parser.add_argument("--downloads-root", type=Path, default=visual_audit.DEFAULT_DOWNLOADS_ROOT)
    parser.add_argument("--startup-receipt", type=Path, default=visual_audit.DEFAULT_STARTUP_RECEIPT)
    parser.add_argument("--source", type=Path, default=visual_audit.DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--nightly-root", type=Path, default=DEFAULT_NIGHTLY_ROOT)
    parser.add_argument("--dedicated-drop-root", type=Path, default=DEFAULT_DEDICATED_DROP_ROOT)
    parser.add_argument("--discovery-root", action="append", default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = args.output.expanduser().resolve()
    roots = [Path(os.path.expandvars(os.path.expanduser(item))) for item in (args.discovery_root or [])]
    auto_import_roots: list[Path] | None = None
    recursive_scan_roots: list[Path] | None = None
    if not roots:
        roots = list(DEFAULT_DISCOVERY_ROOTS)
        auto_import_roots = artifact_discovery_roots(args.dedicated_drop_root)
        recursive_scan_roots = [args.dedicated_drop_root]
    payload = build_request(
        release_channel=args.release_channel,
        portal_release_channel=args.portal_release_channel,
        downloads_root=args.downloads_root,
        startup_receipt=args.startup_receipt,
        source=args.source,
        request_output=output_path,
        discovery_roots=roots,
        nightly_root=args.nightly_root,
        dedicated_drop_root=args.dedicated_drop_root,
        auto_import_roots=auto_import_roots,
        recursive_scan_roots=recursive_scan_roots,
    )
    payload["request_receipt_path"] = str(output_path)
    operator_telegram_draft = (
        payload.get("operator_telegram_draft")
        if isinstance(payload.get("operator_telegram_draft"), dict)
        else {}
    )
    if operator_telegram_draft:
        operator_telegram_draft["request_receipt_path"] = str(output_path)
        payload["operator_telegram_draft_materialized"] = materialize_operator_telegram_draft(operator_telegram_draft)
        materialized_draft = payload["operator_telegram_draft_materialized"]
        payload["operator_ask_text_path"] = str(
            materialized_draft.get("operator_ask_text_path")
            or materialized_draft.get("current_message_path")
            or ""
        )
        payload["operator_ask_metadata_path"] = str(
            materialized_draft.get("operator_ask_metadata_path")
            or operator_telegram_draft.get("current_metadata_path")
            or ""
        )
        payload["operator_ask_send_command"] = str(
            materialized_draft.get("operator_ask_send_command")
            or materialized_draft.get("send_command")
            or ""
        )
        payload["operator_ask_receipt_name"] = str(
            materialized_draft.get("operator_ask_receipt_name")
            or materialized_draft.get("receipt_name")
            or ""
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"windows_installer_visual_audit_intake_request:{payload['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
