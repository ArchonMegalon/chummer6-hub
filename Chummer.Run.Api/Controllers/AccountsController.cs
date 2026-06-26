using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.KarmaForge;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.ViewModels;
using Chummer.Campaign.Contracts;
using Chummer.Control.Contracts.Support;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Ledger;
using Chummer.Run.Contracts.Billing;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[AutoValidateAntiforgeryToken]
[Route("api/v1/accounts")]
public sealed class AccountsController : Controller
{
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;
    private readonly IdentityLinkService _links;
    private readonly UserExperienceService _experience;
    private readonly ParticipationOperatorNotificationService _participationNotifications;
    private readonly InstallLinkingService _installLinking;
    private readonly AccountDesktopLaunchTicketService _desktopLaunchTickets;
    private readonly SupportCaseService _supportCases;
    private readonly SupportCasePresentationService _supportPresentation;
    private readonly CampaignSpineService _campaignSpine;
    private readonly CampaignWorkspaceServerPlaneService _workspaceServerPlane;
    private readonly CreatorPublicationRegistryBridge _creatorPublicationRegistry;
    private readonly BoostSessionService _sessions;
    private readonly LeaderboardService _leaderboards;
    private readonly PublicPackageCatalogService _packageCatalog;
    private readonly KarmaForgeDiscoveryService _karmaForge;
    private readonly BuildGhostConciergeService _buildGhostConcierge;
    private readonly HubPageChromeService _chrome;
    private readonly HubGoogleAuthService _google;
    private readonly PublicReleaseManifestService _releases;
    private readonly ReleaseSelectionService _releaseSelection;
    private readonly PublicPrivacyBoundaryService _privacyBoundaries;
    private readonly SignedInTrustStatusService _signedInTrustStatus;
    private readonly OriginDossierPublicationService _originDossierPublications;
    private readonly BrilliantDirectoriesBillingService? _billing;
    private readonly MediaArtifactHorizonsService? _mediaHorizons;
    private readonly HorizonArtifactRequestService? _artifactRequests;
    private readonly ILogger<AccountsController> _logger;

    public AccountsController(
        AccountService accounts,
        HubIdentityClient identity,
        IdentityLinkService links,
        UserExperienceService experience,
        ParticipationOperatorNotificationService participationNotifications,
        InstallLinkingService installLinking,
        AccountDesktopLaunchTicketService desktopLaunchTickets,
        SupportCaseService supportCases,
        SupportCasePresentationService supportPresentation,
        CampaignSpineService campaignSpine,
        CampaignWorkspaceServerPlaneService workspaceServerPlane,
        CreatorPublicationRegistryBridge creatorPublicationRegistry,
        BoostSessionService sessions,
        LeaderboardService leaderboards,
        PublicPackageCatalogService packageCatalog,
        KarmaForgeDiscoveryService karmaForge,
        BuildGhostConciergeService buildGhostConcierge,
        HubPageChromeService chrome,
        HubGoogleAuthService google,
        PublicReleaseManifestService releases,
        ReleaseSelectionService releaseSelection,
        PublicPrivacyBoundaryService privacyBoundaries,
        SignedInTrustStatusService signedInTrustStatus,
        OriginDossierPublicationService originDossierPublications,
        BrilliantDirectoriesBillingService? billing,
        ILogger<AccountsController> logger,
        HorizonArtifactRequestService? artifactRequests = null,
        MediaArtifactHorizonsService? mediaHorizons = null)
    {
        _accounts = accounts;
        _identity = identity;
        _links = links;
        _experience = experience;
        _participationNotifications = participationNotifications;
        _installLinking = installLinking;
        _desktopLaunchTickets = desktopLaunchTickets;
        _supportCases = supportCases;
        _supportPresentation = supportPresentation;
        _campaignSpine = campaignSpine;
        _workspaceServerPlane = workspaceServerPlane;
        _creatorPublicationRegistry = creatorPublicationRegistry;
        _sessions = sessions;
        _leaderboards = leaderboards;
        _packageCatalog = packageCatalog;
        _karmaForge = karmaForge;
        _buildGhostConcierge = buildGhostConcierge;
        _chrome = chrome;
        _google = google;
        _releases = releases;
        _releaseSelection = releaseSelection;
        _privacyBoundaries = privacyBoundaries;
        _signedInTrustStatus = signedInTrustStatus;
        _originDossierPublications = originDossierPublications;
        _billing = billing;
        _artifactRequests = artifactRequests;
        _mediaHorizons = mediaHorizons;
        _logger = logger;
    }

