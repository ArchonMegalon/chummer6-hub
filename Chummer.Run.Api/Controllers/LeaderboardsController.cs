using System.Net;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/leaderboards")]
public sealed class LeaderboardsController : ControllerBase
{
    private readonly LeaderboardService _leaderboards;

    public LeaderboardsController(LeaderboardService leaderboards)
    {
        _leaderboards = leaderboards;
    }

    [HttpGet("/leaderboards")]
    [Produces("text/html")]
    public ContentResult LeaderboardsPage()
    {
        var individuals = _leaderboards.IndividualLeaderboard(publicOnly: true);
        var sponsorRanks = _leaderboards.SponsorRankLeaderboard(publicOnly: true);
        var groups = _leaderboards.GroupLeaderboard(publicOnly: true);
        var quests = _leaderboards.Quests();
        var individualRows = string.Join("", individuals.Select(row => $"<tr><td>{row.Rank}</td><td>{WebUtility.HtmlEncode(row.DisplayName)}</td><td>{row.Points}</td><td>{row.LandedSlices}</td></tr>"));
        var sponsorRows = string.Join("", sponsorRanks.Select(row => $"<tr><td>{row.Rank}</td><td>{WebUtility.HtmlEncode(row.DisplayName)}</td><td>{WebUtility.HtmlEncode(row.CurrentAuthorizationTier)}</td><td>{row.CurrentRankScore}</td><td>{row.LifetimePoints}</td></tr>"));
        var groupRows = string.Join("", groups.Select(row => $"<tr><td>{row.Rank}</td><td>{WebUtility.HtmlEncode(row.GroupName)}</td><td>{row.Points}</td><td>{row.LandedSlices}</td></tr>"));
        var questRows = string.Join("", quests.Select(quest => $"<li><strong>{WebUtility.HtmlEncode(quest.Title)}</strong>: {WebUtility.HtmlEncode(quest.Description)} ({quest.CurrentProgress}/{quest.TargetProgress})</li>"));
        var html = $"""
<!doctype html>
<html lang="en">
<head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" /><title>Leaderboards</title></head>
<body style="font-family:Georgia,serif;background:#f5efe2;color:#1f1b16;padding:24px;">
  <h1>Leaderboards</h1>
  <p>Public boards show only users who opted into public recognition and groups that are not private.</p>
  <h2>Individuals</h2>
  <table style="width:100%;background:white;border-collapse:collapse;"><tr><th align="left">Rank</th><th align="left">User</th><th align="left">Points</th><th align="left">Landed</th></tr>{individualRows}</table>
  <h2>Current sponsor rank</h2>
  <table style="width:100%;background:white;border-collapse:collapse;"><tr><th align="left">Rank</th><th align="left">User</th><th align="left">Tier</th><th align="left">Current score</th><th align="left">Lifetime points</th></tr>{sponsorRows}</table>
  <h2>Groups</h2>
  <table style="width:100%;background:white;border-collapse:collapse;"><tr><th align="left">Rank</th><th align="left">Group</th><th align="left">Points</th><th align="left">Landed</th></tr>{groupRows}</table>
  <h2>Quests</h2>
  <ul>{questRows}</ul>
</body>
</html>
""";
        return Content(html, "text/html");
    }

    [HttpGet]
    [Produces("application/json")]
    public ActionResult<object> GetLeaderboards()
        => Ok(new
        {
            individuals = _leaderboards.IndividualLeaderboard(publicOnly: true),
            sponsorRank = _leaderboards.SponsorRankLeaderboard(publicOnly: true),
            groups = _leaderboards.GroupLeaderboard(publicOnly: true),
            quests = _leaderboards.Quests(),
        });
}
