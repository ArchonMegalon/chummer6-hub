using System.Text.Json;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Api.Controllers;

[ApiController]
[Route(OriginChapterWorkerGateMiddleware.Prefix)]
public sealed class InternalOriginChaptersController(OriginChapterAuthoringService authoring) : ControllerBase
{
    [HttpGet("pending")]
    public ActionResult Pending([FromQuery] int limit = 20, [FromQuery] string? bookRef = null)
        => Guard(() => Ok(authoring.PendingForWorker(limit, bookRef)));

    [HttpGet("{workId}")]
    public ActionResult Read(string workId)
        => Guard(() => Ok(authoring.GetForWorker(workId)));

    [HttpPost("{workId}/admit")]
    [RequestSizeLimit(4096)]
    public ActionResult Admit(string workId, [FromBody] OriginChapterWorkerAdmissionRequest? request)
        => Guard(() => request is null ? BadRequest() : Ok(authoring.AdmitForWorker(workId,
            request.SourceDigest, request.ExecutionAdmission)));

    [HttpPost("{workId}/complete")]
    [RequestSizeLimit(OriginChapterAuthoringService.MaximumRequestBytes * 2)]
    public ActionResult Complete(string workId, [FromBody] OriginChapterWorkerCompletionRequest? request)
        => Guard(() => request is null ? BadRequest() : Ok(authoring.CompleteForWorker(workId,
            request.SourceDigest, request.ExecutionAdmission, request.DraftText, request.ProviderReceiptDigest)));

    [HttpPost("{workId}/revise-unaccepted")]
    [RequestSizeLimit(OriginChapterAuthoringService.MaximumRequestBytes * 2)]
    public ActionResult ReviseUnaccepted(string workId, [FromBody] OriginChapterWorkerRevisionRequest? request)
        => Guard(() => request is null ? BadRequest() : Ok(authoring.ReviseUnacceptedForWorker(workId,
            request.SourceDigest, request.ExecutionAdmission, request.ExpectedProviderReceiptDigest,
            request.ExpectedTextDigest, request.DraftText, request.ProviderReceiptDigest)));

    private ActionResult Guard(Func<ActionResult> action)
    {
        AndroidLinkedV2RequestProofMiddleware.ApplyPrivateResponseHeaders(Response.Headers);
        if (!OriginChapterWorkerGateMiddleware.IsAdmitted(HttpContext)) return NotFound();
        if (!authoring.IsConfigured) return StatusCode(StatusCodes.Status503ServiceUnavailable);
        try { return action(); }
        catch (KeyNotFoundException) { return NotFound(); }
        catch (ArgumentException) { return BadRequest("Invalid chapter worker binding."); }
        catch (InvalidOperationException) { return Conflict("Reconcile the exact existing chapter admission."); }
        catch (Exception error) when (error is IOException or InvalidDataException or JsonException)
        { return StatusCode(StatusCodes.Status503ServiceUnavailable, "Private chapter storage unavailable."); }
    }
}

public sealed record OriginChapterWorkerAdmissionRequest(string SourceDigest, string ExecutionAdmission);
public sealed record OriginChapterWorkerCompletionRequest(string SourceDigest, string ExecutionAdmission,
    string DraftText, string ProviderReceiptDigest);
public sealed record OriginChapterWorkerRevisionRequest(string SourceDigest, string ExecutionAdmission,
    string ExpectedProviderReceiptDigest, string ExpectedTextDigest, string DraftText, string ProviderReceiptDigest);
