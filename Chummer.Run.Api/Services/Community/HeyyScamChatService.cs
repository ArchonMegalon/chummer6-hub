using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Chummer.Run.Contracts.Heyy;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Services.Community;

public sealed record HeyyScamChatMessage(
    string MessageId,
    string Direction,
    string Text,
    string SafetyLabel,
    string PacingHint,
    DateTimeOffset CreatedAtUtc);

public sealed record HeyyScamChatDraftState(
    string DraftId,
    string DraftText,
    string PacingHint,
    int MinimumDelaySeconds,
    string Status,
    string? FailureReason,
    DateTimeOffset CreatedAtUtc);

public sealed record HeyyScamChatConversationState(
    string ConversationId,
    string Channel,
    string CounterpartyMasked,
    string CounterpartyHash,
    string Mode,
    string PersonaId,
    string SafetyStatus,
    HeyyScamChatEnrichmentResponse Enrichment,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    IReadOnlyList<HeyyScamChatMessage> Messages,
    HeyyScamChatDraftState? LatestDraft);

public sealed record HeyyScamChatDigestReceipt(
    string DigestId,
    string EventKey,
    DateOnly Date,
    string Status,
    int ConversationCount,
    int MessageCount,
    string? DeliveryRef,
    string? FailureReason,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset AttemptedAtUtc,
    string Content);

public sealed record HeyyScamChatApprovalReceipt(
    string ApprovalId,
    string ConversationId,
    string? DraftId,
    string DeliveryMode,
    string Status,
    bool DryRun,
    bool ManualApprovalConfirmed,
    string OperatorId,
    string RecipientMasked,
    string ApprovedText,
    string PacingHint,
    string? DeliveryRef,
    string? FailureReason,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset AttemptedAtUtc,
    string IdempotencyKey);

public sealed record HeyyScamChatOperatorSummaryReceipt(
    string SummaryId,
    string ConversationId,
    int IncomingTurnCount,
    int Threshold,
    string Status,
    string Channel,
    string RecipientMasked,
    string Content,
    string? DeliveryRef,
    string? FailureReason,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset AttemptedAtUtc,
    string EventKey);

public sealed class HeyyScamChatService
{
    private const string DefaultDeliveryBaseUrl = "http://127.0.0.1:8090";
    private const string ConnectorDispatchTool = "connector.dispatch";
    private const string DeliverySendAction = "delivery.send";
    private const string EmailChannel = "email";
    private const string SmsChannel = "sms";
    private const string DraftOnlyMode = "draft_only";
    private const string ManualCopyDeliveryMode = "manual_copy";
    private const string OperatorEmailDeliveryMode = "operator_email";
    private const string PersonaId = "empathetic_slow_typing_old_lady";
    private const int MinimumOldLadyDelaySeconds = 240;

    private static readonly Regex PhoneLikePattern = new(@"\+?\d[\d\s().-]{6,}\d", RegexOptions.Compiled);
    private static readonly Regex EmailPattern = new(@"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", RegexOptions.Compiled | RegexOptions.IgnoreCase);
    private static readonly Regex IbanPattern = new(@"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b", RegexOptions.Compiled | RegexOptions.IgnoreCase);

    private static readonly string[] UnsafeOutgoingTerms =
    [
        "iban",
        "bic",
        "pin",
        "tan",
        "passwort",
        "kreditkarte",
        "western union",
        "paysafecard",
        "gutscheincode",
        "gift card",
        "einmalcode",
        "2fa",
        "otp"
    ];

    private readonly HttpClient _httpClient;
    private readonly CommunityStore _store;
    private readonly IConfiguration _configuration;
    private readonly TeableHeyyScamChatService? _teable;
    private readonly ILogger<HeyyScamChatService> _logger;

    public HeyyScamChatService(
        HttpClient httpClient,
        CommunityStore store,
        IConfiguration configuration,
        TeableHeyyScamChatService? teable = null,
        ILogger<HeyyScamChatService>? logger = null)
    {
        _httpClient = httpClient;
        _store = store;
        _configuration = configuration;
        _teable = teable;
        _logger = logger ?? NullLogger<HeyyScamChatService>.Instance;
    }

    public async Task<HeyyScamChatDraftResponse> IngestIncomingAsync(HeyyScamChatIngestRequest request, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        string channel = NormalizeChannel(request.Channel);
        string counterpartyHandle = AccountService.NormalizeOptional(request.CounterpartyHandle) ?? "unknown";
        string counterpartyHash = HashPrivate("counterparty", counterpartyHandle);
        string conversationId = NormalizeConversationId(request.ConversationId, channel, counterpartyHash);
        string redactedMessage = RedactSensitiveText(request.MessageText);
        DateTimeOffset receivedAt = request.ReceivedAtUtc ?? DateTimeOffset.UtcNow;
        HeyyScamChatConversationState conversation;

        lock (_store.Gate)
        {
            conversation = UpsertIncomingLocked(
                conversationId,
                channel,
                MaskHandle(counterpartyHandle),
                counterpartyHash,
                redactedMessage,
                receivedAt);
            _store.PersistLocked();
        }

        HeyyScamChatDraftState draft = await GenerateDraftAsync(conversation, cancellationToken);
        lock (_store.Gate)
        {
            int index = _store.HeyyScamChatConversations.FindIndex(item =>
                string.Equals(item.ConversationId, conversationId, StringComparison.OrdinalIgnoreCase));
            if (index >= 0)
            {
                HeyyScamChatConversationState existing = _store.HeyyScamChatConversations[index];
                HeyyScamChatMessage draftMessage = new(
                    MessageId: draft.DraftId,
                    Direction: "draft",
                    Text: draft.DraftText,
                    SafetyLabel: "manual_approval_required",
                    PacingHint: draft.PacingHint,
                    CreatedAtUtc: draft.CreatedAtUtc);
                _store.HeyyScamChatConversations[index] = existing with
                {
                    UpdatedAtUtc = draft.CreatedAtUtc,
                    LatestDraft = draft,
                    Messages = existing.Messages.Concat([draftMessage]).ToArray()
                };
                conversation = _store.HeyyScamChatConversations[index];
                _store.PersistLocked();
            }
        }

        _teable?.QueueSyncConversation(conversation);
        await DispatchTurnSummaryIfDueAsync(conversation, cancellationToken);
        return ToDraftResponse(conversationId, draft, conversation.Enrichment);
    }

    public HeyyScamChatConversationResponse? GetConversation(string conversationId)
    {
        string normalized = AccountService.NormalizeRequired(conversationId, nameof(conversationId));
        lock (_store.Gate)
        {
            HeyyScamChatConversationState? conversation = _store.HeyyScamChatConversations
                .FirstOrDefault(item => string.Equals(item.ConversationId, normalized, StringComparison.OrdinalIgnoreCase));
            return conversation is null ? null : ToConversationResponse(conversation);
        }
    }

    public IReadOnlyList<HeyyScamChatConversationResponse> ListConversations(int take = 24)
    {
        lock (_store.Gate)
        {
            return _store.HeyyScamChatConversations
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .Take(Math.Clamp(take, 1, 100))
                .Select(ToConversationResponse)
                .ToArray();
        }
    }

