from __future__ import annotations

import hashlib
import json
import os
import subprocess
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify-windows-installer-visual-proof.py"
PUBLISH_SCRIPT = REPO_ROOT / "scripts" / "publish-download-bundle.sh"
MATERIALIZER = REPO_ROOT / "scripts" / "materialize-public-downloads-bundle.sh"


def _minimal_windows_exe() -> bytes:
    data = bytearray(4096)
    data[0:2] = b"MZ"
    data[0x3C:0x40] = (0x80).to_bytes(4, "little")
    data[0x80:0x84] = b"PE\0\0"
    data[0x84:0x86] = (0x8664).to_bytes(2, "little")
    data[0x86:0x88] = (3).to_bytes(2, "little")
    return bytes(data)


WINDOWS_INSTALLER_STUB = _minimal_windows_exe()


def _windows_installer_stub_with_payload_metadata(
    *,
    payload_download_url: str,
    payload_sha256: str,
    payload_size_bytes: int,
) -> bytes:
    return WINDOWS_INSTALLER_STUB + (
        "\n"
        f"ChummerInstallerPayloadUrl={payload_download_url}\n"
        f"ChummerInstallerPayloadSha256={payload_sha256}\n"
        f"ChummerInstallerPayloadSizeBytes={payload_size_bytes}\n"
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
    installer_sha256: str,
    installer_size_bytes: int,
    payload_name: str = "",
    payload_sha256: str = "",
    payload_size_bytes: int = 0,
    payload_download_url: str | None = None,
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
                "head": "avalonia",
                "rid": "win-x64",
                "installerMode": "bootstrap",
                "payloadFileName": payload_name,
                "payloadDownloadUrl": payload_download_url
                or (f"https://example.invalid/downloads/files/{payload_name}" if payload_name else ""),
                "payloadSha256": payload_sha256,
                "payloadSizeBytes": payload_size_bytes,
            }
        ],
    }
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_payload_sidecar(
    sidecar_path: Path,
    *,
    installer_name: str,
    payload_name: str,
    payload_bytes: bytes,
    download_url: str,
) -> None:
    sidecar_path.write_text(
        json.dumps(
            {
                "contractName": "chummer6-ui.windows_bootstrap_payload",
                "fileName": payload_name,
                "downloadUrl": download_url,
                "sha256": hashlib.sha256(payload_bytes).hexdigest(),
                "sizeBytes": len(payload_bytes),
                "installerFileName": installer_name,
                "releaseVersion": "run-test",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _write_visual_proof(
    proof_path: Path,
    *,
    installer_path: Path,
    progress_path: Path,
    completion_path: Path,
) -> None:
    progress_path.write_bytes(b"progress-image")
    completion_path.write_bytes(b"completion-image")
    installer_sha256 = hashlib.sha256(installer_path.read_bytes()).hexdigest()
    progress_sha256 = hashlib.sha256(progress_path.read_bytes()).hexdigest()
    completion_sha256 = hashlib.sha256(completion_path.read_bytes()).hexdigest()
    proof_path.write_text(
        json.dumps(
            {
                "contractName": "chummer6-ui.windows_installer_visual_proof",
                "status": "pass",
                "releaseVersion": "run-test",
                "version": "run-test",
                "headId": "avalonia",
                "platform": "windows",
                "rid": "win-x64",
                "artifactDigest": f"sha256:{installer_sha256}",
                "screenshots": [
                    {
                        "role": "progress",
                        "path": str(progress_path),
                        "imageDigest": f"sha256:{progress_sha256}",
                    },
                    {
                        "role": "completion",
                        "path": str(completion_path),
                        "imageDigest": f"sha256:{completion_sha256}",
                    },
                ],
                "readabilityReview": {"status": "pass"},
                "contrastReview": {"status": "pass"},
                "clippingReview": {"status": "pass"},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_windows_visual_proof_verifier_allows_empty_when_no_installers_are_present(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()

    result = subprocess.run(
        ["python3", str(VERIFY_SCRIPT), "--files-dir", str(files_dir), "--allow-empty"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "windows_installer_visual_proof_gate:ok no_windows_installers" in result.stdout


def test_windows_visual_proof_verifier_fails_when_visual_proof_is_missing(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        installer_sha256=hashlib.sha256(WINDOWS_INSTALLER_STUB).hexdigest(),
        installer_size_bytes=len(WINDOWS_INSTALLER_STUB),
    )

    result = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--files-dir",
            str(files_dir),
            "--manifest",
            str(manifest_path),
            "--visual-proof",
            str(tmp_path / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "windows_installer_visual_proof_gate:fail" in result.stderr
    assert "Windows installer visual proof is missing" in result.stderr


def test_windows_visual_proof_verifier_accepts_matching_visual_proof(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        installer_sha256=hashlib.sha256(WINDOWS_INSTALLER_STUB).hexdigest(),
        installer_size_bytes=len(WINDOWS_INSTALLER_STUB),
    )
    proof_path = tmp_path / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"
    _write_visual_proof(
        proof_path,
        installer_path=installer_path,
        progress_path=tmp_path / "progress.png",
        completion_path=tmp_path / "completion.png",
    )

    result = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--files-dir",
            str(files_dir),
            "--manifest",
            str(manifest_path),
            "--visual-proof",
            str(proof_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "windows_installer_visual_proof_gate:ok checked=1" in result.stdout


def test_windows_visual_proof_verifier_skips_disabled_artifact_ids(tmp_path: Path) -> None:
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    manifest_path = tmp_path / "releases.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        installer_sha256=hashlib.sha256(WINDOWS_INSTALLER_STUB).hexdigest(),
        installer_size_bytes=len(WINDOWS_INSTALLER_STUB),
    )

    result = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--files-dir",
            str(files_dir),
            "--manifest",
            str(manifest_path),
            "--disabled-artifact-id",
            "avalonia-win-x64-installer",
            "--allow-empty",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "windows_installer_visual_proof_gate:ok no_windows_installers" in result.stdout


def test_publish_download_bundle_fails_before_promotion_when_windows_visual_proof_is_missing(tmp_path: Path) -> None:
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
        payload_sha256=payload_sha256,
        payload_size_bytes=len(payload_bytes),
        payload_download_url=payload_url,
    )

    deploy_dir = tmp_path / "deploy"
    result = subprocess.run(
        ["bash", str(PUBLISH_SCRIPT), str(bundle_dir), str(deploy_dir)],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "CHUMMER_WINDOWS_INSTALLER_VISUAL_PROOF_PATH": str(tmp_path / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "windows_installer_visual_proof_gate:fail" in result.stderr
    assert "Windows installer visual proof is missing" in result.stderr


def test_materialize_public_downloads_bundle_fails_before_generation_when_windows_visual_proof_is_missing(tmp_path: Path) -> None:
    output_root = tmp_path / "downloads"
    runservices_files = tmp_path / "runservices-files"
    presentation_files = tmp_path / "presentation-files"
    presentation_startup_smoke = tmp_path / "presentation-startup-smoke"
    runservices_startup_smoke = tmp_path / "runservices-startup-smoke"
    runservices_files.mkdir()
    presentation_files.mkdir()
    presentation_startup_smoke.mkdir()
    runservices_startup_smoke.mkdir()

    installer_path = presentation_files / "chummer-avalonia-win-x64-installer.exe"
    payload_path = presentation_files / "chummer-avalonia-win-x64-payload.zip"
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
        presentation_files / "chummer-avalonia-win-x64-payload.zip.json",
        installer_name=installer_path.name,
        payload_name=payload_path.name,
        payload_bytes=payload_bytes,
        download_url=payload_url,
    )

    manifest_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        installer_sha256=hashlib.sha256(installer_bytes).hexdigest(),
        installer_size_bytes=len(installer_bytes),
        payload_name=payload_path.name,
        payload_sha256=payload_sha256,
        payload_size_bytes=len(payload_bytes),
        payload_download_url=payload_url,
    )

    release_proof_path = tmp_path / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    release_proof_path.write_text("{}\n", encoding="utf-8")
    release_evidence_path = tmp_path / "public-promotion.json"
    release_evidence_path.write_text("{}\n", encoding="utf-8")
    localization_gate_path = tmp_path / "UI_LOCALIZATION_RELEASE_GATE.generated.json"
    localization_gate_path.write_text("{}\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(MATERIALIZER), str(output_root)],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "CHUMMER_RUNSERVICES_SOURCE_FILES_ROOT": str(runservices_files),
            "CHUMMER_PRESENTATION_FILES_ROOT": str(presentation_files),
            "CHUMMER_PRESENTATION_STARTUP_SMOKE_ROOT": str(presentation_startup_smoke),
            "CHUMMER_RUNSERVICES_PORTAL_STARTUP_SMOKE_ROOT": str(runservices_startup_smoke),
            "CHUMMER_PUBLIC_RELEASE_CHANNEL_SOURCE": str(manifest_path),
            "CHUMMER_RUN_LOCAL_RELEASE_PROOF_SOURCE": str(release_proof_path),
            "CHUMMER_PRESENTATION_RELEASE_EVIDENCE_SOURCE": str(release_evidence_path),
            "CHUMMER_UI_LOCALIZATION_RELEASE_GATE_SOURCE": str(localization_gate_path),
            "CHUMMER_WINDOWS_INSTALLER_VISUAL_PROOF_PATH": str(tmp_path / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "windows_installer_visual_proof_gate:fail" in result.stderr
    assert "Windows installer visual proof is missing" in result.stderr


def test_publish_lanes_call_windows_visual_proof_gate() -> None:
    local_publish = (REPO_ROOT / "scripts" / "publish-download-bundle.sh").read_text(encoding="utf-8")
    http_publish = (REPO_ROOT / "scripts" / "publish-download-bundle-http.sh").read_text(encoding="utf-8")
    s3_publish = (REPO_ROOT / "scripts" / "publish-download-bundle-s3.sh").read_text(encoding="utf-8")
    materializer = (REPO_ROOT / "scripts" / "materialize-public-downloads-bundle.sh").read_text(encoding="utf-8")
    verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")

    assert "verify-windows-installer-visual-proof.py" in local_publish
    assert "verify_windows_installer_visual_proof_gate" in local_publish
    assert "verify-windows-installer-visual-proof.py" in http_publish
    assert "verify-windows-installer-visual-proof.py" in s3_publish
    assert "verify-windows-installer-visual-proof.py" in materializer
    assert "test_windows_installer_visual_proof_gate.py" in verify_script
