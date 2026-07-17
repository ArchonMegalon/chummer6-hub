from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER = REPO_ROOT / "scripts" / "materialize-public-downloads-bundle.sh"
AUR_MATERIALIZER = REPO_ROOT / "scripts" / "materialize-aur-package.py"
RUN_API_LOCALIZATION_GATE_MIRROR = (
    REPO_ROOT
    / "Chummer.Run.Api"
    / "wwwroot"
    / "proofs"
    / "mac-codex-release"
    / "UI_LOCALIZATION_RELEASE_GATE.generated.json"
)

FIXTURE_RELEASE_VERSION = "run-20260716-000000"
FIXTURE_PUBLIC_VERSION = "0.0.0.1"
FIXTURE_PROOF_JOURNEYS = (
    "install_claim_restore_continue",
    "build_explain_publish",
    "campaign_session_recover_recap",
    "report_cluster_release_notify",
    "organize_community_and_close_loop",
)
FIXTURE_PROOF_ROUTES = (
    "/downloads/install/avalonia-linux-x64-installer",
    "/home/access",
    "/home/work",
    "/account/access",
    "/account/work",
    "/account/support",
    "/contact",
    "/downloads",
    "/downloads/install/avalonia-osx-arm64-installer",
    "/downloads/install/avalonia-win-x64-installer",
)
FIXTURE_LOCALIZATION_GATES = (
    "pseudo_localization",
    "missing_key_fail_fast",
    "top_surface_overflow_checks",
    "locale_smoke_first_launch",
    "locale_smoke_settings",
    "locale_smoke_explain",
    "locale_smoke_updater",
    "locale_smoke_support",
    "non_english_generated_artifact_smoke",
)
FIXTURE_SHIPPING_LOCALES = ("en-us", "de-de", "fr-fr", "ja-jp", "pt-br", "zh-cn")
FIXTURE_LOCALIZATION_DOMAINS = (
    "app_chrome",
    "install_update_support",
    "explain_receipts",
    "data_rules_names",
    "generated_artifacts",
)


@dataclass(frozen=True)
class PublicDownloadsFixture:
    root: Path
    files_root: Path
    startup_smoke_root: Path
    manifest_path: Path
    release_proof_path: Path
    localization_gate_path: Path
    promotion_evidence_path: Path
    authoritative_root: Path
    registry_files_root: Path
    windows_visual_proof_path: Path
    linux_row: dict[str, object]
    windows_row: dict[str, object]
    macos_row: dict[str, object]


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def fixture_timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def localization_gate_fixture(generated_at: str) -> dict[str, object]:
    return {
        "status": "passed",
        "generatedAt": generated_at,
        "defaultKeyCount": 100,
        "explicitFallbackRuntime": "passed",
        "signoffSmokeRunnerStatus": "passed",
        "shippingLocales": list(FIXTURE_SHIPPING_LOCALES),
        "acceptanceGates": list(FIXTURE_LOCALIZATION_GATES),
        "domainCoverage": {domain: "passed" for domain in FIXTURE_LOCALIZATION_DOMAINS},
        "localeDomainCoverage": {
            locale: {domain: "passed" for domain in FIXTURE_LOCALIZATION_DOMAINS}
            for locale in FIXTURE_SHIPPING_LOCALES
        },
        "blockingFindings": [],
        "blockingFindingsCount": 0,
        "translationBacklogFindings": [],
        "translationBacklogFindingsCount": 0,
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
            for locale in FIXTURE_SHIPPING_LOCALES
        ],
    }


def write_passing_windows_visual_proof_fixture(root: Path, windows_row: dict[str, object]) -> Path:
    proof_root = root / "windows-visual-proof"
    proof_root.mkdir(parents=True, exist_ok=True)
    progress_path = proof_root / "windows-installer-progress.png"
    completion_path = proof_root / "windows-installer-completion.png"
    progress_path.write_bytes(b"progress-screenshot")
    completion_path.write_bytes(b"completion-screenshot")
    proof_path = root / "WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"
    proof_payload = {
        "contractName": "chummer6-ui.windows_installer_visual_proof",
        "status": "pass",
        "headId": windows_row["head"],
        "rid": windows_row["rid"],
        "releaseVersion": windows_row["version"],
        "artifactDigest": f"sha256:{windows_row['sha256']}",
        "screenshots": [
            {
                "role": "progress",
                "path": str(progress_path),
                "imageDigest": f"sha256:{sha256_file(progress_path)}",
            },
            {
                "role": "completion",
                "path": str(completion_path),
                "imageDigest": f"sha256:{sha256_file(completion_path)}",
            },
        ],
        "readabilityReview": {"status": "pass"},
        "contrastReview": {"status": "pass"},
        "clippingReview": {"status": "pass"},
    }
    proof_path.write_text(json.dumps(proof_payload, indent=2), encoding="utf-8")
    return proof_path


def write_startup_smoke_fixture(
    startup_root: Path,
    artifact_path: Path,
    artifact: dict[str, object],
    generated_at: str,
) -> None:
    startup_root.mkdir(parents=True, exist_ok=True)
    rid = str(artifact["rid"])
    platform = str(artifact["platform"])
    operating_system = {
        "linux": "Ubuntu Linux 24.04",
        "windows": "Windows 11",
        "macos": "macOS 15",
    }[platform]
    receipt: dict[str, object] = {
        "status": "pass",
        "readyCheckpoint": "pre_ui_event_loop",
        "recordedAtUtc": generated_at,
        "completedAtUtc": generated_at,
        "headId": artifact["head"],
        "platform": platform,
        "arch": artifact["arch"],
        "rid": rid,
        "hostClass": f"{platform}-host",
        "operatingSystem": operating_system,
        "channelId": "preview",
        "channel": "preview",
        "releaseVersion": FIXTURE_RELEASE_VERSION,
        "artifactDigest": f"sha256:{artifact['sha256']}",
        "artifactSha256": artifact["sha256"],
        "artifactId": artifact["artifactId"],
        "artifactFileName": artifact["fileName"],
        "artifactPath": str(artifact_path),
    }

    if platform == "windows":
        receipt.update(
            {
                "artifactInstallMode": "nsis_bootstrap_installer",
                "bootstrapPayloadAcquisitionMode": "download",
                "bootstrapPayloadFileName": artifact["payloadFileName"],
                "bootstrapPayloadSha256": artifact["payloadSha256"],
                "bootstrapPayloadSizeBytes": artifact["payloadSizeBytes"],
            }
        )

    if platform == "linux":
        dpkg_log_path = startup_root / "dpkg-avalonia-linux-x64.log"
        launch_capture_path = startup_root / "installed-launch-avalonia-linux-x64.bin"
        wrapper_capture_path = startup_root / "wrapper-avalonia-linux-x64.txt"
        desktop_entry_path = startup_root / "desktop-entry-avalonia-linux-x64.desktop"
        verification_path = startup_root / "install-verification-avalonia-linux-x64.json"
        dpkg_log_path.write_text("synthetic dpkg verification passed\n", encoding="utf-8")
        launch_capture_path.write_bytes(b"synthetic-linux-launch-capture")
        wrapper_capture_path.write_text("/usr/bin/chummer6\n", encoding="utf-8")
        desktop_entry_path.write_text("[Desktop Entry]\nExec=chummer6\n", encoding="utf-8")
        write_json(
            verification_path,
            {
                "status": "pass",
                "artifactSha256": artifact["sha256"],
                "dpkgLogPath": str(dpkg_log_path),
                "installedLaunchCapturePath": str(launch_capture_path),
                "wrapperCapturePath": str(wrapper_capture_path),
                "desktopEntryCapturePath": str(desktop_entry_path),
            },
        )
        receipt.update(
            {
                "artifactInstallVerificationPath": str(verification_path),
                "artifactInstallDpkgLogPath": str(dpkg_log_path),
                "artifactInstallLaunchCapturePath": str(launch_capture_path),
                "artifactInstallWrapperCapturePath": str(wrapper_capture_path),
                "artifactInstallDesktopEntryCapturePath": str(desktop_entry_path),
            }
        )

    write_json(startup_root / f"startup-smoke-avalonia-{rid}.receipt.json", receipt)


