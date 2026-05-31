import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/audit_full_product_reaudit_v16_gate_semantics.py")
SPEC = importlib.util.spec_from_file_location("audit_full_product_reaudit_v16_gate_semantics", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def statuses(checks):
    return {check["name"]: check["status"] for check in checks}


class FullProductReauditV16GateSemanticTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
