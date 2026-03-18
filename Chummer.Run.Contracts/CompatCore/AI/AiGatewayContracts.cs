using Chummer.Contracts.Owners;

namespace Chummer.Contracts.AI;

public static class AiApiOperations
{
    public const string GetGatewayStatus = "get-gateway-status";
    public const string ListProviders = "list-providers";
    public const string ListTools = "list-tools";
    public const string ListRetrievalCorpora = "list-retrieval-corpora";
    public const string ListRoutePolicies = "list-route-policies";
    public const string ListRouteBudgets = "list-route-budgets";
    public const string ListConversations = "list-conversations";
    public const string PreviewTurn = "preview-turn";
    public const string GetConversation = "get-conversation";
    public const string SendChatTurn = "send-chat-turn";
    public const string SendCoachTurn = "send-coach-turn";
    public const string SendBuildTurn = "send-build-turn";
    public const string SendDocsTurn = "send-docs-turn";
    public const string SendRecapTurn = "send-recap-turn";
}

public static class AiRouteTypes
{
    public const string Chat = "chat";
    public const string Coach = "coach";
    public const string Build = "build";
    public const string Docs = "docs";
    public const string Recap = "recap";
}

public static class AiRouteClassIds
{
    public const string CheapChat = "cheap-chat";
    public const string GroundedRulesChat = "grounded-rules-chat";
    public const string BuildSimulation = "build-simulation";
    public const string RecapGeneration = "recap-generation";
}

public static class AiPersonaIds
{
    public const string DeckerContact = "decker-contact";
}

public static class AiProviderIds
{
    public const string AiMagicx = "ai-magicx";
    public const string OneMinAi = "1minai";
}

public static class AiProviderAdapterKinds
{
    public const string None = "none";
    public const string Stub = "stub";
    public const string RemoteHttp = "remote-http";
}

public static class AiProviderCredentialTiers
{
    public const string None = "none";
    public const string Primary = "primary";
    public const string Fallback = "fallback";
}

public static class AiConversationRoles
{
    public const string System = "system";
    public const string User = "user";
    public const string Assistant = "assistant";
    public const string Tool = "tool";
}

public static class AiBudgetUnits
{
    public const string ChummerAiUnits = "chummer-ai-units";
}

public static class AiBudgetLimitKinds
{
    public const string MonthlyAllowance = "monthly-allowance";
    public const string BurstLimitPerMinute = "burst-limit-per-minute";
}

public static class AiToolIds
{
    public const string GetRuntimeSummary = "get_runtime_summary";
    public const string GetCharacterDigest = "get_character_digest";
    public const string ExplainValue = "explain_value";
    public const string SimulateKarmaSpend = "simulate_karma_spend";
    public const string SimulateNuyenSpend = "simulate_nuyen_spend";
    public const string SearchBuildIdeas = "search_build_ideas";
    public const string SearchHubProjects = "search_hub_projects";
    public const string GetSessionDigest = "get_session_digest";
    public const string DraftHistoryEntries = "draft_history_entries";
    public const string CreatePortraitPrompt = "create_portrait_prompt";
    public const string QueueMediaJob = "queue_media_job";
    public const string CreateApplyPreview = "create_apply_preview";

    // Compatibility aliases while older tests and call sites converge on the v1.1 tool vocabulary.
    public const string GetCharacterSummary = GetCharacterDigest;
    public const string ExplainDerivedValue = ExplainValue;
}

public static class AiSuggestedActionIds
{
    public const string OpenRuntimeInspector = "open_runtime_inspector";
    public const string PreviewKarmaSpend = "preview_karma_spend";
    public const string PreviewNuyenSpend = "preview_nuyen_spend";
    public const string PreviewApplyPlan = "preview_apply_plan";
    public const string BrowseBuildIdeas = "browse_build_ideas";
}

public static class AiRetrievalCorpusIds
{
    public const string Runtime = "runtime";
    public const string Private = "private";
    public const string Community = "community";
}

public static class AiGroundingSectionIds
{
    public const string Runtime = "runtime";
    public const string Character = "character";
    public const string Constraints = "constraints";
    public const string RetrievedItems = "retrieved_items";
    public const string AllowedTools = "allowed_tools";
}

public static class AiCitationKinds
{
    public const string Runtime = "runtime";
    public const string Character = "character";
    public const string RetrievedItem = "retrieved-item";
    public const string Corpus = "corpus";
}

public static class AiToolInvocationStatuses
{
    public const string Available = "available";
    public const string Prepared = "prepared";
    public const string Deferred = "deferred";
}

public static class AiCacheStatuses
{
    public const string Miss = "miss";
    public const string Hit = "hit";
}

public static class AiConfidenceLevels
{
    public const string Scaffolded = "scaffolded";
    public const string Grounded = "grounded";
    public const string Limited = "limited";
}

public static class AiRiskSeverities
{
    public const string Note = "note";
    public const string Warning = "warning";
}

