using Chummer.Run.AI.Services.Assets;
using Chummer.Run.AI.Services.Spider;
using Chummer.Media.Contracts;
using Chummer.Run.Contracts.Media;
using System.Collections.Concurrent;
using System.Text;
using System.Text.Json;
using DeliveryOutboxCreateRequest = Chummer.Play.Contracts.Spider.DeliveryOutboxCreateRequest;
using DeliveryOutboxMessage = Chummer.Play.Contracts.Spider.DeliveryOutboxMessage;

namespace Chummer.Run.AI.Services.Creative;

public interface INpcMessageVideoService
{
    Task<NpcVideoMessageResult> CreateAsync(
        NpcVideoMessageRequest request,
        CancellationToken cancellationToken = default);

    NpcVideoMessageResult? Get(string messageId);

    Task<NpcVideoMessagePublishResult> PublishAsync(
        string messageId,
        NpcVideoMessagePublishRequest request,
        CancellationToken cancellationToken = default);
}

public sealed class NpcMessageVideoService : INpcMessageVideoService
{
    private sealed record NpcPublishRecord(
        string Surface,
        string MessageId);

    private sealed class NpcMessageVideoState
    {
        public required string MessageId { get; init; }
        public required string SessionId { get; init; }
        public required string SceneId { get; init; }
        public required string NpcId { get; init; }
        public required string Style { get; init; }
        public required string MessageText { get; init; }
        public required string ScriptPayload { get; init; }
        public required string DeduplicationKey { get; init; }
        public required string VideoJobId { get; init; }
        public required TimeSpan CacheTtl { get; init; }
        public required double Confidence { get; init; }
        public required DateTimeOffset CreatedAtUtc { get; init; }
        public string PublishState { get; set; } = "draft";
        public List<NpcPublishRecord> Publishes { get; } = new();
    }

    private readonly IMediaRenderJobService _mediaRenderJobs;
    private readonly IAssetLifecycleService _assets;
    private readonly IDeliveryOutboxService _outbox;
    private readonly ConcurrentDictionary<string, NpcMessageVideoState> _messages = new(StringComparer.OrdinalIgnoreCase);
    private readonly ConcurrentDictionary<string, string> _messageIdsByDeduplicationKey = new(StringComparer.OrdinalIgnoreCase);
    private readonly object _sync = new();

    public NpcMessageVideoService(
        IMediaRenderJobService mediaRenderJobs,
        IAssetLifecycleService assets,
        IDeliveryOutboxService outbox)
    {
        _mediaRenderJobs = mediaRenderJobs;
        _assets = assets;
        _outbox = outbox;
    }

    public async Task<NpcVideoMessageResult> CreateAsync(
        NpcVideoMessageRequest request,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (string.IsNullOrWhiteSpace(request.SessionId) ||
            string.IsNullOrWhiteSpace(request.SceneId) ||
            string.IsNullOrWhiteSpace(request.NpcId))
        {
            throw new ArgumentException("SessionId, SceneId, and NpcId are required.");
        }

        if (string.IsNullOrWhiteSpace(request.MessageText))
        {
            throw new ArgumentException("MessageText is required.");
        }

        var safeStyle = string.IsNullOrWhiteSpace(request.Style)
            ? "corporate_direct"
            : request.Style.Trim();
        var normalized = request with
        {
            SessionId = request.SessionId.Trim(),
            SceneId = request.SceneId.Trim(),
            NpcId = request.NpcId.Trim(),
            MessageText = request.MessageText.Trim(),
            Style = safeStyle
        };
        var deduplicationKey = BuildDeduplicationKey(normalized, safeStyle);

        lock (_sync)
        {
            if (_messageIdsByDeduplicationKey.TryGetValue(deduplicationKey, out var existingId) &&
                _messages.TryGetValue(existingId, out var existing))
            {
                return BuildResult(existing);
            }
        }

        var script = BuildScript(normalized.NpcId, normalized.MessageText, safeStyle, normalized.SceneId);
        var payload = JsonSerializer.Serialize(new
        {
            normalized.SessionId,
            normalized.SceneId,
            normalized.NpcId,
            Style = safeStyle,
            Message = normalized.MessageText,
            Script = script,
            CreatedAt = DateTimeOffset.UtcNow
        });

        var rendered = new StringBuilder()
            .AppendLine("<npc-video>")
            .AppendLine($"  <npc id=\"{System.Net.WebUtility.HtmlEncode(normalized.NpcId)}\" />")
            .AppendLine($"  <style>{System.Net.WebUtility.HtmlEncode(safeStyle)}</style>")
            .AppendLine($"  <script>{System.Net.WebUtility.HtmlEncode(script)}</script>")
            .AppendLine("</npc-video>")
            .ToString();

        var cacheTtl = TimeSpan.FromDays(14);
        var job = await _mediaRenderJobs.EnqueueAsync(
            new MediaRenderJobEnqueueRequest(
                JobType: MediaRenderJobType.PersonaMessageVideo,
                DeduplicationKey: deduplicationKey,
                Category: "npc/video",
                Payload: rendered,
                Source: normalized.SessionId,
                CacheTtl: cacheTtl,
                MaxBytes: 12_000_000,
                RequiresApproval: true,
                PersistOnApproval: true,
                AllowPersistentPinning: true),
            cancellationToken);

        lock (_sync)
        {
            if (_messageIdsByDeduplicationKey.TryGetValue(deduplicationKey, out var existingId) &&
                _messages.TryGetValue(existingId, out var existing))
            {
                return BuildResult(existing);
            }

            var state = new NpcMessageVideoState
            {
                MessageId = $"npcmsg_{Guid.NewGuid():N}",
                SessionId = normalized.SessionId,
                SceneId = normalized.SceneId,
                NpcId = normalized.NpcId,
                Style = safeStyle,
                MessageText = normalized.MessageText,
                ScriptPayload = payload,
                DeduplicationKey = deduplicationKey,
                VideoJobId = job.JobId,
                CacheTtl = cacheTtl,
                Confidence = 0.77d,
                CreatedAtUtc = DateTimeOffset.UtcNow
            };

            _messages[state.MessageId] = state;
            _messageIdsByDeduplicationKey[deduplicationKey] = state.MessageId;
            return BuildResult(state);
        }
    }

