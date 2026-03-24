using System.Net;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.ViewModels;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/leaderboards")]
public sealed class LeaderboardsController : Controller
{
    private readonly LeaderboardService _leaderboards;
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;
    private readonly HubPageChromeService _chrome;
    private readonly ILogger<LeaderboardsController> _logger;

    public LeaderboardsController(
        LeaderboardService leaderboards,
        AccountService accounts,
        HubIdentityClient identity,
        HubPageChromeService chrome,
        ILogger<LeaderboardsController> logger)
    {
        _leaderboards = leaderboards;
        _accounts = accounts;
        _identity = identity;
        _chrome = chrome;
        _logger = logger;
    }

    [HttpGet("/leaderboards")]
    [Produces("text/html")]
    public async Task<IActionResult> LeaderboardsPage(CancellationToken cancellationToken)
    {
        var model = new LeaderboardsPageViewModel(
            Chrome: await BuildChromeAsync("Leaderboards", "Secondary community standings and quests, kept out of the front-door path.", "/leaderboards", cancellationToken),
            Individuals: _leaderboards.IndividualLeaderboard(publicOnly: true),
            SponsorRank: _leaderboards.SponsorRankLeaderboard(publicOnly: true),
            Groups: _leaderboards.GroupLeaderboard(publicOnly: true),
            Quests: _leaderboards.Quests());
        return View("~/Views/Leaderboards/Index.cshtml", model);
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

    private async Task<SiteChromeViewModel> BuildChromeAsync(
        string title,
        string description,
        string currentPath,
        CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return _chrome.BuildAuthenticatedChrome(title, description, currentPath, user.DisplayName);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return _chrome.BuildPublicChrome(title, description, currentPath);
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Preserving signed-in leaderboard chrome after identity failure.");
            if (Request.Cookies.ContainsKey(HubBrowserAuthConstants.AccessTokenCookieName))
            {
                return _chrome.BuildAuthenticatedChrome(title, description, currentPath, "Signed in");
            }

            return _chrome.BuildPublicChrome(title, description, currentPath);
        }
        catch (Exception ex) when (
            ex is HttpRequestException
            or System.Text.Json.JsonException
            || (ex is TaskCanceledException && !cancellationToken.IsCancellationRequested))
        {
            _logger.LogWarning(ex, "Falling back while building leaderboard chrome.");
            if (Request.Cookies.ContainsKey(HubBrowserAuthConstants.AccessTokenCookieName))
            {
                return _chrome.BuildAuthenticatedChrome(title, description, currentPath, "Signed in");
            }

            return _chrome.BuildPublicChrome(title, description, currentPath);
        }
    }
}
