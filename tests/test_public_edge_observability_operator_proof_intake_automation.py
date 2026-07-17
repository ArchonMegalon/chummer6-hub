from __future__ import annotations

import hashlib
import importlib.util
import json
import shlex
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
REQUEST_SCRIPT = (
    ROOT
    / "scripts"
    / "materialize_public_edge_observability_operator_proof_intake_request.py"
)
WATCH_SCRIPT = (
    ROOT / "scripts" / "watch_public_edge_observability_operator_proof.py"
)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicEdgeObservabilityOperatorProofIntakeRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module(REQUEST_SCRIPT, "observability_intake_request_test")
        self.gate = self.module._load_gate_module()
        self.now = datetime(2026, 7, 13, 14, 0, tzinfo=UTC)

    @staticmethod
    def write_release(path: Path, version: str = "run-current") -> bytes:
        raw = (
            json.dumps(
                {
                    "status": "published",
                    "version": version,
                    "channel": "preview",
                    "publishedAt": "2026-07-13T13:55:00Z",
                },
                indent=2,
            )
            + "\n"
        ).encode("utf-8")
        path.write_bytes(raw)
        return raw

    def test_request_binds_exact_current_policy_release_and_runtime(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-request-") as temp_dir:
            root = Path(temp_dir)
            release = root / "RELEASE_CHANNEL.generated.json"
            release_raw = self.write_release(release)
            source = root / "incoming" / "PUBLIC_EDGE_OBSERVABILITY_OPERATOR_PROOF.generated.json"
            canonical = root / "published" / "PUBLIC_EDGE_OBSERVABILITY_OPERATOR_PROOF.generated.json"
            output = root / "published" / "INTAKE_REQUEST.generated.json"

            payload = self.module.build_request(
                policy_path=self.gate.DEFAULT_POLICY,
                release_channel_path=release,
                source_path=source,
                canonical_proof_path=canonical,
                request_output=output,
                now=self.now,
            )
            self.gate.atomic_write_json(output, payload)
            repeated = self.module.build_request(
                policy_path=self.gate.DEFAULT_POLICY,
                release_channel_path=release,
                source_path=source,
                canonical_proof_path=canonical,
                request_output=output,
                now=self.now + timedelta(minutes=1),
            )

        bindings = payload["current_bindings"]
        expected_policy_sha = hashlib.sha256(
            self.gate.DEFAULT_POLICY.read_bytes()
        ).hexdigest()
        self.assertEqual("ready", payload["status"])
        self.assertEqual("INTAKE_REQUEST_READY", payload["verdict"])
        self.assertEqual(expected_policy_sha, bindings["policy"]["sha256"])
        self.assertEqual(
            hashlib.sha256(release_raw).hexdigest(),
            bindings["release_candidate"]["sha256"],
        )
        self.assertEqual("run-current", bindings["release_candidate"]["version"])
        self.assertRegex(bindings["runtime_source_binding"]["aggregate_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(bindings["binding_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(payload["challenge_nonce"], r"^[0-9a-f]{64}$")
        self.assertEqual(payload, repeated)
        self.assertEqual(
            str(source) + ".attestation.json",
            payload["intake"]["source_attestation_path"],
        )
        self.assertEqual(
            payload["challenge_nonce"],
            payload["required_attestation"]["challenge_nonce"],
        )
        self.assertTrue(all(row["status"] == "pass" for row in payload["runtime_checks"]))
        self.assertTrue(payload["external_evidence_required"])
        self.assertFalse(payload["proof_generated_by_repository"])
        self.assertFalse(payload["sends_alerts"])
        self.assertFalse(payload["configures_monitoring"])

    def test_request_commands_keep_validation_default_and_import_explicit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-request-commands-") as temp_dir:
            root = Path(temp_dir)
            policy = root / "policy custom.json"
            policy.write_bytes(self.gate.DEFAULT_POLICY.read_bytes())
            release = root / "RELEASE_CHANNEL.generated.json"
            self.write_release(release)
            payload = self.module.build_request(
                policy_path=policy,
                release_channel_path=release,
                source_path=root / "incoming proof.json",
                canonical_proof_path=root / "canonical proof.json",
                request_output=root / "request receipt.json",
                now=self.now,
            )

        commands = payload["commands"]
        self.assertNotIn("--import-proof", commands["validate_only"])
        self.assertTrue(commands["import_after_review"].endswith(" --import-proof"))
        self.assertNotIn("--import-proof", commands["watch_validate_only"])
        self.assertTrue(commands["watch_and_import_explicit"].endswith(" --import-proof"))
        self.assertIn("import_public_edge_observability_operator_proof.py", commands["validate_only"])
        self.assertIn("verify_public_edge_observability_release.py", commands["verify_after_import"])
        self.assertNotIn("telegram", json.dumps(payload).lower())

        for command_name in (
            "validate_only",
            "import_after_review",
            "watch_validate_only",
            "watch_and_import_explicit",
        ):
            command = shlex.split(commands[command_name])
            self.assertEqual(str(policy), command[command.index("--policy") + 1])
            self.assertEqual(
                str(release), command[command.index("--release-channel") + 1]
            )
            self.assertEqual(
                str(root / "canonical proof.json"),
                command[command.index("--canonical-proof") + 1],
            )

    def test_request_fails_closed_when_release_binding_is_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-request-missing-") as temp_dir:
            root = Path(temp_dir)
            payload = self.module.build_request(
                policy_path=self.gate.DEFAULT_POLICY,
                release_channel_path=root / "missing-release.json",
                source_path=root / "incoming.json",
                canonical_proof_path=root / "canonical.json",
                request_output=root / "request.json",
                now=self.now,
            )

        self.assertEqual("fail", payload["status"])
        self.assertEqual("INTAKE_REQUEST_BLOCKED", payload["verdict"])
        self.assertTrue(
            any("release_candidate: release channel is missing" in failure for failure in payload["failures"])
        )


class PublicEdgeObservabilityOperatorProofWatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_module(WATCH_SCRIPT, "observability_proof_watch_test")
        self.now = datetime(2026, 7, 13, 14, 0, tzinfo=UTC)

    def request(self, binding: str, status: str = "ready") -> dict[str, object]:
        return {
            "status": status,
            "current_bindings": {"binding_sha256": binding},
        }

    def test_validate_only_watch_refreshes_binding_between_polls_and_never_imports(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-watch-validate-") as temp_dir:
            root = Path(temp_dir)
            source = root / "incoming" / "proof.json"
            request_path = root / "request.json"
            state = root / "state.json"
            refresh_calls: list[str] = []
            process_modes: list[bool] = []

            def refresh(_request_path: Path, _source_path: Path) -> dict[str, object]:
                refresh_calls.append(f"binding-{len(refresh_calls) + 1}")
                return self.request(refresh_calls[-1])

            def process(_source_path: Path, import_proof: bool) -> dict[str, object]:
                process_modes.append(import_proof)
                attestation_path = self.module._load_gate_module().detached_operator_attestation_path(
                    _source_path
                )
                return {
                    "status": "ready",
                    "verdict": "OPERATOR_PROOF_VALIDATED_NOT_IMPORTED",
                    "source": {
                        "sha256": hashlib.sha256(_source_path.read_bytes()).hexdigest(),
                        "attestation": {
                            "sha256": hashlib.sha256(
                                attestation_path.read_bytes()
                            ).hexdigest(),
                        },
                    },
                    "destination": {"imported": False},
                }

            def sleep_and_drop(_seconds: float) -> None:
                source.parent.mkdir(parents=True, exist_ok=True)
                source.write_text('{"external":"proof"}\n', encoding="utf-8")
                self.module._load_gate_module().detached_operator_attestation_path(
                    source
                ).write_text('{"external":"attestation"}\n', encoding="utf-8")

            ticks = iter((0.0, 0.0))
            payload = self.module.watch_for_proof(
                source_path=source,
                request_path=request_path,
                state_path=state,
                wait_seconds=5,
                poll_seconds=1,
                import_proof=False,
                refresh_request=refresh,
                process_source=process,
                post_import_verify=mock.Mock(side_effect=AssertionError("must not verify")),
                monotonic=lambda: next(ticks),
                sleep=sleep_and_drop,
                utc_now=lambda: self.now,
            )
            persisted = json.loads(state.read_text(encoding="utf-8"))

        self.assertEqual(["binding-1", "binding-2"], refresh_calls)
        self.assertEqual([False], process_modes)
        self.assertEqual("proof_validated", payload["status"])
        self.assertEqual("validate_only", payload["mode"])
        self.assertFalse(payload["import_requested_explicitly"])
        self.assertEqual("binding-2", payload["request_binding_sha256"])
        self.assertEqual(payload, persisted)

    def test_validate_only_watch_rejects_source_changed_after_validation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-watch-source-change-") as temp_dir:
            root = Path(temp_dir)
            source = root / "proof.json"
            source.write_text('{"external":"proof-v1"}\n', encoding="utf-8")
            attestation_path = self.module._load_gate_module().detached_operator_attestation_path(
                source
            )
            attestation_path.write_text(
                '{"external":"attestation-v1"}\n', encoding="utf-8"
            )
            original_digest = hashlib.sha256(source.read_bytes()).hexdigest()
            original_attestation_digest = hashlib.sha256(
                attestation_path.read_bytes()
            ).hexdigest()

            def process(_source_path: Path, _import_proof: bool) -> dict[str, object]:
                _source_path.write_text('{"external":"proof-v2"}\n', encoding="utf-8")
                return {
                    "status": "ready",
                    "verdict": "OPERATOR_PROOF_VALIDATED_NOT_IMPORTED",
                    "source": {
                        "sha256": original_digest,
                        "attestation": {"sha256": original_attestation_digest},
                    },
                    "destination": {"imported": False},
                }

            payload = self.module.watch_for_proof(
                source_path=source,
                request_path=root / "request.json",
                state_path=root / "state.json",
                wait_seconds=0,
                poll_seconds=1,
                import_proof=False,
                refresh_request=lambda *_: self.request("binding-current"),
                process_source=process,
                post_import_verify=mock.Mock(side_effect=AssertionError("must not verify")),
                monotonic=lambda: 0.0,
                sleep=mock.Mock(),
                utc_now=lambda: self.now,
            )

        self.assertEqual("proof_source_changed_after_validation", payload["status"])
        self.assertEqual("OPERATOR_PROOF_SOURCE_CHANGED", payload["verdict"])
        self.assertEqual(1, payload["exit_code"])
        self.assertEqual(original_digest, payload["source"]["processed_sha256"])
        self.assertFalse(payload["source"]["matches_processed_bytes"])

    def test_validate_only_watch_requires_processed_source_digest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-watch-source-binding-") as temp_dir:
            root = Path(temp_dir)
            source = root / "proof.json"
            source.write_text('{"external":"proof"}\n', encoding="utf-8")
            payload = self.module.watch_for_proof(
                source_path=source,
                request_path=root / "request.json",
                state_path=root / "state.json",
                wait_seconds=0,
                poll_seconds=1,
                import_proof=False,
                refresh_request=lambda *_: self.request("binding-current"),
                process_source=lambda *_: {
                    "status": "ready",
                    "verdict": "OPERATOR_PROOF_VALIDATED_NOT_IMPORTED",
                    "destination": {"imported": False},
                },
                post_import_verify=mock.Mock(side_effect=AssertionError("must not verify")),
                monotonic=lambda: 0.0,
                sleep=mock.Mock(),
                utc_now=lambda: self.now,
            )

        self.assertEqual("proof_source_binding_missing", payload["status"])
        self.assertEqual("OPERATOR_PROOF_SOURCE_BINDING_MISSING", payload["verdict"])

    def test_validate_only_watch_rejects_attestation_changed_after_validation(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="observability-watch-attestation-change-"
        ) as temp_dir:
            root = Path(temp_dir)
            source = root / "proof.json"
            source.write_text('{"external":"proof"}\n', encoding="utf-8")
            gate = self.module._load_gate_module()
            attestation = gate.detached_operator_attestation_path(source)
            attestation.write_text('{"external":"attestation-v1"}\n', encoding="utf-8")
            proof_digest = hashlib.sha256(source.read_bytes()).hexdigest()
            attestation_digest = hashlib.sha256(attestation.read_bytes()).hexdigest()

            def process(_source_path: Path, _import_proof: bool) -> dict[str, object]:
                attestation.write_text(
                    '{"external":"attestation-v2"}\n', encoding="utf-8"
                )
                return {
                    "status": "ready",
                    "verdict": "OPERATOR_PROOF_VALIDATED_NOT_IMPORTED",
                    "source": {
                        "sha256": proof_digest,
                        "attestation": {"sha256": attestation_digest},
                    },
                    "destination": {"imported": False},
                }

            payload = self.module.watch_for_proof(
                source_path=source,
                request_path=root / "request.json",
                state_path=root / "state.json",
                wait_seconds=0,
                poll_seconds=1,
                import_proof=False,
                refresh_request=lambda *_: self.request("binding-current"),
                process_source=process,
                post_import_verify=mock.Mock(
                    side_effect=AssertionError("must not verify")
                ),
                monotonic=lambda: 0.0,
                sleep=mock.Mock(),
                utc_now=lambda: self.now,
            )

        self.assertEqual("proof_source_changed_after_validation", payload["status"])
        self.assertFalse(payload["source"]["attestation"]["matches_processed_bytes"])
        self.assertEqual(1, payload["exit_code"])

    def test_import_occurs_only_with_explicit_flag_and_regenerates_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-watch-import-") as temp_dir:
            root = Path(temp_dir)
            source = root / "proof.json"
            source.write_text('{"external":"proof"}\n', encoding="utf-8")
            state = root / "state.json"
            modes: list[bool] = []
            verify = mock.Mock(
                return_value={
                    "status": "pass",
                    "verdict": "OBSERVABILITY_RELEASE_READY",
                    "failures": [],
                }
            )

            def process(_source_path: Path, import_proof: bool) -> dict[str, object]:
                modes.append(import_proof)
                return {
                    "status": "pass",
                    "verdict": "OPERATOR_PROOF_IMPORTED",
                    "destination": {"imported": True},
                }

            payload = self.module.watch_for_proof(
                source_path=source,
                request_path=root / "request.json",
                state_path=state,
                wait_seconds=0,
                poll_seconds=1,
                import_proof=True,
                refresh_request=lambda *_: self.request("binding-current"),
                process_source=process,
                post_import_verify=verify,
                monotonic=lambda: 0.0,
                sleep=mock.Mock(),
                utc_now=lambda: self.now,
            )

        self.assertEqual([True], modes)
        verify.assert_called_once_with()
        self.assertEqual("proof_imported_and_verified", payload["status"])
        self.assertEqual("import", payload["mode"])
        self.assertTrue(payload["import_requested_explicitly"])
        self.assertEqual(0, payload["exit_code"])

    def test_missing_proof_times_out_after_one_current_binding_refresh(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-watch-timeout-") as temp_dir:
            root = Path(temp_dir)
            refresh = mock.Mock(return_value=self.request("binding-current"))
            payload = self.module.watch_for_proof(
                source_path=root / "missing.json",
                request_path=root / "request.json",
                state_path=root / "state.json",
                wait_seconds=0,
                poll_seconds=1,
                import_proof=False,
                refresh_request=refresh,
                process_source=mock.Mock(side_effect=AssertionError("must not process")),
                monotonic=lambda: 0.0,
                sleep=mock.Mock(),
                utc_now=lambda: self.now,
            )

        refresh.assert_called_once()
        self.assertEqual("waiting_for_external_proof", payload["status"])
        self.assertEqual("WATCH_TIMEOUT", payload["verdict"])
        self.assertEqual(2, payload["exit_code"])

    def test_invalid_external_proof_is_rejected_without_post_import_verification(self) -> None:
        with tempfile.TemporaryDirectory(prefix="observability-watch-reject-") as temp_dir:
            root = Path(temp_dir)
            source = root / "proof.json"
            source.write_text("{}\n", encoding="utf-8")
            verify = mock.Mock(side_effect=AssertionError("must not verify"))
            payload = self.module.watch_for_proof(
                source_path=source,
                request_path=root / "request.json",
                state_path=root / "state.json",
                wait_seconds=0,
                poll_seconds=1,
                import_proof=True,
                refresh_request=lambda *_: self.request("binding-current"),
                process_source=lambda *_: {
                    "status": "fail",
                    "verdict": "OPERATOR_PROOF_REJECTED",
                    "failures": ["operator_proof: status must be pass"],
                },
                post_import_verify=verify,
                monotonic=lambda: 0.0,
                sleep=mock.Mock(),
                utc_now=lambda: self.now,
            )

        verify.assert_not_called()
        self.assertEqual("proof_rejected", payload["status"])
        self.assertEqual(1, payload["exit_code"])

    def test_wait_and_poll_bounds_fail_closed(self) -> None:
        kwargs = {
            "source_path": Path("missing.json"),
            "request_path": Path("request.json"),
            "state_path": Path("state.json"),
            "import_proof": False,
        }
        with self.assertRaises(ValueError):
            self.module.watch_for_proof(
                **kwargs,
                wait_seconds=self.module.MAX_WAIT_SECONDS + 1,
                poll_seconds=1,
            )
        with self.assertRaises(ValueError):
            self.module.watch_for_proof(
                **kwargs,
                wait_seconds=0,
                poll_seconds=0,
            )

    def test_cli_defaults_to_validate_only(self) -> None:
        with mock.patch("sys.argv", [str(WATCH_SCRIPT)]):
            args = self.module.parse_args()
        self.assertFalse(args.import_proof)
        with mock.patch("sys.argv", [str(WATCH_SCRIPT), "--import-proof"]):
            args = self.module.parse_args()
        self.assertTrue(args.import_proof)

    def test_cli_custom_binding_paths_reach_all_watch_stages(self) -> None:
        policy = Path("custom-policy.json")
        release = Path("custom-release.json")
        canonical = Path("custom-canonical.json")
        captured: dict[str, object] = {}

        def watch(**kwargs: object) -> dict[str, object]:
            captured.update(kwargs)
            return {"status": "waiting_for_external_proof", "exit_code": 2}

        argv = [
            str(WATCH_SCRIPT),
            "--policy",
            str(policy),
            "--release-channel",
            str(release),
            "--canonical-proof",
            str(canonical),
            "--wait-seconds",
            "0",
        ]
        with mock.patch("sys.argv", argv), mock.patch.object(
            self.module, "watch_for_proof", side_effect=watch
        ):
            exit_code = self.module.main()

        self.assertEqual(2, exit_code)
        for callback_name in ("refresh_request", "process_source", "post_import_verify"):
            callback = captured[callback_name]
            self.assertEqual(policy, callback.keywords["policy_path"])
            self.assertEqual(release, callback.keywords["release_channel_path"])
            self.assertEqual(canonical, callback.keywords["canonical_proof_path"])


if __name__ == "__main__":
    unittest.main()
