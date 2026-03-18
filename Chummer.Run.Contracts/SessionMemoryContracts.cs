namespace Chummer.Run.Contracts.Memory;

public sealed record SessionMemoryIngestionRequest(
    string CampaignId,
    string PrincipalId,
    string SessionId,
    Chummer.Run.Contracts.Transcription.TranscriptionRequest Transcription,
    string? SceneId = null,
    string? Notes = null,
    IReadOnlyList<string>? PlayerMessages = null);

public sealed record SessionMemoryIngestionResult(
    string CampaignId,
    string PrincipalId,
    string SessionId,
    string? SceneId,
    Chummer.Run.Contracts.Transcription.TranscriptionResult Transcription,
    Chummer.Play.Contracts.Memory.SessionMemoryDraftResult Draft);
