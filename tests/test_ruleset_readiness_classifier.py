import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "classify_ruleset_readiness.py"


def load_module():
    sys.path.insert(0, str(SCRIPT_PATH.parent))
    spec = importlib.util.spec_from_file_location("classify_ruleset_readiness", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_receipt(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


class RulesetReadinessClassifierTests(unittest.TestCase):
    def test_sr5_uses_authoritative_minimum_coverage_when_ui_gate_is_failing(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="ruleset-readiness-") as temp_dir:
            root = Path(temp_dir)
            presentation = root / "presentation"
            core = root / "core"
            fleet = root / "fleet"
            coverage = root / "run-services" / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json"

            write_receipt(presentation / "SR4_DESKTOP_WORKFLOW_PARITY.generated.json", {"status": "pass"})
            write_receipt(presentation / "SR6_DESKTOP_WORKFLOW_PARITY.generated.json", {"status": "pass"})
            write_receipt(presentation / "SR4_SR6_DESKTOP_PARITY_FRONTIER.generated.json", {"status": "pass"})
            write_receipt(presentation / "UI_FLAGSHIP_RELEASE_GATE.generated.json", {"status": "fail"})
            write_receipt(fleet / "NEXT90_M136_FLEET_AGGREGATE_READINESS_PARITY_GATES.generated.json", {"status": "pass"})
            write_receipt(fleet / "NEXT90_M136_FLEET_SR4_SR6_READINESS_CLOSEOUT.generated.json", {"status": "pass"})
            write_receipt(core / "CODEX_OPERATOR_RULE_AUTHORITY_REVIEW.generated.json", {
                "status": "operator_review_complete_authority_ready",
                "readiness_decision": {"full_product_rule_authority_ready": True},
            })
            write_receipt(core / "HUMAN_SIDE_RULE_AUTHORITY_GOLD_APPROVAL.generated.json", {
                "status": "pass",
                "rulesets": ["sr4", "sr6"],
            })
            write_receipt(core / "FULL_PRODUCT_RULE_AUTHORITY_COMPLETION.generated.json", {
                "status": "pass",
                "readiness_token_allowed": True,
            })
            write_receipt(coverage, {
                "status": "pass",
                "rulesets": {
                    "sr5": {
                        "status": "pass",
                        "rulefact_count": 375,
                        "final_verdict": "SR5_RULE_AUTHORITY_READY",
                        "full_completion_rule_authority_ready": True,
                    }
                },
            })

            with (
                mock.patch.object(module, "PRESENTATION_PUBLISHED", presentation),
                mock.patch.object(module, "CORE_PUBLISHED", core),
                mock.patch.object(module, "FLEET_PUBLISHED", fleet),
                mock.patch.object(module, "RULE_AUTHORITY_MINIMUM_COVERAGE_PATH", coverage),
            ):
                payload = module.classify()

        self.assertEqual("pass", payload["status"])
        self.assertEqual("full", payload["rulesets"]["sr5"]["readiness"])
        self.assertEqual("rule_authority_minimum_coverage", payload["rulesets"]["sr5"]["readiness_basis"])
        self.assertEqual("pass", payload["rulesets"]["sr5"]["rule_authority_status"])

    def test_sr5_minimum_coverage_requires_ready_verdict_and_rulefact_depth(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="ruleset-readiness-depth-") as temp_dir:
            coverage = Path(temp_dir) / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json"
            write_receipt(coverage, {
                "status": "pass",
                "rulesets": {
                    "sr5": {
                        "status": "pass",
                        "rulefact_count": 99,
                        "final_verdict": "SR5_RULE_AUTHORITY_READY",
                        "full_completion_rule_authority_ready": True,
                    }
                },
            })

            with mock.patch.object(module, "RULE_AUTHORITY_MINIMUM_COVERAGE_PATH", coverage):
                self.assertEqual("fail", module.minimum_coverage_status("sr5"))

            write_receipt(coverage, {
                "status": "pass",
                "rulesets": {
                    "sr5": {
                        "status": "pass",
                        "rulefact_count": 120,
                        "final_verdict": "NOT_READY",
                        "full_completion_rule_authority_ready": True,
                    }
                },
            })

            with mock.patch.object(module, "RULE_AUTHORITY_MINIMUM_COVERAGE_PATH", coverage):
                self.assertEqual("fail", module.minimum_coverage_status("sr5"))


if __name__ == "__main__":
    unittest.main()
