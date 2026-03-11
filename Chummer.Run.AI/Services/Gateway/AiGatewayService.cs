
using Chummer.Run.Contracts.Observability;
using System.Collections.Concurrent;

namespace Chummer.Run.AI.Services.Gateway;

public interface IAiGatewayService
{
    Task<GatewayInvocation> ExecuteRouteAsync(ProviderRouteRequest request, CancellationToken cancellationToken);
    GatewayRoutePreview Preview(ProviderRouteRequest request);
    Task<GatewayStatus> GetStatusAsync();
    PipelineProjection GetGatewayPipelineProjection();
}

public sealed class AiGatewayService : IAiGatewayService
{
    private const int MaxRouteAudits = 200;
    private readonly IProviderRouter _router;
    private readonly IReadOnlyList<IProviderAdapter> _providers;
    private readonly IAiBudgetService _budget;
    private readonly IPromptRegistry _prompts;
    private readonly ConcurrentDictionary<string, byte> _idempotencyKeys = new(StringComparer.Ordinal);
    private readonly ConcurrentQueue<PipelineDeadLetterEntry> _deadLetters = new();
    private readonly ConcurrentQueue<GatewayRouteAuditEntry> _routeAudits = new();
    private readonly ConcurrentDictionary<AiProvider, ProviderSelectionCounter> _providerSelections = new();
    private long _processedCount;
    private long _successCount;
    private long _failureCount;
    private long _replayCount;
    private DateTimeOffset? _lastReplayAtUtc;
    private double _estimatedCostUsd;
    private int _budgetUnitsConsumed;

    public AiGatewayService(
        IProviderRouter router,
        IEnumerable<IProviderAdapter> providers,
        IAiBudgetService budget,
        IPromptRegistry prompts)
    {
        _router = router;
        _providers = providers.ToList();
        _budget = budget;
        _prompts = prompts;
    }

    public async Task<GatewayInvocation> ExecuteRouteAsync(ProviderRouteRequest request, CancellationToken cancellationToken)
    {
        Interlocked.Increment(ref _processedCount);
        TrackIdempotency(request);
        var decision = _router.Resolve(request);
        var auditId = Guid.NewGuid().ToString("N");
        var now = DateTimeOffset.UtcNow;
        var budgetSessionId = ResolveBudgetSessionId(request.SessionId, request);
        var budgetRequest = new BudgetCheckRequest(
            SessionId: budgetSessionId,
            EstimatedTokens: request.MaxTokens,
            Provider: decision.Provider);
        var budgetResult = _budget.Check(budgetRequest);
        if (!budgetResult.Allowed)
        {
            Interlocked.Increment(ref _failureCount);
            EnqueueDeadLetter(request, budgetResult.RejectedReason ?? "budget rejected");
            TrackProviderSelection(decision, success: false, budgetRejected: true);
            AppendRouteAudit(new GatewayRouteAuditEntry(
                AuditId: auditId,
                OccurredAtUtc: now,
                SessionId: budgetSessionId,
                Purpose: request.Purpose,
                Decision: decision,
                BudgetAllowed: false,
                BudgetOutcome: budgetResult.RejectedReason ?? "budget rejected",
                Success: false,
                Error: budgetResult.RejectedReason));
            return new GatewayInvocation(
                Request: request,
                Decision: decision,
                Output: null,
                Success: false,
                Error: budgetResult.RejectedReason,
                Prompt: ResolvePromptResult(request));
        }

        var provider = _providers.FirstOrDefault(x => x.Provider == decision.Provider)
                       ?? throw new InvalidOperationException($"Provider adapter {decision.Provider} is not registered.");
        if (!provider.Enabled)
        {
            Interlocked.Increment(ref _failureCount);
            EnqueueDeadLetter(request, $"{decision.Provider} disabled");
            TrackProviderSelection(decision, success: false, budgetRejected: false);
            AppendRouteAudit(new GatewayRouteAuditEntry(
                AuditId: auditId,
                OccurredAtUtc: now,
                SessionId: budgetSessionId,
                Purpose: request.Purpose,
                Decision: decision,
                BudgetAllowed: true,
                BudgetOutcome: "provider disabled",
                Success: false,
                Error: $"{decision.Provider} is not enabled in the current runtime configuration."));
            return new GatewayInvocation(
                Request: request,
                Decision: decision,
                Output: null,
                Success: false,
                Error: $"{decision.Provider} is not enabled in the current runtime configuration.",
                Prompt: ResolvePromptResult(request));
        }

        try
        {
            var output = await provider.GenerateAsync(request, cancellationToken);
            Interlocked.Increment(ref _successCount);
            Interlocked.Add(ref _budgetUnitsConsumed, Math.Max(1, request.MaxTokens / 512));
            AddEstimatedCost(decision.EstimatedCostUsd);
            TrackProviderSelection(decision, success: true, budgetRejected: false);
            AppendRouteAudit(new GatewayRouteAuditEntry(
                AuditId: auditId,
                OccurredAtUtc: now,
                SessionId: budgetSessionId,
                Purpose: request.Purpose,
                Decision: decision,
                BudgetAllowed: true,
                BudgetOutcome: "allowed",
                Success: true,
                Error: null));
            return new GatewayInvocation(
                Request: request,
                Decision: decision,
                Output: output,
                Success: true,
                Error: null,
                Prompt: ResolvePromptResult(request));
        }
        catch (Exception exception)
        {
            Interlocked.Increment(ref _failureCount);
            EnqueueDeadLetter(request, exception.Message);
            TrackProviderSelection(decision, success: false, budgetRejected: false);
            AppendRouteAudit(new GatewayRouteAuditEntry(
                AuditId: auditId,
                OccurredAtUtc: now,
                SessionId: budgetSessionId,
                Purpose: request.Purpose,
                Decision: decision,
                BudgetAllowed: true,
                BudgetOutcome: "provider error",
                Success: false,
                Error: exception.Message));
            return new GatewayInvocation(
                Request: request,
                Decision: decision,
                Output: null,
                Success: false,
                Error: exception.Message,
                Prompt: ResolvePromptResult(request));
        }
    }

