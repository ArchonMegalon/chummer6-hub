using System.ComponentModel.DataAnnotations;
using Chummer.Contracts.Receipts;

namespace Chummer.Run.Api.Contracts;

public sealed record OpenRunJoinPolicyProjection(
    string AdmissionMode,
    int SeatsTotal,
    IReadOnlyList<string> ReservedSeatRoles,
    bool RequireRunnerDossier,
    bool AllowQuickstartRunner,
    string RuleEnvironmentFingerprint,
    string SchedulingMode,
    int ExpectedDurationMinutes,
    string CommunicationPlatform,
    bool VoiceRequired,
    string ObserverMode,
    string Summary);

public sealed record OpenRunListingProjection(
    string OpenRunId,
    string WorkspaceId,
    string CampaignId,
    string RunId,
    string RunTitle,
    string ListingTitle,
    string Visibility,
    string Status,
    string Summary,
    string TableContractSummary,
    OpenRunJoinPolicyProjection JoinPolicy,
    string SchedulingPosture,
    bool QuickstartAllowed,
    IReadOnlyList<string> EvidenceLines,
    string CreatedByUserId,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc);

public sealed record OpenRunJoinRequestProjection(
    string RequestId,
    string OpenRunId,
    string ApplicantUserId,
    string ApplicantDisplayName,
    string? DossierId,
    string? RunnerHandle,
    string? QuickstartPackId,
    string PreflightSummary,
    IReadOnlyList<string> Conflicts,
    IReadOnlyList<string> Warnings,
    string NextSafeAction,
    string Status,
    IReadOnlyList<string> EvidenceLines,
    DateTimeOffset SubmittedAtUtc,
    DateTimeOffset UpdatedAtUtc);

public sealed record OpenRunRosterEntryProjection(
    string EntryId,
    string OpenRunId,
    string UserId,
    string DisplayName,
    string? DossierId,
    string? RunnerHandle,
    string SeatStatus,
    string SeatSummary,
    DateTimeOffset UpdatedAtUtc);

public sealed record OpenRunScheduleReceiptProjection(
    string ReceiptId,
    string OpenRunId,
    string SchedulingMode,
    DateTimeOffset StartsAtUtc,
    int ExpectedDurationMinutes,
    string Platform,
    string Timezone,
    string Summary,
    IReadOnlyList<string> EvidenceLines,
    string ScheduledByUserId,
    DateTimeOffset ScheduledAtUtc,
    ReceiptEnvelope? Envelope = null);

public sealed record OpenRunMeetingHandoffProjection(
    string HandoffId,
    string OpenRunId,
    string ProviderKind,
    string ProviderLabel,
    string AccessPolicy,
    DateTimeOffset ExpiresAtUtc,
    IReadOnlyList<string> AcceptedUserIds,
    string Summary,
    IReadOnlyList<string> EvidenceLines,
    string CreatedByUserId,
    DateTimeOffset CreatedAtUtc);

public sealed record OpenRunCloseoutProjection(
    string CloseoutId,
    string OpenRunId,
    string ResolutionApprovalId,
    string WorldTickId,
    string PlayerSafeNewsId,
    string Summary,
    IReadOnlyList<string> EvidenceLines,
    string ClosedByUserId,
    DateTimeOffset ClosedAtUtc);

public sealed record OpenRunOrchestrationProjection(
    OpenRunListingProjection Listing,
    IReadOnlyList<OpenRunJoinRequestProjection> JoinRequests,
    IReadOnlyList<OpenRunRosterEntryProjection> Roster,
    OpenRunScheduleReceiptProjection? Schedule,
    OpenRunMeetingHandoffProjection? MeetingHandoff,
    OpenRunCloseoutProjection? Closeout);

public sealed record OpenRunCreateRequest(
    [property: StringLength(128)] string? RunId,
    [property: Required(AllowEmptyStrings = false), StringLength(160)] string ListingTitle,
    [property: StringLength(4000)] string? Summary,
    [property: Required(AllowEmptyStrings = false), StringLength(32)] string Visibility,
    [property: Required(AllowEmptyStrings = false), StringLength(4000)] string TableContractSummary,
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string AdmissionMode,
    int SeatsTotal,
    bool RequireRunnerDossier,
    bool AllowQuickstartRunner,
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string SchedulingMode,
    int ExpectedDurationMinutes,
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string Platform,
    bool VoiceRequired,
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string ObserverMode,
    [property: MaxLength(8)] IReadOnlyList<string>? ReservedSeatRoles,
    [property: StringLength(1024)] string? Note = null);

public sealed record OpenRunJoinRequestCommand(
    [property: StringLength(128)] string? DossierId,
    [property: StringLength(128)] string? QuickstartPackId,
    bool TableContractAcknowledged,
    bool VoiceConsentAcknowledged,
    bool PlatformReady,
    [property: StringLength(1024)] string? Note = null);

public sealed record OpenRunJoinReviewRequest(
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string Decision,
    [property: StringLength(1024)] string? Note = null);

public sealed record OpenRunScheduleRequest(
    DateTimeOffset StartsAtUtc,
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string Timezone,
    [property: StringLength(1024)] string? Note = null);

public sealed record OpenRunMeetingHandoffRequest(
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string ProviderKind,
    [property: Required(AllowEmptyStrings = false), StringLength(160)] string ProviderLabel,
    [property: Required(AllowEmptyStrings = false), StringLength(64)] string AccessPolicy,
    DateTimeOffset ExpiresAtUtc,
    [property: StringLength(1024)] string? Note = null);

public sealed record OpenRunCloseoutRequest(
    [property: Required(AllowEmptyStrings = false), StringLength(4000)] string Summary,
    [property: Required(AllowEmptyStrings = false), StringLength(4000)] string WorldTickSummary,
    [property: Required(AllowEmptyStrings = false), StringLength(4000)] string ConsequenceSummary,
    [property: Required(AllowEmptyStrings = false), StringLength(160)] string NewsTitle,
    [property: Required(AllowEmptyStrings = false), StringLength(4000)] string NewsSummary,
    [property: StringLength(160)] string? NewsSource = null,
    [property: StringLength(2048)] string? NewsUrl = null,
    [property: StringLength(1024)] string? NextSafeAction = null,
    [property: StringLength(1024)] string? Note = null);
