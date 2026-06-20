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

public sealed record StartRecoveryEmailLinkRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    [Required(AllowEmptyStrings = false), EmailAddress, StringLength(256)] string Email,
    string? NextPath = null);

public sealed record RecoveryEmailLinkStartResponse(
    string Email,
    string LinkStatus,
    string DeliveryMode,
    string PreviewNote,
    string? PreviewHref,
    DateTimeOffset ExpiresAtUtc);

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

public sealed record LinkChannelToExecutiveAssistantRequest(
    [Required(AllowEmptyStrings = false), StringLength(128)] string SubjectId,
    string? ChannelHandle = null);

public sealed record ChannelDeepLinkResponse(
    string ChannelKind,
    string ChannelHandle,
    string DeepLink,
    string QrImageUrl,
    string? AlternateDeepLink = null);

public sealed record ExecutiveAssistantChannelMessageDto(
    string MessageId,
    string ConversationId,
    string ChannelKind,
    string Direction,
    string Text,
    string SafetyLabel,
    string DeliveryStatus,
    string? CounterpartyHandle,
    string? DeliveryRef,
    string? FailureReason,
    string? IdempotencyKey,
    DateTimeOffset CreatedAtUtc);

public sealed record ExecutiveAssistantChannelConversationDto(
    string ConversationId,
    string UserId,
    string ChannelKind,
    string CounterpartyHandle,
    string CounterpartyHash,
    string Status,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    IReadOnlyList<ExecutiveAssistantChannelMessageDto> Messages);

public sealed record ExecutiveAssistantChannelSendRequest(
    [System.ComponentModel.DataAnnotations.Required(AllowEmptyStrings = false), System.ComponentModel.DataAnnotations.StringLength(2048)]
    string MessageText,
    [System.ComponentModel.DataAnnotations.StringLength(128)] string? CounterpartyHandle,
    [System.ComponentModel.DataAnnotations.StringLength(128)] string? ConversationId = null,
    [System.ComponentModel.DataAnnotations.StringLength(128)] string? IdempotencyKey = null);

public sealed record ExecutiveAssistantChannelIncomingMessageRequest(
    [System.ComponentModel.DataAnnotations.StringLength(128)] string? SubjectId,
    [System.ComponentModel.DataAnnotations.StringLength(128)] string? RecipientHandle,
    [System.ComponentModel.DataAnnotations.Required(AllowEmptyStrings = false), System.ComponentModel.DataAnnotations.StringLength(128)]
    string CounterpartyHandle,
    [System.ComponentModel.DataAnnotations.Required(AllowEmptyStrings = false), System.ComponentModel.DataAnnotations.StringLength(2048)]
    string MessageText,
    [System.ComponentModel.DataAnnotations.StringLength(128)] string? MessageId = null,
    [System.ComponentModel.DataAnnotations.StringLength(128)] string? ConversationId = null,
    DateTimeOffset? ReceivedAtUtc = null);

public sealed record ExecutiveAssistantChannelSendResult(
    string ConversationId,
    string MessageId,
    string Status,
    string? DeliveryRef,
    string? FailureReason,
    string IdempotencyKey,
    DateTimeOffset AttemptedAtUtc,
    bool Duplicate);
