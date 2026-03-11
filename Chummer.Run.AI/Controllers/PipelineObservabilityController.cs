using Chummer.Run.AI.Services.Assets;
using Chummer.Run.AI.Services.Gateway;
using Chummer.Run.AI.Services.Session;
using Chummer.Run.Contracts.Observability;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.AI.Controllers;

[ApiController]
[Route("api/v1/ai/pipelines")]
public sealed class PipelineObservabilityController : ControllerBase
{
    private readonly ISessionLedgerService _ledger;
    private readonly IAssetLifecycleService _assets;
    private readonly IMediaRenderJobService _mediaJobs;
    private readonly IAiGatewayService _gateway;

    public PipelineObservabilityController(
        ISessionLedgerService ledger,
        IAssetLifecycleService assets,
        IMediaRenderJobService mediaJobs,
        IAiGatewayService gateway)
    {
        _ledger = ledger;
        _assets = assets;
        _mediaJobs = mediaJobs;
        _gateway = gateway;
    }

    [HttpGet("projection")]
    [ProducesResponseType<PipelineProjectionEnvelope>(StatusCodes.Status200OK)]
    public ActionResult<PipelineProjectionEnvelope> GetProjection()
    {
        return Ok(new PipelineProjectionEnvelope(
            GeneratedAtUtc: DateTimeOffset.UtcNow,
            Pipelines:
            [
                _ledger.GetRelayPipelineProjection(),
                _assets.GetApprovalPipelineProjection(),
                _mediaJobs.GetMediaPipelineProjection(),
                _gateway.GetGatewayPipelineProjection()
            ]));
    }
}
