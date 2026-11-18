using Chummer.Run.Api.Services.KarmaForge;
using Chummer.Run.Api.Services.Support;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using System.Text.Json;

namespace Chummer.BuildGhost.ToughTongue.Tests;

[TestClass]
public sealed class BuildGhostConciergeProjectionTests
{
    [TestMethod]
    public void Concierge_reports_remote_disabled_as_the_default_posture()
    {
        BuildGhostConciergeProjection projection = Create(new Dictionary<string, string?>()).Build();

        StringAssert.Contains(projection.CanonicalLane, "Rook");
        StringAssert.Contains(projection.CanonicalLane, "VidBoard");
        StringAssert.Contains(projection.ToughTongueStatus, "unavailable");
        StringAssert.Contains(projection.RuntimeBoundary, "explicit live-support escalation");
        Assert.HasCount(3, projection.DefaultSupportResponsibilities);
    }

    [TestMethod]
    public void Concierge_reports_live_support_as_capability_gated_without_serializing_configuration()
    {
        BuildGhostConciergeProjection projection = Create(new Dictionary<string, string?>
        {
            ["CHUMMER_BUILD_GHOST_LIVE_SUPPORT_REMOTE_EXECUTION_ENABLED"] = "true",
            ["CHUMMER_BUILD_GHOST_LIVE_SUPPORT_CAPABILITY_RECEIPT_PATH"] = "/private/live-support-receipt.json",
            ["CHUMMER_AI_INTERNAL_API_TOKEN"] = "secret-live-support-configuration-value"
        }).Build();

        StringAssert.Contains(projection.ToughTongueStatus, "capability-gated");
        Assert.IsFalse(JsonSerializer.Serialize(projection).Contains("secret-live-support", StringComparison.Ordinal));
        Assert.HasCount(3, projection.ToughTongueResponsibilities);
    }

    private static BuildGhostConciergeService Create(IReadOnlyDictionary<string, string?> values)
    {
        IConfiguration configuration = new ConfigurationBuilder().AddInMemoryCollection(values).Build();
        AnswerlyRuntimePolicy policy = new(configuration);
        return new BuildGhostConciergeService(
            configuration,
            policy,
            new AnswerlyHumanizerAdapter(policy, new RuleSafeOutputGate()));
    }
}
