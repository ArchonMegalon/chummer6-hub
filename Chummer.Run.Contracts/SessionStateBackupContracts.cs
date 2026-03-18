using Chummer.Play.Contracts.Relay;
using Chummer.Run.Contracts.Observability;

namespace Chummer.Run.Contracts.Relay;

public sealed record SessionLedgerSceneBackup(
    string SessionId,
    string SceneId,
    IReadOnlyList<SessionEventEnvelope> Events);

public sealed record SessionLedgerBackupPackage(
    DateTimeOffset ExportedAtUtc,
    IReadOnlyList<SessionLedgerSceneBackup> Scenes,
    IReadOnlyList<PipelineDeadLetterEntry> DeadLetters,
    long ProcessedEvents,
    long AcceptedEvents,
    long DuplicateEvents,
    long IgnoredEvents,
    long IdempotencyReplayCount,
    DateTimeOffset? LastReplayAtUtc,
    string ContractFamily = "session_state_backup_v1");
