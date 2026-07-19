#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc


ROOT = Path(__file__).resolve().parents[1]
PUBLISHED_ROOT = ROOT / ".codex-studio" / "published"
OUTPUT_PATH = PUBLISHED_ROOT / "LIVE_PUBLIC_WINDOWS_INSTALLER.generated.json"
DEFAULT_BASE_URL = "https://chummer.run"
DEFAULT_FETCH_TIMEOUT_SECONDS = float(
    os.environ.get("CHUMMER_LIVE_WINDOWS_INSTALLER_FETCH_TIMEOUT_SECONDS", "60")
)
DEFAULT_FETCH_ATTEMPTS = max(
    1,
    int(os.environ.get("CHUMMER_LIVE_WINDOWS_INSTALLER_FETCH_ATTEMPTS", "3")),
)
RETRYABLE_FETCH_REASONS = (
    TimeoutError,
    socket.timeout,
    ConnectionAbortedError,
    ConnectionResetError,
    ConnectionRefusedError,
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_FILE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,254}$")
MAX_VERIFIER_BYTES = 2 * 1024 * 1024
MAX_CHILD_DIAGNOSTIC_BYTES = 4096
REPO_VERIFY_SCRIPT = ROOT / "scripts" / "verify-windows-installer-payloads.py"


def resolve_default_verify_script() -> Path:
    raw_script = os.environ.get("CHUMMER_WINDOWS_INSTALLER_PAYLOAD_VERIFY_SCRIPT", "").strip()
    if raw_script:
        return Path(raw_script).expanduser()

    return REPO_VERIFY_SCRIPT


DEFAULT_VERIFY_SCRIPT = resolve_default_verify_script()


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def portable_verify_script_reference(
    verify_script: Path,
    verifier_sha256: str = "",
) -> str:
    resolved = verify_script.expanduser().resolve()
    try:
        relative = resolved.relative_to(ROOT.resolve())
    except ValueError:
        suffix = f"sha256/{verifier_sha256}" if verifier_sha256 else "unverified"
        return f"external://windows-installer-payload-verifier/{suffix}"
    return f"repo://ArchonMegalon/chummer6-hub/{relative.as_posix()}"


def stable_verifier_bytes(verify_script: Path) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(verify_script, flags)
    except OSError as exc:
        raise RuntimeError("Windows installer payload verifier is unavailable") from exc
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size < 1
            or before.st_size > MAX_VERIFIER_BYTES
        ):
            raise RuntimeError("Windows installer payload verifier has unsafe file identity")
        chunks: list[bytes] = []
        remaining = before.st_size + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        payload = b"".join(chunks)
        after = os.fstat(descriptor)
        try:
            path_metadata = verify_script.lstat()
        except OSError as exc:
            raise RuntimeError(
                "Windows installer payload verifier changed during stable read"
            ) from exc
    finally:
        os.close(descriptor)
    if (
        len(payload) != before.st_size
        or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        or (path_metadata.st_dev, path_metadata.st_ino) != (after.st_dev, after.st_ino)
    ):
        raise RuntimeError("Windows installer payload verifier changed during stable read")
    return payload


def authenticate_verifier(
    verify_script: Path,
    expected_sha256: str | None,
) -> tuple[bytes, str, str]:
    verifier_bytes = stable_verifier_bytes(verify_script)
    actual_sha256 = sha256_bytes(verifier_bytes)
    resolved = verify_script.expanduser().resolve()
    is_repo_owned = resolved == REPO_VERIFY_SCRIPT.resolve()
    normalized_expected = str(expected_sha256 or "").strip().lower()
    if not is_repo_owned and not normalized_expected:
        raise RuntimeError(
            "external Windows installer verifier requires CHUMMER_WINDOWS_INSTALLER_PAYLOAD_VERIFY_SCRIPT_EXPECTED_SHA256"
        )
    if normalized_expected:
        if SHA256_RE.fullmatch(normalized_expected) is None:
            raise RuntimeError("Windows installer verifier expected SHA256 is invalid")
        if not hmac.compare_digest(actual_sha256, normalized_expected):
            raise RuntimeError("Windows installer verifier SHA256 does not match its handoff")
    return (
        verifier_bytes,
        actual_sha256,
        portable_verify_script_reference(verify_script, actual_sha256),
    )