public static class AiActionDraftModes
{
    public const string PreviewOnly = "preview-only";
    public const string ApprovalRequired = "approval-required";
}

public sealed record AiProviderCredentialCounts(
    int PrimaryCredentialCount = 0,
    int FallbackCredentialCount = 0)
{
    public bool IsConfigured => PrimaryCredentialCount > 0 || FallbackCredentialCount > 0;
}

public sealed record AiProviderDescriptor(
    string ProviderId,
    string DisplayName,
    bool SupportsToolCalling,
    bool SupportsStreaming,
    bool SupportsAttachments,
    bool SupportsConversationMemory,
    IReadOnlyList<string> AllowedRouteTypes,
    bool SessionSafe = false,
    string AdapterKind = AiProviderAdapterKinds.None,
    bool LiveExecutionEnabled = false,
    bool AdapterRegistered = false,
    bool IsConfigured = false,
    int PrimaryCredentialCount = 0,
    int FallbackCredentialCount = 0,
    bool TransportBaseUrlConfigured = false,
    bool TransportModelConfigured = false,
    bool TransportMetadataConfigured = false);

public static class AiProviderCircuitStates
{
    public const string Closed = "closed";
    public const string Degraded = "degraded";
    public const string Open = "open";
}

public sealed record AiProviderHealthSnapshot(
    string ProviderId,
    int ConsecutiveFailureCount = 0,
    DateTimeOffset? LastSuccessAtUtc = null,
    DateTimeOffset? LastFailureAtUtc = null,
    string? LastFailureMessage = null,
    string? LastRouteType = null,
    string? LastCredentialTier = null,
    int? LastCredentialSlotIndex = null)
{
    public string CircuitState => ConsecutiveFailureCount >= 3
        ? AiProviderCircuitStates.Open
        : ConsecutiveFailureCount > 0
            ? AiProviderCircuitStates.Degraded
            : AiProviderCircuitStates.Closed;
}

public sealed record AiProviderHealthProjection(
    string ProviderId,
    string DisplayName,
    string AdapterKind,
    bool AdapterRegistered,
    bool LiveExecutionEnabled,
    IReadOnlyList<string> AllowedRouteTypes,
    string CircuitState,
    int ConsecutiveFailureCount = 0,
    DateTimeOffset? LastSuccessAtUtc = null,
    DateTimeOffset? LastFailureAtUtc = null,
    string? LastFailureMessage = null,
    string? LastRouteType = null,
    string? LastCredentialTier = null,
    int? LastCredentialSlotIndex = null,
    bool IsConfigured = false,
    int PrimaryCredentialCount = 0,
    int FallbackCredentialCount = 0,
    bool TransportBaseUrlConfigured = false,
    bool TransportModelConfigured = false,
    bool TransportMetadataConfigured = false,
    bool IsRoutable = true);

public sealed record AiProviderExecutionPolicy(
    string ProviderId,
    string DisplayName,
    bool SupportsToolCalling,
    bool SupportsStreaming,
    bool SupportsAttachments,
    bool SupportsConversationMemory,
    IReadOnlyList<string> AllowedRouteTypes,
    bool SessionSafe = false);

public sealed record AiToolDescriptor(
    string ToolId,
    string Title,
    string Description,
    bool RequiresRuntimeFingerprint = false,
    bool Mutating = false);

public sealed record AiPersonaDescriptor(
    string PersonaId,
    string DisplayName,
    string Summary,
    bool EvidenceFirst = true,
    int MinFlavorPercent = 5,
    int MaxFlavorPercent = 15);

public sealed record AiRoutePolicyDescriptor(
    string RouteType,
    string PrimaryProviderId,
    IReadOnlyList<string> FallbackProviderIds,
    IReadOnlyList<string> RetrievalCorpusIds,
    IReadOnlyList<AiToolDescriptor> AllowedTools,
    bool ToolingEnabled = false,
    bool StreamingPreferred = false,
    bool CacheByRuntimeFingerprint = true,
    string RouteClassId = AiRouteClassIds.CheapChat,
    string PersonaId = AiPersonaIds.DeckerContact);

public sealed record AiRouteBudgetPolicyDescriptor(
    string RouteType,
    string BudgetUnit,
    int MonthlyAllowance,
    int BurstLimitPerMinute,
    string Notes);

public sealed record AiRouteBudgetStatusProjection(
    string RouteType,
    string BudgetUnit,
    int MonthlyAllowance,
    int MonthlyConsumed,
    int MonthlyRemaining,
    int BurstLimitPerMinute,
    int CurrentBurstConsumed,
    int BurstRemaining,
    bool IsLimited = true,
    string? Notes = null);

public sealed record AiRetrievalCorpusDescriptor(
    string CorpusId,
    string Title,
    string Scope,
    bool StructuredFirst = true);

public sealed record AiBudgetSnapshot(
    string BudgetUnit,
    int MonthlyAllowance,
    int MonthlyConsumed,
    int BurstLimitPerMinute,
    int CurrentBurstConsumed = 0,
    bool IsLimited = true);

