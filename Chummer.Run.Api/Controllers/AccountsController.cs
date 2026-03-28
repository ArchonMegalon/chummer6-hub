using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.Services.Support;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
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
    private readonly InstallLinkingService _installLinking;
    private readonly SupportCaseService _supportCases;
    private readonly SupportCasePresentationService _supportPresentation;
    private readonly CampaignSpineService _campaignSpine;
    private readonly CampaignWorkspaceServerPlaneService _workspaceServerPlane;
    private readonly HubPageChromeService _chrome;
    private readonly HubGoogleAuthService _google;
    private readonly PublicPrivacyBoundaryService _privacyBoundaries;
    private readonly ILogger<AccountsController> _logger;

    public AccountsController(
        AccountService accounts,
        HubIdentityClient identity,
        IdentityLinkService links,
        UserExperienceService experience,
        InstallLinkingService installLinking,
        SupportCaseService supportCases,
        SupportCasePresentationService supportPresentation,
        CampaignSpineService campaignSpine,
        CampaignWorkspaceServerPlaneService workspaceServerPlane,
        HubPageChromeService chrome,
        HubGoogleAuthService google,
        PublicPrivacyBoundaryService privacyBoundaries,
        ILogger<AccountsController> logger)
    {
        _accounts = accounts;
        _identity = identity;
        _links = links;
        _experience = experience;
        _installLinking = installLinking;
        _supportCases = supportCases;
        _supportPresentation = supportPresentation;
        _campaignSpine = campaignSpine;
        _workspaceServerPlane = workspaceServerPlane;
        _chrome = chrome;
        _google = google;
        _privacyBoundaries = privacyBoundaries;
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
        [FromRoute] string? publicationId = null)
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
            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            var supportCases = _supportCases.ListForReporter(user.UserId, subject.SubjectId).Items;
            var supportCaseSummaries = _supportPresentation.BuildList(supportCases, installLinking);
            var selectedSupportCase = string.IsNullOrWhiteSpace(caseId)
                ? null
                : _supportCases.GetForReporter(caseId, user.UserId, subject.SubjectId);
            var selectedSupportCaseSummary = selectedSupportCase is null ? null : _supportPresentation.Build(selectedSupportCase, installLinking);
            var campaignSpine = _campaignSpine.GetAccountSummary(user, installLinking);
            var selectedWorkspace = FindById(campaignSpine.Workspaces, workspaceId, static item => item.WorkspaceId);
            var selectedWorkspaceServerPlane = selectedWorkspace is null
                ? null
                : _workspaceServerPlane.GetWorkspaceServerPlane(user, selectedWorkspace.WorkspaceId, installLinking);
            var selectedRun = FindById(campaignSpine.Runs, runId, static item => item.RunId);
            var selectedBuildLabHandoff = FindById(campaignSpine.BuildLabHandoffs, handoffId, static item => item.HandoffId);
            var selectedRulesNavigatorAnswer = FindById(campaignSpine.RulesNavigator, entryId, static item => item.EntryId);
            var selectedCreatorPublication = FindById(campaignSpine.CreatorPublications, publicationId, static item => item.PublicationId);
            var model = new AccountPageViewModel(
                Chrome: _chrome.BuildAuthenticatedChrome(chromeTitle, chromeDescription, currentPath, user.DisplayName),
                CurrentSection: selectedSection,
                CoreSections: BuildAccountCoreSections(selectedSection),
                SecondarySections: BuildAccountSecondarySections(selectedSection),
                User: user,
                Links: _links.GetSummary(subject.SubjectId),
                Experience: _experience.GetOrCreate(subject.SubjectId),
                GoogleAvailable: _google.IsConfigured(),
                InstallLinking: installLinking,
                SupportCases: supportCases,
                SupportCaseSummaries: supportCaseSummaries,
                SelectedSupportCase: selectedSupportCase,
                SelectedSupportCaseSummary: selectedSupportCaseSummary,
                CampaignSpine: campaignSpine,
                SelectedWorkspace: selectedWorkspace,
                SelectedWorkspaceServerPlane: selectedWorkspaceServerPlane,
                SelectedRun: selectedRun,
                SelectedBuildLabHandoff: selectedBuildLabHandoff,
                SelectedRulesNavigatorAnswer: selectedRulesNavigatorAnswer,
                SelectedCreatorPublication: selectedCreatorPublication,
                PrivacyBoundary: _privacyBoundaries.BuildPanel("account"));
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

    private static string NormalizeAccountSection(string? section)
        => string.IsNullOrWhiteSpace(section)
            ? "profile"
            : section.Trim().ToLowerInvariant() switch
            {
                "profile" => "profile",
                "support" => "support",
                "access" => "access",
                "work" => "work",
                "settings" => "settings",
                "advanced" => "advanced",
                _ => "profile"
            };

    private static IReadOnlyList<SectionLinkViewModel> BuildAccountCoreSections(string currentSection)
        => new[]
        {
            new SectionLinkViewModel("profile", "Profile", "/account", string.Equals(currentSection, "profile", StringComparison.OrdinalIgnoreCase)),
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
            return Ok(_experience.Upsert(request with { SubjectId = subject.SubjectId }));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }
}
