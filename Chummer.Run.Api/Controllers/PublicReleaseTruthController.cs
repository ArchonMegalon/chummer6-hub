using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class PublicReleaseTruthController : ControllerBase
{
    private readonly IReleaseTruthProjection _releaseTruth;

    public PublicReleaseTruthController(IReleaseTruthProjection releaseTruth)
    {
        _releaseTruth = releaseTruth;
    }

    [HttpGet("/api/v1/public/release-truth")]
    [HttpGet("/api/public/release-truth")]
    [HttpHead("/api/v1/public/release-truth")]
    [HttpHead("/api/public/release-truth")]
    [Produces("application/json")]
    public IActionResult Get()
    {
        global::Chummer.Run.Api.PrivateResponseCacheHeaders.Apply(Response.Headers);
        return PublicReleaseContractRequestPolicy.IsCanonicalReleaseTruthRequest(
            Request,
            generationId: null)
            ? Ok(
                PublicReleaseTruthProjectionMiddleware.TryGet(HttpContext)
                ?? _releaseTruth.Capture())
            : NotFound();
    }

    [HttpGet("/api/v1/public/release-truth/g/{generationId}")]
    [HttpGet("/api/public/release-truth/g/{generationId}")]
    [HttpHead("/api/v1/public/release-truth/g/{generationId}")]
    [HttpHead("/api/public/release-truth/g/{generationId}")]
    [Produces("application/json")]
    public IActionResult GetGeneration([FromRoute] string generationId)
    {
        global::Chummer.Run.Api.PrivateResponseCacheHeaders.Apply(Response.Headers);
        if (!PublicReleaseContractRequestPolicy.IsCanonicalReleaseTruthRequest(
                Request,
                generationId))
        {
            return NotFound();
        }

        try
        {
            return Ok(
                PublicReleaseTruthProjectionMiddleware.TryGet(HttpContext)
                ?? _releaseTruth.CaptureGeneration(generationId));
        }
        catch (InvalidDataException)
        {
            return NotFound();
        }
        catch (InvalidOperationException)
        {
            return NotFound();
        }
    }
}
