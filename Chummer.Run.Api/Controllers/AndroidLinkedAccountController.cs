using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.Privacy;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/android/linked/account")]
public sealed class AndroidLinkedAccountController : ControllerBase
{
    private const int MaxRequestBodyBytes = 4 * 1024;
    private readonly InstallLinkingService _installLinking;
    private readonly IAccountErasureService _erasure;

    public AndroidLinkedAccountController(
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
        [FromBody] AndroidLinkedAccountErasureRequest? request,
        CancellationToken cancellationToken)
    {
        ApplyPrivateResponseHeaders();
        if (request is null)
        {
            return Problem(
                statusCode: StatusCodes.Status400BadRequest,
                detail: "linked device payload is required.");
        }

        ClaimedInstallationDto? installation = _installLinking.ResolveInstallationForGrant(
            request.InstallationId,
            request.AccessToken);
        if (installation is null || string.IsNullOrWhiteSpace(installation.SubjectId))
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
            CurrentAccountErasureResponse result = await _erasure.EraseAsync(
                installation.SubjectId,
                cancellationToken);
            return Ok(result);
        }
        catch (HubRequestAuthException ex)
        {
            return Problem(
                statusCode: ex.StatusCode,
                title: "Account erasure could not be completed.",
                detail: ex.Message);
        }
    }

    private void ApplyPrivateResponseHeaders()
    {
        Response.Headers.CacheControl = "no-store, max-age=0";
        Response.Headers.Pragma = "no-cache";
        Response.Headers["X-Content-Type-Options"] = "nosniff";
        Response.Headers["Referrer-Policy"] = "no-referrer";
    }
}

public sealed record AndroidLinkedAccountErasureRequest(
    string InstallationId,
    string AccessToken,
    string Confirmation);
