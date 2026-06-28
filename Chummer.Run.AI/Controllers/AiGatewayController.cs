using Chummer.Run.AI.Services.Gateway;
using Chummer.Run.AI.Services.Lore;
using Chummer.Run.AI.Services.Session;
using LoreIngestionRequest = Chummer.Run.Contracts.AI.LoreIngestionRequest;
using LoreLensQuery = Chummer.Run.Contracts.AI.LoreLensQuery;
using LoreLensResult = Chummer.Run.Contracts.AI.LoreLensResult;
using LoreSearchRequest = Chummer.Run.Contracts.AI.LoreSearchRequest;
using LoreSearchResult = Chummer.Run.Contracts.AI.LoreSearchResult;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.AI.Controllers;

[ApiController]
[Route("api/v1/ai")]
public sealed class AiGatewayController : ControllerBase
{
    private const int MaxRequestBodyBytes = 16 * 1024;

    private readonly IAiGatewayService _gateway;
    private readonly IPromptRegistry _promptRegistry;
    private readonly IConversationStore _conversationStore;
    private readonly IEvaluationStore _evaluationStore;
    private readonly IAiBudgetService _budget;
    private readonly IGovernedSkillRuntimeService _skills;
    private readonly ISessionMemoryService _sessionMemory;
    private readonly ILoreService _loreService;
    private readonly IPersonaMemoryService _personaMemoryService;

    public AiGatewayController(
        IAiGatewayService gateway,
        IPromptRegistry promptRegistry,
        IConversationStore conversationStore,
        IEvaluationStore evaluationStore,
        IAiBudgetService budget,
        IGovernedSkillRuntimeService skills,
        ISessionMemoryService sessionMemory,
        ILoreService loreService,
        IPersonaMemoryService personaMemoryService)
    {
        _gateway = gateway;
        _promptRegistry = promptRegistry;
        _conversationStore = conversationStore;
        _evaluationStore = evaluationStore;
        _budget = budget;
        _skills = skills;
        _sessionMemory = sessionMemory;
        _loreService = loreService;
        _personaMemoryService = personaMemoryService;
    }

    [HttpGet("status")]
    [ProducesResponseType<GatewayStatus>(StatusCodes.Status200OK)]
    public async Task<ActionResult<GatewayStatus>> Status(CancellationToken cancellationToken)
    {
        var status = await _gateway.GetStatusAsync();
        return Ok(status);
    }

    [HttpPost("route")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<GatewayInvocation>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<ActionResult<GatewayInvocation>> Route([FromBody] ProviderRouteRequest? request, CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("Route request is required.");
        }

        if (string.IsNullOrWhiteSpace(request.Purpose) || string.IsNullOrWhiteSpace(request.Prompt))
        {
            return BadRequest("Purpose and prompt are required.");
        }

        var result = await _gateway.ExecuteRouteAsync(request, cancellationToken);
        return Ok(result);
    }

    [HttpPost("route/preview")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<GatewayRoutePreview>(StatusCodes.Status200OK)]
    public ActionResult<GatewayRoutePreview> RoutePreview([FromBody] ProviderRouteRequest? request)
    {
        if (request is null)
        {
            return BadRequest("Route request is required.");
        }

        return Ok(_gateway.Preview(request));
    }

    [HttpGet("prompts")]
    [ProducesResponseType<IEnumerable<PromptTemplate>>(StatusCodes.Status200OK)]
    public ActionResult<IEnumerable<PromptTemplate>> PromptTemplates()
    {
        return Ok(_promptRegistry.List());
    }

    [HttpPost("prompts")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<PromptTemplate>(StatusCodes.Status201Created)]
    public ActionResult<PromptTemplate> UpsertPrompt([FromBody] PromptTemplate? template)
    {
        if (template is null)
        {
            return BadRequest("Prompt template is required.");
        }

        _promptRegistry.Register(template);
        return Created(string.Empty, template);
    }

