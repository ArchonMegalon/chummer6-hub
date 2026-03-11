using Chummer.Run.Contracts.Registry;
using Chummer.Run.Contracts.Observability;
using Chummer.Run.Registry.Services;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.Registry.Controllers;

[ApiController]
[Route("api/v1/registry")]
public sealed class HubRegistryController : ControllerBase
{
    private readonly IHubArtifactStore _artifactStore;

    public HubRegistryController(IHubArtifactStore artifactStore)
    {
        _artifactStore = artifactStore;
    }

    [HttpGet("search")]
    [ProducesResponseType<RegistrySearchResponse>(StatusCodes.Status200OK)]
    public ActionResult<RegistrySearchResponse> SearchArtifacts(
        [FromQuery] string? query = null,
        [FromQuery] string? kind = null,
        [FromQuery] string? state = null,
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 20)
    {
        if (page < 1)
        {
            return BadRequest("page must be at least 1.");
        }

        if (pageSize is < 1 or > 100)
        {
            return BadRequest("pageSize must be between 1 and 100.");
        }

        if (!TryParseKind(kind, out var parsedKind, out var kindError))
        {
            return BadRequest(kindError);
        }

        if (!TryParseState(state, out var parsedState, out var stateError))
        {
            return BadRequest(stateError);
        }

        var response = new RegistrySearchResponse(
            Items: _artifactStore.Search(query, parsedKind, parsedState, page, pageSize)
                .Select(ToSearchItem)
                .ToList(),
            Page: page,
            PageSize: pageSize,
            TotalCount: _artifactStore.SearchCount(query, parsedKind, parsedState));

        return Ok(response);
    }

    [HttpGet("artifacts")]
    [ProducesResponseType<RegistrySearchResponse>(StatusCodes.Status200OK)]
    public ActionResult<RegistrySearchResponse> ListArtifacts(
        [FromQuery] string? query = null,
        [FromQuery] string? kind = null,
        [FromQuery] string? state = null,
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 20)
    {
        return SearchArtifacts(query, kind, state, page, pageSize);
    }

