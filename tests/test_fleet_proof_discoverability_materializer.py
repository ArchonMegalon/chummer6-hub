from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "materialize_fleet_proof_discoverability_mirrors.py"


class FleetProofDiscoverabilityMaterializerTests(unittest.TestCase):
    def test_materializes_magicfit_black_ledger_and_table_pulse(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fleet_root = root / "fleet"
            published_root = root / "published"
            magicfit_root = root / "magicfit_provider"
            legacy_root = root / "legacy"

            (magicfit_root / "FINAL_MAGICFIT_PROVIDER_ADAPTER_VERDICT.md").parent.mkdir(parents=True, exist_ok=True)
            (magicfit_root / "FINAL_MAGICFIT_PROVIDER_ADAPTER_VERDICT.md").write_text("MAGICFIT_PROVIDER_ADAPTER_READY\n", encoding="utf-8")
            (magicfit_root / "MAGICFIT_PROVIDER_VERIFICATION.generated.json").write_text(
                json.dumps({"status": "verified"}, indent=2),
                encoding="utf-8",
            )

            screenshot = published_root / "shots" / "ledger-map.png"
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            screenshot.write_bytes(b"png")
            (published_root / "BLACK_LEDGER_LIVE_MEDIA_PROOF.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "screenshots": [
                            {
                                "route": "/ledger/map",
                                "viewport": "desktop",
                                "screenshotPath": str(screenshot),
                            }
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (published_root / "PWA_TABLE_PULSE_SCENARIO_RECEIPTS.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "scenarios": [
                            {"id": "pwa_subscription_delivery_click", "result": "pass"},
                            {"id": "table_pulse_remote_reaction_gm_adjudication", "result": "pass"},
                        ],
                        "private_campaign_data_captured": False,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            (legacy_root / "TABLE_PULSE_SCENARIO_REPLAY.generated.json").parent.mkdir(parents=True, exist_ok=True)
            (legacy_root / "TABLE_PULSE_SCENARIO_REPLAY.generated.json").write_text(
                json.dumps(
                    {
                        "status": "pass",
                        "required_steps": ["remote-notification", "gm-adjudication"],
                        "covered_steps": {"remote-notification": True, "gm-adjudication": True},
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["CHUMMER_RUN_SERVICES_PUBLISHED_ROOT"] = str(published_root)
            env["CHUMMER_FLEET_COMPLETION_ROOT"] = str(fleet_root)
            env["CHUMMER_MAGICFIT_PROVIDER_ROOT"] = str(magicfit_root)
            env["CHUMMER_LEGACY_REAUDIT_ROOT"] = str(legacy_root)
            completed = subprocess.run(
                ["python3", str(SCRIPT)],
                cwd=REPO_ROOT,
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)

            self.assertTrue((fleet_root / "magicfit" / "FINAL_MAGICFIT_PROVIDER_ADAPTER_VERDICT.md").is_file())
            self.assertTrue((fleet_root / "black_ledger" / "BLACK_LEDGER_LIVE_MEDIA_PROOF.generated.json").is_file())
            self.assertTrue((fleet_root / "table_pulse" / "TABLE_PULSE_SCENARIO_REPLAY.generated.json").is_file())
            payload = json.loads((fleet_root / "table_pulse" / "TABLE_PULSE_SCENARIO_REPLAY.generated.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "pass")


if __name__ == "__main__":
    unittest.main()
