import importlib.util
import os
import unittest
from pathlib import Path


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/audit_full_product_reaudit_v16_gate_semantics.py")


def load_module():
    spec = importlib.util.spec_from_file_location("audit_full_product_reaudit_v16_gate_semantics", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_module()
RULE_AUTHORITY_STATE_CHECK = "{edition} rule authority is either bounded-blocked on review or backed by ready completion"


def statuses(checks):
    return {check["name"]: check["status"] for check in checks}


class FullProductReauditV16GateSemanticTests(unittest.TestCase):
    def test_surface_verify_base_url_defaults_to_local_runtime(self) -> None:
        previous = os.environ.pop("CHUMMER_FULL_PRODUCT_REAUDIT_SURFACE_BASE_URL", None)
        try:
            module = load_module()
            self.assertEqual(module.SURFACE_VERIFY_BASE_URL, "http://127.0.0.1:8091")
            self.assertEqual(
                module.surface_verify_command("verify_pwa_notification_runtime.py"),
                [
                    "python3",
                    "scripts/verify_pwa_notification_runtime.py",
                    "--base-url",
                    "http://127.0.0.1:8091",
                ],
            )
        finally:
            if previous is not None:
                os.environ["CHUMMER_FULL_PRODUCT_REAUDIT_SURFACE_BASE_URL"] = previous

    def test_public_guide_release_truth_fails_on_stale_macos_copy(self) -> None:
        checks = MODULE.public_guide_release_truth_checks(
            {
                "available_platforms": ["Windows", "Linux"],
                "missing_platforms": ["macOS"],
                "shelf_truth_line": "Downloads are currently live for Windows and Linux.",
            },
            "Downloads are currently live for Windows and Linux. There is no public macOS installer today.",
        )

        self.assertTrue(any(check["status"] == "fail" for check in checks))
        self.assertEqual(
            statuses(checks)["public guide copy does not regress to stale missing-macOS installer truth"],
            "fail",
        )

    def test_public_guide_release_truth_passes_on_three_platform_shelf(self) -> None:
        checks = MODULE.public_guide_release_truth_checks(
            {
                "available_platforms": ["Windows", "Linux", "macOS"],
                "missing_platforms": [],
                "shelf_truth_line": "Downloads are currently live for Windows, Linux, and macOS.",
            },
            "Avalonia Desktop Windows Installer\nAvalonia Desktop Linux Installer\nAvalonia Desktop macOS ARM64 Installer",
        )

        self.assertTrue(all(check["status"] == "pass" for check in checks), checks)

    def test_journey_gate_truth_fails_on_blocked_current_truth(self) -> None:
        blocked = MODULE.journey_gate_truth_check({"current_truth": {"state": "blocked", "blocked_count": 1}})
        ready = MODULE.journey_gate_truth_check({"current_truth": {"state": "ready", "blocked_count": 0}})

        self.assertEqual(blocked["status"], "fail")
        self.assertEqual(ready["status"], "pass")

    def test_every_wonder_horizon_receipt_fails_false_magicfit_claims(self) -> None:
        receipt = self.valid_horizon_receipt()
        receipt["provider_claim"] = "MagicFit"
        receipt["magicfit_claim_allowed"] = True
        receipt["proof_constraints"] = []

        checks = MODULE.every_wonder_horizon_receipt_checks(receipt, self.valid_probe())

        self.assertEqual(
            statuses(checks)["Every Wonder Horizon promo stays proof-bounded and does not fake MagicFit rendering"],
            "fail",
        )

    def test_every_wonder_horizon_receipt_fails_wrong_or_missing_scenes(self) -> None:
        receipt = self.valid_horizon_receipt()
        receipt["production_scenes"] = receipt["production_scenes"][:11]

        checks = MODULE.every_wonder_horizon_receipt_checks(receipt, self.valid_probe())

        self.assertEqual(
            statuses(checks)["Every Wonder Horizon promo receipt proves the required 12-scene production sheet"],
            "fail",
        )

    def test_every_wonder_horizon_receipt_passes_full_receipt(self) -> None:
        checks = MODULE.every_wonder_horizon_receipt_checks(self.valid_horizon_receipt(), self.valid_probe())

        self.assertTrue(all(check["status"] == "pass" for check in checks), checks)

    def test_rule_authority_receipt_passes_when_sr4_and_sr6_are_explicit_human_review_blockers(self) -> None:
        checks = MODULE.rule_authority_receipt_checks(
            self.valid_rule_authority_minimum_coverage(),
            {
                "sr4": "NOT_READY\n\n- copyright safety: pass\n\nCopyright boundary: implementation facts only.",
                "sr5": "SR5_RULE_AUTHORITY_READY\n\n- acceptance proof: pass\n\nCopyright boundary: structured data only.",
                "sr6": "NOT_READY\n\n- copyright safety: pass\n\nCopyright boundary: implementation facts only.",
            },
        )

        self.assertTrue(all(check["status"] == "pass" for check in checks), checks)

    def test_rule_authority_receipt_fails_if_sr6_has_unexpected_matrix_failure(self) -> None:
        receipt = self.valid_rule_authority_minimum_coverage()
        receipt["rulesets"]["sr6"]["verification_matrix_unexpected_failed_gates"] = ["SR6-G999"]

        checks = MODULE.rule_authority_receipt_checks(
            receipt,
            {
                "sr4": "NOT_READY\n\n- copyright safety: pass\n\nCopyright boundary: implementation facts only.",
                "sr5": "SR5_RULE_AUTHORITY_READY\n\n- acceptance proof: pass\n\nCopyright boundary: structured data only.",
                "sr6": "NOT_READY\n\n- copyright safety: pass\n\nCopyright boundary: implementation facts only.",
            },
        )

        self.assertEqual(
            statuses(checks)[RULE_AUTHORITY_STATE_CHECK.format(edition="SR6")],
            "fail",
        )

    def test_rule_authority_receipt_fails_if_blocked_ruleset_claims_ready_marker(self) -> None:
        checks = MODULE.rule_authority_receipt_checks(
            self.valid_rule_authority_minimum_coverage(),
            {
                "sr4": "SR4_RULE_AUTHORITY_READY\n\n- copyright safety: pass\n\nCopyright boundary: implementation facts only.",
                "sr5": "SR5_RULE_AUTHORITY_READY\n\n- acceptance proof: pass\n\nCopyright boundary: structured data only.",
                "sr6": "NOT_READY\n\n- copyright safety: pass\n\nCopyright boundary: implementation facts only.",
            },
        )

        self.assertEqual(
            statuses(checks)[RULE_AUTHORITY_STATE_CHECK.format(edition="SR4")],
            "fail",
        )

    def valid_probe(self):
        return {"status": "pass", "has_video": True, "has_audio": True, "duration": 90.0}

    def valid_horizon_receipt(self):
        return {
            "status": "published",
            "scene_count": 12,
            "production_scenes": [{"id": scene_id} for scene_id in MODULE.REQUIRED_HORIZON_PROMO_SCENE_IDS],
            "horizon_claim_boundary": "directional_future_shelf_not_current_release_truth",
            "magicfit_claim_allowed": False,
            "provider_claim": "none",
            "proof_constraints": [
                "MagicFit render claim requires provider and scene receipts; otherwise label first-party motion storyboard"
            ],
        }

    def valid_rule_authority_minimum_coverage(self):
        blocked = {
            "status": "fail",
            "final_verdict": "NOT_READY",
            "expected_ready_verdict": "SR4_RULE_AUTHORITY_READY",
            "full_completion_rule_authority_ready": False,
            "operator_gold_status": "fail",
            "human_review_status": {
                "pending_review": True,
                "review_ready": False,
            },
            "verification_matrix_status": "blocked",
            "verification_matrix_unexpected_failed_gates": [],
            "verification_matrix_expected_ready_blockers": ["SR4-G013"],
            "remaining_gates": ["human rule review signoff"],
        }
        return {
            "status": "fail",
            "rulesets": {
                "sr4": dict(blocked),
                "sr5": {
                    "status": "pass",
                    "final_verdict": "SR5_RULE_AUTHORITY_READY",
                },
                "sr6": {
                    **blocked,
                    "expected_ready_verdict": "SR6_RULE_AUTHORITY_READY",
                    "verification_matrix_expected_ready_blockers": ["SR6-G012"],
                },
            },
        }


if __name__ == "__main__":
    unittest.main()
