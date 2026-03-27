using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class DownloadsCompatibilityController : ControllerBase
{
    private readonly PublicReleaseManifestService _releases;
    private readonly ReleaseSelectionService _releaseSelection;
    private readonly InstallLinkingService _installLinking;
    private readonly HubIdentityClient _identity;
    private readonly ILogger<DownloadsCompatibilityController> _logger;

    public DownloadsCompatibilityController(
        PublicReleaseManifestService releases,
        ReleaseSelectionService releaseSelection,
        InstallLinkingService installLinking,
        HubIdentityClient identity,
        ILogger<DownloadsCompatibilityController> logger)
    {
        _releases = releases;
        _releaseSelection = releaseSelection;
        _installLinking = installLinking;
        _identity = identity;
        _logger = logger;
    }

    [HttpGet("/downloads/releases.json")]
    public IActionResult ReleaseManifest()
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        return Ok(manifest);
    }

    [HttpGet("/downloads/get/{artifactId}")]
    public async Task<IActionResult> DownloadArtifact([FromRoute] string artifactId, CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var artifact = manifest.Downloads.FirstOrDefault(item => string.Equals(item.Id, artifactId, StringComparison.OrdinalIgnoreCase));
        if (artifact is null)
        {
            return NotFound();
        }

        var filePath = _releases.ResolveDownloadFilePath(artifact);
        if (filePath is null)
        {
            return NotFound();
        }

        var encodedArtifactId = Uri.EscapeDataString(artifact.Id);
        var subject = await TryGetOptionalSubjectAsync(cancellationToken);
        if (subject is not null)
        {
            return Redirect($"/downloads/install/{encodedArtifactId}");
        }

        if (_releaseSelection.RequiresAccount(artifact))
        {
            return Redirect(BuildInstallLoginHref(encodedArtifactId));
        }

        var dispatch = _installLinking.IssueDownload(manifest, artifact, null, null);
        Response.Headers["X-Chummer-Download-Receipt-Id"] = dispatch.Receipt.ReceiptId;

        return PhysicalFile(
            filePath,
            "application/octet-stream",
            artifact.FileName ?? Path.GetFileName(filePath),
            enableRangeProcessing: true);
    }

    [HttpGet("/downloads/file/{artifactId}")]
    public async Task<IActionResult> DownloadResolvedArtifactFile([FromRoute] string artifactId, CancellationToken cancellationToken)
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var artifact = manifest.Downloads.FirstOrDefault(item => string.Equals(item.Id, artifactId, StringComparison.OrdinalIgnoreCase));
        if (artifact is null)
        {
            return NotFound();
        }

        var filePath = _releases.ResolveDownloadFilePath(artifact);
        if (filePath is null)
        {
            return NotFound();
        }

        var subject = await TryGetOptionalSubjectAsync(cancellationToken);
        if (subject is null && _releaseSelection.RequiresAccount(artifact))
        {
            return Redirect(BuildInstallLoginHref(Uri.EscapeDataString(artifact.Id)));
        }

        return PhysicalFile(
            filePath,
            "application/octet-stream",
            artifact.FileName ?? Path.GetFileName(filePath),
            enableRangeProcessing: true);
    }

    [HttpGet("/downloads/files/{**path}")]
    public async Task<IActionResult> DownloadFile([FromRoute] string? path, CancellationToken cancellationToken)
    {
        var originalArtifact = _releases.FindDownloadByPath(path);
        if (originalArtifact is null)
        {
            return NotFound();
        }

        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        var artifact = manifest.Downloads.FirstOrDefault(item => string.Equals(item.Id, originalArtifact.Id, StringComparison.OrdinalIgnoreCase));
        if (artifact is null)
        {
            return NotFound();
        }

        var filePath = _releases.ResolveDownloadFilePath(path);
        if (filePath is null)
        {
            return NotFound();
        }

        var encodedArtifactId = Uri.EscapeDataString(artifact.Id);
        var subject = await TryGetOptionalSubjectAsync(cancellationToken);
        if (subject is not null)
        {
            return Redirect($"/downloads/install/{encodedArtifactId}");
        }

        if (_releaseSelection.RequiresAccount(artifact))
        {
            return Redirect(BuildInstallLoginHref(encodedArtifactId));
        }

        return PhysicalFile(filePath, "application/octet-stream", enableRangeProcessing: true);
    }

    private static string BuildInstallLoginHref(string encodedArtifactId)
        => $"/login?next={Uri.EscapeDataString($"/downloads/install/{encodedArtifactId}")}";

    private async Task<AuthenticatedHubSubject?> TryGetOptionalSubjectAsync(CancellationToken cancellationToken)
    {
        try
        {
            return await _identity.RequireSubjectAsync(Request, cancellationToken);
        }
        catch (HubRequestAuthException ex) when (ex.StatusCode is StatusCodes.Status401Unauthorized or StatusCodes.Status403Forbidden)
        {
            return null;
        }
        catch (HubRequestAuthException ex)
        {
            _logger.LogWarning(ex, "Download dispatch fell back to guest mode because identity could not be confirmed.");
            return null;
        }
    }
}
