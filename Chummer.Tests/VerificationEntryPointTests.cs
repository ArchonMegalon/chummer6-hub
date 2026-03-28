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
}
