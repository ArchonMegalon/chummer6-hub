#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = ROOT / ".codex-studio" / "published"
DEFAULT_INTAKE_REQUEST = PUBLISHED_ROOT / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json"
DEFAULT_OUTPUT = PUBLISHED_ROOT / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT.generated.json"
INTAKE_MATERIALIZER = ROOT / "scripts" / "materialize_google_oauth_linking_operator_evidence_request.py"
DISCOVERY_MAX_DEPTH = 6
CONTRACT_NAME = "chummer.google_oauth_linking_operator_evidence_auto_import.v2"
WAITING_STATUS = "waiting_for_artifact"

try:
    import import_google_oauth_linking_operator_evidence_artifact as evidence_importer
except ModuleNotFoundError:
    import import_google_oauth_linking_operator_evidence_artifact as evidence_importer
from published_path_hygiene import expand_portable_path, portable_path_text
import google_oauth_linking_evidence_v2 as evidence_v2

DEFAULT_BASE_URL = evidence_importer.DEFAULT_BASE_URL


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


def fallback_auto_import_command(
    intake_request: Path,
    *,
    wait_seconds: float | None = None,
    poll_seconds: float | None = None,
    refresh_intake_request: bool = False,
) -> str:
    command = (
        "python3 scripts/auto_import_google_oauth_linking_operator_evidence.py "
        f"--intake-request {intake_request}"
    )
    if wait_seconds is not None:
        command += f" --wait-seconds {int(wait_seconds)}"
    if poll_seconds is not None:
        command += f" --poll-seconds {int(poll_seconds)}"
    if refresh_intake_request:
        command += " --refresh-intake-request"
    return command


