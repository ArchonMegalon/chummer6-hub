#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import struct
import sys
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any


APPENDED_PAYLOAD_MAGIC = b"CHUMMER6PAYLOAD1"
FOOTER_LENGTH = len(APPENDED_PAYLOAD_MAGIC) + 8

DEFAULT_LAUNCH_EXECUTABLES = {
    "avalonia": "Chummer.Avalonia.exe",
    "blazor-desktop": "Chummer.Blazor.Desktop.exe",
}


@dataclass(frozen=True)
class ManifestRow:
    file_name: str
    payload_file_name: str
    payload_sha256: str
    payload_size_bytes: int | None
    installer_mode: str


@dataclass(frozen=True)
class PayloadCandidate:
    mode: str
    source: str
    data: bytes


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().lower()


def normalize_zip_name(value: str) -> str:
    return value.replace("\\", "/").lstrip("/")


def is_truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def is_windows_installer_name(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith("chummer-") and lowered.endswith("-win-x64-installer.exe") or (
        lowered.startswith("chummer-") and "-win-" in lowered and lowered.endswith("-installer.exe")
    )


def expected_payload_name(installer_name: str) -> str:
    lowered = installer_name.lower()
    if not lowered.endswith("-installer.exe"):
        return ""
    return installer_name[: -len("-installer.exe")] + "-payload.zip"


def infer_head_id(installer_name: str) -> str:
    lowered = installer_name.lower()
    if lowered.startswith("chummer-blazor-desktop-"):
        return "blazor-desktop"
    if lowered.startswith("chummer-avalonia-"):
        return "avalonia"
    return ""


def infer_launch_executables(installer_name: str) -> list[str]:
    head_id = infer_head_id(installer_name)
    if head_id in DEFAULT_LAUNCH_EXECUTABLES:
        return [DEFAULT_LAUNCH_EXECUTABLES[head_id]]
    return []


def read_manifest_rows(manifest_paths: list[Path]) -> dict[str, ManifestRow]:
    rows: dict[str, ManifestRow] = {}
    for manifest_path in manifest_paths:
        if not manifest_path.is_file():
            continue
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        if not isinstance(payload, dict):
            continue
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
                    file_name=file_name,
                    payload_file_name=str(item.get("payloadFileName") or "").strip(),
                    payload_sha256=str(item.get("payloadSha256") or "").strip().lower(),
                    payload_size_bytes=try_int(item.get("payloadSizeBytes")),
                    installer_mode=str(item.get("installerMode") or "").strip().lower(),
                )
    return rows


def resolve_file_name(item: dict[str, Any]) -> str:
    file_name = str(item.get("fileName") or "").strip()
    if file_name:
        return file_name
    raw_url = str(item.get("downloadUrl") or item.get("url") or "").strip()
    return Path(raw_url).name if raw_url else ""


def try_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def find_installers(files_dir: Path | None, explicit_installers: list[Path]) -> list[Path]:
    installers: list[Path] = [path.resolve() for path in explicit_installers]
    if files_dir is not None and files_dir.is_dir():
        installers.extend(
            sorted(path.resolve() for path in files_dir.glob("chummer-*-win-*-installer.exe"))
        )
    seen: set[Path] = set()
    unique: list[Path] = []
    for installer in installers:
        if installer in seen:
            continue
        seen.add(installer)
        unique.append(installer)
    return unique


def read_appended_payload(installer_path: Path) -> PayloadCandidate | None:
    file_size = installer_path.stat().st_size
    if file_size < FOOTER_LENGTH:
        return None

    with installer_path.open("rb") as handle:
        handle.seek(file_size - FOOTER_LENGTH)
        footer = handle.read(FOOTER_LENGTH)
        payload_length = struct.unpack("<q", footer[:8])[0]
        magic = footer[8:]
        if magic != APPENDED_PAYLOAD_MAGIC:
            return None
        payload_offset = file_size - FOOTER_LENGTH - payload_length
        if payload_length <= 0 or payload_offset < 0:
            raise ValueError(f"{installer_path.name}: appended payload footer is invalid")
        handle.seek(payload_offset)
        data = handle.read(payload_length)
        if len(data) != payload_length:
            raise ValueError(f"{installer_path.name}: appended payload is truncated")
    return PayloadCandidate("bundled", "appended-footer", data)


