using Xunit;

namespace Chummer.Tests;

public sealed class ParityChecklistOrderingComplianceTests
{
    [Fact]
    public void ParityChecklistGeneratorAndVerifyLockCanonicalOracleOrdering()
    {
        string checklistScriptPath = RepoPaths.FromRoot("scripts", "generate-parity-checklist.sh");
        string checklistScript = File.ReadAllText(checklistScriptPath);
        Assert.Contains("must preserve canonical token ordering", checklistScript, StringComparison.Ordinal);

        string verifyScriptPath = RepoPaths.FromRoot("scripts", "ai", "verify.sh");
        string verifyScript = File.ReadAllText(verifyScriptPath);
        Assert.Contains(
            "parity checklist generator should reject non-canonical parity oracle token ordering",
            verifyScript,
            StringComparison.Ordinal);
    }
}