public sealed record AiRetrievedItem(
    string CorpusId,
    string ItemId,
    string Title,
    string Summary,
    string? Provenance = null,
    string? RulesetId = null);

public sealed record AiGroundingBundle(
    string RouteType,
    string? RuntimeFingerprint,
    string? CharacterId,
    string? ConversationId,
    IReadOnlyDictionary<string, string> RuntimeFacts,
    IReadOnlyDictionary<string, string> CharacterFacts,
    IReadOnlyList<string> Constraints,
    IReadOnlyList<AiRetrievedItem> RetrievedItems,
    IReadOnlyList<AiToolDescriptor> AllowedTools,
    AiGroundingCoverage? Coverage = null,
    string? WorkspaceId = null);

public sealed record AiGroundingCoverage(
    int ScorePercent,
    string Summary,
    IReadOnlyList<string> PresentSignals,
    IReadOnlyList<string> MissingSignals,
    IReadOnlyList<string> RetrievedCorpusIds);

public sealed record AiGroundingSection(
    string SectionId,
    string Title,
    IReadOnlyList<string> Lines,
    bool Structured = true);

public sealed record AiProviderRouteDecision(
    string RouteType,
    string ProviderId,
    string Reason,
    string BudgetUnit,
    bool ToolingEnabled = false,
    bool RetrievalEnabled = true,
    string CredentialTier = AiProviderCredentialTiers.None,
    int? CredentialSlotIndex = null);

public sealed record AiCitation(
    string Kind,
    string Title,
    string ReferenceId,
    string? Source = null);

public sealed record AiRecommendation(
    string RecommendationId,
    string Title,
    string Reason,
    string ExpectedEffect,
    bool RequiresPreview = true);

public sealed record AiEvidenceEntry(
    string Title,
    string Summary,
    string? ReferenceId = null,
    string? Source = null);

public sealed record AiRiskEntry(
    string Severity,
    string Title,
    string Summary);

public sealed record AiSourceReference(
    string Kind,
    string Title,
    string ReferenceId,
    string? Source = null);

public sealed record AiSuggestedAction(
    string ActionId,
    string Title,
    string Description,
    bool RequiresConfirmation = true,
    string? RuntimeFingerprint = null,
    string? CharacterId = null,
    string? WorkspaceId = null);

public sealed record AiActionDraft(
    string ActionId,
    string Title,
    string Description,
    string Mode = AiActionDraftModes.PreviewOnly,
    bool RequiresConfirmation = true,
    string? RuntimeFingerprint = null,
    string? CharacterId = null,
    string? WorkspaceId = null);

public sealed record AiStructuredAnswer(
    string Summary,
    IReadOnlyList<AiRecommendation> Recommendations,
    IReadOnlyList<AiEvidenceEntry> Evidence,
    IReadOnlyList<AiRiskEntry> Risks,
    string Confidence,
    string? RuntimeFingerprint,
    IReadOnlyList<AiSourceReference> Sources,
    IReadOnlyList<AiActionDraft> ActionDrafts);

public sealed record AiToolInvocation(
    string ToolId,
    string Status,
    string Summary,
    string? ReferenceId = null);

public sealed record AiConversationMessage(
    string MessageId,
    string Role,
    string Content,
    DateTimeOffset CreatedAtUtc,
    string? ProviderId = null);

public sealed record AiConversationTurnRecord(
    string TurnId,
    string RouteType,
    string ProviderId,
    DateTimeOffset CreatedAtUtc,
    string UserMessage,
    string AssistantAnswer,
    IReadOnlyList<AiToolInvocation> ToolInvocations,
    IReadOnlyList<AiCitation> Citations,
    AiStructuredAnswer? StructuredAnswer = null,
    string? RuntimeFingerprint = null,
    string? CharacterId = null,
    AiCacheMetadata? Cache = null,
    AiProviderRouteDecision? RouteDecision = null,
    AiGroundingCoverage? GroundingCoverage = null,
    string? WorkspaceId = null,
    IReadOnlyList<AiSuggestedAction>? SuggestedActions = null,
    string? FlavorLine = null,
    AiBudgetSnapshot? Budget = null);

public sealed record AiConversationSnapshot(
    string ConversationId,
    string RouteType,
    IReadOnlyList<AiConversationMessage> Messages,
    string? RuntimeFingerprint = null,
    string? CharacterId = null,
    IReadOnlyList<AiConversationTurnRecord>? Turns = null,
    string? WorkspaceId = null);

public sealed record AiConversationTurnRequest(
    string Message,
    string? ConversationId = null,
    string? RuntimeFingerprint = null,
    string? CharacterId = null,
    IReadOnlyList<string>? AttachmentIds = null,
    bool Stream = false,
    string? WorkspaceId = null);