def write_public_downloads_fixture(root: Path) -> PublicDownloadsFixture:
    fixture_root = root / "public-downloads-fixture"
    files_root = fixture_root / "files"
    startup_smoke_root = fixture_root / "startup-smoke"
    authoritative_root = fixture_root / "authoritative-published"
    registry_files_root = fixture_root / "registry-published-files"
    for path in (files_root, startup_smoke_root, authoritative_root, registry_files_root):
        path.mkdir(parents=True, exist_ok=True)

    generated_at = fixture_timestamp()
    linux_path = files_root / "chummer-avalonia-linux-x64-installer.deb"
    windows_path = files_root / "chummer-avalonia-win-x64-installer.exe"
    payload_path = files_root / "chummer-avalonia-win-x64-payload.zip"
    macos_path = files_root / "chummer-avalonia-osx-arm64-installer.dmg"

    linux_path.write_bytes(b"synthetic-debian-package-for-public-downloads-bundle-tests")
    macos_path.write_bytes(b"synthetic-macos-disk-image-for-public-downloads-bundle-tests")
    with zipfile.ZipFile(payload_path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("Chummer.Avalonia.exe", b"synthetic-windows-payload" * 512)

    payload_sha = sha256_file(payload_path)
    payload_size = payload_path.stat().st_size
    payload_download_url = f"https://chummer.run/downloads/files/{payload_path.name}"
    installer_bytes = bytearray(4096)
    installer_bytes[0:2] = b"MZ"
    installer_bytes[0x3C:0x40] = (0x80).to_bytes(4, "little")
    installer_bytes[0x80:0x84] = b"PE\0\0"
    installer_bytes[0x84:0x86] = (0x8664).to_bytes(2, "little")
    installer_bytes[0x86:0x88] = (3).to_bytes(2, "little")
    embedded_payload_metadata = f"{payload_download_url}\0{payload_sha}\0{payload_size}\0".encode("utf-8")
    installer_bytes[0x100 : 0x100 + len(embedded_payload_metadata)] = embedded_payload_metadata
    windows_path.write_bytes(installer_bytes)

    linux_row: dict[str, object] = {
        "artifactId": "avalonia-linux-x64-installer",
        "head": "avalonia",
        "rid": "linux-x64",
        "platform": "linux",
        "arch": "x64",
        "kind": "installer",
        "fileName": linux_path.name,
        "downloadUrl": f"https://chummer.run/downloads/files/{linux_path.name}",
        "sha256": sha256_file(linux_path),
        "sizeBytes": linux_path.stat().st_size,
        "channel": "preview",
        "version": FIXTURE_RELEASE_VERSION,
        "installAccessClass": "open_public",
        "compatibilityState": "compatible",
    }
    windows_row: dict[str, object] = {
        "artifactId": "avalonia-win-x64-installer",
        "head": "avalonia",
        "rid": "win-x64",
        "platform": "windows",
        "arch": "x64",
        "kind": "installer",
        "fileName": windows_path.name,
        "downloadUrl": f"https://chummer.run/downloads/files/{windows_path.name}",
        "sha256": sha256_file(windows_path),
        "sizeBytes": windows_path.stat().st_size,
        "channel": "preview",
        "version": FIXTURE_RELEASE_VERSION,
        "installAccessClass": "open_public",
        "compatibilityState": "compatible",
        "installerMode": "bootstrap",
        "payloadFileName": payload_path.name,
        "payloadDownloadUrl": payload_download_url,
        "payloadSha256": payload_sha,
        "payloadSizeBytes": payload_size,
    }
    macos_row: dict[str, object] = {
        "artifactId": "avalonia-osx-arm64-installer",
        "head": "avalonia",
        "rid": "osx-arm64",
        "platform": "macos",
        "arch": "arm64",
        "kind": "installer",
        "fileName": macos_path.name,
        "downloadUrl": f"https://chummer.run/downloads/files/{macos_path.name}",
        "sha256": sha256_file(macos_path),
        "sizeBytes": macos_path.stat().st_size,
        "channel": "preview",
        "version": FIXTURE_RELEASE_VERSION,
        "installAccessClass": "account_required",
        "compatibilityState": "compatible",
    }

    write_json(
        payload_path.with_suffix(payload_path.suffix + ".json"),
        {
            "contractName": "chummer6-ui.windows_bootstrap_payload",
            "fileName": payload_path.name,
            "installerFileName": windows_path.name,
            "downloadUrl": payload_download_url,
            "sha256": payload_sha,
            "sizeBytes": payload_size,
            "releaseVersion": FIXTURE_RELEASE_VERSION,
        },
    )

    artifacts = [linux_row, windows_row, macos_row]
    manifest_path = fixture_root / "RELEASE_CHANNEL.generated.json"
    write_json(
        manifest_path,
        {
            "contractName": "Chummer.Hub.Registry.Contracts",
            "schemaVersion": "1.0.0",
            "status": "published",
            "channelId": "preview",
            "channel": "preview",
            "version": FIXTURE_RELEASE_VERSION,
            "releaseVersion": FIXTURE_RELEASE_VERSION,
            "publicVersion": FIXTURE_PUBLIC_VERSION,
            "generatedAt": generated_at,
            "publishedAt": generated_at,
            "rolloutState": "promoted_preview",
            "rolloutReason": "Synthetic cross-platform shelf for public bundle tests.",
            "supportabilityState": "preview_supported",
            "artifacts": artifacts,
        },
    )

    localization_gate = localization_gate_fixture(generated_at)
    localization_gate_path = fixture_root / "UI_LOCALIZATION_RELEASE_GATE.generated.json"
    write_json(localization_gate_path, localization_gate)

    release_proof_path = fixture_root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
    write_json(
        release_proof_path,
        {
            "status": "passed",
            "generatedAt": generated_at,
            "baseUrl": "https://chummer.run",
            "journeysPassed": list(FIXTURE_PROOF_JOURNEYS),
            "proofRoutes": list(FIXTURE_PROOF_ROUTES),
            "uiLocalizationReleaseGate": localization_gate,
        },
    )

    promotion_evidence_path = fixture_root / "public-promotion.json"
    write_json(
        promotion_evidence_path,
        {
            "contractName": "chummer.run.desktop_release_publication",
            "status": "pass",
            "generatedAt": generated_at,
            "artifacts": [
                {
                    "artifactId": row["artifactId"],
                    "fileName": row["fileName"],
                    "platform": row["platform"],
                    "kind": row["kind"],
                    "installAccessClass": row["installAccessClass"],
                    "promotionStatus": "promoted",
                    "startupSmokeStatus": "passed",
                    "artifactSha256": row["sha256"],
                    "artifactSizeBytes": row["sizeBytes"],
                }
                for row in artifacts
            ],
        },
    )

    for artifact_path, artifact in (
        (linux_path, linux_row),
        (windows_path, windows_row),
        (macos_path, macos_row),
    ):
        write_startup_smoke_fixture(startup_smoke_root, artifact_path, artifact, generated_at)

    windows_visual_proof_path = write_passing_windows_visual_proof_fixture(fixture_root, windows_row)
    return PublicDownloadsFixture(
        root=fixture_root,
        files_root=files_root,
        startup_smoke_root=startup_smoke_root,
        manifest_path=manifest_path,
        release_proof_path=release_proof_path,
        localization_gate_path=localization_gate_path,
        promotion_evidence_path=promotion_evidence_path,
        authoritative_root=authoritative_root,
        registry_files_root=registry_files_root,
        windows_visual_proof_path=windows_visual_proof_path,
        linux_row=linux_row,
        windows_row=windows_row,
        macos_row=macos_row,
    )


def materializer_fixture_env(fixture: PublicDownloadsFixture) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER": "false",
            "CHUMMER_PUBLIC_STARTUP_SMOKE_MAX_AGE_SECONDS": "86400",
            "CHUMMER_MACOS_PUBLIC_SHELF_ENABLED": "true",
            "CHUMMER_PUBLIC_RELEASE_CHANNEL_SOURCE": str(fixture.manifest_path),
            "CHUMMER_PRESENTATION_RELEASE_CHANNEL_PATH": str(fixture.manifest_path),
            "CHUMMER_RUNSERVICES_SOURCE_FILES_ROOT": str(fixture.files_root),
            "CHUMMER_PRESENTATION_FILES_ROOT": str(fixture.files_root),
            "CHUMMER_PRESENTATION_STARTUP_SMOKE_ROOT": str(fixture.startup_smoke_root),
            "CHUMMER_RUNSERVICES_PORTAL_STARTUP_SMOKE_ROOT": str(fixture.startup_smoke_root),
            "CHUMMER_HUB_REGISTRY_PUBLISHED_FILES_ROOT": str(fixture.registry_files_root),
            "CHUMMER_PUBLIC_AUTHORITATIVE_PUBLISHED_ROOT": str(fixture.authoritative_root),
            "CHUMMER_PUBLIC_DISABLE_WORKSPACE_MANIFEST_MIRRORS": "true",
            "CHUMMER_RUN_LOCAL_RELEASE_PROOF_SOURCE": str(fixture.release_proof_path),
            "CHUMMER_UI_LOCALIZATION_RELEASE_GATE_SOURCE": str(fixture.localization_gate_path),
            "CHUMMER_PRESENTATION_RELEASE_EVIDENCE_SOURCE": str(fixture.promotion_evidence_path),
            "CHUMMER_WINDOWS_INSTALLER_VISUAL_PROOF_PATH": str(fixture.windows_visual_proof_path),
            "CHUMMER_WINDOWS_VISUAL_AUDIT_PUBLISHED_PATH": str(
                fixture.root / "WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json"
            ),
            "CHUMMER_WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST_PATH": str(
                fixture.root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            ),
            "CHUMMER_WINDOWS_VISUAL_AUDIT_AUTO_IMPORT_PATH": str(
                fixture.root / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
            ),
        }
    )
    return env


