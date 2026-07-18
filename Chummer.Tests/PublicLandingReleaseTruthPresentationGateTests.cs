using System.Text.Json;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.PublicSurface;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingReleaseTruthPresentationGateTests
{
    [Theory]
    [InlineData("stale", "preview_supported", "promoted_preview")]
    [InlineData("missing", "preview_supported", "promoted_preview")]
    [InlineData("fresh", "review_required", "public_release_review_required")]
    public void NonLaunchableCanonicalTruthOverridesOptimisticPulseClaims(
        string proofFreshnessStatus,
        string supportabilityState,
        string rolloutState)
    {
        PublicReleaseManifestDto manifest = BuildManifest(
            proofFreshnessStatus,
            supportabilityState,
            rolloutState);

        PublicLandingController.ReleaseTruthPresentationGate gate =
            PublicLandingController.BuildReleaseTruthPresentationGate(manifest);
        PublicTrustPulsePanelViewModel panel =
            PublicLandingController.BuildReleaseTruthGatedPulsePanel(manifest, gate);

        Assert.True(gate.ReviewRequired);
        Assert.Equal("Release review required", panel.Heading);
        Assert.True(panel.ParityClaimsReviewRequired);
        Assert.Empty(panel.TrendSamples);
        Assert.DoesNotContain(panel.Rows, row => row.Label is "Progress trend" or "Journey pulse" or "Closure health");
        Assert.Contains("claims are withheld", panel.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("paused", panel.Rows.Single(row => row.Label == "Launch readiness").Value, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(
            "100%",
            string.Join(" ", panel.MicroProof.Concat(panel.Rows.Select(row => row.Value))),
            StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void FreshSupportedCanonicalTruthDoesNotGateTheWeeklyPulse()
    {
        PublicReleaseManifestDto manifest = BuildManifest(
            proofFreshnessStatus: "fresh",
            supportabilityState: "preview_supported",
            rolloutState: "promoted_preview");

        PublicLandingController.ReleaseTruthPresentationGate gate =
            PublicLandingController.BuildReleaseTruthPresentationGate(manifest);

        Assert.False(gate.ReviewRequired);
        Assert.Equal("fresh", gate.ProofFreshnessStatus);
        Assert.Empty(gate.Summary);
    }

    private static PublicReleaseManifestDto BuildManifest(
        string proofFreshnessStatus,
        string supportabilityState,
        string rolloutState)
        => new(
            Version: "run-20260718-000000",
            Channel: "preview",
            PublishedAt: DateTimeOffset.Parse("2026-07-18T00:00:00Z"),
            Downloads:
            [
                new PublicReleaseArtifactDto(
                    Id: "avalonia-win-x64-installer",
                    Platform: "windows",
                    Url: "/downloads/g/current/files/chummer.exe",
                    Sha256: new string('a', 64),
                    SizeBytes: 42,
                    Head: "avalonia",
                    Arch: "x64",
                    FileName: "chummer.exe")
            ],
            RolloutState: rolloutState,
            SupportabilityState: supportabilityState,
            ProofStatus: "passed")
        {
            PublicTrustMetrics = JsonSerializer.SerializeToElement(new
            {
                proofFreshness = new { status = proofFreshnessStatus }
            })
        };
}