public sealed record AiCacheMetadata(
    string Status,
    string CacheKey,
    DateTimeOffset CachedAtUtc,
    string? NormalizedPrompt = null,
    string? RuntimeFingerprint = null,
    string? CharacterId = null,
    string? WorkspaceId = null);

public sealed record AiResponseCacheLookup(
    string RouteType,
    string NormalizedPrompt,
    string? RuntimeFingerprint = null,
    string? CharacterId = null,
    string? AttachmentKey = null,
    string? WorkspaceId = null);

public sealed record AiCachedConversationTurn(
    string CacheKey,
    string RouteType,
    string NormalizedPrompt,
    string? RuntimeFingerprint,
    string? CharacterId,
    string? AttachmentKey,
    DateTimeOffset CachedAtUtc,
    AiConversationTurnResponse Response,
    string? WorkspaceId = null);

public sealed record AiConversationTurnResponse(
    string ConversationId,
    string RouteType,
    string ProviderId,
    string Answer,
    AiProviderRouteDecision RouteDecision,
    AiGroundingBundle Grounding,
    AiBudgetSnapshot Budget,
    IReadOnlyList<AiCitation> Citations,
    IReadOnlyList<AiSuggestedAction> SuggestedActions,
    IReadOnlyList<AiToolInvocation> ToolInvocations,
    string? FlavorLine = null,
    AiStructuredAnswer? StructuredAnswer = null,
    AiCacheMetadata? Cache = null);

public sealed record AiProviderTurnPlan(
    string ProviderId,
    string RouteType,
    string? ConversationId,
    string UserMessage,
    string SystemPrompt,
    bool Stream,
    IReadOnlyList<string> AttachmentIds,
    IReadOnlyList<string> RetrievalCorpusIds,
    IReadOnlyList<AiToolDescriptor> AllowedTools,
    IReadOnlyList<AiGroundingSection> GroundingSections,
    AiProviderRouteDecision RouteDecision,
    AiGroundingBundle Grounding,
    AiBudgetSnapshot Budget,
    string? WorkspaceId = null);

public sealed record AiConversationTurnPreview(
    string RouteType,
    AiProviderRouteDecision RouteDecision,
    AiGroundingBundle Grounding,
    AiBudgetSnapshot Budget,
    string SystemPrompt,
    AiProviderTurnPlan ProviderRequest);

public sealed record AiGatewayStatusProjection(
    string Status,
    IReadOnlyList<string> Routes,
    IReadOnlyList<AiProviderDescriptor> Providers,
    IReadOnlyList<AiToolDescriptor> Tools,
    IReadOnlyList<AiRoutePolicyDescriptor> RoutePolicies,
    IReadOnlyList<AiRouteBudgetPolicyDescriptor> RouteBudgets,
    IReadOnlyList<AiRetrievalCorpusDescriptor> RetrievalCorpora,
    AiBudgetSnapshot Budget,
    string PromptPolicy,
    bool SupportsStreaming = false,
    IReadOnlyList<AiPersonaDescriptor>? Personas = null,
    string? DefaultPersonaId = null,
    IReadOnlyList<AiRouteBudgetStatusProjection>? RouteBudgetStatuses = null);

public sealed record AiNotImplementedReceipt(
    string Error,
    string Operation,
    string Message,
    string? ConversationId = null,
    string? RouteType = null,
    string? OwnerId = null);

public sealed record AiQuotaExceededReceipt(
    string Error,
    string Operation,
    string Message,
    AiBudgetSnapshot Budget,
    int RequestedUnits,
    string LimitKind = AiBudgetLimitKinds.MonthlyAllowance,
    string? ConversationId = null,
    string? RouteType = null,
    string? OwnerId = null,
    int? RetryAfterSeconds = null);

public sealed record AiApiResult<T>(
    T? Payload = default,
    AiNotImplementedReceipt? NotImplemented = null,
    AiQuotaExceededReceipt? QuotaExceeded = null)
{
    public bool IsImplemented => NotImplemented is null;

    public bool IsSuccess => NotImplemented is null && QuotaExceeded is null;

    public static AiApiResult<T> Implemented(T payload)
        => new(payload, null, null);

    public static AiApiResult<T> FromNotImplemented(AiNotImplementedReceipt receipt)
        => new(default, receipt, null);

    public static AiApiResult<T> FromQuotaExceeded(AiQuotaExceededReceipt receipt)
        => new(default, null, receipt);
}

