#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = ROOT / ".codex-studio" / "published"
OUTPUT_PATH = PUBLISHED_ROOT / "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json"
DEFAULT_BASE_URL = "https://chummer.run"


def resolve_default_verify_script() -> Path:
    raw_script = os.environ.get("CHUMMER_WINDOWS_INSTALLER_PAYLOAD_VERIFY_SCRIPT", "").strip()
    if raw_script:
        return Path(raw_script).expanduser()

    raw_presentation = os.environ.get("CHUMMER_PRESENTATION_ROOT", "").strip()
    candidates = []
    if raw_presentation:
        candidates.append(Path(raw_presentation).expanduser() / "scripts" / "verify-windows-installer-payloads.py")
    candidates.extend(
        [
            ROOT.parent / "chummer-presentation" / "scripts" / "verify-windows-installer-payloads.py",
            Path("/docker/chummercomplete/chummer-presentation/scripts/verify-windows-installer-payloads.py"),
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


DEFAULT_VERIFY_SCRIPT = resolve_default_verify_script()


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36 chummer-live-public-windows-installer/1",
            "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
        },
    )


def fetch_bytes(url: str) -> bytes:
    with urllib.request.urlopen(request(url), timeout=60) as response:
        return response.read()


def fetch_json(url: str) -> Any:
    return json.loads(fetch_bytes(url).decode("utf-8"))


def normalize_url(base_url: str, value: str) -> str:
    return urllib.parse.urljoin(f"{base_url.rstrip('/')}/", value)


def is_windows_bootstrap_installer(row: dict[str, Any]) -> bool:
    kind = str(row.get("kind") or "").strip().lower()
    installer_mode = str(row.get("installerMode") or "").strip().lower()
    file_name = str(row.get("fileName") or "").strip().lower()
    platform = str(row.get("platform") or "").strip().lower()
    platform_id = str(row.get("platformId") or "").strip().lower()
    return (
        kind == "installer"
        and installer_mode == "bootstrap"
        and file_name.endswith(".exe")
        and ("windows" in platform or "win" in platform_id or "-win-" in str(row.get("id") or "").lower())
    )


def build_sidecar_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "contractName": "chummer6-ui.windows_bootstrap_payload",
        "fileName": str(row.get("payloadFileName") or ""),
        "downloadUrl": str(row.get("payloadDownloadUrl") or ""),
        "sha256": str(row.get("payloadSha256") or "").lower(),
        "sizeBytes": int(row.get("payloadSizeBytes") or 0),
        "installerFileName": str(row.get("fileName") or ""),
        "releaseVersion": str(row.get("releaseVersion") or row.get("version") or ""),
    }


