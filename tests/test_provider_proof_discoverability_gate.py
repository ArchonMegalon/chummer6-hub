import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/verify_provider_proof_discoverability.py")


def load_module():
    spec = importlib.util.spec_from_file_location("verify_provider_proof_discoverability", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProviderProofDiscoverabilityGateTests(unittest.TestCase):
    def test_gate_fails_when_required_artifacts_are_missing(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="provider-proof-missing-") as temp_dir:
            root = Path(temp_dir)
            output = root / "PROVIDER_PROOF_DISCOVERABILITY.generated.json"
            with mock.patch.object(module, "FLEET_COMPLETION_ROOT", root), mock.patch.object(module, "OUTPUT_PATH", output), mock.patch.object(module, "MIRROR_ROOT", root / "mirror"):
                with self.assertRaises(SystemExit):
                    module.main()

    def test_gate_mirrors_discoverable_artifacts(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="provider-proof-pass-") as temp_dir:
            root = Path(temp_dir)
            for provider, paths in module.required_artifacts().items():
                for path in paths:
                    source = root / path.relative_to(module.FLEET_COMPLETION_ROOT)
                    source.parent.mkdir(parents=True, exist_ok=True)
                    source.write_text("{}", encoding="utf-8")
            output = root / "PROVIDER_PROOF_DISCOVERABILITY.generated.json"
            mirror = root / "mirror"
            with mock.patch.object(module, "FLEET_COMPLETION_ROOT", root), mock.patch.object(module, "OUTPUT_PATH", output), mock.patch.object(module, "MIRROR_ROOT", mirror):
                self.assertEqual(module.main(), 0)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "pass")


if __name__ == "__main__":
    unittest.main()
