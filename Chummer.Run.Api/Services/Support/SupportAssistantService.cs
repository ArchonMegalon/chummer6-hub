using Chummer.Control.Contracts.Support;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;

namespace Chummer.Run.Api.Services.Support;

public sealed class SupportAssistantService : IFirstPartySupportAssistant
{
    private static readonly char[] TokenSeparators =
    [
        ' ', '\t', '\r', '\n', '.', ',', ';', ':', '!', '?', '(', ')', '[', ']', '{', '}', '/', '\\', '-', '_', '"', '\''
    ];

    private static readonly CanonDocRule[] CanonRules =
    [
        new(
            Label: "Downloads and install help",
            RelativePath: ".codex-design/product/PUBLIC_DOWNLOADS_POLICY.md",
            Keywords: ["download", "install", "installer", "claim", "link", "preview", "build"],
            Href: "/downloads"),
        new(
            Label: "Auto-update policy",
            RelativePath: ".codex-design/product/PUBLIC_AUTO_UPDATE_POLICY.md",
            Keywords: ["update", "updater", "restart", "channel", "release", "staged"],
            Href: "/help#install-update"),
        new(
            Label: "Release trust surface",
            RelativePath: ".codex-design/product/PUBLIC_RELEASE_EXPERIENCE.yaml",
            Keywords: ["download", "install", "update", "channel", "known", "issue"],
            Href: "/downloads"),
        new(
            Label: "Crash and feedback system",
            RelativePath: ".codex-design/product/FEEDBACK_AND_CRASH_REPORTING_SYSTEM.md",
            Keywords: ["crash", "bug", "diagnostic", "feedback", "report"],
            Href: "/help#support"),
        new(
            Label: "Support status model",
            RelativePath: ".codex-design/product/FEEDBACK_AND_CRASH_STATUS_MODEL.md",
            Keywords: ["status", "triage", "fixed", "released", "notified", "deferred", "rejected"],
            Href: "/account/support"),
    ];

    private readonly SupportCaseService _supportCases;
    private readonly PublicCanonFileLoader _canon;
    private readonly CampaignSpineService _campaignSpine;
    private readonly InstallLinkingService _installLinking;
    private readonly SupportCasePresentationService _supportPresentation;
    private readonly ILogger<SupportAssistantService> _logger;

    public SupportAssistantService(
        SupportCaseService supportCases,
        PublicCanonFileLoader canon,
        CampaignSpineService campaignSpine,
        InstallLinkingService installLinking,
        SupportCasePresentationService supportPresentation,
        ILogger<SupportAssistantService> logger)
    {
        _supportCases = supportCases;
        _canon = canon;
        _campaignSpine = campaignSpine;
        _installLinking = installLinking;
        _supportPresentation = supportPresentation;
        _logger = logger;
    }

    public SupportAssistantResponse Answer(string? reporterUserId, string? reporterSubjectId, SupportAssistantRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);

        string query = NormalizeRequired(request.Query, nameof(request.Query), 2000);
        string? installationId = NormalizeOptional(request.InstallationId, 64);
        string? caseId = NormalizeOptional(request.CaseId, 64);
        int maxCitations = Math.Clamp(request.MaxCitations, 1, 5);
        HashSet<string> tokens = Tokenize(query);

        IReadOnlyList<SupportCaseProjection> reporterCases = _supportCases.ListForReporter(reporterUserId, reporterSubjectId).Items;
        var installLinking = string.IsNullOrWhiteSpace(reporterUserId) && string.IsNullOrWhiteSpace(reporterSubjectId)
            ? null
            : _installLinking.GetSummary(reporterUserId, reporterSubjectId);
        List<SupportCaseProjection> caseMatches = reporterCases
            .Where(item => MatchesCase(item, caseId, installationId, tokens))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToList();
        List<SupportCasePresentationViewModel> presentedMatches = _supportPresentation
            .BuildList(caseMatches, installLinking)
            .ToList();