def verify(base_url: str, verify_script: Path) -> dict[str, Any]:
    base = base_url.rstrip("/")
    manifest_url = normalize_url(base, "/downloads/releases.json")
    failures: list[str] = []
    checked_artifacts: list[dict[str, Any]] = []

    try:
        manifest = fetch_json(manifest_url)
    except Exception as exc:  # pragma: no cover - network failures are environment-driven
        payload = {
            "contract_name": "chummer.live_public_windows_installer",
            "generated_at_utc": now_iso(),
            "base_url": base,
            "manifest_url": manifest_url,
            "verify_script_path": str(verify_script),
            "status": "fail",
            "verdict": "LIVE_PUBLIC_WINDOWS_INSTALLER_NOT_READY",
            "checked_artifacts": [],
            "failures": [f"could not fetch public downloads manifest: {exc}"],
        }
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload

    downloads = manifest.get("downloads") or []
    if not isinstance(downloads, list):
        downloads = []

    windows_rows = [row for row in downloads if isinstance(row, dict) and is_windows_bootstrap_installer(row)]
    if not windows_rows:
        failures.append("public downloads manifest does not expose any Windows bootstrap installer rows")

    if not verify_script.is_file():
        failures.append(f"missing Windows installer payload verifier: {verify_script}")

    with tempfile.TemporaryDirectory(prefix="chummer-live-public-windows-installer-") as temp_root:
        temp_root_path = Path(temp_root)
        files_dir = temp_root_path / "files"
        files_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = temp_root_path / "releases.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        for row in windows_rows:
            artifact_id = str(row.get("id") or row.get("artifactId") or row.get("fileName") or "unknown")
            installer_file_name = str(row.get("fileName") or "")
            installer_url = normalize_url(base, str(row.get("url") or ""))
            payload_file_name = str(row.get("payloadFileName") or "")
            payload_url = normalize_url(base, str(row.get("payloadDownloadUrl") or ""))
            sidecar_url = f"{payload_url}.json" if payload_url else ""
            expected_installer_sha256 = str(row.get("sha256") or "").lower()
            expected_payload_sha256 = str(row.get("payloadSha256") or "").lower()
            expected_installer_size = int(row.get("sizeBytes") or 0)
            expected_payload_size = int(row.get("payloadSizeBytes") or 0)

            installer_path = files_dir / installer_file_name
            payload_path = files_dir / payload_file_name
            sidecar_path = files_dir / f"{payload_file_name}.json"

            row_failures: list[str] = []
            installer_sha256 = ""
            payload_sha256 = ""
            installer_size = 0
            payload_size = 0

            if not installer_file_name:
                row_failures.append("installer row is missing fileName")
            if not installer_url:
                row_failures.append("installer row is missing url")
            if not payload_file_name:
                row_failures.append("installer row is missing payloadFileName")
            if not payload_url:
                row_failures.append("installer row is missing payloadDownloadUrl")

            try:
                installer_bytes = fetch_bytes(installer_url)
                installer_path.write_bytes(installer_bytes)
                installer_sha256 = sha256_bytes(installer_bytes)
                installer_size = len(installer_bytes)
                if expected_installer_sha256 and installer_sha256 != expected_installer_sha256:
                    row_failures.append("installer sha256 does not match public manifest")
                if expected_installer_size and installer_size != expected_installer_size:
                    row_failures.append("installer sizeBytes does not match public manifest")
            except Exception as exc:  # pragma: no cover - exercised indirectly in network failure cases
                row_failures.append(f"could not fetch installer bytes: {exc}")

            try:
                payload_bytes = fetch_bytes(payload_url)
                payload_path.write_bytes(payload_bytes)
                payload_sha256 = sha256_bytes(payload_bytes)
                payload_size = len(payload_bytes)
                if expected_payload_sha256 and payload_sha256 != expected_payload_sha256:
                    row_failures.append("payload sha256 does not match public manifest")
                if expected_payload_size and payload_size != expected_payload_size:
                    row_failures.append("payload sizeBytes does not match public manifest")
            except Exception as exc:  # pragma: no cover - exercised indirectly in network failure cases
                row_failures.append(f"could not fetch payload bytes: {exc}")

            try:
                sidecar_payload = fetch_json(sidecar_url)
                sidecar_path.write_text(json.dumps(sidecar_payload, indent=2) + "\n", encoding="utf-8")
                expected_sidecar = build_sidecar_payload(row)
                if str(sidecar_payload.get("contractName") or "") != expected_sidecar["contractName"]:
                    row_failures.append("payload sidecar contractName does not match")
                if str(sidecar_payload.get("fileName") or "") != expected_sidecar["fileName"]:
                    row_failures.append("payload sidecar fileName does not match")
                if str(sidecar_payload.get("downloadUrl") or "") != expected_sidecar["downloadUrl"]:
                    row_failures.append("payload sidecar downloadUrl does not match")
                if str(sidecar_payload.get("sha256") or "").lower() != expected_sidecar["sha256"]:
                    row_failures.append("payload sidecar sha256 does not match")
                if int(sidecar_payload.get("sizeBytes") or 0) != expected_sidecar["sizeBytes"]:
                    row_failures.append("payload sidecar sizeBytes does not match")
                if str(sidecar_payload.get("installerFileName") or "") != expected_sidecar["installerFileName"]:
                    row_failures.append("payload sidecar installerFileName does not match")
                if str(sidecar_payload.get("releaseVersion") or "") != expected_sidecar["releaseVersion"]:
                    row_failures.append("payload sidecar releaseVersion does not match")
            except Exception as exc:  # pragma: no cover - exercised indirectly in network failure cases
                row_failures.append(f"could not fetch payload sidecar metadata: {exc}")

            checked_artifacts.append(
                {
                    "artifact_id": artifact_id,
                    "installer_file_name": installer_file_name,
                    "installer_url": installer_url,
                    "installer_sha256": installer_sha256,
                    "expected_installer_sha256": expected_installer_sha256,
                    "installer_size_bytes": installer_size,
                    "expected_installer_size_bytes": expected_installer_size,
                    "payload_file_name": payload_file_name,
                    "payload_url": payload_url,
                    "payload_sha256": payload_sha256,
                    "expected_payload_sha256": expected_payload_sha256,
                    "payload_size_bytes": payload_size,
                    "expected_payload_size_bytes": expected_payload_size,
                    "sidecar_url": sidecar_url,
                    "release_version": str(row.get("releaseVersion") or row.get("version") or ""),
                    "status": "pass" if not row_failures else "fail",
                    "failures": row_failures,
                }
            )
            failures.extend(f"{artifact_id}: {item}" for item in row_failures)

        if windows_rows and verify_script.is_file():
            result = subprocess.run(
                [
                    "python3",
                    str(verify_script),
                    "--files-dir",
                    str(files_dir),
                    "--manifest",
                    str(manifest_path),
                    "--require-embedded-bootstrap-metadata",
                    "--require-manifest-row",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                stderr = (result.stderr or result.stdout or "").strip()
                failures.append(f"live public Windows installer payload gate failed: {stderr}")

    payload = {
        "contract_name": "chummer.live_public_windows_installer",
        "generated_at_utc": now_iso(),
        "base_url": base,
        "manifest_url": manifest_url,
        "verify_script_path": str(verify_script),
        "status": "pass" if not failures else "fail",
        "verdict": "LIVE_PUBLIC_WINDOWS_INSTALLER_READY" if not failures else "LIVE_PUBLIC_WINDOWS_INSTALLER_NOT_READY",
        "checked_artifacts": checked_artifacts,
        "failures": failures,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify that the public Windows bootstrap installer bytes served from the live downloads shelf match manifest metadata and the native payload gate.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Public base URL to verify.")
    parser.add_argument("--verify-script", type=Path, default=DEFAULT_VERIFY_SCRIPT, help="Path to verify-windows-installer-payloads.py.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = verify(args.base_url, args.verify_script)
    if payload["status"] != "pass":
        raise SystemExit("live public windows installer verification failed")
    print("live_public_windows_installer:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
