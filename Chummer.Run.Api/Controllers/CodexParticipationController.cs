using System.Text.Json.Nodes;
using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/participation/codex")]
public sealed class CodexParticipationController : ControllerBase
{
    private readonly CodexParticipationService _participation;
    private readonly FleetBridgeService _fleetBridge;

    public CodexParticipationController(CodexParticipationService participation, FleetBridgeService fleetBridge)
    {
        _participation = participation;
        _fleetBridge = fleetBridge;
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
    <p class="muted">Cheap groundwork remains the baseline. Premium burst lanes are opened only when a human explicitly sponsors them, and final landing still goes through Fleet review and jury.</p>

    <section class="panel">
      <h2>How This Works</h2>
      <ol>
        <li>Fleet keeps the cheap groundwork loop as the default path.</li>
        <li>If you consent, Hub asks Fleet to open a temporary participant burst lane on your behalf.</li>
        <li>Fleet runs <code>codex login --device-auth</code> on the worker host and returns a verification URL plus one-time code.</li>
        <li>Your auth cache stays lane-local on Fleet. Hub records participation metadata only.</li>
        <li>Premium work still lands through review and jury. Your lane never merges independently.</li>
      </ol>
      <p><a href="https://developers.openai.com/codex/auth/" target="_blank" rel="noreferrer">OpenAI Codex auth documentation</a></p>
    </section>

    <section class="panel">
      <h2>Consent</h2>
      <label for="subjectId">Hub subject id</label>
      <input id="subjectId" placeholder="subject-123" />
      <label for="subjectLabel">Display label</label>
      <input id="subjectLabel" placeholder="Archon" />
      <label for="projectId">Project id</label>
      <input id="projectId" value="fleet" />
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

    async function api(path, options = {}) {
      const response = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
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
        projectId: document.getElementById("projectId").value
      };
      const data = await api("/api/v1/participation/codex/intents", { method: "POST", body: JSON.stringify(payload) });
      currentIntentId = data.intent.intentId;
      render(data);
    }

    async function recordConsent() {
      if (!currentIntentId) return;
      if (!consentReady()) throw new Error("all consent checkboxes must be checked");
      const data = await api(`/api/v1/participation/codex/intents/${currentIntentId}/consent`, { method: "POST" });
      render(data);
    }

    async function startAuth() {
      if (!currentIntentId) return;
      const data = await api(`/api/v1/participation/codex/intents/${currentIntentId}/device-auth/start`, { method: "POST" });
      render(data);
    }

    async function activateLane() {
      if (!currentIntentId) return;
      const data = await api(`/api/v1/participation/codex/intents/${currentIntentId}/activate`, { method: "POST" });
      render(data);
    }

    async function refreshIntent() {
      if (!currentIntentId) return;
      const data = await api(`/api/v1/participation/codex/intents/${currentIntentId}`);
      render(data);
    }

    async function stopLane() {
      if (!currentIntentId) return;
      const data = await api(`/api/v1/participation/codex/intents/${currentIntentId}/stop`, { method: "POST" });
      render(data);
    }

    async function revokeLane() {
      if (!currentIntentId) return;
      const data = await api(`/api/v1/participation/codex/intents/${currentIntentId}`, { method: "DELETE" });
      render(data);
    }

