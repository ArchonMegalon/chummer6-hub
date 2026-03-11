using Chummer.Run.AI.Services.Assets;
using Chummer.Media.Contracts;
using Chummer.Run.Contracts.Media;
using System.Collections.Concurrent;
using System.Text.Json;

namespace Chummer.Run.AI.Services.Creative;

public interface IRouteCinemaService
{
    Task<RouteCinemaResult> GenerateAsync(
        RouteCinemaRequest request,
        CancellationToken cancellationToken = default);

    RouteCinemaResult? Get(string routeCinemaId);

    IReadOnlyList<RouteCinemaResult> List(string campaignId);
}

public sealed class RouteCinemaService : IRouteCinemaService
{
    private sealed class RouteCinemaState
    {
        public required string RouteCinemaId { get; init; }
        public required string CampaignId { get; init; }
        public required string SourceNode { get; init; }
        public required string TargetNode { get; init; }
        public required string SceneContext { get; init; }
        public required IReadOnlyList<string> Waypoints { get; init; }
        public required IReadOnlyList<string> WaypointScript { get; init; }
        public required string TravelSummary { get; init; }
        public required string ProjectionFingerprint { get; init; }
        public required string DeduplicationKey { get; init; }
        public required string PreviewJobId { get; init; }
        public required string RouteVideoJobId { get; init; }
        public required TimeSpan CacheTtl { get; init; }
        public required DateTimeOffset CreatedAtUtc { get; init; }
    }

    private readonly IMediaRenderJobService _mediaRenderJobs;
    private readonly IAssetLifecycleService _assets;
    private readonly ConcurrentDictionary<string, RouteCinemaState> _routes = new(StringComparer.OrdinalIgnoreCase);
    private readonly ConcurrentDictionary<string, string> _routeIdsByDeduplicationKey = new(StringComparer.OrdinalIgnoreCase);
    private readonly object _sync = new();

    public RouteCinemaService(
        IMediaRenderJobService mediaRenderJobs,
        IAssetLifecycleService assets)
    {
        _mediaRenderJobs = mediaRenderJobs;
        _assets = assets;
    }

    public async Task<RouteCinemaResult> GenerateAsync(
        RouteCinemaRequest request,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var normalized = Normalize(request);
        var deduplicationKey = BuildDeduplicationKey(normalized);

        lock (_sync)
        {
            if (_routeIdsByDeduplicationKey.TryGetValue(deduplicationKey, out var existingId) &&
                _routes.TryGetValue(existingId, out var existing))
            {
                return BuildResult(existing);
            }
        }

        var waypoints = BuildWaypoints(normalized.SourceNode, normalized.TargetNode);
        var script = BuildScript(normalized, waypoints);
        var travelSummary = BuildTravelSummary(normalized, waypoints);
        var projectionFingerprint = BuildProjectionFingerprint(normalized, waypoints);
        var cacheTtl = TimeSpan.FromDays(7);

        var previewJob = await _mediaRenderJobs.EnqueueAsync(
            new MediaRenderJobEnqueueRequest(
                JobType: MediaRenderJobType.CinematicPreviewImage,
                DeduplicationKey: $"{deduplicationKey}::preview",
                Category: "route-cinema/preview",
                Payload: BuildPreviewPayload(normalized, waypoints, travelSummary),
                Source: normalized.CampaignId,
                CacheTtl: cacheTtl,
                MaxBytes: 1_500_000,
                RequiresApproval: true,
                PersistOnApproval: true,
                AllowPersistentPinning: true),
            cancellationToken);

        var routePayload = JsonSerializer.Serialize(new
        {
            normalized.CampaignId,
            normalized.SourceNode,
            normalized.TargetNode,
            normalized.SceneContext,
            projectionFingerprint,
            Waypoints = waypoints,
            Script = script,
            TravelSummary = travelSummary
        });

        var routeJob = await _mediaRenderJobs.EnqueueAsync(
            new MediaRenderJobEnqueueRequest(
                JobType: MediaRenderJobType.CinematicVideo,
                DeduplicationKey: $"{deduplicationKey}::video",
                Category: "route-cinema/video",
                Payload: routePayload,
                Source: normalized.CampaignId,
                CacheTtl: cacheTtl,
                MaxBytes: 5_000_000,
                RequiresApproval: true,
                PersistOnApproval: true,
                AllowPersistentPinning: true),
            cancellationToken);

        lock (_sync)
        {
            if (_routeIdsByDeduplicationKey.TryGetValue(deduplicationKey, out var existingId) &&
                _routes.TryGetValue(existingId, out var existing))
            {
                return BuildResult(existing);
            }

            var state = new RouteCinemaState
            {
                RouteCinemaId = $"route_{Guid.NewGuid():N}",
                CampaignId = normalized.CampaignId,
                SourceNode = normalized.SourceNode,
                TargetNode = normalized.TargetNode,
                SceneContext = normalized.SceneContext,
                Waypoints = waypoints,
                WaypointScript = script,
                TravelSummary = travelSummary,
                ProjectionFingerprint = projectionFingerprint,
                DeduplicationKey = deduplicationKey,
                PreviewJobId = previewJob.JobId,
                RouteVideoJobId = routeJob.JobId,
                CacheTtl = cacheTtl,
                CreatedAtUtc = DateTimeOffset.UtcNow
            };

            _routes[state.RouteCinemaId] = state;
            _routeIdsByDeduplicationKey[deduplicationKey] = state.RouteCinemaId;
            return BuildResult(state);
        }
    }

