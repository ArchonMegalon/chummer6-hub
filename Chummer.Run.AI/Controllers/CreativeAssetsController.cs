using Chummer.Run.AI.Services.Assets;
using Chummer.Run.AI.Services.Creative;
using Chummer.Media.Contracts;
using Chummer.Run.Contracts.Media;
using Microsoft.AspNetCore.Mvc;
using System.Collections.Generic;

namespace Chummer.Run.AI.Controllers;

#pragma warning disable CS0618
[ApiController]
[Route("api/v1/ai/creative")]
public sealed class CreativeAssetsController : ControllerBase
{
    private readonly IPortraitForgeService _portraitForge;
    private readonly IPacketFactoryService _packetFactory;
    private readonly IAssetLifecycleService _assetLifecycle;
    private readonly IMediaRenderJobService _mediaRenderJobs;
    private readonly INewsNetworkService _newsNetworkService;
    private readonly IRouteCinemaService _routeCinemaService;
    private readonly IShadowfeedService _shadowfeedService;
    private readonly INpcMessageVideoService _npcMessageVideoService;

    public CreativeAssetsController(
        IPortraitForgeService portraitForge,
        IPacketFactoryService packetFactory,
        IAssetLifecycleService assetLifecycle,
        IMediaRenderJobService mediaRenderJobs,
        INewsNetworkService newsNetworkService,
        IRouteCinemaService routeCinemaService,
        IShadowfeedService shadowfeedService,
        INpcMessageVideoService npcMessageVideoService)
    {
        _portraitForge = portraitForge;
        _packetFactory = packetFactory;
        _assetLifecycle = assetLifecycle;
        _mediaRenderJobs = mediaRenderJobs;
        _newsNetworkService = newsNetworkService;
        _routeCinemaService = routeCinemaService;
        _shadowfeedService = shadowfeedService;
        _npcMessageVideoService = npcMessageVideoService;
    }

    [HttpPost("portrait-forge")]
    [ProducesResponseType<PortraitForgeResult>(StatusCodes.Status200OK)]
    public async Task<ActionResult<PortraitForgeResult>> ForgePortrait([FromBody] PortraitForgeRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("Portrait forge request is required.");
        }

