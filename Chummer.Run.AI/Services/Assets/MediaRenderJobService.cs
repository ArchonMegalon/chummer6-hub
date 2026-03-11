using Chummer.Media.Contracts;
using Chummer.Run.Contracts.Observability;
using System.Collections.Concurrent;
using System.Text;

namespace Chummer.Run.AI.Services.Assets;

public interface IMediaRenderJobService
{
    Task<MediaRenderJobStatus> EnqueueAsync(
        MediaRenderJobEnqueueRequest request,
        CancellationToken cancellationToken = default);

    MediaRenderJobStatus? Get(string jobId);
    IReadOnlyList<MediaRenderJobStatus> List();
    PipelineProjection GetMediaPipelineProjection();
}

public sealed class MediaRenderJobService : IMediaRenderJobService
{
    private sealed class MediaRenderJobRow
    {
        public required string JobId { get; init; }
        public required MediaRenderJobType JobType { get; init; }
        public required string DeduplicationKey { get; init; }
        public required string Category { get; init; }
        public required string Payload { get; init; }
        public required string Source { get; init; }
        public required AssetLifecyclePolicy Policy { get; init; }
        public required DateTimeOffset CreatedAtUtc { get; init; }
        public DateTimeOffset? StartedAtUtc { get; set; }
        public DateTimeOffset? CompletedAtUtc { get; set; }
        public string? AssetId { get; set; }
        public string? Error { get; set; }
        public MediaRenderJobState State { get; set; }
    }

    private readonly ConcurrentDictionary<string, MediaRenderJobRow> _jobs = new(StringComparer.OrdinalIgnoreCase);
    private readonly ConcurrentDictionary<string, string> _jobIdsByDeduplicationKey = new(StringComparer.OrdinalIgnoreCase);
    private readonly ConcurrentQueue<PipelineDeadLetterEntry> _deadLetters = new();
    private readonly IAssetLifecycleService _assetLifecycle;
    private readonly object _sync = new();
    private long _enqueueCount;
    private long _dedupeReuseCount;

    public MediaRenderJobService(IAssetLifecycleService assetLifecycle)
    {
        _assetLifecycle = assetLifecycle;
    }

    public Task<MediaRenderJobStatus> EnqueueAsync(
        MediaRenderJobEnqueueRequest request,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var normalizedRequest = Normalize(request);

        if (TryGetReusableJob(normalizedRequest.DeduplicationKey, out var existing))
        {
            Interlocked.Increment(ref _dedupeReuseCount);
            return Task.FromResult(ToStatus(existing));
        }

        var row = new MediaRenderJobRow
        {
            JobId = $"job_{Guid.NewGuid():N}",
            JobType = normalizedRequest.JobType,
            DeduplicationKey = normalizedRequest.DeduplicationKey,
            Category = normalizedRequest.Category,
            Payload = normalizedRequest.Payload,
            Source = normalizedRequest.Source,
            Policy = BuildPolicy(normalizedRequest),
            CreatedAtUtc = DateTimeOffset.UtcNow,
            State = MediaRenderJobState.Queued
        };

        _jobs[row.JobId] = row;
        _jobIdsByDeduplicationKey[row.DeduplicationKey] = row.JobId;
        Interlocked.Increment(ref _enqueueCount);

        _ = ProcessAsync(row);

        return Task.FromResult(ToStatus(row));
    }

    public MediaRenderJobStatus? Get(string jobId)
    {
        if (string.IsNullOrWhiteSpace(jobId) || !_jobs.TryGetValue(jobId, out var row))
        {
            return null;
        }

        RefreshExpiry(row);
        return ToStatus(row);
    }

    public IReadOnlyList<MediaRenderJobStatus> List() =>
        _jobs.Values
            .OrderByDescending(static row => row.CreatedAtUtc)
            .Select(row =>
            {
                RefreshExpiry(row);
                return ToStatus(row);
            })
            .ToArray();

    public PipelineProjection GetMediaPipelineProjection()
    {
        var queued = 0;
        var running = 0;
        var succeeded = 0;
        var failed = 0;
        var expired = 0;
        foreach (var row in _jobs.Values)
        {
            RefreshExpiry(row);
            switch (row.State)
            {
                case MediaRenderJobState.Queued:
                    queued++;
                    break;
                case MediaRenderJobState.Running:
                    running++;
                    break;
                case MediaRenderJobState.Succeeded:
                    succeeded++;
                    break;
                case MediaRenderJobState.Failed:
                    failed++;
                    break;
                case MediaRenderJobState.Expired:
                    expired++;
                    break;
            }
        }

        return new PipelineProjection(
            Pipeline: "media",
            Observability: new PipelineObservabilityProjection(
                ProcessedCount: ToInt(_enqueueCount),
                ActiveCount: queued + running,
                SucceededCount: succeeded,
                FailedCount: failed,
                DuplicateCount: ToInt(_dedupeReuseCount),
                IgnoredCount: expired),
            Idempotency: new PipelineIdempotencyProjection(
                TrackedKeys: _jobIdsByDeduplicationKey.Count,
                ReplayCount: ToInt(_dedupeReuseCount),
                LastReplayAtUtc: null),
            Cost: new PipelineCostProjection(
                EstimatedUsd: 0,
                BudgetUnitsConsumed: 0),
            DeadLetter: new PipelineDeadLetterProjection(
                Count: _deadLetters.Count,
                Recent: _deadLetters.Take(25).ToArray()));
    }

