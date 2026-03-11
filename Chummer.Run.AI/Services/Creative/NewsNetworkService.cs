using Chummer.Run.AI.Services.Assets;
using Chummer.Run.AI.Services.Session;
using Chummer.Run.AI.Services.Spider;
using Chummer.Media.Contracts;
using Chummer.Run.Contracts.Media;
using System.Collections.Concurrent;
using System.Text;
using System.Text.Json;
using DeliveryOutboxCreateRequest = Chummer.Play.Contracts.Spider.DeliveryOutboxCreateRequest;
using DeliveryOutboxMessage = Chummer.Play.Contracts.Spider.DeliveryOutboxMessage;
using SessionMemoryDraftRequest = Chummer.Play.Contracts.Memory.SessionMemoryDraftRequest;
using SessionMemoryEvidence = Chummer.Play.Contracts.Memory.SessionMemoryEvidence;

namespace Chummer.Run.AI.Services.Creative;

public interface INewsNetworkService
{
    Task<NewsBriefResult> BuildNewsBriefAsync(
        NewsBriefRequest request,
        CancellationToken cancellationToken = default);

    NewsBriefResult? Get(string newsBriefId);

    Task<NewsBriefDeliveryResult> DeliverAsync(
        string newsBriefId,
        NewsBriefDeliveryRequest request,
        CancellationToken cancellationToken = default);
}

public sealed class NewsNetworkService : INewsNetworkService
{
    private sealed record NewsBriefDeliveryRecord(
        string Channel,
        string MessageId);

    private sealed class NewsBriefState
    {
        public required string NewsBriefId { get; init; }
        public required string CampaignId { get; init; }
        public string? SessionId { get; set; }
        public string? SceneId { get; set; }
        public string? SceneRevision { get; set; }
        public required string ShortRecap { get; init; }
        public required string LongRecap { get; init; }
        public required string InUniverseBulletin { get; init; }
        public required string FalloutSummary { get; init; }
        public required string RecapAssetId { get; init; }
        public required IReadOnlyList<NewsFact> Facts { get; init; }
        public required string ProjectionFingerprint { get; init; }
        public required DateTimeOffset GeneratedAtUtc { get; init; }
        public string DeliveryState { get; set; } = "draft";
        public string? VideoJobId { get; init; }
        public List<NewsBriefDeliveryRecord> Deliveries { get; } = new();
    }

    private readonly IMediaRenderJobService _mediaRenderJobs;
    private readonly IAssetLifecycleService _assets;
    private readonly ISessionLedgerService _ledger;
    private readonly ISessionMemoryService _memory;
    private readonly IDeliveryOutboxService _outbox;
    private readonly ConcurrentDictionary<string, NewsBriefState> _briefs = new(StringComparer.OrdinalIgnoreCase);
    private readonly object _sync = new();

    public NewsNetworkService(
        IMediaRenderJobService mediaRenderJobs,
        IAssetLifecycleService assets,
        ISessionLedgerService ledger,
        ISessionMemoryService memory,
        IDeliveryOutboxService outbox)
    {
        _mediaRenderJobs = mediaRenderJobs;
        _assets = assets;
        _ledger = ledger;
        _memory = memory;
        _outbox = outbox;
    }

