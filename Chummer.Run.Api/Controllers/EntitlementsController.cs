using System.Net;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/entitlements")]
public sealed class EntitlementsController : ControllerBase
{
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;
    private readonly EntitlementService _entitlements;
    private readonly InstallLinkingService _installLinking;
    private readonly RewardService _rewards;
    private readonly CampaignWorkspaceServerPlaneService _workspaceServerPlane;

    public EntitlementsController(
        AccountService accounts,
        HubIdentityClient identity,
        EntitlementService entitlements,
        InstallLinkingService installLinking,
        RewardService rewards,
        CampaignWorkspaceServerPlaneService workspaceServerPlane)
    {
        _accounts = accounts;
        _identity = identity;
        _entitlements = entitlements;
        _installLinking = installLinking;
        _rewards = rewards;
        _workspaceServerPlane = workspaceServerPlane;
    }

    [HttpGet("/rewards")]
    [Produces("text/html")]
    public IActionResult RewardsPage([FromQuery] string subjectId = "") => Redirect("/account");

    [HttpGet("me")]
    [ProducesResponseType<EntitlementAccountProjection>(StatusCodes.Status200OK)]
    public async Task<ActionResult<EntitlementAccountProjection>> GetMine([FromQuery] string subjectId, CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireMatchingSubjectAsync(Request, subjectId, cancellationToken);
            var user = _accounts.GetBySubject(subject.SubjectId);
            if (user is null)
            {
                return NotFound();
            }

            var installLinking = _installLinking.GetSummary(user.UserId, subject.SubjectId);
            return Ok(new EntitlementAccountProjection(
                User: user,
                Entitlements: _entitlements.ListForUser(user.UserId),
                Badges: _rewards.ListBadgesForUser(user.UserId),
                SyncReceipts: _workspaceServerPlane.GetEntitlementSyncReceiptProjection(user, installLinking)));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }
}
