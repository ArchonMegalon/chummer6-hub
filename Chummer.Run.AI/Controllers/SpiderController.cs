using Chummer.Run.AI.Services.Spider;
using Chummer.Run.AI.Services.Session;
using Microsoft.AspNetCore.Mvc;

namespace Chummer.Run.AI.Controllers;

[ApiController]
[Route("api/v1/ai/spider")]
public sealed class SpiderController : ControllerBase
{
    private readonly IFastSignalDetector _detector;
    private readonly ISpiderDeepIngestionService _deepIngestion;
    private readonly IDirectorPolicyEngine _policyEngine;
    private readonly IDeliveryOutboxService _outbox;
    private readonly ISpiderCardActionService _actions;
    private readonly IInterruptionBudgetService _interruptionBudget;
    private readonly ISessionRuntimeBundleService _runtimeBundles;

    public SpiderController(
        IFastSignalDetector detector,
        ISpiderDeepIngestionService deepIngestion,
        IDirectorPolicyEngine policyEngine,
        IDeliveryOutboxService outbox,
        ISpiderCardActionService actions,
        IInterruptionBudgetService interruptionBudget,
        ISessionRuntimeBundleService runtimeBundles)
    {
        _detector = detector;
        _deepIngestion = deepIngestion;
        _policyEngine = policyEngine;
        _outbox = outbox;
        _actions = actions;
        _interruptionBudget = interruptionBudget;
        _runtimeBundles = runtimeBundles;
    }

