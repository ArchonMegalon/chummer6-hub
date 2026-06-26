using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class HorizonArtifactQuotasController : ControllerBase
{
    private readonly HorizonArtifactQuotaService _quota;
    private readonly AccountService? _accounts;
    private readonly HubIdentityClient? _identity;
    private readonly ILogger<HorizonArtifactQuotasController> _logger;

    public HorizonArtifactQuotasController(
        HorizonArtifactQuotaService quota,
        AccountService? accounts = null,
        HubIdentityClient? identity = null,
        ILogger<HorizonArtifactQuotasController>? logger = null)
    {
        _quota = quota;
        _accounts = accounts;
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
        ResolvedHorizonActor? actor = await TryGetCurrentActorAsync(cancellationToken).ConfigureAwait(false);
        if (actor is null)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "Sign in before checking horizon artifact allowance.");
        }

        try
        {
            IReadOnlyList<HorizonArtifactQuotaSnapshot> quotas = _quota.ListQuotas(
                new HorizonArtifactQuotaCatalogRequest(
                    UserId: actor.UserId,
                    HorizonId: horizonId,
                    ArtifactKindOrCapabilityId: artifactKindOrCapabilityId,
                    Email: actor.Email,
                    PublicVisibleOnly: publicVisibleOnly));
            return Ok(new HorizonArtifactQuotaCatalog(
                UserId: actor.UserId,
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

    private async Task<ResolvedHorizonActor?> TryGetCurrentActorAsync(CancellationToken cancellationToken)
    {
        if (_identity is null)
        {
            return null;
        }

        try
        {
            AuthenticatedHubSubject subject = await _identity.RequireSubjectAsync(Request, cancellationToken).ConfigureAwait(false);
            string userId = _accounts?.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email).UserId
                ?? subject.SubjectId;
            return new ResolvedHorizonActor(userId, subject.Email);
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

    private sealed record ResolvedHorizonActor(
        string UserId,
        string? Email);
}