def sanitize_child_diagnostic(value: str) -> str:
    text = value[:MAX_CHILD_DIAGNOSTIC_BYTES]
    text = re.sub(
        r"(?i)(authorization\s*:\s*bearer\s+)[^\s\"']+",
        r"\1<redacted>",
        text,
    )
    text = re.sub(
        r"(?i)\b(token|ticket|api[_-]?key|secret|password)\s*[:=]\s*[^\s,;]+",
        r"\1=<redacted>",
        text,
    )
    text = re.sub(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?:\.[A-Za-z0-9_-]{8,})?\b",
        "<redacted-token>",
        text,
    )
    text = re.sub(
        r"(?<![A-Za-z0-9:])(?:/Users/|/home/|/root/|/tmp/|/private/|/var/tmp/|/docker/|/workspace/)[^\s\"']*",
        "<local-path>",
        text,
    )
    return "\n".join(line.rstrip() for line in text.splitlines() if line.strip())[-MAX_CHILD_DIAGNOSTIC_BYTES:]


def confined_file_name(value: Any, *, label: str, suffix: str) -> str:
    name = str(value or "").strip()
    if (
        SAFE_FILE_NAME_RE.fullmatch(name) is None
        or Path(name).name != name
        or "/" in name
        or "\\" in name
        or not name.lower().endswith(suffix)
    ):
        raise ValueError(f"{label} is not a confined {suffix} filename")
    return name


def confined_download_url(base_url: str, value: Any, *, file_name: str) -> str:
    base = urllib.parse.urlsplit(base_url)
    candidate = urllib.parse.urlsplit(normalize_url(base_url, str(value or "")))
    expected_path = f"/downloads/files/{urllib.parse.quote(file_name, safe='._-')}"
    if (
        candidate.scheme not in {"http", "https"}
        or candidate.scheme.lower() != base.scheme.lower()
        or candidate.hostname != base.hostname
        or candidate.port != base.port
        or candidate.username is not None
        or candidate.password is not None
        or candidate.query
        or candidate.fragment
        or candidate.path != expected_path
    ):
        raise ValueError("download URL must be the same-origin expected files route")
    return urllib.parse.urlunsplit(candidate)


def safe_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return 0
    return parsed if parsed >= 0 else 0


def request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36 chummer-live-public-windows-installer/1",
            "Accept": "application/json,text/plain;q=0.9,*/*;q=0.8",
        },
    )


def is_retryable_fetch_exception(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return False
    if isinstance(exc, RETRYABLE_FETCH_REASONS):
        return True
    if isinstance(exc, urllib.error.URLError):
        return isinstance(exc.reason, RETRYABLE_FETCH_REASONS)
    return False


def fetch_bytes(url: str) -> bytes:
    for attempt in range(DEFAULT_FETCH_ATTEMPTS):
        try:
            with urllib.request.urlopen(request(url), timeout=DEFAULT_FETCH_TIMEOUT_SECONDS) as response:
                return response.read()
        except Exception as exc:
            if attempt + 1 >= DEFAULT_FETCH_ATTEMPTS or not is_retryable_fetch_exception(exc):
                raise
            time.sleep(min(0.5 * (attempt + 1), 1.5))
    raise RuntimeError("fetch_bytes exhausted retry loop unexpectedly")


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
        "sizeBytes": safe_int(row.get("payloadSizeBytes")),
        "installerFileName": str(row.get("fileName") or ""),
        "releaseVersion": str(row.get("releaseVersion") or row.get("version") or ""),
    }


