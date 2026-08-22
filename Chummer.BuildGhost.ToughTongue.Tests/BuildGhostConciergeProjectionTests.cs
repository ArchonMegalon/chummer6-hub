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

        StringAssert.Contains(projection.CanonicalLane, "Tough Tongue");
        StringAssert.Contains(projection.ToughTongueStatus, "disabled");
        StringAssert.Contains(projection.RuntimeBoundary, "validated again");
    }

    [TestMethod]
    public void Concierge_reports_three_configured_slots_without_serializing_secrets()
    {
        BuildGhostConciergeProjection projection = Create(new Dictionary<string, string?>
        {
            ["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_REMOTE_ENABLED"] = "true",
            ["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CREDENTIAL_SLOT_1"] = "secret-one",
            ["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CREDENTIAL_SLOT_2"] = "secret-two",
            ["CHUMMER_BUILD_GHOST_TOUGH_TONGUE_CREDENTIAL_SLOT_3"] = "secret-three"
        }).Build();

        StringAssert.Contains(projection.ToughTongueStatus, "Three credential slots configured");
        Assert.IsFalse(JsonSerializer.Serialize(projection).Contains("secret-", StringComparison.Ordinal));
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
