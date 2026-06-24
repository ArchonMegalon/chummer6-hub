using Chummer.Control.Contracts.Support;
using Chummer.Run.Api.Services.Support;
using System.Text;

namespace Chummer.Run.Api.Services.KarmaForge;

public sealed record BuildGhostConciergeActionProjection(
    string Label,
    string Href,
    string Tone,
    string Summary);

public sealed record BuildGhostConciergeInsightProjection(
    string Id,
    string Title,
    string Summary,
    string EmbedHref,
    string OpenHref,
    string ActionLabel);

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
    IReadOnlyList<BuildGhostConciergeInsightProjection> Insights,
    string ClientReportHref,
    string PublicFeedbackHref,
    IReadOnlyList<BuildGhostConciergeActionProjection> Actions);

public sealed class BuildGhostConciergeService
{
    private const string FacePopPublicInvitePathConfigKey = "CHUMMER_KARMA_FORGE_FACEPOP_PUBLIC_INVITE_PATH";
    private const string ChartBrickExplainEmbedUrlConfigKey = "CHUMMER_ALICE_CHARTBRICK_EXPLAIN_EMBED_URL";
    private const string ChartBrickExplainShareUrlConfigKey = "CHUMMER_ALICE_CHARTBRICK_EXPLAIN_SHARE_URL";
    private const string ChartBrickRunnerStatsEmbedUrlConfigKey = "CHUMMER_ALICE_CHARTBRICK_RUNNER_STATS_EMBED_URL";
    private const string ChartBrickRunnerStatsShareUrlConfigKey = "CHUMMER_ALICE_CHARTBRICK_RUNNER_STATS_SHARE_URL";

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
        string facePopHref = NormalizeConfiguredPath(_configuration[FacePopPublicInvitePathConfigKey]) ?? "/partizipate";
        RuleSafeAnswerPacket packet = new(
            PacketId: "build-ghost-concierge",
            QuestionId: "build-ghost-entry",
            AccountScope: "public",
            RulesetId: "build_ghost",
            AnswerType: "support_question",
            Authority: "chummer6-build-ghost-boundary",
            SafeSummary: "The character helper is a guided preview. A short intake can route a builder into the right Chummer path. A plain-language explainer can describe what the preview means. Chummer still owns draft creation, comparison, legality explanation, and the final apply decision.",
            CalculationSteps:
            [
                new RuleSafeCalculationStep("Entry", "Public concierge asks what changed and what the builder wants to compare", "facepop_concierge_boundary"),
                new RuleSafeCalculationStep("Explain", "Plain-language explainer summarizes the preview without becoming mechanics truth", "answerly_humanizer_boundary"),
                new RuleSafeCalculationStep("Apply", "Chummer creates drafts, compares them, and applies only reviewed variants", "alice_build_ghost_lab")
            ],
            SourceAnchors: Array.Empty<RuleSafeSourceAnchor>(),
            ReceiptIds: ["build_ghost_lab", "alice_horizon"],
            Confidence: "bounded",
            ForbiddenToAnswerly: ["mechanics_truth", "legality_truth", "apply_truth", "runner_mutation"],
            HumanizerInstruction: "Explain the character-helper split in plain language without overclaiming what the helper can do.",
            FallbackMessage: "A short intake can greet the builder, the explainer can clarify the preview, and Chummer still owns the actual compare and apply decision.");
        RuleSafeOutputGateResult humanized = _humanizer.Humanize(packet);
        string answerlyStatus = _answerlyPolicy.CanUseHumanizer
            ? "Limited explainer fail-closed"
            : "Fallback explainer only";
        const string clientReportHref = "/contact?kind=bug_report&title=Character%20helper%20report&summary=Character%20helper%20compare%20or%20apply%20did%20not%20behave%20as%20expected.&runtime=character_helper&bundle=character_helper&sceneId=character-helper";
        const string publicFeedbackHref = "/feedback?topic=character-helper";
        BuildGhostConciergeInsightProjection[] insights = BuildChartBrickInsights();

