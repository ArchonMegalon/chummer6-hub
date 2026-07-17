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
    private readonly ArtifactDeliveryPolicy _artifactDelivery;
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
        ILogger<DownloadsCompatibilityController> logger,
        ArtifactDeliveryPolicy? artifactDelivery = null)
    {
        _releases = releases;
        _windowsProofInstallers = windowsProofInstallers;
        _aurPackages = aurPackages;
        _releaseSelection = releaseSelection;
        _installLinking = installLinking;
        _installBootstrapTickets = installBootstrapTickets;
        _artifactDelivery = artifactDelivery ?? new ArtifactDeliveryPolicy(releases, configuration);
        _identity = identity;
        _configuration = configuration;
        _flagshipReadiness = new FlagshipReadinessArtifactService(configuration);
        _importRouteParityProofGuard = new ImportRouteParityProofGuardService(configuration);
        _logger = logger;
    }

    [HttpGet("/downloads/releases.json")]
    public IActionResult ReleaseManifest()
    {
        ReleaseShelfSnapshot snapshot = _releases.CaptureShelfSnapshot();
        TryApplyCanonicalManifestNoStoreHeaders(snapshot);
        PublicReleaseManifestDto manifest = _artifactDelivery.FilterRevokedArtifacts(
            snapshot,
            _releaseSelection.ApplyAccessPolicy(_releases.LoadManifest(snapshot)));
        return Ok(manifest);
    }

    [HttpGet("/downloads/RELEASE_CHANNEL.generated.json")]
    public IActionResult CanonicalReleaseManifest()
    {
        ReleaseShelfSnapshot snapshot = _releases.CaptureShelfSnapshot();
        if (ControllerContext.HttpContext is HttpContext httpContext)
        {
            ApplyCanonicalManifestNoStoreHeaders(httpContext.Response.Headers);
            ApplyGenerationHeader(httpContext.Response.Headers, snapshot);
        }

        string? filteredManifest = _releases.LoadCanonicalManifestJson(snapshot);
        return filteredManifest is null
            ? NotFound()
            : Content(filteredManifest, "application/json; charset=utf-8");
    }

    [HttpGet("/downloads/g/{generationId}/releases.json")]
    public IActionResult GenerationReleaseManifest([FromRoute] string generationId)
    {
        ReleaseShelfSnapshot? snapshot = TryCaptureGeneration(generationId);
        if (snapshot is null)
        {
            return NotFound();
        }

        TryApplyGenerationHeader(snapshot);
        TryApplyImmutableGenerationHeaders();
        byte[]? manifestBytes = _releases.LoadGenerationCompatibilityManifestBytes(snapshot);
        return manifestBytes is null
            ? NotFound()
            : File(manifestBytes, "application/json; charset=utf-8");
    }

    [HttpGet("/downloads/g/{generationId}/RELEASE_CHANNEL.generated.json")]
    public IActionResult GenerationCanonicalReleaseManifest([FromRoute] string generationId)
    {
        ReleaseShelfSnapshot? snapshot = TryCaptureGeneration(generationId);
        if (snapshot is null)
        {
            return NotFound();
        }

        TryApplyGenerationHeader(snapshot);
        TryApplyImmutableGenerationHeaders();
        byte[]? manifestBytes = _releases.LoadGenerationCanonicalManifestBytes(snapshot);
        return manifestBytes is null
            ? NotFound()
            : File(manifestBytes, "application/json; charset=utf-8");
    }

    [HttpGet("/downloads/aur-packages.json")]
    public IActionResult AurPackagesManifest()
    {
        ReleaseShelfSnapshot snapshot = _releases.CaptureShelfSnapshot();
        TryApplyGenerationHeader(snapshot);
        return Ok(_aurPackages.LoadCatalog(snapshot));
    }

    [HttpGet("/downloads/g/{generationId}/aur-packages.json")]
    public IActionResult GenerationAurPackagesManifest([FromRoute] string generationId)
    {
        ReleaseShelfSnapshot? snapshot = TryCaptureGeneration(generationId);
        if (snapshot is null)
        {
            return NotFound();
        }

        TryApplyGenerationHeader(snapshot);
        TryApplyImmutableGenerationHeaders();
        return Ok(_aurPackages.LoadCatalog(snapshot));
    }

    [HttpGet("/downloads/proof/windows")]
    [HttpGet("/downloads/proof/windows/current")]
    public IActionResult WindowsProofInstallers()
    {
        WindowsProofDeliverySnapshot? proof = _windowsProofInstallers.CaptureCurrentProof();
        if (proof is not null)
        {
            return BuildWindowsProofCatalog(proof);
        }

        return _windowsProofInstallers.LegacyShelfFallbackEnabled
            ? BuildLegacyWindowsProofCatalog(_releases.CaptureShelfSnapshot())
            : WindowsProofMissing();
    }

    [HttpGet("/downloads/proof/windows/generations/{generationId}")]
    public IActionResult GenerationWindowsProofInstallers([FromRoute] string generationId)
    {
        WindowsProofDeliverySnapshot? proof = _windowsProofInstallers.CaptureProofGeneration(generationId);
        if (proof is not null)
        {
            return BuildWindowsProofCatalog(proof);
        }

        if (!_windowsProofInstallers.LegacyShelfFallbackEnabled)
        {
            return NotFound();
        }

        ReleaseShelfSnapshot? legacy = TryCaptureGeneration(generationId);
        return legacy is null ? NotFound() : BuildLegacyWindowsProofCatalog(legacy);
    }

    [HttpGet("/downloads/proof/windows/candidates/{candidateVersion}")]
    public IActionResult CandidateWindowsProofInstallers([FromRoute] string candidateVersion)
    {
        WindowsProofDeliverySnapshot? proof =
            _windowsProofInstallers.CaptureProofCandidate(candidateVersion);
        return proof is null ? NotFound() : BuildWindowsProofCatalog(proof);
    }

    [HttpGet("/downloads/proof/windows/{fileName}")]
    [HttpHead("/downloads/proof/windows/{fileName}")]
    public IActionResult DownloadWindowsProofInstaller([FromRoute] string fileName)
    {
        WindowsProofDeliverySnapshot? proof = _windowsProofInstallers.CaptureCurrentProof();
        if (proof is not null)
        {
            WindowsProofDeliveryArtifact? artifact =
                _windowsProofInstallers.FindProofInstallerByFileName(proof, fileName);
            return artifact is null
                ? NotFound()
                : BuildWindowsProofArtifactFileResult(proof, artifact);
        }

        return _windowsProofInstallers.LegacyShelfFallbackEnabled
            ? DownloadLegacyWindowsProofInstaller(_releases.CaptureShelfSnapshot(), fileName, byArtifactId: false)
            : NotFound();
    }

    [HttpGet("/downloads/proof/windows/generations/{generationId}/files/{fileName}")]
    [HttpHead("/downloads/proof/windows/generations/{generationId}/files/{fileName}")]
    public IActionResult DownloadGenerationWindowsProofInstaller(
        [FromRoute] string generationId,
        [FromRoute] string fileName)
    {
        WindowsProofDeliverySnapshot? proof = _windowsProofInstallers.CaptureProofGeneration(generationId);
        if (proof is not null)
        {
            WindowsProofDeliveryArtifact? artifact =
                _windowsProofInstallers.FindProofInstallerByFileName(proof, fileName);
            return artifact is null
                ? NotFound()
                : BuildWindowsProofArtifactFileResult(proof, artifact);
        }

        if (!_windowsProofInstallers.LegacyShelfFallbackEnabled)
        {
            return NotFound();
        }

        ReleaseShelfSnapshot? legacy = TryCaptureGeneration(generationId);
        return legacy is null
            ? NotFound()
            : DownloadLegacyWindowsProofInstaller(legacy, fileName, byArtifactId: false);
    }

    [HttpGet("/downloads/proof/windows/current/installers/{artifactId}")]
    [HttpHead("/downloads/proof/windows/current/installers/{artifactId}")]
    public IActionResult DownloadWindowsProofInstallerByArtifactId([FromRoute] string artifactId)
    {
        WindowsProofDeliverySnapshot? proof = _windowsProofInstallers.CaptureCurrentProof();
        if (proof is not null)
        {
            WindowsProofDeliveryArtifact? artifact = _windowsProofInstallers.FindProofArtifact(
                proof,
                artifactId,
                WindowsProofDeliveryRoles.Installer);
            return artifact is null
                ? NotFound()
                : BuildWindowsProofArtifactFileResult(proof, artifact);
        }

        return _windowsProofInstallers.LegacyShelfFallbackEnabled
            ? DownloadLegacyWindowsProofInstaller(_releases.CaptureShelfSnapshot(), artifactId, byArtifactId: true)
            : NotFound();
    }

    [HttpGet("/downloads/proof/windows/generations/{generationId}/installers/{artifactId}")]
    [HttpHead("/downloads/proof/windows/generations/{generationId}/installers/{artifactId}")]
    public IActionResult DownloadGenerationWindowsProofInstallerByArtifactId(
        [FromRoute] string generationId,
        [FromRoute] string artifactId)
    {
        WindowsProofDeliverySnapshot? proof = _windowsProofInstallers.CaptureProofGeneration(generationId);
        if (proof is not null)
        {
            WindowsProofDeliveryArtifact? artifact = _windowsProofInstallers.FindProofArtifact(
                proof,
                artifactId,
                WindowsProofDeliveryRoles.Installer);
            return artifact is null
                ? NotFound()
                : BuildWindowsProofArtifactFileResult(proof, artifact);
        }

        if (!_windowsProofInstallers.LegacyShelfFallbackEnabled)
        {
            return NotFound();
        }

        ReleaseShelfSnapshot? legacy = TryCaptureGeneration(generationId);
        return legacy is null
            ? NotFound()
            : DownloadLegacyWindowsProofInstaller(legacy, artifactId, byArtifactId: true);
    }

    [HttpGet("/downloads/proof/windows/current/artifacts/{artifactId}/{role}")]
    [HttpHead("/downloads/proof/windows/current/artifacts/{artifactId}/{role}")]
    public IActionResult DownloadCurrentWindowsProofArtifact(
        [FromRoute] string artifactId,
        [FromRoute] string role)
    {
        WindowsProofDeliverySnapshot? proof = _windowsProofInstallers.CaptureCurrentProof();
        if (proof is null)
        {
            return NotFound();
        }

        WindowsProofDeliveryArtifact? artifact =
            _windowsProofInstallers.FindProofArtifact(proof, artifactId, role);
        return artifact is null
            ? NotFound()
            : BuildWindowsProofArtifactFileResult(proof, artifact);
    }

    [HttpGet("/downloads/proof/windows/generations/{generationId}/artifacts/{artifactId}/{role}")]
    [HttpHead("/downloads/proof/windows/generations/{generationId}/artifacts/{artifactId}/{role}")]
    public IActionResult DownloadGenerationWindowsProofArtifact(
        [FromRoute] string generationId,
        [FromRoute] string artifactId,
        [FromRoute] string role)
    {
        WindowsProofDeliverySnapshot? proof =
            _windowsProofInstallers.CaptureProofGeneration(generationId);
        if (proof is null)
        {
            return NotFound();
        }

        WindowsProofDeliveryArtifact? artifact =
            _windowsProofInstallers.FindProofArtifact(proof, artifactId, role);
        return artifact is null
            ? NotFound()
            : BuildWindowsProofArtifactFileResult(proof, artifact);
    }

    [HttpGet("/downloads/proof/windows/candidates/{candidateVersion}/artifacts/{artifactId}/{role}")]
    [HttpHead("/downloads/proof/windows/candidates/{candidateVersion}/artifacts/{artifactId}/{role}")]
    public IActionResult DownloadCandidateWindowsProofArtifact(
        [FromRoute] string candidateVersion,
        [FromRoute] string artifactId,
        [FromRoute] string role)
    {
        WindowsProofDeliverySnapshot? proof =
            _windowsProofInstallers.CaptureProofCandidate(candidateVersion);
        if (proof is null)
        {
            return NotFound();
        }

        WindowsProofDeliveryArtifact? artifact =
            _windowsProofInstallers.FindProofArtifact(proof, artifactId, role);
        return artifact is null
            ? NotFound()
            : BuildWindowsProofArtifactFileResult(proof, artifact);
    }

    [HttpGet("/downloads/proof/windows/candidates/{candidateVersion}/files/{fileName}")]
    [HttpHead("/downloads/proof/windows/candidates/{candidateVersion}/files/{fileName}")]
    public IActionResult DownloadCandidateWindowsProofFile(
        [FromRoute] string candidateVersion,
        [FromRoute] string fileName)
    {
        WindowsProofDeliverySnapshot? proof =
            _windowsProofInstallers.CaptureProofCandidate(candidateVersion);
        if (proof is null)
        {
            return NotFound();
        }

        WindowsProofDeliveryArtifact? artifact =
            _windowsProofInstallers.FindProofArtifactByFileName(proof, fileName);
        return artifact is null
            ? NotFound()
            : BuildWindowsProofArtifactFileResult(proof, artifact);
    }

    [HttpGet("/downloads/proof/windows/candidates/{candidateVersion}/{role}")]
    [HttpHead("/downloads/proof/windows/candidates/{candidateVersion}/{role}")]
    public IActionResult DownloadCandidateWindowsProofRole(
        [FromRoute] string candidateVersion,
        [FromRoute] string role)
        => DownloadUniqueCandidateWindowsProofRole(candidateVersion, role, evidenceOnly: false);

    [HttpGet("/downloads/proof/windows/candidates/{candidateVersion}/evidence/{role}")]
    [HttpHead("/downloads/proof/windows/candidates/{candidateVersion}/evidence/{role}")]
    public IActionResult DownloadCandidateWindowsProofEvidence(
        [FromRoute] string candidateVersion,
        [FromRoute] string role)
        => DownloadUniqueCandidateWindowsProofRole(candidateVersion, role, evidenceOnly: true);

    private IActionResult DownloadUniqueCandidateWindowsProofRole(
        string candidateVersion,
        string role,
        bool evidenceOnly)
    {
        WindowsProofDeliverySnapshot? proof =
            _windowsProofInstallers.CaptureProofCandidate(candidateVersion);
        if (proof is null)
        {
            return NotFound();
        }

        WindowsProofDeliveryArtifact? artifact =
            _windowsProofInstallers.FindUniqueProofArtifactByRole(proof, role);
        if (artifact is null)
        {
            return NotFound();
        }

        bool isPrimaryAsset = artifact.Role is WindowsProofDeliveryRoles.Installer
            or WindowsProofDeliveryRoles.BootstrapPayload
            or WindowsProofDeliveryRoles.BootstrapMetadata;
        if (evidenceOnly == isPrimaryAsset)
        {
            return NotFound();
        }

        return BuildWindowsProofArtifactFileResult(proof, artifact);
    }

    private IActionResult BuildWindowsProofCatalog(WindowsProofDeliverySnapshot proof)
    {
        ArtifactDeliveryDecision? denied = proof.Artifacts
            .Select(artifact => _artifactDelivery.EvaluateGlobalRevocation(artifact.ArtifactId, artifact.Sha256))
            .FirstOrDefault(static decision => !decision.Allowed);
        if (denied is not null)
        {
            return ArtifactDeliveryDenied(denied);
        }

        TryApplyWindowsProofHeaders(proof);
        WindowsProofDeliveryArtifact[] installers = proof.Artifacts
            .Where(static artifact => string.Equals(
                artifact.Role,
                WindowsProofDeliveryRoles.Installer,
                StringComparison.Ordinal))
            .ToArray();
        if (installers.Length == 0)
        {
            return WindowsProofMissing();
        }

        return Ok(new
        {
            status = "proof_only",
            supportabilityState = "review_required",
            publicTrustPosture = "blocked",
            canonicalRelease = false,
            cfAccessGated = true,
            generationId = proof.GenerationId,
            candidateVersion = proof.CandidateVersion,
            proof.CreatedAt,
            proof.ActivatedAt,
            proof.RevocationGeneration,
            message = "Private Windows test candidate. This is not the canonical release shelf and must not be treated as a supported or stable build.",
            downloads = installers.Select(installer => new
            {
                installer.ArtifactId,
                installer.FileName,
                installer.Head,
                installer.Rid,
                installer.Sha256,
                installer.SizeBytes,
                installer.CurrentDownloadUrl,
                installer.GenerationDownloadUrl,
                installer.CandidateDownloadUrl,
                payloadUrl = FindSiblingProofUrl(proof, installer.ArtifactId, WindowsProofDeliveryRoles.BootstrapPayload),
                metadataUrl = FindSiblingProofUrl(proof, installer.ArtifactId, WindowsProofDeliveryRoles.BootstrapMetadata),
                signingEvidenceUrl = FindSiblingProofUrl(proof, installer.ArtifactId, WindowsProofDeliveryRoles.Signing),
                startupSmokeEvidenceUrl = FindSiblingProofUrl(proof, installer.ArtifactId, WindowsProofDeliveryRoles.StartupSmoke),
                visualHandoffUrl = FindSiblingProofUrl(proof, installer.ArtifactId, WindowsProofDeliveryRoles.VisualHandoff),
                visualExitEvidenceUrl = FindSiblingProofUrl(proof, installer.ArtifactId, WindowsProofDeliveryRoles.VisualExit)
            })
        });
    }

    private static string? FindSiblingProofUrl(
        WindowsProofDeliverySnapshot proof,
        string artifactId,
        string role)
        => proof.Artifacts.FirstOrDefault(artifact =>
            string.Equals(artifact.ArtifactId, artifactId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(artifact.Role, role, StringComparison.Ordinal))?.CandidateDownloadUrl;

    private IActionResult BuildWindowsProofArtifactFileResult(
        WindowsProofDeliverySnapshot proof,
        WindowsProofDeliveryArtifact artifact)
    {
        ArtifactDeliveryDecision delivery = _artifactDelivery.EvaluateGlobalRevocation(
            artifact.ArtifactId,
            artifact.Sha256);
        if (!delivery.Allowed)
        {
            return ArtifactDeliveryDenied(delivery);
        }

        Stream? stream = _windowsProofInstallers.OpenVerifiedProofArtifact(proof, artifact);
        if (stream is null)
        {
            return NotFound();
        }

        TryApplyWindowsProofHeaders(proof);
        bool enableRanges = string.Equals(
                artifact.Role,
                WindowsProofDeliveryRoles.Installer,
                StringComparison.Ordinal)
            || string.Equals(
                artifact.Role,
                WindowsProofDeliveryRoles.BootstrapPayload,
                StringComparison.Ordinal);
        return File(
            stream,
            artifact.ContentType,
            artifact.FileName,
            enableRangeProcessing: enableRanges);
    }

    private void TryApplyWindowsProofHeaders(WindowsProofDeliverySnapshot proof)
    {
        if (ControllerContext.HttpContext is not HttpContext httpContext)
        {
            return;
        }

        ApplyCanonicalManifestNoStoreHeaders(httpContext.Response.Headers);
        httpContext.Response.Headers["Referrer-Policy"] = "no-referrer";
        httpContext.Response.Headers["X-Content-Type-Options"] = "nosniff";
        httpContext.Response.Headers["X-Robots-Tag"] = "noindex, nofollow, noarchive";
        httpContext.Response.Headers["X-Chummer-Install-Tier"] = "proof_only";
        httpContext.Response.Headers["X-Chummer-Supportability-State"] = "review_required";
        httpContext.Response.Headers["X-Chummer-Public-Trust-Posture"] = "blocked";
        httpContext.Response.Headers["X-Chummer-Canonical-Release"] = "false";
        httpContext.Response.Headers["X-Chummer-Windows-Proof-Generation"] = proof.GenerationId;
        httpContext.Response.Headers["X-Chummer-Windows-Proof-Candidate"] = proof.CandidateVersion;
    }

    private IActionResult BuildLegacyWindowsProofCatalog(ReleaseShelfSnapshot snapshot)
    {
        TryApplyGenerationHeader(snapshot);
        IReadOnlyList<WindowsProofInstallerRecord> installers =
            _windowsProofInstallers.LoadCatalog(snapshot);
        ArtifactDeliveryDecision? invalidDecision = installers
            .Select(installer => _artifactDelivery.EvaluateGlobalRevocation(installer.ArtifactId, installer.Sha256))
            .FirstOrDefault(static decision => decision.Failure is ArtifactDeliveryFailure.InvalidContract
                or ArtifactDeliveryFailure.RevocationTruthUnavailable);
        if (invalidDecision is not null)
        {
            return ArtifactDeliveryDenied(invalidDecision);
        }

        installers = installers
            .Where(installer => _artifactDelivery.EvaluateGlobalRevocation(installer.ArtifactId, installer.Sha256).Allowed)
            .ToArray();
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

    private IActionResult DownloadLegacyWindowsProofInstaller(
        ReleaseShelfSnapshot snapshot,
        string value,
        bool byArtifactId)
    {
        WindowsProofInstallerRecord? installer = byArtifactId
            ? _windowsProofInstallers.FindByArtifactId(snapshot, value)
            : _windowsProofInstallers.FindByFileName(snapshot, value);
        if (installer is null)
        {
            return NotFound();
        }

        ArtifactDeliveryDecision delivery = _artifactDelivery.EvaluateGlobalRevocation(
            installer.ArtifactId,
            installer.Sha256);
        if (!delivery.Allowed)
        {
            return ArtifactDeliveryDenied(delivery);
        }

        TryApplyGenerationHeader(snapshot);
        ApplyProofInstallerHeaders(Response.Headers);
        return BuildWindowsProofInstallerFileResult(snapshot, installer);
    }

    private IActionResult WindowsProofMissing()
        => NotFound(new
        {
            status = "missing",
            message = "No private Windows proof candidate is available right now."
        });

    private static void ApplyProofInstallerHeaders(IHeaderDictionary headers)
    {
        headers["Cache-Control"] = "private, no-store, max-age=0";
        headers["CDN-Cache-Control"] = "no-store, max-age=0";
        headers["Cloudflare-CDN-Cache-Control"] = "no-store, max-age=0";
        headers["Surrogate-Control"] = "no-store";
        headers["Pragma"] = "no-cache";
        headers["Expires"] = "0";
        headers["X-Chummer-Install-Tier"] = "supplemental";
        headers["X-Content-Type-Options"] = "nosniff";
    }

    private IActionResult BuildWindowsProofInstallerFileResult(
        ReleaseShelfSnapshot snapshot,
        WindowsProofInstallerRecord installer)
    {
        ReleaseShelfVerifiedFile? verified = _windowsProofInstallers.OpenVerifiedInstaller(
            snapshot,
            installer);
        if (verified is null)
        {
            return NotFound();
        }

        // FileStreamResult owns the still-verified descriptor for the response lifetime.
        return File(
            verified.Stream,
            "application/octet-stream",
            installer.FileName,
            enableRangeProcessing: true);
    }

    private static void ApplyCanonicalManifestNoStoreHeaders(IHeaderDictionary headers)
    {
        headers["Cache-Control"] = "private, no-store, max-age=0";
        headers["CDN-Cache-Control"] = "no-store, max-age=0";
        headers["Cloudflare-CDN-Cache-Control"] = "no-store, max-age=0";
        headers["Surrogate-Control"] = "no-store";
        headers["Pragma"] = "no-cache";
        headers["Expires"] = "0";
    }

    private static void ApplyCredentialResponseNoStoreHeaders(IHeaderDictionary headers)
    {
        ApplyCanonicalManifestNoStoreHeaders(headers);
        headers["Referrer-Policy"] = "no-referrer";
    }

    private static bool HasCredentialQuery(HttpRequest request)
        => request.Query.ContainsKey("ticket") || request.Query.ContainsKey("claimCode");

    private void TryApplyCredentialResponseNoStoreHeaders()
    {
        if (ControllerContext.HttpContext is not HttpContext httpContext
            || !HasCredentialQuery(Request))
        {
            return;
        }

        ApplyCredentialResponseNoStoreHeaders(httpContext.Response.Headers);
    }

    private static void ApplyGenerationHeader(
        IHeaderDictionary headers,
        ReleaseShelfSnapshot snapshot)
    {
        if (!string.IsNullOrWhiteSpace(snapshot.GenerationId))
        {
            headers["X-Chummer-Release-Generation"] = snapshot.GenerationId;
        }
    }

    private void TryApplyCanonicalManifestNoStoreHeaders(ReleaseShelfSnapshot snapshot)
    {
        if (ControllerContext.HttpContext is not HttpContext httpContext)
        {
            return;
        }

        ApplyCanonicalManifestNoStoreHeaders(httpContext.Response.Headers);
        ApplyGenerationHeader(httpContext.Response.Headers, snapshot);
    }

    private void TryApplyGenerationHeader(ReleaseShelfSnapshot snapshot)
    {
        if (ControllerContext.HttpContext is HttpContext httpContext)
        {
            ApplyGenerationHeader(httpContext.Response.Headers, snapshot);
        }
    }

    private void TryApplyImmutableGenerationHeaders()
    {
        if (ControllerContext.HttpContext is HttpContext httpContext)
        {
            if (HasCredentialQuery(httpContext.Request))
            {
                ApplyCredentialResponseNoStoreHeaders(httpContext.Response.Headers);
            }
            else
            {
                httpContext.Response.Headers["Cache-Control"] = "public, max-age=31536000, immutable";
            }
        }
    }

    private ReleaseShelfSnapshot? TryCaptureGeneration(string generationId)
    {
        try
        {
            return _releases.CaptureShelfGeneration(generationId);
        }
        catch (InvalidDataException)
        {
            return null;
        }
        catch (InvalidOperationException)
        {
            return null;
        }
    }

    [HttpGet("/downloads/get/{artifactId}")]
    public async Task<IActionResult> DownloadArtifact([FromRoute] string artifactId, CancellationToken cancellationToken)
    {
        TryApplyCredentialResponseNoStoreHeaders();
        ReleaseShelfSnapshot snapshot = _releases.CaptureShelfSnapshot();
        TryApplyGenerationHeader(snapshot);
        ArtifactDeliveryResolution resolution = _artifactDelivery.ResolveByArtifactId(snapshot, artifactId);
        if (!resolution.Allowed)
        {
            return ArtifactDeliveryDenied(resolution);
        }

        ArtifactDeliveryBinding binding = resolution.Binding!;
        PublicReleaseManifestDto manifest = binding.Manifest;
        PublicReleaseArtifactDto artifact = binding.Artifact;

        var encodedArtifactId = Uri.EscapeDataString(artifact.Id);
        var subject = await TryGetOptionalSubjectAsync(cancellationToken);
        bool requiresAccount = binding.RequiresAccount;
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

        return BuildVerifiedArtifactFileResult(
            binding,
            "application/octet-stream",
            binding.FileName,
            enableRangeProcessing: true);
    }

    [HttpGet("/downloads/file/{artifactId}")]
    public async Task<IActionResult> DownloadResolvedArtifactFile([FromRoute] string artifactId, CancellationToken cancellationToken)
    {
        TryApplyCredentialResponseNoStoreHeaders();
        ReleaseShelfSnapshot snapshot = _releases.CaptureShelfSnapshot();
        TryApplyGenerationHeader(snapshot);
        ArtifactDeliveryResolution resolution = _artifactDelivery.ResolveByArtifactId(snapshot, artifactId);
        if (!resolution.Allowed)
        {
            return ArtifactDeliveryDenied(resolution);
        }

        ArtifactDeliveryBinding binding = resolution.Binding!;
        PublicReleaseArtifactDto artifact = binding.Artifact;

        if (ControllerContext?.HttpContext is null)
        {
            return NotFound();
        }

        string? bootstrapTicket = Request.Query["ticket"].ToString();
        if (!string.IsNullOrWhiteSpace(bootstrapTicket))
        {
            if (_installBootstrapTickets.TryValidateForArtifactRole(
                    bootstrapTicket,
                    artifact.Id,
                    binding.Role,
                    snapshot.GenerationId,
                    binding.Sha256,
                    allowLegacyUnbound: snapshot.IsLegacy,
                    out _))
            {
                Response.Headers["Cache-Control"] = "private, no-store";
                return BuildVerifiedArtifactFileResult(
                    binding,
                    "application/octet-stream",
                    binding.FileName,
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
            if (_installLinking.CanDownloadArtifactWithClaimCode(
                    artifact.Id,
                    snapshot.GenerationId,
                    artifact.Sha256,
                    allowLegacyUnbound: snapshot.IsLegacy,
                    claimCode))
            {
                Response.Headers["Cache-Control"] = "private, no-store";
                return BuildVerifiedArtifactFileResult(
                    binding,
                    "application/octet-stream",
                    binding.FileName,
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
        if (subject is null && binding.RequiresAccount)
        {
            return Redirect(BuildInstallLoginHref(artifact));
        }

        ApplyRouteProofHeaders(
            Response.Headers,
            "No current release status record is attached to the artifact download output route.",
            $"/downloads/file/{Uri.EscapeDataString(artifact.Id)}",
            "/downloads/file/{artifactId}",
            $"/downloads/install/{Uri.EscapeDataString(artifact.Id)}");
        return BuildVerifiedArtifactFileResult(
            binding,
            "application/octet-stream",
            binding.FileName,
            enableRangeProcessing: true);
    }

    [HttpGet("/downloads/files/{**path}")]
    public async Task<IActionResult> DownloadFile([FromRoute] string? path, CancellationToken cancellationToken)
    {
        TryApplyCredentialResponseNoStoreHeaders();
        ReleaseShelfSnapshot snapshot = _releases.CaptureShelfSnapshot();
        return await DownloadFileFromSnapshot(snapshot, path, generationBound: false, cancellationToken);
    }

    [HttpGet("/downloads/install/{artifactId}/payload")]
    [HttpHead("/downloads/install/{artifactId}/payload")]
    public Task<IActionResult> DownloadCurrentArtifactPayload(
        [FromRoute] string artifactId,
        CancellationToken cancellationToken)
    {
        TryApplyCredentialResponseNoStoreHeaders();
        return DownloadArtifactRoleFromSnapshot(
            _releases.CaptureShelfSnapshot(),
            artifactId,
            ArtifactDeliveryRoles.Payload,
            retainedRawPath: false,
            cancellationToken);
    }

    [HttpGet("/downloads/install/{artifactId}/metadata")]
    [HttpHead("/downloads/install/{artifactId}/metadata")]
    public Task<IActionResult> DownloadCurrentArtifactPayloadMetadata(
        [FromRoute] string artifactId,
        CancellationToken cancellationToken)
    {
        TryApplyCredentialResponseNoStoreHeaders();
        return DownloadArtifactRoleFromSnapshot(
            _releases.CaptureShelfSnapshot(),
            artifactId,
            ArtifactDeliveryRoles.PayloadMetadata,
            retainedRawPath: false,
            cancellationToken);
    }

    [HttpGet("/downloads/g/{generationId}/install/{artifactId}")]
    [HttpHead("/downloads/g/{generationId}/install/{artifactId}")]
    public async Task<IActionResult> DownloadGenerationArtifact(
        [FromRoute] string generationId,
        [FromRoute] string artifactId,
        CancellationToken cancellationToken)
    {
        TryApplyCredentialResponseNoStoreHeaders();
        ReleaseShelfSnapshot? snapshot = TryCaptureGeneration(generationId);
        if (snapshot is null)
        {
            return NotFound();
        }

        TryApplyGenerationHeader(snapshot);
        ArtifactDeliveryResolution resolution = _artifactDelivery.ResolveByArtifactId(snapshot, artifactId);
        if (!resolution.Allowed)
        {
            return ArtifactDeliveryDenied(resolution);
        }

        ArtifactDeliveryBinding binding = resolution.Binding!;
        PublicReleaseManifestDto manifest = binding.Manifest;
        PublicReleaseArtifactDto artifact = binding.Artifact;
        string fileName = binding.FileName;
        if (!binding.RequiresAccount)
        {
            TryApplyImmutableGenerationHeaders();
            return BuildVerifiedArtifactFileResult(
                binding,
                ResolveDirectFileContentType(fileName, matchedBootstrapSidecar: false),
                fileName,
                enableRangeProcessing: true);
        }

        Response.Headers["Cache-Control"] = "private, no-store";
        string? bootstrapTicket = Request.Query["ticket"].ToString();
        if (!string.IsNullOrWhiteSpace(bootstrapTicket))
        {
            if (!_installBootstrapTickets.TryValidateForArtifactRole(
                    bootstrapTicket,
                    artifact.Id,
                    binding.Role,
                    snapshot.GenerationId,
                    binding.Sha256,
                    allowLegacyUnbound: false,
                    out _))
            {
                return Unauthorized(new
                {
                    error = "invalid_or_expired_install_ticket",
                    message = "The install command expired. Open the signed-in Downloads page and copy a fresh install command."
                });
            }

            return BuildVerifiedArtifactFileResult(
                binding,
                ResolveDirectFileContentType(fileName, matchedBootstrapSidecar: false),
                fileName,
                enableRangeProcessing: true);
        }

        string? claimCode = Request.Query["claimCode"].ToString();
        if (!string.IsNullOrWhiteSpace(claimCode))
        {
            if (!_installLinking.CanDownloadArtifactWithClaimCode(
                    artifact.Id,
                    snapshot.GenerationId,
                    artifact.Sha256,
                    allowLegacyUnbound: false,
                    claimCode))
            {
                return Unauthorized(new
                {
                    error = "invalid_or_expired_claim_code",
                    message = "The claim code for this download is no longer valid. Open the signed-in Downloads page and request a fresh install."
                });
            }

            return BuildVerifiedArtifactFileResult(
                binding,
                ResolveDirectFileContentType(fileName, matchedBootstrapSidecar: false),
                fileName,
                enableRangeProcessing: true);
        }

        AuthenticatedHubSubject? subject = await TryGetOptionalSubjectAsync(cancellationToken);
        if (subject is null)
        {
            string nextPath = $"/downloads/g/{Uri.EscapeDataString(snapshot.GenerationId!)}/install/{Uri.EscapeDataString(artifact.Id)}";
            return Redirect($"/login?next={Uri.EscapeDataString(nextPath)}");
        }

        DownloadDispatchResult dispatch = _installLinking.IssueDownload(
            manifest,
            artifact,
            userId: null,
            subjectId: subject.SubjectId);
        if (dispatch.ClaimTicket is null)
        {
            return StatusCode(StatusCodes.Status409Conflict, new
            {
                error = "generation_bound_credential_unavailable",
                message = "A generation-bound install credential could not be issued. Open Downloads and try again."
            });
        }

        Response.Headers["X-Chummer-Download-Receipt-Id"] = dispatch.Receipt.ReceiptId;
        return BuildVerifiedArtifactFileResult(
            binding,
            ResolveDirectFileContentType(fileName, matchedBootstrapSidecar: false),
            fileName,
            enableRangeProcessing: true);
    }

    [HttpGet("/downloads/g/{generationId}/files/{**path}")]
    public async Task<IActionResult> DownloadGenerationFile(
        [FromRoute] string generationId,
        [FromRoute] string? path,
        CancellationToken cancellationToken)
    {
        TryApplyCredentialResponseNoStoreHeaders();
        ReleaseShelfSnapshot snapshot;
        try
        {
            snapshot = _releases.CaptureShelfGeneration(generationId);
        }
        catch (InvalidDataException)
        {
            return NotFound();
        }
        catch (InvalidOperationException)
        {
            return NotFound();
        }

        return await DownloadFileFromSnapshot(snapshot, path, generationBound: true, cancellationToken);
    }

    [HttpGet("/downloads/g/{generationId}/install/{artifactId}/payload")]
    [HttpHead("/downloads/g/{generationId}/install/{artifactId}/payload")]
    public Task<IActionResult> DownloadGenerationArtifactPayload(
        [FromRoute] string generationId,
        [FromRoute] string artifactId,
        CancellationToken cancellationToken)
        => DownloadGenerationArtifactRole(generationId, artifactId, ArtifactDeliveryRoles.Payload, cancellationToken);

    [HttpGet("/downloads/g/{generationId}/install/{artifactId}/metadata")]
    [HttpHead("/downloads/g/{generationId}/install/{artifactId}/metadata")]
    public Task<IActionResult> DownloadGenerationArtifactPayloadMetadata(
        [FromRoute] string generationId,
        [FromRoute] string artifactId,
        CancellationToken cancellationToken)
        => DownloadGenerationArtifactRole(generationId, artifactId, ArtifactDeliveryRoles.PayloadMetadata, cancellationToken);

    private Task<IActionResult> DownloadGenerationArtifactRole(
        string generationId,
        string artifactId,
        string role,
        CancellationToken cancellationToken)
    {
        TryApplyCredentialResponseNoStoreHeaders();
        ReleaseShelfSnapshot? snapshot = TryCaptureGeneration(generationId);
        return snapshot is null
            ? Task.FromResult<IActionResult>(NotFound())
            : DownloadArtifactRoleFromSnapshot(snapshot, artifactId, role, retainedRawPath: false, cancellationToken);
    }

    private async Task<IActionResult> DownloadArtifactRoleFromSnapshot(
        ReleaseShelfSnapshot snapshot,
        string artifactId,
        string role,
        bool retainedRawPath,
        CancellationToken cancellationToken)
    {
        ArtifactDeliveryResolution resolution = _artifactDelivery.ResolveByArtifactId(snapshot, artifactId, role);
        return !resolution.Allowed
            ? ArtifactDeliveryDenied(resolution)
            : await DownloadResolvedBindingFromSnapshot(
                resolution.Binding!,
                retainedRawPath,
                cancellationToken);
    }

    private async Task<IActionResult> DownloadFileFromSnapshot(
        ReleaseShelfSnapshot snapshot,
        string? path,
        bool generationBound,
        CancellationToken cancellationToken)
    {
        ArtifactDeliveryResolution resolution = _artifactDelivery.ResolveByPath(snapshot, path);
        if (resolution.Failure == ArtifactDeliveryFailure.NotFound)
        {
            return DownloadAurPackageFile(snapshot, path);
        }

        if (!resolution.Allowed)
        {
            return ArtifactDeliveryDenied(resolution);
        }

        return await DownloadResolvedBindingFromSnapshot(
            resolution.Binding!,
            retainedRawPath: generationBound,
            cancellationToken);
    }

    private async Task<IActionResult> DownloadResolvedBindingFromSnapshot(
        ArtifactDeliveryBinding binding,
        bool retainedRawPath,
        CancellationToken cancellationToken)
    {
        ReleaseShelfSnapshot snapshot = binding.Snapshot;
        PublicReleaseArtifactDto artifact = binding.Artifact;
        TryApplyGenerationHeader(snapshot);
        if (ControllerContext?.HttpContext is null)
        {
            return NotFound();
        }

        string? bootstrapTicket = Request.Query["ticket"].ToString();
        if (!string.IsNullOrWhiteSpace(bootstrapTicket))
        {
            if (_installBootstrapTickets.TryValidateForArtifactRole(
                    bootstrapTicket,
                    artifact.Id,
                    binding.Role,
                    snapshot.GenerationId,
                    binding.Sha256,
                    allowLegacyUnbound: snapshot.IsLegacy,
                    out _))
            {
                Response.Headers["Cache-Control"] = "private, no-store";
                return BuildVerifiedArtifactFileResult(
                    binding,
                    ResolveDirectFileContentType(
                        binding.FileName,
                        binding.Role == ArtifactDeliveryRoles.PayloadMetadata),
                    fileDownloadName: null,
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
            if (binding.Role == ArtifactDeliveryRoles.Primary
                && _installLinking.CanDownloadArtifactWithClaimCode(
                    artifact.Id,
                    snapshot.GenerationId,
                    binding.Sha256,
                    allowLegacyUnbound: snapshot.IsLegacy,
                    claimCode))
            {
                Response.Headers["Cache-Control"] = "private, no-store";
                return BuildVerifiedArtifactFileResult(
                    binding,
                    "application/octet-stream",
                    fileDownloadName: null,
                    enableRangeProcessing: true);
            }

            Response.Headers["Cache-Control"] = "private, no-store";
            return Unauthorized(new
            {
                error = "invalid_or_expired_claim_code",
                message = "The claim code for this download is no longer valid. Re-download the Mac setup script from the signed-in Downloads page."
            });
        }

        if (!binding.RequiresAccount)
        {
            if (!snapshot.IsLegacy)
            {
                TryApplyImmutableGenerationHeaders();
            }

            return BuildVerifiedArtifactFileResult(
                binding,
                ResolveDirectFileContentType(
                    binding.FileName,
                    binding.Role == ArtifactDeliveryRoles.PayloadMetadata),
                fileDownloadName: null,
                enableRangeProcessing: true);
        }

        if (retainedRawPath)
        {
            Response.Headers["Cache-Control"] = "private, no-store";
            return StatusCode(StatusCodes.Status409Conflict, new
            {
                error = "generation_bound_credential_required",
                message = "This retained release generation requires its generation-bound install ticket or claim code. Use the install command issued for this exact release."
            });
        }

        AuthenticatedHubSubject? subject = await TryGetOptionalSubjectAsync(cancellationToken);
        if (subject is null)
        {
            return Redirect(BuildInstallLoginHref(artifact));
        }

        Response.Headers["Cache-Control"] = "private, no-store";
        ApplyRouteProofHeaders(
            Response.Headers,
            "No current release status record is attached to the public file-output route.",
            snapshot.IsLegacy
                ? "/downloads/files/{**path}"
                : $"/downloads/g/{snapshot.GenerationId}/install/{Uri.EscapeDataString(artifact.Id)}",
            $"/downloads/install/{Uri.EscapeDataString(artifact.Id)}");
        return BuildVerifiedArtifactFileResult(
            binding,
            ResolveDirectFileContentType(
                binding.FileName,
                binding.Role == ArtifactDeliveryRoles.PayloadMetadata),
            fileDownloadName: null,
            enableRangeProcessing: true);
    }

    private IActionResult BuildVerifiedArtifactFileResult(
        ArtifactDeliveryBinding binding,
        string contentType,
        string? fileDownloadName,
        bool enableRangeProcessing)
    {
        ReleaseShelfVerifiedFile? verified = _artifactDelivery.OpenVerifiedFile(binding);
        if (verified is null)
        {
            return StatusCode(StatusCodes.Status503ServiceUnavailable, new
            {
                error = "artifact_bytes_unavailable",
                message = "The selected release bytes did not match their exact delivery contract."
            });
        }

        // FileStreamResult owns and disposes the verified stream after the response completes.
        return string.IsNullOrWhiteSpace(fileDownloadName)
            ? File(verified.Stream, contentType, enableRangeProcessing: enableRangeProcessing)
            : File(verified.Stream, contentType, fileDownloadName, enableRangeProcessing: enableRangeProcessing);
    }

    private IActionResult ArtifactDeliveryDenied(ArtifactDeliveryResolution resolution)
        => resolution.Failure switch
        {
            ArtifactDeliveryFailure.NotFound => NotFound(),
            ArtifactDeliveryFailure.Revoked => StatusCode(StatusCodes.Status410Gone, new
            {
                error = resolution.Code,
                message = "This release artifact has been revoked and cannot be downloaded with any credential."
            }),
            _ => StatusCode(StatusCodes.Status503ServiceUnavailable, new
            {
                error = resolution.Code,
                message = "Artifact delivery truth is unavailable or invalid, so the download is blocked."
            })
        };

    private IActionResult ArtifactDeliveryDenied(ArtifactDeliveryDecision decision)
        => decision.Failure switch
        {
            ArtifactDeliveryFailure.Revoked => StatusCode(StatusCodes.Status410Gone, new
            {
                error = decision.Code,
                message = "This release artifact has been revoked and cannot be downloaded with any credential."
            }),
            ArtifactDeliveryFailure.NotFound => NotFound(),
            _ => StatusCode(StatusCodes.Status503ServiceUnavailable, new
            {
                error = decision.Code,
                message = "Artifact delivery truth is unavailable or invalid, so the download is blocked."
            })
        };

    private IActionResult DownloadAurPackageFile(
        ReleaseShelfSnapshot snapshot,
        string? path)
    {
        AurPackageEntry? package = _aurPackages.FindByFileName(snapshot, path);
        if (package is null)
        {
            return NotFound();
        }

        string fileName = Path.GetFileName((path ?? string.Empty).Trim());
        string? packageSha256 = ResolveAurPackageFileSha256(package, fileName);
        if (packageSha256 is null)
        {
            return NotFound();
        }

        ArtifactDeliveryDecision delivery = _artifactDelivery.EvaluateGlobalRevocation(
            package.UpstreamArtifactId,
            package.UpstreamArtifactSha256);
        if (!delivery.Allowed)
        {
            return ArtifactDeliveryDenied(delivery);
        }

        ArtifactDeliveryDecision sidecarDelivery = _artifactDelivery.EvaluateGlobalRevocation(
            package.UpstreamArtifactId,
            packageSha256);
        if (!sidecarDelivery.Allowed)
        {
            return ArtifactDeliveryDenied(sidecarDelivery);
        }

        string? legacyFilePath = snapshot.IsLegacy
            ? _aurPackages.ResolvePackageFilePath(snapshot, fileName)
            : string.Empty;
        if (legacyFilePath is null)
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
        return BuildVerifiedInventoryFileResult(
            snapshot,
            fileName,
            legacyFilePath,
            "application/octet-stream",
            fileName,
            enableRangeProcessing: true);
    }

    private static string? ResolveAurPackageFileSha256(AurPackageEntry package, string fileName)
        => string.Equals(fileName, package.SourceArchiveFileName, StringComparison.Ordinal)
            ? package.SourceArchiveSha256
            : string.Equals(fileName, package.PkgbuildFileName, StringComparison.Ordinal)
                ? package.PkgbuildSha256
                : string.Equals(fileName, package.SrcinfoFileName, StringComparison.Ordinal)
                    ? package.SrcinfoSha256
                    : null;

    private IActionResult BuildVerifiedInventoryFileResult(
        ReleaseShelfSnapshot snapshot,
        string relativeFilePath,
        string legacyPhysicalPath,
        string contentType,
        string? fileDownloadName,
        bool enableRangeProcessing)
    {
        if (snapshot.IsLegacy)
        {
            return string.IsNullOrWhiteSpace(fileDownloadName)
                ? PhysicalFile(legacyPhysicalPath, contentType, enableRangeProcessing: enableRangeProcessing)
                : PhysicalFile(legacyPhysicalPath, contentType, fileDownloadName, enableRangeProcessing: enableRangeProcessing);
        }

        ReleaseShelfVerifiedFile? verified = snapshot.OpenVerifiedFile($"files/{relativeFilePath}");
        if (verified is null)
        {
            return NotFound();
        }

        return string.IsNullOrWhiteSpace(fileDownloadName)
            ? File(verified.Stream, contentType, enableRangeProcessing: enableRangeProcessing)
            : File(verified.Stream, contentType, fileDownloadName, enableRangeProcessing: enableRangeProcessing);
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

    private static string ResolveDirectFileContentType(string fileName, bool matchedBootstrapSidecar)
    {
        if (matchedBootstrapSidecar && fileName.EndsWith(".json", StringComparison.OrdinalIgnoreCase))
        {
            return "application/json; charset=utf-8";
        }

        return "application/octet-stream";
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
