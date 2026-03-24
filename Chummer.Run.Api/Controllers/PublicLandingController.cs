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
    private readonly ILogger<PublicLandingController> _logger;

    public PublicLandingController(
        PublicLandingService landing,
        PublicReleaseManifestService releases,
        AccountService accounts,
        HubIdentityClient identity,
        IdentityLinkService links,
        UserExperienceService experience,
        HubPageChromeService chrome,
        ILogger<PublicLandingController> logger)
    {
        _landing = landing;
        _releases = releases;
        _accounts = accounts;
        _identity = identity;
        _links = links;
        _experience = experience;
        _chrome = chrome;
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
    public async Task<IActionResult> StatusPage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var model = new ShelfPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Status", "A compact public read on what is live and what still sits in horizon territory.", "/status", cancellationToken),
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            Eyebrow: "Status",
            Heading: "Public status",
            Intro: "This summary comes from the live public surface and stays focused on what people can actually use or inspect.",
            Items: _landing.CardsForBucket(surface, "whats_real_now"));
        return View("~/Views/PublicLanding/Shelf.cshtml", model);
    }

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
        var model = new TrustPageViewModel(
            Chrome: chrome,
            Eyebrow: "Help",
            Heading: "How to get help without guessing",
            Intro: "Chummer is still early access, but the support path should still feel boring: where to ask, what is public, what stays private, and when the bounded participation lane makes sense.",
            Sections: new[]
            {
                new TrustPageSectionViewModel(
                    "Public feedback lane",
                    "Start with public feedback",
                    "Use the public path when you want to report a bug, flag confusing copy, or point at a feature that would make the product more useful.",
                    new[]
                    {
                        "Report a bug or rough edge.",
                        "Flag confusing public copy or onboarding friction.",
                        "Suggest a future lane that would help your table.",
                        "Read status first when you are checking whether something is already known."
                    }),
                new TrustPageSectionViewModel(
                    "Booster lane",
                    "Use participation only when you want the deeper lane",
                    "Participation is the opt-in path for bounded contribution help. It is temporary, review-safe, and additive on top of the normal public feedback path.",
                    new[]
                    {
                        "Participation is optional.",
                        "It does not bypass review.",
                        "You can stop or revoke later.",
                        "Recognition only appears after validated work lands."
                    }),
                new TrustPageSectionViewModel(
                    "Privacy and review",
                    "Normal help should stay low-drama",
                    "Public help should not require a public identity, and contributing should not force you into leaderboards or badges if you prefer to stay quiet.",
                    new[]
                    {
                        "Public recognition stays opt-in.",
                        "Private participation remains valid even when recognition exists.",
                        "The free baseline remains the default path.",
                        "Status and help pages should explain what happened without forcing repo spelunking."
                    }),
                new TrustPageSectionViewModel(
                    "What opens later",
                    "Some expensive lanes may open by invite first",
                    "That is a cost and safety posture, not a promise to lock the interesting parts away forever. The long-run intent is wider access once the lane becomes boring enough to operate safely.",
                    null)
            },
            Actions: BuildTrustActions(authenticated: chrome.Authenticated));
        return View("~/Views/PublicLanding/TrustPage.cshtml", model);
    }

    [HttpGet("/faq")]
    [Produces("text/html")]
    public async Task<IActionResult> FaqPage(CancellationToken cancellationToken)
    {
        var model = new FaqPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("FAQ", "Plain answers about preview status, participation, privacy, and what is already usable.", "/faq", cancellationToken),
            Eyebrow: "FAQ",
            Heading: "Plain answers before you commit time",
            Intro: "The early-access pitch should still answer the normal questions directly: what is real, what is preview, how help works, and what deeper sources are for.",
            Sections: new[]
            {
                new FaqSectionViewModel(
                    "Using Chummer",
                    new[]
                    {
                        new FaqEntryViewModel("Can I actually use this now?", "Yes, with honest caveats. There are usable public surfaces and a real preview shelf, but several surfaces are still explicitly marked preview."),
                        new FaqEntryViewModel("Why would I trust it more than an opaque tool?", "Because the product is trying to make the number and the trail visible together: deterministic outcomes, readable receipts, and provenance instead of mystery math."),
                        new FaqEntryViewModel("What is preview versus available today?", "Available today means there is a real surface or build you can touch right now. Preview means the shape is usable but the support, release, or compatibility story is still moving.")
                    }),
                new FaqSectionViewModel(
                    "Participation and preview",
                    new[]
                    {
                        new FaqEntryViewModel("How can I help?", "Start with public feedback, bug reports, and feature suggestions. If you want to go further, the bounded participation lane exists as an opt-in path."),
                        new FaqEntryViewModel("Do I need to participate to help?", "No. The public feedback path remains the default path. Participation is optional and additive, not the price of admission."),
                        new FaqEntryViewModel("Can I participate privately?", "Yes. Recognition should remain opt-in, and private participation should still be possible even when badges or leaderboards exist."),
                        new FaqEntryViewModel("Will some previews become free later?", "That is the long-run intent. Some lanes may start tighter while approvals, provenance, compatibility, or support costs are still unusually heavy.")
                    }),
                new FaqSectionViewModel(
                    "Deeper sources",
                    new[]
                    {
                        new FaqEntryViewModel("Where does the deeper plan live?", "In the published product materials and linked source trail. The public front should help you decide whether Chummer is for you before you ever need the deeper implementation view."),
                        new FaqEntryViewModel("Where does the code live?", "In the owning source repos. This front door exists so normal users do not have to reverse-engineer the product story from commit archaeology.")
                    })
            },
            Actions: new[]
            {
                new TrustPageActionViewModel("See what works today", "/now", "primary"),
                new TrustPageActionViewModel("Open help", "/help", "secondary"),
                new TrustPageActionViewModel("Create account", "/signup?next=/home", "ghost")
            });
        return View("~/Views/PublicLanding/Faq.cshtml", model);
    }

    [HttpGet("/privacy")]
    [Produces("text/html")]
    public async Task<IActionResult> PrivacyPage(CancellationToken cancellationToken)
    {
        var model = new TrustPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Privacy", "What the account keeps, what stays out of it, and how recognition and privacy stay separate.", "/privacy", cancellationToken),
            Eyebrow: "Privacy",
            Heading: "What Chummer stores, and what it does not",
            Intro: "The product should be honest about data handling. This page explains the practical early-access posture in plain language.",
            Sections: new[]
            {
                new TrustPageSectionViewModel(
                    "Hosted account data",
                    "Hub keeps the account record and your product preferences",
                    "The account keeps your basic profile, linked sign-in methods, recovery posture, update preferences, and participation record so the public and signed-in surfaces can stay coherent.",
                    new[]
                    {
                        "Display name and handle.",
                        "Linked sign-in and recovery posture.",
                        "Update and beta-interest preferences.",
                        "Participation status, badge state, and contribution receipts."
                    }),
                new TrustPageSectionViewModel(
                    "What stays out of Hub",
                    "Temporary contribution auth material does not belong here",
                    "Contribution authorization material stays on the execution host. The account keeps consent, state, and receipts; it does not keep raw provider auth caches.",
                    new[]
                    {
                        "No raw ChatGPT auth cache in Hub.",
                        "No temporary one-time-code secret storage in Hub.",
                        "No provider-credit or provider-secret storage in Hub."
                    }),
                new TrustPageSectionViewModel(
                    "Recognition and privacy",
                    "Recognition should not force publicity",
                    "Badges and leaderboards are recognition layers, not an excuse to make participation public by default. Private participation and private recognition settings remain valid.",
                    null),
                new TrustPageSectionViewModel(
                    "Early-access reality",
                    "This is the current product posture",
                    "This is a practical privacy statement for the current hosted product surface. It is meant to explain the live behavior honestly while the fuller legal and release posture continues to mature.",
                    null)
            },
            Actions: new[]
            {
                new TrustPageActionViewModel("Open account", "/account", "primary"),
                new TrustPageActionViewModel("Read terms", "/terms", "secondary"),
                new TrustPageActionViewModel("Contact Chummer", "/contact", "ghost")
            });
        return View("~/Views/PublicLanding/TrustPage.cshtml", model);
    }

    [HttpGet("/terms")]
    [Produces("text/html")]
    public async Task<IActionResult> TermsPage(CancellationToken cancellationToken)
    {
        var model = new TrustPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Terms", "Preview-use expectations, support posture, and the boundaries of the current hosted promise.", "/terms", cancellationToken),
            Eyebrow: "Terms",
            Heading: "Preview terms in plain language",
            Intro: "This is not legal theater. It is the practical contract the hosted preview is trying to keep right now: what the product is promising, what may still move, and where support stops.",
            Sections: new[]
            {
                new TrustPageSectionViewModel(
                    "Preview posture",
                    "The product is real, but still early access",
                    "Chummer is trying to be usable and honest at the same time. Expect working surfaces, clear labels for preview lanes, and visible evidence when something is not fully settled yet.",
                    null),
                new TrustPageSectionViewModel(
                    "Account and participation",
                    "Accounts should be boring, participation should stay bounded",
                    "Normal sign-in should keep your access and preferences together. Participation remains opt-in, temporary, and review-safe. Authorization alone does not count as contribution credit.",
                    null),
                new TrustPageSectionViewModel(
                    "Downloads and updates",
                    "Installers are the preferred path when available",
                    "Installer builds are the product-default path. Manual archives remain available when needed, but they are the fallback path and should not be mistaken for the polished default experience.",
                    null),
                new TrustPageSectionViewModel(
                    "Support limits",
                    "Early access does not mean silent failure is acceptable",
                    "Support and legal posture are still maturing, but that is not a license for mystery behavior. The status, help, privacy, and contact pages should explain the current state in product language.",
                    null)
            },
            Actions: new[]
            {
                new TrustPageActionViewModel("Open downloads", "/downloads", "primary"),
                new TrustPageActionViewModel("Read privacy", "/privacy", "secondary"),
                new TrustPageActionViewModel("Open help", "/help", "ghost")
            });
        return View("~/Views/PublicLanding/TrustPage.cshtml", model);
    }

    [HttpGet("/contact")]
    [Produces("text/html")]
    public async Task<IActionResult> ContactPage(CancellationToken cancellationToken)
    {
        var model = new TrustPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Contact", "Where to send bugs, account questions, and public product feedback right now.", "/contact", cancellationToken),
            Eyebrow: "Contact",
            Heading: "Where to send the right kind of problem",
            Intro: "A polished product should not make you guess where to go. Chummer is still early access, so the contact path is structured before it is fully staffed.",
            Sections: new[]
            {
                new TrustPageSectionViewModel(
                    "Product bugs and rough edges",
                    "Use the public issue tracker for product feedback",
                    "If something is broken, confusing, or misleading on the public surface, use the public tracker. That keeps the problem visible and stops support from disappearing into side channels.",
                    null),
                new TrustPageSectionViewModel(
                    "Account and sign-in trouble",
                    "Start from the first-party account and help surfaces",
                    "Use the account page for sign-in, recovery, and channel issues, and use the help surface when you need the current support path explained in product language.",
                    null),
                new TrustPageSectionViewModel(
                    "Participation questions",
                    "Read the participation explainer before you open the deeper lane",
                    "The participation route should answer what the lane is for, what gets stored, and when recognition appears before you touch the wizard.",
                    null),
                new TrustPageSectionViewModel(
                    "Status first",
                    "Check status when a failure looks systemic",
                    "If sign-in, downloads, or participation start failing across the board, check status first so you can tell the difference between an account issue and a host issue.",
                    null)
            },
            Actions: new[]
            {
                new TrustPageActionViewModel("Open public issue tracker", "https://github.com/ArchonMegalon/Chummer6/issues", "primary"),
                new TrustPageActionViewModel("Open help", "/help", "secondary"),
                new TrustPageActionViewModel("Check status", "/status", "ghost")
            });
        return View("~/Views/PublicLanding/TrustPage.cshtml", model);
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

    private static IReadOnlyList<TrustPageActionViewModel> BuildTrustActions(bool authenticated)
        => authenticated
            ? new[]
            {
                new TrustPageActionViewModel("Open home", "/home", "primary"),
                new TrustPageActionViewModel("Open participate", "/participate", "secondary"),
                new TrustPageActionViewModel("Open account", "/account", "ghost")
            }
            : new[]
            {
                new TrustPageActionViewModel("Create account", "/signup?next=/home", "primary"),
                new TrustPageActionViewModel("See what works today", "/now", "secondary"),
                new TrustPageActionViewModel("Open participate", "/participate", "ghost")
            };
}
