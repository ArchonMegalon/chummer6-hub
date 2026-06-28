using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Contracts.Receipts;
using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Logging.Abstractions;

namespace Chummer.Run.Api.Services.Community;

public sealed record ParticipationIntentResolution(
    string IntentKind,
    string EntryRoute);

public sealed record ParticipationOperatorNotificationReceipt(
    string ReceiptId,
    string EventType,
    string EventKey,
    string UserId,
    string SubjectHash,
    string EmailMasked,
    string EmailHash,
    string DisplayName,
    string IntentKind,
    string EntryRoute,
    string AuthProviderFamily,
    string Status,
    bool IsFirstParticipationEvent,
    DateTimeOffset OccurredAtUtc,
    DateTimeOffset AttemptedAtUtc,
    string? DeliveryRef = null,
    string? Summary = null,
    string? FailureReason = null,
    string? RateLimitBucket = null,
    ReceiptEnvelope? Envelope = null);

public sealed class ParticipationOperatorNotificationService
{
    private const string DefaultEaBaseUrl = "http://127.0.0.1:8090";
    private const string ConnectorDispatchTool = "connector.dispatch";
    private const string DeliverySendAction = "delivery.send";
    private const string EmailChannel = "email";
    private const string WhatsappChannel = "whatsapp";
    private const string ReceiptPrefix = "partnote";
    private const string OperatorRecipientConfigKey = "CHUMMER_OPERATOR_PARTICIPATION_NOTIFY_TO";
    private const string OperatorRecipientWhatsappConfigKey = "CHUMMER_OPERATOR_PARTICIPATION_NOTIFY_TO_WHATSAPP";
    private const string OperatorNotifyChannelConfigKey = "CHUMMER_OPERATOR_PARTICIPATION_NOTIFY_CHANNEL";
    private const string EaApiTokenConfigKey = "CHUMMER_OPERATOR_PARTICIPATION_EA_API_TOKEN";
    private const string EaPrincipalIdConfigKey = "CHUMMER_OPERATOR_PARTICIPATION_EA_PRINCIPAL_ID";
    private const string EaBindingIdConfigKey = "CHUMMER_OPERATOR_PARTICIPATION_EA_BINDING_ID";
    private const string EaWhatsappBindingIdConfigKey = "CHUMMER_OPERATOR_PARTICIPATION_EA_WHATSAPP_BINDING_ID";
    private const string EaBaseUrlConfigKey = "CHUMMER_OPERATOR_PARTICIPATION_EA_BASE_URL";
    private const string HashSaltConfigKey = "CHUMMER_OPERATOR_PARTICIPATION_HASH_SALT";
    private const string NotificationsEnabledConfigKey = "CHUMMER_OPERATOR_PARTICIPATION_NOTIFY_ENABLED";
    private readonly HttpClient _httpClient;
    private readonly CommunityStore _store;
    private readonly IConfiguration _configuration;
    private readonly ILogger<ParticipationOperatorNotificationService> _logger;

    public ParticipationOperatorNotificationService(
        HttpClient httpClient,
        CommunityStore store,
        IConfiguration configuration,
        ILogger<ParticipationOperatorNotificationService>? logger = null)
    {
        _httpClient = httpClient;
        _store = store;
        _configuration = configuration;
        _logger = logger ?? NullLogger<ParticipationOperatorNotificationService>.Instance;
    }

