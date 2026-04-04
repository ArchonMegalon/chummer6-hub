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
    private readonly InstallBootstrapTicketService _installBootstrapTickets;
    private readonly HubIdentityClient _identity;
    private readonly ILogger<DownloadsCompatibilityController> _logger;

    public DownloadsCompatibilityController(
        PublicReleaseManifestService releases,
        ReleaseSelectionService releaseSelection,
        InstallLinkingService installLinking,
        InstallBootstrapTicketService installBootstrapTickets,
        HubIdentityClient identity,
        ILogger<DownloadsCompatibilityController> logger)
    {
        _releases = releases;
        _releaseSelection = releaseSelection;
        _installLinking = installLinking;
        _installBootstrapTickets = installBootstrapTickets;
        _identity = identity;
        _logger = logger;
    }

    [HttpGet("/downloads/releases.json")]
    public IActionResult ReleaseManifest()
    {
        var manifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
        return Ok(manifest);
    }

    [HttpGet("/downloads/RELEASE_CHANNEL.generated.json")]
    public IActionResult CanonicalReleaseManifest()
    {
        var manifestPath = _releases.ResolveCanonicalManifestFilePath();
        if (manifestPath is null)
        {
            return NotFound();
        }

        return PhysicalFile(
            manifestPath,
            "application/json; charset=utf-8",
            enableRangeProcessing: false);
    }

    [HttpGet("/downloads/get/{artifactId}")]
    public async Task<IActionResult> DownloadArtifact([FromRoute] string artifactId, CancellationToken cancellationToken)
    {
        var (manifest, artifact) = ResolveManifestArtifact(artifactId);
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
        var (manifest, artifact) = ResolveManifestArtifact(artifactId);
        if (artifact is null)
        {
            return NotFound();
        }

        var filePath = _releases.ResolveDownloadFilePath(artifact);
        if (filePath is null)
        {
            return NotFound();
        }

        string? bootstrapTicket = Request.Query["ticket"].ToString();
        if (!string.IsNullOrWhiteSpace(bootstrapTicket))
        {
            if (_installBootstrapTickets.TryValidateForArtifact(bootstrapTicket, artifact.Id, out _))
            {
                Response.Headers["Cache-Control"] = "private, no-store";
                return PhysicalFile(
                    filePath,
                    "application/octet-stream",
                    artifact.FileName ?? Path.GetFileName(filePath),
                    enableRangeProcessing: true);
            }

            Response.Headers["Cache-Control"] = "private, no-store";
            return Unauthorized(new
            {
                error = "invalid_or_expired_install_ticket",
                message = "The install command expired. Re-open the signed-in downloads handoff and copy a fresh install command."
            });
        }

        string? claimCode = Request.Query["claimCode"].ToString();
        if (!string.IsNullOrWhiteSpace(claimCode))
        {
            if (_installLinking.CanDownloadArtifactWithClaimCode(artifact.Id, claimCode))
            {
                Response.Headers["Cache-Control"] = "private, no-store";
                return PhysicalFile(
                    filePath,
                    "application/octet-stream",
                    artifact.FileName ?? Path.GetFileName(filePath),
                    enableRangeProcessing: true);
            }

            Response.Headers["Cache-Control"] = "private, no-store";
            return Unauthorized(new
            {
                error = "invalid_or_expired_claim_code",
                message = "The claim code in this download handoff is no longer valid. Re-download the Mac setup script from the signed-in downloads page."
            });
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

        var (manifest, artifact) = ResolveManifestArtifact(originalArtifact.Id);
        if (artifact is null)
        {
            return NotFound();
        }

        var filePath = _releases.ResolveDownloadFilePath(path);
        if (filePath is null)
        {
            return NotFound();
        }

        string? bootstrapTicket = Request.Query["ticket"].ToString();
        if (!string.IsNullOrWhiteSpace(bootstrapTicket))
        {
            if (_installBootstrapTickets.TryValidateForArtifact(bootstrapTicket, artifact.Id, out _))
            {
                Response.Headers["Cache-Control"] = "private, no-store";
                return PhysicalFile(filePath, "application/octet-stream", enableRangeProcessing: true);
            }

            Response.Headers["Cache-Control"] = "private, no-store";
            return Unauthorized(new
            {
                error = "invalid_or_expired_install_ticket",
                message = "The install command expired. Re-open the signed-in downloads handoff and copy a fresh install command."
            });
        }

        string? claimCode = Request.Query["claimCode"].ToString();
        if (!string.IsNullOrWhiteSpace(claimCode))
        {
            if (_installLinking.CanDownloadArtifactWithClaimCode(artifact.Id, claimCode))
            {
                Response.Headers["Cache-Control"] = "private, no-store";
                return PhysicalFile(filePath, "application/octet-stream", enableRangeProcessing: true);
            }

            Response.Headers["Cache-Control"] = "private, no-store";
            return Unauthorized(new
            {
                error = "invalid_or_expired_claim_code",
                message = "The claim code in this download handoff is no longer valid. Re-download the Mac setup script from the signed-in downloads page."
            });
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

    private (PublicReleaseManifestDto Manifest, PublicReleaseArtifactDto? Artifact) ResolveManifestArtifact(string artifactId)
    {
        PublicReleaseManifestDto rawManifest = _releases.LoadManifest();
        PublicReleaseManifestDto publicManifest = _releaseSelection.ApplyAccessPolicy(rawManifest);
        PublicReleaseArtifactDto? artifact = publicManifest.Downloads
            .FirstOrDefault(item => string.Equals(item.Id, artifactId, StringComparison.OrdinalIgnoreCase));
        if (artifact is not null)
        {
            return (publicManifest, artifact);
        }

        artifact = rawManifest.Downloads
            .FirstOrDefault(item => string.Equals(item.Id, artifactId, StringComparison.OrdinalIgnoreCase));
        return (rawManifest, artifact);
    }

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
