using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Billing;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class PayFunnelsBillingTests
{
    [Fact]
    public void TestPageRequiresNoBenefitAcknowledgementAndHonestCopy()
    {
        PayFunnelsBillingService service = CreateService();

        PayFunnelsTestBillingPageDto page = service.GetTestPage();

        Assert.Equal("$1 Billing Test", page.Product.Name);
        Assert.Equal(100, page.Product.AmountCents);
        Assert.Equal("one_time", page.Product.Type);
        Assert.Equal("none", page.Product.Benefit);
        Assert.Equal("no_op", page.Product.EntitlementEffect);
        Assert.Equal(0, page.Product.RenderUnitsAdded);
        Assert.False(page.Product.PremiumEnabled);
        Assert.False(page.CanCreateIntentWithoutAcknowledgement);
        Assert.Equal("Pay $1 test payment", page.CheckoutButtonCopy);
        Assert.Contains("unlocks no benefits", page.RequiredCopy, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("no premium features", page.RequiredCopy, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("no render credits", page.RequiredCopy, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("no special access", page.RequiredCopy, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Subscribe", page.CheckoutButtonCopy, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Upgrade", page.CheckoutButtonCopy, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Pro", page.CheckoutButtonCopy, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void CannotCreateCheckoutIntentWithoutAcknowledgement()
    {
        PayFunnelsBillingService service = CreateService();

        InvalidOperationException ex = Assert.Throws<InvalidOperationException>(() =>
            service.CreateIntent(new PaymentIntentCreateRequest("user-a", BenefitAcknowledged: false)));

        Assert.Contains("$1 test payment", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void SuccessfulWebhookCreatesOneReceiptAndNoOpEntitlementOnly()
    {
        PayFunnelsBillingService service = CreateService();
        PaymentIntentDto intent = service.CreateIntent(new PaymentIntentCreateRequest("user-a", true));
        PayFunnelsWebhookRequest webhook = SuccessWebhook(intent);

        PayFunnelsWebhookResultDto result = service.ProcessWebhook(webhook, service.ComputeSignature(webhook));
        BillingAccountSummaryDto account = service.GetAccountSummary("user-a");

        Assert.Equal("accepted", result.Status);
        Assert.Equal("verified", result.SignatureStatus);
        Assert.Equal("first_seen", result.IdempotencyStatus);
        PaymentReceiptDto receipt = Assert.Single(account.Receipts);
        Assert.Equal("paid", receipt.Status);
        Assert.Equal("none", receipt.EntitlementEffect);
        BillingEntitlementLedgerEntryDto ledger = Assert.Single(account.EntitlementLedger);
        Assert.Equal("no_op", ledger.EffectType);
        Assert.False(ledger.PremiumEnabledDelta);
        Assert.Equal(0, ledger.RenderUnitsDelta);
        Assert.Empty(ledger.FeatureFlagsAdded);
        Assert.False(account.PremiumEnabled);
        Assert.Equal(0, account.RenderUnits);
    }

    [Fact]
    public void DuplicateWebhookCreatesNoDuplicateReceiptOrLedgerEntry()
    {
        PayFunnelsBillingService service = CreateService();
        PaymentIntentDto intent = service.CreateIntent(new PaymentIntentCreateRequest("user-a", true));
        PayFunnelsWebhookRequest webhook = SuccessWebhook(intent);
        string signature = service.ComputeSignature(webhook);

        PayFunnelsWebhookResultDto first = service.ProcessWebhook(webhook, signature);
        PayFunnelsWebhookResultDto duplicate = service.ProcessWebhook(webhook, signature);
        BillingAccountSummaryDto account = service.GetAccountSummary("user-a");

        Assert.Equal("first_seen", first.IdempotencyStatus);
        Assert.Equal("duplicate_ignored", duplicate.IdempotencyStatus);
        Assert.Single(account.Receipts);
        Assert.Single(account.EntitlementLedger);
    }

    [Fact]
    public void WrongAmountWrongProductAndBadSignatureAreRejected()
    {
        PayFunnelsBillingService service = CreateService();
        PaymentIntentDto intent = service.CreateIntent(new PaymentIntentCreateRequest("user-a", true));
        PayFunnelsWebhookRequest webhook = SuccessWebhook(intent);

        PayFunnelsWebhookRequest wrongAmount = webhook with { ProviderEventId = "pf_evt_wrong_amount", AmountCents = 200 };
        PayFunnelsWebhookRequest wrongProduct = webhook with { ProviderEventId = "pf_evt_wrong_product", BillingProductId = "premium" };

        PayFunnelsWebhookResultDto badSignature = service.ProcessWebhook(webhook with { ProviderEventId = "pf_evt_bad_sig" }, "sha256=bad");
        PayFunnelsWebhookResultDto amount = service.ProcessWebhook(wrongAmount, service.ComputeSignature(wrongAmount));
        PayFunnelsWebhookResultDto product = service.ProcessWebhook(wrongProduct, service.ComputeSignature(wrongProduct));

        Assert.Equal("rejected", badSignature.Status);
        Assert.Equal("failed", badSignature.SignatureStatus);
        Assert.Equal("rejected", amount.Status);
        Assert.Contains("amount", amount.RejectionReason, StringComparison.OrdinalIgnoreCase);
        Assert.Equal("rejected", product.Status);
        Assert.Contains("product", product.RejectionReason, StringComparison.OrdinalIgnoreCase);
        Assert.Empty(service.GetAccountSummary("user-a").Receipts);
        Assert.Empty(service.GetAccountSummary("user-a").EntitlementLedger);
    }

    [Fact]
    public void RefundUpdatesReceiptButRemovesNoFeatureBecauseNoneWasGranted()
    {
        PayFunnelsBillingService service = CreateService();
        PaymentIntentDto intent = service.CreateIntent(new PaymentIntentCreateRequest("user-a", true));
        PayFunnelsWebhookRequest succeeded = SuccessWebhook(intent);
        service.ProcessWebhook(succeeded, service.ComputeSignature(succeeded));
        PayFunnelsWebhookRequest refund = succeeded with
        {
            ProviderEventId = "pf_evt_refund_1",
            EventType = "payment_refunded"
        };

        PayFunnelsWebhookResultDto result = service.ProcessWebhook(refund, service.ComputeSignature(refund));
        BillingAccountSummaryDto account = service.GetAccountSummary("user-a");

        Assert.Equal("accepted", result.Status);
        PaymentReceiptDto receipt = Assert.Single(account.Receipts);
        Assert.Equal("refunded", receipt.Status);
        Assert.NotNull(receipt.RefundedAtUtc);
        BillingEntitlementLedgerEntryDto ledger = Assert.Single(account.EntitlementLedger);
        Assert.Equal("no_op", ledger.EffectType);
        Assert.False(account.PremiumEnabled);
        Assert.Equal(0, account.RenderUnits);
    }

    private static PayFunnelsWebhookRequest SuccessWebhook(PaymentIntentDto intent)
        => new(
            ProviderEventId: "pf_evt_success_1",
            EventType: "payment_succeeded",
            PaymentIntentId: intent.IntentId,
            UserId: intent.UserId,
            ProviderCheckoutId: "pf_checkout_1",
            BillingProductId: PayFunnelsTestBillingConstants.ProductId,
            AmountCents: PayFunnelsTestBillingConstants.AmountCents,
            Currency: PayFunnelsTestBillingConstants.Currency,
            OccurredAtUtc: DateTimeOffset.UtcNow);

    private static PayFunnelsBillingService CreateService()
    {
        string root = Path.Combine(Path.GetTempPath(), "chummer-payfunnels-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PAYFUNNELS_BILLING_STORE_PATH"] = Path.Combine(root, "payfunnels.json"),
                ["PAYFUNNELS_WEBHOOK_SECRET"] = "unit-test-secret-not-committed",
                ["PAYFUNNELS_TEST_CHECKOUT_URL"] = "https://payfunnels.test/checkout"
            })
            .Build();
        PayFunnelsBillingStore store = new(configuration);
        return new PayFunnelsBillingService(store, configuration);
    }
}
