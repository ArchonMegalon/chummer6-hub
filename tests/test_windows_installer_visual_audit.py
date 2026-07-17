import argparse
import importlib.util
import json
import os
import subprocess
import struct
import tempfile
import threading
import time
import unittest
import unittest.mock
import zipfile
import zlib
from pathlib import Path
from unittest import mock


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

    def _write_windows_visual_source_fixture(
        self,
        downloads_root: Path,
        *,
        source_artifact_sha: str,
    ) -> Path:
        source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
        source.parent.mkdir(parents=True, exist_ok=True)
        (source.parent / "old-progress.png").write_bytes(b"old-progress")
        (source.parent / "old-completion.png").write_bytes(b"old-completion")
        source.write_text(
            json.dumps(
                {
                    "status": "pass",
                    "platform": "windows",
                    "hostClass": "native-windows-11",
                    "artifactSha256": source_artifact_sha,
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
        return source

    def _write_valid_windows_visual_source_fixture(
        self,
        downloads_root: Path,
        *,
        source_artifact_sha: str,
    ) -> Path:
        source = downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
        source.parent.mkdir(parents=True, exist_ok=True)
        for name in [
            "progress-default.png",
            "progress-scaled.png",
            "completion-default.png",
            "completion-scaled.png",
        ]:
            (source.parent / name).write_bytes(name.encode("utf-8"))
        source.write_text(
            json.dumps(
                {
                    "status": "pass",
                    "platform": "windows",
                    "hostClass": "native-windows-11",
                    "artifactSha256": source_artifact_sha,
                    "screenshots": [
                        {
                            "path": "progress-default.png",
                            "surface": "install-progress",
                            "dpiScale": 1.0,
                            "clippingStatus": "pass",
                            "readabilityStatus": "pass",
                            "captureMode": "window-bounds",
                            "captureBounds": {"left": 184, "top": 200, "width": 656, "height": 319},
                        },
                        {
                            "path": "progress-scaled.png",
                            "surface": "install-progress",
                            "dpiScale": 1.5,
                            "clippingStatus": "pass",
                            "readabilityStatus": "pass",
                            "captureMode": "window-bounds",
                            "captureBounds": {"left": 184, "top": 200, "width": 656, "height": 319},
                        },
                        {
                            "path": "completion-default.png",
                            "surface": "completion",
                            "dpiScale": 1.0,
                            "clippingStatus": "pass",
                            "readabilityStatus": "pass",
                            "captureMode": "window-bounds",
                            "captureBounds": {"left": 184, "top": 200, "width": 656, "height": 319},
                        },
                        {
                            "path": "completion-scaled.png",
                            "surface": "completion",
                            "dpiScale": 1.5,
                            "clippingStatus": "pass",
                            "readabilityStatus": "pass",
                            "captureMode": "window-bounds",
                            "captureBounds": {"left": 184, "top": 200, "width": 656, "height": 319},
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        return source

    def _build_windows_visual_intake_request_payload(
        self,
        root: Path,
        *,
        startup_receipt_payload: dict[str, object] | None = None,
        source_artifact_sha: str | None = None,
    ) -> tuple[dict[str, object], Path, str]:
        intake = load_intake_module()
        downloads_root, release_channel, sha = self._write_release_fixture(root)
        startup = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
        startup.parent.mkdir(parents=True, exist_ok=True)
        startup_payload = {"status": "pass", "artifactDigest": f"sha256:{sha}"}
        if startup_receipt_payload:
            startup_payload.update(startup_receipt_payload)
        startup.write_text(json.dumps(startup_payload), encoding="utf-8")
        source = self._write_windows_visual_source_fixture(
            downloads_root,
            source_artifact_sha=source_artifact_sha or sha,
        )
        receipt_path = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
        original_draft_root = intake.DEFAULT_OPERATOR_DRAFT_ROOT
        intake.DEFAULT_OPERATOR_DRAFT_ROOT = root / "_completion" / "windows_installer_visual_audit"
        try:
            payload = intake.build_request(
                release_channel=release_channel,
                downloads_root=downloads_root,
                startup_receipt=startup,
                source=source,
                request_output=receipt_path,
                discovery_roots=[root / "drop"],
                nightly_root=root / "nightly",
                dedicated_drop_root=root / "drop",
            )
            payload["operator_telegram_draft_materialized"] = intake.materialize_operator_telegram_draft(
                payload["operator_telegram_draft"]
            )
        finally:
            intake.DEFAULT_OPERATOR_DRAFT_ROOT = original_draft_root
        return payload, receipt_path, sha

    def _write_current_windows_visual_audit_receipt(
        self,
        path: Path,
        *,
        status: str,
        source_digest_matches_promoted: bool,
        manifest_artifact_sha: str | None = None,
        startup_status: str = "pass",
        startup_digest_matches_promoted: bool = True,
        visual_status: str = "pass",
        visual_digest_matches_promoted: bool = True,
        failures: list[str] | None = None,
        failed_gates: list[str] | None = None,
        explicit_pass: bool | None = True,
        artifact_sha: str = "a" * 64,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, object] = {
            "status": status,
            "required_promoted_digest": artifact_sha,
            "manifest_promoted_digest": manifest_artifact_sha or artifact_sha,
            "artifact": {
                "sha256": manifest_artifact_sha or artifact_sha,
                "actualSha256": artifact_sha,
                "effectiveSha256": artifact_sha,
            },
            "source_digest_matches_promoted": source_digest_matches_promoted,
            "startupReceipt": {
                "status": startup_status,
                "verificationDisposition": "pass",
                "skipClass": "",
                "artifactDigest": f"sha256:{artifact_sha}",
                "artifactDigestMatchesPromoted": startup_digest_matches_promoted,
            },
            "visualAuditSource": {
                "exists": True,
                "status": visual_status,
                "platform": "windows",
                "hostClass": "native-windows-11",
                "artifactSha256": artifact_sha,
                "artifactDigestMatchesPromoted": visual_digest_matches_promoted,
                "requiredSurfaces": ["install-progress", "completion"],
                "screenshotCount": 4,
                "defaultDpiScreenshotCount": 2,
                "scaledDpiScreenshotCount": 2,
            },
            "failures": failures or [],
            "failed_gates": failed_gates or [],
        }
        if explicit_pass is not None:
            payload["pass"] = explicit_pass
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

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

    def test_matching_startup_with_stale_visual_digest_keeps_startup_receipt(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-stale-") as temp_dir:
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
            stale_sha = "0" * 64
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": stale_sha,
                        "sourceUpdatedAtUtc": "2026-06-21T17:44:15Z",
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

        self.assertEqual("fail", payload["status"])
        self.assertEqual(
            "Native Windows visual audit still failing: Windows installer visual audit source digest does not match promoted installer",
            payload["summary"],
        )
        self.assertIn("Windows installer visual audit source digest does not match promoted installer", payload["failures"])
        self.assertTrue(payload["startupReceipt"]["artifactDigestMatchesPromoted"])
        self.assertFalse(payload["startupReceipt"]["requiresNativeRefresh"])
        self.assertFalse(payload["visualAuditSource"]["artifactDigestMatchesPromoted"])
        self.assertTrue(payload["visualAuditSource"]["requiresRecapture"])
        self.assertEqual("2026-06-21T17:44:15Z", payload["visualAuditSource"]["sourceUpdatedAtUtc"])
        self.assertTrue(any("Recapture the Windows installer visual audit" in item for item in payload["nextActions"]))
        self.assertTrue(any("Keep the current Windows startup-smoke receipt" in item for item in payload["nextActions"]))
        self.assertFalse(any("Replace or refresh the Windows startup-smoke receipt" in item for item in payload["nextActions"]))

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
        self.assertEqual("Native Windows visual audit matches the promoted installer.", payload["summary"])
        self.assertEqual([], payload["failures"])
        self.assertEqual([], payload["nextActions"])
        self.assertEqual(["install-progress", "completion"], payload["visualAuditSource"]["requiredSurfaces"])
        self.assertTrue(all(row["sha256"] for row in payload["screenshots"]))

    def test_digest_mismatch_surfaces_missing_bundle_and_auto_import_hint_details(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-hints-") as temp_dir:
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
            for index, name in enumerate(
                [
                    "progress-default.png",
                    "progress-scaled.png",
                    "completion-default.png",
                    "completion-scaled.png",
                ]
            ):
                (source.parent / name).write_bytes(f"png-{index}".encode("utf-8"))
            stale_source_sha = "c" * 64
            source.write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": stale_source_sha,
                        "generatedAt": "2026-07-05T13:00:00Z",
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

            published = root / "published"
            published.mkdir(parents=True, exist_ok=True)
            intake_request = published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            ask_text = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"
            ask_metadata = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"
            delivery_root = root / "telegram"
            ask_text.parent.mkdir(parents=True, exist_ok=True)
            delivery_root.mkdir(parents=True, exist_ok=True)
            ask_text.write_text("windows ask current\n", encoding="utf-8")
            ask_metadata.write_text("{}\n", encoding="utf-8")
            (delivery_root / "windows.receipt.json").write_text(
                json.dumps(
                    {
                        "status": "sent",
                        "generated_at_utc": "2026-07-04T20:58:05Z",
                        "message_ids": ["3555"],
                        "text_sha256": module.hashlib.sha256("windows ask current\n".encode("utf-8")).hexdigest(),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            preferred_drop_path = root / "incoming" / "windows-installer-gold-proof.zip"
            intake_request.write_text(
                json.dumps(
                    {
                        "status": "not_required",
                        "preferred_drop_path": str(preferred_drop_path),
                        "preferred_zip_name": preferred_drop_path.name,
                        "required_zip_filename": preferred_drop_path.name,
                        "promoted_installer_sha256": sha,
                        "startup_receipt_bundle_required": False,
                        "operator_telegram_draft": {
                            "current_message_path": str(ask_text),
                            "current_metadata_path": str(ask_metadata),
                            "send_command": "python3 send-windows-ask",
                            "receipt_name": "windows.receipt.json",
                        },
                        "artifact_intake": {
                            "discover_command": "python3 discover-windows-proof",
                            "import_command": "python3 import-windows-proof",
                            "auto_import_watch_command": "python3 watch-windows-proof",
                            "post_import_verify_command": "python3 verify-windows-proof",
                            "post_import_verify_note": "verify the imported bundle",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            auto_import = published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
            auto_import.write_text(
                json.dumps(
                    {
                        "status": "waiting_for_artifact",
                        "actionable_candidate_count": 0,
                        "stage_visual_proof_receipt_count": 8,
                        "matching_promoted_stage_visual_proof_receipt_count": 0,
                        "stale_stage_visual_proof_receipt_count": 8,
                        "stage_startup_smoke_receipt_count": 43,
                        "matching_promoted_stage_startup_smoke_receipt_count": 4,
                        "stale_stage_startup_smoke_receipt_count": 39,
                        "stage_visual_proof_receipt_note": "Stage/nightly Windows proof receipts were found, but none match the promoted installer digest.",
                        "stage_startup_smoke_receipt_note": "Matching stage/nightly Windows startup-smoke receipts were found for the promoted installer digest.",
                        "stale_stage_visual_proof_receipts": [
                            {"path": "/tmp/stale-proof-a/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"},
                            {"path": "/tmp/stale-proof-b/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"},
                        ],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(module, "DEFAULT_WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST", intake_request), mock.patch.object(
                module, "DEFAULT_WINDOWS_VISUAL_AUDIT_AUTO_IMPORT", auto_import
            ), mock.patch.object(module, "DEFAULT_TELEGRAM_TEXT_DELIVERY_ROOT", delivery_root):
                payload = module.build_payload(
                    release_channel_path=release_channel,
                    downloads_root=downloads_root,
                    startup_receipt_path=startup,
                    source_path=source,
                )

        self.assertEqual("fail", payload["status"])
        self.assertIn("Windows installer visual audit source digest does not match promoted installer", payload["failures"])
        self.assertIn(
            f"windows installer visual audit source still targets {stale_source_sha} instead of promoted digest {sha}: {source}",
            payload["failures"],
        )
        self.assertIn(
            f"windows installer gold proof artifact is still missing: {preferred_drop_path}",
            payload["failures"],
        )
        self.assertEqual(sha, payload["required_promoted_digest"])
        self.assertEqual(stale_source_sha, payload["source_digest"])
        self.assertFalse(payload["source_digest_matches_promoted"])
        self.assertEqual(str(preferred_drop_path), payload["expected_bundle_path"])
        self.assertFalse(payload["expected_bundle_path_exists"])
        self.assertEqual(preferred_drop_path.name, payload["required_zip_filename"])
        self.assertEqual(preferred_drop_path.name, payload["preferred_zip_name"])
        self.assertEqual("external_artifact_required", payload["proof_request_status"])
        self.assertEqual("not_required", payload["proof_request_raw_status"])
        self.assertEqual(str(delivery_root / "windows.receipt.json"), payload["operator_ask_delivery_receipt_path"])
        self.assertTrue(payload["operator_ask_delivery_receipt_exists"])
        self.assertEqual("sent", payload["operator_ask_delivery_status"])
        self.assertEqual("2026-07-04T20:58:05Z", payload["operator_ask_delivery_generated_at_utc"])
        self.assertEqual(["3555"], payload["operator_ask_delivery_message_ids"])
        self.assertTrue(payload["operator_ask_delivery_current_text_comparable"])
        self.assertTrue(payload["operator_ask_delivery_matches_current_text"])
        self.assertFalse(payload["operator_ask_delivery_needs_resend"])
        self.assertEqual("", payload["operator_ask_resend_command"])
        self.assertEqual("not_required", payload["operator_request_artifacts"]["request_status"])
        self.assertEqual(
            "external_artifact_required",
            payload["operator_request_artifacts"]["request_effective_status"],
        )
        self.assertTrue(payload["operator_request_artifacts"]["operator_action_still_required"])
        self.assertFalse(payload["operator_request_artifacts"]["preferred_drop_path_exists"])
        self.assertEqual("waiting_for_artifact", payload["operator_request_artifacts"]["auto_import_receipt_status"])
        self.assertEqual(8, payload["operator_request_artifacts"]["auto_import_stage_visual_proof_receipt_count"])
        self.assertEqual(43, payload["operator_request_artifacts"]["auto_import_stage_startup_smoke_receipt_count"])
        self.assertEqual(
            [
                "/tmp/stale-proof-a/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
                "/tmp/stale-proof-b/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
            ],
            payload["operator_request_artifacts"]["auto_import_stage_visual_proof_receipt_sample_paths"],
        )
        self.assertTrue(
            any("visual-proof receipts=8, startup-smoke receipts=43" in item for item in payload["nextActions"])
        )
        self.assertTrue(
            any(
                "Sample stale Windows proof hint paths: /tmp/stale-proof-a/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json; /tmp/stale-proof-b/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json"
                in item
                for item in payload["nextActions"]
            )
        )

    def test_passing_visual_audit_ignores_stale_external_artifact_required_request_status(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="windows-installer-visual-stale-request-pass-") as temp_dir:
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
            for index, name in enumerate(
                [
                    "progress-default.png",
                    "progress-scaled.png",
                    "completion-default.png",
                    "completion-scaled.png",
                ]
            ):
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

            published = root / "published"
            published.mkdir(parents=True, exist_ok=True)
            intake_request = published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            ask_text = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"
            ask_metadata = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"
            ask_text.parent.mkdir(parents=True, exist_ok=True)
            ask_text.write_text("windows ask current\n", encoding="utf-8")
            ask_metadata.write_text("{}\n", encoding="utf-8")
            preferred_drop_path = root / "incoming" / "windows-installer-gold-proof.zip"
            intake_request.write_text(
                json.dumps(
                    {
                        "status": "external_artifact_required",
                        "preferred_drop_path": str(preferred_drop_path),
                        "preferred_zip_name": preferred_drop_path.name,
                        "required_zip_filename": preferred_drop_path.name,
                        "promoted_installer_sha256": sha,
                        "startup_receipt_bundle_required": False,
                        "operator_telegram_draft": {
                            "current_message_path": str(ask_text),
                            "current_metadata_path": str(ask_metadata),
                            "send_command": "python3 send-windows-ask",
                            "receipt_name": "windows.receipt.json",
                        },
                        "artifact_intake": {
                            "discover_command": "python3 discover-windows-proof",
                            "import_command": "python3 import-windows-proof",
                            "auto_import_watch_command": "python3 watch-windows-proof",
                            "post_import_verify_command": "python3 verify-windows-proof",
                            "post_import_verify_note": "verify the imported bundle",
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(module, "DEFAULT_WINDOWS_VISUAL_AUDIT_INTAKE_REQUEST", intake_request), mock.patch.object(
                module, "DEFAULT_WINDOWS_VISUAL_AUDIT_AUTO_IMPORT", published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
            ), mock.patch.object(module, "DEFAULT_TELEGRAM_TEXT_DELIVERY_ROOT", root / "telegram"):
                payload = module.build_payload(
                    release_channel_path=release_channel,
                    downloads_root=downloads_root,
                    startup_receipt_path=startup,
                    source_path=source,
                )

        self.assertEqual("pass", payload["status"])
        self.assertEqual([], payload["failures"])
        self.assertEqual([], payload["nextActions"])
        self.assertEqual("not_required", payload["proof_request_status"])
        self.assertEqual("external_artifact_required", payload["proof_request_raw_status"])
        self.assertEqual("external_artifact_required", payload["operator_request_artifacts"]["request_status"])
        self.assertEqual("not_required", payload["operator_request_artifacts"]["request_effective_status"])
        self.assertFalse(payload["operator_request_artifacts"]["operator_action_still_required"])
        self.assertNotIn(
            f"windows installer gold proof artifact is still missing: {preferred_drop_path}",
            payload["failures"],
        )

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
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactDigest": f"sha256:{'a' * 64}",
                    }
                ),
                encoding="utf-8",
            )
            for token, name in enumerate(
                ["progress-default.png", "progress-scaled.png", "completion-default.png", "completion-scaled.png"],
                start=1,
            ):
                write_valid_png(visual_root / name, token=token)
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": "a" * 64,
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
            downloads_root.mkdir()
            summary = module.import_artifact(artifact, downloads_root)

            self.assertTrue((downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json").is_file())
            self.assertTrue((downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").is_file())
            self.assertEqual(4, len(summary["screenshots"]))
            self.assertEqual("artifact_bundle", summary["startupReceiptSource"])
            self.assertTrue(summary["startupReceiptBundleRequired"])
            self.assertTrue((downloads_root / "visual-audit" / "windows-installer" / "completion-scaled.png").is_file())
            self.assertEqual("committed", summary["proofSetTransaction"]["status"])
            self.assertEqual(6, summary["proofSetTransaction"]["item_count"])
            self.assertTrue(summary["proofSetTransaction"]["atomic_cutover"])
            self.assertTrue(summary["proofSetTransaction"]["root_dirfd_no_follow"])
            self.assertRegex(
                summary["proofSetTransaction"]["generation_id"],
                r"^generation-[0-9a-f]{32}$",
            )
            self.assertTrue((downloads_root / ".windows-installer-proof" / "current").is_symlink())
            self.assertTrue((downloads_root / "visual-audit" / "windows-installer").is_symlink())

    def test_windows_gold_proof_generation_update_retains_old_tree_and_switches_current_atomically(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-generation-update-") as temp_dir:
            root = Path(temp_dir)
            downloads_root = root / "downloads"
            downloads_root.mkdir()
            first_entries = proof_generation_entries(module, downloads_root, token=1)
            second_entries = proof_generation_entries(module, downloads_root, token=2)

            first = module.publish_proof_set_transactionally(first_entries, downloads_root)
            old_public_bytes = (
                downloads_root / "visual-audit" / "windows-installer" / "capture.png"
            ).read_bytes()
            second = module.publish_proof_set_transactionally(second_entries, downloads_root)

            self.assertNotEqual(first["generation_id"], second["generation_id"])
            self.assertTrue(second["previous_generation_retained"])
            generations = downloads_root / ".windows-installer-proof" / "generations"
            self.assertTrue((generations / first["generation_id"]).is_dir())
            self.assertTrue((generations / second["generation_id"]).is_dir())
            self.assertEqual(
                old_public_bytes,
                (generations / first["generation_id"] / "visual-audit" / "windows-installer" / "capture.png").read_bytes(),
            )
            self.assertEqual(
                valid_png_bytes(token=2),
                (downloads_root / "visual-audit" / "windows-installer" / "capture.png").read_bytes(),
            )
            self.assertEqual(
                f"generations/{second['generation_id']}",
                os.readlink(downloads_root / ".windows-installer-proof" / "current"),
            )

    def test_windows_gold_proof_generation_recovers_crash_after_pointer_cutover(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-generation-crash-") as temp_dir:
            downloads_root = Path(temp_dir) / "downloads"
            downloads_root.mkdir()
            entries = proof_generation_entries(module, downloads_root, token=3)
            original_install = module._install_current_pointer

            child_pid = os.fork()
            if child_pid == 0:
                def crash_after_install(control_fd, target):
                    original_install(control_fd, target)
                    os._exit(73)

                module._install_current_pointer = crash_after_install
                module.publish_proof_set_transactionally(entries, downloads_root)
                os._exit(74)
            waited_pid, wait_status = os.waitpid(child_pid, 0)
            self.assertEqual(child_pid, waited_pid)
            self.assertEqual(73, os.waitstatus_to_exitcode(wait_status))

            journal_path = downloads_root / ".windows-installer-proof" / "recovery-journal.json"
            self.assertEqual("cutover_pending", json.loads(journal_path.read_text())["state"])
            recovered = module.publish_proof_set_transactionally(entries, downloads_root)

            self.assertEqual("completed_atomic_cutover", recovered["recovery_disposition"])
            self.assertEqual("committed", json.loads(journal_path.read_text())["state"])
            self.assertEqual(
                valid_png_bytes(token=3),
                (downloads_root / "visual-audit" / "windows-installer" / "capture.png").read_bytes(),
            )

    def test_windows_gold_proof_generation_public_reads_never_observe_partial_tree_during_cutover(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-generation-reader-") as temp_dir:
            downloads_root = Path(temp_dir) / "downloads"
            downloads_root.mkdir()
            first_entries = proof_generation_entries(module, downloads_root, token=4)
            second_entries = proof_generation_entries(module, downloads_root, token=5)
            module.publish_proof_set_transactionally(first_entries, downloads_root)
            expected_pairs = {
                (4, module.hashlib.sha256(valid_png_bytes(token=4)).hexdigest()),
                (5, module.hashlib.sha256(valid_png_bytes(token=5)).hexdigest()),
            }
            observations: list[tuple[int, str]] = []
            read_failures: list[str] = []
            stop = threading.Event()

            def reader() -> None:
                public_directory = downloads_root / "visual-audit" / "windows-installer"
                while not stop.is_set():
                    try:
                        directory_fd = os.open(public_directory, os.O_RDONLY | os.O_DIRECTORY)
                        try:
                            source_fd = os.open(module.VISUAL_SOURCE_NAME, os.O_RDONLY, dir_fd=directory_fd)
                            image_fd = os.open("capture.png", os.O_RDONLY, dir_fd=directory_fd)
                            try:
                                source = json.loads(os.read(source_fd, 65536).decode("utf-8"))
                                image = os.read(image_fd, module.MAX_SCREENSHOT_BYTES)
                            finally:
                                os.close(image_fd)
                                os.close(source_fd)
                        finally:
                            os.close(directory_fd)
                        observations.append((int(source["token"]), module.hashlib.sha256(image).hexdigest()))
                    except BaseException as exc:
                        read_failures.append(type(exc).__name__)
                        stop.set()

            thread = threading.Thread(target=reader, daemon=True)
            thread.start()
            time.sleep(0.03)
            module.publish_proof_set_transactionally(second_entries, downloads_root)
            time.sleep(0.03)
            stop.set()
            thread.join(timeout=2.0)

            self.assertFalse(thread.is_alive())
            self.assertEqual([], read_failures)
            self.assertGreater(len(observations), 0)
            self.assertTrue(set(observations).issubset(expected_pairs), observations[:10])

    def test_windows_gold_proof_generation_rejects_symlinked_public_ancestor_without_writing_outside_root(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-generation-symlink-") as temp_dir:
            root = Path(temp_dir)
            downloads_root = root / "downloads"
            outside = root / "outside"
            downloads_root.mkdir()
            outside.mkdir()
            (downloads_root / "visual-audit").symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(SystemExit, "ancestor is linked|separately authorized migration"):
                module.publish_proof_set_transactionally(
                    proof_generation_entries(module, downloads_root, token=6),
                    downloads_root,
                )

            self.assertEqual([], list(outside.iterdir()))
            self.assertFalse((downloads_root / ".windows-installer-proof").exists())

    def test_windows_gold_proof_generation_rejects_symlink_in_downloads_root_ancestry(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-root-ancestor-symlink-") as temp_dir:
            root = Path(temp_dir)
            real_parent = root / "real-parent"
            real_downloads = real_parent / "downloads"
            real_downloads.mkdir(parents=True)
            alias = root / "alias"
            alias.symlink_to(real_parent, target_is_directory=True)
            aliased_downloads = alias / "downloads"

            with self.assertRaisesRegex(SystemExit, "missing, linked, or not a directory"):
                module.publish_proof_set_transactionally(
                    proof_generation_entries(module, aliased_downloads, token=7),
                    aliased_downloads,
                )

            self.assertFalse((real_downloads / ".windows-installer-proof").exists())

    def test_windows_gold_proof_generation_interprocess_lock_fails_closed(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-generation-lock-") as temp_dir:
            downloads_root = Path(temp_dir) / "downloads"
            downloads_root.mkdir()
            first = module.publish_proof_set_transactionally(
                proof_generation_entries(module, downloads_root, token=8),
                downloads_root,
            )
            lock_path = downloads_root / ".windows-installer-proof" / "publish.lock"
            lock_fd = os.open(lock_path, os.O_RDWR | os.O_NOFOLLOW)
            try:
                module.fcntl.flock(lock_fd, module.fcntl.LOCK_EX | module.fcntl.LOCK_NB)
                with self.assertRaisesRegex(SystemExit, "currently holds the lock"):
                    module.publish_proof_set_transactionally(
                        proof_generation_entries(module, downloads_root, token=9),
                        downloads_root,
                    )
            finally:
                module.fcntl.flock(lock_fd, module.fcntl.LOCK_UN)
                os.close(lock_fd)

            self.assertEqual(
                f"generations/{first['generation_id']}",
                os.readlink(downloads_root / ".windows-installer-proof" / "current"),
            )
            self.assertEqual(
                valid_png_bytes(token=8),
                (downloads_root / "visual-audit" / "windows-installer" / "capture.png").read_bytes(),
            )

    def test_windows_gold_proof_generation_recovers_crash_with_pending_new_anchor(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-pending-anchor-crash-") as temp_dir:
            downloads_root = Path(temp_dir) / "downloads"
            downloads_root.mkdir()
            entries = proof_generation_entries(module, downloads_root, token=10)
            original_ensure = module._ensure_public_anchor

            child_pid = os.fork()
            if child_pid == 0:
                def crash_after_anchor(root_fd, anchor_id):
                    created = original_ensure(root_fd, anchor_id)
                    if anchor_id == "visual":
                        os._exit(75)
                    return created

                module._ensure_public_anchor = crash_after_anchor
                module.publish_proof_set_transactionally(entries, downloads_root)
                os._exit(76)
            _waited_pid, wait_status = os.waitpid(child_pid, 0)
            self.assertEqual(75, os.waitstatus_to_exitcode(wait_status))
            journal_path = downloads_root / ".windows-installer-proof" / "recovery-journal.json"
            crashed_journal = json.loads(journal_path.read_text(encoding="utf-8"))
            self.assertEqual("generation_ready", crashed_journal["state"])
            self.assertEqual("visual", crashed_journal["pending_anchor"])
            self.assertTrue((downloads_root / "visual-audit" / "windows-installer").is_symlink())

            recovered = module.publish_proof_set_transactionally(entries, downloads_root)

            self.assertEqual("removed_uncommitted_anchors", recovered["recovery_disposition"])
            self.assertEqual("committed", json.loads(journal_path.read_text())["state"])
            self.assertTrue((downloads_root / "visual-audit" / "windows-installer").is_symlink())
            self.assertTrue(
                (downloads_root / "startup-smoke" / module.STARTUP_RECEIPT_NAME).is_symlink()
            )

    def test_windows_gold_proof_generation_rolls_back_anchor_created_before_fsync_error(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-anchor-fsync-error-") as temp_dir:
            downloads_root = Path(temp_dir) / "downloads"
            downloads_root.mkdir()
            entries = proof_generation_entries(module, downloads_root, token=11)
            original_ensure = module._ensure_public_anchor

            def fail_after_visual_anchor(root_fd, anchor_id):
                created = original_ensure(root_fd, anchor_id)
                if anchor_id == "visual":
                    raise OSError("synthetic anchor parent fsync failure")
                return created

            with mock.patch.object(module, "_ensure_public_anchor", side_effect=fail_after_visual_anchor):
                with self.assertRaisesRegex(OSError, "synthetic anchor parent fsync failure"):
                    module.publish_proof_set_transactionally(entries, downloads_root)

            journal = json.loads(
                (downloads_root / ".windows-installer-proof" / "recovery-journal.json").read_text()
            )
            self.assertEqual("rolled_back", journal["state"])
            self.assertEqual([], journal["created_anchors"])
            self.assertIsNone(journal["pending_anchor"])
            self.assertFalse((downloads_root / ".windows-installer-proof" / "current").exists())
            self.assertFalse((downloads_root / "visual-audit" / "windows-installer").exists())

    def test_windows_gold_proof_generation_rejects_unknown_journal_before_public_mutation(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-unknown-journal-") as temp_dir:
            downloads_root = Path(temp_dir) / "downloads"
            downloads_root.mkdir()
            first = module.publish_proof_set_transactionally(
                proof_generation_entries(module, downloads_root, token=12),
                downloads_root,
            )
            control = downloads_root / ".windows-installer-proof"
            current_before = os.readlink(control / "current")
            journal_path = control / "recovery-journal.json"
            journal = json.loads(journal_path.read_text())
            journal["state"] = "delete_everything"
            journal_path.write_text(json.dumps(journal), encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "journal state is invalid"):
                module.publish_proof_set_transactionally(
                    proof_generation_entries(module, downloads_root, token=13),
                    downloads_root,
                )

            self.assertEqual(current_before, os.readlink(control / "current"))
            self.assertEqual(f"generations/{first['generation_id']}", current_before)
            self.assertTrue((downloads_root / "visual-audit" / "windows-installer").is_symlink())

    def test_windows_gold_proof_generation_rejects_empty_journal_before_public_mutation(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-empty-journal-") as temp_dir:
            downloads_root = Path(temp_dir) / "downloads"
            downloads_root.mkdir()
            first = module.publish_proof_set_transactionally(
                proof_generation_entries(module, downloads_root, token=121),
                downloads_root,
            )
            control = downloads_root / ".windows-installer-proof"
            current_before = os.readlink(control / "current")
            journal_path = control / "recovery-journal.json"
            journal_path.write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "journal field set is invalid"):
                module.publish_proof_set_transactionally(
                    proof_generation_entries(module, downloads_root, token=122),
                    downloads_root,
                )

            self.assertEqual(current_before, os.readlink(control / "current"))
            self.assertEqual(f"generations/{first['generation_id']}", current_before)
            self.assertTrue((downloads_root / "visual-audit" / "windows-installer").is_symlink())

    def test_windows_gold_proof_generation_rejects_existing_hardlink_without_repair_or_pointer_loss(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-existing-hardlink-") as temp_dir:
            root = Path(temp_dir)
            downloads_root = root / "downloads"
            downloads_root.mkdir()
            entries = proof_generation_entries(module, downloads_root, token=14)
            first = module.publish_proof_set_transactionally(entries, downloads_root)
            control = downloads_root / ".windows-installer-proof"
            generation_root = control / "generations" / first["generation_id"]
            image = generation_root / "visual-audit" / "windows-installer" / "capture.png"
            outside = root / "outside.png"
            outside.write_bytes(image.read_bytes())
            outside.chmod(0o640)
            image.parent.chmod(0o755)
            image.unlink()
            os.link(outside, image)
            image.parent.chmod(0o555)

            with self.assertRaisesRegex(SystemExit, "not a bounded regular file|not private"):
                module.publish_proof_set_transactionally(entries, downloads_root)

            self.assertEqual(0o640, outside.stat().st_mode & 0o777)
            self.assertEqual(
                f"generations/{first['generation_id']}",
                os.readlink(control / "current"),
            )

    def test_windows_gold_proof_generation_rejects_extra_empty_directory(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-extra-directory-") as temp_dir:
            downloads_root = Path(temp_dir) / "downloads"
            downloads_root.mkdir()
            entries = proof_generation_entries(module, downloads_root, token=15)
            first = module.publish_proof_set_transactionally(entries, downloads_root)
            control = downloads_root / ".windows-installer-proof"
            generation_root = control / "generations" / first["generation_id"]
            generation_root.chmod(0o755)
            (generation_root / "extra-empty").mkdir()
            (generation_root / "extra-empty").chmod(0o555)
            generation_root.chmod(0o555)

            with self.assertRaisesRegex(SystemExit, "extra directories"):
                module.publish_proof_set_transactionally(entries, downloads_root)

            self.assertEqual(
                f"generations/{first['generation_id']}",
                os.readlink(control / "current"),
            )

    def test_import_windows_installer_gold_proof_artifact_rejects_visual_only_bundle_even_when_legacy_intake_marks_startup_optional(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-reuse-startup-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            visual_root.mkdir(parents=True)
            for token, name in enumerate(
                ["progress-default.png", "progress-scaled.png", "completion-default.png", "completion-scaled.png"],
                start=1,
            ):
                write_valid_png(visual_root / name, token=token)
            promoted_digest = "a" * 64
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": promoted_digest,
                        "screenshots": [
                            {"path": "progress-default.png", "surface": "install-progress"},
                            {"path": "progress-scaled.png", "surface": "install-progress"},
                            {"path": "completion-default.png", "surface": "completion"},
                            {"path": "completion-scaled.png", "surface": "completion"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            downloads_root = root / "downloads"
            startup_receipt = downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json"
            startup_receipt.parent.mkdir(parents=True)
            startup_receipt.write_text(
                json.dumps({"status": "pass", "artifactDigest": f"sha256:{promoted_digest}"}),
                encoding="utf-8",
            )
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            intake_request.write_text(
                json.dumps(
                    {
                        "promoted_installer_sha256": promoted_digest,
                        "startup_receipt_bundle_required": False,
                        "artifact_intake": {"startup_receipt_bundle_required": False},
                        "operator_request": {"startup_receipt_bundle_required": False},
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                SystemExit,
                "complete generation publication requires the native startup receipt",
            ):
                module.import_artifact(artifact, downloads_root, intake_request=intake_request)

            self.assertTrue(startup_receipt.is_file())
            self.assertFalse(
                (downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").exists()
            )

    def test_import_windows_installer_gold_proof_artifact_rejects_visual_source_digest_mismatch_before_copying(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-visual-digest-mismatch-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            startup_root = artifact / "Chummer.Portal" / "downloads" / "startup-smoke"
            visual_root.mkdir(parents=True)
            startup_root.mkdir(parents=True)
            promoted_digest = "a" * 64
            (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactDigest": f"sha256:{promoted_digest}",
                    }
                ),
                encoding="utf-8",
            )
            for token, name in enumerate(["progress.png", "completion.png"], start=1):
                write_valid_png(visual_root / name, token=token)
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": "b" * 64,
                        "screenshots": [
                            {"path": "progress.png", "surface": "install-progress"},
                            {"path": "completion.png", "surface": "completion"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            downloads_root = root / "downloads"
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            intake_request.write_text(
                json.dumps({"promoted_installer_sha256": promoted_digest}),
                encoding="utf-8",
            )

            with self.assertRaises(SystemExit) as raised:
                module.import_artifact(artifact, downloads_root, intake_request=intake_request)

            self.assertIn("visual audit source digest does not match the promoted installer", str(raised.exception))
            self.assertFalse((downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json").exists())
            self.assertFalse((downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").exists())

    def test_import_windows_installer_gold_proof_artifact_rejects_missing_intake_request_before_copying(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-missing-intake-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            startup_root = artifact / "Chummer.Portal" / "downloads" / "startup-smoke"
            visual_root.mkdir(parents=True)
            startup_root.mkdir(parents=True)
            promoted_digest = "a" * 64
            (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
                json.dumps({"status": "pass", "artifactDigest": f"sha256:{promoted_digest}"}),
                encoding="utf-8",
            )
            for name in ["progress.png", "completion.png"]:
                (visual_root / name).write_bytes(name.encode("utf-8"))
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "artifactSha256": promoted_digest,
                        "screenshots": [
                            {"path": "progress.png", "surface": "install-progress"},
                            {"path": "completion.png", "surface": "completion"},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            downloads_root = root / "downloads"
            missing_intake = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"

            with self.assertRaises(SystemExit) as raised:
                module.import_artifact(artifact, downloads_root, intake_request=missing_intake)

            self.assertIn("intake request not found", str(raised.exception))
            self.assertFalse((downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json").exists())
            self.assertFalse((downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").exists())

    def test_import_windows_installer_gold_proof_artifact_rejects_intake_request_without_promoted_digest_before_copying(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-missing-promoted-digest-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            startup_root = artifact / "Chummer.Portal" / "downloads" / "startup-smoke"
            visual_root.mkdir(parents=True)
            startup_root.mkdir(parents=True)
            promoted_digest = "a" * 64
            (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
                json.dumps({"status": "pass", "artifactDigest": f"sha256:{promoted_digest}"}),
                encoding="utf-8",
            )
            for name in ["progress.png", "completion.png"]:
                (visual_root / name).write_bytes(name.encode("utf-8"))
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "artifactSha256": promoted_digest,
                        "screenshots": [
                            {"path": "progress.png", "surface": "install-progress"},
                            {"path": "completion.png", "surface": "completion"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            intake_request.write_text(json.dumps({"startup_receipt_bundle_required": True}), encoding="utf-8")

            downloads_root = root / "downloads"

            with self.assertRaises(SystemExit) as raised:
                module.import_artifact(artifact, downloads_root, intake_request=intake_request)

            self.assertIn("missing the promoted installer digest", str(raised.exception))
            self.assertFalse((downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json").exists())
            self.assertFalse((downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").exists())

    def test_import_windows_installer_gold_proof_artifact_rejects_bundled_startup_digest_mismatch_before_copying(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-startup-digest-mismatch-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            startup_root = artifact / "Chummer.Portal" / "downloads" / "startup-smoke"
            visual_root.mkdir(parents=True)
            startup_root.mkdir(parents=True)
            promoted_digest = "c" * 64
            (startup_root / "startup-smoke-avalonia-win-x64.receipt.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactDigest": "sha256:" + ("d" * 64),
                    }
                ),
                encoding="utf-8",
            )
            for token, name in enumerate(["progress.png", "completion.png"], start=1):
                write_valid_png(visual_root / name, token=token)
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": promoted_digest,
                        "screenshots": [
                            {"path": "progress.png", "surface": "install-progress"},
                            {"path": "completion.png", "surface": "completion"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            downloads_root = root / "downloads"
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            intake_request.write_text(
                json.dumps({"promoted_installer_sha256": promoted_digest}),
                encoding="utf-8",
            )

            with self.assertRaises(SystemExit) as raised:
                module.import_artifact(artifact, downloads_root, intake_request=intake_request)

            self.assertIn("startup receipt whose digest does not match the promoted installer", str(raised.exception))
            self.assertFalse((downloads_root / "startup-smoke" / "startup-smoke-avalonia-win-x64.receipt.json").exists())
            self.assertFalse((downloads_root / "visual-audit" / "windows-installer" / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").exists())

    def test_import_windows_installer_gold_proof_artifact_rejects_visual_only_bundle_without_valid_published_startup_receipt(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-missing-startup-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            visual_root = artifact / "Chummer.Portal" / "downloads" / "visual-audit" / "windows-installer"
            visual_root.mkdir(parents=True)
            for token, name in enumerate(["progress.png", "completion.png"], start=1):
                write_valid_png(visual_root / name, token=token)
            promoted_digest = "b" * 64
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": promoted_digest,
                        "screenshots": [
                            {"path": "progress.png", "surface": "install-progress"},
                            {"path": "completion.png", "surface": "completion"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            downloads_root = root / "downloads"
            intake_request = root / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            intake_request.write_text(
                json.dumps(
                    {
                        "promoted_installer_sha256": promoted_digest,
                        "startup_receipt_bundle_required": False,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(SystemExit) as raised:
                module.import_artifact(artifact, downloads_root, intake_request=intake_request)

        self.assertIn("complete generation publication requires the native startup receipt", str(raised.exception))

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
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactDigest": f"sha256:{'a' * 64}",
                    }
                ),
                encoding="utf-8",
            )
            write_valid_png(visual_root / "progress.png", token=1)
            write_valid_png(visual_root / "completion.png", token=2)
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": "a" * 64,
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
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactDigest": f"sha256:{'a' * 64}",
                    }
                ),
                encoding="utf-8",
            )
            for name in ["progress.png", "completion.png"]:
                write_valid_png(visual_root / name, token=1)
            (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "platform": "windows",
                        "hostClass": "native-windows-11",
                        "artifactSha256": "a" * 64,
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

            self.assertTrue(
                "byte-identical" in str(raised.exception)
                or "distinct image hashes" in str(raised.exception)
            )

    def test_import_windows_installer_gold_proof_artifact_rejects_absolute_and_parent_screenshot_escapes_before_copy(self) -> None:
        module = load_import_module()
        for escape_kind in ("absolute", "parent"):
            with self.subTest(escape_kind=escape_kind), tempfile.TemporaryDirectory(
                prefix=f"windows-proof-import-{escape_kind}-escape-"
            ) as temp_dir:
                root = Path(temp_dir)
                external = root / "operator-secret.txt"
                external.write_bytes(b"watcher-readable-secret")
                artifact, visual_root = write_windows_gold_proof_fixture(root, [])
                if escape_kind == "absolute":
                    screenshot_path = str(external)
                else:
                    escaped = visual_root.parent / "outside.png"
                    escaped.write_bytes(b"outside-bundle-surface")
                    screenshot_path = "../outside.png"
                (visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json").write_text(
                    json.dumps(
                        {
                            "status": "pass",
                            "platform": "windows",
                            "hostClass": "native-windows-11",
                            "artifactSha256": "a" * 64,
                            "screenshots": [
                                {"path": screenshot_path, "surface": "install-progress"}
                            ],
                        }
                    ),
                    encoding="utf-8",
                )
                downloads_root = root / "downloads"

                with self.assertRaises(SystemExit) as raised:
                    module.import_artifact(artifact, downloads_root)

                self.assertFalse(downloads_root.exists())
                self.assertTrue(
                    "bundle-relative" in str(raised.exception)
                    or "parent traversal" in str(raised.exception)
                )

    def test_import_windows_installer_gold_proof_artifact_rejects_symlink_hardlink_and_nonregular_screenshots(self) -> None:
        module = load_import_module()
        for member_kind in ("symlink", "hardlink", "fifo"):
            with self.subTest(member_kind=member_kind), tempfile.TemporaryDirectory(
                prefix=f"windows-proof-import-{member_kind}-"
            ) as temp_dir:
                root = Path(temp_dir)
                artifact, visual_root = write_windows_gold_proof_fixture(
                    root,
                    [{"path": "surface.png", "surface": "install-progress"}],
                )
                surface = visual_root / "surface.png"
                external = root / "external.png"
                external.write_bytes(b"external-surface")
                if member_kind == "symlink":
                    surface.symlink_to(external)
                elif member_kind == "hardlink":
                    os.link(external, surface)
                else:
                    os.mkfifo(surface)
                downloads_root = root / "downloads"

                with self.assertRaises(SystemExit) as raised:
                    module.import_artifact(artifact, downloads_root)

                self.assertFalse(downloads_root.exists())
                self.assertTrue(
                    any(
                        marker in str(raised.exception)
                        for marker in ("symlink", "hard-linked", "not a regular file")
                    )
                )

    def test_import_windows_installer_gold_proof_artifact_rejects_public_basename_collisions_before_copy(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-import-basename-collision-") as temp_dir:
            root = Path(temp_dir)
            rows = [
                {"path": "first/surface.png", "surface": "install-progress"},
                {"path": "second/SURFACE.png", "surface": "completion"},
            ]
            artifact, visual_root = write_windows_gold_proof_fixture(root, rows)
            (visual_root / "first").mkdir()
            (visual_root / "second").mkdir()
            write_valid_png(visual_root / "first" / "surface.png", token=1)
            write_valid_png(visual_root / "second" / "SURFACE.png", token=2)
            downloads_root = root / "downloads"

            with self.assertRaises(SystemExit) as raised:
                module.import_artifact(artifact, downloads_root)

            self.assertIn("basenames collide", str(raised.exception))
            self.assertFalse(downloads_root.exists())

    def test_import_windows_installer_gold_proof_artifact_accepts_only_real_png_and_jpeg_images(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-valid-images-") as temp_dir:
            root = Path(temp_dir)
            artifact, visual_root = write_windows_gold_proof_fixture(
                root,
                [
                    {"path": "capture.png", "surface": "install-progress"},
                    {"path": "capture.jpg", "surface": "completion"},
                ],
            )
            (visual_root / "capture.png").write_bytes(valid_png_bytes(token=21))
            (visual_root / "capture.jpg").write_bytes(valid_jpeg_bytes(token=22))
            downloads_root = root / "downloads"
            downloads_root.mkdir()

            summary = module.import_artifact(artifact, downloads_root)

            self.assertEqual(
                ["png", "jpeg"],
                [row["image"]["format"] for row in summary["screenshotBindings"]],
            )
            self.assertTrue(
                (downloads_root / "visual-audit" / "windows-installer" / "capture.png").is_file()
            )
            self.assertTrue(
                (downloads_root / "visual-audit" / "windows-installer" / "capture.jpg").is_file()
            )

    def test_import_windows_installer_gold_proof_artifact_rejects_empty_html_fake_and_undersized_images_before_public_mutation(self) -> None:
        module = load_import_module()
        scenarios = {
            "empty": ("surface.png", b"", "byte size"),
            "html": ("surface.png", b"<html><body>not an image</body></html>", "valid PNG or JPEG"),
            "truncated_png": ("surface.png", b"\x89PNG\r\n\x1a\n", "missing required image chunks"),
            "undersized": ("surface.png", valid_png_bytes(width=319, height=180), "width is outside"),
            "extension_mismatch": ("surface.jpg", valid_png_bytes(token=23), "does not match"),
        }
        for scenario, (name, image_bytes, message) in scenarios.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory(
                prefix=f"windows-proof-invalid-image-{scenario}-"
            ) as temp_dir:
                root = Path(temp_dir)
                artifact, visual_root = write_windows_gold_proof_fixture(
                    root,
                    [{"path": name, "surface": "install-progress"}],
                )
                (visual_root / name).write_bytes(image_bytes)
                downloads_root = root / "downloads"

                with self.assertRaisesRegex(SystemExit, message):
                    module.import_artifact(artifact, downloads_root)

                self.assertFalse(downloads_root.exists())

    def test_import_windows_installer_gold_proof_artifact_requires_native_windows_metadata_and_full_digests(self) -> None:
        module = load_import_module()
        scenarios = {
            "visual_platform": ("visual", "platform", "linux", "platform must be windows"),
            "visual_host": ("visual", "hostClass", "container-linux", "native Windows host"),
            "visual_digest": ("visual", "artifactSha256", "deadbeef", "full SHA-256"),
            "startup_platform": ("startup", "platform", "linux", "not native Windows proof"),
            "startup_host": ("startup", "hostClass", "wine", "not native Windows proof"),
            "startup_digest": ("startup", "artifactDigest", "sha256:deadbeef", "full SHA-256"),
        }
        for scenario, (target, key, value, message) in scenarios.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory(
                prefix=f"windows-proof-native-metadata-{scenario}-"
            ) as temp_dir:
                root = Path(temp_dir)
                artifact, visual_root = write_windows_gold_proof_fixture(
                    root,
                    [{"path": "surface.png", "surface": "install-progress"}],
                )
                write_valid_png(visual_root / "surface.png", token=24)
                if target == "visual":
                    metadata_path = visual_root / "WINDOWS_INSTALLER_VISUAL_AUDIT.source.json"
                else:
                    metadata_path = (
                        artifact
                        / "Chummer.Portal"
                        / "downloads"
                        / "startup-smoke"
                        / "startup-smoke-avalonia-win-x64.receipt.json"
                    )
                metadata = json.loads(metadata_path.read_text())
                metadata[key] = value
                metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
                downloads_root = root / "downloads"

                with self.assertRaisesRegex(SystemExit, message):
                    module.import_artifact(artifact, downloads_root)

                self.assertFalse(downloads_root.exists())

    def test_import_windows_installer_gold_proof_artifact_rejects_directory_artifact_without_inspection(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-directory-rejection-") as temp_dir:
            root = Path(temp_dir)
            artifact = root / "artifact"
            artifact.mkdir()
            sentinel = artifact / "operator-secret.txt"
            sentinel.write_text("must-not-be-parsed", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "directory proof artifacts are forbidden"):
                module.extracted_or_directory(artifact, root / "extract")

            self.assertEqual("must-not-be-parsed", sentinel.read_text(encoding="utf-8"))
            self.assertFalse((root / "extract").exists())

    def test_stable_bundle_snapshot_rejects_identity_drift_during_read(self) -> None:
        module = load_import_module()
        with tempfile.TemporaryDirectory(prefix="windows-proof-stable-read-drift-") as temp_dir:
            root = Path(temp_dir)
            source = root / "surface.png"
            source.write_bytes(b"stable-before-read")
            real_fstat = module.os.fstat
            fstat_calls = 0

            def drifting_fstat(descriptor):
                nonlocal fstat_calls
                fstat_calls += 1
                file_stat = real_fstat(descriptor)
                if fstat_calls != 2:
                    return file_stat
                drifted = mock.Mock()
                for name in (
                    "st_dev",
                    "st_ino",
                    "st_mode",
                    "st_nlink",
                    "st_size",
                    "st_mtime_ns",
                    "st_ctime_ns",
                ):
                    setattr(drifted, name, getattr(file_stat, name))
                drifted.st_ctime_ns += 1
                return drifted

            with mock.patch.object(module.os, "fstat", side_effect=drifting_fstat):
                with self.assertRaises(SystemExit) as raised:
                    module.stable_bundle_file_snapshot(source, root, "test screenshot")

        self.assertIn("changed during stable read", str(raised.exception))

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
        self.assertIn(
            "python3 scripts/materialize_operator_release_dashboard.py --release-ready-self-check",
            payload["post_import_gates"],
        )

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
        self.assertIn("Every bundle must contain both the native-Windows startup receipt", text)
        self.assertIn("Delivery must be a bounded zip", text)
        self.assertIn("WINDOWS_INSTALLER_VISUAL_AUDIT.source.json", text)
        self.assertIn("capture_windows_installer_gold_proof.ps1 -LaunchInstaller -CaptureVisualAudit", text)
        self.assertIn("verify_windows_installer_visual_audit.py", text)

    def test_downloads_runbook_documents_google_oauth_operator_proof_loop(self) -> None:
        runbook = Path("/docker/chummercomplete/chummer.run-services/docs/SELF_HOSTED_DOWNLOADS_RUNBOOK.md")
        text = runbook.read_text(encoding="utf-8")

        self.assertIn("/docker/chummercomplete", text)
        self.assertIn("Google OAuth linking operator proof", text)
        self.assertIn("must not publish downloads or promote a release", text)
        self.assertIn("materialize_google_oauth_linking_operator_evidence_request.py --base-url https://chummer.run", text)
        self.assertIn("verify_google_oauth_linking_operator_evidence_request.py", text)
        self.assertIn("CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt", text)
        self.assertIn("GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json", text)
        self.assertIn(".state/incoming_google_oauth_linking_operator_evidence", text)
        self.assertIn("auto_import_google_oauth_linking_operator_evidence.py", text)
        self.assertIn("verify_google_oauth_linking_proof.py --require-pass", text)
