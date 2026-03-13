using System.ComponentModel.DataAnnotations;
using System.Text.Json.Serialization;
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

public static class ArtifactVisibilityModes
{
    public const string Private = "private";
    public const string Shared = "shared";
    public const string CampaignShared = "campaign-shared";
    public const string Public = "public";
    public const string LocalOnly = "local-only";
}

public static class ArtifactTrustTiers
{
    public const string Official = "official";
    public const string Curated = "curated";
    public const string Private = "private";
    public const string LocalOnly = "local-only";
}

public static class ArtifactInstallStates
{
    public const string Available = "available";
    public const string Installed = "installed";
    public const string Pinned = "pinned";
}

public static class RuntimeBundleReadinessStates
{
    public const string Draft = "draft";
    public const string Ready = "ready";
    public const string Retained = "retained";
}

public sealed record ArtifactCoordinate(
    HubArtifactKind Kind,
    string ArtifactId,
    string Version,
    string RulesetId);

public sealed record ArtifactVersionReference(
    string ArtifactId,
    string Version);

public sealed record ArtifactInstallState(
    string State,
    DateTimeOffset? InstalledAtUtc = null,
    string? InstalledTargetKind = null,
    string? InstalledTargetId = null,
    string? RuntimeFingerprint = null);

public sealed record ArtifactPublicationPointer(
    string OwnerId,
    string Visibility,
    string? PublisherId = null,
    DateTimeOffset? PublishedAtUtc = null);

public sealed record HubArtifactIdentifier(
    string Id,
    HubArtifactKind Kind,
    string Version);

public sealed record HubArtifactManifest(
    string ArtifactId,
    HubArtifactKind Kind,
    string Version,
    string RulesetId,
    string Title,
    string Description,
    string Summary,
    string Visibility,
    string TrustTier,
    string? RuntimeFingerprint = null,
    string? EngineApiVersion = null,
    IReadOnlyList<ArtifactVersionReference>? DependsOn = null,
    IReadOnlyDictionary<string, string>? Labels = null);

public sealed record HubArtifactMetadata(
    string Id,
    string Name,
    HubArtifactKind Kind,
    string Version,
    string RulesetId,
    HubArtifactState State,
    string Visibility,
    string TrustTier,
    string? OwnerId,
    string? PublisherId,
    string? Summary,
    string? Description,
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
    DateTimeOffset? PublishedAtUtc = null,
    DateTimeOffset? LifecycleChangedAtUtc = null)
{
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Owner => string.IsNullOrWhiteSpace(OwnerId) ? null : OwnerId;

    public HubArtifactMetadata(
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
        DateTimeOffset? LifecycleChangedAtUtc)
        : this(
            Id,
            Name,
            Kind,
            Version,
            "sr5",
            State,
            ArtifactVisibilityModes.Shared,
            ArtifactTrustTiers.Curated,
            Owner,
            null,
            Summary,
            null,
            RuntimeFingerprint,
            StateReason,
            SupersededByArtifactId,
            ImmutableRetentionRequired,
            InstallCount,
            ActiveRuntimeRefCount,
            ReviewCount,
            AverageReviewScore,
            CreatedAtUtc,
            UpdatedAtUtc,
            null,
            LifecycleChangedAtUtc)
    {
    }
}

public sealed record HubArtifactRecord(
    HubArtifactManifest Manifest,
    HubArtifactMetadata Metadata,
    ArtifactInstallState Install);

