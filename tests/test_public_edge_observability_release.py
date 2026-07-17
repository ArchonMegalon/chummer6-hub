from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_public_edge_observability_release.py"
RELEASE_READY_MATERIALIZER = ROOT / "scripts" / "materialize_release_ready_receipt.py"


def load_module():
    spec = importlib.util.spec_from_file_location("public_edge_observability_release", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_release_ready_materializer():
    name = "release_ready_materializer_for_observability_test"
    spec = importlib.util.spec_from_file_location(name, RELEASE_READY_MATERIALIZER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


class PublicEdgeObservabilityReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module()
        self.now = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)

    def proof(
        self,
        policy_path: Path,
        *,
        release_channel_path: Path | None = None,
        runtime_sources: dict[str, Path] | None = None,
        generated_at: datetime | None = None,
    ) -> dict[str, object]:
        policy_digest = hashlib.sha256(policy_path.read_bytes()).hexdigest()
        timestamp = generated_at or self.now
        release_binding, _, _, failures = self.module.release_candidate_binding(
            release_channel_path or self.module.DEFAULT_RELEASE_CHANNEL
        )
        self.assertEqual([], failures)
        runtime_binding = self.module.runtime_source_binding(runtime_sources)
        return {
            "contract_name": self.module.OPERATOR_PROOF_CONTRACT,
            "status": "pass",
            "generated_at_utc": self.module.iso(timestamp),
            "policy_sha256": policy_digest,
            "release_candidate": {
                "sha256": release_binding["sha256"],
                "version": release_binding["version"],
                "channel": release_binding["channel"],
            },
            "runtime_source_fingerprint_sha256": runtime_binding["aggregate_sha256"],
            "monitor_backend": {
                "provider": "test-monitor",
                "deployment_id": "test-deployment",
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
                "delivery_tested_at_utc": self.module.iso(timestamp),
                "delivery_test_result": "delivered",
            },
        }

    def authority_fixture(
        self,
        root: Path,
        proof_path: Path,
    ) -> tuple[Path, Path]:
        policy_digest = hashlib.sha256(
            self.module.DEFAULT_POLICY.read_bytes()
        ).hexdigest()
        release, _, _, release_failures = self.module.release_candidate_binding(
            self.module.DEFAULT_RELEASE_CHANNEL
        )
        self.assertEqual([], release_failures)
        runtime = self.module.runtime_source_binding()
        expected_bindings = self.module.operator_attestation_bindings(
            policy_sha256=policy_digest,
            release_candidate=release,
            runtime_binding=runtime,
        )
        request_path = root / "intake-request.json"
        write_json(
            request_path,
            {
                "contract_name": self.module.INTAKE_REQUEST_CONTRACT,
                "status": "ready",
                "verdict": "INTAKE_REQUEST_READY",
                "generated_at_utc": self.module.iso(self.now - timedelta(minutes=1)),
                "challenge_nonce": "a" * 64,
                "current_bindings": {
                    "binding_sha256": self.module.canonical_sha256(expected_bindings),
                    "policy": {"sha256": policy_digest},
                    "release_candidate": release,
                    "runtime_source_binding": runtime,
                },
                "failure_count": 0,
                "failures": [],
            },
        )
        attestation_path = self.module.detached_operator_attestation_path(proof_path)
        write_json(attestation_path, {"test_fixture": True})
        return request_path, attestation_path

    def test_repository_runtime_contract_and_policy_are_structurally_valid(self) -> None:
        checks, failures = self.module.validate_runtime_contracts()
        policy, error = self.module.load_json(self.module.DEFAULT_POLICY)

        self.assertEqual([], failures)
        self.assertTrue(all(check["status"] == "pass" for check in checks))
        self.assertIsNone(error)
        self.assertEqual([], self.module.validate_policy(policy))

    def test_runtime_validation_and_binding_share_one_stable_byte_snapshot(self) -> None:
        original_read = self.module.read_regular_file_bytes
        runtime_bytes = {
            path: path.read_bytes()
            for path in self.module.DEFAULT_RUNTIME_SOURCES.values()
        }
        read_counts = {path: 0 for path in runtime_bytes}

        def changing_read(path: Path, **kwargs):
            if path not in runtime_bytes:
                return original_read(path, **kwargs)
            read_counts[path] += 1
            raw = runtime_bytes[path]
            if read_counts[path] > 1:
                raw += b"\n// changed after validation\n"
            return raw, None

        with tempfile.TemporaryDirectory(prefix="observability-runtime-snapshot-") as temp_dir:
            with mock.patch.object(
                self.module,
                "read_regular_file_bytes",
                side_effect=changing_read,
            ):
                receipt = self.module.build_receipt(
                    policy_path=self.module.DEFAULT_POLICY,
                    operator_proof_path=Path(temp_dir) / "missing-proof.json",
                    now=self.now,
                )

        self.assertTrue(all(count == 1 for count in read_counts.values()))
        rows = {
            Path(row["path"]): row
            for row in receipt["runtime_source_binding"]["sources"]
        }
        for path, raw in runtime_bytes.items():
            self.assertEqual(hashlib.sha256(raw).hexdigest(), rows[path]["sha256"])
        self.assertTrue(
            all(
                check["status"] == "pass"
                for check in receipt["checks"]
                if check["id"].startswith("runtime:")
            )
        )

    def test_runtime_gate_rejects_raw_path_metric_labels(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-runtime-path-") as temp_dir:
            mutated_middleware = Path(temp_dir) / "HubRequestObservabilityMiddleware.cs"
            source = self.module.DEFAULT_RUNTIME_SOURCES["middleware"].read_text(encoding="utf-8")
            source = source.replace(
                'new("http.route", route)',
                'new("http.route", context.Request.Path.Value ?? "/")',
                1,
            )
            mutated_middleware.write_text(source, encoding="utf-8")
            runtime_sources = dict(self.module.DEFAULT_RUNTIME_SOURCES)
            runtime_sources["middleware"] = mutated_middleware

            checks, failures = self.module.validate_runtime_contracts(runtime_sources)

        middleware_check = next(check for check in checks if check["id"] == "runtime:middleware")
        self.assertEqual("fail", middleware_check["status"])
        self.assertTrue(any("runtime:middleware" in failure for failure in failures))

    def test_runtime_gate_rejects_correlation_id_metric_dimensions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-runtime-correlation-") as temp_dir:
            mutated_middleware = Path(temp_dir) / "HubRequestObservabilityMiddleware.cs"
            source = self.module.DEFAULT_RUNTIME_SOURCES["middleware"].read_text(encoding="utf-8")
            source = source.replace(
                'new("http.route", route)',
                'new("http.route", route),\n            new("chummer.correlation_id", correlationId)',
                1,
            )
            mutated_middleware.write_text(source, encoding="utf-8")
            runtime_sources = dict(self.module.DEFAULT_RUNTIME_SOURCES)
            runtime_sources["middleware"] = mutated_middleware

            checks, failures = self.module.validate_runtime_contracts(runtime_sources)

        middleware_check = next(check for check in checks if check["id"] == "runtime:middleware")
        self.assertEqual("fail", middleware_check["status"])
        self.assertTrue(any("runtime:middleware" in failure for failure in failures))

    def test_policy_rejects_high_cardinality_or_private_metric_dimensions(self) -> None:
        policy, error = self.module.load_json(self.module.DEFAULT_POLICY)
        self.assertIsNone(error)
        assert policy is not None
        policy["metric_dimensions"]["include_raw_path"] = True
        policy["metric_dimensions"]["allowed_labels"].append("chummer.correlation_id")

        failures = self.module.validate_policy(policy)

        self.assertTrue(any("allowed_labels" in failure for failure in failures))
        self.assertIn("metric_dimensions.include_raw_path must be false", failures)

    def test_policy_requires_exact_evidence_binding_algorithms(self) -> None:
        policy, error = self.module.load_json(self.module.DEFAULT_POLICY)
        self.assertIsNone(error)
        assert policy is not None
        policy["evidence_binding"]["release_candidate_digest_source"] = "version_only"

        failures = self.module.validate_policy(policy)

        self.assertTrue(any("release_candidate_digest_source" in failure for failure in failures))

    def test_gate_passes_only_with_current_policy_bound_monitor_and_alert_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-release-pass-") as temp_dir:
            root = Path(temp_dir)
            proof_path = root / "proof.json"
            write_json(proof_path, self.proof(self.module.DEFAULT_POLICY))
            request_path, attestation_path = self.authority_fixture(root, proof_path)

            expected_proof_digest = hashlib.sha256(proof_path.read_bytes()).hexdigest()
            expected_release_digest = hashlib.sha256(
                self.module.DEFAULT_RELEASE_CHANNEL.read_bytes()
            ).hexdigest()
            with mock.patch.object(
                self.module,
                "validate_operator_attestation",
                return_value=({"status": "pass", "key_id": "fixture"}, []),
            ):
                receipt = self.module.build_receipt(
                    policy_path=self.module.DEFAULT_POLICY,
                    operator_proof_path=proof_path,
                    intake_request_path=request_path,
                    operator_attestation_path=attestation_path,
                    now=self.now,
                )

        self.assertEqual("pass", receipt["status"])
        self.assertEqual("OBSERVABILITY_RELEASE_READY", receipt["verdict"])
        self.assertEqual([], receipt["failures"])
        self.assertEqual(str(proof_path), receipt["operator_proof"]["path"])
        self.assertEqual(expected_proof_digest, receipt["operator_proof"]["sha256"])
        self.assertEqual("pass", receipt["operator_proof"]["status"])
        self.assertEqual(self.module.iso(self.now), receipt["operator_proof"]["generated_at_utc"])
        self.assertEqual(expected_release_digest, receipt["release_candidate"]["sha256"])
        expected_release, _, _, expected_release_failures = self.module.release_candidate_binding(
            self.module.DEFAULT_RELEASE_CHANNEL
        )
        self.assertEqual([], expected_release_failures)
        self.assertEqual(expected_release["version"], receipt["release_candidate"]["version"])
        self.assertEqual(expected_release["channel"], receipt["release_candidate"]["channel"])
        self.assertRegex(
            receipt["runtime_source_binding"]["aggregate_sha256"],
            r"^[0-9a-f]{64}$",
        )
        self.assertTrue(
            all(row["sha256"] for row in receipt["runtime_source_binding"]["sources"])
        )

    def test_gate_fails_closed_when_operator_proof_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-release-missing-") as temp_dir:
            receipt = self.module.build_receipt(
                policy_path=self.module.DEFAULT_POLICY,
                operator_proof_path=Path(temp_dir) / "missing.json",
                now=self.now,
            )

        self.assertEqual("fail", receipt["status"])
        self.assertIn("operator_proof: operator proof is missing", receipt["failures"])
        self.assertTrue(receipt["operator_dependencies"])
        self.assertEqual(
            "waiting_for_external_proof",
            receipt["operator_intake"]["state"],
        )
        self.assertTrue(receipt["operator_intake"]["external_evidence_required"])
        self.assertFalse(receipt["operator_intake"]["sends_alerts"])

    def test_gate_rejects_symlinked_operator_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-release-symlink-") as temp_dir:
            proof_target = Path(temp_dir) / "proof-target.json"
            proof_path = Path(temp_dir) / "proof.json"
            write_json(proof_target, self.proof(self.module.DEFAULT_POLICY))
            proof_path.symlink_to(proof_target)

            receipt = self.module.build_receipt(
                policy_path=self.module.DEFAULT_POLICY,
                operator_proof_path=proof_path,
                now=self.now,
            )

        self.assertEqual("fail", receipt["status"])
        self.assertEqual("symlink_rejected", receipt["operator_proof"]["load_status"])
        self.assertIsNone(receipt["operator_proof"]["sha256"])

    def test_gate_rejects_unknown_secret_bearing_proof_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-release-secret-field-") as temp_dir:
            proof_path = Path(temp_dir) / "proof.json"
            proof = self.proof(self.module.DEFAULT_POLICY)
            proof["monitor_backend"]["api_token"] = "must-not-be-stored"
            proof["alert_route"]["receiver_address"] = "private@example.test"
            write_json(proof_path, proof)

            receipt = self.module.build_receipt(
                policy_path=self.module.DEFAULT_POLICY,
                operator_proof_path=proof_path,
                now=self.now,
            )

        self.assertEqual("fail", receipt["status"])
        self.assertTrue(
            any("monitor_backend contains 1 unsupported field" in item for item in receipt["failures"])
        )
        self.assertTrue(
            any("alert_route contains 1 unsupported field" in item for item in receipt["failures"])
        )
        self.assertNotIn("api_token", json.dumps(receipt))
        self.assertNotIn("receiver_address", json.dumps(receipt))
        self.assertNotIn("must-not-be-stored", json.dumps(receipt))
        self.assertNotIn("private@example.test", json.dumps(receipt))

    def test_gate_rejects_documentation_placeholders_as_backend_identity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-release-placeholder-") as temp_dir:
            proof_path = Path(temp_dir) / "proof.json"
            proof = self.proof(self.module.DEFAULT_POLICY)
            proof["monitor_backend"]["provider"] = "<provider identifier>"
            proof["monitor_backend"]["deployment_id"] = "TBD"
            write_json(proof_path, proof)

            receipt = self.module.build_receipt(
                policy_path=self.module.DEFAULT_POLICY,
                operator_proof_path=proof_path,
                now=self.now,
            )

        self.assertEqual("fail", receipt["status"])
        self.assertTrue(
            any("monitor_backend.provider must be a non-placeholder" in item for item in receipt["failures"])
        )
        self.assertTrue(
            any("monitor_backend.deployment_id must be a non-placeholder" in item for item in receipt["failures"])
        )

    def test_gate_preserves_digest_of_invalid_operator_proof_bytes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-release-invalid-") as temp_dir:
            proof_path = Path(temp_dir) / "proof.json"
            proof_path.write_bytes(b'{"incomplete":')
            expected_digest = hashlib.sha256(proof_path.read_bytes()).hexdigest()

            receipt = self.module.build_receipt(
                policy_path=self.module.DEFAULT_POLICY,
                operator_proof_path=proof_path,
                now=self.now,
            )

        self.assertEqual("fail", receipt["status"])
        self.assertEqual("invalid_json", receipt["operator_proof"]["load_status"])
        self.assertEqual(expected_digest, receipt["operator_proof"]["sha256"])
        self.assertIsNone(receipt["operator_proof"]["status"])

    def test_gate_rejects_stale_operator_and_alert_delivery_proof(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-release-stale-") as temp_dir:
            proof_path = Path(temp_dir) / "proof.json"
            write_json(
                proof_path,
                self.proof(
                    self.module.DEFAULT_POLICY,
                    generated_at=self.now - timedelta(days=8),
                ),
            )

            receipt = self.module.build_receipt(
                policy_path=self.module.DEFAULT_POLICY,
                operator_proof_path=proof_path,
                now=self.now,
            )

        self.assertEqual("fail", receipt["status"])
        self.assertTrue(any("operator proof is stale" in failure for failure in receipt["failures"]))
        self.assertTrue(any("alert delivery test is stale" in failure for failure in receipt["failures"]))

    def test_gate_rejects_proof_for_a_different_policy(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-release-digest-") as temp_dir:
            proof_path = Path(temp_dir) / "proof.json"
            proof = self.proof(self.module.DEFAULT_POLICY)
            proof["policy_sha256"] = "0" * 64
            write_json(proof_path, proof)

            receipt = self.module.build_receipt(
                policy_path=self.module.DEFAULT_POLICY,
                operator_proof_path=proof_path,
                now=self.now,
            )

        self.assertEqual("fail", receipt["status"])
        self.assertTrue(any("policy_sha256" in failure for failure in receipt["failures"]))

    def test_gate_rejects_proof_for_a_different_release_candidate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-release-candidate-") as temp_dir:
            proof_path = Path(temp_dir) / "proof.json"
            proof = self.proof(self.module.DEFAULT_POLICY)
            proof["release_candidate"]["version"] = "different-version"
            write_json(proof_path, proof)

            receipt = self.module.build_receipt(
                policy_path=self.module.DEFAULT_POLICY,
                operator_proof_path=proof_path,
                now=self.now,
            )

        self.assertEqual("fail", receipt["status"])
        self.assertTrue(
            any("release_candidate.version" in failure for failure in receipt["failures"])
        )

    def test_gate_rejects_proof_for_changed_runtime_sources(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-runtime-binding-") as temp_dir:
            proof_path = Path(temp_dir) / "proof.json"
            proof = self.proof(self.module.DEFAULT_POLICY)
            write_json(proof_path, proof)

            changed_program = Path(temp_dir) / "Program.cs"
            changed_program.write_text(
                self.module.DEFAULT_RUNTIME_SOURCES["program"].read_text(encoding="utf-8")
                + "\n// source fingerprint change\n",
                encoding="utf-8",
            )
            runtime_sources = dict(self.module.DEFAULT_RUNTIME_SOURCES)
            runtime_sources["program"] = changed_program

            receipt = self.module.build_receipt(
                policy_path=self.module.DEFAULT_POLICY,
                operator_proof_path=proof_path,
                runtime_sources=runtime_sources,
                now=self.now,
            )

        self.assertEqual("fail", receipt["status"])
        self.assertTrue(
            any(
                "runtime_source_fingerprint_sha256" in failure
                for failure in receipt["failures"]
            )
        )

    def test_gate_fails_closed_when_release_candidate_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-release-missing-candidate-") as temp_dir:
            proof_path = Path(temp_dir) / "proof.json"
            write_json(proof_path, self.proof(self.module.DEFAULT_POLICY))

            receipt = self.module.build_receipt(
                policy_path=self.module.DEFAULT_POLICY,
                operator_proof_path=proof_path,
                release_channel_path=Path(temp_dir) / "missing-release.json",
                now=self.now,
            )

        self.assertEqual("fail", receipt["status"])
        self.assertTrue(
            any("release_candidate: release channel is missing" in failure for failure in receipt["failures"])
        )

    def test_gate_writes_a_failure_receipt_before_returning_nonzero(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-release-output-") as temp_dir:
            output = Path(temp_dir) / "receipt.json"
            receipt = self.module.build_receipt(
                policy_path=self.module.DEFAULT_POLICY,
                operator_proof_path=Path(temp_dir) / "missing.json",
                now=self.now,
            )
            self.module.atomic_write_json(output, receipt)

            persisted = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual("fail", persisted["status"])
        self.assertEqual(self.module.GATE_CONTRACT, persisted["contract_name"])

    def test_root_release_ready_wrapper_runs_observability_after_compose_operability(self) -> None:
        controller = load_release_ready_materializer()
        environment = controller.authoritative_controller_environment(
            {"PATH": controller.TRUSTED_PATH}
        )
        specs = controller.canonical_release_gate_specs(environment)
        names = [str(spec["name"]) for spec in specs]
        commands = {str(spec["name"]): str(spec["command"]) for spec in specs}

        compose_gate = "verify_public_edge_compose_operability"
        observability_gate = "verify_public_edge_observability_release"
        alignment_gate = "verify_hub_release_truth_alignment"
        self.assertIn(compose_gate, names)
        self.assertIn(observability_gate, names)
        self.assertIn(alignment_gate, names)
        self.assertLess(names.index(compose_gate), names.index(observability_gate))
        self.assertLess(names.index(observability_gate), names.index(alignment_gate))
        self.assertIn("/usr/bin/python3", commands[compose_gate])
        self.assertIn("scripts/verify_public_edge_compose_operability.py", commands[compose_gate])
        self.assertIn("/usr/bin/python3", commands[observability_gate])
        self.assertIn("scripts/verify_public_edge_observability_release.py", commands[observability_gate])
        self.assertIn("/usr/bin/python3", commands[alignment_gate])
        self.assertIn("scripts/verify_next90_m144_hub_release_truth_alignment.py", commands[alignment_gate])


if __name__ == "__main__":
    unittest.main()
