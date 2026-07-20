using System.Text.Json;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Controllers;

[ApiController]
public sealed class InternalReleaseBundlesController : ControllerBase
{
    public const string ExactIncomingDesktopScopeHeader =
        "X-Chummer-Release-Exact-Incoming-Scope";

    private readonly ReleaseBundlePromotionService _promotionService;
    private readonly ReleaseBundleUploadSessionService _uploadSessions;
    private readonly ReleaseUploadQuotaOptions _uploadOptions;
    private readonly IConfiguration _configuration;
    private readonly ReleaseShelfGenerationStore _releaseShelfStore;
    private readonly PublicReleaseManifestService _releaseManifestService;
    private readonly AccountService _accounts;
    private readonly InstallLinkingService _installLinking;
    private readonly PublicCanonicalOriginPolicy _publicOrigin;
    private readonly ILogger<InternalReleaseBundlesController> _logger;

    public InternalReleaseBundlesController(
        ReleaseBundlePromotionService promotionService,
        ReleaseBundleUploadSessionService uploadSessions,
        IConfiguration configuration,
        ReleaseUploadTicketService releaseUploadTickets,
        PublicReleaseManifestService releaseManifestService,
        AccountService accounts,
        InstallLinkingService installLinking,
        PublicCanonicalOriginPolicy? publicOrigin = null,
        ILogger<InternalReleaseBundlesController>? logger = null,
        ReleaseUploadQuotaOptions? uploadOptions = null,
        ReleaseShelfGenerationStore? releaseShelfStore = null)
    {
        _promotionService = promotionService;
        _uploadSessions = uploadSessions;
        _uploadOptions = uploadOptions ?? ReleaseUploadQuotaOptions.FromConfiguration(configuration);
        _configuration = configuration;
        _releaseShelfStore = releaseShelfStore ?? new ReleaseShelfGenerationStore(configuration);
        _releaseManifestService = releaseManifestService;
        _accounts = accounts;
        _installLinking = installLinking;
        _publicOrigin = publicOrigin ?? PublicCanonicalOriginPolicy.CreateUnitTestDefault(configuration);
        _logger = logger ?? NullLogger<InternalReleaseBundlesController>.Instance;
    }

    [HttpPost("/api/internal/releases/bundles")]
    [IgnoreAntiforgeryToken]
    [Consumes("multipart/form-data")]
    [ProducesResponseType<ProblemDetails>(StatusCodes.Status409Conflict)]
    public Task<ActionResult<ReleaseBundlePromotionResult>> UploadBundle(
        [FromForm] IFormFile? bundle,
        CancellationToken cancellationToken)
    {
        _ = bundle;
        _ = cancellationToken;
        _ = RequirePrevalidatedAuthorization(out ActionResult? denied);
        if (denied is not null)
        {
            return Task.FromResult<ActionResult<ReleaseBundlePromotionResult>>(denied);
        }

        return Task.FromResult<ActionResult<ReleaseBundlePromotionResult>>(BuildProblem(
            StatusCodes.Status409Conflict,
            "Direct release upload disabled",
            "Direct bundle promotion cannot produce a durable staged-session completion receipt and is permanently disabled.",
            "https://chummer.run/problems/release-bundle/staged-session-required"));
    }

