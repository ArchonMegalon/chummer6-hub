using Chummer.Run.Contracts.Registry;
using Chummer.Run.Contracts.Observability;
using System.Collections.Concurrent;

namespace Chummer.Run.Registry.Services;

public interface IHubArtifactStore
{
    HubArtifactMetadata UpsertArtifact(HubArtifactCreateRequest request);
    RuntimeBundleIssueResponse IssueRuntimeBundle(RuntimeBundleIssueRequest request);
    HubArtifactMetadata? GetArtifact(string id);
    RuntimeBundleArtifactProjection? GetRuntimeBundleArtifact(string artifactId);
    IReadOnlyList<HubArtifactMetadata> Search(string? query, HubArtifactKind? kind, HubArtifactState? state, int page, int pageSize);
    int SearchCount(string? query, HubArtifactKind? kind, HubArtifactState? state);
    RegistryProjectionResponse? GetProjection(string id);
    IReadOnlyList<RegistryProjectionResponse> SearchProjections(string? query, HubArtifactKind? kind, HubArtifactState? state, int page, int pageSize);
    int SearchProjectionCount(string? query, HubArtifactKind? kind, HubArtifactState? state);
    HubArtifactInstallProjection? GetInstallProjection(string id);
    RuntimeBundleHeadProjection? GetRuntimeBundleHead(string sessionId, string sceneId, RuntimeBundleHeadKind head);
    RuntimeBundleHeadListResponse GetRuntimeBundleHeads(string sessionId, string sceneId);
    HubArtifactStateResponse ChangeState(string id, HubArtifactStateChangeRequest request);
    IReadOnlyList<HubArtifactMetadata> ListByState(HubArtifactState state);
    HubArtifactDeleteAttemptResponse AttemptDelete(string id);
    HubArtifactIdentifier RegisterInstall(string id, HubInstallEvent installEvent);
    HubReviewListResponse AddReview(string artifactId, HubReviewRequest request);
    HubArtifactStoreBackupPackage ExportBackup();
    void RestoreBackup(HubArtifactStoreBackupPackage backup);
    PipelineProjection GetRegistryPipelineProjection();
}

public sealed class HubArtifactStore : IHubArtifactStore
{
    private sealed class HubArtifactInternal
    {
        public required string Id { get; init; }
        public required string Name { get; set; }
        public required HubArtifactKind Kind { get; set; }
        public required string Version { get; set; }
        public required string RulesetId { get; set; }
        public required string Visibility { get; set; }
        public required string TrustTier { get; set; }
        public HubArtifactState State { get; set; }
        public string? Owner { get; set; }
        public string? PublisherId { get; set; }
        public string? Summary { get; set; }
        public string? Description { get; set; }
        public string? RuntimeFingerprint { get; set; }
        public string? StateReason { get; set; }
        public string? SupersededByArtifactId { get; set; }
        public required DateTimeOffset CreatedAtUtc { get; init; }
        public DateTimeOffset UpdatedAtUtc { get; set; }
        public DateTimeOffset? LifecycleChangedAtUtc { get; set; }
        public int InstallCount { get; set; }
        public int ActiveRuntimeRefCount { get; set; }
        public DateTimeOffset LastInstalledAtUtc { get; set; }
        public List<double> ReviewScores { get; } = new();
    }

    private sealed class RuntimeBundleArtifactInternal
    {
        public required string ArtifactId { get; init; }
        public required string BundleFamilyId { get; init; }
        public required string SessionId { get; init; }
        public required string SceneId { get; init; }
        public required RuntimeBundleHeadKind Head { get; init; }
        public required string SourceBundleVersion { get; init; }
        public required string ProjectionFingerprint { get; init; }
        public required int ProjectionVersion { get; init; }
        public required bool Ready { get; init; }
        public required bool OfflineCapable { get; init; }
        public required string CollaborationMode { get; init; }
        public required string[] InvalidationSignals { get; init; }
        public required string[] IncludedEventTypes { get; init; }
        public required string[] SupportedExchangeFormats { get; init; }
        public string? RequestedBy { get; init; }
        public required DateTimeOffset IssuedAtUtc { get; init; }
        public string? PreviousArtifactId { get; set; }
    }

    private sealed class RuntimeBundleHeadInternal
    {
        public required string BundleFamilyId { get; init; }
        public required string SessionId { get; init; }
        public required string SceneId { get; init; }
        public required RuntimeBundleHeadKind Head { get; init; }
        public required string CurrentArtifactId { get; set; }
        public required string CurrentVersion { get; set; }
        public required string SourceBundleVersion { get; set; }
        public required string ProjectionFingerprint { get; set; }
        public required int ProjectionVersion { get; set; }
        public required bool Ready { get; set; }
        public required bool OfflineCapable { get; set; }
        public required string CollaborationMode { get; set; }
        public required string[] SupportedExchangeFormats { get; set; }
        public required DateTimeOffset IssuedAtUtc { get; set; }
        public string? PreviousArtifactId { get; set; }
    }

    private readonly ConcurrentDictionary<string, HubArtifactInternal> _artifacts = new(StringComparer.OrdinalIgnoreCase);
    private readonly ConcurrentDictionary<string, RuntimeBundleArtifactInternal> _runtimeBundleArtifacts = new(StringComparer.OrdinalIgnoreCase);
    private readonly ConcurrentDictionary<string, RuntimeBundleHeadInternal> _runtimeBundleHeads = new(StringComparer.OrdinalIgnoreCase);
    private readonly ConcurrentQueue<PipelineDeadLetterEntry> _deadLetters = new();
    private readonly object _sync = new();
    private long _upsertCount;
    private long _runtimeIssueCount;
    private long _runtimeIssueIdempotentCount;
    private DateTimeOffset? _lastRuntimeIssueReplayAtUtc;
    private long _installCount;
    private long _reviewCount;

