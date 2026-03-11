using Chummer.Run.AI.Services.Lore;
using Chummer.Run.AI.Services.Session;
using System.Text.Json;

namespace Chummer.Run.AI.Services.Gateway;

public interface ISkillToolAdapter
{
    string Adapter { get; }
    SkillApprovalClass MinimumApprovalClass { get; }
    string Description { get; }
    Task<GovernedSkillToolResult> ExecuteAsync(GovernedSkillToolCall call, CancellationToken cancellationToken);
}

public interface IGovernedSkillRuntimeService
{
    Task<GovernedSkillExecutionResult> ExecuteAsync(GovernedSkillExecutionRequest request, CancellationToken cancellationToken);
    IReadOnlyList<GovernedSkillAdapterDescriptor> ListAdapters();
}

public sealed class GovernedSkillRuntimeService : IGovernedSkillRuntimeService
{
    private readonly IAiGatewayService _gateway;
    private readonly IReadOnlyDictionary<string, ISkillToolAdapter> _adapters;

    public GovernedSkillRuntimeService(IAiGatewayService gateway, IEnumerable<ISkillToolAdapter> adapters)
    {
        _gateway = gateway;
        _adapters = adapters.ToDictionary(item => item.Adapter, StringComparer.OrdinalIgnoreCase);
    }

    public IReadOnlyList<GovernedSkillAdapterDescriptor> ListAdapters()
    {
        return _adapters.Values
            .OrderBy(item => item.Adapter, StringComparer.OrdinalIgnoreCase)
            .Select(item => new GovernedSkillAdapterDescriptor(item.Adapter, item.MinimumApprovalClass, item.Description))
            .ToArray();
    }

    public async Task<GovernedSkillExecutionResult> ExecuteAsync(GovernedSkillExecutionRequest request, CancellationToken cancellationToken)
    {
        var runId = $"skill_{Guid.NewGuid():N}";
        var executedAtUtc = DateTimeOffset.UtcNow;
        var governanceFlags = new List<string>();
        var toolResults = new List<GovernedSkillToolResult>();
        var approvalState = NormalizeApprovalState(request.ApprovalState);

        if (!IsApprovalSatisfied(request.ApprovalClass, approvalState))
        {
            governanceFlags.Add("approval-required");
            return new GovernedSkillExecutionResult(
                RunId: runId,
                SkillId: request.SkillId,
                SessionId: request.SessionId,
                ApprovalClass: request.ApprovalClass,
                GovernanceOutcome: "approval-required",
                GatewayInvoked: false,
                GovernanceFlags: governanceFlags,
                ToolResults: toolResults,
                Invocation: null,
                ExecutedAtUtc: executedAtUtc);
        }

        foreach (var toolCall in request.ToolCalls ?? Array.Empty<GovernedSkillToolCall>())
        {
            if (!_adapters.TryGetValue(toolCall.Adapter, out var adapter))
            {
                governanceFlags.Add($"unknown-tool:{toolCall.Adapter}");
                toolResults.Add(new GovernedSkillToolResult(toolCall.Adapter, false, "unknown-tool", null, "Adapter is not registered."));
                continue;
            }

            if (request.ApprovalClass < adapter.MinimumApprovalClass)
            {
                governanceFlags.Add($"tool-approval-class-too-low:{adapter.Adapter}");
                toolResults.Add(new GovernedSkillToolResult(adapter.Adapter, false, "approval-class-too-low", null, $"Requires {adapter.MinimumApprovalClass}."));
                continue;
            }

            toolResults.Add(await adapter.ExecuteAsync(toolCall, cancellationToken));
        }

        var prompt = BuildGatewayPrompt(request, toolResults);
        var invocation = await _gateway.ExecuteRouteAsync(
            new ProviderRouteRequest(
                Purpose: request.Purpose,
                Prompt: prompt,
                StructuredOutput: request.StructuredOutput,
                MaxTokens: request.MaxTokens,
                SessionId: request.SessionId,
                PreferredProvider: request.PreferredProvider,
                Temperature: request.Temperature),
            cancellationToken);

        governanceFlags.Add("gateway-governed");
        if (toolResults.Any(item => item.Executed))
        {
            governanceFlags.Add("tool-adapters-executed");
        }

        return new GovernedSkillExecutionResult(
            RunId: runId,
            SkillId: request.SkillId,
            SessionId: request.SessionId,
            ApprovalClass: request.ApprovalClass,
            GovernanceOutcome: invocation.Success ? "executed" : "gateway-failed",
            GatewayInvoked: true,
            GovernanceFlags: governanceFlags,
            ToolResults: toolResults,
            Invocation: invocation,
            ExecutedAtUtc: executedAtUtc);
    }

