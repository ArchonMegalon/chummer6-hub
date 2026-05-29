from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = REPO_ROOT / "Chummer.Run.Api" / "Services" / "ReleaseBundlePromotionService.cs"


class ReleaseBundlePromotionShelfReplacementTests(unittest.TestCase):
    def test_promotion_replaces_manifest_shelf_rows_instead_of_merging_prior_artifacts(self) -> None:
        text = SERVICE_PATH.read_text(encoding="utf-8")

        self.assertIn("private static PublicReleaseManifestDto MergeCompatibilityManifest(", text)
        self.assertIn("return incomingManifest;", text)
        self.assertIn("private static JsonObject MergeCanonicalManifest(JsonObject? existingManifest, JsonObject incomingManifest)", text)
        self.assertIn("return incomingManifest.DeepClone().AsObject();", text)
        self.assertNotIn('merged["artifacts"] = MergeArrayById(', text)
        self.assertNotIn("Downloads = mergedDownloads", text)


if __name__ == "__main__":
    unittest.main()
