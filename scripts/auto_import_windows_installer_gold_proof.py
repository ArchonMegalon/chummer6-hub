#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from published_path_hygiene import expand_portable_path, portable_path_text
from writable_temp_root import configure_process_tmpdir


ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = ROOT / ".codex-studio" / "published"
DEFAULT_INTAKE_REQUEST = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
DEFAULT_OUTPUT = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
INTAKE_MATERIALIZER = ROOT / "scripts" / "materialize_windows_installer_visual_audit_intake_request.py"
AUTO_IMPORT_SIDE_EFFECTS_PAUSE_FLAG = ROOT / ".state" / "windows_installer_visual_audit_paused.flag"
DISCOVERY_MAX_DEPTH = 6
STALE_DIRECTORY_SAMPLE_LIMIT = 5
STAGE_VISUAL_PROOF_RECEIPT_NAME = "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"
PASS_STATUSES = {"pass", "passed", "ready"}

configure_process_tmpdir(workspace_root=ROOT.parent)

try:
    import import_windows_installer_gold_proof_artifact as proof_importer
except ModuleNotFoundError:
    import import_windows_installer_gold_proof_artifact as proof_importer

AUTO_IMPORTER_PROGRAM_BINDING_AT_LOAD = proof_importer.program_file_binding(
    Path(__file__),
    "windows_installer_gold_proof_auto_importer",
)
INTAKE_MATERIALIZER_PROGRAM_BINDING_AT_LOAD = proof_importer.program_file_binding(
    INTAKE_MATERIALIZER,
    "windows_installer_visual_audit_intake_materializer",
)


def program_bindings_for_receipt() -> dict[str, Any]:
    _bundle_bytes, dependency_binding = (
        proof_importer.production_code_owned_python_dependency_bundle()
    )
    return {
        "importer": dict(proof_importer.IMPORTER_PROGRAM_BINDING_AT_LOAD),
        "auto_importer": dict(AUTO_IMPORTER_PROGRAM_BINDING_AT_LOAD),
        "intake_materializer": dict(INTAKE_MATERIALIZER_PROGRAM_BINDING_AT_LOAD),
        "python_dependency_bundle": dependency_binding,
        "sealed_python_launcher": {
            "sha256": proof_importer.SEALED_PYTHON_LAUNCHER_SHA256,
            "size_bytes": len(
                proof_importer.SEALED_PYTHON_LAUNCHER_SOURCE.encode("utf-8")
            ),
        },
    }


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


SENSITIVE_WAITING_RECEIPT_KEYS = {
    "argv",
    "bound_argv",
    "cwd",
    "environment",
    "exception",
    "exception_message",
    "execution_argv",
    "command",
    "import_command",
    "discover_command",
    "auto_import_command",
    "auto_import_watch_command",
    "post_import_verify_command",
    "manual_import_command",
    "message",
    "message_text",
    "operator_summary",
    "operator_telegram_draft",
    "operator_telegram_send_command",
    "promoted_installer_binding_failures",
    "raw_candidate",
    "raw_candidates",
    "raw_exception",
    "raw_result",
    "raw_results",
    "send_command",
    "stderr",
    "stdout",
    "traceback",
}
SENSITIVE_WAITING_RECEIPT_KEY_MARKERS = (
    "api_key",
    "authorization",
    "cookie",
    "credential",
    "draft",
    "password",
    "private_key",
    "secret",
    "token",
)


def redacted_value_receipt(value: Any) -> dict[str, Any]:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError):
        encoded = str(value).encode("utf-8", errors="replace")
    return {
        "redacted": True,
        "value_type": type(value).__name__,
        "byte_count": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest().lower(),
        "present": bool(value),
    }


