using System.ComponentModel.DataAnnotations;

namespace Chummer.Run.Contracts.Community;

public sealed record HubUserDto(
    string UserId,
    string SubjectId,
    string DisplayName,
    string Handle,
    string Visibility,
    string Timezone,
    string CountryCode,
    IReadOnlyList<string> LinkedPrincipals,
    IReadOnlyList<string> GroupIds,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc)
{
    public string Email { get; init; } = string.Empty;
}

public sealed record UpsertHubUserProfileRequest(
    [StringLength(128)] string? SubjectId,
    string? DisplayName = null,
    string? Handle = null,
    string Visibility = "private",
    string? Timezone = null,
    string? CountryCode = null);

public sealed record HubUserExperienceDto(
    string UserId,
    IReadOnlyList<string> LaneInterests,
    bool FollowHorizons,
    bool BetaInterest,
    bool OnboardingCompleted,
    DateTimeOffset? OnboardingCompletedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    bool ImpactCloseoutNotifications = false,
    bool PublicContributionProfileOptIn = false,
    bool BlackLedgerNewsEmail = false,
    IReadOnlyList<WorkspacePrepLibrarySearchHistoryItem>? WorkspacePrepLibrarySearchHistory = null,
    IReadOnlyList<string>? BlackLedgerWorldsFollowed = null);

public sealed record WorkspacePrepLibrarySearchHistoryItem(
    string WorkspaceId,
    string Query,
    DateTimeOffset LastUsedUtc);

public sealed record UpsertHubUserExperienceRequest(
    [StringLength(128)] string? SubjectId,
    IReadOnlyList<string>? LaneInterests = null,
    bool? FollowHorizons = null,
    bool? BetaInterest = null,
    bool? OnboardingCompleted = null,
    bool? ImpactCloseoutNotifications = null,
    bool? PublicContributionProfileOptIn = null,
    bool? BlackLedgerNewsEmail = null,
    IReadOnlyList<string>? BlackLedgerWorldsFollowed = null);

public sealed record OriginDossierPublicationImportRequest(
    [Required(AllowEmptyStrings = false)] string? ProjectId,
    string? Title,
    string? RunnerAlias,
    string? PublicationState,
    string? BookArtifactUrl,
    string? AudiobookshelfShareUrl,
    string? DossierVideoUrl,
    string? StorySceneCoverUrl,
    bool ProviderAuthoredManuscriptImported,
    bool UndetectableHumanizerApplied,
    bool BookArtifactVerified,
    bool DossierVideoVerified,
    bool StorySceneCoverUsesSelectedCharacterFace,
    bool AudiobookshelfPlaybackVerified,
    bool TelegramShareDelivered,
    string? SourcePacketPath,
    string? SourcePacketReceiptPath,
    string? CanonAuditReceiptPath,
    string? ProviderManuscriptPath,
    string? ProviderManuscriptReceiptPath,
    string? HumanizerReceiptPath,
    string? BookArtifactPath,
    string? BookArtifactReceiptPath,
    string? StorySceneCoverPath,
    string? StorySceneCoverReceiptPath,
    string? AudiobookPath,
    string? AudiobookshelfImportReceiptPath,
    string? DossierVideoPath,
    string? DossierVideoReceiptPath,
    string? TelegramShareDeliveryReceiptPath,
    IReadOnlyList<string>? MissingGoldRequirements = null,
    string? FamilyName = null,
    string? GivenName = null,
    string? RunnerName = null,
    string? OriginEditionNamespace = null,
    string? AudiobookshelfDossierShareUrl = null,
    string? AudiobookshelfAudiobookShareUrl = null,
    string? EbookArtifactPath = null,
    string? EbookAudiobookshelfImportReceiptPath = null,
    string? CoverConsistencyReceiptPath = null,
    string? MoviePosterPath = null,
    string? MovieSubtitlesPath = null,
    string? MovieStoryboardPath = null,
    string? FinalNoFallbackNoSentinelAuditReceiptPath = null,
    string? ProviderManuscriptAccountAlias = null,
    string? AudiobookProviderAccountAlias = null,
    string? StorySceneCoverAccountAlias = null,
    string? DossierVideoAccountAlias = null,
    string? BookPackagingAccountAlias = null,
    IReadOnlyList<OriginDossierPortraitChoiceDto>? PortraitChoices = null,
    IReadOnlyList<OriginDossierAudiobookVoiceOptionDto>? AudiobookVoiceOptions = null,
    IReadOnlyList<OriginDossierSceneHighlightDto>? SceneHighlights = null,
    string? RunnerLinkCode = null,
    IReadOnlyList<OriginDossierStoryLinkDto>? StoryLinks = null);

