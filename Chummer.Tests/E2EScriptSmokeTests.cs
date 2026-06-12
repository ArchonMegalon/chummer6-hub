using Xunit;

namespace Chummer.Tests;

public sealed class E2EScriptSmokeTests
{
    [Fact]
    public void AuthScriptIsExplicitlyLegacyAndPointsAtHubExitGate()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "e2e-auth.sh");
        string scriptText = File.ReadAllText(scriptPath);

        Assert.Contains("CHUMMER_ALLOW_LEGACY_WORKSPACE_E2E", scriptText, StringComparison.Ordinal);
        Assert.Contains("retired standalone workspace API surface", scriptText, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh", scriptText, StringComparison.Ordinal);
        Assert.Contains("/api/shell/bootstrap", scriptText, StringComparison.Ordinal);
        Assert.Contains("/api/workspaces", scriptText, StringComparison.Ordinal);
        Assert.DoesNotContain("/api/content/overlays", scriptText, StringComparison.Ordinal);
    }

    [Fact]
    public void LiveScriptIsExplicitlyLegacyAndNotTheCurrentGoldGate()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "e2e-live.sh");
        string scriptText = File.ReadAllText(scriptPath);

        Assert.Contains("CHUMMER_ALLOW_LEGACY_WORKSPACE_E2E", scriptText, StringComparison.Ordinal);
        Assert.Contains("retired standalone workspace API surface", scriptText, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_HUB_PLAYWRIGHT=1 bash scripts/e2e-hub.sh", scriptText, StringComparison.Ordinal);
        Assert.Contains("/api/workspaces/import", scriptText, StringComparison.Ordinal);
        Assert.Contains("/api/workspaces/$workspace_id/summary", scriptText, StringComparison.Ordinal);
        Assert.Contains("/api/workspaces/$workspace_id/export", scriptText, StringComparison.Ordinal);
        Assert.Contains("/api/workspaces/$workspace_id/print", scriptText, StringComparison.Ordinal);
        Assert.Contains("workspace live E2E completed", scriptText, StringComparison.Ordinal);
        Assert.DoesNotContain("/api/characters/summary", scriptText, StringComparison.Ordinal);
        Assert.DoesNotContain("/api/content/overlays", scriptText, StringComparison.Ordinal);
        Assert.DoesNotContain("/api/lifemodules/stages", scriptText, StringComparison.Ordinal);
        Assert.DoesNotContain("/api/lifemodules/modules", scriptText, StringComparison.Ordinal);
    }
}
