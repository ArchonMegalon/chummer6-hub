from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "verify-windows-installer-visual-proof.py"
PUBLISH_SCRIPT = REPO_ROOT / "scripts" / "publish-download-bundle.sh"
MATERIALIZER = REPO_ROOT / "scripts" / "materialize-public-downloads-bundle.sh"
PRESENTATION_RELEASE_HANDOFF_SCRIPT = Path("/docker/chummercomplete/chummer-presentation/scripts/materialize_release_candidate_handoff.py")


def _isolated_materializer_side_effects(tmp_path: Path) -> dict[str, str]:
    published_root = tmp_path / "authoritative-published"
    receipt_root = tmp_path / "operator-receipts"
    return {
        "CHUMMER_PUBLIC_AUTHORITATIVE_PUBLISHED_ROOT": str(published_root),
        "CHUMMER_PUBLIC_DISABLE_WORKSPACE_MANIFEST_MIRRORS": "true",
        "CHUMMER_WINDOWS_VISUAL_AUDIT_PUBLISHED_PATH": str(
            receipt_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"
        ),
        "CHUMMER_WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST_PATH": str(
            receipt_root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
        ),
        "CHUMMER_WINDOWS_VISUAL_AUDIT_AUTO_IMPORT_PATH": str(
            receipt_root / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
        ),
        "CHUMMER_WINDOWS_VISUAL_AUDIT_OPERATOR_DRAFT_ROOT": str(
            tmp_path / "operator-drafts"
        ),
    }


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


