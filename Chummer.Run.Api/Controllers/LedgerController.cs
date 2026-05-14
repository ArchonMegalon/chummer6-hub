using System.Text.Json;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Ledger;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.DependencyInjection;
using System.Security.Cryptography;
using System.Text;

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
    private readonly BlackLedgerPublicStatsService _blackLedgerPublicStats;

    public LedgerController(AccountService accounts, HubIdentityClient identity, LedgerService ledger, FleetReceiptVerifier receiptVerifier, RewardService rewards, BlackLedgerPublicStatsService blackLedgerPublicStats)
    {
        _accounts = accounts;
        _identity = identity;
        _ledger = ledger;
        _receiptVerifier = receiptVerifier;
        _rewards = rewards;
        _blackLedgerPublicStats = blackLedgerPublicStats;
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

    [HttpGet("worlds/{worldId}")]
    [Produces("application/json")]
    public async Task<ActionResult<object>> GetBlackLedgerWorld([FromRoute] string worldId, [FromQuery] string subjectId, [FromQuery] int? turn, CancellationToken cancellationToken)
    {
        if (!string.Equals(worldId, "emerald-sprawl-prelude", StringComparison.OrdinalIgnoreCase))
        {
            return NotFound();
        }

        try
        {
            await _identity.RequireMatchingSubjectAsync(Request, subjectId, cancellationToken);
            var world = _blackLedgerPublicStats.LoadWorldPreview(turn);
            if (world is null)
            {
                return NotFound();
            }

            return Ok(new
            {
                world.WorldId,
                world.PublicName,
                world.Status,
                world.CurrentTurn,
                world.DeterministicPreview,
                world.TurnHeadline,
                world.SafetyNote,
                world.MapNote,
                world.Districts,
                world.Factions,
                world.StewardshipPosts,
                world.StewardshipTransferPreview,
                world.LastTick,
            });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("worlds/{worldId}/ticks")]
    [Produces("application/json")]
    public ActionResult<object> MaterializeDeterministicBlackLedgerTick([FromRoute] string worldId, [FromQuery] int turn = 2)
    {
        if (!string.Equals(worldId, "emerald-sprawl-prelude", StringComparison.OrdinalIgnoreCase))
        {
            return NotFound();
        }

        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        var world = _blackLedgerPublicStats.LoadWorldPreview(turn);
        if (world?.LastTick is null || !world.DeterministicPreview)
        {
            return NotFound();
        }

        return Ok(new
        {
            receipt_type = "world_tick_receipt",
            world.WorldId,
            turn = world.LastTick.Turn,
            world.LastTick.ReceiptId,
            world.LastTick.Mode,
            world.LastTick.InputStateHash,
            world.LastTick.DecisionPacketHash,
            world.LastTick.PrivacyPassed,
            world.LastTick.BlockedFields,
            world.LastTick.OutputStateHash,
            world.LastTick.CreatedAtUtc,
            world.LastTick.Effects,
        });
    }

    private ActionResult? RequireInternalAutomationAuth()
    {
        string expectedToken = (HttpContext.RequestServices.GetRequiredService<IConfiguration>()["FLEET_INTERNAL_API_TOKEN"] ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(expectedToken))
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "internal BLACK LEDGER automation auth is not configured.");
        }

        string header = Request.Headers.Authorization.ToString();
        const string bearerPrefix = "Bearer ";
        if (!header.StartsWith(bearerPrefix, StringComparison.OrdinalIgnoreCase))
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "internal BLACK LEDGER automation authorization is required.");
        }

        string providedToken = header[bearerPrefix.Length..].Trim();
        return FixedTimeEquals(providedToken, expectedToken)
            ? null
            : Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "internal BLACK LEDGER automation authorization is required.");
    }

    private static bool FixedTimeEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.UTF8.GetBytes(left);
        byte[] rightBytes = Encoding.UTF8.GetBytes(right);
        return CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }
}
