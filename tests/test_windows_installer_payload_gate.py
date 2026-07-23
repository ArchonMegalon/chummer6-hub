from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import struct
import subprocess
import zipfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify-windows-installer-payloads.py"
PUBLISH_SCRIPT = REPO_ROOT / "scripts" / "publish-download-bundle.sh"
HTTP_PUBLISH_SCRIPT = REPO_ROOT / "scripts" / "publish-download-bundle-http.sh"
APPENDED_PAYLOAD_MAGIC = b"CHUMMER6PAYLOAD1"


def _minimal_windows_exe() -> bytes:
    data = bytearray(4096)
    data[0:2] = b"MZ"
    data[0x3C:0x40] = (0x80).to_bytes(4, "little")
    data[0x80:0x84] = b"PE\0\0"
    data[0x84:0x86] = (0x8664).to_bytes(2, "little")
    data[0x86:0x88] = (3).to_bytes(2, "little")
    return bytes(data)


WINDOWS_INSTALLER_STUB = _minimal_windows_exe()
WINDOWS_PLACEHOLDER_INSTALLER_STUB = b"MZ" + (b"installer-stub" * 200)


def _windows_installer_stub_with_payload_metadata(
    *,
    payload_download_url: str,
    payload_sha256: str,
    payload_size_bytes: int,
) -> bytes:
    return WINDOWS_INSTALLER_STUB + (
        "\n"
        "CHUMMER6_BOOTSTRAP_METADATA\n"
        f"payloadDownloadUrl={payload_download_url}\n"
        f"payloadSha256={payload_sha256}\n"
        f"payloadSizeBytes={payload_size_bytes}\n"
    ).encode("utf-8")


def _write_bootstrap_payload(payload_path: Path, *, launch_executable: str = "Chummer.Avalonia.exe") -> bytes:
    with zipfile.ZipFile(payload_path, "w") as archive:
        archive.writestr(launch_executable, b"placeholder")
        archive.writestr("Samples/Legacy/Soma-Career.chum5", b"sample")
        archive.writestr("runtime/chummer-runtime.pack", b"0" * 8192)
    return payload_path.read_bytes()


