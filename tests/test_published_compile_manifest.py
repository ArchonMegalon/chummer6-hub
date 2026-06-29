import importlib.util
import json
import unittest
from pathlib import Path


REPO_ROOT = Path("/docker/chummercomplete/chummer.run-services")
FINAL_GOLD_JANITOR_PATH = REPO_ROOT / "scripts" / "final_gold_janitor.py"
MANIFEST_PATH = REPO_ROOT / ".codex-studio" / "published" / "compile.manifest.json"


def load_final_gold_janitor():
    spec = importlib.util.spec_from_file_location("final_gold_janitor", FINAL_GOLD_JANITOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublishedCompileManifestTests(unittest.TestCase):
    def test_manifest_lists_all_published_final_gold_receipts(self) -> None:
        final_gold = load_final_gold_janitor()
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        artifacts = set(manifest["artifacts"])

        required = {
            path.name
            for path in final_gold.REQUIRED_RECEIPTS.values()
            if path.parent == final_gold.PUBLISHED_ROOT
        }
        required.add("ICANPRENEUR_DISCOVERY_LANE.generated.json")
        required.update(
            {
                "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.generated.json",
                "MOBILE_PWA_PUBLIC_PROJECTION_AUDIT.md",
            }
        )

        missing = sorted(required - artifacts)
        self.assertFalse(missing, f"compile manifest is missing published proof artifacts: {missing}")

    def test_manifest_entries_exist_on_disk(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

        missing = [
            artifact
            for artifact in manifest["artifacts"]
            if not (MANIFEST_PATH.parent / artifact).is_file()
        ]
        self.assertFalse(missing, f"compile manifest references missing artifacts: {missing}")


if __name__ == "__main__":
    unittest.main()
