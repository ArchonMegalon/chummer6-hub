using Chummer.Run.AI.Services.Session;
using Microsoft.AspNetCore.Mvc;
using RunMemoryContracts = Chummer.Run.Contracts.Memory;

namespace Chummer.Run.AI.Controllers;

[ApiController]
[Route("api/v1/ai/session")]
public sealed class SessionController : ControllerBase
{
    private readonly ISessionLedgerService _ledgerService;
    private readonly ISessionMemoryService _memoryService;
    private readonly ISessionMemoryIngestionService _memoryIngestionService;
    private readonly ISessionRuntimeBundleService _runtimeBundleService;
    private readonly IOfflineSyncService _offlineSyncService;

    public SessionController(
        ISessionLedgerService ledgerService,
        ISessionMemoryService memoryService,
        ISessionMemoryIngestionService memoryIngestionService,
        ISessionRuntimeBundleService runtimeBundleService,
        IOfflineSyncService offlineSyncService)
    {
        _ledgerService = ledgerService;
        _memoryService = memoryService;
        _memoryIngestionService = memoryIngestionService;
        _runtimeBundleService = runtimeBundleService;
        _offlineSyncService = offlineSyncService;
    }

    [HttpPost("events")]
    [ProducesResponseType<SessionRelayMergeResponse>(StatusCodes.Status200OK)]
    public async Task<ActionResult<SessionRelayMergeResponse>> SubmitEvents([FromBody] IReadOnlyList<SessionEventEnvelope>? events, CancellationToken cancellationToken)
    {
        if (events is null || events.Count == 0)
        {
            return BadRequest("events is required.");
        }

        var merge = await _ledgerService.MergeEventsAsync(events, cancellationToken);
        return Ok(merge);
    }

    [HttpGet("events/{sessionId}/{sceneId}")]
    [ProducesResponseType<SessionEventProjectionDto>(StatusCodes.Status200OK)]
    public ActionResult<SessionEventProjectionDto> GetEvents([FromRoute] string sessionId, [FromRoute] string sceneId)
    {
        if (string.IsNullOrWhiteSpace(sessionId) || string.IsNullOrWhiteSpace(sceneId))
        {
            return BadRequest("sessionId and sceneId are required.");
        }

        return Ok(_ledgerService.GetProjection(sessionId, sceneId));
    }

    [HttpPost("memory/drafts")]
    [ProducesResponseType<SessionMemoryDraftResult>(StatusCodes.Status200OK)]
    public ActionResult<SessionMemoryDraftResult> Draft([FromBody] SessionMemoryDraftRequest? request)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.SessionId))
        {
            return BadRequest("sessionId is required.");
        }

        return Ok(_memoryService.Draft(request, request.SceneId));
    }

    [HttpPost("memory/ingest-transcript")]
    [ProducesResponseType<RunMemoryContracts.SessionMemoryIngestionResult>(StatusCodes.Status200OK)]
    public async Task<ActionResult<RunMemoryContracts.SessionMemoryIngestionResult>> IngestTranscript(
        [FromBody] RunMemoryContracts.SessionMemoryIngestionRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("request is required.");
        }

        try
        {
            return Ok(await _memoryIngestionService.IngestAsync(request, cancellationToken));
        }
        catch (ArgumentException ex)
        {
            return BadRequest(ex.Message);
        }
    }

    [HttpGet("runtime-bundle/{sessionId}/{sceneId}")]
    [ProducesResponseType<SessionRuntimeBundleDto>(StatusCodes.Status200OK)]
    public ActionResult<SessionRuntimeBundleDto> GetRuntimeBundle(
        [FromRoute] string sessionId,
        [FromRoute] string sceneId)
    {
        if (string.IsNullOrWhiteSpace(sessionId) || string.IsNullOrWhiteSpace(sceneId))
        {
            return BadRequest("sessionId and sceneId are required.");
        }

        return Ok(_runtimeBundleService.ResolveBundle(sessionId, sceneId));
    }

    [HttpPost("offline/snapshot")]
    [ProducesResponseType<OfflineSyncSnapshotPackage>(StatusCodes.Status200OK)]
    public ActionResult<OfflineSyncSnapshotPackage> CreateOfflineSnapshot([FromBody] OfflineSyncSnapshotRequest? request)
    {
        if (request is null
            || string.IsNullOrWhiteSpace(request.CampaignId)
            || string.IsNullOrWhiteSpace(request.SessionId)
            || string.IsNullOrWhiteSpace(request.SceneId)
            || string.IsNullOrWhiteSpace(request.ExportedBy))
        {
            return BadRequest("campaignId, sessionId, sceneId, and exportedBy are required.");
        }

        return Ok(_offlineSyncService.CreateSnapshot(request));
    }

    [HttpPost("offline/reconcile")]
    [ProducesResponseType<OfflineSyncReconcileResult>(StatusCodes.Status200OK)]
    public async Task<ActionResult<OfflineSyncReconcileResult>> ReconcileOfflineSnapshot(
        [FromBody] OfflineSyncReconcileRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null || request.Snapshot is null || string.IsNullOrWhiteSpace(request.ReconciledBy))
        {
            return BadRequest("snapshot and reconciledBy are required.");
        }

        return Ok(await _offlineSyncService.ReconcileAsync(request, cancellationToken));
    }
}
