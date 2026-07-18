#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


RUN_SERVICES_ROOT = Path("/docker/chummercomplete/chummer.run-services")
PRESENTATION_ROOT = Path("/docker/chummercomplete/chummer-presentation")
CORE_ROOT = Path("/docker/chummercomplete/chummer-core-engine")
PUBLISHED_ROOT = RUN_SERVICES_ROOT / ".codex-studio" / "published"
DEFAULT_OUTPUT = PUBLISHED_ROOT / "PORTABLE_RECEIPTS_AUDIT.generated.json"
MAX_JSON_BYTES = 16 * 1024 * 1024
MACHINE_SPECIFIC_PATH_PATTERNS = {
    # Require content below the user directory. Bare /home/<name> values are
    # also valid public application routes in Chummer and are not sufficient
    # evidence of a host path on their own.
    "linux_user_home": re.compile(
        r"/home/(?!\[[^\]/]+\][+*?]?/)[^/\r\n]+/(?=[^/?#\"'<>])"
    ),
    "macos_user_home": re.compile(
        r"/Users/(?!\[[^\]/]+\][+*?]?/)[^/\r\n]+/(?=[^/?#\"'<>])"
    ),
    "windows_user_home": re.compile(
        r"(?i)(?:[A-Z]:[\\/])(?:Users|Documents and Settings)[\\/]"
        r"[^\\/\r\n]+[\\/](?=[^\\/?#\"'<>])"
    ),
}
HOST_ABSOLUTE_PATH_FIELDS = {
    "processpath",
    "startup_smoke_bootstrap_temp_root",
    "startup_smoke_payload_download_target",
}
# Compatibility alias for callers that display the original Linux-only pattern.
HOME_PATH_PATTERN = MACHINE_SPECIFIC_PATH_PATTERNS["linux_user_home"]
DEFAULT_SCAN_ROOTS = (
    RUN_SERVICES_ROOT / ".codex-studio" / "published",
    PRESENTATION_ROOT / ".codex-studio" / "published",
    CORE_ROOT / ".codex-studio" / "published",
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _machine_specific_path_category(text: str) -> str | None:
    windows_match = MACHINE_SPECIFIC_PATH_PATTERNS["windows_user_home"].search(text)
    if windows_match is not None:
        return "windows_user_home"

    parsed = urlparse(text)
    if parsed.scheme and parsed.scheme.lower() != "file":
        return None

    boundary_positions = [position for marker in ("?", "#") if (position := text.find(marker)) >= 0]
    content_boundary = min(boundary_positions) if boundary_positions else len(text)
    for category in ("linux_user_home", "macos_user_home"):
        match = MACHINE_SPECIFIC_PATH_PATTERNS[category].search(text)
        if match is not None and match.start() < content_boundary:
            return category
    return None


def _is_absolute_host_path(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    parsed = urlparse(normalized)
    if parsed.scheme == "file":
        return True
    if parsed.scheme and len(parsed.scheme) != 1:
        return False
    return (
        normalized.startswith("/")
        or normalized.startswith("\\\\")
        or bool(re.match(r"^[A-Za-z]:[\\/]", normalized))
    )


def find_machine_specific_match(node: Any) -> str | None:
    if isinstance(node, dict):
        for key, value in node.items():
            match = find_machine_specific_match(value)
            if match is not None:
                return match
            if (
                str(key).strip().casefold() in HOST_ABSOLUTE_PATH_FIELDS
                and isinstance(value, str)
                and _is_absolute_host_path(value)
            ):
                return "host_absolute_path_field"
        return None
    if isinstance(node, list):
        for item in node:
            match = find_machine_specific_match(item)
            if match is not None:
                return match
        return None
    if isinstance(node, str):
        return _machine_specific_path_category(node)
    return None


def _safe_artifact_ref(root_index: int, root: Path, candidate: Path) -> str:
    try:
        relative = candidate.relative_to(root).as_posix()
    except ValueError:
        relative = candidate.name
    return f"scan-root-{root_index}/{relative}"


def _path_identity(path: Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _read_json_snapshot(path: Path) -> tuple[Any | None, str | None]:
    """Read one stable regular-file snapshot without following the final symlink."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except FileNotFoundError:
        return None, "missing"
    except OSError:
        return None, "unreadable_or_symlink"

    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            return None, "not_a_regular_file"
        if before.st_size > MAX_JSON_BYTES:
            return None, "too_large"

        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(65536, MAX_JSON_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_JSON_BYTES:
                return None, "too_large"

        after = os.fstat(descriptor)
        stable_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
            return None, "changed_during_read"

        try:
            return json.loads(b"".join(chunks)), None
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, "invalid_json"
    except OSError:
        return None, "unreadable"
    finally:
        os.close(descriptor)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise OSError("portable receipt output is a symlink")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        directory_descriptor = os.open(
            path.parent,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def scan_published_receipts(
    roots: list[Path] | tuple[Path, ...] = DEFAULT_SCAN_ROOTS,
    *,
    excluded_paths: list[Path] | tuple[Path, ...] = (),
) -> dict[str, Any]:
    scanned_artifact_count = 0
    machine_specific_hits: list[str] = []
    machine_specific_path_hits: list[str] = []
    artifact_integrity_hits: list[str] = []
    machine_specific_hit_details: list[dict[str, str]] = []
    unreadable_artifacts: list[str] = []
    excluded_identities = {_path_identity(path) for path in excluded_paths}
    for root_index, root in enumerate(roots, start=1):
        if not root.is_dir():
            continue
        for candidate in sorted(root.rglob("*.json")):
            if _path_identity(candidate) in excluded_identities:
                continue
            scanned_artifact_count += 1
            artifact_ref = _safe_artifact_ref(root_index, root, candidate)
            payload, read_error = _read_json_snapshot(candidate)
            if read_error is not None:
                unreadable_artifacts.append(artifact_ref)
                artifact_integrity_hits.append(artifact_ref)
                machine_specific_hits.append(artifact_ref)
                machine_specific_hit_details.append(
                    {
                        "path": artifact_ref,
                        "category": read_error,
                        "match": f"<redacted:{read_error}>",
                        "sample": "Receipt could not be read as one stable, regular UTF-8 JSON snapshot.",
                    }
                )
                continue

            match = find_machine_specific_match(payload)
            if match is None:
                continue

            machine_specific_hits.append(artifact_ref)
            machine_specific_path_hits.append(artifact_ref)
            machine_specific_hit_details.append(
                {
                    "path": artifact_ref,
                    "category": match,
                    "match": f"<redacted:{match}>",
                    "sample": "Machine-specific user-home path redacted.",
                }
            )

    return {
        "scanned_artifact_count": scanned_artifact_count,
        # Keep machine_specific_hits as the fail-closed aggregate for existing
        # consumers. The two typed lists below distinguish content portability
        # failures from unreadable or unstable published artifacts.
        "machine_specific_hits": machine_specific_hits,
        "machine_specific_path_hits": machine_specific_path_hits,
        "artifact_integrity_hits": artifact_integrity_hits,
        "machine_specific_hit_details": machine_specific_hit_details,
        "unreadable_artifacts": unreadable_artifacts,
        "scan_roots": [f"scan-root-{index}" for index, _ in enumerate(roots, start=1)],
        "machine_specific_pattern": HOME_PATH_PATTERN.pattern,
        "machine_specific_patterns": {
            category: pattern.pattern
            for category, pattern in MACHINE_SPECIFIC_PATH_PATTERNS.items()
        },
        "host_absolute_path_fields": sorted(HOST_ABSOLUTE_PATH_FIELDS),
        "recursive_scan": True,
        "stable_regular_file_snapshots": True,
    }


def materialize(output_path: Path = DEFAULT_OUTPUT, roots: list[Path] | tuple[Path, ...] = DEFAULT_SCAN_ROOTS) -> dict[str, Any]:
    scan = scan_published_receipts(roots, excluded_paths=[output_path])
    ok = scan["scanned_artifact_count"] > 0 and not scan["machine_specific_hits"]
    machine_specific_path_hits = scan["machine_specific_path_hits"]
    artifact_integrity_hits = scan["artifact_integrity_hits"]
    if ok:
        summary = "Portable receipts audit passed. Published proof artifacts do not embed machine-specific home paths."
    elif machine_specific_path_hits and artifact_integrity_hits:
        summary = (
            "Portable receipts audit failed. Published proof artifacts include machine-specific host paths "
            "and artifacts that could not be read as stable, regular UTF-8 JSON snapshots."
        )
    elif artifact_integrity_hits:
        summary = (
            "Portable receipts audit failed. One or more published proof artifacts could not be read as "
            "stable, regular UTF-8 JSON snapshots."
        )
    else:
        summary = "Portable receipts audit failed. Published proof artifacts still embed machine-specific host paths."
    payload = {
        "contract_name": "chummer.run.portable_receipts_audit",
        "status": "pass" if ok else "fail",
        "generated_at": now_iso(),
        "summary": summary,
        "scanned_artifact_count": scan["scanned_artifact_count"],
        "machine_specific_hits": scan["machine_specific_hits"],
        "machine_specific_path_hits": machine_specific_path_hits,
        "artifact_integrity_hits": artifact_integrity_hits,
        "failure_counts": {
            "machine_specific_paths": len(machine_specific_path_hits),
            "artifact_integrity": len(artifact_integrity_hits),
        },
        "machine_specific_hit_details": scan["machine_specific_hit_details"],
        "unreadable_artifacts": scan["unreadable_artifacts"],
        "scan_roots": scan["scan_roots"],
        "policy": {
            "use_repo_relative_paths": True,
            "allow_local_only_hostnames": True,
            "forbid_machine_specific_paths": True,
            "redact_failure_samples": True,
            "scan_nested_json_artifacts": True,
            "fail_on_artifact_integrity_errors": True,
            "machine_specific_pattern_description": (
                "literal Linux, macOS, and Windows user-home path segments are forbidden "
                "in published receipts"
            ),
        },
        "abs_ids": ["ABS-012"],
    }
    atomic_write_json(output_path, payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize the portable published-receipts audit.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--scan-root", action="append", default=None, help="Optional published-artifact root to scan. Defaults to the estate published roots.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    roots = [Path(item).expanduser() for item in (args.scan_root or [])]
    payload = materialize(args.output, roots or DEFAULT_SCAN_ROOTS)
    print(f"portable_receipts_audit:{payload['status']}")
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