def read_sidecar_payload(
    installer_path: Path,
    files_dir: Path | None,
    explicit_payload: Path | None,
    manifest_row: ManifestRow | None,
) -> PayloadCandidate | None:
    candidates: list[Path] = []
    if explicit_payload is not None:
        candidates.append(explicit_payload)
    if manifest_row is not None and manifest_row.payload_file_name:
        if files_dir is not None:
            candidates.append(files_dir / manifest_row.payload_file_name)
        candidates.append(installer_path.parent / manifest_row.payload_file_name)
    payload_name = expected_payload_name(installer_path.name)
    if payload_name:
        if files_dir is not None:
            candidates.append(files_dir / payload_name)
        candidates.append(installer_path.parent / payload_name)

    seen: set[Path] = set()
    for candidate in candidates:
        candidate = candidate.resolve()
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.is_file():
            return PayloadCandidate("bootstrap", str(candidate), candidate.read_bytes())
    return None


def validate_manifest_payload_metadata(candidate: PayloadCandidate, manifest_row: ManifestRow | None) -> list[str]:
    if manifest_row is None:
        return []
    failures: list[str] = []
    if manifest_row.installer_mode == "bootstrap" and candidate.mode != "bootstrap":
        failures.append("manifest says installerMode=bootstrap but the payload was not a sidecar payload")
    if manifest_row.installer_mode == "bundled" and candidate.mode != "bundled":
        failures.append("manifest says installerMode=bundled but the payload was not appended")
    if candidate.mode == "bootstrap":
        source_name = Path(candidate.source).name
        if manifest_row.payload_file_name and manifest_row.payload_file_name != source_name:
            failures.append(
                f"manifest payloadFileName {manifest_row.payload_file_name} does not match sidecar {source_name}"
            )
        if manifest_row.payload_sha256 and manifest_row.payload_sha256 != sha256_bytes(candidate.data):
            failures.append("manifest payloadSha256 does not match sidecar bytes")
        if manifest_row.payload_size_bytes is not None and manifest_row.payload_size_bytes != len(candidate.data):
            failures.append(
                f"manifest payloadSizeBytes {manifest_row.payload_size_bytes} does not match sidecar size {len(candidate.data)}"
            )
    return failures


def parse_heads_json_base64(value: str) -> list[str]:
    if not value.strip():
        return []
    decoded = base64.b64decode(value)
    payload = json.loads(decoded.decode("utf-8"))
    if not isinstance(payload, list):
        return []
    entries: list[str] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        launch = str(item.get("launchExecutable") or "").strip()
        root = str(item.get("relativeRoot") or "").strip().strip("/\\")
        if not launch:
            continue
        entries.append(normalize_zip_name(f"{root}/{launch}" if root else launch))
    return entries


def validate_zip_payload(
    installer_name: str,
    candidate: PayloadCandidate,
    expected_launches: list[str],
    expected_entries: list[str],
    require_sample: bool,
) -> list[str]:
    failures: list[str] = []
    try:
        with zipfile.ZipFile(BytesIO(candidate.data), "r") as archive:
            names = [normalize_zip_name(info.filename) for info in archive.infolist() if not info.is_dir()]
            if not names:
                return ["payload zip contains no files"]
            for name in names:
                parts = [part for part in name.split("/") if part]
                if name.startswith("/") or any(part == ".." for part in parts):
                    failures.append(f"payload zip contains unsafe entry: {name}")
            name_set = set(names)
            basename_set = {Path(name).name.lower() for name in names}
            for expected_entry in expected_entries:
                normalized = normalize_zip_name(expected_entry)
                if normalized not in name_set:
                    failures.append(f"payload zip is missing expected entry: {normalized}")
            launches = expected_launches or infer_launch_executables(installer_name)
            for launch in launches:
                if Path(launch).name.lower() not in basename_set:
                    failures.append(f"payload zip is missing launch executable: {Path(launch).name}")
            if require_sample and "soma-career.chum5" not in basename_set:
                failures.append("payload zip is missing bundled sample character: Soma-Career.chum5")
    except zipfile.BadZipFile as exc:
        failures.append(f"payload is not a readable zip: {exc}")
    return failures


