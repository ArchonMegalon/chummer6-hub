using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.InstallLinking;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/install-linking")]
public sealed class InstallLinkingController : ControllerBase
{
    private readonly HubIdentityClient _identity;
    private readonly AccountService _accounts;
    private readonly InstallLinkingService _installLinking;

    public InstallLinkingController(
        HubIdentityClient identity,
        AccountService accounts,
        InstallLinkingService installLinking)
    {
        _identity = identity;
        _accounts = accounts;
        _installLinking = installLinking;
    }

    [HttpGet("me")]
    [ProducesResponseType<InstallLinkingSummaryDto>(StatusCodes.Status200OK)]
    public async Task<ActionResult<InstallLinkingSummaryDto>> GetSummary(CancellationToken cancellationToken)
    {
        try
        {
            var subject = await _identity.RequireSubjectAsync(Request, cancellationToken);
            var user = _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
            return Ok(_installLinking.GetSummary(user.UserId, subject.SubjectId));
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(statusCode: ex.StatusCode, detail: ex.Message);
        }
    }
}
