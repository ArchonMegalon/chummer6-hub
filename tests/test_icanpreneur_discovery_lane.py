import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/verify_icanpreneur_discovery_lane.py")


def load_module():
    spec = importlib.util.spec_from_file_location("verify_icanpreneur_discovery_lane", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class IcanpreneurDiscoveryLaneTests(unittest.TestCase):
    def test_lane_receipt_proves_bounded_internal_integration(self) -> None:
        module = load_module()
        payload = module.build_payload()

        self.assertEqual(payload["status"], "pass", payload["failures"])
        self.assertFalse(payload["runtime_ready"])
        self.assertEqual(payload["checks"]["inventory_lane"]["status"], "pass")
        self.assertEqual(payload["checks"]["credential_catalog"]["status"], "pass")
        self.assertEqual(payload["checks"]["karma_forge_handoff"]["status"], "pass")
        self.assertEqual(payload["checks"]["public_copy_quiet"]["status"], "pass")
        self.assertIn("rules truth", payload["claim_boundary"])
        self.assertIn("publication approval", payload["claim_boundary"])

    def test_main_writes_receipt_to_configured_output_path(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="icanpreneur-lane-") as temp_dir:
            output = Path(temp_dir) / "ICANPRENEUR_DISCOVERY_LANE.generated.json"
            with mock.patch.object(module, "OUTPUT_PATH", output):
                self.assertEqual(module.main(), 0)

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "pass")
            self.assertEqual(payload["checks"]["public_leak_gates"]["status"], "pass")


if __name__ == "__main__":
    unittest.main()
