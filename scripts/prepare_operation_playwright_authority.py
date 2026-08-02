#!/usr/bin/env python3
"""Materialize the audited Playwright closure for one public-edge deployment."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
from typing import Any, Callable


CONTRACT_NAME = "chummer.operation-private-playwright-authority-preparation/v1"
AUTHORITY_MODULE_NAME = "chummer_public_download_authority_builder"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require_private_directory(path: Path, *, label: str) -> Path:
    normalized = path.expanduser().resolve(strict=True)
    metadata = normalized.lstat()
    if (
        normalized != path.expanduser().absolute()
        or not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeError(f"{label} is not an exact caller-owned private directory")
    return normalized


def stable_private_bytes(path: Path, *, label: str) -> bytes:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != os.getuid()
        or before.st_nlink != 1
        or stat.S_IMODE(before.st_mode) & 0o077
    ):
        raise RuntimeError(f"{label} is not a caller-owned private regular file")
    value = path.read_bytes()
    after = path.lstat()
    if (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
    ) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise RuntimeError(f"{label} changed while read")
    return value


def atomic_private_json(path: Path, payload: dict[str, Any]) -> None:
    parent = require_private_directory(path.parent, label="receipt parent")
    if path.parent != parent or path.exists() or path.is_symlink():
        raise RuntimeError("preparation receipt path is not a fresh exact path")
    encoded = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        parent_descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def load_authority_builder() -> Callable[[Any], dict[str, Any]]:
    module_path = Path(__file__).with_name("deploy_public_download_only_cutover.py")
    metadata = module_path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        raise RuntimeError("audited Playwright authority builder module is unsafe")
    specification = importlib.util.spec_from_file_location(
        AUTHORITY_MODULE_NAME,
        module_path,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("audited Playwright authority builder could not be loaded")
    module = importlib.util.module_from_spec(specification)
    sys.modules[AUTHORITY_MODULE_NAME] = module
    try:
        specification.loader.exec_module(module)
    finally:
        sys.modules.pop(AUTHORITY_MODULE_NAME, None)
    builder = getattr(module, "prepare_operation_host_build", None)
    if not callable(builder):
        raise RuntimeError("audited Playwright authority builder is unavailable")
    return builder


class AuthorityConfig:
    def __init__(self, host_build_root: Path) -> None:
        self.host_build_root = host_build_root
        self.playwright_python_root = host_build_root / "playwright-python"


def materialize(
    host_build_root: Path,
    output: Path,
    *,
    builder: Callable[[Any], dict[str, Any]],
) -> dict[str, Any]:
    host_build_root = require_private_directory(
        host_build_root,
        label="operation-private host-build root",
    )
    if output.expanduser().absolute().parent != host_build_root.parent:
        raise RuntimeError("preparation receipt must be adjacent to host-build root")
    result = builder(AuthorityConfig(host_build_root))
    authority_path = host_build_root / "playwright-authority.json"
    authority_bytes = stable_private_bytes(
        authority_path,
        label="operation-private Playwright authority",
    )
    authority_sha256 = sha256_bytes(authority_bytes)
    if (
        str(result.get("hostBuildRoot") or "") != str(host_build_root)
        or str(result.get("playwrightAuthority") or "") != str(authority_path)
        or str(result.get("playwrightAuthoritySha256") or "")
        != authority_sha256
    ):
        raise RuntimeError("Playwright authority builder returned a mismatched identity")
    for field in (
        "playwrightPythonTreeSha256",
        "playwrightBrowserTreeSha256",
    ):
        if SHA256_PATTERN.fullmatch(str(result.get(field) or "")) is None:
            raise RuntimeError(f"Playwright authority builder omitted {field}")
    receipt = {
        "contractName": CONTRACT_NAME,
        "status": "pass",
        "hostBuildRoot": str(host_build_root),
        "playwrightAuthority": str(authority_path),
        "playwrightAuthoritySha256": authority_sha256,
        "playwrightPythonTreeSha256": result["playwrightPythonTreeSha256"],
        "playwrightBrowserTreeSha256": result["playwrightBrowserTreeSha256"],
    }
    atomic_private_json(output.expanduser().absolute(), receipt)
    return receipt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare one operation-private Playwright authority closure."
    )
    parser.add_argument("--host-build-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    materialize(
        args.host_build_root,
        args.output,
        builder=load_authority_builder(),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