public static class AiGatewayDefaults
{
    public static AiGatewayStatusProjection CreateStatus(
        IReadOnlyDictionary<string, AiProviderCredentialCounts>? providerCredentials = null,
        IReadOnlyList<AiProviderDescriptor>? registeredProviders = null,
        IReadOnlyList<AiRouteBudgetPolicyDescriptor>? routeBudgets = null,
        int monthlyConsumed = 0,
        int currentBurstConsumed = 0,
        IReadOnlyList<AiRouteBudgetStatusProjection>? routeBudgetStatuses = null)
    {
        IReadOnlyList<AiToolDescriptor> toolCatalog = CreateToolCatalog();
        IReadOnlyList<AiRouteBudgetPolicyDescriptor> effectiveRouteBudgets = routeBudgets ?? CreateRouteBudgets();
        return new AiGatewayStatusProjection(
            Status: "scaffolded",
            Routes: [AiRouteTypes.Chat, AiRouteTypes.Coach, AiRouteTypes.Build, AiRouteTypes.Docs, AiRouteTypes.Recap],
            Providers: CreateProviderDescriptors(providerCredentials, registeredProviders),
            Tools: toolCatalog,
            RoutePolicies: CreateRoutePolicies(),
            RouteBudgets: effectiveRouteBudgets,
            RetrievalCorpora:
            [
                new AiRetrievalCorpusDescriptor(AiRetrievalCorpusIds.Runtime, "Authoritative Runtime", OwnerRepositoryScopeModes.Owned),
                new AiRetrievalCorpusDescriptor(AiRetrievalCorpusIds.Private, "Private Notes And Campaign Data", OwnerRepositoryScopeModes.Owned),
                new AiRetrievalCorpusDescriptor(AiRetrievalCorpusIds.Community, "Community Build Ideas", OwnerRepositoryScopeModes.PublicCatalog)
            ],
            Budget: CreateGatewayBudgetSnapshot(effectiveRouteBudgets, monthlyConsumed, currentBurstConsumed),
            PromptPolicy: "Structured Chummer data first, prose documents second.",
            SupportsStreaming: true,
            Personas: CreatePersonas(),
            DefaultPersonaId: AiPersonaIds.DeckerContact,
            RouteBudgetStatuses: routeBudgetStatuses);
    }

    public static IReadOnlyList<AiToolDescriptor> CreateToolCatalog()
        =>
        [
            new AiToolDescriptor(AiToolIds.GetRuntimeSummary, "Runtime Summary", "Load the active runtime summary, fingerprint, and compatibility context.", RequiresRuntimeFingerprint: true),
            new AiToolDescriptor(AiToolIds.GetCharacterDigest, "Character Digest", "Load the active character digest for grounded coaching and planning."),
            new AiToolDescriptor(AiToolIds.ExplainValue, "Explain Value", "Resolve Explain API details for a derived value or rules outcome.", RequiresRuntimeFingerprint: true),
            new AiToolDescriptor(AiToolIds.SimulateKarmaSpend, "Simulate Karma Spend", "Preview karma-spend outcomes without mutating state.", RequiresRuntimeFingerprint: true),
            new AiToolDescriptor(AiToolIds.SimulateNuyenSpend, "Simulate Nuyen Spend", "Preview nuyen-spend outcomes without mutating state.", RequiresRuntimeFingerprint: true),
            new AiToolDescriptor(AiToolIds.SearchBuildIdeas, "Search Build Ideas", "Search Chummer-grounded build ideas, templates, and advancement cards.", RequiresRuntimeFingerprint: true),
            new AiToolDescriptor(AiToolIds.SearchHubProjects, "Search Hub Projects", "Search RuleProfiles, RulePacks, BuildKits, NPC packs, and other Hub artifacts.", RequiresRuntimeFingerprint: true),
            new AiToolDescriptor(AiToolIds.GetSessionDigest, "Session Digest", "Load the active session digest, sync state, and transient tracker context.", RequiresRuntimeFingerprint: true),
            new AiToolDescriptor(AiToolIds.DraftHistoryEntries, "Draft History Entries", "Draft session-history, recap, and timeline entries without making canonical writes."),
            new AiToolDescriptor(AiToolIds.CreatePortraitPrompt, "Create Portrait Prompt", "Create a grounded portrait prompt from the current character and runtime context."),
            new AiToolDescriptor(AiToolIds.QueueMediaJob, "Queue Media Job", "Queue a portrait, dossier, or route-video job through the protected media pipeline.", Mutating: true),
            new AiToolDescriptor(AiToolIds.CreateApplyPreview, "Create Apply Preview", "Create a non-mutating preview for a follow-up character, runtime, or content action.", RequiresRuntimeFingerprint: true)
        ];

    public static IReadOnlyList<AiPersonaDescriptor> CreatePersonas()
        =>
        [
            new AiPersonaDescriptor(
                PersonaId: AiPersonaIds.DeckerContact,
                DisplayName: "Decker Contact",
                Summary: "Use one short in-world decker-contact line when helpful, then switch to evidence-first grounded guidance.")
        ];

    public static AiPersonaDescriptor ResolvePersona(string personaId)
        => CreatePersonas()
            .FirstOrDefault(persona => string.Equals(persona.PersonaId, personaId, StringComparison.Ordinal))
            ?? throw new InvalidOperationException($"Unknown AI persona id '{personaId}'.");

    public static AiToolDescriptor ResolveToolDescriptor(string toolId)
        => CreateToolCatalog()
            .FirstOrDefault(tool => string.Equals(tool.ToolId, toolId, StringComparison.Ordinal))
            ?? throw new InvalidOperationException($"Unknown AI tool id '{toolId}'.");

