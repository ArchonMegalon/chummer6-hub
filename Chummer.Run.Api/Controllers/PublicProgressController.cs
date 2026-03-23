using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route("api/v1/public")]
public sealed class PublicProgressController : ControllerBase
{
    private readonly PublicProgressService _progress;

    public PublicProgressController(PublicProgressService progress)
    {
        _progress = progress;
    }

    [HttpGet("/progress")]
    [HttpGet("/progress/")]
    [Produces("text/html")]
    public ContentResult ProgressPage()
        => Content(_progress.LoadReportHtml(), "text/html");

    [HttpGet("progress-report")]
    [HttpGet("/api/public/progress-report")]
    [Produces("application/json")]
    public ContentResult ProgressReport()
        => Content(_progress.LoadReportJson(), "application/json");

    [HttpGet("progress-poster.svg")]
    [HttpGet("/api/public/progress-poster.svg")]
    [Produces("image/svg+xml")]
    public ContentResult ProgressPoster()
        => Content(_progress.LoadPosterSvg(), "image/svg+xml");
}
