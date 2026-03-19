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
    public ContentResult GroupsPage()
    {
        var html = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hub Groups</title>
  <style>
    body { font-family: Georgia, serif; background: #efe7d6; color: #1f1b16; margin: 0; }
    main { max-width: 960px; margin: 0 auto; padding: 32px 20px 48px; }
    .panel { background: rgba(255,255,255,.88); border: 1px solid rgba(31,27,22,.12); border-radius: 14px; padding: 18px; margin-bottom: 16px; }
    label { display:block; margin: 10px 0 6px; font-weight: 600; }
    input { width:100%; padding:10px 12px; border-radius:10px; border:1px solid rgba(31,27,22,.2); }
    button { margin-top: 12px; padding: 10px 14px; border-radius:999px; border:0; background:#5a3b21; color:#fff; cursor:pointer; }
    pre { background:#fff7ec; padding:12px; border-radius:12px; overflow:auto; }
  </style>
</head>
<body>
  <main>
    <section class="panel">
      <h1>Groups</h1>
      <p>Groups are generic social and authority containers. Booster groups today can become campaign or GM-circle groups later without schema drift.</p>
      <label for="accessToken">Bearer access token</label>
      <input id="accessToken" placeholder="Paste a Hub access token from the identity surface" />
      <label for="subjectId">Subject id</label>
      <input id="subjectId" placeholder="subject-123" />
      <label for="groupName">Group name</label>
      <input id="groupName" placeholder="Tuesday Boosters" />
      <button onclick="createGroup()">Create group</button>
      <label for="joinCode">Join code</label>
      <input id="joinCode" placeholder="JOIN-ABC123" />
      <button onclick="joinGroup()">Join by code</button>
    </section>
    <section class="panel">
      <h2>Result</h2>
      <pre id="output">No group action yet.</pre>
    </section>
  </main>
  <script>
    function headers() {
      const token = document.getElementById('accessToken').value.trim();
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      return headers;
    }
    async function createGroup() {
      const response = await fetch('/api/v1/groups', {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({ subjectId: subjectId.value, name: groupName.value, groupType: 'booster', visibility: 'group' })
      });
      const data = await response.json();
      document.getElementById('output').textContent = JSON.stringify(data, null, 2);
    }
    async function joinGroup() {
      const response = await fetch('/api/v1/groups/join', {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({ subjectId: subjectId.value, code: joinCode.value })
      });
      const data = await response.json();
      document.getElementById('output').textContent = JSON.stringify(data, null, 2);
    }
  </script>
</body>
</html>
""";
        return Content(html, "text/html");
    }

    [HttpGet("/groups/{groupId}")]
    [Produces("text/html")]
    public ContentResult GroupPage([FromRoute] string groupId)
    {
        var group = _groups.GetGroup(groupId);
        var json = JsonSerializer.Serialize(group, new JsonSerializerOptions { WriteIndented = true });
        var html = $"""
<!doctype html>
<html lang="en">
<head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" /><title>Group</title></head>
<body style="font-family:Georgia,serif;background:#f5efe2;color:#1f1b16;padding:24px;">
  <h1>Group</h1>
  <pre style="background:white;padding:16px;border-radius:12px;border:1px solid rgba(31,27,22,.12);">{System.Net.WebUtility.HtmlEncode(json)}</pre>
</body>
</html>
""";
        return Content(html, "text/html");
    }

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
