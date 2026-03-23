using System.Text.Json;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/groups")]
public sealed class GroupsController : ControllerBase
{
    private readonly GroupService _groups;
    private readonly HubIdentityClient _identity;

    public GroupsController(GroupService groups, HubIdentityClient identity)
    {
        _groups = groups;
        _identity = identity;
    }

    [HttpGet("/groups")]
    [Produces("text/html")]
    public IActionResult GroupsPage() => Redirect("/account");

    [HttpGet("/groups/{groupId}")]
    [Produces("text/html")]
    public IActionResult GroupPage([FromRoute] string groupId) => Redirect("/account");

    [HttpGet]
    [ProducesResponseType(typeof(IReadOnlyList<GroupDto>), StatusCodes.Status200OK)]
    public async Task<ActionResult<IReadOnlyList<GroupDto>>> ListForSubject([FromQuery] string subjectId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, subjectId, cancellationToken);
            return Ok(_groups.ListGroupsForUser(subject.SubjectId));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("{groupId}")]
    [ProducesResponseType<GroupDto>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<GroupDto> GetGroup([FromRoute] string groupId)
    {
        var group = _groups.GetGroup(groupId);
        return group is null ? NotFound() : Ok(group);
    }

    [HttpPost]
    [ProducesResponseType<GroupDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<GroupDto>> Create([FromBody] CreateGroupRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("group payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_groups.CreateGroup(request with { SubjectId = subject.SubjectId }));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("{groupId}/join-codes")]
    [ProducesResponseType<JoinCodeDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<JoinCodeDto>> CreateJoinCode([FromRoute] string groupId, [FromBody] CreateJoinCodeRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("join-code payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_groups.CreateJoinCode(groupId, request with { SubjectId = subject.SubjectId }));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpPost("join")]
    [ProducesResponseType<GroupDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<GroupDto>> Join([FromBody] JoinGroupByCodeRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("join payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_groups.JoinGroup(request with { SubjectId = subject.SubjectId }));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException)
        {
            return BadRequest(ex.Message);
        }
    }
}