    public RouteCinemaResult? Get(string routeCinemaId)
    {
        if (string.IsNullOrWhiteSpace(routeCinemaId) ||
            !_routes.TryGetValue(routeCinemaId.Trim(), out var state))
        {
            return null;
        }

        return BuildResult(state);
    }

    public IReadOnlyList<RouteCinemaResult> List(string campaignId)
    {
        if (string.IsNullOrWhiteSpace(campaignId))
        {
            return Array.Empty<RouteCinemaResult>();
        }

        return _routes.Values
            .Where(state => string.Equals(state.CampaignId, campaignId.Trim(), StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static state => state.CreatedAtUtc)
            .Select(BuildResult)
            .ToArray();
    }

    private RouteCinemaResult BuildResult(RouteCinemaState state)
    {
        var previewArtifact = RefreshArtifact(new RouteCinemaArtifactHandle(
            Role: RouteCinemaArtifactRole.Preview,
            Category: "route-cinema/preview",
            JobId: state.PreviewJobId,
            JobState: MediaRenderJobState.Queued,
            AssetId: null,
            CacheTtl: state.CacheTtl));
        var videoArtifact = RefreshArtifact(new RouteCinemaArtifactHandle(
            Role: RouteCinemaArtifactRole.Video,
            Category: "route-cinema/video",
            JobId: state.RouteVideoJobId,
            JobState: MediaRenderJobState.Queued,
            AssetId: null,
            CacheTtl: state.CacheTtl));

        var videoAsset = string.IsNullOrWhiteSpace(videoArtifact.AssetId) ? null : _assets.Resolve(videoArtifact.AssetId);
        var previewAsset = string.IsNullOrWhiteSpace(previewArtifact.AssetId) ? null : _assets.Resolve(previewArtifact.AssetId);

        var approvalState = videoAsset?.ApprovalState ?? previewAsset?.ApprovalState ?? AssetApprovalState.Draft;
        var retentionState = videoAsset?.RetentionState ?? previewAsset?.RetentionState ?? AssetRetentionState.Expired;
        var expiresAtUtc = videoAsset?.ExpiresAtUtc ?? previewAsset?.ExpiresAtUtc ?? state.CreatedAtUtc + state.CacheTtl;
        var reviewState = ResolveReviewState(videoArtifact, videoAsset, previewAsset);

        if (retentionState == AssetRetentionState.Expired)
        {
            lock (_sync)
            {
                _routeIdsByDeduplicationKey.TryRemove(state.DeduplicationKey, out _);
            }
        }

        return new RouteCinemaResult(
            RouteCinemaId: state.RouteCinemaId,
            CampaignId: state.CampaignId,
            SourceNode: state.SourceNode,
            TargetNode: state.TargetNode,
            SceneContext: state.SceneContext,
            Waypoints: state.Waypoints,
            WaypointScript: state.WaypointScript,
            TravelSummary: state.TravelSummary,
            ProjectionFingerprint: state.ProjectionFingerprint,
            ApprovalState: approvalState,
            RetentionState: retentionState,
            ReviewState: reviewState,
            CreatedAtUtc: state.CreatedAtUtc,
            ExpiresAtUtc: expiresAtUtc,
            PreviewAssetId: previewArtifact.AssetId,
            RouteVideoAssetId: videoArtifact.AssetId,
            PreviewJobId: previewArtifact.JobId,
            PreviewJobState: previewArtifact.JobState,
            RouteVideoJobId: videoArtifact.JobId,
            RouteVideoJobState: videoArtifact.JobState,
            Artifacts: new[] { previewArtifact, videoArtifact },
            CacheTtl: state.CacheTtl);
    }

    private RouteCinemaArtifactHandle RefreshArtifact(RouteCinemaArtifactHandle artifact)
    {
        var status = _mediaRenderJobs.Get(artifact.JobId);
        if (status is null)
        {
            return artifact with { JobState = MediaRenderJobState.Expired };
        }

        return artifact with
        {
            JobState = status.State,
            AssetId = status.AssetId,
            CacheTtl = status.CacheTtl ?? artifact.CacheTtl
        };
    }

    private static RouteCinemaRequest Normalize(RouteCinemaRequest request)
    {
        if (string.IsNullOrWhiteSpace(request.CampaignId))
        {
            throw new ArgumentException("CampaignId is required.", nameof(request));
        }

        if (string.IsNullOrWhiteSpace(request.SourceNode) || string.IsNullOrWhiteSpace(request.TargetNode))
        {
            throw new ArgumentException("SourceNode and TargetNode are required.", nameof(request));
        }

        if (string.IsNullOrWhiteSpace(request.SceneContext))
        {
            throw new ArgumentException("SceneContext is required.", nameof(request));
        }

        return request with
        {
            CampaignId = request.CampaignId.Trim(),
            SourceNode = request.SourceNode.Trim(),
            TargetNode = request.TargetNode.Trim(),
            SceneContext = request.SceneContext.Trim()
        };
    }

    private static string BuildDeduplicationKey(RouteCinemaRequest request) =>
        $"route-cinema::{request.CampaignId}::{request.SourceNode}::{request.TargetNode}::{request.SceneContext}";

    private static List<string> BuildWaypoints(string source, string target)
    {
        var normalizedSource = string.Join(' ', source.Split(' ', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries));
        var normalizedTarget = string.Join(' ', target.Split(' ', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries));

        if (string.Equals(normalizedSource, normalizedTarget, StringComparison.OrdinalIgnoreCase))
        {
            return new List<string> { normalizedSource };
        }

        var mid = MidpointHash(normalizedSource, normalizedTarget);
        return new List<string>
        {
            normalizedSource,
            mid,
            normalizedTarget
        };
    }

    private static List<string> BuildScript(RouteCinemaRequest request, IReadOnlyList<string> waypoints)
    {
        var points = waypoints.Select((point, index) => $"[SEGMENT {index + 1}] {point}").ToList();
        points.Add($"Context cue: {request.SceneContext}");
        points.Add($"End at {request.TargetNode}");
        return points;
    }

    private static string BuildTravelSummary(RouteCinemaRequest request, IReadOnlyList<string> waypoints) =>
        $"{request.SourceNode} to {request.TargetNode} under {request.SceneContext}; {waypoints.Count} travel beats queued for review.";

    private static string BuildProjectionFingerprint(RouteCinemaRequest request, IReadOnlyList<string> waypoints) =>
        $"route-cinema::{request.CampaignId}::{request.SourceNode}::{request.TargetNode}::{waypoints.Count}";

    private static string BuildPreviewPayload(RouteCinemaRequest request, IReadOnlyList<string> waypoints, string travelSummary) =>
        JsonSerializer.Serialize(new
        {
            request.CampaignId,
            request.SourceNode,
            request.TargetNode,
            request.SceneContext,
            Preview = new
            {
                travelSummary,
                Waypoints = waypoints,
                Title = $"{request.SourceNode} -> {request.TargetNode}"
            }
        });

    private static string ResolveReviewState(
        RouteCinemaArtifactHandle videoArtifact,
        AssetCatalogItem? videoAsset,
        AssetCatalogItem? previewAsset)
    {
        if (videoAsset is null && previewAsset is null)
        {
            return "draft-expired";
        }

        if (videoArtifact.JobState == MediaRenderJobState.Failed)
        {
            return "render-failed";
        }

        if ((videoAsset?.ApprovalState ?? previewAsset?.ApprovalState) == AssetApprovalState.Approved)
        {
            return "approved";
        }

        return "draft";
    }

    private static string MidpointHash(string source, string target)
    {
        var sourceHash = Math.Abs(source.GetHashCode());
        var targetHash = Math.Abs(target.GetHashCode());
        var seed = unchecked(sourceHash ^ targetHash);
        return $"WayPoint-{seed & 0x7FFF:X4}";
    }
}
