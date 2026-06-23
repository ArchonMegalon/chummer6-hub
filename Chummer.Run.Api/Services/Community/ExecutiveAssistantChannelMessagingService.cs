using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Services.Community;

public sealed class ExecutiveAssistantChannelMessagingService
{
    private const string ConnectorDispatchTool = "connector.dispatch";
    private const string DeliverySendAction = "delivery.send";
    private const string DefaultEaBaseUrl = "http://127.0.0.1:8090";
    private static readonly string[] NonProductionEaBaseUrlMarkers =
    [
        "support-progress-mock",
        "127.0.0.1",
        "localhost",
    ];

    private const string TelegramChannelKind = "telegram_official_bot";
    private const string WhatsappChannelKind = "whatsapp_official_business";
    private const string TelegramDeliveryChannel = "telegram";
    private const string WhatsappDeliveryChannel = "whatsapp";
    private const string WhatsappBusinessTransport = "whatsapp_business";
    private const string WhatsappWebSessionTransport = "whatsapp_web_session";

    private const string SubjectMessageSafetyLabel = "safe";
    private const string MessageDirectionIncoming = "incoming";
    private const string MessageDirectionOutbound = "outbound";

    private const string MessageStatusQueued = "queued";
    private const string MessageStatusSent = "sent";
    private const string MessageStatusReceived = "received";
    private const string MessageStatusFailed = "failed_send";
    private const string MessageStatusUnconfigured = "suppressed_ea_unconfigured";

    private const string ConversationStatusActive = "active";
    private const string ConversationStatusFailed = "failed";

    private const int MaxMessagesPerConversation = 500;
    private const int MaxConversationsPerUserChannel = 100;
    private static readonly TimeSpan InboundDuplicateWindow = TimeSpan.FromMinutes(2);

    private readonly HttpClient _httpClient;
    private readonly CommunityStore _store;
    private readonly AccountService _accounts;
    private readonly IConfiguration _configuration;
    private readonly ILogger<ExecutiveAssistantChannelMessagingService> _logger;
    private readonly TeableExecutiveAssistantChannelService? _teable;

    public ExecutiveAssistantChannelMessagingService(
        HttpClient httpClient,
        CommunityStore store,
        AccountService accounts,
        IConfiguration configuration,
        ILogger<ExecutiveAssistantChannelMessagingService>? logger = null,
        TeableExecutiveAssistantChannelService? teable = null)
    {
        _httpClient = httpClient;
        _store = store;
        _accounts = accounts;
        _configuration = configuration;
        _logger = logger ?? NullLogger<ExecutiveAssistantChannelMessagingService>.Instance;
        _teable = teable;
    }

