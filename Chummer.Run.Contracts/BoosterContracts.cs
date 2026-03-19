using System.ComponentModel.DataAnnotations;

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
    string RequestedLaneType,
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
    IReadOnlyList<SponsorSessionEventDto> Events);

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
    [property: Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [property: Required(AllowEmptyStrings = false), StringLength(128)] string GroupId,
    string? CampaignId = null,
    string? ProjectId = null,
    string Label = "general");

public sealed record RedeemBoostCodeRequest(
    [property: Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [property: Required(AllowEmptyStrings = false), StringLength(128)] string Code);

public sealed record CreateSponsorSessionRequest(
    [property: Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [property: Required(AllowEmptyStrings = false), StringLength(128)] string ProjectId,
    string? GroupId = null,
    string? SubjectLabel = null,
    string? BoostCode = null,
    string? CampaignId = null,
    string Visibility = "group",
    string RequestedLaneType = "participant_burst");
