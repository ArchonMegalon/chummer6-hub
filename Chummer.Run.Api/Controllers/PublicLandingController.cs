using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.ViewModels;
using Chummer.Campaign.Contracts;
using Chummer.Run.Contracts.Community;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;
using Chummer.Control.Contracts.Support;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Http;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/public")]
public sealed class PublicLandingController : Controller
{
    private readonly PublicLandingService _landing;
    private readonly PublicReleaseManifestService _releases;
    private readonly CampaignOsLocalProofService _campaignOsProof;
    private readonly ReleaseSelectionService _releaseSelection;
    private readonly PublicActionResolver _actions;
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;
    private readonly IdentityLinkService _links;
    private readonly UserExperienceService _experience;
    private readonly InstallLinkingService _installLinking;
    private readonly CampaignSpineService _campaignSpine;
    private readonly CampaignWorkspaceServerPlaneService _workspaceServerPlane;
    private readonly HubPageChromeService _chrome;
    private readonly PublicTrustContentService _trustContent;
    private readonly PublicPrivacyBoundaryService _privacyBoundaries;
    private readonly PublicTrustPulseService _trustPulse;
    private readonly SupportCaseService _supportCases;
    private readonly SupportCasePresentationService _supportPresentation;
    private readonly ILogger<PublicLandingController> _logger;