    public IReadOnlyList<ExecutiveAssistantChannelConversationDto> ListConversations(string subjectId, string channelKind, int take = 24)
    {
        string normalizedSubject = AccountService.NormalizeRequired(subjectId, nameof(subjectId));
        string normalizedChannelKind = NormalizeChannelKind(channelKind);
        HubUserDto user = _accounts.EnsureUser(normalizedSubject);
        int clampedTake = Math.Clamp(take, 1, 100);

        lock (_store.Gate)
        {
            return _store.ExecutiveAssistantChannelConversations
                .Where(item =>
                    string.Equals(item.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.ChannelKind, normalizedChannelKind, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(item => item.UpdatedAtUtc)
                .Take(clampedTake)
                .Select(item => ToConversationDto(item, messages: Array.Empty<ExecutiveAssistantChannelMessageDto>()))
                .ToArray();
        }
    }

    public ExecutiveAssistantChannelConversationDto? GetConversation(string subjectId, string channelKind, string conversationId)
    {
        string normalizedSubject = AccountService.NormalizeRequired(subjectId, nameof(subjectId));
        string normalizedChannelKind = NormalizeChannelKind(channelKind);
        string normalizedConversationId = AccountService.NormalizeRequired(conversationId, nameof(conversationId));
        HubUserDto user = _accounts.EnsureUser(normalizedSubject);

        lock (_store.Gate)
        {
            ExecutiveAssistantChannelConversationState? conversation = _store.ExecutiveAssistantChannelConversations.FirstOrDefault(item =>
                string.Equals(item.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.ChannelKind, normalizedChannelKind, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.ConversationId, normalizedConversationId, StringComparison.OrdinalIgnoreCase));

            return conversation is null
                ? null
                : ToConversationDto(
                    conversation,
                    _store.ExecutiveAssistantChannelMessages
                        .Where(message => string.Equals(message.ConversationId, normalizedConversationId, StringComparison.OrdinalIgnoreCase))
                        .OrderBy(static message => message.CreatedAtUtc)
                        .Take(MaxMessagesPerConversation)
                        .Select(ToMessageDto)
                        .ToArray());
        }
    }

    public async Task<ExecutiveAssistantChannelSendResult> SendMessageAsync(
        string subjectId,
        string channelKind,
        ExecutiveAssistantChannelSendRequest request,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);

        string normalizedSubject = AccountService.NormalizeRequired(subjectId, nameof(subjectId));
        string normalizedChannelKind = NormalizeChannelKind(channelKind);
        string messageText = AccountService.NormalizeRequired(request.MessageText, nameof(request.MessageText));
        HubUserDto user = _accounts.EnsureUser(normalizedSubject);

        ChannelLinkDto? link = GetLinkedChannel(user.UserId, normalizedChannelKind);
        if (link is null)
        {
            throw new InvalidOperationException($"The channel '{normalizedChannelKind}' is not linked to Executive Assistant for this account.");
        }

        string? nowNormalizedConversationId = AccountService.NormalizeOptional(request.ConversationId);
        string recipientHandle = ResolveRecipient(
            user.UserId,
            normalizedChannelKind,
            link,
            nowNormalizedConversationId,
            request.CounterpartyHandle);
        string idempotencyKey = BuildIdempotencyKey(
            normalizedSubject,
            normalizedChannelKind,
            request.IdempotencyKey,
            nowNormalizedConversationId,
            recipientHandle,
            messageText);
        DateTimeOffset now = DateTimeOffset.UtcNow;

        ExecutiveAssistantChannelConversationState conversation;
        lock (_store.Gate)
        {
            conversation = GetOrCreateConversationLocked(
                user.UserId,
                normalizedChannelKind,
                recipientHandle,
                nowNormalizedConversationId,
                now);

            ExecutiveAssistantChannelMessageState? duplicate = _store.ExecutiveAssistantChannelMessages.FirstOrDefault(item =>
                string.Equals(item.ConversationId, conversation.ConversationId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.IdempotencyKey, idempotencyKey, StringComparison.OrdinalIgnoreCase));
            if (duplicate is not null)
            {
                return BuildSendResult(duplicate, duplicate: true);
            }
        }

        var status = MessageStatusQueued;
        string? deliveryRef = null;
        string? failureReason = null;
        if (EaDispatchConfigured(normalizedChannelKind))
        {
            try
            {
                deliveryRef = await SendToEaAsync(
                    user,
                    normalizedChannelKind,
                    recipientHandle,
                    messageText,
                    idempotencyKey,
                    cancellationToken);
                status = MessageStatusSent;
            }
            catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or InvalidOperationException or JsonException)
            {
                _logger.LogWarning(
                    ex,
                    "EA send failed for user {UserId} channel {ChannelKind} conversation {ConversationId}.",
                    user.UserId,
                    normalizedChannelKind,
                    conversation.ConversationId);
                status = MessageStatusFailed;
                failureReason = Truncate(ex.Message, 300);
            }
        }
        else
        {
            status = MessageStatusUnconfigured;
            failureReason = "ea_delivery_unconfigured";
        }

        var outboundMessage = new ExecutiveAssistantChannelMessageState(
            MessageId: AccountService.NewId("eam"),
            ConversationId: conversation.ConversationId,
            ChannelKind: normalizedChannelKind,
            Direction: MessageDirectionOutbound,
            Text: messageText,
            SafetyLabel: SubjectMessageSafetyLabel,
            DeliveryStatus: status,
            CreatedAtUtc: now,
            CounterpartyHandle: recipientHandle,
            DeliveryRef: deliveryRef,
            FailureReason: failureReason,
            IdempotencyKey: idempotencyKey);

        lock (_store.Gate)
        {
            ExecutiveAssistantChannelMessageState? duplicate = _store.ExecutiveAssistantChannelMessages.FirstOrDefault(item =>
                string.Equals(item.ConversationId, conversation.ConversationId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.IdempotencyKey, idempotencyKey, StringComparison.OrdinalIgnoreCase));
            if (duplicate is not null)
            {
                return BuildSendResult(duplicate, duplicate: true);
            }

            conversation = _store.ExecutiveAssistantChannelConversations.FirstOrDefault(item =>
                string.Equals(item.ConversationId, conversation.ConversationId, StringComparison.OrdinalIgnoreCase))
                ?? conversation;
            int index = _store.ExecutiveAssistantChannelConversations.FindIndex(item =>
                string.Equals(item.ConversationId, conversation.ConversationId, StringComparison.OrdinalIgnoreCase));
            if (index >= 0)
            {
                _store.ExecutiveAssistantChannelConversations[index] = conversation with
                {
                    UpdatedAtUtc = now,
                    LatestMessageId = outboundMessage.MessageId,
                    Status = status is MessageStatusFailed ? ConversationStatusFailed : ConversationStatusActive
                };
            }

            _store.ExecutiveAssistantChannelMessages.Add(outboundMessage);
            EnsureConversationMessageLimitLocked(conversation.ConversationId);
            EnsureConversationLimitLocked(user.UserId, normalizedChannelKind);
            _store.PersistLocked();
            conversation = _store.ExecutiveAssistantChannelConversations.First(item =>
                string.Equals(item.ConversationId, conversation.ConversationId, StringComparison.OrdinalIgnoreCase));
        }

        _teable?.QueueSyncConversation(conversation);
        return BuildSendResult(outboundMessage, duplicate: false);
    }

