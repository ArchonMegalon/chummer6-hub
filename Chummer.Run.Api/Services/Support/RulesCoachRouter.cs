using System.Security.Cryptography;
using System.Text;
using Chummer.Control.Contracts.Support;

namespace Chummer.Run.Api.Services.Support;

public sealed class RulesCoachRouter
{
    private static readonly char[] Separators =
    [
        ' ', '\t', '\r', '\n', '.', ',', ';', ':', '!', '?', '(', ')', '[', ']', '{', '}', '/', '\\', '-', '_', '"', '\''
    ];

    private static readonly string[] SupportTerms = ["install", "download", "status", "join", "faction", "email", "newsreel", "link", "support", "feedback", "report", "bug", "ghost", "compare", "apply"];
    private static readonly string[] RulesTerms = ["armor", "illegal", "karma", "modifier", "why", "cost", "calculation", "gear"];
    private static readonly string[] RawRulesTerms = ["quote", "full", "sourcebook", "page", "chapter", "list", "all", "table", "decking", "magic"];
    private static readonly string[] PrivateTerms = ["gm", "secret", "private", "campaign", "runner", "notes", "npc"];

    public RulesCoachRouteDecision Decide(string question, bool privateDataPresent = false)
    {
        string normalizedQuestion = string.IsNullOrWhiteSpace(question) ? string.Empty : question.Trim();
        HashSet<string> tokens = new(
            normalizedQuestion.Split(Separators, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                .Select(static item => item.ToLowerInvariant()));

        string routeType;
        bool answerlyAllowed;
        bool packetRequired;
        bool sourcebookRisk;
        bool fallbackRequired;

        if (privateDataPresent || PrivateTerms.Any(tokens.Contains))
        {
            routeType = RulesCoachRouteTypes.PrivateCampaignQuestion;
            answerlyAllowed = false;
            packetRequired = false;
            sourcebookRisk = false;
            fallbackRequired = true;
        }
        else if (RawRulesTerms.Any(tokens.Contains))
        {
            routeType = RulesCoachRouteTypes.RawRulesQuestion;
            answerlyAllowed = false;
            packetRequired = false;
            sourcebookRisk = true;
            fallbackRequired = true;
        }
        else if (SupportTerms.Any(tokens.Contains))
        {
            routeType = RulesCoachRouteTypes.SupportQuestion;
            answerlyAllowed = true;
            packetRequired = false;
            sourcebookRisk = false;
            fallbackRequired = false;
        }
        else if (RulesTerms.Any(tokens.Contains) || normalizedQuestion.StartsWith("why is my", StringComparison.OrdinalIgnoreCase))
        {
            routeType = RulesCoachRouteTypes.RulesCalculationQuestion;
            answerlyAllowed = true;
            packetRequired = true;
            sourcebookRisk = false;
            fallbackRequired = false;
        }
        else
        {
            routeType = RulesCoachRouteTypes.UnsupportedQuestion;
            answerlyAllowed = false;
            packetRequired = false;
            sourcebookRisk = false;
            fallbackRequired = true;
        }

        return new RulesCoachRouteDecision(
            RouteType: routeType,
            AnswerlyAllowed: answerlyAllowed,
            PacketRequired: packetRequired,
            PrivateDataPresent: privateDataPresent,
            SourcebookRisk: sourcebookRisk,
            FallbackRequired: fallbackRequired,
            ReceiptId: CreateReceiptId(normalizedQuestion, routeType));
    }

    public RuleSafeAnswerPacket BuildSafePacket(string question, string answer, IReadOnlyList<string> receiptIds)
    {
        RulesCoachRouteDecision decision = Decide(question);
        return new RuleSafeAnswerPacket(
            PacketId: CreateReceiptId(question, "packet"),
            QuestionId: CreateReceiptId(question, "question"),
            AccountScope: "anonymous",
            RulesetId: "unknown",
            AnswerType: decision.RouteType,
            Authority: decision.RouteType == RulesCoachRouteTypes.SupportQuestion ? "chummer-public-docs" : "chummer6-core",
            SafeSummary: answer,
            CalculationSteps: Array.Empty<RuleSafeCalculationStep>(),
            SourceAnchors: Array.Empty<RuleSafeSourceAnchor>(),
            ReceiptIds: receiptIds,
            Confidence: decision.FallbackRequired ? "unsupported" : "medium",
            ForbiddenToAnswerly: ["sourcebook_text", "sourcebook_tables", "private_campaign_state", "support_case_body", "secrets"],
            HumanizerInstruction: "Humanize only the safe summary and calculation steps. Do not add rules, quotes, tables, or mechanics.",
            FallbackMessage: "Chummer cannot answer this as rules truth yet. I can create a verification ticket.");
    }

    private static string CreateReceiptId(string input, string category)
    {
        byte[] hash = SHA256.HashData(Encoding.UTF8.GetBytes($"{category}:{input}"));
        return $"{category}-{Convert.ToHexString(hash)[..16].ToLowerInvariant()}";
    }
}
