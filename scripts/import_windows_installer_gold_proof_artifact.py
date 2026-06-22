#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOWNLOADS_ROOT = ROOT / "Chummer.Portal" / "downloads"
STARTUP_RECEIPT_NAME = "startup-smoke-avalonia-win-x64.receipt.json"
VISUAL_SOURCE_NAME = "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
VERIFY_SCRIPT = ROOT / "scripts" / "verify_windows_installer_visual_audit.py"
REQUIRED_SURFACES = {"install-progress", "completion"}


def load_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid json: {path} ({exc})") from exc
    if not isinstance(loaded, dict):
        raise SystemExit(f"json root is not an object: {path}")
    return loaded


def ensure_safe_member(member: str) -> None:
    path = Path(member)
    if path.is_absolute() or ".." in path.parts:
        raise SystemExit(f"unsafe zip member path: {member}")


def extracted_or_directory(source: Path, temp_root: Path) -> Path:
    if source.is_dir():
        return source
    if not source.is_file():
        raise SystemExit(f"proof artifact not found: {source}")
    if source.suffix.lower() != ".zip":
        raise SystemExit(f"proof artifact must be a directory or .zip: {source}")

    output = temp_root / "windows-installer-gold-proof"
    output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as archive:
        for member in archive.namelist():
            ensure_safe_member(member)
        archive.extractall(output)
    return output


def find_unique(root: Path, name: str) -> Path:
    matches = sorted(path for path in root.rglob(name) if path.is_file())
    if not matches:
        raise SystemExit(f"proof artifact is missing {name}")
    if len(matches) > 1:
        preferred = [path for path in matches if "Chummer.Portal" in path.parts]
        if len(preferred) == 1:
            return preferred[0]
        raise SystemExit(f"proof artifact contains multiple {name} files: {matches}")
    return matches[0]


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def normalized_surface(value: Any) -> str:
    surface = normalized(value).replace("_", "-").replace(" ", "-")
    aliases = {
        "progress": "install-progress",
        "install": "install-progress",
        "splash": "install-progress",
        "install-splash": "install-progress",
        "complete": "completion",
        "install-complete": "completion",
    }
    return aliases.get(surface, surface)


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def capture_bounds_look_like_desktop_fallback(row: dict[str, Any]) -> bool:
    mode = normalized(row.get("captureMode"))
    if mode not in {"window-bounds", "reused-same-surface"}:
        return False
    if normalized_surface(row.get("surface")) not in REQUIRED_SURFACES:
        return False

    bounds = row.get("captureBounds")
    if not isinstance(bounds, dict):
        return False
    try:
        left = int(bounds.get("left", 0))
        top = int(bounds.get("top", 0))
        width = int(bounds.get("width", 0))
        height = int(bounds.get("height", 0))
    except (TypeError, ValueError):
        return False

    return left == 0 and top == 0 and width >= 1000 and height >= 700


def resolve_screenshot(source_root: Path, raw_path: Any) -> Path:
    raw = str(raw_path or "").strip()
    if not raw:
        raise SystemExit("visual audit screenshot row has an empty path")
    candidate = Path(raw)
    if candidate.is_absolute():
        if not candidate.is_file():
            raise SystemExit(f"visual audit screenshot is missing: {candidate}")
        return candidate
    direct = source_root / candidate
    if direct.is_file():
        return direct
    matches = sorted(path for path in source_root.rglob(candidate.name) if path.is_file())
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise SystemExit(f"visual audit screenshot is missing: {raw}")
    raise SystemExit(f"visual audit screenshot path is ambiguous: {raw}")


def validate_visual_payload_before_import(visual_source: Path, visual_payload: dict[str, Any]) -> None:
    screenshots = visual_payload.get("screenshots")
    if not isinstance(screenshots, list):
        raise SystemExit(f"visual audit source has no screenshots list: {visual_source}")

    surfaces_by_hash: dict[str, set[str]] = {}
    for row in screenshots:
        if not isinstance(row, dict):
            raise SystemExit("visual audit screenshot row is not an object")
        if capture_bounds_look_like_desktop_fallback(row):
            raise SystemExit(
                "visual audit screenshot used full-desktop fallback bounds instead of installer window: "
                f"{row.get('path')}"
            )
        screenshot_source = resolve_screenshot(visual_source.parent, row.get("path"))
        surface = normalized_surface(row.get("surface"))
        if surface in REQUIRED_SURFACES:
            surfaces_by_hash.setdefault(sha256_file(screenshot_source), set()).add(surface)

    for screenshot_sha, surfaces in sorted(surfaces_by_hash.items()):
        if len(surfaces) > 1:
            raise SystemExit(
                "visual audit screenshots for distinct required surfaces are byte-identical: "
                f"{screenshot_sha} covers {', '.join(sorted(surfaces))}"
            )


def import_artifact(artifact_root: Path, downloads_root: Path) -> dict[str, Any]:
    startup_source = find_unique(artifact_root, STARTUP_RECEIPT_NAME)
    visual_source = find_unique(artifact_root, VISUAL_SOURCE_NAME)
    visual_payload = load_json(visual_source)
    validate_visual_payload_before_import(visual_source, visual_payload)

    startup_destination = downloads_root / "startup-smoke" / STARTUP_RECEIPT_NAME
    visual_destination_root = downloads_root / "visual-audit" / "windows-installer"
    visual_destination = visual_destination_root / VISUAL_SOURCE_NAME

    copy_file(startup_source, startup_destination)
    copy_file(visual_source, visual_destination)

    copied_screenshots: list[str] = []
    screenshots = visual_payload.get("screenshots")
    if not isinstance(screenshots, list):
        raise SystemExit(f"visual audit source has no screenshots list: {visual_source}")
    for row in screenshots:
        if not isinstance(row, dict):
            raise SystemExit("visual audit screenshot row is not an object")
        screenshot_source = resolve_screenshot(visual_source.parent, row.get("path"))
        screenshot_destination = visual_destination_root / Path(str(row.get("path") or screenshot_source.name)).name
        copy_file(screenshot_source, screenshot_destination)
        copied_screenshots.append(str(screenshot_destination))

    return {
        "startupReceipt": str(startup_destination),
        "visualAuditSource": str(visual_destination),
        "screenshots": copied_screenshots,
    }


def run_verifier(downloads_root: Path) -> int:
    completed = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--downloads-root",
            str(downloads_root),
        ],
        cwd=ROOT,
    )
    return int(completed.returncode)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import a windows-installer-gold-proof bundle into the downloads proof shelf.")
    parser.add_argument("artifact", type=Path, help="Exported Windows proof bundle directory or zip.")
    parser.add_argument("--downloads-root", type=Path, default=DEFAULT_DOWNLOADS_ROOT)
    parser.add_argument("--verify", action="store_true", help="Run verify_windows_installer_visual_audit.py after import.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with tempfile.TemporaryDirectory(prefix="windows-installer-gold-proof-import-") as temp_dir:
        artifact_root = extracted_or_directory(args.artifact, Path(temp_dir))
        summary = import_artifact(artifact_root, args.downloads_root)

    print(json.dumps({"status": "imported", **summary}, indent=2))
    if args.verify:
        return run_verifier(args.downloads_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
