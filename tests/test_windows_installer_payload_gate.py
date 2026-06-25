from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import struct
import subprocess
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify-windows-installer-payloads.py"
PUBLISH_SCRIPT = REPO_ROOT / "scripts" / "publish-download-bundle.sh"
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


def _write_bootstrap_payload(payload_path: Path, *, launch_executable: str = "Chummer.Avalonia.exe") -> bytes:
    with zipfile.ZipFile(payload_path, "w") as archive:
        archive.writestr(launch_executable, b"placeholder")
        archive.writestr("Samples/Legacy/Soma-Career.chum5", b"sample")
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
                "url": f"https://example.invalid/downloads/files/{installer_name}",
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


def _release_proof_for_windows_installer() -> dict:
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
        "baseUrl": "https://chummer.run",
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
    assert "manifest installerMode=bootstrap payloadDownloadUrl must be an absolute HTTPS URL" in result.stderr


def test_windows_installer_verifier_rejects_manifest_payload_url_that_is_relative(tmp_path: Path) -> None:
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
    assert "manifest installerMode=bootstrap payloadDownloadUrl must be an absolute HTTPS URL" in result.stderr


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


def test_publish_download_bundle_promotes_windows_bootstrap_payload_sidecar(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    files_dir = bundle_dir / "files"
    files_dir.mkdir(parents=True)
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
    _write_bundle_manifest(
        bundle_dir / "releases.json",
        installer_name=installer_path.name,
        installer_sha256=hashlib.sha256(WINDOWS_INSTALLER_STUB).hexdigest(),
        installer_size_bytes=len(WINDOWS_INSTALLER_STUB),
        payload_name=payload_path.name,
        payload_sha256=hashlib.sha256(payload_bytes).hexdigest(),
        payload_size_bytes=len(payload_bytes),
        release_proof=_release_proof_for_windows_installer(),
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
