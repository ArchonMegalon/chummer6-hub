from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "import_public_edge_observability_operator_proof.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "public_edge_observability_operator_proof_intake",
        SCRIPT,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicEdgeObservabilityOperatorProofIntakeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.gate = self.module._load_gate_module()
        self.now = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)

    def proof(self) -> dict[str, object]:
        policy_digest = hashlib.sha256(self.gate.DEFAULT_POLICY.read_bytes()).hexdigest()
        release, _, _, failures = self.gate.release_candidate_binding(
            self.gate.DEFAULT_RELEASE_CHANNEL
        )
        self.assertEqual([], failures)
        runtime = self.gate.runtime_source_binding()
        return {
            "contract_name": self.gate.OPERATOR_PROOF_CONTRACT,
            "status": "pass",
            "generated_at_utc": self.gate.iso(self.now),
            "policy_sha256": policy_digest,
            "release_candidate": {
                "sha256": release["sha256"],
                "version": release["version"],
                "channel": release["channel"],
            },
            "runtime_source_fingerprint_sha256": runtime["aggregate_sha256"],
            "monitor_backend": {
                "provider": "operator-monitor",
                "deployment_id": "deployment-42",
                "binding_status": "verified",
            },
            "sli_bindings": {
                "availability": True,
                "latency": True,
                "readiness": True,
            },
            "alert_route": {
                "receiver_class": "primary_on_call",
                "binding_status": "verified",
                "delivery_tested_at_utc": self.gate.iso(self.now),
                "delivery_test_result": "delivered",
            },
        }

    @staticmethod
    def write_proof(path: Path, proof: dict[str, object]) -> bytes:
        raw = (json.dumps(proof, indent=2) + "\n").encode("utf-8")
        path.write_bytes(raw)
        return raw

    def authority_fixture(
        self,
        root: Path,
        source: Path,
        *,
        policy_path: Path | None = None,
        release_channel_path: Path | None = None,
    ) -> tuple[Path, Path]:
        policy = policy_path or self.gate.DEFAULT_POLICY
        release_path = release_channel_path or self.gate.DEFAULT_RELEASE_CHANNEL
        policy_digest = hashlib.sha256(policy.read_bytes()).hexdigest()
        release, _, _, release_failures = self.gate.release_candidate_binding(
            release_path
        )
        self.assertEqual([], release_failures)
        runtime = self.gate.runtime_source_binding()
        expected_bindings = self.gate.operator_attestation_bindings(
            policy_sha256=policy_digest,
            release_candidate=release,
            runtime_binding=runtime,
        )
        request_path = root / "intake-request.json"
        request = {
            "contract_name": self.gate.INTAKE_REQUEST_CONTRACT,
            "status": "ready",
            "verdict": "INTAKE_REQUEST_READY",
            "generated_at_utc": self.gate.iso(self.now),
            "challenge_nonce": "a" * 64,
            "current_bindings": {
                "binding_sha256": self.gate.canonical_sha256(expected_bindings),
                "policy": {"sha256": policy_digest},
                "release_candidate": release,
                "runtime_source_binding": runtime,
            },
            "failure_count": 0,
            "failures": [],
        }
        request_path.write_text(json.dumps(request) + "\n", encoding="utf-8")
        attestation_path = self.gate.detached_operator_attestation_path(source)
        attestation_path.write_text('{"test_fixture":true}\n', encoding="utf-8")
        return request_path, attestation_path

    def process_with_fixture_authority(self, **kwargs):
        with mock.patch.object(
            self.module,
            "_load_gate_module",
            return_value=self.gate,
        ), mock.patch.object(
            self.gate,
            "validate_operator_attestation",
            return_value=({"status": "pass", "key_id": "fixture"}, []),
        ):
            return self.module.process_intake(**kwargs)

    def test_validate_only_never_mutates_canonical_destination(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-intake-check-") as temp_dir:
            source = Path(temp_dir) / "external-proof.json"
            destination = Path(temp_dir) / "canonical-proof.json"
            raw = self.write_proof(source, self.proof())
            request_path, attestation_path = self.authority_fixture(
                Path(temp_dir), source
            )

            receipt = self.process_with_fixture_authority(
                source_path=source,
                destination_path=destination,
                attestation_path=attestation_path,
                intake_request_path=request_path,
                import_proof=False,
                now=self.now,
            )
            destination_exists = destination.exists()

        self.assertEqual("ready", receipt["status"])
        self.assertEqual("OPERATOR_PROOF_VALIDATED_NOT_IMPORTED", receipt["verdict"])
        self.assertFalse(receipt["destination"]["imported"])
        self.assertFalse(destination_exists)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), receipt["source"]["sha256"])
        self.assertEqual(source.name, receipt["source"]["name"])
        self.assertNotIn("path", receipt["source"])
        self.assertTrue(receipt["external_evidence_pending"])

    def test_import_copies_exact_validated_bytes_atomically(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-intake-import-") as temp_dir:
            source = Path(temp_dir) / "external-proof.json"
            destination = Path(temp_dir) / "canonical-proof.json"
            raw = self.write_proof(source, self.proof())
            request_path, attestation_path = self.authority_fixture(
                Path(temp_dir), source
            )

            receipt = self.process_with_fixture_authority(
                source_path=source,
                destination_path=destination,
                attestation_path=attestation_path,
                intake_request_path=request_path,
                import_proof=True,
                now=self.now,
            )

            imported = destination.read_bytes()
            imported_attestation = self.gate.detached_operator_attestation_path(
                destination
            ).read_bytes()
            source_attestation = attestation_path.read_bytes()

        self.assertEqual("pass", receipt["status"])
        self.assertEqual("OPERATOR_PROOF_IMPORTED", receipt["verdict"])
        self.assertTrue(receipt["destination"]["imported"])
        self.assertFalse(receipt["external_evidence_pending"])
        self.assertEqual(raw, imported)
        self.assertEqual(source_attestation, imported_attestation)
        self.assertEqual(
            receipt["source"]["sha256"],
            receipt["destination"]["sha256"],
        )

    def test_invalid_source_preserves_existing_canonical_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-intake-preserve-") as temp_dir:
            source = Path(temp_dir) / "external-proof.json"
            destination = Path(temp_dir) / "canonical-proof.json"
            previous = b'{"existing":"proof"}\n'
            destination.write_bytes(previous)
            proof = self.proof()
            proof["alert_route"]["delivery_test_result"] = "not_delivered"
            self.write_proof(source, proof)

            receipt = self.module.process_intake(
                source_path=source,
                destination_path=destination,
                import_proof=True,
                now=self.now,
            )

            retained = destination.read_bytes()

        self.assertEqual("fail", receipt["status"])
        self.assertFalse(receipt["destination"]["imported"])
        self.assertEqual(previous, retained)
        self.assertTrue(
            any("delivery_test_result must be delivered" in item for item in receipt["failures"])
        )

    def test_symlinked_source_is_rejected_without_reading_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-intake-symlink-") as temp_dir:
            target = Path(temp_dir) / "target.json"
            source = Path(temp_dir) / "external-proof.json"
            destination = Path(temp_dir) / "canonical-proof.json"
            self.write_proof(target, self.proof())
            source.symlink_to(target)

            receipt = self.module.process_intake(
                source_path=source,
                destination_path=destination,
                import_proof=True,
                now=self.now,
            )
            destination_exists = destination.exists()

        self.assertEqual("fail", receipt["status"])
        self.assertEqual("symlink_rejected", receipt["source"]["load_status"])
        self.assertIsNone(receipt["source"]["sha256"])
        self.assertFalse(destination_exists)

    def test_canonical_path_cannot_be_reused_as_intake_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-intake-self-") as temp_dir:
            canonical = Path(temp_dir) / "canonical-proof.json"
            previous = self.write_proof(canonical, self.proof())

            receipt = self.module.process_intake(
                source_path=canonical,
                destination_path=canonical,
                import_proof=True,
                now=self.now,
            )
            retained = canonical.read_bytes()

        self.assertEqual("fail", receipt["status"])
        self.assertEqual(
            "canonical_path_is_not_an_intake_source",
            receipt["source"]["load_status"],
        )
        self.assertEqual(previous, retained)

    def test_custom_policy_and_release_paths_are_honored(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-intake-bindings-") as temp_dir:
            root = Path(temp_dir)
            policy = root / "policy.json"
            policy_raw = self.gate.DEFAULT_POLICY.read_bytes()
            policy.write_bytes(policy_raw)
            release = root / "release.json"
            release.write_text(
                json.dumps(
                    {
                        "status": "published",
                        "version": "custom-candidate",
                        "channel": "preview",
                        "publishedAt": "2026-07-13T11:55:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            release_binding, _, _, release_failures = (
                self.gate.release_candidate_binding(release)
            )
            self.assertEqual([], release_failures)

            proof = self.proof()
            proof["policy_sha256"] = hashlib.sha256(policy_raw).hexdigest()
            proof["release_candidate"] = {
                "sha256": release_binding["sha256"],
                "version": release_binding["version"],
                "channel": release_binding["channel"],
            }
            source = root / "external-proof.json"
            destination = root / "canonical-proof.json"
            self.write_proof(source, proof)
            request_path, attestation_path = self.authority_fixture(
                root,
                source,
                policy_path=policy,
                release_channel_path=release,
            )

            receipt = self.process_with_fixture_authority(
                source_path=source,
                destination_path=destination,
                attestation_path=attestation_path,
                intake_request_path=request_path,
                policy_path=policy,
                release_channel_path=release,
                import_proof=False,
                now=self.now,
            )

        self.assertEqual("ready", receipt["status"])
        self.assertEqual(
            "custom-candidate",
            receipt["current_bindings"]["release_candidate"]["version"],
        )
        self.assertEqual(
            hashlib.sha256(policy_raw).hexdigest(),
            receipt["current_bindings"]["policy_sha256"],
        )


if __name__ == "__main__":
    unittest.main()