    public ParticipationIntentResolution? ResolveIntent(string? nextPath)
    {
        string normalized = HubBrowserAuthService.SanitizeNextPath(nextPath, "/home");
        if (normalized.StartsWith("/participate/karma-forge", StringComparison.OrdinalIgnoreCase))
        {
            return new ParticipationIntentResolution("karma_forge", "/participate/karma-forge");
        }

        if (normalized.StartsWith("/participate", StringComparison.OrdinalIgnoreCase)
            || normalized.StartsWith("/partizipate", StringComparison.OrdinalIgnoreCase))
        {
            return new ParticipationIntentResolution(
                "guided_contribution",
                normalized.StartsWith("/participate/codex", StringComparison.OrdinalIgnoreCase) ? "/participate/codex" : "/participate");
        }

        if (normalized.StartsWith("/feedback", StringComparison.OrdinalIgnoreCase))
        {
            return new ParticipationIntentResolution("feedback", "/feedback");
        }

        if (normalized.StartsWith("/packages", StringComparison.OrdinalIgnoreCase))
        {
            return new ParticipationIntentResolution("package", "/packages");
        }

        if (normalized.StartsWith("/roadmap", StringComparison.OrdinalIgnoreCase)
            && normalized.Contains("follow", StringComparison.OrdinalIgnoreCase))
        {
            return new ParticipationIntentResolution("roadmap", "/roadmap");
        }

        if (normalized.StartsWith("/account/participation", StringComparison.OrdinalIgnoreCase))
        {
            return new ParticipationIntentResolution("beta", "/account/participation");
        }

        if (normalized.StartsWith("/mobile", StringComparison.OrdinalIgnoreCase)
            || normalized.StartsWith("/pwa", StringComparison.OrdinalIgnoreCase))
        {
            return new ParticipationIntentResolution("mobile_pwa", normalized.StartsWith("/pwa", StringComparison.OrdinalIgnoreCase) ? "/pwa" : "/mobile");
        }

        if (normalized.StartsWith("/play", StringComparison.OrdinalIgnoreCase)
            || normalized.StartsWith("/player", StringComparison.OrdinalIgnoreCase)
            || normalized.StartsWith("/gm", StringComparison.OrdinalIgnoreCase)
            || normalized.StartsWith("/observer", StringComparison.OrdinalIgnoreCase))
        {
            return new ParticipationIntentResolution("play", normalized);
        }

        return null;
    }

    public async Task<ParticipationOperatorNotificationReceipt?> NotifyAccountOpenedIfNeededAsync(
        HubUserDto user,
        string? email,
        string? nextPath,
        string authProviderFamily,
        bool accountCreated,
        CancellationToken cancellationToken)
    {
        if (!accountCreated)
        {
            return null;
        }

        ParticipationIntentResolution? intent = ResolveIntent(nextPath);
        if (intent is null)
        {
            return null;
        }

        return await DispatchAsync(
            user,
            email,
            eventType: "participant_account_opened",
            eventKey: $"participant_account_opened|{user.UserId}|{intent.IntentKind}|{intent.EntryRoute}",
            intentKind: intent.IntentKind,
            entryRoute: intent.EntryRoute,
            authProviderFamily: authProviderFamily,
            cancellationToken);
    }

    public async Task<ParticipationOperatorNotificationReceipt?> NotifyFirstActionIfNeededAsync(
        HubUserDto user,
        string? email,
        string intentKind,
        string entryRoute,
        string authProviderFamily,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(intentKind))
        {
            throw new ArgumentException("intentKind is required.", nameof(intentKind));
        }

