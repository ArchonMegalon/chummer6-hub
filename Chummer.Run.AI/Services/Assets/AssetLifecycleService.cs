using Chummer.Media.Contracts;
using Chummer.Run.Contracts.Observability;
using System.Collections.Concurrent;
using System.Security.Cryptography;
using System.Text;

namespace Chummer.Run.AI.Services.Assets;

public interface IAssetLifecycleService
{
    Task<AssetRenderResult> StoreAsync(string category, string content, string? source = null, AssetLifecyclePolicy? policy = null, CancellationToken cancellationToken = default);
    AssetCatalogItem? Resolve(string assetId);
    IReadOnlyList<AssetCatalogItem> List();
    Task<AssetCatalogItem?> ApplyLifecycleAsync(string assetId, AssetLifecycleMutationRequest request, CancellationToken cancellationToken = default);
    AssetLifecycleSweepResult SweepExpired(DateTimeOffset? utcNow = null);
    PipelineProjection GetApprovalPipelineProjection();
}

public sealed class AssetLifecycleService : IAssetLifecycleService
{
    private sealed class AssetState
    {
        public required string AssetId { get; init; }
        public required string Url { get; set; }
        public required string Category { get; init; }
        public required string Source { get; init; }
        public required AssetLifecyclePolicy Policy { get; init; }
        public required DateTimeOffset CreatedAtUtc { get; init; }
        public required string Version { get; init; }
        public required string Content { get; init; }
        public required string StorageKey { get; set; }
        public required string CacheKey { get; init; }
        public AssetStorageClass StorageClass { get; set; }
        public AssetApprovalState ApprovalState { get; set; }
        public AssetRetentionState RetentionState { get; set; }
        public bool IsPinned { get; set; }
        public DateTimeOffset? LastAccessedAtUtc { get; set; }
        public int CacheHitCount { get; set; }
        public DateTimeOffset? ApprovedAtUtc { get; set; }
    }

    private readonly ConcurrentDictionary<string, AssetState> _assets = new();
    private readonly ConcurrentDictionary<string, string> _assetIdsByCacheKey = new(StringComparer.Ordinal);
    private readonly ConcurrentQueue<PipelineDeadLetterEntry> _deadLetters = new();
    private readonly object _sync = new();
    private readonly TimeSpan _defaultCacheTtl = TimeSpan.FromDays(30);
    private long _storeCount;
    private long _lifecycleMutations;
    private long _replayMutations;
    private DateTimeOffset? _lastReplayAtUtc;
    private readonly ConcurrentDictionary<string, byte> _mutationFingerprints = new(StringComparer.Ordinal);

    public Task<AssetRenderResult> StoreAsync(
        string category,
        string content,
        string? source = null,
        AssetLifecyclePolicy? policy = null,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (string.IsNullOrWhiteSpace(category))
        {
            throw new ArgumentException("Category is required.", nameof(category));
        }

        var normalizedCategory = category.Trim();
        var normalizedSource = string.IsNullOrWhiteSpace(source) ? "runtime-scaffold" : source.Trim();
        var normalizedPolicy = NormalizePolicy(content, policy);
        var contentBytes = Encoding.UTF8.GetByteCount(content);
        if (normalizedPolicy.MaxBytes > 0 && contentBytes > normalizedPolicy.MaxBytes)
        {
            throw new InvalidOperationException($"Payload exceeds MaxBytes policy ({normalizedPolicy.MaxBytes}).");
        }

        var cacheKey = BuildCacheKey(normalizedCategory, normalizedSource, content, normalizedPolicy);

        lock (_sync)
        {
            if (TryGetReusableAsset(cacheKey, out var existing))
            {
                existing.CacheHitCount++;
                existing.LastAccessedAtUtc = DateTimeOffset.UtcNow;
                return Task.FromResult(ToRenderResult(existing, cacheReused: true));
            }

            var createdAtUtc = DateTimeOffset.UtcNow;
            var assetId = $"asset_{Guid.NewGuid():N}";
            var version = $"v1-{ComputeHash(content)[..12]}";
            var retentionState = DetermineRetentionState(
                normalizedPolicy,
                approvalState: normalizedPolicy.RequiresApproval ? AssetApprovalState.Draft : AssetApprovalState.Approved,
                isPinned: false,
                explicitPersist: false);
            var storageClass = DetermineStorageClass(normalizedPolicy, retentionState);
            var storageKey = BuildStorageKey(storageClass, normalizedCategory, assetId, version);
            var assetState = new AssetState
            {
                AssetId = assetId,
                Url = BuildSignedAssetUrl(assetId, version),
                Category = normalizedCategory,
                Source = normalizedSource,
                Policy = normalizedPolicy,
                CreatedAtUtc = createdAtUtc,
                Version = version,
                Content = content,
                StorageKey = storageKey,
                CacheKey = cacheKey,
                StorageClass = storageClass,
                ApprovalState = normalizedPolicy.RequiresApproval ? AssetApprovalState.Draft : AssetApprovalState.Approved,
                RetentionState = retentionState,
                IsPinned = false,
                LastAccessedAtUtc = null,
                CacheHitCount = 0,
                ApprovedAtUtc = normalizedPolicy.RequiresApproval ? null : createdAtUtc
            };

            _assets[assetId] = assetState;
            _assetIdsByCacheKey[cacheKey] = assetId;
            Interlocked.Increment(ref _storeCount);

            return Task.FromResult(ToRenderResult(assetState, cacheReused: false));
        }
    }