    public HubArtifactMetadata UpsertArtifact(HubArtifactCreateRequest request)
    {
        var rulesetId = NormalizeRulesetId(request.RulesetId);
        var visibility = NormalizeVisibility(request.Visibility);
        var trustTier = NormalizeTrustTier(request.TrustTier);
        var metadata = CreateArtifact(
            request.Name,
            request.Kind,
            request.Version,
            rulesetId,
            visibility,
            trustTier,
            request.ResolveOwnerId(),
            request.PublisherId,
            request.Summary,
            request.Description,
            request.RuntimeFingerprint,
            request.StateReason);
        _artifacts[metadata.Id] = metadata;
        Interlocked.Increment(ref _upsertCount);
        return ToMetadata(metadata);
    }

    public RuntimeBundleIssueResponse IssueRuntimeBundle(RuntimeBundleIssueRequest request)
    {
        var sessionId = request.SessionId.Trim();
        var sceneId = request.SceneId.Trim();
        var sourceBundleVersion = request.SourceBundleVersion.Trim();
        var projectionFingerprint = request.ProjectionFingerprint.Trim();
        var collaborationMode = request.CollaborationMode.Trim();
        var rulesetId = NormalizeRulesetId(request.RulesetId);
        var visibility = NormalizeVisibility(request.Visibility);
        var trustTier = NormalizeTrustTier(request.TrustTier);
        var bundleFamilyId = ComposeRuntimeBundleFamilyId(sessionId, sceneId);
        var headKey = ComposeRuntimeBundleHeadKey(bundleFamilyId, request.Head);

        lock (_sync)
        {
            if (_runtimeBundleHeads.TryGetValue(headKey, out var existingHead)
                && string.Equals(existingHead.SourceBundleVersion, sourceBundleVersion, StringComparison.Ordinal)
                && string.Equals(existingHead.ProjectionFingerprint, projectionFingerprint, StringComparison.Ordinal)
                && existingHead.ProjectionVersion == request.ProjectionVersion
                && existingHead.Ready == request.Ready
                && existingHead.OfflineCapable == request.OfflineCapable
                && string.Equals(existingHead.CollaborationMode, collaborationMode, StringComparison.Ordinal))
            {
                Interlocked.Increment(ref _runtimeIssueIdempotentCount);
                _lastRuntimeIssueReplayAtUtc = DateTimeOffset.UtcNow;
                var existingMetadata = _artifacts[existingHead.CurrentArtifactId];
                var existingProjection = _runtimeBundleArtifacts[existingHead.CurrentArtifactId];
                return new RuntimeBundleIssueResponse(
                    Artifact: ToMetadata(existingMetadata),
                    Projection: ToRuntimeBundleArtifactProjection(existingProjection),
                    Head: ToRuntimeBundleHeadProjection(existingHead),
                    CreatedNewArtifact: false);
            }

            string? previousArtifactId = null;
            if (_runtimeBundleHeads.TryGetValue(headKey, out var currentHead))
            {
                previousArtifactId = currentHead.CurrentArtifactId;
            }

            var version = ComposeRuntimeBundleArtifactVersion(sourceBundleVersion, request.Head);
            var name = $"{sessionId}/{sceneId} {request.Head} runtime bundle";
            var summary = string.IsNullOrWhiteSpace(request.Summary)
                ? $"Immutable {request.Head.ToString().ToLowerInvariant()} runtime bundle for session '{sessionId}' scene '{sceneId}'."
                : request.Summary.Trim();

            var artifact = CreateArtifact(
                name,
                HubArtifactKind.RuntimeBundle,
                version,
                rulesetId,
                visibility,
                trustTier,
                request.ResolveOwnerId(),
                request.PublisherId,
                summary,
                request.Description,
                projectionFingerprint,
                stateReason: null);
            _artifacts[artifact.Id] = artifact;

            var projection = new RuntimeBundleArtifactInternal
            {
                ArtifactId = artifact.Id,
                BundleFamilyId = bundleFamilyId,
                SessionId = sessionId,
                SceneId = sceneId,
                Head = request.Head,
                SourceBundleVersion = sourceBundleVersion,
                ProjectionFingerprint = projectionFingerprint,
                ProjectionVersion = request.ProjectionVersion,
                Ready = request.Ready,
                OfflineCapable = request.OfflineCapable,
                CollaborationMode = collaborationMode,
                InvalidationSignals = NormalizeList(request.InvalidationSignals),
                IncludedEventTypes = NormalizeList(request.IncludedEventTypes),
                SupportedExchangeFormats = NormalizeList(request.SupportedExchangeFormats),
                RequestedBy = NormalizeOptional(request.RequestedBy),
                IssuedAtUtc = artifact.CreatedAtUtc,
                PreviousArtifactId = previousArtifactId
            };
            _runtimeBundleArtifacts[artifact.Id] = projection;

            if (previousArtifactId is not null && _artifacts.TryGetValue(previousArtifactId, out var previousArtifact))
            {
                previousArtifact.State = HubArtifactState.Superseded;
                previousArtifact.StateReason = $"Superseded by {artifact.Id} for {request.Head} head issuance.";
                previousArtifact.SupersededByArtifactId = artifact.Id;
                previousArtifact.UpdatedAtUtc = artifact.CreatedAtUtc;
                previousArtifact.LifecycleChangedAtUtc = artifact.CreatedAtUtc;
            }

            var nextHead = new RuntimeBundleHeadInternal
            {
                BundleFamilyId = bundleFamilyId,
                SessionId = sessionId,
                SceneId = sceneId,
                Head = request.Head,
                CurrentArtifactId = artifact.Id,
                CurrentVersion = version,
                SourceBundleVersion = sourceBundleVersion,
                ProjectionFingerprint = projectionFingerprint,
                ProjectionVersion = request.ProjectionVersion,
                Ready = request.Ready,
                OfflineCapable = request.OfflineCapable,
                CollaborationMode = collaborationMode,
                SupportedExchangeFormats = projection.SupportedExchangeFormats,
                IssuedAtUtc = projection.IssuedAtUtc,
                PreviousArtifactId = previousArtifactId
            };
            _runtimeBundleHeads[headKey] = nextHead;
            Interlocked.Increment(ref _runtimeIssueCount);

            return new RuntimeBundleIssueResponse(
                Artifact: ToMetadata(artifact),
                Projection: ToRuntimeBundleArtifactProjection(projection),
                Head: ToRuntimeBundleHeadProjection(nextHead),
                CreatedNewArtifact: true);
        }
    }