def redact_waiting_receipt_value(value: Any, *, key: str = "") -> Any:
    normalized_key = key.strip().casefold()
    key_is_sensitive = (
        normalized_key in SENSITIVE_WAITING_RECEIPT_KEYS
        or any(marker in normalized_key for marker in SENSITIVE_WAITING_RECEIPT_KEY_MARKERS)
    )
    if key_is_sensitive and isinstance(value, (str, bytes, dict, list, tuple)):
        return redacted_value_receipt(value)
    if isinstance(value, dict):
        return {
            str(child_key): redact_waiting_receipt_value(
                child_value,
                key=str(child_key),
            )
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [redact_waiting_receipt_value(item) for item in value]
    if isinstance(value, tuple):
        return [redact_waiting_receipt_value(item) for item in value]
    return value


def auto_import_side_effects_paused() -> bool:
    return AUTO_IMPORT_SIDE_EFFECTS_PAUSE_FLAG.is_file()


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def materialize_intake_request(path: Path, downloads_root: Path) -> dict[str, Any]:
    if proof_importer.sha256_file(proof_importer.PYTHON_EXECUTABLE) != str(
        proof_importer.PYTHON_PROGRAM_BINDING_AT_LOAD["sha256"]
    ):
        raise SystemExit("code-owned Python interpreter binding drifted before intake refresh")
    if proof_importer.sha256_file(INTAKE_MATERIALIZER) != str(
        INTAKE_MATERIALIZER_PROGRAM_BINDING_AT_LOAD["sha256"]
    ):
        raise SystemExit("intake materializer program bytes drifted before refresh")
    bound_argv = [
        str(proof_importer.PYTHON_EXECUTABLE),
        str(INTAKE_MATERIALIZER),
        "--downloads-root",
        str(downloads_root),
        "--output",
        str(path),
    ]
    completed, _sealed_execution = proof_importer.run_bound_python_subprocess(
        bound_argv,
        interpreter_sha256=str(
            proof_importer.PYTHON_PROGRAM_BINDING_AT_LOAD["sha256"]
        ),
        script_sha256=str(INTAKE_MATERIALIZER_PROGRAM_BINDING_AT_LOAD["sha256"]),
        cwd=ROOT,
        environment=proof_importer.code_owned_post_import_environment(),
    )
    if proof_importer.sha256_file(proof_importer.PYTHON_EXECUTABLE) != str(
        proof_importer.PYTHON_PROGRAM_BINDING_AT_LOAD["sha256"]
    ):
        raise SystemExit("code-owned Python interpreter binding drifted during intake refresh")
    if proof_importer.sha256_file(INTAKE_MATERIALIZER) != str(
        INTAKE_MATERIALIZER_PROGRAM_BINDING_AT_LOAD["sha256"]
    ):
        raise SystemExit("intake materializer program bytes drifted during refresh")
    if completed.returncode != 0:
        stdout_receipt = proof_importer.redacted_stream_receipt(completed.stdout)
        stderr_receipt = proof_importer.redacted_stream_receipt(completed.stderr)
        raise SystemExit(
            "failed to materialize windows installer intake request: "
            f"returncode={completed.returncode}; "
            f"stdout_receipt={json.dumps(stdout_receipt, sort_keys=True)}; "
            f"stderr_receipt={json.dumps(stderr_receipt, sort_keys=True)}"
        )
    payload = load_json(path)
    if not payload:
        raise SystemExit(f"materialized intake request is unreadable: {path}")
    return payload


def fallback_auto_import_command(
    intake_request: Path,
    *,
    wait_seconds: float | None = None,
    poll_seconds: float | None = None,
    refresh_intake_request: bool = False,
) -> str:
    command = (
        "python3 scripts/auto_import_windows_installer_gold_proof.py "
        f"--intake-request {intake_request}"
    )
    if wait_seconds is not None:
        command += f" --wait-seconds {int(wait_seconds)}"
    if poll_seconds is not None:
        command += f" --poll-seconds {int(poll_seconds)}"
    if refresh_intake_request:
        command += " --refresh-intake-request"
    return command


def ensure_intake_request(path: Path, refresh: bool, downloads_root: Path) -> dict[str, Any]:
    if refresh or not path.is_file():
        return materialize_intake_request(path, downloads_root)
    payload = load_json(path)
    if payload:
        return payload
    return materialize_intake_request(path, downloads_root)


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


def discovery_roots_from_intake(intake: dict[str, Any]) -> list[Path]:
    artifact_intake = intake.get("artifact_intake") if isinstance(intake.get("artifact_intake"), dict) else {}
    roots: list[Path] = []
    for raw in intake.get("drop_roots_checked") or []:
        text = str(raw or "").strip()
        if text:
            roots.append(expand_portable_path(text))
    for raw in artifact_intake.get("auto_import_roots") or []:
        text = str(raw or "").strip()
        if text:
            roots.append(expand_portable_path(text))
    for key in ("dedicated_drop_root", "preferred_drop_path"):
        text = str(artifact_intake.get(key) or intake.get(key) or "").strip()
        if not text:
            continue
        path = expand_portable_path(text)
        roots.append(path.parent if key == "preferred_drop_path" else path)
    return unique_paths(roots)


def recursive_scan_roots_from_intake(intake: dict[str, Any]) -> list[Path]:
    artifact_intake = intake.get("artifact_intake") if isinstance(intake.get("artifact_intake"), dict) else {}
    roots: list[Path] = []
    dedicated = str(artifact_intake.get("dedicated_drop_root") or "").strip()
    if dedicated:
        roots.append(Path(dedicated))
    temp_root = Path(tempfile.gettempdir())
    for raw in artifact_intake.get("auto_import_roots") or []:
        text = str(raw or "").strip()
        if not text:
            continue
        candidate = expand_portable_path(text)
        if paths_match(candidate, temp_root):
            roots.append(candidate)
    return unique_paths(roots)


def paths_match(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left == right


def should_recurse_root(search_root: Path, recursive_roots: list[Path]) -> bool:
    return any(paths_match(search_root, root) for root in recursive_roots)


def expected_exact_names(intake: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for raw in intake.get("expected_artifact_patterns") or []:
        text = str(raw or "").strip()
        if text and "*" not in text and "?" not in text:
            names.append(Path(text).name)
    artifact_intake = intake.get("artifact_intake") if isinstance(intake.get("artifact_intake"), dict) else {}
    preferred = str(artifact_intake.get("preferred_drop_path") or intake.get("preferred_drop_path") or "").strip()
    if preferred:
        names.append(Path(preferred).name)
    seen: set[str] = set()
    result: list[str] = []
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        result.append(name)
    return result


def expected_glob_patterns(intake: dict[str, Any]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in intake.get("expected_artifact_patterns") or []:
        text = str(raw or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def required_zip_filename(intake: dict[str, Any]) -> str:
    artifact_intake = intake.get("artifact_intake") if isinstance(intake.get("artifact_intake"), dict) else {}
    return str(
        intake.get("required_zip_filename")
        or intake.get("preferred_zip_name")
        or Path(str(artifact_intake.get("preferred_drop_path") or "")).name
        or ""
    ).strip()


def annotate_candidate_row(row: dict[str, Any], required_zip_name: str) -> dict[str, Any]:
    candidate_path = Path(str(row.get("path") or ""))
    if candidate_path.name.lower().endswith(".zip"):
        row["is_zip_candidate"] = True
        row["required_zip_filename"] = required_zip_name
        row["required_zip_filename_match"] = bool(required_zip_name and candidate_path.name == required_zip_name)
    return row


def artifact_root_from_visual_source(source: Path) -> Path:
    resolved = source.resolve()
    parts = resolved.parts
    if "Chummer.Portal" not in parts:
        return resolved.parent
    index = parts.index("Chummer.Portal")
    if index <= 0:
        return resolved.parent
    return Path(*parts[:index])


def visual_source_candidate_path(candidate_root: Path) -> Path:
    return candidate_root / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer" / proof_importer.VISUAL_SOURCE_NAME


def portable_visual_source_candidate_path(candidate_root: Path) -> Path:
    return candidate_root / proof_importer.VISUAL_SOURCE_NAME


def startup_receipt_candidate_path(candidate_root: Path) -> Path:
    return candidate_root / "Chummer.Portal" / "downloads" / "startup-smoke" / proof_importer.STARTUP_RECEIPT_NAME


def startup_receipt_bundle_required(intake: dict[str, Any]) -> bool:
    artifact_intake = intake.get("artifact_intake") if isinstance(intake.get("artifact_intake"), dict) else {}
    operator_request = intake.get("operator_request") if isinstance(intake.get("operator_request"), dict) else {}
    for value in (
        artifact_intake.get("startup_receipt_bundle_required"),
        operator_request.get("startup_receipt_bundle_required"),
        intake.get("startup_receipt_bundle_required"),
    ):
        if isinstance(value, bool):
            return value
    return True


def resolved_visual_source_candidate_path(candidate_root: Path, intake: dict[str, Any]) -> Path | None:
    standard_path = visual_source_candidate_path(candidate_root)
    if standard_path.is_file():
        return standard_path
    if startup_receipt_bundle_required(intake):
        return None
    portable_path = portable_visual_source_candidate_path(candidate_root)
    if portable_path.is_file():
        return portable_path
    return None


def directory_candidate_complete(candidate_root: Path, intake: dict[str, Any], *, visual_source: Path | None = None) -> bool:
    if visual_source is None:
        visual_source = resolved_visual_source_candidate_path(candidate_root, intake)
    if visual_source is None or not visual_source.is_file():
        return False
    if startup_receipt_bundle_required(intake):
        return startup_receipt_candidate_path(candidate_root).is_file()
    return True


def file_row(path: Path, discovery_kind: str, priority: int) -> dict[str, Any]:
    try:
        stat = path.stat()
        is_dir = path.is_dir()
        mtime_utc = datetime.fromtimestamp(stat.st_mtime, UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        mtime_epoch = float(stat.st_mtime)
        size_bytes = stat.st_size
        exists = True
    except OSError:
        is_dir = False
        mtime_utc = ""
        mtime_epoch = 0.0
        size_bytes = 0
        exists = False
    return {
        "path": str(path),
        "discovery_kind": discovery_kind,
        "priority": priority,
        "mtime_utc": mtime_utc,
        "mtime_epoch": mtime_epoch,
        "size_bytes": size_bytes,
        "is_dir": is_dir,
        "exists": exists,
    }


def normalized_sha256_token(value: Any) -> str:
    return str(value or "").strip().lower().removeprefix("sha256:")


def normalized_token(value: Any) -> str:
    return str(value or "").strip().lower()


def promoted_digest_from_intake(intake: dict[str, Any]) -> str:
    artifact = intake.get("promoted_installer") if isinstance(intake.get("promoted_installer"), dict) else {}
    return normalized_sha256_token(
        intake.get("promoted_installer_sha256")
        or artifact.get("sha256")
        or artifact.get("actual_sha256")
        or ""
    )


def startup_receipt_effective_pass(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").strip().lower()
    failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
    failed_gates = payload.get("failed_gates") if isinstance(payload.get("failed_gates"), list) else []
    disposition = normalized_token(payload.get("verificationDisposition"))
    skip_class = normalized_token(payload.get("skipClass"))
    return (
        status in PASS_STATUSES
        and not failures
        and not failed_gates
        and payload.get("pass") is not False
        and disposition != "incompatible_host"
        and skip_class != "incompatible_host"
    )


def directory_candidate_row(
    candidate_root: Path,
    promoted_digest: str,
    priority: int,
    intake_request: Path,
    intake: dict[str, Any],
    visual_source: Path | None = None,
) -> dict[str, Any]:
    row = file_row(candidate_root, "visual_source_directory", priority)
    row.update(
        {
            "matches_promoted_installer": False,
            "auto_import_ready": False,
            "inspection_status": "rejected_directory_artifact",
            "rejection_code": "zip_bundle_required",
        }
    )
    return row


def zip_candidate_row(
    candidate_zip: Path,
    discovery_kind: str,
    promoted_digest: str,
    priority: int,
    intake_request: Path,
    intake: dict[str, Any],
) -> dict[str, Any]:
    row = annotate_candidate_row(file_row(candidate_zip, discovery_kind, priority), required_zip_filename(intake))
    row["manual_import_command"] = manual_import_command(candidate_zip, intake_request)
    try:
        with tempfile.TemporaryDirectory(prefix="windows-installer-gold-proof-candidate-") as temp_dir:
            artifact_root = proof_importer.extracted_or_directory(candidate_zip, Path(temp_dir))
            visual_source = proof_importer.find_unique(artifact_root, proof_importer.VISUAL_SOURCE_NAME)
            visual_payload = proof_importer.load_json(visual_source)
            screenshots = visual_payload.get("screenshots") if isinstance(visual_payload.get("screenshots"), list) else []
            artifact_sha256 = normalized_sha256_token(
                visual_payload.get("artifactSha256")
                or visual_payload.get("artifactDigest")
                or ""
            )
            row.update(
                {
                    "visual_source_status": visual_payload.get("status"),
                    "visual_source_member_path": str(visual_source.relative_to(artifact_root)),
                    "host_class": visual_payload.get("hostClass"),
                    "artifact_sha256": artifact_sha256,
                    "matches_promoted_installer": bool(promoted_digest and artifact_sha256 == promoted_digest),
                    "screenshot_count": len(screenshots),
                    "source_updated_at_utc": visual_payload.get("sourceUpdatedAtUtc")
                    or visual_payload.get("generatedAt")
                    or visual_payload.get("generated_at"),
                }
            )

            startup_source = proof_importer.find_optional_unique(artifact_root, proof_importer.STARTUP_RECEIPT_NAME)
            row["has_bundled_startup_receipt"] = startup_source is not None
            if startup_source is not None:
                startup_payload = proof_importer.load_json(startup_source)
                startup_digest = normalized_sha256_token(
                    startup_payload.get("artifactDigest")
                    or startup_payload.get("artifactSha256")
                    or ""
                )
                row.update(
                    {
                        "bundled_startup_receipt_member_path": str(startup_source.relative_to(artifact_root)),
                        "bundled_startup_receipt_status": startup_payload.get("status"),
                        "bundled_startup_receipt_digest": startup_digest,
                        "bundled_startup_receipt_pass": startup_receipt_effective_pass(startup_payload),
                    }
                )

            proof_importer.validate_visual_payload_before_import(visual_source, visual_payload)
            proof_importer.validate_visual_payload_matches_promoted_digest(visual_source, visual_payload, promoted_digest)
            if startup_source is not None:
                proof_importer.validate_bundled_startup_receipt(startup_source, promoted_digest)
            else:
                raise SystemExit(f"proof artifact is missing {proof_importer.STARTUP_RECEIPT_NAME}")

            row["auto_import_ready"] = bool(row.get("matches_promoted_installer"))
            row["zip_inspection_status"] = "ready"
    except BaseException as exc:
        row["auto_import_ready"] = False
        row["zip_inspection_status"] = "invalid"
        row["zip_inspection_error"] = import_failure_details(exc)
    return row


def stage_visual_proof_receipt_row(path: Path, promoted_digest: str) -> dict[str, Any]:
    row = file_row(path, "stage_visual_proof_receipt", 4)
    payload = load_json(path)
    screenshots = payload.get("screenshots") if isinstance(payload.get("screenshots"), list) else []
    artifact_sha256 = normalized_sha256_token(
        payload.get("artifactDigest")
        or payload.get("artifactSha256")
        or payload.get("installerDigest")
        or payload.get("installerSha256")
        or ""
    )
    installer_sha256 = normalized_sha256_token(
        payload.get("installerDigest")
        or payload.get("installerSha256")
        or payload.get("artifactDigest")
        or payload.get("artifactSha256")
        or ""
    )
    row.update(
        {
            "is_stage_visual_proof_receipt": True,
            "visual_proof_receipt_status": payload.get("status"),
            "contract_name": payload.get("contractName") or payload.get("contract_name"),
            "host_class": payload.get("hostClass"),
            "artifact_sha256": artifact_sha256,
            "installer_sha256": installer_sha256,
            "matches_promoted_installer": bool(promoted_digest and installer_sha256 == promoted_digest),
            "release_version": payload.get("releaseVersion") or payload.get("version"),
            "head_id": payload.get("headId") or payload.get("head") or payload.get("head_id"),
            "rid": payload.get("rid"),
            "generated_at_utc": payload.get("generatedAt")
            or payload.get("generated_at")
            or payload.get("recordedAtUtc")
            or payload.get("completedAtUtc"),
            "screenshot_count": len(screenshots),
            "screenshot_roles": [
                str(item.get("role") or "").strip()
                for item in screenshots
                if isinstance(item, dict) and str(item.get("role") or "").strip()
            ],
            "requires_gold_bundle_recapture": True,
        }
    )
    return row


def stage_startup_smoke_receipt_row(path: Path, promoted_digest: str) -> dict[str, Any]:
    row = file_row(path, "stage_startup_smoke_receipt", 4)
    payload = load_json(path)
    artifact_digest = normalized_sha256_token(
        payload.get("artifactDigest")
        or payload.get("artifactSha256")
        or ""
    )
    effective_pass = startup_receipt_effective_pass(payload)
    row.update(
        {
            "is_stage_startup_smoke_receipt": True,
            "startup_smoke_receipt_status": payload.get("status"),
            "contract_name": payload.get("contractName") or payload.get("contract_name"),
            "host_class": payload.get("hostClass"),
            "artifact_sha256": artifact_digest,
            "artifact_digest": artifact_digest,
            "matches_promoted_installer": bool(promoted_digest and artifact_digest == promoted_digest),
            "release_version": payload.get("releaseVersion") or payload.get("version"),
            "head_id": payload.get("headId") or payload.get("head") or payload.get("head_id"),
            "rid": payload.get("rid"),
            "platform": payload.get("platform"),
            "ready_checkpoint": payload.get("readyCheckpoint"),
            "generated_at_utc": payload.get("generatedAt")
            or payload.get("generated_at")
            or payload.get("recordedAtUtc")
            or payload.get("completedAtUtc"),
            "startup_already_proven": bool(promoted_digest and artifact_digest == promoted_digest and effective_pass),
        }
    )
    return row


def stale_directory_digest_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        digest = str(row.get("artifact_sha256") or "").strip().lower() or "missing"
        summary = grouped.setdefault(
            digest,
            {
                "artifact_sha256": digest,
                "count": 0,
                "stage_like_count": 0,
                "sample_path": str(row.get("path") or ""),
                "latest_source_updated_at_utc": str(row.get("source_updated_at_utc") or ""),
            },
        )
        summary["count"] += 1
        stage_like = bool(
            row.get("has_stage_visual_proof_receipt")
            or row.get("has_stage_visual_proof_handoff")
            or row.get("has_stage_release_build_handoff")
        )
        if stage_like:
            summary["stage_like_count"] += 1
        source_updated_at = str(row.get("source_updated_at_utc") or "")
        if source_updated_at and source_updated_at > str(summary.get("latest_source_updated_at_utc") or ""):
            summary["latest_source_updated_at_utc"] = source_updated_at
            summary["sample_path"] = str(row.get("path") or "")
    return sorted(
        grouped.values(),
        key=lambda item: (-int(item.get("count") or 0), -int(item.get("stage_like_count") or 0), str(item.get("artifact_sha256") or "")),
    )


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


def discover_candidates(intake: dict[str, Any], roots: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[Path] = set()
    artifact_intake = intake.get("artifact_intake") if isinstance(intake.get("artifact_intake"), dict) else {}
    intake_request = Path(str(intake.get("request_receipt_path") or DEFAULT_INTAKE_REQUEST))
    promoted_digest = promoted_digest_from_intake(intake)
    recursive_roots = recursive_scan_roots_from_intake(intake)
    artifact_intake_roots = artifact_intake.get("auto_import_roots") if isinstance(artifact_intake.get("auto_import_roots"), list) else []
    if not recursive_roots and not artifact_intake_roots and not intake.get("drop_roots_checked"):
        recursive_roots = unique_paths(list(roots))
    preferred = str(artifact_intake.get("preferred_drop_path") or intake.get("preferred_drop_path") or "").strip()
    if preferred:
        preferred_path = expand_portable_path(preferred)
        if preferred_path.exists():
            resolved = preferred_path.resolve()
            seen.add(resolved)
            if preferred_path.is_file() and preferred_path.suffix.lower() == ".zip":
                rows.append(zip_candidate_row(preferred_path, "preferred_drop_path", promoted_digest, 0, intake_request, intake))
            else:
                rows.append(annotate_candidate_row(file_row(preferred_path, "preferred_drop_path", 0), required_zip_filename(intake)))

    exact_names = expected_exact_names(intake)
    exact_name_set = set(exact_names)
    glob_patterns = expected_glob_patterns(intake)
    required_zip_name = required_zip_filename(intake)

    for root in roots:
        if not root.exists():
            continue
        search_root = root if root.is_dir() else root.parent
        if search_root is None or not search_root.exists():
            continue

        for name in exact_name_set:
            candidate = search_root / name
            if not candidate.is_file():
                continue
            resolved = candidate.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            rows.append(file_row(candidate, f"exact:{name}", 1))

        candidate_files = (
            walk_candidate_files(search_root)
            if should_recurse_root(search_root, recursive_roots)
            else top_level_files(search_root)
        )
        for candidate in candidate_files:
            if not candidate.is_file():
                continue
            try:
                resolved = candidate.resolve()
            except OSError:
                resolved = candidate
            if resolved in seen:
                continue

            if candidate.name == STAGE_VISUAL_PROOF_RECEIPT_NAME:
                candidate_root = None
                try:
                    parts = candidate.resolve().parts
                except OSError:
                    parts = candidate.parts
                if "Chummer.Portal" in parts:
                    index = parts.index("Chummer.Portal")
                    if index > 0:
                        candidate_root = Path(*parts[:index])
                if candidate_root is not None and candidate_root.exists() and directory_candidate_complete(candidate_root, intake):
                    continue
                seen.add(resolved)
                rows.append(stage_visual_proof_receipt_row(candidate, promoted_digest))
                continue

            if candidate.name == proof_importer.STARTUP_RECEIPT_NAME:
                candidate_root = None
                try:
                    parts = candidate.resolve().parts
                except OSError:
                    parts = candidate.parts
                if "Chummer.Portal" in parts:
                    index = parts.index("Chummer.Portal")
                    if index > 0:
                        candidate_root = Path(*parts[:index])
                if candidate_root is not None and candidate_root.exists() and directory_candidate_complete(candidate_root, intake):
                    continue
                seen.add(resolved)
                rows.append(stage_startup_smoke_receipt_row(candidate, promoted_digest))
                continue

            if candidate.name == proof_importer.VISUAL_SOURCE_NAME:
                candidate_root = artifact_root_from_visual_source(candidate)
                if not candidate_root.exists():
                    continue
                if not directory_candidate_complete(candidate_root, intake):
                    continue
                try:
                    candidate_root_resolved = candidate_root.resolve()
                except OSError:
                    candidate_root_resolved = candidate_root
                if candidate_root_resolved in seen:
                    continue
                seen.add(candidate_root_resolved)
                rows.append(
                    directory_candidate_row(
                        candidate_root,
                        promoted_digest,
                        3,
                        intake_request,
                        intake,
                        visual_source=candidate,
                    )
                )
                continue

            if candidate.name in exact_name_set:
                seen.add(resolved)
                if candidate.suffix.lower() == ".zip":
                    rows.append(zip_candidate_row(candidate, f"exact:{candidate.name}", promoted_digest, 1, intake_request, intake))
                else:
                    rows.append(annotate_candidate_row(file_row(candidate, f"exact:{candidate.name}", 1), required_zip_name))
                continue

            if not any(fnmatch.fnmatch(candidate.name, pattern) for pattern in glob_patterns):
                continue
            seen.add(resolved)
            if candidate.suffix.lower() == ".zip":
                rows.append(zip_candidate_row(candidate, f"glob:{candidate.name}", promoted_digest, 2, intake_request, intake))
            else:
                rows.append(annotate_candidate_row(file_row(candidate, f"glob:{candidate.name}", 2), required_zip_name))

    rows.sort(
        key=lambda row: (
            int(row["priority"]),
            -float(row.get("mtime_epoch") or 0.0),
            str(row["path"]),
        )
    )
    return rows


def selected_candidate(candidates: list[dict[str, Any]]) -> Path | None:
    for row in candidates:
        if bool(row.get("is_stage_visual_proof_receipt")):
            continue
        if bool(row.get("is_stage_startup_smoke_receipt")):
            continue
        candidate = Path(str(row["path"]))
        if (
            candidate.is_file()
            and candidate.name.lower().endswith(".zip")
            and bool(row.get("auto_import_ready"))
        ):
            return candidate
    return None


def actionable_waiting_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in candidates
        if not bool(row.get("is_stage_visual_proof_receipt"))
        and not bool(row.get("is_stage_startup_smoke_receipt"))
        and (
            bool(row.get("auto_import_ready"))
            or (
                not bool(row.get("is_dir"))
                and not str(Path(str(row.get("path") or "")).name).lower().endswith(".zip")
            )
        )
    ]


def import_proof_artifact(artifact: Path, downloads_root: Path, intake_request: Path | None = None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="windows-installer-gold-proof-auto-import-") as temp_dir:
        artifact_root = proof_importer.extracted_or_directory(artifact, Path(temp_dir))
        return proof_importer.import_artifact(artifact_root, downloads_root, intake_request=intake_request)


def build_code_owned_post_import_plan(
    downloads_root: Path,
    intake_request: Path,
    *,
    handoff_timestamp: str | None = None,
    authorize_external_mutations: bool = False,
) -> dict[str, Any]:
    return proof_importer.build_code_owned_post_import_plan(
        downloads_root,
        intake_request,
        handoff_timestamp=handoff_timestamp,
        auto_importer_program_binding=AUTO_IMPORTER_PROGRAM_BINDING_AT_LOAD,
        authorize_external_mutations=authorize_external_mutations,
    )


def execute_code_owned_post_import_plan(
    plan: dict[str, Any],
    *,
    side_effects_paused: bool | None = None,
) -> list[dict[str, Any]]:
    paused = (
        auto_import_side_effects_paused()
        if side_effects_paused is None
        else side_effects_paused
    )
    if paused:
        return []
    return proof_importer.execute_code_owned_post_import_plan(
        plan,
        external_mutation_pause_check=auto_import_side_effects_paused,
    )


def manual_import_command(path_value: Path, intake_request: Path) -> str:
    return (
        "python3 scripts/import_windows_installer_gold_proof_artifact.py "
        f"{shlex.quote(portable_path_text(path_value))} "
        f"--intake-request {shlex.quote(portable_path_text(intake_request))} "
        "--verify"
    )


def wait_for_candidate(
    intake: dict[str, Any],
    roots: list[Path],
    wait_seconds: float,
    poll_seconds: float,
    on_waiting: Callable[[list[dict[str, Any]]], None] | None = None,
    refresh_binding: Callable[[], None] | None = None,
) -> tuple[Path | None, list[dict[str, Any]]]:
    deadline = time.monotonic() + max(wait_seconds, 0.0)
    latest: list[dict[str, Any]] = []
    poll_index = 0
    while True:
        if poll_index > 0 and refresh_binding is not None:
            refresh_binding()
        latest = discover_candidates(intake, roots)
        candidate = selected_candidate(latest)
        if candidate is not None:
            return candidate, latest
        if on_waiting is not None:
            on_waiting(latest)
        if wait_seconds <= 0:
            return None, latest
        if time.monotonic() >= deadline:
            return None, latest
        poll_index += 1
        time.sleep(max(poll_seconds, 0.1))


def build_waiting_payload(
    *,
    artifact: Path | None,
    candidates: list[dict[str, Any]],
    intake: dict[str, Any],
    intake_request: Path,
    downloads_root: Path,
    roots: list[Path],
) -> dict[str, Any]:
    artifact_intake = intake.get("artifact_intake") if isinstance(intake.get("artifact_intake"), dict) else {}
    operator_request = intake.get("operator_request") if isinstance(intake.get("operator_request"), dict) else {}
    operator_telegram_draft = (
        intake.get("operator_telegram_draft")
        if isinstance(intake.get("operator_telegram_draft"), dict)
        else {}
    )
    intake_last_discovery = intake.get("last_discovery") if isinstance(intake.get("last_discovery"), dict) else {}
    intake_visual_sources = (
        intake_last_discovery.get("visual_sources")
        if isinstance(intake_last_discovery.get("visual_sources"), dict)
        else {}
    )
    release_channel_receipt_path = str(intake.get("release_channel_receipt_path") or "").strip()
    release_version = str(
        intake.get("release_version")
        or intake.get("releaseVersion")
        or intake.get("version")
        or ""
    ).strip()
    release_channel = str(intake.get("release_channel") or intake.get("channel") or "").strip()
    release_supportability_state = str(intake.get("release_supportability_state") or "").strip()
    release_rollout_state = str(intake.get("release_rollout_state") or "").strip()
    promoted_installer_sha256 = str(intake.get("promoted_installer_sha256") or "").strip()
    visual_audit_verifier_binding = (
        dict(intake.get("visual_audit_verifier_binding"))
        if isinstance(intake.get("visual_audit_verifier_binding"), dict)
        else {}
    )
    actionable_candidates = actionable_waiting_candidates(candidates)
    stage_visual_proof_receipts = [
        row
        for row in candidates
        if bool(row.get("is_stage_visual_proof_receipt"))
    ]
    directory_candidates = [row for row in candidates if bool(row.get("is_dir"))]
    zip_candidates = [
        row
        for row in candidates
        if not bool(row.get("is_dir")) and str(Path(str(row.get("path") or "")).name).lower().endswith(".zip")
    ]
    matching_promoted_directory_candidates = [
        row
        for row in directory_candidates
        if bool(row.get("matches_promoted_installer"))
    ]
    stale_directory_candidates = [
        row
        for row in directory_candidates
        if not bool(row.get("matches_promoted_installer"))
    ]
    stale_directory_candidates_sample = stale_directory_candidates[:STALE_DIRECTORY_SAMPLE_LIMIT]
    stale_digest_summary = stale_directory_digest_summary(stale_directory_candidates)
    matching_promoted_stage_visual_proof_receipts = [
        row
        for row in stage_visual_proof_receipts
        if bool(row.get("matches_promoted_installer"))
    ]
    stale_stage_visual_proof_receipts = [
        row
        for row in stage_visual_proof_receipts
        if not bool(row.get("matches_promoted_installer"))
    ]
    stale_stage_visual_proof_receipts_sample = stale_stage_visual_proof_receipts[:STALE_DIRECTORY_SAMPLE_LIMIT]
    stage_startup_smoke_receipts = [
        row
        for row in candidates
        if bool(row.get("is_stage_startup_smoke_receipt"))
    ]
    matching_promoted_stage_startup_smoke_receipts = [
        row
        for row in stage_startup_smoke_receipts
        if bool(row.get("matches_promoted_installer"))
    ]
    matching_promoted_stage_startup_smoke_proven_receipts = [
        row
        for row in matching_promoted_stage_startup_smoke_receipts
        if bool(row.get("startup_already_proven"))
    ]
    stale_stage_startup_smoke_receipts = [
        row
        for row in stage_startup_smoke_receipts
        if not bool(row.get("matches_promoted_installer"))
    ]
    stale_stage_startup_smoke_receipts_sample = stale_stage_startup_smoke_receipts[:STALE_DIRECTORY_SAMPLE_LIMIT]
    required_zip_filename = str(
        intake.get("required_zip_filename")
        or intake.get("preferred_zip_name")
        or Path(str(artifact_intake.get("preferred_drop_path") or "")).name
        or ""
    ).strip()
    matching_promoted_zip_candidates = [
        row
        for row in zip_candidates
        if bool(row.get("auto_import_ready"))
    ]
    auto_import_roots_checked = [
        str(item).strip()
        for item in artifact_intake.get("auto_import_roots") or []
        if str(item).strip()
    ]
    candidates_with_import_commands: list[dict[str, Any]] = []
    for row in actionable_candidates:
        normalized_row = dict(row)
        path_text = str(normalized_row.get("path") or "").strip()
        if path_text:
            normalized_row["manual_import_command"] = manual_import_command(Path(path_text), intake_request)
        candidates_with_import_commands.append(normalized_row)
    matching_directory_rows: list[dict[str, Any]] = []
    for row in matching_promoted_directory_candidates:
        normalized_row = dict(row)
        path_text = str(normalized_row.get("path") or "").strip()
        if path_text:
            normalized_row["manual_import_command"] = manual_import_command(Path(path_text), intake_request)
        matching_directory_rows.append(normalized_row)
    payload = {
        "contract_name": "chummer.windows_installer_visual_audit_auto_import.v1",
        "program_bindings": program_bindings_for_receipt(),
        "generated_at_utc": now_iso(),
        "status": "waiting_for_artifact",
        "artifact": str(artifact) if artifact else None,
        "release_channel_receipt_path": release_channel_receipt_path,
        "release_version": release_version,
        "release_channel": release_channel,
        "release_supportability_state": release_supportability_state,
        "release_rollout_state": release_rollout_state,
        "promoted_installer_sha256": promoted_installer_sha256,
        "promoted_installer_binding_ready": bool(
            intake.get("promoted_installer_binding_ready")
        ),
        "promoted_installer_binding_failures": list(
            intake.get("promoted_installer_binding_failures")
            if isinstance(intake.get("promoted_installer_binding_failures"), list)
            else []
        ),
        "visual_audit_verifier_binding": visual_audit_verifier_binding,
        "preferred_drop_folder": str(
            artifact_intake.get("dedicated_drop_root")
            or intake.get("preferred_drop_folder")
            or ""
        ),
        "preferred_drop_path": str(
            artifact_intake.get("preferred_drop_path")
            or intake.get("preferred_drop_path")
            or ""
        ),
        "preferred_zip_name": str(
            intake.get("preferred_zip_name")
            or Path(str(artifact_intake.get("preferred_drop_path") or "")).name
            or ""
        ),
        "required_zip_filename": required_zip_filename,
        "startup_receipt_bundle_required": startup_receipt_bundle_required(intake),
        "import_command": str(artifact_intake.get("import_command") or ""),
        "discover_command": str(artifact_intake.get("discover_command") or ""),
        "auto_import_command": str(
            artifact_intake.get("auto_import_command")
            or fallback_auto_import_command(intake_request)
        ),
        "auto_import_watch_command": str(
            artifact_intake.get("auto_import_watch_command")
            or fallback_auto_import_command(
                intake_request,
                wait_seconds=900,
                poll_seconds=10,
                refresh_intake_request=True,
            )
        ),
        "post_import_verify_command": str(artifact_intake.get("post_import_verify_command") or ""),
        "operator_summary": str(operator_request.get("summary") or ""),
        "operator_telegram_draft": operator_telegram_draft,
        "operator_telegram_send_command": str(operator_telegram_draft.get("send_command") or ""),
        "downloads_root": str(downloads_root),
        "intake_request": str(intake_request),
        "roots": [portable_path_text(root) for root in roots],
        "all_discovery_roots_checked": [portable_path_text(root) for root in roots],
        "auto_import_roots_checked": auto_import_roots_checked,
        "expected_artifact_patterns": [
            str(item).strip()
            for item in intake.get("expected_artifact_patterns") or []
            if str(item).strip()
        ],
        "drop_roots_checked": [
            str(item).strip()
            for item in intake.get("drop_roots_checked") or []
            if str(item).strip()
        ],
        "drop_roots_checked_note": (
            "drop_roots_checked mirrors the intake request's dedicated/runtime roots; "
            "all_discovery_roots_checked is the watcher/importer search scope."
        ),
        "expected_exact_names": expected_exact_names(intake),
        "expected_glob_patterns": expected_glob_patterns(intake),
        "intake_last_discovery": intake_last_discovery,
        "intake_visual_source_count": int(intake_visual_sources.get("count") or 0),
        "intake_matching_promoted_visual_source_count": int(intake_visual_sources.get("matching_promoted_count") or 0),
        "candidates": candidates_with_import_commands,
        "actionable_candidate_count": len(candidates_with_import_commands),
        "stage_visual_proof_receipt_count": len(stage_visual_proof_receipts),
        "matching_promoted_stage_visual_proof_receipt_count": len(matching_promoted_stage_visual_proof_receipts),
        "matching_promoted_stage_visual_proof_receipts": matching_promoted_stage_visual_proof_receipts,
        "stale_stage_visual_proof_receipt_count": len(stale_stage_visual_proof_receipts),
        "stale_stage_visual_proof_receipts": stale_stage_visual_proof_receipts_sample,
        "suppressed_stale_stage_visual_proof_receipt_count": max(
            len(stale_stage_visual_proof_receipts) - len(stale_stage_visual_proof_receipts_sample),
            0,
        ),
        "stage_visual_proof_receipt_note": (
            "Matching stage/nightly Windows proof receipts were found, but they are not auto-importable gold-proof bundles; use them to locate the Windows capture output, then rerun capture_windows_installer_gold_proof.ps1 or package the visual-audit bundle."
            if matching_promoted_stage_visual_proof_receipts and not stale_stage_visual_proof_receipts
            else (
                "Matching stage/nightly Windows proof receipts were found, but they are not auto-importable gold-proof bundles; use them to locate the Windows capture output, then rerun capture_windows_installer_gold_proof.ps1 or package the visual-audit bundle. Additional digest-mismatched stage/nightly receipts were summarized separately."
                if matching_promoted_stage_visual_proof_receipts
                else (
                    "Stage/nightly Windows proof receipts were found, but none match the promoted installer digest."
                    if stage_visual_proof_receipts
                    else ""
                )
            )
        ),
        "stage_startup_smoke_receipt_count": len(stage_startup_smoke_receipts),
        "matching_promoted_stage_startup_smoke_receipt_count": len(matching_promoted_stage_startup_smoke_receipts),
        "matching_promoted_stage_startup_smoke_proven_count": len(matching_promoted_stage_startup_smoke_proven_receipts),
        "matching_promoted_stage_startup_smoke_receipts": matching_promoted_stage_startup_smoke_receipts,
        "stale_stage_startup_smoke_receipt_count": len(stale_stage_startup_smoke_receipts),
        "stale_stage_startup_smoke_receipts": stale_stage_startup_smoke_receipts_sample,
        "suppressed_stale_stage_startup_smoke_receipt_count": max(
            len(stale_stage_startup_smoke_receipts) - len(stale_stage_startup_smoke_receipts_sample),
            0,
        ),
        "stage_startup_smoke_receipt_note": (
            "Matching stage/nightly Windows startup-smoke receipts were found for the promoted installer digest. Startup is already proven for those staged bytes; only the visual-audit bundle still needs packaging or recapture."
            if matching_promoted_stage_startup_smoke_proven_receipts and not stale_stage_startup_smoke_receipts
            else (
                "Matching stage/nightly Windows startup-smoke receipts were found for the promoted installer digest. Startup is already proven for those staged bytes; only the visual-audit bundle still needs packaging or recapture. Additional digest-mismatched startup-smoke receipts were summarized separately."
                if matching_promoted_stage_startup_smoke_proven_receipts
                else (
                    "Matching stage/nightly Windows startup-smoke receipts were found for the promoted installer digest, but they are not semantically passing; do not treat them as startup proof."
                    if matching_promoted_stage_startup_smoke_receipts and not stale_stage_startup_smoke_receipts
                    else (
                        "Matching stage/nightly Windows startup-smoke receipts were found for the promoted installer digest, but they are not semantically passing; do not treat them as startup proof. Additional digest-mismatched startup-smoke receipts were summarized separately."
                        if matching_promoted_stage_startup_smoke_receipts
                        else (
                            "Stage/nightly Windows startup-smoke receipts were found, but none match the promoted installer digest."
                            if stage_startup_smoke_receipts
                            else ""
                        )
                    )
                )
            )
        ),
        "directory_candidate_count": len(directory_candidates),
        "matching_promoted_directory_candidate_count": len(matching_promoted_directory_candidates),
        "matching_promoted_directory_candidates": matching_directory_rows,
        "stale_directory_candidate_count": len(stale_directory_candidates),
        "stale_directory_candidates": stale_directory_candidates_sample,
        "stale_directory_digest_summary": stale_digest_summary,
        "stage_like_stale_directory_candidate_count": sum(
            1 for row in stale_directory_candidates
            if bool(
                row.get("has_stage_visual_proof_receipt")
                or row.get("has_stage_visual_proof_handoff")
                or row.get("has_stage_release_build_handoff")
            )
        ),
        "suppressed_stale_directory_candidate_count": max(
            len(stale_directory_candidates) - len(stale_directory_candidates_sample),
            0,
        ),
        "zip_candidate_count": len(zip_candidates),
        "matching_promoted_zip_candidate_count": len(matching_promoted_zip_candidates),
        "matching_promoted_zip_candidates": matching_promoted_zip_candidates,
        "directory_candidates_require_explicit_artifact": bool(directory_candidates),
        "directory_candidate_note": (
            "Extracted proof directories are rejected without inspection; package a bounded ZIP containing the complete native Windows proof set."
            if directory_candidates
            else ""
        ),
    }
    redacted_payload = redact_waiting_receipt_value(payload)
    if not isinstance(redacted_payload, dict):
        raise SystemExit("waiting receipt redaction produced an invalid payload")
    return redacted_payload


def build_result_payload(
    *,
    artifact: Path,
    intake_request: Path,
    downloads_root: Path,
    roots: list[Path],
    candidates: list[dict[str, Any]],
    import_summary: dict[str, Any],
    command_results: list[dict[str, Any]],
    post_import_plan: dict[str, Any],
    intake_post_import_gate_metadata: dict[str, Any],
    post_import_side_effects_paused: bool,
) -> dict[str, Any]:
    failures = [row for row in command_results if int(row.get("returncode") or 0) != 0]
    plan_receipt = proof_importer.post_import_plan_receipt(
        post_import_plan,
        command_results,
        paused=post_import_side_effects_paused,
    )
    plan_status = str(plan_receipt.get("status") or "")
    if failures:
        status = "fail"
    elif plan_status == "pass":
        status = "pass"
    elif plan_status == "pending_authorized_external_mutation":
        status = "pending_authorized_external_mutation"
    else:
        status = "fail"
    payload = {
        "contract_name": "chummer.windows_installer_visual_audit_auto_import.v1",
        "program_bindings": program_bindings_for_receipt(),
        "generated_at_utc": now_iso(),
        "status": status,
        "artifact": str(artifact),
        "downloads_root": str(downloads_root),
        "intake_request": str(intake_request),
        "roots": [portable_path_text(root) for root in roots],
        "candidates": candidates,
        "import_summary": import_summary,
        "intake_post_import_gates": intake_post_import_gate_metadata,
        "post_import_plan": plan_receipt,
        "post_import_commands": command_results,
        "failed_command_count": len(failures),
    }
    redacted_payload = redact_waiting_receipt_value(payload)
    if not isinstance(redacted_payload, dict):
        raise SystemExit("result receipt redaction produced an invalid payload")
    return redacted_payload


def import_failure_details(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, SystemExit):
        message = str(exc)
        code = (
            exc.code
            if isinstance(exc.code, int) and not isinstance(exc.code, bool)
            else None
        )
        code_receipt = (
            redacted_value_receipt(exc.code)
            if exc.code is not None and code is None
            else None
        )
        return {
            "type": type(exc).__name__,
            "message_receipt": redacted_value_receipt(message),
            "code": code,
            "code_receipt": code_receipt,
        }
    return {
        "type": type(exc).__name__,
        "message_receipt": redacted_value_receipt(str(exc)),
        "code": None,
    }


def build_import_failure_payload(
    *,
    artifact: Path,
    intake_request: Path,
    downloads_root: Path,
    roots: list[Path],
    candidates: list[dict[str, Any]],
    error: BaseException,
) -> dict[str, Any]:
    payload = {
        "contract_name": "chummer.windows_installer_visual_audit_auto_import.v1",
        "program_bindings": program_bindings_for_receipt(),
        "generated_at_utc": now_iso(),
        "status": "fail",
        "artifact": str(artifact),
        "downloads_root": str(downloads_root),
        "intake_request": str(intake_request),
        "roots": [portable_path_text(root) for root in roots],
        "candidates": candidates,
        "import_failure": import_failure_details(error),
        "post_import_commands": [],
        "failed_command_count": 0,
        "summary": "Selected Windows installer gold-proof artifact failed import validation.",
    }
    redacted_payload = redact_waiting_receipt_value(payload)
    if not isinstance(redacted_payload, dict):
        raise SystemExit("failure receipt redaction produced an invalid payload")
    return redacted_payload


def build_paused_payload(
    *,
    artifact: Path,
    intake_request: Path,
    downloads_root: Path,
    roots: list[Path],
    candidates: list[dict[str, Any]],
    post_import_plan: dict[str, Any],
    intake: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "contract_name": "chummer.windows_installer_visual_audit_auto_import.v1",
        "program_bindings": program_bindings_for_receipt(),
        "generated_at_utc": now_iso(),
        "status": "blocked_auto_import_paused",
        "artifact": str(artifact),
        "downloads_root": str(downloads_root),
        "intake_request": str(intake_request),
        "roots": [portable_path_text(root) for root in roots],
        "candidates": candidates,
        "import_performed": False,
        "public_bytes_written": False,
        "intake_post_import_gates": (
            proof_importer.request_post_import_gate_metadata(intake)
        ),
        "post_import_plan": proof_importer.post_import_plan_receipt(
            post_import_plan,
            [],
            paused=True,
        ),
        "post_import_commands": [],
        "failed_command_count": 0,
        "summary": (
            "Windows installer gold-proof auto-import is paused; no artifact bytes "
            "were imported and no post-import step was executed."
        ),
    }
    redacted_payload = redact_waiting_receipt_value(payload)
    if not isinstance(redacted_payload, dict):
        raise SystemExit("paused receipt redaction produced an invalid payload")
    return redacted_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover, import, and refresh receipts for a Windows installer gold-proof bundle.")
    parser.add_argument("--artifact", type=Path, default=None, help="Explicit proof bundle zip.")
    parser.add_argument("--intake-request", type=Path, default=DEFAULT_INTAKE_REQUEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--downloads-root", type=Path, default=proof_importer.DEFAULT_DOWNLOADS_ROOT)
    parser.add_argument("--discovery-root", action="append", default=None)
    parser.add_argument("--wait-seconds", type=float, default=0.0, help="Optional wait window for a bundle to appear.")
    parser.add_argument("--poll-seconds", type=float, default=5.0, help="Polling interval while waiting for a bundle.")
    parser.add_argument("--refresh-intake-request", action="store_true", help="Regenerate the intake request before discovery.")
    parser.add_argument(
        "--authorize-external-mutations",
        action="store_true",
        help=(
            "Explicitly authorize the code-owned Teable sync and promotion-attempt phase. "
            "The intake request cannot grant this authority."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    intake = ensure_intake_request(
        args.intake_request,
        refresh=args.refresh_intake_request,
        downloads_root=args.downloads_root,
    )
    roots = [Path(item) for item in (args.discovery_root or [])]
    roots_are_explicit = bool(roots)
    if not roots:
        roots = discovery_roots_from_intake(intake)
    roots = unique_paths(roots)

    def refresh_watch_binding() -> None:
        refreshed = materialize_intake_request(args.intake_request, args.downloads_root)
        intake.clear()
        intake.update(refreshed)
        if not roots_are_explicit:
            roots[:] = unique_paths(discovery_roots_from_intake(intake))

    artifact = args.artifact
    candidates: list[dict[str, Any]]
    if artifact is None:
        def emit_waiting_payload(waiting_candidates: list[dict[str, Any]]) -> None:
            waiting_payload = build_waiting_payload(
                artifact=None,
                candidates=waiting_candidates,
                intake=intake,
                intake_request=args.intake_request,
                downloads_root=args.downloads_root,
                roots=roots,
            )
            write_json(args.output, waiting_payload)

        artifact, candidates = wait_for_candidate(
            intake,
            roots,
            args.wait_seconds,
            args.poll_seconds,
            on_waiting=emit_waiting_payload if args.wait_seconds > 0 else None,
            refresh_binding=(
                refresh_watch_binding
                if args.refresh_intake_request and args.wait_seconds > 0
                else None
            ),
        )
    else:
        candidates = discover_candidates(intake, roots)

    if artifact is None:
        payload = build_waiting_payload(
            artifact=artifact,
            candidates=candidates,
            intake=intake,
            intake_request=args.intake_request,
            downloads_root=args.downloads_root,
            roots=roots,
        )
        write_json(args.output, payload)
        print("windows_installer_visual_audit_auto_import:waiting")
        return 2

    if auto_import_side_effects_paused():
        paused_plan = build_code_owned_post_import_plan(
            args.downloads_root,
            args.intake_request,
            authorize_external_mutations=bool(
                getattr(args, "authorize_external_mutations", False)
            ),
        )
        payload = build_paused_payload(
            artifact=artifact,
            intake_request=args.intake_request,
            downloads_root=args.downloads_root,
            roots=roots,
            candidates=candidates,
            post_import_plan=paused_plan,
            intake=intake,
        )
        write_json(args.output, payload)
        print("windows_installer_visual_audit_auto_import:blocked_auto_import_paused")
        return 3

    try:
        import_summary = import_proof_artifact(artifact, args.downloads_root, intake_request=args.intake_request)
    except SystemExit as exc:
        payload = build_import_failure_payload(
            artifact=artifact,
            intake_request=args.intake_request,
            downloads_root=args.downloads_root,
            roots=roots,
            candidates=candidates,
            error=exc,
        )
        write_json(args.output, payload)
        print("windows_installer_visual_audit_auto_import:fail")
        return 1
    except Exception as exc:
        payload = build_import_failure_payload(
            artifact=artifact,
            intake_request=args.intake_request,
            downloads_root=args.downloads_root,
            roots=roots,
            candidates=candidates,
            error=exc,
        )
        write_json(args.output, payload)
        print("windows_installer_visual_audit_auto_import:fail")
        return 1
    if auto_import_side_effects_paused():
        paused_plan = build_code_owned_post_import_plan(
            args.downloads_root,
            args.intake_request,
            authorize_external_mutations=bool(
                getattr(args, "authorize_external_mutations", False)
            ),
        )
        payload = build_result_payload(
            artifact=artifact,
            intake_request=args.intake_request,
            downloads_root=args.downloads_root,
            roots=roots,
            candidates=candidates,
            import_summary=import_summary,
            command_results=[],
            post_import_plan=paused_plan,
            intake_post_import_gate_metadata=(
                proof_importer.request_post_import_gate_metadata(intake)
            ),
            post_import_side_effects_paused=True,
        )
        payload["status"] = "blocked_auto_import_paused_after_import"
        payload["import_performed"] = True
        payload["public_bytes_written"] = True
        payload["summary"] = (
            "The pause interlock appeared during artifact import. Imported local bytes "
            "remain present, but no post-import validation or external mutation ran."
        )
        write_json(args.output, payload)
        print("windows_installer_visual_audit_auto_import:blocked_auto_import_paused_after_import")
        return 3
    post_import_plan = build_code_owned_post_import_plan(
        args.downloads_root,
        args.intake_request,
        authorize_external_mutations=bool(
            getattr(args, "authorize_external_mutations", False)
        ),
    )
    command_results = execute_code_owned_post_import_plan(
        post_import_plan,
        side_effects_paused=False,
    )
    payload = build_result_payload(
        artifact=artifact,
        intake_request=args.intake_request,
        downloads_root=args.downloads_root,
        roots=roots,
        candidates=candidates,
        import_summary=import_summary,
        command_results=command_results,
        post_import_plan=post_import_plan,
        intake_post_import_gate_metadata=(
            proof_importer.request_post_import_gate_metadata(intake)
        ),
        post_import_side_effects_paused=False,
    )
    write_json(args.output, payload)
    print(f"windows_installer_visual_audit_auto_import:{payload['status']}")
    if payload["status"] == "pass":
        return 0
    if payload["status"] == "pending_authorized_external_mutation":
        return 4
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
