using System.Net;
using System.Text;
using Chummer.Run.Contracts.AI.Newspaper;

namespace Chummer.Run.AI.Services.Newspaper;

public interface INewspaperHtmlRenderer
{
    RenderIssueHtmlResponse Render(NewspaperIssue issue);
}

public sealed class NewspaperHtmlRenderer : INewspaperHtmlRenderer
{
    private readonly IWebHostEnvironment _environment;
    private readonly INewspaperValidationService _validator;

    public NewspaperHtmlRenderer(IWebHostEnvironment environment, INewspaperValidationService validator)
    {
        _environment = environment;
        _validator = validator;
    }

    public RenderIssueHtmlResponse Render(NewspaperIssue issue)
    {
        var templatePath = Path.Combine(_environment.ContentRootPath, "Templates", "Newspaper", "issue.html");
        var template = File.Exists(templatePath)
            ? File.ReadAllText(templatePath)
            : DefaultTemplate();

        var html = template
            .Replace("{{TITLE}}", WebUtility.HtmlEncode(issue.Title), StringComparison.Ordinal)
            .Replace("{{SUBTITLE}}", WebUtility.HtmlEncode(issue.Subtitle), StringComparison.Ordinal)
            .Replace("{{ISSUE_DATE}}", issue.IssueDate.ToString("yyyy-MM-dd"), StringComparison.Ordinal)
            .Replace("{{EDITION_NO}}", issue.EditionNo.ToString(), StringComparison.Ordinal)
            .Replace("{{MUST_KNOW}}", RenderStories(issue.MustKnow.Stories), StringComparison.Ordinal)
            .Replace("{{WORTH_KNOWING}}", RenderStories(issue.WorthKnowing.Stories), StringComparison.Ordinal)
            .Replace("{{AGENDA}}", RenderStories(issue.Agenda.Stories), StringComparison.Ordinal)
            .Replace("{{WATCHLIST}}", RenderStories(issue.Watchlist.Stories), StringComparison.Ordinal)
            .Replace("{{FOOTER_NOTE}}", WebUtility.HtmlEncode(issue.FooterNote), StringComparison.Ordinal);

        var validation = _validator.Validate(issue);
        return new RenderIssueHtmlResponse(html, validation);
    }

    private static string RenderStories(IReadOnlyList<NewspaperIssueStory> stories)
    {
        var sb = new StringBuilder();
        foreach (var story in stories)
        {
            sb.AppendLine("<article class=\"story-card\">");
            sb.AppendLine($"  <h3>{WebUtility.HtmlEncode(story.Headline)}</h3>");
            sb.AppendLine($"  <p class=\"dek\">{WebUtility.HtmlEncode(story.Dek)}</p>");
            sb.AppendLine($"  <img src=\"{WebUtility.HtmlEncode(story.Image.Url)}\" alt=\"story visual\" />");
            sb.AppendLine($"  <div class=\"article-body\">{WebUtility.HtmlEncode(story.Summary)}</div>");
            sb.AppendLine($"  <p class=\"why\">{WebUtility.HtmlEncode(story.WhyItMatters)}</p>");
            sb.AppendLine($"  <p class=\"meta\">{WebUtility.HtmlEncode(story.SourceLabel)}</p>");
            sb.AppendLine("</article>");
        }

        return sb.ToString();
    }

    private static string DefaultTemplate() =>
        """
        <!doctype html>
        <html lang="en">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width, initial-scale=1" />
          <title>{{TITLE}}</title>
          <link rel="stylesheet" href="styles/base.css" />
          <link rel="stylesheet" href="styles/components.css" />
          <link rel="stylesheet" href="styles/print.css" />
        </head>
        <body class="issue">
          <header class="masthead">
            <h1>{{TITLE}}</h1>
            <p>{{SUBTITLE}}</p>
            <div class="issue-rail">Issue {{EDITION_NO}} | {{ISSUE_DATE}}</div>
          </header>

          <section class="section">
            <h2>Must Know</h2>
            <div class="story-grid">{{MUST_KNOW}}</div>
          </section>

          <section class="section">
            <h2>Worth Knowing</h2>
            <div class="story-grid">{{WORTH_KNOWING}}</div>
          </section>

          <section class="section">
            <h2>Agenda</h2>
            <div class="story-grid">{{AGENDA}}</div>
          </section>

          <section class="section">
            <h2>Watchlist</h2>
            <div class="story-grid">{{WATCHLIST}}</div>
          </section>

          <footer class="footer">{{FOOTER_NOTE}}</footer>
        </body>
        </html>
        """;
}
