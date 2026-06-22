import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_every_wonder_horizon_promo.py"
SPEC = importlib.util.spec_from_file_location("build_every_wonder_horizon_promo", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class EveryWonderHorizonPromoTests(unittest.TestCase):
    def test_production_sheet_is_twelve_scene_ninety_second_horizon_reel(self) -> None:
        self.assertEqual(len(MODULE.SCENES), 12)
        self.assertEqual(sum(MODULE.SCENE_DURATIONS), 90.0)
        self.assertEqual(len(MODULE.scene_timing()), 12)
        self.assertEqual(MODULE.SCENES[0]["id"], "opener_table_remembers")
        self.assertEqual(MODULE.SCENES[1]["id"], "proof_boundary")
        self.assertEqual(MODULE.SCENES[-1]["id"], "finale_all_horizons")

        horizons = {str(scene["horizon"]) for scene in MODULE.SCENES}
        for horizon in (
            "NEXUS-PAN",
            "ALICE",
            "KARMA FORGE",
            "JACKPOINT",
            "RUNSITE",
            "RUNBOOK PRESS",
            "TABLE PULSE",
            "BLACK LEDGER",
            "COMMUNITY HUB",
        ):
            self.assertIn(horizon, horizons)

    def test_claim_boundary_requires_honest_magicfit_receipt_before_claim(self) -> None:
        self.assertIn(
            "MagicFit render claim requires provider and scene receipts; otherwise label first-party motion storyboard",
            MODULE.PROOF_CONSTRAINTS,
        )
        self.assertIn("No official Shadowrun logos", MODULE.NEGATIVE_PROMPT)
        self.assertIn("no real brand logos", MODULE.GLOBAL_MAGICFIT_PROMPT)


if __name__ == "__main__":
    unittest.main()
