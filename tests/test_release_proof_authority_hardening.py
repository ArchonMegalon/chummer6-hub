from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from contextlib import redirect_stderr
from io import StringIO
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER = REPO_ROOT / "scripts" / "materialize_hub_local_release_proof.py"
ORCHESTRATOR = REPO_ROOT / "scripts" / "release" / "verify_public_projection.py"
RELEASE_COMMIT = "1" * 40
READINESS_COMMIT = "2" * 40


def utc_timestamp(offset_seconds: int = 0) -> str:
    value = datetime.now(timezone.utc) + timedelta(seconds=offset_seconds)
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def write_json(path: Path, payload: dict) -> str:
    encoded = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def release_payload(*, generated_at: str | None = None) -> dict:
    timestamp = generated_at or utc_timestamp()
    return {
        "contractName": "Chummer.Hub.Registry.Contracts",
        "contract_name": "Chummer.Hub.Registry.Contracts",
        "generatedAt": timestamp,
        "generated_at": timestamp,
        "publishedAt": timestamp,
        "channelId": "preview",
        "channel": "preview",
        "releaseVersion": "run-test",
        "version": "run-test",
        "rolloutState": "promoted_preview",
        "supportabilityState": "review_required",
        "registryCommit": RELEASE_COMMIT,
        "registry_commit": RELEASE_COMMIT,
        "artifacts": [],
    }


def readiness_payload(*, generated_at: str | None = None) -> dict:
    timestamp = generated_at or utc_timestamp()
    return {
        "contract_name": "fleet.flagship_product_readiness",
        "generated_at": timestamp,
        "status": "fail",
        "scoped_status": "fail",
        "missing_keys": ["desktop_client"],
        "scoped_missing_keys": ["desktop_client"],
        "completion_audit": {"status": "fail", "reason": "review required"},
        "sourceCommit": READINESS_COMMIT,
        "source_commit": READINESS_COMMIT,
        "flagship_readiness_audit": {
            "reason": "review required",
            "missing_coverage_keys": ["desktop_client"],
            "scoped_missing_coverage_keys": ["desktop_client"],
        },
    }


def materializer_environment(root: Path, release: dict, readiness: dict) -> tuple[dict[str, str], Path, Path]:
    release_path = root / "RELEASE_CHANNEL.generated.json"
    readiness_path = root / "FLAGSHIP_PRODUCT_READINESS.generated.json"
    release_sha256 = write_json(release_path, release)
    readiness_sha256 = write_json(readiness_path, readiness)
    fleet_queue = root / "fleet-authority.yaml"
    design_queue = root / "design-authority.yaml"
    design_registry = root / "design-registry-authority.yaml"
    fleet_queue.write_text("items: []\n", encoding="utf-8")
    design_queue.write_text("items: []\n", encoding="utf-8")
    design_registry.write_text("entries: []\n", encoding="utf-8")
    environment = dict(os.environ)
    environment.update(
        {
            "CHUMMER_REQUIRE_CURRENT_RELEASE_INPUTS": "1",
            "CHUMMER_HUB_RELEASE_CHANNEL_PATH": str(release_path),
            "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_SHA256": release_sha256,
            "CHUMMER_HUB_RELEASE_CHANNEL_AUTHORITY": "registry://release/run-test",
            "CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_COMMIT": RELEASE_COMMIT,
            "CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH": str(readiness_path),
            "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_SHA256": readiness_sha256,
            "CHUMMER_FLAGSHIP_PRODUCT_READINESS_AUTHORITY": "fleet://readiness/run-test",
            "CHUMMER_FLAGSHIP_PRODUCT_READINESS_EXPECTED_COMMIT": READINESS_COMMIT,
            "CHUMMER_FLEET_QUEUE_STAGING_PATH": str(fleet_queue),
            "CHUMMER_FLEET_QUEUE_STAGING_EXPECTED_SHA256": hashlib.sha256(fleet_queue.read_bytes()).hexdigest(),
            "CHUMMER_FLEET_QUEUE_STAGING_AUTHORITY": "fleet://queue/run-test",
            "CHUMMER_DESIGN_QUEUE_STAGING_PATH": str(design_queue),
            "CHUMMER_DESIGN_QUEUE_STAGING_EXPECTED_SHA256": hashlib.sha256(design_queue.read_bytes()).hexdigest(),
            "CHUMMER_DESIGN_QUEUE_STAGING_AUTHORITY": "repo://design/run-test/queue",
            "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_PATH": str(design_registry),
            "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_EXPECTED_SHA256": hashlib.sha256(design_registry.read_bytes()).hexdigest(),
            "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_AUTHORITY": "repo://design/run-test/registry",
            "CHUMMER_HUB_LOCAL_PROOF_MUTATION_LOCK_PATH": str(root / ".lock" / "public-edge-mutation.lock"),
        }
    )
    return environment, release_path, readiness_path


