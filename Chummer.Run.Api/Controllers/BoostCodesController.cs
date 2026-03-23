using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Boosters;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/boost-codes")]
public sealed class BoostCodesController : ControllerBase
{
    private readonly GroupService _groups;
    private readonly HubIdentityClient _identity;

    public BoostCodesController(GroupService groups, HubIdentityClient identity)
    {
        _groups = groups;
        _identity = identity;
    }

    [HttpPost]
    [ProducesResponseType<BoostCodeDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<BoostCodeDto>> Create([FromBody] CreateBoostCodeRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("boost-code payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_groups.CreateBoostCode(request with { SubjectId = subject.SubjectId }));
        }
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpPost("redeem")]
    [ProducesResponseType<BoostCodeDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<BoostCodeDto>> Redeem([FromBody] RedeemBoostCodeRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("redeem payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_groups.RedeemBoostCode(request with { SubjectId = subject.SubjectId }));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException)
        {
            return BadRequest(ex.Message);
        }
    }
}
