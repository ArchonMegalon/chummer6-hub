using System.ComponentModel.DataAnnotations;
using Chummer.Contracts.Receipts;

namespace Chummer.Run.Contracts.Billing;

public static class PayFunnelsTestBillingConstants
{
    public const string Provider = "PayFunnels";
    public const string ProductId = "payfunnels_test_payment_1usd_v1";
    public const string ProductName = "$1 Billing Test";
    public const int AmountCents = 100;
    public const string Currency = "USD";
    public const string EntitlementEffect = "no_op";
    public const string RequiredCustomerCopy =
        "This is a $1 test payment.\nIt currently unlocks no benefits, no premium features, no render credits, and no special access.\nIt only helps us test payment processing.";
    public const string AcknowledgementCopy = "I understand this is a $1 test payment and currently provides no benefits.";
    public const string CheckoutButtonCopy = "Pay $1 test payment";
}

public sealed record BillingProductDto(
    string ProductId,
    string Name,
    int AmountCents,
    string Currency,
    string Type,
    string Benefit,
    string EntitlementEffect,
    int RenderUnitsAdded,
    bool PremiumEnabled);

public sealed record PayFunnelsTestBillingPageDto(
    BillingProductDto Product,
    string RequiredCopy,
    string AcknowledgementCopy,
    string CheckoutButtonCopy,
    bool CanCreateIntentWithoutAcknowledgement,
    IReadOnlyList<string> ForbiddenWordsAbsent);

public sealed record PaymentIntentCreateRequest(
    [Required(AllowEmptyStrings = false)] string UserId,
    bool BenefitAcknowledged);

public sealed record PaymentIntentDto(
    string IntentId,
    string UserId,
    string BillingProductId,
    int AmountCents,
    string Currency,
    string Status,
    bool BenefitAcknowledged,
    string CheckoutUrl,
    DateTimeOffset CreatedAtUtc);

public sealed record PayFunnelsWebhookRequest(
    [Required(AllowEmptyStrings = false)] string ProviderEventId,
    [Required(AllowEmptyStrings = false)] string EventType,
    [Required(AllowEmptyStrings = false)] string PaymentIntentId,
    [Required(AllowEmptyStrings = false)] string UserId,
    [Required(AllowEmptyStrings = false)] string ProviderCheckoutId,
    [Required(AllowEmptyStrings = false)] string BillingProductId,
    int AmountCents,
    [Required(AllowEmptyStrings = false)] string Currency,
    DateTimeOffset OccurredAtUtc);

public sealed record PayFunnelsWebhookResultDto(
    string ProviderEventId,
    string EventType,
    string SignatureStatus,
    string IdempotencyStatus,
    string Status,
    string? ReceiptId,
    string? EntitlementLedgerEntryId,
    string EntitlementEffect,
    int ReceiptCount,
    int EntitlementLedgerCount,
    bool PremiumEnabledDelta,
    int RenderUnitsDelta,
    string? RejectionReason);

public sealed record PaymentEventDto(
    string EventId,
    string Provider,
    string ProviderEventId,
    string EventType,
    string SignatureStatus,
    string IdempotencyKey,
    string RawPayloadHash,
    string Status,
    DateTimeOffset ProcessedAtUtc,
    string? RejectionReason);

public sealed record PaymentReceiptDto(
    string ReceiptId,
    string UserId,
    string Provider,
    string ProviderEventId,
    string ProviderCheckoutId,
    string BillingProductId,
    int AmountCents,
    string Currency,
    string Status,
    string EntitlementEffect,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset? RefundedAtUtc,
    ReceiptEnvelope? Envelope = null);

public sealed record BillingEntitlementLedgerEntryDto(
    string EntryId,
    string UserId,
    string Source,
    string BillingProductId,
    string EffectType,
    bool PremiumEnabledDelta,
    int RenderUnitsDelta,
    IReadOnlyList<string> FeatureFlagsAdded,
    string Reason,
    DateTimeOffset CreatedAtUtc);

public sealed record BillingAccountSummaryDto(
    string UserId,
    bool PremiumEnabled,
    int RenderUnits,
    IReadOnlyList<PaymentReceiptDto> Receipts,
    IReadOnlyList<BillingEntitlementLedgerEntryDto> EntitlementLedger);