def run_materializer(root: Path, environment: dict[str, str], output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(MATERIALIZER),
            str(output),
            "https://chummer.run",
            "docker-compose.yml",
            "120",
            "true",
        ],
        cwd=root,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=60,
    )


def load_orchestrator():
    spec = importlib.util.spec_from_file_location("verify_public_projection_test", ORCHESTRATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_materializer():
    spec = importlib.util.spec_from_file_location("materialize_hub_local_release_proof_test", MATERIALIZER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_queue_fixture() -> str:
    common = {
        "repo": "chummer6-hub",
        "wave": "W17",
        "status": "not_started",
        "allowed_paths": ["Chummer.Run.Api", "scripts", "tests"],
    }
    rendered = yaml.safe_dump(
        {
            "items": [
                {
                    **common,
                    "title": "Build public feedback, roadmap, changelog, support, and signal-intake surfaces that emit governed SignalToCanon packets.",
                    "task": "Build public feedback, roadmap, changelog, support, and signal-intake surfaces that emit governed SignalToCanon packets.",
                    "package_id": "next90-m125-hub-build-public-feedback-roadmap-changelog-support-and-sign",
                    "milestone_id": 125,
                    "work_task_id": "125.1",
                    "frontier_id": 4030850391,
                    "owned_surfaces": ["build_public_feedback_roadmap_changelog:hub"],
                },
                {
                    **common,
                    "title": "Define hosted proof contracts for Open Runs, Community Hub, public signal, community, and account-aware horizon conversions.",
                    "task": "Define hosted proof contracts for Open Runs, Community Hub, public signal, community, and account-aware horizon conversions.",
                    "package_id": "next90-m126-hub-define-hosted-proof-contracts-for-open-runs-shadowcaster",
                    "milestone_id": 126,
                    "work_task_id": "126.4",
                    "frontier_id": 6966685835,
                    "owned_surfaces": ["define_hosted_proof_contracts_for:hub"],
                },
            ]
        },
        sort_keys=False,
    )
    return rendered.replace("work_task_id: 125.1\n", "work_task_id: '125.1'\n").replace(
        "work_task_id: 126.4\n",
        "work_task_id: '126.4'\n",
    )


class ReleaseProofAuthorityHardeningTests(unittest.TestCase):
    def test_post_current_fsync_failure_reports_exact_reconcile_state(self) -> None:
        module = load_orchestrator()
        with tempfile.TemporaryDirectory(prefix="hub-proof-reconcile-") as temp_dir:
            root = Path(temp_dir)
            pointer_stage = root / ".CURRENT.stage"
            pointer_bytes = b'{"status":"pass"}\n'
            pointer_stage.write_bytes(pointer_bytes)
            snapshot_id = "public-projection-" + "a" * 64
            result = module.ProjectionSnapshot(
                current_pointer=root / "CURRENT.json",
                snapshot_directory=root / snapshot_id,
                snapshot_id=snapshot_id,
                snapshot_sha256="a" * 64,
                outputs={},
                output_sha256={},
            )
            result.snapshot_directory.mkdir()

            with (
                mock.patch.object(
                    module,
                    "_fsync_directory",
                    side_effect=module.ProjectionBlocked("injected CURRENT root fsync failure"),
                ),
                self.assertRaises(module.ProjectionCommitReconcileRequired) as raised,
            ):
                module._commit_current_pointer(
                    pointer_stage=pointer_stage,
                    current_pointer=result.current_pointer,
                    snapshot_root=root,
                    result=result,
                )

            self.assertEqual(result, raised.exception.snapshot)
            self.assertEqual(pointer_bytes, result.current_pointer.read_bytes())
            self.assertFalse(pointer_stage.exists())

            stderr = StringIO()
            with (
                mock.patch.object(module, "run_projection", side_effect=raised.exception),
                redirect_stderr(stderr),
            ):
                exit_code = module.main([])

            self.assertEqual(75, exit_code)
            receipt = json.loads(stderr.getvalue())
            self.assertEqual(
                "chummer.public_projection_commit_reconcile/v1",
                receipt["contractName"],
            )
            self.assertEqual("reconcile_required", receipt["status"])
            self.assertTrue(receipt["currentMutated"])
            self.assertEqual(snapshot_id, receipt["snapshotId"])
            self.assertNotIn("public projection blocked", stderr.getvalue())

    def test_real_materializer_is_relocatable_and_records_exact_authorities(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hub-proof-relocated-") as temp_dir:
            root = Path(temp_dir)
            environment, _release_path, _readiness_path = materializer_environment(
                root,
                release_payload(),
                readiness_payload(),
            )
            output = root / "output" / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            completed = run_materializer(root, environment, output)

            self.assertEqual(0, completed.returncode, completed.stderr)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(
                environment["CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_SHA256"],
                payload["authority_inputs"]["release_channel"]["sha256"],
            )
            self.assertEqual(
                "registry://release/run-test",
                payload["release_channel"]["path"],
            )
            self.assertEqual(
                "fleet://readiness/run-test",
                payload["desktop_client_readiness"]["source_path"],
            )
            self.assertEqual(
                {
                    "release_channel",
                    "flagship_readiness",
                    "fleet_queue",
                    "design_queue",
                    "design_successor_registry",
                },
                set(payload["authority_inputs"]),
            )
            serialized = json.dumps(payload, sort_keys=True)
            materializer = load_materializer()
            self.assertIsNone(materializer.MACHINE_LOCAL_PATH_PATTERN.search(serialized))
            self.assertIn("repo://ArchonMegalon/chummer6-hub/", serialized)
            self.assertIn("repo://ArchonMegalon/chummer6-ui/", serialized)
            self.assertFalse((root / ".lock" / "public-edge-mutation.lock").exists())

    def test_unknown_machine_root_is_rejected_instead_of_relabelled(self) -> None:
        module = load_materializer()
        with self.assertRaisesRegex(RuntimeError, "unknown machine-local path"):
            module._portable_public_value(
                {"evidence": ["/docker/unowned/private-proof.json"]}
            )

    def test_release_mode_requires_exact_release_and_readiness_commits(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hub-proof-commit-") as temp_dir:
            root = Path(temp_dir)
            environment, _release_path, _readiness_path = materializer_environment(
                root,
                release_payload(),
                readiness_payload(),
            )
            output = root / "HUB_LOCAL_RELEASE_PROOF.generated.json"

            environment.pop("CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_COMMIT")
            missing = run_materializer(root, environment, output)
            self.assertNotEqual(0, missing.returncode)
            self.assertIn("EXPECTED_COMMIT", missing.stderr)
            self.assertFalse(output.exists())

            environment["CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_COMMIT"] = "3" * 40
            mismatch = run_materializer(root, environment, output)
            self.assertNotEqual(0, mismatch.returncode)
            self.assertIn("does not match", mismatch.stderr)
            self.assertFalse(output.exists())

    def test_claimed_queue_authority_must_exist_and_match_digest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hub-proof-queue-authority-") as temp_dir:
            root = Path(temp_dir)
            environment, _release_path, _readiness_path = materializer_environment(
                root,
                release_payload(),
                readiness_payload(),
            )
            output = root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            fleet_path = Path(environment["CHUMMER_FLEET_QUEUE_STAGING_PATH"])
            fleet_path.write_text("items:\n  - drifted: true\n", encoding="utf-8")

            mismatch = run_materializer(root, environment, output)

            self.assertNotEqual(0, mismatch.returncode)
            self.assertIn("SHA256 does not match", mismatch.stderr)
            self.assertFalse(output.exists())

            fleet_path.unlink()

            completed = run_materializer(root, environment, output)

            self.assertNotEqual(0, completed.returncode)
            self.assertIn("fleet queue authority input is unavailable", completed.stderr)
            self.assertFalse(output.exists())

    def test_fractional_age_beyond_one_day_is_stale(self) -> None:
        module = load_materializer()
        timestamp = (
            datetime.now(timezone.utc) - timedelta(seconds=86400.9)
        ).isoformat()

        with self.assertRaisesRegex(RuntimeError, "is stale"):
            module._require_fresh_authority_timestamp(
                timestamp,
                label="fractional authority",
                max_age_seconds=86400,
                max_future_skew_seconds=300,
            )

    def test_alias_disagreement_cannot_launder_a_stale_timestamp_or_mutate_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hub-proof-alias-") as temp_dir:
            root = Path(temp_dir)
            release = release_payload()
            release["generated_at"] = "2020-01-01T00:00:00Z"
            environment, _release_path, _readiness_path = materializer_environment(
                root,
                release,
                readiness_payload(),
            )
            output = root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            sentinel = b"do-not-replace\n"
            output.write_bytes(sentinel)

            completed = run_materializer(root, environment, output)

            self.assertNotEqual(0, completed.returncode)
            self.assertIn("generated timestamp aliases disagree", completed.stderr)
            self.assertEqual(sentinel, output.read_bytes())
            self.assertNotIn("Traceback", completed.stderr)

    def test_release_mode_rejects_age_limit_above_one_day_before_writing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hub-proof-age-limit-") as temp_dir:
            root = Path(temp_dir)
            environment, _release_path, _readiness_path = materializer_environment(
                root,
                release_payload(),
                readiness_payload(),
            )
            environment["CHUMMER_RELEASE_PROOF_MAX_AGE_SECONDS"] = "100000"
            output = root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            sentinel = b"unchanged\n"
            output.write_bytes(sentinel)

            completed = run_materializer(root, environment, output)

            self.assertNotEqual(0, completed.returncode)
            self.assertIn("between 1 and 86400 seconds", completed.stderr)
            self.assertEqual(sentinel, output.read_bytes())

    def test_reported_98780_second_old_authority_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hub-proof-stale-") as temp_dir:
            root = Path(temp_dir)
            environment, _release_path, _readiness_path = materializer_environment(
                root,
                release_payload(generated_at=utc_timestamp(-98780)),
                readiness_payload(),
            )
            output = root / "HUB_LOCAL_RELEASE_PROOF.generated.json"

            completed = run_materializer(root, environment, output)

            self.assertNotEqual(0, completed.returncode)
            self.assertIn("maximum 86400s", completed.stderr)
            self.assertFalse(output.exists())

    def test_digest_mismatch_and_symlink_handoffs_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hub-proof-digest-") as temp_dir:
            root = Path(temp_dir)
            environment, release_path, _readiness_path = materializer_environment(
                root,
                release_payload(),
                readiness_payload(),
            )
            output = root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            environment["CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_SHA256"] = "0" * 64
            mismatch = run_materializer(root, environment, output)
            self.assertNotEqual(0, mismatch.returncode)
            self.assertFalse(output.exists())

            real_release = root / "real-release.json"
            real_release.write_bytes(release_path.read_bytes())
            release_path.unlink()
            release_path.symlink_to(real_release)
            environment["CHUMMER_HUB_RELEASE_CHANNEL_EXPECTED_SHA256"] = hashlib.sha256(
                real_release.read_bytes()
            ).hexdigest()
            linked = run_materializer(root, environment, output)
            self.assertNotEqual(0, linked.returncode)
            self.assertIn("authority input is unavailable", linked.stderr)
            self.assertFalse(output.exists())

    def test_transaction_keeps_destination_after_real_mutating_gates_then_failure(self) -> None:
        module = load_orchestrator()
        with tempfile.TemporaryDirectory(prefix="hub-proof-transaction-") as temp_dir:
            root = Path(temp_dir)
            environment, release_path, readiness_path = materializer_environment(
                root,
                release_payload(),
                readiness_payload(),
            )
            fleet_queue = root / "fleet.yaml"
            design_queue = root / "design.yaml"
            registry = root / "registry.yaml"
            fleet_queue.write_text(valid_queue_fixture(), encoding="utf-8")
            design_queue.write_text(valid_queue_fixture(), encoding="utf-8")
            registry.write_text("entries: []\n", encoding="utf-8")
            environment.update(
                {
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_OUTPUT": str(root / "authoritative.json"),
                    "CHUMMER_PUBLIC_PROJECTION_SNAPSHOT_ROOT": str(root),
                    "CHUMMER_HUB_RELEASE_CHANNEL_PATH": str(release_path),
                    "CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH": str(readiness_path),
                    "CHUMMER_FLEET_QUEUE_STAGING_PATH": str(fleet_queue),
                    "CHUMMER_FLEET_QUEUE_STAGING_EXPECTED_SHA256": hashlib.sha256(fleet_queue.read_bytes()).hexdigest(),
                    "CHUMMER_FLEET_QUEUE_STAGING_AUTHORITY": "fleet://queue/run-test",
                    "CHUMMER_DESIGN_QUEUE_STAGING_PATH": str(design_queue),
                    "CHUMMER_DESIGN_QUEUE_STAGING_EXPECTED_SHA256": hashlib.sha256(design_queue.read_bytes()).hexdigest(),
                    "CHUMMER_DESIGN_QUEUE_STAGING_AUTHORITY": "repo://design/run-test/queue",
                    "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_PATH": str(registry),
                    "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_EXPECTED_SHA256": hashlib.sha256(registry.read_bytes()).hexdigest(),
                    "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_AUTHORITY": "repo://design/run-test/registry",
                }
            )
            destination = Path(environment["CHUMMER_HUB_LOCAL_RELEASE_PROOF_OUTPUT"])
            sentinel = b"authoritative-sentinel\n"
            destination.write_bytes(sentinel)
            current_pointer = root / "CURRENT.json"
            current_sentinel = b"prior-current-sentinel\n"
            current_pointer.write_bytes(current_sentinel)
            fixed_proof_paths = (
                REPO_ROOT
                / ".codex-studio"
                / "published"
                / "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json",
                REPO_ROOT
                / ".codex-studio"
                / "published"
                / "NEXT90_M126_HUB_HOSTED_PROOF_CONTRACTS.generated.json",
            )
            fixed_proof_snapshots = {
                path: path.read_bytes() if path.is_file() else None
                for path in fixed_proof_paths
            }

            with self.assertRaises(module.ProjectionBlocked) as blocked:
                module.run_projection(
                    environment,
                    gate_commands=[
                        (
                            "real M125 materializing gate",
                            (
                                sys.executable,
                                "scripts/verify_next90_m125_hub_public_signal_packets.py",
                            ),
                        ),
                        (
                            "real M126 materializing gate",
                            (
                                sys.executable,
                                "scripts/verify_next90_m126_hub_hosted_proof_contracts.py",
                            ),
                        ),
                        (
                            "late synthetic failure",
                            (sys.executable, "-c", "raise SystemExit(17)"),
                        ),
                    ],
                )

            self.assertIn("late synthetic failure", str(blocked.exception))
            self.assertEqual(sentinel, destination.read_bytes())
            self.assertEqual(current_sentinel, current_pointer.read_bytes())
            self.assertEqual([], list(root.glob(".public-projection-*")))
            self.assertEqual([], list(root.glob("public-projection-*")))
            for path, expected in fixed_proof_snapshots.items():
                self.assertEqual(
                    expected,
                    path.read_bytes() if path.is_file() else None,
                    f"late gate failure mutated {path}",
                )

    def test_success_publishes_five_output_snapshot_and_one_current_pointer(self) -> None:
        module = load_orchestrator()
        with tempfile.TemporaryDirectory(prefix="hub-proof-success-") as temp_dir:
            root = Path(temp_dir)
            environment, release_path, readiness_path = materializer_environment(
                root,
                release_payload(),
                readiness_payload(),
            )
            fleet_queue = root / "fleet.yaml"
            design_queue = root / "design.yaml"
            registry = root / "registry.yaml"
            fleet_queue.write_text(valid_queue_fixture(), encoding="utf-8")
            design_queue.write_text(valid_queue_fixture(), encoding="utf-8")
            registry.write_text("entries: []\n", encoding="utf-8")
            legacy_output = root / "authoritative.json"
            legacy_sentinel = b"legacy-current-must-not-change\n"
            legacy_output.write_bytes(legacy_sentinel)
            environment.update(
                {
                    "CHUMMER_HUB_LOCAL_RELEASE_PROOF_OUTPUT": str(legacy_output),
                    "CHUMMER_PUBLIC_PROJECTION_SNAPSHOT_ROOT": str(root),
                    "CHUMMER_HUB_RELEASE_CHANNEL_PATH": str(release_path),
                    "CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH": str(readiness_path),
                    "CHUMMER_FLEET_QUEUE_STAGING_PATH": str(fleet_queue),
                    "CHUMMER_FLEET_QUEUE_STAGING_EXPECTED_SHA256": hashlib.sha256(fleet_queue.read_bytes()).hexdigest(),
                    "CHUMMER_FLEET_QUEUE_STAGING_AUTHORITY": "fleet://queue/run-test",
                    "CHUMMER_DESIGN_QUEUE_STAGING_PATH": str(design_queue),
                    "CHUMMER_DESIGN_QUEUE_STAGING_EXPECTED_SHA256": hashlib.sha256(design_queue.read_bytes()).hexdigest(),
                    "CHUMMER_DESIGN_QUEUE_STAGING_AUTHORITY": "repo://design/run-test/queue",
                    "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_PATH": str(registry),
                    "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_EXPECTED_SHA256": hashlib.sha256(registry.read_bytes()).hexdigest(),
                    "CHUMMER_DESIGN_SUCCESSOR_REGISTRY_AUTHORITY": "repo://design/run-test/registry",
                }
            )
            fake_windows_command = (
                sys.executable,
                "-c",
                (
                    "import json,os,pathlib; "
                    "pathlib.Path(os.environ['CHUMMER_PUBLIC_PROJECTION_WINDOWS_OUTPUT']).write_text("
                    "json.dumps({'contract_name':'chummer.live_public_windows_installer','status':'pass'})+'\\n',"
                    "encoding='utf-8')"
                ),
            )

            committed = False
            transaction_events: list[str] = []
            original_replace = module.os.replace
            original_remove = module._remove_private_stage
            original_fsync_directory = module._fsync_directory
            original_snapshot_rename = module._exclusive_snapshot_rename

            def tracked_commit(source: Path, destination: Path) -> None:
                nonlocal committed
                original_replace(source, destination)
                if destination == root / "CURRENT.json":
                    transaction_events.append("replace:CURRENT")
                    committed = True

            def tracked_snapshot_rename(source: Path, destination: Path) -> None:
                original_snapshot_rename(source, destination)
                transaction_events.append("rename:snapshot")

            def guarded_remove(path: Path) -> None:
                self.assertFalse(committed, "stage cleanup ran after CURRENT commit")
                original_remove(path)
                transaction_events.append("cleanup:stage")

            def guarded_fsync(path: Path, *, label: str) -> None:
                original_fsync_directory(path, label=label)
                transaction_events.append(f"fsync:{label}")

            with (
                mock.patch.object(module.os, "replace", side_effect=tracked_commit),
                mock.patch.object(
                    module,
                    "_exclusive_snapshot_rename",
                    side_effect=tracked_snapshot_rename,
                ),
                mock.patch.object(module, "_remove_private_stage", side_effect=guarded_remove),
                mock.patch.object(module, "_fsync_directory", side_effect=guarded_fsync),
            ):
                result = module.run_projection(
                    environment,
                    gate_commands=[
                        (
                            "real M125 materializing gate",
                            (sys.executable, "scripts/verify_next90_m125_hub_public_signal_packets.py"),
                        ),
                        (
                            "real M126 materializing gate",
                            (sys.executable, "scripts/verify_next90_m126_hub_hosted_proof_contracts.py"),
                        ),
                        ("test live Windows receipt", fake_windows_command),
                    ],
                )

            self.assertTrue(committed)
            snapshot_rename_index = transaction_events.index("rename:snapshot")
            snapshot_root_fsync_index = transaction_events.index(
                "fsync:public projection snapshot commit root"
            )
            current_replace_index = transaction_events.index("replace:CURRENT")
            current_root_fsync_index = transaction_events.index(
                "fsync:public projection CURRENT commit root"
            )
            self.assertLess(snapshot_rename_index, snapshot_root_fsync_index)
            self.assertLess(snapshot_root_fsync_index, current_replace_index)
            self.assertLess(current_replace_index, current_root_fsync_index)
            self.assertEqual(
                [
                    "replace:CURRENT",
                    "fsync:public projection CURRENT commit root",
                ],
                transaction_events[current_replace_index:],
                "only the durability fsync may run after CURRENT replacement",
            )
            self.assertEqual(legacy_sentinel, legacy_output.read_bytes())
            self.assertEqual(root / "CURRENT.json", result.current_pointer)
            self.assertEqual(set(module.SNAPSHOT_OUTPUT_NAMES), set(result.outputs))
            self.assertTrue(all(path.is_file() for path in result.outputs.values()))
            resolved = module.resolve_current_snapshot(root)
            self.assertEqual(result.snapshot_id, resolved.snapshot_id)
            self.assertEqual(result.snapshot_sha256, resolved.snapshot_sha256)
            self.assertEqual(result.outputs, resolved.outputs)
            self.assertEqual(
                result.outputs["HUB_LOCAL_RELEASE_PROOF.generated.json"].read_bytes(),
                result.outputs["HUB_SERVED_RELEASE_PROOF.generated.json"].read_bytes(),
            )
            self.assertEqual([], list(root.glob(".public-projection-*")))

    def test_concurrent_publication_is_rejected_before_any_stage_is_created(self) -> None:
        module = load_orchestrator()
        with tempfile.TemporaryDirectory(prefix="hub-proof-lock-") as temp_dir:
            root = Path(temp_dir)
            lock_descriptor = module._acquire_publication_lock(root)
            environment = dict(os.environ)
            environment["CHUMMER_PUBLIC_PROJECTION_SNAPSHOT_ROOT"] = str(root)
            try:
                blocked = subprocess.run(
                    [sys.executable, str(ORCHESTRATOR)],
                    cwd=REPO_ROOT,
                    env=environment,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=30,
                )
            finally:
                module._release_publication_lock(lock_descriptor)

            self.assertEqual(1, blocked.returncode)
            self.assertIn("another public projection publication transaction is active", blocked.stderr)
            self.assertFalse((root / "CURRENT.json").exists())
            self.assertEqual([], list(root.glob(".public-projection-*")))

            after_release = subprocess.run(
                [sys.executable, str(ORCHESTRATOR)],
                cwd=REPO_ROOT,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
                timeout=30,
            )
            self.assertEqual(1, after_release.returncode)
            self.assertNotIn("another public projection publication transaction is active", after_release.stderr)
            self.assertIn("public projection requires CHUMMER_HUB_RELEASE_CHANNEL_", after_release.stderr)

    def test_publication_lock_rejects_group_or_world_writable_root(self) -> None:
        module = load_orchestrator()
        with tempfile.TemporaryDirectory(prefix="hub-proof-unsafe-root-") as temp_dir:
            root = Path(temp_dir)
            root.chmod(0o777)

            with self.assertRaisesRegex(
                module.ProjectionBlocked,
                "current-user-owned and not group/world writable",
            ):
                module._acquire_publication_lock(root)

            self.assertFalse((root / module.PUBLICATION_LOCK_NAME).exists())


if __name__ == "__main__":
    unittest.main()