public sealed record HubArtifactCreateRequest(
    [property: Required(AllowEmptyStrings = false), StringLength(200)] string Name,
    HubArtifactKind Kind,
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string Version,
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string RulesetId = "sr5",
    [property: Required(AllowEmptyStrings = false), StringLength(32)] string Visibility = ArtifactVisibilityModes.Shared,
    [property: Required(AllowEmptyStrings = false), StringLength(32)] string TrustTier = ArtifactTrustTiers.Curated,
    string? OwnerId = null,
    string? PublisherId = null,
    string? Summary = null,
    string? Description = null,
    string? RuntimeFingerprint = null,
    string? StateReason = null,
    string? EngineApiVersion = null)
{
    public HubArtifactCreateRequest()
        : this(
            string.Empty,
            default,
            string.Empty,
            "sr5",
            ArtifactVisibilityModes.Shared,
            ArtifactTrustTiers.Curated,
            null,
            null,
            null,
            null,
            null,
            null,
            null)
    {
    }

    [JsonPropertyName("Owner")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Owner { get; init; }

    public string? ResolveOwnerId() => string.IsNullOrWhiteSpace(OwnerId) ? Owner : OwnerId;

    public HubArtifactCreateRequest(
        string Name,
        HubArtifactKind Kind,
        string Version,
        string? Owner,
        string? Summary,
        string? RuntimeFingerprint,
        string? StateReason = null)
        : this(
            Name,
            Kind,
            Version,
            "sr5",
            ArtifactVisibilityModes.Shared,
            ArtifactTrustTiers.Curated,
            Owner,
            null,
            Summary,
            null,
            RuntimeFingerprint,
            StateReason,
            null)
    {
        this.Owner = Owner;
    }
}

public sealed record HubArtifactStateChangeRequest(
    string? RequestedBy,
    HubArtifactState TargetState,
    string? SupersededByArtifactId,
    string? Reason);

public sealed record HubArtifactStateResponse(
    string Id,
    HubArtifactKind Kind,
    string Version,
    string RulesetId,
    HubArtifactState State,
    string? StateReason,
    string? SupersededByArtifactId,
    DateTimeOffset ChangedAtUtc)
{
    public HubArtifactStateResponse(
        string Id,
        HubArtifactKind Kind,
        string Version,
        HubArtifactState State,
        string? StateReason,
        string? SupersededByArtifactId,
        DateTimeOffset ChangedAtUtc)
        : this(Id, Kind, Version, "sr5", State, StateReason, SupersededByArtifactId, ChangedAtUtc)
    {
    }
}

public sealed record HubArtifactDeleteAttemptResponse(
    string Id,
    bool Accepted,
    string Message,
    HubArtifactState State);

public sealed record HubArtifactInstallProjection(
    string ArtifactId,
    HubArtifactKind Kind,
    string Version,
    string RulesetId,
    HubArtifactState State,
    string? SupersededByArtifactId,
    bool ImmutableRetentionRequired,
    bool AcceptingNewInstalls,
    int InstallCount,
    int ActiveRuntimeRefCount,
    bool HasInstallReferences,
    bool HasRuntimeReferences,
    DateTimeOffset LastInstalledAtUtc,
    ArtifactInstallState Install)
{
    public HubArtifactInstallProjection(
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
        DateTimeOffset LastInstalledAtUtc)
        : this(
            ArtifactId,
            Kind,
            Version,
            "sr5",
            State,
            SupersededByArtifactId,
            ImmutableRetentionRequired,
            AcceptingNewInstalls,
            InstallCount,
            ActiveRuntimeRefCount,
            HasInstallReferences,
            HasRuntimeReferences,
            LastInstalledAtUtc,
            new ArtifactInstallState(
                InstallCount > 0 ? ArtifactInstallStates.Installed : ArtifactInstallStates.Available,
                InstallCount > 0 ? LastInstalledAtUtc : null))
    {
    }
}

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
    string? OwnerId = null,
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string RulesetId = "sr5",
    [property: Required(AllowEmptyStrings = false), StringLength(32)] string Visibility = ArtifactVisibilityModes.Shared,
    [property: Required(AllowEmptyStrings = false), StringLength(32)] string TrustTier = ArtifactTrustTiers.Curated,
    string? PublisherId = null,
    string? Description = null,
    string? Summary = null)
{
    public RuntimeBundleIssueRequest()
        : this(
            string.Empty,
            string.Empty,
            default,
            string.Empty,
            string.Empty,
            0,
            false,
            false,
            string.Empty,
            [],
            [],
            [],
            null,
            null,
            "sr5",
            ArtifactVisibilityModes.Shared,
            ArtifactTrustTiers.Curated,
            null,
            null,
            null)
    {
    }

    [JsonPropertyName("Owner")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Owner { get; init; }

    public string? ResolveOwnerId() => string.IsNullOrWhiteSpace(OwnerId) ? Owner : OwnerId;

    public RuntimeBundleIssueRequest(
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
        string? RequestedBy = null,
        string? Owner = null,
        string? Summary = null)
        : this(
            SessionId,
            SceneId,
            Head,
            SourceBundleVersion,
            ProjectionFingerprint,
            ProjectionVersion,
            Ready,
            OfflineCapable,
            CollaborationMode,
            InvalidationSignals,
            IncludedEventTypes,
            SupportedExchangeFormats,
            RequestedBy,
            Owner,
            "sr5",
            ArtifactVisibilityModes.Shared,
            ArtifactTrustTiers.Curated,
            null,
            null,
            Summary)
    {
        this.Owner = Owner;
    }
}

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

public sealed record RuntimeBundleHeadRecord(
    RuntimeBundleHeadProjection Head,
    HubArtifactMetadata Artifact,
    ArtifactInstallState Install);

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
    string RulesetId = "sr5",
    string Visibility = ArtifactVisibilityModes.Shared,
    string TrustTier = ArtifactTrustTiers.Curated,
    HubArtifactState State = HubArtifactState.Active,
    string? Owner = null,
    string? PublisherId = null,
    string? Summary = null,
    string? Description = null,
    string? RuntimeFingerprint = null,
    string? StateReason = null,
    string? SupersededByArtifactId = null,
    DateTimeOffset CreatedAtUtc = default,
    DateTimeOffset UpdatedAtUtc = default,
    DateTimeOffset? LifecycleChangedAtUtc = null,
    int InstallCount = 0,
    int ActiveRuntimeRefCount = 0,
    DateTimeOffset LastInstalledAtUtc = default,
    IReadOnlyList<double>? ReviewScores = null);

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
