using System.ComponentModel.DataAnnotations;

namespace Chummer.Play.Contracts.Gateway;

public sealed record SubmitObservationRequest(
    [property: Required(AllowEmptyStrings = false), StringLength(128)] string SessionId,
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string Source,
    [property: Required(AllowEmptyStrings = false), StringLength(8000)] string Payload,
    DateTimeOffset ObservedAtUtc);

public sealed record SubmitObservationResponse(
    string ObservationId,
    string Status,
    DateTimeOffset AcceptedAtUtc);

public enum AiProvider
{
    AiMagicx,
    OneMinAi,
    BrowserAct,
    ChatPlayground,
    PromptingSystems,
    MarkupGo,
    PeekShot
}

public enum PromptGroundingKind
{
    None,
    RuntimeFacts,
    LoreRetrieval,
    PersonaMemory,
    SessionLedger
}

public sealed record ProviderRouteRequest(
    string Purpose,
    string Prompt,
    bool StructuredOutput,
    int MaxTokens,
    string? SessionId = null,
    string? PreferredProvider = null,
    double Temperature = 0.25,
    PromptLineage? PromptLineage = null,
    AiProvider? RequiredProvider = null);

public sealed record ProviderRouteDecision(
    AiProvider Provider,
    string Reason,
    bool FallbackUsed,
    string Tier,
    string SelectedModel,
    string ReasoningEffort,
    double EstimatedCostUsd,
    string Policy);

public sealed record GatewayExecutionResult(
    string RequestId,
    AiProvider Provider,
    string Output,
    string? SourceTrace,
    DateTimeOffset ExecutedAtUtc);

public sealed record GatewayInvocation(
    ProviderRouteRequest Request,
    ProviderRouteDecision Decision,
    string? Output,
    bool Success,
    string? Error,
    PromptRenderResult? Prompt = null);

public sealed record ProviderDescriptor(
    string Id,
    string DisplayName,
    bool Enabled,
    bool PrimaryForTooling);

public sealed record PromptTemplate(
    string Name,
    string Version,
    string Persona,
    string Content,
    string? PersonaNote = null,
    string Feature = "general",
    bool DraftOnly = true,
    PromptGroundingKind Grounding = PromptGroundingKind.None,
    IReadOnlyList<string>? Tags = null);

public sealed record PromptGroundingContext(
    string? RuntimeFingerprint = null,
    IReadOnlyList<string>? PackProfileIds = null,
    IReadOnlyList<string>? EvidencePointers = null,
    string? RetrievalScope = null,
    string? SceneId = null);

public sealed record PromptLineage(
    string TemplateName,
    string TemplateVersion,
    string Feature,
    string Persona,
    bool DraftOnly,
    PromptGroundingKind Grounding,
    PromptGroundingContext? GroundingContext,
    string PromptHash,
    DateTimeOffset RenderedAtUtc,
    IReadOnlyList<string> Tags);

public sealed record PromptRenderRequest(
    string TemplateName,
    string Inputs,
    string Version = "latest",
    PromptGroundingContext? GroundingContext = null,
    string? EvaluationLabel = null);

public sealed record PromptRenderResult(
    string TemplateName,
    string Version,
    string RenderedText,
    PromptLineage Lineage,
    bool MissingInputs,
    IReadOnlyList<string> UnresolvedPlaceholders);

public sealed record ConversationAppendRequest(
    string Role,
    string Content);

public sealed record ConversationTurn(
    string Role,
    string Content,
    DateTimeOffset AtUtc);

public sealed record ConversationAppendResult(
    string SessionId,
    int TotalTurns);

public sealed record BudgetLimit(
    int TokensPerMinute,
    int RequestsPerMinute,
    int ConcurrentCap);

public sealed record BudgetCheckRequest(
    string SessionId,
    int EstimatedTokens,
    AiProvider Provider);

public sealed record BudgetCheckResult(
    bool Allowed,
    string? RejectedReason);

public sealed record EvaluationRequest(
    string RequestId,
    string Provider,
    string Prompt,
    string Response,
    int Rating,
    string? Notes,
    PromptLineage? PromptLineage = null,
    string? EvaluationSuiteId = null,
    string Evaluator = "human");

public sealed record EvaluationResult(
    string RequestId,
    bool Accepted,
    IReadOnlyList<string> Flags,
    PromptLineage? PromptLineage = null,
    string? EvaluationSuiteId = null,
    string Evaluator = "human");

