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
    DateTimeOffset ScheduledAtUtc);

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
    string? RunId,
    string ListingTitle,
    string? Summary,
    string Visibility,
    string TableContractSummary,
    string AdmissionMode,
    int SeatsTotal,
    bool RequireRunnerDossier,
    bool AllowQuickstartRunner,
    string SchedulingMode,
    int ExpectedDurationMinutes,
    string Platform,
    bool VoiceRequired,
    string ObserverMode,
    IReadOnlyList<string>? ReservedSeatRoles,
    string? Note = null);

public sealed record OpenRunJoinRequestCommand(
    string? DossierId,
    string? QuickstartPackId,
    bool TableContractAcknowledged,
    bool VoiceConsentAcknowledged,
    bool PlatformReady,
    string? Note = null);

public sealed record OpenRunJoinReviewRequest(
    string Decision,
    string? Note = null);

public sealed record OpenRunScheduleRequest(
    DateTimeOffset StartsAtUtc,
    string Timezone,
    string? Note = null);

public sealed record OpenRunMeetingHandoffRequest(
    string ProviderKind,
    string ProviderLabel,
    string AccessPolicy,
    DateTimeOffset ExpiresAtUtc,
    string? Note = null);

public sealed record OpenRunCloseoutRequest(
    string Summary,
    string WorldTickSummary,
    string ConsequenceSummary,
    string NewsTitle,
    string NewsSummary,
    string? NewsSource = null,
    string? NewsUrl = null,
    string? NextSafeAction = null,
    string? Note = null);
