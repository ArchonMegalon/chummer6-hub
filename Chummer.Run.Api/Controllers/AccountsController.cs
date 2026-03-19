using System.Text.Json;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/accounts")]
public sealed class AccountsController : ControllerBase
{
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;

    public AccountsController(AccountService accounts, HubIdentityClient identity)
    {
        _accounts = accounts;
        _identity = identity;
    }

    [HttpGet("/account")]
    [Produces("text/html")]
    public ContentResult AccountPage()
    {
        var html = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Hub Account</title>
  <style>
    body { font-family: Georgia, serif; background: #f7f1e5; color: #1f1b16; margin: 0; }
    main { max-width: 920px; margin: 0 auto; padding: 32px 20px 48px; }
    .panel { background: white; border: 1px solid rgba(31,27,22,.12); border-radius: 14px; padding: 18px; margin-bottom: 16px; }
    label { display:block; margin: 10px 0 6px; font-weight: 600; }
    input { width:100%; padding:10px 12px; border-radius: 10px; border:1px solid rgba(31,27,22,.2); }
    select { width:100%; padding:10px 12px; border-radius: 10px; border:1px solid rgba(31,27,22,.2); }
    button { margin-top: 12px; padding: 10px 14px; border-radius: 999px; border: 0; background: #205d4a; color: #fff; cursor: pointer; }
    pre { background: #fbf7ef; padding: 12px; border-radius: 12px; overflow: auto; }
    .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
  </style>
</head>
<body>
  <main>
    <section class="panel">
      <h1>Hub Account</h1>
      <p>Hub keeps the product-level account, visibility, and group identity layer above raw identity subjects. In this preview, a bearer token is enough to load the matching account.</p>
      <label for="accessToken">Bearer access token</label>
      <input id="accessToken" placeholder="Paste a Hub access token from the identity surface" />
      <label for="displayName">Display name</label>
      <input id="displayName" placeholder="Archon" />
      <label for="handle">Handle</label>
      <input id="handle" placeholder="archon" />
      <label for="timezone">Timezone</label>
      <input id="timezone" value="Europe/Vienna" />
      <button onclick="loadAccount()">Load account</button>
      <button onclick="saveProfile()">Save profile</button>
    </section>
    <section class="panel">
      <h2>Linked identities and channels</h2>
      <p>Email verification is identity hygiene, social providers are auth adapters, Telegram is a channel or linked identity, and EA remains the orchestrator brain behind the official companion channel.</p>
      <div class="grid">
        <div>
          <label for="emailAddress">Email / magic link</label>
          <input id="emailAddress" placeholder="runner@example.com" />
          <button onclick="linkEmail()">Add email</button>
        </div>
        <div>
          <label for="provider">External provider</label>
          <select id="provider">
            <option value="google">Google</option>
            <option value="telegram">Telegram</option>
            <option value="facebook">Facebook</option>
          </select>
          <label for="providerSubject">Provider subject / handle</label>
          <input id="providerSubject" placeholder="google-subject-123" />
          <button onclick="linkProvider()">Link provider</button>
        </div>
        <div>
          <label for="channelKind">Channel link</label>
          <select id="channelKind">
            <option value="telegram_official_bot">Official Telegram bot</option>
            <option value="telegram_user_bot">Bring your own Telegram bot</option>
          </select>
          <label for="channelHandle">Channel handle</label>
          <input id="channelHandle" placeholder="@hubbrain" />
          <button onclick="linkChannel()">Link channel</button>
        </div>
      </div>
    </section>
    <section class="panel">
      <h2>Current account</h2>
      <pre id="output">No account loaded yet.</pre>
    </section>
    <section class="panel">
      <h2>Identity and channel summary</h2>
      <pre id="linksOutput">No links loaded yet.</pre>
    </section>
  </main>
  <script>
    function headers() {
      const token = document.getElementById('accessToken').value.trim();
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      return headers;
    }
    async function loadAccount() {
      const response = await fetch('/api/v1/accounts/me', {
        headers: headers()
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || JSON.stringify(data));
      document.getElementById('displayName').value = data.displayName || '';
      document.getElementById('handle').value = data.handle || '';
      document.getElementById('timezone').value = data.timezone || 'UTC';
      document.getElementById('output').textContent = JSON.stringify(data, null, 2);
      await loadLinks();
    }
    async function saveProfile() {
      const payload = {
        subjectId: "",
        displayName: document.getElementById('displayName').value,
        handle: document.getElementById('handle').value,
        timezone: document.getElementById('timezone').value,
        visibility: 'private'
      };
      const current = await fetch('/api/v1/accounts/me', { headers: headers() });
      const currentData = await current.json();
      if (!current.ok) throw new Error(currentData.detail || JSON.stringify(currentData));
      payload.subjectId = currentData.subjectId;
      const response = await fetch('/api/v1/accounts/me/profile', {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || JSON.stringify(data));
      document.getElementById('output').textContent = JSON.stringify(data, null, 2);
      await loadLinks();
    }
    async function loadLinks() {
      const response = await fetch('/api/v1/accounts/me/links', {
        headers: headers()
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || JSON.stringify(data));
      document.getElementById('linksOutput').textContent = JSON.stringify(data, null, 2);
      return data;
    }
    async function currentSubjectId() {
      const response = await fetch('/api/v1/accounts/me', { headers: headers() });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || JSON.stringify(data));
      return data.subjectId;
    }
    async function linkEmail() {
      const subjectId = await currentSubjectId();
      const response = await fetch('/api/v1/accounts/me/links/email', {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({
          subjectId,
          email: document.getElementById('emailAddress').value,
          makePrimary: true
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || JSON.stringify(data));
      await loadLinks();
    }
    async function linkProvider() {
      const subjectId = await currentSubjectId();
      const response = await fetch('/api/v1/accounts/me/links/provider', {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({
          subjectId,
          provider: document.getElementById('provider').value,
          providerSubject: document.getElementById('providerSubject').value,
          makePrimary: document.getElementById('provider').value === 'google'
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || JSON.stringify(data));
      await loadLinks();
    }
    async function linkChannel() {
      const subjectId = await currentSubjectId();
      const response = await fetch('/api/v1/accounts/me/channels', {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({
          subjectId,
          channelKind: document.getElementById('channelKind').value,
          channelHandle: document.getElementById('channelHandle').value,
          notificationsEnabled: true
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || JSON.stringify(data));
      await loadLinks();
    }
  </script>
</body>
</html>
""";
        return Content(html, "text/html");
    }

    [HttpGet("me")]
    [ProducesResponseType<HubUserDto>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<HubUserDto>> GetMe([FromQuery] string? subjectId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = string.IsNullOrWhiteSpace(subjectId)
                ? await _identity.RequireSubjectAsync(Request, cancellationToken)
                : await _identity.RequireMatchingSubjectAsync(Request, subjectId, cancellationToken);
            return Ok(_accounts.EnsureUser(subject.SubjectId, subject.SubjectId));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }

    [HttpPost("me/profile")]
    [ProducesResponseType<HubUserDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<HubUserDto>> UpsertProfile([FromBody] UpsertHubUserProfileRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("profile payload is required.");
        }

        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, request.SubjectId, cancellationToken);
            return Ok(_accounts.UpsertProfile(request with { SubjectId = subject.SubjectId }));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }
}
