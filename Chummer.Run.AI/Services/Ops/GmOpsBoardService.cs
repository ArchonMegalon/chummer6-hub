using Chummer.Run.AI.Services.Session;
using Chummer.Run.AI.Services.Spider;
using Chummer.Run.Contracts.Ops;
using System.Collections.Concurrent;

namespace Chummer.Run.AI.Services.Ops;

public interface IGmOpsBoardService
{
    OpsBoardProjection GetProjection(string sessionId, string sceneId, string? sceneRevision = null);
    GmPrepAssetRecord CreatePrepAsset(GmPrepAssetCreateRequest request);
    GmPrepAssetRecord? GetPrepAsset(string assetId);
    GmPrepAssetListResponse ListPrepAssets(
        string? campaignId = null,
        string? sessionId = null,
        string? sceneId = null,
        GmPrepAssetKind? kind = null,
        bool includeReusableCampaignAssets = false);
    GmPrepAssetRecord? UpdateChecklist(string assetId, GmPrepChecklistUpdateRequest request);
    GmPrepAssetRevealResult Reveal(string assetId, GmPrepAssetRevealRequest request);
    IReadOnlyList<GmPrepAssetRecord> ExportPortableAssets(
        string campaignId,
        string sessionId,
        string sceneId,
        IReadOnlyList<string>? assetIds = null,
        bool includeReusableCampaignAssets = false);
    OfflineSyncSurfaceMergeResult ReconcilePortableAssets(IReadOnlyList<OfflineSyncPrepAsset> assets);
}

public sealed class GmOpsBoardService : IGmOpsBoardService
{
    private sealed class PrepAssetState
    {
        public required string AssetId { get; init; }
        public required string CampaignId { get; set; }
        public string? SessionId { get; set; }
        public string? SceneId { get; set; }
        public required string Title { get; set; }
        public required GmPrepAssetKind Kind { get; set; }
        public required GmPrepAssetAudience Audience { get; set; }
        public string? Summary { get; set; }
        public required string Body { get; set; }
        public required string[] Tags { get; set; }
        public required List<GmPrepChecklistItem> ChecklistItems { get; init; }
        public required EvidencePointer[] Evidence { get; init; }
        public required bool Reusable { get; init; }
        public required string Status { get; set; }
        public string? CreatedBy { get; init; }
        public string? RuntimeFingerprint { get; init; }
        public required DateTimeOffset CreatedAtUtc { get; init; }
        public required DateTimeOffset UpdatedAtUtc { get; set; }
        public DateTimeOffset? LastRevealedAtUtc { get; set; }
        public string? LastRevealChannel { get; set; }
        public int RevealCount { get; set; }
    }

    private readonly ISessionLedgerService _ledger;
    private readonly IDeliveryOutboxService _outbox;
    private readonly ConcurrentDictionary<string, PrepAssetState> _assets = new(StringComparer.OrdinalIgnoreCase);

    public GmOpsBoardService(ISessionLedgerService ledger, IDeliveryOutboxService outbox)
    {
        _ledger = ledger;
        _outbox = outbox;
    }

