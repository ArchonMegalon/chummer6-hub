using System.Net;
using System.Text;
using System.Text.Json;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Heyy;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class HeyyScamChatServiceTests
{
    private const string ScammerFixturePhone = "+436765550423";
    private const string ConsentingTestPhone = "+436647916419";
    private const string MetaTestPhone = "+15555550101";
    private const string AlternateFixturePhone = "+15555550102";
    private const string ScamMessage = "Hallo Mama, mein Handy ist kaputt gegangen. Das ist meine neue Nummer. Kannst du mir bitte auf WhatsApp auf diese Nummer schreiben? +436765550423";

    [Fact]
    public async Task IngestIncoming_PreservesNumbersAndReturnsDraftOnlyVienneseOldLadyDraft()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"] = "false",
        });

        HeyyScamChatDraftResponse draft = await fixture.Service.IngestIncomingAsync(
            new HeyyScamChatIngestRequest(
                Channel: "heyy",
                ConversationId: "conv-mama-1",
                CounterpartyHandle: ScammerFixturePhone,
                MessageText: ScamMessage,
                ReceivedAtUtc: DateTimeOffset.Parse("2026-06-19T10:00:00Z")),
            CancellationToken.None);

        Assert.Equal("draft_only", draft.Mode);
        Assert.True(draft.ManualApprovalRequired);
        Assert.False(draft.AutoSendAllowed);
        Assert.Equal("empathetic_slow_typing_old_lady", draft.PersonaId);
        Assert.True(draft.MinimumDelaySeconds >= 240);
        Assert.Contains("Sabi", draft.DraftText, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Brille", draft.DraftText, StringComparison.OrdinalIgnoreCase);
        Assert.Equal("family_emergency_new_number", draft.Enrichment.ScamPattern);
        Assert.Contains(draft.Enrichment.RiskSignals, static item => item.Contains("new-number", StringComparison.OrdinalIgnoreCase));
        Assert.Contains(draft.Enrichment.ForbiddenActions, static item => item.Contains("Do not send money", StringComparison.OrdinalIgnoreCase));

        HeyyScamChatConversationResponse? conversation = fixture.Service.GetConversation("conv-mama-1");
        Assert.NotNull(conversation);
        Assert.Contains(ScammerFixturePhone, conversation.Messages[0].Text, StringComparison.Ordinal);
        Assert.Equal(ScammerFixturePhone, conversation.CounterpartyMasked);
    }

    [Fact]
    public async Task IngestIncoming_RedactsNumbersWhenRuntimePolicyRequiresIt()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"] = "true",
        });

        await fixture.Service.IngestIncomingAsync(
            new HeyyScamChatIngestRequest(
                Channel: "heyy",
                ConversationId: "conv-redacted",
                CounterpartyHandle: ScammerFixturePhone,
                MessageText: ScamMessage),
            CancellationToken.None);

        HeyyScamChatConversationResponse? conversation = fixture.Service.GetConversation("conv-redacted");
        Assert.NotNull(conversation);
        Assert.DoesNotContain(ScammerFixturePhone, conversation.Messages[0].Text, StringComparison.Ordinal);
        Assert.Contains("[phone-redacted", conversation.Messages[0].Text, StringComparison.Ordinal);
        Assert.Contains("[phone-redacted", conversation.CounterpartyMasked, StringComparison.Ordinal);
    }

    [Fact]
    public async Task IngestIncoming_SkipsDefaultAnswerlyEaChatWhenAuthIsMissing()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["ANSWERLY_OPENAI_COMPAT_EA_UPSTREAM_BASE_URL"] = "https://code.girschele.com",
            ["ANSWERLY_OPENAI_COMPAT_EA_UPSTREAM_BEARER_TOKEN"] = "",
            ["ANSWERLY_OPENAI_COMPAT_EA_CF_ACCESS_CLIENT_ID"] = "",
            ["ANSWERLY_OPENAI_COMPAT_EA_CF_ACCESS_CLIENT_SECRET"] = "",
        });

        HeyyScamChatDraftResponse draft = await fixture.Service.IngestIncomingAsync(
            new HeyyScamChatIngestRequest(
                Channel: "heyy",
                ConversationId: "conv-no-ea-auth",
                CounterpartyHandle: ScammerFixturePhone,
                MessageText: ScamMessage),
            CancellationToken.None);

        Assert.Equal("generated_fallback", draft.Status);
        Assert.Equal("ea_chat_unconfigured", draft.FailureReason);
        Assert.DoesNotContain(fixture.Handler.Requests, static item => item.Path.Contains("/v1/chat/completions", StringComparison.Ordinal));
    }

    [Fact]
    public async Task IngestIncoming_SecondDraftForgetsThenScrollsBack()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"] = "false",
        });

        await fixture.Service.IngestIncomingAsync(
            new HeyyScamChatIngestRequest(
                Channel: "heyy",
                ConversationId: "conv-scrollback",
                CounterpartyHandle: ScammerFixturePhone,
                MessageText: ScamMessage),
            CancellationToken.None);
        HeyyScamChatDraftResponse second = await fixture.Service.IngestIncomingAsync(
            new HeyyScamChatIngestRequest(
                Channel: "heyy",
                ConversationId: "conv-scrollback",
                CounterpartyHandle: ScammerFixturePhone,
                MessageText: "Ich bin doch die Sabi, Mama, schreib mir bitte gleich auf WhatsApp."),
            CancellationToken.None);

        Assert.Contains("hinaufgescrollt", second.DraftText, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("du hast eh recht", second.DraftText, StringComparison.OrdinalIgnoreCase);
        Assert.False(second.AutoSendAllowed);
    }

    [Fact]
    public async Task ApproveDraftRecordsManualCopyReceiptWithoutAutoSending()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"] = "false",
        });
        await fixture.Service.IngestIncomingAsync(
            new HeyyScamChatIngestRequest(
                Channel: "heyy",
                ConversationId: "conv-approve",
                CounterpartyHandle: ScammerFixturePhone,
                MessageText: ScamMessage),
            CancellationToken.None);

        HeyyScamChatApprovalResponse approval = await fixture.Service.ApproveDraftAsync(
            "conv-approve",
            new HeyyScamChatApproveDraftRequest(
                OperatorId: "tibor",
                DeliveryMode: "manual_copy",
                ConfirmManualApproval: true,
                DryRun: false),
            CancellationToken.None);

        Assert.Equal("manual_copy_ready", approval.Status);
        Assert.False(approval.AutoSendAllowed);
        Assert.True(approval.ManualApprovalConfirmed);
        Assert.Equal("manual_copy", approval.DeliveryMode);
        Assert.DoesNotContain(fixture.Handler.Requests, static item => item.Path == "/v1/tools/execute");

        HeyyScamChatConversationResponse? conversation = fixture.Service.GetConversation("conv-approve");
        Assert.NotNull(conversation);
        Assert.Single(conversation.Approvals);
        Assert.Contains(conversation.Messages, static item => item.Direction == "approved_manual_copy");
    }

    [Fact]
    public async Task ApproveDraftWhatsappModeDryRunReturnsReadyStatusAndDoesNotSend()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"] = "false",
            ["CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED"] = "true",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID"] = "principal-1",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_WHATSAPP_BINDING_ID"] = "whatsapp-binding",
        });
        await fixture.Service.IngestIncomingAsync(
            new HeyyScamChatIngestRequest(
                Channel: "heyy",
                ConversationId: "conv-whatsapp-dry-run",
                CounterpartyHandle: ScammerFixturePhone,
                MessageText: ScamMessage),
            CancellationToken.None);

        HeyyScamChatApprovalResponse approval = await fixture.Service.ApproveDraftAsync(
            "conv-whatsapp-dry-run",
            new HeyyScamChatApproveDraftRequest(
                OperatorId: "tibor",
                DeliveryMode: "whatsapp_approved",
                Recipient: ConsentingTestPhone,
                ConfirmManualApproval: true,
                DryRun: true),
            CancellationToken.None);

        Assert.Equal("dry_run_whatsapp_approved_ready", approval.Status);
        Assert.Equal("whatsapp_approved", approval.DeliveryMode);
        Assert.Empty(fixture.Handler.Requests);
    }

    [Fact]
    public async Task ApproveDraftWhatsappModeRespectsWhatsappRecipientAllowAndBlockedLists()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"] = "false",
            ["CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED"] = "true",
            ["CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ALLOWED_RECIPIENTS"] = ConsentingTestPhone,
            ["CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID"] = "principal-1",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_WHATSAPP_BINDING_ID"] = "whatsapp-binding",
        });
        await fixture.Service.IngestIncomingAsync(
            new HeyyScamChatIngestRequest(
                Channel: "heyy",
                ConversationId: "conv-whatsapp-legacy-lists",
                CounterpartyHandle: ScammerFixturePhone,
                MessageText: ScamMessage),
            CancellationToken.None);

        HeyyScamChatApprovalResponse approval = await fixture.Service.ApproveDraftAsync(
            "conv-whatsapp-legacy-lists",
            new HeyyScamChatApproveDraftRequest(
                OperatorId: "tibor",
                DeliveryMode: "whatsapp_approved",
                Recipient: ScammerFixturePhone,
                ConfirmManualApproval: true,
                DryRun: false),
            CancellationToken.None);

        Assert.Equal("suppressed_whatsapp_recipient_invalid", approval.Status);
        Assert.Equal("recipient_invalid", approval.FailureReason);

        Assert.DoesNotContain(fixture.Handler.Requests, static item => item.Path == "/v1/tools/execute");
    }

    [Fact]
    public async Task ApproveDraftWhatsappModeBlocksRecipientInConfiguredBlocklist()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"] = "false",
            ["CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED"] = "true",
            ["CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ALLOWED_RECIPIENTS"] = $"{ConsentingTestPhone}, {MetaTestPhone}",
            ["CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_BLOCKED_RECIPIENTS"] = ScammerFixturePhone,
            ["CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID"] = "principal-1",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_WHATSAPP_BINDING_ID"] = "whatsapp-binding",
        });
        await fixture.Service.IngestIncomingAsync(
            new HeyyScamChatIngestRequest(
                Channel: "heyy",
                ConversationId: "conv-whatsapp-blocked-list",
                CounterpartyHandle: ScammerFixturePhone,
                MessageText: ScamMessage),
            CancellationToken.None);

        HeyyScamChatApprovalResponse approval = await fixture.Service.ApproveDraftAsync(
            "conv-whatsapp-blocked-list",
            new HeyyScamChatApproveDraftRequest(
                OperatorId: "tibor",
                DeliveryMode: "whatsapp_approved",
                Recipient: ScammerFixturePhone,
                ConfirmManualApproval: true,
                DryRun: false),
            CancellationToken.None);

        Assert.Equal("suppressed_whatsapp_recipient_invalid", approval.Status);
        Assert.Equal("recipient_invalid", approval.FailureReason);
    }

    [Fact]
    public async Task ApproveDraftWhatsappModeSendsWhenAllowedAndConfigured()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"] = "false",
            ["CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED"] = "true",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID"] = "principal-1",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_WHATSAPP_BINDING_ID"] = "whatsapp-binding",
        });
        await fixture.Service.IngestIncomingAsync(
            new HeyyScamChatIngestRequest(
                Channel: "heyy",
                ConversationId: "conv-whatsapp-sent",
                CounterpartyHandle: ScammerFixturePhone,
                MessageText: ScamMessage),
            CancellationToken.None);

        HeyyScamChatApprovalResponse approval = await fixture.Service.ApproveDraftAsync(
            "conv-whatsapp-sent",
            new HeyyScamChatApproveDraftRequest(
                OperatorId: "tibor",
                DeliveryMode: "whatsapp_approved",
                Recipient: ConsentingTestPhone,
                ConfirmManualApproval: true,
                DryRun: false),
            CancellationToken.None);

        Assert.Equal("sent_whatsapp_approved", approval.Status);
        Assert.Equal("whatsapp_approved", approval.DeliveryMode);
        Assert.Equal("ea-delivery-1", approval.DeliveryRef);
        LoggedRequest request = Assert.Single(fixture.Handler.Requests, static item => item.Path == "/v1/tools/execute");
        using JsonDocument json = JsonDocument.Parse(request.Body);
        JsonElement payload = json.RootElement.GetProperty("payload_json");
        Assert.Equal("whatsapp", payload.GetProperty("channel").GetString());
        Assert.Equal(ConsentingTestPhone, payload.GetProperty("recipient").GetString());
        JsonElement metadata = payload.GetProperty("metadata");
        Assert.Equal("whatsapp_approved", metadata.GetProperty("delivery_mode").GetString());
        Assert.True(metadata.GetProperty("manual_approval_required").GetBoolean());
        Assert.False(metadata.GetProperty("auto_send_allowed").GetBoolean());
    }

    [Fact]
    public async Task ApproveDraftWhatsappModeHonorsConfiguredWhatsappDeliveryRouteEa()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"] = "false",
            ["CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED"] = "true",
            ["CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_DELIVERY_ROUTE"] = "ea",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID"] = "principal-1",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_WHATSAPP_BINDING_ID"] = "whatsapp-binding",
            ["CHUMMER_HEYY_SCAM_CHAT_META_ACCESS_TOKEN"] = "meta-token",
            ["CHUMMER_HEYY_SCAM_CHAT_META_PHONE_NUMBER_ID"] = "1234567890",
            ["CHUMMER_HEYY_SCAM_CHAT_META_GRAPH_VERSION"] = "v21.0",
        });
        await fixture.Service.IngestIncomingAsync(
            new HeyyScamChatIngestRequest(
                Channel: "heyy",
                ConversationId: "conv-whatsapp-route-ea",
                CounterpartyHandle: ScammerFixturePhone,
                MessageText: ScamMessage),
            CancellationToken.None);

        HeyyScamChatApprovalResponse approval = await fixture.Service.ApproveDraftAsync(
            "conv-whatsapp-route-ea",
            new HeyyScamChatApproveDraftRequest(
                OperatorId: "tibor",
                DeliveryMode: "whatsapp_approved",
                Recipient: ConsentingTestPhone,
                ConfirmManualApproval: true,
                DryRun: false),
            CancellationToken.None);

        Assert.Equal("sent_whatsapp_approved", approval.Status);
        LoggedRequest request = Assert.Single(fixture.Handler.Requests, static item => item.Path == "/v1/tools/execute");
        Assert.DoesNotContain(fixture.Handler.Requests, static item => item.Path == "/v21.0/1234567890/messages");
        using JsonDocument json = JsonDocument.Parse(request.Body);
        JsonElement payload = json.RootElement.GetProperty("payload_json");
        Assert.Equal("whatsapp", payload.GetProperty("channel").GetString());
    }

    [Fact]
    public async Task ApproveDraftWhatsappModeSendsThroughMetaCloudApiWhenConfigured()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"] = "false",
            ["CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED"] = "true",
            ["CHUMMER_HEYY_SCAM_CHAT_META_ACCESS_TOKEN"] = "meta-token",
            ["CHUMMER_HEYY_SCAM_CHAT_META_PHONE_NUMBER_ID"] = "1234567890",
            ["CHUMMER_HEYY_SCAM_CHAT_META_GRAPH_VERSION"] = "v21.0",
        });
        await fixture.Service.IngestIncomingAsync(
            new HeyyScamChatIngestRequest(
                Channel: "heyy",
                ConversationId: "conv-whatsapp-meta",
                CounterpartyHandle: ScammerFixturePhone,
                MessageText: ScamMessage),
            CancellationToken.None);

        HeyyScamChatApprovalResponse approval = await fixture.Service.ApproveDraftAsync(
            "conv-whatsapp-meta",
            new HeyyScamChatApproveDraftRequest(
                OperatorId: "tibor",
                DeliveryMode: "whatsapp_approved",
                Recipient: ConsentingTestPhone,
                ConfirmManualApproval: true,
                DryRun: false),
            CancellationToken.None);

        Assert.Equal("sent_whatsapp_approved", approval.Status);
        Assert.Equal("wamid.meta1", approval.DeliveryRef);
        LoggedRequest request = Assert.Single(fixture.Handler.Requests, static item => item.Path == "/v21.0/1234567890/messages");
        using JsonDocument json = JsonDocument.Parse(request.Body);
        Assert.Equal("whatsapp", json.RootElement.GetProperty("messaging_product").GetString());
        Assert.Equal("436647916419", json.RootElement.GetProperty("to").GetString());
        Assert.Equal("text", json.RootElement.GetProperty("type").GetString());
        Assert.False(json.RootElement.GetProperty("text").GetProperty("preview_url").GetBoolean());
        Assert.NotEmpty(json.RootElement.GetProperty("text").GetProperty("body").GetString() ?? string.Empty);
    }

    [Fact]
    public async Task FiveIncomingTurnsCreateOperatorSmsSummaryReceiptButDoNotUseMockDelivery()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"] = "false",
            ["CHUMMER_HEYY_SCAM_CHAT_OPERATOR_SUMMARY_TURNS"] = "5",
            ["CHUMMER_HEYY_SCAM_CHAT_OPERATOR_SMS_ENABLED"] = "true",
            ["CHUMMER_HEYY_SCAM_CHAT_OPERATOR_SMS_TO"] = ConsentingTestPhone,
            ["CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL"] = "http://support-progress-mock:8080",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID"] = "principal-1",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_BINDING_ID"] = "binding-1",
        });

        for (int i = 1; i <= 5; i++)
        {
            await fixture.Service.IngestIncomingAsync(
                new HeyyScamChatIngestRequest(
                    Channel: "heyy",
                    ConversationId: "conv-summary",
                    CounterpartyHandle: ScammerFixturePhone,
                    MessageText: i == 1 ? ScamMessage : $"Mama bitte antworte, Runde {i}."),
                CancellationToken.None);
        }

        HeyyScamChatConversationResponse? conversation = fixture.Service.GetConversation("conv-summary");
        Assert.NotNull(conversation);
        HeyyScamChatOperatorSummaryResponse summary = Assert.Single(conversation.OperatorSummaries);
        Assert.Equal(5, summary.IncomingTurnCount);
        Assert.Equal("suppressed_sms_unconfigured", summary.Status);
        Assert.Equal("real_sms_delivery_unconfigured", summary.FailureReason);
        Assert.Equal("[phone-redacted:*6419]", summary.RecipientMasked);
        Assert.Contains("Operator summary for", summary.Content, StringComparison.Ordinal);
        Assert.DoesNotContain(fixture.Handler.Requests, static item => item.Body.Contains("\"channel\":\"sms\"", StringComparison.Ordinal));
    }

    [Fact]
    public async Task FiveIncomingTurnsCreateOperatorWhatsappSummaryReceiptThroughMetaAndSend()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"] = "false",
            ["CHUMMER_HEYY_SCAM_CHAT_OPERATOR_SUMMARY_TURNS"] = "5",
            ["CHUMMER_HEYY_SCAM_CHAT_OPERATOR_SUMMARY_CHANNEL"] = "whatsapp",
            ["CHUMMER_HEYY_SCAM_CHAT_OPERATOR_SUMMARY_TO"] = MetaTestPhone,
            ["CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED"] = "true",
            ["CHUMMER_HEYY_SCAM_CHAT_META_ACCESS_TOKEN"] = "meta-token",
            ["CHUMMER_HEYY_SCAM_CHAT_META_PHONE_NUMBER_ID"] = "1234567890",
            ["CHUMMER_HEYY_SCAM_CHAT_META_GRAPH_VERSION"] = "v21.0",
        });

        for (int i = 1; i <= 5; i++)
        {
            await fixture.Service.IngestIncomingAsync(
                new HeyyScamChatIngestRequest(
                    Channel: "heyy",
                    ConversationId: "conv-whatsapp-summary",
                    CounterpartyHandle: AlternateFixturePhone,
                    MessageText: i == 1 ? ScamMessage : $"Mama bitte antworte, Runde {i}."),
                CancellationToken.None);
        }

        HeyyScamChatConversationResponse? conversation = fixture.Service.GetConversation("conv-whatsapp-summary");
        Assert.NotNull(conversation);
        HeyyScamChatOperatorSummaryResponse summary = Assert.Single(conversation.OperatorSummaries);
        Assert.Equal(5, summary.IncomingTurnCount);
        Assert.Equal("sent_whatsapp", summary.Status);
        Assert.Equal("whatsapp", summary.Channel);
        Assert.Equal("wamid.meta1", summary.DeliveryRef);
        LoggedRequest request = Assert.Single(fixture.Handler.Requests, static item => item.Path == "/v21.0/1234567890/messages");
        Assert.Contains("\"to\":\"15555550101\"", request.Body, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task FiveIncomingTurnsCreateOperatorWhatsappSummaryRespectsRecipientAllowlist()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"] = "false",
            ["CHUMMER_HEYY_SCAM_CHAT_OPERATOR_SUMMARY_TURNS"] = "5",
            ["CHUMMER_HEYY_SCAM_CHAT_OPERATOR_SUMMARY_CHANNEL"] = "whatsapp",
            ["CHUMMER_HEYY_SCAM_CHAT_OPERATOR_SUMMARY_TO"] = MetaTestPhone,
            ["CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ENABLED"] = "true",
            ["CHUMMER_HEYY_SCAM_CHAT_WHATSAPP_ALLOWED_RECIPIENTS"] = MetaTestPhone,
            ["CHUMMER_HEYY_SCAM_CHAT_META_ACCESS_TOKEN"] = "meta-token",
            ["CHUMMER_HEYY_SCAM_CHAT_META_PHONE_NUMBER_ID"] = "1234567890",
            ["CHUMMER_HEYY_SCAM_CHAT_META_GRAPH_VERSION"] = "v21.0",
        });

        for (int i = 1; i <= 5; i++)
        {
            await fixture.Service.IngestIncomingAsync(
                new HeyyScamChatIngestRequest(
                    Channel: "heyy",
                    ConversationId: "conv-whatsapp-summary-blocked",
                    CounterpartyHandle: AlternateFixturePhone,
                    MessageText: i == 1 ? ScamMessage : $"Mama bitte antworte, Runde {i}."),
                CancellationToken.None);
        }

        HeyyScamChatConversationResponse? conversation = fixture.Service.GetConversation("conv-whatsapp-summary-blocked");
        Assert.NotNull(conversation);
        HeyyScamChatOperatorSummaryResponse summary = Assert.Single(conversation.OperatorSummaries);
        Assert.Equal("sent_whatsapp", summary.Status);
        Assert.Null(summary.FailureReason);
        Assert.Equal("whatsapp", summary.Channel);
        LoggedRequest request = Assert.Single(fixture.Handler.Requests, static item => item.Path == "/v21.0/1234567890/messages");
        Assert.Contains("\"to\":\"15555550101\"", request.Body, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task DigestDispatchSendsDailyEmailThroughEaAndDoesNotDuplicate()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"] = "false",
            ["CHUMMER_HEYY_SCAM_CHAT_DIGEST_ENABLED"] = "true",
            ["CHUMMER_HEYY_SCAM_CHAT_DIGEST_TO"] = "operator@example.com",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_PRINCIPAL_ID"] = "principal-1",
            ["CHUMMER_HEYY_SCAM_CHAT_EA_BINDING_ID"] = "binding-1",
        });
        await fixture.Service.IngestIncomingAsync(
            new HeyyScamChatIngestRequest(
                Channel: "heyy",
                ConversationId: "conv-digest",
                CounterpartyHandle: ScammerFixturePhone,
                MessageText: ScamMessage,
                ReceivedAtUtc: DateTimeOffset.Parse("2026-06-19T11:00:00Z")),
            CancellationToken.None);

        HeyyScamChatDigestResponse first = await fixture.Service.DispatchDailyDigestAsync(new DateOnly(2026, 6, 19), dryRun: false, CancellationToken.None);
        HeyyScamChatDigestResponse second = await fixture.Service.DispatchDailyDigestAsync(new DateOnly(2026, 6, 19), dryRun: false, CancellationToken.None);

        Assert.Equal("sent", first.Status);
        Assert.Equal(first.DigestId, second.DigestId);
        Assert.Equal("ea-delivery-1", first.DeliveryRef);
        Assert.Contains(ScammerFixturePhone, first.Content, StringComparison.Ordinal);
        LoggedRequest request = Assert.Single(fixture.Handler.Requests, static item => item.Path == "/v1/tools/execute");
        Assert.Contains("\"channel\":\"email\"", request.Body, StringComparison.Ordinal);
        Assert.Contains("\"recipient\":\"operator@example.com\"", request.Body, StringComparison.Ordinal);
        Assert.Contains("\"auto_send_allowed\":false", request.Body, StringComparison.Ordinal);
    }

    [Fact]
    public async Task TeableProjectionStoresEnrichedConversationRows()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"] = "false",
            ["CHUMMER_TEABLE_HEYY_SCAM_CHAT_ENABLED"] = "true",
            ["CHUMMER_TEABLE_HEYY_SCAM_CHAT_API_KEY"] = "teable-token",
            ["CHUMMER_TEABLE_HEYY_SCAM_CHAT_API_BASE_URL"] = "https://app.teable.ai/api",
            ["CHUMMER_TEABLE_HEYY_SCAM_CHAT_BASE_ID"] = "base-demo",
        });
        await fixture.Service.IngestIncomingAsync(
            new HeyyScamChatIngestRequest(
                Channel: "heyy",
                ConversationId: "conv-teable",
                CounterpartyHandle: ScammerFixturePhone,
                MessageText: ScamMessage),
            CancellationToken.None);

        TeableHeyyScamChatSyncResult result = await fixture.Teable.SyncAllAsync();

        Assert.Equal("passed", result.State);
        Assert.Equal(1, result.SyncedCount);
        LoggedRequest createTable = Assert.Single(fixture.Handler.Requests, static item => item.Method == HttpMethod.Post && item.Path == "/api/base/base-demo/table/");
        using JsonDocument createTablePayload = JsonDocument.Parse(createTable.Body);
        Assert.False(createTablePayload.RootElement.TryGetProperty("icon", out _));
        Assert.DoesNotContain("\"unique\"", createTable.Body, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("\"notNull\"", createTable.Body, StringComparison.OrdinalIgnoreCase);
        LoggedRequest create = Assert.Single(fixture.Handler.Requests, static item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_heyy/record");
        Assert.Contains("\"Conversation Id\":\"conv-teable\"", create.Body, StringComparison.Ordinal);
        Assert.Contains("436765550423", create.Body, StringComparison.Ordinal);
        Assert.Contains("family_emergency_new_number", create.Body, StringComparison.Ordinal);
        Assert.Contains("Manual Approval Required", create.Body, StringComparison.Ordinal);
        Assert.Contains("Latest Draft", create.Body, StringComparison.Ordinal);
    }

    [Fact]
    public async Task TeableProjectionEscapesConversationIdForTqlFilter()
    {
        const string conversationId = "conv-with'special value";

        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"] = "false",
            ["CHUMMER_TEABLE_HEYY_SCAM_CHAT_ENABLED"] = "true",
            ["CHUMMER_TEABLE_HEYY_SCAM_CHAT_API_KEY"] = "teable-token",
            ["CHUMMER_TEABLE_HEYY_SCAM_CHAT_API_BASE_URL"] = "https://app.teable.ai/api",
            ["CHUMMER_TEABLE_HEYY_SCAM_CHAT_BASE_ID"] = "base-demo",
            ["CHUMMER_TEABLE_HEYY_SCAM_CHAT_TABLE_ID"] = "tbl_heyy",
        });
        await fixture.Service.IngestIncomingAsync(
            new HeyyScamChatIngestRequest(
                Channel: "heyy",
                ConversationId: conversationId,
                CounterpartyHandle: ScammerFixturePhone,
                MessageText: ScamMessage),
            CancellationToken.None);

        await fixture.Teable.SyncAllAsync();

        LoggedRequest getRequest = Assert.Single(
            fixture.Handler.Requests,
            static item => item.Method == HttpMethod.Get && item.Path.StartsWith("/api/table/tbl_heyy/record?", StringComparison.Ordinal));
        string? filter = ExtractFilterByTql(getRequest.Path);
        Assert.NotNull(filter);
        Assert.Equal("{Conversation Id} = 'conv-with\\'special value'", filter);
    }

    [Fact]
    public async Task ApprovalUpdatesTeableProjectionWhenConversationTranscriptChanges()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"] = "false",
            ["CHUMMER_TEABLE_HEYY_SCAM_CHAT_ENABLED"] = "true",
            ["CHUMMER_TEABLE_HEYY_SCAM_CHAT_API_KEY"] = "teable-token",
            ["CHUMMER_TEABLE_HEYY_SCAM_CHAT_API_BASE_URL"] = "https://app.teable.ai/api",
            ["CHUMMER_TEABLE_HEYY_SCAM_CHAT_BASE_ID"] = "base-demo",
        }, attachTeableToService: true);

        await fixture.Service.IngestIncomingAsync(
            new HeyyScamChatIngestRequest(
                Channel: "heyy",
                ConversationId: "conv-teable-approval",
                CounterpartyHandle: ScammerFixturePhone,
                MessageText: ScamMessage),
            CancellationToken.None);

        const string approvedText = "Bitte warte kurz, ich muss erst die Brille suchen.";

        await fixture.Service.ApproveDraftAsync(
            "conv-teable-approval",
            new HeyyScamChatApproveDraftRequest(
                ConfirmManualApproval: true,
                DeliveryMode: "manual_copy",
                ApprovedText: approvedText,
                DryRun: false),
            CancellationToken.None);

        await fixture.Teable.SyncAllAsync();

        LoggedRequest latestProjection = fixture.Handler.Requests
            .Last(item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_heyy/record");
        Assert.Contains(approvedText, latestProjection.Body, StringComparison.Ordinal);
    }

    [Fact]
    public async Task InternalControllerRequiresBearerAndCanIngestAuthorizedMessage()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_INTERNAL_TOKEN"] = "internal-token",
        });
        HeyyScamChatController controller = new(fixture.Service, fixture.Teable, fixture.Configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        ActionResult<HeyyScamChatDraftResponse> denied = await controller.IngestMessage(
            new HeyyScamChatIngestRequest("heyy", "conv-auth", ScammerFixturePhone, ScamMessage),
            CancellationToken.None);
        Assert.IsType<ObjectResult>(denied.Result);

        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer internal-token";
        ActionResult<HeyyScamChatDraftResponse> accepted = await controller.IngestMessage(
            new HeyyScamChatIngestRequest("heyy", "conv-auth", ScammerFixturePhone, ScamMessage),
            CancellationToken.None);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(accepted.Result);
        HeyyScamChatDraftResponse draft = Assert.IsType<HeyyScamChatDraftResponse>(ok.Value);
        Assert.False(draft.AutoSendAllowed);
    }

    [Fact]
    public async Task InternalControllerFallsBackToFleetTokenWhenHeyyTokenIsEmpty()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_HEYY_SCAM_CHAT_INTERNAL_TOKEN"] = "",
            ["FLEET_INTERNAL_API_TOKEN"] = "fleet-token",
        });
        HeyyScamChatController controller = new(fixture.Service, fixture.Teable, fixture.Configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer fleet-token";

        ActionResult<HeyyScamChatDraftResponse> accepted = await controller.IngestMessage(
            new HeyyScamChatIngestRequest("heyy", "conv-fleet-auth", ScammerFixturePhone, ScamMessage),
            CancellationToken.None);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(accepted.Result);
        HeyyScamChatDraftResponse draft = Assert.IsType<HeyyScamChatDraftResponse>(ok.Value);
        Assert.Equal("conv-fleet-auth", draft.ConversationId);
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture(IReadOnlyDictionary<string, string?>? overrides = null, bool attachTeableToService = false)
        {
            _root = Path.Combine(Path.GetTempPath(), "heyy-scam-chat-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            Handler = new FakeHandler();
            Dictionary<string, string?> values = new()
            {
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community-store.json"),
                ["CHUMMER_HEYY_SCAM_CHAT_REDACT_NUMBERS"] = "false",
                ["CHUMMER_HEYY_SCAM_CHAT_DIGEST_ENABLED"] = "false",
                ["CHUMMER_TEABLE_HEYY_SCAM_CHAT_ENABLED"] = "false",
            };
            if (overrides is not null)
            {
                foreach ((string key, string? value) in overrides)
                {
                    values[key] = value;
                }
            }

            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(values)
                .Build();
            Store = new CommunityStore(Configuration, NullLogger<CommunityStore>.Instance);
            Teable = new TeableHeyyScamChatService(
                Store,
                Configuration,
                new StaticHttpClientFactory(new HttpClient(Handler)),
                NullLogger<TeableHeyyScamChatService>.Instance);
            Service = new HeyyScamChatService(
                new HttpClient(Handler),
                Store,
                Configuration,
                attachTeableToService ? Teable : null,
                NullLogger<HeyyScamChatService>.Instance);
        }

        public IConfiguration Configuration { get; }
        public CommunityStore Store { get; }
        public HeyyScamChatService Service { get; }
        public TeableHeyyScamChatService Teable { get; }
        public FakeHandler Handler { get; }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }

    private sealed class StaticHttpClientFactory : IHttpClientFactory
    {
        private readonly HttpClient _client;

        public StaticHttpClientFactory(HttpClient client)
        {
            _client = client;
        }

        public HttpClient CreateClient(string name) => _client;
    }

    private sealed class FakeHandler : HttpMessageHandler
    {
        private readonly HashSet<string> _fields = new(StringComparer.OrdinalIgnoreCase);

        public List<LoggedRequest> Requests { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            string path = request.RequestUri?.PathAndQuery ?? string.Empty;
            string body = request.Content is null ? string.Empty : await request.Content.ReadAsStringAsync(cancellationToken);
            Requests.Add(new LoggedRequest(request.Method, path, body));

            if (request.Method == HttpMethod.Post && path == "/v1/tools/execute")
            {
                return Json(HttpStatusCode.OK, """{"target_ref":"ea-delivery-1"}""");
            }

            if (request.Method == HttpMethod.Post && path == "/v21.0/1234567890/messages")
            {
                return Json(HttpStatusCode.OK, """{"messages":[{"id":"wamid.meta1"}]}""");
            }

            if (request.Method == HttpMethod.Get && path == "/api/base/base-demo/table")
            {
                return Json(HttpStatusCode.OK, "[]");
            }

            if (request.Method == HttpMethod.Post && path == "/api/base/base-demo/table/")
            {
                return Json(HttpStatusCode.Created, """{"id":"tbl_heyy"}""");
            }

            if (request.Method == HttpMethod.Get && path.StartsWith("/api/table/tbl_heyy/field", StringComparison.Ordinal))
            {
                string payload = JsonSerializer.Serialize(_fields.Select(static name => new { id = $"fld_{name.Replace(" ", "_", StringComparison.Ordinal)}", name }).ToArray());
                return Json(HttpStatusCode.OK, payload);
            }

            if (request.Method == HttpMethod.Post && path == "/api/table/tbl_heyy/field")
            {
                using JsonDocument document = JsonDocument.Parse(body);
                string name = document.RootElement.GetProperty("name").GetString() ?? string.Empty;
                if (!string.IsNullOrWhiteSpace(name))
                {
                    _fields.Add(name);
                }

                return Json(HttpStatusCode.Created, $$"""{"id":"fld_{{_fields.Count}}","name":{{JsonSerializer.Serialize(name)}}}""");
            }

            if (request.Method == HttpMethod.Get && path.StartsWith("/api/table/tbl_heyy/record?", StringComparison.Ordinal))
            {
                return Json(HttpStatusCode.OK, """{"records":[]}""");
            }

            if (request.Method == HttpMethod.Post && path == "/api/table/tbl_heyy/record")
            {
                return Json(HttpStatusCode.Created, """{"records":[{"id":"rec_heyy"}]}""");
            }

            return Json(HttpStatusCode.NotFound, $$"""{"path":{{JsonSerializer.Serialize(path)}}}""");
        }

        private static HttpResponseMessage Json(HttpStatusCode statusCode, string payload)
            => new(statusCode)
            {
                Content = new StringContent(payload, Encoding.UTF8, "application/json")
            };
    }

    private static string? ExtractFilterByTql(string path)
    {
        int marker = path.IndexOf("filterByTql=", StringComparison.Ordinal);
        if (marker < 0)
        {
            return null;
        }

        string encoded = path[(marker + "filterByTql=".Length)..];
        int next = encoded.IndexOf('&', StringComparison.Ordinal);
        if (next >= 0)
        {
            encoded = encoded[..next];
        }

        return Uri.UnescapeDataString(encoded);
    }

    private sealed record LoggedRequest(HttpMethod Method, string Path, string Body);
}
