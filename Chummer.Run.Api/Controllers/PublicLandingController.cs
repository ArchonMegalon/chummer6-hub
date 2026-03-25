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
    private readonly PublicTrustContentService _trustContent;
    private readonly ILogger<PublicLandingController> _logger;

    public PublicLandingController(
        PublicLandingService landing,
        PublicReleaseManifestService releases,
        AccountService accounts,
        HubIdentityClient identity,
        IdentityLinkService links,
        UserExperienceService experience,
        HubPageChromeService chrome,
        PublicTrustContentService trustContent,
        ILogger<PublicLandingController> logger)
    {
        _landing = landing;
        _releases = releases;
        _accounts = accounts;
        _identity = identity;
        _links = links;
        _experience = experience;
        _chrome = chrome;
        _trustContent = trustContent;
        _logger = logger;
    }

    [HttpGet("/")]
    [Produces("text/html")]
    public async Task<IActionResult> LandingPage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var manifest = _releases.LoadManifest();
        var hasPreviewBuild = manifest.Downloads.Count > 0;
        var nowCards = _landing.CardsForBucket(surface, "whats_real_now");
        var model = new LandingPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Chummer", surface.Subhead, "/", cancellationToken),
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            Manifest: manifest,
            PrimaryHeroAction: new PublicLandingActionDto(
                hasPreviewBuild ? "Get preview build" : "Request early access",
                hasPreviewBuild ? "/downloads" : "/signup?next=/home",
                "primary"),
            SecondaryHeroAction: new PublicLandingActionDto("See what works today", "/now", "secondary"),
            Workflows: _landing.CardsForBucket(surface, "start_here"),
            TrustPillars: _landing.CardsForBucket(surface, "why_trust_it"),
            Lanes: _landing.CardsForBucket(surface, "choose_your_lane"),
            AvailableToday: nowCards.Where(static card => string.Equals(card.Badge, "Live now", StringComparison.OrdinalIgnoreCase)).ToArray(),
            PreviewItems: nowCards.Where(static card => !string.Equals(card.Badge, "Live now", StringComparison.OrdinalIgnoreCase)).ToArray(),
            ComingNext: _landing.CardsForBucket(surface, "coming_next").Take(3).ToArray(),
            Artifacts: _landing.CardsForBucket(surface, "featured_artifacts"));
        return View("~/Views/PublicLanding/Landing.cshtml", model);
    }

    [HttpGet("/what-is-chummer")]
    [Produces("text/html")]
    public async Task<IActionResult> ProductStoryPage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var model = new StoryPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("What Is Chummer?", surface.ProofLine, "/what-is-chummer", cancellationToken),
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            TrustPillars: _landing.CardsForBucket(surface, "why_trust_it"),
            Lanes: _landing.CardsForBucket(surface, "choose_your_lane"));
        return View("~/Views/PublicLanding/ProductStory.cshtml", model);
    }

    [HttpGet("/now")]
    [Produces("text/html")]
    public async Task<IActionResult> NowPage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var nowCards = _landing.CardsForBucket(surface, "whats_real_now");
        var model = new NowPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("What Is Real Now", "Readiness labels and direct evidence for what you can use today.", "/now", cancellationToken),
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
    public async Task<IActionResult> HorizonsPage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var model = new HorizonsPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Coming Next", "The named horizons, their pain, and the payoff they are aiming for.", "/horizons", cancellationToken),
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            Horizons: _landing.CardsForBucket(surface, "coming_next"));
        return View("~/Views/PublicLanding/Horizons.cshtml", model);
    }

    [HttpGet("/downloads")]
    [Produces("text/html")]
    public async Task<IActionResult> DownloadsPage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var model = new DownloadsPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Downloads", "Install the current preview, compare package types, and keep release integrity in view.", "/downloads", cancellationToken),
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            Manifest: _releases.LoadManifest());
        return View("~/Views/PublicLanding/Downloads.cshtml", model);
    }

    [HttpGet("/participate")]
    [Produces("text/html")]
    public async Task<IActionResult> ParticipatePage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var cards = _landing.CardsForBucket(surface, "participate");
        var model = new ParticipatePageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Participate", "Two clean lanes: public feedback and an optional signed-in guided contribution path.", "/participate", cancellationToken),
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            PublicLane: cards.Where(card => !string.Equals(card.Id, "participate_booster", StringComparison.Ordinal) && !string.Equals(card.Id, "participate_beta", StringComparison.Ordinal)).ToArray(),
            SignedInLane: cards.Where(card => string.Equals(card.Id, "participate_booster", StringComparison.Ordinal) || string.Equals(card.Id, "participate_beta", StringComparison.Ordinal)).ToArray());
        return View("~/Views/PublicLanding/Participate.cshtml", model);
    }

    [HttpGet("/status")]
    [Produces("text/html")]
    public IActionResult StatusPage() => Redirect("/now");

    [HttpGet("/artifacts")]
    [Produces("text/html")]
    public async Task<IActionResult> ArtifactsPage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var model = new ShelfPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Artifacts", "Proof surfaces, briefs, and grounded outputs connected to the current preview.", "/artifacts", cancellationToken),
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            Eyebrow: "Artifacts",
            Heading: "Proof gallery",
            Intro: "Browse the packs, briefs, and proof surfaces that make the preview feel tangible.",
            Items: _landing.CardsForBucket(surface, "featured_artifacts"));
        return View("~/Views/PublicLanding/Shelf.cshtml", model);
    }

    [HttpGet("/help")]
    [Produces("text/html")]
    public async Task<IActionResult> HelpPage(CancellationToken cancellationToken)
    {
        var chrome = await BuildPublicOrAuthenticatedChromeAsync("Help", "How to get help, what participation means, and where to go when something goes wrong.", "/help", cancellationToken);
        return View("~/Views/PublicLanding/TrustPage.cshtml", _trustContent.BuildHelpPage(chrome));
    }

    [HttpGet("/faq")]
    [Produces("text/html")]
    public async Task<IActionResult> FaqPage(CancellationToken cancellationToken)
    {
        var chrome = await BuildPublicOrAuthenticatedChromeAsync("FAQ", "Plain answers about preview status, participation, privacy, and what is already usable.", "/faq", cancellationToken);
        return View("~/Views/PublicLanding/Faq.cshtml", _trustContent.BuildFaqPage(chrome));
    }

    [HttpGet("/privacy")]
    [Produces("text/html")]
    public async Task<IActionResult> PrivacyPage(CancellationToken cancellationToken)
    {
        var chrome = await BuildPublicOrAuthenticatedChromeAsync("Privacy", "What the account keeps, what stays out of it, and how recognition and privacy stay separate.", "/privacy", cancellationToken);
        return View("~/Views/PublicLanding/TrustPage.cshtml", _trustContent.BuildPrivacyPage(chrome));
    }

    [HttpGet("/terms")]
    [Produces("text/html")]
    public async Task<IActionResult> TermsPage(CancellationToken cancellationToken)
    {
        var chrome = await BuildPublicOrAuthenticatedChromeAsync("Terms", "Preview-use expectations, support posture, and the boundaries of the current hosted promise.", "/terms", cancellationToken);
        return View("~/Views/PublicLanding/TrustPage.cshtml", _trustContent.BuildTermsPage(chrome));
    }

    [HttpGet("/contact")]
    [Produces("text/html")]
    public async Task<IActionResult> ContactPage(CancellationToken cancellationToken)
    {
        var chrome = await BuildPublicOrAuthenticatedChromeAsync("Contact", "Where to send bugs, account questions, and public product feedback right now.", "/contact", cancellationToken);
        return View("~/Views/PublicLanding/TrustPage.cshtml", _trustContent.BuildContactPage(chrome));
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
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect("/login?next=/home");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Home page could not confirm the signed-in identity.");
            return View("~/Views/Auth/Message.cshtml", new AuthMessagePageViewModel(
                Chrome: _chrome.BuildPublicChrome("Home unavailable", "Hub could not confirm the signed-in home surface right now.", "/home"),
                Heading: "Home is unavailable right now",
                SupportLine: "Chummer could not open the signed-in home surface right now. Your session may still be valid, so try again in a moment.",
                Notice: null,
                PrimaryLabel: "Try home again",
                PrimaryHref: "/home",
                SecondaryLabel: "Return to landing",
                SecondaryHref: "/"));
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

    private async Task<SiteChromeViewModel> BuildPublicOrAuthenticatedChromeAsync(
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
            _logger.LogWarning(ex, "Preserving signed-in chrome after identity failure for {Path}.", currentPath);
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
            _logger.LogWarning(ex, "Falling back while building public chrome for {Path}.", currentPath);
            if (Request.Cookies.ContainsKey(HubBrowserAuthConstants.AccessTokenCookieName))
            {
                return _chrome.BuildAuthenticatedChrome(title, description, currentPath, "Signed in");
            }

            return _chrome.BuildPublicChrome(title, description, currentPath);
        }
    }
}