    public HubArtifactMetadata? GetArtifact(string id)
    {
        return _artifacts.TryGetValue(id, out var metadata) ? ToMetadata(metadata) : null;
    }

    public RuntimeBundleArtifactProjection? GetRuntimeBundleArtifact(string artifactId)
    {
        return _runtimeBundleArtifacts.TryGetValue(artifactId, out var artifact)
            ? ToRuntimeBundleArtifactProjection(artifact)
            : null;
    }

    public IReadOnlyList<HubArtifactMetadata> Search(string? query, HubArtifactKind? kind, HubArtifactState? state, int page, int pageSize) =>
        FilterArtifacts(query, kind, state)
            .Select(ToMetadata)
            .Skip(Math.Max(0, (page - 1) * pageSize))
            .Take(Math.Max(1, pageSize))
            .ToList();

    public int SearchCount(string? query, HubArtifactKind? kind, HubArtifactState? state) =>
        FilterArtifacts(query, kind, state).Count();

    public RegistryProjectionResponse? GetProjection(string id)
    {
        return _artifacts.TryGetValue(id, out var entry) ? ToProjection(entry) : null;
    }

    public IReadOnlyList<RegistryProjectionResponse> SearchProjections(string? query, HubArtifactKind? kind, HubArtifactState? state, int page, int pageSize) =>
        FilterArtifacts(query, kind, state)
            .Select(ToProjection)
            .Skip(Math.Max(0, (page - 1) * pageSize))
            .Take(Math.Max(1, pageSize))
            .ToList();

    public int SearchProjectionCount(string? query, HubArtifactKind? kind, HubArtifactState? state) =>
        SearchCount(query, kind, state);

    public HubArtifactInstallProjection? GetInstallProjection(string id)
    {
        return _artifacts.TryGetValue(id, out var entry) ? ToInstallProjection(entry) : null;
    }

    public RuntimeBundleHeadProjection? GetRuntimeBundleHead(string sessionId, string sceneId, RuntimeBundleHeadKind head)
    {
        var familyId = ComposeRuntimeBundleFamilyId(sessionId.Trim(), sceneId.Trim());
        var key = ComposeRuntimeBundleHeadKey(familyId, head);
        return _runtimeBundleHeads.TryGetValue(key, out var runtimeHead)
            ? ToRuntimeBundleHeadProjection(runtimeHead)
            : null;
    }

    public RuntimeBundleHeadListResponse GetRuntimeBundleHeads(string sessionId, string sceneId)
    {
        var normalizedSessionId = sessionId.Trim();
        var normalizedSceneId = sceneId.Trim();
        var familyId = ComposeRuntimeBundleFamilyId(normalizedSessionId, normalizedSceneId);
        var heads = _runtimeBundleHeads.Values
            .Where(head => string.Equals(head.BundleFamilyId, familyId, StringComparison.Ordinal))
            .OrderBy(head => head.Head)
            .Select(ToRuntimeBundleHeadProjection)
            .ToList();

        return new RuntimeBundleHeadListResponse(
            BundleFamilyId: familyId,
            SessionId: normalizedSessionId,
            SceneId: normalizedSceneId,
            Heads: heads);
    }

    public HubArtifactStateResponse ChangeState(string id, HubArtifactStateChangeRequest request)
    {
        if (!_artifacts.TryGetValue(id, out var entry))
        {
            return new HubArtifactStateResponse(
                Id: id,
                Kind: HubArtifactKind.RulePack,
                Version: "0.0.0",
                RulesetId: "sr5",
                State: HubArtifactState.Active,
                StateReason: $"Artifact '{id}' was not found.",
                SupersededByArtifactId: null,
                ChangedAtUtc: DateTimeOffset.UtcNow);
        }

        lock (_sync)
        {
            if (!IsTransitionAllowed(entry.State, request.TargetState))
            {
                return new HubArtifactStateResponse(
                    Id: entry.Id,
                    Kind: entry.Kind,
                    Version: entry.Version,
                    RulesetId: entry.RulesetId,
                    State: entry.State,
                    StateReason: $"Transition from {entry.State} to {request.TargetState} is not allowed.",
                    SupersededByArtifactId: entry.SupersededByArtifactId,
                    ChangedAtUtc: entry.LifecycleChangedAtUtc ?? entry.UpdatedAtUtc);
            }

            if (request.TargetState == HubArtifactState.Superseded && string.IsNullOrWhiteSpace(request.SupersededByArtifactId))
            {
                return new HubArtifactStateResponse(
                    Id: entry.Id,
                    Kind: entry.Kind,
                    Version: entry.Version,
                    RulesetId: entry.RulesetId,
                    State: entry.State,
                    StateReason: "Superseded state requires a replacement artifact id.",
                    SupersededByArtifactId: entry.SupersededByArtifactId,
                    ChangedAtUtc: entry.LifecycleChangedAtUtc ?? entry.UpdatedAtUtc);
            }

            entry.State = request.TargetState;
            entry.StateReason = request.Reason;
            entry.SupersededByArtifactId = request.TargetState == HubArtifactState.Superseded
                ? request.SupersededByArtifactId?.Trim()
                : entry.SupersededByArtifactId;
            entry.UpdatedAtUtc = DateTimeOffset.UtcNow;
            entry.LifecycleChangedAtUtc = entry.UpdatedAtUtc;
        }

        return new HubArtifactStateResponse(
            Id: entry.Id,
            Kind: entry.Kind,
            Version: entry.Version,
            RulesetId: entry.RulesetId,
            State: entry.State,
            StateReason: entry.StateReason,
            SupersededByArtifactId: entry.SupersededByArtifactId,
            ChangedAtUtc: entry.LifecycleChangedAtUtc ?? entry.UpdatedAtUtc);
    }

