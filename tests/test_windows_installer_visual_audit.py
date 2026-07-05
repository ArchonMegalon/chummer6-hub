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
AUTO_IMPORT_SCRIPT_PATH = REPO_ROOT / "scripts" / "auto_import_windows_installer_gold_proof.py"
VERIFY_INTAKE_SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_windows_installer_visual_audit_intake_request.py"


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


def load_auto_import_module():
    spec = importlib.util.spec_from_file_location("auto_import_windows_installer_gold_proof", AUTO_IMPORT_SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_verify_intake_module():
    spec = importlib.util.spec_from_file_location(
        "verify_windows_installer_visual_audit_intake_request",
        VERIFY_INTAKE_SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WindowsInstallerVisualAuditTests(unittest.TestCase):
    def test_intake_default_discovery_roots_are_portable(self) -> None:
        intake = load_intake_module()

        self.assertEqual(
            (
                intake.DEFAULT_DEDICATED_DROP_ROOT,
                Path("/tmp"),
            ),
            intake.DEFAULT_DISCOVERY_ROOTS,
        )
        self.assertTrue(all("/home/" not in str(path) for path in intake.DEFAULT_DISCOVERY_ROOTS))

    def test_intake_artifact_discovery_roots_include_common_operator_sync_locations(self) -> None:
        intake = load_intake_module()

        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-roots-") as temp_dir:
            home = Path(temp_dir) / "home"
            dedicated = Path(temp_dir) / "runtime" / "incoming_windows_installer_gold_proof"
            with unittest.mock.patch("pathlib.Path.home", return_value=home):
                roots = intake.artifact_discovery_roots(dedicated)

        self.assertEqual(
            [
                dedicated,
                Path("/tmp"),
                home / "Downloads",
                home / "pCloud Drive" / "EA",
            ],
            roots,
        )

    def test_intake_gitignored_runtime_root_accepts_run_services_and_workspace_state(self) -> None:
        intake = load_intake_module()

        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-gitignored-") as temp_dir:
            runtime_root = Path(temp_dir) / "chummer.run-services"
            workspace_root = runtime_root.parent
            with unittest.mock.patch.object(intake, "ROOT", runtime_root), unittest.mock.patch.object(intake, "WORKSPACE_ROOT", workspace_root):
                self.assertTrue(intake.is_gitignored_runtime_root(runtime_root / ".state" / "incoming"))
                self.assertTrue(intake.is_gitignored_runtime_root(workspace_root / ".state" / "incoming"))
                self.assertFalse(intake.is_gitignored_runtime_root(workspace_root / "Downloads"))

    def test_intake_discover_files_uses_bounded_walk_instead_of_path_rglob(self) -> None:
        intake = load_intake_module()

        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-discovery-") as temp_dir:
            root = Path(temp_dir)
            shallow = root / "incoming" / "windows-installer-gold-proof-deadbeef.zip"
            shallow.parent.mkdir(parents=True)
            shallow.write_bytes(b"shallow")

            deep = root
            for index in range(intake.DISCOVERY_MAX_DEPTH + 2):
                deep = deep / f"deep-{index}"
            deep.mkdir(parents=True)
            too_deep = deep / "windows-installer-gold-proof-too-deep.zip"
            too_deep.write_bytes(b"too-deep")

            with unittest.mock.patch("pathlib.Path.rglob", side_effect=AssertionError("discover_files should not use Path.rglob")):
                discovered = intake.discover_files("*windows-installer-gold-proof*.zip", [root])

        self.assertIn(shallow, discovered)
        self.assertNotIn(too_deep, discovered)

    def test_intake_discover_files_can_skip_recursive_walk_for_broad_roots(self) -> None:
        intake = load_intake_module()

        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-shallow-") as temp_dir:
            root = Path(temp_dir) / "Downloads"
            root.mkdir(parents=True)
            preferred = root / "windows-installer-gold-proof-deadbeef.zip"
            preferred.write_bytes(b"preferred")

            with unittest.mock.patch.object(intake, "walk_candidate_files", side_effect=AssertionError("broad roots should not recurse")):
                discovered = intake.discover_files(
                    "*windows-installer-gold-proof*.zip",
                    [root],
                    recursive_roots=[],
                )

        self.assertEqual([preferred], discovered)

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
        self.assertEqual(
            "Native Windows visual audit still failing: Windows startup receipt is an incompatible-host skip, not native proof",
            payload["summary"],
        )
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
            drop_root = root / ".state" / "incoming_windows_installer_gold_proof"
            drop_root.mkdir(parents=True)
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
                dedicated_drop_root=drop_root,
                auto_import_roots=[drop_root],
                recursive_scan_roots=[drop_root],
            )

        self.assertEqual("external_artifact_required", payload["status"])
        self.assertEqual(str(drop_root / f"windows-installer-gold-proof-{promoted_sha[:12]}.zip"), payload["preferred_drop_path"])
        self.assertEqual(promoted_sha, payload["promoted_installer"]["sha256"])
        self.assertFalse(payload["current_blocker"]["current_visual_source_matches_promoted"])
        self.assertIn(
            "Windows installer visual audit source digest does not match promoted installer",
            payload["current_blocker"]["failure"],
        )
        self.assertEqual(1, payload["last_discovery"]["visual_sources"]["matching_promoted_count"])
        self.assertEqual(str(drop_root), payload["artifact_intake"]["dedicated_drop_root"])
        self.assertIn("auto_import_windows_installer_gold_proof.py", payload["artifact_intake"]["auto_import_watch_command"])
        self.assertIn("CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK", payload["operator_telegram_draft"]["current_message_path"])
        self.assertIn("capture_windows_installer_gold_proof.ps1", payload["operator_request"]["powershell_commands"][0])
        self.assertIn("-CaptureVisualAudit", payload["operator_request"]["powershell_commands"][0])
        self.assertIn(promoted_sha[:12], payload["operator_request"]["powershell_commands"][1])
        self.assertEqual(list(verifier.REQUIRED_SURFACES), payload["operator_request"]["required_surfaces"])
        self.assertFalse(payload["direct_telegram_sent"])

    def test_materialize_windows_installer_visual_audit_operator_telegram_draft_writes_files(self) -> None:
        intake = load_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-draft-") as temp_dir:
            root = Path(temp_dir)
            expected_draft_root = root / "_completion" / "windows_installer_visual_audit"
            original_draft_root = intake.DEFAULT_OPERATOR_DRAFT_ROOT
            intake.DEFAULT_OPERATOR_DRAFT_ROOT = expected_draft_root
            try:
                draft = intake.build_operator_telegram_draft(
                    promoted_digest="deadbeef" * 8,
                    installer_file_name="chummer-avalonia-win-x64-installer.exe",
                    preferred_drop_path=root / "incoming" / "windows-installer-gold-proof-deadbeefdead.zip",
                    import_command="python3 scripts/import_windows_installer_gold_proof_artifact.py bundle.zip --verify",
                    auto_import_watch_command="python3 scripts/auto_import_windows_installer_gold_proof.py --wait-seconds 900",
                    operator_summary="Run the promoted Windows installer on a native Windows host and provide the gold proof bundle.",
                    current_failure="Windows installer visual audit source digest does not match promoted installer",
                    required_surfaces=["install-progress", "completion"],
                    required_dpi_scales=["1.0", "1.5"],
                )
                metadata = intake.materialize_operator_telegram_draft(draft)
            finally:
                intake.DEFAULT_OPERATOR_DRAFT_ROOT = original_draft_root

            message_path = Path(draft["message_path"])
            metadata_path = Path(draft["metadata_path"])
            current_message_path = Path(draft["current_message_path"])
            current_metadata_path = Path(draft["current_metadata_path"])
            self.assertTrue(message_path.is_file())
            self.assertTrue(metadata_path.is_file())
            self.assertTrue(current_message_path.is_file())
            self.assertTrue(current_metadata_path.is_file())
            self.assertIn("native Windows host", message_path.read_text(encoding="utf-8"))
            self.assertEqual(message_path.read_text(encoding="utf-8"), current_message_path.read_text(encoding="utf-8"))
            stored_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            current_metadata = json.loads(current_metadata_path.read_text(encoding="utf-8"))
            self.assertEqual(metadata["message_sha256"], stored_metadata["message_sha256"])
            self.assertEqual(metadata["message_sha256"], current_metadata["message_sha256"])
            self.assertEqual("deadbeef" * 8, stored_metadata["promoted_installer_sha256"])
            self.assertEqual(str(root / "incoming" / "windows-installer-gold-proof-deadbeefdead.zip"), stored_metadata["preferred_drop_path"])
            self.assertEqual(str(current_message_path), stored_metadata["operator_ask_text_path"])
            self.assertEqual(str(current_metadata_path), stored_metadata["operator_ask_metadata_path"])
            self.assertEqual(draft["send_command"], stored_metadata["operator_ask_send_command"])
            self.assertEqual(draft["receipt_name"], stored_metadata["operator_ask_receipt_name"])
            self.assertNotIn("message_text", stored_metadata)
            self.assertEqual(str(message_path), current_metadata["source_message_path"])
            self.assertEqual(str(metadata_path), current_metadata["source_metadata_path"])
            self.assertEqual(str(current_message_path), current_metadata["operator_ask_text_path"])
            self.assertEqual(str(current_metadata_path), current_metadata["operator_ask_metadata_path"])
            self.assertEqual(draft["send_command"], current_metadata["operator_ask_send_command"])
            self.assertEqual(draft["receipt_name"], current_metadata["operator_ask_receipt_name"])
            self.assertTrue(stored_metadata["secrets_redacted"])
            self.assertTrue(current_metadata["secrets_redacted"])
            self.assertTrue(str(current_message_path).startswith(str(expected_draft_root)))
            self.assertTrue(str(current_metadata_path).startswith(str(expected_draft_root)))

    def test_verify_windows_installer_visual_audit_intake_request_reports_missing_receipt_structurally(self) -> None:
        verifier = load_verify_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-verify-missing-") as temp_dir:
            path = Path(temp_dir) / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"

            ok, result = verifier.verify(path, require_pass=False)

        self.assertFalse(ok)
        self.assertEqual("fail", result["status"])
        self.assertEqual("missing", result["structural_status"])
        self.assertEqual("missing", result["effective_status"])
        self.assertEqual("missing", result["request_status"])
        self.assertEqual(
            [f"missing_windows_visual_intake_request:{path}"],
            result["issues"],
        )

    def test_verify_windows_installer_visual_audit_intake_request_accepts_structural_recovery_pack(self) -> None:
        intake = load_intake_module()
        verifier = load_verify_intake_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-intake-verify-") as temp_dir:
            root = Path(temp_dir)
            downloads_root, release_channel, sha = self._write_release_fixture(root)
            startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup.parent.mkdir()
            startup.write_text(
                json.dumps({"status": "pass", "artifactDigest": f"sha256:{sha}"}),
                encoding="utf-8",
            )
            source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
            source.parent.mkdir(parents=True)
            (source.parent / "old-progress.png").write_bytes(b"old-progress")
            (source.parent / "old-completion.png").write_bytes(b"old-completion")
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": "0" * 64,
                        "screenshots": [
                            {
                                "path": "old-progress.png",
                                "surface": "install-progress",
                                "dpiScale": 1.0,
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                            {
                                "path": "old-completion.png",
                                "surface": "completion",
                                "dpiScale": 1.5,
                                "clippingStatus": "pass",
                                "readabilityStatus": "pass",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            output_path = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            original_draft_root = intake.DEFAULT_OPERATOR_DRAFT_ROOT
            intake.DEFAULT_OPERATOR_DRAFT_ROOT = root / "_completion" / "windows_installer_visual_audit"
            try:
                payload = intake.build_request(
                    release_channel=release_channel,
                    downloads_root=downloads_root,
                    startup_receipt=startup,
                    source=source,
                    discovery_roots=[root / "drop"],
                    nightly_root=root / "nightly",
                    dedicated_drop_root=root / "drop",
                )
                payload["request_receipt_path"] = str(output_path)
                payload["operator_telegram_draft"]["request_receipt_path"] = str(output_path)
                payload["operator_telegram_draft_materialized"] = intake.materialize_operator_telegram_draft(
                    payload["operator_telegram_draft"]
                )
            finally:
                intake.DEFAULT_OPERATOR_DRAFT_ROOT = original_draft_root

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            ok, result = verifier.verify(output_path, require_pass=False)

        self.assertTrue(ok)
        self.assertEqual("pass", result["status"])
        self.assertEqual("external_artifact_required", result["request_status"])
        self.assertTrue(result["operator_action_still_required"])
        self.assertTrue(result["recovery_pack_pass"])
        self.assertEqual([], result["issues"])

    def test_auto_import_windows_installer_gold_proof_waiting_payload_surfaces_expected_bundle_details(self) -> None:
        module = load_auto_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-auto-waiting-") as temp_dir:
            root = Path(temp_dir)
            preferred_drop_path = root / "incoming" / "windows-installer-gold-proof-deadbeef1234.zip"
            intake = {
                "preferred_drop_folder": str(preferred_drop_path.parent),
                "preferred_drop_path": str(preferred_drop_path),
                "preferred_zip_name": preferred_drop_path.name,
                "required_zip_filename": preferred_drop_path.name,
                "last_discovery": {
                    "visual_sources": {
                        "count": 3,
                        "matching_promoted_count": 1,
                    }
                },
                "artifact_intake": {
                    "dedicated_drop_root": str(preferred_drop_path.parent),
                    "preferred_drop_path": str(preferred_drop_path),
                    "import_command": f"python3 scripts/import_windows_installer_gold_proof_artifact.py {preferred_drop_path} --verify",
                    "discover_command": "python3 ~/.codex/skills/ea-artifact-intake/scripts/artifact_intake.py discover ...",
                    "post_import_verify_command": "python3 scripts/verify_windows_installer_visual_audit.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
                },
                "operator_request": {
                    "summary": "Provide the native Windows gold-proof bundle.",
                },
                "operator_telegram_draft": {
                    "message_path": str(root / "_completion" / "windows-proof-operator-ask.txt"),
                    "current_message_path": str(root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"),
                    "current_metadata_path": str(root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"),
                    "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file operator-ask.txt",
                    "message_preview": "Native Windows gold proof still missing.",
                },
            }

            payload = module.build_waiting_payload(
                artifact=None,
                candidates=[],
                intake=intake,
                intake_request=root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
                downloads_root=root / "downloads",
                roots=[preferred_drop_path.parent],
            )

        self.assertEqual("waiting_for_artifact", payload["status"])
        self.assertEqual(str(preferred_drop_path.parent), payload["preferred_drop_folder"])
        self.assertEqual(str(preferred_drop_path), payload["preferred_drop_path"])
        self.assertEqual(preferred_drop_path.name, payload["preferred_zip_name"])
        self.assertEqual(preferred_drop_path.name, payload["required_zip_filename"])
        self.assertIn("import_windows_installer_gold_proof_artifact.py", payload["import_command"])
        self.assertIn("artifact_intake.py discover", payload["discover_command"])
        self.assertIn("auto_import_windows_installer_gold_proof.py", payload["auto_import_command"])
        self.assertIn("auto_import_windows_installer_gold_proof.py", payload["auto_import_watch_command"])
        self.assertIn("--wait-seconds 900", payload["auto_import_watch_command"])
        self.assertIn("--refresh-intake-request", payload["auto_import_watch_command"])
        self.assertIn("verify_windows_installer_visual_audit.py", payload["post_import_verify_command"])
        self.assertEqual("Provide the native Windows gold-proof bundle.", payload["operator_summary"])
        self.assertEqual(0, payload["directory_candidate_count"])
        self.assertEqual(0, payload["matching_promoted_directory_candidate_count"])
        self.assertEqual([], payload["matching_promoted_directory_candidates"])
        self.assertEqual(0, payload["stale_directory_candidate_count"])
        self.assertEqual([], payload["stale_directory_candidates"])
        self.assertEqual(0, payload["suppressed_stale_directory_candidate_count"])
        self.assertEqual(0, payload["zip_candidate_count"])
        self.assertEqual(0, payload["matching_promoted_zip_candidate_count"])
        self.assertEqual([], payload["matching_promoted_zip_candidates"])
        self.assertEqual([], payload["candidates"])
        self.assertEqual(0, payload["actionable_candidate_count"])
        self.assertFalse(payload["directory_candidates_require_explicit_artifact"])
        self.assertEqual("", payload["directory_candidate_note"])
        self.assertEqual(3, payload["intake_visual_source_count"])
        self.assertEqual(1, payload["intake_matching_promoted_visual_source_count"])
        self.assertIn("send_telegram_message_via_ea.py", payload["operator_telegram_send_command"])
        self.assertEqual("Native Windows gold proof still missing.", payload["operator_telegram_draft"]["message_preview"])

    def test_downloads_runbook_documents_windows_gold_proof_loop(self) -> None:
        runbook = REPO_ROOT / "docs" / "SELF_HOSTED_DOWNLOADS_RUNBOOK.md"
        text = runbook.read_text(encoding="utf-8")

        self.assertIn("Windows installer gold proof", text)
        self.assertIn("native Windows proof runner", text)
        self.assertIn("must not publish downloads", text)
        self.assertIn("windows-installer-gold-proof.zip --verify", text)
        self.assertIn(".state/incoming_windows_installer_gold_proof", text)
        self.assertIn("CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK", text)
        self.assertIn("auto_import_windows_installer_gold_proof.py", text)
        self.assertIn("review_required", text)
        self.assertIn("capture_windows_installer_gold_proof.ps1 -LaunchInstaller -CaptureVisualAudit", text)
        self.assertIn("verify_windows_installer_visual_audit.py", text)