    [HttpPost("/api/internal/releases/upload-sessions")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<ReleaseUploadSessionCreatedResponse>(StatusCodes.Status200OK)]
    public ActionResult<ReleaseUploadSessionCreatedResponse> CreateUploadSession()
    {
        ReleaseUploadAuthorizationContext? authorization = RequirePrevalidatedAuthorization(out ActionResult? denied);
        if (denied is not null)
        {
            return denied;
        }

        try
        {
            ReleaseDesktopTupleScope? exactIncomingDesktopScope = null;
            if (Request.Headers.TryGetValue(
                    ExactIncomingDesktopScopeHeader,
                    out Microsoft.Extensions.Primitives.StringValues declaredScope))
            {
                try
                {
                    if (declaredScope.Count != 1)
                    {
                        throw new InvalidDataException(
                            "exact incoming desktop scope header must be supplied exactly once.");
                    }

                    exactIncomingDesktopScope = ReleaseDesktopTupleScope.Parse(
                        declaredScope[0] ?? string.Empty);
                }
                catch (InvalidDataException ex)
                {
                    return BuildProblem(
                        StatusCodes.Status400BadRequest,
                        "Upload session scope rejected",
                        ex.Message,
                        "https://chummer.run/problems/release-bundle/invalid-exact-scope");
                }
            }

            ReleaseUploadSession session = _uploadSessions.CreateSession(
                authorization!.AuthorizationBinding,
                authorization.SingleUseAuthorization,
                authorization.AuthorizationExpiresAtUtc,
                authorization.CandidateImportAuthority?.SessionBinding,
                exactIncomingDesktopScope);
            return Ok(new ReleaseUploadSessionCreatedResponse(
                SessionId: session.SessionId,
                ExpiresAtUtc: session.ExpiresAtUtc,
                FilesUrl: BuildAbsoluteRoute($"/api/internal/releases/upload-sessions/{session.SessionId}/files"),
                ChunksUrl: BuildAbsoluteRoute($"/api/internal/releases/upload-sessions/{session.SessionId}/chunks"),
                CompleteUrl: BuildAbsoluteRoute($"/api/internal/releases/upload-sessions/{session.SessionId}/complete"),
                ExactIncomingDesktopTuples: session.ExactIncomingDesktopScope?.TupleIds));
        }
        catch (ReleaseUploadQuotaException ex)
        {
            return BuildProblem(
                ex.StatusCode,
                "Upload session creation rejected",
                ex.Message,
                "https://chummer.run/problems/release-bundle/quota");
        }
        catch (Exception ex) when (ex is InvalidDataException or InvalidOperationException or IOException or UnauthorizedAccessException)
        {
            if (ex is IOException or UnauthorizedAccessException)
            {
                LogSessionInfrastructureFailure(ex);
                return BuildProblem(
                    StatusCodes.Status503ServiceUnavailable,
                    "Upload session creation unavailable",
                    "release upload session storage is unavailable.",
                    "https://chummer.run/problems/release-bundle/unavailable");
            }

            return BuildProblem(
                StatusCodes.Status409Conflict,
                "Upload session creation rejected",
                ex.Message,
                "https://chummer.run/problems/release-bundle/session-conflict");
        }
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
        ReleaseUploadAuthorizationContext? authorization = RequirePrevalidatedAuthorization(out ActionResult? denied);
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

        if (file.Length > _uploadOptions.MaxChunkBytes)
        {
            return BuildProblem(
                StatusCodes.Status413PayloadTooLarge,
                "Upload session file rejected",
                $"file payload exceeds its {_uploadOptions.MaxChunkBytes}-byte limit; use bounded chunks for larger files.",
                "https://chummer.run/problems/release-bundle/payload-too-large");
        }

        if (ReleaseBuildProvenanceValidator.TryGetGovernedUploadLimit(uploadPath, out long maximumProofBytes)
            && file.Length > maximumProofBytes)
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session file rejected",
                $"governed build provenance file exceeds its {maximumProofBytes}-byte limit.",
                "https://chummer.run/problems/release-bundle/invalid-parameter");
        }

        try
        {
            await using Stream content = file.OpenReadStream();
            long bytesStored = await _uploadSessions.WriteFileAsync(
                sessionId,
                uploadPath,
                content,
                authorization!.AuthorizationBinding,
                cancellationToken);
            return Ok(new ReleaseUploadFileStoredResponse(uploadPath, bytesStored));
        }
        catch (ReleaseUploadQuotaException ex)
        {
            return BuildProblem(
                ex.StatusCode,
                "Upload session file rejected",
                ex.Message,
                "https://chummer.run/problems/release-bundle/quota");
        }
        catch (Exception ex) when (ex is InvalidDataException or InvalidOperationException or IOException or UnauthorizedAccessException)
        {
            if (ex is IOException or UnauthorizedAccessException)
            {
                LogSessionInfrastructureFailure(ex);
                return BuildProblem(
                    StatusCodes.Status503ServiceUnavailable,
                    "Upload session file unavailable",
                    "release upload session storage is unavailable.",
                    "https://chummer.run/problems/release-bundle/unavailable");
            }

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
        ReleaseUploadAuthorizationContext? authorization = RequirePrevalidatedAuthorization(out ActionResult? denied);
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

        if (chunk.Length > _uploadOptions.MaxChunkBytes)
        {
            return BuildProblem(
                StatusCodes.Status413PayloadTooLarge,
                "Upload session chunk rejected",
                $"chunk payload exceeds its {_uploadOptions.MaxChunkBytes}-byte limit.",
                "https://chummer.run/problems/release-bundle/payload-too-large");
        }

        if (ReleaseBuildProvenanceValidator.IsGovernedUploadNamespace(uploadPath))
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session chunk rejected",
                "governed build provenance files must use the bounded file upload endpoint.",
                "https://chummer.run/problems/release-bundle/invalid-parameter");
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
                authorization!.AuthorizationBinding,
                cancellationToken);
            return Ok(new ReleaseUploadChunkStoredResponse(
                result.RelativePath,
                result.ChunkIndex,
                result.TotalChunks,
                result.BytesReceived,
                result.Completed));
        }
        catch (ReleaseUploadQuotaException ex)
        {
            return BuildProblem(
                ex.StatusCode,
                "Upload session chunk rejected",
                ex.Message,
                "https://chummer.run/problems/release-bundle/quota");
        }
        catch (Exception ex) when (ex is InvalidDataException or InvalidOperationException or IOException or UnauthorizedAccessException)
        {
            if (ex is IOException or UnauthorizedAccessException)
            {
                LogSessionInfrastructureFailure(ex);
                return BuildProblem(
                    StatusCodes.Status503ServiceUnavailable,
                    "Upload session chunk unavailable",
                    "release upload session storage is unavailable.",
                    "https://chummer.run/problems/release-bundle/unavailable");
            }

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
        ReleaseUploadAuthorizationContext? authorization = RequirePrevalidatedAuthorization(out ActionResult? denied);
        if (denied is not null)
        {
            return denied;
        }

        if (authorization!.UploadTicketClaims is not null)
        {
            ApplyCredentialResponseNoStoreHeaders(Response.Headers);
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

        bool activationIntentRecorded = false;
        try
        {
            using ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease completion =
                _uploadSessions.BeginCompletion(sessionId, authorization!.AuthorizationBinding);
            if (completion.CandidateImportBinding
                != authorization.CandidateImportAuthority?.SessionBinding)
            {
                throw new InvalidDataException(
                    "upload session candidate authority does not match its exact creator binding.");
            }
            if (completion.CompletedResult is not null)
            {
                ReleaseBundlePromotionResult completedResult = completion.CompletedResult;
                if (completion.ActivationIntent is not null)
                {
                    activationIntentRecorded = true;
                    _promotionService.AcknowledgeActivationCompletion(completion.ActivationIntent);
                    completion.MarkActivationAcknowledged();
                }

                if (authorization.UploadTicketClaims is not null)
                {
                    try
                    {
                        completedResult = AttachSignedInInstallClaims(completedResult, authorization.UploadTicketClaims);
                    }
                    catch (Exception ex)
                    {
                        _logger.LogWarning(
                            "Fresh signed-in install claims could not be attached to completed release {Version} ({ExceptionType}).",
                            completedResult.Version,
                            ex.GetType().Name);
                    }
                }

                return Ok(completedResult);
            }

            if (completion.PublicationOutcomeUnknown)
            {
                ReleaseActivationIntent intent = completion.ActivationIntent
                    ?? throw new InvalidDataException("publishing upload session is missing its durable activation intent.");
                activationIntentRecorded = true;
                if (!_promotionService.TryReconcileActivation(intent, out ReleaseBundlePromotionResult? reconciled))
                {
                    completion.ResetAbortedActivation(intent);
                    activationIntentRecorded = false;
                    return BuildProblem(
                        StatusCodes.Status409Conflict,
                        "Release activation aborted",
                        "the prior activation was durably proven not published; the staged session remains repairable and may be completed again.",
                        "https://chummer.run/problems/release-bundle/activation-aborted");
                }

                if (reconciled is null)
                {
                    return BuildPublicationOutcomeUnknown();
                }

                completion.MarkCompleted(reconciled);
                _promotionService.AcknowledgeActivationCompletion(intent);
                completion.MarkActivationAcknowledged();
                ReleaseBundlePromotionResult reconciledResponse = reconciled;
                if (authorization.UploadTicketClaims is not null)
                {
                    try
                    {
                        reconciledResponse = AttachSignedInInstallClaims(reconciled, authorization.UploadTicketClaims);
                    }
                    catch (Exception ex)
                    {
                        _logger.LogWarning(
                            "Reconciled release {Version} could not attach fresh signed-in install claims ({ExceptionType}).",
                            reconciled.Version,
                            ex.GetType().Name);
                    }
                }

                return Ok(reconciledResponse);
            }

            if (authorization.CandidateImportAuthority is not null)
            {
                ReleaseUploadCandidateBundleValidator.Validate(
                    completion.BundleRoot,
                    authorization.CandidateImportAuthority);
            }

            await _promotionService.ValidateDirectoryAsync(
                completion.BundleRoot,
                completion.ExactIncomingDesktopScope,
                cancellationToken);
            ObjectResult? admissionFailure = EvaluateFreshCompletionAdmission(
                completion,
                cancellationToken);
            if (admissionFailure is not null)
            {
                return admissionFailure;
            }

            ReleaseBundlePromotionResult durableResult;
            try
            {
                durableResult = await _promotionService.PromoteDirectoryAsync(
                    completion.BundleRoot,
                    completion.ExactIncomingDesktopScope,
                    intent =>
                    {
                        completion.RecordActivationIntent(intent);
                        activationIntentRecorded = true;
                    },
                    cancellationToken);
            }
            catch (ReleaseActivationAbortedException ex)
            {
                completion.ResetAbortedActivation(ex.Intent);
                activationIntentRecorded = false;
                return BuildProblem(
                    StatusCodes.Status409Conflict,
                    "Release activation aborted",
                    "the activation was durably aborted before the canonical pointer changed; the staged session remains repairable.",
                    "https://chummer.run/problems/release-bundle/activation-aborted");
            }
            catch (ReleaseActivationOutcomeUnknownException)
            {
                return BuildPublicationOutcomeUnknown();
            }

            completion.MarkCompleted(durableResult);
            ReleaseActivationIntent durableIntent = completion.ActivationIntent
                ?? throw new InvalidDataException("completed release session is missing its durable activation intent.");
            _promotionService.AcknowledgeActivationCompletion(durableIntent);
            completion.MarkActivationAcknowledged();
            ReleaseBundlePromotionResult responseResult = durableResult;
            if (authorization.UploadTicketClaims is not null)
            {
                try
                {
                    responseResult = AttachSignedInInstallClaims(durableResult, authorization.UploadTicketClaims);
                }
                catch (Exception ex)
                {
                    _logger.LogWarning(
                        "Release {Version} was activated, but fresh signed-in install claims could not be attached to this response ({ExceptionType}).",
                        durableResult.Version,
                        ex.GetType().Name);
                }
            }

            return Ok(responseResult);
        }
        catch (Exception ex) when (ex is InvalidDataException or InvalidOperationException or JsonException or NotSupportedException)
        {
            if (activationIntentRecorded)
            {
                LogSessionInfrastructureFailure(ex);
                return BuildPublicationOutcomeUnknown();
            }

            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session promotion rejected",
                ex.Message,
                "https://chummer.run/problems/release-bundle/rejected");
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            LogSessionInfrastructureFailure(ex);
            if (activationIntentRecorded)
            {
                return BuildPublicationOutcomeUnknown();
            }

            return BuildProblem(
                StatusCodes.Status503ServiceUnavailable,
                "Release upload infrastructure failure",
                "release upload session storage is unavailable.",
                "https://chummer.run/problems/release-bundle/unavailable");
        }
    }

    [HttpPost("/api/internal/releases/upload-sessions/{sessionId}/reconcile")]
    [IgnoreAntiforgeryToken]
    [ProducesResponseType<ReleaseBundlePromotionResult>(StatusCodes.Status200OK)]
    public ActionResult<ReleaseBundlePromotionResult> ReconcileUploadSession(
        [FromRoute] string sessionId)
    {
        ReleaseUploadAuthorizationContext? authorization = RequirePrevalidatedAuthorization(
            out ActionResult? denied);
        if (denied is not null)
        {
            return denied;
        }

        if (!authorization!.AllowsPrivilegedReconciliation)
        {
            return BuildProblem(
                StatusCodes.Status403Forbidden,
                "Privileged release reconciliation required",
                "candidate-import and expiring release upload authorities cannot invoke operator reconciliation.",
                "https://chummer.run/problems/release-bundle/reconciliation-forbidden");
        }

        if (string.IsNullOrWhiteSpace(sessionId) || !Guid.TryParse(sessionId, out _))
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Release reconciliation rejected",
                "sessionId is required and must be a valid GUID.",
                "https://chummer.run/problems/release-bundle/invalid-session-id");
        }

        bool activationIntentLoaded = false;
        try
        {
            using ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease completion =
                _uploadSessions.BeginPrivilegedReconciliation(sessionId);
            if (!completion.RecoveryOnly)
            {
                throw new InvalidOperationException(
                    "release reconciliation did not acquire a recovery-only session lease.");
            }

            ReleaseActivationIntent intent = completion.ActivationIntent
                ?? throw new InvalidDataException(
                    "unresolved upload session is missing its durable activation intent.");
            activationIntentLoaded = true;

            if (completion.CompletedResult is not null)
            {
                ReleaseBundlePromotionResult completed = completion.CompletedResult;
                _promotionService.AcknowledgeActivationCompletion(intent);
                completion.MarkActivationAcknowledged();
                return Ok(completed);
            }

            if (!completion.PublicationOutcomeUnknown)
            {
                throw new InvalidOperationException(
                    "release reconciliation can only inspect an unresolved activation.");
            }

            if (!_promotionService.TryReconcileActivation(
                    intent,
                    out ReleaseBundlePromotionResult? reconciled))
            {
                completion.ResetAbortedActivation(intent);
                return BuildProblem(
                    StatusCodes.Status409Conflict,
                    "Release activation aborted",
                    "the prior activation was durably proven not published; no new publication was attempted.",
                    "https://chummer.run/problems/release-bundle/activation-aborted");
            }

            if (reconciled is null)
            {
                return BuildPublicationOutcomeUnknown();
            }

            completion.MarkCompleted(reconciled);
            _promotionService.AcknowledgeActivationCompletion(intent);
            completion.MarkActivationAcknowledged();
            return Ok(reconciled);
        }
        catch (ReleaseActivationOutcomeUnknownException)
        {
            return BuildPublicationOutcomeUnknown();
        }
        catch (Exception ex) when (ex is InvalidDataException or InvalidOperationException or JsonException)
        {
            if (activationIntentLoaded)
            {
                LogSessionInfrastructureFailure(ex);
                return BuildPublicationOutcomeUnknown();
            }

            return BuildProblem(
                StatusCodes.Status409Conflict,
                "Release reconciliation rejected",
                "the upload session is not eligible for privileged reconciliation.",
                "https://chummer.run/problems/release-bundle/reconciliation-rejected");
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            LogSessionInfrastructureFailure(ex);
            return activationIntentLoaded
                ? BuildPublicationOutcomeUnknown()
                : BuildProblem(
                    StatusCodes.Status503ServiceUnavailable,
                    "Release reconciliation unavailable",
                    "release reconciliation storage is unavailable.",
                    "https://chummer.run/problems/release-bundle/unavailable");
        }
    }

    private ObjectResult? EvaluateFreshCompletionAdmission(
        ReleaseBundleUploadSessionService.ReleaseUploadSessionCompletionLease completion,
        CancellationToken cancellationToken)
    {
        ReleaseUploadStorageReadiness uploadStorage = completion.EvaluateUploadStorageReadiness();
        if (!uploadStorage.Ready)
        {
            return BuildCompletionAdmissionFailure(uploadStorage.Code);
        }

        ReleaseUploadStorageReadiness sessionProtocol =
            completion.EvaluateSessionActivationReadiness(cancellationToken);
        if (!sessionProtocol.Ready)
        {
            return BuildCompletionAdmissionFailure(sessionProtocol.Code);
        }

        ReleaseShelfSnapshot snapshot;
        try
        {
            snapshot = _releaseShelfStore.Capture();
        }
        catch (Exception ex) when (ex is InvalidDataException or IOException or UnauthorizedAccessException)
        {
            return BuildCompletionAdmissionFailure("release_shelf_unavailable");
        }

        ReleaseUploadStorageReadiness destination =
            completion.EvaluatePublicationDestinationReadiness(
                snapshot,
                cancellationToken);
        if (!destination.Ready)
        {
            return BuildCompletionAdmissionFailure(destination.Code);
        }

        bool hasLayoutRequired = TryReadExplicitBoolean(
            "CHUMMER_RELEASE_SHELF_LAYOUT_V1_REQUIRED",
            out bool layoutRequired);
        bool hasInitialMigration = TryReadExplicitBoolean(
            "CHUMMER_RELEASE_SHELF_INITIAL_MIGRATION_ALLOWED",
            out bool initialMigrationAllowed);
        if (!hasLayoutRequired || !hasInitialMigration)
        {
            return BuildCompletionAdmissionFailure("release_shelf_migration_posture_unspecified");
        }

        bool firstActivation = snapshot.IsLegacy
                               && !layoutRequired
                               && initialMigrationAllowed
                               && IsPristineLegacyCutoverRoot(snapshot.DownloadsRoot);
        bool steadyState = !snapshot.IsLegacy
                           && layoutRequired
                           && !initialMigrationAllowed;
        if (!firstActivation && !steadyState)
        {
            return BuildCompletionAdmissionFailure("release_shelf_migration_posture_invalid");
        }

        ReleaseShelfPublicationReadinessProbeResult activationProtocol =
            _promotionService.EvaluateActivationProtocolReadiness(snapshot, cancellationToken);
        if (activationProtocol.Ready)
        {
            return null;
        }

        bool explicitFirstActivationException = firstActivation
                                                && activationProtocol.Code is
                                                    "writer_policy_missing"
                                                    or "layout_v1_activation_required";
        return explicitFirstActivationException
            ? null
            : BuildCompletionAdmissionFailure(activationProtocol.Code);
    }

    private bool TryReadExplicitBoolean(string key, out bool value)
    {
        string raw = (_configuration[key] ?? string.Empty).Trim();
        return bool.TryParse(raw, out value);
    }

    private static bool IsPristineLegacyCutoverRoot(string downloadsRoot)
    {
        try
        {
            string root = Path.GetFullPath(downloadsRoot);
            if (!Directory.Exists(root)
                || System.IO.File.Exists(Path.Combine(root, ReleaseShelfGenerationStore.CurrentPointerFileName))
                || System.IO.File.Exists(Path.Combine(root, ReleaseShelfGenerationStore.LayoutMarkerFileName)))
            {
                return false;
            }

            string generations = Path.Combine(
                root,
                ReleaseShelfGenerationStore.GenerationsDirectoryName);
            if (!Directory.Exists(generations))
            {
                return true;
            }

            FileAttributes attributes = System.IO.File.GetAttributes(generations);
            return (attributes & FileAttributes.Directory) != 0
                   && (attributes & FileAttributes.ReparsePoint) == 0
                   && !Directory.EnumerateFileSystemEntries(generations).Any();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or NotSupportedException)
        {
            return false;
        }
    }

    private ObjectResult BuildCompletionAdmissionFailure(string code)
        => BuildProblem(
            StatusCodes.Status503ServiceUnavailable,
            "Release publication admission blocked",
            $"release publication readiness is blocked ({code}). No activation was prepared.",
            "https://chummer.run/problems/release-bundle/publication-admission-blocked");

    private ReleaseUploadAuthorizationContext? RequirePrevalidatedAuthorization(out ActionResult? denied)
    {
        ReleaseUploadAuthorizationContext? authorization =
            ReleaseUploadRequestGateMiddleware.RequireAuthorization(Request.HttpContext);
        if (authorization is not null)
        {
            denied = null;
            return authorization;
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
        if (ReleaseBuildProvenanceValidator.IsGovernedUploadNamespace(normalizedPath)
            && !ReleaseBuildProvenanceValidator.TryGetGovernedUploadLimit(normalizedPath, out _))
        {
            return BuildProblem(
                StatusCodes.Status400BadRequest,
                "Upload session path rejected",
                $"{fieldName} is not an allowlisted governed build provenance path.",
                "https://chummer.run/problems/release-bundle/invalid-parameter");
        }
        return null;
    }

    internal ReleaseBundlePromotionResult AttachSignedInInstallClaims(
        ReleaseBundlePromotionResult result,
        ReleaseUploadTicketClaims claims)
    {
        if (result.PromotedArtifactIds.Count == 0)
        {
            return result with { SignedInInstallClaims = Array.Empty<ReleasePromotionInstallClaim>() };
        }

        ReleaseShelfSnapshot snapshot = string.IsNullOrWhiteSpace(result.GenerationId)
            ? _releaseManifestService.CaptureShelfSnapshot()
            : _releaseManifestService.CaptureShelfGeneration(result.GenerationId);
        var manifest = _releaseManifestService.LoadManifest(snapshot);
        if (!string.IsNullOrWhiteSpace(result.GenerationId)
            && !string.Equals(manifest.GenerationId, result.GenerationId, StringComparison.Ordinal))
        {
            throw new InvalidDataException("promoted install claims must bind the exact activated generation.");
        }
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

            var dispatch = _installLinking.IssueDownload(
                manifest,
                artifact,
                user.UserId,
                claims.SubjectId,
                forceNewClaim: true);
            if (dispatch.ClaimTicket is null)
            {
                continue;
            }

            string installDispatchUrl;
            if (!string.IsNullOrWhiteSpace(manifest.GenerationId))
            {
                string generationHref = PublicLandingController.BuildCredentialBoundArtifactHref(
                    manifest,
                    artifact,
                    $"/downloads/install/{Uri.EscapeDataString(artifactId)}");
                installDispatchUrl = $"{generationHref}{QueryString.Create("claimCode", dispatch.ClaimTicket.ClaimCode)}";
            }
            else
            {
                installDispatchUrl = installUrlByArtifactId.TryGetValue(artifactId, out string? installUrl)
                    ? installUrl
                    : $"/downloads/install/{Uri.EscapeDataString(artifactId)}";
            }

            issuedClaims.Add(new ReleasePromotionInstallClaim(
                ArtifactId: artifactId,
                InstallDispatchUrl: installDispatchUrl,
                ClaimCode: dispatch.ClaimTicket.ClaimCode,
                ClaimCodeExpiresAtUtc: dispatch.ClaimTicket.ExpiresAtUtc));
        }

        return result with { SignedInInstallClaims = issuedClaims };
    }

    private void LogSessionInfrastructureFailure(Exception ex)
    {
        _logger.LogWarning(
            "Release upload session infrastructure failure for request {TraceIdentifier} ({ExceptionType}).",
            Request.HttpContext.TraceIdentifier,
            ex.GetType().Name);
    }

    private ObjectResult BuildPublicationOutcomeUnknown()
        => BuildProblem(
            StatusCodes.Status409Conflict,
            "Upload session publication outcome is unknown",
            "the release may already be live; reconcile the canonical shelf before any retry.",
            "https://chummer.run/problems/release-bundle/publication-outcome-unknown");

    private static void ApplyCredentialResponseNoStoreHeaders(IHeaderDictionary headers)
    {
        headers["Cache-Control"] = "private, no-store, max-age=0";
        headers["CDN-Cache-Control"] = "no-store, max-age=0";
        headers["Cloudflare-CDN-Cache-Control"] = "no-store, max-age=0";
        headers["Surrogate-Control"] = "no-store";
        headers["Pragma"] = "no-cache";
        headers["Expires"] = "0";
        headers["Referrer-Policy"] = "no-referrer";
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
        => _publicOrigin.BuildAbsolute(path, pathBase: Request.PathBase);

    public sealed record ReleaseUploadSessionCreatedResponse(
        string SessionId,
        DateTimeOffset ExpiresAtUtc,
        string FilesUrl,
        string ChunksUrl,
        string CompleteUrl,
        IReadOnlyList<string>? ExactIncomingDesktopTuples);

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