        var result = await _portraitForge.ForgeAsync(request, cancellationToken);
        return Ok(result);
    }

    [HttpGet("portrait-forge/{portraitDraftId}")]
    [ProducesResponseType<PortraitForgeResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<PortraitForgeResult> GetPortraitDraft([FromRoute] string portraitDraftId)
    {
        var result = _portraitForge.Get(portraitDraftId);
        return result is null ? NotFound() : Ok(result);
    }

    [HttpGet("portrait-forge/entity/{entityId}")]
    [ProducesResponseType<IEnumerable<PortraitForgeResult>>(StatusCodes.Status200OK)]
    public ActionResult<IEnumerable<PortraitForgeResult>> ListPortraitDrafts([FromRoute] string entityId)
    {
        return Ok(_portraitForge.ListForEntity(entityId));
    }

    [HttpPost("portrait-forge/{portraitDraftId}/approve")]
    [ProducesResponseType<PortraitForgeResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<ActionResult<PortraitForgeResult>> ApprovePortraitDraft(
        [FromRoute] string portraitDraftId,
        [FromBody] PortraitApprovalRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("Portrait approval request is required.");
        }

        try
        {
            var result = await _portraitForge.ApproveAsync(portraitDraftId, request, cancellationToken);
            return result is null ? NotFound() : Ok(result);
        }
        catch (InvalidOperationException exception)
        {
            return Conflict(exception.Message);
        }
    }

    [HttpPost("packet-factory")]
    [ProducesResponseType<PacketFactoryResult>(StatusCodes.Status200OK)]
    public async Task<ActionResult<PacketFactoryResult>> CreatePacket([FromBody] PacketFactoryRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("Packet factory request is required.");
        }

        var result = await _packetFactory.CreateAsync(request, cancellationToken);
        return Ok(result);
    }

    [HttpGet("packet-factory/{packetId}")]
    [ProducesResponseType<PacketFactoryResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<PacketFactoryResult> GetPacket([FromRoute] string packetId)
    {
        var result = _packetFactory.Get(packetId);
        return result is null ? NotFound() : Ok(result);
    }

    [HttpPost("packet-factory/{packetId}/attachments")]
    [ProducesResponseType<IEnumerable<PacketAttachmentRecord>>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<IEnumerable<PacketAttachmentRecord>>> AttachPacket(
        [FromRoute] string packetId,
        [FromBody] PacketAttachmentBatchRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("Packet attachment batch is required.");
        }

        try
        {
            return Ok(await _packetFactory.AttachAsync(packetId, request, cancellationToken));
        }
        catch (KeyNotFoundException)
        {
            return NotFound();
        }
    }

    [HttpGet("assets")]
    [ProducesResponseType<IEnumerable<AssetCatalogItem>>(StatusCodes.Status200OK)]
    public ActionResult<IEnumerable<AssetCatalogItem>> ListAssets()
    {
        return Ok(_assetLifecycle.List());
    }

    [HttpGet("assets/{assetId}")]
    [ProducesResponseType<AssetCatalogItem>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<AssetCatalogItem> GetAsset([FromRoute] string assetId)
    {
        var entry = _assetLifecycle.Resolve(assetId);
        return entry is null ? NotFound() : Ok(entry);
    }

    [HttpPost("assets/{assetId}/lifecycle")]
    [ProducesResponseType<AssetCatalogItem>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<ActionResult<AssetCatalogItem>> ApplyAssetLifecycle(
        [FromRoute] string assetId,
        [FromBody] AssetLifecycleMutationRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("Asset lifecycle mutation is required.");
        }

        try
        {
            var entry = await _assetLifecycle.ApplyLifecycleAsync(assetId, request, cancellationToken);
            return entry is null ? NotFound() : Ok(entry);
        }
        catch (InvalidOperationException exception)
        {
            return Conflict(exception.Message);
        }
    }

    [HttpPost("assets/sweep")]
    [ProducesResponseType<AssetLifecycleSweepResult>(StatusCodes.Status200OK)]
    public ActionResult<AssetLifecycleSweepResult> SweepAssets()
    {
        return Ok(_assetLifecycle.SweepExpired());
    }

    [HttpGet("media-jobs")]
    [ProducesResponseType<IEnumerable<MediaRenderJobStatus>>(StatusCodes.Status200OK)]
    public ActionResult<IEnumerable<MediaRenderJobStatus>> ListMediaJobs()
    {
        return Ok(_mediaRenderJobs.List());
    }

    [HttpGet("media-jobs/{jobId}")]
    [ProducesResponseType<MediaRenderJobStatus>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<MediaRenderJobStatus> GetMediaJob([FromRoute] string jobId)
    {
        var job = _mediaRenderJobs.Get(jobId);
        return job is null ? NotFound() : Ok(job);
    }

    [HttpPost("news-network/brief")]
    [ProducesResponseType<NewsBriefResult>(StatusCodes.Status200OK)]
    public async Task<ActionResult<NewsBriefResult>> CreateNewsBrief(
        [FromBody] NewsBriefRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("News brief request is required.");
        }

        return Ok(await _newsNetworkService.BuildNewsBriefAsync(request, cancellationToken));
    }

    [HttpGet("news-network/brief/{briefId}")]
    [ProducesResponseType<NewsBriefResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<NewsBriefResult> GetNewsBrief([FromRoute] string briefId)
    {
        var result = _newsNetworkService.Get(briefId);
        return result is null ? NotFound() : Ok(result);
    }

    [HttpPost("news-network/brief/{briefId}/deliver")]
    [ProducesResponseType<NewsBriefDeliveryResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    public async Task<ActionResult<NewsBriefDeliveryResult>> DeliverNewsBrief(
        [FromRoute] string briefId,
        [FromBody] NewsBriefDeliveryRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("News brief delivery request is required.");
        }

        var result = await _newsNetworkService.DeliverAsync(briefId, request, cancellationToken);
        return result.Outcome switch
        {
            "missing" => NotFound(result),
            "approval-required" => Conflict(result),
            _ => Ok(result)
        };
    }

    [HttpPost("route-cinema")]
    [ProducesResponseType<RouteCinemaResult>(StatusCodes.Status200OK)]
    public async Task<ActionResult<RouteCinemaResult>> BuildRouteCinema(
        [FromBody] RouteCinemaRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("Route cinema request is required.");
        }

        return Ok(await _routeCinemaService.GenerateAsync(request, cancellationToken));
    }

    [HttpGet("route-cinema/{routeCinemaId}")]
    [ProducesResponseType<RouteCinemaResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<RouteCinemaResult> GetRouteCinema([FromRoute] string routeCinemaId)
    {
        var result = _routeCinemaService.Get(routeCinemaId);
        return result is null ? NotFound() : Ok(result);
    }

    [HttpGet("route-cinema/campaign/{campaignId}")]
    [ProducesResponseType<IEnumerable<RouteCinemaResult>>(StatusCodes.Status200OK)]
    public ActionResult<IEnumerable<RouteCinemaResult>> ListRouteCinema([FromRoute] string campaignId)
    {
        return Ok(_routeCinemaService.List(campaignId));
    }

    [HttpPost("shadowfeed")]
    [ProducesResponseType<ShadowfeedResult>(StatusCodes.Status200OK)]
    public async Task<ActionResult<ShadowfeedResult>> DraftShadowfeed(
        [FromBody] ShadowfeedRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("Shadowfeed request is required.");
        }

        return Ok(await _shadowfeedService.DraftAsync(request, cancellationToken));
    }

    [HttpPost("npc-message-video")]
    [ProducesResponseType<NpcVideoMessageResult>(StatusCodes.Status200OK)]
    public async Task<ActionResult<NpcVideoMessageResult>> BuildNpcMessageVideo(
        [FromBody] NpcVideoMessageRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("NPC message video request is required.");
        }

        return Ok(await _npcMessageVideoService.CreateAsync(request, cancellationToken));
    }

    [HttpGet("npc-message-video/{messageId}")]
    [ProducesResponseType<NpcVideoMessageResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<NpcVideoMessageResult> GetNpcMessageVideo([FromRoute] string messageId)
    {
        var result = _npcMessageVideoService.Get(messageId);
        return result is null ? NotFound() : Ok(result);
    }

    [HttpPost("npc-message-video/{messageId}/publish")]
    [ProducesResponseType<NpcVideoMessagePublishResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    [ProducesResponseType(StatusCodes.Status409Conflict)]
    [ProducesResponseType(StatusCodes.Status410Gone)]
    public async Task<ActionResult<NpcVideoMessagePublishResult>> PublishNpcMessageVideo(
        [FromRoute] string messageId,
        [FromBody] NpcVideoMessagePublishRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("NPC message video publish request is required.");
        }

        var result = await _npcMessageVideoService.PublishAsync(messageId, request, cancellationToken);
        return result.Outcome switch
        {
            "missing" => NotFound(result),
            "expired" => StatusCode(StatusCodes.Status410Gone, result),
            "approval-required" or "scope-mismatch" => Conflict(result),
            _ => Ok(result)
        };
    }
}
#pragma warning restore CS0618
