#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "scripts"))
import verify_windows_installer_visual_audit as visual_audit  # noqa: E402
from published_path_hygiene import portable_command_text, portable_path_text


PUBLISHED_ROOT = ROOT / ".codex-studio" / "published"
DEFAULT_OUTPUT = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
CONTRACT_NAME = "chummer.windows_installer_visual_audit_intake_request.v1"
DEFAULT_DEDICATED_DROP_ROOT = ROOT / ".state" / "incoming_windows_installer_gold_proof"
DEFAULT_OPERATOR_DRAFT_ROOT = ROOT / "_completion" / "windows_installer_visual_audit"
CURRENT_OPERATOR_ASK_TEXT_NAME = "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"
CURRENT_OPERATOR_ASK_METADATA_NAME = "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"
DEFAULT_DISCOVERY_ROOTS = (
    DEFAULT_DEDICATED_DROP_ROOT,
    Path("/tmp"),
)
DEFAULT_GOLD_PROOF_PATTERN = "*windows-installer-gold-proof*.zip"
DEFAULT_VISUAL_SOURCE_PATTERN = "*WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
DEFAULT_NIGHTLY_ROOT = Path("/docker/chummercomplete/_staging")
DISCOVERY_MAX_DEPTH = 6


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
    return unique_paths(
        [
            dedicated_drop_root,
            Path("/tmp"),
            home / "Downloads",
            home / "pCloud Drive" / "EA",
        ]
    )


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
    token = (promoted_digest or "promoted")[:12] or "promoted"
    return f"windows-installer-gold-proof-{token}-operator-ask"


def current_operator_ask_text_path(operator_draft_root: Path | None = None) -> Path:
    return (operator_draft_root or DEFAULT_OPERATOR_DRAFT_ROOT) / CURRENT_OPERATOR_ASK_TEXT_NAME


def current_operator_ask_metadata_path(operator_draft_root: Path | None = None) -> Path:
    return (operator_draft_root or DEFAULT_OPERATOR_DRAFT_ROOT) / CURRENT_OPERATOR_ASK_METADATA_NAME


def build_operator_telegram_text(
    *,
    promoted_digest: str,
    installer_file_name: str,
    preferred_drop_path: Path,
    import_command: str,
    auto_import_watch_command: str,
    operator_summary: str,
    current_failure: str,
    required_surfaces: list[str],
    required_dpi_scales: list[str],
    release_context: dict[str, str],
    startup_receipt_matches_promoted: bool = False,
    current_visual_source_path: str = "",
    current_visual_source_artifact_sha256: str = "",
) -> str:
    surface_summary = ", ".join(required_surfaces) if required_surfaces else "install-progress and completion"
    dpi_summary = ", ".join(required_dpi_scales) if required_dpi_scales else "1.0 and 1.5"
    release_summary = (
        f"{release_context.get('version') or 'unknown'}"
        f" | channel={release_context.get('channel') or 'unknown'}"
        f" | rollout={release_context.get('rollout_state') or 'unknown'}"
        f" | supportability={release_context.get('supportability_state') or 'unknown'}"
    )
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
    if current_visual_source_artifact_sha256:
        lines.append(
            "Current visual source digest: "
            f"{current_visual_source_artifact_sha256}"
            + (f" ({current_visual_source_path})" if current_visual_source_path else "")
        )
    lines.extend(
        [
            "",
            "Needed from a native Windows host:",
            f"1. Run the promoted installer and capture visual proof for: {surface_summary}.",
            f"2. Capture both DPI scales: {dpi_summary}.",
            f"3. Zip the startup-smoke receipt plus Chummer.Portal/downloads/visual-audit/windows-installer as {preferred_drop_path.name}.",
            f"4. Drop the zip here: {preferred_drop_path}",
            "",
            f"After the bundle is available, import it with: {import_command}",
        ]
    )
    if auto_import_watch_command:
        lines.append(f"Or watch for the bundle automatically with: {auto_import_watch_command}")
    return "\n".join(lines).strip() + "\n"