    public GatewayRoutePreview Preview(ProviderRouteRequest request)
    {
        var decision = _router.Resolve(request);
        var budgetSessionId = ResolveBudgetSessionId(request.SessionId, request);
        var budgetResult = _budget.Preview(new BudgetCheckRequest(
            SessionId: budgetSessionId,
            EstimatedTokens: request.MaxTokens,
            Provider: decision.Provider));
        return new GatewayRoutePreview(
            Request: request,
            Decision: decision,
            EstimatedAllowed: budgetResult.Allowed,
            Reason: budgetResult.RejectedReason ?? "preview pass");
    }

    public Task<GatewayStatus> GetStatusAsync()
    {
        var budgetStatuses = _budget.AllStatuses();
        var providers = _providers
            .Select(provider => new ProviderDescriptor(
                Id: provider.Provider.ToString(),
                DisplayName: provider.Provider.ToString(),
                Enabled: provider.Enabled,
                PrimaryForTooling: provider.PrimaryForStructuredOutput))
            .ToList();

        var status = new GatewayStatus(
            Enabled: true,
            DryRunOnly: false,
            ActiveConversations: 0,
            RegisteredProviders: providers,
            PromptTemplates: _prompts.List().ToArray(),
            BudgetStatuses: budgetStatuses,
            SelectionVisibility: BuildSelectionVisibility(),
            UtcNow: DateTimeOffset.UtcNow);

        return Task.FromResult(status);
    }

    public PipelineProjection GetGatewayPipelineProjection()
    {
        var statuses = _budget.AllStatuses();
        var activeBudgetLedgers = statuses.Count(static status => status.MonthlyUsed > 0 || status.BurstUsedThisMinute > 0);
        return new PipelineProjection(
            Pipeline: "ai-gateway",
            Observability: new PipelineObservabilityProjection(
                ProcessedCount: ToInt(_processedCount),
                ActiveCount: activeBudgetLedgers,
                SucceededCount: ToInt(_successCount),
                FailedCount: ToInt(_failureCount),
                DuplicateCount: ToInt(_replayCount),
                IgnoredCount: 0),
            Idempotency: new PipelineIdempotencyProjection(
                TrackedKeys: _idempotencyKeys.Count,
                ReplayCount: ToInt(_replayCount),
                LastReplayAtUtc: _lastReplayAtUtc),
            Cost: new PipelineCostProjection(
                EstimatedUsd: Math.Round(Interlocked.CompareExchange(ref _estimatedCostUsd, 0, 0), 4),
                BudgetUnitsConsumed: _budgetUnitsConsumed),
            DeadLetter: new PipelineDeadLetterProjection(
                Count: _deadLetters.Count,
                Recent: _deadLetters.Take(25).ToArray()));
    }

    private static string ResolveBudgetSessionId(string? requestedSessionId, ProviderRouteRequest request) =>
        !string.IsNullOrWhiteSpace(requestedSessionId)
            ? requestedSessionId
            : $"route:{request.Purpose}";

