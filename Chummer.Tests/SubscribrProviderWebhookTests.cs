using System.Text.Json;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class SubscribrProviderWebhookTests
{
    [Fact]
    public void WebhookRejectsBadSignatureWithoutMaterializingReceipt()
    {
        using Fixture fixture = new();
        SubscribrWebhookRequest request = fixture.ValidRequest();

        SubscribrWebhookResult result = fixture.Service.ProcessWebhook(
            request,
            signature: "sha256=bad",
            timestamp: Fixture.Timestamp,
            now: Fixture.Now);

        Assert.Equal("rejected", result.Status);
        Assert.Equal("failed", result.SignatureStatus);
        Assert.Null(result.ReceiptPath);
        Assert.Empty(Directory.GetFiles(fixture.ReceiptRoot));
    }

    [Fact]
    public void WebhookRejectsStaleTimestamp()
    {
        using Fixture fixture = new();
        SubscribrWebhookRequest request = fixture.ValidRequest();
        string staleTimestamp = Fixture.Now.AddHours(-1).ToString("O");

        SubscribrWebhookResult result = fixture.Service.ProcessWebhook(
            request,
            signature: fixture.Service.ComputeSignature(request, staleTimestamp),
            timestamp: staleTimestamp,
            now: Fixture.Now);

        Assert.Equal("rejected", result.Status);
        Assert.Equal("verified", result.SignatureStatus);
        Assert.Contains("timestamp", result.RejectionReason, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void WebhookMaterializesReviewRequiredReceiptAndRejectsReplay()
    {
        using Fixture fixture = new();
        SubscribrWebhookRequest request = fixture.ValidRequest();
        string signature = fixture.Service.ComputeSignature(request, Fixture.Timestamp);

        SubscribrWebhookResult first = fixture.Service.ProcessWebhook(request, signature, Fixture.Timestamp, Fixture.Now);
        SubscribrWebhookResult duplicate = fixture.Service.ProcessWebhook(request, signature, Fixture.Timestamp, Fixture.Now);

        Assert.Equal("accepted", first.Status);
        Assert.Equal("first_seen", first.ReplayStatus);
        Assert.Equal("review_required", first.ValidationStatus);
        Assert.NotNull(first.ReceiptPath);
        Assert.True(File.Exists(first.ReceiptPath));
        JsonDocument receipt = JsonDocument.Parse(File.ReadAllText(first.ReceiptPath!));
        Assert.Equal("chummer.subscribr_script_receipt.v1", receipt.RootElement.GetProperty("contract_name").GetString());
        Assert.Equal("review_required", receipt.RootElement.GetProperty("status").GetString());

        Assert.Equal("accepted", duplicate.Status);
        Assert.Equal("duplicate_ignored", duplicate.ReplayStatus);
        Assert.Equal(first.ReceiptPath, duplicate.ReceiptPath);
        Assert.Single(Directory.GetFiles(fixture.ReceiptRoot));
    }

    [Fact]
    public void ControllerUsesInternalRouteAndReturnsProblemWhenSecretMissing()
    {
        using Fixture fixture = new(configureSecret: false);
        var controller = new SubscribrProviderWebhookController(fixture.Service)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.Request.Headers["X-Subscribr-Signature"] = "sha256=bad";
        controller.Request.Headers["X-Subscribr-Timestamp"] = Fixture.Timestamp;

        ActionResult<SubscribrWebhookResult> result = controller.Webhook(fixture.ValidRequest());

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, problem.StatusCode);
    }

    [Fact]
    public void WebhookLaneReturnsServiceUnavailableWhenDisabled()
    {
        using Fixture fixture = new(configureLaneEnabled: false);

        InvalidOperationException exception = Assert.Throws<InvalidOperationException>(() =>
            fixture.Service.ProcessWebhook(
                fixture.ValidRequest(),
                fixture.Service.ComputeSignature(fixture.ValidRequest(), Fixture.Timestamp),
                Fixture.Timestamp,
                Fixture.Now));

        Assert.Contains("disabled", exception.Message, StringComparison.OrdinalIgnoreCase);
    }

    private sealed class Fixture : IDisposable
    {
        public static readonly DateTimeOffset Now = new(2026, 6, 26, 12, 0, 0, TimeSpan.Zero);
        public const string Timestamp = "2026-06-26T12:00:00Z";

        private readonly string _root;

        public Fixture(bool configureSecret = true, bool configureLaneEnabled = true)
        {
            _root = Path.Combine(Path.GetTempPath(), "chummer-subscribr-webhook-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            ReceiptRoot = Path.Combine(_root, "receipts");
            PacketPath = Path.Combine(_root, "packet.json");
            MarkdownPath = Path.Combine(_root, "script.md");
            StorePath = Path.Combine(_root, "subscribr-webhooks.json");

            File.WriteAllText(
                PacketPath,
                """
                {
                  "contract_name": "chummer.content_source_packet.v1",
                  "packet_id": "runbook-restore-runner-2026-06-26",
                  "mode": "RUNBOOK_VIDEO",
                  "target_provider": "subscribr",
                  "subscribr_channel_key": "chummer-runbook",
                  "approval": {
                    "publication_allowed": false
                  },
                  "source_heads": {
                    "chummer_core": "sha-core"
                  }
                }
                """);
            File.WriteAllText(MarkdownPath, "Approved scripted export.\n");

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["SUBSCRIBR_WEBHOOK_SECRET"] = configureSecret ? "unit-test-subscribr-secret" : null,
                    ["CHUMMER_SUBSCRIBR_ENABLED"] = configureLaneEnabled ? "true" : "false",
                    ["CHUMMER_SUBSCRIBR_WEBHOOKS_ENABLED"] = configureLaneEnabled ? "true" : "false",
                    ["CHUMMER_SUBSCRIBR_WEBHOOK_STORE_PATH"] = StorePath,
                    ["CHUMMER_SUBSCRIBR_WEBHOOK_RECEIPT_ROOT"] = ReceiptRoot
                })
                .Build();

            Store = new SubscribrWebhookStore(configuration);
            Service = new SubscribrProviderWebhookService(Store, configuration);
        }

        public string PacketPath { get; }
        public string MarkdownPath { get; }
        public string StorePath { get; }
        public string ReceiptRoot { get; }
        public SubscribrWebhookStore Store { get; }
        public SubscribrProviderWebhookService Service { get; }

        public SubscribrWebhookRequest ValidRequest()
            => new(
                EventId: "sub_evt_1",
                EventType: "script.export_ready",
                ProviderScriptId: "script_1",
                ProviderChannelId: "channel_1",
                ProviderIdeaId: "idea_1",
                PacketPath: PacketPath,
                MarkdownExportPath: MarkdownPath);

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