    public NpcVideoMessageResult? Get(string messageId)
    {
        if (string.IsNullOrWhiteSpace(messageId) || !_messages.TryGetValue(messageId, out var state))
        {
            return null;
        }

        return BuildResult(state);
    }

    public Task<NpcVideoMessagePublishResult> PublishAsync(
        string messageId,
        NpcVideoMessagePublishRequest request,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (string.IsNullOrWhiteSpace(messageId))
        {
            throw new ArgumentException("messageId is required.", nameof(messageId));
        }

        if (request is null)
        {
            throw new ArgumentNullException(nameof(request));
        }

        if (string.IsNullOrWhiteSpace(request.SessionId) ||
            string.IsNullOrWhiteSpace(request.SceneId) ||
            string.IsNullOrWhiteSpace(request.SceneRevision) ||
            string.IsNullOrWhiteSpace(request.RequestedBy))
        {
            throw new ArgumentException("SessionId, SceneId, SceneRevision, and RequestedBy are required.", nameof(request));
        }

        if (!_messages.TryGetValue(messageId, out var state))
        {
            return Task.FromResult(new NpcVideoMessagePublishResult(messageId, "missing", "missing", "missing", Array.Empty<DeliveryOutboxMessage>()));
        }

        if (!string.Equals(state.SessionId, request.SessionId.Trim(), StringComparison.Ordinal) ||
            !string.Equals(state.SceneId, request.SceneId.Trim(), StringComparison.Ordinal))
        {
            lock (_sync)
            {
                state.PublishState = "scope-mismatch";
            }

            return Task.FromResult(new NpcVideoMessagePublishResult(messageId, "scope-mismatch", ResolveApprovalStateLabel(state), state.PublishState, Array.Empty<DeliveryOutboxMessage>()));
        }

        var job = _mediaRenderJobs.Get(state.VideoJobId);
        var assetId = job?.AssetId;
        var asset = string.IsNullOrWhiteSpace(assetId) ? null : _assets.Resolve(assetId);

        if (asset is null)
        {
            lock (_sync)
            {
                state.PublishState = "expired";
                _messageIdsByDeduplicationKey.TryRemove(state.DeduplicationKey, out _);
            }

            return Task.FromResult(new NpcVideoMessagePublishResult(messageId, "expired", "expired", "expired", Array.Empty<DeliveryOutboxMessage>()));
        }

        if (asset.ApprovalState != AssetApprovalState.Approved)
        {
            lock (_sync)
            {
                state.PublishState = "approval-required";
            }

            return Task.FromResult(new NpcVideoMessagePublishResult(
                messageId,
                "approval-required",
                asset.ApprovalState.ToString().ToLowerInvariant(),
                state.PublishState,
                Array.Empty<DeliveryOutboxMessage>()));
        }

        var messages = new List<DeliveryOutboxMessage>();
        foreach (var surface in ResolvePublishSurfaces(request))
        {
            var existing = ResolvePublishedMessage(state, surface);
            if (existing is not null)
            {
                messages.Add(existing);
                continue;
            }

            var created = _outbox.Enqueue(new DeliveryOutboxCreateRequest(
                SessionId: request.SessionId.Trim(),
                SceneId: request.SceneId.Trim(),
                SceneRevision: request.SceneRevision.Trim(),
                Channel: surface,
                Content: BuildPublishContent(state, request.RequestedBy, request.Notes, surface),
                ApprovalState: "approved",
                AutonomyMode: "manual-review",
                Ttl: asset.Policy?.CacheTtl ?? state.CacheTtl,
                ProjectionFingerprint: BuildProjectionFingerprint(state, job?.AssetId),
                CollaborationMode: "portable"));

            lock (_sync)
            {
                state.Publishes.Add(new NpcPublishRecord(surface, created.Id));
                state.PublishState = "published";
            }

            messages.Add(created);
        }

        return Task.FromResult(new NpcVideoMessagePublishResult(messageId, "published", "approved", state.PublishState, messages));
    }