def materialize_intake_request(path: Path, base_url: str) -> dict[str, Any]:
    completed = subprocess.run(
        [
            "python3",
            str(INTAKE_MATERIALIZER),
            "--output",
            str(path),
            "--base-url",
            base_url,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(
            "failed to materialize Google OAuth operator evidence intake request: "
            f"{completed.stderr.strip() or completed.stdout.strip() or completed.returncode}"
        )
    payload = load_json(path)
    if not payload:
        raise SystemExit(f"materialized intake request is unreadable: {path}")
    return payload


def ensure_intake_request(path: Path, refresh: bool, base_url: str) -> dict[str, Any]:
    if refresh or not path.is_file():
        return materialize_intake_request(path, base_url)
    payload = load_json(path)
    if payload:
        return payload
    return materialize_intake_request(path, base_url)


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
    preferred = str(artifact_intake.get("preferred_drop_path") or intake.get("preferred_drop_path") or "").strip()
    if preferred:
        roots.append(expand_portable_path(preferred).parent)
    return unique_paths(roots)


def recursive_scan_roots_from_intake(intake: dict[str, Any]) -> list[Path]:
    artifact_intake = intake.get("artifact_intake") if isinstance(intake.get("artifact_intake"), dict) else {}
    roots: list[Path] = []
    dedicated = str(artifact_intake.get("dedicated_drop_root") or "").strip()
    if dedicated:
        roots.append(Path(dedicated))
    return unique_paths(roots)


def expected_exact_names(intake: dict[str, Any]) -> list[str]:
    artifact_intake = intake.get("artifact_intake") if isinstance(intake.get("artifact_intake"), dict) else {}
    names: list[str] = []
    for raw in intake.get("expected_artifact_patterns") or []:
        text = str(raw or "").strip()
        if text and "*" not in text and "?" not in text:
            names.append(Path(text).name)
    preferred = str(artifact_intake.get("preferred_drop_path") or intake.get("preferred_drop_path") or "").strip()
    if preferred:
        names.append(Path(preferred).name)
    return list(dict.fromkeys(name for name in names if name))


def expected_glob_patterns(intake: dict[str, Any]) -> list[str]:
    patterns: list[str] = []
    for raw in intake.get("expected_artifact_patterns") or []:
        text = str(raw or "").strip()
        if text:
            patterns.append(text)
    return list(dict.fromkeys(patterns))


def file_row(path: Path, discovery_kind: str, priority: int) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "discovery_kind": discovery_kind,
        "priority": priority,
        "mtime_epoch": float(stat.st_mtime),
        "mtime_utc": datetime.fromtimestamp(stat.st_mtime, UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "size_bytes": stat.st_size,
        "is_dir": path.is_dir(),
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


def discover_candidates(intake: dict[str, Any], roots: list[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[Path] = set()
    artifact_intake = intake.get("artifact_intake") if isinstance(intake.get("artifact_intake"), dict) else {}
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

    exact_names = set(expected_exact_names(intake))
    glob_patterns = expected_glob_patterns(intake)

    for root in roots:
        if not root.exists():
            continue
        search_root = root if root.is_dir() else root.parent
        if search_root is None or not search_root.exists():
            continue
        candidate_files = (
            walk_candidate_files(search_root)
            if should_recurse_root(search_root, recursive_roots)
            else (top_level_files(search_root) if search_root.is_dir() else [search_root])
        )
        for candidate in candidate_files:
            try:
                resolved = candidate.resolve()
            except OSError:
                resolved = candidate
            if resolved in seen:
                continue
            name = candidate.name
            priority: int | None = None
            discovery_kind = ""
            if name in exact_names:
                priority = 1
                discovery_kind = "expected_exact_name"
            elif any(fnmatch.fnmatch(name, pattern) for pattern in glob_patterns):
                priority = 2
                discovery_kind = "expected_glob"
            elif name == "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json":
                priority = 3
                discovery_kind = "direct_receipt"
            if priority is None:
                continue
            seen.add(resolved)
            rows.append(file_row(candidate, discovery_kind, priority))

    rows.sort(
        key=lambda row: (
            sort_priority(row),
            -float(row.get("mtime_epoch") or 0.0),
            str(row.get("path") or ""),
        )
    )
    return rows


def select_candidate(candidates: list[dict[str, Any]]) -> Path | None:
    if not candidates:
        return None
    prioritized = sorted(
        candidates,
        key=lambda row: (
            sort_priority(row),
            -float(row.get("mtime_epoch") or 0.0),
            str(row.get("path") or ""),
        ),
    )
    return Path(str(prioritized[0].get("path") or ""))


def sort_priority(row: dict[str, Any]) -> int:
    priority = row.get("priority")
    if priority is None:
        return 99
    try:
        return int(priority)
    except (TypeError, ValueError):
        return 99


def run_command(argv: list[str], cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        argv,
        cwd=cwd,
        shell=False,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "argv": argv,
        "returncode": int(completed.returncode),
        "stdout_tail": completed.stdout.splitlines()[-40:],
        "stderr_tail": completed.stderr.splitlines()[-40:],
    }


def post_import_argv_plan(intake: dict[str, Any], intake_request: Path) -> list[list[str]]:
    evidence_path_text = str(
        intake.get("required_operator_evidence_path")
        or intake.get("required_receipt_path")
        or evidence_v2.DEFAULT_EVIDENCE_PATH
    )
    return evidence_v2.fixed_post_import_argv_plan(
        base_url=str(intake.get("base_url") or DEFAULT_BASE_URL),
        request_path=intake_request,
        evidence_path=Path(evidence_path_text),
    )


def release_tuple_from_intake(intake: dict[str, Any]) -> dict[str, str]:
    return {
        "base_url": str(intake.get("base_url") or "").strip(),
        "release_channel_receipt_path": str(intake.get("release_channel_receipt_path") or "").strip(),
        "release_version": str(intake.get("release_version") or "").strip(),
        "release_channel": str(intake.get("release_channel") or "").strip(),
        "release_supportability_state": str(intake.get("release_supportability_state") or "").strip(),
        "release_rollout_state": str(intake.get("release_rollout_state") or "").strip(),
        "release_published_at": str(intake.get("release_published_at") or "").strip(),
    }


def build_waiting_payload(
    *,
    intake: dict[str, Any],
    intake_request: Path,
    roots: list[Path],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    artifact_intake = intake.get("artifact_intake") if isinstance(intake.get("artifact_intake"), dict) else {}
    required_operator_evidence_path = str(
        intake.get("required_operator_evidence_path")
        or intake.get("required_receipt_path")
        or ""
    ).strip()
    return {
        "contract_name": CONTRACT_NAME,
        "generated_at_utc": now_iso(),
        "status": WAITING_STATUS,
        "preferred_drop_path": str(artifact_intake.get("preferred_drop_path") or intake.get("preferred_drop_path") or ""),
        "required_operator_evidence_path": required_operator_evidence_path,
        "required_receipt_path": required_operator_evidence_path,
        "intake_request": str(intake_request),
        "roots": [portable_path_text(root) for root in roots],
        "candidates": candidates,
        "discover_command": str(artifact_intake.get("discover_command") or ""),
        "import_command": str(artifact_intake.get("import_command") or ""),
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
        "post_import_argv_plan": post_import_argv_plan(intake, intake_request),
        **release_tuple_from_intake(intake),
    }


def build_not_required_payload(
    *,
    intake: dict[str, Any],
    intake_request: Path,
    roots: list[Path],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    artifact_intake = intake.get("artifact_intake") if isinstance(intake.get("artifact_intake"), dict) else {}
    required_operator_evidence_path = str(
        intake.get("required_operator_evidence_path")
        or intake.get("required_receipt_path")
        or ""
    ).strip()
    return {
        "contract_name": CONTRACT_NAME,
        "generated_at_utc": now_iso(),
        "status": "pass",
        "request_status": "not_required",
        "operator_action_still_required": False,
        "preferred_drop_path": str(artifact_intake.get("preferred_drop_path") or intake.get("preferred_drop_path") or ""),
        "required_operator_evidence_path": required_operator_evidence_path,
        "required_receipt_path": required_operator_evidence_path,
        "intake_request": str(intake_request),
        "roots": [portable_path_text(root) for root in roots],
        "candidates": candidates,
        "discover_command": str(artifact_intake.get("discover_command") or ""),
        "import_command": str(artifact_intake.get("import_command") or ""),
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
        "post_import_argv_plan": post_import_argv_plan(intake, intake_request),
        "summary": "Google OAuth operator evidence already satisfies the current request.",
        **release_tuple_from_intake(intake),
    }


def build_result_payload(
    *,
    artifact: Path,
    intake_request: Path,
    roots: list[Path],
    candidates: list[dict[str, Any]],
    import_summary: dict[str, Any],
    command_results: list[dict[str, Any]],
) -> dict[str, Any]:
    failures = [row for row in command_results if int(row.get("returncode") or 0) != 0]
    return {
        "contract_name": CONTRACT_NAME,
        "generated_at_utc": now_iso(),
        "status": "pass" if not failures else "fail",
        "artifact": str(artifact),
        "intake_request": str(intake_request),
        "roots": [portable_path_text(root) for root in roots],
        "candidates": candidates,
        "import_summary": import_summary,
        "post_import_argv_results": command_results,
        "failed_command_count": len(failures),
        **release_tuple_from_intake(load_json(intake_request)),
    }


def wait_for_candidate(intake: dict[str, Any], roots: list[Path], wait_seconds: float, poll_seconds: float) -> tuple[Path | None, list[dict[str, Any]]]:
    deadline = time.monotonic() + max(wait_seconds, 0.0)
    while True:
        candidates = discover_candidates(intake, roots)
        selected = select_candidate(candidates)
        if selected is not None:
            return selected, candidates
        if wait_seconds <= 0 or time.monotonic() >= deadline:
            return None, candidates
        time.sleep(max(poll_seconds, 1.0))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Discover, import, and refresh receipts for Google OAuth operator evidence.")
    parser.add_argument("--artifact", type=Path, default=None, help="Explicit operator evidence bundle directory, JSON receipt, or zip.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--intake-request", type=Path, default=DEFAULT_INTAKE_REQUEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--discovery-root", action="append", default=None)
    parser.add_argument("--wait-seconds", type=float, default=0.0)
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--refresh-intake-request", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    intake = ensure_intake_request(
        args.intake_request,
        refresh=args.refresh_intake_request,
        base_url=args.base_url,
    )
    request_status = str(intake.get("status") or intake.get("request_status") or "").strip()
    if request_status == "blocked_release_authority":
        payload = {
            "contract_name": CONTRACT_NAME,
            "generated_at_utc": now_iso(),
            "status": "blocked_release_authority",
            "intake_request": str(args.intake_request),
            "release_authority": intake.get("release") or {},
            "roots": [],
            "candidates": [],
            "summary": "Auto-import is disabled until portal, hub-registry, and captured live release manifests agree.",
        }
        write_json(args.output, payload)
        print("google_oauth_linking_operator_evidence_auto_import:blocked")
        return 2
    if request_status != "operator_action_required":
        payload = {
            "contract_name": CONTRACT_NAME,
            "generated_at_utc": now_iso(),
            "status": "fail",
            "intake_request": str(args.intake_request),
            "roots": [],
            "candidates": [],
            "failures": [f"unsupported or stale intake request status: {request_status or 'missing'}"],
        }
        write_json(args.output, payload)
        return 1
    _request_payload, _request_summary, _request_raw, request_failures = evidence_v2.verify_request_file(
        args.intake_request
    )
    if request_failures:
        payload = {
            "contract_name": CONTRACT_NAME,
            "generated_at_utc": now_iso(),
            "status": "fail",
            "intake_request": str(args.intake_request),
            "roots": [],
            "candidates": [],
            "failures": request_failures,
        }
        write_json(args.output, payload)
        return 1
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
            intake=intake,
            intake_request=args.intake_request,
            roots=roots,
            candidates=candidates,
        )
        write_json(args.output, payload)
        print("google_oauth_linking_operator_evidence_auto_import:waiting")
        return 2

    evidence_path_text = str(
        intake.get("required_operator_evidence_path")
        or intake.get("required_receipt_path")
        or ""
    ).strip()
    evidence_path = Path(evidence_path_text) if evidence_path_text else evidence_importer.DEFAULT_OPERATOR_EVIDENCE_PATH
    import_summary = evidence_importer.import_artifact(
        artifact,
        evidence_path=evidence_path,
        intake_request=args.intake_request,
    )
    command_results = [
        run_command(argv, ROOT)
        for argv in post_import_argv_plan(intake, args.intake_request)
    ]
    payload = build_result_payload(
        artifact=artifact,
        intake_request=args.intake_request,
        roots=roots,
        candidates=candidates,
        import_summary=import_summary,
        command_results=command_results,
    )
    write_json(args.output, payload)
    print(f"google_oauth_linking_operator_evidence_auto_import:{payload['status']}")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
