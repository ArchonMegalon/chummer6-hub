namespace Chummer.Run.AI.Compatibility;

[Obsolete("Use Chummer.Play.Contracts.Memory.PersonaMemoryQuery.")]
internal sealed record PersonaMemoryQuery(
    string SessionId,
    string? SceneId = null,
    int TopK = 4,
    string? PersonaId = null,
    string? LocationId = null,
    string? Location = null,
    IReadOnlyList<string>? SessionContext = null);

[Obsolete("Use Chummer.Play.Contracts.Memory.PersonaMemoryItem.")]
internal sealed record PersonaMemoryItem(
    string Key,
    string Value,
    double RelevanceScore);

[Obsolete("Use Chummer.Play.Contracts.Memory.SessionMemoryDraftRequest.")]
internal sealed record SessionMemoryDraftRequest(
    string SessionId,
    string? SceneId = null,
    string? Notes = null,
    string? Transcript = null,
    IReadOnlyList<string>? PlayerMessages = null);

[Obsolete("Use Chummer.Play.Contracts.Memory.SessionMemoryEvidence.")]
internal sealed record SessionMemoryEvidence(
    string Kind,
    string Reference,
    string Detail);

[Obsolete("Use Chummer.Play.Contracts.Memory.SessionRecapDraft.")]
internal sealed record SessionRecapDraft(
    string Title,
    string ShortText,
    string LongText,
    IReadOnlyList<string> Highlights,
    IReadOnlyList<SessionMemoryEvidence> Evidence,
    string DraftState,
    string ProposedCanonTarget);

[Obsolete("Use Chummer.Play.Contracts.Memory.SessionUnresolvedThreadDraft.")]
internal sealed record SessionUnresolvedThreadDraft(
    string ThreadId,
    string Title,
    string Summary,
    string Status,
    int MentionCount,
    IReadOnlyList<SessionMemoryEvidence> Evidence,
    string DraftState,
    string ProposedCanonTarget);

[Obsolete("Use Chummer.Play.Contracts.Memory.SessionTimelineDraftEntry.")]
internal sealed record SessionTimelineDraftEntry(
    string EntryId,
    string Summary,
    DateTimeOffset? AtUtc,
    string SourceKind,
    IReadOnlyList<SessionMemoryEvidence> Evidence,
    string DraftState,
    string ProposedCanonTarget);

[Obsolete("Use Chummer.Play.Contracts.Memory.SessionRelationshipChangeDraft.")]
internal sealed record SessionRelationshipChangeDraft(
    string ChangeId,
    string Summary,
    string ChangeKind,
    string Impact,
    int MentionCount,
    double Confidence,
    IReadOnlyList<SessionMemoryEvidence> Evidence,
    string DraftState,
    string ProposedCanonTarget);

[Obsolete("Use Chummer.Play.Contracts.Memory.SessionMemoryCandidateDraft.")]
internal sealed record SessionMemoryCandidateDraft(
    string CandidateId,
    string Category,
    string Title,
    string Summary,
    string CanonScope,
    double Confidence,
    IReadOnlyList<SessionMemoryEvidence> Evidence,
    string DraftState,
    string ProposedCanonTarget);

[Obsolete("Use Chummer.Play.Contracts.Memory.SessionMemoryDraftResult.")]
internal sealed record SessionMemoryDraftResult(
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

[Obsolete("Use Chummer.Play.Contracts.Memory.PersonaMemoryCard.")]
internal sealed record PersonaMemoryCard(
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

[Obsolete("Use Chummer.Play.Contracts.Memory.PersonaMemoryResult.")]
internal sealed record PersonaMemoryResult(
    string SessionId,
    IReadOnlyList<PersonaMemoryCard> Cards,
    int Retrieved,
    string? PersonaId = null,
    string? LocationId = null,
    string? Location = null,
    IReadOnlyList<string>? SessionContext = null);
