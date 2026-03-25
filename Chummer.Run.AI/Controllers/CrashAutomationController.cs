using Chummer.Run.AI.Services.Ops;
using Chummer.Control.Contracts.Support;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.AI.Controllers;

[ApiController]
[Route("api/v1/ai/support/crashes")]
public sealed class CrashAutomationController : ControllerBase
{
    private readonly IHubCrashAutomationClient _hub;

    public CrashAutomationController(IHubCrashAutomationClient hub)
    {
        _hub = hub;
    }

    [HttpGet("clusters")]
    [ProducesResponseType<CrashClusterListResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status503ServiceUnavailable)]
    public async Task<ActionResult<CrashClusterListResponse>> ListClusters(
        [FromQuery] string? status = null,
        CancellationToken cancellationToken = default)
    {
        try
        {
            return Ok(await _hub.ListCrashClustersAsync(status, cancellationToken).ConfigureAwait(false));
        }
        catch (Exception ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
    }

    [HttpGet("work-items")]
    [ProducesResponseType<CrashWorkItemListResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status503ServiceUnavailable)]
    public async Task<ActionResult<CrashWorkItemListResponse>> ListWorkItems(
        [FromQuery] string? status = null,
        [FromQuery] string? candidateOwnerRepo = null,
        CancellationToken cancellationToken = default)
    {
        try
        {
            return Ok(await _hub.ListCrashWorkItemsAsync(status, candidateOwnerRepo, cancellationToken).ConfigureAwait(false));
        }
        catch (Exception ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
    }
}
