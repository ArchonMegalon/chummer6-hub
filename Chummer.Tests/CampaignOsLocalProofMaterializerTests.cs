using System.Diagnostics;
using Xunit;

namespace Chummer.Tests;

public sealed class CampaignOsLocalProofMaterializerTests
{
    [Fact]
    public void MaterializerRejectsLegacyOverridesWithoutTouchingCanonicalProof()
    {
        string tempRoot = Path.Combine(
            Path.GetTempPath(),
            "campaign-os-proof-cli",
            Guid.NewGuid().ToString("N"));
        string redirectedProofPath = Path.Combine(
            tempRoot,
            ".codex-studio",
            "published",
            "HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json");
        string scriptPath = RepoPaths.FromRoot("scripts", "materialize_campaign_os_local_proof.py");
        string canonicalProofPath = RepoPaths.FromRoot(
            ".codex-studio",
            "published",
            "HUB_CAMPAIGN_OS_LOCAL_PROOF.generated.json");
        byte[] canonicalBefore = File.ReadAllBytes(canonicalProofPath);

        ProcessResult result = RunMaterializer(
            scriptPath,
            "run",
            "--root",
            tempRoot,
            "--source",
            RepoPaths.FromRoot("tests", "RunServicesSmoke", "Program.cs"),
            "--out",
            redirectedProofPath);

        Assert.Equal(2, result.ExitCode);
        Assert.Contains("unrecognized arguments", result.Stderr, StringComparison.OrdinalIgnoreCase);
        Assert.False(File.Exists(redirectedProofPath));
        Assert.Equal(canonicalBefore, File.ReadAllBytes(canonicalProofPath));
    }

    private static ProcessResult RunMaterializer(string scriptPath, params string[] arguments)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = "python3",
            RedirectStandardError = true,
            RedirectStandardOutput = true,
            UseShellExecute = false,
        };
        startInfo.ArgumentList.Add("-I");
        startInfo.ArgumentList.Add("-S");
        startInfo.ArgumentList.Add(scriptPath);
        foreach (string argument in arguments)
        {
            startInfo.ArgumentList.Add(argument);
        }

        using Process process = Process.Start(startInfo)!;
        string stdout = process.StandardOutput.ReadToEnd();
        string stderr = process.StandardError.ReadToEnd();
        process.WaitForExit();
        return new ProcessResult(process.ExitCode, stdout, stderr);
    }

    private sealed record ProcessResult(int ExitCode, string Stdout, string Stderr);
}