def build_operator_telegram_draft(
    *,
    promoted_digest: str,
    installer_file_name: str,
    preferred_drop_path: Path,
    import_command: str,
    auto_import_watch_command: str = "",
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
) -> dict[str, Any]:
    stem = operator_ask_stem(promoted_digest)
    draft_root = DEFAULT_OPERATOR_DRAFT_ROOT
    message_path = draft_root / f"{stem}.txt"
    metadata_path = draft_root / f"{stem}.generated.json"
    current_message_path = current_operator_ask_text_path(draft_root)
    current_metadata_path = current_operator_ask_metadata_path(draft_root)
    receipt_name = f"{stem}.receipt.json"
    message_text = build_operator_telegram_text(
        promoted_digest=promoted_digest,
        installer_file_name=installer_file_name,
        preferred_drop_path=preferred_drop_path,
        import_command=import_command,
        auto_import_watch_command=auto_import_watch_command,
        operator_summary=operator_summary,
        current_failure=current_failure,
        required_surfaces=required_surfaces,
        required_dpi_scales=required_dpi_scales,
        release_context=release_context or {},
        startup_receipt_matches_promoted=startup_receipt_matches_promoted,
        current_visual_source_path=current_visual_source_path,
        current_visual_source_artifact_sha256=current_visual_source_artifact_sha256,
    )
    return {
        "status": "prepared_not_sent",
        "message_path": str(message_path),
        "metadata_path": str(metadata_path),
        "current_message_path": str(current_message_path),
        "current_metadata_path": str(current_metadata_path),
        "message_text": message_text,
        "message_sha256": sha256_text(message_text),
        "message_preview": text_preview(message_text),
        "receipt_name": receipt_name,
        "send_command": (
            "python3 scripts/send_telegram_message_via_ea.py "
            f"--text-file {message_path} --receipt-name {receipt_name}"
        ),
        "request_receipt_path": str(request_receipt_path) if request_receipt_path else "",
        "promoted_installer_sha256": promoted_digest,
        "preferred_drop_path": str(preferred_drop_path),
        "preferred_zip_name": preferred_drop_path.name,
        "import_command": import_command,
        "auto_import_watch_command": auto_import_watch_command,
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
        "direct_send_allowed": False,
        "direct_send_reason": "Not sent without an explicit operator-send instruction in this turn.",
    }


def build_auto_import_command(
    *,
    wait_seconds: float | None = None,
    poll_seconds: float | None = None,
    refresh_intake_request: bool = False,
) -> str:
    command = (
        "python3 scripts/auto_import_windows_installer_gold_proof.py "
        "--intake-request .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
    )
    if wait_seconds is not None:
        command += f" --wait-seconds {int(wait_seconds)}"
    if poll_seconds is not None:
        command += f" --poll-seconds {int(poll_seconds)}"
    if refresh_intake_request:
        command += " --refresh-intake-request"
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
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
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
            try:
                resolved = candidate.resolve()
            except OSError:
                resolved = candidate
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
    screenshots = payload.get("screenshots") if isinstance(payload.get("screenshots"), list) else []
    artifact_digest = normalize_digest(payload.get("artifactDigest") or payload.get("artifactSha256"))
    notes = str(payload.get("notes") or "").strip()
    row = file_row(path)
    row.update(
        {
            "status": payload.get("status"),
            "artifact_sha256": artifact_digest,
            "matches_promoted_installer": bool(promoted_digest and artifact_digest == promoted_digest),
            "screenshot_count": len(screenshots),
            "suffices_for_native_gold_audit": bool(
                promoted_digest
                and artifact_digest == promoted_digest
                and len(screenshots) >= len(visual_audit.REQUIRED_SURFACES) * 2
                and "proxy" not in notes.lower()
                and "fallback" not in notes.lower()
            ),
            "notes": notes,
        }
    )
    return row


