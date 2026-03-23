using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Mvc;
using System.Net;
using System.Text;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/public")]
public sealed class PublicProgressController : ControllerBase
{
    private readonly PublicProgressService _progress;
    private readonly PublicLandingService _landing;

    public PublicProgressController(PublicProgressService progress, PublicLandingService landing)
    {
        _progress = progress;
        _landing = landing;
    }

    [HttpGet("/progress")]
    [Produces("text/html")]
    public ContentResult ProgressPage()
        => Content(RenderShell(_progress.LoadReportHtml()), "text/html");

    [HttpGet("progress-report")]
    [HttpGet("/api/public/progress-report")]
    [Produces("application/json")]
    public ContentResult ProgressReport()
        => Content(_progress.LoadReportJson(), "application/json");

    [HttpGet("progress-poster.svg")]
    [HttpGet("/api/public/progress-poster.svg")]
    [Produces("image/svg+xml")]
    public ContentResult ProgressPoster()
        => Content(_progress.LoadPosterSvg(), "image/svg+xml");

    private string RenderShell(string reportHtml)
    {
        var surface = _landing.LoadSurface();
        var nav = string.Join("", surface.PublicRoutes.Select(route =>
        {
            var current = string.Equals(route.Path, "/progress", StringComparison.OrdinalIgnoreCase);
            return current
                ? $"""<span class="progress-shell-nav-current">{Encode(route.Title)}</span>"""
                : $"""<a href="{EncodeHref(route.Path)}">{Encode(route.Title)}</a>""";
        }));
        var authActions = string.Join("", surface.GuestShellActions.Select(action =>
            $"""<a class="progress-shell-action progress-shell-action-{Encode(action.Emphasis)}" href="{EncodeHref(action.Href)}">{Encode(action.Label)}</a>"""));
        var topbar = $$"""
<header class="progress-topbar" aria-label="Chummer public navigation">
  <a class="progress-shell-brand" href="/">Chummer</a>
  <nav class="progress-shell-nav">{{nav}}</nav>
  <div class="progress-shell-actions">{{authActions}}</div>
</header>
""";
        var shellCss = """
    .progress-topbar {
      width: min(var(--max), calc(100vw - 56px));
      margin: 0 auto;
      padding: 18px 0 0;
      display: grid;
      grid-template-columns: auto 1fr auto;
      gap: 18px;
      align-items: center;
      position: relative;
      z-index: 4;
    }
    .progress-shell-brand {
      color: var(--text);
      text-decoration: none;
      font-size: 1.02rem;
      letter-spacing: .16em;
      text-transform: uppercase;
      font-weight: 700;
    }
    .progress-shell-nav {
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      color: rgba(246,251,255,.72);
      font-size: .95rem;
    }
    .progress-shell-nav a {
      color: inherit;
      text-decoration: none;
    }
    .progress-shell-nav-current {
      color: var(--text);
      font-weight: 700;
    }
    .progress-shell-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      justify-content: flex-end;
    }
    .progress-shell-action {
      appearance: none;
      border: 1px solid var(--line-strong);
      color: var(--text);
      text-decoration: none;
      padding: 12px 16px;
      border-radius: 999px;
      font-size: .92rem;
      letter-spacing: .01em;
      background: rgba(255,255,255,.035);
      backdrop-filter: blur(10px);
      transition: transform .18s ease, border-color .2s ease, background .2s ease;
    }
    .progress-shell-action-primary {
      background: linear-gradient(135deg, rgba(107,224,193,.18), rgba(137,182,255,.14));
      border-color: rgba(107,224,193,.38);
    }
    .progress-shell-action:hover {
      transform: translateY(-1px);
      border-color: rgba(255,255,255,.42);
      background: rgba(255,255,255,.07);
    }
""";
        reportHtml = reportHtml.Replace("</style>", shellCss + Environment.NewLine + "  </style>", StringComparison.Ordinal);
        reportHtml = reportHtml.Replace("<div class=\"shell\">", "<div class=\"shell\">" + Environment.NewLine + topbar, StringComparison.Ordinal);
        reportHtml = reportHtml.Replace("min-height: 96vh;", "min-height: calc(96vh - 88px);", StringComparison.Ordinal);
        reportHtml = reportHtml.Replace("@media (max-width: 760px) {", """
    @media (max-width: 980px) {
      .progress-topbar {
        grid-template-columns: 1fr;
        justify-items: flex-start;
      }
      .progress-shell-actions {
        justify-content: flex-start;
      }
    }
    @media (max-width: 760px) {
      .progress-topbar {
        width: min(var(--max), calc(100vw - 36px));
        padding-top: 14px;
      }
      .progress-shell-actions {
        width: 100%;
      }
""", StringComparison.Ordinal);
        return reportHtml;
    }

    private static string Encode(string value) => WebUtility.HtmlEncode(value);

    private static string EncodeHref(string value)
    {
        var builder = new StringBuilder(value.Length);
        foreach (var ch in value)
        {
            builder.Append(ch switch
            {
                '&' => "&amp;",
                '"' => "&quot;",
                '\'' => "&#39;",
                '<' => "&lt;",
                '>' => "&gt;",
                _ => ch.ToString()
            });
        }

        return builder.ToString();
    }
}
