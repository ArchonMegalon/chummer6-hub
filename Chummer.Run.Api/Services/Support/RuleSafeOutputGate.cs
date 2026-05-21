using System.Text.RegularExpressions;
using Chummer.Control.Contracts.Support;

namespace Chummer.Run.Api.Services.Support;

public sealed class RuleSafeOutputGate
{
    private static readonly Regex EmailPattern = new(@"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly string[] ProviderTerms = ["answerly", "api key", "api-key", "widget token", "answerly_"];
    private static readonly string[] SourcebookTerms = ["sourcebook", "pdf", "page ", "chapter ", "table ", "quote "];
    private static readonly string[] PrivateTerms = ["gm only", "secret npc", "private campaign", "support case body", "runner note"];

    public RuleSafeOutputGateResult Enforce(RuleSafeAnswerPacket packet, string? candidateOutput)
    {
        string output = string.IsNullOrWhiteSpace(candidateOutput)
            ? packet.FallbackMessage
            : candidateOutput.Trim();
        List<string> blockingReasons = new();
        string normalized = output.ToLowerInvariant();

        if (packet.AnswerType == RulesCoachRouteTypes.UnsupportedQuestion)
        {
            blockingReasons.Add("unsupported_answer_type");
        }

        if (ProviderTerms.Any(normalized.Contains))
        {
            blockingReasons.Add("provider_names");
        }

        if (SourcebookTerms.Any(normalized.Contains))
        {
            blockingReasons.Add("sourcebook_terms");
        }

        if (PrivateTerms.Any(normalized.Contains) || EmailPattern.IsMatch(output))
        {
            blockingReasons.Add("private_data");
        }

        if (output.Contains('|') || output.Contains("\t"))
        {
            blockingReasons.Add("copied_tables");
        }

        return blockingReasons.Count == 0
            ? new RuleSafeOutputGateResult(true, output, Array.Empty<string>())
            : new RuleSafeOutputGateResult(false, packet.FallbackMessage, blockingReasons);
    }
}
