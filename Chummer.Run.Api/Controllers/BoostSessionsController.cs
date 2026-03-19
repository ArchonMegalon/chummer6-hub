using System.Text.Json;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Boosters;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/boost-sessions")]
public sealed class BoostSessionsController : ControllerBase
{
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;
    private readonly BoostSessionService _sessions;

    public BoostSessionsController(AccountService accounts, HubIdentityClient identity, BoostSessionService sessions)
    {
        _accounts = accounts;
        _identity = identity;
        _sessions = sessions;
    }

    [HttpGet("/boost")]
    [Produces("text/html")]
    public ContentResult BoostPage()
    {
        var html = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Boost the Mission</title>
  <style>
    body { font-family: Georgia, serif; background: linear-gradient(180deg,#efe6d2 0%,#ddd0b2 100%); color:#1f1b16; margin:0; }
    main { max-width: 980px; margin: 0 auto; padding: 32px 20px 56px; }
    .panel { background: rgba(255,255,255,.85); border: 1px solid rgba(31,27,22,.12); border-radius: 16px; padding: 18px; margin-bottom: 16px; }
    label { display:block; margin: 10px 0 6px; font-weight: 600; }
    input { width:100%; padding:10px 12px; border-radius:10px; border:1px solid rgba(31,27,22,.2); background:#fffaf0; }
    button { margin: 8px 8px 0 0; padding:10px 14px; border-radius:999px; border:0; background:#205d4a; color:#fff; cursor:pointer; }
    button.secondary { background:#7a5532; }
    pre { background:#fff8eb; padding:12px; border-radius:12px; overflow:auto; }
  </style>
</head>
<body>
  <main>
    <section class="panel">
      <h1>Boost the Mission</h1>
      <p>Hub owns the account, group, and ledger side. Fleet owns the sponsored worker lane. Jury still lands the result.</p>
    </section>
    <section class="panel">
      <h2>Create sponsor session</h2>
      <label for="accessToken">Bearer access token</label>
      <input id="accessToken" placeholder="Paste a Hub access token from the identity surface" />
      <label for="subjectId">Subject id</label>
      <input id="subjectId" placeholder="subject-123" />
      <label for="subjectLabel">Display name</label>
      <input id="subjectLabel" placeholder="Archon" />
      <label for="projectId">Project id</label>
      <input id="projectId" value="fleet" />
      <label for="groupId">Group id</label>
      <input id="groupId" placeholder="optional existing group" />
      <label for="boostCode">Boost code</label>
      <input id="boostCode" placeholder="optional BOOST-XXXX" />
      <button onclick="createSession()">Create sponsor session</button>
      <button class="secondary" onclick="recordConsent()">Record consent</button>
      <button onclick="startAuth()">Start device auth</button>
      <button onclick="activateSession()">Activate lane</button>
      <button class="secondary" onclick="stopSession()">Stop lane</button>
      <button class="secondary" onclick="revokeSession()">Revoke lane</button>
    </section>
    <section class="panel">
      <h2>Status</h2>
      <pre id="output">No sponsor session created yet.</pre>
    </section>
  </main>
  <script>
    let currentSessionId = '';
    function headers() {
      const token = document.getElementById('accessToken').value.trim();
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      return headers;
    }
    async function api(path, method, payload) {
      const response = await fetch(path, {
        method,
        headers: headers(),
        body: payload ? JSON.stringify(payload) : undefined
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || JSON.stringify(data));
      document.getElementById('output').textContent = JSON.stringify(data, null, 2);
      return data;
    }
    async function createSession() {
      const data = await api('/api/v1/boost-sessions', 'POST', {
        subjectId: subjectId.value,
        subjectLabel: subjectLabel.value,
        projectId: projectId.value,
        groupId: groupId.value || null,
        boostCode: boostCode.value || null,
        visibility: 'group',
        requestedLaneType: 'participant_burst'
      });
      currentSessionId = data.sponsorSessionId || data.sponsor_session_id || data.sponsorSession?.sponsorSessionId || data.sponsorSession?.sponsor_session_id || '';
    }
    async function recordConsent() { if (currentSessionId) await api(`/api/v1/boost-sessions/${currentSessionId}/consent`, 'POST'); }
    async function startAuth() { if (currentSessionId) await api(`/api/v1/boost-sessions/${currentSessionId}/device-auth/start`, 'POST'); }
    async function activateSession() { if (currentSessionId) await api(`/api/v1/boost-sessions/${currentSessionId}/activate`, 'POST'); }
    async function stopSession() { if (currentSessionId) await api(`/api/v1/boost-sessions/${currentSessionId}/stop`, 'POST'); }
    async function revokeSession() { if (currentSessionId) await api(`/api/v1/boost-sessions/${currentSessionId}`, 'DELETE'); }
  </script>
</body>
</html>
""";
        return Content(html, "text/html");
    }

    [HttpPost]
    [ProducesResponseType<SponsorSessionStatusDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<SponsorSessionStatusDto>> Create([FromBody] CreateSponsorSessionRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("boost-session payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_sessions.Create(request with { SubjectId = subject.SubjectId }));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (Exception ex) when (ex is KeyNotFoundException or InvalidOperationException or ArgumentException)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpGet("{sponsorSessionId}")]
    [ProducesResponseType<SponsorSessionStatusDto>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<SponsorSessionStatusDto>> Get([FromRoute] string sponsorSessionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(sponsorSessionId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            return session is null ? NotFound() : Ok(session);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("{sponsorSessionId}/consent")]
    [ProducesResponseType<SponsorSessionStatusDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<SponsorSessionStatusDto>> Consent([FromRoute] string sponsorSessionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(sponsorSessionId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            return Ok(_sessions.RecordConsent(sponsorSessionId));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
    }

    [HttpPost("{sponsorSessionId}/device-auth/start")]
    public async Task<ActionResult<object>> StartDeviceAuth([FromRoute] string sponsorSessionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(sponsorSessionId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var result = await _sessions.StartDeviceAuthAsync(sponsorSessionId, cancellationToken);
            return Ok(new { sponsorSession = result.Session, fleet = result.Fleet });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
        catch (Exception ex) when (ex is InvalidOperationException or ArgumentException)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpPost("{sponsorSessionId}/activate")]
    public async Task<ActionResult<object>> Activate([FromRoute] string sponsorSessionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(sponsorSessionId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var result = await _sessions.ActivateAsync(sponsorSessionId, cancellationToken);
            return Ok(new { sponsorSession = result.Session, fleet = result.Fleet });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
        catch (Exception ex) when (ex is InvalidOperationException or ArgumentException)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpPost("{sponsorSessionId}/stop")]
    public async Task<ActionResult<object>> Stop([FromRoute] string sponsorSessionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(sponsorSessionId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var result = await _sessions.StopAsync(sponsorSessionId, revoke: false, cancellationToken);
            return Ok(new { sponsorSession = result.Session, fleet = result.Fleet });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
        catch (Exception ex) when (ex is InvalidOperationException or ArgumentException)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpDelete("{sponsorSessionId}")]
    public async Task<ActionResult<object>> Revoke([FromRoute] string sponsorSessionId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(sponsorSessionId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var result = await _sessions.StopAsync(sponsorSessionId, revoke: true, cancellationToken);
            return Ok(new { sponsorSession = result.Session, fleet = result.Fleet });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
        catch (Exception ex) when (ex is InvalidOperationException or ArgumentException)
        {
            return BadRequest(ex.Message);
        }
    }

    private SponsorSessionStatusDto? TryGetOwnedSession(string sponsorSessionId, string subjectId, out ActionResult? denied)
    {
        denied = null;
        var session = _sessions.Get(sponsorSessionId);
        if (session is null)
        {
            return null;
        }

        var user = _accounts.EnsureUser(subjectId, subjectId);
        if (!string.Equals(session.UserId, user.UserId, StringComparison.OrdinalIgnoreCase))
        {
            denied = Problem(statusCode: StatusCodes.Status403Forbidden, detail: "sponsor session does not belong to the authenticated subject.");
            return null;
        }

        return session;
    }
}
