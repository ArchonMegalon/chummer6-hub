using Xunit;

namespace Chummer.Tests;

public sealed class DesignMirrorExecutionPlanTests
{
    [Fact]
    public void NineMonthExecutionArtifactsAreLinkedFromDesignFrontDoor()
    {
        string readmePath = RepoPaths.FromRoot(".codex-design", "product", "README.md");
        string startHerePath = RepoPaths.FromRoot(".codex-design", "product", "START_HERE.md");

        string readme = File.ReadAllText(readmePath);
        string startHere = File.ReadAllText(startHerePath);

        Assert.Contains("NINE_MONTH_EXECUTION_PLAN.md", readme, StringComparison.Ordinal);
        Assert.Contains("NINE_MONTH_EXECUTION_REGISTRY.yaml", readme, StringComparison.Ordinal);
        Assert.Contains("NINE_MONTH_EXECUTION_PLAN.md", startHere, StringComparison.Ordinal);
        Assert.Contains("NINE_MONTH_EXECUTION_REGISTRY.yaml", startHere, StringComparison.Ordinal);
    }

    [Fact]
    public void NineMonthExecutionPlanCoversAprilThroughDecember2026()
    {
        string planPath = RepoPaths.FromRoot(".codex-design", "product", "NINE_MONTH_EXECUTION_PLAN.md");
        string plan = File.ReadAllText(planPath);

        string[] requiredTokens =
        [
            "April 2026",
            "May 2026",
            "June 2026",
            "July 2026",
            "August 2026",
            "September 2026",
            "October 2026",
            "November 2026",
            "December 2026",
            "NEXT_20_BIG_WINS_AFTER_POST_AUDIT_CLOSEOUT_GUIDE.md",
            "CAMPAIGN_OS_GAP_AND_CHANGE_GUIDE.md"
        ];

        foreach (string requiredToken in requiredTokens)
        {
            Assert.Contains(requiredToken, plan, StringComparison.Ordinal);
        }
    }

    [Fact]
    public void NineMonthExecutionRegistryTracksNineMonthlyCheckpoints()
    {
        string registryPath = RepoPaths.FromRoot(".codex-design", "product", "NINE_MONTH_EXECUTION_REGISTRY.yaml");
        string registry = File.ReadAllText(registryPath);

        string[] requiredTokens =
        [
            "start_month: 2026-04",
            "end_month: 2026-12",
            "NEXT_20_BIG_WINS_AFTER_POST_AUDIT_CLOSEOUT_REGISTRY.yaml",
            "GOLDEN_JOURNEY_RELEASE_GATES.yaml",
            "- id: 2026-04",
            "- id: 2026-05",
            "- id: 2026-06",
            "- id: 2026-07",
            "- id: 2026-08",
            "- id: 2026-09",
            "- id: 2026-10",
            "- id: 2026-11",
            "- id: 2026-12"
        ];

        foreach (string requiredToken in requiredTokens)
        {
            Assert.Contains(requiredToken, registry, StringComparison.Ordinal);
        }
    }

    [Fact]
    public void WeeklyPulseAndScorecardReferenceActiveNineMonthCheckpoint()
    {
        string scorecardPath = RepoPaths.FromRoot(".codex-design", "product", "PRODUCT_HEALTH_SCORECARD.yaml");
        string pulsePath = RepoPaths.FromRoot(".codex-design", "product", "WEEKLY_PRODUCT_PULSE.generated.json");

        string scorecard = File.ReadAllText(scorecardPath);
        string pulse = File.ReadAllText(pulsePath);

        Assert.Contains("active_nine_month_checkpoint", scorecard, StringComparison.Ordinal);
        Assert.Contains("NINE_MONTH_EXECUTION_REGISTRY.yaml", scorecard, StringComparison.Ordinal);
        Assert.Contains("\"active_nine_month_checkpoint\"", pulse, StringComparison.Ordinal);
        Assert.Contains("NINE_MONTH_EXECUTION_REGISTRY.yaml", pulse, StringComparison.Ordinal);
        Assert.Contains("\"id\": \"2026-04\"", pulse, StringComparison.Ordinal);
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
