using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[AutoValidateAntiforgeryToken]
[Route("api/v1/accounts/me")]
public sealed class AccountLinksController : ControllerBase
{
    private const int MaxRequestBodyBytes = 16 * 1024;

    private readonly IdentityLinkService _links;
    private readonly ExecutiveAssistantChannelMessagingService _channelMessaging;
    private readonly HubIdentityClient _identity;
    private readonly AccountService _accounts;
    private readonly HubBrowserAuthService _browserAuth;
    private readonly HubEmailLinkVerificationService _emailLinks;

    public AccountLinksController(
        IdentityLinkService links,
        ExecutiveAssistantChannelMessagingService channelMessaging,
        HubIdentityClient identity,
        AccountService accounts,
        HubBrowserAuthService browserAuth,
        HubEmailLinkVerificationService emailLinks)
    {
        _links = links;
        _channelMessaging = channelMessaging;
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
    [RequestSizeLimit(MaxRequestBodyBytes)]
    public ActionResult<LinkedIdentityDto> ConfirmLink([FromBody] ConfirmIdentityLinkRequest? request)
    {
        return Problem(statusCode: StatusCodes.Status403Forbidden, detail: "Identity links are confirmed through provider callbacks or email verification, not this API.");
    }

    [HttpPost("links/email/start")]
    [ValidateAntiForgeryToken]
    [ProducesResponseType<RecoveryEmailLinkStartResponse>(StatusCodes.Status200OK)]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    public async Task<ActionResult<RecoveryEmailLinkStartResponse>> StartRecoveryEmailLink([FromBody] StartRecoveryEmailLinkRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("recovery email payload is required.");
        }

        HubEmailSignInAvailability emailEntryAvailability = HubEmailSignInPolicy.Resolve(HttpContext?.RequestServices?.GetService<IConfiguration>());
        if (!emailEntryAvailability.Enabled)
        {
            return Problem(
                statusCode: StatusCodes.Status503ServiceUnavailable,
                detail: emailEntryAvailability.PreviewNote);
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
            var verificationToken = _emailLinks.CreateVerificationToken(subject.SubjectId, normalizedEmail, nextPath);
            var verificationNextPath = _emailLinks.BuildVerificationCallbackPath(verificationToken);
            var started = await _browserAuth.StartEmailEntryAsync(normalizedEmail, currentUser.DisplayName, verificationNextPath, cancellationToken);
            var link = _links.LinkEmail(new LinkEmailIdentityRequest(subject.SubjectId, normalizedEmail, MakePrimary: false));
            var previewHref = string.Equals(started.DeliveryMode, "preview_inline_link", StringComparison.OrdinalIgnoreCase)
                && !string.IsNullOrWhiteSpace(started.TicketId)
                && HubBrowserAuthService.ShouldExposeInlinePreviewLink(Request)
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

    [HttpGet("channels/{channelKind}/messages")]
    [ProducesResponseType<IReadOnlyList<ExecutiveAssistantChannelConversationDto>>(StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyList<ExecutiveAssistantChannelConversationDto>>> ListChannelConversations(
        string channelKind,
        [FromQuery] int take = 24,
        CancellationToken cancellationToken = default)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            return Ok(_channelMessaging.ListConversations(subject.SubjectId, channelKind, take));
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

    [HttpGet("channels/{channelKind}/messages/{conversationId}")]
    [ProducesResponseType<ExecutiveAssistantChannelConversationDto>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<ExecutiveAssistantChannelConversationDto>> GetChannelConversation(
        string channelKind,
        string conversationId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            ExecutiveAssistantChannelConversationDto? conversation = _channelMessaging.GetConversation(
                subject.SubjectId,
                channelKind,
                conversationId);
            return conversation is null ? NotFound() : Ok(conversation);
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

    [HttpPost("channels/{channelKind}/messages")]
    [ValidateAntiForgeryToken]
    [ProducesResponseType<ExecutiveAssistantChannelSendResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    public async Task<ActionResult<ExecutiveAssistantChannelSendResult>> SendChannelMessage(
        string channelKind,
        [FromBody] ExecutiveAssistantChannelSendRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("channel message payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            return Ok(await _channelMessaging.SendMessageAsync(subject.SubjectId, channelKind, request, cancellationToken));
        }
        catch (ArgumentException ex)
        {
            return ValidationProblem(detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status409Conflict, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("channels")]
    [ValidateAntiForgeryToken]
    [ProducesResponseType<ChannelLinkDto>(StatusCodes.Status200OK)]
    [RequestSizeLimit(MaxRequestBodyBytes)]
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

    [HttpGet("links/channels/{channelKind}/deeplink")]
    [ProducesResponseType<ChannelDeepLinkResponse>(StatusCodes.Status200OK)]
    public async Task<ActionResult<ChannelDeepLinkResponse>> GetChannelDeeplink(string channelKind, [FromQuery] string? channelHandle, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            return Ok(_links.GetChannelDeepLink(subject.SubjectId, channelKind, channelHandle));
        }
        catch (ArgumentException ex)
        {
            return ValidationProblem(detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (KeyNotFoundException ex)
        {
            return NotFound(ex.Message);
        }
    }

    [HttpPost("channels/{channelKind}/executive-assistant")]
    [ValidateAntiForgeryToken]
    [ProducesResponseType<ChannelLinkDto>(StatusCodes.Status200OK)]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    public async Task<ActionResult<ChannelLinkDto>> LinkChannelToExecutiveAssistant(
        string channelKind,
        [FromBody] LinkChannelToExecutiveAssistantRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("executive assistant link payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_links.LinkChannelToExecutiveAssistant(channelKind, request with { SubjectId = subject.SubjectId }));
        }
        catch (ArgumentException ex)
        {
            return ValidationProblem(detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status409Conflict, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }
}
