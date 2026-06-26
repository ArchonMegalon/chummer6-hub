using System.Security.Cryptography;
using System.Text;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class InternalTeableImportantWorkController : ControllerBase
{
    private readonly TeableImportantWorkService _importantWork;
    private readonly IConfiguration _configuration;

    public InternalTeableImportantWorkController(
        TeableImportantWorkService importantWork,
        IConfiguration configuration)
    {
        _importantWork = importantWork;
        _configuration = configuration;
    }

    [HttpGet("/api/internal/community/important-work/teable")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<TeableImportantWorkDashboard>(StatusCodes.Status200OK)]
    public async Task<ActionResult<TeableImportantWorkDashboard>> GetDashboard(
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
            await _importantWork.SyncAllAsync(cancellationToken);
        }

        return Ok(_importantWork.GetDashboard());
    }

    [HttpPost("/api/internal/community/important-work")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<ImportantWorkItemProjection>(StatusCodes.Status200OK)]
    public ActionResult<ImportantWorkItemProjection> Record([FromBody] ImportantWorkItemRequest request)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        return Ok(_importantWork.Record(request));
    }

    [HttpPost("/api/internal/community/important-work/teable/sync")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<TeableImportantWorkSyncResult>(StatusCodes.Status200OK)]
    public async Task<ActionResult<TeableImportantWorkSyncResult>> SyncAll(CancellationToken cancellationToken)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        return Ok(await _importantWork.SyncAllAsync(cancellationToken));
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
