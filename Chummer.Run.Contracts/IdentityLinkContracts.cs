using System.ComponentModel.DataAnnotations;

namespace Chummer.Run.Contracts.Community;

public sealed record LinkedIdentityDto(
    string IdentityLinkId,
    string UserId,
    string Provider,
    string LinkKind,
    string ProviderSubject,
    string DisplayLabel,
    string Status,
    string VerificationPolicy,
    bool IsPrimary,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    DateTimeOffset? VerifiedAtUtc,
    string? Note = null);

public sealed record ChannelLinkDto(
    string ChannelLinkId,
    string UserId,
    string ChannelKind,
    string DisplayLabel,
    string Status,
    bool OfficialChannel,
    bool NotificationsEnabled,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    string? Note = null);

public sealed record AccountLinkSummaryDto(
    HubUserDto User,
    IReadOnlyList<LinkedIdentityDto> LinkedIdentities,
    IReadOnlyList<ChannelLinkDto> ChannelLinks,
    string RecommendedPrimaryAuth,
    string RecoveryPosture,
    string OrchestratorBrain,
    string OfficialCompanionChannel,
    IReadOnlyList<string> SupportedIdentityProviders,
    IReadOnlyList<string> SupportedChannels,
    IReadOnlyList<string> FutureCapabilities);

public sealed record LinkEmailIdentityRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [Required(AllowEmptyStrings = false), EmailAddress, StringLength(256)] string Email,
    bool MakePrimary = true);

public sealed record ConfirmIdentityLinkRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [Required(AllowEmptyStrings = false), StringLength(128)] string IdentityLinkId);

public sealed record LinkExternalIdentityRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [Required(AllowEmptyStrings = false), StringLength(32)] string Provider,
    [Required(AllowEmptyStrings = false), StringLength(256)] string ProviderSubject,
    string? DisplayLabel = null,
    bool MakePrimary = false);

public sealed record LinkChannelRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [Required(AllowEmptyStrings = false), StringLength(64)] string ChannelKind,
    string? ChannelHandle = null,
    bool NotificationsEnabled = true);
