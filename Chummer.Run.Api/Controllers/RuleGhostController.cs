using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.Support;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[AutoValidateAntiforgeryToken]
[Route("api/v1/rule-ghost")]
public sealed class RuleGhostController : ControllerBase
{
    private readonly HubIdentityClient _identity;
    private readonly AccountService _accounts;
    private readonly RuleGhostService _ruleGhost;

    public RuleGhostController(
        HubIdentityClient identity,
        AccountService accounts,
        RuleGhostService ruleGhost)
    {
        _identity = identity;
        _accounts = accounts;
        _ruleGhost = ruleGhost;
    }

    [HttpPost("ask")]
    [ProducesResponseType<RuleGhostResponse>(StatusCodes.Status200OK)]
    public async Task<ActionResult<RuleGhostResponse>> Ask(
        [FromBody] RuleGhostAskRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("rule ghost payload is required.");
        }

        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return Ok(_ruleGhost.Ask(request.Query, request.PreferredRuleset));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }
}
