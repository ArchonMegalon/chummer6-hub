using Chummer.Run.AI.Services.Session;
using Chummer.Run.AI.Services.Transcription;
using Chummer.Run.Contracts.Transcription;
using RunMemoryContracts = Chummer.Run.Contracts.Memory;

namespace RunServicesVerification;

internal static class SessionMemoryIngestionVerification
{
    public static async Task RunAsync()
    {
        var ledger = new SessionLedgerService();
        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session-ingest",
                SceneId: "scene-ingest",
                EventType: "objective.unresolved",
                Payload: "find the stolen prototype",
                AtUtc: DateTimeOffset.UtcNow.AddMinutes(-2),
                EventId: "evt-ingest-1",
                SceneRevision: "scene-ingest:r1",
                IdempotencyKey: "evt-ingest-1")
        ]);

        var ingestion = new SessionMemoryIngestionService(
            new SessionMemoryService(ledger),
            new LocalTranscriptionProvider());

        var result = await ingestion.IngestAsync(new RunMemoryContracts.SessionMemoryIngestionRequest(
            CampaignId: "campaign-ingest",
            PrincipalId: "gm.ingest",
            SessionId: "session-ingest",
            SceneId: "scene-ingest",
            Notes: "scope this to the current scene",
            Transcription: new TranscriptionRequest(
                Source: "GM: Team is still chasing the prototype.\nFace: unresolved lead from fixer.",
                MimeType: "text/plain",
                LanguageHint: "en",
                PreserveSpeakerTurns: true)));

        VerificationAssert.Equal("campaign-ingest", result.CampaignId, "ingestion result should preserve campaign scoping.");
        VerificationAssert.Equal("gm.ingest", result.PrincipalId, "ingestion result should preserve principal scoping.");
        VerificationAssert.True(result.Transcription.Accepted, "transcription provider seam should accept valid source.");
        VerificationAssert.True(result.Draft.TimelineEntries.Any(entry => entry.SourceKind == "transcript"), "ingestion should propagate transcript evidence into session memory drafts.");
        VerificationAssert.True(result.Draft.UnresolvedThreadDrafts.Count >= 1, "ingestion should produce unresolved-thread drafts for review.");
    }
}