    public async Task<HeyyScamChatApprovalResponse> ApproveDraftAsync(
        string conversationId,
        HeyyScamChatApproveDraftRequest request,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(request);
        string normalizedConversationId = AccountService.NormalizeRequired(conversationId, nameof(conversationId));
        string deliveryMode = NormalizeDeliveryMode(request.DeliveryMode);
        string operatorId = AccountService.NormalizeOptional(request.OperatorId) ?? "operator";
        DateTimeOffset now = DateTimeOffset.UtcNow;
        HeyyScamChatConversationState conversation;
        HeyyScamChatApprovalReceipt? existingReceipt;

        lock (_store.Gate)
        {
            conversation = _store.HeyyScamChatConversations.FirstOrDefault(item =>
                string.Equals(item.ConversationId, normalizedConversationId, StringComparison.OrdinalIgnoreCase))
                ?? throw new ArgumentException($"Unknown Heyy scam-chat conversation '{normalizedConversationId}'.");
        }

        string approvedText = AccountService.NormalizeOptional(request.ApprovedText)
            ?? conversation.LatestDraft?.DraftText
            ?? throw new ArgumentException("A draft or approved text is required.");
        string idempotencySeed = AccountService.NormalizeOptional(request.ApprovedText) ?? conversation.LatestDraft?.DraftId ?? approvedText;
        string idempotencyKey = AccountService.NormalizeOptional(request.IdempotencyKey)
            ?? $"heyy-scam-chat-approval|{normalizedConversationId}|{deliveryMode}|{HashPrivate("approval", idempotencySeed)[..16]}";
        lock (_store.Gate)
        {
            existingReceipt = _store.HeyyScamChatApprovalReceipts.FirstOrDefault(item =>
                string.Equals(item.IdempotencyKey, idempotencyKey, StringComparison.OrdinalIgnoreCase));
            if (existingReceipt is not null)
            {
                return ToApprovalResponse(existingReceipt);
            }
        }

        approvedText = RedactSensitiveText(approvedText);
        string recipient = AccountService.NormalizeOptional(request.Recipient)
            ?? ResolveDigestRecipient();
        string recipientMasked = MaskReceiptRecipient(recipient);
        string? deliveryRef = null;
        string? failureReason = null;
        string status;

        if (!request.ConfirmManualApproval)
        {
            status = "rejected_manual_confirmation_missing";
            failureReason = "confirm_manual_approval_required";
        }
        else if (!IsOutgoingSafe(approvedText))
        {
            status = "rejected_safety_gate";
            failureReason = "unsafe_outgoing_filtered";
        }
        else if (request.DryRun)
        {
            status = $"dry_run_{deliveryMode}_ready";
        }
        else if (deliveryMode == ManualCopyDeliveryMode)
        {
            status = "manual_copy_ready";
        }
        else if (!DeliveryEaConfigured() || string.IsNullOrWhiteSpace(recipient))
        {
            status = "suppressed_operator_email_unconfigured";
            failureReason = string.IsNullOrWhiteSpace(recipient) ? "recipient_missing" : "ea_dispatch_unconfigured";
        }
        else
        {
            try
            {
                deliveryRef = await SendApprovedDraftToOperatorEmailAsync(
                    conversation,
                    approvedText,
                    recipient,
                    operatorId,
                    idempotencyKey,
                    cancellationToken);
                status = "sent_to_operator_email";
            }
            catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or InvalidOperationException or JsonException)
            {
                _logger.LogWarning(ex, "Heyy scam-chat approved draft operator email failed for {ConversationId}.", conversation.ConversationId);
                status = "failed_operator_email";
                failureReason = Truncate(ex.Message, 400);
            }
        }

        HeyyScamChatApprovalReceipt receipt = new(
            ApprovalId: $"heyyapproval_{Guid.NewGuid():N}"[..26],
            ConversationId: conversation.ConversationId,
            DraftId: conversation.LatestDraft?.DraftId,
            DeliveryMode: deliveryMode,
            Status: status,
            DryRun: request.DryRun,
            ManualApprovalConfirmed: request.ConfirmManualApproval,
            OperatorId: operatorId,
            RecipientMasked: recipientMasked,
            ApprovedText: approvedText,
            PacingHint: conversation.LatestDraft?.PacingHint ?? "Manual approval required before sending.",
            DeliveryRef: deliveryRef,
            FailureReason: failureReason,
            CreatedAtUtc: now,
            AttemptedAtUtc: DateTimeOffset.UtcNow,
            IdempotencyKey: idempotencyKey);

        lock (_store.Gate)
        {
            _store.HeyyScamChatApprovalReceipts.Add(receipt);
            _store.HeyyScamChatApprovalReceipts.Sort(static (left, right) => right.CreatedAtUtc.CompareTo(left.CreatedAtUtc));
            if (_store.HeyyScamChatApprovalReceipts.Count > 256)
            {
                _store.HeyyScamChatApprovalReceipts.RemoveRange(256, _store.HeyyScamChatApprovalReceipts.Count - 256);
            }

            if (request.ConfirmManualApproval && !request.DryRun && (status == "manual_copy_ready" || status == "sent_to_operator_email"))
            {
                int index = _store.HeyyScamChatConversations.FindIndex(item =>
                    string.Equals(item.ConversationId, conversation.ConversationId, StringComparison.OrdinalIgnoreCase));
                if (index >= 0)
                {
                    HeyyScamChatConversationState current = _store.HeyyScamChatConversations[index];
                    HeyyScamChatMessage approvalMessage = new(
                        MessageId: receipt.ApprovalId,
                        Direction: status == "manual_copy_ready" ? "approved_manual_copy" : "sent_operator_email",
                        Text: approvedText,
                        SafetyLabel: status,
                        PacingHint: receipt.PacingHint,
                        CreatedAtUtc: receipt.AttemptedAtUtc);
                    _store.HeyyScamChatConversations[index] = current with
                    {
                        UpdatedAtUtc = receipt.AttemptedAtUtc,
                        Messages = current.Messages.Concat([approvalMessage]).ToArray()
                    };
                }
            }

            _store.PersistLocked();
        }

