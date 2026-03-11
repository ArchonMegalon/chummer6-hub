using Chummer.Run.Contracts.Transcription;
using RunMemoryContracts = Chummer.Run.Contracts.Memory;

namespace Chummer.Run.AI.Services.Session;

public interface ISessionMemoryIngestionService
{
    Task<RunMemoryContracts.SessionMemoryIngestionResult> IngestAsync(
        RunMemoryContracts.SessionMemoryIngestionRequest request,
        CancellationToken cancellationToken = default);
}

public sealed class SessionMemoryIngestionService : ISessionMemoryIngestionService
{
    private readonly ISessionMemoryService _memoryService;
    private readonly ITranscriptionProvider _transcriptionProvider;

    public SessionMemoryIngestionService(
        ISessionMemoryService memoryService,
        ITranscriptionProvider transcriptionProvider)
    {
        _memoryService = memoryService;
        _transcriptionProvider = transcriptionProvider;
    }

    public async Task<RunMemoryContracts.SessionMemoryIngestionResult> IngestAsync(
        RunMemoryContracts.SessionMemoryIngestionRequest request,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(request.CampaignId))
        {
            throw new ArgumentException("campaignId is required.", nameof(request));
        }

        if (string.IsNullOrWhiteSpace(request.PrincipalId))
        {
            throw new ArgumentException("principalId is required.", nameof(request));
        }

        if (string.IsNullOrWhiteSpace(request.SessionId))
        {
            throw new ArgumentException("sessionId is required.", nameof(request));
        }

        var transcription = await _transcriptionProvider.TranscribeAsync(request.Transcription, cancellationToken);
        var draft = _memoryService.Draft(
            new SessionMemoryDraftRequest(
                SessionId: request.SessionId,
                SceneId: request.SceneId,
                Notes: request.Notes,
                Transcript: transcription.Transcript,
                PlayerMessages: request.PlayerMessages),
            request.SceneId);

        return new RunMemoryContracts.SessionMemoryIngestionResult(
            CampaignId: request.CampaignId.Trim(),
            PrincipalId: request.PrincipalId.Trim(),
            SessionId: request.SessionId.Trim(),
            SceneId: string.IsNullOrWhiteSpace(request.SceneId) ? null : request.SceneId.Trim(),
            Transcription: transcription,
            Draft: draft);
    }
}
