using Chummer.Run.Api.Services;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Mvc;
using System.Net;
using System.Text;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/public")]
public sealed class PublicProgressController : ControllerBase
{
    private readonly PublicProgressService _progress;
    private readonly PublicNavigationService _navigation;
    private readonly HubPageChromeService _chrome;
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;
    private readonly IAntiforgery _antiforgery;
    private readonly ILogger<PublicProgressController> _logger;

    public PublicProgressController(
        PublicProgressService progress,
        PublicNavigationService navigation,
        HubPageChromeService chrome,
        AccountService accounts,
        HubIdentityClient identity,
        IAntiforgery antiforgery,
        ILogger<PublicProgressController> logger)
    {
        _progress = progress;
        _navigation = navigation;
        _chrome = chrome;
        _accounts = accounts;
        _identity = identity;
        _antiforgery = antiforgery;
        _logger = logger;
    }

    [HttpGet("/progress")]
    [Produces("text/html")]
    public async Task<ContentResult> ProgressPage(CancellationToken cancellationToken)
    {
        var chrome = await BuildChromeAsync(
            title: "Progress",
            description: "Public progress and milestone status for Chummer.",
            currentPath: "/progress",
            cancellationToken);
        var antiForgeryToken = chrome.Authenticated
            ? _antiforgery.GetAndStoreTokens(HttpContext).RequestToken
            : null;
        return Content(RenderShell(_progress.LoadReportHtml(), chrome, antiForgeryToken), "text/html");
    }

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

    private string RenderShell(string reportHtml, SiteChromeViewModel chrome, string? antiForgeryToken)
    {
        var navigation = _navigation.LoadNavigation();
        var nav = string.Join("", navigation.Primary.Append(new PublicNavigationLink("Progress", "/progress")).Select(route =>
        {
            var current = string.Equals(route.Href, "/progress", StringComparison.OrdinalIgnoreCase);
            return current
                ? $"""<span class="progress-shell-nav-current">{Encode(route.Label)}</span>"""
                : $"""<a href="{EncodeHref(route.Href)}">{Encode(route.Label)}</a>""";
        }));
        var authActions = string.Join("", chrome.HeaderActions.Select(action =>
        {
            if (string.Equals(action.Href, "/logout", StringComparison.OrdinalIgnoreCase)
                && !string.IsNullOrWhiteSpace(antiForgeryToken))
            {
                return $$"""
<form method="post" action="/logout" class="progress-shell-action-form">
  <input type="hidden" name="__RequestVerificationToken" value="{{Encode(antiForgeryToken)}}" />
  <button class="progress-shell-action progress-shell-action-{{Encode(action.Tone)}} progress-shell-action-button" type="submit">{{Encode(action.Label)}}</button>
</form>
""";
            }

            return action.Current
                ? $"""<span class="progress-shell-action progress-shell-action-current">{Encode(action.Label)}</span>"""
                : $"""<a class="progress-shell-action progress-shell-action-{Encode(action.Tone)}" href="{EncodeHref(action.Href)}">{Encode(action.Label)}</a>""";
        }));
        var signedInLabel = chrome.Authenticated && !string.IsNullOrWhiteSpace(chrome.SignedInLabel)
            ? $"""<p class="progress-shell-signed-in">Signed in as {Encode(chrome.SignedInLabel!)}</p>"""
            : string.Empty;
        var topbar = $$"""
<header class="progress-topbar" aria-label="Chummer public navigation">
  <a class="progress-shell-brand" href="/">Chummer</a>
  <nav class="progress-shell-nav">{{nav}}</nav>
  <div class="progress-shell-controls">
    {{signedInLabel}}
    <div class="progress-shell-actions">{{authActions}}</div>
  </div>
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
    .progress-shell-controls {
      display: grid;
      gap: 8px;
      justify-items: flex-end;
    }
    .progress-shell-signed-in {
      margin: 0;
      color: rgba(246,251,255,.68);
      font-size: .84rem;
    }
    .progress-shell-actions {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      justify-content: flex-end;
    }
    .progress-shell-action-form {
      margin: 0;
    }
    .progress-shell-action-button {
      font: inherit;
      cursor: pointer;
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
    .progress-shell-action-current {
      background: rgba(255,255,255,.06);
      border-color: rgba(255,255,255,.16);
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
      .progress-shell-controls {
        justify-items: flex-start;
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

    private async Task<SiteChromeViewModel> BuildChromeAsync(
        string title,
        string description,
        string currentPath,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return _chrome.BuildAuthenticatedChrome(title, description, currentPath, user.DisplayName);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return _chrome.BuildPublicChrome(title, description, currentPath);
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Preserving signed-in progress chrome after identity failure.");
            if (Request.Cookies.ContainsKey(HubBrowserAuthConstants.AccessTokenCookieName))
            {
                return _chrome.BuildAuthenticatedChrome(title, description, currentPath, "Signed in");
            }

            return _chrome.BuildPublicChrome(title, description, currentPath);
        }
        catch (Exception ex) when (
            ex is HttpRequestException
            or System.Text.Json.JsonException
            || (ex is TaskCanceledException && !cancellationToken.IsCancellationRequested))
        {
            _logger.LogWarning(ex, "Falling back while building progress chrome.");
            if (Request.Cookies.ContainsKey(HubBrowserAuthConstants.AccessTokenCookieName))
            {
                return _chrome.BuildAuthenticatedChrome(title, description, currentPath, "Signed in");
            }

            return _chrome.BuildPublicChrome(title, description, currentPath);
        }
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
