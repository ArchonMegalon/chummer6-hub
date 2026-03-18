namespace Chummer.Play.Core.Offline;

public sealed record OfflineLedgerEnvelope(
    string SessionId,
    string SceneId,
    string SceneRevision,
    string RuntimeFingerprint,
    IReadOnlyList<string> PendingEvents,
    long LastKnownSequence,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? LastSyncedAtUtc,
    int LastAcceptedEventCount
);
