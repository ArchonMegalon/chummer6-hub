#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ "$#" -gt 0 ]]; then
  TARGETS=("$@")
else
  TARGETS=("$REPO_ROOT/Docker/Amends")
fi

python3 - "$REPO_ROOT" "${TARGETS[@]}" <<'PY'
import hashlib
import json
import re
import sys
from pathlib import Path

HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def normalize_checksum(value: str, context: str, errors: list[str]) -> str | None:
    raw = (value or "").strip()
    if raw.lower().startswith("sha256:"):
        raw = raw[7:]
    if not HEX64.fullmatch(raw):
        errors.append(f"{context}: invalid checksum '{value}'. Expected 64-char SHA-256 hex or sha256:<hex>.")
        return None
    return raw.lower()


def resolve_targets(repo_root: Path, args: list[str], errors: list[str]) -> list[Path]:
    manifests: list[Path] = []
    seen: set[Path] = set()
    for arg in args:
        candidate = Path(arg)
        if not candidate.is_absolute():
            candidate = (repo_root / candidate).resolve()
        else:
            candidate = candidate.resolve()

        if candidate.is_file():
            if candidate.name != "manifest.json":
                errors.append(f"{candidate}: expected a manifest.json file.")
                continue
            if candidate not in seen:
                manifests.append(candidate)
                seen.add(candidate)
            continue

        if candidate.is_dir():
            direct = candidate / "manifest.json"
            found: list[Path]
            if direct.is_file():
                found = [direct]
            else:
                found = sorted(candidate.rglob("manifest.json"))

            if not found:
                errors.append(f"{candidate}: no manifest.json found.")
                continue

            for manifest in found:
                resolved = manifest.resolve()
                if resolved in seen:
                    continue
                manifests.append(resolved)
                seen.add(resolved)
            continue

        errors.append(f"{candidate}: target does not exist.")
    return manifests


def rel_under(root: Path, path: Path) -> str | None:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def collect_release_files(pack_root: Path) -> list[str]:
    release_files: list[str] = []
    for relative in ("data", "lang"):
        folder = pack_root / relative
        if not folder.is_dir():
            continue
        for file_path in sorted(folder.rglob("*")):
            if file_path.is_file():
                rel = file_path.relative_to(pack_root).as_posix()
                release_files.append(rel)
    return release_files


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def validate_manifest(manifest_path: Path, errors: list[str]) -> tuple[int, int]:
    raw_text = manifest_path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        errors.append(f"{manifest_path}: invalid JSON ({exc.msg} at line {exc.lineno}, col {exc.colno}).")
        return (0, 0)

    checksums = payload.get("checksums")
    if not isinstance(checksums, dict) or len(checksums) == 0:
        errors.append(f"{manifest_path}: checksums map is required and must be non-empty.")
        return (0, 0)

    pack_root = manifest_path.parent.resolve()
    release_files = collect_release_files(pack_root)
    checksum_keys = [str(key).replace("\\", "/").strip() for key in checksums.keys()]

    if not release_files:
        errors.append(f"{manifest_path}: no release files found under data/ or lang/ to validate.")
        return (0, 0)

    release_set = set(release_files)
    checksum_set = set(checksum_keys)

    missing = sorted(release_set - checksum_set)
    for rel in missing:
        errors.append(f"{manifest_path}: missing checksum entry for '{rel}'.")

    extra = sorted(checksum_set - release_set)
    for rel in extra:
        errors.append(f"{manifest_path}: checksum entry '{rel}' does not map to a data/lang release file.")

    validated = 0
    for original_key, original_value in sorted(checksums.items(), key=lambda item: str(item[0])):
        rel_key = str(original_key).replace("\\", "/").strip()
        if not rel_key:
            errors.append(f"{manifest_path}: checksum key must be a non-empty relative path.")
            continue

        target = (pack_root / rel_key).resolve()
        rel = rel_under(pack_root, target)
        if rel is None:
            errors.append(f"{manifest_path}: checksum path '{original_key}' escapes pack root.")
            continue

        if rel not in release_set:
            # Reported above as extra; skip hash validation.
            continue

        if not target.is_file():
            errors.append(f"{manifest_path}: checksum path '{rel_key}' does not exist as a file.")
            continue

        normalized = normalize_checksum(str(original_value), f"{manifest_path}::{rel}", errors)
        if normalized is None:
            continue

        actual = sha256_file(target)
        if actual != normalized:
            errors.append(
                f"{manifest_path}: checksum mismatch for '{rel}'. expected {normalized}, actual {actual}."
            )
            continue

        validated += 1

    return (len(release_files), validated)


def main() -> int:
    repo_root = Path(sys.argv[1]).resolve()
    args = sys.argv[2:]
    errors: list[str] = []
    manifests = resolve_targets(repo_root, args, errors)

    if not manifests:
        if not errors:
            errors.append("No amend manifests found.")
        for message in errors:
            print(f"ERROR: {message}", file=sys.stderr)
        return 1

    total_release_files = 0
    total_validated = 0
    for manifest in manifests:
        release_count, validated_count = validate_manifest(manifest, errors)
        total_release_files += release_count
        total_validated += validated_count

    if errors:
        for message in errors:
            print(f"ERROR: {message}", file=sys.stderr)
        return 1

    print(
        f"Validated {len(manifests)} amend manifest(s) with checksums for "
        f"{total_validated}/{total_release_files} release file(s)."
    )
    return 0


raise SystemExit(main())
PY
