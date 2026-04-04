using System.Text;
using System.Text.Json;
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
using Microsoft.AspNetCore.Http.Extensions;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.WebUtilities;

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
    private readonly PublicCreatorPublicationDiscoveryService _publicCreatorDiscovery;
    private readonly HubPageChromeService _chrome;
    private readonly PublicTrustContentService _trustContent;
    private readonly PublicPrivacyBoundaryService _privacyBoundaries;
    private readonly PublicTrustPulseService _trustPulse;
    private readonly SignedInTrustStatusService _signedInTrustStatus;
    private readonly SupportCaseService _supportCases;
    private readonly SupportCasePresentationService _supportPresentation;
    private readonly InstallBootstrapTicketService _installBootstrapTickets;
    private readonly ReleaseUploadTicketService _releaseUploadTickets;
    private readonly IWebHostEnvironment _webHostEnvironment;
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
        PublicCreatorPublicationDiscoveryService publicCreatorDiscovery,
        HubPageChromeService chrome,
        PublicTrustContentService trustContent,
        PublicPrivacyBoundaryService privacyBoundaries,
        PublicTrustPulseService trustPulse,
        SignedInTrustStatusService signedInTrustStatus,
        SupportCaseService supportCases,
        SupportCasePresentationService supportPresentation,
        InstallBootstrapTicketService installBootstrapTickets,
        ReleaseUploadTicketService releaseUploadTickets,
        IWebHostEnvironment webHostEnvironment,
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
        _publicCreatorDiscovery = publicCreatorDiscovery;
        _chrome = chrome;
        _trustContent = trustContent;
        _privacyBoundaries = privacyBoundaries;
        _trustPulse = trustPulse;
        _signedInTrustStatus = signedInTrustStatus;
        _supportCases = supportCases;
        _supportPresentation = supportPresentation;
        _installBootstrapTickets = installBootstrapTickets;
        _releaseUploadTickets = releaseUploadTickets;
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
            CampaignSpine: await BuildLandingCampaignSpineAsync(cancellationToken));
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
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
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
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var authenticated = await TryIsAuthenticatedAsync(cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        var chrome = await BuildPublicOrAuthenticatedChromeAsync("Downloads", "Install the current preview, compare package types, and keep release integrity in view.", "/downloads", cancellationToken);
        chrome = RebindDownloadsHeaderActions(chrome, releaseExperience);
        var model = new DownloadsPageViewModel(
            Chrome: chrome,
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            Manifest: manifest,
            ReleaseExperience: releaseExperience,
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
        return View("~/Views/PublicLanding/Downloads.cshtml", model);
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
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var ticket = _releaseUploadTickets.Issue(subject);
            var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated: true);
            string bootstrapUrl = BuildAbsoluteUrl(
                "/downloads/release-upload/bootstrap.sh",
                QueryString.Create("ticket", ticket.Ticket));
            string command = $"bash <(curl -fsSL {SingleQuoteShellValue(bootstrapUrl)})";
            var model = new ReleaseUploadPageViewModel(
                Chrome: _chrome.BuildAuthenticatedChrome(
                    "Release upload handoff",
                    "Mint a short-lived upload ticket and hand a zero-touch bootstrap command to the Mac or Windows release runner.",
                    currentPath,
                    user.DisplayName),
                Heading: "Signed-in release upload handoff",
                Summary: "This page mints a short-lived upload ticket, bakes it into the bootstrap command, and lets the release runner promote the artifact directly onto the live downloads shelf without a manual server copy step.",
                Command: command,
                BootstrapUrl: bootstrapUrl,
                TicketExpiresAtUtc: ticket.Claims.ExpiresAtUtc,
                UploadUrl: BuildAbsoluteUrl("/api/internal/releases/bundles"),
                ReadmeUrl: BuildAbsoluteUrl("/artifacts/mac-codex-release-pipeline/readme.md"),
                VerifyUrl: BuildAbsoluteUrl("/downloads/releases.json"),
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
    [Produces("text/plain")]
    public IActionResult ReleaseUploadBootstrapScript([FromQuery] string? ticket)
    {
        if (!_releaseUploadTickets.TryValidate(ticket, out _))
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "release upload ticket is missing, expired, or invalid.");
        }

        string webRoot = _webHostEnvironment.WebRootPath
            ?? Path.Combine(AppContext.BaseDirectory, "wwwroot");
        string templatePath = Path.Combine(webRoot, "artifacts", "mac-codex-release-pipeline", "bootstrap.sh");
        if (!System.IO.File.Exists(templatePath))
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "release upload bootstrap template is unavailable.");
        }

        string rendered = RenderReleaseUploadBootstrapScript(System.IO.File.ReadAllText(templatePath), ticket!);
        return Content(rendered, "text/x-shellscript; charset=utf-8", Encoding.UTF8);
    }

    [HttpGet("/downloads/install/{artifactId}")]
    [Produces("text/html")]
    public async Task<IActionResult> DownloadDispatchPage([FromRoute] string artifactId, CancellationToken cancellationToken)
    {
        var (manifest, artifact) = ResolveInstallDispatchArtifact(artifactId);
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
            var bootstrapScriptDownload = _releaseSelection.UsesGuidedBootstrapScript(artifact);
            var bootstrapPlatform = bootstrapScriptDownload ? ResolveGuidedBootstrapPlatform(artifact) : null;
            var guidedBootstrapArtifacts = bootstrapScriptDownload
                ? ResolveGuidedBootstrapArtifacts(manifest, artifact)
                : Array.Empty<PublicReleaseArtifactDto>();
            var bootstrapTicket = bootstrapScriptDownload
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
                ? BuildBootstrapScriptPath(artifact.Id, bootstrapPlatform)
                : null;
            var bootstrapScriptHref = bootstrapScriptPath is null
                ? null
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
            var terminalInstallCommand = bootstrapScriptDownload && bootstrapTicket is not null
                ? BuildBootstrapInstallCommand(
                    bootstrapPlatform,
                    BuildAbsoluteUrl(
                        BuildBootstrapScriptPath(artifact.Id, bootstrapPlatform!),
                        QueryString.Create("ticket", bootstrapTicket.Ticket)))
                : null;
            var model = new DownloadDispatchPageViewModel(
                Chrome: _chrome.BuildAuthenticatedChrome("Download handoff", "Start the installer download and keep the install linked to this account from the first launch.", "/downloads", user.DisplayName),
                Heading: release.SignedInDispatchHeading,
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
                BootstrapFeatureCards: BuildBootstrapFeatureCards(bootstrapPlatform),
                AutoStartDownload: !bootstrapScriptDownload,
                BootstrapScriptDownload: bootstrapScriptDownload,
                SecondaryDownloadHref: bootstrapScriptDownload ? rawDownloadHref : null,
                SecondaryDownloadLabel: bootstrapScriptDownload ? BuildBootstrapSecondaryDownloadLabel(bootstrapPlatform) : null,
                AccountHref: "/account/access",
                AccountLabel: "Open Devices and access",
                HelpHref: release.InstallHelpHref,
                HelpLabel: release.InstallHelpLabel,
                Display: release.Display,
                Channel: manifest.Channel,
                Version: manifest.Version,
                CurrentReleaseSummary: bootstrapScriptDownload
                    ? BuildBootstrapCurrentReleaseSummary(bootstrapPlatform, guidedBootstrapArtifacts)
                    : option.PlatformLabel,
                PlatformLabel: option.PlatformLabel,
                HeadLabel: option.HeadLabel,
                ClaimCode: bootstrapScriptDownload ? null : dispatch.ClaimTicket?.ClaimCode,
                ClaimCodeExpiresAtUtc: bootstrapScriptDownload ? null : dispatch.ClaimTicket?.ExpiresAtUtc,
                Steps: steps,
                TrustPulse: BuildPublicTrustPulsePanel(manifest, release),
                SignedInStatus: _signedInTrustStatus.Build(user, manifest, release));
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

    [HttpGet("/downloads/install/{artifactId}/bootstrap.command")]
    [Produces("text/plain")]
    public async Task<IActionResult> DownloadDispatchBootstrapScript([FromRoute] string artifactId, CancellationToken cancellationToken)
    {
        var (context, failure) = await TryBuildGuidedBootstrapContextAsync(artifactId, "macos", cancellationToken);
        if (failure is not null)
        {
            return failure;
        }

        var scriptArtifacts = context!.Artifacts
            .Select(candidate => new MacInstallBootstrapArtifact(
                ArtifactId: candidate.ArtifactId,
                HeadId: candidate.HeadId,
                Title: candidate.Title,
                ShortLabel: candidate.ShortLabel,
                DownloadUrl: candidate.DownloadUrl,
                ClaimUrl: candidate.ClaimUrl,
                Sha256: candidate.Sha256,
                DmgName: candidate.PackageName,
                Architecture: candidate.Architecture,
                LaunchAfterInstall: candidate.LaunchAfterInstall))
            .ToArray();

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

    [HttpGet("/downloads/install/{artifactId}/bootstrap.ps1")]
    [Produces("text/plain")]
    public async Task<IActionResult> DownloadDispatchWindowsBootstrapScript([FromRoute] string artifactId, CancellationToken cancellationToken)
    {
        var (context, failure) = await TryBuildGuidedBootstrapContextAsync(artifactId, "windows", cancellationToken);
        if (failure is not null)
        {
            return failure;
        }

        string script = RenderWindowsInstallBootstrapScript(
            context!.Artifacts,
            BuildAbsoluteUrl("/"),
            BuildAbsoluteUrl("/account/access"),
            BuildAbsoluteUrl("/downloads"),
            BuildAbsoluteUrl("/help"));

        Response.Headers["Cache-Control"] = "private, no-store";
        return File(
            Encoding.UTF8.GetBytes(script),
            "text/plain; charset=utf-8",
            BuildWindowsBootstrapFileName(context.Artifact));
    }

    [HttpGet("/downloads/install/{artifactId}/bootstrap.sh")]
    [Produces("text/plain")]
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
    [Produces("application/json")]
    public IActionResult DownloadDispatchBootstrapClaim([FromRoute] string artifactId)
    {
        var (manifest, artifact) = ResolveInstallDispatchArtifact(artifactId);
        if (artifact is null)
        {
            return NotFound();
        }

        if (!_releaseSelection.UsesGuidedBootstrapScript(artifact))
        {
            return NotFound();
        }

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

        var dispatch = _installLinking.IssueDownload(manifest, artifact, ticketClaims.UserId, ticketClaims.SubjectId);
        if (dispatch.ClaimTicket is null || string.IsNullOrWhiteSpace(dispatch.ClaimTicket.ClaimCode))
        {
            Response.Headers["Cache-Control"] = "private, no-store";
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "install claim code is unavailable for this artifact.");
        }

        Response.Headers["Cache-Control"] = "private, no-store";
        return Ok(new
        {
            artifactId = artifact.Id,
            claimCode = dispatch.ClaimTicket.ClaimCode,
            expiresAtUtc = dispatch.ClaimTicket.ExpiresAtUtc,
            status = "pass"
        });
    }

    [HttpGet("/participate")]
    [Produces("text/html")]
    public async Task<IActionResult> ParticipatePage(CancellationToken cancellationToken)
    {
        var surface = _landing.LoadSurface();
        var cards = _landing.CardsForBucket(surface, "participate");
        var chrome = await BuildPublicOrAuthenticatedChromeAsync("Participate", "Two clean lanes: public feedback and an optional signed-in guided contribution path.", "/participate", cancellationToken);
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), chrome.Authenticated);
        var model = new ParticipatePageViewModel(
            Chrome: chrome,
            Surface: surface,
            Assets: new AssetCatalogViewModel(surface.Assets),
            PublicLane: ResolveCards(cards.Where(card => !string.Equals(card.Id, "participate_booster", StringComparison.Ordinal) && !string.Equals(card.Id, "participate_beta", StringComparison.Ordinal)).ToArray(), new AssetCatalogViewModel(surface.Assets), authenticated: false, "/participate"),
            SignedInLane: ResolveCards(cards.Where(card => string.Equals(card.Id, "participate_booster", StringComparison.Ordinal) || string.Equals(card.Id, "participate_beta", StringComparison.Ordinal)).ToArray(), new AssetCatalogViewModel(surface.Assets), authenticated: chrome.Authenticated, "/participate"),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
        return View("~/Views/PublicLanding/Participate.cshtml", model);
    }

    [HttpGet("/status")]
    [Produces("text/html")]
    public async Task<IActionResult> StatusPage(CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var authenticated = await TryIsAuthenticatedAsync(cancellationToken);
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        var model = new StatusPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync("Status", "Weekly pulse, release posture, and the current longest pole on one calmer route.", "/status", cancellationToken),
            Manifest: manifest,
            ReleaseExperience: releaseExperience,
            CampaignOsProof: _campaignOsProof.LoadProof(),
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
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
        IReadOnlyList<CreatorPublicationProjection> publicCreatorPublications = _publicCreatorDiscovery.ListDiscoverable();
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
            Items: ResolveCards(_landing.CardsForBucket(surface, "featured_artifacts"), assetCatalog, authenticated: false, "/artifacts"),
            PublicCreatorPublications: publicCreatorPublications,
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken),
            SignedInRecapShelf: signedInRecapShelf,
            SignedInCreatorPublications: signedInCreatorPublications,
            SignedInArtifactView: signedInArtifactView);
        return View("~/Views/PublicLanding/Shelf.cshtml", model);
    }

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
        var model = new PublicCreatorPublicationPageViewModel(
            Chrome: await BuildPublicOrAuthenticatedChromeAsync(publication.Title, publication.Summary, currentPath, cancellationToken),
            Publication: publication,
            BackHref: "/artifacts#governed-creator-discovery",
            TrustPulse: BuildPublicTrustPulsePanel(manifest, releaseExperience),
            SignedInStatus: await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken));
        return View("~/Views/PublicLanding/PublicCreatorPublication.cshtml", model);
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
        return View(
            "~/Views/PublicLanding/Faq.cshtml",
            _trustContent.BuildFaqPage(chrome) with
            {
                TrustPulse = BuildPublicTrustPulsePanel(manifest, releaseExperience),
                SignedInStatus = await BuildSignedInTrustStatusPanelAsync(manifest, releaseExperience, cancellationToken)
            });
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

        var chrome = await BuildPublicOrAuthenticatedChromeAsync("Support case submitted", "What happens next after a first-party support report reaches Chummer.", $"/contact/submitted/{caseId}", cancellationToken);
        var subject = await TryGetOptionalSubjectAsync(cancellationToken);
        var authenticated = subject is not null;
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated);
        var user = subject is null
            ? null
            : _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        var trackedCase = subject is null
            ? null
            : _supportCases.GetForReporter(caseId, user!.UserId, subject.SubjectId);
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
            TrackedCaseSummary: trackedCase is null ? null : _supportPresentation.Build(trackedCase),
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
            var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
            var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated: true);
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

        if (pulse.ClosureHealthWaitingCount is int closureWaitingCount
            && pulse.ClosureHealthPendingHumanResponseCount is int pendingHumanResponseCount)
        {
            microProof.Add($"{closureWaitingCount} waiting closure / {pendingHumanResponseCount} pending human response");
        }

        var rows = new List<PublicTrustPulseRowViewModel>
        {
            new("Recommended now", BuildTrustPulseRecommendedSummary(manifest, releaseExperience)),
            new("Who can get it now", BuildTrustPulseAccessSummary(releaseExperience)),
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
            : "Guest-readable handoff is live on the current shelf, and Signed-in handoff keeps the install linked once you want account-aware follow-through.";
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

    private static SiteChromeViewModel RebindDownloadsHeaderActions(SiteChromeViewModel chrome, ReleaseExperienceViewModel releaseExperience)
    {
        if (chrome.Authenticated || releaseExperience.Recommended?.RequiresAccount != true)
        {
            return chrome;
        }

        var reboundActions = chrome.HeaderActions
            .Select(action =>
            {
                if (string.Equals(action.Label, "Sign in", StringComparison.OrdinalIgnoreCase))
                {
                    return action with
                    {
                        Href = releaseExperience.GuestGateSecondaryHref,
                        Current = false
                    };
                }

                if (string.Equals(action.Label, "Get preview build", StringComparison.OrdinalIgnoreCase))
                {
                    return action with
                    {
                        Href = releaseExperience.GuestGatePrimaryHref,
                        Current = false
                    };
                }

                return action;
            })
            .ToArray();

        return chrome with { HeaderActions = reboundActions };
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

        if (IsWindowsBootstrapArtifact(artifact))
        {
            return "windows";
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
            "windows" => $"/downloads/install/{Uri.EscapeDataString(artifactId)}/bootstrap.ps1",
            "linux" => $"/downloads/install/{Uri.EscapeDataString(artifactId)}/bootstrap.sh",
            _ => throw new InvalidOperationException($"unsupported bootstrap platform '{platform}'.")
        };

    private static string? BuildBootstrapCommandLabel(string? platform)
        => platform switch
        {
            "macos" => "Mac install command",
            "windows" => "Windows install command",
            "linux" => "Linux install command",
            _ => null
        };

    private static string? BuildBootstrapCommandIntro(string? platform)
        => platform switch
        {
            "macos" => "Paste this into Terminal.",
            "windows" => "Paste this into PowerShell.",
            "linux" => "Paste this into your shell.",
            _ => null
        };

    private static string? BuildBootstrapCommandNote(string? platform)
        => platform switch
        {
            "macos" => "It streams the short-lived setup assistant directly into bash. The assistant asks which Chummer apps to install, where to put them, whether quick access should stay in the Applications folder or add Desktop links, whether to open them when it finishes, and then shows live progress while it downloads, verifies, installs, and links the selected apps.",
            "windows" => "It streams a short-lived PowerShell setup assistant. The assistant asks which Chummer apps to install, where to put them, whether quick access should stay in the Start menu or add Desktop links, whether to open them when it finishes, and then shows live progress while it downloads, verifies, installs, and links the selected apps.",
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
            "windows" =>
            [
                new("Choose your setup", "Pick the Windows desktop builds to install before any installers are run."),
                new("Choose where it lands", "Install into your local Chummer programs folder or a folder you pick without changing the published installers."),
                new("Choose your quick access", "Keep Chummer in the Start menu only or let setup add Desktop shortcuts for the apps you picked."),
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
            "windows" => "Download setup script fallback",
            "linux" => "Download setup script fallback",
            _ => "Download setup script fallback"
        };

    private static string? BuildBootstrapSecondaryDownloadLabel(string? platform)
        => platform switch
        {
            "macos" => "Download raw DMG instead",
            "windows" => "Download raw installer instead",
            "linux" => "Download raw package instead",
            _ => null
        };

    private static string BuildBootstrapDispatchSummary(string? platform)
        => platform switch
        {
            "windows" => "Paste the PowerShell install command below. It streams a short-lived Windows setup assistant, asks which Chummer apps to install and where to put them, then downloads, verifies, installs, and links the selected apps to this account.",
            "linux" => "Paste the shell install command below. It streams a short-lived Linux setup assistant, asks which Chummer apps to install and where to put them, then downloads, verifies, installs, and links the selected apps to this account.",
            _ => "Paste the Terminal install command below. It streams the short-lived Mac setup assistant directly into bash, asks which Chummer apps to install and where to put them, then downloads, verifies, installs, and links the selected apps to this account."
        };

    private static string BuildBootstrapDispatchNote(string? platform)
        => platform switch
        {
            "windows" => "The PowerShell command keeps the published Windows installers unchanged while streaming a short-lived guided setup assistant that can attach the install relationship to this account from the first launch.",
            "linux" => "The shell command keeps the published Debian packages unchanged while streaming a short-lived guided setup assistant that can attach the install relationship to this account from the first launch.",
            _ => "macOS can quarantine a downloaded unsigned .command and label it as damaged. The Terminal command avoids that by streaming the same short-lived setup assistant directly into bash while keeping the published DMGs unchanged."
        };

    private static IReadOnlyList<string> BuildBootstrapSteps(string? platform)
        => platform switch
        {
            "windows" =>
            [
                "Copy the PowerShell install command below and paste it into PowerShell.",
                "The Windows setup assistant offers Auto select for the matching desktop builds on this PC, lets you switch to manual selection when you want different heads, asks where to install them, whether quick access should stay in the Start menu or add Desktop links, whether to open Chummer when it finishes, and then verifies that linking actually completed.",
                "PowerShell then shows staged progress while it downloads the selected installers, verifies their published SHA-256 digests, installs the selected apps, and preserves rollback-safe installer behavior.",
                "Each selected app is started once through a short-lived environment handoff so it is already linked to this account the next time you open it."
            ],
            "linux" =>
            [
                "Copy the shell install command below and paste it into your shell.",
                "The Linux setup assistant offers Auto select for the matching desktop builds on this machine, lets you switch to manual selection when you want different heads, asks whether to use a user-local root or a system root, whether quick access should stay in the applications menu or add Desktop links, whether to open Chummer when it finishes, and then verifies that linking actually completed.",
                "The shell then shows staged progress while it downloads the selected packages, verifies their published SHA-256 digests, unpacks them into the selected root, and writes the launchers and desktop entries without mutating the published .deb files.",
                "Each selected app is started once through a short-lived environment handoff so it is already linked to this account the next time you open it."
            ],
            _ =>
            [
                "Copy the Terminal install command below and paste it into Terminal.",
                "The Mac setup assistant offers Auto select for the matching Apple Silicon or Intel builds on this Mac, lets you switch to manual selection when you want different heads, asks whether to use /Applications or ~/Applications, whether to leave quick access in Applications only or add Desktop links, whether to open Chummer when it finishes, and then verifies that linking actually completed.",
                "Terminal then shows staged progress while it downloads the selected DMGs, verifies their published SHA-256 digests, mounts them, and installs the app bundles with a staged swap instead of a delete-first replace.",
                "Each selected app is started once through a short-lived environment handoff so it is already linked to this account the next time you open it."
            ]
        };

    private static string BuildMacBootstrapFileName(PublicReleaseArtifactDto artifact)
    {
        return "Chummer Setup.command";
    }

    private static string BuildWindowsBootstrapFileName(PublicReleaseArtifactDto artifact)
    {
        return "Chummer Setup.ps1";
    }

    private static string BuildLinuxBootstrapFileName(PublicReleaseArtifactDto artifact)
    {
        return "chummer-setup.sh";
    }

    internal static string BuildBootstrapInstallCommand(string? platform, string bootstrapUrl)
        => platform switch
        {
            "windows" => $"powershell -NoProfile -ExecutionPolicy Bypass -Command \"Set-StrictMode -Version Latest; $ProgressPreference='SilentlyContinue'; iex ((Invoke-WebRequest -UseBasicParsing {SingleQuoteShellValue(bootstrapUrl)}).Content)\"",
            "linux" => BuildMacBootstrapTerminalCommand(bootstrapUrl),
            _ => BuildMacBootstrapTerminalCommand(bootstrapUrl)
        };

    internal static string BuildMacBootstrapTerminalCommand(string bootstrapUrl)
        => $"set -o pipefail; curl -fsSL {SingleQuoteShellValue(bootstrapUrl)} | /bin/bash";

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
            "windows" => BuildWindowsBootstrapCurrentReleaseSummary(artifacts),
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
        builder.AppendLine("CLAIM_ENDPOINTS=(");
        foreach (var artifact in artifacts)
        {
            builder.Append("  '").Append(SingleQuoteShellLiteral(artifact.ClaimUrl)).AppendLine("'");
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
        builder.AppendLine("fetch_install_claim_code() {");
        builder.AppendLine("  local claim_url=\"$1\"");
        builder.AppendLine("  local response_path=\"$WORK_ROOT/claim-$RANDOM.json\"");
        builder.AppendLine("  local http_code claim_code claim_error");
        builder.AppendLine("  http_code=\"$(curl --silent --show-error --location --output \"$response_path\" --write-out '%{http_code}' \"$claim_url\")\" || {");
        builder.AppendLine("    rm -f \"$response_path\"");
        builder.AppendLine("    return 1");
        builder.AppendLine("  }");
        builder.AppendLine("  if [[ \"$http_code\" != \"200\" ]]; then");
        builder.AppendLine("    claim_error=\"$(/usr/bin/plutil -extract message raw -o - \"$response_path\" 2>/dev/null || true)\"");
        builder.AppendLine("    if [[ -n \"$claim_error\" ]]; then");
        builder.AppendLine("      echo \"$claim_error\" >&2");
        builder.AppendLine("    fi");
        builder.AppendLine("    rm -f \"$response_path\"");
        builder.AppendLine("    return 1");
        builder.AppendLine("  fi");
        builder.AppendLine("  claim_code=\"$(/usr/bin/plutil -extract claimCode raw -o - \"$response_path\" 2>/dev/null || true)\"");
        builder.AppendLine("  rm -f \"$response_path\"");
        builder.AppendLine("  [[ -n \"$claim_code\" ]] || return 1");
        builder.AppendLine("  printf '%s' \"$claim_code\"");
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
        builder.AppendLine("  local download_url=\"${DOWNLOAD_URLS[$idx]}\"");
        builder.AppendLine("  local expected_sha256=\"${SHA256_DIGESTS[$idx]}\"");
        builder.AppendLine("  local dmg_name=\"${DMG_NAMES[$idx]}\"");
        builder.AppendLine("  local stage_root=\"$WORK_ROOT/$idx\"");
        builder.AppendLine("  local mount_point=\"$stage_root/mount\"");
        builder.AppendLine("  local dmg_path=\"$DOWNLOAD_DIR/$dmg_name\"");
        builder.AppendLine("  mkdir -p \"$stage_root\" \"$mount_point\"");
        builder.AppendLine("  MOUNT_POINTS+=(\"$mount_point\")");
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
        builder.AppendLine("  local claim_endpoint=\"${CLAIM_ENDPOINTS[$artifact_idx]}\"");
        builder.AppendLine("  local claim_code");
        builder.AppendLine("  local head_id=\"${HEAD_IDS[$artifact_idx]}\"");
        builder.AppendLine("  local artifact_arch=\"${ARTIFACT_ARCHES[$artifact_idx]}\"");
        builder.AppendLine("  local artifact_title=\"${ARTIFACT_TITLES[$artifact_idx]}\"");
        builder.AppendLine("  local state_path");
        builder.AppendLine("  local launch_pid");
        builder.AppendLine("  local claim_message claim_error claim_status");
        builder.AppendLine("  state_path=\"$(build_install_state_path \"$head_id\" \"$artifact_arch\")\"");
        builder.AppendLine("  advance_progress \"Linking $artifact_title to this account\"");
        builder.AppendLine("  echo \"Linking $artifact_title to this account...\"");
        builder.AppendLine("  claim_code=\"$(fetch_install_claim_code \"$claim_endpoint\")\" || {");
        builder.AppendLine("    INSTALL_WARNINGS+=(\"$artifact_title could not fetch a short-lived install claim from the downloads handoff. Re-open the current Mac install command from $DOWNLOADS_URL and run it again.\")");
        builder.AppendLine("    return 0");
        builder.AppendLine("  }");
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
                        $"/downloads/install/{Uri.EscapeDataString(candidate.Id)}/claim.json",
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

        return (new GuidedBootstrapScriptContext(artifact, scriptArtifacts, effectiveBootstrapTicket), null);
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

    private static bool IsWindowsBootstrapArtifact(PublicReleaseArtifactDto artifact)
    {
        string platformToken = $"{artifact.PlatformId} {artifact.Platform} {artifact.Url}";
        return (platformToken.Contains("win", StringComparison.OrdinalIgnoreCase)
                || ((artifact.FileName ?? string.Empty).EndsWith(".exe", StringComparison.OrdinalIgnoreCase)))
               && (artifact.Url.EndsWith(".exe", StringComparison.OrdinalIgnoreCase)
                   || (artifact.FileName ?? string.Empty).EndsWith(".exe", StringComparison.OrdinalIgnoreCase));
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

    private static string BuildWindowsBootstrapCurrentReleaseSummary(IReadOnlyList<PublicReleaseArtifactDto> artifacts)
    {
        if (artifacts.Count == 0)
        {
            return "Windows desktop setup handoff";
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
                    _ => string.IsNullOrWhiteSpace(artifact.Arch) ? "Windows" : artifact.Arch
                })
                .Distinct(StringComparer.OrdinalIgnoreCase));

        return string.IsNullOrWhiteSpace(arches)
            ? $"Windows desktop setup handoff, {heads}"
            : $"Windows desktop setup handoff, {heads}, {arches}";
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
            "blazor-desktop" when string.Equals(ResolveGuidedBootstrapPlatform(artifact), "windows", StringComparison.OrdinalIgnoreCase) => "Chummer.Blazor.Desktop.exe",
            "blazor-desktop" => "Chummer.Blazor.Desktop",
            _ when string.Equals(ResolveGuidedBootstrapPlatform(artifact), "windows", StringComparison.OrdinalIgnoreCase) => "Chummer.Avalonia.exe",
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
            "windows" => BuildWindowsBootstrapArtifactTitle(artifact),
            "linux" => BuildLinuxBootstrapArtifactTitle(artifact),
            _ => BuildMacBootstrapArtifactTitle(artifact)
        };

    private static string BuildGuidedBootstrapShortLabel(PublicReleaseArtifactDto artifact)
        => ResolveGuidedBootstrapPlatform(artifact) switch
        {
            "windows" => BuildWindowsBootstrapShortLabel(artifact),
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

    private static string BuildWindowsBootstrapArtifactTitle(PublicReleaseArtifactDto artifact)
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
            _ => "Windows"
        };

        return $"{headLabel} Windows {archLabel} Installer";
    }

    private static string BuildWindowsBootstrapShortLabel(PublicReleaseArtifactDto artifact)
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

    internal static string RenderWindowsInstallBootstrapScript(
        IReadOnlyList<GuidedBootstrapArtifact> artifacts,
        string publicBaseUrl,
        string accountUrl,
        string downloadsUrl,
        string helpUrl)
    {
        ArgumentNullException.ThrowIfNull(artifacts);
        if (artifacts.Count == 0)
        {
            throw new ArgumentException("at least one Windows bootstrap artifact is required.", nameof(artifacts));
        }

        string artifactsJson = JsonSerializer.Serialize(artifacts);
        string template = """
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$PublicBaseUrl = '__PUBLIC_BASE_URL__'
$AccountUrl = '__ACCOUNT_URL__'
$DownloadsUrl = '__DOWNLOADS_URL__'
$HelpUrl = '__HELP_URL__'
$Artifacts = @'
__ARTIFACTS_JSON__
'@ | ConvertFrom-Json

try {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $GuiAvailable = $true
}
catch {
    $GuiAvailable = $false
}

function Write-Banner {
    Write-Host '============================================================'
    Write-Host ' Chummer Setup'
    Write-Host ' Guided Windows install for the current desktop preview'
    Write-Host '============================================================'
    Write-Host ''
}

function Write-Step([int]$Step, [int]$Total, [string]$Message) {
    $percent = [Math]::Min([Math]::Round(($Step / [double]$Total) * 100), 100)
    Write-Progress -Activity 'Chummer Setup' -Status $Message -PercentComplete $percent
    Write-Host ''
    Write-Host ('[' + ('#' * [Math]::Max([int][Math]::Round($percent / 4), 1)).PadRight(25, '.') + "] $Step/$Total $Message")
}

function Read-ConsoleChoice([string]$Prompt, [string[]]$Choices, [int]$DefaultIndex) {
    Write-Host $Prompt
    for ($i = 0; $i -lt $Choices.Length; $i++) {
        $marker = if ($i -eq $DefaultIndex) { '*' } else { ' ' }
        Write-Host ("  [{0}] {1} {2}" -f ($i + 1), $marker, $Choices[$i])
    }

    while ($true) {
        $raw = Read-Host ("Choose 1-{0} (blank = {1})" -f $Choices.Length, ($DefaultIndex + 1))
        if ([string]::IsNullOrWhiteSpace($raw)) {
            return $Choices[$DefaultIndex]
        }

        $selectedIndex = 0
        if ([int]::TryParse($raw, [ref]$selectedIndex) -and $selectedIndex -ge 1 -and $selectedIndex -le $Choices.Length) {
            return $Choices[$selectedIndex - 1]
        }
    }
}

function Show-ButtonDialog([string]$Title, [string]$Message, [string[]]$Buttons, [string]$DefaultButton) {
    if (-not $GuiAvailable) {
        $defaultIndex = [Array]::IndexOf($Buttons, $DefaultButton)
        if ($defaultIndex -lt 0) { $defaultIndex = 0 }
        return Read-ConsoleChoice $Message $Buttons $defaultIndex
    }

    $form = New-Object System.Windows.Forms.Form
    $form.Text = $Title
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MinimizeBox = $false
    $form.MaximizeBox = $false
    $form.TopMost = $true
    $form.ClientSize = New-Object System.Drawing.Size(620, 210)

    $label = New-Object System.Windows.Forms.Label
    $label.AutoSize = $false
    $label.Text = $Message
    $label.Left = 18
    $label.Top = 18
    $label.Width = 584
    $label.Height = 110
    $label.MaximumSize = New-Object System.Drawing.Size(584, 0)

    $buttonsPanel = New-Object System.Windows.Forms.FlowLayoutPanel
    $buttonsPanel.Left = 18
    $buttonsPanel.Top = 142
    $buttonsPanel.Width = 584
    $buttonsPanel.Height = 46
    $buttonsPanel.FlowDirection = 'RightToLeft'

    foreach ($choice in $Buttons) {
        $button = New-Object System.Windows.Forms.Button
        $button.Text = $choice
        $button.AutoSize = $true
        $button.Add_Click({
            $form.Tag = $this.Text
            $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
            $form.Close()
        })
        if ($choice -eq $DefaultButton) {
            $form.AcceptButton = $button
        }
        [void]$buttonsPanel.Controls.Add($button)
    }

    [void]$form.Controls.Add($label)
    [void]$form.Controls.Add($buttonsPanel)
    [void]$form.ShowDialog()
    if ($null -eq $form.Tag) {
        throw 'Chummer Setup was cancelled.'
    }

    return [string]$form.Tag
}

function Show-ChecklistDialog([string]$Title, [string]$Message, [object[]]$Items, [string[]]$DefaultIds) {
    if (-not $GuiAvailable) {
        Write-Host $Message
        for ($i = 0; $i -lt $Items.Count; $i++) {
            $item = $Items[$i]
            $selected = if ($DefaultIds -contains $item.ArtifactId) { '*' } else { ' ' }
            Write-Host ("  [{0}] {1} {2}" -f ($i + 1), $selected, $item.ShortLabel)
        }

        $raw = Read-Host 'Enter comma-separated numbers (blank keeps Auto select defaults)'
        if ([string]::IsNullOrWhiteSpace($raw)) {
            return $DefaultIds
        }

        $selectedIds = New-Object System.Collections.Generic.List[string]
        foreach ($token in ($raw -split ',')) {
            $value = $token.Trim()
            if (-not [string]::IsNullOrWhiteSpace($value)) {
                $index = 0
                if ([int]::TryParse($value, [ref]$index) -and $index -ge 1 -and $index -le $Items.Count) {
                    [void]$selectedIds.Add([string]$Items[$index - 1].ArtifactId)
                }
            }
        }

        if ($selectedIds.Count -eq 0) {
            throw 'Choose at least one Chummer app.'
        }

        return $selectedIds.ToArray()
    }

    $form = New-Object System.Windows.Forms.Form
    $form.Text = $Title
    $form.StartPosition = 'CenterScreen'
    $form.FormBorderStyle = 'FixedDialog'
    $form.MinimizeBox = $false
    $form.MaximizeBox = $false
    $form.TopMost = $true
    $form.ClientSize = New-Object System.Drawing.Size(620, 420)

    $label = New-Object System.Windows.Forms.Label
    $label.AutoSize = $false
    $label.Text = $Message
    $label.Left = 18
    $label.Top = 18
    $label.Width = 584
    $label.Height = 72

    $checkList = New-Object System.Windows.Forms.CheckedListBox
    $checkList.Left = 18
    $checkList.Top = 96
    $checkList.Width = 584
    $checkList.Height = 250
    foreach ($item in $Items) {
        $index = $checkList.Items.Add([string]$item.ShortLabel)
        if ($DefaultIds -contains [string]$item.ArtifactId) {
            $checkList.SetItemChecked($index, $true)
        }
    }

    $buttonsPanel = New-Object System.Windows.Forms.FlowLayoutPanel
    $buttonsPanel.Left = 18
    $buttonsPanel.Top = 360
    $buttonsPanel.Width = 584
    $buttonsPanel.Height = 44
    $buttonsPanel.FlowDirection = 'RightToLeft'

    $okButton = New-Object System.Windows.Forms.Button
    $okButton.Text = 'Continue'
    $okButton.AutoSize = $true
    $okButton.Add_Click({
        if ($checkList.CheckedIndices.Count -eq 0) {
            [System.Windows.Forms.MessageBox]::Show('Choose at least one Chummer app.', 'Chummer Setup', [System.Windows.Forms.MessageBoxButtons]::OK, [System.Windows.Forms.MessageBoxIcon]::Warning) | Out-Null
            return
        }

        $selected = New-Object System.Collections.Generic.List[string]
        foreach ($index in $checkList.CheckedIndices) {
            [void]$selected.Add([string]$Items[[int]$index].ArtifactId)
        }

        $form.Tag = $selected.ToArray()
        $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
        $form.Close()
    })

    $cancelButton = New-Object System.Windows.Forms.Button
    $cancelButton.Text = 'Cancel'
    $cancelButton.AutoSize = $true
    $cancelButton.Add_Click({
        $form.Close()
    })

    [void]$buttonsPanel.Controls.Add($okButton)
    [void]$buttonsPanel.Controls.Add($cancelButton)
    [void]$form.Controls.Add($label)
    [void]$form.Controls.Add($checkList)
    [void]$form.Controls.Add($buttonsPanel)
    [void]$form.ShowDialog()

    if ($null -eq $form.Tag) {
        throw 'Chummer Setup was cancelled.'
    }

    return [string[]]$form.Tag
}

function Show-FolderDialog([string]$Description, [string]$SelectedPath) {
    if (-not $GuiAvailable) {
        $raw = Read-Host ($Description + " (blank keeps " + $SelectedPath + ")")
        if ([string]::IsNullOrWhiteSpace($raw)) {
            return $SelectedPath
        }

        return $raw
    }

    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = $Description
    $dialog.SelectedPath = $SelectedPath
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        return $SelectedPath
    }

    return $dialog.SelectedPath
}

function Get-HostArchitecture {
    $arch = ($env:PROCESSOR_ARCHITECTURE ?? '').Trim().ToUpperInvariant()
    if ($arch.Contains('ARM64')) {
        return 'arm64'
    }

    return 'x64'
}

function Get-HostArchitectureLabel([string]$Arch) {
    switch ($Arch) {
        'arm64' { return 'ARM64' }
        default { return 'x64' }
    }
}

function Get-DefaultArtifacts([object[]]$ArtifactSet, [string]$HostArch) {
    $matching = @($ArtifactSet | Where-Object { $_.Architecture -eq $HostArch })
    if ($matching.Count -gt 0) {
        return $matching
    }

    return @($ArtifactSet | Sort-Object @{ Expression = { if ($_.LaunchAfterInstall) { 0 } else { 1 } } }, ShortLabel)
}

function Resolve-SelectedArtifacts {
    $hostArch = Get-HostArchitecture
    $defaultArtifacts = @(Get-DefaultArtifacts $Artifacts $hostArch)
    $defaultIds = @($defaultArtifacts | ForEach-Object { [string]$_.ArtifactId })
    $defaultSummary = (($defaultArtifacts | ForEach-Object { [string]$_.ShortLabel }) -join [Environment]::NewLine)
    $message = "Auto select the matching $(Get-HostArchitectureLabel $hostArch) builds for this PC, or choose manually?`n`nAuto select:`n$defaultSummary"
    $mode = Show-ButtonDialog 'Chummer Setup' $message @('Choose manually', 'Auto select') 'Auto select'
    if ($mode -eq 'Auto select') {
        return $defaultArtifacts
    }

    $selectedIds = @(Show-ChecklistDialog 'Chummer Setup' 'Choose which Chummer desktop apps to install now.' $Artifacts $defaultIds)
    return @($Artifacts | Where-Object { $selectedIds -contains [string]$_.ArtifactId })
}

function Resolve-InstallRoot {
    $defaultRoot = Join-Path $env:LOCALAPPDATA 'Programs\Chummer6'
    $choice = Show-ButtonDialog 'Chummer Setup' "Choose where to install the selected apps.`n`nRecommended keeps them under:`n$defaultRoot" @('Choose folder', 'Recommended') 'Recommended'
    if ($choice -eq 'Choose folder') {
        return Show-FolderDialog 'Choose the folder that should hold the installed Chummer app folders.' $defaultRoot
    }

    return $defaultRoot
}

function Resolve-ShortcutMode {
    $choice = Show-ButtonDialog 'Chummer Setup' 'Where should Chummer leave quick access after setup?' @('Start menu only', 'Desktop links', 'Both') 'Start menu only'
    switch ($choice) {
        'Desktop links' { return 'desktop' }
        'Both' { return 'both' }
        default { return 'start' }
    }
}

function Resolve-OpenAfterInstall {
    $choice = Show-ButtonDialog 'Chummer Setup' 'After Chummer finishes installing, should it open the selected app when setup is done?' @('Finish closed', 'Open when done') 'Open when done'
    return $choice -eq 'Open when done'
}

function Ensure-Directory([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Download-Artifact([object]$Artifact, [string]$DownloadRoot) {
    Ensure-Directory $DownloadRoot
    $targetPath = Join-Path $DownloadRoot ([string]$Artifact.PackageName)
    Write-Host ("Downloading {0} to {1}" -f $Artifact.Title, $targetPath)
    Invoke-WebRequest -UseBasicParsing -Uri ([string]$Artifact.DownloadUrl) -OutFile $targetPath
    return $targetPath
}

function Verify-ArtifactHash([string]$DownloadedPath, [object]$Artifact) {
    if ([string]::IsNullOrWhiteSpace([string]$Artifact.Sha256)) {
        return
    }

    $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $DownloadedPath).Hash.ToLowerInvariant()
    $expected = ([string]$Artifact.Sha256).Trim().ToLowerInvariant()
    if ($actual -ne $expected) {
        throw ("SHA-256 mismatch for {0}. Expected {1} but saw {2}." -f $Artifact.Title, $expected, $actual)
    }
}

function Invoke-Installer([string]$InstallerPath, [string]$TargetDir, [string]$ShortcutMode) {
    $startMenu = if ($ShortcutMode -eq 'desktop') { 'off' } else { 'on' }
    $desktop = if ($ShortcutMode -eq 'start') { 'off' } else { 'on' }
    $arguments = @(
        '--bootstrap-install', $TargetDir,
        '--start-menu-shortcut', $startMenu,
        '--desktop-shortcut', $desktop,
        '--launch', 'off'
    )
    $process = Start-Process -FilePath $InstallerPath -ArgumentList $arguments -Wait -PassThru
    if ($process.ExitCode -ne 0) {
        throw ("Installer exited with code {0} for {1}" -f $process.ExitCode, $InstallerPath)
    }
}

function Get-StatePath([object]$Artifact) {
    $stateRoot = Join-Path $env:LOCALAPPDATA 'Chummer6\install-linking'
    return Join-Path $stateRoot ([IO.Path]::Combine([string]$Artifact.HeadId, 'windows', [string]$Artifact.Architecture, 'state.json'))
}

function Read-State([string]$StatePath) {
    if (-not (Test-Path -LiteralPath $StatePath)) {
        return $null
    }

    try {
        return (Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json)
    }
    catch {
        return $null
    }
}

function Get-StateField([string]$StatePath, [string]$FieldName) {
    $state = Read-State $StatePath
    if ($null -eq $state) {
        return $null
    }

    $property = $state.PSObject.Properties[$FieldName]
    if ($null -eq $property) {
        return $null
    }

    return [string]$property.Value
}

function Wait-ForClaimSuccess([string]$StatePath, [int]$TimeoutSeconds) {
    for ($i = 0; $i -lt $TimeoutSeconds; $i++) {
        $state = Read-State $StatePath
        if ($null -ne $state -and [string]$state.status -eq 'claimed' -and $state.grantToken -and $state.claimedAtUtc) {
            return $true
        }

        Start-Sleep -Seconds 1
    }

    return $false
}

function Resolve-InstalledExecutable([string]$InstallDir, [object]$Artifact) {
    return Join-Path $InstallDir ([string]$Artifact.ExecutableName)
}

function Get-InstallClaimCode([object]$Artifact) {
    $response = Invoke-WebRequest -UseBasicParsing -Uri ([string]$Artifact.ClaimUrl)
    $payload = $response.Content | ConvertFrom-Json
    $claimCode = [string]$payload.claimCode
    if ([string]::IsNullOrWhiteSpace($claimCode)) {
        throw ("Install claim exchange did not return a usable claim code for {0}" -f $Artifact.Title)
    }

    return $claimCode
}

function Start-ClaimLaunch([string]$ExecutablePath, [object]$Artifact) {
    $claimCode = Get-InstallClaimCode $Artifact
    $previousClaimCode = $env:CHUMMER_INSTALL_CLAIM_CODE
    $previousApiBase = $env:CHUMMER_API_BASE_URL
    $previousWebBase = $env:CHUMMER_WEB_BASE_URL
    try {
        $env:CHUMMER_INSTALL_CLAIM_CODE = $claimCode
        $env:CHUMMER_API_BASE_URL = $PublicBaseUrl
        $env:CHUMMER_WEB_BASE_URL = $PublicBaseUrl
        return Start-Process -FilePath $ExecutablePath -WorkingDirectory (Split-Path -Parent $ExecutablePath) -PassThru
    }
    finally {
        $env:CHUMMER_INSTALL_CLAIM_CODE = $previousClaimCode
        $env:CHUMMER_API_BASE_URL = $previousApiBase
        $env:CHUMMER_WEB_BASE_URL = $previousWebBase
    }
}

Write-Banner
Write-Step 1 6 'Preparing the guided Windows install'
$selectedArtifacts = @(Resolve-SelectedArtifacts)
if ($selectedArtifacts.Count -eq 0) {
    throw 'Choose at least one Chummer app.'
}

$hostArch = Get-HostArchitecture
$installRoot = Resolve-InstallRoot
$shortcutMode = Resolve-ShortcutMode
$openAfterInstall = Resolve-OpenAfterInstall

Write-Host 'Selected apps:'
foreach ($artifact in $selectedArtifacts) {
    Write-Host (" - {0}" -f $artifact.ShortLabel)
}
Write-Host ("Install destination: {0}" -f $installRoot)
Write-Host ("Current PC architecture: {0}" -f (Get-HostArchitectureLabel $hostArch))
Write-Host ("Quick access: {0}" -f $(switch ($shortcutMode) { 'desktop' { 'Desktop links' } 'both' { 'Start menu + Desktop links' } default { 'Start menu only' } }))
Write-Host ("Finish behavior: {0}" -f $(if ($openAfterInstall) { 'open the selected apps when installation completes' } else { 'finish without opening the selected apps' }))

$downloadRoot = Join-Path $env:TEMP ("chummer-setup-" + [Guid]::NewGuid().ToString('N'))
$installedArtifacts = New-Object System.Collections.Generic.List[object]
$installWarnings = New-Object System.Collections.Generic.List[string]
$linkedConfirmed = 0

foreach ($artifact in $selectedArtifacts) {
    Write-Step 2 6 ("Downloading " + $artifact.Title)
    $downloadedInstaller = Download-Artifact $artifact $downloadRoot
    Verify-ArtifactHash $downloadedInstaller $artifact

    $targetDir = Join-Path $installRoot ([string]$artifact.InstallFolderName)
    Write-Step 3 6 ("Installing " + $artifact.Title)
    Write-Host ("Installing {0} to {1}" -f $artifact.Title, $targetDir)
    Invoke-Installer $downloadedInstaller $targetDir $shortcutMode

    $installedArtifacts.Add([pscustomobject]@{
        Artifact = $artifact
        InstallDir = $targetDir
        ExecutablePath = (Resolve-InstalledExecutable $targetDir $artifact)
    }) | Out-Null
}

Write-Host ''
Write-Host 'Installed Windows desktop builds:'
foreach ($installed in $installedArtifacts) {
    Write-Host (" - {0}" -f $installed.InstallDir)
}
Write-Host 'Running a first-launch link check for the selected installs...'

foreach ($installed in $installedArtifacts) {
    $artifact = $installed.Artifact
    Write-Step 4 6 ("Linking " + $artifact.Title + " to this account")
    $statePath = Get-StatePath $artifact
    $claimProcess = Start-ClaimLaunch $installed.ExecutablePath $artifact
    if (Wait-ForClaimSuccess $statePath 25) {
        $linkedConfirmed += 1
        $message = Get-StateField $statePath 'lastClaimMessage'
        if ([string]::IsNullOrWhiteSpace($message)) {
            Write-Host ($artifact.Title + ' linked successfully.')
        }
        else {
            Write-Host ($artifact.Title + ': ' + $message)
        }
    }
    else {
        $claimError = Get-StateField $statePath 'lastClaimError'
        $claimStatus = Get-StateField $statePath 'status'
        if (-not [string]::IsNullOrWhiteSpace($claimError)) {
            $installWarnings.Add("$($artifact.Title) could not confirm account linking automatically: $claimError Re-run the current Windows install command or open the app manually once if Devices and access does not show it yet.") | Out-Null
        }
        elseif (-not [string]::IsNullOrWhiteSpace($claimStatus)) {
            $installWarnings.Add("$($artifact.Title) finished first-launch work with status '$claimStatus' instead of a confirmed linked state. Re-run the current Windows install command or open the app manually once if Devices and access does not show it yet.") | Out-Null
        }
        else {
            $installWarnings.Add("$($artifact.Title) did not write a confirmed install-link receipt yet. Re-run the current Windows install command or open the app manually once if Devices and access does not show it yet.") | Out-Null
        }
    }

    if ($openAfterInstall -and [bool]$artifact.LaunchAfterInstall) {
        continue
    }

    if ($claimProcess -and -not $claimProcess.HasExited) {
        Stop-Process -Id $claimProcess.Id -Force -ErrorAction SilentlyContinue
        Wait-Process -Id $claimProcess.Id -ErrorAction SilentlyContinue
    }
}

Write-Step 5 6 'Finishing Chummer Setup'
Write-Host ''
Write-Host ("Confirmed linked installs: {0} / {1}" -f $linkedConfirmed, $installedArtifacts.Count)
if ($linkedConfirmed -eq $installedArtifacts.Count) {
    Write-Host 'The selected Chummer app or apps were installed and linked to this account.'
    Write-Host 'When you open them again later, they should already be linked to this account.'
}
else {
    Write-Host 'The selected Chummer app or apps were installed, but setup could not confirm linking for every app yet.'
    Write-Host 'If Devices and access does not show them, rerun the current install command or open the app manually once.'
}

if ($installWarnings.Count -gt 0) {
    Write-Host ''
    Write-Host 'Setup notes:'
    foreach ($warning in $installWarnings) {
        Write-Host (" - {0}" -f $warning)
    }
}

Write-Host ("Devices and access: {0}" -f $AccountUrl)
Write-Host ("Downloads shelf: {0}" -f $DownloadsUrl)
Write-Host ("Help: {0}" -f $HelpUrl)
Write-Step 6 6 'Done'
""";

        return template
            .Replace("__PUBLIC_BASE_URL__", EscapePowerShellSingleQuoted(publicBaseUrl), StringComparison.Ordinal)
            .Replace("__ACCOUNT_URL__", EscapePowerShellSingleQuoted(accountUrl), StringComparison.Ordinal)
            .Replace("__DOWNLOADS_URL__", EscapePowerShellSingleQuoted(downloadsUrl), StringComparison.Ordinal)
            .Replace("__HELP_URL__", EscapePowerShellSingleQuoted(helpUrl), StringComparison.Ordinal)
            .Replace("__ARTIFACTS_JSON__", artifactsJson, StringComparison.Ordinal);
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
  mkdir -p "$(dirname "$desktop_path")"
  cat >"$desktop_path" <<ENTRY
[Desktop Entry]
Type=Application
Name=$app_name
Exec=$exec_path
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
Terminal=false
Categories=Game;
ENTRY
chmod 755 "${desktop_entry_target}"
SCRIPT
    run_privileged_script "$shortcuts_script"
  else
    write_wrapper_script "$launcher_target" "${target_dir}/${executable_name}"
    write_desktop_entry "$desktop_entry_target" "${SHORT_LABELS[$idx]}" "$launcher_target"
  fi

  if [[ "$shortcut_mode" == "desktop" || "$shortcut_mode" == "both" ]]; then
    create_desktop_link "$desktop_entry_target" "${SHORT_LABELS[$idx]}"
  fi

  INSTALLED_PATHS+=("${target_dir}")
  INSTALLED_ARTIFACT_INDEXES+=("$idx")
}

launch_installed_app() {
  local installed_idx="$1"
  local artifact_idx="${INSTALLED_ARTIFACT_INDEXES[$installed_idx]}"
  local target_dir="${INSTALLED_PATHS[$installed_idx]}"
  local executable_path="${target_dir}/${EXECUTABLE_NAMES[$artifact_idx]}"
  local claim_url="${CLAIM_URLS[$artifact_idx]}"
  local claim_code
  local head_id="${HEAD_IDS[$artifact_idx]}"
  local artifact_arch="${ARTIFACT_ARCHES[$artifact_idx]}"
  local artifact_title="${ARTIFACT_TITLES[$artifact_idx]}"
  local state_path launch_pid claim_error claim_status claim_message

  state_path="$(build_install_state_path "$head_id" "$artifact_arch")"
  advance_progress "Linking ${artifact_title} to this account"
  echo "Linking ${artifact_title} to this account..."
  claim_code="$(fetch_install_claim_code "$claim_url")" || {
    INSTALL_WARNINGS+=("${artifact_title} could not fetch a short-lived install claim from the downloads handoff. Re-run the current Linux install command from ${DOWNLOADS_URL} and try again.")
    return 0
  }
  env CHUMMER_INSTALL_CLAIM_CODE="$claim_code" CHUMMER_API_BASE_URL="$PUBLIC_BASE_URL" CHUMMER_WEB_BASE_URL="$PUBLIC_BASE_URL" "$executable_path" >/dev/null 2>&1 &
  launch_pid="$!"

  if wait_for_claim_success "$state_path" 25; then
    LINKED_CONFIRMED_COUNT=$((LINKED_CONFIRMED_COUNT + 1))
    claim_message="$(read_install_state_field "$state_path" lastClaimMessage || true)"
    if [[ -n "$claim_message" ]]; then
      echo "${artifact_title}: ${claim_message}"
    else
      echo "${artifact_title} linked successfully."
    fi
  else
    claim_error="$(read_install_state_field "$state_path" lastClaimError || true)"
    claim_status="$(read_install_state_field "$state_path" status || true)"
    if [[ -n "$claim_error" ]]; then
      INSTALL_WARNINGS+=("${artifact_title} could not confirm account linking automatically: ${claim_error} Re-run the current Linux install command or open the app manually once if Devices and access does not show it yet.")
    elif [[ -n "$claim_status" ]]; then
      INSTALL_WARNINGS+=("${artifact_title} finished first-launch work with status '${claim_status}' instead of a confirmed linked state. Re-run the current Linux install command or open the app manually once if Devices and access does not show it yet.")
    else
      INSTALL_WARNINGS+=("${artifact_title} did not write a confirmed install-link receipt yet. Re-run the current Linux install command or open the app manually once if Devices and access does not show it yet.")
    fi
  fi

  if [[ "$OPEN_SELECTED_AFTER_INSTALL" == "1" && "${LAUNCH_AFTER_INSTALL[$artifact_idx]}" == "1" ]]; then
    :
  else
    sleep 2
    kill "$launch_pid" >/dev/null 2>&1 || true
    wait "$launch_pid" >/dev/null 2>&1 || true
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
echo "Running a first-launch link check for the selected installs..."
for install_idx in "${!INSTALLED_PATHS[@]}"; do
  launch_installed_app "$install_idx"
done

advance_progress "Finishing Chummer Setup"
echo
echo "Confirmed linked installs: ${LINKED_CONFIRMED_COUNT} / ${#INSTALLED_PATHS[@]}"
if [[ "${LINKED_CONFIRMED_COUNT}" -eq "${#INSTALLED_PATHS[@]}" ]]; then
  echo "The selected Chummer app or apps were installed and linked to this account."
  echo "When you open them again later, they should already be linked to this account."
else
  echo "The selected Chummer app or apps were installed, but setup could not confirm linking for every app yet."
  echo "If Devices and access does not show them, rerun the current install command or open the app manually once."
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

    private static string EscapePowerShellSingleQuoted(string value)
        => value.Replace("'", "''", StringComparison.Ordinal);

    private static string RenderReleaseUploadBootstrapScript(string template, string ticket)
    {
        string scriptBody = template.StartsWith("#!/usr/bin/env bash", StringComparison.Ordinal)
            ? template["#!/usr/bin/env bash".Length..].TrimStart('\r', '\n')
            : template;
        StringBuilder builder = new();
        builder.AppendLine("#!/usr/bin/env bash");
        builder.Append("export CHUMMER_RELEASE_UPLOAD_TOKEN='")
            .Append(SingleQuoteShellLiteral(ticket))
            .AppendLine("'");
        builder.AppendLine("export CHUMMER_RELEASE_UPLOAD_URL=\"https://chummer.run/api/internal/releases/bundles\"");
        builder.AppendLine(scriptBody);
        return builder.ToString();
    }

    private static string SingleQuoteShellValue(string value)
        => $"'{SingleQuoteShellLiteral(value)}'";

    private static string SingleQuoteShellLiteral(string value)
        => value.Replace("'", "'\"'\"'", StringComparison.Ordinal);

    internal sealed record MacInstallBootstrapArtifact(
        string ArtifactId,
        string HeadId,
        string Title,
        string ShortLabel,
        string DownloadUrl,
        string ClaimUrl,
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
        PublicReleaseArtifactDto Artifact,
        IReadOnlyList<GuidedBootstrapArtifact> Artifacts,
        string BootstrapTicket);
}