    [HttpPost("observe")]
    [ProducesResponseType<PolicyDecision>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status202Accepted)]
    public async Task<ActionResult<PolicyDecision>> Observe([FromBody] SpiderObservation? observation, CancellationToken cancellationToken)
    {
        if (observation is null)
        {
            return BadRequest("Observation is required.");
        }

        var fastSignal = _detector.Detect(observation);
        var sceneId = ResolveSceneId(observation);
        var sceneRevision = ResolveSceneRevision(observation, sceneId);
        var bundle = _runtimeBundles.ResolveBundle(observation.SessionId, sceneId);
        var deepAnalysis = fastSignal?.Escalate == true
            ? await _deepIngestion.AnalyzeAsync(observation, fastSignal, sceneId, sceneRevision, bundle, cancellationToken)
            : null;
        var decision = _policyEngine.Decide(observation, fastSignal, deepAnalysis, sceneRevision);
        if (decision.ShouldDeliver)
        {
            var budget = _interruptionBudget.Evaluate(observation.SessionId, decision.InterruptionLevel, DateTimeOffset.UtcNow);
            if (!budget.Allowed)
            {
                return Accepted(new PolicyDecision(
                    SessionId: decision.SessionId,
                    Action: "throttle",
                    InterruptionLevel: decision.InterruptionLevel,
                    Rationale: $"{decision.Rationale} | interruption budget empty for this minute.",
                    ShouldDeliver: false,
                    ExpireAfter: TimeSpan.FromMinutes(1),
                    CardKind: "throttle",
                    CardTitle: "Spider throttled",
                    Tags: ["budget-empty"],
                    DecisionTier: decision.DecisionTier,
                    DeepAnalysis: deepAnalysis));
            }

            var channel = observation.Source;
            var card = BuildCard(observation, fastSignal, sceneId, sceneRevision, decision, budget, bundle);
            var message = $"{decision.CardTitle}: {decision.Rationale} | signal={fastSignal?.Signal} | tier={decision.DecisionTier} | budgetRemaining={budget.RemainingThisMinute}";
            _outbox.Enqueue(new DeliveryOutboxCreateRequest(
                SessionId: observation.SessionId,
                SceneId: sceneId,
                SceneRevision: sceneRevision,
                Channel: channel,
                Content: message,
                ApprovalState: "pending",
                AutonomyMode: decision.InterruptionLevel.ToString(),
                Ttl: TimeSpan.FromMinutes(8),
                SceneStartedAtUtc: observation.ObservedAtUtc,
                ProjectionFingerprint: bundle.ProjectionFingerprint,
                CollaborationMode: bundle.CollaborationMode,
                Card: card));

            return Ok(decision);
        }

        return Accepted(decision);
    }

    [HttpPost("outbox")]
    [ProducesResponseType<DeliveryOutboxMessage>(StatusCodes.Status200OK)]
    public ActionResult<DeliveryOutboxMessage> QueueManual([FromBody] DeliveryOutboxCreateRequest? request)
    {
        if (request is null)
        {
            return BadRequest("Outbox request is required.");
        }

        if (string.IsNullOrWhiteSpace(request.SessionId) || string.IsNullOrWhiteSpace(request.SceneId))
        {
            return BadRequest("sessionId and sceneId are required.");
        }

        return Ok(_outbox.Enqueue(request));
    }

    [HttpGet("outbox/{sessionId}/{sceneId}")]
    [ProducesResponseType<IEnumerable<DeliveryOutboxMessage>>(StatusCodes.Status200OK)]
    public ActionResult<IEnumerable<DeliveryOutboxMessage>> GetOutbox([FromRoute] string sessionId, [FromRoute] string sceneId, [FromQuery] string? sceneRevision = null)
    {
        if (string.IsNullOrWhiteSpace(sessionId) || string.IsNullOrWhiteSpace(sceneId))
        {
            return BadRequest("sessionId and sceneId are required.");
        }

        return Ok(_outbox.GetForScene(sessionId, sceneId, sceneRevision));
    }

    [HttpPost("outbox/{messageId}/actions/{actionId}")]
    [ProducesResponseType<SpiderActionExecutionResult>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    [ProducesResponseType(StatusCodes.Status404NotFound)]
    public async Task<ActionResult<SpiderActionExecutionResult>> ExecuteAction(
        [FromRoute] string messageId,
        [FromRoute] string actionId,
        [FromBody] SpiderActionExecuteRequest? request,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(messageId) || string.IsNullOrWhiteSpace(actionId))
        {
            return BadRequest("messageId and actionId are required.");
        }

        if (request is null
            || string.IsNullOrWhiteSpace(request.SessionId)
            || string.IsNullOrWhiteSpace(request.SceneId)
            || string.IsNullOrWhiteSpace(request.SceneRevision)
            || string.IsNullOrWhiteSpace(request.RequestedBy))
        {
            return BadRequest("sessionId, sceneId, sceneRevision, and requestedBy are required.");
        }

        var result = await _actions.ExecuteAsync(messageId, actionId, request, cancellationToken);
        return result.Outcome == "missing"
            ? NotFound(result)
            : Ok(result);
    }

    [HttpGet("interruption/{sessionId}/{level}")]
    [ProducesResponseType<InterruptionBudgetProfile>(StatusCodes.Status200OK)]
    [ProducesResponseType(StatusCodes.Status400BadRequest)]
    public ActionResult<InterruptionBudgetProfile> GetInterruptionBudget(
        [FromRoute] string sessionId,
        [FromRoute] string level)
    {
        if (string.IsNullOrWhiteSpace(sessionId))
        {
            return BadRequest("sessionId is required.");
        }

        if (!Enum.TryParse<InterruptionLevel>(level, true, out var parsedLevel))
        {
            return BadRequest("level must be one of Off, Low, Tactical, Narrative, High.");
        }

        return Ok(_interruptionBudget.Peek(sessionId, parsedLevel, DateTimeOffset.UtcNow));
    }

    private static SpiderTacticalCard BuildCard(
        SpiderObservation observation,
        FastSignal? signal,
        string sceneId,
        string sceneRevision,
        PolicyDecision decision,
        InterruptionBudgetProfile budget,
        SessionRuntimeBundleDto bundle)
    {
        var now = DateTimeOffset.UtcNow;
        var actionDigest = decision.SuggestedActions is { Count: > 0 }
            ? string.Join(", ", decision.SuggestedActions.Select(item => item.ActionId))
            : "none";
        return new SpiderTacticalCard(
            CardId: Guid.NewGuid().ToString("N"),
            SessionId: observation.SessionId,
            SceneId: sceneId,
            SceneRevision: sceneRevision,
            CardKind: decision.CardKind,
            Title: string.IsNullOrWhiteSpace(decision.CardTitle) ? "Spider card" : decision.CardTitle,
            Summary: decision.Rationale,
            InterruptionLevel: decision.InterruptionLevel,
            Status: "pending",
            ProjectionFingerprint: bundle.ProjectionFingerprint,
            Tags: decision.Tags?.ToArray() ?? Array.Empty<string>(),
            Actions: decision.SuggestedActions?.ToArray() ?? Array.Empty<SpiderTacticalAction>(),
            Evidence: decision.Evidence?.ToArray() ?? Array.Empty<EvidencePointer>(),
            ActionExecutions: Array.Empty<SpiderActionExecutionState>(),
            CreatedAtUtc: now,
            StaleAfterUtc: decision.ExpireAfter.HasValue ? now.Add(decision.ExpireAfter.Value) : null,
            Payload: new SpiderTacticalPayload(
                Workflow: "ooda",
                Observe: $"{observation.Source} @ {observation.ObservedAtUtc:O}",
                Orient: decision.DeepAnalysis?.Summary ?? decision.Rationale,
                Decide: $"{decision.Action} [{decision.InterruptionLevel}]",
                Act: actionDigest,
                DecisionTier: decision.DecisionTier,
                SignalConfidence: signal?.Confidence,
                BudgetRemainingThisMinute: budget.RemainingThisMinute,
                BudgetLimitPerMinute: budget.LimitPerMinute,
                BudgetAllowed: budget.Allowed,
                IsStaleDraft: false,
                DraftState: "active"));
    }

    private static string ResolveSceneId(SpiderObservation observation)
    {
        if (!string.IsNullOrWhiteSpace(observation.SceneId))
        {
            return observation.SceneId;
        }

        return ParseTaggedValue(observation.Payload, "scene") ?? "default";
    }

    private static string ResolveSceneRevision(SpiderObservation observation, string sceneId)
    {
        if (!string.IsNullOrWhiteSpace(observation.SceneRevision))
        {
            return observation.SceneRevision;
        }

        return ParseTaggedValue(observation.Payload, "scene-revision")
            ?? ParseTaggedValue(observation.Payload, "revision")
            ?? sceneId;
    }

    private static string? ParseTaggedValue(string payload, string tag)
    {
        if (string.IsNullOrWhiteSpace(payload))
        {
            return null;
        }

        var prefix = $"{tag}:";
        var start = payload.IndexOf(prefix, StringComparison.OrdinalIgnoreCase);
        if (start < 0)
        {
            return null;
        }

        var remaining = payload[(start + prefix.Length)..];
        return remaining.Split('|', ';', ',', ' ').FirstOrDefault()?.Trim() is { Length: > 0 } value
            ? value
            : null;
    }
}
