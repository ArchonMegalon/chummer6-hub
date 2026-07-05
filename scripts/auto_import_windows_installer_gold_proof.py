#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from published_path_hygiene import expand_portable_path, portable_path_text


ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = ROOT / ".codex-studio" / "published"
DEFAULT_INTAKE_REQUEST = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
DEFAULT_OUTPUT = PUBLISHED_ROOT / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
INTAKE_MATERIALIZER = ROOT / "scripts" / "materialize_windows_installer_visual_audit_intake_request.py"
DISCOVERY_MAX_DEPTH = 6
STALE_DIRECTORY_SAMPLE_LIMIT = 5

try:
    import import_windows_installer_gold_proof_artifact as proof_importer
except ModuleNotFoundError:
    import import_windows_installer_gold_proof_artifact as proof_importer


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def materialize_intake_request(path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "python3",
            str(INTAKE_MATERIALIZER),
            "--output",
            str(path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(
            "failed to materialize windows installer intake request: "
            f"{completed.stderr.strip() or completed.stdout.strip() or completed.returncode}"
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


def ensure_intake_request(path: Path, refresh: bool) -> dict[str, Any]:
    if refresh or not path.is_file():
        return materialize_intake_request(path)
    payload = load_json(path)
    if payload:
        return payload
    return materialize_intake_request(path)


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
        roots.append(expand_portable_path(dedicated))
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


def startup_receipt_candidate_path(candidate_root: Path) -> Path:
    return candidate_root / "Chummer.Portal" / "downloads" / "startup-smoke" / proof_importer.STARTUP_RECEIPT_NAME


def directory_candidate_complete(candidate_root: Path) -> bool:
    return startup_receipt_candidate_path(candidate_root).is_file()


def file_row(path: Path, discovery_kind: str, priority: int) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "name": path.name,
        "discovery_kind": discovery_kind,
        "priority": priority,
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "size_bytes": stat.st_size,
        "is_dir": path.is_dir(),
    }


def promoted_digest_from_intake(intake: dict[str, Any]) -> str:
    artifact = intake.get("promoted_installer") if isinstance(intake.get("promoted_installer"), dict) else {}
    return str(
        intake.get("promoted_installer_sha256")
        or artifact.get("sha256")
        or artifact.get("actual_sha256")
        or ""
    ).strip().lower().removeprefix("sha256:")


def directory_candidate_row(candidate_root: Path, promoted_digest: str, priority: int, visual_source: Path | None = None) -> dict[str, Any]:
    row = file_row(candidate_root, "visual_source_directory", priority)
    visual_source = visual_source or visual_source_candidate_path(candidate_root)
    if not visual_source.is_file():
        return row

    payload = load_json(visual_source)
    screenshots = payload.get("screenshots") if isinstance(payload.get("screenshots"), list) else []
    artifact_sha256 = str(
        payload.get("artifactSha256")
        or payload.get("artifactDigest")
        or ""
    ).strip().lower().removeprefix("sha256:")
    row.update(
        {
            "visual_source_path": str(visual_source),
            "visual_source_status": payload.get("status"),
            "host_class": payload.get("hostClass"),
            "artifact_sha256": artifact_sha256,
            "matches_promoted_installer": bool(promoted_digest and artifact_sha256 == promoted_digest),
            "screenshot_count": len(screenshots),
            "source_updated_at_utc": payload.get("sourceUpdatedAtUtc")
            or payload.get("generatedAt")
            or payload.get("generated_at"),
            "manual_import_command": (
                "python3 scripts/import_windows_installer_gold_proof_artifact.py "
                f"{candidate_root} --verify"
            ),
        }
    )
    return row


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
            rows.append(file_row(preferred_path, "preferred_drop_path", 0))

    exact_names = expected_exact_names(intake)
    exact_name_set = set(exact_names)
    glob_patterns = expected_glob_patterns(intake)

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

            if candidate.name == proof_importer.VISUAL_SOURCE_NAME:
                candidate_root = artifact_root_from_visual_source(candidate)
                if not candidate_root.exists() or not directory_candidate_complete(candidate_root):
                    continue
                try:
                    candidate_root_resolved = candidate_root.resolve()
                except OSError:
                    candidate_root_resolved = candidate_root
                if candidate_root_resolved in seen:
                    continue
                seen.add(candidate_root_resolved)
                rows.append(directory_candidate_row(candidate_root, promoted_digest, 3, visual_source=candidate))
                continue

            if candidate.name in exact_name_set:
                seen.add(resolved)
                rows.append(file_row(candidate, f"exact:{candidate.name}", 1))
                continue

            if not any(fnmatch.fnmatch(candidate.name, pattern) for pattern in glob_patterns):
                continue
            seen.add(resolved)
            rows.append(file_row(candidate, f"glob:{candidate.name}", 2))

    rows.sort(key=lambda row: (int(row["priority"]), -Path(str(row["path"])).stat().st_mtime, str(row["path"])))
    return rows


def selected_candidate(candidates: list[dict[str, Any]]) -> Path | None:
    for row in candidates:
        candidate = Path(str(row["path"]))
        if candidate.is_file():
            return candidate
        if candidate.is_dir() and bool(row.get("matches_promoted_installer")):
            return candidate
    return None


def actionable_waiting_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in candidates
        if not bool(row.get("is_dir")) or bool(row.get("matches_promoted_installer"))
    ]


def run_command(command: str, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        ["bash", "-lc", command],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": command,
        "returncode": int(completed.returncode),
        "stdout_tail": completed.stdout.splitlines()[-20:],
        "stderr_tail": completed.stderr.splitlines()[-20:],
    }


def import_proof_artifact(artifact: Path, downloads_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="windows-installer-gold-proof-auto-import-") as temp_dir:
        artifact_root = proof_importer.extracted_or_directory(artifact, Path(temp_dir))
        return proof_importer.import_artifact(artifact_root, downloads_root)


def post_import_commands(intake: dict[str, Any]) -> list[str]:
    commands = intake.get("post_import_gates")
    if not isinstance(commands, list):
        return []
    result: list[str] = []
    for item in commands:
        text = str(item or "").strip()
        if text:
            result.append(text)
    return result


def wait_for_candidate(
    intake: dict[str, Any],
    roots: list[Path],
    wait_seconds: float,
    poll_seconds: float,
) -> tuple[Path | None, list[dict[str, Any]]]:
    deadline = time.monotonic() + max(wait_seconds, 0.0)
    latest: list[dict[str, Any]] = []
    while True:
        latest = discover_candidates(intake, roots)
        candidate = selected_candidate(latest)
        if candidate is not None:
            return candidate, latest
        if wait_seconds <= 0 or time.monotonic() >= deadline:
            return None, latest
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
    actionable_candidates = actionable_waiting_candidates(candidates)
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
    required_zip_filename = str(
        intake.get("required_zip_filename")
        or intake.get("preferred_zip_name")
        or Path(str(artifact_intake.get("preferred_drop_path") or "")).name
        or ""
    ).strip()
    matching_promoted_zip_candidates = [
        row
        for row in zip_candidates
        if required_zip_filename
        and Path(str(row.get("path") or "")).name == required_zip_filename
    ]
    return {
        "contract_name": "chummer.windows_installer_visual_audit_auto_import.v1",
        "generated_at_utc": now_iso(),
        "status": "waiting_for_artifact",
        "artifact": str(artifact) if artifact else None,
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
        "intake_last_discovery": intake_last_discovery,
        "intake_visual_source_count": int(intake_visual_sources.get("count") or 0),
        "intake_matching_promoted_visual_source_count": int(intake_visual_sources.get("matching_promoted_count") or 0),
        "candidates": actionable_candidates,
        "actionable_candidate_count": len(actionable_candidates),
        "directory_candidate_count": len(directory_candidates),
        "matching_promoted_directory_candidate_count": len(matching_promoted_directory_candidates),
        "matching_promoted_directory_candidates": matching_promoted_directory_candidates,
        "stale_directory_candidate_count": len(stale_directory_candidates),
        "stale_directory_candidates": stale_directory_candidates_sample,
        "suppressed_stale_directory_candidate_count": max(
            len(stale_directory_candidates) - len(stale_directory_candidates_sample),
            0,
        ),
        "zip_candidate_count": len(zip_candidates),
        "matching_promoted_zip_candidate_count": len(matching_promoted_zip_candidates),
        "matching_promoted_zip_candidates": matching_promoted_zip_candidates,
        "directory_candidates_require_explicit_artifact": bool(directory_candidates) and not bool(matching_promoted_directory_candidates),
        "directory_candidate_note": (
            "Matching extracted proof directories were found; auto-import can consume them directly."
            if matching_promoted_directory_candidates and not stale_directory_candidates
            else (
                "Matching extracted proof directories were found; auto-import can consume them directly. "
                "Additional digest-mismatched directories were summarized separately."
                if matching_promoted_directory_candidates
                else (
                    "Complete extracted proof directories were found, but none match the promoted installer digest. "
                    "Digest-mismatched directories were summarized separately."
                    if directory_candidates
                    else ""
                )
            )
        ),
    }


def build_result_payload(
    *,
    artifact: Path,
    intake_request: Path,
    downloads_root: Path,
    roots: list[Path],
    candidates: list[dict[str, Any]],
    import_summary: dict[str, Any],
    command_results: list[dict[str, Any]],
) -> dict[str, Any]:
    failures = [row for row in command_results if int(row.get("returncode") or 0) != 0]
    return {
        "contract_name": "chummer.windows_installer_visual_audit_auto_import.v1",
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "artifact": str(artifact),
        "downloads_root": str(downloads_root),
        "intake_request": str(intake_request),
        "roots": [portable_path_text(root) for root in roots],
        "candidates": candidates,
        "import_summary": import_summary,
        "post_import_commands": command_results,
        "failed_command_count": len(failures),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover, import, and refresh receipts for a Windows installer gold-proof bundle.")
    parser.add_argument("--artifact", type=Path, default=None, help="Explicit proof bundle directory or zip.")
    parser.add_argument("--intake-request", type=Path, default=DEFAULT_INTAKE_REQUEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--downloads-root", type=Path, default=proof_importer.DEFAULT_DOWNLOADS_ROOT)
    parser.add_argument("--discovery-root", action="append", default=None)
    parser.add_argument("--wait-seconds", type=float, default=0.0, help="Optional wait window for a bundle to appear.")
    parser.add_argument("--poll-seconds", type=float, default=5.0, help="Polling interval while waiting for a bundle.")
    parser.add_argument("--refresh-intake-request", action="store_true", help="Regenerate the intake request before discovery.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    intake = ensure_intake_request(args.intake_request, refresh=args.refresh_intake_request)
    roots = [Path(item) for item in (args.discovery_root or [])]
    if not roots:
        roots = discovery_roots_from_intake(intake)
    roots = unique_paths(roots)

    artifact = args.artifact
    candidates: list[dict[str, Any]]
    if artifact is None:
        artifact, candidates = wait_for_candidate(intake, roots, args.wait_seconds, args.poll_seconds)
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

    import_summary = import_proof_artifact(artifact, args.downloads_root)
    command_results = [run_command(command, ROOT) for command in post_import_commands(intake)]
    payload = build_result_payload(
        artifact=artifact,
        intake_request=args.intake_request,
        downloads_root=args.downloads_root,
        roots=roots,
        candidates=candidates,
        import_summary=import_summary,
        command_results=command_results,
    )
    write_json(args.output, payload)
    print(f"windows_installer_visual_audit_auto_import:{payload['status']}")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