        List<SupportAssistantCitation> citations = new();
        foreach (var item in presentedMatches.Take(maxCitations))
        {
            citations.Add(new SupportAssistantCitation(
                SourceKind: "support_case",
                Label: item.Case.Title,
                Summary: TrimForSummary($"{item.StageLabel}. {item.ReleaseProgressSummary} {item.VerificationSummary}"),
                Status: item.Case.Status,
                Href: item.DetailHref,
                ReceiptId: $"support.case.{item.Case.CaseId}"));
        }

        foreach (var citation in BuildRulesTruthCitations(reporterUserId, reporterSubjectId, tokens, maxCitations - citations.Count))
        {
            citations.Add(citation);
        }

        foreach (var citation in BuildBuildJourneyTruthCitations(reporterUserId, reporterSubjectId, tokens, maxCitations - citations.Count))
        {
            citations.Add(citation);
        }

        foreach (var rule in CanonRules)
        {
            if (citations.Count >= maxCitations)
            {
                break;
            }

            if (!rule.Keywords.Any(tokens.Contains))
            {
                continue;
            }

            string? excerpt = TryExtractCanonExcerpt(rule.RelativePath, rule.Keywords);
            if (string.IsNullOrWhiteSpace(excerpt))
            {
                continue;
            }

            citations.Add(new SupportAssistantCitation(
                SourceKind: "canon_doc",
                Label: rule.Label,
                Summary: excerpt,
                Href: rule.Href));
        }

        List<SupportAssistantAction> actions = BuildActions(presentedMatches, tokens);
        string confidence = presentedMatches.Count > 0
            ? SupportAssistantConfidenceLevels.CaseTruth
            : citations.Count > 0
                ? SupportAssistantConfidenceLevels.CanonHelp
                : SupportAssistantConfidenceLevels.NeedsCase;
        bool escalationRecommended = confidence == SupportAssistantConfidenceLevels.NeedsCase
            || presentedMatches.Any(static item => string.Equals(item.Case.Status, SupportCaseStatuses.AwaitingEvidence, StringComparison.OrdinalIgnoreCase));