    public AssetCatalogItem? Resolve(string assetId)
    {
        if (string.IsNullOrWhiteSpace(assetId))
        {
            return null;
        }

        lock (_sync)
        {
            if (!_assets.TryGetValue(assetId, out var assetState))
            {
                return null;
            }

            if (ExpireIfNeeded(assetState, DateTimeOffset.UtcNow))
            {
                return null;
            }

            assetState.LastAccessedAtUtc = DateTimeOffset.UtcNow;
            assetState.CacheHitCount++;
            return ToCatalogItem(assetState);
        }
    }

    public IReadOnlyList<AssetCatalogItem> List()
    {
        var now = DateTimeOffset.UtcNow;
        lock (_sync)
        {
            foreach (var assetState in _assets.Values)
            {
                ExpireIfNeeded(assetState, now);
            }

            return _assets.Values
                .Where(static state => state.RetentionState != AssetRetentionState.Expired)
                .OrderByDescending(static state => state.CreatedAtUtc)
                .Select(ToCatalogItem)
                .ToList();
        }
    }

    public Task<AssetCatalogItem?> ApplyLifecycleAsync(
        string assetId,
        AssetLifecycleMutationRequest request,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (string.IsNullOrWhiteSpace(assetId))
        {
            return Task.FromResult<AssetCatalogItem?>(null);
        }

        lock (_sync)
        {
            if (!_assets.TryGetValue(assetId, out var assetState) || ExpireIfNeeded(assetState, DateTimeOffset.UtcNow))
            {
                return Task.FromResult<AssetCatalogItem?>(null);
            }

            if (request.ApprovalState is { } approvalState)
            {
                switch (approvalState)
                {
                    case AssetApprovalState.Approved:
                        assetState.ApprovalState = AssetApprovalState.Approved;
                        assetState.ApprovedAtUtc = DateTimeOffset.UtcNow;
                        break;
                    case AssetApprovalState.Rejected:
                        assetState.ApprovalState = AssetApprovalState.Rejected;
                        assetState.ApprovedAtUtc = null;
                        assetState.IsPinned = false;
                        break;
                    default:
                        assetState.ApprovalState = AssetApprovalState.Draft;
                        assetState.ApprovedAtUtc = null;
                        assetState.IsPinned = false;
                        break;
                }
            }

            if (request.Persist is true &&
                assetState.Policy.RequiresApproval &&
                assetState.ApprovalState != AssetApprovalState.Approved)
            {
                EnqueueDeadLetter(assetId, "approval-required-before-persist", BuildMutationFingerprint(assetId, request));
                throw new InvalidOperationException("Asset must be approved before it can be persisted.");
            }

            if (request.Pin is true)
            {
                if (!assetState.Policy.AllowPersistentPinning)
                {
                    EnqueueDeadLetter(assetId, "pinning-not-allowed-by-policy", BuildMutationFingerprint(assetId, request));
                    throw new InvalidOperationException("Asset policy does not allow pinning.");
                }

                if (assetState.Policy.RequiresApproval && assetState.ApprovalState != AssetApprovalState.Approved)
                {
                    EnqueueDeadLetter(assetId, "approval-required-before-pinning", BuildMutationFingerprint(assetId, request));
                    throw new InvalidOperationException("Asset must be approved before it can be pinned.");
                }

                assetState.IsPinned = true;
            }
            else if (request.Pin is false)
            {
                assetState.IsPinned = false;
            }

            var explicitPersist = request.Persist ?? false;
            assetState.RetentionState = DetermineRetentionState(assetState.Policy, assetState.ApprovalState, assetState.IsPinned, explicitPersist);
            assetState.StorageClass = DetermineStorageClass(assetState.Policy, assetState.RetentionState);
            assetState.StorageKey = BuildStorageKey(assetState.StorageClass, assetState.Category, assetState.AssetId, assetState.Version);
            assetState.Url = BuildSignedAssetUrl(assetState.AssetId, assetState.Version);
            Interlocked.Increment(ref _lifecycleMutations);
            TrackMutationReplay(assetId, request);
            return Task.FromResult<AssetCatalogItem?>(ToCatalogItem(assetState));
        }
    }

