using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.WindowsProof;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

/// <summary>
/// Stages and activates the private, CF-gated Windows native-proof candidate.
/// This controller is intentionally separate from canonical release promotion.
/// </summary>
[ApiController]
public sealed class InternalWindowsProofUploadsController : ControllerBase
{
    private readonly WindowsProofUploadSessionService _sessions;
    private readonly IWindowsProofGenerationStore _store;
    private readonly WindowsProofUploadOptions _options;
    private readonly ILogger<InternalWindowsProofUploadsController> _logger;

    public InternalWindowsProofUploadsController(
        WindowsProofUploadSessionService sessions,
        IWindowsProofGenerationStore store,
        WindowsProofUploadOptions options,
        ILogger<InternalWindowsProofUploadsController> logger)
    {
        _sessions = sessions ?? throw new ArgumentNullException(nameof(sessions));
        _store = store ?? throw new ArgumentNullException(nameof(store));
        _options = options ?? throw new ArgumentNullException(nameof(options));
        _logger = logger ?? throw new ArgumentNullException(nameof(logger));
    }

    [HttpPost("/api/internal/windows-proof/upload-sessions")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<WindowsProofUploadSessionCreatedResponse>(StatusCodes.Status200OK)]
    public ActionResult<WindowsProofUploadSessionCreatedResponse> CreateUploadSession()
    {
        WindowsProofUploadAuthorizationContext? authorization = RequireAuthorization(out ActionResult? denied);
        if (denied is not null)
        {
            return denied;
        }

        try
        {
            WindowsProofUploadSession session = _sessions.CreateSession(
                authorization!.AuthorizationBinding,
                authorization.SingleUseAuthorization,
                authorization.AuthorizationExpiresAtUtc);
            string root = $"/api/internal/windows-proof/upload-sessions/{session.SessionId}";
            return Ok(new WindowsProofUploadSessionCreatedResponse(
                session.SessionId,
                session.State,
                session.ExpiresAtUtc,
                $"{root}/files",
                $"{root}/chunks",
                $"{root}/complete",
                $"{root}/reconcile"));
        }
        catch (Exception ex) when (IsExpected(ex))
        {
            return MapFailure(ex, "Windows proof upload session creation");
        }
    }

    [HttpPost("/api/internal/windows-proof/upload-sessions/{sessionId}/files")]
    [IgnoreAntiforgeryToken]
    [Consumes("multipart/form-data")]
    [ProducesResponseType<WindowsProofUploadFileStoredResponse>(StatusCodes.Status200OK)]
    public async Task<ActionResult<WindowsProofUploadFileStoredResponse>> UploadFile(
        [FromRoute] string sessionId,
        [FromForm] IFormFile? file,
        [FromForm(Name = "path")] string? relativePath,
        CancellationToken cancellationToken)
    {
        WindowsProofUploadAuthorizationContext? authorization = RequireAuthorization(out ActionResult? denied);
        if (denied is not null)
        {
            return denied;
        }
        if (file is null || file.Length <= 0 || string.IsNullOrWhiteSpace(relativePath))
        {
            return ProblemResult(
                StatusCodes.Status400BadRequest,
                "Windows proof upload file rejected",
                "A non-empty file and manifest-bound relative path are required.",
                "invalid-request");
        }
        if (file.Length > _options.MaxChunkBytes)
        {
            return ProblemResult(
                StatusCodes.Status413PayloadTooLarge,
                "Windows proof upload file rejected",
                "Use bounded chunks for files larger than the direct-upload limit.",
                "payload-too-large");
        }

        try
        {
            await using Stream content = file.OpenReadStream();
            long bytes = await _sessions.WriteFileAsync(
                sessionId,
                relativePath,
                content,
                authorization!.AuthorizationBinding,
                cancellationToken);
            return Ok(new WindowsProofUploadFileStoredResponse(relativePath, bytes));
        }
        catch (Exception ex) when (IsExpected(ex))
        {
            return MapFailure(ex, "Windows proof upload file");
        }
    }

