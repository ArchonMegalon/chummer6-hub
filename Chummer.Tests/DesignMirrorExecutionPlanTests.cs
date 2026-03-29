using Xunit;

namespace Chummer.Tests;

public sealed class DesignMirrorExecutionPlanTests
{
    [Fact]
    public void CurrentWaveArtifactsAreLinkedFromDesignFrontDoor()
    {
        string readmePath = RepoPaths.FromRoot(".codex-design", "product", "README.md");
        string startHerePath = RepoPaths.FromRoot(".codex-design", "product", "START_HERE.md");

        string readme = File.ReadAllText(readmePath);
        string startHere = File.ReadAllText(startHerePath);

        Assert.Contains("NEXT_20_BIG_WINS_AFTER_POST_AUDIT_CLOSEOUT_GUIDE.md", readme, StringComparison.Ordinal);
        Assert.Contains("CAMPAIGN_OS_GAP_AND_CHANGE_GUIDE.md", readme, StringComparison.Ordinal);
        Assert.Contains("PRIVACY_AND_RETENTION_BOUNDARIES.md", readme, StringComparison.Ordinal);
        Assert.Contains("PUBLIC_TRUST_CONTENT.yaml", readme, StringComparison.Ordinal);
        Assert.Contains("NEXT_20_BIG_WINS_AFTER_POST_AUDIT_CLOSEOUT_GUIDE.md", startHere, StringComparison.Ordinal);
        Assert.Contains("CAMPAIGN_OS_GAP_AND_CHANGE_GUIDE.md", startHere, StringComparison.Ordinal);
        Assert.Contains("PRIVACY_AND_RETENTION_BOUNDARIES.md", startHere, StringComparison.Ordinal);
        Assert.DoesNotContain("NINE_MONTH_EXECUTION_PLAN.md", readme, StringComparison.Ordinal);
        Assert.DoesNotContain("NINE_MONTH_EXECUTION_REGISTRY.yaml", readme, StringComparison.Ordinal);
        Assert.DoesNotContain("NINE_MONTH_EXECUTION_PLAN.md", startHere, StringComparison.Ordinal);
        Assert.DoesNotContain("NINE_MONTH_EXECUTION_REGISTRY.yaml", startHere, StringComparison.Ordinal);
    }

    [Fact]
    public void WeeklyPulseTracksCurrentWaveWithoutRetiredNineMonthOverlay()
    {
        string pulsePath = RepoPaths.FromRoot(".codex-design", "product", "WEEKLY_PRODUCT_PULSE.generated.json");
        string pulse = File.ReadAllText(pulsePath);

        string[] requiredTokens =
        [
            "\"contract_name\": \"chummer.weekly_product_pulse\"",
            "\"active_wave\": \"Next 20 Big Wins After Post-Audit Closeout\"",
            "\"active_wave_registry\": \"products/chummer/NEXT_20_BIG_WINS_AFTER_POST_AUDIT_CLOSEOUT_REGISTRY.yaml\"",
            "\"journey_gate_health\"",
            "\"closure_health\"",
            "\"adoption_health\"",
            "\"progress_trend\"",
            "\"next_checkpoint_question\""
        ];

        foreach (string requiredToken in requiredTokens)
        {
            Assert.Contains(requiredToken, pulse, StringComparison.Ordinal);
        }
        Assert.DoesNotContain("active_nine_month_checkpoint", pulse, StringComparison.Ordinal);
        Assert.DoesNotContain("NINE_MONTH_EXECUTION_REGISTRY.yaml", pulse, StringComparison.Ordinal);
    }

    [Fact]
    public void ScorecardNoLongerRequiresRetiredNineMonthCheckpointFields()
    {
        string scorecardPath = RepoPaths.FromRoot(".codex-design", "product", "PRODUCT_HEALTH_SCORECARD.yaml");

        string scorecard = File.ReadAllText(scorecardPath);

        Assert.DoesNotContain("active_nine_month_checkpoint", scorecard, StringComparison.Ordinal);
        Assert.DoesNotContain("NINE_MONTH_EXECUTION_REGISTRY.yaml", scorecard, StringComparison.Ordinal);
        Assert.Contains("next_checkpoint_question", scorecard, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicGuideExportManifestUsesHorizonRegistryFieldNames()
    {
        string manifestPath = RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_GUIDE_EXPORT_MANIFEST.yaml");
        string registryPath = RepoPaths.FromRoot(".codex-design", "product", "HORIZON_REGISTRY.yaml");

        string manifest = File.ReadAllText(manifestPath);
        string registry = File.ReadAllText(registryPath);

        Assert.DoesNotContain("public_guide.pain_label", manifest, StringComparison.Ordinal);
        Assert.DoesNotContain("build_path.owning_repos", manifest, StringComparison.Ordinal);
        Assert.Contains("- pain_label", manifest, StringComparison.Ordinal);
        Assert.Contains("- owning_repos", manifest, StringComparison.Ordinal);
        Assert.Contains("pain_label:", registry, StringComparison.Ordinal);
        Assert.Contains("owning_repos:", registry, StringComparison.Ordinal);
    }
}
