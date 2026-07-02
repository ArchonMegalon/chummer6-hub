import importlib.util
import json
import tempfile
import unittest
import unittest.mock
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_windows_installer_visual_audit.py"
IMPORT_SCRIPT_PATH = REPO_ROOT / "scripts" / "import_windows_installer_gold_proof_artifact.py"
INTAKE_SCRIPT_PATH = REPO_ROOT / "scripts" / "materialize_windows_installer_visual_audit_intake_request.py"


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


def load_intake_module():
    spec = importlib.util.spec_from_file_location("materialize_windows_installer_visual_audit_intake_request", INTAKE_SCRIPT_PATH)
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
        self.assertTrue(any("native Windows proof runner" in item for item in payload["nextActions"]))
        self.assertTrue(any("does not publish downloads" in item for item in payload["nextActions"]))
        self.assertTrue(any("byte-identical" in item for item in payload["nextActions"]))
        self.assertTrue(any("native Windows pass" in item for item in payload["nextActions"]))

    def test_default_downloads_root_can_fall_back_to_published_artifact_shelf(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-default-root-") as temp_dir:
            root = Path(temp_dir)
            source_checkout = root / "source" / "Chummer.Portal" / "downloads"
            deploy_checkout = root / "chummer.run-services" / "Chummer.Portal" / "downloads"
            source_checkout.mkdir(parents=True)
            deploy_checkout.mkdir(parents=True)
            (source_checkout / "RELEASE_CHANNEL.generated.json").write_text(
                json.dumps({"version": "run-test", "artifacts": []}),
                encoding="utf-8",
            )
            downloads_root, _, _ = self._write_release_fixture(root / "chummer.run-services" / "Chummer.Portal")

            with unittest.mock.patch.object(module, "ROOT", root / "source"):
                self.assertEqual(downloads_root, module.resolve_default_downloads_root())

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

    def test_automated_full_desktop_capture_bounds_block_visual_gold(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-bounds-") as temp_dir:
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
                                "captureMode": "window-bounds",
                                "captureBounds": {"left": 180, "top": 200, "width": 656, "height": 319},
                            },
                            {
                                "path": "progress-scaled.png",
                                "dpiScale": 1.5,
                                "surface": "install-progress",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                                "captureMode": "window-bounds",
                                "captureBounds": {"left": 180, "top": 200, "width": 656, "height": 319},
                            },
                            {
                                "path": "completion-default.png",
                                "dpiScale": 1.0,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                                "captureMode": "window-bounds",
                                "captureBounds": {"left": 0, "top": 0, "width": 1024, "height": 768},
                            },
                            {
                                "path": "completion-scaled.png",
                                "dpiScale": 1.5,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                                "captureMode": "reused-same-surface",
                                "captureBounds": {"left": 0, "top": 0, "width": 1024, "height": 768},
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
            any("used full-desktop fallback bounds" in item for item in payload["failures"])
        )

    def test_windows_capture_helper_updates_source_receipt_without_manual_json_editing(self) -> None:
        script = REPO_ROOT / "scripts" / "capture_windows_installer_visual_audit.ps1"
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
        self.assertIn("function Test-CaptureBoundsLookLikeDesktopFallback", text)
        self.assertIn("function Test-CaptureBoundsMapLookLikeDesktopFallback", text)
        self.assertIn("Test-CaptureBoundsLookLikeDesktopFallback $bounds", text)
        self.assertIn("Test-CaptureBoundsMapLookLikeDesktopFallback $item.captureBounds", text)
        self.assertIn("$surfacesByHash", text)
        self.assertIn("[System.Collections.Generic.HashSet[string]]::new()", text)
        self.assertIn('"install-progress", "completion"', text)
        self.assertIn("[switch]$CaptureRequiredSet", text)
        self.assertIn("$ScaledDpiScale", text)
        self.assertLess(
            text.index('[ordered]@{ Surface = "install-progress"; DpiScale = $ScaledDpiScale }'),
            text.index('[ordered]@{ Surface = "completion"; DpiScale = "1.0" }'),
        )
        self.assertIn("foreach ($request in $captureRequests)", text)
        self.assertIn("function Wait-ForInstallerSurface", text)
        self.assertIn("function New-InstallerSurfaceWindow", text)
        self.assertIn("function Get-VisibleInstallerWindows", text)
        self.assertIn("public static extern bool EnumWindows", text)
        self.assertIn("public static extern bool IsWindowVisible", text)
        self.assertIn("public static extern int GetWindowTextLength", text)
        self.assertIn("public static extern int GetWindowText", text)
        self.assertIn("public static extern uint GetWindowThreadProcessId", text)
        self.assertIn("public static class WindowScanner", text)
        self.assertIn("GetVisibleTopLevelWindows", text)
        self.assertIn("ProcessId = [int]$Window.ProcessId", text)
        self.assertIn("MainWindowHandle = $Window.Handle", text)
        self.assertIn("public static extern bool PostMessage", text)
        self.assertIn("function Close-InstallerSurfaceWindows", text)
        self.assertIn("function Stop-InstallerSurfaceProcesses", text)
        self.assertIn("function Stop-LaunchedInstallerProcess", text)
        self.assertIn("function Write-InstallerCaptureFailure", text)
        self.assertIn("function Get-InstallerTraceCandidates", text)
        self.assertIn("function Get-InstallerProcessSnapshotRows", text)
        self.assertIn("function Invoke-InstallerCaptureCleanup", text)
        self.assertIn("Requested close for installer window", text)
        self.assertIn("WINDOWS_INSTALLER_CAPTURE_FAILURE.txt", text)
        self.assertIn("chummerProcesses:", text)
        self.assertIn("traceCandidates:", text)
        self.assertIn("Get-Content -LiteralPath $candidate -Tail 40", text)
        self.assertIn("Stopped launched installer process", text)
        self.assertIn("Stopped installer window process", text)
        self.assertIn("$script:LaunchedInstallerProcessId = $launchedProcess.Id", text)
        self.assertIn("trap {", text)
        self.assertIn("Invoke-InstallerCaptureCleanup", text)
        self.assertIn("if ($AutoCapture -and $LaunchInstaller)", text)
        self.assertIn("function Find-InstallerSurfaceWindow([string]$SurfaceValue, [bool]$AllowCompletionInstallerFallback = $false)", text)
        self.assertIn("Find-InstallerSurfaceWindow $SurfaceValue $AllowCompletionInstallerFallback", text)
        self.assertIn("$AllowCompletionInstallerFallback -and $title.IndexOf(\"Installer\"", text)
        self.assertIn("handle=$($_.Handle)", text)
        self.assertIn("MainWindowTitle", text)
        self.assertNotIn("Get-Process | Where-Object {\n        -not [string]::IsNullOrWhiteSpace($_.MainWindowTitle)", text)
        self.assertIn('$title.IndexOf("Install Complete"', text)
        self.assertIn('$title.IndexOf("Installer"', text)
        self.assertIn("function Get-CaptureBounds", text)
        self.assertIn("GetWindowRect", text)
        self.assertIn("function Get-AutomationCaptureBounds", text)
        self.assertIn("Add-Type -AssemblyName UIAutomationClient", text)
        self.assertIn("[System.Windows.Automation.AutomationElement]::FromHandle", text)
        self.assertIn("Using UI Automation bounds for installer window after GetWindowRect was unavailable.", text)
        self.assertIn("SetForegroundWindow", text)
        self.assertIn("Automated installer capture refused full-screen fallback", text)
        self.assertIn("expected compact installer window bounds", text)
        self.assertIn("Get-CaptureBounds $window (-not $AutoCapture)", text)
        self.assertIn("window-bounds", text)
        self.assertIn("captureBounds", text)
        self.assertIn("Launching installer for visual capture", text)
        self.assertIn('$isProgressSurface = (Normalize-Surface $captureSurface) -eq "install-progress"', text)
        self.assertIn("Progress surfaces are captured immediately so fast installers cannot close before bounds are read.", text)
        self.assertLess(
            text.index("Progress surfaces are captured immediately"),
            text.index("[void][ChummerInstallerCapture.NativeMethods]::SetForegroundWindow"),
        )
        self.assertLess(text.index('Add-Type @"'), text.index("Launching installer for visual capture"))
        self.assertLess(text.index("Launching installer for visual capture"), text.index("foreach ($request in $captureRequests)"))
        self.assertIn("$previousSameSurfaceRows", text)
        self.assertIn("reused-same-surface", text)
        self.assertIn("reusedFrom", text)
        self.assertIn("Reused previous $captureSurface screenshot after the window closed", text)
        self.assertIn("Reused previous $captureSurface screenshot after the window bounds became unavailable", text)
        self.assertIn("Timed out waiting for Chummer installer surface", text)
        self.assertIn("$AutoCaptureTimeoutSeconds", text)
        self.assertIn("$effectiveAutoCaptureTimeoutSeconds", text)
        self.assertIn("[Math]::Min($AutoCaptureTimeoutSeconds, 90)", text)
        self.assertIn("Auto-capture timeout capped", text)
        self.assertIn("$delaySeconds = 0", text)
        self.assertIn("$delaySeconds = [Math]::Max($delaySeconds, 8)", text)
        self.assertIn('$requiredSurfaces = @("install-progress", "completion")', text)
        self.assertIn("$requiredSurfaces -notcontains (Normalize-Surface $_.surface)", text)
        self.assertIn("surfaceCoverage", text)

    def test_windows_gold_proof_helper_writes_startup_receipt_and_delegates_visual_capture(self) -> None:
        script = REPO_ROOT / "scripts" / "capture_windows_installer_gold_proof.ps1"
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

        self.assertIn("ui_desktop_run_id", text)
        self.assertIn("chummer-avalonia-win-x64-installer.exe", text)
        self.assertIn("RELEASE_CHANNEL.generated.json", text)
        self.assertIn("avalonia-win-x64-installer", text)

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

    def test_import_windows_installer_gold_proof_artifact_rejects_desktop_fallback_bounds_before_copying(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-fallback-") as temp_dir:
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
            (visual_root / "progress.png").write_bytes(b"progress")
            (visual_root / "completion.png").write_bytes(b"completion")
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "screenshots": [
                            {
                                "path": "progress.png",
                                "surface": "install-progress",
                                "captureMode": "window-bounds",
                                "captureBounds": {"left": 184, "top": 200, "width": 656, "height": 319},
                            },
                            {
                                "path": "completion.png",
                                "surface": "completion",
                                "captureMode": "window-bounds",
                                "captureBounds": {"left": 0, "top": 0, "width": 1024, "height": 768},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            downloads_root = root / "downloads"

            with self.assertRaises(SystemExit) as raised:
                module.import_artifact(artifact, downloads_root)

            self.assertIn("full-desktop fallback bounds", str(raised.exception))
            self.assertFalse((downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json").exists())
            self.assertFalse((downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").exists())

    def test_import_windows_installer_gold_proof_artifact_rejects_byte_identical_required_surfaces(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-identical-") as temp_dir:
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
            for name in ["progress.png", "completion.png"]:
                (visual_root / name).write_bytes(b"same installer surface")
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "screenshots": [
                            {
                                "path": "progress.png",
                                "surface": "install-progress",
                                "captureMode": "window-bounds",
                                "captureBounds": {"left": 184, "top": 200, "width": 656, "height": 319},
                            },
                            {
                                "path": "completion.png",
                                "surface": "completion",
                                "captureMode": "window-bounds",
                                "captureBounds": {"left": 184, "top": 200, "width": 656, "height": 319},
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(SystemExit) as raised:
                module.import_artifact(artifact, root / "downloads")

            self.assertIn("byte-identical", str(raised.exception))

    def test_import_windows_installer_gold_proof_artifact_rejects_unsafe_zip_members(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-zip-") as temp_dir:
            root = Path(temp_dir)
            zip_path = root / "artifact.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("../escape.txt", "bad")

            with self.assertRaises(SystemExit):
                module.extracted_or_directory(zip_path, root / "extract")

    def test_materialize_windows_installer_visual_audit_intake_request_keeps_external_blocker_honest(self) -> None:
        intake = load_intake_module()
        verifier = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-visual-intake-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, promoted_sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "artifactDigest": f"sha256:{promoted_sha}",
                    }
                ),
                encoding="utf-8",
            )
            stale_source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            stale_source.parent.mkdir(parents=True)
            (stale_source.parent / "completion.png").write_bytes(b"stale")
            stale_source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": "0" * 64,
                        "screenshots": [
                            {
                                "path": "completion.png",
                                "dpiScale": 1.0,
                                "surface": "completion",
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            drop_root = root / "operator-drop"
            drop_root.mkdir()
            matching_candidate = drop_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            matching_candidate.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": promoted_sha,
                        "screenshots": [],
                    }
                ),
                encoding="utf-8",
            )

            payload = intake.build_request(
                release_channel=release_channel,
                downloads_root=downloads_root,
                startup_receipt=startup,
                source=stale_source,
                discovery_roots=[drop_root],
                nightly_root=root / "missing-nightlies",
            )

        self.assertEqual("external_artifact_required", payload["status"])
        self.assertEqual(promoted_sha, payload["promoted_installer"]["sha256"])
        self.assertFalse(payload["current_blocker"]["current_visual_source_matches_promoted"])
        self.assertIn(
            "Windows installer visual audit source digest does not match promoted installer",
            payload["current_blocker"]["failure"],
        )
        self.assertEqual(1, payload["last_discovery"]["visual_sources"]["matching_promoted_count"])
        self.assertIn("capture_windows_installer_gold_proof.ps1", payload["operator_request"]["powershell_commands"][0])
        self.assertIn("-CaptureVisualAudit", payload["operator_request"]["powershell_commands"][0])
        self.assertIn(promoted_sha[:12], payload["operator_request"]["powershell_commands"][1])
        self.assertEqual(list(verifier.REQUIRED_SURFACES), payload["operator_request"]["required_surfaces"])
        self.assertFalse(payload["direct_telegram_sent"])

    def test_visual_audit_intake_defaults_watch_nightly_staging_root(self) -> None:
        intake = load_intake_module()

        self.assertIn(Path("/docker/chummercomplete/_staging"), intake.DEFAULT_DISCOVERY_ROOTS)

    def test_downloads_runbook_documents_windows_gold_proof_loop(self) -> None:
        runbook = REPO_ROOT / "docs" / "SELF_HOSTED_DOWNLOADS_RUNBOOK.md"
        text = runbook.read_text(encoding="utf-8")

        self.assertIn("Windows installer gold proof", text)
        self.assertIn("native Windows proof runner", text)
        self.assertIn("must not publish downloads", text)
        self.assertIn("windows-installer-gold-proof.zip --verify", text)
        self.assertIn("review_required", text)
        self.assertIn("capture_windows_installer_gold_proof.ps1 -LaunchInstaller -CaptureVisualAudit", text)
        self.assertIn("verify_windows_installer_visual_audit.py", text)
