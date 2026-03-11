using System.Text;
using Chummer.Run.Contracts.AI.Newspaper;

namespace Chummer.Run.AI.Services.Newspaper;

public interface INewspaperCompositionService
{
    ComposeIssueResponse Compose(ComposeIssueRequest request);
}

public sealed class NewspaperCompositionService : INewspaperCompositionService
{
    private const int MinIssueStories = 8;
    private const int MinCoverStories = 3;
    private const int MinFeatureStories = 2;
    private const int MaxFeatureStories = 4;
    private readonly INewspaperValidationService _validator;

    public NewspaperCompositionService(INewspaperValidationService validator)
    {
        _validator = validator;
    }

    public ComposeIssueResponse Compose(ComposeIssueRequest request)
    {
        var ranked = request.Candidates
            .OrderByDescending(c => c.Score)
            .ThenByDescending(c => c.PublishedAt ?? DateTimeOffset.MinValue)
            .ToList();

        var mustKnow = new List<NewspaperIssueStory>();
        var worthKnowing = new List<NewspaperIssueStory>();
        var watchlist = new List<NewspaperIssueStory>();
        var agenda = new List<NewspaperIssueStory>();
        var remaining = ranked.ToList();
        if (remaining.Count == 0)
        {
            remaining.Add(CreateFallbackCandidate());
            remaining.Add(CreateFallbackCandidate());
            remaining.Add(CreateFallbackCandidate());
        }

        var coverCandidates = DeduplicateBySource(remaining);
        var lead = coverCandidates.FirstOrDefault();
        if (lead is not null)
        {
            mustKnow.Add(ToIssueStory(lead, "must_know", "cover_lead", 220));
            remaining.RemoveAll(c => c.Id == lead.Id);
        }

        foreach (var teaser in DeduplicateBySource(remaining).Take(2))
        {
            mustKnow.Add(ToIssueStory(teaser, "must_know", "cover_teaser", 80));
            remaining.RemoveAll(c => c.Id == teaser.Id);
        }

        foreach (var feature in DeduplicateBySource(remaining).Take(MaxFeatureStories))
        {
            worthKnowing.Add(ToIssueStory(feature, "worth_knowing", "feature", 160));
            remaining.RemoveAll(c => c.Id == feature.Id);
        }

        if (worthKnowing.Count < MinFeatureStories)
        {
            foreach (var fallbackFeature in DeduplicateBySource(remaining).Take(MinFeatureStories - worthKnowing.Count))
            {
                worthKnowing.Add(ToIssueStory(fallbackFeature, "worth_knowing", "feature", 160));
                remaining.RemoveAll(c => c.Id == fallbackFeature.Id);
            }
        }

        if (mustKnow.Count < MinCoverStories)
        {
            foreach (var filler in DeduplicateBySource(remaining).Take(MinCoverStories - mustKnow.Count))
            {
                mustKnow.Add(ToIssueStory(filler, "must_know", "cover_teaser", 80));
                remaining.RemoveAll(c => c.Id == filler.Id);
            }
        }

        foreach (var quickHit in DeduplicateBySource(remaining).Take(4))
        {
            watchlist.Add(ToIssueStory(quickHit, "watchlist", "quick_hit", 80));
            remaining.RemoveAll(c => c.Id == quickHit.Id);
        }

        if (request.AgendaItems is not null)
        {
            foreach (var item in request.AgendaItems.Take(6))
            {
                agenda.Add(new NewspaperIssueStory(
                    Id: item.Id,
                    Section: "agenda",
                    LayoutRole: "agenda_item",
                    Headline: Clip(item.Title, 75),
                    Dek: Clip(item.Detail ?? "Scheduled item", 130),
                    Summary: Clip(item.Detail ?? "Agenda item.", 180),
                    WhyItMatters: "Actionable today.",
                    SourceLabel: "Personal Agenda",
                    SourceUrl: string.Empty,
                    PublishedAt: item.DueAt,
                    Image: BuildFallbackImage("agenda"),
                    PullQuote: null,
                    Facts: item.DueAt is null ? Array.Empty<string>() : new[] { $"Due {item.DueAt:yyyy-MM-dd HH:mm zzz}" }));
            }
        }

        // Ensure minimum body for print pagination by repeating top watchlist candidates.
        while (mustKnow.Count + worthKnowing.Count + watchlist.Count + agenda.Count < MinIssueStories && ranked.Count > 0)
        {
            var candidate = ranked[(mustKnow.Count + worthKnowing.Count + watchlist.Count + agenda.Count) % ranked.Count];
            watchlist.Add(ToIssueStory(candidate, "watchlist", "quick_hit", 60));
        }

        var issue = new NewspaperIssue(
            IssueId: Guid.NewGuid().ToString("N"),
            Title: Clip(request.Title, 80),
            Subtitle: Clip(request.Subtitle, 120),
            IssueDate: request.IssueDate,
            EditionNo: request.EditionNo,
            Timezone: request.Timezone,
            MustKnow: new NewspaperIssueSection(mustKnow),
            WorthKnowing: new NewspaperIssueSection(worthKnowing),
            Agenda: new NewspaperIssueSection(agenda),
            Watchlist: new NewspaperIssueSection(watchlist),
            FooterNote: "Curated automatically from your sources.");

        var validation = _validator.Validate(issue);
        return new ComposeIssueResponse(issue, validation);
    }