    private async Task ProcessAsync(MediaRenderJobRow row)
    {
        try
        {
            lock (_sync)
            {
                if (row.State != MediaRenderJobState.Queued)
                {
                    return;
                }

                row.State = MediaRenderJobState.Running;
                row.StartedAtUtc = DateTimeOffset.UtcNow;
            }

            var payloadBytes = Encoding.UTF8.GetByteCount(row.Payload);
            if (row.Policy.MaxBytes > 0 && payloadBytes > row.Policy.MaxBytes)
            {
                throw new InvalidOperationException($"Payload exceeds MaxBytes policy ({row.Policy.MaxBytes}).");
            }

            var asset = await _assetLifecycle.StoreAsync(
                category: row.Category,
                content: row.Payload,
                source: row.Source,
                policy: row.Policy,
                cancellationToken: CancellationToken.None);

            lock (_sync)
            {
                row.AssetId = asset.AssetId;
                row.State = MediaRenderJobState.Succeeded;
                row.CompletedAtUtc = DateTimeOffset.UtcNow;
                row.Error = null;
            }
        }
        catch (Exception exception)
        {
            lock (_sync)
            {
                row.Error = exception.Message;
                row.State = MediaRenderJobState.Failed;
                row.CompletedAtUtc = DateTimeOffset.UtcNow;
            }

            _deadLetters.Enqueue(new PipelineDeadLetterEntry(
                ItemId: row.JobId,
                Reason: exception.Message,
                OccurredAtUtc: DateTimeOffset.UtcNow,
                Fingerprint: row.DeduplicationKey));
            while (_deadLetters.Count > 200 && _deadLetters.TryDequeue(out _))
            {
            }

            _jobIdsByDeduplicationKey.TryRemove(row.DeduplicationKey, out _);
        }
    }

    private bool TryGetReusableJob(string deduplicationKey, out MediaRenderJobRow row)
    {
        row = null!;

        if (!_jobIdsByDeduplicationKey.TryGetValue(deduplicationKey, out var jobId) ||
            !_jobs.TryGetValue(jobId, out var existing))
        {
            return false;
        }

        RefreshExpiry(existing);
        if (existing.State is MediaRenderJobState.Failed or MediaRenderJobState.Expired)
        {
            _jobIdsByDeduplicationKey.TryRemove(deduplicationKey, out _);
            return false;
        }

        row = existing;
        return true;
    }

    private void RefreshExpiry(MediaRenderJobRow row)
    {
        if (row.State != MediaRenderJobState.Succeeded ||
            row.Policy.LongTermCache ||
            row.Policy.CacheTtl <= TimeSpan.Zero ||
            row.CompletedAtUtc is not { } completedAtUtc ||
            completedAtUtc + row.Policy.CacheTtl > DateTimeOffset.UtcNow)
        {
            return;
        }

        lock (_sync)
        {
            if (row.State == MediaRenderJobState.Succeeded &&
                row.CompletedAtUtc is { } completed &&
                completed + row.Policy.CacheTtl <= DateTimeOffset.UtcNow)
            {
                row.State = MediaRenderJobState.Expired;
                _jobIdsByDeduplicationKey.TryRemove(row.DeduplicationKey, out _);
            }
        }
    }

    private static MediaRenderJobEnqueueRequest Normalize(MediaRenderJobEnqueueRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.DeduplicationKey))
        {
            throw new ArgumentException("DeduplicationKey is required.", nameof(request));
        }

        if (string.IsNullOrWhiteSpace(request.Category))
        {
            throw new ArgumentException("Category is required.", nameof(request));
        }

        if (string.IsNullOrWhiteSpace(request.Payload))
        {
            throw new ArgumentException("Payload is required.", nameof(request));
        }

        if (string.IsNullOrWhiteSpace(request.Source))
        {
            throw new ArgumentException("Source is required.", nameof(request));
        }

        return request with
        {
            DeduplicationKey = request.DeduplicationKey.Trim(),
            Category = request.Category.Trim(),
            Payload = request.Payload.Trim(),
            Source = request.Source.Trim()
        };
    }

    private static AssetLifecyclePolicy BuildPolicy(MediaRenderJobEnqueueRequest request)
    {
        var cacheTtl = request.CacheTtl is { } ttl && ttl > TimeSpan.Zero
            ? ttl
            : TimeSpan.FromDays(7);
        var maxBytes = request.MaxBytes > 0
            ? request.MaxBytes
            : Math.Max(4096, Encoding.UTF8.GetByteCount(request.Payload) * 2);

        return new AssetLifecyclePolicy(
            CacheTtl: cacheTtl,
            LongTermCache: false,
            MaxBytes: maxBytes,
            RequiresApproval: request.RequiresApproval,
            PersistOnApproval: request.PersistOnApproval,
            StorageClass: AssetStorageClass.ObjectStorage,
            AllowPersistentPinning: request.AllowPersistentPinning);
    }

    private MediaRenderJobStatus ToStatus(MediaRenderJobRow row)
    {
        lock (_sync)
        {
            return new MediaRenderJobStatus(
                JobId: row.JobId,
                JobType: row.JobType,
                State: row.State,
                CreatedAtUtc: row.CreatedAtUtc,
                StartedAtUtc: row.StartedAtUtc,
                CompletedAtUtc: row.CompletedAtUtc,
                AssetId: row.AssetId,
                CacheTtl: row.Policy.CacheTtl,
                Error: row.Error);
        }
    }

    private static int ToInt(long value) => value > int.MaxValue ? int.MaxValue : (int)value;
}
