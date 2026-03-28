using Chummer.Play.Core.Application;

namespace Chummer.Play.Core.PlayApi;

public static class PlayApiRoutes
{
    public const string Bootstrap = "/api/play/bootstrap";
    public const string Projection = "/api/play/projection/{sessionId}";
    public const string Reconnect = "/api/play/reconnect";
    public const string Observe = "/api/play/observe/{sessionId}";
    public const string ContinuityClaim = "/api/play/continuity/claim";
    public const string Sync = "/api/play/sync";
    public const string QuickAction = "/api/play/quick-action";
    public const string Resume = "/api/play/resume/{sessionId}";
    public const string CachePressure = "/api/play/cache-pressure/{sessionId}";
}

public sealed record BrowserSessionShellProbe(
    bool OfflineCapable,
    bool RuntimeBundleCached,
    bool MediaCacheEnabled
);

public sealed record EngineSessionEnvelope(
    string SessionId,
    string SceneId,
    string SceneRevision,
    string RuntimeFingerprint
);

public sealed record EngineSessionCursor(
    EngineSessionEnvelope Session,
    long AppliedThroughSequence
);

public sealed record PlayBootstrapRequest(
    EngineSessionEnvelope Session,
    PlaySurfaceRole Role
);

public sealed record PlayBootstrapResponse(
    string Project,
    PlaySessionProjection Projection,
    PlayShellSnapshot ActiveShell,
    IReadOnlyList<PlayShellSnapshot> AvailableShells,
    BrowserSessionShellProbe ShellProbe,
    IReadOnlyList<string> RoleCapabilities,
    IReadOnlyList<PlayTacticalSpiderCard> TacticalSpiderCards,
    IReadOnlyList<PlayCoachHint> CoachHints,
    IReadOnlyList<PlayQuickAction> QuickActions
);

public sealed record PlayShellSnapshot(
    PlaySurfaceRole Role,
    string ShellName,
    string Summary,
    IReadOnlyList<string> RequiredCapabilities
);

public sealed record PlayTacticalSpiderCard(
    string CardId,
    string Title,
    string Summary,
    string RequiredCapability
);

public sealed record PlayCoachHint(
    string HintId,
    string Message
);

public sealed record PlayQuickAction(
    string ActionId,
    string Label,
    string RequiredCapability,
    bool StaleProtected
);

public sealed record PlaySessionProjection(
    EngineSessionCursor Cursor,
    IReadOnlyList<string> Timeline,
    DateTimeOffset GeneratedAtUtc
);

public sealed record PlayReconnectRequest(
    EngineSessionCursor Cursor
);

public sealed record PlayReconnectResponse(
    PlaySessionProjection Projection,
    Chummer.Play.Core.Sync.SyncCheckpoint ResumeCheckpoint,
    Chummer.Play.Core.Offline.OfflineLedgerEnvelope Ledger
);

public sealed record PlayContinuityClaimRequest(
    EngineSessionCursor Cursor,
    PlaySurfaceRole Role,
    string DeviceId,
    string ObserverId
);

public sealed record PlayObserverContinuity(
    string ObserverId,
    string DeviceId,
    PlaySurfaceRole Role,
    long ObservedThroughSequence,
    DateTimeOffset ObservedAtUtc,
    string ContinuityToken
);

public sealed record PlayContinuityClaimResponse(
    bool Accepted,
    bool Stale,
    string Reason,
    PlaySessionProjection Projection,
    Chummer.Play.Core.Sync.SyncCheckpoint Checkpoint,
    PlayObserverContinuity Continuity,
    string DeepLinkOwnerRoute
);

public sealed record PlayObserveResponse(
    string SessionId,
    PlaySessionProjection Projection,
    Chummer.Play.Core.Sync.SyncCheckpoint Checkpoint,
    PlayObserverContinuity? Continuity,
    PlayRuntimeBundleMetadata? RuntimeBundle
);

public sealed record PlaySyncRequest(
    EngineSessionCursor Cursor,
    IReadOnlyList<string> PendingEvents
);

public sealed record PlaySyncResponse(
    bool Accepted,
    bool Stale,
    PlaySessionProjection Projection,
    Chummer.Play.Core.Sync.SyncCheckpoint Checkpoint,
    int AcceptedEventCount
);

public sealed record PlayQuickActionRequest(
    EngineSessionCursor Cursor,
    PlaySurfaceRole Role,
    string ActionId
);

public sealed record PlayQuickActionResponse(
    bool Accepted,
    bool Stale,
    string Reason,
    PlaySessionProjection Projection,
    Chummer.Play.Core.Sync.SyncCheckpoint Checkpoint
);

public sealed record PlayRuntimeBundleMetadata(
    string RuntimeFingerprint,
    string SceneRevision,
    string BundleTag,
    DateTimeOffset CachedAtUtc,
    DateTimeOffset LastValidatedAtUtc
);

public sealed record PlayCachePressureSnapshot(
    int RuntimeBundleCount,
    int RuntimeBundleQuota,
    bool BackpressureActive,
    int EvictedEntryCount,
    IReadOnlyList<string> EvictedSessionIds,
    DateTimeOffset MeasuredAtUtc
);

public sealed record PlaySupportClosureNotice(
    string StatusLabel,
    string KnownIssueSummary,
    string FixAvailabilitySummary,
    string NextSafeAction,
    string FollowThroughHref,
    string? CaseId = null
);

public sealed record PlayResumeResponse(
    string SessionId,
    PlaySurfaceRole Role,
    string DeepLinkOwnerRoute,
    PlayBootstrapResponse Bootstrap,
    Chummer.Play.Core.Sync.SyncCheckpoint? Checkpoint,
    PlayRuntimeBundleMetadata? RuntimeBundle,
    PlayCachePressureSnapshot CachePressure,
    PlaySupportClosureNotice? SupportNotice = null
);