    public IReadOnlyList<HubArtifactMetadata> ListByState(HubArtifactState state) =>
        _artifacts.Values
            .Where(item => item.State == state)
            .OrderBy(item => item.Name, StringComparer.OrdinalIgnoreCase)
            .Select(ToMetadata)
            .ToList();

    public HubArtifactDeleteAttemptResponse AttemptDelete(string id)
    {
        if (!_artifacts.TryGetValue(id, out var entry))
        {
            EnqueueDeadLetter(id, "artifact-not-found");
            return new HubArtifactDeleteAttemptResponse(
                Id: id,
                Accepted: false,
                Message: "Artifact not found.",
                State: HubArtifactState.Active);
        }

        EnqueueDeadLetter(id, "hard-delete-disabled");
        return new HubArtifactDeleteAttemptResponse(
            Id: id,
            Accepted: false,
            Message: "Hard-delete is disabled for Hub artifacts. Use delist, deprecate, or supersede lifecycle states instead.",
            State: entry.State);
    }

    public HubArtifactIdentifier RegisterInstall(string id, HubInstallEvent installEvent)
    {
        if (!_artifacts.TryGetValue(id, out var entry))
        {
            entry = new HubArtifactInternal
            {
                Id = id,
                Name = "Unknown",
                Kind = HubArtifactKind.RulePack,
                Version = "0.0.0",
                RulesetId = "sr5",
                Visibility = ArtifactVisibilityModes.Shared,
                TrustTier = ArtifactTrustTiers.Curated,
                State = HubArtifactState.Active,
                CreatedAtUtc = DateTimeOffset.UtcNow,
                UpdatedAtUtc = DateTimeOffset.UtcNow,
                LastInstalledAtUtc = installEvent.InstalledAtUtc
            };
            _artifacts[id] = entry;
        }

        lock (_sync)
        {
            entry.InstallCount++;
            Interlocked.Increment(ref _installCount);
            if (installEvent.ActiveRuntimeRef)
            {
                entry.ActiveRuntimeRefCount++;
            }

            if (installEvent.InstalledAtUtc > entry.LastInstalledAtUtc)
            {
                entry.LastInstalledAtUtc = installEvent.InstalledAtUtc;
            }

            entry.UpdatedAtUtc = DateTimeOffset.UtcNow;
        }

        return new HubArtifactIdentifier(
            Id: id,
            Kind: entry.Kind,
            Version: entry.Version);
    }

    public HubReviewListResponse AddReview(string artifactId, HubReviewRequest request)
    {
        if (!_artifacts.TryGetValue(artifactId, out var entry))
        {
            EnqueueDeadLetter(artifactId, "review-target-not-found");
            return new HubReviewListResponse(
                ArtifactId: artifactId,
                AverageScore: 0,
                ReviewCount: 0,
                Reviews: Array.Empty<HubReviewResponse>());
        }

        if (request.Score is >= 0 and <= 10)
        {
            lock (_sync)
            {
                entry.ReviewScores.Add(request.Score);
                entry.UpdatedAtUtc = DateTimeOffset.UtcNow;
            }
            Interlocked.Increment(ref _reviewCount);
        }

        double average;
        int reviewCount;
        lock (_sync)
        {
            reviewCount = entry.ReviewScores.Count;
            average = reviewCount == 0 ? 0 : entry.ReviewScores.Average();
        }

        var reviews = new List<HubReviewResponse>
        {
            new(
                ArtifactId: artifactId,
                AverageScore: average,
                ReviewCount: reviewCount)
        };
        return new HubReviewListResponse(
            ArtifactId: artifactId,
            AverageScore: average,
            ReviewCount: reviewCount,
            Reviews: reviews);
    }

    public PipelineProjection GetRegistryPipelineProjection()
    {
        var active = _artifacts.Values.Count(item => item.State == HubArtifactState.Active);
        var superseded = _artifacts.Values.Count(item => item.State == HubArtifactState.Superseded);
        var banned = _artifacts.Values.Count(item => item.State == HubArtifactState.BannedButRetained);
        return new PipelineProjection(
            Pipeline: "registry",
            Observability: new PipelineObservabilityProjection(
                ProcessedCount: ToInt(_upsertCount + _runtimeIssueCount + _installCount + _reviewCount),
                ActiveCount: active,
                SucceededCount: _runtimeBundleHeads.Count,
                FailedCount: banned,
                DuplicateCount: superseded,
                IgnoredCount: 0),
            Idempotency: new PipelineIdempotencyProjection(
                TrackedKeys: _runtimeBundleHeads.Count,
                ReplayCount: ToInt(_runtimeIssueIdempotentCount),
                LastReplayAtUtc: _lastRuntimeIssueReplayAtUtc),
            Cost: new PipelineCostProjection(
                EstimatedUsd: 0,
                BudgetUnitsConsumed: 0),
            DeadLetter: new PipelineDeadLetterProjection(
                Count: _deadLetters.Count,
                Recent: _deadLetters.Take(25).ToArray()));
    }

