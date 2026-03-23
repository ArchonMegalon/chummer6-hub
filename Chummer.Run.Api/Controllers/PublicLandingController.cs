using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/public")]
public sealed class PublicLandingController : Controller
{
    private readonly PublicLandingService _landing;
    private readonly PublicReleaseManifestService _releases;
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;
    private readonly IdentityLinkService _links;
    private readonly UserExperienceService _experience;
    private readonly HubPageChromeService _chrome;

    public PublicLandingController(
        PublicLandingService landing,
        PublicReleaseManifestService releases,
        AccountService accounts,
        HubIdentityClient identity,
        IdentityLinkService links,
        UserExperienceService experience,
        HubPageChromeService chrome)
    {
        _landing = landing;
        _releases = releases;
        _accounts = accounts;
        _identity = identity;
        _links = links;
        _experience = experience;
        _chrome = chrome;
    }

    [HttpGet("/")]
    [Produces("text/html")]
    public IActionResult LandingPage()
    {
        var surface = _landing.LoadSurface();
        var model = new LandingPageViewModel(
            Chrome: _chrome.BuildPublicChrome("Chummer", surface.Subhead, "/"),
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            StartHere: _landing.CardsForBucket(surface, "start_here"),
            TrustPillars: _landing.CardsForBucket(surface, "why_trust_it"),
            Lanes: _landing.CardsForBucket(surface, "choose_your_lane"));
        return View("~/Views/PublicLanding/Landing.cshtml", model);
    }

    [HttpGet("/what-is-chummer")]
    [Produces("text/html")]
    public IActionResult ProductStoryPage()
    {
        var surface = _landing.LoadSurface();
        var model = new StoryPageViewModel(
            Chrome: _chrome.BuildPublicChrome("What Is Chummer?", surface.ProofLine, "/what-is-chummer"),
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            TrustPillars: _landing.CardsForBucket(surface, "why_trust_it"),
            Lanes: _landing.CardsForBucket(surface, "choose_your_lane"));
        return View("~/Views/PublicLanding/ProductStory.cshtml", model);
    }

    [HttpGet("/now")]
    [Produces("text/html")]
    public IActionResult NowPage()
    {
        var surface = _landing.LoadSurface();
        var nowCards = _landing.CardsForBucket(surface, "whats_real_now");
        var model = new NowPageViewModel(
            Chrome: _chrome.BuildPublicChrome("What Is Real Now", "A public proof shelf with readiness labels and direct evidence.", "/now"),
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            AvailableToday: nowCards.Where(static card => string.Equals(card.Badge, "Live now", StringComparison.OrdinalIgnoreCase)).ToArray(),
            Inspectable: nowCards.Where(static card => !string.Equals(card.Badge, "Live now", StringComparison.OrdinalIgnoreCase)).ToArray(),
            SignedInPreview: surface.RegisteredOverlays,
            Manifest: _releases.LoadManifest());
        return View("~/Views/PublicLanding/Now.cshtml", model);
    }

    [HttpGet("/horizons")]
    [Produces("text/html")]
    public IActionResult HorizonsPage()
    {
        var surface = _landing.LoadSurface();
        var model = new HorizonsPageViewModel(
            Chrome: _chrome.BuildPublicChrome("Coming Next", "The named horizons, their pain, and the payoff they are aiming for.", "/horizons"),
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            Horizons: _landing.CardsForBucket(surface, "coming_next"));
        return View("~/Views/PublicLanding/Horizons.cshtml", model);
    }

    [HttpGet("/downloads")]
    [Produces("text/html")]
    public IActionResult DownloadsPage()
    {
        var surface = _landing.LoadSurface();
        var model = new DownloadsPageViewModel(
            Chrome: _chrome.BuildPublicChrome("Downloads", "The live release shelf, integrity row, and direct artifact downloads.", "/downloads"),
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            Manifest: _releases.LoadManifest());
        return View("~/Views/PublicLanding/Downloads.cshtml", model);
    }

    [HttpGet("/participate")]
    [Produces("text/html")]
    public IActionResult ParticipatePage()
    {
        var surface = _landing.LoadSurface();
        var cards = _landing.CardsForBucket(surface, "participate");
        var model = new ParticipatePageViewModel(
            Chrome: _chrome.BuildPublicChrome("Participate", "Two clean lanes: public feedback and an optional signed-in booster path.", "/participate"),
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            PublicLane: cards.Where(card => !string.Equals(card.Id, "participate_booster", StringComparison.Ordinal) && !string.Equals(card.Id, "participate_beta", StringComparison.Ordinal)).ToArray(),
            SignedInLane: cards.Where(card => string.Equals(card.Id, "participate_booster", StringComparison.Ordinal) || string.Equals(card.Id, "participate_beta", StringComparison.Ordinal)).ToArray());
        return View("~/Views/PublicLanding/Participate.cshtml", model);
    }

    [HttpGet("/status")]
    [Produces("text/html")]
    public IActionResult StatusPage()
    {
        var surface = _landing.LoadSurface();
        var model = new ShelfPageViewModel(
            Chrome: _chrome.BuildPublicChrome("Status", "A compact public read on what is live and what still sits in horizon territory.", "/status"),
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            Eyebrow: "Status",
            Heading: "Public status",
            Intro: "This summary is derived from the design mirror and the live proof shelf, not from internal operator dashboards.",
            Items: _landing.CardsForBucket(surface, "whats_real_now"));
        return View("~/Views/PublicLanding/Shelf.cshtml", model);
    }

    [HttpGet("/artifacts")]
    [Produces("text/html")]
    public IActionResult ArtifactsPage()
    {
        var surface = _landing.LoadSurface();
        var model = new ShelfPageViewModel(
            Chrome: _chrome.BuildPublicChrome("Artifacts", "A secondary teaser shelf for artifacts and future outputs.", "/artifacts"),
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            Eyebrow: "Artifacts",
            Heading: "Artifact shelf",
            Intro: "Artifact teasers stay secondary. They point to the related horizon instead of trying to become the front door.",
            Items: _landing.CardsForBucket(surface, "featured_artifacts"));
        return View("~/Views/PublicLanding/Shelf.cshtml", model);
    }

    [HttpGet("/home")]
    [Produces("text/html")]
    public async Task<IActionResult> HomePage(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var surface = _landing.LoadSurface();
            var model = new HomePageViewModel(
                Chrome: _chrome.BuildAuthenticatedChrome("Home", "Pick the next action and keep track of what is opening next.", "/home", user.DisplayName),
                Surface: surface,
                Assets: new AssetCatalogViewModel(surface.Assets),
                User: user,
                Links: _links.GetSummary(subject.SubjectId),
                Experience: _experience.GetOrCreate(subject.SubjectId),
                NowRail: _landing.CardsForBucket(surface, "whats_real_now").Take(3).ToArray(),
                HorizonRail: _landing.CardsForBucket(surface, "coming_next").Take(3).ToArray());
            return View("~/Views/PublicLanding/Home.cshtml", model);
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
}
