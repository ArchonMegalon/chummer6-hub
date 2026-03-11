using Chummer.Run.Contracts.AI.Newspaper;

namespace Chummer.Run.AI.Services.Newspaper;

public interface INewspaperValidationService
{
    IssueValidationReport Validate(NewspaperIssue issue);
}

public sealed class NewspaperValidationService : INewspaperValidationService
{
    private const int MaxHeadlineChars = 75;
    private const int MaxDekChars = 130;
    private const int MaxCoverSummaryWordsMax = 220;
    private const int MaxCoverSummaryWordsMin = 140;
    private const int MaxFeatureSummaryWordsMax = 160;
    private const int MinFeatureSummaryWords = 100;
    private const int MaxQuickHitSummaryWordsMax = 80;
    private const int MinQuickHitSummaryWords = 40;
    private const int MaxWhyItMattersSentencesWords = 40;
    private const int MinCoverStories = 3;
    private const int MinVisualsPerIssue = 3;
    private static readonly string[] DebugTokens =
    [
        "exception",
        "stacktrace",
        "traceback",
        "error:",
        "diagnostic",
        "\"status\":500"
    ];

    public IssueValidationReport Validate(NewspaperIssue issue)
    {
        var findings = new List<ValidationFinding>();
        var stories = AllStories(issue).ToList();

        var imageCount = stories.Count(s => !string.IsNullOrWhiteSpace(s.Image.Url));
        var estimatedPageCount = EstimatePageCount(stories.Count);

        if (issue.MustKnow.Stories.Count < MinCoverStories)
        {
            findings.Add(Fail("cover_structure", "Cover requires at least one lead and two teasers."));
        }

        if (estimatedPageCount < 4)
        {
            findings.Add(Fail("page_count_min", "Issue must estimate to at least 4 pages."));
        }

        if (imageCount < MinVisualsPerIssue)
        {
            findings.Add(Fail("image_count_min", "Issue must include at least 3 visuals."));
        }

        foreach (var feature in issue.WorthKnowing.Stories)
        {
            if (string.IsNullOrWhiteSpace(feature.Image.Url))
            {
                findings.Add(Fail("feature_visual_required", $"Feature story '{feature.Id}' has no visual."));
            }
        }

        foreach (var story in stories)
        {
            if (story.Headline.Length > MaxHeadlineChars)
            {
                findings.Add(Fail("headline_too_long", $"Story '{story.Id}' headline exceeds max length."));
            }

            if (story.Dek.Length > MaxDekChars)
            {
                findings.Add(Fail("dek_too_long", $"Story '{story.Id}' dek exceeds max length."));
            }

            var words = WordCount(story.Summary);
            switch (story.LayoutRole)
            {
                case "cover_lead":
                    if (words < MaxCoverSummaryWordsMin || words > MaxCoverSummaryWordsMax)
                    {
                        findings.Add(Fail("summary_length_invalid", $"Cover lead '{story.Id}' summary must be 140-220 words."));
                    }
                    break;
                case "feature":
                    if (words < MinFeatureSummaryWords || words > MaxFeatureSummaryWordsMax)
                    {
                        findings.Add(Fail("summary_length_invalid", $"Feature story '{story.Id}' summary must be 100-160 words."));
                    }
                    break;
                case "quick_hit":
                    if (words < MinQuickHitSummaryWords || words > MaxQuickHitSummaryWordsMax)
                    {
                        findings.Add(Fail("summary_length_invalid", $"Quick hit '{story.Id}' summary must be 40-80 words."));
                    }
                    break;
                default:
                    if (words > MaxCoverSummaryWordsMax)
                    {
                        findings.Add(Fail("summary_too_long", $"Story '{story.Id}' summary exceeds editorial max length."));
                    }
                    break;
            }

            if (WordCount(story.WhyItMatters) > MaxWhyItMattersSentencesWords)
            {
                findings.Add(Fail("why_matters_too_long", $"Story '{story.Id}' why-it-matters is too long."));
            }

            if (ContainsDebugToken(story.WhyItMatters) || ContainsDebugToken(story.PullQuote ?? string.Empty))
            {
                findings.Add(Fail("debug_text_present", $"Story '{story.Id}' contains diagnostic text."));
            }

            if (ContainsDebugToken(story.Headline) || ContainsDebugToken(story.Dek) || ContainsDebugToken(story.Summary))
            {
                findings.Add(Fail("debug_text_present", $"Story '{story.Id}' contains diagnostic text."));
            }
        }

        var coverLongBodies = issue.MustKnow.Stories.Count(s => WordCount(s.Summary) > 140);
        if (coverLongBodies > 1)
        {
            findings.Add(Fail("cover_body_overflow", "Cover contains more than one long summary."));
        }

        var coverSources = issue.MustKnow.Stories
            .Select(s => SourceLabelKey(s.SourceLabel))
            .Where(s => !string.IsNullOrWhiteSpace(s))
            .ToList();
        if (coverSources.Count != coverSources.Distinct(StringComparer.OrdinalIgnoreCase).Count())
        {
            findings.Add(Fail("cover_source_dup", "Only one story per source is allowed on the cover."));
        }

        var passed = findings.Count == 0;
        return new IssueValidationReport(passed, estimatedPageCount, imageCount, findings);
    }

    private static IEnumerable<NewspaperIssueStory> AllStories(NewspaperIssue issue)
    {
        foreach (var story in issue.MustKnow.Stories) yield return story;
        foreach (var story in issue.WorthKnowing.Stories) yield return story;
        foreach (var story in issue.Agenda.Stories) yield return story;
        foreach (var story in issue.Watchlist.Stories) yield return story;
    }

    private static bool ContainsDebugToken(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return false;
        }

        var lower = value.ToLowerInvariant();
        return DebugTokens.Any(token => lower.Contains(token, StringComparison.Ordinal));
    }

    private static string SourceLabelKey(string sourceLabel)
    {
        return string.IsNullOrWhiteSpace(sourceLabel) ? string.Empty : sourceLabel.Trim().ToLowerInvariant();
    }

    private static int EstimatePageCount(int storyCount)
    {
        if (storyCount <= 0)
        {
            return 0;
        }

        var pages = (int)Math.Ceiling(storyCount / 2.0);
        return Math.Max(4, pages);
    }

    private static int WordCount(string text) =>
        text
            .Split(' ', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Length;

    private static ValidationFinding Fail(string code, string message) =>
        new(code, message, "error");
}
