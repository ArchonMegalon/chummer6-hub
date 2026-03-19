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
    public async Task<IActionResult> AccountPage(CancellationToken cancellationToken)
    {
        try
        {
            await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException)
        {
            return Redirect("/login?next=/account");
        }

        var html = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Account · Chummer</title>
  <style>
    :root {
      --bg: #efe6d2;
      --paper: rgba(255, 251, 242, 0.82);
      --ink: #1a1712;
      --muted: #665d52;
      --accent: #125a58;
      --warm: #8d5932;
      --line: rgba(26, 23, 18, 0.12);
      --shadow: 0 18px 40px rgba(26, 23, 18, 0.08);
    }
    body { font-family: Georgia, serif; background: linear-gradient(180deg, #f5eedf 0%, var(--bg) 55%, #e7dac0 100%); color: var(--ink); margin: 0; }
    main { max-width: 1040px; margin: 0 auto; padding: 28px 20px 56px; }
    .topbar { display:flex; justify-content:space-between; align-items:center; gap:18px; margin-bottom:22px; padding:14px 18px; border:1px solid var(--line); border-radius:999px; background:rgba(255,255,255,.72); box-shadow:var(--shadow); }
    .nav { display:flex; flex-wrap:wrap; gap:14px; color:var(--muted); font-size:.95rem; }
    .brand { font-size:1.1rem; letter-spacing:.08em; text-transform:uppercase; }
    .panel { background: var(--paper); border: 1px solid rgba(31,27,22,.12); border-radius: 18px; padding: 18px; margin-bottom: 16px; box-shadow: var(--shadow); }
    label { display:block; margin: 10px 0 6px; font-weight: 600; }
    input, select { width:100%; padding:10px 12px; border-radius: 10px; border:1px solid rgba(31,27,22,.2); background:rgba(255,255,255,.92); }
    button, .chip { margin-top: 12px; padding: 10px 14px; border-radius: 999px; border: 0; background: #205d4a; color: #fff; cursor: pointer; text-decoration:none; display:inline-flex; align-items:center; justify-content:center; }
    .chip.secondary { background:#7a5532; }
    pre { background: #fbf7ef; padding: 12px; border-radius: 12px; overflow: auto; border:1px solid rgba(31,27,22,.08); }
    .grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }
    p, li { color: var(--muted); }
  </style>
</head>
<body>
  <main>
    <header class="topbar">
      <div class="brand">Chummer.run</div>
      <nav class="nav">
        <a href="/">Landing</a>
        <a href="/home">Home</a>
        <a href="/participate">Participate</a>
        <a href="/leaderboards">Leaderboards</a>
        <a href="/logout">Sign out</a>
      </nav>
    </header>
    <section class="panel">
      <h1>Account</h1>
      <p>Hub keeps the product-level account, visibility, linked identities, and channel policy above raw identity subjects. This page assumes you already reached it through the hosted sign-in flow.</p>
      <label for="displayName">Display name</label>
      <input id="displayName" placeholder="Archon" />
      <label for="handle">Handle</label>
      <input id="handle" placeholder="archon" />
      <label for="timezone">Timezone</label>
      <input id="timezone" value="Europe/Vienna" />
      <button onclick="loadAccount()">Refresh account</button>
      <button onclick="saveProfile()">Save profile</button>
    </section>
    <section class="panel">
      <h2>Linked identities and channels</h2>
      <p>Email-first entry is live now. Google is the next allowed mainstream bootstrap when credentials land. Telegram can be linked as an identity or the official companion channel. Facebook and bring-your-own bots stay out of the first-wave UI.</p>
      <div class="grid">
        <div>
          <label for="emailAddress">Email / magic link</label>
          <input id="emailAddress" placeholder="runner@example.com" />
          <button onclick="linkEmail()">Add email identity</button>
        </div>
        <div>
          <label for="provider">External provider</label>
          <select id="provider">
            <option value="google">Google</option>
            <option value="telegram">Telegram</option>
          </select>
          <label for="providerSubject">Provider subject / handle</label>
          <input id="providerSubject" placeholder="google-subject-123" />
          <button onclick="linkProvider()">Link provider</button>
        </div>
        <div>
          <label for="channelKind">Channel link</label>
          <select id="channelKind">
            <option value="telegram_official_bot">Official Telegram bot</option>
          </select>
          <label for="channelHandle">Channel handle</label>
          <input id="channelHandle" placeholder="@hubbrain" />
          <button onclick="linkChannel()">Link channel</button>
        </div>
      </div>
    </section>
    <section class="panel">
      <h2>Current account</h2>
      <pre id="output">Loading account...</pre>
    </section>
    <section class="panel">
      <h2>Identity and channel summary</h2>
      <pre id="linksOutput">Loading linked identities...</pre>
    </section>
    <section class="panel">
      <h2>First-wave honesty</h2>
      <ul>
        <li>Email-first entry is the current live path for the browser shell.</li>
        <li>Google is allowed next, but this host should not pretend it is active before provider credentials exist.</li>
        <li>Facebook and user-provided Telegram bots are intentionally out of the first-wave account UI.</li>
      </ul>
    </section>
  </main>
  <script>
    const jsonHeaders = { 'Content-Type': 'application/json' };

    async function loadAccount() {
      const response = await fetch('/api/v1/accounts/me', { headers: jsonHeaders });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || JSON.stringify(data));
      document.getElementById('displayName').value = data.displayName || '';
      document.getElementById('handle').value = data.handle || '';
      document.getElementById('timezone').value = data.timezone || 'UTC';
      document.getElementById('output').textContent = JSON.stringify(data, null, 2);
      await loadLinks();
    }

    async function saveProfile() {
      const current = await fetch('/api/v1/accounts/me', { headers: jsonHeaders });
      const currentData = await current.json();
      if (!current.ok) throw new Error(currentData.detail || JSON.stringify(currentData));

      const payload = {
        subjectId: currentData.subjectId,
        displayName: document.getElementById('displayName').value,
        handle: document.getElementById('handle').value,
        timezone: document.getElementById('timezone').value,
        visibility: 'private'
      };

      const response = await fetch('/api/v1/accounts/me/profile', {
        method: 'POST',
        headers: jsonHeaders,
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || JSON.stringify(data));
      document.getElementById('output').textContent = JSON.stringify(data, null, 2);
      await loadLinks();
    }

    async function loadLinks() {
      const response = await fetch('/api/v1/accounts/me/links', { headers: jsonHeaders });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || JSON.stringify(data));
      document.getElementById('linksOutput').textContent = JSON.stringify(data, null, 2);
      return data;
    }

    async function currentSubjectId() {
      const response = await fetch('/api/v1/accounts/me', { headers: jsonHeaders });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || JSON.stringify(data));
      return data.subjectId;
    }

    async function linkEmail() {
      const subjectId = await currentSubjectId();
      const response = await fetch('/api/v1/accounts/me/links/email', {
        method: 'POST',
        headers: jsonHeaders,
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
      const provider = document.getElementById('provider').value;
      const response = await fetch('/api/v1/accounts/me/links/provider', {
        method: 'POST',
        headers: jsonHeaders,
        body: JSON.stringify({
          subjectId,
          provider,
          providerSubject: document.getElementById('providerSubject').value,
          makePrimary: provider === 'google'
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
        headers: jsonHeaders,
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

    loadAccount().catch(error => {
      document.getElementById('output').textContent = error.message;
      document.getElementById('linksOutput').textContent = error.message;
    });
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
