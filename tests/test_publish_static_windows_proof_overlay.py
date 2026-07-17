from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "publish_static_windows_proof_overlay.py"
SPEC = importlib.util.spec_from_file_location("publish_static_windows_proof_overlay", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)

FIXTURE_SCRIPT = REPO_ROOT / "tests" / "test_materialize_windows_proof_bundle.py"
FIXTURE_SPEC = importlib.util.spec_from_file_location(
    "windows_proof_materializer_fixture",
    FIXTURE_SCRIPT,
)
assert FIXTURE_SPEC is not None and FIXTURE_SPEC.loader is not None
FIXTURE = importlib.util.module_from_spec(FIXTURE_SPEC)
sys.modules[FIXTURE_SPEC.name] = FIXTURE
FIXTURE_SPEC.loader.exec_module(FIXTURE)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StaticWindowsProofOverlayPublisherTests(unittest.TestCase):
    SUCCESSFUL_VERIFICATION = {
        "canonicalIdentityUnchanged": True,
        "proofOnlyPostureValidated": True,
        "sourceBundleExactMatch": True,
        "targetBytesUnchanged": True,
        "targetTreeComplete": True,
    }

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="windows-proof-static-publish-")
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "bundle"
        self.overlay = self.root / "portal-overlay"
        self.canonical = self.root / "canonical"
        self.receipts = self.root / "receipts"
        self.bundle.mkdir()
        self.overlay.mkdir()
        self.canonical.mkdir()
        self.receipts.mkdir()
        (self.overlay / "wwwroot").mkdir()
        (self.overlay / "Chummer.Run.Api.dll").write_bytes(b"portal-marker")
        self.version = "run-20260716-115521"
        self.canonical_manifest = self.canonical / "RELEASE_CHANNEL.generated.json"
        self.canonical_manifest.write_text(
            json.dumps(
                {
                    "schemaVersion": 1,
                    "version": "run-20260715-140426",
                    "releaseVersion": "run-20260715-140426",
                    "channel": "preview",
                    "publishedAt": "2026-07-15T14:06:48Z",
                }
            ),
            encoding="utf-8",
        )
        self.files = self._write_bundle()
        self.manifest = self.bundle / "WINDOWS_PROOF_MANIFEST.generated.json"
        self.manifest_digest = sha256(self.manifest)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_bundle(self) -> dict[str, Path]:
        stage, _, _ = FIXTURE.make_stage(self.root)
        self.bundle.rmdir()
        result = FIXTURE.run_materializer(stage, self.bundle)
        if result.returncode != 0:
            raise AssertionError(result.stderr)
        manifest = json.loads(
            (self.bundle / "WINDOWS_PROOF_MANIFEST.generated.json").read_text(
                encoding="utf-8"
            )
        )
        return {
            str(row["relativePath"]): self.bundle / str(row["relativePath"])
            for row in manifest["artifacts"]
        }

    def _command(
        self,
        receipt: Path | None = None,
        *,
        cf_gated: bool = True,
        reconcile_existing: bool = False,
    ) -> list[str]:
        command = [
            sys.executable,
            str(SCRIPT),
            "--bundle-root",
            str(self.bundle),
            "--overlay-root",
            str(self.overlay),
            "--canonical-root",
            str(self.canonical),
            "--receipt",
            str(receipt or self.receipts / "publication.json"),
            "--expected-candidate-version",
            self.version,
            "--expected-manifest-sha256",
            self.manifest_digest,
        ]
        if cf_gated:
            command.append("--cf-access-gated")
        if reconcile_existing:
            command.append("--reconcile-existing")
        return command

    @property
    def target(self) -> Path:
        return (
            self.overlay
            / "wwwroot"
            / "downloads"
            / "proof"
            / "windows"
            / "candidates"
            / self.version
        )

    def _install_manual_candidate(self) -> None:
        self.target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.bundle, self.target)
        os.chmod(self.target, 0o755)

    def _tree_snapshot(self, root: Path) -> dict[str, tuple[int, int, int, int, str | None]]:
        snapshot: dict[str, tuple[int, int, int, int, str | None]] = {}
        for path in [root, *sorted(root.rglob("*"))]:
            metadata = path.lstat()
            relative = "." if path == root else path.relative_to(root).as_posix()
            digest = sha256(path) if stat.S_ISREG(metadata.st_mode) else None
            snapshot[relative] = (
                stat.S_IMODE(metadata.st_mode),
                metadata.st_size,
                metadata.st_mtime_ns,
                metadata.st_ino,
                digest,
            )
        return snapshot

    def _target_snapshot(self) -> dict[str, tuple[int, int, int, int, str | None]]:
        return self._tree_snapshot(self.target)

    def test_reconciles_existing_candidate_without_modifying_target_tree(self) -> None:
        self._install_manual_candidate()
        receipt_path = self.receipts / "reconciled.json"
        target_before = self._target_snapshot()
        canonical_before = self._tree_snapshot(self.canonical)

        completed = subprocess.run(
            self._command(receipt_path, reconcile_existing=True),
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertIn("windows_proof_static_reconcile:completed", completed.stdout)
        self.assertEqual(target_before, self._target_snapshot())
        self.assertEqual(canonical_before, self._tree_snapshot(self.canonical))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual("completed", receipt["state"])
        self.assertEqual("reconcile_existing", receipt["operation"])
        self.assertEqual(receipt["canonicalBefore"], receipt["canonicalAfter"])
        self.assertEqual(receipt["targetIdentityBefore"], receipt["targetIdentityAfter"])
        self.assertEqual(self.SUCCESSFUL_VERIFICATION, receipt["verification"])
        self.assertEqual(0o600, stat.S_IMODE(receipt_path.stat().st_mode))

    def test_reconcile_refuses_valid_but_byte_mismatched_candidate(self) -> None:
        self._install_manual_candidate()
        installer = self.target / "files/chummer-avalonia-win-x64-installer.exe"
        installer.write_bytes(b"different-valid-proof-installer")
        target_manifest = self.target / self.manifest.name
        manifest = json.loads(target_manifest.read_text(encoding="utf-8"))
        row = next(item for item in manifest["artifacts"] if item["kind"] == "installer")
        row["size"] = installer.stat().st_size
        row["sha256"] = sha256(installer)
        provenance_row = next(
            item
            for item in manifest["artifacts"]
            if item["kind"] == "build_provenance_receipt"
        )
        provenance_path = self.target / provenance_row["relativePath"]
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        provenance["subjects"][0]["artifact_sha256"] = row["sha256"]
        provenance["subjects"][0]["artifact_size_bytes"] = row["size"]
        provenance_path.write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        provenance_row["size"] = provenance_path.stat().st_size
        provenance_row["sha256"] = sha256(provenance_path)
        target_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        target_before = self._target_snapshot()
        receipt_path = self.receipts / "mismatch.json"

        refused = subprocess.run(
            self._command(receipt_path, reconcile_existing=True),
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(0, refused.returncode)
        self.assertIn("does not exactly match", refused.stderr)
        self.assertEqual(target_before, self._target_snapshot())
        self.assertFalse(receipt_path.exists())

    def test_reconcile_refuses_undeclared_extra_file(self) -> None:
        self._install_manual_candidate()
        extra = self.target / "files/undeclared-proof.txt"
        extra.write_bytes(b"must-not-be-present")
        target_before = self._target_snapshot()
        receipt_path = self.receipts / "extra-file.json"

        refused = subprocess.run(
            self._command(receipt_path, reconcile_existing=True),
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(0, refused.returncode)
        self.assertIn("undeclared, missing, or stale files", refused.stderr)
        self.assertEqual(target_before, self._target_snapshot())
        self.assertFalse(receipt_path.exists())

        extra.unlink()
        (self.target / "undeclared-empty-directory").mkdir()
        directory_receipt = self.receipts / "extra-directory.json"
        refused_directory = subprocess.run(
            self._command(directory_receipt, reconcile_existing=True),
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, refused_directory.returncode)
        self.assertIn("undeclared, missing, or stale directories", refused_directory.stderr)
        self.assertFalse(directory_receipt.exists())

    def test_reconcile_refuses_candidate_symlink(self) -> None:
        self._install_manual_candidate()
        installer = self.target / "files/chummer-avalonia-win-x64-installer.exe"
        external = self.root / "external-installer.exe"
        external.write_bytes(installer.read_bytes())
        installer.unlink()
        installer.symlink_to(external)
        receipt_path = self.receipts / "target-symlink.json"

        refused = subprocess.run(
            self._command(receipt_path, reconcile_existing=True),
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(0, refused.returncode)
        self.assertIn("symbolic link", refused.stderr)
        self.assertTrue(installer.is_symlink())
        self.assertFalse(receipt_path.exists())

    def test_publishes_append_only_candidate_and_durable_identity_receipt(self) -> None:
        receipt_path = self.receipts / "publication.json"
        canonical_before = self._tree_snapshot(self.canonical)
        source_before = {relative: sha256(path) for relative, path in self.files.items()}

        completed = subprocess.run(
            self._command(receipt_path),
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, completed.returncode, completed.stderr)
        self.assertTrue(self.target.is_dir())
        self.assertEqual(0o755, stat.S_IMODE(self.target.stat().st_mode))
        self.assertEqual(canonical_before, self._tree_snapshot(self.canonical))
        self.assertEqual(source_before, {relative: sha256(path) for relative, path in self.files.items()})
        for relative, source in self.files.items():
            self.assertEqual(sha256(source), sha256(self.target / relative))
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual("chummer.windows-proof.static-overlay-publication/v1", receipt["schemaVersion"])
        self.assertEqual("completed", receipt["state"])
        self.assertEqual("publish_new", receipt["operation"])
        self.assertEqual(self.manifest_digest, receipt["manifestSha256"])
        self.assertEqual(receipt["canonicalBefore"], receipt["canonicalAfter"])
        self.assertIsNone(receipt["targetIdentityBefore"])
        self.assertEqual(
            MODULE.bundle_identity(MODULE.validate_bundle(self.target)),
            receipt["targetIdentityAfter"],
        )
        self.assertEqual(self.SUCCESSFUL_VERIFICATION, receipt["verification"])
        self.assertEqual("review_required", json.loads((self.target / self.manifest.name).read_text())["supportabilityState"])
        self.assertEqual(0o600, stat.S_IMODE(receipt_path.stat().st_mode))

        replay = subprocess.run(
            self._command(self.receipts / "replay.json"),
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, replay.returncode)
        self.assertIn("append-only candidate already exists", replay.stderr)
        self.assertFalse((self.receipts / "replay.json").exists())

    def test_requires_cf_assertion_and_rejects_optimistic_posture(self) -> None:
        missing_cf = subprocess.run(
            self._command(cf_gated=False),
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, missing_cf.returncode)
        self.assertIn("Cloudflare Access gate", missing_cf.stderr)
        self.assertFalse(self.target.exists())

        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        manifest["supportabilityState"] = "preview_supported"
        manifest["publicTrustPosture"] = "preview"
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        self.manifest_digest = sha256(self.manifest)
        optimistic = subprocess.run(
            self._command(self.receipts / "optimistic.json"),
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, optimistic.returncode)
        self.assertIn("supportabilityState", optimistic.stderr)
        self.assertFalse(self.target.exists())

    def test_rejects_download_or_missing_payload_acquisition_mode(self) -> None:
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        for invalid_mode in ("download", None):
            with self.subTest(payload_acquisition_mode=invalid_mode):
                invalid = deepcopy(manifest)
                if invalid_mode is None:
                    invalid["compatibilitySmoke"].pop("payloadAcquisitionMode")
                else:
                    invalid["compatibilitySmoke"]["payloadAcquisitionMode"] = invalid_mode
                with self.assertRaisesRegex(ValueError, "compatibility smoke posture"):
                    MODULE.validate_manifest_posture(invalid)

    def test_rejects_digest_drift_traversal_and_symlinks(self) -> None:
        installer = self.files["files/chummer-avalonia-win-x64-installer.exe"]
        installer.write_bytes(b"changed-after-manifest")
        drift = subprocess.run(
            self._command(self.receipts / "drift.json"),
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, drift.returncode)
        self.assertIn("artifact bytes do not match", drift.stderr)
        self.assertFalse(self.target.exists())

        self.temporary.cleanup()
        self.setUp()
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        manifest["artifacts"][0]["relativePath"] = "files/../escape.exe"
        manifest["artifacts"][0]["fileName"] = "escape.exe"
        self.manifest.write_text(json.dumps(manifest), encoding="utf-8")
        self.manifest_digest = sha256(self.manifest)
        traversal = subprocess.run(
            self._command(self.receipts / "traversal.json"),
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, traversal.returncode)
        self.assertIn("nonportable relativePath", traversal.stderr)

        self.temporary.cleanup()
        self.setUp()
        external = self.root / "external-installer.exe"
        external.write_bytes(b"external")
        installer = self.files["files/chummer-avalonia-win-x64-installer.exe"]
        installer.unlink()
        installer.symlink_to(external)
        symlink = subprocess.run(
            self._command(self.receipts / "symlink.json"),
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, symlink.returncode)
        self.assertIn("symbolic link", symlink.stderr)

    def test_refuses_canonical_overlap_and_existing_target_symlink(self) -> None:
        overlapping_overlay = self.canonical / "portal-overlay"
        overlapping_overlay.mkdir()
        (overlapping_overlay / "wwwroot").mkdir()
        (overlapping_overlay / "Chummer.Run.Api.dll").write_bytes(b"marker")
        command = self._command(self.receipts / "overlap.json")
        command[command.index(str(self.overlay))] = str(overlapping_overlay)
        overlap = subprocess.run(command, cwd=REPO_ROOT, text=True, capture_output=True, check=False)
        self.assertNotEqual(0, overlap.returncode)
        self.assertIn("overlay and canonical roots must be physically separate", overlap.stderr)

        candidate_parent = self.target.parent
        candidate_parent.mkdir(parents=True)
        external = self.root / "external-target"
        external.mkdir()
        self.target.symlink_to(external, target_is_directory=True)
        target_link = subprocess.run(
            self._command(self.receipts / "target-link.json"),
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, target_link.returncode)
        self.assertIn("append-only candidate already exists", target_link.stderr)

    def test_canonical_drift_is_recorded_and_never_claimed_complete(self) -> None:
        receipt_path = self.receipts / "canonical-drift.json"
        request = MODULE.PublicationRequest(
            bundle_root=self.bundle,
            overlay_root=self.overlay,
            canonical_root=self.canonical,
            receipt_path=receipt_path,
            expected_candidate_version=self.version,
            expected_manifest_sha256=self.manifest_digest,
            cf_access_gated=True,
            public_origin="https://chummer.run",
        )
        before = {"identitySha256": "a" * 64}
        after = {"identitySha256": "b" * 64}

        with mock.patch.object(
            MODULE,
            "capture_canonical_identity",
            side_effect=[before, before, after],
        ):
            with self.assertRaisesRegex(ValueError, "canonical release identity changed"):
                MODULE.publish(request)

        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual("canonical_drift_detected", receipt["state"])
        self.assertEqual("publish_new", receipt["operation"])
        self.assertEqual(before, receipt["canonicalBefore"])
        self.assertEqual(after, receipt["canonicalAfter"])
        self.assertIsNone(receipt["targetIdentityBefore"])
        self.assertNotIn("targetIdentityAfter", receipt)
        self.assertNotIn("verification", receipt)
        self.assertNotIn("completedAt", receipt)
        self.assertTrue(self.target.is_dir())

    def test_activation_failure_leaves_durable_recovery_receipt_and_no_candidate(self) -> None:
        receipt_path = self.receipts / "activation-failure.json"
        request = MODULE.PublicationRequest(
            bundle_root=self.bundle,
            overlay_root=self.overlay,
            canonical_root=self.canonical,
            receipt_path=receipt_path,
            expected_candidate_version=self.version,
            expected_manifest_sha256=self.manifest_digest,
            cf_access_gated=True,
            public_origin="https://chummer.run",
        )
        with mock.patch.object(
            MODULE,
            "atomic_rename_noreplace",
            side_effect=OSError("simulated activation failure"),
        ):
            with self.assertRaisesRegex(OSError, "simulated activation failure"):
                MODULE.publish(request)

        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual("activation_started", receipt["state"])
        self.assertEqual("publish_new", receipt["operation"])
        self.assertIsNone(receipt["targetIdentityBefore"])
        self.assertNotIn("targetIdentityAfter", receipt)
        self.assertNotIn("verification", receipt)
        self.assertNotIn("completedAt", receipt)
        self.assertFalse(self.target.exists())
        staging = list(self.target.parent.glob(f".{self.version}.*.staging"))
        self.assertEqual([], staging)

    def test_pre_activation_failure_leaves_no_receipt_or_candidate(self) -> None:
        receipt_path = self.receipts / "pre-activation-failure.json"
        request = MODULE.PublicationRequest(
            bundle_root=self.bundle,
            overlay_root=self.overlay,
            canonical_root=self.canonical,
            receipt_path=receipt_path,
            expected_candidate_version=self.version,
            expected_manifest_sha256=self.manifest_digest,
            cf_access_gated=True,
            public_origin="https://chummer.run",
        )
        canonical_before = self._tree_snapshot(self.canonical)

        with mock.patch.object(
            MODULE,
            "copy_verified_file",
            side_effect=OSError("simulated staging failure"),
        ):
            with self.assertRaisesRegex(OSError, "simulated staging failure"):
                MODULE.publish(request)

        self.assertFalse(receipt_path.exists())
        self.assertFalse(self.target.exists())
        self.assertEqual(canonical_before, self._tree_snapshot(self.canonical))
        self.assertEqual([], list(self.target.parent.glob(f".{self.version}.*.staging")))


if __name__ == "__main__":
    unittest.main()