    public static IReadOnlyList<AiToolDescriptor> ResolveToolDescriptors(params string[] toolIds)
        => toolIds
            .Select(ResolveToolDescriptor)
            .ToArray();

    public static IReadOnlyList<AiRoutePolicyDescriptor> CreateRoutePolicies()
        =>
        [
            new AiRoutePolicyDescriptor(
                RouteType: AiRouteTypes.Chat,
                PrimaryProviderId: AiProviderIds.OneMinAi,
                FallbackProviderIds: [AiProviderIds.AiMagicx],
                RetrievalCorpusIds: [AiRetrievalCorpusIds.Runtime, AiRetrievalCorpusIds.Private],
                AllowedTools: [],
                ToolingEnabled: false,
                StreamingPreferred: true,
                RouteClassId: AiRouteClassIds.CheapChat,
                PersonaId: AiPersonaIds.DeckerContact),
            new AiRoutePolicyDescriptor(
                RouteType: AiRouteTypes.Coach,
                PrimaryProviderId: AiProviderIds.AiMagicx,
                FallbackProviderIds: [AiProviderIds.OneMinAi],
                RetrievalCorpusIds: [AiRetrievalCorpusIds.Runtime, AiRetrievalCorpusIds.Private, AiRetrievalCorpusIds.Community],
                AllowedTools: ResolveToolDescriptors(
                    AiToolIds.GetRuntimeSummary,
                    AiToolIds.GetCharacterDigest,
                    AiToolIds.ExplainValue,
                    AiToolIds.SimulateKarmaSpend,
                    AiToolIds.SimulateNuyenSpend,
                    AiToolIds.SearchBuildIdeas,
                    AiToolIds.SearchHubProjects,
                    AiToolIds.GetSessionDigest,
                    AiToolIds.CreatePortraitPrompt,
                    AiToolIds.QueueMediaJob,
                    AiToolIds.CreateApplyPreview),
                ToolingEnabled: true,
                StreamingPreferred: true,
                RouteClassId: AiRouteClassIds.GroundedRulesChat,
                PersonaId: AiPersonaIds.DeckerContact),
            new AiRoutePolicyDescriptor(
                RouteType: AiRouteTypes.Build,
                PrimaryProviderId: AiProviderIds.AiMagicx,
                FallbackProviderIds: [AiProviderIds.OneMinAi],
                RetrievalCorpusIds: [AiRetrievalCorpusIds.Runtime, AiRetrievalCorpusIds.Community],
                AllowedTools: ResolveToolDescriptors(
                    AiToolIds.GetRuntimeSummary,
                    AiToolIds.GetCharacterDigest,
                    AiToolIds.SimulateKarmaSpend,
                    AiToolIds.SimulateNuyenSpend,
                    AiToolIds.SearchBuildIdeas,
                    AiToolIds.SearchHubProjects,
                    AiToolIds.CreateApplyPreview),
                ToolingEnabled: true,
                StreamingPreferred: true,
                RouteClassId: AiRouteClassIds.BuildSimulation,
                PersonaId: AiPersonaIds.DeckerContact),
            new AiRoutePolicyDescriptor(
                RouteType: AiRouteTypes.Docs,
                PrimaryProviderId: AiProviderIds.OneMinAi,
                FallbackProviderIds: [AiProviderIds.AiMagicx],
                RetrievalCorpusIds: [AiRetrievalCorpusIds.Runtime, AiRetrievalCorpusIds.Private],
                AllowedTools: ResolveToolDescriptors(
                    AiToolIds.GetRuntimeSummary,
                    AiToolIds.GetCharacterDigest,
                    AiToolIds.ExplainValue,
                    AiToolIds.SearchHubProjects),
                ToolingEnabled: true,
                StreamingPreferred: true,
                RouteClassId: AiRouteClassIds.GroundedRulesChat,
                PersonaId: AiPersonaIds.DeckerContact),
            new AiRoutePolicyDescriptor(
                RouteType: AiRouteTypes.Recap,
                PrimaryProviderId: AiProviderIds.OneMinAi,
                FallbackProviderIds: [AiProviderIds.AiMagicx],
                RetrievalCorpusIds: [AiRetrievalCorpusIds.Private, AiRetrievalCorpusIds.Runtime],
                AllowedTools: ResolveToolDescriptors(
                    AiToolIds.GetRuntimeSummary,
                    AiToolIds.GetSessionDigest,
                    AiToolIds.DraftHistoryEntries,
                    AiToolIds.QueueMediaJob),
                ToolingEnabled: true,
                StreamingPreferred: true,
                RouteClassId: AiRouteClassIds.RecapGeneration,
                PersonaId: AiPersonaIds.DeckerContact)
        ];