    public AssetLifecycleSweepResult SweepExpired(DateTimeOffset? utcNow = null)
    {
        var now = utcNow ?? DateTimeOffset.UtcNow;
        lock (_sync)
        {
            var expiredCount = 0;
            foreach (var assetState in _assets.Values)
            {
                if (ExpireIfNeeded(assetState, now))
                {
                    expiredCount++;
                }
            }

            var activeCount = _assets.Values.Count(static state => state.RetentionState != AssetRetentionState.Expired);
            return new AssetLifecycleSweepResult(expiredCount, activeCount, now);
        }
    }

    public PipelineProjection GetApprovalPipelineProjection()
    {
        lock (_sync)
        {
            var active = _assets.Values.Count(state => state.RetentionState != AssetRetentionState.Expired);
            var approved = _assets.Values.Count(state => state.ApprovalState == AssetApprovalState.Approved);
            var rejected = _assets.Values.Count(state => state.ApprovalState == AssetApprovalState.Rejected);
            var drafts = _assets.Values.Count(state => state.ApprovalState == AssetApprovalState.Draft);
            return new PipelineProjection(
                Pipeline: "approval",
                Observability: new PipelineObservabilityProjection(
                    ProcessedCount: ToInt(_storeCount + _lifecycleMutations),
                    ActiveCount: active,
                    SucceededCount: approved,
                    FailedCount: rejected,
                    DuplicateCount: 0,
                    IgnoredCount: drafts),
                Idempotency: new PipelineIdempotencyProjection(
                    TrackedKeys: _mutationFingerprints.Count,
                    ReplayCount: ToInt(_replayMutations),
                    LastReplayAtUtc: _lastReplayAtUtc),
                Cost: new PipelineCostProjection(
                    EstimatedUsd: 0,
                    BudgetUnitsConsumed: 0),
                DeadLetter: new PipelineDeadLetterProjection(
                    Count: _deadLetters.Count,
                    Recent: _deadLetters.Take(25).ToArray()));
        }
    }

    private bool TryGetReusableAsset(string cacheKey, out AssetState assetState)
    {
        assetState = null!;
        if (!_assetIdsByCacheKey.TryGetValue(cacheKey, out var assetId) ||
            !_assets.TryGetValue(assetId, out var existing))
        {
            return false;
        }

        if (ExpireIfNeeded(existing, DateTimeOffset.UtcNow))
        {
            return false;
        }

        assetState = existing;
        return true;
    }

    private void TrackMutationReplay(string assetId, AssetLifecycleMutationRequest request)
    {
        var fingerprint = BuildMutationFingerprint(assetId, request);
        if (!_mutationFingerprints.TryAdd(fingerprint, 0))
        {
            Interlocked.Increment(ref _replayMutations);
            _lastReplayAtUtc = DateTimeOffset.UtcNow;
        }
    }

    private static string BuildMutationFingerprint(string assetId, AssetLifecycleMutationRequest request) =>
        $"{assetId}:{request.ApprovalState?.ToString() ?? "none"}:{request.Pin?.ToString() ?? "none"}:{request.Persist?.ToString() ?? "none"}:{request.Reason ?? string.Empty}";

    private void EnqueueDeadLetter(string itemId, string reason, string? fingerprint = null)
    {
        _deadLetters.Enqueue(new PipelineDeadLetterEntry(
            ItemId: itemId,
            Reason: reason,
            OccurredAtUtc: DateTimeOffset.UtcNow,
            Fingerprint: fingerprint));
        while (_deadLetters.Count > 200 && _deadLetters.TryDequeue(out _))
        {
        }
    }

    private static int ToInt(long value) => value > int.MaxValue ? int.MaxValue : (int)value;

    private bool ExpireIfNeeded(AssetState assetState, DateTimeOffset now)
    {
        if (assetState.RetentionState == AssetRetentionState.Expired)
        {
            return true;
        }

        if (assetState.RetentionState is AssetRetentionState.Persisted or AssetRetentionState.Pinned)
        {
            return false;
        }

        var expiresAtUtc = GetExpiresAtUtc(assetState);
        if (expiresAtUtc is null || expiresAtUtc > now)
        {
            return false;
        }

        assetState.RetentionState = AssetRetentionState.Expired;
        assetState.IsPinned = false;
        _assetIdsByCacheKey.TryRemove(assetState.CacheKey, out _);
        return true;
    }