def build_request(
    *,
    release_channel: Path,
    downloads_root: Path,
    startup_receipt: Path,
    source: Path,
    discovery_roots: list[Path],
    nightly_root: Path,
    dedicated_drop_root: Path = DEFAULT_DEDICATED_DROP_ROOT,
    auto_import_roots: list[Path] | None = None,
    recursive_scan_roots: list[Path] | None = None,
) -> dict[str, Any]:
    dedicated_drop_root.mkdir(parents=True, exist_ok=True)
    scan_roots = unique_paths(list(discovery_roots))
    watch_roots = unique_paths(list(auto_import_roots or scan_roots))
    recursive_roots = unique_paths(list(scan_roots if recursive_scan_roots is None else recursive_scan_roots))

    audit = visual_audit.build_payload(
        release_channel_path=release_channel,
        downloads_root=downloads_root,
        startup_receipt_path=startup_receipt,
        source_path=source,
    )
    release_context = read_release_context(release_channel)
    artifact = audit.get("artifact") if isinstance(audit.get("artifact"), dict) else {}
    visual_source = audit.get("visualAuditSource") if isinstance(audit.get("visualAuditSource"), dict) else {}
    promoted_digest = normalize_digest(artifact.get("sha256"))
    visual_digest = normalize_digest(visual_source.get("artifactSha256"))
    gold_proof_candidates = discover_files(
        DEFAULT_GOLD_PROOF_PATTERN,
        scan_roots,
        recursive_roots=recursive_roots,
    )
    visual_source_candidates = discover_files(
        DEFAULT_VISUAL_SOURCE_PATTERN,
        scan_roots,
        recursive_roots=recursive_roots,
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
            "visual_proof_receipt": (
                latest_nightly_visual_proof_row(nightly_visual_proof_receipt_path, promoted_digest)
                if nightly_visual_proof_receipt_path.is_file()
                else {}
            ),
        }

    status = "not_required" if audit.get("status") == "pass" else "external_artifact_required"
    command_root = "${REPO_ROOT}"
    current_failure = "; ".join(str(item) for item in audit.get("failures") or [])
    preferred_zip_name = f"windows-installer-gold-proof-{promoted_digest[:12] or 'promoted'}.zip"
    preferred_drop_path = dedicated_drop_root / preferred_zip_name
    import_command = (
        "python3 scripts/import_windows_installer_gold_proof_artifact.py "
        f"{preferred_drop_path} --verify"
    )
    discover_command = (
        "python3 ~/.codex/skills/ea-artifact-intake/scripts/artifact_intake.py discover "
        "--pattern '*windows-installer-gold-proof*.zip' "
        + " ".join(f"--root {json.dumps(portable_path_text(path))}" for path in watch_roots)
    )
    nightly_visual_proof = (
        latest_nightly.get("visual_proof_receipt")
        if isinstance(latest_nightly.get("visual_proof_receipt"), dict)
        else {}
    )
    operator_summary = (
        "Run the promoted Windows installer on a native Windows host and provide the gold proof bundle."
    )
    if nightly_visual_proof and not nightly_visual_proof.get("suffices_for_native_gold_audit"):
        operator_summary = (
            "Run the promoted Windows installer on a native Windows host and provide the gold proof bundle. "
            "The latest staged nightly proof is still incomplete or does not match the promoted installer digest."
        )
    operator_telegram_draft = build_operator_telegram_draft(
        promoted_digest=promoted_digest,
        installer_file_name=str(artifact.get("fileName") or ""),
        preferred_drop_path=preferred_drop_path,
        import_command=import_command,
        auto_import_watch_command=build_auto_import_command(
            wait_seconds=900,
            poll_seconds=10,
            refresh_intake_request=True,
        ),
        operator_summary=operator_summary,
        current_failure=current_failure,
        required_surfaces=list(visual_audit.REQUIRED_SURFACES),
        required_dpi_scales=["1.0", "1.5"],
        release_context=release_context,
        request_receipt_path=DEFAULT_OUTPUT,
        current_blocker_receipt_path=PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
        current_visual_source_path=str(visual_source.get("path") or ""),
        current_visual_source_artifact_sha256=visual_digest,
        startup_receipt_matches_promoted=bool((audit.get("startupReceipt") or {}).get("artifactDigest") and normalize_digest((audit.get("startupReceipt") or {}).get("artifactDigest")) == promoted_digest),
    )
    payload = {
        "contract_name": CONTRACT_NAME,
        "generated_at_utc": now_iso(),
        "status": status,
        "provider": "native_windows_operator",
        "artifact_kind": "windows_installer_gold_proof_bundle",
        "release_channel_receipt_path": release_context.get("path") or str(release_channel),
        "release_version": release_context.get("version") or None,
        "release_channel": release_context.get("channel") or None,
        "release_supportability_state": release_context.get("supportability_state") or None,
        "release_rollout_state": release_context.get("rollout_state") or None,
        "release_published_at": release_context.get("published_at") or None,
        "request_receipt_path": str(DEFAULT_OUTPUT),
        "promoted_installer_sha256": promoted_digest,
        "preferred_drop_folder": str(dedicated_drop_root),
        "preferred_zip_name": preferred_zip_name,
        "required_zip_filename": preferred_zip_name,
        "preferred_drop_path": str(preferred_drop_path),
        "promoted_installer": {
            "file_name": artifact.get("fileName"),
            "sha256": promoted_digest,
            "path": artifact.get("path"),
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
            "preferred_drop_folder": str(dedicated_drop_root),
            "preferred_zip_name": preferred_zip_name,
            "preferred_drop_path": str(preferred_drop_path),
            "copy_to_windows": [
                "Copy the repository checkout or at least Chummer.Portal/downloads/files, Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json, and scripts to the Windows host.",
                "Do not mark screenshots pass until a human has inspected clipping/readability.",
            ],
            "powershell_commands": [
                f"{command_root}\\scripts\\capture_windows_installer_gold_proof.ps1 -InstallerPath {command_root}\\Chummer.Portal\\downloads\\files\\{artifact.get('fileName')} -DownloadsRoot {command_root}\\Chummer.Portal\\downloads -LaunchInstaller -CaptureVisualAudit -ScaledDpiScale 1.5 -VisualClippingStatus pass -VisualReadabilityStatus pass",
                f"Compress-Archive -Path {command_root}\\Chummer.Portal\\downloads\\startup-smoke\\startup-smoke-avalonia-win-x64.receipt.json,{command_root}\\Chummer.Portal\\downloads\\visual-audit\\windows-installer\\* -DestinationPath {preferred_zip_name} -Force",
            ],
            "required_surfaces": list(visual_audit.REQUIRED_SURFACES),
            "required_dpi_scales": ["1.0", "1.5"],
            "required_host_class_prefix": "native-windows",
        },
        "operator_telegram_draft": operator_telegram_draft,
        "artifact_intake": {
            "dedicated_drop_root": str(dedicated_drop_root),
            "dedicated_drop_root_gitignored": is_gitignored_runtime_root(dedicated_drop_root),
            "preferred_drop_path": str(preferred_drop_path),
            "expected_patterns": [
                DEFAULT_GOLD_PROOF_PATTERN,
                preferred_zip_name,
                DEFAULT_VISUAL_SOURCE_PATTERN,
            ],
            "discover_command": portable_command_text(discover_command),
            "import_command": import_command,
            "auto_import_command": build_auto_import_command(),
            "auto_import_watch_command": build_auto_import_command(
                wait_seconds=900,
                poll_seconds=10,
                refresh_intake_request=True,
            ),
            "auto_import_roots": [portable_path_text(path) for path in watch_roots],
            "post_import_verify_command": (
                "python3 scripts/verify_windows_installer_visual_audit.py "
                "--output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"
            ),
        },
        "expected_artifact_patterns": [
            DEFAULT_GOLD_PROOF_PATTERN,
            preferred_zip_name,
            DEFAULT_VISUAL_SOURCE_PATTERN,
        ],
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
            "python3 scripts/verify_windows_installer_visual_audit.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
            "python3 scripts/materialize_windows_installer_visual_audit_intake_request.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
            "python3 scripts/verify_windows_installer_visual_audit_intake_request.py",
            "python3 scripts/materialize_release_ready_receipt.py",
            "python3 scripts/materialize_operator_release_dashboard.py",
            "python3 scripts/verify_flagship_product_readiness_gate.py --summary-output .codex-studio/published/FLAGSHIP_PRODUCT_READINESS_GATE.generated.json",
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
        downloads_root=args.downloads_root,
        startup_receipt=args.startup_receipt,
        source=args.source,
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
