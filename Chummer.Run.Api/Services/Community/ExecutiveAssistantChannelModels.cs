namespace Chummer.Run.Api.Services.Community;

public sealed record ExecutiveAssistantChannelConversationState(
    string ConversationId,
    string UserId,
    string ChannelKind,
    string CounterpartyHandle,
    string CounterpartyHash,
    string Status,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    string? LatestMessageId);

public sealed record ExecutiveAssistantChannelMessageState(
    string MessageId,
    string ConversationId,
    string ChannelKind,
    string Direction,
    string Text,
    string SafetyLabel,
    string DeliveryStatus,
    DateTimeOffset CreatedAtUtc,
    string? CounterpartyHandle,
    string? DeliveryRef,
    string? FailureReason,
    string? IdempotencyKey);
