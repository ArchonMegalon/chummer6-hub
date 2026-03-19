using System.ComponentModel.DataAnnotations;

namespace Chummer.Run.AI.Compatibility;

[Obsolete("Use Chummer.Run.Contracts.Gateway.SubmitObservationRequest.")]
internal sealed record SubmitObservationRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SessionId,
    [Required(AllowEmptyStrings = false), StringLength(64)] string Source,
    [Required(AllowEmptyStrings = false), StringLength(8000)] string Payload,
    DateTimeOffset ObservedAtUtc);

[Obsolete("Use Chummer.Run.Contracts.Gateway.SubmitObservationResponse.")]
internal sealed record SubmitObservationResponse(
    string ObservationId,
    string Status,
    DateTimeOffset AcceptedAtUtc);

[Obsolete("Use Chummer.Run.Contracts.Gateway.AiProvider.")]
internal enum AiProvider
{
    AiMagicx,
    OneMinAi,
    BrowserAct,
    ChatPlayground,
    PromptingSystems,
    MarkupGo,
    PeekShot
}

[Obsolete("Use Chummer.Run.Contracts.Gateway.PromptGroundingKind.")]
internal enum PromptGroundingKind
{
    None,
    RuntimeFacts,
    LoreRetrieval,
    PersonaMemory,
    SessionLedger
}

[Obsolete("Use Chummer.Run.Contracts.Gateway.ProviderRouteRequest.")]
internal sealed record ProviderRouteRequest(
    string Purpose,
    string Prompt,
    bool StructuredOutput,
    int MaxTokens,
    string? SessionId = null,
    string? PreferredProvider = null,
    double Temperature = 0.25,
    PromptLineage? PromptLineage = null,
    AiProvider? RequiredProvider = null);

[Obsolete("Use Chummer.Run.Contracts.Gateway.ProviderRouteDecision.")]
internal sealed record ProviderRouteDecision(
    AiProvider Provider,
    string Reason,
    bool FallbackUsed,
    string Tier,
    string SelectedModel,
    string ReasoningEffort,
    double EstimatedCostUsd,
    string Policy);

[Obsolete("Use Chummer.Run.Contracts.Gateway.GatewayExecutionResult.")]
internal sealed record GatewayExecutionResult(
    string RequestId,
    AiProvider Provider,
    string Output,
    string? SourceTrace,
    DateTimeOffset ExecutedAtUtc);

[Obsolete("Use Chummer.Run.Contracts.Gateway.GatewayInvocation.")]
internal sealed record GatewayInvocation(
    ProviderRouteRequest Request,
    ProviderRouteDecision Decision,
    string? Output,
    bool Success,
    string? Error,
    PromptRenderResult? Prompt = null);

[Obsolete("Use Chummer.Run.Contracts.Gateway.ProviderDescriptor.")]
internal sealed record ProviderDescriptor(
    string Id,
    string DisplayName,
    bool Enabled,
    bool PrimaryForTooling);

[Obsolete("Use Chummer.Run.Contracts.Gateway.PromptTemplate.")]
internal sealed record PromptTemplate(
    string Name,
    string Version,
    string Persona,
    string Content,
    string? PersonaNote = null,
    string Feature = "general",
    bool DraftOnly = true,
    PromptGroundingKind Grounding = PromptGroundingKind.None,
    IReadOnlyList<string>? Tags = null);

[Obsolete("Use Chummer.Run.Contracts.Gateway.PromptGroundingContext.")]
internal sealed record PromptGroundingContext(
    string? RuntimeFingerprint = null,
    IReadOnlyList<string>? PackProfileIds = null,
    IReadOnlyList<string>? EvidencePointers = null,
    string? RetrievalScope = null,
    string? SceneId = null);