    public static IReadOnlyList<AiRouteBudgetPolicyDescriptor> CreateRouteBudgets()
        =>
        [
            new AiRouteBudgetPolicyDescriptor(AiRouteTypes.Chat, AiBudgetUnits.ChummerAiUnits, 300, 12, "Cheap general Q&A and summarization path."),
            new AiRouteBudgetPolicyDescriptor(AiRouteTypes.Coach, AiBudgetUnits.ChummerAiUnits, 180, 8, "High-value coaching path with retrieval and tool calling."),
            new AiRouteBudgetPolicyDescriptor(AiRouteTypes.Build, AiBudgetUnits.ChummerAiUnits, 120, 6, "Build-planning path with structured Chummer grounding."),
            new AiRouteBudgetPolicyDescriptor(AiRouteTypes.Docs, AiBudgetUnits.ChummerAiUnits, 180, 8, "Docs concierge path with runtime-aware evidence and explanation support."),
            new AiRouteBudgetPolicyDescriptor(AiRouteTypes.Recap, AiBudgetUnits.ChummerAiUnits, 90, 4, "Session recap and document summarization path.")
        ];

    public static AiBudgetSnapshot CreateGatewayBudgetSnapshot(
        IReadOnlyList<AiRouteBudgetPolicyDescriptor>? routeBudgets,
        int monthlyConsumed = 0,
        int currentBurstConsumed = 0)
    {
        IReadOnlyList<AiRouteBudgetPolicyDescriptor> effectiveRouteBudgets = routeBudgets is { Count: > 0 }
            ? routeBudgets
            : CreateRouteBudgets();

        return new AiBudgetSnapshot(
            BudgetUnit: effectiveRouteBudgets[0].BudgetUnit,
            MonthlyAllowance: effectiveRouteBudgets.Sum(static policy => policy.MonthlyAllowance),
            MonthlyConsumed: Math.Max(0, monthlyConsumed),
            BurstLimitPerMinute: effectiveRouteBudgets.Max(static policy => policy.BurstLimitPerMinute),
            CurrentBurstConsumed: Math.Max(0, currentBurstConsumed),
            IsLimited: true);
    }

    public static AiRouteBudgetStatusProjection CreateRouteBudgetStatus(
        AiRouteBudgetPolicyDescriptor policy,
        AiBudgetSnapshot budget)
        => new(
            RouteType: policy.RouteType,
            BudgetUnit: budget.BudgetUnit,
            MonthlyAllowance: budget.MonthlyAllowance,
            MonthlyConsumed: budget.MonthlyConsumed,
            MonthlyRemaining: Math.Max(0, budget.MonthlyAllowance - budget.MonthlyConsumed),
            BurstLimitPerMinute: budget.BurstLimitPerMinute,
            CurrentBurstConsumed: budget.CurrentBurstConsumed,
            BurstRemaining: Math.Max(0, budget.BurstLimitPerMinute - budget.CurrentBurstConsumed),
            IsLimited: budget.IsLimited,
            Notes: policy.Notes);

    public static bool IsKnownRouteType(string routeType)
        => CreateRoutePolicies().Any(policy => string.Equals(policy.RouteType, routeType, StringComparison.Ordinal));

    public static AiRoutePolicyDescriptor ResolveRoutePolicy(string routeType)
        => CreateRoutePolicies()
            .FirstOrDefault(policy => string.Equals(policy.RouteType, routeType, StringComparison.Ordinal))
            ?? throw new InvalidOperationException($"Unknown AI route type '{routeType}'.");

    public static AiRouteBudgetPolicyDescriptor ResolveRouteBudget(string routeType)
        => CreateRouteBudgets()
            .FirstOrDefault(policy => string.Equals(policy.RouteType, routeType, StringComparison.Ordinal))
            ?? throw new InvalidOperationException($"Unknown AI route type '{routeType}'.");

    private static AiProviderCredentialCounts ResolveProviderCredentials(
        IReadOnlyDictionary<string, AiProviderCredentialCounts>? providerCredentials,
        string providerId)
    {
        if (providerCredentials is not null && providerCredentials.TryGetValue(providerId, out AiProviderCredentialCounts? configured))
        {
            return configured;
        }

        return new AiProviderCredentialCounts();
    }

    private static IReadOnlyList<AiProviderDescriptor> CreateProviderDescriptors(
        IReadOnlyDictionary<string, AiProviderCredentialCounts>? providerCredentials,
        IReadOnlyList<AiProviderDescriptor>? registeredProviders)
    {
        Dictionary<string, AiProviderDescriptor> providerDescriptors = (registeredProviders ?? Array.Empty<AiProviderDescriptor>())
            .GroupBy(static provider => provider.ProviderId, StringComparer.Ordinal)
            .ToDictionary(static group => group.Key, static group => group.Last(), StringComparer.Ordinal);
        List<string> orderedProviderIds = [AiProviderIds.AiMagicx, AiProviderIds.OneMinAi];

        orderedProviderIds.AddRange(providerDescriptors.Keys
            .Where(static providerId => providerId is not AiProviderIds.AiMagicx and not AiProviderIds.OneMinAi)
            .OrderBy(static providerId => providerId, StringComparer.Ordinal));

        return orderedProviderIds
            .Select(providerId => ResolveProviderDescriptor(providerId, providerDescriptors, providerCredentials))
            .ToArray();
    }

