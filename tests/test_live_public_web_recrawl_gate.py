import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = Path("/docker/chummercomplete/chummer.run-services/scripts/verify_live_public_web_recrawl.py")


def load_module():
    spec = importlib.util.spec_from_file_location("verify_live_public_web_recrawl", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LivePublicWebRecrawlGateTests(unittest.TestCase):
    def test_recrawl_persists_hashes_and_excerpts(self) -> None:
        module = load_module()

        with tempfile.TemporaryDirectory(prefix="live-recrawl-") as temp_dir:
            output_path = Path(temp_dir) / "LIVE_PUBLIC_WEB_RECRAWL.generated.json"
            with mock.patch.object(module, "OUTPUT_PATH", output_path), mock.patch.object(
                module,
                "fetch",
                return_value=(200, "<html><body><h1>Chummer</h1><p>Black Ledger command deck</p></body></html>", {}),
            ):
                payload = module.recrawl("https://example.test")

        self.assertEqual(payload["status"], "pass")
        self.assertEqual(len(payload["results"]), len(load_module().REQUIRED_PATHS))
        self.assertTrue(all(result["sha256"] for result in payload["results"]))
        self.assertTrue(all(result["excerpt"] for result in payload["results"]))

    def test_recrawl_fails_on_forbidden_copy(self) -> None:
        module = load_module()
        with tempfile.TemporaryDirectory(prefix="live-recrawl-forbidden-") as temp_dir:
            output_path = Path(temp_dir) / "LIVE_PUBLIC_WEB_RECRAWL.generated.json"
            with mock.patch.object(module, "OUTPUT_PATH", output_path), mock.patch.object(
                module,
                "fetch",
                return_value=(200, "<html><body>Load Demo Runner</body></html>", {}),
            ):
                payload = module.recrawl("https://example.test")

        self.assertEqual(payload["status"], "fail")
        self.assertTrue(payload["forbidden_hits"])


if __name__ == "__main__":
    unittest.main()
