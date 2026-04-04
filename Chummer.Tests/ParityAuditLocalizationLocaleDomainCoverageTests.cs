using Xunit;

namespace Chummer.Tests;

public sealed class ParityAuditLocalizationLocaleDomainCoverageTests
{
    [Fact]
    public void AuditUiParityFailClosesUnexpectedLocaleDomainCoverageDomains()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "audit-ui-parity.sh");
        string script = File.ReadAllText(scriptPath);

        Assert.Contains(
            "releaseProof.uiLocalizationReleaseGate.localeDomainCoverage locale has unexpected domains",
            script,
            StringComparison.Ordinal);
    }

    [Fact]
    public void VerifyEntrypointMutatesUnexpectedLocaleDomainCoverageDomainKeys()
    {
        string scriptPath = RepoPaths.FromRoot("scripts", "ai", "verify.sh");
        string script = File.ReadAllText(scriptPath);

        Assert.Contains(
            "bonus_noncanonical_domain",
            script,
            StringComparison.Ordinal);
        Assert.Contains(
            "reject unexpected releaseProof.uiLocalizationReleaseGate.localeDomainCoverage locale domain keys",
            script,
            StringComparison.Ordinal);
    }
}
