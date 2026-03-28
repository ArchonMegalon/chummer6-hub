using System.Diagnostics;
using Xunit;

namespace Chummer.Tests;

public sealed class CampaignOsLocalProofMaterializerTests
{
    [Fact]
    public void MaterializerDoesNotRewriteProofWhenSemanticPayloadIsUnchanged()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "campaign-os-proof", Guid.NewGuid().ToString("N"));
        string smokeDir = Path.Combine(tempRoot, "tests", "RunServicesSmoke");
        string proofDir = Path.Combine(tempRoot, ".codex-studio", "published");
        string smokeSourcePath = Path.Combine(smokeDir, "Program.cs");
        string proofPath = Path.Combine(proofDir, "HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json");
        string scriptPath = RepoPaths.FromRoot("scripts", "materialize_campaign_os_local_proof.py");
        string repoSmokeSourcePath = RepoPaths.FromRoot("tests", "RunServicesSmoke", "Program.cs");

        Directory.CreateDirectory(smokeDir);
        Directory.CreateDirectory(proofDir);
        File.Copy(repoSmokeSourcePath, smokeSourcePath, overwrite: true);

        RunMaterializer(scriptPath, tempRoot, smokeSourcePath, proofPath);
        string first = File.ReadAllText(proofPath);

        Thread.Sleep(1200);

        RunMaterializer(scriptPath, tempRoot, smokeSourcePath, proofPath);
        string second = File.ReadAllText(proofPath);

        Assert.Equal(first, second);
    }

    private static void RunMaterializer(string scriptPath, string rootPath, string sourcePath, string outPath)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = "python3",
            Arguments = scriptPath,
            RedirectStandardError = true,
            RedirectStandardOutput = true,
            UseShellExecute = false,
        };

        startInfo.Environment["CHUMMER_CAMPAIGN_OS_LOCAL_PROOF_ROOT"] = rootPath;
        startInfo.Environment["CHUMMER_CAMPAIGN_OS_LOCAL_PROOF_SOURCE"] = sourcePath;
        startInfo.Environment["CHUMMER_CAMPAIGN_OS_LOCAL_PROOF_OUT"] = outPath;

        using Process process = Process.Start(startInfo)!;
        string stdout = process.StandardOutput.ReadToEnd();
        string stderr = process.StandardError.ReadToEnd();
        process.WaitForExit();

        Assert.True(
            process.ExitCode == 0,
            $"materializer should succeed but exited with {process.ExitCode}\nstdout:\n{stdout}\nstderr:\n{stderr}");
    }
}