    public HubArtifactStoreBackupPackage ExportBackup()
    {
        lock (_sync)
        {
            var artifacts = _artifacts.Values
                .OrderBy(item => item.Id, StringComparer.OrdinalIgnoreCase)
                .Select(ToBackupArtifact)
                .ToArray();
            var runtimeBundleArtifacts = _runtimeBundleArtifacts.Values
                .OrderBy(item => item.ArtifactId, StringComparer.OrdinalIgnoreCase)
                .Select(ToBackupRuntimeBundleArtifact)
                .ToArray();
            var runtimeBundleHeads = _runtimeBundleHeads.Values
                .OrderBy(item => item.BundleFamilyId, StringComparer.Ordinal)
                .ThenBy(item => item.Head)
                .Select(ToBackupRuntimeBundleHead)
                .ToArray();

            return new HubArtifactStoreBackupPackage(
                ExportedAtUtc: DateTimeOffset.UtcNow,
                Artifacts: artifacts,
                RuntimeBundleArtifacts: runtimeBundleArtifacts,
                RuntimeBundleHeads: runtimeBundleHeads,
                DeadLetters: _deadLetters.ToArray(),
                UpsertCount: Interlocked.Read(ref _upsertCount),
                RuntimeIssueCount: Interlocked.Read(ref _runtimeIssueCount),
                RuntimeIssueIdempotentCount: Interlocked.Read(ref _runtimeIssueIdempotentCount),
                LastRuntimeIssueReplayAtUtc: _lastRuntimeIssueReplayAtUtc,
                InstallCount: Interlocked.Read(ref _installCount),
                ReviewCount: Interlocked.Read(ref _reviewCount));
        }
    }

    public void RestoreBackup(HubArtifactStoreBackupPackage backup)
    {
        if (!string.Equals(backup.ContractFamily, "hub_state_backup_v1", StringComparison.Ordinal))
        {
            throw new InvalidOperationException("Hub state backups must use contract family 'hub_state_backup_v1'.");
        }

        lock (_sync)
        {
            _artifacts.Clear();
            foreach (var snapshot in backup.Artifacts)
            {
                _artifacts[snapshot.Id] = FromBackupArtifact(snapshot);
            }

            _runtimeBundleArtifacts.Clear();
            foreach (var snapshot in backup.RuntimeBundleArtifacts)
            {
                _runtimeBundleArtifacts[snapshot.ArtifactId] = FromBackupRuntimeBundleArtifact(snapshot);
            }

            _runtimeBundleHeads.Clear();
            foreach (var snapshot in backup.RuntimeBundleHeads)
            {
                var key = ComposeRuntimeBundleHeadKey(snapshot.BundleFamilyId, ToLiveRuntimeBundleHeadKind(snapshot.Head));
                _runtimeBundleHeads[key] = FromBackupRuntimeBundleHead(snapshot);
            }

            while (_deadLetters.TryDequeue(out _))
            {
            }
            foreach (var deadLetter in backup.DeadLetters)
            {
                _deadLetters.Enqueue(deadLetter);
            }
            while (_deadLetters.Count > 200 && _deadLetters.TryDequeue(out _))
            {
            }

            Interlocked.Exchange(ref _upsertCount, backup.UpsertCount);
            Interlocked.Exchange(ref _runtimeIssueCount, backup.RuntimeIssueCount);
            Interlocked.Exchange(ref _runtimeIssueIdempotentCount, backup.RuntimeIssueIdempotentCount);
            _lastRuntimeIssueReplayAtUtc = backup.LastRuntimeIssueReplayAtUtc;
            Interlocked.Exchange(ref _installCount, backup.InstallCount);
            Interlocked.Exchange(ref _reviewCount, backup.ReviewCount);
        }
    }

    private IEnumerable<HubArtifactInternal> FilterArtifacts(string? query, HubArtifactKind? kind, HubArtifactState? state)
    {
        var normalized = NormalizeQuery(query);
        return _artifacts.Values
            .Where(item =>
                (string.IsNullOrWhiteSpace(normalized)
                 || item.Id.Contains(normalized, StringComparison.OrdinalIgnoreCase)
                 || item.Name.Contains(normalized, StringComparison.OrdinalIgnoreCase))
                && (kind is null || item.Kind == kind.Value)
                && (state is null || item.State == state.Value))
            .OrderBy(item => item.Name, StringComparer.OrdinalIgnoreCase)
            .ThenBy(item => item.Version, StringComparer.OrdinalIgnoreCase);
    }

    private static string NormalizeQuery(string? query) => (query ?? string.Empty).Trim();

    private void EnqueueDeadLetter(string itemId, string reason)
    {
        _deadLetters.Enqueue(new PipelineDeadLetterEntry(
            ItemId: itemId,
            Reason: reason,
            OccurredAtUtc: DateTimeOffset.UtcNow));
        while (_deadLetters.Count > 200 && _deadLetters.TryDequeue(out _))
        {
        }
    }

    private static string? NormalizeOptional(string? value) =>
        string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string[] NormalizeList(IReadOnlyList<string> values) =>
        values
            .Where(value => !string.IsNullOrWhiteSpace(value))
            .Select(value => value.Trim())
            .Distinct(StringComparer.Ordinal)
            .OrderBy(value => value, StringComparer.Ordinal)
            .ToArray();

    private static string ComposeRuntimeBundleFamilyId(string sessionId, string sceneId) =>
        $"runtime-family:{sessionId}:{sceneId}";

    private static string ComposeRuntimeBundleHeadKey(string bundleFamilyId, RuntimeBundleHeadKind head) =>
        $"{bundleFamilyId}::{head}";

