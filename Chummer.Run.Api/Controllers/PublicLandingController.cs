using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;
using Chummer.Control.Contracts.Support;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/public")]
public sealed class PublicLandingController : Controller
{
    private readonly PublicLandingService _landing;
    private readonly PublicReleaseManifestService _releases;
    private readonly ReleaseSelectionService _releaseSelection;
    private readonly PublicActionResolver _actions;
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;
    private readonly IdentityLinkService _links;
    private readonly UserExperienceService _experience;
    private readonly InstallLinkingService _installLinking;
    private readonly HubPageChromeService _chrome;
    private readonly PublicTrustContentService _trustContent;
    private readonly SupportCaseService _supportCases;
    private readonly ILogger<PublicLandingController> _logger;

    public PublicLandingController(
        PublicLandingService landing,
        PublicReleaseManifestService releases,
        ReleaseSelectionService releaseSelection,
        PublicActionResolver actions,
        AccountService accounts,
        HubIdentityClient identity,
        IdentityLinkService links,
        UserExperienceService experience,
        InstallLinkingService installLinking,
        HubPageChromeService chrome,
        PublicTrustContentService trustContent,
        SupportCaseService supportCases,
        ILogger<PublicLandingController> logger)
    {
        _landing = landing;
        _releases = releases;
        _releaseSelection = releaseSelection;
        _actions = actions;
        _accounts = accounts;
        _identity = identity;
        _links = links;
        _experience = experience;
        _installLinking = installLinking;
        _chrome = chrome;
        _trustContent = trustContent;
        _supportCases = supportCases;
        _logger = logger;
    }

