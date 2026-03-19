using Chummer.Run.Contracts.Identity;
using Chummer.Run.Identity.Services;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Identity.Controllers;

[ApiController]
[Route("api/v1/identity")]
public sealed class IdentityController : ControllerBase
{
    private readonly IIdentityAccessService _identity;
    private readonly IConfiguration _configuration;

    public IdentityController(IIdentityAccessService identity, IConfiguration configuration)
    {
        _identity = identity;
        _configuration = configuration;
    }

    [HttpPost("sessions")]
    [ProducesResponseType<IdentitySessionIssueResponse>(StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<IdentitySessionIssueResponse> IssueSession([FromBody] IdentitySessionIssueRequest? request)
    {
        if (!IsAdminRouteAuthorized())
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: "identity session issuance is reserved for internal or admin callers.");
        }

        if (request is null || string.IsNullOrWhiteSpace(request.SubjectId))
        {
            return BadRequest("subjectId is required.");
        }

        var issued = _identity.IssueSession(request);
        return CreatedAtAction(nameof(GetSubject), new { subjectId = issued.SubjectId }, issued);
    }

    [HttpPost("email/start")]
    [ProducesResponseType<EmailAuthStartResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<EmailAuthStartResponse> StartEmailEntry([FromBody] EmailAuthStartRequest? request)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.Email))
        {
            return BadRequest("email is required.");
        }

        return Ok(_identity.StartEmailEntry(request));
    }

    [HttpPost("email/complete")]
    [ProducesResponseType<IdentitySessionIssueResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<IdentitySessionIssueResponse> CompleteEmailEntry([FromBody] EmailAuthCompleteRequest? request)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.TicketId))
        {
            return BadRequest("ticketId is required.");
        }

        try
        {
            return Ok(_identity.CompleteEmailEntry(request));
        }
        catch (Exception ex) when (ex is KeyNotFoundException or ArgumentException)
        {
            return Problem(statusCode: StatusCodes.Status400BadRequest, detail: ex.Message);
        }
    }

    [HttpGet("subjects/{subjectId}")]
    [ProducesResponseType<IdentitySubjectResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<IdentitySubjectResponse> GetSubject([FromRoute] string subjectId)
    {
        if (string.IsNullOrWhiteSpace(subjectId))
        {
            return BadRequest("subjectId is required.");
        }

        var subject = _identity.GetSubject(subjectId);
        return subject is null ? NotFound() : Ok(subject);
    }

    [HttpPut("subjects/{subjectId}/roles")]
    [ProducesResponseType<IdentitySubjectResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<IdentitySubjectResponse> SetRoles(
        [FromRoute] string subjectId,
        [FromBody] IdentityRoleSetRequest? request)
    {
        if (!IsAdminRouteAuthorized())
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: "identity role mutation is reserved for internal or admin callers.");
        }

        if (string.IsNullOrWhiteSpace(subjectId))
        {
            return BadRequest("subjectId is required.");
        }

        if (request is null || request.Roles is null)
        {
            return BadRequest("roles are required.");
        }

        return Ok(_identity.SetRoles(subjectId, request));
    }

    [HttpPost("sessions/revoke")]
    [ProducesResponseType<IdentitySessionRevokeResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<IdentitySessionRevokeResponse> RevokeSession([FromBody] IdentitySessionRevokeRequest? request)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.AccessToken))
        {
            return BadRequest("accessToken is required.");
        }

        return Ok(_identity.RevokeSession(request));
    }

    [HttpPost("introspect")]
    [ProducesResponseType<IdentityIntrospectionResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<IdentityIntrospectionResponse> Introspect([FromBody] IdentityIntrospectionRequest? request)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.AccessToken))
        {
            return BadRequest("accessToken is required.");
        }

        return Ok(_identity.Introspect(request));
    }

    private bool IsAdminRouteAuthorized()
    {
        var configuredKey = _configuration["IDENTITY_ADMIN_KEY"];
        if (string.IsNullOrWhiteSpace(configuredKey))
        {
            return false;
        }

        if (!Request.Headers.TryGetValue("X-Identity-Admin-Key", out var supplied))
        {
            return false;
        }

        return string.Equals(supplied.ToString(), configuredKey, StringComparison.Ordinal);
    }
}
