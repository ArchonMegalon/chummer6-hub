using Xunit;

namespace Chummer.Tests;

public sealed class PublicSurfaceReferenceFilesTests
{
    [Fact]
    public void PublicLandingSurfaceDocTracksTheCurrentPublicRouteFamilies()
    {
        string docPath = RepoPaths.FromRoot("docs", "PUBLIC_LANDING_SURFACE.md");
        string doc = File.ReadAllText(docPath);

        Assert.Contains("/roadmap", doc, StringComparison.Ordinal);
        Assert.Contains("/feedback", doc, StringComparison.Ordinal);
        Assert.Contains("/changelog", doc, StringComparison.Ordinal);
        Assert.Contains("/participate/karma-forge", doc, StringComparison.Ordinal);
        Assert.Contains("/feedback/operations", doc, StringComparison.Ordinal);
        Assert.Contains("milestone-backed public direction", doc, StringComparison.Ordinal);
        Assert.Contains("public signal, projected movement, and shipped proof", doc, StringComparison.Ordinal);
    }

    [Fact]
    public void MachineReadableGuideFilesExistForTheCurrentPublicRouteSplit()
    {
        string llmsPath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "llms.txt");
        string aiPath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "ai.txt");

        string llms = File.ReadAllText(llmsPath);
        string ai = File.ReadAllText(aiPath);

        Assert.Contains("/downloads", llms, StringComparison.Ordinal);
        Assert.Contains("/roadmap", llms, StringComparison.Ordinal);
        Assert.Contains("/feedback", llms, StringComparison.Ordinal);
        Assert.Contains("/changelog", llms, StringComparison.Ordinal);
        Assert.Contains("/participate/karma-forge", llms, StringComparison.Ordinal);
        Assert.Contains("/llms.txt", ai, StringComparison.Ordinal);
        Assert.Contains("/roadmap", ai, StringComparison.Ordinal);
        Assert.Contains("/feedback", ai, StringComparison.Ordinal);
        Assert.Contains("/contact", ai, StringComparison.Ordinal);
    }

    [Fact]
    public void SurfaceDocsTrackCodexFallbackTruthAndTheManifestRouteVerifier()
    {
        string docPath = RepoPaths.FromRoot("docs", "PUBLIC_LANDING_SURFACE.md");
        string runbookPath = RepoPaths.FromRoot("docs", "SELF_HOSTED_DOWNLOADS_RUNBOOK.md");
        string manifestPath = RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_LANDING_MANIFEST.yaml");

        string doc = File.ReadAllText(docPath);
        string manifest = File.ReadAllText(manifestPath);
        string runbook = File.ReadAllText(runbookPath);

        Assert.Contains("/auth/google/start?next=...", doc, StringComparison.Ordinal);
        Assert.Contains("/auth/google/start?next=/participate/codex", manifest, StringComparison.Ordinal);
        Assert.Contains("/progress", manifest, StringComparison.Ordinal);
        Assert.Contains("/feedback/operations", manifest, StringComparison.Ordinal);
        Assert.Contains("/feedback/operations/lookup", manifest, StringComparison.Ordinal);
        Assert.Contains("/contact/submitted/{caseId}", manifest, StringComparison.Ordinal);
        Assert.Contains("/participate/karma-forge/submitted/{submissionId}", manifest, StringComparison.Ordinal);
        Assert.Contains("verification_mode: controller_contract", manifest, StringComparison.Ordinal);
        Assert.Contains("verify_public_routes_from_manifest.py", runbook, StringComparison.Ordinal);
        Assert.Contains(".codex-design/product/PUBLIC_LANDING_MANIFEST.yaml", runbook, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_PUBLIC_ROUTE_PROOF.generated.json", runbook, StringComparison.Ordinal);
        Assert.Contains("https://chummer.run", runbook, StringComparison.Ordinal);
        Assert.Contains("https://chummer6.run", runbook, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_PUBLIC_ROUTE_PROOF_CHUMMER6_ALIAS.generated.json", runbook, StringComparison.Ordinal);
        Assert.Contains("stay unpublished", runbook, StringComparison.Ordinal);
    }

    [Fact]
    public void SelectedPublicSurfaceCopyAvoidsProviderAndLtdNames()
    {
        string[] publicFiles =
        {
            RepoPaths.FromRoot(".codex-design", "product", "PUBLIC_FEATURE_REGISTRY.yaml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Changelog.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Feedback.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "FeedbackOperationsDetail.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_PublicSignalOperationsPacket.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "KarmaForge.cshtml"),
            RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "KarmaForgeSubmitted.cshtml"),
        };

        string combined = string.Join("\n", publicFiles.Select(static path => File.ReadAllText(path)));

        Assert.DoesNotContain("ProductLift", combined, StringComparison.Ordinal);
        Assert.DoesNotContain("Emailit", combined, StringComparison.Ordinal);
        Assert.DoesNotContain("Icanpreneur", combined, StringComparison.Ordinal);
        Assert.DoesNotContain("Lunacal", combined, StringComparison.Ordinal);
        Assert.DoesNotContain("Product Governor", combined, StringComparison.Ordinal);
        Assert.DoesNotContain("OpenAI account in ChatGPT", combined, StringComparison.Ordinal);
    }
}
