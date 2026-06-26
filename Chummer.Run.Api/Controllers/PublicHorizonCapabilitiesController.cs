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
    public ActionResult<HorizonCapabilityHealthCatalog> ListCapabilities()
    {
        HorizonCapabilityHealthSnapshot[] capabilities = _capabilities.ListCapabilities()
            .Where(static capability => capability.PublicVisible)
            .Select(item => _capabilities.GetHealth(item.HorizonId, item.CapabilityId, publicSafe: true))
            .ToArray();

        return Ok(new HorizonCapabilityHealthCatalog(PublicSafe: true, Capabilities: capabilities));
    }
}