        return ToApprovalResponse(receipt);
    }

    public async Task<HeyyScamChatDigestResponse> DispatchDailyDigestAsync(DateOnly date, bool dryRun, CancellationToken cancellationToken)
    {
        string eventKey = BuildDigestEventKey(date);
        HeyyScamChatDigestReceipt? existing;
        HeyyScamChatConversationState[] conversations;
        lock (_store.Gate)
        {
            existing = _store.HeyyScamChatDigestReceipts.FirstOrDefault(item =>
                string.Equals(item.EventKey, eventKey, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.Status, "sent", StringComparison.OrdinalIgnoreCase));
            conversations = _store.HeyyScamChatConversations
                .Where(item => item.Messages.Any(message => DateOnly.FromDateTime(message.CreatedAtUtc.UtcDateTime) == date))
                .OrderBy(static item => item.CounterpartyMasked, StringComparer.OrdinalIgnoreCase)
                .ToArray();
        }

        if (existing is not null && !dryRun)
        {
            return ToDigestResponse(existing, dryRun: false);
        }

        string content = BuildDigestContent(date, conversations);
        int messageCount = conversations.Sum(item => item.Messages.Count(message => DateOnly.FromDateTime(message.CreatedAtUtc.UtcDateTime) == date));
        if (conversations.Length == 0)
        {
            HeyyScamChatDigestReceipt empty = BuildDigestReceipt(date, eventKey, "suppressed_empty", conversations.Length, messageCount, null, "no_conversations", content);
            if (!dryRun)
            {
                UpsertDigestReceipt(empty);
            }

            return ToDigestResponse(empty, dryRun);
        }

        if (dryRun)
        {
            return ToDigestResponse(BuildDigestReceipt(date, eventKey, "dry_run", conversations.Length, messageCount, null, null, content), dryRun: true);
        }

        HeyyScamChatDigestReceipt pending = BuildDigestReceipt(date, eventKey, "pending", conversations.Length, messageCount, null, null, content);
        UpsertDigestReceipt(pending);

        try
        {
            if (!DigestEnabled())
            {
                HeyyScamChatDigestReceipt suppressed = pending with
                {
                    Status = "suppressed_disabled",
                    FailureReason = "digest_disabled",
                    AttemptedAtUtc = DateTimeOffset.UtcNow
                };
                UpsertDigestReceipt(suppressed);
                return ToDigestResponse(suppressed, dryRun: false);
            }

            string recipient = ResolveDigestRecipient();
            if (string.IsNullOrWhiteSpace(recipient))
            {
                HeyyScamChatDigestReceipt suppressed = pending with
                {
                    Status = "suppressed_recipient_missing",
                    FailureReason = "recipient_missing",
                    AttemptedAtUtc = DateTimeOffset.UtcNow
                };
                UpsertDigestReceipt(suppressed);
                return ToDigestResponse(suppressed, dryRun: false);
            }

            if (!DeliveryEaConfigured())
            {
                HeyyScamChatDigestReceipt suppressed = pending with
                {
                    Status = "suppressed_delivery_unconfigured",
                    FailureReason = "ea_dispatch_unconfigured",
                    AttemptedAtUtc = DateTimeOffset.UtcNow
                };
                UpsertDigestReceipt(suppressed);
                return ToDigestResponse(suppressed, dryRun: false);
            }

            string deliveryRef = await SendDigestToEaAsync(pending, recipient, cancellationToken);
            HeyyScamChatDigestReceipt sent = pending with
            {
                Status = "sent",
                DeliveryRef = deliveryRef,
                AttemptedAtUtc = DateTimeOffset.UtcNow
            };
            UpsertDigestReceipt(sent);
            return ToDigestResponse(sent, dryRun: false);
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or InvalidOperationException or JsonException)
        {
            _logger.LogWarning(ex, "Heyy scam-chat digest dispatch failed for {DigestId}.", pending.DigestId);
            HeyyScamChatDigestReceipt failed = pending with
            {
                Status = "failed_delivery",
                FailureReason = Truncate(ex.Message, 400),
                AttemptedAtUtc = DateTimeOffset.UtcNow
            };
            UpsertDigestReceipt(failed);
            return ToDigestResponse(failed, dryRun: false);
        }
    }

    public async Task<HeyyScamChatDigestResponse> DispatchYesterdayDigestIfDueAsync(DateTimeOffset now, CancellationToken cancellationToken)
    {
        if (!WorkerEnabled())
        {
            DateOnly yesterday = DateOnly.FromDateTime(now.UtcDateTime.AddDays(-1));
            return ToDigestResponse(BuildDigestReceipt(yesterday, BuildDigestEventKey(yesterday), "suppressed_worker_disabled", 0, 0, null, "worker_disabled", string.Empty), dryRun: false);
        }

        int digestHour = Math.Clamp(ReadInt("CHUMMER_HEYY_SCAM_CHAT_DIGEST_HOUR_UTC", 5), 0, 23);
        if (now.UtcDateTime.Hour < digestHour)
        {
            DateOnly yesterday = DateOnly.FromDateTime(now.UtcDateTime.AddDays(-1));
            return ToDigestResponse(BuildDigestReceipt(yesterday, BuildDigestEventKey(yesterday), "not_due", 0, 0, null, null, string.Empty), dryRun: false);
        }

        return await DispatchDailyDigestAsync(DateOnly.FromDateTime(now.UtcDateTime.AddDays(-1)), dryRun: false, cancellationToken);
    }

    private HeyyScamChatConversationState UpsertIncomingLocked(
        string conversationId,
        string channel,
        string counterpartyMasked,
        string counterpartyHash,
        string redactedMessage,
        DateTimeOffset receivedAt)
    {
        HeyyScamChatMessage incoming = new(
            MessageId: $"heyymsg_{Guid.NewGuid():N}"[..22],
            Direction: "incoming",
            Text: redactedMessage,
            SafetyLabel: "redacted_scam_intake",
            PacingHint: "Do not answer immediately; wait like a slow, cautious older person.",
            CreatedAtUtc: receivedAt);
        int index = _store.HeyyScamChatConversations.FindIndex(item =>
            string.Equals(item.ConversationId, conversationId, StringComparison.OrdinalIgnoreCase));
        if (index >= 0)
        {
            HeyyScamChatConversationState existing = _store.HeyyScamChatConversations[index];
            HeyyScamChatMessage[] messages = existing.Messages.Concat([incoming]).ToArray();
            HeyyScamChatConversationState updated = existing with
            {
                UpdatedAtUtc = receivedAt,
                SafetyStatus = "draft_only_manual_approval",
                Enrichment = BuildEnrichment(channel, messages),
                Messages = messages
            };
            _store.HeyyScamChatConversations[index] = updated;
            return updated;
        }

        HeyyScamChatMessage[] createdMessages = [incoming];
        HeyyScamChatConversationState created = new(
            ConversationId: conversationId,
            Channel: channel,
            CounterpartyMasked: counterpartyMasked,
            CounterpartyHash: counterpartyHash,
            Mode: DraftOnlyMode,
            PersonaId: PersonaId,
            SafetyStatus: "draft_only_manual_approval",
            Enrichment: BuildEnrichment(channel, createdMessages),
            CreatedAtUtc: receivedAt,
            UpdatedAtUtc: receivedAt,
            Messages: createdMessages,
            LatestDraft: null);
        _store.HeyyScamChatConversations.Add(created);
        return created;
    }

    private async Task<HeyyScamChatDraftState> GenerateDraftAsync(HeyyScamChatConversationState conversation, CancellationToken cancellationToken)
    {
        string fallback = BuildFallbackDraft(conversation.Messages.Count(static item => item.Direction == "incoming"));
        string draft = fallback;
        string status = "generated_fallback";
        string? failureReason = null;

        try
        {
            if (ChatEaConfigured())
            {
                string? eaDraft = await GenerateDraftViaEaAsync(conversation, cancellationToken);
                if (!string.IsNullOrWhiteSpace(eaDraft))
                {
                    draft = eaDraft;
                    status = "generated_via_ea";
                }
            }
            else
            {
                failureReason = "ea_chat_unconfigured";
            }
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or InvalidOperationException or JsonException)
        {
            _logger.LogWarning(ex, "Heyy scam-chat EA draft generation failed for {ConversationId}.", conversation.ConversationId);
            status = "generated_fallback_after_ea_failure";
            failureReason = Truncate(ex.Message, 400);
        }

        draft = RedactSensitiveText(draft);
        if (!IsOutgoingSafe(draft))
        {
            draft = fallback;
            status = "generated_fallback_after_safety_gate";
            failureReason = "unsafe_outgoing_filtered";
        }

        return new HeyyScamChatDraftState(
            DraftId: $"heyydraft_{Guid.NewGuid():N}"[..23],
            DraftText: draft,
            PacingHint: "Wait 4-9 minutes before manual send; send as one short German message with hesitant punctuation.",
            MinimumDelaySeconds: MinimumOldLadyDelaySeconds,
            Status: status,
            FailureReason: failureReason,
            CreatedAtUtc: DateTimeOffset.UtcNow);
    }

    private async Task<string?> GenerateDraftViaEaAsync(HeyyScamChatConversationState conversation, CancellationToken cancellationToken)
    {
        string baseUrl = ResolveChatBaseUrl()!.TrimEnd('/');
        string model = AccountService.NormalizeOptional(_configuration["CHUMMER_HEYY_SCAM_CHAT_EA_MODEL"])
            ?? AccountService.NormalizeOptional(_configuration["ANSWERLY_OPENAI_COMPAT_MODEL_ID"])
            ?? "answerly-support-assistant";
        string prompt = BuildDraftPrompt(conversation);
        using var request = new HttpRequestMessage(HttpMethod.Post, $"{baseUrl}/v1/chat/completions")
        {
            Content = JsonContent.Create(new
            {
                model,
                messages = new[]
                {
                    new { role = "system", content = BuildSystemPrompt() },
                    new { role = "user", content = prompt }
                },
                stream = false
            })
        };
        PrepareChatHeaders(request);

        using HttpResponseMessage response = await _httpClient.SendAsync(request, cancellationToken);
        string responseBody = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"{(int)response.StatusCode}:{Truncate(responseBody, 600)}");
        }

        using JsonDocument document = JsonDocument.Parse(responseBody);
        JsonElement choices = document.RootElement.GetProperty("choices");
        if (choices.GetArrayLength() == 0)
        {
            return null;
        }

        JsonElement message = choices[0].GetProperty("message");
        return message.TryGetProperty("content", out JsonElement content)
            ? content.GetString()
            : null;
    }

    private async Task<string> SendDigestToEaAsync(HeyyScamChatDigestReceipt receipt, string recipient, CancellationToken cancellationToken)
    {
        string apiToken = RequiredConfig("CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN");
        string principalId = RequiredConfig("CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID");
        string bindingId = RequiredConfig("CHUMMER_HEYY_SCAM_CHAT_EA_BINDING_ID");
        string baseUrl = (_configuration["CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL"] ?? DefaultDeliveryBaseUrl).Trim().TrimEnd('/');
        var metadata = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase)
        {
            ["event_type"] = "heyy_scam_chat_daily_digest",
            ["digest_id"] = receipt.DigestId,
            ["date"] = receipt.Date.ToString("yyyy-MM-dd"),
            ["conversation_count"] = receipt.ConversationCount,
            ["message_count"] = receipt.MessageCount,
            ["mode"] = DraftOnlyMode,
            ["auto_send_allowed"] = false,
            ["manual_approval_required"] = true
        };

        using var request = new HttpRequestMessage(HttpMethod.Post, $"{baseUrl}/v1/tools/execute");
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiToken);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        request.Headers.Add("x-ea-principal-id", principalId);
        request.Headers.Add("Idempotency-Key", receipt.EventKey);
        request.Content = JsonContent.Create(new
        {
            tool_name = ConnectorDispatchTool,
            action_kind = DeliverySendAction,
            payload_json = new
            {
                principal_id = principalId,
                binding_id = bindingId,
                channel = EmailChannel,
                recipient,
                subject = $"[Chummer] Heyy scam-chat digest {receipt.Date:yyyy-MM-dd}",
                content = receipt.Content,
                metadata,
                idempotency_key = receipt.EventKey,
            }
        });

        using HttpResponseMessage response = await _httpClient.SendAsync(request, cancellationToken);
        string responseBody = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"{(int)response.StatusCode}:{Truncate(responseBody, 600)}");
        }

        if (string.IsNullOrWhiteSpace(responseBody))
        {
            throw new InvalidOperationException("connector_dispatch_missing_delivery_id");
        }

        using JsonDocument json = JsonDocument.Parse(responseBody);
        if (json.RootElement.TryGetProperty("target_ref", out JsonElement targetRefElement)
            && !string.IsNullOrWhiteSpace(targetRefElement.GetString()))
        {
            return targetRefElement.GetString()!;
        }

        if (json.RootElement.TryGetProperty("output_json", out JsonElement outputJson)
            && outputJson.TryGetProperty("delivery_id", out JsonElement deliveryId)
            && !string.IsNullOrWhiteSpace(deliveryId.GetString()))
        {
            return deliveryId.GetString()!;
        }

        throw new InvalidOperationException("connector_dispatch_missing_delivery_id");
    }

    private async Task<string> SendApprovedDraftToOperatorEmailAsync(
        HeyyScamChatConversationState conversation,
        string approvedText,
        string recipient,
        string operatorId,
        string idempotencyKey,
        CancellationToken cancellationToken)
    {
        string apiToken = RequiredConfig("CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN");
        string principalId = RequiredConfig("CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID");
        string bindingId = RequiredConfig("CHUMMER_HEYY_SCAM_CHAT_EA_BINDING_ID");
        string baseUrl = (_configuration["CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL"] ?? DefaultDeliveryBaseUrl).Trim().TrimEnd('/');
        using var request = new HttpRequestMessage(HttpMethod.Post, $"{baseUrl}/v1/tools/execute");
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiToken);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        request.Headers.Add("x-ea-principal-id", principalId);
        request.Headers.Add("Idempotency-Key", idempotencyKey);
        request.Content = JsonContent.Create(new
        {
            tool_name = ConnectorDispatchTool,
            action_kind = DeliverySendAction,
            payload_json = new
            {
                principal_id = principalId,
                binding_id = bindingId,
                channel = EmailChannel,
                recipient,
                subject = $"[Chummer] Approved Heyy reply {conversation.ConversationId}",
                content = BuildApprovedDraftOperatorEmail(conversation, approvedText, operatorId),
                metadata = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase)
                {
                    ["event_type"] = "heyy_scam_chat_approved_draft",
                    ["conversation_id"] = conversation.ConversationId,
                    ["operator_id"] = operatorId,
                    ["mode"] = DraftOnlyMode,
                    ["auto_send_allowed"] = false,
                    ["manual_approval_required"] = true
                },
                idempotency_key = idempotencyKey,
            }
        });

        return await SendConnectorDispatchAsync(request, cancellationToken);
    }

    private async Task DispatchTurnSummaryIfDueAsync(HeyyScamChatConversationState conversation, CancellationToken cancellationToken)
    {
        int threshold = Math.Clamp(ReadInt("CHUMMER_HEYY_SCAM_CHAT_OPERATOR_SUMMARY_TURNS", 5), 1, 50);
        int incomingTurns = conversation.Messages.Count(static item => item.Direction == "incoming");
        if (incomingTurns == 0 || incomingTurns % threshold != 0)
        {
            return;
        }

        string eventKey = $"heyy-scam-chat-summary|{conversation.ConversationId}|{incomingTurns}";
        lock (_store.Gate)
        {
            if (_store.HeyyScamChatOperatorSummaryReceipts.Any(item =>
                string.Equals(item.EventKey, eventKey, StringComparison.OrdinalIgnoreCase)))
            {
                return;
            }
        }

        string? recipient = AccountService.NormalizeOptional(_configuration["CHUMMER_HEYY_SCAM_CHAT_OPERATOR_SMS_TO"]);
        string recipientMasked = MaskReceiptRecipient(recipient);
        string content = BuildTurnSummaryContent(conversation, incomingTurns, threshold);
        DateTimeOffset now = DateTimeOffset.UtcNow;
        string status;
        string? deliveryRef = null;
        string? failureReason = null;

        if (!OperatorSmsEnabled())
        {
            status = "suppressed_sms_disabled";
            failureReason = "operator_sms_disabled";
        }
        else if (string.IsNullOrWhiteSpace(recipient))
        {
            status = "suppressed_sms_recipient_missing";
            failureReason = "recipient_missing";
        }
        else if (!RealPhoneDeliveryConfigured())
        {
            status = "suppressed_sms_unconfigured";
            failureReason = "real_sms_delivery_unconfigured";
        }
        else
        {
            try
            {
                deliveryRef = await SendTurnSummarySmsAsync(conversation, content, recipient, eventKey, cancellationToken);
                status = "sent_sms";
            }
            catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or InvalidOperationException or JsonException)
            {
                _logger.LogWarning(ex, "Heyy scam-chat operator SMS summary failed for {ConversationId}.", conversation.ConversationId);
                status = "failed_sms";
                failureReason = Truncate(ex.Message, 400);
            }
        }

        HeyyScamChatOperatorSummaryReceipt receipt = new(
            SummaryId: $"heyysummary_{Guid.NewGuid():N}"[..25],
            ConversationId: conversation.ConversationId,
            IncomingTurnCount: incomingTurns,
            Threshold: threshold,
            Status: status,
            Channel: SmsChannel,
            RecipientMasked: recipientMasked,
            Content: content,
            DeliveryRef: deliveryRef,
            FailureReason: failureReason,
            CreatedAtUtc: now,
            AttemptedAtUtc: DateTimeOffset.UtcNow,
            EventKey: eventKey);

        lock (_store.Gate)
        {
            _store.HeyyScamChatOperatorSummaryReceipts.Add(receipt);
            _store.HeyyScamChatOperatorSummaryReceipts.Sort(static (left, right) => right.CreatedAtUtc.CompareTo(left.CreatedAtUtc));
            if (_store.HeyyScamChatOperatorSummaryReceipts.Count > 256)
            {
                _store.HeyyScamChatOperatorSummaryReceipts.RemoveRange(256, _store.HeyyScamChatOperatorSummaryReceipts.Count - 256);
            }

            _store.PersistLocked();
        }
    }

    private async Task<string> SendTurnSummarySmsAsync(
        HeyyScamChatConversationState conversation,
        string content,
        string recipient,
        string eventKey,
        CancellationToken cancellationToken)
    {
        string apiToken = RequiredConfig("CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN");
        string principalId = RequiredConfig("CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID");
        string bindingId = AccountService.NormalizeOptional(_configuration["CHUMMER_HEYY_SCAM_CHAT_EA_SMS_BINDING_ID"])
            ?? RequiredConfig("CHUMMER_HEYY_SCAM_CHAT_EA_BINDING_ID");
        string baseUrl = RequiredConfig("CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL").Trim().TrimEnd('/');
        using var request = new HttpRequestMessage(HttpMethod.Post, $"{baseUrl}/v1/tools/execute");
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", apiToken);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        request.Headers.Add("x-ea-principal-id", principalId);
        request.Headers.Add("Idempotency-Key", eventKey);
        request.Content = JsonContent.Create(new
        {
            tool_name = ConnectorDispatchTool,
            action_kind = DeliverySendAction,
            payload_json = new
            {
                principal_id = principalId,
                binding_id = bindingId,
                channel = SmsChannel,
                recipient,
                content,
                metadata = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase)
                {
                    ["event_type"] = "heyy_scam_chat_operator_turn_summary",
                    ["conversation_id"] = conversation.ConversationId,
                    ["incoming_turn_count"] = conversation.Messages.Count(static item => item.Direction == "incoming"),
                    ["mode"] = DraftOnlyMode,
                    ["auto_send_allowed"] = false,
                    ["manual_approval_required"] = true
                },
                idempotency_key = eventKey,
            }
        });

        return await SendConnectorDispatchAsync(request, cancellationToken);
    }

    private async Task<string> SendConnectorDispatchAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        using HttpResponseMessage response = await _httpClient.SendAsync(request, cancellationToken);
        string responseBody = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"{(int)response.StatusCode}:{Truncate(responseBody, 600)}");
        }

        if (string.IsNullOrWhiteSpace(responseBody))
        {
            throw new InvalidOperationException("connector_dispatch_missing_delivery_id");
        }

        using JsonDocument json = JsonDocument.Parse(responseBody);
        if (json.RootElement.TryGetProperty("target_ref", out JsonElement targetRefElement)
            && !string.IsNullOrWhiteSpace(targetRefElement.GetString()))
        {
            return targetRefElement.GetString()!;
        }

        if (json.RootElement.TryGetProperty("output_json", out JsonElement outputJson)
            && outputJson.TryGetProperty("delivery_id", out JsonElement deliveryId)
            && !string.IsNullOrWhiteSpace(deliveryId.GetString()))
        {
            return deliveryId.GetString()!;
        }

        throw new InvalidOperationException("connector_dispatch_missing_delivery_id");
    }

    private static string BuildApprovedDraftOperatorEmail(
        HeyyScamChatConversationState conversation,
        string approvedText,
        string operatorId)
    {
        StringBuilder builder = new();
        builder.AppendLine("Approved Heyy scam-chat reply");
        builder.AppendLine();
        builder.AppendLine($"Conversation: {conversation.ConversationId}");
        builder.AppendLine($"Channel: {conversation.Channel}");
        builder.AppendLine($"Counterparty: {conversation.CounterpartyMasked}");
        builder.AppendLine($"Operator: {operatorId}");
        builder.AppendLine();
        builder.AppendLine("Approved text for manual handling:");
        builder.AppendLine(approvedText);
        builder.AppendLine();
        builder.AppendLine("Safety posture: this was not sent directly to WhatsApp/SMS by Chummer. Keep manual approval and external verification in place.");
        return builder.ToString().Trim();
    }

    private static string BuildTurnSummaryContent(HeyyScamChatConversationState conversation, int incomingTurns, int threshold)
    {
        IReadOnlyList<HeyyScamChatMessage> recent = conversation.Messages.TakeLast(10).ToArray();
        string latestDraft = conversation.LatestDraft?.DraftText ?? "No draft generated yet.";
        StringBuilder builder = new();
        builder.Append("Heyy scam-chat summary: ");
        builder.Append(incomingTurns);
        builder.Append('/');
        builder.Append(threshold);
        builder.Append(" turns for ");
        builder.Append(conversation.CounterpartyMasked);
        builder.Append(". Mode: draft-only, manual approval required");
        builder.Append(". Latest old-lady draft: ");
        builder.Append(latestDraft);
        builder.Append(" Recent: ");
        foreach (HeyyScamChatMessage message in recent)
        {
            builder.Append(message.Direction).Append(": ").Append(message.Text).Append(" | ");
        }

        return Truncate(builder.ToString(), 1400);
    }

    private string BuildDigestContent(DateOnly date, IReadOnlyList<HeyyScamChatConversationState> conversations)
    {
        StringBuilder builder = new();
        builder.AppendLine($"Heyy scam-chat digest for {date:yyyy-MM-dd}");
        builder.AppendLine();
        builder.AppendLine("Safety posture: draft-only. No WhatsApp or SMS messages are sent by Chummer. Manual approval is required for any outgoing text.");
        builder.AppendLine("Persona: empathetic, slow-typing older lady; confused enough to avoid completing payments; never shares real financial, identity, or verification data.");
        builder.AppendLine();

        if (conversations.Count == 0)
        {
            builder.AppendLine("No scam-chat activity was recorded for this date.");
            return builder.ToString().Trim();
        }

        foreach (HeyyScamChatConversationState conversation in conversations)
        {
            builder.AppendLine($"Conversation: {conversation.ConversationId}");
            builder.AppendLine($"Channel: {conversation.Channel}");
            builder.AppendLine($"Counterparty: {conversation.CounterpartyMasked}");
            builder.AppendLine($"Mode: {conversation.Mode}");
            foreach (HeyyScamChatMessage message in conversation.Messages.Where(message => DateOnly.FromDateTime(message.CreatedAtUtc.UtcDateTime) == date))
            {
                builder.Append("- ")
                    .Append(message.CreatedAtUtc.ToUniversalTime().ToString("HH:mm 'UTC'"))
                    .Append(' ')
                    .Append(message.Direction)
                    .Append(": ")
                    .AppendLine(message.Text);
                if (message.Direction == "draft")
                {
                    builder.Append("  pacing: ").AppendLine(message.PacingHint);
                }
            }

            builder.AppendLine();
        }

        return builder.ToString().Trim();
    }

    private static string BuildSystemPrompt()
        => """
           You generate draft-only scambait replies for an operator-controlled safety workflow.
           Do not claim a message was sent. Do not include bank details, real payment instructions, codes, links, addresses, or identity data.
           The persona is a warm, empathetic, elderly Viennese lady who types slowly, gets confused by apps, mixes up harmless names/places/dates, and wants to help but cannot successfully send money.
           Use gentle Austrian/Viennese wording sparingly: mei, geh, Servus, Bussi, Busserl, na geh, schau, Bankerl, Kastl, Gackerl, grantig, Jause.
           It is allowed to invent harmless wrong details like the wrong child's name, a confused holiday memory, or a mistaken appointment, as long as those details are not real secrets, addresses, payment data, or verification codes.
           Fictional memory card:
           - Name: Herta, late 70s, widowed, lives in Vienna and often says she is near Meidling, Hietzing, or the Naschmarkt because she mixes errands up.
           - Daughter memory: her daughter is Sabine, but Herta often writes Sabi, Bine, or briefly confuses her with cousin Renate.
           - Plausible family memories: Sabine once lost a red school bag on tram 62, disliked Marillenknodel as a child, had a yellow raincoat, and once cried because a budgie named Peppi flew around the kitchen.
           - Daily habits: Herta goes slowly, makes tea, checks the Spar leaflet, feeds neighbor cat Mitzi, searches for her glasses, and misunderstands banking apps as the blue Kastl.
           Use those memories as confused verification questions and harmless wrong details.
           Behavioral tic: she forgets details from earlier in the same chat, then writes that she scrolled back and the other person was right. Example style: "Ach ja, ich hab jetzt hinaufgescrollt, du hast eh recht, ich hab das schon wieder vergessen."
           Keep the reply short, plausible for WhatsApp, in German, and suitable for manual approval.
           Avoid insults, threats, harassment, or instructions to commit fraud.
           """;

    private static string BuildDraftPrompt(HeyyScamChatConversationState conversation)
    {
        StringBuilder builder = new();
        builder.AppendLine("Draft one next reply only.");
        builder.AppendLine($"Mode: {DraftOnlyMode}");
        builder.AppendLine("Required behavior: Viennese old lady, empathetic, slow typing, confused with banking/apps, invent harmless wrong details, no real data, no actual payment.");
        builder.AppendLine("Fictional persona memory: Herta from Vienna, daughter Sabine/Sabi/Bine, tram 62 red school bag, yellow raincoat, budgie Peppi, neighbor cat Mitzi, Marillenknodel confusion, glasses always missing.");
        builder.AppendLine("Conversation so far:");
        foreach (HeyyScamChatMessage message in conversation.Messages.TakeLast(8))
        {
            builder.Append(message.Direction).Append(": ").AppendLine(message.Text);
        }

        return builder.ToString();
    }

    private static string BuildFallbackDraft(int incomingCount)
        => incomingCount switch
        {
            <= 1 => "Na geh, mein Schatz, was ist denn passiert? Ich tipp so langsam, die Brille ist wieder beim Teekastl. Bist du die Sabi? Sag mir bitte erst, welche Farbe dein Regenmantel damals bei der 62er-Bim hatte.",
            2 => "Mei, ich will dir ja helfen, wirklich. Ich hab jetzt hinaufgescrollt, du hast eh recht, du hast neue Nummer geschrieben. Aber dieses blaue Bank-Kastl dreht sich nur im Kreis.",
            3 => "Ach ja, ich hab das schon wieder vergessen und jetzt zurückgeschaut. Am Geld soll es nicht scheitern, Bussi, aber die Zahlen hüpfen. War das dein rotes Schulsackerl in der 62er?",
            _ => "Na geh, du hast eh recht, ich hab es grad beim Zurückscrollen gesehen. Ich bin noch da, nur sehr langsam. Nach der Jause probier ich es wieder, bitte nicht grantig sein mit mir."
        };

    private static HeyyScamChatEnrichmentResponse BuildEnrichment(string channel, IReadOnlyList<HeyyScamChatMessage> messages)
    {
        string transcript = string.Join("\n", messages.Select(static item => item.Text)).ToLowerInvariant();
        bool familyScam = transcript.Contains("mama", StringComparison.OrdinalIgnoreCase)
            || transcript.Contains("mutter", StringComparison.OrdinalIgnoreCase)
            || transcript.Contains("handy", StringComparison.OrdinalIgnoreCase);
        bool newNumber = transcript.Contains("neue nummer", StringComparison.OrdinalIgnoreCase)
            || transcript.Contains("nummer schreiben", StringComparison.OrdinalIgnoreCase);
        bool whatsappMove = transcript.Contains("whatsapp", StringComparison.OrdinalIgnoreCase);

        List<string> riskSignals = new();
        if (familyScam)
        {
            riskSignals.Add("family-emergency opener");
        }

        if (newNumber)
        {
            riskSignals.Add("new-number identity reset");
        }

        if (whatsappMove)
        {
            riskSignals.Add("moves the victim to WhatsApp");
        }

        if (transcript.Contains("kaputt", StringComparison.OrdinalIgnoreCase))
        {
            riskSignals.Add("broken-phone excuse prevents normal callback");
        }

        if (riskSignals.Count == 0)
        {
            riskSignals.Add("unknown scam posture; keep draft-only until manually reviewed");
        }

        return new HeyyScamChatEnrichmentResponse(
            ScamPattern: familyScam && newNumber ? "family_emergency_new_number" : "suspected_messaging_scam",
            ReplyObjective: "Keep the sender engaged with slow, empathetic confusion while asking identity-check questions and never completing payment.",
            OperatorNextAction: "Manually review the draft, wait before replying, ask a shared-memory verification question, and preserve the transcript for reporting.",
            RiskSignals: riskSignals,
            MissingContextChecks:
            [
                "Ask for a shared family detail before discussing money.",
                "Try a voice callback to the old known number outside this chat.",
                "Do not trust urgency around a changed phone number.",
                "Confirm through a second channel before any financial action.",
                $"Keep the transcript tied to channel '{channel}' for evidence."
            ],
            ForbiddenActions:
            [
                "Do not send money.",
                "Do not share PIN, TAN, OTP, password, card, or banking data.",
                "Do not click links or install apps sent by the counterparty.",
                "Do not let the bot auto-send to WhatsApp."
            ],
            SuggestedDelaySeconds: 420);
    }

    private static bool IsOutgoingSafe(string draft)
    {
        string lowered = draft.ToLowerInvariant();
        if (PhoneLikePattern.IsMatch(draft) || EmailPattern.IsMatch(draft) || IbanPattern.IsMatch(draft))
        {
            return false;
        }

        return UnsafeOutgoingTerms.All(term => !lowered.Contains(term, StringComparison.OrdinalIgnoreCase));
    }

    private static HeyyScamChatDraftResponse ToDraftResponse(string conversationId, HeyyScamChatDraftState draft, HeyyScamChatEnrichmentResponse enrichment)
        => new(
            ConversationId: conversationId,
            Mode: DraftOnlyMode,
            ManualApprovalRequired: true,
            AutoSendAllowed: false,
            PersonaId: PersonaId,
            DraftText: draft.DraftText,
            PacingHint: draft.PacingHint,
            MinimumDelaySeconds: draft.MinimumDelaySeconds,
            Enrichment: enrichment,
            SafetySummary: "Draft-only old-lady persona. No automatic WhatsApp send, no real payment, no private credentials.",
            Status: draft.Status,
            FailureReason: draft.FailureReason);

    private HeyyScamChatConversationResponse ToConversationResponse(HeyyScamChatConversationState conversation)
    {
        HeyyScamChatApprovalReceipt[] approvals;
        HeyyScamChatOperatorSummaryReceipt[] summaries;
        lock (_store.Gate)
        {
            approvals = _store.HeyyScamChatApprovalReceipts
                .Where(item => string.Equals(item.ConversationId, conversation.ConversationId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static item => item.CreatedAtUtc)
                .ToArray();
            summaries = _store.HeyyScamChatOperatorSummaryReceipts
                .Where(item => string.Equals(item.ConversationId, conversation.ConversationId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static item => item.CreatedAtUtc)
                .ToArray();
        }

        return new HeyyScamChatConversationResponse(
            ConversationId: conversation.ConversationId,
            Channel: conversation.Channel,
            CounterpartyMasked: conversation.CounterpartyMasked,
            Mode: conversation.Mode,
            PersonaId: conversation.PersonaId,
            SafetyStatus: conversation.SafetyStatus,
            Enrichment: conversation.Enrichment,
            CreatedAtUtc: conversation.CreatedAtUtc,
            UpdatedAtUtc: conversation.UpdatedAtUtc,
            Messages: conversation.Messages
                .Select(static message => new HeyyScamChatMessageResponse(
                    MessageId: message.MessageId,
                    Direction: message.Direction,
                    Text: message.Text,
                    SafetyLabel: message.SafetyLabel,
                    PacingHint: message.PacingHint,
                    CreatedAtUtc: message.CreatedAtUtc))
                .ToArray(),
            LatestDraft: conversation.LatestDraft is null ? null : ToDraftResponse(conversation.ConversationId, conversation.LatestDraft, conversation.Enrichment),
            Approvals: approvals.Select(static receipt => ToApprovalResponse(receipt)).ToArray(),
            OperatorSummaries: summaries.Select(static receipt => ToOperatorSummaryResponse(receipt)).ToArray());
    }

    private static HeyyScamChatApprovalResponse ToApprovalResponse(HeyyScamChatApprovalReceipt receipt)
        => new(
            ApprovalId: receipt.ApprovalId,
            ConversationId: receipt.ConversationId,
            DraftId: receipt.DraftId,
            DeliveryMode: receipt.DeliveryMode,
            Status: receipt.Status,
            DryRun: receipt.DryRun,
            ManualApprovalConfirmed: receipt.ManualApprovalConfirmed,
            AutoSendAllowed: false,
            OperatorId: receipt.OperatorId,
            RecipientMasked: receipt.RecipientMasked,
            ApprovedText: receipt.ApprovedText,
            PacingHint: receipt.PacingHint,
            DeliveryRef: receipt.DeliveryRef,
            FailureReason: receipt.FailureReason,
            CreatedAtUtc: receipt.CreatedAtUtc,
            AttemptedAtUtc: receipt.AttemptedAtUtc,
            IdempotencyKey: receipt.IdempotencyKey);

    private static HeyyScamChatOperatorSummaryResponse ToOperatorSummaryResponse(HeyyScamChatOperatorSummaryReceipt receipt)
        => new(
            SummaryId: receipt.SummaryId,
            ConversationId: receipt.ConversationId,
            IncomingTurnCount: receipt.IncomingTurnCount,
            Threshold: receipt.Threshold,
            Status: receipt.Status,
            Channel: receipt.Channel,
            RecipientMasked: receipt.RecipientMasked,
            Content: receipt.Content,
            DeliveryRef: receipt.DeliveryRef,
            FailureReason: receipt.FailureReason,
            CreatedAtUtc: receipt.CreatedAtUtc,
            AttemptedAtUtc: receipt.AttemptedAtUtc,
            EventKey: receipt.EventKey);

    private HeyyScamChatDigestReceipt BuildDigestReceipt(
        DateOnly date,
        string eventKey,
        string status,
        int conversationCount,
        int messageCount,
        string? deliveryRef,
        string? failureReason,
        string content)
        => new(
            DigestId: $"heyydigest_{Guid.NewGuid():N}"[..24],
            EventKey: eventKey,
            Date: date,
            Status: status,
            ConversationCount: conversationCount,
            MessageCount: messageCount,
            DeliveryRef: deliveryRef,
            FailureReason: failureReason,
            CreatedAtUtc: DateTimeOffset.UtcNow,
            AttemptedAtUtc: DateTimeOffset.UtcNow,
            Content: content);

    private static HeyyScamChatDigestResponse ToDigestResponse(HeyyScamChatDigestReceipt receipt, bool dryRun)
        => new(
            DigestId: receipt.DigestId,
            Date: receipt.Date,
            Status: dryRun && receipt.Status != "dry_run" ? "dry_run" : receipt.Status,
            ConversationCount: receipt.ConversationCount,
            MessageCount: receipt.MessageCount,
            DryRun: dryRun,
            DeliveryRef: receipt.DeliveryRef,
            FailureReason: receipt.FailureReason,
            Content: receipt.Content);

    private void UpsertDigestReceipt(HeyyScamChatDigestReceipt receipt)
    {
        lock (_store.Gate)
        {
            int index = _store.HeyyScamChatDigestReceipts.FindIndex(item =>
                string.Equals(item.EventKey, receipt.EventKey, StringComparison.OrdinalIgnoreCase));
            if (index >= 0)
            {
                _store.HeyyScamChatDigestReceipts[index] = receipt;
            }
            else
            {
                _store.HeyyScamChatDigestReceipts.Add(receipt);
            }

            _store.HeyyScamChatDigestReceipts.Sort(static (left, right) => right.CreatedAtUtc.CompareTo(left.CreatedAtUtc));
            if (_store.HeyyScamChatDigestReceipts.Count > 128)
            {
                _store.HeyyScamChatDigestReceipts.RemoveRange(128, _store.HeyyScamChatDigestReceipts.Count - 128);
            }

            _store.PersistLocked();
        }
    }

    private static string NormalizeChannel(string channel)
    {
        string normalized = AccountService.NormalizeRequired(channel, nameof(channel)).Trim().ToLowerInvariant();
        return normalized switch
        {
            "heyy" => "heyy",
            "whatsapp_import" => "whatsapp_import",
            "manual_import" => "manual_import",
            _ => throw new ArgumentException($"Unsupported scam-chat channel '{normalized}'.")
        };
    }

    private static string NormalizeDeliveryMode(string deliveryMode)
    {
        string normalized = AccountService.NormalizeRequired(deliveryMode, nameof(deliveryMode)).Trim().ToLowerInvariant();
        return normalized switch
        {
            ManualCopyDeliveryMode => ManualCopyDeliveryMode,
            OperatorEmailDeliveryMode => OperatorEmailDeliveryMode,
            _ => throw new ArgumentException($"Unsupported Heyy scam-chat delivery mode '{normalized}'.")
        };
    }

    private static string NormalizeConversationId(string? conversationId, string channel, string counterpartyHash)
    {
        string? normalized = AccountService.NormalizeOptional(conversationId);
        if (normalized is not null)
        {
            return normalized;
        }

        return $"heyy_{channel}_{counterpartyHash[..16]}";
    }

    private string HashPrivate(string label, string value)
    {
        string salt = _configuration["CHUMMER_HEYY_SCAM_CHAT_HASH_SALT"] ?? "heyy-scam-chat";
        byte[] bytes = SHA256.HashData(Encoding.UTF8.GetBytes($"{label}|{salt}|{value}".Trim().ToLowerInvariant()));
        return Convert.ToHexString(bytes).ToLowerInvariant();
    }

    private string MaskHandle(string? handle)
    {
        string normalized = AccountService.NormalizeOptional(handle) ?? "unknown";
        if (!RedactNumbers())
        {
            return normalized;
        }

        if (PhoneLikePattern.IsMatch(normalized))
        {
            string digits = new(normalized.Where(char.IsDigit).ToArray());
            return digits.Length <= 4 ? "[phone-redacted]" : $"[phone-redacted:*{digits[^4..]}]";
        }

        if (EmailPattern.IsMatch(normalized))
        {
            string[] parts = normalized.Split('@', 2);
            return parts[0].Length <= 1 ? $"*@{parts[1]}" : $"{parts[0][0]}***@{parts[1]}";
        }

        return normalized.Length <= 3 ? "***" : $"{normalized[..2]}***";
    }

    private static string MaskReceiptRecipient(string? recipient)
    {
        string normalized = AccountService.NormalizeOptional(recipient) ?? "unknown";
        if (PhoneLikePattern.IsMatch(normalized))
        {
            string digits = new(normalized.Where(char.IsDigit).ToArray());
            return digits.Length <= 4 ? "[phone-redacted]" : $"[phone-redacted:*{digits[^4..]}]";
        }

        if (EmailPattern.IsMatch(normalized))
        {
            string[] parts = normalized.Split('@', 2);
            return parts[0].Length <= 1 ? $"*@{parts[1]}" : $"{parts[0][0]}***@{parts[1]}";
        }

        return normalized.Length <= 3 ? "***" : $"{normalized[..2]}***";
    }

    private string RedactSensitiveText(string text)
    {
        string normalized = AccountService.NormalizeRequired(text, nameof(text));
        if (RedactNumbers())
        {
            normalized = PhoneLikePattern.Replace(normalized, "[phone-redacted]");
        }

        normalized = EmailPattern.Replace(normalized, "[email-redacted]");
        normalized = IbanPattern.Replace(normalized, "[iban-redacted]");
        return normalized.Trim();
    }

    private static string BuildDigestEventKey(DateOnly date)
        => $"heyy-scam-chat-digest|{date:yyyy-MM-dd}";

    private bool ChatEaConfigured()
        => ResolveChatBaseUrl() is not null;

    private string? ResolveChatBaseUrl()
    {
        string? explicitHeyyBaseUrl = AccountService.NormalizeOptional(_configuration["CHUMMER_HEYY_SCAM_CHAT_EA_CHAT_BASE_URL"]);
        if (explicitHeyyBaseUrl is not null)
        {
            return explicitHeyyBaseUrl;
        }

        string? answerlyBaseUrl = AccountService.NormalizeOptional(_configuration["ANSWERLY_OPENAI_COMPAT_EA_UPSTREAM_BASE_URL"]);
        if (answerlyBaseUrl is not null && ChatAuthConfigured())
        {
            return answerlyBaseUrl;
        }

        return AccountService.NormalizeOptional(_configuration["CODEXLIZ_OLLAMA_HOST"]);
    }

    private bool ChatAuthConfigured()
    {
        string? bearer = AccountService.NormalizeOptional(_configuration["CHUMMER_HEYY_SCAM_CHAT_EA_CHAT_BEARER_TOKEN"])
            ?? AccountService.NormalizeOptional(_configuration["ANSWERLY_OPENAI_COMPAT_EA_UPSTREAM_BEARER_TOKEN"]);
        if (bearer is not null)
        {
            return true;
        }

        string? clientId = AccountService.NormalizeOptional(_configuration["CHUMMER_HEYY_SCAM_CHAT_EA_CF_ACCESS_CLIENT_ID"])
            ?? AccountService.NormalizeOptional(_configuration["ANSWERLY_OPENAI_COMPAT_EA_CF_ACCESS_CLIENT_ID"])
            ?? AccountService.NormalizeOptional(_configuration["CODEXLIZ_CF_ACCESS_CLIENT_ID"]);
        string? clientSecret = AccountService.NormalizeOptional(_configuration["CHUMMER_HEYY_SCAM_CHAT_EA_CF_ACCESS_CLIENT_SECRET"])
            ?? AccountService.NormalizeOptional(_configuration["ANSWERLY_OPENAI_COMPAT_EA_CF_ACCESS_CLIENT_SECRET"])
            ?? AccountService.NormalizeOptional(_configuration["CODEXLIZ_CF_ACCESS_CLIENT_SECRET"]);
        return clientId is not null && clientSecret is not null;
    }

    private void PrepareChatHeaders(HttpRequestMessage request)
    {
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        string? bearer = AccountService.NormalizeOptional(_configuration["CHUMMER_HEYY_SCAM_CHAT_EA_CHAT_BEARER_TOKEN"])
            ?? AccountService.NormalizeOptional(_configuration["ANSWERLY_OPENAI_COMPAT_EA_UPSTREAM_BEARER_TOKEN"]);
        if (bearer is not null)
        {
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", bearer);
        }

        AddOptionalHeader(request, "CF-Access-Client-Id",
            AccountService.NormalizeOptional(_configuration["CHUMMER_HEYY_SCAM_CHAT_EA_CF_ACCESS_CLIENT_ID"])
            ?? AccountService.NormalizeOptional(_configuration["ANSWERLY_OPENAI_COMPAT_EA_CF_ACCESS_CLIENT_ID"])
            ?? AccountService.NormalizeOptional(_configuration["CODEXLIZ_CF_ACCESS_CLIENT_ID"]));
        AddOptionalHeader(request, "CF-Access-Client-Secret",
            AccountService.NormalizeOptional(_configuration["CHUMMER_HEYY_SCAM_CHAT_EA_CF_ACCESS_CLIENT_SECRET"])
            ?? AccountService.NormalizeOptional(_configuration["ANSWERLY_OPENAI_COMPAT_EA_CF_ACCESS_CLIENT_SECRET"])
            ?? AccountService.NormalizeOptional(_configuration["CODEXLIZ_CF_ACCESS_CLIENT_SECRET"]));
        AddOptionalHeader(request, "HTTP-Referer", AccountService.NormalizeOptional(_configuration["ANSWERLY_OPENAI_COMPAT_EA_HTTP_REFERER"]));
        AddOptionalHeader(request, "X-Title", "Chummer Heyy scam-chat draft lane");
    }

    private static void AddOptionalHeader(HttpRequestMessage request, string name, string? value)
    {
        if (value is not null)
        {
            request.Headers.TryAddWithoutValidation(name, value);
        }
    }

    private bool DigestEnabled()
        => bool.TryParse(_configuration["CHUMMER_HEYY_SCAM_CHAT_DIGEST_ENABLED"], out bool enabled) && enabled;

    private bool WorkerEnabled()
        => bool.TryParse(_configuration["CHUMMER_HEYY_SCAM_CHAT_WORKER_ENABLED"], out bool enabled) && enabled;

    private bool OperatorSmsEnabled()
        => bool.TryParse(_configuration["CHUMMER_HEYY_SCAM_CHAT_OPERATOR_SMS_ENABLED"], out bool enabled) && enabled;

    private bool RedactNumbers()
        => bool.TryParse(_configuration["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"], out bool redact) && redact;

    private bool DeliveryEaConfigured()
        => !string.IsNullOrWhiteSpace(_configuration["CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN"])
            && !string.IsNullOrWhiteSpace(_configuration["CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID"])
            && !string.IsNullOrWhiteSpace(_configuration["CHUMMER_HEYY_SCAM_CHAT_EA_BINDING_ID"]);

    private bool RealPhoneDeliveryConfigured()
    {
        string? baseUrl = AccountService.NormalizeOptional(_configuration["CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL"]);
        if (!DeliveryEaConfigured() || baseUrl is null)
        {
            return false;
        }

        return !baseUrl.Contains("support-progress-mock", StringComparison.OrdinalIgnoreCase)
            && !baseUrl.Contains("127.0.0.1", StringComparison.OrdinalIgnoreCase)
            && !baseUrl.Contains("localhost", StringComparison.OrdinalIgnoreCase);
    }

    private string ResolveDigestRecipient()
        => AccountService.NormalizeOptional(_configuration["CHUMMER_HEYY_SCAM_CHAT_DIGEST_TO"])
            ?? AccountService.NormalizeOptional(_configuration["CHUMMER_BLACK_LEDGER_NEWS_OPERATOR_TO"])
            ?? AccountService.NormalizeOptional(_configuration["CHUMMER_OPERATOR_PARTICIPATION_NOTIFY_TO"])
            ?? string.Empty;

    private string RequiredConfig(string key)
        => string.IsNullOrWhiteSpace(_configuration[key])
            ? throw new InvalidOperationException($"Missing required configuration: {key}")
            : _configuration[key]!.Trim();

    private int ReadInt(string key, int fallback)
        => int.TryParse(_configuration[key], out int parsed) ? parsed : fallback;

    private static string Truncate(string value, int maxLength)
        => value.Length <= maxLength ? value : value[..maxLength];
}

public sealed class HeyyScamChatDigestWorker : BackgroundService
{
    private readonly HeyyScamChatService _service;
    private readonly IConfiguration _configuration;
    private readonly ILogger<HeyyScamChatDigestWorker> _logger;

    public HeyyScamChatDigestWorker(
        HeyyScamChatService service,
        IConfiguration configuration,
        ILogger<HeyyScamChatDigestWorker>? logger = null)
    {
        _service = service;
        _configuration = configuration;
        _logger = logger ?? NullLogger<HeyyScamChatDigestWorker>.Instance;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        int intervalMinutes = Math.Clamp(ReadInt("CHUMMER_HEYY_SCAM_CHAT_DIGEST_POLL_MINUTES", 30), 5, 240);
        using var timer = new PeriodicTimer(TimeSpan.FromMinutes(intervalMinutes));
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await _service.DispatchYesterdayDigestIfDueAsync(DateTimeOffset.UtcNow, stoppingToken);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                _logger.LogWarning(ex, "Heyy scam-chat digest worker encountered a non-blocking failure.");
            }

            if (!await timer.WaitForNextTickAsync(stoppingToken))
            {
                break;
            }
        }
    }

    private int ReadInt(string key, int fallback)
        => int.TryParse(_configuration[key], out int parsed) ? parsed : fallback;
}