    [HttpPost("/api/internal/windows-proof/upload-sessions/{sessionId}/chunks")]
    [IgnoreAntiforgeryToken]
    [Consumes("multipart/form-data")]
    [ProducesResponseType<WindowsProofUploadChunkStoredResponse>(StatusCodes.Status200OK)]
    public async Task<ActionResult<WindowsProofUploadChunkStoredResponse>> UploadChunk(
        [FromRoute] string sessionId,
        [FromForm] IFormFile? chunk,
        [FromForm(Name = "path")] string? relativePath,
        [FromForm(Name = "index")] int chunkIndex,
        [FromForm(Name = "total")] int totalChunks,
        CancellationToken cancellationToken)
    {
        WindowsProofUploadAuthorizationContext? authorization = RequireAuthorization(out ActionResult? denied);
        if (denied is not null)
        {
            return denied;
        }
        if (chunk is null || chunk.Length <= 0 || string.IsNullOrWhiteSpace(relativePath))
        {
            return ProblemResult(
                StatusCodes.Status400BadRequest,
                "Windows proof upload chunk rejected",
                "A non-empty chunk and manifest-bound relative path are required.",
                "invalid-request");
        }
        if (chunk.Length > _options.MaxChunkBytes)
        {
            return ProblemResult(
                StatusCodes.Status413PayloadTooLarge,
                "Windows proof upload chunk rejected",
                "Chunk exceeds the configured bounded-upload limit.",
                "payload-too-large");
        }

        try
        {
            await using Stream content = chunk.OpenReadStream();
            WindowsProofUploadChunkResult result = await _sessions.AppendChunkAsync(
                sessionId,
                relativePath,
                chunkIndex,
                totalChunks,
                content,
                authorization!.AuthorizationBinding,
                cancellationToken);
            return Ok(new WindowsProofUploadChunkStoredResponse(
                result.RelativePath,
                result.ChunkIndex,
                result.TotalChunks,
                result.BytesReceived,
                result.Completed));
        }
        catch (Exception ex) when (IsExpected(ex))
        {
            return MapFailure(ex, "Windows proof upload chunk");
        }
    }

    [HttpPost("/api/internal/windows-proof/upload-sessions/{sessionId}/complete")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<WindowsProofUploadCompletionResult>(StatusCodes.Status200OK)]
    public Task<ActionResult<WindowsProofUploadCompletionResult>> Complete(
        [FromRoute] string sessionId,
        CancellationToken cancellationToken)
        => CompleteOrReconcile(sessionId, cancellationToken);

    [HttpPost("/api/internal/windows-proof/upload-sessions/{sessionId}/reconcile")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<WindowsProofUploadCompletionResult>(StatusCodes.Status200OK)]
    public Task<ActionResult<WindowsProofUploadCompletionResult>> Reconcile(
        [FromRoute] string sessionId,
        CancellationToken cancellationToken)
        => CompleteOrReconcile(sessionId, cancellationToken);

