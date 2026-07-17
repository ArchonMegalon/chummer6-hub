using System.Diagnostics;
using System.Text.Json;
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
        Assert.Contains("resolve_hub_proof_base_url", script, StringComparison.Ordinal);
        Assert.Contains("https://%s", script, StringComparison.Ordinal);
        Assert.Contains("\"$hub_proof_base_url\"", script, StringComparison.Ordinal);
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

    [Fact]
    public void MaterializerPublishesWorkspaceContinuityProofReceipts()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-local-proof", Guid.NewGuid().ToString("N"));
        string proofPath = Path.Combine(tempRoot, "HUB_LOCAL_RELEASE_PROOF.generated.json");
        string scriptPath = RepoPaths.FromRoot("scripts", "materialize_hub_local_release_proof.py");

        Directory.CreateDirectory(tempRoot);

        RunMaterializer(scriptPath, proofPath);

        using JsonDocument document = JsonDocument.Parse(File.ReadAllText(proofPath));
        JsonElement package = document.RootElement.GetProperty("successor_queue_package");
        Assert.Equal("next90-m105-hub-workspace-continuity", package.GetProperty("package_id").GetString());
        Assert.Equal(105, package.GetProperty("milestone_id").GetInt32());
        Assert.Equal(4623636482, package.GetProperty("frontier_id").GetInt64());
        Assert.Contains(
            package.GetProperty("owned_surfaces").EnumerateArray(),
            surface => string.Equals(surface.GetString(), "workspace_restore:provenance", StringComparison.Ordinal));
        Assert.Contains(
            package.GetProperty("owned_surfaces").EnumerateArray(),
            surface => string.Equals(surface.GetString(), "entitlement_sync:conflict_receipts", StringComparison.Ordinal));

        JsonElement routes = document.RootElement.GetProperty("proof_routes");
        string[] routeList = routes.EnumerateArray().Select(static route => route.GetString() ?? string.Empty).ToArray();
        Assert.Equal(
            [
                "/downloads/install/avalonia-linux-x64-installer",
                "/home/access",
                "/home/work",
                "/account/access",
                "/account/work",
                "/account/support",
                "/contact",
                "/downloads",
                "/downloads/install/avalonia-osx-arm64-installer",
                "/downloads/install/avalonia-win-x64-installer",
            ],
            routeList);

        JsonElement receipts = document.RootElement.GetProperty("proof_receipts");

        Assert.Equal(JsonValueKind.Array, receipts.ValueKind);
        Assert.Contains(
            receipts.EnumerateArray(),
            receipt => string.Equals(receipt.GetProperty("receipt_id").GetString(), "workspace_restore:provenance", StringComparison.Ordinal));
        Assert.Contains(
            receipts.EnumerateArray(),
            receipt => string.Equals(receipt.GetProperty("receipt_id").GetString(), "entitlement_sync:conflict_receipts", StringComparison.Ordinal));
        Assert.Contains(
            receipts.EnumerateArray(),
            receipt => string.Equals(receipt.GetProperty("receipt_id").GetString(), "desktop_native_claim_and_recovery", StringComparison.Ordinal));
        Assert.Contains(
            receipts.EnumerateArray(),
            receipt => string.Equals(receipt.GetProperty("receipt_id").GetString(), "public_proof_shelf:release_bundles", StringComparison.Ordinal));
        Assert.Contains(
            receipts.EnumerateArray(),
            receipt => string.Equals(receipt.GetProperty("receipt_id").GetString(), "campaign_memory:consequence_truth", StringComparison.Ordinal)
                && receipt.GetProperty("routes").EnumerateArray().Any(route => string.Equals(route.GetString(), "/account/work#campaign-consequences", StringComparison.Ordinal)));
        Assert.Contains(
            receipts.EnumerateArray(),
            receipt => string.Equals(receipt.GetProperty("receipt_id").GetString(), "downtime_aftermath:api", StringComparison.Ordinal)
                && receipt.GetProperty("routes").EnumerateArray().Any(route => string.Equals(route.GetString(), "/account/work#aftermath-packages", StringComparison.Ordinal)));

        JsonElement provenanceReceipt = receipts.EnumerateArray().Single(
            receipt => string.Equals(receipt.GetProperty("receipt_id").GetString(), "workspace_restore:provenance", StringComparison.Ordinal));
        Assert.Equal("next90-m105-hub-workspace-continuity", provenanceReceipt.GetProperty("package_id").GetString());
        Assert.Equal(105, provenanceReceipt.GetProperty("milestone_id").GetInt32());
        Assert.Equal(4623636482, provenanceReceipt.GetProperty("frontier_id").GetInt64());
        Assert.Contains("claimed installs", provenanceReceipt.GetProperty("summary").GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.Contains(
            provenanceReceipt.GetProperty("surfaces").EnumerateArray(),
            surface => string.Equals(surface.GetString(), "workspace_restore:provenance", StringComparison.Ordinal));

        JsonElement desktopRecoveryReceipt = receipts.EnumerateArray().Single(
            receipt => string.Equals(receipt.GetProperty("receipt_id").GetString(), "desktop_native_claim_and_recovery", StringComparison.Ordinal));
        string[] desktopRecoveryRoutes = desktopRecoveryReceipt.GetProperty("routes").EnumerateArray()
            .Select(static route => route.GetString() ?? string.Empty)
            .ToArray();
        Assert.Contains("/downloads/install/avalonia-linux-x64-installer/continue.json", desktopRecoveryRoutes, StringComparer.Ordinal);
        Assert.Contains("/api/v1/install-linking/continuation", desktopRecoveryRoutes, StringComparer.Ordinal);
        Assert.Contains("/account/access", desktopRecoveryRoutes, StringComparer.Ordinal);

        JsonElement releaseBundleReceipt = receipts.EnumerateArray().Single(
            receipt => string.Equals(receipt.GetProperty("receipt_id").GetString(), "public_proof_shelf:release_bundles", StringComparison.Ordinal));
        Assert.Equal("next90-m107-hub-artifact-factory", releaseBundleReceipt.GetProperty("package_id").GetString());
        Assert.Equal(107, releaseBundleReceipt.GetProperty("milestone_id").GetInt32());
        Assert.Equal(1421219975, releaseBundleReceipt.GetProperty("frontier_id").GetInt64());
        Assert.Contains("release-bundle shelf refs", releaseBundleReceipt.GetProperty("summary").GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.Contains(
            releaseBundleReceipt.GetProperty("surfaces").EnumerateArray(),
            surface => string.Equals(surface.GetString(), "artifact_factory:orchestration", StringComparison.Ordinal));
        Assert.Contains(
            releaseBundleReceipt.GetProperty("surfaces").EnumerateArray(),
            surface => string.Equals(surface.GetString(), "public_proof_shelf:release_bundles", StringComparison.Ordinal));

        JsonElement conflictReceipt = receipts.EnumerateArray().Single(
            receipt => string.Equals(receipt.GetProperty("receipt_id").GetString(), "entitlement_sync:conflict_receipts", StringComparison.Ordinal));
        Assert.Equal("next90-m105-hub-workspace-continuity", conflictReceipt.GetProperty("package_id").GetString());
        Assert.Equal(105, conflictReceipt.GetProperty("milestone_id").GetInt32());
        Assert.Equal(4623636482, conflictReceipt.GetProperty("frontier_id").GetInt64());
        Assert.Contains("continue-blocking conflicts", conflictReceipt.GetProperty("summary").GetString(), StringComparison.OrdinalIgnoreCase);
        Assert.Contains(
            conflictReceipt.GetProperty("surfaces").EnumerateArray(),
            surface => string.Equals(surface.GetString(), "entitlement_sync:conflict_receipts", StringComparison.Ordinal));
    }

    [Fact]
    public void MaterializerPublishesCanonicalBaselineJourneyOrder()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-local-proof", Guid.NewGuid().ToString("N"));
        string proofPath = Path.Combine(tempRoot, "HUB_LOCAL_RELEASE_PROOF.generated.json");
        string scriptPath = RepoPaths.FromRoot("scripts", "materialize_hub_local_release_proof.py");

        Directory.CreateDirectory(tempRoot);

        RunMaterializer(scriptPath, proofPath);

        using JsonDocument document = JsonDocument.Parse(File.ReadAllText(proofPath));
        string[] journeys = document.RootElement
            .GetProperty("journeys_passed")
            .EnumerateArray()
            .Select(static item => item.GetString() ?? string.Empty)
            .ToArray();

        Assert.Equal(
            [
                "install_claim_restore_continue",
                "build_explain_publish",
                "campaign_session_recover_recap",
                "report_cluster_release_notify",
                "organize_community_and_close_loop",
            ],
            journeys);
    }

    [Fact]
    public void MaterializedProofSatisfiesRegistryReleaseProofContract()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "hub-local-proof", Guid.NewGuid().ToString("N"));
        string proofPath = Path.Combine(tempRoot, "HUB_LOCAL_RELEASE_PROOF.generated.json");
        string materializerPath = RepoPaths.FromRoot("scripts", "materialize_hub_local_release_proof.py");
        string registryValidatorPath = Path.GetFullPath(
            Path.Combine(
                RepoPaths.Root,
                "..",
                "chummer-hub-registry",
                "scripts",
                "materialize_public_release_channel.py"));

        Directory.CreateDirectory(tempRoot);

        RunMaterializer(materializerPath, proofPath, baseUrl: "https://chummer.run");
        RunRegistryReleaseProofValidator(registryValidatorPath, proofPath);
    }

    private static void RunMaterializer(
        string scriptPath,
        string proofPath,
        IReadOnlyDictionary<string, string>? environment = null,
        string baseUrl = "http://127.0.0.1:8091")
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = "python3",
            RedirectStandardError = true,
            RedirectStandardOutput = true,
            UseShellExecute = false,
        };
        startInfo.ArgumentList.Add(scriptPath);
        startInfo.ArgumentList.Add(proofPath);
        startInfo.ArgumentList.Add(baseUrl);
        startInfo.ArgumentList.Add("docker-compose.public-edge.yml");
        startInfo.ArgumentList.Add("300");
        startInfo.ArgumentList.Add("true");

        if (environment is not null)
        {
            foreach ((string key, string value) in environment)
            {
                startInfo.Environment[key] = value;
            }
        }

        using Process process = Process.Start(startInfo)!;
        string stdout = process.StandardOutput.ReadToEnd();
        string stderr = process.StandardError.ReadToEnd();
        process.WaitForExit();

        Assert.True(
            process.ExitCode == 0,
            $"hub local proof materializer should succeed but exited with {process.ExitCode}\nstdout:\n{stdout}\nstderr:\n{stderr}");
    }

    private static void RunRegistryReleaseProofValidator(string scriptPath, string proofPath)
    {
        Assert.True(File.Exists(scriptPath), $"Registry release-proof validator was not found: {scriptPath}");

        var startInfo = new ProcessStartInfo
        {
            FileName = "python3",
            RedirectStandardError = true,
            RedirectStandardOutput = true,
            UseShellExecute = false,
        };
        startInfo.ArgumentList.Add("-c");
        startInfo.ArgumentList.Add(
            "from pathlib import Path; import runpy, sys; "
            + "runpy.run_path(sys.argv[1])['load_release_proof'](Path(sys.argv[2]))");
        startInfo.ArgumentList.Add(scriptPath);
        startInfo.ArgumentList.Add(proofPath);

        using Process process = Process.Start(startInfo)!;
        string stdout = process.StandardOutput.ReadToEnd();
        string stderr = process.StandardError.ReadToEnd();
        process.WaitForExit();

        Assert.True(
            process.ExitCode == 0,
            $"Registry release-proof validator should accept the generated Hub proof but exited with {process.ExitCode}\nstdout:\n{stdout}\nstderr:\n{stderr}");
    }

}
