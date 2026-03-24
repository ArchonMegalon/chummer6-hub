using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/accounts/me")]
public sealed class AccountLinksController : ControllerBase
{
    private readonly IdentityLinkService _links;
    private readonly HubIdentityClient _identity;
    private readonly AccountService _accounts;
    private readonly HubBrowserAuthService _browserAuth;
    private readonly HubEmailLinkVerificationService _emailLinks;

    public AccountLinksController(
        IdentityLinkService links,
        HubIdentityClient identity,
        AccountService accounts,
        HubBrowserAuthService browserAuth,
        HubEmailLinkVerificationService emailLinks)
    {
        _links = links;
        _identity = identity;
        _accounts = accounts;
        _browserAuth = browserAuth;
        _emailLinks = emailLinks;
    }

    [HttpGet("links")]
    [ProducesResponseType<AccountLinkSummaryDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<AccountLinkSummaryDto>> GetLinks(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            return Ok(_links.GetSummary(subject.SubjectId));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("links/email")]
    public ActionResult LinkEmail()
        => Problem(
            statusCode: StatusCodes.Status410Gone,
            detail: "Recovery email linking now starts through /api/v1/accounts/me/links/email/start so the address can be verified before Hub links it.");

    [HttpPost("links/confirm")]
    [ProducesResponseType<LinkedIdentityDto>(StatusCodes.Status200OK)]
    public ActionResult<LinkedIdentityDto> ConfirmLink([FromBody] ConfirmIdentityLinkRequest? request)
    {
        return Problem(statusCode: StatusCodes.Status403Forbidden, detail: "Identity links are confirmed through provider callbacks or email verification, not this API.");
    }

    [HttpPost("links/email/start")]
    [ProducesResponseType<RecoveryEmailLinkStartResponse>(StatusCodes.Status200OK)]
    public async Task<ActionResult<RecoveryEmailLinkStartResponse>> StartRecoveryEmailLink([FromBody] StartRecoveryEmailLinkRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("recovery email payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            var currentUser = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            var normalizedEmail = request.Email.Trim().ToLowerInvariant();
            var existingEmailLink = _links.FindLinkedIdentity("email", normalizedEmail);
            if (existingEmailLink is not null
                && !string.Equals(existingEmailLink.UserId, currentUser.UserId, StringComparison.OrdinalIgnoreCase))
            {
                return Conflict(new ProblemDetails
                {
                    Status = StatusCodes.Status409Conflict,
                    Title = "Recovery email already linked",
                    Detail = "That email address is already linked to a different Chummer account."
                });
            }

            var nextPath = HubBrowserAuthService.SanitizeNextPath(request.NextPath, "/account");
            var link = _links.LinkEmail(new LinkEmailIdentityRequest(subject.SubjectId, normalizedEmail, MakePrimary: false));
            var verificationToken = _emailLinks.CreateVerificationToken(subject.SubjectId, normalizedEmail, nextPath);
            var verificationNextPath = _emailLinks.BuildVerificationCallbackPath(verificationToken);
            var started = await _browserAuth.StartEmailEntryAsync(normalizedEmail, currentUser.DisplayName, verificationNextPath, cancellationToken);
            var previewHref = string.Equals(started.DeliveryMode, "preview_inline_link", StringComparison.OrdinalIgnoreCase)
                ? $"/auth/email/callback?ticket={Uri.EscapeDataString(started.TicketId)}&next={Uri.EscapeDataString(verificationNextPath)}"
                : null;

            return Ok(new RecoveryEmailLinkStartResponse(
                Email: normalizedEmail,
                LinkStatus: link.Status,
                DeliveryMode: started.DeliveryMode,
                PreviewNote: started.PreviewNote,
                PreviewHref: previewHref,
                ExpiresAtUtc: started.ExpiresAtUtc));
        }
        catch (HubBrowserAuthUnavailableException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Conflict(new ProblemDetails
            {
                Status = StatusCodes.Status409Conflict,
                Title = "Recovery email could not be linked",
                Detail = ex.Message
            });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("links/provider")]
    public ActionResult LinkProvider()
        => Problem(
            statusCode: StatusCodes.Status410Gone,
            detail: "Provider links are created through verified provider callbacks, not this API.");

    [HttpPost("channels")]
    [ProducesResponseType<ChannelLinkDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<ChannelLinkDto>> LinkChannel([FromBody] LinkChannelRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("channel link payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_links.LinkChannel(request with { SubjectId = subject.SubjectId }));
        }
        catch (ArgumentException ex)
        {
            return ValidationProblem(detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }
}
