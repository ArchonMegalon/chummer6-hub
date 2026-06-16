using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Contracts.Receipts;
using Chummer.Run.Contracts.Billing;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class PayFunnelsBillingService
{
    private static readonly HashSet<string> SupportedEventTypes = new(StringComparer.OrdinalIgnoreCase)
    {
        "payment_succeeded",
        "payment_failed",
        "payment_refunded",
        "chargeback"
    };

    private readonly PayFunnelsBillingStore _store;
    private readonly IConfiguration _configuration;

    public PayFunnelsBillingService(PayFunnelsBillingStore store, IConfiguration configuration)
    {
        _store = store;
        _configuration = configuration;
    }

    public BillingProductDto Product { get; } = new(
        PayFunnelsTestBillingConstants.ProductId,
        PayFunnelsTestBillingConstants.ProductName,
        PayFunnelsTestBillingConstants.AmountCents,
        PayFunnelsTestBillingConstants.Currency,
        "one_time",
        "none",
        PayFunnelsTestBillingConstants.EntitlementEffect,
        0,
        false);

    public PayFunnelsTestBillingPageDto GetTestPage()
        => new(
            Product,
            PayFunnelsTestBillingConstants.RequiredCustomerCopy,
            PayFunnelsTestBillingConstants.AcknowledgementCopy,
            PayFunnelsTestBillingConstants.CheckoutButtonCopy,
            CanCreateIntentWithoutAcknowledgement: false,
            ForbiddenWordsAbsent: ["Premium", "Pro", "Subscribe", "Upgrade"]);

    public PaymentIntentDto CreateIntent(PaymentIntentCreateRequest request)
    {
        if (!request.BenefitAcknowledged)
        {
            throw new InvalidOperationException(PayFunnelsTestBillingConstants.AcknowledgementCopy);
        }

        if (string.IsNullOrWhiteSpace(request.UserId))
        {
            throw new InvalidOperationException("A user id is required before creating a PayFunnels test payment intent.");
        }

        lock (_store.Gate)
        {
            var intent = new PaymentIntentDto(
                IntentId: NewId("pf_intent"),
                UserId: request.UserId.Trim(),
                BillingProductId: PayFunnelsTestBillingConstants.ProductId,
                AmountCents: PayFunnelsTestBillingConstants.AmountCents,
                Currency: PayFunnelsTestBillingConstants.Currency,
                Status: "created",
                BenefitAcknowledged: true,
                CheckoutUrl: BuildCheckoutUrl(request.UserId.Trim()),
                CreatedAtUtc: DateTimeOffset.UtcNow);
            _store.Intents.Add(intent);
            _store.PersistLocked();
            return intent;
        }
    }

    public PayFunnelsWebhookResultDto ProcessWebhook(PayFunnelsWebhookRequest request, string? signature)
    {
        string canonicalPayload = CanonicalPayload(request);
        string payloadHash = $"sha256:{Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(canonicalPayload))).ToLowerInvariant()}";
        if (!VerifySignature(canonicalPayload, signature))
        {
            return RecordRejectedEvent(request, payloadHash, "failed", "signature verification failed");
        }

        if (!SupportedEventTypes.Contains(request.EventType))
        {
            return RecordRejectedEvent(request, payloadHash, "verified", "unsupported PayFunnels event type for the $1 test adapter");
        }

        if (!string.Equals(request.BillingProductId, PayFunnelsTestBillingConstants.ProductId, StringComparison.OrdinalIgnoreCase))
        {
            return RecordRejectedEvent(request, payloadHash, "verified", "wrong billing product");
        }

        if (request.AmountCents != PayFunnelsTestBillingConstants.AmountCents
            || !string.Equals(request.Currency, PayFunnelsTestBillingConstants.Currency, StringComparison.OrdinalIgnoreCase))
        {
            return RecordRejectedEvent(request, payloadHash, "verified", "wrong amount or currency");
        }

        lock (_store.Gate)
        {
            var existingEvent = _store.Events.FirstOrDefault(item => string.Equals(item.ProviderEventId, request.ProviderEventId, StringComparison.OrdinalIgnoreCase));
            if (existingEvent is not null)
            {
                var existingReceipt = _store.Receipts.FirstOrDefault(item => string.Equals(item.ProviderEventId, request.ProviderEventId, StringComparison.OrdinalIgnoreCase))
                    ?? _store.Receipts.FirstOrDefault(item => string.Equals(item.ProviderCheckoutId, request.ProviderCheckoutId, StringComparison.OrdinalIgnoreCase));
                return BuildResult(request, "verified", "duplicate_ignored", existingEvent.Status, existingReceipt?.ReceiptId, FindNoOpEntryId(request.UserId, existingReceipt?.BillingProductId), existingEvent.RejectionReason);
            }

            var intent = _store.Intents.FirstOrDefault(item =>
                string.Equals(item.IntentId, request.PaymentIntentId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.UserId, request.UserId, StringComparison.OrdinalIgnoreCase)
                && item.BenefitAcknowledged);
            if (intent is null)
            {
                return RecordRejectedEventLocked(request, payloadHash, "verified", "payment intent metadata did not match an acknowledged Chummer intent");
            }

            _store.Events.Add(new PaymentEventDto(
                EventId: NewId("pf_evt"),
                Provider: PayFunnelsTestBillingConstants.Provider,
                ProviderEventId: request.ProviderEventId,
                EventType: request.EventType,
                SignatureStatus: "verified",
                IdempotencyKey: request.ProviderEventId,
                RawPayloadHash: payloadHash,
                Status: "accepted",
                ProcessedAtUtc: DateTimeOffset.UtcNow,
                RejectionReason: null));

            PaymentReceiptDto? receipt = null;
            BillingEntitlementLedgerEntryDto? ledger = null;
            if (string.Equals(request.EventType, "payment_succeeded", StringComparison.OrdinalIgnoreCase))
            {
                receipt = new PaymentReceiptDto(
                    ReceiptId: NewId("pf_receipt"),
                    UserId: request.UserId,
                    Provider: PayFunnelsTestBillingConstants.Provider,
                    ProviderEventId: request.ProviderEventId,
                    ProviderCheckoutId: request.ProviderCheckoutId,
                    BillingProductId: request.BillingProductId,
                    AmountCents: request.AmountCents,
                    Currency: request.Currency,
                    Status: "paid",
                    EntitlementEffect: "none",
                    CreatedAtUtc: DateTimeOffset.UtcNow,
                    RefundedAtUtc: null,
                    Envelope: ReceiptEnvelopeFactory.ExternalWebhook(
                        receiptKind: "billing_payment",
                        ownerScope: "billing.account",
                        evidenceRef: request.ProviderEventId,
                        reviewState: "verified"));
                _store.Receipts.Add(receipt);

                ledger = new BillingEntitlementLedgerEntryDto(
                    EntryId: NewId("pf_noop"),
                    UserId: request.UserId,
                    Source: PayFunnelsTestBillingConstants.Provider,
                    BillingProductId: request.BillingProductId,
                    EffectType: PayFunnelsTestBillingConstants.EntitlementEffect,
                    PremiumEnabledDelta: false,
                    RenderUnitsDelta: 0,
                    FeatureFlagsAdded: [],
                    Reason: "$1 billing plumbing test; no current benefit",
                    CreatedAtUtc: DateTimeOffset.UtcNow);
                _store.EntitlementLedger.Add(ledger);
            }
            else if (string.Equals(request.EventType, "payment_refunded", StringComparison.OrdinalIgnoreCase))
            {
                var original = _store.Receipts.LastOrDefault(item =>
                    string.Equals(item.UserId, request.UserId, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.ProviderCheckoutId, request.ProviderCheckoutId, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(item.Status, "paid", StringComparison.OrdinalIgnoreCase));
                if (original is not null)
                {
                    var updated = original with
                    {
                        Status = "refunded",
                        RefundedAtUtc = DateTimeOffset.UtcNow,
                        Envelope = (original.Envelope ?? ReceiptEnvelopeFactory.ExternalWebhook(
                            receiptKind: "billing_payment",
                            ownerScope: "billing.account",
                            evidenceRef: request.ProviderEventId,
                            reviewState: "verified")) with
                        {
                            LifecycleState = ReceiptLifecycleStates.Archived
                        }
                    };
                    _store.Receipts[_store.Receipts.IndexOf(original)] = updated;
                    receipt = updated;
                }
            }

            _store.PersistLocked();
            return BuildResult(request, "verified", "first_seen", "accepted", receipt?.ReceiptId, ledger?.EntryId ?? FindNoOpEntryId(request.UserId, request.BillingProductId), null);
        }
    }

    public BillingAccountSummaryDto GetAccountSummary(string userId)
    {
        lock (_store.Gate)
        {
            return new BillingAccountSummaryDto(
                userId,
                PremiumEnabled: false,
                RenderUnits: 0,
                Receipts: _store.Receipts
                    .Where(item => string.Equals(item.UserId, userId, StringComparison.OrdinalIgnoreCase))
                    .OrderByDescending(item => item.CreatedAtUtc)
                    .ToArray(),
                EntitlementLedger: _store.EntitlementLedger
                    .Where(item => string.Equals(item.UserId, userId, StringComparison.OrdinalIgnoreCase))
                    .OrderByDescending(item => item.CreatedAtUtc)
                    .ToArray());
        }
    }

    public IReadOnlyList<PaymentReceiptDto> ListReceipts()
    {
        lock (_store.Gate)
        {
            return _store.Receipts.OrderByDescending(item => item.CreatedAtUtc).ToArray();
        }
    }

    public static string CanonicalPayload(PayFunnelsWebhookRequest request)
        => JsonSerializer.Serialize(request, new JsonSerializerOptions(JsonSerializerDefaults.Web));

    public string ComputeSignature(PayFunnelsWebhookRequest request)
    {
        var secret = GetWebhookSecret();
        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(secret));
        return $"sha256={Convert.ToHexString(hmac.ComputeHash(Encoding.UTF8.GetBytes(CanonicalPayload(request)))).ToLowerInvariant()}";
    }

    private PayFunnelsWebhookResultDto RecordRejectedEvent(PayFunnelsWebhookRequest request, string payloadHash, string signatureStatus, string reason)
    {
        lock (_store.Gate)
        {
            return RecordRejectedEventLocked(request, payloadHash, signatureStatus, reason);
        }
    }

    private PayFunnelsWebhookResultDto RecordRejectedEventLocked(PayFunnelsWebhookRequest request, string payloadHash, string signatureStatus, string reason)
    {
        if (_store.Events.All(item => !string.Equals(item.ProviderEventId, request.ProviderEventId, StringComparison.OrdinalIgnoreCase)))
        {
            _store.Events.Add(new PaymentEventDto(
                EventId: NewId("pf_evt"),
                Provider: PayFunnelsTestBillingConstants.Provider,
                ProviderEventId: request.ProviderEventId,
                EventType: request.EventType,
                SignatureStatus: signatureStatus,
                IdempotencyKey: request.ProviderEventId,
                RawPayloadHash: payloadHash,
                Status: "rejected",
                ProcessedAtUtc: DateTimeOffset.UtcNow,
                RejectionReason: reason));
            _store.PersistLocked();
        }

        return BuildResult(request, signatureStatus, "first_seen", "rejected", null, null, reason);
    }

    private PayFunnelsWebhookResultDto BuildResult(
        PayFunnelsWebhookRequest request,
        string signatureStatus,
        string idempotencyStatus,
        string status,
        string? receiptId,
        string? ledgerId,
        string? rejectionReason)
        => new(
            ProviderEventId: request.ProviderEventId,
            EventType: request.EventType,
            SignatureStatus: signatureStatus,
            IdempotencyStatus: idempotencyStatus,
            Status: status,
            ReceiptId: receiptId,
            EntitlementLedgerEntryId: ledgerId,
            EntitlementEffect: PayFunnelsTestBillingConstants.EntitlementEffect,
            ReceiptCount: _store.Receipts.Count,
            EntitlementLedgerCount: _store.EntitlementLedger.Count,
            PremiumEnabledDelta: false,
            RenderUnitsDelta: 0,
            RejectionReason: rejectionReason);

    private string? FindNoOpEntryId(string userId, string? billingProductId)
        => _store.EntitlementLedger.LastOrDefault(item =>
            string.Equals(item.UserId, userId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.BillingProductId, billingProductId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(item.EffectType, PayFunnelsTestBillingConstants.EntitlementEffect, StringComparison.OrdinalIgnoreCase))?.EntryId;

    private bool VerifySignature(string canonicalPayload, string? signature)
    {
        if (string.IsNullOrWhiteSpace(signature))
        {
            return false;
        }

        var secret = GetWebhookSecret();
        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(secret));
        var expected = $"sha256={Convert.ToHexString(hmac.ComputeHash(Encoding.UTF8.GetBytes(canonicalPayload))).ToLowerInvariant()}";
        return CryptographicOperations.FixedTimeEquals(Encoding.UTF8.GetBytes(expected), Encoding.UTF8.GetBytes(signature.Trim()));
    }

    private string GetWebhookSecret()
        => _configuration["PAYFUNNELS_WEBHOOK_SECRET"]
            ?? _configuration["PayFunnels:WebhookSecret"]
            ?? throw new InvalidOperationException("PAYFUNNELS_WEBHOOK_SECRET must be configured; webhook secrets are not committed.");

    private string BuildCheckoutUrl(string userId)
    {
        var baseUrl = _configuration["PAYFUNNELS_TEST_CHECKOUT_URL"] ?? _configuration["PayFunnels:TestCheckoutUrl"] ?? "https://checkout.payfunnels.example/test";
        return $"{baseUrl}?product={Uri.EscapeDataString(PayFunnelsTestBillingConstants.ProductId)}&amount=100&currency=USD&user={Uri.EscapeDataString(userId)}&no_benefit=true";
    }

    private static string NewId(string prefix) => $"{prefix}_{Guid.NewGuid():N}";
}