    private static string ComposeRuntimeBundleArtifactVersion(string sourceBundleVersion, RuntimeBundleHeadKind head) =>
        $"{sourceBundleVersion}-{head.ToString().ToLowerInvariant()}";

    private static Chummer.Run.Contracts.Registry.HubArtifactKind ToLegacyHubArtifactKind(HubArtifactKind value) =>
        Enum.Parse<Chummer.Run.Contracts.Registry.HubArtifactKind>(value.ToString());

    private static HubArtifactKind ToLiveHubArtifactKind(Chummer.Run.Contracts.Registry.HubArtifactKind value) =>
        Enum.Parse<HubArtifactKind>(value.ToString());

    private static Chummer.Run.Contracts.Registry.HubArtifactState ToLegacyHubArtifactState(HubArtifactState value) =>
        Enum.Parse<Chummer.Run.Contracts.Registry.HubArtifactState>(value.ToString());

    private static HubArtifactState ToLiveHubArtifactState(Chummer.Run.Contracts.Registry.HubArtifactState value) =>
        Enum.Parse<HubArtifactState>(value.ToString());

    private static Chummer.Run.Contracts.Registry.RuntimeBundleHeadKind ToLegacyRuntimeBundleHeadKind(RuntimeBundleHeadKind value) =>
        Enum.Parse<Chummer.Run.Contracts.Registry.RuntimeBundleHeadKind>(value.ToString());

    private static RuntimeBundleHeadKind ToLiveRuntimeBundleHeadKind(Chummer.Run.Contracts.Registry.RuntimeBundleHeadKind value) =>
        Enum.Parse<RuntimeBundleHeadKind>(value.ToString());

    private static bool AcceptingNewInstalls(HubArtifactInternal artifact) =>
        artifact.State == HubArtifactState.Active;

    private static bool IsTransitionAllowed(HubArtifactState current, HubArtifactState target)
    {
        if (current == target)
        {
            return true;
        }

        return current switch
        {
            HubArtifactState.Active => target is HubArtifactState.Delisted or HubArtifactState.Deprecated or HubArtifactState.Superseded or HubArtifactState.BannedButRetained,
            HubArtifactState.Delisted => target is HubArtifactState.Deprecated or HubArtifactState.Superseded or HubArtifactState.BannedButRetained,
            HubArtifactState.Deprecated => target is HubArtifactState.Delisted or HubArtifactState.Superseded or HubArtifactState.BannedButRetained,
            HubArtifactState.Superseded => target is HubArtifactState.Delisted or HubArtifactState.Deprecated or HubArtifactState.BannedButRetained,
            HubArtifactState.BannedButRetained => false,
            _ => false
        };
    }

    private HubArtifactMetadata ToMetadata(HubArtifactInternal internalState)
    {
        int reviewCount;
        double averageScore;
        lock (_sync)
        {
            reviewCount = internalState.ReviewScores.Count;
            averageScore = reviewCount == 0 ? 0 : internalState.ReviewScores.Average();
        }

        return new HubArtifactMetadata(
            Id: internalState.Id,
            Name: internalState.Name,
            Kind: internalState.Kind,
            Version: internalState.Version,
            RulesetId: internalState.RulesetId,
            State: internalState.State,
            Visibility: internalState.Visibility,
            TrustTier: internalState.TrustTier,
            OwnerId: internalState.Owner,
            PublisherId: internalState.PublisherId,
            Summary: internalState.Summary,
            Description: internalState.Description,
            RuntimeFingerprint: internalState.RuntimeFingerprint,
            StateReason: internalState.StateReason,
            SupersededByArtifactId: internalState.SupersededByArtifactId,
            ImmutableRetentionRequired: true,
            InstallCount: internalState.InstallCount,
            ActiveRuntimeRefCount: internalState.ActiveRuntimeRefCount,
            ReviewCount: reviewCount,
            AverageReviewScore: averageScore,
            CreatedAtUtc: internalState.CreatedAtUtc,
            UpdatedAtUtc: internalState.UpdatedAtUtc,
            LifecycleChangedAtUtc: internalState.LifecycleChangedAtUtc);
    }

    private static HubArtifactStoreArtifactSnapshot ToBackupArtifact(HubArtifactInternal internalState) =>
        new(
            Id: internalState.Id,
            Name: internalState.Name,
            Kind: ToLegacyHubArtifactKind(internalState.Kind),
            Version: internalState.Version,
            RulesetId: internalState.RulesetId,
            Visibility: internalState.Visibility,
            TrustTier: internalState.TrustTier,
            State: ToLegacyHubArtifactState(internalState.State),
            Owner: internalState.Owner,
            PublisherId: internalState.PublisherId,
            Summary: internalState.Summary,
            Description: internalState.Description,
            RuntimeFingerprint: internalState.RuntimeFingerprint,
            StateReason: internalState.StateReason,
            SupersededByArtifactId: internalState.SupersededByArtifactId,
            CreatedAtUtc: internalState.CreatedAtUtc,
            UpdatedAtUtc: internalState.UpdatedAtUtc,
            LifecycleChangedAtUtc: internalState.LifecycleChangedAtUtc,
            InstallCount: internalState.InstallCount,
            ActiveRuntimeRefCount: internalState.ActiveRuntimeRefCount,
            LastInstalledAtUtc: internalState.LastInstalledAtUtc,
            ReviewScores: internalState.ReviewScores.ToArray());

