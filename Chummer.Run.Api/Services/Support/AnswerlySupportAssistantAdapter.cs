using Chummer.Control.Contracts.Support;

namespace Chummer.Run.Api.Services.Support;

public sealed class AnswerlySupportAssistantAdapter : IChummerAssistantAdapter
{
    private readonly IFirstPartySupportAssistant _firstParty;
    private readonly AnswerlyRuntimePolicy _policy;
    private readonly RulesCoachRouter _router;
    private readonly AnswerlyHumanizerAdapter _humanizer;

    public AnswerlySupportAssistantAdapter(
        IFirstPartySupportAssistant firstParty,
        AnswerlyRuntimePolicy policy,
        RulesCoachRouter router,
        AnswerlyHumanizerAdapter humanizer)
    {
        _firstParty = firstParty;
        _policy = policy;
        _router = router;
        _humanizer = humanizer;
    }

    public SupportAssistantResponse AskSupport(string? reporterUserId, string? reporterSubjectId, SupportAssistantRequest request)
    {
        SupportAssistantResponse firstParty = _firstParty.Answer(reporterUserId, reporterSubjectId, request);
        RulesCoachRouteDecision decision = _router.Decide(request.Query);
        if (!_policy.CanUseSupportAdapter || !decision.AnswerlyAllowed || decision.RouteType != RulesCoachRouteTypes.SupportQuestion)
        {
            return firstParty;
        }

        string answer = firstParty.Answer;
        if (firstParty.Citations.Count > 0)
        {
            answer += " Grounding: " + string.Join(" | ", firstParty.Citations.Select(static item => item.Label).Take(2));
        }

        return firstParty with { Answer = answer };
    }

    public RuleSafeOutputGateResult HumanizeSafeRulesAnswer(RuleSafeAnswerPacket packet)
        => _humanizer.Humanize(packet);
}
