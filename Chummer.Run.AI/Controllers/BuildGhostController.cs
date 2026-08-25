using Chummer.Run.AI.Services.BuildGhost;
using Chummer.Run.AI.Security;
using Chummer.Run.Contracts.BuildGhost;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using System.Security.Cryptography;
using System.Text;

namespace Chummer.Run.AI.Controllers;

[ApiController]
[Route("api/v1/ai/build-ghost")]
public sealed class BuildGhostController(
    IToughTongueBuildGhostAdapter adapter,
    IBuildGhostPersonaReleaseRegistry releases,
    IBuildGhostLiveSupportService liveSupport,
    IBuildGhostPrivateToolAuthorityClient privateToolAuthority,
    ILogger<BuildGhostController> logger,
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

    [HttpGet("support-experience")]
    [ProducesResponseType<BuildGhostSupportExperienceProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public ActionResult<BuildGhostSupportExperienceProjection> SupportExperience()
    {
        if (!IsInternallyAuthorized())
        {
            return Unauthorized();
        }

        Response.Headers.CacheControl = "no-store";
        return Ok(liveSupport.BuildExperience());
    }

    [HttpPost("live-support")]
    [IgnoreAntiforgeryToken]
    [RequestSizeLimit(16 * 1024)]
    [ProducesResponseType<BuildGhostLiveSupportSessionProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public async Task<ActionResult<BuildGhostLiveSupportSessionProjection>> RequestLiveSupport(
        [FromBody] BuildGhostLiveSupportRequest? request,
        CancellationToken cancellationToken)
    {
        if (!IsInternallyAuthorized())
        {
            return Unauthorized();
        }

        if (request is null)
        {
            return BadRequest("Build Ghost live-support request is required.");
        }

        Response.Headers.CacheControl = "no-store";
        return Ok(await liveSupport.RequestAsync(request, cancellationToken).ConfigureAwait(false));
    }

    [HttpPost("live-support/status")]
    [IgnoreAntiforgeryToken]
    [RequestSizeLimit(8 * 1024)]
    [ProducesResponseType<BuildGhostLiveSupportSessionProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    public async Task<ActionResult<BuildGhostLiveSupportSessionProjection>> LiveSupportStatus(
        [FromBody] BuildGhostLiveSupportStatusRequest? request,
        CancellationToken cancellationToken)
    {
        if (!IsInternallyAuthorized())
        {
            return Unauthorized();
        }

        if (request is null)
        {
            return NotFound();
        }

        Response.Headers.CacheControl = "no-store";
        BuildGhostLiveSupportSessionProjection? session =
            await liveSupport.GetAsync(request, cancellationToken).ConfigureAwait(false);
        return session is null ? NotFound() : Ok(session);
    }

    [HttpPost("tool")]
    [IgnoreAntiforgeryToken]
    [RequestSizeLimit(16 * 1024)]
    [Produces("application/json")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status503ServiceUnavailable)]
    public async Task<IActionResult> Tool(
        [FromBody] BuildGhostPrivateToolRequest? request,
        CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        IReadOnlyList<string> validationReasons = BuildGhostPrivateToolAuthorityClient.ValidateRequest(request);
        if (validationReasons.Count != 0 || request is null)
        {
            return BadRequest(new { error = "private_tool_request_invalid", reasons = validationReasons });
        }

        BuildGhostPrivateToolDeploymentValidation deployment =
            BuildGhostPrivateToolDeploymentContract.FromConfiguration(configuration);
        if (!deployment.Accepted
            || deployment.Package is null
            || !string.Equals(deployment.Package.AuthenticationAudience, "build-ghost-private-tool", StringComparison.Ordinal))
        {
            return PrivateToolUnavailable();
        }

        BuildGhostPrivateToolDeploymentPackage legacyPackage;
        if (deployment.Package.AuthenticationScheme == BuildGhostPrivateToolDeploymentContract.LegacyBearerAuthenticationScheme)
        {
            legacyPackage = deployment.Package;
        }
        else if (deployment.Package.AuthenticationScheme == BuildGhostPrivateToolDeploymentContract.ProviderBodyKeyAuthenticationScheme)
        {
            UriBuilder legacyEndpoint = new(deployment.Package.Tool.Endpoint)
            {
                Path = BuildGhostPrivateToolDeploymentContract.LegacyV1Path,
                Query = string.Empty,
                Fragment = string.Empty
            };
            legacyPackage = BuildGhostPrivateToolDeploymentContract.Create(
                legacyEndpoint.Uri,
                deployment.Package.AuthenticationAudience);
        }
        else
        {
            return PrivateToolUnavailable();
        }
        string suppliedContract = Request.Headers["X-Chummer-Build-Ghost-Tool-Contract"].ToString().Trim();
        if (!FixedTimeEquals(suppliedContract, legacyPackage.Tool.ContractDigest)
            || !EphemeralBearerMatches(request.PacketAccessKey))
        {
            return Unauthorized();
        }

        return await ResolveToolAsync(request, deployment.Package.Tool.ContractDigest, cancellationToken)
            .ConfigureAwait(false);
    }

    [HttpPost("~/api/v2/ai/build-ghost/tool")]
    [IgnoreAntiforgeryToken]
    [RequestSizeLimit(16 * 1024)]
    [Produces("application/json")]
    [ProducesResponseType(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status401Unauthorized)]
    [ProducesResponseType(StatusCodes.Status503ServiceUnavailable)]
    public async Task<IActionResult> ProviderToolV2(
        [FromBody] BuildGhostPrivateToolProviderRequest? request,
        CancellationToken cancellationToken)
    {
        Response.Headers.CacheControl = "no-store";
        IReadOnlyList<string> validationReasons =
            BuildGhostPrivateToolAuthorityClient.ValidateProviderRequest(request);
        if (validationReasons.Count != 0 || request is null)
        {
            return BadRequest(new { error = "private_tool_provider_request_invalid", reasons = validationReasons });
        }

        BuildGhostPrivateToolDeploymentValidation deployment =
            BuildGhostPrivateToolDeploymentContract.FromConfiguration(configuration);
        if (!deployment.Accepted
            || deployment.Package is null
            || !string.Equals(deployment.Package.AuthenticationAudience, "build-ghost-private-tool", StringComparison.Ordinal)
            || BuildGhostPrivateToolDeploymentContract.ValidateProviderBodyCredentialDeployment(deployment.Package).Count != 0)
        {
            return PrivateToolUnavailable();
        }

        string suppliedContract = Request.Headers["X-Chummer-Build-Ghost-Tool-Contract"].ToString().Trim();
        string cacheControl = Request.Headers.CacheControl.ToString().Trim();
        if (Request.Headers.ContainsKey("Authorization")
            || Request.Headers.ContainsKey("Cookie")
            || Request.QueryString.HasValue
            || !string.Equals(cacheControl, "no-store", StringComparison.OrdinalIgnoreCase)
            || !FixedTimeEquals(suppliedContract, deployment.Package.Tool.ContractDigest))
        {
            return Unauthorized();
        }

        BuildGhostPrivateToolRequest normalized = new(
            request.PacketAccessKey,
            request.PacketDigest,
            request.Locale,
            request.RequestKind,
            request.Question);
        return await ResolveToolAsync(normalized, deployment.Package.Tool.ContractDigest, cancellationToken)
            .ConfigureAwait(false);
    }

    private async Task<IActionResult> ResolveToolAsync(
        BuildGhostPrivateToolRequest request,
        string authorityContractDigest,
        CancellationToken cancellationToken)
    {
        try
        {
            string packetJson = await privateToolAuthority.ResolveAsync(
                request,
                authorityContractDigest,
                cancellationToken).ConfigureAwait(false);
            Response.Headers["X-Chummer-Build-Ghost-Packet-Digest"] = request.PacketDigest;
            Response.Headers.CacheControl = "no-store";
            return Content(packetJson, "application/json", Encoding.UTF8);
        }
        catch (BuildGhostPrivateToolResolutionException exception)
        {
            logger.LogWarning(
                "Build Ghost private tool resolution failed with {Reason}; trace {TraceId}.",
                exception.Reason,
                HttpContext.TraceIdentifier);
            return PrivateToolResolutionFailure(exception);
        }
    }

    private JsonResult PrivateToolResolutionFailure(
        BuildGhostPrivateToolResolutionException exception)
    {
        Response.Headers.CacheControl = "no-store";
        return new JsonResult(new { error = exception.Reason })
        {
            StatusCode = exception.StatusCode
        };
    }

    private ObjectResult PrivateToolUnavailable()
        => Problem(
            statusCode: StatusCodes.Status503ServiceUnavailable,
            title: "Build Ghost private tool unavailable",
            detail: "The private tool deployment contract is not active.");

    private bool IsInternallyAuthorized()
        => HttpContext.Items.TryGetValue(
                AiMutationAuthorizationMiddleware.AuthorizationMarker,
                out object? authorized)
            && authorized is true;

    private bool EphemeralBearerMatches(string packetAccessKey)
    {
        const string prefix = "Bearer ";
        string header = Request.Headers.Authorization.ToString();
        return header.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)
            && FixedTimeEquals(header[prefix.Length..].Trim(), packetAccessKey);
    }

    private static bool FixedTimeEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.UTF8.GetBytes(left);
        byte[] rightBytes = Encoding.UTF8.GetBytes(right);
        return leftBytes.Length == rightBytes.Length
            && CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }
}
