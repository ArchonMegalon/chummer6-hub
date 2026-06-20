import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/verify_windows_installer_visual_audit.py")
IMPORT_SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/import_windows_installer_gold_proof_artifact.py")


def load_module():
    spec = importlib.util.spec_from_file_location("verify_windows_installer_visual_audit", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_import_module():
    spec = importlib.util.spec_from_file_location("import_windows_installer_gold_proof_artifact", IMPORT_SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WindowsInstallerVisualAuditTests(unittest.TestCase):
    def _write_release_fixture(self, root: Path) -> tuple[Path, Path, str]:
        downloads_root = root / "downloads"
        files_root = downloads_root / "files"
        files_root.mkdir(parents=True)
        artifact = files_root / "chummer-avalonia-win-x64-installer.exe"
        artifact.write_bytes(b"windows installer bytes")
        sha = load_module().sha256_file(artifact)
        release_channel = downloads_root / "RELEASE_CHANNEL.generated.json"
        release_channel.write_text(
            json.dumps(
                {
                    "version": "run-test",
                    "channelId": "preview",
                    "artifacts": [
                        {
                            "artifactId": "avalonia-win-x64-installer",
                            "fileName": artifact.name,
                            "platform": "windows",
                            "kind": "installer",
                            "sha256": sha,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return downloads_root, release_channel, sha

    def test_incompatible_host_startup_receipt_blocks_visual_gold(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps(
                    {
                        "status": "skipped",
                        "verificationDisposition": "incompatible_host",
                        "skipClass": "incompatible_host",
                        "artifactDigest": f"sha256:{sha}",
                    }
                ),
                encoding="utf-8",
            )
            payload = module.build_payload(
                release_channel_path=release_channel,
                downloads_root=downloads_root,
                startup_receipt_path=startup,
                source_path=downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
            )

        self.assertEqual("fail", payload["status"])
        self.assertIn("Windows startup receipt is an incompatible-host skip, not native proof", payload["failures"])
        self.assertIn("Windows installer visual audit source is missing", " ".join(payload["failures"]))
        self.assertIn("nextActions", payload)
        self.assertTrue(any("capture_windows_installer_visual_audit.ps1" in item for item in payload["nextActions"]))
        self.assertTrue(any("capture_windows_installer_gold_proof.ps1" in item for item in payload["nextActions"]))
        self.assertTrue(any("-CaptureRequiredSet" in item for item in payload["nextActions"]))
        self.assertTrue(any("import_windows_installer_gold_proof_artifact.py" in item for item in payload["nextActions"]))
        self.assertTrue(any("Windows Installer Gold Proof" in item for item in payload["nextActions"]))
        self.assertTrue(any("windows-installer-gold-proof.yml" in item for item in payload["nextActions"]))
        self.assertTrue(any("does not publish downloads" in item for item in payload["nextActions"]))
        self.assertTrue(any("byte-identical" in item for item in payload["nextActions"]))
        self.assertTrue(any("native Windows pass" in item for item in payload["nextActions"]))

    def test_native_startup_with_only_completion_screenshots_still_fails(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-pass-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "artifactDigest": f"sha256:{sha}",
                    }
                ),
                encoding="utf-8",
            )
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True)
            (source.parent / "default.png").write_bytes(b"png")
            (source.parent / "scaled.png").write_bytes(b"png")
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": sha,
                        "screenshots": [
                            {
                                "path": "default.png",
                                "dpiScale": 1.0,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "scaled.png",
                                "dpiScale": 1.5,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            payload = module.build_payload(
                release_channel_path=release_channel,
                downloads_root=downloads_root,
                startup_receipt_path=startup,
                source_path=source,
            )

        self.assertEqual("fail", payload["status"])
        self.assertIn("Windows installer visual audit has no install-progress screenshot", payload["failures"])

    def test_native_startup_and_required_surface_dpi_screenshots_pass(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-pass-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "artifactDigest": f"sha256:{sha}",
                    }
                ),
                encoding="utf-8",
            )
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True)
            for index, name in enumerate(["progress-default.png", "progress-scaled.png", "completion-default.png", "completion-scaled.png"]):
                (source.parent / name).write_bytes(f"png-{index}".encode("utf-8"))
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": sha,
                        "screenshots": [
                            {
                                "path": "progress-default.png",
                                "dpiScale": 1.0,
                                "surface": "install-progress",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "progress-scaled.png",
                                "dpiScale": 1.5,
                                "surface": "install-progress",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "completion-default.png",
                                "dpiScale": 1.0,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "completion-scaled.png",
                                "dpiScale": 1.5,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            payload = module.build_payload(
                release_channel_path=release_channel,
                downloads_root=downloads_root,
                startup_receipt_path=startup,
                source_path=source,
            )

        self.assertEqual("pass", payload["status"])
        self.assertEqual([], payload["failures"])
        self.assertEqual([], payload["nextActions"])
        self.assertEqual(["install-progress", "completion"], payload["visualAuditSource"]["requiredSurfaces"])
        self.assertTrue(all(row["sha256"] for row in payload["screenshots"]))

    def test_distinct_required_surfaces_must_not_be_byte_identical(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-identical-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "artifactDigest": f"sha256:{sha}",
                    }
                ),
                encoding="utf-8",
            )
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True)
            for name in ["progress-default.png", "completion-default.png"]:
                (source.parent / name).write_bytes(b"same screenshot")
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": sha,
                        "screenshots": [
                            {
                                "path": "progress-default.png",
                                "dpiScale": 1.0,
                                "surface": "install-progress",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "completion-default.png",
                                "dpiScale": 1.5,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            payload = module.build_payload(
                release_channel_path=release_channel,
                downloads_root=downloads_root,
                startup_receipt_path=startup,
                source_path=source,
            )

        self.assertEqual("fail", payload["status"])
        self.assertTrue(
            any("distinct required surfaces are byte-identical" in item for item in payload["failures"])
        )

    def test_windows_capture_helper_updates_source_receipt_without_manual_json_editing(self) -> None:
        script = Path("/docker/chummercomplete/chummer.run-services/scripts/capture_windows_installer_visual_audit.ps1")
        text = script.read_text(encoding="utf-8")

        self.assertIn("WINDOWS_INSTALLER_VISUAL_AUDIT.source.json", text)
        self.assertIn("CopyFromScreen", text)
        self.assertIn("artifactSha256", text)
        self.assertIn("review_required", text)
        self.assertIn("Get-FileHash", text)
        self.assertIn("$normalized = @{}", text)
        self.assertIn("function Test-MapHasKey", text)
        self.assertIn("Get-MapValue $source \"screenshots\"", text)
        self.assertIn('ValidateSet("install-progress", "completion")', text)
        self.assertIn('"install-progress", "completion"', text)
        self.assertIn("[switch]$CaptureRequiredSet", text)
        self.assertIn("$ScaledDpiScale", text)
        self.assertLess(
            text.index('[ordered]@{ Surface = "install-progress"; DpiScale = $ScaledDpiScale }'),
            text.index('[ordered]@{ Surface = "completion"; DpiScale = "1.0" }'),
        )
        self.assertIn("foreach ($request in $captureRequests)", text)
        self.assertIn("function Wait-ForInstallerSurface", text)
        self.assertIn("Find-InstallerSurfaceWindow", text)
        self.assertIn("MainWindowTitle", text)
        self.assertIn('$title.IndexOf("Install Complete"', text)
        self.assertIn('$title.IndexOf("Installer"', text)
        self.assertIn("function Get-CaptureBounds", text)
        self.assertIn("GetWindowRect", text)
        self.assertIn("SetForegroundWindow", text)
        self.assertIn("window-bounds", text)
        self.assertIn("captureBounds", text)
        self.assertIn("Launching installer for visual capture", text)
        self.assertLess(text.index('Add-Type @"'), text.index("Launching installer for visual capture"))
        self.assertLess(text.index("Launching installer for visual capture"), text.index("foreach ($request in $captureRequests)"))
        self.assertIn("Timed out waiting for Chummer installer surface", text)
        self.assertIn("$AutoCaptureTimeoutSeconds", text)
        self.assertIn("$delaySeconds = 0", text)
        self.assertIn("$delaySeconds = [Math]::Max($delaySeconds, 8)", text)
        self.assertIn("surfaceCoverage", text)

    def test_windows_gold_proof_helper_writes_startup_receipt_and_delegates_visual_capture(self) -> None:
        script = Path("/docker/chummercomplete/chummer.run-services/scripts/capture_windows_installer_gold_proof.ps1")
        text = script.read_text(encoding="utf-8")

        self.assertIn("startup-smoke-$HeadId-$Rid.receipt.json", text)
        self.assertIn('status = "pass"', text)
        self.assertIn('readyCheckpoint = "pre_ui_event_loop"', text)
        self.assertIn('hostClass = "native-windows"', text)
        self.assertIn('artifactDigest = "sha256:$artifactHash"', text)
        self.assertIn("if ($LaunchInstaller -and -not $CaptureVisualAudit)", text)
        self.assertIn("elseif ($LaunchInstaller)", text)
        self.assertIn("capture_windows_installer_visual_audit.ps1", text)
        self.assertIn("$normalized = @{}", text)
        self.assertIn("function Test-MapHasKey", text)
        self.assertIn("Get-MapValue $releaseChannel \"version\"", text)
        self.assertIn("$captureArgs = @{", text)
        self.assertIn("CaptureRequiredSet = $true", text)
        self.assertIn('$captureArgs["AutoCapture"] = $true', text)
        self.assertIn("ClippingStatus = $VisualClippingStatus", text)
        self.assertIn("ReadabilityStatus = $VisualReadabilityStatus", text)
        self.assertIn("$AutoCaptureVisualAudit", text)
        self.assertIn('$captureArgs["AutoCaptureDelaySeconds"] = $AutoCaptureDelaySeconds', text)
        self.assertIn('$captureArgs["AutoCaptureTimeoutSeconds"] = $AutoCaptureTimeoutSeconds', text)
        self.assertIn('$captureArgs["LaunchInstaller"] = $true', text)

    def test_windows_installer_gold_proof_workflow_is_manual_non_publishing_and_native_capture_bounded(self) -> None:
        workflow = Path("/docker/chummercomplete/chummer.run-services/.github/workflows/windows-installer-gold-proof.yml")
        text = workflow.read_text(encoding="utf-8")

        self.assertIn("workflow_dispatch:", text)
        self.assertNotIn("push:", text)
        self.assertNotIn("schedule:", text)
        self.assertIn("runs-on: windows-2025-vs2026", text)
        self.assertIn("capture_windows_installer_gold_proof.ps1", text)
        self.assertIn("Ensure installer artifact", text)
        self.assertIn("RELEASE_CHANNEL.generated.json", text)
        self.assertIn("avalonia-win-x64-installer", text)
        self.assertIn("https://chummer.run/downloads/files/chummer-avalonia-win-x64-installer.exe", text)
        self.assertIn("Invoke-WebRequest -Uri $installerUrl", text)
        self.assertIn("$proofArgs = @{", text)
        self.assertIn('$proofArgs["VisualClippingStatus"] = "pass"', text)
        self.assertIn('$proofArgs["VisualReadabilityStatus"] = "pass"', text)
        self.assertIn("auto_capture_timeout_seconds", text)
        self.assertIn('$proofArgs["AutoCaptureTimeoutSeconds"]', text)
        self.assertIn("does not publish downloads", text)
        self.assertIn("native window-bounds screenshots", text)
        self.assertIn("byte-identical", text)
        self.assertIn("actions/upload-artifact", text)
        self.assertIn("import_windows_installer_gold_proof_artifact.py", text)
        self.assertNotIn("deploy_portal_downloads", text)

    def test_import_windows_installer_gold_proof_artifact_copies_expected_receipts_and_screenshots(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            startup_root = artifact / "Chummer.Portal" / "downloads" / "startup-smoke"
            visual_root.mkdir(parents=True)
            startup_root.mkdir(parents=True)
            (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
                json.dumps({"status": "pass", "artifactDigest": "sha256:test"}),
                encoding="utf-8",
            )
            for name in ["progress-default.png", "progress-scaled.png", "completion-default.png", "completion-scaled.png"]:
                (visual_root / name).write_bytes(b"png")
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "screenshots": [
                            {"path": "progress-default.png"},
                            {"path": "progress-scaled.png"},
                            {"path": "completion-default.png"},
                            {"path": "completion-scaled.png"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            downloads_root = root / "downloads"
            summary = module.import_artifact(artifact, downloads_root)

            self.assertTrue((downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json").is_file())
            self.assertTrue((downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").is_file())
            self.assertEqual(4, len(summary["screenshots"]))
            self.assertTrue((downloads_root / "visual-audit" / "windows-installer" / "completion-scaled.png").is_file())

    def test_import_windows_installer_gold_proof_artifact_rejects_unsafe_zip_members(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-zip-") as temp_dir:
            root = Path(temp_dir)
            zip_path = root / "artifact.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("../escape.txt", "bad")

            with self.assertRaises(SystemExit):
                module.extracted_or_directory(zip_path, root / "extract")

    def test_downloads_runbook_documents_windows_gold_proof_loop(self) -> None:
        runbook = Path("/docker/chummercomplete/chummer.run-services/docs/SELF_HOSTED_DOWNLOADS_RUNBOOK.md")
        text = runbook.read_text(encoding="utf-8")

        self.assertIn("Windows installer gold proof", text)
        self.assertIn("Windows Installer Gold Proof", text)
        self.assertIn(".github/workflows/windows-installer-gold-proof.yml", text)
        self.assertIn("must not publish downloads", text)
        self.assertIn("windows-installer-gold-proof.zip --verify", text)
        self.assertIn("review_required", text)
        self.assertIn("capture_windows_installer_gold_proof.ps1 -LaunchInstaller -CaptureVisualAudit", text)
        self.assertIn("verify_windows_installer_visual_audit.py", text)
