from __future__ import annotations

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICE_PATH = REPO_ROOT / "Chummer.Run.Api" / "Services" / "ReleaseBundlePromotionService.cs"


class ReleaseBundlePromotionShelfReplacementTests(unittest.TestCase):
    def test_promotion_activates_registry_manifests_without_rederiving_them(self) -> None:
        text = SERVICE_PATH.read_text(encoding="utf-8")
        promotion_start = text.index("private Task<ReleaseBundlePromotionResult> PromotePreparedBundleAsync(")
        promotion_end = text.index("\n    private string ResolveDownloadsRoot()", promotion_start)
        promotion_body = text[promotion_start:promotion_end]

        self.assertIn("ValidateRegistryAuthoredManifestPair(", promotion_body)
        self.assertIn("incomingCompatibilityBytes = prepared.CompatibilityManifestBytes", promotion_body)
        self.assertIn("incomingCanonicalBytes = prepared.CanonicalManifestBytes", promotion_body)
        self.assertIn("compatibilityManifestSha256 = Sha256For(incomingCompatibilityBytes)", promotion_body)
        self.assertIn("canonicalManifestSha256 = Sha256For(incomingCanonicalBytes)", promotion_body)
        self.assertNotIn("NormalizeMergedShelfProjection(", promotion_body)
        self.assertNotIn("MergeCompatibilityManifest(", promotion_body)
        self.assertNotIn("MergeCanonicalManifest(", promotion_body)

        stage_start = text.index("private static void PrepareStagedShelf(")
        stage_end = text.index("\n    private static void RewritePayloadSidecarsForGeneration(", stage_start)
        stage_body = text[stage_start:stage_end]
        self.assertIn("compatibilityManifestBytes", stage_body)
        self.assertIn("canonicalManifestBytes", stage_body)
        self.assertIn("File.WriteAllBytes(", stage_body)
        self.assertNotIn("NormalizeManifestForGeneration(", stage_body)

    def test_activation_is_digest_bound_and_enforces_registry_platform_floor(self) -> None:
        text = SERVICE_PATH.read_text(encoding="utf-8")

        self.assertIn('private const string RegistryContractName = "Chummer.Hub.Registry.Contracts";', text)
        self.assertIn('private const string ActivationCandidateName = "activation-candidate.json";', text)
        self.assertIn('private const string CurrentPointerName = "current.json";', text)
        self.assertIn('private static readonly string[] RequiredDesktopPlatforms = ["linux", "windows", "macos"];', text)
        self.assertIn('"avalonia:linux-x64:linux"', text)
        self.assertIn('"avalonia:osx-arm64:macos"', text)
        self.assertIn('"avalonia:win-x64:windows"', text)
        self.assertIn("FixedTimeDigestEquals(Sha256For(liveCompatibilityManifestPath), expectedCompatibilitySha256)", text)
        self.assertIn("FixedTimeDigestEquals(Sha256For(liveCanonicalManifestPath), expectedCanonicalSha256)", text)
        self.assertIn('CanonicalManifestSha256: $"sha256:{canonicalManifestSha256}"', text)
        validation_index = text.index("ValidateRegistryBoundaryCompatibilityCounts(liveCompatibilityManifest, liveCanonicalManifest);")
        policy_index = text.index("return releaseSelection.ApplyAccessPolicy(liveCompatibilityManifest);")
        self.assertLess(
            validation_index,
            policy_index,
            "registry boundary counts must be validated against the unfiltered live manifest before access-policy filtering",
        )


if __name__ == "__main__":
    unittest.main()