    function render(data) {
      const intent = data.intent || {};
      const fleet = data.fleet || {};
      currentIntentId = intent.intentId || currentIntentId;
      document.getElementById("intentState").textContent = JSON.stringify(intent, null, 2);
      const lane = fleet.lane || {};
      const auth = lane.device_auth || {};
      document.getElementById("deviceCode").textContent = auth.user_code || "No device code issued yet.";
      document.getElementById("deviceState").textContent = JSON.stringify({ lane, deviceAuth: auth }, null, 2);
    }
  </script>
</body>
</html>
""";
        return Content(html, "text/html");
    }

    [HttpPost("intents")]
    public ActionResult<object> CreateIntent([FromBody] CreateCodexParticipationIntentRequest? request)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.SubjectId) || string.IsNullOrWhiteSpace(request.ProjectId))
        {
            return BadRequest("subjectId and projectId are required.");
        }

        var intent = _participation.CreateIntent(request.SubjectId, request.SubjectLabel ?? request.SubjectId, request.ProjectId);
        return Ok(new { intent });
    }

    [HttpPost("intents/{intentId}/consent")]
    public ActionResult<object> RecordConsent([FromRoute] string intentId)
    {
        try
        {
            var intent = _participation.RecordConsent(intentId);
            return Ok(new { intent });
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
    }

    [HttpPost("intents/{intentId}/device-auth/start")]
    public async Task<ActionResult<object>> StartDeviceAuth([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        var intent = _participation.GetIntent(intentId);
        if (intent is null)
        {
            return NotFound();
        }

        if (!intent.Consented)
        {
            return BadRequest("consent is required before device auth can start.");
        }

        JsonObject fleet;
        if (string.IsNullOrWhiteSpace(intent.FleetLaneId))
        {
            var created = await _fleetBridge.CreateParticipantLaneAsync(
                intent.SubjectId,
                intent.SubjectLabel,
                intent.ProjectId,
                "",
                "",
                "",
                intent.IntentId,
                "private",
                cancellationToken);
            var laneId = created["lane"]?["lane_id"]?.GetValue<string>() ?? "";
            intent = _participation.AttachFleetLane(intent.IntentId, laneId, $"Fleet lane {laneId} created.");
        }

        fleet = await _fleetBridge.StartDeviceAuthAsync(intent.FleetLaneId!, cancellationToken);
        intent = _participation.RecordStatus(intent.IntentId, "pending_auth", "Device auth started on Fleet.");
        return Ok(new { intent, fleet });
    }

    [HttpPost("intents/{intentId}/activate")]
    public async Task<ActionResult<object>> ActivateLane([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        var intent = _participation.GetIntent(intentId);
        if (intent is null)
        {
            return NotFound();
        }

        if (string.IsNullOrWhiteSpace(intent.FleetLaneId))
        {
            return BadRequest("no Fleet lane exists for this intent.");
        }

        var fleet = await _fleetBridge.ActivateParticipantLaneAsync(intent.FleetLaneId, cancellationToken);
        intent = _participation.RecordStatus(intent.IntentId, "active", "Participant lane activated.");
        return Ok(new { intent, fleet });
    }

    [HttpGet("intents/{intentId}")]
    public async Task<ActionResult<object>> GetIntent([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        var intent = _participation.GetIntent(intentId);
        if (intent is null)
        {
            return NotFound();
        }

        JsonObject? fleet = null;
        if (!string.IsNullOrWhiteSpace(intent.FleetLaneId))
        {
            fleet = await _fleetBridge.GetParticipantLaneAsync(intent.FleetLaneId, cancellationToken);
        }

        return Ok(new { intent, fleet });
    }

    [HttpGet("intents/{intentId}/events")]
    public async Task<ActionResult<object>> GetEvents([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        var intent = _participation.GetIntent(intentId);
        if (intent is null)
        {
            return NotFound();
        }

        JsonObject? fleet = null;
        if (!string.IsNullOrWhiteSpace(intent.FleetLaneId))
        {
            fleet = await _fleetBridge.GetParticipantLaneAsync(intent.FleetLaneId, cancellationToken);
        }

        return Ok(new
        {
            intentId = intent.IntentId,
            events = _participation.GetEvents(intent.IntentId),
            fleet
        });
    }

    [HttpPost("intents/{intentId}/stop")]
    public async Task<ActionResult<object>> StopIntent([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        var intent = _participation.GetIntent(intentId);
        if (intent is null)
        {
            return NotFound();
        }

        JsonObject? fleet = null;
        if (!string.IsNullOrWhiteSpace(intent.FleetLaneId))
        {
            fleet = await _fleetBridge.StopParticipantLaneAsync(intent.FleetLaneId, cancellationToken);
        }

        intent = _participation.RecordStatus(intent.IntentId, "stopped", "Participant lane stopped.");
        return Ok(new { intent, fleet });
    }

    [HttpDelete("intents/{intentId}")]
    public async Task<ActionResult<object>> DeleteIntent([FromRoute] string intentId, CancellationToken cancellationToken)
    {
        var intent = _participation.GetIntent(intentId);
        if (intent is null)
        {
            return NotFound();
        }

        JsonObject? fleet = null;
        if (!string.IsNullOrWhiteSpace(intent.FleetLaneId))
        {
            fleet = await _fleetBridge.DeleteParticipantLaneAsync(intent.FleetLaneId, cancellationToken);
        }

        intent = _participation.RecordRevocation(intent.IntentId, "Participant lane revoked.");
        return Ok(new { intent, fleet });
    }
}

public sealed record CreateCodexParticipationIntentRequest(
    string SubjectId,
    string? SubjectLabel,
    string ProjectId);
