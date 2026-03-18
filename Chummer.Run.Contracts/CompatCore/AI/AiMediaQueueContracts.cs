namespace Chummer.Contracts.AI;

public static class AiMediaQueueApiOperations
{
    public const string QueueMediaJob = "queue-media-job";
}

public static class AiMediaQueueStates
{
    public const string Scaffolded = "scaffolded";
    public const string Queued = "queued";
}

public sealed record AiMediaQueueRequest(
    string JobType,
    string CharacterId,
    string? RuntimeFingerprint = null,
    string? Prompt = null,
    string? StylePackId = null,
    IReadOnlyDictionary<string, string>? Options = null);

public sealed record AiMediaQueueReceipt(
    string QueueId,
    string Operation,
    string JobType,
    string State,
    string CharacterId,
    string CharacterDisplayName,
    string RulesetId,
    string RuntimeFingerprint,
    string Prompt,
    IReadOnlyDictionary<string, string> Options,
    IReadOnlyList<AiEvidenceEntry> Evidence,
    IReadOnlyList<AiRiskEntry> Risks,
    bool ApprovalRequired = true,
    string? UnderlyingOperation = null,
    string? UnderlyingState = null);