    private async Task<ActionResult<WindowsProofUploadCompletionResult>> CompleteOrReconcile(
        string sessionId,
        CancellationToken cancellationToken)
    {
        WindowsProofUploadAuthorizationContext? authorization = RequireAuthorization(out ActionResult? denied);
        if (denied is not null)
        {
            return denied;
        }

        try
        {
            using WindowsProofUploadCompletionLease lease = _sessions.BeginCompletion(
                sessionId,
                authorization!.AuthorizationBinding);
            if (lease.CompletionResult is not null)
            {
                return Ok(lease.CompletionResult);
            }

            string generationId;
            string candidateVersion;
            string inventoryDigest;
            if (lease.PreparedGenerationId is null)
            {
                WindowsProofGenerationSnapshot? current = await _store.CaptureCurrentAsync(cancellationToken);
                WindowsProofPreparedGeneration prepared = await _store.PrepareAsync(
                    new WindowsProofPrepareRequest(
                        lease.RequestId,
                        lease.BundleRoot,
                        lease.ManifestSha256),
                    cancellationToken);
                lease.RecordPrepared(prepared, current?.GenerationId);
                generationId = prepared.GenerationId;
                candidateVersion = prepared.CandidateVersion;
                inventoryDigest = prepared.InventoryDigest;
            }
            else
            {
                generationId = lease.PreparedGenerationId;
                candidateVersion = lease.PreparedCandidateVersion
                    ?? throw new InvalidDataException("Prepared candidate version is missing from the durable session.");
                inventoryDigest = lease.PreparedInventoryDigest
                    ?? throw new InvalidDataException("Prepared inventory digest is missing from the durable session.");
            }

            WindowsProofActivationReceipt activation = await _store.ActivateAsync(
                new WindowsProofActivationRequest(
                    lease.RequestId,
                    generationId,
                    inventoryDigest,
                    lease.ExpectedCurrentGenerationId),
                cancellationToken);
            if (!string.Equals(activation.GenerationId, generationId, StringComparison.Ordinal)
                || !string.Equals(activation.CandidateVersion, candidateVersion, StringComparison.Ordinal)
                || !FixedTimeDigestEquals(activation.InventoryDigest, inventoryDigest))
            {
                throw new InvalidDataException("Windows proof activation receipt does not match the prepared request.");
            }

            WindowsProofGenerationSnapshot snapshot =
                await _store.CaptureGenerationAsync(generationId, cancellationToken)
                ?? throw new InvalidDataException("Activated Windows proof generation cannot be captured.");
            if (!string.Equals(snapshot.CandidateVersion, candidateVersion, StringComparison.Ordinal))
            {
                throw new InvalidDataException("Activated Windows proof candidate version changed after activation.");
            }

            var result = new WindowsProofUploadCompletionResult(
                lease.SessionId,
                activation.GenerationId,
                activation.CandidateVersion,
                lease.ManifestSha256,
                activation.InventoryDigest,
                activation.ActivatedAt,
                BuildGenerationRoutes(snapshot));
            lease.MarkCompleted(result);
            return Ok(result);
        }
        catch (Exception ex) when (IsExpected(ex))
        {
            return MapFailure(ex, "Windows proof upload completion");
        }
    }

