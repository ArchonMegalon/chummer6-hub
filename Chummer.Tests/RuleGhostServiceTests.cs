using Chummer.Run.Api.Services.Support;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class RuleGhostServiceTests
{
    [Fact]
    public void Ask_RefusesBookWordingRequests()
    {
        RuleGhostService service = CreateService();

        var response = service.Ask("Quote the full matrix chapter from SR6.");

        Assert.True(response.Refused);
        Assert.DoesNotContain("sourcebook", response.Answer, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("page", response.Answer, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Rule Ghost", response.Citations[0].Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Rules help", response.Citations[0].Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void Ask_AsksForEditionWhenQuestionIsAmbiguous()
    {
        RuleGhostService service = CreateService();

        var response = service.Ask("How does Edge work?");

        Assert.True(response.ClarificationNeeded);
        Assert.Equal("needs_edition", response.Confidence);
    }

    [Fact]
    public void Ask_ReturnsSafeParaphraseForRecognizedRulesQuestion()
    {
        RuleGhostService service = CreateService();

        var response = service.Ask("In SR5, what is Edge for?");

        Assert.False(response.Refused);
        Assert.False(response.ClarificationNeeded);
        Assert.Equal("sr5", response.RulesetId);
        Assert.Contains("luck", response.Answer, StringComparison.OrdinalIgnoreCase);
        Assert.NotEmpty(response.Citations);
    }

    private static RuleGhostService CreateService()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ANSWERLY_ENABLED"] = "true",
                ["ANSWERLY_HUMANIZER_ENABLED"] = "true",
                ["ANSWERLY_PROVIDER_VERIFICATION_STATE"] = AnswerlyRuntimePolicy.VerifiedFullAdapter
            })
            .Build();

        return new RuleGhostService(
            new AnswerlyHumanizerAdapter(new AnswerlyRuntimePolicy(configuration), new RuleSafeOutputGate()));
    }
}
