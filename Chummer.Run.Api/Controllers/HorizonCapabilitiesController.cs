using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class HorizonCapabilitiesController : ControllerBase
{
    private readonly HorizonCapabilityService _capabilities;
    private readonly HubIdentityClient? _identity;
    private readonly ILogger<HorizonCapabilitiesController> _logger;

    public HorizonCapabilitiesController(
        HorizonCapabilityService capabilities,
        HubIdentityClient? identity = null,
        ILogger<HorizonCapabilitiesController>? logger = null)
    {
        _capabilities = capabilities;
        _identity = identity;
        _logger = logger ?? NullLogger<HorizonCapabilitiesController>.Instance;
    }

    [HttpGet("/api/v1/horizons/capabilities/me")]
    [ProducesResponseType<HorizonCapabilityHealthCatalog>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public async Task<ActionResult<HorizonCapabilityHealthCatalog>> MyCapabilities(
        [FromQuery] string? horizonId = null,
        [FromQuery] string? artifactKindOrCapabilityId = null,
        [FromQuery] bool publicVisibleOnly = false,
        CancellationToken cancellationToken = default)
    {
        AuthenticatedHubSubject? subject = await TryGetCurrentSubjectAsync(cancellationToken).ConfigureAwait(false);
        if (subject is null)
        {
            return Problem(statusCode: StatusCodes.Status401Unauthorized, detail: "Sign in before checking horizon capability health.");
        }

        string? normalizedHorizonId = TrimToNull(horizonId);
        string? normalizedSelector = TrimToNull(artifactKindOrCapabilityId);
        HorizonCapabilityHealthSnapshot[] capabilities = _capabilities.ListCapabilities()
            .Where(capability =>
                (normalizedHorizonId is null || string.Equals(capability.HorizonId, normalizedHorizonId, StringComparison.OrdinalIgnoreCase))
                && (normalizedSelector is null
                    || string.Equals(capability.ArtifactKind, normalizedSelector, StringComparison.OrdinalIgnoreCase)
                    || string.Equals(capability.CapabilityId, normalizedSelector, StringComparison.OrdinalIgnoreCase))
                && (!publicVisibleOnly || capability.PublicVisible))
            .OrderBy(capability => capability.HorizonId, StringComparer.OrdinalIgnoreCase)
            .ThenBy(capability => capability.CapabilityId, StringComparer.OrdinalIgnoreCase)
            .Select(item => _capabilities.GetHealth(item.HorizonId, item.CapabilityId, publicSafe: true))
            .ToArray();

        return Ok(new HorizonCapabilityHealthCatalog(PublicSafe: true, Capabilities: capabilities));
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
            _logger.LogWarning(ex, "Horizon capability surface could not resolve the current signed-in subject.");
            return null;
        }
    }

    private static string? TrimToNull(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