    public async Task<NewsBriefResult> BuildNewsBriefAsync(
        NewsBriefRequest request,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (string.IsNullOrWhiteSpace(request.CampaignId))
        {
            throw new ArgumentException("CampaignId is required.", nameof(request));
        }

        var normalized = Normalize(request);
        var generatedAtUtc = DateTimeOffset.UtcNow;
        var facts = CollectFacts(normalized);
        var projectionFingerprint = ResolveProjectionFingerprint(normalized);
        var shortRecap = BuildShortRecap(facts);
        var longRecap = BuildLongRecap(facts, normalized.SceneId);
        var bulletin = BuildInUniverseBulletin(facts, normalized.CampaignId);
        var falloutSummary = BuildFalloutSummary(facts);
        var recapPayload = JsonSerializer.Serialize(new
        {
            normalized.CampaignId,
            normalized.SessionId,
            normalized.SceneId,
            normalized.SceneRevision,
            projectionFingerprint,
            shortRecap,
            longRecap,
            bulletin,
            falloutSummary,
            facts,
            generatedAtUtc
        });

        var recapAsset = await _assets.StoreAsync(
            category: "news/recap",
            content: recapPayload,
            source: normalized.CampaignId,
            policy: new AssetLifecyclePolicy(
                CacheTtl: TimeSpan.FromDays(30),
                LongTermCache: false,
                MaxBytes: 256_000,
                RequiresApproval: true,
                PersistOnApproval: true,
                StorageClass: AssetStorageClass.ObjectStorage,
                AllowPersistentPinning: true),
            cancellationToken: cancellationToken);

        MediaRenderJobStatus? videoJob = null;
        if (normalized.IncludeVideo)
        {
            videoJob = await _mediaRenderJobs.EnqueueAsync(
                new MediaRenderJobEnqueueRequest(
                    JobType: MediaRenderJobType.NarrativeBriefVideo,
                    DeduplicationKey: BuildDeduplicationKey(normalized.CampaignId, normalized.SceneRevision, facts),
                    Category: "news/video",
                    Payload: BuildVideoScript(normalized.CampaignId, facts, bulletin),
                    Source: normalized.CampaignId,
                    CacheTtl: TimeSpan.FromDays(30),
                    MaxBytes: 8_000_000,
                    RequiresApproval: true,
                    PersistOnApproval: true,
                    AllowPersistentPinning: true),
                cancellationToken);
        }

        var briefId = $"brief_{Guid.NewGuid():N}";
        var state = new NewsBriefState
        {
            NewsBriefId = briefId,
            CampaignId = normalized.CampaignId,
            SessionId = normalized.SessionId,
            SceneId = normalized.SceneId,
            SceneRevision = normalized.SceneRevision,
            ShortRecap = shortRecap,
            LongRecap = longRecap,
            InUniverseBulletin = bulletin,
            FalloutSummary = falloutSummary,
            RecapAssetId = recapAsset.AssetId,
            Facts = facts,
            ProjectionFingerprint = projectionFingerprint,
            GeneratedAtUtc = generatedAtUtc,
            VideoJobId = videoJob?.JobId
        };

        _briefs[briefId] = state;
        return BuildResult(state);
    }

    public NewsBriefResult? Get(string newsBriefId)
    {
        if (string.IsNullOrWhiteSpace(newsBriefId) || !_briefs.TryGetValue(newsBriefId, out var state))
        {
            return null;
        }

        return BuildResult(state);
    }