    public ExecutiveAssistantChannelMessageDto IngestIncomingMessage(string channelKind, ExecutiveAssistantChannelIncomingMessageRequest request)
    {
        ArgumentNullException.ThrowIfNull(request);
        string normalizedChannelKind = NormalizeChannelKind(channelKind);
        string rawCounterparty = AccountService.NormalizeRequired(request.CounterpartyHandle, nameof(request.CounterpartyHandle));
        string normalizedCounterparty = NormalizeCounterpartyHandle(normalizedChannelKind, rawCounterparty);
        string normalizedText = AccountService.NormalizeRequired(request.MessageText, nameof(request.MessageText));
        DateTimeOffset receivedAt = request.ReceivedAtUtc ?? DateTimeOffset.UtcNow;
        string? normalizedSubjectId = AccountService.NormalizeOptional(request.SubjectId);
        string? providedRecipientHandle = AccountService.NormalizeOptional(request.RecipientHandle);
        string? normalizedRecipientHandle = providedRecipientHandle is null
            ? null
            : NormalizeCounterpartyHandle(normalizedChannelKind, providedRecipientHandle);
        IncomingRouteResolution resolution = ResolveIncomingRoute(
            normalizedChannelKind,
            normalizedSubjectId,
            normalizedCounterparty,
            normalizedRecipientHandle);
        HubUserDto user = resolution.User;
        string normalizedExternalHandle = resolution.ExternalHandle;

        ChannelLinkDto? link = GetLinkedChannel(user.UserId, normalizedChannelKind);
        if (link is null)
        {
            throw new InvalidOperationException($"The channel '{normalizedChannelKind}' is not linked to Executive Assistant for this account.");
        }

        string normalizedConversationId = AccountService.NormalizeOptional(request.ConversationId)
            ?? BuildConversationId(user.UserId, normalizedChannelKind, HashPrivate("counterparty", normalizedExternalHandle));
        string? providerMessageId = AccountService.NormalizeOptional(request.MessageId);
        string messageId = providerMessageId ?? AccountService.NewId("eami");

        ExecutiveAssistantChannelConversationState syncedConversation;
        ExecutiveAssistantChannelMessageDto dto;
        lock (_store.Gate)
        {
            ExecutiveAssistantChannelConversationState conversation = GetOrCreateConversationLocked(
                user.UserId,
                normalizedChannelKind,
                normalizedExternalHandle,
                normalizedConversationId,
                receivedAt);

            if (providerMessageId is null
                && TryFindRecentInboundDuplicateLocked(conversation.ConversationId, normalizedExternalHandle, normalizedText, receivedAt) is ExecutiveAssistantChannelMessageState duplicate)
            {
                return ToMessageDto(duplicate);
            }

            ExecutiveAssistantChannelMessageState? existing = _store.ExecutiveAssistantChannelMessages.FirstOrDefault(item =>
                string.Equals(item.ConversationId, conversation.ConversationId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.MessageId, messageId, StringComparison.OrdinalIgnoreCase));
            if (existing is not null)
            {
                return ToMessageDto(existing);
            }

            var incomingMessage = new ExecutiveAssistantChannelMessageState(
                MessageId: messageId,
                ConversationId: conversation.ConversationId,
                ChannelKind: normalizedChannelKind,
                Direction: MessageDirectionIncoming,
                Text: normalizedText,
                SafetyLabel: SubjectMessageSafetyLabel,
                DeliveryStatus: MessageStatusReceived,
                CreatedAtUtc: receivedAt,
                CounterpartyHandle: normalizedExternalHandle,
                DeliveryRef: null,
                FailureReason: null,
                IdempotencyKey: null);

            int conversationIndex = _store.ExecutiveAssistantChannelConversations.FindIndex(item =>
                string.Equals(item.ConversationId, conversation.ConversationId, StringComparison.OrdinalIgnoreCase));
            if (conversationIndex >= 0)
            {
                _store.ExecutiveAssistantChannelConversations[conversationIndex] = conversation with
                {
                    UpdatedAtUtc = receivedAt,
                    LatestMessageId = incomingMessage.MessageId,
                    Status = ConversationStatusActive
                };
            }

            _store.ExecutiveAssistantChannelMessages.Add(incomingMessage);
            EnsureConversationMessageLimitLocked(conversation.ConversationId);
            EnsureConversationLimitLocked(user.UserId, normalizedChannelKind);
            _store.PersistLocked();
            syncedConversation = _store.ExecutiveAssistantChannelConversations[conversationIndex];
            dto = ToMessageDto(incomingMessage);
        }

        _teable?.QueueSyncConversation(syncedConversation);
        return dto;
    }

