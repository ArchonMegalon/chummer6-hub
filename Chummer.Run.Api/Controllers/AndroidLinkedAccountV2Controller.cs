using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.Privacy;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v2/android/linked/account")]
public sealed class AndroidLinkedAccountV2Controller : ControllerBase
{
    private const int MaxRequestBodyBytes = 4 * 1024;
    private readonly InstallLinkingService _installLinking;
    private readonly IAccountErasureService _erasure;

    public AndroidLinkedAccountV2Controller(
        InstallLinkingService installLinking,
        IAccountErasureService erasure)
    {
        _installLinking = installLinking;
        _erasure = erasure;
    }

    [HttpPost("erase")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<CurrentAccountErasureResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status400BadRequest)]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status503ServiceUnavailable)]
    public async Task<ActionResult<CurrentAccountErasureResponse>> Erase(
        [FromBody] AndroidLinkedV2AccountErasureRequest? request,
        CancellationToken cancellationToken)
    {
        AndroidLinkedV2RequestProofMiddleware.ApplyPrivateResponseHeaders(Response.Headers);
        if (request is null)
        {
            return Problem(
                statusCode: StatusCodes.Status400BadRequest,
                detail: "linked device payload is required.");
        }

        if (!AndroidLinkedV2RequestProof.TryGetPrincipal(HttpContext, out AndroidLinkedV2GrantPrincipal? principal)
            || !string.Equals(request.InstallationId, principal!.Installation.InstallationId, StringComparison.Ordinal)
            || _installLinking.ResolveAndroidLinkedV2Principal(principal) is not { SubjectId: { Length: > 0 } subjectId })
        {
            return Problem(
                statusCode: StatusCodes.Status401Unauthorized,
                detail: "linked device grant is unknown or expired.");
        }

        if (!string.Equals(
                request.Confirmation,
                AccountErasureConfirmation.RequiredPhrase,
                StringComparison.Ordinal))
        {
            return Problem(
                statusCode: StatusCodes.Status400BadRequest,
                detail: $"Enter {AccountErasureConfirmation.RequiredPhrase} exactly to erase the account.");
        }

        try
        {
            CurrentAccountErasureResponse result = await _erasure.EraseAsync(subjectId, cancellationToken);
            return Ok(result);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(
                statusCode: ex.StatusCode,
                title: "Account erasure could not be completed.",
                detail: "The authenticated account-erasure operation failed.");
        }
    }
}

public sealed record AndroidLinkedV2AccountErasureRequest(
    string InstallationId,
    string Confirmation) : AndroidLinkedV2GrantRequest(InstallationId);
