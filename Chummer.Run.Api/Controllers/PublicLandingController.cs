using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.ComponentModel.DataAnnotations;
using Microsoft.Extensions.Configuration;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.KarmaForge;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.ViewModels;
using Chummer.Campaign.Contracts;
using Chummer.Hub.Registry.Contracts;
using Chummer.Run.Contracts.Community;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;
using Chummer.Control.Contracts.Support;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Extensions;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.WebUtilities;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/public")]
public sealed class PublicLandingController : Controller
{
    private const string ReleaseUploadTicketEnvironmentVariable = "CHUMMER_RELEASE_UPLOAD_TICKET";
    private const string ReleaseUploadTokenEnvironmentVariable = "CHUMMER_RELEASE_UPLOAD_TOKEN";

    private readonly PublicLandingService _landing;
    private readonly PublicFlagshipCoverageService _flagshipCoverage;
    private readonly PublicReleaseManifestService _releases;
    private readonly CampaignOsLocalProofService _campaignOsProof;
    private readonly ReleaseSelectionService _releaseSelection;
    private readonly PublicActionResolver _actions;
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;
    private readonly IdentityLinkService _links;
    private readonly UserExperienceService _experience;
    private readonly ParticipationOperatorNotificationService _participationNotifications;
    private readonly InstallLinkingService _installLinking;
    private readonly CampaignSpineService _campaignSpine;
    private readonly CampaignWorkspaceServerPlaneService _workspaceServerPlane;
    private readonly ReadyForTonightService _readyForTonight;
    private readonly KnowledgeFabricService _knowledgeFabric;
    private readonly NexusPanContinuityService _nexusPan;
    private readonly MediaArtifactHorizonsService _mediaHorizons;
    private readonly CommunityCreatorHorizonsService _communityCreatorHorizons;
    private readonly WaveEightHorizonsService _waveEightHorizons;
    private readonly KarmaForgeDiscoveryService _karmaForge;
    private readonly BlackLedgerPublicStatsService _blackLedgerStats;
    private readonly BlackLedgerDispatchService _blackLedgerDispatches;
    private readonly BlackLedgerFactionOnboardingService _blackLedgerFactions;
    private readonly AnarchyPreviewService _anarchyPreview;
    private readonly PublicPackageCatalogService _packageCatalog;
    private readonly PublicCreatorPublicationDiscoveryService _publicCreatorDiscovery;
    private readonly HubPageChromeService _chrome;
    private readonly PublicTrustContentService _trustContent;
    private readonly PublicPrivacyBoundaryService _privacyBoundaries;
    private readonly PublicSignalProjectionService _signalProjection;
    private readonly PublicSignalOperationsService _signalOperations;
    private readonly PublicTrustPulseService _trustPulse;
    private readonly FlagshipReadinessArtifactService _flagshipReadiness;
    private readonly LocalReleaseProofArtifactService _localReleaseProof;
    private readonly ImportRouteParityProofGuardService _importRouteParityProofGuard;
    private readonly SignedInTrustStatusService _signedInTrustStatus;
    private readonly SupportCaseService _supportCases;
    private readonly SupportCasePresentationService _supportPresentation;
    private readonly IConfiguration _configuration;
    private readonly InstallBootstrapTicketService _installBootstrapTickets;
    private readonly PersonalizedInstallScriptService _personalizedInstallScripts;
    private readonly ReleaseUploadTicketService _releaseUploadTickets;
    private readonly WindowsProofInstallerService _windowsProofInstallers;
    private readonly IWebHostEnvironment _webHostEnvironment;
    private readonly ILogger<PublicLandingController> _logger;

    public PublicLandingController(
        PublicLandingService landing,
        PublicFlagshipCoverageService flagshipCoverage,
        PublicReleaseManifestService releases,
        CampaignOsLocalProofService campaignOsProof,
        ReleaseSelectionService releaseSelection,
        PublicActionResolver actions,
        AccountService accounts,
        HubIdentityClient identity,
        IdentityLinkService links,
        UserExperienceService experience,
        ParticipationOperatorNotificationService participationNotifications,
        InstallLinkingService installLinking,
        CampaignSpineService campaignSpine,
        CampaignWorkspaceServerPlaneService workspaceServerPlane,
        ReadyForTonightService readyForTonight,
        KnowledgeFabricService knowledgeFabric,
        NexusPanContinuityService nexusPan,
        MediaArtifactHorizonsService mediaHorizons,
        CommunityCreatorHorizonsService communityCreatorHorizons,
        WaveEightHorizonsService waveEightHorizons,
        KarmaForgeDiscoveryService karmaForge,
        BlackLedgerPublicStatsService blackLedgerStats,
        BlackLedgerDispatchService blackLedgerDispatches,
        BlackLedgerFactionOnboardingService blackLedgerFactions,
        AnarchyPreviewService anarchyPreview,
        PublicPackageCatalogService packageCatalog,
        PublicCreatorPublicationDiscoveryService publicCreatorDiscovery,
        HubPageChromeService chrome,
        PublicTrustContentService trustContent,
        PublicPrivacyBoundaryService privacyBoundaries,
        PublicSignalProjectionService signalProjection,
        PublicSignalOperationsService signalOperations,
        PublicTrustPulseService trustPulse,
        SignedInTrustStatusService signedInTrustStatus,
        SupportCaseService supportCases,
        SupportCasePresentationService supportPresentation,
        IConfiguration configuration,
        InstallBootstrapTicketService installBootstrapTickets,
        PersonalizedInstallScriptService personalizedInstallScripts,
        ReleaseUploadTicketService releaseUploadTickets,
        WindowsProofInstallerService windowsProofInstallers,
        IWebHostEnvironment webHostEnvironment,
        ILogger<PublicLandingController> logger)
    {
        _landing = landing;
        _flagshipCoverage = flagshipCoverage;
        _releases = releases;
        _campaignOsProof = campaignOsProof;
        _releaseSelection = releaseSelection;
        _actions = actions;
        _accounts = accounts;
        _identity = identity;
        _links = links;
        _experience = experience;
        _participationNotifications = participationNotifications;
        _installLinking = installLinking;
        _campaignSpine = campaignSpine;
        _workspaceServerPlane = workspaceServerPlane;
        _readyForTonight = readyForTonight;
        _knowledgeFabric = knowledgeFabric;
        _nexusPan = nexusPan;
        _mediaHorizons = mediaHorizons;
        _communityCreatorHorizons = communityCreatorHorizons;
        _waveEightHorizons = waveEightHorizons;
        _karmaForge = karmaForge;
        _blackLedgerStats = blackLedgerStats;
        _blackLedgerDispatches = blackLedgerDispatches;
        _blackLedgerFactions = blackLedgerFactions;
        _anarchyPreview = anarchyPreview;
        _packageCatalog = packageCatalog;
        _publicCreatorDiscovery = publicCreatorDiscovery;
        _chrome = chrome;
        _trustContent = trustContent;
        _privacyBoundaries = privacyBoundaries;
        _signalProjection = signalProjection;
        _signalOperations = signalOperations;
        _trustPulse = trustPulse;
        _flagshipReadiness = new FlagshipReadinessArtifactService(configuration);
        _localReleaseProof = new LocalReleaseProofArtifactService(configuration);
        _importRouteParityProofGuard = new ImportRouteParityProofGuardService(configuration);
        _signedInTrustStatus = signedInTrustStatus;
        _supportCases = supportCases;
        _supportPresentation = supportPresentation;
        _configuration = configuration;
        _installBootstrapTickets = installBootstrapTickets;
        _personalizedInstallScripts = personalizedInstallScripts;
        _releaseUploadTickets = releaseUploadTickets;
        _windowsProofInstallers = windowsProofInstallers;
        _webHostEnvironment = webHostEnvironment;
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
        var accessPosture = _releaseSelection.BuildPublicAccessPosture(manifest, releaseExperience);
        var assetCatalog = new AssetCatalogViewModel(surface.Assets);
        var nowCards = _landing.CardsForBucket(surface, "whats_real_now");
        var secondaryHeroAction = surface.HeroCtas.FirstOrDefault(static action => string.Equals(action.Emphasis, "secondary", StringComparison.OrdinalIgnoreCase))
            ?? surface.HeroCtas.Skip(1).FirstOrDefault()
            ?? new PublicLandingActionDto("See what works today", "/now", "secondary");
        var primaryHeroAction = surface.HeroCtas.FirstOrDefault(static action => string.Equals(action.Emphasis, "primary", StringComparison.OrdinalIgnoreCase))
            ?? surface.HeroCtas.FirstOrDefault()
            ?? _releaseSelection.BuildPublicPrimaryAction(
                manifest,
                Request.Headers.UserAgent.ToString(),
                authenticated);
        var model = new LandingPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Chummer", surface.Subhead, "/", cancellationToken),
            Surface: surface,
            Assets: assetCatalog,
            Manifest: manifest,
            ReleaseExperience: releaseExperience,
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken),
            PrimaryHeroAction: primaryHeroAction,
            SecondaryHeroAction: secondaryHeroAction,
            Workflows: ResolveCards(_landing.CardsForBucket(surface, "start_here"), assetCatalog, authenticated: false, "/"),
            TrustPillars: _landing.CardsForBucket(surface, "why_trust_it"),
            Lanes: ResolveCards(_landing.CardsForBucket(surface, "choose_your_lane"), assetCatalog, authenticated: false, "/"),
            AvailableToday: ResolveCards(nowCards.Where(static card => PublicSurfaceStatus.IsAvailableToday(card.Badge)).ToArray(), assetCatalog, authenticated: false, "/"),
            PreviewItems: ResolveCards(nowCards.Where(static card => !PublicSurfaceStatus.IsAvailableToday(card.Badge)).ToArray(), assetCatalog, authenticated: false, "/"),
            ComingNext: ResolveCards(_landing.CardsForBucket(surface, "coming_next").Take(3).ToArray(), assetCatalog, authenticated: false, "/"),
            Artifacts: ResolveCards(_landing.CardsForBucket(surface, "featured_artifacts"), assetCatalog, authenticated: false, "/"),
            FlagshipCoverage: _flagshipCoverage.LoadStrip(),
            BlackLedgerStats: _blackLedgerStats.ListHomepageStats(),
            BlackLedgerWorld: _blackLedgerStats.LoadWorldPreview(),
            LatestBlackLedgerDispatch: _blackLedgerDispatches.ListPublishedDispatches().FirstOrDefault(),
            CampaignSpine: await BuildLandingCampaignSpineAsync(cancellationToken),
            AccessPosture: accessPosture);
        return View("~/Views/PublicLanding/Landing.cshtml", model);
    }

    [HttpGet("/what-is-chummer")]
    [Produces("text/html")]
    public async Task<IActionResult> ProductStoryPage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var assetCatalog = new AssetCatalogViewModel(surface.Assets);
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var authenticated = await TryIsAuthenticatedAsync(cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        var model = new StoryPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("What Is Chummer?", surface.ProofLine, "/what-is-chummer", cancellationToken),
            Surface: surface,
            Assets: assetCatalog,
            Workflows: ResolveCards(_landing.CardsForBucket(surface, "start_here"), assetCatalog, authenticated: false, "/what-is-chummer"),
            TrustPillars: _landing.CardsForBucket(surface, "why_trust_it"),
            Lanes: ResolveCards(_landing.CardsForBucket(surface, "choose_your_lane"), assetCatalog, authenticated: false, "/what-is-chummer"),
            ReleaseExperience: releaseExperience,
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
        return View("~/Views/PublicLanding/ProductStory.cshtml", model);
    }

    [HttpGet("/now")]
    [Produces("text/html")]
    public async Task<IActionResult> NowPage(CancellationToken cancellationToken)
    {
        var model = await BuildNowPageModel(
            title: "What Is Real Now",
            description: "Readiness labels and direct evidence for what you can use today.",
            currentPath: "/now",
            cancellationToken: cancellationToken);
        return View("~/Views/PublicLanding/Now.cshtml", model);
    }

    [HttpGet("/horizons")]
    [Produces("text/html")]
    public async Task<IActionResult> HorizonsPage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var assetCatalog = new AssetCatalogViewModel(surface.Assets);
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var authenticated = await TryIsAuthenticatedAsync(cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        var model = new HorizonsPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Coming Next", "The named horizons, their pain, and the payoff they are aiming for.", "/horizons", cancellationToken),
            Surface: surface,
            Assets: assetCatalog,
            Horizons: ResolveCards(_landing.CardsForBucket(surface, "coming_next"), assetCatalog, authenticated: false, "/horizons"),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
        return View("~/Views/PublicLanding/Horizons.cshtml", model);
    }

    [HttpGet("/downloads")]
    [Produces("text/html")]
    public async Task<IActionResult> DownloadsPage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var rawManifest = _releases.LoadManifest();
        var manifest = _releaseSelection.ApplyAccessPolicy(rawManifest);
        var authenticated = await TryIsAuthenticatedAsync(cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        var signedInWindowsBuilds = authenticated
            ? _releaseSelection.BuildSignedInOnlyWindowsOptions(rawManifest)
            : Array.Empty<ReleaseOptionViewModel>();
        var surfacedWindowsArtifactIds = manifest.Downloads
            .Select(static download => download.Id)
            .Concat(signedInWindowsBuilds.Select(static option => option.Artifact.Id))
            .Where(static artifactId => !string.IsNullOrWhiteSpace(artifactId))
            .ToArray();
        var windowsProofInstallers = _windowsProofInstallers.LoadCatalog(
            surfacedWindowsArtifactIds);
        var chrome = await BuildPublicOrAuthenticatedChromeAsync("Downloads", "Install the current preview, compare package types, and keep release integrity in view.", "/downloads", cancellationToken);
        chrome = RebindDownloadsHeaderActions(chrome, releaseExperience);
        var accessPosture = _releaseSelection.BuildPublicAccessPosture(manifest, releaseExperience);
        var model = new DownloadsPageViewModel(
            Chrome: chrome,
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            Manifest: manifest,
            ReleaseExperience: releaseExperience,
            FlagshipCoverage: _flagshipCoverage.LoadStrip(),
            SignedInWindowsBuilds: signedInWindowsBuilds,
            WindowsProofInstallers: windowsProofInstallers,
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken),
            AccessPosture: accessPosture);
        return View("~/Views/PublicLanding/Downloads.cshtml", model);
    }

    [HttpGet("/packages")]
    [Produces("text/html")]
    public async Task<IActionResult> PackagesPage(CancellationToken cancellationToken)
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalSubjectAsync(cancellationToken);
        HubUserDto? user = subject is null ? null : _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        var model = await BuildPackageCatalogPageModel(
            currentPath: "/packages",
            chromeTitle: "Packages",
            chromeDescription: "Browse install, rules, amendment, artifact, and proposal packages with explicit compatibility and follow posture.",
            eyebrow: "Governed package browser",
            heading: "Packages",
            intro: "Package class, compatibility, and vote-or-follow posture stay explicit before installs, amendments, artifacts, or community proposals drift into one blurred shelf.",
            scopeLabel: "Public browser",
            signedInScope: false,
            operatorScope: false,
            detailBasePath: "/packages",
            subject,
            user,
            cancellationToken: cancellationToken);
        return View("~/Views/PublicLanding/Packages.cshtml", model);
    }

    [HttpGet("/packages/{packageId}")]
    [Produces("text/html")]
    public async Task<IActionResult> PackageDetailPage([FromRoute] string packageId, CancellationToken cancellationToken)
    {
        PublicPackageDefinition? package = _packageCatalog.FindPackage(packageId);
        if (package is null)
        {
            return NotFound();
        }

        AuthenticatedHubSubject? subject = await TryGetOptionalSubjectAsync(cancellationToken);
        HubUserDto? user = subject is null ? null : _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        var model = await BuildPackageDetailPageModel(
            package,
            currentPath: $"/packages/{Uri.EscapeDataString(package.PackageId)}",
            scopeLabel: "Public browser",
            secondaryAction: subject is null
                ? new TrustPageActionViewModel("Open mobile rail", "/mobile", "secondary")
                : new TrustPageActionViewModel("Open account packages", "/account/packages", "secondary"),
            subject,
            user,
            cancellationToken: cancellationToken);
        return View("~/Views/PublicLanding/PackageDetail.cshtml", model);
    }

    [HttpGet("/packages/{packageId}/vote")]
    public IActionResult PackageVoteEntry([FromRoute] string packageId)
        => Redirect($"/packages/{Uri.EscapeDataString(packageId)}#community-actions");

    [HttpPost("/packages/{packageId}/vote")]
    [ValidateAntiForgeryToken]
    [Produces("text/html")]
    public async Task<IActionResult> VotePackage([FromRoute] string packageId, CancellationToken cancellationToken)
    {
        PublicPackageDefinition? package = _packageCatalog.FindPackage(packageId);
        if (package is null)
        {
            return NotFound();
        }

        string currentPath = $"/packages/{Uri.EscapeDataString(package.PackageId)}";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            PublicPackageReceipt receipt = _packageCatalog.RecordVote(package.PackageId, subject.SubjectId, user.DisplayName);
            string authProviderFamily = ParticipationOperatorNotificationService.InferAuthProviderFamily(_links.GetSummary(subject.SubjectId));
            await _participationNotifications.NotifyFirstActionIfNeededAsync(
                user,
                subject.Email,
                intentKind: "package",
                entryRoute: $"/packages/{package.PackageId}/vote",
                authProviderFamily,
                cancellationToken);
            return Redirect($"/packages/{Uri.EscapeDataString(package.PackageId)}/vote/{Uri.EscapeDataString(receipt.ReceiptId)}");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Package vote could not confirm the signed-in identity.");
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("/packages/{packageId}/vote/{receiptId}")]
    [Produces("text/html")]
    public Task<IActionResult> PackageVoteReceiptPage([FromRoute] string packageId, [FromRoute] string receiptId, CancellationToken cancellationToken)
        => BuildPackageActionReceiptPage(packageId, receiptId, "vote", cancellationToken);

    [HttpPost("/packages/{packageId}/vote/revoke")]
    [ValidateAntiForgeryToken]
    [Produces("text/html")]
    public async Task<IActionResult> RevokePackageVote([FromRoute] string packageId, CancellationToken cancellationToken)
        => await RevokePackageAction(packageId, "vote", cancellationToken);

    [HttpGet("/packages/{packageId}/follow")]
    public IActionResult PackageFollowEntry([FromRoute] string packageId)
        => Redirect($"/packages/{Uri.EscapeDataString(packageId)}#community-actions");

    [HttpPost("/packages/{packageId}/follow")]
    [ValidateAntiForgeryToken]
    [Produces("text/html")]
    public async Task<IActionResult> FollowPackage([FromRoute] string packageId, CancellationToken cancellationToken)
    {
        PublicPackageDefinition? package = _packageCatalog.FindPackage(packageId);
        if (package is null)
        {
            return NotFound();
        }

        string currentPath = $"/packages/{Uri.EscapeDataString(package.PackageId)}";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            PublicPackageReceipt receipt = _packageCatalog.RecordFollow(package.PackageId, subject.SubjectId, user.DisplayName);
            string authProviderFamily = ParticipationOperatorNotificationService.InferAuthProviderFamily(_links.GetSummary(subject.SubjectId));
            await _participationNotifications.NotifyFirstActionIfNeededAsync(
                user,
                subject.Email,
                intentKind: "package",
                entryRoute: $"/packages/{package.PackageId}/follow",
                authProviderFamily,
                cancellationToken);
            return Redirect($"/packages/{Uri.EscapeDataString(package.PackageId)}/follow/{Uri.EscapeDataString(receipt.ReceiptId)}");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Package follow could not confirm the signed-in identity.");
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("/packages/{packageId}/follow/{receiptId}")]
    [Produces("text/html")]
    public Task<IActionResult> PackageFollowReceiptPage([FromRoute] string packageId, [FromRoute] string receiptId, CancellationToken cancellationToken)
        => BuildPackageActionReceiptPage(packageId, receiptId, "follow", cancellationToken);

    [HttpPost("/packages/{packageId}/follow/revoke")]
    [ValidateAntiForgeryToken]
    [Produces("text/html")]
    public async Task<IActionResult> RevokePackageFollow([FromRoute] string packageId, CancellationToken cancellationToken)
        => await RevokePackageAction(packageId, "follow", cancellationToken);

    [HttpGet("/account/packages")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountPackagesPage(CancellationToken cancellationToken)
    {
        const string currentPath = "/account/packages";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var model = await BuildPackageCatalogPageModel(
                currentPath: currentPath,
                chromeTitle: "Account packages",
                chromeDescription: "Track package follows, votes, and package return posture from the same signed-in rail as installs and support.",
                eyebrow: "Signed-in package rail",
                heading: "Account packages",
                intro: "Votes, follows, and package return posture stay attached to the same account rail that already owns installs, recovery, and support follow-through.",
                scopeLabel: "Account rail",
                signedInScope: true,
                operatorScope: false,
                detailBasePath: "/account/packages",
                subject,
                user,
                cancellationToken);
            return View("~/Views/PublicLanding/Packages.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Account packages could not confirm the signed-in identity.");
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("/account/packages/{packageId}")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountPackageDetailPage([FromRoute] string packageId, CancellationToken cancellationToken)
    {
        PublicPackageDefinition? package = _packageCatalog.FindPackage(packageId);
        if (package is null)
        {
            return NotFound();
        }

        string currentPath = $"/account/packages/{Uri.EscapeDataString(package.PackageId)}";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var model = await BuildPackageDetailPageModel(
                package,
                currentPath: currentPath,
                scopeLabel: "Account rail",
                secondaryAction: new TrustPageActionViewModel("Open public package browser", "/packages", "secondary"),
                subject,
                user,
                cancellationToken);
            return View("~/Views/PublicLanding/PackageDetail.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Account package detail could not confirm the signed-in identity.");
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("/admin/packages")]
    [Produces("text/html")]
    public async Task<IActionResult> AdminPackagesPage(CancellationToken cancellationToken)
    {
        const string currentPath = "/admin/packages";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var model = await BuildPackageCatalogPageModel(
                currentPath: currentPath,
                chromeTitle: "Package operator summary",
                chromeDescription: "Bounded operator summary of package classes, compatibility posture, and first-party vote or follow receipts.",
                eyebrow: "Bounded operator summary",
                heading: "Package operator summary",
                intro: "Operator view keeps public package class posture, compatibility pressure, and first-party receipts together without turning the package browser into a hidden admin-only surface.",
                scopeLabel: "Operator summary",
                signedInScope: true,
                operatorScope: true,
                detailBasePath: "/packages",
                subject,
                user,
                cancellationToken);
            return View("~/Views/PublicLanding/Packages.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Package operator summary could not confirm the signed-in identity.");
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("/mobile")]
    [Produces("text/html")]
    public async Task<IActionResult> MobileProjectionPage(CancellationToken cancellationToken)
    {
        var model = await BuildMobileProjectionPageModel(
            currentPath: "/mobile",
            chromeTitle: "Mobile and PWA",
            chromeDescription: "Phone, tablet, and installable play entry with reconnect posture and role-aware routes.",
            eyebrow: "Mobile public rail",
            heading: "Mobile and PWA entry",
            intro: "Installability, reconnect posture, and player, GM, or observer entry stay on first-party routes instead of leaking into fallback docs or legacy aliases.",
            currentRoleKey: "player",
            primaryAction: new TrustPageActionViewModel("Open play shell", "/play", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open downloads", "/downloads", "secondary"),
            cancellationToken: cancellationToken);
        return View("~/Views/PublicLanding/MobileProjection.cshtml", model);
    }

    [HttpGet("/pwa")]
    public IActionResult PwaProjectionAlias()
        => Redirect("/mobile");

    [HttpGet("/play")]
    [Produces("text/html")]
    public async Task<IActionResult> PlayProjectionPage([FromQuery] string? role, CancellationToken cancellationToken)
    {
        string currentRoleKey = NormalizePlayRole(role);
        string currentRoleLabel = ResolvePlayRoleLabel(currentRoleKey);
        string currentPath = string.Equals(currentRoleKey, "player", StringComparison.OrdinalIgnoreCase)
            ? "/play"
            : $"/play?role={Uri.EscapeDataString(currentRoleKey)}";
        var model = await BuildMobileProjectionPageModel(
            currentPath: currentPath,
            chromeTitle: $"{currentRoleLabel} play shell",
            chromeDescription: "Role-aware mobile and tablet entry with reconnect, continuity, and first-party route ownership.",
            eyebrow: "Play shell",
            heading: $"{currentRoleLabel} entry",
            intro: "The play shell keeps role entry, reconnect expectations, and current continuity posture visible without pretending the mobile route replaces installs, support, or deeper campaign work.",
            currentRoleKey: currentRoleKey,
            primaryAction: new TrustPageActionViewModel("Open mobile and PWA", "/mobile", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open downloads", "/downloads", "secondary"),
            cancellationToken: cancellationToken);
        return View("~/Views/PublicLanding/MobileProjection.cshtml", model);
    }

    [HttpGet("/player")]
    public IActionResult PlayerProjectionAlias()
        => Redirect("/play?role=player");

    [HttpGet("/gm")]
    public IActionResult GmProjectionAlias()
        => Redirect("/play?role=gm");

    [HttpGet("/observer")]
    public IActionResult ObserverProjectionAlias()
        => Redirect("/play?role=observer");

    [HttpGet("/anarchy")]
    [Produces("text/html")]
    public async Task<IActionResult> AnarchyOverviewPage(CancellationToken cancellationToken)
    {
        var model = await BuildAnarchyPageModel(
            currentPath: "/anarchy",
            currentSection: "overview",
            eyebrow: "Dedicated ruleset preview",
            heading: "Shadowrun Anarchy",
            intro: "A dedicated rules-light lane for mobile play, dispatches, faction consequence, and fast continuity. This is a playable preview, not full book-level rules completeness.",
            primaryAction: new TrustPageActionViewModel("Open Anarchy play shell", "/play/anarchy", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open Anarchy ledger lane", "/ledger/anarchy", "secondary"),
            cancellationToken: cancellationToken);
        return View("~/Views/PublicLanding/Anarchy.cshtml", model);
    }

    [HttpGet("/play/anarchy")]
    [Produces("text/html")]
    public async Task<IActionResult> AnarchyPlayPage(CancellationToken cancellationToken)
    {
        var model = await BuildAnarchyPageModel(
            currentPath: "/play/anarchy",
            currentSection: "play",
            eyebrow: "Rules-light play shell",
            heading: "Anarchy play shell",
            intro: "This route keeps a one-page runner sheet, continuity cues, and explainable export in one first-party play lane without pretending to be full dense-builder parity.",
            primaryAction: new TrustPageActionViewModel("Open mobile and PWA", "/mobile", "primary"),
            secondaryAction: new TrustPageActionViewModel("View dispatches through the Anarchy lens", "/ledger/dispatches?ruleset=anarchy", "secondary"),
            cancellationToken: cancellationToken);
        return View("~/Views/PublicLanding/Anarchy.cshtml", model);
    }

    [HttpGet("/anarchy/export/runner.json")]
    [Produces("application/json")]
    public IActionResult AnarchyExportJson()
        => Content(_waveEightHorizons.BuildAnarchyExportJson(), "application/json");

    [HttpGet("/anarchy/receipts/explain.json")]
    [Produces("application/json")]
    public IActionResult AnarchyExplainReceiptJson()
        => Content(_waveEightHorizons.BuildAnarchyExplainJson(), "application/json");

    [HttpGet("/downloads/release-upload")]
    [Produces("text/html")]
    public async Task<IActionResult> ReleaseUploadPage(CancellationToken cancellationToken)
    {
        const string currentPath = "/downloads/release-upload";
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            if (!ReleaseUploadAccessPolicy.CanAccess(subject.Email))
            {
                return NotFound();
            }

            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var ticket = _releaseUploadTickets.Issue(subject);
            var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated: true);
            string? templatePath = ResolveWebAssetPath("artifacts", "mac-codex-release-pipeline", "bootstrap.sh");
            if (string.IsNullOrWhiteSpace(templatePath))
            {
                return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "release upload bootstrap template is unavailable.");
            }

            string bootstrapUrl = BuildAbsoluteUrl("/downloads/release-upload/bootstrap.sh");
            string bootstrapTemplate = System.IO.File.ReadAllText(templatePath);
            string command = BuildReleaseUploadBootstrapCommand(
                bootstrapUrl,
                ComputeSha256Hex(bootstrapTemplate),
                ReleaseUploadTicketEnvironmentVariable,
                ticket.Ticket);
            var model = new ReleaseUploadPageViewModel(
                Chrome: _chrome.BuildAuthenticatedChrome(
                    "Release upload handoff",
                    "Mint a short-lived upload handoff code and hand a digest-pinned, self-contained bootstrap command to the Mac or Windows release runner.",
                    currentPath,
                    user.DisplayName,
                    user.Email),
                Heading: "Signed-in release upload handoff",
                Summary: "This page mints a short-lived upload handoff code and embeds it only in the signed-in bootstrap command so non-interactive Mac release runners can build, publish, and verify without stopping for a second secret paste.",
                Command: command,
                HandoffCode: ticket.Ticket,
                BootstrapUrl: bootstrapUrl,
                TicketExpiresAtUtc: ticket.Claims.ExpiresAtUtc,
                UploadUrl: BuildAbsoluteUrl("/api/internal/releases/bundles"),
                ReadmeUrl: BuildAbsoluteUrl("/artifacts/mac-codex-release-pipeline/readme.md"),
                VerifyUrl: BuildAbsoluteUrl("/downloads/RELEASE_CHANNEL.generated.json"),
                WindowsUploadNote: "Windows bundles use the same upload endpoint and the same signed-in claim-code return path once the signed installer, startup-smoke receipts, and promotion evidence are present.",
                TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
                SignedInStatus: _signedInTrustStatus.Build(user, manifest, releaseExperience));
            return View("~/Views/PublicLanding/ReleaseUpload.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Release upload handoff could not confirm the signed-in identity.");
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("/downloads/release-upload/bootstrap.sh")]
    [Produces("text/x-shellscript", "application/problem+json")]
    public IActionResult ReleaseUploadBootstrapScript([FromQuery] string? ticket, [FromQuery] string? apiToken)
    {
        string? templatePath = ResolveWebAssetPath("artifacts", "mac-codex-release-pipeline", "bootstrap.sh");
        if (string.IsNullOrWhiteSpace(templatePath))
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "release upload bootstrap template is unavailable.");
        }

        Response.Headers["Cache-Control"] = "private, no-store";
        string bootstrapScript = System.IO.File.ReadAllText(templatePath);
        string? releaseUploadAuth = ResolveReleaseUploadCommandAuth(
            ticket,
            apiToken,
            out string releaseUploadAuthEnvironmentVariable,
            out IActionResult? failure);
        if (failure is not null)
        {
            return failure;
        }

        if (!string.IsNullOrWhiteSpace(releaseUploadAuth))
        {
            bootstrapScript =
                "# Release upload authorization was attached by the signed-in chummer.run handoff.\n" +
                "export " + releaseUploadAuthEnvironmentVariable + "=" + SingleQuoteShellValue(releaseUploadAuth) + "\n" +
                bootstrapScript;
        }

        return Content(bootstrapScript, "text/x-shellscript; charset=utf-8", Encoding.UTF8);
    }

    [HttpGet("/downloads/release-upload/bootstrap.command")]
    [Produces("text/x-shellscript", "application/problem+json")]
    public async Task<IActionResult> ReleaseUploadBootstrapCommand(
        [FromQuery] string? ticket,
        [FromQuery] string? apiToken,
        CancellationToken cancellationToken)
    {
        string? releaseUploadAuth = ResolveReleaseUploadCommandAuth(
            ticket,
            apiToken,
            out string releaseUploadAuthEnvironmentVariable,
            out IActionResult? failure);
        if (failure is not null)
        {
            return failure;
        }

        if (string.IsNullOrWhiteSpace(releaseUploadAuth))
        {
            try
            {
                var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
                if (!ReleaseUploadAccessPolicy.CanAccess(subject.Email))
                {
                    return NotFound();
                }

                releaseUploadAuth = _releaseUploadTickets.Issue(subject).Ticket;
                releaseUploadAuthEnvironmentVariable = ReleaseUploadTicketEnvironmentVariable;
            }
            catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
            {
                return Problem(
                    statusCode: StatusCodes.Status401Unauthorized,
                    detail: "Sign in at /downloads/release-upload or provide a valid ticket/apiToken query value before fetching the release upload command.");
            }
            catch (HubRequestAuthException ex)
            {
                _logger.LogWarning(ex, "Release upload command could not confirm the signed-in identity.");
                return Problem(statusCode: ex.StatusCode, detail: ex.Message);
            }
        }

        string? templatePath = ResolveWebAssetPath("artifacts", "mac-codex-release-pipeline", "bootstrap.sh");
        if (string.IsNullOrWhiteSpace(templatePath))
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "release upload bootstrap template is unavailable.");
        }

        string bootstrapUrl = BuildAbsoluteUrl("/downloads/release-upload/bootstrap.sh");
        string bootstrapTemplate = System.IO.File.ReadAllText(templatePath);
        string command = BuildReleaseUploadBootstrapCommand(
            bootstrapUrl,
            ComputeSha256Hex(bootstrapTemplate),
            releaseUploadAuthEnvironmentVariable,
            releaseUploadAuth);

        Response.Headers["Cache-Control"] = "private, no-store";
        return Content(command + "\n", "text/x-shellscript; charset=utf-8", Encoding.UTF8);
    }

    private string? ResolveReleaseUploadCommandAuth(
        string? ticket,
        string? apiToken,
        out string environmentVariable,
        out IActionResult? failure)
    {
        environmentVariable = ReleaseUploadTicketEnvironmentVariable;
        failure = null;

        string cleanToken = (apiToken ?? string.Empty).Trim();
        if (!string.IsNullOrWhiteSpace(cleanToken))
        {
            string expectedToken = (_configuration["FLEET_INTERNAL_API_TOKEN"] ?? string.Empty).Trim();
            if (string.IsNullOrWhiteSpace(expectedToken) || !FixedTimeEquals(cleanToken, expectedToken))
            {
                failure = Problem(
                    statusCode: StatusCodes.Status401Unauthorized,
                    detail: "The supplied release upload apiToken is not valid for this chummer.run instance.");
                return null;
            }

            environmentVariable = ReleaseUploadTokenEnvironmentVariable;
            return cleanToken;
        }

        string cleanTicket = (ticket ?? string.Empty).Trim();
        if (!string.IsNullOrWhiteSpace(cleanTicket))
        {
            if (!_releaseUploadTickets.TryValidate(cleanTicket, out _))
            {
                failure = Problem(
                    statusCode: StatusCodes.Status401Unauthorized,
                    detail: "The supplied release upload ticket is expired or invalid. Refresh /downloads/release-upload and copy a new command.");
                return null;
            }

            return cleanTicket;
        }

        return null;
    }

    private string? ResolveWebAssetPath(params string[] relativeSegments)
    {
        static string Combine(string root, IEnumerable<string> segments)
        {
            string path = root;
            foreach (string segment in segments)
            {
                path = Path.Combine(path, segment);
            }

            return path;
        }

        string? contentRoot = _webHostEnvironment.ContentRootPath;
        string?[] roots =
        [
            _webHostEnvironment.WebRootPath,
            Path.Combine(AppContext.BaseDirectory, "wwwroot"),
            string.IsNullOrWhiteSpace(contentRoot) ? null : Path.Combine(contentRoot, "wwwroot"),
            string.IsNullOrWhiteSpace(contentRoot) ? null : Path.Combine(contentRoot, "Chummer.Run.Api", "wwwroot")
        ];

        foreach (string? root in roots)
        {
            if (string.IsNullOrWhiteSpace(root))
            {
                continue;
            }

            string candidate = Combine(root, relativeSegments);
            if (System.IO.File.Exists(candidate))
            {
                return candidate;
            }
        }

        return null;
    }

    private static bool FixedTimeEquals(string left, string right)
    {
        ReadOnlySpan<byte> leftBytes = Encoding.UTF8.GetBytes(left);
        ReadOnlySpan<byte> rightBytes = Encoding.UTF8.GetBytes(right);
        if (leftBytes.Length != rightBytes.Length)
        {
            return false;
        }

        return CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }

    [HttpGet("/downloads/install/{artifactId}")]
    [HttpHead("/downloads/install/{artifactId}")]
    [Produces("text/html")]
    public async Task<IActionResult> DownloadDispatchPage([FromRoute] string artifactId, CancellationToken cancellationToken)
    {
        var (manifest, artifact) = ResolveInstallDispatchArtifact(artifactId);
        if (artifact is null)
        {
            WindowsProofInstallerRecord? proofInstaller = _windowsProofInstallers.FindByArtifactId(artifactId);
            if (proofInstaller is null)
            {
                return NotFound();
            }

            return await BuildWindowsProofDispatchPageAsync(artifactId, proofInstaller, manifest, cancellationToken);
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var release = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated: true);
            var option = _releaseSelection.BuildOption(manifest, artifact, authenticated: true, recommended: false);
            var bootstrapScriptDownload = _releaseSelection.UsesGuidedBootstrapScript(artifact);
            var bootstrapPlatform = bootstrapScriptDownload ? ResolveGuidedBootstrapPlatform(artifact) : null;
            var guidedBootstrapArtifacts = bootstrapScriptDownload
                ? ResolveGuidedBootstrapArtifacts(manifest, artifact)
                : Array.Empty<PublicReleaseArtifactDto>();
            var dispatch = bootstrapScriptDownload
                ? null
                : _installLinking.IssueDownload(manifest, artifact, user.UserId, subject.SubjectId);
            var personalizedMacInstallScript = bootstrapScriptDownload && string.Equals(bootstrapPlatform, "macos", StringComparison.Ordinal)
                ? IssuePersonalizedMacInstallScript(
                    manifest,
                    artifact,
                    guidedBootstrapArtifacts,
                    user.UserId,
                    subject.SubjectId)
                : null;
            var bootstrapTicket = bootstrapScriptDownload && !string.Equals(bootstrapPlatform, "macos", StringComparison.Ordinal)
                ? _installBootstrapTickets.Issue(
                    artifact.Id,
                    guidedBootstrapArtifacts.Select(candidate => candidate.Id),
                    user.UserId,
                    subject.SubjectId)
                : null;
            var bootstrapQuery = bootstrapTicket is null
                ? QueryString.Empty
                : QueryString.Create("ticket", bootstrapTicket.Ticket);
            var bootstrapScriptPath = bootstrapScriptDownload && bootstrapPlatform is not null
                ? string.Equals(bootstrapPlatform, "macos", StringComparison.Ordinal)
                    ? BuildPersonalizedMacBootstrapScriptPath(
                        personalizedMacInstallScript!.ScriptId,
                        personalizedMacInstallScript.Link.RenderedScriptSha256)
                    : BuildBootstrapScriptPath(artifact.Id, bootstrapPlatform)
                : null;
            var bootstrapScriptHref = bootstrapScriptPath is null
                ? null
                : bootstrapTicket is null
                    ? bootstrapScriptPath
                    : $"{bootstrapScriptPath}{bootstrapQuery}";
            var rawDownloadHref = option.DirectFileHref;
            var downloadHref = bootstrapScriptDownload
                ? bootstrapScriptHref!
                : rawDownloadHref;
            var downloadLabel = bootstrapScriptDownload
                ? BuildBootstrapFallbackDownloadLabel(bootstrapPlatform)
                : "Start download again";
            var dispatchSummary = bootstrapScriptDownload
                ? BuildBootstrapDispatchSummary(bootstrapPlatform)
                : release.SignedInDispatchSummary;
            var dispatchNote = bootstrapScriptDownload
                ? BuildBootstrapDispatchNote(bootstrapPlatform)
                : "This handoff keeps the published installer unchanged while attaching the install relationship to your account through a short-lived install ticket.";
            var steps = bootstrapScriptDownload
                ? BuildBootstrapSteps(bootstrapPlatform)
                : release.SignedInDispatchSteps;
            var supportHref = DesktopInstallRail.BuildSupportHref(
                artifact,
                manifest,
                installationId: null,
                bootstrapScriptDownload);
            var terminalInstallCommand = bootstrapScriptDownload && bootstrapTicket is not null
                ? BuildBootstrapInstallCommand(
                    bootstrapPlatform,
                    BuildAbsoluteUrl(
                        BuildBootstrapScriptPath(artifact.Id, bootstrapPlatform!),
                        QueryString.Create("ticket", bootstrapTicket.Ticket)))
                : bootstrapScriptDownload
                    && personalizedMacInstallScript is not null
                    && string.Equals(bootstrapPlatform, "macos", StringComparison.Ordinal)
                    ? BuildBootstrapInstallCommand(
                        bootstrapPlatform,
                        BuildAbsoluteUrl(bootstrapScriptPath!),
                        personalizedMacInstallScript.Link.RenderedScriptSha256)
                : bootstrapScriptDownload && bootstrapScriptPath is not null
                    ? BuildBootstrapInstallCommand(
                        bootstrapPlatform,
                        BuildAbsoluteUrl(bootstrapScriptPath))
                : null;
            var model = new DownloadDispatchPageViewModel(
                Chrome: _chrome.BuildAuthenticatedChrome("Download handoff", "Start the installer download and keep the install linked to this account from the first launch.", "/downloads", user.DisplayName, user.Email),
                Eyebrow: "Signed-in download",
                Heading: bootstrapScriptDownload
                    ? BuildDispatchHeading(release.SignedInDispatchHeading, bootstrapPlatform)
                    : release.SignedInDispatchHeading,
                Summary: dispatchSummary,
                DispatchNote: dispatchNote,
                ArtifactTitle: option.Title,
                ArtifactSupportLine: option.SupportLine,
                DownloadHref: downloadHref,
                DownloadLabel: downloadLabel,
                TerminalInstallCommand: terminalInstallCommand,
                BootstrapCommandLabel: BuildBootstrapCommandLabel(bootstrapPlatform),
                BootstrapCommandIntro: BuildBootstrapCommandIntro(bootstrapPlatform),
                BootstrapCommandNote: BuildBootstrapCommandNote(bootstrapPlatform),
                CopyCommandLabel: BuildCopyCommandLabel(bootstrapPlatform),
                CompactDispatchLayout: bootstrapScriptDownload && string.Equals(bootstrapPlatform, "macos", StringComparison.Ordinal),
                BootstrapFeatureCards: BuildBootstrapFeatureCards(bootstrapPlatform),
                AutoStartDownload: !bootstrapScriptDownload,
                BootstrapScriptDownload: bootstrapScriptDownload,
                PromoteSecondaryDownload: false,
                SecondaryDownloadHref: bootstrapScriptDownload ? rawDownloadHref : null,
                SecondaryDownloadLabel: bootstrapScriptDownload ? BuildBootstrapSecondaryDownloadLabel(bootstrapPlatform) : null,
                AccountHref: "/account/access",
                AccountLabel: "Open Devices and access",
                HelpHref: release.InstallHelpHref,
                HelpLabel: release.InstallHelpLabel,
                SupportHref: supportHref,
                SupportLabel: "Open tracked support",
                Display: release.Display,
                Channel: manifest.Channel,
                Version: manifest.Version,
                CurrentReleaseSummary: bootstrapScriptDownload
                    ? BuildBootstrapCurrentReleaseSummary(bootstrapPlatform, guidedBootstrapArtifacts)
                    : option.PlatformLabel,
                PlatformLabel: option.PlatformLabel,
                HeadLabel: option.HeadLabel,
                ClaimExchangeUrl: bootstrapScriptDownload ? null : $"/downloads/install/{Uri.EscapeDataString(artifactId)}/continue.json",
                ClaimCode: dispatch?.ClaimTicket?.ClaimCode,
                ClaimCodeExpiresAtUtc: dispatch?.ClaimTicket?.ExpiresAtUtc,
                Steps: steps,
                TrustPulse: BuildPublicTrustPulsePanel(manifest, release),
                SignedInStatus: _signedInTrustStatus.Build(user, manifest, release));
            ApplyNoStoreHeaders(Response.Headers);
            return View("~/Views/PublicLanding/DownloadDispatch.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/auth/google/start?next={Uri.EscapeDataString($"/downloads/install/{artifactId}")}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Downloads handoff could not confirm the signed-in identity.");
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    private async Task<IActionResult> BuildWindowsProofDispatchPageAsync(
        string artifactId,
        WindowsProofInstallerRecord proofInstaller,
        PublicReleaseManifestDto manifest,
        CancellationToken cancellationToken)
    {
        bool authenticated = await TryIsAuthenticatedAsync(cancellationToken);
        var chrome = await BuildPublicOrAuthenticatedChromeAsync(
            "Supplemental Windows installer",
            "Direct Windows installer for verification and support outside the main recommended shelf.",
            $"/downloads/install/{artifactId}",
            cancellationToken: cancellationToken);
        var release = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        string headLabel = string.Equals(proofInstaller.Head, "blazor-desktop", StringComparison.OrdinalIgnoreCase)
            ? "Blazor Desktop"
            : "Avalonia Desktop";
        var model = new DownloadDispatchPageViewModel(
            Chrome: chrome,
            Eyebrow: "Supplemental Windows installer",
            Heading: $"{headLabel} Windows setup",
            Summary: "This direct Windows installer stays available for verification and support when this specific build is not on the main recommended shelf.",
            DispatchNote: "Use this route only when support, verification, or a specific proof flow points to this installer.",
            ArtifactTitle: $"{headLabel} Windows x64 installer",
            ArtifactSupportLine: "Direct Windows installer for verification and support.",
            DownloadHref: $"/downloads/install/{Uri.EscapeDataString(artifactId)}/proof",
            DownloadLabel: "Download installer",
            TerminalInstallCommand: null,
            BootstrapCommandLabel: null,
            BootstrapCommandIntro: null,
            BootstrapCommandNote: null,
            CopyCommandLabel: "Copy command",
            CompactDispatchLayout: false,
            BootstrapFeatureCards: Array.Empty<DownloadDispatchFeatureCardViewModel>(),
            AutoStartDownload: true,
            BootstrapScriptDownload: false,
            PromoteSecondaryDownload: false,
            SecondaryDownloadHref: proofInstaller.DownloadUrl,
            SecondaryDownloadLabel: "Direct file mirror",
            AccountHref: "/downloads",
            AccountLabel: "Back to downloads",
            HelpHref: release.InstallHelpHref,
            HelpLabel: release.InstallHelpLabel,
            SupportHref: QueryHelpers.AddQueryString(
                "/contact",
                new Dictionary<string, string?>
                {
                    ["kind"] = SupportCaseKinds.InstallHelp,
                    ["title"] = $"{headLabel} Windows supplemental install help",
                    ["summary"] = "Windows supplemental installer needs help on this device.",
                    ["detail"] = "The Windows supplemental installer path needs help on this device. Keep support on the same install rail.",
                    ["applicationVersion"] = manifest.Version,
                    ["releaseChannel"] = manifest.Channel,
                    ["headId"] = proofInstaller.Head,
                    ["platform"] = "windows",
                    ["arch"] = "x64"
                }),
            SupportLabel: "Open tracked support",
            Display: release.Display,
            Channel: manifest.Channel,
            Version: manifest.Version,
            CurrentReleaseSummary: "Windows stays on a supplemental verification rail here; use the main downloads shelf for the recommended setup when it is promoted there.",
            PlatformLabel: "Windows x64",
            HeadLabel: headLabel,
            ClaimExchangeUrl: null,
            ClaimCode: null,
            ClaimCodeExpiresAtUtc: null,
            Steps:
            [
                "Download the supplemental installer directly from this page.",
                "Install and validate the current Windows build.",
                "Use install help and support if this specific Windows installer needs follow-through."
            ],
            TrustPulse: BuildPublicTrustPulsePanel(manifest, release),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, release, cancellationToken));
        ApplyNoStoreHeaders(Response.Headers);
        return View("~/Views/PublicLanding/DownloadDispatch.cshtml", model);
    }

    private static void ApplyNoStoreHeaders(IHeaderDictionary headers)
    {
        headers["Cache-Control"] = "private, no-store, max-age=0";
        headers["Pragma"] = "no-cache";
        headers["Expires"] = "0";
    }

    [HttpGet("/downloads/install/{artifactId}/bootstrap.command")]
    [Produces("text/x-shellscript", "application/problem+json")]
    public async Task<IActionResult> DownloadDispatchBootstrapScript([FromRoute] string artifactId, CancellationToken cancellationToken)
    {
        var (context, failure) = await TryBuildGuidedBootstrapContextAsync(artifactId, "macos", cancellationToken);
        if (failure is not null)
        {
            return failure;
        }

        MacInstallBootstrapArtifact[] scriptArtifacts = BuildMacInstallBootstrapArtifacts(
            context!.Manifest,
            context.Artifacts,
            context.UserId,
            context.SubjectId);

        string script = RenderMacInstallBootstrapScript(
            scriptArtifacts,
            BuildAbsoluteUrl("/"),
            BuildAbsoluteUrl("/account/access"),
            BuildAbsoluteUrl("/downloads"),
            BuildAbsoluteUrl("/help"));

        Response.Headers["Cache-Control"] = "private, no-store";
        return File(
            Encoding.UTF8.GetBytes(script),
            "text/x-shellscript; charset=utf-8",
            BuildMacBootstrapFileName(context.Artifact));
    }

    [HttpGet("/install-{scriptId:minlength(24):maxlength(24)}.sh")]
    [HttpGet("/install-{scriptId:minlength(24):maxlength(24)}-{renderedScriptSha256:minlength(64):maxlength(64)}.sh")]
    [Produces("text/x-shellscript", "application/problem+json")]
    public IActionResult DownloadDispatchPersonalizedMacBootstrapScript(
        [FromRoute] string scriptId,
        [FromRoute] string? renderedScriptSha256 = null)
    {
        PersonalizedInstallScriptConsumeResult consume = _personalizedInstallScripts.Resolve(scriptId, renderedScriptSha256);
        if (consume.Status != PersonalizedInstallScriptConsumeStatus.Success || consume.Link is null)
        {
            Response.Headers["Cache-Control"] = "private, no-store";
            if (consume.Status == PersonalizedInstallScriptConsumeStatus.DigestMismatch)
            {
                return NotFound();
            }

            return StatusCode(
                StatusCodes.Status410Gone,
                new
                {
                    error = consume.Status switch
                    {
                        PersonalizedInstallScriptConsumeStatus.Expired => "install_command_expired",
                        PersonalizedInstallScriptConsumeStatus.Revoked => "install_command_revoked",
                        _ => "install_command_unavailable",
                    },
                    message = "The install command expired or is no longer available. Re-open the signed-in downloads handoff and copy a fresh install command."
                });
        }

        var (manifest, artifact) = ResolveInstallDispatchArtifact(consume.Link.ArtifactId);
        if (artifact is null
            || !string.Equals(consume.Link.Platform, "macos", StringComparison.OrdinalIgnoreCase)
            || !_releaseSelection.UsesGuidedBootstrapScript(artifact)
            || !string.Equals(ResolveGuidedBootstrapPlatform(artifact), "macos", StringComparison.OrdinalIgnoreCase))
        {
            Response.Headers["Cache-Control"] = "private, no-store";
            return NotFound();
        }

        IReadOnlyList<GuidedBootstrapArtifact> guidedArtifacts = ResolveGuidedBootstrapArtifacts(manifest, artifact)
            .Where(candidate => consume.Link.AllowedArtifactIds.Contains(candidate.Id, StringComparer.OrdinalIgnoreCase))
            .Select(candidate => new GuidedBootstrapArtifact(
                ArtifactId: candidate.Id,
                HeadId: candidate.Head ?? string.Empty,
                Title: BuildGuidedBootstrapArtifactTitle(candidate),
                ShortLabel: BuildGuidedBootstrapShortLabel(candidate),
                DownloadUrl: BuildAbsoluteUrl($"/downloads/file/{Uri.EscapeDataString(candidate.Id)}"),
                ClaimUrl: string.Empty,
                Sha256: candidate.Sha256,
                PackageName: candidate.FileName ?? Path.GetFileName(candidate.Url),
                Architecture: candidate.Arch,
                LaunchAfterInstall: string.Equals(candidate.Id, artifact.Id, StringComparison.OrdinalIgnoreCase),
                InstallFolderName: ResolveGuidedBootstrapInstallFolderName(candidate),
                ExecutableName: ResolveGuidedBootstrapExecutableName(candidate),
                LauncherName: ResolveGuidedBootstrapLauncherName(candidate),
                DesktopEntryName: ResolveGuidedBootstrapDesktopEntryName(candidate)))
            .ToArray();
        if (guidedArtifacts.Count == 0)
        {
            Response.Headers["Cache-Control"] = "private, no-store";
            return Problem(
                statusCode: StatusCodes.Status503ServiceUnavailable,
                detail: "no macOS bootstrap artifacts are available for this personalized handoff.");
        }

        MacInstallBootstrapArtifact[] scriptArtifacts = BuildMacInstallBootstrapArtifacts(
            manifest,
            guidedArtifacts,
            consume.Link.UserId,
            consume.Link.SubjectId);

        string script = !string.IsNullOrWhiteSpace(consume.Link.RenderedScript)
            ? consume.Link.RenderedScript
            : RenderMacInstallBootstrapScript(
                scriptArtifacts,
                BuildAbsoluteUrl("/"),
                BuildAbsoluteUrl("/account/access"),
                BuildAbsoluteUrl("/downloads"),
                BuildAbsoluteUrl("/help"));

        Response.Headers["Cache-Control"] = "private, no-store";
        return File(
            Encoding.UTF8.GetBytes(script),
            "text/x-shellscript; charset=utf-8",
            BuildMacBootstrapFileName(artifact));
    }

    [HttpGet("/downloads/install/{artifactId}/bootstrap.sh")]
    [Produces("text/x-shellscript", "application/problem+json")]
    public async Task<IActionResult> DownloadDispatchLinuxBootstrapScript([FromRoute] string artifactId, CancellationToken cancellationToken)
    {
        var (context, failure) = await TryBuildGuidedBootstrapContextAsync(artifactId, "linux", cancellationToken);
        if (failure is not null)
        {
            return failure;
        }

        string script = RenderLinuxInstallBootstrapScript(
            context!.Artifacts,
            BuildAbsoluteUrl("/"),
            BuildAbsoluteUrl("/account/access"),
            BuildAbsoluteUrl("/downloads"),
            BuildAbsoluteUrl("/help"));

        Response.Headers["Cache-Control"] = "private, no-store";
        return File(
            Encoding.UTF8.GetBytes(script),
            "text/x-shellscript; charset=utf-8",
            BuildLinuxBootstrapFileName(context.Artifact));
    }

    [HttpGet("/downloads/install/{artifactId}/claim.json")]
    [HttpGet("/downloads/install/{artifactId}/continue.json")]
    [Produces("application/json")]
    public async Task<IActionResult> DownloadDispatchBootstrapClaim([FromRoute] string artifactId, CancellationToken cancellationToken)
    {
        var (manifest, artifact) = ResolveInstallDispatchArtifact(artifactId);
        if (artifact is null)
        {
            return NotFound();
        }

        string? userId;
        string? subjectId;
        bool guidedBootstrapDownload = _releaseSelection.UsesGuidedBootstrapScript(artifact);

        if (guidedBootstrapDownload)
        {
            string? bootstrapTicket = Request.Query["ticket"].ToString();
            if (!_installBootstrapTickets.TryValidateForArtifact(bootstrapTicket, artifact.Id, out InstallBootstrapTicketClaims? ticketClaims)
                || ticketClaims is null)
            {
                Response.Headers["Cache-Control"] = "private, no-store";
                return Unauthorized(new
                {
                    error = "invalid_or_expired_install_ticket",
                    message = "The install command expired. Re-open the signed-in downloads handoff and copy a fresh install command."
                });
            }

            userId = ticketClaims.UserId;
            subjectId = ticketClaims.SubjectId;
        }
        else
        {
            try
            {
                var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
                var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
                userId = user.UserId;
                subjectId = subject.SubjectId;
            }
            catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
            {
                Response.Headers["Cache-Control"] = "private, no-store";
                return Unauthorized(new
                {
                    error = "install_session_auth_required",
                    message = "Sign in again to refresh install recovery for this setup download."
                });
            }
        }

        var dispatch = _installLinking.IssueDownload(manifest, artifact, userId, subjectId);
        if (dispatch.ClaimTicket is null || string.IsNullOrWhiteSpace(dispatch.ClaimTicket.ClaimCode))
        {
            Response.Headers["Cache-Control"] = "private, no-store";
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "install claim code is unavailable for this artifact.");
        }

        string supportHref = DesktopInstallRail.BuildSupportHref(
            artifact,
            manifest,
            installationId: null,
            recoveryMode: true);
        DesktopInstallContinuationReceipt continuation = DesktopInstallRail.BuildContinuationReceipt(
            artifact,
            manifest,
            recoveryMode: true);
        LocalReleaseProofLookupResult routeLookup = FindLocalReleaseProofReceipt(
            $"/downloads/install/{Uri.EscapeDataString(artifactId)}/continue.json",
            "/downloads/install/{artifactId}/continue.json");
        RouteClaimStatus routeClaim = ResolvePublicRouteClaimStatus(
            routeLookup,
            passingState: "pass",
            missingReceiptReason: "No current local release-proof receipt is attached to this install recovery exchange route for the requested artifact.");

        Response.Headers["Cache-Control"] = "private, no-store";
        return Ok(new
        {
            artifactId = artifact.Id,
            downloadReceiptId = dispatch.Receipt.ReceiptId,
            claimTicketId = dispatch.ClaimTicket.TicketId,
            claimCode = dispatch.ClaimTicket.ClaimCode,
            expiresAtUtc = dispatch.ClaimTicket.ExpiresAtUtc,
            status = routeClaim.State,
            routeReceipt = BuildRouteReceiptPayload(routeLookup.ReceiptMatch),
            boundedFailureReason = routeClaim.BoundedFailureReason,
            requiredReceiptRefs = new[]
            {
                $"download:{dispatch.Receipt.ReceiptId}",
                $"claim-ticket:{dispatch.ClaimTicket.TicketId}",
                "desktop_native_claim_and_recovery"
            },
            nextSafeAction = continuation.NextSafeAction,
            recoveryModeOnly = guidedBootstrapDownload,
            applicationVersion = continuation.ApplicationVersion,
            releaseChannel = continuation.ReleaseChannel,
            headId = continuation.HeadId,
            platform = continuation.Platform,
            platformId = continuation.PlatformId,
            arch = continuation.Arch,
            fallbackPosture = continuation.FallbackPosture,
            updateAction = continuation.UpdateAction,
            rollbackAction = continuation.RollbackAction,
            accountHref = "/account/access",
            downloadsHref = "/downloads",
            helpHref = "/help#install-update",
            supportHref,
            supportSummary = continuation.SupportContinuation
        });
    }

    [HttpGet("/participate")]
    [Produces("text/html")]
    public async Task<IActionResult> ParticipatePage(CancellationToken cancellationToken)
    {
        var model = await BuildParticipatePageModel(
            title: "Participate",
            description: "Public product signal stays visible here, while signed-in Codex access remains an optional account-linked lane.",
            currentPath: "/participate",
            cancellationToken: cancellationToken);
        return View("~/Views/PublicLanding/Participate.cshtml", model);
    }

    [HttpGet("/ready")]
    [Produces("text/html")]
    public async Task<IActionResult> ReadyForTonightPage(CancellationToken cancellationToken)
    {
        var model = await BuildReadyForTonightPageModel(cancellationToken);
        return View("~/Views/PublicLanding/ReadyForTonight.cshtml", model);
    }

    [HttpGet("/tonight")]
    public IActionResult TonightAliasPage()
        => Redirect("/ready");

    [HttpGet("/ready/packet/{role}.md")]
    [Produces("text/markdown")]
    public IActionResult ReadyForTonightPacketMarkdown([FromRoute] string role)
    {
        var bytes = Encoding.UTF8.GetBytes(_readyForTonight.BuildPacketMarkdown(role));
        return File(bytes, "text/markdown; charset=utf-8", $"chummer-ready-{role.Trim().ToLowerInvariant()}.md");
    }

    [HttpGet("/ready/packet/{role}.json")]
    [Produces("application/json")]
    public IActionResult ReadyForTonightPacketJson([FromRoute] string role)
        => Content(_readyForTonight.BuildPacketJson(role), "application/json");

    [HttpGet("/ready/loadout/{kitId}.json")]
    [Produces("application/json")]
    public IActionResult ReadyForTonightLoadoutJson([FromRoute] string kitId)
        => Content(_readyForTonight.BuildLoadoutJson(kitId), "application/json");

    [HttpGet("/ready/handoff/mobile.json")]
    [Produces("application/json")]
    public IActionResult ReadyForTonightMobileHandoff()
        => Content(_readyForTonight.BuildMobileHandoffJson(), "application/json");

    [HttpGet("/rules")]
    [Produces("text/html")]
    public async Task<IActionResult> RulesKnowledgePage(CancellationToken cancellationToken)
    {
        var model = await BuildKnowledgeFabricPageModel(cancellationToken);
        return View("~/Views/PublicLanding/KnowledgeFabric.cshtml", model);
    }

    [HttpGet("/knowledge")]
    public IActionResult KnowledgeAliasPage()
        => Redirect("/rules");

    [HttpGet("/rules/receipts")]
    [Produces("application/json")]
    public IActionResult KnowledgeFabricReceiptIndex()
        => Content(_knowledgeFabric.BuildIndexJson(), "application/json");

    [HttpGet("/rules/receipts/{receiptId}.json")]
    [Produces("application/json")]
    public IActionResult KnowledgeFabricReceiptJson([FromRoute] string receiptId)
        => Content(_knowledgeFabric.BuildReceiptJson(receiptId), "application/json");

    [HttpGet("/play/continuity")]
    [Produces("text/html")]
    public async Task<IActionResult> ContinuityPreviewPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/NexusPanContinuity.cshtml", await BuildNexusPanContinuityPageModel(cancellationToken));

    [HttpGet("/play/continuity/receipts")]
    [Produces("application/json")]
    public IActionResult NexusPanReceiptIndex()
        => Content(_nexusPan.BuildIndexJson(), "application/json");

    [HttpGet("/play/continuity/receipts/{receiptId}.json")]
    [Produces("application/json")]
    public IActionResult NexusPanReceiptJson([FromRoute] string receiptId)
        => Content(_nexusPan.BuildReceiptJson(receiptId), "application/json");

    [HttpGet("/mobile/pwa.json")]
    [Produces("application/json")]
    public IActionResult MobilePwaJson()
        => Content(_nexusPan.BuildMobilePwaJson(), "application/json");

    [HttpGet("/jackpoint")]
    [Produces("text/html")]
    public async Task<IActionResult> JackpointPreviewPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildJackpointPageModel(cancellationToken));

    [HttpGet("/jackpoint/briefings/{briefingId}.md")]
    [Produces("text/markdown")]
    public IActionResult JackpointBriefingMarkdown([FromRoute] string briefingId)
        => Content(_mediaHorizons.BuildDocumentMarkdown(_mediaHorizons.GetJackpointBriefing(briefingId), "JACKPOINT", "Player-safe dossier and mission-brief output only. GM-private spoiler packets stay off the public rail."), "text/markdown");

    [HttpGet("/jackpoint/briefings/{briefingId}.json")]
    [Produces("application/json")]
    public IActionResult JackpointBriefingJson([FromRoute] string briefingId)
        => Content(_mediaHorizons.BuildDocumentJson(_mediaHorizons.GetJackpointBriefing(briefingId), "jackpoint", "Player-safe dossier and mission-brief output only. GM-private spoiler packets stay off the public rail."), "application/json");

    [HttpGet("/briefings")]
    public IActionResult BriefingsAliasPage()
        => Redirect("/jackpoint");

    [HttpGet("/runsites")]
    [Produces("text/html")]
    public async Task<IActionResult> RunsitePreviewPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildRunsitePageModel(cancellationToken));

    [HttpGet("/runsites/packs/{packId}.md")]
    [Produces("text/markdown")]
    public IActionResult RunsitePackMarkdown([FromRoute] string packId)
        => Content(_mediaHorizons.BuildDocumentMarkdown(_mediaHorizons.GetRunsitePack(packId), "RUNSITE", "Spatial-prep packet only. This route does not claim a full overlay, VTT, or tactical authority stack."), "text/markdown");

    [HttpGet("/runsites/packs/{packId}.json")]
    [Produces("application/json")]
    public IActionResult RunsitePackJson([FromRoute] string packId)
        => Content(_mediaHorizons.BuildDocumentJson(_mediaHorizons.GetRunsitePack(packId), "runsite", "Spatial-prep packet only. This route does not claim a full overlay, VTT, or tactical authority stack."), "application/json");

    [HttpGet("/runbook")]
    [Produces("text/html")]
    public async Task<IActionResult> RunbookPreviewPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildRunbookPageModel(cancellationToken));

    [HttpGet("/runbook/primers/{primerId}.md")]
    [Produces("text/markdown")]
    public IActionResult RunbookPrimerMarkdown([FromRoute] string primerId)
        => Content(_mediaHorizons.BuildDocumentMarkdown(_mediaHorizons.GetRunbookPrimer(primerId), "RUNBOOK PRESS", "Printable onboarding and prep packets only. This route does not claim a full long-form publishing studio."), "text/markdown");

    [HttpGet("/runbook/primers/{primerId}.json")]
    [Produces("application/json")]
    public IActionResult RunbookPrimerJson([FromRoute] string primerId)
        => Content(_mediaHorizons.BuildDocumentJson(_mediaHorizons.GetRunbookPrimer(primerId), "runbook_press", "Printable onboarding and prep packets only. This route does not claim a full long-form publishing studio."), "application/json");

    [HttpGet("/primers")]
    public IActionResult PrimersAliasPage()
        => Redirect("/runbook");

    [HttpGet("/community")]
    [Produces("text/html")]
    public async Task<IActionResult> CommunityPreviewPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildCommunityHubPageModel(cancellationToken));

    [HttpGet("/runs")]
    public IActionResult RunsAliasPage()
        => Redirect("/community");

    [HttpGet("/organizers")]
    public IActionResult OrganizersAliasPage()
        => Redirect("/community");

    [HttpGet("/creator")]
    [Produces("text/html")]
    public async Task<IActionResult> CreatorPreviewPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildCreatorOsPageModel(cancellationToken));

    [HttpGet("/ghostwire")]
    [Produces("text/html")]
    public async Task<IActionResult> GhostwirePreviewPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildGhostwirePageModel(cancellationToken));

    [HttpGet("/ghostwire/after-action/{packetId}.md")]
    [Produces("text/markdown")]
    public IActionResult GhostwirePacketMarkdown([FromRoute] string packetId)
        => Content(_waveEightHorizons.BuildGhostwireMarkdown(packetId), "text/markdown");

    [HttpGet("/ghostwire/after-action/{packetId}.json")]
    [Produces("application/json")]
    public IActionResult GhostwirePacketJson([FromRoute] string packetId)
        => Content(_waveEightHorizons.BuildGhostwireJson(packetId), "application/json");

    [HttpGet("/exports/foundry")]
    [Produces("text/html")]
    public async Task<IActionResult> FoundryHandoffPage(CancellationToken cancellationToken)
    {
        var model = await BuildHorizonPreviewPageModel(
            pageId: "foundry-handoff",
            title: "Foundry handoff",
            description: "Governed Foundry export remains intentionally parked until packet truth and map metadata transport can be proven together.",
            currentPath: "/exports/foundry",
            eyebrow: "Honestly parked",
            heading: "Foundry handoff",
            intro: "Foundry handoff is intentionally parked. Chummer does not currently claim a shipped public Foundry packet lane, and this route exists to make that boundary explicit instead of vague.",
            summaryPoints:
            [
                "Honestly parked",
                "No public Foundry packet claim",
                "Map authority not exported"
            ],
            sections:
            [
                new TrustPageSectionViewModel("foundry-boundary", "Boundary", "Do not overclaim the export lane", "Foundry handoff stays parked until first-party export truth, map metadata transport, and moderation-safe publication posture can be proven together.", ["Parked on purpose", "No fake public export", "No third-party truth owner"]),
                new TrustPageSectionViewModel("foundry-next", "Next real step", "Proof before promotion", "The next honest promotion step is a governed handoff packet with first-party receipts, not roadmap prose alone.", ["Governed packet", "Receipt proof", "Future promotion gate"])
            ],
            actions:
            [
                new TrustPageActionViewModel("Open runsites", "/runsites", "primary"),
                new TrustPageActionViewModel("Open roadmap", "/roadmap/foundry-vtt-handoff", "secondary")
            ],
            cancellationToken: cancellationToken);
        return View("~/Views/PublicLanding/TrustPage.cshtml", model);
    }

    [HttpGet("/passport")]
    [Produces("text/html")]
    public async Task<IActionResult> RunnerPassportPreviewPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildRunnerPassportPageModel(cancellationToken));

    [HttpGet("/community/open-runs/{packetId}.md")]
    [Produces("text/markdown")]
    public IActionResult CommunityOpenRunPacketMarkdown([FromRoute] string packetId)
        => Content(_communityCreatorHorizons.BuildCommunityMarkdown(packetId), "text/markdown");

    [HttpGet("/community/open-runs/{packetId}.json")]
    [Produces("application/json")]
    public IActionResult CommunityOpenRunPacketJson([FromRoute] string packetId)
        => Content(_communityCreatorHorizons.BuildCommunityJson(packetId), "application/json");

    [HttpGet("/creator/packets/{packetId}.md")]
    [Produces("text/markdown")]
    public IActionResult CreatorPacketMarkdown([FromRoute] string packetId)
        => Content(_communityCreatorHorizons.BuildCreatorMarkdown(packetId), "text/markdown");

    [HttpGet("/creator/packets/{packetId}.json")]
    [Produces("application/json")]
    public IActionResult CreatorPacketJson([FromRoute] string packetId)
        => Content(_communityCreatorHorizons.BuildCreatorJson(packetId), "application/json");

    [HttpGet("/passport/receipts/{receiptId}.md")]
    [Produces("text/markdown")]
    public IActionResult PassportReceiptMarkdown([FromRoute] string receiptId)
        => Content(_communityCreatorHorizons.BuildPassportMarkdown(receiptId), "text/markdown");

    [HttpGet("/passport/receipts/{receiptId}.json")]
    [Produces("application/json")]
    public IActionResult PassportReceiptJson([FromRoute] string receiptId)
        => Content(_communityCreatorHorizons.BuildPassportJson(receiptId), "application/json");

    [HttpGet("/karma-forge")]
    public IActionResult KarmaForgeAliasPage()
        => Redirect("/participate/karma-forge");

    [HttpGet("/participate/karma-forge")]
    [Produces("text/html")]
    public async Task<IActionResult> KarmaForgePage([FromQuery] string? track, CancellationToken cancellationToken)
    {
        var request = new KarmaForgeSubmissionRequest();
        if (!string.IsNullOrWhiteSpace(track))
        {
            request.TrackKey = track;
        }

        var model = await BuildKarmaForgePageModel(
            request,
            submissionNotice: null,
            validationErrors: Array.Empty<string>(),
            cancellationToken: cancellationToken);
        return View("~/Views/PublicLanding/KarmaForge.cshtml", model);
    }

    [HttpPost("/participate/karma-forge")]
    [ValidateAntiForgeryToken]
    [Produces("text/html")]
    public async Task<IActionResult> SubmitKarmaForgePage([FromForm] KarmaForgeSubmissionRequest request, CancellationToken cancellationToken)
    {
        request ??= new KarmaForgeSubmissionRequest();
        AuthenticatedHubSubject? subject = await TryGetOptionalPublicSurfaceSubjectAsync("/participate/karma-forge", cancellationToken);
        IReadOnlyList<string> validationErrors = ValidateKarmaForgeSubmission(request, subject is not null);
        if (validationErrors.Count > 0)
        {
            var invalidModel = await BuildKarmaForgePageModel(
                request,
                "The packet is still local to this form until the required fields and consent are complete.",
                validationErrors,
                cancellationToken,
                subject);
            return View("~/Views/PublicLanding/KarmaForge.cshtml", invalidModel);
        }

        HubUserDto? signedInUser = subject is null ? null : _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        KarmaForgeSubmissionProjection submission = _karmaForge.Submit(request, subject?.SubjectId, subject?.DisplayName);
        if (subject is not null && signedInUser is not null)
        {
            string authProviderFamily = ParticipationOperatorNotificationService.InferAuthProviderFamily(_links.GetSummary(subject.SubjectId));
            await _participationNotifications.NotifyFirstActionIfNeededAsync(
                signedInUser,
                subject.Email,
                intentKind: "karma_forge",
                entryRoute: "/participate/karma-forge",
                authProviderFamily,
                cancellationToken);
        }

        return Redirect($"/participate/karma-forge/submitted/{Uri.EscapeDataString(submission.SubmissionId)}");
    }

    [HttpGet("/participate/karma-forge/submitted/{submissionId}")]
    [Produces("text/html")]
    public async Task<IActionResult> KarmaForgeSubmittedPage([FromRoute] string submissionId, CancellationToken cancellationToken)
    {
        KarmaForgeSubmissionProjection? submission = _karmaForge.FindById(submissionId);
        if (submission is null && string.Equals(submissionId, "sample-submission-id", StringComparison.OrdinalIgnoreCase))
        {
            submission = BuildSampleKarmaForgeSubmission();
        }

        if (submission is null)
        {
            return NotFound();
        }

        var model = await BuildKarmaForgeSubmittedPageModel(submission, cancellationToken);
        return View("~/Views/PublicLanding/KarmaForgeSubmitted.cshtml", model);
    }

    [HttpGet("/ledger")]
    [Produces("text/html")]
    public async Task<IActionResult> LedgerPage([FromQuery] int? turn, CancellationToken cancellationToken)
    {
        if (await TryIsAuthenticatedAsync(cancellationToken))
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            HubUserDto user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            if (!_blackLedgerFactions.HasActiveAllegiance(user.UserId))
            {
                return Redirect("/account/ledger/onboarding");
            }
        }

        var model = await BuildBlackLedgerPageModel("/ledger", "hub", turn, cancellationToken);
        return View("~/Views/PublicLanding/Ledger.cshtml", model);
    }

    [HttpGet("/ledger/map")]
    [Produces("text/html")]
    public async Task<IActionResult> LedgerMapPage([FromQuery] int? turn, [FromQuery] string? mode, CancellationToken cancellationToken)
    {
        var model = await BuildBlackLedgerPageModel("/ledger/map", "map", turn, cancellationToken, selectedMapMode: mode);
        return View("~/Views/PublicLanding/Ledger.cshtml", model);
    }

    [HttpGet("/black-ledger")]
    public IActionResult LedgerAliasPage()
        => Redirect("/ledger");

    [HttpGet("/ledger/stats")]
    [Produces("text/html")]
    public async Task<IActionResult> LedgerStatsPage([FromQuery] int? turn, CancellationToken cancellationToken)
    {
        var model = await BuildBlackLedgerPageModel("/ledger/stats", "stats", turn, cancellationToken);
        return View("~/Views/PublicLanding/Ledger.cshtml", model);
    }

    [HttpGet("/ledger/factions")]
    [Produces("text/html")]
    public async Task<IActionResult> LedgerFactionsPage([FromQuery] int? turn, CancellationToken cancellationToken)
    {
        var model = await BuildBlackLedgerPageModel("/ledger/factions", "factions", turn, cancellationToken);
        return View("~/Views/PublicLanding/Ledger.cshtml", model);
    }

    [HttpGet("/ledger/factions/{factionId}")]
    [Produces("text/html")]
    public async Task<IActionResult> LedgerFactionProfilePage([FromRoute] string factionId, [FromQuery] int? turn, CancellationToken cancellationToken)
    {
        var model = await BuildBlackLedgerPageModel($"/ledger/factions/{factionId}", "factions", turn, cancellationToken, selectedFactionId: factionId);
        bool knownFaction = model.World?.Factions.Any(faction =>
            string.Equals(faction.Id, factionId, StringComparison.OrdinalIgnoreCase) ||
            string.Equals(faction.Id.Replace('_', '-'), factionId, StringComparison.OrdinalIgnoreCase)) == true;
        if (!knownFaction)
        {
            return NotFound();
        }

        return View("~/Views/PublicLanding/Ledger.cshtml", model);
    }

    [HttpGet("/ledger/packages")]
    [Produces("text/html")]
    public async Task<IActionResult> LedgerPackagesPage([FromQuery] int? turn, CancellationToken cancellationToken)
    {
        var model = await BuildBlackLedgerPageModel("/ledger/packages", "packages", turn, cancellationToken);
        return View("~/Views/PublicLanding/Ledger.cshtml", model);
    }

    [HttpGet("/ledger/closeouts")]
    [Produces("text/html")]
    public async Task<IActionResult> LedgerCloseoutsPage([FromQuery] int? turn, CancellationToken cancellationToken)
    {
        var model = await BuildBlackLedgerPageModel("/ledger/closeouts", "closeouts", turn, cancellationToken);
        return View("~/Views/PublicLanding/Ledger.cshtml", model);
    }

    [HttpGet("/ledger/dispatches")]
    [Produces("text/html")]
    public async Task<IActionResult> LedgerDispatchesPage([FromQuery] int? turn, [FromQuery] string? ruleset, CancellationToken cancellationToken)
    {
        var model = await BuildBlackLedgerPageModel("/ledger/dispatches", "dispatches", turn, cancellationToken, selectedRulesetId: ruleset);
        return View("~/Views/PublicLanding/Ledger.cshtml", model);
    }

    [HttpGet("/ledger/dispatches/{dispatchId}")]
    [Produces("text/html")]
    public async Task<IActionResult> LedgerDispatchDetailPage([FromRoute] string dispatchId, [FromQuery] int? turn, CancellationToken cancellationToken)
    {
        var model = await BuildBlackLedgerPageModel($"/ledger/dispatches/{dispatchId}", "dispatches", turn, cancellationToken, dispatchId);
        if (model.SelectedDispatch is null)
        {
            return NotFound();
        }

        return View("~/Views/PublicLanding/Ledger.cshtml", model);
    }

    [HttpGet("/ledger/turns/{turn}")]
    [Produces("text/html")]
    public async Task<IActionResult> LedgerTurnPage([FromRoute] string turn, [FromQuery] string? mode, CancellationToken cancellationToken)
    {
        if (!int.TryParse(turn, out int requestedTurn) || requestedTurn < 0)
        {
            return NotFound();
        }

        var model = await BuildBlackLedgerPageModel($"/ledger/turns/{requestedTurn}", "map", requestedTurn, cancellationToken, selectedMapMode: mode);
        return View("~/Views/PublicLanding/Ledger.cshtml", model);
    }

    [HttpGet("/ledger/turns/{turn}/dispatches")]
    [Produces("text/html")]
    public async Task<IActionResult> LedgerTurnDispatchesPage([FromRoute] string turn, CancellationToken cancellationToken)
    {
        if (!int.TryParse(turn, out int requestedTurn) || requestedTurn < 0)
        {
            return NotFound();
        }

        var model = await BuildBlackLedgerPageModel($"/ledger/turns/{requestedTurn}/dispatches", "dispatches", requestedTurn, cancellationToken);
        return View("~/Views/PublicLanding/Ledger.cshtml", model);
    }

    [HttpGet("/ledger/factions/{factionId}/dispatches")]
    [Produces("text/html")]
    public async Task<IActionResult> LedgerFactionDispatchesPage([FromRoute] string factionId, [FromQuery] int? turn, CancellationToken cancellationToken)
    {
        var model = await BuildBlackLedgerPageModel($"/ledger/factions/{factionId}/dispatches", "dispatches", turn, cancellationToken, selectedFactionId: factionId);
        if (model.Dispatches.Count == 0)
        {
            return NotFound();
        }

        return View("~/Views/PublicLanding/Ledger.cshtml", model);
    }

    [HttpGet("/ledger/factions/{factionId}/packages")]
    [Produces("text/html")]
    public async Task<IActionResult> LedgerFactionPackagesPage([FromRoute] string factionId, [FromQuery] int? turn, CancellationToken cancellationToken)
    {
        var model = await BuildBlackLedgerPageModel($"/ledger/factions/{factionId}/packages", "packages", turn, cancellationToken, selectedFactionId: factionId);
        bool knownFaction = model.World?.Factions.Any(faction =>
            string.Equals(faction.Id, factionId, StringComparison.OrdinalIgnoreCase) ||
            string.Equals(faction.Id.Replace('_', '-'), factionId, StringComparison.OrdinalIgnoreCase)) == true;
        return knownFaction
            ? View("~/Views/PublicLanding/Ledger.cshtml", model)
            : NotFound();
    }

    [HttpGet("/account/ledger")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountLedgerHomePage(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            if (!_blackLedgerFactions.HasActiveAllegiance(user.UserId))
            {
                return Redirect("/account/ledger/onboarding");
            }

            var model = await BuildLedgerFactionHomePageModel(user, cancellationToken);
            return View("~/Views/PublicLanding/LedgerAccountHome.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect("/login?next=%2Faccount%2Fledger");
        }
    }

    [HttpGet("/account/ledger/onboarding")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountLedgerOnboardingPage(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var model = await BuildLedgerOnboardingPageModel(user, cancellationToken);
            return View("~/Views/PublicLanding/LedgerOnboarding.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect("/login?next=%2Faccount%2Fledger%2Fonboarding");
        }
    }

    [HttpPost("/account/ledger/onboarding/join")]
    [ValidateAntiForgeryToken]
    public async Task<IActionResult> AccountLedgerOnboardingJoin([FromForm] string factionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var receipt = _blackLedgerFactions.JoinFaction(user, factionId);
            return Redirect($"/account/ledger/factions/{receipt.FactionId.Replace('_', '-')}");
        }
        catch (Exception ex) when (ex is HubRequestAuthException or InvalidOperationException)
        {
            return Redirect("/account/ledger/onboarding");
        }
    }

    [HttpGet("/account/ledger/factions/create")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountLedgerFactionCreatePage(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var model = await BuildLedgerFactionCreatePageModel(user, cancellationToken);
            return View("~/Views/PublicLanding/LedgerFactionCreate.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect("/login?next=%2Faccount%2Fledger%2Ffactions%2Fcreate");
        }
    }

    [HttpPost("/account/ledger/factions/create")]
    [ValidateAntiForgeryToken]
    public async Task<IActionResult> AccountLedgerFactionCreatePost(
        [FromForm] string publicName,
        [FromForm] string charterType,
        [FromForm] string archetypeId,
        [FromForm] string? startingDistrictId,
        [FromForm] string? rivalFactionId,
        [FromForm] string[] perkIds,
        [FromForm] string[] flawIds,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var charter = _blackLedgerFactions.CreateFaction(user, new BlackLedgerCreateFactionRequest(publicName, charterType, archetypeId, perkIds, flawIds, startingDistrictId, rivalFactionId));
            return Redirect($"/account/ledger/factions/{charter.FactionId.Replace('_', '-')}");
        }
        catch (Exception ex) when (ex is HubRequestAuthException or InvalidOperationException)
        {
            return Redirect("/account/ledger/factions/create");
        }
    }

    [HttpGet("/account/ledger/factions/{factionId}")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountLedgerFactionPage([FromRoute] string factionId, CancellationToken cancellationToken)
        => await BuildLedgerFactionWorkspacePage($"/account/ledger/factions/{factionId}", factionId, "overview", cancellationToken);

    [HttpGet("/account/ledger/factions/{factionId}/manage")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountLedgerFactionManagePage([FromRoute] string factionId, CancellationToken cancellationToken)
        => await BuildLedgerFactionWorkspacePage($"/account/ledger/factions/{factionId}/manage", factionId, "manage", cancellationToken);

    [HttpGet("/account/ledger/factions/{factionId}/stewards")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountLedgerFactionStewardsPage([FromRoute] string factionId, CancellationToken cancellationToken)
        => await BuildLedgerFactionWorkspacePage($"/account/ledger/factions/{factionId}/stewards", factionId, "stewards", cancellationToken);

    [HttpGet("/account/ledger/factions/{factionId}/private-lore")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountLedgerFactionPrivateLorePage([FromRoute] string factionId, CancellationToken cancellationToken)
        => await BuildLedgerFactionWorkspacePage($"/account/ledger/factions/{factionId}/private-lore", factionId, "private-lore", cancellationToken);

    [HttpPost("/account/ledger/factions/{factionId}/actions")]
    [ValidateAntiForgeryToken]
    public async Task<IActionResult> AccountLedgerFactionActionPost(
        [FromRoute] string factionId,
        [FromForm] string actionId,
        [FromForm] string? targetDistrictId,
        [FromForm] string? targetFactionId,
        [FromForm] string? stake,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            _blackLedgerFactions.ExecuteAction(user, factionId, new BlackLedgerFactionActionRequest(actionId, targetDistrictId, targetFactionId, stake));
            return Redirect($"/account/ledger/factions/{factionId}/manage");
        }
        catch (Exception ex) when (ex is HubRequestAuthException or InvalidOperationException)
        {
            return Redirect($"/account/ledger/factions/{factionId}/manage");
        }
    }

    [HttpGet("/ledger/anarchy")]
    [Produces("text/html")]
    public async Task<IActionResult> AnarchyLedgerPage(CancellationToken cancellationToken)
    {
        var model = await BuildAnarchyPageModel(
            currentPath: "/ledger/anarchy",
            currentSection: "ledger",
            eyebrow: "Anarchy and Black Ledger",
            heading: "Anarchy consequence lane",
            intro: "Anarchy belongs here as a dedicated narrative ruleset lane: dispatch-friendly, mobile-first, and bound to the same public-safe World Tick receipts as the rest of Black Ledger.",
            primaryAction: new TrustPageActionViewModel("Open Black Ledger", "/ledger", "primary"),
            secondaryAction: new TrustPageActionViewModel("Read Anarchy-compatible dispatches", "/ledger/dispatches?ruleset=anarchy", "secondary"),
            cancellationToken);
        return View("~/Views/PublicLanding/Anarchy.cshtml", model);
    }

    [HttpGet("/feedback")]
    [Produces("text/html")]
    public async Task<IActionResult> FeedbackPage(CancellationToken cancellationToken)
    {
        var model = await BuildParticipatePageModel(
            title: "Feedback",
            description: "Public ideas, votes, safe bug reports, and shipped follow-up stay on a dedicated first-party signal rail.",
            currentPath: "/feedback",
            cancellationToken);
        return View("~/Views/PublicLanding/Feedback.cshtml", model);
    }

    [HttpGet("/help/feedback")]
    public IActionResult FeedbackHelpPage()
        => Redirect("/feedback");

    [HttpPost("/feedback/providers/productlift/webhook")]
    [HttpPost("/api/v1/public/feedback/providers/productlift/webhook")]
    [ProducesResponseType<PublicSignalWebhookAckResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    [ProducesResponseType(StatusCodes.Status503ServiceUnavailable)]
    public ActionResult<PublicSignalWebhookAckResponse> ReceiveProductLiftWebhook([FromBody] JsonElement payload)
    {
        string? configuredSecret = _configuration["CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET"]?.Trim();
        if (string.IsNullOrWhiteSpace(configuredSecret))
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "productlift webhook adapter is not configured.");
        }

        string suppliedSecret = Request.Headers[PublicSignalOperationsService.WebhookSecretHeader].ToString();
        if (!string.Equals(suppliedSecret, configuredSecret, StringComparison.Ordinal))
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: "productlift webhook secret mismatch.");
        }

        try
        {
            return Ok(_signalOperations.RecordWebhook(payload));
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpGet("/feedback/operations")]
    [HttpGet("/api/v1/public/feedback/operations")]
    [Produces("application/json")]
    public ContentResult FeedbackOperationsArtifact()
        => Content(_signalOperations.LoadArtifactJson(), "application/json");

    [HttpGet("/feedback/operations/lookup")]
    [Produces("text/html")]
    public async Task<IActionResult> FeedbackOperationsLookupPage([FromQuery] string? q, [FromQuery] string? scope, CancellationToken cancellationToken)
        => View(
            "~/Views/PublicLanding/FeedbackOperationsLookup.cshtml",
            new PublicSignalOperationsLookupPageViewModel(
                Chrome: await BuildPublicOrAuthenticatedChromeAsync(
                    "Feedback Activity Lookup",
                    "Bounded public lookup across first-party source receipts and follow-up thread drilldowns.",
                    "/feedback/operations/lookup",
                    cancellationToken),
                Lookup: _signalOperations.BuildLookup(q, scope)));

    [HttpGet("/api/v1/public/feedback/operations/lookup")]
    [Produces("application/json")]
    public ContentResult FeedbackOperationsLookupArtifact([FromQuery] string? q, [FromQuery] string? scope)
        => Content(_signalOperations.LoadLookupJson(q, scope), "application/json");

    [HttpGet("/feedback/operations/source/{sourceReceiptId}")]
    [Produces("text/html")]
    public async Task<IActionResult> FeedbackOperationsSourceDetailPage(string sourceReceiptId, [FromQuery] string? filter, CancellationToken cancellationToken)
    {
        PublicSignalOperationsDetailViewModel? detail = _signalOperations.BuildSourceReceiptDetail(sourceReceiptId, filter);
        if (detail is null)
        {
            return NotFound();
        }

        return View(
            "~/Views/PublicLanding/FeedbackOperationsDetail.cshtml",
            new PublicSignalOperationsDetailPageViewModel(
                Chrome: await BuildPublicOrAuthenticatedChromeAsync(
                    "Feedback Activity Source Detail",
                    "Bounded source receipt drilldown across queue, delivery update, and journey state.",
                    string.Equals(detail.FilterKey, "all", StringComparison.Ordinal)
                        ? $"/feedback/operations/source/{sourceReceiptId}"
                        : $"/feedback/operations/source/{sourceReceiptId}?filter={Uri.EscapeDataString(detail.FilterKey)}",
                    cancellationToken),
                Detail: detail));
    }

    [HttpGet("/api/v1/public/feedback/operations/source/{sourceReceiptId}")]
    [Produces("application/json")]
    public IActionResult FeedbackOperationsSourceDetailArtifact(string sourceReceiptId, [FromQuery] string? filter)
    {
        string? json = _signalOperations.LoadSourceReceiptDetailJson(sourceReceiptId, filter);
        return json is null
            ? NotFound()
            : Content(json, "application/json");
    }

    [HttpGet("/feedback/operations/thread/{dispatchReceiptId}")]
    [Produces("text/html")]
    public async Task<IActionResult> FeedbackOperationsThreadDetailPage(string dispatchReceiptId, [FromQuery] string? filter, CancellationToken cancellationToken)
    {
        PublicSignalOperationsDetailViewModel? detail = _signalOperations.BuildRecipientThreadDetail(dispatchReceiptId, filter);
        if (detail is null)
        {
            return NotFound();
        }

        return View(
            "~/Views/PublicLanding/FeedbackOperationsDetail.cshtml",
            new PublicSignalOperationsDetailPageViewModel(
                Chrome: await BuildPublicOrAuthenticatedChromeAsync(
                    "Feedback Activity Thread Detail",
                    "Bounded follow-up thread drilldown for one dispatch spine.",
                    string.Equals(detail.FilterKey, "all", StringComparison.Ordinal)
                        ? $"/feedback/operations/thread/{dispatchReceiptId}"
                        : $"/feedback/operations/thread/{dispatchReceiptId}?filter={Uri.EscapeDataString(detail.FilterKey)}",
                    cancellationToken),
                Detail: detail));
    }

    [HttpGet("/api/v1/public/feedback/operations/thread/{dispatchReceiptId}")]
    [Produces("application/json")]
    public IActionResult FeedbackOperationsThreadDetailArtifact(string dispatchReceiptId, [FromQuery] string? filter)
    {
        string? json = _signalOperations.LoadRecipientThreadDetailJson(dispatchReceiptId, filter);
        return json is null
            ? NotFound()
            : Content(json, "application/json");
    }

    [HttpPost("/feedback/operations/reconcile")]
    [HttpPost("/api/v1/public/feedback/operations/reconcile")]
    [ProducesResponseType<PublicSignalOperationsReconcileResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    [ProducesResponseType(StatusCodes.Status503ServiceUnavailable)]
    public ActionResult<PublicSignalOperationsReconcileResponse> ReconcileFeedbackOperations()
    {
        string? configuredSecret = _configuration["CHUMMER_PRODUCTLIFT_OPERATIONS_SECRET"]?.Trim();
        if (string.IsNullOrWhiteSpace(configuredSecret))
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "productlift operations replay is not configured.");
        }

        string suppliedSecret = Request.Headers[PublicSignalOperationsService.OperationsSecretHeader].ToString();
        if (!string.Equals(suppliedSecret, configuredSecret, StringComparison.Ordinal))
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: "productlift operations secret mismatch.");
        }

        return Ok(_signalOperations.ReconcilePendingCloseouts());
    }

    [HttpPost("/feedback/operations/recover")]
    [HttpPost("/api/v1/public/feedback/operations/recover")]
    [ProducesResponseType<PublicSignalOperationsRecoveryResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    [ProducesResponseType(StatusCodes.Status503ServiceUnavailable)]
    public ActionResult<PublicSignalOperationsRecoveryResponse> RecoverFeedbackOperations()
    {
        string? configuredSecret = _configuration["CHUMMER_PRODUCTLIFT_OPERATIONS_SECRET"]?.Trim();
        if (string.IsNullOrWhiteSpace(configuredSecret))
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "productlift operations recovery is not configured.");
        }

        string suppliedSecret = Request.Headers[PublicSignalOperationsService.OperationsSecretHeader].ToString();
        if (!string.Equals(suppliedSecret, configuredSecret, StringComparison.Ordinal))
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: "productlift operations secret mismatch.");
        }

        return Ok(_signalOperations.RecoverDispatchOutcomes());
    }

    [HttpPost("/feedback/providers/emailit/webhook")]
    [HttpPost("/api/v1/public/feedback/providers/emailit/webhook")]
    [ProducesResponseType<PublicSignalDeliveryOutcomeAckResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    [ProducesResponseType(StatusCodes.Status503ServiceUnavailable)]
    public ActionResult<PublicSignalDeliveryOutcomeAckResponse> ReceiveEmailitDeliveryOutcome([FromBody] JsonElement payload)
    {
        string? configuredSecret = _configuration["CHUMMER_PRODUCTLIFT_EMAILIT_WEBHOOK_SECRET"]?.Trim();
        if (string.IsNullOrWhiteSpace(configuredSecret))
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "emailit delivery callback adapter is not configured.");
        }

        string suppliedSecret = Request.Headers[PublicSignalOperationsService.EmailitWebhookSecretHeader].ToString();
        if (!string.Equals(suppliedSecret, configuredSecret, StringComparison.Ordinal))
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: "emailit webhook secret mismatch.");
        }

        try
        {
            return Ok(_signalOperations.RecordDeliveryOutcome("emailit", payload));
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpPost("/feedback/providers/ea/delivery/webhook")]
    [HttpPost("/api/v1/public/feedback/providers/ea/delivery/webhook")]
    [ProducesResponseType<PublicSignalDeliveryOutcomeAckResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    [ProducesResponseType(StatusCodes.Status503ServiceUnavailable)]
    public ActionResult<PublicSignalDeliveryOutcomeAckResponse> ReceiveEaDeliveryOutcome([FromBody] JsonElement payload)
    {
        string? configuredSecret = _configuration["CHUMMER_PRODUCTLIFT_EA_DELIVERY_WEBHOOK_SECRET"]?.Trim();
        if (string.IsNullOrWhiteSpace(configuredSecret))
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "ea delivery callback adapter is not configured.");
        }

        string suppliedSecret = Request.Headers[PublicSignalOperationsService.EaDeliveryWebhookSecretHeader].ToString();
        if (!string.Equals(suppliedSecret, configuredSecret, StringComparison.Ordinal))
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: "ea delivery webhook secret mismatch.");
        }

        try
        {
            return Ok(_signalOperations.RecordDeliveryOutcome("ea", payload));
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpPost("/feedback/providers/delivery/outcome")]
    [HttpPost("/api/v1/public/feedback/providers/delivery/outcome")]
    [ProducesResponseType<PublicSignalDeliveryOutcomeAckResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    [ProducesResponseType(StatusCodes.Status503ServiceUnavailable)]
    public ActionResult<PublicSignalDeliveryOutcomeAckResponse> ReceiveDeliveryOutcome([FromBody] JsonElement payload)
    {
        string? configuredSecret = _configuration["CHUMMER_PRODUCTLIFT_OPERATIONS_SECRET"]?.Trim();
        if (string.IsNullOrWhiteSpace(configuredSecret))
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "delivery outcome adapter is not configured.");
        }

        string suppliedSecret = Request.Headers[PublicSignalOperationsService.OperationsSecretHeader].ToString();
        if (!string.Equals(suppliedSecret, configuredSecret, StringComparison.Ordinal))
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: "productlift operations secret mismatch.");
        }

        try
        {
            return Ok(_signalOperations.RecordDeliveryOutcome(payload));
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpGet("/roadmap")]
    [Produces("text/html")]
    public async Task<IActionResult> RoadmapPage(CancellationToken cancellationToken)
    {
        const string currentPath = "/roadmap";
        var surface = _landing.LoadSurface();
        var assetCatalog = new AssetCatalogViewModel(surface.Assets);
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var authenticated = await TryIsAuthenticatedAsync(cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        var signalLoop = BuildPublicSignalLoopSnapshot(surface, assetCatalog, authenticated, currentPath);
        var signalProjection = BuildOptionalSignalProjectionPacket(currentPath);
        var model = new RoadmapPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Roadmap", "Milestone-backed public direction, readiness posture, and the next honest routes.", currentPath, cancellationToken),
            Horizons: ResolveCards(_landing.CardsForBucket(surface, "coming_next"), assetCatalog, authenticated: false, currentPath),
            Milestones: BuildRoadmapMilestones(),
            SignalLoop: signalLoop,
            SignalProjection: signalProjection,
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience));
        return View("~/Views/PublicLanding/Roadmap.cshtml", model);
    }

    [HttpGet("/changelog")]
    [Produces("text/html")]
    public async Task<IActionResult> ChangelogPage(CancellationToken cancellationToken)
    {
        var model = await BuildNowPageModel(
            title: "Changelog",
            description: "Shipped closeout, user-available proof, and current caution stay on one calmer first-party rail.",
            currentPath: "/changelog",
            cancellationToken);
        return View("~/Views/PublicLanding/Changelog.cshtml", model);
    }

    [HttpGet("/status")]
    [Produces("text/html")]
    public async Task<IActionResult> StatusPage(CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var authenticated = await TryIsAuthenticatedAsync(cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        var pulse = _trustPulse.LoadSnapshot();
        var model = new StatusPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Status", "Weekly pulse, release posture, and the current longest pole on one calmer route.", "/status", cancellationToken),
            Manifest: manifest,
            ReleaseExperience: releaseExperience,
            CampaignOsProof: _campaignOsProof.LoadProof(),
            LaunchHealthRows: BuildPublicLaunchHealthRows(manifest, releaseExperience, pulse),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience, pulse),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
        return View("~/Views/PublicLanding/Status.cshtml", model);
    }

    [HttpGet("/artifacts")]
    [Produces("text/html")]
    public async Task<IActionResult> ArtifactsPage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var assetCatalog = new AssetCatalogViewModel(surface.Assets);
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var authenticated = await TryIsAuthenticatedAsync(cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        var signedInArtifactView = NormalizeSignedInArtifactView(Request.Query["view"].ToString());
        IReadOnlyList<RecapShelfEntry> signedInRecapShelf = Array.Empty<RecapShelfEntry>();
        IReadOnlyList<CreatorPublicationProjection> signedInCreatorPublications = Array.Empty<CreatorPublicationProjection>();
        IReadOnlyList<CreatorPublicationProjection> publicCreatorPublications = FilterGuestArtifactShelfPublications(
            _publicCreatorDiscovery.ListDiscoverable(),
            signedInArtifactView);
        IReadOnlyList<ResolvedPublicCardViewModel> guestCards = FilterGuestArtifactShelfCards(
            ResolveCards(_landing.CardsForBucket(surface, "featured_artifacts"), assetCatalog, authenticated: false, "/artifacts"),
            signedInArtifactView);
        var subject = await TryGetOptionalPublicSurfaceSubjectAsync("/artifacts", cancellationToken);
        if (subject is not null)
        {
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var campaignSpine = _campaignSpine.GetAccountSummary(user, installLinking);
            signedInRecapShelf = FilterSignedInArtifactShelfEntries(
                MergeSignedInArtifactShelfEntries(
                    BuildSignedInArtifactShelfEntries(user, campaignSpine, installLinking),
                    BuildSignedInPersonalArtifactShelfEntries(campaignSpine)),
                signedInArtifactView);
            signedInCreatorPublications = FilterSignedInCreatorPublications(
                campaignSpine.CreatorPublications
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray(),
                signedInArtifactView);
        }
        var model = new ShelfPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Artifacts", "Proof surfaces, briefs, and grounded outputs connected to the current preview.", "/artifacts", cancellationToken),
            Surface: surface,
            Assets: assetCatalog,
            Eyebrow: "Artifacts",
            Heading: "Proof gallery",
            Intro: "Browse the packs, briefs, and proof surfaces that make the preview feel tangible.",
            Items: guestCards,
            PublicCreatorPublications: publicCreatorPublications,
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken),
            SignedInRecapShelf: signedInRecapShelf,
            SignedInCreatorPublications: signedInCreatorPublications,
            SignedInArtifactView: signedInArtifactView);
        return View("~/Views/PublicLanding/Shelf.cshtml", model);
    }

    [HttpGet("artifacts/shelf")]
    [HttpGet("/api/v1/public/artifacts/shelf")]
    [HttpGet("/api/public/artifacts/shelf")]
    [Produces("application/json")]
    public async Task<IActionResult> ArtifactShelfApi([FromQuery] string? view, [FromQuery] string? locale, CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var assetCatalog = new AssetCatalogViewModel(surface.Assets);
        var signedInArtifactView = NormalizeSignedInArtifactView(view ?? Request.Query["view"].ToString());
        IReadOnlyList<RecapShelfEntry> signedInRecapShelf = Array.Empty<RecapShelfEntry>();
        IReadOnlyList<CreatorPublicationProjection> signedInCreatorPublications = Array.Empty<CreatorPublicationProjection>();
        IReadOnlyList<CreatorPublicationProjection> publicCreatorPublications = _publicCreatorDiscovery.ListDiscoverable();
        IReadOnlyList<RecapShelfEntry> mergedSignedInArtifactShelf = Array.Empty<RecapShelfEntry>();
        var subject = await TryGetOptionalPublicSurfaceSubjectAsync("/artifacts", cancellationToken);
        if (subject is not null)
        {
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var campaignSpine = _campaignSpine.GetAccountSummary(user, installLinking);
            mergedSignedInArtifactShelf = MergeSignedInArtifactShelfEntries(
                BuildSignedInArtifactShelfEntries(user, campaignSpine, installLinking),
                BuildSignedInPersonalArtifactShelfEntries(campaignSpine));
            signedInRecapShelf = FilterSignedInArtifactShelfEntries(
                mergedSignedInArtifactShelf,
                signedInArtifactView);
            signedInCreatorPublications = FilterSignedInCreatorPublications(
                campaignSpine.CreatorPublications
                    .OrderByDescending(static item => item.UpdatedAtUtc)
                    .ToArray(),
                signedInArtifactView);
        }

        string resolvedLocale = ResolveArtifactShelfLocale(locale, Request.Headers.AcceptLanguage.ToString());
        PrivacyBoundaryPanelViewModel retention = _privacyBoundaries.BuildPanel("privacy");
        IReadOnlyList<ResolvedPublicCardViewModel> guestCards = ResolveCards(
            _landing.CardsForBucket(surface, "featured_artifacts"),
            assetCatalog,
            authenticated: subject is not null,
            "/artifacts");
        IReadOnlyList<ResolvedPublicCardViewModel> filteredGuestCards = FilterGuestArtifactShelfCards(guestCards, signedInArtifactView);
        IReadOnlyList<CreatorPublicationProjection> filteredPublicCreatorPublications = FilterGuestArtifactShelfPublications(publicCreatorPublications, signedInArtifactView);
        IReadOnlyDictionary<string, int> viewCounts = BuildArtifactShelfViewCounts(
            mergedSignedInArtifactShelf,
            signedInCreatorPublications,
            guestCards,
            publicCreatorPublications,
            subject is not null);

        return Ok(new
        {
            contractName = "chummer.run.public_artifact_shelf.v2",
            generatedAtUtc = DateTimeOffset.UtcNow,
            locale = resolvedLocale,
            signedIn = subject is not null,
            requestedView = signedInArtifactView,
            availableViews = new[]
            {
                BuildArtifactShelfViewPayload("all", viewCounts),
                BuildArtifactShelfViewPayload("personal", viewCounts),
                BuildArtifactShelfViewPayload("campaign", viewCounts),
                BuildArtifactShelfViewPayload("creator", viewCounts),
                BuildArtifactShelfViewPayload("public", viewCounts)
            },
            retention = BuildArtifactShelfRetentionPayload(retention),
            guestShelf = new
            {
                caption = GuestArtifactViewSummaryForApi(signedInArtifactView),
                cards = filteredGuestCards.Select(card => BuildArtifactShelfCardPayload(
                    card,
                    resolvedLocale,
                    BuildArtifactShelfRetentionSummary(retention, "claim_install_linkage"))),
                publicCreatorPublications = filteredPublicCreatorPublications.Select(publication =>
                    BuildArtifactShelfCreatorPublicationPayload(
                        publication,
                        filteredPublicCreatorPublications,
                        resolvedLocale,
                        BuildArtifactShelfRetentionSummary(retention, publication.Discoverable ? "survey_follow_up" : "claim_install_linkage"),
                        publicOnly: true))
            },
            signedInShelf = subject is null
                ? null
                : new
                {
                    caption = ArtifactViewSummaryForApi(signedInArtifactView),
                    recapItems = signedInRecapShelf.Select(item =>
                        BuildArtifactShelfRecapPayload(
                            item,
                            signedInCreatorPublications,
                            resolvedLocale,
                            BuildArtifactShelfRetentionSummary(retention, "claim_install_linkage"))),
                    creatorPublications = signedInCreatorPublications.Select(publication =>
                        BuildArtifactShelfCreatorPublicationPayload(
                            publication,
                            signedInCreatorPublications,
                            resolvedLocale,
                            BuildArtifactShelfRetentionSummary(retention, publication.Discoverable ? "survey_follow_up" : "claim_install_linkage"),
                            publicOnly: string.Equals(signedInArtifactView, "public", StringComparison.Ordinal)))
                }
        });
    }

    [HttpGet("/artifacts/release-bundles/{releaseArtifactId}")]
    [Produces("application/json")]
    public IActionResult ReleaseArtifactBundleProof([FromRoute] string releaseArtifactId)
        => BuildReleaseArtifactBundleProof(releaseArtifactId, requestedFormat: null);

    [HttpGet("/artifacts/release-bundles/{releaseArtifactId}/{format}")]
    [Produces("application/json")]
    public IActionResult ReleaseArtifactBundleOutputProof([FromRoute] string releaseArtifactId, [FromRoute] string format)
        => BuildReleaseArtifactBundleProof(releaseArtifactId, format);

    [HttpGet("/artifacts/creator/{publicationId}")]
    public IActionResult CreatorPublicationDetailCompatibilityRedirect([FromRoute] string publicationId)
        => LocalRedirect($"/artifacts/publications/{Uri.EscapeDataString(publicationId)}");

    [HttpGet("/artifacts/publications/{publicationId}")]
    [Produces("text/html")]
    public async Task<IActionResult> CreatorPublicationDetailPage([FromRoute] string publicationId, CancellationToken cancellationToken)
    {
        CreatorPublicationProjection? publication = _publicCreatorDiscovery.GetDiscoverable(publicationId);
        if (publication is null)
        {
            return NotFound();
        }

        var currentPath = $"/artifacts/publications/{Uri.EscapeDataString(publicationId)}";
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var authenticated = await TryIsAuthenticatedAsync(cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        LocalReleaseProofLookupResult routeLookup = FindLocalReleaseProofReceipt(
            "/artifacts/publications/{publicationId}",
            "/api/v1/public/artifacts/publications/{publicationId}",
            "/api/public/artifacts/publications/{publicationId}");
        RouteClaimStatus routeClaim = ResolvePublicRouteClaimStatus(
            routeLookup,
            passingState: "published",
            missingReceiptReason: "No current local release-proof receipt is attached to the public creator-publication detail route.");
        var model = new PublicCreatorPublicationPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync(publication.Title, publication.Summary, currentPath, cancellationToken),
            Publication: publication,
            BackHref: "/artifacts#governed-creator-discovery",
            RouteState: routeClaim.State,
            RouteReceipt: BuildRouteReceiptPayload(routeLookup.ReceiptMatch),
            BoundedFailureReason: routeClaim.BoundedFailureReason,
            RequiredReceiptRefs: new[]
            {
                "artifact_shelf:v2",
                "public-shelf:/artifacts/publications/{publicationId}"
            },
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
        return View("~/Views/PublicLanding/PublicCreatorPublication.cshtml", model);
    }

    [HttpGet("artifacts/publications/{publicationId}")]
    [HttpGet("/api/v1/public/artifacts/publications/{publicationId}")]
    [HttpGet("/api/public/artifacts/publications/{publicationId}")]
    [Produces("application/json")]
    public async Task<IActionResult> CreatorPublicationDetailApi([FromRoute] string publicationId, [FromQuery] string? locale, CancellationToken cancellationToken)
    {
        CreatorPublicationProjection? publication = _publicCreatorDiscovery.GetDiscoverable(publicationId);
        if (publication is null)
        {
            return NotFound();
        }

        string resolvedLocale = ResolveArtifactShelfLocale(locale, Request.Headers.AcceptLanguage.ToString());
        PrivacyBoundaryPanelViewModel retention = _privacyBoundaries.BuildPanel("privacy");
        IReadOnlyList<CreatorPublicationProjection> siblings = _publicCreatorDiscovery.ListDiscoverable(limit: 12)
            .Where(item => !string.Equals(item.PublicationId, publicationId, StringComparison.OrdinalIgnoreCase))
            .ToArray();
        var subject = await TryGetOptionalPublicSurfaceSubjectAsync($"/artifacts/publications/{publicationId}", cancellationToken);
        LocalReleaseProofLookupResult routeLookup = FindLocalReleaseProofReceipt(
            "/artifacts/publications/{publicationId}",
            "/api/v1/public/artifacts/publications/{publicationId}",
            "/api/public/artifacts/publications/{publicationId}");
        RouteClaimStatus routeClaim = ResolvePublicRouteClaimStatus(
            routeLookup,
            passingState: "published",
            missingReceiptReason: "No current local release-proof receipt is attached to the public creator-publication detail route.");

        return Ok(new
        {
            contractName = "chummer.run.public_artifact_shelf.publication.v1",
            generatedAtUtc = DateTimeOffset.UtcNow,
            locale = resolvedLocale,
            signedIn = subject is not null,
            routeState = routeClaim.State,
            routeReceipt = BuildRouteReceiptPayload(routeLookup.ReceiptMatch),
            boundedFailureReason = routeClaim.BoundedFailureReason,
            requiredReceiptRefs = new[]
            {
                "artifact_shelf:v2",
                "public-shelf:/artifacts/publications/{publicationId}"
            },
            retention = BuildArtifactShelfRetentionPayload(retention),
            publication = BuildArtifactShelfCreatorPublicationPayload(
                publication,
                siblings.Prepend(publication).ToArray(),
                resolvedLocale,
                BuildArtifactShelfRetentionSummary(retention, publication.Discoverable ? "survey_follow_up" : "claim_install_linkage"),
                publicOnly: true)
        });
    }

    private IActionResult BuildReleaseArtifactBundleProof(string releaseArtifactId, string? requestedFormat)
    {
        PublicReleaseArtifactDto? artifact = _releases.FindDownload(releaseArtifactId);
        if (artifact is null)
        {
            return NotFound();
        }

        string artifactId = artifact.Id.Trim();
        string bundleRef = $"/artifacts/release-bundles/{Uri.EscapeDataString(artifactId)}";
        string installRef = $"/downloads/install/{Uri.EscapeDataString(artifactId)}";
        string? normalizedFormat = NormalizeArtifactFactoryOutputFormat(requestedFormat);
        if (requestedFormat is not null && normalizedFormat is null)
        {
            return BadRequest(new
            {
                contractName = "chummer.run.public_proof_shelf.release_bundle.v1",
                releaseArtifactId = artifactId,
                rejectedFormat = requestedFormat,
                allowedFormats = ArtifactFactoryOrchestrationService.GetReleaseBundleFormats()
            });
        }

        Dictionary<string, string> outputRefs = ArtifactFactoryOrchestrationService.GetReleaseBundleFormats()
            .ToDictionary(
                static format => format,
                format => $"{bundleRef}/{Uri.EscapeDataString(format)}",
                StringComparer.OrdinalIgnoreCase);
        LocalReleaseProofLookupResult routeLookup = FindLocalReleaseProofReceipt(
            normalizedFormat is null ? bundleRef : outputRefs[normalizedFormat],
            bundleRef,
            installRef);
        RouteClaimStatus routeClaim = ResolvePublicRouteClaimStatus(
            routeLookup,
            passingState: "published",
            missingReceiptReason: "No current local release-proof receipt is attached to this release-bundle route or format.");

        return Ok(new
        {
            contractName = "chummer.run.public_proof_shelf.release_bundle.v1",
            releaseArtifactId = artifactId,
            state = routeClaim.State,
            publicProofShelfRef = normalizedFormat is null ? bundleRef : outputRefs[normalizedFormat],
            releaseBundleRef = bundleRef,
            canonicalInstallRef = installRef,
            requestedFormat = normalizedFormat,
            outputRefs,
            routeReceipt = BuildRouteReceiptPayload(routeLookup.ReceiptMatch),
            boundedFailureReason = routeClaim.BoundedFailureReason,
            nextSafeAction = routeClaim.Blocked
                ? $"Stay on {installRef} or the governed support lane until a current proof receipt is published for {bundleRef}."
                : "Current release-bundle proof is attached to this public route.",
            requiredReceiptRefs = new[]
            {
                $"release:{artifactId}",
                $"public-shelf:{installRef}",
                $"public-shelf:{bundleRef}"
            },
            artifact = new
            {
                artifact.Id,
                artifact.Head,
                artifact.Platform,
                artifact.PlatformId,
                artifact.Arch,
                artifact.Kind,
                artifact.FileName,
                artifact.Sha256,
                artifact.SizeBytes,
                artifact.InstallAccessClass
            }
        });
    }

    private static string? NormalizeArtifactFactoryOutputFormat(string? format)
    {
        if (string.IsNullOrWhiteSpace(format))
        {
            return null;
        }

        string normalized = format.Trim().Replace('-', '_').ToLowerInvariant();
        return ArtifactFactoryOrchestrationService.GetReleaseBundleFormats().Contains(normalized, StringComparer.OrdinalIgnoreCase)
            ? normalized
            : null;
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
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), chrome.Authenticated);
        var accessPosture = _releaseSelection.BuildPublicAccessPosture(manifest, releaseExperience);
        var model = RebindFaqAccessPosture(_trustContent.BuildFaqPage(chrome), accessPosture) with
        {
            TrustPulse = BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus = await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken)
        };
        return View(
            "~/Views/PublicLanding/Faq.cshtml",
            model);
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
                TrustPulse = BuildPublicTrustPulsePanel(manifest, releaseExperience),
                SignedInStatus = await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken)
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
                TrustPulse = BuildPublicTrustPulsePanel(manifest, releaseExperience),
                SignedInStatus = await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken)
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

        bool sampleReceiptId = string.Equals(caseId, "sample-case-id", StringComparison.OrdinalIgnoreCase);
        if (!sampleReceiptId && !caseId.StartsWith("support_case_", StringComparison.OrdinalIgnoreCase))
        {
            return NotFound();
        }

        var chrome = await BuildPublicOrAuthenticatedChromeAsync("Support case submitted", "What happens next after a first-party support report reaches Chummer.", $"/contact/submitted/{caseId}", cancellationToken);
        var subject = await TryGetOptionalSubjectAsync(cancellationToken);
        var authenticated = subject is not null;
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        var user = subject is null
            ? null
            : _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        var installLinking = user is null || subject is null
            ? null
            : _installLinking.GetSummary(user.UserId, subject.SubjectId);
        var trackedCase = subject is null
            ? null
            : _supportCases.GetForReporter(caseId, user!.UserId, subject.SubjectId);
        bool sampleReceipt = trackedCase is null && sampleReceiptId;
        DesktopInstallRailContext installRail = ResolveSupportIntakeRailFromQuery();
        var highlights = new List<string>
        {
            sampleReceipt ? "Sample receipt used for public-route proof." : $"Case id {caseId}",
            sampleReceipt
                ? "This route resolves without opening a real support case."
                : authenticated
                    ? "Tracked on your account support page"
                    : "Guest follow-up stays on the reply email you provided"
        };
        if (trackedCase?.Attachments is { Count: > 0 })
        {
            highlights.Add($"{trackedCase.Attachments.Count} attachment(s) saved");
        }
        if (!string.IsNullOrWhiteSpace(installRail.Summary))
        {
            highlights.Add(installRail.Summary);
        }

        var actions = new List<TrustPageActionViewModel>();
        if (trackedCase is not null)
        {
            actions.Add(new TrustPageActionViewModel("Open tracked support", $"/account/support/{trackedCase.CaseId}", "primary"));
        }
        else if (sampleReceipt)
        {
            actions.Add(new TrustPageActionViewModel("Return to contact", "/contact#support-intake", "primary"));
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
        if (!string.IsNullOrWhiteSpace(installRail.ReturnHref) && !string.IsNullOrWhiteSpace(installRail.ReturnLabel))
        {
            actions.Add(new TrustPageActionViewModel(installRail.ReturnLabel!, installRail.ReturnHref!, "ghost"));
        }

        return View("~/Views/PublicLanding/SupportSubmitted.cshtml", new SupportSubmittedPageViewModel(
            Chrome: chrome,
            Eyebrow: "Support",
            Heading: "Support case received",
            Intro: sampleReceipt
                ? "This sample receipt keeps the public support-submission route provable without opening a real support case."
                : trackedCase is null
                    ? "Chummer accepted the report. Keep the case id nearby if you need to mention it later."
                    : "Chummer accepted the report and linked it to the signed-in account path so the next routed update stays visible.",
            CaseId: caseId,
            StatusLabel: sampleReceipt ? "sample" : trackedCase?.Status ?? SupportCaseStatuses.New,
            ResponseExpectation: sampleReceipt
                ? "This sample receipt only proves the first-party support submission route resolves on the hosted surface. Real follow-up still starts from a submitted support case or the account support rail."
                : BuildSupportResponseExpectation(
                    authenticated,
                    BuildPublicTrustPulsePanel(manifest, releaseExperience)),
            Highlights: highlights,
            Actions: actions,
            Attachments: trackedCase?.Attachments ?? Array.Empty<SupportCaseAttachmentProjection>(),
            TrackedCaseSummary: trackedCase is null ? null : _supportPresentation.Build(trackedCase, installLinking),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: user is null ? null : _signedInTrustStatus.Build(user, manifest, releaseExperience)));
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
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());

        try
        {
            var subject = await TryGetOptionalSubjectAsync(cancellationToken);
            if (subject is null && string.IsNullOrWhiteSpace(replyEmail))
            {
                throw new ArgumentException("A reply email is required when you submit support without an account.");
            }

            var user = subject is null ? null : _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var created = _supportCases.Submit(user?.UserId, subject?.SubjectId, request, await ReadSupportUploadsAsync(attachments, cancellationToken));
            string submittedHref = QueryHelpers.AddQueryString(
                $"/contact/submitted/{Uri.EscapeDataString(created.CaseId)}",
                BuildSupportRailQuery(ResolveSupportIntakeRailFromQuery()));
            return Redirect(submittedHref);
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
                    manifest,
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
                        ContextHint: ResolveSupportContextHintFromRequestQuery(),
                        ArtifactId: NormalizeSupportPrefill(Request.Query.TryGetValue("artifactId", out var artifactValues) ? artifactValues.ToString() : null),
                        RecoveryMode: Request.Query.TryGetValue("recoveryMode", out var recoveryValues)
                            && bool.TryParse(recoveryValues.ToString(), out bool recoveryMode)
                            && recoveryMode))
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
            var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
            var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated: true);
            var supportCases = _supportCases.ListForReporter(user.UserId, subject.SubjectId).Items;
            var supportCaseSummaries = _supportPresentation.BuildList(supportCases, installLinking);
            var campaignSpine = _campaignSpine.GetAccountSummary(user, installLinking);
            var leadWorkspaceServerPlane = campaignSpine.Workspaces.Count == 0
                ? null
                : _workspaceServerPlane.GetWorkspaceServerPlane(user, campaignSpine.Workspaces[0].WorkspaceId, installLinking);
            var model = new HomePageViewModel(
                Chrome: _chrome.BuildAuthenticatedChrome(chromeTitle, chromeDescription, currentPath, user.DisplayName, user.Email),
                CurrentSection: selectedSection,
                Sections: BuildHomeSections(selectedSection),
                Surface: surface,
                Assets: assetCatalog,
                ReleaseExperience: releaseExperience,
                User: user,
                Links: links,
                Experience: experience,
                InstallLinking: installLinking,
                SupportCases: supportCases,
                SupportCaseSummaries: supportCaseSummaries,
                CampaignSpine: campaignSpine,
                LeadWorkspaceServerPlane: leadWorkspaceServerPlane,
                PrimaryAction: BuildHomePrimaryAction(experience, campaignSpine, installLinking, releaseExperience),
                FlagshipCoverage: _flagshipCoverage.LoadStrip(),
                SignedInStatus: _signedInTrustStatus.Build(user, manifest, releaseExperience),
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

    private async Task<PackageCatalogPageViewModel> BuildPackageCatalogPageModel(
        string currentPath,
        string chromeTitle,
        string chromeDescription,
        string eyebrow,
        string heading,
        string intro,
        string scopeLabel,
        bool signedInScope,
        bool operatorScope,
        string detailBasePath,
        AuthenticatedHubSubject? subject,
        HubUserDto? user,
        CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        bool authenticated = subject is not null;
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        SiteChromeViewModel chrome = authenticated && user is not null
            ? _chrome.BuildAuthenticatedChrome(chromeTitle, chromeDescription, currentPath, user.DisplayName, user.Email)
            : await BuildPublicOrAuthenticatedChromeAsync(chromeTitle, chromeDescription, currentPath, cancellationToken);
        var packages = _packageCatalog.ListPackages()
            .Select(package => BuildPackageCatalogEntry(package, detailBasePath))
            .ToArray();
        var receipts = (signedInScope && subject is not null && !operatorScope
                ? _packageCatalog.ListReceiptsForSubject(subject.SubjectId, 12)
                : _packageCatalog.ListRecentReceipts(12))
            .Select(BuildPackageReceiptCard)
            .ToArray();
        TrustPageActionViewModel primaryAction = new("Open downloads", "/downloads", "primary");
        TrustPageActionViewModel? secondaryAction = operatorScope
            ? new TrustPageActionViewModel("Open KARMA FORGE", "/participate/karma-forge", "secondary")
            : authenticated
                ? new TrustPageActionViewModel("Open mobile rail", "/mobile", "secondary")
                : new TrustPageActionViewModel("Create account for tracked packages", "/signup?next=%2Faccount%2Fpackages", "secondary");
        return new PackageCatalogPageViewModel(
            Chrome: chrome,
            Eyebrow: eyebrow,
            Heading: heading,
            Intro: intro,
            SignedInScope: authenticated && signedInScope,
            ScopeLabel: scopeLabel,
            Classes: _packageCatalog.ListPackageClasses()
                .Select(static item => new PackageClassCardViewModel(item.Label, item.Summary, item.Rules))
                .ToArray(),
            Packages: packages,
            Receipts: receipts,
            PrimaryAction: primaryAction,
            SecondaryAction: secondaryAction,
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: user is null ? null : _signedInTrustStatus.Build(user, manifest, releaseExperience));
    }

    private async Task<PackageDetailPageViewModel> BuildPackageDetailPageModel(
        PublicPackageDefinition package,
        string currentPath,
        string scopeLabel,
        TrustPageActionViewModel? secondaryAction,
        AuthenticatedHubSubject? subject,
        HubUserDto? user,
        CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        bool authenticated = subject is not null;
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        SiteChromeViewModel chrome = authenticated && user is not null
            ? _chrome.BuildAuthenticatedChrome(package.Title, package.Summary, currentPath, user.DisplayName, user.Email)
            : await BuildPublicOrAuthenticatedChromeAsync(package.Title, package.Summary, currentPath, cancellationToken);
        string packageDetailBasePath = currentPath.StartsWith("/account/packages/", StringComparison.Ordinal)
            ? "/account/packages"
            : "/packages";
        PackageCatalogEntryViewModel packageEntry = BuildPackageCatalogEntry(package, packageDetailBasePath);
        PackageReceiptCardViewModel? latestVoteReceipt = subject is null
            ? null
            : _packageCatalog.FindLatestReceiptForSubject(package.PackageId, "vote", subject.SubjectId) is { } voteReceipt
                ? BuildPackageReceiptCard(voteReceipt)
                : null;
        PackageReceiptCardViewModel? latestFollowReceipt = subject is null
            ? null
            : _packageCatalog.FindLatestReceiptForSubject(package.PackageId, "follow", subject.SubjectId) is { } followReceipt
                ? BuildPackageReceiptCard(followReceipt)
                : null;
        return new PackageDetailPageViewModel(
            Chrome: chrome,
            ScopeLabel: scopeLabel,
            Package: packageEntry,
            CompatibilityNotes: package.CompatibilityNotes,
            GovernanceNotes: package.GovernanceNotes,
            RecentReceipts: _packageCatalog.ListReceiptsForPackage(package.PackageId, 8)
                .Select(BuildPackageReceiptCard)
                .ToArray(),
            LatestVoteReceipt: latestVoteReceipt,
            LatestFollowReceipt: latestFollowReceipt,
            CanInteract: authenticated,
            CanRevokeVote: latestVoteReceipt is not null,
            CanRevokeFollow: latestFollowReceipt is not null,
            VoteActionHref: authenticated
                ? $"/packages/{Uri.EscapeDataString(package.PackageId)}/vote"
                : $"/login?next={Uri.EscapeDataString($"/packages/{package.PackageId}")}",
            FollowActionHref: authenticated
                ? $"/packages/{Uri.EscapeDataString(package.PackageId)}/follow"
                : $"/signup?next={Uri.EscapeDataString($"/packages/{package.PackageId}")}",
            RevokeVoteActionHref: authenticated ? $"/packages/{Uri.EscapeDataString(package.PackageId)}/vote/revoke" : null,
            RevokeFollowActionHref: authenticated ? $"/packages/{Uri.EscapeDataString(package.PackageId)}/follow/revoke" : null,
            VoteActionLabel: authenticated ? "Vote for this package" : "Sign in to vote",
            FollowActionLabel: authenticated ? "Follow this package" : "Create account to follow",
            PrimaryAction: new TrustPageActionViewModel(package.PrimaryActionLabel, package.PrimaryActionHref, "primary"),
            SecondaryAction: secondaryAction,
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: user is null ? null : _signedInTrustStatus.Build(user, manifest, releaseExperience));
    }

    private async Task<IActionResult> BuildPackageActionReceiptPage(
        string packageId,
        string receiptId,
        string expectedActionKind,
        CancellationToken cancellationToken)
    {
        PublicPackageDefinition? package = _packageCatalog.FindPackage(packageId);
        PublicPackageReceipt? receipt = _packageCatalog.FindReceipt(receiptId);
        bool actionKindMatches = receipt is not null
            && (string.Equals(receipt.ActionKind, expectedActionKind, StringComparison.OrdinalIgnoreCase)
                || string.Equals(receipt.ActionKind, $"revoke_{expectedActionKind}", StringComparison.OrdinalIgnoreCase));
        if (package is null
            || receipt is null
            || !string.Equals(receipt.PackageId, package.PackageId, StringComparison.OrdinalIgnoreCase)
            || !actionKindMatches)
        {
            return NotFound();
        }

        AuthenticatedHubSubject? subject = await TryGetOptionalSubjectAsync(cancellationToken);
        HubUserDto? user = subject is null ? null : _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        string currentPath = $"/packages/{Uri.EscapeDataString(package.PackageId)}/{Uri.EscapeDataString(expectedActionKind)}/{Uri.EscapeDataString(receipt.ReceiptId)}";
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), subject is not null);
        SiteChromeViewModel chrome = subject is not null && user is not null
            ? _chrome.BuildAuthenticatedChrome(
                $"{BuildPackageActionLabel(receipt.ActionKind)} receipt",
                receipt.RouteSummary,
                currentPath,
                user.DisplayName,
                user.Email)
            : await BuildPublicOrAuthenticatedChromeAsync(
                $"{BuildPackageActionLabel(receipt.ActionKind)} receipt",
                receipt.RouteSummary,
                currentPath,
                cancellationToken);
        PackageCatalogEntryViewModel packageEntry = BuildPackageCatalogEntry(package, "/packages");
        PackageReceiptCardViewModel receiptCard = BuildPackageReceiptCard(receipt);
        return View(
            "~/Views/PublicLanding/PackageReceipt.cshtml",
            new PackageActionReceiptPageViewModel(
                Chrome: chrome,
                Eyebrow: "First-party package receipt",
                Heading: $"{BuildPackageActionLabel(receipt.ActionKind)} recorded",
                Intro: "This receipt stays inside Chummer-owned package routes so package interest, compatibility posture, and later follow-through do not disappear into an external board or generic support thread.",
                Package: packageEntry,
                Receipt: receiptCard,
                PrimaryAction: new TrustPageActionViewModel("Open package detail", $"/packages/{Uri.EscapeDataString(package.PackageId)}", "primary"),
                SecondaryAction: subject is null
                    ? new TrustPageActionViewModel("Create account for tracked packages", "/signup?next=%2Faccount%2Fpackages", "secondary")
                    : new TrustPageActionViewModel("Open account packages", "/account/packages", "secondary"),
                TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
                SignedInStatus: user is null ? null : _signedInTrustStatus.Build(user, manifest, releaseExperience)));
    }

    private async Task<IActionResult> RevokePackageAction(
        string packageId,
        string actionKind,
        CancellationToken cancellationToken)
    {
        PublicPackageDefinition? package = _packageCatalog.FindPackage(packageId);
        if (package is null)
        {
            return NotFound();
        }

        string currentPath = $"/packages/{Uri.EscapeDataString(package.PackageId)}";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            PublicPackageReceipt receipt = _packageCatalog.RecordRevoke(package.PackageId, actionKind, subject.SubjectId, user.DisplayName);
            return Redirect($"/packages/{Uri.EscapeDataString(package.PackageId)}/{Uri.EscapeDataString(actionKind)}/{Uri.EscapeDataString(receipt.ReceiptId)}");
        }
        catch (InvalidOperationException)
        {
            return Redirect($"{currentPath}#community-actions");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Package {ActionKind} revoke could not confirm the signed-in identity.", actionKind);
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    private async Task<KnowledgeFabricPageViewModel> BuildKnowledgeFabricPageModel(CancellationToken cancellationToken)
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalSubjectAsync(cancellationToken);
        HubUserDto? user = subject is null ? null : _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), subject is not null);
        SiteChromeViewModel chrome = subject is not null && user is not null
            ? _chrome.BuildAuthenticatedChrome("Knowledge Fabric", "Source-aware explain, provenance, and public-safe receipts on one first-party rail.", "/rules", user.DisplayName, user.Email)
            : await BuildPublicOrAuthenticatedChromeAsync("Knowledge Fabric", "Source-aware explain, provenance, and public-safe receipts on one first-party rail.", "/rules", cancellationToken);

        return new KnowledgeFabricPageViewModel(
            Chrome: chrome,
            Eyebrow: "Trust horizon",
            Heading: "Knowledge Fabric",
            Intro: "This page turns rules trust into an inspectable surface: provenance, source-safe summaries, and downloadable explain receipts stay attached without leaking copyrighted text or private campaign state.",
            SummaryPoints:
            [
                "Provenance stays attached",
                "Source-safe summaries only",
                "Explain receipts stay downloadable"
            ],
            Receipts: _knowledgeFabric.ListReceipts()
                .Select(receipt => new KnowledgeFabricReceiptViewModel(receipt.ReceiptId, receipt.Topic, receipt.Summary, receipt.Provenance, receipt.Route, receipt.Status))
                .ToArray(),
            PrimaryAction: new TrustPageActionViewModel("Open receipt index JSON", "/rules/receipts", "primary"),
            SecondaryAction: new TrustPageActionViewModel("See what works today", "/now#real-rules-truth", "secondary"),
            TertiaryAction: new TrustPageActionViewModel("Open packages", "/packages", "ghost"),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: user is null ? null : _signedInTrustStatus.Build(user, manifest, releaseExperience));
    }

    private async Task<MobileProjectionPageViewModel> BuildMobileProjectionPageModel(
        string currentPath,
        string chromeTitle,
        string chromeDescription,
        string eyebrow,
        string heading,
        string intro,
        string currentRoleKey,
        TrustPageActionViewModel primaryAction,
        TrustPageActionViewModel secondaryAction,
        CancellationToken cancellationToken)
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalSubjectAsync(cancellationToken);
        HubUserDto? user = subject is null ? null : _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), subject is not null);
        var continuitySummary = _nexusPan.BuildPublicSummary();
        SiteChromeViewModel chrome = subject is not null && user is not null
            ? _chrome.BuildAuthenticatedChrome(chromeTitle, chromeDescription, currentPath, user.DisplayName, user.Email)
            : await BuildPublicOrAuthenticatedChromeAsync(chromeTitle, chromeDescription, currentPath, cancellationToken);
        return new MobileProjectionPageViewModel(
            Chrome: chrome,
            Eyebrow: eyebrow,
            Heading: heading,
            Intro: intro,
            CurrentRoleLabel: ResolvePlayRoleLabel(currentRoleKey),
            InstallabilitySummary: $"The public rail names the installable PWA posture, reconnect expectations, and role entry routes without pretending the mobile shell replaces downloads, support, or deeper campaign work. Claimed installs currently tracked: {continuitySummary.ActiveInstallationCount}; pending recovery rails: {continuitySummary.PendingClaimCount + continuitySummary.PendingBrowserCallbackCount}.",
            Roles:
            [
                new MobileRoleCardViewModel("Player", "Resume the session, keep the dossier visible, and re-enter with reconnect posture already named.", "/player", string.Equals(currentRoleKey, "player", StringComparison.OrdinalIgnoreCase)),
                new MobileRoleCardViewModel("GM", "Keep the next scene, continuity, and return posture visible without dropping back to legacy aliases.", "/gm", string.Equals(currentRoleKey, "gm", StringComparison.OrdinalIgnoreCase)),
                new MobileRoleCardViewModel("Observer", "Join the same bounded play shell in a read-mostly role when the table only needs visibility.", "/observer", string.Equals(currentRoleKey, "observer", StringComparison.OrdinalIgnoreCase))
            ],
            Capabilities:
            [
                new MobileCapabilityCardViewModel("Installable PWA posture", "The public route keeps the installable shell, trusted entry point, and fallback posture on first-party routes."),
                new MobileCapabilityCardViewModel("Offline and reconnect", "Continuity, reconnect, and next-safe-action posture remain visible before the network starts wobbling."),
                new MobileCapabilityCardViewModel("Role-aware entry", "Player, GM, and observer aliases all converge on the same bounded play shell instead of splitting product truth."),
                new MobileCapabilityCardViewModel("Claimed install truth", $"Active claimed installs: {continuitySummary.ActiveInstallationCount}; active grants: {continuitySummary.ActiveGrantCount}; observed platforms: {string.Join(", ", continuitySummary.PlatformLabels.DefaultIfEmpty("none yet"))}."),
                new MobileCapabilityCardViewModel("Downloads stay separate", "Mobile entry explains play posture; Downloads still owns platform choice, build integrity, and guided acquisition.")
            ],
            PrimaryAction: primaryAction,
            SecondaryAction: secondaryAction,
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: user is null ? null : _signedInTrustStatus.Build(user, manifest, releaseExperience));
    }

    private async Task<NexusPanContinuityPageViewModel> BuildNexusPanContinuityPageModel(CancellationToken cancellationToken)
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalSubjectAsync(cancellationToken);
        HubUserDto? user = subject is null ? null : _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), subject is not null);
        var summary = _nexusPan.BuildPublicSummary();
        SiteChromeViewModel chrome = subject is not null && user is not null
            ? _chrome.BuildAuthenticatedChrome("NEXUS-PAN continuity", "Claimed installs, reconnect posture, and public-safe continuity receipts on a first-party rail.", "/play/continuity", user.DisplayName, user.Email)
            : await BuildPublicOrAuthenticatedChromeAsync("NEXUS-PAN continuity", "Claimed installs, reconnect posture, and public-safe continuity receipts on a first-party rail.", "/play/continuity", cancellationToken);

        string platformSummary = summary.PlatformLabels.Count == 0
            ? "No claimed-install platform labels are public yet, but the route still proves the continuity contract and the public/private boundary."
            : $"Observed claimed-install platforms on the first-party rail: {string.Join(", ", summary.PlatformLabels)}.";

        return new NexusPanContinuityPageViewModel(
            Chrome: chrome,
            Eyebrow: "Continuity horizon",
            Heading: "NEXUS-PAN continuity",
            Intro: "This route is no longer vague preview copy. It exposes the real continuity contract: claimed installs, reconnect posture, public-safe receipts, and the explicit boundary where signed-in runboard state begins.",
            VerdictSummary: "Continuity is now a first-party MVP surface: the public route shows aggregate install and recovery posture, while deeper device and workspace history stays on signed-in rails.",
            PlatformSummary: platformSummary,
            SummaryPoints:
            [
                "Claimed install truth stays first-party",
                "Reconnect posture stays inspectable",
                "Signed-in runboard history stays private"
            ],
            ActiveInstallationCount: summary.ActiveInstallationCount,
            ActiveGrantCount: summary.ActiveGrantCount,
            PendingClaimCount: summary.PendingClaimCount,
            PendingBrowserCallbackCount: summary.PendingBrowserCallbackCount,
            PlatformLabels: summary.PlatformLabels.Count == 0 ? ["No public platform labels yet"] : summary.PlatformLabels,
            Receipts: _nexusPan.ListReceipts()
                .Select(receipt => new NexusPanReceiptViewModel(receipt.ReceiptId, receipt.Topic, receipt.Summary, receipt.Route, receipt.Status))
                .ToArray(),
            PrimaryAction: new TrustPageActionViewModel("Open receipt index JSON", "/play/continuity/receipts", "primary"),
            SecondaryAction: new TrustPageActionViewModel("Open mobile and PWA", "/mobile", "secondary"),
            TertiaryAction: new TrustPageActionViewModel("Open mobile PWA JSON", "/mobile/pwa.json", "ghost"),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: user is null ? null : _signedInTrustStatus.Build(user, manifest, releaseExperience));
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildJackpointPageModel(CancellationToken cancellationToken)
        => await BuildMediaArtifactHorizonPageModel(
            currentPath: "/jackpoint",
            title: "JACKPOINT briefings",
            description: "Player-safe dossier cards, mission briefs, and first-party artifact packets.",
            eyebrow: "Media horizon",
            heading: "JACKPOINT briefings",
            intro: "JACKPOINT is now a real packet lane: dossier cards and mission briefs can be opened as first-party markdown or JSON instead of surviving only as horizon prose.",
            boundaryLine: "Player-safe dossier and mission-brief output only. GM-private spoilers and private campaign notes stay off the public rail.",
            summaryPoints: ["Dossier cards", "Mission brief packets", "Public-safe artifact rail"],
            documents: _mediaHorizons.ListJackpointBriefings(),
            primaryAction: new TrustPageActionViewModel("Open first briefing", "/jackpoint/briefings/emerald-sprawl-briefing.md", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open JSON packet", "/jackpoint/briefings/emerald-sprawl-briefing.json", "secondary"),
            tertiaryAction: new TrustPageActionViewModel("Open artifacts", "/artifacts", "ghost"),
            cancellationToken: cancellationToken);

    private async Task<MediaArtifactHorizonPageViewModel> BuildRunsitePageModel(CancellationToken cancellationToken)
        => await BuildMediaArtifactHorizonPageModel(
            currentPath: "/runsites",
            title: "RUNSITE packets",
            description: "Site cards, threat clocks, and first-party runsite packets.",
            eyebrow: "Packet horizon",
            heading: "RUNSITE packets",
            intro: "RUNSITE now ships as a packet lane: site cards, pressure clocks, and entry/exit notes live on real routes instead of generic preview copy.",
            boundaryLine: "Spatial-prep packet only. This rail does not claim tactical overlays, live map authority, or full VTT integration.",
            summaryPoints: ["Site cards", "Threat clocks", "Entry and exit notes"],
            documents: _mediaHorizons.ListRunsitePacks(),
            primaryAction: new TrustPageActionViewModel("Open first runsite pack", "/runsites/packs/redmond-dockyard-pack.md", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open JSON pack", "/runsites/packs/redmond-dockyard-pack.json", "secondary"),
            tertiaryAction: new TrustPageActionViewModel("Open runbook", "/runbook", "ghost"),
            cancellationToken: cancellationToken);

    private async Task<MediaArtifactHorizonPageViewModel> BuildRunbookPageModel(CancellationToken cancellationToken)
        => await BuildMediaArtifactHorizonPageModel(
            currentPath: "/runbook",
            title: "RUNBOOK PRESS",
            description: "Printable primers and first-session onboarding packets.",
            eyebrow: "Primer horizon",
            heading: "RUNBOOK PRESS",
            intro: "RUNBOOK PRESS now ships real first-party primers: packets you can hand to a player or GM without sending them into scattered docs.",
            boundaryLine: "Printable onboarding and prep packets only. This rail does not claim a full long-form publication studio yet.",
            summaryPoints: ["New-player primer", "GM primer", "Printable packet posture"],
            documents: _mediaHorizons.ListRunbookPrimers(),
            primaryAction: new TrustPageActionViewModel("Open first primer", "/runbook/primers/new-runner-primer.md", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open primer JSON", "/runbook/primers/new-runner-primer.json", "secondary"),
            tertiaryAction: new TrustPageActionViewModel("Open Ready for Tonight", "/ready", "ghost"),
            cancellationToken: cancellationToken);

    private async Task<MediaArtifactHorizonPageViewModel> BuildCommunityHubPageModel(CancellationToken cancellationToken)
    {
        CommunityHubPublicSummary summary = _communityCreatorHorizons.BuildCommunitySummary();
        return await BuildMediaArtifactHorizonPageModel(
            currentPath: "/community",
            title: "Community Hub",
            description: "Open-run board, organizer closeout posture, and moderation-safe public rails.",
            eyebrow: "Community horizon",
            heading: "Community Hub",
            intro: "Community Hub now ships first-party packet rails: open-run board posture, organizer closeout proof, and moderation boundaries live on real markdown and JSON routes.",
            boundaryLine: "Public route shows board posture and safety boundaries only. Private roster notes, meeting access, and case handling stay signed-in.",
            summaryPoints:
            [
                $"{summary.OpenRuns.Count} open runs visible",
                $"{summary.PendingJoinCount} pending join requests",
                $"{summary.CloseoutCount} closeouts on record"
            ],
            documents: _communityCreatorHorizons.ListCommunityDocuments().Select(item => new MediaArtifactDocument(item.Id, item.Label, item.Summary, item.MarkdownRoute, item.JsonRoute, item.Highlights)).ToArray(),
            primaryAction: new TrustPageActionViewModel("Open run board packet", "/community/open-runs/open_run_board.md", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open JSON board", "/community/open-runs/open_run_board.json", "secondary"),
            tertiaryAction: new TrustPageActionViewModel("Open participate", "/participate", "ghost"),
            cancellationToken: cancellationToken);
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildCreatorOsPageModel(CancellationToken cancellationToken)
    {
        CreatorOsPublicSummary summary = _communityCreatorHorizons.BuildCreatorSummary();
        return await BuildMediaArtifactHorizonPageModel(
            currentPath: "/creator",
            title: "Creator OS",
            description: "Governed publication discovery, trust posture, and campaign return loops.",
            eyebrow: "Creator horizon",
            heading: "Creator OS",
            intro: "Creator OS now ships first-party publication packets: governed discovery, trust-boundary receipts, and campaign-return posture on real routes.",
            boundaryLine: "Creator truth comes from Chummer-owned publication receipts. Private review state and provider dashboards stay off the public lane.",
            summaryPoints:
            [
                $"{summary.Publications.Count} discoverable publications",
                $"{summary.CuratedLiveCount} curated live",
                $"{summary.ReturnLoopCount} with campaign return summaries"
            ],
            documents: _communityCreatorHorizons.ListCreatorDocuments().Select(item => new MediaArtifactDocument(item.Id, item.Label, item.Summary, item.MarkdownRoute, item.JsonRoute, item.Highlights)).ToArray(),
            primaryAction: new TrustPageActionViewModel("Open publication board", "/creator/packets/publication_board.md", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open publication JSON", "/creator/packets/publication_board.json", "secondary"),
            tertiaryAction: new TrustPageActionViewModel("Open artifacts", "/artifacts", "ghost"),
            cancellationToken: cancellationToken);
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildRunnerPassportPageModel(CancellationToken cancellationToken)
    {
        RunnerPassportPublicSummary summary = _communityCreatorHorizons.BuildPassportSummary();
        return await BuildMediaArtifactHorizonPageModel(
            currentPath: "/passport",
            title: "Runner Passport",
            description: "Public-safe runner return posture, participation proof, and bounded cross-table trust.",
            eyebrow: "Identity horizon",
            heading: "Runner Passport",
            intro: "Runner Passport now ships real public-safe receipts: runner return posture, bounded cross-table trust, and privacy-safe participation proof on first-party routes.",
            boundaryLine: "The public lane exposes aggregate readiness and trust boundaries only. Private identity links, moderation state, and account recovery stay signed-in.",
            summaryPoints:
            [
                $"{summary.ActiveInstallationCount} active claimed installs",
                $"{summary.OpenRunCount} open runs on the public board",
                $"{summary.PendingJoinCount} pending join requests"
            ],
            documents: _communityCreatorHorizons.ListPassportDocuments().Select(item => new MediaArtifactDocument(item.Id, item.Label, item.Summary, item.MarkdownRoute, item.JsonRoute, item.Highlights)).ToArray(),
            primaryAction: new TrustPageActionViewModel("Open runner return receipt", "/passport/receipts/runner_return_posture.md", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open receipt JSON", "/passport/receipts/runner_return_posture.json", "secondary"),
            tertiaryAction: new TrustPageActionViewModel("Open community", "/community", "ghost"),
            cancellationToken: cancellationToken);
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildGhostwirePageModel(CancellationToken cancellationToken)
    {
        GhostwirePublicSummary summary = _waveEightHorizons.BuildGhostwireSummary();
        return await BuildMediaArtifactHorizonPageModel(
            currentPath: "/ghostwire",
            title: "GHOSTWIRE after-action",
            description: "Receipt-backed replay packets, after-action reports, and consequence carry-forward.",
            eyebrow: "Replay horizon",
            heading: "GHOSTWIRE after-action",
            intro: "GHOSTWIRE now ships first-party after-action packet rails: replay timelines, after-action reports, and consequence-chain packets live on real markdown and JSON routes.",
            boundaryLine: "Replay stays receipt-backed and public-safe. No private transcript lane and no retrospective fiction engine are claimed here.",
            summaryPoints:
            [
                $"{summary.Packages.Count} aftermath packets on record",
                $"{summary.AfterActionCount} after-action reports",
                $"{summary.ReplayCount} replay timelines"
            ],
            documents: _waveEightHorizons.ListGhostwireDocuments().Select(item => new MediaArtifactDocument(item.Id, item.Label, item.Summary, item.MarkdownRoute, item.JsonRoute, item.Highlights)).ToArray(),
            primaryAction: new TrustPageActionViewModel("Open replay timeline", "/ghostwire/after-action/replay_timeline.md", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open replay JSON", "/ghostwire/after-action/replay_timeline.json", "secondary"),
            tertiaryAction: new TrustPageActionViewModel("Open ledger", "/ledger", "ghost"),
            cancellationToken: cancellationToken);
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildMediaArtifactHorizonPageModel(
        string currentPath,
        string title,
        string description,
        string eyebrow,
        string heading,
        string intro,
        string boundaryLine,
        IReadOnlyList<string> summaryPoints,
        IReadOnlyList<MediaArtifactDocument> documents,
        TrustPageActionViewModel primaryAction,
        TrustPageActionViewModel secondaryAction,
        TrustPageActionViewModel tertiaryAction,
        CancellationToken cancellationToken)
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalSubjectAsync(cancellationToken);
        HubUserDto? user = subject is null ? null : _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), subject is not null);
        SiteChromeViewModel chrome = subject is not null && user is not null
            ? _chrome.BuildAuthenticatedChrome(title, description, currentPath, user.DisplayName, user.Email)
            : await BuildPublicOrAuthenticatedChromeAsync(title, description, currentPath, cancellationToken);
        return new MediaArtifactHorizonPageViewModel(
            Chrome: chrome,
            Eyebrow: eyebrow,
            Heading: heading,
            Intro: intro,
            BoundaryLine: boundaryLine,
            SummaryPoints: summaryPoints,
            Documents: documents.Select(item => new MediaArtifactCardViewModel(item.Id, item.Label, item.Summary, item.MarkdownRoute, item.JsonRoute, item.Highlights)).ToArray(),
            PrimaryAction: primaryAction,
            SecondaryAction: secondaryAction,
            TertiaryAction: tertiaryAction,
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: user is null ? null : _signedInTrustStatus.Build(user, manifest, releaseExperience));
    }

    private PackageCatalogEntryViewModel BuildPackageCatalogEntry(PublicPackageDefinition package, string detailBasePath)
        => new(
            PackageId: package.PackageId,
            Title: package.Title,
            Summary: package.Summary,
            ClassLabel: package.PackageClassLabel,
            StatusLabel: package.StatusLabel,
            CompatibilitySummary: package.CompatibilityNotes.FirstOrDefault() ?? "Compatibility posture stays explicit.",
            GovernanceSummary: package.GovernanceNotes.FirstOrDefault() ?? "Governance posture stays explicit.",
            EvidenceSummary: package.EvidenceSummary,
            VoteCount: _packageCatalog.CountUniqueReceipts(package.PackageId, "vote"),
            FollowCount: _packageCatalog.CountUniqueReceipts(package.PackageId, "follow"),
            DetailHref: $"{detailBasePath.TrimEnd('/')}/{Uri.EscapeDataString(package.PackageId)}");

    private PackageReceiptCardViewModel BuildPackageReceiptCard(PublicPackageReceipt receipt)
    {
        string packageTitle = _packageCatalog.FindPackage(receipt.PackageId)?.Title ?? receipt.PackageId;
        return new PackageReceiptCardViewModel(
            ReceiptId: receipt.ReceiptId,
            PackageId: receipt.PackageId,
            PackageTitle: packageTitle,
            ActionLabel: BuildPackageActionLabel(receipt.ActionKind),
            ActorLabel: receipt.ActorLabel,
            RouteSummary: receipt.RouteSummary,
            RecordedAtLabel: receipt.RecordedAtUtc.ToUniversalTime().ToString("yyyy-MM-dd HH:mm 'UTC'"),
            Href: $"/packages/{Uri.EscapeDataString(receipt.PackageId)}/{Uri.EscapeDataString(receipt.ActionKind)}/{Uri.EscapeDataString(receipt.ReceiptId)}");
    }

    private static string BuildPackageActionLabel(string actionKind)
        => actionKind.Trim().ToLowerInvariant() switch
        {
            "follow" => "Follow",
            "revoke_follow" => "Follow revoked",
            "revoke_vote" => "Vote revoked",
            _ => "Vote"
        };

    private async Task<ReadyForTonightPageViewModel> BuildReadyForTonightPageModel(CancellationToken cancellationToken)
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalSubjectAsync(cancellationToken);
        HubUserDto? user = subject is null ? null : _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), subject is not null);
        SiteChromeViewModel chrome = subject is not null && user is not null
            ? _chrome.BuildAuthenticatedChrome("Ready for Tonight", "Get a player, GM, or organizer to a usable session packet without pretending the whole product collapses into one screen.", "/ready", user.DisplayName, user.Email)
            : await BuildPublicOrAuthenticatedChromeAsync("Ready for Tonight", "Role verdicts, starter loadouts, and packet exports for the shortest honest route into tonight's run.", "/ready", cancellationToken);

        var verdicts = _readyForTonight.ListRoleVerdicts()
            .Select(verdict => new ReadyVerdictCardViewModel(
                verdict.RoleId,
                verdict.RoleLabel,
                verdict.Status,
                verdict.StatusLabel,
                verdict.Summary,
                verdict.BlockingReasons,
                verdict.ChangedSinceLastSession,
                verdict.FixNowActions.Select(action => new TrustPageActionViewModel(action.Label, action.Href, action.Tone)).ToArray(),
                verdict.NextBestScreen,
                verdict.ProofReceipts))
            .ToArray();
        var kits = _readyForTonight.ListRoleKits()
            .Select(kit => new ReadyRoleKitViewModel(kit.KitId, kit.RoleLane, kit.Label, kit.Summary, kit.DownloadHref, kit.Highlights))
            .ToArray();
        var packets = _readyForTonight.ListPacketAssets()
            .Select(packet => new ReadyPacketAssetViewModel(packet.RoleId, packet.Label, packet.Summary, packet.MarkdownHref, packet.JsonHref))
            .ToArray();

        return new ReadyForTonightPageViewModel(
            Chrome: chrome,
            Eyebrow: "Session-start mode",
            Heading: "Ready for Tonight",
            Intro: "This page answers the only urgent question before a game starts: are you ready, what still blocks you, and which packet should you carry into the session right now.",
            VerdictSummary: "Chummer now ships one bounded first-party session-start rail: role verdict, starter loadout, packet export, and mobile handoff in one place.",
            SummaryPoints:
            [
                "Role-aware readiness verdicts",
                "Starter loadouts with downloadable JSON",
                "Printable packets and mobile handoff"
            ],
            Verdicts: verdicts,
            RoleKits: kits,
            Packets: packets,
            PrimaryAction: new TrustPageActionViewModel("Download player packet", "/ready/packet/player.md", "primary"),
            SecondaryAction: new TrustPageActionViewModel("Open mobile and PWA", "/mobile", "secondary"),
            TertiaryAction: new TrustPageActionViewModel("Open help", "/help", "ghost"),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: user is null ? null : _signedInTrustStatus.Build(user, manifest, releaseExperience));
    }

    private static string NormalizePlayRole(string? role)
        => role?.Trim().ToLowerInvariant() switch
        {
            "gm" => "gm",
            "observer" => "observer",
            _ => "player"
        };

    private static string ResolvePlayRoleLabel(string role)
        => string.Equals(role, "gm", StringComparison.OrdinalIgnoreCase)
            ? "GM"
            : string.Equals(role, "observer", StringComparison.OrdinalIgnoreCase)
                ? "Observer"
                : "Player";

    private static KarmaForgeSubmissionProjection BuildSampleKarmaForgeSubmission()
    {
        KarmaForgePrioritySignalsProjection prioritySignals = new(
            BlockerScore: 4,
            FrequencySignal: "repeatable",
            ShareabilityScore: 4,
            ImplementationRisk: "bounded",
            MonetizationRelevance: "retention");
        HouseRuleDemandPacketProjection packet = new(
            Id: "hrp_2026_05_09_sample_karma_forge",
            Title: "Sample campaign amendment packet",
            Source: new KarmaForgeSourceProjection(
                IntakeChannel: "Hub Participate",
                CanonicalLane: "KARMA_FORGE",
                RespondentRole: "GM",
                Edition: "SR5",
                TableType: "home_campaign",
                TrackKey: "gm_house_rule_track",
                InterviewTrack: "GM house rule track",
                RuleCategory: "campaign_progression",
                Severity: "session_friction",
                InterviewRef: "hub_karma_forge_sample_submission",
                ConsentRef: "hub_karma_forge_sample_consent",
                ExternalStages: Array.Empty<KarmaForgeExternalStageProjection>(),
                JourneyProofEventRefs:
                [
                    new("karma_request_submitted", "karma_forge_discovery", "hrp_2026_05_09_sample_karma_forge", "The public discovery request entered the first-party KARMA FORGE intake lane."),
                    new("karma_interview_completed", "karma_forge_discovery", "hrp_2026_05_09_sample_karma_forge", "Guided follow-up completed inside the bounded KARMA FORGE discovery chain."),
                    new("karma_demand_packet_created", "karma_forge_discovery", "hrp_2026_05_09_sample_karma_forge", "The intake normalized into a Chummer-owned demand packet before Product Governor review."),
                    new("karma_candidate_reviewed", "karma_forge_discovery", "hrp_2026_05_09_sample_karma_forge", "The candidate is visible on the governed review rail instead of staying provider-owned.")
                ]),
            UserWords: new KarmaForgeUserWordsProjection(
                Summary: "We need a governed table amendment that survives continuity and rollback without hiding the approval trail.",
                CurrentWorkaround: "We keep the rule in chat and manually restate it before every session."),
            InterpretedNeed: new KarmaForgeInterpretedNeedProjection(
                Summary: "Campaign-scoped amendment package with visible compatibility, portability, and rollback posture.",
                Confidence: "high"),
            AffectedDomains: ["campaign_progression", "character_build_legality"],
            DesiredScope: ["campaign", "shared_workspace"],
            LikelyChummerObjects: ["rule_environment", "after_action_receipt"],
            PossibleBlackLedgerObjects: ["campaign_notice"],
            TrustRequirements: new KarmaForgeTrustRequirementsProjection(
                PlayerVisibleBeforeJoin: true,
                BuildDiffRequired: true,
                RollbackRequired: true,
                ApprovalRequired: true,
                ReceiptRequired: true),
            PortabilityRequirements: new KarmaForgePortabilityRequirementsProjection(
                CrossDeviceRestore: true,
                PackageFingerprintRequired: true),
            PrioritySignals: prioritySignals,
            Classification: new KarmaForgeClassificationProjection(
                CurrentStatus: "candidate",
                DecisionNeeded: true,
                CandidateDecision: "campaign_rule_package",
                CandidateDecisionMeaning: "Needs a governed campaign package lane before broader rollout.",
                ProposedRoute: "KARMA_FORGE"),
            NextSteps:
            [
                "Review the campaign scope and rollback posture.",
                "Attach compatibility and portability notes before approval.",
                "Keep the public receipt bounded to first-party package language."
            ],
            OperatorNotes: new KarmaForgeOperatorNotesProjection(
                FeedbackPrompt: "What needs to stay stable when the campaign amendment changes?",
                ImpactNotes: "Touches campaign continuity, player visibility, and rollback posture.",
                ShareabilityNotes: "Portable across the same campaign workspace once approved."));
        KarmaForgeCandidateProjection candidate = new(
            Id: "kfc_hrp_2026_05_09_sample_karma_forge",
            Title: packet.Title,
            LinkedPacketId: packet.Id,
            TrackKey: "gm_house_rule_track",
            TrackTitle: "GM house rule track",
            CandidateDecision: "campaign_rule_package",
            CandidateDecisionMeaning: "Needs a governed campaign package lane before broader rollout.",
            ProposedRoute: "KARMA_FORGE",
            GovernorDecisionRequired: true,
            Confidence: "high",
            PrioritySignals: prioritySignals);
        RuleEnvironmentImpactHypothesisProjection impactHypothesis = new(
            Id: "reh_hrp_2026_05_09_sample_karma_forge",
            Title: packet.Title,
            Summary: packet.InterpretedNeed.Summary,
            AffectedDomains: packet.AffectedDomains,
            LikelyObjects: packet.LikelyChummerObjects,
            PossibleBlackLedgerObjects: packet.PossibleBlackLedgerObjects,
            TrustPressure: ["player_visible_before_join", "build_diff_required", "rollback_required", "approval_required"],
            PortabilityPressure: ["cross_device_restore", "package_fingerprint_required"],
            RolloutScope: ["campaign", "shared_workspace"],
            ComparisonSurface: "build_diff",
            PlayerVisibility: "before_join",
            RollbackSurface: "rollback_required");
        return new KarmaForgeSubmissionProjection(
            SubmissionId: "sample-submission-id",
            SubmittedAtUtc: new DateTimeOffset(2026, 5, 9, 7, 30, 0, TimeSpan.Zero),
            IntakeStatus: "packet_normalized",
            QueueStatus: "queued_for_product_governor",
            QueueSummary: "Sample seeded receipt proving the KARMA FORGE submission route with a first-party packet payload.",
            ReporterNextAction: "Open the package or campaign decision rail when you need the next governed step.",
            ConsentSummary: "Sample seeded receipt with follow-up and quote posture enabled for route proof.",
            AuthenticatedSubmission: true,
            FollowUpAllowed: true,
            QuoteAllowed: true,
            SubjectId: "sample-subject",
            SubjectDisplayName: "Sample operator",
            ReplyEmail: "sample@chummer.run",
            NextQuestions:
            [
                "Should this stay campaign-scoped or become a broader package class?",
                "What rollback posture is required before publish?",
                "Which portability notes must remain attached?"
            ],
            Packet: packet,
            Candidate: candidate,
            ImpactHypothesis: impactHypothesis);
    }

    private static HomePrimaryActionViewModel BuildHomePrimaryAction(
        HubUserExperienceDto experience,
        AccountCampaignSummary campaignSpine,
        InstallLinkingSummaryDto installLinking,
        ReleaseExperienceViewModel releaseExperience)
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
            var installActionLabel = releaseExperience.Recommended?.ActionLabel ?? "Open downloads";
            var installActionHref = releaseExperience.Recommended?.DispatchHref ?? "/downloads";
            return new HomePrimaryActionViewModel(
                "Install",
                "Install Chummer",
                "Start with the recommended installer, then come back here when you want to link the installed copy to this account.",
                installActionLabel,
                installActionHref,
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

    private IReadOnlyList<RecapShelfEntry> BuildSignedInArtifactShelfEntries(
        HubUserDto user,
        AccountCampaignSummary campaignSpine,
        InstallLinkingSummaryDto installLinking)
    {
        HashSet<string> seen = new(StringComparer.OrdinalIgnoreCase);
        return campaignSpine.Workspaces
            .Take(3)
            .Select(workspace => _workspaceServerPlane.GetWorkspaceServerPlane(user, workspace.WorkspaceId, installLinking))
            .Where(static workspace => workspace is not null)
            .SelectMany(static workspace => workspace!.RecapShelf)
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .Where(item => seen.Add(BuildArtifactShelfDedupeKey(item)))
            .ToArray();
    }

    private static IReadOnlyList<RecapShelfEntry> BuildSignedInPersonalArtifactShelfEntries(AccountCampaignSummary campaignSpine)
    {
        var campaignsById = campaignSpine.Campaigns.ToDictionary(static item => item.CampaignId, StringComparer.OrdinalIgnoreCase);
        return campaignSpine.Dossiers
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .Take(6)
            .Select(dossier =>
            {
                campaignsById.TryGetValue(dossier.CampaignId ?? string.Empty, out CampaignProjection? campaign);
                string campaignName = campaign?.Name ?? "your account";
                string continuitySummary = string.IsNullOrWhiteSpace(dossier.LatestContinuity?.Summary)
                    ? $"{campaignName} can reopen this runner from the same governed dossier artifact."
                    : dossier.LatestContinuity!.Summary;
                string provenanceSummary = $"{dossier.RuleEnvironment.CompatibilityFingerprint} + {continuitySummary}";
                string auditSummary = dossier.LatestContinuity is null
                    ? "No governed continuity snapshot is attached yet."
                    : $"Continuity snapshot {dossier.LatestContinuity.SnapshotId} was captured at {dossier.LatestContinuity.CapturedAtUtc:yyyy-MM-dd HH:mm} UTC.";
                return new RecapShelfEntry(
                    EntryId: $"dossier:{dossier.DossierId}",
                    Kind: "dossier_projection",
                    Label: $"{dossier.DisplayName} dossier",
                    Summary: continuitySummary,
                    ArtifactId: dossier.DossierId,
                    UpdatedAtUtc: dossier.UpdatedAtUtc,
                    Audience: "personal,campaign",
                    OwnershipSummary: $"{campaignName} reuses the same governed dossier artifact on the signed-in account path instead of forking a shadow copy.",
                    PublicationState: "personal_ready",
                    TrustBand: null,
                    Discoverable: false,
                    PublicationSummary: $"Personal and campaign views already share this {campaignName} artifact without requiring a second export lane.",
                    CreatorPublicationId: null,
                    NextSafeAction: "Reopen the shared campaign view before you move this runner artifact into another campaign, shelf, or publication step.",
                    ProvenanceSummary: provenanceSummary,
                    AuditSummary: auditSummary);
            })
            .ToArray();
    }

    private static IReadOnlyList<RecapShelfEntry> MergeSignedInArtifactShelfEntries(
        params IReadOnlyList<RecapShelfEntry>[] shelves)
    {
        HashSet<string> seen = new(StringComparer.OrdinalIgnoreCase);
        return shelves
            .SelectMany(static item => item)
            .OrderByDescending(static item => item.UpdatedAtUtc)
            .Where(item => seen.Add(BuildArtifactShelfDedupeKey(item)))
            .ToArray();
    }

    private static IReadOnlyList<RecapShelfEntry> FilterSignedInArtifactShelfEntries(
        IReadOnlyList<RecapShelfEntry> items,
        string signedInArtifactView)
    {
        if (string.Equals(signedInArtifactView, "all", StringComparison.Ordinal))
        {
            return items;
        }

        return items
            .Where(item => MatchesSignedInArtifactView(item, signedInArtifactView))
            .ToArray();
    }

    private static IReadOnlyList<CreatorPublicationProjection> FilterSignedInCreatorPublications(
        IReadOnlyList<CreatorPublicationProjection> items,
        string signedInArtifactView)
    {
        return signedInArtifactView switch
        {
            "all" => items,
            "creator" => items,
            "public" => items
                .Where(static item =>
                    item.Discoverable
                    && string.Equals(item.PublicationStatus, HubPublicationStates.Published, StringComparison.OrdinalIgnoreCase))
                .ToArray(),
            _ => Array.Empty<CreatorPublicationProjection>()
        };
    }

    private static string BuildArtifactShelfDedupeKey(RecapShelfEntry item)
    {
        if (!string.IsNullOrWhiteSpace(item.ArtifactId))
        {
            return $"artifact:{item.ArtifactId}";
        }

        if (!string.IsNullOrWhiteSpace(item.CreatorPublicationId))
        {
            return $"publication:{item.CreatorPublicationId}";
        }

        return $"entry:{item.EntryId}";
    }

    private static string NormalizeSignedInArtifactView(string? rawView)
        => string.IsNullOrWhiteSpace(rawView)
            ? "all"
            : rawView.Trim().ToLowerInvariant() switch
            {
                "all" => "all",
                "personal" => "personal",
                "campaign" => "campaign",
                "creator" => "creator",
                "public" => "public",
                _ => "all"
            };

    private static bool MatchesSignedInArtifactView(RecapShelfEntry item, string signedInArtifactView)
    {
        if (string.Equals(signedInArtifactView, "creator", StringComparison.Ordinal))
        {
            return AudienceContains(item.Audience, "creator")
                || !string.IsNullOrWhiteSpace(item.CreatorPublicationId);
        }

        return AudienceContains(item.Audience, signedInArtifactView);
    }

    private static bool AudienceContains(string? audience, string needle)
    {
        if (string.IsNullOrWhiteSpace(audience))
        {
            return false;
        }

        return audience
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Any(token => string.Equals(token, needle, StringComparison.OrdinalIgnoreCase));
    }

    private static string ResolveArtifactShelfLocale(string? requestedLocale, string? acceptLanguage)
    {
        string? direct = NormalizeArtifactShelfLocaleToken(requestedLocale);
        if (!string.IsNullOrWhiteSpace(direct))
        {
            return direct;
        }

        if (!string.IsNullOrWhiteSpace(acceptLanguage))
        {
            string[] candidates = acceptLanguage
                .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
            foreach (string candidate in candidates)
            {
                string language = candidate.Split(';', 2, StringSplitOptions.TrimEntries)[0];
                string? normalized = NormalizeArtifactShelfLocaleToken(language);
                if (!string.IsNullOrWhiteSpace(normalized))
                {
                    return normalized;
                }
            }
        }

        return "en-US";
    }

    private static string? NormalizeArtifactShelfLocaleToken(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string trimmed = value.Trim().Replace('_', '-');
        string[] parts = trimmed.Split('-', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (parts.Length == 0 || parts.Length > 3)
        {
            return null;
        }

        string language = parts[0].ToLowerInvariant();
        if (language.Length < 2 || language.Length > 8 || !language.All(char.IsLetter))
        {
            return null;
        }

        if (parts.Length == 1)
        {
            return language;
        }

        string region = parts[1].ToUpperInvariant();
        if (region.Length is < 2 or > 8 || !region.All(char.IsLetterOrDigit))
        {
            return null;
        }

        return parts.Length == 2
            ? $"{language}-{region}"
            : $"{language}-{region}-{parts[2].ToUpperInvariant()}";
    }

    private static string ArtifactViewSummaryForApi(string view) => view switch
    {
        "personal" => "Personal shelf view keeps account-side runner artifacts and continuity on the governed personal rail.",
        "campaign" => "Campaign shelf view keeps shared continuity, replay, and aftermath artifacts on the governed campaign rail.",
        "creator" => "Creator shelf view keeps creator-linked lineage, publication posture, and sibling packets together.",
        "public" => "Public shelf view keeps discoverable published creator packets and their public detail routes on one shared rail.",
        _ => "All shelf views keep personal, campaign, creator, and public artifact posture inspectable from one route."
    };

    private static string GuestArtifactViewSummaryForApi(string view) => view switch
    {
        "creator" => "Guest creator shelf view keeps discoverable creator packets, sibling packets, and publication posture together on the public rail.",
        "public" => "Guest public shelf view keeps proof cards, preview posture, and published creator packets on one inspectable route.",
        "personal" => "Personal shelf view requires a signed-in account before private return artifacts can render.",
        "campaign" => "Campaign shelf view requires a signed-in account before shared continuity artifacts can render.",
        _ => "Public proof, preview posture, and governed publication discovery stay on one inspectable artifact rail."
    };

    private static IReadOnlyList<ResolvedPublicCardViewModel> FilterGuestArtifactShelfCards(
        IReadOnlyList<ResolvedPublicCardViewModel> items,
        string artifactView)
        => artifactView switch
        {
            "personal" or "campaign" or "creator" => Array.Empty<ResolvedPublicCardViewModel>(),
            _ => items
        };

    private static IReadOnlyList<CreatorPublicationProjection> FilterGuestArtifactShelfPublications(
        IReadOnlyList<CreatorPublicationProjection> items,
        string artifactView)
        => artifactView switch
        {
            "personal" or "campaign" => Array.Empty<CreatorPublicationProjection>(),
            _ => items
        };

    private static IReadOnlyDictionary<string, int> BuildArtifactShelfViewCounts(
        IReadOnlyList<RecapShelfEntry> signedInArtifactShelf,
        IReadOnlyList<CreatorPublicationProjection> creatorPublications,
        IReadOnlyList<ResolvedPublicCardViewModel> guestCards,
        IReadOnlyList<CreatorPublicationProjection> publicCreatorPublications,
        bool signedIn)
    {
        if (!signedIn)
        {
            int guestVisibleCount = guestCards.Count + publicCreatorPublications.Count;
            return new Dictionary<string, int>(StringComparer.Ordinal)
            {
                ["all"] = guestVisibleCount,
                ["personal"] = 0,
                ["campaign"] = 0,
                ["creator"] = publicCreatorPublications.Count,
                ["public"] = guestVisibleCount
            };
        }

        int guestAllCount = FilterGuestArtifactShelfCards(guestCards, "all").Count
            + FilterGuestArtifactShelfPublications(publicCreatorPublications, "all").Count;
        int guestCreatorCount = FilterGuestArtifactShelfPublications(publicCreatorPublications, "creator").Count;
        int guestPublicCount = FilterGuestArtifactShelfCards(guestCards, "public").Count
            + FilterGuestArtifactShelfPublications(publicCreatorPublications, "public").Count;
        int allCount = signedInArtifactShelf.Count + creatorPublications.Count + guestAllCount;
        int personalCount = FilterSignedInArtifactShelfEntries(signedInArtifactShelf, "personal").Count;
        int campaignCount = FilterSignedInArtifactShelfEntries(signedInArtifactShelf, "campaign").Count;
        int creatorCount = FilterSignedInArtifactShelfEntries(signedInArtifactShelf, "creator").Count
            + creatorPublications.Count
            + guestCreatorCount;
        int publicCount = FilterSignedInCreatorPublications(creatorPublications, "public").Count + guestPublicCount;
        return new Dictionary<string, int>(StringComparer.Ordinal)
        {
            ["all"] = allCount,
            ["personal"] = personalCount,
            ["campaign"] = campaignCount,
            ["creator"] = creatorCount,
            ["public"] = publicCount
        };
    }

    private static object BuildArtifactShelfViewPayload(string view, IReadOnlyDictionary<string, int> viewCounts)
        => new
        {
            view,
            title = view switch
            {
                "personal" => "Personal view",
                "campaign" => "Campaign view",
                "creator" => "Creator view",
                "public" => "Public view",
                _ => "All views"
            },
            summary = ArtifactViewSummaryForApi(view),
            itemCount = viewCounts.TryGetValue(view, out int count) ? count : 0
        };

    private static object BuildArtifactShelfRetentionPayload(PrivacyBoundaryPanelViewModel retention)
        => new
        {
            heading = retention.Heading,
            summary = retention.Summary,
            domains = retention.Domains.Select(domain => new
            {
                id = NormalizeRetentionDomainId(domain.Label),
                domain.Label,
                domain.Owner,
                domain.RetentionSummary,
                domain.RedactionSummary
            })
        };

    private static string BuildArtifactShelfRetentionSummary(PrivacyBoundaryPanelViewModel retention, string domainId)
    {
        PrivacyBoundaryDomainViewModel? domain = retention.Domains.FirstOrDefault(item =>
            string.Equals(NormalizeRetentionDomainId(item.Label), domainId, StringComparison.Ordinal));
        return domain?.RetentionSummary ?? retention.Summary;
    }

    private static string NormalizeRetentionDomainId(string label)
        => label.Trim().ToLowerInvariant().Replace(" ", "_");

    private static object BuildArtifactShelfCardPayload(
        ResolvedPublicCardViewModel card,
        string locale,
        string retentionSummary)
        => new
        {
            id = card.Card.Id,
            title = card.Card.Title,
            summary = card.Card.Summary,
            caption = string.IsNullOrWhiteSpace(card.Asset?.Caption) ? card.Card.Title : card.Asset.Caption,
            audience = SplitAudience(card.Card.Audience),
            audienceLabel = PublicSurfaceStatus.AudienceLabel(card.Card.Audience),
            locale,
            retentionSummary,
            previewState = PublicSurfaceStatus.IsAvailableToday(card.Card.Badge) ? "available_today" : "preview_in_progress",
            publicationState = BuildArtifactCardPublicationState(card.Card),
            proof = string.IsNullOrWhiteSpace(card.Card.ProofNote) ? card.Card.Payoff : card.Card.ProofNote,
            detailHref = card.Action.Href,
            detailLabel = card.Action.Label,
            siblingPackets = Array.Empty<object>()
        };

    private static object BuildArtifactShelfRecapPayload(
        RecapShelfEntry item,
        IReadOnlyList<CreatorPublicationProjection> creatorPublications,
        string locale,
        string retentionSummary)
    {
        CreatorPublicationProjection? linkedPublication = string.IsNullOrWhiteSpace(item.CreatorPublicationId)
            ? null
            : creatorPublications.FirstOrDefault(publication =>
                string.Equals(publication.PublicationId, item.CreatorPublicationId, StringComparison.OrdinalIgnoreCase));
        return new
        {
            id = item.EntryId,
            kind = item.Kind,
            title = item.Label,
            item.Summary,
            caption = BuildArtifactRecapCaption(item),
            artifactId = item.ArtifactId,
            audience = SplitAudience(item.Audience),
            audienceLabel = PublicSurfaceStatus.AudienceLabel(item.Audience),
            locale,
            retentionSummary,
            previewState = BuildArtifactPreviewState(item.PublicationState, item.Discoverable),
            proof = BuildArtifactProofSummary(item.ProvenanceSummary, item.AuditSummary, item.PublicationSummary),
            publicationState = item.PublicationState,
            trustBand = item.TrustBand,
            discoverable = item.Discoverable,
            creatorPublicationId = item.CreatorPublicationId,
            publicationHref = string.IsNullOrWhiteSpace(item.CreatorPublicationId)
                ? null
                : CreatorPublicationHrefForApi(linkedPublication, item.CreatorPublicationId!),
            siblingPackets = BuildCreatorSiblingPackets(linkedPublication, creatorPublications),
            ownershipSummary = item.OwnershipSummary,
            provenanceSummary = item.ProvenanceSummary,
            auditSummary = item.AuditSummary,
            publicationSummary = item.PublicationSummary,
            lineageSummary = item.LineageSummary,
            nextSafeAction = item.NextSafeAction,
            updatedAtUtc = item.UpdatedAtUtc
        };
    }

    private static object BuildArtifactShelfCreatorPublicationPayload(
        CreatorPublicationProjection publication,
        IReadOnlyList<CreatorPublicationProjection> publications,
        string locale,
        string retentionSummary,
        bool publicOnly)
    {
        string[] audience = publicOnly
            ? ["public"]
            : ["creator", publication.Discoverable ? "public" : "signed_in"];
        return new
        {
            id = publication.PublicationId,
            kind = publication.Kind,
            title = publication.Title,
            publication.Summary,
            caption = BuildCreatorPublicationCaption(publication, publicOnly),
            audience,
            audienceLabel = PublicSurfaceStatus.AudienceLabel(string.Join(",", audience)),
            locale,
            retentionSummary,
            previewState = BuildArtifactPreviewState(publication.PublicationStatus, publication.Discoverable),
            proof = BuildArtifactProofSummary(publication.ProvenanceSummary, publication.TrustSummary, publication.ModerationSummary),
            publicationState = publication.PublicationStatus,
            visibility = publication.Visibility,
            trustBand = publication.TrustBand,
            discoverable = publication.Discoverable,
            detailHref = $"/artifacts/publications/{Uri.EscapeDataString(publication.PublicationId)}",
            siblingPackets = BuildCreatorSiblingPackets(publication, publications),
            provenanceSummary = publication.ProvenanceSummary,
            discoverySummary = publication.DiscoverySummary,
            comparisonSummary = publication.ComparisonSummary,
            lineageSummary = publication.LineageSummary,
            moderationSummary = publication.ModerationSummary,
            campaignReturnSummary = publication.CampaignReturnSummary,
            supportClosureSummary = publication.SupportClosureSummary,
            nextSafeAction = publication.NextSafeAction,
            updatedAtUtc = publication.UpdatedAtUtc
        };
    }

    private static string BuildArtifactRecapCaption(RecapShelfEntry item)
        => item.Kind.Trim().ToLowerInvariant() switch
        {
            "dossier_projection" => "Signed-in personal dossier packet",
            var kind when kind.Contains("replay", StringComparison.Ordinal) => "Signed-in replay packet",
            var kind when kind.Contains("downtime", StringComparison.Ordinal) => "Signed-in downtime packet",
            var kind when kind.Contains("aftermath", StringComparison.Ordinal) => "Signed-in aftermath packet",
            _ => "Signed-in return shelf packet"
        };

    private static string BuildCreatorPublicationCaption(CreatorPublicationProjection publication, bool publicOnly)
        => publicOnly
            ? "Published shared-publication packet"
            : string.Equals(publication.PublicationStatus, HubPublicationStates.Published, StringComparison.OrdinalIgnoreCase)
                ? "Creator packet already widened onto the public rail"
                : "Creator packet still moving through governed publication"
        ;

    private static string BuildArtifactCardPublicationState(PublicFeatureCardDto card)
        => PublicSurfaceStatus.IsAvailableToday(card.Badge) ? "published" : "preview";

    private static string BuildArtifactPreviewState(string? publicationState, bool discoverable)
    {
        string normalized = publicationState?.Trim().ToLowerInvariant() ?? string.Empty;
        if (normalized is "published" or "ready" or "personal_ready")
        {
            return discoverable || normalized == "published" ? "live" : "signed_in_ready";
        }

        return normalized switch
        {
            "approved" => "approved_preview",
            "review" or "pending_review" => "under_review",
            "draft" => "draft_preview",
            _ => discoverable ? "live" : "preview_in_progress"
        };
    }

    private static string[] BuildArtifactProofSummary(params string?[] segments)
        => segments
            .Where(static item => !string.IsNullOrWhiteSpace(item))
            .Select(static item => item!.Trim())
            .Distinct(StringComparer.Ordinal)
            .ToArray();

    private static string[] SplitAudience(string? audience)
        => string.IsNullOrWhiteSpace(audience)
            ? Array.Empty<string>()
            : audience
                .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();

    private static string CreatorPublicationHrefForApi(CreatorPublicationProjection? publication, string publicationId)
        => publication is { Discoverable: true }
            && string.Equals(publication.PublicationStatus, HubPublicationStates.Published, StringComparison.OrdinalIgnoreCase)
                ? $"/artifacts/publications/{Uri.EscapeDataString(publicationId)}"
                : $"/account/work/publications/{Uri.EscapeDataString(publicationId)}";

    private static object[] BuildCreatorSiblingPackets(
        CreatorPublicationProjection? publication,
        IReadOnlyList<CreatorPublicationProjection> publications)
    {
        if (publication is null)
        {
            return Array.Empty<object>();
        }

        return publications
            .Where(item =>
                !string.Equals(item.PublicationId, publication.PublicationId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.CampaignId, publication.CampaignId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(item => RankPublicationSibling(item, publication))
            .ThenBy(static item => item.Title, StringComparer.OrdinalIgnoreCase)
            .Take(3)
            .Select(item => (object)new
            {
                id = item.PublicationId,
                kind = item.Kind,
                title = item.Title,
                discoverable = item.Discoverable,
                publicationState = item.PublicationStatus,
                detailHref = CreatorPublicationHrefForApi(item, item.PublicationId),
                detailLabel = string.Equals(
                    CreatorPublicationHrefForApi(item, item.PublicationId),
                    $"/artifacts/publications/{Uri.EscapeDataString(item.PublicationId)}",
                    StringComparison.Ordinal)
                    ? "Open public publication"
                    : "Open publication status"
            })
            .ToArray();
    }

    private static int RankPublicationSibling(CreatorPublicationProjection candidate, CreatorPublicationProjection reference)
    {
        int sameKindBonus = string.Equals(candidate.Kind, reference.Kind, StringComparison.OrdinalIgnoreCase) ? 2 : 0;
        int discoverableBonus = candidate.Discoverable ? 1 : 0;
        return sameKindBonus + discoverableBonus;
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
            SignedInStatus = await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken),
            SupportIntake = BuildSupportIntakeModel(
                authenticated: chrome.Authenticated,
                submissionNotice: null,
                manifest,
                installDefaults,
                overrides)
        };
    }

    private PublicTrustPulsePanelViewModel? BuildPublicTrustPulsePanel(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience,
        PublicTrustPulseSnapshot? pulse = null)
    {
        pulse ??= _trustPulse.LoadSnapshot();
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

        if (pulse.MissingDesktopClientCoverage)
        {
            microProof.Add("Desktop proof gap: desktop_client");
        }

        if (pulse.ClosureHealthWaitingCount is int closureWaitingCount
            && pulse.ClosureHealthPendingHumanResponseCount is int pendingHumanResponseCount)
        {
            microProof.Add($"{closureWaitingCount} waiting closure / {pendingHumanResponseCount} pending human response");
        }

        var rows = new List<PublicTrustPulseRowViewModel>
        {
            new("Recommended now", BuildTrustPulseRecommendedSummary(manifest, releaseExperience, pulse)),
            new("Who can get it now", BuildTrustPulseAccessSummary(manifest, releaseExperience, pulse)),
            new("Release proof", BuildReleaseProofSummary(manifest)),
            new("Launch readiness", BuildTrustPulseLaunchReadinessSummary(pulse)),
            new("Provider-route stewardship", BuildProviderRouteStewardshipSummary(pulse)),
            new("Closure health", BuildTrustPulseClosureHealthSummary(pulse)),
            new("Adoption health", BuildTrustPulseAdoptionSummary(pulse)),
            new("Progress trend", BuildTrustPulseProgressTrendSummary(pulse)),
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
        var trendSamples = BuildTrustPulseTrendSamples(pulse);

        return new PublicTrustPulsePanelViewModel(
            Eyebrow: "Weekly trust pulse",
            Heading: heading,
            Summary: summary,
            MicroProof: microProof,
            TrendSamples: trendSamples,
            Rows: rows,
            PrimaryAction: new TrustPageActionViewModel("Open progress", "/progress", "secondary"),
            SecondaryAction: new TrustPageActionViewModel(
                "Open downloads",
                string.IsNullOrWhiteSpace(releaseExperience.GuestGatePrimaryHref)
                    ? "/downloads"
                    : releaseExperience.GuestGatePrimaryHref,
                "ghost"),
            MissingDesktopClientCoverage: pulse.MissingDesktopClientCoverage,
            ParityClaimsReviewRequired: pulse.ParityClaimsReviewRequired,
            RouteGuardSummary: BuildTrustPulseLaunchReadinessSummary(pulse));
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
        return _signedInTrustStatus.Build(user, manifest, releaseExperience);
    }

    private async Task<AccountCampaignSummary?> BuildLandingCampaignSpineAsync(CancellationToken cancellationToken)
    {
        var subject = await TryGetOptionalPublicSurfaceSubjectAsync("/", cancellationToken);
        if (subject is null)
        {
            return null;
        }

        var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
        return _campaignSpine.GetAccountSummary(user, installLinking);
    }

    private async Task<ParticipatePageViewModel> BuildParticipatePageModel(
        string title,
        string description,
        string currentPath,
        CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var cards = _landing.CardsForBucket(surface, "participate");
        var assets = new AssetCatalogViewModel(surface.Assets);
        var chrome = await BuildPublicOrAuthenticatedChromeAsync(title, description, currentPath, cancellationToken);
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), chrome.Authenticated);
        var signalLoop = BuildPublicSignalLoopSnapshot(surface, assets, chrome.Authenticated, currentPath);
        var signalProjection = BuildOptionalSignalProjectionPacket(currentPath);
        var signalOperations = string.Equals(currentPath, "/feedback", StringComparison.OrdinalIgnoreCase)
            ? BuildOptionalSignalOperationsPacket()
            : null;

        return new ParticipatePageViewModel(
            Chrome: chrome,
            Surface: surface,
            Assets: assets,
            PublicLane: ResolveCards(
                cards.Where(card =>
                        !string.Equals(card.Id, "participate_booster", StringComparison.Ordinal)
                        && !string.Equals(card.Id, "participate_beta", StringComparison.Ordinal))
                    .ToArray(),
                assets,
                authenticated: false,
                currentPath),
            SignedInLane: ResolveCards(
                cards.Where(card =>
                        string.Equals(card.Id, "participate_booster", StringComparison.Ordinal)
                        || string.Equals(card.Id, "participate_beta", StringComparison.Ordinal))
                    .ToArray(),
                assets,
                authenticated: chrome.Authenticated,
                currentPath),
            SignalLoop: signalLoop,
            SignalProjection: signalProjection,
            SignalOperations: signalOperations,
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
    }

    private async Task<TrustPageViewModel> BuildHorizonPreviewPageModel(
        string pageId,
        string title,
        string description,
        string currentPath,
        string eyebrow,
        string heading,
        string intro,
        IReadOnlyList<TrustPageSectionViewModel> sections,
        IReadOnlyList<TrustPageActionViewModel> actions,
        CancellationToken cancellationToken,
        IReadOnlyList<string>? summaryPoints = null)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var chrome = await BuildPublicOrAuthenticatedChromeAsync(title, description, currentPath, cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), chrome.Authenticated);

        return new TrustPageViewModel(
            PageId: pageId,
            Chrome: chrome,
            Eyebrow: eyebrow,
            Heading: heading,
            Intro: intro,
            Sections: sections,
            Actions: actions,
            SummaryPoints: summaryPoints,
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
    }

    private async Task<KarmaForgeIntakePageViewModel> BuildKarmaForgePageModel(
        KarmaForgeSubmissionRequest request,
        string? submissionNotice,
        IReadOnlyList<string> validationErrors,
        CancellationToken cancellationToken,
        AuthenticatedHubSubject? subject = null)
    {
        request ??= new KarmaForgeSubmissionRequest();
        subject ??= await TryGetOptionalPublicSurfaceSubjectAsync("/participate/karma-forge", cancellationToken);

        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var chrome = await BuildPublicOrAuthenticatedChromeAsync(
            "KARMA FORGE",
            "Chummer-owned intake for house-rule, campaign, and trust-friction discovery packets.",
            "/participate/karma-forge",
            cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), chrome.Authenticated);
        KarmaForgeTrackDefinition selectedTrack = _karmaForge.ResolveTrack(request.TrackKey);

        return new KarmaForgeIntakePageViewModel(
            Chrome: chrome,
            Eyebrow: "Governed discovery intake",
            Heading: "KARMA FORGE",
            Intro: "Turn one table pain into named Chummer-owned packets before it drifts into generic feedback, unsupported roadmap claims, or implementation guesswork.",
            CanonicalLane: _karmaForge.CanonicalLane,
            EntryLane: _karmaForge.EntryLane,
            Dashboard: _karmaForge.GetDashboardSummary(),
            DiscoverySteps: _karmaForge.GetDiscoverySteps(),
            ExternalStages: _karmaForge.GetExternalStageProjections(),
            JourneyProofEventRefs: _karmaForge.GetJourneyProofEventRefs(),
            Form: new KarmaForgeIntakeFormViewModel(
                ActionHref: "/participate/karma-forge",
                Authenticated: chrome.Authenticated,
                SubmissionNotice: submissionNotice,
                ValidationErrors: validationErrors,
                TrackOptions: _karmaForge.ListTracks().Select(static track => new KarmaForgeOptionDefinition(track.Key, track.Title, track.Family)).ToArray(),
                RoleOptions: _karmaForge.ListRoleOptions(),
                EditionOptions: _karmaForge.ListEditionOptions(),
                TableTypeOptions: _karmaForge.ListTableTypeOptions(),
                RuleCategoryOptions: _karmaForge.ListRuleCategoryOptions(),
                SeverityOptions: _karmaForge.ListSeverityOptions(),
                DefaultTrackKey: request.TrackKey,
                DefaultRespondentRole: request.RespondentRole,
                DefaultEdition: request.Edition,
                DefaultTableType: request.TableType,
                DefaultRuleCategory: request.RuleCategory,
                DefaultSeverity: request.Severity,
                DefaultFeedbackPrompt: request.FeedbackPrompt,
                DefaultUserWordsSummary: request.UserWordsSummary,
                DefaultCurrentWorkaround: request.CurrentWorkaround,
                DefaultInterpretedNeedSummary: request.InterpretedNeedSummary,
                DefaultImpactNotes: request.ImpactNotes,
                DefaultShareabilityNotes: request.ShareabilityNotes,
                DefaultReplyEmail: string.IsNullOrWhiteSpace(request.ReplyEmail) ? subject?.Email ?? string.Empty : request.ReplyEmail,
                DefaultFollowUpAllowed: request.FollowUpAllowed,
                DefaultQuoteAllowed: request.QuoteAllowed,
                DefaultConsentAccepted: request.ConsentAccepted),
            SelectedTrack: selectedTrack,
            CandidateDecisions: _karmaForge.GetCandidateDecisionMeanings()
                .Select(static item => new KarmaForgeCandidateDecisionViewModel(item.Key, item.Value))
                .ToArray(),
            CanonicalOutputs: _karmaForge.GetCanonicalOutputs(),
            RecentSubmissions: _karmaForge.ListRecentForSubject(subject?.SubjectId)
                .Select(static item => new KarmaForgeRecentSubmissionViewModel(
                    item.SubmissionId,
                    item.Packet.Title,
                    item.SubmittedAtUtc.ToUniversalTime().ToString("yyyy-MM-dd HH:mm 'UTC'"),
                    HumanizeToken(item.Candidate.CandidateDecision, "Decision pending"),
                    HumanizeToken(item.QueueStatus, "Queued")))
                .ToArray(),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
    }

    private async Task<NowPageViewModel> BuildNowPageModel(
        string title,
        string description,
        string currentPath,
        CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var assetCatalog = new AssetCatalogViewModel(surface.Assets);
        var nowCards = _landing.CardsForBucket(surface, "whats_real_now");
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var authenticated = await TryIsAuthenticatedAsync(cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        var signalLoop = BuildPublicSignalLoopSnapshot(surface, assetCatalog, authenticated, currentPath);
        var signalProjection = BuildOptionalSignalProjectionPacket(currentPath);

        return new NowPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync(title, description, currentPath, cancellationToken),
            Surface: surface,
            Assets: assetCatalog,
            ReleaseExperience: releaseExperience,
            ProofModules: ResolveCards(_landing.CardsForBucket(surface, "start_here").Take(3).ToArray(), assetCatalog, authenticated: false, currentPath),
            AvailableToday: ResolveCards(nowCards.Where(static card => PublicSurfaceStatus.IsAvailableToday(card.Badge)).ToArray(), assetCatalog, authenticated: false, currentPath),
            Inspectable: ResolveCards(nowCards.Where(static card => !PublicSurfaceStatus.IsAvailableToday(card.Badge)).ToArray(), assetCatalog, authenticated: false, currentPath),
            SignedInPreview: surface.RegisteredOverlays,
            Manifest: manifest,
            SignalLoop: signalLoop,
            SignalProjection: signalProjection,
            CampaignOsProof: _campaignOsProof.LoadProof(),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
    }

    private async Task<KarmaForgeSubmittedPageViewModel> BuildKarmaForgeSubmittedPageModel(
        KarmaForgeSubmissionProjection submission,
        CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var chrome = await BuildPublicOrAuthenticatedChromeAsync(
            "KARMA FORGE packet receipt",
            "The normalized packet, decision path, and follow-through questions for one KARMA FORGE submission.",
            $"/participate/karma-forge/submitted/{submission.SubmissionId}",
            cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), chrome.Authenticated);
        JsonSerializerOptions jsonOptions = new() { WriteIndented = true };

        List<TrustPageActionViewModel> actions =
        [
            new("Open KARMA FORGE", "/participate/karma-forge", "primary"),
            new("Read the horizon brief", "/roadmap/karma-forge", "secondary"),
            new("Open support intake", "/contact#support-intake", "ghost")
        ];

        string affectedDomains = submission.Packet.AffectedDomains.Count == 0
            ? "No domain tags were inferred yet."
            : $"Affected domains: {string.Join(", ", submission.Packet.AffectedDomains.Select(domain => HumanizeToken(domain, domain)))}.";
        string rolloutScope = submission.ImpactHypothesis.RolloutScope.Count == 0
            ? "Scope still needs an explicit portability call."
            : $"Rollout scope: {string.Join(", ", submission.ImpactHypothesis.RolloutScope.Select(scope => HumanizeToken(scope, scope)))}.";

        return new KarmaForgeSubmittedPageViewModel(
            Chrome: chrome,
            Eyebrow: "Normalized packet receipt",
            Heading: "KARMA FORGE submission captured",
            Intro: "The intake is now visible as Chummer-owned packet truth, with the next questions and the likely governor route still explicit.",
            SubmissionId: submission.SubmissionId,
            TrackTitle: submission.Candidate.TrackTitle,
            QueueStatus: HumanizeToken(submission.QueueStatus, "Queued"),
            Actions: actions,
            PacketTitle: submission.Packet.Title,
            QueueSummary: submission.QueueSummary,
            CandidateDecision: HumanizeToken(submission.Candidate.CandidateDecision, "Decision pending"),
            CandidateDecisionMeaning: submission.Candidate.CandidateDecisionMeaning,
            ReporterNextAction: submission.ReporterNextAction,
            ConsentSummary: submission.ConsentSummary,
            ExternalStages: submission.Packet.Source.ExternalStages,
            JourneyProofEventRefs: submission.Packet.Source.JourneyProofEventRefs,
            Highlights:
            [
                $"{HumanizeToken(submission.Packet.Source.RuleCategory, "Rule category")} · {HumanizeToken(submission.Packet.Source.Severity, "Severity")}",
                $"Blocker score {submission.Packet.PrioritySignals.BlockerScore}/5 · shareability {submission.Packet.PrioritySignals.ShareabilityScore}/5 · {HumanizeToken(submission.Packet.PrioritySignals.FrequencySignal, "Frequency signal")}",
                $"{affectedDomains} {rolloutScope}"
            ],
            FollowUpAllowed: submission.FollowUpAllowed,
            NextQuestions: submission.NextQuestions,
            NextSteps: submission.Packet.NextSteps,
            QuoteAllowed: submission.QuoteAllowed,
            PacketJson: JsonSerializer.Serialize(submission.Packet, jsonOptions),
            CandidateJson: JsonSerializer.Serialize(submission.Candidate, jsonOptions),
            ImpactHypothesisJson: JsonSerializer.Serialize(submission.ImpactHypothesis, jsonOptions),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
    }

    private PublicSignalLoopSnapshotViewModel BuildPublicSignalLoopSnapshot(
        PublicLandingSurfaceDto surface,
        AssetCatalogViewModel assets,
        bool authenticated,
        string currentPath)
    {
        var milestones = BuildRoadmapMilestones();
        var milestoneFollowUp = milestones.Take(3).ToArray();
        var roadmapCards = _landing.CardsForBucket(surface, "coming_next");
        var roadmapFollowUp = ResolveCards(
            roadmapCards.Take(3).ToArray(),
            assets,
            authenticated: false,
            currentPath);
        var shippedCards = _landing.CardsForBucket(surface, "whats_real_now")
            .Where(static card => PublicSurfaceStatus.IsAvailableToday(card.Badge))
            .ToArray();
        var shippedFollowUp = ResolveCards(
            shippedCards.Take(3).ToArray(),
            assets,
            authenticated: false,
            currentPath);

        return new PublicSignalLoopSnapshotViewModel(
            OpenMilestoneCount: milestones.Count,
            ClaimedMilestoneCount: milestones.Count(static milestone => milestone.Claimed),
            HighDifficultyMilestoneCount: milestones.Count(static milestone => string.Equals(milestone.DifficultyLabel, "High", StringComparison.OrdinalIgnoreCase)),
            RoadmapFollowUpCount: roadmapCards.Count,
            ShippedFollowUpCount: shippedCards.Length,
            MilestoneFollowUp: milestoneFollowUp,
            RoadmapFollowUp: roadmapFollowUp,
            ShippedFollowUp: shippedFollowUp,
            FollowSettingsHref: authenticated ? "/account/participation" : "/signup?next=%2Faccount%2Fparticipation",
            FollowSettingsLabel: authenticated ? "Open participation dashboard" : "Create account for follow-up");
    }

    private PublicSignalProjectionPacketViewModel? BuildOptionalSignalProjectionPacket(string currentPath)
    {
        try
        {
            return _signalProjection.BuildPacket(currentPath);
        }
        catch (Exception ex) when (ex is DirectoryNotFoundException or FileNotFoundException or InvalidOperationException)
        {
            _logger.LogWarning(ex, "Public signal projection packet could not load for {Path}.", currentPath);
            return null;
        }
    }

    private PublicSignalOperationsPacketViewModel? BuildOptionalSignalOperationsPacket()
    {
        try
        {
            return _signalOperations.BuildPacket();
        }
        catch (Exception ex) when (ex is DirectoryNotFoundException or FileNotFoundException or InvalidOperationException)
        {
            _logger.LogWarning(ex, "Public signal operations packet could not load.");
            return null;
        }
    }

    private IReadOnlyList<ProgramMilestoneSummaryViewModel> BuildRoadmapMilestones()
    {
        try
        {
            return new ProgramMilestoneDigestService(new PublicCanonFileLoader(_configuration)).BuildOpenMilestones();
        }
        catch (Exception ex) when (ex is DirectoryNotFoundException or FileNotFoundException or InvalidOperationException)
        {
            _logger.LogWarning(ex, "Roadmap page could not load milestone digest.");
            return Array.Empty<ProgramMilestoneSummaryViewModel>();
        }
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
            ContextHint: ResolveSupportContextHintFromRequestQuery(),
            ArtifactId: NormalizeSupportPrefill(Request.Query.TryGetValue("artifactId", out var artifactValues) ? artifactValues.ToString() : null),
            RecoveryMode: Request.Query.TryGetValue("recoveryMode", out var recoveryValues)
                && bool.TryParse(recoveryValues.ToString(), out bool recoveryMode)
                && recoveryMode);
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

    private static IReadOnlyList<string> ValidateKarmaForgeSubmission(KarmaForgeSubmissionRequest request, bool authenticated)
    {
        List<string> errors = [];
        if (string.IsNullOrWhiteSpace(request.UserWordsSummary))
        {
            errors.Add("User words are required before Chummer can normalize the packet.");
        }

        if (string.IsNullOrWhiteSpace(request.CurrentWorkaround))
        {
            errors.Add("Current workaround is required so the packet records how the table is coping today.");
        }

        if (!request.ConsentAccepted)
        {
            errors.Add("Consent must be accepted before the intake can become Chummer-owned packet truth.");
        }

        if (!authenticated && request.FollowUpAllowed && string.IsNullOrWhiteSpace(request.ReplyEmail))
        {
            errors.Add("Guest submissions that allow follow-up need a reply email.");
        }

        if (!string.IsNullOrWhiteSpace(request.ReplyEmail)
            && !new EmailAddressAttribute().IsValid(request.ReplyEmail))
        {
            errors.Add("Reply email must be a valid email address when it is provided.");
        }

        return errors;
    }

    private DesktopInstallRailContext ResolveSupportIntakeRailFromQuery()
    {
        string? artifactId = NormalizeSupportPrefill(Request.Query.TryGetValue("artifactId", out var artifactValues) ? artifactValues.ToString() : null);
        bool recoveryMode = Request.Query.TryGetValue("recoveryMode", out var recoveryValues)
            && bool.TryParse(recoveryValues.ToString(), out bool parsedRecoveryMode)
            && parsedRecoveryMode;
        return DesktopInstallRail.ResolveSupportIntakeRail(artifactId, recoveryMode);
    }

    private static Dictionary<string, string?> BuildSupportRailQuery(DesktopInstallRailContext installRail)
    {
        if (string.IsNullOrWhiteSpace(installRail.ReturnHref))
        {
            return new Dictionary<string, string?>();
        }

        const string dispatchPrefix = "/downloads/install/";
        if (!installRail.ReturnHref.StartsWith(dispatchPrefix, StringComparison.OrdinalIgnoreCase))
        {
            return new Dictionary<string, string?>();
        }

        string artifactId = installRail.ReturnHref[dispatchPrefix.Length..];
        return new Dictionary<string, string?>
        {
            ["artifactId"] = artifactId,
            ["recoveryMode"] = installRail.RecoveryModeOnly ? "true" : "false"
        };
    }

    private static SupportIntakeViewModel BuildSupportIntakeModel(
        bool authenticated,
        string? submissionNotice,
        PublicReleaseManifestDto manifest,
        SupportIntakeDefaults installDefaults,
        SupportIntakeOverrides overrides)
    {
        DesktopInstallRailContext installRail = DesktopInstallRail.ResolveSupportIntakeRail(
            overrides.ArtifactId,
            overrides.RecoveryMode);

        return new(
            ActionHref: QueryHelpers.AddQueryString("/contact", BuildSupportRailQuery(installRail)),
            Heading: "Open a first-party support case",
            Intro: authenticated
                ? "Use the form for a quick report here, or open Account > Support when you want the full tracked case view."
                : "Use the first-party intake here when you want help without a GitHub account. Create an account later if you want tracked follow-up inside Chummer.",
            Authenticated: authenticated,
            AccountSupportHref: authenticated ? "/account/support" : "/signup?next=%2Faccount%2Fsupport",
            AccountSupportLabel: authenticated ? "Open tracked support" : "Create account for tracked support",
            InstallAccessHref: installRail.ReturnHref ?? "/account/access",
            InstallAccessLabel: installRail.ReturnLabel ?? "Open Devices and access",
            ResponseExpectation: BuildSupportResponseExpectation(authenticated, manifest.SupportabilityState, manifest.SupportabilitySummary),
            SubmissionNotice: submissionNotice,
            AttachmentHelp: "Add screenshots, logs, or a small diagnostic bundle when they make the bug or install problem easier to route.",
            Options:
            [
                new SupportIntakeOptionViewModel(SupportCaseKinds.InstallHelp, "Install or update", "Choose this when the installer, updater, or download handoff is the problem."),
                new SupportIntakeOptionViewModel(SupportCaseKinds.BugReport, "Product bug", "Use this for broken behavior, bad routing, regressions, or cases that need private logs and tracked follow-up."),
                new SupportIntakeOptionViewModel(SupportCaseKinds.Feedback, "Feature request or UX feedback", "Safe public feedback should start on Fixer Board. Choose this form only when the issue needs private or account-linked follow-up.")
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
            InstallRailHref: installRail.ReturnHref,
            InstallRailLabel: installRail.ReturnLabel,
            InstallRailSummary: installRail.Summary,
            RecoveryModeOnly: installRail.RecoveryModeOnly,
            ContextHint: string.Join(" ",
                new[]
                {
                    installDefaults.ContextHint,
                    overrides.ContextHint
                }.Where(static item => !string.IsNullOrWhiteSpace(item))));
    }

    private static string BuildSupportResponseExpectation(
        bool authenticated,
        PublicTrustPulsePanelViewModel? pulse)
        => BuildSupportResponseExpectation(
            authenticated,
            pulse?.ParityClaimsReviewRequired == true ? "review_required" : null,
            pulse?.RouteGuardSummary);

    private static string BuildSupportResponseExpectation(
        bool authenticated,
        string? supportabilityState,
        string? routeGuardSummary)
    {
        string baseline = authenticated
            ? "Tracked cases stay visible in Account. When the report is actionable, the next routed update should show up there without sending you into side channels."
            : "Guest cases should include a reply email. We usually answer preview support within two working days when the report includes a clear reproduction path.";

        if (!string.Equals(supportabilityState, "review_required", StringComparison.OrdinalIgnoreCase))
        {
            return baseline;
        }

        if (string.IsNullOrWhiteSpace(routeGuardSummary))
        {
            return $"{baseline} Public parity claims stay review-required until the current desktop proof receipts are green again.";
        }

        return $"{baseline} {routeGuardSummary}";
    }

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

    private static IReadOnlyList<PublicTrustPulseRowViewModel> BuildPublicLaunchHealthRows(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience,
        PublicTrustPulseSnapshot? pulse)
    {
        return
        [
            new("Live", BuildLiveLaunchSummary(manifest)),
            new("Preview", BuildPreviewLaunchSummary(manifest, releaseExperience)),
            new("Fallback", BuildFallbackLaunchSummary(manifest)),
            new("Revoked", BuildRevokedLaunchSummary(manifest)),
            new("Fixed", BuildFixedLaunchSummary(manifest)),
            new("Blocked", BuildBlockedLaunchSummary(manifest, pulse)),
            new("Proof freshness", BuildProofFreshnessSummary(manifest, pulse)),
            new("Support pulse", BuildSupportPulseSummary(manifest, pulse)),
            new("Adoption health", pulse is null
                ? BuildReleaseProofSummary(manifest)
                : BuildTrustPulseAdoptionSummary(pulse))
        ];
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

    private static string BuildLiveLaunchSummary(PublicReleaseManifestDto manifest)
    {
        int openPublicCount = manifest.Downloads.Count(static artifact =>
            !string.Equals(artifact.InstallAccessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase));
        string shelfSummary = openPublicCount switch
        {
            <= 0 => "No open-public artifacts are live on the shelf right now.",
            1 => "1 open-public artifact is live on the shelf right now.",
            _ => $"{openPublicCount} open-public artifacts are live on the shelf right now."
        };

        JsonElement primaryRoute = EnumerateDesktopRouteTruth(manifest)
            .FirstOrDefault(static route => string.Equals(TryGetJsonString(route, "routeRole"), "primary", StringComparison.OrdinalIgnoreCase));

        string? primaryReason = primaryRoute.ValueKind == JsonValueKind.Object
            ? FirstNonEmpty(
                TryGetJsonString(primaryRoute, "installPostureReason"),
                TryGetJsonString(primaryRoute, "promotionReason"),
                TryGetJsonString(primaryRoute, "updateEligibilityReason"))
            : null;

        return string.IsNullOrWhiteSpace(primaryReason)
            ? shelfSummary
            : $"{shelfSummary} {primaryReason}";
    }

    private static string BuildPreviewLaunchSummary(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience)
        => $"{HumanizeToken(manifest.RolloutState, "Current preview")} on {releaseExperience.Display.ChannelLabel} {manifest.Version}, published {manifest.PublishedAt.ToUniversalTime():yyyy-MM-dd HH:mm} UTC.";

    private static string BuildFallbackLaunchSummary(PublicReleaseManifestDto manifest)
    {
        var fallbackRoutes = EnumerateDesktopRouteTruth(manifest)
            .Where(static route => string.Equals(TryGetJsonString(route, "routeRole"), "fallback", StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (fallbackRoutes.Length == 0)
        {
            return "No explicit fallback route is mirrored for the current shelf.";
        }

        string? reason = FirstNonEmpty(
            TryGetJsonString(fallbackRoutes[0], "rollbackReason"),
            TryGetJsonString(fallbackRoutes[0], "promotionReason"),
            TryGetJsonString(fallbackRoutes[0], "updateEligibilityReason"));
        return string.IsNullOrWhiteSpace(reason)
            ? $"{fallbackRoutes.Length} explicit fallback route(s) are mirrored for the current shelf."
            : $"{fallbackRoutes.Length} explicit fallback route(s) are mirrored for the current shelf. {reason}";
    }

    private static string BuildRevokedLaunchSummary(PublicReleaseManifestDto manifest)
    {
        var routeRows = EnumerateDesktopRouteTruth(manifest);
        var revokedRoutes = routeRows
            .Where(static route => string.Equals(TryGetJsonString(route, "revokeState"), "revoked", StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (revokedRoutes.Length == 0)
        {
            return routeRows.Count == 0
                ? "No desktop route revoke truth is mirrored for the current shelf."
                : $"No registry revoke markers are active across {routeRows.Count} tracked desktop route(s).";
        }

        string? reason = FirstNonEmpty(
            TryGetJsonString(revokedRoutes[0], "revokeReason"),
            TryGetJsonString(revokedRoutes[0], "installPostureReason"));
        return string.IsNullOrWhiteSpace(reason)
            ? $"{revokedRoutes.Length} desktop route(s) are currently revoked."
            : $"{revokedRoutes.Length} desktop route(s) are currently revoked. {reason}";
    }

    private static string BuildFixedLaunchSummary(PublicReleaseManifestDto manifest)
        => !string.IsNullOrWhiteSpace(manifest.FixAvailabilitySummary)
            ? manifest.FixAvailabilitySummary!
            : !string.IsNullOrWhiteSpace(manifest.SupportabilitySummary)
                ? manifest.SupportabilitySummary!
                : "No fixed-release follow-through note is published for the current shelf.";

    private static string BuildBlockedLaunchSummary(
        PublicReleaseManifestDto manifest,
        PublicTrustPulseSnapshot? pulse)
    {
        int blockedRouteCount = EnumerateDesktopRouteTruth(manifest).Count(static route =>
        {
            string routeRole = TryGetJsonString(route, "routeRole") ?? string.Empty;
            string promotionState = TryGetJsonString(route, "promotionState") ?? string.Empty;
            string revokeState = TryGetJsonString(route, "revokeState") ?? string.Empty;
            if (string.Equals(routeRole, "fallback", StringComparison.OrdinalIgnoreCase)
                && string.Equals(promotionState, "proof_required", StringComparison.OrdinalIgnoreCase)
                && !string.Equals(revokeState, "revoked", StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }

            return IsBlockedStatus(TryGetJsonString(route, "updateEligibility"))
                   || IsBlockedStatus(TryGetJsonString(route, "promotionState"))
                   || IsBlockedStatus(TryGetJsonString(route, "installPosture"));
        });
        int blockedJourneyCount = pulse?.BlockedJourneyCount ?? 0;
        if (blockedRouteCount == 0 && blockedJourneyCount == 0)
        {
            return "No blocked public route or journey is mirrored right now.";
        }

        var segments = new List<string>(2);
        if (blockedRouteCount > 0)
        {
            segments.Add($"{blockedRouteCount} desktop route(s) are blocked or still proof-gated");
        }

        if (blockedJourneyCount > 0)
        {
            segments.Add($"{blockedJourneyCount} golden journey(s) remain blocked");
        }

        return string.Join("; ", segments) + ".";
    }

    private static string BuildProofFreshnessSummary(
        PublicReleaseManifestDto manifest,
        PublicTrustPulseSnapshot? pulse)
    {
        string manifestStamp = manifest.GeneratedAt is DateTimeOffset generatedAt
            ? $"Manifest {generatedAt.ToUniversalTime():yyyy-MM-dd HH:mm} UTC"
            : $"Manifest published {manifest.PublishedAt.ToUniversalTime():yyyy-MM-dd HH:mm} UTC";
        string proofStamp = manifest.ProofGeneratedAt is DateTimeOffset proofGeneratedAt
            ? $"release proof {proofGeneratedAt.ToUniversalTime():yyyy-MM-dd HH:mm} UTC ({HumanizeToken(manifest.ProofStatus, "unknown")})"
            : $"release proof {HumanizeToken(manifest.ProofStatus, "not mirrored").ToLowerInvariant()}";
        string pulseStamp = string.IsNullOrWhiteSpace(pulse?.AsOf)
            ? "weekly pulse not mirrored"
            : $"weekly pulse as of {pulse.AsOf}";
        return $"{manifestStamp}; {proofStamp}; {pulseStamp}.";
    }

    private static string BuildSupportPulseSummary(
        PublicReleaseManifestDto manifest,
        PublicTrustPulseSnapshot? pulse)
        => pulse is not null
            ? BuildTrustPulseClosureHealthSummary(pulse)
            : !string.IsNullOrWhiteSpace(manifest.SupportabilitySummary)
                ? manifest.SupportabilitySummary!
                : "Support closure posture is not mirrored yet.";

    private static bool IsBlockedStatus(string? value)
    {
        string normalized = value?.Trim() ?? string.Empty;
        return normalized.StartsWith("blocked", StringComparison.OrdinalIgnoreCase)
               || normalized.EndsWith("_required", StringComparison.OrdinalIgnoreCase)
               || string.Equals(normalized, "proof_required", StringComparison.OrdinalIgnoreCase)
               || string.Equals(normalized, "fallback_not_promoted", StringComparison.OrdinalIgnoreCase);
    }

    private static List<JsonElement> EnumerateDesktopRouteTruth(PublicReleaseManifestDto manifest)
    {
        var rows = new List<JsonElement>();
        if (manifest.DesktopTupleCoverage is not JsonElement coverage
            || coverage.ValueKind != JsonValueKind.Object
            || !coverage.TryGetProperty("desktopRouteTruth", out JsonElement routeTruth)
            || routeTruth.ValueKind != JsonValueKind.Array)
        {
            return rows;
        }

        foreach (JsonElement route in routeTruth.EnumerateArray())
        {
            rows.Add(route.Clone());
        }

        return rows;
    }

    private static string? TryGetJsonString(JsonElement element, string propertyName)
        => element.ValueKind == JsonValueKind.Object
            && element.TryGetProperty(propertyName, out JsonElement value)
            && value.ValueKind == JsonValueKind.String
            ? value.GetString()
            : null;

    private static string? FirstNonEmpty(params string?[] values)
        => values.FirstOrDefault(static value => !string.IsNullOrWhiteSpace(value));

    private static string BuildSignedInInstallRecommendationSummary(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience,
        ClaimedInstallationDto? installation,
        SupportCasePresentationViewModel? followThrough)
    {
        if (installation is null)
        {
            return manifest.Downloads.Count == 0 || releaseExperience.Recommended is null
                ? "Link the current preview first so Chummer can compare this account against the published shelf."
                : $"Link the current preview first so Chummer can compare this account against {BuildPublishedArtifactSummary(manifest, releaseExperience, releaseExperience.Recommended.Artifact)}.";
        }

        string installationLabel = ResolveInstallationDisplayLabel(installation);
        if (!string.IsNullOrWhiteSpace(followThrough?.FixedReleaseLabel))
        {
            if (followThrough.NeedsInstallUpdate)
            {
                PublicReleaseArtifactDto? publishedArtifact = FindPublishedArtifactForInstallation(manifest, installation);
                return publishedArtifact is null
                    ? $"Support is tracking {followThrough.FixedReleaseLabel} for {installationLabel}. Keep this linked copy on the support-directed lane until the promoted shelf catches up."
                    : $"Support is tracking {followThrough.FixedReleaseLabel} for {installationLabel}. The current public shelf still shows {BuildPublishedArtifactSummary(manifest, releaseExperience, publishedArtifact)}.";
            }

            if (followThrough.CanVerifyFix)
            {
                return $"{installationLabel} is already on {followThrough.FixedReleaseLabel}, so this linked copy is the right one to verify now.";
            }
        }

        PublicReleaseArtifactDto? artifact = FindPublishedArtifactForInstallation(manifest, installation);
        if (artifact is null)
        {
            return $"No promoted public-shelf match is published right now for {installationLabel}. Keep this copy linked and use a support-directed lane before moving it.";
        }

        string publishedSummary = BuildPublishedArtifactSummary(manifest, releaseExperience, artifact);
        if (InstallationMatchesPublishedShelf(manifest, installation, artifact))
        {
            return $"{installationLabel} already matches the promoted {publishedSummary}.";
        }

        return $"{installationLabel} reports {installation.Version} on {ResolveChannelLabel(installation.Channel, manifest, releaseExperience)}. The promoted shelf for this install is {publishedSummary}.";
    }

    private static string BuildSignedInInstallPostureSummary(
        PublicReleaseManifestDto manifest,
        ClaimedInstallationDto? installation,
        SupportCasePresentationViewModel? followThrough)
    {
        if (followThrough?.NeedsLinkedInstall == true || followThrough?.NeedsInstallUpdate == true)
        {
            return followThrough.InstallReadinessSummary;
        }

        if (followThrough?.CanVerifyFix == true)
        {
            return followThrough.VerificationSummary;
        }

        if (installation is not null && FindPublishedArtifactForInstallation(manifest, installation) is null)
        {
            return $"{ResolveInstallationDisplayLabel(installation)} is linked on {BuildInstallationFootprintSummary(installation)}, and that lane is not on the promoted public shelf right now.";
        }

        if (!string.IsNullOrWhiteSpace(manifest.KnownIssueSummary))
        {
            return manifest.KnownIssueSummary!;
        }

        if (!string.IsNullOrWhiteSpace(manifest.FixAvailabilitySummary))
        {
            return manifest.FixAvailabilitySummary!;
        }

        if (!string.IsNullOrWhiteSpace(manifest.RolloutReason))
        {
            return manifest.RolloutReason!;
        }

        if (!string.IsNullOrWhiteSpace(manifest.SupportabilitySummary))
        {
            return manifest.SupportabilitySummary!;
        }

        return installation is null
            ? "No linked install is attached yet, so Chummer cannot compare this account against the current shelf or fix lane."
            : "No extra install-specific posture warning is published right now.";
    }

    private static string BuildSignedInFixAvailabilitySummary(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience,
        ClaimedInstallationDto? installation,
        SupportCasePresentationViewModel? followThrough)
    {
        if (followThrough is not null && !string.IsNullOrWhiteSpace(followThrough.FixedReleaseLabel))
        {
            string fixedReleaseLabel = followThrough.FixedReleaseLabel!;
            if (followThrough.CanVerifyFix && installation is not null)
            {
                return $"{ResolveInstallationDisplayLabel(installation)} can verify {fixedReleaseLabel} on this linked install now.";
            }

            if (followThrough.NeedsInstallUpdate && installation is not null)
            {
                PublicReleaseArtifactDto? artifact = FindPublishedArtifactForInstallation(manifest, installation);
                return artifact is null
                    ? $"{fixedReleaseLabel} is the tracked fix target, but this linked install still needs a support-directed update before it can verify."
                    : $"{fixedReleaseLabel} is the tracked fix target. The promoted shelf for this install is {BuildPublishedArtifactSummary(manifest, releaseExperience, artifact)}.";
            }

            return $"{fixedReleaseLabel} is the tracked fix target for this account right now.";
        }

        if (!string.IsNullOrWhiteSpace(manifest.FixAvailabilitySummary))
        {
            return manifest.FixAvailabilitySummary!;
        }

        if (!string.IsNullOrWhiteSpace(manifest.SupportabilitySummary))
        {
            return manifest.SupportabilitySummary!;
        }

        return installation is null
            ? "No linked install is attached yet, so Chummer cannot tie this account to a fix-ready shelf."
            : "No fix-specific availability note is published for this linked install right now.";
    }

    private static string BuildSignedInInstallCautionSummary(
        PublicReleaseManifestDto manifest,
        ClaimedInstallationDto? installation,
        SupportCasePresentationViewModel? followThrough)
    {
        if (followThrough?.NeedsLinkedInstall == true)
        {
            return followThrough.InstallReadinessSummary;
        }

        if (followThrough?.NeedsInstallUpdate == true)
        {
            return followThrough.InstallReadinessSummary;
        }

        if (followThrough?.ReporterActionNeeded == true)
        {
            return followThrough.NextSafeAction;
        }

        if (followThrough?.CanVerifyFix == true)
        {
            return "No extra caution is published for this linked install right now; use the verification lane to confirm the fix on this device.";
        }

        if (installation is not null && FindPublishedArtifactForInstallation(manifest, installation) is null)
        {
            return $"{ResolveInstallationDisplayLabel(installation)} is outside the promoted public shelf right now, so keep it on the support-directed lane until a matching build lands.";
        }

        if (!string.IsNullOrWhiteSpace(manifest.KnownIssueSummary))
        {
            return manifest.KnownIssueSummary!;
        }

        if (!string.IsNullOrWhiteSpace(manifest.RolloutReason))
        {
            return manifest.RolloutReason!;
        }

        return installation is null
            ? "No linked install is attached yet, so Chummer cannot publish install-specific caution for this account."
            : "No extra caution is published for this linked install right now.";
    }

    private static PublicReleaseArtifactDto? FindPublishedArtifactForInstallation(
        PublicReleaseManifestDto manifest,
        ClaimedInstallationDto installation)
    {
        string? installationPlatform = NormalizePlatformFamily(installation.Platform);
        string? installationHead = NormalizeHeadId(installation.HeadId);

        if (!string.IsNullOrWhiteSpace(installationPlatform) && !string.IsNullOrWhiteSpace(installationHead))
        {
            var exactMatch = manifest.Downloads.FirstOrDefault(item =>
                string.Equals(NormalizeArtifactPlatformFamily(item), installationPlatform, StringComparison.OrdinalIgnoreCase)
                && string.Equals(NormalizeHeadId(item.Head), installationHead, StringComparison.OrdinalIgnoreCase));
            if (exactMatch is not null)
            {
                return exactMatch;
            }
        }

        if (!string.IsNullOrWhiteSpace(installationPlatform))
        {
            var platformMatch = manifest.Downloads.FirstOrDefault(item =>
                string.Equals(NormalizeArtifactPlatformFamily(item), installationPlatform, StringComparison.OrdinalIgnoreCase));
            if (platformMatch is not null)
            {
                return platformMatch;
            }
        }

        if (!string.IsNullOrWhiteSpace(installationHead))
        {
            return manifest.Downloads.FirstOrDefault(item =>
                string.Equals(NormalizeHeadId(item.Head), installationHead, StringComparison.OrdinalIgnoreCase));
        }

        return null;
    }

    private static bool InstallationMatchesPublishedShelf(
        PublicReleaseManifestDto manifest,
        ClaimedInstallationDto installation,
        PublicReleaseArtifactDto artifact)
    {
        if (!string.Equals(installation.Channel, manifest.Channel, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(installation.Version, manifest.Version, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        string? installationPlatform = NormalizePlatformFamily(installation.Platform);
        string? artifactPlatform = NormalizeArtifactPlatformFamily(artifact);
        if (!string.IsNullOrWhiteSpace(installationPlatform)
            && !string.IsNullOrWhiteSpace(artifactPlatform)
            && !string.Equals(installationPlatform, artifactPlatform, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        string? installationHead = NormalizeHeadId(installation.HeadId);
        string? artifactHead = NormalizeHeadId(artifact.Head);
        return string.IsNullOrWhiteSpace(installationHead)
            || string.IsNullOrWhiteSpace(artifactHead)
            || string.Equals(installationHead, artifactHead, StringComparison.OrdinalIgnoreCase);
    }

    private static string BuildPublishedArtifactSummary(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience,
        PublicReleaseArtifactDto artifact)
        => $"{BuildPublishedArtifactLabel(artifact)} on {ResolveChannelLabel(manifest.Channel, manifest, releaseExperience)} {manifest.Version}";

    private static string BuildPublishedArtifactLabel(PublicReleaseArtifactDto artifact)
    {
        string platform = BuildPlatformDisplayLabel(artifact.Platform, artifact.Arch);
        return NormalizeHeadId(artifact.Head) switch
        {
            "avalonia" => $"the recommended desktop build for {platform}",
            "blazor-desktop" => $"the alternative desktop build for {platform}",
            _ => $"the published build for {platform}"
        };
    }

    private static string BuildInstallationFootprintSummary(ClaimedInstallationDto installation)
    {
        string platform = BuildPlatformDisplayLabel(installation.Platform, installation.Arch);
        return NormalizeHeadId(installation.HeadId) switch
        {
            "avalonia" => $"the recommended desktop lane on {platform}",
            "blazor-desktop" => $"the alternative desktop lane on {platform}",
            _ => platform
        };
    }

    private static string BuildPlatformDisplayLabel(string? platform, string? arch)
    {
        string platformLabel = NormalizePlatformFamily(platform) switch
        {
            "windows" => "Windows",
            "linux" => "Linux",
            "macos" => "macOS",
            _ when !string.IsNullOrWhiteSpace(platform) => HumanizeToken(platform, "current platform"),
            _ => "the current platform"
        };

        return string.IsNullOrWhiteSpace(arch)
            ? platformLabel
            : $"{platformLabel} {arch}";
    }

    private static string? NormalizeArtifactPlatformFamily(PublicReleaseArtifactDto artifact)
        => NormalizePlatformFamily(!string.IsNullOrWhiteSpace(artifact.PlatformId) ? artifact.PlatformId : artifact.Platform);

    private static string? NormalizePlatformFamily(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string normalized = value.Trim().ToLowerInvariant();
        if (normalized.Contains("win", StringComparison.OrdinalIgnoreCase))
        {
            return "windows";
        }

        if (normalized.Contains("linux", StringComparison.OrdinalIgnoreCase))
        {
            return "linux";
        }

        if (normalized.Contains("osx", StringComparison.OrdinalIgnoreCase) || normalized.Contains("mac", StringComparison.OrdinalIgnoreCase))
        {
            return "macos";
        }

        return normalized;
    }

    private static string? NormalizeHeadId(string? value)
        => string.IsNullOrWhiteSpace(value)
            ? null
            : value.Trim().ToLowerInvariant();

    private static string BuildTrustPulseRecommendedSummary(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience,
        PublicTrustPulseSnapshot pulse)
    {
        if (manifest.Downloads.Count == 0 || releaseExperience.Recommended is null)
        {
            return string.IsNullOrWhiteSpace(manifest.Message)
                ? "No published build is on the shelf yet."
                : manifest.Message;
        }

        if (pulse.MissingDesktopClientCoverage || string.Equals(manifest.SupportabilityState, "review_required", StringComparison.OrdinalIgnoreCase))
        {
            return releaseExperience.Recommended.RequiresAccount && !releaseExperience.GuestDownloadAvailable
                ? "Signed-in handoff remains the safest route while desktop proof receipts stay review-required."
                : "The current shelf is still installable, but keep parity-sensitive installs on the review-required lane until current desktop proof receipts are green.";
        }

        string accessSummary = releaseExperience.Recommended.RequiresAccount && !releaseExperience.GuestDownloadAvailable
            ? "Signed-in handoff is the recommended path so the install can stay linked."
            : "Guest-readable handoff is live on the current shelf, and Signed-in handoff keeps the install linked once you want account-aware follow-through.";
        return $"{releaseExperience.Recommended.Title} on {releaseExperience.Display.ChannelLabel}. {accessSummary}";
    }

    private static string BuildTrustPulseAccessSummary(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience,
        PublicTrustPulseSnapshot pulse)
    {
        if (releaseExperience.Recommended is null)
        {
            return "No release handoff is published yet.";
        }

        if (pulse.MissingDesktopClientCoverage || string.Equals(manifest.SupportabilityState, "review_required", StringComparison.OrdinalIgnoreCase))
        {
            return releaseExperience.Recommended.RequiresAccount && !releaseExperience.GuestDownloadAvailable
                ? "Signed-in handoff stays preferred while desktop proof receipts are still review-required."
                : "Guest and signed-in handoffs are both visible, but parity-sensitive follow-through stays on the review-required support lane until current desktop proof receipts are green.";
        }

        if (releaseExperience.Recommended.RequiresAccount && !releaseExperience.GuestDownloadAvailable)
        {
            return "Signed-in handoff is the live path now, so the install stays linked and support can follow the exact device.";
        }

        if (releaseExperience.GuestDownloadAvailable)
        {
            return "Guest-readable handoff is visible now, and Signed-in handoff adds linked-install follow-through once you want the install attached to your account.";
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

        if (pulse.MissingDesktopClientCoverage && !string.IsNullOrWhiteSpace(pulse.FlagshipReadinessReason))
        {
            segments.Add($"Desktop flagship proof still needs closure: {pulse.FlagshipReadinessReason!.Trim().TrimEnd('.')}.");
        }

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
        if (pulse.MissingDesktopClientCoverage && !string.IsNullOrWhiteSpace(pulse.FlagshipReadinessReason))
        {
            return $"Hold parity claims on public routes and support surfaces because {pulse.FlagshipReadinessReason!.Trim().TrimEnd('.')}.";
        }

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

        if (pulse.MissingDesktopClientCoverage && !string.IsNullOrWhiteSpace(pulse.FlagshipReadinessReason))
        {
            segments.Add($"Flagship desktop proof still needs closure: {pulse.FlagshipReadinessReason!.Trim().TrimEnd('.')}.");
        }

        return segments.Count == 0
            ? "Measured adoption evidence is still accumulating."
            : string.Join(" ", segments);
    }

    private static string BuildTrustPulseClosureHealthSummary(PublicTrustPulseSnapshot pulse)
    {
        if (!string.IsNullOrWhiteSpace(pulse.ClosureHealthSummary))
        {
            return pulse.ClosureHealthSummary!;
        }

        if (pulse.ClosureHealthWaitingCount is int waitingCount
            && pulse.ClosureHealthPendingHumanResponseCount is int pendingCount)
        {
            string openCaseSegment = pulse.ClosureHealthOpenCaseCount is int openCaseCount
                ? $" {openCaseCount} open support packet(s) remain."
                : string.Empty;
            return $"{waitingCount} waiting closure / {pendingCount} pending human response.{openCaseSegment}".Trim();
        }

        return "Closure health is waiting on current support-packet evidence.";
    }

    private static string BuildTrustPulseProgressTrendSummary(PublicTrustPulseSnapshot pulse)
    {
        if (pulse.ProgressTrendSamples is not { Count: > 1 } samples)
        {
            return pulse.ProgressHistorySnapshotCount is not null && pulse.ProgressHistorySnapshotCount > 1
                ? $"Trend needs two distinct snapshots to calculate movement. {pulse.ProgressHistorySnapshotCount} snapshot(s) are available."
                : "Progress trend is awaiting measured history; two weekly points are required.";
        }

        string trendWindow = string.Join(
            " → ",
            samples.Select(static sample =>
                $"{sample.AsOf} {sample.OverallProgressPercent}%"));

        string sparkline = BuildProgressTrendSparkline(samples);
        if (pulse.ProgressTrendDirection is null
            || pulse.ProgressTrendFromAsOf is null
            || pulse.ProgressTrendToAsOf is null
            || pulse.ProgressTrendDeltaPercent is null)
        {
            return $"Weekly trend window: {trendWindow}. {sparkline}";
        }

        string direction = pulse.ProgressTrendDirection switch
        {
            "up" => $"Upward momentum",
            "down" => "Regression",
            _ => "Flat trend"
        };

        string deltaSign = pulse.ProgressTrendDirection switch
        {
            "up" => $"+{pulse.ProgressTrendDeltaPercent.Value}%",
            "down" => $"-{pulse.ProgressTrendDeltaPercent.Value}%",
            _ => $"{pulse.ProgressTrendDeltaPercent.Value}%"
        };

        return
            $"{direction} {deltaSign} from {pulse.ProgressTrendFromAsOf} to {pulse.ProgressTrendToAsOf}. Trend window: {trendWindow}. {sparkline}";

    }

    private static IReadOnlyList<PublicTrustPulseTrendPointViewModel> BuildTrustPulseTrendSamples(PublicTrustPulseSnapshot pulse)
    {
        if (pulse.ProgressTrendSamples is not { Count: > 1 } samples)
        {
            return Array.Empty<PublicTrustPulseTrendPointViewModel>();
        }

        return samples
            .Select((sample, index) => new PublicTrustPulseTrendPointViewModel(
                AsOf: sample.AsOf,
                OverallProgressPercent: sample.OverallProgressPercent,
                Current: index == samples.Count - 1))
            .ToArray();
    }

    private static string BuildProgressTrendSparkline(IReadOnlyList<ProgressHistoryTrendPoint> points)
    {
        if (points.Count < 2)
        {
            return string.Empty;
        }

        const string bars = "▁▂▃▄▅▆▇█";
        int min = points.Min(static point => point.OverallProgressPercent);
        int max = points.Max(static point => point.OverallProgressPercent);
        if (min == max)
        {
            return $"Trend sparkline: {string.Concat(Enumerable.Repeat('▁', points.Count))}";
        }

        string barsString = string.Concat(points.Select(point =>
        {
            double scaled = (point.OverallProgressPercent - min) / (double)(max - min);
            int index = (int)Math.Clamp(Math.Round(scaled * (bars.Length - 1)), 0, bars.Length - 1);
            return bars[index];
        }));

        return $"Trend sparkline: {barsString}";
    }

    private static string HumanizeToken(string? value, string fallback)
        => string.IsNullOrWhiteSpace(value)
            ? fallback
            : System.Globalization.CultureInfo.InvariantCulture.TextInfo.ToTitleCase(value.Replace('_', ' '));

    private static PublicRouteReceiptViewModel? BuildRouteReceiptPayload(LocalProofReceiptMatch? routeReceipt)
        => routeReceipt is null
            ? null
            : new PublicRouteReceiptViewModel(
                routeReceipt.ReceiptId,
                routeReceipt.PackageId,
                routeReceipt.MatchedRoute,
                routeReceipt.MatchMode,
                routeReceipt.Summary);

    private RouteClaimStatus ResolvePublicRouteClaimStatus(
        LocalReleaseProofLookupResult routeLookup,
        string passingState,
        string missingReceiptReason)
    {
        if (!string.IsNullOrWhiteSpace(routeLookup.CurrentnessFailureReason))
        {
            return new RouteClaimStatus(
                "bounded_failure",
                $"Parity claims stay review-required because {routeLookup.CurrentnessFailureReason!.Trim().TrimEnd('.')}.");
        }

        LocalProofReceiptMatch? routeReceipt = routeLookup.ReceiptMatch;
        if (routeReceipt is null)
        {
            return new RouteClaimStatus("bounded_failure", missingReceiptReason);
        }

        FlagshipReadinessSnapshot? readiness = _flagshipReadiness.LoadSnapshot();
        if (readiness?.MissingDesktopClientCoverage == true)
        {
            string reviewRequiredReason = readiness.DesktopClientGapSummary.Trim().TrimEnd('.');
            return new RouteClaimStatus(
                "bounded_failure",
                $"Current direct route receipt is attached, but parity claims stay review-required because {reviewRequiredReason}.");
        }

        ImportRouteParityProofGuardSnapshot importRouteGuard = _importRouteParityProofGuard.Evaluate();
        if (!importRouteGuard.IsCurrent && !string.IsNullOrWhiteSpace(importRouteGuard.ReviewRequiredReason))
        {
            return new RouteClaimStatus(
                "bounded_failure",
                $"Current direct route receipt is attached, but parity claims stay review-required because {importRouteGuard.ReviewRequiredReason!.Trim().TrimEnd('.')}.");
        }

        return new RouteClaimStatus(passingState, null);
    }

    private LocalReleaseProofLookupResult FindLocalReleaseProofReceipt(params string?[] routeCandidates)
        => _localReleaseProof.FindReceipt(routeCandidates);

    private sealed record RouteClaimStatus(
        string State,
        string? BoundedFailureReason)
    {
        public bool Blocked => string.Equals(State, "bounded_failure", StringComparison.OrdinalIgnoreCase);
    }

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
        string? ContextHint = null,
        string? ArtifactId = null,
        bool RecoveryMode = false);

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
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
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
            MicroProof: BuildFeatureDetailMicroProof(card),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
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
            return _chrome.BuildAuthenticatedChrome(title, description, currentPath, user.DisplayName, user.Email);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return BuildContextualPublicChrome(title, description, currentPath);
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Preserving signed-in chrome after identity failure for {Path}.", currentPath);
            if (Request.Cookies.ContainsKey(HubBrowserAuthConstants.AccessTokenCookieName))
            {
                return _chrome.BuildAuthenticatedChrome(title, description, currentPath, "Signed in");
            }

            return BuildContextualPublicChrome(title, description, currentPath);
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

            return BuildContextualPublicChrome(title, description, currentPath);
        }
    }

    private SiteChromeViewModel BuildContextualPublicChrome(string title, string description, string currentPath)
    {
        var chrome = _chrome.BuildPublicChrome(title, description, currentPath);
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(
            manifest,
            Request.Headers.UserAgent.ToString(),
            authenticated: false);
        return RebindGuestGateChromeActions(chrome, releaseExperience, rebindSignIn: false);
    }

    private static FaqPageViewModel RebindFaqAccessPosture(FaqPageViewModel model, PublicAccessPostureViewModel accessPosture)
        => model with
        {
            Sections = model.Sections
                .Select(section => section with
                {
                    Entries = section.Entries
                        .Select(entry => string.Equals(entry.Question, "Do I need an account to download the current preview?", StringComparison.Ordinal)
                            ? entry with { Answer = accessPosture.DownloadFaqAnswer }
                            : string.Equals(entry.Question, "What does account creation give me right away?", StringComparison.Ordinal)
                                ? entry with { Answer = accessPosture.AccountFaqAnswer }
                                : entry)
                        .ToArray()
                })
                .ToArray(),
            AccessPosture = accessPosture
        };

    private static SiteChromeViewModel RebindDownloadsHeaderActions(SiteChromeViewModel chrome, ReleaseExperienceViewModel releaseExperience)
        => RebindGuestGateChromeActions(chrome, releaseExperience, rebindSignIn: true);

    private static SiteChromeViewModel RebindGuestGateChromeActions(
        SiteChromeViewModel chrome,
        ReleaseExperienceViewModel releaseExperience,
        bool rebindSignIn)
    {
        if (chrome.Authenticated || releaseExperience.Recommended is null)
        {
            return chrome;
        }

        var requiresAccount = releaseExperience.Recommended.RequiresAccount;
        var primaryHref = requiresAccount
            ? releaseExperience.GuestGatePrimaryHref
            : releaseExperience.Recommended.DispatchHref;
        var primaryLabel = requiresAccount
            ? releaseExperience.GuestGatePrimaryLabel
            : releaseExperience.Recommended.ActionLabel;

        var reboundActions = chrome.HeaderActions
            .Select(action =>
            {
                if (rebindSignIn
                    && requiresAccount
                    && string.Equals(action.Label, "Sign in", StringComparison.OrdinalIgnoreCase))
                {
                    return action with
                    {
                        Href = releaseExperience.GuestGateSecondaryHref,
                        Current = false
                    };
                }

                // Downloads chrome always exposes a single primary CTA, but the copy
                // now varies between public-preview and guest-gated account flows.
                if (string.Equals(action.Tone, "primary", StringComparison.OrdinalIgnoreCase))
                {
                    return action with
                    {
                        Label = primaryLabel,
                        Href = primaryHref,
                        Current = false
                    };
                }

                return action;
            })
            .ToArray();

        var reboundPublicPrimaryCta = chrome.PublicPrimaryCta is not null
            ? chrome.PublicPrimaryCta with
            {
                Label = primaryLabel,
                Href = primaryHref,
                Current = false
            }
            : null;

        return chrome with
        {
            HeaderActions = reboundActions,
            PublicPrimaryCta = reboundPublicPrimaryCta
        };
    }

    private string BuildAbsoluteUrl(string path, QueryString query = default)
        => UriHelper.BuildAbsolute(
            Request.Scheme,
            Request.Host,
            Request.PathBase,
            path,
            query);

    private static string? ResolveGuidedBootstrapPlatform(PublicReleaseArtifactDto artifact)
    {
        if (IsMacBootstrapArtifact(artifact))
        {
            return "macos";
        }

        if (IsLinuxBootstrapArtifact(artifact))
        {
            return "linux";
        }

        return null;
    }

    private static string BuildBootstrapScriptPath(string artifactId, string platform)
        => platform switch
        {
            "macos" => $"/downloads/install/{Uri.EscapeDataString(artifactId)}/bootstrap.command",
            "linux" => $"/downloads/install/{Uri.EscapeDataString(artifactId)}/bootstrap.sh",
            _ => throw new InvalidOperationException($"unsupported bootstrap platform '{platform}'.")
        };

    internal static string BuildPersonalizedMacBootstrapScriptPath(string scriptId, string? renderedScriptSha256 = null)
        => string.IsNullOrWhiteSpace(renderedScriptSha256)
            ? $"/install-{Uri.EscapeDataString(scriptId)}.sh"
            : $"/install-{Uri.EscapeDataString(scriptId)}-{Uri.EscapeDataString(renderedScriptSha256.Trim().ToLowerInvariant())}.sh";

    private static string? BuildBootstrapCommandLabel(string? platform)
        => platform switch
        {
            "macos" => "Install command",
            "linux" => "Linux install command",
            _ => null
        };

    private static string? BuildBootstrapCommandIntro(string? platform)
        => platform switch
        {
            "macos" => "Copy this into Terminal.",
            "linux" => "Paste this into your shell.",
            _ => null
        };

    private static string BuildDispatchHeading(string defaultHeading, string? platform)
        => platform switch
        {
            "macos" => "Install your personalized Chummer6 app",
            _ => defaultHeading
        };

    private static string BuildCopyCommandLabel(string? platform)
        => platform switch
        {
            "macos" => "Copy the install command",
            _ => "Copy install command"
        };

    private static string? BuildBootstrapCommandNote(string? platform)
        => platform switch
        {
            "macos" => "It streams a short-lived setup assistant directly into bash. The assistant asks which Chummer apps to install, where to put them, whether quick access should stay in the Applications folder or add Desktop links, whether to open them when it finishes, and then shows live progress while it downloads, verifies, installs, and links the selected apps.",
            "linux" => "It streams a short-lived shell setup assistant. The assistant asks which Chummer apps to install, where to put them, whether quick access should stay in the applications menu or add Desktop links, whether to open them when it finishes, and then shows live progress while it downloads, verifies, installs, and links the selected apps.",
            _ => null
        };

    private static IReadOnlyList<DownloadDispatchFeatureCardViewModel> BuildBootstrapFeatureCards(string? platform)
        => platform switch
        {
            "macos" =>
            [
                new("Choose your setup", "Pick Avalonia, Blazor Desktop, or both from a native macOS dialog before any files are copied."),
                new("Choose where it lands", "Install into /Applications or ~/Applications without changing the published DMGs."),
                new("Choose your quick access", "Keep Chummer in the Applications folder only or let setup drop Desktop links for the apps you picked."),
                new("Finish verified and linked", "The selected apps are launched once through a short-lived environment handoff, and setup checks the install-link receipt before it tells you the apps are attached to this account.")
            ],
            "linux" =>
            [
                new("Choose your setup", "Pick Avalonia, Blazor Desktop, or both before any packages are unpacked."),
                new("Choose where it lands", "Install into a user-local applications root or a system root without changing the published Debian packages."),
                new("Choose your quick access", "Keep Chummer in the applications menu only or let setup add Desktop launchers for the apps you picked."),
                new("Finish verified and linked", "The selected apps are launched once through a short-lived environment handoff, and setup checks the install-link receipt before it tells you the apps are attached to this account.")
            ],
            _ => Array.Empty<DownloadDispatchFeatureCardViewModel>()
        };

    private static string BuildBootstrapFallbackDownloadLabel(string? platform)
        => platform switch
        {
            "macos" => "Download setup script",
            "linux" => "Download setup script fallback",
            _ => "Download setup script fallback"
        };

    private static string? BuildBootstrapSecondaryDownloadLabel(string? platform)
        => platform switch
        {
            "macos" => "Download raw DMG instead",
            "linux" => "Download raw package instead",
            _ => null
        };

    private static string BuildBootstrapDispatchSummary(string? platform)
        => platform switch
        {
            "linux" => "Paste the shell install command below. It streams a short-lived Linux setup assistant, asks which Chummer apps to install and where to put them, then downloads, verifies, installs, and links the selected apps to this account.",
            _ => "Copy the install command and run it in Terminal."
        };

    private static string BuildBootstrapDispatchNote(string? platform)
        => platform switch
        {
            "linux" => "The shell command keeps the published Debian packages unchanged while streaming a short-lived guided setup assistant that can attach the install relationship to this account from the first launch.",
            _ => "macOS can quarantine a downloaded unsigned .command and label it as damaged. The signed Terminal command avoids that by streaming the same short-lived setup assistant directly into bash while keeping the published DMGs unchanged."
        };

    private static IReadOnlyList<string> BuildBootstrapSteps(string? platform)
        => platform switch
        {
            "linux" =>
            [
                "Copy the shell install command below and paste it into your shell.",
                "The Linux setup assistant offers Auto select for the matching desktop builds on this machine, lets you switch to manual selection when you want different heads, asks whether to use a user-local root or a system root, whether quick access should stay in the applications menu or add Desktop links, whether to open Chummer when it finishes, and then verifies that linking actually completed.",
                "The shell then shows staged progress while it downloads the selected packages, verifies their published SHA-256 digests, unpacks them into the selected root, and writes the launchers and desktop entries without mutating the published .deb files.",
                "Each selected app is started once through a short-lived environment handoff so it is already linked to this account the next time you open it."
            ],
            _ =>
            [
                "Copy the signed Terminal install command below and paste it into Terminal.",
                "The Mac setup assistant offers Auto select for the matching Apple Silicon or Intel builds on this Mac, lets you switch to manual selection when you want different heads, asks whether to use /Applications or ~/Applications, whether to leave quick access in Applications only or add Desktop links, whether to open Chummer when it finishes, and then verifies that linking actually completed.",
                "Terminal then shows staged progress while it downloads the selected DMGs, verifies their published SHA-256 digests, mounts them, and installs the app bundles with a staged swap instead of a delete-first replace.",
                "Each selected app is started once through a short-lived environment handoff so it is already linked to this account the next time you open it."
            ]
        };

    private static string BuildMacBootstrapFileName(PublicReleaseArtifactDto artifact)
    {
        return "Chummer Setup.command";
    }

    private static string BuildLinuxBootstrapFileName(PublicReleaseArtifactDto artifact)
    {
        return "chummer-setup.sh";
    }

    internal static string BuildBootstrapInstallCommand(string? platform, string bootstrapUrl)
        => platform switch
        {
            "linux" => BuildMacBootstrapTerminalCommand(bootstrapUrl),
            _ => BuildMacBootstrapTerminalCommand(bootstrapUrl)
        };

    internal static string BuildBootstrapInstallCommand(string? platform, string bootstrapUrl, string? bootstrapSha256)
        => platform switch
        {
            "linux" => BuildMacBootstrapTerminalCommand(bootstrapUrl, bootstrapSha256),
            _ => BuildMacBootstrapTerminalCommand(bootstrapUrl, bootstrapSha256)
        };

    internal static string BuildMacBootstrapTerminalCommand(string bootstrapUrl, string? bootstrapSha256 = null)
    {
        var builder = new StringBuilder();
        builder.Append("set -euo pipefail; ");
        builder.Append("TMP_BOOTSTRAP_SCRIPT=\"$(mktemp \\\"${TMPDIR:-/tmp}/chummer-install.XXXXXX\\\")\"; ");
        builder.Append("trap 'rm -f \"$TMP_BOOTSTRAP_SCRIPT\"' EXIT; ");
        builder.Append("curl -fsSL ").Append(SingleQuoteShellValue(bootstrapUrl)).Append(" -o \"$TMP_BOOTSTRAP_SCRIPT\"; ");
        if (!string.IsNullOrWhiteSpace(bootstrapSha256))
        {
            builder.Append("ACTUAL_BOOTSTRAP_SHA256=\"$(shasum -a 256 \"$TMP_BOOTSTRAP_SCRIPT\" | awk '{print $1}')\"; ");
            builder.Append("[[ \"$ACTUAL_BOOTSTRAP_SHA256\" == ")
                .Append(SingleQuoteShellValue(bootstrapSha256))
                .Append(" ]] || { echo 'Bootstrap digest mismatch; re-open the signed-in downloads handoff and copy a fresh install command.' >&2; exit 1; }; ");
        }

        builder.Append("/bin/bash \"$TMP_BOOTSTRAP_SCRIPT\"");
        return builder.ToString();
    }

    private PersonalizedInstallScriptIssueResult IssuePersonalizedMacInstallScript(
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto primaryArtifact,
        IReadOnlyList<PublicReleaseArtifactDto> guidedArtifacts,
        string? userId,
        string? subjectId)
    {
        GuidedBootstrapArtifact[] scriptArtifacts = guidedArtifacts
            .Select(candidate => new GuidedBootstrapArtifact(
                ArtifactId: candidate.Id,
                HeadId: candidate.Head ?? string.Empty,
                Title: BuildGuidedBootstrapArtifactTitle(candidate),
                ShortLabel: BuildGuidedBootstrapShortLabel(candidate),
                DownloadUrl: string.Empty,
                ClaimUrl: string.Empty,
                Sha256: candidate.Sha256,
                PackageName: candidate.FileName ?? Path.GetFileName(candidate.Url),
                Architecture: candidate.Arch,
                LaunchAfterInstall: string.Equals(candidate.Id, primaryArtifact.Id, StringComparison.OrdinalIgnoreCase),
                InstallFolderName: ResolveGuidedBootstrapInstallFolderName(candidate),
                ExecutableName: ResolveGuidedBootstrapExecutableName(candidate),
                LauncherName: ResolveGuidedBootstrapLauncherName(candidate),
                DesktopEntryName: ResolveGuidedBootstrapDesktopEntryName(candidate)))
            .ToArray();
        string renderedScript = RenderMacInstallBootstrapScript(
            BuildMacInstallBootstrapArtifacts(manifest, scriptArtifacts, userId, subjectId),
            BuildAbsoluteUrl("/"),
            BuildAbsoluteUrl("/account/access"),
            BuildAbsoluteUrl("/downloads"),
            BuildAbsoluteUrl("/help"));
        return _personalizedInstallScripts.IssueMacScript(
            primaryArtifact.Id,
            guidedArtifacts.Select(candidate => candidate.Id),
            userId,
            subjectId,
            renderedScript,
            ComputeSha256Hex(renderedScript));
    }

    private MacInstallBootstrapArtifact[] BuildMacInstallBootstrapArtifacts(
        PublicReleaseManifestDto manifest,
        IReadOnlyList<GuidedBootstrapArtifact> guidedArtifacts,
        string? userId,
        string? subjectId)
        => guidedArtifacts
            .Select(candidate =>
            {
                PublicReleaseArtifactDto sourceArtifact = manifest.Downloads
                    .First(item => string.Equals(item.Id, candidate.ArtifactId, StringComparison.OrdinalIgnoreCase));
                DownloadDispatchResult dispatch = _installLinking.IssueDownload(manifest, sourceArtifact, userId, subjectId);
                string claimCode = dispatch.ClaimTicket?.ClaimCode
                    ?? throw new InvalidOperationException($"install claim code is unavailable for {candidate.ArtifactId}.");
                return new MacInstallBootstrapArtifact(
                    ArtifactId: candidate.ArtifactId,
                    HeadId: candidate.HeadId,
                    Title: candidate.Title,
                    ShortLabel: candidate.ShortLabel,
                    DownloadUrl: BuildAbsoluteUrl($"/downloads/file/{Uri.EscapeDataString(candidate.ArtifactId)}"),
                    ClaimCode: claimCode,
                    Sha256: candidate.Sha256,
                    DmgName: candidate.PackageName,
                    Architecture: candidate.Architecture,
                    LaunchAfterInstall: candidate.LaunchAfterInstall);
            })
            .ToArray();

    internal static IReadOnlyList<PublicReleaseArtifactDto> ResolveGuidedBootstrapArtifacts(
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto primaryArtifact)
    {
        string? platform = ResolveGuidedBootstrapPlatform(primaryArtifact);
        if (platform is null)
        {
            return Array.Empty<PublicReleaseArtifactDto>();
        }

        string? expectedArch = NormalizeBootstrapToken(primaryArtifact.Arch);
        string primaryId = primaryArtifact.Id.Trim();

        return manifest.Downloads
            .Where(item => string.Equals(ResolveGuidedBootstrapPlatform(item), platform, StringComparison.OrdinalIgnoreCase))
            .Where(item => string.Equals(NormalizeBootstrapToken(item.InstallAccessClass), NormalizeBootstrapToken(primaryArtifact.InstallAccessClass), StringComparison.OrdinalIgnoreCase))
            .OrderBy(item => string.Equals(item.Id, primaryId, StringComparison.OrdinalIgnoreCase) ? 0 : 1)
            .ThenBy(item => string.Equals(NormalizeBootstrapToken(item.Arch), expectedArch, StringComparison.OrdinalIgnoreCase) ? 0 : 1)
            .ThenBy(item => MacBootstrapHeadPriority(item.Head))
            .ThenBy(item => item.Id, StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    internal static IReadOnlyList<PublicReleaseArtifactDto> ResolveMacBootstrapArtifacts(
        PublicReleaseManifestDto manifest,
        PublicReleaseArtifactDto primaryArtifact)
    {
        ArgumentNullException.ThrowIfNull(manifest);
        ArgumentNullException.ThrowIfNull(primaryArtifact);

        string? expectedArch = NormalizeBootstrapToken(primaryArtifact.Arch);
        string primaryId = primaryArtifact.Id.Trim();

        return manifest.Downloads
            .Where(IsMacBootstrapArtifact)
            .Where(item => string.Equals(NormalizeBootstrapToken(item.InstallAccessClass), NormalizeBootstrapToken(primaryArtifact.InstallAccessClass), StringComparison.OrdinalIgnoreCase))
            .OrderBy(item => string.Equals(item.Id, primaryId, StringComparison.OrdinalIgnoreCase) ? 0 : 1)
            .ThenBy(item => string.Equals(NormalizeBootstrapToken(item.Arch), expectedArch, StringComparison.OrdinalIgnoreCase) ? 0 : 1)
            .ThenBy(item => MacBootstrapHeadPriority(item.Head))
            .ThenBy(item => item.Id, StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private static string BuildBootstrapCurrentReleaseSummary(string? platform, IReadOnlyList<PublicReleaseArtifactDto> artifacts)
        => platform switch
        {
            "linux" => BuildLinuxBootstrapCurrentReleaseSummary(artifacts),
            _ => BuildMacCurrentReleaseSummary(artifacts)
        };

    internal static string RenderMacInstallBootstrapScript(
        IReadOnlyList<MacInstallBootstrapArtifact> artifacts,
        string publicBaseUrl,
        string accountUrl,
        string downloadsUrl,
        string helpUrl)
    {
        ArgumentNullException.ThrowIfNull(artifacts);
        if (artifacts.Count == 0)
        {
            throw new ArgumentException("at least one Mac bootstrap artifact is required.", nameof(artifacts));
        }

        StringBuilder builder = new();
        builder.AppendLine("#!/usr/bin/env bash");
        builder.AppendLine("set -euo pipefail");
        builder.AppendLine();
        builder.Append("PUBLIC_BASE_URL='").Append(SingleQuoteShellLiteral(publicBaseUrl)).AppendLine("'");
        builder.Append("ACCOUNT_URL='").Append(SingleQuoteShellLiteral(accountUrl)).AppendLine("'");
        builder.Append("DOWNLOADS_URL='").Append(SingleQuoteShellLiteral(downloadsUrl)).AppendLine("'");
        builder.Append("HELP_URL='").Append(SingleQuoteShellLiteral(helpUrl)).AppendLine("'");
        builder.AppendLine("APP_CHOICES=(");
        foreach (var artifact in artifacts)
        {
            builder.Append("  '").Append(SingleQuoteShellLiteral(artifact.ShortLabel)).AppendLine("'");
        }
        builder.AppendLine(")");
        builder.AppendLine("ARTIFACT_TITLES=(");
        foreach (var artifact in artifacts)
        {
            builder.Append("  '").Append(SingleQuoteShellLiteral(artifact.Title)).AppendLine("'");
        }
        builder.AppendLine(")");
        builder.AppendLine("DOWNLOAD_URLS=(");
        foreach (var artifact in artifacts)
        {
            builder.Append("  '").Append(SingleQuoteShellLiteral(artifact.DownloadUrl)).AppendLine("'");
        }
        builder.AppendLine(")");
        builder.AppendLine("CLAIM_CODES=(");
        foreach (var artifact in artifacts)
        {
            builder.Append("  '").Append(SingleQuoteShellLiteral(artifact.ClaimCode)).AppendLine("'");
        }
        builder.AppendLine(")");
        builder.AppendLine("HEAD_IDS=(");
        foreach (var artifact in artifacts)
        {
            builder.Append("  '").Append(SingleQuoteShellLiteral(artifact.HeadId)).AppendLine("'");
        }
        builder.AppendLine(")");
        builder.AppendLine("SHA256_DIGESTS=(");
        foreach (var artifact in artifacts)
        {
            builder.Append("  '").Append(SingleQuoteShellLiteral(artifact.Sha256 ?? string.Empty)).AppendLine("'");
        }
        builder.AppendLine(")");
        builder.AppendLine("DMG_NAMES=(");
        foreach (var artifact in artifacts)
        {
            string fallbackName = string.IsNullOrWhiteSpace(artifact.DmgName) ? "chummer-macos-preview.dmg" : artifact.DmgName;
            builder.Append("  '").Append(SingleQuoteShellLiteral(fallbackName)).AppendLine("'");
        }
        builder.AppendLine(")");
        builder.AppendLine("ARTIFACT_ARCHES=(");
        foreach (var artifact in artifacts)
        {
            builder.Append("  '").Append(SingleQuoteShellLiteral(artifact.Architecture ?? string.Empty)).AppendLine("'");
        }
        builder.AppendLine(")");
        builder.AppendLine("LAUNCH_AFTER_INSTALL=(");
        foreach (var artifact in artifacts)
        {
            builder.Append("  '").Append(artifact.LaunchAfterInstall ? "1" : "0").AppendLine("'");
        }
        builder.AppendLine(")");
        builder.AppendLine("DOWNLOAD_DIR=\"$HOME/Downloads\"");
        builder.AppendLine("WORK_ROOT=\"${TMPDIR:-/tmp}/chummer-install-${RANDOM}\"");
        builder.AppendLine("TARGET_ROOT=\"/Applications\"");
        builder.AppendLine("GUI_ENABLED=0");
        builder.AppendLine("OPEN_SELECTED_AFTER_INSTALL=1");
        builder.AppendLine("INSTALL_SCOPE_DESCRIPTION=\"/Applications\"");
        builder.AppendLine("SHORTCUT_MODE=\"applications\"");
        builder.AppendLine("SHORTCUT_DESCRIPTION=\"Applications only\"");
        builder.AppendLine("declare -a SELECTED_INDEXES=()");
        builder.AppendLine("declare -a DEFAULT_SELECTED_INDEXES=()");
        builder.AppendLine("declare -a DEFAULT_APP_CHOICES=()");
        builder.AppendLine("declare -a INSTALL_WARNINGS=()");
        builder.AppendLine("LINKED_CONFIRMED_COUNT=0");
        builder.AppendLine("TOTAL_STEPS=1");
        builder.AppendLine("CURRENT_STEP=0");
        builder.AppendLine();
        builder.AppendLine("supports_gui() {");
        builder.AppendLine("  command -v osascript >/dev/null 2>&1 && [[ -z \"${CI:-}\" ]]");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("notify_gui() {");
        builder.AppendLine("  local title=\"$1\"");
        builder.AppendLine("  local message=\"$2\"");
        builder.AppendLine("  if [[ \"$GUI_ENABLED\" == \"1\" ]]; then");
        builder.AppendLine("    osascript - \"$title\" \"$message\" <<'APPLESCRIPT' >/dev/null 2>&1 || true");
        builder.AppendLine("on run argv");
        builder.AppendLine("  display notification (item 2 of argv) with title (item 1 of argv)");
        builder.AppendLine("end run");
        builder.AppendLine("APPLESCRIPT");
        builder.AppendLine("  fi");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("run_gui_dialog() {");
        builder.AppendLine("  local script_name=\"$1\"");
        builder.AppendLine("  shift");
        builder.AppendLine("  osascript - \"$script_name\" \"$@\" <<'APPLESCRIPT'");
        builder.AppendLine("on run argv");
        builder.AppendLine("  set commandName to item 1 of argv");
        builder.AppendLine("  set payload to {}");
        builder.AppendLine("  if (count of argv) > 1 then");
        builder.AppendLine("    set payload to items 2 thru -1 of argv");
        builder.AppendLine("  end if");
        builder.AppendLine("  if commandName is \"welcome\" then");
        builder.AppendLine("    display dialog \"Chummer Setup will guide you through installing the current Mac desktop builds, linking them to this account, and optionally opening them when finished.\" with title \"Chummer Setup\" buttons {\"Cancel\", \"Continue\"} default button \"Continue\" with icon note");
        builder.AppendLine("    return \"continue\"");
        builder.AppendLine("  else if commandName is \"select-app-mode\" then");
        builder.AppendLine("    set hostLabel to item 1 of payload");
        builder.AppendLine("    set defaultSummary to item 2 of payload");
        builder.AppendLine("    set promptText to \"Auto select the matching \" & hostLabel & \" builds for this Mac, or choose manually?\"");
        builder.AppendLine("    if defaultSummary is not \"\" then");
        builder.AppendLine("      set promptText to promptText & return & return & \"Auto select:\" & return & defaultSummary");
        builder.AppendLine("    end if");
        builder.AppendLine("    set answer to button returned of (display dialog promptText with title \"Chummer Setup\" buttons {\"Choose manually\", \"Auto select\"} default button \"Auto select\" with icon note)");
        builder.AppendLine("    if answer is \"Auto select\" then");
        builder.AppendLine("      return \"auto\"");
        builder.AppendLine("    end if");
        builder.AppendLine("    return \"manual\"");
        builder.AppendLine("  else if commandName is \"select-apps\" then");
        builder.AppendLine("    set defaultCount to (item 1 of payload) as integer");
        builder.AppendLine("    set defaultItems to {}");
        builder.AppendLine("    if defaultCount > 0 then");
        builder.AppendLine("      set defaultItems to items 2 thru (1 + defaultCount) of payload");
        builder.AppendLine("    end if");
        builder.AppendLine("    set choiceStart to (2 + defaultCount)");
        builder.AppendLine("    set choiceItems to {}");
        builder.AppendLine("    if (count of payload) >= choiceStart then");
        builder.AppendLine("      set choiceItems to items choiceStart thru -1 of payload");
        builder.AppendLine("    end if");
        builder.AppendLine("    set picked to choose from list choiceItems with title \"Chummer Setup\" with prompt \"Choose which Chummer apps to install.\" default items defaultItems OK button name \"Install\" cancel button name \"Cancel\" with multiple selections allowed");
        builder.AppendLine("    if picked is false then error number -128");
        builder.AppendLine("    set AppleScript's text item delimiters to linefeed");
        builder.AppendLine("    return picked as text");
        builder.AppendLine("  else if commandName is \"install-location\" then");
        builder.AppendLine("    set answer to button returned of (display dialog \"Choose where to install the selected apps.\" with title \"Chummer Setup\" buttons {\"Home Applications\", \"Applications\"} default button \"Applications\" with icon note)");
        builder.AppendLine("    return answer");
        builder.AppendLine("  else if commandName is \"launch-behavior\" then");
        builder.AppendLine("    set answer to button returned of (display dialog \"After Chummer finishes installing, do you want the selected apps to open now? They will still be linked to this account either way.\" with title \"Chummer Setup\" buttons {\"Install Only\", \"Install and Open\"} default button \"Install and Open\" with icon note)");
        builder.AppendLine("    return answer");
        builder.AppendLine("  else if commandName is \"shortcut-location\" then");
        builder.AppendLine("    set answer to button returned of (display dialog \"Where should Chummer leave quick access after setup?\" with title \"Chummer Setup\" buttons {\"Applications Folder\", \"Desktop Links\"} default button \"Applications Folder\" with icon note)");
        builder.AppendLine("    return answer");
        builder.AppendLine("  else if commandName is \"complete\" then");
        builder.AppendLine("    set messageText to item 1 of payload");
        builder.AppendLine("    set folderPath to item 2 of payload");
        builder.AppendLine("    set answer to button returned of (display dialog messageText with title \"Chummer Setup\" buttons {\"Done\", \"Open Folder\"} default button \"Done\" with icon note)");
        builder.AppendLine("    if answer is \"Open Folder\" then");
        builder.AppendLine("      tell application \"Finder\" to open POSIX file folderPath");
        builder.AppendLine("    end if");
        builder.AppendLine("    return answer");
        builder.AppendLine("  end if");
        builder.AppendLine("  error \"unknown Chummer Setup action\" number 64");
        builder.AppendLine("end run");
        builder.AppendLine("APPLESCRIPT");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("print_banner() {");
        builder.AppendLine("  echo");
        builder.AppendLine("  echo \"============================================================\"");
        builder.AppendLine("  echo \" Chummer Setup\"");
        builder.AppendLine("  echo \" Guided Mac install for the current desktop preview\"");
        builder.AppendLine("  echo \"============================================================\"");
        builder.AppendLine("  echo");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("render_progress_bar() {");
        builder.AppendLine("  local current=\"$1\"");
        builder.AppendLine("  local total=\"$2\"");
        builder.AppendLine("  local label=\"$3\"");
        builder.AppendLine("  local width=26");
        builder.AppendLine("  local filled=$(( current * width / total ))");
        builder.AppendLine("  local empty=$(( width - filled ))");
        builder.AppendLine("  printf '\\n[%s%s] %d/%d %s\\n' \"$(printf '%*s' \"$filled\" '' | tr ' ' '#')\" \"$(printf '%*s' \"$empty\" '' | tr ' ' '.')\" \"$current\" \"$total\" \"$label\"");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("advance_progress() {");
        builder.AppendLine("  local label=\"$1\"");
        builder.AppendLine("  CURRENT_STEP=$((CURRENT_STEP + 1))");
        builder.AppendLine("  render_progress_bar \"$CURRENT_STEP\" \"$TOTAL_STEPS\" \"$label\"");
        builder.AppendLine("  notify_gui \"Chummer Setup\" \"$label\"");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("resolve_selected_indexes() {");
        builder.AppendLine("  local selection_output mode default_summary host_arch_label");
        builder.AppendLine("  seed_default_selected_indexes");
        builder.AppendLine("  host_arch_label=\"$(describe_arch \"$(current_host_arch)\")\"");
        builder.AppendLine("  default_summary=\"$(default_app_choices_summary)\"");
        builder.AppendLine("  if [[ \"$GUI_ENABLED\" == \"1\" ]]; then");
        builder.AppendLine("    run_gui_dialog welcome >/dev/null");
        builder.AppendLine("    mode=\"$(run_gui_dialog select-app-mode \"$host_arch_label\" \"$default_summary\")\"");
        builder.AppendLine("    if [[ \"$mode\" == \"manual\" ]]; then");
        builder.AppendLine("      selection_output=\"$(run_gui_dialog select-apps \"${#DEFAULT_APP_CHOICES[@]}\" \"${DEFAULT_APP_CHOICES[@]}\" \"${APP_CHOICES[@]}\")\"");
        builder.AppendLine("      while IFS= read -r line; do");
        builder.AppendLine("        [[ -n \"$line\" ]] || continue");
        builder.AppendLine("        for idx in \"${!APP_CHOICES[@]}\"; do");
        builder.AppendLine("          if [[ \"${APP_CHOICES[$idx]}\" == \"$line\" ]]; then");
        builder.AppendLine("            SELECTED_INDEXES+=(\"$idx\")");
        builder.AppendLine("          fi");
        builder.AppendLine("        done");
        builder.AppendLine("      done <<< \"$selection_output\"");
        builder.AppendLine("    fi");
        builder.AppendLine("  fi");
        builder.AppendLine("  if [[ \"${#SELECTED_INDEXES[@]}\" -eq 0 ]]; then");
        builder.AppendLine("    for idx in \"${DEFAULT_SELECTED_INDEXES[@]}\"; do");
        builder.AppendLine("      SELECTED_INDEXES+=(\"$idx\")");
        builder.AppendLine("    done");
        builder.AppendLine("  fi");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("resolve_install_location() {");
        builder.AppendLine("  local choice=\"Applications\"");
        builder.AppendLine("  if [[ \"$GUI_ENABLED\" == \"1\" ]]; then");
        builder.AppendLine("    choice=\"$(run_gui_dialog install-location)\"");
        builder.AppendLine("  fi");
        builder.AppendLine("  if [[ \"$choice\" == \"Home Applications\" ]]; then");
        builder.AppendLine("    TARGET_ROOT=\"$HOME/Applications\"");
        builder.AppendLine("    INSTALL_SCOPE_DESCRIPTION=\"~/Applications\"");
        builder.AppendLine("    mkdir -p \"$TARGET_ROOT\"");
        builder.AppendLine("  else");
        builder.AppendLine("    TARGET_ROOT=\"/Applications\"");
        builder.AppendLine("    INSTALL_SCOPE_DESCRIPTION=\"/Applications\"");
        builder.AppendLine("  fi");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("resolve_launch_behavior() {");
        builder.AppendLine("  if [[ \"$GUI_ENABLED\" == \"1\" ]]; then");
        builder.AppendLine("    local choice");
        builder.AppendLine("    choice=\"$(run_gui_dialog launch-behavior)\"");
        builder.AppendLine("    if [[ \"$choice\" == \"Install Only\" ]]; then");
        builder.AppendLine("      OPEN_SELECTED_AFTER_INSTALL=0");
        builder.AppendLine("    fi");
        builder.AppendLine("  fi");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("resolve_shortcut_location() {");
        builder.AppendLine("  local choice=\"Applications Folder\"");
        builder.AppendLine("  if [[ \"$GUI_ENABLED\" == \"1\" ]]; then");
        builder.AppendLine("    choice=\"$(run_gui_dialog shortcut-location)\"");
        builder.AppendLine("  fi");
        builder.AppendLine("  if [[ \"$choice\" == \"Desktop Links\" ]]; then");
        builder.AppendLine("    SHORTCUT_MODE=\"desktop\"");
        builder.AppendLine("    SHORTCUT_DESCRIPTION=\"Desktop links\"");
        builder.AppendLine("  else");
        builder.AppendLine("    SHORTCUT_MODE=\"applications\"");
        builder.AppendLine("    SHORTCUT_DESCRIPTION=\"Applications folder\"");
        builder.AppendLine("  fi");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("shell_escape() {");
        builder.AppendLine("  printf '%q' \"$1\"");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("normalize_arch() {");
        builder.AppendLine("  local raw=\"${1:-}\"");
        builder.AppendLine("  case \"$(printf '%s' \"$raw\" | tr '[:upper:]' '[:lower:]')\" in");
        builder.AppendLine("    arm64|aarch64)");
        builder.AppendLine("      printf 'arm64'");
        builder.AppendLine("      ;;");
        builder.AppendLine("    x64|x86_64|amd64)");
        builder.AppendLine("      printf 'x64'");
        builder.AppendLine("      ;;");
        builder.AppendLine("    *)");
        builder.AppendLine("      printf '%s' \"$raw\"");
        builder.AppendLine("      ;;");
        builder.AppendLine("  esac");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("describe_arch() {");
        builder.AppendLine("  case \"$(normalize_arch \"${1:-}\")\" in");
        builder.AppendLine("    arm64)");
        builder.AppendLine("      printf 'Apple Silicon'");
        builder.AppendLine("      ;;");
        builder.AppendLine("    x64)");
        builder.AppendLine("      printf 'Intel'");
        builder.AppendLine("      ;;");
        builder.AppendLine("    *)");
        builder.AppendLine("      printf '%s' \"${1:-unknown}\"");
        builder.AppendLine("      ;;");
        builder.AppendLine("  esac");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("current_host_arch() {");
        builder.AppendLine("  normalize_arch \"$(uname -m)\"");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("append_default_index() {");
        builder.AppendLine("  local candidate=\"$1\"");
        builder.AppendLine("  local existing");
        builder.AppendLine("  for existing in \"${DEFAULT_SELECTED_INDEXES[@]:-}\"; do");
        builder.AppendLine("    if [[ \"$existing\" == \"$candidate\" ]]; then");
        builder.AppendLine("      return 0");
        builder.AppendLine("    fi");
        builder.AppendLine("  done");
        builder.AppendLine("  DEFAULT_SELECTED_INDEXES+=(\"$candidate\")");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("seed_default_selected_indexes() {");
        builder.AppendLine("  DEFAULT_SELECTED_INDEXES=()");
        builder.AppendLine("  DEFAULT_APP_CHOICES=()");
        builder.AppendLine("  local host_arch preferred_arch idx");
        builder.AppendLine("  host_arch=\"$(current_host_arch)\"");
        builder.AppendLine("  preferred_arch=\"${ARTIFACT_ARCHES[0]}\"");
        builder.AppendLine("  for idx in \"${!ARTIFACT_ARCHES[@]}\"; do");
        builder.AppendLine("    if [[ \"$(normalize_arch \"${ARTIFACT_ARCHES[$idx]}\")\" == \"$host_arch\" ]]; then");
        builder.AppendLine("      append_default_index \"$idx\"");
        builder.AppendLine("    fi");
        builder.AppendLine("  done");
        builder.AppendLine("  if [[ \"${#DEFAULT_SELECTED_INDEXES[@]}\" -eq 0 ]]; then");
        builder.AppendLine("    for idx in \"${!ARTIFACT_ARCHES[@]}\"; do");
        builder.AppendLine("      if [[ \"$(normalize_arch \"${ARTIFACT_ARCHES[$idx]}\")\" == \"$(normalize_arch \"$preferred_arch\")\" ]]; then");
        builder.AppendLine("        append_default_index \"$idx\"");
        builder.AppendLine("      fi");
        builder.AppendLine("    done");
        builder.AppendLine("  fi");
        builder.AppendLine("  if [[ \"${#DEFAULT_SELECTED_INDEXES[@]}\" -eq 0 ]]; then");
        builder.AppendLine("    for idx in \"${!ARTIFACT_TITLES[@]}\"; do");
        builder.AppendLine("      append_default_index \"$idx\"");
        builder.AppendLine("    done");
        builder.AppendLine("  fi");
        builder.AppendLine("  for idx in \"${DEFAULT_SELECTED_INDEXES[@]}\"; do");
        builder.AppendLine("    DEFAULT_APP_CHOICES+=(\"${APP_CHOICES[$idx]}\")");
        builder.AppendLine("  done");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("default_app_choices_summary() {");
        builder.AppendLine("  if [[ \"${#DEFAULT_APP_CHOICES[@]}\" -eq 0 ]]; then");
        builder.AppendLine("    return 0");
        builder.AppendLine("  fi");
        builder.AppendLine("  printf '%s\\n' \"${DEFAULT_APP_CHOICES[@]}\"");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("resolve_install_state_root() {");
        builder.AppendLine("  if [[ -n \"${CHUMMER_DESKTOP_STATE_ROOT:-}\" ]]; then");
        builder.AppendLine("    printf '%s/Chummer6' \"${CHUMMER_DESKTOP_STATE_ROOT%/}\"");
        builder.AppendLine("    return 0");
        builder.AppendLine("  fi");
        builder.AppendLine("  if [[ -n \"${XDG_DATA_HOME:-}\" ]]; then");
        builder.AppendLine("    printf '%s/Chummer6' \"${XDG_DATA_HOME%/}\"");
        builder.AppendLine("    return 0");
        builder.AppendLine("  fi");
        builder.AppendLine("  printf '%s/.local/share/Chummer6' \"$HOME\"");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("build_install_state_path() {");
        builder.AppendLine("  local head_id=\"$1\"");
        builder.AppendLine("  local artifact_arch");
        builder.AppendLine("  artifact_arch=\"$(normalize_arch \"$2\")\"");
        builder.AppendLine("  printf '%s/install-linking/%s/macos/%s/state.json' \"$(resolve_install_state_root)\" \"$head_id\" \"$artifact_arch\"");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("read_install_state_field() {");
        builder.AppendLine("  local state_path=\"$1\"");
        builder.AppendLine("  local field_name=\"$2\"");
        builder.AppendLine("  [[ -f \"$state_path\" ]] || return 1");
        builder.AppendLine("  /usr/bin/plutil -extract \"$field_name\" raw -o - \"$state_path\" 2>/dev/null");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("wait_for_claim_success() {");
        builder.AppendLine("  local state_path=\"$1\"");
        builder.AppendLine("  local timeout_seconds=\"$2\"");
        builder.AppendLine("  local elapsed=0");
        builder.AppendLine("  local claim_status grant_token claimed_at");
        builder.AppendLine("  while (( elapsed < timeout_seconds )); do");
        builder.AppendLine("    claim_status=\"$(read_install_state_field \"$state_path\" status || true)\"");
        builder.AppendLine("    grant_token=\"$(read_install_state_field \"$state_path\" grantToken || true)\"");
        builder.AppendLine("    claimed_at=\"$(read_install_state_field \"$state_path\" claimedAtUtc || true)\"");
        builder.AppendLine("    if [[ \"$claim_status\" == \"claimed\" && -n \"$grant_token\" && -n \"$claimed_at\" ]]; then");
        builder.AppendLine("      return 0");
        builder.AppendLine("    fi");
        builder.AppendLine("    sleep 1");
        builder.AppendLine("    elapsed=$((elapsed + 1))");
        builder.AppendLine("  done");
        builder.AppendLine("  return 1");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("verify_download_digest() {");
        builder.AppendLine("  local file_path=\"$1\"");
        builder.AppendLine("  local expected_digest=\"$2\"");
        builder.AppendLine("  [[ -n \"$expected_digest\" ]] || return 0");
        builder.AppendLine("  command -v shasum >/dev/null 2>&1 || { echo \"shasum is required to verify downloaded Mac installers.\" >&2; exit 1; }");
        builder.AppendLine("  local actual_digest normalized_expected");
        builder.AppendLine("  actual_digest=\"$(shasum -a 256 \"$file_path\" | awk '{print tolower($1)}')\"");
        builder.AppendLine("  normalized_expected=\"$(printf '%s' \"$expected_digest\" | tr '[:upper:]' '[:lower:]')\"");
        builder.AppendLine("  if [[ \"$actual_digest\" != \"$normalized_expected\" ]]; then");
        builder.AppendLine("    echo \"SHA-256 mismatch for $(basename \"$file_path\").\" >&2");
        builder.AppendLine("    echo \"Expected: $normalized_expected\" >&2");
        builder.AppendLine("    echo \"Actual:   $actual_digest\" >&2");
        builder.AppendLine("    rm -f \"$file_path\"");
        builder.AppendLine("    exit 1");
        builder.AppendLine("  fi");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("run_privileged_shell() {");
        builder.AppendLine("  local command_text=\"$1\"");
        builder.AppendLine("  osascript - \"$command_text\" <<'APPLESCRIPT'");
        builder.AppendLine("on run argv");
        builder.AppendLine("  do shell script (item 1 of argv) with administrator privileges");
        builder.AppendLine("end run");
        builder.AppendLine("APPLESCRIPT");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("run_privileged_script() {");
        builder.AppendLine("  local script_path=\"$1\"");
        builder.AppendLine("  shift");
        builder.AppendLine("  local command_text");
        builder.AppendLine("  command_text=\"/bin/bash $(shell_escape \"$script_path\")\"");
        builder.AppendLine("  local arg");
        builder.AppendLine("  for arg in \"$@\"; do");
        builder.AppendLine("    command_text+=\" $(shell_escape \"$arg\")\"");
        builder.AppendLine("  done");
        builder.AppendLine("  run_privileged_shell \"$command_text\"");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("perform_staged_install() {");
        builder.AppendLine("  local app_source=\"$1\"");
        builder.AppendLine("  local target_app=\"$2\"");
        builder.AppendLine("  local app_name target_root staged_app backup_app had_backup=0");
        builder.AppendLine("  app_name=\"$(basename \"$target_app\")\"");
        builder.AppendLine("  target_root=\"$(dirname \"$target_app\")\"");
        builder.AppendLine("  staged_app=\"$target_root/.${app_name}.staged.$$\"");
        builder.AppendLine("  backup_app=\"$target_root/.${app_name}.backup.$$\"");
        builder.AppendLine("  rm -rf \"$staged_app\" \"$backup_app\"");
        builder.AppendLine("  ditto \"$app_source\" \"$staged_app\"");
        builder.AppendLine("  [[ -d \"$staged_app\" ]] || { echo \"Failed to stage $app_name before install.\" >&2; return 1; }");
        builder.AppendLine("  if [[ -e \"$target_app\" ]]; then");
        builder.AppendLine("    mv \"$target_app\" \"$backup_app\"");
        builder.AppendLine("    had_backup=1");
        builder.AppendLine("  fi");
        builder.AppendLine("  if mv \"$staged_app\" \"$target_app\"; then");
        builder.AppendLine("    rm -rf \"$backup_app\"");
        builder.AppendLine("    return 0");
        builder.AppendLine("  fi");
        builder.AppendLine("  rm -rf \"$staged_app\"");
        builder.AppendLine("  if [[ \"$had_backup\" == \"1\" && -e \"$backup_app\" ]]; then");
        builder.AppendLine("    mv \"$backup_app\" \"$target_app\" || true");
        builder.AppendLine("  fi");
        builder.AppendLine("  echo \"Install swap failed for $app_name; the previous app bundle was restored.\" >&2");
        builder.AppendLine("  return 1");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("report_architecture_posture() {");
        builder.AppendLine("  local host_arch artifact_arch idx");
        builder.AppendLine("  host_arch=\"$(current_host_arch)\"");
        builder.AppendLine("  echo \"Current Mac architecture: $(describe_arch \"$host_arch\")\"");
        builder.AppendLine("  for idx in \"${SELECTED_INDEXES[@]}\"; do");
        builder.AppendLine("    artifact_arch=\"$(normalize_arch \"${ARTIFACT_ARCHES[$idx]}\")\"");
        builder.AppendLine("    [[ -n \"$artifact_arch\" ]] || continue");
        builder.AppendLine("    echo \"Selected build: ${APP_CHOICES[$idx]}\"");
        builder.AppendLine("    echo \"Published artifact: ${ARTIFACT_TITLES[$idx]}\"");
        builder.AppendLine("    if [[ \"$host_arch\" == \"arm64\" && \"$artifact_arch\" == \"x64\" ]]; then");
        builder.AppendLine("      INSTALL_WARNINGS+=(\"${ARTIFACT_TITLES[$idx]} targets Intel Mac hardware. macOS may prompt for Rosetta on Apple Silicon.\")");
        builder.AppendLine("    fi");
        builder.AppendLine("  done");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("wait_for_launch_observation() {");
        builder.AppendLine("  local target_app=\"$1\"");
        builder.AppendLine("  local attempt");
        builder.AppendLine("  for attempt in 1 2 3 4 5 6 7 8 9 10; do");
        builder.AppendLine("    if pgrep -f \"$target_app\" >/dev/null 2>&1; then");
        builder.AppendLine("      return 0");
        builder.AppendLine("    fi");
        builder.AppendLine("    sleep 1");
        builder.AppendLine("  done");
        builder.AppendLine("  return 1");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("launch_bundle_binary_with_claim() {");
        builder.AppendLine("  local target_app=\"$1\"");
        builder.AppendLine("  local claim_code=\"$2\"");
        builder.AppendLine("  local executable_path");
        builder.AppendLine("  executable_path=\"$(find \"$target_app/Contents/MacOS\" -maxdepth 1 -type f -perm -111 -print -quit)\"");
        builder.AppendLine("  if [[ -z \"$executable_path\" ]]; then");
        builder.AppendLine("    INSTALL_WARNINGS+=(\"Could not find a launchable executable in $target_app. Open it manually once if Devices and access does not show it yet.\")");
        builder.AppendLine("    return 1");
        builder.AppendLine("  fi");
        builder.AppendLine("  env CHUMMER_INSTALL_CLAIM_CODE=\"$claim_code\" CHUMMER_API_BASE_URL=\"$PUBLIC_BASE_URL\" CHUMMER_WEB_BASE_URL=\"$PUBLIC_BASE_URL\" \"$executable_path\" >/dev/null 2>&1 &");
        builder.AppendLine("  printf '%s' \"$!\"");
        builder.AppendLine("  return 0");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("build_claim_download_url() {");
        builder.AppendLine("  local base_url=\"$1\"");
        builder.AppendLine("  local claim_code=\"$2\"");
        builder.AppendLine("  if [[ -z \"$claim_code\" ]]; then");
        builder.AppendLine("    printf '%s' \"$base_url\"");
        builder.AppendLine("    return 0");
        builder.AppendLine("  fi");
        builder.AppendLine("  if [[ \"$base_url\" == *\\?* ]]; then");
        builder.AppendLine("    printf '%s&claimCode=%s' \"$base_url\" \"$claim_code\"");
        builder.AppendLine("    return 0");
        builder.AppendLine("  fi");
        builder.AppendLine("  printf '%s?claimCode=%s' \"$base_url\" \"$claim_code\"");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("create_desktop_link() {");
        builder.AppendLine("  local target_app=\"$1\"");
        builder.AppendLine("  local desktop_dir=\"$HOME/Desktop\"");
        builder.AppendLine("  local link_path=\"$desktop_dir/$(basename \"$target_app\")\"");
        builder.AppendLine("  if [[ ! -d \"$desktop_dir\" ]]; then");
        builder.AppendLine("    INSTALL_WARNINGS+=(\"Desktop links were requested, but $desktop_dir is not available on this Mac.\")");
        builder.AppendLine("    return 0");
        builder.AppendLine("  fi");
        builder.AppendLine("  rm -f \"$link_path\"");
        builder.AppendLine("  if ln -s \"$target_app\" \"$link_path\"; then");
        builder.AppendLine("    echo \"Desktop link created: $link_path\"");
        builder.AppendLine("    return 0");
        builder.AppendLine("  fi");
        builder.AppendLine("  INSTALL_WARNINGS+=(\"Could not create the Desktop link for $(basename \"$target_app\"). Open it from $target_app instead.\")");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("cleanup() {");
        builder.AppendLine("  for mount_point in \"${MOUNT_POINTS[@]:-}\"; do");
        builder.AppendLine("    if [[ -n \"$mount_point\" && -d \"$mount_point\" ]] && mount | grep -Fq \" on $mount_point \"; then");
        builder.AppendLine("      hdiutil detach \"$mount_point\" -quiet >/dev/null 2>&1 || true");
        builder.AppendLine("    fi");
        builder.AppendLine("  done");
        builder.AppendLine("  rm -rf \"$WORK_ROOT\"");
        builder.AppendLine("}");
        builder.AppendLine("trap cleanup EXIT");
        builder.AppendLine();
        builder.AppendLine("if supports_gui; then");
        builder.AppendLine("  GUI_ENABLED=1");
        builder.AppendLine("fi");
        builder.AppendLine();
        builder.AppendLine("print_banner");
        builder.AppendLine("resolve_selected_indexes");
        builder.AppendLine("resolve_install_location");
        builder.AppendLine("resolve_launch_behavior");
        builder.AppendLine("resolve_shortcut_location");
        builder.AppendLine("mkdir -p \"$DOWNLOAD_DIR\" \"$WORK_ROOT\"");
        builder.AppendLine("if [[ \"$GUI_ENABLED\" != \"1\" && \"$TARGET_ROOT\" == \"/Applications\" && ! -w \"$TARGET_ROOT\" ]]; then");
        builder.AppendLine("  TARGET_ROOT=\"$HOME/Applications\"");
        builder.AppendLine("  INSTALL_SCOPE_DESCRIPTION=\"~/Applications\"");
        builder.AppendLine("fi");
        builder.AppendLine();
        builder.AppendLine("if [[ \"$TARGET_ROOT\" != \"/Applications\" ]]; then");
        builder.AppendLine("  mkdir -p \"$TARGET_ROOT\"");
        builder.AppendLine("fi");
        builder.AppendLine();
        builder.AppendLine("declare -a INSTALLED_APPS=()");
        builder.AppendLine("declare -a INSTALLED_ARTIFACT_INDEXES=()");
        builder.AppendLine("declare -a MOUNT_POINTS=()");
        builder.AppendLine("TOTAL_STEPS=$((2 + ${#SELECTED_INDEXES[@]} * 4 + 1))");
        builder.AppendLine("advance_progress \"Preparing the guided Mac install\"");        
        builder.AppendLine("echo \"Selected apps:\"");
        builder.AppendLine("for idx in \"${SELECTED_INDEXES[@]}\"; do");
        builder.AppendLine("  echo \" - ${APP_CHOICES[$idx]}\"");
        builder.AppendLine("done");
        builder.AppendLine("echo \"Install destination: $INSTALL_SCOPE_DESCRIPTION\"");
        builder.AppendLine("report_architecture_posture");
        builder.AppendLine("echo \"Quick access: $SHORTCUT_DESCRIPTION\"");
        builder.AppendLine("if [[ \"$OPEN_SELECTED_AFTER_INSTALL\" == \"1\" ]]; then");
        builder.AppendLine("  echo \"Finish behavior: open the selected apps when installation completes\"");
        builder.AppendLine("else");
        builder.AppendLine("  echo \"Finish behavior: link quietly and leave the apps closed in the foreground\"");
        builder.AppendLine("fi");
        builder.AppendLine("advance_progress \"Checking install destination permissions\"");
        builder.AppendLine("if [[ \"$TARGET_ROOT\" == \"/Applications\" && ! -w \"$TARGET_ROOT\" ]]; then");
        builder.AppendLine("  echo \"Installing into /Applications requires administrator approval.\"");
        builder.AppendLine("fi");
        builder.AppendLine();
        builder.AppendLine("install_artifact() {");
        builder.AppendLine("  local idx=\"$1\"");
        builder.AppendLine("  local artifact_title=\"${ARTIFACT_TITLES[$idx]}\"");
        builder.AppendLine("  local claim_code=\"${CLAIM_CODES[$idx]}\"");
        builder.AppendLine("  local download_url");
        builder.AppendLine("  local expected_sha256=\"${SHA256_DIGESTS[$idx]}\"");
        builder.AppendLine("  local dmg_name=\"${DMG_NAMES[$idx]}\"");
        builder.AppendLine("  local stage_root=\"$WORK_ROOT/$idx\"");
        builder.AppendLine("  local mount_point=\"$stage_root/mount\"");
        builder.AppendLine("  local dmg_path=\"$DOWNLOAD_DIR/$dmg_name\"");
        builder.AppendLine("  mkdir -p \"$stage_root\" \"$mount_point\"");
        builder.AppendLine("  MOUNT_POINTS+=(\"$mount_point\")");
        builder.AppendLine("  download_url=\"$(build_claim_download_url \"${DOWNLOAD_URLS[$idx]}\" \"$claim_code\")\"");
        builder.AppendLine("  advance_progress \"Downloading $artifact_title\"");
        builder.AppendLine("  echo \"Downloading $artifact_title to $dmg_path\"");
        builder.AppendLine("  local http_code");
        builder.AppendLine("  http_code=\"$(curl --silent --show-error --location --progress-bar --output \"$dmg_path\" --write-out '%{http_code}' \"$download_url\")\"");
        builder.AppendLine("  if [[ \"$http_code\" != \"200\" ]]; then");
        builder.AppendLine("    rm -f \"$dmg_path\"");
        builder.AppendLine("    echo \"The Mac setup handoff expired or could not download $artifact_title (HTTP $http_code).\" >&2");
        builder.AppendLine("    echo \"Re-open the Mac install handoff and copy a fresh Terminal command from: $DOWNLOADS_URL\" >&2");
        builder.AppendLine("    exit 1");
        builder.AppendLine("  fi");
        builder.AppendLine("  verify_download_digest \"$dmg_path\" \"$expected_sha256\"");
        builder.AppendLine("  advance_progress \"Mounting $artifact_title\"");
        builder.AppendLine("  echo \"Mounting installer image for $artifact_title at $mount_point\"");
        builder.AppendLine("  hdiutil attach \"$dmg_path\" -nobrowse -mountpoint \"$mount_point\" >/dev/null");
        builder.AppendLine("  local app_source");
        builder.AppendLine("  app_source=\"$(find \"$mount_point\" -maxdepth 2 -name '*.app' -print -quit)\"");
        builder.AppendLine("  if [[ -z \"$app_source\" ]]; then");
        builder.AppendLine("    echo \"No app bundle was found inside the mounted image for $artifact_title.\" >&2");
        builder.AppendLine("    exit 1");
        builder.AppendLine("  fi");
        builder.AppendLine("  local app_name");
        builder.AppendLine("  app_name=\"$(basename \"$app_source\")\"");
        builder.AppendLine("  local target_app=\"$TARGET_ROOT/$app_name\"");
        builder.AppendLine("  advance_progress \"Installing $artifact_title\"");
        builder.AppendLine("  echo \"Installing $artifact_title to $target_app\"");
        builder.AppendLine("  if [[ \"$TARGET_ROOT\" == \"/Applications\" && ! -w \"$TARGET_ROOT\" ]]; then");
        builder.AppendLine("    local privileged_script=\"$stage_root/install-into-applications.sh\"");
        builder.AppendLine("    cat > \"$privileged_script\" <<'SCRIPT'");
        builder.AppendLine("#!/usr/bin/env bash");
        builder.AppendLine("set -euo pipefail");
        builder.AppendLine("app_source=\"$1\"");
        builder.AppendLine("target_app=\"$2\"");
        builder.AppendLine("app_name=\"$(basename \"$target_app\")\"");
        builder.AppendLine("target_root=\"$(dirname \"$target_app\")\"");
        builder.AppendLine("staged_app=\"$target_root/.${app_name}.staged.$$\"");
        builder.AppendLine("backup_app=\"$target_root/.${app_name}.backup.$$\"");
        builder.AppendLine("had_backup=0");
        builder.AppendLine("rm -rf \"$staged_app\" \"$backup_app\"");
        builder.AppendLine("ditto \"$app_source\" \"$staged_app\"");
        builder.AppendLine("[[ -d \"$staged_app\" ]] || { echo \"Failed to stage $app_name before install.\" >&2; exit 1; }");
        builder.AppendLine("if [[ -e \"$target_app\" ]]; then");
        builder.AppendLine("  mv \"$target_app\" \"$backup_app\"");
        builder.AppendLine("  had_backup=1");
        builder.AppendLine("fi");
        builder.AppendLine("if mv \"$staged_app\" \"$target_app\"; then");
        builder.AppendLine("  rm -rf \"$backup_app\"");
        builder.AppendLine("  exit 0");
        builder.AppendLine("fi");
        builder.AppendLine("rm -rf \"$staged_app\"");
        builder.AppendLine("if [[ \"$had_backup\" == \"1\" && -e \"$backup_app\" ]]; then");
        builder.AppendLine("  mv \"$backup_app\" \"$target_app\" || true");
        builder.AppendLine("fi");
        builder.AppendLine("echo \"Install swap failed for $app_name; the previous app bundle was restored.\" >&2");
        builder.AppendLine("exit 1");
        builder.AppendLine("SCRIPT");
        builder.AppendLine("    chmod 700 \"$privileged_script\"");
        builder.AppendLine("    run_privileged_script \"$privileged_script\" \"$app_source\" \"$target_app\"");
        builder.AppendLine("  else");
        builder.AppendLine("    perform_staged_install \"$app_source\" \"$target_app\"");
        builder.AppendLine("  fi");
        builder.AppendLine("  hdiutil detach \"$mount_point\" -quiet >/dev/null || true");
        builder.AppendLine("  if [[ \"$SHORTCUT_MODE\" == \"desktop\" ]]; then");
        builder.AppendLine("    create_desktop_link \"$target_app\"");
        builder.AppendLine("  fi");
        builder.AppendLine("  INSTALLED_APPS+=(\"$target_app\")");
        builder.AppendLine("  INSTALLED_ARTIFACT_INDEXES+=(\"$idx\")");
        builder.AppendLine("}");
        builder.AppendLine("launch_installed_app() {");
        builder.AppendLine("  local installed_idx=\"$1\"");
        builder.AppendLine("  local artifact_idx=\"${INSTALLED_ARTIFACT_INDEXES[$installed_idx]}\"");
        builder.AppendLine("  local target_app=\"${INSTALLED_APPS[$installed_idx]}\"");
        builder.AppendLine("  local claim_code=\"${CLAIM_CODES[$artifact_idx]}\"");
        builder.AppendLine("  local head_id=\"${HEAD_IDS[$artifact_idx]}\"");
        builder.AppendLine("  local artifact_arch=\"${ARTIFACT_ARCHES[$artifact_idx]}\"");
        builder.AppendLine("  local artifact_title=\"${ARTIFACT_TITLES[$artifact_idx]}\"");
        builder.AppendLine("  local state_path");
        builder.AppendLine("  local launch_pid");
        builder.AppendLine("  local claim_message claim_error claim_status");
        builder.AppendLine("  state_path=\"$(build_install_state_path \"$head_id\" \"$artifact_arch\")\"");
        builder.AppendLine("  advance_progress \"Linking $artifact_title to this account\"");
        builder.AppendLine("  echo \"Linking $artifact_title to this account...\"");
        builder.AppendLine("  if [[ -z \"$claim_code\" ]]; then");
        builder.AppendLine("    INSTALL_WARNINGS+=(\"$artifact_title could not find the embedded short-lived install claim for this handoff. Re-open the current Mac install command from $DOWNLOADS_URL and run it again.\")");
        builder.AppendLine("    return 0");
        builder.AppendLine("  fi");
        builder.AppendLine("  launch_pid=\"$(launch_bundle_binary_with_claim \"$target_app\" \"$claim_code\")\" || {");
        builder.AppendLine("    return 0");
        builder.AppendLine("  }");
        builder.AppendLine("  if ! wait_for_launch_observation \"$target_app\"; then");
        builder.AppendLine("    INSTALL_WARNINGS+=(\"$artifact_title did not stay running long enough to confirm first-launch linking. Open it once manually from $target_app if Devices and access does not show it yet.\")");
        builder.AppendLine("  fi");
        builder.AppendLine("  if wait_for_claim_success \"$state_path\" 25; then");
        builder.AppendLine("    LINKED_CONFIRMED_COUNT=$((LINKED_CONFIRMED_COUNT + 1))");
        builder.AppendLine("    claim_message=\"$(read_install_state_field \"$state_path\" lastClaimMessage || true)\"");
        builder.AppendLine("    if [[ -n \"$claim_message\" ]]; then");
        builder.AppendLine("      echo \"$artifact_title: $claim_message\"");
        builder.AppendLine("    else");
        builder.AppendLine("      echo \"$artifact_title linked successfully.\"");
        builder.AppendLine("    fi");
        builder.AppendLine("  else");
        builder.AppendLine("    claim_error=\"$(read_install_state_field \"$state_path\" lastClaimError || true)\"");
        builder.AppendLine("    claim_status=\"$(read_install_state_field \"$state_path\" status || true)\"");
        builder.AppendLine("    if [[ -n \"$claim_error\" ]]; then");
        builder.AppendLine("      INSTALL_WARNINGS+=(\"$artifact_title could not confirm account linking automatically: $claim_error Re-run the current Mac install command or open $target_app manually once if Devices and access does not show it yet.\")");
        builder.AppendLine("    elif [[ -n \"$claim_status\" ]]; then");
        builder.AppendLine("      INSTALL_WARNINGS+=(\"$artifact_title finished first-launch work with status '$claim_status' instead of a confirmed linked state. Re-run the current Mac install command or open $target_app manually once if Devices and access does not show it yet.\")");
        builder.AppendLine("    else");
        builder.AppendLine("      INSTALL_WARNINGS+=(\"$artifact_title did not write a confirmed install-link receipt yet. Re-run the current Mac install command or open $target_app manually once if Devices and access does not show it yet.\")");
        builder.AppendLine("    fi");
        builder.AppendLine("  fi");
        builder.AppendLine("  if [[ \"$OPEN_SELECTED_AFTER_INSTALL\" == \"1\" && \"${LAUNCH_AFTER_INSTALL[$artifact_idx]}\" == \"1\" ]]; then");
        builder.AppendLine("    if [[ -n \"$launch_pid\" ]]; then");
        builder.AppendLine("      kill \"$launch_pid\" >/dev/null 2>&1 || true");
        builder.AppendLine("      wait \"$launch_pid\" >/dev/null 2>&1 || true");
        builder.AppendLine("    fi");
        builder.AppendLine("    open -n \"$target_app\" >/dev/null 2>&1 || true");
        builder.AppendLine("  else");
        builder.AppendLine("    sleep 2");
        builder.AppendLine("    if [[ -n \"$launch_pid\" ]]; then");
        builder.AppendLine("      kill \"$launch_pid\" >/dev/null 2>&1 || true");
        builder.AppendLine("      wait \"$launch_pid\" >/dev/null 2>&1 || true");
        builder.AppendLine("    fi");
        builder.AppendLine("  fi");
        builder.AppendLine("}");
        builder.AppendLine();
        builder.AppendLine("for idx in \"${SELECTED_INDEXES[@]}\"; do");
        builder.AppendLine("  install_artifact \"$idx\"");
        builder.AppendLine("done");
        builder.AppendLine();
        builder.AppendLine("echo");
        builder.AppendLine("echo \"Installed Mac desktop builds:\"");
        builder.AppendLine("for target_app in \"${INSTALLED_APPS[@]}\"; do");
        builder.AppendLine("  echo \" - $target_app\"");
        builder.AppendLine("done");
        builder.AppendLine("echo \"Running a first-launch link check for the selected installs...\"");
        builder.AppendLine("for install_idx in \"${!INSTALLED_APPS[@]}\"; do");
        builder.AppendLine("  launch_installed_app \"$install_idx\"");
        builder.AppendLine("done");
        builder.AppendLine("advance_progress \"Finishing Chummer Setup\"");
        builder.AppendLine("echo");
        builder.AppendLine("echo \"Confirmed linked installs: $LINKED_CONFIRMED_COUNT / ${#INSTALLED_APPS[@]}\"");
        builder.AppendLine("if [[ \"$LINKED_CONFIRMED_COUNT\" -eq \"${#INSTALLED_APPS[@]}\" ]]; then");
        builder.AppendLine("  echo \"The selected Chummer app or apps were installed and linked to this account.\"");
        builder.AppendLine("  echo \"When you open them again later, they should already be linked to this account.\"");
        builder.AppendLine("  COMPLETION_MESSAGE=\"The selected Chummer apps are installed in $INSTALL_SCOPE_DESCRIPTION and verified as linked to this account.\"");
        builder.AppendLine("else");
        builder.AppendLine("  echo \"The selected Chummer app or apps were installed, but setup could not confirm linking for every app yet.\"");
        builder.AppendLine("  echo \"If Devices and access does not show them, rerun the current install command or open the app manually once.\"");
        builder.AppendLine("  COMPLETION_MESSAGE=\"The selected Chummer apps are installed in $INSTALL_SCOPE_DESCRIPTION, but setup could not confirm linking for every app yet. Review the setup notes before closing this window.\"");
        builder.AppendLine("fi");
        builder.AppendLine("if [[ \"${#INSTALL_WARNINGS[@]}\" -gt 0 ]]; then");
        builder.AppendLine("  echo");
        builder.AppendLine("  echo \"Setup notes:\"");
        builder.AppendLine("  warning=''");
        builder.AppendLine("  for warning in \"${INSTALL_WARNINGS[@]}\"; do");
        builder.AppendLine("    echo \" - $warning\"");
        builder.AppendLine("  done");
        builder.AppendLine("fi");
        builder.AppendLine("echo \"Devices and access: $ACCOUNT_URL\"");
        builder.AppendLine("echo \"Downloads shelf: $DOWNLOADS_URL\"");
        builder.AppendLine("echo \"Help: $HELP_URL\"");
        builder.AppendLine("if [[ \"$GUI_ENABLED\" == \"1\" ]]; then");
        builder.AppendLine("  run_gui_dialog complete \"$COMPLETION_MESSAGE\" \"$TARGET_ROOT\" >/dev/null || true");
        builder.AppendLine("fi");
        return builder.ToString();
    }

    private async Task<(GuidedBootstrapScriptContext? Context, IActionResult? Failure)> TryBuildGuidedBootstrapContextAsync(
        string artifactId,
        string requiredPlatform,
        CancellationToken cancellationToken)
    {
        var (manifest, artifact) = ResolveInstallDispatchArtifact(artifactId);
        if (artifact is null)
        {
            return (null, NotFound());
        }

        if (!_releaseSelection.UsesGuidedBootstrapScript(artifact)
            || !string.Equals(ResolveGuidedBootstrapPlatform(artifact), requiredPlatform, StringComparison.OrdinalIgnoreCase))
        {
            return (null, NotFound());
        }

        string? bootstrapTicket = Request.Query["ticket"].ToString();
        string? claimCode = Request.Query["claimCode"].ToString();
        string? userId = null;
        string? subjectId = null;

        if (!string.IsNullOrWhiteSpace(bootstrapTicket))
        {
            bootstrapTicket = bootstrapTicket.Trim();
            if (!_installBootstrapTickets.TryValidateForArtifact(bootstrapTicket, artifact.Id, out InstallBootstrapTicketClaims? ticketClaims)
                || ticketClaims is null)
            {
                Response.Headers["Cache-Control"] = "private, no-store";
                return (null, Unauthorized(new
                {
                    error = "invalid_or_expired_install_ticket",
                    message = "The install command expired. Re-open the signed-in downloads handoff and copy a fresh install command."
                }));
            }

            userId = ticketClaims.UserId;
            subjectId = ticketClaims.SubjectId;
        }
        else if (!string.IsNullOrWhiteSpace(claimCode))
        {
            InstallClaimTicketDto? primaryClaimTicket = _installLinking.ResolveClaimTicketForDownload(artifact.Id, claimCode);
            if (primaryClaimTicket is null
                || (string.IsNullOrWhiteSpace(primaryClaimTicket.UserId) && string.IsNullOrWhiteSpace(primaryClaimTicket.SubjectId)))
            {
                Response.Headers["Cache-Control"] = "private, no-store";
                return (null, Unauthorized(new
                {
                    error = "invalid_or_expired_claim_code",
                    message = "The install command expired. Re-open the signed-in downloads handoff and copy a fresh install command."
                }));
            }

            userId = primaryClaimTicket.UserId;
            subjectId = primaryClaimTicket.SubjectId;
        }
        else
        {
            try
            {
                var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
                var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
                userId = user.UserId;
                subjectId = subject.SubjectId;
            }
            catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
            {
                return (null, Redirect($"/auth/google/start?next={Uri.EscapeDataString($"/downloads/install/{artifactId}")}"));
            }
            catch (HubRequestAuthException ex)
            {
                _logger.LogWarning(ex, "{Platform} bootstrap handoff could not confirm the signed-in identity.", requiredPlatform);
                return (null, Problem(statusCode: ex.StatusCode, detail: ex.Message));
            }
        }

        IReadOnlyList<PublicReleaseArtifactDto> guidedArtifacts = ResolveGuidedBootstrapArtifacts(manifest, artifact);

        if (guidedArtifacts.Count == 0)
        {
            return (null, Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: $"no {requiredPlatform} bootstrap artifacts are available for this handoff."));
        }

        string effectiveBootstrapTicket = !string.IsNullOrWhiteSpace(bootstrapTicket)
            ? bootstrapTicket
            : _installBootstrapTickets.Issue(
                artifact.Id,
                guidedArtifacts.Select(candidate => candidate.Id),
                userId,
                subjectId).Ticket;

        var scriptArtifacts = guidedArtifacts
            .Select(candidate =>
            {
                var candidateOption = _releaseSelection.BuildOption(manifest, candidate, authenticated: true, recommended: false);
                return new GuidedBootstrapArtifact(
                    ArtifactId: candidate.Id,
                    HeadId: candidate.Head ?? string.Empty,
                    Title: BuildGuidedBootstrapArtifactTitle(candidate),
                    ShortLabel: BuildGuidedBootstrapShortLabel(candidate),
                    DownloadUrl: BuildAbsoluteUrl(
                        candidateOption.DirectFileHref,
                        QueryString.Create("ticket", effectiveBootstrapTicket)),
                    ClaimUrl: BuildAbsoluteUrl(
                        $"/downloads/install/{Uri.EscapeDataString(candidate.Id)}/continue.json",
                        QueryString.Create("ticket", effectiveBootstrapTicket)),
                    Sha256: candidate.Sha256,
                    PackageName: candidate.FileName ?? Path.GetFileName(candidate.Url),
                    Architecture: candidate.Arch,
                    LaunchAfterInstall: string.Equals(candidate.Id, artifact.Id, StringComparison.OrdinalIgnoreCase),
                    InstallFolderName: ResolveGuidedBootstrapInstallFolderName(candidate),
                    ExecutableName: ResolveGuidedBootstrapExecutableName(candidate),
                    LauncherName: ResolveGuidedBootstrapLauncherName(candidate),
                    DesktopEntryName: ResolveGuidedBootstrapDesktopEntryName(candidate));
            })
            .ToArray();

        return (new GuidedBootstrapScriptContext(manifest, artifact, scriptArtifacts, effectiveBootstrapTicket, userId, subjectId), null);
    }

    private (PublicReleaseManifestDto Manifest, PublicReleaseArtifactDto? Artifact) ResolveInstallDispatchArtifact(string artifactId)
    {
        PublicReleaseManifestDto rawManifest = _releases.LoadManifest();
        PublicReleaseManifestDto publicManifest = _releaseSelection.ApplyAccessPolicy(rawManifest);
        PublicReleaseArtifactDto? artifact = publicManifest.Downloads
            .FirstOrDefault(item => string.Equals(item.Id, artifactId, StringComparison.OrdinalIgnoreCase));
        if (artifact is not null)
        {
            return (publicManifest, artifact);
        }

        artifact = rawManifest.Downloads
            .FirstOrDefault(item => string.Equals(item.Id, artifactId, StringComparison.OrdinalIgnoreCase));
        return (rawManifest, artifact);
    }

    private static bool IsMacBootstrapArtifact(PublicReleaseArtifactDto artifact)
    {
        string platformToken = $"{artifact.PlatformId} {artifact.Platform} {artifact.Url}";
        return platformToken.Contains("mac", StringComparison.OrdinalIgnoreCase)
            || platformToken.Contains("osx", StringComparison.OrdinalIgnoreCase)
            || ((artifact.FileName ?? string.Empty).EndsWith(".dmg", StringComparison.OrdinalIgnoreCase));
    }

    private static bool IsLinuxBootstrapArtifact(PublicReleaseArtifactDto artifact)
    {
        string platformToken = $"{artifact.PlatformId} {artifact.Platform} {artifact.Url}";
        return (platformToken.Contains("linux", StringComparison.OrdinalIgnoreCase)
                || ((artifact.FileName ?? string.Empty).EndsWith(".deb", StringComparison.OrdinalIgnoreCase)))
               && (artifact.Url.EndsWith(".deb", StringComparison.OrdinalIgnoreCase)
                   || (artifact.FileName ?? string.Empty).EndsWith(".deb", StringComparison.OrdinalIgnoreCase));
    }

    private static string? NormalizeBootstrapToken(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static int MacBootstrapHeadPriority(string? head)
        => NormalizeBootstrapToken(head)?.ToLowerInvariant() switch
        {
            "avalonia" => 0,
            "blazor-desktop" => 1,
            _ => 9
        };

    private static string BuildMacCurrentReleaseSummary(IReadOnlyList<PublicReleaseArtifactDto> artifacts)
    {
        if (artifacts.Count == 0)
        {
            return "macOS desktop setup handoff";
        }

        string heads = string.Join(
            " + ",
            artifacts
                .Select(static artifact => NormalizeBootstrapToken(artifact.Head)?.ToLowerInvariant() switch
                {
                    "avalonia" => "Avalonia",
                    "blazor-desktop" => "Blazor Desktop",
                    _ => string.IsNullOrWhiteSpace(artifact.Head) ? "Desktop" : artifact.Head
                })
                .Distinct(StringComparer.OrdinalIgnoreCase));

        string arches = string.Join(
            " + ",
            artifacts
                .Select(static artifact => NormalizeBootstrapToken(artifact.Arch)?.ToLowerInvariant() switch
                {
                    "arm64" => "Apple Silicon",
                    "x64" => "Intel",
                    _ => string.IsNullOrWhiteSpace(artifact.Arch) ? "Mac" : artifact.Arch
                })
                .Distinct(StringComparer.OrdinalIgnoreCase));

        return string.IsNullOrWhiteSpace(arches)
            ? $"macOS desktop setup handoff, {heads}"
            : $"macOS desktop setup handoff, {heads}, {arches}";
    }

    private static string BuildLinuxBootstrapCurrentReleaseSummary(IReadOnlyList<PublicReleaseArtifactDto> artifacts)
    {
        if (artifacts.Count == 0)
        {
            return "Linux desktop setup handoff";
        }

        string heads = string.Join(
            " + ",
            artifacts
                .Select(static artifact => NormalizeBootstrapToken(artifact.Head)?.ToLowerInvariant() switch
                {
                    "avalonia" => "Avalonia",
                    "blazor-desktop" => "Blazor Desktop",
                    _ => string.IsNullOrWhiteSpace(artifact.Head) ? "Desktop" : artifact.Head
                })
                .Distinct(StringComparer.OrdinalIgnoreCase));

        string arches = string.Join(
            " + ",
            artifacts
                .Select(static artifact => NormalizeBootstrapToken(artifact.Arch)?.ToLowerInvariant() switch
                {
                    "arm64" => "ARM64",
                    "x64" => "x64",
                    _ => string.IsNullOrWhiteSpace(artifact.Arch) ? "Linux" : artifact.Arch
                })
                .Distinct(StringComparer.OrdinalIgnoreCase));

        return string.IsNullOrWhiteSpace(arches)
            ? $"Linux desktop setup handoff, {heads}"
            : $"Linux desktop setup handoff, {heads}, {arches}";
    }

    private static string ResolveGuidedBootstrapInstallFolderName(PublicReleaseArtifactDto artifact)
        => artifact.Id.EndsWith("-installer", StringComparison.OrdinalIgnoreCase)
            ? artifact.Id[..^"-installer".Length]
            : artifact.Id;

    private static string ResolveGuidedBootstrapExecutableName(PublicReleaseArtifactDto artifact)
        => NormalizeBootstrapToken(artifact.Head)?.ToLowerInvariant() switch
        {
            "blazor-desktop" => "Chummer.Blazor.Desktop",
            _ => "Chummer.Avalonia"
        };

    private static string ResolveGuidedBootstrapLauncherName(PublicReleaseArtifactDto artifact)
        => NormalizeBootstrapToken(artifact.Head)?.ToLowerInvariant() switch
        {
            "blazor-desktop" => "chummer6-blazor-desktop",
            _ => "chummer6-avalonia"
        };

    private static string ResolveGuidedBootstrapDesktopEntryName(PublicReleaseArtifactDto artifact)
        => $"{ResolveGuidedBootstrapLauncherName(artifact)}.desktop";

    private static string BuildGuidedBootstrapArtifactTitle(PublicReleaseArtifactDto artifact)
        => ResolveGuidedBootstrapPlatform(artifact) switch
        {
            "linux" => BuildLinuxBootstrapArtifactTitle(artifact),
            _ => BuildMacBootstrapArtifactTitle(artifact)
        };

    private static string BuildGuidedBootstrapShortLabel(PublicReleaseArtifactDto artifact)
        => ResolveGuidedBootstrapPlatform(artifact) switch
        {
            "linux" => BuildLinuxBootstrapShortLabel(artifact),
            _ => BuildMacBootstrapShortLabel(artifact)
        };

    private static string BuildMacBootstrapArtifactTitle(PublicReleaseArtifactDto artifact)
    {
        string headLabel = NormalizeBootstrapToken(artifact.Head)?.ToLowerInvariant() switch
        {
            "avalonia" => "Avalonia Desktop",
            "blazor-desktop" => "Blazor Desktop",
            _ => string.IsNullOrWhiteSpace(artifact.Head) ? "Desktop" : artifact.Head!
        };

        string archLabel = NormalizeBootstrapToken(artifact.Arch)?.ToLowerInvariant() switch
        {
            "arm64" => "Apple Silicon",
            "x64" => "Intel",
            _ => "Mac"
        };

        return $"{headLabel} macOS {archLabel} Installer";
    }

    private static string BuildMacBootstrapShortLabel(PublicReleaseArtifactDto artifact)
    {
        string suffix = NormalizeBootstrapToken(artifact.Arch)?.ToLowerInvariant() switch
        {
            "arm64" => " (Apple Silicon)",
            "x64" => " (Intel)",
            _ => string.Empty
        };

        return NormalizeBootstrapToken(artifact.Head)?.ToLowerInvariant() switch
        {
            "avalonia" => $"Chummer Avalonia{suffix}",
            "blazor-desktop" => $"Chummer Blazor Desktop{suffix}",
            _ => string.IsNullOrWhiteSpace(artifact.Platform) ? artifact.Id : $"{artifact.Platform}{suffix}"
        };
    }

    private static string BuildLinuxBootstrapArtifactTitle(PublicReleaseArtifactDto artifact)
    {
        string headLabel = NormalizeBootstrapToken(artifact.Head)?.ToLowerInvariant() switch
        {
            "avalonia" => "Avalonia Desktop",
            "blazor-desktop" => "Blazor Desktop",
            _ => string.IsNullOrWhiteSpace(artifact.Head) ? "Desktop" : artifact.Head!
        };

        string archLabel = NormalizeBootstrapToken(artifact.Arch)?.ToLowerInvariant() switch
        {
            "arm64" => "ARM64",
            "x64" => "x64",
            _ => "Linux"
        };

        return $"{headLabel} Linux {archLabel} Installer";
    }

    private static string BuildLinuxBootstrapShortLabel(PublicReleaseArtifactDto artifact)
    {
        string suffix = NormalizeBootstrapToken(artifact.Arch)?.ToLowerInvariant() switch
        {
            "arm64" => " (ARM64)",
            "x64" => " (x64)",
            _ => string.Empty
        };

        return NormalizeBootstrapToken(artifact.Head)?.ToLowerInvariant() switch
        {
            "avalonia" => $"Chummer Avalonia{suffix}",
            "blazor-desktop" => $"Chummer Blazor Desktop{suffix}",
            _ => string.IsNullOrWhiteSpace(artifact.Platform) ? artifact.Id : $"{artifact.Platform}{suffix}"
        };
    }

    internal static string RenderLinuxInstallBootstrapScript(
        IReadOnlyList<GuidedBootstrapArtifact> artifacts,
        string publicBaseUrl,
        string accountUrl,
        string downloadsUrl,
        string helpUrl)
    {
        ArgumentNullException.ThrowIfNull(artifacts);
        if (artifacts.Count == 0)
        {
            throw new ArgumentException("at least one Linux bootstrap artifact is required.", nameof(artifacts));
        }

        StringBuilder artifactBlock = new();
        foreach (GuidedBootstrapArtifact artifact in artifacts)
        {
            artifactBlock.Append("ARTIFACT_IDS+=(").Append(SingleQuoteShellValue(artifact.ArtifactId)).AppendLine(")");
            artifactBlock.Append("HEAD_IDS+=(").Append(SingleQuoteShellValue(artifact.HeadId)).AppendLine(")");
            artifactBlock.Append("ARTIFACT_TITLES+=(").Append(SingleQuoteShellValue(artifact.Title)).AppendLine(")");
            artifactBlock.Append("SHORT_LABELS+=(").Append(SingleQuoteShellValue(artifact.ShortLabel)).AppendLine(")");
            artifactBlock.Append("DOWNLOAD_URLS+=(").Append(SingleQuoteShellValue(artifact.DownloadUrl)).AppendLine(")");
            artifactBlock.Append("CLAIM_URLS+=(").Append(SingleQuoteShellValue(artifact.ClaimUrl)).AppendLine(")");
            artifactBlock.Append("SHA256_DIGESTS+=(").Append(SingleQuoteShellValue(artifact.Sha256 ?? string.Empty)).AppendLine(")");
            artifactBlock.Append("PACKAGE_NAMES+=(").Append(SingleQuoteShellValue(artifact.PackageName)).AppendLine(")");
            artifactBlock.Append("ARTIFACT_ARCHES+=(").Append(SingleQuoteShellValue(artifact.Architecture ?? string.Empty)).AppendLine(")");
            artifactBlock.Append("LAUNCH_AFTER_INSTALL+=(").Append(artifact.LaunchAfterInstall ? "1" : "0").AppendLine(")");
            artifactBlock.Append("INSTALL_FOLDERS+=(").Append(SingleQuoteShellValue(artifact.InstallFolderName)).AppendLine(")");
            artifactBlock.Append("EXECUTABLE_NAMES+=(").Append(SingleQuoteShellValue(artifact.ExecutableName)).AppendLine(")");
            artifactBlock.Append("WRAPPER_NAMES+=(").Append(SingleQuoteShellValue(artifact.LauncherName)).AppendLine(")");
            artifactBlock.Append("DESKTOP_ENTRY_NAMES+=(").Append(SingleQuoteShellValue(artifact.DesktopEntryName)).AppendLine(")");
        }

        string template = """
#!/usr/bin/env bash
set -euo pipefail

PUBLIC_BASE_URL='__PUBLIC_BASE_URL__'
ACCOUNT_URL='__ACCOUNT_URL__'
DOWNLOADS_URL='__DOWNLOADS_URL__'
HELP_URL='__HELP_URL__'

ARTIFACT_IDS=()
HEAD_IDS=()
ARTIFACT_TITLES=()
SHORT_LABELS=()
DOWNLOAD_URLS=()
CLAIM_URLS=()
SHA256_DIGESTS=()
PACKAGE_NAMES=()
ARTIFACT_ARCHES=()
LAUNCH_AFTER_INSTALL=()
INSTALL_FOLDERS=()
EXECUTABLE_NAMES=()
WRAPPER_NAMES=()
DESKTOP_ENTRY_NAMES=()
__ARTIFACT_BLOCK__

progress_step=0
progress_total=6
GUI_ENABLED=0
if command -v zenity >/dev/null 2>&1; then
  GUI_ENABLED=1
fi

print_banner() {
  echo "============================================================"
  echo " Chummer Setup"
  echo " Guided Linux install for the current desktop preview"
  echo "============================================================"
  echo
}

render_progress_bar() {
  local percent="$1"
  local filled=$(( percent / 4 ))
  local empty=$(( 25 - filled ))
  printf "["
  if (( filled > 0 )); then
    printf '%*s' "$filled" '' | tr ' ' '#'
  fi
  if (( empty > 0 )); then
    printf '%*s' "$empty" '' | tr ' ' '.'
  fi
  printf "]"
}

advance_progress() {
  progress_step=$((progress_step + 1))
  local message="$1"
  local percent=$(( progress_step * 100 / progress_total ))
  echo
  render_progress_bar "$percent"
  echo " ${progress_step}/${progress_total} ${message}"
}

detect_host_arch() {
  local machine
  machine="$(uname -m | tr '[:upper:]' '[:lower:]')"
  case "$machine" in
    arm64|aarch64) echo "arm64" ;;
    *) echo "x64" ;;
  esac
}

host_arch_label() {
  case "${1:-}" in
    arm64) echo "ARM64" ;;
    *) echo "x64" ;;
  esac
}

default_selected_indexes() {
  local host_arch="$1"
  local matches=()
  local idx
  for idx in "${!ARTIFACT_IDS[@]}"; do
    if [[ "${ARTIFACT_ARCHES[$idx]}" == "$host_arch" ]]; then
      matches+=("$idx")
    fi
  done

  if [[ "${#matches[@]}" -gt 0 ]]; then
    printf '%s\n' "${matches[@]}"
    return
  fi

  for idx in "${!ARTIFACT_IDS[@]}"; do
    printf '%s\n' "$idx"
  done
}

read_console_choice() {
  local prompt="$1"
  shift
  local default_index="$1"
  shift
  local choices=("$@")
  echo "$prompt"
  local idx=0
  for choice in "${choices[@]}"; do
    local marker=" "
    if [[ "$idx" == "$default_index" ]]; then
      marker="*"
    fi
    printf '  [%d] %s %s\n' "$((idx + 1))" "$marker" "$choice"
    idx=$((idx + 1))
  done
  while true; do
    read -r -p "Choose 1-${#choices[@]} (blank = $((default_index + 1))): " answer
    if [[ -z "${answer:-}" ]]; then
      printf '%s\n' "${choices[$default_index]}"
      return
    fi
    if [[ "$answer" =~ ^[0-9]+$ ]] && (( answer >= 1 && answer <= ${#choices[@]} )); then
      printf '%s\n' "${choices[$((answer - 1))]}"
      return
    fi
  done
}

choose_mode() {
  local host_arch="$1"
  local default_summary="$2"
  local prompt="Auto select the matching $(host_arch_label "$host_arch") builds for this machine, or choose manually?"
  prompt+=$'\n\n'"Auto select:"$'\n'"$default_summary"
  if [[ "$GUI_ENABLED" == "1" ]]; then
    local choice
    choice="$(zenity --list --title='Chummer Setup' --text="$prompt" --radiolist --column='' --column='Mode' TRUE 'Auto select' FALSE 'Choose manually' --height=240 --width=520 2>/dev/null || true)"
    if [[ -n "${choice:-}" ]]; then
      printf '%s\n' "$choice"
      return
    fi
  fi
  read_console_choice "$prompt" 0 "Auto select" "Choose manually"
}

choose_manual_indexes() {
  local host_arch="$1"
  local defaults=()
  mapfile -t defaults < <(default_selected_indexes "$host_arch")
  if [[ "$GUI_ENABLED" == "1" ]]; then
    local args=()
    local idx
    for idx in "${!ARTIFACT_IDS[@]}"; do
      local is_default="FALSE"
      local default_idx
      for default_idx in "${defaults[@]}"; do
        if [[ "$default_idx" == "$idx" ]]; then
          is_default="TRUE"
          break
        fi
      done
      args+=("$is_default" "$idx" "${SHORT_LABELS[$idx]}")
    done
    local output
    output="$(zenity --list --title='Chummer Setup' --text='Choose which Chummer desktop apps to install now.' --checklist --column='' --column='Index' --column='App' "${args[@]}" --separator='|' --height=320 --width=640 2>/dev/null || true)"
    if [[ -n "${output:-}" ]]; then
      tr '|' '\n' <<<"$output"
      return
    fi
  fi
  echo "Choose which Chummer desktop apps to install now."
  local idx
  for idx in "${!ARTIFACT_IDS[@]}"; do
    local marker=" "
    local default_idx
    for default_idx in "${defaults[@]}"; do
      if [[ "$default_idx" == "$idx" ]]; then
        marker="*"
        break
      fi
    done
    printf '  [%d] %s %s\n' "$((idx + 1))" "$marker" "${SHORT_LABELS[$idx]}"
  done
  read -r -p "Enter comma-separated numbers (blank keeps Auto select defaults): " answer
  if [[ -z "${answer:-}" ]]; then
    printf '%s\n' "${defaults[@]}"
    return
  fi
  tr ',' '\n' <<<"$answer" | while read -r token; do
    token="$(echo "$token" | xargs)"
    if [[ "$token" =~ ^[0-9]+$ ]] && (( token >= 1 && token <= ${#ARTIFACT_IDS[@]} )); then
      echo "$((token - 1))"
    fi
  done | awk '!seen[$0]++'
}

choose_install_scope() {
  local default_root="${HOME}/.local/opt/chummer6"
  if [[ "$GUI_ENABLED" == "1" ]]; then
    local choice
    choice="$(zenity --list --title='Chummer Setup' --text="Choose where to install the selected apps." --radiolist --column='' --column='Location' TRUE "User-local (${default_root})" FALSE 'System root (/opt/chummer6)' --height=220 --width=520 2>/dev/null || true)"
    case "$choice" in
      *"/opt/chummer6"*) echo "system:/opt/chummer6" ; return ;;
      *"${default_root}"*) echo "user:${default_root}" ; return ;;
    esac
  fi
  local choice
  choice="$(read_console_choice "Choose where to install the selected apps." 0 "User-local (${default_root})" "System root (/opt/chummer6)")"
  case "$choice" in
    *"/opt/chummer6"*) echo "system:/opt/chummer6" ;;
    *) echo "user:${default_root}" ;;
  esac
}

choose_shortcut_mode() {
  if [[ "$GUI_ENABLED" == "1" ]]; then
    local choice
    choice="$(zenity --list --title='Chummer Setup' --text='Where should Chummer leave quick access after setup?' --radiolist --column='' --column='Links' TRUE 'Applications menu only' FALSE 'Desktop links' FALSE 'Both' --height=220 --width=520 2>/dev/null || true)"
    case "$choice" in
      'Desktop links') echo "desktop" ; return ;;
      'Both') echo "both" ; return ;;
      'Applications menu only') echo "menu" ; return ;;
    esac
  fi
  local choice
  choice="$(read_console_choice 'Where should Chummer leave quick access after setup?' 0 'Applications menu only' 'Desktop links' 'Both')"
  case "$choice" in
    'Desktop links') echo "desktop" ;;
    'Both') echo "both" ;;
    *) echo "menu" ;;
  esac
}

choose_open_after_install() {
  if [[ "$GUI_ENABLED" == "1" ]]; then
    if zenity --question --title='Chummer Setup' --text='After Chummer finishes installing, should it open the selected app when setup is done?' --ok-label='Open when done' --cancel-label='Finish closed' 2>/dev/null; then
      echo "1"
      return
    fi
  fi
  local choice
  choice="$(read_console_choice 'After Chummer finishes installing, should it open the selected app when setup is done?' 0 'Open when done' 'Finish closed')"
  if [[ "$choice" == 'Open when done' ]]; then
    echo "1"
  else
    echo "0"
  fi
}

verify_download_digest() {
  local downloaded_path="$1"
  local expected_sha="$2"
  if [[ -z "${expected_sha:-}" ]]; then
    return 0
  fi
  local actual_sha
  if command -v sha256sum >/dev/null 2>&1; then
    actual_sha="$(sha256sum "$downloaded_path" | awk '{print tolower($1)}')"
  else
    actual_sha="$(shasum -a 256 "$downloaded_path" | awk '{print tolower($1)}')"
  fi
  if [[ "$actual_sha" != "$(echo "$expected_sha" | tr '[:upper:]' '[:lower:]')" ]]; then
    echo "SHA-256 mismatch for $downloaded_path" >&2
    exit 1
  fi
}

run_privileged_script() {
  local script_path="$1"
  shift
  chmod 700 "$script_path"
  if command -v sudo >/dev/null 2>&1; then
    sudo "$script_path" "$@"
  else
    echo "sudo is required for a system-wide Linux install root." >&2
    exit 1
  fi
}

write_wrapper_script() {
  local wrapper_path="$1"
  local target_binary="$2"
  mkdir -p "$(dirname "$wrapper_path")"
  cat >"$wrapper_path" <<SCRIPT
#!/usr/bin/env bash
exec "$target_binary" "\$@"
SCRIPT
  chmod 755 "$wrapper_path"
}

write_desktop_entry() {
  local desktop_path="$1"
  local app_name="$2"
  local exec_path="$3"
  local icon_path="${4:-}"
  mkdir -p "$(dirname "$desktop_path")"
  cat >"$desktop_path" <<ENTRY
[Desktop Entry]
Type=Application
Name=$app_name
Exec=$exec_path
$( [[ -n "$icon_path" ]] && printf 'Icon=%s\n' "$icon_path" )
Terminal=false
Categories=Game;
ENTRY
  chmod 755 "$desktop_path"
}

create_desktop_link() {
  local desktop_entry_path="$1"
  local short_label="$2"
  mkdir -p "${HOME}/Desktop"
  cp "$desktop_entry_path" "${HOME}/Desktop/${short_label}.desktop"
  chmod 755 "${HOME}/Desktop/${short_label}.desktop"
  echo "Desktop link created: ${HOME}/Desktop/${short_label}.desktop"
}

read_install_state_field() {
  local state_path="$1"
  local field_name="$2"
  python3 - "$state_path" "$field_name" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
field = sys.argv[2]
if not path.is_file():
    sys.exit(0)

try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    sys.exit(0)

value = data.get(field)
if value is None:
    sys.exit(0)

print(str(value))
PY
}

wait_for_claim_success() {
  local state_path="$1"
  local timeout_seconds="$2"
  local attempt=0
  while (( attempt < timeout_seconds )); do
    local status grant claimed_at
    status="$(read_install_state_field "$state_path" status)"
    grant="$(read_install_state_field "$state_path" grantToken)"
    claimed_at="$(read_install_state_field "$state_path" claimedAtUtc)"
    if [[ "$status" == "claimed" && -n "$grant" && -n "$claimed_at" ]]; then
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done
  return 1
}

fetch_install_claim_code() {
  local claim_url="$1"
  python3 - "$claim_url" <<'PY'
import json
import sys
import urllib.error
import urllib.request

url = sys.argv[1]
request = urllib.request.Request(url, headers={"User-Agent": "ChummerSetup/1.0"})
with urllib.request.urlopen(request, timeout=30) as response:
    payload = json.load(response)
claim_code = str(payload.get("claimCode") or "").strip()
if not claim_code:
    raise SystemExit(1)
print(claim_code)
PY
}

resolve_install_state_root() {
  if [[ -n "${XDG_DATA_HOME:-}" ]]; then
    printf '%s\n' "$XDG_DATA_HOME"
  else
    printf '%s\n' "${HOME}/.local/share"
  fi
}

build_install_state_path() {
  local head_id="$1"
  local artifact_arch="$2"
  printf '%s/install-linking/%s/linux/%s/state.json\n' "$(resolve_install_state_root)/Chummer6" "$head_id" "$artifact_arch"
}

build_pending_claim_code_path() {
  local head_id="$1"
  local artifact_arch="$2"
  printf '%s/install-linking/%s/linux/%s/pending-claim-code.txt\n' "$(resolve_install_state_root)/Chummer6" "$head_id" "$artifact_arch"
}

persist_pending_claim_code() {
  local head_id="$1"
  local artifact_arch="$2"
  local claim_code="$3"
  local pending_path
  pending_path="$(build_pending_claim_code_path "$head_id" "$artifact_arch")"
  mkdir -p "$(dirname "$pending_path")"
  printf '%s\n' "$claim_code" >"$pending_path"
}

install_artifact() {
  local idx="$1"
  local download_root="$2"
  local install_root="$3"
  local install_mode="$4"
  local shortcut_mode="$5"
  local artifact_title="${ARTIFACT_TITLES[$idx]}"
  local package_name="${PACKAGE_NAMES[$idx]}"
  local install_folder="${INSTALL_FOLDERS[$idx]}"
  local executable_name="${EXECUTABLE_NAMES[$idx]}"
  local launcher_name="${WRAPPER_NAMES[$idx]}"
  local desktop_entry_name="${DESKTOP_ENTRY_NAMES[$idx]}"
  local download_path="${download_root}/${package_name}"
  local staging_root="${download_root}/extract-${idx}"
  local extracted_root="${staging_root}/opt/chummer6/${install_folder}"
  local target_dir="${install_root}/${install_folder}"
  local icon_target="${target_dir}/chummer-icon.png"
  local launcher_target
  local desktop_entry_target

  advance_progress "Downloading ${artifact_title}"
  echo "Downloading ${artifact_title} to ${download_path}"
  curl -fsSL "${DOWNLOAD_URLS[$idx]}" -o "$download_path"
  verify_download_digest "$download_path" "${SHA256_DIGESTS[$idx]}"

  advance_progress "Installing ${artifact_title}"
  rm -rf "$staging_root"
  mkdir -p "$staging_root"
  dpkg-deb -x "$download_path" "$staging_root"
  if [[ ! -d "$extracted_root" ]]; then
    echo "Expected package root not found for ${artifact_title}: $extracted_root" >&2
    exit 1
  fi

  if [[ "$install_mode" == "system" && ! -w "$install_root" ]]; then
    local privileged_script="${download_root}/install-${idx}.sh"
    cat >"$privileged_script" <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
source_dir="$1"
target_dir="$2"
mkdir -p "$(dirname "$target_dir")"
rm -rf "$target_dir"
cp -a "$source_dir" "$target_dir"
SCRIPT
    run_privileged_script "$privileged_script" "$extracted_root" "$target_dir"
  else
    mkdir -p "$(dirname "$target_dir")"
    rm -rf "$target_dir"
    cp -a "$extracted_root" "$target_dir"
  fi

  if [[ "$install_mode" == "system" ]]; then
    launcher_target="/usr/local/bin/${launcher_name}"
    desktop_entry_target="/usr/local/share/applications/${desktop_entry_name}"
  else
    launcher_target="${HOME}/.local/bin/${launcher_name}"
    desktop_entry_target="${HOME}/.local/share/applications/${desktop_entry_name}"
  fi

  if [[ "$install_mode" == "system" && ( ! -w /usr/local/bin || ! -w /usr/local/share/applications ) ]]; then
    local shortcuts_script="${download_root}/shortcuts-${idx}.sh"
    cat >"$shortcuts_script" <<SCRIPT
#!/usr/bin/env bash
set -euo pipefail
mkdir -p /usr/local/bin
mkdir -p /usr/local/share/applications
cat >"${launcher_target}" <<WRAP
#!/usr/bin/env bash
exec "${target_dir}/${executable_name}" "\$@"
WRAP
chmod 755 "${launcher_target}"
cat >"${desktop_entry_target}" <<ENTRY
[Desktop Entry]
Type=Application
Name=${SHORT_LABELS[$idx]}
Exec=${launcher_target}
Icon=${icon_target}
Terminal=false
Categories=Game;
ENTRY
chmod 755 "${desktop_entry_target}"
SCRIPT
    run_privileged_script "$shortcuts_script"
  else
    write_wrapper_script "$launcher_target" "${target_dir}/${executable_name}"
    write_desktop_entry "$desktop_entry_target" "${SHORT_LABELS[$idx]}" "$launcher_target" "$icon_target"
  fi

  if [[ "$shortcut_mode" == "desktop" || "$shortcut_mode" == "both" ]]; then
    create_desktop_link "$desktop_entry_target" "${SHORT_LABELS[$idx]}"
  fi

  INSTALLED_PATHS+=("${target_dir}")
  INSTALLED_ARTIFACT_INDEXES+=("$idx")
  local claim_code
  local claim_url="${CLAIM_URLS[$idx]}"
  local head_id="${HEAD_IDS[$idx]}"
  local artifact_arch="${ARTIFACT_ARCHES[$idx]}"
  claim_code="$(fetch_install_claim_code "$claim_url")" || {
    INSTALL_WARNINGS+=("${artifact_title} could not fetch a short-lived setup ticket for account linking. Setup will continue, but Devices and access may stay guest-only until you rerun the guided installer.")
    return 0
  }
  persist_pending_claim_code "$head_id" "$artifact_arch" "$claim_code"
  LINKED_CONFIRMED_COUNT=$((LINKED_CONFIRMED_COUNT + 1))
  echo "${artifact_title} is staged to finish account linking on first open."
}

launch_installed_app() {
  local installed_idx="$1"
  local artifact_idx="${INSTALLED_ARTIFACT_INDEXES[$installed_idx]}"
  local target_dir="${INSTALLED_PATHS[$installed_idx]}"
  local executable_path="${target_dir}/${EXECUTABLE_NAMES[$artifact_idx]}"
  local artifact_title="${ARTIFACT_TITLES[$artifact_idx]}"
  if [[ "$OPEN_SELECTED_AFTER_INSTALL" == "1" && "${LAUNCH_AFTER_INSTALL[$artifact_idx]}" == "1" ]]; then
    advance_progress "Opening ${artifact_title}"
    echo "Opening ${artifact_title}..."
    "$executable_path" >/dev/null 2>&1 &
  fi
}

print_banner
advance_progress "Preparing the guided Linux install"
HOST_ARCH="$(detect_host_arch)"
mapfile -t DEFAULT_SELECTED_INDEXES < <(default_selected_indexes "$HOST_ARCH")
DEFAULT_SUMMARY=""
for idx in "${DEFAULT_SELECTED_INDEXES[@]}"; do
  DEFAULT_SUMMARY+="${SHORT_LABELS[$idx]}"$'\n'
done
SELECTION_MODE="$(choose_mode "$HOST_ARCH" "$DEFAULT_SUMMARY")"
if [[ "$SELECTION_MODE" == "Auto select" ]]; then
  SELECTED_INDEXES=("${DEFAULT_SELECTED_INDEXES[@]}")
else
  mapfile -t SELECTED_INDEXES < <(choose_manual_indexes "$HOST_ARCH")
fi

if [[ "${#SELECTED_INDEXES[@]}" -eq 0 ]]; then
  echo "Choose at least one Chummer app." >&2
  exit 1
fi

INSTALL_SCOPE="$(choose_install_scope)"
INSTALL_MODE="${INSTALL_SCOPE%%:*}"
INSTALL_ROOT="${INSTALL_SCOPE#*:}"
SHORTCUT_MODE="$(choose_shortcut_mode)"
OPEN_SELECTED_AFTER_INSTALL="$(choose_open_after_install)"

echo "Selected apps:"
for idx in "${SELECTED_INDEXES[@]}"; do
  echo " - ${SHORT_LABELS[$idx]}"
done
echo "Install destination: ${INSTALL_ROOT}"
echo "Current Linux architecture: $(host_arch_label "$HOST_ARCH")"
case "$SHORTCUT_MODE" in
  desktop) echo "Quick access: Desktop links" ;;
  both) echo "Quick access: Applications menu + Desktop links" ;;
  *) echo "Quick access: Applications menu only" ;;
esac
if [[ "$OPEN_SELECTED_AFTER_INSTALL" == "1" ]]; then
  echo "Finish behavior: open the selected apps when installation completes"
else
  echo "Finish behavior: finish without opening the selected apps"
fi

DOWNLOAD_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/chummer-linux-setup.XXXXXX")"
INSTALLED_PATHS=()
INSTALLED_ARTIFACT_INDEXES=()
INSTALL_WARNINGS=()
LINKED_CONFIRMED_COUNT=0

for idx in "${SELECTED_INDEXES[@]}"; do
  install_artifact "$idx" "$DOWNLOAD_ROOT" "$INSTALL_ROOT" "$INSTALL_MODE" "$SHORTCUT_MODE"
done

echo
echo "Installed Linux desktop builds:"
for target_dir in "${INSTALLED_PATHS[@]}"; do
  echo " - ${target_dir}"
done
if [[ "$OPEN_SELECTED_AFTER_INSTALL" == "1" ]]; then
  echo "Opening the selected Linux desktop builds..."
fi
for install_idx in "${!INSTALLED_PATHS[@]}"; do
  launch_installed_app "$install_idx"
done

advance_progress "Finishing Chummer Setup"
echo
echo "Confirmed linked installs: ${LINKED_CONFIRMED_COUNT} / ${#INSTALLED_PATHS[@]}"
echo "Prepared first-open account linking: ${LINKED_CONFIRMED_COUNT} / ${#INSTALLED_PATHS[@]}"
if [[ "${LINKED_CONFIRMED_COUNT}" -eq "${#INSTALLED_PATHS[@]}" ]]; then
  echo "The selected Chummer app or apps were installed and setup staged account linking for first open."
  echo "When you open them, they should attach to this account without asking you to copy a claim code from the website."
else
  echo "The selected Chummer app or apps were installed, but setup could not pre-stage account linking for every app."
  echo "If Devices and access does not show them after first open, rerun the current guided installer."
fi
if [[ "${#INSTALL_WARNINGS[@]}" -gt 0 ]]; then
  echo
  echo "Setup notes:"
  for warning in "${INSTALL_WARNINGS[@]}"; do
    echo " - ${warning}"
  done
fi
echo "Devices and access: ${ACCOUNT_URL}"
echo "Downloads shelf: ${DOWNLOADS_URL}"
echo "Help: ${HELP_URL}"
""";

        return template
            .Replace("__PUBLIC_BASE_URL__", SingleQuoteShellLiteral(publicBaseUrl), StringComparison.Ordinal)
            .Replace("__ACCOUNT_URL__", SingleQuoteShellLiteral(accountUrl), StringComparison.Ordinal)
            .Replace("__DOWNLOADS_URL__", SingleQuoteShellLiteral(downloadsUrl), StringComparison.Ordinal)
            .Replace("__HELP_URL__", SingleQuoteShellLiteral(helpUrl), StringComparison.Ordinal)
            .Replace("__ARTIFACT_BLOCK__", artifactBlock.ToString().TrimEnd(), StringComparison.Ordinal);
    }

    private static string SingleQuoteShellValue(string value)
        => $"'{SingleQuoteShellLiteral(value)}'";

    private static string SingleQuoteShellLiteral(string value)
        => value.Replace("'", "'\"'\"'", StringComparison.Ordinal);

    private async Task<BlackLedgerHubPageViewModel> BuildBlackLedgerPageModel(
        string currentPath,
        string currentSection,
        int? requestedTurn,
        CancellationToken cancellationToken,
        string? selectedDispatchId = null,
        string? selectedFactionId = null,
        string? selectedRulesetId = null,
        string? selectedMapMode = null)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var authenticated = await TryIsAuthenticatedAsync(cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        var world = _blackLedgerStats.LoadWorldPreview(requestedTurn);
        if (world is not null)
        {
            var createdFactions = _blackLedgerFactions.ListFactionSummaries()
                .Select(summary => _blackLedgerFactions.GetFactionDetail(summary.FactionId))
                .Where(static detail => detail is not null)
                .Select(static detail => new BlackLedgerFactionViewModel(
                    detail!.FactionId,
                    detail.PublicName,
                    detail.Type,
                    detail.FactionLeader,
                    detail.FieldGm,
                    detail.IntelProvider,
                    detail.PublicSignals,
                    detail.ColorPrimary,
                    detail.ColorSecondary,
                    detail.Icon));
            world = world with
            {
                Factions = world.Factions
                    .Concat(createdFactions)
                    .GroupBy(static item => item.Id, StringComparer.OrdinalIgnoreCase)
                    .Select(static group => group.First())
                    .OrderBy(static item => item.PublicName, StringComparer.OrdinalIgnoreCase)
                    .ToArray()
            };
        }
        var dispatches = _blackLedgerDispatches.ListPublishedDispatches(requestedTurn, selectedFactionId);
        var selectedDispatch = string.IsNullOrWhiteSpace(selectedDispatchId)
            ? dispatches.FirstOrDefault()
            : dispatches.FirstOrDefault(item => string.Equals(item.DispatchId, selectedDispatchId, StringComparison.OrdinalIgnoreCase));
        var commandMap = _blackLedgerStats.LoadCommandMap(requestedTurn, selectedMapMode ?? "influence");
        var mapFocused = string.Equals(currentSection, "map", StringComparison.OrdinalIgnoreCase);
        var selectedFaction = string.IsNullOrWhiteSpace(selectedFactionId) || world is null
            ? null
            : world.Factions.FirstOrDefault(faction =>
                string.Equals(faction.Id, selectedFactionId, StringComparison.OrdinalIgnoreCase)
                || string.Equals(faction.Id.Replace('_', '-'), selectedFactionId, StringComparison.OrdinalIgnoreCase));
        var intro = world?.DeterministicPreview == true
            ? "This deterministic turn-two preview shows how AI interim stewards stay bounded, receipt-backed, and subordinate to verified human takeover."
            : "A fictional, public-safe seed world with six factions, visible pressure zones, and bounded dispatches.";
        if (selectedFaction is not null)
        {
            intro = $"Receipt-backed faction page for {selectedFaction.PublicName}. This lane stays public-safe, route-backed, and never publishes private labels or free-floating lore.";
        }
        else if (string.Equals(selectedRulesetId, "anarchy", StringComparison.OrdinalIgnoreCase)
            || string.Equals(selectedRulesetId, AnarchyPreviewService.RulesetId, StringComparison.OrdinalIgnoreCase))
        {
            intro = "This Anarchy lens reads the same public-safe Black Ledger dispatch receipts through a rules-light play profile. It does not invent separate unsupported fiction or flatten Anarchy into an SR5/SR6 toggle.";
        }
        else if (mapFocused)
        {
            intro = "Focused command-map view for the seeded Emerald Sprawl world. District pressure, event arcs, and replay controls stay public-safe, route-backed, and visibly distinct from the broader ledger overview.";
        }

        return new BlackLedgerHubPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync(
                selectedFaction?.PublicName ?? "Black Ledger",
                "Public-safe campaign pressure, package heat, and proof-backed closeout movement.",
                currentPath,
                cancellationToken),
            Eyebrow: mapFocused ? "Black Ledger command map" : selectedFaction is null ? "Black Ledger preview" : "Black Ledger faction file",
            Heading: selectedFaction is not null
                ? $"{selectedFaction.PublicName} faction file"
                : mapFocused
                ? $"{world?.PublicName ?? "Emerald Sprawl: First Pressure"} command map"
                : world?.PublicName ?? "Emerald Sprawl: First Pressure",
            Intro: intro,
            CurrentSection: currentSection,
            World: world,
            SelectedFaction: selectedFaction,
            Stats: _blackLedgerStats.ListPublicStats(requestedTurn),
            Modules: _blackLedgerStats.ListModules(),
            Closeouts: _blackLedgerStats.ListCloseouts(),
            Dispatches: dispatches,
            SelectedDispatch: selectedDispatch,
            CommandMap: commandMap,
            PrimaryAction: mapFocused
                ? new TrustPageActionViewModel("Back to ledger overview", "/ledger", "secondary")
                : new TrustPageActionViewModel("Open command map", "/ledger/map#ledger-map", "primary"),
            SecondaryAction: new TrustPageActionViewModel("Read dispatches", "/ledger/dispatches", "secondary"),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
    }

    private async Task<IActionResult> BuildLedgerFactionWorkspacePage(
        string currentPath,
        string factionId,
        string currentSection,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            BlackLedgerFactionWorkspacePageViewModel? model = await BuildLedgerFactionWorkspacePageModel(currentPath, factionId, currentSection, user, cancellationToken);
            return model is null
                ? NotFound()
                : View("~/Views/PublicLanding/LedgerFactionWorkspace.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
    }

    private async Task<BlackLedgerFactionWorkspacePageViewModel?> BuildLedgerFactionWorkspacePageModel(
        string currentPath,
        string factionId,
        string currentSection,
        HubUserDto user,
        CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated: true);
        var world = _blackLedgerStats.LoadWorldPreview();
        if (world is not null)
        {
            var createdFactions = _blackLedgerFactions.ListFactionSummaries()
                .Select(summary => _blackLedgerFactions.GetFactionDetail(summary.FactionId))
                .Where(static detail => detail is not null)
                .Select(static detail => new BlackLedgerFactionViewModel(
                    detail!.FactionId,
                    detail.PublicName,
                    detail.Type,
                    detail.FactionLeader,
                    detail.FieldGm,
                    detail.IntelProvider,
                    detail.PublicSignals,
                    detail.ColorPrimary,
                    detail.ColorSecondary,
                    detail.Icon));
            world = world with
            {
                Factions = world.Factions
                    .Concat(createdFactions)
                    .GroupBy(static item => item.Id, StringComparer.OrdinalIgnoreCase)
                    .Select(static group => group.First())
                    .OrderBy(static item => item.PublicName, StringComparer.OrdinalIgnoreCase)
                    .ToArray()
            };
        }
        BlackLedgerFactionViewModel? faction = world?.Factions.FirstOrDefault(item =>
            string.Equals(item.Id, factionId, StringComparison.OrdinalIgnoreCase)
            || string.Equals(item.Id.Replace('_', '-'), factionId, StringComparison.OrdinalIgnoreCase));
        if (world is null || faction is null)
        {
            return null;
        }

        string normalizedFactionId = faction.Id.Replace('_', '-');
        var coveredDistricts = world.Districts
            .Where(district => string.Equals(district.DominantFaction.Replace(' ', '-'), normalizedFactionId, StringComparison.OrdinalIgnoreCase))
            .Select(district => district.Name)
            .ToArray();
        var privateLabels = new[]
        {
            $"{faction.PublicName} internal tag",
            $"{faction.PublicName} district pressure lane",
            $"{faction.PublicName} lore overlay alpha",
        };
        var privateLoreNotes = new[]
        {
            "Private labels can exist on authenticated campaign routes only.",
            "Public Black Ledger pages never render these labels or account-linked overlays.",
            "The private-lore API receipt stays non-projecting by contract.",
        };
        var tabs = new[]
        {
            new BlackLedgerFactionWorkspaceTabViewModel("Overview", $"/account/ledger/factions/{normalizedFactionId}", string.Equals(currentSection, "overview", StringComparison.OrdinalIgnoreCase)),
            new BlackLedgerFactionWorkspaceTabViewModel("Manage", $"/account/ledger/factions/{normalizedFactionId}/manage", string.Equals(currentSection, "manage", StringComparison.OrdinalIgnoreCase)),
            new BlackLedgerFactionWorkspaceTabViewModel("Stewards", $"/account/ledger/factions/{normalizedFactionId}/stewards", string.Equals(currentSection, "stewards", StringComparison.OrdinalIgnoreCase)),
            new BlackLedgerFactionWorkspaceTabViewModel("Private lore", $"/account/ledger/factions/{normalizedFactionId}/private-lore", string.Equals(currentSection, "private-lore", StringComparison.OrdinalIgnoreCase)),
        };
        string intro = currentSection switch
        {
            "manage" => "Authenticated faction management posture for route-backed campaign stewardship, bounded package pressure, and district coverage.",
            "stewards" => "Human and AI stewardship posts stay explicit here so public summary roles never get confused with private campaign authority.",
            "private-lore" => "Private lore overlays can exist here for campaign context, but public Ledger routes must never render them.",
            _ => "Authenticated faction workspace for the same Black Ledger seed world, with private labels and management posture kept off public routes.",
        };

        return new BlackLedgerFactionWorkspacePageViewModel(
            Chrome: _chrome.BuildAuthenticatedChrome($"{faction.PublicName} workspace", "Authenticated Black Ledger faction management and private-lore posture.", currentPath, user.DisplayName, user.Email),
            Eyebrow: "Authenticated faction workspace",
            Heading: $"{faction.PublicName} workspace",
            Intro: intro,
            CurrentSection: currentSection,
            World: world,
            Faction: faction,
            CoveredDistricts: coveredDistricts,
            PrivateLabels: privateLabels,
            PrivateLoreNotes: privateLoreNotes,
            Dispatches: _blackLedgerDispatches.ListPublishedDispatches(world.CurrentTurn, faction.Id),
            Tabs: tabs,
            PublicProfileHref: $"/ledger/factions/{normalizedFactionId}",
            PrivacyNote: "Authenticated faction workspaces may render private labels and campaign-scoped overlays. Public Ledger routes never do.",
            Allegiance: _blackLedgerFactions.GetAllegiance(user),
            AvailableActions: string.Equals(currentSection, "manage", StringComparison.OrdinalIgnoreCase) ? _blackLedgerFactions.GetActionDefinitions(faction.Id) : Array.Empty<BlackLedgerFactionActionDefinitionDto>(),
            RecentActionReceipts: _blackLedgerFactions.GetActionReceipts(faction.Id).Take(6).ToArray(),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: _signedInTrustStatus.Build(user, manifest, releaseExperience));
    }

    private async Task<BlackLedgerFactionHomeViewModel> BuildLedgerFactionHomePageModel(HubUserDto user, CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated: true);
        _ = await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken);
        return _blackLedgerFactions.BuildFactionHome(user);
    }

    private async Task<BlackLedgerFactionOnboardingViewModel> BuildLedgerOnboardingPageModel(HubUserDto user, CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated: true);
        _ = await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken);
        return _blackLedgerFactions.BuildOnboardingModel(user);
    }

    private async Task<BlackLedgerFactionCreatePageViewModel> BuildLedgerFactionCreatePageModel(HubUserDto user, CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated: true);
        _ = await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken);
        return _blackLedgerFactions.BuildCreatePage(user);
    }

    private async Task<AnarchyPageViewModel> BuildAnarchyPageModel(
        string currentPath,
        string currentSection,
        string eyebrow,
        string heading,
        string intro,
        TrustPageActionViewModel primaryAction,
        TrustPageActionViewModel secondaryAction,
        CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var authenticated = await TryIsAuthenticatedAsync(cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        return new AnarchyPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync(
                "Shadowrun Anarchy",
                "Rules-light play, Black Ledger consequence, and dispatch-backed mobile continuity.",
                currentPath,
                cancellationToken),
            Eyebrow: eyebrow,
            Heading: heading,
            Intro: intro,
            CurrentSection: currentSection,
            RulesetId: AnarchyPreviewService.RulesetId,
            VerdictLabel: "Playable preview",
            ScopeLabel: "Dedicated ruleset lane",
            FeaturedProfile: _anarchyPreview.LoadFeaturedProfile(),
            LedgerStats: _anarchyPreview.BuildLedgerStats(),
            Dispatches: _anarchyPreview.ListDispatches(),
            ExplainReceipt: _anarchyPreview.BuildExplainReceipt(),
            ExportJson: _anarchyPreview.BuildExportJson(),
            PrimaryAction: primaryAction,
            SecondaryAction: secondaryAction,
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
    }

    private static string BuildReleaseUploadBootstrapCommand(
        string bootstrapUrl,
        string bootstrapSha256,
        string releaseUploadAuthEnvironmentVariable,
        string releaseUploadAuth)
    {
        return "set -euo pipefail; " +
            "TMP_BOOTSTRAP_SCRIPT=\"$(mktemp)\"; " +
            "trap 'rm -f \"$TMP_BOOTSTRAP_SCRIPT\"' EXIT; " +
            "curl -fsSL " + SingleQuoteShellValue(bootstrapUrl) + " > \"$TMP_BOOTSTRAP_SCRIPT\" || { echo 'Failed to fetch bootstrap script; refresh the signed-in handoff page and retry.' >&2; exit 1; }; " +
            "ACTUAL_BOOTSTRAP_SHA256=\"$(python3 -c 'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' \"$TMP_BOOTSTRAP_SCRIPT\")\"; " +
            "[[ \"$ACTUAL_BOOTSTRAP_SHA256\" == " + SingleQuoteShellValue(bootstrapSha256) + " ]] || { echo 'Bootstrap digest mismatch; refresh the signed-in handoff page and retry.' >&2; exit 1; }; " +
            "CHUMMER_RELEASE_CHANNEL='preview' " +
            "CHUMMER_ALLOW_UNSIGNED_PREVIEW='1' " +
            "CHUMMER_ALLOW_REMOTE_RELEASE_PROOF_INPUTS='0' " +
            "CHUMMER_RELEASE_UPLOAD_ALLOW_DIRECT_FALLBACK='0' " +
            "CHUMMER_RELEASE_KEEP_UPLOAD_RESPONSE='0' " +
            "CHUMMER_RELEASE_UPLOAD_MAX_ATTEMPTS='4' " +
            "CHUMMER_BOOTSTRAP_EXPECTED_SHA256=" + SingleQuoteShellValue(bootstrapSha256) + " " +
            releaseUploadAuthEnvironmentVariable + "=" + SingleQuoteShellValue(releaseUploadAuth) + " " +
            "bash \"$TMP_BOOTSTRAP_SCRIPT\"";
    }

    private static string ComputeSha256Hex(string value)
    {
        byte[] bytes = Encoding.UTF8.GetBytes(value);
        return Convert.ToHexStringLower(SHA256.HashData(bytes));
    }

    internal sealed record MacInstallBootstrapArtifact(
        string ArtifactId,
        string HeadId,
        string Title,
        string ShortLabel,
        string DownloadUrl,
        string ClaimCode,
        string? Sha256,
        string DmgName,
        string? Architecture,
        bool LaunchAfterInstall);

    internal sealed record GuidedBootstrapArtifact(
        string ArtifactId,
        string HeadId,
        string Title,
        string ShortLabel,
        string DownloadUrl,
        string ClaimUrl,
        string? Sha256,
        string PackageName,
        string? Architecture,
        bool LaunchAfterInstall,
        string InstallFolderName,
        string ExecutableName,
        string LauncherName,
        string DesktopEntryName);

    private sealed record GuidedBootstrapScriptContext(
        PublicReleaseManifestDto Manifest,
        PublicReleaseArtifactDto Artifact,
        IReadOnlyList<GuidedBootstrapArtifact> Artifacts,
        string BootstrapTicket,
        string? UserId,
        string? SubjectId);

}
