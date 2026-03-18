using Chummer.Contracts.Journal;

namespace Chummer.Contracts.Presentation;

public static class JournalPanelSurfaceIds
{
    public const string NotesPanel = "notes-panel";
    public const string LedgerPanel = "ledger-panel";
    public const string TimelinePanel = "timeline-panel";
    public const string CampaignJournalPanel = "campaign-journal-panel";
}

public static class JournalPanelSectionKinds
{
    public const string Notes = "notes";
    public const string Ledger = "ledger";
    public const string Timeline = "timeline";
    public const string Summary = "summary";
}

public sealed record NoteListItem(
    string NoteId,
    string Title,
    string ScopeKind,
    int BlockCount,
    DateTimeOffset UpdatedAtUtc);

public sealed record LedgerEntryView(
    string EntryId,
    string Kind,
    string Label,
    decimal Amount,
    string Currency,
    DateTimeOffset OccurredAtUtc,
    string? NoteId = null);

public sealed record TimelineEventView(
    string EventId,
    string Kind,
    string Title,
    DateTimeOffset StartsAtUtc,
    DateTimeOffset? EndsAtUtc = null,
    string? NoteId = null,
    string? LedgerEntryId = null);

public sealed record JournalPanelSection(
    string SectionId,
    string Kind,
    string Title,
    int ItemCount);

public sealed record JournalPanelProjection(
    string ScopeKind,
    string ScopeId,
    IReadOnlyList<JournalPanelSection> Sections,
    IReadOnlyList<NoteListItem> Notes,
    IReadOnlyList<LedgerEntryView> LedgerEntries,
    IReadOnlyList<TimelineEventView> TimelineEvents);
