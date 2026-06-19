using Chummer.Control.Contracts.Support;
using Chummer.Run.Api.Services.Support;

namespace Chummer.Run.Api.Services.KarmaForge;

public sealed record BuildGhostConciergeActionProjection(
    string Label,
    string Href,
    string Tone,
    string Summary);

public sealed record BuildGhostConciergeProjection(
    string FacePopEntryHref,
    string FacePopStatus,
    string AnswerlyStatus,
    string EngineStatus,
    string HumanizedSummary,
    string CanonicalLane,
    string RuntimeBoundary,
    IReadOnlyList<string> FacePopResponsibilities,
    IReadOnlyList<string> AnswerlyResponsibilities,
    IReadOnlyList<string> ChummerResponsibilities,
    IReadOnlyList<string> CompareArtifacts,
    string ClientReportHref,
    string PublicFeedbackHref,
    IReadOnlyList<BuildGhostConciergeActionProjection> Actions);

public sealed class BuildGhostConciergeService
{
    private const string FacePopPublicInvitePathConfigKey = "CHUMMER_KARMA_FORGE_FACEPOP_PUBLIC_INVITE_PATH";

    private readonly IConfiguration _configuration;
    private readonly AnswerlyRuntimePolicy _answerlyPolicy;
    private readonly AnswerlyHumanizerAdapter _humanizer;

    public BuildGhostConciergeService(
        IConfiguration configuration,
        AnswerlyRuntimePolicy answerlyPolicy,
        AnswerlyHumanizerAdapter humanizer)
    {
        _configuration = configuration;
        _answerlyPolicy = answerlyPolicy;
        _humanizer = humanizer;
    }

    public BuildGhostConciergeProjection Build()
    {
        string facePopHref = NormalizeConfiguredPath(_configuration[FacePopPublicInvitePathConfigKey]) ?? "/participate";
        RuleSafeAnswerPacket packet = new(
            PacketId: "build-ghost-concierge",
            QuestionId: "build-ghost-entry",
            AccountScope: "public",
            RulesetId: "build_ghost",
            AnswerType: "support_question",
            Authority: "chummer6-build-ghost-boundary",
            SafeSummary: "The character helper is a guided preview. A short intake can route a builder into the right Chummer path. A plain-language explainer can describe what the preview means. Chummer still owns draft creation, comparison, checks, legality explanation, and the final apply decision.",
            CalculationSteps:
            [
                new RuleSafeCalculationStep("Entry", "Public concierge asks what changed and what the builder wants to compare", "facepop_concierge_boundary"),
                new RuleSafeCalculationStep("Explain", "Plain-language explainer summarizes the preview without becoming mechanics truth", "answerly_humanizer_boundary"),
                new RuleSafeCalculationStep("Truth", "Chummer creates drafts, compares them, checks them, and applies only reviewed variants", "alice_build_ghost_lab")
            ],
            SourceAnchors: Array.Empty<RuleSafeSourceAnchor>(),
            ReceiptIds: ["build_ghost_lab", "alice_horizon"],
            Confidence: "bounded",
            ForbiddenToAnswerly: ["mechanics_truth", "legality_truth", "apply_truth", "runner_mutation"],
            HumanizerInstruction: "Explain the character-helper split in plain language without claiming runtime truth.",
            FallbackMessage: "A short intake can greet the builder, the explainer can clarify the preview, and Chummer still owns the actual compare and apply decision.");
        RuleSafeOutputGateResult humanized = _humanizer.Humanize(packet);
        string answerlyStatus = _answerlyPolicy.CanUseHumanizer
            ? "Bounded explainer fail-closed"
            : "Fallback explainer only";
        const string clientReportHref = "/contact?kind=bug_report&title=Build%20Ghost%20report&summary=Build%20Ghost%20compare%20or%20apply%20did%20not%20behave%20as%20expected.&runtime=alice_build_ghost_lab&bundle=build_ghost&sceneId=build-ghost";
        const string publicFeedbackHref = "/feedback?topic=build-ghosts";

        return new BuildGhostConciergeProjection(
            FacePopEntryHref: facePopHref,
            FacePopStatus: "Public concierge only",
            AnswerlyStatus: answerlyStatus.Replace("Bounded", "Limited", StringComparison.OrdinalIgnoreCase),
            EngineStatus: "First-party compare/apply only",
            HumanizedSummary: packet.FallbackMessage,
            CanonicalLane: "Short intake -> plain-language explanation -> Chummer character compare bench",
            RuntimeBoundary: "Neither the public concierge nor the bounded explainer may compute legality, mutate the runner, or become apply truth.",
            FacePopResponsibilities:
            [
                "Greet the builder and ask which runner decision needs comparison.",
                "Route the builder into the right first-party entry lane.",
                "Collect only lightweight public-safe intake signal."
            ],
            AnswerlyResponsibilities:
            [
                "Paraphrase what a build-ghost experiment is for.",
                "Explain the compare/apply boundary in human language.",
                "Stay outside mechanics, legality, and canonical runner state."
            ],
            ChummerResponsibilities:
            [
                "Spawn temporary build ghosts from canonical runner truth.",
                "Compare deltas with receipts and explicit tradeoff notes.",
                "Apply only the reviewed variant through Chummer."
            ],
            CompareArtifacts:
            [
                "Draft compare brief",
                "What-if check packet",
                "Apply check or discard check"
            ],
            ClientReportHref: clientReportHref,
            PublicFeedbackHref: publicFeedbackHref,
            Actions:
            [
                new BuildGhostConciergeActionProjection(
                    "Open character intake",
                    "/participate/karma-forge?track=player_trust_track",
                    "primary",
                    "Start the first-party intake that can feed a future ghost-comparison packet."),
                new BuildGhostConciergeActionProjection(
                    "Open signed-in helper",
                    "/account/alice/open",
                    "secondary",
                    "Open the signed-in helper and inspect the limited compare path."),
                new BuildGhostConciergeActionProjection(
                    "Open public concierge",
                    facePopHref,
                    "ghost",
                    "Use the bounded public invite lane without granting it runtime truth."),
                new BuildGhostConciergeActionProjection(
                    "Report a Build Ghost issue",
                    clientReportHref,
                    "secondary",
                    "Open first-party support with the build-ghost runtime context already attached.")
            ]);
    }

    private static string? NormalizeConfiguredPath(string? href)
    {
        if (string.IsNullOrWhiteSpace(href))
        {
            return null;
        }

        string trimmed = href.Trim();
        if (Uri.TryCreate(trimmed, UriKind.Absolute, out _))
        {
            return trimmed;
        }

        return trimmed.StartsWith("/", StringComparison.Ordinal) ? trimmed : "/" + trimmed;
    }
}
