using System.Net;
using System.Text;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/public")]
public sealed class PublicLandingController : ControllerBase
{
    private readonly PublicLandingService _landing;
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;

    public PublicLandingController(PublicLandingService landing, AccountService accounts, HubIdentityClient identity)
    {
        _landing = landing;
        _accounts = accounts;
        _identity = identity;
    }

    [HttpGet("/")]
    [Produces("text/html")]
    public ContentResult LandingPage()
    {
        var surface = _landing.LoadSurface();
        var body = new StringBuilder();
        body.AppendLine(RenderHero(surface));
        body.AppendLine(RenderCardSection(surface, "what_you_can_do_today"));
        body.AppendLine(RenderCardSection(surface, "why_this_feels_different"));
        body.AppendLine(RenderCardSection(surface, "choose_your_lane"));
        body.AppendLine(RenderCardSection(surface, "whats_real_now"));
        body.AppendLine(RenderCardSection(surface, "coming_next"));
        body.AppendLine(RenderCardSection(surface, "featured_artifacts"));
        body.AppendLine(RenderCardSection(surface, "participate"));
        body.AppendLine(RenderCardSection(surface, "release_shelf"));
        return Content(RenderPage(surface, "Chummer", surface.Subhead, body.ToString()), "text/html");
    }

    [HttpGet("/what-is-chummer")]
    [Produces("text/html")]
    public ContentResult ProductStoryPage()
    {
        var surface = _landing.LoadSurface();
        var body = new StringBuilder()
            .AppendLine(RenderStoryPanel(surface))
            .AppendLine(RenderCardSection(surface, "why_this_feels_different"))
            .AppendLine(RenderCardSection(surface, "choose_your_lane"));
        return Content(RenderPage(surface, "What Is Chummer?", surface.ProofLine, body.ToString()), "text/html");
    }

    [HttpGet("/now")]
    [Produces("text/html")]
    public ContentResult NowPage()
    {
        var surface = _landing.LoadSurface();
        var body = new StringBuilder()
            .AppendLine(RenderCardSection(surface, "whats_real_now"))
            .AppendLine(RenderCardSection(surface, "release_shelf"));
        return Content(RenderPage(surface, "What Is Real Today", "This page exists to prove there is something real here now, not to promise magic later.", body.ToString()), "text/html");
    }

    [HttpGet("/horizons")]
    [Produces("text/html")]
    public ContentResult HorizonsPage()
    {
        var surface = _landing.LoadSurface();
        var lead = "Horizons are real future lanes with canonical names, pain statements, and payoff promises. They are not shipment lies.";
        return Content(RenderPage(surface, "Coming Next", lead, RenderCardSection(surface, "coming_next")), "text/html");
    }

    [HttpGet("/downloads")]
    [Produces("text/html")]
    public ContentResult DownloadsPage()
    {
        var surface = _landing.LoadSurface();
        var lead = "Public drops live here with one shelf, one warning posture, and one obvious path to the current POC.";
        return Content(RenderPage(surface, "Downloads", lead, RenderCardSection(surface, "release_shelf")), "text/html");
    }

    [HttpGet("/participate")]
    [Produces("text/html")]
    public ContentResult ParticipatePage()
    {
        var surface = _landing.LoadSurface();
        var body = new StringBuilder();
        body.AppendLine("""
<section class="panel prose">
  <h2>How participation works</h2>
  <ol>
    <li>Use public feedback when you only want to report a bug or suggest a future.</li>
    <li>Use the booster path only when you explicitly want to lend temporary premium coding capacity.</li>
    <li>Hub keeps the user, group, receipt, reward, and entitlement truth.</li>
    <li>Fleet opens the temporary worker lane and handles device-code auth on the worker host.</li>
    <li>Final landing still goes through review and jury. Participation does not bypass governance.</li>
  </ol>
  <p><a class="inline-link" href="/login?next=/participate/codex">Sign in for the booster console</a></p>
</section>
""");
        body.AppendLine(RenderCardSection(surface, "participate"));
        return Content(RenderPage(surface, "Participate", "There are two clean help lanes: public feedback and the bounded booster path.", body.ToString()), "text/html");
    }

