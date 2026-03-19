using System.Text.Json;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Ledger;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/ledger")]
public sealed class LedgerController : ControllerBase
{
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;
    private readonly LedgerService _ledger;
    private readonly FleetReceiptVerifier _receiptVerifier;
    private readonly RewardService _rewards;

    public LedgerController(AccountService accounts, HubIdentityClient identity, LedgerService ledger, FleetReceiptVerifier receiptVerifier, RewardService rewards)
    {
        _accounts = accounts;
        _identity = identity;
        _ledger = ledger;
        _receiptVerifier = receiptVerifier;
        _rewards = rewards;
    }

    [HttpPost("receipts")]
    [ProducesResponseType<ReceiptIngestResultDto>(StatusCodes.Status200OK)]
    public ActionResult<ReceiptIngestResultDto> Ingest([FromBody] JsonElement receipt)
    {
        try
        {
            var verifiedReceipt = _receiptVerifier.VerifyAndDeserialize(Request, receipt);
            return Ok(_ledger.Ingest(verifiedReceipt));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpGet("me")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    [Produces("application/json")]
    public async Task<ActionResult<object>> GetMine([FromQuery] string subjectId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, subjectId, cancellationToken);
            var user = _accounts.GetBySubject(subject.SubjectId);
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
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }
}
