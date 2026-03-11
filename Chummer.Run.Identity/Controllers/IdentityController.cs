using Chummer.Run.Contracts.Identity;
using Chummer.Run.Identity.Services;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Identity.Controllers;

[ApiController]
[Route("api/v1/identity")]
public sealed class IdentityController : ControllerBase
{
    private readonly IIdentityAccessService _identity;

    public IdentityController(IIdentityAccessService identity)
    {
        _identity = identity;
    }

    [HttpPost("sessions")]
    [ProducesResponseType<IdentitySessionIssueResponse>(StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<IdentitySessionIssueResponse> IssueSession([FromBody] IdentitySessionIssueRequest? request)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.SubjectId))
        {
            return BadRequest("subjectId is required.");
        }

        var issued = _identity.IssueSession(request);
        return CreatedAtAction(nameof(GetSubject), new { subjectId = issued.SubjectId }, issued);
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
}
