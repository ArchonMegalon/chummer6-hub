using System.Diagnostics;
using System.Text.Json;
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
        using JsonDocument proof = JsonDocument.Parse(first);
        JsonElement installMarkers = proof.RootElement
            .GetProperty("required_markers")
            .GetProperty("install_claim_restore_continue");
        JsonElement recoverRecapMarkers = proof.RootElement
            .GetProperty("required_markers")
            .GetProperty("campaign_session_recover_recap");

        Assert.Contains(
            proof.RootElement.GetProperty("journeys_passed").EnumerateArray().Select(static item => item.GetString()).ToArray(),
            journey => string.Equals(journey, "install_claim_restore_continue", StringComparison.Ordinal));
        Assert.Contains(
            installMarkers.EnumerateArray().Select(static item => item.GetString()).ToArray(),
            marker => string.Equals(
                marker,
                "redeemPayload is not null && !redeemPayload.AlreadyClaimed",
                StringComparison.Ordinal));
        Assert.Contains(
            installMarkers.EnumerateArray().Select(static item => item.GetString()).ToArray(),
            marker => string.Equals(
                marker,
                "!string.IsNullOrWhiteSpace(dispatchModel?.ClaimExchangeUrl) && dispatchModel.ClaimExchangeUrl!.EndsWith(\"/continue.json\", StringComparison.Ordinal)",
                StringComparison.Ordinal));

        Assert.Contains(
            recoverRecapMarkers.EnumerateArray().Select(static item => item.GetString()).ToArray(),
            marker => string.Equals(
                marker,
                "workspaceServerPlanePayload.RestoreProvenanceReceipts.Count == restorePayload!.ProvenanceReceipts.Count",
                StringComparison.Ordinal));
        Assert.Contains(
            recoverRecapMarkers.EnumerateArray().Select(static item => item.GetString()).ToArray(),
            marker => string.Equals(
                marker,
                "accountWorkspaceDetailModel?.SelectedWorkspaceServerPlane?.RestoreConflictReceipts.Count == restorePayload.ConflictReceipts.Count",
                StringComparison.Ordinal));
        Assert.Contains(
            recoverRecapMarkers.EnumerateArray().Select(static item => item.GetString()).ToArray(),
            marker => string.Equals(
                marker,
                "string.Equals(item.Kind, \"entitlement_artifact_drift\", StringComparison.OrdinalIgnoreCase)",
                StringComparison.Ordinal));

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
