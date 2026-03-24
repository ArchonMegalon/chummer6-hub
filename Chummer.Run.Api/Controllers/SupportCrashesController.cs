using Chummer.Run.Api.Services.Support;
using Chummer.Run.Contracts.Support;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/support/crashes")]
public sealed class SupportCrashesController : ControllerBase
{
    private readonly CrashSupportService _crashSupport;

    public SupportCrashesController(CrashSupportService crashSupport)
    {
        _crashSupport = crashSupport;
    }

    [HttpPost]
    [ProducesResponseType<CrashIntakeAcceptedResponse>(StatusCodes.Status202Accepted)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<CrashIntakeAcceptedResponse> Submit([FromBody] CrashEnvelope? envelope)
    {
        if (envelope is null)
        {
            return BadRequest("crash envelope is required.");
        }

        CrashIntakeAcceptedResponse accepted = _crashSupport.Submit(envelope);
        return AcceptedAtAction(
            nameof(GetIncident),
            new { incidentId = accepted.Incident.IncidentId },
            accepted);
    }

    [HttpGet("incidents/{incidentId}")]
    [ProducesResponseType<CrashIncidentProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<CrashIncidentProjection> GetIncident([FromRoute] string incidentId)
    {
        if (string.IsNullOrWhiteSpace(incidentId))
        {
            return BadRequest("incidentId is required.");
        }

        CrashIncidentProjection? incident = _crashSupport.GetIncident(incidentId);
        return incident is null ? NotFound() : Ok(incident);
    }

    [HttpGet("clusters")]
    [ProducesResponseType<CrashClusterListResponse>(StatusCodes.Status200OK)]
    public ActionResult<CrashClusterListResponse> ListClusters(
        [FromQuery] string? status = null,
        [FromQuery] string? fingerprint = null)
        => Ok(_crashSupport.ListClusters(status, fingerprint));

    [HttpGet("work-items")]
    [ProducesResponseType<CrashWorkItemListResponse>(StatusCodes.Status200OK)]
    public ActionResult<CrashWorkItemListResponse> ListWorkItems(
        [FromQuery] string? status = null,
        [FromQuery] string? candidateOwnerRepo = null)
        => Ok(_crashSupport.ListWorkItems(status, candidateOwnerRepo));
}