    [HttpGet("/")]
    [Produces("text/html")]
    public async Task<IActionResult> LandingPage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var authenticated = await TryIsAuthenticatedAsync(cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        var assetCatalog = new AssetCatalogViewModel(surface.Assets);
        var nowCards = _landing.CardsForBucket(surface, "whats_real_now");
        var secondaryHeroAction = surface.HeroCtas.FirstOrDefault(static action => string.Equals(action.Emphasis, "secondary", StringComparison.OrdinalIgnoreCase))
            ?? surface.HeroCtas.Skip(1).FirstOrDefault()
            ?? new PublicLandingActionDto("See what works today", "/now", "secondary");
        var model = new LandingPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Chummer", surface.Subhead, "/", cancellationToken),
            Surface: surface,
            Assets: assetCatalog,
            Manifest: manifest,
            ReleaseExperience: releaseExperience,
            PrimaryHeroAction: _releaseSelection.BuildPublicPrimaryAction(manifest, authenticated),
            SecondaryHeroAction: secondaryHeroAction,
            Workflows: ResolveCards(_landing.CardsForBucket(surface, "start_here"), assetCatalog, authenticated: false, "/"),
            TrustPillars: _landing.CardsForBucket(surface, "why_trust_it"),
            Lanes: ResolveCards(_landing.CardsForBucket(surface, "choose_your_lane"), assetCatalog, authenticated: false, "/"),
            AvailableToday: ResolveCards(nowCards.Where(static card => string.Equals(card.Badge, "Live now", StringComparison.OrdinalIgnoreCase)).ToArray(), assetCatalog, authenticated: false, "/"),
            PreviewItems: ResolveCards(nowCards.Where(static card => !string.Equals(card.Badge, "Live now", StringComparison.OrdinalIgnoreCase)).ToArray(), assetCatalog, authenticated: false, "/"),
            ComingNext: ResolveCards(_landing.CardsForBucket(surface, "coming_next").Take(3).ToArray(), assetCatalog, authenticated: false, "/"),
            Artifacts: ResolveCards(_landing.CardsForBucket(surface, "featured_artifacts"), assetCatalog, authenticated: false, "/"));
        return View("~/Views/PublicLanding/Landing.cshtml", model);
    }

    [HttpGet("/what-is-chummer")]
    [Produces("text/html")]
    public async Task<IActionResult> ProductStoryPage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var assetCatalog = new AssetCatalogViewModel(surface.Assets);
        var model = new StoryPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("What Is Chummer?", surface.ProofLine, "/what-is-chummer", cancellationToken),
            Surface: surface,
            Assets: assetCatalog,
            Workflows: ResolveCards(_landing.CardsForBucket(surface, "start_here"), assetCatalog, authenticated: false, "/what-is-chummer"),
            TrustPillars: _landing.CardsForBucket(surface, "why_trust_it"),
            Lanes: ResolveCards(_landing.CardsForBucket(surface, "choose_your_lane"), assetCatalog, authenticated: false, "/what-is-chummer"));
        return View("~/Views/PublicLanding/ProductStory.cshtml", model);
    }

    [HttpGet("/now")]
    [Produces("text/html")]
    public async Task<IActionResult> NowPage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var assetCatalog = new AssetCatalogViewModel(surface.Assets);
        var nowCards = _landing.CardsForBucket(surface, "whats_real_now");
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var authenticated = await TryIsAuthenticatedAsync(cancellationToken);
        var model = new NowPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("What Is Real Now", "Readiness labels and direct evidence for what you can use today.", "/now", cancellationToken),
            Surface: surface,
            Assets: assetCatalog,
            ReleaseExperience: _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated),
            ProofModules: ResolveCards(_landing.CardsForBucket(surface, "start_here").Take(3).ToArray(), assetCatalog, authenticated: false, "/now"),
            AvailableToday: ResolveCards(nowCards.Where(static card => string.Equals(card.Badge, "Live now", StringComparison.OrdinalIgnoreCase)).ToArray(), assetCatalog, authenticated: false, "/now"),
            Inspectable: ResolveCards(nowCards.Where(static card => !string.Equals(card.Badge, "Live now", StringComparison.OrdinalIgnoreCase)).ToArray(), assetCatalog, authenticated: false, "/now"),
            SignedInPreview: surface.RegisteredOverlays,
            Manifest: manifest);
        return View("~/Views/PublicLanding/Now.cshtml", model);
    }

    [HttpGet("/horizons")]
    [Produces("text/html")]
    public async Task<IActionResult> HorizonsPage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var assetCatalog = new AssetCatalogViewModel(surface.Assets);
        var model = new HorizonsPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Coming Next", "The named horizons, their pain, and the payoff they are aiming for.", "/horizons", cancellationToken),
            Surface: surface,
            Assets: assetCatalog,
            Horizons: ResolveCards(_landing.CardsForBucket(surface, "coming_next"), assetCatalog, authenticated: false, "/horizons"));
        return View("~/Views/PublicLanding/Horizons.cshtml", model);
    }

    [HttpGet("/downloads")]
    [Produces("text/html")]
    public async Task<IActionResult> DownloadsPage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var authenticated = await TryIsAuthenticatedAsync(cancellationToken);
        var model = new DownloadsPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Downloads", "Install the current preview, compare package types, and keep release integrity in view.", "/downloads", cancellationToken),
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            Manifest: manifest,
            ReleaseExperience: _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated));
        return View("~/Views/PublicLanding/Downloads.cshtml", model);
    }

    [HttpGet("/downloads/install/{artifactId}")]
    [Produces("text/html")]
    public async Task<IActionResult> DownloadDispatchPage([FromRoute] string artifactId, CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var artifact = manifest.Downloads.FirstOrDefault(item => string.Equals(item.Id, artifactId, StringComparison.OrdinalIgnoreCase));
        if (artifact is null)
        {
            return NotFound();
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var dispatch = _installLinking.IssueDownload(manifest, artifact, user.UserId, subject.SubjectId);
            var release = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated: true);
            var option = _releaseSelection.BuildOption(manifest, artifact, authenticated: true, recommended: false);
            var model = new DownloadDispatchPageViewModel(
                Chrome: _chrome.BuildAuthenticatedChrome("Download handoff", "Start the installer download and keep the install linked to this account from the first launch.", "/downloads", user.DisplayName),
                Heading: release.SignedInDispatchHeading,
                Summary: release.SignedInDispatchSummary,
                ArtifactTitle: option.Title,
                ArtifactSupportLine: option.SupportLine,
                DownloadHref: option.DirectFileHref,
                DownloadLabel: "Start download again",
                AccountHref: "/account#devices-access",
                AccountLabel: "Open Devices and access",
                HelpHref: release.InstallHelpHref,
                HelpLabel: release.InstallHelpLabel,
                Display: release.Display,
                Channel: manifest.Channel,
                Version: manifest.Version,
                PlatformLabel: option.PlatformLabel,
                HeadLabel: option.HeadLabel,
                ClaimCode: dispatch.ClaimTicket?.ClaimCode,
                ClaimCodeExpiresAtUtc: dispatch.ClaimTicket?.ExpiresAtUtc,
                Steps: release.SignedInDispatchSteps);
            return View("~/Views/PublicLanding/DownloadDispatch.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString($"/downloads/install/{artifactId}")}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Downloads handoff could not confirm the signed-in identity.");
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
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
            PublicLane: ResolveCards(cards.Where(card => !string.Equals(card.Id, "participate_booster", StringComparison.Ordinal) && !string.Equals(card.Id, "participate_beta", StringComparison.Ordinal)).ToArray(), new AssetCatalogViewModel(surface.Assets), authenticated: false, "/participate"),
            SignedInLane: ResolveCards(cards.Where(card => string.Equals(card.Id, "participate_booster", StringComparison.Ordinal) || string.Equals(card.Id, "participate_beta", StringComparison.Ordinal)).ToArray(), new AssetCatalogViewModel(surface.Assets), authenticated: true, "/participate"));
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
        var assetCatalog = new AssetCatalogViewModel(surface.Assets);
        var model = new ShelfPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Artifacts", "Proof surfaces, briefs, and grounded outputs connected to the current preview.", "/artifacts", cancellationToken),
            Surface: surface,
            Assets: assetCatalog,
            Eyebrow: "Artifacts",
            Heading: "Proof gallery",
            Intro: "Browse the packs, briefs, and proof surfaces that make the preview feel tangible.",
            Items: ResolveCards(_landing.CardsForBucket(surface, "featured_artifacts"), assetCatalog, authenticated: false, "/artifacts"));
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
        return View("~/Views/PublicLanding/TrustPage.cshtml", BuildContactPageModel(chrome));
    }

    [HttpPost("/contact")]
    [ValidateAntiForgeryToken]
    [Consumes("application/x-www-form-urlencoded")]
    [Produces("text/html")]
    public async Task<IActionResult> SubmitContactCase(
        [FromForm] string? kind,
        [FromForm] string? title,
        [FromForm] string? summary,
        [FromForm] string? detail,
        CancellationToken cancellationToken)
    {
        var request = new SupportCaseSubmitRequest(
            Kind: kind ?? string.Empty,
            Title: title ?? string.Empty,
            Summary: summary ?? string.Empty,
            Detail: detail ?? string.Empty,
            Source: SupportCaseSourceKinds.PublicWeb);

        try
        {
            var subject = await TryGetOptionalSubjectAsync(cancellationToken);
            var user = subject is null ? null : _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var created = _supportCases.Submit(user?.UserId, subject?.SubjectId, request);
            TempData["ContactSubmittedCaseId"] = created.CaseId;
            return Redirect("/contact#support-intake");
        }
        catch (ArgumentException ex)
        {
            var chrome = await BuildPublicOrAuthenticatedChromeAsync("Contact", "Where to send bugs, account questions, and public product feedback right now.", "/contact", cancellationToken);
            var model = BuildContactPageModel(chrome) with
            {
                SupportIntake = BuildSupportIntakeModel(
                    authenticated: chrome.Authenticated,
                    submissionNotice: ex.Message)
            };
            return View("~/Views/PublicLanding/TrustPage.cshtml", model);
        }
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
            var assetCatalog = new AssetCatalogViewModel(surface.Assets);
            var links = _links.GetSummary(subject.SubjectId);
            var experience = _experience.GetOrCreate(subject.SubjectId);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var model = new HomePageViewModel(
                Chrome: _chrome.BuildAuthenticatedChrome("Home", "Pick the next action and keep track of what is opening next.", "/home", user.DisplayName),
                Surface: surface,
                Assets: assetCatalog,
                User: user,
                Links: links,
                Experience: experience,
                InstallLinking: installLinking,
                PrimaryAction: BuildHomePrimaryAction(experience, installLinking),
                NowRail: ResolveCards(_landing.CardsForBucket(surface, "whats_real_now").Take(3).ToArray(), assetCatalog, authenticated: true, "/home"),
                HorizonRail: ResolveCards(_landing.CardsForBucket(surface, "coming_next").Take(3).ToArray(), assetCatalog, authenticated: true, "/home"));
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

    [HttpGet("/artifacts/{slug}")]
    [Produces("text/html")]
    public async Task<IActionResult> ArtifactDetailPage([FromRoute] string slug, CancellationToken cancellationToken)
    {
        var currentPath = $"/artifacts/{slug}";
        return await BuildFeatureDetailPageAsync(
            currentPath,
            chromeTitle: "Artifact detail",
            chromeDescription: "A grounded artifact detail page with current status, payoff, and the next truthful action.",
            eyebrow: "Artifact detail",
            cancellationToken);
    }

    [HttpGet("/roadmap/{slug}")]
    [Produces("text/html")]
    public async Task<IActionResult> RoadmapDetailPage([FromRoute] string slug, CancellationToken cancellationToken)
    {
        var currentPath = $"/roadmap/{slug}";
        return await BuildFeatureDetailPageAsync(
            currentPath,
            chromeTitle: "Roadmap detail",
            chromeDescription: "A horizon detail page with the pain, payoff, and the next place to read deeper.",
            eyebrow: "Roadmap detail",
            cancellationToken);
    }

    private IReadOnlyList<ResolvedPublicCardViewModel> ResolveCards(
        IReadOnlyList<PublicFeatureCardDto> cards,
        AssetCatalogViewModel assets,
        bool authenticated,
        string currentPath)
        => cards.Select(card => new ResolvedPublicCardViewModel(
                Card: card,
                Asset: assets.ForCard(card),
                Action: _actions.ResolveFeatureAction(card, authenticated, currentPath)))
            .ToArray();

    private static HomePrimaryActionViewModel BuildHomePrimaryAction(HubUserExperienceDto experience, InstallLinkingSummaryDto installLinking)
    {
        if (!experience.OnboardingCompleted)
        {
            return new HomePrimaryActionViewModel(
                "Setup",
                "Finish setup",
                "Complete the short setup flow so Chummer can recover your account, route updates, and keep the signed-in shell calm.",
                "Complete setup",
                "#setup-sheet",
                "primary");
        }

        if ((installLinking.ClaimedInstallations?.Count ?? 0) == 0 && installLinking.RecentReceipts.Count == 0 && installLinking.PendingClaimTickets.Count == 0)
        {
            return new HomePrimaryActionViewModel(
                "Install",
                "Get the preview build",
                "Start with the recommended installer, then come back here when you want to link the installed copy to this account.",
                "Open downloads",
                "/downloads",
                "primary");
        }

        if ((installLinking.ClaimedInstallations?.Count ?? 0) == 0 && installLinking.PendingClaimTickets.Count > 0)
        {
            return new HomePrimaryActionViewModel(
                "Devices & access",
                "Link this copy",
                "You already have a signed-in download handoff. Open Devices and access to claim the install instead of starting over.",
                "Open account",
                "/account#devices-access",
                "primary");
        }

        return new HomePrimaryActionViewModel(
            "Current release",
            "Stay on the current preview",
            "Check the current release posture, your linked devices, and what changed before you spend attention on optional contribution work.",
            "See what works today",
            "/now",
            "primary");
    }

    private async Task<bool> TryIsAuthenticatedAsync(CancellationToken cancellationToken)
    {
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
            return true;
        }
        catch
        {
            return false;
        }
    }

    private async Task<AuthenticatedHubSubject?> TryGetOptionalSubjectAsync(CancellationToken cancellationToken)
    {
        try
        {
            return await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return null;
        }
    }

    private TrustPageViewModel BuildContactPageModel(SiteChromeViewModel chrome)
    {
        var submittedCaseId = TempData["ContactSubmittedCaseId"] as string;
        return _trustContent.BuildContactPage(chrome) with
        {
            SupportIntake = BuildSupportIntakeModel(
                authenticated: chrome.Authenticated,
                submissionNotice: string.IsNullOrWhiteSpace(submittedCaseId)
                    ? null
                    : $"Support case {submittedCaseId} was accepted. Create an account or use Account > Support if you want tracked follow-up in the product shell.")
        };
    }

    private static SupportIntakeViewModel BuildSupportIntakeModel(bool authenticated, string? submissionNotice)
        => new(
            ActionHref: "/contact",
            Heading: "Open a first-party support case",
            Intro: authenticated
                ? "Use the form for a quick report here, or open Account > Support when you want the full tracked case view."
                : "Use the first-party intake here when you want help without a GitHub account. Create an account later if you want tracked follow-up inside Chummer.",
            Authenticated: authenticated,
            AccountSupportHref: authenticated ? "/account#support" : "/signup?next=%2Faccount%23support",
            AccountSupportLabel: authenticated ? "Open tracked support" : "Create account for tracked support",
            SubmissionNotice: submissionNotice,
            Options:
            [
                new SupportIntakeOptionViewModel(SupportCaseKinds.InstallHelp, "Install or update", "Choose this when the installer, updater, or download handoff is the problem."),
                new SupportIntakeOptionViewModel(SupportCaseKinds.BugReport, "Product bug", "Use this for broken behavior, bad routing, or product regressions."),
                new SupportIntakeOptionViewModel(SupportCaseKinds.Feedback, "Feature request or UX feedback", "Use this when the product direction is right but the current surface is getting in your way.")
            ]);

    private async Task<IActionResult> BuildFeatureDetailPageAsync(
        string currentPath,
        string chromeTitle,
        string chromeDescription,
        string eyebrow,
        CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var card = _landing.FindCardByDetailRoute(surface, currentPath);
        if (card is null)
        {
            return NotFound();
        }

        var subject = await TryGetOptionalSubjectAsync(cancellationToken);
        var authenticated = subject is not null;
        if (subject is not null)
        {
            _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        }

        var chrome = await BuildPublicOrAuthenticatedChromeAsync(chromeTitle, chromeDescription, currentPath, cancellationToken);
        var assets = new AssetCatalogViewModel(surface.Assets);
        var primaryAction = _actions.ResolvePrimaryExperienceAction(card, authenticated, currentPath);
        TrustPageActionViewModel? secondaryAction = null;
        if (!string.IsNullOrWhiteSpace(card.FallbackRoute))
        {
            secondaryAction = new TrustPageActionViewModel(
                card.FallbackLabel ?? "Read the deeper brief",
                card.FallbackRoute!,
                "ghost");
        }

        var proofNote = BuildFeatureDetailProofNote(card);
        var payoff = BuildFeatureDetailPayoff(card);
        var facts = BuildFeatureDetailFacts(card, proofNote, payoff);
        var model = new FeatureDetailPageViewModel(
            Chrome: chrome,
            Eyebrow: eyebrow,
            Heading: card.Title,
            Intro: card.Summary,
            StatusLabel: card.Badge,
            Asset: assets.ForCard(card),
            PrimaryAction: primaryAction,
            SecondaryAction: secondaryAction,
            Facts: facts,
            Pain: card.Pain,
            Payoff: payoff,
            ProofNote: proofNote,
            MicroProof: BuildFeatureDetailMicroProof(card));
        return View("~/Views/PublicLanding/FeatureDetail.cshtml", model);
    }

    private static IReadOnlyList<FeatureDetailFactViewModel> BuildFeatureDetailFacts(PublicFeatureCardDto card, string? proofNote, string? payoff)
    {
        var facts = new List<FeatureDetailFactViewModel>
        {
            new("Current status", $"{card.Badge}. {card.Summary}")
        };

        if (!string.IsNullOrWhiteSpace(card.Pain))
        {
            facts.Add(new FeatureDetailFactViewModel("Why it matters", card.Pain));
        }

        if (!string.IsNullOrWhiteSpace(payoff))
        {
            facts.Add(new FeatureDetailFactViewModel("What it unlocks", payoff));
        }

        if (!string.IsNullOrWhiteSpace(proofNote))
        {
            facts.Add(new FeatureDetailFactViewModel("How to verify it", proofNote));
        }

        return facts;
    }

    private static string? BuildFeatureDetailProofNote(PublicFeatureCardDto card)
    {
        if (!string.IsNullOrWhiteSpace(card.ProofNote))
        {
            return card.ProofNote;
        }

        return card.Bucket switch
        {
            "coming_next" => "Read the horizon brief, compare it to the current preview surface, and treat this as planned product work until it appears on the live proof shelf.",
            "featured_artifacts" => "Use the proof gallery and current release shelf together to verify whether this artifact is live today or still preview-only.",
            _ => null
        };
    }

    private static string? BuildFeatureDetailPayoff(PublicFeatureCardDto card)
    {
        if (!string.IsNullOrWhiteSpace(card.Payoff))
        {
            return card.Payoff;
        }

        return card.Bucket switch
        {
            "featured_artifacts" => "This artifact keeps the preview tangible through manifests, provenance, and one truthful next action instead of a vague gallery card.",
            "coming_next" => "The payoff only becomes real when the horizon moves onto the live proof shelf, but the user value is already explicit here.",
            _ => null
        };
    }

    private static IReadOnlyList<string> BuildFeatureDetailMicroProof(PublicFeatureCardDto card)
    {
        var explicitProof = SplitMicroProof(card.MicroProof);
        if (explicitProof.Count > 0)
        {
            return explicitProof;
        }

        return card.Bucket switch
        {
            "coming_next" => new[] { "Planned product work", "Current proof shelf contrast", "Deeper horizon brief" },
            "featured_artifacts" => new[] { "Manifest-backed", "Preview or live status", "Next truthful action" },
            _ => Array.Empty<string>()
        };
    }

    private static IReadOnlyList<string> SplitMicroProof(string? raw)
        => string.IsNullOrWhiteSpace(raw)
            ? Array.Empty<string>()
            : raw.Split('|', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

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
