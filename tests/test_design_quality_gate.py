import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/materialize_design_quality_gate.py")


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_design_quality_gate", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DesignQualityGateTests(unittest.TestCase):
    def test_design_gate_requires_bounded_icanpreneur_lane(self) -> None:
        module = load_module()
        payload = module.build_payload()

        check = payload["checks"]["icanpreneur_design_lane"]
        self.assertTrue(check["pass"], payload["failures"])
        self.assertEqual(check["status"], "tracked")
        self.assertEqual(check["lane_status"], "pass")
        self.assertEqual(check["license_tier"], "Tier 3")
        self.assertFalse(check["runtime_ready"])


if __name__ == "__main__":
    unittest.main()
