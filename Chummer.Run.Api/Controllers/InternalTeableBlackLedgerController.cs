using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class InternalTeableBlackLedgerController : ControllerBase
{
    private readonly TeableBlackLedgerWorldTickService _teableWorldTicks;
    private readonly IConfiguration _configuration;

    public InternalTeableBlackLedgerController(
        TeableBlackLedgerWorldTickService teableWorldTicks,
        IConfiguration configuration)
    {
        _teableWorldTicks = teableWorldTicks;
        _configuration = configuration;
    }

    [HttpGet("/api/internal/black-ledger/teable/world-ticks")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<TeableBlackLedgerWorldTickDashboard>(StatusCodes.Status200OK)]
    public async Task<ActionResult<TeableBlackLedgerWorldTickDashboard>> GetDashboard([FromQuery] bool sync = false, CancellationToken cancellationToken = default)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        if (sync)
        {
            await _teableWorldTicks.SyncAllAsync(cancellationToken);
        }

        return Ok(_teableWorldTicks.GetDashboard());
    }

    [HttpPost("/api/internal/black-ledger/teable/world-ticks/sync")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<TeableBlackLedgerWorldTickSyncResult>(StatusCodes.Status200OK)]
    public async Task<ActionResult<TeableBlackLedgerWorldTickSyncResult>> SyncAll(CancellationToken cancellationToken)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        return Ok(await _teableWorldTicks.SyncAllAsync(cancellationToken));
    }

    private ActionResult? RequireInternalAutomationAuth()
    {
        string expectedToken = (_configuration["FLEET_INTERNAL_API_TOKEN"] ?? string.Empty).Trim();
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
        if (!FixedTimeEquals(providedToken, expectedToken))
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "internal BLACK LEDGER automation authorization is required.");
        }

        return null;
    }

    private static bool FixedTimeEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.UTF8.GetBytes(left);
        byte[] rightBytes = Encoding.UTF8.GetBytes(right);
        return CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }
}
