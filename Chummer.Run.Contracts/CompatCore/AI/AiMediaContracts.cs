namespace Chummer.Contracts.AI;

public static class AiMediaApiOperations
{
    public const string QueuePortraitJob = "queue-portrait-job";
    public const string QueueDossierJob = "queue-dossier-job";
    public const string QueueRouteVideoJob = "queue-route-video-job";
}

public static class AiMediaJobTypes
{
    public const string Portrait = "portrait";
    public const string Dossier = "dossier";
    public const string RouteVideo = "route-video";
}

public static class AiMediaJobStates
{
    public const string Queued = "queued";
    public const string NotImplemented = "not-implemented";
}

public sealed record AiMediaJobRequest(
    string Prompt,
    string? CharacterId = null,
    string? RuntimeFingerprint = null,
    string? StylePackId = null,
    IReadOnlyDictionary<string, string>? Options = null);

public sealed record AiMediaJobReceipt(
    string JobId,
    string JobType,
    string State,
    string Message,
    bool ApprovalRequired = true,
    string? CharacterId = null,
    string? RuntimeFingerprint = null,
    string? OwnerId = null);
