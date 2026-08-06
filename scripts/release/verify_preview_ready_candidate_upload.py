#!/usr/bin/env python3
"""Verify an exact upload bundle against a proof-bound preview-ready v6 authority."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib.util
from pathlib import Path
import stat
import sys
from typing import NoReturn


SCRIPT_DIRECTORY = Path(__file__).resolve().parent
PROJECTION_VERIFIER = SCRIPT_DIRECTORY / "verify_public_projection.py"
V6_CONTRACT = "chummer.release-upload.candidate-import-authority/v6"
SHA256_HEX_LENGTH = 64
READ_CHUNK_BYTES = 1024 * 1024


def fail(message: str) -> NoReturn:
    raise ValueError(message)


def load_projection_verifier():
    module_name = "chummer_preview_ready_upload_projection_verifier"
    spec = importlib.util.spec_from_file_location(module_name, PROJECTION_VERIFIER)
    if spec is None or spec.loader is None:
        fail("preview-ready projection verifier could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise ValueError("preview-ready projection verifier could not be loaded") from exc
    return module


def sha256_regular_file(path: Path, *, expected_size: int) -> str:
    before = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(before.st_mode) or before.st_size != expected_size:
        fail(f"candidate upload file is not the exact regular file: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(READ_CHUNK_BYTES), b""):
            digest.update(chunk)
    after = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(after.st_mode)
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    ):
        fail(f"candidate upload file changed while it was read: {path}")
    return digest.hexdigest()


def verify_bundle(
    *,
    authority_path: Path,
    expected_authority_sha256: str,
    bundle_root: Path,
) -> dict[str, object]:
    if (
        len(expected_authority_sha256) != SHA256_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in expected_authority_sha256)
    ):
        fail("candidate authority SHA-256 pin is invalid")
    verifier = load_projection_verifier()
    authority_raw = verifier._stable_read(
        authority_path,
        label="preview-ready candidate authority",
    )
    if not hmac.compare_digest(
        hashlib.sha256(authority_raw).hexdigest(),
        expected_authority_sha256,
    ):
        fail("preview-ready candidate authority differs from its independent SHA-256 pin")
    authority = verifier._validate_candidate_import_authority(authority_raw)
    if (
        authority.get("contractName") != V6_CONTRACT
        or authority.get("previewPublicationReadinessBridgeAuthority") is not True
    ):
        fail("stage-client proof substitution requires the exact preview-ready v6 authority")

    custody = authority.get("custody")
    if not isinstance(custody, dict):
        fail("preview-ready candidate custody is unavailable")
    inventory_raw = verifier._candidate_embedded_bytes(
        custody.get("inventory"),
        label="preview-ready upload inventory",
        expected_path="CANDIDATE_UPLOAD_INVENTORY.generated.json",
    )
    inventory = verifier._strict_json_object(
        inventory_raw,
        label="preview-ready upload inventory",
    )
    rows = verifier._candidate_inventory_rows(
        inventory.get("files"),
        label="preview-ready upload inventory",
    )

    root = bundle_root.resolve(strict=True)
    root_metadata = root.lstat()
    if bundle_root.is_symlink() or not stat.S_ISDIR(root_metadata.st_mode):
        fail("candidate upload bundle root must be a non-symlink directory")
    expected_paths = {str(row["path"]) for row in rows}
    observed_paths: set[str] = set()
    for candidate in root.rglob("*"):
        metadata = candidate.lstat()
        if candidate.is_symlink():
            fail(f"candidate upload bundle contains a symlink: {candidate}")
        if stat.S_ISDIR(metadata.st_mode):
            continue
        if not stat.S_ISREG(metadata.st_mode):
            fail(f"candidate upload bundle contains a special file: {candidate}")
        observed_paths.add(candidate.relative_to(root).as_posix())
    if observed_paths != expected_paths:
        fail("candidate upload bundle file set differs from the v6 authority inventory")

    for row in rows:
        relative_path = str(row["path"])
        candidate = root / relative_path
        actual_sha256 = sha256_regular_file(
            candidate,
            expected_size=int(row["sizeBytes"]),
        )
        if not hmac.compare_digest(actual_sha256, str(row["sha256"])):
            fail(f"candidate upload file digest differs from v6 authority: {relative_path}")
    return authority


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify an exact stage-only bundle against a preview-ready v6 authority."
    )
    parser.add_argument("--authority", type=Path, required=True)
    parser.add_argument("--expected-authority-sha256", required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        authority = verify_bundle(
            authority_path=args.authority,
            expected_authority_sha256=args.expected_authority_sha256,
            bundle_root=args.bundle_root,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"preview-ready candidate upload blocked: {exc}", file=sys.stderr)
        return 1
    candidate = authority.get("candidate")
    version = candidate.get("version") if isinstance(candidate, dict) else ""
    print(f"preview_ready_candidate_upload:ok version={version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
