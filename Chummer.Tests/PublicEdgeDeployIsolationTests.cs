using Xunit;

namespace Chummer.Tests;

public sealed class PublicEdgeDeployIsolationTests
{
    [Fact]
    public void PublicEdgeComposeDoesNotForcePortalToWaitForBlazor()
    {
        string composePath = RepoPaths.FromRoot("docker-compose.public-edge.yml");
        string compose = File.ReadAllText(composePath);
        int portalStart = compose.IndexOf("  chummer-portal:", StringComparison.Ordinal);
        int nextService = compose.IndexOf("\n  chummer-run-cloudflared:", StringComparison.Ordinal);
        string portalBlock = portalStart >= 0 && nextService > portalStart
            ? compose[portalStart..nextService]
            : compose;

        Assert.Contains("chummer-portal:", compose, StringComparison.Ordinal);
        Assert.Contains("depends_on:", portalBlock, StringComparison.Ordinal);
        Assert.Contains("- chummer-run-identity", portalBlock, StringComparison.Ordinal);
        Assert.Contains("- support-progress-mock", portalBlock, StringComparison.Ordinal);
        Assert.DoesNotContain("- chummer-public-blazor", portalBlock, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_PUBLIC_BLAZOR_PROXY_URL", compose, StringComparison.Ordinal);
    }

    [Fact]
    public void HubCloseoutKeepsBlazorAsAnExplicitOptInLane()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "ai", "hub_closeout.sh");
        string script = File.ReadAllText(scriptPath);

        Assert.Contains("HUB_CLOSEOUT_INCLUDE_BLAZOR", script, StringComparison.Ordinal);
        Assert.Contains("public_edge_services=(chummer-run-identity chummer-portal)", script, StringComparison.Ordinal);
        Assert.Contains("public_edge_services+=(chummer-public-blazor)", script, StringComparison.Ordinal);
        Assert.Contains("docker compose \"${compose_args[@]}\" up -d --build --remove-orphans \"${public_edge_services[@]}\"", script, StringComparison.Ordinal);
        Assert.DoesNotContain("up -d --build --remove-orphans chummer-run-identity chummer-portal", script, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicEdgeDoesNotOwnHomeAssistant()
    {
        string composePath = RepoPaths.FromRoot("docker-compose.public-edge.yml");
        string envExamplePath = RepoPaths.FromRoot(".env.example");

        string compose = File.ReadAllText(composePath);
        string envExample = File.ReadAllText(envExamplePath);

        Assert.DoesNotContain("home-girschele-hass", compose, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("homeassistant", compose, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("HOME_GIRSCHELE", compose, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("HOME_GIRSCHELE", envExample, StringComparison.OrdinalIgnoreCase);
        Assert.False(File.Exists(RepoPaths.FromRoot("scripts", "home_girschele_hass_ops.sh")));
        Assert.False(File.Exists(RepoPaths.FromRoot("docs", "HOME_GIRSCHELE_HOME_ASSISTANT_RUNBOOK.md")));
    }
}
