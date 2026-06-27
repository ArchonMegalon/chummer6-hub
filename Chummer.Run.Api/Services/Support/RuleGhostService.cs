using Chummer.Control.Contracts.Support;
using Chummer.Run.Api.Contracts;

namespace Chummer.Run.Api.Services.Support;

public sealed class RuleGhostService
{
    public const int MaxQueryLength = 2000;
    public const int MaxPreferredRulesetLength = 16;
    public const int MaxRequestBodyBytes = 16 * 1024;

    private static readonly string[] RefusalTerms = ["quote", "verbatim", "full text", "page ", "chapter ", "table ", "scan", "pdf", "list every"];
    private static readonly string[] PrivateTerms = ["gm only", "secret", "private campaign", "hidden npc", "runner note"];
    private static readonly string[] AmbiguousTerms = ["edge", "initiative", "matrix", "magic", "drain", "glitch", "armor", "damage", "availability"];
    private static readonly string[] Sr5Hints = ["sr5", "5e", "fifth edition", "fifth"];
    private static readonly string[] Sr6Hints = ["sr6", "6e", "sixth world", "sixth edition", "sixth"];

    private readonly AnswerlyHumanizerAdapter _humanizer;

    public RuleGhostService(AnswerlyHumanizerAdapter humanizer)
    {
        _humanizer = humanizer;
    }