    [HttpPost("artifacts")]
    [ProducesResponseType<HubArtifactMetadata>(StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<HubArtifactMetadata> CreateArtifact([FromBody] HubArtifactCreateRequest? request)
    {
        if (request is null)
        {
            return BadRequest("Artifact payload is required.");
        }

        if (string.IsNullOrWhiteSpace(request.Name))
        {
            return BadRequest("Artifact name is required.");
        }

        if (string.IsNullOrWhiteSpace(request.Version))
        {
            return BadRequest("Artifact version is required.");
        }

        var created = _artifactStore.UpsertArtifact(request);
        return CreatedAtAction(nameof(GetArtifact), new { id = created.Id }, created);
    }

    [HttpPost("runtime-bundles/issue")]
    [ProducesResponseType<RuntimeBundleIssueResponse>(StatusCodes.Status201Created)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<RuntimeBundleIssueResponse> IssueRuntimeBundle([FromBody] RuntimeBundleIssueRequest? request)
    {
        if (request is null)
        {
            return BadRequest("Runtime bundle payload is required.");
        }

        if (string.IsNullOrWhiteSpace(request.SessionId))
        {
            return BadRequest("SessionId is required.");
        }

        if (string.IsNullOrWhiteSpace(request.SceneId))
        {
            return BadRequest("SceneId is required.");
        }

        if (string.IsNullOrWhiteSpace(request.SourceBundleVersion))
        {
            return BadRequest("SourceBundleVersion is required.");
        }

        if (string.IsNullOrWhiteSpace(request.ProjectionFingerprint))
        {
            return BadRequest("ProjectionFingerprint is required.");
        }

        if (request.ProjectionVersion < 0)
        {
            return BadRequest("ProjectionVersion must be zero or greater.");
        }

        if (string.IsNullOrWhiteSpace(request.CollaborationMode))
        {
            return BadRequest("CollaborationMode is required.");
        }

        var issued = _artifactStore.IssueRuntimeBundle(request);
        return CreatedAtAction(nameof(GetRuntimeBundleArtifact), new { artifactId = issued.Artifact.Id }, issued);
    }

    [HttpGet("artifacts/{id}")]
    [ProducesResponseType<HubArtifactMetadata>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<HubArtifactMetadata> GetArtifact([FromRoute] string id)
    {
        if (string.IsNullOrWhiteSpace(id))
        {
            return BadRequest("id is required.");
        }

        var artifact = _artifactStore.GetArtifact(id);
        if (artifact is null)
        {
            return NotFound();
        }

        return Ok(artifact);
    }

    [HttpGet("runtime-bundles/{artifactId}")]
    [ProducesResponseType<RuntimeBundleArtifactProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<RuntimeBundleArtifactProjection> GetRuntimeBundleArtifact([FromRoute] string artifactId)
    {
        if (string.IsNullOrWhiteSpace(artifactId))
        {
            return BadRequest("artifactId is required.");
        }

        var artifact = _artifactStore.GetRuntimeBundleArtifact(artifactId);
        if (artifact is null)
        {
            return NotFound();
        }

        return Ok(artifact);
    }

    [HttpGet("runtime-bundles/heads/{sessionId}/{sceneId}")]
    [ProducesResponseType<RuntimeBundleHeadListResponse>(StatusCodes.Status200OK)]
    public ActionResult<RuntimeBundleHeadListResponse> GetRuntimeBundleHeads(
        [FromRoute] string sessionId,
        [FromRoute] string sceneId)
    {
        if (string.IsNullOrWhiteSpace(sessionId))
        {
            return BadRequest("sessionId is required.");
        }

        if (string.IsNullOrWhiteSpace(sceneId))
        {
            return BadRequest("sceneId is required.");
        }

        return Ok(_artifactStore.GetRuntimeBundleHeads(sessionId, sceneId));
    }

    [HttpGet("runtime-bundles/heads/{sessionId}/{sceneId}/{head}")]
    [ProducesResponseType<RuntimeBundleHeadProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<RuntimeBundleHeadProjection> GetRuntimeBundleHead(
        [FromRoute] string sessionId,
        [FromRoute] string sceneId,
        [FromRoute] RuntimeBundleHeadKind head)
    {
        if (string.IsNullOrWhiteSpace(sessionId))
        {
            return BadRequest("sessionId is required.");
        }

        if (string.IsNullOrWhiteSpace(sceneId))
        {
            return BadRequest("sceneId is required.");
        }

        var projection = _artifactStore.GetRuntimeBundleHead(sessionId, sceneId, head);
        if (projection is null)
        {
            return NotFound();
        }

        return Ok(projection);
    }

    [HttpGet("{id}/preview")]
    [HttpGet("artifacts/{id}/preview")]
    [ProducesResponseType<RegistryPreviewResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<RegistryPreviewResponse> GetPreview([FromRoute] string id)
    {
        if (string.IsNullOrWhiteSpace(id))
        {
            return NotFound();
        }

        var metadata = _artifactStore.GetArtifact(id);
        if (metadata is null)
        {
            return NotFound();
        }

        var response = new RegistryPreviewResponse(
            Id: metadata.Id,
            Name: metadata.Name,
            Kind: metadata.Kind.ToString(),
            Version: metadata.Version,
            Summary: metadata.Summary ?? $"Preview for artifact '{id}'.",
            State: metadata.State.ToString(),
            StateReason: metadata.StateReason,
            AcceptingNewInstalls: metadata.State == HubArtifactState.Active,
            ImmutableRetentionRequired: metadata.ImmutableRetentionRequired,
            SupersededByArtifactId: metadata.SupersededByArtifactId,
            Tags: Array.Empty<string>());

        return Ok(response);
    }

    [HttpGet("projections")]
    [ProducesResponseType<RegistryProjectionListResponse>(StatusCodes.Status200OK)]
    public ActionResult<RegistryProjectionListResponse> ListProjections(
        [FromQuery] string? query = null,
        [FromQuery] string? kind = null,
        [FromQuery] string? state = null,
        [FromQuery] int page = 1,
        [FromQuery] int pageSize = 20)
    {
        if (page < 1)
        {
            return BadRequest("page must be at least 1.");
        }

        if (pageSize is < 1 or > 100)
        {
            return BadRequest("pageSize must be between 1 and 100.");
        }

        if (!TryParseKind(kind, out var parsedKind, out var kindError))
        {
            return BadRequest(kindError);
        }

        if (!TryParseState(state, out var parsedState, out var stateError))
        {
            return BadRequest(stateError);
        }

        return Ok(new RegistryProjectionListResponse(
            Items: _artifactStore.SearchProjections(query, parsedKind, parsedState, page, pageSize),
            Page: page,
            PageSize: pageSize,
            TotalCount: _artifactStore.SearchProjectionCount(query, parsedKind, parsedState)));
    }

    [HttpGet("projections/pipelines")]
    [ProducesResponseType<PipelineProjectionEnvelope>(StatusCodes.Status200OK)]
    public ActionResult<PipelineProjectionEnvelope> GetPipelineProjection()
    {
        return Ok(new PipelineProjectionEnvelope(
            GeneratedAtUtc: DateTimeOffset.UtcNow,
            Pipelines: [_artifactStore.GetRegistryPipelineProjection()]));
    }

    [HttpGet("artifacts/{id}/projection")]
    [ProducesResponseType<RegistryProjectionResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<RegistryProjectionResponse> GetProjection([FromRoute] string id)
    {
        if (string.IsNullOrWhiteSpace(id))
        {
            return BadRequest("id is required.");
        }

        var projection = _artifactStore.GetProjection(id);
        if (projection is null)
        {
            return NotFound();
        }

        return Ok(projection);
    }

    [HttpGet("artifacts/{id}/install-projection")]
    [ProducesResponseType<HubArtifactInstallProjection>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<HubArtifactInstallProjection> GetInstallProjection([FromRoute] string id)
    {
        if (string.IsNullOrWhiteSpace(id))
        {
            return BadRequest("id is required.");
        }

        var projection = _artifactStore.GetInstallProjection(id);
        if (projection is null)
        {
            return NotFound();
        }

        return Ok(projection);
    }

    [HttpPatch("artifacts/{id}/state")]
    [ProducesResponseType<HubArtifactStateResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<HubArtifactStateResponse> ChangeState(
        [FromRoute] string id,
        [FromBody] HubArtifactStateChangeRequest? request)
    {
        if (string.IsNullOrWhiteSpace(id))
        {
            return BadRequest("id is required.");
        }

        if (request is null)
        {
            return BadRequest("State change request is required.");
        }

        var artifact = _artifactStore.GetArtifact(id);
        if (artifact is null)
        {
            return NotFound();
        }

        return Ok(_artifactStore.ChangeState(id, request));
    }

    [HttpDelete("artifacts/{id}")]
    [ProducesResponseType<HubArtifactDeleteAttemptResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<HubArtifactDeleteAttemptResponse> DeleteArtifact([FromRoute] string id)
    {
        if (string.IsNullOrWhiteSpace(id))
        {
            return BadRequest("id is required.");
        }

        var existing = _artifactStore.GetArtifact(id);
        if (existing is null)
        {
            return NotFound();
        }

        return Ok(_artifactStore.AttemptDelete(id));
    }

    [HttpGet("artifacts/state/{state}")]
    [ProducesResponseType<RegistrySearchResponse>(StatusCodes.Status200OK)]
    public ActionResult<RegistrySearchResponse> ListArtifactsByState([FromRoute] string state)
    {
        if (!Enum.TryParse<HubArtifactState>(state, true, out var parsedState))
        {
            return BadRequest("state must be one of Active, Delisted, Deprecated, Superseded, or BannedButRetained.");
        }

        var items = _artifactStore.ListByState(parsedState)
            .Select(ToSearchItem)
            .ToList();

        var response = new RegistrySearchResponse(
            Items: items,
            Page: 1,
            PageSize: items.Count,
            TotalCount: items.Count);

        return Ok(response);
    }

    [HttpPost("artifacts/{id}/install")]
    [ProducesResponseType<HubArtifactIdentifier>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<HubArtifactIdentifier> RegisterInstall(
        [FromRoute] string id,
        [FromBody] HubInstallEvent? installEvent)
    {
        if (string.IsNullOrWhiteSpace(id))
        {
            return BadRequest("id is required.");
        }

        if (installEvent is null)
        {
            return BadRequest("Install payload is required.");
        }

        if (!string.Equals(installEvent.ArtifactId, id, StringComparison.Ordinal))
        {
            return BadRequest("install payload artifactId must match route id.");
        }

        if (_artifactStore.GetArtifact(id) is null)
        {
            return NotFound();
        }

        return Ok(_artifactStore.RegisterInstall(id, installEvent));
    }

    [HttpPost("artifacts/{id}/reviews")]
    [ProducesResponseType<HubReviewListResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<HubReviewListResponse> AddReview(
        [FromRoute] string id,
        [FromBody] HubReviewRequest? request)
    {
        if (string.IsNullOrWhiteSpace(id))
        {
            return BadRequest("id is required.");
        }

        if (request is null)
        {
            return BadRequest("Review payload is required.");
        }

        if (request.Score is < 0 or > 10)
        {
            return BadRequest("Review score must be between 0 and 10.");
        }

        if (_artifactStore.GetArtifact(id) is null)
        {
            return NotFound();
        }

        return Ok(_artifactStore.AddReview(id, request));
    }

    [HttpGet("artifacts/{id}/reviews")]
    [ProducesResponseType<HubReviewListResponse>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public ActionResult<HubReviewListResponse> GetReviews([FromRoute] string id)
    {
        var artifact = _artifactStore.GetArtifact(id);
        if (artifact is null)
        {
            return NotFound();
        }

        return Ok(new HubReviewListResponse(
            ArtifactId: artifact.Id,
            AverageScore: artifact.AverageReviewScore,
            ReviewCount: artifact.ReviewCount,
            Reviews: Array.Empty<HubReviewResponse>()));
    }

    private static bool TryParseKind(string? value, out HubArtifactKind? kind, out string? error)
    {
        error = null;
        kind = null;

        if (string.IsNullOrWhiteSpace(value))
        {
            return true;
        }

        if (Enum.TryParse<HubArtifactKind>(value, true, out var parsed))
        {
            kind = parsed;
            return true;
        }

        error = "kind must be one of RulePack, RuleProfile, BuildKit, NpcVault, BuildIdea, or RuntimeBundle.";
        return false;
    }

    private static bool TryParseState(string? value, out HubArtifactState? state, out string? error)
    {
        error = null;
        state = null;

        if (string.IsNullOrWhiteSpace(value))
        {
            return true;
        }

        if (Enum.TryParse<HubArtifactState>(value, true, out var parsed))
        {
            state = parsed;
            return true;
        }

        error = "state must be one of Active, Delisted, Deprecated, Superseded, or BannedButRetained.";
        return false;
    }

    private static RegistrySearchItem ToSearchItem(HubArtifactMetadata metadata) => new(
        Id: metadata.Id,
        Name: metadata.Name,
        Kind: metadata.Kind.ToString(),
        Version: metadata.Version,
        Summary: metadata.Summary ?? string.Empty,
        State: metadata.State.ToString(),
        AcceptingNewInstalls: metadata.State == HubArtifactState.Active,
        ImmutableRetentionRequired: metadata.ImmutableRetentionRequired,
        InstallCount: metadata.InstallCount,
        ActiveRuntimeRefCount: metadata.ActiveRuntimeRefCount,
        SupersededByArtifactId: metadata.SupersededByArtifactId);
}
