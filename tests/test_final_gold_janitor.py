import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "final_gold_janitor.py"


def load_module():
    spec = importlib.util.spec_from_file_location("final_gold_janitor", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.WORKSPACE_PLAY_SURFACE_HORIZON_CANDIDATES = ()
    return module


def valid_blazor_bridge_payload(module):
    return {
        "status": "pass",
        "generated_at_utc": module.now_iso(),
        "proofs": {
            "hub_mobile_pwa_public_projection": {
                "base_url": module.DEFAULT_BASE_URL,
                "pass": True,
                "public_entry": {
                    "home_open_chummer_dropdown_holds": True,
                    "build_route_holds": True,
                    "build_final_route": "/app?command=character_roster",
                    "play_shell_holds": True,
                    "play_final_route": "/play",
                    "checks_pass": True,
                    "checks": {
                        "home_open_chummer_dropdown_routes_build_and_play": {"present": True, "pass": True},
                        "build_route_opens_character_roster": {"present": True, "pass": True},
                        "play_route_opens_pwa_play_shell": {"present": True, "pass": True},
                    },
                },
            },
        },
    }


def write_required_receipt(module, published: Path, key: str, path: Path, payload: dict) -> None:
    if (
        key == "blazor_execution_horizon_bridge"
        and payload.get("status") == "pass"
        and not isinstance(payload.get("proofs"), dict)
    ):
        payload = valid_blazor_bridge_payload(module)
    if (
        key == "operator_release_dashboard"
        and payload.get("status") == "pass"
        and not isinstance(payload.get("release_readiness"), dict)
    ):
        payload = {
            **payload,
            "verdict": "OPERABLE_RELEASE_READY",
            "release_readiness": {
                "full_release_ready": True,
                "nightly_handoff_ready": True,
                "full_release_blockers": [],
            },
        }
    (published / path.name).write_text(json.dumps(payload), encoding="utf-8")


class FinalGoldJanitorTests(unittest.TestCase):
    def test_windows_visual_audit_is_release_blocking_by_default_but_explicit_dev_override_remains(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            default_module = load_module()
        self.assertFalse(default_module.IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING)

        with mock.patch.dict(
            os.environ,
            {"CHUMMER_IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING": "1"},
            clear=True,
        ):
            override_module = load_module()
        self.assertTrue(override_module.IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING)

    def test_verified_staged_public_edge_is_activation_proof_not_local_surface_regression(self) -> None:
        module = load_module()
        required_gates = {
            name: {"status": "pass", "pass": True}
            for name in module.ROOT_BLOCKER_LOCAL_SURFACE_GATES
        }
        required_gates["public_edge_postdeploy_gate"].update(
            {
                "status": "fail",
                "pass": False,
                "release_truth_runtime_blocker_class": "deployment_activation_proof_required",
                "release_truth_runtime_overlay_root": "/overlay/active/app",
                "release_truth_runtime_failures": [
                    "public_edge_overlay_source_fingerprint_missing: legacy active metadata",
                    "public_edge_overlay_source_fingerprint_mismatch: active program digest differs",
                ],
                "release_truth_staged_overlay_observation": {
                    "status": "pass",
                    "receipt_path": "/published/PUBLIC_EDGE_PORTAL_OVERLAY_PUBLISH.generated.json",
                    "staging_root": "/overlay/next/app",
                    "activation_transaction_journal_path": "/overlay/.app.activation-transaction.json",
                    "activation_transaction_journal_exists": False,
                },
                "failures": [
                    "public_edge_overlay_source_fingerprint_missing: legacy active metadata",
                ],
            }
        )
        root_release_blockers = {
            "root_blockers": [
                {
                    "id": "release_truth:public_edge_postdeploy_gate",
                    "external_prerequisite": "Obtain explicit activation authority and capture post-activation proof.",
                    "verify_command": "python3 scripts/verify_public_edge_postdeploy_gate.py",
                }
            ]
        }

        families, local_surface_status = module.final_gold_root_blocker_families(
            required_gates,
            root_release_blockers,
        )

        family_ids = [item["id"] for item in families]
        self.assertIn("public_edge_activation_proof", family_ids)
        self.assertNotIn("local_surface_regressions", family_ids)
        activation_family = next(item for item in families if item["id"] == "public_edge_activation_proof")
        self.assertEqual("deployment_activation_proof", activation_family["kind"])
        self.assertFalse(activation_family["local_surface_regression"])
        self.assertTrue(activation_family["activation_authority_required"])
        self.assertTrue(activation_family["post_activation_proof_required"])
        self.assertEqual("/overlay/next/app", activation_family["staging_root"])
        self.assertFalse(local_surface_status["all_passing"])
        public_edge_check = next(
            item for item in local_surface_status["checks"] if item["name"] == "public_edge_postdeploy_gate"
        )
        self.assertFalse(public_edge_check["pass"])
        self.assertEqual(
            "deployment_activation_proof_required",
            public_edge_check["derived_root_cause"],
        )

    def test_windows_operator_request_artifacts_refreshes_watcher_state_via_status_command(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="final-gold-windows-watcher-refresh-") as temp_dir:
            root = Path(temp_dir)
            intake_request = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            ask_text_path = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"
            ask_metadata_path = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"
            watcher_state_path = root / "state" / "windows_installer_gold_proof_watcher.generated.json"
            ask_text_path.parent.mkdir(parents=True, exist_ok=True)
            ask_text_path.write_text("windows ask current\n", encoding="utf-8")
            ask_metadata_path.write_text("{}\n", encoding="utf-8")
            watcher_state_path.parent.mkdir(parents=True, exist_ok=True)
            watcher_state_path.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-07-06T15:00:00Z",
                        "status": "running",
                        "pid": 1111,
                        "process_alive": True,
                        "matching_process_pids": [1111],
                        "matching_process_count": 1,
                        "duplicate_process_pids": [],
                        "duplicate_process_count": 0,
                        "note": "stale watcher snapshot",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            payload = {
                "preferred_drop_path": str(root / "incoming" / "windows-proof.zip"),
                "operator_telegram_draft": {
                    "current_message_path": str(ask_text_path),
                    "current_metadata_path": str(ask_metadata_path),
                    "receipt_name": "windows.receipt.json",
                    "message_preview": "Windows operator ask preview",
                },
                "artifact_intake": {
                    "watcher_state_path": str(watcher_state_path),
                    "watcher_status_command": "python3 watcher-status --intake-request /tmp/intake.json",
                },
            }
            intake_request.parent.mkdir(parents=True, exist_ok=True)
            intake_request.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            def fake_run(*_args, **_kwargs):
                watcher_state_path.write_text(
                    json.dumps(
                        {
                            "generated_at_utc": "2026-07-06T15:24:14Z",
                            "status": "running",
                            "pid": 2086931,
                            "process_alive": True,
                            "matching_process_pids": [2086931],
                            "matching_process_count": 1,
                            "duplicate_process_pids": [],
                            "duplicate_process_count": 0,
                            "note": "watcher discovered by pid file or process scan",
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch.object(module.subprocess, "run", side_effect=fake_run):
                artifacts = module.windows_operator_request_artifacts(intake_request, payload)

        self.assertEqual("2026-07-06T15:24:14Z", artifacts["watcher_state_receipt_generated_at_utc"])
        self.assertEqual(2086931, artifacts["watcher_pid"])
        self.assertEqual("watcher discovered by pid file or process scan", artifacts["watcher_note"])

    def test_windows_operator_request_artifacts_refreshes_auto_import_before_watcher_state(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="final-gold-windows-auto-import-refresh-") as temp_dir:
            root = Path(temp_dir)
            intake_request = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            auto_import_path = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
            ask_text_path = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"
            ask_metadata_path = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"
            watcher_state_path = root / "state" / "windows_installer_gold_proof_watcher.generated.json"
            ask_text_path.parent.mkdir(parents=True, exist_ok=True)
            ask_text_path.write_text("windows ask current\n", encoding="utf-8")
            ask_metadata_path.write_text("{}\n", encoding="utf-8")
            watcher_state_path.parent.mkdir(parents=True, exist_ok=True)
            watcher_state_path.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-07-06T15:00:00Z",
                        "status": "running",
                        "pid": 1111,
                        "process_alive": True,
                        "matching_process_pids": [1111],
                        "matching_process_count": 1,
                        "duplicate_process_pids": [],
                        "duplicate_process_count": 0,
                        "note": "stale watcher snapshot",
                        "auto_import_receipt_status": "waiting_for_artifact",
                        "auto_import_receipt_generated_at_utc": "2026-07-06T15:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            auto_import_path.parent.mkdir(parents=True, exist_ok=True)
            auto_import_path.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-07-06T15:00:00Z",
                        "status": "waiting_for_artifact",
                        "actionable_candidate_count": 0,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            payload = {
                "preferred_drop_path": str(root / "incoming" / "windows-proof.zip"),
                "operator_telegram_draft": {
                    "current_message_path": str(ask_text_path),
                    "current_metadata_path": str(ask_metadata_path),
                    "receipt_name": "windows.receipt.json",
                    "message_preview": "Windows operator ask preview",
                },
                "artifact_intake": {
                    "watcher_state_path": str(watcher_state_path),
                    "watcher_status_command": "python3 watcher-status --intake-request /tmp/intake.json",
                    "auto_import_command": "python3 auto-import --intake-request /tmp/intake.json",
                },
            }
            intake_request.parent.mkdir(parents=True, exist_ok=True)
            intake_request.write_text(json.dumps(payload) + "\n", encoding="utf-8")
            run_calls: list[list[str]] = []

            def fake_run(args, **_kwargs):
                command = list(args)
                run_calls.append(command)
                if command[:2] == ["python3", "auto-import"]:
                    auto_import_path.write_text(
                        json.dumps(
                            {
                                "generated_at_utc": "2026-07-06T15:24:12Z",
                                "status": "waiting_for_artifact",
                                "actionable_candidate_count": 0,
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                elif command[:2] == ["python3", "watcher-status"]:
                    watcher_state_path.write_text(
                        json.dumps(
                            {
                                "generated_at_utc": "2026-07-06T15:24:14Z",
                                "status": "running",
                                "pid": 2086931,
                                "process_alive": True,
                                "matching_process_pids": [2086931],
                                "matching_process_count": 1,
                                "duplicate_process_pids": [],
                                "duplicate_process_count": 0,
                                "note": "watcher discovered by pid file or process scan",
                                "auto_import_receipt_status": "waiting_for_artifact",
                                "auto_import_receipt_generated_at_utc": "2026-07-06T15:24:12Z",
                            }
                        )
                        + "\n",
                        encoding="utf-8",
                    )
                return mock.Mock(returncode=0, stdout="", stderr="")

            with mock.patch.object(module.subprocess, "run", side_effect=fake_run):
                artifacts = module.windows_operator_request_artifacts(intake_request, payload)

        self.assertEqual(str(auto_import_path), artifacts["auto_import_receipt_path"])
        self.assertEqual("2026-07-06T15:24:12Z", artifacts["auto_import_receipt_generated_at_utc"])
        self.assertEqual("2026-07-06T15:24:14Z", artifacts["watcher_state_receipt_generated_at_utc"])
        self.assertEqual(["python3", "auto-import"], run_calls[0][:2])
        self.assertEqual(["python3", "watcher-status"], run_calls[1][:2])

    def test_windows_operator_request_artifacts_can_skip_runtime_refresh(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="final-gold-windows-no-runtime-refresh-") as temp_dir:
            root = Path(temp_dir)
            intake_request = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json"
            auto_import_path = root / "published" / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"
            ask_text_path = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"
            ask_metadata_path = root / "_completion" / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json"
            watcher_state_path = root / "state" / "windows_installer_gold_proof_watcher.generated.json"
            ask_text_path.parent.mkdir(parents=True, exist_ok=True)
            ask_text_path.write_text("windows ask current\n", encoding="utf-8")
            ask_metadata_path.write_text("{}\n", encoding="utf-8")
            watcher_state_path.parent.mkdir(parents=True, exist_ok=True)
            watcher_state_path.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-07-06T15:00:00Z",
                        "status": "running",
                        "pid": 1111,
                        "process_alive": True,
                        "matching_process_pids": [1111],
                        "matching_process_count": 1,
                        "duplicate_process_pids": [],
                        "duplicate_process_count": 0,
                        "note": "stale watcher snapshot",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            auto_import_path.parent.mkdir(parents=True, exist_ok=True)
            auto_import_path.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-07-06T15:00:00Z",
                        "status": "waiting_for_artifact",
                        "actionable_candidate_count": 0,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            payload = {
                "preferred_drop_path": str(root / "incoming" / "windows-proof.zip"),
                "operator_telegram_draft": {
                    "current_message_path": str(ask_text_path),
                    "current_metadata_path": str(ask_metadata_path),
                    "receipt_name": "windows.receipt.json",
                    "message_preview": "Windows operator ask preview",
                },
                "artifact_intake": {
                    "watcher_state_path": str(watcher_state_path),
                    "watcher_status_command": "python3 watcher-status --intake-request /tmp/intake.json",
                    "auto_import_command": "python3 auto-import --intake-request /tmp/intake.json",
                },
            }
            intake_request.parent.mkdir(parents=True, exist_ok=True)
            intake_request.write_text(json.dumps(payload) + "\n", encoding="utf-8")

            with mock.patch.object(module.subprocess, "run") as mocked_run:
                artifacts = module.windows_operator_request_artifacts(
                    intake_request,
                    payload,
                    refresh_runtime_receipts=False,
                )

        mocked_run.assert_not_called()
        self.assertEqual("2026-07-06T15:00:00Z", artifacts["auto_import_receipt_generated_at_utc"])
        self.assertEqual("2026-07-06T15:00:00Z", artifacts["watcher_state_receipt_generated_at_utc"])
        self.assertEqual(1111, artifacts["watcher_pid"])
        self.assertEqual("stale watcher snapshot", artifacts["watcher_note"])

    def test_flagship_recovery_accepts_explicit_release_truth_blockers(self) -> None:
        module = load_module()

        self.assertTrue(
            module.flagship_product_readiness_launch_blockers_recoverable(
                {
                    "launch_critical_nested_blockers": [
                        "release channel channel is preview, not a flagship stable lane",
                        "release channel supportability is not gold_supported",
                        "release channel rollout is promoted_preview, not public_stable",
                        "Windows installer visual audit source digest does not match promoted installer",
                    ]
                }
            )
        )

    def test_enrich_operator_ask_delivery_details_hides_historical_preview_when_request_not_required(self) -> None:
        module = load_module()

        artifacts = module.enrich_operator_ask_delivery_details(
            {
                "request_status": "not_required",
                "operator_ask_message_sha256": "a" * 64,
                "operator_ask_delivery_text_sha256": "b" * 64,
                "operator_ask_delivery_text_preview": "Old operator ask said proof was still missing.",
                "operator_ask_send_command": "python3 resend-google",
                "import_command": "python3 import-google",
                "auto_import_watch_command": "python3 watch-google",
                "post_import_commands": ["python3 verify-google"],
                "preferred_drop_path": "/tmp/google-proof.zip",
            }
        )

        self.assertFalse(artifacts["operator_ask_delivery_current_text_comparable"])
        self.assertFalse(artifacts["operator_ask_delivery_matches_current_text"])
        self.assertFalse(artifacts["operator_ask_delivery_needs_resend"])
        self.assertEqual("", artifacts["operator_ask_resend_command"])
        self.assertTrue(artifacts["operator_ask_delivery_historical_only"])
        self.assertEqual("", artifacts["operator_ask_delivery_text_preview"])
        self.assertEqual(
            "Old operator ask said proof was still missing.",
            artifacts["operator_ask_delivery_historical_text_preview"],
        )
        self.assertEqual("", artifacts["operator_ask_send_command"])
        self.assertEqual("", artifacts["import_command"])
        self.assertEqual("", artifacts["auto_import_watch_command"])
        self.assertEqual([], artifacts["post_import_commands"])
        self.assertEqual("", artifacts["preferred_drop_path"])
        self.assertTrue(artifacts["operator_action_historical_only"])
        self.assertEqual(
            {
                "operator_ask_send_command": "python3 resend-google",
                "import_command": "python3 import-google",
                "auto_import_watch_command": "python3 watch-google",
                "post_import_commands": ["python3 verify-google"],
                "preferred_drop_path": "/tmp/google-proof.zip",
            },
            artifacts["operator_action_historical_artifacts"],
        )

    def test_enrich_operator_ask_delivery_details_restores_actions_when_effective_status_requires_followup(self) -> None:
        module = load_module()

        suppressed = module.enrich_operator_ask_delivery_details(
            {
                "request_status": "not_required",
                "operator_ask_message_sha256": "a" * 64,
                "operator_ask_delivery_text_sha256": "b" * 64,
                "operator_ask_delivery_text_preview": "Old operator ask said proof was still missing.",
                "operator_ask_send_command": "python3 resend-windows",
                "import_command": "python3 import-windows",
                "auto_import_watch_command": "python3 watch-windows",
                "post_import_commands": ["python3 verify-windows"],
                "preferred_drop_path": "/tmp/windows-proof.zip",
            }
        )

        suppressed["request_effective_status"] = "external_artifact_required"
        suppressed["operator_action_still_required"] = True
        restored = module.enrich_operator_ask_delivery_details(suppressed)

        self.assertTrue(restored["operator_ask_delivery_current_text_comparable"])
        self.assertFalse(restored["operator_ask_delivery_matches_current_text"])
        self.assertTrue(restored["operator_ask_delivery_needs_resend"])
        self.assertEqual("python3 resend-windows", restored["operator_ask_resend_command"])
        self.assertFalse(restored["operator_ask_delivery_historical_only"])
        self.assertEqual(
            "Old operator ask said proof was still missing.",
            restored["operator_ask_delivery_text_preview"],
        )
        self.assertEqual("python3 resend-windows", restored["operator_ask_send_command"])
        self.assertEqual("python3 import-windows", restored["import_command"])
        self.assertEqual("python3 watch-windows", restored["auto_import_watch_command"])
        self.assertEqual(["python3 verify-windows"], restored["post_import_commands"])
        self.assertEqual("/tmp/windows-proof.zip", restored["preferred_drop_path"])

    def test_build_payload_hides_historical_google_delivery_preview_when_request_not_required(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-google-history-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            for key, path in required.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "teable_important_work":
                    payload = passing_teable_important_work_payload(module)
                if key == "public_route_proof":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "summary": {"route_count": 10, "failed_count": 0, "negative_path_failed_count": 0},
                    }
                if key == "google_oauth_linking_proof":
                    payload["operator_request_artifacts"] = {
                        "request_status": "not_required",
                        "operator_ask_message_sha256": "a" * 64,
                        "operator_ask_delivery_text_sha256": "b" * 64,
                        "operator_ask_delivery_text_preview": "Old operator ask said proof was still missing.",
                        "operator_ask_send_command": "python3 resend-google",
                    }
                path.write_text(json.dumps(payload), encoding="utf-8")

            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "REQUIRED_RECEIPTS", required), \
                mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"):
                payload = module.build_payload([])

        artifacts = payload["required_gates"]["google_oauth_linking_proof"]["operator_request_artifacts"]
        self.assertFalse(artifacts["operator_ask_delivery_current_text_comparable"])
        self.assertFalse(artifacts["operator_ask_delivery_matches_current_text"])
        self.assertFalse(artifacts["operator_ask_delivery_needs_resend"])
        self.assertEqual("", artifacts["operator_ask_delivery_text_preview"])
        self.assertEqual(
            "Old operator ask said proof was still missing.",
            artifacts["operator_ask_delivery_historical_text_preview"],
        )
        self.assertTrue(artifacts["operator_ask_delivery_historical_only"])

    def test_build_verdict_markdown_hides_google_action_commands_when_request_not_required(self) -> None:
        module = load_module()
        payload = {
            "verdict": "NOT_GOLD",
            "generated_at_utc": module.now_iso(),
            "scope": "test",
            "root_blockers": [],
            "required_gates": {
                "google_oauth_linking_proof": {
                    "status": "fail",
                    "pass": False,
                    "path": "/tmp/google-proof.generated.json",
                    "failures": ["google oauth operator evidence is still missing: /tmp/operator-evidence.json"],
                    "operator_request_artifacts": {
                        "request_status": "not_required",
                        "required_operator_evidence_path": "/tmp/operator-evidence.json",
                        "request_receipt_path": "/tmp/operator-request.generated.json",
                        "operator_ask_text_path": "/tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt",
                        "operator_ask_send_command": "python3 resend-google",
                        "operator_ask_resend_command": "python3 resend-google",
                    },
                }
            },
        }

        markdown = module.build_verdict_markdown(payload)

        self.assertIn("google oauth operator evidence:", markdown)
        self.assertNotIn("google oauth operator ask send:", markdown)
        self.assertNotIn("google oauth operator ask resend:", markdown)

    def test_public_edge_semantics_short_circuit_frontdoor_noise_when_homepage_lane_is_missing(self) -> None:
        module = load_module()
        payload = passing_public_edge_postdeploy_payload(module)
        payload.update(
            {
                "frontdoorNavigationStatus": "fail",
                "frontdoorNavigationMobileArtifactContract": "",
                "frontdoorNavigationLedgerArtifactContract": "",
                "frontdoorNavigationGatedTargets": [],
                "frontdoorNavigationPublicTargets": ["Build", "Play"],
                "frontdoorNavigationPlayRoute": "",
                "frontdoorNavigationDirectPlayerRoute": "",
                "frontdoorNavigationDirectPlayerHttpStatus": 500,
                "frontdoorNavigationFinalUrl": "",
                "frontdoorNavigationGmRoute": "",
                "frontdoorNavigationGmHttpStatus": 500,
                "frontdoorNavigationGmFinalUrl": "",
                "frontdoorNavigationLedgerPrimary": True,
                "failures": [
                    module.PUBLIC_EDGE_HOMEPAGE_LANE_DISCLOSURE_RECEIPT_FAILURE,
                    module.PUBLIC_EDGE_HOMEPAGE_LANE_COPY_MISMATCH_RECEIPT_FAILURE,
                ],
            }
        )

        failures = module.public_edge_postdeploy_semantic_failures(payload)

        self.assertIn("public-edge postdeploy homepage does not disclose current public lane", failures)
        self.assertIn("public-edge postdeploy receipt contains failures", failures)
        self.assertNotIn("public-edge postdeploy frontdoorNavigationStatus is not pass", failures)
        self.assertNotIn("public-edge postdeploy frontdoorNavigationMobileArtifactContract is not chummer.frontdoor_mobile_launch.v2", failures)
        self.assertNotIn("public-edge postdeploy frontdoorNavigationLedgerArtifactContract is not chummer.black_ledger_globe_frontdoor.v1", failures)
        self.assertNotIn("public-edge postdeploy front-door navigation does not gate Build", failures)
        self.assertNotIn("public-edge postdeploy front-door navigation Play route is not /mobile/player", failures)
        self.assertNotIn("public-edge postdeploy Black Ledger remains primary on the front door", failures)

    def test_public_edge_semantics_fail_closed_on_v1_raw_identity_and_private_cache(self) -> None:
        module = load_module()
        payload = passing_public_edge_postdeploy_payload(module)
        payload.update(
            {
                "pwaOfflineCacheArtifactContract": "chummer.pwa_offline_cache.v1",
                "pwaOfflineCachePrivateNavigationCached": True,
                "pwaOfflineCacheStaticPaths": [*payload["pwaOfflineCacheStaticPaths"], "/mobile/player?sessionId=private-session"],
                "frontdoorNavigationMobileArtifactContract": "chummer.frontdoor_mobile_launch.v1",
                "frontdoorNavigationFinalUrl": "https://chummer.run/mobile/player?sessionId=private-session",
                "frontdoorNavigationGmRoute": "/mobile/gm?sessionId=private-session",
                "frontdoorNavigationGmFinalUrl": "https://chummer.run/mobile/gm?deviceId=private-device",
                "frontdoorNavigationPlayerSessionHandoffUrl": "https://chummer.run/mobile/player?sessionId=private-session&role=Player",
            }
        )

        failures = module.public_edge_postdeploy_semantic_failures(payload)

        self.assertIn("public-edge postdeploy pwaOfflineCacheArtifactContract is not chummer.pwa_offline_cache.v2", failures)
        self.assertIn("public-edge postdeploy frontdoorNavigationMobileArtifactContract is not chummer.frontdoor_mobile_launch.v2", failures)
        self.assertIn("public-edge postdeploy PWA offline static cache contains a private or query-bearing route", failures)
        self.assertIn("public-edge postdeploy PWA offline cache did not prove private navigation remain uncached", failures)
        self.assertIn("public-edge postdeploy front-door visible Player URL is not query-free /mobile/player", failures)
        self.assertIn("public-edge postdeploy front-door Player handoff is not a redacted player route", failures)

    def test_materializers_build_provider_receipts_before_ltd_stack(self) -> None:
        module = load_module()
        commands = [" ".join(command) for command in module.MATERIALIZERS]

        icanpreneur_index = commands.index("python3 scripts/verify_icanpreneur_discovery_lane.py")
        provider_index = commands.index("python3 scripts/verify_provider_proof_discoverability.py")
        ltd_index = commands.index("python3 scripts/materialize_ltd_optimization_stack.py")

        self.assertLess(icanpreneur_index, provider_index)
        self.assertLess(provider_index, ltd_index)
        self.assertIn("icanpreneur_discovery_lane", module.REQUIRED_RECEIPTS)
        self.assertIn("icanpreneur_discovery_lane", module.FRESHNESS_REQUIRED_GATES)

    def test_materializers_require_full_public_edge_postdeploy_gate(self) -> None:
        module = load_module()
        commands = [" ".join(command) for command in module.MATERIALIZERS]
        public_edge_command = next(command for command in commands if "scripts/verify_public_edge_postdeploy_gate.py" in command)
        dashboard_command = next(command for command in commands if "scripts/materialize_operator_release_dashboard.py" in command)

        live_windows_index = commands.index("python3 scripts/verify_live_public_windows_installer.py --base-url https://chummer.run")
        public_edge_index = commands.index(public_edge_command)
        blazor_index = commands.index("python3 scripts/verify_blazor_execution_horizon_bridge.py")

        self.assertLess(live_windows_index, public_edge_index)
        self.assertLess(public_edge_index, blazor_index)
        self.assertIn("--expected-release-channel nightly", public_edge_command)
        self.assertIn("--require-downloads-status-playwright", public_edge_command)
        self.assertIn("--require-mobile-pwa-viewport-playwright", public_edge_command)
        self.assertIn("--require-frontdoor-navigation-playwright", public_edge_command)
        self.assertIn("--release-ready-self-check", dashboard_command)
        self.assertIn("public_edge_postdeploy_gate", module.REQUIRED_RECEIPTS)
        self.assertIn("public_edge_postdeploy_gate", module.FRESHNESS_REQUIRED_GATES)

    def test_materializers_build_minimal_experience_before_design_gate(self) -> None:
        module = load_module()
        commands = [" ".join(command) for command in module.MATERIALIZERS]

        minimal_index = next(index for index, command in enumerate(commands) if "scripts/verify_minimal_experience_gate.py" in command)
        premium_index = commands.index("python3 scripts/verify_premium_ui_design_exit_gate.py --completion-dir /docker/chummercomplete/_completion/chummer_run_redesign_closure")
        design_index = commands.index("python3 scripts/materialize_design_quality_gate.py")

        self.assertLess(minimal_index, design_index)
        self.assertLess(minimal_index, premium_index)
        self.assertLess(premium_index, design_index)
        self.assertIn("premium_ui_design_exit_gate", module.REQUIRED_RECEIPTS)
        self.assertIn("premium_ui_design_exit_gate", module.FRESHNESS_REQUIRED_GATES)

    def test_materializers_refresh_release_ready_before_operator_dashboard(self) -> None:
        module = load_module()
        commands = [" ".join(command) for command in module.MATERIALIZERS]

        release_ready_index = commands.index("python3 scripts/materialize_release_ready_receipt.py")
        operator_dashboard_index = commands.index("python3 scripts/materialize_operator_release_dashboard.py")

        self.assertLess(release_ready_index, operator_dashboard_index)

    def test_materializers_refresh_hub_local_release_proof_after_release_ready(self) -> None:
        module = load_module()
        commands = [" ".join(command) for command in module.MATERIALIZERS]

        release_ready_index = commands.index("python3 scripts/materialize_release_ready_receipt.py")
        hub_local_release_proof_index = commands.index(
            "python3 scripts/materialize_hub_local_release_proof.py "
            f"{module.PUBLISHED_ROOT / 'HUB_LOCAL_RELEASE_PROOF.generated.json'} "
            f"{module.DEFAULT_BASE_URL} docker-compose.yml 120 true"
        )

        self.assertLess(release_ready_index, hub_local_release_proof_index)

    def test_materializers_refresh_hub_local_release_proof_before_operator_dashboard(self) -> None:
        module = load_module()
        commands = [" ".join(command) for command in module.MATERIALIZERS]

        hub_local_release_proof_index = commands.index(
            "python3 scripts/materialize_hub_local_release_proof.py "
            f"{module.PUBLISHED_ROOT / 'HUB_LOCAL_RELEASE_PROOF.generated.json'} "
            f"{module.DEFAULT_BASE_URL} docker-compose.yml 120 true"
        )
        operator_dashboard_index = commands.index("python3 scripts/materialize_operator_release_dashboard.py")

        self.assertLess(hub_local_release_proof_index, operator_dashboard_index)

    def test_materializers_refresh_windows_proof_intake_before_release_ready(self) -> None:
        module = load_module()
        commands = [" ".join(command) for command in module.MATERIALIZERS]

        verify_windows_index = commands.index("python3 scripts/verify_windows_installer_visual_audit.py")
        intake_index = commands.index(
            "python3 scripts/materialize_windows_installer_visual_audit_intake_request.py --output "
            f"{module.PUBLISHED_ROOT / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'}"
        )
        auto_import_index = commands.index(
            "python3 scripts/auto_import_windows_installer_gold_proof.py --intake-request "
            f"{module.PUBLISHED_ROOT / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
            "--output "
            f"{module.PUBLISHED_ROOT / 'WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json'} "
            "--wait-seconds 0"
        )
        release_ready_index = commands.index("python3 scripts/materialize_release_ready_receipt.py")

        self.assertLess(verify_windows_index, intake_index)
        self.assertLess(intake_index, auto_import_index)
        self.assertLess(auto_import_index, release_ready_index)

    def test_public_route_materializer_uses_bounded_live_probe_settings(self) -> None:
        module = load_module()
        public_route_command = next(
            command for command in module.MATERIALIZERS
            if "scripts/verify_public_routes_from_manifest.py" in " ".join(command)
        )

        command_text = " ".join(public_route_command)
        self.assertIn("--request-timeout-seconds 2", command_text)
        self.assertIn("--max-retries 1", command_text)
        self.assertIn("--retry-delay-seconds 0.1", command_text)

    def test_public_edge_postdeploy_gate_is_required_and_materialized(self) -> None:
        module = load_module()
        public_edge_command = next(
            command for command in module.MATERIALIZERS
            if "scripts/verify_public_edge_postdeploy_gate.py" in " ".join(command)
        )

        command_text = " ".join(public_edge_command)
        self.assertIn("public_edge_postdeploy_gate", module.REQUIRED_RECEIPTS)
        self.assertIn("public_edge_postdeploy_gate", module.FRESHNESS_REQUIRED_GATES)
        self.assertNotIn("--skip-preflight", command_text)
        self.assertIn("--require-downloads-status-playwright", command_text)
        self.assertIn("--require-mobile-pwa-viewport-playwright", command_text)
        self.assertIn("--require-pwa-offline-cache-playwright", command_text)
        self.assertIn("--require-frontdoor-navigation-playwright", command_text)
        self.assertIn("--reuse-existing-playwright-artifacts", command_text)
        self.assertIn(f"--reuse-artifact-max-age-hours {module.RECRAWL_MAX_AGE_HOURS}", command_text)
        self.assertIn(str(module.PUBLIC_EDGE_DOWNLOADS_STATUS_ARTIFACT_DIR), command_text)
        self.assertIn(str(module.PUBLIC_EDGE_MOBILE_VIEWPORT_ARTIFACT_DIR), command_text)
        self.assertIn(str(module.PUBLIC_EDGE_OFFLINE_CACHE_ARTIFACT_DIR), command_text)
        self.assertIn(str(module.PUBLIC_EDGE_FRONTDOOR_ARTIFACT_DIR), command_text)
        self.assertIn("PUBLIC_EDGE_POSTDEPLOY_GATE.generated.json", command_text)

    def test_teable_important_work_sync_is_required_and_materialized(self) -> None:
        module = load_module()
        commands = [" ".join(command) for command in module.MATERIALIZERS]

        self.assertIn("teable_important_work", module.REQUIRED_RECEIPTS)
        self.assertIn("teable_important_work", module.FRESHNESS_REQUIRED_GATES)
        self.assertIn("python3 scripts/sync_important_work_to_teable.py --sync", commands)

    def test_flagship_product_readiness_is_required_and_materialized(self) -> None:
        module = load_module()
        commands = [" ".join(command) for command in module.MATERIALIZERS]

        self.assertIn("flagship_product_readiness", module.REQUIRED_RECEIPTS)
        self.assertIn("flagship_product_readiness", module.FRESHNESS_REQUIRED_GATES)
        self.assertIn("python3 scripts/verify_flagship_product_readiness_gate.py", commands)
        self.assertIn("flagship_product_readiness", module.OPERATOR_DASHBOARD_REQUIRED_CHECKS)

    def test_google_oauth_operator_request_materializer_runs_before_release_ready(self) -> None:
        module = load_module()
        commands = [" ".join(command) for command in module.MATERIALIZERS]

        request_command = (
            "python3 scripts/materialize_google_oauth_linking_operator_evidence_request.py "
            f"--base-url {module.DEFAULT_BASE_URL} "
            "--output "
            f"{module.PUBLISHED_ROOT / 'GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json'} "
            "--evidence-path "
            f"{module.PUBLISHED_ROOT / 'GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE.generated.json'}"
        )
        auto_import_command = (
            "python3 scripts/auto_import_google_oauth_linking_operator_evidence.py "
            "--intake-request "
            f"{module.PUBLISHED_ROOT / 'GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_REQUEST.generated.json'} "
            "--output "
            f"{module.PUBLISHED_ROOT / 'GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT.generated.json'} "
            "--wait-seconds 0"
        )
        proof_command = (
            "python3 scripts/materialize_google_oauth_linking_proof.py "
            f"--base-url {module.DEFAULT_BASE_URL}"
        )
        request_verify_command = "python3 scripts/verify_google_oauth_linking_operator_evidence_request.py"
        proof_verify_command = "python3 scripts/verify_google_oauth_linking_proof.py"
        ea_materialize_command = "python3 scripts/materialize_ea_operator_readiness.py"
        ea_verify_command = "python3 scripts/verify_ea_operator_readiness.py"
        mymedia_materialize_command = "python3 scripts/materialize_mymedia_public_surface.py"
        mymedia_verify_command = "python3 scripts/verify_mymedia_public_surface.py"
        request_index = commands.index(request_command)
        request_verify_index = commands.index(request_verify_command)
        auto_import_index = commands.index(auto_import_command)
        proof_index = commands.index(proof_command)
        proof_verify_index = commands.index(proof_verify_command)
        ea_materialize_index = commands.index(ea_materialize_command)
        ea_verify_index = commands.index(ea_verify_command)
        mymedia_materialize_index = commands.index(mymedia_materialize_command)
        mymedia_verify_index = commands.index(mymedia_verify_command)
        release_ready_index = commands.index("python3 scripts/materialize_release_ready_receipt.py")
        dashboard_index = commands.index("python3 scripts/materialize_operator_release_dashboard.py")

        self.assertIn("google_oauth_linking_proof", module.REQUIRED_RECEIPTS)
        self.assertIn("google_oauth_linking_proof", module.FRESHNESS_REQUIRED_GATES)
        self.assertLess(request_index, release_ready_index)
        self.assertLess(request_index, request_verify_index)
        self.assertLess(request_verify_index, auto_import_index)
        self.assertLess(auto_import_index, proof_index)
        self.assertLess(request_index, proof_index)
        self.assertLess(proof_index, proof_verify_index)
        self.assertLess(proof_verify_index, release_ready_index)
        self.assertLess(proof_verify_index, dashboard_index)
        self.assertLess(ea_materialize_index, ea_verify_index)
        self.assertLess(ea_verify_index, dashboard_index)
        self.assertLess(mymedia_materialize_index, mymedia_verify_index)
        self.assertLess(mymedia_verify_index, dashboard_index)
        self.assertLess(proof_index, release_ready_index)
        self.assertLess(proof_index, dashboard_index)
        self.assertLess(request_index, dashboard_index)
        self.assertLess(auto_import_index, release_ready_index)
        self.assertLess(auto_import_index, dashboard_index)

    def test_operator_dashboard_required_checks_match_release_blocking_contract(self) -> None:
        module = load_module()

        self.assertEqual(
            {
                "account_handoff_runtime_config",
                "design_quality_gate",
                "external_distribution_mirror_proof",
                "flagship_product_readiness",
                "google_oauth_linking_proof",
                "participate_billing_honesty",
                "public_copy_leak_gate",
                "public_edge_postdeploy_gate",
                "public_route_proof",
                "release_channel",
                "release_ready",
                "ruleset_readiness",
                "teable_important_work",
                "ui_frame_integrity",
                "windows_installer_visual_audit",
            },
            module.OPERATOR_DASHBOARD_REQUIRED_CHECKS,
        )
        self.assertEqual(
            module.OPERATOR_DASHBOARD_REQUIRED_CHECKS - {"release_channel"},
            module.OPERATOR_DASHBOARD_FRESHNESS_REQUIRED_CHECKS,
        )

    def test_run_materializers_records_timeout_instead_of_hanging(self) -> None:
        module = load_module()
        timeout = module.MATERIALIZER_TIMEOUT_SECONDS
        process = mock.Mock(pid=1234, returncode=None)
        process.wait.side_effect = [
            subprocess.TimeoutExpired(cmd=["python3", "slow.py"], timeout=timeout),
            0,
        ]

        def fake_popen(*_args, **kwargs):
            kwargs["stdout"].write(b"partial out")
            kwargs["stdout"].flush()
            kwargs["stderr"].write(b"partial err")
            kwargs["stderr"].flush()
            return process

        with (
            mock.patch.object(module, "MATERIALIZERS", [["python3", "slow.py"]]),
            mock.patch.object(module.subprocess, "Popen", side_effect=fake_popen),
            mock.patch.object(module.os, "killpg") as killpg,
        ):
            results = module.run_materializers()

        self.assertEqual(1, len(results))
        result = results[0]
        self.assertEqual("python3 slow.py", result["command"])
        self.assertEqual(124, result["returncode"])
        self.assertTrue(result["timed_out"])
        self.assertEqual(timeout, result["timeout_seconds"])
        self.assertEqual("partial out", result["stdout"])
        self.assertEqual("partial err", result["stderr"])
        killpg.assert_called_once_with(1234, module.signal.SIGTERM)

    def test_release_ready_materializer_uses_extended_timeout(self) -> None:
        module = load_module()
        command = ["python3", "scripts/materialize_release_ready_receipt.py"]
        process = mock.Mock(pid=1234, returncode=0)
        process.wait.return_value = 0

        with mock.patch.object(module, "MATERIALIZERS", [command]), mock.patch.object(module.subprocess, "Popen", return_value=process):
            results = module.run_materializers()

        timeout = module.materializer_timeout_seconds(command)
        self.assertGreaterEqual(timeout, module.RELEASE_READY_MATERIALIZER_TIMEOUT_SECONDS)
        self.assertGreater(timeout, module.MATERIALIZER_TIMEOUT_SECONDS)
        process.wait.assert_called_once_with(timeout=timeout)
        self.assertEqual(timeout, results[0]["timeout_seconds"])

    def test_black_ledger_live_media_materializer_uses_extended_timeout(self) -> None:
        module = load_module()
        command = ["python3", "scripts/verify_black_ledger_live_media_proof.py", "--base-url", "https://chummer.run"]
        process = mock.Mock(pid=1234, returncode=0)
        process.wait.return_value = 0

        with mock.patch.object(module, "MATERIALIZERS", [command]), mock.patch.object(module.subprocess, "Popen", return_value=process):
            results = module.run_materializers()

        timeout = module.materializer_timeout_seconds(command)
        self.assertGreaterEqual(timeout, module.BLACK_LEDGER_LIVE_MEDIA_MATERIALIZER_TIMEOUT_SECONDS)
        self.assertGreater(timeout, module.MATERIALIZER_TIMEOUT_SECONDS)
        process.wait.assert_called_once_with(timeout=timeout)
        self.assertEqual(timeout, results[0]["timeout_seconds"])

    def test_payload_suppresses_duplicate_materializer_failure_when_gate_refreshed_during_command(self) -> None:
        module = load_module()
        base_time = datetime.now(timezone.utc).replace(microsecond=0)
        command_started_at = (base_time - timedelta(seconds=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
        gate_generated_at = (base_time - timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        command_completed_at = base_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        with tempfile.TemporaryDirectory(prefix="gold-janitor-gate-refresh-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "release_channel":
                    payload["channel"] = "public_stable"
                    payload["channelId"] = "public_stable"
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "teable_important_work":
                    payload = {
                        "contract_name": "chummer.teable_important_work.v1",
                        "status": "pass",
                        "generated_at_utc": command_completed_at,
                        "row_count": 1,
                        "rows": [{"title": "row"}],
                        "sync": {"state": "passed", "attempted": True, "synced_count": 1, "failed_count": 0},
                    }
                if key == "flagship_product_readiness":
                    payload = passing_flagship_product_readiness_payload(module)
                if key == "operator_release_dashboard":
                    payload = passing_operator_dashboard_payload(module)
                if key == "google_oauth_linking_proof":
                    payload = {
                        "status": "waiting_for_artifact",
                        "generated_at_utc": gate_generated_at,
                        "failures": [
                            "operator_end_to_end_evidence: missing operator evidence receipt: /tmp/operator-evidence.json"
                        ],
                        "operator_request_artifacts": {
                            "required_operator_evidence_path": "/tmp/operator-evidence.json",
                            "request_receipt_path": "/tmp/operator-request.generated.json",
                            "operator_ask_text_path": "/tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt",
                            "operator_ask_send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt --receipt-name google-oauth-linking-operator-ask.receipt.json",
                            "operator_ask_delivery_needs_resend": True,
                            "operator_ask_resend_command": "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt --receipt-name google-oauth-linking-operator-ask.receipt.json",
                        },
                        "operator_end_to_end_evidence": {
                            "pass": False,
                            "exists": False,
                            "path": "/tmp/operator-evidence.json",
                            "failures": [
                                "missing operator evidence receipt: /tmp/operator-evidence.json"
                            ],
                        },
                    }
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"),
                mock.patch.object(module, "REQUIRED_RECEIPTS", required),
            ):
                payload = module.build_payload(
                    [
                        {
                            "command": "python3 scripts/materialize_google_oauth_linking_proof.py --base-url https://chummer.run",
                            "started_at_utc": command_started_at,
                            "completed_at_utc": command_completed_at,
                            "returncode": 1,
                            "stdout": "",
                            "stderr": "",
                            "timed_out": False,
                            "timeout_seconds": 180,
                        }
                    ]
                )

        self.assertIn("google_oauth_linking_proof failed", payload["failures"])
        self.assertIn(
            "google oauth operator evidence is still missing: /tmp/operator-evidence.json",
            payload["failures"],
        )
        self.assertNotIn(
            "materializer failed: python3 scripts/materialize_google_oauth_linking_proof.py --base-url https://chummer.run",
            payload["failures"],
        )

    def test_payload_keeps_materializer_failure_when_gate_was_not_refreshed_during_command(self) -> None:
        module = load_module()
        base_time = datetime.now(timezone.utc).replace(microsecond=0)
        gate_generated_at = (base_time - timedelta(seconds=12)).strftime("%Y-%m-%dT%H:%M:%SZ")
        command_started_at = (base_time - timedelta(seconds=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
        command_completed_at = base_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        with tempfile.TemporaryDirectory(prefix="gold-janitor-stale-gate-refresh-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "release_channel":
                    payload["channel"] = "public_stable"
                    payload["channelId"] = "public_stable"
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "teable_important_work":
                    payload = {
                        "contract_name": "chummer.teable_important_work.v1",
                        "status": "pass",
                        "generated_at_utc": command_completed_at,
                        "row_count": 1,
                        "rows": [{"title": "row"}],
                        "sync": {"state": "passed", "attempted": True, "synced_count": 1, "failed_count": 0},
                    }
                if key == "flagship_product_readiness":
                    payload = passing_flagship_product_readiness_payload(module)
                if key == "operator_release_dashboard":
                    payload = passing_operator_dashboard_payload(module)
                if key == "google_oauth_linking_proof":
                    payload = {
                        "status": "fail",
                        "generated_at_utc": gate_generated_at,
                        "failures": [
                            "operator_end_to_end_evidence: missing operator evidence receipt: /tmp/operator-evidence.json"
                        ],
                        "operator_request_artifacts": {
                            "required_operator_evidence_path": "/tmp/operator-evidence.json",
                        },
                        "operator_end_to_end_evidence": {
                            "pass": False,
                            "exists": False,
                            "path": "/tmp/operator-evidence.json",
                            "failures": [
                                "missing operator evidence receipt: /tmp/operator-evidence.json"
                            ],
                        },
                    }
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"),
                mock.patch.object(module, "REQUIRED_RECEIPTS", required),
            ):
                payload = module.build_payload(
                    [
                        {
                            "command": "python3 scripts/materialize_google_oauth_linking_proof.py --base-url https://chummer.run",
                            "started_at_utc": command_started_at,
                            "completed_at_utc": command_completed_at,
                            "returncode": 1,
                            "stdout": "",
                            "stderr": "",
                            "timed_out": False,
                            "timeout_seconds": 180,
                        }
                    ]
                )

        self.assertIn("google_oauth_linking_proof failed", payload["failures"])
        self.assertIn(
            "google oauth operator evidence is still missing: /tmp/operator-evidence.json",
            payload["failures"],
        )
        self.assertIn(
            "materializer failed: python3 scripts/materialize_google_oauth_linking_proof.py --base-url https://chummer.run",
            payload["failures"],
        )

    def test_payload_surfaces_google_oauth_missing_operator_evidence_path_without_materializer_results(self) -> None:
        module = load_module()
        generated_at_utc = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        with tempfile.TemporaryDirectory(prefix="gold-janitor-google-oauth-path-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "release_channel":
                    payload["channel"] = "public_stable"
                    payload["channelId"] = "public_stable"
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "teable_important_work":
                    payload = {
                        "contract_name": "chummer.teable_important_work.v1",
                        "status": "pass",
                        "generated_at_utc": generated_at_utc,
                        "row_count": 1,
                        "rows": [{"title": "row"}],
                        "sync": {"state": "passed", "attempted": True, "synced_count": 1, "failed_count": 0},
                    }
                if key == "flagship_product_readiness":
                    payload = passing_flagship_product_readiness_payload(module)
                if key == "operator_release_dashboard":
                    payload = passing_operator_dashboard_payload(module)
                if key == "google_oauth_linking_proof":
                    payload = {
                        "status": "fail",
                        "generated_at_utc": generated_at_utc,
                        "failures": [
                            "operator_end_to_end_evidence: missing operator evidence receipt: /tmp/operator-evidence.json"
                        ],
                        "operator_request_artifacts": {
                            "required_operator_evidence_path": "/tmp/operator-evidence.json",
                            "request_receipt_path": "/tmp/operator-request.generated.json",
                            "operator_ask_text_path": "/tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt",
                            "operator_ask_send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt --receipt-name google-oauth-linking-operator-ask.receipt.json",
                            "operator_ask_delivery_needs_resend": True,
                            "operator_ask_resend_command": "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt --receipt-name google-oauth-linking-operator-ask.receipt.json",
                        },
                        "operator_end_to_end_evidence": {
                            "pass": False,
                            "exists": False,
                            "path": "/tmp/operator-evidence.json",
                            "failures": [
                                "missing operator evidence receipt: /tmp/operator-evidence.json"
                            ],
                        },
                    }
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"),
                mock.patch.object(module, "REQUIRED_RECEIPTS", required),
            ):
                payload = module.build_payload([])
                markdown = module.build_verdict_markdown(payload)

        self.assertIn("google_oauth_linking_proof failed", payload["failures"])
        self.assertIn(
            "google_oauth_operator_evidence",
            [item["id"] for item in payload["root_blockers"]],
        )
        self.assertIn(
            "google oauth operator evidence is still missing: /tmp/operator-evidence.json",
            payload["failures"],
        )
        self.assertNotIn(
            "google oauth operator ask delivery is stale; resend current ask: "
            "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt "
            "--receipt-name google-oauth-linking-operator-ask.receipt.json",
            payload["failures"],
        )
        self.assertIn(
            "`google_oauth_operator_evidence`: Browser-backed Google OAuth linking evidence is still missing.",
            markdown,
        )
        self.assertIn(
            "google oauth operator evidence: required_path=/tmp/operator-evidence.json request_receipt=/tmp/operator-request.generated.json ask_text=/tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt",
            markdown,
        )
        self.assertIn(
            "google oauth operator ask send: python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt --receipt-name google-oauth-linking-operator-ask.receipt.json",
            markdown,
        )
        self.assertIn(
            "google oauth operator ask resend: python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt --receipt-name google-oauth-linking-operator-ask.receipt.json",
            markdown,
        )
        self.assertIn("  - advisory actions:", markdown)

    def test_payload_rewrites_auto_import_waiting_materializer_failure_as_missing_artifact(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-auto-import-waiting-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "teable_important_work":
                    payload = {
                        "contract_name": "chummer.teable_important_work.v1",
                        "status": "pass",
                        "generated_at_utc": "2026-07-04T17:00:08Z",
                        "row_count": 1,
                        "rows": [{"title": "row"}],
                        "sync": {"state": "passed", "attempted": True, "synced_count": 1, "failed_count": 0},
                    }
                if key == "flagship_product_readiness":
                    payload = passing_flagship_product_readiness_payload(module)
                if key == "operator_release_dashboard":
                    payload = passing_operator_dashboard_payload(module)
                if key == "windows_installer_visual_audit":
                    payload = {
                        **passing_required_receipt_payload(module, key),
                        "status": "fail",
                        "generated_at_utc": "2026-07-04T17:00:09Z",
                        "contract_name": module.WINDOWS_INSTALLER_VISUAL_AUDIT_CONTRACT_NAME,
                        "artifact": {"sha256": "a" * 64, "actualSha256": "a" * 64},
                        "startupReceipt": {"status": "pass", "artifactDigest": f"sha256:{'a' * 64}"},
                        "visualAuditSource": {
                            "exists": True,
                            "status": "pass",
                            "platform": "windows",
                            "hostClass": "native-windows-11",
                            "artifactSha256": "b" * 64,
                            "screenshotCount": 4,
                            "defaultDpiScreenshotCount": 2,
                            "scaledDpiScreenshotCount": 2,
                            "requiredSurfaces": ["install-progress", "completion"],
                        },
                        "failures": ["Windows installer visual audit source digest does not match promoted installer"],
                        "nextActions": ["Capture fresh Windows proof."],
                    }
                if key == "release_ready":
                    payload = {
                        **passing_required_receipt_payload(module, key),
                        "blocking_gate_artifacts": {
                            "windows_installer_visual_audit": {
                                "stage_release_build_handoff_path": "/tmp/RELEASE_BUILD_HANDOFF.generated.json",
                                "stage_release_build_handoff_status": "fail",
                                "stage_windows_visual_proof_handoff_path": "/tmp/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json",
                                "stage_windows_visual_proof_handoff_status": "ready_for_windows_host",
                                "stage_windows_visual_proof_handoff_summary": "Windows desktop exit gate failed: Windows installer visual proof version does not match release channel.",
                            },
                        },
                    }
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")

            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json").write_text(
                json.dumps(
                    {
                        "status": "waiting_for_artifact",
                        "generated_at_utc": "2026-07-04T17:00:05Z",
                        "preferred_drop_path": "/tmp/windows-installer-gold-proof-test.zip",
                    }
                ),
                encoding="utf-8",
            )

            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"),
                mock.patch.object(module, "REQUIRED_RECEIPTS", required),
            ):
                payload = module.build_payload(
                    [
                        {
                            "command": "python3 scripts/auto_import_windows_installer_gold_proof.py --intake-request /tmp/intake.json --output /tmp/output.json --wait-seconds 0",
                            "started_at_utc": "2026-07-04T17:00:00Z",
                            "completed_at_utc": "2026-07-04T17:00:06Z",
                            "returncode": 2,
                            "stdout": "windows_installer_visual_audit_auto_import:waiting",
                            "stderr": "",
                            "timed_out": False,
                            "timeout_seconds": 180,
                        }
                    ]
                )

        self.assertIn("windows installer gold proof artifact is still missing: /tmp/windows-installer-gold-proof-test.zip", payload["failures"])
        self.assertNotIn(
            "materializer failed: python3 scripts/auto_import_windows_installer_gold_proof.py --intake-request /tmp/intake.json --output /tmp/output.json --wait-seconds 0",
            payload["failures"],
        )

    def test_payload_rewrites_google_auto_import_waiting_materializer_failure_as_missing_artifact(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-google-auto-import-waiting-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "teable_important_work":
                    payload = {
                        "contract_name": "chummer.teable_important_work.v1",
                        "status": "pass",
                        "generated_at_utc": "2026-07-04T17:00:08Z",
                        "row_count": 1,
                        "rows": [{"title": "row"}],
                        "sync": {"state": "passed", "attempted": True, "synced_count": 1, "failed_count": 0},
                    }
                if key == "flagship_product_readiness":
                    payload = passing_flagship_product_readiness_payload(module)
                if key == "operator_release_dashboard":
                    payload = passing_operator_dashboard_payload(module)
                if key == "google_oauth_linking_proof":
                    payload = {
                        "status": "fail",
                        "generated_at_utc": "2026-07-04T17:00:05Z",
                        "failures": [
                            "operator_end_to_end_evidence: missing operator evidence receipt: /tmp/operator-evidence.json"
                        ],
                        "operator_request_artifacts": {
                            "required_operator_evidence_path": "/tmp/operator-evidence.json",
                            "request_receipt_path": "/tmp/operator-request.generated.json",
                            "operator_ask_text_path": "/tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt",
                            "operator_ask_send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/CURRENT_GOOGLE_OAUTH_LINKING_OPERATOR_ASK.txt --receipt-name google-oauth-linking-operator-ask.receipt.json",
                        },
                        "operator_end_to_end_evidence": {
                            "pass": False,
                            "exists": False,
                            "path": "/tmp/operator-evidence.json",
                            "failures": [
                                "missing operator evidence receipt: /tmp/operator-evidence.json"
                            ],
                        },
                    }
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")

            (published / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT.generated.json").write_text(
                json.dumps(
                    {
                        "status": "waiting_for_artifact",
                        "generated_at_utc": "2026-07-04T17:00:05Z",
                        "preferred_drop_path": "/tmp/google-oauth-linking-operator-evidence-test.zip",
                        "required_operator_evidence_path": "/tmp/operator-evidence.json",
                    }
                ),
                encoding="utf-8",
            )

            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"),
                mock.patch.object(module, "REQUIRED_RECEIPTS", required),
            ):
                payload = module.build_payload(
                    [
                        {
                            "command": "python3 scripts/auto_import_google_oauth_linking_operator_evidence.py --intake-request /tmp/google-request.json --output /tmp/google-output.json --wait-seconds 0",
                            "started_at_utc": "2026-07-04T17:00:00Z",
                            "completed_at_utc": "2026-07-04T17:00:06Z",
                            "returncode": 2,
                            "stdout": "google_oauth_linking_operator_evidence_auto_import:waiting",
                            "stderr": "",
                            "timed_out": False,
                            "timeout_seconds": 180,
                        }
                    ]
                )

        self.assertIn(
            "google oauth operator evidence bundle is still missing: /tmp/google-oauth-linking-operator-evidence-test.zip",
            payload["failures"],
        )
        self.assertNotIn(
            "materializer failed: python3 scripts/auto_import_google_oauth_linking_operator_evidence.py --intake-request /tmp/google-request.json --output /tmp/google-output.json --wait-seconds 0",
            payload["failures"],
        )

    def test_payload_keeps_auto_import_materializer_failure_when_waiting_receipt_not_refreshed(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-auto-import-stale-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "teable_important_work":
                    payload = {
                        "contract_name": "chummer.teable_important_work.v1",
                        "status": "pass",
                        "generated_at_utc": "2026-07-04T17:00:08Z",
                        "row_count": 1,
                        "rows": [{"title": "row"}],
                        "sync": {"state": "passed", "attempted": True, "synced_count": 1, "failed_count": 0},
                    }
                if key == "flagship_product_readiness":
                    payload = passing_flagship_product_readiness_payload(module)
                if key == "operator_release_dashboard":
                    payload = passing_operator_dashboard_payload(module)
                    payload["release"].update(
                        {
                            "channel": "preview",
                            "supportability_state": "preview_supported",
                            "rollout_state": "promoted_preview",
                        }
                    )
                    payload["checks"]["release_channel"].update(
                        {
                            "channel": "preview",
                            "supportability_state": "preview_supported",
                            "rollout_state": "promoted_preview",
                        }
                    )
                    payload["checks"]["release_channel"]["summary"].update(
                        {
                            "channel": "preview",
                            "supportability_state": "preview_supported",
                            "rollout_state": "promoted_preview",
                        }
                    )
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")

            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json").write_text(
                json.dumps(
                    {
                        "status": "waiting_for_artifact",
                        "generated_at_utc": "2026-07-04T16:59:50Z",
                        "preferred_drop_path": "/tmp/windows-installer-gold-proof-test.zip",
                    }
                ),
                encoding="utf-8",
            )

            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"),
                mock.patch.object(module, "REQUIRED_RECEIPTS", required),
            ):
                payload = module.build_payload(
                    [
                        {
                            "command": "python3 scripts/auto_import_windows_installer_gold_proof.py --intake-request /tmp/intake.json --output /tmp/output.json --wait-seconds 0",
                            "started_at_utc": "2026-07-04T17:00:00Z",
                            "completed_at_utc": "2026-07-04T17:00:06Z",
                            "returncode": 2,
                            "stdout": "windows_installer_visual_audit_auto_import:waiting",
                            "stderr": "",
                            "timed_out": False,
                            "timeout_seconds": 180,
                        }
                    ]
                )

        self.assertIn(
            "materializer failed: python3 scripts/auto_import_windows_installer_gold_proof.py --intake-request /tmp/intake.json --output /tmp/output.json --wait-seconds 0",
            payload["failures"],
        )

    def test_payload_keeps_google_auto_import_materializer_failure_when_waiting_receipt_not_refreshed(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-google-auto-import-stale-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "teable_important_work":
                    payload = {
                        "contract_name": "chummer.teable_important_work.v1",
                        "status": "pass",
                        "generated_at_utc": "2026-07-04T17:00:08Z",
                        "row_count": 1,
                        "rows": [{"title": "row"}],
                        "sync": {"state": "passed", "attempted": True, "synced_count": 1, "failed_count": 0},
                    }
                if key == "flagship_product_readiness":
                    payload = passing_flagship_product_readiness_payload(module)
                if key == "operator_release_dashboard":
                    payload = passing_operator_dashboard_payload(module)
                    payload["release"].update(
                        {
                            "channel": "preview",
                            "supportability_state": "preview_supported",
                            "rollout_state": "promoted_preview",
                        }
                    )
                    payload["checks"]["release_channel"].update(
                        {
                            "channel": "preview",
                            "supportability_state": "preview_supported",
                            "rollout_state": "promoted_preview",
                        }
                    )
                    payload["checks"]["release_channel"]["summary"].update(
                        {
                            "channel": "preview",
                            "supportability_state": "preview_supported",
                            "rollout_state": "promoted_preview",
                        }
                    )
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")

            (published / "GOOGLE_OAUTH_LINKING_OPERATOR_EVIDENCE_AUTO_IMPORT.generated.json").write_text(
                json.dumps(
                    {
                        "status": "waiting_for_artifact",
                        "generated_at_utc": "2026-07-04T16:59:50Z",
                        "preferred_drop_path": "/tmp/google-oauth-linking-operator-evidence-test.zip",
                    }
                ),
                encoding="utf-8",
            )

            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"),
                mock.patch.object(module, "REQUIRED_RECEIPTS", required),
            ):
                payload = module.build_payload(
                    [
                        {
                            "command": "python3 scripts/auto_import_google_oauth_linking_operator_evidence.py --intake-request /tmp/google-request.json --output /tmp/google-output.json --wait-seconds 0",
                            "started_at_utc": "2026-07-04T17:00:00Z",
                            "completed_at_utc": "2026-07-04T17:00:06Z",
                            "returncode": 2,
                            "stdout": "google_oauth_linking_operator_evidence_auto_import:waiting",
                            "stderr": "",
                            "timed_out": False,
                            "timeout_seconds": 180,
                        }
                    ]
                )

        self.assertIn(
            "materializer failed: python3 scripts/auto_import_google_oauth_linking_operator_evidence.py --intake-request /tmp/google-request.json --output /tmp/google-output.json --wait-seconds 0",
            payload["failures"],
        )

    def test_payload_surfaces_windows_visual_audit_digest_mismatch_path_without_materializer_results(self) -> None:
        module = load_module()
        module.IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING = False
        generated_at_utc = datetime.now(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
        with tempfile.TemporaryDirectory(prefix="gold-janitor-windows-digest-path-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "teable_important_work":
                    payload = {
                        "contract_name": "chummer.teable_important_work.v1",
                        "status": "pass",
                        "generated_at_utc": generated_at_utc,
                        "row_count": 1,
                        "rows": [{"title": "row"}],
                        "sync": {"state": "passed", "attempted": True, "synced_count": 1, "failed_count": 0},
                    }
                if key == "flagship_product_readiness":
                    payload = passing_flagship_product_readiness_payload(module)
                if key == "operator_release_dashboard":
                    payload = passing_operator_dashboard_payload(module)
                if key == "windows_installer_visual_audit":
                    payload = {
                        **passing_required_receipt_payload(module, key),
                        "status": "fail",
                        "generated_at_utc": generated_at_utc,
                        "contract_name": module.WINDOWS_INSTALLER_VISUAL_AUDIT_CONTRACT_NAME,
                        "artifact": {"sha256": "a" * 64, "actualSha256": "a" * 64},
                        "startupReceipt": {
                            "status": "pass",
                            "artifactDigest": f"sha256:{'a' * 64}",
                            "path": "/tmp/windows-startup.receipt.json",
                        },
                        "visualAuditSource": {
                            "exists": True,
                            "status": "pass",
                            "platform": "windows",
                            "hostClass": "native-windows-11",
                            "artifactSha256": "b" * 64,
                            "path": "/tmp/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                            "screenshotCount": 4,
                            "defaultDpiScreenshotCount": 2,
                            "scaledDpiScreenshotCount": 2,
                            "requiredSurfaces": ["install-progress", "completion"],
                        },
                        "failures": ["Windows installer visual audit source digest does not match promoted installer"],
                        "nextActions": ["Capture fresh Windows proof."],
                    }
                if key == "release_ready":
                    payload = {
                        **passing_required_receipt_payload(module, key),
                        "blocking_gate_artifacts": {
                            "windows_installer_visual_audit": {
                                "stage_release_build_handoff_path": "/tmp/RELEASE_BUILD_HANDOFF.generated.json",
                                "stage_release_build_handoff_status": "fail",
                                "stage_windows_visual_proof_handoff_path": "/tmp/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json",
                                "stage_windows_visual_proof_handoff_status": "ready_for_windows_host",
                                "stage_windows_visual_proof_handoff_summary": "Windows desktop exit gate failed: Windows installer visual proof version does not match release channel.",
                            },
                        },
                    }
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json").write_text(
                json.dumps(
                    {
                        "status": "external_artifact_required",
                        "promoted_installer_sha256": "a" * 64,
                        "preferred_drop_path": "/tmp/windows-proof.zip",
                        "preferred_extracted_visual_dir": "/tmp/windows-proof-dir",
                        "operator_telegram_draft": {
                            "current_message_path": "/tmp/CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt",
                            "current_metadata_path": "/tmp/CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.generated.json",
                            "send_command": "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt --receipt-name windows.receipt.json",
                            "receipt_name": "windows.receipt.json",
                            "message_preview": "Windows operator ask preview",
                            "preferred_extracted_visual_dir": "/tmp/windows-proof-dir",
                            "discover_visual_source_command": "python3 discover-visual",
                        },
                        "artifact_intake": {
                            "discover_command": "python3 discover",
                            "discover_visual_source_command": "python3 discover-visual",
                            "preferred_extracted_visual_dir": "/tmp/windows-proof-dir",
                            "watcher_launch_mode": "python_subprocess_start_new_session",
                            "watcher_state_path": str(Path(temp_dir) / "state" / "windows_installer_gold_proof_watcher.generated.json"),
                            "watcher_pid_file": str(Path(temp_dir) / "state" / "windows_installer_gold_proof_watcher.pid"),
                            "watcher_log_path": str(Path(temp_dir) / "state" / "windows_installer_gold_proof_auto_import_watch.log"),
                            "watcher_start_command": (
                                "python3 watcher-start "
                                f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'}"
                            ),
                            "watcher_status_command": (
                                "python3 watcher-status "
                                f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'}"
                            ),
                            "watcher_stop_command": (
                                "python3 watcher-stop "
                                f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'}"
                            ),
                            "import_command": (
                                "python3 scripts/import_windows_installer_gold_proof_artifact.py "
                                "bundle.zip "
                                f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
                                "--verify"
                            ),
                            "auto_import_watch_command": (
                                "python3 scripts/auto_import_windows_installer_gold_proof.py "
                                f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
                                "--wait-seconds 900"
                            ),
                            "post_import_verify_command": "python3 scripts/verify_windows_installer_visual_audit.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
                        },
                        "post_import_gates": [
                            "python3 scripts/verify_windows_installer_visual_audit.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT.generated.json",
                            "python3 scripts/materialize_windows_installer_visual_audit_intake_request.py --output .codex-studio/published/WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json",
                            "python3 scripts/verify_windows_installer_visual_audit_intake_request.py",
                            "python3 scripts/materialize_release_ready_receipt.py --force-global-verifier",
                            "python3 scripts/materialize_operator_release_dashboard.py",
                            "python3 scripts/final_gold_janitor.py --skip-materializers",
                            "python3 ../scripts/release/_release_gate_common.py",
                            "python3 ../scripts/materialize_codex_flagship_handoff.py --timestamp \"$(date --iso-8601=seconds)\"",
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json").write_text(
                json.dumps(
                    {
                        "status": "waiting_for_artifact",
                        "generated_at_utc": "2026-07-04T17:00:05Z",
                        "import_failure": {
                            "type": "BadZipFile",
                            "message": "File is not a zip file",
                            "code": None,
                        },
                        "summary": "Selected Windows installer gold-proof artifact failed import validation.",
                        "actionable_candidate_count": 0,
                        "matching_promoted_directory_candidate_count": 0,
                        "matching_promoted_zip_candidate_count": 0,
                        "stale_directory_candidate_count": 11,
                        "stage_like_stale_directory_candidate_count": 2,
                        "stage_visual_proof_receipt_count": 3,
                        "matching_promoted_stage_visual_proof_receipt_count": 0,
                        "stale_stage_visual_proof_receipt_count": 3,
                        "suppressed_stale_stage_visual_proof_receipt_count": 1,
                        "stage_startup_smoke_receipt_count": 2,
                        "matching_promoted_stage_startup_smoke_receipt_count": 1,
                        "stale_stage_startup_smoke_receipt_count": 1,
                        "suppressed_stale_stage_startup_smoke_receipt_count": 0,
                        "matching_promoted_stage_startup_smoke_receipts": [
                            {
                                "path": "/tmp/chummer6-ui-publishfix/Docker/Downloads/startup-smoke/startup-smoke-avalonia-win-x64.receipt.json",
                                "matches_promoted_installer": True,
                            },
                        ],
                        "stale_stage_startup_smoke_receipts": [
                            {
                                "path": "/tmp/stale/startup-smoke-avalonia-win-x64.receipt.json",
                                "matches_promoted_installer": False,
                            },
                        ],
                        "stale_stage_visual_proof_receipts": [
                            {
                                "path": "/tmp/chummer6-ui-publishfix/Docker/Downloads/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
                                "matches_promoted_installer": False,
                            },
                            {
                                "path": "/tmp/chummer6-ui-publishfix/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
                                "matches_promoted_installer": False,
                            },
                        ],
                        "stage_visual_proof_receipt_note": (
                            "Stage/nightly Windows proof receipts were found, but none match the promoted installer digest."
                        ),
                        "stage_startup_smoke_receipt_note": (
                            "Matching stage/nightly Windows startup-smoke receipts were found for the promoted installer digest. Startup is already proven for those staged bytes; only the visual-audit bundle still needs packaging or recapture. Additional digest-mismatched startup-smoke receipts were summarized separately."
                        ),
                        "stale_directory_digest_summary": [
                            {
                                "artifact_sha256": "c5691dcdb5176394e9529985bf85022577a593098b3eddeda50d9d91af914c5b",
                                "count": 2,
                                "stage_like_count": 2,
                                "sample_path": "/tmp/chummer-run-services-browserfix3",
                                "latest_source_updated_at_utc": "2026-06-21T17:44:15.3027652Z",
                            },
                            {
                                "artifact_sha256": "c41d17cea200060b0940f37f18eea6b0bd407c447cd9cd62a8e140e965bc6a51",
                                "count": 9,
                                "stage_like_count": 0,
                                "sample_path": "/tmp/windows-installer-proof-27866529115",
                                "latest_source_updated_at_utc": "2026-06-20T09:21:23Z",
                            },
                        ],
                        "directory_candidate_note": (
                            "Complete extracted proof directories were found, but none match the promoted installer digest. "
                            "Digest-mismatched directories were summarized separately."
                        ),
                    }
                ),
                encoding="utf-8",
            )
            watcher_state_path = Path(temp_dir) / "state" / "windows_installer_gold_proof_watcher.generated.json"
            watcher_state_path.parent.mkdir(parents=True, exist_ok=True)
            watcher_state_path.write_text(
                json.dumps(
                    {
                        "generated_at_utc": "2026-07-04T17:00:06Z",
                        "status": "running",
                        "pid": 1866861,
                        "process_alive": True,
                        "matching_process_pids": [1866861],
                        "matching_process_count": 1,
                        "duplicate_process_pids": [],
                        "duplicate_process_count": 0,
                        "note": "watcher discovered by pid file or process scan",
                    }
                ),
                encoding="utf-8",
            )
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"),
                mock.patch.object(module, "REQUIRED_RECEIPTS", required),
            ):
                payload = module.build_payload([])
                markdown = module.build_verdict_markdown(payload)

        self.assertIn("windows_installer_visual_audit failed", payload["failures"])
        self.assertIn(
            "windows installer visual audit source still targets "
            f"{'b' * 64} instead of promoted digest {'a' * 64}: /tmp/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
            payload["failures"],
        )
        self.assertEqual(
            "/tmp/windows-proof.zip",
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["preferred_drop_path"],
        )
        self.assertEqual(
            "/tmp/windows-proof-dir",
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["preferred_extracted_visual_dir"],
        )
        self.assertEqual(
            "python3 discover-visual",
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["discover_visual_source_command"],
        )
        self.assertEqual(
            str(published / "WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json"),
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["auto_import_receipt_path"],
        )
        self.assertEqual(
            str(Path(temp_dir) / "state" / "windows_installer_gold_proof_watcher.generated.json"),
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["watcher_state_receipt_path"],
        )
        self.assertEqual(
            "running",
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["watcher_status"],
        )
        self.assertEqual(
            "running",
            payload["required_gates"]["windows_installer_visual_audit"]["watcher_status"],
        )
        self.assertEqual(
            "python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt --receipt-name windows.receipt.json",
            payload["required_gates"]["windows_installer_visual_audit"]["operator_ask_send_command"],
        )
        self.assertEqual(
            1866861,
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["watcher_pid"],
        )
        self.assertEqual(
            1866861,
            payload["required_gates"]["windows_installer_visual_audit"]["watcher_pid"],
        )
        self.assertEqual(
            1,
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["watcher_matching_process_count"],
        )
        self.assertEqual(
            0,
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["watcher_duplicate_process_count"],
        )
        self.assertFalse(
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["watcher_attention_required"]
        )
        self.assertEqual(
            "waiting_for_artifact",
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["auto_import_receipt_status"],
        )
        self.assertEqual(
            "waiting_for_artifact",
            payload["required_gates"]["windows_installer_visual_audit"]["auto_import_receipt_status"],
        )
        self.assertEqual(
            "BadZipFile",
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["auto_import_import_failure_type"],
        )
        self.assertEqual(
            "BadZipFile",
            payload["required_gates"]["windows_installer_visual_audit"]["auto_import_import_failure_type"],
        )
        self.assertEqual(
            "File is not a zip file",
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["auto_import_import_failure_message"],
        )
        self.assertEqual(
            "Selected Windows installer gold-proof artifact failed import validation.",
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["auto_import_import_failure_summary"],
        )
        self.assertEqual(
            3,
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["auto_import_stage_visual_proof_receipt_count"],
        )
        self.assertEqual(
            3,
            payload["required_gates"]["windows_installer_visual_audit"]["auto_import_stage_visual_proof_receipt_count"],
        )
        self.assertEqual(
            0,
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["auto_import_matching_promoted_stage_visual_proof_receipt_count"],
        )
        self.assertEqual(
            3,
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["auto_import_stale_stage_visual_proof_receipt_count"],
        )
        self.assertEqual(
            2,
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["auto_import_stage_startup_smoke_receipt_count"],
        )
        self.assertEqual(
            1,
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["auto_import_matching_promoted_stage_startup_smoke_receipt_count"],
        )
        self.assertEqual(
            "Stage/nightly Windows proof receipts were found, but none match the promoted installer digest.",
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["auto_import_stage_visual_proof_receipt_note"],
        )
        self.assertIn(
            "Startup is already proven",
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["auto_import_stage_startup_smoke_receipt_note"],
        )
        self.assertEqual(
            "/tmp/RELEASE_BUILD_HANDOFF.generated.json",
            payload["required_gates"]["windows_installer_visual_audit"]["stage_release_build_handoff_path"],
        )
        self.assertEqual(
            "/tmp/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json",
            payload["required_gates"]["windows_installer_visual_audit"]["stage_windows_visual_proof_handoff_path"],
        )
        self.assertIn(
            "visual audit source: promoted_digest="
            f"{'a' * 64} source_digest={'b' * 64} "
            "source_path=/tmp/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json "
            "startup_path=/tmp/windows-startup.receipt.json",
            markdown,
        )
        self.assertIn(
            "windows visual proof request: request_receipt="
            f"{published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
            "ask_text=/tmp/CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt "
            "preferred_drop=/tmp/windows-proof.zip fallback_dir=/tmp/windows-proof-dir",
            markdown,
        )
        self.assertIn(
            "windows proof discovery: bundle=python3 discover visual_source=python3 discover-visual",
            markdown,
        )
        self.assertIn(
            "staged windows handoff: release_build=/tmp/RELEASE_BUILD_HANDOFF.generated.json "
            "release_status=fail visual_handoff=/tmp/WINDOWS_INSTALLER_VISUAL_PROOF_HANDOFF.generated.json "
            "visual_status=ready_for_windows_host",
            markdown,
        )
        self.assertIn(
            "staged windows handoff summary: Windows desktop exit gate failed: Windows installer visual proof version does not match release channel.",
            markdown,
        )
        self.assertIn(
            "windows operator ask send: python3 scripts/send_telegram_message_via_ea.py --text-file /tmp/CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt --receipt-name windows.receipt.json",
            markdown,
        )
        self.assertIn(
            "windows proof intake: "
            "import=python3 scripts/import_windows_installer_gold_proof_artifact.py "
            "bundle.zip "
            f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
            "--verify "
            "watch=python3 scripts/auto_import_windows_installer_gold_proof.py "
            f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} --wait-seconds 900",
            markdown,
        )
        self.assertIn(
            "windows watcher state: status=running pid=1866861 matches=1 duplicates=0 "
            f"attention=false state={Path(temp_dir) / 'state' / 'windows_installer_gold_proof_watcher.generated.json'}",
            markdown,
        )
        self.assertIn(
            "windows watcher control: "
            f"start=python3 watcher-start --intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
            f"status=python3 watcher-status --intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
            f"stop=python3 watcher-stop --intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'}",
            markdown,
        )
        self.assertIn(
            "windows auto-import state: "
            "status=waiting_for_artifact actionable=0 matching_dirs=0 matching_zips=0 stale_dirs=11 "
            f"artifact=missing receipt={published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json'}",
            markdown,
        )
        self.assertIn(
            "windows auto-import failure: "
            "type=BadZipFile message=File is not a zip file "
            "summary=Selected Windows installer gold-proof artifact failed import validation.",
            markdown,
        )
        self.assertIn(
            "windows stage-proof hints: "
            f"total=3 matching_promoted=0 stale=3 receipt={published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json'}",
            markdown,
        )
        self.assertIn(
            "windows stage-proof hint paths: "
            "/tmp/chummer6-ui-publishfix/Docker/Downloads/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json; "
            "/tmp/chummer6-ui-publishfix/.codex-studio/published/WINDOWS_INSTALLER_VISUAL_PROOF.generated.json",
            markdown,
        )
        self.assertIn(
            "windows stage-proof hint note: Stage/nightly Windows proof receipts were found, but none match the promoted installer digest.",
            markdown,
        )
        self.assertIn(
            "windows startup-smoke hints: total=2 matching_promoted=1 stale=1 "
            f"receipt={published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json'}",
            markdown,
        )
        self.assertIn(
            "windows startup-smoke hint note: Matching stage/nightly Windows startup-smoke receipts were found for the promoted installer digest. "
            "Startup is already proven for those staged bytes; only the visual-audit bundle still needs packaging or recapture. "
            "Additional digest-mismatched startup-smoke receipts were summarized separately.",
            markdown,
        )
        self.assertIn(
            "windows startup-smoke hint paths: "
            "/tmp/chummer6-ui-publishfix/Docker/Downloads/startup-smoke/startup-smoke-avalonia-win-x64.receipt.json; "
            "/tmp/stale/startup-smoke-avalonia-win-x64.receipt.json",
            markdown,
        )
        self.assertEqual(
            2,
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["auto_import_stage_like_stale_directory_candidate_count"],
        )
        self.assertEqual(
            2,
            len(payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["auto_import_stale_directory_digest_summary"]),
        )
        self.assertIn(
            "windows auto-import stale digests: "
            "c5691dcdb517 count=2 stage_like=2; c41d17cea200 count=9 stage_like=0 "
            "(stage_like_total=2)",
            markdown,
        )
        self.assertIn(
            "windows auto-import note: Complete extracted proof directories were found, but none match the promoted installer digest. Digest-mismatched directories were summarized separately.",
            markdown,
        )
        self.assertIn(
            "windows stage/nightly proof hints are available: "
            f"{published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_AUTO_IMPORT.generated.json'}; "
            "visual-proof receipts=3, startup-smoke receipts=2. "
            "Use them only to locate old Windows capture output for recapture or bundle packaging. "
            "Stage/nightly Windows proof receipts were found, but none match the promoted installer digest. "
            "Matching stage/nightly Windows startup-smoke receipts were found for the promoted installer digest. "
            "Startup is already proven for those staged bytes; only the visual-audit bundle still needs packaging or recapture. "
            "Additional digest-mismatched startup-smoke receipts were summarized separately.",
            payload["required_gates"]["windows_installer_visual_audit"]["advisoryActions"],
        )

    def test_payload_surfaces_windows_operator_missing_artifact_and_stale_ask(self) -> None:
        module = load_module()
        module.IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING = False
        with tempfile.TemporaryDirectory(prefix="gold-janitor-windows-operator-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            ask_path = Path(temp_dir) / "CURRENT_WINDOWS_INSTALLER_VISUAL_AUDIT_OPERATOR_ASK.txt"
            ask_path.write_text("Current Windows operator ask", encoding="utf-8")
            delivery_root = Path(temp_dir) / "telegram_text_delivery"
            delivery_root.mkdir(parents=True, exist_ok=True)
            (delivery_root / "windows.receipt.json").write_text(
                json.dumps(
                    {
                        "status": "sent",
                        "generated_at_utc": "2026-07-04T17:00:11Z",
                        "message_ids": ["1"],
                        "text_sha256": "f" * 64,
                        "text_preview": "Older Windows operator ask",
                    }
                ),
                encoding="utf-8",
            )
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "teable_important_work":
                    payload = {
                        "contract_name": "chummer.teable_important_work.v1",
                        "status": "pass",
                        "generated_at_utc": "2026-07-04T17:00:08Z",
                        "row_count": 1,
                        "rows": [{"title": "row"}],
                        "sync": {"state": "passed", "attempted": True, "synced_count": 1, "failed_count": 0},
                    }
                if key == "flagship_product_readiness":
                    payload = passing_flagship_product_readiness_payload(module)
                if key == "operator_release_dashboard":
                    payload = passing_operator_dashboard_payload(module)
                if key == "windows_installer_visual_audit":
                    payload = {
                        **passing_required_receipt_payload(module, key),
                        "status": "fail",
                        "generated_at_utc": "2026-07-04T17:00:09Z",
                        "contract_name": module.WINDOWS_INSTALLER_VISUAL_AUDIT_CONTRACT_NAME,
                        "artifact": {"sha256": "a" * 64, "actualSha256": "a" * 64},
                        "startupReceipt": {
                            "status": "pass",
                            "artifactDigest": f"sha256:{'a' * 64}",
                            "path": "/tmp/windows-startup.receipt.json",
                        },
                        "visualAuditSource": {
                            "exists": True,
                            "status": "pass",
                            "platform": "windows",
                            "hostClass": "native-windows-11",
                            "artifactSha256": "b" * 64,
                            "path": "/tmp/WINDOWS_INSTALLER_VISUAL_AUDIT.source.json",
                            "screenshotCount": 4,
                            "defaultDpiScreenshotCount": 2,
                            "scaledDpiScreenshotCount": 2,
                            "requiredSurfaces": ["install-progress", "completion"],
                        },
                        "failures": ["Windows installer visual audit source digest does not match promoted installer"],
                        "nextActions": ["Capture fresh Windows proof."],
                    }
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")
            missing_bundle = Path(temp_dir) / "windows-installer-gold-proof-test.zip"
            (published / "WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json").write_text(
                json.dumps(
                    {
                        "status": "external_artifact_required",
                        "promoted_installer_sha256": "a" * 64,
                        "preferred_drop_path": str(missing_bundle),
                        "preferred_zip_name": missing_bundle.name,
                        "required_zip_filename": missing_bundle.name,
                        "operator_telegram_draft": {
                            "current_message_path": str(ask_path),
                            "current_metadata_path": str(ask_path.with_suffix(".generated.json")),
                            "send_command": f"python3 scripts/send_telegram_message_via_ea.py --text-file {ask_path} --receipt-name windows.receipt.json",
                            "receipt_name": "windows.receipt.json",
                            "message_preview": "Windows operator ask preview",
                        },
                        "artifact_intake": {
                            "import_command": (
                                "python3 scripts/import_windows_installer_gold_proof_artifact.py "
                                "bundle.zip "
                                f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
                                "--verify"
                            ),
                            "auto_import_watch_command": (
                                "python3 scripts/auto_import_windows_installer_gold_proof.py "
                                f"--intake-request {published / 'WINDOWS_INSTALLER_VISUAL_AUDIT_INTAKE_REQUEST.generated.json'} "
                                "--wait-seconds 900 --poll-seconds 10 --refresh-intake-request"
                            ),
                        },
                    }
                ),
                encoding="utf-8",
            )
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"),
                mock.patch.object(module, "REQUIRED_RECEIPTS", required),
                mock.patch.object(module, "TELEGRAM_TEXT_DELIVERY_ROOT", delivery_root),
            ):
                payload = module.build_payload([])
                markdown = module.build_verdict_markdown(payload)

        self.assertIn(
            f"windows installer gold proof artifact is still missing: {missing_bundle}",
            payload["failures"],
        )
        self.assertNotIn(
            f"windows installer operator ask delivery is stale; resend current ask: python3 scripts/send_telegram_message_via_ea.py --text-file {ask_path} --receipt-name windows.receipt.json",
            payload["failures"],
        )
        if has_windows_native_root_blocker(module):
            self.assertIn(
                "windows_native_visual_proof",
                [item["id"] for item in payload["root_blockers"]],
            )
        self.assertTrue(
            payload["required_gates"]["windows_installer_visual_audit"]["operator_request_artifacts"]["operator_ask_delivery_needs_resend"]
        )
        self.assertIn(
            f"windows installer operator ask delivery is stale; resend current ask: python3 scripts/send_telegram_message_via_ea.py --text-file {ask_path} --receipt-name windows.receipt.json",
            payload["required_gates"]["windows_installer_visual_audit"]["advisoryActions"],
        )
        self.assertIn(
            f"windows operator ask resend: python3 scripts/send_telegram_message_via_ea.py --text-file {ask_path} --receipt-name windows.receipt.json",
            markdown,
        )

    def test_payload_uses_current_v20_root(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            module = load_module()
        self.assertEqual("full_product_reaudit_v20", module.ARTIFACT_ROOT_NAME)
        with tempfile.TemporaryDirectory(prefix="gold-janitor-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                write_required_receipt(
                    module,
                    published,
                    key,
                    path,
                    {"status": "pass", "generated_at_utc": module.now_iso()},
                )
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])

        self.assertEqual(payload["artifact_root"], "_completion/full_product_reaudit_v20")
        self.assertEqual(payload["scope"], "full_estate_v20")
        self.assertTrue(payload["required_gates"]["blazor_execution_horizon_bridge"]["public_entry"]["pass"])

    def test_payload_fails_on_stale_recrawl(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-stale-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            stale_time = "2020-01-01T00:00:00Z"
            for key, path in module.REQUIRED_RECEIPTS.items():
                generated_at = stale_time if key == "live_public_web_recrawl" else module.now_iso()
                write_required_receipt(
                    module,
                    published,
                    key,
                    path,
                    {"status": "pass", "generated_at_utc": generated_at},
                )
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])

        self.assertEqual(payload["status"], "fail")
        self.assertIn("live_public_web_recrawl stale", payload["failures"])

    def test_payload_fails_on_stale_google_oauth_linking_proof(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-stale-google-oauth-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            stale_time = "2020-01-01T00:00:00Z"
            for key, path in module.REQUIRED_RECEIPTS.items():
                generated_at = stale_time if key == "google_oauth_linking_proof" else module.now_iso()
                (published / path.name).write_text(
                    json.dumps(passing_required_receipt_payload(module, key, generated_at)),
                    encoding="utf-8",
                )
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])

        self.assertEqual(payload["status"], "fail")
        self.assertIn("google_oauth_linking_proof stale", payload["failures"])

    def test_payload_fails_when_public_route_receipt_status_disagrees_with_summary(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-public-route-status-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "flagship_product_readiness":
                    payload = passing_flagship_product_readiness_payload(module)
                if key == "teable_important_work":
                    payload = passing_teable_important_work_payload(module)
                if key == "public_route_proof":
                    payload = {
                        "status": "fail",
                        "generated_at_utc": module.now_iso(),
                        "summary": {
                            "route_count": 10,
                            "passed_count": 10,
                            "failed_count": 0,
                            "negative_path_failed_count": 0,
                        },
                    }
                write_required_receipt(module, published, key, path, payload)
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])

        self.assertEqual("fail", payload["status"])
        self.assertIn("public_route_proof failed", payload["failures"])
        self.assertFalse(payload["required_gates"]["public_route_proof"]["pass"])

    def test_payload_fails_when_blazor_bridge_lacks_live_build_play_public_entry(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-blazor-public-entry-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = {"status": "pass", "generated_at_utc": module.now_iso()}
                if key == "public_route_proof":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "summary": {
                            "route_count": 10,
                            "passed_count": 10,
                            "failed_count": 0,
                            "negative_path_failed_count": 0,
                        },
                    }
                if key == "blazor_execution_horizon_bridge":
                    payload = valid_blazor_bridge_payload(module)
                    payload["proofs"]["hub_mobile_pwa_public_projection"]["public_entry"]["build_final_route"] = "/build"
                write_required_receipt(module, published, key, path, payload)
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])

        gate = payload["required_gates"]["blazor_execution_horizon_bridge"]
        self.assertEqual("fail", payload["status"])
        self.assertIn(
            "blazor_execution_horizon_bridge missing live Build/Play public-entry proof",
            payload["failures"],
        )
        self.assertFalse(gate["pass"])
        self.assertFalse(gate["public_entry"]["pass"])
        self.assertEqual("/build", gate["public_entry"]["build_final_route"])

    def test_payload_fails_required_receipts_that_report_structured_failures(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-structured-failures-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "design_quality_gate":
                    payload = {
                        "status": "pass",
                        "verdict": "DESIGN_READY",
                        "generated_at_utc": module.now_iso(),
                        "failures": ["homepage still exposes internal review wording"],
                    }
                if key == "public_route_proof":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "summary": {
                            "route_count": 10,
                            "failed_count": 0,
                            "negative_path_failed_count": 0,
                        },
                    }
                write_required_receipt(module, published, key, path, payload)
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])

        gate = payload["required_gates"]["design_quality_gate"]
        self.assertEqual("fail", payload["status"])
        self.assertIn("design_quality_gate has structured failures", payload["failures"])
        self.assertEqual(1, gate["structured_failures_count"])
        self.assertFalse(gate["pass"])

    def test_payload_fails_when_operator_dashboard_is_only_nightly_handoff_ready(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-nightly-dashboard-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = {"status": "pass", "generated_at_utc": module.now_iso()}
                if key == "operator_release_dashboard":
                    payload = {
                        "status": "pass",
                        "verdict": "NIGHTLY_HANDOFF_READY",
                        "generated_at_utc": module.now_iso(),
                        "release_readiness": {
                            "full_release_ready": False,
                            "nightly_handoff_ready": True,
                            "full_release_blockers": ["windows_installer_visual_audit"],
                            "full_release_blocker_details": [
                                "Windows installer visual audit source digest does not match promoted installer",
                            ],
                        },
                    }
                if key == "public_route_proof":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "summary": {
                            "route_count": 10,
                            "passed_count": 10,
                            "failed_count": 0,
                            "negative_path_failed_count": 0,
                        },
                    }
                write_required_receipt(module, published, key, path, payload)
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])

        gate = payload["required_gates"]["operator_release_dashboard"]
        self.assertEqual("fail", payload["status"])
        self.assertEqual("fail", gate["status"])
        self.assertFalse(gate["pass"])
        self.assertEqual("NIGHTLY_HANDOFF_READY", gate["verdict"])
        self.assertFalse(gate["release_readiness"]["full_release_ready"])
        self.assertIn("operator_release_dashboard is not full release ready", payload["failures"])

    def test_verdict_markdown_surfaces_operator_release_blocker_details(self) -> None:
        module = load_module()
        payload = {
            "verdict": "NOT_GOLD",
            "generated_at_utc": module.now_iso(),
            "scope": "full_estate_v20",
            "required_gates": {
                "operator_release_dashboard": {
                    "pass": False,
                    "status": "fail",
                    "path": "/tmp/operator-dashboard.json",
                    "release_readiness": {
                        "full_release_ready": False,
                        "nightly_handoff_ready": True,
                        "full_release_blockers": ["release_ready", "windows_installer_visual_audit"],
                        "full_release_blocker_details": [
                            "release channel channel is preview, not a flagship stable lane",
                            "Windows installer visual audit source digest does not match promoted installer",
                        ],
                    },
                    "release": {
                        "version": "run-20260705-040324",
                        "channel": "preview",
                    },
                },
            },
            "caveats": [],
            "failures": ["operator_release_dashboard is not full release ready"],
        }

        markdown = module.build_verdict_markdown(payload)

        self.assertIn("  - full release blocker details:", markdown)
        self.assertIn("    - release channel channel is preview, not a flagship stable lane", markdown)
        self.assertIn(
            "    - Windows installer visual audit source digest does not match promoted installer",
            markdown,
        )

    def test_main_writes_identical_published_and_durable_v20_janitor_artifacts(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-failed-gates-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "teable_important_work":
                    payload = passing_teable_important_work_payload(module)
                if key == "flagship_product_readiness":
                    payload = passing_flagship_product_readiness_payload(module)
                if key == "public_route_proof":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "summary": {
                            "route_count": 10,
                            "failed_count": 0,
                            "negative_path_failed_count": 0,
                        },
                    }
                if key == "public_copy_leak_gate":
                    payload["failed_gates"] = ["verify_public_copy"]
                if key == "operator_release_dashboard":
                    payload = passing_operator_dashboard_payload(module)
                    payload["release"].update(
                        {
                            "channel": "preview",
                            "supportability_state": "preview_supported",
                            "rollout_state": "promoted_preview",
                        }
                    )
                    payload["checks"]["release_channel"].update(
                        {
                            "channel": "preview",
                            "supportability_state": "preview_supported",
                            "rollout_state": "promoted_preview",
                        }
                    )
                    payload["checks"]["release_channel"]["summary"].update(
                        {
                            "channel": "preview",
                            "supportability_state": "preview_supported",
                            "rollout_state": "promoted_preview",
                        }
                    )
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])
                markdown = module.build_verdict_markdown(payload)

        gate = payload["required_gates"]["public_copy_leak_gate"]
        self.assertEqual("fail", payload["status"])
        self.assertIn("public_copy_leak_gate has failed gates", payload["failures"])
        self.assertEqual(["verify_public_copy"], gate["failed_gates"])
        self.assertEqual(1, gate["failed_gates_count"])
        self.assertFalse(gate["pass"])
        self.assertEqual("fail", gate["status"])
        self.assertIn("- FAIL `public_copy_leak_gate`: `fail`", markdown)
        self.assertIn("failed gates: verify_public_copy", markdown)

    def test_payload_rejects_required_receipts_with_unexpected_pass_verdicts(self) -> None:
        module = load_module()
        for key, expected_verdicts in sorted(module.PASS_VERDICT_EXPECTATIONS.items()):
            with self.subTest(key=key):
                with tempfile.TemporaryDirectory(prefix=f"gold-janitor-{key}-verdict-") as temp_dir:
                    published = Path(temp_dir) / "published"
                    published.mkdir(parents=True, exist_ok=True)
                    for receipt_key, path in module.REQUIRED_RECEIPTS.items():
                        payload = passing_required_receipt_payload(module, receipt_key)
                        if receipt_key == "public_edge_postdeploy_gate":
                            payload = passing_public_edge_postdeploy_payload(module)
                        if receipt_key == key:
                            payload["verdict"] = "UNEXPECTED_PASS_VERDICT"
                        if receipt_key == "operator_release_dashboard":
                            payload = passing_operator_dashboard_payload(module)
                            payload["release"].update(
                                {
                                    "channel": "preview",
                                    "supportability_state": "preview_supported",
                                    "rollout_state": "promoted_preview",
                                }
                            )
                            payload["checks"]["release_channel"].update(
                                {
                                    "channel": "preview",
                                    "supportability_state": "preview_supported",
                                    "rollout_state": "promoted_preview",
                                }
                            )
                            payload["checks"]["release_channel"]["summary"].update(
                                {
                                    "channel": "preview",
                                    "supportability_state": "preview_supported",
                                    "rollout_state": "promoted_preview",
                                }
                            )
                        (published / path.name).write_text(json.dumps(payload), encoding="utf-8")
                    required = {receipt_key: published / path.name for receipt_key, path in module.REQUIRED_RECEIPTS.items()}
                    with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                        payload = module.build_payload([])

                gate = payload["required_gates"][key]
                self.assertEqual("fail", payload["status"])
                self.assertIn(f"{key} has unexpected verdict", payload["failures"])
                self.assertFalse(gate["pass"])
                self.assertEqual("fail", gate["status"])
                self.assertIn(
                    f"{key} has unexpected verdict (expected one of: {', '.join(sorted(expected_verdicts))})",
                    gate["semanticFailures"],
                )

    def test_payload_surfaces_release_ready_failed_gates(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-release-ready-gates-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "teable_important_work":
                    payload = passing_teable_important_work_payload(module)
                if key == "public_route_proof":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "summary": {
                            "route_count": 10,
                            "failed_count": 0,
                            "negative_path_failed_count": 0,
                        },
                    }
                if key == "release_ready":
                    payload = {
                        "status": "fail",
                        "verdict": "NOT_RELEASE_READY",
                        "generated_at_utc": module.now_iso(),
                        "failures": [
                            "FAIL verify_public_release_snapshot_truth",
                            "verify_public_release_snapshot_truth",
                        ],
                        "failed_gates": ["verify_public_release_snapshot_truth"],
                        "blocking_gate_artifacts": {
                            "public_release_snapshot_readonly_audit": {
                                "path": str(Path(temp_dir) / ".codex-studio" / "published" / "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.generated.json"),
                                "exists": True,
                                "load_status": "loaded",
                                "status": "pass",
                                "verdict": "SNAPSHOT_CONSISTENT_NOT_LAUNCH_READY",
                                "summary": "Snapshot is internally consistent with current launch truth, but the release is not launch-ready.",
                                "expected_top_level_blocker_ids": [
                                    "release_posture:non_flagship_channel",
                                    "release_truth:windows_installer_visual_audit",
                                ],
                                "expected_release_truth_blockers": ["windows_installer_visual_audit"],
                            },
                        },
                    }
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")
            (Path(temp_dir) / ".codex-studio" / "published").mkdir(parents=True, exist_ok=True)
            (Path(temp_dir) / ".codex-studio" / "published" / "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.generated.json").write_text(
                json.dumps(
                    {
                        "status": "fail",
                        "verdict": "FALLBACK_SHOULD_NOT_WIN",
                        "summary": "This fallback receipt should not override the embedded release_ready audit.",
                        "expected_top_level_blocker_ids": ["fallback:stale"],
                        "expected_release_truth_blockers": ["fallback"],
                    }
                ),
                encoding="utf-8",
            )
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), \
                mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), \
                mock.patch.object(module, "REQUIRED_RECEIPTS", required), \
                mock.patch.object(
                    module,
                    "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT_PATH",
                    Path(temp_dir) / ".codex-studio" / "published" / "PUBLIC_RELEASE_SNAPSHOT_READONLY_AUDIT.generated.json",
                ):
                payload = module.build_payload([])

        gate = payload["required_gates"]["release_ready"]
        markdown = module.build_verdict_markdown(payload)
        self.assertEqual("fail", payload["status"])
        self.assertIn("release_ready failed", payload["failures"])
        self.assertEqual(["verify_public_release_snapshot_truth"], gate["failed_gates"])
        snapshot_audit = gate["public_release_snapshot_readonly_audit"]
        self.assertEqual("fail", snapshot_audit["status"])
        self.assertEqual("pass", snapshot_audit["raw_status"])
        self.assertFalse(snapshot_audit["pass"])
        self.assertEqual("SNAPSHOT_CONSISTENT_NOT_LAUNCH_READY", snapshot_audit["verdict"])
        self.assertEqual(
            ["release_posture:non_flagship_channel", "release_truth:windows_installer_visual_audit"],
            snapshot_audit["expected_top_level_blocker_ids"],
        )
        self.assertEqual("loaded", snapshot_audit["load_status"])
        self.assertIn("release failed gates: verify_public_release_snapshot_truth", markdown)
        self.assertIn("snapshot truth audit: status=fail verdict=SNAPSHOT_CONSISTENT_NOT_LAUNCH_READY", markdown)
        self.assertIn("snapshot truth audit raw status: pass", markdown)

    def test_payload_rejects_release_ready_unexpected_contract(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-release-ready-contract-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "teable_important_work":
                    payload = passing_teable_important_work_payload(module)
                if key == "flagship_product_readiness":
                    payload = passing_flagship_product_readiness_payload(module)
                if key == "public_route_proof":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "summary": {
                            "route_count": 10,
                            "passed_count": 10,
                            "failed_count": 0,
                            "negative_path_failed_count": 0,
                        },
                    }
                write_required_receipt(module, published, key, path, payload)
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            stdout = io.StringIO()
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", artifact_root), mock.patch.object(module, "LEGACY_GOLD_CLOSURE_ROOT", legacy_root), mock.patch.object(module, "REQUIRED_RECEIPTS", required), mock.patch("sys.argv", ["final_gold_janitor.py", "--skip-materializers"]):
                with redirect_stdout(stdout):
                    self.assertEqual(0, module.main())

            published_payload = json.loads(
                (published / "FINAL_GOLD_JANITOR.generated.json").read_text(encoding="utf-8")
            )
            durable_payload = json.loads(
                (artifact_root / "FINAL_GOLD_JANITOR.generated.json").read_text(encoding="utf-8")
            )
            legacy_payload = json.loads(
                (legacy_root / "FINAL_GOLD_JANITOR.generated.json").read_text(encoding="utf-8")
            )

        self.assertEqual("final_gold_janitor:ok\n", stdout.getvalue())
        self.assertEqual(published_payload, durable_payload)
        self.assertEqual("_completion/full_product_reaudit_v20", durable_payload["artifact_root"])
        self.assertEqual("GOLD_READY", durable_payload["verdict"])
        self.assertEqual("_completion/full_product_reaudit_v20", legacy_payload["mirrors"]["authoritative_artifact_root"])
        markdown = module.build_verdict_markdown(durable_payload)
        self.assertIn("role PWA manifests: count=2", markdown)
        self.assertIn("/manifest.player.webmanifest", markdown)
        self.assertIn("/mobile/player?role=Player", markdown)
        self.assertIn("/manifest.gm.webmanifest", markdown)
        self.assertIn("/mobile/gm?role=GameMaster", markdown)

    def test_main_writes_optional_fleet_completion_mirror_when_default_roots_are_active(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-fleet-mirror-") as temp_dir:
            published = Path(temp_dir) / "published"
            artifact_root = Path(temp_dir) / "full_product_reaudit_v20"
            legacy_root = Path(temp_dir) / "gold_readiness_closure"
            fleet_completion_root = Path(temp_dir) / "fleet_completion"
            fleet_artifact_root = fleet_completion_root / module.ARTIFACT_ROOT_NAME
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "public_route_proof":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "summary": {
                            "route_count": 10,
                            "passed_count": 10,
                            "failed_count": 0,
                            "negative_path_failed_count": 0,
                        },
                    }
                if key == "teable_important_work":
                    payload = passing_teable_important_work_payload(module)
                if key == "flagship_product_readiness":
                    payload = passing_flagship_product_readiness_payload(module)
                if key == "operator_release_dashboard":
                    payload = passing_operator_dashboard_payload(module)
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            stdout = io.StringIO()
            with mock.patch.object(module, "DEFAULT_PUBLISHED_ROOT", published), mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", artifact_root), mock.patch.object(module, "LEGACY_GOLD_CLOSURE_ROOT", legacy_root), mock.patch.object(module, "FLEET_COMPLETION_ROOT", fleet_completion_root), mock.patch.object(module, "FLEET_ARTIFACT_ROOT", fleet_artifact_root), mock.patch.object(module, "REQUIRED_RECEIPTS", required), mock.patch("sys.argv", ["final_gold_janitor.py", "--skip-materializers"]):
                with redirect_stdout(stdout):
                    self.assertEqual(0, module.main())

            fleet_payload = json.loads(
                (fleet_artifact_root / "FINAL_GOLD_JANITOR.generated.json").read_text(encoding="utf-8")
            )
            legacy_payload = json.loads(
                (legacy_root / "FINAL_GOLD_JANITOR.generated.json").read_text(encoding="utf-8")
            )
            fleet_verdict_markdown = (fleet_artifact_root / "FINAL_GOLD_VERDICT.md").read_text(encoding="utf-8")

        self.assertEqual("final_gold_janitor:ok\n", stdout.getvalue())
        self.assertEqual("GOLD_READY", fleet_payload["verdict"])
        self.assertEqual(str(fleet_artifact_root), legacy_payload["mirrors"]["fleet_artifact_root"])
        self.assertEqual("# GOLD_READY", fleet_verdict_markdown.splitlines()[0])

    def test_skip_materializers_does_not_carry_forward_stale_prior_materializer_logs(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-skip-materializers-") as temp_dir:
            published = Path(temp_dir) / "published"
            artifact_root = Path(temp_dir) / "v20"
            legacy_root = Path(temp_dir) / "legacy"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "public_route_proof":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "summary": {
                            "route_count": 10,
                            "passed_count": 10,
                            "failed_count": 0,
                            "negative_path_failed_count": 0,
                        },
                    }
                if key == "teable_important_work":
                    payload = passing_teable_important_work_payload(module)
                if key == "flagship_product_readiness":
                    payload = passing_flagship_product_readiness_payload(module)
                if key == "operator_release_dashboard":
                    payload = passing_operator_dashboard_payload(module)
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")

            (published / "FINAL_GOLD_JANITOR.generated.json").write_text(
                json.dumps(
                    {
                        "status": "fail",
                        "verdict": "NOT_GOLD",
                        "materializers": [
                            {
                                "command": "python3 scripts/verify_flagship_product_readiness_gate.py",
                                "returncode": 1,
                                "stderr": "stale prior failure",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            stdout = io.StringIO()
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", artifact_root), mock.patch.object(module, "LEGACY_GOLD_CLOSURE_ROOT", legacy_root), mock.patch.object(module, "REQUIRED_RECEIPTS", required), mock.patch("sys.argv", ["final_gold_janitor.py", "--skip-materializers"]):
                with redirect_stdout(stdout):
                    self.assertEqual(0, module.main())

            payload = json.loads((published / "FINAL_GOLD_JANITOR.generated.json").read_text(encoding="utf-8"))

        self.assertEqual("final_gold_janitor:ok\n", stdout.getvalue())
        self.assertEqual([], payload["materializers"])
        self.assertTrue(payload["materializers_skipped"])

    def test_main_skip_materializers_disables_windows_runtime_refresh(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-main-skip-runtime-refresh-") as temp_dir:
            published = Path(temp_dir) / "published"
            artifact_root = Path(temp_dir) / "v20"
            legacy_root = Path(temp_dir) / "legacy"
            published.mkdir(parents=True, exist_ok=True)
            payload = {
                "status": "pass",
                "verdict": "GOLD_READY",
                "failures": [],
                "required_gates": {},
                "materializers": [],
                "artifact_root": str(artifact_root),
            }
            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "ARTIFACT_ROOT", artifact_root),
                mock.patch.object(module, "LEGACY_GOLD_CLOSURE_ROOT", legacy_root),
                mock.patch.object(module, "build_payload", return_value=payload) as build_payload,
                mock.patch.object(module, "build_verdict_markdown", return_value="# GOLD_READY\n"),
                mock.patch("sys.argv", ["final_gold_janitor.py", "--skip-materializers"]),
            ):
                self.assertEqual(0, module.main())

        build_payload.assert_called_once_with(
            [],
            refresh_windows_runtime_receipts=False,
            refresh_flagship_product_readiness_gate_receipt=False,
        )

    def test_main_explicit_skip_windows_runtime_refresh_preserves_materializer_run(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-main-explicit-runtime-refresh-skip-") as temp_dir:
            published = Path(temp_dir) / "published"
            artifact_root = Path(temp_dir) / "v20"
            legacy_root = Path(temp_dir) / "legacy"
            published.mkdir(parents=True, exist_ok=True)
            payload = {
                "status": "pass",
                "verdict": "GOLD_READY",
                "failures": [],
                "required_gates": {},
                "materializers": [],
                "artifact_root": str(artifact_root),
            }
            command_results = [{"command": "python3 scripts/verify_flagship_product_readiness_gate.py", "returncode": 0}]
            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "ARTIFACT_ROOT", artifact_root),
                mock.patch.object(module, "LEGACY_GOLD_CLOSURE_ROOT", legacy_root),
                mock.patch.object(module, "run_materializers", return_value=command_results),
                mock.patch.object(module, "build_payload", return_value=payload) as build_payload,
                mock.patch.object(module, "build_verdict_markdown", return_value="# GOLD_READY\n"),
                mock.patch("sys.argv", ["final_gold_janitor.py", "--skip-windows-runtime-refresh"]),
            ):
                self.assertEqual(0, module.main())

        build_payload.assert_called_once_with(
            command_results,
            refresh_windows_runtime_receipts=False,
            refresh_flagship_product_readiness_gate_receipt=True,
        )

    def test_skip_materializers_does_not_preserve_stale_failed_materializer_rows(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-skip-materializers-") as temp_dir:
            published = Path(temp_dir) / "published"
            artifact_root = Path(temp_dir) / "full_product_reaudit_v20"
            legacy_root = Path(temp_dir) / "gold_readiness_closure"
            published.mkdir(parents=True, exist_ok=True)
            (published / "FINAL_GOLD_JANITOR.generated.json").write_text(
                json.dumps(
                    {
                        "status": "fail",
                        "materializers": [
                            {
                                "command": "python3 old_broken_materializer.py",
                                "returncode": 1,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = {"status": "pass", "generated_at_utc": module.now_iso()}
                if key == "public_route_proof":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "summary": {
                            "route_count": 10,
                            "passed_count": 10,
                            "failed_count": 0,
                            "negative_path_failed_count": 0,
                        },
                    }
                write_required_receipt(module, published, key, path, payload)
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with (
                mock.patch.object(module, "PUBLISHED_ROOT", published),
                mock.patch.object(module, "ARTIFACT_ROOT", artifact_root),
                mock.patch.object(module, "LEGACY_GOLD_CLOSURE_ROOT", legacy_root),
                mock.patch.object(module, "REQUIRED_RECEIPTS", required),
                mock.patch("sys.argv", ["final_gold_janitor.py", "--skip-materializers"]),
            ):
                self.assertEqual(0, module.main())

            payload = json.loads((published / "FINAL_GOLD_JANITOR.generated.json").read_text(encoding="utf-8"))

        self.assertEqual([], payload["materializers"])

    def test_payload_fails_on_stale_rule_authority_receipt(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-stale-rules-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            stale_time = "2020-01-01T00:00:00Z"
            for key, path in module.REQUIRED_RECEIPTS.items():
                generated_at = stale_time if key == "rule_authority_minimum_coverage" else module.now_iso()
                write_required_receipt(
                    module,
                    published,
                    key,
                    path,
                    {"status": "pass", "generated_at_utc": generated_at},
                )
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])

        self.assertEqual(payload["status"], "fail")
        self.assertIn("rule_authority_minimum_coverage stale", payload["failures"])

    def test_payload_accepts_generated_at_utc_camel_case_for_public_edge_gate(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-public-edge-fresh-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = {"status": "pass", "generated_at_utc": module.now_iso()}
                if key == "public_edge_postdeploy_gate":
                    payload = {
                        "status": "pass",
                        "generatedAtUtc": module.now_iso(),
                        "releaseManifestVersion": "run-20260701-124648",
                        "visibleVersion": "Version run-20260701-124648",
                        "browserPlaywrightStatus": "pass",
                        "flagshipHorizonsBrowserProofCoverage": "full",
                        "mobileLedgerPayloadStatus": "opt_in_required",
                    }
                if key == "public_route_proof":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "summary": {
                            "route_count": 10,
                            "failed_count": 0,
                            "negative_path_failed_count": 0,
                        },
                    }
                write_required_receipt(module, published, key, path, payload)
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])

        gate = payload["required_gates"]["public_edge_postdeploy_gate"]
        self.assertEqual("pass", payload["status"])
        self.assertEqual("Version run-20260701-124648", gate["visibleVersion"])
        self.assertEqual("full", gate["flagshipHorizonsBrowserProofCoverage"])

    def test_payload_fails_when_public_edge_postdeploy_gate_is_missing(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-public-edge-missing-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                if key == "public_edge_postdeploy_gate":
                    continue
                payload = {"status": "pass", "generated_at_utc": module.now_iso()}
                if key == "public_route_proof":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "summary": {
                            "route_count": 10,
                            "failed_count": 0,
                            "negative_path_failed_count": 0,
                        },
                    }
                write_required_receipt(module, published, key, path, payload)
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])

        self.assertEqual("fail", payload["status"])
        self.assertIn("public_edge_postdeploy_gate missing", payload["failures"])

    def test_payload_surfaces_rule_authority_blocker_details(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-rules-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "rule_authority_minimum_coverage":
                    payload = {
                        "status": "fail",
                        "generated_at_utc": module.now_iso(),
                        "rulesets": {
                            "sr4": {
                                "status": "fail",
                                "blocker_receipts": {"row_level_mapping": "/tmp/sr4-row.json", "errata_posture": "/tmp/sr4-errata.json"},
                                "row_level_mapping_status": "pending_human_review",
                                "errata_posture_status": "pending_reviewed_application",
                                "human_review_status": {"pending_review": True, "review_ready": False, "source_baseline_required": False},
                            }
                        },
                        "failures": ["sr4 final_verdict is not ready"],
                    }
                write_required_receipt(module, published, key, path, payload)
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])

        rules_gate = payload["required_gates"]["rule_authority_minimum_coverage"]
        self.assertEqual("fail", rules_gate["status"])
        self.assertIn("sr4", rules_gate["rulesets"])
        self.assertEqual("/tmp/sr4-row.json", rules_gate["rulesets"]["sr4"]["blocker_receipts"]["row_level_mapping"])
        self.assertTrue(rules_gate["rulesets"]["sr4"]["human_review_status"]["pending_review"])
        self.assertFalse(rules_gate["rulesets"]["sr4"]["human_review_status"]["source_baseline_required"])

    def test_payload_surfaces_windows_installer_visual_audit_failures(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-windows-visual-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "windows_installer_visual_audit":
                    payload = {
                        "status": "fail",
                        "generated_at_utc": module.now_iso(),
                        "failures": [
                            "Windows startup receipt is an incompatible-host skip, not native proof",
                            "Windows installer visual audit source is missing",
                        ],
                        "nextActions": [
                            "Use PowerShell: scripts/capture_windows_installer_visual_audit.ps1 -Surface install-progress",
                            "Replace the incompatible-host Windows startup-smoke receipt with a native Windows pass",
                        ],
                        "startupReceipt": {
                            "status": "skipped",
                            "verificationDisposition": "incompatible_host",
                        },
                        "visualAuditSource": {
                            "exists": False,
                        },
                    }
                write_required_receipt(module, published, key, path, payload)
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])
                markdown = module.build_verdict_markdown(payload)

        gate = payload["required_gates"]["windows_installer_visual_audit"]
        self.assertEqual("fail", payload["status"])
        self.assertEqual("fail", gate["status"])
        self.assertIn("windows_installer_visual_audit failed", payload["failures"])
        self.assertIn("Windows startup receipt is an incompatible-host skip, not native proof", gate["failures"])
        if has_windows_native_root_blocker(module):
            self.assertIn(
                "windows_native_visual_proof",
                [item["id"] for item in payload["root_blockers"]],
            )
            self.assertIn(
                "`windows_native_visual_proof`: Native Windows installer visual proof is still missing or mismatched for the promoted bytes.",
                markdown,
            )
        self.assertTrue(any("capture_windows_installer_visual_audit.ps1" in item for item in gate["nextActions"]))

    def test_windows_visual_root_blocker_summary_acknowledges_confirmed_startup(self) -> None:
        module = load_module()
        summary = module.windows_visual_root_blocker_summary(
            {
                "artifact": {"sha256": "a" * 64},
                "startupReceipt": {
                    "status": "pass",
                    "artifactDigest": "sha256:" + ("a" * 64),
                },
                "visualAuditSource": {
                    "artifactSha256": "b" * 64,
                },
            }
        )

        self.assertEqual(
            "Native Windows installer execution is confirmed, but the matching visual proof is still missing or mismatched for the promoted bytes.",
            summary,
        )

    def test_payload_rejects_windows_installer_visual_audit_semantic_contradictions(self) -> None:
        module = load_module()
        module.IGNORE_WINDOWS_VISUAL_AUDIT_BLOCKING = False
        with tempfile.TemporaryDirectory(prefix="gold-janitor-windows-visual-semantics-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "teable_important_work":
                    payload = passing_teable_important_work_payload(module)
                if key == "flagship_product_readiness":
                    payload = passing_flagship_product_readiness_payload(module)
                if key == "public_route_proof":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "summary": {
                            "route_count": 10,
                            "passed_count": 10,
                            "failed_count": 0,
                            "negative_path_failed_count": 0,
                        },
                    }
                if key == "operator_release_dashboard":
                    payload = passing_operator_dashboard_payload(module)
                if key == "windows_installer_visual_audit":
                    payload.update(
                        {
                            "artifact": {
                                "sha256": "a" * 64,
                                "actualSha256": "b" * 64,
                            },
                            "startupReceipt": {
                                "status": "pass",
                                "verificationDisposition": "incompatible_host",
                                "artifactDigest": "sha256:" + ("c" * 64),
                            },
                            "visualAuditSource": {
                                "exists": True,
                                "status": "pass",
                                "platform": "linux",
                                "hostClass": "container",
                                "artifactSha256": "d" * 64,
                                "screenshotCount": 1,
                                "defaultDpiScreenshotCount": 1,
                                "scaledDpiScreenshotCount": 0,
                                "requiredSurfaces": ["completion"],
                            },
                        }
                    )
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])
                markdown = module.build_verdict_markdown(payload)

        gate = payload["required_gates"]["windows_installer_visual_audit"]
        self.assertEqual("fail", payload["status"])
        self.assertIn("windows_installer_visual_audit semantic proof failed", payload["failures"])
        self.assertFalse(gate["pass"])
        self.assertEqual("fail", gate["status"])
        self.assertEqual("pass", gate["raw_status"])
        if has_windows_native_root_blocker(module):
            self.assertIn(
                "windows_native_visual_proof",
                [item["id"] for item in payload["root_blockers"]],
            )
        self.assertIn("windows_installer_visual_audit artifact sha256 does not match actual artifact bytes", gate["semanticFailures"])
        self.assertIn("windows_installer_visual_audit startup receipt is incompatible-host", gate["semanticFailures"])
        self.assertIn("windows_installer_visual_audit visual source platform is not windows", gate["semanticFailures"])
        self.assertIn("windows_installer_visual_audit scaled-DPI screenshot count is below required count", gate["semanticFailures"])
        if has_windows_native_root_blocker(module):
            self.assertIn(
                "`windows_native_visual_proof`: Native Windows installer visual proof is still missing or mismatched for the promoted bytes.",
                markdown,
            )
        self.assertIn("raw status: `pass`", markdown)
        self.assertIn("failures: windows_installer_visual_audit artifact sha256 does not match actual artifact bytes", markdown)

    def test_main_prints_failed_gate_details_before_exiting(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-main-") as temp_dir:
            published = Path(temp_dir) / "published"
            artifact_root = Path(temp_dir) / "v20"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "rule_authority_minimum_coverage":
                    payload = {
                        "status": "fail",
                        "generated_at_utc": module.now_iso(),
                        "rulesets": {
                            "sr4": {
                                "status": "fail",
                                "remaining_gates": ["human rule review signoff"],
                                "verification_matrix_status": "blocked",
                            }
                        },
                        "failures": ["sr4 final_verdict is not ready"],
                    }
                write_required_receipt(module, published, key, path, payload)
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            stderr = io.StringIO()
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", artifact_root), mock.patch.object(module, "REQUIRED_RECEIPTS", required), mock.patch("sys.argv", ["final_gold_janitor.py", "--skip-materializers"]):
                with self.assertRaises(SystemExit):
                    with redirect_stderr(stderr):
                        module.main()

        stderr_text = stderr.getvalue()
        self.assertIn("rule_authority_minimum_coverage", stderr_text)
        self.assertIn("human rule review signoff", stderr_text)
        self.assertIn("NOT_GOLD", stderr_text)

    def test_payload_surfaces_ruleset_readiness_human_side_assumption_as_accepted_boundary(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-ruleset-boundary-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "teable_important_work":
                    payload = passing_teable_important_work_payload(module)
                if key == "flagship_product_readiness":
                    payload = passing_flagship_product_readiness_payload(module)
                if key == "ruleset_readiness":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "rule_authority_human_approval": {
                            "rulesets": ["sr4", "sr6"],
                        },
                        "rulesets": {
                            "sr4": {"human_side_gold_assumption": True},
                            "sr5": {"human_side_gold_assumption": False},
                            "sr6": {"human_side_gold_assumption": False},
                        },
                    }
                if key == "public_route_proof":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "summary": {
                            "route_count": 10,
                            "failed_count": 0,
                            "negative_path_failed_count": 0,
                        },
                    }
                write_required_receipt(module, published, key, path, payload)
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])

        self.assertEqual("pass", payload["status"])
        self.assertNotIn("ruleset_human_side_gold_assumption unresolved", payload["failures"])
        self.assertIn(
            "ruleset_human_side_gold_assumption",
            {str(item.get("id")) for item in payload["caveats"] if isinstance(item, dict)},
        )

    def test_payload_does_not_fail_closed_when_only_authority_approval_exists(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-authority-approved-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "teable_important_work":
                    payload = passing_teable_important_work_payload(module)
                if key == "flagship_product_readiness":
                    payload = passing_flagship_product_readiness_payload(module)
                if key == "ruleset_readiness":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "rule_authority_human_approval": {
                            "rulesets": ["sr4", "sr6"],
                        },
                        "rulesets": {
                            "sr4": {"human_side_gold_assumption": False},
                            "sr5": {"human_side_gold_assumption": False},
                            "sr6": {"human_side_gold_assumption": False},
                        },
                    }
                if key == "external_distribution_mirror_proof":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "external_required": False,
                        "advisory_external_failures": [],
                        "providers": {
                            "local_registry": {"status": "pass"},
                            "public_edge": {"status": "pass"},
                            "onedrive": {"status": "pass"},
                            "pcloud": {"status": "pass"},
                        },
                    }
                if key == "public_route_proof":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "summary": {
                            "route_count": 10,
                            "failed_count": 0,
                            "negative_path_failed_count": 0,
                        },
                    }
                write_required_receipt(module, published, key, path, payload)
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])

        self.assertEqual("pass", payload["status"])
        self.assertNotIn("ruleset_human_side_gold_assumption unresolved", payload["failures"])

    def test_payload_surfaces_optional_external_mirrors_as_operational_advisory(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-mirror-boundary-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = passing_required_receipt_payload(module, key)
                if key == "public_edge_postdeploy_gate":
                    payload = passing_public_edge_postdeploy_payload(module)
                if key == "teable_important_work":
                    payload = passing_teable_important_work_payload(module)
                if key == "flagship_product_readiness":
                    payload = passing_flagship_product_readiness_payload(module)
                if key == "external_distribution_mirror_proof":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "external_required": False,
                        "advisory_external_failures": ["onedrive", "pcloud"],
                        "providers": {
                            "local_registry": {"status": "pass"},
                            "public_edge": {"status": "pass"},
                            "onedrive": {"status": "fail"},
                            "pcloud": {"status": "fail"},
                        },
                    }
                if key == "public_route_proof":
                    payload = {
                        "status": "pass",
                        "generated_at_utc": module.now_iso(),
                        "summary": {
                            "route_count": 10,
                            "failed_count": 0,
                            "negative_path_failed_count": 0,
                        },
                    }
                write_required_receipt(module, published, key, path, payload)
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])

        self.assertEqual("pass", payload["status"])
        self.assertNotIn("optional_external_mirrors_degraded unresolved", payload["failures"])
        self.assertIn(
            "optional_external_mirrors_degraded",
            {str(item.get("id")) for item in payload["caveats"] if isinstance(item, dict)},
        )


if __name__ == "__main__":
    unittest.main()