    public Task<NewsBriefDeliveryResult> DeliverAsync(
        string newsBriefId,
        NewsBriefDeliveryRequest request,
        CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (string.IsNullOrWhiteSpace(newsBriefId))
        {
            throw new ArgumentException("newsBriefId is required.", nameof(newsBriefId));
        }

        if (request is null)
        {
            throw new ArgumentNullException(nameof(request));
        }

        if (string.IsNullOrWhiteSpace(request.SessionId)
            || string.IsNullOrWhiteSpace(request.SceneId)
            || string.IsNullOrWhiteSpace(request.SceneRevision)
            || string.IsNullOrWhiteSpace(request.RequestedBy))
        {
            throw new ArgumentException("SessionId, SceneId, SceneRevision, and RequestedBy are required.", nameof(request));
        }

        if (!_briefs.TryGetValue(newsBriefId, out var state))
        {
            return Task.FromResult(new NewsBriefDeliveryResult(newsBriefId, "missing", "missing", "missing", Array.Empty<DeliveryOutboxMessage>()));
        }

        var recapAsset = _assets.Resolve(state.RecapAssetId);
        if (recapAsset is null)
        {
            return Task.FromResult(new NewsBriefDeliveryResult(newsBriefId, "asset-missing", "missing", state.DeliveryState, Array.Empty<DeliveryOutboxMessage>()));
        }

        if (recapAsset.ApprovalState != AssetApprovalState.Approved)
        {
            state.DeliveryState = "approval-required";
            return Task.FromResult(new NewsBriefDeliveryResult(newsBriefId, "approval-required", recapAsset.ApprovalState.ToString().ToLowerInvariant(), state.DeliveryState, Array.Empty<DeliveryOutboxMessage>()));
        }

        if (!string.IsNullOrWhiteSpace(state.SceneRevision)
            && !string.Equals(state.SceneRevision, request.SceneRevision, StringComparison.Ordinal))
        {
            return Task.FromResult(new NewsBriefDeliveryResult(newsBriefId, "stale", "approved", state.DeliveryState, Array.Empty<DeliveryOutboxMessage>()));
        }

        lock (_sync)
        {
            state.SessionId ??= request.SessionId.Trim();
            state.SceneId ??= request.SceneId.Trim();
            state.SceneRevision ??= request.SceneRevision.Trim();
        }

        var messages = new List<DeliveryOutboxMessage>();
        foreach (var channel in ResolveDeliveryChannels(request))
        {
            var existing = ResolveDeliveredMessage(state, channel);
            if (existing is not null)
            {
                messages.Add(existing);
                continue;
            }

            var created = _outbox.Enqueue(new DeliveryOutboxCreateRequest(
                SessionId: request.SessionId.Trim(),
                SceneId: request.SceneId.Trim(),
                SceneRevision: request.SceneRevision.Trim(),
                Channel: channel,
                Content: BuildDeliveryContent(state, channel, request.RequestedBy),
                ApprovalState: "approved",
                AutonomyMode: "manual-review",
                Ttl: TimeSpan.FromDays(30),
                ProjectionFingerprint: state.ProjectionFingerprint,
                CollaborationMode: "portable"));
            lock (_sync)
            {
                state.Deliveries.Add(new NewsBriefDeliveryRecord(channel, created.Id));
                state.DeliveryState = "delivered";
            }

            messages.Add(created);
        }

        return Task.FromResult(new NewsBriefDeliveryResult(newsBriefId, "delivered", "approved", state.DeliveryState, messages));
    }

    private NewsBriefResult BuildResult(NewsBriefState state)
    {
        var recapAsset = _assets.Resolve(state.RecapAssetId);
        var videoJob = string.IsNullOrWhiteSpace(state.VideoJobId) ? null : _mediaRenderJobs.Get(state.VideoJobId);
        lock (_sync)
        {
            var deliveryMessageIds = state.Deliveries
                .Select(static delivery => delivery.MessageId)
                .Distinct(StringComparer.Ordinal)
                .ToArray();

            return new NewsBriefResult(
                NewsBriefId: state.NewsBriefId,
                CampaignId: state.CampaignId,
                SessionId: state.SessionId,
                SceneId: state.SceneId,
                SceneRevision: state.SceneRevision,
                ShortRecap: state.ShortRecap,
                LongRecap: state.LongRecap,
                InUniverseBulletin: state.InUniverseBulletin,
                FalloutSummary: state.FalloutSummary,
                Facts: state.Facts,
                RecapAssetId: state.RecapAssetId,
                ApprovalState: recapAsset?.ApprovalState ?? AssetApprovalState.Draft,
                RetentionState: recapAsset?.RetentionState ?? AssetRetentionState.Expired,
                ProjectionFingerprint: state.ProjectionFingerprint,
                DeliveryState: state.DeliveryState,
                DeliveryMessageIds: deliveryMessageIds,
                GeneratedAtUtc: state.GeneratedAtUtc,
                VideoAssetId: videoJob?.AssetId,
                VideoJobId: videoJob?.JobId,
                VideoJobState: videoJob?.State);
        }
    }

