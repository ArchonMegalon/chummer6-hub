namespace Chummer.Play.Core.Sync;

public sealed record SyncCheckpoint(
    string SessionId,
    string SceneId,
    string SceneRevision,
    string ProjectionFingerprint,
    long AppliedThroughSequence,
    DateTimeOffset CapturedAtUtc
);
