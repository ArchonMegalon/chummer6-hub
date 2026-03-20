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
    private readonly PublicReleaseManifestService _releases;
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;

    public PublicLandingController(
        PublicLandingService landing,
        PublicReleaseManifestService releases,
        AccountService accounts,
        HubIdentityClient identity)
    {
        _landing = landing;
        _releases = releases;
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
        body.AppendLine(RenderCardSection(surface, "what_you_can_do_today", "/"));
        body.AppendLine(RenderCardSection(surface, "why_this_feels_different", "/"));
        body.AppendLine(RenderCardSection(surface, "choose_your_lane", "/"));
        body.AppendLine(RenderCardSection(surface, "whats_real_now", "/"));
        body.AppendLine(RenderCardSection(surface, "coming_next", "/"));
        body.AppendLine(RenderCardSection(surface, "featured_artifacts", "/"));
        body.AppendLine(RenderCardSection(surface, "participate", "/"));
        body.AppendLine(RenderCardSection(surface, "release_shelf", "/"));
        return Content(RenderPage(surface, "Chummer", surface.Subhead, body.ToString(), "/"), "text/html");
    }

    [HttpGet("/what-is-chummer")]
    [Produces("text/html")]
    public ContentResult ProductStoryPage()
    {
        var surface = _landing.LoadSurface();
        var body = new StringBuilder()
            .AppendLine(RenderStoryPanel(surface))
            .AppendLine(RenderGuidePanel())
            .AppendLine(RenderCardSection(surface, "why_this_feels_different", "/what-is-chummer"))
            .AppendLine(RenderCardSection(surface, "choose_your_lane", "/what-is-chummer"));
        return Content(RenderPage(surface, "What Is Chummer?", surface.ProofLine, body.ToString(), "/what-is-chummer"), "text/html");
    }

    [HttpGet("/now")]
    [Produces("text/html")]
    public ContentResult NowPage()
    {
        var surface = _landing.LoadSurface();
        var body = new StringBuilder()
            .AppendLine(RenderCardSection(surface, "whats_real_now", "/now"))
            .AppendLine(RenderCardSection(surface, "release_shelf", "/now"));
        return Content(RenderPage(surface, "What Is Real Today", "This page exists to prove there is something real here now, not to promise magic later.", body.ToString(), "/now"), "text/html");
    }

    [HttpGet("/horizons")]
    [Produces("text/html")]
    public ContentResult HorizonsPage()
    {
        var surface = _landing.LoadSurface();
        var lead = "Horizons are real future lanes with canonical names, pain statements, and payoff promises. They are not shipment lies.";
        return Content(RenderPage(surface, "Coming Next", lead, RenderCardSection(surface, "coming_next", "/horizons"), "/horizons"), "text/html");
    }

    [HttpGet("/downloads")]
    [Produces("text/html")]
    public ContentResult DownloadsPage()
    {
        var surface = _landing.LoadSurface();
        var manifest = _releases.LoadManifest();
        var body = new StringBuilder()
            .AppendLine(RenderReleaseShelf(manifest))
            .AppendLine(RenderCardSection(surface, "release_shelf", "/downloads"));
        var lead = "The public downloads shelf should speak from the live release manifest first, then point deeper when the shelf is still sparse.";
        return Content(RenderPage(surface, "Downloads", lead, body.ToString(), "/downloads"), "text/html");
    }

    [HttpGet("/participate")]
    [Produces("text/html")]
    public ContentResult ParticipatePage()
    {
        var surface = _landing.LoadSurface();
        var body = new StringBuilder();
        body.AppendLine(RenderParticipatePanels());
        body.AppendLine(RenderCardSection(surface, "participate", "/participate"));
        return Content(RenderPage(surface, "Participate", "There are two clean help lanes here: public feedback and the optional bounded booster path.", body.ToString(), "/participate"), "text/html");
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
{{RenderCardSection(surface, "whats_real_now", "/status")}}
{{RenderCardSection(surface, "coming_next", "/status")}}
""";
        return Content(RenderPage(surface, "Public Status", "Public status moves from canonical design and visible proof cards, not from repo archaeology.", body, "/status"), "text/html");
    }

    [HttpGet("/artifacts")]
    [Produces("text/html")]
    public ContentResult ArtifactsPage()
    {
        var surface = _landing.LoadSurface();
        var lead = "Artifact teasers should point at deliberate related surfaces, not bounce you back onto the same shelf.";
        return Content(RenderPage(surface, "Featured Artifacts", lead, RenderCardSection(surface, "featured_artifacts", "/artifacts"), "/artifacts"), "text/html");
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
    <li>Follow surfaces, beta-interest state, and participation history still live as honest preview overlays here.</li>
  </ul>
  <p><a class="inline-link" href="/account">Account</a> · <a class="inline-link" href="/participate">Participate</a> · <a class="inline-link" href="/leaderboards">Leaderboards</a></p>
</section>
""")
                .AppendLine(RenderOverlaySection(surface));
            return Content(RenderPage(surface, "Home", "Registered overlays live here: follows, beta interest, participation state, and future advisory surfaces.", body.ToString(), "/home"), "text/html");
        }
        catch (HubRequestAuthException)
        {
            return Redirect("/login?next=/home");
        }
    }

    [HttpGet("landing")]
    [HttpGet("/api/public/landing")]
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
        var heroAsset = ResolveSectionAsset(surface, "hero");
        return $$"""
<section class="hero panel">
  <div class="hero-copy">
    <p class="eyebrow">Chummer</p>
    <h1>{{Encode(surface.Headline)}}</h1>
    <p class="lead">{{Encode(surface.Subhead)}}</p>
    <p class="proof-line">{{Encode(surface.ProofLine)}}</p>
    <div class="cta-row">{{ctas}}</div>
    <ul class="highlights">{{highlights}}</ul>
  </div>
  <div class="hero-visual">
    {{RenderAssetFigure(heroAsset, "Public product hero", "hero")}}
  </div>
</section>
""";
    }

    private string RenderStoryPanel(PublicLandingSurfaceDto surface)
        => $$"""
<section class="panel prose">
  <h2>What the product is trying to do</h2>
  <p>{{Encode(surface.ProofLine)}}</p>
  <p>Chummer is trying to make rules truth, session continuity, public proof, and future artifact lanes feel like one coherent product instead of a bag of unrelated tools.</p>
  <p>The front door should tell you what is real, what is coming, and why it is worth trusting before it asks you to learn any internal language.</p>
</section>
""";

    private string RenderGuidePanel()
        => """
<section id="public-guide" class="panel prose">
  <h2>Deeper guide, same product posture</h2>
  <p>`chummer.run` stays short and product-facing. The deeper guide can go longer, but it should still feel like the same front door rather than a repo detour.</p>
  <p><a class="inline-link" href="https://github.com/ArchonMegalon/Chummer6">Open the deeper guide fallback</a></p>
</section>
""";

    private string RenderParticipatePanels()
        => """
<section class="panel prose">
  <h2>How participation works</h2>
  <ol>
    <li>The free path stays free. Public feedback and future suggestions do not require sign-in.</li>
    <li>The booster path is optional and temporary. It exists only for people who want to lend premium capacity on purpose.</li>
    <li>Recognition, account state, and future follow-up belong in your signed-in home, not in public issue noise.</li>
  </ol>
</section>
<section id="report-a-problem" class="panel prose">
  <h2>Report a problem</h2>
  <p>Use the public issue tracker when something is broken, unclear, or missing from the public-facing story.</p>
  <p><a class="inline-link" href="https://github.com/ArchonMegalon/Chummer6/issues">Open the public issue tracker</a></p>
</section>
<section id="suggest-a-future" class="panel prose">
  <h2>Suggest a future</h2>
  <p>Future suggestions are welcome as advisory signals. They help shape the queue without pretending public comments become design canon by themselves.</p>
  <p><a class="inline-link" href="https://github.com/ArchonMegalon/Chummer6/issues">Share a public future request</a></p>
</section>
<section id="booster-path" class="panel prose">
  <h2>Optional booster path</h2>
  <p>If you want to lend temporary premium help, sign in first. The hosted shell should explain the consent and show the bounded participation console there.</p>
  <p><a class="cta" href="/login?next=/participate/codex">Sign in for the booster console</a></p>
</section>
<section id="beta-waitlist" class="panel prose">
  <h2>Beta waitlist</h2>
  <p>Follow-up previews and future gated surfaces should land behind a real account lane, not a vague bounce to generic home.</p>
  <p><a class="cta secondary" href="/signup?next=/home">Create account for beta interest</a></p>
</section>
""";

    private string RenderReleaseShelf(PublicReleaseManifestDto manifest)
    {
        var publishedAt = manifest.PublishedAt.ToUniversalTime().ToString("yyyy-MM-dd");
        if (manifest.Downloads.Count == 0)
        {
            return $$"""
<section class="panel prose">
  <h2>Release shelf</h2>
  <p>Version {{Encode(manifest.Version)}} · {{Encode(manifest.Channel)}} · {{Encode(publishedAt)}}</p>
  <p>{{Encode(manifest.Message ?? "No downloadable artifacts are on the public shelf yet.")}}</p>
  <p><a class="inline-link" href="https://github.com/ArchonMegalon/Chummer6/releases">Open GitHub releases fallback</a></p>
</section>
""";
        }

        var cards = string.Join("", manifest.Downloads.Select(download => $$"""
<article class="card download-card">
  <span class="badge">{{Encode(download.Platform)}}</span>
  <h3>{{Encode(download.Id)}}</h3>
  <p>Published {{Encode(publishedAt)}} on the {{Encode(manifest.Channel)}} channel.</p>
  <p class="micro">SHA-256: <code>{{Encode(ShortChecksum(download.Sha256))}}</code></p>
  {{(download.SizeBytes is long size ? $"<p class=\"micro\">Size: {Encode(FormatBytes(size))}</p>" : string.Empty)}}
  <div class="card-actions">
    <a class="card-link" href="{{EncodeHref(download.Url)}}">Download</a>
  </div>
</article>
"""));
        return $$"""
<section class="section-block" id="release-manifest">
  <div class="section-header">
    <p class="eyebrow">/downloads/releases.json</p>
    <h2>Live release manifest</h2>
    <p class="section-lead">Version {{Encode(manifest.Version)}} · {{Encode(manifest.Channel)}} · {{Encode(publishedAt)}}</p>
  </div>
  <div class="card-grid">{{cards}}</div>
</section>
""";
    }

    private string RenderOverlaySection(PublicLandingSurfaceDto surface)
    {
        var overlays = string.Join("", surface.RegisteredOverlays.Select(overlay => $$"""
<article id="{{Encode(ToAnchorId(overlay.Id))}}" class="card compact">
  <span class="badge">Registered</span>
  <h3>{{Encode(overlay.Title)}}</h3>
  <p>{{Encode(overlay.Summary)}}</p>
  <div class="card-actions"><a class="card-link" href="{{EncodeHref(overlay.Path)}}">Open overlay</a></div>
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

    private string RenderCardSection(PublicLandingSurfaceDto surface, string bucket, string currentPath)
    {
        var section = surface.Sections.FirstOrDefault(item => string.Equals(item.Id, bucket, StringComparison.Ordinal));
        var cards = _landing.CardsForBucket(surface, bucket);
        if (section is null || cards.Count == 0)
        {
            return string.Empty;
        }

        var cardHtml = string.Join("", cards.Select(card => RenderCard(surface, card, currentPath)));
        return $$"""
<section id="{{Encode(ToAnchorId(section.Id))}}" class="section-block">
  <div class="section-header">
    <p class="eyebrow">{{Encode(section.Route)}}</p>
    <h2>{{Encode(section.Title)}}</h2>
  </div>
  <div class="card-grid">{{cardHtml}}</div>
</section>
""";
    }

    private string RenderCard(PublicLandingSurfaceDto surface, PublicFeatureCardDto card, string currentPath)
    {
        var asset = ResolveCardAsset(surface, card);
        var primaryHref = ResolveCardHref(card, registeredShell: false);
        var primaryActionAllowed = !string.IsNullOrWhiteSpace(primaryHref) && !IsBlockedSelfLink(currentPath, primaryHref, card.SelfLinkAllowed);
        var ctaLabel = ResolvePrimaryLabel(card);
        var fallback = card.ExternalOk && !string.IsNullOrWhiteSpace(card.FallbackRoute)
            ? $$"""<a class="meta-link" href="{{EncodeHref(card.FallbackRoute!)}}">{{Encode(card.FallbackLabel ?? "Open external fallback")}}</a>"""
            : string.Empty;
        var teaser = !primaryActionAllowed && string.Equals(card.RenderMode, "teaser", StringComparison.OrdinalIgnoreCase)
            ? """<span class="card-static">Teaser only</span>"""
            : string.Empty;
        var action = primaryActionAllowed
            ? $$"""<a class="card-link" href="{{EncodeHref(primaryHref!)}}">{{Encode(ctaLabel)}}</a>"""
            : string.Empty;

        return $$"""
<article id="{{Encode(ToAnchorId(card.Id))}}" class="card">
  {{RenderAssetFigure(asset, card.Title, "card")}}
  <span class="badge">{{Encode(card.Badge)}}</span>
  <h3>{{Encode(card.Title)}}</h3>
  <p>{{Encode(card.Summary)}}</p>
  {{(string.IsNullOrWhiteSpace(card.Pain) ? string.Empty : $"<p class=\"micro\"><strong>Pain:</strong> {Encode(card.Pain)}</p>")}}
  {{(string.IsNullOrWhiteSpace(card.Payoff) ? string.Empty : $"<p class=\"micro\"><strong>Payoff:</strong> {Encode(card.Payoff)}</p>")}}
  <div class="card-actions">
    {{action}}
    {{teaser}}
    {{fallback}}
  </div>
</article>
""";
    }

    private string RenderAssetFigure(PublicLandingAssetDto? asset, string fallbackLabel, string size)
    {
        var assetClass = asset is null
            ? "asset--neutral"
            : $"asset--{ToAnchorId(asset.FallbackStyle)}";
        var caption = asset?.Caption ?? fallbackLabel;
        var alt = asset?.Alt ?? fallbackLabel;
        var media = asset is { PosterUrl.Length: > 0 }
            ? $$"""
<picture class="asset-media">
  {{(asset.MobilePosterUrl is { Length: > 0 } mobile ? $"<source media=\"(max-width: 720px)\" srcset=\"{EncodeHref(mobile)}\" />" : string.Empty)}}
  <img src="{{EncodeHref(asset.PosterUrl!)}}" alt="{{Encode(alt)}}" loading="lazy" />
</picture>
"""
            : $$"""
<div class="asset-fallback" aria-hidden="true"></div>
<span class="sr-only">{{Encode(alt)}}</span>
""";
        return $$"""
<figure class="asset-frame asset-frame--{{Encode(size)}} {{assetClass}}">
  {{media}}
  <figcaption>{{Encode(caption)}}</figcaption>
</figure>
""";
    }

    private string RenderPage(PublicLandingSurfaceDto surface, string title, string lead, string body, string currentPath)
    {
        var nav = string.Join("", surface.PublicRoutes.Select(route =>
        {
            var current = string.Equals(route.Path, currentPath, StringComparison.OrdinalIgnoreCase);
            return current
                ? $"""<span class="nav-current">{Encode(route.Title)}</span>"""
                : $"""<a href="{EncodeHref(route.Path)}">{Encode(route.Title)}</a>""";
        }));
        var authActions = string.Join("", surface.GuestShellActions.Select(action =>
        {
            var current = string.Equals(NormalizeRoute(currentPath), NormalizeRoute(action.Href), StringComparison.OrdinalIgnoreCase);
            return current
                ? $"""<span class="shell-action shell-action-current">{Encode(action.Label)}</span>"""
                : $"""<a class="shell-action shell-action-{Encode(action.Emphasis)}" href="{EncodeHref(action.Href)}">{Encode(action.Label)}</a>""";
        }));
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
      --paper: rgba(255, 251, 242, 0.84);
      --ink: #161311;
      --muted: #62584d;
      --accent: #0f5c5a;
      --accent-soft: #d8ebe8;
      --warm: #8b5630;
      --line: rgba(22, 19, 17, 0.12);
      --shadow: 0 18px 40px rgba(22, 19, 17, 0.08);
      --ui: "Avenir Next", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
      --display: "Iowan Old Style", Georgia, "Palatino Linotype", serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(255,255,255,0.56), transparent 32%),
        linear-gradient(180deg, #f7f1e4 0%, var(--bg) 58%, #e2d2b6 100%);
      font-family: var(--display);
    }
    a { color: inherit; text-decoration: none; }
    code { font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; }
    .shell { max-width: 1180px; margin: 0 auto; padding: 24px 18px 72px; }
    .topbar {
      display: grid; grid-template-columns: auto 1fr auto; gap: 18px; align-items: center;
      margin-bottom: 22px; padding: 16px 18px; border: 1px solid var(--line); border-radius: 999px;
      background: rgba(255,255,255,0.76); box-shadow: var(--shadow); backdrop-filter: blur(8px);
    }
    .brand { font-family: var(--ui); font-size: 1.05rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; }
    .nav { display: flex; flex-wrap: wrap; gap: 14px; color: var(--muted); font-family: var(--ui); font-size: 0.94rem; }
    .nav-current { color: var(--ink); font-weight: 700; }
    .topbar-actions { display: flex; flex-wrap: wrap; gap: 10px; justify-content: flex-end; }
    .shell-action, .cta, .inline-link, .card-link, .meta-link, .card-static {
      display: inline-flex; align-items: center; justify-content: center; gap: 8px;
      border-radius: 999px; font-family: var(--ui);
    }
    .shell-action { padding: 10px 14px; border: 1px solid transparent; }
    .shell-action-primary, .cta, .card-link { background: var(--accent); color: #fff; }
    .shell-action-secondary, .cta.secondary, .inline-link { background: var(--warm); color: #fff; }
    .shell-action-current { background: rgba(15, 92, 90, 0.12); color: var(--accent); border-color: rgba(15, 92, 90, 0.18); }
    .intro { margin: 0 0 22px; color: var(--muted); max-width: 68ch; font-size: 1.05rem; }
    .panel {
      background: var(--paper); border: 1px solid var(--line); border-radius: 24px;
      box-shadow: var(--shadow); backdrop-filter: blur(6px);
    }
    .hero {
      display: grid; grid-template-columns: 1.15fr 0.85fr; gap: 26px;
      padding: 28px; margin-bottom: 28px;
    }
    .hero-copy h1 { font-size: clamp(2.5rem, 5vw, 4.4rem); line-height: 0.96; margin: 0 0 12px; }
    .lead { font-size: 1.15rem; color: var(--muted); max-width: 44ch; margin: 0 0 12px; }
    .proof-line { margin: 0; color: var(--ink); max-width: 42ch; }
    .eyebrow { margin: 0 0 10px; color: var(--warm); text-transform: uppercase; letter-spacing: 0.12em; font-size: 0.78rem; font-family: var(--ui); }
    .cta-row { display: flex; flex-wrap: wrap; gap: 12px; margin: 18px 0 20px; }
    .highlights { margin: 0; padding-left: 18px; color: var(--muted); }
    .hero-visual { display: flex; align-items: stretch; }
    .section-block { margin: 0 0 26px; }
    .section-header { margin-bottom: 14px; }
    .section-header h2 { margin: 0 0 4px; font-size: 1.72rem; }
    .section-lead { margin: 0; color: var(--muted); }
    .card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }
    .card {
      background: rgba(255,255,255,0.78); border: 1px solid var(--line); border-radius: 22px;
      padding: 16px; box-shadow: var(--shadow); display: flex; flex-direction: column; gap: 10px;
    }
    .card.compact { min-height: 0; }
    .card h3 { margin: 0; font-size: 1.14rem; }
    .card p { margin: 0; color: var(--muted); }
    .badge {
      display: inline-flex; width: fit-content; padding: 5px 10px; border-radius: 999px;
      background: #f1dfca; color: var(--warm); font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.08em; font-family: var(--ui);
    }
    .micro { font-size: 0.92rem; }
    .card-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: auto; padding-top: 6px; }
    .card-link, .inline-link { padding: 10px 14px; }
    .meta-link, .card-static {
      padding: 9px 12px; background: rgba(15, 92, 90, 0.08); color: var(--accent);
      border: 1px solid rgba(15, 92, 90, 0.14);
    }
    .asset-frame {
      position: relative; margin: 0; overflow: hidden; border-radius: 18px;
      border: 1px solid rgba(22, 19, 17, 0.08); background: rgba(255,255,255,0.55);
    }
    .asset-frame--hero { min-height: 340px; }
    .asset-frame--card { min-height: 165px; }
    .asset-frame figcaption {
      position: absolute; left: 14px; right: 14px; bottom: 12px; z-index: 2;
      color: rgba(255,255,255,0.96); font-family: var(--ui); font-size: 0.8rem;
      letter-spacing: 0.08em; text-transform: uppercase;
    }
    .asset-media, .asset-media img, .asset-fallback { display: block; width: 100%; height: 100%; }
    .asset-media img { object-fit: cover; }
    .asset-fallback {
      position: absolute; inset: 0;
      background:
        radial-gradient(circle at 20% 18%, rgba(255,255,255,0.24), transparent 28%),
        radial-gradient(circle at 78% 20%, rgba(255,255,255,0.12), transparent 24%),
        linear-gradient(140deg, rgba(255,255,255,0.08), transparent 45%);
    }
    .asset--neutral .asset-fallback { background: linear-gradient(135deg, #7e8b91, #44545d); }
    .asset--boulevard-glass .asset-fallback { background: linear-gradient(145deg, #0b4151, #1b6b6d 45%, #8f5a30 100%); }
    .asset--archive-paper .asset-fallback { background: linear-gradient(145deg, #5b3a28, #927150 52%, #e0c9a4 100%); }
    .asset--dossier-lamplight .asset-fallback { background: linear-gradient(145deg, #24343f, #47606a 42%, #b58a54 100%); }
    .asset--facility-cyan-night .asset-fallback { background: linear-gradient(145deg, #102938, #1a5464 50%, #9fbac2 100%); }
    .asset--future-boulevard .asset-fallback { background: linear-gradient(145deg, #1b2339, #37537d 50%, #d9925d 100%); }
    .asset--simulation-amber .asset-fallback { background: linear-gradient(145deg, #241f18, #5a4a31 48%, #dfb66a 100%); }
    .asset--streetfront-rain .asset-fallback { background: linear-gradient(145deg, #1e2b35, #445f69 46%, #89a3a3 100%); }
    .asset--solo-cockpit .asset-fallback { background: linear-gradient(145deg, #17262f, #294f59 44%, #9b6e44 100%); }
    .asset--prop-table .asset-fallback { background: linear-gradient(145deg, #35261d, #6f4f3d 46%, #cab187 100%); }
    .prose { padding: 18px 20px; }
    .prose h2 { margin-top: 0; }
    .prose ol, .prose ul, .prose p { color: var(--muted); }
    .stats {
      display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px; padding: 18px; margin-bottom: 20px;
    }
    .stats article {
      background: rgba(255,255,255,0.72); border: 1px solid var(--line); border-radius: 16px; padding: 14px;
    }
    .stats strong { display: block; font-size: 2rem; margin-top: 4px; }
    .sr-only {
      position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
      overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
    }
    footer { margin-top: 28px; color: var(--muted); }
    footer sub { font-size: 0.76rem; line-height: 1.7; }
    @media (max-width: 960px) {
      .topbar { grid-template-columns: 1fr; border-radius: 22px; }
      .topbar-actions { justify-content: flex-start; }
      .hero { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <header class="topbar">
      <div class="brand">Chummer.run</div>
      <nav class="nav">{{nav}}</nav>
      <div class="topbar-actions">{{authActions}}</div>
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

    private PublicLandingAssetDto? ResolveSectionAsset(PublicLandingSurfaceDto surface, string sectionId)
        => surface.Assets.FirstOrDefault(asset => string.Equals(asset.SectionId, sectionId, StringComparison.Ordinal))
           ?? surface.Assets.FirstOrDefault(asset => string.Equals(asset.AssetSlot, $"section_{sectionId}", StringComparison.Ordinal));

    private PublicLandingAssetDto? ResolveCardAsset(PublicLandingSurfaceDto surface, PublicFeatureCardDto card)
        => surface.Assets.FirstOrDefault(asset => string.Equals(asset.AssetSlot, card.AssetSlot, StringComparison.Ordinal));

    private static string ResolveCardHref(PublicFeatureCardDto card, bool registeredShell)
    {
        if (registeredShell && !string.IsNullOrWhiteSpace(card.RegisteredHref))
        {
            return card.RegisteredHref!;
        }

        if (!registeredShell && !string.IsNullOrWhiteSpace(card.GuestHref))
        {
            return card.GuestHref!;
        }

        if (!string.IsNullOrWhiteSpace(card.DetailRoute))
        {
            return card.DetailRoute!;
        }

        return card.Href;
    }

    private static bool IsBlockedSelfLink(string currentPath, string targetHref, bool selfLinkAllowed)
    {
        if (selfLinkAllowed)
        {
            return false;
        }

        if (!string.Equals(NormalizeRoute(currentPath), NormalizeRoute(targetHref), StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        return !targetHref.Contains('#', StringComparison.Ordinal);
    }

    private static string NormalizeRoute(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return "/";
        }

        var trimmed = value.Trim();
        if (Uri.TryCreate(trimmed, UriKind.Absolute, out var absolute))
        {
            trimmed = absolute.AbsolutePath;
        }

        var hash = trimmed.IndexOf('#');
        if (hash >= 0)
        {
            trimmed = trimmed[..hash];
        }

        var query = trimmed.IndexOf('?');
        if (query >= 0)
        {
            trimmed = trimmed[..query];
        }

        return string.IsNullOrWhiteSpace(trimmed) ? "/" : trimmed;
    }

    private static string ResolvePrimaryLabel(PublicFeatureCardDto card)
        => card.CtaKind switch
        {
            "login" => "Sign in",
            "signup" => "Create account",
            "external" => "Open external",
            _ when string.Equals(card.RenderMode, "external_explainer", StringComparison.OrdinalIgnoreCase) => "Open on chummer.run",
            _ => "Open"
        };

    private static string ToAnchorId(string value)
    {
        var normalized = new string(value
            .Trim()
            .ToLowerInvariant()
            .Select(ch => char.IsLetterOrDigit(ch) ? ch : '-')
            .ToArray());
        while (normalized.Contains("--", StringComparison.Ordinal))
        {
            normalized = normalized.Replace("--", "-", StringComparison.Ordinal);
        }

        return normalized.Trim('-');
    }

    private static string ShortChecksum(string value)
        => string.IsNullOrWhiteSpace(value) || value.Length <= 16
            ? value
            : $"{value[..8]}...{value[^8..]}";

    private static string FormatBytes(long sizeBytes)
    {
        string[] suffixes = ["B", "KB", "MB", "GB"];
        double value = sizeBytes;
        var order = 0;
        while (value >= 1024d && order < suffixes.Length - 1)
        {
            order++;
            value /= 1024d;
        }

        return $"{value:0.#} {suffixes[order]}";
    }

    private static string Encode(string value) => WebUtility.HtmlEncode(value);

    private static string EncodeHref(string value) => WebUtility.HtmlEncode(value);
}