def copy_fixture_files(source_root: Path, target_root: Path) -> None:
    target_root.mkdir(parents=True, exist_ok=True)
    for source_path in source_root.iterdir():
        if source_path.is_file():
            shutil.copy2(source_path, target_root / source_path.name)


def run_materializer(output_root: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    mirror_existed = RUN_API_LOCALIZATION_GATE_MIRROR.is_file()
    mirror_stat = RUN_API_LOCALIZATION_GATE_MIRROR.stat() if mirror_existed else None
    mirror_bytes = RUN_API_LOCALIZATION_GATE_MIRROR.read_bytes() if mirror_existed else b""
    try:
        return subprocess.run(
            ["bash", str(MATERIALIZER), str(output_root)],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    finally:
        if mirror_existed:
            RUN_API_LOCALIZATION_GATE_MIRROR.write_bytes(mirror_bytes)
            if mirror_stat is not None:
                os.utime(
                    RUN_API_LOCALIZATION_GATE_MIRROR,
                    ns=(mirror_stat.st_atime_ns, mirror_stat.st_mtime_ns),
                )
        else:
            RUN_API_LOCALIZATION_GATE_MIRROR.unlink(missing_ok=True)


class PublicDownloadsBundleTests(unittest.TestCase):
    def assert_materializer_rejects_release_proof_routes(
        self,
        routes: list[str],
        expected_error: str,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="chummer-public-proof-routes-invalid-") as temp_root:
            temp_path = Path(temp_root)
            fixture = write_public_downloads_fixture(temp_path)
            proof_payload = json.loads(fixture.release_proof_path.read_text(encoding="utf-8"))
            proof_payload["proofRoutes"] = routes
            write_json(fixture.release_proof_path, proof_payload)

            output_root = temp_path / "downloads"
            output_root.mkdir(parents=True)
            output_sentinel = output_root / "RELEASE_CHANNEL.generated.json"
            output_sentinel.write_text("existing output must survive\n", encoding="utf-8")
            authoritative_sentinel = fixture.authoritative_root / "RELEASE_CHANNEL.generated.json"
            authoritative_sentinel.write_text("existing publication must survive\n", encoding="utf-8")

            completed = run_materializer(output_root, materializer_fixture_env(fixture))

            self.assertNotEqual(completed.returncode, 0, msg=completed.stdout)
            self.assertIn(expected_error, completed.stderr or completed.stdout)
            self.assertEqual(output_sentinel.read_text(encoding="utf-8"), "existing output must survive\n")
            self.assertEqual(
                authoritative_sentinel.read_text(encoding="utf-8"),
                "existing publication must survive\n",
            )

    def test_materializer_accepts_registry_canonical_proof_routes(self):
        with tempfile.TemporaryDirectory(prefix="chummer-public-proof-routes-valid-") as temp_root:
            temp_path = Path(temp_root)
            fixture = write_public_downloads_fixture(temp_path)
            output_root = temp_path / "downloads"

            completed = run_materializer(output_root, materializer_fixture_env(fixture))

            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
            self.assertTrue((output_root / "RELEASE_CHANNEL.generated.json").is_file())

    def test_materializer_rejects_roster_route_in_release_proof(self):
        self.assert_materializer_rejects_release_proof_routes(
            [*FIXTURE_PROOF_ROUTES[:8], "/account/roster", *FIXTURE_PROOF_ROUTES[8:]],
            "declares unsupported additional routes: /account/roster",
        )

    def test_materializer_rejects_duplicate_route_in_release_proof(self):
        self.assert_materializer_rejects_release_proof_routes(
            [*FIXTURE_PROOF_ROUTES, FIXTURE_PROOF_ROUTES[-1]],
            "contains duplicate routes: /downloads/install/avalonia-win-x64-installer",
        )

    def test_materializer_rejects_reordered_registry_prefix_in_release_proof(self):
        reordered_routes = list(FIXTURE_PROOF_ROUTES)
        reordered_routes[1], reordered_routes[2] = reordered_routes[2], reordered_routes[1]
        self.assert_materializer_rejects_release_proof_routes(
            reordered_routes,
            "must begin with the exact Registry canonical route prefix",
        )

    def test_materializer_rejects_arbitrary_extension_in_release_proof(self):
        self.assert_materializer_rejects_release_proof_routes(
            [*FIXTURE_PROOF_ROUTES[:8], "/account/admin", *FIXTURE_PROOF_ROUTES[8:]],
            "declares unsupported additional routes: /account/admin",
        )

    def test_materializer_rejects_non_registry_installer_identifier(self):
        self.assert_materializer_rejects_release_proof_routes(
            [*FIXTURE_PROOF_ROUTES, "/downloads/install/experimental.build"],
            "declares unsupported additional routes: /downloads/install/experimental.build",
        )

    def test_materializer_rejects_null_primary_route_alias(self):
        with tempfile.TemporaryDirectory(prefix="chummer-public-proof-null-primary-") as temp_root:
            temp_path = Path(temp_root)
            fixture = write_public_downloads_fixture(temp_path)
            proof_payload = json.loads(fixture.release_proof_path.read_text(encoding="utf-8"))
            proof_payload["proof_routes"] = list(FIXTURE_PROOF_ROUTES)
            proof_payload["proofRoutes"] = None
            write_json(fixture.release_proof_path, proof_payload)

            completed = run_materializer(temp_path / "downloads", materializer_fixture_env(fixture))

            self.assertNotEqual(completed.returncode, 0, msg=completed.stdout)
            self.assertIn("release proof proofRoutes must be a list of strings", completed.stderr or completed.stdout)

    def test_materializer_rejects_null_secondary_route_alias(self):
        with tempfile.TemporaryDirectory(prefix="chummer-public-proof-null-secondary-") as temp_root:
            temp_path = Path(temp_root)
            fixture = write_public_downloads_fixture(temp_path)
            proof_payload = json.loads(fixture.release_proof_path.read_text(encoding="utf-8"))
            proof_payload["proof_routes"] = None
            write_json(fixture.release_proof_path, proof_payload)

            completed = run_materializer(temp_path / "downloads", materializer_fixture_env(fixture))

            self.assertNotEqual(completed.returncode, 0, msg=completed.stdout)
            self.assertIn("release proof proof_routes must be a list of strings", completed.stderr or completed.stdout)

    def test_materializer_rejects_unsorted_installer_extensions_in_release_proof(self):
        self.assert_materializer_rejects_release_proof_routes(
            [*FIXTURE_PROOF_ROUTES[:8], *reversed(FIXTURE_PROOF_ROUTES[8:])],
            "additional installer routes must use canonical ordering",
        )

    def test_materializer_declares_workspace_portal_manifest_mirror_sync(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        script_text = MATERIALIZER.read_text(encoding="utf-8")

        self.assertIn("sync_workspace_portal_manifest_mirrors() {", script_text)
        self.assertIn('replace_file_atomically "$source_path" "$target_path"', script_text)
        self.assertIn('local -a mirror_root_candidates=(', script_text)
        self.assertIn('"$REPO_ROOT"', script_text)
        self.assertIn('"$mirror_root/Chummer.Portal/downloads/$source_name"', script_text)
        self.assertIn('"$mirror_root/Docker/Downloads/$source_name"', script_text)
        self.assertIn('"$mirror_root/.codex-studio/published/portal/$source_name"', script_text)
        self.assertIn('"/docker/chummercomplete/chummer6-ui"', script_text)
        self.assertIn('"/docker/chummercomplete/chummer-presentation"', script_text)
        self.assertIn('sync_workspace_portal_manifest_mirrors "RELEASE_CHANNEL.generated.json"', script_text)
        self.assertIn('sync_workspace_portal_manifest_mirrors "releases.json"', script_text)

    def test_materializer_hydrates_manifest_owned_artifacts_from_candidate_roots(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        script_text = MATERIALIZER.read_text(encoding="utf-8")

        self.assertIn('REGISTRY_PUBLISHED_FILES_ROOT="${CHUMMER_HUB_REGISTRY_PUBLISHED_FILES_ROOT:-$REGISTRY_ROOT/.codex-studio/published/files}"', script_text)
        self.assertIn('AUTHORITATIVE_PUBLISHED_ROOT="${CHUMMER_PUBLIC_AUTHORITATIVE_PUBLISHED_ROOT:-$REGISTRY_ROOT/.codex-studio/published}"', script_text)
        self.assertIn("hydrate_manifest_owned_artifacts_from_candidate_roots() {", script_text)
        self.assertIn('replace_file(source_path, target_path)', script_text)
        self.assertIn('payload_sidecar_matches(', script_text)
        self.assertIn('"$REGISTRY_PUBLISHED_FILES_ROOT"', script_text)
        self.assertIn("sync_authoritative_publication_with_rollback() {", script_text)
        self.assertIn('sync_authoritative_publication_with_rollback "$OUTPUT_ROOT"', script_text)
        self.assertIn('hydrate_manifest_owned_artifacts_from_candidate_roots \\', script_text)
        self.assertIn('"$PUBLIC_RELEASE_CHANNEL_SOURCE_PATH" \\', script_text)
        self.assertIn('"$RUNSERVICES_SOURCE_FILES_ROOT" \\', script_text)
        self.assertIn('"$PRESENTATION_FILES_ROOT"', script_text)

    def test_materializer_refreshes_stage_release_handoff_with_presentation_scripts(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        script_text = MATERIALIZER.read_text(encoding="utf-8")

        self.assertIn('RELEASE_BUILD_HANDOFF_SCRIPT_PATH="${CHUMMER_PUBLIC_RELEASE_BUILD_HANDOFF_SCRIPT_PATH:-$PRESENTATION_ROOT/scripts/materialize_release_candidate_handoff.py}"', script_text)
        self.assertIn('WINDOWS_EXIT_GATE_SCRIPT_PATH="${CHUMMER_WINDOWS_EXIT_GATE_SCRIPT_PATH:-$PRESENTATION_ROOT/scripts/materialize-windows-desktop-exit-gate.sh}"', script_text)
        self.assertIn("refresh_release_build_handoff() {", script_text)
        self.assertIn('"$stage_dir/RELEASE_BUILD_HANDOFF.generated.json"', script_text)
        self.assertIn('"$stage_dir/UI_WINDOWS_DESKTOP_EXIT_GATE.generated.json"', script_text)
        self.assertIn('env "${handoff_env[@]}" python3 "$RELEASE_BUILD_HANDOFF_SCRIPT_PATH" "$stage_dir" >/dev/null', script_text)
        self.assertIn('refresh_release_build_handoff "$OUTPUT_ROOT"', script_text)

    def test_materializer_refreshes_windows_visual_proof_operator_receipts_on_gate_failure(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        script_text = MATERIALIZER.read_text(encoding="utf-8")

        self.assertIn('WINDOWS_VISUAL_AUDIT_PUBLISHED_PATH="${CHUMMER_WINDOWS_VISUAL_AUDIT_PUBLISHED_PATH:-$REPO_ROOT/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json}"', script_text)
        self.assertIn('WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST_PATH="${CHUMMER_WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST_PATH:-$REPO_ROOT/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json}"', script_text)
        self.assertIn('WINDOWS_VISUAL_AUDIT_AUTO_IMPORT_PATH="${CHUMMER_WINDOWS_VISUAL_AUDIT_AUTO_IMPORT_PATH:-$REPO_ROOT/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json}"', script_text)
        self.assertIn("refresh_windows_visual_proof_operator_receipts() {", script_text)
        self.assertIn('python3 "$SCRIPT_DIR/verify_windows_installer_visual_audit.py" "${audit_args[@]}"', script_text)
        self.assertIn('python3 "$SCRIPT_DIR/materialize_windows_installer_visual_audit_intake_request.py" "${intake_args[@]}"', script_text)
        self.assertIn('python3 "$SCRIPT_DIR/verify_windows_installer_visual_audit_intake_request.py" --receipt "$WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST_PATH"', script_text)
        self.assertIn('python3 "$SCRIPT_DIR/auto_import_windows_installer_gold_proof.py" \\', script_text)
        self.assertIn('--refresh-intake-request \\', script_text)
        self.assertIn('refresh_windows_visual_proof_operator_receipts \\', script_text)
        self.assertIn('"$OUTPUT_ROOT/visual-audit/windows-installer/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"', script_text)

    def test_aur_package_materializer_derives_arch_sidecar_from_linux_deb(self):
        if not AUR_MATERIALIZER.exists():
            self.skipTest(f"missing AUR materializer: {AUR_MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-aur-materializer-") as temp_root:
            root = Path(temp_root)
            files_root = root / "files"
            files_root.mkdir(parents=True)
            deb_path = files_root / "chummer-avalonia-linux-x64-installer.deb"
            deb_path.write_bytes(b"fake deb for sidecar materializer")
            deb_sha = subprocess.check_output(["sha256sum", str(deb_path)], text=True).split()[0]
            manifest_path = root / "releases.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "version": "run-20260619-101500",
                        "channel": "public_stable",
                        "downloads": [
                            {
                                "id": "avalonia-linux-x64-installer",
                                "artifactId": "avalonia-linux-x64-installer",
                                "platform": "Avalonia Desktop Linux X64 Installer",
                                "platformId": "linux",
                                "arch": "x64",
                                "kind": "installer",
                                "fileName": deb_path.name,
                                "url": f"https://chummer.run/downloads/files/{deb_path.name}",
                                "sha256": deb_sha,
                                "sizeBytes": deb_path.stat().st_size,
                                "channel": "public_stable",
                                "version": "run-20260619-101500",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    "python3",
                    str(AUR_MATERIALIZER),
                    "--manifest",
                    str(manifest_path),
                    "--files-root",
                    str(files_root),
                    "--output-root",
                    str(root),
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)

            catalog = json.loads((root / "aur-packages.json").read_text(encoding="utf-8"))
            package = catalog["packages"][0]
            self.assertEqual(package["packageName"], "chummer6-bin")
            self.assertEqual(package["packageVersion"], "20260619.101500")
            self.assertEqual(package["upstreamArtifactSha256"], deb_sha)
            self.assertTrue((files_root / "chummer6-bin.PKGBUILD").is_file())
            self.assertTrue((files_root / "chummer6-bin.SRCINFO").is_file())
            archive_path = files_root / "chummer6-bin-aur-source.tar.gz"
            self.assertTrue(archive_path.is_file())
            with tarfile.open(archive_path, "r:gz") as archive:
                names = set(archive.getnames())
            self.assertIn("chummer6-bin/PKGBUILD", names)
            self.assertIn("chummer6-bin/.SRCINFO", names)

    def test_aur_package_materializer_uses_artifact_timestamp_when_release_id_is_ci_run_number(self):
        if not AUR_MATERIALIZER.exists():
            self.skipTest(f"missing AUR materializer: {AUR_MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-aur-run-number-materializer-") as temp_root:
            root = Path(temp_root)
            files_root = root / "files"
            files_root.mkdir(parents=True)
            deb_path = files_root / "chummer-avalonia-linux-x64-installer.deb"
            deb_path.write_bytes(b"fake deb for run-number sidecar materializer")
            deb_sha = subprocess.check_output(["sha256sum", str(deb_path)], text=True).split()[0]
            manifest_path = root / "releases.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "version": "run-258",
                        "channel": "preview",
                        "generatedAt": "2026-06-19T19:53:33Z",
                        "downloads": [
                            {
                                "id": "avalonia-linux-x64-installer",
                                "artifactId": "avalonia-linux-x64-installer",
                                "platform": "Avalonia Desktop Linux X64 Installer",
                                "platformId": "linux",
                                "arch": "x64",
                                "kind": "installer",
                                "fileName": deb_path.name,
                                "url": f"https://chummer.run/downloads/files/{deb_path.name}",
                                "sha256": deb_sha,
                                "sizeBytes": deb_path.stat().st_size,
                                "channel": "preview",
                                "version": "run-258",
                                "generatedAt": "2026-06-19T19:53:33Z",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    "python3",
                    str(AUR_MATERIALIZER),
                    "--manifest",
                    str(manifest_path),
                    "--files-root",
                    str(files_root),
                    "--output-root",
                    str(root),
                ],
                cwd=REPO_ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)

            catalog = json.loads((root / "aur-packages.json").read_text(encoding="utf-8"))
            package = catalog["packages"][0]
            self.assertEqual(package["packageVersion"], "20260619.195333")
            self.assertEqual(package["upstreamArtifactSha256"], deb_sha)
            self.assertIn("pkgver=20260619.195333", (files_root / "chummer6-bin.PKGBUILD").read_text(encoding="utf-8"))

    def test_materializer_publishes_linux_startup_smoke_with_stable_companion_evidence(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-public-downloads-bundle-") as temp_root:
            temp_path = Path(temp_root)
            fixture = write_public_downloads_fixture(temp_path)
            output_root = temp_path / "downloads"
            env = materializer_fixture_env(fixture)

            completed = run_materializer(output_root, env)
            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)

            releases_payload = json.loads((output_root / "releases.json").read_text(encoding="utf-8"))
            self.assertEqual(releases_payload.get("publicVersion"), FIXTURE_PUBLIC_VERSION)
            aur_catalog_path = output_root / "aur-packages.json"
            self.assertTrue(
                (output_root / "files" / "chummer-avalonia-linux-x64-installer.deb").is_file(),
                "synthetic release shelf must retain its Linux installer",
            )
            self.assertTrue(aur_catalog_path.is_file(), "Linux bundles should publish an Arch/AUR sidecar catalog")
            aur_payload = json.loads(aur_catalog_path.read_text(encoding="utf-8"))
            self.assertIn("chummer6-bin", {str(item.get("packageName") or "") for item in aur_payload.get("packages") or []})
            self.assertTrue((output_root / "files" / "chummer6-bin-aur-source.tar.gz").is_file())
            self.assertTrue((output_root / "files" / "chummer6-bin.PKGBUILD").is_file())
            self.assertTrue((output_root / "files" / "chummer6-bin.SRCINFO").is_file())
            downloads = releases_payload.get("downloads") or []
            linux_installer = next(
                (item for item in downloads if str(item.get("id") or "") == "avalonia-linux-x64-installer"),
                None,
            )
            self.assertIsNotNone(linux_installer, "synthetic release shelf must publish a Linux manifest row")
            self.assertEqual(
                linux_installer.get("installAccessClass"),
                "open_public",
                "materialized Linux installer rows must match the current public-edge guest-readable install posture",
            )

            windows_installer = next(
                (item for item in downloads if str(item.get("id") or "") == "avalonia-win-x64-installer"),
                None,
            )
            self.assertIsNotNone(windows_installer, "synthetic release shelf must publish a Windows manifest row")
            self.assertEqual(
                windows_installer.get("installAccessClass"),
                "open_public",
                "materialized Windows installer rows must match the current public-edge guest-readable install posture",
            )

            payload_file_name = str(windows_installer.get("payloadFileName") or "").strip()
            payload_download_url = str(windows_installer.get("payloadDownloadUrl") or "").strip()
            self.assertTrue(payload_file_name, "Windows installer rows should publish payloadFileName")
            self.assertTrue(payload_download_url, "Windows installer rows should publish payloadDownloadUrl")

            payload_path = output_root / "files" / payload_file_name
            sidecar_path = output_root / "files" / f"{payload_file_name}.json"
            self.assertTrue(payload_path.is_file(), f"missing published Windows payload zip: {payload_path}")
            self.assertTrue(sidecar_path.is_file(), f"missing published Windows payload sidecar: {sidecar_path}")

            sidecar_payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
            self.assertEqual(sidecar_payload.get("contractName"), "chummer6-ui.windows_bootstrap_payload")
            self.assertEqual(sidecar_payload.get("fileName"), payload_file_name)
            self.assertEqual(sidecar_payload.get("installerFileName"), str(windows_installer.get("fileName") or ""))
            self.assertEqual(sidecar_payload.get("downloadUrl"), payload_download_url)
            self.assertEqual(sidecar_payload.get("sha256"), windows_installer.get("payloadSha256"))
            self.assertEqual(int(sidecar_payload.get("sizeBytes") or 0), int(windows_installer.get("payloadSizeBytes") or 0))

            macos_installer = next(
                (item for item in downloads if str(item.get("id") or "") == "avalonia-osx-arm64-installer"),
                None,
            )
            self.assertIsNotNone(macos_installer, "synthetic release shelf must publish a macOS manifest row")

            startup_root = output_root / "startup-smoke"
            receipt_path = startup_root / "startup-smoke-avalonia-linux-x64.receipt.json"
            self.assertTrue(receipt_path.is_file(), f"missing published receipt: {receipt_path}")

            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt.get("channelId"), str(releases_payload.get("channel") or ""))
            self.assertEqual(receipt.get("channel"), str(releases_payload.get("channel") or ""))
            for key in (
                "artifactInstallVerificationPath",
                "artifactInstallDpkgLogPath",
                "artifactInstallLaunchCapturePath",
                "artifactInstallWrapperCapturePath",
                "artifactInstallDesktopEntryCapturePath",
            ):
                value = str(receipt.get(key) or "").strip()
                self.assertTrue(value, f"receipt field {key} should be populated")
                companion_path = Path(value)
                self.assertTrue(companion_path.is_file(), f"missing companion evidence for {key}: {companion_path}")
                self.assertEqual(companion_path.parent, startup_root, f"{key} should point into the published startup-smoke shelf")

            verification = json.loads(Path(receipt["artifactInstallVerificationPath"]).read_text(encoding="utf-8"))
            for key in (
                "dpkgLogPath",
                "installedLaunchCapturePath",
                "wrapperCapturePath",
                "desktopEntryCapturePath",
            ):
                value = str(verification.get(key) or "").strip()
                self.assertTrue(value, f"install verification field {key} should be populated")
                companion_path = Path(value)
                self.assertTrue(companion_path.is_file(), f"missing install verification evidence for {key}: {companion_path}")
                self.assertEqual(companion_path.parent, startup_root, f"{key} should point into the published startup-smoke shelf")

    def test_materializer_keeps_windows_manifest_rows_aligned_with_published_bytes(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-public-downloads-bundle-windows-") as temp_root:
            temp_path = Path(temp_root)
            fixture = write_public_downloads_fixture(temp_path)
            output_root = temp_path / "downloads"
            env = materializer_fixture_env(fixture)

            completed = run_materializer(output_root, env)
            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)

            manifest = json.loads((output_root / "RELEASE_CHANNEL.generated.json").read_text(encoding="utf-8"))
            artifacts = manifest.get("artifacts") or []
            windows_installer = next(
                (item for item in artifacts if str(item.get("artifactId") or "") == "avalonia-win-x64-installer"),
                None,
            )
            self.assertIsNotNone(windows_installer, "expected a published Windows installer row")

            installer_path = output_root / "files" / str(windows_installer.get("fileName") or "")
            payload_file_name = str(windows_installer.get("payloadFileName") or "")
            payload_path = output_root / "files" / payload_file_name
            payload_sidecar_path = output_root / "files" / f"{payload_file_name}.json"

            self.assertTrue(installer_path.is_file(), f"missing Windows installer bytes: {installer_path}")
            self.assertTrue(payload_path.is_file(), f"missing Windows payload bytes: {payload_path}")
            self.assertTrue(payload_sidecar_path.is_file(), f"missing Windows payload sidecar: {payload_sidecar_path}")

            self.assertEqual(sha256_file(installer_path), str(windows_installer.get("sha256") or ""))
            self.assertEqual(installer_path.stat().st_size, int(windows_installer.get("sizeBytes") or 0))
            self.assertEqual(sha256_file(payload_path), str(windows_installer.get("payloadSha256") or ""))
            self.assertEqual(payload_path.stat().st_size, int(windows_installer.get("payloadSizeBytes") or 0))

            payload_sidecar = json.loads(payload_sidecar_path.read_text(encoding="utf-8"))
            self.assertEqual(payload_sidecar.get("sha256"), windows_installer.get("payloadSha256"))
            self.assertEqual(int(payload_sidecar.get("sizeBytes") or 0), int(windows_installer.get("payloadSizeBytes") or 0))

    def test_materializer_drops_stale_source_artifacts_not_present_in_manifest_truth(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-public-downloads-bundle-stale-") as temp_root:
            temp_path = Path(temp_root)
            fixture = write_public_downloads_fixture(temp_path)
            output_root = temp_path / "downloads"
            stale_root = temp_path / "stale-files"
            stale_root.mkdir(parents=True, exist_ok=True)
            (stale_root / "chummer-blazor-desktop-linux-x64-installer.deb").write_bytes(b"stale-extra-artifact")

            env = materializer_fixture_env(fixture)
            env["CHUMMER_RUNSERVICES_SOURCE_FILES_ROOT"] = str(stale_root)

            completed = run_materializer(output_root, env)
            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)

            canonical_payload = json.loads((output_root / "RELEASE_CHANNEL.generated.json").read_text(encoding="utf-8"))
            artifact_ids = {str(artifact.get("artifactId") or "") for artifact in canonical_payload.get("artifacts") or []}
            self.assertNotIn(
                "blazor-desktop-linux-x64-installer",
                artifact_ids,
                "materializer must drop stale source artifacts that are not present in the active release-channel truth",
            )
            self.assertFalse(
                (output_root / "files" / "chummer-blazor-desktop-linux-x64-installer.deb").exists(),
                "materializer must not leak stale Linux installer bytes into the published files shelf",
            )

    def test_materializer_drops_stale_mac_installer_bytes_not_present_in_manifest_truth(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-public-downloads-bundle-stale-macos-") as temp_root:
            temp_path = Path(temp_root)
            fixture = write_public_downloads_fixture(temp_path)
            output_root = temp_path / "downloads"
            stale_root = temp_path / "stale-files"
            stale_root.mkdir(parents=True, exist_ok=True)
            stale_file = stale_root / "chummer-blazor-desktop-osx-arm64-installer.dmg"
            stale_file.write_bytes(b"stale-extra-macos-installer")

            env = materializer_fixture_env(fixture)
            env["CHUMMER_RUNSERVICES_SOURCE_FILES_ROOT"] = str(stale_root)

            completed = run_materializer(output_root, env)
            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)

            canonical_payload = json.loads((output_root / "RELEASE_CHANNEL.generated.json").read_text(encoding="utf-8"))
            artifact_names = {str(artifact.get("fileName") or "") for artifact in canonical_payload.get("artifacts") or []}
            self.assertNotIn(
                "chummer-blazor-desktop-osx-arm64-installer.dmg",
                artifact_names,
                "materializer must not resurrect stale macOS installer bytes that are no longer present in release-channel truth",
            )
            self.assertFalse(
                (output_root / "files" / stale_file.name).exists(),
                "materializer must not leak stale macOS installer bytes into the published files shelf",
            )

    def test_materializer_preserves_newer_merged_artifact_bytes_over_stale_manifest_matches(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-public-downloads-bundle-stale-manifest-") as temp_root:
            temp_path = Path(temp_root)
            fixture = write_public_downloads_fixture(temp_path)
            output_root = temp_path / "downloads"
            fresh_root = temp_path / "fresh-files"
            stale_registry_root = temp_path / "registry-published-files"
            copy_fixture_files(fixture.files_root, fresh_root)
            stale_registry_root.mkdir(parents=True, exist_ok=True)

            linux_file_name = "chummer-avalonia-linux-x64-installer.deb"
            fresh_linux_path = fresh_root / linux_file_name
            fresh_linux_sha = sha256_file(fresh_linux_path)
            fresh_linux_size = fresh_linux_path.stat().st_size

            stale_linux_path = stale_registry_root / linux_file_name
            stale_linux_path.write_bytes(b"stale-linux-installer-bytes-for-manifest-regression")
            stale_linux_sha = sha256_file(stale_linux_path)
            stale_linux_size = stale_linux_path.stat().st_size

            source_manifest_path = temp_path / "RELEASE_CHANNEL.generated.json"
            source_manifest = json.loads(fixture.manifest_path.read_text(encoding="utf-8"))
            for artifact in source_manifest.get("artifacts") or []:
                if str(artifact.get("artifactId") or "") != "avalonia-linux-x64-installer":
                    continue
                artifact["sha256"] = stale_linux_sha
                artifact["sizeBytes"] = stale_linux_size
            source_manifest_path.write_text(json.dumps(source_manifest, indent=2) + "\n", encoding="utf-8")

            env = materializer_fixture_env(fixture)
            env["CHUMMER_RUNSERVICES_SOURCE_FILES_ROOT"] = str(fresh_root)
            env["CHUMMER_PRESENTATION_FILES_ROOT"] = str(fresh_root)
            env["CHUMMER_HUB_REGISTRY_PUBLISHED_FILES_ROOT"] = str(stale_registry_root)
            env["CHUMMER_PUBLIC_RELEASE_CHANNEL_SOURCE"] = str(source_manifest_path)

            completed = run_materializer(output_root, env)
            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)

            manifest = json.loads((output_root / "RELEASE_CHANNEL.generated.json").read_text(encoding="utf-8"))
            linux_installer = next(
                (item for item in manifest.get("artifacts") or [] if str(item.get("artifactId") or "") == "avalonia-linux-x64-installer"),
                None,
            )
            self.assertIsNotNone(linux_installer, "expected a published Linux installer row")
            self.assertEqual(
                linux_installer.get("sha256"),
                fresh_linux_sha,
                "materializer must keep newer merged Linux bytes authoritative instead of restoring stale manifest-matching bytes",
            )
            self.assertEqual(
                int(linux_installer.get("sizeBytes") or 0),
                fresh_linux_size,
                "materializer must publish the actual merged Linux installer size",
            )
            self.assertNotEqual(
                linux_installer.get("sha256"),
                stale_linux_sha,
                "materializer must not resurrect stale Linux digest truth from registry fallback files",
            )

    def test_materializer_allows_presentation_source_to_replace_stale_runservices_bytes(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-public-downloads-bundle-source-precedence-") as temp_root:
            temp_path = Path(temp_root)
            fixture = write_public_downloads_fixture(temp_path)
            output_root = temp_path / "downloads"
            stale_runservices_root = temp_path / "runservices-files"
            fresh_presentation_root = temp_path / "presentation-files"
            stale_runservices_root.mkdir(parents=True, exist_ok=True)
            copy_fixture_files(fixture.files_root, fresh_presentation_root)

            linux_file_name = "chummer-avalonia-linux-x64-installer.deb"
            fresh_linux_path = fresh_presentation_root / linux_file_name
            fresh_linux_sha = sha256_file(fresh_linux_path)
            fresh_linux_size = fresh_linux_path.stat().st_size

            stale_linux_path = stale_runservices_root / linux_file_name
            stale_linux_path.write_bytes(b"older-runservices-linux-installer")

            source_manifest_path = temp_path / "RELEASE_CHANNEL.generated.json"
            source_manifest = json.loads(fixture.manifest_path.read_text(encoding="utf-8"))
            for artifact in source_manifest.get("artifacts") or []:
                if str(artifact.get("artifactId") or "") != "avalonia-linux-x64-installer":
                    continue
                artifact["sha256"] = fresh_linux_sha
                artifact["sizeBytes"] = fresh_linux_size
            source_manifest_path.write_text(json.dumps(source_manifest, indent=2) + "\n", encoding="utf-8")

            env = materializer_fixture_env(fixture)
            env["CHUMMER_RUNSERVICES_SOURCE_FILES_ROOT"] = str(stale_runservices_root)
            env["CHUMMER_PRESENTATION_FILES_ROOT"] = str(fresh_presentation_root)
            env["CHUMMER_PUBLIC_RELEASE_CHANNEL_SOURCE"] = str(source_manifest_path)

            completed = run_materializer(output_root, env)
            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)

            manifest = json.loads((output_root / "RELEASE_CHANNEL.generated.json").read_text(encoding="utf-8"))
            linux_installer = next(
                (item for item in manifest.get("artifacts") or [] if str(item.get("artifactId") or "") == "avalonia-linux-x64-installer"),
                None,
            )
            self.assertIsNotNone(linux_installer, "expected a published Linux installer row")
            self.assertEqual(
                linux_installer.get("sha256"),
                fresh_linux_sha,
                "materializer must let the later presentation source replace stale earlier run-services bytes",
            )
            self.assertEqual(
                int(linux_installer.get("sizeBytes") or 0),
                fresh_linux_size,
                "materializer must keep the presentation Linux installer size when run-services holds stale bytes",
            )

    def test_materializer_can_force_account_required_downloads(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-public-downloads-bundle-auth-") as temp_root:
            temp_path = Path(temp_root)
            fixture = write_public_downloads_fixture(temp_path)
            output_root = temp_path / "downloads"
            env = materializer_fixture_env(fixture)
            env["CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS"] = "true"

            completed = run_materializer(output_root, env)
            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)

            releases_payload = json.loads((output_root / "releases.json").read_text(encoding="utf-8"))
            downloads = releases_payload.get("downloads") or []
            self.assertGreater(len(downloads), 0, "forced-auth bundle should still publish downloadable rows")
            for download in downloads:
                self.assertEqual(
                    download.get("installAccessClass"),
                    "account_required",
                    "forced-auth bundle should mark every published download row as account_required",
                )

            canonical_payload = json.loads((output_root / "RELEASE_CHANNEL.generated.json").read_text(encoding="utf-8"))
            artifacts = canonical_payload.get("artifacts") or []
            self.assertGreater(len(artifacts), 0, "forced-auth canonical bundle should still publish artifact rows")
            for artifact in artifacts:
                self.assertEqual(
                    artifact.get("installAccessClass"),
                    "account_required",
                    "forced-auth canonical bundle should mark every published artifact row as account_required",
                )

    def test_materializer_syncs_authoritative_registry_manifests_from_generated_truth(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-public-downloads-bundle-authoritative-") as temp_root:
            temp_path = Path(temp_root)
            fixture = write_public_downloads_fixture(temp_path)
            output_root = temp_path / "downloads"
            authoritative_root = temp_path / "authoritative-published"
            authoritative_root.mkdir(parents=True, exist_ok=True)
            stale_bytes = b'{"version":"stale"}\n'
            (authoritative_root / "RELEASE_CHANNEL.generated.json").write_bytes(stale_bytes)
            (authoritative_root / "releases.json").write_bytes(stale_bytes)

            env = materializer_fixture_env(fixture)
            env["CHUMMER_PUBLIC_AUTHORITATIVE_PUBLISHED_ROOT"] = str(authoritative_root)

            completed = run_materializer(output_root, env)
            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)

            for name in ("RELEASE_CHANNEL.generated.json", "releases.json"):
                output_bytes = (output_root / name).read_bytes()
                authoritative_bytes = (authoritative_root / name).read_bytes()
                self.assertEqual(
                    output_bytes,
                    authoritative_bytes,
                    f"authoritative published manifest {name} must match the freshly generated bundle truth",
                )
                self.assertNotEqual(
                    stale_bytes,
                    authoritative_bytes,
                    f"authoritative published manifest {name} must not retain stale pre-run content",
                )

    def test_materializer_rolls_back_all_authoritative_paths_when_publication_fails(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-public-downloads-bundle-rollback-") as temp_root:
            temp_path = Path(temp_root)
            fixture = write_public_downloads_fixture(temp_path)
            output_root = temp_path / "downloads"
            authoritative_root = fixture.authoritative_root
            old_canonical = b'{"version":"old-canonical"}\n'
            old_compatibility = b'{"version":"old-compatibility"}\n'
            old_receipt = b'{"version":"old-startup"}\n'
            (authoritative_root / "RELEASE_CHANNEL.generated.json").write_bytes(old_canonical)
            (authoritative_root / "releases.json").write_bytes(old_compatibility)
            old_startup_root = authoritative_root / "startup-smoke"
            old_startup_root.mkdir(parents=True)
            (old_startup_root / "old.receipt.json").write_bytes(old_receipt)

            env = materializer_fixture_env(fixture)
            env["CHUMMER_PUBLIC_AUTHORITATIVE_PUBLISH_TEST_FAIL_AFTER"] = "releases.json"

            completed = run_materializer(output_root, env)

            self.assertNotEqual(completed.returncode, 0, msg=completed.stdout)
            self.assertIn("injected authoritative publication failure", completed.stderr or completed.stdout)
            self.assertEqual(
                (authoritative_root / "RELEASE_CHANNEL.generated.json").read_bytes(),
                old_canonical,
            )
            self.assertEqual((authoritative_root / "releases.json").read_bytes(), old_compatibility)
            self.assertEqual(
                (authoritative_root / "startup-smoke" / "old.receipt.json").read_bytes(),
                old_receipt,
            )
            self.assertEqual(
                list(authoritative_root.glob(".release-publication-transaction-*")),
                [],
            )

    def test_materializer_recovers_abandoned_authoritative_publication_before_retry(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-public-downloads-bundle-recovery-") as temp_root:
            temp_path = Path(temp_root)
            fixture = write_public_downloads_fixture(temp_path)
            output_root = temp_path / "downloads"
            authoritative_root = fixture.authoritative_root
            old_canonical = b'{"version":"old-canonical"}\n'
            old_compatibility = b'{"version":"old-compatibility"}\n'
            old_receipt = b'{"version":"old-startup"}\n'
            new_receipt = b'{"version":"interrupted-startup"}\n'
            (authoritative_root / "RELEASE_CHANNEL.generated.json").write_bytes(old_canonical)
            (authoritative_root / "releases.json").write_bytes(old_compatibility)
            current_startup_root = authoritative_root / "startup-smoke"
            current_startup_root.mkdir(parents=True)
            (current_startup_root / "new.receipt.json").write_bytes(new_receipt)

            abandoned_root = authoritative_root / ".release-publication-transaction-abandoned"
            backup_startup_root = abandoned_root / "backup" / "startup-smoke"
            backup_startup_root.mkdir(parents=True)
            (backup_startup_root / "old.receipt.json").write_bytes(old_receipt)
            write_json(
                abandoned_root / "state.json",
                {
                    "schemaVersion": "chummer.authoritative-release-publication-transaction/v1",
                    "status": "activating",
                    "touched": ["startup-smoke"],
                    "hadOriginal": {"startup-smoke": True},
                },
            )

            env = materializer_fixture_env(fixture)
            env["CHUMMER_PUBLIC_AUTHORITATIVE_PUBLISH_TEST_FAIL_AFTER"] = "startup-smoke"

            completed = run_materializer(output_root, env)

            self.assertNotEqual(completed.returncode, 0, msg=completed.stdout)
            self.assertIn("injected authoritative publication failure", completed.stderr or completed.stdout)
            self.assertEqual(
                (authoritative_root / "RELEASE_CHANNEL.generated.json").read_bytes(),
                old_canonical,
            )
            self.assertEqual((authoritative_root / "releases.json").read_bytes(), old_compatibility)
            self.assertEqual(
                (authoritative_root / "startup-smoke" / "old.receipt.json").read_bytes(),
                old_receipt,
            )
            self.assertFalse((authoritative_root / "startup-smoke" / "new.receipt.json").exists())
            self.assertEqual(
                list(authoritative_root.glob(".release-publication-transaction-*")),
                [],
            )

    def test_materializer_discards_abandoned_preparation_and_cleans_preactivation_failure(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-public-downloads-bundle-preparation-") as temp_root:
            temp_path = Path(temp_root)
            fixture = write_public_downloads_fixture(temp_path)
            output_root = temp_path / "downloads"
            authoritative_root = fixture.authoritative_root
            old_canonical = b'{"version":"old-canonical"}\n'
            old_compatibility = b'{"version":"old-compatibility"}\n'
            old_receipt = b'{"version":"old-startup"}\n'
            (authoritative_root / "RELEASE_CHANNEL.generated.json").write_bytes(old_canonical)
            (authoritative_root / "releases.json").write_bytes(old_compatibility)
            old_startup_root = authoritative_root / "startup-smoke"
            old_startup_root.mkdir(parents=True)
            (old_startup_root / "old.receipt.json").write_bytes(old_receipt)

            abandoned_preparing_root = authoritative_root / ".release-publication-preparing-abandoned"
            abandoned_preparing_root.mkdir()
            (abandoned_preparing_root / "partial-copy").write_bytes(b"interrupted before journal\n")
            abandoned_tombstone_root = authoritative_root / ".release-publication-tombstone-abandoned"
            abandoned_tombstone_root.mkdir()
            (abandoned_tombstone_root / "partial-cleanup").write_bytes(b"committed transaction cleanup\n")

            env = materializer_fixture_env(fixture)
            env["CHUMMER_PUBLIC_AUTHORITATIVE_PUBLISH_TEST_FAIL_AFTER"] = "preactivation"

            completed = run_materializer(output_root, env)

            self.assertNotEqual(completed.returncode, 0, msg=completed.stdout)
            self.assertIn("injected authoritative publication failure before activation", completed.stderr or completed.stdout)
            self.assertEqual(
                (authoritative_root / "RELEASE_CHANNEL.generated.json").read_bytes(),
                old_canonical,
            )
            self.assertEqual((authoritative_root / "releases.json").read_bytes(), old_compatibility)
            self.assertEqual(
                (authoritative_root / "startup-smoke" / "old.receipt.json").read_bytes(),
                old_receipt,
            )
            self.assertEqual(
                list(authoritative_root.glob(".release-publication-preparing-*")),
                [],
            )
            self.assertEqual(
                list(authoritative_root.glob(".release-publication-transaction-*")),
                [],
            )
            self.assertEqual(
                list(authoritative_root.glob(".release-publication-tombstone-*")),
                [],
            )

    def test_materializer_discards_journalless_tombstone_after_interrupted_cleanup(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-public-downloads-bundle-tombstone-") as temp_root:
            temp_path = Path(temp_root)
            fixture = write_public_downloads_fixture(temp_path)
            output_root = temp_path / "downloads"
            authoritative_root = fixture.authoritative_root
            abandoned_tombstone_root = authoritative_root / ".release-publication-tombstone-abandoned"
            abandoned_tombstone_root.mkdir()
            (abandoned_tombstone_root / "state-was-already-deleted").write_bytes(
                b"interrupted recursive cleanup\n"
            )

            completed = run_materializer(output_root, materializer_fixture_env(fixture))

            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)
            self.assertEqual(
                (authoritative_root / "RELEASE_CHANNEL.generated.json").read_bytes(),
                (output_root / "RELEASE_CHANNEL.generated.json").read_bytes(),
            )
            self.assertEqual(
                list(authoritative_root.glob(".release-publication-tombstone-*")),
                [],
            )

    def test_materializer_hydrates_missing_manifest_artifacts_from_registry_fallback(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-public-downloads-bundle-hydration-") as temp_root:
            temp_path = Path(temp_root)
            fixture = write_public_downloads_fixture(temp_path)
            output_root = temp_path / "downloads"
            empty_runservices_root = temp_path / "empty-runservices-files"
            empty_presentation_root = temp_path / "empty-presentation-files"
            empty_runservices_root.mkdir()
            empty_presentation_root.mkdir()
            copy_fixture_files(fixture.files_root, fixture.registry_files_root)

            env = materializer_fixture_env(fixture)
            env["CHUMMER_RUNSERVICES_SOURCE_FILES_ROOT"] = str(empty_runservices_root)
            env["CHUMMER_PRESENTATION_FILES_ROOT"] = str(empty_presentation_root)

            completed = run_materializer(output_root, env)
            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)

            for row in (fixture.linux_row, fixture.windows_row, fixture.macos_row):
                artifact_path = output_root / "files" / str(row["fileName"])
                self.assertTrue(artifact_path.is_file(), f"missing hydrated artifact: {artifact_path}")
                self.assertEqual(sha256_file(artifact_path), str(row["sha256"]))
            payload_name = str(fixture.windows_row["payloadFileName"])
            self.assertTrue((output_root / "files" / payload_name).is_file())
            self.assertTrue((output_root / "files" / f"{payload_name}.json").is_file())

    def test_materializer_syncs_authoritative_startup_smoke_as_exact_directory_truth(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-public-downloads-bundle-startup-authority-") as temp_root:
            temp_path = Path(temp_root)
            fixture = write_public_downloads_fixture(temp_path)
            output_root = temp_path / "downloads"
            authoritative_startup_root = fixture.authoritative_root / "startup-smoke"
            authoritative_startup_root.mkdir(parents=True)
            (authoritative_startup_root / "stale.receipt.json").write_text("{}\n", encoding="utf-8")

            completed = run_materializer(output_root, materializer_fixture_env(fixture))
            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)

            output_startup_root = output_root / "startup-smoke"
            output_files = {
                path.relative_to(output_startup_root): path.read_bytes()
                for path in output_startup_root.rglob("*")
                if path.is_file()
            }
            authoritative_files = {
                path.relative_to(authoritative_startup_root): path.read_bytes()
                for path in authoritative_startup_root.rglob("*")
                if path.is_file()
            }
            self.assertEqual(authoritative_files, output_files)
            self.assertNotIn(Path("stale.receipt.json"), authoritative_files)

    def test_materializer_declares_authoritative_registry_startup_smoke_sync(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        script_text = MATERIALIZER.read_text(encoding="utf-8")

        self.assertIn("sync_authoritative_publication_with_rollback() {", script_text)
        self.assertIn(
            'publication_order = (\n    "startup-smoke",\n    "releases.json",\n    "RELEASE_CHANNEL.generated.json",\n)',
            script_text,
        )
        self.assertIn('sync_authoritative_publication_with_rollback "$OUTPUT_ROOT"', script_text)
