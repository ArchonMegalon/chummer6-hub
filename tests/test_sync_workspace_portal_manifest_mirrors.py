from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "sync_workspace_portal_manifest_mirrors.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "sync_workspace_portal_manifest_mirrors",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SyncWorkspacePortalManifestMirrorsTests(unittest.TestCase):
    def test_parse_args_uses_process_argv_when_not_injected(self) -> None:
        module = load_module()

        with patch.object(
            sys,
            "argv",
            [
                "sync_workspace_portal_manifest_mirrors.py",
                "--workspace-root",
                "/tmp/workspace",
                "--source-root",
                "/tmp/source",
                "--name",
                "RELEASE_CHANNEL.generated.json",
                "--create-missing",
            ],
        ):
            args = module.parse_args()

        self.assertEqual("/tmp/workspace", args.workspace_root)
        self.assertEqual("/tmp/source", args.source_root)
        self.assertEqual(["RELEASE_CHANNEL.generated.json"], args.names)
        self.assertTrue(args.create_missing)

    def test_sync_updates_existing_targets_and_skips_missing_by_default(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="sync-workspace-manifests-") as temp_dir:
            workspace_root = Path(temp_dir)
            source_root = workspace_root / "chummer-hub-registry" / ".codex-studio" / "published"
            source_root.mkdir(parents=True)
            source_bytes = json.dumps({"version": "run-20260704-170602"}, indent=2).encode("utf-8")
            (source_root / "RELEASE_CHANNEL.generated.json").write_bytes(source_bytes)

            stale_target = (
                workspace_root
                / "chummer.run-services"
                / "Chummer.Portal"
                / "downloads"
                / "RELEASE_CHANNEL.generated.json"
            )
            stale_target.parent.mkdir(parents=True)
            stale_target.write_text('{"version":"run-test"}\n', encoding="utf-8")

            matching_target = (
                workspace_root
                / "chummer-presentation"
                / "Chummer.Portal"
                / "downloads"
                / "RELEASE_CHANNEL.generated.json"
            )
            matching_target.parent.mkdir(parents=True)
            matching_target.write_bytes(source_bytes)

            summary = module.sync_workspace_portal_manifest_mirrors(
                source_root,
                workspace_root,
                names=["RELEASE_CHANNEL.generated.json"],
            )

            self.assertEqual("pass", summary["status"])
            file_result = summary["files"][0]
            self.assertEqual("synced", file_result["status"])
            self.assertEqual(
                ["chummer.run-services/Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json"],
                file_result["updated_targets"],
            )
            self.assertEqual(
                ["chummer-presentation/Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json"],
                file_result["unchanged_targets"],
            )
            self.assertIn(
                "chummer6-ui/Chummer.Portal/downloads/RELEASE_CHANNEL.generated.json",
                file_result["skipped_missing_targets"],
            )
            self.assertIn(
                "chummer-presentation/Docker/Downloads/RELEASE_CHANNEL.generated.json",
                file_result["skipped_missing_targets"],
            )
            self.assertEqual(source_bytes, stale_target.read_bytes())

    def test_sync_can_create_missing_targets(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="sync-workspace-manifests-create-") as temp_dir:
            workspace_root = Path(temp_dir)
            source_root = workspace_root / "chummer-hub-registry" / ".codex-studio" / "published"
            source_root.mkdir(parents=True)
            source_bytes = json.dumps({"version": "run-20260704-170602"}, indent=2).encode("utf-8")
            (source_root / "releases.json").write_bytes(source_bytes)

            summary = module.sync_workspace_portal_manifest_mirrors(
                source_root,
                workspace_root,
                names=["releases.json"],
                create_missing=True,
            )

            self.assertEqual("pass", summary["status"])
            file_result = summary["files"][0]
            self.assertEqual("synced", file_result["status"])
            self.assertEqual([], file_result["skipped_missing_targets"])

            created_target = (
                workspace_root
                / "chummer6-ui"
                / ".codex-studio"
                / "published"
                / "portal"
                / "releases.json"
            )
            self.assertTrue(created_target.is_file())
            self.assertEqual(source_bytes, created_target.read_bytes())

    def test_sync_fails_closed_before_mutating_any_layout_v1_target(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="sync-workspace-manifests-v1-") as temp_dir:
            workspace_root = Path(temp_dir)
            source_root = workspace_root / "registry" / "published"
            source_root.mkdir(parents=True)
            source_bytes = b'{"version":"incoming"}\n'
            (source_root / "releases.json").write_bytes(source_bytes)

            unmarked_target = (
                workspace_root
                / "chummer.run-services"
                / "Chummer.Portal"
                / "downloads"
                / "releases.json"
            )
            unmarked_target.parent.mkdir(parents=True)
            original_bytes = b'{"version":"original"}\n'
            unmarked_target.write_bytes(original_bytes)
            marked_root = (
                workspace_root / "chummer-presentation" / "Chummer.Portal" / "downloads"
            )
            marked_root.mkdir(parents=True)
            (marked_root / ".release-shelf-layout-v1").write_text("v1\n", encoding="utf-8")
            (marked_root / "current.json").write_text("{}\n", encoding="utf-8")

            with self.assertRaisesRegex(
                module.LegacyReleaseShelfTargetError,
                "refusing legacy manifest mirror mutation",
            ):
                module.sync_workspace_portal_manifest_mirrors(
                    source_root,
                    workspace_root,
                    names=["releases.json"],
                )

            self.assertEqual(original_bytes, unmarked_target.read_bytes())
