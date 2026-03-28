using Xunit;

namespace Chummer.Tests;

public sealed class VerificationEntryPointTests
{
    [Fact]
    public void AuditComplianceUsesSupportedVerificationScript()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "audit-compliance.sh");
        string script = File.ReadAllText(scriptPath);

        Assert.Contains("bash scripts/ai/verify.sh", script, StringComparison.Ordinal);
    }

    [Fact]
    public void SupportVerificationGuardAvoidsUnmatchedInstallFallback()
    {
        string presenterPath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "Support", "SupportCasePresentationService.cs");
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "SupportCasesController.cs");

        string presenter = File.ReadAllText(presenterPath);
        string controller = File.ReadAllText(controllerPath);

        Assert.Contains("best is not null && best.Score > 0", presenter, StringComparison.Ordinal);
        Assert.Contains("AllowsReporterVerification", controller, StringComparison.Ordinal);
        Assert.Contains("presented.CanVerifyFix", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void SignedInTrustProjectionSuppressesIdentityOutages()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string controller = File.ReadAllText(controllerPath);

        Assert.Contains("TryGetOptionalPublicSurfaceSubjectAsync", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicEdgeComposePinsHttpsPortForLocalChummerRunRedirects()
    {
        string composePath = RepoPaths.FromRoot("docker-compose.public-edge.yml");
        string compose = File.ReadAllText(composePath);

        Assert.Contains("ASPNETCORE_HTTPS_PORT", compose, StringComparison.Ordinal);
        Assert.Contains("${ASPNETCORE_HTTPS_PORT:-443}", compose, StringComparison.Ordinal);
    }

    [Fact]
    public void HubLiveAuditSupportsReverseProxiedLocalEdgeMode()
    {
        string auditPath = RepoPaths.FromRoot("scripts", "hub-live-audit.py");
        string audit = File.ReadAllText(auditPath);

        Assert.Contains("--public-host", audit, StringComparison.Ordinal);
        Assert.Contains("--forwarded-proto", audit, StringComparison.Ordinal);
        Assert.Contains("--verify-http-redirects", audit, StringComparison.Ordinal);
        Assert.Contains("X-Forwarded-Proto", audit, StringComparison.Ordinal);
    }

    [Fact]
    public void HubCloseoutAndE2EUseReverseProxiedLocalEdgeAudit()
    {
        string closeoutPath = RepoPaths.FromRoot("scripts", "ai", "hub_closeout.sh");
        string e2ePath = RepoPaths.FromRoot("scripts", "e2e-hub.sh");
        string closeout = File.ReadAllText(closeoutPath);
        string e2e = File.ReadAllText(e2ePath);

        Assert.Contains("HUB_PUBLIC_HOST", closeout, StringComparison.Ordinal);
        Assert.Contains("--forwarded-proto https", closeout, StringComparison.Ordinal);
        Assert.Contains("--verify-http-redirects", closeout, StringComparison.Ordinal);
        Assert.Contains("hub-live-audit.py", e2e, StringComparison.Ordinal);
        Assert.Contains("wait_for_hub_edge", e2e, StringComparison.Ordinal);
        Assert.Contains("HUB_PUBLIC_HOST", e2e, StringComparison.Ordinal);
        Assert.Contains("--forwarded-proto https", e2e, StringComparison.Ordinal);
        Assert.Contains("--verify-http-redirects", e2e, StringComparison.Ordinal);
    }

    [Fact]
    public void HubRequestObservabilityIsWiredIntoProgramAndVerification()
    {
        string programPath = RepoPaths.FromRoot("Chummer.Run.Api", "Program.cs");
        string verificationProgramPath = RepoPaths.FromRoot("tests", "RunServicesVerification", "Program.cs");
        string backlogPath = RepoPaths.FromRoot("docs", "MIGRATION_BACKLOG.md");
        string middlewarePath = RepoPaths.FromRoot("Chummer.Run.Api", "HubRequestObservabilityMiddleware.cs");

        string program = File.ReadAllText(programPath);
        string verificationProgram = File.ReadAllText(verificationProgramPath);
        string backlog = File.ReadAllText(backlogPath);
        string middleware = File.ReadAllText(middlewarePath);

        Assert.Contains("AddHubRequestObservability", program, StringComparison.Ordinal);
        Assert.Contains("UseHubRequestObservability", program, StringComparison.Ordinal);
        Assert.Contains("HubRequestObservabilityVerification.RunAsync", verificationProgram, StringComparison.Ordinal);
        Assert.Contains("MIG-091", backlog, StringComparison.Ordinal);
        Assert.Contains("Response.OnStarting", middleware, StringComparison.Ordinal);
    }

    [Fact]
    public void ReleaseWorkflowPublishesApiAndDownloadsMirrorArtifacts()
    {
        string workflowPath = RepoPaths.FromRoot(".github", "workflows", "desktop-downloads-matrix.yml");
        string docsPath = RepoPaths.FromRoot("docs", "ACTIVE_HEAD_RELEASE_ARTIFACTS.md");

        string workflow = File.ReadAllText(workflowPath);
        string docs = File.ReadAllText(docsPath);

        Assert.Contains("- main", workflow, StringComparison.Ordinal);
        Assert.Contains("name: Public Edge Release Artifacts", workflow, StringComparison.Ordinal);
        Assert.Contains("name: release-api-portable", workflow, StringComparison.Ordinal);
        Assert.Contains("Stage public downloads mirror", workflow, StringComparison.Ordinal);
        Assert.Contains("desktop-download-bundle", workflow, StringComparison.Ordinal);
        Assert.DoesNotContain("Chummer.Avalonia/Chummer.Avalonia.csproj", workflow, StringComparison.Ordinal);
        Assert.DoesNotContain("Chummer.Blazor.Desktop/Chummer.Blazor.Desktop.csproj", workflow, StringComparison.Ordinal);
        Assert.Contains("release-api-portable", docs, StringComparison.Ordinal);
        Assert.Contains("checked-in public download mirror", docs, StringComparison.Ordinal);
        Assert.Contains("desktop-download-bundle", docs, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicEdgeGuardrailsDoNotReferenceMissingPortalProject()
    {
        string workflowPath = RepoPaths.FromRoot(".github", "workflows", "docker-architecture-guardrails.yml");
        string composePath = RepoPaths.FromRoot("legacy", "tooling", "docker", "docker-compose.yml");
        string runbookPath = RepoPaths.FromRoot("scripts", "runbook.sh");
        string migrationLoopPath = RepoPaths.FromRoot("scripts", "migration-loop.sh");
        string backlogPath = RepoPaths.FromRoot("docs", "MIGRATION_BACKLOG.md");

        string workflow = File.ReadAllText(workflowPath);
        string compose = File.ReadAllText(composePath);
        string runbook = File.ReadAllText(runbookPath);
        string migrationLoop = File.ReadAllText(migrationLoopPath);
        string backlog = File.ReadAllText(backlogPath);

        Assert.DoesNotContain("Chummer.Portal/Chummer.Portal.csproj", workflow, StringComparison.Ordinal);
        Assert.DoesNotContain("Chummer.Portal/appsettings.json", runbook, StringComparison.Ordinal);
        Assert.Contains("Chummer.Run.Api/Chummer.Run.Api.csproj", workflow, StringComparison.Ordinal);
        Assert.Contains("Chummer.Run.Api/Dockerfile", compose, StringComparison.Ordinal);
        Assert.Contains("PublicLandingController.cs", runbook, StringComparison.Ordinal);
        Assert.DoesNotContain("chummer-blazor", migrationLoop, StringComparison.Ordinal);
        Assert.Contains("docker-compose.public-edge.yml", migrationLoop, StringComparison.Ordinal);
        Assert.DoesNotContain("CHUMMER_PORTAL_DEV_AUTH_ENABLED", backlog, StringComparison.Ordinal);
        Assert.DoesNotContain("CHUMMER_PORTAL_REQUIRE_AUTH", backlog, StringComparison.Ordinal);
        Assert.Contains("Chummer.Run.Api", backlog, StringComparison.Ordinal);
    }
}
