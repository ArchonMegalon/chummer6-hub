using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Mvc;
using System.Text.Json;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class DownloadsCompatibilityController : ControllerBase
{
    private const string DefaultLocalReleaseProofRelativePath = ".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json";
    private const string LocalReleaseProofFileKey = "CHUMMER_HUB_LOCAL_RELEASE_PROOF_FILE";

    private readonly PublicReleaseManifestService _releases;
    private readonly WindowsProofInstallerService _windowsProofInstallers;
    private readonly AurPackageCatalogService _aurPackages;
    private readonly ReleaseSelectionService _releaseSelection;
    private readonly InstallLinkingService _installLinking;
    private readonly InstallBootstrapTicketService _installBootstrapTickets;
    private readonly HubIdentityClient _identity;
    private readonly IConfiguration _configuration;
    private readonly FlagshipReadinessArtifactService _flagshipReadiness;
    private readonly ImportRouteParityProofGuardService _importRouteParityProofGuard;
    private readonly ILogger<DownloadsCompatibilityController> _logger;

    public DownloadsCompatibilityController(
        PublicReleaseManifestService releases,
        WindowsProofInstallerService windowsProofInstallers,
        AurPackageCatalogService aurPackages,
        ReleaseSelectionService releaseSelection,
        InstallLinkingService installLinking,
        InstallBootstrapTicketService installBootstrapTickets,
        HubIdentityClient identity,
        IConfiguration configuration,
        ILogger<DownloadsCompatibilityController> logger)
    {
        _releases = releases;
        _windowsProofInstallers = windowsProofInstallers;
        _aurPackages = aurPackages;
        _releaseSelection = releaseSelection;
        _installLinking = installLinking;
        _installBootstrapTickets = installBootstrapTickets;
        _identity = identity;
        _configuration = configuration;
        _flagshipReadiness = new FlagshipReadinessArtifactService(configuration);
        _importRouteParityProofGuard = new ImportRouteParityProofGuardService(configuration);
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
        string? filteredManifest = _releases.LoadCanonicalManifestJson();
        return filteredManifest is null
            ? NotFound()
            : Content(filteredManifest, "application/json; charset=utf-8");
    }

    [HttpGet("/downloads/aur-packages.json")]
    public IActionResult AurPackagesManifest()
        => Ok(_aurPackages.LoadCatalog());

    [HttpGet("/downloads/proof/windows")]
    public IActionResult WindowsProofInstallers()
    {
        var installers = _windowsProofInstallers.LoadCatalog();
        if (installers.Count == 0)
        {
            return NotFound(new
            {
                status = "missing",
                message = "No staged Windows supplemental installers are available right now."
            });
        }

        return Ok(new
        {
            status = "support_only",
            message = "These Windows installers are supplemental support downloads. Use the main Downloads page for the recommended Windows setup, and use these direct copies only when support asks you to.",
            downloads = installers.Select(static installer => new
            {
                installer.FileName,
                installer.Head,
                installer.Rid,
                installer.Sha256,
                installer.SizeBytes,
                installer.UpdatedAtUtc,
                installer.DownloadUrl
            })
        });
    }

    [HttpGet("/downloads/proof/windows/{fileName}")]
    [HttpHead("/downloads/proof/windows/{fileName}")]
    public IActionResult DownloadWindowsProofInstaller([FromRoute] string fileName)
    {
        var installer = _windowsProofInstallers.FindByFileName(fileName);
        if (installer is null)
        {
            return NotFound();
        }

        ApplyProofInstallerHeaders(Response.Headers);
        ApplyRouteProofHeaders(
            Response.Headers,
            "No current release status record is attached to the Windows installer output route.",
            "/downloads/proof/windows/{fileName}",
            "/downloads/install/{artifactId}/proof",
            $"/downloads/install/{Uri.EscapeDataString(installer.ArtifactId)}");
        return PhysicalFile(
            installer.FilePath,
            "application/octet-stream",
            installer.FileName,
            enableRangeProcessing: true);
    }

    [HttpGet("/downloads/install/{artifactId}/proof")]
    [HttpHead("/downloads/install/{artifactId}/proof")]
    public IActionResult DownloadWindowsProofInstallerByArtifactId([FromRoute] string artifactId)
    {
        var installer = _windowsProofInstallers.FindByArtifactId(artifactId);
        if (installer is null)
        {
            return NotFound();
        }

        ApplyProofInstallerHeaders(Response.Headers);
        ApplyRouteProofHeaders(
            Response.Headers,
            "No current release status record is attached to the Windows installer artifact route.",
            $"/downloads/install/{Uri.EscapeDataString(installer.ArtifactId)}/proof",
            "/downloads/install/{artifactId}/proof",
            $"/downloads/install/{Uri.EscapeDataString(installer.ArtifactId)}");
        return PhysicalFile(
            installer.FilePath,
            "application/octet-stream",
            installer.FileName,
            enableRangeProcessing: true);
    }

    private static void ApplyProofInstallerHeaders(IHeaderDictionary headers)
    {
        headers["Cache-Control"] = "private, no-store, max-age=0";
        headers["Pragma"] = "no-cache";
        headers["Expires"] = "0";
        headers["X-Chummer-Install-Tier"] = "proof-only";
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
        var requiresAccount = _releaseSelection.RequiresAccount(artifact);
        if (subject is not null && requiresAccount)
        {
            return Redirect($"/downloads/install/{encodedArtifactId}");
        }

        if (requiresAccount)
        {
            return Redirect(BuildInstallLoginHref(artifact));
        }

        var dispatch = _installLinking.IssueDownload(manifest, artifact, null, null);
        Response.Headers["X-Chummer-Download-Receipt-Id"] = dispatch.Receipt.ReceiptId;
        ApplyRouteProofHeaders(
            Response.Headers,
            "No current release status record is attached to the compatibility download route.",
            $"/downloads/get/{Uri.EscapeDataString(artifact.Id)}",
            "/downloads/get/{artifactId}",
            $"/downloads/install/{Uri.EscapeDataString(artifact.Id)}");

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

        if (ControllerContext?.HttpContext is null)
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
                message = "The install command expired. Open the signed-in Downloads page and copy a fresh install command."
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
                message = "The claim code for this download is no longer valid. Re-download the Mac setup script from the signed-in Downloads page."
            });
        }

        var subject = await TryGetOptionalSubjectAsync(cancellationToken);
        if (subject is null && _releaseSelection.RequiresAccount(artifact))
        {
            return Redirect(BuildInstallLoginHref(artifact));
        }

        ApplyRouteProofHeaders(
            Response.Headers,
            "No current release status record is attached to the artifact download output route.",
            $"/downloads/file/{Uri.EscapeDataString(artifact.Id)}",
            "/downloads/file/{artifactId}",
            $"/downloads/install/{Uri.EscapeDataString(artifact.Id)}");
        return PhysicalFile(
            filePath,
            "application/octet-stream",
            artifact.FileName ?? Path.GetFileName(filePath),
            enableRangeProcessing: true);
    }

    [HttpGet("/downloads/files/{**path}")]
    public async Task<IActionResult> DownloadFile([FromRoute] string? path, CancellationToken cancellationToken)
    {
        var (manifest, artifact) = ResolvePublicManifestArtifactByPath(path);
        if (artifact is null)
        {
            return DownloadAurPackageFile(path);
        }

        var filePath = _releases.ResolveDownloadFilePath(path);
        if (filePath is null)
        {
            return NotFound();
        }

        if (ControllerContext?.HttpContext is null)
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
                message = "The install command expired. Open the signed-in Downloads page and copy a fresh install command."
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
                message = "The claim code for this download is no longer valid. Re-download the Mac setup script from the signed-in Downloads page."
            });
        }

        var encodedArtifactId = Uri.EscapeDataString(artifact.Id);
        var subject = await TryGetOptionalSubjectAsync(cancellationToken);
        var requiresAccount = _releaseSelection.RequiresAccount(artifact);
        if (subject is not null && requiresAccount)
        {
            return Redirect($"/downloads/install/{encodedArtifactId}");
        }

        if (requiresAccount)
        {
            return Redirect(BuildInstallLoginHref(artifact));
        }

        ApplyRouteProofHeaders(
            Response.Headers,
            "No current release status record is attached to the public file-output route.",
            "/downloads/files/{**path}",
            $"/downloads/install/{encodedArtifactId}");
        return PhysicalFile(filePath, "application/octet-stream", enableRangeProcessing: true);
    }

    private IActionResult DownloadAurPackageFile(string? path)
    {
        AurPackageEntry? package = _aurPackages.FindByFileName(path);
        if (package is null)
        {
            return NotFound();
        }

        string fileName = Path.GetFileName((path ?? string.Empty).Trim());
        string? filePath = _aurPackages.ResolvePackageFilePath(fileName);
        if (filePath is null)
        {
            return NotFound();
        }

        ApplyRouteProofHeaders(
            Response.Headers,
            "No current release status record is attached to the Arch package sidecar output route.",
            "/downloads/files/{**path}",
            "/downloads");
        Response.Headers["X-Chummer-Install-Tier"] = "arch-sidecar";
        Response.Headers["X-Chummer-Upstream-Artifact-Id"] = package.UpstreamArtifactId;
        return PhysicalFile(filePath, "application/octet-stream", fileName, enableRangeProcessing: true);
    }

    private void ApplyRouteProofHeaders(
        IHeaderDictionary headers,
        string missingReceiptReason,
        params string?[] routeCandidates)
    {
        RouteReceiptMatch? routeReceipt = FindLocalReleaseProofReceipt(routeCandidates);
        RouteProofStatus routeProof = ResolveRouteProofStatus(routeReceipt, missingReceiptReason);

        headers["X-Chummer-Route-State"] = routeProof.State;
        if (!string.IsNullOrWhiteSpace(routeProof.BoundedFailureReason))
        {
            headers["X-Chummer-Route-Bounded-Failure-Reason"] = routeProof.BoundedFailureReason;
        }

        if (routeReceipt is null)
        {
            return;
        }

        headers["X-Chummer-Route-Receipt-Id"] = routeReceipt.ReceiptId;
        headers["X-Chummer-Route-Receipt-Package-Id"] = routeReceipt.PackageId;
        headers["X-Chummer-Route-Receipt-Route"] = routeReceipt.MatchedRoute;
        headers["X-Chummer-Route-Receipt-Match-Mode"] = routeReceipt.MatchMode;
    }

    private RouteProofStatus ResolveRouteProofStatus(RouteReceiptMatch? routeReceipt, string missingReceiptReason)
    {
        if (routeReceipt is null)
        {
            return new RouteProofStatus("bounded_failure", missingReceiptReason);
        }

        FlagshipReadinessSnapshot? readiness = _flagshipReadiness.LoadSnapshot();
        if (readiness?.MissingDesktopClientCoverage == true)
        {
            string reviewRequiredReason = readiness.DesktopClientGapSummary.Trim().TrimEnd('.');
            return new RouteProofStatus(
                "bounded_failure",
                $"Current direct route receipt is attached, but parity claims stay review-required because {reviewRequiredReason}.");
        }

        ImportRouteParityProofGuardSnapshot importRouteGuard = _importRouteParityProofGuard.Evaluate();
        if (!importRouteGuard.IsCurrent && !string.IsNullOrWhiteSpace(importRouteGuard.ReviewRequiredReason))
        {
            return new RouteProofStatus(
                "bounded_failure",
                $"Current direct route receipt is attached, but parity claims stay review-required because {importRouteGuard.ReviewRequiredReason!.Trim().TrimEnd('.')}.");
        }

        return new RouteProofStatus("pass", null);
    }

    private RouteReceiptMatch? FindLocalReleaseProofReceipt(params string?[] routeCandidates)
    {
        string? proofPath = ResolveLocalReleaseProofPath();
        if (string.IsNullOrWhiteSpace(proofPath) || !System.IO.File.Exists(proofPath))
        {
            return null;
        }

        try
        {
            using JsonDocument proof = JsonDocument.Parse(System.IO.File.ReadAllText(proofPath));
            if (!proof.RootElement.TryGetProperty("proof_receipts", out JsonElement receipts) || receipts.ValueKind != JsonValueKind.Array)
            {
                return null;
            }

            foreach (JsonElement receipt in receipts.EnumerateArray())
            {
                if (!receipt.TryGetProperty("routes", out JsonElement routes) || routes.ValueKind != JsonValueKind.Array)
                {
                    continue;
                }

                foreach (JsonElement route in routes.EnumerateArray())
                {
                    string? publishedRoute = NormalizeOptionalRoute(route.GetString());
                    if (publishedRoute is null)
                    {
                        continue;
                    }

                    foreach (string? routeCandidate in routeCandidates)
                    {
                        string? normalizedCandidate = NormalizeOptionalRoute(routeCandidate);
                        if (normalizedCandidate is null)
                        {
                            continue;
                        }

                        if (string.Equals(publishedRoute, normalizedCandidate, StringComparison.OrdinalIgnoreCase))
                        {
                            return new RouteReceiptMatch(
                                ReceiptId: NormalizeOptionalRoute(receipt.GetProperty("receipt_id").GetString()) ?? "unknown",
                                PackageId: NormalizeOptionalRoute(receipt.GetProperty("package_id").GetString()) ?? "unknown",
                                MatchedRoute: publishedRoute,
                                MatchMode: "exact");
                        }
                    }
                }
            }
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Skipping local release status record lookup after JSON load failure.");
        }

        return null;
    }

    private string? ResolveLocalReleaseProofPath()
    {
        string? configuredPath = NormalizeOptionalRoute(_configuration[LocalReleaseProofFileKey]);
        if (configuredPath is not null)
        {
            return configuredPath;
        }

        string relativePath = DefaultLocalReleaseProofRelativePath.Replace('/', Path.DirectorySeparatorChar);
        return new[]
            {
                Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), relativePath)),
                Path.GetFullPath(Path.Combine(Directory.GetCurrentDirectory(), "..", relativePath)),
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, relativePath)),
                Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", relativePath))
            }
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .FirstOrDefault(System.IO.File.Exists);
    }

    private sealed record RouteReceiptMatch(
        string ReceiptId,
        string PackageId,
        string MatchedRoute,
        string MatchMode);

    private sealed record RouteProofStatus(
        string State,
        string? BoundedFailureReason);

    private static string BuildInstallLoginHref(PublicReleaseArtifactDto artifact)
    {
        string encodedArtifactId = Uri.EscapeDataString(artifact.Id);
        string nextPath = $"/downloads/install/{encodedArtifactId}";
        return $"/login?next={Uri.EscapeDataString(nextPath)}";
    }

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

    private (PublicReleaseManifestDto Manifest, PublicReleaseArtifactDto? Artifact) ResolvePublicManifestArtifactByPath(string? path)
    {
        string? normalized = string.IsNullOrWhiteSpace(path)
            ? null
            : path.Trim().TrimStart('/');
        if (normalized is null)
        {
            var emptyManifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
            return (emptyManifest, null);
        }

        string targetFile = Path.GetFileName(normalized.Split('?', '#')[0]);
        if (string.IsNullOrWhiteSpace(targetFile))
        {
            var emptyManifest = _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest());
            return (emptyManifest, null);
        }

        PublicReleaseManifestDto rawManifest = _releases.LoadManifest();
        PublicReleaseManifestDto manifest = _releaseSelection.ApplyAccessPolicy(rawManifest);
        PublicReleaseArtifactDto? artifact = manifest.Downloads.FirstOrDefault(item =>
        {
            string? fileName = item.FileName;
            if (string.IsNullOrWhiteSpace(fileName))
            {
                string rawUrl = item.Url ?? string.Empty;
                string withoutQuery = rawUrl.Split('?', '#')[0];
                fileName = Path.GetFileName(withoutQuery);
            }

            return string.Equals(fileName, targetFile, StringComparison.OrdinalIgnoreCase);
        });

        if (artifact is not null)
        {
            return (manifest, artifact);
        }

        artifact = rawManifest.Downloads.FirstOrDefault(item =>
        {
            string? fileName = item.FileName;
            if (string.IsNullOrWhiteSpace(fileName))
            {
                string rawUrl = item.Url ?? string.Empty;
                string withoutQuery = rawUrl.Split('?', '#')[0];
                fileName = Path.GetFileName(withoutQuery);
            }

            return string.Equals(fileName, targetFile, StringComparison.OrdinalIgnoreCase);
        });

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

    private static string? NormalizeOptionalRoute(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