    private static HubArtifactStoreRuntimeBundleArtifactSnapshot ToBackupRuntimeBundleArtifact(RuntimeBundleArtifactInternal internalState) =>
        new(
            ArtifactId: internalState.ArtifactId,
            BundleFamilyId: internalState.BundleFamilyId,
            SessionId: internalState.SessionId,
            SceneId: internalState.SceneId,
            Head: ToLegacyRuntimeBundleHeadKind(internalState.Head),
            SourceBundleVersion: internalState.SourceBundleVersion,
            ProjectionFingerprint: internalState.ProjectionFingerprint,
            ProjectionVersion: internalState.ProjectionVersion,
            Ready: internalState.Ready,
            OfflineCapable: internalState.OfflineCapable,
            CollaborationMode: internalState.CollaborationMode,
            InvalidationSignals: internalState.InvalidationSignals,
            IncludedEventTypes: internalState.IncludedEventTypes,
            SupportedExchangeFormats: internalState.SupportedExchangeFormats,
            RequestedBy: internalState.RequestedBy,
            IssuedAtUtc: internalState.IssuedAtUtc,
            PreviousArtifactId: internalState.PreviousArtifactId);

    private static HubArtifactStoreRuntimeBundleHeadSnapshot ToBackupRuntimeBundleHead(RuntimeBundleHeadInternal internalState) =>
        new(
            BundleFamilyId: internalState.BundleFamilyId,
            SessionId: internalState.SessionId,
            SceneId: internalState.SceneId,
            Head: ToLegacyRuntimeBundleHeadKind(internalState.Head),
            CurrentArtifactId: internalState.CurrentArtifactId,
            CurrentVersion: internalState.CurrentVersion,
            SourceBundleVersion: internalState.SourceBundleVersion,
            ProjectionFingerprint: internalState.ProjectionFingerprint,
            ProjectionVersion: internalState.ProjectionVersion,
            Ready: internalState.Ready,
            OfflineCapable: internalState.OfflineCapable,
            CollaborationMode: internalState.CollaborationMode,
            SupportedExchangeFormats: internalState.SupportedExchangeFormats,
            IssuedAtUtc: internalState.IssuedAtUtc,
            PreviousArtifactId: internalState.PreviousArtifactId);

    private static HubArtifactInternal FromBackupArtifact(HubArtifactStoreArtifactSnapshot snapshot)
    {
        var artifact = new HubArtifactInternal
        {
            Id = snapshot.Id,
            Name = snapshot.Name,
            Kind = ToLiveHubArtifactKind(snapshot.Kind),
            Version = snapshot.Version,
            RulesetId = snapshot.RulesetId,
            Visibility = snapshot.Visibility,
            TrustTier = snapshot.TrustTier,
            State = ToLiveHubArtifactState(snapshot.State),
            Owner = snapshot.Owner,
            PublisherId = snapshot.PublisherId,
            Summary = snapshot.Summary,
            Description = snapshot.Description,
            RuntimeFingerprint = snapshot.RuntimeFingerprint,
            StateReason = snapshot.StateReason,
            SupersededByArtifactId = snapshot.SupersededByArtifactId,
            CreatedAtUtc = snapshot.CreatedAtUtc,
            UpdatedAtUtc = snapshot.UpdatedAtUtc,
            LifecycleChangedAtUtc = snapshot.LifecycleChangedAtUtc,
            InstallCount = snapshot.InstallCount,
            ActiveRuntimeRefCount = snapshot.ActiveRuntimeRefCount,
            LastInstalledAtUtc = snapshot.LastInstalledAtUtc
        };
        artifact.ReviewScores.AddRange(snapshot.ReviewScores ?? Array.Empty<double>());
        return artifact;
    }

    private static RuntimeBundleArtifactInternal FromBackupRuntimeBundleArtifact(HubArtifactStoreRuntimeBundleArtifactSnapshot snapshot) =>
        new()
        {
            ArtifactId = snapshot.ArtifactId,
            BundleFamilyId = snapshot.BundleFamilyId,
            SessionId = snapshot.SessionId,
            SceneId = snapshot.SceneId,
            Head = ToLiveRuntimeBundleHeadKind(snapshot.Head),
            SourceBundleVersion = snapshot.SourceBundleVersion,
            ProjectionFingerprint = snapshot.ProjectionFingerprint,
            ProjectionVersion = snapshot.ProjectionVersion,
            Ready = snapshot.Ready,
            OfflineCapable = snapshot.OfflineCapable,
            CollaborationMode = snapshot.CollaborationMode,
            InvalidationSignals = snapshot.InvalidationSignals.ToArray(),
            IncludedEventTypes = snapshot.IncludedEventTypes.ToArray(),
            SupportedExchangeFormats = snapshot.SupportedExchangeFormats.ToArray(),
            RequestedBy = snapshot.RequestedBy,
            IssuedAtUtc = snapshot.IssuedAtUtc,
            PreviousArtifactId = snapshot.PreviousArtifactId
        };

    private static RuntimeBundleHeadInternal FromBackupRuntimeBundleHead(HubArtifactStoreRuntimeBundleHeadSnapshot snapshot) =>
        new()
        {
            BundleFamilyId = snapshot.BundleFamilyId,
            SessionId = snapshot.SessionId,
            SceneId = snapshot.SceneId,
            Head = ToLiveRuntimeBundleHeadKind(snapshot.Head),
            CurrentArtifactId = snapshot.CurrentArtifactId,
            CurrentVersion = snapshot.CurrentVersion,
            SourceBundleVersion = snapshot.SourceBundleVersion,
            ProjectionFingerprint = snapshot.ProjectionFingerprint,
            ProjectionVersion = snapshot.ProjectionVersion,
            Ready = snapshot.Ready,
            OfflineCapable = snapshot.OfflineCapable,
            CollaborationMode = snapshot.CollaborationMode,
            SupportedExchangeFormats = snapshot.SupportedExchangeFormats.ToArray(),
            IssuedAtUtc = snapshot.IssuedAtUtc,
            PreviousArtifactId = snapshot.PreviousArtifactId
        };

