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

    public AccountLinksController(IdentityLinkService links, HubIdentityClient identity)
    {
        _links = links;
        _identity = identity;
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
    [ProducesResponseType<LinkedIdentityDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<LinkedIdentityDto>> LinkEmail([FromBody] LinkEmailIdentityRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("email identity payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_links.LinkEmail(request with { SubjectId = subject.SubjectId }));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("links/confirm")]
    [ProducesResponseType<LinkedIdentityDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<LinkedIdentityDto>> ConfirmLink([FromBody] ConfirmIdentityLinkRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("identity confirmation payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_links.ConfirmIdentityLink(request with { SubjectId = subject.SubjectId }));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("links/provider")]
    [ProducesResponseType<LinkedIdentityDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<LinkedIdentityDto>> LinkProvider([FromBody] LinkExternalIdentityRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("external identity payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_links.LinkExternalIdentity(request with { SubjectId = subject.SubjectId }));
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
