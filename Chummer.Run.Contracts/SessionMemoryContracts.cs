namespace Chummer.Run.Contracts.Memory;

public sealed record PersonaMemoryQuery(
    string SessionId,
    string? SceneId = null,
    int TopK = 4,
    string? PersonaId = null,
    string? LocationId = null,
    string? Location = null,
    IReadOnlyList<string>? SessionContext = null);

public sealed record PersonaMemoryItem(
    string Key,
    string Value,
    double RelevanceScore);

public sealed record SessionMemoryDraftRequest(
    string SessionId,
    string? SceneId = null,
    string? Notes = null,
    string? Transcript = null,
    IReadOnlyList<string>? PlayerMessages = null);

public sealed record SessionMemoryEvidence(
    string Kind,
    string Reference,
    string Detail);

public sealed record SessionRecapDraft(
    string Title,
    string ShortText,
    string LongText,
    IReadOnlyList<string> Highlights,
    IReadOnlyList<SessionMemoryEvidence> Evidence,
    string DraftState,
    string ProposedCanonTarget);

public sealed record SessionUnresolvedThreadDraft(
    string ThreadId,
    string Title,
    string Summary,
    string Status,
    int MentionCount,
    IReadOnlyList<SessionMemoryEvidence> Evidence,
    string DraftState,
    string ProposedCanonTarget);

public sealed record SessionTimelineDraftEntry(
    string EntryId,
    string Summary,
    DateTimeOffset? AtUtc,
    string SourceKind,
    IReadOnlyList<SessionMemoryEvidence> Evidence,
    string DraftState,
    string ProposedCanonTarget);

public sealed record SessionRelationshipChangeDraft(
    string ChangeId,
    string Summary,
    string ChangeKind,
    string Impact,
    int MentionCount,
    double Confidence,
    IReadOnlyList<SessionMemoryEvidence> Evidence,
    string DraftState,
    string ProposedCanonTarget);

public sealed record SessionMemoryCandidateDraft(
    string CandidateId,
    string Category,
    string Title,
    string Summary,
    string CanonScope,
    double Confidence,
    IReadOnlyList<SessionMemoryEvidence> Evidence,
    string DraftState,
    string ProposedCanonTarget);

public sealed record SessionMemoryDraftResult(
    string SessionId,
    string? SceneId,
    string Recap,
    IReadOnlyList<string> UnresolvedHooks,
    IReadOnlyList<string> TimelineDrafts,
    IReadOnlyList<string> RelationshipChanges,
    SessionRecapDraft RecapDraft,
    IReadOnlyList<SessionUnresolvedThreadDraft> UnresolvedThreadDrafts,
    IReadOnlyList<SessionTimelineDraftEntry> TimelineEntries,
    IReadOnlyList<SessionRelationshipChangeDraft> RelationshipChangeDrafts,
    IReadOnlyList<SessionMemoryCandidateDraft> MemoryCandidateDrafts,
    IReadOnlyList<string> ProposedCanonTargets,
    double Confidence,
    DateTimeOffset GeneratedAtUtc);

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

public sealed record PersonaMemoryCard(
    string PersonaId,
    string StaticCard,
    string RelationshipState,
    string EpisodicMemory,
    string HiddenPlotMemory,
    DateTimeOffset UpdatedAtUtc,
    string? CardId = null,
    string? LocationId = null,
    string? Location = null,
    IReadOnlyList<string>? SceneIds = null,
    IReadOnlyList<string>? SessionContextTags = null);

public sealed record PersonaMemoryResult(
    string SessionId,
    IReadOnlyList<PersonaMemoryCard> Cards,
    int Retrieved,
    string? PersonaId = null,
    string? LocationId = null,
    string? Location = null,
    IReadOnlyList<string>? SessionContext = null);
