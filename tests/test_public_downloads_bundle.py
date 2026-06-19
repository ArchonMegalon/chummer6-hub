from __future__ import annotations

import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER = REPO_ROOT / "scripts" / "materialize-public-downloads-bundle.sh"
AUR_MATERIALIZER = REPO_ROOT / "scripts" / "materialize-aur-package.py"


class PublicDownloadsBundleTests(unittest.TestCase):
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

    def test_materializer_publishes_linux_startup_smoke_with_stable_companion_evidence(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-public-downloads-bundle-") as temp_root:
            output_root = Path(temp_root) / "downloads"
            env = os.environ.copy()
            env.setdefault("CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER", "true")

            completed = subprocess.run(
                ["bash", str(MATERIALIZER), str(output_root)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, msg=completed.stderr or completed.stdout)

            releases_payload = json.loads((output_root / "releases.json").read_text(encoding="utf-8"))
            aur_catalog_path = output_root / "aur-packages.json"
            if (output_root / "files" / "chummer-avalonia-linux-x64-installer.deb").is_file():
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
            if linux_installer is not None:
                self.assertEqual(
                    linux_installer.get("installAccessClass"),
                    "open_public",
                    "materialized Linux installer rows must match the current public-edge guest-readable install posture",
                )

            windows_installer = next(
                (item for item in downloads if str(item.get("id") or "") == "avalonia-win-x64-installer"),
                None,
            )
            if windows_installer is not None:
                self.assertEqual(
                    windows_installer.get("installAccessClass"),
                    "open_public",
                    "materialized Windows installer rows must match the current public-edge guest-readable install posture",
                )

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

    def test_materializer_drops_stale_source_artifacts_not_present_in_manifest_truth(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-public-downloads-bundle-stale-") as temp_root:
            output_root = Path(temp_root) / "downloads"
            stale_root = Path(temp_root) / "stale-files"
            stale_root.mkdir(parents=True, exist_ok=True)
            (stale_root / "chummer-blazor-desktop-linux-x64-installer.deb").write_bytes(b"stale-extra-artifact")

            env = os.environ.copy()
            env.setdefault("CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER", "true")
            env["CHUMMER_RUNSERVICES_SOURCE_FILES_ROOT"] = str(stale_root)

            completed = subprocess.run(
                ["bash", str(MATERIALIZER), str(output_root)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
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
            output_root = Path(temp_root) / "downloads"
            stale_root = Path(temp_root) / "stale-files"
            stale_root.mkdir(parents=True, exist_ok=True)
            stale_file = stale_root / "chummer-blazor-desktop-osx-arm64-installer.dmg"
            stale_file.write_bytes(b"stale-extra-macos-installer")

            env = os.environ.copy()
            env.setdefault("CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER", "true")
            env["CHUMMER_RUNSERVICES_SOURCE_FILES_ROOT"] = str(stale_root)

            completed = subprocess.run(
                ["bash", str(MATERIALIZER), str(output_root)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
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

    def test_materializer_can_force_account_required_downloads(self):
        if not MATERIALIZER.exists():
            self.skipTest(f"missing public downloads materializer: {MATERIALIZER}")

        with tempfile.TemporaryDirectory(prefix="chummer-public-downloads-bundle-auth-") as temp_root:
            output_root = Path(temp_root) / "downloads"
            env = os.environ.copy()
            env.setdefault("CHUMMER_PUBLIC_SKIP_STARTUP_SMOKE_FILTER", "true")
            env["CHUMMER_PUBLIC_FORCE_ACCOUNT_REQUIRED_DOWNLOADS"] = "true"

            completed = subprocess.run(
                ["bash", str(MATERIALIZER), str(output_root)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
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
