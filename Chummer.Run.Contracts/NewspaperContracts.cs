namespace Chummer.Run.Contracts.AI.Newspaper;

public sealed record NewspaperStoryCandidate(
    string Id,
    string Source,
    string Url,
    string Title,
    DateTimeOffset? PublishedAt,
    string? Author,
    string? RawSummary,
    string? BodyText,
    IReadOnlyList<string>? Topics,
    string? HeroImageUrl,
    double Score);

public sealed record NewspaperAgendaItem(
    string Id,
    string Title,
    string? Detail,
    DateTimeOffset? DueAt,
    string Priority);

public sealed record ComposeIssueRequest(
    string Title,
    string Subtitle,
    DateOnly IssueDate,
    int EditionNo,
    string Timezone,
    IReadOnlyList<NewspaperStoryCandidate> Candidates,
    IReadOnlyList<NewspaperAgendaItem>? AgendaItems);

public sealed record IssueStoryImage(
    string Kind,
    string Url,
    string? Caption);

public sealed record NewspaperIssueStory(
    string Id,
    string Section,
    string LayoutRole,
    string Headline,
    string Dek,
    string Summary,
    string WhyItMatters,
    string SourceLabel,
    string SourceUrl,
    DateTimeOffset? PublishedAt,
    IssueStoryImage Image,
    string? PullQuote,
    IReadOnlyList<string>? Facts);

public sealed record NewspaperIssueSection(
    IReadOnlyList<NewspaperIssueStory> Stories);

public sealed record NewspaperIssue(
    string IssueId,
    string Title,
    string Subtitle,
    DateOnly IssueDate,
    int EditionNo,
    string Timezone,
    NewspaperIssueSection MustKnow,
    NewspaperIssueSection WorthKnowing,
    NewspaperIssueSection Agenda,
    NewspaperIssueSection Watchlist,
    string FooterNote);

public sealed record ValidationFinding(
    string Code,
    string Message,
    string Severity);

public sealed record IssueValidationReport(
    bool Passed,
    int EstimatedPageCount,
    int ImageCount,
    IReadOnlyList<ValidationFinding> Findings);

public sealed record ComposeIssueResponse(
    NewspaperIssue Issue,
    IssueValidationReport Validation);

public sealed record RenderIssueHtmlRequest(
    NewspaperIssue Issue);

public sealed record RenderIssueHtmlResponse(
    string Html,
    IssueValidationReport Validation);