def _write_ui_localization_release_gate(path: Path) -> None:
    generated_at = dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    shipping_locales = ["en-us", "de-de", "fr-fr", "ja-jp", "pt-br", "zh-cn"]
    acceptance_gates = [
        "pseudo_localization",
        "missing_key_fail_fast",
        "top_surface_overflow_checks",
        "locale_smoke_first_launch",
        "locale_smoke_settings",
        "locale_smoke_explain",
        "locale_smoke_updater",
        "locale_smoke_support",
        "non_english_generated_artifact_smoke",
    ]
    domain_coverage = {
        "app_chrome": "pass",
        "data_rules_names": "pass",
        "explain_receipts": "pass",
        "generated_artifacts": "pass",
        "install_update_support": "pass",
    }
    path.write_text(
        json.dumps(
            {
                "status": "pass",
                "generatedAt": generated_at,
                "defaultKeyCount": 1,
                "explicitFallbackRuntime": "pass",
                "signoffSmokeRunnerStatus": "pass",
                "shippingLocales": shipping_locales,
                "acceptanceGates": acceptance_gates,
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
    proof_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path.parent.mkdir(parents=True, exist_ok=True)
    completion_path.parent.mkdir(parents=True, exist_ok=True)
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


def _write_visual_audit(audit_path: Path, *, installer_path: Path) -> dict[str, object]:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    installer_sha256 = hashlib.sha256(installer_path.read_bytes()).hexdigest()
    source_path = audit_path.parent / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
    startup_path = audit_path.parent / "startup-smoke-avalonia-win-x64.receipt.json"
    screenshot_specs = [
        ("install-progress", "1.0"),
        ("install-progress", "1.5"),
        ("completion", "1.0"),
        ("completion", "1.5"),
    ]
    audit_screenshots: list[dict[str, object]] = []
    source_screenshots: list[dict[str, object]] = []
    for surface, dpi_scale in screenshot_specs:
        screenshot_path = audit_path.parent / f"{surface}-dpi-{dpi_scale}.png"
        screenshot_path.write_bytes(f"{surface}-{dpi_scale}".encode("utf-8"))
        screenshot_sha256 = hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
        audit_screenshots.append(
            {
                "path": str(screenshot_path),
                "exists": True,
                "sha256": screenshot_sha256,
                "dpiScale": dpi_scale,
                "surface": surface,
                "canonicalSurface": surface,
                "clippingStatus": "pass",
                "readabilityStatus": "pass",
                "hostClass": "native-windows",
            }
        )
        source_screenshots.append(
            {
                "path": screenshot_path.name,
                "dpiScale": dpi_scale,
                "surface": surface,
                "clippingStatus": "pass",
                "readabilityStatus": "pass",
                "hostClass": "native-windows",
            }
        )

    source_path.write_text(
        json.dumps(
            {
                "contract_name": "chummer.windows_installer_visual_audit.source",
                "status": "pass",
                "platform": "windows",
                "hostClass": "native-windows-Microsoft Windows Server",
                "artifactSha256": installer_sha256,
                "requiredSurfaces": ["install-progress", "completion"],
                "screenshots": source_screenshots,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    startup_path.write_text(
        json.dumps(
            {
                "status": "pass",
                "version": "run-test",
                "releaseVersion": "run-test",
                "channel": "preview",
                "artifactDigest": f"sha256:{installer_sha256}",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    payload: dict[str, object] = {
        "contract_name": "chummer.windows_installer_visual_audit",
        "status": "pass",
        "required_promoted_digest": installer_sha256,
        "actual_artifact_sha256": installer_sha256,
        "manifest_promoted_digest": installer_sha256,
        "source_digest": installer_sha256,
        "source_digest_matches_promoted": True,
        "release": {
            "loadStatus": "loaded",
            "version": "run-test",
            "channel": "preview",
        },
        "artifact": {
            "artifactId": "avalonia-win-x64-installer",
            "fileName": installer_path.name,
            "path": str(installer_path),
            "sha256": installer_sha256,
            "actualSha256": installer_sha256,
            "effectiveSha256": installer_sha256,
        },
        "startupReceipt": {
            "path": str(startup_path),
            "exists": True,
            "loadStatus": "loaded",
            "status": "pass",
            "artifactDigest": f"sha256:{installer_sha256}",
            "artifactDigestMatchesPromoted": True,
        },
        "visualAuditSource": {
            "path": str(source_path),
            "exists": True,
            "loadStatus": "loaded",
            "status": "pass",
            "platform": "windows",
            "hostClass": "native-windows-Microsoft Windows Server",
            "artifactSha256": installer_sha256,
            "artifactDigestMatchesPromoted": True,
            "requiresRecapture": False,
            "screenshotCount": 4,
            "defaultDpiScreenshotCount": 2,
            "scaledDpiScreenshotCount": 2,
            "requiredSurfaces": ["install-progress", "completion"],
        },
        "screenshots": audit_screenshots,
        "failures": [],
        "nextActions": [],
    }
    audit_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


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


def test_windows_visual_proof_verifier_accepts_matching_stronger_visual_audit(tmp_path: Path) -> None:
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
    audit_path = tmp_path / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"
    _write_visual_audit(audit_path, installer_path=installer_path)

    result = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--files-dir",
            str(files_dir),
            "--manifest",
            str(manifest_path),
            "--visual-proof",
            str(tmp_path / "missing-legacy-proof.json"),
            "--visual-audit",
            str(audit_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "windows_installer_visual_proof_gate:ok checked=1 legacy=0 visual_audit=1" in result.stdout


@pytest.mark.parametrize(
    ("case", "expected_failure"),
    [
        ("wrong_digest", "source_digest does not match promoted installer bytes"),
        ("stale_release", "version does not match release channel"),
        ("missing_dpi_surface", "does not contain at least four screenshots"),
        ("non_native_host", "source host is not native Windows"),
        ("missing_screenshot_file", "file is missing"),
        ("failed_readability", "readability review is not passing"),
    ],
)
def test_windows_visual_proof_verifier_rejects_incomplete_or_stale_visual_audit(
    tmp_path: Path,
    case: str,
    expected_failure: str,
) -> None:
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
    audit_path = tmp_path / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"
    payload = _write_visual_audit(audit_path, installer_path=installer_path)
    release = payload["release"]
    source = payload["visualAuditSource"]
    screenshots = payload["screenshots"]
    assert isinstance(release, dict)
    assert isinstance(source, dict)
    assert isinstance(screenshots, list)

    if case == "wrong_digest":
        payload["source_digest"] = "0" * 64
    elif case == "stale_release":
        release["version"] = "run-stale"
    elif case == "missing_dpi_surface":
        screenshots.pop()
    elif case == "non_native_host":
        source["hostClass"] = "container-linux"
    elif case == "missing_screenshot_file":
        first = screenshots[0]
        assert isinstance(first, dict)
        Path(str(first["path"])).unlink()
    elif case == "failed_readability":
        first = screenshots[0]
        assert isinstance(first, dict)
        first["readabilityStatus"] = "fail"
    else:
        raise AssertionError(f"unsupported case: {case}")
    audit_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    result = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--files-dir",
            str(files_dir),
            "--manifest",
            str(manifest_path),
            "--visual-proof",
            str(tmp_path / "missing-legacy-proof.json"),
            "--visual-audit",
            str(audit_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "windows_installer_visual_proof_gate:fail" in result.stderr
    assert expected_failure in result.stderr


def test_windows_visual_proof_verifier_auto_discovers_release_aligned_proof_when_hint_is_stale(tmp_path: Path) -> None:
    downloads_dir = tmp_path / "downloads"
    files_dir = downloads_dir / "files"
    files_dir.mkdir(parents=True)
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    manifest_path = downloads_dir / "RELEASE_CHANNEL.generated.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        installer_sha256=hashlib.sha256(WINDOWS_INSTALLER_STUB).hexdigest(),
        installer_size_bytes=len(WINDOWS_INSTALLER_STUB),
    )

    release_aligned_proof_path = downloads_dir / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"
    _write_visual_proof(
        release_aligned_proof_path,
        installer_path=installer_path,
        progress_path=downloads_dir / "windows-installer-visual-proof" / "progress.png",
        completion_path=downloads_dir / "windows-installer-visual-proof" / "completion.png",
    )

    stale_hint_path = tmp_path / "published" / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"
    stale_installer_path = tmp_path / "stale" / "chummer-avalonia-win-x64-installer.exe"
    stale_installer_path.parent.mkdir(parents=True, exist_ok=True)
    stale_installer_path.write_bytes(WINDOWS_INSTALLER_STUB + b"-stale")
    _write_visual_proof(
        stale_hint_path,
        installer_path=stale_installer_path,
        progress_path=tmp_path / "stale" / "progress.png",
        completion_path=tmp_path / "stale" / "completion.png",
    )

    result = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--files-dir",
            str(files_dir),
            "--manifest",
            str(manifest_path),
        ],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "CHUMMER_WINDOWS_INSTALLER_VISUAL_PROOF_PATH": str(stale_hint_path),
            "CHUMMER_WINDOWS_VISUAL_AUDIT_PUBLISHED_PATH": str(
                tmp_path / "missing-visual-audit.json"
            ),
        },
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "windows_installer_visual_proof_gate:ok checked=1" in result.stdout


def test_windows_visual_proof_verifier_ignores_stale_hint_when_current_release_proof_is_missing(tmp_path: Path) -> None:
    downloads_dir = tmp_path / "downloads"
    files_dir = downloads_dir / "files"
    files_dir.mkdir(parents=True)
    installer_path = files_dir / "chummer-avalonia-win-x64-installer.exe"
    installer_path.write_bytes(WINDOWS_INSTALLER_STUB)
    manifest_path = downloads_dir / "RELEASE_CHANNEL.generated.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_path.name,
        installer_sha256=hashlib.sha256(WINDOWS_INSTALLER_STUB).hexdigest(),
        installer_size_bytes=len(WINDOWS_INSTALLER_STUB),
    )

    stale_hint_path = tmp_path / "published" / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"
    stale_installer_path = tmp_path / "stale" / "chummer-avalonia-win-x64-installer.exe"
    stale_installer_path.parent.mkdir(parents=True, exist_ok=True)
    stale_installer_path.write_bytes(WINDOWS_INSTALLER_STUB + b"-stale")
    _write_visual_proof(
        stale_hint_path,
        installer_path=stale_installer_path,
        progress_path=tmp_path / "stale" / "progress.png",
        completion_path=tmp_path / "stale" / "completion.png",
    )

    result = subprocess.run(
        [
            "python3",
            str(VERIFY_SCRIPT),
            "--files-dir",
            str(files_dir),
            "--manifest",
            str(manifest_path),
        ],
        text=True,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "CHUMMER_WINDOWS_INSTALLER_VISUAL_PROOF_PATH": str(stale_hint_path),
            "CHUMMER_WINDOWS_VISUAL_AUDIT_PUBLISHED_PATH": str(
                tmp_path / "missing-visual-audit.json"
            ),
        },
    )

    assert result.returncode != 0
    assert "windows_installer_visual_proof_gate:fail" in result.stderr
    assert "Windows installer visual proof is missing" in result.stderr
    assert "version does not match release channel" not in result.stderr
    assert "artifactDigest does not match promoted installer bytes" not in result.stderr


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
    release_proof_path.write_text(
        json.dumps(_release_proof_for_windows_installer(), indent=2) + "\n",
        encoding="utf-8",
    )
    release_evidence_path = tmp_path / "public-promotion.json"
    release_evidence_path.write_text("{}\n", encoding="utf-8")
    localization_gate_path = tmp_path / "UI_LOCALIZATION_RELEASE_GATE.generated.json"
    _write_ui_localization_release_gate(localization_gate_path)

    result = subprocess.run(
        ["bash", str(MATERIALIZER), str(output_root)],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            **_isolated_materializer_side_effects(tmp_path),
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


def test_materialize_public_downloads_bundle_refreshes_stage_handoff_before_visual_proof_failure_returns(tmp_path: Path) -> None:
    assert PRESENTATION_RELEASE_HANDOFF_SCRIPT.is_file()

    output_root = tmp_path / "downloads"
    runservices_files = tmp_path / "runservices-files"
    presentation_files = tmp_path / "presentation-files"
    presentation_startup_smoke = tmp_path / "presentation-startup-smoke"
    runservices_startup_smoke = tmp_path / "runservices-startup-smoke"
    runservices_files.mkdir()
    presentation_files.mkdir()
    presentation_startup_smoke.mkdir()
    runservices_startup_smoke.mkdir()
    authoritative_root = tmp_path / "authoritative-published"
    authoritative_root.mkdir()
    authoritative_manifest = authoritative_root / "RELEASE_CHANNEL.generated.json"
    authoritative_manifest.write_text('{"version":"still-live"}\n', encoding="utf-8")

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

    (presentation_startup_smoke / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "headId": "avalonia",
                "platform": "windows",
                "rid": "win-x64",
                "readyCheckpoint": "pre_ui_event_loop",
                "hostClass": "local-win-x64",
                "artifactDigest": f"sha256:{hashlib.sha256(installer_bytes).hexdigest()}",
                "artifactFileName": installer_path.name,
                "version": "run-test",
                "releaseVersion": "run-test",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    release_proof_path = tmp_path / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    release_proof_path.write_text(
        json.dumps(_release_proof_for_windows_installer(), indent=2) + "\n",
        encoding="utf-8",
    )
    release_evidence_path = output_root / "release-evidence" / "public-promotion.json"
    release_evidence_path.parent.mkdir(parents=True, exist_ok=True)
    release_evidence_path.write_text("{}\n", encoding="utf-8")
    localization_gate_path = tmp_path / "UI_LOCALIZATION_RELEASE_GATE.generated.json"
    _write_ui_localization_release_gate(localization_gate_path)

    gate_stub = tmp_path / "gate-stub.sh"
    gate_stub.write_text(
        "\n".join(
            [
                "#!/usr/bin/env bash",
                "set -euo pipefail",
                'cat > "$CHUMMER_UI_WINDOWS_DESKTOP_EXIT_GATE_PATH" <<EOF',
                "{",
                '  "status": "failed",',
                '  "summary": "Windows desktop exit gate failed: Windows installer visual proof is missing; capture progress and completion screenshots on a Windows host.",',
                '  "blockingMode": "external_only",',
                '  "reasons": ["Windows installer visual proof is missing; capture progress and completion screenshots on a Windows host."]',
                "}",
                "EOF",
                "exit 1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    gate_stub.chmod(0o755)

    result = subprocess.run(
        ["bash", str(MATERIALIZER), str(output_root)],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            **_isolated_materializer_side_effects(tmp_path),
            "CHUMMER_RUNSERVICES_SOURCE_FILES_ROOT": str(runservices_files),
            "CHUMMER_PRESENTATION_FILES_ROOT": str(presentation_files),
            "CHUMMER_PRESENTATION_STARTUP_SMOKE_ROOT": str(presentation_startup_smoke),
            "CHUMMER_RUNSERVICES_PORTAL_STARTUP_SMOKE_ROOT": str(runservices_startup_smoke),
            "CHUMMER_PUBLIC_RELEASE_CHANNEL_SOURCE": str(manifest_path),
            "CHUMMER_RUN_LOCAL_RELEASE_PROOF_SOURCE": str(release_proof_path),
            "CHUMMER_PRESENTATION_RELEASE_EVIDENCE_SOURCE": str(release_evidence_path),
            "CHUMMER_UI_LOCALIZATION_RELEASE_GATE_SOURCE": str(localization_gate_path),
            "CHUMMER_WINDOWS_INSTALLER_VISUAL_PROOF_PATH": str(tmp_path / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"),
            "CHUMMER_PUBLIC_RELEASE_BUILD_HANDOFF_SCRIPT_PATH": str(PRESENTATION_RELEASE_HANDOFF_SCRIPT),
            "CHUMMER_WINDOWS_EXIT_GATE_SCRIPT_PATH": str(gate_stub),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "windows_installer_visual_proof_gate:fail" in result.stderr
    assert "Windows installer visual proof is missing" in result.stderr

    handoff_path = output_root / "RELEASE_BUILD_HANDOFF.generated.json"
    windows_gate_path = output_root / "UI_WINDOWS_DESKTOP_EXIT_GATE.generated.json"
    visual_handoff_path = output_root / "WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json"

    assert handoff_path.is_file()
    assert windows_gate_path.is_file()
    assert visual_handoff_path.is_file()

    handoff_payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert handoff_payload["windows_exit_gate_refresh"]["status"] == "failed"
    assert handoff_payload["windows_exit_gate_refresh"]["blocking_mode"] == "external_only"
    assert handoff_payload["windows_visual_proof_handoff"]["status"] == "ready_for_windows_host"
    assert handoff_payload["windows_visual_proof_handoff"]["visual_proof_path"] == str(
        output_root / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"
    )
    assert authoritative_manifest.read_text(encoding="utf-8") == '{"version":"still-live"}\n'
    assert not (authoritative_root / "releases.json").exists()
    assert not (authoritative_root / "startup-smoke").exists()


def test_materialize_public_downloads_bundle_replaces_stale_duplicate_artifacts_with_manifest_matching_bytes(tmp_path: Path) -> None:
    output_root = tmp_path / "downloads"
    runservices_files = tmp_path / "runservices-files"
    presentation_files = tmp_path / "presentation-files"
    presentation_startup_smoke = tmp_path / "presentation-startup-smoke"
    runservices_startup_smoke = tmp_path / "runservices-startup-smoke"
    runservices_files.mkdir()
    presentation_files.mkdir()
    presentation_startup_smoke.mkdir()
    runservices_startup_smoke.mkdir()

    installer_name = "chummer-avalonia-win-x64-installer.exe"
    payload_name = "chummer-avalonia-win-x64-payload.zip"

    correct_payload_path = presentation_files / payload_name
    correct_payload_bytes = _write_bootstrap_payload(correct_payload_path)
    correct_payload_sha256 = hashlib.sha256(correct_payload_bytes).hexdigest()
    correct_payload_url = f"https://example.invalid/downloads/files/{payload_name}"
    correct_installer_bytes = _windows_installer_stub_with_payload_metadata(
        payload_download_url=correct_payload_url,
        payload_sha256=correct_payload_sha256,
        payload_size_bytes=len(correct_payload_bytes),
    )
    correct_installer_path = presentation_files / installer_name
    correct_installer_path.write_bytes(correct_installer_bytes)
    _write_payload_sidecar(
        presentation_files / f"{payload_name}.json",
        installer_name=installer_name,
        payload_name=payload_name,
        payload_bytes=correct_payload_bytes,
        download_url=correct_payload_url,
    )

    stale_payload_path = runservices_files / payload_name
    stale_payload_bytes = _write_bootstrap_payload(stale_payload_path, launch_executable="Stale.exe")
    stale_payload_sha256 = hashlib.sha256(stale_payload_bytes).hexdigest()
    stale_payload_url = correct_payload_url
    stale_installer_bytes = _windows_installer_stub_with_payload_metadata(
        payload_download_url=stale_payload_url,
        payload_sha256=stale_payload_sha256,
        payload_size_bytes=len(stale_payload_bytes),
    )
    stale_installer_path = runservices_files / installer_name
    stale_installer_path.write_bytes(stale_installer_bytes)
    _write_payload_sidecar(
        runservices_files / f"{payload_name}.json",
        installer_name=installer_name,
        payload_name=payload_name,
        payload_bytes=stale_payload_bytes,
        download_url=stale_payload_url,
    )

    manifest_path = tmp_path / "RELEASE_CHANNEL.generated.json"
    _write_bundle_manifest(
        manifest_path,
        installer_name=installer_name,
        installer_sha256=hashlib.sha256(correct_installer_bytes).hexdigest(),
        installer_size_bytes=len(correct_installer_bytes),
        payload_name=payload_name,
        payload_sha256=correct_payload_sha256,
        payload_size_bytes=len(correct_payload_bytes),
        payload_download_url=correct_payload_url,
    )

    proof_path = tmp_path / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"
    _write_visual_proof(
        proof_path,
        installer_path=correct_installer_path,
        progress_path=tmp_path / "progress.png",
        completion_path=tmp_path / "completion.png",
    )

    release_proof_path = REPO_ROOT / ".codex-studio" / "published" / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    release_evidence_path = REPO_ROOT / "Chummer.Portal" / "downloads" / "release-evidence" / "public-promotion.json"
    localization_gate_path = tmp_path / "UI_LOCALIZATION_RELEASE_GATE.generated.json"
    _write_ui_localization_release_gate(localization_gate_path)

    result = subprocess.run(
        ["bash", str(MATERIALIZER), str(output_root)],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            **_isolated_materializer_side_effects(tmp_path),
            "CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER": "true",
            "CHUMMER_RUNSERVICES_SOURCE_FILES_ROOT": str(runservices_files),
            "CHUMMER_PRESENTATION_FILES_ROOT": str(presentation_files),
            "CHUMMER_PRESENTATION_STARTUP_SMOKE_ROOT": str(presentation_startup_smoke),
            "CHUMMER_RUNSERVICES_PORTAL_STARTUP_SMOKE_ROOT": str(runservices_startup_smoke),
            "CHUMMER_PUBLIC_RELEASE_CHANNEL_SOURCE": str(manifest_path),
            "CHUMMER_RUN_LOCAL_RELEASE_PROOF_SOURCE": str(release_proof_path),
            "CHUMMER_PRESENTATION_RELEASE_EVIDENCE_SOURCE": str(release_evidence_path),
            "CHUMMER_UI_LOCALIZATION_RELEASE_GATE_SOURCE": str(localization_gate_path),
            "CHUMMER_WINDOWS_INSTALLER_VISUAL_PROOF_PATH": str(proof_path),
        },
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr

    produced_installer = output_root / "files" / installer_name
    produced_payload = output_root / "files" / payload_name
    produced_sidecar = output_root / "files" / f"{payload_name}.json"

    assert produced_installer.is_file()
    assert produced_payload.is_file()
    assert produced_sidecar.is_file()
    assert hashlib.sha256(produced_installer.read_bytes()).hexdigest() == hashlib.sha256(correct_installer_bytes).hexdigest()
    assert hashlib.sha256(produced_payload.read_bytes()).hexdigest() == correct_payload_sha256
    produced_sidecar_payload = json.loads(produced_sidecar.read_text(encoding="utf-8"))
    assert produced_sidecar_payload["sha256"] == correct_payload_sha256
    assert produced_sidecar_payload["sizeBytes"] == len(correct_payload_bytes)


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
    assert '--visual-audit "$WINDOWS_VISUAL_AUDIT_PUBLISHED_PATH"' in materializer
    assert "test_windows_installer_visual_proof_gate.py" in verify_script