    public OpsBoardProjection GetProjection(string sessionId, string sceneId, string? sceneRevision = null)
    {
        var projection = _ledger.GetProjection(sessionId, sceneId);
        var cards = _outbox.GetForScene(sessionId, sceneId, sceneRevision);
        var assets = ListPrepAssets(sessionId: sessionId, sceneId: sceneId).Items;

        var recentEvents = projection.Events
            .OrderByDescending(item => item.AtUtc)
            .Take(8)
            .Select(item => new OpsBoardRecentEvent(
                item.EventId,
                item.EventType,
                item.Payload,
                item.AtUtc,
                item.SceneRevision))
            .ToList();

        var unresolved = projection.Events
            .Where(static item => LooksUnresolved(item.EventType, item.Payload))
            .OrderByDescending(item => item.AtUtc)
            .Take(6)
            .Select(item => new OpsBoardUnresolvedItem(
                ItemId: $"ops:{item.EventId}",
                Summary: item.Payload,
                Severity: ResolveSeverity(item.EventType, item.Payload),
                Evidence:
                [
                    new EvidencePointer("ledger-event", item.EventId, item.EventType, item.Payload)
                ]))
            .ToList();

        var tacticalCards = cards
            .Select(item => new OpsBoardTacticalCardSummary(
                item.Id,
                item.Channel,
                item.ApprovalState,
                item.AutonomyMode,
                item.Card?.CardKind,
                item.Card?.Title ?? item.Channel,
                item.Card?.Summary ?? item.Content,
                item.EnqueuedAtUtc,
                item.HiddenUntilUtc))
            .ToList();

        var revealSurfaces = _assets.Values
            .Where(item => string.Equals(item.SessionId, sessionId, StringComparison.OrdinalIgnoreCase))
            .Where(item => string.Equals(item.SceneId, sceneId, StringComparison.OrdinalIgnoreCase))
            .Where(static item => item.Kind is GmPrepAssetKind.RevealSurface or GmPrepAssetKind.PlayerScreen)
            .OrderByDescending(item => item.UpdatedAtUtc)
            .Select(item => new OpsBoardRevealSurface(
                item.AssetId,
                item.Title,
                item.Kind,
                item.Audience,
                item.Status,
                item.LastRevealChannel,
                item.LastRevealedAtUtc,
                item.RevealCount))
            .ToList();

        var checklistItems = assets
            .Where(static item => item.Kind == GmPrepAssetKind.Checklist)
            .SelectMany(item => item.ChecklistItemCount == 0
                ? Array.Empty<(int Total, int Completed)>()
                : [(item.ChecklistItemCount, item.ChecklistCompletedCount)]);
        var totalItems = checklistItems.Sum(item => item.Total);
        var completedItems = checklistItems.Sum(item => item.Completed);

        return new OpsBoardProjection(
            SessionId: sessionId,
            SceneId: sceneId,
            SceneRevision: sceneRevision ?? projection.Events.LastOrDefault()?.SceneRevision ?? sceneId,
            ProjectionFingerprint: projection.ProjectionFingerprint,
            LedgerVersion: projection.Version,
            GeneratedAtUtc: DateTimeOffset.UtcNow,
            RecentEvents: recentEvents,
            UnresolvedItems: unresolved,
            TacticalCards: tacticalCards,
            PrepAssets: assets,
            RevealSurfaces: revealSurfaces,
            ChecklistSummary: new OpsBoardChecklistSummary(
                TotalItems: totalItems,
                CompletedItems: completedItems,
                OpenItems: Math.Max(0, totalItems - completedItems)));
    }

    public GmPrepAssetRecord CreatePrepAsset(GmPrepAssetCreateRequest request)
    {
        var now = DateTimeOffset.UtcNow;
        var assetId = $"prep_{Guid.NewGuid():N}";
        var state = new PrepAssetState
        {
            AssetId = assetId,
            CampaignId = request.CampaignId.Trim(),
            SessionId = NormalizeOptional(request.SessionId),
            SceneId = NormalizeOptional(request.SceneId),
            Title = request.Title.Trim(),
            Kind = request.Kind,
            Audience = request.Audience,
            Summary = NormalizeOptional(request.Summary),
            Body = request.Body.Trim(),
            Tags = NormalizeList(request.Tags),
            ChecklistItems = NormalizeChecklist(request.ChecklistItems),
            Evidence = ResolveEvidence(request.SessionId, request.SceneId, request.SourceEventIds),
            Reusable = request.Reusable,
            Status = request.Kind is GmPrepAssetKind.RevealSurface or GmPrepAssetKind.PlayerScreen ? "ready" : "draft",
            CreatedBy = NormalizeOptional(request.CreatedBy),
            RuntimeFingerprint = NormalizeOptional(request.RuntimeFingerprint),
            CreatedAtUtc = now,
            UpdatedAtUtc = now
        };

        _assets[state.AssetId] = state;
        return ToRecord(state);
    }