public sealed record OriginDossierPublicationImportResultDto(
    string ProjectId,
    string Title,
    string RunnerAlias,
    string PublicationState,
    string? ChummerRunOwnerUrl,
    string? BookArtifactUrl,
    string? AudiobookshelfShareUrl,
    string? DossierVideoUrl,
    string? StorySceneCoverUrl,
    bool ProviderAuthoredManuscriptImported,
    bool UndetectableHumanizerApplied,
    bool BookArtifactVerified,
    bool DossierVideoVerified,
    bool StorySceneCoverUsesSelectedCharacterFace,
    bool AudiobookshelfPlaybackVerified,
    bool TelegramShareDelivered,
    bool RequiresAuthenticatedChummerRunUser,
    bool GoldReady,
    IReadOnlyList<string> MissingGoldRequirements,
    string? FamilyName = null,
    string? GivenName = null,
    string? RunnerName = null,
    string? OriginEditionNamespace = null,
    string? AudiobookshelfDossierShareUrl = null,
    string? AudiobookshelfAudiobookShareUrl = null,
    IReadOnlyList<OriginDossierPortraitChoiceDto>? PortraitChoices = null,
    IReadOnlyList<OriginDossierAudiobookVoiceOptionDto>? AudiobookVoiceOptions = null,
    IReadOnlyList<OriginDossierSceneHighlightDto>? SceneHighlights = null,
    bool FullStoryVerified = false,
    bool EbookHandoffReady = false,
    string? RunnerLinkCode = null,
    IReadOnlyList<OriginDossierStoryLinkDto>? StoryLinks = null);

public sealed record OriginDossierPortraitChoiceDto(
    string PortraitId,
    string Title,
    string Summary,
    string? PreviewUrl = null,
    bool Selected = false);

public sealed record OriginDossierAudiobookVoiceOptionDto(
    string VoiceId,
    string Label,
    string Summary,
    bool Recommended = false,
    bool Selected = false);

public sealed record OriginDossierSceneHighlightDto(
    string SceneId,
    string ChapterLabel,
    string Title,
    string Summary,
    bool Selected = false);

public sealed record OriginDossierStoryLinkDto(
    string LinkId,
    string LinkedRunnerAlias,
    string Summary,
    string Status = "accepted",
    string? LinkedProjectId = null,
    string? LinkedRunnerLinkCode = null,
    bool IntegrateIntoStory = true);

public sealed record OriginDossierProviderCreditReservationRequest(
    string? UserId,
    string? Email,
    string? ProjectId,
    string? BookKind,
    string? PrivacyClassification,
    string? Provider,
    string? ProviderAccountAlias,
    int CreditsRequested,
    bool SourcePacketApproved,
    bool ExternalProcessingConsent,
    bool ChronologyValidated,
    bool OutlineApproved,
    bool VoiceSampleApproved,
    bool CanonPreflightPassed,
    bool HumanReviewAssigned,
    bool AuditOnly = false);

public sealed record OriginDossierProviderCreditReservationResult(
    string Status,
    bool ProviderBurnAllowed,
    string? ReservationId,
    string? UserId,
    string? ProjectId,
    string? Provider,
    string? ProviderAccountAlias,
    int CreditsReserved,
    IReadOnlyList<string> BlockedRequirements,
    DateTimeOffset CheckedAtUtc,
    bool AuditOnly = false,
    bool ProviderBurnWouldBeAllowed = false);

public sealed record SubscribrWebhookRequest(
    string? EventId,
    string? EventType,
    string? ProviderScriptId,
    string? ProviderChannelId,
    string? ProviderIdeaId,
    string? PacketPath,
    string? MarkdownExportPath);

public sealed record SubscribrWebhookResult(
    string EventId,
    string Status,
    string SignatureStatus,
    string ReplayStatus,
    string ValidationStatus,
    string? PacketId,
    string? ReceiptPath,
    string? RejectionReason,
    DateTimeOffset ProcessedAtUtc);

public sealed record GroupRoleDto(
    string Role,
    string DisplayName,
    bool CanManageMembers,
    bool CanIssueCodes);

public sealed record GroupMembershipDto(
    string MembershipId,
    string GroupId,
    string UserId,
    string Role,
    DateTimeOffset JoinedAtUtc)
{
    public string? RunnerDossierId { get; init; }
    public string? RunnerHandle { get; init; }
    public string? RunnerTicketId { get; init; }
}

public sealed record GroupDto(
    string GroupId,
    string GroupType,
    string Name,
    string Visibility,
    string OwnerUserId,
    IReadOnlyList<string> Capabilities,
    IReadOnlyList<GroupMembershipDto> Memberships,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc);

public sealed record JoinCodeDto(
    string JoinCodeId,
    string Code,
    string GroupId,
    string Role,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset? ExpiresAtUtc,
    int Uses)
{
    public int? MaxUses { get; init; }
    public DateTimeOffset? RevokedAtUtc { get; init; }
    public string InviteUrl { get; init; } = string.Empty;
}

public sealed record RunnerTicketDto(
    string RunnerTicketId,
    string JoinCodeId,
    string GroupId,
    string UserId,
    string DossierId,
    string RunnerHandle,
    string Status,
    DateTimeOffset IssuedAtUtc,
    DateTimeOffset ConsumedAtUtc);

