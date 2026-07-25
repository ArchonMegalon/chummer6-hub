from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "verify_next90_m125_hub_public_signal_packets.py"
SOURCE_FILES = [
    "Chummer.Run.Api/Contracts/SignalToCanonPacketContracts.cs",
    "Chummer.Run.Api/Services/Support/PublicSignalToCanonPacketService.cs",
    "Chummer.Run.Api/ServiceCollectionBoundedContextExtensions.cs",
    "Chummer.Tests/PublicSignalToCanonPacketServiceTests.cs",
    "tests/RunServicesSmoke/Program.cs",
    "scripts/materialize_next90_m125_hub_public_signal_packets_proof.py",
    "scripts/verify_next90_m125_hub_public_signal_packets.py",
    "scripts/ai/verify.sh",
]


def _load_verifier_module():
    module_name = "verify_next90_m125_hub_public_signal_packets_test"
    spec = importlib.util.spec_from_file_location(module_name, SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.pop(module_name, None)


class Next90M125HubPublicSignalPacketsTests(unittest.TestCase):
    def test_verifier_accepts_repo_local_public_signal_packet_lane(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m125-proof-") as temp_dir:
            proof_path = Path(temp_dir) / "NEXT90_M125_HUB_PUBLIC_SIGNAL_PACKETS.generated.json"
            env = os.environ.copy()
            env["CHUMMER_NEXT90_M125_OUT"] = str(proof_path)
            result = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            payload = json.loads(proof_path.read_text(encoding="utf-8")) if proof_path.is_file() else {}

        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        self.assertIn("next90 m125 hub public signal packets proof passed", result.stdout)
        self.assertEqual(payload.get("schema_version"), 2)
        self.assertEqual(payload.get("status"), "passed")
        self.assertEqual(payload.get("proof_kind"), "source_digest_and_executed_test_contract")
        self.assertTrue(payload.get("generated_at"))
        self.assertGreaterEqual(payload.get("test_receipt", {}).get("executed_test_count", 0), 1)
        self.assertEqual(payload.get("test_receipt", {}).get("status"), "passed")
        self.assertGreaterEqual(len(payload.get("source_evidence", [])), 7)
        self.assertEqual(len(payload.get("queue_evidence", [])), 2)
        self.assertFalse(payload.get("release_binding", {}).get("release_artifact_specific", True))

    def test_verify_script_runs_m125_guard(self) -> None:
        verify_script = (REPO_ROOT / "scripts" / "ai" / "verify.sh").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/materialize_next90_m125_hub_public_signal_packets_proof.py", verify_script)
        self.assertIn("python3 scripts/verify_next90_m125_hub_public_signal_packets.py", verify_script)
        self.assertIn("python3 -m unittest tests/test_next90_m125_hub_public_signal_packets.py", verify_script)

    def test_proof_validation_rejects_nonpassing_and_future_receipts(self) -> None:
        module = _load_verifier_module()
        generated = datetime.now(timezone.utc)
        generated_at = generated.replace(microsecond=0).isoformat().replace("+00:00", "Z")
        source_evidence = module._source_evidence()
        queue_evidence = module._queue_evidence()
        payload = {
            "contract_name": "chummer6-hub.next90_m125_hub_public_signal_packets",
            "schema_version": 2,
            "status": "passed",
            "status_scope": module.STATUS_SCOPE,
            "proof_kind": module.PROOF_KIND,
            "generated_at": generated_at,
            "verification_command": module.VERIFICATION_COMMAND,
            "release_binding": {
                "scope": "release_independent_product_capability",
                "release_artifact_specific": False,
            },
            "package_proof": module._expected_package_proof(),
            "package_workflow_status": module.PACKAGE_STATUS,
            "package_workflow_status_affects_capability_status": False,
            "source_evidence": source_evidence,
            "source_evidence_set_sha256": module._evidence_set_sha256(source_evidence),
            "queue_evidence": queue_evidence,
            "queue_evidence_set_sha256": module._evidence_set_sha256(queue_evidence),
            "test_receipt": {
                "status": "passed",
                "executed_at": generated_at,
                "command": module.TEST_COMMAND,
                "fully_qualified_name": module.TEST_FQN,
                "exit_code": 0,
                "executed_test_count": 1,
                "output_sha256": "0" * 64,
            },
        }
        kwargs = {
            "materialization_started_at": generated - timedelta(seconds=1),
            "expected_source_evidence": source_evidence,
            "expected_queue_evidence": queue_evidence,
        }
        self.assertEqual(module._proof_validation_issues(payload, **kwargs), [])

        nonpassing = copy.deepcopy(payload)
        nonpassing["status"] = "failed"
        self.assertIn("proof file status must be passed", module._proof_validation_issues(nonpassing, **kwargs))

        future = copy.deepcopy(payload)
        future_at = (
            datetime.now(timezone.utc)
            + timedelta(seconds=module.MAX_FUTURE_SKEW_SECONDS + 60)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        future["generated_at"] = future_at
        future["test_receipt"]["executed_at"] = future_at
        self.assertIn(
            "proof file generated_at is unacceptably future-dated",
            module._proof_validation_issues(future, **kwargs),
        )

    def test_verifier_fails_when_queue_row_drifts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m125-queue-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            queue_path = temp_root / "fleet-queue.yaml"
            design_queue_path = temp_root / "design-queue.yaml"
            shutil.copyfile("/docker/fleet/.codex-studio/published/NEXT_90_DAY_QUEUE_STAGING.generated.yaml", queue_path)
            shutil.copyfile("/docker/chummercomplete/chummer-design-m114/products/chummer/NEXT_90_DAY_QUEUE_STAGING.generated.yaml", design_queue_path)
            queue_payload = self.load_queue_payload(queue_path)
            for item in queue_payload["items"]:
                if item.get("package_id") == "next90-m125-hub-build-public-feedback-roadmap-changelog-support-and-sign":
                    item["frontier_id"] = 0
                    break
            queue_path.write_text(yaml.safe_dump(queue_payload, sort_keys=False), encoding="utf-8")
            result = self.run_verifier(temp_root, queue_path=queue_path, design_queue_path=design_queue_path)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("frontier_id must be 4030850391", result.stderr)

    def test_verifier_fails_when_smoke_loses_signal_intake_assertion(self) -> None:
        with tempfile.TemporaryDirectory(prefix="next90-m125-smoke-") as temp_dir:
            temp_root = Path(temp_dir)
            self.copy_sources(temp_root)
            smoke_path = temp_root / "tests/RunServicesSmoke/Program.cs"
            smoke_text = smoke_path.read_text(encoding="utf-8")
            smoke_path.write_text(smoke_text.replace("governed signal-intake packets for the shared participate surface", "signal-intake drift"), encoding="utf-8")
            result = self.run_verifier(temp_root)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("governed signal-intake packets for the shared participate surface", result.stderr)

    @staticmethod
    def copy_sources(temp_root: Path) -> None:
        for relative_path in SOURCE_FILES:
            source = REPO_ROOT / relative_path
            target = temp_root / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)

    def run_verifier(self, temp_root: Path, *, queue_path: Path | None = None, design_queue_path: Path | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["CHUMMER_NEXT90_M125_ROOT"] = str(temp_root)
        if queue_path is not None:
            env["CHUMMER_NEXT90_M125_QUEUE_STAGING"] = str(queue_path)
        if design_queue_path is not None:
            env["CHUMMER_NEXT90_M125_DESIGN_QUEUE_STAGING"] = str(design_queue_path)
        return subprocess.run(["python3", str(temp_root / "scripts/verify_next90_m125_hub_public_signal_packets.py")], cwd=temp_root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    @staticmethod
    def load_queue_payload(path: Path) -> dict:
        text = path.read_text(encoding="utf-8")
        try:
            payload = yaml.safe_load(text)
        except yaml.YAMLError:
            payload = None
        if isinstance(payload, dict) and isinstance(payload.get("items"), list):
            return payload

        package_marker = "package_id: next90-m125-hub-build-public-feedback-roadmap-changelog-support-and-sign"
        package_index = text.find(package_marker)
        if package_index < 0:
            raise AssertionError(f"queue staging is missing {package_marker}")

        start = text.rfind("\n- title:", 0, package_index)
        if start < 0:
            if not text.startswith("- title:"):
                raise AssertionError("queue staging is missing the target item block")
            start = 0
        else:
            start += 1

        end = text.find("\n- title:", package_index)
        if end < 0:
            end = len(text)

        block = text[start:end].rstrip() + "\n"
        payload = yaml.safe_load(block)
        if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
            raise AssertionError("queue staging target block did not parse correctly")
        return {"items": payload}


if __name__ == "__main__":
    unittest.main()