def verify(
    base_url: str,
    verify_script: Path,
    output_path: Path | None = None,
    *,
    expected_verify_script_sha256: str | None = None,
) -> dict[str, Any]:
    output_path = output_path or OUTPUT_PATH
    base = base_url.rstrip("/")
    parsed_base = urllib.parse.urlsplit(base)
    if (
        parsed_base.scheme not in {"http", "https"}
        or not parsed_base.hostname
        or parsed_base.username is not None
        or parsed_base.password is not None
        or parsed_base.query
        or parsed_base.fragment
    ):
        raise ValueError("base URL must be one HTTP(S) origin without credentials, query, or fragment")
    manifest_url = normalize_url(base, "/downloads/releases.json")
    failures: list[str] = []
    checked_artifacts: list[dict[str, Any]] = []
    verifier_bytes = b""
    verifier_sha256 = ""
    verify_script_reference = portable_verify_script_reference(verify_script)

    try:
        verifier_bytes, verifier_sha256, verify_script_reference = authenticate_verifier(
            verify_script,
            expected_verify_script_sha256
            or os.environ.get(
                "CHUMMER_WINDOWS_INSTALLER_PAYLOAD_VERIFY_SCRIPT_EXPECTED_SHA256"
            ),
        )
    except RuntimeError as exc:
        failures.append(str(exc))

    try:
        manifest = fetch_json(manifest_url)
    except Exception as exc:  # pragma: no cover - network failures are environment-driven
        payload = {
            "contract_name": "chummer.live_public_windows_installer",
            "generated_at_utc": now_iso(),
            "base_url": base,
            "manifest_url": manifest_url,
            "verify_script_path": verify_script_reference,
            "verify_script_sha256": verifier_sha256,
            "status": "fail",
            "verdict": "LIVE_PUBLIC_WINDOWS_INSTALLER_NOT_READY",
            "checked_artifacts": [],
            "failures": failures + [
                "could not fetch public downloads manifest: "
                f"{sanitize_child_diagnostic(type(exc).__name__)}"
            ],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return payload

    if not isinstance(manifest, dict):
        failures.append("public downloads manifest must be a JSON object")
        manifest = {}
    downloads = manifest.get("downloads") or []
    if not isinstance(downloads, list):
        downloads = []

    windows_rows = [row for row in downloads if isinstance(row, dict) and is_windows_bootstrap_installer(row)]
    if not windows_rows:
        failures.append("public downloads manifest does not expose any Windows bootstrap installer rows")

    with tempfile.TemporaryDirectory(prefix="chummer-live-public-windows-installer-") as temp_root:
        temp_root_path = Path(temp_root)
        files_dir = temp_root_path / "files"
        files_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = temp_root_path / "releases.json"
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        for row in windows_rows:
            artifact_id = str(row.get("id") or row.get("artifactId") or "unknown").strip()
            if SAFE_FILE_NAME_RE.fullmatch(artifact_id) is None:
                artifact_id = "invalid-artifact"
            installer_file_name = ""
            installer_url = ""
            payload_file_name = ""
            payload_url = ""
            sidecar_url = ""
            expected_installer_sha256 = str(row.get("sha256") or "").lower()
            expected_payload_sha256 = str(row.get("payloadSha256") or "").lower()
            expected_installer_size = safe_int(row.get("sizeBytes"))
            expected_payload_size = safe_int(row.get("payloadSizeBytes"))

            row_failures: list[str] = []
            installer_sha256 = ""
            payload_sha256 = ""
            installer_size = 0
            payload_size = 0

            if SHA256_RE.fullmatch(expected_installer_sha256) is None:
                row_failures.append("installer row is missing a canonical sha256")
            if SHA256_RE.fullmatch(expected_payload_sha256) is None:
                row_failures.append("installer row is missing a canonical payloadSha256")
            if expected_installer_size <= 0:
                row_failures.append("installer row is missing a positive sizeBytes")
            if expected_payload_size <= 0:
                row_failures.append("installer row is missing a positive payloadSizeBytes")

            try:
                installer_file_name = confined_file_name(
                    row.get("fileName"),
                    label="installer fileName",
                    suffix=".exe",
                )
                payload_file_name = confined_file_name(
                    row.get("payloadFileName"),
                    label="payloadFileName",
                    suffix=".zip",
                )
                installer_url = confined_download_url(
                    base,
                    row.get("url"),
                    file_name=installer_file_name,
                )
                payload_url = confined_download_url(
                    base,
                    row.get("payloadDownloadUrl"),
                    file_name=payload_file_name,
                )
                sidecar_url = f"{payload_url}.json"
            except ValueError as exc:
                row_failures.append(str(exc))

            installer_path = files_dir / (installer_file_name or "invalid-installer.exe")
            payload_path = files_dir / (payload_file_name or "invalid-payload.zip")
            sidecar_path = files_dir / f"{payload_file_name or 'invalid-payload.zip'}.json"

            try:
                if not installer_url:
                    raise ValueError("installer URL is unavailable after confinement")
                installer_bytes = fetch_bytes(installer_url)
                installer_path.write_bytes(installer_bytes)
                installer_sha256 = sha256_bytes(installer_bytes)
                installer_size = len(installer_bytes)
                if expected_installer_sha256 and installer_sha256 != expected_installer_sha256:
                    row_failures.append("installer sha256 does not match public manifest")
                if expected_installer_size and installer_size != expected_installer_size:
                    row_failures.append("installer sizeBytes does not match public manifest")
            except Exception as exc:  # pragma: no cover - exercised indirectly in network failure cases
                row_failures.append(
                    "could not fetch installer bytes: "
                    f"{sanitize_child_diagnostic(type(exc).__name__)}"
                )

            try:
                if not payload_url:
                    raise ValueError("payload URL is unavailable after confinement")
                payload_bytes = fetch_bytes(payload_url)
                payload_path.write_bytes(payload_bytes)
                payload_sha256 = sha256_bytes(payload_bytes)
                payload_size = len(payload_bytes)
                if expected_payload_sha256 and payload_sha256 != expected_payload_sha256:
                    row_failures.append("payload sha256 does not match public manifest")
                if expected_payload_size and payload_size != expected_payload_size:
                    row_failures.append("payload sizeBytes does not match public manifest")
            except Exception as exc:  # pragma: no cover - exercised indirectly in network failure cases
                row_failures.append(
                    "could not fetch payload bytes: "
                    f"{sanitize_child_diagnostic(type(exc).__name__)}"
                )

            try:
                if not sidecar_url:
                    raise ValueError("payload sidecar URL is unavailable after confinement")
                sidecar_payload = fetch_json(sidecar_url)
                if not isinstance(sidecar_payload, dict):
                    raise ValueError("payload sidecar must be a JSON object")
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
                if safe_int(sidecar_payload.get("sizeBytes")) != expected_sidecar["sizeBytes"]:
                    row_failures.append("payload sidecar sizeBytes does not match")
                if str(sidecar_payload.get("installerFileName") or "") != expected_sidecar["installerFileName"]:
                    row_failures.append("payload sidecar installerFileName does not match")
                if str(sidecar_payload.get("releaseVersion") or "") != expected_sidecar["releaseVersion"]:
                    row_failures.append("payload sidecar releaseVersion does not match")
            except Exception as exc:  # pragma: no cover - exercised indirectly in network failure cases
                row_failures.append(
                    "could not fetch payload sidecar metadata: "
                    f"{sanitize_child_diagnostic(type(exc).__name__)}"
                )

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

        if windows_rows and verifier_bytes:
            authenticated_verifier = temp_root_path / "authenticated-windows-installer-verifier.py"
            authenticated_verifier.write_bytes(verifier_bytes)
            authenticated_verifier.chmod(0o400)
            result = subprocess.run(
                [
                    sys.executable,
                    str(authenticated_verifier),
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
                stderr = sanitize_child_diagnostic(result.stderr or result.stdout or "")
                failures.append(f"live public Windows installer payload gate failed: {stderr}")

    payload = {
        "contract_name": "chummer.live_public_windows_installer",
        "generated_at_utc": now_iso(),
        "base_url": base,
        "manifest_url": manifest_url,
        "verify_script_path": verify_script_reference,
        "verify_script_sha256": verifier_sha256,
        "status": "pass" if not failures else "fail",
        "verdict": "LIVE_PUBLIC_WINDOWS_INSTALLER_READY" if not failures else "LIVE_PUBLIC_WINDOWS_INSTALLER_NOT_READY",
        "checked_artifact_count": len(checked_artifacts),
        "artifact": checked_artifacts[0] if len(checked_artifacts) == 1 else None,
        "checked_artifacts": checked_artifacts,
        "failures": failures,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify that the public Windows bootstrap installer bytes served from the live downloads shelf match manifest metadata and the native payload gate.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Public base URL to verify.")
    parser.add_argument("--verify-script", type=Path, default=DEFAULT_VERIFY_SCRIPT, help="Path to verify-windows-installer-payloads.py.")
    parser.add_argument(
        "--verify-script-sha256",
        default=os.environ.get(
            "CHUMMER_WINDOWS_INSTALLER_PAYLOAD_VERIFY_SCRIPT_EXPECTED_SHA256",
            "",
        ),
        help="Required SHA256 when --verify-script is outside this repository.",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH, help="Path to write the generated live public Windows installer receipt.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = verify(
        args.base_url,
        args.verify_script,
        args.output,
        expected_verify_script_sha256=args.verify_script_sha256,
    )
    if payload["status"] != "pass":
        raise SystemExit("live public windows installer verification failed")
    print("live_public_windows_installer:ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