    private static List<NewspaperStoryCandidate> DeduplicateBySource(List<NewspaperStoryCandidate> candidates)
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var result = new List<NewspaperStoryCandidate>();
        foreach (var candidate in candidates)
        {
            var source = NormalizeSource(candidate.Source);
            if (seen.Add(source))
            {
                result.Add(candidate);
            }
        }

        return result;
    }

    private static string NormalizeSource(string source)
    {
        return string.IsNullOrWhiteSpace(source) ? "unknown" : source.Trim().ToLowerInvariant();
    }

    private static NewspaperStoryCandidate CreateFallbackCandidate() =>
        new(
            Id: Guid.NewGuid().ToString("N"),
            Source: "watchlist-fallback",
            Url: "https://example.invalid",
            Title: "Pending brief item",
            PublishedAt: DateTimeOffset.UtcNow,
            Author: null,
            RawSummary: "A fallback item ensures editorial continuity until a full source set is available.",
            BodyText: null,
            Topics: null,
            HeroImageUrl: null,
            Score: 0);

    private static NewspaperIssueStory ToIssueStory(NewspaperStoryCandidate candidate, string section, string layoutRole, int summaryWordCap)
    {
        var summarySeed = FirstNonEmpty(candidate.RawSummary, candidate.BodyText, "Summary unavailable.");
        var summary = ClipWords(summarySeed, summaryWordCap);
        var whyItMatters = ClipWords(summarySeed, 18);
        var sourceLabel = SourceLabel(candidate.Source);

        return new NewspaperIssueStory(
            Id: candidate.Id,
            Section: section,
            LayoutRole: layoutRole,
            Headline: Clip(candidate.Title, 75),
            Dek: Clip(summary, 130),
            Summary: summary,
            WhyItMatters: whyItMatters,
            SourceLabel: sourceLabel,
            SourceUrl: candidate.Url,
            PublishedAt: candidate.PublishedAt,
            Image: BuildImage(candidate),
            PullQuote: null,
            Facts: candidate.Topics?.Take(2).ToArray() ?? Array.Empty<string>());
    }

    private static IssueStoryImage BuildImage(NewspaperStoryCandidate candidate)
    {
        if (!string.IsNullOrWhiteSpace(candidate.HeroImageUrl))
        {
            return new IssueStoryImage("hero", candidate.HeroImageUrl, null);
        }

        return BuildFallbackImage(candidate.Source);
    }

    private static IssueStoryImage BuildFallbackImage(string source)
    {
        var slug = string.IsNullOrWhiteSpace(source) ? "source" : source.Trim().ToLowerInvariant();
        var svg = $"<svg xmlns='http://www.w3.org/2000/svg' width='1280' height='720'><rect width='100%' height='100%' fill='#1f2937'/><rect x='0' y='0' width='100%' height='120' fill='#111827'/><text x='48' y='78' fill='#f3f4f6' font-size='56' font-family='Georgia'>{EscapeXml(slug)}</text><text x='48' y='400' fill='#e5e7eb' font-size='44' font-family='Georgia'>Visual fallback</text></svg>";
        var bytes = Encoding.UTF8.GetBytes(svg);
        var data = Convert.ToBase64String(bytes);
        return new IssueStoryImage("fallback", $"data:image/svg+xml;base64,{data}", $"{source} fallback visual");
    }

    private static string SourceLabel(string source) =>
        source.Trim().ToLowerInvariant() switch
        {
            "nyt" => "The New York Times",
            "nytimes" => "The New York Times",
            "economist" => "The Economist",
            "atlantic" => "The Atlantic",
            _ => string.IsNullOrWhiteSpace(source) ? "Unknown Source" : source
        };

    private static string Clip(string text, int maxChars)
    {
        if (string.IsNullOrWhiteSpace(text))
        {
            return string.Empty;
        }

        var trimmed = text.Trim();
        return trimmed.Length <= maxChars ? trimmed : $"{trimmed[..(maxChars - 1)].TrimEnd()}…";
    }

    private static string ClipWords(string text, int maxWords)
    {
        var words = text
            .Split(' ', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .ToArray();

        if (words.Length <= maxWords)
        {
            return string.Join(' ', words);
        }

        return $"{string.Join(' ', words.Take(maxWords))}…";
    }

    private static string FirstNonEmpty(params string?[] candidates)
    {
        foreach (var candidate in candidates)
        {
            if (!string.IsNullOrWhiteSpace(candidate))
            {
                return candidate.Trim();
            }
        }

        return string.Empty;
    }

    private static string EscapeXml(string value) =>
        value
            .Replace("&", "&amp;", StringComparison.Ordinal)
            .Replace("<", "&lt;", StringComparison.Ordinal)
            .Replace(">", "&gt;", StringComparison.Ordinal)
            .Replace("\"", "&quot;", StringComparison.Ordinal)
            .Replace("'", "&apos;", StringComparison.Ordinal);
}
