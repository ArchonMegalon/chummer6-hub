import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/verify_table_pulse_scenario_replay.py")


def load_module():
    spec = importlib.util.spec_from_file_location("verify_table_pulse_scenario_replay", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TablePulseScenarioReplayGateTests(unittest.TestCase):
    def test_gate_fails_without_scenario_receipt(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="table-pulse-fail-") as temp_dir:
            output = Path(temp_dir) / "TABLE_PULSE_SCENARIO_REPLAY.generated.json"
            ok = {"command": "x", "returncode": 0, "stdout": "ok", "stderr": "", "pass": True}
            with mock.patch.object(module, "OUTPUT_PATH", output), mock.patch.object(module, "FLEET_RECEIPT", Path(temp_dir) / "missing.json"), mock.patch.object(module, "run_command", return_value=ok):
                with self.assertRaises(SystemExit):
                    with mock.patch("sys.argv", ["verify_table_pulse_scenario_replay.py"]):
                        module.main()

    def test_gate_passes_with_live_lane_and_receipt(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="table-pulse-pass-") as temp_dir:
            output = Path(temp_dir) / "TABLE_PULSE_SCENARIO_REPLAY.generated.json"
            receipt = Path(temp_dir) / "TABLE_PULSE_SCENARIO_REPLAY.generated.json"
            receipt.write_text("{}", encoding="utf-8")
            ok = {"command": "x", "returncode": 0, "stdout": "ok", "stderr": "", "pass": True}
            with mock.patch.object(module, "OUTPUT_PATH", output), mock.patch.object(module, "FLEET_RECEIPT", receipt), mock.patch.object(module, "run_command", return_value=ok):
                with mock.patch("sys.argv", ["verify_table_pulse_scenario_replay.py"]):
                    self.assertEqual(module.main(), 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "pass")


if __name__ == "__main__":
    unittest.main()
