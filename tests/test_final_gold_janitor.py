import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "final_gold_janitor.py"


def load_module():
    spec = importlib.util.spec_from_file_location("final_gold_janitor", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
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

        live_windows_index = commands.index("python3 scripts/verify_live_public_windows_installer.py --base-url https://chummer.run")
        public_edge_index = commands.index(public_edge_command)
        blazor_index = commands.index("python3 scripts/verify_blazor_execution_horizon_bridge.py")

        self.assertLess(live_windows_index, public_edge_index)
        self.assertLess(public_edge_index, blazor_index)
        self.assertIn("--expected-release-channel nightly", public_edge_command)
        self.assertIn("--require-downloads-status-playwright", public_edge_command)
        self.assertIn("--require-mobile-pwa-viewport-playwright", public_edge_command)
        self.assertIn("--require-frontdoor-navigation-playwright", public_edge_command)
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

    def test_public_route_materializer_uses_bounded_live_probe_settings(self) -> None:
        module = load_module()
        public_route_command = next(
            command for command in module.MATERIALIZERS
            if "scripts/verify_public_routes_from_manifest.py" in " ".join(command)
        )

        command_text = " ".join(public_route_command)
        self.assertIn("--request-timeout-seconds 2", command_text)
        self.assertIn("--max-retries 0", command_text)
        self.assertIn("--retry-delay-seconds 0.1", command_text)

    def test_run_materializers_records_timeout_instead_of_hanging(self) -> None:
        module = load_module()
        timeout = module.MATERIALIZER_TIMEOUT_SECONDS
        timeout_error = subprocess.TimeoutExpired(cmd=["python3", "slow.py"], timeout=timeout, output="partial out", stderr="partial err")

        with mock.patch.object(module, "MATERIALIZERS", [["python3", "slow.py"]]), mock.patch.object(module.subprocess, "run", side_effect=timeout_error):
            results = module.run_materializers()

        self.assertEqual(1, len(results))
        result = results[0]
        self.assertEqual("python3 slow.py", result["command"])
        self.assertEqual(124, result["returncode"])
        self.assertTrue(result["timed_out"])
        self.assertEqual(timeout, result["timeout_seconds"])
        self.assertEqual("partial out", result["stdout"])
        self.assertEqual("partial err", result["stderr"])

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

    def test_payload_fails_when_public_route_receipt_status_disagrees_with_summary(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-public-route-status-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = {"status": "pass", "generated_at_utc": module.now_iso()}
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
                payload = {"status": "pass", "generated_at_utc": module.now_iso()}
                if key == "design_quality_gate":
                    payload = {
                        "status": "pass",
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

    def test_main_writes_identical_published_and_durable_v20_janitor_artifacts(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-dual-write-") as temp_dir:
            published = Path(temp_dir) / "published"
            artifact_root = Path(temp_dir) / "full_product_reaudit_v20"
            legacy_root = Path(temp_dir) / "gold_readiness_closure"
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
                payload = {"status": "pass", "generated_at_utc": module.now_iso()}
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
                payload = {"status": "pass", "generated_at_utc": module.now_iso()}
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

        gate = payload["required_gates"]["windows_installer_visual_audit"]
        self.assertEqual("fail", payload["status"])
        self.assertEqual("fail", gate["status"])
        self.assertIn("windows_installer_visual_audit failed", payload["failures"])
        self.assertIn("Windows startup receipt is an incompatible-host skip, not native proof", gate["failures"])
        self.assertTrue(any("capture_windows_installer_visual_audit.ps1" in item for item in gate["nextActions"]))

    def test_main_prints_failed_gate_details_before_exiting(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-main-") as temp_dir:
            published = Path(temp_dir) / "published"
            artifact_root = Path(temp_dir) / "v20"
            published.mkdir(parents=True, exist_ok=True)
            for key, path in module.REQUIRED_RECEIPTS.items():
                payload = {"status": "pass", "generated_at_utc": module.now_iso()}
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
                payload = {"status": "pass", "generated_at_utc": module.now_iso()}
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
                payload = {"status": "pass", "generated_at_utc": module.now_iso()}
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
                payload = {"status": "pass", "generated_at_utc": module.now_iso()}
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
