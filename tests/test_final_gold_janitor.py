import importlib.util
import io
import json
import os
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

    def test_materializers_build_minimal_experience_before_design_gate(self) -> None:
        module = load_module()
        commands = [" ".join(command) for command in module.MATERIALIZERS]

        minimal_index = next(index for index, command in enumerate(commands) if "scripts/verify_minimal_experience_gate.py" in command)
        design_index = commands.index("python3 scripts/materialize_design_quality_gate.py")

        self.assertLess(minimal_index, design_index)

    def test_payload_uses_current_v20_root(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            module = load_module()
        self.assertEqual("full_product_reaudit_v20", module.ARTIFACT_ROOT_NAME)
        with tempfile.TemporaryDirectory(prefix="gold-janitor-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            for name in module.REQUIRED_RECEIPTS.values():
                (published / name.name).write_text(
                    json.dumps({"status": "pass", "generated_at_utc": module.now_iso()}),
                    encoding="utf-8",
                )
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])

        self.assertEqual(payload["artifact_root"], "_completion/full_product_reaudit_v20")
        self.assertEqual(payload["scope"], "full_estate_v20")

    def test_payload_fails_on_stale_recrawl(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-stale-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            stale_time = "2020-01-01T00:00:00Z"
            for key, path in module.REQUIRED_RECEIPTS.items():
                generated_at = stale_time if key == "live_public_web_recrawl" else module.now_iso()
                (published / path.name).write_text(
                    json.dumps({"status": "pass", "generated_at_utc": generated_at}),
                    encoding="utf-8",
                )
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])

        self.assertEqual(payload["status"], "fail")
        self.assertIn("live_public_web_recrawl stale", payload["failures"])

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
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")
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

    def test_payload_fails_on_stale_rule_authority_receipt(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="gold-janitor-stale-rules-") as temp_dir:
            published = Path(temp_dir) / "published"
            published.mkdir(parents=True, exist_ok=True)
            stale_time = "2020-01-01T00:00:00Z"
            for key, path in module.REQUIRED_RECEIPTS.items():
                generated_at = stale_time if key == "rule_authority_minimum_coverage" else module.now_iso()
                (published / path.name).write_text(
                    json.dumps({"status": "pass", "generated_at_utc": generated_at}),
                    encoding="utf-8",
                )
            required = {key: published / path.name for key, path in module.REQUIRED_RECEIPTS.items()}
            with mock.patch.object(module, "PUBLISHED_ROOT", published), mock.patch.object(module, "ARTIFACT_ROOT", Path(temp_dir) / "v20"), mock.patch.object(module, "REQUIRED_RECEIPTS", required):
                payload = module.build_payload([])

        self.assertEqual(payload["status"], "fail")
        self.assertIn("rule_authority_minimum_coverage stale", payload["failures"])

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
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")
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
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")
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
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")
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
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")
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
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")
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
                (published / path.name).write_text(json.dumps(payload), encoding="utf-8")
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