    public RuleGhostResponse Ask(string query, string? preferredRuleset = null)
    {
        string normalized = NormalizeOptional(query, nameof(query), MaxQueryLength) ?? string.Empty;
        string? normalizedPreferredRuleset = NormalizeOptional(preferredRuleset, nameof(preferredRuleset), MaxPreferredRulesetLength);
        string lowered = normalized.ToLowerInvariant();
        string rulesetId = ResolveRuleset(normalizedPreferredRuleset, lowered);

        if (string.IsNullOrWhiteSpace(normalized))
        {
            return Clarify(
                rulesetId,
                "Tell me the edition, the action, and the specific mechanic you want summarized.",
                [
                    "What edition are you using: SR5 or SR6?",
                    "What action are you trying to resolve?",
                    "What part feels unclear right now?"
                ]);
        }

        if (PrivateTerms.Any(lowered.Contains))
        {
            return Refuse(
                rulesetId,
                "I can help with public rules summaries, but I should not infer private campaign state or hidden GM material.",
                "Core privacy boundary",
                "Private campaign and hidden-GM material stays outside support answers.");
        }

        if (RefusalTerms.Any(lowered.Contains))
        {
            return Refuse(
                rulesetId,
                "I can explain the rule in my own words, but I will not reproduce book wording or structured mechanic grids. Ask for the mechanic and edition instead.",
                "Owned-rule summary only",
                "Rules help summarizes owned material instead of reproducing it.");
        }

        if (rulesetId == "auto" && AmbiguousTerms.Any(lowered.Contains))
        {
            return Clarify(
                rulesetId,
                "That mechanic changes enough between SR5 and SR6 that I should not guess. Tell me the edition and I will summarize the rule path in plain language.",
                [
                    "Say SR5 or SR6 first.",
                    "Describe the specific action or test.",
                    "Mention whether you want a quick summary or a worked example."
                ]);
        }

        if (lowered.Contains("initiative"))
        {
            return SafeAnswer(
                normalized,
                rulesetId,
                rulesetId == "sr5"
                    ? "In SR5, initiative is mainly about how often you act in a pass and how quickly your score falls as passes advance. Build the score from your relevant initiative stats plus the normal edition-specific roll, then act from highest to lowest and reduce the score between passes."
                    : rulesetId == "sr6"
                        ? "In SR6, initiative is still turn order, but the flow is flatter and easier to read at the table than older pass-heavy loops. Build the score from the edition's initiative pieces, sort from highest to lowest, and resolve actions in order while using the current round structure."
                        : "Initiative decides action order, but the exact loop changes between SR5 and SR6. If you tell me the edition, I can summarize the concrete sequence in plain language.",
                InitiativeCitations(rulesetId),
                "medium");
        }

        if (lowered.Contains("edge"))
        {
            return SafeAnswer(
                normalized,
                rulesetId,
                rulesetId == "sr5"
                    ? "In SR5, Edge is a scarce luck resource that lets you improve important rolls or rescue a bad situation. Treat it as a limited boost you save for high-impact moments."
                    : rulesetId == "sr6"
                        ? "In SR6, Edge is much more active and is meant to move in and out during play when positioning, gear, and circumstance matter. Think of it as the edition's momentum currency rather than a once-in-a-while panic button."
                        : "Edge exists in both editions, but SR5 uses it more like a limited luck reserve while SR6 expects it to flow more actively during play.",
                EdgeCitations(rulesetId),
                "medium");
        }

        if (lowered.Contains("glitch"))
        {
            return SafeAnswer(
                normalized,
                rulesetId,
                "A glitch is the game's sign that the attempt technically resolved but something went sideways. When it happens, keep the main outcome in view and add a complication, cost, or messy side effect instead of treating it as a separate rule universe.",
                CommonCoreCitations(rulesetId, "Core test resolution", "Glitches are best treated as messy success-or-failure complications, not as a total rules reset."),
                "medium");
        }

        if (lowered.Contains("drain") || lowered.Contains("fade"))
        {
            return SafeAnswer(
                normalized,
                rulesetId,
                "Drain or Fade is the cost that pushes back after magical or resonance-heavy actions. Resolve the effect first, then handle the backlash with the edition's resistance procedure and apply the remaining consequence if the resistance is not enough.",
                CommonCoreCitations(rulesetId, "Magic and backlash", "Backlash is the balancing cost after the main effect resolves."),
                "medium");
        }

        if (lowered.Contains("matrix") || lowered.Contains("overwatch"))
        {
            return SafeAnswer(
                normalized,
                rulesetId,
                rulesetId == "auto"
                    ? "Matrix play changes enough between editions that you should tell me SR5 or SR6 before I summarize the sequence. Once you do, I can break down the loop into plain-language steps."
                    : "For Matrix questions, the safe shortcut is to think in three layers: what action you are attempting, what system resists it, and what long-tail risk or trace pressure you build by staying active too long. Tell me the exact Matrix action and I can summarize that path cleanly.",
                CommonCoreCitations(rulesetId, "Matrix action flow", "Matrix answers stay safer when we reduce them to action, resistance, and trace pressure."),
                rulesetId == "auto" ? "needs_edition" : "medium");
        }

        if (lowered.Contains("damage") || lowered.Contains("wound"))
        {
            return SafeAnswer(
                normalized,
                rulesetId,
                "Damage usually matters twice: once when you resist the incoming hit and again when accumulated injury starts dragging down later performance. Track the boxes cleanly, then apply the edition's penalty posture only after enough injury has piled up.",
                CommonCoreCitations(rulesetId, "Damage and wound pressure", "Damage changes both survival and later effectiveness."),
                "medium");
        }

        if (lowered.Contains("availability") || lowered.Contains("illegal") || lowered.Contains("gear"))
        {
            return SafeAnswer(
                normalized,
                rulesetId,
                "For gear questions, separate three things: whether the item is allowed at your table stage, how hard it is to legally obtain, and what hidden upkeep or license pressure it creates later. If you name the item and edition, I can summarize the practical answer instead of guessing.",
                CommonCoreCitations(rulesetId, "Gear acquisition posture", "Acquisition is easier to summarize when the item and edition are explicit."),
                "medium");
        }

        return Clarify(
            rulesetId,
            "I can help, but I need the edition and the exact mechanic or action you want summarized.",
            [
                "Start with SR5 or SR6.",
                "Name the action, spell, Matrix move, or gear item.",
                "Tell me whether you want the short answer or a step-by-step summary."
            ]);
    }

    private RuleGhostResponse SafeAnswer(
        string question,
        string rulesetId,
        string answer,
        IReadOnlyList<RuleGhostCitation> citations,
        string confidence)
    {
        RuleSafeAnswerPacket packet = new(
            PacketId: $"rule-ghost-{Guid.NewGuid():N}",
            QuestionId: $"question-{Guid.NewGuid():N}",
            AccountScope: "anonymous",
            RulesetId: rulesetId,
            AnswerType: RulesCoachRouteTypes.RulesCalculationQuestion,
            Authority: "chummer6-rule-ghost",
            SafeSummary: answer,
            CalculationSteps: Array.Empty<RuleSafeCalculationStep>(),
            SourceAnchors: Array.Empty<RuleSafeSourceAnchor>(),
            ReceiptIds: citations.Select(static item => item.SourceLabel).ToArray(),
            Confidence: confidence,
            ForbiddenToAnswerly: ["sourcebook_text", "sourcebook_tables", "private_campaign_state", "secrets"],
            HumanizerInstruction: "Paraphrase the safe rules summary without reproducing book wording, pages, or tables.",
            FallbackMessage: "I can give a safe summary once you narrow the edition and mechanic.");
        RuleSafeOutputGateResult result = _humanizer.Humanize(packet);
        string safeAnswer = result.Allowed ? result.Output : packet.FallbackMessage;
        return new RuleGhostResponse(
            Answer: safeAnswer,
            Confidence: confidence,
            RulesetId: rulesetId,
            ClarificationNeeded: false,
            Refused: !result.Allowed,
            Citations: citations,
            SafeFollowUps:
            [
                "Tell me the edition if you want the tighter answer.",
                "Name the exact action or item if you want a sharper summary."
            ]);
    }

