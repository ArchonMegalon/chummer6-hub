using System.Text.Json;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Ledger;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/ledger")]
public sealed class LedgerController : ControllerBase
{
    private readonly AccountService _accounts;
    private readonly LedgerService _ledger;
    private readonly RewardService _rewards;

    public LedgerController(AccountService accounts, LedgerService ledger, RewardService rewards)
    {
        _accounts = accounts;
        _ledger = ledger;
        _rewards = rewards;
    }

    [HttpPost("receipts")]
    [ProducesResponseType<ReceiptIngestResultDto>(StatusCodes.Status200OK)]
    public ActionResult<ReceiptIngestResultDto> Ingest([FromBody] ContributionReceiptDto? receipt)
    {
        if (receipt is null)
        {
            return BadRequest("receipt payload is required.");
        }

        try
        {
            return Ok(_ledger.Ingest(receipt));
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpGet("me")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    [Produces("application/json")]
    public ActionResult<object> GetMine([FromQuery] string subjectId)
    {
        var user = _accounts.GetBySubject(subjectId);
        if (user is null)
        {
            return NotFound();
        }

        return Ok(new
        {
            user,
            ledger = _ledger.ListForUser(user.UserId),
            rewards = _rewards.ListRewardsForUser(user.UserId),
            badges = _rewards.ListBadgesForUser(user.UserId),
        });
    }
}
