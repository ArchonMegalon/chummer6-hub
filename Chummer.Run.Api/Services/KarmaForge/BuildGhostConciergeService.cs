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
            SafeSummary: "Build Ghost is a guided experiment lane. A public concierge can greet and route a builder into the right intake. A bounded explainer can paraphrase what the experiment means in plain language. Chummer still owns the actual ghost spawn, compare, receipts, legality explanation, and apply decision.",
            CalculationSteps:
            [
                new RuleSafeCalculationStep("Entry", "Public concierge asks what changed and what the builder wants to compare", "facepop_concierge_boundary"),
                new RuleSafeCalculationStep("Explain", "Bounded explainer summarizes the experiment without becoming mechanics truth", "answerly_humanizer_boundary"),
                new RuleSafeCalculationStep("Truth", "First-party Build Ghost lab spawns, compares, receipts, and applies only reviewed variants", "alice_build_ghost_lab")
            ],
            SourceAnchors: Array.Empty<RuleSafeSourceAnchor>(),
            ReceiptIds: ["build_ghost_lab", "alice_horizon"],
            Confidence: "bounded",
            ForbiddenToAnswerly: ["mechanics_truth", "legality_truth", "apply_truth", "runner_mutation"],
            HumanizerInstruction: "Explain the Build Ghost concierge split in plain language without claiming runtime truth.",
            FallbackMessage: "A public concierge can greet the builder, a bounded explainer can explain the experiment, and Chummer still owns the actual Build Ghost compare and apply truth.");
        RuleSafeOutputGateResult humanized = _humanizer.Humanize(packet);
        string answerlyStatus = _answerlyPolicy.CanUseHumanizer
            ? (humanized.Allowed ? "Bounded explainer ready" : "Bounded explainer fail-closed")
            : "Fallback explainer only";
        const string clientReportHref = "/contact?kind=bug_report&title=Build%20Ghost%20report&summary=Build%20Ghost%20compare%20or%20apply%20did%20not%20behave%20as%20expected.&runtime=alice_build_ghost_lab&bundle=build_ghost&sceneId=build-ghost";
        const string publicFeedbackHref = "/feedback?topic=build-ghosts";

        return new BuildGhostConciergeProjection(
            FacePopEntryHref: facePopHref,
            FacePopStatus: "Public concierge only",
            AnswerlyStatus: answerlyStatus,
            EngineStatus: "First-party compare/apply only",
            HumanizedSummary: humanized.Allowed ? humanized.Output : packet.FallbackMessage,
            CanonicalLane: "Public concierge greeting -> bounded explanation -> Chummer Build Ghost compare bench",
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
                "Apply only the reviewed variant through first-party contracts."
            ],
            CompareArtifacts:
            [
                "Build ghost compare brief",
                "What-if receipt packet",
                "Apply receipt or discard receipt"
            ],
            ClientReportHref: clientReportHref,
            PublicFeedbackHref: publicFeedbackHref,
            Actions:
            [
                new BuildGhostConciergeActionProjection(
                    "Open Build Ghost intake",
                    "/participate/karma-forge?track=player_trust_track",
                    "primary",
                    "Start the first-party intake that can feed a future ghost-comparison packet."),
                new BuildGhostConciergeActionProjection(
                    "Open ALICE roadmap",
                    "/roadmap/alice",
                    "secondary",
                    "Inspect the horizon and proof posture before treating the lane as shipped runtime."),
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