    private static string BuildGatewayPrompt(GovernedSkillExecutionRequest request, IReadOnlyList<GovernedSkillToolResult> toolResults)
    {
        if (toolResults.Count == 0)
        {
            return request.Prompt;
        }

        var toolSummary = JsonSerializer.Serialize(toolResults);
        return $"{request.Prompt}\n\nTool Adapter Results (JSON):\n{toolSummary}";
    }

    private static string NormalizeApprovalState(string approvalState)
    {
        return string.IsNullOrWhiteSpace(approvalState) ? "draft" : approvalState.Trim().ToLowerInvariant();
    }

    private static bool IsApprovalSatisfied(SkillApprovalClass approvalClass, string approvalState)
    {
        return approvalClass switch
        {
            SkillApprovalClass.Advisory => true,
            SkillApprovalClass.Operational => approvalState is "approved" or "operator-approved",
            SkillApprovalClass.CanonMutation => approvalState is "approved" or "canon-approved",
            _ => false
        };
    }
}

public sealed class SessionProjectionSkillToolAdapter : ISkillToolAdapter
{
    private readonly ISessionLedgerService _ledger;

    public SessionProjectionSkillToolAdapter(ISessionLedgerService ledger)
    {
        _ledger = ledger;
    }

    public string Adapter => "session.projection";
    public SkillApprovalClass MinimumApprovalClass => SkillApprovalClass.Advisory;
    public string Description => "Reads a session/scene projection summary from the session ledger.";

    public Task<GovernedSkillToolResult> ExecuteAsync(GovernedSkillToolCall call, CancellationToken cancellationToken)
    {
        try
        {
            var request = JsonSerializer.Deserialize<SessionProjectionToolInput>(call.Input, JsonOptions())
                          ?? throw new InvalidOperationException("Tool input is empty.");
            var projection = _ledger.GetProjection(request.SessionId, request.SceneId);
            var output = JsonSerializer.Serialize(new
            {
                projection.SessionId,
                projection.SceneId,
                projection.Version,
                projection.ProjectionFingerprint,
                EventCount = projection.Events.Count
            });
            return Task.FromResult(new GovernedSkillToolResult(Adapter, true, "executed", output));
        }
        catch (Exception exception)
        {
            return Task.FromResult(new GovernedSkillToolResult(Adapter, false, "error", null, exception.Message));
        }
    }

    private sealed record SessionProjectionToolInput(string SessionId, string SceneId);

    private static JsonSerializerOptions JsonOptions()
    {
        return new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        };
    }
}

public sealed class LoreSearchSkillToolAdapter : ISkillToolAdapter
{
    private readonly ILoreService _lore;

    public LoreSearchSkillToolAdapter(ILoreService lore)
    {
        _lore = lore;
    }

    public string Adapter => "lore.search";
    public SkillApprovalClass MinimumApprovalClass => SkillApprovalClass.Advisory;
    public string Description => "Runs approved-only lore retrieval for skill grounding.";

    public Task<GovernedSkillToolResult> ExecuteAsync(GovernedSkillToolCall call, CancellationToken cancellationToken)
    {
        try
        {
            var request = JsonSerializer.Deserialize<LoreSearchToolInput>(call.Input, JsonOptions())
                          ?? throw new InvalidOperationException("Tool input is empty.");
            var result = _lore.Search(new Chummer.Run.Contracts.AI.LoreSearchRequest(
                District: request.Scope,
                TopicTag: request.Query,
                CampaignScope: null,
                MaxItems: request.Limit));
            var output = JsonSerializer.Serialize(result);
            return Task.FromResult(new GovernedSkillToolResult(Adapter, true, "executed", output));
        }
        catch (Exception exception)
        {
            return Task.FromResult(new GovernedSkillToolResult(Adapter, false, "error", null, exception.Message));
        }
    }

    private sealed record LoreSearchToolInput(string Query, string? Scope = null, int Limit = 5);

    private static JsonSerializerOptions JsonOptions()
    {
        return new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true
        };
    }
}
