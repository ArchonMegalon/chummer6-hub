using Xunit;

namespace Chummer.Tests;

public sealed class ParityAuditLocaleSummaryRowContractTests
{
    [Fact]
    public void AuditUiParityFailClosesLocaleSummaryRowContractDrift()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "audit-ui-parity.sh");
        string script = File.ReadAllText(scriptPath);

        Assert.Contains(
            "release-channel nested receipt releaseProof.uiLocalizationReleaseGate.localeSummary rows are missing required keys",
            script,
            StringComparison.Ordinal);
        Assert.Contains(
            "release-channel nested receipt releaseProof.uiLocalizationReleaseGate.localeSummary rows have unexpected keys",
            script,
            StringComparison.Ordinal);
        Assert.Contains(
            "release-channel nested receipt releaseProof.uiLocalizationReleaseGate.localeSummary missingReleaseSeedKeys must be an empty list",
            script,
            StringComparison.Ordinal);
        Assert.Contains(
            "release-channel nested receipt releaseProof.uiLocalizationReleaseGate.localeSummary overrideCount must be >= minimumOverrideCount",
            script,
            StringComparison.Ordinal);
    }

    [Fact]
    public void VerifyEntrypointMutatesLocaleSummaryRowContractForNegativeCoverage()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "ai", "verify.sh");
        string script = File.ReadAllText(scriptPath);

        Assert.Contains(
            "verify gate failed: parity audit should reject non-empty releaseProof.uiLocalizationReleaseGate.localeSummary missingReleaseSeedKeys.",
            script,
            StringComparison.Ordinal);
        Assert.Contains(
            "verify gate failed: parity audit should reject unexpected releaseProof.uiLocalizationReleaseGate.localeSummary row keys.",
            script,
            StringComparison.Ordinal);
    }
}
