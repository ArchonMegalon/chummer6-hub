using Xunit;

namespace Chummer.Tests;

public sealed class E2EScriptSmokeTests
{
    [Fact]
    public void AuthScriptTracksCurrentWorkspaceSurfaceAndAllowsKeylessPublicSmoke()
    {
        string repoRoot = RepoPaths.Root;
        string scriptPath = RepoPaths.FromRoot("scripts", "e2e-auth.sh");
        string scriptText = File.ReadAllText(scriptPath);

        Assert.Contains("/api/shell/bootstrap", scriptText, StringComparison.Ordinal);
        Assert.Contains("/api/workspaces", scriptText, StringComparison.Ordinal);
        Assert.Contains("auth E2E completed without privileged API key", scriptText, StringComparison.Ordinal);
        Assert.DoesNotContain("/api/content/overlays", scriptText, StringComparison.Ordinal);
    }

    [Fact]
    public void LiveScriptUsesWorkspaceFlowAndNotRemovedCharacterOrLifemoduleRoutes()
    {
        string repoRoot = RepoPaths.Root;
        string scriptPath = RepoPaths.FromRoot("scripts", "e2e-live.sh");
        string scriptText = File.ReadAllText(scriptPath);

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
