using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Boosters;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/participation/codex")]
public sealed class CodexParticipationController : ControllerBase
{
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;
    private readonly BoostSessionService _sessions;

    public CodexParticipationController(AccountService accounts, HubIdentityClient identity, BoostSessionService sessions)
    {
        _accounts = accounts;
        _identity = identity;
        _sessions = sessions;
    }

    [HttpGet("/participate/codex")]
    [Produces("text/html")]
    public ContentResult ParticipationPage()
    {
        var html = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Codex Participation</title>
  <style>
    body { font-family: Georgia, serif; background: linear-gradient(180deg, #f4efe3 0%, #e6dcc3 100%); color: #1e1b16; margin: 0; }
    main { max-width: 920px; margin: 0 auto; padding: 32px 20px 60px; }
    h1, h2 { margin: 0 0 12px; }
    .panel { background: rgba(255,255,255,0.75); border: 1px solid rgba(30,27,22,0.12); border-radius: 16px; padding: 18px; margin: 16px 0; box-shadow: 0 8px 20px rgba(30,27,22,0.08); }
    label { display: block; margin: 12px 0 6px; font-weight: 600; }
    input { width: 100%; padding: 10px 12px; border-radius: 10px; border: 1px solid rgba(30,27,22,0.2); background: #fffaf0; }
    button { margin: 8px 8px 0 0; padding: 10px 14px; border-radius: 999px; border: 0; background: #1f5f4a; color: white; cursor: pointer; }
    button.secondary { background: #7a5532; }
    .muted { color: #5d564e; }
    .codebox { font-family: monospace; font-size: 1.1rem; background: #1e1b16; color: #f8f2e6; padding: 12px; border-radius: 12px; }
    pre { white-space: pre-wrap; word-break: break-word; background: #fff8eb; padding: 12px; border-radius: 12px; border: 1px solid rgba(30,27,22,0.12); }
  </style>
</head>
<body>
  <main>
    <h1>Codex Participation</h1>
    <p class="muted">Hub owns the user, group, and ledger truth. Fleet opens the sponsored worker lane. Jury still lands the result.</p>

    <section class="panel">
      <h2>How This Works</h2>
      <ol>
        <li>Fleet keeps the cheap groundwork loop as the default path.</li>
        <li>If you consent, Hub opens a sponsor session on the community plane and asks Fleet to create a temporary participant burst lane.</li>
        <li>Fleet runs <code>codex login --device-auth</code> on the worker host and returns a verification URL plus one-time code.</li>
        <li>Your auth cache stays lane-local on Fleet. Hub stores product metadata, receipts, rewards, and entitlements.</li>
        <li>Premium work still lands through review and jury. Your lane never merges independently.</li>
      </ol>
      <p><a href="https://developers.openai.com/codex/auth/" target="_blank" rel="noreferrer">OpenAI Codex auth documentation</a></p>
    </section>

    <section class="panel">
      <h2>Consent</h2>
      <label for="accessToken">Bearer access token</label>
      <input id="accessToken" placeholder="Paste a Hub access token from the identity surface" />
      <label for="subjectId">Hub subject id</label>
      <input id="subjectId" placeholder="subject-123" />
      <label for="subjectLabel">Display label</label>
      <input id="subjectLabel" placeholder="Archon" />
      <label for="projectId">Project id</label>
      <input id="projectId" value="fleet" />
      <label for="groupId">Existing group id</label>
      <input id="groupId" placeholder="optional grp-..." />
      <label for="boostCode">Boost code</label>
      <input id="boostCode" placeholder="optional BOOST-..." />
      <label><input id="consent1" type="checkbox" /> I understand my ChatGPT/Codex entitlement will be used for project work.</label>
      <label><input id="consent2" type="checkbox" /> I understand this creates a temporary worker lane.</label>
      <label><input id="consent3" type="checkbox" /> I understand final merge is still controlled by Fleet review and jury.</label>
      <label><input id="consent4" type="checkbox" /> I want to participate.</label>
      <div>
        <button onclick="createIntent()">Create Intent</button>
        <button class="secondary" onclick="recordConsent()">Record Consent</button>
        <button onclick="startAuth()">Start Device Auth</button>
        <button onclick="activateLane()">Activate Lane</button>
        <button class="secondary" onclick="refreshIntent()">Refresh</button>
        <button class="secondary" onclick="stopLane()">Stop</button>
        <button class="secondary" onclick="revokeLane()">Revoke</button>
      </div>
    </section>

    <section class="panel">
      <h2>Current Intent</h2>
      <pre id="intentState">No intent created yet.</pre>
    </section>

    <section class="panel">
      <h2>Device Auth</h2>
      <div class="codebox" id="deviceCode">No device code issued yet.</div>
      <pre id="deviceState">Waiting for Fleet lane state.</pre>
    </section>
  </main>

  <script>
    let currentIntentId = "";

    function headers() {
      const token = document.getElementById("accessToken").value.trim();
      const headers = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      return headers;
    }

    async function api(path, options = {}) {
      const response = await fetch(path, { headers: headers(), ...options });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || JSON.stringify(data));
      return data;
    }

    function consentReady() {
      return ["consent1", "consent2", "consent3", "consent4"].every(id => document.getElementById(id).checked);
    }

    async function createIntent() {
      const payload = {
        subjectId: document.getElementById("subjectId").value,
        subjectLabel: document.getElementById("subjectLabel").value,
        projectId: document.getElementById("projectId").value,
        groupId: document.getElementById("groupId").value || null,
        boostCode: document.getElementById("boostCode").value || null
      };
      const data = await api("/api/v1/participation/intents", { method: "POST", body: JSON.stringify(payload) });
      currentIntentId = data.intent.intentId || data.intent.sponsorSessionId || "";
      render(data);
    }

    async function recordConsent() {
      if (!currentIntentId) return;
      if (!consentReady()) throw new Error("all consent checkboxes must be checked");
      const data = await api(`/api/v1/participation/intents/${currentIntentId}/consent`, { method: "POST" });
      render(data);
    }

    async function startAuth() {
      if (!currentIntentId) return;
      const data = await api(`/api/v1/participation/intents/${currentIntentId}/device-auth/start`, { method: "POST" });
      render(data);
    }

    async function activateLane() {
      if (!currentIntentId) return;
      const data = await api(`/api/v1/participation/intents/${currentIntentId}/activate`, { method: "POST" });
      render(data);
    }

    async function refreshIntent() {
      if (!currentIntentId) return;
      const data = await api(`/api/v1/participation/intents/${currentIntentId}`);
      render(data);
    }

    async function stopLane() {
      if (!currentIntentId) return;
      const data = await api(`/api/v1/participation/intents/${currentIntentId}/stop`, { method: "POST" });
      render(data);
    }

    async function revokeLane() {
      if (!currentIntentId) return;
      const data = await api(`/api/v1/participation/intents/${currentIntentId}`, { method: "DELETE" });
      render(data);
    }

    function render(data) {
      const intent = data.intent || data.sponsorSession || {};
      const fleet = data.fleet || {};
      currentIntentId = intent.intentId || intent.sponsorSessionId || currentIntentId;
      document.getElementById("intentState").textContent = JSON.stringify(intent, null, 2);
      const lane = fleet.lane || {};
      const auth = lane.device_auth || {};
      document.getElementById("deviceCode").textContent = auth.user_code || intent.deviceAuthUserCode || "No device code issued yet.";
      document.getElementById("deviceState").textContent = JSON.stringify({ lane, deviceAuth: auth, sponsorSession: data.sponsorSession || null }, null, 2);
    }
  </script>
</body>
</html>
""";
        return Content(html, "text/html");
    }

    [HttpPost("intents")]
    [HttpPost("/api/v1/participation/intents")]
    public async Task<ActionResult<object>> CreateIntent([FromBody] CreateCodexParticipationIntentRequest? request, CancellationToken cancellationToken)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.ProjectId))
        {
            return BadRequest("subjectId and projectId are required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            var session = _sessions.Create(new CreateSponsorSessionRequest(
                SubjectId: subject.SubjectId,
                ProjectId: request.ProjectId,
                GroupId: request.GroupId,
                SubjectLabel: request.SubjectLabel,
                BoostCode: request.BoostCode,
                CampaignId: request.CampaignId,
                Visibility: request.Visibility ?? "group",
                RequestedLaneType: request.RequestedLaneType ?? "participant_burst"));
            return Ok(BuildIntentEnvelope(session));
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

    [HttpPost("intents/{intentId}/consent")]
    [HttpPost("/api/v1/participation/intents/{intentId}/consent")]
    public async Task<ActionResult<object>> RecordConsent([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var ownedSession = TryGetOwnedSession(intentId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (ownedSession is null)
            {
                return NotFound();
            }

            var session = _sessions.RecordConsent(intentId);
            return Ok(BuildIntentEnvelope(session));
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

    [HttpPost("intents/{intentId}/device-auth/start")]
    [HttpPost("/api/v1/participation/intents/{intentId}/device-auth/start")]
    public async Task<ActionResult<object>> StartDeviceAuth([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(intentId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var result = await _sessions.StartDeviceAuthAsync(intentId, cancellationToken);
            return Ok(BuildIntentEnvelope(result.Session, result.Fleet));
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

    [HttpPost("intents/{intentId}/activate")]
    [HttpPost("/api/v1/participation/intents/{intentId}/activate")]
    public async Task<ActionResult<object>> ActivateLane([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(intentId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var result = await _sessions.ActivateAsync(intentId, cancellationToken);
            return Ok(BuildIntentEnvelope(result.Session, result.Fleet));
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

    [HttpGet("intents/{intentId}")]
    [HttpGet("/api/v1/participation/intents/{intentId}")]
    public async Task<ActionResult<object>> GetIntent([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(intentId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            return session is null ? NotFound() : Ok(BuildIntentEnvelope(session));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpGet("intents/{intentId}/events")]
    [HttpGet("/api/v1/participation/intents/{intentId}/events")]
    public async Task<ActionResult<object>> GetEvents([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(intentId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            return Ok(new
            {
                intentId = session.SponsorSessionId,
                sponsorSessionId = session.SponsorSessionId,
                events = session.Events,
                fleet = (object?)null
            });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("intents/{intentId}/stop")]
    [HttpPost("/api/v1/participation/intents/{intentId}/stop")]
    public async Task<ActionResult<object>> StopIntent([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(intentId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var result = await _sessions.StopAsync(intentId, revoke: false, cancellationToken);
            return Ok(BuildIntentEnvelope(result.Session, result.Fleet));
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

    [HttpDelete("intents/{intentId}")]
    [HttpDelete("/api/v1/participation/intents/{intentId}")]
    public async Task<ActionResult<object>> DeleteIntent([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var session = TryGetOwnedSession(intentId, subject.SubjectId, out var denied);
            if (denied is not null)
            {
                return denied;
            }

            if (session is null)
            {
                return NotFound();
            }

            var result = await _sessions.StopAsync(intentId, revoke: true, cancellationToken);
            return Ok(BuildIntentEnvelope(result.Session, result.Fleet));
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

    // Keep the public participation surface on the canonical sponsor-session/community-ledger path.
    private static object BuildIntentEnvelope(SponsorSessionStatusDto session, JsonObject? fleet = null)
        => new
        {
            intent = new
            {
                intentId = session.SponsorSessionId,
                sponsorSessionId = session.SponsorSessionId,
                userId = session.UserId,
                groupId = session.GroupId,
                projectId = session.ProjectId,
                requestedLaneType = session.RequestedLaneType,
                visibility = session.Visibility,
                status = session.Status,
                consented = session.Consented,
                fleetLaneId = session.FleetLaneId,
                boostCampaignId = session.BoostCampaignId,
                boostCodeId = session.BoostCodeId,
                deviceAuthVerificationUri = session.DeviceAuthVerificationUri,
                deviceAuthUserCode = session.DeviceAuthUserCode,
                createdAtUtc = session.CreatedAtUtc,
                updatedAtUtc = session.UpdatedAtUtc,
                consentedAtUtc = session.ConsentedAtUtc,
                stoppedAtUtc = session.StoppedAtUtc,
                events = session.Events
            },
            sponsorSession = session,
            fleet
        };

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

public sealed record CreateCodexParticipationIntentRequest(
    string SubjectId,
    string? SubjectLabel,
    string ProjectId,
    string? GroupId = null,
    string? BoostCode = null,
    string? CampaignId = null,
    string? Visibility = null,
    string? RequestedLaneType = null);
