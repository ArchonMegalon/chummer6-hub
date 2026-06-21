import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/materialize_ltd_optimization_stack.py")


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_ltd_optimization_stack", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LtdOptimizationStackTests(unittest.TestCase):
    def test_stack_includes_bounded_icanpreneur_lane(self) -> None:
        module = load_module()
        payload = module.build_payload()

        self.assertEqual(payload["status"], "pass", payload["failures"])
        check = payload["checks"]["icanpreneur_discovery_interview"]
        self.assertTrue(check["pass"])
        self.assertEqual(check["status"], "tracked")
        self.assertEqual(check["lane_status"], "pass")
        self.assertEqual(check["license_tier"], "Tier 3")
        self.assertFalse(check["runtime_ready"])


if __name__ == "__main__":
    unittest.main()
