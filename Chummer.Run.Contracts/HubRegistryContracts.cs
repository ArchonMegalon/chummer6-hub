using System.ComponentModel.DataAnnotations;
using Chummer.Run.Contracts.Observability;

namespace Chummer.Run.Contracts.Registry;

public enum HubArtifactKind
{
    RulePack,
    RuleProfile,
    BuildKit,
    NpcVault,
    BuildIdea,
    RuntimeBundle
}

public enum RuntimeBundleHeadKind
{
    Session,
    Mobile,
    Offline
}

public enum HubArtifactState
{
    Active,
    Delisted,
    Deprecated,
    Superseded,
    BannedButRetained
}

public sealed record HubArtifactIdentifier(
    string Id,
    HubArtifactKind Kind,
    string Version);

public sealed record HubArtifactCreateRequest(
    [property: Required(AllowEmptyStrings = false), StringLength(200)] string Name,
    HubArtifactKind Kind,
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string Version,
    string? Owner,
    string? Summary,
    string? RuntimeFingerprint,
    string? StateReason = null);

public sealed record HubArtifactMetadata(
    string Id,
    string Name,
    HubArtifactKind Kind,
    string Version,
    HubArtifactState State,
    string? Owner,
    string? Summary,
    string? RuntimeFingerprint,
    string? StateReason,
    string? SupersededByArtifactId,
    bool ImmutableRetentionRequired,
    int InstallCount,
    int ActiveRuntimeRefCount,
    int ReviewCount,
    double AverageReviewScore,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? LifecycleChangedAtUtc);

public sealed record HubArtifactStateChangeRequest(
    string? RequestedBy,
    HubArtifactState TargetState,
    string? SupersededByArtifactId,
    string? Reason);

public sealed record HubArtifactStateResponse(
    string Id,
    HubArtifactKind Kind,
    string Version,
    HubArtifactState State,
    string? StateReason,
    string? SupersededByArtifactId,
    DateTimeOffset ChangedAtUtc);

public sealed record HubArtifactDeleteAttemptResponse(
    string Id,
    bool Accepted,
    string Message,
    HubArtifactState State);

public sealed record HubArtifactInstallProjection(
    string ArtifactId,
    HubArtifactKind Kind,
    string Version,
    HubArtifactState State,
    string? SupersededByArtifactId,
    bool ImmutableRetentionRequired,
    bool AcceptingNewInstalls,
    int InstallCount,
    int ActiveRuntimeRefCount,
    bool HasInstallReferences,
    bool HasRuntimeReferences,
    DateTimeOffset LastInstalledAtUtc);

public sealed record HubInstallEvent(
    [property: Required(AllowEmptyStrings = false), StringLength(128)] string ArtifactId,
    [property: Required(AllowEmptyStrings = false), StringLength(128)] string UserId,
    DateTimeOffset InstalledAtUtc,
    bool ActiveRuntimeRef);

public sealed record HubReviewListResponse(
    string ArtifactId,
    double AverageScore,
    int ReviewCount,
    IReadOnlyList<HubReviewResponse> Reviews);

public sealed record HubReviewRequest(
    [property: Required(AllowEmptyStrings = false), StringLength(128)] string ArtifactId,
    [property: Range(0, 10)] int Score,
    string? Comment = null);

public sealed record HubReviewResponse(
    string ArtifactId,
    double AverageScore,
    int ReviewCount);

public sealed record RuntimeBundleIssueRequest(
    [property: Required(AllowEmptyStrings = false), StringLength(128)] string SessionId,
    [property: Required(AllowEmptyStrings = false), StringLength(128)] string SceneId,
    RuntimeBundleHeadKind Head,
    [property: Required(AllowEmptyStrings = false), StringLength(128)] string SourceBundleVersion,
    [property: Required(AllowEmptyStrings = false), StringLength(128)] string ProjectionFingerprint,
    int ProjectionVersion,
    bool Ready,
    bool OfflineCapable,
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string CollaborationMode,
    IReadOnlyList<string> InvalidationSignals,
    IReadOnlyList<string> IncludedEventTypes,
    IReadOnlyList<string> SupportedExchangeFormats,
    string? RequestedBy = null,
    string? Owner = null,
    string? Summary = null);