    private static RuleGhostResponse Clarify(string rulesetId, string answer, IReadOnlyList<string> followUps)
        => new(
            Answer: answer,
            Confidence: "needs_edition",
            RulesetId: rulesetId,
            ClarificationNeeded: true,
            Refused: false,
            Citations: Array.Empty<RuleGhostCitation>(),
            SafeFollowUps: followUps);

    private static RuleGhostResponse Refuse(string rulesetId, string answer, string label, string summary)
        => new(
            Answer: answer,
            Confidence: "policy_refusal",
            RulesetId: rulesetId,
            ClarificationNeeded: false,
            Refused: true,
            Citations: [new RuleGhostCitation(label, "Safe summary boundary", summary)],
            SafeFollowUps:
            [
                "Ask for a plain-language summary instead.",
                "Tell me the edition and the single mechanic you need."
            ]);

    private static IReadOnlyList<RuleGhostCitation> InitiativeCitations(string rulesetId)
        => rulesetId == "sr5"
            ? [
                new RuleGhostCitation("Shadowrun Fifth Edition Core Rulebook", "Initiative and action passes", "Your owned SR5 core book is the right anchor for pass-based initiative order."),
                new RuleGhostCitation("Shadowrun 5D - Grundregelwerk", "Initiative und Durchgaenge", "Your German SR5 core copy can be used as the same mechanical anchor.")
            ]
            : [
                new RuleGhostCitation("Shadowrun Sixth World", "Initiative and combat round flow", "Your owned SR6 core book is the right anchor for the flatter turn-order loop.")
            ];

    private static IReadOnlyList<RuleGhostCitation> EdgeCitations(string rulesetId)
        => rulesetId == "sr5"
            ? [
                new RuleGhostCitation("Shadowrun Fifth Edition Core Rulebook", "Edge attribute usage", "SR5 treats Edge as a limited high-impact luck resource.")
            ]
            : rulesetId == "sr6"
                ? [
                    new RuleGhostCitation("Shadowrun Sixth World", "Edge gain and spend loop", "SR6 expects Edge to move more actively during play.")
                ]
                : [
                    new RuleGhostCitation("Shadowrun Fifth Edition Core Rulebook", "Edge attribute usage", "SR5 uses Edge more sparingly."),
                    new RuleGhostCitation("Shadowrun Sixth World", "Edge gain and spend loop", "SR6 uses Edge more actively.")
                ];

    private static IReadOnlyList<RuleGhostCitation> CommonCoreCitations(string rulesetId, string sectionHint, string summary)
        => rulesetId == "sr6"
            ? [new RuleGhostCitation("Shadowrun Sixth World", sectionHint, summary)]
            : rulesetId == "sr5"
                ? [new RuleGhostCitation("Shadowrun Fifth Edition Core Rulebook", sectionHint, summary)]
                : [
                    new RuleGhostCitation("Shadowrun Fifth Edition Core Rulebook", sectionHint, summary),
                    new RuleGhostCitation("Shadowrun Sixth World", sectionHint, "The same topic exists in your SR6 core book, but the exact procedure may differ.")
                ];

    private static string ResolveRuleset(string? preferredRuleset, string loweredQuestion)
    {
        string normalized = (preferredRuleset ?? string.Empty).Trim().ToLowerInvariant();
        if (normalized is "sr5" or "5e" or "fifth")
        {
            return "sr5";
        }

        if (normalized is "sr6" or "6e" or "sixth")
        {
            return "sr6";
        }

        if (Sr5Hints.Any(loweredQuestion.Contains))
        {
            return "sr5";
        }

        if (Sr6Hints.Any(loweredQuestion.Contains))
        {
            return "sr6";
        }

        return "auto";
    }

    private static string? NormalizeOptional(string? value, string parameterName, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string normalized = value.Trim();
        if (normalized.Length > maxLength)
        {
            throw new ArgumentException(
                $"{parameterName} exceeds the maximum length of {maxLength} characters.",
                parameterName);
        }

        return normalized;
    }
}
