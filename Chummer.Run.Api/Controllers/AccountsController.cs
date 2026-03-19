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
    button { margin-top: 12px; padding: 10px 14px; border-radius: 999px; border: 0; background: #205d4a; color: #fff; cursor: pointer; }
    pre { background: #fbf7ef; padding: 12px; border-radius: 12px; overflow: auto; }
  </style>
</head>
<body>
  <main>
    <section class="panel">
      <h1>Hub Account</h1>
      <p>Hub keeps the product-level account, visibility, and group identity layer above raw identity subjects.</p>
      <label for="accessToken">Bearer access token</label>
      <input id="accessToken" placeholder="Paste a Hub access token from the identity surface" />
      <label for="subjectId">Subject id</label>
      <input id="subjectId" placeholder="subject-123" />
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
      <h2>Current account</h2>
      <pre id="output">No account loaded yet.</pre>
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
      const subjectId = document.getElementById('subjectId').value;
      const response = await fetch(`/api/v1/accounts/me?subjectId=${encodeURIComponent(subjectId)}`, {
        headers: headers()
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || JSON.stringify(data));
      document.getElementById('output').textContent = JSON.stringify(data, null, 2);
    }
    async function saveProfile() {
      const payload = {
        subjectId: document.getElementById('subjectId').value,
        displayName: document.getElementById('displayName').value,
        handle: document.getElementById('handle').value,
        timezone: document.getElementById('timezone').value,
        visibility: 'private'
      };
      const response = await fetch('/api/v1/accounts/me/profile', {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || JSON.stringify(data));
      document.getElementById('output').textContent = JSON.stringify(data, null, 2);
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
    public async Task<ActionResult<HubUserDto>> GetMe([FromQuery] string subjectId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, subjectId, cancellationToken);
            var user = _accounts.GetBySubject(subject.SubjectId);
            return user is null ? NotFound() : Ok(user);
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
