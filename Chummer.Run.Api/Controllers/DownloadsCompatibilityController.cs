using System.Text.Json;
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
    private readonly InstallLinkingService _installLinking;
    private readonly AccountService _accounts;
    private readonly HubIdentityClient _identity;
    private readonly ILogger<DownloadsCompatibilityController> _logger;

    public DownloadsCompatibilityController(
        PublicReleaseManifestService releases,
        InstallLinkingService installLinking,
        AccountService accounts,
        HubIdentityClient identity,
        ILogger<DownloadsCompatibilityController> logger)
    {
        _releases = releases;
        _installLinking = installLinking;
        _accounts = accounts;
        _identity = identity;
        _logger = logger;
    }

    [HttpGet("/downloads/releases.json")]
    public IActionResult ReleaseManifest()
    {
        var manifest = _releases.LoadManifest();
        return Ok(manifest);
    }

    [HttpGet("/downloads/get/{artifactId}")]
    public async Task<IActionResult> DownloadArtifact([FromRoute] string artifactId, CancellationToken cancellationToken)
    {
        var artifact = _releases.FindDownload(artifactId);
        if (artifact is null)
        {
            return NotFound();
        }

        var filePath = _releases.ResolveDownloadFilePath(artifact);
        if (filePath is null)
        {
            return NotFound();
        }

        var manifest = _releases.LoadManifest();
        AuthenticatedHubSubject? subject = await TryGetOptionalSubjectAsync(cancellationToken);
        var user = subject is null ? null : _accounts.EnsureUser(subject.SubjectId, subject.DisplayName, subject.Email);
        var dispatch = _installLinking.IssueDownload(manifest, artifact, user?.UserId, subject?.SubjectId);
        Response.Headers["X-Chummer-Download-Receipt-Id"] = dispatch.Receipt.ReceiptId;
        if (dispatch.ClaimTicket is not null)
        {
            Response.Headers["Cache-Control"] = "private, no-store";
            Response.Headers["X-Chummer-Install-Claim-Ticket-Id"] = dispatch.ClaimTicket.TicketId;
            Response.Headers["X-Chummer-Install-Claim-Code"] = dispatch.ClaimTicket.ClaimCode;
            Response.Headers["X-Chummer-Install-Claim-Expires"] = dispatch.ClaimTicket.ExpiresAtUtc.ToUniversalTime().ToString("O");
        }

        return PhysicalFile(
            filePath,
            "application/octet-stream",
            artifact.FileName ?? Path.GetFileName(filePath),
            enableRangeProcessing: true);
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