    private IReadOnlyList<NewsFact> CollectFacts(NewsBriefRequest request)
    {
        var facts = new List<NewsFact>();
        var factIndex = 0;

        foreach (var item in request.SeedItems ?? Array.Empty<NewsItem>())
        {
            if (string.IsNullOrWhiteSpace(item.Title) && string.IsNullOrWhiteSpace(item.Summary))
            {
                continue;
            }

            facts.Add(new NewsFact(
                FactId: $"seed-{++factIndex}",
                Category: "seed",
                Summary: ComposeFactSummary(item.Title, item.Source, item.Summary),
                Evidence: new[]
                {
                    new SessionMemoryEvidence("seed-item", item.Url, $"{item.Source}: {item.Title}")
                }));
        }

        foreach (var note in request.ApprovedNotes ?? Array.Empty<string>())
        {
            if (string.IsNullOrWhiteSpace(note))
            {
                continue;
            }

            facts.Add(new NewsFact(
                FactId: $"approved-note-{++factIndex}",
                Category: "approved-note",
                Summary: note.Trim(),
                Evidence: new[]
                {
                    new SessionMemoryEvidence("approved-note", $"note:{factIndex}", note.Trim())
                }));
        }

        if (!string.IsNullOrWhiteSpace(request.SessionId) && !string.IsNullOrWhiteSpace(request.SceneId))
        {
            var draft = _memory.Draft(new SessionMemoryDraftRequest(
                SessionId: request.SessionId,
                SceneId: request.SceneId,
                Notes: request.Notes,
                Transcript: request.Transcript,
                PlayerMessages: request.PlayerMessages), request.SceneId);

            foreach (var highlight in draft.RecapDraft.Highlights.Take(3))
            {
                facts.Add(new NewsFact(
                    FactId: $"highlight-{++factIndex}",
                    Category: "session-highlight",
                    Summary: highlight,
                    Evidence: draft.RecapDraft.Evidence.Take(2).ToArray()));
            }

            foreach (var thread in draft.UnresolvedThreadDrafts.Take(2))
            {
                facts.Add(new NewsFact(
                    FactId: $"thread-{++factIndex}",
                    Category: "fallout",
                    Summary: $"{thread.Title}: {thread.Summary}",
                    Evidence: thread.Evidence));
            }

            foreach (var entry in draft.TimelineEntries.Take(3))
            {
                facts.Add(new NewsFact(
                    FactId: $"timeline-{++factIndex}",
                    Category: "timeline",
                    Summary: entry.Summary,
                    Evidence: entry.Evidence));
            }
        }

        if (facts.Count == 0)
        {
            facts.Add(new NewsFact(
                FactId: "fallback-1",
                Category: "fallback",
                Summary: "No verified session deltas were available; hold editorial posture and request GM review.",
                Evidence: new[]
                {
                    new SessionMemoryEvidence("fallback", "news:fallback", "Generated from empty session context")
                }));
        }

        return facts
            .DistinctBy(static fact => $"{fact.Category}:{fact.Summary}", StringComparer.Ordinal)
            .Take(8)
            .ToArray();
    }

    private string ResolveProjectionFingerprint(NewsBriefRequest request)
    {
        if (!string.IsNullOrWhiteSpace(request.SessionId) && !string.IsNullOrWhiteSpace(request.SceneId))
        {
            return _ledger.GetProjection(request.SessionId, request.SceneId).ProjectionFingerprint;
        }

        return $"seed:{BuildDeduplicationKey(request.CampaignId, request.SceneRevision, CollectFacts(request))}";
    }

    private static NewsBriefRequest Normalize(NewsBriefRequest request)
    {
        return request with
        {
            CampaignId = request.CampaignId.Trim(),
            SessionId = string.IsNullOrWhiteSpace(request.SessionId) ? null : request.SessionId.Trim(),
            SceneId = string.IsNullOrWhiteSpace(request.SceneId) ? null : request.SceneId.Trim(),
            SceneRevision = string.IsNullOrWhiteSpace(request.SceneRevision) ? null : request.SceneRevision.Trim(),
            Transcript = string.IsNullOrWhiteSpace(request.Transcript) ? null : request.Transcript.Trim(),
            Notes = string.IsNullOrWhiteSpace(request.Notes) ? null : request.Notes.Trim(),
            ApprovedNotes = request.ApprovedNotes?.Where(static item => !string.IsNullOrWhiteSpace(item)).Select(static item => item.Trim()).ToArray(),
            PlayerMessages = request.PlayerMessages?.Where(static item => !string.IsNullOrWhiteSpace(item)).Select(static item => item.Trim()).ToArray(),
            SeedItems = request.SeedItems?.Where(static item => !string.IsNullOrWhiteSpace(item.Title) || !string.IsNullOrWhiteSpace(item.Summary)).ToArray()
        };
    }

    private static string BuildShortRecap(IReadOnlyList<NewsFact> facts)
    {
        var topLines = facts.Take(3).Select(static fact => fact.Summary).ToArray();
        return $"Recap: {string.Join(" | ", topLines)}";
    }

