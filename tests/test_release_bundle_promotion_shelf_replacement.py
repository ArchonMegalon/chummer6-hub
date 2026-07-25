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

    def test_promotion_normalizes_registry_boundary_compatibility_counts(self) -> None:
        text = SERVICE_PATH.read_text(encoding="utf-8")

        self.assertIn("NormalizeRegistryBoundaryCoverage(", text)
        self.assertIn("RegistryBoundaryCoverage = JsonSerializer.SerializeToElement(registryBoundaryCoverage, JsonOptions)", text)
        self.assertIn('compatibility["compatibleArtifactCount"] = publishedArtifactCount;', text)
        self.assertIn('compatibility["unknownArtifactCount"] = 0;', text)
        validation_index = text.index("ValidateRegistryBoundaryCompatibilityCounts(liveCompatibilityManifest, liveCanonicalManifest);")
        authoritative_return_index = text.index("return liveCompatibilityManifest;", validation_index)
        self.assertLess(
            validation_index,
            authoritative_return_index,
            "registry boundary counts must be validated against the complete authoritative manifest before it is returned",
        )
        self.assertNotIn(
            "ApplyAccessPolicy(",
            text,
            "promotion must not apply request-time visibility policy to the authoritative release shelf",
        )
        self.assertIn(
            "dist/releases.json preview_supported release must keep registryBoundaryCoverage.compatibility.compatibleArtifactCount equal to published artifact count",
            text,
        )

    def test_release_channel_summary_rebuilds_public_trust_counts_from_route_truth(self) -> None:
        text = SERVICE_PATH.read_text(encoding="utf-8")

        self.assertIn('JsonObject adoptionHealth = metrics["adoptionHealth"] as JsonObject ?? new JsonObject();', text)
        self.assertIn('JsonObject revocationFacts = metrics["revocationFacts"] as JsonObject ?? new JsonObject();', text)
        self.assertIn("List<JsonObject> recommendedRoutes = rows", text)
        self.assertIn("List<JsonObject> fallbackRoutes = rows", text)
        self.assertIn("List<JsonObject> blockedRoutes = rows", text)
        self.assertIn('releaseChannel["fallbackRecoveryRouteCount"] = fallbackRouteCount;', text)
        self.assertIn('adoptionHealth["primaryPromotedCount"] = recommendedRouteCount;', text)
        self.assertIn('adoptionHealth["fallbackRecoveryCount"] = fallbackRouteCount;', text)
        self.assertIn('adoptionHealth["blockedRouteCount"] = blockedRouteCount;', text)
        self.assertIn('revocationFacts["activeRevocationCount"] = revokedRouteCount;', text)
        self.assertIn('metrics["adoptionHealth"] = adoptionHealth;', text)
        self.assertIn('metrics["revocationFacts"] = revocationFacts;', text)
        self.assertIn("private static bool RouteTruthIsFallbackRecovery(JsonObject row)", text)
        self.assertIn("private static bool RouteTruthIsBlocked(JsonObject row)", text)
        self.assertIn("private static bool ProofFreshnessBlocksOutputReadiness(string proofFreshnessStatus)", text)
        self.assertIn("private static int GetMetricCount(JsonObject? section, string propertyName, int fallbackValue)", text)


if __name__ == "__main__":
    unittest.main()