public sealed record PromptEvaluationCase(
    string CaseId,
    string Label,
    string TemplateName,
    string Inputs,
    string ExpectedSignals,
    string Version = "latest",
    PromptGroundingContext? GroundingContext = null);

public sealed record PromptEvaluationRunRequest(
    string SuiteId,
    string TemplateName,
    string Version = "latest",
    string? PreferredProvider = null,
    bool StructuredOutput = true,
    int MaxTokens = 1200,
    IReadOnlyList<PromptEvaluationCase>? Cases = null);

public sealed record PromptEvaluationCaseResult(
    string CaseId,
    string Label,
    bool Passed,
    IReadOnlyList<string> Flags,
    PromptRenderResult Prompt,
    ProviderRouteDecision Decision,
    IReadOnlyList<string> MissingSignals);

public sealed record PromptEvaluationRunResult(
    string RunId,
    string SuiteId,
    string TemplateName,
    string TemplateVersion,
    bool Passed,
    int TotalCases,
    int PassedCases,
    DateTimeOffset ExecutedAtUtc,
    IReadOnlyList<PromptEvaluationCaseResult> Cases);

public sealed record GatewayStatus(
    bool Enabled,
    bool DryRunOnly,
    int ActiveConversations,
    IReadOnlyList<ProviderDescriptor> RegisteredProviders,
    IReadOnlyList<PromptTemplate> PromptTemplates,
    IReadOnlyList<GatewayBudgetStatus> BudgetStatuses,
    GatewaySelectionVisibility SelectionVisibility,
    DateTimeOffset UtcNow);

public sealed record GatewayBudgetStatus(
    string RouteType,
    string SessionId,
    int MonthlyAllowance,
    int MonthlyUsed,
    int BurstAllowancePerMinute,
    int BurstUsedThisMinute,
    bool OverMonthly,
    bool OverBurst);

public sealed record ProviderSelectionStatus(
    AiProvider Provider,
    int TotalSelections,
    int SuccessfulSelections,
    int FailedSelections,
    int BudgetRejectedSelections,
    int FallbackSelections,
    DateTimeOffset? LastSelectedAtUtc);

public sealed record GatewayRouteAuditEntry(
    string AuditId,
    DateTimeOffset OccurredAtUtc,
    string? SessionId,
    string Purpose,
    ProviderRouteDecision Decision,
    bool BudgetAllowed,
    string BudgetOutcome,
    bool Success,
    string? Error);

public sealed record GatewaySelectionVisibility(
    int TotalRoutes,
    int TotalFallbackRoutes,
    IReadOnlyList<ProviderSelectionStatus> Providers,
    IReadOnlyList<GatewayRouteAuditEntry> RecentAudits);

public sealed record GatewayRoutePreview(
    ProviderRouteRequest Request,
    ProviderRouteDecision Decision,
    bool EstimatedAllowed,
    string Reason);

public sealed record GatewayConversationRequest(
    string SessionId,
    string RouteType,
    string Prompt,
    string? RuntimeFingerprint = null,
    bool Structured = false,
    int MaxTokens = 600);

public sealed record GatewayConversationResult(
    string SessionId,
    string RouteType,
    string RouteDecisionProvider,
    string Response,
    bool Delivered,
    IReadOnlyList<string>? Evidence = null);

public enum SkillApprovalClass
{
    Advisory,
    Operational,
    CanonMutation
}

public sealed record GovernedSkillToolCall(
    string Adapter,
    string Input);

public sealed record GovernedSkillToolResult(
    string Adapter,
    bool Executed,
    string Outcome,
    string? Output,
    string? Error = null);

public sealed record GovernedSkillAdapterDescriptor(
    string Adapter,
    SkillApprovalClass MinimumApprovalClass,
    string Description);

public sealed record GovernedSkillExecutionRequest(
    string SkillId,
    string SessionId,
    string Purpose,
    string Prompt,
    SkillApprovalClass ApprovalClass,
    string RequestedBy,
    string ApprovalState = "draft",
    IReadOnlyList<GovernedSkillToolCall>? ToolCalls = null,
    bool StructuredOutput = true,
    int MaxTokens = 900,
    string? PreferredProvider = null,
    double Temperature = 0.2);

public sealed record GovernedSkillExecutionResult(
    string RunId,
    string SkillId,
    string SessionId,
    SkillApprovalClass ApprovalClass,
    string GovernanceOutcome,
    bool GatewayInvoked,
    IReadOnlyList<string> GovernanceFlags,
    IReadOnlyList<GovernedSkillToolResult> ToolResults,
    GatewayInvocation? Invocation,
    DateTimeOffset ExecutedAtUtc);