    [HttpGet("/account")]
    [HttpGet("/account/{section}")]
    [HttpGet("/account/support/{caseId}")]
    [HttpGet("/account/work/workspaces/{workspaceId}")]
    [HttpGet("/account/work/runs/{runId}")]
    [HttpGet("/account/work/build-handoffs/{handoffId}")]
    [HttpGet("/account/work/rules/{entryId}")]
    [HttpGet("/account/work/publications/{publicationId}")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountPage(
        [FromRoute] string? section,
        [FromRoute] string? caseId,
        CancellationToken cancellationToken,
        [FromRoute] string? workspaceId = null,
        [FromRoute] string? runId = null,
        [FromRoute] string? handoffId = null,
        [FromRoute] string? entryId = null,
        [FromRoute] string? publicationId = null,
        [FromQuery] string? prepQuery = null)
    {
        bool showHub = string.IsNullOrWhiteSpace(section)
                       && string.IsNullOrWhiteSpace(caseId)
                       && !HasWorkSelection(workspaceId, runId, handoffId, entryId, publicationId);

        if (!showHub && IsBillingSectionAlias(section))
        {
            return Redirect("/account/billing");
        }

        var selectedSection = showHub
            ? "profile"
            : !string.IsNullOrWhiteSpace(caseId)
            ? "support"
            : HasWorkSelection(workspaceId, runId, handoffId, entryId, publicationId)
                ? "work"
                : NormalizeAccountSection(section);
        if (string.Equals(selectedSection, "profile", StringComparison.OrdinalIgnoreCase))
        {
            if (!showHub)
            {
                return Redirect("/account");
            }
        }

        var currentPath = showHub
            ? "/account"
            : BuildAccountCurrentPath(selectedSection, caseId, workspaceId, runId, handoffId, entryId, publicationId);
        var (chromeTitle, chromeDescription) = DescribeAccountSection(selectedSection);

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var links = _links.GetSummary(subject.SubjectId);
            HubUserExperienceDto experience = _experience.GetOrCreate(subject.SubjectId);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var supportCases = _supportCases.ListForReporter(user.UserId, subject.SubjectId).Items;
            var supportCaseSummaries = _supportPresentation.BuildList(supportCases, installLinking);
            var selectedSupportCase = string.IsNullOrWhiteSpace(caseId)
                ? null
                : _supportCases.GetForReporter(caseId, user.UserId, subject.SubjectId);
            var selectedSupportCaseSummary = selectedSupportCase is null ? null : _supportPresentation.Build(selectedSupportCase, installLinking);
            var campaignSpine = _campaignSpine.GetAccountSummary(user, installLinking);
            var originDossierPublications = _originDossierPublications.ListForAccount(user.UserId, subject.SubjectId);
            EntitlementSyncReceiptProjection entitlementSyncReceipts = _workspaceServerPlane.GetEntitlementSyncReceiptProjection(user, installLinking);
            var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
            var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated: true);
            var selectedWorkspace = FindById(campaignSpine.Workspaces, workspaceId, static item => item.WorkspaceId);
            if (selectedWorkspace is not null && !string.IsNullOrWhiteSpace(prepQuery))
            {
                experience = _experience.RecordWorkspacePrepLibrarySearch(subject.SubjectId, selectedWorkspace.WorkspaceId, prepQuery);
            }
            var selectedWorkspaceServerPlane = selectedWorkspace is null
                ? null
                : _workspaceServerPlane.GetWorkspaceServerPlane(user, selectedWorkspace.WorkspaceId, installLinking);
            var selectedWorkspaceRosterTransferPlan = selectedWorkspace is null
                ? null
                : _campaignSpine.GetRosterTransferPlan(user, selectedWorkspace.WorkspaceId, installLinking);
            var selectedWorkspacePrepLibrarySearch = selectedWorkspace is null || string.IsNullOrWhiteSpace(prepQuery)
                ? null
                : _workspaceServerPlane.GetWorkspacePrepLibrary(user, selectedWorkspace.WorkspaceId, installLinking, prepQuery);
            var selectedRun = FindById(campaignSpine.Runs, runId, static item => item.RunId);
            var selectedBuildLabHandoff = FindById(campaignSpine.BuildLabHandoffs, handoffId, static item => item.HandoffId);
            var selectedRulesNavigatorAnswer = FindById(campaignSpine.RulesNavigator, entryId, static item => item.EntryId);
            var selectedCreatorPublication = FindById(campaignSpine.CreatorPublications, publicationId, static item => item.PublicationId);
            var selectedCreatorPublicationWorkspace = selectedCreatorPublication is null
                ? null
                : campaignSpine.Workspaces.FirstOrDefault(item => string.Equals(item.CampaignId, selectedCreatorPublication.CampaignId, StringComparison.OrdinalIgnoreCase));
            var selectedCreatorPublicationRegistry = selectedCreatorPublication is null
                ? null
                : _creatorPublicationRegistry.GetOrCreatePublicationLane(user, selectedCreatorPublication, selectedCreatorPublicationWorkspace);
            var participationSession = _sessions.FindMostRelevantForUser(subject.SubjectId);
            IReadOnlyList<ContributionReceiptDto> participationReceipts = participationSession is null
                ? Array.Empty<ContributionReceiptDto>()
                : _sessions.ListReceipts(participationSession.SponsorSessionId);
            if (showHub)
            {
                return View(
                    "~/Views/Accounts/Hub.cshtml",
                    BuildAccountHubModel(user, installLinking, supportCases, campaignSpine));
            }

            var model = new AccountPageViewModel(
                Chrome: _chrome.BuildAuthenticatedChrome(chromeTitle, chromeDescription, currentPath, user.DisplayName, user.Email),
                CurrentSection: selectedSection,
                CoreSections: BuildAccountCoreSections(selectedSection),
                SecondarySections: BuildAccountSecondarySections(selectedSection),
                User: user,
                Links: links,
                Experience: experience,
                GoogleAvailable: _google.IsConfigured(),
                InstallLinking: installLinking,
                SupportCases: supportCases,
                SupportCaseSummaries: supportCaseSummaries,
                SelectedSupportCase: selectedSupportCase,
                SelectedSupportCaseSummary: selectedSupportCaseSummary,
                CampaignSpine: campaignSpine,
                EntitlementSyncReceipts: entitlementSyncReceipts,
                SelectedWorkspace: selectedWorkspace,
                SelectedWorkspaceServerPlane: selectedWorkspaceServerPlane,
                SelectedWorkspaceRosterTransferPlan: selectedWorkspaceRosterTransferPlan,
                SelectedWorkspacePrepLibrarySearch: selectedWorkspacePrepLibrarySearch,
                SelectedWorkspacePrepLibraryQuery: prepQuery,
                SelectedRun: selectedRun,
                SelectedBuildLabHandoff: selectedBuildLabHandoff,
                SelectedBuildLabInsights: selectedBuildLabHandoff is null
                    ? Array.Empty<BuildGhostConciergeInsightProjection>()
                    : _buildGhostConcierge.BuildChartBrickInsightsForHandoff(selectedBuildLabHandoff.HandoffId, selectedBuildLabHandoff.Title),
                SelectedRulesNavigatorAnswer: selectedRulesNavigatorAnswer,
                SelectedCreatorPublication: selectedCreatorPublication,
                SelectedCreatorPublicationDraftDetail: selectedCreatorPublicationRegistry?.DraftDetail,
                SelectedCreatorPublicationReceipt: selectedCreatorPublicationRegistry?.PublicationReceipt,
                SignedInTrustStatus: _signedInTrustStatus.Build(user, manifest, releaseExperience),
                PrivacyBoundary: _privacyBoundaries.BuildPanel("account"),
                ParticipationRecognition: _leaderboards.UserRecognitionSummary(user.UserId),
                ParticipationSession: participationSession,
                ParticipationReceipts: participationReceipts,
                ParticipationPackageReceipts: _packageCatalog.ListReceiptsForSubject(subject.SubjectId, 8),
                ParticipationKarmaSubmissions: _karmaForge.ListRecentForSubject(subject.SubjectId, 5),
                ParticipationActivityReceipts: _participationNotifications.ListReceiptsForUser(user.UserId, 6),
                OriginDossierPublications: originDossierPublications);
            return View("~/Views/Accounts/Account.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Account page could not confirm the signed-in identity.");
            return View("~/Views/Auth/Message.cshtml", new AuthMessagePageViewModel(
                Chrome: _chrome.BuildPublicChrome("Account unavailable", "Hub could not confirm the account page right now.", currentPath),
                Heading: "Account is unavailable right now",
                SupportLine: "Chummer could not open the account page right now. Your account details were not changed.",
                Notice: null,
                PrimaryLabel: "Try account again",
                PrimaryHref: currentPath,
                SecondaryLabel: "Return home",
                SecondaryHref: "/home"));
        }
    }

    private AccountHubPageViewModel BuildAccountHubModel(
        HubUserDto user,
        InstallLinkingSummaryDto installLinking,
        IReadOnlyList<SupportCaseProjection> supportCases,
        AccountCampaignSummary campaignSpine)
    {
        int linkedInstallCount = installLinking.ClaimedInstallations?.Count ?? 0;
        int pendingClaimCount = installLinking.PendingClaimTickets.Count;
        bool hasLinkedInstall = linkedInstallCount > 0;
        MyFirstBookQuotaSnapshotDto? quota = null;
        if (_billing is not null)
        {
            try
            {
                quota = _billing.GetMyFirstBookQuota(user.UserId, email: user.Email);
            }
            catch (BrilliantDirectoriesBillingUnavailableException)
            {
                quota = null;
            }
        }

        string membershipLabel = quota?.PlanName ?? "Free";
        string membershipSummary = quota is null
            ? "Supporter handoff is not configured yet."
            : quota.SupporterActive
                ? "Supporter only changes the monthly Origin Book allowance."
                : "Free and Supporter use the same app.";
        string bookQuotaSummary = quota is null
            ? "Origin book quota shows up here after billing is configured."
            : $"{quota.MonthlyRemaining} of {quota.MonthlyLimit} origin books left this month.";

        string installSummary = hasLinkedInstall
            ? $"{linkedInstallCount} linked install{(linkedInstallCount == 1 ? string.Empty : "s")}."
            : "No linked install yet.";
        if (pendingClaimCount > 0)
        {
            installSummary += $" {pendingClaimCount} claim ticket{(pendingClaimCount == 1 ? string.Empty : "s")} waiting.";
        }

        string supportSummary = supportCases.Count == 0
            ? "No tracked support cases."
            : $"{supportCases.Count} tracked support case{(supportCases.Count == 1 ? string.Empty : "s")}.";
        string campaignSummary = $"{campaignSpine.Dossiers.Count} runner{(campaignSpine.Dossiers.Count == 1 ? string.Empty : "s")}, {campaignSpine.Campaigns.Count} campaign{(campaignSpine.Campaigns.Count == 1 ? string.Empty : "s")}.";

        return new AccountHubPageViewModel(
            Chrome: _chrome.BuildAuthenticatedChrome(
                "Account",
                "Installs, support, membership, and campaign return paths.",
                "/account",
                user.DisplayName,
                user.Email),
            User: user,
            Heading: "Keep installs, support, and membership in one place.",
            Summary: "Use this page for return paths. Character work belongs in Chummer itself.",
            MembershipLabel: membershipLabel,
            MembershipSummary: membershipSummary,
            BookQuotaSummary: bookQuotaSummary,
            Cards:
            [
                new AccountHubCardViewModel(
                    "Installs",
                    "Devices and access",
                    installSummary,
                    hasLinkedInstall ? "Open installs" : "Open downloads",
                    hasLinkedInstall ? "/account/access" : "/downloads",
                    hasLinkedInstall ? "Downloads" : "Devices and access",
                    hasLinkedInstall ? "/downloads" : "/account/access"),
                new AccountHubCardViewModel(
                    "Membership",
                    "Billing",
                    membershipSummary,
                    "Open billing",
                    "/account/billing"),
                new AccountHubCardViewModel(
                    "Support",
                    "Tracked help",
                    supportSummary,
                    "Open support",
                    "/account/support"),
                new AccountHubCardViewModel(
                    "Campaigns",
                    "Characters and groups",
                    campaignSummary,
                    "Open campaigns",
                    "/account/work")
            ]);
    }

    [HttpGet("/account/work/origin-dossiers/{originDossierProjectId}")]
    [Produces("text/html")]
    public async Task<IActionResult> OriginDossierDetailPage(
        [FromRoute] string originDossierProjectId,
        CancellationToken cancellationToken)
    {
        string currentPath = $"/account/work/origin-dossiers/{Uri.EscapeDataString(originDossierProjectId)}";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            OriginDossierPublicationViewModel? publication = _originDossierPublications.GetForAccount(
                user.UserId,
                subject.SubjectId,
                originDossierProjectId);
            if (publication is null)
            {
                Response.StatusCode = StatusCodes.Status404NotFound;
                return View("~/Views/Auth/Message.cshtml", new AuthMessagePageViewModel(
                    Chrome: _chrome.BuildAuthenticatedChrome(
                        "Origin Dossier unavailable",
                        "The requested Origin Dossier is not available for this signed-in account.",
                        currentPath,
                        user.DisplayName,
                        user.Email),
                    Heading: "Origin Dossier is not available",
                    SupportLine: "This account does not have a verified Origin Dossier publication for that project.",
                    Notice: "Open your library to see the dossiers that belong to this account.",
                    PrimaryLabel: "Open Origin Dossier library",
                    PrimaryHref: "/account/work#origin-dossier-library",
                    SecondaryLabel: "Return to account",
                    SecondaryHref: "/account"));
            }

            var model = new OriginDossierPublicationDetailPageViewModel(
                Chrome: _chrome.BuildAuthenticatedChrome(
                    publication.Title,
                    "Private Origin Dossier edition, cover, and audiobook gate.",
                    currentPath,
                    user.DisplayName,
                    user.Email),
                Publication: publication,
                AccountHref: "/account",
                LibraryHref: "/account/work#origin-dossier-library");
            return View("~/Views/Accounts/OriginDossier.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Origin Dossier detail page could not confirm the signed-in identity.");
            return View("~/Views/Auth/Message.cshtml", new AuthMessagePageViewModel(
                Chrome: _chrome.BuildPublicChrome("Origin Dossier unavailable", "Hub could not confirm this Origin Dossier right now.", currentPath),
                Heading: "Origin Dossier is unavailable right now",
                SupportLine: "Chummer could not open this private Origin Dossier right now. The dossier and account were not changed.",
                Notice: null,
                PrimaryLabel: "Try account again",
                PrimaryHref: "/account/work#origin-dossier-library",
                SecondaryLabel: "Return home",
                SecondaryHref: "/home"));
        }
    }

    [HttpGet("/account/work/origin-dossiers/{originDossierProjectId}/{artifactKind}")]
    public async Task<IActionResult> OriginDossierArtifact(
        [FromRoute] string originDossierProjectId,
        [FromRoute] string artifactKind,
        CancellationToken cancellationToken)
    {
        string currentPath = $"/account/work/origin-dossiers/{Uri.EscapeDataString(originDossierProjectId)}/{Uri.EscapeDataString(artifactKind)}";
        if (!string.Equals(artifactKind, "book", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(artifactKind, "read", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(artifactKind, "dossier", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(artifactKind, "cover", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(artifactKind, "video", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(artifactKind, "watch", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(artifactKind, "movie", StringComparison.OrdinalIgnoreCase)
            && !string.Equals(artifactKind, "listen", StringComparison.OrdinalIgnoreCase))
        {
            return NotFound();
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            HorizonArtifactRequestReceipt? receipt = null;
            if (_artifactRequests is not null)
            {
                MediaArtifactSurfaceDefinition surface = _mediaHorizons?.GetSurface("origin-dossier")
                    ?? new("origin-dossier", "origin-dossier-media");
                string normalizedArtifactKind = artifactKind.Trim().ToLowerInvariant();
                string sourceRef = _mediaHorizons?.BuildSourceRef(surface, $"{originDossierProjectId}:{normalizedArtifactKind}")
                    ?? $"{surface.HorizonId}:{originDossierProjectId}:{normalizedArtifactKind}";
                receipt = _artifactRequests.BuildRequest(
                    new HorizonArtifactRequestCreateRequest(
                        HorizonId: surface.HorizonId,
                        ArtifactKindOrCapabilityId: surface.CapabilityId,
                        UserId: subject.SubjectId,
                        SourceRef: sourceRef,
                        Visibility: "private",
                        ExternalProcessingConsent: true,
                        Email: subject.Email),
                    consumeQuota: false,
                    requireEnabledCapability: false);
                if (!string.Equals(receipt.Status, "accepted", StringComparison.OrdinalIgnoreCase))
                {
                    _logger.LogWarning(
                        "Origin Dossier artifact access denied for {UserId} on {ProjectId}/{ArtifactKind}; blocked reasons: {BlockedReasons}.",
                        subject.SubjectId,
                        originDossierProjectId,
                        normalizedArtifactKind,
                        string.Join(", ", receipt.BlockedReasons));
                    return Problem(statusCode: StatusCodes.Status400BadRequest, detail: "Unable to create a Chummer-owned Origin Dossier artifact access receipt.");
                }

                Response.Headers["X-Horizon-Artifact-Request-Id"] = receipt.RequestId;
                Response.Headers["X-Horizon-Artifact-Request-Href"] = $"/api/v1/horizons/artifact-requests/me/{Uri.EscapeDataString(receipt.RequestId)}";
            }

            if (string.Equals(artifactKind, "read", StringComparison.OrdinalIgnoreCase)
                || string.Equals(artifactKind, "dossier", StringComparison.OrdinalIgnoreCase)
                || string.Equals(artifactKind, "listen", StringComparison.OrdinalIgnoreCase))
            {
                string shareKind = string.Equals(artifactKind, "listen", StringComparison.OrdinalIgnoreCase)
                    ? "audiobook"
                    : "dossier";
                string? audiobookshelfShareUrl = _originDossierPublications.GetAudiobookshelfShareForAccount(
                    user.UserId,
                    subject.SubjectId,
                    originDossierProjectId,
                    shareKind);
                return string.IsNullOrWhiteSpace(audiobookshelfShareUrl)
                    ? NotFound()
                    : Redirect(audiobookshelfShareUrl);
            }

            string resolvedArtifactKind = artifactKind.Trim().ToLowerInvariant() switch
            {
                "watch" or "movie" => "video",
                _ => artifactKind
            };
            OriginDossierPublicationArtifact? artifact = _originDossierPublications.GetArtifactForAccount(
                user.UserId,
                subject.SubjectId,
                originDossierProjectId,
                resolvedArtifactKind);
            return artifact is null
                ? NotFound()
                : PhysicalFile(artifact.Path, artifact.ContentType, enableRangeProcessing: true);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Origin Dossier artifact route could not confirm the signed-in identity.");
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("/account/alice/{handoffId}")]
    [Produces("text/html")]
    public async Task<IActionResult> AliceBenchDetailPage(
        [FromRoute] string handoffId,
        CancellationToken cancellationToken)
    {
        string currentPath = $"/account/alice/{Uri.EscapeDataString(handoffId)}";
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }

        return await AccountPage(
            section: "work",
            caseId: null,
            cancellationToken: cancellationToken,
            workspaceId: null,
            runId: null,
            handoffId: handoffId,
            entryId: null,
            publicationId: null,
            prepQuery: null);
    }

    [HttpGet("/account/alice")]
    [Produces("text/html")]
    public async Task<IActionResult> AliceBenchPage(CancellationToken cancellationToken)
    {
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/alice")}");
        }

        return await OpenAliceBench(cancellationToken);
    }

    [HttpGet("/account/alice/open")]
    [Produces("text/html")]
    public async Task<IActionResult> OpenAliceBench(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var leadHandoff = _campaignSpine
                .GetAccountSummary(user, installLinking)
                .BuildLabHandoffs
                .OrderByDescending(item => item.UpdatedAtUtc)
                .FirstOrDefault();

            return Redirect(leadHandoff is null
                ? "/account/work"
                : $"/account/alice/{Uri.EscapeDataString(leadHandoff.HandoffId)}");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/alice/open")}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "ALICE bench could not confirm the signed-in identity.");
            return Redirect("/alice");
        }
    }

    [HttpGet("/account/community")]
    [Produces("text/html")]
    public async Task<IActionResult> CommunityHubPage(CancellationToken cancellationToken)
    {
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/community")}");
        }

        return await OpenCommunityHub(cancellationToken);
    }

    [HttpGet("/account/community/open")]
    [Produces("text/html")]
    public async Task<IActionResult> OpenCommunityHub(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var leadOpenRun = _campaignSpine
                .GetOpenRuns(user, installLinking)
                .OrderByDescending(item => item.UpdatedAtUtc)
                .FirstOrDefault();

            if (leadOpenRun is not null)
            {
                return Redirect($"/account/work/runs/{Uri.EscapeDataString(leadOpenRun.RunId)}#community-ops");
            }

            return Redirect("/account/work#community-ops");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/community/open")}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Community Hub could not confirm the signed-in identity.");
            return Redirect("/community");
        }
    }

    [HttpGet("/account/creator/{publicationId}")]
    [Produces("text/html")]
    public async Task<IActionResult> CreatorPublicationPage(
        [FromRoute] string publicationId,
        CancellationToken cancellationToken)
    {
        string currentPath = $"/account/creator/{Uri.EscapeDataString(publicationId)}";
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }

        return await AccountPage(
            section: "work",
            caseId: null,
            cancellationToken: cancellationToken,
            workspaceId: null,
            runId: null,
            handoffId: null,
            entryId: null,
            publicationId: publicationId,
            prepQuery: null);
    }

    [HttpGet("/account/open/character/{dossierId}")]
    [HttpGet("/account/open/campaign/{campaignId}")]
    [HttpGet("/account/open/group/{groupId}")]
    [HttpGet("/account/open/example/{exampleId}")]
    [Produces("text/html")]
    public async Task<IActionResult> OpenInChummer(
        [FromRoute] string? dossierId,
        [FromRoute] string? campaignId,
        [FromRoute] string? groupId,
        [FromRoute] string? exampleId,
        CancellationToken cancellationToken)
    {
        string currentPath = BuildAccountOpenCurrentPath(dossierId, campaignId, groupId, exampleId);
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            bool hasLinkedDesktop = (installLinking.ClaimedInstallations?.Count ?? 0) > 0
                || (installLinking.ActiveGrants?.Count ?? 0) > 0
                || installLinking.PendingClaimTickets.Count > 0;
            if (!hasLinkedDesktop)
            {
                return Redirect("/downloads");
            }

            string launchKind;
            string resourceId;
            string heading;
            string summary;
            if (!string.IsNullOrWhiteSpace(dossierId))
            {
                launchKind = "character";
                resourceId = dossierId;
                heading = "Open character in Chummer";
                summary = "This account already has a linked desktop copy, so the next step belongs in the app.";
            }
            else if (!string.IsNullOrWhiteSpace(campaignId))
            {
                launchKind = "campaign";
                resourceId = campaignId;
                heading = "Open campaign in Chummer";
                summary = "Return to the desktop app for the real campaign flow instead of staying in the browser.";
            }
            else if (!string.IsNullOrWhiteSpace(groupId))
            {
                launchKind = "group";
                resourceId = groupId;
                heading = "Open group in Chummer";
                summary = "Use the linked desktop copy for the actual group and campaign work.";
            }
            else if (!string.IsNullOrWhiteSpace(exampleId))
            {
                launchKind = "example-character";
                resourceId = exampleId;
                heading = "Open example character in Chummer";
                summary = "Start from an archetype inside the app, then turn it into your own runner.";
            }
            else
            {
                return Redirect("/account/work");
            }

            var ticket = _desktopLaunchTickets.Issue(launchKind, resourceId, user.UserId, subject.SubjectId);
            string launchUri = $"chummer://open?ticket={Uri.EscapeDataString(ticket.Ticket)}&kind={Uri.EscapeDataString(launchKind)}&id={Uri.EscapeDataString(resourceId)}";
            return View("~/Views/Accounts/OpenInChummer.cshtml", new AccountDesktopLaunchPageViewModel(
                Chrome: _chrome.BuildAuthenticatedChrome(heading, summary, currentPath, user.DisplayName, user.Email),
                Heading: heading,
                Summary: summary,
                LaunchUri: launchUri,
                PrimaryLabel: "Open in Chummer",
                PrimaryHref: "/downloads",
                SecondaryLabel: "Open downloads",
                SecondaryHref: "/account/work",
                Notes: new[]
                {
                    "If the app does not answer, use downloads or devices and access instead of repeating the same dead click.",
                    "This browser page is only the launch bridge. The real editing flow stays in the desktop app."
                }));
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
    }

    [HttpGet("/account/creator")]
    [Produces("text/html")]
    public async Task<IActionResult> CreatorOsPage(CancellationToken cancellationToken)
    {
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/creator")}");
        }

        return await OpenCreatorOs(cancellationToken);
    }

    [HttpGet("/account/creator/open")]
    [Produces("text/html")]
    public async Task<IActionResult> OpenCreatorOs(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var leadPublication = _campaignSpine
                .GetAccountSummary(user, installLinking)
                .CreatorPublications
                .OrderByDescending(item => item.UpdatedAtUtc)
                .FirstOrDefault();

            return Redirect(leadPublication is null
                ? "/account/work"
                : $"/account/creator/{Uri.EscapeDataString(leadPublication.PublicationId)}");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/creator/open")}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Creator OS could not confirm the signed-in identity.");
            return Redirect("/creator");
        }
    }

    [HttpGet("/account/jackpoint/{publicationId}")]
    [Produces("text/html")]
    public async Task<IActionResult> JackpointPublicationPage(
        [FromRoute] string publicationId,
        CancellationToken cancellationToken)
    {
        string currentPath = $"/account/jackpoint/{Uri.EscapeDataString(publicationId)}";
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }

        return await AccountPage(
            section: "work",
            caseId: null,
            cancellationToken: cancellationToken,
            workspaceId: null,
            runId: null,
            handoffId: null,
            entryId: null,
            publicationId: publicationId,
            prepQuery: null);
    }

    [HttpGet("/account/jackpoint")]
    [Produces("text/html")]
    public async Task<IActionResult> JackpointDeskPage(CancellationToken cancellationToken)
    {
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/jackpoint")}");
        }

        return await OpenJackpointDesk(cancellationToken);
    }

    [HttpGet("/account/jackpoint/open")]
    [Produces("text/html")]
    public async Task<IActionResult> OpenJackpointDesk(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var leadPublication = _campaignSpine
                .GetAccountSummary(user, installLinking)
                .CreatorPublications
                .OrderByDescending(item => item.UpdatedAtUtc)
                .FirstOrDefault();

            return Redirect(leadPublication is null
                ? "/account/creator"
                : $"/account/jackpoint/{Uri.EscapeDataString(leadPublication.PublicationId)}");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/jackpoint/open")}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "JACKPOINT desk could not confirm the signed-in identity.");
            return Redirect("/jackpoint");
        }
    }

    [HttpGet("/account/runsites/{workspaceId}")]
    [Produces("text/html")]
    public async Task<IActionResult> RunsiteWorkspacePage(
        [FromRoute] string workspaceId,
        CancellationToken cancellationToken)
    {
        string currentPath = $"/account/runsites/{Uri.EscapeDataString(workspaceId)}";
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }

        return await AccountPage(
            section: "work",
            caseId: null,
            cancellationToken: cancellationToken,
            workspaceId: workspaceId,
            runId: null,
            handoffId: null,
            entryId: null,
            publicationId: null,
            prepQuery: null);
    }

    [HttpGet("/account/runsites")]
    [Produces("text/html")]
    public async Task<IActionResult> RunsiteBenchPage(CancellationToken cancellationToken)
    {
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/runsites")}");
        }

        return await OpenRunsiteBench(cancellationToken);
    }

    [HttpGet("/account/runsites/open")]
    [Produces("text/html")]
    public async Task<IActionResult> OpenRunsiteBench(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var leadWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking)
                ?? _campaignSpine.GetAccountSummary(user, installLinking)
                    .Workspaces
                    .FirstOrDefault();

            return Redirect(leadWorkspace is null
                ? "/account/work"
                : $"/account/runsites/{Uri.EscapeDataString(leadWorkspace.WorkspaceId)}");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/runsites/open")}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "RUNSITE bench could not confirm the signed-in identity.");
            return Redirect("/runsites");
        }
    }

    [HttpGet("/account/propertyquarry/{propertyId}")]
    [Produces("text/html")]
    public async Task<IActionResult> PropertyquarryPropertyPage(
        [FromRoute] string propertyId,
        CancellationToken cancellationToken)
    {
        string currentPath = $"/account/propertyquarry/{Uri.EscapeDataString(propertyId)}";
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            MediaArtifactDocument property = GetPropertyquarryPropertyOrThrow(propertyId);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            CampaignWorkspaceProjection? leadWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking)
                ?? _campaignSpine.GetAccountSummary(user, installLinking).Workspaces.FirstOrDefault();
            return Redirect(BuildPropertyquarryPrepSearchAccountHref(property.Label, leadWorkspace?.WorkspaceId));
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
        catch (InvalidOperationException ex)
        {
            _logger.LogWarning(ex, "PROPERTYQUARRY detail route is unavailable because the media horizon catalog is not configured.");
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "PROPERTYQUARRY detail route could not confirm the signed-in identity.");
            return Redirect("/propertyquarry");
        }
    }

    [HttpGet("/account/propertyquarry")]
    [Produces("text/html")]
    public async Task<IActionResult> PropertyquarryDeskPage(CancellationToken cancellationToken)
    {
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/propertyquarry")}");
        }

        return await OpenPropertyquarryDesk(cancellationToken);
    }

    [HttpGet("/account/propertyquarry/open")]
    [Produces("text/html")]
    public async Task<IActionResult> OpenPropertyquarryDesk(CancellationToken cancellationToken)
    {
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
            MediaArtifactDocument? leadProperty = _mediaHorizons?.ListPropertyquarryProperties().FirstOrDefault();
            return Redirect(leadProperty is null
                ? "/account/work"
                : $"/account/propertyquarry/{Uri.EscapeDataString(leadProperty.Id)}");
        }
        catch (InvalidOperationException ex)
        {
            _logger.LogWarning(ex, "PROPERTYQUARRY desk is unavailable because the media horizon catalog is not configured.");
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/propertyquarry/open")}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "PROPERTYQUARRY desk could not confirm the signed-in identity.");
            return Redirect("/propertyquarry");
        }
    }

    [HttpGet("/account/run-control/{runId}")]
    [Produces("text/html")]
    public async Task<IActionResult> RunControlRunPage(
        [FromRoute] string runId,
        CancellationToken cancellationToken)
    {
        string currentPath = $"/account/run-control/{Uri.EscapeDataString(runId)}";
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }

        return await AccountPage(
            section: "work",
            caseId: null,
            cancellationToken: cancellationToken,
            workspaceId: null,
            runId: runId,
            handoffId: null,
            entryId: null,
            publicationId: null,
            prepQuery: null);
    }

    [HttpGet("/account/run-control")]
    [Produces("text/html")]
    public async Task<IActionResult> RunControlDeskPage(CancellationToken cancellationToken)
    {
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/run-control")}");
        }

        return await OpenRunControlDesk(cancellationToken);
    }

    [HttpGet("/account/run-control/open")]
    [Produces("text/html")]
    public async Task<IActionResult> OpenRunControlDesk(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            RunProjection? leadRun = _campaignSpine
                .GetAccountSummary(user, installLinking)
                .Runs
                .OrderByDescending(item => item.UpdatedAtUtc)
                .FirstOrDefault();

            return Redirect(leadRun is null
                ? "/account/work"
                : $"/account/run-control/{Uri.EscapeDataString(leadRun.RunId)}");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/run-control/open")}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "RUN CONTROL desk could not confirm the signed-in identity.");
            return Redirect("/run-control");
        }
    }

    [HttpGet("/account/onramp/starter")]
    [Produces("text/html")]
    public async Task<IActionResult> OnrampStarterPage(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            CampaignWorkspaceProjection? starterWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking);

            return Redirect(starterWorkspace is null
                ? "/ready"
                : $"/account/runsites/{Uri.EscapeDataString(starterWorkspace.WorkspaceId)}");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/onramp/starter")}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "ONRAMP starter route could not confirm the signed-in identity.");
            return Redirect("/onramp");
        }
    }

    [HttpGet("/account/onramp")]
    [Produces("text/html")]
    public async Task<IActionResult> OnrampPage(CancellationToken cancellationToken)
    {
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/onramp")}");
        }

        return await OpenOnramp(cancellationToken);
    }

    [HttpGet("/account/onramp/open")]
    [Produces("text/html")]
    public async Task<IActionResult> OpenOnramp(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
            CampaignWorkspaceProjection? starterWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking)
                ?? summary.Workspaces.FirstOrDefault();

            if (starterWorkspace is not null)
            {
                return Redirect("/account/onramp/starter");
            }

            if (summary.Restore.ClaimedDevices.Count > 0
                || summary.Restore.RecentArtifacts.Count > 0
                || summary.Restore.ConflictSummaries.Count > 0)
            {
                return Redirect("/account/access");
            }

            return Redirect("/ready");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/onramp/open")}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "ONRAMP could not confirm the signed-in identity.");
            return Redirect("/onramp");
        }
    }

    [HttpGet("/account/edition-studio")]
    [Produces("text/html")]
    public async Task<IActionResult> EditionStudioPage(CancellationToken cancellationToken)
    {
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/edition-studio")}");
        }

        return await OpenEditionStudio(cancellationToken);
    }

    [HttpGet("/account/edition-studio/open")]
    [Produces("text/html")]
    public async Task<IActionResult> OpenEditionStudio(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
            string preferredEdition = ResolvePreferredEditionStudioHead(summary);
            return Redirect($"/account/edition-studio/{Uri.EscapeDataString(preferredEdition)}");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/edition-studio/open")}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Edition Studio could not confirm the signed-in identity.");
            return Redirect("/edition-studio");
        }
    }

    [HttpGet("/account/edition-studio/{edition}")]
    [Produces("text/html")]
    public async Task<IActionResult> EditionStudioHeadPage([FromRoute] string edition, CancellationToken cancellationToken)
    {
        string normalizedEdition = ResolveNormalizedEditionStudioHeadId(edition);
        string requestedPath = $"/account/edition-studio/{Uri.EscapeDataString(edition)}";

        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(requestedPath)}");
        }

        return Redirect($"/account/work?edition={Uri.EscapeDataString(normalizedEdition)}");
    }

    [HttpGet("/account/local-co-processor")]
    [Produces("text/html")]
    public async Task<IActionResult> LocalCoProcessorPage(CancellationToken cancellationToken)
    {
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/local-co-processor")}");
        }

        return await OpenLocalCoProcessor(cancellationToken);
    }

    [HttpGet("/account/local-co-processor/open")]
    [Produces("text/html")]
    public async Task<IActionResult> OpenLocalCoProcessor(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
            string preferredProfile = ResolvePreferredLocalCoProcessorProfile(summary);
            return Redirect($"/account/local-co-processor/{Uri.EscapeDataString(preferredProfile)}");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/local-co-processor/open")}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Local Co-Processor could not confirm the signed-in identity.");
            return Redirect("/local-co-processor");
        }
    }

    [HttpGet("/account/local-co-processor/{profile}")]
    [Produces("text/html")]
    public async Task<IActionResult> LocalCoProcessorProfilePage([FromRoute] string profile, CancellationToken cancellationToken)
    {
        string normalizedProfile = ResolveNormalizedLocalCoProcessorProfileId(profile);
        string requestedPath = $"/account/local-co-processor/{Uri.EscapeDataString(profile)}";

        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(requestedPath)}");
        }

        return Redirect($"/account/access?localCoProcessor={Uri.EscapeDataString(normalizedProfile)}");
    }

    [HttpGet("/account/passport")]
    [Produces("text/html")]
    public async Task<IActionResult> RunnerPassportPage(CancellationToken cancellationToken)
    {
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/passport")}");
        }

        return await OpenRunnerPassport(cancellationToken);
    }

    [HttpGet("/account/passport/open")]
    [Produces("text/html")]
    public async Task<IActionResult> OpenRunnerPassport(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var accountSummary = _campaignSpine.GetAccountSummary(user, installLinking);

            if (accountSummary.Workspaces.Count > 0)
            {
                return Redirect("/account/work#aftermath-packages");
            }

            return Redirect("/account/access");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/passport/open")}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Runner Passport could not confirm the signed-in identity.");
            return Redirect("/passport");
        }
    }

    [HttpGet("/account/quicksilver")]
    [Produces("text/html")]
    public async Task<IActionResult> QuicksilverPage(CancellationToken cancellationToken)
    {
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/quicksilver")}");
        }

        return await OpenQuicksilver(cancellationToken);
    }

    [HttpGet("/account/quicksilver/open")]
    [Produces("text/html")]
    public async Task<IActionResult> OpenQuicksilver(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
            CampaignWorkspaceProjection? starterWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking)
                ?? summary.Workspaces.FirstOrDefault();

            if (summary.BuildLabHandoffs.Count > 0)
            {
                return Redirect("/account/quicksilver/builds");
            }

            if (summary.RulesNavigator.Count > 0)
            {
                return Redirect("/account/quicksilver/rules");
            }

            if (starterWorkspace is not null)
            {
                return Redirect("/account/quicksilver/runsites");
            }

            if (summary.CreatorPublications.Count > 0)
            {
                return Redirect("/account/quicksilver/creator");
            }

            return Redirect("/account/work");
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString("/account/quicksilver/open")}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Quicksilver bench could not confirm the signed-in identity.");
            return Redirect("/quicksilver");
        }
    }

    [HttpGet("/account/quicksilver/{focus}")]
    [Produces("text/html")]
    public async Task<IActionResult> QuicksilverFocusPage([FromRoute] string focus, CancellationToken cancellationToken)
    {
        string normalizedFocus = string.IsNullOrWhiteSpace(focus) ? "builds" : focus.Trim().ToLowerInvariant();
        string currentPath = $"/account/quicksilver/{Uri.EscapeDataString(normalizedFocus)}";

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            AccountCampaignSummary summary = _campaignSpine.GetAccountSummary(user, installLinking);
            CampaignWorkspaceProjection? starterWorkspace = _campaignSpine.GetStarterWorkspace(user, installLinking)
                ?? summary.Workspaces.FirstOrDefault();
            BuildLabHandoffProjection? leadHandoff = summary.BuildLabHandoffs.OrderByDescending(item => item.UpdatedAtUtc).FirstOrDefault();
            CreatorPublicationProjection? leadPublication = summary.CreatorPublications.OrderByDescending(item => item.UpdatedAtUtc).FirstOrDefault();
            RulesNavigatorAnswerProjection? leadRule = summary.RulesNavigator.FirstOrDefault();

            return normalizedFocus switch
            {
                "builds" => Redirect(leadHandoff is null ? "/account/alice" : $"/account/alice/{Uri.EscapeDataString(leadHandoff.HandoffId)}"),
                "rules" => Redirect(leadRule is null ? "/account/work" : $"/account/work/rules/{Uri.EscapeDataString(leadRule.EntryId)}"),
                "runsites" => Redirect(starterWorkspace is null ? "/account/runsites" : $"/account/runsites/{Uri.EscapeDataString(starterWorkspace.WorkspaceId)}"),
                "creator" => Redirect(leadPublication is null ? "/account/creator" : $"/account/creator/{Uri.EscapeDataString(leadPublication.PublicationId)}"),
                "briefings" => Redirect(leadPublication is null ? "/account/jackpoint" : $"/account/jackpoint/{Uri.EscapeDataString(leadPublication.PublicationId)}"),
                _ => Redirect("/account/quicksilver/open")
            };
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Quicksilver focus route {Focus} could not confirm the signed-in identity.", normalizedFocus);
            return Redirect("/quicksilver");
        }
    }

    [HttpPost("/account/work/publications/{publicationId}/submit")]
    [ValidateAntiForgeryToken]
    [Produces("text/html")]
    public Task<IActionResult> SubmitCreatorPublication(
        [FromRoute] string publicationId,
        [FromForm] string? notes,
        CancellationToken cancellationToken)
        => MutateCreatorPublication(
            publicationId,
            notes,
            cancellationToken,
            static (bridge, user, publication, workspace, mutationNotes) => bridge.SubmitForReview(user, publication, workspace, mutationNotes));

    [HttpPost("/account/work/publications/{publicationId}/approve")]
    [ValidateAntiForgeryToken]
    [Produces("text/html")]
    public Task<IActionResult> ApproveCreatorPublication(
        [FromRoute] string publicationId,
        [FromForm] string? notes,
        CancellationToken cancellationToken)
        => MutateCreatorPublication(
            publicationId,
            notes,
            cancellationToken,
            static (bridge, user, publication, workspace, mutationNotes) => bridge.ApproveReview(user, publication, workspace, mutationNotes));

    [HttpPost("/account/work/publications/{publicationId}/publish")]
    [ValidateAntiForgeryToken]
    [Produces("text/html")]
    public Task<IActionResult> PublishCreatorPublication(
        [FromRoute] string publicationId,
        [FromForm] string? notes,
        CancellationToken cancellationToken)
        => MutateCreatorPublication(
            publicationId,
            notes,
            cancellationToken,
            static (bridge, user, publication, workspace, mutationNotes) => bridge.Publish(user, publication, workspace, mutationNotes));

    [HttpPost("/account/work/publications/{publicationId}/reject")]
    [ValidateAntiForgeryToken]
    [Produces("text/html")]
    public Task<IActionResult> RejectCreatorPublication(
        [FromRoute] string publicationId,
        [FromForm] string? notes,
        CancellationToken cancellationToken)
        => MutateCreatorPublication(
            publicationId,
            notes,
            cancellationToken,
            static (bridge, user, publication, workspace, mutationNotes) => bridge.RejectReview(user, publication, workspace, mutationNotes));

    private static string ResolvePreferredEditionStudioHead(AccountCampaignSummary summary)
    {
        string[] candidates = summary.Workspaces.Select(item => item.RuleEnvironment.CompatibilityFingerprint)
            .Concat(summary.Dossiers.Select(item => item.RuleEnvironment.CompatibilityFingerprint))
            .Concat(summary.Restore.RecentRuleEnvironments.Select(item => item.CompatibilityFingerprint))
            .Select(ResolveNormalizedEditionStudioHeadId)
            .ToArray();

        if (candidates.Any(static item => string.Equals(item, "sr5", StringComparison.OrdinalIgnoreCase)))
        {
            return "sr5";
        }

        if (candidates.Any(static item => string.Equals(item, "sr4", StringComparison.OrdinalIgnoreCase)))
        {
            return "sr4";
        }

        return candidates.FirstOrDefault(static item => item is "sr4" or "sr5" or "sr6") ?? "sr6";
    }

    private static string ResolveNormalizedEditionStudioHeadId(string? candidate)
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

    private static string ResolvePreferredLocalCoProcessorProfile(AccountCampaignSummary summary)
    {
        if (summary.Restore.ClaimedDevices.Count > 0)
        {
            return "privacy_first";
        }

        if (summary.Workspaces.Count > 0 || summary.Dossiers.Count > 0)
        {
            return "hybrid_local";
        }

        return "hosted_only";
    }

    private static string ResolveNormalizedLocalCoProcessorProfileId(string? candidate)
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

    private static bool HasWorkSelection(
        string? workspaceId,
        string? runId,
        string? handoffId,
        string? entryId,
        string? publicationId)
        => !string.IsNullOrWhiteSpace(workspaceId)
            || !string.IsNullOrWhiteSpace(runId)
            || !string.IsNullOrWhiteSpace(handoffId)
            || !string.IsNullOrWhiteSpace(entryId)
            || !string.IsNullOrWhiteSpace(publicationId);

    private static string BuildAccountCurrentPath(
        string selectedSection,
        string? caseId,
        string? workspaceId,
        string? runId,
        string? handoffId,
        string? entryId,
        string? publicationId)
    {
        if (!string.IsNullOrWhiteSpace(caseId))
        {
            return $"/account/support/{Uri.EscapeDataString(caseId)}";
        }

        if (!string.IsNullOrWhiteSpace(workspaceId))
        {
            return $"/account/work/workspaces/{Uri.EscapeDataString(workspaceId)}";
        }

        if (!string.IsNullOrWhiteSpace(runId))
        {
            return $"/account/work/runs/{Uri.EscapeDataString(runId)}";
        }

        if (!string.IsNullOrWhiteSpace(handoffId))
        {
            return $"/account/work/build-handoffs/{Uri.EscapeDataString(handoffId)}";
        }

        if (!string.IsNullOrWhiteSpace(entryId))
        {
            return $"/account/work/rules/{Uri.EscapeDataString(entryId)}";
        }

        if (!string.IsNullOrWhiteSpace(publicationId))
        {
            return $"/account/work/publications/{Uri.EscapeDataString(publicationId)}";
        }

        return selectedSection == "profile"
            ? "/account"
            : $"/account/{selectedSection}";
    }

    private static string BuildAccountOpenCurrentPath(
        string? dossierId,
        string? campaignId,
        string? groupId,
        string? exampleId)
    {
        if (!string.IsNullOrWhiteSpace(dossierId))
        {
            return $"/account/open/character/{Uri.EscapeDataString(dossierId)}";
        }

        if (!string.IsNullOrWhiteSpace(campaignId))
        {
            return $"/account/open/campaign/{Uri.EscapeDataString(campaignId)}";
        }

        if (!string.IsNullOrWhiteSpace(groupId))
        {
            return $"/account/open/group/{Uri.EscapeDataString(groupId)}";
        }

        if (!string.IsNullOrWhiteSpace(exampleId))
        {
            return $"/account/open/example/{Uri.EscapeDataString(exampleId)}";
        }

        return "/account/work";
    }

    private static TItem? FindById<TItem>(
        IReadOnlyList<TItem> items,
        string? id,
        Func<TItem, string> keySelector)
        where TItem : class
    {
        if (string.IsNullOrWhiteSpace(id))
        {
            return null;
        }

        return items.FirstOrDefault(item => string.Equals(keySelector(item), id, StringComparison.OrdinalIgnoreCase));
    }

    private async Task<IActionResult> MutateCreatorPublication(
        string publicationId,
        string? notes,
        CancellationToken cancellationToken,
        Func<CreatorPublicationRegistryBridge, HubUserDto, CreatorPublicationProjection, CampaignWorkspaceProjection?, string?, CreatorPublicationRegistryProjection> mutation)
    {
        string currentPath = $"/account/work/publications/{Uri.EscapeDataString(publicationId)}";

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var campaignSpine = _campaignSpine.GetAccountSummary(user, installLinking);
            var publication = FindById(campaignSpine.CreatorPublications, publicationId, static item => item.PublicationId);
            if (publication is null)
            {
                return NotFound();
            }

            var workspace = campaignSpine.Workspaces.FirstOrDefault(item => string.Equals(item.CampaignId, publication.CampaignId, StringComparison.OrdinalIgnoreCase));
            mutation(_creatorPublicationRegistry, user, publication, workspace, notes);
            return Redirect(currentPath);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect($"/login?next={Uri.EscapeDataString(currentPath)}");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Creator publication account action could not confirm the signed-in identity.");
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException)
        {
            return Problem(statusCode: StatusCodes.Status409Conflict, detail: ex.Message);
        }
    }

    private static string NormalizeAccountSection(string? section)
        => string.IsNullOrWhiteSpace(section)
            ? "profile"
            : section.Trim().ToLowerInvariant() switch
            {
                "profile" => "profile",
                "support" => "support",
                "access" => "access",
                "work" => "work",
                "participation" => "participation",
                _ => "profile"
            };

    private static bool IsBillingSectionAlias(string? section)
        => !string.IsNullOrWhiteSpace(section)
           && section.Trim().ToLowerInvariant() is "billing" or "settings" or "advanced";

    private static IReadOnlyList<SectionLinkViewModel> BuildAccountCoreSections(string currentSection)
        => new[]
        {
            new SectionLinkViewModel("access", "Installs", "/account/access", string.Equals(currentSection, "access", StringComparison.OrdinalIgnoreCase)),
            new SectionLinkViewModel("work", "Campaigns", "/account/work", string.Equals(currentSection, "work", StringComparison.OrdinalIgnoreCase)),
            new SectionLinkViewModel("support", "Support", "/account/support", string.Equals(currentSection, "support", StringComparison.OrdinalIgnoreCase)),
            new SectionLinkViewModel("participation", "Participation", "/account/participation", string.Equals(currentSection, "participation", StringComparison.OrdinalIgnoreCase))
        };

    private static IReadOnlyList<SectionLinkViewModel> BuildAccountSecondarySections(string currentSection)
        => new[]
        {
            new SectionLinkViewModel("billing", "Billing", "/account/billing", false)
        };

    private static (string Title, string Description) DescribeAccountSection(string currentSection)
        => currentSection switch
        {
            "participation" => ("Account · Participation", "Public feedback and recognition."),
            "support" => ("Account · Support", "Tracked cases and the next step."),
            "access" => ("Account · Installs", "Linked installs, downloads, and recovery."),
            "work" => ("Account · Campaigns", "Characters, groups, and campaigns."),
            _ => ("Account", "Installs, campaigns, support, and billing.")
        };

    private MediaArtifactDocument GetPropertyquarryPropertyOrThrow(string propertyId)
    {
        if (_mediaHorizons is null)
        {
            throw new InvalidOperationException("PROPERTYQUARRY routes require the media artifact horizon catalog.");
        }

        return _mediaHorizons.GetPropertyquarryProperty(propertyId);
    }

    private static string BuildPropertyquarryPrepSearchAccountHref(string propertyLabel, string? workspaceId = null)
    {
        string escapedQuery = Uri.EscapeDataString(propertyLabel);
        return string.IsNullOrWhiteSpace(workspaceId)
            ? $"/account/work?prepQuery={escapedQuery}"
            : $"/account/work/workspaces/{Uri.EscapeDataString(workspaceId)}?prepQuery={escapedQuery}";
    }

    [HttpGet("me")]
    [ProducesResponseType<HubUserDto>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<HubUserDto>> GetMe([FromQuery] string? subjectId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = string.IsNullOrWhiteSpace(subjectId)
                ? await _identity.RequireSubjectAsync(Request, cancellationToken)
                : await _identity.RequireMatchingSubjectAsync(Request, subjectId, cancellationToken);
            return Ok(_accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("me/origin-dossiers/publications")]
    [ValidateAntiForgeryToken]
    [ProducesResponseType<OriginDossierPublicationImportResultDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<OriginDossierPublicationImportResultDto>> UpsertOriginDossierPublication(
        [FromBody] OriginDossierPublicationImportRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("Origin Dossier publication payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            HubUserDto user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            OriginDossierPublicationViewModel publication = _originDossierPublications.UpsertForAccount(user, subject.SubjectId, request);
            return Ok(OriginDossierPublicationService.ToImportResult(publication));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is InvalidOperationException or ArgumentException)
        {
            return Problem(statusCode: StatusCodes.Status409Conflict, detail: ex.Message);
        }
    }

    [HttpPost("me/profile")]
    [ValidateAntiForgeryToken]
    [ProducesResponseType<HubUserDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<HubUserDto>> UpsertProfile([FromBody] UpsertHubUserProfileRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("profile payload is required.");
        }

        try
        {
            var subject = string.IsNullOrWhiteSpace(request.SubjectId)
                ? await _identity.RequireSubjectAsync(Request, cancellationToken)
                : await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_accounts.UpsertProfile(request with { SubjectId = subject.SubjectId }));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("me/preferences")]
    [ProducesResponseType<HubUserExperienceDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<HubUserExperienceDto>> GetPreferences(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            return Ok(_experience.GetOrCreate(subject.SubjectId));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("me/preferences")]
    [ValidateAntiForgeryToken]
    [ProducesResponseType<HubUserExperienceDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<HubUserExperienceDto>> UpsertPreferences([FromBody] UpsertHubUserExperienceRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("preferences payload is required.");
        }

        try
        {
            var subject = string.IsNullOrWhiteSpace(request.SubjectId)
                ? await _identity.RequireSubjectAsync(Request, cancellationToken)
                : await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            HubUserExperienceDto existing = _experience.GetOrCreate(subject.SubjectId);
            HubUserExperienceDto updated = _experience.Upsert(request with { SubjectId = subject.SubjectId });
            if (!existing.BetaInterest && updated.BetaInterest)
            {
                HubUserDto user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
                string authProviderFamily = ParticipationOperatorNotificationService.InferAuthProviderFamily(_links.GetSummary(subject.SubjectId));
                await _participationNotifications.NotifyFirstActionIfNeededAsync(
                    user,
                    subject.Email,
                    intentKind: "beta",
                    entryRoute: "/account/participation",
                    authProviderFamily,
                    cancellationToken);
            }

            return Ok(updated);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }
}
