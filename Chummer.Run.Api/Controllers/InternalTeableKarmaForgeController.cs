using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services.KarmaForge;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class InternalTeableKarmaForgeController : ControllerBase
{
    private readonly TeableKarmaForgeReviewBoardService _teableReviewBoard;
    private readonly IConfiguration _configuration;

    public InternalTeableKarmaForgeController(
        TeableKarmaForgeReviewBoardService teableReviewBoard,
        IConfiguration configuration)
    {
        _teableReviewBoard = teableReviewBoard;
        _configuration = configuration;
    }

    [HttpGet("/api/internal/karma-forge/teable")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<TeableKarmaForgeReviewBoardDashboard>(StatusCodes.Status200OK)]
    public async Task<ActionResult<TeableKarmaForgeReviewBoardDashboard>> GetDashboard(
        [FromQuery] bool sync = false,
        CancellationToken cancellationToken = default)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        if (sync)
        {
            await _teableReviewBoard.SyncAllAsync(cancellationToken);
        }

        return Ok(_teableReviewBoard.GetDashboard());
    }

    [HttpPost("/api/internal/karma-forge/teable/sync")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<TeableKarmaForgeReviewBoardSyncResult>(StatusCodes.Status200OK)]
    public async Task<ActionResult<TeableKarmaForgeReviewBoardSyncResult>> SyncAll(CancellationToken cancellationToken)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        return Ok(await _teableReviewBoard.SyncAllAsync(cancellationToken));
    }

    private ActionResult? RequireInternalAutomationAuth()
    {
        string expectedToken = (_configuration["FLEET_INTERNAL_API_TOKEN"] ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(expectedToken))
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "internal KARMA FORGE automation auth is not configured.");
        }

        string header = Request.Headers.Authorization.ToString();
        const string bearerPrefix = "Bearer ";
        if (!header.StartsWith(bearerPrefix, StringComparison.OrdinalIgnoreCase))
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "internal KARMA FORGE automation authorization is required.");
        }

        string providedToken = header[bearerPrefix.Length..].Trim();
        if (!FixedTimeEquals(providedToken, expectedToken))
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "internal KARMA FORGE automation authorization is required.");
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
