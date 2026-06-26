using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
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
using Chummer.Contracts.Content;
using Chummer.Run.Api.Contracts;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Extensions;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.WebUtilities;
using System.Net.Http.Headers;
using System.Text.RegularExpressions;
using Microsoft.Extensions.DependencyInjection;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/public")]
public sealed class PublicLandingController : Controller
{
    private const string ReleaseUploadTicketEnvironmentVariable = "CHUMMER_RELEASE_UPLOAD_TICKET";
    private const string ReleaseUploadTokenEnvironmentVariable = "CHUMMER_RELEASE_UPLOAD_TOKEN";
    private static readonly JsonSerializerOptions PublicJsonContentOptions = new(JsonSerializerDefaults.Web) { WriteIndented = true };

    private readonly PublicLandingService _landing;
    private readonly FlipLinkDocumentPortalService _flipLinkDocumentPortal;
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
    private readonly RunsiteTourQuotaService _runsiteTourQuota;
    private readonly HorizonArtifactRequestService? _artifactRequests;
    private readonly HorizonArtifactAccessTokenService? _artifactAccessTokens;
    private readonly HorizonCapabilityService _horizonCapabilities;
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
    private readonly BuildGhostConciergeService _buildGhostConcierge;
    private readonly BlackLedgerPublicStatsService _blackLedgerStats;
    private readonly BlackLedgerDispatchService _blackLedgerDispatches;
    private readonly BlackLedgerTickNewsNotificationService _blackLedgerTickNews;
    private readonly BlackLedgerFactionOnboardingService _blackLedgerFactions;
    private readonly BlackLedgerAdvisoryService _blackLedgerAdvisories;
    private readonly BlackLedgerWorldTickBriefingService _blackLedgerBriefings;
    private readonly BeHumanEventAdapterPostureService _beHumanEventAdapterPosture;
    private readonly GmSessionVenueService _gmSessionVenues;
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
    private readonly GoldReadinessArtifactService _goldReadiness;
    private readonly ImportRouteParityProofGuardService _importRouteParityProofGuard;
    private readonly SignedInTrustStatusService _signedInTrustStatus;
    private readonly SupportCaseService _supportCases;
    private readonly SupportCasePresentationService _supportPresentation;
    private readonly IConfiguration _configuration;
    private readonly InstallBootstrapTicketService _installBootstrapTickets;
    private readonly PersonalizedInstallScriptService _personalizedInstallScripts;
    private readonly ReleaseUploadTicketService _releaseUploadTickets;
    private readonly WindowsProofInstallerService _windowsProofInstallers;
    private readonly AurPackageCatalogService _aurPackages;
    private readonly IHttpClientFactory? _httpClientFactory;
    private readonly IWebHostEnvironment _webHostEnvironment;
    private readonly ILogger<PublicLandingController> _logger;

    [ActivatorUtilitiesConstructor]
    public PublicLandingController(
        PublicLandingService landing,
        FlipLinkDocumentPortalService flipLinkDocumentPortal,
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
        RunsiteTourQuotaService runsiteTourQuota,
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
        BuildGhostConciergeService buildGhostConcierge,
        BlackLedgerPublicStatsService blackLedgerStats,
        BlackLedgerDispatchService blackLedgerDispatches,
        BlackLedgerTickNewsNotificationService blackLedgerTickNews,
        BlackLedgerFactionOnboardingService blackLedgerFactions,
        BlackLedgerAdvisoryService blackLedgerAdvisories,
        BlackLedgerWorldTickBriefingService blackLedgerBriefings,
        BeHumanEventAdapterPostureService beHumanEventAdapterPosture,
        GmSessionVenueService gmSessionVenues,
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
        AurPackageCatalogService aurPackages,
        IHttpClientFactory httpClientFactory,
        IWebHostEnvironment webHostEnvironment,
        ILogger<PublicLandingController> logger,
        HorizonArtifactRequestService? artifactRequests = null,
        HorizonCapabilityService? horizonCapabilities = null,
        HorizonArtifactAccessTokenService? artifactAccessTokens = null)
    {
        _landing = landing;
        _flipLinkDocumentPortal = flipLinkDocumentPortal;
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
        _runsiteTourQuota = runsiteTourQuota;
        _artifactRequests = artifactRequests;
        _artifactAccessTokens = artifactAccessTokens;
        _horizonCapabilities = horizonCapabilities ?? new HorizonCapabilityService(configuration);
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
        _buildGhostConcierge = buildGhostConcierge;
        _blackLedgerStats = blackLedgerStats;
        _blackLedgerDispatches = blackLedgerDispatches;
        _blackLedgerTickNews = blackLedgerTickNews;
        _blackLedgerFactions = blackLedgerFactions;
        _blackLedgerAdvisories = blackLedgerAdvisories;
        _blackLedgerBriefings = blackLedgerBriefings;
        _beHumanEventAdapterPosture = beHumanEventAdapterPosture;
        _gmSessionVenues = gmSessionVenues;
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
        _goldReadiness = new GoldReadinessArtifactService(configuration);
        _importRouteParityProofGuard = new ImportRouteParityProofGuardService(configuration);
        _signedInTrustStatus = signedInTrustStatus;
        _supportCases = supportCases;
        _supportPresentation = supportPresentation;
        _configuration = configuration;
        _installBootstrapTickets = installBootstrapTickets;
        _personalizedInstallScripts = personalizedInstallScripts;
        _releaseUploadTickets = releaseUploadTickets;
        _windowsProofInstallers = windowsProofInstallers;
        _aurPackages = aurPackages;
        _httpClientFactory = httpClientFactory;
        _webHostEnvironment = webHostEnvironment;
        _logger = logger;
    }

    public PublicLandingController(
        PublicLandingService landing,
        FlipLinkDocumentPortalService flipLinkDocumentPortal,
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
        RunsiteTourQuotaService runsiteTourQuota,
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
        BuildGhostConciergeService buildGhostConcierge,
        BlackLedgerPublicStatsService blackLedgerStats,
        BlackLedgerDispatchService blackLedgerDispatches,
        BlackLedgerTickNewsNotificationService blackLedgerTickNews,
        BlackLedgerFactionOnboardingService blackLedgerFactions,
        BlackLedgerAdvisoryService blackLedgerAdvisories,
        BlackLedgerWorldTickBriefingService blackLedgerBriefings,
        BeHumanEventAdapterPostureService beHumanEventAdapterPosture,
        GmSessionVenueService gmSessionVenues,
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
        AurPackageCatalogService aurPackages,
        IWebHostEnvironment webHostEnvironment,
        ILogger<PublicLandingController> logger,
        HorizonArtifactRequestService? artifactRequests = null,
        HorizonCapabilityService? horizonCapabilities = null,
        HorizonArtifactAccessTokenService? artifactAccessTokens = null)
        : this(
            landing,
            flipLinkDocumentPortal,
            flagshipCoverage,
            releases,
            campaignOsProof,
            releaseSelection,
            actions,
            accounts,
            identity,
            links,
            experience,
            participationNotifications,
            runsiteTourQuota,
            installLinking,
            campaignSpine,
            workspaceServerPlane,
            readyForTonight,
            knowledgeFabric,
            nexusPan,
            mediaHorizons,
            communityCreatorHorizons,
            waveEightHorizons,
            karmaForge,
            buildGhostConcierge,
            blackLedgerStats,
            blackLedgerDispatches,
            blackLedgerTickNews,
            blackLedgerFactions,
            blackLedgerAdvisories,
            blackLedgerBriefings,
            beHumanEventAdapterPosture,
            gmSessionVenues,
            anarchyPreview,
            packageCatalog,
            publicCreatorDiscovery,
            chrome,
            trustContent,
            privacyBoundaries,
            signalProjection,
            signalOperations,
            trustPulse,
            signedInTrustStatus,
            supportCases,
            supportPresentation,
            configuration,
            installBootstrapTickets,
            personalizedInstallScripts,
            releaseUploadTickets,
            windowsProofInstallers,
            aurPackages,
            httpClientFactory: null!,
            webHostEnvironment,
            logger,
            artifactRequests,
            horizonCapabilities,
            artifactAccessTokens)
    {
    }

    [HttpGet("/")]
    [Produces("text/html")]
    public async Task<IActionResult> LandingPage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        bool hasAuthCookie = Request.Cookies.ContainsKey(HubBrowserAuthConstants.AccessTokenCookieName);
        var authenticated = hasAuthCookie && await TryIsAuthenticatedAsync(cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        var accessPosture = _releaseSelection.BuildPublicAccessPosture(manifest, releaseExperience);
        var assetCatalog = new AssetCatalogViewModel(surface.Assets);
        var nowCards = _landing.CardsForBucket(surface, "whats_real_now");
        var secondaryHeroAction = surface.HeroCtas.FirstOrDefault(static action => string.Equals(action.Emphasis, "secondary", StringComparison.OrdinalIgnoreCase))
            ?? surface.HeroCtas.Skip(1).FirstOrDefault()
            ?? new PublicLandingActionDto("Open current release", "/now", "secondary");
        var primaryHeroAction = surface.HeroCtas.FirstOrDefault(static action => string.Equals(action.Emphasis, "primary", StringComparison.OrdinalIgnoreCase))
            ?? surface.HeroCtas.FirstOrDefault()
            ?? _releaseSelection.BuildPublicPrimaryAction(
                manifest,
                Request.Headers.UserAgent.ToString(),
                authenticated);
        var model = new LandingPageViewModel(
            Chrome: hasAuthCookie
                ? await BuildPublicOrAuthenticatedChromeAsync("Chummer", "Desktop character manager for Shadowrun.", "/", cancellationToken)
                : BuildContextualPublicChrome("Chummer", "Desktop character manager for Shadowrun.", "/"),
            Surface: surface,
            Assets: assetCatalog,
            Manifest: manifest,
            ReleaseExperience: releaseExperience,
            TrustPulse: null,
            SignedInStatus: null,
            PrimaryHeroAction: primaryHeroAction,
            SecondaryHeroAction: secondaryHeroAction,
            Workflows: ResolveCards(_landing.CardsForBucket(surface, "start_here"), assetCatalog, authenticated: false, "/"),
            TrustPillars: _landing.CardsForBucket(surface, "why_trust_it"),
            Lanes: ResolveCards(_landing.CardsForBucket(surface, "choose_your_lane"), assetCatalog, authenticated: false, "/"),
            AvailableToday: ResolveCards(nowCards.Where(static card => PublicSurfaceStatus.IsAvailableToday(card.Badge)).ToArray(), assetCatalog, authenticated: false, "/"),
            PreviewItems: ResolveCards(nowCards.Where(static card => !PublicSurfaceStatus.IsAvailableToday(card.Badge)).ToArray(), assetCatalog, authenticated: false, "/"),
            ComingNext: ResolveCards(_landing.CardsForBucket(surface, "coming_next").Take(3).ToArray(), assetCatalog, authenticated: false, "/"),
            Artifacts: ResolveCards(_landing.CardsForBucket(surface, "featured_artifacts"), assetCatalog, authenticated: false, "/"),
            FlagshipCoverage: new FlagshipCoverageStripViewModel(string.Empty, string.Empty, string.Empty, Array.Empty<FlagshipCoverageCardViewModel>()),
            BlackLedgerStats: Array.Empty<BlackLedgerPublicStatViewModel>(),
            BlackLedgerWorld: null,
            LatestBlackLedgerDispatch: null,
            CampaignSpine: null,
            OpenRail: null,
            AccessPosture: accessPosture);
        return View("~/Views/PublicLanding/Landing.cshtml", model);
    }

    [HttpGet("/what-is-chummer")]
    [Produces("text/html")]
    public async Task<IActionResult> ProductStoryPage(CancellationToken cancellationToken)
    {
        var model = new StoryPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync(
                "What Is Chummer?",
                "Character tools for Shadowrun.",
                "/what-is-chummer",
                cancellationToken));
        return View("~/Views/PublicLanding/ProductStory.cshtml", model);
    }

    [HttpGet("/now")]
    [Produces("text/html")]
    public async Task<IActionResult> NowPage(CancellationToken cancellationToken)
    {
        var model = await BuildNowPageModel(
            title: "What Is Real Now",
            description: "Readiness labels and direct status for what you can use today.",
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
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Maintenance", "Future work stays behind the main app.", "/horizons", cancellationToken),
            Surface: surface,
            Assets: assetCatalog,
            Horizons: ResolveCards(_landing.CardsForBucket(surface, "coming_next"), assetCatalog, authenticated: false, "/horizons"),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
        return View("~/Views/PublicLanding/Horizons.cshtml", model);
    }

    [HttpGet("/downloads")]
    [HttpHead("/downloads")]
    [Produces("text/html")]
    public async Task<IActionResult> DownloadsPage(CancellationToken cancellationToken)
    {
        ApplyNoStoreHeaders(Response.Headers);
        ApplyDownloadClientHintHeaders(Response.Headers);
        var surface = _landing.LoadSurface();
        var rawManifest = _releases.LoadManifest();
        var manifest = _releaseSelection.ApplyAccessPolicy(rawManifest);
        var authenticated = await TryIsAuthenticatedAsync(cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, BuildDownloadSelectionUserAgent(), authenticated);
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
        var chrome = await BuildPublicOrAuthenticatedChromeAsync("Downloads", "Current Chummer installers and platform availability.", "/downloads", cancellationToken);
        chrome = RebindDownloadsHeaderActions(chrome, releaseExperience);
        var accessPosture = _releaseSelection.BuildPublicAccessPosture(manifest, releaseExperience);
        var model = new DownloadsPageViewModel(
            Chrome: chrome,
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            Manifest: manifest,
            ReleaseTruth: BuildReleaseTruthDisplay(manifest),
            ReleaseExperience: releaseExperience,
            FlagshipCoverage: _flagshipCoverage.LoadStrip(),
            SignedInWindowsBuilds: signedInWindowsBuilds,
            WindowsProofInstallers: windowsProofInstallers,
            AurPackages: _aurPackages.LoadCatalog().Packages,
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
            chromeDescription: "Browse current Chummer downloads, rules data, add-ons, and planned package ideas.",
            eyebrow: "Packages",
            heading: "Packages",
            intro: "A quiet overview of what you can install, what belongs to rules data, and what is still only a planned add-on.",
            scopeLabel: "Public overview",
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
                ? new TrustPageActionViewModel("Open mobile", "/mobile", "secondary")
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
                chromeDescription: "Track package follows, votes, and package returns from the same account area as installs and support.",
                eyebrow: "Account packages",
                heading: "Account packages",
                intro: "Votes, follows, and package returns stay attached to the same account area that already owns installs, recovery, and support history.",
                scopeLabel: "Account area",
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
                scopeLabel: "Account area",
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
                chromeTitle: "Package maintenance summary",
                chromeDescription: "Private summary of package classes, compatibility status, and Chummer vote or follow history.",
                eyebrow: "Maintenance summary",
                heading: "Package maintenance summary",
                intro: "The account view keeps public package status, compatibility pressure, and Chummer history together without turning the package browser into a hidden admin-only page.",
                scopeLabel: "Maintenance summary",
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
            _logger.LogWarning(ex, "Package maintenance summary could not confirm the signed-in identity.");
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("/admin/providers/clickrank")]
    [Produces("application/json")]
    public async Task<IActionResult> AdminClickRankProviderDashboard(CancellationToken cancellationToken)
    {
        const string currentPath = "/admin/providers/clickrank";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);

            JsonElement? providerVerification = ReadCompletionArtifact("CLICKRANK_PROVIDER_VERIFICATION.generated.json");
            JsonElement? domainSetup = ReadCompletionArtifact("CLICKRANK_DOMAIN_SETUP.generated.json");
            JsonElement? gscConnection = ReadCompletionArtifact("CLICKRANK_GSC_CONNECTION.generated.json");
            JsonElement? patchPlan = ReadCompletionArtifact("CLICKRANK_METADATA_SCHEMA_PATCH_PLAN.generated.json");
            JsonElement? recommendationExport = ReadCompletionArtifact("CLICKRANK_RECOMMENDATION_EXPORT.generated.json");
            JsonElement? firstPatch = ReadCompletionArtifact("CLICKRANK_FIRST_PATCH_RECEIPT.generated.json");
            JsonElement? baselineCrawl = ReadCompletionArtifact("CLICKRANK_CHUMMER_BASELINE_CRAWL.generated.json");
            JsonElement? recrawl = ReadCompletionArtifact("CLICKRANK_RECRAWL_VERIFICATION.generated.json");
            JsonElement? privateRouteProof = ReadCompletionArtifact("CLICKRANK_NO_PRIVATE_ROUTE_CRAWL_PROOF.generated.json");
            JsonElement? copyrightBoundary = ReadCompletionArtifact("CLICKRANK_SOURCEBOOK_COPYRIGHT_BOUNDARY.generated.json");

            return Json(new
            {
                adapter = "ClickRankVisibilityAdapter",
                currentPath,
                generatedAtUtc = DateTime.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture),
                provider = new
                {
                    status = ReadStatus(providerVerification),
                    verifiedAtUtc = ReadDate(providerVerification, "verified_at_utc") ?? ReadDate(providerVerification, "generated_at_utc"),
                    service = ReadString(providerVerification, "service"),
                    accountEmail = ReadString(providerVerification, "account_email"),
                    plan = ReadString(providerVerification, "plan"),
                    siteIds = ReadStringArray(providerVerification, "site_ids"),
                    autoFixDisabled = ReadBoolean(providerVerification, "auto_fix_disabled_by_default"),
                    failures = ReadStringArray(providerVerification, "failures"),
                    payload = providerVerification
                },
                domain = new
                {
                    status = ReadStatus(domainSetup),
                    siteId = ReadString(domainSetup, "site_id"),
                    domain = ReadString(domainSetup, "domain"),
                    homepageStatus = ReadNumber(domainSetup, "homepage_status_code"),
                    failures = ReadStringArray(domainSetup, "failures"),
                    payload = domainSetup
                },
                gsc = new
                {
                    status = ReadStatus(gscConnection),
                    connected = ReadBoolean(gscConnection, "connected"),
                    documentedUnavailable = ReadBoolean(gscConnection, "documented_unavailable"),
                    failures = ReadStringArray(gscConnection, "failures"),
                    payload = gscConnection
                },
                patchPlan = new
                {
                    status = ReadStatus(patchPlan),
                    readyForPrProposalMode = ReadBoolean(patchPlan, "ready_for_pr_proposal_mode"),
                    autoFixDisabled = ReadBoolean(patchPlan, "auto_fix_disabled"),
                    failures = ReadStringArray(patchPlan, "failures"),
                    payload = patchPlan
                },
                recommendations = new
                {
                    status = ReadStatus(recommendationExport),
                    generatedAtUtc = ReadDate(recommendationExport, "generated_at_utc"),
                    payload = recommendationExport
                },
                releaseReadiness = new
                {
                    firstPatchStatus = ReadStatus(firstPatch),
                    firstPatch = ReadDate(firstPatch, "deployed_at_utc") ?? ReadDate(firstPatch, "generated_at_utc"),
                    baselineStatus = ReadStatus(baselineCrawl),
                    recrawlStatus = ReadStatus(recrawl),
                    privateRoutesOk = IsPass(ReadStatus(privateRouteProof)),
                    copyrightBoundaryOk = IsPass(ReadStatus(copyrightBoundary)),
                    summary = BuildClickRankProviderSummary(providerVerification, domainSetup, gscConnection, baselineCrawl, patchPlan, recommendationExport, firstPatch, recrawl)
                }
            });
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "ClickRank provider dashboard could not confirm the signed-in identity.");
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("/admin/visibility")]
    [Produces("application/json")]
    public async Task<IActionResult> AdminVisibilityDashboard(CancellationToken cancellationToken)
    {
        const string currentPath = "/admin/visibility";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);

            JsonElement? recrawl = ReadCompletionArtifact("CLICKRANK_RECRAWL_VERIFICATION.generated.json");
            JsonElement? baseline = ReadCompletionArtifact("CLICKRANK_CHUMMER_BASELINE_CRAWL.generated.json");
            JsonElement? visibilityReport = ReadCompletionArtifact("CLICKRANK_MONTHLY_VISIBILITY_REPORT.generated.json");
            JsonElement? privateRouteProof = ReadCompletionArtifact("CLICKRANK_NO_PRIVATE_ROUTE_CRAWL_PROOF.generated.json");
            JsonElement? finalVerdict = ReadFinalClickRankVerdict();

            var baselineRoutes = GetRouteVisibilityRows(baseline);

            return Json(new
            {
                surface = "public_visibility_health",
                generatedAtUtc = DateTime.UtcNow.ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture),
                currentPath,
                status = ReadStatus(visibilityReport),
                reportSummary = ReadString(visibilityReport, "summary"),
                recrawl = new
                {
                    status = ReadStatus(recrawl),
                    latest = ReadDate(recrawl, "verified_at_utc") ?? ReadDate(recrawl, "generated_at_utc"),
                    routeCount = ReadInt(recrawl, "route_count"),
                    passingRoutes = ReadInt(recrawl, "passing_routes"),
                    failingRoutes = ReadInt(recrawl, "failing_routes"),
                    payload = recrawl
                },
                baseline = new
                {
                    status = ReadStatus(baseline),
                    crawlDate = ReadDate(baseline, "baseline_crawl", "crawl_date") ?? ReadDate(baseline, "generated_at_utc"),
                    pagesCrawled = ReadInt(baseline, "baseline_crawl", "pages_crawled"),
                    missingCanonical = ReadInt(baseline, "baseline_crawl", "canonical_errors"),
                    missingSchema = ReadInt(baseline, "baseline_crawl", "missing_schema"),
                    noindexPages = ReadInt(baseline, "baseline_crawl", "noindex_pages"),
                    payload = baseline,
                    routes = baselineRoutes
                },
                privateRouteBoundary = new
                {
                    status = ReadStatus(privateRouteProof),
                    failures = ReadStringArray(privateRouteProof, "failures"),
                },
                finalVerdict = new
                {
                    verdict = ReadString(finalVerdict, "verdict"),
                    status = ReadString(finalVerdict, "status"),
                    summary = ReadString(finalVerdict, "summary"),
                    payload = finalVerdict
                },
                operatorSignals = new
                {
                    goldReadiness = BuildGoldReadinessSummary(_goldReadiness.LoadSnapshot()),
                    launchReadinessLabel = BuildLiveVerificationLabel(_releaseSelection.ApplyAccessPolicy(_releases.LoadManifest())),
                    launchReadiness = BuildGoldReadinessStatus(_goldReadiness.LoadSnapshot())?.Summary,
                    trustPulse = _trustPulse.LoadSnapshot()
                },
                recommendations = BuildClickRankRouteRecommendations(recrawl)
            });
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Visibility dashboard could not confirm the signed-in identity.");
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    private static JsonElement? ReadCompletionArtifact(string fileName)
    {
        string? path = ResolveCompletionArtifactPath(fileName);
        if (string.IsNullOrWhiteSpace(path) || !System.IO.File.Exists(path))
        {
            return null;
        }

        try
        {
            using JsonDocument document = JsonDocument.Parse(System.IO.File.ReadAllText(path, Encoding.UTF8));
            return document.RootElement.Clone();
        }
        catch
        {
            return null;
        }
    }

    private static JsonElement? ReadFinalClickRankVerdict()
    {
        JsonElement? generated = ReadCompletionArtifact("FINAL_CLICKRANK_CHUMMER_VISIBILITY_VERDICT.generated.json");
        if (generated is not null)
        {
            return generated;
        }

        string? path = ResolveCompletionArtifactPath("FINAL_CLICKRANK_CHUMMER_VISIBILITY_VERDICT.md");
        if (string.IsNullOrWhiteSpace(path) || !System.IO.File.Exists(path))
        {
            return null;
        }

        string content = System.IO.File.ReadAllText(path, Encoding.UTF8);
        bool ready = content.Contains("CLICKRANK_CHUMMER_VISIBILITY_READY", StringComparison.OrdinalIgnoreCase);
        string summary = ready
            ? "Final ClickRank visibility verdict is present and reports READY."
            : "Final ClickRank visibility verdict is present but does not report READY.";

        return JsonSerializer.SerializeToElement(new
        {
            verdict = ready ? "CLICKRANK_CHUMMER_VISIBILITY_READY" : "NOT_READY",
            status = ready ? "pass" : "blocked",
            summary,
            generated_at_utc = new DateTimeOffset(System.IO.File.GetLastWriteTimeUtc(path)).ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture)
        });
    }

    private static string? ResolveCompletionArtifactPath(string fileName)
    {
        foreach (string candidate in EnumerateCompletionArtifactPaths(fileName))
        {
            if (System.IO.File.Exists(candidate))
            {
                return candidate;
            }
        }

        return null;
    }

    private static IEnumerable<string> EnumerateCompletionArtifactPaths(string fileName)
    {
        string[] roots =
        [
            Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "_completion", "clickrank"),
            Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "fleet", "_completion", "clickrank"),
            Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", ".integrated", "fleet", "_completion", "clickrank"),
            Path.Combine(Directory.GetCurrentDirectory(), "_completion", "clickrank"),
            Path.Combine(Directory.GetCurrentDirectory(), "fleet", "_completion", "clickrank"),
            Path.Combine(Directory.GetCurrentDirectory(), ".integrated", "fleet", "_completion", "clickrank"),
            Path.Combine(AppContext.BaseDirectory, ".codex-studio", "published"),
            Path.Combine(Directory.GetCurrentDirectory(), ".codex-studio", "published")
        ];

        foreach (string root in roots)
        {
            yield return Path.GetFullPath(Path.Combine(root, fileName));
        }
    }

    private static string ReadStatus(JsonElement? artifact)
    {
        if (artifact is null)
        {
            return "missing";
        }

        foreach (string propertyName in new[] { "status", "verdict", "result", "state" })
        {
            string? value = ReadString(artifact, propertyName);
            if (!string.IsNullOrWhiteSpace(value))
            {
                return value;
            }
        }

        return "present";
    }

    private static string? ReadDate(JsonElement? artifact, params string[] propertyPath)
    {
        JsonElement? value = ResolvePath(artifact, propertyPath);
        if (value is null)
        {
            return null;
        }

        if (value.Value.ValueKind == JsonValueKind.String
            && DateTimeOffset.TryParse(value.Value.GetString(), CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out DateTimeOffset parsed))
        {
            return parsed.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture);
        }

        if (value.Value.ValueKind == JsonValueKind.Number && value.Value.TryGetInt64(out long unixSeconds))
        {
            return DateTimeOffset.FromUnixTimeSeconds(unixSeconds).ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture);
        }

        return null;
    }

    private static string? ReadString(JsonElement? artifact, params string[] propertyPath)
    {
        JsonElement? value = ResolvePath(artifact, propertyPath);
        if (value is null)
        {
            return null;
        }

        return value.Value.ValueKind switch
        {
            JsonValueKind.String => value.Value.GetString(),
            JsonValueKind.Number => value.Value.ToString(),
            JsonValueKind.True => bool.TrueString,
            JsonValueKind.False => bool.FalseString,
            _ => null
        };
    }

    private static string[] ReadStringArray(JsonElement? artifact, params string[] propertyPath)
    {
        JsonElement? value = ResolvePath(artifact, propertyPath);
        if (value is null)
        {
            return [];
        }

        if (value.Value.ValueKind == JsonValueKind.Array)
        {
            return value.Value.EnumerateArray()
                .Select(static item => item.ValueKind == JsonValueKind.String ? item.GetString() : item.ToString())
                .Where(static item => !string.IsNullOrWhiteSpace(item))
                .Cast<string>()
                .ToArray();
        }

        string? single = ReadString(artifact, propertyPath);
        return string.IsNullOrWhiteSpace(single) ? [] : [single];
    }

    private static bool ReadBoolean(JsonElement? artifact, params string[] propertyPath)
    {
        JsonElement? value = ResolvePath(artifact, propertyPath);
        if (value is null)
        {
            return false;
        }

        return value.Value.ValueKind switch
        {
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            JsonValueKind.String when bool.TryParse(value.Value.GetString(), out bool parsed) => parsed,
            JsonValueKind.String => string.Equals(value.Value.GetString(), "pass", StringComparison.OrdinalIgnoreCase)
                                    || string.Equals(value.Value.GetString(), "ready", StringComparison.OrdinalIgnoreCase)
                                    || string.Equals(value.Value.GetString(), "verified", StringComparison.OrdinalIgnoreCase),
            JsonValueKind.Number when value.Value.TryGetInt32(out int number) => number != 0,
            _ => false
        };
    }

    private static int ReadInt(JsonElement? artifact, params string[] propertyPath)
    {
        JsonElement? value = ResolvePath(artifact, propertyPath);
        if (value is null)
        {
            return 0;
        }

        if (value.Value.ValueKind == JsonValueKind.Number)
        {
            if (value.Value.TryGetInt32(out int intValue))
            {
                return intValue;
            }

            if (value.Value.TryGetDouble(out double doubleValue))
            {
                return Convert.ToInt32(doubleValue, CultureInfo.InvariantCulture);
            }
        }

        if (value.Value.ValueKind == JsonValueKind.String && int.TryParse(value.Value.GetString(), NumberStyles.Integer, CultureInfo.InvariantCulture, out int parsed))
        {
            return parsed;
        }

        return 0;
    }

    private static double? ReadNumber(JsonElement? artifact, params string[] propertyPath)
    {
        JsonElement? value = ResolvePath(artifact, propertyPath);
        if (value is null)
        {
            return null;
        }

        if (value.Value.ValueKind == JsonValueKind.Number && value.Value.TryGetDouble(out double number))
        {
            return number;
        }

        if (value.Value.ValueKind == JsonValueKind.String && double.TryParse(value.Value.GetString(), NumberStyles.Float, CultureInfo.InvariantCulture, out double parsed))
        {
            return parsed;
        }

        return null;
    }

    private static JsonElement? ResolvePath(JsonElement? artifact, params string[] propertyPath)
    {
        if (artifact is null)
        {
            return null;
        }

        JsonElement current = artifact.Value;
        foreach (string propertyName in propertyPath)
        {
            if (current.ValueKind != JsonValueKind.Object || !current.TryGetProperty(propertyName, out JsonElement next))
            {
                return null;
            }

            current = next;
        }

        return current;
    }

    private static bool IsPass(string? status)
        => !string.IsNullOrWhiteSpace(status)
           && (string.Equals(status, "pass", StringComparison.OrdinalIgnoreCase)
               || string.Equals(status, "passed", StringComparison.OrdinalIgnoreCase)
               || string.Equals(status, "verified", StringComparison.OrdinalIgnoreCase)
               || string.Equals(status, "ready", StringComparison.OrdinalIgnoreCase)
               || string.Equals(status, "healthy", StringComparison.OrdinalIgnoreCase));

    private static string BuildClickRankProviderSummary(
        JsonElement? providerVerification,
        JsonElement? domainSetup,
        JsonElement? gscConnection,
        JsonElement? baselineCrawl,
        JsonElement? patchPlan,
        JsonElement? recommendationExport,
        JsonElement? firstPatch,
        JsonElement? recrawl)
    {
        int passingChecks = new[]
        {
            IsPass(ReadStatus(providerVerification)),
            IsPass(ReadStatus(domainSetup)),
            IsPass(ReadStatus(gscConnection)),
            IsPass(ReadStatus(baselineCrawl)),
            IsPass(ReadStatus(patchPlan)),
            IsPass(ReadStatus(firstPatch)),
            IsPass(ReadStatus(recrawl))
        }.Count(static item => item);

        int recommendationCount = ResolvePath(recommendationExport, "recommendations") is JsonElement recommendations
            && recommendations.ValueKind == JsonValueKind.Array
            ? recommendations.GetArrayLength()
            : 0;

        return $"{passingChecks}/7 ClickRank readiness items are currently passing. Exported recommendation count: {recommendationCount}.";
    }

    private static object[] GetRouteVisibilityRows(JsonElement? baseline)
    {
        JsonElement? routes = ResolvePath(baseline, "baseline_crawl", "routes") ?? ResolvePath(baseline, "routes");
        if (routes is null || routes.Value.ValueKind != JsonValueKind.Array)
        {
            return [];
        }

        return routes.Value.EnumerateArray()
            .Take(12)
            .Select(route => (object)new
            {
                route = ReadString(route, "route") ?? ReadString(route, "path") ?? ReadString(route, "url") ?? "unknown",
                status = ReadString(route, "status") ?? ReadString(route, "result") ?? "present",
                issues = ReadStringArray(route, "issues"),
                title = ReadString(route, "title")
            })
            .ToArray();
    }

    private static object[] BuildClickRankRouteRecommendations(JsonElement? recrawl)
    {
        JsonElement? recommendations = ResolvePath(recrawl, "recommendations") ?? ResolvePath(recrawl, "routes");
        if (recommendations is null || recommendations.Value.ValueKind != JsonValueKind.Array)
        {
            return [];
        }

        return recommendations.Value.EnumerateArray()
            .Take(20)
            .Select(item => (object)new
            {
                route = ReadString(item, "route") ?? ReadString(item, "path") ?? ReadString(item, "url") ?? "unknown",
                status = ReadString(item, "status") ?? ReadString(item, "result") ?? "present",
                severity = ReadString(item, "severity") ?? "info",
                summary = ReadString(item, "summary") ?? ReadString(item, "issue_type") ?? "No summary mirrored."
            })
            .ToArray();
    }

    private static object? BuildGoldReadinessSummary(GoldReadinessSnapshot? snapshot)
    {
        GoldReadinessStatusViewModel? status = BuildGoldReadinessStatus(snapshot);
        if (status is null)
        {
            return null;
        }

        return new
        {
            statusLabel = status.StatusLabel,
            summary = status.Summary,
            generatedAtUtc = status.GeneratedAtLabel,
            blockerCount = status.Blockers.Count
        };
    }

    [HttpGet("/mobile")]
    [Produces("text/html")]
    public async Task<IActionResult> MobileProjectionPage(CancellationToken cancellationToken)
    {
        var model = await BuildMobileProjectionPageModel(
            currentPath: "/mobile",
            chromeTitle: "Mobile and PWA",
            chromeDescription: "Phone, tablet, and installable play entry with reconnect behavior and role-aware routes.",
            eyebrow: "Mobile",
            heading: "Mobile and PWA entry",
            intro: "Installability, reconnect behavior, and player, GM, or observer entry stay on Chummer routes instead of fallback docs or legacy aliases.",
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
            chromeDescription: "Role-aware mobile and tablet entry with reconnect and continuity inside Chummer.",
            eyebrow: "Play shell",
            heading: $"{currentRoleLabel} entry",
            intro: "The play shell keeps role entry, reconnect expectations, and current continuity visible without pretending the mobile route replaces installs, support, or deeper campaign work.",
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
            eyebrow: "Dedicated ruleset path",
            heading: "Shadowrun Anarchy",
            intro: "A shipped rules-light path for mobile play, dispatches, faction consequence, and fast continuity. Chummer treats Anarchy as its own ruleset profile without claiming full dense-book completeness.",
            primaryAction: new TrustPageActionViewModel("Open Anarchy play shell", "/play/anarchy", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open Anarchy ledger", "/ledger/anarchy", "secondary"),
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
            intro: "This page keeps a one-page runner sheet, continuity cues, and explainable export together without pretending to be full dense-builder parity.",
            primaryAction: new TrustPageActionViewModel("Open mobile and PWA", "/mobile", "primary"),
            secondaryAction: new TrustPageActionViewModel("View dispatches through the Anarchy lens", "/ledger/dispatches?ruleset=anarchy", "secondary"),
            cancellationToken: cancellationToken);
        return View("~/Views/PublicLanding/Anarchy.cshtml", model);
    }

    [HttpGet("/anarchy/export/runner.json")]
    [Produces("application/json")]
    public IActionResult AnarchyExportJson()
        => Content(_waveEightHorizons.BuildAnarchyExportJson(), "application/json");

    [HttpGet("/anarchy/explain")]
    [HttpGet("/anarchy/receipts/explain.json")]
    [Produces("application/json")]
    public IActionResult AnarchyExplainReceiptJson()
        => Content(_waveEightHorizons.BuildAnarchyExplainJson(), "application/json");

    [HttpGet("/anarchy/runtime")]
    [HttpGet("/anarchy/receipts/runtime.json")]
    [Produces("application/json")]
    public IActionResult AnarchyRuntimeReceiptJson()
    {
        var profile = _anarchyPreview.LoadFeaturedProfile();
        var explain = _anarchyPreview.BuildExplainReceipt();
        var dispatches = _anarchyPreview.ListDispatches();
        return Ok(new
        {
            Horizon = "anarchy",
            Status = "shipped_mvp",
            RulesetId = AnarchyPreviewService.RulesetId,
            PlayShell = new
            {
                OverviewHref = "/anarchy",
                PlayHref = "/play/anarchy",
                LedgerHref = "/ledger/anarchy"
            },
            ExportLane = new
            {
                ExportJsonHref = "/anarchy/export/runner.json",
                ExplainReceiptHref = "/anarchy/explain",
                ExplainReceiptId = explain.ReceiptId
            },
            PublicProfile = new
            {
                Handle = profile.Handle,
                VerdictLabel = "Shipped rules-light path",
                ScopeLabel = "Dedicated ruleset path"
            },
            DispatchLane = new
            {
                DispatchCount = dispatches.Count,
                ReceiptAnchored = dispatches.All(item => string.Equals(item.SourceReceiptId, "ledger_tick_0001_preseeded", StringComparison.Ordinal)),
                DispatchHrefTemplate = "/ledger/dispatches?ruleset=anarchy"
            },
            Boundary = new
            {
                DenseBookCompleteness = "Not claimed",
                SourcebookProse = "Not shipped",
                WorldTruth = "Campaign city records only"
            }
        });
    }

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
            string hubLocalReleaseProofUrl = BuildAbsoluteUrl("/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json");
            string bootstrapTemplate = System.IO.File.ReadAllText(templatePath);
            string command = BuildReleaseUploadBootstrapCommand(
                bootstrapUrl,
                ComputeSha256Hex(bootstrapTemplate),
                hubLocalReleaseProofUrl,
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
                WindowsUploadNote: "Windows bundles use the same upload endpoint and the same signed-in claim-code return path once the signed installer, startup status, and promotion status are present.",
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
        string hubLocalReleaseProofUrl = BuildAbsoluteUrl("/proofs/mac-codex-release/HUB_LOCAL_RELEASE_PROOF.generated.json");
        string bootstrapTemplate = System.IO.File.ReadAllText(templatePath);
        string command = BuildReleaseUploadBootstrapCommand(
            bootstrapUrl,
            ComputeSha256Hex(bootstrapTemplate),
            hubLocalReleaseProofUrl,
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
                : string.Empty;
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
                Chrome: _chrome.BuildAuthenticatedChrome("Download", "Start the installer download.", "/downloads", user.DisplayName, user.Email),
                Eyebrow: "Download",
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
                AccountLabel: "Open installs",
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
            return Redirect($"/login?next={Uri.EscapeDataString($"/downloads/install/{artifactId}")}");
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
            "Direct Windows installer for support outside the main downloads page.",
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
            Summary: "This direct Windows installer stays available when this specific build is not on the main recommended downloads page.",
            DispatchNote: "Use this page when you need this exact installer.",
            ArtifactTitle: $"{headLabel} Windows x64 installer",
            ArtifactSupportLine: "Direct Windows installer.",
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
                    ["title"] = $"{headLabel} Windows direct install help",
                    ["summary"] = "This Windows installer needs help on this device.",
                    ["detail"] = "This Windows installer needs help on this device. Keep support on the same install page.",
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
            CurrentReleaseSummary: "This Windows installer stays available here; use the main downloads page for the recommended setup when it is promoted there.",
            PlatformLabel: "Windows x64",
            HeadLabel: headLabel,
            ClaimExchangeUrl: null,
            ClaimCode: null,
            ClaimCodeExpiresAtUtc: null,
            Steps:
            [
                "Download the direct installer from this page.",
                "Install and validate the current Windows build.",
                "Use install help and support if this Windows installer needs more help."
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
                    message = "The install command expired or is no longer available. Open the signed-in Downloads page and copy a fresh install command."
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
                detail: "No macOS setup files are available for this personalized install.");
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
                    message = "The install command expired. Open the signed-in Downloads page and copy a fresh install command."
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
            // .Replace( M143 source marker: missingReceiptReason: "No current local release-proof receipt is attached to this install recovery exchange route for the requested artifact." )
            missingReceiptReason: "No current release record is attached to this install recovery route for the requested artifact.");

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

    [HttpGet("/partizipate")]
    public async Task<IActionResult> ParticipateAliasPage(CancellationToken cancellationToken)
    {
        await Task.CompletedTask.ConfigureAwait(false);
        _ = cancellationToken;
        string target = $"/participate{Request.QueryString}";
        return Redirect(target);
    }

    [HttpGet("/participate")]
    [Produces("text/html")]
    public async Task<IActionResult> ParticipatePage(CancellationToken cancellationToken)
    {
        return await ParticipateBoardProxyCore(
            boardPath: string.Empty,
            cancellationToken,
            localOrigin: "/participate",
            localBaseHref: "/participate/",
            fallbackPath: "/participate").ConfigureAwait(false);
    }

    private async Task<FirstPartyParticipateBoardViewModel> BuildFirstPartyParticipateBoardAsync(CancellationToken cancellationToken, string currentPath = "/participate")
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalSubjectAsync(cancellationToken).ConfigureAwait(false);
        ParticipateItemViewModel[] fallbackItems =
        [
            new(8, "Mobile companion app for dice rolling", "Quick access for rolling dice pools and checking modifiers at the table.", "Open"),
            new(7, "Import characters from Chummer5A", "Bring existing .chum5 characters forward without rebuilding them by hand.", "Open"),
            new(5, "Shared initiative tracker", "A table view for GM and players when combat starts moving fast.", "Open")
        ];

        ProductLiftParticipateSnapshot snapshot = await TryFetchFirstPartyParticipatePostsAsync(cancellationToken).ConfigureAwait(false);
        bool loadedFromBoard = snapshot.Posts.Count > 0;

        return new FirstPartyParticipateBoardViewModel(
            Chrome: subject is null
                ? _chrome.BuildPublicChrome(
                    "Participate",
                    "Public requests and visible bugs.",
                    currentPath)
                : _chrome.BuildAuthenticatedChrome(
                    "Participate",
                    "Public requests and visible bugs.",
                    currentPath,
                    string.IsNullOrWhiteSpace(subject.DisplayName) ? "Signed in" : subject.DisplayName,
                    subject.Email),
            Heading: "Participate",
            Summary: "Short requests, clear bugs, useful ideas.",
            StatusLabel: loadedFromBoard ? "Live requests" : "Requests unavailable",
            Posts: snapshot.Posts,
            FallbackItems: fallbackItems,
            TotalRequestCount: loadedFromBoard ? snapshot.TotalCount : fallbackItems.Length,
            SyncedLabel: loadedFromBoard ? FormatParticipateSyncedLabel(snapshot.SyncedAtUtc) : "Fallback list",
            RoadmapHref: "/roadmap",
            SupportHref: "/contact#support-intake",
            RetryHref: currentPath,
            SupporterHref: ResolveParticipateSupporterHref(),
            LoadedFromBoard: loadedFromBoard);
    }

    private async Task<ProductLiftParticipateSnapshot> TryFetchFirstPartyParticipatePostsAsync(CancellationToken cancellationToken)
    {
        Uri? upstream = ResolveProductLiftHostedBoardUri();
        if (upstream is null)
        {
            return ProductLiftParticipateSnapshot.Empty;
        }

        Uri upstreamOrigin = new($"{upstream.GetLeftPart(UriPartial.Authority).TrimEnd('/')}/");
        Uri target = new(upstreamOrigin, "http_api/posts?tab=feedback");

        try
        {
            using HttpClient client = _httpClientFactory?.CreateClient() ?? new HttpClient();
            using var outbound = new HttpRequestMessage(HttpMethod.Get, target);
            outbound.Headers.TryAddWithoutValidation("Accept", "application/json");
            outbound.Headers.TryAddWithoutValidation("User-Agent", Request.Headers.UserAgent.ToString());

            using HttpResponseMessage response = await client.SendAsync(outbound, HttpCompletionOption.ResponseHeadersRead, cancellationToken).ConfigureAwait(false);
            if (!response.IsSuccessStatusCode)
            {
                return ProductLiftParticipateSnapshot.Empty;
            }

            string mediaType = response.Content.Headers.ContentType?.MediaType ?? string.Empty;
            if (!mediaType.Contains("json", StringComparison.OrdinalIgnoreCase))
            {
                return ProductLiftParticipateSnapshot.Empty;
            }

            await using Stream stream = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false);
            using JsonDocument document = await JsonDocument.ParseAsync(stream, cancellationToken: cancellationToken).ConfigureAwait(false);
            if (!document.RootElement.TryGetProperty("data", out JsonElement data) || data.ValueKind != JsonValueKind.Array)
            {
                return ProductLiftParticipateSnapshot.Empty;
            }

            List<FirstPartyParticipatePostViewModel> posts = [];
            foreach (JsonElement item in data.EnumerateArray())
            {
                if (posts.Count >= 12)
                {
                    break;
                }

                string title = ReadJsonString(item, "title");
                if (string.IsNullOrWhiteSpace(title))
                {
                    continue;
                }

                posts.Add(new FirstPartyParticipatePostViewModel(
                    Id: ReadJsonString(item, "id"),
                    Title: CleanParticipateCopy(title),
                    Summary: CleanParticipateCopy(FirstNonEmptyParticipateValue(
                        ReadJsonString(item, "description_short"),
                        ReadJsonString(item, "excerpt"),
                        StripHtml(ReadJsonString(item, "description")))),
                    Score: ReadJsonInt(item, "votes_count"),
                    CommentCount: ReadJsonInt(item, "comments_count"),
                    Status: CleanParticipateStatus(ReadNestedJsonString(item, "status", "name")),
                    Category: CleanParticipateCategory(ReadNestedJsonString(item, "category", "name")),
                    UpdatedLabel: FormatParticipateUpdatedLabel(ReadJsonString(item, "updated_at")),
                    Href: RewriteParticipatePostHref(FirstNonEmptyParticipateValue(
                        ReadJsonString(item, "proxy_url"),
                        ReadJsonString(item, "url")))));
            }

            int totalCount = ReadJsonInt(document.RootElement, "total");
            if (totalCount <= 0)
            {
                totalCount = posts.Count;
            }

            return new ProductLiftParticipateSnapshot(posts, totalCount, DateTimeOffset.UtcNow);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogWarning(ex, "Participate first-party board could not fetch public board posts.");
            return ProductLiftParticipateSnapshot.Empty;
        }
        catch (JsonException ex)
        {
            _logger.LogWarning(ex, "Participate first-party board received invalid public board JSON.");
            return ProductLiftParticipateSnapshot.Empty;
        }
        catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogWarning(ex, "Participate first-party board timed out while fetching posts.");
            return ProductLiftParticipateSnapshot.Empty;
        }
    }

    private sealed record ProductLiftParticipateSnapshot(
        IReadOnlyList<FirstPartyParticipatePostViewModel> Posts,
        int TotalCount,
        DateTimeOffset SyncedAtUtc)
    {
        public static ProductLiftParticipateSnapshot Empty { get; } = new([], 0, DateTimeOffset.MinValue);
    }

    private static string ReadJsonString(JsonElement element, string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out JsonElement value))
        {
            return string.Empty;
        }

        return value.ValueKind switch
        {
            JsonValueKind.String => value.GetString()?.Trim() ?? string.Empty,
            JsonValueKind.Number => value.GetRawText(),
            _ => string.Empty
        };
    }

    private static int ReadJsonInt(JsonElement element, string propertyName)
    {
        if (!element.TryGetProperty(propertyName, out JsonElement value))
        {
            return 0;
        }

        if (value.ValueKind == JsonValueKind.Number && value.TryGetInt32(out int number))
        {
            return Math.Max(0, number);
        }

        return value.ValueKind == JsonValueKind.String && int.TryParse(value.GetString(), NumberStyles.Integer, CultureInfo.InvariantCulture, out number)
            ? Math.Max(0, number)
            : 0;
    }

    private static string ReadNestedJsonString(JsonElement element, string objectPropertyName, string nestedPropertyName)
    {
        if (!element.TryGetProperty(objectPropertyName, out JsonElement nested) || nested.ValueKind != JsonValueKind.Object)
        {
            return string.Empty;
        }

        return ReadJsonString(nested, nestedPropertyName);
    }

    private static string FirstNonEmptyParticipateValue(params string[] values)
        => values.FirstOrDefault(static value => !string.IsNullOrWhiteSpace(value))?.Trim() ?? string.Empty;

    private static string? RewriteParticipatePostHref(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string trimmed = value.Trim();
        if (Uri.TryCreate(trimmed, UriKind.Absolute, out Uri? absolute))
        {
            string pathAndQuery = string.IsNullOrWhiteSpace(absolute.PathAndQuery) ? "/" : absolute.PathAndQuery;
            return $"/participate/board{pathAndQuery}";
        }

        if (!Uri.TryCreate(trimmed, UriKind.Relative, out _))
        {
            return null;
        }

        string relative = trimmed.StartsWith("/", StringComparison.Ordinal) ? trimmed : $"/{trimmed}";
        if (relative.StartsWith("/participate/board", StringComparison.OrdinalIgnoreCase))
        {
            return relative;
        }

        return $"/participate/board{relative}";
    }

    private static string StripHtml(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return string.Empty;
        }

        string withoutTags = Regex.Replace(value, "<.*?>", " ", RegexOptions.Singleline, TimeSpan.FromMilliseconds(250));
        return System.Net.WebUtility.HtmlDecode(withoutTags).Trim();
    }

    private static string CleanParticipateCopy(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return string.Empty;
        }

        string cleaned = value
            .Replace("AI-powered", string.Empty, StringComparison.OrdinalIgnoreCase)
            .Replace("AI powered", string.Empty, StringComparison.OrdinalIgnoreCase)
            .Replace("AI-generated", string.Empty, StringComparison.OrdinalIgnoreCase)
            .Replace("AI generated", string.Empty, StringComparison.OrdinalIgnoreCase)
            .Replace("Automatically generate", "Create", StringComparison.OrdinalIgnoreCase)
            .Replace("automatically generate", "create", StringComparison.Ordinal);

        cleaned = Regex.Replace(cleaned, @"\s{2,}", " ", RegexOptions.None, TimeSpan.FromMilliseconds(250)).Trim();
        return cleaned.Length <= 220 ? cleaned : $"{cleaned[..217].TrimEnd()}...";
    }

    private static string CleanParticipateStatus(string value)
    {
        string cleaned = CleanParticipateCopy(value);
        return string.Equals(cleaned, "Gathering votes", StringComparison.OrdinalIgnoreCase)
            ? "Open"
            : (string.IsNullOrWhiteSpace(cleaned) ? "Open" : cleaned);
    }

    private static string CleanParticipateCategory(string value)
    {
        string cleaned = CleanParticipateCopy(value);
        return string.Equals(cleaned, "Feature", StringComparison.OrdinalIgnoreCase)
            ? "Idea"
            : (string.IsNullOrWhiteSpace(cleaned) ? "Request" : cleaned);
    }

    private static string FormatParticipateUpdatedLabel(string raw)
    {
        if (!DateTimeOffset.TryParse(raw, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out DateTimeOffset updated))
        {
            return "Updated";
        }

        return $"Updated {updated.UtcDateTime:yyyy-MM-dd}";
    }

    private static string FormatParticipateSyncedLabel(DateTimeOffset syncedAtUtc)
        => syncedAtUtc == DateTimeOffset.MinValue
            ? "Not synced"
            : $"Synced {syncedAtUtc.UtcDateTime:HH:mm} UTC";

    [HttpGet("/partizipate/{**boardPath}")]
    public Task<IActionResult> ParticipateBoardProxyLegacyAlias(string? boardPath, CancellationToken cancellationToken)
    {
        _ = cancellationToken;
        string raw = string.IsNullOrWhiteSpace(boardPath) ? string.Empty : boardPath.TrimStart('/');
        if (string.IsNullOrWhiteSpace(raw))
        {
            return Task.FromResult<IActionResult>(Redirect($"/participate{Request.QueryString}"));
        }

        string targetPath = raw switch
        {
            var value when string.Equals(value, "board", StringComparison.OrdinalIgnoreCase) => string.Empty,
            var value when value.StartsWith("board/", StringComparison.OrdinalIgnoreCase) => value["board/".Length..],
            _ => raw
        };
        string pathPrefix = string.IsNullOrWhiteSpace(targetPath) ? string.Empty : $"/{targetPath}";
        return Task.FromResult<IActionResult>(Redirect($"/participate{pathPrefix}{Request.QueryString}"));
    }

    [HttpGet("/participate/{**boardPath}")]
    public async Task<IActionResult> ParticipateBoardProxyAlias(string? boardPath, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(boardPath))
        {
            return Redirect($"/participate{Request.QueryString}");
        }

        return await ParticipateBoardProxyCore(
            NormalizeParticipateBoardPath(boardPath),
            cancellationToken,
            localOrigin: "/participate",
            localBaseHref: "/participate/",
            fallbackPath: "/participate").ConfigureAwait(false);
    }

    [HttpGet("/participate/board")]
    [HttpGet("/participate/board/{**boardPath}")]
    public async Task<IActionResult> ParticipateBoardProxy(string? boardPath, CancellationToken cancellationToken)
        => await ParticipateBoardProxyCore(NormalizeParticipateBoardPath(boardPath), cancellationToken).ConfigureAwait(false);

    [AcceptVerbs("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", Route = "/http_api/{**boardPath}")]
    public async Task<IActionResult> ParticipateBoardRootHttpApiProxy(string? boardPath, CancellationToken cancellationToken)
        => await ParticipateBoardRootResourceProxy("http_api", boardPath, cancellationToken).ConfigureAwait(false);

    [HttpGet("/translations_i18n/{**boardPath}")]
    public async Task<IActionResult> ParticipateBoardRootTranslationsProxy(string? boardPath, CancellationToken cancellationToken)
        => await ParticipateBoardRootResourceProxy("translations_i18n", boardPath, cancellationToken).ConfigureAwait(false);

    [HttpGet("/loading.svg")]
    public async Task<IActionResult> ParticipateBoardRootLoadingImageProxy(CancellationToken cancellationToken)
        => await ParticipateBoardRootResourceProxy("loading.svg", null, cancellationToken).ConfigureAwait(false);

    [HttpGet("/participate/provider-assets/{assetHost}/{**assetPath}")]
    [HttpGet("/partizipate/provider-assets/{assetHost}/{**assetPath}")]
    public async Task<IActionResult> ParticipateBoardProviderAssetProxy(string assetHost, string? assetPath, CancellationToken cancellationToken)
        => await ParticipateBoardProviderAssetProxyCore(assetHost, assetPath, cancellationToken).ConfigureAwait(false);

    [HttpGet("/roadmap/provider-assets/{assetHost}/{**assetPath}")]
    public async Task<IActionResult> RoadmapBoardProviderAssetProxy(string assetHost, string? assetPath, CancellationToken cancellationToken)
        => await ParticipateBoardProviderAssetProxyCore(assetHost, assetPath, cancellationToken).ConfigureAwait(false);

    private async Task<IActionResult> ParticipateBoardProxyCore(
        string? boardPath,
        CancellationToken cancellationToken,
        string localOrigin = "/participate/board",
        string localBaseHref = "/participate/board/",
        string fallbackPath = "/participate")
    {
        Uri? upstream = ResolveProductLiftHostedBoardUri();
        if (upstream is null)
        {
            return ParticipateBoardUnavailable(fallbackPath);
        }

        string relativePath = string.IsNullOrWhiteSpace(boardPath) ? string.Empty : boardPath.TrimStart('/');
        Uri target = string.IsNullOrWhiteSpace(relativePath)
            ? AppendQueryString(upstream, Request.QueryString.Value)
            : AppendQueryString(new Uri(upstream, relativePath), Request.QueryString.Value);

        try
        {
            using HttpClient client = _httpClientFactory?.CreateClient() ?? new HttpClient();
            using var outbound = new HttpRequestMessage(HttpMethod.Get, target);
            outbound.Headers.TryAddWithoutValidation("User-Agent", Request.Headers.UserAgent.ToString());
            outbound.Headers.TryAddWithoutValidation("Accept", Request.Headers.Accept.ToArray());
            outbound.Headers.TryAddWithoutValidation("Accept-Language", Request.Headers.AcceptLanguage.ToArray());
            outbound.Headers.Referrer = upstream;

            using HttpResponseMessage response = await client.SendAsync(outbound, HttpCompletionOption.ResponseHeadersRead, cancellationToken);

            if ((int)response.StatusCode >= 300 && (int)response.StatusCode < 400 && response.Headers.Location is not null)
            {
                string redirected = RewriteHostedBoardLocation(response.Headers.Location, upstream, fallbackPath, localOrigin);
                return Redirect(redirected);
            }

            string mediaType = response.Content.Headers.ContentType?.MediaType ?? "application/octet-stream";
            if (mediaType.StartsWith("text/html", StringComparison.OrdinalIgnoreCase))
            {
                string html = await response.Content.ReadAsStringAsync(cancellationToken);
                if (!response.IsSuccessStatusCode || HostedBoardHtmlLooksUnavailable(html))
                {
                    return ParticipateBoardUnavailable(fallbackPath);
                }

                string rewritten = RewriteHostedBoardHtml(
                    html,
                    upstream,
                    ResolveParticipateBoardHomeHref(),
                    ResolveParticipateSupporterHref(),
                    localOrigin,
                    localBaseHref,
                    railTitle: "Chummer Participate",
                    railNavLabel: "Participate actions",
                    firstLinkHref: "/roadmap",
                    firstLinkLabel: "Roadmap",
                    secondLinkHref: fallbackPath,
                    secondLinkLabel: "Board",
                    canonicalHref: localOrigin,
                    assetProxyBasePath: "/participate/provider-assets",
                    pageTitle: "Participate - Chummer.run",
                    hostedHeadingReplacement: "What should Chummer do next?",
                    hostedSummaryReplacement: "Short requests, clear bugs, useful ideas.",
                    hostedPrimaryActionReplacement: "Add a note",
                    hostedLeadReplacement: "Tell us what would help.",
                    applyFeedbackPolish: true,
                    failureTitle: "The board is unavailable",
                    failureSummary: "Try again shortly. Use Support only for private or blocked issues.",
                    failurePrimaryHref: "/roadmap",
                    failurePrimaryLabel: "Roadmap",
                    failureSecondaryHref: "/contact#support-intake",
                    failureSecondaryLabel: "Support",
                    failureReturnHref: fallbackPath,
                    failureReturnLabel: "Retry");
                return Content(rewritten, "text/html; charset=utf-8");
            }

            byte[] bytes = await response.Content.ReadAsByteArrayAsync(cancellationToken);
            CopySafeProxyHeaders(response);
            return File(bytes, mediaType);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogWarning(ex, "Participate board proxy could not reach upstream board.");
            return ParticipateBoardUnavailable(fallbackPath);
        }
        catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogWarning(ex, "Participate board proxy timed out.");
            return ParticipateBoardUnavailable(fallbackPath);
        }
    }

    private async Task<IActionResult> ParticipateBoardRootResourceProxy(string rootSegment, string? boardPath, CancellationToken cancellationToken)
    {
        Uri? upstream = ResolveProductLiftHostedBoardUri();
        if (upstream is null)
        {
            return NotFound();
        }

        string relativePath = string.IsNullOrWhiteSpace(boardPath)
            ? rootSegment
            : $"{rootSegment.TrimEnd('/')}/{boardPath.TrimStart('/')}";
        Uri upstreamOrigin = new($"{upstream.GetLeftPart(UriPartial.Authority).TrimEnd('/')}/");
        Uri target = AppendQueryString(new Uri(upstreamOrigin, relativePath), Request.QueryString.Value);

        try
        {
            using HttpClient client = _httpClientFactory?.CreateClient() ?? new HttpClient();
            using var outbound = new HttpRequestMessage(new HttpMethod(Request.Method), target);
            CopySafeBoardRequestHeaders(outbound);

            if (HttpMethods.IsPost(Request.Method)
                || HttpMethods.IsPut(Request.Method)
                || HttpMethods.IsPatch(Request.Method)
                || HttpMethods.IsDelete(Request.Method))
            {
                outbound.Content = new StreamContent(Request.Body);
                if (!string.IsNullOrWhiteSpace(Request.ContentType))
                {
                    outbound.Content.Headers.TryAddWithoutValidation("Content-Type", Request.ContentType);
                }
            }

            using HttpResponseMessage response = await client.SendAsync(outbound, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
            string mediaType = response.Content.Headers.ContentType?.MediaType ?? "application/octet-stream";
            byte[] bytes = await response.Content.ReadAsByteArrayAsync(cancellationToken);
            CopySafeProxyHeaders(response);
            return File(bytes, mediaType);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogWarning(ex, "Participate board root proxy could not reach upstream board resource {RootSegment}.", rootSegment);
            return NotFound();
        }
        catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogWarning(ex, "Participate board root proxy timed out for upstream board resource {RootSegment}.", rootSegment);
            return NotFound();
        }
    }

    private async Task<IActionResult> ParticipateBoardProviderAssetProxyCore(string assetHost, string? assetPath, CancellationToken cancellationToken)
    {
        string normalizedHost = assetHost.Trim().ToLowerInvariant();
        if (normalizedHost is not ("media" or "cdn") || string.IsNullOrWhiteSpace(assetPath))
        {
            return NotFound();
        }

        string providerDomain = string.Concat("product", "lift.dev");
        Uri target = AppendQueryString(
            new Uri($"https://{normalizedHost}.{providerDomain}/{assetPath.TrimStart('/')}"),
            Request.QueryString.Value);

        try
        {
            using HttpClient client = _httpClientFactory?.CreateClient() ?? new HttpClient();
            using var outbound = new HttpRequestMessage(HttpMethod.Get, target);
            outbound.Headers.TryAddWithoutValidation("User-Agent", Request.Headers.UserAgent.ToArray());
            outbound.Headers.TryAddWithoutValidation("Accept", Request.Headers.Accept.ToArray());
            outbound.Headers.TryAddWithoutValidation("Accept-Language", Request.Headers.AcceptLanguage.ToArray());

            using HttpResponseMessage response = await client.SendAsync(outbound, HttpCompletionOption.ResponseHeadersRead, cancellationToken);
            if (!response.IsSuccessStatusCode)
            {
                return StatusCode((int)response.StatusCode);
            }

            string mediaType = response.Content.Headers.ContentType?.MediaType ?? "application/octet-stream";
            byte[] bytes = await response.Content.ReadAsByteArrayAsync(cancellationToken);
            CopySafeProxyHeaders(response);
            return File(bytes, mediaType);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogWarning(ex, "Participate board provider asset proxy could not reach {AssetHost}.", normalizedHost);
            return NotFound();
        }
        catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogWarning(ex, "Participate board provider asset proxy timed out for {AssetHost}.", normalizedHost);
            return NotFound();
        }
    }

    private void CopySafeBoardRequestHeaders(HttpRequestMessage outbound)
    {
        outbound.Headers.TryAddWithoutValidation("User-Agent", Request.Headers.UserAgent.ToArray());
        outbound.Headers.TryAddWithoutValidation("Accept", Request.Headers.Accept.ToArray());
        outbound.Headers.TryAddWithoutValidation("Accept-Language", Request.Headers.AcceptLanguage.ToArray());
        outbound.Headers.TryAddWithoutValidation("X-Requested-With", Request.Headers["X-Requested-With"].ToArray());
        outbound.Headers.TryAddWithoutValidation("X-CSRF-TOKEN", Request.Headers["X-CSRF-TOKEN"].ToArray());
        outbound.Headers.TryAddWithoutValidation("X-XSRF-TOKEN", Request.Headers["X-XSRF-TOKEN"].ToArray());
    }

    private static string NormalizeParticipateBoardPath(string? boardPath)
    {
        string relativePath = string.IsNullOrWhiteSpace(boardPath) ? string.Empty : boardPath.TrimStart('/');
        if (relativePath.StartsWith("board/", StringComparison.OrdinalIgnoreCase))
        {
            return relativePath["board/".Length..];
        }

        return string.Equals(relativePath, "board", StringComparison.OrdinalIgnoreCase)
            ? string.Empty
            : relativePath;
    }

    private ContentResult ParticipateBoardUnavailable(string returnHref = "/participate")
        => HostedBoardUnavailable(
            "The board is unavailable",
            "Try again shortly.",
            "Use Support for account, install, or private details.",
            "/roadmap",
            "Roadmap",
            "/contact#support-intake",
            "Support",
            returnHref,
            "Retry");

    private ContentResult HostedBoardUnavailable(
        string title,
        string lead,
        string summary,
        string primaryHref,
        string primaryLabel,
        string secondaryHref,
        string secondaryLabel,
        string returnHref,
        string returnLabel)
    {
        string html = $$"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{title}}</title>
  <style>
    :root { color-scheme: dark; }
    body { margin: 0; font-family: Inter, system-ui, sans-serif; background: #11131a; color: #f3f4f7; }
    main { max-width: 44rem; margin: 0 auto; padding: 2rem 1.25rem; }
    h1 { font-size: 1.4rem; margin: 0 0 0.75rem; }
    p { line-height: 1.55; color: #cfd5df; margin: 0 0 1rem; }
    .actions { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-top: 1.25rem; }
    a { color: inherit; text-decoration: none; border: 1px solid #2c3340; padding: 0.7rem 0.95rem; border-radius: 999px; }
  </style>
</head>
<body>
  <main>
    <h1>{{title}}</h1>
    <p>{{lead}}</p>
    <p>{{summary}}</p>
    <div class="actions">
      <a href="{{primaryHref}}" target="_top" rel="noopener">{{primaryLabel}}</a>
      <a href="{{secondaryHref}}" target="_top" rel="noopener">{{secondaryLabel}}</a>
      <a href="{{returnHref}}" target="_top" rel="noopener">{{returnLabel}}</a>
    </div>
  </main>
</body>
</html>
""";
        return Content(html, "text/html; charset=utf-8");
    }

    private string? ResolveProductLiftHostedBoardHref()
        => ResolveProductLiftHostedBoardUri() is null ? null : "/participate/board";

    private static string BuildParticipateSignInHref(string targetPath = "/participate")
        => $"/auth/google/start?next={Uri.EscapeDataString(string.IsNullOrWhiteSpace(targetPath) ? "/participate" : targetPath)}";

    private string ResolveParticipateBoardHomeHref()
    {
        string configured = (_configuration["CHUMMER_PUBLIC_BASE_URL"] ?? "https://chummer.run").Trim();
        if (!Uri.TryCreate(configured, UriKind.Absolute, out Uri? uri))
        {
            return "https://chummer.run/";
        }

        return $"{uri.GetLeftPart(UriPartial.Authority).TrimEnd('/')}/";
    }

    private Uri? ResolveProductLiftHostedBoardUri()
    {
        string? configured = _configuration["CHUMMER_PRODUCTLIFT_FEEDBACK_URL"]?.Trim();
        if (string.IsNullOrWhiteSpace(configured)
            || !Uri.TryCreate(configured, UriKind.Absolute, out Uri? uri)
            || (uri.Scheme != Uri.UriSchemeHttps
                && !(uri.Scheme == Uri.UriSchemeHttp && uri.IsLoopback)))
        {
            return null;
        }

        return uri;
    }

    private string? ResolveProductLiftHostedRoadmapHref()
        => ResolveProductLiftHostedRoadmapUri() is null ? null : "/roadmap/board";

    private Uri? ResolveProductLiftHostedRoadmapUri()
    {
        string? configured = _configuration["CHUMMER_PRODUCTLIFT_ROADMAP_URL"]?.Trim();
        if (string.IsNullOrWhiteSpace(configured)
            || !Uri.TryCreate(configured, UriKind.Absolute, out Uri? uri)
            || (uri.Scheme != Uri.UriSchemeHttps
                && !(uri.Scheme == Uri.UriSchemeHttp && uri.IsLoopback)))
        {
            return null;
        }

        return uri;
    }

    private static Uri AppendQueryString(Uri baseUri, string? queryString)
    {
        if (string.IsNullOrWhiteSpace(queryString))
        {
            return baseUri;
        }

        string raw = queryString.StartsWith('?') ? queryString : $"?{queryString}";
        var builder = new UriBuilder(baseUri)
        {
            Query = raw.TrimStart('?')
        };
        return builder.Uri;
    }

    private static string RewriteHostedBoardLocation(Uri location, Uri upstream, string fallbackPath, string localPrefix)
    {
        Uri absolute = location.IsAbsoluteUri ? location : new Uri(upstream, location);
        if (!Uri.Compare(absolute, upstream, UriComponents.SchemeAndServer, UriFormat.Unescaped, StringComparison.OrdinalIgnoreCase).Equals(0))
        {
            return fallbackPath;
        }

        string relative = upstream.MakeRelativeUri(absolute).ToString();
        if (string.IsNullOrWhiteSpace(relative))
        {
            return fallbackPath;
        }

        return $"{localPrefix}/{relative}";
    }

    private string RewriteParticipateBoardLocation(Uri location, Uri upstream)
        => RewriteHostedBoardLocation(location, upstream, "/participate", "/participate/board");

    private static string RewriteHostedBoardHtml(
        string html,
        Uri upstream,
        string publicHomeHref,
        string? supporterHref,
        string localOrigin,
        string localBaseHref,
        string railTitle,
        string railNavLabel,
        string firstLinkHref,
        string firstLinkLabel,
        string secondLinkHref,
        string secondLinkLabel,
        string canonicalHref,
        string assetProxyBasePath,
        string pageTitle,
        string? hostedHeadingReplacement,
        string? hostedSummaryReplacement,
        string? hostedPrimaryActionReplacement,
        string? hostedLeadReplacement,
        bool applyFeedbackPolish,
        string failureTitle,
        string failureSummary,
        string failurePrimaryHref,
        string failurePrimaryLabel,
        string failureSecondaryHref,
        string failureSecondaryLabel,
        string failureReturnHref,
        string failureReturnLabel)
    {
        string upstreamOrigin = upstream.GetLeftPart(UriPartial.Authority).TrimEnd('/');

        string rewritten = html.Replace(upstreamOrigin, localOrigin, StringComparison.OrdinalIgnoreCase);
        rewritten = rewritten.Replace("href=\"/", $"href=\"{localOrigin}/", StringComparison.OrdinalIgnoreCase);
        rewritten = rewritten.Replace("src=\"/", $"src=\"{localOrigin}/", StringComparison.OrdinalIgnoreCase);
        rewritten = rewritten.Replace("action=\"/", $"action=\"{localOrigin}/", StringComparison.OrdinalIgnoreCase);
        rewritten = rewritten.Replace("content=\"/", $"content=\"{localOrigin}/", StringComparison.OrdinalIgnoreCase);
        rewritten = Regex.Replace(
            rewritten,
            @"<title>.*?</title>",
            $"<title>{HtmlEncoder.Default.Encode(pageTitle)}</title>",
            RegexOptions.IgnoreCase | RegexOptions.Singleline,
            TimeSpan.FromMilliseconds(250));
        if (!string.IsNullOrWhiteSpace(hostedHeadingReplacement))
        {
            rewritten = rewritten.Replace("What do you want to see next?", hostedHeadingReplacement, StringComparison.OrdinalIgnoreCase);
        }

        if (!string.IsNullOrWhiteSpace(hostedSummaryReplacement))
        {
            rewritten = rewritten.Replace("Tell us how we could make Chummer6 more useful to you", hostedSummaryReplacement, StringComparison.OrdinalIgnoreCase);
        }

        if (!string.IsNullOrWhiteSpace(hostedPrimaryActionReplacement))
        {
            rewritten = rewritten.Replace("Add Feature or Bug", hostedPrimaryActionReplacement, StringComparison.OrdinalIgnoreCase);
        }

        if (!string.IsNullOrWhiteSpace(hostedLeadReplacement))
        {
            rewritten = rewritten.Replace("Let us know how we can improve Chummer6.", hostedLeadReplacement, StringComparison.OrdinalIgnoreCase);
        }

        if (!rewritten.Contains("<base ", StringComparison.OrdinalIgnoreCase))
        {
            rewritten = Regex.Replace(
                rewritten,
                "<head(.*?)>",
                $"<head$1><base href=\"{localBaseHref}\" />",
                RegexOptions.IgnoreCase | RegexOptions.Singleline,
                TimeSpan.FromMilliseconds(250));
        }

        rewritten = Regex.Replace(
            rewritten,
            @"<link\b(?=[^>]*\brel\s*=\s*[""']canonical[""'])[^>]*>",
            string.Empty,
            RegexOptions.IgnoreCase | RegexOptions.Singleline,
            TimeSpan.FromMilliseconds(250));
        rewritten = Regex.Replace(
            rewritten,
            @"(<base\b[^>]*>)",
            $"$1<link rel=\"canonical\" href=\"{canonicalHref}\" />",
            RegexOptions.IgnoreCase | RegexOptions.Singleline,
            TimeSpan.FromMilliseconds(250));
        rewritten = Regex.Replace(
            rewritten,
            @"(<meta\b[^>]*\b(?:property|name)\s*=\s*[""'](?:og:url|twitter:url)[""'][^>]*\bcontent\s*=\s*[""'])[^""']*([""'][^>]*>)",
            $"$1{canonicalHref}$2",
            RegexOptions.IgnoreCase | RegexOptions.Singleline,
            TimeSpan.FromMilliseconds(250));

        if (!rewritten.Contains("data-chummer-home-link-patch", StringComparison.Ordinal))
        {
            string escapedPublicHomeHref = JavaScriptEncoder.Default.Encode(publicHomeHref);
            string pageTitleJson = JsonSerializer.Serialize(pageTitle);
            string localOriginJson = JsonSerializer.Serialize(localOrigin);
            string canonicalHrefJson = JsonSerializer.Serialize(canonicalHref);
            string headingReplacementJs = string.IsNullOrWhiteSpace(hostedHeadingReplacement)
                ? string.Empty
                : $"[new RegExp('\\\\bWhat do you want' + ' to see next\\\\?', 'g'), {JsonSerializer.Serialize(hostedHeadingReplacement)}],";
            string summaryReplacementJs = string.IsNullOrWhiteSpace(hostedSummaryReplacement)
                ? string.Empty
                : $"[new RegExp('\\\\bTell us how we could make Chummer6' + ' more useful to you\\\\b', 'g'), {JsonSerializer.Serialize(hostedSummaryReplacement)}],";
            string primaryActionReplacementJs = string.IsNullOrWhiteSpace(hostedPrimaryActionReplacement)
                ? string.Empty
                : $"[/\\\\bAdd Feature or Bug\\\\b/g, {JsonSerializer.Serialize(hostedPrimaryActionReplacement)}],";
            string leadReplacementJs = string.IsNullOrWhiteSpace(hostedLeadReplacement)
                ? string.Empty
                : $"[/\\\\bLet us know how we can improve Chummer6\\\\./g, {JsonSerializer.Serialize(hostedLeadReplacement)}],";
            string feedbackOnlyReplacementsJs = applyFeedbackPolish
                ? """
      [/\bShort title of your feedback\.\.\./g, 'Short title'],
      [/\bDescribe your idea or bug\.\.\./g, 'What happened, or what should exist?'],
      [/-- Choose a category --/g, 'Choose a category'],
      [/\bGathering votes\b/g, ''],
      [/\bFeature\b/g, 'Idea'],
      [/\bvotes\b/gi, 'requests'],
"""
                : string.Empty;
            string hiddenStatusTermsJs = applyFeedbackPolish
                ? "['gathering votes', 'planned', 'in progress']"
                : "[]";
            const string boardSkin = """
<style data-chummer-board-skin>
:root {
  color-scheme: dark;
  --chummer-board-bg: #0b0c0d;
  --chummer-board-panel: #15171a;
  --chummer-board-panel-soft: #111315;
  --chummer-board-line: rgba(241, 233, 219, 0.1);
  --chummer-board-text: #f4eee4;
  --chummer-board-muted: #b8afa1;
  --chummer-board-accent: #d6b763;
}

body {
  background: var(--chummer-board-bg) !important;
  color: var(--chummer-board-text) !important;
}

main,
[role="main"] {
  max-width: 1180px !important;
  margin-inline: auto !important;
}

main > section:first-of-type,
[role="main"] > section:first-of-type {
  margin: 0.8rem 0 1rem !important;
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
}

article,
form,
[class*="card"],
[class*="panel"] {
  border-color: var(--chummer-board-line) !important;
  border-radius: 8px !important;
  background-color: var(--chummer-board-panel) !important;
  box-shadow: none !important;
}

button,
a,
input,
textarea,
select {
  border-radius: 8px !important;
  box-shadow: none !important;
}

button,
[role="button"] {
  background-image: none !important;
}

input,
textarea,
select {
  background-color: #111315 !important;
  border-color: rgba(241, 233, 219, 0.14) !important;
  color: var(--chummer-board-text) !important;
}

input::placeholder,
textarea::placeholder {
  color: rgba(244, 238, 228, 0.52) !important;
}

[data-chummer-hidden-status] {
  display: none !important;
}

body > header,
body > nav,
[class*="navbar"],
[class*="topbar"],
[class*="top-bar"],
[class*="sidebar"],
[id*="global-search"],
[class*="global-search"],
[class*="search-modal"],
[class*="image-modal"],
[id*="imageModal"] {
  display: none !important;
}

main,
[role="main"] {
  padding-top: 0 !important;
}
</style>
""";
            string homeLinkPatch = """
<script data-chummer-home-link-patch>
document.addEventListener('DOMContentLoaded', function () {
  const pageTitle = __CHUMMER_PAGE_TITLE__;
  const localOrigin = __CHUMMER_LOCAL_ORIGIN__;
  const canonicalHref = __CHUMMER_CANONICAL_HREF__;
  const hiddenStatusTerms = __CHUMMER_HIDDEN_STATUS_TERMS__;
  const polishVisibleCopy = function () {
    const replacements = [
      [/\bAI-powered\b/gi, ''],
      [/\bAI powered\b/gi, ''],
      [new RegExp('\\bAI' + '-generated\\b', 'gi'), ''],
      [new RegExp('\\bAI' + ' generated\\b', 'gi'), ''],
      [/\bArtificial intelligence\b/gi, ''],
      [/\bAutomatically generate\b/gi, 'Create'],
      [/\bautomatically generate\b/g, 'create'],
      __CHUMMER_HEADING_REPLACEMENT__
      __CHUMMER_SUMMARY_REPLACEMENT__
      __CHUMMER_PRIMARY_ACTION_REPLACEMENT__
      __CHUMMER_LEAD_REPLACEMENT__
      __CHUMMER_FEEDBACK_ONLY_REPLACEMENTS__
      [/\s{2,}/g, ' ']
    ];

    document.title = pageTitle;

    const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    while (walker.nextNode()) {
      textNodes.push(walker.currentNode);
    }

    textNodes.forEach(function (node) {
      let value = node.nodeValue || '';
      const original = value;
      replacements.forEach(function (pair) {
        value = value.replace(pair[0], pair[1]);
      });

      if (value !== original) {
        node.nodeValue = value.trimStart();
      }
    });

    const attributeCandidates = Array.from(document.querySelectorAll('[placeholder], [aria-label], [title]'));
    attributeCandidates.forEach(function (node) {
      ['placeholder', 'aria-label', 'title'].forEach(function (name) {
        if (!node.hasAttribute(name)) {
          return;
        }

        let value = node.getAttribute(name) || '';
        const original = value;
        replacements.forEach(function (pair) {
          value = value.replace(pair[0], pair[1]);
        });

        if (value !== original) {
          node.setAttribute(name, value.trim());
        }
      });
    });
  };

  const quietHostedBoardChrome = function () {
    const nodes = Array.from(document.querySelectorAll('span, small, label, div, button, option, a, nav, header'));
    nodes.forEach(function (node) {
      const text = (node.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
      if (hiddenStatusTerms.includes(text)) {
        node.setAttribute('data-chummer-hidden-status', 'true');
      }

      if (text === 'search' || text === 'ctrl k' || text === '×' || text === 'x') {
        node.setAttribute('data-chummer-hidden-status', 'true');
      }

      if (node instanceof HTMLButtonElement && text === 'create' && hiddenStatusTerms.length > 0) {
        node.textContent = 'Send';
      }
    });
  };

  const removeHostedAuth = function () {
    const authCandidates = Array.from(document.querySelectorAll('a[href], button, [role="button"]'));
    authCandidates.forEach(function (node) {
      const text = ((node.textContent || '') + ' ' + (node.getAttribute('aria-label') || '')).trim().toLowerCase();
      const href = (node.getAttribute('href') || '').trim().toLowerCase();
      const authLikeText = text === ('log' + ' in')
        || text === ('log' + 'in')
        || text === ('sign' + ' in')
        || text === ('sign' + 'in')
        || text === ('sign' + ' up')
        || text === ('sign' + 'up')
        || text === 'register'
        || text.includes('log' + ' in')
        || text.includes('sign' + ' up')
        || text.includes('sign' + ' in');
      const authLikeHref = href.includes('/' + 'login')
        || href.includes('/' + 'signup')
        || href.includes('/register')
        || href.includes('product' + 'lift.dev/' + 'login')
        || href.includes('product' + 'lift.dev/' + 'signup');

      if (!authLikeText && !authLikeHref) {
        return;
      }

      if (node instanceof HTMLElement) {
        node.remove();
      }
    });
  };

  polishVisibleCopy();
  quietHostedBoardChrome();
  removeHostedAuth();
  const authObserver = new MutationObserver(function () {
    polishVisibleCopy();
    quietHostedBoardChrome();
    removeHostedAuth();
  });
  authObserver.observe(document.documentElement, { childList: true, subtree: true });

  const candidates = Array.from(document.querySelectorAll('header a[href], nav a[href], [class*="header"] a[href], [class*="brand"] a[href], [class*="logo"] a[href]'));
  const brand = candidates.find(function (anchor) {
    if (!(anchor instanceof HTMLAnchorElement)) {
      return false;
    }

    const href = (anchor.getAttribute('href') || '').trim();
    if (!href) {
      return false;
    }

    const text = (anchor.textContent || '').trim().toLowerCase();
    const hasBrandText = text === 'chummer' || text === ('product' + 'lift') || text.includes('feedback') || text.includes('roadmap');
    const hasLogo = !!anchor.querySelector('img, svg');
    const pointsToRoot = href === '/'
      || href === canonicalHref
      || href === canonicalHref + '/'
      || href === localOrigin
      || href === localOrigin + '/'
      || href === '/partizipate'
      || href === '/partizipate/'
      || /^https:\/\/[^/]+\/?$/.test(href);

    return pointsToRoot && (hasBrandText || hasLogo);
  });

  if (!brand) {
    return;
  }

  brand.setAttribute('href', '__CHUMMER_PUBLIC_HOME_HREF__');
  brand.setAttribute('target', '_top');
  brand.setAttribute('rel', 'noopener');
});
</script>
"""
                .Replace("__CHUMMER_PUBLIC_HOME_HREF__", escapedPublicHomeHref, StringComparison.Ordinal)
                .Replace("__CHUMMER_PAGE_TITLE__", pageTitleJson, StringComparison.Ordinal)
                .Replace("__CHUMMER_LOCAL_ORIGIN__", localOriginJson, StringComparison.Ordinal)
                .Replace("__CHUMMER_CANONICAL_HREF__", canonicalHrefJson, StringComparison.Ordinal)
                .Replace("__CHUMMER_HIDDEN_STATUS_TERMS__", hiddenStatusTermsJs, StringComparison.Ordinal)
                .Replace("__CHUMMER_HEADING_REPLACEMENT__", headingReplacementJs, StringComparison.Ordinal)
                .Replace("__CHUMMER_SUMMARY_REPLACEMENT__", summaryReplacementJs, StringComparison.Ordinal)
                .Replace("__CHUMMER_PRIMARY_ACTION_REPLACEMENT__", primaryActionReplacementJs, StringComparison.Ordinal)
                .Replace("__CHUMMER_LEAD_REPLACEMENT__", leadReplacementJs, StringComparison.Ordinal)
                .Replace("__CHUMMER_FEEDBACK_ONLY_REPLACEMENTS__", feedbackOnlyReplacementsJs, StringComparison.Ordinal);

            string boardFailurePatch = """
<script data-chummer-board-failure-patch>
document.addEventListener('DOMContentLoaded', function () {
  const errorPhrases = [
    'something went wrong on our side',
    'could not load posts',
    'network error while loading tab configuration',
    'please try again or contact ' + 'support@' + 'product' + 'lift.dev'
  ];

  const ensureFailurePanel = function () {
    if (document.querySelector('[data-chummer-board-failure]')) {
      return document.querySelector('[data-chummer-board-failure]');
    }

    const panel = document.createElement('section');
    panel.setAttribute('data-chummer-board-failure', 'true');
    panel.setAttribute('role', 'status');
    panel.innerHTML = ''
      + '<style>'
      + '[data-chummer-board-failure]{margin:0.8rem; padding:0.85rem 0.95rem; border:1px solid rgba(238,232,222,0.12); border-radius:8px; background:#151310; color:#f2ede5; font:500 14px/1.5 Inter,system-ui,sans-serif;}'
      + '[data-chummer-board-failure] h2{margin:0 0 0.35rem; font-size:1rem; line-height:1.3; color:#f7f1e8;}'
      + '[data-chummer-board-failure] p{margin:0; color:#cfc7ba;}'
      + '[data-chummer-board-failure] nav{display:flex; flex-wrap:wrap; gap:0.55rem; margin-top:0.85rem;}'
      + '[data-chummer-board-failure] a{display:inline-flex; align-items:center; padding:0.45rem 0.7rem; border:1px solid rgba(238,232,222,0.14); border-radius:999px; background:rgba(238,232,222,0.05); color:inherit; text-decoration:none;}'
      + '</style>'
      + '<h2>__CHUMMER_FAILURE_TITLE__</h2>'
      + '<p>__CHUMMER_FAILURE_SUMMARY__</p>'
      + '<nav aria-label="Board recovery actions">'
      + '<a href="__CHUMMER_FAILURE_PRIMARY_HREF__" target="_top" rel="noopener">__CHUMMER_FAILURE_PRIMARY_LABEL__</a>'
      + '<a href="__CHUMMER_FAILURE_SECONDARY_HREF__" target="_top" rel="noopener">__CHUMMER_FAILURE_SECONDARY_LABEL__</a>'
      + '<a href="__CHUMMER_FAILURE_RETURN_HREF__" target="_top" rel="noopener">__CHUMMER_FAILURE_RETURN_LABEL__</a>'
      + '</nav>';

    const host = document.querySelector('main') || document.body;
    if (!host) {
      return null;
    }

    host.prepend(panel);
    return panel;
  };

  const suppressHostedError = function () {
    const nodes = Array.from(document.querySelectorAll('main, section, article, div, p, span, h1, h2, h3'));
    let found = false;

    nodes.forEach(function (node) {
      const text = (node.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase();
      if (!text) {
        return;
      }

      const matches = errorPhrases.some(function (phrase) {
        return text.includes(phrase);
      });

      if (!matches) {
        return;
      }

      found = true;
      if (node instanceof HTMLElement) {
        node.style.display = 'none';
      }
    });

    if (found) {
      ensureFailurePanel();
    }
  };

  suppressHostedError();
  const observer = new MutationObserver(function () {
    suppressHostedError();
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
});
</script>
"""
                .Replace("__CHUMMER_FAILURE_TITLE__", JavaScriptEncoder.Default.Encode(failureTitle), StringComparison.Ordinal)
                .Replace("__CHUMMER_FAILURE_SUMMARY__", JavaScriptEncoder.Default.Encode(failureSummary), StringComparison.Ordinal)
                .Replace("__CHUMMER_FAILURE_PRIMARY_HREF__", failurePrimaryHref, StringComparison.Ordinal)
                .Replace("__CHUMMER_FAILURE_PRIMARY_LABEL__", JavaScriptEncoder.Default.Encode(failurePrimaryLabel), StringComparison.Ordinal)
                .Replace("__CHUMMER_FAILURE_SECONDARY_HREF__", failureSecondaryHref, StringComparison.Ordinal)
                .Replace("__CHUMMER_FAILURE_SECONDARY_LABEL__", JavaScriptEncoder.Default.Encode(failureSecondaryLabel), StringComparison.Ordinal)
                .Replace("__CHUMMER_FAILURE_RETURN_HREF__", failureReturnHref, StringComparison.Ordinal)
                .Replace("__CHUMMER_FAILURE_RETURN_LABEL__", JavaScriptEncoder.Default.Encode(failureReturnLabel), StringComparison.Ordinal);

            if (rewritten.Contains("</head>", StringComparison.OrdinalIgnoreCase))
            {
                rewritten = Regex.Replace(
                    rewritten,
                    "</head>",
                    $"{boardSkin}{homeLinkPatch}{boardFailurePatch}</head>",
                    RegexOptions.IgnoreCase,
                    TimeSpan.FromMilliseconds(250));
            }
            else
            {
                rewritten = boardSkin + homeLinkPatch + boardFailurePatch + rewritten;
            }
        }

        rewritten = Regex.Replace(
            rewritten,
            "<!--.*?ProductLift.*?-->",
            string.Empty,
            RegexOptions.IgnoreCase | RegexOptions.Singleline,
            TimeSpan.FromMilliseconds(250));
        rewritten = Regex.Replace(
            rewritten,
            "<meta[^>]+name=\"generator\"[^>]*>",
            string.Empty,
            RegexOptions.IgnoreCase,
            TimeSpan.FromMilliseconds(250));
        rewritten = RemoveHostedBoardAuthLinks(rewritten);
        rewritten = RemoveHostedBoardProviderChrome(rewritten);
        rewritten = ReplaceHostedBoardVisibleBrandText(rewritten);
        rewritten = rewritten.Replace("productlift-", "board-", StringComparison.OrdinalIgnoreCase);
        rewritten = rewritten.Replace("ProductLift.dev", "Chummer", StringComparison.OrdinalIgnoreCase);
        rewritten = rewritten.Replace("Powered by ProductLift", "Hosted by Chummer", StringComparison.OrdinalIgnoreCase);
        rewritten = RewriteHostedBoardAssetHosts(rewritten, assetProxyBasePath);

        return rewritten;
    }

    private static string RemoveHostedBoardAuthLinks(string html)
    {
        if (string.IsNullOrWhiteSpace(html))
        {
            return string.Empty;
        }

        return Regex.Replace(
            html,
            @"<a\b(?=[^>]*\bhref\s*=\s*(?:""[^""]*(?:login|signin|sign-in|signup|sign-up|register)[^""]*""|'[^']*(?:login|signin|sign-in|signup|sign-up|register)[^']*'|[^\s>]*(?:login|signin|sign-in|signup|sign-up|register)[^\s>]*))[^>]*>.*?</a>",
            string.Empty,
            RegexOptions.IgnoreCase | RegexOptions.Singleline,
            TimeSpan.FromMilliseconds(250));
    }

    private static string ReplaceHostedBoardVisibleBrandText(string html)
    {
        string rewritten = Regex.Replace(
            html,
            @">(\s*)ProductLift(\s*)<",
            ">$1Chummer$2<",
            RegexOptions.IgnoreCase,
            TimeSpan.FromMilliseconds(250));
        return Regex.Replace(
            rewritten,
            @"\b(aria-label|title)\s*=\s*(""|')ProductLift\2",
            "$1=$2Chummer$2",
            RegexOptions.IgnoreCase,
            TimeSpan.FromMilliseconds(250));
    }

    private static string RemoveHostedBoardProviderChrome(string html)
    {
        if (string.IsNullOrWhiteSpace(html))
        {
            return string.Empty;
        }

        string rewritten = Regex.Replace(
            html,
            @"<li\b(?=[^>]*\bclass\s*=\s*(?:""[^""]*\bnav-item\b[^""]*""|'[^']*\bnav-item\b[^']*'|[^\s>]*\bnav-item\b[^\s>]*))[^>]*>(?:(?!</li>).)*\bglobal-search-trigger(?:-mobile)?\b(?:(?!</li>).)*</li>",
            string.Empty,
            RegexOptions.IgnoreCase | RegexOptions.Singleline,
            TimeSpan.FromMilliseconds(250));

        rewritten = Regex.Replace(
            rewritten,
            @"<a\b(?=[^>]*\bid\s*=\s*(?:""global-search-trigger(?:-mobile)?""|'global-search-trigger(?:-mobile)?'|global-search-trigger(?:-mobile)?))[^>]*>[\s\S]*?</a>",
            string.Empty,
            RegexOptions.IgnoreCase | RegexOptions.Singleline,
            TimeSpan.FromMilliseconds(250));

        rewritten = Regex.Replace(
            rewritten,
            @"<button\b(?=[^>]*(?:\blogin\b|\bsignup\b|\bsign-up\b|\bsignin\b|\bsign-in\b|\bregister\b))[^>]*>[\s\S]*?</button>",
            string.Empty,
            RegexOptions.IgnoreCase | RegexOptions.Singleline,
            TimeSpan.FromMilliseconds(250));

        return Regex.Replace(
            rewritten,
            @"<div\b(?=[^>]*\bid\s*=\s*(?:""imageModal""|'imageModal'|imageModal))[^>]*>[\s\S]*?</div>\s*</div>\s*</div>\s*</div>",
            string.Empty,
            RegexOptions.IgnoreCase | RegexOptions.Singleline,
            TimeSpan.FromMilliseconds(250));
    }

    private static bool HostedBoardHtmlLooksUnavailable(string html)
    {
        if (string.IsNullOrWhiteSpace(html))
        {
            return true;
        }

        ReadOnlySpan<string> phrases =
        [
            "something went wrong on our side",
            "could not load posts",
            "network error while loading tab configuration",
            string.Concat("please try again or contact ", "support@", "productlift.dev")
        ];

        foreach (string phrase in phrases)
        {
            if (html.Contains(phrase, StringComparison.OrdinalIgnoreCase))
            {
                return true;
            }
        }

        return false;
    }

    private static string RewriteHostedBoardAssetHosts(string html, string assetProxyBasePath)
    {
        string providerDomain = string.Concat("product", "lift.dev");
        string rewritten = Regex.Replace(
            html,
            $"https://(?<assetHost>media|cdn)\\.{Regex.Escape(providerDomain)}(?=[/\"'>\\s])",
            match => $"{assetProxyBasePath}/{match.Groups["assetHost"].Value}",
            RegexOptions.IgnoreCase,
            TimeSpan.FromMilliseconds(250));
        return Regex.Replace(
            rewritten,
            @"https://(?<assetHost>media|cdn)\.chummer(?=[/""'>\s])",
            match => $"{assetProxyBasePath}/{match.Groups["assetHost"].Value}",
            RegexOptions.IgnoreCase,
            TimeSpan.FromMilliseconds(250));
    }

    private static string RewriteParticipateBoardHtml(string html, Uri upstream, string publicHomeHref, string? supporterHref)
        => RewriteHostedBoardHtml(
            html,
            upstream,
            publicHomeHref,
            supporterHref,
            localOrigin: "/participate/board",
            localBaseHref: "/participate/board/",
            railTitle: "Chummer Participate",
            railNavLabel: "Participate actions",
            firstLinkHref: "/roadmap",
            firstLinkLabel: "Roadmap",
            secondLinkHref: "/participate",
            secondLinkLabel: "Board",
            canonicalHref: "/participate/board",
            assetProxyBasePath: "/participate/provider-assets",
            pageTitle: "Participate - Chummer.run",
            hostedHeadingReplacement: "What should Chummer do next?",
            hostedSummaryReplacement: "Short requests, clear bugs, useful ideas.",
            hostedPrimaryActionReplacement: "Add a note",
            hostedLeadReplacement: "Tell us what would help.",
            applyFeedbackPolish: true,
            failureTitle: "The board is unavailable",
            failureSummary: "Try again shortly. Use Support only for private or blocked issues.",
            failurePrimaryHref: "/roadmap",
            failurePrimaryLabel: "Roadmap",
            failureSecondaryHref: "/contact#support-intake",
            failureSecondaryLabel: "Support",
            failureReturnHref: "/participate",
            failureReturnLabel: "Retry");

    private string? ResolveParticipateSupporterHref()
    {
        BrilliantDirectoriesBillingService? billing = HttpContext?.RequestServices.GetService<BrilliantDirectoriesBillingService>();
        try
        {
            if (billing is null)
            {
                return "/account/billing";
            }

            _ = billing.GetPage();
            return "/account/billing/supporter/start";
        }
        catch (InvalidOperationException)
        {
            return null;
        }
    }

    private void CopySafeProxyHeaders(HttpResponseMessage response)
    {
        foreach (var header in response.Headers)
        {
            if (string.Equals(header.Key, "transfer-encoding", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "location", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "set-cookie", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "connection", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "keep-alive", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "proxy-authenticate", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "proxy-authorization", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "te", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "trailer", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "upgrade", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "content-security-policy", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "x-frame-options", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            Response.Headers[header.Key] = header.Value.ToArray();
        }

        foreach (var header in response.Content.Headers)
        {
            if (string.Equals(header.Key, "content-security-policy", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "set-cookie", StringComparison.OrdinalIgnoreCase)
                || string.Equals(header.Key, "x-frame-options", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }

            Response.Headers[header.Key] = header.Value.ToArray();
        }

        Response.Headers.Remove("transfer-encoding");
    }

    [HttpGet("/participate/build-ghosts")]
    [Produces("text/html")]
    public async Task<IActionResult> BuildGhostConciergePage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/BuildGhostConcierge.cshtml", await BuildBuildGhostConciergePageModel(cancellationToken));

    [HttpGet("/alice")]
    [Produces("text/html")]
    public async Task<IActionResult> AlicePage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/BuildGhostConcierge.cshtml", await BuildBuildGhostConciergePageModel(cancellationToken, currentPath: "/alice", title: "Character help", eyebrow: "Build help", heading: "Character help", intro: "Use character help when you want a guided build plan, tradeoff notes, legality explanations, or a clean way to discard and apply suggested changes." ));

    [HttpGet("/participate/build-ghosts.json")]
    [Produces("application/json")]
    public IActionResult BuildGhostConciergeJson()
        => Ok(_buildGhostConcierge.Build());

    [HttpGet("/alice/receipts/build-ghost.json")]
    [Produces("application/json")]
    public IActionResult AliceReceiptJson()
    {
        BuildGhostConciergeProjection projection = _buildGhostConcierge.Build();
        return Ok(new
        {
            projection.FacePopEntryHref,
            projection.FacePopStatus,
            projection.AnswerlyStatus,
            projection.EngineStatus,
            projection.HumanizedSummary,
            projection.CanonicalLane,
            projection.RuntimeBoundary,
            projection.FacePopResponsibilities,
            projection.AnswerlyResponsibilities,
            projection.ChummerResponsibilities,
            projection.CompareArtifacts,
            projection.Insights,
            projection.ClientReportHref,
            projection.PublicFeedbackHref,
            projection.Actions,
            SignedInBench = new
            {
                AccountEntryHref = "/account/alice",
                AccountRedirectHref = "/account/alice/open",
                AccountFallbackHref = "/account/work",
                HandoffDetailHrefTemplate = "/account/alice/{handoffId}",
                HandoffIndexApiHref = "/api/v1/campaign-spine/me/build-handoffs",
                HandoffDetailApiHrefTemplate = "/api/v1/campaign-spine/me/build-handoffs/{handoffId}",
                Summary = "Signed-in character help keeps compare history, planner coverage, tradeoffs, and apply-safe outputs attached to the account."
            }
        });
    }

    [HttpGet("/docs")]
    [Produces("text/html")]
    public async Task<IActionResult> DocumentPortalPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/TrustPage.cshtml", await BuildDocumentPortalHomePageModel(cancellationToken));

    [HttpGet("/docs/{slug}/receipts/publication.json")]
    [Produces("application/json")]
    public IActionResult DocumentPortalPublicationReceipt([FromRoute] string slug)
    {
        var document = _flipLinkDocumentPortal.TryGetPublicDocument(slug);
        var publication = document is null ? null : _flipLinkDocumentPortal.TryGetPublication(document.Id);
        var receipt = _flipLinkDocumentPortal.TryBuildPublicationReceipt(slug);

        if (document is null || publication is null || receipt is null)
        {
            return NotFound();
        }

        return Json(new
        {
            document,
            publication,
            receipt,
            routePublicationStatus = document.Status,
            externalViewerPublicationStatus = publication.PublicationStatus,
            externalViewerRequired = false,
            readinessPosture = DocumentPortalReadinessPostures.OperatorManagedRouteReady,
            truthOwner = "chummer",
            viewerPosture = DocumentPortalReadinessPostures.OperatorManagedViewerOptional
        });
    }

    [HttpGet("/docs/category/{category}")]
    [Produces("text/html")]
    public async Task<IActionResult> DocumentPortalCategoryPage([FromRoute] string category, CancellationToken cancellationToken)
    {
        var documents = _flipLinkDocumentPortal.ListCategoryDocuments(category);
        if (documents.Count == 0)
        {
            return NotFound();
        }

        return View("~/Views/PublicLanding/TrustPage.cshtml", await BuildDocumentPortalQuickstartCategoryPageModel(documents[0], cancellationToken));
    }

    [HttpGet("/docs/embed/{slug}")]
    [Produces("text/html")]
    public async Task<IActionResult> DocumentPortalEmbedPage([FromRoute] string slug, CancellationToken cancellationToken)
    {
        var document = _flipLinkDocumentPortal.TryGetPublicDocument(slug);
        if (document is null)
        {
            return NotFound();
        }

        return View("~/Views/PublicLanding/TrustPage.cshtml", await BuildDocumentPortalEmbedBoundaryPageModel(document, cancellationToken));
    }

    [HttpGet("/docs/{slug}/download.pdf")]
    [Produces("application/pdf")]
    public IActionResult DocumentPortalPdfDownload([FromRoute] string slug)
    {
        var artifact = _flipLinkDocumentPortal.TryBuildPdfArtifact(slug);
        if (artifact is null)
        {
            return NotFound();
        }

        return File(artifact.Bytes, artifact.ContentType, artifact.FileName);
    }

    [HttpGet("/docs/{slug}/source.md")]
    [Produces("text/markdown")]
    public IActionResult DocumentPortalSourceDownload([FromRoute] string slug)
    {
        var artifact = _flipLinkDocumentPortal.TryBuildSourceArtifact(slug);
        if (artifact is null)
        {
            return NotFound();
        }

        return File(artifact.Bytes, artifact.ContentType, artifact.FileName);
    }

    [HttpGet("/docs/{slug}")]
    [Produces("text/html")]
    public async Task<IActionResult> DocumentPortalDetailPage([FromRoute] string slug, CancellationToken cancellationToken)
    {
        var document = _flipLinkDocumentPortal.TryGetPublicDocument(slug);
        if (document is null)
        {
            return NotFound();
        }

        return View("~/Views/PublicLanding/TrustPage.cshtml", await BuildDocumentPortalQuickstartPageModel(document, cancellationToken));
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

    [HttpGet("/roadmap/knowledge-fabric")]
    public IActionResult KnowledgeFabricRoadmapAlias()
        => Redirect("/rules");

    [HttpGet("/knowledge")]
    public IActionResult KnowledgeAliasPage()
        => Redirect("/rules");

    [HttpGet("/rules/explanations")]
    [HttpGet("/rules/receipts")]
    [Produces("application/json")]
    public IActionResult KnowledgeFabricReceiptIndex()
        => Content(_knowledgeFabric.BuildIndexJson(), "application/json");

    [HttpGet("/rules/explanations/{receiptId}.json")]
    [HttpGet("/rules/receipts/{receiptId}.json")]
    [Produces("application/json")]
    public IActionResult KnowledgeFabricReceiptJson([FromRoute] string receiptId)
        => Content(_knowledgeFabric.BuildReceiptJson(receiptId), "application/json");

    [HttpGet("/play/continuity")]
    [Produces("text/html")]
    public async Task<IActionResult> ContinuityPreviewPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/NexusPanContinuity.cshtml", await BuildNexusPanContinuityPageModel(cancellationToken));

    [HttpGet("/roadmap/nexus-pan")]
    public IActionResult NexusPanRoadmapAlias()
        => Redirect("/play/continuity");

    [HttpGet("/play/continuity/history")]
    [HttpGet("/play/continuity/receipts")]
    [Produces("application/json")]
    public IActionResult NexusPanReceiptIndex()
        => Content(_nexusPan.BuildIndexJson(), "application/json");

    [HttpGet("/play/continuity/history/{receiptId}.json")]
    [HttpGet("/play/continuity/receipts/{receiptId}.json")]
    [Produces("application/json")]
    public IActionResult NexusPanReceiptJson([FromRoute] string receiptId)
        => Content(_nexusPan.BuildReceiptJson(receiptId), "application/json");

    [HttpGet("/table-pulse")]
    [Produces("text/html")]
    public async Task<IActionResult> TablePulsePage(CancellationToken cancellationToken)
    {
        TrustPageViewModel model = await BuildHorizonPreviewPageModel(
            pageId: "table-pulse",
            title: "TABLE PULSE",
            description: "Live heat and GM-private aftermath stay separate.",
            currentPath: "/table-pulse",
            eyebrow: "Live table",
            heading: "TABLE PULSE",
            intro: "TABLE PULSE is now a real product surface, not just a redirect. Live pressure stays in the account inbox. Private aftermath stays separate so heat, recap, and next steps do not collapse into surveillance or vague drama text.",
            sections:
            [
                new TrustPageSectionViewModel(
                    "table_pulse_live",
                    "Live table",
                    "What is live now",
                    "The live view is the in-world signal and reaction system.",
                    [
                        "GM-controlled heat updates in the account inbox.",
                        "Remote reactions wait for explicit GM adjudication.",
                        "World pressure remains inspectable before it affects the wider city."
                    ]),
                new TrustPageSectionViewModel(
                    "table_pulse_aftermath",
                    "Aftermath",
                    "What aftermath owns",
                    "Aftermath is a separate private recap and carry-forward system for the GM.",
                    [
                        "Workspace aftermath recaps stay attached.",
                        "Downtime, carry-forward, and campaign-memory cues stay in one clear return path.",
                        "Aftermath is private GM recap and next-step work, not public scoring or moderation."
                    ]),
                new TrustPageSectionViewModel(
                    "table_pulse_boundary",
                    "Boundary",
                    "What this feature does not claim",
                    "The live view and aftermath stay deliberately separate.",
                    [
                        "No automatic canon mutation.",
                        "No player surveillance or public trust scoring.",
                        "No claim that an external coach outranks Chummer campaign state."
                    ])
            ],
            actions:
            [
                new TrustPageActionViewModel("Open live notifications", "/account/ledger/notifications", "primary"),
                new TrustPageActionViewModel("Open aftermath", "/table-pulse/debrief", "secondary"),
                new TrustPageActionViewModel("Open Black Ledger", "/ledger", "ghost")
            ],
            cancellationToken: cancellationToken,
            summaryPoints:
            [
                "Live heat updates are real now",
                "Private aftermath recaps are real now",
                "Live play and aftermath stay separate on purpose"
            ],
            horizonCapability: BuildPublicHorizonCapability(
                "table-pulse",
                "debrief_packet",
                "table-pulse:live-and-aftermath"));
        return View("~/Views/PublicLanding/TrustPage.cshtml", model);
    }

    [HttpGet("/table-pulse/receipts/live-and-aftermath.json")]
    [Produces("application/json")]
    public IActionResult TablePulseReceiptJson()
        => Ok(new
        {
            Horizon = "table_pulse",
            Status = "shipped_mvp",
            SeparationStatus = "pass",
            LiveRail = new
            {
                Status = "live",
                NotificationsHref = "/account/ledger/notifications",
                ReactionPostHref = "/account/ledger/notifications/table-pulse/react",
                Summary = "GM-controlled heat updates, remote reactions, and adjudicated fallout stay in the account inbox."
            },
            AftermathRail = new
            {
                Status = "live",
                WorkspaceHref = "/account/work#aftermath-packages",
                ApiRoutes = new[]
                {
                    "/api/v1/campaign-spine/me/workspaces/{workspaceId}/aftermath-recap-packages",
                    "/api/v1/campaign-spine/me/workspaces/{workspaceId}/downtime-aftermath"
                },
                Summary = "Private aftermath recap, downtime carry-forward, and campaign-memory next steps remain separate from the live path."
            },
            Boundaries = new[]
            {
                "no_automatic_world_changes",
                "no_player_scoring",
                "no_public_surveillance"
            },
            SharedArtifacts = BuildSharedArtifactSurfaceRoutes("table-pulse", "debrief_packet"),
            ArtifactCapability = BuildPublicHorizonCapability(
                "table-pulse",
                "debrief_packet",
                "table-pulse:live-and-aftermath")
        });

    [HttpGet("/origin-dossier")]
    [Produces("text/html")]
    public async Task<IActionResult> OriginDossierPage(CancellationToken cancellationToken)
    {
        TrustPageViewModel model = await BuildHorizonPreviewPageModel(
            pageId: "origin-dossier",
            title: "Origin Dossier",
            description: "Story-first runner canon, bounded media, and no silent mechanics mutation.",
            currentPath: "/origin-dossier",
            eyebrow: "Runner origin",
            heading: "Origin Dossier",
            intro: "Origin Dossier turns an approved runner backstory into a readable story packet before it becomes a video, audiobook, or later ALICE context. The story stays first. The sheet stays authoritative.",
            sections:
            [
                new TrustPageSectionViewModel(
                    "origin_story_first",
                    "Story first",
                    "What the player sees first",
                    "The first artifact should be a readable story packet the player and GM can approve together before the run continues into later media or follow-up help.",
                    [
                        "Readable story packet before later media.",
                        "Approved canon stays separate from mechanics.",
                        "Player and GM can review the same text."
                    ]),
                new TrustPageSectionViewModel(
                    "origin_bundle",
                    "Next",
                    "Where the story can continue",
                    "Once the story is approved, the same source can continue into a bounded media bundle without turning narration, portraits, or video into character authority.",
                    [
                        "PDF booklet.",
                        "Narrated overview and later audiobook lane.",
                        "Portrait, scene, and video packet lineage."
                    ]),
                new TrustPageSectionViewModel(
                    "origin_boundary",
                    "Boundary",
                    "What this lane does not get to do",
                    "Origin Dossier can shape presentation and later context, but it does not get to smuggle in ware, qualities, availability exceptions, or other mechanics changes.",
                    [
                        "No silent sheet edits.",
                        "No automatic legality claims.",
                        "No media provider becomes mechanics authority."
                    ])
            ],
            actions:
            [
                new TrustPageActionViewModel("Open the story booklet", "/docs/origin-dossier-the-name-she-chose", "primary"),
                new TrustPageActionViewModel("Read the book-studio design", "/docs/origin-book-studio", "secondary"),
                new TrustPageActionViewModel("Watch the narrated overview", "/origin-dossier/media", "secondary"),
                new TrustPageActionViewModel("Download the booklet PDF", "/docs/origin-dossier-the-name-she-chose/download.pdf", "ghost")
            ],
            cancellationToken: cancellationToken,
            summaryPoints:
            [
                "Story before media",
                "Approved canon stays bounded",
                "The sheet remains authoritative"
            ],
            horizonCapability: BuildPublicHorizonCapability(
                "origin-dossier",
                "dossier_media",
                "origin-dossier:public-story-packet"));
        return View("~/Views/PublicLanding/TrustPage.cshtml", model);
    }

    [HttpGet("/origin-dossier/story-network")]
    [HttpGet("/origin-dossier/receipts/story-network.json")]
    [Produces("application/json")]
    public IActionResult OriginDossierReceiptJson()
        => Ok(new
        {
            Horizon = "origin-dossier",
            Status = "shipped_mvp",
            PublicBoard = new
            {
                StoryBookletHref = "/docs/origin-dossier-the-name-she-chose",
                StoryBookletPdfHref = "/docs/origin-dossier-the-name-she-chose/download.pdf",
                MediaDispatchHref = "/origin-dossier/media",
                BookStudioHref = "/docs/origin-book-studio",
                Summary = "Origin Dossier keeps the approved story packet first, then widens into bounded media on first-party routes."
            },
            SharedArtifacts = BuildSharedArtifactSurfaceRoutes("origin-dossier", "dossier_media"),
            ArtifactCapability = BuildPublicHorizonCapability(
                "origin-dossier",
                "dossier_media",
                "origin-dossier:public-story-packet"),
            Boundary = new
            {
                StoryTruth = "approved_chummer_owned_packet",
                SilentMechanicsMutation = "not_claimed",
                ProviderTruth = "not_claimed"
            }
        });

    [HttpGet("/roadmap/origin-dossier")]
    public IActionResult OriginDossierRoadmapAlias()
        => Redirect("/origin-dossier");

    [HttpGet("/mobile/pwa.json")]
    [Produces("application/json")]
    public IActionResult MobilePwaJson()
        => Content(_nexusPan.BuildMobilePwaJson(), "application/json");

    [HttpGet("/jackpoint")]
    [Produces("text/html")]
    public async Task<IActionResult> JackpointPreviewPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildJackpointPageModel(cancellationToken));

    [HttpGet("/jackpoint/briefing-network")]
    [HttpGet("/jackpoint/receipts/briefing-network.json")]
    [Produces("application/json")]
    public IActionResult JackpointReceiptJson()
    {
        IReadOnlyList<MediaArtifactDocument> briefings = _mediaHorizons?.ListJackpointBriefings() ?? Array.Empty<MediaArtifactDocument>();
        string firstBriefingMarkdownHref = briefings.FirstOrDefault()?.MarkdownRoute ?? "/jackpoint/briefings/emerald-sprawl-briefing.md";
        string firstBriefingJsonHref = briefings.FirstOrDefault()?.JsonRoute ?? "/jackpoint/briefings/emerald-sprawl-briefing.json";
        return Ok(new
        {
            Horizon = "jackpoint",
            Status = "shipped_mvp",
            PublicBoard = new
            {
                FirstBriefingMarkdownHref = firstBriefingMarkdownHref,
                FirstBriefingJsonHref = firstBriefingJsonHref,
                BriefingCount = briefings.Count == 0 ? 2 : briefings.Count,
                Summary = "Public JACKPOINT keeps player-safe briefing and dossier packets on Chummer markdown and JSON."
            },
            SignedInDesk = new
            {
                AccountEntryHref = "/account/jackpoint",
                AccountRedirectHref = "/account/jackpoint/open",
                AccountPublicationHrefTemplate = "/account/jackpoint/{publicationId}",
                PublicationIndexApiHref = "/api/v1/campaign-spine/me/publications",
                PublicationDetailApiHrefTemplate = "/api/v1/campaign-spine/me/publications/{publicationId}",
                ArtifactDetailHrefTemplate = "/artifacts/publications/{publicationId}",
                Summary = "Signed-in JACKPOINT keeps publication review, public publication status, and campaign-return publication history inside Chummer."
            },
            SharedArtifacts = BuildSharedArtifactSurfaceRoutes("jackpoint", "briefing_video"),
            ArtifactCapability = BuildPublicHorizonCapability(
                "jackpoint",
                "briefing_video",
                "jackpoint:briefing-network"),
            Boundary = new
            {
                PublicAudience = "player_safe_only",
                GmSpoilerPackets = "signed_in_only",
                PublicationTruth = "chummer_owned",
                ExternalNarrationAuthority = "not_claimed"
            }
        });
    }

    [HttpGet("/jackpoint/briefings/{briefingId}.md")]
    [Produces("text/markdown")]
    public IActionResult JackpointBriefingMarkdown([FromRoute] string briefingId)
        => Content(_mediaHorizons.BuildDocumentMarkdown(_mediaHorizons.GetJackpointBriefing(briefingId), "JACKPOINT", "Player-safe dossier and mission-brief output only. GM-private spoiler packets stay off the public page."), "text/markdown");

    [HttpGet("/jackpoint/briefings/{briefingId}.json")]
    [Produces("application/json")]
    public IActionResult JackpointBriefingJson([FromRoute] string briefingId)
        => Content(_mediaHorizons.BuildDocumentJson(_mediaHorizons.GetJackpointBriefing(briefingId), "jackpoint", "Player-safe dossier and mission-brief output only. GM-private spoiler packets stay off the public page."), "application/json");

    [HttpGet("/briefings")]
    public IActionResult BriefingsAliasPage()
        => Redirect("/jackpoint");

    [HttpGet("/roadmap/jackpoint")]
    public IActionResult JackpointRoadmapAlias()
        => Redirect("/jackpoint");

    [HttpGet("/runsites")]
    [Produces("text/html")]
    public async Task<IActionResult> RunsitePreviewPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildRunsitePageModel(cancellationToken));

    [HttpGet("/runsites/prep-network")]
    [HttpGet("/runsites/receipts/prep-network.json")]
    [Produces("application/json")]
    public IActionResult RunsiteReceiptJson()
    {
        IReadOnlyList<MediaArtifactDocument> packs = _mediaHorizons?.ListRunsitePacks() ?? Array.Empty<MediaArtifactDocument>();
        MediaArtifactDocument? firstPack = packs.FirstOrDefault();
        string firstPackMarkdownHref = firstPack?.MarkdownRoute ?? "/runsites/packs/redmond-dockyard-pack.md";
        string firstPackJsonHref = firstPack?.JsonRoute ?? "/runsites/packs/redmond-dockyard-pack.json";
        return Ok(new
        {
            Horizon = "runsite",
            Status = "shipped_mvp",
            PublicBoard = new
            {
                FirstPackMarkdownHref = firstPackMarkdownHref,
                FirstPackJsonHref = firstPackJsonHref,
                PackCount = packs.Count == 0 ? 2 : packs.Count,
                Summary = "Public RUNSITE keeps inspectable packs, routes, and threat clocks visible before signed-in prep opens."
            },
            SignedInBench = new
            {
                AccountEntryHref = "/account/runsites",
                AccountRedirectHref = "/account/runsites/open",
                AccountWorkspaceHrefTemplate = "/account/runsites/{workspaceId}",
                WorkspaceIndexApiHref = "/api/v1/campaign-spine/me/workspace-digests",
                WorkspaceDetailApiHrefTemplate = "/api/v1/campaign-spine/me/workspaces/{workspaceId}",
                PrepLibraryApiHrefTemplate = "/api/v1/campaign-spine/me/workspaces/{workspaceId}/prep-library",
                RunIndexApiHref = "/api/v1/campaign-spine/me/runs",
                RunDetailApiHrefTemplate = "/api/v1/campaign-spine/me/runs/{runId}",
                Summary = "Signed-in RUNSITE keeps workspace prep, runboard continuity, and prep-library launch inside Chummer."
            },
            SharedArtifacts = BuildSharedArtifactSurfaceRoutes("runsite", "tour"),
            ArtifactCapability = BuildPublicHorizonCapability(
                "runsite",
                "tour",
                "runsite:prep-network"),
            Boundary = new
            {
                TacticalAuthority = "not_claimed",
                VttReplacement = "not_claimed",
                PrepTruth = "chummer_workspace_and_run_paths",
                ProviderTours = "secondary_only"
            }
        });
    }

    [HttpGet("/runsites/packs/{packId}.md")]
    [Produces("text/markdown")]
    public IActionResult RunsitePackMarkdown([FromRoute] string packId)
        => Content(_mediaHorizons.BuildDocumentMarkdown(_mediaHorizons.GetRunsitePack(packId), "RUNSITE", "Spatial-prep guide only. This route does not claim a full overlay, VTT, or tactical control stack."), "text/markdown");

    [HttpGet("/runsites/packs/{packId}.json")]
    [Produces("application/json")]
    public IActionResult RunsitePackJson([FromRoute] string packId)
        => Content(_mediaHorizons.BuildDocumentJson(_mediaHorizons.GetRunsitePack(packId), "runsite", "Spatial-prep guide only. This route does not claim a full overlay, VTT, or tactical control stack."), "application/json");

    [HttpGet("/runsites/packs/{packId}/tour")]
    public async Task<IActionResult> RunsiteTourDispatch([FromRoute] string packId, CancellationToken cancellationToken)
        => await DispatchHorizonArtifactAsync(
            operationLabel: "runsite tour",
            dispatchRoute: $"/runsites/packs/{Uri.EscapeDataString(packId)}/tour",
            sourceId: packId,
            horizonId: "runsite",
            artifactKindOrCapabilityId: "tour",
            emitRunsiteHeaders: true,
            resolveSource: _mediaHorizons.GetRunsitePack,
            resolveDispatchTarget: static document => document.DispatchTargetHref ?? document.TourHref,
            quotaAllowanceExhaustedMessage: "3D-tour allowance is exhausted for this week.",
            fallbackQuotaUnavailableMessage: "Unable to confirm 3D-tour allowance receipt right now.",
            cancellationToken: cancellationToken);

    [HttpGet("/propertyquarry")]
    [Produces("text/html")]
    public async Task<IActionResult> PropertyquarryPreviewPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildPropertyquarryPageModel(cancellationToken));

    [HttpGet("/propertyquarry/property-network")]
    [HttpGet("/propertyquarry/receipts/property-network")]
    [HttpGet("/propertyquarry/receipts/property-network.json")]
    [Produces("application/json")]
    public IActionResult PropertyquarryReceiptJson()
    {
        IReadOnlyList<MediaArtifactDocument> properties = _mediaHorizons?.ListPropertyquarryProperties() ?? Array.Empty<MediaArtifactDocument>();
        MediaArtifactDocument? firstProperty = properties.FirstOrDefault();
        string firstPropertyMarkdownHref = firstProperty?.MarkdownRoute ?? "/propertyquarry/properties/northbound-research-lab.md";
        string firstPropertyJsonHref = firstProperty?.JsonRoute ?? "/propertyquarry/properties/northbound-research-lab.json";
        return Ok(new
        {
            Horizon = "propertyquarry",
            Status = "shipped_mvp",
            PublicBoard = new
            {
                FirstPropertyMarkdownHref = firstPropertyMarkdownHref,
                FirstPropertyJsonHref = firstPropertyJsonHref,
                PropertyCount = properties.Count == 0 ? 3 : properties.Count,
                Summary = "Public PROPERTYQUARRY keeps inspectable property packets, style markers, and 3D tour actions for GM prep."
            },
            SignedInDesk = new
            {
                AccountEntryHref = "/account/propertyquarry",
                AccountRedirectHref = "/account/propertyquarry/open",
                AccountWorkspaceHrefTemplate = "/account/propertyquarry/{propertyId}",
                PrepWorkspaceApiHrefTemplate = "/api/v1/campaign-spine/me/property-workspaces/{propertyId}",
                ContinuityApiHref = "/api/v1/campaign-spine/me/property-continuity/{propertyId}",
                Summary = "Signed-in PROPERTYQUARRY keeps selected property prep, continuity hooks, and workspace continuity behind account links."
            },
            SharedArtifacts = BuildSharedArtifactSurfaceRoutes("propertyquarry", "tour"),
            ArtifactCapability = BuildPublicHorizonCapability(
                "propertyquarry",
                "tour",
                "propertyquarry:property-network"),
            Boundary = new
            {
                TacticalAuthority = "not_claimed",
                TourTruth = "chummer_owned",
                PropertyTruth = "chummer_workspace_and_property_paths"
            }
        });
    }

    [HttpGet("/propertyquarry/properties/{propertyId}.md")]
    [Produces("text/markdown")]
    public IActionResult PropertyquarryPropertyMarkdown([FromRoute] string propertyId)
        => Content(_mediaHorizons.BuildDocumentMarkdown(_mediaHorizons.GetPropertyquarryProperty(propertyId), "PROPERTYQUARRY", "Player-safe property overview and scene-flow output only. GM-private investigation notes stay off the public page."), "text/markdown");

    [HttpGet("/propertyquarry/properties/{propertyId}.json")]
    [Produces("application/json")]
    public IActionResult PropertyquarryPropertyJson([FromRoute] string propertyId)
        => Content(_mediaHorizons.BuildDocumentJson(_mediaHorizons.GetPropertyquarryProperty(propertyId), "propertyquarry", "Player-safe property overview and scene-flow output only. GM-private investigation notes stay off the public page."), "application/json");

    [HttpGet("/propertyquarry/properties/{propertyId}/tour")]
    public async Task<IActionResult> PropertyquarryPropertyTourDispatch([FromRoute] string propertyId, CancellationToken cancellationToken)
        => await DispatchHorizonArtifactAsync(
            operationLabel: "propertyquarry property tour",
            dispatchRoute: $"/propertyquarry/properties/{Uri.EscapeDataString(propertyId)}/tour",
            sourceId: propertyId,
            horizonId: "propertyquarry",
            artifactKindOrCapabilityId: "tour",
            emitRunsiteHeaders: false,
            resolveSource: _mediaHorizons.GetPropertyquarryProperty,
            resolveDispatchTarget: static document => document.DispatchTargetHref ?? document.TourHref,
            quotaAllowanceExhaustedMessage: "3D-tour allowance is exhausted for this week.",
            fallbackQuotaUnavailableMessage: "Unable to confirm 3D-tour allowance receipt right now.",
            cancellationToken: cancellationToken);

    [HttpGet("/jackpoint/briefings/{briefingId}/video")]
    public async Task<IActionResult> JackpointBriefingVideoDispatch([FromRoute] string briefingId, CancellationToken cancellationToken)
        => await DispatchHorizonArtifactAsync(
            operationLabel: "jackpoint briefing video",
            dispatchRoute: $"/jackpoint/briefings/{Uri.EscapeDataString(briefingId)}/video",
            sourceId: briefingId,
            horizonId: "jackpoint",
            artifactKindOrCapabilityId: "briefing_video",
            emitRunsiteHeaders: false,
            resolveSource: _mediaHorizons.GetJackpointBriefing,
            resolveDispatchTarget: static document => document.DispatchTargetHref ?? document.TourHref,
            quotaAllowanceExhaustedMessage: "Briefing video allowance is exhausted for this week.",
            fallbackQuotaUnavailableMessage: "Unable to confirm briefing video allowance receipt right now.",
            cancellationToken: cancellationToken);

    [HttpGet("/runbook/primers/{primerId}/export")]
    public async Task<IActionResult> RunbookPrimerExportDispatch([FromRoute] string primerId, CancellationToken cancellationToken)
        => await DispatchHorizonArtifactAsync(
            operationLabel: "runbook primer export",
            dispatchRoute: $"/runbook/primers/{Uri.EscapeDataString(primerId)}/export",
            sourceId: primerId,
            horizonId: "runbook-press",
            artifactKindOrCapabilityId: "document_export",
            emitRunsiteHeaders: false,
            resolveSource: _mediaHorizons.GetRunbookPrimer,
            resolveDispatchTarget: static document => document.DispatchTargetHref ?? document.TourHref,
            quotaAllowanceExhaustedMessage: "Runbook export allowance is exhausted for this week.",
            fallbackQuotaUnavailableMessage: "Unable to confirm runbook export allowance receipt right now.",
            cancellationToken: cancellationToken);

    [HttpGet("/table-pulse/debrief")]
    public async Task<IActionResult> TablePulseDebriefDispatch(CancellationToken cancellationToken)
        => await DispatchResolvedHorizonArtifactAsync(
            operationLabel: "table pulse debrief",
            dispatchRoute: "/table-pulse/debrief",
            sourceId: "live-and-aftermath",
            sourceRef: "table-pulse:live-and-aftermath",
            horizonId: "table-pulse",
            artifactKindOrCapabilityId: "debrief_packet",
            dispatchTarget: "/account/work#aftermath-packages",
            emitRunsiteHeaders: false,
            quotaAllowanceExhaustedMessage: "Debrief packet allowance is exhausted for this week.",
            fallbackQuotaUnavailableMessage: "Unable to confirm debrief packet allowance receipt right now.",
            cancellationToken: cancellationToken);

    [HttpGet("/ledger/turns/{turn}/digest")]
    public async Task<IActionResult> BlackLedgerDigestDispatch([FromRoute] string turn, CancellationToken cancellationToken)
    {
        if (!int.TryParse(turn, out int requestedTurn) || requestedTurn < 0)
        {
            return NotFound();
        }

        if (BuildProtectedBlackLedgerWorldTurnBriefing(requestedTurn) is null)
        {
            return NotFound();
        }

        return await DispatchResolvedHorizonArtifactAsync(
            operationLabel: "black ledger digest",
            dispatchRoute: $"/ledger/turns/{Uri.EscapeDataString(turn)}/digest",
            sourceId: $"turn-{requestedTurn}",
            sourceRef: $"black-ledger:turn-{requestedTurn}:digest",
            horizonId: "black-ledger",
            artifactKindOrCapabilityId: "world_tick_digest",
            dispatchTarget: $"/ledger/turns/{requestedTurn}/newsreel.json",
            emitRunsiteHeaders: false,
            quotaAllowanceExhaustedMessage: "World tick digest allowance is exhausted for this week.",
            fallbackQuotaUnavailableMessage: "Unable to confirm world tick digest allowance receipt right now.",
            cancellationToken: cancellationToken);
    }

    [HttpGet("/origin-dossier/media")]
    public async Task<IActionResult> OriginDossierMediaDispatch(CancellationToken cancellationToken)
        => await DispatchResolvedHorizonArtifactAsync(
            operationLabel: "origin dossier media",
            dispatchRoute: "/origin-dossier/media",
            sourceId: "public-story-packet",
            sourceRef: "origin-dossier:public-story-packet",
            horizonId: "origin-dossier",
            artifactKindOrCapabilityId: "dossier_media",
            dispatchTarget: "/media/horizons/origin-dossier-the-name-she-chose-20260619.mp4",
            emitRunsiteHeaders: false,
            quotaAllowanceExhaustedMessage: "Dossier media allowance is exhausted for this week.",
            fallbackQuotaUnavailableMessage: "Unable to confirm dossier media allowance receipt right now.",
            cancellationToken: cancellationToken);

    [HttpGet("/participate/karma-forge/discovery")]
    public async Task<IActionResult> KarmaForgeDiscoveryPacketDispatch(CancellationToken cancellationToken)
        => await DispatchResolvedHorizonArtifactAsync(
            operationLabel: "karma forge discovery packet",
            dispatchRoute: "/participate/karma-forge/discovery",
            sourceId: "public-intake",
            sourceRef: "karma-forge:public-intake",
            horizonId: "karma-forge",
            artifactKindOrCapabilityId: "discovery_packet",
            dispatchTarget: "/participate/karma-forge",
            emitRunsiteHeaders: false,
            quotaAllowanceExhaustedMessage: "Discovery packet allowance is exhausted for this week.",
            fallbackQuotaUnavailableMessage: "Unable to confirm discovery packet allowance receipt right now.",
            cancellationToken: cancellationToken);

    private async Task<IActionResult> DispatchHorizonArtifactAsync(
        string operationLabel,
        string dispatchRoute,
        string sourceId,
        string horizonId,
        string artifactKindOrCapabilityId,
        bool emitRunsiteHeaders,
        Func<string, MediaArtifactDocument> resolveSource,
        Func<MediaArtifactDocument, string?> resolveDispatchTarget,
        string quotaAllowanceExhaustedMessage,
        string fallbackQuotaUnavailableMessage,
        CancellationToken cancellationToken)
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalSubjectAsync(cancellationToken);
        if (subject is null)
        {
            _logger.LogInformation("{Operation} dispatch rejected because no authenticated user was present for {SourceId}.", operationLabel, sourceId);
            return Redirect($"/login?next={Uri.EscapeDataString(dispatchRoute)}");
        }

        MediaArtifactDocument source;
        try
        {
            source = resolveSource(sourceId);
        }
        catch (KeyNotFoundException)
        {
            _logger.LogWarning("{Operation} dispatch requested unknown source {SourceId} for {HorizonId}.", operationLabel, sourceId, horizonId);
            return NotFound();
        }

        string? dispatchTarget = resolveDispatchTarget(source);
        if (string.IsNullOrWhiteSpace(dispatchTarget))
        {
            _logger.LogInformation("{Operation} dispatch skipped because {SourceId} has no configured target.", operationLabel, sourceId);
            return NotFound();
        }

        return await DispatchResolvedHorizonArtifactAsync(
            operationLabel,
            dispatchRoute,
            sourceId,
            $"{horizonId}:{sourceId}",
            horizonId,
            artifactKindOrCapabilityId,
            dispatchTarget,
            emitRunsiteHeaders,
            quotaAllowanceExhaustedMessage,
            fallbackQuotaUnavailableMessage,
            cancellationToken,
            authenticatedSubject: subject);
    }

    private async Task<IActionResult> DispatchResolvedHorizonArtifactAsync(
        string operationLabel,
        string dispatchRoute,
        string sourceId,
        string sourceRef,
        string horizonId,
        string artifactKindOrCapabilityId,
        string dispatchTarget,
        bool emitRunsiteHeaders,
        string quotaAllowanceExhaustedMessage,
        string fallbackQuotaUnavailableMessage,
        CancellationToken cancellationToken,
        AuthenticatedHubSubject? authenticatedSubject = null)
    {
        AuthenticatedHubSubject? subject = authenticatedSubject ?? await TryGetOptionalSubjectAsync(cancellationToken);
        if (subject is null)
        {
            _logger.LogInformation("{Operation} dispatch rejected because no authenticated user was present for {SourceId}.", operationLabel, sourceId);
            return Redirect($"/login?next={Uri.EscapeDataString(dispatchRoute)}");
        }

        HorizonArtifactQuotaSnapshot? dispatchQuota = null;
        if (_artifactRequests is not null)
        {
            try
            {
                HorizonArtifactRequestReceipt receipt = _artifactRequests.BuildRequest(
                    new HorizonArtifactRequestCreateRequest(
                        HorizonId: horizonId,
                        ArtifactKindOrCapabilityId: artifactKindOrCapabilityId,
                        UserId: subject.SubjectId,
                        SourceRef: sourceRef,
                        Visibility: "private",
                        ExternalProcessingConsent: true,
                        Email: subject.Email),
                    consumeQuota: true);

                if (!string.Equals(receipt.Status, "accepted", StringComparison.OrdinalIgnoreCase))
                {
                    _logger.LogWarning(
                        "{Operation} dispatch denied for {UserId} on {SourceId}; blocked reasons: {BlockedReasons}.",
                        operationLabel,
                        subject.SubjectId,
                        sourceId,
                        string.Join(", ", receipt.BlockedReasons));
                    if (receipt.BlockedReasons.Contains("artifact allowance", StringComparer.OrdinalIgnoreCase))
                    {
                        return Problem(statusCode: StatusCodes.Status429TooManyRequests, detail: quotaAllowanceExhaustedMessage);
                    }

                    return Problem(statusCode: StatusCodes.Status400BadRequest, detail: $"Unable to create a Chummer-owned {operationLabel} request receipt.");
                }

                HorizonArtifactQuotaSnapshot? receiptQuota = receipt.Quota;
                if (receipt.QuotaTracked && receiptQuota is null)
                {
                    _logger.LogWarning("{Operation} dispatch accepted without quota receipt for {UserId} on {SourceId}.", operationLabel, subject.SubjectId, sourceId);
                    return Problem(statusCode: StatusCodes.Status500InternalServerError, detail: fallbackQuotaUnavailableMessage);
                }

                Response.Headers["X-Horizon-Artifact-Quota-Tracked"] = receipt.QuotaTracked ? "true" : "false";
                if (receiptQuota is not null)
                {
                    dispatchQuota = receiptQuota;
                    Response.Headers["X-Horizon-Artifact-Quota-Limit"] = receiptQuota.WeeklyLimit.ToString(CultureInfo.InvariantCulture);
                    Response.Headers["X-Horizon-Artifact-Quota-Used"] = receiptQuota.WeeklyUsed.ToString(CultureInfo.InvariantCulture);
                    Response.Headers["X-Horizon-Artifact-Quota-Remaining"] = receiptQuota.WeeklyRemaining.ToString(CultureInfo.InvariantCulture);
                    Response.Headers["X-Horizon-Artifact-Allowance-Tier"] = receiptQuota.AllowanceTier;
                    Response.Headers["X-Horizon-Artifact-Entitlement-Basis"] = receiptQuota.EntitlementBasis;
                    Response.Headers["X-Horizon-Artifact-Entitlement-Scope"] = receiptQuota.EntitlementScope;
                }

                Response.Headers["X-Horizon-Artifact-Request-Id"] = receipt.RequestId;
                Response.Headers["X-Horizon-Artifact-Request-Href"] = $"/api/v1/horizons/artifact-requests/me/{Uri.EscapeDataString(receipt.RequestId)}";
            }
            catch (BrilliantDirectoriesBillingUnavailableException ex)
            {
                _logger.LogWarning(ex, "{Operation} dispatch failed because billing is unavailable for {UserId}/{SourceId}.", operationLabel, subject.SubjectId, sourceId);
                return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
            }
            catch (InvalidOperationException ex)
            {
                _logger.LogWarning(ex, "{Operation} dispatch denied for {UserId} on {SourceId} due unexpected request handling error.", operationLabel, subject.SubjectId, sourceId);
                return Problem(statusCode: StatusCodes.Status500InternalServerError, detail: $"Unable to process {operationLabel} request right now.");
            }
        }
        else
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "Shared horizon artifact dispatch service is not available right now.");
        }

        if (emitRunsiteHeaders && dispatchQuota is not null)
        {
            Response.Headers["X-Runsite-Tour-Limit"] = dispatchQuota.WeeklyLimit.ToString(CultureInfo.InvariantCulture);
            Response.Headers["X-Runsite-Tour-Remaining"] = dispatchQuota.WeeklyRemaining.ToString(CultureInfo.InvariantCulture);
        }

        _logger.LogInformation(
            "{Operation} dispatch allowed for {UserId} on {SourceId}; remaining={Remaining}/{Limit}.",
            operationLabel,
            subject.SubjectId,
            sourceId,
            dispatchQuota?.WeeklyRemaining,
            dispatchQuota?.WeeklyLimit);

        return Redirect(ProtectHorizonArtifactDispatchTarget(dispatchTarget));
    }

    [HttpGet("/runsites/tour-quota/me")]
    [ProducesResponseType<RunsiteTourQuotaSnapshot>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status503ServiceUnavailable)]
    public async Task<IActionResult> RunsiteTourQuota(CancellationToken cancellationToken = default)
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalSubjectAsync(cancellationToken);
        if (subject is null)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "Sign in before checking 3D-tour allowance.");
        }

        try
        {
            return Ok(_runsiteTourQuota.GetQuota(subject.SubjectId, email: subject.Email));
        }
        catch (BrilliantDirectoriesBillingUnavailableException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status400BadRequest, detail: ex.Message);
        }
    }

    [HttpGet("/roadmap/runsite")]
    public IActionResult RunsiteRoadmapAlias()
        => Redirect("/runsites");

    [HttpGet("/onramp")]
    [Produces("text/html")]
    public async Task<IActionResult> OnrampPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildOnrampPageModel(cancellationToken));

    [HttpGet("/onramp/guided-starter")]
    [HttpGet("/onramp/receipts/guided-starter.json")]
    [Produces("application/json")]
    public async Task<IActionResult> OnrampReceiptJson(CancellationToken cancellationToken)
        => Ok(BuildOnrampReceipt(await TryGetOptionalPublicSurfaceSubjectAsync("/onramp", cancellationToken)));

    [HttpGet("/onramp/packets/{packetId}.md")]
    [Produces("text/markdown")]
    public async Task<IActionResult> OnrampPacketMarkdown([FromRoute] string packetId, CancellationToken cancellationToken)
    {
        if (!IsKnownOnrampPacketId(packetId))
        {
            return NotFound();
        }

        return Content(await BuildOnrampPacketMarkdownAsync(packetId, cancellationToken), "text/markdown");
    }

    [HttpGet("/onramp/packets/{packetId}.json")]
    [Produces("application/json")]
    public async Task<IActionResult> OnrampPacketJson([FromRoute] string packetId, CancellationToken cancellationToken)
    {
        if (!IsKnownOnrampPacketId(packetId))
        {
            return NotFound();
        }

        return Content(await BuildOnrampPacketJsonAsync(packetId, cancellationToken), "application/json");
    }

    [HttpGet("/roadmap/onramp")]
    public IActionResult OnrampRoadmapAlias()
        => Redirect("/onramp");

    [HttpGet("/edition-studio")]
    [Produces("text/html")]
    public async Task<IActionResult> EditionStudioPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildEditionStudioPageModel(cancellationToken));

    [HttpGet("/edition-studio/ruleset-heads")]
    [HttpGet("/edition-studio/receipts/ruleset-heads.json")]
    [Produces("application/json")]
    public async Task<IActionResult> EditionStudioReceiptJson(CancellationToken cancellationToken)
        => Ok(BuildEditionStudioReceipt(await TryGetOptionalPublicSurfaceSubjectAsync("/edition-studio", cancellationToken)));

    [HttpGet("/edition-studio/packets/{packetId}.md")]
    [Produces("text/markdown")]
    public async Task<IActionResult> EditionStudioPacketMarkdown([FromRoute] string packetId, CancellationToken cancellationToken)
    {
        if (!IsKnownEditionStudioPacketId(packetId))
        {
            return NotFound();
        }

        return Content(await BuildEditionStudioPacketMarkdownAsync(packetId, cancellationToken), "text/markdown");
    }

    [HttpGet("/edition-studio/packets/{packetId}.json")]
    [Produces("application/json")]
    public async Task<IActionResult> EditionStudioPacketJson([FromRoute] string packetId, CancellationToken cancellationToken)
    {
        if (!IsKnownEditionStudioPacketId(packetId))
        {
            return NotFound();
        }

        return Content(await BuildEditionStudioPacketJsonAsync(packetId, cancellationToken), "application/json");
    }

    [HttpGet("/roadmap/edition-studio")]
    public IActionResult EditionStudioRoadmapAlias()
        => Redirect("/edition-studio");

    [HttpGet("/local-co-processor")]
    [Produces("text/html")]
    public async Task<IActionResult> LocalCoProcessorPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildLocalCoProcessorPageModel(cancellationToken));

    [HttpGet("/local-co-processor/optional-acceleration")]
    [HttpGet("/local-co-processor/receipts/optional-acceleration.json")]
    [Produces("application/json")]
    public async Task<IActionResult> LocalCoProcessorReceiptJson(CancellationToken cancellationToken)
        => Ok(BuildLocalCoProcessorReceipt(await TryGetOptionalPublicSurfaceSubjectAsync("/local-co-processor", cancellationToken)));

    [HttpGet("/local-co-processor/packets/{packetId}.md")]
    [Produces("text/markdown")]
    public async Task<IActionResult> LocalCoProcessorPacketMarkdown([FromRoute] string packetId, CancellationToken cancellationToken)
    {
        if (!IsKnownLocalCoProcessorPacketId(packetId))
        {
            return NotFound();
        }

        return Content(await BuildLocalCoProcessorPacketMarkdownAsync(packetId, cancellationToken), "text/markdown");
    }

    [HttpGet("/local-co-processor/packets/{packetId}.json")]
    [Produces("application/json")]
    public async Task<IActionResult> LocalCoProcessorPacketJson([FromRoute] string packetId, CancellationToken cancellationToken)
    {
        if (!IsKnownLocalCoProcessorPacketId(packetId))
        {
            return NotFound();
        }

        return Content(await BuildLocalCoProcessorPacketJsonAsync(packetId, cancellationToken), "application/json");
    }

    [HttpGet("/roadmap/local-co-processor")]
    public IActionResult LocalCoProcessorRoadmapAlias()
        => Redirect("/local-co-processor");

    [HttpGet("/run-control")]
    [Produces("text/html")]
    public async Task<IActionResult> RunControlPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildRunControlPageModel(cancellationToken));

    [HttpGet("/run-control/control-network")]
    [HttpGet("/run-control/receipts/control-network.json")]
    [Produces("application/json")]
    public async Task<IActionResult> RunControlReceiptJson(CancellationToken cancellationToken)
        => Ok(BuildRunControlReceipt(await TryGetOptionalPublicSurfaceSubjectAsync("/run-control", cancellationToken)));

    [HttpGet("/run-control/packets/{packetId}.md")]
    [Produces("text/markdown")]
    public async Task<IActionResult> RunControlPacketMarkdown([FromRoute] string packetId, CancellationToken cancellationToken)
    {
        if (!IsKnownRunControlPacketId(packetId))
        {
            return NotFound();
        }

        return Content(await BuildRunControlPacketMarkdownAsync(packetId, cancellationToken), "text/markdown");
    }

    [HttpGet("/run-control/packets/{packetId}.json")]
    [Produces("application/json")]
    public async Task<IActionResult> RunControlPacketJson([FromRoute] string packetId, CancellationToken cancellationToken)
    {
        if (!IsKnownRunControlPacketId(packetId))
        {
            return NotFound();
        }

        return Content(await BuildRunControlPacketJsonAsync(packetId, cancellationToken), "application/json");
    }

    [HttpGet("/roadmap/run-control")]
    public IActionResult RunControlRoadmapAlias()
        => Redirect("/run-control");

    [HttpGet("/runbook")]
    [Produces("text/html")]
    public async Task<IActionResult> RunbookPreviewPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildRunbookPageModel(cancellationToken));

    [HttpGet("/runbook/primer-network")]
    [HttpGet("/runbook/receipts/primer-network.json")]
    [Produces("application/json")]
    public IActionResult RunbookReceiptJson()
    {
        IReadOnlyList<MediaArtifactDocument> primers = _mediaHorizons?.ListRunbookPrimers() ?? Array.Empty<MediaArtifactDocument>();
        MediaArtifactDocument? firstPrimer = primers.FirstOrDefault();
        string firstPrimerMarkdownHref = firstPrimer?.MarkdownRoute ?? "/runbook/primers/new-runner-primer.md";
        string firstPrimerJsonHref = firstPrimer?.JsonRoute ?? "/runbook/primers/new-runner-primer.json";
        return Ok(new
        {
            Horizon = "runbook-press",
            Status = "shipped_mvp",
            PublicBoard = new
            {
                FirstPrimerMarkdownHref = firstPrimerMarkdownHref,
                FirstPrimerJsonHref = firstPrimerJsonHref,
                PrimerCount = primers.Count == 0 ? 2 : primers.Count,
                ExportDispatchHrefTemplate = "/runbook/primers/{primerId}/export",
                Summary = "RUNBOOK PRESS keeps printable primers first-party and routes formatted exports through shared Chummer-owned artifact requests."
            },
            SharedArtifacts = BuildSharedArtifactSurfaceRoutes("runbook-press", "document_export"),
            ArtifactCapability = BuildPublicHorizonCapability(
                "runbook-press",
                "document_export",
                "runbook-press:primer-network"),
            Boundary = new
            {
                PublicationStudio = "not_claimed",
                SourceTruth = "chummer_owned_primer_packets",
                ProviderTruth = "not_claimed"
            }
        });
    }

    [HttpGet("/roadmap/runbook-press")]
    public IActionResult RunbookPressRoadmapAlias()
        => Redirect("/runbook");

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

    [HttpGet("/roadmap/community-hub")]
    public IActionResult CommunityHubRoadmapAlias()
        => Redirect("/community");

    [HttpGet("/community/runs/{runId}/venue")]
    [Produces("text/html")]
    public async Task<IActionResult> CommunityRunVenuePage([FromRoute] string runId, CancellationToken cancellationToken)
    {
        string normalizedRunId = string.IsNullOrWhiteSpace(runId) ? "open-run" : runId.Trim();
        TrustPageViewModel model = await BuildHorizonPreviewPageModel(
            pageId: "community-run-venue",
            title: "Open-run venue",
            description: "Public venue status for an open run without leaking private room details.",
            currentPath: $"/community/runs/{normalizedRunId}/venue",
            eyebrow: "Community venue",
            heading: "Open-run venue status",
            intro: "This page can show that a run has a live room without exposing private room links, player emails, or campaign details.",
            sections:
            [
                new TrustPageSectionViewModel(
                    "community_run_venue_public_surface",
                    "Public venue",
                    "What this page can show",
                    "This route can acknowledge a venue without leaking the room itself.",
                    [
                        "Public session title or run label.",
                        "Scheduled start time when the organizer has published it.",
                        "Whether the live room is not configured, private, or ready for account participants."
                    ]),
                new TrustPageSectionViewModel(
                    "community_run_venue_private_boundary",
                    "Privacy boundary",
                    "What stays out of public view",
                    "Private session data remains in signed-in Chummer.",
                    [
                        "Private room links for closed tables.",
                        "Runner sheets, campaign spoilers, and GM-only notes.",
                        "Player emails, attendance imports, and service secrets."
                    ]),
                new TrustPageSectionViewModel(
                    "community_run_venue_fallback",
                    "Fallback",
                    "Fallback when the service is unavailable",
                    "Manual room links stay available when room creation is off.",
                    [
                        "Live room integration unavailable. Paste your external room link manually or use another service.",
                        "Chummer keeps the scheduling and closeout details even when room creation is off."
                    ])
            ],
            actions:
            [
                new TrustPageActionViewModel("Open community hub", "/community", "primary"),
                new TrustPageActionViewModel("Open participate", "/participate", "secondary"),
                new TrustPageActionViewModel("Open support", "/contact#support-intake", "ghost")
            ],
            cancellationToken: cancellationToken,
            summaryPoints:
            [
                "Public venue status only",
                "No private room disclosure",
                "Manual fallback stays available"
            ]);
        return View("~/Views/PublicLanding/TrustPage.cshtml", model);
    }

    [HttpGet("/account/campaigns/{campaignId}/sessions/{sessionId}/venue")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountCampaignSessionVenuePage([FromRoute] string campaignId, [FromRoute] string sessionId, CancellationToken cancellationToken)
        => await BuildGmSessionVenuePage("overview", campaignId, sessionId, $"/account/campaigns/{campaignId}/sessions/{sessionId}/venue", cancellationToken);

    [HttpGet("/account/campaigns/{campaignId}/sessions/{sessionId}/venue/manage")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountCampaignSessionVenueManagePage([FromRoute] string campaignId, [FromRoute] string sessionId, CancellationToken cancellationToken)
        => await BuildGmSessionVenuePage("manage", campaignId, sessionId, $"/account/campaigns/{campaignId}/sessions/{sessionId}/venue/manage", cancellationToken);

    [HttpGet("/account/campaigns/{campaignId}/sessions/{sessionId}/venue/closeout")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountCampaignSessionVenueCloseoutPage([FromRoute] string campaignId, [FromRoute] string sessionId, CancellationToken cancellationToken)
        => await BuildGmSessionVenuePage("closeout", campaignId, sessionId, $"/account/campaigns/{campaignId}/sessions/{sessionId}/venue/closeout", cancellationToken);

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

    [HttpGet("/roadmap/creator-os")]
    public IActionResult CreatorOsRoadmapAlias()
        => Redirect("/creator");

    [HttpGet("/quicksilver")]
    [Produces("text/html")]
    public async Task<IActionResult> QuicksilverPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildQuicksilverPageModel(cancellationToken));

    [HttpGet("/roadmap/quicksilver")]
    public IActionResult QuicksilverRoadmapAlias()
        => Redirect("/quicksilver");

    [HttpGet("/quicksilver/command-network")]
    [HttpGet("/quicksilver/receipts/command-network.json")]
    [Produces("application/json")]
    public async Task<IActionResult> QuicksilverCommandNetworkReceiptJson(CancellationToken cancellationToken)
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalPublicSurfaceSubjectAsync("/quicksilver", cancellationToken);
        QuicksilverCommandDeckReceipt payload = BuildQuicksilverCommandDeckReceipt(subject);
        return Ok(payload);
    }

    [HttpGet("/quicksilver/packets/{packetId}.md")]
    [Produces("text/markdown")]
    public async Task<IActionResult> QuicksilverPacketMarkdown([FromRoute] string packetId, CancellationToken cancellationToken)
    {
        if (!IsKnownQuicksilverPacketId(packetId))
        {
            return NotFound();
        }

        return Content(await BuildQuicksilverPacketMarkdownAsync(packetId, cancellationToken), "text/markdown");
    }

    [HttpGet("/quicksilver/packets/{packetId}.json")]
    [Produces("application/json")]
    public async Task<IActionResult> QuicksilverPacketJson([FromRoute] string packetId, CancellationToken cancellationToken)
    {
        if (!IsKnownQuicksilverPacketId(packetId))
        {
            return NotFound();
        }

        return Content(await BuildQuicksilverPacketJsonAsync(packetId, cancellationToken), "application/json");
    }

    [HttpGet("/ghostwire")]
    [Produces("text/html")]
    public async Task<IActionResult> GhostwirePreviewPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildGhostwirePageModel(cancellationToken));

    [HttpGet("/roadmap/ghostwire")]
    public IActionResult GhostwireRoadmapAlias()
        => Redirect("/ghostwire");

    [HttpGet("/ghostwire/replay-network")]
    [HttpGet("/ghostwire/receipts/replay-network.json")]
    [Produces("application/json")]
    public IActionResult GhostwireReplayNetworkReceiptJson()
    {
        GhostwirePublicSummary summary = _waveEightHorizons.BuildGhostwireSummary();
        return Ok(new
        {
            Horizon = "ghostwire",
            Status = "shipped_mvp",
            PublicBoard = new
            {
                ReplayTimelineMarkdownHref = "/ghostwire/after-action/replay_timeline.md",
                ReplayTimelineJsonHref = "/ghostwire/after-action/replay_timeline.json",
                AfterActionReportMarkdownHref = "/ghostwire/after-action/after_action_report.md",
                AfterActionReportJsonHref = "/ghostwire/after-action/after_action_report.json",
                ConsequenceChainMarkdownHref = "/ghostwire/after-action/consequence_chain.md",
                ConsequenceChainJsonHref = "/ghostwire/after-action/consequence_chain.json",
                PackageCount = summary.Packages.Count,
                AfterActionCount = summary.AfterActionCount,
                ReplayCount = summary.ReplayCount,
                DowntimeCount = summary.DowntimeCount
            },
            Boundaries = new
            {
                TranscriptTruth = "Not claimed",
                RetrospectiveFiction = "Not claimed",
                WorldTruth = "Aftermath packets only"
            }
        });
    }

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
            pageId: "foundry-export-boundary",
            title: "Foundry export boundary",
            description: "Foundry export remains a limited export path, not a separate flagship feature.",
            currentPath: "/exports/foundry",
            eyebrow: "Export support",
            heading: "Foundry export boundary",
            intro: "This route explains what Chummer can export toward Foundry-style targets without making export support look like a separate product.",
            summaryPoints:
            [
                "Export path",
                "No separate public Foundry feature",
                "Chummer keeps the campaign state"
            ],
            sections:
            [
                new TrustPageSectionViewModel("foundry-boundary", "Export limits", "Use export when it helps", "Foundry-style export creates files for another tool. Chummer keeps campaign state, moderation status, and active table work in Chummer even when a VTT target exists.", ["Export only", "Chummer keeps the record", "No outside owner"]),
                new TrustPageSectionViewModel("foundry-next", "Current status", "Use the shipped paths", "The shipped product story now lives on the active native and public features. This route remains as a simple export explainer, not as a parked roadmap promise.", ["Shipped features elsewhere", "Export stays clear", "No stale parked claim"])
            ],
            actions:
            [
                new TrustPageActionViewModel("Open runsites", "/runsites", "primary"),
                new TrustPageActionViewModel("Open run control", "/run-control", "secondary")
            ],
            cancellationToken: cancellationToken);
        return View("~/Views/PublicLanding/TrustPage.cshtml", model);
    }

    [HttpGet("/passport")]
    [Produces("text/html")]
    public async Task<IActionResult> RunnerPassportPreviewPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildRunnerPassportPageModel(cancellationToken));

    [HttpGet("/passport/identity-network")]
    [HttpGet("/passport/receipts/identity-network.json")]
    [Produces("application/json")]
    public async Task<IActionResult> RunnerPassportIdentityNetworkReceiptJson(CancellationToken cancellationToken)
    {
        IActionResult? receiptFailure = await TryCreatePublicArtifactReceiptAsync(
            operationLabel: "runner passport identity network",
            currentPath: "/passport/identity-network",
            sourceRef: "runner_passport:identity-network",
            horizonId: "runner_passport",
            artifactKindOrCapabilityId: "identity_network",
            cancellationToken: cancellationToken);
        if (receiptFailure is not null)
        {
            return receiptFailure;
        }

        RunnerPassportPublicSummary summary = _communityCreatorHorizons.BuildPassportSummary();
        return Ok(new
        {
            Horizon = "runner_passport",
            Status = "shipped_mvp",
            PublicBoard = new
            {
                RunnerReturnMarkdownHref = "/passport/runner_return_posture.md",
                RunnerReturnJsonHref = "/passport/runner_return_posture.json",
                CrossTableBoundaryMarkdownHref = "/passport/cross_table_identity_boundary.md",
                CrossTableBoundaryJsonHref = "/passport/cross_table_identity_boundary.json",
                PrivacySafeParticipationMarkdownHref = "/passport/privacy_safe_participation_proof.md",
                PrivacySafeParticipationJsonHref = "/passport/privacy_safe_participation_proof.json",
                ActiveInstallationCount = summary.ActiveInstallationCount,
                OpenRunCount = summary.OpenRunCount,
                PendingJoinCount = summary.PendingJoinCount,
                ParticipationNotificationCount = summary.ParticipationNotificationCount
            },
            SignedInBench = new
            {
                AccountEntryHref = "/account/passport",
                AccountRedirectHref = "/account/passport/open",
                AccountFallbackHref = "/account/work#aftermath-packages",
                LiveNotificationsHref = "/account/ledger/notifications",
                LeaderBriefingHrefTemplate = "/account/ledger/factions/{factionId}/leader-briefing",
                AftermathHref = "/account/work#aftermath-packages",
                Summary = "Runner Passport keeps account identity connected to the Table Pulse inbox, leader briefings, and the private aftermath return."
            },
            Boundary = new
            {
                ReputationTruth = "Not claimed",
                Surveillance = "Not claimed",
                ModerationTruth = "Signed-in only",
                IdentityRecovery = "Signed-in only"
            },
            SharedArtifacts = BuildSharedArtifactSurfaceRoutes("runner_passport", "identity_network"),
            ArtifactCapability = BuildPublicHorizonCapability(
                "runner_passport",
                "identity_network",
                "runner_passport:identity-network")
        });
    }

    [HttpGet("/signal-deck")]
    [Produces("text/html")]
    public async Task<IActionResult> SignalDeckPreviewPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildSignalDeckPageModel(cancellationToken));

    [HttpGet("/living-world")]
    [Produces("text/html")]
    public async Task<IActionResult> LivingWorldPreviewPage(CancellationToken cancellationToken)
        => View("~/Views/PublicLanding/MediaArtifactHorizon.cshtml", await BuildLivingWorldPageModel(cancellationToken));

    [HttpGet("/community/open-runs/{packetId}.md")]
    [Produces("text/markdown")]
    public IActionResult CommunityOpenRunPacketMarkdown([FromRoute] string packetId)
        => !IsKnownCommunityCreatorDocumentId(_communityCreatorHorizons.ListCommunityDocuments(), packetId)
            ? NotFound()
            : Content(_communityCreatorHorizons.BuildCommunityMarkdown(packetId), "text/markdown");

    [HttpGet("/community/open-runs/{packetId}.json")]
    [Produces("application/json")]
    public async Task<IActionResult> CommunityOpenRunPacketJson([FromRoute] string packetId, CancellationToken cancellationToken)
        => await BuildCommunityCreatorReceiptJsonAsync(
            operationLabel: "community hub open-run packet",
            currentPath: $"/community/open-runs/{Uri.EscapeDataString(packetId)}.json",
            horizonId: "community_hub",
            artifactKindOrCapabilityId: "open_run_network",
            receiptId: packetId,
            documents: _communityCreatorHorizons.ListCommunityDocuments(),
            buildJson: _communityCreatorHorizons.BuildCommunityJson,
            cancellationToken: cancellationToken);

    [HttpGet("/community/open-run-network")]
    [HttpGet("/community/receipts/open-run-network.json")]
    [Produces("application/json")]
    public async Task<IActionResult> CommunityHubReceiptJson(CancellationToken cancellationToken)
    {
        IActionResult? receiptFailure = await TryCreatePublicArtifactReceiptAsync(
            operationLabel: "community hub open-run network",
            currentPath: "/community/open-run-network",
            sourceRef: "community_hub:open-run-network",
            horizonId: "community_hub",
            artifactKindOrCapabilityId: "open_run_network",
            cancellationToken: cancellationToken);
        if (receiptFailure is not null)
        {
            return receiptFailure;
        }

        CommunityHubPublicSummary summary = _communityCreatorHorizons.BuildCommunitySummary();
        return Ok(new
        {
            Horizon = "community_hub",
            Status = "shipped_mvp",
            PublicBoard = new
            {
                BoardMarkdownHref = "/community/open-runs/open_run_board.md",
                BoardJsonHref = "/community/open-runs/open_run_board.json",
                OpenRunCount = summary.OpenRuns.Count,
                PendingJoinCount = summary.PendingJoinCount,
                ScheduledCount = summary.ScheduledCount,
                CloseoutCount = summary.CloseoutCount
            },
            SignedInBench = new
            {
                AccountEntryHref = "/account/community",
                AccountRedirectHref = "/account/community/open",
                AccountFallbackHref = "/account/work#community-ops",
                OpenRunIndexApiHref = "/api/v1/campaign-spine/me/open-runs",
                OpenRunDetailApiHrefTemplate = "/api/v1/campaign-spine/me/open-runs/{openRunId}",
                OpenRunCreateApiHrefTemplate = "/api/v1/campaign-spine/me/workspaces/{workspaceId}/open-runs",
                JoinRequestApiHrefTemplate = "/api/v1/campaign-spine/me/open-runs/{openRunId}/join-requests",
                JoinReviewApiHrefTemplate = "/api/v1/campaign-spine/me/open-runs/{openRunId}/join-requests/{requestId}/reviews",
                ScheduleApiHrefTemplate = "/api/v1/campaign-spine/me/open-runs/{openRunId}/schedule",
                MeetingHandoffApiHrefTemplate = "/api/v1/campaign-spine/me/open-runs/{openRunId}/meeting-handoff",
                CloseoutApiHrefTemplate = "/api/v1/campaign-spine/me/open-runs/{openRunId}/closeout",
                Summary = "Account Community Hub keeps open-run listing, join review, scheduling, meeting links, and closeout together on Chummer pages."
            },
            Boundary = new
            {
                MeetingTools = "Projection only",
                RulesOwner = "Chummer",
                WorldOwner = "Chummer",
                Surveillance = "Not claimed"
            },
            SharedArtifacts = BuildSharedArtifactSurfaceRoutes("community_hub", "open_run_network"),
            ArtifactCapability = BuildPublicHorizonCapability(
                "community_hub",
                "open_run_network",
                "community_hub:open-run-network")
        });
    }

    [HttpGet("/creator/packets/{packetId}.md")]
    [Produces("text/markdown")]
    public IActionResult CreatorPacketMarkdown([FromRoute] string packetId)
        => !IsKnownCommunityCreatorDocumentId(_communityCreatorHorizons.ListCreatorDocuments(), packetId)
            ? NotFound()
            : Content(_communityCreatorHorizons.BuildCreatorMarkdown(packetId), "text/markdown");

    [HttpGet("/creator/packets/{packetId}.json")]
    [Produces("application/json")]
    public async Task<IActionResult> CreatorPacketJson([FromRoute] string packetId, CancellationToken cancellationToken)
        => await BuildCommunityCreatorReceiptJsonAsync(
            operationLabel: "creator publication packet",
            currentPath: $"/creator/packets/{Uri.EscapeDataString(packetId)}.json",
            horizonId: "creator_os",
            artifactKindOrCapabilityId: "publication_network",
            receiptId: packetId,
            documents: _communityCreatorHorizons.ListCreatorDocuments(),
            buildJson: _communityCreatorHorizons.BuildCreatorJson,
            cancellationToken: cancellationToken);

    [HttpGet("/creator/publication-network")]
    [HttpGet("/creator/receipts/publication-network.json")]
    [Produces("application/json")]
    public async Task<IActionResult> CreatorOsReceiptJson(CancellationToken cancellationToken)
    {
        IActionResult? receiptFailure = await TryCreatePublicArtifactReceiptAsync(
            operationLabel: "creator publication network",
            currentPath: "/creator/publication-network",
            sourceRef: "creator_os:publication-network",
            horizonId: "creator_os",
            artifactKindOrCapabilityId: "publication_network",
            cancellationToken: cancellationToken);
        if (receiptFailure is not null)
        {
            return receiptFailure;
        }

        CreatorOsPublicSummary summary = _communityCreatorHorizons.BuildCreatorSummary();
        return Ok(new
        {
            Horizon = "creator_os",
            Status = "shipped_mvp",
            PublicBoard = new
            {
                BoardMarkdownHref = "/creator/packets/publication_board.md",
                BoardJsonHref = "/creator/packets/publication_board.json",
                PublicationCount = summary.Publications.Count,
                CuratedLiveCount = summary.CuratedLiveCount,
                ApprovalBackedCount = summary.ApprovalBackedCount,
                ReturnLoopCount = summary.ReturnLoopCount
            },
            SignedInBench = new
            {
                AccountEntryHref = "/account/creator",
                AccountRedirectHref = "/account/creator/open",
                AccountFallbackHref = "/account/work",
                PublicationDetailHrefTemplate = "/account/creator/{publicationId}",
                PublicationFallbackDetailHrefTemplate = "/account/work/publications/{publicationId}",
                PublicDetailHrefTemplate = "/artifacts/publications/{publicationId}",
                Summary = "Signed-in Creator OS keeps publication draft, review, publish, and campaign-return history on Chummer account pages."
            },
            Boundary = new
            {
                ProviderDashboards = "Not truth",
                PublicationTruth = "Chummer-owned",
                ReviewState = "Signed-in only"
            },
            SharedArtifacts = BuildSharedArtifactSurfaceRoutes("creator_os", "publication_network"),
            ArtifactCapability = BuildPublicHorizonCapability(
                "creator_os",
                "publication_network",
                "creator_os:publication-network")
        });
    }

    [HttpGet("/passport/{receiptId}.md")]
    [HttpGet("/passport/receipts/{receiptId}.md")]
    [Produces("text/markdown")]
    public IActionResult PassportReceiptMarkdown([FromRoute] string receiptId)
        => !IsKnownCommunityCreatorDocumentId(_communityCreatorHorizons.ListPassportDocuments(), receiptId)
            ? NotFound()
            : Content(_communityCreatorHorizons.BuildPassportMarkdown(receiptId), "text/markdown");

    [HttpGet("/passport/{receiptId}.json")]
    [HttpGet("/passport/receipts/{receiptId}.json")]
    [Produces("application/json")]
    public async Task<IActionResult> PassportReceiptJson([FromRoute] string receiptId, CancellationToken cancellationToken)
        => await BuildCommunityCreatorReceiptJsonAsync(
            operationLabel: "runner passport receipt",
            currentPath: $"/passport/receipts/{Uri.EscapeDataString(receiptId)}.json",
            horizonId: "runner_passport",
            artifactKindOrCapabilityId: "identity_network",
            receiptId: receiptId,
            documents: _communityCreatorHorizons.ListPassportDocuments(),
            buildJson: _communityCreatorHorizons.BuildPassportJson,
            cancellationToken: cancellationToken);

    [HttpGet("/signal-deck/{receiptId}.md")]
    [HttpGet("/signal-deck/receipts/{receiptId}.md")]
    [Produces("text/markdown")]
    public IActionResult SignalDeckReceiptMarkdown([FromRoute] string receiptId)
        => !IsKnownCommunityCreatorDocumentId(_communityCreatorHorizons.ListSignalDeckDocuments(), receiptId)
            ? NotFound()
            : Content(_communityCreatorHorizons.BuildSignalDeckMarkdown(receiptId), "text/markdown");

    [HttpGet("/signal-deck/{receiptId}.json")]
    [HttpGet("/signal-deck/receipts/{receiptId}.json")]
    [Produces("application/json")]
    public async Task<IActionResult> SignalDeckReceiptJson([FromRoute] string receiptId, CancellationToken cancellationToken)
        => await BuildCommunityCreatorReceiptJsonAsync(
            operationLabel: "signal deck receipt",
            currentPath: $"/signal-deck/receipts/{Uri.EscapeDataString(receiptId)}.json",
            horizonId: "signal_deck",
            artifactKindOrCapabilityId: "command_network",
            receiptId: receiptId,
            documents: _communityCreatorHorizons.ListSignalDeckDocuments(),
            buildJson: _communityCreatorHorizons.BuildSignalDeckJson,
            cancellationToken: cancellationToken);

    [HttpGet("/living-world/{receiptId}.md")]
    [HttpGet("/living-world/receipts/{receiptId}.md")]
    [Produces("text/markdown")]
    public IActionResult LivingWorldReceiptMarkdown([FromRoute] string receiptId)
        => !IsKnownCommunityCreatorDocumentId(_communityCreatorHorizons.ListLivingWorldDocuments(), receiptId)
            ? NotFound()
            : Content(_communityCreatorHorizons.BuildLivingWorldMarkdown(receiptId), "text/markdown");

    [HttpGet("/living-world/{receiptId}.json")]
    [HttpGet("/living-world/receipts/{receiptId}.json")]
    [Produces("application/json")]
    public async Task<IActionResult> LivingWorldReceiptJson([FromRoute] string receiptId, CancellationToken cancellationToken)
        => await BuildCommunityCreatorReceiptJsonAsync(
            operationLabel: "living world receipt",
            currentPath: $"/living-world/receipts/{Uri.EscapeDataString(receiptId)}.json",
            horizonId: "living_world",
            artifactKindOrCapabilityId: "watch_network",
            receiptId: receiptId,
            documents: _communityCreatorHorizons.ListLivingWorldDocuments(),
            buildJson: _communityCreatorHorizons.BuildLivingWorldJson,
            cancellationToken: cancellationToken);

    [HttpGet("/karma-forge")]
    public IActionResult KarmaForgeAliasPage()
        => Redirect("/participate/karma-forge");

    [HttpGet("/roadmap/karma-forge")]
    public IActionResult KarmaForgeRoadmapAlias()
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

    [HttpGet("/participate/karma-forge/discovery-network")]
    [HttpGet("/participate/karma-forge/receipts/discovery-network.json")]
    [Produces("application/json")]
    public IActionResult KarmaForgeReceiptJson()
        => Ok(new
        {
            Horizon = "karma-forge",
            Status = "shipped_mvp",
            PublicBoard = new
            {
                IntakeHref = "/participate/karma-forge",
                DiscoveryDispatchHref = "/participate/karma-forge/discovery",
                SubmittedReceiptHrefTemplate = "/participate/karma-forge/submitted/{submissionId}",
                Summary = "KARMA FORGE keeps house-rule demand intake first-party and routes discovery packets through shared Chummer-owned artifact receipts."
            },
            SharedArtifacts = BuildSharedArtifactSurfaceRoutes("karma-forge", "discovery_packet"),
            ArtifactCapability = BuildPublicHorizonCapability(
                "karma-forge",
                "discovery_packet",
                "karma-forge:public-intake"),
            Boundary = new
            {
                RulesTruth = "not_claimed",
                ApprovalTruth = "chummer_owned",
                RoadmapTruth = "separate"
            }
        });

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
                "This submission stays on this form until the required fields and consent are complete.",
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
    public IActionResult LedgerPage([FromQuery] int? turn, [FromQuery] string? mode)
        => Redirect(BuildLedgerMapEntryHref(turn, mode));

    [HttpGet("/ledger/map")]
    [Produces("text/html")]
    public async Task<IActionResult> LedgerMapPage([FromQuery] int? turn, [FromQuery] string? mode, CancellationToken cancellationToken)
    {
        var model = await BuildBlackLedgerPageModel("/ledger/map", "map", turn, cancellationToken, selectedMapMode: mode);
        return View("~/Views/PublicLanding/Ledger.cshtml", model);
    }

    [HttpGet("/black-ledger")]
    public IActionResult LedgerAliasPage()
        => Redirect("/ledger/map");

    [HttpGet("/roadmap/black-ledger")]
    public IActionResult BlackLedgerRoadmapAlias()
        => Redirect("/horizons");

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
        ApplyNoStoreHeaders(Response.Headers);
        return View("~/Views/PublicLanding/Ledger.cshtml", model);
    }

    [HttpGet("/ledger/turns/{turn}/newsreel.json")]
    [Produces("application/json")]
    public async Task<IActionResult> LedgerTurnNewsreelJson([FromRoute] string turn, CancellationToken cancellationToken)
    {
        if (!int.TryParse(turn, out int requestedTurn) || requestedTurn < 0)
        {
            return NotFound();
        }

        BlackLedgerWorldTurnBriefingViewModel? briefing = BuildProtectedBlackLedgerWorldTurnBriefing(requestedTurn);
        if (briefing is null)
        {
            return NotFound();
        }

        string sourceRef = $"black-ledger:turn-{requestedTurn}:newsroom";
        IActionResult? receiptFailure = await TryCreatePublicArtifactReceiptAsync(
            operationLabel: "black ledger newsroom bulletin",
            currentPath: $"/ledger/turns/{requestedTurn}/newsreel.json",
            sourceRef: sourceRef,
            horizonId: "black-ledger",
            artifactKindOrCapabilityId: "newsroom_bulletin",
            cancellationToken: cancellationToken);
        if (receiptFailure is not null)
        {
            return receiptFailure;
        }

        return Ok(briefing with
        {
            SharedArtifacts = BuildSharedArtifactSurfaceRoutes("black-ledger", "newsroom_bulletin"),
            ArtifactCapability = BuildPublicHorizonCapability(
                "black-ledger",
                "newsroom_bulletin",
                sourceRef)
        });
    }

    [HttpGet("/ledger/newsroom")]
    [Produces("text/html")]
    public IActionResult LedgerNewsroomHome()
    {
        BlackLedgerWorldTurnBriefingViewModel? briefing = BuildProtectedBlackLedgerWorldTurnBriefing(null);
        if (briefing?.Broadcast is null)
        {
            return NotFound();
        }

        ApplyNoStoreHeaders(Response.Headers);
        return Redirect(briefing.Broadcast.WatchHref);
    }

    [HttpGet("/ledger/newsroom/{episodeId}")]
    [Produces("text/html")]
    public async Task<IActionResult> LedgerNewsroomEpisodePage([FromRoute] string episodeId, CancellationToken cancellationToken)
    {
        if (!TryParseNewsroomEpisodeTurn(episodeId, out int requestedTurn))
        {
            return NotFound();
        }

        BlackLedgerWorldTurnBriefingViewModel? briefing = BuildProtectedBlackLedgerWorldTurnBriefing(requestedTurn);
        if (briefing?.Broadcast is null || briefing.ToTurn != requestedTurn)
        {
            return NotFound();
        }

        IActionResult? receiptFailure = await TryCreatePublicArtifactReceiptAsync(
            operationLabel: "black ledger newsroom bulletin",
            currentPath: $"/ledger/newsroom/{episodeId}",
            sourceRef: $"black-ledger:turn-{requestedTurn}:newsroom",
            horizonId: "black-ledger",
            artifactKindOrCapabilityId: "newsroom_bulletin",
            cancellationToken: cancellationToken);
        if (receiptFailure is not null)
        {
            return receiptFailure;
        }

        ApplyNoStoreHeaders(Response.Headers);
        var model = await BuildBlackLedgerPageModel($"/ledger/newsroom/{episodeId}", "newsroom", requestedTurn, cancellationToken);
        return View("~/Views/PublicLanding/Ledger.cshtml", model);
    }

    [HttpGet("/ledger/newsroom/{episodeId}/transcript")]
    [Produces("text/vtt")]
    public async Task<IActionResult> LedgerNewsroomEpisodeTranscript([FromRoute] string episodeId, CancellationToken cancellationToken)
    {
        if (!TryParseNewsroomEpisodeTurn(episodeId, out int requestedTurn))
        {
            return NotFound();
        }

        BlackLedgerWorldTurnBriefingViewModel? briefing = BuildProtectedBlackLedgerWorldTurnBriefing(requestedTurn);
        if (briefing?.Broadcast is null || briefing.ToTurn != requestedTurn)
        {
            return NotFound();
        }

        IActionResult? receiptFailure = await TryCreatePublicArtifactReceiptAsync(
            operationLabel: "black ledger newsroom transcript",
            currentPath: $"/ledger/newsroom/{episodeId}/transcript",
            sourceRef: $"black-ledger:turn-{requestedTurn}:newsroom",
            horizonId: "black-ledger",
            artifactKindOrCapabilityId: "newsroom_bulletin",
            cancellationToken: cancellationToken);
        if (receiptFailure is not null)
        {
            return receiptFailure;
        }

        ApplyNoStoreHeaders(Response.Headers);
        return Redirect(briefing.Broadcast.CaptionsHref);
    }

    [HttpGet("/ledger/newsroom/{episodeId}/receipts")]
    [Produces("application/json")]
    public async Task<IActionResult> LedgerNewsroomEpisodeReceipts([FromRoute] string episodeId, CancellationToken cancellationToken)
    {
        if (!TryParseNewsroomEpisodeTurn(episodeId, out int requestedTurn))
        {
            return NotFound();
        }

        IActionResult? receiptFailure = await TryCreatePublicArtifactReceiptAsync(
            operationLabel: "black ledger newsroom receipt packet",
            currentPath: $"/ledger/newsroom/{episodeId}/receipts",
            sourceRef: $"black-ledger:turn-{requestedTurn}:newsroom",
            horizonId: "black-ledger",
            artifactKindOrCapabilityId: "newsroom_bulletin",
            cancellationToken: cancellationToken);
        if (receiptFailure is not null)
        {
            return receiptFailure;
        }

        BlackLedgerWorldTickValidationPacketViewModel? packet = _blackLedgerBriefings.BuildValidationPacket(requestedTurn, null);
        ApplyNoStoreHeaders(Response.Headers);
        return packet is null || packet.ToTurn != requestedTurn
            ? NotFound()
            : Ok(packet with
            {
                SharedArtifacts = BuildSharedArtifactSurfaceRoutes("black-ledger", "newsroom_bulletin"),
                ArtifactCapability = BuildPublicHorizonCapability(
                    "black-ledger",
                    "newsroom_bulletin",
                    $"black-ledger:turn-{requestedTurn}:newsroom")
            });
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
        ApplyNoStoreHeaders(Response.Headers);
        return View("~/Views/PublicLanding/Ledger.cshtml", model);
    }

    private static bool TryParseNewsroomEpisodeTurn(string? episodeId, out int requestedTurn)
    {
        requestedTurn = -1;
        if (string.IsNullOrWhiteSpace(episodeId))
        {
            return false;
        }

        string normalized = episodeId.Trim();
        if (normalized.StartsWith("turn-", StringComparison.OrdinalIgnoreCase)
            && normalized.EndsWith("-newsreel", StringComparison.OrdinalIgnoreCase))
        {
            string inner = normalized["turn-".Length..^"-newsreel".Length];
            return int.TryParse(inner, out requestedTurn) && requestedTurn >= 0;
        }

        return false;
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

    [HttpGet("/ledger/factions/{factionId}/promo")]
    [Produces("text/html")]
    public async Task<IActionResult> LedgerFactionPromoPage([FromRoute] string factionId, CancellationToken cancellationToken)
    {
        IActionResult? receiptFailure = await TryCreatePublicArtifactReceiptAsync(
            operationLabel: "black ledger faction promo",
            currentPath: $"/ledger/factions/{factionId}/promo",
            sourceRef: $"black-ledger:faction-{factionId}:promo",
            horizonId: "black-ledger",
            artifactKindOrCapabilityId: "faction_promo",
            cancellationToken: cancellationToken);
        if (receiptFailure is not null)
        {
            return receiptFailure;
        }

        BlackLedgerFactionPromoPageViewModel? model = await BuildLedgerFactionPromoPageModel(factionId, cancellationToken);
        return model is null
            ? NotFound()
            : View("~/Views/PublicLanding/LedgerFactionPromo.cshtml", model);
    }

    [HttpGet("/ledger/factions/{factionId}/promo.json")]
    [Produces("application/json")]
    public async Task<IActionResult> LedgerFactionPromoJson([FromRoute] string factionId, CancellationToken cancellationToken)
    {
        BlackLedgerFactionPromoArtifactViewModel? promo = _blackLedgerFactions.GetPromoArtifact(factionId);
        if (promo is null)
        {
            return NotFound();
        }

        IActionResult? receiptFailure = await TryCreatePublicArtifactReceiptAsync(
            operationLabel: "black ledger faction promo",
            currentPath: $"/ledger/factions/{promo.FactionId}/promo.json",
            sourceRef: $"black-ledger:faction-{promo.FactionId}:promo",
            horizonId: "black-ledger",
            artifactKindOrCapabilityId: "faction_promo",
            cancellationToken: cancellationToken);
        if (receiptFailure is not null)
        {
            return receiptFailure;
        }

        BlackLedgerFactionPromoArtifactViewModel publicPromo = BuildPublicFactionPromoArtifact(promo);
        return Ok(new
        {
            publicPromo.FactionId,
            publicPromo.PublicName,
            provider_status = publicPromo.ProviderStatus,
            render_mode = publicPromo.RenderMode,
            fallback_render_mode = publicPromo.FallbackRenderMode,
            storyline_summary = publicPromo.StorylineSummary,
            narrator_posture = publicPromo.NarratorPosture,
            render_pipeline = publicPromo.RenderPipelineLabel,
            formats = publicPromo.FormatLabels,
            static_card_label = publicPromo.StaticCardLabel,
            playback_label = publicPromo.PlaybackLabel,
            captions = publicPromo.CaptionLines,
            campaign_hook = publicPromo.CampaignHook,
            audience_promise = publicPromo.AudiencePromise,
            validation_href = publicPromo.ValidationHref,
            storyboard_shots = publicPromo.StoryboardShots,
            storyboard_frames = publicPromo.StoryboardFrames.Select(frame => new
            {
                label = frame.Label,
                visual_hook = frame.VisualHook,
                action_beat = frame.ActionBeat,
                proof_payoff = frame.ProofPayoff,
            }),
            screenplay_scenes = publicPromo.ScreenplayScenes.Select(scene => new
            {
                scene_id = scene.SceneId,
                label = scene.Label,
                duration = scene.DurationLabel,
                purpose = scene.Purpose,
                visual_direction = scene.VisualDirection,
                narrator_line = scene.NarratorLine,
            }),
            html_href = publicPromo.HtmlHref,
            captions_href = publicPromo.CaptionsHref,
            poster_href = publicPromo.PosterHref,
            video_mp4_href = publicPromo.VideoMp4Href,
            video_webm_href = publicPromo.VideoWebmHref,
            SharedArtifacts = BuildSharedArtifactSurfaceRoutes("black-ledger", "faction_promo"),
            artifact_capability = BuildPublicHorizonCapability(
                "black-ledger",
                "faction_promo",
                $"black-ledger:faction-{publicPromo.FactionId}:promo")
        });
    }

    [HttpGet("/ledger/factions/{factionId}/promo.vtt")]
    [Produces("text/vtt")]
    public async Task<IActionResult> LedgerFactionPromoCaptions([FromRoute] string factionId, CancellationToken cancellationToken)
    {
        BlackLedgerFactionPromoArtifactViewModel? promo = _blackLedgerFactions.GetPromoArtifact(factionId);
        if (promo is null)
        {
            return NotFound();
        }

        IActionResult? receiptFailure = await TryCreatePublicArtifactReceiptAsync(
            operationLabel: "black ledger faction promo captions",
            currentPath: $"/ledger/factions/{promo.FactionId}/promo.vtt",
            sourceRef: $"black-ledger:faction-{promo.FactionId}:promo",
            horizonId: "black-ledger",
            artifactKindOrCapabilityId: "faction_promo",
            cancellationToken: cancellationToken);
        if (receiptFailure is not null)
        {
            return receiptFailure;
        }

        var lines = new List<string> { "WEBVTT", string.Empty };
        for (int index = 0; index < promo.CaptionLines.Count; index += 1)
        {
            int start = index * 6;
            int end = start + 6;
            lines.Add($"{index + 1}");
            lines.Add($"00:00:{start:00}.000 --> 00:00:{end:00}.000");
            lines.Add(promo.CaptionLines[index]);
            lines.Add(string.Empty);
        }

        return Content(string.Join('\n', lines), "text/vtt");
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

    [HttpGet("/account/ledger/notifications")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountLedgerNotificationsPage(CancellationToken cancellationToken)
    {
        const string currentPath = "/account/ledger/notifications";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var model = await BuildLedgerNotificationsPageModel(user, subject.SubjectId, cancellationToken);
            return View("~/Views/PublicLanding/LedgerNotifications.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
    }

    [HttpPost("/account/ledger/notifications/table-pulse/react")]
    [ValidateAntiForgeryToken]
    public async Task<IActionResult> AccountLedgerTablePulseReactionPost([FromForm] string reactionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            CampaignWorkspaceProjection? workspace = _campaignSpine.GetStarterWorkspace(user, installLinking);
            if (workspace is null)
            {
                return Redirect("/account/ledger/notifications");
            }

            CampaignConsequenceUpdateRequest request = BuildTablePulseReactionConsequenceRequest(reactionId);
            _workspaceServerPlane.UpsertCampaignConsequence(user, workspace.WorkspaceId, request, installLinking);
            return Redirect($"/account/ledger/notifications?reaction={Uri.EscapeDataString(request.Kind)}");
        }
        catch (Exception ex) when (ex is HubRequestAuthException or InvalidOperationException or ArgumentException)
        {
            _logger.LogWarning(ex, "Table Pulse Live reaction adjudication failed for the signed-in ledger lane.");
            return Redirect("/account/ledger/notifications?reaction=error");
        }
    }

    [HttpGet("/account/ledger/advisory")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountLedgerAdvisoryPage(CancellationToken cancellationToken)
    {
        const string currentPath = "/account/ledger/advisory";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var chrome = _chrome.BuildAuthenticatedChrome("Black Ledger advisory voting", "Signed-in advisory page for players, GMs, and faction leaders.", currentPath, user.DisplayName, user.Email);
            var model = _blackLedgerAdvisories.BuildPage(chrome, user);
            return View("~/Views/PublicLanding/LedgerAdvisory.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
    }

    [HttpGet("/account/ledger/advisory.json")]
    [Produces("application/json")]
    public async Task<IActionResult> AccountLedgerAdvisoryJson(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return Ok(_blackLedgerAdvisories.BuildSummaryJson(user));
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect("/login?next=%2Faccount%2Fledger%2Fadvisory.json");
        }
    }

    [HttpPost("/account/ledger/advisory/vote")]
    [ValidateAntiForgeryToken]
    public async Task<IActionResult> AccountLedgerAdvisoryVotePost([FromForm] string ballotId, [FromForm] string optionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            _blackLedgerAdvisories.SubmitVote(user, ballotId, optionId);
            return Redirect("/account/ledger/advisory");
        }
        catch (Exception ex) when (ex is HubRequestAuthException or InvalidOperationException)
        {
            return Redirect("/account/ledger/advisory");
        }
    }

    [HttpGet("/account/ledger/worldtick/validation")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountLedgerWorldTickValidationPage(CancellationToken cancellationToken)
    {
        const string currentPath = "/account/ledger/worldtick/validation";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var model = await BuildLedgerWorldTickValidationPageModel(user, cancellationToken);
            return View("~/Views/PublicLanding/LedgerWorldTickValidation.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
    }

    [HttpGet("/account/ledger/worldtick/validation.json")]
    [Produces("application/json")]
    public async Task<IActionResult> AccountLedgerWorldTickValidationJson(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            string? factionId = _blackLedgerFactions.GetAllegiance(user)?.ActiveFactionId;
            BlackLedgerWorldTickValidationPacketViewModel? packet = _blackLedgerBriefings.BuildValidationPacket(1, factionId);
            return packet is null
                ? NotFound()
                : Ok(packet with
                {
                    SharedArtifacts = BuildSharedArtifactSurfaceRoutes("black-ledger", "world_tick_digest"),
                    ArtifactCapability = BuildPublicHorizonCapability(
                        "black-ledger",
                        "world_tick_digest",
                        $"black-ledger:turn-{packet.ToTurn}:validation")
                });
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect("/login?next=%2Faccount%2Fledger%2Fworldtick%2Fvalidation.json");
        }
    }

    [HttpGet("/account/ledger/onboarding")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountLedgerOnboardingPage([FromQuery] string? step, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var model = await BuildLedgerOnboardingPageModel(user, step, cancellationToken);
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
    public async Task<IActionResult> AccountLedgerFactionCreatePage([FromQuery] string? charterType, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var model = await BuildLedgerFactionCreatePageModel(user, charterType, cancellationToken);
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
        [FromForm] bool? warningAccepted,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var charter = _blackLedgerFactions.CreateFaction(user, new BlackLedgerCreateFactionRequest(publicName, charterType, archetypeId, perkIds, flawIds, startingDistrictId, rivalFactionId, warningAccepted));
            return Redirect($"/account/ledger/factions/{charter.FactionId.Replace('_', '-')}");
        }
        catch (Exception ex) when (ex is HubRequestAuthException or InvalidOperationException)
        {
            return Redirect("/account/ledger/factions/create");
        }
    }

    [HttpGet("/account/ledger/factions/{factionId}")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountLedgerFactionPage([FromRoute] string factionId, [FromQuery] string? campaignId, CancellationToken cancellationToken)
        => await BuildLedgerFactionWorkspacePage($"/account/ledger/factions/{factionId}", factionId, "overview", campaignId, cancellationToken);

    [HttpGet("/account/ledger/factions/{factionId}/manage")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountLedgerFactionManagePage([FromRoute] string factionId, [FromQuery] string? campaignId, CancellationToken cancellationToken)
        => await BuildLedgerFactionWorkspacePage($"/account/ledger/factions/{factionId}/manage", factionId, "manage", campaignId, cancellationToken);

    [HttpGet("/account/ledger/factions/{factionId}/stewards")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountLedgerFactionStewardsPage([FromRoute] string factionId, [FromQuery] string? campaignId, CancellationToken cancellationToken)
        => await BuildLedgerFactionWorkspacePage($"/account/ledger/factions/{factionId}/stewards", factionId, "stewards", campaignId, cancellationToken);

    [HttpGet("/account/ledger/factions/{factionId}/private-lore")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountLedgerFactionPrivateLorePage([FromRoute] string factionId, [FromQuery] string? campaignId, CancellationToken cancellationToken)
        => await BuildLedgerFactionWorkspacePage($"/account/ledger/factions/{factionId}/private-lore", factionId, "private-lore", campaignId, cancellationToken);

    [HttpGet("/account/ledger/factions/{factionId}/leader-briefing")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountLedgerFactionLeaderBriefingPage([FromRoute] string factionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var model = await BuildLedgerFactionLeaderBriefingPageModel(user, factionId, cancellationToken);
            return model is null
                ? NotFound()
                : View("~/Views/PublicLanding/LedgerLeaderBriefing.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString($"/account/ledger/factions/{factionId}/leader-briefing")}");
        }
    }

    [HttpGet("/account/ledger/factions/{factionId}/leader-briefing.json")]
    [Produces("application/json")]
    public async Task<IActionResult> AccountLedgerFactionLeaderBriefingJson([FromRoute] string factionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            BlackLedgerAccountFactionAllegianceDto? allegiance = _blackLedgerFactions.GetAllegiance(user);
            if (allegiance is null || !string.Equals(allegiance.ActiveFactionId.Replace('_', '-'), factionId.Replace('_', '-'), StringComparison.OrdinalIgnoreCase))
            {
                return Forbid();
            }

            BlackLedgerFactionLeaderDigestViewModel? digest = _blackLedgerBriefings.BuildLeaderDigest(factionId, 1);
            return digest is null ? NotFound() : Ok(digest);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString($"/account/ledger/factions/{factionId}/leader-briefing.json")}");
        }
    }

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
            heading: "Anarchy consequence view",
            intro: "Anarchy belongs here as a dedicated narrative ruleset view: dispatch-friendly, mobile-first, and tied to the same shared World Turn state as the rest of the campaign city.",
            primaryAction: new TrustPageActionViewModel("Open Black Ledger", "/ledger", "primary"),
            secondaryAction: new TrustPageActionViewModel("Read Anarchy-compatible dispatches", "/ledger/dispatches?ruleset=anarchy", "secondary"),
            cancellationToken);
        return View("~/Views/PublicLanding/Anarchy.cshtml", model);
    }

    [HttpGet("/feedback")]
    [Produces("text/html")]
    public IActionResult FeedbackPage()
        => Redirect("/participate");

    [HttpGet("/help/feedback")]
    public IActionResult FeedbackHelpPage()
        => Redirect("/participate");

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
        if (!FixedTimeEquals(suppliedSecret.Trim(), configuredSecret))
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
                    "Bounded public lookup across Chummer-owned source history and follow-up thread drilldowns.",
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
                    "Bounded source drilldown across queue, delivery update, and journey state.",
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
        if (!FixedTimeEquals(suppliedSecret.Trim(), configuredSecret))
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
        if (!FixedTimeEquals(suppliedSecret.Trim(), configuredSecret))
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
        if (!FixedTimeEquals(suppliedSecret.Trim(), configuredSecret))
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
        if (!FixedTimeEquals(suppliedSecret.Trim(), configuredSecret))
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
        if (!FixedTimeEquals(suppliedSecret.Trim(), configuredSecret))
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
        => await RoadmapBoardProxyCore(
            boardPath: string.Empty,
            cancellationToken,
            localOrigin: "/roadmap/board",
            localBaseHref: "/roadmap/board/",
            canonicalHref: "/roadmap",
            fallbackPath: "/roadmap").ConfigureAwait(false);

    [HttpGet("/roadmap/board")]
    [HttpGet("/roadmap/board/{**boardPath}")]
    public async Task<IActionResult> RoadmapBoardProxy(string? boardPath, CancellationToken cancellationToken)
        => await RoadmapBoardProxyCore(
            NormalizeParticipateBoardPath(boardPath),
            cancellationToken).ConfigureAwait(false);

    private async Task<IActionResult> RoadmapBoardProxyCore(
        string? boardPath,
        CancellationToken cancellationToken,
        string localOrigin = "/roadmap/board",
        string localBaseHref = "/roadmap/board/",
        string? canonicalHref = null,
        string fallbackPath = "/roadmap")
    {
        Uri? upstream = ResolveProductLiftHostedRoadmapUri();
        if (upstream is null)
        {
            return RedirectToParticipateFallback();
        }

        string relativePath = string.IsNullOrWhiteSpace(boardPath) ? string.Empty : boardPath.TrimStart('/');
        Uri target = string.IsNullOrWhiteSpace(relativePath)
            ? AppendQueryString(upstream, Request.QueryString.Value)
            : AppendQueryString(new Uri(upstream, relativePath), Request.QueryString.Value);

        try
        {
            using HttpClient client = _httpClientFactory?.CreateClient() ?? new HttpClient();
            using var outbound = new HttpRequestMessage(HttpMethod.Get, target);
            outbound.Headers.TryAddWithoutValidation("User-Agent", Request.Headers.UserAgent.ToString());
            outbound.Headers.TryAddWithoutValidation("Accept", Request.Headers.Accept.ToArray());
            outbound.Headers.TryAddWithoutValidation("Accept-Language", Request.Headers.AcceptLanguage.ToArray());
            outbound.Headers.Referrer = upstream;

            using HttpResponseMessage response = await client.SendAsync(outbound, HttpCompletionOption.ResponseHeadersRead, cancellationToken);

            if ((int)response.StatusCode >= 300 && (int)response.StatusCode < 400 && response.Headers.Location is not null)
            {
                string redirected = RewriteHostedBoardLocation(response.Headers.Location, upstream, fallbackPath, localOrigin);
                return Redirect(redirected);
            }

            string mediaType = response.Content.Headers.ContentType?.MediaType ?? "application/octet-stream";
            if (mediaType.StartsWith("text/html", StringComparison.OrdinalIgnoreCase))
            {
                string html = await response.Content.ReadAsStringAsync(cancellationToken);
                if (!response.IsSuccessStatusCode || HostedBoardHtmlLooksUnavailable(html))
                {
                    return RedirectToParticipateFallback();
                }

                string rewritten = RewriteHostedBoardHtml(
                    html,
                    upstream,
                    ResolveParticipateBoardHomeHref(),
                    supporterHref: null,
                    localOrigin: localOrigin,
                    localBaseHref: localBaseHref,
                    railTitle: "Chummer Roadmap",
                    railNavLabel: "Roadmap actions",
                    firstLinkHref: "/participate",
                    firstLinkLabel: "Participate",
                    secondLinkHref: "/changelog",
                    secondLinkLabel: "Changelog",
                    canonicalHref: canonicalHref ?? localOrigin,
                    assetProxyBasePath: "/roadmap/provider-assets",
                    pageTitle: "Roadmap - Chummer.run",
                    hostedHeadingReplacement: "What is next?",
                    hostedSummaryReplacement: "Planned work and what moved recently.",
                    hostedPrimaryActionReplacement: "Open item",
                    hostedLeadReplacement: "Roadmap follows shipped work.",
                    applyFeedbackPolish: false,
                    failureTitle: "Roadmap temporarily unavailable",
                    failureSummary: "Try again shortly. Use the changelog for shipped work or Participate for new requests.",
                    failurePrimaryHref: "/changelog",
                    failurePrimaryLabel: "Open changelog",
                    failureSecondaryHref: "/participate",
                    failureSecondaryLabel: "Participate",
                    failureReturnHref: fallbackPath,
                    failureReturnLabel: "Back to roadmap");
                return Content(rewritten, "text/html; charset=utf-8");
            }

            byte[] bytes = await response.Content.ReadAsByteArrayAsync(cancellationToken);
            CopySafeProxyHeaders(response);
            return File(bytes, mediaType);
        }
        catch (HttpRequestException ex)
        {
            _logger.LogWarning(ex, "Roadmap board proxy could not reach upstream roadmap.");
            return RedirectToParticipateFallback();
        }
        catch (TaskCanceledException ex) when (!cancellationToken.IsCancellationRequested)
        {
            _logger.LogWarning(ex, "Roadmap board proxy timed out.");
            return RedirectToParticipateFallback();
        }
    }

    private RedirectResult RedirectToParticipateFallback()
        => Redirect($"/participate{Request.QueryString}");

    [HttpGet("/changelog")]
    [Produces("text/html")]
    public async Task<IActionResult> ChangelogPage(CancellationToken cancellationToken)
    {
        var model = await BuildNowPageModel(
            title: "Changelog",
            description: "Shipped closeout, user-visible status, and current caution stay together.",
            currentPath: "/changelog",
            cancellationToken);
        return View("~/Views/PublicLanding/Changelog.cshtml", model);
    }

    [HttpGet("/status")]
    [HttpHead("/status")]
    [Produces("text/html")]
    public async Task<IActionResult> StatusPage(CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var authenticated = await TryIsAuthenticatedAsync(cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        var pulse = _trustPulse.LoadSnapshot();
        var releaseSummary = BuildPublicStatusReleaseSummary(manifest, releaseExperience, pulse);
        var cautionSummary = BuildPublicStatusCautionSummary(manifest, pulse);
        var model = new StatusPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Status", "Chummer availability and the next useful links.", "/status", cancellationToken),
            Manifest: manifest,
            ReleaseTruth: BuildReleaseTruthDisplay(manifest),
            ReleaseExperience: releaseExperience,
            ReleaseSummary: releaseSummary,
            CautionSummary: cautionSummary,
            CampaignOsProof: _campaignOsProof.LoadProof(),
            LaunchHealthRows: BuildPublicLaunchHealthRows(manifest, releaseExperience, pulse),
            GoldReadiness: BuildGoldReadinessStatus(_goldReadiness.LoadSnapshot()),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience, pulse),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));

        ApplyNoStoreHeaders(Response.Headers);
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
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Artifacts", "Detail surfaces, briefs, and grounded outputs connected to the current public release.", "/artifacts", cancellationToken),
            Surface: surface,
            Assets: assetCatalog,
            Eyebrow: "Artifacts",
            Heading: "Detail gallery",
            Intro: "Browse the packs, briefs, and detail surfaces that make the current release feel tangible.",
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
            // .Replace( M143 source marker: missingReceiptReason: "No current local release-proof receipt is attached to the public creator-publication detail route." )
            missingReceiptReason: "No current release record is attached to the public creator-publication detail route.");
        var model = new PublicCreatorPublicationPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync(publication.Title, publication.Summary, currentPath, cancellationToken),
            Publication: publication,
            BackHref: "/artifacts#public-shared-publications",
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
            // .Replace( M143 source marker: missingReceiptReason: "No current local release-proof receipt is attached to the public creator-publication detail route." )
            missingReceiptReason: "No current release record is attached to the public creator-publication detail route.");

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
            // .Replace( M143 source marker: missingReceiptReason: "No current local release-proof receipt is attached to this release-bundle route or format." )
            missingReceiptReason: "No current release record is attached to this release-bundle route or format.");

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
                ? $"Stay on {installRef} or use support until {bundleRef} is current."
                : "Current release status is shown on this public page.",
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
        var chrome = await BuildPublicOrAuthenticatedChromeAsync("Help", "Install help, account recovery, and support.", "/help", cancellationToken);
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
        var chrome = await BuildPublicOrAuthenticatedChromeAsync("FAQ", "Short answers about downloads, accounts, and support.", "/faq", cancellationToken);
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
        var chrome = await BuildPublicOrAuthenticatedChromeAsync("Terms", "Preview-use expectations, support expectations, and the boundaries of the current hosted promise.", "/terms", cancellationToken);
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
        var chrome = await BuildPublicOrAuthenticatedChromeAsync("Contact", "Discord first. Private form only for logs or account details.", "/contact", cancellationToken);
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

        var chrome = await BuildPublicOrAuthenticatedChromeAsync("Support case submitted", "What happens next after a support report reaches Chummer.", $"/contact/submitted/{caseId}", cancellationToken);
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
            sampleReceipt ? "Sample route used for public page routing." : $"Case id {caseId}",
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
            actions.Add(new TrustPageActionViewModel("Claim your copy", "/signup?next=%2Faccount%2Fsupport", "primary"));
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
                ? "This sample page keeps the support confirmation page reachable without opening a real support case."
                : trackedCase is null
                    ? "Chummer accepted the report. Keep the case id nearby if you need to mention it later."
                    : "Chummer accepted the report and linked it to the account path so the next routed update stays visible.",
            CaseId: caseId,
            StatusLabel: sampleReceipt ? "sample" : trackedCase?.Status ?? SupportCaseStatuses.New,
            ResponseExpectation: sampleReceipt
                ? "This sample page only confirms that the support confirmation page resolves. Real follow-up still starts from a submitted support case or the account support path."
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
            var chrome = await BuildPublicOrAuthenticatedChromeAsync("Contact", "Discord first. Private form only for logs or account details.", "/contact", cancellationToken);
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
            chromeDescription: "A maintenance detail page with the pain, payoff, and the next place to read deeper.",
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
                ? new TrustPageActionViewModel("Open mobile", "/mobile", "secondary")
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
                $"{BuildPackageActionLabel(receipt.ActionKind)} record",
                receipt.RouteSummary,
                currentPath,
                user.DisplayName,
                user.Email)
            : await BuildPublicOrAuthenticatedChromeAsync(
                $"{BuildPackageActionLabel(receipt.ActionKind)} record",
                receipt.RouteSummary,
                currentPath,
                cancellationToken);
        PackageCatalogEntryViewModel packageEntry = BuildPackageCatalogEntry(package, "/packages");
        PackageReceiptCardViewModel receiptCard = BuildPackageReceiptCard(receipt);
        return View(
            "~/Views/PublicLanding/PackageReceipt.cshtml",
            new PackageActionReceiptPageViewModel(
                Chrome: chrome,
                Eyebrow: "Package record",
                Heading: $"{BuildPackageActionLabel(receipt.ActionKind)} recorded",
                Intro: "This record stays inside Chummer so package interest, compatibility, and later next steps do not disappear into an external board or generic support thread.",
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
            ? _chrome.BuildAuthenticatedChrome("Knowledge Fabric", "Source-aware explanations and readable history in Chummer.", "/rules", user.DisplayName, user.Email)
            : await BuildPublicOrAuthenticatedChromeAsync("Knowledge Fabric", "Source-aware explanations and readable history in Chummer.", "/rules", cancellationToken);

        return new KnowledgeFabricPageViewModel(
            Chrome: chrome,
            Eyebrow: "Rules help",
            Heading: "Knowledge Fabric",
            Intro: "This page keeps rules explanations readable: history, source-safe summaries, and downloadable explanations stay attached without exposing copyrighted text or private campaign state.",
            SummaryPoints:
            [
                "Source context stays attached",
                "Source-safe summaries only",
                "Explanations stay downloadable"
            ],
            Receipts: _knowledgeFabric.ListReceipts()
                .Select(receipt => new KnowledgeFabricReceiptViewModel(receipt.ReceiptId, receipt.Topic, receipt.Summary, receipt.Provenance, receipt.Route, receipt.Status))
                .ToArray(),
            PrimaryAction: new TrustPageActionViewModel("Open explanations", "/rules/explanations", "primary"),
            SecondaryAction: new TrustPageActionViewModel("Open current release", "/now#real-rules-truth", "secondary"),
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
            InstallabilitySummary: $"The public mobile page explains installability, reconnect behavior, and role entry without pretending the mobile shell replaces downloads, support, or deeper campaign work. Claimed installs currently tracked: {continuitySummary.ActiveInstallationCount}; pending recovery items: {continuitySummary.PendingClaimCount + continuitySummary.PendingBrowserCallbackCount}.",
            Roles:
            [
                new MobileRoleCardViewModel("Player", "Resume the session, keep the dossier visible, and re-enter with reconnect behavior already named.", "/player", string.Equals(currentRoleKey, "player", StringComparison.OrdinalIgnoreCase)),
                new MobileRoleCardViewModel("GM", "Keep the next scene, continuity, and return status visible without dropping back to legacy aliases.", "/gm", string.Equals(currentRoleKey, "gm", StringComparison.OrdinalIgnoreCase)),
                new MobileRoleCardViewModel("Observer", "Join the same play view in a read-mostly role when the table only needs visibility.", "/observer", string.Equals(currentRoleKey, "observer", StringComparison.OrdinalIgnoreCase))
            ],
            Capabilities:
            [
                new MobileCapabilityCardViewModel("Installable PWA", "The public page keeps the installable shell, entry point, and fallback behavior inside Chummer."),
                new MobileCapabilityCardViewModel("Offline and reconnect", "Continuity, reconnect, and next safe action remain visible before the network starts wobbling."),
                new MobileCapabilityCardViewModel("Role-aware entry", "Player, GM, and observer aliases all converge on the same play shell instead of splitting the product into separate stories."),
                new MobileCapabilityCardViewModel("Claimed install truth", $"Active claimed installs: {continuitySummary.ActiveInstallationCount}; active grants: {continuitySummary.ActiveGrantCount}; observed platforms: {string.Join(", ", continuitySummary.PlatformLabels.DefaultIfEmpty("none yet"))}."),
                new MobileCapabilityCardViewModel("Downloads stay separate", "Mobile entry explains play behavior; Downloads still owns platform choice, build integrity, and guided acquisition.")
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
            ? _chrome.BuildAuthenticatedChrome("NEXUS-PAN continuity", "Claimed installs, reconnect behavior, and continuity history in Chummer.", "/play/continuity", user.DisplayName, user.Email)
            : await BuildPublicOrAuthenticatedChromeAsync("NEXUS-PAN continuity", "Claimed installs, reconnect behavior, and continuity history in Chummer.", "/play/continuity", cancellationToken);

        string platformSummary = summary.PlatformLabels.Count == 0
            ? "No claimed-install platform labels are public yet, but this page still shows the continuity boundary between public status and signed-in history."
            : $"Observed claimed-install platforms: {string.Join(", ", summary.PlatformLabels)}.";

        return new NexusPanContinuityPageViewModel(
            Chrome: chrome,
            Eyebrow: "Continuity",
            Heading: "NEXUS-PAN continuity",
            Intro: "This page shows the continuity model clearly: claimed installs, reconnect behavior, public history, and the boundary where signed-in runboard state begins.",
            VerdictSummary: "Continuity is now part of the product surface: public pages show aggregate install and recovery status, while deeper device and workspace history stays signed in.",
            PlatformSummary: platformSummary,
            SummaryPoints:
            [
                "Claimed install status stays in Chummer",
                "Reconnect behavior stays visible",
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
            PrimaryAction: new TrustPageActionViewModel("Open continuity history", "/play/continuity/history", "primary"),
            SecondaryAction: new TrustPageActionViewModel("Open mobile and PWA", "/mobile", "secondary"),
            TertiaryAction: new TrustPageActionViewModel("Open mobile app data", "/mobile/pwa.json", "ghost"),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: user is null ? null : _signedInTrustStatus.Build(user, manifest, releaseExperience));
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildJackpointPageModel(CancellationToken cancellationToken)
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalPublicSurfaceSubjectAsync("/jackpoint", cancellationToken);
        IReadOnlyList<MediaArtifactDocument> briefings = _mediaHorizons.ListJackpointBriefings();
        return await BuildMediaArtifactHorizonPageModel(
            currentPath: "/jackpoint",
            title: "JACKPOINT",
            description: "Player-safe dossier cards, mission briefs, and Chummer publication history.",
            eyebrow: "Briefings",
            heading: "JACKPOINT",
            intro: "JACKPOINT keeps dossiers and mission briefs readable in public, while publication review and campaign return history stay on account pages.",
            boundaryLine: "Dossier and mission-brief output only. GM spoilers, draft publication notes, and private campaign return state stay signed in.",
            summaryPoints: ["Dossier cards", "Mission briefs", "Account publication workspace"],
            documents: briefings,
            primaryAction: new TrustPageActionViewModel(subject is null ? "Sign in for JACKPOINT" : "Open JACKPOINT", subject is null ? "/login?next=%2Faccount%2Fjackpoint" : "/account/jackpoint", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open briefing list", "/jackpoint/briefing-network", "secondary"),
            tertiaryAction: new TrustPageActionViewModel("Open first briefing", briefings[0].MarkdownRoute, "ghost"),
            cancellationToken: cancellationToken,
            connectedLanePacket: BuildJackpointConnectedLanePacket(subject));
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildPropertyquarryPageModel(CancellationToken cancellationToken)
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalPublicSurfaceSubjectAsync("/propertyquarry", cancellationToken);
        IReadOnlyList<MediaArtifactDocument> properties = _mediaHorizons.ListPropertyquarryProperties();
        string firstPropertyMarkdownHref = properties.FirstOrDefault()?.MarkdownRoute ?? "/propertyquarry/properties/northbound-research-lab.md";
        return await BuildMediaArtifactHorizonPageModel(
            currentPath: "/propertyquarry",
            title: "PROPERTYQUARRY",
            description: "Spatially anchored property packets with 3D-tour actions for GM-hosted runs.",
            eyebrow: "Locations",
            heading: "PROPERTYQUARRY",
            intro: "PROPERTYQUARRY keeps inspectable property packets readable in public, and each property keeps its own scene style for quick orientation with optional 3D tours.",
            boundaryLine: "Property packet and scene-style previews are public. GM-private investigation details, continuity, and run secrets stay signed in.",
            summaryPoints: ["Property packets", "Scene styles", "3D tours", "Signed-in continuity"],
            documents: properties,
            primaryAction: new TrustPageActionViewModel(subject is null ? "Sign in for PROPERTYQUARRY" : "Open PROPERTYQUARRY", subject is null ? "/login?next=%2Faccount%2Fpropertyquarry" : "/account/propertyquarry", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open property network", "/propertyquarry/property-network", "secondary"),
            tertiaryAction: new TrustPageActionViewModel("Open first property", firstPropertyMarkdownHref, "ghost"),
            cancellationToken: cancellationToken,
            connectedLanePacket: null);
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildRunsitePageModel(CancellationToken cancellationToken)
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalPublicSurfaceSubjectAsync("/runsites", cancellationToken);
        IReadOnlyList<MediaArtifactDocument> packs = _mediaHorizons.ListRunsitePacks();
        string firstPackMarkdownHref = packs.FirstOrDefault()?.MarkdownRoute ?? "/runsites/packs/redmond-dockyard-pack.md";
        return await BuildMediaArtifactHorizonPageModel(
            currentPath: "/runsites",
            title: "RUNSITE",
            description: "Site cards, threat clocks, prep paths, and Chummer runsite notes.",
            eyebrow: "Prep",
            heading: "RUNSITE",
            intro: "RUNSITE keeps prep packs readable in public, and each runsite keeps its own scene style for quick orientation with optional 3D tours.",
            boundaryLine: "Spatial-prep guide only. This page does not promise tactical overlays, live map control, or full VTT integration.",
            summaryPoints: ["Site cards", "Threat clocks", "Scene styles", "Signed-in prep bench"],
            documents: packs,
            primaryAction: new TrustPageActionViewModel(subject is null ? "Sign in for RUNSITE" : "Open RUNSITE", subject is null ? "/login?next=%2Faccount%2Frunsites" : "/account/runsites", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open prep overview", "/runsites/prep-network", "secondary"),
            tertiaryAction: new TrustPageActionViewModel("Open first runsite", firstPackMarkdownHref, "ghost"),
            cancellationToken: cancellationToken,
            connectedLanePacket: BuildRunsiteConnectedLanePacket(subject));
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildRunControlPageModel(CancellationToken cancellationToken)
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalPublicSurfaceSubjectAsync("/run-control", cancellationToken);
        return await BuildMediaArtifactHorizonPageModel(
            currentPath: "/run-control",
            title: "RUN CONTROL",
            description: "Session board, active-scene continuity, reconnect behavior, and GM operations history.",
            eyebrow: "GM operations",
            heading: "RUN CONTROL",
            intro: "RUN CONTROL keeps board status readable in public, while session control, active-scene continuity, reconnect-safe run history, and recap return stay on signed-in campaign pages.",
            boundaryLine: "GM-control surface only. RUN CONTROL does not replace the rules engine, become a chat suite, or let hidden state outrank the campaign.",
            summaryPoints: ["Session board", "Continuity board", "Account control workspace"],
            documents:
            [
                new MediaArtifactDocument(
                    "session_board",
                    "Session board",
                    "Read the session board before using Run Control at the table.",
                    "/run-control/packets/session_board.md",
                    "/run-control/packets/session_board.json",
                    ["Session status", "Active scene", "Next safe action", "Account workspace"]),
                new MediaArtifactDocument(
                    "continuity_board",
                    "Continuity board",
                    "Read the reconnect and recovery notes that keep live GM work attached to the same campaign.",
                    "/run-control/packets/continuity_board.md",
                    "/run-control/packets/continuity_board.json",
                    ["Reconnect behavior", "Runboard continuity", "Recovery notes"])
            ],
            primaryAction: new TrustPageActionViewModel(subject is null ? "Sign in for RUN CONTROL" : "Open RUN CONTROL", subject is null ? "/login?next=%2Faccount%2Frun-control" : "/account/run-control", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open control overview", "/run-control/control-network", "secondary"),
            tertiaryAction: new TrustPageActionViewModel("Open session board", "/run-control/packets/session_board.md", "ghost"),
            cancellationToken: cancellationToken,
            connectedLanePacket: BuildRunControlConnectedLanePacket(subject, BuildRunControlReceipt(subject)));
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildOnrampPageModel(CancellationToken cancellationToken)
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalPublicSurfaceSubjectAsync("/onramp", cancellationToken);
        return await BuildMediaArtifactHorizonPageModel(
            currentPath: "/onramp",
            title: "ONRAMP",
            description: "Guided first session, recovery status, and continuity without fake automation.",
            eyebrow: "Guided start",
            heading: "ONRAMP",
            intro: "ONRAMP keeps first-session setup calm: public starter and recovery notes stay readable, while account workspace, continuity restore, and session history stay attached to your account.",
            boundaryLine: "Guided starter surface only. ONRAMP does not auto-build characters, invent legality, or let tutorial theater outrank core rules and signed-in restore truth.",
            summaryPoints: ["Starter guide", "Recovery guide", "Signed-in workspace"],
            documents:
            [
                new MediaArtifactDocument(
                    "starter_lane",
                    "Starter guide",
                    "Read the starter guide before using ONRAMP for the first session.",
                    "/onramp/packets/starter_lane.md",
                    "/onramp/packets/starter_lane.json",
                    ["Starter workspace", "First playable session", "Next safe action", "Account workspace"]),
                new MediaArtifactDocument(
                    "recovery_lane",
                    "Recovery guide",
                    "Read the restore and continuity notes that keep guided setup tied to the account.",
                    "/onramp/packets/recovery_lane.md",
                    "/onramp/packets/recovery_lane.json",
                    ["Restore status", "Claimed devices", "Conflict summaries", "Recovery notes"])
            ],
            primaryAction: new TrustPageActionViewModel(subject is null ? "Sign in for ONRAMP" : "Open ONRAMP", subject is null ? "/login?next=%2Faccount%2Fonramp" : "/account/onramp", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open starter overview", "/onramp/guided-starter", "secondary"),
            tertiaryAction: new TrustPageActionViewModel("Open starter guide", "/onramp/packets/starter_lane.md", "ghost"),
            cancellationToken: cancellationToken,
            connectedLanePacket: BuildOnrampConnectedLanePacket(subject, BuildOnrampReceipt(subject)));
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildEditionStudioPageModel(CancellationToken cancellationToken)
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalPublicSurfaceSubjectAsync("/edition-studio", cancellationToken);
        return await BuildMediaArtifactHorizonPageModel(
            currentPath: "/edition-studio",
            title: "EDITION STUDIO",
            description: "Distinct SR4, SR5, and SR6 ruleset heads without splitting the product into disconnected apps.",
            eyebrow: "Edition expression",
            heading: "EDITION STUDIO",
            intro: "EDITION STUDIO now ships a focused ruleset path: SR4, SR5, and SR6 edition guides stay readable in public, while signed-in edition focus stays attached to the same account workbench.",
            boundaryLine: "Edition-focused surface only. EDITION STUDIO does not create three disconnected apps, replace core rules with styling, or treat visual flavor as rules.",
            summaryPoints: ["SR4 guide", "SR5 guide", "SR6 guide"],
            documents:
            [
                new MediaArtifactDocument(
                    "sr4_head",
                    "SR4 guide",
                    "Read the SR4 guide before switching into the legacy-focused workbench.",
                    "/edition-studio/packets/sr4_head.md",
                    "/edition-studio/packets/sr4_head.json",
                    ["Legacy muscle memory", "Dense layout", "Account edition focus"]),
                new MediaArtifactDocument(
                    "sr5_head",
                    "SR5 guide",
                    "Read the SR5 guide for the dense veteran workflow.",
                    "/edition-studio/packets/sr5_head.md",
                    "/edition-studio/packets/sr5_head.json",
                    ["Flagship density", "Explainability", "Account edition focus"]),
                new MediaArtifactDocument(
                    "sr6_head",
                    "SR6 guide",
                    "Read the SR6 guide without forcing it into older edition habits.",
                    "/edition-studio/packets/sr6_head.md",
                    "/edition-studio/packets/sr6_head.json",
                    ["Campaign-approved path", "Modern pace", "Account edition focus"])
            ],
            primaryAction: new TrustPageActionViewModel(subject is null ? "Sign in for EDITION STUDIO" : "Open EDITION STUDIO", subject is null ? "/login?next=%2Faccount%2Fedition-studio" : "/account/edition-studio", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open edition overview", "/edition-studio/ruleset-heads", "secondary"),
            tertiaryAction: new TrustPageActionViewModel("Open SR5 guide", "/edition-studio/packets/sr5_head.md", "ghost"),
            cancellationToken: cancellationToken,
            connectedLanePacket: BuildEditionStudioConnectedLanePacket(subject, BuildEditionStudioReceipt(subject)));
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildLocalCoProcessorPageModel(CancellationToken cancellationToken)
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalPublicSurfaceSubjectAsync("/local-co-processor", cancellationToken);
        return await BuildMediaArtifactHorizonPageModel(
            currentPath: "/local-co-processor",
            title: "LOCAL CO-PROCESSOR",
            description: "Optional local acceleration, explicit hosted-first parity, and disableable profiles that never become hidden requirements.",
            eyebrow: "Optional acceleration",
            heading: "LOCAL CO-PROCESSOR",
            intro: "LOCAL CO-PROCESSOR keeps optional acceleration readable in public, while profile choice and local status stay on account pages.",
            boundaryLine: "Optional acceleration surface only. LOCAL CO-PROCESSOR does not move rules into local runtime, make desktop compute mandatory, or turn optional helpers into hidden product requirements.",
            summaryPoints: ["Capability matrix", "Policy boundary", "Account optional profile"],
            documents:
            [
                new MediaArtifactDocument(
                    "capability_matrix",
                    "Capability matrix",
                    "Read the hosted-first capability matrix before enabling local compute.",
                    "/local-co-processor/packets/capability_matrix.md",
                    "/local-co-processor/packets/capability_matrix.json",
                    ["Hosted-first parity", "Optional local help", "Disableable profiles", "Account workspace"]),
                new MediaArtifactDocument(
                    "policy_boundary",
                    "Policy boundary",
                    "Read the privacy and fallback notes that keep local acceleration optional.",
                    "/local-co-processor/packets/policy_boundary.md",
                    "/local-co-processor/packets/policy_boundary.json",
                    ["No local rules owner", "No mandatory runtime", "Fallback available", "Privacy notes"])
            ],
            primaryAction: new TrustPageActionViewModel(subject is null ? "Sign in for LOCAL CO-PROCESSOR" : "Open LOCAL CO-PROCESSOR", subject is null ? "/login?next=%2Faccount%2Flocal-co-processor" : "/account/local-co-processor", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open acceleration overview", "/local-co-processor/optional-acceleration", "secondary"),
            tertiaryAction: new TrustPageActionViewModel("Open capability matrix", "/local-co-processor/packets/capability_matrix.md", "ghost"),
            cancellationToken: cancellationToken,
            connectedLanePacket: BuildLocalCoProcessorConnectedLanePacket(subject, BuildLocalCoProcessorReceipt(subject)));
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildRunbookPageModel(CancellationToken cancellationToken)
        => await BuildMediaArtifactHorizonPageModel(
            currentPath: "/runbook",
            title: "RUNBOOK PRESS",
            description: "Printable primers and first-session onboarding guides.",
            eyebrow: "Primers",
            heading: "RUNBOOK PRESS",
            intro: "RUNBOOK PRESS now ships real primers: guides you can hand to a player or GM without sending them into scattered docs.",
            boundaryLine: "Printable onboarding and prep guides only. This path does not claim a full long-form publication studio yet.",
            summaryPoints: ["New-player primer", "GM primer", "Printable guides"],
            documents: _mediaHorizons.ListRunbookPrimers(),
            primaryAction: new TrustPageActionViewModel("Open first primer", "/runbook/primers/new-runner-primer.md", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open primer data", "/runbook/primers/new-runner-primer.json", "secondary"),
            tertiaryAction: new TrustPageActionViewModel("Open Ready for Tonight", "/ready", "ghost"),
            cancellationToken: cancellationToken);

    private async Task<MediaArtifactHorizonPageViewModel> BuildCommunityHubPageModel(CancellationToken cancellationToken)
    {
        CommunityHubPublicSummary summary = _communityCreatorHorizons.BuildCommunitySummary();
        AuthenticatedHubSubject? subject = await TryGetOptionalPublicSurfaceSubjectAsync("/community", cancellationToken);
        return await BuildMediaArtifactHorizonPageModel(
            currentPath: "/community",
            title: "Community Hub",
            description: "Find open runs, understand the ground rules, and keep the public side of play easy to follow.",
            eyebrow: "Community",
            heading: "Community Hub",
            intro: "Community Hub keeps the public board readable first. Open runs, safety notes, and status stay easy to scan, while join review, scheduling, meeting links, and closeout stay on the same account page.",
            boundaryLine: "Public pages show open runs and safety notes. Private roster details, meeting access, and case handling stay in your Chummer account pages.",
            summaryPoints:
            [
                $"{summary.OpenRuns.Count} open runs visible",
                $"{summary.PendingJoinCount} pending join requests",
                $"{summary.CloseoutCount} closeouts on record"
            ],
            documents: _communityCreatorHorizons.ListCommunityDocuments().Select(item => new MediaArtifactDocument(item.Id, item.Label, item.Summary, item.MarkdownRoute, item.JsonRoute, item.Highlights)).ToArray(),
            primaryAction: new TrustPageActionViewModel(subject is null ? "Sign in for Community Hub" : "Open Community Hub", subject is null ? "/login?next=%2Faccount%2Fcommunity" : "/account/community", "primary"),
            secondaryAction: new TrustPageActionViewModel("See the public board", "/community/open-runs/open_run_board.md", "secondary"),
            tertiaryAction: new TrustPageActionViewModel("Open details", "/community/open-run-network", "ghost"),
            cancellationToken: cancellationToken,
            connectedLanePacket: BuildCommunityHubConnectedLanePacket(subject, summary));
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildCreatorOsPageModel(CancellationToken cancellationToken)
    {
        CreatorOsPublicSummary summary = _communityCreatorHorizons.BuildCreatorSummary();
        AuthenticatedHubSubject? subject = await TryGetOptionalPublicSurfaceSubjectAsync("/creator", cancellationToken);
        return await BuildMediaArtifactHorizonPageModel(
            currentPath: "/creator",
            title: "Creator OS",
            description: "Publication discovery, status, and campaign return history.",
            eyebrow: "Creator",
            heading: "Creator OS",
            intro: "Creator OS keeps publication discovery readable in public, while draft review, publication state, and campaign return history stay on account pages.",
            boundaryLine: "Creator status comes from Chummer publication history and signed-in review state. External dashboards and asset hosts do not decide what is published.",
            summaryPoints:
            [
                $"{summary.Publications.Count} discoverable publications",
                $"{summary.CuratedLiveCount} curated live",
                $"{summary.ReturnLoopCount} with campaign return summaries"
            ],
            documents: _communityCreatorHorizons.ListCreatorDocuments().Select(item => new MediaArtifactDocument(item.Id, item.Label, item.Summary, item.MarkdownRoute, item.JsonRoute, item.Highlights)).ToArray(),
            primaryAction: new TrustPageActionViewModel(subject is null ? "Sign in for Creator OS" : "Open Creator OS", subject is null ? "/login?next=%2Faccount%2Fcreator" : "/account/creator", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open publication list", "/creator/publication-network", "secondary"),
            tertiaryAction: new TrustPageActionViewModel("Open publication board", "/creator/packets/publication_board.md", "ghost"),
            cancellationToken: cancellationToken,
            connectedLanePacket: BuildCreatorOsConnectedLanePacket(subject, summary));
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildQuicksilverPageModel(CancellationToken cancellationToken)
    {
        AuthenticatedHubSubject? subject = await TryGetOptionalPublicSurfaceSubjectAsync("/quicksilver", cancellationToken);
        QuicksilverCommandDeckReceipt receipt = BuildQuicksilverCommandDeckReceipt(subject);
        return await BuildMediaArtifactHorizonPageModel(
            currentPath: "/quicksilver",
            title: "Quicksilver",
            description: "Expert-speed jump view, jump targets, and focused entry points.",
            eyebrow: "Speed",
            heading: "Quicksilver",
            intro: "Quicksilver keeps build compare, rules answers, prep, and publication work one jump apart without flattening legality, explainability, or account state.",
            boundaryLine: "Quicksilver is a speed surface for the same product. It does not hide legality, invent background automation, or turn old cached views into decisions.",
            summaryPoints:
            [
                "Jump view",
                "Typed jump targets",
                "Signed-in focus path"
            ],
            documents:
            [
                new MediaArtifactDocument(
                    "command_deck",
                    "Command deck",
                    "Read the quick-jump guide before using Quicksilver as your jump view.",
                    "/quicksilver/packets/command_deck.md",
                    "/quicksilver/packets/command_deck.json",
                    ["Builds", "Rules", "Prep", "Publications"]),
                new MediaArtifactDocument(
                    "jump_targets",
                    "Jump targets",
                    "Read the targets and focus pages that keep expert speed inside Chummer.",
                    "/quicksilver/packets/jump_targets.md",
                    "/quicksilver/packets/jump_targets.json",
                    ["Focus routes", "API deck", "Account-owned history"])
            ],
            primaryAction: new TrustPageActionViewModel(subject is null ? "Sign in for Quicksilver" : "Open Quicksilver", subject is null ? "/login?next=%2Faccount%2Fquicksilver" : "/account/quicksilver", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open command overview", "/quicksilver/command-network", "secondary"),
            tertiaryAction: new TrustPageActionViewModel("Open jump guide", "/quicksilver/packets/command_deck.md", "ghost"),
            cancellationToken: cancellationToken,
            connectedLanePacket: BuildQuicksilverConnectedLanePacket(subject, receipt));
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildRunnerPassportPageModel(CancellationToken cancellationToken)
    {
        RunnerPassportPublicSummary summary = _communityCreatorHorizons.BuildPassportSummary();
        AuthenticatedHubSubject? subject = await TryGetOptionalSubjectAsync(cancellationToken);
        HubUserDto? user = subject is null ? null : _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), subject is not null);
        SiteChromeViewModel chrome = subject is not null && user is not null
            ? _chrome.BuildAuthenticatedChrome("Runner Passport", "Runner return status, participation history, and cross-table trust in Chummer.", "/passport", user.DisplayName, user.Email)
            : await BuildPublicOrAuthenticatedChromeAsync("Runner Passport", "Runner return status, participation history, and cross-table trust in Chummer.", "/passport", cancellationToken);
        CampaignWorkspaceServerPlaneProjection? workspaceServerPlane = null;
        string? factionId = null;
        if (user is not null && subject is not null)
        {
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            CampaignWorkspaceProjection? starterWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking);
            workspaceServerPlane = starterWorkspace is null
                ? null
                : _workspaceServerPlane.GetWorkspaceServerPlane(user, starterWorkspace.WorkspaceId, installLinking);
            factionId = _blackLedgerFactions.GetAllegiance(user)?.ActiveFactionId?.Replace('_', '-');
        }

        return new MediaArtifactHorizonPageViewModel(
            Chrome: chrome,
            Eyebrow: "Identity",
            Heading: "Runner Passport",
            Intro: "Runner Passport keeps your public participation history, open runs, and return status together so your table does not have to reconstruct it from memory.",
            BoundaryLine: "This page shows public summary status only. Private identity links, moderation details, and account recovery stay signed in.",
            SummaryPoints:
            [
                $"{summary.ActiveInstallationCount} active claimed installs",
                $"{summary.OpenRunCount} open runs on the public board",
                $"{summary.PendingJoinCount} pending join requests"
            ],
            Documents: _communityCreatorHorizons.ListPassportDocuments().Select(item => new MediaArtifactCardViewModel(item.Id, item.Label, item.Summary, item.MarkdownRoute, item.JsonRoute, item.Highlights)).ToArray(),
            PrimaryAction: new TrustPageActionViewModel(subject is null ? "Sign in for Runner Passport" : "Open Runner Passport", subject is null ? "/login?next=%2Faccount%2Fpassport" : "/account/passport", "primary"),
            SecondaryAction: new TrustPageActionViewModel("Open identity overview", "/passport/identity-network", "secondary"),
            TertiaryAction: new TrustPageActionViewModel("Open return details", "/passport/runner_return_posture.md", "ghost"),
            ConnectedLanePacket: BuildRunnerPassportConnectedLanePacket(summary, workspaceServerPlane, factionId, BuildProtectedBlackLedgerWorldTurnBriefing(1)),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: user is null ? null : _signedInTrustStatus.Build(user, manifest, releaseExperience));
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildSignalDeckPageModel(CancellationToken cancellationToken)
    {
        SignalDeckPublicSummary summary = _communityCreatorHorizons.BuildSignalDeckSummary();
        AuthenticatedHubSubject? subject = await TryGetOptionalSubjectAsync(cancellationToken);
        HubUserDto? user = subject is null ? null : _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), subject is not null);
        SiteChromeViewModel chrome = subject is not null && user is not null
            ? _chrome.BuildAuthenticatedChrome("Signal Deck", "Current command pressure, consequence status, and aftermath continuity in Chummer.", "/signal-deck", user.DisplayName, user.Email)
            : await BuildPublicOrAuthenticatedChromeAsync("Signal Deck", "Current command pressure, consequence status, and aftermath continuity in Chummer.", "/signal-deck", cancellationToken);
        CampaignWorkspaceServerPlaneProjection? workspaceServerPlane = null;
        string? factionId = null;
        BlackLedgerWorldTurnBriefingViewModel? worldTurnBriefing = BuildProtectedBlackLedgerWorldTurnBriefing(1);
        if (user is not null && subject is not null)
        {
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            CampaignWorkspaceProjection? starterWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking);
            workspaceServerPlane = starterWorkspace is null
                ? null
                : _workspaceServerPlane.GetWorkspaceServerPlane(user, starterWorkspace.WorkspaceId, installLinking);
            factionId = _blackLedgerFactions.GetAllegiance(user)?.ActiveFactionId?.Replace('_', '-');
        }

        int consequenceCount = workspaceServerPlane?.Consequences.Count ?? 0;
        int aftermathCount = workspaceServerPlane?.AftermathPackages.Count ?? 0;

        return new MediaArtifactHorizonPageViewModel(
            Chrome: chrome,
            Eyebrow: "Command",
            Heading: "Signal Deck",
            Intro: "Signal Deck keeps command pressure, consequences, and aftermath on one page so the current state does not disappear into recap text.",
            BoundaryLine: "Signal Deck shows current command state only. It does not become automatic world control, a hidden moderation score, or a private transcript view.",
            SummaryPoints:
            [
                consequenceCount > 0 ? $"{consequenceCount} consequence cue(s) live" : "Command path ready",
                $"{summary.OpenRunCount} open runs on the public board",
                aftermathCount > 0 ? $"{aftermathCount} aftermath package(s) on the return path" : "Aftermath path ready"
            ],
            Documents: _communityCreatorHorizons.ListSignalDeckDocuments().Select(item => new MediaArtifactCardViewModel(item.Id, item.Label, item.Summary, item.MarkdownRoute, item.JsonRoute, item.Highlights)).ToArray(),
            PrimaryAction: new TrustPageActionViewModel("Open pressure summary", "/signal-deck/pressure_posture.md", "primary"),
            SecondaryAction: new TrustPageActionViewModel("Open pressure data", "/signal-deck/pressure_posture.json", "secondary"),
            TertiaryAction: new TrustPageActionViewModel("Open Table Pulse Live inbox", "/account/ledger/notifications", "ghost"),
            ConnectedLanePacket: BuildSignalDeckConnectedLanePacket(summary, workspaceServerPlane, factionId, worldTurnBriefing),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: user is null ? null : _signedInTrustStatus.Build(user, manifest, releaseExperience));
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildLivingWorldPageModel(CancellationToken cancellationToken)
    {
        LivingWorldPublicSummary summary = _communityCreatorHorizons.BuildLivingWorldSummary();
        AuthenticatedHubSubject? subject = await TryGetOptionalSubjectAsync(cancellationToken);
        HubUserDto? user = subject is null ? null : _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), subject is not null);
        SiteChromeViewModel chrome = subject is not null && user is not null
            ? _chrome.BuildAuthenticatedChrome("Living World", "Between-session command, bulletin framing, and aftermath continuity in Chummer.", "/living-world", user.DisplayName, user.Email)
            : await BuildPublicOrAuthenticatedChromeAsync("Living World", "Between-session command, bulletin framing, and aftermath continuity in Chummer.", "/living-world", cancellationToken);
        CampaignWorkspaceServerPlaneProjection? workspaceServerPlane = null;
        string? factionId = null;
        BlackLedgerWorldTurnBriefingViewModel? worldTurnBriefing = BuildProtectedBlackLedgerWorldTurnBriefing(1);
        if (user is not null && subject is not null)
        {
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            CampaignWorkspaceProjection? starterWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking);
            workspaceServerPlane = starterWorkspace is null
                ? null
                : _workspaceServerPlane.GetWorkspaceServerPlane(user, starterWorkspace.WorkspaceId, installLinking);
            factionId = _blackLedgerFactions.GetAllegiance(user)?.ActiveFactionId?.Replace('_', '-');
        }

        int consequenceCount = workspaceServerPlane?.Consequences.Count ?? 0;
        int aftermathCount = workspaceServerPlane?.AftermathPackages.Count ?? 0;

        return new MediaArtifactHorizonPageViewModel(
            Chrome: chrome,
            Eyebrow: "World",
            Heading: "Living World",
            Intro: "Living World keeps the between-session picture together: the current bulletin, faction command, Runner Passport, and aftermath stay tied to the same turn.",
            BoundaryLine: "Living World is opt-in and stays inside Chummer. It does not claim autonomous simulation, automatic world state, or off-table authorship outside your game.",
            SummaryPoints:
            [
                worldTurnBriefing?.Broadcast is not null ? "Bulletin live" : "Bulletin ready",
                consequenceCount > 0 ? $"{consequenceCount} consequence cue(s) live" : "Command path ready",
                aftermathCount > 0 ? $"{aftermathCount} aftermath package(s) queued" : "Aftermath path ready"
            ],
            Documents: _communityCreatorHorizons.ListLivingWorldDocuments().Select(item => new MediaArtifactCardViewModel(item.Id, item.Label, item.Summary, item.MarkdownRoute, item.JsonRoute, item.Highlights)).ToArray(),
            PrimaryAction: new TrustPageActionViewModel("Open bulletin summary", "/living-world/watch_package_posture.md", "primary"),
            SecondaryAction: new TrustPageActionViewModel("Open bulletin data", "/living-world/watch_package_posture.json", "secondary"),
            TertiaryAction: new TrustPageActionViewModel("Open current bulletin", worldTurnBriefing?.Broadcast?.WatchHref ?? "/ledger/turns/1", "ghost"),
            ConnectedLanePacket: BuildLivingWorldConnectedLanePacket(summary, workspaceServerPlane, factionId, worldTurnBriefing),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: user is null ? null : _signedInTrustStatus.Build(user, manifest, releaseExperience));
    }

    private async Task<MediaArtifactHorizonPageViewModel> BuildGhostwirePageModel(CancellationToken cancellationToken)
    {
        GhostwirePublicSummary summary = _waveEightHorizons.BuildGhostwireSummary();
        return await BuildMediaArtifactHorizonPageModel(
            currentPath: "/ghostwire",
            title: "GHOSTWIRE",
            description: "Replay timelines, after-action reports, and consequence carry-forward.",
            eyebrow: "Replay",
            heading: "GHOSTWIRE",
            intro: "GHOSTWIRE now ships after-action notes: replay timelines, after-action reports, and consequence chains live on real pages.",
            boundaryLine: "Replay stays public. No private transcript page and no retrospective fiction engine are claimed here.",
            summaryPoints:
            [
                $"{summary.Packages.Count} aftermath note(s) on record",
                $"{summary.AfterActionCount} after-action reports",
                $"{summary.ReplayCount} replay timelines"
            ],
            documents: _waveEightHorizons.ListGhostwireDocuments().Select(item => new MediaArtifactDocument(item.Id, item.Label, item.Summary, item.MarkdownRoute, item.JsonRoute, item.Highlights)).ToArray(),
            primaryAction: new TrustPageActionViewModel("Open replay timeline", "/ghostwire/after-action/replay_timeline.md", "primary"),
            secondaryAction: new TrustPageActionViewModel("Open replay data", "/ghostwire/after-action/replay_timeline.json", "secondary"),
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
        CancellationToken cancellationToken,
        BlackLedgerConnectedLanePacketViewModel? connectedLanePacket = null)
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
            Documents: documents.Select(item => new MediaArtifactCardViewModel(
                item.Id,
                item.Label,
                item.Summary,
                item.MarkdownRoute,
                item.JsonRoute,
                item.Highlights,
                item.Style,
                item.TourHref,
                item.TourLabel,
                item.TourOpenInNewTab,
                item.TourActionHref,
                item.TourActionLabel,
                item.TourActionOpenInNewTab)).ToArray(),
            PrimaryAction: primaryAction,
            SecondaryAction: secondaryAction,
            TertiaryAction: tertiaryAction,
            ConnectedLanePacket: connectedLanePacket,
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: user is null ? null : _signedInTrustStatus.Build(user, manifest, releaseExperience));
    }

    private BlackLedgerConnectedLanePacketViewModel BuildCommunityHubConnectedLanePacket(
        AuthenticatedHubSubject? subject,
        CommunityHubPublicSummary publicSummary)
    {
        if (subject is null)
        {
            BlackLedgerFollowThroughCueViewModel[] guestCues =
            [
                new(
                    Label: "Account board",
                    Summary: "Sign in to open the Community Hub board where open-run listing, join review, scheduling, and closeout stay together.",
                    Href: "/login?next=%2Faccount%2Fcommunity",
                    StatusLabel: "Sign-in"),
                new(
                    Label: "Public board",
                    Summary: $"{publicSummary.OpenRuns.Count} public open run(s), {publicSummary.PendingJoinCount} pending join request(s), and {publicSummary.CloseoutCount} closeout record(s) are already visible without exposing private roster details.",
                    Href: "/community/open-runs/open_run_board.md",
                    StatusLabel: "Public"),
                new(
                    Label: "Details",
                    Summary: "Read the account and public pages without turning Community Hub into just another forum or meeting tool.",
                    Href: "/community/open-run-network",
                    StatusLabel: "Current")
            ];

            return new BlackLedgerConnectedLanePacketViewModel(
                Heading: "Community Hub operations",
                Summary: "Public board status is readable without an account, while open-run listing, join review, scheduling, and closeout stay on the account Community Hub page.",
                BoundaryLine: "Meeting tools and public venues are handoff paths only. Chummer keeps the run, roster, scheduling, and closeout records together.",
                Cues: guestCues);
        }

        HubUserDto user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        InstallLinkingSummaryDto installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
        IReadOnlyList<OpenRunListingProjection> openRuns = _campaignSpine
            .GetOpenRuns(user, installLinking)
            .OrderByDescending(item => item.UpdatedAtUtc)
            .ToArray();
        OpenRunListingProjection? leadOpenRun = openRuns.FirstOrDefault();
        OpenRunOrchestrationProjection? leadDetail = leadOpenRun is null ? null : _campaignSpine.GetOpenRun(user, leadOpenRun.OpenRunId, installLinking);
        string detailApiHref = leadOpenRun is null
            ? "/api/v1/campaign-spine/me/open-runs"
            : $"/api/v1/campaign-spine/me/open-runs/{Uri.EscapeDataString(leadOpenRun.OpenRunId)}";
        string venueHref = leadOpenRun is null
            ? "/community/runs/open-run/venue"
            : $"/community/runs/{Uri.EscapeDataString(leadOpenRun.RunId)}/venue";

        BlackLedgerFollowThroughCueViewModel[] cues =
        [
            new(
                    Label: "Account board",
                    Summary: openRuns.Count == 0
                    ? "No open run is attached to this account yet. Community Hub is ready to open the account board as soon as a workspace publishes one."
                    : $"{openRuns.Count} open run(s) are already visible on your board, with listing, join review, scheduling, and closeout attached to the same account path.",
                Href: "/account/community",
                StatusLabel: openRuns.Count == 0 ? "Ready" : "Signed-in"),
                new(
                    Label: "Lead open run",
                    Summary: leadDetail is null
                    ? "Use the open-run list when you want current table status before a public listing becomes a real table."
                    : $"{leadDetail.JoinRequests.Count} join request(s), {leadDetail.Roster.Count} roster seat(s), and {(leadDetail.Schedule is null ? "no" : "a")} schedule are attached to {leadDetail.Listing.ListingTitle}.",
                Href: detailApiHref,
                StatusLabel: leadDetail is null ? "API" : "Typed"),
            new(
                    Label: "Venue and meeting link",
                    Summary: leadDetail?.MeetingHandoff is null
                    ? "Public venue status can be shown without leaking private room details, and meeting-service automation stays optional."
                    : $"{leadDetail.MeetingHandoff.ProviderLabel} handoff exists for the lead open run, but Chummer still keeps accepted roster and run status.",
                Href: venueHref,
                StatusLabel: leadDetail?.MeetingHandoff is null ? "Boundary" : "Handoff")
        ];

        return new BlackLedgerConnectedLanePacketViewModel(
            Heading: "Community Hub operations",
            Summary: "Community Hub now carries open-run board status, join review, scheduling, meeting links, and closeout in one Chummer campaign flow.",
            BoundaryLine: "Community Hub can show venue status and service handoff, but it does not hand run, roster, or closeout records to chat tools, meeting tools, or public boards.",
            Cues: cues);
    }

    private BlackLedgerConnectedLanePacketViewModel BuildCreatorOsConnectedLanePacket(
        AuthenticatedHubSubject? subject,
        CreatorOsPublicSummary publicSummary)
    {
        if (subject is null)
        {
            BlackLedgerFollowThroughCueViewModel[] guestCues =
            [
                new(
                    Label: "Account publication workspace",
                    Summary: "Sign in to open the Creator OS workspace where publication review, publish state, and campaign-return history stay in Chummer.",
                    Href: "/login?next=%2Faccount%2Fcreator",
                    StatusLabel: "Sign-in"),
                new(
                    Label: "Public publication board",
                    Summary: $"{publicSummary.Publications.Count} discoverable publication(s), {publicSummary.CuratedLiveCount} curated live, and {publicSummary.ReturnLoopCount} campaign return item(s) are already visible without leaking draft state.",
                    Href: "/creator/packets/publication_board.json",
                    StatusLabel: "Public-safe"),
                new(
                    Label: "Publication details",
                    Summary: "Read the account and public publication paths before treating Creator OS as an external creator page.",
                    Href: "/creator/publication-network",
                    StatusLabel: "Current")
            ];

            return new BlackLedgerConnectedLanePacketViewModel(
                Heading: "Creator OS publication",
                Summary: "Public publication discovery is readable without an account, but draft review, publish state, and campaign return stay on the signed-in Creator OS path.",
                BoundaryLine: "External creator tools may assist rendering or promotion, but Chummer owns publication status, moderation status, and campaign return state.",
                Cues: guestCues);
        }

        HubUserDto user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        InstallLinkingSummaryDto installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
        IReadOnlyList<CreatorPublicationProjection> publications = _campaignSpine
            .GetAccountSummary(user, installLinking)
            .CreatorPublications
            .OrderByDescending(item => item.UpdatedAtUtc)
            .ToArray();
        CreatorPublicationProjection? leadPublication = publications.FirstOrDefault();
        string leadPublicationHref = leadPublication is null
            ? "/account/creator"
            : $"/account/creator/{Uri.EscapeDataString(leadPublication.PublicationId)}";
        string publicPublicationHref = leadPublication is null
            ? "/artifacts"
            : $"/artifacts/publications/{Uri.EscapeDataString(leadPublication.PublicationId)}";

        BlackLedgerFollowThroughCueViewModel[] cues =
        [
                new(
                    Label: "Account publication workspace",
                    Summary: publications.Count == 0
                    ? "No publication is attached to this account yet. Creator OS is ready to open the account workspace as soon as a workspace publishes one."
                    : $"{publications.Count} publication(s) are already visible in your account area, with review, publish state, and campaign-return history together.",
                Href: "/account/creator",
                StatusLabel: publications.Count == 0 ? "Ready" : "Signed-in"),
            new(
                    Label: "Lead publication detail",
                    Summary: leadPublication is null
                        ? "Use the publication board and public view until a publication is attached to the account workspace."
                        : $"{leadPublication.PublicationStatus} · {leadPublication.TrustBand}. {leadPublication.CampaignReturnSummary ?? "Campaign-return status stays attached to the publication."}",
                Href: leadPublicationHref,
                StatusLabel: leadPublication is null ? "Desk" : "Typed"),
            new(
                    Label: "Public shelf boundary",
                    Summary: leadPublication is null
                    ? "Public creator discovery is live, but draft review and service-side state remain off the public page."
                    : $"{leadPublication.Title} is discoverable on the public view, but Chummer still owns publication history and review state.",
                Href: publicPublicationHref,
                StatusLabel: leadPublication is null ? "Public" : "Linked")
        ];

        return new BlackLedgerConnectedLanePacketViewModel(
            Heading: "Creator OS publication",
            Summary: "Creator OS now carries publication discovery, signed-in publication detail, and campaign-return history in one Chummer flow.",
            BoundaryLine: "Creator OS can show public publication detail, but it does not hand publication status, review state, or campaign return to service dashboards or generic asset pages.",
            Cues: cues);
    }

    private BlackLedgerConnectedLanePacketViewModel BuildQuicksilverConnectedLanePacket(
        AuthenticatedHubSubject? subject,
        QuicksilverCommandDeckReceipt receipt)
    {
        if (subject is null)
        {
            BlackLedgerFollowThroughCueViewModel[] guestCues =
            [
                new(
                    Label: "Signed-in jump view",
                    Summary: "Sign in to open the Quicksilver workspace where jump targets stay attached to builds, rules, prep, and publications in Chummer.",
                    Href: "/login?next=%2Faccount%2Fquicksilver",
                    StatusLabel: "Sign-in"),
                new(
                    Label: "Public command guide",
                    Summary: "The public command guide shows where quick jumps are allowed without pretending expert speed is a secret local-only mode.",
                    Href: "/quicksilver/packets/command_deck.json",
                    StatusLabel: "Public"),
                new(
                    Label: "Command details",
                    Summary: "Read the account and focus boundaries before using Quicksilver as a jump view.",
                    Href: "/quicksilver/command-network",
                    StatusLabel: "Current")
            ];

            return new BlackLedgerConnectedLanePacketViewModel(
                Heading: "Quicksilver command",
                Summary: "Public command status is readable without an account, but the actual fast-jump history stays signed in.",
                BoundaryLine: "Quicksilver speeds up access to trusted Chummer paths; it does not become a separate rules engine, hidden automation, or a source of decisions from old cached views.",
                Cues: guestCues);
        }

        QuicksilverFocusTarget? leadFocus = receipt.FocusTargets.FirstOrDefault(static item => item.Available);
        BlackLedgerFollowThroughCueViewModel[] cues =
        [
            new(
                Label: "Signed-in jump view",
                Summary: $"{receipt.Counts.BuildHandoffs} build handoff(s), {receipt.Counts.RulesAnswers} rules answer(s), {receipt.Counts.Workspaces} workspace(s), and {receipt.Counts.Publications} publication(s) are currently reachable from one speed view.",
                Href: "/account/quicksilver",
                StatusLabel: "Signed-in"),
            new(
                Label: "Command data",
                Summary: "Use this jump view when you want the current targets before opening a build, rule, workspace, or publication surface.",
                Href: "/api/v1/campaign-spine/me/quicksilver/command-deck",
                StatusLabel: "API"),
            new(
                Label: "Lead focus route",
                Summary: leadFocus is null
                    ? "Quicksilver stays ready even when no focus target is populated yet."
                    : $"{leadFocus.Label} is currently the lead jump target, and it opens a focused Chummer page instead of dropping you into a generic view.",
                Href: leadFocus?.FocusHref ?? "/account/work",
                StatusLabel: leadFocus is null ? "Ready" : "Focus")
        ];

        return new BlackLedgerConnectedLanePacketViewModel(
            Heading: "Quicksilver command",
            Summary: "Quicksilver now carries expert-speed jump targets across builds, rules, prep, and publication work in one Chummer flow.",
            BoundaryLine: "Quicksilver can reduce click friction and preserve context, but it does not hide legality, flatten meaning, or let background automation outrank explicit account state.",
            Cues: cues);
    }

    private BlackLedgerConnectedLanePacketViewModel BuildJackpointConnectedLanePacket(
        AuthenticatedHubSubject? subject)
    {
        if (subject is null)
        {
            BlackLedgerFollowThroughCueViewModel[] guestCues =
            [
                new(
                    Label: "Account JACKPOINT workspace",
                    Summary: "Sign in to open the JACKPOINT publication workspace where review, publication status, and campaign-return history stay on Chummer paths.",
                    Href: "/login?next=%2Faccount%2Fjackpoint",
                    StatusLabel: "Sign-in"),
                new(
                    Label: "Public briefing guide",
                    Summary: $"{_mediaHorizons.ListJackpointBriefings().Count} briefing(s) are already readable without opening the signed-in publication path.",
                    Href: "/jackpoint/briefings/emerald-sprawl-briefing.json",
                    StatusLabel: "Public"),
                new(
                    Label: "Briefing details",
                    Summary: "Read the account and publication paths before treating JACKPOINT like a generic export page.",
                    Href: "/jackpoint/briefing-network",
                    StatusLabel: "Current")
            ];

            return new BlackLedgerConnectedLanePacketViewModel(
                Heading: "JACKPOINT briefing",
                Summary: "Public dossiers and briefings are readable without an account, but publication review and campaign-return history stay signed in.",
                BoundaryLine: "Narration, export, or promotion helpers may assist packaging, but Chummer owns publication status, provenance, and spoiler boundaries.",
                Cues: guestCues);
        }

        HubUserDto user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        InstallLinkingSummaryDto installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
        IReadOnlyList<CreatorPublicationProjection> publications = _campaignSpine
            .GetAccountSummary(user, installLinking)
            .CreatorPublications
            .OrderByDescending(item => item.UpdatedAtUtc)
            .ToArray();
        CreatorPublicationProjection? leadPublication = publications.FirstOrDefault();
        string detailApiHref = leadPublication is null
            ? "/api/v1/campaign-spine/me/publications"
            : $"/api/v1/campaign-spine/me/publications/{Uri.EscapeDataString(leadPublication.PublicationId)}";
        string detailAccountHref = leadPublication is null
            ? "/account/jackpoint"
            : $"/account/jackpoint/{Uri.EscapeDataString(leadPublication.PublicationId)}";

        BlackLedgerFollowThroughCueViewModel[] cues =
        [
            new(
                Label: "Account publication workspace",
                Summary: publications.Count == 0
                    ? "No publication is attached to this account yet. JACKPOINT is ready to open the account workspace as soon as a publishable output lands."
                    : $"{publications.Count} publishable output(s) are already attached to this account, with review and return status still in Chummer.",
                Href: "/account/jackpoint",
                StatusLabel: publications.Count == 0 ? "Ready" : "Signed-in"),
            new(
                Label: "Lead publication status",
                Summary: leadPublication is null
                    ? "Use the publication list before opening a single file page."
                    : $"{leadPublication.Title} stays on the publication path with {leadPublication.PublicationStatus} status and {leadPublication.Visibility} visibility.",
                Href: detailApiHref,
                StatusLabel: leadPublication is null ? "API" : "Typed"),
            new(
                Label: "Open JACKPOINT workspace",
                Summary: leadPublication is null
                    ? "The JACKPOINT workspace opens to the first signed-in publication page, not to a generic docs page."
                    : $"Open the JACKPOINT workspace for {leadPublication.Title} when the next job is publication review or campaign-return history.",
                Href: detailAccountHref,
                    StatusLabel: leadPublication is null ? "Desk" : "Next step")
        ];

        return new BlackLedgerConnectedLanePacketViewModel(
            Heading: "JACKPOINT briefing",
            Summary: "JACKPOINT now carries briefings, publication review, and campaign return in one Chummer flow.",
            BoundaryLine: "JACKPOINT can package and publish, but it does not hand source history, spoiler boundaries, or publication status to external pages or media adapters.",
            Cues: cues);
    }

    private BlackLedgerConnectedLanePacketViewModel BuildRunsiteConnectedLanePacket(
        AuthenticatedHubSubject? subject)
    {
        if (subject is null)
        {
            string firstPackJsonHref = _mediaHorizons.ListRunsitePacks().FirstOrDefault()?.JsonRoute ?? "/runsites/packs/redmond-dockyard-pack.json";
            BlackLedgerFollowThroughCueViewModel[] guestCues =
            [
                new(
                    Label: "Signed-in RUNSITE bench",
                    Summary: "Sign in to open the RUNSITE workspace where prep, runboard continuity, and prep-library launch stay in Chummer.",
                    Href: "/login?next=%2Faccount%2Frunsites",
                    StatusLabel: "Sign-in"),
                new(
                    Label: "Public runsite pack",
                    Summary: $"{_mediaHorizons.ListRunsitePacks().Count} inspectable runsite pack(s) are already readable without opening the signed-in prep path.",
                    Href: firstPackJsonHref,
                    StatusLabel: "Public"),
                new(
                    Label: "Prep details",
                    Summary: "Inspect the workspace, run, and prep-library pages before treating RUNSITE like a static map gallery.",
                    Href: "/runsites/prep-network",
                    StatusLabel: "Current")
            ];

            return new BlackLedgerConnectedLanePacketViewModel(
                Heading: "RUNSITE prep",
                Summary: "Public runsite packs are inspectable without an account, but prep and runboard continuity stay in signed-in workspace and run pages.",
                BoundaryLine: "Route overlays, host clips, and tours may assist orientation, but Chummer owns prep truth, runboard truth, and workspace continuity.",
                Cues: guestCues);
        }

        HubUserDto user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        InstallLinkingSummaryDto installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
        AccountCampaignSummary accountSummary = _campaignSpine.GetAccountSummary(user, installLinking);
        CampaignWorkspaceProjection? leadWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking)
            ?? accountSummary.Workspaces.FirstOrDefault();
        RunProjection? leadRun = leadWorkspace?.Runs.OrderByDescending(item => item.UpdatedAtUtc).FirstOrDefault()
            ?? accountSummary.Runs.OrderByDescending(item => item.UpdatedAtUtc).FirstOrDefault();
        string workspaceHref = leadWorkspace is null
            ? "/account/runsites"
            : $"/account/runsites/{Uri.EscapeDataString(leadWorkspace.WorkspaceId)}";
        string prepLibraryApiHref = leadWorkspace is null
            ? "/api/v1/campaign-spine/me/workspace-digests"
            : $"/api/v1/campaign-spine/me/workspaces/{Uri.EscapeDataString(leadWorkspace.WorkspaceId)}/prep-library";
        string runApiHref = leadRun is null
            ? "/api/v1/campaign-spine/me/runs"
            : $"/api/v1/campaign-spine/me/runs/{Uri.EscapeDataString(leadRun.RunId)}";

        BlackLedgerFollowThroughCueViewModel[] cues =
        [
            new(
                Label: "Signed-in prep bench",
                Summary: leadWorkspace is null
                    ? "No workspace is attached to this account yet. RUNSITE is ready to open the prep workspace as soon as one returns."
                    : $"{leadWorkspace.CampaignName} is already on the prep path with {leadWorkspace.Runs.Count} run(s), {leadWorkspace.RecapShelf.Count} recap item(s), and continuity history attached.",
                Href: workspaceHref,
                StatusLabel: leadWorkspace is null ? "Ready" : "Signed-in"),
            new(
                Label: "Workspace and prep contract",
                Summary: leadWorkspace is null
                    ? "Use the typed workspace index when you want the prep contract before a single runsite pack becomes table prep."
                    : $"The typed workspace and prep-library APIs stay attached to {leadWorkspace.CampaignName} instead of collapsing prep into a media-only path.",
                Href: prepLibraryApiHref,
                StatusLabel: leadWorkspace is null ? "API" : "Typed"),
            new(
                Label: "Lead run continuity",
                Summary: leadRun is null
                    ? "RUNSITE can still open the run index before a live run exists."
                    : $"{leadRun.Title} keeps active-scene, objective, and continuity state on the same Chummer run path as prep.",
                Href: runApiHref,
                StatusLabel: leadRun is null ? "Index" : "Run")
        ];

        return new BlackLedgerConnectedLanePacketViewModel(
            Heading: "RUNSITE prep",
            Summary: "RUNSITE now carries public pack inspection, signed-in workspace prep, runboard continuity, and prep-library launch in one Chummer flow.",
            BoundaryLine: "RUNSITE can orient a crew before the run starts, but it does not become tactical authority, a live-map replacement, or an off-platform truth source.",
            Cues: cues);
    }

    private BlackLedgerConnectedLanePacketViewModel BuildRunControlConnectedLanePacket(
        AuthenticatedHubSubject? subject,
        RunControlReceipt receipt)
    {
        if (subject is null)
        {
            BlackLedgerFollowThroughCueViewModel[] guestCues =
            [
                new(
                    Label: "Account control workspace",
                    Summary: "Sign in to open the RUN CONTROL workspace where runboard continuity, active scene, and recap history stay on Chummer campaign paths.",
                    Href: "/login?next=%2Faccount%2Frun-control",
                    StatusLabel: "Sign-in"),
                new(
                    Label: "Public session guide",
                    Summary: "The public guide shows the session board and continuity limits without pretending GM control is only a private surface.",
                    Href: "/run-control/packets/session_board.json",
                    StatusLabel: "Public-safe"),
                new(
                    Label: "Control details",
                    Summary: "Read the account routes and control notes before using RUN CONTROL as the table hub.",
                    Href: "/run-control/control-network",
                    StatusLabel: "Current")
            ];

            return new BlackLedgerConnectedLanePacketViewModel(
                Heading: "RUN CONTROL operations",
                Summary: "Public board status is readable without an account, but the live session-control history stays signed in.",
                BoundaryLine: "RUN CONTROL can summarize session status and continuity, but it does not replace campaign state, the rules engine, or the dedicated workbench paths.",
                Cues: guestCues);
        }

        RunControlTarget? leadRun = receipt.LeadRun;
        BlackLedgerFollowThroughCueViewModel[] cues =
        [
            new(
                Label: "Account control workspace",
                Summary: $"{receipt.Counts.Campaigns} campaign(s), {receipt.Counts.Workspaces} workspace(s), and {receipt.Counts.Runs} run(s) are currently visible in the GM operations workspace.",
                Href: "/account/run-control",
                StatusLabel: "Signed-in"),
            new(
                Label: "Control data",
                Summary: "Use the dashboard and run details when you want the current session status before opening the full account workbench.",
                Href: "/api/v1/campaign-spine/me/run-control/dashboard",
                StatusLabel: "API"),
            new(
                Label: "Lead run route",
                Summary: leadRun is null
                    ? "RUN CONTROL stays ready even when no live run is attached to the account yet."
                    : $"{leadRun.Title} is the current lead run, with {(string.IsNullOrWhiteSpace(leadRun.ActiveSceneTitle) ? "no active scene yet" : $"{leadRun.ActiveSceneTitle} active")} and explicit next-step continuity.",
                Href: leadRun?.AccountHref ?? "/account/work",
                StatusLabel: leadRun is null ? "Ready" : "Run")
        ];

        return new BlackLedgerConnectedLanePacketViewModel(
            Heading: "RUN CONTROL operations",
            Summary: "RUN CONTROL now carries session board status, active-scene continuity, reconnect-safe history, and recap return in one Chummer flow.",
            BoundaryLine: "RUN CONTROL can help a GM operate the table, but it does not become hidden state, a generic collaboration suite, or a truth source outside the campaign spine.",
            Cues: cues);
    }

    private BlackLedgerConnectedLanePacketViewModel BuildOnrampConnectedLanePacket(
        AuthenticatedHubSubject? subject,
        OnrampReceipt receipt)
    {
        if (subject is null)
        {
            BlackLedgerFollowThroughCueViewModel[] guestCues =
            [
                new(
                    Label: "Account starter workspace",
                    Summary: "Sign in to open the ONRAMP workspace where starter setup, first playable session, and restore history stay on Chummer account paths.",
                    Href: "/login?next=%2Faccount%2Fonramp",
                    StatusLabel: "Sign-in"),
                new(
                    Label: "Public starter guide",
                    Summary: "The public guide shows starter and recovery limits without pretending the product is an auto-build wizard.",
                    Href: "/onramp/packets/starter_lane.json",
                    StatusLabel: "Public"),
                new(
                    Label: "Starter details",
                    Summary: "Read the account routes and recovery notes before treating ONRAMP like a simple tutorial overlay.",
                    Href: "/onramp/guided-starter",
                    StatusLabel: "Details")
            ];

            return new BlackLedgerConnectedLanePacketViewModel(
                Heading: "ONRAMP starter",
                Summary: "Public starter status is readable without an account, but actual starter workspace and restore history stay signed in.",
                BoundaryLine: "ONRAMP can guide the first playable session and recovery path, but it does not replace the rules engine, hide complexity, or turn background hints into decisions.",
                Cues: guestCues);
        }

        BlackLedgerFollowThroughCueViewModel[] cues =
        [
            new(
                Label: "Account starter workspace",
                Summary: $"{receipt.Counts.Campaigns} campaign(s), {receipt.Counts.Workspaces} workspace(s), and {receipt.Counts.Dossiers} dossier(s) are currently visible in the starter workspace.",
                Href: "/account/onramp",
                StatusLabel: "Signed-in"),
            new(
                Label: "Starter data",
                Summary: "Use the dashboard and recovery notes when you want the current guided setup before opening the broader workbench.",
                Href: "/api/v1/campaign-spine/me/onramp/dashboard",
                StatusLabel: "API"),
            new(
                Label: "Lead starter route",
                Summary: receipt.LeadStarter is null
                    ? "ONRAMP stays ready even when no starter workspace is attached to the account yet."
                    : $"{receipt.LeadStarter.CampaignName} is the lead starter workspace. Next safe action: {receipt.LeadStarter.NextSafeAction}",
                Href: receipt.LeadStarter?.AccountHref ?? "/ready",
                StatusLabel: receipt.LeadStarter is null ? "Ready" : "Starter")
        ];

        return new BlackLedgerConnectedLanePacketViewModel(
            Heading: "ONRAMP starter path",
            Summary: "ONRAMP now carries starter workspace, recovery status, and first playable history in one Chummer flow.",
            BoundaryLine: "ONRAMP can reduce first-session friction, but it does not auto-build characters, hide legality, or become a separate authority outside the campaign spine.",
            Cues: cues);
    }

    private BlackLedgerConnectedLanePacketViewModel BuildEditionStudioConnectedLanePacket(
        AuthenticatedHubSubject? subject,
        EditionStudioReceipt receipt)
    {
        if (subject is null)
        {
            BlackLedgerFollowThroughCueViewModel[] guestCues =
            [
                new(
                    Label: "Account edition workspace",
                    Summary: "Sign in to open the EDITION STUDIO workspace where SR4, SR5, and SR6 focus routes stay attached to one shared workbench.",
                    Href: "/login?next=%2Faccount%2Fedition-studio",
                    StatusLabel: "Sign-in"),
                new(
                    Label: "Public edition guide",
                    Summary: "The public guides show the SR4, SR5, and SR6 differences without pretending visual styling is rules.",
                    Href: "/edition-studio/packets/sr5_head.json",
                    StatusLabel: "Public"),
                new(
                    Label: "Ruleset details",
                    Summary: "Read the account routes and edition focus before treating EDITION STUDIO like decorative skinning.",
                    Href: "/edition-studio/ruleset-heads",
                    StatusLabel: "Details")
            ];

            return new BlackLedgerConnectedLanePacketViewModel(
                Heading: "EDITION STUDIO edition path",
                Summary: "Public edition status is readable without an account, but signed-in edition focus stays on the same Chummer workbench.",
                BoundaryLine: "EDITION STUDIO can preserve SR4, SR5, and SR6 differences, but it does not replace core rules or split the product into disconnected apps.",
                Cues: guestCues);
        }

        EditionStudioHeadTarget? leadHead = receipt.Heads.OrderByDescending(item => item.EnvironmentCount).FirstOrDefault();
        BlackLedgerFollowThroughCueViewModel[] cues =
        [
            new(
                Label: "Account edition workspace",
                Summary: $"{receipt.Counts.Workspaces} workspace(s), {receipt.Counts.Dossiers} dossier(s), and {receipt.Counts.RuleEnvironments} rule environments currently feed the edition workbenches.",
                Href: "/account/edition-studio",
                StatusLabel: "Signed-in"),
            new(
                Label: "Edition data",
                Summary: "Use the edition data when you want current SR4, SR5, and SR6 status before opening the full account workbench.",
                Href: "/api/v1/campaign-spine/me/edition-studio/heads",
                StatusLabel: "API"),
            new(
                Label: "Lead edition focus",
                Summary: leadHead is null
                    ? "EDITION STUDIO stays ready even when no rule environments are attached yet."
                    : $"{leadHead.Label} currently leads with {leadHead.EnvironmentCount} matching environment(s).",
                Href: leadHead?.AccountHref ?? "/account/work",
                StatusLabel: leadHead is null ? "Ready" : "Focus")
        ];

        return new BlackLedgerConnectedLanePacketViewModel(
            Heading: "EDITION STUDIO edition path",
            Summary: "EDITION STUDIO now carries authored SR4, SR5, and SR6 ruleset focus in one Chummer flow.",
            BoundaryLine: "EDITION STUDIO can express edition differences clearly, but it does not let styling outrank core semantics or split the product into three separate authorities.",
            Cues: cues);
    }

    private BlackLedgerConnectedLanePacketViewModel BuildLocalCoProcessorConnectedLanePacket(
        AuthenticatedHubSubject? subject,
        LocalCoProcessorReceipt receipt)
    {
        if (subject is null)
        {
            BlackLedgerFollowThroughCueViewModel[] guestCues =
            [
                new(
                    Label: "Account profile workspace",
                    Summary: "Sign in to open the LOCAL CO-PROCESSOR workspace where optional profiles and fallback behavior stay attached to your account instead of hiding in local-only assumptions.",
                    Href: "/login?next=%2Faccount%2Flocal-co-processor",
                    StatusLabel: "Sign-in"),
                new(
                    Label: "Public capability guide",
                    Summary: "The public guide shows which workloads may accelerate locally while keeping hosted mode available.",
                    Href: "/local-co-processor/packets/capability_matrix.json",
                    StatusLabel: "Public-safe"),
                new(
                    Label: "Acceleration details",
                    Summary: "Read the account routes and policy notes before treating optional acceleration like a hidden requirement.",
                    Href: "/local-co-processor/optional-acceleration",
                    StatusLabel: "Details")
            ];

            return new BlackLedgerConnectedLanePacketViewModel(
                Heading: "LOCAL CO-PROCESSOR profile path",
                Summary: "Public optional-acceleration status is readable without an account, but actual profile choice and fallback stay on signed-in Chummer pages.",
                BoundaryLine: "LOCAL CO-PROCESSOR can improve cost, privacy, or responsiveness where available, but it does not become mandatory infrastructure or a separate source of decisions.",
                Cues: guestCues);
        }

        LocalCoProcessorProfileTarget? leadProfile = receipt.Profiles.FirstOrDefault();
        BlackLedgerFollowThroughCueViewModel[] cues =
        [
            new(
                Label: "Account profile workspace",
                Summary: $"{receipt.Counts.Workspaces} workspace(s), {receipt.Counts.Dossiers} dossier(s), and {receipt.Counts.ClaimedDevices} claimed device(s) stay compatible with hosted-only fallback.",
                Href: "/account/local-co-processor",
                StatusLabel: "Signed-in"),
            new(
                Label: "Capability data",
                Summary: "Use capability and policy notes when you want the current local-acceleration status before opening account billing and membership.",
                Href: "/api/v1/campaign-spine/me/local-co-processor/capabilities",
                StatusLabel: "API"),
            new(
                Label: "Lead profile route",
                Summary: leadProfile is null
                    ? "LOCAL CO-PROCESSOR stays valid even when no optional profile is selected yet."
                    : $"{leadProfile.Label} keeps optional local help enabled only where it improves the product without becoming required.",
                Href: leadProfile?.AccountHref ?? "/account/billing",
                StatusLabel: leadProfile is null ? "Ready" : "Profile")
        ];

        return new BlackLedgerConnectedLanePacketViewModel(
            Heading: "LOCAL CO-PROCESSOR profile path",
            Summary: "LOCAL CO-PROCESSOR now carries optional acceleration policy, profile status, and fail-open fallback in one Chummer flow.",
            BoundaryLine: "LOCAL CO-PROCESSOR can accelerate certain workloads, but it does not move campaign state off the hosted path, require special hardware, or hide provider ownership.",
            Cues: cues);
    }

    private QuicksilverCommandDeckReceipt BuildQuicksilverCommandDeckReceipt(AuthenticatedHubSubject? subject)
    {
        if (subject is null)
        {
            return new QuicksilverCommandDeckReceipt(
                Horizon: "quicksilver",
                Status: "shipped_mvp",
                PublicBoard: new QuicksilverPublicBoard(
                    CommandDeckMarkdownHref: "/quicksilver/packets/command_deck.md",
                    CommandDeckJsonHref: "/quicksilver/packets/command_deck.json",
                    JumpTargetsMarkdownHref: "/quicksilver/packets/jump_targets.md",
                    JumpTargetsJsonHref: "/quicksilver/packets/jump_targets.json"),
                SignedInBench: new QuicksilverSignedInBench(
                    AccountEntryHref: "/account/quicksilver",
                    AccountRedirectHref: "/account/quicksilver/open",
                    FocusHrefTemplate: "/account/quicksilver/{focus}",
                    CommandDeckApiHref: "/api/v1/campaign-spine/me/quicksilver/command-deck",
                    JumpTargetsApiHref: "/api/v1/campaign-spine/me/quicksilver/jump-targets",
                    Summary: "Account Quicksilver opens the jump view where builds, rules, prep, and publications stay one focused jump apart."),
                Counts: new QuicksilverCounts(0, 0, 0, 0),
                FocusTargets:
                [
                new QuicksilverFocusTarget("builds", "Build handoffs", false, "/account/quicksilver/builds", "/api/v1/campaign-spine/me/build-handoffs", "Jump straight into ALICE build history."),
                    new QuicksilverFocusTarget("rules", "Rules answers", false, "/account/quicksilver/rules", "/account/work", "Jump into the rules answer view without losing the supporting context."),
                    new QuicksilverFocusTarget("runsites", "Prep benches", false, "/account/quicksilver/runsites", "/api/v1/campaign-spine/me/workspace-digests", "Jump into prep and workspace continuity."),
                    new QuicksilverFocusTarget("creator", "Creator desk", false, "/account/quicksilver/creator", "/api/v1/campaign-spine/me/publications", "Jump into signed-in publication desks without leaving Chummer paths."),
                    new QuicksilverFocusTarget("briefings", "JACKPOINT desk", false, "/account/quicksilver/briefings", "/api/v1/campaign-spine/me/publications", "Jump into briefing-safe publication history.")
                ],
                Boundary: new QuicksilverBoundary(
                    RulesTruth: "Explainability required",
                    BulkMutationAuthority: "Not claimed",
                    BackgroundAutomation: "Not claimed",
                    CacheAuthority: "Not claimed"));
        }

        HubUserDto user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        InstallLinkingSummaryDto installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
        AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
        BuildLabHandoffProjection? leadHandoff = summary.BuildLabHandoffs.OrderByDescending(item => item.UpdatedAtUtc).FirstOrDefault();
        RulesNavigatorAnswerProjection? leadRule = summary.RulesNavigator.FirstOrDefault();
        CampaignWorkspaceProjection? leadWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking)
            ?? summary.Workspaces.FirstOrDefault();
        CreatorPublicationProjection? leadPublication = summary.CreatorPublications.OrderByDescending(item => item.UpdatedAtUtc).FirstOrDefault();

        return new QuicksilverCommandDeckReceipt(
            Horizon: "quicksilver",
            Status: "shipped_mvp",
            PublicBoard: new QuicksilverPublicBoard(
                CommandDeckMarkdownHref: "/quicksilver/packets/command_deck.md",
                CommandDeckJsonHref: "/quicksilver/packets/command_deck.json",
                JumpTargetsMarkdownHref: "/quicksilver/packets/jump_targets.md",
                JumpTargetsJsonHref: "/quicksilver/packets/jump_targets.json"),
            SignedInBench: new QuicksilverSignedInBench(
                AccountEntryHref: "/account/quicksilver",
                AccountRedirectHref: "/account/quicksilver/open",
                FocusHrefTemplate: "/account/quicksilver/{focus}",
                CommandDeckApiHref: "/api/v1/campaign-spine/me/quicksilver/command-deck",
                JumpTargetsApiHref: "/api/v1/campaign-spine/me/quicksilver/jump-targets",
                Summary: "Signed-in Quicksilver keeps the speed deck on Chummer pages so help, rules answers, RUNSITE, Creator OS, and JACKPOINT stay one deliberate jump apart."),
            Counts: new QuicksilverCounts(
                summary.BuildLabHandoffs.Count,
                summary.RulesNavigator.Count,
                summary.Workspaces.Count,
                summary.CreatorPublications.Count),
            FocusTargets:
            [
                new QuicksilverFocusTarget(
                    "builds",
                    "Build handoffs",
                    leadHandoff is not null,
                    leadHandoff is null ? "/account/alice" : $"/account/alice/{Uri.EscapeDataString(leadHandoff.HandoffId)}",
                    leadHandoff is null ? "/api/v1/campaign-spine/me/build-handoffs" : $"/api/v1/campaign-spine/me/build-handoffs/{Uri.EscapeDataString(leadHandoff.HandoffId)}",
                    leadHandoff is null ? "ALICE stays ready for the next build compare and apply step." : $"{leadHandoff.Title} is ready in ALICE for the next safe jump."),
                new QuicksilverFocusTarget(
                    "rules",
                    "Rules answers",
                    leadRule is not null,
                    leadRule is null ? "/account/work" : $"/account/work/rules/{Uri.EscapeDataString(leadRule.EntryId)}",
                    leadRule is null ? "/account/work" : $"/account/work/rules/{Uri.EscapeDataString(leadRule.EntryId)}",
                    leadRule is null ? "Rules Navigator remains available when the next trustworthy answer appears." : $"Lead rules answer: {leadRule.Question}"),
                new QuicksilverFocusTarget(
                    "runsites",
                    "Prep benches",
                    leadWorkspace is not null,
                    leadWorkspace is null ? "/account/runsites" : $"/account/runsites/{Uri.EscapeDataString(leadWorkspace.WorkspaceId)}",
                    leadWorkspace is null ? "/api/v1/campaign-spine/me/workspace-digests" : $"/api/v1/campaign-spine/me/workspaces/{Uri.EscapeDataString(leadWorkspace.WorkspaceId)}/prep-library",
                    leadWorkspace is null ? "RUNSITE remains ready for prep and continuity." : $"{leadWorkspace.CampaignName} is ready in RUNSITE prep."),
                new QuicksilverFocusTarget(
                    "creator",
                    "Creator desk",
                    leadPublication is not null,
                    leadPublication is null ? "/account/creator" : $"/account/creator/{Uri.EscapeDataString(leadPublication.PublicationId)}",
                    leadPublication is null ? "/api/v1/campaign-spine/me/publications" : $"/api/v1/campaign-spine/me/publications/{Uri.EscapeDataString(leadPublication.PublicationId)}",
                    leadPublication is null ? "Creator OS remains ready for signed-in publishing work." : $"{leadPublication.Title} is ready in Creator OS."),
                new QuicksilverFocusTarget(
                    "briefings",
                    "JACKPOINT desk",
                    leadPublication is not null,
                    leadPublication is null ? "/account/jackpoint" : $"/account/jackpoint/{Uri.EscapeDataString(leadPublication.PublicationId)}",
                    leadPublication is null ? "/api/v1/campaign-spine/me/publications" : $"/api/v1/campaign-spine/me/publications/{Uri.EscapeDataString(leadPublication.PublicationId)}",
                    leadPublication is null ? "JACKPOINT remains ready for publication-safe briefings." : $"{leadPublication.Title} is also reachable through the JACKPOINT briefing desk.")
            ],
            Boundary: new QuicksilverBoundary(
                RulesTruth: "Explainability required",
                BulkMutationAuthority: "Not claimed",
                BackgroundAutomation: "Not claimed",
                CacheAuthority: "Not claimed"));
    }

    private OnrampReceipt BuildOnrampReceipt(AuthenticatedHubSubject? subject)
    {
        if (subject is null)
        {
            return new OnrampReceipt(
                Horizon: "onramp",
                Status: "shipped_mvp",
                PublicBoard: new OnrampPublicBoard(
                    StarterLaneMarkdownHref: "/onramp/packets/starter_lane.md",
                    StarterLaneJsonHref: "/onramp/packets/starter_lane.json",
                    RecoveryLaneMarkdownHref: "/onramp/packets/recovery_lane.md",
                    RecoveryLaneJsonHref: "/onramp/packets/recovery_lane.json"),
                SignedInDesk: new OnrampSignedInDesk(
                    AccountEntryHref: "/account/onramp",
                    AccountRedirectHref: "/account/onramp/open",
                    AccountStarterHref: "/account/onramp/starter",
                    DashboardApiHref: "/api/v1/campaign-spine/me/onramp/dashboard",
                    StarterApiHref: "/api/v1/campaign-spine/me/onramp/starter",
                    RecoveryApiHref: "/api/v1/campaign-spine/me/onramp/recovery",
                Summary: "Signed-in ONRAMP keeps starter workspace, restore status, and first-session history in Chummer."),
                Counts: new OnrampCounts(0, 0, 0, 0),
                LeadStarter: null,
                Recovery: new OnrampRecoveryTarget(
                    RestoreId: "signed_in_only",
                    ClaimedDevices: 0,
                    RecentArtifacts: 0,
                    ConflictCount: 0,
                    AccountHref: "/account/access",
                    ApiHref: "/api/v1/campaign-spine/me/onramp/recovery"),
                Boundary: new OnrampBoundary(
                    BuildTruth: "Core records only",
                    HiddenAutomation: "Not claimed",
                    AutoBuildAuthority: "Not claimed",
                    RecoveryAuthority: "Signed-in history"));
        }

        HubUserDto user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        InstallLinkingSummaryDto installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
        AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
        CampaignWorkspaceProjection? starterWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking)
            ?? summary.Workspaces.FirstOrDefault();
        WorkspaceRestoreProjection restore = summary.Restore;

        return new OnrampReceipt(
            Horizon: "onramp",
            Status: "shipped_mvp",
            PublicBoard: new OnrampPublicBoard(
                StarterLaneMarkdownHref: "/onramp/packets/starter_lane.md",
                StarterLaneJsonHref: "/onramp/packets/starter_lane.json",
                RecoveryLaneMarkdownHref: "/onramp/packets/recovery_lane.md",
                RecoveryLaneJsonHref: "/onramp/packets/recovery_lane.json"),
            SignedInDesk: new OnrampSignedInDesk(
                AccountEntryHref: "/account/onramp",
                AccountRedirectHref: "/account/onramp/open",
                AccountStarterHref: "/account/onramp/starter",
                DashboardApiHref: "/api/v1/campaign-spine/me/onramp/dashboard",
                StarterApiHref: "/api/v1/campaign-spine/me/onramp/starter",
                RecoveryApiHref: "/api/v1/campaign-spine/me/onramp/recovery",
                Summary: "Signed-in ONRAMP keeps starter workspace, restore status, and first playable history together in Chummer."),
            Counts: new OnrampCounts(
                summary.Campaigns.Count,
                summary.Workspaces.Count,
                summary.Dossiers.Count,
                restore.RecentArtifacts.Count),
            LeadStarter: starterWorkspace is null
                ? null
                : new OnrampStarterTarget(
                    starterWorkspace.WorkspaceId,
                    starterWorkspace.CampaignName,
                    starterWorkspace.RuleEnvironment.CompatibilityFingerprint,
                    starterWorkspace.NextSafeAction ?? "Open the starter workspace to continue.",
                    $"/account/runsites/{Uri.EscapeDataString(starterWorkspace.WorkspaceId)}",
                    $"/api/v1/campaign-spine/me/workspaces/{Uri.EscapeDataString(starterWorkspace.WorkspaceId)}"),
            Recovery: new OnrampRecoveryTarget(
                RestoreId: restore.RestoreId,
                ClaimedDevices: restore.ClaimedDevices.Count,
                RecentArtifacts: restore.RecentArtifacts.Count,
                ConflictCount: restore.ConflictSummaries.Count,
                AccountHref: "/account/access",
                ApiHref: "/api/v1/campaign-spine/me/onramp/recovery"),
            Boundary: new OnrampBoundary(
                BuildTruth: "Core records only",
                HiddenAutomation: "Not claimed",
                AutoBuildAuthority: "Not claimed",
                RecoveryAuthority: "Signed-in history"));
    }

    private EditionStudioReceipt BuildEditionStudioReceipt(AuthenticatedHubSubject? subject)
    {
        if (subject is null)
        {
            return new EditionStudioReceipt(
                Horizon: "edition_studio",
                Status: "shipped_mvp",
                PublicBoard: new EditionStudioPublicBoard(
                    Sr4HeadMarkdownHref: "/edition-studio/packets/sr4_head.md",
                    Sr4HeadJsonHref: "/edition-studio/packets/sr4_head.json",
                    Sr5HeadMarkdownHref: "/edition-studio/packets/sr5_head.md",
                    Sr5HeadJsonHref: "/edition-studio/packets/sr5_head.json",
                    Sr6HeadMarkdownHref: "/edition-studio/packets/sr6_head.md",
                    Sr6HeadJsonHref: "/edition-studio/packets/sr6_head.json"),
                SignedInDesk: new EditionStudioSignedInDesk(
                    AccountEntryHref: "/account/edition-studio",
                    AccountRedirectHref: "/account/edition-studio/open",
                    AccountHeadHrefTemplate: "/account/edition-studio/{edition}",
                    HeadsApiHref: "/api/v1/campaign-spine/me/edition-studio/heads",
                    HeadDetailApiHrefTemplate: "/api/v1/campaign-spine/me/edition-studio/heads/{edition}",
                    Summary: "Signed-in EDITION STUDIO keeps authored SR4, SR5, and SR6 focus on the same Chummer workbench."),
                Counts: new EditionStudioCounts(0, 0, 0),
                Heads:
                [
                    new EditionStudioHeadTarget("sr4", "SR4", 0, Array.Empty<string>(), "/account/edition-studio/sr4", "/api/v1/campaign-spine/me/edition-studio/heads/sr4", "Legacy veteran-first focus."),
                    new EditionStudioHeadTarget("sr5", "SR5", 0, Array.Empty<string>(), "/account/edition-studio/sr5", "/api/v1/campaign-spine/me/edition-studio/heads/sr5", "Flagship dense-workbench focus."),
                    new EditionStudioHeadTarget("sr6", "SR6", 0, Array.Empty<string>(), "/account/edition-studio/sr6", "/api/v1/campaign-spine/me/edition-studio/heads/sr6", "Campaign-approved modern focus.")
                ],
                Boundary: new EditionStudioBoundary(
                    RulesTruth: "Core semantics only",
                    DecorativeThemingAuthority: "Not claimed",
                    AppForkAuthority: "Not claimed",
                    VisualFlavorAuthority: "Not claimed"));
        }

        HubUserDto user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        InstallLinkingSummaryDto installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
        AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
        RuleEnvironmentRef[] environments = summary.Workspaces.Select(static item => item.RuleEnvironment)
            .Concat(summary.Dossiers.Select(static item => item.RuleEnvironment))
            .Concat(summary.Restore.RecentRuleEnvironments)
            .ToArray();

        return new EditionStudioReceipt(
            Horizon: "edition_studio",
            Status: "shipped_mvp",
            PublicBoard: new EditionStudioPublicBoard(
                Sr4HeadMarkdownHref: "/edition-studio/packets/sr4_head.md",
                Sr4HeadJsonHref: "/edition-studio/packets/sr4_head.json",
                Sr5HeadMarkdownHref: "/edition-studio/packets/sr5_head.md",
                Sr5HeadJsonHref: "/edition-studio/packets/sr5_head.json",
                Sr6HeadMarkdownHref: "/edition-studio/packets/sr6_head.md",
                Sr6HeadJsonHref: "/edition-studio/packets/sr6_head.json"),
            SignedInDesk: new EditionStudioSignedInDesk(
                AccountEntryHref: "/account/edition-studio",
                AccountRedirectHref: "/account/edition-studio/open",
                AccountHeadHrefTemplate: "/account/edition-studio/{edition}",
                HeadsApiHref: "/api/v1/campaign-spine/me/edition-studio/heads",
                HeadDetailApiHrefTemplate: "/api/v1/campaign-spine/me/edition-studio/heads/{edition}",
                Summary: "Signed-in EDITION STUDIO keeps authored SR4, SR5, and SR6 ruleset focus attached to one Chummer workbench."),
            Counts: new EditionStudioCounts(summary.Workspaces.Count, summary.Dossiers.Count, environments.Length),
            Heads:
            [
                BuildEditionStudioHeadTarget("sr4", "SR4", "Dense veteran-first focus for legacy muscle memory and BP-era expectations.", environments),
                BuildEditionStudioHeadTarget("sr5", "SR5", "The flagship dense-workbench focus where legality, explain, and veteran speed stay authored together.", environments),
                BuildEditionStudioHeadTarget("sr6", "SR6", "Campaign-approved modern focus where simplified pace stays distinct from older heads.", environments)
            ],
            Boundary: new EditionStudioBoundary(
                RulesTruth: "Core semantics only",
                DecorativeThemingAuthority: "Not claimed",
                AppForkAuthority: "Not claimed",
                VisualFlavorAuthority: "Not claimed"));
    }

    private LocalCoProcessorReceipt BuildLocalCoProcessorReceipt(AuthenticatedHubSubject? subject)
    {
        if (subject is null)
        {
            return new LocalCoProcessorReceipt(
                Horizon: "local_co_processor",
                Status: "shipped_mvp",
                PublicBoard: new LocalCoProcessorPublicBoard(
                    CapabilityMatrixMarkdownHref: "/local-co-processor/packets/capability_matrix.md",
                    CapabilityMatrixJsonHref: "/local-co-processor/packets/capability_matrix.json",
                    PolicyBoundaryMarkdownHref: "/local-co-processor/packets/policy_boundary.md",
                    PolicyBoundaryJsonHref: "/local-co-processor/packets/policy_boundary.json"),
                SignedInDesk: new LocalCoProcessorSignedInDesk(
                    AccountEntryHref: "/account/local-co-processor",
                    AccountRedirectHref: "/account/local-co-processor/open",
                    AccountProfileHrefTemplate: "/account/local-co-processor/{profile}",
                    CapabilitiesApiHref: "/api/v1/campaign-spine/me/local-co-processor/capabilities",
                    PolicyApiHref: "/api/v1/campaign-spine/me/local-co-processor/policy",
                Summary: "Signed-in LOCAL CO-PROCESSOR keeps optional local profiles, hosted-first parity, and fail-open fallback in Chummer."),
                Counts: new LocalCoProcessorCounts(0, 0, 0, 3),
                Profiles:
                [
                    new LocalCoProcessorProfileTarget("hosted_only", "Hosted only", false, "/account/local-co-processor/hosted_only", "/api/v1/campaign-spine/me/local-co-processor/policy", "Keep every workflow fully hosted with no local acceleration requirement."),
                    new LocalCoProcessorProfileTarget("hybrid_local", "Hybrid local", false, "/account/local-co-processor/hybrid_local", "/api/v1/campaign-spine/me/local-co-processor/capabilities", "Allow optional local acceleration where it improves responsiveness or cost."),
                    new LocalCoProcessorProfileTarget("privacy_first", "Privacy first", false, "/account/local-co-processor/privacy_first", "/api/v1/campaign-spine/me/local-co-processor/capabilities", "Prefer local handling where it reduces disclosure without breaking hosted fallback.")
                ],
                Boundary: new LocalCoProcessorBoundary(
                    HostedFirstParity: "Required",
                    MandatoryRuntime: "Not claimed",
                    LocalTruthAuthority: "Not claimed",
                    DisableableProfiles: "Required"));
        }

        HubUserDto user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        InstallLinkingSummaryDto installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
        AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
        string preferredProfile = summary.Restore.ClaimedDevices.Count > 0
            ? "privacy_first"
            : summary.Workspaces.Count > 0 || summary.Dossiers.Count > 0
                ? "hybrid_local"
                : "hosted_only";

        LocalCoProcessorProfileTarget[] profiles =
        [
            new("hosted_only", "Hosted only", string.Equals(preferredProfile, "hosted_only", StringComparison.Ordinal), "/account/local-co-processor/hosted_only", "/api/v1/campaign-spine/me/local-co-processor/policy", "Keep every workflow fully hosted with no local acceleration requirement."),
            new("hybrid_local", "Hybrid local", string.Equals(preferredProfile, "hybrid_local", StringComparison.Ordinal), "/account/local-co-processor/hybrid_local", "/api/v1/campaign-spine/me/local-co-processor/capabilities", "Allow optional local acceleration where it improves responsiveness or cost."),
            new("privacy_first", "Privacy first", string.Equals(preferredProfile, "privacy_first", StringComparison.Ordinal), "/account/local-co-processor/privacy_first", "/api/v1/campaign-spine/me/local-co-processor/capabilities", "Prefer local handling where it reduces disclosure without breaking hosted fallback.")
        ];

        return new LocalCoProcessorReceipt(
            Horizon: "local_co_processor",
            Status: "shipped_mvp",
            PublicBoard: new LocalCoProcessorPublicBoard(
                CapabilityMatrixMarkdownHref: "/local-co-processor/packets/capability_matrix.md",
                CapabilityMatrixJsonHref: "/local-co-processor/packets/capability_matrix.json",
                PolicyBoundaryMarkdownHref: "/local-co-processor/packets/policy_boundary.md",
                PolicyBoundaryJsonHref: "/local-co-processor/packets/policy_boundary.json"),
            SignedInDesk: new LocalCoProcessorSignedInDesk(
                AccountEntryHref: "/account/local-co-processor",
                AccountRedirectHref: "/account/local-co-processor/open",
                AccountProfileHrefTemplate: "/account/local-co-processor/{profile}",
                CapabilitiesApiHref: "/api/v1/campaign-spine/me/local-co-processor/capabilities",
                PolicyApiHref: "/api/v1/campaign-spine/me/local-co-processor/policy",
                Summary: "Signed-in LOCAL CO-PROCESSOR keeps optional local profiles, hosted-first parity, and fail-open fallback together in Chummer."),
            Counts: new LocalCoProcessorCounts(summary.Workspaces.Count, summary.Dossiers.Count, summary.Restore.ClaimedDevices.Count, profiles.Length),
            Profiles: profiles,
            Boundary: new LocalCoProcessorBoundary(
                HostedFirstParity: "Required",
                MandatoryRuntime: "Not claimed",
                LocalTruthAuthority: "Not claimed",
                DisableableProfiles: "Required"));
    }

    private static EditionStudioHeadTarget BuildEditionStudioHeadTarget(string edition, string label, string summary, IReadOnlyList<RuleEnvironmentRef> environments)
    {
        RuleEnvironmentRef[] matching = environments
            .Where(environment => string.Equals(NormalizeEditionStudioHeadId(environment.CompatibilityFingerprint), edition, StringComparison.OrdinalIgnoreCase)
                || environment.SourcePacks.Any(pack => string.Equals(NormalizeEditionStudioHeadId(pack), edition, StringComparison.OrdinalIgnoreCase)))
            .ToArray();

        return new EditionStudioHeadTarget(
            Edition: edition,
            Label: label,
            EnvironmentCount: matching.Length,
            Fingerprints: matching.Select(static item => item.CompatibilityFingerprint).Distinct(StringComparer.OrdinalIgnoreCase).Take(3).ToArray(),
            AccountHref: $"/account/edition-studio/{edition}",
            ApiHref: $"/api/v1/campaign-spine/me/edition-studio/heads/{edition}",
            Summary: summary);
    }

    private static string NormalizeEditionStudioHeadId(string? candidate)
    {
        string normalized = string.IsNullOrWhiteSpace(candidate) ? string.Empty : candidate.Trim().ToLowerInvariant();
        if (normalized.Contains("sr4", StringComparison.Ordinal))
        {
            return "sr4";
        }

        if (normalized.Contains("sr5", StringComparison.Ordinal))
        {
            return "sr5";
        }

        return normalized.Contains("sr6", StringComparison.Ordinal) ? "sr6" : "sr6";
    }

    private static string NormalizeLocalCoProcessorProfileId(string? candidate)
    {
        string normalized = string.IsNullOrWhiteSpace(candidate) ? string.Empty : candidate.Trim().ToLowerInvariant().Replace('-', '_');
        if (normalized.Contains("privacy", StringComparison.Ordinal))
        {
            return "privacy_first";
        }

        if (normalized.Contains("hybrid", StringComparison.Ordinal) || normalized.Contains("local", StringComparison.Ordinal))
        {
            return "hybrid_local";
        }

        return "hosted_only";
    }

    private RunControlReceipt BuildRunControlReceipt(AuthenticatedHubSubject? subject)
    {
        if (subject is null)
        {
            return new RunControlReceipt(
                Horizon: "run_control",
                Status: "shipped_mvp",
                PublicBoard: new RunControlPublicBoard(
                    SessionBoardMarkdownHref: "/run-control/packets/session_board.md",
                    SessionBoardJsonHref: "/run-control/packets/session_board.json",
                    ContinuityBoardMarkdownHref: "/run-control/packets/continuity_board.md",
                    ContinuityBoardJsonHref: "/run-control/packets/continuity_board.json"),
                SignedInDesk: new RunControlSignedInDesk(
                    AccountEntryHref: "/account/run-control",
                    AccountRedirectHref: "/account/run-control/open",
                    AccountRunHrefTemplate: "/account/run-control/{runId}",
                    DashboardApiHref: "/api/v1/campaign-spine/me/run-control/dashboard",
                    RunIndexApiHref: "/api/v1/campaign-spine/me/runs",
                    RunDetailApiHrefTemplate: "/api/v1/campaign-spine/me/run-control/runs/{runId}",
                    Summary: "Signed-in RUN CONTROL keeps live session board, active-scene continuity, and reconnect-safe history in Chummer."),
                Counts: new RunControlCounts(0, 0, 0, 0),
                LeadRun: null,
                Boundary: new RunControlBoundary(
                    CampaignTruth: "First-party only",
                    ReconnectAuthority: "Current records",
                    CollaborationReplacement: "Not claimed",
                    HiddenStateAuthority: "Not claimed"));
        }

        HubUserDto user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        InstallLinkingSummaryDto installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
        AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
        RunProjection? leadRun = summary.Runs.OrderByDescending(item => item.UpdatedAtUtc).FirstOrDefault();
        CampaignWorkspaceProjection? workspace = leadRun is null
            ? _campaignSpine.GetStarterWorkspace(user, installLinking) ?? summary.Workspaces.FirstOrDefault()
            : summary.Workspaces.FirstOrDefault(item => item.Runs.Any(candidate => string.Equals(candidate.RunId, leadRun.RunId, StringComparison.OrdinalIgnoreCase)))
                ?? _campaignSpine.GetStarterWorkspace(user, installLinking)
                ?? summary.Workspaces.FirstOrDefault();
        SceneProjection? activeScene = leadRun?.Scenes.FirstOrDefault(scene => string.Equals(scene.SceneId, leadRun.ActiveSceneId, StringComparison.OrdinalIgnoreCase));

        return new RunControlReceipt(
            Horizon: "run_control",
            Status: "shipped_mvp",
            PublicBoard: new RunControlPublicBoard(
                SessionBoardMarkdownHref: "/run-control/packets/session_board.md",
                SessionBoardJsonHref: "/run-control/packets/session_board.json",
                ContinuityBoardMarkdownHref: "/run-control/packets/continuity_board.md",
                ContinuityBoardJsonHref: "/run-control/packets/continuity_board.json"),
            SignedInDesk: new RunControlSignedInDesk(
                AccountEntryHref: "/account/run-control",
                AccountRedirectHref: "/account/run-control/open",
                AccountRunHrefTemplate: "/account/run-control/{runId}",
                DashboardApiHref: "/api/v1/campaign-spine/me/run-control/dashboard",
                RunIndexApiHref: "/api/v1/campaign-spine/me/runs",
                RunDetailApiHrefTemplate: "/api/v1/campaign-spine/me/run-control/runs/{runId}",
                Summary: "Signed-in RUN CONTROL keeps session board, active-scene continuity, and recap-safe GM history together in Chummer."),
            Counts: new RunControlCounts(
                summary.Campaigns.Count,
                summary.Workspaces.Count,
                summary.Runs.Count,
                summary.Runs.Count(item => item.RunboardContinuity is not null)),
            LeadRun: leadRun is null
                ? null
                : new RunControlTarget(
                    leadRun.RunId,
                    leadRun.Title,
                    leadRun.Status,
                    activeScene?.Title,
                    workspace?.NextSafeAction ?? leadRun.RunboardContinuity?.RunboardState.NextSafeAction ?? "Open the signed-in run desk to continue.",
                    $"/account/run-control/{Uri.EscapeDataString(leadRun.RunId)}",
                    $"/api/v1/campaign-spine/me/run-control/runs/{Uri.EscapeDataString(leadRun.RunId)}"),
            Boundary: new RunControlBoundary(
                CampaignTruth: "First-party only",
                ReconnectAuthority: "Current records",
                CollaborationReplacement: "Not claimed",
                HiddenStateAuthority: "Not claimed"));
    }

    private async Task<string> BuildOnrampPacketMarkdownAsync(string packetId, CancellationToken cancellationToken)
    {
        OnrampReceipt receipt = BuildOnrampReceipt(await TryGetOptionalPublicSurfaceSubjectAsync("/onramp", cancellationToken));
        string normalizedPacketId = string.IsNullOrWhiteSpace(packetId) ? "starter_lane" : packetId.Trim().ToLowerInvariant();
        if (normalizedPacketId == "recovery_lane")
        {
            return $$"""
# ONRAMP recovery packet

ONRAMP keeps guided recovery on Chummer paths.

## Public board

* Starter packet: `{{receipt.PublicBoard.StarterLaneJsonHref}}`
* Recovery packet: `{{receipt.PublicBoard.RecoveryLaneJsonHref}}`

## Account workspace

* Account workspace: `{{receipt.SignedInDesk.AccountEntryHref}}`
* Direct open route: `{{receipt.SignedInDesk.AccountRedirectHref}}`
* Recovery API: `{{receipt.SignedInDesk.RecoveryApiHref}}`

## Recovery posture

* Restore id: `{{receipt.Recovery.RestoreId}}`
* Claimed devices: {{receipt.Recovery.ClaimedDevices}}
* Recent restore artifacts: {{receipt.Recovery.RecentArtifacts}}
* Conflict summaries: {{receipt.Recovery.ConflictCount}}

## Boundary

ONRAMP does not claim hidden automation, automatic build changes, or off-account recovery.
""";
        }

        return $$"""
# ONRAMP starter packet

ONRAMP now ships a guided starter packet.

## Public board

* Starter packet: `{{receipt.PublicBoard.StarterLaneJsonHref}}`
* Recovery packet: `{{receipt.PublicBoard.RecoveryLaneJsonHref}}`

## Account workspace

* Account workspace: `{{receipt.SignedInDesk.AccountEntryHref}}`
* Open page: `{{receipt.SignedInDesk.AccountRedirectHref}}`
* Starter page: `{{receipt.SignedInDesk.AccountStarterHref}}`
* Dashboard API: `{{receipt.SignedInDesk.DashboardApiHref}}`
* Starter API: `{{receipt.SignedInDesk.StarterApiHref}}`

## Counts

* Campaigns: {{receipt.Counts.Campaigns}}
* Workspaces: {{receipt.Counts.Workspaces}}
* Dossiers: {{receipt.Counts.Dossiers}}
* Restore artifacts: {{receipt.Counts.RestoreArtifacts}}

## Lead starter workspace

{{(receipt.LeadStarter is null
    ? "No lead starter workspace is attached yet. Use the account workspace to move into the first playable session when the first workspace is ready."
    : $"{receipt.LeadStarter.CampaignName} is the lead starter workspace. Ruleset: {receipt.LeadStarter.RuleEnvironment}. Next safe action: {receipt.LeadStarter.NextSafeAction}")}}
""";
    }

    private async Task<string> BuildOnrampPacketJsonAsync(string packetId, CancellationToken cancellationToken)
    {
        OnrampReceipt receipt = BuildOnrampReceipt(await TryGetOptionalPublicSurfaceSubjectAsync("/onramp", cancellationToken));
        string normalizedPacketId = string.IsNullOrWhiteSpace(packetId) ? "starter_lane" : packetId.Trim().ToLowerInvariant();
        object payload = normalizedPacketId == "recovery_lane"
            ? new
            {
                horizon = receipt.Horizon,
                status = receipt.Status,
                packet = "recovery_lane",
                publicBoard = receipt.PublicBoard,
                signedInDesk = receipt.SignedInDesk,
                recovery = receipt.Recovery,
                boundary = receipt.Boundary
            }
            : new
            {
                horizon = receipt.Horizon,
                status = receipt.Status,
                packet = "starter_lane",
                publicBoard = receipt.PublicBoard,
                signedInDesk = receipt.SignedInDesk,
                counts = receipt.Counts,
                leadStarter = receipt.LeadStarter,
                recovery = receipt.Recovery,
                boundary = receipt.Boundary
            };

        return JsonSerializer.Serialize(payload, new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });
    }

    private static bool IsKnownOnrampPacketId(string? packetId)
    {
        string normalized = string.IsNullOrWhiteSpace(packetId) ? string.Empty : packetId.Trim().ToLowerInvariant();
        return normalized is "starter_lane" or "recovery_lane";
    }

    private async Task<string> BuildEditionStudioPacketMarkdownAsync(string packetId, CancellationToken cancellationToken)
    {
        EditionStudioReceipt receipt = BuildEditionStudioReceipt(await TryGetOptionalPublicSurfaceSubjectAsync("/edition-studio", cancellationToken));
        string normalizedPacketId = string.IsNullOrWhiteSpace(packetId) ? "sr5_head" : packetId.Trim().ToLowerInvariant();
        EditionStudioHeadTarget head = receipt.Heads.First(item => string.Equals(item.Edition, NormalizeEditionStudioHeadId(normalizedPacketId), StringComparison.OrdinalIgnoreCase));

        return $$"""
# EDITION STUDIO {{head.Label}} focus

EDITION STUDIO keeps {{head.Label}} authored as a distinct ruleset focus in Chummer.

## Public board

* SR4 head packet: `{{receipt.PublicBoard.Sr4HeadJsonHref}}`
* SR5 head packet: `{{receipt.PublicBoard.Sr5HeadJsonHref}}`
* SR6 head packet: `{{receipt.PublicBoard.Sr6HeadJsonHref}}`

## Account workspace

* Account workspace: `{{receipt.SignedInDesk.AccountEntryHref}}`
* Direct open route: `{{receipt.SignedInDesk.AccountRedirectHref}}`
* Head route: `{{head.AccountHref}}`
* Head API: `{{head.ApiHref}}`

## Head status

* Matching environments: {{head.EnvironmentCount}}
* Fingerprints: {{(head.Fingerprints.Count == 0 ? "none yet" : string.Join(", ", head.Fingerprints))}}

## Boundary

EDITION STUDIO does not treat decorative theming, app forks, or visual flavor as rules.
""";
    }

    private async Task<string> BuildEditionStudioPacketJsonAsync(string packetId, CancellationToken cancellationToken)
    {
        EditionStudioReceipt receipt = BuildEditionStudioReceipt(await TryGetOptionalPublicSurfaceSubjectAsync("/edition-studio", cancellationToken));
        string normalizedPacketId = string.IsNullOrWhiteSpace(packetId) ? "sr5_head" : packetId.Trim().ToLowerInvariant();
        EditionStudioHeadTarget head = receipt.Heads.First(item => string.Equals(item.Edition, NormalizeEditionStudioHeadId(normalizedPacketId), StringComparison.OrdinalIgnoreCase));
        object payload = new
        {
            horizon = receipt.Horizon,
            status = receipt.Status,
            packet = $"{head.Edition}_head",
            publicBoard = receipt.PublicBoard,
            signedInDesk = receipt.SignedInDesk,
            counts = receipt.Counts,
            head,
            boundary = receipt.Boundary
        };

        return JsonSerializer.Serialize(payload, new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });
    }

    private static bool IsKnownEditionStudioPacketId(string? packetId)
    {
        string normalized = string.IsNullOrWhiteSpace(packetId) ? string.Empty : packetId.Trim().ToLowerInvariant();
        return normalized is "sr4_head" or "sr5_head" or "sr6_head";
    }

    private async Task<string> BuildLocalCoProcessorPacketMarkdownAsync(string packetId, CancellationToken cancellationToken)
    {
        LocalCoProcessorReceipt receipt = BuildLocalCoProcessorReceipt(await TryGetOptionalPublicSurfaceSubjectAsync("/local-co-processor", cancellationToken));
        string normalizedPacketId = string.IsNullOrWhiteSpace(packetId) ? "capability_matrix" : packetId.Trim().ToLowerInvariant();
        if (normalizedPacketId == "policy_boundary")
        {
            return $$"""
# LOCAL CO-PROCESSOR policy boundary

LOCAL CO-PROCESSOR keeps local acceleration optional and fail-open.

## Public board

* Capability details: `{{receipt.PublicBoard.CapabilityMatrixJsonHref}}`
* Policy notes: `{{receipt.PublicBoard.PolicyBoundaryJsonHref}}`

## Account workspace

* Account workspace: `{{receipt.SignedInDesk.AccountEntryHref}}`
* Direct open page: `{{receipt.SignedInDesk.AccountRedirectHref}}`
* Policy API: `{{receipt.SignedInDesk.PolicyApiHref}}`

## Boundary

* Hosted-first parity: {{receipt.Boundary.HostedFirstParity}}
* Mandatory runtime: {{receipt.Boundary.MandatoryRuntime}}
* Local rules owner: {{receipt.Boundary.LocalTruthAuthority}}
* Disableable profiles: {{receipt.Boundary.DisableableProfiles}}

LOCAL CO-PROCESSOR does not turn desktop compute into a requirement, does not move rules into local runtime, and does not require a provider-specific helper to keep the product working.
""";
        }

        LocalCoProcessorProfileTarget leadProfile = receipt.Profiles.FirstOrDefault(static item => item.IsSelected) ?? receipt.Profiles.First();
        return $$"""
# LOCAL CO-PROCESSOR capability matrix

LOCAL CO-PROCESSOR keeps optional local acceleration available.

## Public board

* Capability details: `{{receipt.PublicBoard.CapabilityMatrixJsonHref}}`
* Policy notes: `{{receipt.PublicBoard.PolicyBoundaryJsonHref}}`

## Account workspace

* Account workspace: `{{receipt.SignedInDesk.AccountEntryHref}}`
* Direct open page: `{{receipt.SignedInDesk.AccountRedirectHref}}`
* Profile page template: `{{receipt.SignedInDesk.AccountProfileHrefTemplate}}`
* Capabilities API: `{{receipt.SignedInDesk.CapabilitiesApiHref}}`

## Counts

* Workspaces: {{receipt.Counts.Workspaces}}
* Dossiers: {{receipt.Counts.Dossiers}}
* Claimed devices: {{receipt.Counts.ClaimedDevices}}
* Profiles: {{receipt.Counts.Profiles}}

## Lead profile

{{leadProfile.Label}} is the current lead profile. {{leadProfile.Summary}}
""";
    }

    private async Task<string> BuildLocalCoProcessorPacketJsonAsync(string packetId, CancellationToken cancellationToken)
    {
        LocalCoProcessorReceipt receipt = BuildLocalCoProcessorReceipt(await TryGetOptionalPublicSurfaceSubjectAsync("/local-co-processor", cancellationToken));
        string normalizedPacketId = string.IsNullOrWhiteSpace(packetId) ? "capability_matrix" : packetId.Trim().ToLowerInvariant();
        object payload = normalizedPacketId == "policy_boundary"
            ? new
            {
                horizon = receipt.Horizon,
                status = receipt.Status,
                packet = "policy_boundary",
                publicBoard = receipt.PublicBoard,
                signedInDesk = receipt.SignedInDesk,
                boundary = receipt.Boundary
            }
            : new
            {
                horizon = receipt.Horizon,
                status = receipt.Status,
                packet = "capability_matrix",
                publicBoard = receipt.PublicBoard,
                signedInDesk = receipt.SignedInDesk,
                counts = receipt.Counts,
                profiles = receipt.Profiles,
                boundary = receipt.Boundary
            };

        return JsonSerializer.Serialize(payload, new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });
    }

    private static bool IsKnownLocalCoProcessorPacketId(string? packetId)
    {
        string normalized = string.IsNullOrWhiteSpace(packetId) ? string.Empty : packetId.Trim().ToLowerInvariant();
        return normalized is "capability_matrix" or "policy_boundary";
    }

    private async Task<string> BuildRunControlPacketMarkdownAsync(string packetId, CancellationToken cancellationToken)
    {
        RunControlReceipt receipt = BuildRunControlReceipt(await TryGetOptionalPublicSurfaceSubjectAsync("/run-control", cancellationToken));
        string normalizedPacketId = string.IsNullOrWhiteSpace(packetId) ? "session_board" : packetId.Trim().ToLowerInvariant();
        if (normalizedPacketId == "continuity_board")
        {
            return $$"""
# Run Control continuity packet

RUN CONTROL keeps reconnect-safe GM history in Chummer.

## Public board

* Session board packet: `{{receipt.PublicBoard.SessionBoardJsonHref}}`
* Continuity packet: `{{receipt.PublicBoard.ContinuityBoardJsonHref}}`

## Account workspace

* Account workspace: `{{receipt.SignedInDesk.AccountEntryHref}}`
* Direct open page: `{{receipt.SignedInDesk.AccountRedirectHref}}`
* Dashboard API: `{{receipt.SignedInDesk.DashboardApiHref}}`

## Lead continuity status

{{(receipt.LeadRun is null
    ? "No lead run is attached yet. RUN CONTROL stays ready to open the GM desk as soon as a live run returns."
    : $"{receipt.LeadRun.Title} is the lead run. Active scene: {receipt.LeadRun.ActiveSceneTitle ?? "none yet"}. Next safe action: {receipt.LeadRun.NextSafeAction}")}}

## Boundary

RUN CONTROL does not override hidden state, replace collaboration tools, or move the campaign off Chummer.
""";
        }

        return $$"""
# Run Control session board

RUN CONTROL keeps the GM operations page readable and current.

## Public board

* Session board packet: `{{receipt.PublicBoard.SessionBoardJsonHref}}`
* Continuity packet: `{{receipt.PublicBoard.ContinuityBoardJsonHref}}`

## Account workspace

* Account workspace: `{{receipt.SignedInDesk.AccountEntryHref}}`
* Direct open page: `{{receipt.SignedInDesk.AccountRedirectHref}}`
* Run detail template: `{{receipt.SignedInDesk.AccountRunHrefTemplate}}`
* Dashboard API: `{{receipt.SignedInDesk.DashboardApiHref}}`
* Run index API: `{{receipt.SignedInDesk.RunIndexApiHref}}`

## Counts

* Campaigns: {{receipt.Counts.Campaigns}}
* Workspaces: {{receipt.Counts.Workspaces}}
* Runs: {{receipt.Counts.Runs}}
* Continuity-backed runs: {{receipt.Counts.ContinuityRuns}}

## Lead run

{{(receipt.LeadRun is null
    ? "No lead run is attached yet. Use the account workspace to open the campaign workbench when the first session returns."
    : $"{receipt.LeadRun.Title} is the lead run. Status: {receipt.LeadRun.Status}. Active scene: {receipt.LeadRun.ActiveSceneTitle ?? "none yet"}.")}}
""";
    }

    private async Task<string> BuildRunControlPacketJsonAsync(string packetId, CancellationToken cancellationToken)
    {
        RunControlReceipt receipt = BuildRunControlReceipt(await TryGetOptionalPublicSurfaceSubjectAsync("/run-control", cancellationToken));
        string normalizedPacketId = string.IsNullOrWhiteSpace(packetId) ? "session_board" : packetId.Trim().ToLowerInvariant();
        object payload = normalizedPacketId == "continuity_board"
            ? new
            {
                horizon = receipt.Horizon,
                status = receipt.Status,
                packet = "continuity_board",
                publicBoard = receipt.PublicBoard,
                signedInDesk = receipt.SignedInDesk,
                leadRun = receipt.LeadRun,
                boundary = receipt.Boundary
            }
            : new
            {
                horizon = receipt.Horizon,
                status = receipt.Status,
                packet = "session_board",
                publicBoard = receipt.PublicBoard,
                signedInDesk = receipt.SignedInDesk,
                counts = receipt.Counts,
                leadRun = receipt.LeadRun,
                boundary = receipt.Boundary
            };

        return JsonSerializer.Serialize(payload, new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });
    }

    private static bool IsKnownRunControlPacketId(string? packetId)
    {
        string normalized = string.IsNullOrWhiteSpace(packetId) ? string.Empty : packetId.Trim().ToLowerInvariant();
        return normalized is "session_board" or "continuity_board";
    }

    private async Task<string> BuildQuicksilverPacketMarkdownAsync(string packetId, CancellationToken cancellationToken)
    {
        QuicksilverCommandDeckReceipt receipt = BuildQuicksilverCommandDeckReceipt(await TryGetOptionalPublicSurfaceSubjectAsync("/quicksilver", cancellationToken));
        string normalizedPacketId = string.IsNullOrWhiteSpace(packetId) ? "command_deck" : packetId.Trim().ToLowerInvariant();
        if (normalizedPacketId == "jump_targets")
        {
            return $$"""
# Quicksilver jump targets

The typed jump view stays focused:

{{string.Join("\n", receipt.FocusTargets.Select(target => $"- {target.Label}: focus {target.FocusHref} | api {target.ApiHref} | {(target.Available ? "live" : "ready")}"))}}
""";
        }

        return $$"""
# Quicksilver jump guide

Quicksilver keeps expert-speed jumps inside Chummer.

- Build handoffs: {{receipt.FocusTargets[0].FocusHref}}
- Rules answers: {{receipt.FocusTargets[1].FocusHref}}
- Prep benches: {{receipt.FocusTargets[2].FocusHref}}
- Creator desk: {{receipt.FocusTargets[3].FocusHref}}
- JACKPOINT desk: {{receipt.FocusTargets[4].FocusHref}}

Boundary:
- legality still visible
- explainability still required
- no background mutation authority
- no cache authority
""";
    }

    private async Task<string> BuildQuicksilverPacketJsonAsync(string packetId, CancellationToken cancellationToken)
    {
        QuicksilverCommandDeckReceipt receipt = BuildQuicksilverCommandDeckReceipt(await TryGetOptionalPublicSurfaceSubjectAsync("/quicksilver", cancellationToken));
        string normalizedPacketId = string.IsNullOrWhiteSpace(packetId) ? "command_deck" : packetId.Trim().ToLowerInvariant();
        object payload = normalizedPacketId switch
        {
            "jump_targets" => new
            {
                packetId = "jump_targets",
                horizon = receipt.Horizon,
                status = receipt.Status,
                targets = receipt.FocusTargets
            },
            _ => new
            {
                packetId = "command_deck",
                horizon = receipt.Horizon,
                status = receipt.Status,
                publicBoard = receipt.PublicBoard,
                signedInBench = receipt.SignedInBench,
                counts = receipt.Counts,
                focusTargets = receipt.FocusTargets,
                boundary = receipt.Boundary
            }
        };

        return JsonSerializer.Serialize(payload, new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });
    }

    private static bool IsKnownQuicksilverPacketId(string? packetId)
    {
        string normalized = string.IsNullOrWhiteSpace(packetId) ? string.Empty : packetId.Trim().ToLowerInvariant();
        return normalized is "command_deck" or "jump_targets";
    }

    private sealed record RunControlPublicBoard(
        string SessionBoardMarkdownHref,
        string SessionBoardJsonHref,
        string ContinuityBoardMarkdownHref,
        string ContinuityBoardJsonHref);

    private sealed record OnrampPublicBoard(
        string StarterLaneMarkdownHref,
        string StarterLaneJsonHref,
        string RecoveryLaneMarkdownHref,
        string RecoveryLaneJsonHref);

    private sealed record OnrampSignedInDesk(
        string AccountEntryHref,
        string AccountRedirectHref,
        string AccountStarterHref,
        string DashboardApiHref,
        string StarterApiHref,
        string RecoveryApiHref,
        string Summary);

    private sealed record OnrampCounts(
        int Campaigns,
        int Workspaces,
        int Dossiers,
        int RestoreArtifacts);

    private sealed record OnrampStarterTarget(
        string WorkspaceId,
        string CampaignName,
        string RuleEnvironment,
        string NextSafeAction,
        string AccountHref,
        string ApiHref);

    private sealed record OnrampRecoveryTarget(
        string RestoreId,
        int ClaimedDevices,
        int RecentArtifacts,
        int ConflictCount,
        string AccountHref,
        string ApiHref);

    private sealed record OnrampBoundary(
        string BuildTruth,
        string HiddenAutomation,
        string AutoBuildAuthority,
        string RecoveryAuthority);

    private sealed record OnrampReceipt(
        string Horizon,
        string Status,
        OnrampPublicBoard PublicBoard,
        OnrampSignedInDesk SignedInDesk,
        OnrampCounts Counts,
        OnrampStarterTarget? LeadStarter,
        OnrampRecoveryTarget Recovery,
        OnrampBoundary Boundary);

    private sealed record EditionStudioPublicBoard(
        string Sr4HeadMarkdownHref,
        string Sr4HeadJsonHref,
        string Sr5HeadMarkdownHref,
        string Sr5HeadJsonHref,
        string Sr6HeadMarkdownHref,
        string Sr6HeadJsonHref);

    private sealed record EditionStudioSignedInDesk(
        string AccountEntryHref,
        string AccountRedirectHref,
        string AccountHeadHrefTemplate,
        string HeadsApiHref,
        string HeadDetailApiHrefTemplate,
        string Summary);

    private sealed record EditionStudioCounts(
        int Workspaces,
        int Dossiers,
        int RuleEnvironments);

    private sealed record EditionStudioHeadTarget(
        string Edition,
        string Label,
        int EnvironmentCount,
        IReadOnlyList<string> Fingerprints,
        string AccountHref,
        string ApiHref,
        string Summary);

    private sealed record EditionStudioBoundary(
        string RulesTruth,
        string DecorativeThemingAuthority,
        string AppForkAuthority,
        string VisualFlavorAuthority);

    private sealed record EditionStudioReceipt(
        string Horizon,
        string Status,
        EditionStudioPublicBoard PublicBoard,
        EditionStudioSignedInDesk SignedInDesk,
        EditionStudioCounts Counts,
        IReadOnlyList<EditionStudioHeadTarget> Heads,
        EditionStudioBoundary Boundary);

    private sealed record LocalCoProcessorPublicBoard(
        string CapabilityMatrixMarkdownHref,
        string CapabilityMatrixJsonHref,
        string PolicyBoundaryMarkdownHref,
        string PolicyBoundaryJsonHref);

    private sealed record LocalCoProcessorSignedInDesk(
        string AccountEntryHref,
        string AccountRedirectHref,
        string AccountProfileHrefTemplate,
        string CapabilitiesApiHref,
        string PolicyApiHref,
        string Summary);

    private sealed record LocalCoProcessorCounts(
        int Workspaces,
        int Dossiers,
        int ClaimedDevices,
        int Profiles);

    private sealed record LocalCoProcessorProfileTarget(
        string Profile,
        string Label,
        bool IsSelected,
        string AccountHref,
        string ApiHref,
        string Summary);

    private sealed record LocalCoProcessorBoundary(
        string HostedFirstParity,
        string MandatoryRuntime,
        string LocalTruthAuthority,
        string DisableableProfiles);

    private sealed record LocalCoProcessorReceipt(
        string Horizon,
        string Status,
        LocalCoProcessorPublicBoard PublicBoard,
        LocalCoProcessorSignedInDesk SignedInDesk,
        LocalCoProcessorCounts Counts,
        IReadOnlyList<LocalCoProcessorProfileTarget> Profiles,
        LocalCoProcessorBoundary Boundary);

    private sealed record RunControlSignedInDesk(
        string AccountEntryHref,
        string AccountRedirectHref,
        string AccountRunHrefTemplate,
        string DashboardApiHref,
        string RunIndexApiHref,
        string RunDetailApiHrefTemplate,
        string Summary);

    private sealed record RunControlCounts(
        int Campaigns,
        int Workspaces,
        int Runs,
        int ContinuityRuns);

    private sealed record RunControlTarget(
        string RunId,
        string Title,
        string Status,
        string? ActiveSceneTitle,
        string NextSafeAction,
        string AccountHref,
        string ApiHref);

    private sealed record RunControlBoundary(
        string CampaignTruth,
        string ReconnectAuthority,
        string CollaborationReplacement,
        string HiddenStateAuthority);

    private sealed record RunControlReceipt(
        string Horizon,
        string Status,
        RunControlPublicBoard PublicBoard,
        RunControlSignedInDesk SignedInDesk,
        RunControlCounts Counts,
        RunControlTarget? LeadRun,
        RunControlBoundary Boundary);

    private sealed record QuicksilverPublicBoard(
        string CommandDeckMarkdownHref,
        string CommandDeckJsonHref,
        string JumpTargetsMarkdownHref,
        string JumpTargetsJsonHref);

    private sealed record QuicksilverSignedInBench(
        string AccountEntryHref,
        string AccountRedirectHref,
        string FocusHrefTemplate,
        string CommandDeckApiHref,
        string JumpTargetsApiHref,
        string Summary);

    private sealed record QuicksilverCounts(
        int BuildHandoffs,
        int RulesAnswers,
        int Workspaces,
        int Publications);

    private sealed record QuicksilverFocusTarget(
        string Focus,
        string Label,
        bool Available,
        string FocusHref,
        string ApiHref,
        string Summary);

    private sealed record QuicksilverBoundary(
        string RulesTruth,
        string BulkMutationAuthority,
        string BackgroundAutomation,
        string CacheAuthority);

    private sealed record QuicksilverCommandDeckReceipt(
        string Horizon,
        string Status,
        QuicksilverPublicBoard PublicBoard,
        QuicksilverSignedInBench SignedInBench,
        QuicksilverCounts Counts,
        IReadOnlyList<QuicksilverFocusTarget> FocusTargets,
        QuicksilverBoundary Boundary);

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
            VerdictSummary: "Chummer now keeps role status, starter loadouts, session files, and mobile setup in one place.",
            SummaryPoints:
            [
                "Role-aware readiness verdicts",
                "Starter loadouts with downloadable JSON",
                "Printable packets and mobile setup"
            ],
            Verdicts: verdicts,
            RoleKits: kits,
            Packets: packets,
            PrimaryAction: new TrustPageActionViewModel("Download player notes", "/ready/packet/player.md", "primary"),
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
            Title: "Sample campaign amendment request",
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
                    new("karma_request_submitted", "karma_forge_discovery", "hrp_2026_05_09_sample_karma_forge", "The public discovery request entered the KARMA FORGE intake."),
                    new("karma_interview_completed", "karma_forge_discovery", "hrp_2026_05_09_sample_karma_forge", "Guided follow-up completed inside the KARMA FORGE review path."),
                    new("karma_demand_packet_created", "karma_forge_discovery", "hrp_2026_05_09_sample_karma_forge", "The intake became a Chummer request before product review."),
                    new("karma_candidate_reviewed", "karma_forge_discovery", "hrp_2026_05_09_sample_karma_forge", "The request is visible on the review path instead of staying with an outside tool.")
                ]),
            UserWords: new KarmaForgeUserWordsProjection(
                Summary: "We need a table amendment that survives continuity and rollback without hiding the approval trail.",
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
                CandidateDecisionMeaning: "Needs a campaign package path before broader rollout.",
                ProposedRoute: "KARMA_FORGE"),
            NextSteps:
            [
                "Review the campaign scope and rollback posture.",
                "Attach compatibility and portability notes before approval.",
                "Keep the public note limited to Chummer-owned request language."
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
            CandidateDecisionMeaning: "Needs a campaign package path before broader rollout.",
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
            QueueSummary: "Sample request saved through the KARMA FORGE submission route.",
            ReporterNextAction: "Open the campaign decision path when you need the next review step.",
            ConsentSummary: "Sample seeded record with follow-up and quote posture enabled for this route.",
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
                "First session",
                "Open work and start your first playable session",
                "Your install is linked. Open your workspace to move from setup into the next safe session before returning to optional tasks.",
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
                "Installs",
                "Link this copy",
                "You already have a pending linked install. Open Installs to claim this copy instead of starting over.",
                "Open installs",
                "/account/access",
                "primary");
        }

        return new HomePrimaryActionViewModel(
            "Current release",
            "Stay on the current release",
            "Open the current release, your linked devices, and what changed before you spend attention on optional contribution work.",
            "Open current release",
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
                    ? $"{campaignName} can reopen this runner from the same shared dossier."
                    : dossier.LatestContinuity!.Summary;
                string provenanceSummary = $"{dossier.RuleEnvironment.CompatibilityFingerprint} + {continuitySummary}";
                string auditSummary = dossier.LatestContinuity is null
                    ? "No continuity snapshot is attached yet."
                    : $"Continuity snapshot {dossier.LatestContinuity.SnapshotId} was captured at {dossier.LatestContinuity.CapturedAtUtc:yyyy-MM-dd HH:mm} UTC.";
                return new RecapShelfEntry(
                    EntryId: $"dossier:{dossier.DossierId}",
                    Kind: "dossier_projection",
                    Label: $"{dossier.DisplayName} dossier",
                    Summary: continuitySummary,
                    ArtifactId: dossier.DossierId,
                    UpdatedAtUtc: dossier.UpdatedAtUtc,
                    Audience: "personal,campaign",
                    OwnershipSummary: $"{campaignName} reuses the same shared dossier on the account path instead of forking a shadow copy.",
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
        "personal" => "Personal shelf view keeps account-side runner history and continuity together.",
        "campaign" => "Campaign shelf view keeps shared continuity, replay, and aftermath together.",
        "creator" => "Creator shelf view keeps creator-linked lineage, publication status, and sibling items together.",
        "public" => "Public shelf view keeps published creator items and their public detail routes together.",
        _ => "All shelf views keep personal, campaign, creator, and public history easy to inspect from one route."
    };

    private static string GuestArtifactViewSummaryForApi(string view) => view switch
    {
        "creator" => "Guest creator shelf view keeps discoverable creator items, related items, and publication status together on the public page.",
        "public" => "Guest public view keeps status cards, preview status, and published creator items together on one page.",
        "personal" => "Personal shelf view requires a signed-in account before private return items can appear.",
        "campaign" => "Campaign shelf view requires a signed-in account before shared continuity items can appear.",
        _ => "Public status, preview status, and publication discovery stay together on one page."
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
            _ => "Signed-in history packet"
        };

    private static string BuildCreatorPublicationCaption(CreatorPublicationProjection publication, bool publicOnly)
        => publicOnly
            ? "Published shared-publication packet"
            : string.Equals(publication.PublicationStatus, HubPublicationStates.Published, StringComparison.OrdinalIgnoreCase)
                ? "Creator item is already live on the public page"
                : "Creator item is still moving through review"
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
            new SectionLinkViewModel("access", "Installs", "/home/access", string.Equals(currentSection, "access", StringComparison.OrdinalIgnoreCase)),
            new SectionLinkViewModel("work", "Work", "/home/work", string.Equals(currentSection, "work", StringComparison.OrdinalIgnoreCase)),
            new SectionLinkViewModel("setup", "Setup", "/home/setup", string.Equals(currentSection, "setup", StringComparison.OrdinalIgnoreCase))
        };

    private static (string Title, string Description) DescribeHomeSection(string currentSection)
        => currentSection switch
        {
            "access" => ("Home · Installs", "Linked copies, setup codes, downloads, and install help."),
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

    private string ProtectHorizonArtifactDispatchTarget(string dispatchTarget)
        => _artifactAccessTokens?.IssueProtectedUrl(dispatchTarget) ?? dispatchTarget;

    private BlackLedgerWorldTurnBriefingViewModel? BuildProtectedBlackLedgerWorldTurnBriefing(int? requestedTurn)
    {
        BlackLedgerWorldTurnBriefingViewModel? briefing = _blackLedgerBriefings.BuildWorldTurnBriefing(requestedTurn);
        if (briefing?.Broadcast is null)
        {
            return briefing;
        }

        return briefing with
        {
            Broadcast = ProtectBlackLedgerBroadcast(briefing.Broadcast)
        };
    }

    private BlackLedgerNewsreelBroadcastViewModel? ProtectBlackLedgerBroadcast(BlackLedgerNewsreelBroadcastViewModel? broadcast)
        => broadcast is null
            ? null
            : broadcast with
            {
                VideoMp4Href = ProtectHorizonArtifactDispatchTarget(broadcast.VideoMp4Href),
                VideoWebmHref = ProtectHorizonArtifactDispatchTarget(broadcast.VideoWebmHref),
                PosterHref = ProtectHorizonArtifactDispatchTarget(broadcast.PosterHref),
                CaptionsHref = ProtectHorizonArtifactDispatchTarget(broadcast.CaptionsHref)
            };

    private BlackLedgerFactionPromoArtifactViewModel BuildPublicFactionPromoArtifact(BlackLedgerFactionPromoArtifactViewModel promo)
    {
        string renderMode = string.Equals(promo.ProviderStatus, "VERIFIED_PROVIDER", StringComparison.OrdinalIgnoreCase)
            ? "verified_cinematic_faction_bulletin"
            : "first_party_motion_video";
        string playbackLabel = string.Equals(promo.ProviderStatus, "VERIFIED_PROVIDER", StringComparison.OrdinalIgnoreCase)
            ? "Playable verified faction reel"
            : promo.PlaybackLabel;
        string narratorPosture = ReplacePublicVendorTruth(promo.NarratorPosture);
        string renderPipelineLabel = ReplacePublicVendorTruth(promo.RenderPipelineLabel)
            .Replace("Verified scene render", "Verified cinematic render", StringComparison.OrdinalIgnoreCase);
        string audiencePromise = ReplacePublicVendorTruth(promo.AudiencePromise)
            .Replace("rendered cinematic faction reel", "cinematic faction reel", StringComparison.OrdinalIgnoreCase);
        string storylineSummary = ReplacePublicVendorTruth(promo.StorylineSummary);
        string campaignHook = ReplacePublicVendorTruth(promo.CampaignHook);
        string[] formatLabels = promo.FormatLabels
            .Select(ReplacePublicVendorTruth)
            .Select(label => label.Replace("Verified-rendered", "Verified", StringComparison.OrdinalIgnoreCase))
            .ToArray();
        return promo with
        {
            RenderMode = renderMode,
            FallbackRenderMode = "storyboard_fallback",
            NarratorPosture = narratorPosture,
            RenderPipelineLabel = renderPipelineLabel,
            PlaybackLabel = playbackLabel,
            FormatLabels = formatLabels,
            StorylineSummary = storylineSummary,
            CampaignHook = campaignHook,
            AudiencePromise = audiencePromise,
            PosterHref = ProtectHorizonArtifactDispatchTarget(promo.PosterHref),
            VideoMp4Href = ProtectHorizonArtifactDispatchTarget(promo.VideoMp4Href),
            VideoWebmHref = ProtectHorizonArtifactDispatchTarget(promo.VideoWebmHref)
        };
    }

    private static string ReplacePublicVendorTruth(string value)
        => value
            .Replace("MagicFit-rendered", "Verified", StringComparison.OrdinalIgnoreCase)
            .Replace("MagicFit scene render", "Verified scene render", StringComparison.OrdinalIgnoreCase)
            .Replace("MagicFit scene composite", "verified scene composite", StringComparison.OrdinalIgnoreCase)
            .Replace("MagicFit", "Verified", StringComparison.OrdinalIgnoreCase);

    private async Task<IActionResult?> TryCreatePublicArtifactReceiptAsync(
        string operationLabel,
        string currentPath,
        string sourceRef,
        string horizonId,
        string artifactKindOrCapabilityId,
        CancellationToken cancellationToken)
    {
        if (_artifactRequests is null)
        {
            _logger.LogWarning("{Operation} public route could not record a shared artifact request because the request service is unavailable for {Path}.", operationLabel, currentPath);
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "Shared horizon artifact request service is not available right now.");
        }

        AuthenticatedHubSubject? subject = await TryGetOptionalPublicSurfaceSubjectAsync(currentPath, cancellationToken);
        try
        {
            HorizonArtifactRequestReceipt receipt = _artifactRequests.BuildRequest(
                new HorizonArtifactRequestCreateRequest(
                    HorizonId: horizonId,
                    ArtifactKindOrCapabilityId: artifactKindOrCapabilityId,
                    UserId: subject?.SubjectId ?? string.Empty,
                    SourceRef: sourceRef,
                    Visibility: "public_safe",
                    ExternalProcessingConsent: true,
                    Email: subject?.Email),
                consumeQuota: false,
                requireRequestingUser: false);

            if (!string.Equals(receipt.Status, "accepted", StringComparison.OrdinalIgnoreCase))
            {
                _logger.LogWarning(
                    "{Operation} public route denied for {Path}; blocked reasons: {BlockedReasons}.",
                    operationLabel,
                    currentPath,
                    string.Join(", ", receipt.BlockedReasons));
                return Problem(statusCode: StatusCodes.Status400BadRequest, detail: $"Unable to create a Chummer-owned {operationLabel} request receipt.");
            }

            if (HttpContext?.Response?.Headers is { } responseHeaders)
            {
                responseHeaders["X-Horizon-Artifact-Request-Id"] = receipt.RequestId;
                responseHeaders["X-Horizon-Artifact-Request-Href"] = $"/api/v1/public/horizons/artifact-requests/{Uri.EscapeDataString(receipt.RequestId)}";
            }
            return null;
        }
        catch (InvalidOperationException ex)
        {
            _logger.LogWarning(ex, "{Operation} public route failed while recording shared artifact request for {Path}.", operationLabel, currentPath);
            return Problem(statusCode: StatusCodes.Status500InternalServerError, detail: $"Unable to process {operationLabel} request right now.");
        }
    }

    private async Task<IActionResult> BuildCommunityCreatorReceiptJsonAsync(
        string operationLabel,
        string currentPath,
        string horizonId,
        string artifactKindOrCapabilityId,
        string receiptId,
        IReadOnlyList<CommunityCreatorDocument> documents,
        Func<string, string> buildJson,
        CancellationToken cancellationToken)
    {
        if (!IsKnownCommunityCreatorDocumentId(documents, receiptId))
        {
            return NotFound();
        }

        string normalizedReceiptId = NormalizeRouteToken(receiptId);
        string sourceRef = $"{horizonId}:{normalizedReceiptId}";
        IActionResult? receiptFailure = await TryCreatePublicArtifactReceiptAsync(
            operationLabel,
            currentPath,
            sourceRef,
            horizonId,
            artifactKindOrCapabilityId,
            cancellationToken);
        if (receiptFailure is not null)
        {
            return receiptFailure;
        }

        string json = buildJson(normalizedReceiptId);
        string payload = AppendPublicArtifactMetadataJson(json, horizonId, artifactKindOrCapabilityId, sourceRef);
        return Content(payload, "application/json");
    }

    private string AppendPublicArtifactMetadataJson(
        string json,
        string horizonId,
        string artifactKindOrCapabilityId,
        string sourceRef)
    {
        JsonNode? node = JsonNode.Parse(json);
        if (node is not JsonObject payload)
        {
            return json;
        }

        payload["artifact_capability"] = BuildPublicArtifactCapabilityNode(horizonId, artifactKindOrCapabilityId, sourceRef);
        payload["shared_artifacts"] = BuildSharedArtifactSurfaceRoutesNode(horizonId, artifactKindOrCapabilityId);
        return payload.ToJsonString(PublicJsonContentOptions);
    }

    private JsonObject BuildPublicArtifactCapabilityNode(
        string horizonId,
        string artifactKindOrCapabilityId,
        string sourceRef)
        => _horizonCapabilities.BuildPublicCapabilityJsonNode(horizonId, artifactKindOrCapabilityId, sourceRef);

    private static bool IsKnownCommunityCreatorDocumentId(IReadOnlyList<CommunityCreatorDocument> documents, string? documentId)
    {
        string normalizedDocumentId = NormalizeRouteToken(documentId);
        return !string.IsNullOrWhiteSpace(normalizedDocumentId)
            && documents.Any(item => string.Equals(item.Id, normalizedDocumentId, StringComparison.OrdinalIgnoreCase));
    }

    private static string NormalizeRouteToken(string? value)
        => string.IsNullOrWhiteSpace(value) ? string.Empty : value.Trim();

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
            microProof.Add("Desktop polish gap: desktop_client");
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
            new("Release status", BuildReleaseProofSummary(manifest)),
            new("Launch readiness", BuildTrustPulseLaunchReadinessSummary(pulse)),
            new("Provider status", BuildProviderRouteStewardshipSummary(pulse)),
            new("Closure health", BuildTrustPulseClosureHealthSummary(pulse)),
            new("Adoption health", BuildTrustPulseAdoptionSummary(pulse)),
            new("Progress trend", BuildTrustPulseProgressTrendSummary(pulse)),
            new("Journey pulse", BuildJourneyPulseSummary(pulse)),
            new("Current caution", BuildTrustPulseCautionSummary(pulse))
        };

        string journeyState = HumanizeToken(pulse.JourneyGateState, "Current");
        string heading = string.IsNullOrWhiteSpace(pulse.LongestPoleLabel)
            ? $"{journeyState} status this week"
            : $"{journeyState} status; {pulse.LongestPoleLabel} still needs caution";
        string summary = string.IsNullOrWhiteSpace(pulse.Summary)
            ? "The weekly pulse keeps release status, journey progress, and current caution visible in one clear panel."
            : pulse.Summary;
        var trendSamples = BuildTrustPulseTrendSamples(pulse);

        return new PublicTrustPulsePanelViewModel(
            Eyebrow: "Weekly status",
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

    private async Task<LandingOpenRailViewModel?> BuildLandingOpenRailAsync(
        AccountCampaignSummary? campaignSpine,
        CancellationToken cancellationToken)
    {
        var subject = await TryGetOptionalPublicSurfaceSubjectAsync("/", cancellationToken);
        if (subject is null)
        {
            return null;
        }

        var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
        bool hasLinkedDesktop = (installLinking.ClaimedInstallations?.Count ?? 0) > 0
            || (installLinking.ActiveGrants?.Count ?? 0) > 0
            || installLinking.PendingClaimTickets.Count > 0;

        IReadOnlyList<LandingOpenRailItemViewModel> items = BuildLandingOpenRailItems(campaignSpine, hasLinkedDesktop);
        if (items.Count == 0)
        {
            return null;
        }

        string summary = hasLinkedDesktop
            ? "Open your current runner, current campaign, or a starter example in the app."
            : "Pick what you want to open. If this account has not linked a desktop copy yet, the click will continue into install and account linking.";

        return new LandingOpenRailViewModel(
            Heading: "Open in Chummer",
            Summary: summary,
            Items: items);
    }

    private static IReadOnlyList<LandingOpenRailItemViewModel> BuildLandingOpenRailItems(
        AccountCampaignSummary? campaignSpine,
        bool hasLinkedDesktop)
    {
        List<LandingOpenRailItemViewModel> items = new(capacity: 4);

        if (campaignSpine is not null)
        {
            foreach (var dossier in campaignSpine.Dossiers
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .Take(3))
            {
                items.Add(new LandingOpenRailItemViewModel(
                    Label: dossier.DisplayName,
                    Summary: string.IsNullOrWhiteSpace(dossier.LatestContinuity?.Summary)
                        ? "Open this runner in the desktop app."
                        : dossier.LatestContinuity!.Summary,
                    Href: $"/account/open/character/{Uri.EscapeDataString(dossier.DossierId)}",
                    Kind: "Character"));
            }

            if (items.Count == 0)
            {
                foreach (var workspace in campaignSpine.Workspaces
                    .OrderByDescending(static item => ResolveLandingWorkspaceFreshnessUtc(item))
                    .Take(2))
                {
                    items.Add(new LandingOpenRailItemViewModel(
                        Label: workspace.CampaignName,
                        Summary: workspace.ReturnSummary,
                        Href: $"/account/open/campaign/{Uri.EscapeDataString(workspace.CampaignId)}",
                        Kind: "Campaign"));
                }
            }
        }

        if (items.Count == 0)
        {
            items.AddRange(GetLandingExampleOpenRailItems());
        }

        if (!hasLinkedDesktop)
        {
            items = items
                .Select(static item => item with
                {
                    Summary = $"{item.Summary} Install and account linking continue automatically when no linked desktop copy is available."
                })
                .ToList();
        }

        return items;
    }

    private static DateTimeOffset ResolveLandingWorkspaceFreshnessUtc(CampaignWorkspaceProjection workspace)
    {
        ArgumentNullException.ThrowIfNull(workspace);

        return new[] { workspace.LatestContinuity?.CapturedAtUtc, workspace.NextSessionCarryForward?.UpdatedAtUtc }
            .Concat((workspace.Runs ?? Array.Empty<RunProjection>()).Select(static item => (DateTimeOffset?)item.UpdatedAtUtc))
            .Concat((workspace.ChangePackets ?? Array.Empty<WorkspaceChangePacketProjection>()).Select(static item => (DateTimeOffset?)item.UpdatedAtUtc))
            .Concat((workspace.Consequences ?? Array.Empty<CampaignConsequenceProjection>()).Select(static item => (DateTimeOffset?)item.UpdatedAtUtc))
            .Concat((workspace.RosterTransfers ?? Array.Empty<RosterTransferProjection>()).Select(static item => (DateTimeOffset?)item.TransferredAtUtc))
            .Concat((workspace.PrepLaunches ?? Array.Empty<GovernedPrepLaunchProjection>()).Select(static item => (DateTimeOffset?)item.LaunchedAtUtc))
            .Concat((workspace.TravelPrefetches ?? Array.Empty<TravelPrefetchReceiptProjection>()).Select(static item => (DateTimeOffset?)item.StagedAtUtc))
            .Concat((workspace.AftermathPackages ?? Array.Empty<AftermathRecapPackageProjection>()).Select(static item => (DateTimeOffset?)item.GeneratedAtUtc))
            .Where(static item => item.HasValue)
            .Select(static item => item!.Value)
            .DefaultIfEmpty(DateTimeOffset.MinValue)
            .Max();
    }

    private static IReadOnlyList<LandingOpenRailItemViewModel> GetLandingExampleOpenRailItems()
        =>
        [
            new(
                Label: "Street Samurai",
                Summary: "Cybered frontline runner with straightforward combat pressure.",
                Href: "/account/open/example/street-samurai",
                Kind: "Example"),
            new(
                Label: "Decker",
                Summary: "Matrix intrusion starter with logic, gear, and host-first momentum.",
                Href: "/account/open/example/decker",
                Kind: "Example"),
            new(
                Label: "Combat Mage",
                Summary: "Awakened caster with direct action and visible spell tradeoffs.",
                Href: "/account/open/example/combat-mage",
                Kind: "Example"),
            new(
                Label: "Face",
                Summary: "Social operator focused on negotiation, cover, and team access.",
                Href: "/account/open/example/face",
                Kind: "Example")
        ];

    private BuildGhostConciergeTeaserViewModel BuildBuildGhostConciergeTeaser()
    {
        BuildGhostConciergeProjection projection = _buildGhostConcierge.Build();
        return new BuildGhostConciergeTeaserViewModel(
            StatusLabel: "Character compare bench",
            Summary: projection.HumanizedSummary,
            Href: "/alice",
            ProofPoints:
            [
                projection.FacePopStatus,
                projection.AnswerlyStatus,
                projection.EngineStatus
            ]);
    }

    private async Task<BuildGhostConciergePageViewModel> BuildBuildGhostConciergePageModel(
        CancellationToken cancellationToken,
        string currentPath = "/participate/build-ghosts",
        string title = "Character helper",
        string eyebrow = "Private preview",
        string heading = "A helper can orient you. Chummer still makes the character decisions.",
        string intro = "This page is the public preview for character-helper experiments. It keeps intake, explanation, comparison, and final apply decisions clearly separated.")
    {
        BuildGhostConciergeProjection projection = _buildGhostConcierge.Build();
        AuthenticatedHubSubject? subject = await TryGetOptionalPublicSurfaceSubjectAsync(currentPath, cancellationToken);
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var chrome = await BuildPublicOrAuthenticatedChromeAsync(
            title,
            "Public intake and explanation for character help, with Chummer keeping the actual character decisions.",
            currentPath,
            cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), chrome.Authenticated);
        return new BuildGhostConciergePageViewModel(
            Chrome: chrome,
            Eyebrow: eyebrow,
            Heading: heading,
            Intro: intro,
            Projection: projection,
            SignedInBench: BuildBuildGhostSignedInBench(subject),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
    }

    private BuildGhostSignedInBenchViewModel? BuildBuildGhostSignedInBench(AuthenticatedHubSubject? subject)
    {
        if (subject is null)
        {
            return null;
        }

        HubUserDto user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        InstallLinkingSummaryDto installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
        BuildLabHandoffProjection? leadHandoff = _campaignSpine
            .GetAccountSummary(user, installLinking)
            .BuildLabHandoffs
            .OrderByDescending(item => item.UpdatedAtUtc)
            .FirstOrDefault();

        if (leadHandoff is null)
        {
            return new BuildGhostSignedInBenchViewModel(
                StatusLabel: "Signed in, waiting for a build handoff",
                Summary: "Character help is ready as soon as a runner, workspace, or guided build path has produced a build handoff.",
                EntryHref: "/account/alice/open",
                EntryLabel: "Open character help",
                LeadHandoffHref: "/account/work",
                LeadHandoffTitle: "No build handoff yet",
                LeadHandoffSummary: "Create or restore a runner, then return here to inspect compare history, planner coverage, and safe output paths.",
                ProofPoints:
                [
                    "Account-owned next step",
                    "Only Chummer applies changes",
                    "Records stay with Chummer"
                ]);
        }

        string[] proofPoints =
        [
            leadHandoff.NextSafeAction ?? "Variants stay parked until you deliberately continue.",
            leadHandoff.PlannerCoverageSummary ?? "Planner coverage stays attached to the build handoff.",
            leadHandoff.RuntimeCompatibilitySummary ?? "Runtime compatibility stays on the Chummer build handoff."
        ];

        return new BuildGhostSignedInBenchViewModel(
            StatusLabel: "Signed-in helper ready",
            Summary: "Your account already has a build handoff. Open character help to inspect tradeoffs, planner coverage, rules setup changes, and output history on the account page.",
            EntryHref: "/account/alice/open",
            EntryLabel: "Open character help",
            LeadHandoffHref: $"/account/alice/{Uri.EscapeDataString(leadHandoff.HandoffId)}",
            LeadHandoffTitle: leadHandoff.Title,
            LeadHandoffSummary: leadHandoff.Summary,
            ProofPoints: proofPoints.Where(static item => !string.IsNullOrWhiteSpace(item)).ToArray());
    }

    private BeHumanEventAdapterPanelViewModel BuildBeHumanEventAdapterPanel()
    {
        BeHumanEventAdapterPosture posture = _beHumanEventAdapterPosture.Build();
        string summary = posture.Verdict switch
        {
            "BEHUMAN_EVENT_ADAPTER_READY" when posture.CapacityClaimAllowed && posture.VerifiedRegistrationCapacity is > 0
                => $"BeHuman is allowed only as a verified event venue layer. Current verified registration capacity is limited to {posture.VerifiedRegistrationCapacity.Value} seats and does not decide anything outside community events.",
            "BEHUMAN_EVENT_ADAPTER_READY"
                => "BeHuman is allowed only as a verified event venue layer. Capacity remains intentionally unclaimed until a verified registration bound is attached.",
            _
                => posture.FailureReason ?? "BeHuman event routing stays off until Chummer has verified setup and the required operating secrets."
        };

        string statusLabel = posture.Verdict == "BEHUMAN_EVENT_ADAPTER_READY"
            ? "Verified event venue only"
            : "Fail-closed until verified";

        return new BeHumanEventAdapterPanelViewModel(
            Verdict: posture.Verdict,
            StatusLabel: statusLabel,
            Summary: summary,
            OperatingMode: posture.OperatingMode,
            CapacityClaimAllowed: posture.CapacityClaimAllowed,
            VerifiedRegistrationCapacity: posture.VerifiedRegistrationCapacity,
            AllowedEventFamilies: posture.AllowedEventFamilies,
            ForbiddenTruthDomains: posture.ForbiddenTruthDomains);
    }

    private async Task<IActionResult> BuildGmSessionVenuePage(
        string section,
        string campaignId,
        string sessionId,
        string currentPath,
        CancellationToken cancellationToken)
    {
        try
        {
            AuthenticatedHubSubject subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            HubUserDto user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            GmSessionVenueSurfaceProjection venue = _gmSessionVenues.DescribeVenue(user.UserId, campaignId, sessionId, requireManage: section != "overview");
            var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
            var chrome = await BuildPublicOrAuthenticatedChromeAsync("Session venue", "Manage the live room without exposing private campaign details.", currentPath, cancellationToken);
            var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), chrome.Authenticated);
            GmSessionVenuePageViewModel model = new(
                Chrome: chrome,
                Section: section,
                CampaignId: venue.CampaignId,
                CampaignName: venue.CampaignName,
                SessionId: venue.SessionId,
                SessionTitle: venue.SessionTitle,
                VenueStatus: venue.VenueStatus,
                Provider: venue.Provider,
                Mode: venue.Mode,
                Visibility: venue.Visibility,
                ScheduledTimeSummary: venue.ScheduledTimeSummary,
                PrivacyStatus: venue.PrivacyStatus,
                ConsentStatus: venue.ConsentStatus,
                AttendeeSyncStatus: venue.AttendeeSyncStatus,
                LatestRecapStatus: venue.LatestRecapStatus,
                ProviderRoomUrl: venue.ProviderRoomUrl,
                InvitePageUrl: venue.InvitePageUrl,
                FallbackMessage: venue.FallbackMessage,
                CanManage: venue.CanManage,
                ProviderCreateAvailable: venue.ProviderCreateAvailable,
                ProviderCreateDisabledReason: venue.ProviderCreateDisabledReason,
                TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
                SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
            return View("~/Views/PublicLanding/GmSessionVenue.cshtml", model);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
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
        IReadOnlyList<string>? summaryPoints = null,
        PublicHorizonCapabilityViewModel? horizonCapability = null)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var chrome = await BuildPublicOrAuthenticatedChromeAsync(title, description, currentPath, cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), chrome.Authenticated);

        return new TrustPageViewModel(
            PageId: pageId,
            Chrome: chrome,
            Eyebrow: PublicFacingCopyHumanizer.Clean(eyebrow),
            Heading: PublicFacingCopyHumanizer.Clean(heading),
            Intro: PublicFacingCopyHumanizer.Clean(intro),
            Sections: sections
                .Select(static section => new TrustPageSectionViewModel(
                    section.Id,
                    PublicFacingCopyHumanizer.Clean(section.Eyebrow),
                    PublicFacingCopyHumanizer.Clean(section.Heading),
                    PublicFacingCopyHumanizer.Clean(section.Body),
                    PublicFacingCopyHumanizer.CleanLines(section.Bullets)))
                .ToArray(),
            Actions: actions
                .Select(static action => new TrustPageActionViewModel(
                    PublicFacingCopyHumanizer.Clean(action.Label),
                    action.Href,
                    action.Tone))
                .ToArray(),
            SummaryPoints: PublicFacingCopyHumanizer.CleanLines(summaryPoints),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken),
            HorizonCapability: horizonCapability);
    }

    private async Task<TrustPageViewModel> BuildDocumentPortalHomePageModel(CancellationToken cancellationToken)
    {
        var documents = _flipLinkDocumentPortal.ListPublicDocuments();
        var firstDocument = documents.First();
        return await BuildHorizonPreviewPageModel(
            pageId: "document-portal",
            title: "Document Portal",
            description: "Chummer-owned guides, primers, and player-safe packets with a clear fallback path.",
            currentPath: "/docs",
            eyebrow: "Document library",
            heading: "Document Portal",
            intro: "Start with a Chummer-owned guide or story packet. Read it on Chummer, open the optional viewer boundary, or download the PDF.",
            sections:
            [
                new TrustPageSectionViewModel(
                    "document_portal_featured",
                    "Available now",
                    "Open a guide or story packet",
                    "The portal stays intentionally narrow: original Chummer-authored documents only, on named first-party routes, with a clear fallback before broader campaign packet rollout.",
                    documents.Select(static item => item.Title).ToArray()),
                new TrustPageSectionViewModel(
                    "document_portal_boundary",
                    "Boundary",
                    "Viewer, not source",
                    "Chummer owns document content, version, access, and safety. FlipLink can present approved documents later without changing the Chummer page.",
                    [
                        "No sourcebook PDF hosting",
                        "No entitlement or payment status",
                        "No private GM archive by default"
                    ]),
                new TrustPageSectionViewModel(
                    "document_portal_provider_posture",
                    "External viewer",
                    "Chummer page first",
                    "The Chummer page and PDF are available now. The external FlipLink viewer can be linked later without changing the user path.",
                    [
                        "Chummer page and PDF fallback are current",
                        "External viewer remains optional"
                    ])
            ],
            actions:
            [
                new TrustPageActionViewModel("Open Quickstart Guide", $"/docs/{firstDocument.Slug}", "primary"),
                new TrustPageActionViewModel("Open Origin Dossier booklet", "/docs/origin-dossier-the-name-she-chose", "secondary"),
                new TrustPageActionViewModel("Read publication boundary", $"/docs/embed/{firstDocument.Slug}", "ghost"),
                new TrustPageActionViewModel("Download PDF", $"/docs/{firstDocument.Slug}/download.pdf", "ghost")
            ],
            cancellationToken: cancellationToken,
            summaryPoints:
            [
                "Original Chummer guides only",
                "Clear document classification",
                "FlipLink optional as viewer layer"
            ]);
    }

    private async Task<TrustPageViewModel> BuildDocumentPortalQuickstartCategoryPageModel(ChummerDocument document, CancellationToken cancellationToken)
        => await BuildHorizonPreviewPageModel(
            pageId: "document-portal-quickstart-category",
            title: $"{document.Category} documents",
            description: "Chummer-owned documents on named public routes with PDF fallback.",
            currentPath: $"/docs/category/{document.Category}",
            eyebrow: "Document category",
            heading: $"{document.Category} documents",
            intro: "Each category in the Document Portal stays first-party, original, and safe to open without leaking private campaign state or copied rulebook prose.",
            sections:
            [
                new TrustPageSectionViewModel(
                    "category_documents_current",
                    "Current document",
                    "The first document on this rail",
                    "This category page keeps one named route per document so readers can open the packet directly instead of hunting through a separate shelf first.",
                    [
                        document.Title,
                        "First-party document route",
                        "Reader view available"
                    ])
            ],
            actions:
            [
                new TrustPageActionViewModel($"Open {document.Title}", $"/docs/{document.Slug}", "primary"),
                new TrustPageActionViewModel("Back to Document Portal", "/docs", "secondary"),
                new TrustPageActionViewModel("Download PDF", $"/docs/{document.Slug}/download.pdf", "ghost")
            ],
            cancellationToken: cancellationToken);

    private async Task<TrustPageViewModel> BuildDocumentPortalQuickstartPageModel(ChummerDocument document, CancellationToken cancellationToken)
        => await BuildHorizonPreviewPageModel(
            pageId: "document-portal-quickstart-guide",
            title: document.Title,
            description: "Original Chummer document with a simple viewer fallback.",
            currentPath: $"/docs/{document.Slug}",
            eyebrow: "Chummer-owned guide",
            heading: document.Title,
            intro: "Open this Chummer document as a first-party page or PDF. The Chummer route stays available even if the external viewer is unavailable.",
            sections:
            [
                new TrustPageSectionViewModel(
                    "document_scope",
                    "Scope",
                    "What this document is for",
                    string.Equals(document.Category, "origin-dossier", StringComparison.OrdinalIgnoreCase)
                        ? "Use this booklet to review the approved story packet before later media, audiobook, or assistant follow-up tries to build on it."
                        : "Use the Quickstart Guide to orient a new player without pushing them into a sourcebook PDF, a sprawling docs pile, or private campaign notes.",
                    string.Equals(document.Category, "origin-dossier", StringComparison.OrdinalIgnoreCase)
                        ? ["Readable story first", "Approved canon boundary", "Later media stays downstream"]
                        : ["Install posture", "First safe actions", "Clear Chummer orientation"]),
                new TrustPageSectionViewModel(
                    "document_boundary",
                    "Boundary",
                    "What this document must not become",
                    "This document must stay original and current in Chummer. It must not host copied rulebook prose, private runner sheets, GM-only lore, or account-only records.",
                    [
                        "No sourcebook prose",
                        "No private campaign data",
                        "No release shortcuts"
                    ]),
                new TrustPageSectionViewModel(
                    "document_publication_posture",
                    "Availability",
                    "How to read it",
                    "The Chummer page and fallback PDF are live now. A reader view can stay optional without changing the basic path.",
                    [
                        "Chummer page is current",
                        "PDF fallback is current",
                        "Reader view remains optional"
                    ])
            ],
            actions:
            [
                new TrustPageActionViewModel("Open Document Portal", "/docs", "primary"),
                new TrustPageActionViewModel("Open reader view", $"/docs/embed/{document.Slug}", "secondary"),
                new TrustPageActionViewModel("Download source", $"/docs/{document.Slug}/source.md", "ghost"),
                new TrustPageActionViewModel("Download PDF", $"/docs/{document.Slug}/download.pdf", "ghost")
            ],
            cancellationToken: cancellationToken,
            summaryPoints:
            [
                "Original Chummer-authored document",
                "First-party route published",
                "External viewer optional",
                "Fallback PDF is current"
            ],
            horizonCapability: string.Equals(document.Category, "origin-dossier", StringComparison.OrdinalIgnoreCase)
                ? BuildPublicHorizonCapability(
                    "origin-dossier",
                    "dossier_media",
                    $"origin-dossier:document:{document.Slug}")
                : null);

    private async Task<TrustPageViewModel> BuildDocumentPortalEmbedBoundaryPageModel(ChummerDocument document, CancellationToken cancellationToken)
        => await BuildHorizonPreviewPageModel(
            pageId: "document-portal-embed-boundary",
            title: "Quickstart reader view",
            description: "Viewer fallback for the Chummer6 Quickstart Guide.",
            currentPath: $"/docs/embed/{document.Slug}",
            eyebrow: "Reader view",
            heading: "Quickstart reader view",
            intro: "Open the quickstart in the embedded reader. The Chummer page and PDF fallback stay available even when the reader is unavailable.",
            sections:
            [
                new TrustPageSectionViewModel(
                    "embed_boundary_contract",
                    "Contract",
                    "What the reader may do",
                    "The reader may present the guide, but the Chummer page and PDF remain the reliable fallback.",
                    [
                        "Presentation only",
                        "Analytics are engagement-only",
                        "Chummer page remains primary"
                    ]),
                new TrustPageSectionViewModel(
                    "embed_boundary_current_state",
                    "Fallback",
                    "Why the fallback stays visible",
                    "The reader remains optional. Chummer keeps the page and PDF available even when the embedded view is unavailable.",
                    [
                        "Chummer route remains current",
                        "Fallback PDF remains current",
                        "Reader view remains optional"
                    ])
            ],
            actions:
            [
                new TrustPageActionViewModel("Back to Quickstart Guide", $"/docs/{document.Slug}", "primary"),
                new TrustPageActionViewModel("Back to Document Portal", "/docs", "secondary"),
                new TrustPageActionViewModel("Download PDF", $"/docs/{document.Slug}/download.pdf", "ghost")
            ],
            cancellationToken: cancellationToken);

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
            "Chummer-owned intake for house-rule, campaign, and table-friction requests.",
            "/participate/karma-forge",
            cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), chrome.Authenticated);
        KarmaForgeTrackDefinition selectedTrack = _karmaForge.ResolveTrack(request.TrackKey);

        return new KarmaForgeIntakePageViewModel(
            Chrome: chrome,
            Eyebrow: "Request intake",
            Heading: "KARMA FORGE",
            Intro: "Turn one table pain into a clear Chummer request before it drifts into generic feedback, unsupported roadmap claims, or implementation guesswork.",
            CanonicalLane: _karmaForge.CanonicalLane,
            EntryLane: _karmaForge.EntryLane,
            DiscoveryCapability: BuildPublicHorizonCapability(
                "karma-forge",
                "discovery_packet",
                "karma-forge:public-intake"),
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
            ReleaseTruth: BuildReleaseTruthDisplay(manifest),
            SignalLoop: signalLoop,
            SignalProjection: signalProjection,
            CampaignOsProof: _campaignOsProof.LoadProof(),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
    }

    private static ReleaseTruthDisplayViewModel BuildReleaseTruthDisplay(PublicReleaseManifestDto manifest)
        => new(
            PublishedDateLabel: manifest.PublishedAt.ToUniversalTime().ToString("yyyy-MM-dd"),
            VerifiedDateLabel: BuildLiveVerificationLabel(manifest));

    private static string BuildLiveVerificationLabel(PublicReleaseManifestDto manifest)
    {
        DateTimeOffset effective = manifest.PublishedAt;
        if (manifest.GeneratedAt is DateTimeOffset generatedAt && generatedAt > effective)
        {
            effective = generatedAt;
        }

        if (manifest.ProofGeneratedAt is DateTimeOffset proofGeneratedAt && proofGeneratedAt > effective)
        {
            effective = proofGeneratedAt;
        }

        foreach (string receiptPath in new[]
                 {
                     "/proofs/FINAL_GOLD_JANITOR.generated.json",
                     "/proofs/HUB_LOCAL_RELEASE_PROOF.generated.json",
                     Path.Combine(AppContext.BaseDirectory, ".codex-studio", "published", "LIVE_PUBLIC_WEB_RECRAWL.generated.json")
                 })
        {
            if (!System.IO.File.Exists(receiptPath))
            {
                continue;
            }

            try
            {
                using JsonDocument document = JsonDocument.Parse(System.IO.File.ReadAllText(receiptPath));
                foreach (string propertyName in new[] { "generated_at_utc", "generatedAtUtc", "generatedAt" })
                {
                    if (document.RootElement.TryGetProperty(propertyName, out JsonElement generatedAtElement)
                        && generatedAtElement.ValueKind == JsonValueKind.String
                        && DateTimeOffset.TryParse(generatedAtElement.GetString(), out DateTimeOffset parsedGeneratedAt))
                    {
                        if (parsedGeneratedAt > effective)
                        {
                            effective = parsedGeneratedAt;
                        }

                        break;
                    }
                }
            }
            catch
            {
                continue;
            }
        }

        return effective.ToUniversalTime().ToString("yyyy-MM-dd");
    }

    private async Task<KarmaForgeSubmittedPageViewModel> BuildKarmaForgeSubmittedPageModel(
        KarmaForgeSubmissionProjection submission,
        CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var chrome = await BuildPublicOrAuthenticatedChromeAsync(
            "KARMA FORGE request saved",
            "The saved request, review path, and next questions for one KARMA FORGE submission.",
            $"/participate/karma-forge/submitted/{submission.SubmissionId}",
            cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), chrome.Authenticated);
        JsonSerializerOptions jsonOptions = new() { WriteIndented = true };

        List<TrustPageActionViewModel> actions =
        [
            new("Open KARMA FORGE", "/participate/karma-forge", "primary"),
            new("Read the maintenance note", "/roadmap/karma-forge", "secondary"),
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
            Eyebrow: "KARMA FORGE request saved",
            Heading: "KARMA FORGE submission captured",
            Intro: "The request is saved. Chummer can now show the likely review route and the next questions.",
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
            DiscoveryCapability: BuildPublicHorizonCapability(
                "karma-forge",
                "discovery_packet",
                $"karma-forge:{submission.SubmissionId}"),
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

    private PublicHorizonCapabilityViewModel BuildPublicHorizonCapability(
        string horizonId,
        string artifactKindOrCapabilityId,
        string sourceRef,
        string visibility = "public_safe")
        => _horizonCapabilities.BuildPublicCapabilityViewModel(horizonId, artifactKindOrCapabilityId, sourceRef, visibility);

    private JsonObject BuildSharedArtifactSurfaceRoutesNode(string horizonId, string artifactKindOrCapabilityId)
        => _horizonCapabilities.BuildSharedArtifactSurfaceRoutesJsonNode(horizonId, artifactKindOrCapabilityId);

    private SharedArtifactSurfaceRoutesViewModel BuildSharedArtifactSurfaceRoutes(string horizonId, string artifactKindOrCapabilityId)
        => _horizonCapabilities.BuildSharedArtifactSurfaceRoutesViewModel(horizonId, artifactKindOrCapabilityId);

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
            : $"Context opened with {string.Join(" · ", segments)}.";
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
            errors.Add("Consent must be accepted before Chummer can save the request.");
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
            Heading: "Private help",
            Intro: authenticated
                ? "Send one clear problem here, or open account support when you want the full saved history."
                : "Send one clear problem here. Use Discord for everything that does not need private details.",
            Authenticated: authenticated,
            AccountSupportHref: authenticated ? "/account/support" : "#private-support-form",
            AccountSupportLabel: authenticated ? "Open account support" : "Open private form",
            InstallAccessHref: installRail.ReturnHref ?? "/downloads",
            InstallAccessLabel: installRail.ReturnLabel ?? "Open downloads",
            ResponseExpectation: BuildSupportResponseExpectation(authenticated, manifest.SupportabilityState, manifest.SupportabilitySummary),
            SubmissionNotice: submissionNotice,
            AttachmentHelp: "Add screenshots, logs, or a small diagnostic bundle when they make the bug or install problem easier to route.",
            Options:
            [
                new SupportIntakeOptionViewModel(SupportCaseKinds.InstallHelp, "Install or update", "Choose this when the installer, updater, or download link is the problem."),
                new SupportIntakeOptionViewModel(SupportCaseKinds.BugReport, "Bug report", "Use this for broken behavior, bad routing, regressions, or cases that need private logs."),
                new SupportIntakeOptionViewModel(SupportCaseKinds.Feedback, "Feature request or UX feedback", "Public feedback should start on the feedback page. Choose this form only when the issue needs private or account-linked follow-up.")
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
            return $"{baseline} Public parity claims stay paused until the desktop experience is ready again.";
        }

        return $"{baseline} {routeGuardSummary}";
    }

    private async Task<SupportIntakeDefaults> ResolveSupportIntakeDefaultsAsync(CancellationToken cancellationToken)
    {
        var currentPath = Request.Path.HasValue ? Request.Path.Value! : "/contact";
        var subject = await TryGetOptionalPublicSurfaceSubjectAsync(currentPath, cancellationToken);
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

        return HumanizeToken(channel, "Current release");
    }

    private static IReadOnlyList<PublicTrustPulseRowViewModel> BuildPublicLaunchHealthRows(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience,
        PublicTrustPulseSnapshot? pulse)
    {
        var rows = new List<PublicTrustPulseRowViewModel>
        {
            new("Live", BuildLiveLaunchSummary(manifest)),
            new("Preview", BuildPreviewLaunchSummary(manifest, releaseExperience, pulse)),
            new("Fallback", BuildFallbackLaunchSummary(manifest)),
            new("Revoked", BuildRevokedLaunchSummary(manifest)),
            new("Fixed", BuildFixedLaunchSummary(manifest)),
            new("Blocked", BuildBlockedLaunchSummary(manifest, pulse)),
            new("Release checks", BuildProofFreshnessSummary(manifest, pulse)),
            new("Support pulse", BuildSupportPulseSummary(manifest, pulse)),
            new("Adoption health", pulse is null
                ? BuildManifestAdoptionSummary(manifest)
                : BuildTrustPulseAdoptionSummary(pulse))
        };

        return rows
            .Select(SanitizePublicLaunchHealthRow)
            .ToArray();
    }

    private static PublicTrustPulseRowViewModel SanitizePublicLaunchHealthRow(PublicTrustPulseRowViewModel row)
    {
        return new PublicTrustPulseRowViewModel(
            NormalizePublicLaunchHealthText(row.Label),
            NormalizePublicLaunchHealthText(row.Value));
    }

    private static string NormalizePublicLaunchHealthText(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return string.Empty;
        }

        return value
            .Replace("proof\u00a0freshness", "Release checks", StringComparison.OrdinalIgnoreCase)
            .Replace("proof freshness", "Release checks", StringComparison.OrdinalIgnoreCase)
            .Replace("Proof freshness", "Release checks")
            .Replace("proof-freshness", "Release checks", StringComparison.OrdinalIgnoreCase)
            .Replace("Proof-freshness", "Release checks")
            .Replace("proof\u00a0recency", "Release checks", StringComparison.OrdinalIgnoreCase)
            .Replace("proof recency", "Release checks", StringComparison.OrdinalIgnoreCase)
            .Replace("Proof recency", "Release checks")
            .Replace("local edge proof", "current release status", StringComparison.OrdinalIgnoreCase)
            .Replace("governor truth", "release status", StringComparison.OrdinalIgnoreCase)
            .Replace("journey proofs", "tested journeys", StringComparison.OrdinalIgnoreCase)
            .Replace("trust routes", "checked pages", StringComparison.OrdinalIgnoreCase)
            .Replace("startup-smoke proof", "startup status", StringComparison.OrdinalIgnoreCase)
            .Replace("startup-smoke", "startup status", StringComparison.OrdinalIgnoreCase)
            .Replace("executable-gate proof", "executable status", StringComparison.OrdinalIgnoreCase)
            .Replace("executable-gate", "executable status", StringComparison.OrdinalIgnoreCase)
            .Replace("promoted flagship bytes", "promoted release packages", StringComparison.OrdinalIgnoreCase)
            .Replace("Open demo", "Open launcher")
            .Replace("Load Demo Runner", "Run example")
            .Replace("Proof freshness", "Release checks");
    }

    private static GoldReadinessStatusViewModel? BuildGoldReadinessStatus(GoldReadinessSnapshot? snapshot)
    {
        if (snapshot is null || snapshot.RuleAuthorityBlockers.Count == 0)
        {
            return null;
        }

        List<GoldReadinessBlockerViewModel> blockers = [];
        foreach (GoldReadinessRuleAuthorityBlocker blocker in snapshot.RuleAuthorityBlockers)
        {
            string rulesetLabel = blocker.RulesetId.ToUpperInvariant();
            string summary = $"{rulesetLabel} has {blocker.RulefactCount?.ToString() ?? "unknown"} published rules entries, but release-ready support still waits on rules coverage, current errata updates, and final human review.";
            string nextStep = BuildGoldBlockerNextStep(blocker);
            blockers.Add(new GoldReadinessBlockerViewModel(
                RulesetLabel: rulesetLabel,
                Summary: summary,
                NextStepLabel: nextStep,
                ReviewStatusLabel: BuildGoldBlockerReviewStatus(blocker),
                MatrixStatusLabel: BuildGoldBlockerMatrixStatus(blocker),
                RemainingChecks: blocker.RemainingGates.Select(HumanizeGoldRemainingCheck).ToArray()));
        }

        string statusLabel = string.Equals(snapshot.Verdict, "GOLD_READY", StringComparison.OrdinalIgnoreCase)
            ? "Gold support is ready."
            : "Gold support is still blocked.";
        string summaryText = blockers.Count == 1
            ? "One remaining ruleset still needs coverage closure before this release can be treated as fully release-ready."
            : $"{blockers.Count} remaining rulesets still need coverage closure before this release can be treated as fully release-ready.";
        string? generatedAtLabel = snapshot.GeneratedAtUtc?.UtcDateTime.ToString("yyyy-MM-dd HH:mm 'UTC'");
        return new GoldReadinessStatusViewModel(statusLabel, summaryText, generatedAtLabel, blockers);
    }

    private static string BuildGoldBlockerNextStep(GoldReadinessRuleAuthorityBlocker blocker)
    {
        List<string> steps = [];
        if (string.Equals(blocker.RowLevelMappingStatus, "pending_human_review", StringComparison.OrdinalIgnoreCase))
        {
            steps.Add("complete the rules coverage");
        }

        if (string.Equals(blocker.ErrataPostureStatus, "pending_reviewed_application", StringComparison.OrdinalIgnoreCase))
        {
            steps.Add("apply the current errata updates");
        }

        if (blocker.SourceBaselineRequired == true)
        {
            steps.Add("choose the SR6 source baseline");
        }

        steps.Add("publish the final human review");
        return $"{blocker.RulesetId.ToUpperInvariant()} still needs these steps: {string.Join("; ", steps)}.";
    }

    private static string BuildGoldBlockerReviewStatus(GoldReadinessRuleAuthorityBlocker blocker)
    {
        if (blocker.HumanReviewReady == true)
        {
            return "Human review is approved.";
        }

        if (blocker.HumanReviewPending == true)
        {
            return blocker.SourceBaselineRequired == true
                ? "Human review is pending, including the SR6 source-baseline choice."
                : "Human review is pending.";
        }

        return "Human review status is not recorded yet.";
    }

    private static string BuildGoldBlockerMatrixStatus(GoldReadinessRuleAuthorityBlocker blocker)
    {
        if (blocker.VerificationMatrixUnexpectedFailedGates.Count > 0)
        {
            return $"{blocker.VerificationMatrixUnexpectedFailedGates.Count} unexpected status gate(s) need team review.";
        }

        if (string.Equals(blocker.VerificationMatrixStatus, "blocked", StringComparison.OrdinalIgnoreCase))
        {
            return blocker.VerificationMatrixFailedGates.Count > 0
                ? "Status matrix is blocked only on expected review gates."
                : "Status matrix is blocked on review gates.";
        }

        if (!string.IsNullOrWhiteSpace(blocker.VerificationMatrixStatus))
        {
            return $"Status matrix: {HumanizeToken(blocker.VerificationMatrixStatus, "Unknown")}.";
        }

        return "Status matrix is not recorded yet.";
    }

    private static string HumanizeGoldRemainingCheck(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return "Current review step";
        }

        return value.Trim()
            .Replace("human-reviewed row-level mapping from indexed table evidence into normalized records", "Rules coverage from indexed source tables into normalized records", StringComparison.OrdinalIgnoreCase)
            .Replace("human-reviewed mapping of private PDF line-hash candidates into normalized public-safe records", "Rules coverage from indexed source candidates into normalized records", StringComparison.OrdinalIgnoreCase)
            .Replace("errata profile applied and reviewed", "Current errata updates applied and reviewed", StringComparison.OrdinalIgnoreCase)
            .Replace("complete authority golden fixture corpus, beyond seed fixtures", "Complete golden fixture coverage beyond the current seed fixtures", StringComparison.OrdinalIgnoreCase)
            .Replace("full provider-backed explain receipt corpus", "Complete explain coverage from the current explanation records", StringComparison.OrdinalIgnoreCase)
            .Replace("human rule review signoff", "Final human review signoff", StringComparison.OrdinalIgnoreCase);
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
            return $"{proof} · {HumanizeToken(manifest.SupportabilityState, "Current release")}";
        }

        return proof;
    }

    private static string BuildManifestAdoptionSummary(PublicReleaseManifestDto manifest)
    {
        if (manifest.PublicTrustMetrics is JsonElement metrics
            && metrics.ValueKind == JsonValueKind.Object
            && metrics.TryGetProperty("adoptionHealth", out JsonElement adoptionHealth)
            && adoptionHealth.ValueKind == JsonValueKind.Object)
        {
            string? summary = TryGetJsonString(adoptionHealth, "summary");
            if (!string.IsNullOrWhiteSpace(summary))
            {
                return summary!;
            }

            string? status = TryGetJsonString(adoptionHealth, "status");
            if (!string.IsNullOrWhiteSpace(status))
            {
                return $"Adoption health is {HumanizeToken(status, "unknown").ToLowerInvariant()}.";
            }
        }

        return BuildReleaseProofSummary(manifest);
    }

    private static bool ShouldUseManifestAdoptionSummary(PublicTrustPulseSnapshot? pulse)
    {
        if (pulse is null)
        {
            return true;
        }

        bool proofUnknown = string.IsNullOrWhiteSpace(pulse.LocalReleaseProofStatus)
            || string.Equals(pulse.LocalReleaseProofStatus, "unknown", StringComparison.OrdinalIgnoreCase);
        bool noEvidence = (!pulse.ProvenJourneyCount.HasValue || pulse.ProvenJourneyCount.Value <= 0)
            && (!pulse.ProvenRouteCount.HasValue || pulse.ProvenRouteCount.Value <= 0);
        return proofUnknown && noEvidence;
    }

    private static string BuildLiveLaunchSummary(PublicReleaseManifestDto manifest)
    {
        int totalLiveRouteCount = manifest.Downloads.Count;
        int accountRequiredCount = manifest.Downloads.Count(static artifact =>
            string.Equals(artifact.InstallAccessClass, InstallAccessClasses.AccountRequired, StringComparison.OrdinalIgnoreCase));
        int directPublicCount = totalLiveRouteCount - accountRequiredCount;
        string routeSummary = totalLiveRouteCount switch
        {
            <= 0 => "No current install routes are available on downloads right now.",
            1 when accountRequiredCount <= 0 => "1 current install route is available on downloads right now.",
            1 => "1 current install route is available on downloads right now with optional sign-in and support attached.",
            _ when accountRequiredCount <= 0 => $"{totalLiveRouteCount} current install routes are available on downloads right now.",
            _ when directPublicCount <= 0 => $"{totalLiveRouteCount} current install routes are available on downloads right now with optional sign-in and support attached.",
            _ => $"{totalLiveRouteCount} current install routes are available on downloads right now; {directPublicCount} are direct downloads and {accountRequiredCount} can start with sign-in and support attached."
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
            ? routeSummary
            : $"{routeSummary} {primaryReason}";
    }

    private static string BuildPreviewLaunchSummary(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience,
        PublicTrustPulseSnapshot? pulse)
    {
        string updated = $"Updated {BuildLiveVerificationLabel(manifest)}.";
        string supportabilityState = (manifest.SupportabilityState ?? string.Empty).Trim();

        bool checksPassing = string.Equals(manifest.ProofStatus, "passed", StringComparison.OrdinalIgnoreCase)
            || string.Equals(manifest.ProofStatus, "pass", StringComparison.OrdinalIgnoreCase);
        if (string.Equals(supportabilityState, "gold_supported", StringComparison.OrdinalIgnoreCase)
            || checksPassing
            || pulse?.ParityClaimsReviewRequired == false)
        {
            return updated;
        }

        return $"{updated} Open status and support before wider rollouts.";
    }

    private static string BuildPublicStatusReleaseSummary(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience,
        PublicTrustPulseSnapshot? pulse)
        => BuildPreviewLaunchSummary(manifest, releaseExperience, pulse);

    private static string BuildPublicStatusCautionSummary(
        PublicReleaseManifestDto manifest,
        PublicTrustPulseSnapshot? pulse)
    {
        string blockedSummary = BuildBlockedLaunchSummary(manifest, pulse);
        if (!blockedSummary.StartsWith("No blocked", StringComparison.OrdinalIgnoreCase))
        {
            return blockedSummary;
        }

        return "Known issues stay on downloads.";
    }

    private static string BuildFallbackLaunchSummary(PublicReleaseManifestDto manifest)
    {
        var fallbackRoutes = EnumerateDesktopRouteTruth(manifest)
            .Where(static route => string.Equals(TryGetJsonString(route, "routeRole"), "fallback", StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (fallbackRoutes.Length == 0)
        {
            return "No separate fallback download route is published right now.";
        }

        string? reason = FirstNonEmpty(
            TryGetJsonString(fallbackRoutes[0], "rollbackReason"),
            TryGetJsonString(fallbackRoutes[0], "promotionReason"),
            TryGetJsonString(fallbackRoutes[0], "updateEligibilityReason"));
        if (!string.IsNullOrWhiteSpace(reason))
        {
            reason = reason
                .Replace("Fallback route", "Alternate route", StringComparison.OrdinalIgnoreCase)
                .Replace("fallback route", "alternate route", StringComparison.OrdinalIgnoreCase)
                .Replace("Fallback ", "Alternate ", StringComparison.OrdinalIgnoreCase)
                .Replace("fallback ", "alternate ", StringComparison.OrdinalIgnoreCase);
        }
        return string.IsNullOrWhiteSpace(reason)
            ? $"{fallbackRoutes.Length} alternate download route(s) are published right now."
            : $"{fallbackRoutes.Length} alternate download route(s) are published right now. {reason}";
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
                ? "No desktop download revoke state is published right now."
                : $"No revoked markers are active across {routeRows.Count} tracked desktop download routes.";
        }

        string? reason = FirstNonEmpty(
            TryGetJsonString(revokedRoutes[0], "revokeReason"),
            TryGetJsonString(revokedRoutes[0], "installPostureReason"));
        return string.IsNullOrWhiteSpace(reason)
            ? $"{revokedRoutes.Length} desktop download route(s) are currently unavailable."
            : $"{revokedRoutes.Length} desktop download route(s) are currently unavailable. {reason}";
    }

    private static string BuildFixedLaunchSummary(PublicReleaseManifestDto manifest)
        => !string.IsNullOrWhiteSpace(manifest.FixAvailabilitySummary)
            ? manifest.FixAvailabilitySummary!
            : !string.IsNullOrWhiteSpace(manifest.SupportabilitySummary)
                ? manifest.SupportabilitySummary!
                : "No fix note is published for downloads right now.";

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
            return "No blocked public install path or tested path is active right now.";
        }

        var segments = new List<string>(2);
        if (blockedRouteCount > 0)
        {
            segments.Add($"{blockedRouteCount} desktop routes are blocked or still waiting for current status");
        }

        if (blockedJourneyCount > 0)
        {
            segments.Add($"{blockedJourneyCount} verified paths remain blocked");
        }

        return string.Join("; ", segments) + ".";
    }

    private static string BuildProofFreshnessSummary(
        PublicReleaseManifestDto manifest,
        PublicTrustPulseSnapshot? pulse)
    {
        string manifestStamp = manifest.GeneratedAt is DateTimeOffset generatedAt
            ? $"Release details refreshed {generatedAt.ToUniversalTime():yyyy-MM-dd HH:mm} UTC"
            : $"Release details published {manifest.PublishedAt.ToUniversalTime():yyyy-MM-dd HH:mm} UTC";
        string proofStamp = manifest.ProofGeneratedAt is DateTimeOffset proofGeneratedAt
            ? $"release status updated {proofGeneratedAt.ToUniversalTime():yyyy-MM-dd HH:mm} UTC ({HumanizeToken(manifest.ProofStatus, "unknown").ToLowerInvariant()})"
            : $"release status is {HumanizeToken(manifest.ProofStatus, "not mirrored").ToLowerInvariant()}";
        string pulseStamp = string.IsNullOrWhiteSpace(pulse?.AsOf)
            ? "weekly adoption pulse is not mirrored"
            : $"weekly adoption pulse as of {pulse.AsOf}";
        return $"{manifestStamp}; {proofStamp}; {pulseStamp}.";
    }

    private static string BuildSupportPulseSummary(
        PublicReleaseManifestDto manifest,
        PublicTrustPulseSnapshot? pulse)
    {
        if (pulse is not null)
        {
            if (pulse.ClosureHealthWaitingCount is int waitingCount
                && pulse.ClosureHealthPendingHumanResponseCount is int pendingCount
                && pulse.ClosureHealthOpenCaseCount is int openCaseCount)
            {
                if (waitingCount == 0 && pendingCount == 0 && openCaseCount == 0)
                {
                    return "No open support next step is waiting right now.";
                }

                return $"{waitingCount} support next step(s) are waiting / {pendingCount} are waiting on a human reply. {openCaseCount} open support case(s) remain.";
            }

            return BuildTrustPulseClosureHealthSummary(pulse);
        }

        return !string.IsNullOrWhiteSpace(manifest.SupportabilitySummary)
            ? manifest.SupportabilitySummary!
            : "Support history is not mirrored yet.";
    }

    private static string BuildLedgerMapEntryHref(int? turn, string? mode)
    {
        var queryParts = new List<string>(2);
        if (turn is int requestedTurn)
        {
            queryParts.Add($"turn={requestedTurn}");
        }

        if (!string.IsNullOrWhiteSpace(mode))
        {
            queryParts.Add($"mode={Uri.EscapeDataString(mode.Trim())}");
        }

        return queryParts.Count == 0
            ? "/ledger/map"
            : $"/ledger/map?{string.Join("&", queryParts)}";
    }

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
                ? "Link the current public release first so Chummer can compare this account against the published shelf."
                : $"Link the current public release first so Chummer can compare this account against {BuildPublishedArtifactSummary(manifest, releaseExperience, releaseExperience.Recommended.Artifact)}.";
        }

        string installationLabel = ResolveInstallationDisplayLabel(installation);
        if (!string.IsNullOrWhiteSpace(followThrough?.FixedReleaseLabel))
        {
            if (followThrough.NeedsInstallUpdate)
            {
                PublicReleaseArtifactDto? publishedArtifact = FindPublishedArtifactForInstallation(manifest, installation);
                return publishedArtifact is null
                    ? $"Support is tracking {followThrough.FixedReleaseLabel} for {installationLabel}. Keep this linked copy on the support path until the promoted download catches up."
                    : $"Support is tracking {followThrough.FixedReleaseLabel} for {installationLabel}. The current downloads page still shows {BuildPublishedArtifactSummary(manifest, releaseExperience, publishedArtifact)}.";
            }

            if (followThrough.CanVerifyFix)
            {
                return $"{installationLabel} is already on {followThrough.FixedReleaseLabel}, so this linked copy is the right one to verify now.";
            }
        }

        PublicReleaseArtifactDto? artifact = FindPublishedArtifactForInstallation(manifest, installation);
        if (artifact is null)
        {
            return $"No promoted download match is published right now for {installationLabel}. Keep this copy linked and use a support path before moving it.";
        }

        string publishedSummary = BuildPublishedArtifactSummary(manifest, releaseExperience, artifact);
        if (InstallationMatchesPublishedShelf(manifest, installation, artifact))
        {
            return $"{installationLabel} already matches the promoted {publishedSummary}.";
        }

        return $"{installationLabel} reports {installation.Version} on {ResolveChannelLabel(installation.Channel, manifest, releaseExperience)}. The promoted download for this install is {publishedSummary}.";
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
            return $"{ResolveInstallationDisplayLabel(installation)} is linked on {BuildInstallationFootprintSummary(installation)}, and that path is not on the current downloads page right now.";
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
            ? "No linked install is attached yet, so Chummer cannot compare this account against the current downloads page or the current fix target."
            : "No extra install-specific warning is published right now.";
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
                    ? $"{fixedReleaseLabel} is the tracked fix target, but this linked install still needs a support-path update before it can verify."
                    : $"{fixedReleaseLabel} is the tracked fix target. The promoted download for this install is {BuildPublishedArtifactSummary(manifest, releaseExperience, artifact)}.";
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
            ? "No linked install is attached yet, so Chummer cannot tie this account to a fix-ready download."
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
            return "No extra caution is published for this linked install right now; use support to confirm the fix on this device.";
        }

        if (installation is not null && FindPublishedArtifactForInstallation(manifest, installation) is null)
        {
            return $"{ResolveInstallationDisplayLabel(installation)} is outside the current downloads page right now, so keep it on the support path until a matching build lands.";
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
                ? "The linked install route remains the safest option while the desktop experience is still being polished."
                : "The current downloads page is still installable, but parity-sensitive installs should stay with support until the desktop experience is ready.";
        }

        string accessSummary = releaseExperience.Recommended.RequiresAccount && !releaseExperience.GuestDownloadAvailable
            ? "The linked install route is the recommended path so the install can stay attached."
            : "The public download is live on the current downloads page, and signing in keeps the install linked once you want account-aware history.";
        return $"{releaseExperience.Recommended.Title} on {releaseExperience.Display.ChannelLabel}. {accessSummary}";
    }

    private static string BuildTrustPulseAccessSummary(
        PublicReleaseManifestDto manifest,
        ReleaseExperienceViewModel releaseExperience,
        PublicTrustPulseSnapshot pulse)
    {
        if (releaseExperience.Recommended is null)
        {
            return "No release download is published yet.";
        }

        if (pulse.MissingDesktopClientCoverage || string.Equals(manifest.SupportabilityState, "review_required", StringComparison.OrdinalIgnoreCase))
        {
            return releaseExperience.Recommended.RequiresAccount && !releaseExperience.GuestDownloadAvailable
                ? "The linked install route stays preferred while the desktop experience is still being polished."
                : "Public downloads are visible, but parity-sensitive next steps stay with support until the desktop experience is ready.";
        }

        if (releaseExperience.Recommended.RequiresAccount && !releaseExperience.GuestDownloadAvailable)
        {
            return "The linked install route is the live path now, so the install stays attached and support can follow the exact device.";
        }

        if (releaseExperience.GuestDownloadAvailable)
        {
            return "The public download is visible now, and signing in adds linked-install history once you want the install attached to your account.";
        }

        return "Linked-install history is available now when you sign in.";
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
            segments.Add($"Desktop polish still needs closure: {pulse.FlagshipReadinessReason!.Trim().TrimEnd('.')}.");
        }

        if (!string.IsNullOrWhiteSpace(pulse.LongestPoleLabel))
        {
            segments.Add($"Current focus: {pulse.LongestPoleLabel}.");
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
            return "Wave is still active. Continue from guided-wave review and guard against scope regressions before expanding.";
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
            ? "default route behavior follows the Hub configuration and is not hard-coded here"
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
            string proofStatus = pulse.LocalReleaseProofStatus.Trim();
            segments.Add(string.Equals(proofStatus, "passed", StringComparison.OrdinalIgnoreCase)
                ? "Current release is ready."
                : string.Equals(proofStatus, "review_required", StringComparison.OrdinalIgnoreCase)
                    ? "Current release status is posted."
                    : $"Current release status is {HumanizeToken(proofStatus, "unknown").ToLowerInvariant()}.");
        }

        if (pulse.ProvenJourneyCount is int journeyCount && journeyCount > 0 && pulse.ProvenRouteCount is int routeCount && routeCount > 0)
        {
            segments.Add($"{journeyCount} tested paths and {routeCount} checked pages are on record.");
        }
        else if (pulse.ProvenJourneyCount is int journeyOnly && journeyOnly > 0)
        {
            segments.Add($"{journeyOnly} tested paths are on record.");
        }
        else if (pulse.ProvenRouteCount is int routeOnly && routeOnly > 0)
        {
            segments.Add($"{routeOnly} checked pages are on record.");
        }

        if (pulse.HistorySnapshotCount is int historySnapshotCount && historySnapshotCount > 0)
        {
            segments.Add(historySnapshotCount < 6
                ? $"{historySnapshotCount} weekly snapshots are measured so far, so usage history is still early."
                : $"{historySnapshotCount} weekly snapshots are on record for the current public release picture.");
        }

        if (pulse.MissingDesktopClientCoverage && !string.IsNullOrWhiteSpace(pulse.FlagshipReadinessReason))
        {
            segments.Add($"Flagship desktop readiness still needs closure: {pulse.FlagshipReadinessReason!.Trim().TrimEnd('.')}.");
        }

        return segments.Count == 0
            ? "Measured usage history is still accumulating."
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
                ? $" {openCaseCount} open support case(s) remain."
                : string.Empty;
            return $"{waitingCount} support follow-up item(s) are waiting / {pendingCount} are waiting on a human reply.{openCaseSegment}".Trim();
        }

        return "Support next steps are waiting on current support evidence.";
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
                $"Public comparison stays limited because {routeLookup.CurrentnessFailureReason!.Trim().TrimEnd('.')}.");
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
                $"Current direct route record is attached, but public comparison stays limited because {reviewRequiredReason}.");
        }

        ImportRouteParityProofGuardSnapshot importRouteGuard = _importRouteParityProofGuard.Evaluate();
        if (!importRouteGuard.IsCurrent && !string.IsNullOrWhiteSpace(importRouteGuard.ReviewRequiredReason))
        {
            return new RouteClaimStatus(
                "bounded_failure",
                $"Current direct route record is attached, but public comparison stays limited because {importRouteGuard.ReviewRequiredReason!.Trim().TrimEnd('.')}.");
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
            "featured_artifacts" => "What this artifact opens next",
            "coming_next" => "Where this maintenance item sits now",
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
                => "live-release",
            "featured_artifacts" => "preview-detail",
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
            "coming_next" => "Compare this maintenance item with the current release first, then open the longer note only when you need the rationale.",
            "featured_artifacts" => "Use the current release page to see whether this is live today or still preview-only.",
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
            "featured_artifacts" => "This page keeps the preview tangible with one clear next action instead of a vague gallery card.",
            "coming_next" => "The payoff becomes real when this maintenance item moves onto the current release view, but the user value is already explicit here.",
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
            "coming_next" => new[] { "Planned product work", "Current release contrast", "Longer maintenance note" },
            "featured_artifacts" => new[] { "Current listing", "Preview or live status", "Next useful action" },
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
                        .Select(entry => string.Equals(entry.Question, "Do I need an account to download the current release?", StringComparison.Ordinal)
                            ? entry with
                            {
                                Question = "Do I need an account to download the current release?",
                                Answer = accessPosture.DownloadFaqAnswer
                            }
                            : string.Equals(entry.Question, "Can I actually use Chummer right now?", StringComparison.Ordinal)
                                ? entry with
                                {
                                    Answer = "Yes. Downloads shows the current public installer, platform notes, and any known limits."
                                }
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

    private string BuildDownloadSelectionUserAgent()
    {
        var builder = new StringBuilder(Request.Headers.UserAgent.ToString());
        AppendBrowserClientHint(builder, "Sec-CH-UA-Platform");
        AppendBrowserClientHint(builder, "Sec-CH-UA-Arch");
        AppendBrowserClientHint(builder, "Sec-CH-UA-Bitness");
        AppendBrowserClientHint(builder, "Sec-CH-UA-Model");
        return builder.ToString();
    }

    private void AppendBrowserClientHint(StringBuilder builder, string headerName)
    {
        if (!Request.Headers.TryGetValue(headerName, out var value) || string.IsNullOrWhiteSpace(value.ToString()))
        {
            return;
        }

        if (builder.Length > 0)
        {
            builder.Append(' ');
        }

        builder.Append(headerName).Append('=').Append(value.ToString().Trim());
    }

    private static void ApplyDownloadClientHintHeaders(IHeaderDictionary headers)
    {
        const string clientHints = "Sec-CH-UA-Platform, Sec-CH-UA-Arch, Sec-CH-UA-Bitness, Sec-CH-UA-Model";
        headers["Accept-CH"] = clientHints;
        headers["Vary"] = AppendVaryHeader(headers["Vary"].ToString(), "User-Agent", "Sec-CH-UA-Platform", "Sec-CH-UA-Arch", "Sec-CH-UA-Bitness", "Sec-CH-UA-Model");
    }

    private static string AppendVaryHeader(string current, params string[] values)
    {
        var existing = string.IsNullOrWhiteSpace(current)
            ? new HashSet<string>(StringComparer.OrdinalIgnoreCase)
            : current.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries).ToHashSet(StringComparer.OrdinalIgnoreCase);

        foreach (var value in values)
        {
            if (!string.IsNullOrWhiteSpace(value))
            {
                existing.Add(value.Trim());
            }
        }

        return string.Join(", ", existing);
    }

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
                    && IsGuestAccountOpenAction(action))
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

    private static bool IsGuestAccountOpenAction(SiteChromeActionViewModel action)
    {
        if (!string.Equals(action.Tone, "link", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        return action.Href.StartsWith("/login", StringComparison.OrdinalIgnoreCase)
            || action.Href.StartsWith("/auth/google/start", StringComparison.OrdinalIgnoreCase);
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
            "macos" => "Copy this one Terminal command into Terminal.",
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
            "macos" => "It streams a short-lived setup assistant directly into bash. The assistant asks which Chummer apps to install, where to put them, whether quick access should stay in the Applications folder or add Desktop links, whether to open them when it finishes, and then shows live progress while it downloads, verifies the published DMG digest, installs, and links the selected apps.",
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
                new("Finish linked", "The selected apps are launched once through a short-lived environment handoff, and setup confirms the apps are attached to this account.")
            ],
            "linux" =>
            [
                new("Choose your setup", "Pick Avalonia, Blazor Desktop, or both before any packages are unpacked."),
                new("Choose where it lands", "Install into a user-local applications root or a system root without changing the published Debian packages."),
                new("Choose your quick access", "Keep Chummer in the applications menu only or let setup add Desktop launchers for the apps you picked."),
                new("Finish linked", "The selected apps are launched once through a short-lived environment handoff, and setup confirms the apps are attached to this account.")
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
                .Append(" ]] || { echo 'Setup script check failed; open the signed-in Downloads page and copy a fresh install command.' >&2; exit 1; }; ");
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
        builder.AppendLine("    INSTALL_WARNINGS+=(\"$artifact_title could not find the embedded short-lived install claim for this build. Re-open the current Mac install command from $DOWNLOADS_URL and run it again.\")");
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
                    message = "The install command expired. Open the signed-in Downloads page and copy a fresh install command."
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
                    message = "The install command expired. Open the signed-in Downloads page and copy a fresh install command."
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
                return (null, Redirect($"/login?next={Uri.EscapeDataString($"/downloads/install/{artifactId}")}"));
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
            return (null, Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: $"No {requiredPlatform} setup files are available for this install."));
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
        IReadOnlyList<BlackLedgerDispatchViewModel> dispatches = _blackLedgerDispatches.ListPublishedDispatches(requestedTurn, selectedFactionId);
        if (dispatches.Count == 0)
        {
            // Local seeded app instances can start without the CommunityStore projection populated yet.
            // Fall back to the deterministic public-safe dispatch corpus so public route proof stays stable.
            dispatches = _blackLedgerStats.ListDispatches(requestedTurn, selectedFactionId);
        }

        var selectedDispatch = string.IsNullOrWhiteSpace(selectedDispatchId)
            ? dispatches.FirstOrDefault()
            : dispatches.FirstOrDefault(item => string.Equals(item.DispatchId, selectedDispatchId, StringComparison.OrdinalIgnoreCase))
                ?? _blackLedgerStats.LoadDispatch(selectedDispatchId, requestedTurn, selectedFactionId);
        var commandMap = _blackLedgerStats.LoadCommandMap(requestedTurn, selectedMapMode ?? "influence");
        var mapFocused = string.Equals(currentSection, "map", StringComparison.OrdinalIgnoreCase);
        var selectedFaction = string.IsNullOrWhiteSpace(selectedFactionId) || world is null
            ? null
            : world.Factions.FirstOrDefault(faction =>
                string.Equals(faction.Id, selectedFactionId, StringComparison.OrdinalIgnoreCase)
                || string.Equals(faction.Id.Replace('_', '-'), selectedFactionId, StringComparison.OrdinalIgnoreCase));
        var intro = world?.DeterministicPreview == true
            ? "This deterministic turn-two board shows how interim roles hold together while the city reacts to pressure: cleaner routes, harder heat, and faction moves a GM can use."
            : "A fictional city board with six factions, visible pressure zones, and contained dispatches.";
        if (selectedFaction is not null)
        {
            intro = $"{selectedFaction.PublicName} faction page. This lane shows public pressure, table hooks, and city movement without exposing private table labels.";
        }
        else if (string.Equals(selectedRulesetId, "anarchy", StringComparison.OrdinalIgnoreCase)
            || string.Equals(selectedRulesetId, AnarchyPreviewService.RulesetId, StringComparison.OrdinalIgnoreCase))
        {
            intro = "This Anarchy lens reads the same Black Ledger dispatches through a rules-light play profile. It does not invent a separate city or flatten Anarchy into an SR5/SR6 toggle.";
        }
        else if (string.Equals(currentSection, "newsroom", StringComparison.OrdinalIgnoreCase))
        {
            intro = "Public newsroom view for Emerald Sprawl. Bulletin playback, transcript, and episode details stay distinct from the command map while still pointing back to the same city board.";
        }
        else if (mapFocused)
        {
            intro = "Focused command-map view for Emerald Sprawl. District pressure, event arcs, and replay controls stay visibly distinct from the broader ledger overview.";
        }

        int newsTurn = requestedTurn ?? world?.CurrentTurn ?? 1;
        BlackLedgerNewsStatusViewModel newsreelStatus = _blackLedgerTickNews.BuildStatusViewModel(
            worldId: "emerald-sprawl-prelude",
            turn: newsTurn,
            scopeLabel: "Public Black Ledger lane",
            notificationsHref: "/account/ledger/notifications",
            turnHref: $"/ledger/turns/{newsTurn}",
            dispatchHref: string.IsNullOrWhiteSpace(selectedFactionId) ? $"/ledger/turns/{newsTurn}/dispatches" : $"/ledger/factions/{selectedFactionId}/dispatches");
        BlackLedgerWorldTurnBriefingViewModel? worldTurnBriefing = BuildProtectedBlackLedgerWorldTurnBriefing(newsTurn);
        string worldTitle = world?.PublicName ?? "Emerald Sprawl: First Pressure";
        string sectionEyebrow =
            string.Equals(currentSection, "newsroom", StringComparison.OrdinalIgnoreCase) ? "Black Ledger newsroom"
            : mapFocused ? "Black Ledger command map"
            : string.Equals(currentSection, "dispatches", StringComparison.OrdinalIgnoreCase) ? "Black Ledger dispatch lane"
            : string.Equals(currentSection, "packages", StringComparison.OrdinalIgnoreCase) ? "Black Ledger package rail"
            : string.Equals(currentSection, "closeouts", StringComparison.OrdinalIgnoreCase) ? "Black Ledger closeout board"
            : string.Equals(currentSection, "stats", StringComparison.OrdinalIgnoreCase) ? "Black Ledger world stats"
            : string.Equals(currentSection, "factions", StringComparison.OrdinalIgnoreCase) && selectedFaction is null ? "Black Ledger faction files"
            : selectedFaction is null ? "Black Ledger command deck"
            : "Black Ledger faction file";
        string sectionHeading =
            selectedFaction is not null ? $"{selectedFaction.PublicName} faction file"
            : string.Equals(currentSection, "newsroom", StringComparison.OrdinalIgnoreCase) ? $"Black Ledger newsroom · {worldTurnBriefing?.Broadcast?.PackageLabel ?? $"Turn {newsTurn} anchor package"}"
            : mapFocused ? "Black Ledger command map"
            : string.Equals(currentSection, "dispatches", StringComparison.OrdinalIgnoreCase) ? $"Black Ledger dispatches · {worldTitle}"
            : string.Equals(currentSection, "packages", StringComparison.OrdinalIgnoreCase) ? $"Black Ledger packages · {worldTitle}"
            : string.Equals(currentSection, "closeouts", StringComparison.OrdinalIgnoreCase) ? $"Black Ledger closeouts · {worldTitle}"
            : string.Equals(currentSection, "stats", StringComparison.OrdinalIgnoreCase) ? $"Black Ledger world stats · {worldTitle}"
            : string.Equals(currentSection, "factions", StringComparison.OrdinalIgnoreCase) && selectedFaction is null ? $"Black Ledger factions · {worldTitle}"
            : worldTitle;

        return new BlackLedgerHubPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync(
                selectedFaction?.PublicName ?? "Black Ledger",
                "Fictional campaign pressure, package heat, and closeout movement.",
                currentPath,
                cancellationToken),
            Eyebrow: sectionEyebrow,
            Heading: sectionHeading,
            Intro: intro,
            CurrentSection: currentSection,
            World: world,
            SelectedFaction: selectedFaction,
            Stats: _blackLedgerStats.ListPublicStats(requestedTurn),
            Modules: _blackLedgerStats.ListModules(),
            Closeouts: _blackLedgerStats.ListCloseouts(),
            Dispatches: dispatches,
            SelectedDispatch: selectedDispatch,
            NewsreelStatus: newsreelStatus,
            WorldTurnBriefing: worldTurnBriefing,
            SelectedFactionPromo: selectedFaction is null ? null : _blackLedgerFactions.GetPromoArtifact(selectedFaction.Id),
            CommandMap: commandMap,
            PrimaryAction: string.Equals(currentSection, "newsroom", StringComparison.OrdinalIgnoreCase)
                ? new TrustPageActionViewModel("Back to ledger overview", "/ledger", "secondary")
                : mapFocused
                ? new TrustPageActionViewModel("Back to ledger overview", "/ledger", "secondary")
                : new TrustPageActionViewModel("Open command map", "/ledger/map#ledger-map", "primary"),
            SecondaryAction: new TrustPageActionViewModel("Latest bulletin", $"/ledger/turns/{newsTurn}/digest", "secondary"),
            DigestCapability: BuildPublicHorizonCapability(
                "black-ledger",
                "world_tick_digest",
                $"black-ledger:turn-{newsTurn}:digest"),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
    }

    private async Task<IActionResult> BuildLedgerFactionWorkspacePage(
        string currentPath,
        string factionId,
        string currentSection,
        string? campaignId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            BlackLedgerFactionWorkspacePageViewModel? model = await BuildLedgerFactionWorkspacePageModel(currentPath, factionId, currentSection, campaignId, user, cancellationToken);
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
        string? campaignId,
        HubUserDto user,
        CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated: true);
        var world = _blackLedgerStats.LoadWorldPreview();
        var workspaceFaction = _blackLedgerFactions.GetWorkspaceFactionDetail(factionId);
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
        if (faction is null && workspaceFaction is not null)
        {
            faction = new BlackLedgerFactionViewModel(
                workspaceFaction.FactionId,
                workspaceFaction.PublicName,
                workspaceFaction.Type,
                workspaceFaction.FactionLeader,
                workspaceFaction.FieldGm,
                workspaceFaction.IntelProvider,
                workspaceFaction.PublicSignals,
                workspaceFaction.ColorPrimary,
                workspaceFaction.ColorSecondary,
                workspaceFaction.Icon);
        }
        if (world is null || faction is null)
        {
            return null;
        }

        string normalizedFactionId = faction.Id.Replace('_', '-');
        var coveredDistricts = world.Districts
            .Where(district => string.Equals(district.DominantFaction.Replace(' ', '-'), normalizedFactionId, StringComparison.OrdinalIgnoreCase))
            .Select(district => district.Name)
            .ToArray();
        var workspaceSummary = _campaignSpine.GetAccountSummary(user);
        string? resolvedCampaignId = string.IsNullOrWhiteSpace(campaignId)
            ? workspaceSummary.Workspaces.FirstOrDefault()?.CampaignId ?? workspaceSummary.Campaigns.FirstOrDefault()?.CampaignId
            : campaignId.Trim();
        var installLinking = _installLinking.GetSummary(user.UserId, user.SubjectId);
        CampaignWorkspaceProjection? starterWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking);
        CampaignWorkspaceServerPlaneProjection? workspaceServerPlane = starterWorkspace is null
            ? null
            : _workspaceServerPlane.GetWorkspaceServerPlane(user, starterWorkspace.WorkspaceId, installLinking);
        BlackLedgerWorldTurnBriefingViewModel? worldTurnBriefing = BuildProtectedBlackLedgerWorldTurnBriefing(1);
        RunnerPassportPublicSummary runnerPassportSummary = _communityCreatorHorizons.BuildPassportSummary();
        BlackLedgerPrivateLoreOverlayDto? overlay = string.IsNullOrWhiteSpace(resolvedCampaignId)
            ? null
            : _blackLedgerFactions.GetPrivateLoreOverlay(resolvedCampaignId, faction.Id);
        var privateLabels = overlay?.LabelMap?.Values?.Where(static label => !string.IsNullOrWhiteSpace(label)).Take(6).ToArray()
            ?? [$"{faction.PublicName} campaign alias", $"{faction.PublicName} safehouse codename", $"{faction.PublicName} pressure lane beta"];
        var privateLoreNotes = (overlay?.Notes?.Count > 0
                ? overlay.Notes
                : new[]
                {
                    "Private labels can exist on authenticated campaign routes only.",
                    "Public Black Ledger pages never render these labels or account-linked overlays.",
                    "The private-lore API receipt stays non-projecting by contract.",
                })
            .Take(6)
            .ToArray();
        string campaignQuery = string.IsNullOrWhiteSpace(resolvedCampaignId)
            ? string.Empty
            : $"?campaignId={Uri.EscapeDataString(resolvedCampaignId)}";
        var tabs = new[]
        {
            new BlackLedgerFactionWorkspaceTabViewModel("Overview", $"/account/ledger/factions/{normalizedFactionId}{campaignQuery}", string.Equals(currentSection, "overview", StringComparison.OrdinalIgnoreCase)),
            new BlackLedgerFactionWorkspaceTabViewModel("Manage", $"/account/ledger/factions/{normalizedFactionId}/manage{campaignQuery}", string.Equals(currentSection, "manage", StringComparison.OrdinalIgnoreCase)),
            new BlackLedgerFactionWorkspaceTabViewModel("Stewards", $"/account/ledger/factions/{normalizedFactionId}/stewards{campaignQuery}", string.Equals(currentSection, "stewards", StringComparison.OrdinalIgnoreCase)),
            new BlackLedgerFactionWorkspaceTabViewModel("Private lore", $"/account/ledger/factions/{normalizedFactionId}/private-lore{campaignQuery}", string.Equals(currentSection, "private-lore", StringComparison.OrdinalIgnoreCase)),
        };
        string intro = currentSection switch
        {
            "manage" => "Signed-in faction management for campaign pressure, district coverage, and private coordination.",
            "stewards" => "Steward roles stay explicit here so public summary roles never get confused with private campaign authority.",
            "private-lore" => "Private lore overlays can exist here for campaign context, but public Ledger pages must never render them.",
            _ => "Faction command workspace for the same Black Ledger world, with private labels and management details kept off public pages.",
        };

        return new BlackLedgerFactionWorkspacePageViewModel(
            Chrome: _chrome.BuildAuthenticatedChrome($"{faction.PublicName} workspace", "Signed-in Black Ledger faction management and private lore.", currentPath, user.DisplayName, user.Email),
            Eyebrow: "Faction command workspace",
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
            PrivacyNote: "Faction command workspaces may render private labels and campaign-scoped overlays. Public Ledger routes never do.",
            Allegiance: _blackLedgerFactions.GetAllegiance(user),
            AvailableActions: string.Equals(currentSection, "manage", StringComparison.OrdinalIgnoreCase) ? _blackLedgerFactions.GetActionDefinitions(faction.Id) : Array.Empty<BlackLedgerFactionActionDefinitionDto>(),
            RecentActionReceipts: _blackLedgerFactions.GetActionReceipts(faction.Id).Take(6).ToArray(),
            ConnectedLanePacket: BuildLedgerWorkspaceConnectedLanePacket(
                workspaceServerPlane,
                runnerPassportSummary,
                normalizedFactionId,
                worldTurnBriefing),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: _signedInTrustStatus.Build(user, manifest, releaseExperience));
    }

    private async Task<BlackLedgerFactionHomeViewModel> BuildLedgerFactionHomePageModel(HubUserDto user, CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated: true);
        _ = await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken);
        var chrome = _chrome.BuildAuthenticatedChrome("My Black Ledger faction", "Account Black Ledger faction home, welcome kit, and action trail.", "/account/ledger", user.DisplayName, user.Email);
        var installLinking = _installLinking.GetSummary(user.UserId, user.SubjectId);
        CampaignWorkspaceProjection? starterWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking);
        CampaignWorkspaceServerPlaneProjection? workspaceServerPlane = starterWorkspace is null
            ? null
            : _workspaceServerPlane.GetWorkspaceServerPlane(user, starterWorkspace.WorkspaceId, installLinking);
        RunnerPassportPublicSummary runnerPassportSummary = _communityCreatorHorizons.BuildPassportSummary();
        BlackLedgerFactionHomeViewModel model = _blackLedgerFactions.BuildFactionHome(chrome, user);
        string factionId = model.Faction.FactionId.Replace('_', '-');
        BlackLedgerWorldTurnBriefingViewModel? worldTurnBriefing = BuildProtectedBlackLedgerWorldTurnBriefing(1);
        return model with
        {
            NewsreelStatus = _blackLedgerTickNews.BuildStatusViewModel(
                worldId: "emerald-sprawl-prelude",
                turn: 1,
                scopeLabel: "Account lane",
                notificationsHref: "/account/ledger/notifications",
                turnHref: "/ledger/turns/1",
                dispatchHref: "/ledger/turns/1/dispatches",
                recipientUserId: user.UserId),
            WorldTurnBriefing = worldTurnBriefing,
            LeaderDigest = _blackLedgerBriefings.BuildLeaderDigest(factionId, 1),
            ValidationPacket = _blackLedgerBriefings.BuildValidationPacket(1, factionId),
            AdvisorySummary = _blackLedgerAdvisories.BuildSummary(user),
            FollowThroughPacket = BuildLedgerFollowThroughPacket(
                workspaceServerPlane,
                runnerPassportSummary,
                factionId,
                worldTurnBriefing)
        };
    }

    private static BlackLedgerFollowThroughPacketViewModel BuildLedgerFollowThroughPacket(
        CampaignWorkspaceServerPlaneProjection? workspaceServerPlane,
        RunnerPassportPublicSummary runnerPassportSummary,
        string factionId,
        BlackLedgerWorldTurnBriefingViewModel? worldTurnBriefing)
    {
        string signalDeckSummary = workspaceServerPlane?.Consequences.Count > 0
            ? $"Signal Deck is carrying {workspaceServerPlane.Consequences.Count} consequence cue(s) forward from the latest inbox reaction and workspace state."
            : "Signal Deck is ready, but no consequence cue has been written yet for this account.";
        string runnerPassportSummaryText =
            $"Runner Passport is live with {runnerPassportSummary.ActiveInstallationCount} claimed install(s), {runnerPassportSummary.OpenRunCount} public open run(s), and {runnerPassportSummary.ParticipationNotificationCount} participation record(s) on the Chummer path.";
        int aftermathCount = workspaceServerPlane?.AftermathPackages.Count ?? 0;
        string livingNewsroomSummary = worldTurnBriefing?.Broadcast is not null
            ? $"Living Newsroom is carrying {worldTurnBriefing.Broadcast.PackageLabel} as the public bulletin for this turn, so the same bulletin can frame what Signal Deck and the inbox are reacting to."
            : "Living Newsroom is ready for this turn, but the account has not attached a bulletin yet.";
        string livingNewsroomHref = worldTurnBriefing?.Broadcast?.WatchHref ?? "/ledger/turns/1";
        string aftermathSummary = aftermathCount > 0
            ? $"Aftermath currently holds {aftermathCount} package(s), so remote reactions can return as records and next steps instead of disappearing into flavor-only copy."
            : "No aftermath package is attached yet, so the next-step path stays ready until the next safe action writes one.";
        string aftermathHref = "/account/work#aftermath-packages";
        string summary = "After a Table Pulse Live reaction resolves, the result should survive as a durable next step: Signal Deck keeps the pressure cue visible, and Runner Passport keeps the return story clear.";
        string boundaryLine = "Next steps stay on Chummer pages only. Signal Deck shows current consequence state, and Runner Passport shows public continuity history without leaking private account or moderation detail.";

        BlackLedgerFollowThroughCueViewModel[] cues =
        [
            new(
                Label: "Signal Deck",
                Summary: signalDeckSummary,
                Href: "/signal-deck",
                StatusLabel: workspaceServerPlane?.Consequences.Count > 0 ? "Consequence-backed" : "Armed"),
            new(
                Label: "Runner Passport",
                Summary: runnerPassportSummaryText,
                Href: "/passport",
                StatusLabel: "Live"),
            new(
                Label: "Living Newsroom",
                Summary: livingNewsroomSummary,
                Href: worldTurnBriefing?.Broadcast?.WatchHref ?? "/ledger/turns/1",
                StatusLabel: worldTurnBriefing?.Broadcast is null ? "Armed" : "Bulletin"),
            new(
                Label: "Leader next steps",
                Summary: "Leader briefing stays the escalation path when a reaction outcome needs another command decision before the next turn.",
                Href: $"/account/ledger/factions/{factionId}/leader-briefing",
                StatusLabel: "Escalation"),
            new(
                Label: "Aftermath return",
                Summary: "Any remote reaction that lands as downtime or aftermath stays on the return path instead of becoming orphaned flavor text.",
                Href: "/account/work#aftermath-packages",
                StatusLabel: "Return")
        ];

        return new BlackLedgerFollowThroughPacketViewModel(
            Heading: "Signal Deck and Runner Passport continuity",
            Summary: summary,
            SignalDeckSummary: signalDeckSummary,
            RunnerPassportSummary: runnerPassportSummaryText,
            LivingNewsroomSummary: livingNewsroomSummary,
            LivingNewsroomHref: livingNewsroomHref,
            AftermathSummary: aftermathSummary,
            AftermathHref: aftermathHref,
            BoundaryLine: boundaryLine,
            Cues: cues);
    }

    private static BlackLedgerConnectedLanePacketViewModel BuildRunnerPassportConnectedLanePacket(
        RunnerPassportPublicSummary runnerPassportSummary,
        CampaignWorkspaceServerPlaneProjection? workspaceServerPlane,
        string? factionId,
        BlackLedgerWorldTurnBriefingViewModel? worldTurnBriefing)
    {
        int consequenceCount = workspaceServerPlane?.Consequences.Count ?? 0;
        int aftermathCount = workspaceServerPlane?.AftermathPackages.Count ?? 0;
        string leaderHref = string.IsNullOrWhiteSpace(factionId)
            ? "/account/ledger"
            : $"/account/ledger/factions/{factionId}/leader-briefing";
        string summary = "Runner Passport keeps public participation and return history together while still linking back to inbox reactions, Signal Deck, the newsroom, and aftermath.";
        string boundaryLine = "Runner Passport shows public summary status only. It can link back to account pages, but it does not expose private identity, moderation decisions, or transcript detail.";
        BlackLedgerFollowThroughCueViewModel[] cues =
        [
            new(
                Label: "Trust status",
                Summary: $"Passport is live with {runnerPassportSummary.ActiveInstallationCount} claimed install(s), {runnerPassportSummary.OpenRunCount} open run(s), and {runnerPassportSummary.ParticipationNotificationCount} participation record(s) in Chummer.",
                Href: "/passport/runner_return_posture.md",
                StatusLabel: "Public-safe"),
            new(
                Label: "Table Pulse Live inbox",
                Summary: consequenceCount > 0
                    ? $"The account inbox is already carrying {consequenceCount} consequence cue(s), so Passport history stays attached to real fallout instead of floating notes."
                    : "Table Pulse Live is ready for this account, so the next reaction can land on the same history instead of disappearing into a separate system.",
                Href: "/account/ledger/notifications",
                StatusLabel: workspaceServerPlane is null ? "Armed" : "Account"),
            new(
                Label: "Leader command",
                Summary: string.IsNullOrWhiteSpace(factionId)
                    ? "Sign in and join a faction to connect Runner Passport to the leader briefing and command view."
                    : "Use the leader briefing when a passport-safe reaction needs another decision instead of a detached note.",
                Href: leaderHref,
                StatusLabel: string.IsNullOrWhiteSpace(factionId) ? "Sign-in" : "Command-linked"),
            new(
                Label: "Living Newsroom",
                Summary: worldTurnBriefing?.Broadcast is not null
                    ? $"Living Newsroom is framing this turn through {worldTurnBriefing.Broadcast.PackageLabel}, so Runner Passport stays attached to the same public bulletin."
                    : "Living Newsroom is ready and will attach once the current turn publishes a bulletin.",
                Href: worldTurnBriefing?.Broadcast?.WatchHref ?? "/ledger/turns/1",
                StatusLabel: worldTurnBriefing?.Broadcast is null ? "Armed" : "Bulletin"),
            new(
                Label: "Aftermath return",
                Summary: aftermathCount > 0
                    ? $"{aftermathCount} aftermath package(s) are on the return path, so Passport continuity survives the off-table return."
                    : "Aftermath return stays ready even when the queue is empty, so status does not vanish when a session moves off-table.",
                Href: "/account/work#aftermath-packages",
                StatusLabel: aftermathCount > 0 ? "Queued" : "Armed")
        ];

        return new BlackLedgerConnectedLanePacketViewModel(
            Heading: "Runner Passport continuity",
            Summary: summary,
            BoundaryLine: boundaryLine,
            Cues: cues);
    }

    private static BlackLedgerConnectedLanePacketViewModel BuildSignalDeckConnectedLanePacket(
        SignalDeckPublicSummary signalDeckSummary,
        CampaignWorkspaceServerPlaneProjection? workspaceServerPlane,
        string? factionId,
        BlackLedgerWorldTurnBriefingViewModel? worldTurnBriefing)
    {
        int consequenceCount = workspaceServerPlane?.Consequences.Count ?? 0;
        int aftermathCount = workspaceServerPlane?.AftermathPackages.Count ?? 0;
        string leaderHref = string.IsNullOrWhiteSpace(factionId)
            ? "/account/ledger"
            : $"/account/ledger/factions/{factionId}/leader-briefing";
        string summary = "Signal Deck keeps pressure cues, inbox reactions, newsroom framing, and aftermath together on one page.";
        string boundaryLine = "Signal Deck shows current command state only. It does not publish private transcripts, hidden moderation state, or automatic world changes.";
        BlackLedgerFollowThroughCueViewModel[] cues =
        [
            new(
                Label: "Command pressure",
                Summary: consequenceCount > 0
                    ? $"{consequenceCount} consequence cue(s) are already live, so Signal Deck is carrying real fallout instead of speculative flavor."
                    : "Signal Deck is ready before the next reaction resolves, so the next inbox packet can stay on the same page.",
                Href: "/account/ledger/notifications",
                StatusLabel: consequenceCount > 0 ? "Consequence-backed" : "Armed"),
            new(
                Label: "Leader command",
                Summary: string.IsNullOrWhiteSpace(factionId)
                    ? "Join a faction to connect Signal Deck to the leader briefing and GM cockpit."
                    : "Use the leader briefing when Signal Deck pressure needs another decision before the next turn.",
                Href: leaderHref,
                StatusLabel: string.IsNullOrWhiteSpace(factionId) ? "Sign-in" : "Cockpit"),
            new(
                Label: "Living Newsroom",
                Summary: worldTurnBriefing?.Broadcast is not null
                    ? $"Living Newsroom is currently framed by {worldTurnBriefing.Broadcast.PackageLabel}, so Signal Deck stays attached to the same public bulletin."
                    : "Living Newsroom is ready and will attach when the current turn publishes a bulletin.",
                Href: worldTurnBriefing?.Broadcast?.WatchHref ?? "/ledger/turns/1",
                StatusLabel: worldTurnBriefing?.Broadcast is null ? "Armed" : "Bulletin"),
            new(
                Label: "Aftermath return",
                Summary: aftermathCount > 0
                    ? $"{aftermathCount} aftermath package(s) are already queued, so Signal Deck pressure survives the off-table return."
                    : "Aftermath return stays attached even when no package is queued yet, so command pressure does not disappear after adjudication.",
                Href: "/account/work#aftermath-packages",
                StatusLabel: aftermathCount > 0 ? "Queued" : "Armed"),
            new(
                Label: "Public records",
                Summary: $"Signal Deck records currently summarize {signalDeckSummary.ActiveInstallationCount} active install(s), {signalDeckSummary.OpenRunCount} open run(s), and {signalDeckSummary.ParticipationNotificationCount} participation record(s) in Chummer.",
                Href: "/signal-deck/pressure_posture.md",
                StatusLabel: "Details")
        ];

        return new BlackLedgerConnectedLanePacketViewModel(
            Heading: "Signal Deck command",
            Summary: summary,
            BoundaryLine: boundaryLine,
            Cues: cues);
    }

    private static BlackLedgerConnectedLanePacketViewModel BuildLivingWorldConnectedLanePacket(
        LivingWorldPublicSummary livingWorldSummary,
        CampaignWorkspaceServerPlaneProjection? workspaceServerPlane,
        string? factionId,
        BlackLedgerWorldTurnBriefingViewModel? worldTurnBriefing)
    {
        int consequenceCount = workspaceServerPlane?.Consequences.Count ?? 0;
        int aftermathCount = workspaceServerPlane?.AftermathPackages.Count ?? 0;
        string leaderHref = string.IsNullOrWhiteSpace(factionId)
            ? "/account/ledger"
            : $"/account/ledger/factions/{factionId}/leader-briefing";
        string summary = "Living World keeps the between-session parts together: the current bulletin, command continuity, Runner Passport, and aftermath stay attached to the same turn.";
        string boundaryLine = "Living World can frame and carry continuity, but it does not claim automatic simulation or detached world control.";
        BlackLedgerFollowThroughCueViewModel[] cues =
        [
            new(
                Label: "Current bulletin",
                Summary: worldTurnBriefing?.Broadcast is not null
                    ? $"Living Newsroom is currently carrying {worldTurnBriefing.Broadcast.PackageLabel}, so the same public bulletin frames what the command side is reacting to."
                    : "Bulletin framing is ready and will attach once the current turn publishes it.",
                Href: worldTurnBriefing?.Broadcast?.WatchHref ?? "/ledger/turns/1",
                StatusLabel: worldTurnBriefing?.Broadcast is null ? "Armed" : "Bulletin"),
            new(
                Label: "Table Pulse Live inbox",
                Summary: consequenceCount > 0
                    ? $"{consequenceCount} consequence cue(s) are already live, so between-session continuity stays attached to current command state."
                    : "The account inbox is ready so the next remote reaction can enter the same between-session loop.",
                Href: "/account/ledger/notifications",
                StatusLabel: consequenceCount > 0 ? "Consequence-backed" : "Inbox"),
            new(
                Label: "Faction command",
                Summary: string.IsNullOrWhiteSpace(factionId)
                    ? "Join a faction to connect Living World continuity to the leader briefing and command view."
                    : "Leader briefing keeps between-session escalation on the same path instead of a detached lore layer.",
                Href: leaderHref,
                StatusLabel: string.IsNullOrWhiteSpace(factionId) ? "Sign-in" : "Command-linked"),
            new(
                Label: "Runner Passport",
                Summary: $"Runner Passport keeps {livingWorldSummary.ActiveInstallationCount} active install(s) and {livingWorldSummary.ParticipationNotificationCount} participation record(s) attached to this same between-session path.",
                Href: "/passport",
                StatusLabel: "Continuity"),
            new(
                Label: "Aftermath return",
                Summary: aftermathCount > 0
                    ? $"{aftermathCount} aftermath package(s) are already queued, so Living World fallout survives the off-table return."
                    : "Aftermath return stays attached even before the next package is written, so the between-session path stays concrete.",
                Href: "/account/work#aftermath-packages",
                StatusLabel: aftermathCount > 0 ? "Queued" : "Armed")
        ];

        return new BlackLedgerConnectedLanePacketViewModel(
            Heading: "Living World continuity",
            Summary: summary,
            BoundaryLine: boundaryLine,
            Cues: cues);
    }

    private static BlackLedgerConnectedLanePacketViewModel BuildLedgerWorkspaceConnectedLanePacket(
        CampaignWorkspaceServerPlaneProjection? workspaceServerPlane,
        RunnerPassportPublicSummary runnerPassportSummary,
        string factionId,
        BlackLedgerWorldTurnBriefingViewModel? worldTurnBriefing)
    {
        int consequenceCount = workspaceServerPlane?.Consequences.Count ?? 0;
        int aftermathCount = workspaceServerPlane?.AftermathPackages.Count ?? 0;
        string summary = "Faction workspace is part of the same command path as Table Pulse Live, Signal Deck, Runner Passport, Living Newsroom, and aftermath. Command does not end at action points; it carries through to fallout.";
        string boundaryLine = "Workspace command stays in the account and attached to Chummer state. It can route pressure, command, and fallout, but it does not publish private lore or invent public world state outside Chummer pages.";
        BlackLedgerFollowThroughCueViewModel[] cues =
        [
            new(
                Label: "Table Pulse Live inbox",
                Summary: consequenceCount > 0
                    ? $"{consequenceCount} consequence cue(s) are already live from the inbox, so this workspace can act on real pressure."
                    : "Open the account inbox to review or trigger the next remote reaction before spending command effort here.",
                Href: "/account/ledger/notifications",
                StatusLabel: consequenceCount > 0 ? "Consequence-backed" : "Inbox"),
            new(
                Label: "Leader briefing",
                Summary: "Escalate into the GM cockpit when a faction action needs another command decision, adjudication, or continuity review.",
                Href: $"/account/ledger/factions/{factionId}/leader-briefing",
                StatusLabel: "Cockpit"),
            new(
                Label: "Runner Passport",
                Summary: $"Runner Passport is carrying {runnerPassportSummary.ActiveInstallationCount} claimed install(s) and {runnerPassportSummary.ParticipationNotificationCount} participation event(s), so faction continuity stays attached to real runner continuity.",
                Href: "/passport",
                StatusLabel: "Passport"),
            new(
                Label: "Living Newsroom",
                Summary: worldTurnBriefing?.Broadcast is not null
                    ? $"Public fallout is currently framed by {worldTurnBriefing.Broadcast.PackageLabel}, keeping faction command tied to the same bulletin as the public page."
                    : "Living Newsroom is ready and will attach here once the current turn publishes a bulletin.",
                Href: worldTurnBriefing?.Broadcast?.WatchHref ?? "/ledger/turns/1",
                StatusLabel: worldTurnBriefing?.Broadcast is null ? "Armed" : "Bulletin"),
            new(
                Label: "Aftermath return",
                Summary: aftermathCount > 0
                    ? $"{aftermathCount} aftermath package(s) are on the return path, so this workspace can review fallout instead of losing the thread after adjudication."
                    : "Aftermath return is attached even when the queue is empty, so the workspace stays connected to follow-up status.",
                Href: "/account/work#aftermath-packages",
                StatusLabel: aftermathCount > 0 ? "Queued" : "Armed")
        ];

        return new BlackLedgerConnectedLanePacketViewModel(
            Heading: "Faction command",
            Summary: summary,
            BoundaryLine: boundaryLine,
            Cues: cues);
    }

    private async Task<BlackLedgerNotificationsPageViewModel> BuildLedgerNotificationsPageModel(HubUserDto user, string subjectId, CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated: true);
        _ = await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken);
        var chrome = _chrome.BuildAuthenticatedChrome("Black Ledger notifications", "Account Black Ledger newsreel delivery status and history.", "/account/ledger/notifications", user.DisplayName, user.Email);
        var installLinking = _installLinking.GetSummary(user.UserId, subjectId);
        CampaignWorkspaceProjection? starterWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking);
        CampaignWorkspaceServerPlaneProjection? workspaceServerPlane = starterWorkspace is null
            ? null
            : _workspaceServerPlane.GetWorkspaceServerPlane(user, starterWorkspace.WorkspaceId, installLinking);
        string? factionId = _blackLedgerFactions.GetAllegiance(user)?.ActiveFactionId?.Replace('_', '-');
        BlackLedgerNewsStatusViewModel status = _blackLedgerTickNews.BuildStatusViewModel(
            worldId: "emerald-sprawl-prelude",
            turn: 1,
            scopeLabel: "Account",
            notificationsHref: "/account/ledger/notifications",
            turnHref: "/ledger/turns/1",
            dispatchHref: "/ledger/turns/1/dispatches",
            recipientUserId: user.UserId);
        BlackLedgerWorldTurnBriefingViewModel? worldTurnBriefing = BuildProtectedBlackLedgerWorldTurnBriefing(1);
        BlackLedgerWorldTickValidationPacketViewModel? validationPacket = _blackLedgerBriefings.BuildValidationPacket(1, factionId);
        BlackLedgerFactionLeaderDigestViewModel? leaderDigest = string.IsNullOrWhiteSpace(factionId)
            ? null
            : _blackLedgerBriefings.BuildLeaderDigest(factionId, 1);
        BlackLedgerFactionPromoArtifactViewModel? promoArtifact = string.IsNullOrWhiteSpace(factionId)
            ? null
            : _blackLedgerFactions.GetPromoArtifact(factionId);
        _blackLedgerTickNews.BackfillInboxEntries(user.UserId);
        List<BlackLedgerInboxMessageViewModel> inboxMessages = _blackLedgerTickNews.ListInboxEntries(user.UserId)
            .Select(static item => new BlackLedgerInboxMessageViewModel(
                Kind: item.Kind,
                Eyebrow: item.Eyebrow,
                Heading: item.Heading,
                Summary: item.Summary,
                Href: item.Href,
                CtaLabel: item.CtaLabel,
                StatusLabel: item.StatusLabel))
            .ToList();
        if (inboxMessages.Count == 0)
        {
            inboxMessages =
            [
                new(
                    Kind: "newsreel",
                    Eyebrow: "World turn",
                    Heading: worldTurnBriefing?.InboxHeadline ?? "Turn 1 newsreel is ready",
                    Summary: worldTurnBriefing?.NewsreelLead ?? status.Summary,
                    Href: "/ledger/turns/1",
                    CtaLabel: "Open newsreel",
                    StatusLabel: status.StatusLabel),
                new(
                    Kind: "validation",
                    Eyebrow: "World state",
                    Heading: "World turn",
                    Summary: validationPacket?.Summary ?? "Review the inbox-safe world turn against the same current turn details.",
                    Href: "/account/ledger/worldtick/validation",
                    CtaLabel: "Open turn review",
                    StatusLabel: "Ready")
            ];

            if (leaderDigest is not null)
            {
                inboxMessages.Add(new BlackLedgerInboxMessageViewModel(
                    Kind: "leader_digest",
                    Eyebrow: "Leader brief",
                    Heading: $"{leaderDigest.PublicName} personalized digest",
                    Summary: leaderDigest.Summary,
                    Href: $"/account/ledger/factions/{leaderDigest.FactionId}/leader-briefing",
                    CtaLabel: "Open leader brief",
                    StatusLabel: "Personalized"));
            }

            if (promoArtifact is not null)
            {
                inboxMessages.Add(new BlackLedgerInboxMessageViewModel(
                    Kind: "promo",
                    Eyebrow: "Faction promo",
                    Heading: $"{promoArtifact.PublicName} motion preview",
                    Summary: $"{promoArtifact.CampaignHook} {promoArtifact.AudiencePromise}",
                    Href: promoArtifact.HtmlHref,
                    CtaLabel: "Open promo",
                    StatusLabel: "Public-safe"));
            }
        }

        BlackLedgerAdvisorySummaryViewModel advisorySummary = _blackLedgerAdvisories.BuildSummary(user);
        if (advisorySummary.PlayerBallots.Count > 0 || advisorySummary.GmBallots.Count > 0 || advisorySummary.ExecutiveSummaries.Count > 0)
        {
            inboxMessages.Insert(0, new BlackLedgerInboxMessageViewModel(
                Kind: "advisory",
                Eyebrow: "Advisory",
                Heading: advisorySummary.Heading,
                Summary: advisorySummary.NoDemocracyNote,
                Href: "/account/ledger/advisory",
                CtaLabel: "Open advisory",
                StatusLabel: "Advisory"));
        }

        BlackLedgerTablePulsePacketViewModel tablePulsePacket = BuildLedgerTablePulsePacket(
            status,
            worldTurnBriefing,
            validationPacket,
            leaderDigest,
            promoArtifact,
            workspaceServerPlane);

        return new BlackLedgerNotificationsPageViewModel(
            Chrome: chrome,
            Heading: "Black Ledger inbox",
            Intro: "This page shows the inbox-safe newsreel, whether delivery happened, and the world state behind the current turn for this account.",
            Status: status,
            DeliveryNotes:
            [
                "Inbox copy is explicit about the Turn 0 -> Turn 1 boundary.",
                "Preview policy can suppress delivery to regular accounts without hiding the reason.",
                "Duplicate sends are blocked by the stored event key, not by vague best effort.",
                "Advisory voting remains upstream signal. Players inform GMs, GMs inform leaders, and the chain can still overrule the vote."
            ],
            InboxMessages: inboxMessages,
            TablePulsePacket: tablePulsePacket,
            WorldTurnBriefing: worldTurnBriefing,
            ValidationPacket: validationPacket,
            AdvisorySummary: advisorySummary);
    }

    private static BlackLedgerTablePulsePacketViewModel BuildLedgerTablePulsePacket(
        BlackLedgerNewsStatusViewModel status,
        BlackLedgerWorldTurnBriefingViewModel? worldTurnBriefing,
        BlackLedgerWorldTickValidationPacketViewModel? validationPacket,
        BlackLedgerFactionLeaderDigestViewModel? leaderDigest,
        BlackLedgerFactionPromoArtifactViewModel? promoArtifact,
        CampaignWorkspaceServerPlaneProjection? workspaceServerPlane)
    {
        string heatPosture = worldTurnBriefing is null
            ? "Heat is quiet enough to hold notifications only."
            : $"{worldTurnBriefing.WorldName} is carrying live district pressure into Turn {worldTurnBriefing.ToTurn}; treat inbox opens as heat-bearing moves, not passive updates.";
        string notificationPosture = $"Delivery policy is {status.Policy.ToLowerInvariant()} with {status.ReceiptCount} stored record(s) across {status.RecipientCount} recipient destination(s).";
        string remoteReactionPosture = leaderDigest is null
            ? "Remote reactions stay contained here: respond from the inbox, then escalate into GM adjudication before consequences land."
            : $"{leaderDigest.PublicName} can turn inbox beats into remote reactions, minigame prompts, and command decisions before the next turn lands.";
        string signalDeckPosture = promoArtifact is null
            ? "Signal Deck stays attached to the same inbox packet so command visuals, pressure cues, and records do not split into a second page."
            : $"{promoArtifact.PublicName} promo previews are ready to amplify Signal Deck cues without leaving the account page.";
        string runnerPassportPosture = leaderDigest is null
            ? "Runner Passport stays ready to stamp return status, trust, and private continuity after each remote reaction."
            : $"Runner Passport can stamp {leaderDigest.PublicName} response status, return trust, and cross-table continuity after the current inbox action.";
        string aftermathPosture = workspaceServerPlane?.AftermathPackages.Count > 0
            ? $"Table Pulse Aftermath is holding {workspaceServerPlane.AftermathPackages.Count} return package(s) so recap and coaching stay attached to the same Chummer page."
            : "Table Pulse Aftermath stays private and ready even when no package is queued yet, so debrief and coaching remain separate from the live page.";
        string verdictLabel = workspaceServerPlane is null
            ? "Consent-gated preview"
            : "Account path";
        string boundaryLine = workspaceServerPlane is null
            ? "No workspace means no live reaction write path. Table Pulse Live stays read-only instead of inventing detached minigame results, and Table Pulse Aftermath stays parked."
            : "Table Pulse Live can write current consequence state on the account workspace page. It does not publish world state, public scores, or private session transcripts. Table Pulse Aftermath remains the separate private return page.";
        string consentPosture = "Table Pulse Live is opt-in and review-based. Remote reactions are mini-games and packets, not direct table mutation or automatic world-state authority. Table Pulse Aftermath remains private and GM-controlled.";

        List<BlackLedgerTablePulseCueViewModel> cues =
        [
            new(
                Label: "Heat",
                Summary: heatPosture,
                StatusLabel: "Live pressure",
                Href: status.TurnHref),
            new(
                Label: "Notifications",
                Summary: notificationPosture,
                StatusLabel: status.StatusLabel,
                Href: status.NotificationsHref),
            new(
                Label: "Remote reactions",
                Summary: remoteReactionPosture,
                StatusLabel: "GM review",
                Href: "/account/ledger/worldtick/validation"),
            new(
                Label: "Signal Deck",
                Summary: signalDeckPosture,
                StatusLabel: promoArtifact is null ? "Ready" : "Promo-backed",
                Href: "/signal-deck"),
            new(
                Label: "Runner Passport",
                Summary: runnerPassportPosture,
                StatusLabel: "Return-safe",
                Href: "/passport")
        ];

        if (validationPacket is not null)
        {
            cues.Add(new BlackLedgerTablePulseCueViewModel(
                Label: "Validation",
                Summary: validationPacket.Summary,
                StatusLabel: "Recorded",
                Href: "/account/ledger/worldtick/validation"));
        }

        BlackLedgerRemoteReactionOptionViewModel[] reactionOptions = workspaceServerPlane is null
            ? Array.Empty<BlackLedgerRemoteReactionOptionViewModel>()
            : [
                new("intercept", "Intercept", "heat", "Cut the hottest consequence line early and trade tempo for lower exposure.", "Adjudicate intercept"),
                new("cover-story", "Cover Story", "reputation", "Shift public framing before the next world turn makes the damage stick.", "Adjudicate cover story"),
                new("scramble", "Scramble", "contact", "Stabilize contact fallout and route pressure before the next follow-up.", "Adjudicate scramble"),
                new("temptation", "Temptation", "faction", "Push a risky faction offer that can buy leverage at the cost of trust.", "Adjudicate temptation"),
                new("shadow-reply", "Shadow Reply", "downtime", "Queue an off-table response packet that resolves on the aftermath page.", "Adjudicate shadow reply")
            ];

        string? adjudicationSummary = workspaceServerPlane?.Consequences.Count > 0
            ? $"Current consequence state: {string.Join(", ", workspaceServerPlane.Consequences.Take(3).Select(static item => $"{item.Label} {item.State}"))}."
            : workspaceServerPlane is null
                ? "Adjudication is parked until a workspace is available for this account."
                : null;

        string summary = "Table Pulse Live turns the account inbox into a command packet: read world heat, confirm delivery, trigger remote reactions, and keep Signal Deck plus Runner Passport on the same page. Table Pulse Aftermath is the separate private return page.";
        string[] labels =
        [
            "Table Pulse Live",
            "heat threshold watch",
            "delivery records",
            "remote reaction minigames",
            "Signal Deck",
            "Runner Passport",
            "Table Pulse Aftermath"
        ];

        return new BlackLedgerTablePulsePacketViewModel(
            Heading: "Table Pulse Live",
            Summary: summary,
            VerdictLabel: verdictLabel,
            BoundaryLine: boundaryLine,
            ConsentPosture: consentPosture,
            HeatPosture: heatPosture,
            NotificationPosture: notificationPosture,
            RemoteReactionPosture: remoteReactionPosture,
            SignalDeckPosture: signalDeckPosture,
            RunnerPassportPosture: runnerPassportPosture,
            AftermathPosture: aftermathPosture,
            AftermathHref: "/account/work",
            EntryHref: status.NotificationsHref,
            Labels: labels,
            Cues: cues,
            ReactionOptions: reactionOptions,
            AdjudicationSummary: adjudicationSummary);
    }

    private static CampaignConsequenceUpdateRequest BuildTablePulseReactionConsequenceRequest(string reactionId)
    {
        string normalizedReactionId = AccountService.NormalizeOptional(reactionId)?.ToLowerInvariant()
            ?? throw new ArgumentException("reaction id is required.", nameof(reactionId));

        return normalizedReactionId switch
        {
            "intercept" => new CampaignConsequenceUpdateRequest(
                Kind: "heat",
                State: "contained",
                Summary: "Remote intercept adjudication absorbed the hottest pressure line before it spilled into the next turn packet.",
                ReturnLoopAction: "Review heat fallout",
                ReturnLoopRoute: "/account/work",
                Note: "Table Pulse Live remote reaction: intercept"),
            "cover-story" => new CampaignConsequenceUpdateRequest(
                Kind: "reputation",
                State: "under_review",
                Summary: "Cover Story adjudication is holding the public narrative in review until records catch up.",
                ReturnLoopAction: "Review reputation fallout",
                ReturnLoopRoute: "/account/work",
                Note: "Table Pulse Live remote reaction: cover story"),
            "scramble" => new CampaignConsequenceUpdateRequest(
                Kind: "contact",
                State: "fragile",
                Summary: "Scramble adjudication kept the contact network live, but the route is still fragile and needs a continuity pass.",
                ReturnLoopAction: "Review contact fallout",
                ReturnLoopRoute: "/account/work",
                Note: "Table Pulse Live remote reaction: scramble"),
            "temptation" => new CampaignConsequenceUpdateRequest(
                Kind: "faction",
                State: "strained",
                Summary: "Temptation adjudication created faction leverage, but it also strained the standing that has to be justified on the next safe return.",
                ReturnLoopAction: "Confirm faction standing",
                ReturnLoopRoute: "/account/work",
                Note: "Table Pulse Live remote reaction: temptation"),
            "shadow-reply" => new CampaignConsequenceUpdateRequest(
                Kind: "downtime",
                State: "queued",
                Summary: "Shadow Reply adjudication queued an off-table response packet on the aftermath path.",
                ReturnLoopAction: "Review downtime obligations",
                ReturnLoopRoute: "/account/work#aftermath-packages",
                Note: "Table Pulse Live remote reaction: shadow reply"),
            _ => throw new ArgumentException($"Unsupported Table Pulse Live reaction id: {reactionId}", nameof(reactionId))
        };
    }

    private async Task<BlackLedgerLeaderBriefingPageViewModel?> BuildLedgerFactionLeaderBriefingPageModel(HubUserDto user, string factionId, CancellationToken cancellationToken)
    {
        _ = cancellationToken;
        BlackLedgerAccountFactionAllegianceDto? allegiance = _blackLedgerFactions.GetAllegiance(user);
        if (allegiance is null
            || !string.Equals(allegiance.ActiveFactionId.Replace('_', '-'), factionId.Replace('_', '-'), StringComparison.OrdinalIgnoreCase))
        {
            return null;
        }

        BlackLedgerFactionLeaderDigestViewModel? digest = _blackLedgerBriefings.BuildLeaderDigest(factionId, 1);
        if (digest is null)
        {
            return null;
        }

        var installLinking = _installLinking.GetSummary(user.UserId, user.SubjectId);
        CampaignWorkspaceProjection? starterWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking);
        CampaignWorkspaceServerPlaneProjection? workspaceServerPlane = starterWorkspace is null
            ? null
            : _workspaceServerPlane.GetWorkspaceServerPlane(user, starterWorkspace.WorkspaceId, installLinking);
        RunnerPassportPublicSummary runnerPassportSummary = _communityCreatorHorizons.BuildPassportSummary();
        BlackLedgerWorldTurnBriefingViewModel? worldTurnBriefing = BuildProtectedBlackLedgerWorldTurnBriefing(1);

        return new BlackLedgerLeaderBriefingPageViewModel(
            Chrome: _chrome.BuildAuthenticatedChrome(
                $"{digest.PublicName} leader brief",
                "Signed-in faction-leader digest for the active Black Ledger allegiance.",
                $"/account/ledger/factions/{digest.FactionId}/leader-briefing",
                user.DisplayName,
                user.Email),
            Heading: digest.Heading,
            Intro: "This is the personalized world-turn readout for the faction leader. It turns the current public board into specific pressure calls and focused next moves.",
            Digest: digest,
            WorldTurnBriefing: worldTurnBriefing,
            ValidationPacket: _blackLedgerBriefings.BuildValidationPacket(1, digest.FactionId),
            GmCockpitPacket: BuildLedgerGmCockpitPacket(
                workspaceServerPlane,
                runnerPassportSummary,
                digest.FactionId,
                worldTurnBriefing));
    }

    private static BlackLedgerGmCockpitPacketViewModel BuildLedgerGmCockpitPacket(
        CampaignWorkspaceServerPlaneProjection? workspaceServerPlane,
        RunnerPassportPublicSummary runnerPassportSummary,
        string factionId,
        BlackLedgerWorldTurnBriefingViewModel? worldTurnBriefing)
    {
        string commandPosture = workspaceServerPlane?.Consequences.Count > 0
            ? $"{workspaceServerPlane.Consequences.Count} consequence cue(s) are live; leader escalation should stay on explicit follow-up actions instead of freeform side decisions."
            : "No consequence cue is active yet, so the cockpit remains a focused readout instead of a mutation-heavy control panel.";
        int aftermathCount = workspaceServerPlane?.AftermathPackages.Count ?? 0;
        string livingNewsroomSummary = worldTurnBriefing?.Broadcast is not null
            ? $"Living Newsroom is carrying {worldTurnBriefing.Broadcast.PackageLabel}; use the same public bulletin when you want the command desk to review how the turn is framed outside the private cockpit."
            : "Living Newsroom is available, but no bulletin is attached to this briefing yet.";
        string livingNewsroomHref = worldTurnBriefing?.Broadcast?.WatchHref ?? "/ledger/turns/1";
        string aftermathSummary = aftermathCount > 0
            ? $"Aftermath queue has {aftermathCount} package(s) waiting on the return path, so GM review can stay attached to concrete fallout instead of freeform notes."
            : "Aftermath queue is empty right now, so this cockpit is reading state rather than shepherding live fallout packages.";
        string aftermathHref = "/account/work#aftermath-packages";
        string summary = "GM cockpit keeps remote-reaction aftermath on one command path: review consequences, escalate to leader intent, preserve Signal Deck continuity, and keep Runner Passport limited.";
        string boundaryLine = "This cockpit can interpret and escalate current consequence state only. It does not create public scores, mutate world state directly, or reveal private session transcripts.";
        BlackLedgerFollowThroughCueViewModel[] cues =
        [
            new(
                Label: "Reaction inbox",
                Summary: "Open the signed-in notifications page to review or trigger remote reactions before the next world turn locks in.",
                Href: "/account/ledger/notifications",
                StatusLabel: "Inbox"),
            new(
                Label: "Aftermath return",
                Summary: "Downtime and aftermath consequences stay attached to the return path when a remote reaction resolves off-table.",
                Href: "/account/work#aftermath-packages",
                StatusLabel: "Return"),
            new(
                Label: "Runner Passport",
                Summary: $"Runner Passport currently carries {runnerPassportSummary.ActiveInstallationCount} claimed install(s) and {runnerPassportSummary.ParticipationNotificationCount} participation record(s) in Chummer.",
                Href: "/passport",
                StatusLabel: "Passport"),
            new(
                Label: "Living Newsroom",
                Summary: livingNewsroomSummary,
                Href: worldTurnBriefing?.Broadcast?.WatchHref ?? "/ledger/turns/1",
                StatusLabel: worldTurnBriefing?.Broadcast is null ? "Armed" : "Bulletin"),
            new(
                Label: "Faction command",
                Summary: "Escalate from the briefing back into faction command when a reaction outcome needs new action points, district status, or private review.",
                Href: $"/account/ledger/factions/{factionId}",
                StatusLabel: "Command")
        ];

        return new BlackLedgerGmCockpitPacketViewModel(
            Heading: "GM cockpit continuity",
            Summary: summary,
            CommandPosture: commandPosture,
            LivingNewsroomSummary: livingNewsroomSummary,
            LivingNewsroomHref: livingNewsroomHref,
            AftermathSummary: aftermathSummary,
            AftermathHref: aftermathHref,
            BoundaryLine: boundaryLine,
            Cues: cues);
    }

    private async Task<BlackLedgerWorldTickValidationPageViewModel> BuildLedgerWorldTickValidationPageModel(HubUserDto user, CancellationToken cancellationToken)
    {
        _ = cancellationToken;
        BlackLedgerAccountFactionAllegianceDto? allegiance = _blackLedgerFactions.GetAllegiance(user);
        string? factionId = allegiance?.ActiveFactionId?.Replace('_', '-');
        BlackLedgerWorldTickValidationPacketViewModel packet = _blackLedgerBriefings.BuildValidationPacket(1, factionId)
            ?? throw new InvalidOperationException("Black Ledger validation packet is unavailable.");
        return new BlackLedgerWorldTickValidationPageViewModel(
            Chrome: _chrome.BuildAuthenticatedChrome(
                "Black Ledger world-turn review",
                "Signed-in turn details for inbox newsreel, leader brief, and public world-turn status.",
                "/account/ledger/worldtick/validation",
                user.DisplayName,
                user.Email),
            Heading: "World turn",
            Intro: "Use this page to review the inbox newsreel, the public turn update, and the faction-leader readout against the same current turn details.",
            Packet: packet,
            WorldTurnBriefing: BuildProtectedBlackLedgerWorldTurnBriefing(1),
            LeaderDigest: string.IsNullOrWhiteSpace(factionId) ? null : _blackLedgerBriefings.BuildLeaderDigest(factionId, 1));
    }

    private async Task<BlackLedgerFactionOnboardingViewModel> BuildLedgerOnboardingPageModel(HubUserDto user, string? step, CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated: true);
        _ = await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken);
        var chrome = _chrome.BuildAuthenticatedChrome("Black Ledger onboarding", "Signed-in faction allegiance and founder path onboarding.", "/account/ledger/onboarding", user.DisplayName, user.Email);
        return _blackLedgerFactions.BuildOnboardingModel(chrome, user, step);
    }

    private async Task<BlackLedgerFactionCreatePageViewModel> BuildLedgerFactionCreatePageModel(HubUserDto user, string? charterType, CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated: true);
        _ = await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken);
        var chrome = _chrome.BuildAuthenticatedChrome("Create Black Ledger faction", "Signed-in faction charter builder with route-backed major and challenger flows.", "/account/ledger/factions/create", user.DisplayName, user.Email);
        return _blackLedgerFactions.BuildCreatePage(chrome, user, charterType);
    }

    private async Task<BlackLedgerFactionPromoPageViewModel?> BuildLedgerFactionPromoPageModel(string factionId, CancellationToken cancellationToken)
    {
        BlackLedgerFactionPromoArtifactViewModel? promo = _blackLedgerFactions.GetPromoArtifact(factionId);
        if (promo is null)
        {
            return null;
        }

        BlackLedgerFactionPromoArtifactViewModel publicPromo = BuildPublicFactionPromoArtifact(promo);

        return new BlackLedgerFactionPromoPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync(
                $"{publicPromo.PublicName} war bulletin",
                "Public-safe faction bulletin media with cinematic playback, captions, and storyboard fallback.",
                $"/ledger/factions/{publicPromo.FactionId}/promo",
                cancellationToken),
            Heading: $"{publicPromo.PublicName} mobilization bulletin",
            Intro: "This page presents the faction reel with visible characters, action, captions, supporting data, and a storyboard fallback. It should feel cinematic while staying tied to the current campaign state.",
            Promo: publicPromo,
            DeliveryNotes:
            [
                "The video stays tied to the same faction and turn data as the rest of Black Ledger.",
                "Storyboard fallback remains available if motion playback is unavailable, but it still carries the same scene-driven bulletin energy.",
                "No official lore text and no provider branding appear here.",
                "These links open real assets, not placeholders.",
                "The same faction and turn details drive the public bulletin and the signed-in follow-up pages."
            ]);
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
                "Rules-light play, campaign city consequence, and dispatch-backed mobile continuity.",
                currentPath,
                cancellationToken),
            Eyebrow: eyebrow,
            Heading: heading,
            Intro: intro,
            CurrentSection: currentSection,
            RulesetId: AnarchyPreviewService.RulesetId,
            VerdictLabel: "Shipped rules-light path",
            ScopeLabel: "Dedicated ruleset path",
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
        string hubLocalReleaseProofUrl,
        string releaseUploadAuthEnvironmentVariable,
        string releaseUploadAuth)
    {
        return "set -euo pipefail; " +
            "TMP_BOOTSTRAP_SCRIPT=\"$(mktemp)\"; " +
            "trap 'rm -f \"$TMP_BOOTSTRAP_SCRIPT\"' EXIT; " +
            "curl -fsSL " + SingleQuoteShellValue(bootstrapUrl) + " > \"$TMP_BOOTSTRAP_SCRIPT\" || { echo 'Failed to fetch setup script; refresh the release page and retry.' >&2; exit 1; }; " +
            "ACTUAL_BOOTSTRAP_SHA256=\"$(python3 -c 'import hashlib, pathlib, sys; print(hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest())' \"$TMP_BOOTSTRAP_SCRIPT\")\"; " +
            "[[ \"$ACTUAL_BOOTSTRAP_SHA256\" == " + SingleQuoteShellValue(bootstrapSha256) + " ]] || { echo 'Setup script check failed; refresh the release page and retry.' >&2; exit 1; }; " +
            "CHUMMER_RELEASE_CHANNEL='preview' " +
            "CHUMMER_ALLOW_UNSIGNED_PREVIEW='1' " +
            "CHUMMER_ALLOW_REMOTE_RELEASE_PROOF_INPUTS='1' " +
            "CHUMMER_HUB_LOCAL_RELEASE_PROOF_URL=" + SingleQuoteShellValue(hubLocalReleaseProofUrl) + " " +
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