public sealed record RuntimeBundleArtifactProjection(
    string ArtifactId,
    string BundleFamilyId,
    string SessionId,
    string SceneId,
    RuntimeBundleHeadKind Head,
    string SourceBundleVersion,
    string ProjectionFingerprint,
    int ProjectionVersion,
    bool Ready,
    bool OfflineCapable,
    string CollaborationMode,
    IReadOnlyList<string> InvalidationSignals,
    IReadOnlyList<string> IncludedEventTypes,
    IReadOnlyList<string> SupportedExchangeFormats,
    string? RequestedBy,
    DateTimeOffset IssuedAtUtc,
    string? PreviousArtifactId);

public sealed record RuntimeBundleHeadProjection(
    string BundleFamilyId,
    string SessionId,
    string SceneId,
    RuntimeBundleHeadKind Head,
    string CurrentArtifactId,
    string CurrentVersion,
    string SourceBundleVersion,
    string ProjectionFingerprint,
    int ProjectionVersion,
    bool Ready,
    bool OfflineCapable,
    string CollaborationMode,
    IReadOnlyList<string> SupportedExchangeFormats,
    DateTimeOffset IssuedAtUtc,
    string? PreviousArtifactId);

public sealed record RuntimeBundleIssueResponse(
    HubArtifactMetadata Artifact,
    RuntimeBundleArtifactProjection Projection,
    RuntimeBundleHeadProjection Head,
    bool CreatedNewArtifact);

public sealed record RuntimeBundleHeadListResponse(
    string BundleFamilyId,
    string SessionId,
    string SceneId,
    IReadOnlyList<RuntimeBundleHeadProjection> Heads);

public sealed record HubArtifactStoreArtifactSnapshot(
    string Id,
    string Name,
    HubArtifactKind Kind,
    string Version,
    HubArtifactState State,
    string? Owner,
    string? Summary,
    string? RuntimeFingerprint,
    string? StateReason,
    string? SupersededByArtifactId,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? LifecycleChangedAtUtc,
    int InstallCount,
    int ActiveRuntimeRefCount,
    DateTimeOffset LastInstalledAtUtc,
    IReadOnlyList<double> ReviewScores);

public sealed record HubArtifactStoreRuntimeBundleArtifactSnapshot(
    string ArtifactId,
    string BundleFamilyId,
    string SessionId,
    string SceneId,
    RuntimeBundleHeadKind Head,
    string SourceBundleVersion,
    string ProjectionFingerprint,
    int ProjectionVersion,
    bool Ready,
    bool OfflineCapable,
    string CollaborationMode,
    IReadOnlyList<string> InvalidationSignals,
    IReadOnlyList<string> IncludedEventTypes,
    IReadOnlyList<string> SupportedExchangeFormats,
    string? RequestedBy,
    DateTimeOffset IssuedAtUtc,
    string? PreviousArtifactId);

public sealed record HubArtifactStoreRuntimeBundleHeadSnapshot(
    string BundleFamilyId,
    string SessionId,
    string SceneId,
    RuntimeBundleHeadKind Head,
    string CurrentArtifactId,
    string CurrentVersion,
    string SourceBundleVersion,
    string ProjectionFingerprint,
    int ProjectionVersion,
    bool Ready,
    bool OfflineCapable,
    string CollaborationMode,
    IReadOnlyList<string> SupportedExchangeFormats,
    DateTimeOffset IssuedAtUtc,
    string? PreviousArtifactId);

public sealed record HubArtifactStoreBackupPackage(
    DateTimeOffset ExportedAtUtc,
    IReadOnlyList<HubArtifactStoreArtifactSnapshot> Artifacts,
    IReadOnlyList<HubArtifactStoreRuntimeBundleArtifactSnapshot> RuntimeBundleArtifacts,
    IReadOnlyList<HubArtifactStoreRuntimeBundleHeadSnapshot> RuntimeBundleHeads,
    IReadOnlyList<PipelineDeadLetterEntry> DeadLetters,
    long UpsertCount,
    long RuntimeIssueCount,
    long RuntimeIssueIdempotentCount,
    DateTimeOffset? LastRuntimeIssueReplayAtUtc,
    long InstallCount,
    long ReviewCount,
    string ContractFamily = "hub_state_backup_v1");
