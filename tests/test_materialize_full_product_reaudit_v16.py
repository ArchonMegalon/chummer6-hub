import importlib.util
import os
import unittest
from pathlib import Path


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/materialize_full_product_reaudit_v16.py")


def load_module():
    spec = importlib.util.spec_from_file_location("materialize_full_product_reaudit_v16", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MaterializeFullProductReauditV16Tests(unittest.TestCase):
    def test_defaults_to_public_route_audit_base(self) -> None:
        previous = os.environ.pop("CHUMMER_FULL_PRODUCT_REAUDIT_BASE_URL", None)
        try:
            module = load_module()
            self.assertEqual(module.BASE_URL, "https://chummer.run")
        finally:
            if previous is not None:
                os.environ["CHUMMER_FULL_PRODUCT_REAUDIT_BASE_URL"] = previous

    def test_base_url_override_is_respected(self) -> None:
        previous = os.environ.get("CHUMMER_FULL_PRODUCT_REAUDIT_BASE_URL")
        os.environ["CHUMMER_FULL_PRODUCT_REAUDIT_BASE_URL"] = "https://example.test/"
        try:
            module = load_module()
            self.assertEqual(module.BASE_URL, "https://example.test")
        finally:
            if previous is None:
                os.environ.pop("CHUMMER_FULL_PRODUCT_REAUDIT_BASE_URL", None)
            else:
                os.environ["CHUMMER_FULL_PRODUCT_REAUDIT_BASE_URL"] = previous

    def test_surface_verify_base_url_defaults_to_local_runtime(self) -> None:
        previous = os.environ.pop("CHUMMER_FULL_PRODUCT_REAUDIT_SURFACE_BASE_URL", None)
        try:
            module = load_module()
            self.assertEqual(module.SURFACE_VERIFY_BASE_URL, "http://127.0.0.1:8091")
        finally:
            if previous is not None:
                os.environ["CHUMMER_FULL_PRODUCT_REAUDIT_SURFACE_BASE_URL"] = previous

    def test_surface_verify_commands_default_to_served_surface_probe(self) -> None:
        previous = os.environ.pop("CHUMMER_FULL_PRODUCT_REAUDIT_SURFACE_BASE_URL", None)
        try:
            module = load_module()
            self.assertEqual(
                module.surface_verify_command("verify_black_ledger_newsroom_surface.py"),
                [
                    "python3",
                    "scripts/verify_black_ledger_newsroom_surface.py",
                    "--base-url",
                    "http://127.0.0.1:8091",
                ],
            )
        finally:
            if previous is not None:
                os.environ["CHUMMER_FULL_PRODUCT_REAUDIT_SURFACE_BASE_URL"] = previous


if __name__ == "__main__":
    unittest.main()