    [HttpPost("prompts/preview")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<PromptRenderResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<PromptRenderResult> PreviewPrompt([FromBody] PromptRenderRequest? request)
    {
        if (request is null)
        {
            return BadRequest("Prompt render request is required.");
        }

        try
        {
            var rendered = _promptRegistry.Render(request);
            return Ok(rendered);
        }
        catch (Exception exception)
        {
            return BadRequest(exception.Message);
        }
    }

    [HttpPost("budget/check")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<BudgetCheckResult>(StatusCodes.Status200OK)]
    public ActionResult<BudgetCheckResult> CheckBudget([FromBody] BudgetCheckRequest? request)
    {
        if (request is null)
        {
            return BadRequest("Budget check request is required.");
        }

        return Ok(_budget.Check(request));
    }

    [HttpGet("budget/{sessionId}")]
    [ProducesResponseType<IEnumerable<GatewayBudgetStatus>>(StatusCodes.Status200OK)]
    public ActionResult<IEnumerable<GatewayBudgetStatus>> BudgetStatus([FromRoute] string sessionId)
    {
        if (string.IsNullOrWhiteSpace(sessionId))
        {
            return BadRequest("sessionId is required.");
        }

        return Ok(_budget.StatusesForSession(sessionId));
    }

    [HttpGet("skills/adapters")]
    [ProducesResponseType<IEnumerable<GovernedSkillAdapterDescriptor>>(StatusCodes.Status200OK)]
    public ActionResult<IEnumerable<GovernedSkillAdapterDescriptor>> ListSkillAdapters()
    {
        return Ok(_skills.ListAdapters());
    }

    [HttpPost("skills/execute")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<GovernedSkillExecutionResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public async Task<ActionResult<GovernedSkillExecutionResult>> ExecuteSkill(
        [FromBody] GovernedSkillExecutionRequest? request,
        CancellationToken cancellationToken)
    {
        if (request is null)
        {
            return BadRequest("Skill execution request is required.");
        }

        if (string.IsNullOrWhiteSpace(request.SkillId)
            || string.IsNullOrWhiteSpace(request.SessionId)
            || string.IsNullOrWhiteSpace(request.Purpose)
            || string.IsNullOrWhiteSpace(request.Prompt))
        {
            return BadRequest("SkillId, sessionId, purpose, and prompt are required.");
        }

        var result = await _skills.ExecuteAsync(request, cancellationToken);
        return Ok(result);
    }

    [HttpPost("conversations/{sessionId}/turns")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<ConversationAppendResult>(StatusCodes.Status200OK)]
    public async Task<ActionResult<ConversationAppendResult>> AddConversationTurn(
        [FromRoute] string sessionId,
        [FromBody] ConversationAppendRequest? request,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(sessionId))
        {
            return BadRequest("sessionId is required.");
        }

        if (request is null)
        {
            return BadRequest("Conversation turn request is required.");
        }

        var result = await _conversationStore.AppendAsync(sessionId, request, cancellationToken);
        return Ok(result);
    }

    [HttpGet("conversations/{sessionId}")]
    [ProducesResponseType<IEnumerable<ConversationTurn>>(StatusCodes.Status200OK)]
    public ActionResult<IEnumerable<ConversationTurn>> GetConversation([FromRoute] string sessionId)
    {
        if (string.IsNullOrWhiteSpace(sessionId))
        {
            return BadRequest("sessionId is required.");
        }

        return Ok(_conversationStore.GetTurns(sessionId));
    }

    [HttpPost("evaluations")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<EvaluationResult>(StatusCodes.Status200OK)]
    public ActionResult<EvaluationResult> RecordEvaluation([FromBody] EvaluationRequest? request)
    {
        if (request is null)
        {
            return BadRequest("Evaluation request is required.");
        }

        return Ok(_evaluationStore.Add(request));
    }

    [HttpGet("evaluations")]
    [ProducesResponseType<IEnumerable<EvaluationResult>>(StatusCodes.Status200OK)]
    public ActionResult<IEnumerable<EvaluationResult>> ListEvaluations()
    {
        return Ok(_evaluationStore.GetAll());
    }

    [HttpGet("evaluations/{requestId}")]
    [ProducesResponseType<EvaluationResult>(StatusCodes.Status200OK)]
    public ActionResult<EvaluationResult> GetEvaluation([FromRoute] string requestId)
    {
        var result = _evaluationStore.TryGet(requestId);
        return result is null ? NotFound() : Ok(result);
    }

    [HttpPost("evaluations/runs")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<PromptEvaluationRunResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<PromptEvaluationRunResult> RunEvaluations([FromBody] PromptEvaluationRunRequest? request)
    {
        if (request is null)
        {
            return BadRequest("Evaluation run request is required.");
        }

        try
        {
            return Ok(_evaluationStore.Run(request));
        }
        catch (Exception exception)
        {
            return BadRequest(exception.Message);
        }
    }

    [HttpGet("evaluations/runs")]
    [ProducesResponseType<IEnumerable<PromptEvaluationRunResult>>(StatusCodes.Status200OK)]
    public ActionResult<IEnumerable<PromptEvaluationRunResult>> ListEvaluationRuns()
    {
        return Ok(_evaluationStore.GetRuns());
    }

    [HttpGet("evaluations/runs/{runId}")]
    [ProducesResponseType<PromptEvaluationRunResult>(StatusCodes.Status200OK)]
    public ActionResult<PromptEvaluationRunResult> GetEvaluationRun([FromRoute] string runId)
    {
        var result = _evaluationStore.TryGetRun(runId);
        return result is null ? NotFound() : Ok(result);
    }

    [HttpPost("lore")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<LoreSearchResult>(StatusCodes.Status200OK)]
    public ActionResult<LoreSearchResult> SearchLore([FromBody] LoreSearchRequest? request)
    {
        if (request is null)
        {
            request = new LoreSearchRequest();
        }

        return Ok(_loreService.Search(request));
    }

    [HttpPost("lore/lens")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<LoreLensResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<LoreLensResult> QueryLoreLens([FromBody] LoreLensQuery? request)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.QueryText))
        {
            return BadRequest("Lore Lens queryText is required.");
        }

        return Ok(_loreService.QueryLoreLens(request));
    }