    private static string BuildLongRecap(IReadOnlyList<NewsFact> facts, string? sceneId)
    {
        var prefix = string.IsNullOrWhiteSpace(sceneId)
            ? "Last time on the run:"
            : $"Last time on {sceneId}:";
        var numbered = facts
            .Take(5)
            .Select((fact, index) => $"{index + 1}. {fact.Summary}")
            .ToArray();
        return $"{prefix} {string.Join(" ", numbered)}";
    }

    private static string BuildInUniverseBulletin(IReadOnlyList<NewsFact> facts, string campaignId)
    {
        var lines = facts
            .Take(4)
            .Select(static fact => fact.Summary)
            .ToArray();
        return $"Sixth World News Network [{campaignId}]: {string.Join(" | ", lines)}";
    }

    private static string BuildFalloutSummary(IReadOnlyList<NewsFact> facts)
    {
        var fallout = facts
            .Where(static fact => string.Equals(fact.Category, "fallout", StringComparison.Ordinal))
            .Select(static fact => fact.Summary)
            .Take(2)
            .ToArray();
        if (fallout.Length == 0)
        {
            fallout = facts.TakeLast(Math.Min(2, facts.Count)).Select(static fact => fact.Summary).ToArray();
        }

        return $"Fallout watch: {string.Join(" | ", fallout)}";
    }

    private static string BuildDeduplicationKey(string campaignId, string? sceneRevision, IReadOnlyList<NewsFact> facts)
    {
        var summaries = facts.Take(6).Select(static fact => fact.Summary.Replace('|', '/')).ToArray();
        return $"news-brief::{campaignId.Trim()}::{sceneRevision?.Trim() ?? "none"}::{string.Join("||", summaries)}";
    }

    private static string BuildVideoScript(string campaignId, IReadOnlyList<NewsFact> facts, string bulletin)
    {
        var builder = new StringBuilder()
            .AppendLine("<video-script>")
            .AppendLine($"  <intro>{campaignId} bulletin</intro>")
            .AppendLine($"  <anchor>{bulletin}</anchor>")
            .AppendLine("  <shots>");

        foreach (var fact in facts.Take(4))
        {
            builder.AppendLine($"    <shot category=\"{fact.Category}\">{System.Net.WebUtility.HtmlEncode(fact.Summary)}</shot>");
        }

        builder
            .AppendLine("  </shots>")
            .AppendLine("  <credits>Grounded on session ledger, transcript, and approved notes.</credits>")
            .AppendLine("</video-script>");
        return builder.ToString();
    }

    private static string ComposeFactSummary(string title, string source, string summary)
    {
        var trimmedTitle = string.IsNullOrWhiteSpace(title) ? "Untitled dispatch" : title.Trim();
        var trimmedSource = string.IsNullOrWhiteSpace(source) ? "Unknown source" : source.Trim();
        var trimmedSummary = string.IsNullOrWhiteSpace(summary) ? "No summary supplied." : summary.Trim();
        return $"{trimmedTitle} ({trimmedSource}) - {trimmedSummary}";
    }

    private static IReadOnlyList<string> ResolveDeliveryChannels(NewsBriefDeliveryRequest request)
    {
        return new[] { request.Channel, request.Archive ? "archive" : null }
            .Where(static channel => !string.IsNullOrWhiteSpace(channel))
            .Select(static channel => channel!.Trim())
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    private DeliveryOutboxMessage? ResolveDeliveredMessage(NewsBriefState state, string channel)
    {
        var record = state.Deliveries.FirstOrDefault(item => string.Equals(item.Channel, channel, StringComparison.OrdinalIgnoreCase));
        return record is null ? null : _outbox.GetById(record.MessageId);
    }

    private static string BuildDeliveryContent(NewsBriefState state, string channel, string requestedBy)
    {
        return channel.Equals("archive", StringComparison.OrdinalIgnoreCase)
            ? $"Archived news recap: {state.LongRecap} | fallout={state.FalloutSummary} | requestedBy={requestedBy} | recapAsset={state.RecapAssetId}"
            : $"Approved news recap: {state.ShortRecap} | bulletin={state.InUniverseBulletin} | requestedBy={requestedBy}";
    }
}
