#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


PASSING_STATUSES = {"pass", "passed", "ready"}
REQUIRED_ROLES = {"progress", "completion"}
DEFAULT_VISUAL_PROOF_PATH = Path(
    os.environ.get(
        "CHUMMER_WINDOWS_INSTALLER_VISUAL_PROOF_PATH",
        "/docker/chummercomplete/chummer6-ui/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
    )
)


@dataclass(frozen=True)
class ManifestRow:
    artifact_id: str
    file_name: str
    version: str
    head: str
    rid: str


def normalize_token(value: Any) -> str:
    return str(value or "").strip().lower()


def is_windows_installer_name(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith("chummer-") and lowered.endswith("-win-x64-installer.exe") or (
        lowered.startswith("chummer-") and "-win-" in lowered and lowered.endswith("-installer.exe")
    )


def resolve_file_name(item: dict[str, Any]) -> str:
    file_name = str(item.get("fileName") or "").strip()
    if file_name:
        return file_name
    raw_url = str(item.get("downloadUrl") or item.get("url") or "").strip()
    return Path(urlparse(raw_url).path).name if raw_url else ""


def infer_head_id(installer_name: str) -> str:
    lowered = installer_name.lower()
    if lowered.startswith("chummer-blazor-desktop-"):
        return "blazor-desktop"
    if lowered.startswith("chummer-avalonia-"):
        return "avalonia"
    return ""


def infer_rid(installer_name: str) -> str:
    lowered = installer_name.lower()
    suffix = "-installer.exe"
    if not lowered.endswith(suffix):
        return ""
    stem = lowered[: -len(suffix)]
    marker = stem.rfind("-win-")
    if marker < 0:
        return ""
    return stem[marker + 1 :]


def read_manifest_rows(manifest_paths: list[Path]) -> dict[str, ManifestRow]:
    rows: dict[str, ManifestRow] = {}
    for manifest_path in manifest_paths:
        if not manifest_path.is_file():
            continue
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            continue
        version = str(payload.get("version") or payload.get("releaseVersion") or "").strip()
        for collection_name in ("artifacts", "downloads"):
            collection = payload.get(collection_name)
            if not isinstance(collection, list):
                continue
            for item in collection:
                if not isinstance(item, dict):
                    continue
                file_name = resolve_file_name(item)
                if not file_name or not is_windows_installer_name(file_name):
                    continue
                rows[file_name] = ManifestRow(
                    artifact_id=str(item.get("artifactId") or item.get("id") or "").strip(),
                    file_name=file_name,
                    version=str(item.get("version") or version or "").strip(),
                    head=str(item.get("head") or "").strip(),
                    rid=str(item.get("rid") or "").strip(),
                )
    return rows


def find_installers(files_dir: Path | None, explicit_installers: list[Path]) -> list[Path]:
    installers: list[Path] = [path.resolve() for path in explicit_installers]
    if files_dir is not None and files_dir.is_dir():
        installers.extend(sorted(path.resolve() for path in files_dir.glob("chummer-*-win-*-installer.exe")))
    seen: set[Path] = set()
    unique: list[Path] = []
    for installer in installers:
        if installer in seen:
            continue
        seen.add(installer)
        unique.append(installer)
    return unique


def split_tokens(value: str | None) -> set[str]:
    tokens: set[str] = set()
    for raw in str(value or "").replace(";", ",").replace("\n", ",").split(","):
        for token in raw.split():
            token = token.strip().lower()
            if token:
                tokens.add(token)
    return tokens


def is_disabled_installer(installer_path: Path, manifest_row: ManifestRow | None, disabled_tokens: set[str]) -> bool:
    if not disabled_tokens:
        return False

    candidates = {installer_path.name.lower()}
    if manifest_row is not None:
        for value in (manifest_row.artifact_id, manifest_row.file_name):
            value = str(value or "").strip().lower()
            if value:
                candidates.add(value)
    return any(token in candidates for token in disabled_tokens)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return payload


def screenshot_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    screenshots = payload.get("screenshots")
    mapped: dict[str, dict[str, Any]] = {}
    if not isinstance(screenshots, list):
        return mapped
    for item in screenshots:
        if not isinstance(item, dict):
            continue
        role = normalize_token(item.get("role"))
        if role:
            mapped[role] = item
    return mapped


def status_is_passing(value: Any) -> bool:
    return normalize_token(value) in PASSING_STATUSES


def nested_status(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, dict):
            status = str(value.get("status") or "").strip()
            if status:
                return status
    return ""


def verify_installer(installer_path: Path, manifest_row: ManifestRow | None, visual_proof_path: Path) -> list[str]:
    failures: list[str] = []
    if not installer_path.is_file():
        return [f"installer does not exist: {installer_path}"]

    if manifest_row is None:
        failures.append("Windows installer is missing from the supplied release manifest")

    if not visual_proof_path.is_file():
        return ["Windows installer visual proof is missing; capture progress and completion screenshots on a Windows host."]

    payload = load_json(visual_proof_path)
    contract = str(payload.get("contractName") or payload.get("contract_name") or "").strip()
    if contract != "chummer6-ui.windows_installer_visual_proof":
        failures.append("Windows installer visual proof contract is not chummer6-ui.windows_installer_visual_proof.")

    status = str(payload.get("status") or "").strip()
    if not status_is_passing(status):
        failures.append("Windows installer visual proof status is not passing.")

    expected_head = (manifest_row.head if manifest_row is not None and manifest_row.head else infer_head_id(installer_path.name)).strip()
    expected_rid = (manifest_row.rid if manifest_row is not None and manifest_row.rid else infer_rid(installer_path.name)).strip()
    expected_version = manifest_row.version.strip() if manifest_row is not None else ""
    expected_digest = f"sha256:{sha256_file(installer_path)}"

    visual_head = str(payload.get("headId") or payload.get("head") or "").strip()
    visual_rid = str(payload.get("rid") or "").strip()
    visual_version = str(payload.get("releaseVersion") or payload.get("version") or "").strip()
    visual_digest = str(payload.get("artifactDigest") or payload.get("installerDigest") or "").strip().lower()

    if expected_head and visual_head and visual_head != expected_head:
        failures.append(f"Windows installer visual proof head does not match promoted head {expected_head}.")
    if expected_rid and visual_rid and visual_rid != expected_rid:
        failures.append(f"Windows installer visual proof rid does not match promoted RID {expected_rid}.")
    if expected_version and visual_version and visual_version != expected_version:
        failures.append("Windows installer visual proof version does not match release channel.")
    if visual_digest != expected_digest:
        failures.append("Windows installer visual proof artifactDigest does not match promoted installer bytes.")

    screenshots = screenshot_map(payload)
    missing_roles = sorted(REQUIRED_ROLES - set(screenshots))
    if missing_roles:
        failures.append(
            "Windows installer visual proof is missing required screenshot roles: "
            + ", ".join(missing_roles)
            + "."
        )

    missing_files: list[str] = []
    missing_digests: list[str] = []
    distinct_digests: set[str] = set()
    for role in sorted(REQUIRED_ROLES & set(screenshots)):
        shot = screenshots[role]
        shot_path = Path(str(shot.get("path") or "").strip())
        if not shot_path.is_file():
            missing_files.append(role)
            continue
        digest = str(shot.get("imageDigest") or "").strip().lower()
        if not digest:
            raw_sha = str(shot.get("sha256") or shot.get("imageSha256") or "").strip().lower()
            digest = f"sha256:{raw_sha}" if raw_sha else ""
        if not digest:
            missing_digests.append(role)
        else:
            distinct_digests.add(digest)
            actual_digest = f"sha256:{sha256_file(shot_path)}"
            if actual_digest != digest:
                failures.append(
                    "Windows installer visual proof screenshot digests do not match the referenced files for: "
                    + role
                    + "."
                )
    if missing_files:
        failures.append(
            "Windows installer visual proof screenshot files are missing for: "
            + ", ".join(missing_files)
            + "."
        )
    if missing_digests:
        failures.append(
            "Windows installer visual proof screenshots are missing image digests for: "
            + ", ".join(missing_digests)
            + "."
        )
    if not missing_roles and not missing_files and len(distinct_digests) < len(REQUIRED_ROLES):
        failures.append("Windows installer visual proof screenshots are not distinct across progress and completion.")

    for review_name, review_status in (
        ("readability", nested_status(payload, "readabilityReview", "textReadabilityReview", "readability")),
        ("contrast", nested_status(payload, "contrastReview", "contrast")),
        ("clipping", nested_status(payload, "clippingReview", "clipping")),
    ):
        if not status_is_passing(review_status):
            failures.append(f"Windows installer visual proof {review_name} review is not passing.")

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail if a promoted Windows Chummer installer lacks a matching passing visual-proof receipt."
    )
    parser.add_argument("--files-dir", type=Path, help="Bundle files directory containing installers.")
    parser.add_argument("--manifest", type=Path, action="append", default=[], help="Release manifest to cross-check version/head/rid.")
    parser.add_argument("--installer", type=Path, action="append", default=[], help="Specific installer .exe to check.")
    parser.add_argument("--visual-proof", type=Path, default=DEFAULT_VISUAL_PROOF_PATH, help="Path to WINDOWS_INSTALLER_VISUAL_PROOF.generated.json.")
    parser.add_argument("--disabled-artifact-id", action="append", default=[], help="Skip a quarantined Windows installer artifact id or file name.")
    parser.add_argument("--allow-empty", action="store_true", help="Pass when no Windows installers are present.")
    args = parser.parse_args()

    files_dir = args.files_dir.resolve() if args.files_dir else None
    manifest_rows = read_manifest_rows([path.resolve() for path in args.manifest])
    disabled_tokens: set[str] = set()
    for value in args.disabled_artifact_id:
        disabled_tokens.update(split_tokens(value))
    disabled_tokens.update(split_tokens(os.environ.get("CHUMMER_PUBLIC_DISABLED_ARTIFACT_IDS")))
    disabled_tokens.update(split_tokens(os.environ.get("CHUMMER_RELEASE_DISABLED_ARTIFACT_IDS")))
    installers = [
        installer
        for installer in find_installers(files_dir, args.installer)
        if not is_disabled_installer(installer, manifest_rows.get(installer.name), disabled_tokens)
    ]
    if not installers:
        if args.allow_empty:
            print("windows_installer_visual_proof_gate:ok no_windows_installers")
            return 0
        print("windows_installer_visual_proof_gate:fail no Windows installers found", file=sys.stderr)
        return 1

    visual_proof_path = args.visual_proof.resolve()
    failures: list[str] = []
    for installer_path in installers:
        failures.extend(
            f"{installer_path.name}: {failure}"
            for failure in verify_installer(installer_path, manifest_rows.get(installer_path.name), visual_proof_path)
        )

    if failures:
        print("windows_installer_visual_proof_gate:fail", file=sys.stderr)
        for failure in failures:
            print(f" - {failure}", file=sys.stderr)
        return 1

    print(f"windows_installer_visual_proof_gate:ok checked={len(installers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
