using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class InternalTeableUsersController : ControllerBase
{
    private readonly TeableUserProjectionService _teableUsers;
    private readonly IConfiguration _configuration;

    public InternalTeableUsersController(
        TeableUserProjectionService teableUsers,
        IConfiguration configuration)
    {
        _teableUsers = teableUsers;
        _configuration = configuration;
    }

    [HttpGet("/api/internal/community/users/teable")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<TeableUserProjectionDashboard>(StatusCodes.Status200OK)]
    public async Task<ActionResult<TeableUserProjectionDashboard>> GetDashboard(
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
            await _teableUsers.SyncAllAsync(cancellationToken);
        }

        return Ok(_teableUsers.GetDashboard());
    }

    [HttpPost("/api/internal/community/users/teable/sync")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<TeableUserProjectionSyncResult>(StatusCodes.Status200OK)]
    public async Task<ActionResult<TeableUserProjectionSyncResult>> SyncAll(CancellationToken cancellationToken)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        return Ok(await _teableUsers.SyncAllAsync(cancellationToken));
    }

    private ActionResult? RequireInternalAutomationAuth()
    {
        string expectedToken = (_configuration["FLEET_INTERNAL_API_TOKEN"] ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(expectedToken))
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "internal community automation auth is not configured.");
        }

        string header = Request.Headers.Authorization.ToString();
        const string bearerPrefix = "Bearer ";
        if (!header.StartsWith(bearerPrefix, StringComparison.OrdinalIgnoreCase))
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "internal community automation authorization is required.");
        }

        string providedToken = header[bearerPrefix.Length..].Trim();
        if (!FixedTimeEquals(providedToken, expectedToken))
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "internal community automation authorization is required.");
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