    private ExecutiveAssistantChannelMessageState? TryFindRecentInboundDuplicateLocked(
        string conversationId,
        string normalizedCounterpartyHandle,
        string normalizedText,
        DateTimeOffset receivedAt)
    {
        return _store.ExecutiveAssistantChannelMessages.FirstOrDefault(item =>
            string.Equals(item.ConversationId, conversationId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.Direction, MessageDirectionIncoming, StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.CounterpartyHandle, normalizedCounterpartyHandle, StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.Text, normalizedText, StringComparison.Ordinal)
            && Math.Abs((item.CreatedAtUtc - receivedAt).TotalSeconds) <= InboundDuplicateWindow.TotalSeconds);
    }

    private IncomingRouteResolution ResolveIncomingRoute(
        string channelKind,
        string? subjectId,
        string normalizedCounterpartyHandle,
        string? normalizedRecipientHandle)
    {
        if (subjectId is not null)
        {
            HubUserDto? subjectUser = _accounts.GetBySubject(subjectId);
            if (subjectUser is not null)
            {
                return new IncomingRouteResolution(subjectUser, normalizedCounterpartyHandle, "subject_id");
            }
        }

        HubUserDto? counterpartyUser = FindUserByChannelRecipient(channelKind, normalizedCounterpartyHandle);
        HubUserDto? recipientUser = string.IsNullOrWhiteSpace(normalizedRecipientHandle)
            ? null
            : FindUserByChannelRecipient(channelKind, normalizedRecipientHandle);

        if (counterpartyUser is not null && recipientUser is not null
            && !string.Equals(counterpartyUser.UserId, recipientUser.UserId, StringComparison.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException(
                $"Ambiguous incoming {channelKind} routing; counterparty {normalizedCounterpartyHandle} and recipient {normalizedRecipientHandle} resolve to different EA-linked users.");
        }

        if (counterpartyUser is not null)
        {
            return new IncomingRouteResolution(counterpartyUser, normalizedCounterpartyHandle, "counterparty_handle");
        }

        if (recipientUser is not null && normalizedRecipientHandle is not null)
        {
            return new IncomingRouteResolution(recipientUser, normalizedRecipientHandle, "recipient_handle");
        }

        string recipientDetail = normalizedRecipientHandle is null
            ? "no recipient handle was supplied"
            : $"recipient handle {normalizedRecipientHandle} was supplied";
        throw new ArgumentException(
            $"Unable to route incoming {channelKind} message to an EA-linked user for counterparty {normalizedCounterpartyHandle}; {recipientDetail}.");
    }

    private sealed record IncomingRouteResolution(HubUserDto User, string ExternalHandle, string RouteSource);

    private HubUserDto? FindUserByChannelRecipient(string channelKind, string normalizedRecipient)
    {
        lock (_store.Gate)
        {
            string? userId = null;
            foreach (ChannelLinkDto link in _store.ChannelLinks)
            {
                if (!string.Equals(link.ChannelKind, channelKind, StringComparison.OrdinalIgnoreCase)
                    || !string.Equals(link.Status, "ea_linked", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                string normalizedStored = NormalizeCounterpartyHandle(channelKind, link.DisplayLabel);
                if (!string.Equals(normalizedStored, normalizedRecipient, StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                if (userId is null)
                {
                    userId = link.UserId;
                    continue;
                }

                if (!string.Equals(userId, link.UserId, StringComparison.OrdinalIgnoreCase))
                {
                    throw new InvalidOperationException(
                        $"Ambiguous incoming {channelKind} counterparty routing; {normalizedRecipient} matches multiple linked users.");
                }
            }

            return userId is null ? null : _accounts.GetById(userId);
        }
    }

    private ExecutiveAssistantChannelConversationState GetOrCreateConversationLocked(
        string userId,
        string channelKind,
        string normalizedCounterpartyHandle,
        string? requestedConversationId,
        DateTimeOffset now)
    {
        string counterpartyHash = HashPrivate("counterparty", normalizedCounterpartyHandle);
        string? normalizedConversationId = AccountService.NormalizeOptional(requestedConversationId);

        if (normalizedConversationId is not null)
        {
            ExecutiveAssistantChannelConversationState? requested = _store.ExecutiveAssistantChannelConversations.FirstOrDefault(item =>
                string.Equals(item.ConversationId, normalizedConversationId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.UserId, userId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.ChannelKind, channelKind, StringComparison.OrdinalIgnoreCase));
            if (requested is not null)
            {
                return requested;
            }
        }

        ExecutiveAssistantChannelConversationState? existing = _store.ExecutiveAssistantChannelConversations.FirstOrDefault(item =>
            string.Equals(item.UserId, userId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.ChannelKind, channelKind, StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.CounterpartyHash, counterpartyHash, StringComparison.OrdinalIgnoreCase));
        if (existing is not null)
        {
            return existing;
        }

        string conversationId = normalizedConversationId ?? BuildConversationId(userId, channelKind, counterpartyHash);
        var created = new ExecutiveAssistantChannelConversationState(
            ConversationId: conversationId,
            UserId: userId,
            ChannelKind: channelKind,
            CounterpartyHandle: normalizedCounterpartyHandle,
            CounterpartyHash: counterpartyHash,
            Status: ConversationStatusActive,
            CreatedAtUtc: now,
            UpdatedAtUtc: now,
            LatestMessageId: null);
        _store.ExecutiveAssistantChannelConversations.Add(created);
        EnsureConversationMessageLimitLocked(conversationId);
        return created;
    }

    private string ResolveRecipient(
        string userId,
        string channelKind,
        ChannelLinkDto link,
        string? conversationId,
        string? requestedCounterparty)
    {
        if (!string.IsNullOrWhiteSpace(requestedCounterparty))
        {
            return NormalizeCounterpartyHandle(channelKind, requestedCounterparty!);
        }

        if (string.IsNullOrWhiteSpace(conversationId))
        {
            string normalizedDefault = NormalizeCounterpartyHandle(channelKind, link.DisplayLabel);
            if (string.IsNullOrWhiteSpace(normalizedDefault))
            {
                throw new ArgumentException("A counterparty handle is required.");
            }

            return normalizedDefault;
        }

        string normalizedConversationId = AccountService.NormalizeRequired(conversationId, nameof(conversationId));
        ExecutiveAssistantChannelConversationState? matched = _store.ExecutiveAssistantChannelConversations.FirstOrDefault(item =>
            string.Equals(item.UserId, userId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.ChannelKind, channelKind, StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.ConversationId, normalizedConversationId, StringComparison.OrdinalIgnoreCase));
        if (matched is not null)
        {
            return matched.CounterpartyHandle;
        }

        return NormalizeCounterpartyHandle(channelKind, link.DisplayLabel);
    }

    private async Task<string> SendToEaAsync(
        HubUserDto user,
        string channelKind,
        string recipientHandle,
        string messageText,
        string idempotencyKey,
        CancellationToken cancellationToken)
    {
        string principalId = ResolveEaPrincipalId();
        string bindingId = ResolveEaBindingId(channelKind);
        string deliveryChannel = ResolveEaDeliveryChannel(channelKind);
        string deliveryTransport = ResolveEaDeliveryTransport(channelKind, bindingId);
        var metadata = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase)
        {
            ["event_type"] = "executive_assistant_channel_send",
            ["source_service"] = "chummer_hub_account_channel",
            ["user_id"] = user.UserId,
            ["subject_id"] = user.SubjectId,
            ["channel_kind"] = channelKind,
            ["account_channel_kind"] = channelKind,
            ["delivery_channel"] = deliveryChannel,
            ["delivery_transport"] = deliveryTransport,
            ["recipient"] = recipientHandle
        };
        var payload = new
        {
            tool_name = ConnectorDispatchTool,
            action_kind = DeliverySendAction,
            payload_json = new
            {
                principal_id = principalId,
                binding_id = bindingId,
                channel = deliveryChannel,
                recipient = recipientHandle,
                subject = $"Message from Chummer account {user.Handle}",
                content = messageText,
                metadata,
                idempotency_key = idempotencyKey
            }
        };

        using var request = new HttpRequestMessage(HttpMethod.Post, $"{ResolveEaBaseUrl()}/v1/tools/execute");
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", ResolveEaApiToken());
        request.Headers.Add("x-ea-principal-id", principalId);
        request.Headers.Add("Idempotency-Key", idempotencyKey);
        request.Content = JsonContent.Create(payload);

        using HttpResponseMessage response = await _httpClient.SendAsync(request, cancellationToken);
        string responseBody = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"{(int)response.StatusCode}:{Truncate(responseBody, 450)}");
        }

        if (string.IsNullOrWhiteSpace(responseBody))
        {
            throw new InvalidOperationException("connector_dispatch_missing_delivery_id");
        }

        using JsonDocument document = JsonDocument.Parse(responseBody);
        string? deliveryRef = document.RootElement.TryGetProperty("target_ref", out JsonElement targetRef)
            ? targetRef.GetString()
            : document.RootElement.TryGetProperty("output_json", out JsonElement output)
                && output.TryGetProperty("delivery_id", out JsonElement deliveryId)
                    ? deliveryId.GetString()
                    : null;
        if (string.IsNullOrWhiteSpace(deliveryRef))
        {
            throw new InvalidOperationException("connector_dispatch_missing_delivery_id");
        }

        return deliveryRef;
    }

    private static ExecutiveAssistantChannelConversationDto ToConversationDto(
        ExecutiveAssistantChannelConversationState conversation,
        IReadOnlyList<ExecutiveAssistantChannelMessageDto> messages)
    {
        return new ExecutiveAssistantChannelConversationDto(
            ConversationId: conversation.ConversationId,
            UserId: conversation.UserId,
            ChannelKind: conversation.ChannelKind,
            CounterpartyHandle: conversation.CounterpartyHandle,
            CounterpartyHash: conversation.CounterpartyHash,
            Status: conversation.Status,
            CreatedAtUtc: conversation.CreatedAtUtc,
            UpdatedAtUtc: conversation.UpdatedAtUtc,
            Messages: messages);
    }

    private static ExecutiveAssistantChannelMessageDto ToMessageDto(ExecutiveAssistantChannelMessageState message)
    {
        return new ExecutiveAssistantChannelMessageDto(
            MessageId: message.MessageId,
            ConversationId: message.ConversationId,
            ChannelKind: message.ChannelKind,
            Direction: message.Direction,
            Text: message.Text,
            SafetyLabel: message.SafetyLabel,
            DeliveryStatus: message.DeliveryStatus,
            CounterpartyHandle: message.CounterpartyHandle,
            DeliveryRef: message.DeliveryRef,
            FailureReason: message.FailureReason,
            IdempotencyKey: message.IdempotencyKey,
            CreatedAtUtc: message.CreatedAtUtc);
    }

    private ExecutiveAssistantChannelSendResult BuildSendResult(
        ExecutiveAssistantChannelMessageState message,
        bool duplicate)
    {
        return new ExecutiveAssistantChannelSendResult(
            ConversationId: message.ConversationId,
            MessageId: message.MessageId,
            Status: message.DeliveryStatus,
            DeliveryRef: message.DeliveryRef,
            FailureReason: message.FailureReason,
            IdempotencyKey: message.IdempotencyKey ?? string.Empty,
            AttemptedAtUtc: message.CreatedAtUtc,
            Duplicate: duplicate);
    }

    private ChannelLinkDto? GetLinkedChannel(string userId, string channelKind)
    {
        return _store.ChannelLinks.FirstOrDefault(link =>
            string.Equals(link.UserId, userId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(link.ChannelKind, channelKind, StringComparison.OrdinalIgnoreCase)
            && string.Equals(link.Status, "ea_linked", StringComparison.OrdinalIgnoreCase));
    }

    private void EnsureConversationLimitLocked(string userId, string channelKind)
    {
        var ordered = _store.ExecutiveAssistantChannelConversations
            .Where(conversation =>
                string.Equals(conversation.UserId, userId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(conversation.ChannelKind, channelKind, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(item => item.UpdatedAtUtc)
            .ToList();

        if (ordered.Count <= MaxConversationsPerUserChannel)
        {
            return;
        }

        foreach (var stale in ordered.Skip(MaxConversationsPerUserChannel))
        {
            string staleConversationId = stale.ConversationId;
            _store.ExecutiveAssistantChannelConversations.RemoveAll(item =>
                string.Equals(item.ConversationId, staleConversationId, StringComparison.OrdinalIgnoreCase));
            _store.ExecutiveAssistantChannelMessages.RemoveAll(item =>
                string.Equals(item.ConversationId, staleConversationId, StringComparison.OrdinalIgnoreCase));
        }
    }

    private void EnsureConversationMessageLimitLocked(string conversationId)
    {
        var ordered = _store.ExecutiveAssistantChannelMessages
            .Where(message => string.Equals(message.ConversationId, conversationId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(message => message.CreatedAtUtc)
            .ToList();

        if (ordered.Count <= MaxMessagesPerConversation)
        {
            return;
        }

        foreach (var stale in ordered.Skip(MaxMessagesPerConversation))
        {
            int index = _store.ExecutiveAssistantChannelMessages.FindIndex(message =>
                string.Equals(message.MessageId, stale.MessageId, StringComparison.OrdinalIgnoreCase));
            if (index >= 0)
            {
                _store.ExecutiveAssistantChannelMessages.RemoveAt(index);
            }
        }
    }

    private static string BuildConversationId(string userId, string channelKind, string counterpartyHash)
        => $"{channelKind}:{userId}:{counterpartyHash[..12]}";

    private static string BuildIdempotencyKey(
        string subjectId,
        string channelKind,
        string? providedKey,
        string? conversationId,
        string counterpartyHandle,
        string messageText)
    {
        if (AccountService.NormalizeOptional(providedKey) is string existing)
        {
            return $"ea-channel-send|{subjectId}|{channelKind}|{existing}";
        }

        _ = messageText; // retained for signature compatibility with existing callers.
        return $"ea-channel-send|{subjectId}|{channelKind}|{conversationId ?? string.Empty}|{counterpartyHandle}|{Guid.NewGuid():N}";
    }

    private bool EaDispatchConfigured(string channelKind)
        => !string.IsNullOrWhiteSpace(ResolveEaApiToken())
            && !string.IsNullOrWhiteSpace(ResolveEaPrincipalId())
            && !string.IsNullOrWhiteSpace(ResolveEaBindingId(channelKind))
            && RealEaBaseUrlConfigured();

    private bool RealEaBaseUrlConfigured()
    {
        string? configured = AccountService.NormalizeOptional(_configuration["CHUMMER_EA_CHANNEL_MESSAGING_EA_BASE_URL"]);
        if (configured is null)
        {
            return false;
        }

        string normalized = configured.Trim().TrimEnd('/');
        return NonProductionEaBaseUrlMarkers.All(marker =>
            !normalized.Contains(marker, StringComparison.OrdinalIgnoreCase));
    }

    private string ResolveEaBindingId(string channelKind)
        => string.Equals(channelKind, WhatsappChannelKind, StringComparison.OrdinalIgnoreCase)
            ? AccountService.NormalizeOptional(_configuration["CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_WEB_BINDING_ID"])
                ?? AccountService.NormalizeOptional(_configuration["CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_BINDING_ID"])
                ?? AccountService.NormalizeOptional(_configuration["CHUMMER_EA_CHANNEL_MESSAGING_EA_BINDING_ID"])
                ?? string.Empty
            : AccountService.NormalizeOptional(_configuration["CHUMMER_EA_CHANNEL_MESSAGING_EA_TELEGRAM_BINDING_ID"])
                ?? AccountService.NormalizeOptional(_configuration["CHUMMER_EA_CHANNEL_MESSAGING_EA_BINDING_ID"])
                ?? string.Empty;

    private string ResolveEaDeliveryChannel(string channelKind)
        => string.Equals(channelKind, WhatsappChannelKind, StringComparison.OrdinalIgnoreCase)
            ? WhatsappDeliveryChannel
            : TelegramDeliveryChannel;

    private string ResolveEaDeliveryTransport(string channelKind, string bindingId)
    {
        if (!string.Equals(channelKind, WhatsappChannelKind, StringComparison.OrdinalIgnoreCase))
        {
            return "telegram_bot";
        }

        string? configuredTransport = AccountService.NormalizeOptional(_configuration["CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_TRANSPORT"]);
        if (configuredTransport is not null)
        {
            return configuredTransport;
        }

        string? webBindingId = AccountService.NormalizeOptional(_configuration["CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_WEB_BINDING_ID"]);
        return !string.IsNullOrWhiteSpace(webBindingId)
            && string.Equals(bindingId, webBindingId, StringComparison.OrdinalIgnoreCase)
                ? WhatsappWebSessionTransport
                : WhatsappBusinessTransport;
    }

    private string ResolveEaApiToken()
        => (_configuration["CHUMMER_EA_CHANNEL_MESSAGING_EA_API_TOKEN"] ?? string.Empty).Trim();

    private string ResolveEaPrincipalId()
        => (_configuration["CHUMMER_EA_CHANNEL_MESSAGING_EA_PRINCIPAL_ID"] ?? string.Empty).Trim();

    private string ResolveEaBaseUrl()
        => (_configuration["CHUMMER_EA_CHANNEL_MESSAGING_EA_BASE_URL"] ?? DefaultEaBaseUrl).Trim().TrimEnd('/');

    private static string NormalizeChannelKind(string channelKind)
    {
        string normalized = AccountService.NormalizeRequired(channelKind, nameof(channelKind)).ToLowerInvariant();
        return normalized switch
        {
            TelegramChannelKind => normalized,
            WhatsappChannelKind => normalized,
            _ => throw new ArgumentException($"Unsupported channel kind '{normalized}'.")
        };
    }

    private static string NormalizeCounterpartyHandle(string channelKind, string rawHandle)
    {
        string normalized = rawHandle.Trim();
        return channelKind switch
        {
            WhatsappChannelKind => NormalizeWhatsappHandle(normalized),
            TelegramChannelKind => NormalizeTelegramHandle(normalized),
            _ => normalized
        };
    }

    private static string NormalizeWhatsappHandle(string rawHandle)
        => new string(rawHandle.Where(char.IsDigit).ToArray());

    private static string NormalizeTelegramHandle(string rawHandle)
    {
        string trimmed = rawHandle.Trim();
        if (trimmed.StartsWith("@", StringComparison.OrdinalIgnoreCase))
        {
            trimmed = trimmed[1..];
        }

        if (Uri.TryCreate(trimmed, UriKind.Absolute, out Uri? uri)
            && uri.Host.StartsWith("t.me", StringComparison.OrdinalIgnoreCase))
        {
            string path = uri.AbsolutePath.Trim('/');
            if (!string.IsNullOrWhiteSpace(path))
            {
                return path.Split('/', StringSplitOptions.RemoveEmptyEntries)[0].Trim();
            }
        }

        return trimmed;
    }

    private static string HashPrivate(string scope, string value)
    {
        string normalized = value.ToLowerInvariant().Trim();
        string salt = "chummer-exec-assistant-channel";
        byte[] hash = SHA256.HashData(Encoding.UTF8.GetBytes($"{salt}|{scope}|{normalized}"));
        return Convert.ToHexString(hash).ToLowerInvariant();
    }

    private static string Truncate(string value, int maxLength)
        => value.Length <= maxLength ? value : value[..maxLength];
}
