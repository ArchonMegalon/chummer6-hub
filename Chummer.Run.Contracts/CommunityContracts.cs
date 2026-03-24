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
    DateTimeOffset UpdatedAtUtc);

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
    DateTimeOffset UpdatedAtUtc);

public sealed record UpsertHubUserExperienceRequest(
    [StringLength(128)] string? SubjectId,
    IReadOnlyList<string>? LaneInterests = null,
    bool? FollowHorizons = null,
    bool? BetaInterest = null,
    bool? OnboardingCompleted = null);

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
    DateTimeOffset JoinedAtUtc);

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
    int Uses);

public sealed record CreateGroupRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [Required(AllowEmptyStrings = false), StringLength(128)] string Name,
    string GroupType = "booster",
    string Visibility = "private",
    IReadOnlyList<string>? Capabilities = null);

public sealed record CreateJoinCodeRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    string Role = "member",
    TimeSpan? Ttl = null);

public sealed record JoinGroupByCodeRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [Required(AllowEmptyStrings = false), StringLength(128)] string Code);
