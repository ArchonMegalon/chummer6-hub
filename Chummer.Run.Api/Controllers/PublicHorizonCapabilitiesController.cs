using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class PublicHorizonCapabilitiesController : ControllerBase
{
    private readonly HorizonCapabilityService _capabilities;

    public PublicHorizonCapabilitiesController(HorizonCapabilityService capabilities)
    {
        _capabilities = capabilities;
    }

    [HttpGet("/api/v1/public/horizons/capabilities")]
    [ProducesResponseType<HorizonCapabilityHealthCatalog>(StatusCodes.Status200OK)]
    public ActionResult<HorizonCapabilityHealthCatalog> ListCapabilities(
        [FromQuery] string? horizonId = null,
        [FromQuery] string? artifactKindOrCapabilityId = null)
    {
        string? normalizedHorizonId = TrimToNull(horizonId);
        string? normalizedSelector = TrimToNull(artifactKindOrCapabilityId);
        HorizonCapabilityHealthSnapshot[] capabilities = _capabilities.ListCapabilities()
            .Where(capability =>
                capability.PublicVisible
                && (normalizedHorizonId is null || string.Equals(capability.HorizonId, normalizedHorizonId, StringComparison.OrdinalIgnoreCase))
                && (normalizedSelector is null
                    || string.Equals(capability.ArtifactKind, normalizedSelector, StringComparison.OrdinalIgnoreCase)
                    || string.Equals(capability.CapabilityId, normalizedSelector, StringComparison.OrdinalIgnoreCase)))
            .Select(item => _capabilities.GetHealth(item.HorizonId, item.CapabilityId, publicSafe: true))
            .ToArray();

        return Ok(new HorizonCapabilityHealthCatalog(PublicSafe: true, Capabilities: capabilities));
    }

    private static string? TrimToNull(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
