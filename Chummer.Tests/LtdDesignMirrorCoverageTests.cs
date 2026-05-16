using Xunit;

namespace Chummer.Tests;

public sealed class LtdDesignMirrorCoverageTests
{
    [Fact]
    public void BlipAiIsTrackedAsBoundedHelperInDesignMirror()
    {
        string toolsPlane = File.ReadAllText(RepoPaths.FromRoot(".codex-design", "product", "EXTERNAL_TOOLS_PLANE.md"));
        string capabilityMap = File.ReadAllText(RepoPaths.FromRoot(".codex-design", "product", "LTD_CAPABILITY_MAP.md"));
        string runtimeRegistry = File.ReadAllText(RepoPaths.FromRoot(".codex-design", "product", "LTD_RUNTIME_AND_PROJECTION_REGISTRY.yaml"));
        string envExample = File.ReadAllText(RepoPaths.FromRoot(".env.example"));
        string ltdInventory = File.ReadAllText(RepoPaths.FromRoot("ltds.md"));

        Assert.Contains("* Blip AI", toolsPlane, StringComparison.Ordinal);
        Assert.Contains("workspace integration Tier 3, vendor license plan Tier 4", toolsPlane, StringComparison.Ordinal);
        Assert.Contains("knowledge-fabric", toolsPlane, StringComparison.Ordinal);
        Assert.Contains("runbook-press", toolsPlane, StringComparison.Ordinal);

        Assert.Contains("`Blip AI` - bounded dictation, transcript cleanup, and operator draft-capture helper", capabilityMap, StringComparison.Ordinal);
        Assert.Contains("`Blip AI` - `chummer6-hub` for bounded dictation, transcript cleanup, and operator draft capture", capabilityMap, StringComparison.Ordinal);

        Assert.Contains("- Blip AI", runtimeRegistry, StringComparison.Ordinal);
        Assert.Contains("knowledge_projection_system", runtimeRegistry, StringComparison.Ordinal);
        Assert.Contains("local_acceleration_research", runtimeRegistry, StringComparison.Ordinal);

        Assert.Contains("CHUMMER_EA_BLIPAI_APP_TIER=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_BLIPAI_APP_EMAIL=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_BLIPAI_APP_PASSWORD=", envExample, StringComparison.Ordinal);

        Assert.Contains("### blipai.app", ltdInventory, StringComparison.Ordinal);
        Assert.DoesNotContain("rangersofB5!", ltdInventory, StringComparison.Ordinal);
    }
}
