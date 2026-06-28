using System.ComponentModel.DataAnnotations;
using System.Text.Json.Serialization;

namespace Chummer.Run.Contracts.Boosters;

public sealed record BoostCampaignDto(
    string CampaignId,
    string GroupId,
    string ProjectId,
    string Title,
    string Status,
    DateTimeOffset CreatedAtUtc);

public sealed record BoostCodeDto(
    string BoostCodeId,
    string Code,
    string GroupId,
    string CampaignId,
    string CreatedByUserId,
    string Status,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset? RedeemedAtUtc,
    string? RedeemedByUserId);

public sealed record SponsorSessionEventDto(
    string EventId,
    string Kind,
    string Message,
    DateTimeOffset CreatedAtUtc);

public sealed record SponsorSessionStatusDto(
    string SponsorSessionId,
    string UserId,
    string GroupId,
    string ProjectId,
    string? ParticipantCodexCode,
    string RequestedLaneType,
    string RequestedLaneRole,
    string Visibility,
    string Status,
    bool Consented,
    string? FleetLaneId,
    string? BoostCampaignId,
    string? BoostCodeId,
    string? DeviceAuthVerificationUri,
    string? DeviceAuthUserCode,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? ConsentedAtUtc,
    DateTimeOffset? ActivatedAtUtc,
    DateTimeOffset? StoppedAtUtc,
    IReadOnlyList<SponsorSessionEventDto> Events,
    string AuthorizationTier = "unknown",
    string TierSource = "unknown",
    DateTimeOffset? AuthorizedAtUtc = null,
    [property: JsonPropertyName("credentialHandlePresent")] bool CredentialHandlePresent = false);

public sealed record SponsorSessionProjectionDto(
    string SponsorSessionId,
    string Status,
    int ReceiptCount,
    int LandedSlices,
    int EstimatedPoints,
    DateTimeOffset? LastReceiptAtUtc,
    IReadOnlyList<string> ActiveLaneIds);

public sealed record GroupContributionProjectionDto(
    string GroupId,
    int ReceiptCount,
    int LandedSlices,
    int EstimatedPoints,
    IReadOnlyList<string> ActiveSponsorSessionIds);

public sealed record CreateBoostCodeRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [Required(AllowEmptyStrings = false), StringLength(128)] string GroupId,
    string? CampaignId = null,
    string? ProjectId = null,
    string Label = "general");

public sealed record RedeemBoostCodeRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [Required(AllowEmptyStrings = false), StringLength(128)] string Code);

public sealed record CreateSponsorSessionRequest(
    [StringLength(128)] string? SubjectId,
    [Required(AllowEmptyStrings = false), StringLength(128)] string ProjectId,
    [StringLength(128)] string? GroupId = null,
    [StringLength(160)] string? SubjectLabel = null,
    [StringLength(64)] string? ParticipantCodexCode = null,
    [StringLength(128)] string? BoostCode = null,
    [StringLength(128)] string? CampaignId = null,
    [StringLength(32)] string Visibility = "group",
    [StringLength(64)] string RequestedLaneType = "participant_burst",
    [StringLength(64)] string RequestedLaneRole = "coding",
    [StringLength(64)] string? AuthorizationTier = null,
    [StringLength(64)] string? TierSource = null);
