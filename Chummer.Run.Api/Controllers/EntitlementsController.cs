using System.Net;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/entitlements")]
public sealed class EntitlementsController : ControllerBase
{
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;
    private readonly EntitlementService _entitlements;
    private readonly RewardService _rewards;

    public EntitlementsController(AccountService accounts, HubIdentityClient identity, EntitlementService entitlements, RewardService rewards)
    {
        _accounts = accounts;
        _identity = identity;
        _entitlements = entitlements;
        _rewards = rewards;
    }

    [HttpGet("/rewards")]
    [Produces("text/html")]
    public ContentResult RewardsPage([FromQuery] string subjectId = "")
    {
        var html = $$"""
<!doctype html>
<html lang="en">
<head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" /><title>Rewards</title></head>
<body style="font-family:Georgia,serif;background:#f4efe4;color:#1f1b16;padding:24px;max-width:920px;margin:0 auto;">
  <h1>Rewards and Entitlements</h1>
  <p>Rewards and entitlements are private account data. Use the same subject id that owns the bearer token below.</p>
  <label for="accessToken" style="display:block;margin:12px 0 6px;">Bearer access token</label>
  <input id="accessToken" style="width:100%;padding:10px 12px;border-radius:10px;border:1px solid rgba(31,27,22,.2);" placeholder="Paste a Hub access token from the identity surface" />
  <label for="subjectId" style="display:block;margin:12px 0 6px;">Subject id</label>
  <input id="subjectId" style="width:100%;padding:10px 12px;border-radius:10px;border:1px solid rgba(31,27,22,.2);" value="{{WebUtility.HtmlEncode(subjectId)}}" placeholder="subject-123" />
  <button onclick="loadRewards()" style="margin-top:12px;padding:10px 14px;border-radius:999px;border:0;background:#205d4a;color:white;cursor:pointer;">Load rewards</button>
  <pre id="output" style="background:white;padding:16px;border-radius:12px;border:1px solid rgba(31,27,22,.12);margin-top:16px;">No rewards loaded yet.</pre>
  <script>
    async function loadRewards() {
      const token = document.getElementById('accessToken').value.trim();
      const currentSubjectId = document.getElementById('subjectId').value.trim();
      const response = await fetch(`/api/v1/entitlements/me?subjectId=${encodeURIComponent(currentSubjectId)}`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
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
    public async Task<ActionResult<object>> GetMine([FromQuery] string subjectId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, subjectId, cancellationToken);
            var user = _accounts.GetBySubject(subject.SubjectId);
            if (user is null)
            {
                return NotFound();
            }

            return Ok(new
            {
                user,
                entitlements = _entitlements.ListForUser(user.UserId),
                badges = _rewards.ListBadgesForUser(user.UserId),
            });
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }
}
