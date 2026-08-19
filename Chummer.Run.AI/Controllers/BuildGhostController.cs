using Chummer.Run.AI.Services.BuildGhost;
using Chummer.Run.Contracts.BuildGhost;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using System.Security.Cryptography;
using System.Text;

namespace Chummer.Run.AI.Controllers;

[ApiController]
[Route("api/v1/ai/build-ghost")]
public sealed class BuildGhostController(
    IToughTongueBuildGhostAdapter adapter,
    IBuildGhostPersonaReleaseRegistry releases,
    IConfiguration configuration) : ControllerBase
{
    [HttpPost("explain")]
    [IgnoreAntiforgeryToken]
    [RequestSizeLimit(2 * 1024 * 1024)]
    [ProducesResponseType<ToughTongueBuildGhostResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public async Task<ActionResult<ToughTongueBuildGhostResult>> Explain(
        [FromBody] ToughTongueBuildGhostRequest? request,
        CancellationToken cancellationToken)
    {
        if (!IsInternallyAuthorized())
        {
            return Unauthorized();
        }

        if (request is null)
        {
            return BadRequest("Build Ghost explanation request is required.");
        }

        try
        {
            return Ok(await adapter.ExplainAsync(request, cancellationToken).ConfigureAwait(false));
        }
        catch (InvalidDataException exception)
        {
            return BadRequest(exception.Message);
        }
    }

    [HttpGet("rook-release")]
    [ProducesResponseType<BuildGhostPersonaReleaseProjection>(StatusCodes.Status200OK)]
    public ActionResult<BuildGhostPersonaReleaseProjection> RookRelease()
        => Ok(releases.ResolveRook());

    private bool IsInternallyAuthorized()
    {
        string configured = configuration["FLEET_INTERNAL_API_TOKEN"]?.Trim() ?? string.Empty;
        const string prefix = "Bearer ";
        string header = Request.Headers.Authorization.ToString();
        if (string.IsNullOrWhiteSpace(configured)
            || !header.StartsWith(prefix, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        byte[] supplied = Encoding.UTF8.GetBytes(header[prefix.Length..].Trim());
        byte[] expected = Encoding.UTF8.GetBytes(configured);
        return supplied.Length == expected.Length && CryptographicOperations.FixedTimeEquals(supplied, expected);
    }
}
