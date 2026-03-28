using System.ComponentModel.DataAnnotations;

namespace Chummer.Control.Contracts.Support;

public static class SupportCaseKinds
{
    public const string CrashReport = "crash_report";
    public const string BugReport = "bug_report";
    public const string Feedback = "feedback";
    public const string InstallHelp = "install_help";
}

public static class SupportCaseStatuses
{
    public const string New = "new";
    public const string Clustered = "clustered";
    public const string Routed = "routed";
    public const string AwaitingEvidence = "awaiting_evidence";
    public const string Accepted = "accepted";
    public const string Fixed = "fixed";
    public const string Deferred = "deferred";
    public const string Rejected = "rejected";
    public const string ReleasedToReporterChannel = "released_to_reporter_channel";
    public const string UserNotified = "user_notified";
}

public static class SupportCaseSourceKinds
{
    public const string HubAccount = "hub_account";
    public const string DesktopCrash = "desktop_crash";
    public const string DesktopFeedback = "desktop_feedback";
    public const string PublicWeb = "public_web";
    public const string FleetAutomation = "fleet_automation";
}

public static class SupportCaseVerificationStates
{
    public const string ConfirmedFixed = "confirmed_fixed";
    public const string StillBroken = "still_broken";
}

public sealed record SupportCaseTimelineEvent(
    string EventId,
    string Status,
    string Summary,
    DateTimeOffset OccurredAtUtc,
    string? Actor = null,
    IReadOnlyDictionary<string, string>? Metadata = null);

public sealed record SupportCaseAttachmentProjection(
    string AttachmentId,
    string FileName,
    string ContentType,
    long SizeBytes,
    DateTimeOffset UploadedAtUtc,
    string? DownloadHref = null);

public sealed record SupportCaseProjection(
    string CaseId,
    string ClusterKey,
    string Kind,
    string Status,
    string Title,
    string Summary,
    string Detail,
    string CandidateOwnerRepo,
    bool DesignImpactSuspected,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    string Source,
    string? ReporterEmail = null,
    string? ReporterUserId = null,
    string? ReporterSubjectId = null,
    string? InstallationId = null,
    string? ApplicationVersion = null,
    string? ReleaseChannel = null,
    string? HeadId = null,
    string? Platform = null,
    string? Arch = null,
    string? FixedVersion = null,
    string? FixedChannel = null,
    DateTimeOffset? ReleasedToReporterChannelAtUtc = null,
    DateTimeOffset? UserNotifiedAtUtc = null,
    string? ReporterVerificationState = null,
    string? ReporterVerificationNote = null,
    DateTimeOffset? ReporterVerifiedAtUtc = null,
    IReadOnlyList<string>? RelatedIds = null,
    IReadOnlyList<SupportCaseTimelineEvent>? Timeline = null,
    IReadOnlyList<SupportCaseAttachmentProjection>? Attachments = null);

public sealed record SupportCaseSubmitRequest(
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string Kind,
    [property: Required(AllowEmptyStrings = false), StringLength(160)] string Title,
    [property: Required(AllowEmptyStrings = false), StringLength(280)] string Summary,
    [property: Required(AllowEmptyStrings = false)] string Detail,
    [property: StringLength(256)] string? ReporterEmail = null,
    [property: StringLength(64)] string? InstallationId = null,
    [property: StringLength(64)] string? ApplicationVersion = null,
    [property: StringLength(64)] string? ReleaseChannel = null,
    [property: StringLength(64)] string? HeadId = null,
    [property: StringLength(64)] string? Platform = null,
    [property: StringLength(32)] string? Arch = null,
    [property: StringLength(64)] string? Source = null);

public sealed record SupportCaseTransitionRequest(
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string TargetStatus,
    [property: StringLength(160)] string? Note = null,
    [property: StringLength(64)] string? FixedVersion = null,
    [property: StringLength(64)] string? FixedChannel = null,
    [property: StringLength(64)] string? Actor = null);

public sealed record SupportCaseNotificationRequest(
    [property: Required(AllowEmptyStrings = false), StringLength(160)] string Note,
    [property: StringLength(64)] string? Actor = null,
    [property: StringLength(64)] string? Channel = null);

public sealed record SupportCaseVerificationRequest(
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string Outcome,
    [property: StringLength(160)] string? Note = null,
    [property: StringLength(64)] string? Actor = null);

public sealed record SupportCaseListResponse(
    IReadOnlyList<SupportCaseProjection> Items,
    int TotalCount);

public static class SupportAssistantConfidenceLevels
{
    public const string CaseTruth = "case_truth";
    public const string CanonHelp = "canon_help";
    public const string NeedsCase = "needs_case";
}

public sealed record SupportAssistantRequest(
    [Required(AllowEmptyStrings = false), StringLength(2000)] string Query,
    [StringLength(64)] string? CaseId = null,
    [StringLength(64)] string? InstallationId = null,
    [Range(1, 5)] int MaxCitations = 3);

public sealed record SupportAssistantCitation(
    string SourceKind,
    string Label,
    string Summary,
    string? Status = null,
    string? Href = null);

public sealed record SupportAssistantAction(
    string ActionId,
    string Label,
    string Href,
    string Reason);

public sealed record SupportAssistantResponse(
    string Answer,
    string Confidence,
    bool EscalationRecommended,
    IReadOnlyList<SupportAssistantCitation> Citations,
    IReadOnlyList<SupportAssistantAction> Actions);

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
    [StringLength(64)] string? InstallationId = null,
    [StringLength(256)] string? InstallationGrantToken = null,
    [StringLength(64)] string? UserId = null,
    [StringLength(128)] string? SubjectId = null,
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
