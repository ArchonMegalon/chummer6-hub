using System.Diagnostics;
using Xunit;

namespace Chummer.Tests;

public sealed class HubLocalReleaseProofMaterializerTests
{
    [Fact]
    public void E2EScriptUsesStableHubLocalReleaseProofMaterializer()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "e2e-hub.sh");
        string script = File.ReadAllText(scriptPath);

        Assert.Contains("materialize_hub_local_release_proof.py", script, StringComparison.Ordinal);
    }

    [Fact]
    public void MaterializerDoesNotRewriteHubLocalProofWhenPayloadIsUnchanged()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-local-proof", Guid.NewGuid().ToString("N"));
        string proofPath = Path.Combine(tempRoot, "HUB_LOCAL_RELEASE_PROOF.generated.json");
        string scriptPath = RepoPaths.FromRoot("scripts", "materialize_hub_local_release_proof.py");

        Directory.CreateDirectory(tempRoot);

        RunMaterializer(scriptPath, proofPath);
        string first = File.ReadAllText(proofPath);

        Thread.Sleep(1200);

        RunMaterializer(scriptPath, proofPath);
        string second = File.ReadAllText(proofPath);

        Assert.Equal(first, second);
    }

    private static void RunMaterializer(string scriptPath, string proofPath)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = "python3",
            Arguments = $"{scriptPath} {proofPath} http://127.0.0.1:8091 docker-compose.public-edge.yml 300 true",
            RedirectStandardError = true,
            RedirectStandardOutput = true,
            UseShellExecute = false,
        };

        using Process process = Process.Start(startInfo)!;
        string stdout = process.StandardOutput.ReadToEnd();
        string stderr = process.StandardError.ReadToEnd();
        process.WaitForExit();

        Assert.True(
            process.ExitCode == 0,
            $"hub local proof materializer should succeed but exited with {process.ExitCode}\nstdout:\n{stdout}\nstderr:\n{stderr}");
    }
}