        return new BuildGhostConciergeProjection(
            FacePopEntryHref: facePopHref,
            FacePopStatus: "Public concierge only",
            AnswerlyStatus: answerlyStatus,
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
                "Paraphrase what a draft-build preview is for.",
                "Explain the compare/apply boundary in human language.",
                "Stay outside mechanics, legality, and canonical runner state."
            ],
            ChummerResponsibilities:
            [
                "Create temporary draft builds from the current runner.",
                "Compare changes with explicit tradeoff notes.",
                "Apply only the reviewed variant through Chummer."
            ],
            CompareArtifacts:
            [
                "Draft compare brief",
                "What-if check packet",
                "Apply check or discard check"
            ],
            Insights: insights,
            ClientReportHref: clientReportHref,
            PublicFeedbackHref: publicFeedbackHref,
            Actions:
            [
                new BuildGhostConciergeActionProjection(
                    "Open character helper",
                    "/alice",
                    "primary",
                    "Open the public character-helper preview."),
                new BuildGhostConciergeActionProjection(
                    "Open signed-in helper",
                    "/account/alice/open",
                    "secondary",
                    "Open the signed-in helper and inspect the limited compare path."),
                new BuildGhostConciergeActionProjection(
                    "Open public concierge",
                    facePopHref,
                    "ghost",
                    "Use the public intake path when you want to shape the workflow."),
                new BuildGhostConciergeActionProjection(
                    "Report a character-helper issue",
                    clientReportHref,
                    "secondary",
                    "Open support with the character-helper context already attached.")
            ]);
    }

    public IReadOnlyList<BuildGhostConciergeInsightProjection> BuildChartBrickInsightsForHandoff(string handoffId, string? runnerLabel = null)
        => BuildChartBrickInsights(
            handoffId: handoffId,
            runnerLabel: runnerLabel,
            publicPreview: false);

    private BuildGhostConciergeInsightProjection[] BuildChartBrickInsights(
        string? handoffId = null,
        string? runnerLabel = null,
        bool publicPreview = true)
    {
        List<BuildGhostConciergeInsightProjection> insights = [];

        AddInsight(
            insights,
            id: "alice-why",
            title: "Why ALICE leans this way",
            summary: publicPreview
                ? "A visual breakdown of the tradeoffs behind a suggested direction. This can clarify role fit, survivability, cost pressure, and upgrade shape without becoming rules truth."
                : BuildSignedInExplainSummary(runnerLabel),
            embedKey: ChartBrickExplainEmbedUrlConfigKey,
            shareKey: ChartBrickExplainShareUrlConfigKey,
            actionLabel: "Open explanation board",
            handoffId: handoffId,
            runnerLabel: runnerLabel);

        AddInsight(
            insights,
            id: "runner-stats",
            title: "Runner stats",
            summary: publicPreview
                ? "A compact board for the current runner view: strengths, weak spots, and pressure points that are easier to scan visually than in prose alone."
                : BuildSignedInStatsSummary(runnerLabel),
            embedKey: ChartBrickRunnerStatsEmbedUrlConfigKey,
            shareKey: ChartBrickRunnerStatsShareUrlConfigKey,
            actionLabel: "Open stats board",
            handoffId: handoffId,
            runnerLabel: runnerLabel);

        return insights.ToArray();
    }

    private void AddInsight(
        List<BuildGhostConciergeInsightProjection> insights,
        string id,
        string title,
        string summary,
        string embedKey,
        string shareKey,
        string actionLabel,
        string? handoffId,
        string? runnerLabel)
    {
        string? embedHref = NormalizeChartBrickUrl(_configuration[embedKey], handoffId, runnerLabel);
        if (string.IsNullOrWhiteSpace(embedHref))
        {
            return;
        }

        string openHref = NormalizeChartBrickUrl(_configuration[shareKey], handoffId, runnerLabel) ?? embedHref;
        insights.Add(new BuildGhostConciergeInsightProjection(
            Id: id,
            Title: title,
            Summary: summary,
            EmbedHref: embedHref,
            OpenHref: openHref,
            ActionLabel: actionLabel));
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

    private static string? NormalizeChartBrickUrl(string? href, string? handoffId, string? runnerLabel)
    {
        if (string.IsNullOrWhiteSpace(href))
        {
            return null;
        }

        string trimmed = ReplaceInsightTokens(href.Trim(), handoffId, runnerLabel);
        if (!Uri.TryCreate(trimmed, UriKind.Absolute, out Uri? uri))
        {
            return null;
        }

        if (!string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        string host = uri.Host.Trim();
        if (!host.EndsWith("chartbrick.com", StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        return uri.ToString();
    }

    private static string ReplaceInsightTokens(string template, string? handoffId, string? runnerLabel)
    {
        StringBuilder builder = new(template);
        builder.Replace("{handoffId}", Uri.EscapeDataString(handoffId ?? string.Empty));
        builder.Replace("{runnerLabel}", Uri.EscapeDataString(runnerLabel ?? string.Empty));
        return builder.ToString();
    }

    private static string BuildSignedInExplainSummary(string? runnerLabel)
    {
        string label = NormalizeRunnerLabel(runnerLabel);
        return $"{label} now has a visual tradeoff read: survivability, role fit, cost pressure, and upgrade shape, without letting the board replace Chummer's final decision.";
    }

    private static string BuildSignedInStatsSummary(string? runnerLabel)
    {
        string label = NormalizeRunnerLabel(runnerLabel);
        return $"{label} also gets a runner-stat board so weak spots, spikes, and pressure points are easier to scan before you apply a change.";
    }

    private static string NormalizeRunnerLabel(string? runnerLabel)
    {
        if (string.IsNullOrWhiteSpace(runnerLabel))
        {
            return "This handoff";
        }

        return runnerLabel.Trim();
    }
}
