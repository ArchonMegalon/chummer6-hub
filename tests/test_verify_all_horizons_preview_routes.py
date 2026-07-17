from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/verify_all_horizons_preview_routes.py")


def load_module():
    spec = importlib.util.spec_from_file_location("verify_all_horizons_preview_routes", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class VerifyAllHorizonsPreviewRoutesTests(unittest.TestCase):
    def test_successful_route_matrix_only_claims_flagship_front_ready(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="all-horizons-preview-routes-") as temp_dir:
            root = Path(temp_dir)
            controller = root / "PublicLandingController.cs"
            manifest = root / "PUBLIC_LANDING_MANIFEST.yaml"
            completion = root / "completion"

            controller.write_text(
                "\n".join(f'[HttpGet("{route}")]' for route, _, _ in module.ROUTES) + "\n",
                encoding="utf-8",
            )
            manifest.write_text(
                "\n".join(f"path: {route}" for route, _, _ in module.ROUTES) + "\n",
                encoding="utf-8",
            )

            with mock.patch.object(module, "CONTROLLER", controller), \
                mock.patch.object(module, "MANIFEST", manifest), \
                mock.patch.object(module, "COMPLETION", completion):
                result = module.main()

            self.assertEqual(0, result)
            verdict_text = (completion / "FINAL_ALL_HORIZONS_FLAGSHIP_VERDICT.md").read_text(encoding="utf-8")
            self.assertTrue(verdict_text.startswith("FLAGSHIP_FRONT_READY\n"))
            self.assertIn("does not prove release-channel stability", verdict_text)
            self.assertNotIn("GLOBAL_FLAGSHIP_READY", verdict_text)


if __name__ == "__main__":
    unittest.main()