    [HttpGet("/status")]
    [Produces("text/html")]
    public ContentResult StatusPage()
    {
        var surface = _landing.LoadSurface();
        var availableCount = _landing.CardsForBucket(surface, "whats_real_now").Count;
        var horizonCount = _landing.CardsForBucket(surface, "coming_next").Count;
        var body = $$"""
<section class="panel stats">
  <article><span class="eyebrow">Available now</span><strong>{{availableCount}}</strong></article>
  <article><span class="eyebrow">Horizons</span><strong>{{horizonCount}}</strong></article>
  <article><span class="eyebrow">Public routes</span><strong>{{surface.PublicRoutes.Count}}</strong></article>
  <article><span class="eyebrow">Registered overlays</span><strong>{{surface.RegisteredOverlays.Count}}</strong></article>
</section>
{{RenderCardSection(surface, "whats_real_now")}}
{{RenderCardSection(surface, "coming_next")}}
""";
        return Content(RenderPage(surface, "Public Status", "Public status moves from canonical design and visible proof cards, not from repo archaeology.", body), "text/html");
    }

    [HttpGet("/artifacts")]
    [Produces("text/html")]
    public ContentResult ArtifactsPage()
    {
        var surface = _landing.LoadSurface();
        return Content(RenderPage(surface, "Featured Artifacts", "Teasers make future lanes tangible without pretending they are already done.", RenderCardSection(surface, "featured_artifacts")), "text/html");
    }

