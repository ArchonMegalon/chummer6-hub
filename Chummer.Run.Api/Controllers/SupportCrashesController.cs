using Chummer.Run.Api.Services.Support;
using Chummer.Control.Contracts.Support;
using Microsoft.AspNetCore.Mvc;
using System.Security.Cryptography;
using System.Text;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/support/crashes")]
public sealed class SupportCrashesController : ControllerBase
{
    private readonly CrashSupportService _crashSupport;
    private readonly IConfiguration _configuration;

    public SupportCrashesController(CrashSupportService crashSupport, IConfiguration configuration)
    {
        _crashSupport = crashSupport;
        _configuration = configuration;
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
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

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
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        return Ok(_crashSupport.ListClusters(status, fingerprint));
    }

    [HttpGet("work-items")]
    [ProducesResponseType<CrashWorkItemListResponse>(StatusCodes.Status200OK)]
    public ActionResult<CrashWorkItemListResponse> ListWorkItems(
        [FromQuery] string? status = null,
        [FromQuery] string? candidateOwnerRepo = null)
    {
        ActionResult? denied = RequireInternalAutomationAuth();
        if (denied is not null)
        {
            return denied;
        }

        return Ok(_crashSupport.ListWorkItems(status, candidateOwnerRepo));
    }

    private ActionResult? RequireInternalAutomationAuth()
    {
        string expectedToken = (_configuration["FLEET_INTERNAL_API_TOKEN"] ?? string.Empty).Trim();
        if (string.IsNullOrWhiteSpace(expectedToken))
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: "internal crash automation auth is not configured.");
        }

        string header = Request.Headers.Authorization.ToString();
        const string bearerPrefix = "Bearer ";
        if (!header.StartsWith(bearerPrefix, StringComparison.OrdinalIgnoreCase))
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "internal crash automation authorization is required.");
        }

        string providedToken = header[bearerPrefix.Length..].Trim();
        if (!FixedTimeEquals(providedToken, expectedToken))
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "internal crash automation authorization is required.");
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
