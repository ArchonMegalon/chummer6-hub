using System.Text.Json;
using Chummer.Run.AI.Services.Booster;
using Chummer.Run.Contracts.Ledger;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.AI.Controllers;

[ApiController]
[Route("api/v1/ai/booster")]
public sealed class BoosterReceiptsController : ControllerBase
{
    private readonly BoosterReceiptProjectionService _projections;
    private readonly BoosterReceiptVerifier _verifier;

    public BoosterReceiptsController(BoosterReceiptProjectionService projections, BoosterReceiptVerifier verifier)
    {
        _projections = projections;
        _verifier = verifier;
    }

    [HttpPost("receipts")]
    [ProducesResponseType<ReceiptIngestResultDto>(StatusCodes.Status200OK)]
    public ActionResult<ReceiptIngestResultDto> IngestReceipt([FromBody] JsonElement receipt)
    {
        try
        {
            var verifiedReceipt = _verifier.VerifyAndDeserialize(Request, receipt);
            return Ok(_projections.Ingest(verifiedReceipt));
        }
        catch (BoosterReceiptAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
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