    private AssetCatalogItem ToCatalogItem(AssetState assetState) =>
        new(
            AssetId: assetState.AssetId,
            Url: assetState.Url,
            Category: assetState.Category,
            Version: assetState.Version,
            Source: assetState.Source,
            Policy: assetState.Policy,
            CreatedAtUtc: assetState.CreatedAtUtc,
            ExpiresAtUtc: GetExpiresAtUtc(assetState),
            StorageKey: assetState.StorageKey,
            StorageClass: assetState.StorageClass,
            ApprovalState: assetState.ApprovalState,
            RetentionState: assetState.RetentionState,
            IsPinned: assetState.IsPinned,
            CacheHitCount: assetState.CacheHitCount,
            LastAccessedAtUtc: assetState.LastAccessedAtUtc,
            ApprovedAtUtc: assetState.ApprovedAtUtc);

    private AssetRenderResult ToRenderResult(AssetState assetState, bool cacheReused) =>
        new(
            AssetId: assetState.AssetId,
            Url: assetState.Url,
            Policy: assetState.Policy,
            ApprovalState: assetState.ApprovalState,
            RetentionState: assetState.RetentionState,
            StorageKey: assetState.StorageKey,
            StorageClass: assetState.StorageClass,
            CacheReused: cacheReused);

    private AssetLifecyclePolicy NormalizePolicy(string content, AssetLifecyclePolicy? policy)
    {
        var normalized = policy ?? new AssetLifecyclePolicy(_defaultCacheTtl, LongTermCache: false, MaxBytes: Math.Max(0, Encoding.UTF8.GetByteCount(content)) * 2);
        var maxBytes = normalized.MaxBytes > 0
            ? normalized.MaxBytes
            : Math.Max(4096, Encoding.UTF8.GetByteCount(content) * 2);
        var cacheTtl = normalized.CacheTtl < TimeSpan.Zero ? TimeSpan.Zero : normalized.CacheTtl;

        return normalized with
        {
            CacheTtl = cacheTtl,
            MaxBytes = maxBytes
        };
    }

    private static AssetRetentionState DetermineRetentionState(
        AssetLifecyclePolicy policy,
        AssetApprovalState approvalState,
        bool isPinned,
        bool explicitPersist)
    {
        if (approvalState == AssetApprovalState.Rejected)
        {
            return AssetRetentionState.Rejected;
        }

        if (isPinned)
        {
            return AssetRetentionState.Pinned;
        }

        if (approvalState == AssetApprovalState.Approved &&
            (explicitPersist || policy.PersistOnApproval || policy.LongTermCache))
        {
            return AssetRetentionState.Persisted;
        }

        if (policy.RequiresApproval && approvalState != AssetApprovalState.Approved)
        {
            return AssetRetentionState.ApprovalPending;
        }

        return AssetRetentionState.CacheOnly;
    }

    private static AssetStorageClass DetermineStorageClass(AssetLifecyclePolicy policy, AssetRetentionState retentionState)
    {
        if (retentionState is AssetRetentionState.Persisted or AssetRetentionState.Pinned)
        {
            return AssetStorageClass.LongTermObjectStorage;
        }

        return policy.StorageClass;
    }

    private static DateTimeOffset? GetExpiresAtUtc(AssetState assetState)
    {
        if (assetState.RetentionState is AssetRetentionState.Persisted or AssetRetentionState.Pinned or AssetRetentionState.Expired)
        {
            return null;
        }

        if (assetState.Policy.CacheTtl <= TimeSpan.Zero)
        {
            return null;
        }

        return assetState.CreatedAtUtc + assetState.Policy.CacheTtl;
    }

    private static string BuildCacheKey(string category, string source, string content, AssetLifecyclePolicy policy)
    {
        var input = string.Join(
            "\n",
            category,
            source,
            content,
            policy.CacheTtl.TotalSeconds,
            policy.LongTermCache,
            policy.MaxBytes,
            policy.RequiresApproval,
            policy.PersistOnApproval,
            policy.StorageClass,
            policy.AllowPersistentPinning);
        return ComputeHash(input);
    }

    private static string BuildSignedAssetUrl(string assetId, string version)
    {
        var signature = ComputeHash($"{assetId}:{version}")[..16];
        return $"/asset-store/{assetId}?v={version}&sig={signature}";
    }

    private static string BuildStorageKey(AssetStorageClass storageClass, string category, string assetId, string version)
    {
        var tier = storageClass == AssetStorageClass.LongTermObjectStorage ? "archive" : "active";
        var normalizedCategory = category.Replace(' ', '-').Replace('/', '-').ToLowerInvariant();
        return $"r2://creative-assets/{tier}/{normalizedCategory}/{assetId}/{version}";
    }

    private static string ComputeHash(string value)
    {
        var bytes = SHA256.HashData(Encoding.UTF8.GetBytes(value));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }
}