def verify_installer(
    installer_path: Path,
    files_dir: Path | None,
    explicit_payload: Path | None,
    manifest_row: ManifestRow | None,
    expected_launches: list[str],
    expected_entries: list[str],
    require_sample: bool,
) -> list[str]:
    failures: list[str] = []
    if not installer_path.is_file():
        return [f"installer does not exist: {installer_path}"]
    if installer_path.stat().st_size <= FOOTER_LENGTH:
        return [f"installer is too small to contain a payload-aware executable: {installer_path}"]

    candidate = read_appended_payload(installer_path)
    if candidate is None:
        candidate = read_sidecar_payload(installer_path, files_dir, explicit_payload, manifest_row)

    if candidate is None:
        payload_name = expected_payload_name(installer_path.name) or "<unknown>"
        return [
            f"{installer_path.name}: no appended payload and no bootstrap sidecar '{payload_name}' was found"
        ]

    failures.extend(validate_manifest_payload_metadata(candidate, manifest_row))
    failures.extend(
        validate_zip_payload(
            installer_path.name,
            candidate,
            expected_launches,
            expected_entries,
            require_sample,
        )
    )
    return [f"{installer_path.name}: {failure}" for failure in failures]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail if a Windows Chummer installer cannot reach its bundled/bootstrap payload."
    )
    parser.add_argument("--files-dir", type=Path, help="Bundle files directory containing installers and payload sidecars.")
    parser.add_argument("--manifest", type=Path, action="append", default=[], help="Release manifest to cross-check payload metadata.")
    parser.add_argument("--installer", type=Path, action="append", default=[], help="Specific installer .exe to check.")
    parser.add_argument("--payload", type=Path, help="Specific payload zip to use for an explicit installer check.")
    parser.add_argument("--expected-launch", action="append", default=[], help="Launch executable basename expected in the payload zip.")
    parser.add_argument("--expected-entry", action="append", default=[], help="Exact zip entry expected in the payload zip.")
    parser.add_argument("--heads-json-base64", default="", help="Installer heads JSON metadata used to derive exact payload entries.")
    parser.add_argument("--require-sample", action="store_true", help="Require the legacy Soma sample character in the payload.")
    parser.add_argument("--allow-empty", action="store_true", help="Pass when no Windows installers are present.")
    args = parser.parse_args()

    files_dir = args.files_dir.resolve() if args.files_dir else None
    manifest_rows = read_manifest_rows([path.resolve() for path in args.manifest])
    installers = find_installers(files_dir, args.installer)
    if not installers:
        if args.allow_empty:
            print("windows_installer_payload_gate:ok no_windows_installers")
            return 0
        print("windows_installer_payload_gate:fail no Windows installers found", file=sys.stderr)
        return 1

    expected_entries = [normalize_zip_name(entry) for entry in args.expected_entry]
    expected_entries.extend(parse_heads_json_base64(args.heads_json_base64))
    require_sample = args.require_sample or is_truthy(os.environ.get("CHUMMER_WINDOWS_INSTALLER_REQUIRE_SAMPLE_PAYLOAD"))
    failures: list[str] = []
    for installer_path in installers:
        manifest_row = manifest_rows.get(installer_path.name)
        failures.extend(
            verify_installer(
                installer_path,
                files_dir,
                args.payload.resolve() if args.payload else None,
                manifest_row,
                [str(item).strip() for item in args.expected_launch if str(item).strip()],
                expected_entries,
                require_sample,
            )
        )

    if failures:
        print("windows_installer_payload_gate:fail", file=sys.stderr)
        for failure in failures:
            print(f" - {failure}", file=sys.stderr)
        return 1

    print(f"windows_installer_payload_gate:ok checked={len(installers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
