using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Boosters;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/boost-codes")]
public sealed class BoostCodesController : ControllerBase
{
    private readonly GroupService _groups;

    public BoostCodesController(GroupService groups)
    {
        _groups = groups;
    }

    [HttpPost]
    [ProducesResponseType<BoostCodeDto>(StatusCodes.Status200OK)]
    public ActionResult<BoostCodeDto> Create([FromBody] CreateBoostCodeRequest? request)
    {
        if (request is null)
        {
            return BadRequest("boost-code payload is required.");
        }

        try
        {
            return Ok(_groups.CreateBoostCode(request));
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpPost("redeem")]
    [ProducesResponseType<BoostCodeDto>(StatusCodes.Status200OK)]
    public ActionResult<BoostCodeDto> Redeem([FromBody] RedeemBoostCodeRequest? request)
    {
        if (request is null)
        {
            return BadRequest("redeem payload is required.");
        }

        try
        {
            return Ok(_groups.RedeemBoostCode(request));
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException)
        {
            return BadRequest(ex.Message);
        }
    }
}