def _write_bundle_manifest(
    manifest_path: Path,
    *,
    installer_name: str,
    installer_sha256: str = "installer-sha-placeholder",
    installer_size_bytes: int = 1,
    payload_name: str = "",
    payload_sha256: str = "",
    payload_size_bytes: int = 0,
    installer_mode: str = "bootstrap",
    payload_download_url: str | None = None,
    installer_download_url: str | None = None,
    release_proof: dict | None = None,
) -> None:
    payload = {
        "version": "run-test",
        "channel": "preview",
        "publishedAt": "2026-06-24T00:00:00Z",
        "downloads": [
            {
                "artifactId": "avalonia-win-x64-installer",
                "fileName": installer_name,
                "url": (
                    f"https://example.invalid/downloads/files/{installer_name}"
                    if installer_download_url is None
                    else installer_download_url
                ),
                "sha256": installer_sha256,
                "sizeBytes": installer_size_bytes,
                "kind": "installer",
                "platform": "windows",
                "installerMode": installer_mode,
                "payloadFileName": payload_name,
                "payloadDownloadUrl": payload_download_url
                or (f"https://example.invalid/downloads/files/{payload_name}" if payload_name else ""),
                "payloadSha256": payload_sha256,
                "payloadSizeBytes": payload_size_bytes,
            }
        ],
    }
    if release_proof is not None:
        payload["releaseProof"] = release_proof
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_payload_sidecar(
    sidecar_path: Path,
    *,
    installer_name: str,
    payload_name: str,
    payload_bytes: bytes,
    download_url: str | None = None,
    sha256: str | None = None,
    contract_name: str = "chummer6-ui.windows_bootstrap_payload",
) -> None:
    sidecar_path.write_text(
        json.dumps(
            {
                "contractName": contract_name,
                "fileName": payload_name,
                "downloadUrl": download_url or f"https://example.invalid/downloads/files/{payload_name}",
                "sha256": sha256 or hashlib.sha256(payload_bytes).hexdigest(),
                "sizeBytes": len(payload_bytes),
                "installerFileName": installer_name,
                "releaseVersion": "run-test",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _run_bootstrap_url_case(
    tmp_path: Path,
    *,
    installer_download_url: str,
    manifest_payload_url: str,
    sidecar_download_url: str,
    release_proof: dict | None = None,
    embedded_download_url: str | None = None,
    require_embedded_metadata: bool = False,
    require_manifest_row: bool = False,
    extra_installer_bytes: bytes = b"",
    manifest_row_updates: dict | None = None,
    manifest_row_removals: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    installer_bytes = (
        _windows_installer_stub_with_payload_metadata(
            payload_download_url=embedded_download_url or sidecar_download_url,
            payload_sha256=payload_sha256,
            payload_size_bytes=len(payload_bytes),
        )
        if require_embedded_metadata
        else WINDOWS_INSTALLER_STUB
    )
    installer_bytes += extra_installer_bytes
    installer_path.write_bytes(installer_bytes)
    _write_payload_sidecar(
        files_dir / f"{payload_path.name}.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
        download_url=sidecar_download_url,
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        installer_sha256=hashlib.sha256(installer_bytes).hexdigest(),
        installer_size_bytes=len(installer_bytes),
        payload_name=payload_path.name,
        payload_download_url=manifest_payload_url,
        payload_sha256=payload_sha256,
        payload_size_bytes=len(payload_bytes),
        installer_download_url=installer_download_url,
        release_proof=release_proof,
    )
    if manifest_row_updates or manifest_row_removals:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["downloads"][0].update(manifest_row_updates or {})
        for key in manifest_row_removals:
            manifest["downloads"][0].pop(key, None)
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
    arguments = [
        "python3",
        str(VERIFY_SCRIPT),
        "--files-dir",
        str(files_dir),
        "--manifest",
        str(manifest_path),
    ]
    if require_embedded_metadata:
        arguments.append("--require-embedded-bootstrap-metadata")
    if require_manifest_row:
        arguments.append("--require-manifest-row")
    return subprocess.run(
        arguments,
        text=True,
        capture_output=True,
        check=False,
    )


def _write_bundled_installer_manifests(
    tmp_path: Path,
) -> tuple[Path, list[Path]]:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    payload_path = tmp_path / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    installer_bytes = (
        WINDOWS_INSTALLER_STUB
        + payload_bytes
        + struct.pack("<q", len(payload_bytes))
        + APPENDED_PAYLOAD_MAGIC
    )
    installer_path.write_bytes(installer_bytes)
    manifests = [tmp_path / "releases.json", tmp_path / "canonical.json"]
    for manifest_path in manifests:
        _write_bundle_manifest(
            manifest_path,
            installer_name=installer_path.name,
            installer_sha256=hashlib.sha256(installer_bytes).hexdigest(),
            installer_size_bytes=len(installer_bytes),
            payload_name=payload_path.name,
            payload_download_url=(
                f"https://example.invalid/downloads/files/{payload_path.name}"
            ),
            payload_sha256=hashlib.sha256(payload_bytes).hexdigest(),
            payload_size_bytes=len(payload_bytes),
            installer_mode="bundled",
        )
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["downloads"][0].update(
            {
                "installAccessClass": "open_public",
                "previewPolicy": "preview_policy",
                "signature": {
                    "policy": "preview_policy",
                    "required": False,
                    "status": "unsigned",
                },
                "payloadAcquisitionMode": "embedded",
                "version": "run-test",
                "releaseVersion": "run-test",
                "channel": "preview",
                "channelId": "preview",
            }
        )
        manifest_path.write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
    return files_dir, manifests


def _release_proof_for_windows_installer(
    *, base_url: str = "https://chummer.run"
) -> dict:
    generated_at = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    shipping_locales = ["en-us", "de-de", "fr-fr", "ja-jp", "pt-br", "zh-cn"]
    domain_coverage = {
        "app_chrome": "pass",
        "data_rules_names": "pass",
        "explain_receipts": "pass",
        "generated_artifacts": "pass",
        "install_update_support": "pass",
    }
    return {
        "status": "passed",
        "generatedAt": generated_at,
        "baseUrl": base_url,
        "journeysPassed": [
            "install_claim_restore_continue",
            "build_explain_publish",
            "campaign_session_recover_recap",
            "report_cluster_release_notify",
            "organize_community_and_close_loop",
        ],
        "proofRoutes": [
            "/downloads/install/avalonia-linux-x64-installer",
            "/home/access",
            "/home/work",
            "/account/access",
            "/account/work",
            "/account/support",
            "/contact",
            "/downloads",
            "/downloads/install/avalonia-win-x64-installer",
        ],
        "uiLocalizationReleaseGate": {
            "status": "pass",
            "generatedAt": generated_at,
            "defaultKeyCount": 1,
            "explicitFallbackRuntime": "pass",
            "signoffSmokeRunnerStatus": "pass",
            "shippingLocales": shipping_locales,
            "acceptanceGates": [
                "pseudo_localization",
                "missing_key_fail_fast",
                "top_surface_overflow_checks",
                "locale_smoke_first_launch",
                "locale_smoke_settings",
                "locale_smoke_explain",
                "locale_smoke_updater",
                "locale_smoke_support",
                "non_english_generated_artifact_smoke",
            ],
            "domainCoverage": domain_coverage,
            "localeDomainCoverage": {locale: domain_coverage for locale in shipping_locales},
            "localeSummary": [
                {
                    "locale": locale,
                    "untranslatedKeyCount": 0,
                    "overrideCount": 1,
                    "minimumOverrideCount": 1,
                    "missingReleaseSeedKeys": [],
                    "legacyXmlPresent": True,
                    "legacyDataXmlPresent": True,
                }
                for locale in shipping_locales
            ],
            "blockingFindings": [],
            "blockingFindingsCount": 0,
            "translationBacklogFindings": [],
            "translationBacklogFindingsCount": 0,
        },
    }


def _write_startup_smoke_receipt(startup_smoke_dir: Path, installer_path: Path) -> None:
    startup_smoke_dir.mkdir(parents=True, exist_ok=True)
    generated_at = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    installer_sha256 = hashlib.sha256(installer_path.read_bytes()).hexdigest()
    (startup_smoke_dir / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
        json.dumps(
            {
                "status": "passed",
                "readyCheckpoint": "pre_ui_event_loop",
                "headId": "avalonia",
                "head": "avalonia",
                "platform": "windows",
                "arch": "x64",
                "rid": "win-x64",
                "hostClass": "windows-host",
                "operatingSystem": "Windows 11",
                "artifactPath": str(installer_path),
                "artifactDigest": f"sha256:{installer_sha256}",
                "channelId": "preview",
                "channel": "preview",
                "releaseVersion": "run-test",
                "version": "run-test",
                "recordedAtUtc": generated_at,
                "startedAtUtc": generated_at,
                "completedAtUtc": generated_at,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_windows_installer_verifier_accepts_bootstrap_payload_with_sidecar_metadata(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    _write_payload_sidecar(
        files_dir / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        installer_sha256=hashlib.sha256(WINDOWS_INSTALLER_STUB).hexdigest(),
        installer_size_bytes=len(WINDOWS_INSTALLER_STUB),
        payload_name=payload_path.name,
        payload_sha256=hashlib.sha256(payload_bytes).hexdigest(),
        payload_size_bytes=len(payload_bytes),
    )

    result = subprocess.run(
        ["python3", str(VERIFY_SCRIPT), "--files-dir", str(files_dir), "--manifest", str(manifest_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "windows_installer_payload_gate:ok checked=1" in result.stdout


def test_windows_installer_verifier_rejects_manifest_without_installer_hash_and_size(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    _write_payload_sidecar(
        files_dir / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        installer_sha256="",
        installer_size_bytes=0,
        payload_name=payload_path.name,
        payload_sha256=hashlib.sha256(payload_bytes).hexdigest(),
        payload_size_bytes=len(payload_bytes),
    )

    result = subprocess.run(
        ["python3", str(VERIFY_SCRIPT), "--files-dir", str(files_dir), "--manifest", str(manifest_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "manifest Windows installer row is missing sha256" in result.stderr
    assert "manifest Windows installer row is missing sizeBytes" in result.stderr


def test_windows_installer_verifier_rejects_bootstrap_payload_without_sidecar_metadata(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_sha256=hashlib.sha256(payload_bytes).hexdigest(),
        payload_size_bytes=len(payload_bytes),
    )

    result = subprocess.run(
        ["python3", str(VERIFY_SCRIPT), "--files-dir", str(files_dir), "--manifest", str(manifest_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "bootstrap payload sidecar metadata is missing" in result.stderr


def test_windows_installer_verifier_rejects_placeholder_bootstrap_stub(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_PLACEHOLDER_INSTALLER_STUB)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    _write_payload_sidecar(
        files_dir / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_sha256=hashlib.sha256(payload_bytes).hexdigest(),
        payload_size_bytes=len(payload_bytes),
    )

    result = subprocess.run(
        ["python3", str(VERIFY_SCRIPT), "--files-dir", str(files_dir), "--manifest", str(manifest_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "installer has an invalid Windows PE header offset" in result.stderr
    assert "installer still contains placeholder installer-stub bytes" in result.stderr


def test_windows_installer_verifier_rejects_mismatched_bootstrap_sidecar_metadata(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    _write_payload_sidecar(
        files_dir / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
        sha256="wrong",
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_sha256=hashlib.sha256(payload_bytes).hexdigest(),
        payload_size_bytes=len(payload_bytes),
    )

    result = subprocess.run(
        ["python3", str(VERIFY_SCRIPT), "--files-dir", str(files_dir), "--manifest", str(manifest_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "bootstrap payload sidecar metadata sha256 does not match payload bytes" in result.stderr


def test_windows_installer_verifier_rejects_mismatched_manifest_download_url(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    _write_payload_sidecar(
        files_dir / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
        download_url="https://example.invalid/downloads/files/wrong.zip",
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_sha256=hashlib.sha256(payload_bytes).hexdigest(),
        payload_size_bytes=len(payload_bytes),
    )

    result = subprocess.run(
        ["python3", str(VERIFY_SCRIPT), "--files-dir", str(files_dir), "--manifest", str(manifest_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "bootstrap payload sidecar metadata downloadUrl does not match manifest payloadDownloadUrl" in result.stderr


def test_windows_installer_verifier_rejects_bootstrap_manifest_without_payload_download_metadata(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    _write_payload_sidecar(
        files_dir / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        installer_mode="bootstrap",
    )

    result = subprocess.run(
        ["python3", str(VERIFY_SCRIPT), "--files-dir", str(files_dir), "--manifest", str(manifest_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "manifest installerMode=bootstrap is missing payloadFileName" in result.stderr
    assert "manifest installerMode=bootstrap is missing payloadDownloadUrl" in result.stderr
    assert "manifest installerMode=bootstrap is missing payloadSha256" in result.stderr
    assert "manifest installerMode=bootstrap is missing payloadSizeBytes" in result.stderr


def test_windows_installer_verifier_rejects_bootstrap_installer_without_embedded_payload_metadata(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    payload_url = f"https://example.invalid/downloads/files/{payload_path.name}"
    _write_payload_sidecar(
        files_dir / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
        download_url=payload_url,
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        installer_sha256=hashlib.sha256(WINDOWS_INSTALLER_STUB).hexdigest(),
        installer_size_bytes=len(WINDOWS_INSTALLER_STUB),
        payload_name=payload_path.name,
        payload_download_url=payload_url,
        payload_sha256=payload_sha256,
        payload_size_bytes=len(payload_bytes),
    )

    result = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--files-dir",
            str(files_dir),
            "--manifest",
            str(manifest_path),
            "--require-embedded-bootstrap-metadata",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "bootstrap installer does not contain embedded payloadDownloadUrl metadata" in result.stderr


def test_windows_installer_verifier_rejects_missing_manifest_row_when_required(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    payload_url = f"https://example.invalid/downloads/files/{payload_path.name}"
    installer_path.write_bytes(
        _windows_installer_stub_with_payload_metadata(
            payload_download_url=payload_url,
            payload_sha256=payload_sha256,
            payload_size_bytes=len(payload_bytes),
        )
    )
    _write_payload_sidecar(
        files_dir / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
        download_url=payload_url,
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name="chummer-blazor-desktop-win-x64-installer.exe",
        payload_name=payload_path.name,
        payload_download_url=payload_url,
        payload_sha256=payload_sha256,
        payload_size_bytes=len(payload_bytes),
    )

    result = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--files-dir",
            str(files_dir),
            "--manifest",
            str(manifest_path),
            "--require-manifest-row",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "Windows installer is missing from the supplied release manifest" in result.stderr


def test_windows_installer_verifier_rejects_manifest_payload_url_with_wrong_file_name(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    wrong_url = "https://example.invalid/downloads/files/not-the-payload.zip"
    _write_payload_sidecar(
        files_dir / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
        download_url=wrong_url,
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_download_url=wrong_url,
        payload_sha256=hashlib.sha256(payload_bytes).hexdigest(),
        payload_size_bytes=len(payload_bytes),
    )

    result = subprocess.run(
        ["python3", str(VERIFY_SCRIPT), "--files-dir", str(files_dir), "--manifest", str(manifest_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "manifest payloadDownloadUrl file name not-the-payload.zip does not match payloadFileName chummer-avalonia-win-x64-payload.zip" in result.stderr


def test_windows_installer_verifier_rejects_manifest_payload_sha_that_is_not_hex_digest(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    _write_payload_sidecar(
        files_dir / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
        sha256="not-a-real-sha",
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_sha256="not-a-real-sha",
        payload_size_bytes=len(payload_bytes),
    )

    result = subprocess.run(
        ["python3", str(VERIFY_SCRIPT), "--files-dir", str(files_dir), "--manifest", str(manifest_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "manifest installerMode=bootstrap payloadSha256 is not a 64-character hex digest" in result.stderr


def test_windows_installer_verifier_rejects_manifest_payload_url_that_is_not_https(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    insecure_url = f"http://example.invalid/downloads/files/{payload_path.name}"
    _write_payload_sidecar(
        files_dir / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
        download_url=insecure_url,
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_download_url=insecure_url,
        payload_sha256=hashlib.sha256(payload_bytes).hexdigest(),
        payload_size_bytes=len(payload_bytes),
    )

    result = subprocess.run(
        ["python3", str(VERIFY_SCRIPT), "--files-dir", str(files_dir), "--manifest", str(manifest_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert (
        "manifest installerMode=bootstrap payloadDownloadUrl must be a "
        "lossless canonical absolute HTTPS URL or /downloads/... site path"
    ) in result.stderr


def test_windows_installer_verifier_accepts_canonical_site_manifest_url_with_absolute_sidecar_url(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    relative_url = f"/downloads/files/{payload_path.name}"
    absolute_url = f"https://example.invalid{relative_url}"
    installer_bytes = _windows_installer_stub_with_payload_metadata(
        payload_download_url=absolute_url,
        payload_sha256=payload_sha256,
        payload_size_bytes=len(payload_bytes),
    )
    installer_path.write_bytes(installer_bytes)
    _write_payload_sidecar(
        files_dir / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
        download_url=absolute_url,
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        installer_sha256=hashlib.sha256(installer_bytes).hexdigest(),
        installer_size_bytes=len(installer_bytes),
        payload_name=payload_path.name,
        payload_download_url=relative_url,
        payload_sha256=payload_sha256,
        payload_size_bytes=len(payload_bytes),
    )

    result = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--files-dir",
            str(files_dir),
            "--manifest",
            str(manifest_path),
            "--require-embedded-bootstrap-metadata",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "windows_installer_payload_gate:ok checked=1" in result.stdout


def test_windows_installer_verifier_accepts_release_proof_origin_for_site_relative_urls(
    tmp_path: Path,
) -> None:
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    result = _run_bootstrap_url_case(
        tmp_path,
        installer_download_url=(
            "/downloads/files/chummer-avalonia-win-x64-installer.exe"
        ),
        manifest_payload_url=f"/downloads/files/{payload_name}",
        sidecar_download_url=f"https://example.invalid/downloads/files/{payload_name}",
        release_proof={"baseUrl": "https://example.invalid"},
        require_embedded_metadata=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "windows_installer_payload_gate:ok checked=1" in result.stdout


def test_windows_installer_verifier_accepts_effective_default_https_port_origin(
    tmp_path: Path,
) -> None:
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    result = _run_bootstrap_url_case(
        tmp_path,
        installer_download_url=(
            "https://example.invalid:443/downloads/files/"
            "chummer-avalonia-win-x64-installer.exe"
        ),
        manifest_payload_url=f"/downloads/files/{payload_name}",
        sidecar_download_url=(
            f"https://example.invalid:443/downloads/files/{payload_name}"
        ),
        release_proof={"baseUrl": "https://example.invalid"},
        require_embedded_metadata=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "windows_installer_payload_gate:ok checked=1" in result.stdout


@pytest.mark.parametrize(
    "origin",
    [
        "https://127.0.0.1",
        "https://[2001:db8::1]",
    ],
)
def test_windows_installer_verifier_accepts_canonical_ip_authority(
    tmp_path: Path,
    origin: str,
) -> None:
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    result = _run_bootstrap_url_case(
        tmp_path,
        installer_download_url=(
            "/downloads/files/chummer-avalonia-win-x64-installer.exe"
        ),
        manifest_payload_url=f"/downloads/files/{payload_name}",
        sidecar_download_url=f"{origin}/downloads/files/{payload_name}",
        release_proof={"baseUrl": origin},
        require_embedded_metadata=True,
        require_manifest_row=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "windows_installer_payload_gate:ok checked=1" in result.stdout


def test_windows_installer_verifier_accepts_equal_installer_url_aliases(
    tmp_path: Path,
) -> None:
    installer_url = (
        "https://example.invalid/downloads/files/"
        "chummer-avalonia-win-x64-installer.exe"
    )
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    result = _run_bootstrap_url_case(
        tmp_path,
        installer_download_url=installer_url,
        manifest_payload_url=f"/downloads/files/{payload_name}",
        sidecar_download_url=f"https://example.invalid/downloads/files/{payload_name}",
        manifest_row_updates={"downloadUrl": installer_url},
        require_manifest_row=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("manifest_row_updates", "manifest_row_removals", "alias_failure"),
    [
        ({}, ("url",), None),
        ({"url": ""}, (), None),
        (
            {"url": None},
            (),
            "manifest Windows installer URL alias url must be a string",
        ),
        (
            {"url": 7},
            (),
            "manifest Windows installer URL alias url must be a string",
        ),
    ],
)
def test_windows_installer_verifier_strict_mode_requires_installer_download_url(
    tmp_path: Path,
    manifest_row_updates: dict,
    manifest_row_removals: tuple[str, ...],
    alias_failure: str | None,
) -> None:
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    result = _run_bootstrap_url_case(
        tmp_path,
        installer_download_url=(
            "https://example.invalid/downloads/files/"
            "chummer-avalonia-win-x64-installer.exe"
        ),
        manifest_payload_url=f"/downloads/files/{payload_name}",
        sidecar_download_url=f"https://example.invalid/downloads/files/{payload_name}",
        release_proof={"baseUrl": "https://example.invalid"},
        manifest_row_updates=manifest_row_updates,
        manifest_row_removals=manifest_row_removals,
        require_manifest_row=True,
    )

    assert result.returncode != 0
    assert (
        "Windows installer row requires a nonempty canonical downloadUrl/url"
        in result.stderr
    )
    if alias_failure:
        assert alias_failure in result.stderr


@pytest.mark.parametrize(
    ("manifest_row_updates", "expected_failure"),
    [
        (
            {
                "downloadUrl": (
                    "https://attacker.invalid/downloads/files/"
                    "chummer-avalonia-win-x64-installer.exe"
                )
            },
            "manifest Windows installer URL aliases downloadUrl/url must agree exactly",
        ),
        (
            {"downloadUrl": 7},
            "manifest Windows installer URL alias downloadUrl must be a string",
        ),
        (
            {"name": "chummer-attacker-win-x64-installer.exe"},
            "manifest Windows installer file name aliases fileName/name must agree exactly",
        ),
        (
            {"id": "attacker-win-x64-installer"},
            "manifest Windows installer artifact identity aliases artifactId/id must agree exactly",
        ),
        (
            {"payloadName": "attacker-payload.zip"},
            "manifest Windows payload file name aliases payloadFileName/payloadName must agree exactly",
        ),
    ],
)
def test_windows_installer_verifier_rejects_manifest_alias_disagreement_matrix(
    tmp_path: Path,
    manifest_row_updates: dict,
    expected_failure: str,
) -> None:
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    result = _run_bootstrap_url_case(
        tmp_path,
        installer_download_url=(
            "https://example.invalid/downloads/files/"
            "chummer-avalonia-win-x64-installer.exe"
        ),
        manifest_payload_url=f"/downloads/files/{payload_name}",
        sidecar_download_url=f"https://example.invalid/downloads/files/{payload_name}",
        manifest_row_updates=manifest_row_updates,
        require_manifest_row=True,
    )

    assert result.returncode != 0
    assert expected_failure in result.stderr


def test_windows_installer_verifier_rejects_installer_url_basename_drift(
    tmp_path: Path,
) -> None:
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    result = _run_bootstrap_url_case(
        tmp_path,
        installer_download_url=(
            "https://example.invalid/downloads/files/"
            "chummer-other-win-x64-installer.exe"
        ),
        manifest_payload_url=f"/downloads/files/{payload_name}",
        sidecar_download_url=f"https://example.invalid/downloads/files/{payload_name}",
        require_manifest_row=True,
    )

    assert result.returncode != 0
    assert (
        "manifest Windows installer downloadUrl basename must match fileName exactly"
    ) in result.stderr


def test_windows_installer_verifier_rejects_site_relative_urls_without_trusted_origin(
    tmp_path: Path,
) -> None:
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    result = _run_bootstrap_url_case(
        tmp_path,
        installer_download_url=(
            "/downloads/files/chummer-avalonia-win-x64-installer.exe"
        ),
        manifest_payload_url=f"/downloads/files/{payload_name}",
        sidecar_download_url=f"https://example.invalid/downloads/files/{payload_name}",
    )

    assert result.returncode != 0
    assert "manifest bootstrap URL authority is missing" in result.stderr


def test_windows_installer_verifier_rejects_sidecar_origin_not_manifest_authority(
    tmp_path: Path,
) -> None:
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    result = _run_bootstrap_url_case(
        tmp_path,
        installer_download_url=(
            "/downloads/files/chummer-avalonia-win-x64-installer.exe"
        ),
        manifest_payload_url=f"/downloads/files/{payload_name}",
        sidecar_download_url=f"https://attacker.invalid/downloads/files/{payload_name}",
        release_proof={"baseUrl": "https://example.invalid"},
    )

    assert result.returncode != 0
    assert (
        "bootstrap payload sidecar metadata downloadUrl does not match "
        "manifest payloadDownloadUrl"
    ) in result.stderr


def test_windows_installer_verifier_rejects_absolute_payload_origin_not_installer_authority(
    tmp_path: Path,
) -> None:
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    attacker_url = f"https://attacker.invalid/downloads/files/{payload_name}"
    result = _run_bootstrap_url_case(
        tmp_path,
        installer_download_url=(
            "https://example.invalid/downloads/files/"
            "chummer-avalonia-win-x64-installer.exe"
        ),
        manifest_payload_url=attacker_url,
        sidecar_download_url=attacker_url,
    )

    assert result.returncode != 0
    assert "manifest payloadDownloadUrl must use the trusted manifest origin" in result.stderr


def test_windows_installer_verifier_rejects_disagreeing_manifest_origins(
    tmp_path: Path,
) -> None:
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    result = _run_bootstrap_url_case(
        tmp_path,
        installer_download_url=(
            "https://example.invalid/downloads/files/"
            "chummer-avalonia-win-x64-installer.exe"
        ),
        manifest_payload_url=f"/downloads/files/{payload_name}",
        sidecar_download_url=f"https://example.invalid/downloads/files/{payload_name}",
        release_proof={"baseUrl": "https://other.invalid"},
    )

    assert result.returncode != 0
    assert (
        "manifest installer downloadUrl and releaseProof.baseUrl origins must all agree"
    ) in result.stderr


def test_windows_installer_verifier_rejects_disagreeing_origins_across_manifests(
    tmp_path: Path,
) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    relative_installer_url = f"/downloads/files/{installer_path.name}"
    relative_payload_url = f"/downloads/files/{payload_path.name}"
    _write_payload_sidecar(
        files_dir / f"{payload_path.name}.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
        download_url=f"https://example.invalid{relative_payload_url}",
    )
    manifests = [tmp_path / "canonical.json", tmp_path / "compatibility.json"]
    for manifest, origin in zip(
        manifests,
        ("https://example.invalid", "https://attacker.invalid"),
        strict=True,
    ):
        _write_bundle_manifest(
            manifest,
            installer_name=installer_path.name,
            installer_sha256=hashlib.sha256(WINDOWS_INSTALLER_STUB).hexdigest(),
            installer_size_bytes=len(WINDOWS_INSTALLER_STUB),
            payload_name=payload_path.name,
            payload_download_url=relative_payload_url,
            payload_sha256=payload_sha256,
            payload_size_bytes=len(payload_bytes),
            installer_download_url=relative_installer_url,
            release_proof={"baseUrl": origin},
        )

    result = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--files-dir",
            str(files_dir),
            "--manifest",
            str(manifests[0]),
            "--manifest",
            str(manifests[1]),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert (
        "manifest installer downloadUrl and releaseProof.baseUrl origins must all agree"
    ) in result.stderr


def test_windows_installer_verifier_strict_mode_rejects_empty_manifest_with_attacker_origin(
    tmp_path: Path,
) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    payload_url = f"https://example.invalid/downloads/files/{payload_path.name}"
    _write_payload_sidecar(
        files_dir / f"{payload_path.name}.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
        download_url=payload_url,
    )
    valid_manifest = tmp_path / "releases.json"
    _write_bundle_manifest(
        valid_manifest,
        installer_name=installer_path.name,
        installer_sha256=hashlib.sha256(WINDOWS_INSTALLER_STUB).hexdigest(),
        installer_size_bytes=len(WINDOWS_INSTALLER_STUB),
        payload_name=payload_path.name,
        payload_download_url=payload_url,
        payload_sha256=payload_sha256,
        payload_size_bytes=len(payload_bytes),
    )
    empty_manifest = tmp_path / "canonical.json"
    empty_manifest.write_text(
        json.dumps(
            {
                "releaseProof": {"baseUrl": "https://attacker.invalid"},
                "artifacts": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--files-dir",
            str(files_dir),
            "--manifest",
            str(valid_manifest),
            "--manifest",
            str(empty_manifest),
            "--require-manifest-row",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "canonical.json: must contain exactly one row" in result.stderr
    assert "supplied release manifest URL authority origins must all agree" in result.stderr


def test_windows_installer_verifier_strict_mode_validates_empty_manifest_root(
    tmp_path: Path,
) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    payload_url = f"https://example.invalid/downloads/files/{payload_path.name}"
    _write_payload_sidecar(
        files_dir / f"{payload_path.name}.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
        download_url=payload_url,
    )
    empty_manifest = tmp_path / "canonical.json"
    empty_manifest.write_text(
        json.dumps(
            {
                "releaseProof": {
                    "baseUrl": "https://user@attacker.invalid",
                },
                "artifacts": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--files-dir",
            str(files_dir),
            "--manifest",
            str(empty_manifest),
            "--require-manifest-row",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "canonical.json: must contain exactly one row" in result.stderr
    assert (
        "canonical.json: releaseProof.baseUrl must be one lossless canonical HTTPS origin"
    ) in result.stderr


def test_windows_installer_verifier_strict_mode_rejects_duplicate_row_in_one_manifest(
    tmp_path: Path,
) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    payload_url = f"https://example.invalid/downloads/files/{payload_path.name}"
    _write_payload_sidecar(
        files_dir / f"{payload_path.name}.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
        download_url=payload_url,
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        installer_sha256=hashlib.sha256(WINDOWS_INSTALLER_STUB).hexdigest(),
        installer_size_bytes=len(WINDOWS_INSTALLER_STUB),
        payload_name=payload_path.name,
        payload_download_url=payload_url,
        payload_sha256=hashlib.sha256(payload_bytes).hexdigest(),
        payload_size_bytes=len(payload_bytes),
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["downloads"].append(dict(manifest["downloads"][0]))
    manifest_path.write_text(json.dumps(manifest) + "\n", encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--files-dir",
            str(files_dir),
            "--manifest",
            str(manifest_path),
            "--require-manifest-row",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "must contain exactly one row for every checked Windows installer" in result.stderr


@pytest.mark.parametrize(
    "installer_download_url",
    [
        "//example.invalid/downloads/files/chummer-avalonia-win-x64-installer.exe",
        "downloads/files/chummer-avalonia-win-x64-installer.exe",
        "http://example.invalid/downloads/files/chummer-avalonia-win-x64-installer.exe",
        "https://user@example.invalid/downloads/files/chummer-avalonia-win-x64-installer.exe",
        "https://EXAMPLE.invalid/downloads/files/chummer-avalonia-win-x64-installer.exe",
        "https://example.invalid:444/downloads/files/chummer-avalonia-win-x64-installer.exe",
        "https://example.invalid:99999/downloads/files/chummer-avalonia-win-x64-installer.exe",
        "https://example.invalid/downloads//chummer-avalonia-win-x64-installer.exe",
        "https://example.invalid/downloads/files/%63hummer-avalonia-win-x64-installer.exe",
        "https://example.invalid/downloads/files/chummer-avalonia-win-x64-installer.exe?",
        "https://example.invalid/downloads/files/chummer avalonia-win-x64-installer.exe",
        "https://example.invalid/downloads/files/chummer-avalonia-win-x64-installer.exe\x00",
    ],
)
def test_windows_installer_verifier_rejects_noncanonical_installer_url_matrix(
    tmp_path: Path,
    installer_download_url: str,
) -> None:
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    result = _run_bootstrap_url_case(
        tmp_path,
        installer_download_url=installer_download_url,
        manifest_payload_url=f"/downloads/files/{payload_name}",
        sidecar_download_url=f"https://example.invalid/downloads/files/{payload_name}",
        release_proof={"baseUrl": "https://example.invalid"},
    )

    assert result.returncode != 0
    assert (
        "manifest Windows installer downloadUrl must be a lossless canonical "
        "absolute HTTPS URL or /downloads/... site path"
    ) in result.stderr


@pytest.mark.parametrize(
    "manifest_payload_url",
    [
        "//example.invalid/downloads/files/chummer-avalonia-win-x64-payload.zip",
        "downloads/files/chummer-avalonia-win-x64-payload.zip",
        "https://user@example.invalid/downloads/files/chummer-avalonia-win-x64-payload.zip",
        "https://EXAMPLE.invalid/downloads/files/chummer-avalonia-win-x64-payload.zip",
        "https://example.invalid:444/downloads/files/chummer-avalonia-win-x64-payload.zip",
        "https://example.invalid/downloads/files/chummer-avalonia-win-x64-payload.zip?",
        "/downloads//files/chummer-avalonia-win-x64-payload.zip",
        "/downloads/./files/chummer-avalonia-win-x64-payload.zip",
        "/downloads/files/../chummer-avalonia-win-x64-payload.zip",
        "/downloads/files/%63hummer-avalonia-win-x64-payload.zip",
        "/downloads/files\\chummer-avalonia-win-x64-payload.zip",
        "/downloads/files/chummer-avalonia-win-x64-payload.zip;",
        "/downloads/files/chummer-avalonia-win-x64-payload.zip?",
        "/downloads/files/chummer-avalonia-win-x64-payload.zip#",
        "/downloads/files/chummer avalonia-win-x64-payload.zip",
        "/downloads/files/chummer-avalonia-win-x64-payload.zip\x00",
        "/downloads/files/chummer-avalonia-win-x64-payload.zip\x1f",
        "/downloads/files/",
    ],
)
def test_windows_installer_verifier_rejects_noncanonical_manifest_payload_url_matrix(
    tmp_path: Path,
    manifest_payload_url: str,
) -> None:
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    result = _run_bootstrap_url_case(
        tmp_path,
        installer_download_url=(
            "https://example.invalid/downloads/files/"
            "chummer-avalonia-win-x64-installer.exe"
        ),
        manifest_payload_url=manifest_payload_url,
        sidecar_download_url=f"https://example.invalid/downloads/files/{payload_name}",
    )

    assert result.returncode != 0
    assert (
        "manifest installerMode=bootstrap payloadDownloadUrl must be a "
        "lossless canonical absolute HTTPS URL or /downloads/... site path"
    ) in result.stderr


def test_windows_installer_verifier_requires_embedded_absolute_sidecar_url_exactly(
    tmp_path: Path,
) -> None:
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    sidecar_url = f"https://example.invalid/downloads/files/{payload_name}"
    result = _run_bootstrap_url_case(
        tmp_path,
        installer_download_url=(
            "/downloads/files/chummer-avalonia-win-x64-installer.exe"
        ),
        manifest_payload_url=f"/downloads/files/{payload_name}",
        sidecar_download_url=sidecar_url,
        release_proof={"baseUrl": "https://example.invalid"},
        embedded_download_url=(
            "https://example.invalid/downloads/files/not-the-payload.zip"
        ),
        require_embedded_metadata=True,
    )

    assert result.returncode != 0
    assert (
        "bootstrap installer embedded payloadDownloadUrl metadata does not equal "
        "validated metadata"
    ) in result.stderr


@pytest.mark.parametrize(
    ("label", "extra_installer_bytes", "malformed"),
    [
        (
            "payloadDownloadUrl",
            (
                b"\npayloadDownloadUrl=https://example.invalid/downloads/files/"
                b"chummer-avalonia-win-x64-payload.zip\n"
            ),
            False,
        ),
        (
            "payloadSha256",
            b"\npayloadSha256=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n",
            False,
        ),
        ("payloadSizeBytes", b"\npayloadSizeBytes=123\n", False),
        (
            "payloadDownloadUrl",
            (
                b"XpayloadDownloadUrl=https://attacker.invalid/downloads/files/"
                b"chummer-avalonia-win-x64-payload.zip\n"
            ),
            True,
        ),
        (
            "payloadDownloadUrl",
            (
                b"\npayloadDownloadUrl=https://attacker.invalid/downloads/files/"
                b"chummer-avalonia-win-x64-payload.zip"
            ),
            True,
        ),
    ],
)
def test_windows_installer_verifier_rejects_duplicate_or_malformed_embedded_metadata(
    tmp_path: Path,
    label: str,
    extra_installer_bytes: bytes,
    malformed: bool,
) -> None:
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    result = _run_bootstrap_url_case(
        tmp_path,
        installer_download_url=(
            "/downloads/files/chummer-avalonia-win-x64-installer.exe"
        ),
        manifest_payload_url=f"/downloads/files/{payload_name}",
        sidecar_download_url=f"https://example.invalid/downloads/files/{payload_name}",
        release_proof={"baseUrl": "https://example.invalid"},
        require_embedded_metadata=True,
        require_manifest_row=True,
        extra_installer_bytes=extra_installer_bytes,
    )

    assert result.returncode != 0
    assert (
        f"bootstrap installer must contain exactly one embedded {label} "
        "metadata occurrence"
    ) in result.stderr
    if malformed:
        assert f"embedded {label} metadata is malformed" in result.stderr


@pytest.mark.parametrize(
    "sidecar_download_url",
    [
        "http://example.invalid/downloads/files/chummer-avalonia-win-x64-payload.zip",
        "//example.invalid/downloads/files/chummer-avalonia-win-x64-payload.zip",
        "https://user@example.invalid/downloads/files/chummer-avalonia-win-x64-payload.zip",
        "https://example.invalid:444/downloads/files/chummer-avalonia-win-x64-payload.zip",
        "https://example.invalid:99999/downloads/files/chummer-avalonia-win-x64-payload.zip",
        "https://EXAMPLE.invalid/downloads/files/chummer-avalonia-win-x64-payload.zip",
        "https://example.invalid/downloads/files/%63hummer-avalonia-win-x64-payload.zip",
        "https://example.invalid/downloads/files/chummer-avalonia-win-x64-payload.zip?",
        "https://example.invalid/downloads/files/chummer-avalonia-win-x64-payload.zip#",
        "https://example.invalid/downloads/files/chummer avalonia-win-x64-payload.zip",
        "https://example.invalid/downloads//chummer-avalonia-win-x64-payload.zip",
        "https://example.invalid/downloads/files/chummer-avalonia-win-x64-payload.zip\x00",
    ],
)
def test_windows_installer_verifier_rejects_noncanonical_sidecar_url_matrix(
    tmp_path: Path,
    sidecar_download_url: str,
) -> None:
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    result = _run_bootstrap_url_case(
        tmp_path,
        installer_download_url=(
            "https://example.invalid/downloads/files/"
            "chummer-avalonia-win-x64-installer.exe"
        ),
        manifest_payload_url=f"/downloads/files/{payload_name}",
        sidecar_download_url=sidecar_download_url,
    )

    assert result.returncode != 0
    assert (
        "bootstrap payload sidecar metadata downloadUrl must be a lossless "
        "canonical absolute HTTPS URL"
    ) in result.stderr


@pytest.mark.parametrize(
    "proof_base_url",
    [
        "http://example.invalid",
        "https://user@example.invalid",
        "https://EXAMPLE.invalid",
        "https://-",
        "https://.",
        "https://foo..bar",
        "https://foo.invalid.",
        "https://caf\u00e9.invalid",
        "https://xn--caf-dma.invalid",
        "https://127.1",
        "https://0x7f000001",
        "https://127.000.0.1",
        "https://foo_bar.invalid",
        "https://-foo.invalid",
        "https://foo-.invalid",
        f"https://{'a' * 64}.invalid",
        "https://example.invalid:444",
        "https://example.invalid:99999",
        "https://example.invalid/",
        "https://example.invalid?",
        "https://example.invalid#",
        "https://example.invalid ",
        "https://example.invalid\x00",
    ],
)
def test_windows_installer_verifier_rejects_noncanonical_release_proof_origin_matrix(
    tmp_path: Path,
    proof_base_url: str,
) -> None:
    payload_name = "chummer-avalonia-win-x64-payload.zip"
    result = _run_bootstrap_url_case(
        tmp_path,
        installer_download_url=(
            "/downloads/files/chummer-avalonia-win-x64-installer.exe"
        ),
        manifest_payload_url=f"/downloads/files/{payload_name}",
        sidecar_download_url=f"https://example.invalid/downloads/files/{payload_name}",
        release_proof={"baseUrl": proof_base_url},
    )

    assert result.returncode != 0
    assert (
        "manifest releaseProof.baseUrl must be one lossless canonical HTTPS origin"
    ) in result.stderr


def test_windows_installer_verifier_rejects_relative_sidecar_download_url(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    relative_url = f"/downloads/files/{payload_path.name}"
    _write_payload_sidecar(
        files_dir / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
        download_url=relative_url,
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_download_url=relative_url,
        payload_sha256=hashlib.sha256(payload_bytes).hexdigest(),
        payload_size_bytes=len(payload_bytes),
    )

    result = subprocess.run(
        ["python3", str(VERIFY_SCRIPT), "--files-dir", str(files_dir), "--manifest", str(manifest_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert (
        "bootstrap payload sidecar metadata downloadUrl must be a lossless "
        "canonical absolute HTTPS URL"
    ) in result.stderr


def test_windows_installer_verifier_rejects_noncanonical_site_manifest_url(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    relative_url = f"/downloads/files/../files/{payload_path.name}"
    _write_payload_sidecar(
        files_dir / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_download_url=relative_url,
        payload_sha256=hashlib.sha256(payload_bytes).hexdigest(),
        payload_size_bytes=len(payload_bytes),
    )

    result = subprocess.run(
        ["python3", str(VERIFY_SCRIPT), "--files-dir", str(files_dir), "--manifest", str(manifest_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert (
        "manifest installerMode=bootstrap payloadDownloadUrl must be a "
        "lossless canonical absolute HTTPS URL or /downloads/... site path"
    ) in result.stderr


def test_windows_installer_verifier_rejects_bulk_bootstrap_installer(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    installer_bytes = _windows_installer_stub_with_payload_metadata(
        payload_download_url=f"https://example.invalid/downloads/files/{payload_path.name}",
        payload_sha256=payload_sha256,
        payload_size_bytes=len(payload_bytes),
    ) + (b"\0" * len(payload_bytes))
    installer_path.write_bytes(installer_bytes)
    _write_payload_sidecar(
        files_dir / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        installer_sha256=hashlib.sha256(installer_bytes).hexdigest(),
        installer_size_bytes=len(installer_bytes),
        payload_name=payload_path.name,
        payload_sha256=payload_sha256,
        payload_size_bytes=len(payload_bytes),
    )

    result = subprocess.run(
        ["python3", str(VERIFY_SCRIPT), "--files-dir", str(files_dir), "--manifest", str(manifest_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "manifest installerMode=bootstrap but installer size" in result.stderr
    assert "is not smaller than payloadSizeBytes" in result.stderr


def test_windows_installer_verifier_accepts_cross_manifest_schema_aliases(
    tmp_path: Path,
) -> None:
    files_dir, manifests = _write_bundled_installer_manifests(tmp_path)
    canonical = json.loads(manifests[1].read_text(encoding="utf-8"))
    row = canonical["downloads"][0]
    row["downloadUrl"] = row.pop("url")
    row["id"] = row.pop("artifactId")
    row["name"] = row.pop("fileName")
    row["payloadName"] = row.pop("payloadFileName")
    manifests[1].write_text(
        json.dumps(canonical, indent=2) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--files-dir",
            str(files_dir),
            "--manifest",
            str(manifests[0]),
            "--manifest",
            str(manifests[1]),
            "--require-manifest-row",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("field", "mutated_value"),
    [
        ("artifactId", "other-win-x64-installer"),
        ("sha256", "0" * 64),
        ("sizeBytes", 1),
        ("installAccessClass", "private"),
        ("previewPolicy", "stable_policy"),
        (
            "signature",
            {
                "policy": "stable_policy",
                "required": True,
                "status": "signed",
            },
        ),
        (
            "url",
            "https://attacker.invalid/downloads/files/"
            "chummer-avalonia-win-x64-installer.exe",
        ),
        ("payloadFileName", "other-payload.zip"),
        (
            "payloadDownloadUrl",
            "https://example.invalid/downloads/files/other-payload.zip",
        ),
        ("payloadSha256", "0" * 64),
        ("payloadSizeBytes", 1),
        ("payloadAcquisitionMode", "download"),
        ("installerMode", "bootstrap"),
        ("version", "other-version"),
    ],
)
def test_windows_installer_verifier_rejects_cross_manifest_bundled_identity_drift(
    tmp_path: Path,
    field: str,
    mutated_value: object,
) -> None:
    files_dir, manifests = _write_bundled_installer_manifests(tmp_path)
    compatibility = json.loads(manifests[1].read_text(encoding="utf-8"))
    compatibility["downloads"][0][field] = mutated_value
    manifests[1].write_text(
        json.dumps(compatibility, indent=2) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--files-dir",
            str(files_dir),
            "--manifest",
            str(manifests[0]),
            "--manifest",
            str(manifests[1]),
            "--require-manifest-row",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "normalized Windows installer row disagrees" in result.stderr


def test_windows_installer_verifier_surfaces_bundled_manifest_conflicts_without_strict_mode(
    tmp_path: Path,
) -> None:
    files_dir, manifests = _write_bundled_installer_manifests(tmp_path)
    compatibility = json.loads(manifests[1].read_text(encoding="utf-8"))
    compatibility["downloads"][0]["previewPolicy"] = "stable_policy"
    manifests[1].write_text(
        json.dumps(compatibility, indent=2) + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--files-dir",
            str(files_dir),
            "--manifest",
            str(manifests[0]),
            "--manifest",
            str(manifests[1]),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert (
        "supplied release manifests disagree on the Windows installer row"
        in result.stderr
    )


def test_windows_installer_verifier_accepts_appended_payload(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    payload_zip_path = tmp_path / "payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_zip_path)
    installer_path.write_bytes(
        WINDOWS_INSTALLER_STUB
        + payload_bytes
        + struct.pack("<q", len(payload_bytes))
        + APPENDED_PAYLOAD_MAGIC
    )

    result = subprocess.run(
        ["python3", str(VERIFY_SCRIPT), "--files-dir", str(files_dir)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "windows_installer_payload_gate:ok checked=1" in result.stdout


def test_publish_download_bundle_fails_before_promotion_when_windows_payload_is_missing(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    files_dir = bundle_dir / "files"
    files_dir.mkdir(parents=True)
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    _write_bundle_manifest(bundle_dir / "releases.json", installer_name=installer_path.name)

    deploy_dir = tmp_path / "deploy"
    result = subprocess.run(
        ["bash", str(PUBLISH_SCRIPT), str(bundle_dir), str(deploy_dir)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "windows_installer_payload_gate:fail" in result.stderr
    assert "no appended payload and no bootstrap sidecar" in result.stderr


def test_http_publisher_requires_manifest_bound_embedded_bootstrap_metadata() -> None:
    script = HTTP_PUBLISH_SCRIPT.read_text(encoding="utf-8")
    invocation_start = script.index(
        'python3 "$SCRIPT_DIR/verify-windows-installer-payloads.py"'
    )
    invocation_end = script.index("\n\n", invocation_start)
    invocation = script[invocation_start:invocation_end]

    assert "--manifest \"$MANIFEST_PATH\"" in invocation
    assert "--manifest \"$CANONICAL_MANIFEST_PATH\"" in invocation
    assert "--require-embedded-bootstrap-metadata" in invocation
    assert "--require-manifest-row" in invocation


def test_publish_download_bundle_promotes_windows_bootstrap_payload_sidecar(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    files_dir = bundle_dir / "files"
    files_dir.mkdir(parents=True)
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    payload_sha256 = hashlib.sha256(payload_bytes).hexdigest()
    payload_url = f"https://example.invalid/downloads/files/{payload_path.name}"
    installer_bytes = _windows_installer_stub_with_payload_metadata(
        payload_download_url=payload_url,
        payload_sha256=payload_sha256,
        payload_size_bytes=len(payload_bytes),
    )
    installer_path.write_bytes(installer_bytes)
    _write_payload_sidecar(
        files_dir / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
        download_url=payload_url,
    )
    _write_bundle_manifest(
        bundle_dir / "releases.json",
        installer_name=installer_path.name,
        installer_sha256=hashlib.sha256(installer_bytes).hexdigest(),
        installer_size_bytes=len(installer_bytes),
        payload_name=payload_path.name,
        payload_download_url=payload_url,
        payload_sha256=payload_sha256,
        payload_size_bytes=len(payload_bytes),
        release_proof=_release_proof_for_windows_installer(
            base_url="https://example.invalid"
        ),
    )
    _write_startup_smoke_receipt(bundle_dir / "startup-smoke", installer_path)

    deploy_dir = tmp_path / "deploy"
    result = subprocess.run(
        ["bash", str(PUBLISH_SCRIPT), str(bundle_dir), str(deploy_dir)],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "CHUMMER_PUBLIC_REQUIRED_DESKTOP_PLATFORMS": "windows",
            "CHUMMER_PUBLIC_EDGE_DOWNLOADS_MIRROR_AUTO": "false",
            "CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER": "true",
            "PORTAL_MANIFEST_PATH": str(deploy_dir / "releases.json"),
            "PORTAL_DOWNLOADS_DIR": str(deploy_dir),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert (deploy_dir / "files" / installer_path.name).is_file()
    assert (deploy_dir / "files" / payload_path.name).is_file()
    deployed_sidecar = deploy_dir / "files" / f"{payload_path.name}.json"
    assert deployed_sidecar.is_file()
    sidecar = json.loads(deployed_sidecar.read_text(encoding="utf-8"))
    assert sidecar["fileName"] == payload_path.name
    assert sidecar["installerFileName"] == installer_path.name


def test_windows_installer_verifier_rejects_non_windows_executable(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(b"not-a-windows-exe" * 200)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = _write_bootstrap_payload(payload_path)
    _write_payload_sidecar(
        files_dir / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_sha256=hashlib.sha256(payload_bytes).hexdigest(),
        payload_size_bytes=len(payload_bytes),
    )

    result = subprocess.run(
        ["python3", str(VERIFY_SCRIPT), "--files-dir", str(files_dir), "--manifest", str(manifest_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "installer does not start with Windows MZ executable magic" in result.stderr


def test_windows_installer_verifier_rejects_non_zip_bootstrap_payload(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    payload_path = files_dir / "chummer-avalonia-win-x64-payload.zip"
    payload_bytes = b"not-a-zip-payload"
    payload_path.write_bytes(payload_bytes)
    _write_payload_sidecar(
        files_dir / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
    )
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_sha256=hashlib.sha256(payload_bytes).hexdigest(),
        payload_size_bytes=len(payload_bytes),
    )

    result = subprocess.run(
        ["python3", str(VERIFY_SCRIPT), "--files-dir", str(files_dir), "--manifest", str(manifest_path)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "payload does not start with ZIP local-file header magic" in result.stderr


def test_publish_download_bundle_keeps_desktop_artifact_classification_centralized() -> None:
    script = PUBLISH_SCRIPT.read_text(encoding="utf-8")

    assert "is_desktop_artifact()" in script
    assert "cleanup_desktop_artifacts()" in script
    assert script.count("chummer-avalonia-*|chummer-blazor-desktop-*|chummer-6-*") == 1
    assert script.count('-name "chummer-avalonia-*.exe"') == 0
    assert script.count('-name "chummer-blazor-desktop-*.exe"') == 0
    assert script.count('-name "chummer-6-*.exe"') == 0
