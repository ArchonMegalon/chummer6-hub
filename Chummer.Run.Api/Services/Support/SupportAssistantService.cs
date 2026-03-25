using Chummer.Control.Contracts.Support;

namespace Chummer.Run.Api.Services.Support;

public sealed class SupportAssistantService
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
            Href: "/account#support"),
    ];

    private readonly SupportCaseService _supportCases;
    private readonly PublicCanonFileLoader _canon;
    private readonly ILogger<SupportAssistantService> _logger;

    public SupportAssistantService(
        SupportCaseService supportCases,
        PublicCanonFileLoader canon,
        ILogger<SupportAssistantService> logger)
    {
        _supportCases = supportCases;
        _canon = canon;
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
        List<SupportCaseProjection> caseMatches = reporterCases
            .Where(item => MatchesCase(item, caseId, installationId, tokens))
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .ToList();

        List<SupportAssistantCitation> citations = new();
        foreach (var item in caseMatches.Take(maxCitations))
        {
            citations.Add(new SupportAssistantCitation(
                SourceKind: "support_case",
                Label: item.Title,
                Summary: $"Status: {HumanizeStatus(item.Status)}. Owner: {item.CandidateOwnerRepo}. Summary: {item.Summary}",
                Status: item.Status,
                Href: "/account#support"));
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

        List<SupportAssistantAction> actions = BuildActions(caseMatches, tokens);
        string confidence = caseMatches.Count > 0
            ? SupportAssistantConfidenceLevels.CaseTruth
            : citations.Count > 0
                ? SupportAssistantConfidenceLevels.CanonHelp
                : SupportAssistantConfidenceLevels.NeedsCase;
        bool escalationRecommended = confidence == SupportAssistantConfidenceLevels.NeedsCase
            || caseMatches.Any(static item => string.Equals(item.Status, SupportCaseStatuses.AwaitingEvidence, StringComparison.OrdinalIgnoreCase));

        string answer = BuildAnswer(caseMatches, citations, tokens, escalationRecommended);
        return new SupportAssistantResponse(answer, confidence, escalationRecommended, citations, actions);
    }

    private string BuildAnswer(
        IReadOnlyList<SupportCaseProjection> caseMatches,
        IReadOnlyList<SupportAssistantCitation> citations,
        IReadOnlySet<string> tokens,
        bool escalationRecommended)
    {
        if (caseMatches.Count > 0)
        {
            SupportCaseProjection latest = caseMatches[0];
            string status = HumanizeStatus(latest.Status);
            string guidance = latest.Status switch
            {
                SupportCaseStatuses.ReleasedToReporterChannel or SupportCaseStatuses.Fixed or SupportCaseStatuses.UserNotified
                    => "The tracked fix is already tied to a release or notification state, so the next useful step is to confirm you are on the matching channel and installer head.",
                SupportCaseStatuses.AwaitingEvidence
                    => "The tracked case is waiting for more evidence, so add the missing repro details or diagnostics instead of opening a duplicate report.",
                SupportCaseStatuses.Deferred or SupportCaseStatuses.Rejected
                    => "The tracked case already has a terminal decision, so use the existing thread and ask for clarification only if the current state does not match reality.",
                _ => "The tracked case is still live, so follow that case instead of creating a duplicate thread."
            };

            return $"I found {caseMatches.Count} matching support case(s). The latest is '{latest.Title}' in {status}. {guidance}";
        }

        if (citations.Count > 0)
        {
            string guidance = tokens.Contains("update") || tokens.Contains("restart")
                ? "I did not find an account-linked case yet, but the first-party release and update docs match your question."
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

    private List<SupportAssistantAction> BuildActions(IReadOnlyList<SupportCaseProjection> caseMatches, IReadOnlySet<string> tokens)
    {
        Dictionary<string, SupportAssistantAction> actions = new(StringComparer.OrdinalIgnoreCase);

        void Add(string id, string label, string href, string reason)
            => actions[id] = new SupportAssistantAction(id, label, href, reason);

        Add("open_help", "Open help", "/help", "Use the first-party help surface instead of guessing.");

        if (caseMatches.Count > 0)
        {
            Add("open_account_support", "Open support timeline", "/account#support", "Review the tracked case and its latest status.");

            if (caseMatches.Any(item =>
                    string.Equals(item.Status, SupportCaseStatuses.ReleasedToReporterChannel, StringComparison.OrdinalIgnoreCase)
                    || string.Equals(item.Status, SupportCaseStatuses.Fixed, StringComparison.OrdinalIgnoreCase)
                    || string.Equals(item.Status, SupportCaseStatuses.UserNotified, StringComparison.OrdinalIgnoreCase)))
            {
                Add("open_downloads", "Open downloads", "/downloads", "Confirm you are on the fixed channel and installer head.");
            }
        }
        else
        {
            Add("open_support_case", "Open support case", "/account#support", "Create a tracked case if the docs do not resolve the issue.");
        }

        if (tokens.Contains("install") || tokens.Contains("download") || tokens.Contains("update") || tokens.Contains("claim") || tokens.Contains("restart"))
        {
            Add("open_downloads", "Open downloads", "/downloads", "Check the current installer and release posture.");
        }

        return actions.Values.ToList();
    }

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
            string repoRoot = _canon.ResolveRepoRoot(relativePath);
            string fullPath = Path.Combine(repoRoot, relativePath.Replace('/', Path.DirectorySeparatorChar));
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
