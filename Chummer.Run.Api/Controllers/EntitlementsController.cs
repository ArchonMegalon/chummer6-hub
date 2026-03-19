using System.Net;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/entitlements")]
public sealed class EntitlementsController : ControllerBase
{
    private readonly AccountService _accounts;
    private readonly EntitlementService _entitlements;
    private readonly RewardService _rewards;

    public EntitlementsController(AccountService accounts, EntitlementService entitlements, RewardService rewards)
    {
        _accounts = accounts;
        _entitlements = entitlements;
        _rewards = rewards;
    }

    [HttpGet("/rewards")]
    [Produces("text/html")]
    public ContentResult RewardsPage([FromQuery] string subjectId = "")
    {
        var user = _accounts.GetBySubject(subjectId);
        var entitlements = user is null ? Array.Empty<object>() : _entitlements.ListForUser(user.UserId).Cast<object>().ToArray();
        var badges = user is null ? Array.Empty<object>() : _rewards.ListBadgesForUser(user.UserId).Cast<object>().ToArray();
        var entitlementRows = string.Join("", entitlements.Select(item => $"<li>{WebUtility.HtmlEncode(item.ToString() ?? string.Empty)}</li>"));
        var badgeRows = string.Join("", badges.Select(item => $"<li>{WebUtility.HtmlEncode(item.ToString() ?? string.Empty)}</li>"));
        var html = $"""
<!doctype html>
<html lang="en">
<head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" /><title>Rewards</title></head>
<body style="font-family:Georgia,serif;background:#f4efe4;color:#1f1b16;padding:24px;">
  <h1>Rewards and Entitlements</h1>
  <p>Subject: {WebUtility.HtmlEncode(subjectId)}</p>
  <h2>Entitlements</h2>
  <ul>{entitlementRows}</ul>
  <h2>Badges</h2>
  <ul>{badgeRows}</ul>
</body>
</html>
""";
        return Content(html, "text/html");
    }

    [HttpGet("me")]
    public ActionResult<object> GetMine([FromQuery] string subjectId)
    {
        var user = _accounts.GetBySubject(subjectId);
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
}
