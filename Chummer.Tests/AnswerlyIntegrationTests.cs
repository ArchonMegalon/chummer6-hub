using Chummer.Control.Contracts.Support;
using Chummer.Run.Api.Services.Support;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class RuleSafeOutputGateTests
{
    [Fact]
    public void Enforce_BlocksProviderNameLeak()
    {
        RuleSafeAnswerPacket packet = Packet(answerType: RulesCoachRouteTypes.RulesCalculationQuestion);
        RuleSafeOutputGate gate = new();

        RuleSafeOutputGateResult result = gate.Enforce(packet, "Answerly says to quote the sourcebook.");

        Assert.False(result.Allowed);
        Assert.Contains("provider_names", result.BlockingReasons);
        Assert.Equal(packet.FallbackMessage, result.Output);
    }

    [Fact]
    public void Enforce_AllowsSafeSummary()
    {
        RuleSafeAnswerPacket packet = Packet(answerType: RulesCoachRouteTypes.RulesCalculationQuestion);
        RuleSafeOutputGate gate = new();

        RuleSafeOutputGateResult result = gate.Enforce(packet, "Armor stays at 12 because the equipped item is active.");

        Assert.True(result.Allowed);
        Assert.Empty(result.BlockingReasons);
    }

    private static RuleSafeAnswerPacket Packet(string answerType)
        => new(
            PacketId: "packet-1",
            QuestionId: "question-1",
            AccountScope: "anonymous",
            RulesetId: "sr6",
            AnswerType: answerType,
            Authority: "chummer6-core",
            SafeSummary: "Safe summary.",
            CalculationSteps: Array.Empty<RuleSafeCalculationStep>(),
            SourceAnchors: Array.Empty<RuleSafeSourceAnchor>(),
            ReceiptIds: ["receipt-1"],
            Confidence: "medium",
            ForbiddenToAnswerly: ["sourcebook_text"],
            HumanizerInstruction: "Humanize only safe summary.",
            FallbackMessage: "Fallback.");
}

public sealed class RulesCoachRouterTests
{
    [Fact]
    public void Decide_RoutesSupportQuestionToSupportAssistant()
    {
        RulesCoachRouter router = new();

        RulesCoachRouteDecision result = router.Decide("How do I install the mac build and get the newsreel email?");

        Assert.Equal(RulesCoachRouteTypes.SupportQuestion, result.RouteType);
        Assert.True(result.AnswerlyAllowed);
        Assert.False(result.PacketRequired);
    }

    [Fact]
    public void Decide_FailClosesRawRulesQuestions()
    {
        RulesCoachRouter router = new();

        RulesCoachRouteDecision result = router.Decide("Quote the full decking rules from the sourcebook.");

        Assert.Equal(RulesCoachRouteTypes.RawRulesQuestion, result.RouteType);
        Assert.False(result.AnswerlyAllowed);
        Assert.True(result.SourcebookRisk);
        Assert.True(result.FallbackRequired);
    }
}

public sealed class AnswerlySupportAssistantAdapterTests
{
    [Fact]
    public void AskSupport_FallsBackWhenProviderIsDisabled()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>())
            .Build();
        AnswerlySupportAssistantAdapter adapter = new(
            new StubFirstPartySupportAssistant(),
            new AnswerlyRuntimePolicy(configuration),
            new RulesCoachRouter(),
            new AnswerlyHumanizerAdapter(new AnswerlyRuntimePolicy(configuration), new RuleSafeOutputGate()));

        SupportAssistantResponse response = adapter.AskSupport("user-1", "subject-1", new SupportAssistantRequest("How do I install this?"));

        Assert.Equal("First-party answer.", response.Answer);
    }

    [Fact]
    public void HumanizeSafeRulesAnswer_UsesFallbackWhenUnverified()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["ANSWERLY_ENABLED"] = "true",
                ["ANSWERLY_HUMANIZER_ENABLED"] = "true",
                ["ANSWERLY_PROVIDER_VERIFICATION_STATE"] = "unverified"
            })
            .Build();
        AnswerlySupportAssistantAdapter adapter = new(
            new StubFirstPartySupportAssistant(),
            new AnswerlyRuntimePolicy(configuration),
            new RulesCoachRouter(),
            new AnswerlyHumanizerAdapter(new AnswerlyRuntimePolicy(configuration), new RuleSafeOutputGate()));

        RuleSafeOutputGateResult result = adapter.HumanizeSafeRulesAnswer(
            new RuleSafeAnswerPacket(
                PacketId: "packet-2",
                QuestionId: "question-2",
                AccountScope: "anonymous",
                RulesetId: "sr6",
                AnswerType: RulesCoachRouteTypes.RulesCalculationQuestion,
                Authority: "chummer6-core",
                SafeSummary: "Armor is 12.",
                CalculationSteps: [new RuleSafeCalculationStep("Armor", "12", "engine")],
                SourceAnchors: Array.Empty<RuleSafeSourceAnchor>(),
                ReceiptIds: ["receipt-2"],
                Confidence: "high",
                ForbiddenToAnswerly: ["sourcebook_text"],
                HumanizerInstruction: "Humanize only safe summary.",
                FallbackMessage: "Fallback humanizer message."));

        Assert.False(result.Allowed);
        Assert.Equal("Fallback humanizer message.", result.Output);
    }

    private sealed class StubFirstPartySupportAssistant : IFirstPartySupportAssistant
    {
        public SupportAssistantResponse Answer(string? reporterUserId, string? reporterSubjectId, SupportAssistantRequest request)
            => new(
                "First-party answer.",
                SupportAssistantConfidenceLevels.CanonHelp,
                false,
                [new SupportAssistantCitation("canon_doc", "Install help", "Use the installer.")],
                [new SupportAssistantAction("open_support", "Open support", "/contact", "Escalate if needed.")]);
    }
}
