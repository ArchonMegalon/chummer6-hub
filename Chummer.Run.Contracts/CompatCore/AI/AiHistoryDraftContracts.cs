namespace Chummer.Contracts.AI;

public static class AiHistoryDraftApiOperations
{
    public const string CreateHistoryDraft = "create-history-draft";
}

public static class AiHistoryDraftSourceKinds
{
    public const string Character = "character";
    public const string Session = "session";
    public const string Transcript = "transcript";
}

public static class AiHistoryDraftEntryKinds
{
    public const string SessionRecap = "session-recap";
    public const string TimelineEvent = "timeline-event";
    public const string JournalEntry = "journal-entry";
    public const string CharacterHistory = "character-history";
}

public sealed record AiHistoryDraftRequest(
    string CharacterId,
    string? RuntimeFingerprint = null,
    string? SessionId = null,
    string? TranscriptId = null,
    string? Focus = null,
    int MaxEntries = 4);

public sealed record AiHistoryDraftEntry(
    string EntryKind,
    string Title,
    string Summary,
    string ApprovalTargetKind = AiApprovalTargetKinds.RecapDraft,
    bool RequiresApproval = true);

public sealed record AiHistoryDraftProjection(
    string DraftId,
    string Operation,
    string CharacterId,
    string CharacterDisplayName,
    string RulesetId,
    string RuntimeFingerprint,
    string SourceKind,
    string SourceId,
    string Summary,
    IReadOnlyList<AiHistoryDraftEntry> Entries,
    IReadOnlyList<AiEvidenceEntry> Evidence,
    IReadOnlyList<AiRiskEntry> Risks,
    string? TranscriptState = null,
    string? ProfileId = null,
    string? ProfileTitle = null);