    private PromptRenderResult? ResolvePromptResult(ProviderRouteRequest request)
    {
        if (request.PromptLineage is null)
        {
            return null;
        }

        return new PromptRenderResult(
            TemplateName: request.PromptLineage.TemplateName,
            Version: request.PromptLineage.TemplateVersion,
            RenderedText: request.Prompt,
            Lineage: request.PromptLineage,
            MissingInputs: false,
            UnresolvedPlaceholders: Array.Empty<string>());
    }

    private void TrackIdempotency(ProviderRouteRequest request)
    {
        var key = $"{request.SessionId ?? "none"}|{request.Purpose}|{request.MaxTokens}|{request.StructuredOutput}|{request.Prompt}";
        if (!_idempotencyKeys.TryAdd(key, 0))
        {
            Interlocked.Increment(ref _replayCount);
            _lastReplayAtUtc = DateTimeOffset.UtcNow;
        }
    }

    private void EnqueueDeadLetter(ProviderRouteRequest request, string reason)
    {
        _deadLetters.Enqueue(new PipelineDeadLetterEntry(
            ItemId: $"{request.SessionId ?? "route"}:{request.Purpose}",
            Reason: reason,
            OccurredAtUtc: DateTimeOffset.UtcNow,
            Fingerprint: request.Prompt.Length <= 64 ? request.Prompt : request.Prompt[..64]));
        while (_deadLetters.Count > 200 && _deadLetters.TryDequeue(out _))
        {
        }
    }

    private void AddEstimatedCost(double delta)
    {
        double initial, computed;
        do
        {
            initial = _estimatedCostUsd;
            computed = initial + delta;
        } while (Math.Abs(Interlocked.CompareExchange(ref _estimatedCostUsd, computed, initial) - initial) > double.Epsilon);
    }

    private GatewaySelectionVisibility BuildSelectionVisibility()
    {
        var providerStatuses = _providerSelections
            .OrderBy(pair => pair.Key.ToString(), StringComparer.Ordinal)
            .Select(pair => pair.Value.ToStatus(pair.Key))
            .ToArray();
        var totalRoutes = providerStatuses.Sum(static status => status.TotalSelections);
        var totalFallbackRoutes = providerStatuses.Sum(static status => status.FallbackSelections);
        var audits = _routeAudits.TakeLast(50).ToArray();
        return new GatewaySelectionVisibility(
            TotalRoutes: totalRoutes,
            TotalFallbackRoutes: totalFallbackRoutes,
            Providers: providerStatuses,
            RecentAudits: audits);
    }

    private void TrackProviderSelection(ProviderRouteDecision decision, bool success, bool budgetRejected)
    {
        var counter = _providerSelections.GetOrAdd(decision.Provider, _ => new ProviderSelectionCounter());
        counter.Record(decision, success, budgetRejected);
    }

    private void AppendRouteAudit(GatewayRouteAuditEntry entry)
    {
        _routeAudits.Enqueue(entry);
        while (_routeAudits.Count > MaxRouteAudits && _routeAudits.TryDequeue(out _))
        {
        }
    }

    private static int ToInt(long value) => value > int.MaxValue ? int.MaxValue : (int)value;

    private sealed class ProviderSelectionCounter
    {
        private int _total;
        private int _successful;
        private int _failed;
        private int _budgetRejected;
        private int _fallback;
        private long _lastSelectedAtUnixMs;

        public void Record(ProviderRouteDecision decision, bool success, bool budgetRejected)
        {
            Interlocked.Increment(ref _total);
            Interlocked.Exchange(ref _lastSelectedAtUnixMs, DateTimeOffset.UtcNow.ToUnixTimeMilliseconds());
            if (decision.FallbackUsed)
            {
                Interlocked.Increment(ref _fallback);
            }

            if (success)
            {
                Interlocked.Increment(ref _successful);
                return;
            }

            Interlocked.Increment(ref _failed);
            if (budgetRejected)
            {
                Interlocked.Increment(ref _budgetRejected);
            }
        }

        public ProviderSelectionStatus ToStatus(AiProvider provider)
        {
            var lastSelectedAtUnixMs = Interlocked.Read(ref _lastSelectedAtUnixMs);
            var lastSelectedAtUtc = lastSelectedAtUnixMs <= 0
                ? (DateTimeOffset?)null
                : DateTimeOffset.FromUnixTimeMilliseconds(lastSelectedAtUnixMs);
            return new ProviderSelectionStatus(
                Provider: provider,
                TotalSelections: Volatile.Read(ref _total),
                SuccessfulSelections: Volatile.Read(ref _successful),
                FailedSelections: Volatile.Read(ref _failed),
                BudgetRejectedSelections: Volatile.Read(ref _budgetRejected),
                FallbackSelections: Volatile.Read(ref _fallback),
                LastSelectedAtUtc: lastSelectedAtUtc);
        }
    }
}
