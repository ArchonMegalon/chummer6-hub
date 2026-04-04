using Chummer.Contracts.Hub;
using Chummer.Run.AI.Services.Session;
using Chummer.Run.AI.Services.Spider;
using Chummer.Run.Contracts.Ops;
using System.Collections.Concurrent;

namespace Chummer.Run.AI.Services.Ops;

public interface IGmOpsBoardService
{
    OpsBoardProjection GetProjection(string sessionId, string sceneId, string? sceneRevision = null);
    GmPrepAssetRecord CreatePrepAsset(GmPrepAssetCreateRequest request);
    GmPrepAssetRecord CreatePrepAssetFromProject(GmPrepAssetCatalogImportRequest request);
    GmPrepAssetRecord? GetPrepAsset(string assetId);
    GmPrepAssetListResponse ListPrepAssets(
        string? campaignId = null,
        string? sessionId = null,
        string? sceneId = null,
        GmPrepAssetKind? kind = null,
        bool includeReusableCampaignAssets = false,
        string? queryText = null);
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
    private static readonly HashSet<string> AllowedPortableAssetStatuses = new(StringComparer.OrdinalIgnoreCase)
    {
        "draft",
        "ready",
        "in-progress",
        "completed",
        "approval-required",
        "revealed"
    };

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
        public GmPrepAssetGovernedProjectReference? GovernedProject { get; set; }
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
            .Select(item =>
            {
                string gmDomain = ResolveGmOpsDomain(item.EventType, item.Payload);
                string severity = ResolveSeverity(item.EventType, item.Payload);
                return new
                {
                    Event = item,
                    DomainPriority = ResolveGmOpsDomainPriority(gmDomain),
                    Severity = severity,
                    SeverityPriority = ResolveSeverityPriority(severity)
                };
            })
            .OrderByDescending(static item => item.SeverityPriority)
            .ThenByDescending(static item => item.DomainPriority)
            .ThenByDescending(static item => item.Event.AtUtc)
            .ThenBy(static item => item.Event.EventId, StringComparer.Ordinal)
            .Take(6)
            .Select(item => new OpsBoardUnresolvedItem(
                ItemId: $"ops:{item.Event.EventId}",
                Summary: item.Event.Payload,
                Severity: item.Severity,
                Evidence:
                [
                    new EvidencePointer("ledger-event", item.Event.EventId, item.Event.EventType, item.Event.Payload)
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
        => CreatePrepAssetCore(request, governedProject: null);

    private GmPrepAssetRecord CreatePrepAssetCore(
        GmPrepAssetCreateRequest request,
        GmPrepAssetGovernedProjectReference? governedProject)
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
            GovernedProject = governedProject,
            CreatedAtUtc = now,
            UpdatedAtUtc = now
        };

        _assets[state.AssetId] = state;
        return ToRecord(state);
    }

    public GmPrepAssetRecord CreatePrepAssetFromProject(GmPrepAssetCatalogImportRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(request.Project);

        string projectKind = HubCatalogItemKinds.NormalizeRequired(request.Project.Summary.Kind, nameof(request.Project));
        if (!SupportsGovernedPacketBinding(projectKind))
        {
            throw new ArgumentOutOfRangeException(nameof(request.Project), $"Unsupported governed prep packet kind '{request.Project.Summary.Kind}'.");
        }

        return CreatePrepAssetCore(new GmPrepAssetCreateRequest(
            CampaignId: request.CampaignId,
            SessionId: request.SessionId,
            SceneId: request.SceneId,
            Title: BuildGovernedPacketTitle(request.Project),
            Kind: GmPrepAssetKind.Note,
            Audience: request.Audience,
            Summary: BuildGovernedPacketSummary(request.Project),
            Body: BuildGovernedPacketBody(request.Project),
            Tags: BuildGovernedPacketTags(request.Project, request.AdditionalTags),
            ChecklistItems: Array.Empty<GmPrepChecklistItem>(),
            SourceEventIds: Array.Empty<string>(),
            Reusable: request.Reusable,
            CreatedBy: request.CreatedBy,
            RuntimeFingerprint: request.RuntimeFingerprint),
            BuildGovernedProjectReference(request.Project));
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
        bool includeReusableCampaignAssets = false,
        string? queryText = null)
    {
        var normalizedCampaignId = NormalizeOptional(campaignId);
        var normalizedSessionId = NormalizeOptional(sessionId);
        var normalizedSceneId = NormalizeOptional(sceneId);
        var normalizedQueryText = NormalizeOptional(queryText);
        var items = _assets.Values
            .Where(item => kind is null || item.Kind == kind)
            .Where(item => MatchesPrepAssetContext(
                item,
                normalizedCampaignId,
                normalizedSessionId,
                normalizedSceneId,
                includeReusableCampaignAssets))
            .Where(item => MatchesQueryText(item, normalizedQueryText))
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

    private static bool MatchesQueryText(PrepAssetState item, string? queryText)
    {
        if (queryText is null)
        {
            return true;
        }

        var searchable = string.Join(' ', new[]
        {
            item.Title,
            item.Summary ?? string.Empty,
            item.Body,
            string.Join(' ', item.Tags),
            item.GovernedProject?.ProjectKind ?? string.Empty,
            item.GovernedProject?.ProjectId ?? string.Empty,
            item.GovernedProject?.Title ?? string.Empty,
            item.GovernedProject?.RulesetId ?? string.Empty,
            item.GovernedProject?.LinkTarget ?? string.Empty,
            string.Join(' ', item.ChecklistItems.Select(static checklist => checklist.Label)),
            string.Join(' ', item.ChecklistItems.Select(static checklist => checklist.Notes ?? string.Empty))
        });
        var normalizedSearchable = BuildCompactSearchableText(searchable);

        if (searchable.Contains(queryText, StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        if (normalizedSearchable.Contains(queryText, StringComparison.OrdinalIgnoreCase))
        {
            return true;
        }

        foreach (var token in TokenizeQueryText(queryText))
        {
            if (!searchable.Contains(token, StringComparison.OrdinalIgnoreCase)
                && !normalizedSearchable.Contains(token, StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }
        }

        return true;
    }

    private static string[] TokenizeQueryText(string queryText)
    {
        HashSet<string> tokens = queryText
            .Split([' ', '\t', '\r', '\n', ',', ';', ':', '/', '-', '_'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Where(static token => !string.IsNullOrWhiteSpace(token))
            .Select(static token => token.Trim().ToLowerInvariant())
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        if ((tokens.Contains("gm") && tokens.Contains("ops")) || (tokens.Contains("gm") && tokens.Contains("op")))
        {
            tokens.Remove("gm");
            tokens.Remove("ops");
            tokens.Remove("op");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if ((tokens.Contains("event") && tokens.Contains("ops")) || (tokens.Contains("event") && tokens.Contains("op")))
        {
            tokens.Remove("ops");
            tokens.Remove("op");
            tokens.Add("eventcontrol");
            tokens.Add("operation");
        }

        if ((tokens.Contains("season") && tokens.Contains("ops")) || (tokens.Contains("season") && tokens.Contains("op")))
        {
            tokens.Remove("ops");
            tokens.Remove("op");
            tokens.Add("operation");
        }

        if ((tokens.Contains("league") && tokens.Contains("ops")) || (tokens.Contains("league") && tokens.Contains("op")))
        {
            tokens.Remove("league");
            tokens.Remove("ops");
            tokens.Remove("op");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if ((tokens.Contains("community") && tokens.Contains("ops")) || (tokens.Contains("community") && tokens.Contains("op")))
        {
            tokens.Remove("community");
            tokens.Remove("ops");
            tokens.Remove("op");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if ((tokens.Contains("league") && tokens.Contains("operations")) || (tokens.Contains("league") && tokens.Contains("operation")))
        {
            tokens.Remove("league");
            tokens.Remove("operations");
            tokens.Remove("operation");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if ((tokens.Contains("community") && tokens.Contains("operations")) || (tokens.Contains("community") && tokens.Contains("operation")))
        {
            tokens.Remove("community");
            tokens.Remove("operations");
            tokens.Remove("operation");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if ((tokens.Contains("league") && tokens.Contains("ctrl")) || (tokens.Contains("league") && tokens.Contains("control")))
        {
            tokens.Remove("league");
            tokens.Remove("ctrl");
            tokens.Remove("control");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if ((tokens.Contains("community") && tokens.Contains("ctrl")) || (tokens.Contains("community") && tokens.Contains("control")))
        {
            tokens.Remove("community");
            tokens.Remove("ctrl");
            tokens.Remove("control");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("event") && tokens.Contains("ctrl"))
        {
            tokens.Remove("ctrl");
            tokens.Add("eventcontrol");
        }

        if (tokens.Contains("season") && tokens.Contains("ctrl"))
        {
            tokens.Remove("ctrl");
            tokens.Add("seasoncontrol");
        }

        if (tokens.Contains("season") && tokens.Contains("control"))
        {
            tokens.Remove("control");
            tokens.Add("eventcontrol");
            tokens.Add("operation");
        }

        if (tokens.Contains("eventctrl"))
        {
            tokens.Remove("eventctrl");
            tokens.Add("eventcontrol");
        }

        if (tokens.Contains("eventcontrols"))
        {
            tokens.Remove("eventcontrols");
            tokens.Add("eventcontrol");
        }

        if (tokens.Contains("seasonctrl"))
        {
            tokens.Remove("seasonctrl");
            tokens.Add("seasoncontrol");
        }

        if (tokens.Contains("gmops"))
        {
            tokens.Remove("gmops");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("gmop"))
        {
            tokens.Remove("gmop");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("eventops"))
        {
            tokens.Remove("eventops");
            tokens.Add("eventcontrol");
            tokens.Add("event");
            tokens.Add("operation");
        }

        if (tokens.Contains("eventop"))
        {
            tokens.Remove("eventop");
            tokens.Add("eventcontrol");
            tokens.Add("event");
            tokens.Add("operation");
        }

        if (tokens.Contains("crewtransfer"))
        {
            tokens.Remove("crewtransfer");
            tokens.Add("crewhandoff");
        }

        if (tokens.Contains("crewmove"))
        {
            tokens.Remove("crewmove");
            tokens.Add("rostermove");
        }

        if (tokens.Contains("seasonops"))
        {
            tokens.Remove("seasonops");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("seasonop"))
        {
            tokens.Remove("seasonop");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("seasoncontrol"))
        {
            tokens.Remove("seasoncontrol");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("seasoncontrols"))
        {
            tokens.Remove("seasoncontrols");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("leagueops"))
        {
            tokens.Remove("leagueops");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("leagueop"))
        {
            tokens.Remove("leagueop");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("leagueoperation"))
        {
            tokens.Remove("leagueoperation");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("leagueoperations"))
        {
            tokens.Remove("leagueoperations");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("communityops"))
        {
            tokens.Remove("communityops");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("communityop"))
        {
            tokens.Remove("communityop");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("communityoperation"))
        {
            tokens.Remove("communityoperation");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("communityoperations"))
        {
            tokens.Remove("communityoperations");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("leaguectrl"))
        {
            tokens.Remove("leaguectrl");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("leaguecontrol"))
        {
            tokens.Remove("leaguecontrol");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("leaguecontrols"))
        {
            tokens.Remove("leaguecontrols");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("communityctrl"))
        {
            tokens.Remove("communityctrl");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("communitycontrol"))
        {
            tokens.Remove("communitycontrol");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        if (tokens.Contains("communitycontrols"))
        {
            tokens.Remove("communitycontrols");
            tokens.Add("eventcontrol");
            tokens.Add("season");
            tokens.Add("operation");
        }

        return tokens.ToArray();
    }

    private static string BuildCompactSearchableText(string value)
    {
        Span<char> buffer = stackalloc char[value.Length];
        var index = 0;
        foreach (char character in value)
        {
            if (char.IsLetterOrDigit(character))
            {
                buffer[index++] = char.ToLowerInvariant(character);
            }
        }

        return index == 0 ? string.Empty : new string(buffer[..index]);
    }

    public OfflineSyncSurfaceMergeResult ReconcilePortableAssets(IReadOnlyList<OfflineSyncPrepAsset> assets)
    {
        var imported = 0;
        var skipped = 0;
        var conflicts = new List<OfflineSyncConflict>();
        var signaturesByAssetVersion = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        var processedNonAmbiguousAssetVersions = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        HashSet<string> ambiguousAssetVersions = new(StringComparer.OrdinalIgnoreCase);
        foreach (var candidate in assets)
        {
            string? normalizedCandidateAssetId = NormalizeOptional(candidate.AssetId);
            if (normalizedCandidateAssetId is null)
            {
                continue;
            }

            string versionKey = BuildPortableAssetVersionKey(normalizedCandidateAssetId, candidate.UpdatedAtUtc);
            string signature = BuildPortableAssetConflictFingerprint(candidate);
            if (!signaturesByAssetVersion.TryGetValue(versionKey, out string? existingSignature))
            {
                signaturesByAssetVersion[versionKey] = signature;
                continue;
            }

            if (!string.Equals(existingSignature, signature, StringComparison.Ordinal))
            {
                ambiguousAssetVersions.Add(versionKey);
            }
        }
        foreach (var asset in assets)
        {
            string? normalizedAssetId = NormalizeOptional(asset.AssetId);
            if (normalizedAssetId is null)
            {
                skipped++;
                conflicts.Add(new OfflineSyncConflict(
                    Surface: "ops-prep",
                    EntityId: "missing-asset-id",
                    Reason: "invalid-asset",
                    Resolution: "skipped-invalid"));
                continue;
            }

            string versionKey = BuildPortableAssetVersionKey(normalizedAssetId, asset.UpdatedAtUtc);
            if (ambiguousAssetVersions.Contains(versionKey))
            {
                skipped++;
                conflicts.Add(new OfflineSyncConflict(
                    Surface: "ops-prep",
                    EntityId: normalizedAssetId,
                    Reason: "duplicate-asset-id-ambiguous",
                    Resolution: "skipped-invalid",
                    LocalFingerprint: asset.UpdatedAtUtc.ToUnixTimeSeconds().ToString(),
                    RemoteFingerprint: "conflicting-payload"));
                continue;
            }

            if (!processedNonAmbiguousAssetVersions.Add(versionKey))
            {
                continue;
            }

            if (!HasRequiredPortableAssetFields(asset))
            {
                skipped++;
                conflicts.Add(new OfflineSyncConflict(
                    Surface: "ops-prep",
                    EntityId: normalizedAssetId,
                    Reason: "invalid-asset-required-fields",
                    Resolution: "skipped-invalid"));
                continue;
            }

            if (!HasValidPortableAssetEnums(asset, out string? enumReason))
            {
                skipped++;
                conflicts.Add(new OfflineSyncConflict(
                    Surface: "ops-prep",
                    EntityId: normalizedAssetId,
                    Reason: enumReason ?? "invalid-asset-enum",
                    Resolution: "skipped-invalid"));
                continue;
            }

            if (!HasValidPortableAssetStatus(asset.Status, out string? statusReason))
            {
                skipped++;
                conflicts.Add(new OfflineSyncConflict(
                    Surface: "ops-prep",
                    EntityId: normalizedAssetId,
                    Reason: statusReason ?? "invalid-asset-status",
                    Resolution: "skipped-invalid"));
                continue;
            }

            if (!HasValidPortableAssetTimeline(asset, out string? timelineReason))
            {
                skipped++;
                conflicts.Add(new OfflineSyncConflict(
                    Surface: "ops-prep",
                    EntityId: normalizedAssetId,
                    Reason: timelineReason ?? "invalid-asset-timeline",
                    Resolution: "skipped-invalid"));
                continue;
            }

            if (!HasConsistentPortableAssetRevealStatus(asset, out string? revealStatusReason))
            {
                skipped++;
                conflicts.Add(new OfflineSyncConflict(
                    Surface: "ops-prep",
                    EntityId: normalizedAssetId,
                    Reason: revealStatusReason ?? "invalid-asset-reveal-status",
                    Resolution: "skipped-invalid"));
                continue;
            }

            if (_assets.TryGetValue(normalizedAssetId, out var local))
            {
                lock (local)
                {
                    string normalizedRemoteCampaignId = asset.CampaignId.Trim();
                    if (!string.Equals(local.CampaignId, normalizedRemoteCampaignId, StringComparison.OrdinalIgnoreCase))
                    {
                        skipped++;
                        conflicts.Add(new OfflineSyncConflict(
                            Surface: "ops-prep",
                            EntityId: normalizedAssetId,
                            Reason: "campaign-mismatch",
                            Resolution: "kept-local",
                            LocalFingerprint: local.CampaignId,
                            RemoteFingerprint: normalizedRemoteCampaignId));
                        continue;
                    }

                    if (asset.UpdatedAtUtc <= local.UpdatedAtUtc)
                    {
                        skipped++;
                        conflicts.Add(new OfflineSyncConflict(
                            Surface: "ops-prep",
                            EntityId: normalizedAssetId,
                            Reason: "stale-remote",
                            Resolution: "kept-local",
                            LocalFingerprint: local.UpdatedAtUtc.ToUnixTimeSeconds().ToString(),
                            RemoteFingerprint: asset.UpdatedAtUtc.ToUnixTimeSeconds().ToString()));
                        continue;
                    }

                    local.CampaignId = normalizedRemoteCampaignId;
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
                    local.Status = NormalizePortableAssetStatus(asset.Status);
                    local.UpdatedAtUtc = asset.UpdatedAtUtc;
                    local.LastRevealedAtUtc = asset.LastRevealedAtUtc;
                    local.LastRevealChannel = NormalizeOptional(asset.LastRevealChannel);
                    local.RevealCount = asset.RevealCount;
                    local.GovernedProject = NormalizeGovernedProject(asset.GovernedProject, out string? governedProjectDropReason);
                    if (asset.GovernedProject is not null && local.GovernedProject is null)
                    {
                        conflicts.Add(new OfflineSyncConflict(
                            Surface: "ops-prep",
                            EntityId: normalizedAssetId,
                            Reason: governedProjectDropReason ?? "invalid-governed-project",
                            Resolution: "dropped-governed-project"));
                    }
                }

                imported++;
                continue;
            }

            var state = new PrepAssetState
            {
                AssetId = normalizedAssetId,
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
                Status = NormalizePortableAssetStatus(asset.Status),
                CreatedBy = NormalizeOptional(asset.CreatedBy),
                RuntimeFingerprint = NormalizeOptional(asset.RuntimeFingerprint),
                GovernedProject = NormalizeGovernedProject(asset.GovernedProject, out string? newAssetGovernedProjectDropReason),
                CreatedAtUtc = asset.CreatedAtUtc,
                UpdatedAtUtc = asset.UpdatedAtUtc,
                LastRevealedAtUtc = asset.LastRevealedAtUtc,
                LastRevealChannel = NormalizeOptional(asset.LastRevealChannel),
                RevealCount = asset.RevealCount
            };

            _assets[state.AssetId] = state;
            if (asset.GovernedProject is not null && state.GovernedProject is null)
            {
                conflicts.Add(new OfflineSyncConflict(
                    Surface: "ops-prep",
                    EntityId: normalizedAssetId,
                    Reason: newAssetGovernedProjectDropReason ?? "invalid-governed-project",
                    Resolution: "dropped-governed-project"));
            }
            imported++;
        }

        return new OfflineSyncSurfaceMergeResult(
            Surface: "ops-prep",
            ImportedCount: imported,
            SkippedCount: skipped,
            Conflicts: conflicts);
    }

    private static string BuildPortableAssetVersionKey(string normalizedAssetId, DateTimeOffset updatedAtUtc) =>
        $"{normalizedAssetId}|{updatedAtUtc.ToUnixTimeMilliseconds()}";

    private static string BuildPortableAssetConflictFingerprint(OfflineSyncPrepAsset asset) =>
        string.Join('|',
            NormalizeOptional(asset.CampaignId) ?? string.Empty,
            NormalizeOptional(asset.SessionId) ?? string.Empty,
            NormalizeOptional(asset.SceneId) ?? string.Empty,
            NormalizeOptional(asset.Title) ?? string.Empty,
            NormalizeOptional(asset.Kind) ?? string.Empty,
            NormalizeOptional(asset.Audience) ?? string.Empty,
            NormalizeOptional(asset.Summary) ?? string.Empty,
            NormalizeOptional(asset.Body) ?? string.Empty,
            NormalizeOptional(asset.Status) ?? string.Empty,
            NormalizeOptional(asset.CreatedBy) ?? string.Empty,
            NormalizeOptional(asset.RuntimeFingerprint) ?? string.Empty,
            asset.CreatedAtUtc.ToUnixTimeMilliseconds().ToString(),
            NormalizeOptional(asset.LastRevealChannel) ?? string.Empty,
            asset.LastRevealedAtUtc?.ToUnixTimeMilliseconds().ToString() ?? string.Empty,
            asset.RevealCount.ToString(),
            string.Join(',', NormalizeList(asset.Tags)),
            string.Join(',', asset.ChecklistItems.Select(static item =>
                $"{NormalizeOptional(item.ItemId) ?? string.Empty}:{NormalizeOptional(item.Label) ?? string.Empty}:{item.Completed}:{NormalizeOptional(item.Notes) ?? string.Empty}")),
            asset.GovernedProject is null
                ? string.Empty
                : string.Join('~',
                    NormalizeOptional(asset.GovernedProject.ProjectKind) ?? string.Empty,
                    NormalizeOptional(asset.GovernedProject.ProjectId) ?? string.Empty,
                    NormalizeOptional(asset.GovernedProject.Title) ?? string.Empty,
                    NormalizeOptional(asset.GovernedProject.RulesetId) ?? string.Empty,
                    NormalizeOptional(asset.GovernedProject.LinkTarget) ?? string.Empty,
                    NormalizeOptional(asset.GovernedProject.TrustTier) ?? string.Empty,
                    NormalizeOptional(asset.GovernedProject.RuntimeFingerprint) ?? string.Empty));

    private static bool HasRequiredPortableAssetFields(OfflineSyncPrepAsset asset) =>
        !string.IsNullOrWhiteSpace(asset.CampaignId)
        && !string.IsNullOrWhiteSpace(asset.Title)
        && !string.IsNullOrWhiteSpace(asset.Body);

    private static bool HasValidPortableAssetEnums(OfflineSyncPrepAsset asset, out string? reason)
    {
        if (!Enum.TryParse<GmPrepAssetKind>(asset.Kind, ignoreCase: true, out _))
        {
            reason = "invalid-asset-kind";
            return false;
        }

        if (!Enum.TryParse<GmPrepAssetAudience>(asset.Audience, ignoreCase: true, out _))
        {
            reason = "invalid-asset-audience";
            return false;
        }

        reason = null;
        return true;
    }

    private static bool HasConsistentPortableAssetRevealStatus(OfflineSyncPrepAsset asset, out string? reason)
    {
        string normalizedStatus = NormalizePortableAssetStatus(asset.Status);
        bool hasRevealTimestamp = asset.LastRevealedAtUtc.HasValue;
        bool hasRevealChannel = !string.IsNullOrWhiteSpace(asset.LastRevealChannel);
        bool hasRevealProof = asset.RevealCount > 0 && hasRevealTimestamp && hasRevealChannel;

        if (string.Equals(normalizedStatus, "revealed", StringComparison.OrdinalIgnoreCase) && !hasRevealProof)
        {
            reason = "invalid-asset-reveal-status";
            return false;
        }

        reason = null;
        return true;
    }

    private static bool HasValidPortableAssetStatus(string? status, out string? reason)
    {
        string? normalized = NormalizeOptional(status);
        if (normalized is null || !AllowedPortableAssetStatuses.Contains(normalized))
        {
            reason = "invalid-asset-status";
            return false;
        }

        reason = null;
        return true;
    }

    private static string NormalizePortableAssetStatus(string status)
    {
        string normalized = status.Trim();
        if (string.Equals(normalized, "in-progress", StringComparison.OrdinalIgnoreCase))
        {
            return "in-progress";
        }

        if (string.Equals(normalized, "approval-required", StringComparison.OrdinalIgnoreCase))
        {
            return "approval-required";
        }

        return normalized.ToLowerInvariant();
    }

    private static bool HasValidPortableAssetTimeline(OfflineSyncPrepAsset asset, out string? reason)
    {
        if (asset.CreatedAtUtc == default || asset.UpdatedAtUtc == default)
        {
            reason = "invalid-asset-timeline";
            return false;
        }

        if (asset.UpdatedAtUtc < asset.CreatedAtUtc)
        {
            reason = "invalid-asset-timeline";
            return false;
        }

        if (asset.LastRevealedAtUtc is { } lastRevealed && (lastRevealed < asset.CreatedAtUtc || lastRevealed > asset.UpdatedAtUtc))
        {
            reason = "invalid-asset-reveal-timestamp";
            return false;
        }

        if (asset.RevealCount < 0)
        {
            reason = "invalid-asset-reveal-count";
            return false;
        }

        bool hasRevealTimestamp = asset.LastRevealedAtUtc.HasValue;
        bool hasRevealChannel = !string.IsNullOrWhiteSpace(asset.LastRevealChannel);
        if (asset.RevealCount == 0 && (hasRevealTimestamp || hasRevealChannel))
        {
            reason = "invalid-asset-reveal-state";
            return false;
        }

        if (asset.RevealCount > 0 && (!hasRevealTimestamp || !hasRevealChannel))
        {
            reason = "invalid-asset-reveal-state";
            return false;
        }

        reason = null;
        return true;
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

    private static GmPrepAssetGovernedProjectReference? NormalizeGovernedProject(
        OfflineSyncPrepGovernedProjectReference? governedProject,
        out string? dropReason)
    {
        if (governedProject is null)
        {
            dropReason = null;
            return null;
        }

        string? projectKind = NormalizeOptional(governedProject.ProjectKind);
        string? projectId = NormalizeOptional(governedProject.ProjectId);
        string? title = NormalizeOptional(governedProject.Title);
        string? rulesetId = NormalizeOptional(governedProject.RulesetId);
        string? linkTarget = NormalizeOptional(governedProject.LinkTarget);
        string? trustTier = NormalizeOptional(governedProject.TrustTier);
        if (projectKind is null
            || projectId is null
            || title is null
            || rulesetId is null
            || linkTarget is null
            || trustTier is null)
        {
            dropReason = "invalid-governed-project-required-fields";
            return null;
        }

        if (!SupportsGovernedPacketBinding(projectKind))
        {
            dropReason = "invalid-governed-project-kind";
            return null;
        }

        dropReason = null;
        return new GmPrepAssetGovernedProjectReference(
            ProjectKind: projectKind,
            ProjectId: projectId,
            Title: title,
            RulesetId: rulesetId,
            LinkTarget: linkTarget,
            TrustTier: trustTier,
            RuntimeFingerprint: NormalizeOptional(governedProject.RuntimeFingerprint));
    }

    private static bool SupportsGovernedPacketBinding(string projectKind) =>
        string.Equals(projectKind, HubCatalogItemKinds.NpcEntry, StringComparison.Ordinal)
        || string.Equals(projectKind, HubCatalogItemKinds.NpcPack, StringComparison.Ordinal)
        || string.Equals(projectKind, HubCatalogItemKinds.EncounterPack, StringComparison.Ordinal);

    private static string BuildGovernedPacketTitle(HubProjectDetailProjection project) =>
        $"Governed prep: {project.Summary.Title}";

    private static string BuildGovernedPacketSummary(HubProjectDetailProjection project) =>
        $"{ResolveCatalogKindLabel(project.Summary.Kind)} packet from {project.Summary.RulesetId} with grounded catalog facts, dependencies, and actions.";

    private static string BuildGovernedPacketBody(HubProjectDetailProjection project)
    {
        List<string> lines =
        [
            $"Catalog packet: {ResolveCatalogKindLabel(project.Summary.Kind)}",
            $"Project id: {project.Summary.ItemId}",
            $"Ruleset: {project.Summary.RulesetId}",
            $"Trust tier: {project.Summary.TrustTier}",
            $"Catalog link: {project.Summary.LinkTarget}",
            $"Description: {project.Summary.Description}"
        ];

        if (!string.IsNullOrWhiteSpace(project.RuntimeFingerprint))
        {
            lines.Add($"Runtime fingerprint: {project.RuntimeFingerprint}");
        }

        if (project.Facts.Count > 0)
        {
            lines.Add("Facts:");
            lines.AddRange(project.Facts.Select(static fact => $"- {fact.Label}: {fact.Value}"));
        }

        if (project.Dependencies.Count > 0)
        {
            lines.Add("Dependencies:");
            lines.AddRange(project.Dependencies.Select(static dependency =>
            {
                string notes = string.IsNullOrWhiteSpace(dependency.Notes) ? string.Empty : $" ({dependency.Notes})";
                return $"- {dependency.Kind} {dependency.ItemKind}:{dependency.ItemId}@{dependency.Version}{notes}";
            }));
        }

        if (project.Actions.Count > 0)
        {
            lines.Add("Actions:");
            lines.AddRange(project.Actions.Select(static action => $"- {action.Label} ({action.Kind})"));
        }

        return string.Join(Environment.NewLine, lines);
    }

    private static string[] BuildGovernedPacketTags(HubProjectDetailProjection project, IReadOnlyList<string>? additionalTags) =>
        NormalizeList(
        [
            "governed-packet",
            "campaign-bindable",
            project.Summary.Kind,
            project.Summary.RulesetId,
            project.Summary.TrustTier,
            ..(additionalTags ?? Array.Empty<string>())
        ]);

    private static GmPrepAssetGovernedProjectReference BuildGovernedProjectReference(HubProjectDetailProjection project) =>
        new(
            ProjectKind: project.Summary.Kind,
            ProjectId: project.Summary.ItemId,
            Title: project.Summary.Title,
            RulesetId: project.Summary.RulesetId,
            LinkTarget: project.Summary.LinkTarget,
            TrustTier: project.Summary.TrustTier,
            RuntimeFingerprint: NormalizeOptional(project.RuntimeFingerprint));

    private static string ResolveCatalogKindLabel(string kind) =>
        kind switch
        {
            HubCatalogItemKinds.NpcEntry => "NPC entry",
            HubCatalogItemKinds.NpcPack => "NPC pack",
            HubCatalogItemKinds.EncounterPack => "Encounter pack",
            _ => "Catalog packet"
        };

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

    private static string ResolveGmOpsDomain(string eventType, string payload)
    {
        var combined = $"{eventType} {payload}";
        if (ContainsAny(combined,
            "opposition",
            "hostile",
            "adversary",
            "encounter",
            "encounters",
            "enemy",
            "enemies",
            "opfor",
            "opforce",
            "op-force",
            "op force",
            "op_for",
            "threat"))
        {
            return "opposition";
        }

        if (ContainsAny(combined,
            "event control",
            "event-control",
            "event_control",
            "eventcontrol",
            "eventcontrols",
            "eventctrl",
            "seasoncontrol",
            "seasoncontrols",
            "seasonctrl",
            "eventops",
            "eventop",
            "event-ops",
            "event_op",
            "event ops",
            "gmops",
            "gmop",
            "gm ops",
            "gm-ops",
            "gm_op",
            "leagueops",
            "leagueop",
            "leagueoperation",
            "leagueoperations",
            "leaguecontrol",
            "leaguecontrols",
            "leaguectrl",
            "league control",
            "league-control",
            "league_control",
            "league operation",
            "league-operation",
            "league_operation",
            "league ops",
            "league-ops",
            "league_op",
            "communityops",
            "communityop",
            "communityoperation",
            "communityoperations",
            "communitycontrol",
            "communitycontrols",
            "communityctrl",
            "community control",
            "community-control",
            "community_control",
            "community operation",
            "community-operation",
            "community_operation",
            "community ops",
            "community-ops",
            "community_op",
            "season",
            "seasonops",
            "seasonop",
            "checkpoint",
            "timeline",
            "operation",
            "operations",
            "prep launch",
            "prep_launch",
            "preplaunch",
            "preplaunches",
            "travel prefetch",
            "travel_prefetch",
            "travelprefetch",
            "travelprefetches"))
        {
            return "event_control";
        }

        if (ContainsAny(combined,
                "schedule",
                "schedules",
                "scheduled",
                "calendar",
                "calendars")
            && ContainsAny(combined,
                "event",
                "season",
                "operation",
                "operations",
                "checkpoint",
                "prep",
                "travel",
                "window"))
        {
            return "event_control";
        }

        if (ContainsAny(combined,
            "roster",
            "crew",
            "rostermove",
            "crewmove",
            "rostertransfer",
            "rosterhandoff",
            "crewhandoff",
            "crewtransfer",
            "handoff",
            "transfer",
            "assignment",
            "reassign",
            "bench",
            "rotation"))
        {
            return "roster_movement";
        }

        if (ContainsAny(combined,
                "prep library",
                "prep-library",
                "prep_library",
                "preplibrary",
                "prep packet",
                "prep_packet",
                "preppacket",
                "packet prep",
                "prep dossier",
                "prepdossier",
                "prep briefing",
                "prepbriefing",
                "prep brief",
                "prep binder",
                "prep catalog")
            || (ContainsAny(combined,
                    "packet",
                    "packets",
                    "library",
                    "runbook",
                    "playbook",
                    "briefing",
                    "briefings",
                    "dossier",
                    "binder",
                    "catalog")
                && ContainsAny(combined,
                    "prep",
                    "gm",
                    "campaign",
                    "session")))
        {
            return "prep_library";
        }

        return "general";
    }

    private static bool ContainsAny(string value, params string[] candidates) =>
        candidates.Any(candidate => value.Contains(candidate, StringComparison.OrdinalIgnoreCase));

    private static int ResolveGmOpsDomainPriority(string domain)
        => domain switch
        {
            "opposition" => 4,
            "event_control" => 3,
            "roster_movement" => 2,
            "prep_library" => 2,
            "general" => 1,
            _ => 0
        };

    private static int ResolveSeverityPriority(string severity)
        => severity switch
        {
            "high" => 3,
            "medium" => 2,
            "low" => 1,
            _ => 0
        };

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
            state.RevealCount,
            state.GovernedProject);

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
            state.LastRevealedAtUtc,
            state.GovernedProject);
}