    [HttpPost("lore/chunks")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType(StatusCodes.Status202Accepted)]
    public ActionResult<IEnumerable<string>> IngestLore([FromBody] LoreIngestionRequest? request)
    {
        if (request is null)
        {
            return BadRequest("Lore ingestion request is required.");
        }

        _loreService.Ingest(request);
        return Accepted(new[] { request.ChunkId });
    }

    [HttpPost("persona/{sessionId}/memory")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<PersonaMemoryResult>(StatusCodes.Status200OK)]
    public ActionResult<PersonaMemoryResult> QueryPersonaMemory(
        [FromRoute] string sessionId,
        [FromBody] PersonaMemoryQuery? query)
    {
        if (string.IsNullOrWhiteSpace(sessionId))
        {
            return BadRequest("sessionId is required.");
        }

        var effectiveQuery = (query ?? new PersonaMemoryQuery(sessionId)) with
        {
            SessionId = sessionId
        };

        return Ok(_personaMemoryService.Search(sessionId, effectiveQuery));
    }

    [HttpPost("persona/{sessionId}/cards")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<PersonaMemoryCard>(StatusCodes.Status202Accepted)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<PersonaMemoryCard> UpsertPersonaCard(
        [FromRoute] string sessionId,
        [FromBody] PersonaMemoryCard? card)
    {
        if (string.IsNullOrWhiteSpace(sessionId))
        {
            return BadRequest("sessionId is required.");
        }

        if (card is null || string.IsNullOrWhiteSpace(card.PersonaId))
        {
            return BadRequest("persona card is required.");
        }

        var effectiveCard = card.UpdatedAtUtc == default
            ? card with { UpdatedAtUtc = DateTimeOffset.UtcNow }
            : card;
        _personaMemoryService.Upsert(sessionId, effectiveCard);
        return Accepted(effectiveCard);
    }

    [HttpPost("session-memory/draft")]
    [RequestSizeLimit(MaxRequestBodyBytes)]
    [ProducesResponseType<SessionMemoryDraftResult>(StatusCodes.Status200OK)]
    public ActionResult<SessionMemoryDraftResult> DraftFromSession([FromBody] SessionMemoryDraftRequest? request)
    {
        if (request is null || string.IsNullOrWhiteSpace(request.SessionId))
        {
            return BadRequest("sessionId is required.");
        }

        var draft = _sessionMemory.Draft(request, request.SceneId);
        return Ok(draft);
    }
}
