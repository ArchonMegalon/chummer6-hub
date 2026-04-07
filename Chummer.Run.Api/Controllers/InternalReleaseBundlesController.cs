using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class InternalReleaseBundlesController : ControllerBase
{
    private readonly ReleaseBundlePromotionService _promotionService;
    private readonly ReleaseBundleUploadSessionService _uploadSessions;
    private readonly IConfiguration _configuration;
    private readonly ReleaseUploadTicketService _releaseUploadTickets;
    private readonly PublicReleaseManifestService _releaseManifestService;
    private readonly AccountService _accounts;
    private readonly InstallLinkingService _installLinking;

    public InternalReleaseBundlesController(
        ReleaseBundlePromotionService promotionService,
        ReleaseBundleUploadSessionService uploadSessions,
        IConfiguration configuration,
        ReleaseUploadTicketService releaseUploadTickets,
        PublicReleaseManifestService releaseManifestService,
        AccountService accounts,
        InstallLinkingService installLinking)
    {
        _promotionService = promotionService;
        _uploadSessions = uploadSessions;
        _configuration = configuration;
        _releaseUploadTickets = releaseUploadTickets;
        _releaseManifestService = releaseManifestService;
        _accounts = accounts;
        _installLinking = installLinking;
    }

    [HttpPost("/api/internal/releases/bundles")]
    [IgnoreAntiforgeryToken]
    [Consumes("multipart/form-data")]
    [ProducesResponseType<ReleaseBundlePromotionResult>(StatusCodes.Status200OK)]
    public async Task<ActionResult<ReleaseBundlePromotionResult>> UploadBundle(
        [FromForm] IFormFile? bundle,
        CancellationToken cancellationToken)
    {
        ReleaseBundleAuthorizationContext? authorization = RequireInternalAutomationAuth(out ActionResult? denied);
        if (denied is not null)
        {
            return denied;
        }

        if (bundle is null || bundle.Length <= 0)
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Missing release bundle",
                "bundle file is required.",
                "https://chummer.run/problems/release-bundle/missing-parameter");
        }

        try
        {
            await using Stream bundleStream = bundle.OpenReadStream();
            ReleaseBundlePromotionResult result = await _promotionService.PromoteAsync(bundle.FileName, bundleStream, cancellationToken);
            if (authorization?.UploadTicketClaims is not null)
            {
                result = AttachSignedInInstallClaims(result, authorization.UploadTicketClaims);
            }

            return Ok(result);
        }
        catch (Exception ex) when (ex is InvalidDataException or InvalidOperationException or JsonException or NotSupportedException)
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Release bundle rejected",
                ex.Message,
                "https://chummer.run/problems/release-bundle/rejected");
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return BuildProblem(
                StatusCodes.Status503ServiceUnavailable,
                "Release upload infrastructure failure",
                ex.Message,
                "https://chummer.run/problems/release-bundle/unavailable");
        }
    }

    [HttpPost("/api/internal/releases/upload-sessions")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<ReleaseUploadSessionCreatedResponse>(StatusCodes.Status200OK)]
    public ActionResult<ReleaseUploadSessionCreatedResponse> CreateUploadSession()
    {
        ReleaseBundleAuthorizationContext? authorization = RequireInternalAutomationAuth(out ActionResult? denied);
        if (denied is not null)
        {
            return denied;
        }

        ReleaseUploadSession session = _uploadSessions.CreateSession();
        return Ok(new ReleaseUploadSessionCreatedResponse(
            SessionId: session.SessionId,
            ExpiresAtUtc: session.ExpiresAtUtc,
            FilesUrl: BuildAbsoluteRoute($"/api/internal/releases/upload-sessions/{session.SessionId}/files"),
            ChunksUrl: BuildAbsoluteRoute($"/api/internal/releases/upload-sessions/{session.SessionId}/chunks"),
            CompleteUrl: BuildAbsoluteRoute($"/api/internal/releases/upload-sessions/{session.SessionId}/complete")));
    }

    [HttpPost("/api/internal/releases/upload-sessions/{sessionId}/files")]
    [IgnoreAntiforgeryToken]
    [Consumes("multipart/form-data")]
    [ProducesResponseType<ReleaseUploadFileStoredResponse>(StatusCodes.Status200OK)]
    public async Task<ActionResult<ReleaseUploadFileStoredResponse>> UploadSessionFile(
        [FromRoute] string sessionId,
        [FromForm] IFormFile? file,
        [FromForm(Name = "path")] string? relativePath,
        CancellationToken cancellationToken)
    {
        ReleaseBundleAuthorizationContext? authorization = RequireInternalAutomationAuth(out ActionResult? denied);
        if (denied is not null)
        {
            return denied;
        }

        if (string.IsNullOrWhiteSpace(sessionId))
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session file rejected",
                "sessionId is required.",
                "https://chummer.run/problems/release-bundle/missing-parameter");
        }

        if (!Guid.TryParse(sessionId, out _))
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session file rejected",
                "sessionId must be a valid GUID.",
                "https://chummer.run/problems/release-bundle/invalid-session-id");
        }

        string uploadPath;
        ActionResult? pathProblem = ResolveSessionUploadPath(relativePath, nameof(relativePath), out uploadPath);
        if (pathProblem is not null)
        {
            return pathProblem;
        }

        if (file is null || file.Length <= 0)
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session file rejected",
                "file is required.",
                "https://chummer.run/problems/release-bundle/missing-parameter");
        }

        try
        {
            await using Stream content = file.OpenReadStream();
            long bytesStored = await _uploadSessions.WriteFileAsync(sessionId, uploadPath, content, cancellationToken);
            return Ok(new ReleaseUploadFileStoredResponse(uploadPath, bytesStored));
        }
        catch (Exception ex) when (ex is InvalidDataException or IOException or UnauthorizedAccessException)
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session file rejected",
                ex.Message,
                "https://chummer.run/problems/release-bundle/rejected");
        }
    }

    [HttpPost("/api/internal/releases/upload-sessions/{sessionId}/chunks")]
    [IgnoreAntiforgeryToken]
    [Consumes("multipart/form-data")]
    [ProducesResponseType<ReleaseUploadChunkStoredResponse>(StatusCodes.Status200OK)]
    public async Task<ActionResult<ReleaseUploadChunkStoredResponse>> UploadSessionChunk(
        [FromRoute] string sessionId,
        [FromForm] IFormFile? chunk,
        [FromForm(Name = "path")] string? relativePath,
        [FromForm(Name = "index")] int chunkIndex,
        [FromForm(Name = "total")] int totalChunks,
        CancellationToken cancellationToken)
    {
        ReleaseBundleAuthorizationContext? authorization = RequireInternalAutomationAuth(out ActionResult? denied);
        if (denied is not null)
        {
            return denied;
        }

        if (string.IsNullOrWhiteSpace(sessionId))
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session chunk rejected",
                "sessionId is required.",
                "https://chummer.run/problems/release-bundle/missing-parameter");
        }

        if (!Guid.TryParse(sessionId, out _))
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session chunk rejected",
                "sessionId must be a valid GUID.",
                "https://chummer.run/problems/release-bundle/invalid-session-id");
        }

        if (chunkIndex < 0)
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session chunk rejected",
                "chunk index must be zero or greater.",
                "https://chummer.run/problems/release-bundle/invalid-parameter");
        }

        if (totalChunks <= 0)
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session chunk rejected",
                "total must be greater than zero.",
                "https://chummer.run/problems/release-bundle/invalid-parameter");
        }

        if (chunkIndex >= totalChunks)
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session chunk rejected",
                "chunk index must be smaller than total.",
                "https://chummer.run/problems/release-bundle/invalid-parameter");
        }

        string uploadPath;
        ActionResult? pathProblem = ResolveSessionUploadPath(relativePath, nameof(relativePath), out uploadPath);
        if (pathProblem is not null)
        {
            return pathProblem;
        }

        if (chunk is null || chunk.Length <= 0)
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session chunk rejected",
                "chunk is required.",
                "https://chummer.run/problems/release-bundle/missing-parameter");
        }

        try
        {
            await using Stream content = chunk.OpenReadStream();
            ReleaseUploadChunkResult result = await _uploadSessions.AppendChunkAsync(
                sessionId,
                uploadPath,
                chunkIndex,
                totalChunks,
                content,
                cancellationToken);
            return Ok(new ReleaseUploadChunkStoredResponse(
                result.RelativePath,
                result.ChunkIndex,
                result.TotalChunks,
                result.BytesReceived,
                result.Completed));
        }
        catch (Exception ex) when (ex is InvalidDataException or IOException or UnauthorizedAccessException)
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session chunk rejected",
                ex.Message,
                "https://chummer.run/problems/release-bundle/rejected");
        }
    }

    [HttpPost("/api/internal/releases/upload-sessions/{sessionId}/complete")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<ReleaseBundlePromotionResult>(StatusCodes.Status200OK)]
    public async Task<ActionResult<ReleaseBundlePromotionResult>> CompleteUploadSession(
        [FromRoute] string sessionId,
        CancellationToken cancellationToken)
    {
        ReleaseBundleAuthorizationContext? authorization = RequireInternalAutomationAuth(out ActionResult? denied);
        if (denied is not null)
        {
            return denied;
        }

        if (string.IsNullOrWhiteSpace(sessionId))
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session promotion rejected",
                "sessionId is required.",
                "https://chummer.run/problems/release-bundle/missing-parameter");
        }

        if (!Guid.TryParse(sessionId, out _))
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session promotion rejected",
                "sessionId must be a valid GUID.",
                "https://chummer.run/problems/release-bundle/invalid-session-id");
        }

        try
        {
            string bundleRoot = _uploadSessions.ResolveBundleRoot(sessionId);
            ReleaseBundlePromotionResult result = await _promotionService.PromoteDirectoryAsync(bundleRoot, cancellationToken);
            if (authorization?.UploadTicketClaims is not null)
            {
                result = AttachSignedInInstallClaims(result, authorization.UploadTicketClaims);
            }

            _uploadSessions.DeleteSession(sessionId);
            return Ok(result);
        }
        catch (Exception ex) when (ex is InvalidDataException or InvalidOperationException or JsonException or NotSupportedException)
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session promotion rejected",
                ex.Message,
                "https://chummer.run/problems/release-bundle/rejected");
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return BuildProblem(
                StatusCodes.Status503ServiceUnavailable,
                "Release upload infrastructure failure",
                ex.Message,
                "https://chummer.run/problems/release-bundle/unavailable");
        }
    }

    private ReleaseBundleAuthorizationContext? RequireInternalAutomationAuth(out ActionResult? denied)
    {
        denied = null;

        string header = Request.Headers.Authorization.ToString();
        const string bearerPrefix = "Bearer ";
        if (!header.StartsWith(bearerPrefix, StringComparison.OrdinalIgnoreCase))
        {
            denied = BuildProblem(
                StatusCodes.Status401Unauthorized,
                "Release promotion authorization required",
                "internal release promotion authorization is required.",
                "https://chummer.run/problems/release-bundle/auth-required");
            return null;
        }

        string providedToken = header[bearerPrefix.Length..].Trim();
        string expectedToken = (_configuration["FLEET_INTERNAL_API_TOKEN"] ?? string.Empty).Trim();
        if (!string.IsNullOrWhiteSpace(expectedToken) && FixedTimeEquals(providedToken, expectedToken))
        {
            return new ReleaseBundleAuthorizationContext(null);
        }

        if (_releaseUploadTickets.TryValidate(providedToken, out ReleaseUploadTicketClaims? ticketClaims))
        {
            return new ReleaseBundleAuthorizationContext(ticketClaims);
        }

        denied = BuildProblem(
            StatusCodes.Status401Unauthorized,
            "Release promotion authorization required",
            "internal release promotion authorization is required.",
            "https://chummer.run/problems/release-bundle/auth-required");
        return null;
    }

    private ActionResult? ResolveSessionUploadPath(string? relativePath, string fieldName, out string normalizedPath)
    {
        normalizedPath = string.Empty;
        if (string.IsNullOrWhiteSpace(relativePath))
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session path rejected",
                $"{fieldName} is required. Provide a bundle-relative path such as 'releases.json' or 'files/chummer-avalonia-osx-arm64-installer.dmg'.",
                "https://chummer.run/problems/release-bundle/missing-parameter");
        }

        string normalized = relativePath.Replace('\\', '/').Trim();
        if (normalized.StartsWith("/", StringComparison.Ordinal))
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session path rejected",
                $"{fieldName} must be relative and must not start at root.",
                "https://chummer.run/problems/release-bundle/invalid-parameter");
        }

        string[] segments = normalized.Split('/', StringSplitOptions.RemoveEmptyEntries);
        if (segments.Length == 0 || segments.Any(segment => segment == "." || segment == ".."))
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session path rejected",
                $"{fieldName} must be a relative path within the bundle and cannot contain '.' or '..'.",
                "https://chummer.run/problems/release-bundle/invalid-parameter");
        }

        normalizedPath = string.Join('/', segments);
        return null;
    }

    private ReleaseBundlePromotionResult AttachSignedInInstallClaims(
        ReleaseBundlePromotionResult result,
        ReleaseUploadTicketClaims claims)
    {
        if (result.PromotedArtifactIds.Count == 0)
        {
            return result with { SignedInInstallClaims = Array.Empty<ReleasePromotionInstallClaim>() };
        }

        var manifest = _releaseManifestService.LoadManifest();
        var installUrlByArtifactId = result.PromotedArtifactIds
            .Zip(result.InstallDispatchUrls, static (artifactId, installUrl) => new KeyValuePair<string, string>(artifactId, installUrl))
            .ToDictionary(static pair => pair.Key, static pair => pair.Value, StringComparer.OrdinalIgnoreCase);
        var user = _accounts.EnsureUser(claims.SubjectId, claims.DisplayName, claims.Email);
        List<ReleasePromotionInstallClaim> issuedClaims = new();
        foreach (string artifactId in result.PromotedArtifactIds)
        {
            var artifact = manifest.Downloads.FirstOrDefault(item => string.Equals(item.Id, artifactId, StringComparison.OrdinalIgnoreCase));
            if (artifact is null)
            {
                continue;
            }

            var dispatch = _installLinking.IssueDownload(manifest, artifact, user.UserId, claims.SubjectId);
            if (dispatch.ClaimTicket is null)
            {
                continue;
            }

            issuedClaims.Add(new ReleasePromotionInstallClaim(
                ArtifactId: artifactId,
                InstallDispatchUrl: installUrlByArtifactId.TryGetValue(artifactId, out string? installUrl)
                    ? installUrl
                    : $"/downloads/install/{Uri.EscapeDataString(artifactId)}",
                ClaimCode: dispatch.ClaimTicket.ClaimCode,
                ClaimCodeExpiresAtUtc: dispatch.ClaimTicket.ExpiresAtUtc));
        }

        return result with { SignedInInstallClaims = issuedClaims };
    }

    private static bool FixedTimeEquals(string left, string right)
    {
        byte[] leftBytes = Encoding.UTF8.GetBytes(left);
        byte[] rightBytes = Encoding.UTF8.GetBytes(right);
        return CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }

    private ObjectResult BuildProblem(
        int statusCode,
        string title,
        string detail,
        string type)
    {
        return Problem(
            detail: detail,
            statusCode: statusCode,
            title: title,
            type: type,
            instance: $"{Request.Path}#{Request.HttpContext.TraceIdentifier}");
    }

    private string BuildAbsoluteRoute(string path)
        => $"{Request.Scheme}://{Request.Host}{path}";

    private sealed record ReleaseBundleAuthorizationContext(ReleaseUploadTicketClaims? UploadTicketClaims);

    public sealed record ReleaseUploadSessionCreatedResponse(
        string SessionId,
        DateTimeOffset ExpiresAtUtc,
        string FilesUrl,
        string ChunksUrl,
        string CompleteUrl);

    public sealed record ReleaseUploadFileStoredResponse(
        string RelativePath,
        long BytesStored);

    public sealed record ReleaseUploadChunkStoredResponse(
        string RelativePath,
        int ChunkIndex,
        int TotalChunks,
        long BytesReceived,
        bool Completed);
}
