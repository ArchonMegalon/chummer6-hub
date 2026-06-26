using System.Text;
using System.Text.Json;
using Chummer.Contracts.Receipts;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Billing;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class PayFunnelsBillingTests
{
    [Fact]
    public void TestPageRequiresNoBenefitAcknowledgementAndHonestCopy()
    {
        using Fixture fixture = new();

        PayFunnelsTestBillingPageDto page = fixture.Service.GetTestPage();

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
        using Fixture fixture = new();

        InvalidOperationException ex = Assert.Throws<InvalidOperationException>(() =>
            fixture.Service.CreateIntent(new PaymentIntentCreateRequest("user-a", BenefitAcknowledged: false)));

        Assert.Contains("$1 test payment", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void SuccessfulWebhookCreatesOneReceiptAndNoOpEntitlementOnly()
    {
        using Fixture fixture = new();
        PaymentIntentDto intent = fixture.Service.CreateIntent(new PaymentIntentCreateRequest("user-a", true));
        PayFunnelsWebhookRequest webhook = SuccessWebhook(intent);

        PayFunnelsWebhookResultDto result = fixture.Service.ProcessWebhook(webhook, fixture.Service.ComputeSignature(webhook));
        BillingAccountSummaryDto account = fixture.Service.GetAccountSummary("user-a");

        Assert.Equal("accepted", result.Status);
        Assert.Equal("verified", result.SignatureStatus);
        Assert.Equal("first_seen", result.IdempotencyStatus);
        PaymentReceiptDto receipt = Assert.Single(account.Receipts);
        Assert.Equal("paid", receipt.Status);
        Assert.Equal("none", receipt.EntitlementEffect);
        Assert.NotNull(receipt.Envelope);
        Assert.Equal(ReceiptProvenanceClasses.ExternalWebhook, receipt.Envelope!.ProvenanceClass);
        Assert.Equal(ReceiptLifecycleStates.Verified, receipt.Envelope.LifecycleState);
        Assert.Equal("billing.account", receipt.Envelope.OwnerScope);
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
        using Fixture fixture = new();
        PaymentIntentDto intent = fixture.Service.CreateIntent(new PaymentIntentCreateRequest("user-a", true));
        PayFunnelsWebhookRequest webhook = SuccessWebhook(intent);
        string signature = fixture.Service.ComputeSignature(webhook);

        PayFunnelsWebhookResultDto first = fixture.Service.ProcessWebhook(webhook, signature);
        PayFunnelsWebhookResultDto duplicate = fixture.Service.ProcessWebhook(webhook, signature);
        BillingAccountSummaryDto account = fixture.Service.GetAccountSummary("user-a");

        Assert.Equal("first_seen", first.IdempotencyStatus);
        Assert.Equal("duplicate_ignored", duplicate.IdempotencyStatus);
        Assert.Single(account.Receipts);
        Assert.Single(account.EntitlementLedger);
    }

    [Fact]
    public void WrongAmountWrongProductAndBadSignatureAreRejected()
    {
        using Fixture fixture = new();
        PaymentIntentDto intent = fixture.Service.CreateIntent(new PaymentIntentCreateRequest("user-a", true));
        PayFunnelsWebhookRequest webhook = SuccessWebhook(intent);

        PayFunnelsWebhookRequest wrongAmount = webhook with { ProviderEventId = "pf_evt_wrong_amount", AmountCents = 200 };
        PayFunnelsWebhookRequest wrongProduct = webhook with { ProviderEventId = "pf_evt_wrong_product", BillingProductId = "premium" };

        PayFunnelsWebhookResultDto badSignature = fixture.Service.ProcessWebhook(webhook with { ProviderEventId = "pf_evt_bad_sig" }, "sha256=bad");
        PayFunnelsWebhookResultDto amount = fixture.Service.ProcessWebhook(wrongAmount, fixture.Service.ComputeSignature(wrongAmount));
        PayFunnelsWebhookResultDto product = fixture.Service.ProcessWebhook(wrongProduct, fixture.Service.ComputeSignature(wrongProduct));

        Assert.Equal("rejected", badSignature.Status);
        Assert.Equal("failed", badSignature.SignatureStatus);
        Assert.Equal("rejected", amount.Status);
        Assert.Contains("amount", amount.RejectionReason, StringComparison.OrdinalIgnoreCase);
        Assert.Equal("rejected", product.Status);
        Assert.Contains("product", product.RejectionReason, StringComparison.OrdinalIgnoreCase);
        Assert.Empty(fixture.Service.GetAccountSummary("user-a").Receipts);
        Assert.Empty(fixture.Service.GetAccountSummary("user-a").EntitlementLedger);
    }

    [Fact]
    public void WebhookRejectsBlankProviderEventId()
    {
        using Fixture fixture = new();
        PaymentIntentDto intent = fixture.Service.CreateIntent(new PaymentIntentCreateRequest("user-a", true));
        PayFunnelsWebhookRequest webhook = SuccessWebhook(intent) with { ProviderEventId = "   " };

        PayFunnelsWebhookResultDto result = fixture.Service.ProcessWebhook(webhook, fixture.Service.ComputeSignature(webhook));

        Assert.Equal("rejected", result.Status);
        Assert.Contains("provider event id is required", result.RejectionReason, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RefundUpdatesReceiptButRemovesNoFeatureBecauseNoneWasGranted()
    {
        using Fixture fixture = new();
        PaymentIntentDto intent = fixture.Service.CreateIntent(new PaymentIntentCreateRequest("user-a", true));
        PayFunnelsWebhookRequest succeeded = SuccessWebhook(intent);
        fixture.Service.ProcessWebhook(succeeded, fixture.Service.ComputeSignature(succeeded));
        PayFunnelsWebhookRequest refund = succeeded with
        {
            ProviderEventId = "pf_evt_refund_1",
            EventType = "payment_refunded"
        };

        PayFunnelsWebhookResultDto result = fixture.Service.ProcessWebhook(refund, fixture.Service.ComputeSignature(refund));
        BillingAccountSummaryDto account = fixture.Service.GetAccountSummary("user-a");

        Assert.Equal("accepted", result.Status);
        PaymentReceiptDto receipt = Assert.Single(account.Receipts);
        Assert.Equal("refunded", receipt.Status);
        Assert.NotNull(receipt.RefundedAtUtc);
        Assert.NotNull(receipt.Envelope);
        Assert.Equal(ReceiptLifecycleStates.Archived, receipt.Envelope!.LifecycleState);
        BillingEntitlementLedgerEntryDto ledger = Assert.Single(account.EntitlementLedger);
        Assert.Equal("no_op", ledger.EffectType);
        Assert.False(account.PremiumEnabled);
        Assert.Equal(0, account.RenderUnits);
    }

    [Fact]
    public async Task ControllerAcceptsValidSignatureOverRawPayload()
    {
        using Fixture fixture = new();
        PaymentIntentDto intent = fixture.Service.CreateIntent(new PaymentIntentCreateRequest("user-a", true));
        PayFunnelsWebhookRequest webhook = SuccessWebhook(intent);
        string rawPayload = WebhookRawJson(webhook, includeIgnoredProperty: true);
        string signature = fixture.Service.ComputeSignature(rawPayload);
        var controller = new PayFunnelsBillingController(fixture.Service)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(rawPayload));
        controller.Request.Headers["X-PayFunnels-Signature"] = signature;

        ActionResult<PayFunnelsWebhookResultDto> result = await controller.Webhook(CancellationToken.None);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result.Result);
        PayFunnelsWebhookResultDto payload = Assert.IsType<PayFunnelsWebhookResultDto>(ok.Value);
        Assert.Equal("accepted", payload.Status);
    }

    [Fact]
    public async Task ControllerReturnsServiceUnavailableWhenWebhookSecretMissing()
    {
        using Fixture fixture = new(configureSecret: false);
        PaymentIntentDto intent = fixture.Service.CreateIntent(new PaymentIntentCreateRequest("user-a", true));
        PayFunnelsWebhookRequest webhook = SuccessWebhook(intent);
        string rawPayload = WebhookRawJson(webhook);
        var controller = new PayFunnelsBillingController(fixture.Service)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(rawPayload));
        controller.Request.Headers["X-PayFunnels-Signature"] = "sha256=bad";

        ActionResult<PayFunnelsWebhookResultDto> result = await controller.Webhook(CancellationToken.None);

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, problem.StatusCode);
    }

    [Fact]
    public void CorruptBillingStoreIsQuarantinedAndDoesNotBlockProcessing()
    {
        using Fixture fixture = new(seedCorruptStore: true);
        PaymentIntentDto intent = fixture.Service.CreateIntent(new PaymentIntentCreateRequest("user-a", true));
        PayFunnelsWebhookRequest webhook = SuccessWebhook(intent);

        PayFunnelsWebhookResultDto result = fixture.Service.ProcessWebhook(webhook, fixture.Service.ComputeSignature(webhook));

        Assert.Equal("accepted", result.Status);
        Assert.True(File.Exists(fixture.StorePath));
        Assert.Single(Directory.GetFiles(fixture.RootPath, "payfunnels.json.corrupt-*"));
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

    private static string WebhookRawJson(PayFunnelsWebhookRequest webhook, bool includeIgnoredProperty = false)
    {
        string json = JsonSerializer.Serialize(webhook, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        if (!includeIgnoredProperty)
        {
            return json;
        }

        return json.Insert(json.Length - 1, ",\"ignored\":\"signed-but-not-bound\"");
    }

    private sealed class Fixture : IDisposable
    {
        public Fixture(bool configureSecret = true, bool seedCorruptStore = false)
        {
            RootPath = Path.Combine(Path.GetTempPath(), "chummer-payfunnels-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(RootPath);
            StorePath = Path.Combine(RootPath, "payfunnels.json");
            if (seedCorruptStore)
            {
                File.WriteAllText(StorePath, "{ definitely-not-json", Encoding.UTF8);
            }

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PAYFUNNELS_BILLING_STORE_PATH"] = StorePath,
                    ["PAYFUNNELS_WEBHOOK_SECRET"] = configureSecret ? "unit-test-secret-not-committed" : null,
                    ["PAYFUNNELS_TEST_CHECKOUT_URL"] = "https://payfunnels.test/checkout"
                })
                .Build();
            Store = new PayFunnelsBillingStore(configuration);
            Service = new PayFunnelsBillingService(Store, configuration);
        }

        public string RootPath { get; }
        public string StorePath { get; }
        public PayFunnelsBillingStore Store { get; }
        public PayFunnelsBillingService Service { get; }

        public void Dispose()
        {
            if (Directory.Exists(RootPath))
            {
                Directory.Delete(RootPath, recursive: true);
            }
        }
    }
}