[Obsolete("Use Chummer.Run.Contracts.Gateway.PromptLineage.")]
internal sealed record PromptLineage(
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

[Obsolete("Use Chummer.Run.Contracts.Gateway.PromptRenderRequest.")]
internal sealed record PromptRenderRequest(
    string TemplateName,
    string Inputs,
    string Version = "latest",
    PromptGroundingContext? GroundingContext = null,
    string? EvaluationLabel = null);

[Obsolete("Use Chummer.Run.Contracts.Gateway.PromptRenderResult.")]
internal sealed record PromptRenderResult(
    string TemplateName,
    string Version,
    string RenderedText,
    PromptLineage Lineage,
    bool MissingInputs,
    IReadOnlyList<string> UnresolvedPlaceholders);

[Obsolete("Use Chummer.Run.Contracts.Gateway.ConversationAppendRequest.")]
internal sealed record ConversationAppendRequest(
    string Role,
    string Content);

[Obsolete("Use Chummer.Run.Contracts.Gateway.ConversationTurn.")]
internal sealed record ConversationTurn(
    string Role,
    string Content,
    DateTimeOffset AtUtc);

[Obsolete("Use Chummer.Run.Contracts.Gateway.ConversationAppendResult.")]
internal sealed record ConversationAppendResult(
    string SessionId,
    int TotalTurns);

[Obsolete("Use Chummer.Run.Contracts.Gateway.BudgetLimit.")]
internal sealed record BudgetLimit(
    int TokensPerMinute,
    int RequestsPerMinute,
    int ConcurrentCap);

[Obsolete("Use Chummer.Run.Contracts.Gateway.BudgetCheckRequest.")]
internal sealed record BudgetCheckRequest(
    string SessionId,
    int EstimatedTokens,
    AiProvider Provider);

[Obsolete("Use Chummer.Run.Contracts.Gateway.BudgetCheckResult.")]
internal sealed record BudgetCheckResult(
    bool Allowed,
    string? RejectedReason);

[Obsolete("Use Chummer.Run.Contracts.Gateway.EvaluationRequest.")]
internal sealed record EvaluationRequest(
    string RequestId,
    string Provider,
    string Prompt,
    string Response,
    int Rating,
    string? Notes,
    PromptLineage? PromptLineage = null,
    string? EvaluationSuiteId = null,
    string Evaluator = "human");

[Obsolete("Use Chummer.Run.Contracts.Gateway.EvaluationResult.")]
internal sealed record EvaluationResult(
    string RequestId,
    bool Accepted,
    IReadOnlyList<string> Flags,
    PromptLineage? PromptLineage = null,
    string? EvaluationSuiteId = null,
    string Evaluator = "human");

[Obsolete("Use Chummer.Run.Contracts.Gateway.PromptEvaluationCase.")]
internal sealed record PromptEvaluationCase(
    string CaseId,
    string Label,
    string TemplateName,
    string Inputs,
    string ExpectedSignals,
    string Version = "latest",
    PromptGroundingContext? GroundingContext = null);

[Obsolete("Use Chummer.Run.Contracts.Gateway.PromptEvaluationRunRequest.")]
internal sealed record PromptEvaluationRunRequest(
    string SuiteId,
    string TemplateName,
    string Version = "latest",
    string? PreferredProvider = null,
    bool StructuredOutput = true,
    int MaxTokens = 1200,
    IReadOnlyList<PromptEvaluationCase>? Cases = null);

[Obsolete("Use Chummer.Run.Contracts.Gateway.PromptEvaluationCaseResult.")]
internal sealed record PromptEvaluationCaseResult(
    string CaseId,
    string Label,
    bool Passed,
    IReadOnlyList<string> Flags,
    PromptRenderResult Prompt,
    ProviderRouteDecision Decision,
    IReadOnlyList<string> MissingSignals);

[Obsolete("Use Chummer.Run.Contracts.Gateway.PromptEvaluationRunResult.")]
internal sealed record PromptEvaluationRunResult(
    string RunId,
    string SuiteId,
    string TemplateName,
    string TemplateVersion,
    bool Passed,
    int TotalCases,
    int PassedCases,
    DateTimeOffset ExecutedAtUtc,
    IReadOnlyList<PromptEvaluationCaseResult> Cases);

[Obsolete("Use Chummer.Run.Contracts.Gateway.GatewayStatus.")]
internal sealed record GatewayStatus(
    bool Enabled,
    bool DryRunOnly,
    int ActiveConversations,
    IReadOnlyList<ProviderDescriptor> RegisteredProviders,
    IReadOnlyList<PromptTemplate> PromptTemplates,
    IReadOnlyList<GatewayBudgetStatus> BudgetStatuses,
    GatewaySelectionVisibility SelectionVisibility,
    DateTimeOffset UtcNow);

[Obsolete("Use Chummer.Run.Contracts.Gateway.GatewayBudgetStatus.")]
internal sealed record GatewayBudgetStatus(
    string RouteType,
    string SessionId,
    int MonthlyAllowance,
    int MonthlyUsed,
    int BurstAllowancePerMinute,
    int BurstUsedThisMinute,
    bool OverMonthly,
    bool OverBurst);

[Obsolete("Use Chummer.Run.Contracts.Gateway.ProviderSelectionStatus.")]
internal sealed record ProviderSelectionStatus(
    AiProvider Provider,
    int TotalSelections,
    int SuccessfulSelections,
    int FailedSelections,
    int BudgetRejectedSelections,
    int FallbackSelections,
    DateTimeOffset? LastSelectedAtUtc);

[Obsolete("Use Chummer.Run.Contracts.Gateway.GatewayRouteAuditEntry.")]
internal sealed record GatewayRouteAuditEntry(
    string AuditId,
    DateTimeOffset OccurredAtUtc,
    string? SessionId,
    string Purpose,
    ProviderRouteDecision Decision,
    bool BudgetAllowed,
    string BudgetOutcome,
    bool Success,
    string? Error);

[Obsolete("Use Chummer.Run.Contracts.Gateway.GatewaySelectionVisibility.")]
internal sealed record GatewaySelectionVisibility(
    int TotalRoutes,
    int TotalFallbackRoutes,
    IReadOnlyList<ProviderSelectionStatus> Providers,
    IReadOnlyList<GatewayRouteAuditEntry> RecentAudits);

[Obsolete("Use Chummer.Run.Contracts.Gateway.GatewayRoutePreview.")]
internal sealed record GatewayRoutePreview(
    ProviderRouteRequest Request,
    ProviderRouteDecision Decision,
    bool EstimatedAllowed,
    string Reason);

[Obsolete("Use Chummer.Run.Contracts.Gateway.GatewayConversationRequest.")]
internal sealed record GatewayConversationRequest(
    string SessionId,
    string RouteType,
    string Prompt,
    string? RuntimeFingerprint = null,
    bool Structured = false,
    int MaxTokens = 600);

[Obsolete("Use Chummer.Run.Contracts.Gateway.GatewayConversationResult.")]
internal sealed record GatewayConversationResult(
    string SessionId,
    string RouteType,
    string RouteDecisionProvider,
    string Response,
    bool Delivered,
    IReadOnlyList<string>? Evidence = null);
