from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER = REPO_ROOT / "scripts" / "materialize-public-downloads-bundle.sh"


class PublicDownloadsBundleTests(unittest.TestCase):
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
            downloads = releases_payload.get("downloads") or []
            linux_installer = next(
                (item for item in downloads if str(item.get("id") or "") == "blazor-desktop-linux-x64-installer"),
                None,
            )
            if linux_installer is not None:
                self.assertEqual(
                    linux_installer.get("installAccessClass"),
                    "open_public",
                    "published Linux installer rows must stay publicly downloadable when they are present",
                )

            windows_installer = next(
                (item for item in downloads if str(item.get("id") or "") == "avalonia-win-x64-installer"),
                None,
            )
            if windows_installer is not None:
                self.assertEqual(
                    windows_installer.get("installAccessClass"),
                    "open_public",
                    "published Windows installer rows must stay publicly downloadable when they are present",
                )

            startup_root = output_root / "startup-smoke"
            receipt_path = startup_root / "startup-smoke-blazor-desktop-linux-x64.receipt.json"
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