    private RuntimeBundleArtifactProjection ToRuntimeBundleArtifactProjection(RuntimeBundleArtifactInternal internalState) =>
        new(
            ArtifactId: internalState.ArtifactId,
            BundleFamilyId: internalState.BundleFamilyId,
            SessionId: internalState.SessionId,
            SceneId: internalState.SceneId,
            Head: internalState.Head,
            SourceBundleVersion: internalState.SourceBundleVersion,
            ProjectionFingerprint: internalState.ProjectionFingerprint,
            ProjectionVersion: internalState.ProjectionVersion,
            Ready: internalState.Ready,
            OfflineCapable: internalState.OfflineCapable,
            CollaborationMode: internalState.CollaborationMode,
            InvalidationSignals: internalState.InvalidationSignals,
            IncludedEventTypes: internalState.IncludedEventTypes,
            SupportedExchangeFormats: internalState.SupportedExchangeFormats,
            RequestedBy: internalState.RequestedBy,
            IssuedAtUtc: internalState.IssuedAtUtc,
            PreviousArtifactId: internalState.PreviousArtifactId);

    private RuntimeBundleHeadProjection ToRuntimeBundleHeadProjection(RuntimeBundleHeadInternal internalState) =>
        new(
            BundleFamilyId: internalState.BundleFamilyId,
            SessionId: internalState.SessionId,
            SceneId: internalState.SceneId,
            Head: internalState.Head,
            CurrentArtifactId: internalState.CurrentArtifactId,
            CurrentVersion: internalState.CurrentVersion,
            SourceBundleVersion: internalState.SourceBundleVersion,
            ProjectionFingerprint: internalState.ProjectionFingerprint,
            ProjectionVersion: internalState.ProjectionVersion,
            Ready: internalState.Ready,
            OfflineCapable: internalState.OfflineCapable,
            CollaborationMode: internalState.CollaborationMode,
            SupportedExchangeFormats: internalState.SupportedExchangeFormats,
            IssuedAtUtc: internalState.IssuedAtUtc,
            PreviousArtifactId: internalState.PreviousArtifactId);

    private RegistryProjectionResponse ToProjection(HubArtifactInternal internalState) =>
        new(
            Id: internalState.Id,
            Name: internalState.Name,
            Kind: internalState.Kind.ToString(),
            Version: internalState.Version,
            Summary: internalState.Summary ?? string.Empty,
            State: internalState.State.ToString(),
            StateReason: internalState.StateReason,
            RuntimeFingerprint: internalState.RuntimeFingerprint,
            SupersededByArtifactId: internalState.SupersededByArtifactId,
            AcceptingNewInstalls: AcceptingNewInstalls(internalState),
            ImmutableRetentionRequired: true,
            InstallCount: internalState.InstallCount,
            ActiveRuntimeRefCount: internalState.ActiveRuntimeRefCount,
            CreatedAtUtc: internalState.CreatedAtUtc,
            UpdatedAtUtc: internalState.UpdatedAtUtc,
            LifecycleChangedAtUtc: internalState.LifecycleChangedAtUtc);

    private HubArtifactInstallProjection ToInstallProjection(HubArtifactInternal internalState) =>
        new(
            ArtifactId: internalState.Id,
            Kind: internalState.Kind,
            Version: internalState.Version,
            RulesetId: internalState.RulesetId,
            State: internalState.State,
            SupersededByArtifactId: internalState.SupersededByArtifactId,
            ImmutableRetentionRequired: true,
            AcceptingNewInstalls: AcceptingNewInstalls(internalState),
            InstallCount: internalState.InstallCount,
            ActiveRuntimeRefCount: internalState.ActiveRuntimeRefCount,
            HasInstallReferences: internalState.InstallCount > 0,
            HasRuntimeReferences: internalState.ActiveRuntimeRefCount > 0,
            LastInstalledAtUtc: internalState.LastInstalledAtUtc,
            Install: new ArtifactInstallState(
                State: internalState.InstallCount > 0 ? ArtifactInstallStates.Installed : ArtifactInstallStates.Available,
                InstalledAtUtc: internalState.InstallCount > 0 ? internalState.LastInstalledAtUtc : null,
                RuntimeFingerprint: internalState.RuntimeFingerprint));

    private static HubArtifactInternal CreateArtifact(
        string name,
        HubArtifactKind kind,
        string version,
        string rulesetId,
        string visibility,
        string trustTier,
        string? owner,
        string? publisherId,
        string? summary,
        string? description,
        string? runtimeFingerprint,
        string? stateReason)
    {
        var id = $"artifact_{Guid.NewGuid():N}";
        var now = DateTimeOffset.UtcNow;

        return new HubArtifactInternal
        {
            Id = id,
            Name = name,
            Kind = kind,
            Version = version,
            RulesetId = rulesetId,
            Visibility = visibility,
            TrustTier = trustTier,
            State = HubArtifactState.Active,
            Owner = owner,
            PublisherId = publisherId,
            Summary = summary,
            Description = description,
            RuntimeFingerprint = runtimeFingerprint,
            StateReason = stateReason,
            CreatedAtUtc = now,
            UpdatedAtUtc = now,
            LifecycleChangedAtUtc = null,
            LastInstalledAtUtc = DateTimeOffset.MinValue
        };
    }

    private static int ToInt(long value) => value > int.MaxValue ? int.MaxValue : (int)value;

    private static string NormalizeRulesetId(string? value) =>
        string.IsNullOrWhiteSpace(value) ? "sr5" : value.Trim();

    private static string NormalizeVisibility(string? value) =>
        string.IsNullOrWhiteSpace(value) ? ArtifactVisibilityModes.Shared : value.Trim();

    private static string NormalizeTrustTier(string? value) =>
        string.IsNullOrWhiteSpace(value) ? ArtifactTrustTiers.Curated : value.Trim();
}
