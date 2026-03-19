using Chummer.Run.AI.Services.Booster;
using Chummer.Run.Contracts.Ledger;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.AI.Controllers;

[ApiController]
[Route("api/v1/ai/booster")]
public sealed class BoosterReceiptsController : ControllerBase
{
    private readonly BoosterReceiptProjectionService _projections;

    public BoosterReceiptsController(BoosterReceiptProjectionService projections)
    {
        _projections = projections;
    }

    [HttpPost("receipts")]
    [ProducesResponseType<ReceiptIngestResultDto>(StatusCodes.Status200OK)]
    public ActionResult<ReceiptIngestResultDto> IngestReceipt([FromBody] ContributionReceiptDto? receipt)
    {
        if (receipt is null)
        {
            return BadRequest("receipt payload is required.");
        }

        return Ok(_projections.Ingest(receipt));
    }

    [HttpGet("sessions/{sponsorSessionId}")]
    public ActionResult<object> GetSessionProjection([FromRoute] string sponsorSessionId)
        => Ok(_projections.SessionProjection(sponsorSessionId));

    [HttpGet("leaderboard-projection")]
    public ActionResult<object> GetLeaderboardProjection()
        => Ok(_projections.LeaderboardProjection());

    [HttpGet("group-projection/{groupId}")]
    public ActionResult<object> GetGroupProjection([FromRoute] string groupId)
        => Ok(_projections.GroupProjection(groupId));
}
