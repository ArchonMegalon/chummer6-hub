using System.Text;
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
    public void WebhookKeepsReceiptPathInsideReceiptRootForUnsafeEventIds()
    {
        using Fixture fixture = new();
        SubscribrWebhookRequest request = fixture.ValidRequest() with { EventId = "../sub_evt_1" };
        string signature = fixture.Service.ComputeSignature(request, Fixture.Timestamp);

        SubscribrWebhookResult result = fixture.Service.ProcessWebhook(request, signature, Fixture.Timestamp, Fixture.Now);

        Assert.Equal("accepted", result.Status);
        Assert.NotNull(result.ReceiptPath);
        string receiptRoot = Path.GetFullPath(fixture.ReceiptRoot) + Path.DirectorySeparatorChar;
        string receiptPath = Path.GetFullPath(result.ReceiptPath!);
        Assert.StartsWith(receiptRoot, receiptPath, StringComparison.Ordinal);
        Assert.True(File.Exists(receiptPath));
    }

    [Fact]
    public void WebhookRejectsSourcePathsOutsideConfiguredRoots()
    {
        using Fixture fixture = new();
        string outsideRoot = Path.Combine(Path.GetTempPath(), "chummer-subscribr-webhook-outside", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(outsideRoot);

        try
        {
            string packetPath = Path.Combine(outsideRoot, "packet.json");
            string markdownPath = Path.Combine(outsideRoot, "script.md");
            File.WriteAllText(packetPath, File.ReadAllText(fixture.PacketPath));
            File.WriteAllText(markdownPath, "Provider export.\n");

            SubscribrWebhookRequest request = fixture.ValidRequest() with
            {
                PacketPath = packetPath,
                MarkdownExportPath = markdownPath
            };
            string signature = fixture.Service.ComputeSignature(request, Fixture.Timestamp);

            SubscribrWebhookResult result = fixture.Service.ProcessWebhook(request, signature, Fixture.Timestamp, Fixture.Now);

            Assert.Equal("rejected", result.Status);
            Assert.Contains("allowed source roots", result.RejectionReason, StringComparison.OrdinalIgnoreCase);
            Assert.Empty(Directory.GetFiles(fixture.ReceiptRoot));
        }
        finally
        {
            if (Directory.Exists(outsideRoot))
            {
                Directory.Delete(outsideRoot, recursive: true);
            }
        }
    }

    [Fact]
    public async Task ControllerAcceptsValidSignatureOverRawPayload()
    {
        using Fixture fixture = new();
        string timestamp = DateTimeOffset.UtcNow.ToString("O");
        string rawPayload = fixture.ValidRawRequestJson(includeIgnoredProperty: true);
        string signature = fixture.Service.ComputeSignature(rawPayload, timestamp);
        var controller = new SubscribrProviderWebhookController(fixture.Service)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(rawPayload));
        controller.Request.Headers["X-Subscribr-Signature"] = signature;
        controller.Request.Headers["X-Subscribr-Timestamp"] = timestamp;

        ActionResult<SubscribrWebhookResult> result = await controller.Webhook(CancellationToken.None);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result.Result);
        SubscribrWebhookResult payload = Assert.IsType<SubscribrWebhookResult>(ok.Value);
        Assert.Equal("accepted", payload.Status);
    }

    [Fact]
    public async Task ControllerUsesInternalRouteAndReturnsProblemWhenSecretMissing()
    {
        using Fixture fixture = new(configureSecret: false);
        var controller = new SubscribrProviderWebhookController(fixture.Service)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(fixture.ValidRawRequestJson()));
        controller.Request.Headers["X-Subscribr-Signature"] = "sha256=bad";
        controller.Request.Headers["X-Subscribr-Timestamp"] = Fixture.Timestamp;

        ActionResult<SubscribrWebhookResult> result = await controller.Webhook(CancellationToken.None);

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, problem.StatusCode);
    }

    [Fact]
    public void CorruptWebhookLedgerIsQuarantinedAndDoesNotBlockProcessing()
    {
        using Fixture fixture = new(seedCorruptStore: true);
        SubscribrWebhookRequest request = fixture.ValidRequest();
        string signature = fixture.Service.ComputeSignature(request, Fixture.Timestamp);

        SubscribrWebhookResult result = fixture.Service.ProcessWebhook(request, signature, Fixture.Timestamp, Fixture.Now);

        Assert.Equal("accepted", result.Status);
        Assert.True(File.Exists(fixture.StorePath));
        Assert.Single(Directory.GetFiles(fixture.RootPath, "subscribr-webhooks.json.corrupt-*"));
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

        public Fixture(bool configureSecret = true, bool configureLaneEnabled = true, bool seedCorruptStore = false)
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
            if (seedCorruptStore)
            {
                File.WriteAllText(StorePath, "{ definitely-not-json", Encoding.UTF8);
            }

            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["SUBSCRIBR_WEBHOOK_SECRET"] = configureSecret ? "unit-test-subscribr-secret" : null,
                    ["CHUMMER_SUBSCRIBR_ENABLED"] = configureLaneEnabled ? "true" : "false",
                    ["CHUMMER_SUBSCRIBR_WEBHOOKS_ENABLED"] = configureLaneEnabled ? "true" : "false",
                    ["CHUMMER_SUBSCRIBR_WEBHOOK_STORE_PATH"] = StorePath,
                    ["CHUMMER_SUBSCRIBR_WEBHOOK_RECEIPT_ROOT"] = ReceiptRoot,
                    ["CHUMMER_SUBSCRIBR_WEBHOOK_ALLOWED_SOURCE_ROOTS"] = _root
                })
                .Build();

            Store = new SubscribrWebhookStore(configuration);
            Service = new SubscribrProviderWebhookService(Store, configuration);
        }

        public string PacketPath { get; }
        public string MarkdownPath { get; }
        public string RootPath => _root;
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

        public string ValidRawRequestJson(bool includeIgnoredProperty = false)
        {
            string json = JsonSerializer.Serialize(ValidRequest(), new JsonSerializerOptions(JsonSerializerDefaults.Web));
            if (!includeIgnoredProperty)
            {
                return json;
            }

            return json.Insert(json.Length - 1, ",\"ignored\":\"signed-but-not-bound\"");
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }
}
