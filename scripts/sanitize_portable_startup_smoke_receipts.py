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


MAX_RECEIPT_BYTES = 16 * 1024 * 1024
CONTRACT_NAME = "chummer.startup_smoke.portable_process_path_sanitization.v1"
DEFAULT_OUTPUT = Path(
    "/docker/chummercomplete/chummer.run-services/.state/"
    "PORTABLE_STARTUP_SMOKE_SANITIZATION.generated.json"
)
ABSOLUTE_WINDOWS_PATH = re.compile(r"^[A-Za-z]:[\\/]")


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def portable_process_file_name(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    normalized = raw.replace("\\", "/").rstrip("/")
    file_name = normalized.rsplit("/", 1)[-1].strip()
    return file_name or None


def is_absolute_host_path(value: object) -> bool:
    raw = str(value or "").strip()
    return raw.startswith("/") or raw.startswith("\\\\") or ABSOLUTE_WINDOWS_PATH.match(raw) is not None


def read_receipt(path: Path) -> tuple[dict[str, Any], int]:
    metadata = path.lstat()
    if not stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise ValueError("receipt must be a regular non-symlink file")
    if metadata.st_size < 2 or metadata.st_size > MAX_RECEIPT_BYTES:
        raise ValueError("receipt size is outside the accepted range")
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("receipt root must be a JSON object")
    return payload, stat.S_IMODE(metadata.st_mode)


def atomic_write_json(path: Path, payload: dict[str, Any], mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def sanitize_receipt(path: Path) -> bool:
    payload, mode = read_receipt(path)
    process_path = payload.get("processPath")
    if not is_absolute_host_path(process_path):
        return False
    process_file_name = portable_process_file_name(process_path)
    payload["processPath"] = process_file_name or "<redacted:process-path>"
    payload["processPathDisclosure"] = "file_name_only" if process_file_name else "unavailable"
    atomic_write_json(path, payload, mode)
    return True


def sanitize_roots(roots: list[Path]) -> dict[str, Any]:
    sanitized: list[str] = []
    inspected = 0
    failures: list[dict[str, str]] = []
    for root_index, root in enumerate(roots, start=1):
        resolved_root = root.resolve(strict=True)
        if not resolved_root.is_dir():
            raise ValueError(f"root-{root_index} is not a directory")
        for path in sorted(resolved_root.rglob("startup-smoke-*.receipt.json")):
            inspected += 1
            try:
                changed = sanitize_receipt(path)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
                failures.append(
                    {
                        "path": f"root-{root_index}/{path.relative_to(resolved_root).as_posix()}",
                        "reason": type(exc).__name__,
                    }
                )
                continue
            if changed:
                sanitized.append(f"root-{root_index}/{path.relative_to(resolved_root).as_posix()}")
    return {
        "contract_name": CONTRACT_NAME,
        "status": "pass" if not failures else "fail",
        "generated_at": now_iso(),
        "root_count": len(roots),
        "inspected_receipt_count": inspected,
        "sanitized_receipt_count": len(sanitized),
        "sanitized_receipts": sanitized,
        "failures": failures,
        "policy": {
            "field": "processPath",
            "disclosure": "file_name_only",
            "semantic_test_results_preserved": True,
            "artifact_digests_preserved": True,
            "raw_host_paths_recorded": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Remove absolute host process paths from published startup-smoke receipts."
    )
    parser.add_argument("--root", action="append", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = sanitize_roots(args.root)
    atomic_write_json(args.output, payload, 0o600)
    print(
        "portable_startup_smoke_sanitization:"
        f"{payload['status']}:sanitized={payload['sanitized_receipt_count']}"
    )
    return 0 if payload["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
