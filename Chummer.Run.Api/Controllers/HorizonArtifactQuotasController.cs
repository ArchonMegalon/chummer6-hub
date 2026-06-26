using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class HorizonArtifactQuotasController : ControllerBase
{
    private readonly HorizonArtifactQuotaService _quota;
    private readonly HubIdentityClient? _identity;
    private readonly ILogger<HorizonArtifactQuotasController> _logger;

    public HorizonArtifactQuotasController(
        HorizonArtifactQuotaService quota,
        HubIdentityClient? identity = null,
        ILogger<HorizonArtifactQuotasController>? logger = null)
    {
        _quota = quota;
        _identity = identity;
        _logger = logger ?? NullLogger<HorizonArtifactQuotasController>.Instance;
    }

    [HttpGet("/api/v1/horizons/quotas/me")]
    [ProducesResponseType<HorizonArtifactQuotaCatalog>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status503ServiceUnavailable)]
    public async Task<ActionResult<HorizonArtifactQuotaCatalog>> MyQuotas(
        [FromQuery] string? horizonId = null,
        [FromQuery] string? artifactKindOrCapabilityId = null,
        [FromQuery] bool publicVisibleOnly = false,
        CancellationToken cancellationToken = default)
    {
        AuthenticatedHubSubject? subject = await TryGetCurrentSubjectAsync(cancellationToken).ConfigureAwait(false);
        if (subject is null)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "Sign in before checking horizon artifact allowance.");
        }

        try
        {
            IReadOnlyList<HorizonArtifactQuotaSnapshot> quotas = _quota.ListQuotas(
                new HorizonArtifactQuotaCatalogRequest(
                    UserId: subject.SubjectId,
                    HorizonId: horizonId,
                    ArtifactKindOrCapabilityId: artifactKindOrCapabilityId,
                    Email: subject.Email,
                    PublicVisibleOnly: publicVisibleOnly));
            return Ok(new HorizonArtifactQuotaCatalog(
                UserId: subject.SubjectId,
                HorizonId: TrimToNull(horizonId),
                ArtifactKindOrCapabilityId: TrimToNull(artifactKindOrCapabilityId),
                PublicVisibleOnly: publicVisibleOnly,
                Quotas: quotas));
        }
        catch (BrilliantDirectoriesBillingUnavailableException ex)
        {
            return Problem(statusCode: StatusCodes.Status503ServiceUnavailable, detail: ex.Message);
        }
        catch (InvalidOperationException ex)
        {
            return Problem(statusCode: StatusCodes.Status400BadRequest, detail: ex.Message);
        }
    }

    private async Task<AuthenticatedHubSubject?> TryGetCurrentSubjectAsync(CancellationToken cancellationToken)
    {
        if (_identity is null)
        {
            return null;
        }

        try
        {
            return await _identity.RequireSubjectAsync(Request, cancellationToken).ConfigureAwait(false);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return null;
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Horizon quota surface could not resolve the current signed-in subject.");
            return null;
        }
    }

    private static string? TrimToNull(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