        return await DispatchAsync(
            user,
            email,
            eventType: "participant_first_action",
            eventKey: $"participant_first_action|{user.UserId}",
            intentKind: intentKind.Trim().ToLowerInvariant(),
            entryRoute: NormalizeEntryRoute(entryRoute),
            authProviderFamily: authProviderFamily,
            cancellationToken);
    }

    public IReadOnlyList<ParticipationOperatorNotificationReceipt> ListReceiptsForUser(string userId, int take = 12)
    {
        string normalizedUserId = AccountService.NormalizeRequired(userId, nameof(userId));
        lock (_store.Gate)
        {
            return _store.ParticipationNotificationReceipts
                .Where(receipt => string.Equals(receipt.UserId, normalizedUserId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static receipt => receipt.OccurredAtUtc)
                .Take(Math.Max(1, take))
                .ToArray();
        }
    }

    public static string InferAuthProviderFamily(AccountLinkSummaryDto? links)
    {
        string recommended = (links?.RecommendedPrimaryAuth ?? string.Empty).Trim().ToLowerInvariant();
        if (recommended is "google")
        {
            return "google";
        }

        if (recommended is "email" or "verified_email" or "awaiting_email_verification")
        {
            return "email";
        }

        if (links?.LinkedIdentities.Any(identity => string.Equals(identity.Provider, "google", StringComparison.OrdinalIgnoreCase)) == true)
        {
            return "google";
        }

        if (links?.LinkedIdentities.Any(identity => string.Equals(identity.Provider, "email", StringComparison.OrdinalIgnoreCase)) == true)
        {
            return "email";
        }

        return "unknown";
    }

    private async Task<ParticipationOperatorNotificationReceipt> DispatchAsync(
        HubUserDto user,
        string? email,
        string eventType,
        string eventKey,
        string intentKind,
        string entryRoute,
        string authProviderFamily,
        CancellationToken cancellationToken)
    {
        string normalizedAuthProvider = NormalizeAuthProviderFamily(authProviderFamily);
        string normalizedEntryRoute = NormalizeEntryRoute(entryRoute);
        string normalizedIntentKind = AccountService.NormalizeRequired(intentKind, nameof(intentKind)).Trim().ToLowerInvariant();
        string normalizedEmail = AccountService.NormalizeOptional(email) ?? AccountService.NormalizeOptional(user.Email) ?? string.Empty;
        DateTimeOffset now = DateTimeOffset.UtcNow;
        ParticipationOperatorNotificationReceipt pendingReceipt;

        lock (_store.Gate)
        {
            ParticipationOperatorNotificationReceipt? existing = _store.ParticipationNotificationReceipts
                .FirstOrDefault(receipt => string.Equals(receipt.EventKey, eventKey, StringComparison.OrdinalIgnoreCase));
            if (existing is not null)
            {
                if (!CanRetryExistingReceipt(existing))
                {
                    return existing;
                }

                pendingReceipt = existing with
                {
                    Status = "pending",
                    AttemptedAtUtc = now,
                    Summary = "The participant event is queued for the internal operator notification bridge.",
                    FailureReason = null,
                    Envelope = ReceiptEnvelopeFactory.Runtime(
                        receiptKind: "participation_operator_notification",
                        ownerScope: "community.participation",
                        exposureClass: ReceiptExposureClasses.Internal,
                        evidenceRef: existing.EventKey,
                        reviewState: "pending"),
                };

                int existingIndex = _store.ParticipationNotificationReceipts.FindIndex(item =>
                    string.Equals(item.ReceiptId, existing.ReceiptId, StringComparison.OrdinalIgnoreCase));
                if (existingIndex >= 0)
                {
                    _store.ParticipationNotificationReceipts[existingIndex] = pendingReceipt;
                    _store.PersistLocked();
                }

                goto DispatchPendingReceipt;
            }

            bool isFirstParticipationEvent = !_store.ParticipationNotificationReceipts.Any(receipt =>
                string.Equals(receipt.UserId, user.UserId, StringComparison.OrdinalIgnoreCase)
                && !string.Equals(receipt.Status, "duplicate", StringComparison.OrdinalIgnoreCase));
            string? rateLimitBucket = BuildRateLimitBucket(user.UserId, now);
            if (RateLimitExceededLocked(user.UserId, now))
            {
                var limitedReceipt = BuildReceipt(
                    user,
                    normalizedEmail,
                    eventType,
                    eventKey,
                    normalizedIntentKind,
                    normalizedEntryRoute,
                    normalizedAuthProvider,
                    status: "suppressed_rate_limited",
                    isFirstParticipationEvent,
                    occurredAtUtc: now,
                    attemptedAtUtc: now,
                    deliveryRef: null,
                    summary: "The participant event stayed local because the per-user operator notification cap was already reached.",
                    failureReason: "rate_limited",
                    rateLimitBucket);
                _store.ParticipationNotificationReceipts.Add(limitedReceipt);
                _store.PersistLocked();
                return limitedReceipt;
            }

            pendingReceipt = BuildReceipt(
                user,
                normalizedEmail,
                eventType,
                eventKey,
                normalizedIntentKind,
                normalizedEntryRoute,
                normalizedAuthProvider,
                status: "pending",
                isFirstParticipationEvent,
                occurredAtUtc: now,
                attemptedAtUtc: now,
                deliveryRef: null,
                summary: "The participant event is queued for the internal operator notification bridge.",
                failureReason: null,
                rateLimitBucket);
            _store.ParticipationNotificationReceipts.Add(pendingReceipt);
            _store.PersistLocked();
        }

DispatchPendingReceipt:
        try
        {
            if (!NotificationsEnabled())
            {
                return FinalizeReceipt(pendingReceipt, "suppressed_disabled", null, "Operator participation notifications are disabled on this runtime.", "notifications_disabled");
            }

            string notifyChannel = ResolveOperatorNotifyChannel();
            string recipient = ResolveOperatorRecipient(notifyChannel);
            if (string.IsNullOrWhiteSpace(recipient))
            {
                return FinalizeReceipt(pendingReceipt, "suppressed_recipient_missing", null, "No operator recipient is configured for participant notifications on this runtime.", "recipient_missing");
            }

            if (!EaDispatchConfigured(notifyChannel))
            {
                return FinalizeReceipt(pendingReceipt, "suppressed_adapter_unconfigured", null, "The EA dispatch adapter is not configured on this runtime, so the participant event stayed as a first-party receipt only.", "ea_dispatch_unconfigured");
            }

            if (!IsSupportedNotifyChannel(notifyChannel))
            {
                return FinalizeReceipt(
                    pendingReceipt,
                    "suppressed_adapter_unconfigured",
                    null,
                    $"Operator notification channel '{notifyChannel}' is not supported.",
                    "unsupported_notify_channel");
            }

            string deliveryRef = await SendToEaAsync(pendingReceipt, recipient, notifyChannel, cancellationToken);
            return FinalizeReceipt(pendingReceipt, "sent", deliveryRef, "The participant event was queued to the internal EA delivery bridge.", null);
        }
        catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException or InvalidOperationException or JsonException)
        {
            _logger.LogWarning(ex, "Participant operator notification dispatch failed for receipt {ReceiptId}.", pendingReceipt.ReceiptId);
            return FinalizeReceipt(
                pendingReceipt,
                "failed_delivery",
                null,
                "The participant event stayed in the first-party receipt ledger because the EA bridge call failed.",
                Truncate(ex.Message, 400));
        }
    }

    private ParticipationOperatorNotificationReceipt FinalizeReceipt(
        ParticipationOperatorNotificationReceipt receipt,
        string status,
        string? deliveryRef,
        string summary,
        string? failureReason)
    {
        ParticipationOperatorNotificationReceipt finalized = receipt with
        {
            Status = status,
            DeliveryRef = deliveryRef,
            Summary = summary,
            FailureReason = failureReason,
            AttemptedAtUtc = DateTimeOffset.UtcNow,
            Envelope = ReceiptEnvelopeFactory.Runtime(
                receiptKind: "participation_operator_notification",
                ownerScope: "community.participation",
                exposureClass: ReceiptExposureClasses.Internal,
                evidenceRef: receipt.EventKey,
                reviewState: status),
        };

        lock (_store.Gate)
        {
            int index = _store.ParticipationNotificationReceipts.FindIndex(item => string.Equals(item.ReceiptId, receipt.ReceiptId, StringComparison.OrdinalIgnoreCase));
            if (index >= 0)
            {
                _store.ParticipationNotificationReceipts[index] = finalized;
                _store.PersistLocked();
            }
        }

        return finalized;
    }

    private ParticipationOperatorNotificationReceipt BuildReceipt(
        HubUserDto user,
        string email,
        string eventType,
        string eventKey,
        string intentKind,
        string entryRoute,
        string authProviderFamily,
        string status,
        bool isFirstParticipationEvent,
        DateTimeOffset occurredAtUtc,
        DateTimeOffset attemptedAtUtc,
        string? deliveryRef,
        string? summary,
        string? failureReason,
        string? rateLimitBucket)
        => new(
            ReceiptId: $"{ReceiptPrefix}_{Guid.NewGuid():N}"[..21],
            EventType: eventType,
            EventKey: eventKey,
            UserId: user.UserId,
            SubjectHash: HashPrivate("subject", user.SubjectId),
            EmailMasked: MaskEmail(email),
            EmailHash: HashPrivate("email", email),
            DisplayName: AccountService.NormalizeOptional(user.DisplayName) ?? "Runner",
            IntentKind: intentKind,
            EntryRoute: entryRoute,
            AuthProviderFamily: authProviderFamily,
            Status: status,
            IsFirstParticipationEvent: isFirstParticipationEvent,
            OccurredAtUtc: occurredAtUtc,
            AttemptedAtUtc: attemptedAtUtc,
            DeliveryRef: deliveryRef,
            Summary: summary,
            FailureReason: failureReason,
            RateLimitBucket: rateLimitBucket,
            Envelope: ReceiptEnvelopeFactory.Runtime(
                receiptKind: "participation_operator_notification",
                ownerScope: "community.participation",
                exposureClass: ReceiptExposureClasses.Internal,
                evidenceRef: eventKey,
                reviewState: status));

    private async Task<string> SendToEaAsync(ParticipationOperatorNotificationReceipt receipt, string recipient, string notifyChannel, CancellationToken cancellationToken)
    {
        string principalId = (_configuration[EaPrincipalIdConfigKey] ?? string.Empty).Trim();
        string bindingId = ResolveEaBindingId(notifyChannel);
        string idempotencyKey = receipt.EventKey;
        var metadata = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase)
        {
            ["event_type"] = receipt.EventType,
            ["receipt_id"] = receipt.ReceiptId,
            ["intent_kind"] = receipt.IntentKind,
            ["entry_route"] = receipt.EntryRoute,
            ["auth_provider_family"] = receipt.AuthProviderFamily,
            ["user_id"] = receipt.UserId,
            ["subject_hash"] = receipt.SubjectHash,
            ["email_masked"] = receipt.EmailMasked,
            ["email_hash"] = receipt.EmailHash,
            ["is_first_participation_event"] = receipt.IsFirstParticipationEvent,
            ["occurred_at_utc"] = receipt.OccurredAtUtc.ToString("O"),
        };

        var payload = new
        {
            tool_name = ConnectorDispatchTool,
            action_kind = DeliverySendAction,
            payload_json = new
            {
                principal_id = principalId,
                binding_id = bindingId,
                channel = notifyChannel,
                recipient,
                subject = $"[Chummer] New participant account: {receipt.IntentKind}",
                content = BuildContent(receipt),
                metadata,
                notify_channel = notifyChannel,
                idempotency_key = idempotencyKey,
            }
        };

        using var request = new HttpRequestMessage(HttpMethod.Post, $"{ResolveEaBaseUrl()}/v1/tools/execute");
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", ResolveEaApiToken());
        request.Headers.Add("x-ea-principal-id", principalId);
        request.Headers.Add("Idempotency-Key", idempotencyKey);
        request.Content = JsonContent.Create(payload);

        using HttpResponseMessage response = await _httpClient.SendAsync(request, cancellationToken);
        string body = await response.Content.ReadAsStringAsync(cancellationToken);
        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"{(int)response.StatusCode}:{Truncate(body, 600)}");
        }

        if (string.IsNullOrWhiteSpace(body))
        {
            throw new InvalidOperationException("connector_dispatch_missing_delivery_id");
        }

        using JsonDocument document = JsonDocument.Parse(body);
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

    private bool NotificationsEnabled()
        => !string.Equals((_configuration[NotificationsEnabledConfigKey] ?? "true").Trim(), "false", StringComparison.OrdinalIgnoreCase);

    private static bool CanRetryExistingReceipt(ParticipationOperatorNotificationReceipt receipt)
        => receipt.Status is "failed_delivery"
            or "suppressed_recipient_missing"
            or "suppressed_adapter_unconfigured"
            or "suppressed_disabled";

    private bool EaDispatchConfigured(string notifyChannel)
        => !string.IsNullOrWhiteSpace(ResolveEaApiToken())
            && !string.IsNullOrWhiteSpace((_configuration[EaPrincipalIdConfigKey] ?? string.Empty).Trim())
            && !string.IsNullOrWhiteSpace(ResolveEaBindingId(notifyChannel));

    private string ResolveOperatorRecipient(string notifyChannel)
    {
        if (string.Equals(notifyChannel, WhatsappChannel, StringComparison.OrdinalIgnoreCase))
        {
            string? whatsappRecipient = ResolveWhatsappRecipient(
                AccountService.NormalizeOptional(_configuration[OperatorRecipientWhatsappConfigKey])
                    ?? AccountService.NormalizeOptional(_configuration[OperatorRecipientConfigKey]));
            return whatsappRecipient ?? string.Empty;
        }

        return AccountService.NormalizeOptional(_configuration[OperatorRecipientConfigKey]) ?? string.Empty;
    }

    private string ResolveOperatorNotifyChannel()
    {
        string requested = (AccountService.NormalizeOptional(_configuration[OperatorNotifyChannelConfigKey]) ?? EmailChannel).ToLowerInvariant();
        return requested switch
        {
            EmailChannel => EmailChannel,
            WhatsappChannel => WhatsappChannel,
            _ => requested
        };
    }

    private static bool IsSupportedNotifyChannel(string channel)
        => string.Equals(channel, EmailChannel, StringComparison.OrdinalIgnoreCase)
            || string.Equals(channel, WhatsappChannel, StringComparison.OrdinalIgnoreCase);

    private string ResolveEaBindingId(string notifyChannel)
    {
        if (string.Equals(notifyChannel, WhatsappChannel, StringComparison.OrdinalIgnoreCase))
        {
            return AccountService.NormalizeOptional(_configuration[EaWhatsappBindingIdConfigKey])
                ?? AccountService.NormalizeOptional(_configuration[EaBindingIdConfigKey])
                ?? string.Empty;
        }

        return AccountService.NormalizeOptional(_configuration[EaBindingIdConfigKey]) ?? string.Empty;
    }

    private string ResolveEaApiToken()
        => (_configuration[EaApiTokenConfigKey] ?? string.Empty).Trim();

    private string ResolveEaBaseUrl()
        => (_configuration[EaBaseUrlConfigKey] ?? DefaultEaBaseUrl).Trim().TrimEnd('/');

    private bool RateLimitExceededLocked(string userId, DateTimeOffset now)
        => _store.ParticipationNotificationReceipts.Count(receipt =>
            string.Equals(receipt.UserId, userId, StringComparison.OrdinalIgnoreCase)
            && receipt.OccurredAtUtc >= now.AddHours(-24)
            && receipt.Status is "pending" or "sent" or "suppressed_recipient_missing" or "suppressed_adapter_unconfigured" or "suppressed_disabled") >= 6;

    private static string BuildRateLimitBucket(string userId, DateTimeOffset now)
        => $"{userId}:{now:yyyyMMdd}";

    private static string NormalizeEntryRoute(string? route)
        => HubBrowserAuthService.SanitizeNextPath(route, "/home");

    private static string NormalizeAuthProviderFamily(string? provider)
        => (provider ?? string.Empty).Trim().ToLowerInvariant() switch
        {
            "email" => "email",
            "google" => "google",
            _ => "unknown"
        };

    private string HashPrivate(string scope, string? value)
    {
        string normalized = AccountService.NormalizeOptional(value) ?? string.Empty;
        string salt = (_configuration[HashSaltConfigKey] ?? "chummer-operator-participation").Trim();
        byte[] hash = SHA256.HashData(Encoding.UTF8.GetBytes($"{salt}|{scope}|{normalized.ToLowerInvariant()}"));
        return Convert.ToHexString(hash).ToLowerInvariant();
    }

    private static string MaskEmail(string? email)
    {
        string normalized = AccountService.NormalizeOptional(email) ?? string.Empty;
        int atIndex = normalized.IndexOf('@');
        if (atIndex <= 0 || atIndex == normalized.Length - 1)
        {
            return string.Empty;
        }

        string localPart = normalized[..atIndex];
        string domain = normalized[(atIndex + 1)..];
        return $"{localPart[0]}***@{domain}";
    }

    private static string BuildContent(ParticipationOperatorNotificationReceipt receipt)
        => string.Join(
            "\n",
            new[]
            {
                $"Event type: {receipt.EventType}",
                $"Occurred at UTC: {receipt.OccurredAtUtc:O}",
                $"Intent: {receipt.IntentKind}",
                $"Entry route: {receipt.EntryRoute}",
                $"Account id: {receipt.UserId}",
                $"Masked email: {receipt.EmailMasked}",
                $"Subject hash: {receipt.SubjectHash}",
                $"Auth provider family: {receipt.AuthProviderFamily}",
                $"Receipt id: {receipt.ReceiptId}",
            });

    private static string? ResolveWhatsappRecipient(string? recipient)
    {
        string? normalized = AccountService.NormalizeOptional(recipient);
        if (normalized is null)
        {
            return null;
        }

        string digits = new(normalized.Where(char.IsDigit).ToArray());
        if (digits.Length < 8 || digits.Length > 15)
        {
            return null;
        }

        return digits;
    }

    private static string Truncate(string? value, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return string.Empty;
        }

        string normalized = value.Trim();
        return normalized.Length <= maxLength ? normalized : normalized[..maxLength];
    }
}
