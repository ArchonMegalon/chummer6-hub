using System.Text.Json;
using Chummer.Run.AI.Services.Booster;
using Chummer.Run.Contracts.Ledger;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.AI.Controllers;

[ApiController]
[Route("api/v1/ai/booster")]
public sealed class BoosterReceiptsController : ControllerBase
{
    private const int MaxRequestBodyBytes = 16 * 1024;

    private readonly BoosterProjectionAccessGuard _accessGuard;
    private readonly BoosterReceiptProjectionService _projections;
    private readonly BoosterReceiptVerifier _verifier;

    public BoosterReceiptsController(BoosterProjectionAccessGuard accessGuard, BoosterReceiptProjectionService projections, BoosterReceiptVerifier verifier)
    {
        _accessGuard = accessGuard;
        _projections = projections;
        _verifier = verifier;
    }

    [HttpPost("receipts")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
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
    {
        try
        {
            _accessGuard.Require(Request);
            return Ok(_projections.SessionProjection(sponsorSessionId));
        }
        catch (BoosterProjectionAccessException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("leaderboard-projection")]
    public ActionResult<object> GetLeaderboardProjection()
    {
        try
        {
            _accessGuard.Require(Request);
            return Ok(_projections.LeaderboardProjection());
        }
        catch (BoosterProjectionAccessException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("group-projection/{groupId}")]
    public ActionResult<object> GetGroupProjection([FromRoute] string groupId)
    {
        try
        {
            _accessGuard.Require(Request);
            return Ok(_projections.GroupProjection(groupId));
        }
        catch (BoosterProjectionAccessException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }
}