    private static IReadOnlyDictionary<string, string> BuildGenerationRoutes(
        WindowsProofGenerationSnapshot snapshot)
    {
        string generation = Uri.EscapeDataString(snapshot.GenerationId);
        string candidate = Uri.EscapeDataString(snapshot.CandidateVersion);
        string currentRoot = "/downloads/proof/windows/current";
        string generationRoot = $"/downloads/proof/windows/generations/{generation}";
        string candidateRoot = $"/downloads/proof/windows/candidates/{candidate}";
        var routes = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["current:catalog"] = currentRoot,
            ["generation:catalog"] = generationRoot,
            ["candidate:catalog"] = candidateRoot
        };
        foreach (WindowsProofInventoryEntry entry in snapshot.Inventory)
        {
            string role = entry.Kind switch
            {
                WindowsProofArtifactKind.Installer => "installer",
                WindowsProofArtifactKind.BootstrapPayload => "payload",
                WindowsProofArtifactKind.BootstrapMetadata => "metadata",
                WindowsProofArtifactKind.SigningReceipt => "signing",
                WindowsProofArtifactKind.StartupSmokeReceipt => "startup-smoke",
                WindowsProofArtifactKind.VisualHandoff => "visual-handoff",
                WindowsProofArtifactKind.VisualExitEvidence => "visual-exit",
                _ => throw new InvalidDataException("Windows proof artifact kind has no delivery route.")
            };
            string artifact = Uri.EscapeDataString(entry.ArtifactId);
            if (!routes.TryAdd(
                    $"generation:{entry.ArtifactId}:{role}",
                    $"{generationRoot}/artifacts/{artifact}/{role}")
                || !routes.TryAdd(
                    $"candidate:{entry.ArtifactId}:{role}",
                    $"{candidateRoot}/artifacts/{artifact}/{role}")
                || !routes.TryAdd(
                    $"current:{entry.ArtifactId}:{role}",
                    $"{currentRoot}/artifacts/{artifact}/{role}"))
            {
                throw new InvalidDataException("Windows proof delivery route key is duplicated.");
            }

            if (entry.Kind is WindowsProofArtifactKind.Installer
                or WindowsProofArtifactKind.BootstrapPayload
                or WindowsProofArtifactKind.BootstrapMetadata)
            {
                routes[$"candidate-file:{entry.FileName}"] =
                    $"{candidateRoot}/files/{Uri.EscapeDataString(entry.FileName)}";
            }
        }
        return routes;
    }

    private WindowsProofUploadAuthorizationContext? RequireAuthorization(out ActionResult? denied)
    {
        ApplyPrivateHeaders(Response.Headers);
        WindowsProofUploadAuthorizationContext? authorization =
            WindowsProofUploadRequestGateMiddleware.RequireAuthorization(Request.HttpContext);
        if (authorization is null)
        {
            denied = ProblemResult(
                StatusCodes.Status401Unauthorized,
                "Windows proof upload authorization required",
                "A prevalidated Windows-proof-scoped authorization is required.",
                "auth-required");
            return null;
        }

        denied = null;
        return authorization;
    }

    private ActionResult MapFailure(Exception exception, string operation)
    {
        if (exception is IOException or UnauthorizedAccessException)
        {
            _logger.LogWarning(
                "{Operation} storage failure for request {TraceIdentifier} ({ExceptionType}).",
                operation,
                HttpContext.TraceIdentifier,
                exception.GetType().Name);
            return ProblemResult(
                StatusCodes.Status503ServiceUnavailable,
                $"{operation} unavailable",
                "Windows proof upload durable storage is unavailable.",
                "storage-unavailable");
        }

        int status = exception is InvalidOperationException
            ? StatusCodes.Status409Conflict
            : StatusCodes.Status400BadRequest;
        return ProblemResult(
            status,
            $"{operation} rejected",
            exception.Message,
            "rejected");
    }

    private ObjectResult ProblemResult(
        int statusCode,
        string title,
        string detail,
        string code)
        => Problem(
            statusCode: statusCode,
            title: title,
            detail: detail,
            type: $"https://chummer.run/problems/windows-proof-upload/{code}",
            instance: $"{Request.Path}#{HttpContext.TraceIdentifier}");

    private static bool IsExpected(Exception exception)
        => exception is InvalidDataException
            or InvalidOperationException
            or IOException
            or UnauthorizedAccessException;

    private static bool FixedTimeDigestEquals(string left, string right)
        => left.Length == right.Length
           && System.Security.Cryptography.CryptographicOperations.FixedTimeEquals(
               System.Text.Encoding.ASCII.GetBytes(left),
               System.Text.Encoding.ASCII.GetBytes(right));

    private static void ApplyPrivateHeaders(IHeaderDictionary headers)
    {
        headers["Cache-Control"] = "private, no-store, max-age=0";
        headers["CDN-Cache-Control"] = "no-store, max-age=0";
        headers["Cloudflare-CDN-Cache-Control"] = "no-store, max-age=0";
        headers["Pragma"] = "no-cache";
        headers["Expires"] = "0";
        headers["Referrer-Policy"] = "no-referrer";
    }

    public sealed record WindowsProofUploadSessionCreatedResponse(
        string SessionId,
        string State,
        DateTimeOffset ExpiresAtUtc,
        string FilesUrl,
        string ChunksUrl,
        string CompleteUrl,
        string ReconcileUrl);

    public sealed record WindowsProofUploadFileStoredResponse(string RelativePath, long BytesStored);

    public sealed record WindowsProofUploadChunkStoredResponse(
        string RelativePath,
        int ChunkIndex,
        int TotalChunks,
        long BytesReceived,
        bool Completed);
}
