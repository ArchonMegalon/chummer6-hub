using Chummer.Control.Contracts.Support;

namespace Chummer.Run.Api.Services.Support;

public sealed class AnswerlyHumanizerAdapter
{
    private readonly AnswerlyRuntimePolicy _policy;
    private readonly RuleSafeOutputGate _outputGate;

    public AnswerlyHumanizerAdapter(AnswerlyRuntimePolicy policy, RuleSafeOutputGate outputGate)
    {
        _policy = policy;
        _outputGate = outputGate;
    }

    public RuleSafeOutputGateResult Humanize(RuleSafeAnswerPacket packet)
    {
        if (!_policy.CanUseHumanizer)
        {
            return new RuleSafeOutputGateResult(false, packet.FallbackMessage, ["answerly_humanizer_unavailable"]);
        }

        string candidate = packet.SafeSummary;
        if (packet.CalculationSteps.Count > 0)
        {
            candidate = packet.SafeSummary + " " + string.Join(
                " ",
                packet.CalculationSteps.Select(step => $"{step.Label}: {step.Value}."));
        }

        return _outputGate.Enforce(packet, candidate);
    }
}
