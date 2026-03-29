using Chummer.Run.AI.Services.Ops;
using Chummer.Run.Contracts.Ops;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.AI.Controllers;

[ApiController]
[Route("api/v1/ai/ops-board")]
public sealed class GmOpsBoardController : ControllerBase
{
    private readonly IGmOpsBoardService _opsBoard;

    public GmOpsBoardController(IGmOpsBoardService opsBoard)
    {
        _opsBoard = opsBoard;
    }

    [HttpGet("{sessionId}/{sceneId}")]
    [ProducesResponseType<OpsBoardProjection>(StatusCodes.Status200OK)]
    public ActionResult<OpsBoardProjection> GetProjection(
        [FromRoute] string sessionId,
        [FromRoute] string sceneId,
        [FromQuery] string? sceneRevision = null)
    {
        if (string.IsNullOrWhiteSpace(sessionId) || string.IsNullOrWhiteSpace(sceneId))
        {
            return BadRequest("sessionId and sceneId are required.");
        }

        return Ok(_opsBoard.GetProjection(sessionId, sceneId, sceneRevision));
    }

    [HttpPost("prep-assets")]
    [ProducesResponseType<GmPrepAssetRecord>(StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<GmPrepAssetRecord> CreatePrepAsset([FromBody] GmPrepAssetCreateRequest? request)
    {
        if (request is null
            || string.IsNullOrWhiteSpace(request.CampaignId)
            || string.IsNullOrWhiteSpace(request.Title)
            || string.IsNullOrWhiteSpace(request.Body))
        {
            return BadRequest("campaignId, title, and body are required.");
        }

        var created = _opsBoard.CreatePrepAsset(request);
        return CreatedAtAction(nameof(GetPrepAsset), new { assetId = created.AssetId }, created);
    }

    [HttpGet("prep-assets/{assetId}")]
    [ProducesResponseType<GmPrepAssetRecord>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<GmPrepAssetRecord> GetPrepAsset([FromRoute] string assetId)
    {
        if (string.IsNullOrWhiteSpace(assetId))
        {
            return BadRequest("assetId is required.");
        }

        var asset = _opsBoard.GetPrepAsset(assetId);
        return asset is null ? NotFound() : Ok(asset);
    }

    [HttpGet("prep-assets")]
    [ProducesResponseType<GmPrepAssetListResponse>(StatusCodes.Status200OK)]
    public ActionResult<GmPrepAssetListResponse> ListPrepAssets(
        [FromQuery] string? campaignId = null,
        [FromQuery] string? sessionId = null,
        [FromQuery] string? sceneId = null,
        [FromQuery] GmPrepAssetKind? kind = null,
        [FromQuery] bool includeReusableCampaignAssets = false,
        [FromQuery] string? queryText = null)
    {
        return Ok(_opsBoard.ListPrepAssets(campaignId, sessionId, sceneId, kind, includeReusableCampaignAssets, queryText));
    }

    [HttpPost("prep-assets/{assetId}/checklist")]
    [ProducesResponseType<GmPrepAssetRecord>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<GmPrepAssetRecord> UpdateChecklist([FromRoute] string assetId, [FromBody] GmPrepChecklistUpdateRequest? request)
    {
        if (string.IsNullOrWhiteSpace(assetId))
        {
            return BadRequest("assetId is required.");
        }

        if (request is null || string.IsNullOrWhiteSpace(request.UpdatedBy))
        {
            return BadRequest("updatedBy is required.");
        }

        var updated = _opsBoard.UpdateChecklist(assetId, request);
        return updated is null ? NotFound() : Ok(updated);
    }

    [HttpPost("prep-assets/{assetId}/reveal")]
    [ProducesResponseType<GmPrepAssetRevealResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<GmPrepAssetRevealResult> Reveal([FromRoute] string assetId, [FromBody] GmPrepAssetRevealRequest? request)
    {
        if (string.IsNullOrWhiteSpace(assetId))
        {
            return BadRequest("assetId is required.");
        }

        if (request is null
            || string.IsNullOrWhiteSpace(request.SessionId)
            || string.IsNullOrWhiteSpace(request.SceneId)
            || string.IsNullOrWhiteSpace(request.SceneRevision)
            || string.IsNullOrWhiteSpace(request.RequestedBy))
        {
            return BadRequest("sessionId, sceneId, sceneRevision, and requestedBy are required.");
        }

        var result = _opsBoard.Reveal(assetId, request);
        return result.Outcome == "missing" ? NotFound(result) : Ok(result);
    }
}
