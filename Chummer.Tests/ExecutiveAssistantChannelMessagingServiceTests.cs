using System.Text;
using System.Text.Json;
using System.Net;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class ExecutiveAssistantChannelMessagingServiceTests
{
    [Fact]
    public async Task SendMessageAsync_callsEaAndPersistsConversationWhenConfigured()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_PRINCIPAL_ID"] = "principal-runner",
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_TELEGRAM_BINDING_ID"] = "telegram-binding",
            ["CHUMMER_TEABLE_EXECUTIVE_ASSISTANT_CHANNEL_ENABLED"] = "false"
        });

        const string subjectId = "subject.ea.runner";
        fixture.Accounts.EnsureUserWithStatus(subjectId, "Runner", "runner@example.com");
        fixture.Links.LinkChannel(new LinkChannelRequest(subjectId, "telegram_official_bot", "@runnerbot", true));
        fixture.Links.LinkChannelToExecutiveAssistant("telegram_official_bot", new LinkChannelToExecutiveAssistantRequest(subjectId, null));

        ExecutiveAssistantChannelSendResult result = await fixture.Service.SendMessageAsync(
            subjectId,
            "telegram_official_bot",
            new ExecutiveAssistantChannelSendRequest("hello from executive assistant", CounterpartyHandle: null),
            CancellationToken.None);

        Assert.Equal("sent", result.Status);
        Assert.Equal("ea-target-1", result.DeliveryRef);
        Assert.StartsWith("telegram_official_bot:", result.ConversationId);
        Assert.Single(fixture.Handler.Requests, item => item.Method == HttpMethod.Post && item.Path == "/v1/tools/execute");
        Assert.Single(fixture.Store.ExecutiveAssistantChannelConversations);
        Assert.Single(fixture.Store.ExecutiveAssistantChannelMessages);
        Assert.Contains(fixture.Handler.Requests, item => item.Method == HttpMethod.Post && item.Path == "/v1/tools/execute");
    }

    [Fact]
    public void ListConversations_returnsOnlyChannelDataForUser()
    {
        using Fixture fixture = new();

        const string subject1Id = "subject.ea.reader.1";
        const string subject2Id = "subject.ea.reader.2";
        fixture.Accounts.EnsureUserWithStatus(subject1Id, "Reader One", "reader1@example.com");
        fixture.Accounts.EnsureUserWithStatus(subject2Id, "Reader Two", "reader2@example.com");
        fixture.Links.LinkChannel(new LinkChannelRequest(subject1Id, "telegram_official_bot", "runnerbot.one", true));
        fixture.Links.LinkChannel(new LinkChannelRequest(subject2Id, "telegram_official_bot", "runnerbot.two", true));
        fixture.Links.LinkChannelToExecutiveAssistant("telegram_official_bot", new LinkChannelToExecutiveAssistantRequest(subject1Id, null));
        fixture.Links.LinkChannelToExecutiveAssistant("telegram_official_bot", new LinkChannelToExecutiveAssistantRequest(subject2Id, null));

        fixture.Store.ExecutiveAssistantChannelMessages.Add(new ExecutiveAssistantChannelMessageState(
            MessageId: "m1",
            ConversationId: "telegram_official_bot:user1:111111111111",
            ChannelKind: "telegram_official_bot",
            Direction: "incoming",
            Text: "hello",
            SafetyLabel: "safe",
            DeliveryStatus: "received",
            CreatedAtUtc: DateTimeOffset.UtcNow.AddMinutes(-5),
            CounterpartyHandle: "runnerbot.one",
            DeliveryRef: null,
            FailureReason: null,
            IdempotencyKey: null));
        fixture.Store.ExecutiveAssistantChannelConversations.Add(new ExecutiveAssistantChannelConversationState(
            ConversationId: "telegram_official_bot:user1:111111111111",
            UserId: fixture.Accounts.EnsureUser(subject1Id).UserId,
            ChannelKind: "telegram_official_bot",
            CounterpartyHandle: "runnerbot.one",
            CounterpartyHash: "11111111111111111111111111111111111111111111111111111111111111111111",
            Status: "active",
            CreatedAtUtc: DateTimeOffset.UtcNow.AddMinutes(-5),
            UpdatedAtUtc: DateTimeOffset.UtcNow.AddMinutes(-5),
            LatestMessageId: "m1"));
        fixture.Store.ExecutiveAssistantChannelMessages.Add(new ExecutiveAssistantChannelMessageState(
            MessageId: "m2",
            ConversationId: "telegram_official_bot:user2:222222222222",
            ChannelKind: "telegram_official_bot",
            Direction: "incoming",
            Text: "hello",
            SafetyLabel: "safe",
            DeliveryStatus: "received",
            CreatedAtUtc: DateTimeOffset.UtcNow.AddMinutes(-5),
            CounterpartyHandle: "runnerbot.two",
            DeliveryRef: null,
            FailureReason: null,
            IdempotencyKey: null));
        fixture.Store.ExecutiveAssistantChannelConversations.Add(new ExecutiveAssistantChannelConversationState(
            ConversationId: "telegram_official_bot:user2:222222222222",
            UserId: fixture.Accounts.EnsureUser(subject2Id).UserId,
            ChannelKind: "telegram_official_bot",
            CounterpartyHandle: "runnerbot.two",
            CounterpartyHash: "22222222222222222222222222222222222222222222222222222222222222222222",
            Status: "active",
            CreatedAtUtc: DateTimeOffset.UtcNow.AddMinutes(-5),
            UpdatedAtUtc: DateTimeOffset.UtcNow.AddMinutes(-5),
            LatestMessageId: "m2"));

        IReadOnlyList<ExecutiveAssistantChannelConversationDto> conversations = fixture.Service.ListConversations(
            subject1Id,
            "telegram_official_bot",
            take: 24);
        Assert.Single(conversations);
        Assert.Equal("telegram_official_bot:user1:111111111111", conversations[0].ConversationId);
    }

    [Fact]
    public void GetConversation_returnsConversationByIdWithMessages()
    {
        using Fixture fixture = new();

        const string subjectId = "subject.ea.conversation.get";
        fixture.Accounts.EnsureUserWithStatus(subjectId, "Reader", "reader@example.com");
        fixture.Links.LinkChannel(new LinkChannelRequest(subjectId, "whatsapp_official_business", "+43 664 791 6419", true));
        fixture.Links.LinkChannelToExecutiveAssistant("whatsapp_official_business", new LinkChannelToExecutiveAssistantRequest(subjectId, null));
        fixture.Store.ExecutiveAssistantChannelConversations.Add(new ExecutiveAssistantChannelConversationState(
            ConversationId: "whatsapp_official_business:convo-1",
            UserId: fixture.Accounts.EnsureUser(subjectId).UserId,
            ChannelKind: "whatsapp_official_business",
            CounterpartyHandle: "+436647916419",
            CounterpartyHash: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
            Status: "active",
            CreatedAtUtc: DateTimeOffset.UtcNow.AddMinutes(-10),
            UpdatedAtUtc: DateTimeOffset.UtcNow,
            LatestMessageId: "incoming-1"));
        fixture.Store.ExecutiveAssistantChannelMessages.Add(new ExecutiveAssistantChannelMessageState(
            MessageId: "incoming-1",
            ConversationId: "whatsapp_official_business:convo-1",
            ChannelKind: "whatsapp_official_business",
            Direction: "incoming",
            Text: "first",
            SafetyLabel: "safe",
            DeliveryStatus: "received",
            CreatedAtUtc: DateTimeOffset.UtcNow.AddMinutes(-5),
            CounterpartyHandle: "+436647916419",
            DeliveryRef: null,
            FailureReason: null,
            IdempotencyKey: null));
        fixture.Store.ExecutiveAssistantChannelMessages.Add(new ExecutiveAssistantChannelMessageState(
            MessageId: "outbound-1",
            ConversationId: "whatsapp_official_business:convo-1",
            ChannelKind: "whatsapp_official_business",
            Direction: "outbound",
            Text: "reply",
            SafetyLabel: "safe",
            DeliveryStatus: "sent",
            CreatedAtUtc: DateTimeOffset.UtcNow.AddMinutes(-1),
            CounterpartyHandle: "+436647916419",
            DeliveryRef: "delivery-1",
            FailureReason: null,
            IdempotencyKey: "id-1"));

        ExecutiveAssistantChannelConversationDto? conversation = fixture.Service.GetConversation(
            subjectId,
            "whatsapp_official_business",
            "whatsapp_official_business:convo-1");
        Assert.NotNull(conversation);
        Assert.Equal("whatsapp_official_business:convo-1", conversation.ConversationId);
        Assert.Equal(2, conversation.Messages.Count);
        Assert.Equal("incoming-1", conversation.Messages[0].MessageId);
    }

    [Fact]
    public async Task SendMessageAsync_marksDuplicateWhenSameIdempotencyKeyProvided()
    {
        using Fixture fixture = new();

        const string subjectId = "subject.ea.runner.dup";
        fixture.Accounts.EnsureUserWithStatus(subjectId, "Runner", "runner@example.com");
        fixture.Links.LinkChannel(new LinkChannelRequest(subjectId, "telegram_official_bot", "runnerbot", true));
        fixture.Links.LinkChannelToExecutiveAssistant("telegram_official_bot", new LinkChannelToExecutiveAssistantRequest(subjectId, null));

        const string idempotencyKey = "idempotent-1";
        ExecutiveAssistantChannelSendRequest request = new(
            MessageText: "hello",
            CounterpartyHandle: null,
            ConversationId: null,
            IdempotencyKey: idempotencyKey);

        ExecutiveAssistantChannelSendResult first = await fixture.Service.SendMessageAsync(subjectId, "telegram_official_bot", request, CancellationToken.None);
        ExecutiveAssistantChannelSendResult second = await fixture.Service.SendMessageAsync(subjectId, "telegram_official_bot", request, CancellationToken.None);

        Assert.False(first.Duplicate);
        Assert.True(second.Duplicate);
        Assert.Equal(first.MessageId, second.MessageId);
        Assert.Equal(first.ConversationId, second.ConversationId);
        Assert.Single(fixture.Store.ExecutiveAssistantChannelMessages);
    }

    [Fact]
    public async Task SendMessageAsync_returnsUnconfiguredStatusWhenEaNotConfigured()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_API_TOKEN"] = string.Empty,
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_PRINCIPAL_ID"] = string.Empty,
            ["CHUMMER_TEABLE_EXECUTIVE_ASSISTANT_CHANNEL_ENABLED"] = "false"
        });

        const string subjectId = "subject.ea.runner.offline";
        fixture.Accounts.EnsureUserWithStatus(subjectId, "Runner", "runner@example.com");
        fixture.Links.LinkChannel(new LinkChannelRequest(subjectId, "whatsapp_official_business", "+43 664 791 6419", true));
        fixture.Links.LinkChannelToExecutiveAssistant("whatsapp_official_business", new LinkChannelToExecutiveAssistantRequest(subjectId, null));

        ExecutiveAssistantChannelSendResult result = await fixture.Service.SendMessageAsync(
            subjectId,
            "whatsapp_official_business",
            new ExecutiveAssistantChannelSendRequest(
                MessageText: "testing offline",
                CounterpartyHandle: null,
                ConversationId: null,
                IdempotencyKey: null),
            CancellationToken.None);

        Assert.Equal("suppressed_ea_unconfigured", result.Status);
        Assert.Equal("ea_delivery_unconfigured", result.FailureReason);
        Assert.Single(fixture.Store.ExecutiveAssistantChannelMessages);
    }

    [Fact]
    public async Task SendMessageAsync_returnsUnconfiguredStatusWhenEaBaseUrlIsMock()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_BASE_URL"] = "http://support-progress-mock:8080",
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_PRINCIPAL_ID"] = "principal-runner",
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_BINDING_ID"] = "business-binding",
            ["CHUMMER_TEABLE_EXECUTIVE_ASSISTANT_CHANNEL_ENABLED"] = "false"
        });

        const string subjectId = "subject.ea.runner.mock";
        fixture.Accounts.EnsureUserWithStatus(subjectId, "Runner", "runner@example.com");
        fixture.Links.LinkChannel(new LinkChannelRequest(subjectId, "whatsapp_official_business", "+43 664 791 6419", true));
        fixture.Links.LinkChannelToExecutiveAssistant("whatsapp_official_business", new LinkChannelToExecutiveAssistantRequest(subjectId, null));

        ExecutiveAssistantChannelSendResult result = await fixture.Service.SendMessageAsync(
            subjectId,
            "whatsapp_official_business",
            new ExecutiveAssistantChannelSendRequest(
                MessageText: "testing mock route",
                CounterpartyHandle: null,
                ConversationId: null,
                IdempotencyKey: null),
            CancellationToken.None);

        Assert.Equal("suppressed_ea_unconfigured", result.Status);
        Assert.Equal("ea_delivery_unconfigured", result.FailureReason);
        Assert.DoesNotContain(fixture.Handler.Requests, static item => item.Path == "/v1/tools/execute");
    }

    [Fact]
    public async Task SendMessageAsync_prefersWhatsappWebBindingWhenConfigured()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_PRINCIPAL_ID"] = "principal-runner",
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_BINDING_ID"] = "business-binding",
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_WEB_BINDING_ID"] = "web-session-binding",
            ["CHUMMER_TEABLE_EXECUTIVE_ASSISTANT_CHANNEL_ENABLED"] = "false"
        });

        const string subjectId = "subject.ea.runner.whatsapp.web";
        fixture.Accounts.EnsureUserWithStatus(subjectId, "Runner", "runner@example.com");
        fixture.Links.LinkChannel(new LinkChannelRequest(subjectId, "whatsapp_official_business", "+43 664 791 6419", true));
        fixture.Links.LinkChannelToExecutiveAssistant("whatsapp_official_business", new LinkChannelToExecutiveAssistantRequest(subjectId, null));

        ExecutiveAssistantChannelSendResult result = await fixture.Service.SendMessageAsync(
            subjectId,
            "whatsapp_official_business",
            new ExecutiveAssistantChannelSendRequest(
                MessageText: "testing whatsapp web",
                CounterpartyHandle: null,
                ConversationId: null,
                IdempotencyKey: "wa-web-test"),
            CancellationToken.None);

        Assert.Equal("sent", result.Status);
        RecordedRequest request = Assert.Single(fixture.Handler.Requests, item => item.Method == HttpMethod.Post && item.Path == "/v1/tools/execute");
        using JsonDocument json = JsonDocument.Parse(request.Body);
        JsonElement payload = json.RootElement.GetProperty("payload_json");
        Assert.Equal("web-session-binding", payload.GetProperty("binding_id").GetString());
        Assert.Equal("whatsapp", payload.GetProperty("channel").GetString());
        Assert.Equal("436647916419", payload.GetProperty("recipient").GetString());

        JsonElement metadata = payload.GetProperty("metadata");
        Assert.Equal("chummer_hub_account_channel", metadata.GetProperty("source_service").GetString());
        Assert.Equal("whatsapp_official_business", metadata.GetProperty("account_channel_kind").GetString());
        Assert.Equal("whatsapp", metadata.GetProperty("delivery_channel").GetString());
        Assert.Equal("whatsapp_web_session", metadata.GetProperty("delivery_transport").GetString());
    }

    [Fact]
    public void IngestIncomingMessage_persistsIncomingMessageAndConversationForSubject()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_BASE_URL"] = "https://ea.test",
        });

        const string subjectId = "subject.ea.incoming";
        fixture.Accounts.EnsureUserWithStatus(subjectId, "Runner", "runner@example.com");
        fixture.Links.LinkChannel(new LinkChannelRequest(subjectId, "whatsapp_official_business", "+43 664 791 6419", true));
        fixture.Links.LinkChannelToExecutiveAssistant("whatsapp_official_business", new LinkChannelToExecutiveAssistantRequest(subjectId, null));

        ExecutiveAssistantChannelMessageDto message = fixture.Service.IngestIncomingMessage(
            "whatsapp_official_business",
            new ExecutiveAssistantChannelIncomingMessageRequest(
                SubjectId: subjectId,
                RecipientHandle: null,
                CounterpartyHandle: "+43664123455",
                MessageText: "Willkommen zurück",
                MessageId: null));

        Assert.Equal("incoming", message.Direction);
        Assert.Equal("received", message.DeliveryStatus);
        Assert.NotNull(message.MessageId);
        Assert.Single(fixture.Store.ExecutiveAssistantChannelConversations);
        Assert.Single(fixture.Store.ExecutiveAssistantChannelMessages);
        Assert.Equal("whatsapp_official_business", message.ChannelKind);
    }

    [Fact]
    public void IngestIncomingMessage_routesWhatsappByEaLinkedCounterpartyWhenSubjectMissing()
    {
        using Fixture fixture = new();

        const string subjectId = "subject.ea.incoming.whatsapp.counterparty";
        fixture.Accounts.EnsureUserWithStatus(subjectId, "Runner", "runner@example.com");
        fixture.Links.LinkChannel(new LinkChannelRequest(subjectId, "whatsapp_official_business", "+43 664 791 6419", true));
        fixture.Links.LinkChannelToExecutiveAssistant("whatsapp_official_business", new LinkChannelToExecutiveAssistantRequest(subjectId, null));

        ExecutiveAssistantChannelMessageDto message = fixture.Service.IngestIncomingMessage(
            "whatsapp_official_business",
            new ExecutiveAssistantChannelIncomingMessageRequest(
                SubjectId: null,
                RecipientHandle: null,
                CounterpartyHandle: "+43 664 791 6419",
                MessageText: "Can Chummer call me back here?",
                MessageId: "wa-message-1"));

        Assert.Equal("incoming", message.Direction);
        Assert.Equal("received", message.DeliveryStatus);
        Assert.Equal("wa-message-1", message.MessageId);
        Assert.Single(fixture.Store.ExecutiveAssistantChannelConversations);
        Assert.Single(fixture.Store.ExecutiveAssistantChannelMessages);
        Assert.Equal("436647916419", fixture.Store.ExecutiveAssistantChannelConversations[0].CounterpartyHandle);
    }

    [Fact]
    public void IngestIncomingMessage_routesWhatsappByRecipientHandleWhenCounterpartyFieldCarriesBusinessNumber()
    {
        using Fixture fixture = new();

        const string subjectId = "subject.ea.incoming.whatsapp.recipient";
        fixture.Accounts.EnsureUserWithStatus(subjectId, "Runner", "runner@example.com");
        fixture.Links.LinkChannel(new LinkChannelRequest(subjectId, "whatsapp_official_business", "+43 664 791 6419", true));
        fixture.Links.LinkChannelToExecutiveAssistant("whatsapp_official_business", new LinkChannelToExecutiveAssistantRequest(subjectId, null));

        ExecutiveAssistantChannelMessageDto message = fixture.Service.IngestIncomingMessage(
            "whatsapp_official_business",
            new ExecutiveAssistantChannelIncomingMessageRequest(
                SubjectId: null,
                RecipientHandle: "+43 664 791 6419",
                CounterpartyHandle: "+43 700 000 0000",
                MessageText: "These samples are fine now",
                MessageId: "wa-message-recipient-1"));

        Assert.Equal("incoming", message.Direction);
        Assert.Equal("received", message.DeliveryStatus);
        Assert.Equal("wa-message-recipient-1", message.MessageId);
        Assert.Single(fixture.Store.ExecutiveAssistantChannelConversations);
        Assert.Single(fixture.Store.ExecutiveAssistantChannelMessages);
        Assert.Equal("436647916419", fixture.Store.ExecutiveAssistantChannelConversations[0].CounterpartyHandle);
    }

    [Fact]
    public void IngestIncomingMessage_rejectsAmbiguousRouteWhenCounterpartyAndRecipientMatchDifferentUsers()
    {
        using Fixture fixture = new();

        const string subjectA = "subject.ea.incoming.whatsapp.ambiguous.a";
        const string subjectB = "subject.ea.incoming.whatsapp.ambiguous.b";
        fixture.Accounts.EnsureUserWithStatus(subjectA, "Runner A", "runner-a@example.com");
        fixture.Accounts.EnsureUserWithStatus(subjectB, "Runner B", "runner-b@example.com");
        fixture.Links.LinkChannel(new LinkChannelRequest(subjectA, "whatsapp_official_business", "+43 664 791 6419", true));
        fixture.Links.LinkChannel(new LinkChannelRequest(subjectB, "whatsapp_official_business", "+43 664 111 2222", true));
        fixture.Links.LinkChannelToExecutiveAssistant("whatsapp_official_business", new LinkChannelToExecutiveAssistantRequest(subjectA, null));
        fixture.Links.LinkChannelToExecutiveAssistant("whatsapp_official_business", new LinkChannelToExecutiveAssistantRequest(subjectB, null));

        InvalidOperationException ex = Assert.Throws<InvalidOperationException>(() => fixture.Service.IngestIncomingMessage(
            "whatsapp_official_business",
            new ExecutiveAssistantChannelIncomingMessageRequest(
                SubjectId: null,
                RecipientHandle: "+43 664 111 2222",
                CounterpartyHandle: "+43 664 791 6419",
                MessageText: "route this",
                MessageId: "wa-message-ambiguous-1")));

        Assert.Contains("Ambiguous incoming whatsapp_official_business routing", ex.Message, StringComparison.Ordinal);
    }

    [Fact]
    public void IngestIncomingMessage_requiresRoutableIncomingTarget()
    {
        using Fixture fixture = new();

        Assert.Throws<ArgumentException>(() => fixture.Service.IngestIncomingMessage(
            "telegram_official_bot",
            new ExecutiveAssistantChannelIncomingMessageRequest(
                SubjectId: null,
                RecipientHandle: null,
                CounterpartyHandle: "+43 664 791 6419",
                MessageText: "Hi",
                MessageId: null)));
    }

    [Fact]
    public void IngestIncomingMessage_dedupesRecentWebhookRetryWhenProviderMessageIdIsMissing()
    {
        using Fixture fixture = new();

        const string subjectId = "subject.ea.incoming.retry";
        DateTimeOffset receivedAt = DateTimeOffset.Parse("2026-06-22T16:10:00Z");
        fixture.Accounts.EnsureUserWithStatus(subjectId, "Runner", "runner@example.com");
        fixture.Links.LinkChannel(new LinkChannelRequest(subjectId, "whatsapp_official_business", "+43 664 791 6419", true));
        fixture.Links.LinkChannelToExecutiveAssistant("whatsapp_official_business", new LinkChannelToExecutiveAssistantRequest(subjectId, null));

        ExecutiveAssistantChannelMessageDto first = fixture.Service.IngestIncomingMessage(
            "whatsapp_official_business",
            new ExecutiveAssistantChannelIncomingMessageRequest(
                SubjectId: subjectId,
                RecipientHandle: null,
                CounterpartyHandle: "+43 664 123 455",
                MessageText: "Ping mich bitte spaeter an.",
                MessageId: null,
                ConversationId: null,
                ReceivedAtUtc: receivedAt));

        ExecutiveAssistantChannelMessageDto second = fixture.Service.IngestIncomingMessage(
            "whatsapp_official_business",
            new ExecutiveAssistantChannelIncomingMessageRequest(
                SubjectId: subjectId,
                RecipientHandle: null,
                CounterpartyHandle: "+43 664 123 455",
                MessageText: "Ping mich bitte spaeter an.",
                MessageId: null,
                ConversationId: null,
                ReceivedAtUtc: receivedAt.AddSeconds(20)));

        Assert.Equal(first.MessageId, second.MessageId);
        Assert.Single(fixture.Store.ExecutiveAssistantChannelMessages);
    }

    [Fact]
    public void IngestIncomingMessage_keepsDistinctRepeatedMessagesOutsideRetryWindowWhenProviderMessageIdIsMissing()
    {
        using Fixture fixture = new();

        const string subjectId = "subject.ea.incoming.repeat";
        DateTimeOffset receivedAt = DateTimeOffset.Parse("2026-06-22T16:10:00Z");
        fixture.Accounts.EnsureUserWithStatus(subjectId, "Runner", "runner@example.com");
        fixture.Links.LinkChannel(new LinkChannelRequest(subjectId, "whatsapp_official_business", "+43 664 791 6419", true));
        fixture.Links.LinkChannelToExecutiveAssistant("whatsapp_official_business", new LinkChannelToExecutiveAssistantRequest(subjectId, null));

        ExecutiveAssistantChannelMessageDto first = fixture.Service.IngestIncomingMessage(
            "whatsapp_official_business",
            new ExecutiveAssistantChannelIncomingMessageRequest(
                SubjectId: subjectId,
                RecipientHandle: null,
                CounterpartyHandle: "+43 664 123 455",
                MessageText: "Bist du da?",
                MessageId: null,
                ConversationId: null,
                ReceivedAtUtc: receivedAt));

        ExecutiveAssistantChannelMessageDto second = fixture.Service.IngestIncomingMessage(
            "whatsapp_official_business",
            new ExecutiveAssistantChannelIncomingMessageRequest(
                SubjectId: subjectId,
                RecipientHandle: null,
                CounterpartyHandle: "+43 664 123 455",
                MessageText: "Bist du da?",
                MessageId: null,
                ConversationId: null,
                ReceivedAtUtc: receivedAt.AddMinutes(3)));

        Assert.NotEqual(first.MessageId, second.MessageId);
        Assert.Equal(2, fixture.Store.ExecutiveAssistantChannelMessages.Count);
    }

    [Fact]
    public async Task TeableSyncAll_projectsStoredExecutiveAssistantConversationTranscript()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_TEABLE_EXECUTIVE_ASSISTANT_CHANNEL_ENABLED"] = "true",
            ["CHUMMER_TEABLE_EXECUTIVE_ASSISTANT_CHANNEL_API_KEY"] = "teable-key",
            ["CHUMMER_TEABLE_EXECUTIVE_ASSISTANT_CHANNEL_API_BASE_URL"] = "https://app.teable.ai/api",
            ["CHUMMER_TEABLE_EXECUTIVE_ASSISTANT_CHANNEL_BASE_ID"] = "base-demo"
        });

        const string subjectId = "subject.ea.teable.sync";
        fixture.Accounts.EnsureUserWithStatus(subjectId, "Runner", "runner@example.com");
        fixture.Links.LinkChannel(new LinkChannelRequest(subjectId, "whatsapp_official_business", "+43 664 791 6419", true));
        fixture.Links.LinkChannelToExecutiveAssistant("whatsapp_official_business", new LinkChannelToExecutiveAssistantRequest(subjectId, null));
        string userId = fixture.Accounts.EnsureUser(subjectId).UserId;

        lock (fixture.Store.Gate)
        {
            fixture.Store.ExecutiveAssistantChannelConversations.Add(new ExecutiveAssistantChannelConversationState(
                ConversationId: "whatsapp_official_business:sync-1",
                UserId: userId,
                ChannelKind: "whatsapp_official_business",
                CounterpartyHandle: "436647916419",
                CounterpartyHash: new string('a', 64),
                Status: "active",
                CreatedAtUtc: DateTimeOffset.Parse("2026-06-22T10:00:00Z"),
                UpdatedAtUtc: DateTimeOffset.Parse("2026-06-22T10:06:00Z"),
                LatestMessageId: "eam-2"));
            fixture.Store.ExecutiveAssistantChannelMessages.Add(new ExecutiveAssistantChannelMessageState(
                MessageId: "eam-1",
                ConversationId: "whatsapp_official_business:sync-1",
                ChannelKind: "whatsapp_official_business",
                Direction: "incoming",
                Text: "Kannst du mir helfen?",
                SafetyLabel: "safe",
                DeliveryStatus: "received",
                CreatedAtUtc: DateTimeOffset.Parse("2026-06-22T10:01:00Z"),
                CounterpartyHandle: "436647916419",
                DeliveryRef: null,
                FailureReason: null,
                IdempotencyKey: null));
            fixture.Store.ExecutiveAssistantChannelMessages.Add(new ExecutiveAssistantChannelMessageState(
                MessageId: "eam-2",
                ConversationId: "whatsapp_official_business:sync-1",
                ChannelKind: "whatsapp_official_business",
                Direction: "outbound",
                Text: "Ja, schick mir die Datei.",
                SafetyLabel: "safe",
                DeliveryStatus: "sent",
                CreatedAtUtc: DateTimeOffset.Parse("2026-06-22T10:05:00Z"),
                CounterpartyHandle: "436647916419",
                DeliveryRef: "delivery-1",
                FailureReason: null,
                IdempotencyKey: "idem-1"));
            fixture.Store.PersistLocked();
        }

        TeableExecutiveAssistantChannelSyncResult result = await fixture.Teable.SyncAllAsync();

        Assert.Equal("passed", result.State);
        Assert.Equal(1, result.SyncedCount);
        RecordedRequest createTable = Assert.Single(
            fixture.Handler.Requests,
            static item => item.Method == HttpMethod.Post && item.Path == "/api/base/base-demo/table/");
        Assert.DoesNotContain("\"unique\"", createTable.Body, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("\"notNull\"", createTable.Body, StringComparison.OrdinalIgnoreCase);
        RecordedRequest createRecord = Assert.Single(
            fixture.Handler.Requests,
            static item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_ea_channel/record");
        using JsonDocument created = JsonDocument.Parse(createRecord.Body);
        JsonElement fields = created.RootElement.GetProperty("records")[0].GetProperty("fields");
        Assert.Equal("whatsapp_official_business", fields.GetProperty("Channel Kind").GetString());
        Assert.Equal("outbound", fields.GetProperty("Latest Direction").GetString());
        Assert.Contains("incoming: Kannst du mir helfen?", fields.GetProperty("Transcript").GetString(), StringComparison.Ordinal);
        Assert.Contains("outbound: Ja, schick mir die Datei.", fields.GetProperty("Transcript").GetString(), StringComparison.Ordinal);

        TeableExecutiveAssistantChannelDashboard dashboard = fixture.Teable.GetDashboard();
        Assert.Equal("ready", dashboard.State);
        Assert.Single(dashboard.Rows);
        Assert.Equal("sent", dashboard.Rows[0].LatestDeliveryStatus);
    }

    [Fact]
    public async Task SendMessageAsync_autosyncsExecutiveAssistantConversationToTeable()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_BASE_URL"] = "https://ea.test",
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_API_TOKEN"] = "ea-token",
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_PRINCIPAL_ID"] = "principal-runner",
            ["CHUMMER_EA_CHANNEL_MESSAGING_EA_WHATSAPP_BINDING_ID"] = "business-binding",
            ["CHUMMER_TEABLE_EXECUTIVE_ASSISTANT_CHANNEL_ENABLED"] = "true",
            ["CHUMMER_TEABLE_EXECUTIVE_ASSISTANT_CHANNEL_API_KEY"] = "teable-key",
            ["CHUMMER_TEABLE_EXECUTIVE_ASSISTANT_CHANNEL_API_BASE_URL"] = "https://app.teable.ai/api",
            ["CHUMMER_TEABLE_EXECUTIVE_ASSISTANT_CHANNEL_BASE_ID"] = "base-demo"
        });

        const string subjectId = "subject.ea.teable.send";
        fixture.Accounts.EnsureUserWithStatus(subjectId, "Runner", "runner@example.com");
        fixture.Links.LinkChannel(new LinkChannelRequest(subjectId, "whatsapp_official_business", "+43 664 791 6419", true));
        fixture.Links.LinkChannelToExecutiveAssistant("whatsapp_official_business", new LinkChannelToExecutiveAssistantRequest(subjectId, null));

        ExecutiveAssistantChannelSendResult result = await fixture.Service.SendMessageAsync(
            subjectId,
            "whatsapp_official_business",
            new ExecutiveAssistantChannelSendRequest("Hier ist die naechste Probe.", CounterpartyHandle: null, IdempotencyKey: "autosync-send-1"),
            CancellationToken.None);

        Assert.Equal("sent", result.Status);
        await fixture.WaitForRequestAsync(HttpMethod.Post, "/api/table/tbl_ea_channel/record");

        RecordedRequest createRecord = Assert.Single(
            fixture.Handler.Requests,
            static item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_ea_channel/record");
        using JsonDocument created = JsonDocument.Parse(createRecord.Body);
        JsonElement fields = created.RootElement.GetProperty("records")[0].GetProperty("fields");
        Assert.Equal("sent", fields.GetProperty("Latest Delivery Status").GetString());
        Assert.Contains("outbound: Hier ist die naechste Probe.", fields.GetProperty("Transcript").GetString(), StringComparison.Ordinal);
    }

    [Fact]
    public async Task IngestIncomingMessage_autosyncsExecutiveAssistantConversationToTeable()
    {
        using Fixture fixture = new(new Dictionary<string, string?>
        {
            ["CHUMMER_TEABLE_EXECUTIVE_ASSISTANT_CHANNEL_ENABLED"] = "true",
            ["CHUMMER_TEABLE_EXECUTIVE_ASSISTANT_CHANNEL_API_KEY"] = "teable-key",
            ["CHUMMER_TEABLE_EXECUTIVE_ASSISTANT_CHANNEL_API_BASE_URL"] = "https://app.teable.ai/api",
            ["CHUMMER_TEABLE_EXECUTIVE_ASSISTANT_CHANNEL_BASE_ID"] = "base-demo"
        });

        const string subjectId = "subject.ea.teable.ingest";
        fixture.Accounts.EnsureUserWithStatus(subjectId, "Runner", "runner@example.com");
        fixture.Links.LinkChannel(new LinkChannelRequest(subjectId, "whatsapp_official_business", "+43 664 791 6419", true));
        fixture.Links.LinkChannelToExecutiveAssistant("whatsapp_official_business", new LinkChannelToExecutiveAssistantRequest(subjectId, null));

        ExecutiveAssistantChannelMessageDto message = fixture.Service.IngestIncomingMessage(
            "whatsapp_official_business",
            new ExecutiveAssistantChannelIncomingMessageRequest(
                SubjectId: subjectId,
                RecipientHandle: null,
                CounterpartyHandle: "+43 664 123 455",
                MessageText: "Das war die richtige Datei.",
                MessageId: "wa-msg-sync-1"));

        Assert.Equal("wa-msg-sync-1", message.MessageId);
        await fixture.WaitForRequestAsync(HttpMethod.Post, "/api/table/tbl_ea_channel/record");

        RecordedRequest createRecord = Assert.Single(
            fixture.Handler.Requests,
            static item => item.Method == HttpMethod.Post && item.Path == "/api/table/tbl_ea_channel/record");
        using JsonDocument created = JsonDocument.Parse(createRecord.Body);
        JsonElement fields = created.RootElement.GetProperty("records")[0].GetProperty("fields");
        Assert.Equal("incoming", fields.GetProperty("Latest Direction").GetString());
        Assert.Equal("received", fields.GetProperty("Latest Delivery Status").GetString());
        Assert.Contains("incoming: Das war die richtige Datei.", fields.GetProperty("Transcript").GetString(), StringComparison.Ordinal);
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture(IReadOnlyDictionary<string, string?>? overrides = null)
        {
            _root = Path.Combine(Path.GetTempPath(), "executive-assistant-channel-messaging-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);

            var values = new Dictionary<string, string?>
            {
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community-store.json"),
                ["CHUMMER_EA_CHANNEL_MESSAGING_EA_BASE_URL"] = "https://ea.test",
                ["CHUMMER_TEABLE_EXECUTIVE_ASSISTANT_CHANNEL_ENABLED"] = "false"
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
            Accounts = new AccountService(Store);
            Links = new IdentityLinkService(Store, Accounts);
            Handler = new FakeHandler();
            Teable = new TeableExecutiveAssistantChannelService(
                Store,
                Configuration,
                new StaticHttpClientFactory(new HttpClient(Handler)),
                NullLogger<TeableExecutiveAssistantChannelService>.Instance);
            Service = new ExecutiveAssistantChannelMessagingService(
                new HttpClient(Handler),
                Store,
                Accounts,
                Configuration,
                NullLogger<ExecutiveAssistantChannelMessagingService>.Instance,
                Teable);
        }

        public IConfiguration Configuration { get; }
        public CommunityStore Store { get; }
        public AccountService Accounts { get; }
        public IdentityLinkService Links { get; }
        public TeableExecutiveAssistantChannelService Teable { get; }
        public ExecutiveAssistantChannelMessagingService Service { get; }
        public FakeHandler Handler { get; }

        public async Task WaitForRequestAsync(HttpMethod method, string path, int attempts = 40)
        {
            for (int i = 0; i < attempts; i++)
            {
                if (Handler.Requests.Any(item => item.Method == method && item.Path == path))
                {
                    return;
                }

                await Task.Delay(25);
            }

            throw new TimeoutException($"Timed out waiting for {method} {path}.");
        }

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

    private sealed class FakeHandler : System.Net.Http.HttpMessageHandler
    {
        private readonly HashSet<string> _fields = new(StringComparer.OrdinalIgnoreCase);

        public List<RecordedRequest> Requests { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            string path = request.RequestUri?.PathAndQuery ?? string.Empty;
            string body = request.Content is null ? string.Empty : await request.Content.ReadAsStringAsync(cancellationToken);
            Requests.Add(new RecordedRequest(request.Method, path, body));

            if (request.Method == HttpMethod.Post && path == "/v1/tools/execute")
            {
                return Json(HttpStatusCode.OK, """{"target_ref":"ea-target-1"}""");
            }

            if (request.Method == HttpMethod.Get && path == "/api/base/base-demo/table")
            {
                return Json(HttpStatusCode.OK, "[]");
            }

            if (request.Method == HttpMethod.Post && path == "/api/base/base-demo/table/")
            {
                return Json(HttpStatusCode.Created, """{"id":"tbl_ea_channel"}""");
            }

            if (request.Method == HttpMethod.Get && path.StartsWith("/api/table/tbl_ea_channel/field", StringComparison.Ordinal))
            {
                string payload = JsonSerializer.Serialize(_fields.Select(static name => new { id = $"fld_{name.Replace(" ", "_", StringComparison.Ordinal)}", name }).ToArray());
                return Json(HttpStatusCode.OK, payload);
            }

            if (request.Method == HttpMethod.Post && path == "/api/table/tbl_ea_channel/field")
            {
                using JsonDocument document = JsonDocument.Parse(body);
                string name = document.RootElement.GetProperty("name").GetString() ?? string.Empty;
                if (!string.IsNullOrWhiteSpace(name))
                {
                    _fields.Add(name);
                }

                return Json(HttpStatusCode.Created, $$"""{"id":"fld_{{_fields.Count}}","name":{{JsonSerializer.Serialize(name)}}}""");
            }

            if (request.Method == HttpMethod.Get && path.StartsWith("/api/table/tbl_ea_channel/record?", StringComparison.Ordinal))
            {
                return Json(HttpStatusCode.OK, """{"records":[]}""");
            }

            if (request.Method == HttpMethod.Post && path == "/api/table/tbl_ea_channel/record")
            {
                return Json(HttpStatusCode.Created, """{"records":[{"id":"rec_ea_channel"}]}""");
            }

            return Json(HttpStatusCode.NotFound, $$"""{"path":{{JsonSerializer.Serialize(path)}}}""");
        }

        private static HttpResponseMessage Json(HttpStatusCode statusCode, string payload)
            => new(statusCode)
            {
                Content = new StringContent(payload, Encoding.UTF8, "application/json")
            };
    }

    private sealed record RecordedRequest(HttpMethod Method, string Path, string Body);
}
