import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/verify_rules_authority_minimum_coverage.py")


def load_module():
    spec = importlib.util.spec_from_file_location("verify_rules_authority_minimum_coverage", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ready_registry(module, ruleset: str, verdict: str, *, count: int = 120, omit_provider: str | None = None) -> dict:
    providers = [
        provider
        for candidates in module.REQUIRED_PROVIDER_GROUPS[ruleset].values()
        for provider in candidates
    ]
    fact_providers = [provider for provider in providers if provider != omit_provider]
    if not fact_providers:
        raise ValueError("ready_registry requires at least one rulefact provider")
    rulefacts = [
        {
            "id": f"{ruleset}.{index:03d}.{fact_providers[index % len(fact_providers)]}",
            "provider": fact_providers[index % len(fact_providers)],
            "ruleset": ruleset,
        }
        for index in range(count)
    ]
    return {
        "rulefact_count": len(rulefacts),
        "final_verdict": verdict,
        "status": "pass",
        "required_providers": providers,
        "implemented_providers": providers,
        "missing_implemented_providers": [],
        "rulefacts": rulefacts,
    }


class RulesAuthorityMinimumCoverageGateTests(unittest.TestCase):
    def test_gate_fails_below_threshold(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="rules-min-") as temp_dir:
            root = Path(temp_dir)
            for name in ("SR4_RULEFACT_REGISTRY.generated.json", "SR5_RULE_AUTHORITY_REGISTRY.generated.json", "SR6_RULEFACT_REGISTRY.generated.json"):
                (root / ".codex-studio" / "published").mkdir(parents=True, exist_ok=True)
                (root / ".codex-studio" / "published" / name).write_text(
                    json.dumps({"rulefact_count": 5, "final_verdict": "READY"}),
                    encoding="utf-8",
                )
            (root / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json").write_text(
                json.dumps({"rulesets": {"sr4": {"rule_authority_ready": True}, "sr5": {"rule_authority_ready": True}, "sr6": {"rule_authority_ready": True}}}),
                encoding="utf-8",
            )
            (root / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json").write_text(
                json.dumps({"rulesets": [{"ruleset": "sr4", "status": "pass", "verdict": "SR4_RULE_AUTHORITY_READY"}, {"ruleset": "sr5", "status": "pass", "verdict": "SR5_RULE_AUTHORITY_READY"}, {"ruleset": "sr6", "status": "pass", "verdict": "SR6_RULE_AUTHORITY_READY"}]}),
                encoding="utf-8",
            )
            output = root / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json"
            with mock.patch.object(module, "CORE_ENGINE_ROOT", root), mock.patch.object(module, "OUTPUT_PATH", output), mock.patch.object(module, "FULL_COMPLETION_PATH", root / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json"), mock.patch.object(module, "OPERATOR_GOLD_PATH", root / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json"):
                stderr = io.StringIO()
                with self.assertRaises(SystemExit):
                    with redirect_stderr(stderr), mock.patch("sys.argv", ["verify_rules_authority_minimum_coverage.py", "--min-rulefacts", "100"]):
                        module.main()
            self.assertIn("sr4 rulefact_count 5 is below minimum 100", stderr.getvalue())
            self.assertIn(str(output), stderr.getvalue())

    def test_gate_passes_at_threshold(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="rules-min-pass-") as temp_dir:
            root = Path(temp_dir)
            for name in ("SR4_RULEFACT_REGISTRY.generated.json", "SR5_RULE_AUTHORITY_REGISTRY.generated.json", "SR6_RULEFACT_REGISTRY.generated.json"):
                (root / ".codex-studio" / "published").mkdir(parents=True, exist_ok=True)
            (root / ".codex-studio" / "published" / "SR4_RULEFACT_REGISTRY.generated.json").write_text(json.dumps(ready_registry(module, "sr4", "SR4_RULE_AUTHORITY_READY")), encoding="utf-8")
            (root / ".codex-studio" / "published" / "SR5_RULE_AUTHORITY_REGISTRY.generated.json").write_text(json.dumps(ready_registry(module, "sr5", "SR5_RULE_AUTHORITY_READY")), encoding="utf-8")
            (root / ".codex-studio" / "published" / "SR6_RULEFACT_REGISTRY.generated.json").write_text(json.dumps(ready_registry(module, "sr6", "SR6_RULE_AUTHORITY_READY")), encoding="utf-8")
            (root / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json").write_text(
                json.dumps({"rulesets": {"sr4": {"rule_authority_ready": True}, "sr5": {"rule_authority_ready": True}, "sr6": {"rule_authority_ready": True}}}),
                encoding="utf-8",
            )
            (root / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json").write_text(
                json.dumps({"rulesets": [{"ruleset": "sr4", "status": "pass", "verdict": "SR4_RULE_AUTHORITY_READY"}, {"ruleset": "sr5", "status": "pass", "verdict": "SR5_RULE_AUTHORITY_READY"}, {"ruleset": "sr6", "status": "pass", "verdict": "SR6_RULE_AUTHORITY_READY"}]}),
                encoding="utf-8",
            )
            output = root / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json"
            with mock.patch.object(module, "CORE_ENGINE_ROOT", root), mock.patch.object(module, "OUTPUT_PATH", output), mock.patch.object(module, "FULL_COMPLETION_PATH", root / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json"), mock.patch.object(module, "OPERATOR_GOLD_PATH", root / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json"):
                with mock.patch("sys.argv", ["verify_rules_authority_minimum_coverage.py", "--min-rulefacts", "100"]):
                    self.assertEqual(module.main(), 0)

    def test_gate_rejects_marker_only_ready_registry(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="rules-min-marker-only-") as temp_dir:
            root = Path(temp_dir)
            (root / ".codex-studio" / "published").mkdir(parents=True, exist_ok=True)
            for name, verdict in (
                ("SR4_RULEFACT_REGISTRY.generated.json", "SR4_RULE_AUTHORITY_READY"),
                ("SR5_RULE_AUTHORITY_REGISTRY.generated.json", "SR5_RULE_AUTHORITY_READY"),
                ("SR6_RULEFACT_REGISTRY.generated.json", "SR6_RULE_AUTHORITY_READY"),
            ):
                (root / ".codex-studio" / "published" / name).write_text(
                    json.dumps({"rulefact_count": 120, "final_verdict": verdict}),
                    encoding="utf-8",
                )
            (root / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json").write_text(
                json.dumps({"rulesets": {"sr4": {"rule_authority_ready": True}, "sr5": {"rule_authority_ready": True}, "sr6": {"rule_authority_ready": True}}}),
                encoding="utf-8",
            )
            (root / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json").write_text(
                json.dumps({"rulesets": [{"ruleset": "sr4", "status": "pass", "verdict": "SR4_RULE_AUTHORITY_READY"}, {"ruleset": "sr5", "status": "pass", "verdict": "SR5_RULE_AUTHORITY_READY"}, {"ruleset": "sr6", "status": "pass", "verdict": "SR6_RULE_AUTHORITY_READY"}]}),
                encoding="utf-8",
            )
            output = root / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json"
            with mock.patch.object(module, "CORE_ENGINE_ROOT", root), mock.patch.object(module, "OUTPUT_PATH", output), mock.patch.object(module, "FULL_COMPLETION_PATH", root / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json"), mock.patch.object(module, "OPERATOR_GOLD_PATH", root / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json"):
                stderr = io.StringIO()
                with self.assertRaises(SystemExit):
                    with redirect_stderr(stderr), mock.patch("sys.argv", ["verify_rules_authority_minimum_coverage.py", "--min-rulefacts", "100"]):
                        module.main()

            self.assertIn("sr4 rule authority registry is missing a rulefacts list", stderr.getvalue())
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertIn("sr5 rule authority registry declares no required providers", payload["failures"])
            self.assertEqual("fail", payload["rulesets"]["sr6"]["status"])

    def test_gate_rejects_superseded_registry_even_with_ready_marker(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="rules-min-superseded-") as temp_dir:
            root = Path(temp_dir)
            (root / ".codex-studio" / "published").mkdir(parents=True, exist_ok=True)
            (root / ".codex-studio" / "published" / "SR4_RULEFACT_REGISTRY.generated.json").write_text(
                json.dumps(ready_registry(module, "sr4", "SR4_RULE_AUTHORITY_READY")),
                encoding="utf-8",
            )
            sr5_registry = ready_registry(module, "sr5", "SR5_RULE_AUTHORITY_READY")
            sr5_registry["superseded"] = True
            (root / ".codex-studio" / "published" / "SR5_RULE_AUTHORITY_REGISTRY.generated.json").write_text(
                json.dumps(sr5_registry),
                encoding="utf-8",
            )
            (root / ".codex-studio" / "published" / "SR6_RULEFACT_REGISTRY.generated.json").write_text(
                json.dumps(ready_registry(module, "sr6", "SR6_RULE_AUTHORITY_READY")),
                encoding="utf-8",
            )
            (root / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json").write_text(
                json.dumps({"rulesets": {"sr4": {"rule_authority_ready": True}, "sr5": {"rule_authority_ready": True}, "sr6": {"rule_authority_ready": True}}}),
                encoding="utf-8",
            )
            (root / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json").write_text(
                json.dumps({"rulesets": [{"ruleset": "sr4", "status": "pass", "verdict": "SR4_RULE_AUTHORITY_READY"}, {"ruleset": "sr5", "status": "pass", "verdict": "SR5_RULE_AUTHORITY_READY"}, {"ruleset": "sr6", "status": "pass", "verdict": "SR6_RULE_AUTHORITY_READY"}]}),
                encoding="utf-8",
            )
            output = root / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json"
            with mock.patch.object(module, "CORE_ENGINE_ROOT", root), mock.patch.object(module, "OUTPUT_PATH", output), mock.patch.object(module, "FULL_COMPLETION_PATH", root / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json"), mock.patch.object(module, "OPERATOR_GOLD_PATH", root / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json"):
                stderr = io.StringIO()
                with self.assertRaises(SystemExit):
                    with redirect_stderr(stderr), mock.patch("sys.argv", ["verify_rules_authority_minimum_coverage.py", "--min-rulefacts", "100"]):
                        module.main()

            self.assertIn("sr5 rule authority registry is superseded", stderr.getvalue())
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(["sr5 rule authority registry is superseded"], payload["rulesets"]["sr5"]["schema_failures"])

    def test_gate_fails_when_completion_or_operator_gold_are_not_ready(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="rules-min-completion-") as temp_dir:
            root = Path(temp_dir)
            (root / ".codex-studio" / "published").mkdir(parents=True, exist_ok=True)
            (root / ".codex-studio" / "published" / "SR4_RULEFACT_REGISTRY.generated.json").write_text(json.dumps(ready_registry(module, "sr4", "SR4_RULE_AUTHORITY_READY")), encoding="utf-8")
            (root / ".codex-studio" / "published" / "SR5_RULE_AUTHORITY_REGISTRY.generated.json").write_text(json.dumps(ready_registry(module, "sr5", "SR5_RULE_AUTHORITY_READY")), encoding="utf-8")
            (root / ".codex-studio" / "published" / "SR6_RULEFACT_REGISTRY.generated.json").write_text(json.dumps(ready_registry(module, "sr6", "SR6_RULE_AUTHORITY_READY")), encoding="utf-8")
            (root / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json").write_text(
                json.dumps({"rulesets": {"sr4": {"rule_authority_ready": False}, "sr5": {"rule_authority_ready": True}, "sr6": {"rule_authority_ready": False}}}),
                encoding="utf-8",
            )
            (root / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json").write_text(
                json.dumps({"rulesets": [{"ruleset": "sr4", "status": "fail", "verdict": "NOT_READY"}, {"ruleset": "sr5", "status": "pass", "verdict": "SR5_RULE_AUTHORITY_READY"}, {"ruleset": "sr6", "status": "fail", "verdict": "NOT_READY"}]}),
                encoding="utf-8",
            )
            output = root / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json"
            with mock.patch.object(module, "CORE_ENGINE_ROOT", root), mock.patch.object(module, "OUTPUT_PATH", output), mock.patch.object(module, "FULL_COMPLETION_PATH", root / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json"), mock.patch.object(module, "OPERATOR_GOLD_PATH", root / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json"):
                stderr = io.StringIO()
                with self.assertRaises(SystemExit):
                    with redirect_stderr(stderr), mock.patch("sys.argv", ["verify_rules_authority_minimum_coverage.py", "--min-rulefacts", "100"]):
                        module.main()
            self.assertIn("sr4 full product rule authority completion is not ready", stderr.getvalue())

    def test_gate_surfaces_blocker_receipts_when_not_ready(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="rules-min-blockers-") as temp_dir:
            root = Path(temp_dir)
            (root / ".codex-studio" / "published").mkdir(parents=True, exist_ok=True)
            (root / ".codex-studio" / "published" / "SR4_RULEFACT_REGISTRY.generated.json").write_text(json.dumps({"rulefact_count": 120, "final_verdict": "NOT_READY"}), encoding="utf-8")
            (root / ".codex-studio" / "published" / "SR5_RULE_AUTHORITY_REGISTRY.generated.json").write_text(json.dumps({"rulefact_count": 120, "final_verdict": "SR5_RULE_AUTHORITY_READY"}), encoding="utf-8")
            (root / ".codex-studio" / "published" / "SR6_RULEFACT_REGISTRY.generated.json").write_text(json.dumps({"rulefact_count": 120, "final_verdict": "NOT_READY"}), encoding="utf-8")
            (root / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json").write_text(
                json.dumps({
                    "generated_at_utc": "2026-06-09T13:30:00Z",
                    "rulesets": {"sr4": {"rule_authority_ready": False}, "sr5": {"rule_authority_ready": True}, "sr6": {"rule_authority_ready": False}},
                    "blockers": [
                        {
                            "ruleset": "sr4",
                            "blocker_receipts": {
                                "row_level_mapping": "/tmp/sr4-row.json",
                                "errata_posture": "/tmp/sr4-errata.json",
                                "verification_matrix_run": str(root / "sr4-matrix.json"),
                            },
                            "row_level_mapping_status": "pending_human_review",
                            "errata_posture_status": "pending_reviewed_application",
                            "human_review_status": {"pending_review": True, "review_ready": False, "source_baseline_required": False},
                            "remaining_gates": ["human-reviewed row-level mapping", "errata profile applied and reviewed"],
                        },
                        {
                            "ruleset": "sr6",
                            "blocker_receipts": {
                                "row_level_mapping": "/tmp/sr6-row.json",
                                "errata_posture": "/tmp/sr6-errata.json",
                                "verification_matrix_run": str(root / "sr6-matrix.json"),
                            },
                            "row_level_mapping_status": "pending_human_review",
                            "errata_posture_status": "pending_reviewed_application",
                            "human_review_status": {"pending_review": True, "review_ready": False, "source_baseline_required": True},
                            "remaining_gates": ["human-reviewed mapping", "errata profile applied and reviewed"],
                        },
                    ],
                }),
                encoding="utf-8",
            )
            (root / "sr4-matrix.json").write_text(
                json.dumps({"status": "blocked", "failed_gates": ["SR4-G013"], "unexpected_failed_gates": [], "expected_ready_blockers": ["SR4-G013"]}),
                encoding="utf-8",
            )
            (root / "sr6-matrix.json").write_text(
                json.dumps({"status": "blocked", "failed_gates": ["SR6-G012"], "unexpected_failed_gates": [], "expected_ready_blockers": ["SR6-G012"]}),
                encoding="utf-8",
            )
            (root / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json").write_text(
                json.dumps({"rulesets": [{"ruleset": "sr4", "status": "fail", "verdict": "NOT_READY"}, {"ruleset": "sr5", "status": "pass", "verdict": "SR5_RULE_AUTHORITY_READY"}, {"ruleset": "sr6", "status": "fail", "verdict": "NOT_READY"}]}),
                encoding="utf-8",
            )
            output = root / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json"
            with mock.patch.object(module, "CORE_ENGINE_ROOT", root), mock.patch.object(module, "OUTPUT_PATH", output), mock.patch.object(module, "FULL_COMPLETION_PATH", root / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json"), mock.patch.object(module, "OPERATOR_GOLD_PATH", root / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json"):
                stderr = io.StringIO()
                with self.assertRaises(SystemExit):
                    with redirect_stderr(stderr), mock.patch("sys.argv", ["verify_rules_authority_minimum_coverage.py", "--min-rulefacts", "100"]):
                        module.main()
            self.assertIn("human-reviewed row-level mapping", stderr.getvalue())
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertRegex(payload["generated_at_utc"], r"^\d{4}-\d{2}-\d{2}T")
            self.assertEqual("2026-06-09T13:30:00Z", payload["source_generated_at_utc"]["full_completion"])
            self.assertEqual("/tmp/sr4-row.json", payload["rulesets"]["sr4"]["blocker_receipts"]["row_level_mapping"])
            self.assertEqual("pending_reviewed_application", payload["rulesets"]["sr6"]["errata_posture_status"])
            self.assertTrue(payload["rulesets"]["sr4"]["human_review_status"]["pending_review"])
            self.assertFalse(payload["rulesets"]["sr6"]["human_review_status"]["review_ready"])
            self.assertFalse(payload["rulesets"]["sr4"]["human_review_status"]["source_baseline_required"])
            self.assertTrue(payload["rulesets"]["sr6"]["human_review_status"]["source_baseline_required"])
            self.assertEqual("blocked", payload["rulesets"]["sr4"]["verification_matrix_status"])
            self.assertEqual([], payload["rulesets"]["sr6"]["verification_matrix_unexpected_failed_gates"])

    def test_gate_fails_when_matrix_has_unexpected_failures(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="rules-min-matrix-") as temp_dir:
            root = Path(temp_dir)
            (root / ".codex-studio" / "published").mkdir(parents=True, exist_ok=True)
            (root / ".codex-studio" / "published" / "SR4_RULEFACT_REGISTRY.generated.json").write_text(json.dumps({"rulefact_count": 120, "final_verdict": "NOT_READY"}), encoding="utf-8")
            (root / ".codex-studio" / "published" / "SR5_RULE_AUTHORITY_REGISTRY.generated.json").write_text(json.dumps({"rulefact_count": 120, "final_verdict": "SR5_RULE_AUTHORITY_READY"}), encoding="utf-8")
            (root / ".codex-studio" / "published" / "SR6_RULEFACT_REGISTRY.generated.json").write_text(json.dumps({"rulefact_count": 120, "final_verdict": "SR6_RULE_AUTHORITY_READY"}), encoding="utf-8")
            matrix_path = root / "sr4-matrix.json"
            matrix_path.write_text(json.dumps({"status": "fail", "failed_gates": ["SR4-G002"], "unexpected_failed_gates": ["SR4-G002"], "expected_ready_blockers": ["SR4-G013"]}), encoding="utf-8")
            (root / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json").write_text(
                json.dumps({
                    "rulesets": {"sr4": {"rule_authority_ready": False}, "sr5": {"rule_authority_ready": True}, "sr6": {"rule_authority_ready": True}},
                    "blockers": [{"ruleset": "sr4", "blocker_receipts": {"verification_matrix_run": str(matrix_path)}}],
                }),
                encoding="utf-8",
            )
            (root / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json").write_text(
                json.dumps({"rulesets": [{"ruleset": "sr4", "status": "fail", "verdict": "NOT_READY"}, {"ruleset": "sr5", "status": "pass", "verdict": "SR5_RULE_AUTHORITY_READY"}, {"ruleset": "sr6", "status": "pass", "verdict": "SR6_RULE_AUTHORITY_READY"}]}),
                encoding="utf-8",
            )
            output = root / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json"
            with mock.patch.object(module, "CORE_ENGINE_ROOT", root), mock.patch.object(module, "OUTPUT_PATH", output), mock.patch.object(module, "FULL_COMPLETION_PATH", root / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json"), mock.patch.object(module, "OPERATOR_GOLD_PATH", root / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json"):
                stderr = io.StringIO()
                with self.assertRaises(SystemExit):
                    with redirect_stderr(stderr), mock.patch("sys.argv", ["verify_rules_authority_minimum_coverage.py", "--min-rulefacts", "100"]):
                        module.main()
            self.assertIn("SR4-G002", stderr.getvalue())

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertIn("sr4 verification matrix has unexpected failed gates", payload["failures"])
            self.assertEqual("fail", payload["rulesets"]["sr4"]["status"])
            self.assertEqual(["SR4-G002"], payload["rulesets"]["sr4"]["verification_matrix_unexpected_failed_gates"])

    def test_gate_fails_ruleset_status_when_only_matrix_has_unexpected_failures(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="rules-min-ready-matrix-") as temp_dir:
            root = Path(temp_dir)
            (root / ".codex-studio" / "published").mkdir(parents=True, exist_ok=True)
            (root / ".codex-studio" / "published" / "SR4_RULEFACT_REGISTRY.generated.json").write_text(json.dumps({"rulefact_count": 120, "final_verdict": "SR4_RULE_AUTHORITY_READY"}), encoding="utf-8")
            (root / ".codex-studio" / "published" / "SR5_RULE_AUTHORITY_REGISTRY.generated.json").write_text(json.dumps({"rulefact_count": 120, "final_verdict": "SR5_RULE_AUTHORITY_READY"}), encoding="utf-8")
            (root / ".codex-studio" / "published" / "SR6_RULEFACT_REGISTRY.generated.json").write_text(json.dumps({"rulefact_count": 120, "final_verdict": "SR6_RULE_AUTHORITY_READY"}), encoding="utf-8")
            matrix_path = root / "sr4-matrix.json"
            matrix_path.write_text(json.dumps({"status": "fail", "failed_gates": ["SR4-G002"], "unexpected_failed_gates": ["SR4-G002"], "expected_ready_blockers": []}), encoding="utf-8")
            (root / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json").write_text(
                json.dumps({
                    "rulesets": {"sr4": {"rule_authority_ready": True}, "sr5": {"rule_authority_ready": True}, "sr6": {"rule_authority_ready": True}},
                    "blockers": [{"ruleset": "sr4", "blocker_receipts": {"verification_matrix_run": str(matrix_path)}}],
                }),
                encoding="utf-8",
            )
            (root / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json").write_text(
                json.dumps({"rulesets": [{"ruleset": "sr4", "status": "pass", "verdict": "SR4_RULE_AUTHORITY_READY"}, {"ruleset": "sr5", "status": "pass", "verdict": "SR5_RULE_AUTHORITY_READY"}, {"ruleset": "sr6", "status": "pass", "verdict": "SR6_RULE_AUTHORITY_READY"}]}),
                encoding="utf-8",
            )
            output = root / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json"
            with mock.patch.object(module, "CORE_ENGINE_ROOT", root), mock.patch.object(module, "OUTPUT_PATH", output), mock.patch.object(module, "FULL_COMPLETION_PATH", root / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json"), mock.patch.object(module, "OPERATOR_GOLD_PATH", root / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json"):
                stderr = io.StringIO()
                with self.assertRaises(SystemExit):
                    with redirect_stderr(stderr), mock.patch("sys.argv", ["verify_rules_authority_minimum_coverage.py", "--min-rulefacts", "100"]):
                        module.main()

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("fail", payload["rulesets"]["sr4"]["status"])
            self.assertIn("sr4 verification matrix has unexpected failed gates", payload["failures"])
            self.assertIn("SR4-G002", stderr.getvalue())

    def test_gate_fails_when_declared_required_provider_has_no_rulefacts(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory(prefix="rules-min-provider-") as temp_dir:
            root = Path(temp_dir)
            (root / ".codex-studio" / "published").mkdir(parents=True, exist_ok=True)
            (root / ".codex-studio" / "published" / "SR4_RULEFACT_REGISTRY.generated.json").write_text(
                json.dumps(ready_registry(module, "sr4", "SR4_RULE_AUTHORITY_READY")),
                encoding="utf-8",
            )
            (root / ".codex-studio" / "published" / "SR5_RULE_AUTHORITY_REGISTRY.generated.json").write_text(
                json.dumps(ready_registry(module, "sr5", "SR5_RULE_AUTHORITY_READY", omit_provider="SR5CombatProvider")),
                encoding="utf-8",
            )
            (root / ".codex-studio" / "published" / "SR6_RULEFACT_REGISTRY.generated.json").write_text(
                json.dumps(ready_registry(module, "sr6", "SR6_RULE_AUTHORITY_READY")),
                encoding="utf-8",
            )
            (root / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json").write_text(
                json.dumps({"rulesets": {"sr4": {"rule_authority_ready": True}, "sr5": {"rule_authority_ready": True}, "sr6": {"rule_authority_ready": True}}}),
                encoding="utf-8",
            )
            (root / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json").write_text(
                json.dumps({"rulesets": [{"ruleset": "sr4", "status": "pass", "verdict": "SR4_RULE_AUTHORITY_READY"}, {"ruleset": "sr5", "status": "pass", "verdict": "SR5_RULE_AUTHORITY_READY"}, {"ruleset": "sr6", "status": "pass", "verdict": "SR6_RULE_AUTHORITY_READY"}]}),
                encoding="utf-8",
            )
            output = root / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json"
            with mock.patch.object(module, "CORE_ENGINE_ROOT", root), mock.patch.object(module, "OUTPUT_PATH", output), mock.patch.object(module, "FULL_COMPLETION_PATH", root / ".codex-studio" / "published" / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json"), mock.patch.object(module, "OPERATOR_GOLD_PATH", root / ".codex-studio" / "published" / "OPERATOR_PROMOTED_RULE_AUTHORITY_GOLD.generated.json"):
                stderr = io.StringIO()
                with self.assertRaises(SystemExit):
                    with redirect_stderr(stderr), mock.patch("sys.argv", ["verify_rules_authority_minimum_coverage.py", "--min-rulefacts", "100"]):
                        module.main()

            self.assertIn("sr5 required provider group combat has no rulefacts", stderr.getvalue())
            payload = json.loads(output.read_text(encoding="utf-8"))
            sr5_combat = payload["rulesets"]["sr5"]["provider_group_coverage"]["groups"]["combat"]
            self.assertEqual("fail", payload["rulesets"]["sr5"]["status"])
            self.assertEqual(["SR5CombatProvider"], sr5_combat["listed_providers"])
            self.assertEqual(0, sr5_combat["rulefact_count"])


if __name__ == "__main__":
    unittest.main()
