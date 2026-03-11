namespace Chummer.Run.Contracts.Observability;

public sealed record PipelineProjectionEnvelope(
    DateTimeOffset GeneratedAtUtc,
    IReadOnlyList<PipelineProjection> Pipelines);

public sealed record PipelineProjection(
    string Pipeline,
    PipelineObservabilityProjection Observability,
    PipelineIdempotencyProjection Idempotency,
    PipelineCostProjection Cost,
    PipelineDeadLetterProjection DeadLetter);

public sealed record PipelineObservabilityProjection(
    int ProcessedCount,
    int ActiveCount,
    int SucceededCount,
    int FailedCount,
    int DuplicateCount,
    int IgnoredCount);

public sealed record PipelineIdempotencyProjection(
    int TrackedKeys,
    int ReplayCount,
    DateTimeOffset? LastReplayAtUtc);

public sealed record PipelineCostProjection(
    double EstimatedUsd,
    int BudgetUnitsConsumed);

public sealed record PipelineDeadLetterProjection(
    int Count,
    IReadOnlyList<PipelineDeadLetterEntry> Recent);

public sealed record PipelineDeadLetterEntry(
    string ItemId,
    string Reason,
    DateTimeOffset OccurredAtUtc,
    string? Fingerprint = null);
