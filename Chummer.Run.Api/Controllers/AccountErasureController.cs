using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.Privacy;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[AutoValidateAntiforgeryToken]
[Route("api/v1/accounts/me")]
public sealed class AccountErasureController : ControllerBase
{
    private readonly HubIdentityClient _identity;
    private readonly AccountErasureService _erasure;
    private readonly HubBrowserAuthService _browserAuth;

    public AccountErasureController(
        HubIdentityClient identity,
        AccountErasureService erasure,
        HubBrowserAuthService browserAuth)
    {
        _identity = identity;
        _erasure = erasure;
        _browserAuth = browserAuth;
    }

    [HttpPost("erase")]
    [ProducesResponseType<CurrentAccountErasureResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status400BadRequest)]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status503ServiceUnavailable)]
    public async Task<ActionResult<CurrentAccountErasureResponse>> EraseCurrentAccount(
        [FromBody] EraseCurrentAccountRequest request,
        CancellationToken cancellationToken)
    {
        if (!string.Equals(
                request.Confirmation,
                AccountErasureConfirmation.RequiredPhrase,
                StringComparison.Ordinal))
        {
            return Problem(
                statusCode: StatusCodes.Status400BadRequest,
                title: "Confirmation phrase does not match.",
                detail: $"Enter {AccountErasureConfirmation.RequiredPhrase} exactly to erase the account.");
        }

        try
        {
            AuthenticatedHubSubject subject =
                await _identity.RequireFreshSubjectAsync(Request, cancellationToken);
            CurrentAccountErasureResponse result =
                await _erasure.EraseAsync(subject.SubjectId, cancellationToken);
            _browserAuth.ClearCookie(Request, Response);
            return Ok(result);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(
                statusCode: ex.StatusCode,
                title: ex.StatusCode == StatusCodes.Status401Unauthorized
                    ? "Sign in again to erase this account."
                    : "Account erasure could not be completed.",
                detail: ex.Message);
        }
    }
}
