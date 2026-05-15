using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.KarmaForge;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.ViewModels;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Ledger;
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
    private readonly SupportCaseService _supportCases;
    private readonly SupportCasePresentationService _supportPresentation;
    private readonly CampaignSpineService _campaignSpine;
    private readonly CampaignWorkspaceServerPlaneService _workspaceServerPlane;
    private readonly CreatorPublicationRegistryBridge _creatorPublicationRegistry;
    private readonly BoostSessionService _sessions;
    private readonly LeaderboardService _leaderboards;
    private readonly PublicPackageCatalogService _packageCatalog;
    private readonly KarmaForgeDiscoveryService _karmaForge;
    private readonly HubPageChromeService _chrome;
    private readonly HubGoogleAuthService _google;
    private readonly PublicReleaseManifestService _releases;
    private readonly ReleaseSelectionService _releaseSelection;
    private readonly PublicPrivacyBoundaryService _privacyBoundaries;
    private readonly SignedInTrustStatusService _signedInTrustStatus;
    private readonly ILogger<AccountsController> _logger;

    public AccountsController(
        AccountService accounts,
        HubIdentityClient identity,
        IdentityLinkService links,
        UserExperienceService experience,
        ParticipationOperatorNotificationService participationNotifications,
        InstallLinkingService installLinking,
        SupportCaseService supportCases,
        SupportCasePresentationService supportPresentation,
        CampaignSpineService campaignSpine,
        CampaignWorkspaceServerPlaneService workspaceServerPlane,
        CreatorPublicationRegistryBridge creatorPublicationRegistry,
        BoostSessionService sessions,
        LeaderboardService leaderboards,
        PublicPackageCatalogService packageCatalog,
        KarmaForgeDiscoveryService karmaForge,
        HubPageChromeService chrome,
        HubGoogleAuthService google,
        PublicReleaseManifestService releases,
        ReleaseSelectionService releaseSelection,
        PublicPrivacyBoundaryService privacyBoundaries,
        SignedInTrustStatusService signedInTrustStatus,
        ILogger<AccountsController> logger)
    {
        _accounts = accounts;
        _identity = identity;
        _links = links;
        _experience = experience;
        _participationNotifications = participationNotifications;
        _installLinking = installLinking;
        _supportCases = supportCases;
        _supportPresentation = supportPresentation;
        _campaignSpine = campaignSpine;
        _workspaceServerPlane = workspaceServerPlane;
        _creatorPublicationRegistry = creatorPublicationRegistry;
        _sessions = sessions;
        _leaderboards = leaderboards;
        _packageCatalog = packageCatalog;
        _karmaForge = karmaForge;
        _chrome = chrome;
        _google = google;
        _releases = releases;
        _releaseSelection = releaseSelection;
        _privacyBoundaries = privacyBoundaries;
        _signedInTrustStatus = signedInTrustStatus;
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
        var selectedSection = !string.IsNullOrWhiteSpace(caseId)
            ? "support"
            : HasWorkSelection(workspaceId, runId, handoffId, entryId, publicationId)
                ? "work"
                : NormalizeAccountSection(section);
        var currentPath = BuildAccountCurrentPath(selectedSection, caseId, workspaceId, runId, handoffId, entryId, publicationId);
        var (chromeTitle, chromeDescription) = DescribeAccountSection(selectedSection);

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var links = _links.GetSummary(subject.SubjectId);
            var experience = _experience.GetOrCreate(subject.SubjectId);
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var supportCases = _supportCases.ListForReporter(user.UserId, subject.SubjectId).Items;
            var supportCaseSummaries = _supportPresentation.BuildList(supportCases, installLinking);
            var selectedSupportCase = string.IsNullOrWhiteSpace(caseId)
                ? null
                : _supportCases.GetForReporter(caseId, user.UserId, subject.SubjectId);
            var selectedSupportCaseSummary = selectedSupportCase is null ? null : _supportPresentation.Build(selectedSupportCase, installLinking);
            var campaignSpine = _campaignSpine.GetAccountSummary(user, installLinking);
            EntitlementSyncReceiptProjection entitlementSyncReceipts = _workspaceServerPlane.GetEntitlementSyncReceiptProjection(user, installLinking);
            var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
            var releaseExperience = _releaseSelection.BuildExperience(manifest, Request.Headers.UserAgent.ToString(), authenticated: true);
            var selectedWorkspace = FindById(campaignSpine.Workspaces, workspaceId, static item => item.WorkspaceId);
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
                ParticipationActivityReceipts: _participationNotifications.ListReceiptsForUser(user.UserId, 6));
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
                Chrome: _chrome.BuildPublicChrome("Account unavailable", "Hub could not confirm the signed-in account surface right now.", currentPath),
                Heading: "Account is unavailable right now",
                SupportLine: "Chummer could not open the signed-in account surface right now. Your account details were not changed.",
                Notice: null,
                PrimaryLabel: "Try account again",
                PrimaryHref: currentPath,
                SecondaryLabel: "Return home",
                SecondaryHref: "/home"));
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
                "settings" => "settings",
                "advanced" => "advanced",
                _ => "profile"
            };

    private static IReadOnlyList<SectionLinkViewModel> BuildAccountCoreSections(string currentSection)
        => new[]
        {
            new SectionLinkViewModel("profile", "Profile", "/account", string.Equals(currentSection, "profile", StringComparison.OrdinalIgnoreCase)),
            new SectionLinkViewModel("participation", "Participation", "/account/participation", string.Equals(currentSection, "participation", StringComparison.OrdinalIgnoreCase)),
            new SectionLinkViewModel("support", "Support", "/account/support", string.Equals(currentSection, "support", StringComparison.OrdinalIgnoreCase)),
            new SectionLinkViewModel("access", "Devices & access", "/account/access", string.Equals(currentSection, "access", StringComparison.OrdinalIgnoreCase)),
            new SectionLinkViewModel("work", "Work", "/account/work", string.Equals(currentSection, "work", StringComparison.OrdinalIgnoreCase))
        };

    private static IReadOnlyList<SectionLinkViewModel> BuildAccountSecondarySections(string currentSection)
        => new[]
        {
            new SectionLinkViewModel("settings", "More settings", "/account/settings", string.Equals(currentSection, "settings", StringComparison.OrdinalIgnoreCase)),
            new SectionLinkViewModel("advanced", "Advanced", "/account/advanced", string.Equals(currentSection, "advanced", StringComparison.OrdinalIgnoreCase))
        };

    private static (string Title, string Description) DescribeAccountSection(string currentSection)
        => currentSection switch
        {
            "participation" => ("Account · Participation", "Followed package work, guided contribution receipts, and privacy-safe recognition settings."),
            "support" => ("Account · Support", "Open, track, and close support without leaving the account surface."),
            "access" => ("Account · Devices & access", "Linked installs, access rights, and claim handoff in one calmer route."),
            "work" => ("Account · Work", "Campaign return, shared work, and deeper follow-through when you explicitly need them."),
            "settings" => ("Account · Settings", "Preferences, linked channels, participation, and help policy outside the customer core."),
            "advanced" => ("Account · Advanced", "Account identifiers and deeper account details when you explicitly need them."),
            _ => ("Account", "Profile, sign-in methods, recovery posture, and channel settings.")
        };

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
