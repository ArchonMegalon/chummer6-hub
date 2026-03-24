using System.ComponentModel.DataAnnotations;

namespace Chummer.Run.Contracts.Support;

public sealed record CrashEnvelope(
    [Required(AllowEmptyStrings = false), StringLength(64)] string CrashId,
    [Required(AllowEmptyStrings = false), StringLength(64)] string HeadId,
    [Required(AllowEmptyStrings = false), StringLength(64)] string ApplicationVersion,
    [Required(AllowEmptyStrings = false), StringLength(128)] string RuntimeVersion,
    [Required(AllowEmptyStrings = false), StringLength(256)] string OperatingSystem,
    [Required(AllowEmptyStrings = false), StringLength(32)] string ProcessArchitecture,
    [Required(AllowEmptyStrings = false), StringLength(128)] string CrashFingerprint,
    [Required(AllowEmptyStrings = false), StringLength(256)] string ExceptionType,
    [Required(AllowEmptyStrings = false)] string ExceptionMessage,
    [Required(AllowEmptyStrings = false)] string ExceptionDetail,
    DateTimeOffset CapturedAtUtc,
    bool IsTerminating = true,
    [StringLength(64)] string? ReleaseChannel = null,
    [StringLength(64)] string? Platform = null,
    [StringLength(64)] string? DesktopHead = null,
    [StringLength(64)] string? RuntimeHead = null,
    [StringLength(128)] string? LastActionCategory = null,
    IReadOnlyList<string>? LogTail = null,
    bool FullDiagnosticsOptIn = false);

public sealed record CrashRegistryContextProjection(
    string? ApplicationVersion,
    string? ReleaseChannel,
    string? Platform,
    string? ProcessArchitecture,
    string? DesktopHead,
    string? RuntimeHead,
    bool UpdateAvailable,
    string? UpdateTargetVersion,
    string Source);

public sealed record CrashIncidentProjection(
    string IncidentId,
    string ClusterId,
    string WorkItemId,
    DateTimeOffset ReceivedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    string Status,
    CrashEnvelope Envelope,
    CrashRegistryContextProjection RegistryContext);

public sealed record CrashClusterProjection(
    string ClusterId,
    string CrashFingerprint,
    string ExceptionType,
    string Status,
    int OccurrenceCount,
    DateTimeOffset FirstSeenAtUtc,
    DateTimeOffset LastSeenAtUtc,
    IReadOnlyList<string> IncidentIds,
    IReadOnlyList<string> ApplicationVersions,
    IReadOnlyList<string> ReleaseChannels,
    IReadOnlyList<string> Platforms);

public sealed record CrashWorkItemProjection(
    string WorkItemId,
    string ClusterId,
    string Status,
    string Summary,
    string CandidateOwnerRepo,
    bool RegressionSuspected,
    int OccurrenceCount,
    DateTimeOffset FirstSeenAtUtc,
    DateTimeOffset LastSeenAtUtc,
    CrashRegistryContextProjection RegistryContext,
    IReadOnlyList<string> IncidentIds);

public sealed record CrashIntakeAcceptedResponse(
    CrashIncidentProjection Incident,
    CrashClusterProjection Cluster,
    CrashWorkItemProjection WorkItem,
    bool ForwardedForAutomation);

public sealed record CrashClusterListResponse(
    IReadOnlyList<CrashClusterProjection> Items,
    int TotalCount);

public sealed record CrashWorkItemListResponse(
    IReadOnlyList<CrashWorkItemProjection> Items,
    int TotalCount);
