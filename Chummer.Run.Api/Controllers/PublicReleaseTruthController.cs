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
    [Produces("application/json")]
    public IActionResult Get()
        => Ok(PublicReleaseTruthProjectionMiddleware.TryGet(HttpContext) ?? _releaseTruth.Capture());

    [HttpGet("/api/v1/public/release-truth/g/{generationId}")]
    [HttpGet("/api/public/release-truth/g/{generationId}")]
    [Produces("application/json")]
    public IActionResult GetGeneration([FromRoute] string generationId)
    {
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
