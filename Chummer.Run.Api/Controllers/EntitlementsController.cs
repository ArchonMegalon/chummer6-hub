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
    public IActionResult RewardsPage([FromQuery] string subjectId = "") => Redirect("/account");

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
