using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[AutoValidateAntiforgeryToken]
[Route("api/v1/account/campaigns/{campaignId}/sessions/{sessionId}/venue")]
public sealed class GmSessionVenueController : ControllerBase
{
    private readonly HubIdentityClient _identity;
    private readonly AccountService _accounts;
    private readonly GmSessionVenueService _venues;

    public GmSessionVenueController(HubIdentityClient identity, AccountService accounts, GmSessionVenueService venues)
    {
        _identity = identity;
        _accounts = accounts;
        _venues = venues;
    }

    [HttpGet]
    [ProducesResponseType<GmSessionVenueProjection>(StatusCodes.Status200OK)]
    public async Task<ActionResult<GmSessionVenueProjection>> GetVenue(
        [FromRoute] string campaignId,
        [FromRoute] string sessionId,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return Ok(_venues.GetVenue(user.UserId, campaignId, sessionId));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (KeyNotFoundException ex)
        {
            return NotFound(ex.Message);
        }
    }

    [HttpPost("manual-link")]
    [ProducesResponseType<VenueLinkReceiptProjection>(StatusCodes.Status200OK)]
    public async Task<ActionResult<VenueLinkReceiptProjection>> AddManualVenueLink(
        [FromRoute] string campaignId,
        [FromRoute] string sessionId,
        [FromBody] ManualVenueLinkRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("manual venue link payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return Ok(_venues.AddManualVenueLink(user.UserId, campaignId, sessionId, request));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (KeyNotFoundException ex)
        {
            return NotFound(ex.Message);
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpPost("behuman")]
    [ProducesResponseType<VenueCreatedReceiptProjection>(StatusCodes.Status200OK)]
    public async Task<ActionResult<VenueCreatedReceiptProjection>> CreateBeHumanVenue(
        [FromRoute] string campaignId,
        [FromRoute] string sessionId,
        [FromBody] CreateBeHumanVenueRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("BeHuman venue payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return Ok(_venues.CreateBeHumanVenue(user.UserId, campaignId, sessionId, request));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (KeyNotFoundException ex)
        {
            return NotFound(ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Conflict(new ProblemDetails
            {
                Title = "BeHuman venue creation unavailable",
                Detail = ex.Message,
                Status = StatusCodes.Status409Conflict
            });
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpPost("closeout")]
    [ProducesResponseType<SessionVenueCloseoutReceiptProjection>(StatusCodes.Status200OK)]
    public async Task<ActionResult<SessionVenueCloseoutReceiptProjection>> CloseVenue(
        [FromRoute] string campaignId,
        [FromRoute] string sessionId,
        [FromBody] SessionVenueCloseoutRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("session venue closeout payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return Ok(_venues.CloseVenue(user.UserId, campaignId, sessionId, request));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (KeyNotFoundException ex)
        {
            return NotFound(ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Conflict(new ProblemDetails
            {
                Title = "Session venue closeout unavailable",
                Detail = ex.Message,
                Status = StatusCodes.Status409Conflict
            });
        }
    }
}
