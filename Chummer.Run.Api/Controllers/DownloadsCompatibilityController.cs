using System.Text.Json;
using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class DownloadsCompatibilityController : ControllerBase
{
    private readonly PublicReleaseManifestService _releases;

    public DownloadsCompatibilityController(PublicReleaseManifestService releases)
    {
        _releases = releases;
    }

    [HttpGet("/downloads/releases.json")]
    public IActionResult ReleaseManifest()
    {
        var manifest = _releases.LoadManifest();
        return Ok(manifest);
    }

    [HttpGet("/downloads/files/{**path}")]
    public IActionResult DownloadFile([FromRoute] string? path)
    {
        var filePath = _releases.ResolveDownloadFilePath(path);
        if (filePath is null)
        {
            return NotFound();
        }

        return PhysicalFile(filePath, "application/octet-stream", enableRangeProcessing: true);
    }
}
