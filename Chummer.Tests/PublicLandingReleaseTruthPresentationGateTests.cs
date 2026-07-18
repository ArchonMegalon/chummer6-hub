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
    public void ReviewRequiredHelpCopyCannotRenderOptimisticAvailability()
    {
        PublicReleaseManifestDto manifest = BuildManifest(
            proofFreshnessStatus: "fresh",
            supportabilityState: "preview_supported",
            rolloutState: "promoted_preview");
        var releaseTruth = new PublicReleaseTruthProjectionDto(
            ContractName: PublicReleaseTruthProjectionDto.Schema,
            ReleaseVersion: "run-authority-20260718",
            Channel: "preview",
            ReleaseStatus: "published",
            RolloutState: "promoted_preview",
            SupportabilityState: "preview_supported",
            AvailablePlatforms: ["windows"],
            PrimaryHeadByPlatform: new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["windows"] = "avalonia"
            },
            ArtifactCount: 2,
            DownloadAccessPosture: "open_public",
            KnownIssueSummary: "Immutable release review remains open.",
            ManifestSha256: new string('a', 64),
            RegistryCommit: new string('b', 40),
            ReleaseDecisionStatus: "review_required",
            ReleaseDecisionSha256: new string('c', 64));
        PublicLandingController.ReleaseTruthPresentationGate gate =
            PublicLandingController.BuildReleaseTruthPresentationGate(manifest, releaseTruth);
        PublicTrustPulsePanelViewModel pulse =
            PublicLandingController.BuildReleaseTruthGatedPulsePanel(manifest, gate, releaseTruth);
        var optimisticSignedInStatus = new SignedInTrustStatusPanelViewModel(
            Eyebrow: "Signed-in trust status",
            Heading: "Your linked install can verify a fix now",
            Summary: "Preview builds are available for this linked install.",
            Rows:
            [
                new("Who can get it now", "Preview builds are available."),
                new("Recommended for this install", "Install the promoted preview now."),
                new("Install status", "This install matches the promoted release."),
                new("Fix availability", "This install can verify the fix now."),
                new("Current caution", "No extra caution is needed."),
                new("Release checks", "Passed")
            ],
            PrimaryAction: new TrustPageActionViewModel("Verify fix on this install", "/account/support/case-1", "primary"));

        SignedInTrustStatusPanelViewModel signedInStatus = Assert.IsType<SignedInTrustStatusPanelViewModel>(
            PublicLandingController.RebindSignedInTrustStatusToReleaseTruth(
                optimisticSignedInStatus,
                releaseTruth,
                gate));

        string pulseText = string.Join(" ", pulse.MicroProof.Concat(pulse.Rows.Select(row => row.Value)));
        string signedInText = string.Join(
            " ",
            new[] { signedInStatus.Heading, signedInStatus.Summary }
                .Concat(signedInStatus.Rows.Select(row => row.Value)));
        Assert.True(gate.ReviewRequired);
        Assert.Contains("2 authority-listed installers", pulseText, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("availability is not asserted", pulseText, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("availability is not asserted", signedInText, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("review required", signedInStatus.Heading, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Preview builds are available", signedInText, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("can verify", signedInText, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("matches the promoted", signedInText, StringComparison.OrdinalIgnoreCase);
        Assert.Equal("/downloads", signedInStatus.PrimaryAction.Href);
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

    [Theory]
    [InlineData("absent_metrics")]
    [InlineData("missing_freshness")]
    [InlineData("blank_status")]
    public void AbsentFreshnessTruthFailsClosedInsteadOfPublishingOptimism(string variant)
    {
        PublicReleaseManifestDto manifest = BuildManifest(
            proofFreshnessStatus: "fresh",
            supportabilityState: "preview_supported",
            rolloutState: "promoted_preview");
        manifest = variant switch
        {
            "absent_metrics" => manifest with { PublicTrustMetrics = null },
            "missing_freshness" => manifest with
            {
                PublicTrustMetrics = JsonSerializer.SerializeToElement(new
                {
                    releaseChannel = new { supportabilityState = "preview_supported" }
                })
            },
            "blank_status" => manifest with
            {
                PublicTrustMetrics = JsonSerializer.SerializeToElement(new
                {
                    proofFreshness = new { status = " " }
                })
            },
            _ => throw new ArgumentOutOfRangeException(nameof(variant), variant, null)
        };

        PublicLandingController.ReleaseTruthPresentationGate gate =
            PublicLandingController.BuildReleaseTruthPresentationGate(manifest);

        Assert.True(gate.ReviewRequired);
        Assert.Equal("missing", gate.ProofFreshnessStatus);
        Assert.Contains("freshness is missing", gate.Summary, StringComparison.OrdinalIgnoreCase);
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
