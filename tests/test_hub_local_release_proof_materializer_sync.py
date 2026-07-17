from __future__ import annotations

import json
import importlib.util
import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MATERIALIZER = REPO_ROOT / "scripts" / "materialize_hub_local_release_proof.py"


def load_materializer_module():
    spec = importlib.util.spec_from_file_location("materialize_hub_local_release_proof_test", MATERIALIZER)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class HubLocalReleaseProofMaterializerSyncTests(unittest.TestCase):
    def test_public_json_writer_replaces_linked_or_mode_drifted_destination(self) -> None:
        module = load_materializer_module()
        with tempfile.TemporaryDirectory(prefix="hub-local-proof-public-json-") as temp_dir:
            temp_root = Path(temp_dir)
            output = temp_root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            hardlink = temp_root / "proof-hardlink.json"
            payload = '{"status":"pass"}\n'

            output.write_text("old\n", encoding="utf-8")
            output.chmod(0o664)
            os.link(output, hardlink)

            self.assertTrue(module._write_public_json_artifact(output, payload))
            self.assertEqual(payload, output.read_text(encoding="utf-8"))
            self.assertEqual("old\n", hardlink.read_text(encoding="utf-8"))
            self.assertEqual(1, output.stat().st_nlink)
            self.assertEqual(0o644, stat.S_IMODE(output.stat().st_mode))

            output.unlink()
            victim = temp_root / "unrelated.json"
            victim.write_text("keep\n", encoding="utf-8")
            output.symlink_to(victim)

            self.assertTrue(module._write_public_json_artifact(output, payload))
            self.assertFalse(output.is_symlink())
            self.assertEqual(payload, output.read_text(encoding="utf-8"))
            self.assertEqual("keep\n", victim.read_text(encoding="utf-8"))
            self.assertEqual(0o644, stat.S_IMODE(output.stat().st_mode))

    def test_materializer_includes_current_release_channel_binding(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hub-local-proof-release-channel-") as temp_dir:
            temp_root = Path(temp_dir)
            proof_path = temp_root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            readiness_path = temp_root / "FLAGSHIP_PRODUCT_READINESS.generated.json"
            release_channel_path = temp_root / "downloads" / "RELEASE_CHANNEL.generated.json"
            release_channel_path.parent.mkdir(parents=True, exist_ok=True)

            readiness_path.write_text(
                json.dumps(
                    {
                        "contract_name": "fleet.flagship_product_readiness",
                        "generated_at": "2026-06-30T01:00:00Z",
                        "status": "pass",
                        "scoped_status": "ready",
                        "missing_keys": [],
                        "scoped_missing_keys": [],
                        "completion_audit": {"status": "pass", "reason": "ready"},
                        "flagship_readiness_audit": {
                            "reason": "ready",
                            "missing_coverage_keys": [],
                            "scoped_missing_coverage_keys": [],
                        },
                    }
                ),
                encoding="utf-8",
            )
            release_channel_path.write_text(
                json.dumps(
                    {
                        "channelId": "preview",
                        "channel": "preview",
                        "version": "run-20260703-170551",
                        "releaseVersion": "run-20260703-170551",
                        "rolloutState": "promoted_preview",
                        "supportabilityState": "preview_supported",
                        "publishedAt": "2026-07-03T17:28:45Z",
                    }
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH"] = str(readiness_path)
            env["CHUMMER_HUB_RELEASE_CHANNEL_PATH"] = str(release_channel_path)

            completed = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    str(proof_path),
                    "http://127.0.0.1:8091",
                    "docker-compose.public-edge.yml",
                    "300",
                    "true",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=60,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout)
            payload = json.loads(proof_path.read_text(encoding="utf-8"))
            release_channel = payload.get("release_channel") or {}
            self.assertEqual("available", release_channel.get("status"))
            self.assertEqual(str(release_channel_path), release_channel.get("path"))
            self.assertEqual("preview", release_channel.get("channelId"))
            self.assertEqual("run-20260703-170551", release_channel.get("releaseVersion"))
            self.assertEqual("promoted_preview", release_channel.get("rolloutState"))
            self.assertEqual("preview_supported", release_channel.get("supportabilityState"))

    def test_materializer_marks_missing_release_channel_binding_unavailable(self) -> None:
        module = load_materializer_module()
        with tempfile.TemporaryDirectory(prefix="hub-local-proof-missing-release-channel-") as temp_dir:
            missing_path = Path(temp_dir) / "missing" / "RELEASE_CHANNEL.generated.json"
            old_env = os.environ.get("CHUMMER_HUB_RELEASE_CHANNEL_PATH")
            os.environ["CHUMMER_HUB_RELEASE_CHANNEL_PATH"] = str(missing_path)
            try:
                release_channel = module._load_release_channel_snapshot()
                self.assertEqual("unavailable", release_channel.get("status"))
                self.assertEqual(str(missing_path), release_channel.get("path"))
                self.assertEqual("", release_channel.get("releaseVersion"))
            finally:
                if old_env is None:
                    os.environ.pop("CHUMMER_HUB_RELEASE_CHANNEL_PATH", None)
                else:
                    os.environ["CHUMMER_HUB_RELEASE_CHANNEL_PATH"] = old_env

    def test_materializer_marks_empty_release_channel_binding_invalid(self) -> None:
        module = load_materializer_module()
        with tempfile.TemporaryDirectory(prefix="hub-local-proof-invalid-release-channel-") as temp_dir:
            release_channel_path = Path(temp_dir) / "RELEASE_CHANNEL.generated.json"
            release_channel_path.write_text("{}\n", encoding="utf-8")
            old_env = os.environ.get("CHUMMER_HUB_RELEASE_CHANNEL_PATH")
            os.environ["CHUMMER_HUB_RELEASE_CHANNEL_PATH"] = str(release_channel_path)
            try:
                release_channel = module._load_release_channel_snapshot()
                self.assertEqual("invalid", release_channel.get("status"))
                self.assertEqual("", release_channel.get("releaseVersion"))
            finally:
                if old_env is None:
                    os.environ.pop("CHUMMER_HUB_RELEASE_CHANNEL_PATH", None)
                else:
                    os.environ["CHUMMER_HUB_RELEASE_CHANNEL_PATH"] = old_env

    def test_materializer_marks_malformed_release_channel_binding_invalid(self) -> None:
        module = load_materializer_module()
        with tempfile.TemporaryDirectory(prefix="hub-local-proof-malformed-release-channel-") as temp_dir:
            release_channel_path = Path(temp_dir) / "RELEASE_CHANNEL.generated.json"
            release_channel_path.write_text("{not-json\n", encoding="utf-8")
            old_env = os.environ.get("CHUMMER_HUB_RELEASE_CHANNEL_PATH")
            os.environ["CHUMMER_HUB_RELEASE_CHANNEL_PATH"] = str(release_channel_path)
            try:
                release_channel = module._load_release_channel_snapshot()
                self.assertEqual("invalid", release_channel.get("status"))
                self.assertEqual("", release_channel.get("channelId"))
            finally:
                if old_env is None:
                    os.environ.pop("CHUMMER_HUB_RELEASE_CHANNEL_PATH", None)
                else:
                    os.environ["CHUMMER_HUB_RELEASE_CHANNEL_PATH"] = old_env

    def test_materializer_marks_non_object_release_channel_binding_invalid(self) -> None:
        module = load_materializer_module()
        with tempfile.TemporaryDirectory(prefix="hub-local-proof-non-object-release-channel-") as temp_dir:
            release_channel_path = Path(temp_dir) / "RELEASE_CHANNEL.generated.json"
            release_channel_path.write_text("[]\n", encoding="utf-8")
            old_env = os.environ.get("CHUMMER_HUB_RELEASE_CHANNEL_PATH")
            os.environ["CHUMMER_HUB_RELEASE_CHANNEL_PATH"] = str(release_channel_path)
            try:
                release_channel = module._load_release_channel_snapshot()
                self.assertEqual("invalid", release_channel.get("status"))
                self.assertEqual("", release_channel.get("releaseVersion"))
            finally:
                if old_env is None:
                    os.environ.pop("CHUMMER_HUB_RELEASE_CHANNEL_PATH", None)
                else:
                    os.environ["CHUMMER_HUB_RELEASE_CHANNEL_PATH"] = old_env

    def test_materializer_rejects_conflicting_release_channel_aliases(self) -> None:
        module = load_materializer_module()
        with tempfile.TemporaryDirectory(prefix="hub-local-proof-conflicting-release-channel-") as temp_dir:
            release_channel_path = Path(temp_dir) / "RELEASE_CHANNEL.generated.json"
            release_channel_path.write_text(
                json.dumps(
                    {
                        "channelId": "preview",
                        "channel": "stable",
                        "releaseVersion": "run-1",
                        "version": "run-2",
                        "rolloutState": "promoted_preview",
                        "supportabilityState": "preview_supported",
                        "publishedAt": "2026-07-03T17:28:45Z",
                    }
                ),
                encoding="utf-8",
            )
            old_env = os.environ.get("CHUMMER_HUB_RELEASE_CHANNEL_PATH")
            os.environ["CHUMMER_HUB_RELEASE_CHANNEL_PATH"] = str(release_channel_path)
            try:
                release_channel = module._load_release_channel_snapshot()
                self.assertEqual("invalid", release_channel.get("status"))
                self.assertEqual("", release_channel.get("channelId"))
                self.assertEqual("", release_channel.get("releaseVersion"))
            finally:
                if old_env is None:
                    os.environ.pop("CHUMMER_HUB_RELEASE_CHANNEL_PATH", None)
                else:
                    os.environ["CHUMMER_HUB_RELEASE_CHANNEL_PATH"] = old_env

    def test_materializer_rejects_naive_release_channel_timestamp(self) -> None:
        module = load_materializer_module()
        with tempfile.TemporaryDirectory(prefix="hub-local-proof-naive-release-channel-") as temp_dir:
            release_channel_path = Path(temp_dir) / "RELEASE_CHANNEL.generated.json"
            release_channel_path.write_text(
                json.dumps(
                    {
                        "channelId": "preview",
                        "channel": "preview",
                        "releaseVersion": "run-1",
                        "version": "run-1",
                        "rolloutState": "promoted_preview",
                        "supportabilityState": "preview_supported",
                        "publishedAt": "2026-07-03T17:28:45",
                    }
                ),
                encoding="utf-8",
            )
            old_env = os.environ.get("CHUMMER_HUB_RELEASE_CHANNEL_PATH")
            os.environ["CHUMMER_HUB_RELEASE_CHANNEL_PATH"] = str(release_channel_path)
            try:
                release_channel = module._load_release_channel_snapshot()
                self.assertEqual("invalid", release_channel.get("status"))
                self.assertEqual("", release_channel.get("publishedAt"))
            finally:
                if old_env is None:
                    os.environ.pop("CHUMMER_HUB_RELEASE_CHANNEL_PATH", None)
                else:
                    os.environ["CHUMMER_HUB_RELEASE_CHANNEL_PATH"] = old_env

    def test_materializer_allows_distinct_published_and_generated_timestamps(self) -> None:
        module = load_materializer_module()
        with tempfile.TemporaryDirectory(prefix="hub-local-proof-distinct-timestamps-") as temp_dir:
            release_channel_path = Path(temp_dir) / "RELEASE_CHANNEL.generated.json"
            release_channel_path.write_text(
                json.dumps(
                    {
                        "channelId": "preview",
                        "channel": "preview",
                        "releaseVersion": "run-1",
                        "version": "run-1",
                        "rolloutState": "promoted_preview",
                        "supportabilityState": "preview_supported",
                        "publishedAt": "2026-07-03T17:28:45.250+02:00",
                        "generatedAt": "2026-07-03T15:29:00Z",
                    }
                ),
                encoding="utf-8",
            )
            old_env = os.environ.get("CHUMMER_HUB_RELEASE_CHANNEL_PATH")
            os.environ["CHUMMER_HUB_RELEASE_CHANNEL_PATH"] = str(release_channel_path)
            try:
                release_channel = module._load_release_channel_snapshot()
                self.assertEqual("available", release_channel.get("status"))
                self.assertEqual("2026-07-03T17:28:45.250+02:00", release_channel.get("publishedAt"))
            finally:
                if old_env is None:
                    os.environ.pop("CHUMMER_HUB_RELEASE_CHANNEL_PATH", None)
                else:
                    os.environ["CHUMMER_HUB_RELEASE_CHANNEL_PATH"] = old_env

    def test_default_read_path_prefers_local_canonical_flagship_readiness_after_sync(self) -> None:
        module = load_materializer_module()
        with tempfile.TemporaryDirectory(prefix="hub-local-proof-read-path-") as temp_dir:
            temp_root = Path(temp_dir)
            local_readiness_path = temp_root / "local" / "FLAGSHIP_PRODUCT_READINESS.generated.json"
            fallback_readiness_path = temp_root / "fleet" / "FLAGSHIP_PRODUCT_READINESS.generated.json"
            local_readiness_path.parent.mkdir(parents=True, exist_ok=True)
            fallback_readiness_path.parent.mkdir(parents=True, exist_ok=True)
            local_readiness_path.write_text("{}", encoding="utf-8")
            fallback_readiness_path.write_text("{}", encoding="utf-8")

            old_default = module.DEFAULT_FLAGSHIP_READINESS_PATH
            old_fallback = module.FALLBACK_FLAGSHIP_READINESS_PATH
            old_env = os.environ.pop("CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH", None)
            try:
                module.DEFAULT_FLAGSHIP_READINESS_PATH = local_readiness_path
                module.FALLBACK_FLAGSHIP_READINESS_PATH = fallback_readiness_path
                self.assertEqual(local_readiness_path, module._flagship_readiness_path())
            finally:
                module.DEFAULT_FLAGSHIP_READINESS_PATH = old_default
                module.FALLBACK_FLAGSHIP_READINESS_PATH = old_fallback
                if old_env is not None:
                    os.environ["CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH"] = old_env

    def test_materializer_syncs_fresh_flagship_readiness_into_explicit_mirror_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hub-local-proof-") as temp_dir:
            temp_root = Path(temp_dir)
            proof_path = temp_root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            source_readiness_path = temp_root / "fleet" / "FLAGSHIP_PRODUCT_READINESS.generated.json"
            mirrored_readiness_path = temp_root / "local" / "FLAGSHIP_PRODUCT_READINESS.generated.json"
            source_readiness_path.parent.mkdir(parents=True, exist_ok=True)
            mirrored_readiness_path.parent.mkdir(parents=True, exist_ok=True)

            source_payload = {
                "contract_name": "fleet.flagship_product_readiness",
                "generated_at": "2026-06-27T19:45:08Z",
                "status": "pass",
                "scoped_status": "ready",
                "missing_keys": [],
                "scoped_missing_keys": [],
                "completion_audit": {
                    "status": "pass",
                    "reason": "Flagship product readiness proof is green.",
                },
                "flagship_readiness_audit": {
                    "reason": "Flagship product readiness proof is green.",
                    "missing_coverage_keys": [],
                    "scoped_missing_coverage_keys": [],
                },
            }
            mirrored_stale_payload = {
                "contract_name": "fleet.flagship_product_readiness",
                "generated_at": "2026-06-27T18:54:35Z",
                "status": "fail",
                "scoped_status": "fail",
                "missing_keys": ["desktop_client"],
                "scoped_missing_keys": ["desktop_client"],
                "completion_audit": {
                    "status": "fail",
                    "reason": "stale drift",
                },
                "flagship_readiness_audit": {
                    "reason": "stale drift",
                    "missing_coverage_keys": ["desktop_client"],
                    "scoped_missing_coverage_keys": ["desktop_client"],
                },
            }
            source_readiness_path.write_text(json.dumps(source_payload), encoding="utf-8")
            mirrored_readiness_path.write_text(json.dumps(mirrored_stale_payload), encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH"] = str(source_readiness_path)
            env["CHUMMER_LOCAL_FLAGSHIP_READINESS_SYNC_PATH"] = str(mirrored_readiness_path)

            completed = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    str(proof_path),
                    "http://127.0.0.1:8091",
                    "docker-compose.public-edge.yml",
                    "300",
                    "true",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=60,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout)
            payload = json.loads(proof_path.read_text(encoding="utf-8"))
            self.assertEqual("https://chummer.run", payload["base_url"])

            mirrored_payload = json.loads(mirrored_readiness_path.read_text(encoding="utf-8"))
            self.assertEqual(source_payload, mirrored_payload)

    def test_load_flagship_readiness_snapshot_prefers_fail_closed_override_reason(self) -> None:
        module = load_materializer_module()
        with tempfile.TemporaryDirectory(prefix="hub-local-proof-override-reason-") as temp_dir:
            temp_root = Path(temp_dir)
            readiness_path = temp_root / "FLAGSHIP_PRODUCT_READINESS.generated.json"
            readiness_path.write_text(
                json.dumps(
                    {
                        "contract_name": "fleet.flagship_product_readiness",
                        "generated_at": "2026-07-03T09:21:04Z",
                        "status": "fail",
                        "scoped_status": "fail",
                        "missing_keys": [],
                        "scoped_missing_keys": [],
                        "completion_audit": {
                            "status": "pass",
                            "reason": "Flagship product readiness proof is green.",
                        },
                        "flagship_readiness_audit": {
                            "status": "pass",
                            "reason": "Flagship product readiness proof is green.",
                            "coverage_gap_keys": [],
                            "scoped_coverage_gap_keys": [],
                        },
                        "gate_status_override": {
                            "reason": "Launch-critical nested blockers or coverage gaps remain; raw materializer status is not sufficient for a flagship launch claim.",
                            "launch_critical_nested_blockers": [
                                "final gold janitor state is 'fail'",
                                "final gold janitor verdict is 'NOT_GOLD'",
                                "live-backed gold claim is not allowed",
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )

            old_env = os.environ.get("CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH")
            try:
                os.environ["CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH"] = str(readiness_path)
                snapshot = module._load_flagship_readiness_snapshot()
            finally:
                if old_env is None:
                    os.environ.pop("CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH", None)
                else:
                    os.environ["CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH"] = old_env

            self.assertEqual("fail", snapshot["status"])
            self.assertIn("Launch-critical nested blockers or coverage gaps remain", snapshot["reason"])
            self.assertIn("final gold janitor verdict is 'NOT_GOLD'", snapshot["reason"])
            self.assertEqual(snapshot["reason"], snapshot["completion_audit_reason"])

    def test_materializer_does_not_overwrite_newer_local_flagship_readiness_with_older_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hub-local-proof-stale-source-") as temp_dir:
            temp_root = Path(temp_dir)
            proof_path = temp_root / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            source_readiness_path = temp_root / "fleet" / "FLAGSHIP_PRODUCT_READINESS.generated.json"
            mirrored_readiness_path = temp_root / "local" / "FLAGSHIP_PRODUCT_READINESS.generated.json"
            source_readiness_path.parent.mkdir(parents=True, exist_ok=True)
            mirrored_readiness_path.parent.mkdir(parents=True, exist_ok=True)

            source_payload = {
                "contract_name": "fleet.flagship_product_readiness",
                "generated_at": "2026-06-27T18:54:35Z",
                "status": "pass",
                "scoped_status": "ready",
                "missing_keys": [],
                "scoped_missing_keys": [],
                "completion_audit": {
                    "status": "pass",
                    "reason": "Flagship product readiness proof is green.",
                },
                "flagship_readiness_audit": {
                    "status": "pass",
                    "reason": "Flagship product readiness proof is green.",
                    "missing_coverage_keys": [],
                    "scoped_missing_coverage_keys": [],
                },
            }
            mirrored_newer_payload = {
                "contract_name": "fleet.flagship_product_readiness",
                "generated_at": "2026-07-02T15:39:44Z",
                "status": "fail",
                "scoped_status": "fail",
                "missing_keys": ["desktop_client"],
                "scoped_missing_keys": ["desktop_client"],
                "completion_audit": {
                    "status": "fail",
                    "reason": "Flagship product readiness planes are not green.",
                },
                "flagship_readiness_audit": {
                    "status": "fail",
                    "reason": "missing coverage: desktop_client",
                    "missing_coverage_keys": ["desktop_client"],
                    "scoped_missing_coverage_keys": ["desktop_client"],
                },
            }
            source_readiness_path.write_text(json.dumps(source_payload), encoding="utf-8")
            mirrored_readiness_path.write_text(json.dumps(mirrored_newer_payload), encoding="utf-8")

            env = os.environ.copy()
            env["CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH"] = str(source_readiness_path)
            env["CHUMMER_LOCAL_FLAGSHIP_READINESS_SYNC_PATH"] = str(mirrored_readiness_path)

            completed = subprocess.run(
                [
                    "python3",
                    str(MATERIALIZER),
                    str(proof_path),
                    "http://127.0.0.1:8091",
                    "docker-compose.public-edge.yml",
                    "300",
                    "true",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=60,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout)

            mirrored_payload = json.loads(mirrored_readiness_path.read_text(encoding="utf-8"))
            self.assertEqual(mirrored_newer_payload, mirrored_payload)
            self.assertIn("skipped local flagship readiness sync because source is older", completed.stdout)

    def test_materializer_syncs_default_published_proof_into_served_repo_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="hub-local-proof-served-sync-") as temp_dir:
            temp_root = Path(temp_dir)
            repo_script_path = temp_root / "scripts" / "materialize_hub_local_release_proof.py"
            proof_path = temp_root / ".codex-studio" / "published" / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            served_proof_path = (
                temp_root
                / "Chummer.Run.Api"
                / "wwwroot"
                / "proofs"
                / "mac-codex-release"
                / "HUB_LOCAL_RELEASE_PROOF.generated.json"
            )
            readiness_path = temp_root / "FLAGSHIP_PRODUCT_READINESS.generated.json"

            repo_script_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(MATERIALIZER, repo_script_path)
            readiness_path.write_text(
                json.dumps(
                    {
                        "contract_name": "fleet.flagship_product_readiness",
                        "generated_at": "2026-06-30T01:00:00Z",
                        "status": "pass",
                        "scoped_status": "ready",
                        "missing_keys": [],
                        "scoped_missing_keys": [],
                        "completion_audit": {"status": "pass", "reason": "ready"},
                        "flagship_readiness_audit": {
                            "reason": "ready",
                            "missing_coverage_keys": [],
                            "scoped_missing_coverage_keys": [],
                        },
                    }
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_FLAGSHIP_PRODUCT_READINESS_PATH"] = str(readiness_path)

            command = [
                "python3",
                str(repo_script_path),
                str(proof_path),
                "http://127.0.0.1:8091",
                "docker-compose.public-edge.yml",
                "300",
                "true",
            ]
            completed = subprocess.run(
                command,
                cwd=temp_root,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=60,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stdout)
            self.assertTrue(served_proof_path.is_file(), completed.stdout)
            self.assertEqual(
                json.loads(proof_path.read_text(encoding="utf-8")),
                json.loads(served_proof_path.read_text(encoding="utf-8")),
            )
            self.assertEqual(0o644, stat.S_IMODE(proof_path.stat().st_mode))
            self.assertEqual(0o644, stat.S_IMODE(served_proof_path.stat().st_mode))

            proof_path.chmod(0o664)
            served_proof_path.chmod(0o664)
            completed = subprocess.run(
                command,
                cwd=temp_root,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=60,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stdout)
            self.assertIn("hub local proof unchanged and still fresh", completed.stdout)
            self.assertEqual(0o644, stat.S_IMODE(proof_path.stat().st_mode))
            self.assertEqual(0o644, stat.S_IMODE(served_proof_path.stat().st_mode))


if __name__ == "__main__":
    unittest.main()