    public GmPrepAssetRecord? GetPrepAsset(string assetId)
    {
        return _assets.TryGetValue(assetId, out var state) ? ToRecord(state) : null;
    }

    public GmPrepAssetListResponse ListPrepAssets(
        string? campaignId = null,
        string? sessionId = null,
        string? sceneId = null,
        GmPrepAssetKind? kind = null,
        bool includeReusableCampaignAssets = false)
    {
        var normalizedCampaignId = NormalizeOptional(campaignId);
        var normalizedSessionId = NormalizeOptional(sessionId);
        var normalizedSceneId = NormalizeOptional(sceneId);
        var items = _assets.Values
            .Where(item => kind is null || item.Kind == kind)
            .Where(item => MatchesPrepAssetContext(
                item,
                normalizedCampaignId,
                normalizedSessionId,
                normalizedSceneId,
                includeReusableCampaignAssets))
            .OrderByDescending(item => item.UpdatedAtUtc)
            .ThenBy(item => item.Title, StringComparer.OrdinalIgnoreCase)
            .Select(ToSummary)
            .ToList();

        return new GmPrepAssetListResponse(items, items.Count);
    }

    public GmPrepAssetRecord? UpdateChecklist(string assetId, GmPrepChecklistUpdateRequest request)
    {
        if (!_assets.TryGetValue(assetId, out var state))
        {
            return null;
        }

        lock (state)
        {
            if (state.Kind != GmPrepAssetKind.Checklist)
            {
                return ToRecord(state);
            }

            state.ChecklistItems.Clear();
            state.ChecklistItems.AddRange(NormalizeChecklist(request.ChecklistItems));
            state.Status = state.ChecklistItems.All(item => item.Completed) ? "completed" : "in-progress";
            state.UpdatedAtUtc = DateTimeOffset.UtcNow;
            return ToRecord(state);
        }
    }

    public GmPrepAssetRevealResult Reveal(string assetId, GmPrepAssetRevealRequest request)
    {
        if (!_assets.TryGetValue(assetId, out var state))
        {
            return new GmPrepAssetRevealResult(assetId, "missing", request.ApprovalState, "missing", null, null, DateTimeOffset.UtcNow);
        }

        lock (state)
        {
            if (request.ApprovalState is not "approved")
            {
                state.Status = "approval-required";
                state.UpdatedAtUtc = DateTimeOffset.UtcNow;
                return new GmPrepAssetRevealResult(assetId, "approval-required", request.ApprovalState, state.Status, null, request.Channel, state.UpdatedAtUtc);
            }

            var content = string.IsNullOrWhiteSpace(state.Summary)
                ? state.Body
                : $"{state.Title}: {state.Summary}";
            var message = _outbox.Enqueue(new DeliveryOutboxCreateRequest(
                SessionId: request.SessionId,
                SceneId: request.SceneId,
                SceneRevision: request.SceneRevision,
                Channel: request.Channel,
                Content: content,
                ApprovalState: request.ApprovalState,
                AutonomyMode: request.AutonomyMode,
                Ttl: request.Archive ? null : TimeSpan.FromMinutes(15),
                ProjectionFingerprint: state.RuntimeFingerprint ?? "ops-board",
                CollaborationMode: "local-first",
                Card: new SpiderTacticalCard(
                    CardId: $"reveal_{Guid.NewGuid():N}",
                    SessionId: request.SessionId,
                    SceneId: request.SceneId,
                    SceneRevision: request.SceneRevision,
                    CardKind: state.Kind == GmPrepAssetKind.PlayerScreen ? "player-screen" : "player-reveal",
                    Title: state.Title,
                    Summary: state.Summary ?? state.Body,
                    InterruptionLevel: InterruptionLevel.Low,
                    Status: "delivered",
                    ProjectionFingerprint: state.RuntimeFingerprint ?? "ops-board",
                    Tags: state.Tags,
                    Actions: Array.Empty<SpiderTacticalAction>(),
                    Evidence: state.Evidence,
                    ActionExecutions: Array.Empty<SpiderActionExecutionState>(),
                    CreatedAtUtc: DateTimeOffset.UtcNow,
                    StaleAfterUtc: request.Archive ? null : DateTimeOffset.UtcNow.AddMinutes(15))));

            state.Status = "revealed";
            state.LastRevealChannel = request.Channel;
            state.LastRevealedAtUtc = DateTimeOffset.UtcNow;
            state.RevealCount++;
            state.UpdatedAtUtc = state.LastRevealedAtUtc.Value;

            return new GmPrepAssetRevealResult(
                AssetId: assetId,
                Outcome: "delivered",
                ApprovalState: request.ApprovalState,
                Status: state.Status,
                MessageId: message.Id,
                Channel: message.Channel,
                ProcessedAtUtc: state.UpdatedAtUtc,
                Message: message);
        }
    }

