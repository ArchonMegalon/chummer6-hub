namespace Chummer.Contracts.AI;

public sealed record AiConversationCatalogQuery(
    string? ConversationId = null,
    string? RouteType = null,
    string? CharacterId = null,
    string? RuntimeFingerprint = null,
    int MaxCount = 20,
    string? WorkspaceId = null);

public sealed record AiConversationCatalogPage(
    IReadOnlyList<AiConversationSnapshot> Items,
    int TotalCount);

public sealed record AiConversationAuditSummary(
    string ConversationId,
    string RouteType,
    int MessageCount,
    DateTimeOffset? LastUpdatedAtUtc,
    string? RuntimeFingerprint = null,
    string? CharacterId = null,
    string? LastAssistantAnswer = null,
    string? LastProviderId = null,
    AiCacheMetadata? Cache = null,
    AiProviderRouteDecision? RouteDecision = null,
    AiGroundingCoverage? GroundingCoverage = null,
    string? WorkspaceId = null,
    string? FlavorLine = null,
    AiBudgetSnapshot? Budget = null,
    AiStructuredAnswer? StructuredAnswer = null);

public sealed record AiConversationAuditCatalogPage(
    IReadOnlyList<AiConversationAuditSummary> Items,
    int TotalCount);
