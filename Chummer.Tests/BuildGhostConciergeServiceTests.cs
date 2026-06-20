using Chummer.Run.Api.Services.KarmaForge;
using Chummer.Run.Api.Services.Support;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class BuildGhostConciergeServiceTests
{
    [Fact]
    public void Build_UsesConfiguredFacePopPathAndReadyHumanizerWhenVerified()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_KARMA_FORGE_FACEPOP_PUBLIC_INVITE_PATH"] = "/facepop/build-ghosts",
                ["ANSWERLY_ENABLED"] = "true",
                ["ANSWERLY_HUMANIZER_ENABLED"] = "true",
                ["ANSWERLY_PROVIDER_VERIFICATION_STATE"] = AnswerlyRuntimePolicy.VerifiedFullAdapter
            })
            .Build();
        BuildGhostConciergeService service = CreateService(configuration);

        BuildGhostConciergeProjection projection = service.Build();

        Assert.Equal("/facepop/build-ghosts", projection.FacePopEntryHref);
        Assert.Equal("Limited explainer fail-closed", projection.AnswerlyStatus);
        Assert.Equal("First-party compare/apply only", projection.EngineStatus);
        Assert.Contains("A short intake can", projection.HumanizedSummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(projection.Actions, item => string.Equals(item.Href, "/participate/karma-forge?track=player_trust_track", StringComparison.Ordinal));
    }

    [Fact]
    public void Build_FallsBackCleanlyWhenAnswerlyHumanizerIsUnavailable()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>())
            .Build();
        BuildGhostConciergeService service = CreateService(configuration);

        BuildGhostConciergeProjection projection = service.Build();

        Assert.Equal("/participate", projection.FacePopEntryHref);
        Assert.Equal("Fallback explainer only", projection.AnswerlyStatus);
        Assert.Contains("A short intake can", projection.HumanizedSummary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("legality", projection.RuntimeBoundary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Build_NormalizesRelativeFacePopPathToLeadingSlash()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_KARMA_FORGE_FACEPOP_PUBLIC_INVITE_PATH"] = "facepop/build-ghosts"
            })
            .Build();
        BuildGhostConciergeService service = CreateService(configuration);

        BuildGhostConciergeProjection projection = service.Build();

        Assert.Equal("/facepop/build-ghosts", projection.FacePopEntryHref);
    }

    private static BuildGhostConciergeService CreateService(IConfiguration configuration)
    {
        AnswerlyRuntimePolicy policy = new(configuration);
        RuleSafeOutputGate gate = new();
        AnswerlyHumanizerAdapter humanizer = new(policy, gate);
        return new BuildGhostConciergeService(configuration, policy, humanizer);
    }
}