    private static AiProviderDescriptor ResolveProviderDescriptor(
        string providerId,
        IReadOnlyDictionary<string, AiProviderDescriptor> registeredProviders,
        IReadOnlyDictionary<string, AiProviderCredentialCounts>? providerCredentials)
    {
        AiProviderDescriptor baseline = CreateBaselineProviderDescriptor(providerId);
        if (registeredProviders.TryGetValue(providerId, out AiProviderDescriptor? registered))
        {
            baseline = baseline with
            {
                DisplayName = registered.DisplayName,
                SupportsToolCalling = registered.SupportsToolCalling,
                SupportsStreaming = registered.SupportsStreaming,
                SupportsAttachments = registered.SupportsAttachments,
                SupportsConversationMemory = registered.SupportsConversationMemory,
                AllowedRouteTypes = registered.AllowedRouteTypes,
                SessionSafe = registered.SessionSafe,
                AdapterKind = registered.AdapterKind,
                LiveExecutionEnabled = registered.LiveExecutionEnabled,
                AdapterRegistered = registered.AdapterRegistered,
                TransportBaseUrlConfigured = registered.TransportBaseUrlConfigured,
                TransportModelConfigured = registered.TransportModelConfigured,
                TransportMetadataConfigured = registered.TransportMetadataConfigured
            };
        }

        AiProviderCredentialCounts credentials = ResolveProviderCredentials(providerCredentials, providerId);
        return baseline with
        {
            IsConfigured = credentials.IsConfigured,
            PrimaryCredentialCount = credentials.PrimaryCredentialCount,
            FallbackCredentialCount = credentials.FallbackCredentialCount
        };
    }

    private static AiProviderDescriptor CreateBaselineProviderDescriptor(string providerId)
        => CreateDescriptor(AiProviderExecutionPolicies.Resolve(providerId));

    public static AiProviderDescriptor CreateDescriptor(
        AiProviderExecutionPolicy executionPolicy,
        string adapterKind = AiProviderAdapterKinds.None,
        bool liveExecutionEnabled = false,
        bool adapterRegistered = false,
        bool transportBaseUrlConfigured = false,
        bool transportModelConfigured = false,
        bool transportMetadataConfigured = false)
        => new(
            ProviderId: executionPolicy.ProviderId,
            DisplayName: executionPolicy.DisplayName,
            SupportsToolCalling: executionPolicy.SupportsToolCalling,
            SupportsStreaming: executionPolicy.SupportsStreaming,
            SupportsAttachments: executionPolicy.SupportsAttachments,
            SupportsConversationMemory: executionPolicy.SupportsConversationMemory,
            AllowedRouteTypes: executionPolicy.AllowedRouteTypes,
            SessionSafe: executionPolicy.SessionSafe,
            AdapterKind: adapterKind,
            LiveExecutionEnabled: liveExecutionEnabled,
            AdapterRegistered: adapterRegistered,
            TransportBaseUrlConfigured: transportBaseUrlConfigured,
            TransportModelConfigured: transportModelConfigured,
            TransportMetadataConfigured: transportMetadataConfigured);
}

public static class AiProviderExecutionPolicies
{
    public static AiProviderExecutionPolicy Resolve(string providerId)
        => providerId switch
        {
            AiProviderIds.AiMagicx => new AiProviderExecutionPolicy(
                ProviderId: providerId,
                DisplayName: "AI Magicx",
                SupportsToolCalling: true,
                SupportsStreaming: true,
                SupportsAttachments: true,
                SupportsConversationMemory: true,
                AllowedRouteTypes: [AiRouteTypes.Chat, AiRouteTypes.Coach, AiRouteTypes.Build, AiRouteTypes.Docs, AiRouteTypes.Recap],
                SessionSafe: false),
            AiProviderIds.OneMinAi => new AiProviderExecutionPolicy(
                ProviderId: providerId,
                DisplayName: "1minAI",
                SupportsToolCalling: false,
                SupportsStreaming: true,
                SupportsAttachments: true,
                SupportsConversationMemory: true,
                AllowedRouteTypes: [AiRouteTypes.Chat, AiRouteTypes.Coach, AiRouteTypes.Build, AiRouteTypes.Docs, AiRouteTypes.Recap],
                SessionSafe: true),
            _ => new AiProviderExecutionPolicy(
                ProviderId: providerId,
                DisplayName: providerId,
                SupportsToolCalling: false,
                SupportsStreaming: true,
                SupportsAttachments: false,
                SupportsConversationMemory: false,
                AllowedRouteTypes: Array.Empty<string>(),
                SessionSafe: false)
        };
}
