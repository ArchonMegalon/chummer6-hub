import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/verify_rules_authority_minimum_coverage.py")


def load_module():
    spec = importlib.util.spec_from_file_location("verify_rules_authority_minimum_coverage", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
            output = root / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json"
            with mock.patch.object(module, "CORE_ENGINE_ROOT", root), mock.patch.object(module, "OUTPUT_PATH", output):
                with self.assertRaises(SystemExit):
                    with mock.patch("sys.argv", ["verify_rules_authority_minimum_coverage.py", "--min-rulefacts", "100"]):
                        module.main()

    def test_gate_passes_at_threshold(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="rules-min-pass-") as temp_dir:
            root = Path(temp_dir)
            for name in ("SR4_RULEFACT_REGISTRY.generated.json", "SR5_RULE_AUTHORITY_REGISTRY.generated.json", "SR6_RULEFACT_REGISTRY.generated.json"):
                (root / ".codex-studio" / "published").mkdir(parents=True, exist_ok=True)
                (root / ".codex-studio" / "published" / name).write_text(
                    json.dumps({"rulefact_count": 120, "final_verdict": "SR_READY"}),
                    encoding="utf-8",
                )
            output = root / "RULE_AUTHORITY_MINIMUM_COVERAGE.generated.json"
            with mock.patch.object(module, "CORE_ENGINE_ROOT", root), mock.patch.object(module, "OUTPUT_PATH", output):
                with mock.patch("sys.argv", ["verify_rules_authority_minimum_coverage.py", "--min-rulefacts", "100"]):
                    self.assertEqual(module.main(), 0)


if __name__ == "__main__":
    unittest.main()