public sealed record CreateGroupRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [Required(AllowEmptyStrings = false), StringLength(128)] string Name,
    string GroupType = "booster",
    string Visibility = "private",
    IReadOnlyList<string>? Capabilities = null);

public sealed record CreateJoinCodeRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    string Role = "member",
    TimeSpan? Ttl = null,
    [Range(1, 1000)] int? MaxUses = 25);

public sealed record UpdateGroupRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [Required(AllowEmptyStrings = false), StringLength(128)] string Name,
    [Required(AllowEmptyStrings = false), StringLength(32)] string Visibility = "private");

public sealed record CreateRunnerRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [Required(AllowEmptyStrings = false), StringLength(64)] string RunnerHandle,
    [StringLength(128)] string? DisplayName = null);

public sealed record JoinGroupByCodeRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [Required(AllowEmptyStrings = false), StringLength(128)] string Code,
    [StringLength(128)] string? DossierId = null);

public sealed record ChronicleProjectDto(
    string ChronicleProjectId,
    string GroupId,
    string CreatedByUserId,
    string Title,
    string BookKind,
    string Audience,
    string Status,
    string SourceSummary,
    string ModelKey,
    int TargetChapterCount,
    int TargetWordsPerChapter,
    bool IncludeRunnerRoster,
    IReadOnlyList<string> RunnerRoster,
    bool IncludeCover,
    bool IncludeTranslation,
    bool IncludeAudiobook,
    bool ExternalProcessingConsent,
    bool ParticipantConsentConfirmed,
    bool RedactionReviewed,
    bool SourceRightsConfirmed,
    int SourcePacketVersion,
    string SourcePacketSha256,
    int EstimatedCredits,
    string Provider,
    bool OperatorRequired,
    bool UnattendedAutomationAllowed,
    string? ExternalProjectRef,
    string? ArtifactUrl,
    string? ArtifactSha256,
    string? ExportFormat,
    DateTimeOffset? SourceApprovedAtUtc,
    DateTimeOffset? HandoffApprovedAtUtc,
    DateTimeOffset? OutlineApprovedAtUtc,
    DateTimeOffset? ArtifactImportedAtUtc,
    DateTimeOffset? PublicationApprovedAtUtc,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc)
{
    public IReadOnlyList<ChronicleSourcePacketRevisionDto> SourcePacketRevisions { get; init; } = [];
    public bool SpoilerReviewConfirmed { get; init; }
    public DateTimeOffset? UploadApprovedAtUtc { get; init; }
    public DateTimeOffset? GenerationApprovedAtUtc { get; init; }
    public DateTimeOffset? ExternalSendApprovedAtUtc { get; init; }
}

public sealed record ChronicleSourcePacketRevisionDto(
    int Version,
    string Sha256,
    DateTimeOffset CreatedAtUtc);

public sealed record CreateChronicleProjectRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [Required(AllowEmptyStrings = false), StringLength(160)] string Title,
    [Required(AllowEmptyStrings = false), StringLength(32)] string BookKind,
    [Required(AllowEmptyStrings = false), StringLength(32)] string Audience,
    [Required(AllowEmptyStrings = false), StringLength(4000)] string SourceSummary,
    [Required(AllowEmptyStrings = false), StringLength(32)] string ModelKey,
    [Range(1, 40)] int TargetChapterCount,
    [Range(100, 5000)] int TargetWordsPerChapter,
    bool IncludeRunnerRoster,
    bool IncludeCover,
    bool IncludeTranslation,
    bool IncludeAudiobook,
    bool ExternalProcessingConsent,
    bool ParticipantConsentConfirmed,
    bool RedactionReviewed,
    bool SourceRightsConfirmed,
    bool SpoilerReviewConfirmed = false);

public sealed record ReviseChronicleProjectRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [Required(AllowEmptyStrings = false), StringLength(160)] string Title,
    [Required(AllowEmptyStrings = false), StringLength(32)] string BookKind,
    [Required(AllowEmptyStrings = false), StringLength(32)] string Audience,
    [Required(AllowEmptyStrings = false), StringLength(4000)] string SourceSummary,
    [Required(AllowEmptyStrings = false), StringLength(32)] string ModelKey,
    [Range(1, 40)] int TargetChapterCount,
    [Range(100, 5000)] int TargetWordsPerChapter,
    bool IncludeRunnerRoster,
    bool IncludeCover,
    bool IncludeTranslation,
    bool IncludeAudiobook,
    bool ExternalProcessingConsent,
    bool ParticipantConsentConfirmed,
    bool RedactionReviewed,
    bool SourceRightsConfirmed,
    bool SpoilerReviewConfirmed = false);

public sealed record UpdateChronicleProjectRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [Required(AllowEmptyStrings = false), StringLength(32)] string Action,
    [StringLength(256)] string? ExternalProjectRef = null,
    [StringLength(2048)] string? ArtifactUrl = null,
    [StringLength(64)] string? ArtifactSha256 = null,
    [StringLength(16)] string? ExportFormat = null);
