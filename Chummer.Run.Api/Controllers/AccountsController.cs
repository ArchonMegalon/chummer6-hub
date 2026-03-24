using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
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
    private readonly HubPageChromeService _chrome;
    private readonly HubGoogleAuthService _google;
    private readonly ILogger<AccountsController> _logger;

    public AccountsController(
        AccountService accounts,
        HubIdentityClient identity,
        IdentityLinkService links,
        UserExperienceService experience,
        HubPageChromeService chrome,
        HubGoogleAuthService google,
        ILogger<AccountsController> logger)
    {
        _accounts = accounts;
        _identity = identity;
        _links = links;
        _experience = experience;
        _chrome = chrome;
        _google = google;
        _logger = logger;
    }

    [HttpGet("/account")]
    [Produces("text/html")]
    public async Task<IActionResult> AccountPage(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var model = new AccountPageViewModel(
                Chrome: _chrome.BuildAuthenticatedChrome("Account", "Profile, sign-in methods, recovery posture, and channel settings.", "/account", user.DisplayName),
                User: user,
                Links: _links.GetSummary(subject.SubjectId),
                Experience: _experience.GetOrCreate(subject.SubjectId),
                GoogleAvailable: _google.IsConfigured());
            return View("~/Views/Accounts/Account.cshtml", model);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return Redirect("/login?next=/account");
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Account page could not confirm the signed-in identity.");
            return View("~/Views/Auth/Message.cshtml", new AuthMessagePageViewModel(
                Chrome: _chrome.BuildPublicChrome("Account unavailable", "Hub could not confirm the signed-in account surface right now.", "/account"),
                Heading: "Account is unavailable right now",
                SupportLine: ex.Message,
                Notice: null,
                PrimaryLabel: "Try account again",
                PrimaryHref: "/account",
                SecondaryLabel: "Return home",
                SecondaryHref: "/home"));
        }
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
