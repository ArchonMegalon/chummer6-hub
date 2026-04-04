using Xunit;

namespace Chummer.Tests;

public sealed class ParityAuditLocalizationGateAliasDriftTests
{
    [Fact]
    public void AuditUiParityFailClosesLocalizationGateAliasDrift()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "audit-ui-parity.sh");
        string script = File.ReadAllText(scriptPath);

        Assert.Contains(
            "releaseProof.uiLocalizationReleaseGate alias values drift between uiLocalizationReleaseGate and ui_localization_release_gate",
            script,
            StringComparison.Ordinal);
    }

    [Fact]
    public void VerifyEntrypointMutatesLocalizationGateAliasDriftForNegativeCoverage()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "ai", "verify.sh");
        string script = File.ReadAllText(scriptPath);

        Assert.Contains(
            "reject conflicting alias values between releaseProof.uiLocalizationReleaseGate and releaseProof.ui_localization_release_gate",
            script,
            StringComparison.Ordinal);
    }

    [Fact]
    public void VerifyEntrypointMutatesLocalizationGateGeneratedAtAliasDriftForNegativeCoverage()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "ai", "verify.sh");
        string script = File.ReadAllText(scriptPath);

        Assert.Contains(
            "reject conflicting alias values between releaseProof.uiLocalizationReleaseGate.generatedAt and releaseProof.uiLocalizationReleaseGate.generated_at",
            script,
            StringComparison.Ordinal);
    }

    [Fact]
    public void VerifyEntrypointMutatesLocalizationGateSignoffStatusAliasForNegativeCoverage()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "ai", "verify.sh");
        string script = File.ReadAllText(scriptPath);

        Assert.Contains(
            "reject non-passing releaseProof.uiLocalizationReleaseGate.signoff_smoke_runner_status alias status",
            script,
            StringComparison.Ordinal);
    }
}