    [HttpGet("/home")]
    [Produces("text/html")]
    public async Task<IActionResult> HomePage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.SubjectId);
            var body = new StringBuilder()
                .AppendLine($"""
<section class="panel prose">
  <h2>Welcome back</h2>
  <p><strong>{Encode(user.DisplayName)}</strong> is signed in.</p>
  <ul>
    <li>Handle: {Encode(user.Handle)}</li>
    <li>Visibility: {Encode(user.Visibility)}</li>
    <li>Groups: {user.GroupIds.Count}</li>
    <li>Interests and follows are still thin overlays in this preview, but this is the right home for them.</li>
  </ul>
  <p><a class="inline-link" href="/account">Account</a> · <a class="inline-link" href="/participate">Participate</a> · <a class="inline-link" href="/leaderboards">Leaderboards</a></p>
</section>
""")
                .AppendLine(RenderOverlaySection(surface));
            return Content(RenderPage(surface, "Home", "Registered overlays live here: follows, beta interest, participation state, and future advisory surfaces.", body.ToString()), "text/html");
        }
        catch (HubRequestAuthException)
        {
            return Redirect("/login?next=/home");
        }
    }

    [HttpGet("landing")]
    [Produces("application/json")]
    public ActionResult<PublicLandingSurfaceDto> GetLanding() => Ok(_landing.LoadSurface());

    [HttpGet("cards/{bucket}")]
    [Produces("application/json")]
    public ActionResult<IReadOnlyList<PublicFeatureCardDto>> GetCards([FromRoute] string bucket)
    {
        var surface = _landing.LoadSurface();
        return Ok(_landing.CardsForBucket(surface, bucket));
    }

    private string RenderHero(PublicLandingSurfaceDto surface)
    {
        var ctas = string.Join("", surface.HeroCtas.Select(action =>
            $"""<a class="cta {(action.Emphasis == "secondary" ? "secondary" : string.Empty)}" href="{EncodeHref(action.Href)}">{Encode(action.Label)}</a>"""));
        var highlights = string.Join("", surface.SecondaryHighlights.Select(item => $"""<li>{Encode(item)}</li>"""));
        return $$"""
<section class="hero panel">
  <div class="hero-copy">
    <p class="eyebrow">Chummer</p>
    <h1>{{Encode(surface.Headline)}}</h1>
    <p class="lead">{{Encode(surface.Subhead)}}</p>
    <div class="cta-row">{{ctas}}</div>
    <ul class="highlights">{{highlights}}</ul>
  </div>
  <div class="hero-art" aria-hidden="true">
    <div class="poster">
      <span>proof shelf</span>
      <strong>local-first</strong>
      <span>coming next</span>
    </div>
  </div>
</section>
""";
    }

    private string RenderStoryPanel(PublicLandingSurfaceDto surface)
        => $$"""
<section class="panel prose">
  <h2>What the product is trying to do</h2>
  <p>{{Encode(surface.ProofLine)}}</p>
  <p>Chummer is trying to become the place where rules truth, session continuity, public proof, and future artifact lanes feel like one coherent product instead of a bag of unrelated tools.</p>
  <p>That means the homepage should tell you what is real, what is coming, and why it is worth trusting before it asks you to learn any internal language.</p>
</section>
""";

    private string RenderOverlaySection(PublicLandingSurfaceDto surface)
    {
        var overlays = string.Join("", surface.RegisteredOverlays.Select(overlay => $$"""
<article class="card compact">
  <span class="badge">Registered</span>
  <h3><a href="{{EncodeHref(overlay.Path)}}">{{Encode(overlay.Title)}}</a></h3>
  <p>{{Encode(overlay.Summary)}}</p>
</article>
"""));
        return $$"""
<section class="section-block">
  <div class="section-header">
    <p class="eyebrow">Registered overlays</p>
    <h2>What changes when you sign in</h2>
  </div>
  <div class="card-grid">{{overlays}}</div>
</section>
""";
    }

    private string RenderCardSection(PublicLandingSurfaceDto surface, string bucket)
    {
        var section = surface.Sections.FirstOrDefault(item => string.Equals(item.Id, bucket, StringComparison.Ordinal));
        var cards = _landing.CardsForBucket(surface, bucket);
        if (section is null || cards.Count == 0)
        {
            return string.Empty;
        }

        var cardHtml = string.Join("", cards.Select(card => $$"""
<article class="card">
  <div class="media-chip">{{Encode(card.ImageFamily.Replace('_', ' '))}}</div>
  <span class="badge">{{Encode(card.Badge)}}</span>
  <h3><a href="{{EncodeHref(card.Href)}}">{{Encode(card.Title)}}</a></h3>
  <p>{{Encode(card.Summary)}}</p>
  {{(string.IsNullOrWhiteSpace(card.Pain) ? string.Empty : $"<p class=\"micro\"><strong>Pain:</strong> {Encode(card.Pain)}</p>")}}
  {{(string.IsNullOrWhiteSpace(card.Payoff) ? string.Empty : $"<p class=\"micro\"><strong>Payoff:</strong> {Encode(card.Payoff)}</p>")}}
</article>
"""));

        return $$"""
<section class="section-block">
  <div class="section-header">
    <p class="eyebrow">{{Encode(section.Route)}}</p>
    <h2>{{Encode(section.Title)}}</h2>
  </div>
  <div class="card-grid">{{cardHtml}}</div>
</section>
""";
    }

    private string RenderPage(PublicLandingSurfaceDto surface, string title, string lead, string body)
    {
        var navRoutes = surface.PublicRoutes
            .Concat(surface.AuthRoutes.Where(static route => string.Equals(route.Path, "/login", StringComparison.Ordinal)))
            .ToArray();
        var nav = string.Join("", navRoutes.Select(route => $"""<a href="{EncodeHref(route.Path)}">{Encode(route.Title)}</a>"""));
        return $$"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{Encode(title)}} · Chummer</title>
  <style>
    :root {
      --bg: #efe6d2;
      --paper: rgba(255, 251, 242, 0.82);
      --ink: #1a1712;
      --muted: #665d52;
      --accent: #125a58;
      --accent-soft: #d4ebe7;
      --warm: #8d5932;
      --line: rgba(26, 23, 18, 0.12);
      --shadow: 0 18px 40px rgba(26, 23, 18, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(255,255,255,0.55), transparent 34%),
        linear-gradient(180deg, #f5eedf 0%, var(--bg) 55%, #e7dac0 100%);
      font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
    }
    a { color: inherit; text-decoration: none; }
    .shell { max-width: 1180px; margin: 0 auto; padding: 24px 18px 64px; }
    .topbar {
      display: flex; justify-content: space-between; align-items: center; gap: 18px;
      margin-bottom: 22px; padding: 14px 18px; border: 1px solid var(--line); border-radius: 999px;
      background: rgba(255,255,255,0.72); box-shadow: var(--shadow);
    }
    .brand { font-size: 1.1rem; letter-spacing: 0.08em; text-transform: uppercase; }
    .nav { display: flex; flex-wrap: wrap; gap: 14px; color: var(--muted); font-size: 0.95rem; }
    .intro { margin: 0 0 22px; color: var(--muted); max-width: 68ch; }
    .panel {
      background: var(--paper); border: 1px solid var(--line); border-radius: 24px;
      box-shadow: var(--shadow); backdrop-filter: blur(6px);
    }
    .hero {
      display: grid; grid-template-columns: 1.4fr 0.9fr; gap: 24px;
      padding: 28px; margin-bottom: 28px;
    }
    .hero-copy h1 { font-size: clamp(2.4rem, 5vw, 4.2rem); line-height: 0.98; margin: 0 0 12px; }
    .lead { font-size: 1.15rem; color: var(--muted); max-width: 44ch; }
    .eyebrow { margin: 0 0 10px; color: var(--warm); text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.78rem; }
    .cta-row { display: flex; flex-wrap: wrap; gap: 12px; margin: 18px 0 20px; }
    .cta, .inline-link {
      display: inline-flex; align-items: center; justify-content: center; gap: 8px;
      padding: 11px 16px; border-radius: 999px; background: var(--accent); color: white;
    }
    .cta.secondary { background: var(--warm); }
    .highlights { margin: 0; padding-left: 18px; color: var(--muted); }
    .hero-art { display: flex; align-items: stretch; }
    .poster {
      flex: 1; border-radius: 22px; padding: 24px;
      background:
        linear-gradient(160deg, rgba(18,90,88,0.94), rgba(16,47,60,0.94)),
        radial-gradient(circle at top right, rgba(255,255,255,0.18), transparent 36%);
      color: #f3f8f8; display: flex; flex-direction: column; justify-content: space-between;
      min-height: 300px; text-transform: uppercase; letter-spacing: 0.08em;
    }
    .poster strong { font-size: clamp(1.8rem, 3vw, 2.8rem); line-height: 1; }
    .section-block { margin: 0 0 26px; }
    .section-header { margin-bottom: 14px; }
    .section-header h2 { margin: 0; font-size: 1.7rem; }
    .card-grid {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px;
    }
    .card {
      background: rgba(255,255,255,0.76); border: 1px solid var(--line); border-radius: 20px;
      padding: 16px; box-shadow: var(--shadow);
    }
    .card.compact { min-height: 0; }
    .card h3 { margin: 10px 0 8px; font-size: 1.15rem; }
    .card p { margin: 0 0 8px; color: var(--muted); }
    .media-chip {
      display: inline-flex; align-items: center; justify-content: center;
      min-width: 94px; padding: 6px 10px; border-radius: 999px;
      background: var(--accent-soft); color: var(--accent); font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.08em;
    }
    .badge {
      display: inline-flex; margin-top: 12px; padding: 5px 10px; border-radius: 999px;
      background: #f0e0cb; color: var(--warm); font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.08em;
    }
    .micro { font-size: 0.92rem; }
    .prose { padding: 18px 20px; }
    .prose h2 { margin-top: 0; }
    .prose ol, .prose ul { margin-bottom: 0; color: var(--muted); }
    .stats {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px; padding: 18px; margin-bottom: 20px;
    }
    .stats article {
      background: rgba(255,255,255,0.72); border: 1px solid var(--line); border-radius: 16px; padding: 14px;
    }
    .stats strong { display: block; font-size: 2rem; margin-top: 4px; }
    footer { margin-top: 28px; color: var(--muted); }
    footer sub { font-size: 0.76rem; line-height: 1.6; }
    @media (max-width: 860px) {
      .hero { grid-template-columns: 1fr; }
      .topbar { border-radius: 22px; align-items: flex-start; flex-direction: column; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div class="brand">Chummer.run</div>
      <nav class="nav">{{nav}}</nav>
    </header>
    <p class="intro">{{Encode(lead)}}</p>
    {{body}}
    <footer>
      <hr />
      <sub>
        Canonical source: {{Encode(surface.FooterCanonicalSource)}}<br />
        {{Encode(surface.FooterGeneratedNote)}}<br />
        Public routes may move faster than the deeper guide, but they may not outrun canonical design.
      </sub>
    </footer>
  </main>
</body>
</html>
""";
    }

    private static string Encode(string value) => WebUtility.HtmlEncode(value);

    private static string EncodeHref(string value) => WebUtility.HtmlEncode(value);
}