    private NpcVideoMessageResult BuildResult(NpcMessageVideoState state)
    {
        var job = _mediaRenderJobs.Get(state.VideoJobId);
        var assetId = job?.AssetId;
        var asset = string.IsNullOrWhiteSpace(assetId) ? null : _assets.Resolve(assetId);

        AssetApprovalState approvalState;
        AssetRetentionState retentionState;
        DateTimeOffset? expiresAtUtc;
        string publishState;

        lock (_sync)
        {
            if (asset is null)
            {
                approvalState = AssetApprovalState.Draft;
                retentionState = AssetRetentionState.Expired;
                expiresAtUtc = state.CreatedAtUtc + state.CacheTtl;
                state.PublishState = state.Publishes.Count > 0 ? "expired" : "draft-expired";
                publishState = state.PublishState;
                _messageIdsByDeduplicationKey.TryRemove(state.DeduplicationKey, out _);
            }
            else
            {
                approvalState = asset.ApprovalState;
                retentionState = asset.RetentionState;
                expiresAtUtc = asset.ExpiresAtUtc;
                if (state.Publishes.Count > 0)
                {
                    state.PublishState = "published";
                }
                else if (approvalState != AssetApprovalState.Approved)
                {
                    state.PublishState = "draft";
                }
                else
                {
                    state.PublishState = "approved";
                }

                publishState = state.PublishState;
            }

            var publishedMessageIds = state.Publishes
                .Select(static publish => publish.MessageId)
                .Distinct(StringComparer.Ordinal)
                .ToArray();

            return new NpcVideoMessageResult(
                MessageId: state.MessageId,
                SessionId: state.SessionId,
                SceneId: state.SceneId,
                NpcId: state.NpcId,
                VideoAssetId: assetId,
                VideoJobId: state.VideoJobId,
                VideoJobState: job?.State ?? MediaRenderJobState.Expired,
                Script: state.ScriptPayload,
                Confidence: state.Confidence,
                CacheTtl: state.CacheTtl,
                ApprovalState: approvalState,
                RetentionState: retentionState,
                PublishState: publishState,
                PublishedMessageIds: publishedMessageIds,
                CreatedAtUtc: state.CreatedAtUtc,
                ExpiresAtUtc: expiresAtUtc);
        }
    }

    private static string BuildDeduplicationKey(NpcVideoMessageRequest request, string style) =>
        $"npc-video::{request.SessionId.Trim()}::{request.SceneId.Trim()}::{request.NpcId.Trim()}::{style.Trim()}::{request.MessageText.Trim()}";

    private static string BuildScript(string npcId, string message, string style, string sceneId) =>
        $"NPC[{npcId}] in scene {sceneId}: speak with {style} tone. Message: '{message}'. Include 2-second hold before send.";

    private static IReadOnlyList<string> ResolvePublishSurfaces(NpcVideoMessagePublishRequest request)
    {
        var requested = request.Surfaces ?? Array.Empty<string>();
        return requested
            .Append(request.Archive ? "archive" : null)
            .Where(static surface => !string.IsNullOrWhiteSpace(surface))
            .Select(static surface => surface!.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private DeliveryOutboxMessage? ResolvePublishedMessage(NpcMessageVideoState state, string surface)
    {
        lock (_sync)
        {
            var published = state.Publishes
                .LastOrDefault(item => string.Equals(item.Surface, surface, StringComparison.OrdinalIgnoreCase));
            return published is null ? null : _outbox.GetById(published.MessageId);
        }
    }

    private static string BuildPublishContent(
        NpcMessageVideoState state,
        string requestedBy,
        string? notes,
        string surface)
    {
        var builder = new StringBuilder()
            .Append("NPC video message ready for ")
            .Append(surface)
            .Append(": ")
            .Append(state.NpcId)
            .Append(" says \"")
            .Append(state.MessageText)
            .Append("\". Approved by ")
            .Append(requestedBy.Trim())
            .Append('.');

        if (!string.IsNullOrWhiteSpace(notes))
        {
            builder.Append(" Notes: ").Append(notes.Trim()).Append('.');
        }

        return builder.ToString();
    }

    private static string BuildProjectionFingerprint(NpcMessageVideoState state, string? assetId) =>
        $"npc-video::{state.SessionId}::{state.SceneId}::{state.NpcId}::{assetId ?? "pending"}";

    private string ResolveApprovalStateLabel(NpcMessageVideoState state)
    {
        var result = BuildResult(state);
        return result.ApprovalState.ToString().ToLowerInvariant();
    }
}