    public IReadOnlyList<GmPrepAssetRecord> ExportPortableAssets(
        string campaignId,
        string sessionId,
        string sceneId,
        IReadOnlyList<string>? assetIds = null,
        bool includeReusableCampaignAssets = false)
    {
        var filter = assetIds is { Count: > 0 }
            ? assetIds.Where(static item => !string.IsNullOrWhiteSpace(item)).Select(static item => item.Trim()).ToHashSet(StringComparer.Ordinal)
            : null;
        var summaries = ListPrepAssets(
            campaignId,
            sessionId,
            sceneId,
            includeReusableCampaignAssets: includeReusableCampaignAssets).Items;
        var exported = new List<GmPrepAssetRecord>(summaries.Count);
        foreach (var summary in summaries)
        {
            if (filter is not null && !filter.Contains(summary.AssetId))
            {
                continue;
            }

            var full = GetPrepAsset(summary.AssetId);
            if (full is not null)
            {
                exported.Add(full);
            }
        }

        return exported;
    }

    private static bool MatchesPrepAssetContext(
        PrepAssetState item,
        string? campaignId,
        string? sessionId,
        string? sceneId,
        bool includeReusableCampaignAssets)
    {
        if (campaignId is not null && !string.Equals(item.CampaignId, campaignId, StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        bool directSessionMatch = sessionId is null || string.Equals(item.SessionId, sessionId, StringComparison.OrdinalIgnoreCase);
        bool directSceneMatch = sceneId is null || string.Equals(item.SceneId, sceneId, StringComparison.OrdinalIgnoreCase);
        if (directSessionMatch && directSceneMatch)
        {
            return true;
        }

        if (!includeReusableCampaignAssets || !item.Reusable || campaignId is null)
        {
            return false;
        }

        bool reusableSessionMatch = sessionId is null
            || string.IsNullOrWhiteSpace(item.SessionId)
            || string.Equals(item.SessionId, sessionId, StringComparison.OrdinalIgnoreCase);
        bool reusableSceneMatch = sceneId is null
            || string.IsNullOrWhiteSpace(item.SceneId)
            || string.Equals(item.SceneId, sceneId, StringComparison.OrdinalIgnoreCase);
        return reusableSessionMatch && reusableSceneMatch;
    }

    public OfflineSyncSurfaceMergeResult ReconcilePortableAssets(IReadOnlyList<OfflineSyncPrepAsset> assets)
    {
        var imported = 0;
        var skipped = 0;
        var conflicts = new List<OfflineSyncConflict>();
        foreach (var asset in assets)
        {
            if (string.IsNullOrWhiteSpace(asset.AssetId))
            {
                skipped++;
                conflicts.Add(new OfflineSyncConflict(
                    Surface: "ops-prep",
                    EntityId: "missing-asset-id",
                    Reason: "invalid-asset",
                    Resolution: "skipped-invalid"));
                continue;
            }

            if (_assets.TryGetValue(asset.AssetId, out var local))
            {
                lock (local)
                {
                    if (asset.UpdatedAtUtc <= local.UpdatedAtUtc)
                    {
                        skipped++;
                        conflicts.Add(new OfflineSyncConflict(
                            Surface: "ops-prep",
                            EntityId: asset.AssetId,
                            Reason: "stale-remote",
                            Resolution: "kept-local",
                            LocalFingerprint: local.UpdatedAtUtc.ToUnixTimeSeconds().ToString(),
                            RemoteFingerprint: asset.UpdatedAtUtc.ToUnixTimeSeconds().ToString()));
                        continue;
                    }

                    local.CampaignId = asset.CampaignId.Trim();
                    local.SessionId = NormalizeOptional(asset.SessionId);
                    local.SceneId = NormalizeOptional(asset.SceneId);
                    local.Title = asset.Title.Trim();
                    local.Kind = ParseEnum(asset.Kind, GmPrepAssetKind.Note);
                    local.Audience = ParseEnum(asset.Audience, GmPrepAssetAudience.Shared);
                    local.Summary = NormalizeOptional(asset.Summary);
                    local.Body = asset.Body.Trim();
                    local.Tags = NormalizeList(asset.Tags);
                    local.ChecklistItems.Clear();
                    local.ChecklistItems.AddRange(asset.ChecklistItems.Select(item => new GmPrepChecklistItem(
                        ItemId: string.IsNullOrWhiteSpace(item.ItemId) ? $"check_{Guid.NewGuid():N}" : item.ItemId.Trim(),
                        Label: string.IsNullOrWhiteSpace(item.Label) ? "Checklist item" : item.Label.Trim(),
                        Completed: item.Completed,
                        Notes: NormalizeOptional(item.Notes))));
                    local.Status = string.IsNullOrWhiteSpace(asset.Status) ? local.Status : asset.Status.Trim();
                    local.UpdatedAtUtc = asset.UpdatedAtUtc;
                    local.LastRevealedAtUtc = asset.LastRevealedAtUtc;
                    local.LastRevealChannel = NormalizeOptional(asset.LastRevealChannel);
                    local.RevealCount = asset.RevealCount;
                }

                imported++;
                continue;
            }

            var state = new PrepAssetState
            {
                AssetId = asset.AssetId.Trim(),
                CampaignId = asset.CampaignId.Trim(),
                SessionId = NormalizeOptional(asset.SessionId),
                SceneId = NormalizeOptional(asset.SceneId),
                Title = asset.Title.Trim(),
                Kind = ParseEnum(asset.Kind, GmPrepAssetKind.Note),
                Audience = ParseEnum(asset.Audience, GmPrepAssetAudience.Shared),
                Summary = NormalizeOptional(asset.Summary),
                Body = asset.Body.Trim(),
                Tags = NormalizeList(asset.Tags),
                ChecklistItems = asset.ChecklistItems.Select(item => new GmPrepChecklistItem(
                    ItemId: string.IsNullOrWhiteSpace(item.ItemId) ? $"check_{Guid.NewGuid():N}" : item.ItemId.Trim(),
                    Label: string.IsNullOrWhiteSpace(item.Label) ? "Checklist item" : item.Label.Trim(),
                    Completed: item.Completed,
                    Notes: NormalizeOptional(item.Notes))).ToList(),
                Evidence = Array.Empty<EvidencePointer>(),
                Reusable = true,
                Status = string.IsNullOrWhiteSpace(asset.Status) ? "draft" : asset.Status.Trim(),
                CreatedBy = NormalizeOptional(asset.CreatedBy),
                RuntimeFingerprint = NormalizeOptional(asset.RuntimeFingerprint),
                CreatedAtUtc = asset.CreatedAtUtc,
                UpdatedAtUtc = asset.UpdatedAtUtc,
                LastRevealedAtUtc = asset.LastRevealedAtUtc,
                LastRevealChannel = NormalizeOptional(asset.LastRevealChannel),
                RevealCount = asset.RevealCount
            };

            _assets[state.AssetId] = state;
            imported++;
        }

        return new OfflineSyncSurfaceMergeResult(
            Surface: "ops-prep",
            ImportedCount: imported,
            SkippedCount: skipped,
            Conflicts: conflicts);
    }

    private EvidencePointer[] ResolveEvidence(string? sessionId, string? sceneId, IReadOnlyList<string>? eventIds)
    {
        if (string.IsNullOrWhiteSpace(sessionId) || string.IsNullOrWhiteSpace(sceneId) || eventIds is not { Count: > 0 })
        {
            return Array.Empty<EvidencePointer>();
        }

        var events = _ledger.GetEvents(sessionId.Trim(), sceneId.Trim());
        return events
            .Where(item => eventIds.Contains(item.EventId, StringComparer.Ordinal))
            .Select(item => new EvidencePointer("ledger-event", item.EventId, item.EventType, item.Payload))
            .ToArray();
    }

    private static string[] NormalizeList(IReadOnlyList<string>? values) =>
        values is null
            ? Array.Empty<string>()
            : values
                .Where(static item => !string.IsNullOrWhiteSpace(item))
                .Select(static item => item.Trim())
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();

    private static T ParseEnum<T>(string raw, T fallback)
        where T : struct, Enum
    {
        return Enum.TryParse<T>(raw, ignoreCase: true, out var parsed)
            ? parsed
            : fallback;
    }

    private static List<GmPrepChecklistItem> NormalizeChecklist(IReadOnlyList<GmPrepChecklistItem>? items)
    {
        if (items is not { Count: > 0 })
        {
            return new List<GmPrepChecklistItem>();
        }

        return items
            .Where(static item => !string.IsNullOrWhiteSpace(item.Label))
            .Select(item => item with
            {
                ItemId = string.IsNullOrWhiteSpace(item.ItemId) ? $"check_{Guid.NewGuid():N}" : item.ItemId.Trim(),
                Label = item.Label.Trim(),
                Notes = NormalizeOptional(item.Notes)
            })
            .ToList();
    }

    private static bool LooksUnresolved(string eventType, string payload)
    {
        var combined = $"{eventType} {payload}";
        return combined.Contains("unresolved", StringComparison.OrdinalIgnoreCase)
            || combined.Contains("open", StringComparison.OrdinalIgnoreCase)
            || combined.Contains("todo", StringComparison.OrdinalIgnoreCase)
            || combined.Contains("threat", StringComparison.OrdinalIgnoreCase)
            || combined.Contains("heat", StringComparison.OrdinalIgnoreCase);
    }

    private static string ResolveSeverity(string eventType, string payload)
    {
        var combined = $"{eventType} {payload}";
        if (combined.Contains("threat", StringComparison.OrdinalIgnoreCase) || combined.Contains("alert", StringComparison.OrdinalIgnoreCase))
        {
            return "high";
        }

        if (combined.Contains("heat", StringComparison.OrdinalIgnoreCase))
        {
            return "medium";
        }

        return "low";
    }

    private static string? NormalizeOptional(string? value) =>
        string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static GmPrepAssetRecord ToRecord(PrepAssetState state) =>
        new(
            state.AssetId,
            state.CampaignId,
            state.SessionId,
            state.SceneId,
            state.Title,
            state.Kind,
            state.Audience,
            state.Summary,
            state.Body,
            state.Tags,
            state.ChecklistItems.ToArray(),
            state.Evidence,
            state.Reusable,
            state.Status,
            state.CreatedBy,
            state.RuntimeFingerprint,
            state.CreatedAtUtc,
            state.UpdatedAtUtc,
            state.LastRevealedAtUtc,
            state.LastRevealChannel,
            state.RevealCount);

    private static GmPrepAssetSummary ToSummary(PrepAssetState state) =>
        new(
            state.AssetId,
            state.CampaignId,
            state.SessionId,
            state.SceneId,
            state.Title,
            state.Kind,
            state.Audience,
            state.Status,
            state.Tags,
            state.Reusable,
            state.ChecklistItems.Count,
            state.ChecklistItems.Count(item => item.Completed),
            state.UpdatedAtUtc,
            state.LastRevealedAtUtc);
}