    public PublicLandingController(
        PublicLandingService landing,
        PublicReleaseManifestService releases,
        CampaignOsLocalProofService campaignOsProof,
        ReleaseSelectionService releaseSelection,
        PublicActionResolver actions,
        AccountService accounts,
        HubIdentityClient identity,
        IdentityLinkService links,
        UserExperienceService experience,
        InstallLinkingService installLinking,
        CampaignSpineService campaignSpine,
        CampaignWorkspaceServerPlaneService workspaceServerPlane,
        HubPageChromeService chrome,
        PublicTrustContentService trustContent,
        PublicPrivacyBoundaryService privacyBoundaries,
        PublicTrustPulseService trustPulse,
        SupportCaseService supportCases,
        SupportCasePresentationService supportPresentation,
        ILogger<PublicLandingController> logger)
    {
        _landing = landing;
        _releases = releases;
        _campaignOsProof = campaignOsProof;
        _releaseSelection = releaseSelection;
        _actions = actions;
        _accounts = accounts;
        _identity = identity;
        _links = links;
        _experience = experience;
        _installLinking = installLinking;
        _campaignSpine = campaignSpine;
        _workspaceServerPlane = workspaceServerPlane;
        _chrome = chrome;
        _trustContent = trustContent;
        _privacyBoundaries = privacyBoundaries;
        _trustPulse = trustPulse;
        _supportCases = supportCases;
        _supportPresentation = supportPresentation;
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
        var manifestPrimaryHeroAction = surface.HeroCtas.FirstOrDefault(static action => string.Equals(action.Emphasis, "primary", StringComparison.OrdinalIgnoreCase));
        var secondaryHeroAction = surface.HeroCtas.FirstOrDefault(static action => string.Equals(action.Emphasis, "secondary", StringComparison.OrdinalIgnoreCase))
            ?? surface.HeroCtas.Skip(1).FirstOrDefault()
            ?? new PublicLandingActionDto("See what works today", "/now", "secondary");
        var primaryHeroAction = !authenticated && manifestPrimaryHeroAction is not null
            ? manifestPrimaryHeroAction
            : _releaseSelection.BuildPublicPrimaryAction(manifest, authenticated);
        var model = new LandingPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Chummer", surface.Subhead, "/", cancellationToken),
            Surface: surface,
            Assets: assetCatalog,
            Manifest: manifest,
            ReleaseExperience: releaseExperience,
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            PrimaryHeroAction: primaryHeroAction,
            SecondaryHeroAction: secondaryHeroAction,
            Workflows: ResolveCards(_landing.CardsForBucket(surface, "start_here"), assetCatalog, authenticated: false, "/"),
            TrustPillars: _landing.CardsForBucket(surface, "why_trust_it"),
            Lanes: ResolveCards(_landing.CardsForBucket(surface, "choose_your_lane"), assetCatalog, authenticated: false, "/"),
            AvailableToday: ResolveCards(nowCards.Where(static card => PublicSurfaceStatus.IsAvailableToday(card.Badge)).ToArray(), assetCatalog, authenticated: false, "/"),
            PreviewItems: ResolveCards(nowCards.Where(static card => !PublicSurfaceStatus.IsAvailableToday(card.Badge)).ToArray(), assetCatalog, authenticated: false, "/"),
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
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        var model = new NowPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("What Is Real Now", "Readiness labels and direct evidence for what you can use today.", "/now", cancellationToken),
            Surface: surface,
            Assets: assetCatalog,
            ReleaseExperience: releaseExperience,
            ProofModules: ResolveCards(_landing.CardsForBucket(surface, "start_here").Take(3).ToArray(), assetCatalog, authenticated: false, "/now"),
            AvailableToday: ResolveCards(nowCards.Where(static card => PublicSurfaceStatus.IsAvailableToday(card.Badge)).ToArray(), assetCatalog, authenticated: false, "/now"),
            Inspectable: ResolveCards(nowCards.Where(static card => !PublicSurfaceStatus.IsAvailableToday(card.Badge)).ToArray(), assetCatalog, authenticated: false, "/now"),
            SignedInPreview: surface.RegisteredOverlays,
            Manifest: manifest,
            CampaignOsProof: _campaignOsProof.LoadProof(),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
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
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        var model = new DownloadsPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Downloads", "Install the current preview, compare package types, and keep release integrity in view.", "/downloads", cancellationToken),
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            Manifest: manifest,
            ReleaseExperience: releaseExperience,
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
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
                AccountHref: "/account/access",
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
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), chrome.Authenticated);
        return View(
            "~/Views/PublicLanding/TrustPage.cshtml",
            _trustContent.BuildHelpPage(chrome) with
            {
                PrivacyBoundary = _privacyBoundaries.BuildPanel("help"),
                TrustPulse = BuildPublicTrustPulsePanel(manifest, releaseExperience),
                SignedInStatus = await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken)
            });
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
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), chrome.Authenticated);
        return View(
            "~/Views/PublicLanding/TrustPage.cshtml",
            _trustContent.BuildPrivacyPage(chrome) with
            {
                PrivacyBoundary = _privacyBoundaries.BuildPanel("privacy"),
                TrustPulse = BuildPublicTrustPulsePanel(manifest, releaseExperience)
            });
    }

    [HttpGet("/terms")]
    [Produces("text/html")]
    public async Task<IActionResult> TermsPage(CancellationToken cancellationToken)
    {
        var chrome = await BuildPublicOrAuthenticatedChromeAsync("Terms", "Preview-use expectations, support posture, and the boundaries of the current hosted promise.", "/terms", cancellationToken);
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), chrome.Authenticated);
        return View(
            "~/Views/PublicLanding/TrustPage.cshtml",
            _trustContent.BuildTermsPage(chrome) with
            {
                TrustPulse = BuildPublicTrustPulsePanel(manifest, releaseExperience)
            });
    }

    [HttpGet("/contact")]
    [Produces("text/html")]
    public async Task<IActionResult> ContactPage(CancellationToken cancellationToken)
    {
        var chrome = await BuildPublicOrAuthenticatedChromeAsync("Contact", "Where to send bugs, account questions, and public product feedback right now.", "/contact", cancellationToken);
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), chrome.Authenticated);
        return View("~/Views/PublicLanding/TrustPage.cshtml", await BuildContactPageModelAsync(chrome, manifest, releaseExperience, cancellationToken));
    }

    [HttpGet("/contact/submitted/{caseId}")]
    [Produces("text/html")]
    public async Task<IActionResult> ContactSubmittedPage([FromRoute] string caseId, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(caseId))
        {
            return NotFound();
        }

        var chrome = await BuildPublicOrAuthenticatedChromeAsync("Support case submitted", "What happens next after a first-party support report reaches Chummer.", $"/contact/submitted/{caseId}", cancellationToken);
        var subject = await TryGetOptionalSubjectAsync(cancellationToken);
        var authenticated = subject is not null;
        var trackedCase = subject is null
            ? null
            : _supportCases.GetForReporter(caseId, _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email).UserId, subject.SubjectId);
        var highlights = new List<string>
        {
            $"Case id {caseId}",
            authenticated ? "Tracked on your account support page" : "Guest follow-up stays on the reply email you provided"
        };
        if (trackedCase?.Attachments is { Count: > 0 })
        {
            highlights.Add($"{trackedCase.Attachments.Count} attachment(s) saved");
        }

        var actions = new List<TrustPageActionViewModel>();
        if (trackedCase is not null)
        {
            actions.Add(new TrustPageActionViewModel("Open tracked support", $"/account/support/{trackedCase.CaseId}", "primary"));
        }
        else if (authenticated)
        {
            actions.Add(new TrustPageActionViewModel("Open account support", "/account/support", "primary"));
        }
        else
        {
            actions.Add(new TrustPageActionViewModel("Create account for tracked support", "/signup?next=%2Faccount%2Fsupport", "primary"));
        }

        actions.Add(new TrustPageActionViewModel("Return to help", "/help", "secondary"));

        return View("~/Views/PublicLanding/SupportSubmitted.cshtml", new SupportSubmittedPageViewModel(
            Chrome: chrome,
            Eyebrow: "Support",
            Heading: "Support case received",
            Intro: trackedCase is null
                ? "Chummer accepted the report. Keep the case id nearby if you need to mention it later."
                : "Chummer accepted the report and linked it to the signed-in account path so the next routed update stays visible.",
            CaseId: caseId,
            StatusLabel: trackedCase?.Status ?? SupportCaseStatuses.New,
            ResponseExpectation: authenticated
                ? "Tracked support updates should appear inside Account > Support when the case moves through triage or a release reaches reporter-ready state."
                : "Guest reports should include a reply email. Clear preview reports usually get an answer within two working days.",
            Highlights: highlights,
            Actions: actions,
            Attachments: trackedCase?.Attachments ?? Array.Empty<SupportCaseAttachmentProjection>(),
            TrackedCaseSummary: trackedCase is null ? null : _supportPresentation.Build(trackedCase)));
    }

    [HttpPost("/contact")]
    [ValidateAntiForgeryToken]
    [Consumes("multipart/form-data", "application/x-www-form-urlencoded")]
    [Produces("text/html")]
    public async Task<IActionResult> SubmitContactCase(
        [FromForm] string? kind,
        [FromForm] string? title,
        [FromForm] string? summary,
        [FromForm] string? detail,
        [FromForm] string? replyEmail,
        [FromForm] string? installationId,
        [FromForm] string? applicationVersion,
        [FromForm] string? releaseChannel,
        [FromForm] string? headId,
        [FromForm] string? platform,
        [FromForm] string? arch,
        [FromForm] List<IFormFile>? attachments,
        CancellationToken cancellationToken)
    {
        var request = new SupportCaseSubmitRequest(
            Kind: kind ?? string.Empty,
            Title: title ?? string.Empty,
            Summary: summary ?? string.Empty,
            Detail: detail ?? string.Empty,
            ReporterEmail: replyEmail,
            InstallationId: installationId,
            ApplicationVersion: applicationVersion,
            ReleaseChannel: releaseChannel,
            HeadId: headId,
            Platform: platform,
            Arch: arch,
            Source: SupportCaseSourceKinds.PublicWeb);

        try
        {
            var subject = await TryGetOptionalSubjectAsync(cancellationToken);
            if (subject is null && string.IsNullOrWhiteSpace(replyEmail))
            {
                throw new ArgumentException("A reply email is required when you submit support without an account.");
            }

            var user = subject is null ? null : _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var created = _supportCases.Submit(user?.UserId, subject?.SubjectId, request, await ReadSupportUploadsAsync(attachments, cancellationToken));
            return Redirect($"/contact/submitted/{Uri.EscapeDataString(created.CaseId)}");
        }
        catch (ArgumentException ex)
        {
            var chrome = await BuildPublicOrAuthenticatedChromeAsync("Contact", "Where to send bugs, account questions, and public product feedback right now.", "/contact", cancellationToken);
            var installDefaults = await ResolveSupportIntakeDefaultsAsync(cancellationToken);
            var model = _trustContent.BuildContactPage(chrome) with
            {
                SupportIntake = BuildSupportIntakeModel(
                    authenticated: chrome.Authenticated,
                    submissionNotice: ex.Message,
                    installDefaults,
                    new SupportIntakeOverrides(
                        Kind: kind,
                        Title: title,
                        Summary: summary,
                        Detail: detail,
                        Platform: platform,
                        ApplicationVersion: applicationVersion,
                        InstallationId: installationId,
                        ReleaseChannel: releaseChannel,
                        HeadId: headId,
                        Arch: arch,
                        ContextHint: ResolveSupportContextHintFromRequestQuery()))
            };
            return View("~/Views/PublicLanding/TrustPage.cshtml", model);
        }
    }

    [HttpGet("/home")]
    [HttpGet("/home/{section}")]
    [Produces("text/html")]
    public async Task<IActionResult> HomePage([FromRoute] string? section, CancellationToken cancellationToken)
    {
        var selectedSection = NormalizeHomeSection(section);
        var currentPath = selectedSection == "overview" ? "/home" : $"/home/{selectedSection}";
        var (chromeTitle, chromeDescription) = DescribeHomeSection(selectedSection);

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var surface = _landing.LoadSurface();
            var assetCatalog = new AssetCatalogViewModel(surface.Assets);
            var links = _links.GetSummary(subject.SubjectId);
            var experience = _experience.GetOrCreate(subject.SubjectId);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var supportCases = _supportCases.ListForReporter(user.UserId, subject.SubjectId).Items;
            var supportCaseSummaries = _supportPresentation.BuildList(supportCases, installLinking);
            var campaignSpine = _campaignSpine.GetAccountSummary(user, installLinking);
        var leadWorkspaceServerPlane = campaignSpine.Workspaces.Count == 0
            ? null
            : _workspaceServerPlane.GetWorkspaceServerPlane(user, campaignSpine.Workspaces[0].WorkspaceId, installLinking);
        var model = new HomePageViewModel(
            Chrome: _chrome.BuildAuthenticatedChrome(chromeTitle, chromeDescription, currentPath, user.DisplayName),
            CurrentSection: selectedSection,
            Sections: BuildHomeSections(selectedSection),
            Surface: surface,
            Assets: assetCatalog,
            User: user,
            Links: links,
            Experience: experience,
            InstallLinking: installLinking,
            SupportCases: supportCases,
            SupportCaseSummaries: supportCaseSummaries,
            CampaignSpine: campaignSpine,
            LeadWorkspaceServerPlane: leadWorkspaceServerPlane,
            PrimaryAction: BuildHomePrimaryAction(experience, campaignSpine, installLinking),
            NowRail: ResolveCards(_landing.CardsForBucket(surface, "whats_real_now").Take(3).ToArray(), assetCatalog, authenticated: true, currentPath),
            HorizonRail: ResolveCards(_landing.CardsForBucket(surface, "coming_next").Take(3).ToArray(), assetCatalog, authenticated: true, currentPath));
            return View("~/Views/PublicLanding/Home.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Home page could not confirm the signed-in identity.");
            return View("~/Views/Auth/Message.cshtml", new AuthMessagePageViewModel(
                Chrome: _chrome.BuildPublicChrome("Home unavailable", "Hub could not confirm the signed-in home surface right now.", currentPath),
                Heading: "Home is unavailable right now",
                SupportLine: "Chummer could not open the signed-in home surface right now. Your session may still be valid, so try again in a moment.",
                Notice: null,
                PrimaryLabel: "Try home again",
                PrimaryHref: currentPath,
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

    private static HomePrimaryActionViewModel BuildHomePrimaryAction(
        HubUserExperienceDto experience,
        AccountCampaignSummary campaignSpine,
        InstallLinkingSummaryDto installLinking)
    {
        if (!experience.OnboardingCompleted)
        {
            return new HomePrimaryActionViewModel(
                "Setup",
                "Finish setup",
                "Complete the short setup flow so Chummer can recover your account, route updates, and keep your account surface calm.",
                "Complete setup",
                "/home/setup",
                "primary");
        }

        bool hasNoCampaignWork = campaignSpine.Dossiers.Count == 0
            && campaignSpine.Campaigns.Count == 0
            && campaignSpine.Runs.Count == 0
            && campaignSpine.Workspaces.Count == 0;

        if ((installLinking.ClaimedInstallations?.Count ?? 0) > 0 && hasNoCampaignWork)
        {
            return new HomePrimaryActionViewModel(
                "Starter lane",
                "Open work and seed your first playable session",
                "Your install is linked. Open the work lane to move from setup into the next safe session surface before returning to optional tasks.",
                "Open work",
                "/home/work",
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
                "Open Devices and access",
                "/account/access",
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

    private static string NormalizeHomeSection(string? section)
        => string.IsNullOrWhiteSpace(section)
            ? "overview"
            : section.Trim().ToLowerInvariant() switch
            {
                "overview" => "overview",
                "access" => "access",
                "work" => "work",
                "setup" => "setup",
                _ => "overview"
            };

    private static IReadOnlyList<SectionLinkViewModel> BuildHomeSections(string currentSection)
        => new[]
        {
            new SectionLinkViewModel("overview", "Overview", "/home", string.Equals(currentSection, "overview", StringComparison.OrdinalIgnoreCase)),
            new SectionLinkViewModel("access", "Access", "/home/access", string.Equals(currentSection, "access", StringComparison.OrdinalIgnoreCase)),
            new SectionLinkViewModel("work", "Work", "/home/work", string.Equals(currentSection, "work", StringComparison.OrdinalIgnoreCase)),
            new SectionLinkViewModel("setup", "Setup", "/home/setup", string.Equals(currentSection, "setup", StringComparison.OrdinalIgnoreCase))
        };

    private static (string Title, string Description) DescribeHomeSection(string currentSection)
        => currentSection switch
        {
            "access" => ("Home · Access", "Install return, support closure, and access state without the rest of the dashboard."),
            "work" => ("Home · Work", "Current work, return context, and the next useful route without the rest of Home."),
            "setup" => ("Home · Setup", "Finish the short account setup flow, then come back to access and work."),
            _ => ("Home", "Pick the next action and keep track of what is opening next.")
        };

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

    private async Task<AuthenticatedHubSubject?> TryGetOptionalPublicSurfaceSubjectAsync(string currentPath, CancellationToken cancellationToken)
    {
        try
        {
            return await TryGetOptionalSubjectAsync(cancellationToken);
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Skipping signed-in public trust projection after identity failure for {Path}.", currentPath);
            return null;
        }
    }

    private async Task<TrustPageViewModel> BuildContactPageModelAsync(
        SiteChromeViewModel chrome,
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience,
        CancellationToken cancellationToken)
    {
        var installDefaults = await ResolveSupportIntakeDefaultsAsync(cancellationToken);
        var overrides = ResolveSupportIntakeOverridesFromQuery();
        return _trustContent.BuildContactPage(chrome) with
        {
            PrivacyBoundary = _privacyBoundaries.BuildPanel("contact"),
            TrustPulse = BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SupportIntake = BuildSupportIntakeModel(
                authenticated: chrome.Authenticated,
                submissionNotice: null,
                installDefaults,
                overrides)
        };
    }

    private PublicTrustPulsePanelViewModel? BuildPublicTrustPulsePanel(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience)
    {
        var pulse = _trustPulse.LoadSnapshot();
        if (pulse is null)
        {
            return null;
        }

        List<string> microProof =
        [
            string.IsNullOrWhiteSpace(pulse.AsOf) ? "Current weekly pulse" : $"As of {pulse.AsOf}"
        ];

        if (!string.IsNullOrWhiteSpace(pulse.ActiveCheckpointTitle))
        {
            microProof.Add(string.IsNullOrWhiteSpace(pulse.ActiveCheckpointId)
                ? pulse.ActiveCheckpointTitle!
                : $"{pulse.ActiveCheckpointId} · {pulse.ActiveCheckpointTitle}");
        }

        if (!string.IsNullOrWhiteSpace(pulse.NextCheckpointQuestion))
        {
            microProof.Add($"Next question: {pulse.NextCheckpointQuestion}");
        }

        if (pulse.OverallProgressPercent is int overallProgressPercent && !string.IsNullOrWhiteSpace(pulse.PhaseLabel))
        {
            microProof.Add($"{overallProgressPercent}% · {pulse.PhaseLabel}");
        }
        else if (pulse.OverallProgressPercent is int progressOnly)
        {
            microProof.Add($"{progressOnly}% weighted progress");
        }

        if (pulse.HistorySnapshotCount is int historySnapshotCount && historySnapshotCount > 0)
        {
            microProof.Add($"{historySnapshotCount} measured snapshot(s)");
        }

        var rows = new List<PublicTrustPulseRowViewModel>
        {
            new("Recommended now", BuildTrustPulseRecommendedSummary(manifest, releaseExperience)),
            new("Who can get it now", BuildTrustPulseAccessSummary(releaseExperience)),
            new("Release proof", BuildReleaseProofSummary(manifest)),
            new("Launch readiness", BuildTrustPulseLaunchReadinessSummary(pulse)),
            new("Provider-route stewardship", BuildProviderRouteStewardshipSummary(pulse)),
            new("Adoption health", BuildTrustPulseAdoptionSummary(pulse)),
            new("Journey pulse", BuildJourneyPulseSummary(pulse)),
            new("Current caution", BuildTrustPulseCautionSummary(pulse))
        };

        string journeyState = HumanizeToken(pulse.JourneyGateState, "Current");
        string heading = string.IsNullOrWhiteSpace(pulse.LongestPoleLabel)
            ? $"{journeyState} trust posture this week"
            : $"{journeyState} trust posture; {pulse.LongestPoleLabel} still needs caution";
        string summary = string.IsNullOrWhiteSpace(pulse.Summary)
            ? "The weekly pulse keeps the release posture, journey evidence, and caution lane visible in one customer-safe panel."
            : pulse.Summary;

        return new PublicTrustPulsePanelViewModel(
            Eyebrow: "Weekly trust pulse",
            Heading: heading,
            Summary: summary,
            MicroProof: microProof,
            Rows: rows,
            PrimaryAction: new TrustPageActionViewModel("Open progress", "/progress", "secondary"),
            SecondaryAction: new TrustPageActionViewModel("Open downloads", "/downloads", "ghost"));
    }

    private async Task<SignedInTrustStatusPanelViewModel?> BuildSignedInTrustStatusPanelAsync(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience,
        CancellationToken cancellationToken)
    {
        var subject = await TryGetOptionalPublicSurfaceSubjectAsync(Request.Path.Value ?? "/", cancellationToken);
        if (subject is null)
        {
            return null;
        }

        var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
        var supportSummaries = _supportPresentation.BuildList(_supportCases.ListForReporter(user.UserId, subject.SubjectId).Items, installLinking);
        var latestInstallation = installLinking.ClaimedInstallations?
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .FirstOrDefault();
        var installCount = installLinking.ClaimedInstallations?.Count ?? 0;
        var followThrough = supportSummaries
            .Where(static item => item.ReporterActionNeeded || item.NeedsLinkedInstall || item.NeedsInstallUpdate || item.CanVerifyFix)
            .OrderByDescending(static item => item.Case.UpdatedAtUtc)
            .FirstOrDefault();
        var rows = new List<SignedInTrustStatusRowViewModel>
        {
            new(
                "Linked installs",
                installCount > 0
                    ? $"{installCount} linked"
                    : installLinking.PendingClaimTickets.Count > 0
                        ? $"{installLinking.PendingClaimTickets.Count} claim pending"
                        : "No linked install yet"),
            new(
                "Current linked build",
                latestInstallation is null
                    ? "No linked build yet"
                    : $"{ResolveInstallationDisplayLabel(latestInstallation)} · {latestInstallation.Version} on {ResolveChannelLabel(latestInstallation.Channel, manifest, releaseExperience)}"),
            new("Release proof", BuildReleaseProofSummary(manifest)),
            new(
                "Support follow-through",
                followThrough is null
                    ? "No active fix, relink, or evidence follow-through is waiting on this account."
                    : $"{followThrough.StageLabel} · {followThrough.NextSafeAction}")
        };

        if (followThrough?.NeedsLinkedInstall == true)
        {
            return new SignedInTrustStatusPanelViewModel(
                Eyebrow: "Signed-in trust status",
                Heading: "Relink the affected install",
                Summary: followThrough.InstallReadinessSummary,
                Rows: rows,
                PrimaryAction: new TrustPageActionViewModel("Open Devices and access", "/account/access", "primary"),
                SecondaryAction: new TrustPageActionViewModel("Open support timeline", "/account/support", "secondary"));
        }

        if (followThrough?.NeedsInstallUpdate == true)
        {
            return new SignedInTrustStatusPanelViewModel(
                Eyebrow: "Signed-in trust status",
                Heading: "Update your linked install",
                Summary: followThrough.InstallReadinessSummary,
                Rows: rows,
                PrimaryAction: new TrustPageActionViewModel("Open downloads", "/downloads", "primary"),
                SecondaryAction: new TrustPageActionViewModel("Open support timeline", "/account/support", "secondary"));
        }

        if (followThrough?.CanVerifyFix == true)
        {
            return new SignedInTrustStatusPanelViewModel(
                Eyebrow: "Signed-in trust status",
                Heading: "Your linked install can verify a fix now",
                Summary: followThrough.VerificationSummary,
                Rows: rows,
                PrimaryAction: new TrustPageActionViewModel("Open support timeline", "/account/support", "primary"),
                SecondaryAction: new TrustPageActionViewModel("Open downloads", "/downloads", "secondary"));
        }

        if (followThrough?.ReporterActionNeeded == true)
        {
            return new SignedInTrustStatusPanelViewModel(
                Eyebrow: "Signed-in trust status",
                Heading: "Support needs one more detail",
                Summary: followThrough.NextSafeAction,
                Rows: rows,
                PrimaryAction: new TrustPageActionViewModel("Open support timeline", "/account/support", "primary"),
                SecondaryAction: new TrustPageActionViewModel("Open help", "/help", "secondary"));
        }

        if (latestInstallation is null)
        {
            return new SignedInTrustStatusPanelViewModel(
                Eyebrow: "Signed-in trust status",
                Heading: "No linked install is attached yet",
                Summary: "Claim the current preview first so downloads, support closure, and recovery stay attached to this account instead of turning into a fresh unknown device next time.",
                Rows: rows,
                PrimaryAction: new TrustPageActionViewModel("Open Devices and access", "/account/access", "primary"),
                SecondaryAction: new TrustPageActionViewModel("Open downloads", "/downloads", "secondary"));
        }

        string installationLabel = ResolveInstallationDisplayLabel(latestInstallation);
        return new SignedInTrustStatusPanelViewModel(
            Eyebrow: "Signed-in trust status",
            Heading: $"{installationLabel} is attached",
            Summary: $"{installationLabel} is linked on {latestInstallation.Version} in {ResolveChannelLabel(latestInstallation.Channel, manifest, releaseExperience)}. Downloads, support, and recovery are all using the same claimed install context right now.",
            Rows: rows,
            PrimaryAction: new TrustPageActionViewModel("Open Devices and access", "/account/access", "primary"),
            SecondaryAction: new TrustPageActionViewModel("Open downloads", "/downloads", "secondary"));
    }

    private SupportIntakeOverrides ResolveSupportIntakeOverridesFromQuery()
    {
        string? kind = NormalizeSupportPrefill(Request.Query.TryGetValue("kind", out var kindValues) ? kindValues.ToString() : null);
        string? title = NormalizeSupportPrefill(Request.Query.TryGetValue("title", out var titleValues) ? titleValues.ToString() : null);
        string? summary = NormalizeSupportPrefill(Request.Query.TryGetValue("summary", out var summaryValues) ? summaryValues.ToString() : null);
        string? detail = NormalizeSupportPrefill(Request.Query.TryGetValue("detail", out var detailValues) ? detailValues.ToString() : null);
        string? platform = NormalizeSupportPrefill(Request.Query.TryGetValue("platform", out var platformValues) ? platformValues.ToString() : null);
        string? applicationVersion = NormalizeSupportPrefill(Request.Query.TryGetValue("applicationVersion", out var versionValues) ? versionValues.ToString() : null);
        string? installationId = NormalizeSupportPrefill(Request.Query.TryGetValue("installationId", out var installationValues) ? installationValues.ToString() : null);
        string? releaseChannel = NormalizeSupportPrefill(Request.Query.TryGetValue("releaseChannel", out var channelValues) ? channelValues.ToString() : null);
        string? headId = NormalizeSupportPrefill(Request.Query.TryGetValue("headId", out var headValues) ? headValues.ToString() : null);
        string? arch = NormalizeSupportPrefill(Request.Query.TryGetValue("arch", out var archValues) ? archValues.ToString() : null);

        return new SupportIntakeOverrides(
            Kind: kind,
            Title: title,
            Summary: summary,
            Detail: detail,
            Platform: platform,
            ApplicationVersion: applicationVersion,
            InstallationId: installationId,
            ReleaseChannel: releaseChannel,
            HeadId: headId,
            Arch: arch,
            ContextHint: ResolveSupportContextHintFromRequestQuery());
    }

    private string? ResolveSupportContextHintFromRequestQuery()
    {
        List<string> segments = [];

        string? sessionId = NormalizeSupportPrefill(Request.Query.TryGetValue("sessionId", out var sessionValues) ? sessionValues.ToString() : null);
        if (!string.IsNullOrWhiteSpace(sessionId))
        {
            segments.Add($"session {sessionId}");
        }

        string? sceneId = NormalizeSupportPrefill(Request.Query.TryGetValue("sceneId", out var sceneValues) ? sceneValues.ToString() : null);
        if (!string.IsNullOrWhiteSpace(sceneId))
        {
            segments.Add($"scene {sceneId}");
        }

        string? runtime = NormalizeSupportPrefill(Request.Query.TryGetValue("runtime", out var runtimeValues) ? runtimeValues.ToString() : null);
        if (!string.IsNullOrWhiteSpace(runtime))
        {
            segments.Add($"runtime {runtime}");
        }

        string? bundle = NormalizeSupportPrefill(Request.Query.TryGetValue("bundle", out var bundleValues) ? bundleValues.ToString() : null);
        if (!string.IsNullOrWhiteSpace(bundle))
        {
            segments.Add($"bundle {bundle}");
        }

        return segments.Count == 0
            ? null
            : $"Follow-through opened with {string.Join(" · ", segments)}.";
    }

    private static string? NormalizeSupportPrefill(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static SupportIntakeViewModel BuildSupportIntakeModel(
        bool authenticated,
        string? submissionNotice,
        SupportIntakeDefaults installDefaults,
        SupportIntakeOverrides overrides)
        => new(
            ActionHref: "/contact",
            Heading: "Open a first-party support case",
            Intro: authenticated
                ? "Use the form for a quick report here, or open Account > Support when you want the full tracked case view."
                : "Use the first-party intake here when you want help without a GitHub account. Create an account later if you want tracked follow-up inside Chummer.",
            Authenticated: authenticated,
            AccountSupportHref: authenticated ? "/account/support" : "/signup?next=%2Faccount%2Fsupport",
            AccountSupportLabel: authenticated ? "Open tracked support" : "Create account for tracked support",
            ResponseExpectation: authenticated
                ? "Tracked cases stay visible in Account. When the report is actionable, the next routed update should show up there without sending you into side channels."
                : "Guest cases should include a reply email. We usually answer preview support within two working days when the report includes a clear reproduction path.",
            SubmissionNotice: submissionNotice,
            AttachmentHelp: "Add screenshots, logs, or a small diagnostic bundle when they make the bug or install problem easier to route.",
            Options:
            [
                new SupportIntakeOptionViewModel(SupportCaseKinds.InstallHelp, "Install or update", "Choose this when the installer, updater, or download handoff is the problem."),
                new SupportIntakeOptionViewModel(SupportCaseKinds.BugReport, "Product bug", "Use this for broken behavior, bad routing, or product regressions."),
                new SupportIntakeOptionViewModel(SupportCaseKinds.Feedback, "Feature request or UX feedback", "Use this when the product direction is right but the current surface is getting in your way.")
            ],
            DefaultKind: overrides.Kind,
            DefaultTitle: overrides.Title,
            DefaultSummary: overrides.Summary,
            DefaultDetail: overrides.Detail,
            DefaultPlatform: overrides.Platform ?? installDefaults.Platform,
            DefaultApplicationVersion: overrides.ApplicationVersion ?? installDefaults.ApplicationVersion,
            DefaultInstallationId: overrides.InstallationId ?? installDefaults.InstallationId,
            DefaultReleaseChannel: overrides.ReleaseChannel ?? installDefaults.ReleaseChannel,
            DefaultHeadId: overrides.HeadId ?? installDefaults.HeadId,
            DefaultArch: overrides.Arch ?? installDefaults.Arch,
            ContextHint: string.Join(" ",
                new[]
                {
                    installDefaults.ContextHint,
                    overrides.ContextHint
                }.Where(static item => !string.IsNullOrWhiteSpace(item))));

    private async Task<SupportIntakeDefaults> ResolveSupportIntakeDefaultsAsync(CancellationToken cancellationToken)
    {
        var subject = await TryGetOptionalSubjectAsync(cancellationToken);
        if (subject is null)
        {
            return SupportIntakeDefaults.Empty;
        }

        var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        var summary = _installLinking.GetSummary(user.UserId, subject.SubjectId);
        var installation = summary.ClaimedInstallations?.OrderByDescending(static item => item.UpdatedAtUtc).FirstOrDefault();
        if (installation is not null)
        {
            var descriptor = string.Join(" · ",
                new[]
                {
                    installation.Platform,
                    installation.Version,
                    installation.Channel,
                    installation.HeadId,
                    installation.Arch,
                    installation.InstallationId
                }.Where(static item => !string.IsNullOrWhiteSpace(item)));
            return new SupportIntakeDefaults(
                Platform: installation.Platform,
                ApplicationVersion: installation.Version,
                InstallationId: installation.InstallationId,
                ReleaseChannel: installation.Channel,
                HeadId: installation.HeadId,
                Arch: installation.Arch,
                ContextHint: string.IsNullOrWhiteSpace(descriptor)
                    ? "Prefilled from your most recent linked install."
                    : $"Prefilled from your most recent linked install: {descriptor}.");
        }

        var pendingTicket = summary.PendingClaimTickets
            .OrderByDescending(static item => item.CreatedAtUtc)
            .FirstOrDefault();
        if (pendingTicket is not null)
        {
            var descriptor = string.Join(" · ",
                new[]
                {
                    pendingTicket.ArtifactLabel,
                    pendingTicket.Version,
                    pendingTicket.Channel,
                    pendingTicket.ClaimCode
                }.Where(static item => !string.IsNullOrWhiteSpace(item)));
            return new SupportIntakeDefaults(
                Platform: pendingTicket.ArtifactLabel,
                ApplicationVersion: pendingTicket.Version,
                InstallationId: pendingTicket.ClaimCode,
                ReleaseChannel: pendingTicket.Channel,
                HeadId: null,
                Arch: null,
                ContextHint: string.IsNullOrWhiteSpace(descriptor)
                    ? "Prefilled from your latest pending install handoff."
                    : $"Prefilled from your latest pending install handoff: {descriptor}.");
        }

        return SupportIntakeDefaults.Empty;
    }

    private static string ResolveInstallationDisplayLabel(ClaimedInstallationDto installation)
        => installation.HostLabel
            ?? installation.HeadId
            ?? installation.ArtifactId
            ?? installation.InstallationId;

    private static string ResolveChannelLabel(
        string? channel,
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience)
    {
        if (!string.IsNullOrWhiteSpace(channel)
            && string.Equals(channel, manifest.Channel, StringComparison.OrdinalIgnoreCase))
        {
            return releaseExperience.Display.ChannelLabel;
        }

        return HumanizeToken(channel, "Current preview");
    }

    private static string BuildReleaseProofSummary(PublicReleaseManifestDto manifest)
    {
        string proof = HumanizeToken(manifest.ProofStatus, "Unknown");
        if (!string.IsNullOrWhiteSpace(manifest.SupportabilitySummary))
        {
            return $"{proof} · {manifest.SupportabilitySummary}";
        }

        if (!string.IsNullOrWhiteSpace(manifest.SupportabilityState))
        {
            return $"{proof} · {HumanizeToken(manifest.SupportabilityState, "Current preview")}";
        }

        return proof;
    }

    private static string BuildTrustPulseRecommendedSummary(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience)
    {
        if (manifest.Downloads.Count == 0 || releaseExperience.Recommended is null)
        {
            return string.IsNullOrWhiteSpace(manifest.Message)
                ? "No published build is on the shelf yet."
                : manifest.Message;
        }

        string accessSummary = releaseExperience.Recommended.RequiresAccount && !releaseExperience.GuestDownloadAvailable
            ? "Signed-in handoff is the recommended path so the install can stay linked."
            : "Guest-readable handoff is live on the current shelf.";
        return $"{releaseExperience.Recommended.Title} on {releaseExperience.Display.ChannelLabel}. {accessSummary}";
    }

    private static string BuildTrustPulseAccessSummary(ReleaseExperienceViewModel releaseExperience)
    {
        if (releaseExperience.Recommended is null)
        {
            return "No release handoff is published yet.";
        }

        if (releaseExperience.Recommended.RequiresAccount && !releaseExperience.GuestDownloadAvailable)
        {
            return "Signed-in handoff is the live path now, so the install stays linked and support can follow the exact device.";
        }

        if (releaseExperience.GuestDownloadAvailable)
        {
            return "Guest-readable handoff is visible now, and signing in adds linked-install follow-through.";
        }

        return "Signed-in handoff is available now for linked-install follow-through.";
    }

    private static string BuildJourneyPulseSummary(PublicTrustPulseSnapshot pulse)
    {
        string state = HumanizeToken(pulse.JourneyGateState, "Unknown");
        string reason = string.IsNullOrWhiteSpace(pulse.JourneyGateReason)
            ? "Current published evidence is holding."
            : pulse.JourneyGateReason!;
        string counts = $"{pulse.BlockedJourneyCount ?? 0} blocked / {pulse.WarningJourneyCount ?? 0} warning";
        return $"{state} · {reason} · {counts}";
    }

    private static string BuildTrustPulseCautionSummary(PublicTrustPulseSnapshot pulse)
    {
        List<string> segments = [];

        if (!string.IsNullOrWhiteSpace(pulse.LongestPoleLabel))
        {
            segments.Add($"{pulse.LongestPoleLabel} remains the current longest pole.");
        }

        if (pulse.HistorySnapshotCount is int historySnapshotCount && historySnapshotCount > 0)
        {
            segments.Add(historySnapshotCount < 6
                ? $"{historySnapshotCount} weekly snapshots are measured so far, so adoption history is still early."
                : $"{historySnapshotCount} weekly snapshots are on record.");
        }

        if (!string.IsNullOrWhiteSpace(pulse.NextCheckpointQuestion))
        {
            segments.Add(pulse.NextCheckpointQuestion!);
        }

        if (!string.IsNullOrWhiteSpace(pulse.ReleaseHealthReason))
        {
            segments.Add(pulse.ReleaseHealthReason!);
        }

        return segments.Count == 0
            ? "No extra caution note is published right now."
            : string.Join(" ", segments);
    }

    private static string BuildTrustPulseLaunchReadinessSummary(PublicTrustPulseSnapshot pulse)
    {
        if (!string.IsNullOrWhiteSpace(pulse.LaunchReadiness))
        {
            return pulse.LaunchReadiness!;
        }

        if (pulse.LongestPoleLabel is not null && string.Equals(pulse.JourneyGateState, "blocked", StringComparison.OrdinalIgnoreCase))
        {
            return $"Launch remains paused: {pulse.LongestPoleLabel} requires closure before broad fan-out.";
        }

        if (pulse.ActiveWaveStatus is not null && string.Equals(pulse.ActiveWaveStatus, "in_progress", StringComparison.OrdinalIgnoreCase))
        {
            return "Wave is still active. Continue from guided-wave proof and guard against scope regressions before expanding.";
        }

        if (string.Equals(pulse.ReleaseHealthState, "red", StringComparison.OrdinalIgnoreCase))
        {
            return "Hold launch expansion while release health remains red and active blockers resolve.";
        }

        return pulse.JourneyGateState is not null
            && string.Equals(pulse.JourneyGateState, "ready", StringComparison.OrdinalIgnoreCase)
            && (pulse.BlockedJourneyCount ?? 0) == 0
                ? "Ready to progress this wave if weekly signals stay stable."
                : "Launch posture follows current governance signals; review before large rollout.";
    }

    private static string BuildProviderRouteStewardshipSummary(PublicTrustPulseSnapshot pulse)
    {
        string defaultStatus = string.IsNullOrWhiteSpace(pulse.ProviderRouteDefault)
            ? "default route posture is governed by the Hub and not hard-coded in this lane"
            : pulse.ProviderRouteDefault!;
        string canaryStatus = string.IsNullOrWhiteSpace(pulse.ProviderRouteCanary)
            ? "canary status is not yet mirrored here"
            : pulse.ProviderRouteCanary!;
        string reviewDue = string.IsNullOrWhiteSpace(pulse.ProviderRouteReviewDue)
            ? string.Empty
            : $"; next review due {pulse.ProviderRouteReviewDue}.";
        string nextDecision = string.IsNullOrWhiteSpace(pulse.ProviderRouteNextDecision)
            ? string.Empty
            : $" Next decision: {pulse.ProviderRouteNextDecision}.";

        return string.Join(string.Empty, [defaultStatus, " — ", canaryStatus, reviewDue, nextDecision]).Replace(" .", ".").Trim();
    }

    private static string BuildTrustPulseAdoptionSummary(PublicTrustPulseSnapshot pulse)
    {
        List<string> segments = [];

        if (!string.IsNullOrWhiteSpace(pulse.LocalReleaseProofStatus))
        {
            segments.Add(string.Equals(pulse.LocalReleaseProofStatus, "passed", StringComparison.OrdinalIgnoreCase)
                ? "Current local edge proof passed."
                : $"Current local edge proof is {HumanizeToken(pulse.LocalReleaseProofStatus, "unknown").ToLowerInvariant()}.");
        }

        if (pulse.ProvenJourneyCount is int journeyCount && journeyCount > 0 && pulse.ProvenRouteCount is int routeCount && routeCount > 0)
        {
            segments.Add($"{journeyCount} journey proofs and {routeCount} trust routes are on record.");
        }
        else if (pulse.ProvenJourneyCount is int journeyOnly && journeyOnly > 0)
        {
            segments.Add($"{journeyOnly} journey proofs are on record.");
        }
        else if (pulse.ProvenRouteCount is int routeOnly && routeOnly > 0)
        {
            segments.Add($"{routeOnly} trust routes are on record.");
        }

        if (pulse.HistorySnapshotCount is int historySnapshotCount && historySnapshotCount > 0)
        {
            segments.Add(historySnapshotCount < 6
                ? $"{historySnapshotCount} weekly snapshots are measured so far, so adoption history is still early."
                : $"{historySnapshotCount} weekly snapshots are on record for the current public trust posture.");
        }

        return segments.Count == 0
            ? "Measured adoption evidence is still accumulating."
            : string.Join(" ", segments);
    }

    private static string HumanizeToken(string? value, string fallback)
        => string.IsNullOrWhiteSpace(value)
            ? fallback
            : System.Globalization.CultureInfo.InvariantCulture.TextInfo.ToTitleCase(value.Replace('_', ' '));

    private sealed record SupportIntakeDefaults(
        string? Platform,
        string? ApplicationVersion,
        string? InstallationId,
        string? ReleaseChannel,
        string? HeadId,
        string? Arch,
        string? ContextHint)
    {
        public static SupportIntakeDefaults Empty { get; } = new(null, null, null, null, null, null, null);
    }

    private sealed record SupportIntakeOverrides(
        string? Kind = null,
        string? Title = null,
        string? Summary = null,
        string? Detail = null,
        string? Platform = null,
        string? ApplicationVersion = null,
        string? InstallationId = null,
        string? ReleaseChannel = null,
        string? HeadId = null,
        string? Arch = null,
        string? ContextHint = null);

    private static async Task<IReadOnlyList<SupportAttachmentUpload>> ReadSupportUploadsAsync(
        IReadOnlyList<IFormFile>? files,
        CancellationToken cancellationToken)
    {
        if (files is null || files.Count == 0)
        {
            return Array.Empty<SupportAttachmentUpload>();
        }

        List<SupportAttachmentUpload> uploads = new(files.Count);
        foreach (var file in files)
        {
            if (file.Length <= 0)
            {
                continue;
            }

            await using var stream = file.OpenReadStream();
            using var buffer = new MemoryStream();
            await stream.CopyToAsync(buffer, cancellationToken);
            uploads.Add(new SupportAttachmentUpload(
                FileName: file.FileName,
                ContentType: file.ContentType,
                Content: buffer.ToArray()));
        }

        return uploads;
    }

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
        var primaryAction = _actions.ResolveDetailPrimaryAction(card, authenticated, currentPath);
        TrustPageActionViewModel? secondaryAction = null;
        if (!string.IsNullOrWhiteSpace(card.FallbackRoute)
            && !string.Equals(
                PublicRouteCatalog.NormalizeRoute(card.FallbackRoute),
                PublicRouteCatalog.NormalizeRoute(primaryAction.Href),
                StringComparison.OrdinalIgnoreCase))
        {
            secondaryAction = new TrustPageActionViewModel(
                card.FallbackLabel ?? "Read the deeper brief",
                card.FallbackRoute!,
                "ghost");
        }

        var proofNote = BuildFeatureDetailProofNote(card);
        var payoff = BuildFeatureDetailPayoff(card);
        var statusEyebrow = card.Bucket switch
        {
            "featured_artifacts" => "Availability",
            "coming_next" => "Roadmap status",
            _ => "Current status"
        };
        var statusHeading = card.Bucket switch
        {
            "featured_artifacts" when PublicSurfaceStatus.IsAvailableToday(card.Badge)
                => "What is live today",
            "featured_artifacts" => "What this artifact is proving next",
            "coming_next" => "Where this horizon sits now",
            _ => card.Badge
        };
        var facts = BuildFeatureDetailFacts(card);
        var model = new FeatureDetailPageViewModel(
            Chrome: chrome,
            Family: ResolveFeatureDetailFamily(card),
            Eyebrow: card.Bucket switch
            {
                "featured_artifacts" => "Artifact",
                "coming_next" => "Roadmap",
                _ => eyebrow
            },
            Heading: card.Title,
            Intro: card.Summary,
            StatusEyebrow: statusEyebrow,
            StatusHeading: statusHeading,
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

    private static string ResolveFeatureDetailFamily(PublicFeatureCardDto card)
        => card.Bucket switch
        {
            "coming_next" => "roadmap",
            "featured_artifacts" when PublicSurfaceStatus.IsAvailableToday(card.Badge)
                => "live-proof",
            "featured_artifacts" => "preview-concept",
            _ => "detail"
        };

    private static IReadOnlyList<FeatureDetailFactViewModel> BuildFeatureDetailFacts(PublicFeatureCardDto card)
    {
        var facts = new List<FeatureDetailFactViewModel>();
        var liveArtifact = PublicSurfaceStatus.IsAvailableToday(card.Badge);

        facts.Add(new(
            card.Bucket switch
            {
                "featured_artifacts" => liveArtifact ? "Availability" : "Preview status",
                "coming_next" => "Roadmap status",
                _ => "Current status"
            },
            $"{PublicSurfaceStatus.DisplayLabel(card.Badge)}. {card.Summary}"));

        if (!string.IsNullOrWhiteSpace(card.Audience))
        {
            facts.Add(new(
                card.Bucket switch
                {
                    "coming_next" => "Who should follow this",
                    "featured_artifacts" when liveArtifact => "Who should use this now",
                    "featured_artifacts" => "Who should track this",
                    _ => "Audience"
                },
                PublicSurfaceStatus.AudienceLabel(card.Audience)));
        }

        var nextStep = card.DetailPrimaryLabel
            ?? card.ActionLabel
            ?? card.FallbackLabel;
        if (!string.IsNullOrWhiteSpace(nextStep))
        {
            facts.Add(new(
                card.Bucket switch
                {
                    "coming_next" => "Best next route",
                    "featured_artifacts" when liveArtifact => "Start from",
                    "featured_artifacts" => "Follow from",
                    _ => "Next step"
                },
                nextStep));
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
            "coming_next" => "Compare this horizon with the current preview proof first, then open the deeper roadmap brief only when you need the longer rationale.",
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
