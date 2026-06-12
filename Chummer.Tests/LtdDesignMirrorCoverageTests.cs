using Xunit;
using System.Text.RegularExpressions;

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
        string publicEdgeCompose = File.ReadAllText(RepoPaths.FromRoot("docker-compose.public-edge.yml"));

        Assert.Contains("Current known external-tool inventory includes:", toolsPlane, StringComparison.Ordinal);
        Assert.Contains("workspace integration Tier 3, vendor license plan Tier 4", toolsPlane, StringComparison.Ordinal);
        Assert.Contains("runbook-press", toolsPlane, StringComparison.Ordinal);
        Assert.Contains("table-pulse-aftermath", toolsPlane, StringComparison.Ordinal);
        Assert.Contains("Prompt Architects", toolsPlane, StringComparison.Ordinal);
        Assert.Contains("PayFunnels", toolsPlane, StringComparison.Ordinal);

        Assert.Contains("`ClickRank` - public site visibility, crawl-health, technical SEO, schema, metadata, and AI-search audit lane", capabilityMap, StringComparison.Ordinal);
        Assert.Contains("`ProductLift` - public feedback, voting, roadmap projection, changelog projection, and voter closeout lane", capabilityMap, StringComparison.Ordinal);
        Assert.Contains("`Documentation.AI` - docs/help projection surface downstream of canon, not first-line crash capture", capabilityMap, StringComparison.Ordinal);
        Assert.Contains("`Prompt Architects` - prompt, style, and persona support for guide, horizon, media, and live runtime planning workflows", capabilityMap, StringComparison.Ordinal);
        Assert.Contains("`PayFunnels` - bounded test-billing adapter and entitlement-event simulation lane", capabilityMap, StringComparison.Ordinal);
        Assert.Contains("`Unmixr AI` - candidate voice lane until proven", capabilityMap, StringComparison.Ordinal);
        Assert.Contains("`SendFox` - public newsletter and digest list if Emailit stays primarily transactional.", capabilityMap, StringComparison.Ordinal);
        Assert.Contains("`Flonnect` - bounded QA, bug reproduction, support evidence, tutorial, and operator-training capture.", capabilityMap, StringComparison.Ordinal);
        Assert.Contains("`CutMe Short` - branded links, UTM discipline, expiry, rotators, and campaign-link analytics if Signitic/Taja/vidBoard/FacePop links get hard to govern.", capabilityMap, StringComparison.Ordinal);
        Assert.Contains("`Backona AI` - operator question layer over GA4/Search Console only if ClickRank, PostHog, and GSC dashboards are not getting used.", capabilityMap, StringComparison.Ordinal);
        Assert.Contains("`Visby` - optional AI-answer visibility and competitor/gap monitoring after ClickRank and Katteb are already in use.", capabilityMap, StringComparison.Ordinal);

        Assert.Contains("public_growth_system:", runtimeRegistry, StringComparison.Ordinal);
        Assert.Contains("artifact_factory:", runtimeRegistry, StringComparison.Ordinal);
        Assert.Contains("trust_closure_system:", runtimeRegistry, StringComparison.Ordinal);
        Assert.Contains("Prompt Architects", runtimeRegistry, StringComparison.Ordinal);
        Assert.Contains("PayFunnels", runtimeRegistry, StringComparison.Ordinal);
        Assert.Contains("Unmixr AI", runtimeRegistry, StringComparison.Ordinal);
        Assert.Contains("SendFox:", runtimeRegistry, StringComparison.Ordinal);
        Assert.Contains("Flonnect:", runtimeRegistry, StringComparison.Ordinal);
        Assert.Contains("CutMe Short:", runtimeRegistry, StringComparison.Ordinal);
        Assert.Contains("Backona AI:", runtimeRegistry, StringComparison.Ordinal);
        Assert.Contains("Visby:", runtimeRegistry, StringComparison.Ordinal);

        Assert.Contains("CHUMMER_EA_BLIPAI_APP_TIER=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_BLIPAI_APP_EMAIL=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_BLIPAI_APP_PASSWORD=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_MAGICFIT_TIER=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_MAGICFIT_EMAIL=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_MAGICFIT_PASSWORD=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_MAGICFIT_GM_SESSION_EMAIL=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_MAGICFIT_GM_SESSION_PASSWORD=", envExample, StringComparison.Ordinal);
        Assert.Contains("PROMPTING_SYSTEMS_API_KEY=", envExample, StringComparison.Ordinal);
        Assert.Contains("PROMPT_ARCHITECTS_TIER4_VERIFIED=", envExample, StringComparison.Ordinal);
        Assert.Contains("PROMPT_ARCHITECTS_API_AVAILABLE=", envExample, StringComparison.Ordinal);
        Assert.Contains("PROMPT_ARCHITECTS_MCP_VERIFIED=", envExample, StringComparison.Ordinal);
        Assert.Contains("PROMPT_ARCHITECTS_EXPORT_AVAILABLE=", envExample, StringComparison.Ordinal);
        Assert.Contains("PROMPT_ARCHITECTS_IMPORT_AVAILABLE=", envExample, StringComparison.Ordinal);
        Assert.Contains("PROMPT_ARCHITECTS_DATA_RETENTION_REVIEWED=", envExample, StringComparison.Ordinal);
        Assert.Contains("PROMPT_ARCHITECTS_TEAM_PERMISSIONS_REVIEWED=", envExample, StringComparison.Ordinal);
        Assert.Contains("PAYFUNNELS_WEBHOOK_SECRET=", envExample, StringComparison.Ordinal);
        Assert.Contains("PAYFUNNELS_TEST_CHECKOUT_URL=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_PAYFUNNELS_BILLING_STORE_PATH=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_UNMIXR_TIER=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_UNMIXR_EMAIL=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_UNMIXR_PASSWORD=", envExample, StringComparison.Ordinal);
        Assert.Contains("UNMIXR_USERNAME=", envExample, StringComparison.Ordinal);
        Assert.Contains("UNMIXR_PASSWORD=", envExample, StringComparison.Ordinal);
        Assert.Contains("UNMIXR_API_KEY=", envExample, StringComparison.Ordinal);
        Assert.Contains("UNMIXR_VOICE_ID=", envExample, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_MAGICFIT_EMAIL: ${CHUMMER_EA_MAGICFIT_EMAIL:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_MAGICFIT_PASSWORD: ${CHUMMER_EA_MAGICFIT_PASSWORD:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_MAGICFIT_GM_SESSION_EMAIL: ${CHUMMER_EA_MAGICFIT_GM_SESSION_EMAIL:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_MAGICFIT_GM_SESSION_PASSWORD: ${CHUMMER_EA_MAGICFIT_GM_SESSION_PASSWORD:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("PROMPTING_SYSTEMS_API_KEY: ${PROMPTING_SYSTEMS_API_KEY:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("PROMPT_ARCHITECTS_TIER4_VERIFIED: ${PROMPT_ARCHITECTS_TIER4_VERIFIED:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("PROMPT_ARCHITECTS_API_AVAILABLE: ${PROMPT_ARCHITECTS_API_AVAILABLE:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("PROMPT_ARCHITECTS_MCP_VERIFIED: ${PROMPT_ARCHITECTS_MCP_VERIFIED:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("PROMPT_ARCHITECTS_EXPORT_AVAILABLE: ${PROMPT_ARCHITECTS_EXPORT_AVAILABLE:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("PROMPT_ARCHITECTS_IMPORT_AVAILABLE: ${PROMPT_ARCHITECTS_IMPORT_AVAILABLE:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("PROMPT_ARCHITECTS_DATA_RETENTION_REVIEWED: ${PROMPT_ARCHITECTS_DATA_RETENTION_REVIEWED:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("PROMPT_ARCHITECTS_TEAM_PERMISSIONS_REVIEWED: ${PROMPT_ARCHITECTS_TEAM_PERMISSIONS_REVIEWED:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("PAYFUNNELS_WEBHOOK_SECRET: ${PAYFUNNELS_WEBHOOK_SECRET:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("PAYFUNNELS_TEST_CHECKOUT_URL: ${PAYFUNNELS_TEST_CHECKOUT_URL:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_PAYFUNNELS_BILLING_STORE_PATH: ${CHUMMER_PAYFUNNELS_BILLING_STORE_PATH:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_UNMIXR_TIER: ${CHUMMER_EA_UNMIXR_TIER:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_UNMIXR_EMAIL: ${CHUMMER_EA_UNMIXR_EMAIL:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_EA_UNMIXR_PASSWORD: ${CHUMMER_EA_UNMIXR_PASSWORD:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("UNMIXR_USERNAME: ${UNMIXR_USERNAME:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("UNMIXR_PASSWORD: ${UNMIXR_PASSWORD:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("UNMIXR_API_KEY: ${UNMIXR_API_KEY:-}", publicEdgeCompose, StringComparison.Ordinal);
        Assert.Contains("UNMIXR_VOICE_ID: ${UNMIXR_VOICE_ID:-}", publicEdgeCompose, StringComparison.Ordinal);

        Assert.Contains("### blipai.app", ltdInventory, StringComparison.Ordinal);
        Assert.Contains("### magicfit", ltdInventory, StringComparison.Ordinal);
        Assert.Contains("### magicfit_session", ltdInventory, StringComparison.Ordinal);
        Assert.Contains("### prompt_architects", ltdInventory, StringComparison.Ordinal);
        Assert.Contains("### payfunnels", ltdInventory, StringComparison.Ordinal);
        Assert.Contains("### unmixr", ltdInventory, StringComparison.Ordinal);
        Assert.Contains("SendFox", ltdInventory, StringComparison.Ordinal);
        Assert.Contains("Flonnect", ltdInventory, StringComparison.Ordinal);
        Assert.Contains("CutMe Short", ltdInventory, StringComparison.Ordinal);
        Assert.Contains("Backona AI", ltdInventory, StringComparison.Ordinal);
        Assert.Contains("Visby", ltdInventory, StringComparison.Ordinal);
        Assert.DoesNotContain("rangersofB5!", ltdInventory, StringComparison.Ordinal);
        Assert.DoesNotContain("rangersofB5", ltdInventory, StringComparison.Ordinal);
    }

    [Fact]
    public void EveryLtdInventoryEnvKeyIsDocumentedAndPassedThroughToPublicEdge()
    {
        string ltdInventory = File.ReadAllText(RepoPaths.FromRoot("ltds.md"));
        string envExample = File.ReadAllText(RepoPaths.FromRoot(".env.example"));
        string publicEdgeCompose = File.ReadAllText(RepoPaths.FromRoot("docker-compose.public-edge.yml"));

        string[] inventoryEnvKeys = Regex.Matches(
                ltdInventory,
                @"-\s+env_[^:]+:\s*`(?<key>[A-Z0-9_]+)`",
                RegexOptions.CultureInvariant)
            .Select(static match => match.Groups["key"].Value)
            .Distinct(StringComparer.Ordinal)
            .Order(StringComparer.Ordinal)
            .ToArray();

        Assert.NotEmpty(inventoryEnvKeys);

        foreach (string key in inventoryEnvKeys)
        {
            Assert.Contains($"{key}=", envExample, StringComparison.Ordinal);
            Assert.Contains($"{key}: ${{{key}:-", publicEdgeCompose, StringComparison.Ordinal);
        }
    }
}