        string answer = BuildAnswer(presentedMatches, citations, tokens, escalationRecommended);
        return new SupportAssistantResponse(answer, confidence, escalationRecommended, citations, actions);
    }

    private IReadOnlyList<SupportAssistantCitation> BuildRulesTruthCitations(
        string? reporterUserId,
        string? reporterSubjectId,
        IReadOnlySet<string> tokens,
        int capacity)
    {
        if (capacity <= 0
            || string.IsNullOrWhiteSpace(reporterUserId)
            || !ShouldUseRulesTruth(tokens))
        {
            return Array.Empty<SupportAssistantCitation>();
        }

        try
        {
            var now = DateTimeOffset.UtcNow;
            var summary = _campaignSpine.GetAccountSummary(new HubUserDto(
                UserId: reporterUserId,
                SubjectId: reporterSubjectId ?? reporterUserId,
                DisplayName: reporterSubjectId ?? reporterUserId,
                Handle: reporterSubjectId ?? reporterUserId,
                Visibility: "private",
                Timezone: "UTC",
                CountryCode: "ZZ",
                LinkedPrincipals: Array.Empty<string>(),
                GroupIds: Array.Empty<string>(),
                CreatedAtUtc: now,
                UpdatedAtUtc: now));

            return summary.RulesNavigator
                .Take(capacity)
                .Select(entry => new SupportAssistantCitation(
                    SourceKind: "rules_truth",
                    Label: entry.Question,
                    Summary: TrimForSummary(string.Join(
                        " ",
                        new[]
                        {
                            entry.ShortAnswer,
                            entry.Diffs?.FirstOrDefault() is { } diff
                                ? $"Diff: {diff.Label} -> {diff.AfterSummary}"
                                : null,
                            $"Evidence: {string.Join(" | ", entry.EvidenceLines.Take(2))}"
                        }.Where(static item => !string.IsNullOrWhiteSpace(item)))),
                    Href: "/home",
                    ReceiptId: entry.ExplainEntryId))
                .ToArray();
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "support assistant could not hydrate rules-truth citations for reporter {ReporterUserId}", reporterUserId);
            return Array.Empty<SupportAssistantCitation>();
        }
    }

    private IReadOnlyList<SupportAssistantCitation> BuildBuildJourneyTruthCitations(
        string? reporterUserId,
        string? reporterSubjectId,
        IReadOnlySet<string> tokens,
        int capacity)
    {
        if (capacity <= 0
            || string.IsNullOrWhiteSpace(reporterUserId)
            || !ShouldUseBuildJourneyTruth(tokens))
        {
            return Array.Empty<SupportAssistantCitation>();
        }

        try
        {
            var now = DateTimeOffset.UtcNow;
            var summary = _campaignSpine.GetAccountSummary(new HubUserDto(
                UserId: reporterUserId,
                SubjectId: reporterSubjectId ?? reporterUserId,
                DisplayName: reporterSubjectId ?? reporterUserId,
                Handle: reporterSubjectId ?? reporterUserId,
                Visibility: "private",
                Timezone: "UTC",
                CountryCode: "ZZ",
                LinkedPrincipals: Array.Empty<string>(),
                GroupIds: Array.Empty<string>(),
                CreatedAtUtc: now,
                UpdatedAtUtc: now));

            return summary.BuildLabHandoffs
                .Take(capacity)
                .Select(entry => new SupportAssistantCitation(
                    SourceKind: "build_truth",
                    Label: entry.Title,
                    Summary: TrimForSummary(string.Join(
                        " ",
                        new[]
                        {
                            entry.NextSafeAction ?? entry.Summary,
                            !string.IsNullOrWhiteSpace(entry.PlannerCoverageSummary) ? $"Coverage: {entry.PlannerCoverageSummary}" : null,
                            entry.PlannerCoverageLines?.FirstOrDefault() is { Length: > 0 } coverageLine ? $"Coverage detail: {coverageLine}" : null,
                            $"Return: {entry.CampaignReturnSummary ?? entry.ProgressionLabel}",
                            $"Support: {entry.SupportClosureSummary ?? string.Join(" | ", entry.ProgressionOutcomes.Take(1))}"
                        }.Where(static item => !string.IsNullOrWhiteSpace(item)))),
                    Href: "/account/work",
                    ReceiptId: entry.ExplainEntryId))
                .ToArray();
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "support assistant could not hydrate build-truth citations for reporter {ReporterUserId}", reporterUserId);
            return Array.Empty<SupportAssistantCitation>();
        }
    }

    private string BuildAnswer(
        IReadOnlyList<SupportCasePresentationViewModel> caseMatches,
        IReadOnlyList<SupportAssistantCitation> citations,
        IReadOnlySet<string> tokens,
        bool escalationRecommended)
    {
        if (caseMatches.Count > 0)
        {
            SupportCasePresentationViewModel latest = caseMatches[0];
            string guidance = latest.Case.Status switch
                {
                SupportCaseStatuses.ReleasedToReporterChannel or SupportCaseStatuses.Fixed or SupportCaseStatuses.UserNotified
                    when latest.FixReadyOnLinkedInstall
                        => $"{latest.InstallReadinessSummary} Use the verification buttons on this same tracked case now to confirm whether the fix worked here or whether the issue is still broken.",
                SupportCaseStatuses.ReleasedToReporterChannel or SupportCaseStatuses.Fixed or SupportCaseStatuses.UserNotified
                    when latest.NeedsLinkedInstall
                        => $"{latest.InstallReadinessSummary} Once that copy is linked, come back to this same case to verify the fix.",
                SupportCaseStatuses.ReleasedToReporterChannel or SupportCaseStatuses.Fixed or SupportCaseStatuses.UserNotified
                    => $"{latest.InstallReadinessSummary} After the linked install is current, come back to this same case to confirm whether the fix worked here.",
                SupportCaseStatuses.AwaitingEvidence
                    => "The tracked case is waiting for more evidence, so add the missing repro details or diagnostics instead of opening a duplicate report.",
                SupportCaseStatuses.Deferred or SupportCaseStatuses.Rejected
                    => "The tracked case already has a terminal decision, so use the existing thread and ask for clarification only if the current state does not match reality.",
                _ => "The tracked case is still live, so follow that case instead of creating a duplicate thread."
            };

            return $"I found {caseMatches.Count} matching support case(s). The latest is '{latest.Case.Title}' in {latest.StageLabel}. {guidance}";
        }

        if (citations.Count > 0)
        {
            string guidance = tokens.Contains("update") || tokens.Contains("restart")
                ? "I did not find an account-linked case yet, but the first-party release and update docs match your question."
                : ShouldUseBuildJourneyTruth(tokens)
                    ? "I did not find an account-linked case yet, but I did find a grounded build or campaign continuity path in your signed-in workspace."
                : tokens.Contains("install") || tokens.Contains("download") || tokens.Contains("claim")
                    ? "I did not find an account-linked case yet, but the first-party install and downloads docs cover this path."
                    : "I did not find an account-linked case yet, but I did find first-party help that matches your question.";
            if (escalationRecommended)
            {
                guidance += " If that does not resolve the problem, open a support case so Chummer can track the issue against your install and channel.";
            }
            return guidance;
        }

        return "I could not ground an answer from your current support cases or the first-party help docs. Open a support case so the problem can be tracked against your install, channel, or release state.";
    }

    private List<SupportAssistantAction> BuildActions(IReadOnlyList<SupportCasePresentationViewModel> caseMatches, IReadOnlySet<string> tokens)
    {
        Dictionary<string, SupportAssistantAction> actions = new(StringComparer.OrdinalIgnoreCase);

        void Add(string id, string label, string href, string reason)
            => actions[id] = new SupportAssistantAction(id, label, href, reason);

        Add("open_help", "Open help", "/help", "Use the first-party help surface instead of guessing.");

        if (caseMatches.Count > 0)
        {
            Add("open_account_support", "Open support timeline", "/account/support", "Review the tracked case and its latest status.");

            if (caseMatches.FirstOrDefault(static item => item.CanVerifyFix) is { } readyToVerify)
            {
                Add("verify_fix_on_case", "Verify fix now", readyToVerify.DetailHref, "The linked install is already on the reporter-ready fix, so confirm whether the fix worked here.");
            }

            if (caseMatches.Any(static item => item.NeedsLinkedInstall))
            {
                Add("open_account_access", "Open Devices and access", "/account/access", "Link or reclaim the affected install before you verify the fix.");
            }

            if (caseMatches.Any(static item => item.NeedsInstallUpdate))
            {
                Add("open_downloads", "Open downloads", "/downloads", "Confirm you are on the fixed channel and installer head.");
            }
        }
        else
        {
            Add("open_support_case", "Open support case", "/account/support", "Create a tracked case if the docs do not resolve the issue.");
        }

        if (tokens.Contains("install") || tokens.Contains("download") || tokens.Contains("update") || tokens.Contains("claim") || tokens.Contains("restart"))
        {
            Add("open_downloads", "Open downloads", "/downloads", "Check the current installer and release status.");
        }

        if (ShouldUseRulesTruth(tokens))
        {
            Add("open_home", "Open home", "/home", "Review the current rule environment, campaign workspace, and grounded answer path.");
        }

        if (ShouldUseBuildJourneyTruth(tokens))
        {
            Add("open_work", "Open work", "/account/work", "Review the current build path, living dossier, and campaign return rail.");
        }

        return actions.Values.ToList();
    }

    private static bool ShouldUseRulesTruth(IReadOnlySet<string> tokens)
        => tokens.Contains("rule")
           || tokens.Contains("rules")
           || tokens.Contains("environment")
           || tokens.Contains("visibility")
           || tokens.Contains("permission")
           || tokens.Contains("permissions")
           || tokens.Contains("change")
           || tokens.Contains("changed")
           || tokens.Contains("why");

    private static bool ShouldUseBuildJourneyTruth(IReadOnlySet<string> tokens)
        => tokens.Contains("build")
           || tokens.Contains("compare")
           || tokens.Contains("variant")
           || tokens.Contains("export")
           || tokens.Contains("publish")
           || tokens.Contains("dossier")
           || tokens.Contains("campaign")
           || tokens.Contains("return")
           || tokens.Contains("continuity")
           || tokens.Contains("handoff");

    private bool MatchesCase(
        SupportCaseProjection item,
        string? caseId,
        string? installationId,
        IReadOnlySet<string> tokens)
    {
        if (!string.IsNullOrWhiteSpace(caseId) && string.Equals(item.CaseId, caseId, StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        if (!string.IsNullOrWhiteSpace(installationId)
            && string.Equals(item.InstallationId, installationId, StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        if (tokens.Count == 0)
        {
            return false;
        }

        string haystack = string.Join(
            '\n',
            new[]
            {
                item.Title,
                item.Summary,
                item.Detail,
                item.InstallationId,
                item.ApplicationVersion,
                item.ReleaseChannel,
                item.HeadId,
                item.Platform,
            }.Where(static value => !string.IsNullOrWhiteSpace(value)));
        HashSet<string> caseTokens = Tokenize(haystack);
        return tokens.Any(caseTokens.Contains);
    }

    private string? TryExtractCanonExcerpt(string relativePath, IReadOnlyList<string> keywords)
    {
        try
        {
            string fullPath = _canon.ResolveRequiredPath(relativePath);
            if (!File.Exists(fullPath))
            {
                return null;
            }

            foreach (string rawLine in File.ReadLines(fullPath))
            {
                string line = rawLine.Trim();
                if (string.IsNullOrWhiteSpace(line) || line.StartsWith('#') || line.StartsWith("```", StringComparison.Ordinal))
                {
                    continue;
                }

                string lowered = line.ToLowerInvariant();
                if (keywords.Any(keyword => lowered.Contains(keyword, StringComparison.Ordinal)))
                {
                    return TrimForSummary(line);
                }
            }

            foreach (string rawLine in File.ReadLines(fullPath))
            {
                string line = rawLine.Trim();
                if (string.IsNullOrWhiteSpace(line) || line.StartsWith('#') || line.StartsWith("```", StringComparison.Ordinal))
                {
                    continue;
                }

                return TrimForSummary(line);
            }
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Support assistant could not read canon help file {RelativePath}.", relativePath);
        }

        return null;
    }

    private static string HumanizeStatus(string status)
        => status.Replace("_", " ", StringComparison.Ordinal).Trim();

    private static string TrimForSummary(string value)
    {
        string clean = value.Trim().TrimStart('*', '-', ' ');
        if (clean.Length <= 220)
        {
            return clean;
        }

        return clean[..217].TrimEnd() + "...";
    }

    private static HashSet<string> Tokenize(string value)
        => value
            .Split(TokenSeparators, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(static item => item.ToLowerInvariant())
            .Where(static item => item.Length >= 3)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

    private static string NormalizeRequired(string? value, string name, int maxLength)
    {
        string normalized = NormalizeOptional(value, maxLength)
            ?? throw new ArgumentException($"{name} is required.", name);
        return normalized;
    }

    private static string? NormalizeOptional(string? value, int maxLength)
    {
        string? normalized = value?.Trim();
        if (string.IsNullOrWhiteSpace(normalized))
        {
            return null;
        }

        return normalized.Length <= maxLength ? normalized : normalized[..maxLength].Trim();
    }

    private sealed record CanonDocRule(
        string Label,
        string RelativePath,
        IReadOnlyList<string> Keywords,
        string Href);
}
