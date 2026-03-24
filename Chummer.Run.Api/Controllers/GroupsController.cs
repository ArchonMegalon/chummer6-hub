using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[AutoValidateAntiforgeryToken]
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
    [ProducesResponseType(StatusCodes.Status403Forbidden)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<GroupDto>> GetGroup([FromRoute] string groupId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var group = _groups.GetGroup(groupId);
            if (group is null)
            {
                return NotFound();
            }

            var visibleGroup = _groups.ListGroupsForUser(subject.SubjectId)
                .FirstOrDefault(item => string.Equals(item.GroupId, groupId, StringComparison.OrdinalIgnoreCase));
            if (visibleGroup is null)
            {
                return Problem(statusCode: StatusCodes.Status403Forbidden, detail: "group does not belong to the authenticated subject.");
            }

            return Ok(visibleGroup);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
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
        catch (CommunityAccessDeniedException ex)
        {
            return Problem(statusCode: StatusCodes.Status403Forbidden, detail: ex.Message);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException)
        {
            return CommunityApiProblemMapper.FromException(this, ex);
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
            return CommunityApiProblemMapper.FromException(this, ex);
        }
    }
}
