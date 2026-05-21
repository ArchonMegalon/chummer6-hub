using Chummer.Control.Contracts.Support;

namespace Chummer.Run.Api.Services.Support;

public interface IChummerAssistantAdapter
{
    SupportAssistantResponse AskSupport(string? reporterUserId, string? reporterSubjectId, SupportAssistantRequest request);
    RuleSafeOutputGateResult HumanizeSafeRulesAnswer(RuleSafeAnswerPacket packet);
}
