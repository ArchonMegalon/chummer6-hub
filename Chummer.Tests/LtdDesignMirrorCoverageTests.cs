using Xunit;

namespace Chummer.Tests;

public sealed class LtdDesignMirrorCoverageTests
{
    [Fact]
    public void DesignMirrorAndEaCredentialInventoryStayAligned()
    {
        string toolsPlane = File.ReadAllText(RepoPaths.FromRoot(".codex-design", "product", "EXTERNAL_TOOLS_PLANE.md"));
        string capabilityMap = File.ReadAllText(RepoPaths.FromRoot(".codex-design", "product", "LTD_CAPABILITY_MAP.md"));
        string runtimeRegistry = File.ReadAllText(RepoPaths.FromRoot(".codex-design", "product", "LTD_RUNTIME_AND_PROJECTION_REGISTRY.yaml"));
        string envExample = File.ReadAllText(RepoPaths.FromRoot(".env.example"));
        string ltdInventory = File.ReadAllText(RepoPaths.FromRoot("ltds.md"));

        Assert.Contains("Current known external-tool inventory includes:", toolsPlane, StringComparison.Ordinal);
        Assert.Contains("workspace integration Tier 3, vendor license plan Tier 4", toolsPlane, StringComparison.Ordinal);
        Assert.Contains("runbook-press", toolsPlane, StringComparison.Ordinal);
        Assert.Contains("table-pulse-aftermath", toolsPlane, StringComparison.Ordinal);

        Assert.Contains("`ClickRank` - public site visibility, crawl-health, technical SEO, schema, metadata, and AI-search audit lane", capabilityMap, StringComparison.Ordinal);
        Assert.Contains("`ProductLift` - public feedback, voting, roadmap projection, changelog projection, and voter closeout lane", capabilityMap, StringComparison.Ordinal);
        Assert.Contains("`Documentation.AI` - docs/help projection surface downstream of canon, not first-line crash capture", capabilityMap, StringComparison.Ordinal);

        Assert.Contains("public_growth_system:", runtimeRegistry, StringComparison.Ordinal);
        Assert.Contains("artifact_factory:", runtimeRegistry, StringComparison.Ordinal);
        Assert.Contains("trust_closure_system:", runtimeRegistry, StringComparison.Ordinal);

        Assert.Contains("CHUMMER_EA_BLIPAI_APP_TIER=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_BLIPAI_APP_EMAIL=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_BLIPAI_APP_PASSWORD=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_MAGICFIT_TIER=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_MAGICFIT_EMAIL=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_MAGICFIT_PASSWORD=", envExample, StringComparison.Ordinal);

        Assert.Contains("### blipai.app", ltdInventory, StringComparison.Ordinal);
        Assert.Contains("### magicfit", ltdInventory, StringComparison.Ordinal);
        Assert.DoesNotContain("rangersofB5!", ltdInventory, StringComparison.Ordinal);
        Assert.DoesNotContain("rangersofB5", ltdInventory, StringComparison.Ordinal);
    }
}
