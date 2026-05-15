using System.Net;
using System.Text.Json;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class BlackLedgerTickNewsTests
{
    [Fact]
    public void BlackLedgerNewsRecipientResolver_only_user_preview_fallback_resolves_exactly_one_user()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"] = BlackLedgerNewsRecipientResolver.SubscribedOrOnlyUserPreviewFallbackPolicy,
            });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            HubUserDto user = accounts.EnsureUserWithStatus("subject.ledger.one", "Ledger One", "ledger-one@example.com").User;
            BlackLedgerNewsRecipientResolver resolver = new(store, configuration);

            BlackLedgerNewsRecipientResolution resolution = resolver.Resolve("emerald-sprawl-prelude");

            Assert.Equal("resolved", resolution.Status);
            Assert.Single(resolution.Recipients);
            Assert.Equal(user.UserId, resolution.Recipients[0].RecipientUserId);
            Assert.Equal("only_user_preview_fallback", resolution.Recipients[0].Source);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public void BlackLedgerNewsRecipientResolver_suppresses_when_multiple_users_without_subscription()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"] = BlackLedgerNewsRecipientResolver.SubscribedOrOnlyUserPreviewFallbackPolicy,
            });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            _ = accounts.EnsureUserWithStatus("subject.ledger.one", "Ledger One", "ledger-one@example.com").User;
            _ = accounts.EnsureUserWithStatus("subject.ledger.two", "Ledger Two", "ledger-two@example.com").User;
            BlackLedgerNewsRecipientResolver resolver = new(store, configuration);

            BlackLedgerNewsRecipientResolution resolution = resolver.Resolve("emerald-sprawl-prelude");

            Assert.Equal("suppressed_multiple_users_no_subscription", resolution.Status);
            Assert.Empty(resolution.Recipients);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task BlackLedgerTickNews_sends_to_subscribed_users()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            var requests = new List<CapturedRequest>();
            using var http = new HttpClient(new CapturingHandler(requests, HttpStatusCode.OK, """{"target_ref":"ea-delivery-2"}"""));
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED"] = "true",
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"] = BlackLedgerNewsRecipientResolver.SubscribedOnlyPolicy,
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN"] = "ea-token",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID"] = "principal-1",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID"] = "binding-1",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_BASE_URL"] = "https://ea.test",
                ["CHUMMER_BLACK_LEDGER_NEWS_HASH_SALT"] = "salt-1",
            });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            HubUserDto subscribed = accounts.EnsureUserWithStatus("subject.ledger.subscribed", "Ledger One", "ledger-one@example.com").User;
            HubUserDto other = accounts.EnsureUserWithStatus("subject.ledger.other", "Ledger Two", "ledger-two@example.com").User;
            store.UserExperienceByUserId[subscribed.UserId] = new HubUserExperienceDto(
                subscribed.UserId,
                LaneInterests: Array.Empty<string>(),
                FollowHorizons: false,
                BetaInterest: false,
                OnboardingCompleted: true,
                OnboardingCompletedAtUtc: DateTimeOffset.UtcNow,
                UpdatedAtUtc: DateTimeOffset.UtcNow,
                BlackLedgerNewsEmail: true,
                BlackLedgerWorldsFollowed: ["emerald-sprawl-prelude"]);
            store.UserExperienceByUserId[other.UserId] = new HubUserExperienceDto(
                other.UserId,
                LaneInterests: Array.Empty<string>(),
                FollowHorizons: false,
                BetaInterest: false,
                OnboardingCompleted: true,
                OnboardingCompletedAtUtc: DateTimeOffset.UtcNow,
                UpdatedAtUtc: DateTimeOffset.UtcNow);

            BlackLedgerTickNewsNotificationService service = new(
                http,
                store,
                configuration,
                new BlackLedgerNewsRecipientResolver(store, configuration),
                NullLogger<BlackLedgerTickNewsNotificationService>.Instance);

            BlackLedgerTickNewsNotificationBatchReceipt batch = await service.NotifyTickNewsAsync(
                CreateTickEvent(),
                dryRun: false,
                policyOverride: null,
                CancellationToken.None);

            Assert.Equal("sent", batch.Status);
            Assert.Single(batch.Receipts);
            Assert.Equal("sent", batch.Receipts[0].Status);
            Assert.Equal(subscribed.UserId, batch.Receipts[0].RecipientUserId);
            CapturedRequest request = Assert.Single(requests);
            using JsonDocument payload = JsonDocument.Parse(request.Body);
            Assert.Equal("connector.dispatch", payload.RootElement.GetProperty("tool_name").GetString());
            Assert.Equal("delivery.send", payload.RootElement.GetProperty("action_kind").GetString());
            JsonElement payloadJson = payload.RootElement.GetProperty("payload_json");
            Assert.Equal("ledger-one@example.com", payloadJson.GetProperty("recipient").GetString());
            Assert.Equal("binding-1", payloadJson.GetProperty("binding_id").GetString());
            Assert.True(payloadJson.TryGetProperty("idempotency_key", out _));
            Assert.False(request.Body.Contains("ledger-two@example.com", StringComparison.Ordinal));
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task BlackLedgerTickNews_suppresses_when_email_delivery_disabled()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            using var http = new HttpClient(new CapturingHandler(new List<CapturedRequest>(), HttpStatusCode.OK, """{"target_ref":"ea-delivery-2"}"""));
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"] = BlackLedgerNewsRecipientResolver.SubscribedOrOnlyUserPreviewFallbackPolicy,
            });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            _ = accounts.EnsureUserWithStatus("subject.ledger.one", "Ledger One", "ledger-one@example.com").User;

            BlackLedgerTickNewsNotificationService service = new(
                http,
                store,
                configuration,
                new BlackLedgerNewsRecipientResolver(store, configuration),
                NullLogger<BlackLedgerTickNewsNotificationService>.Instance);

            BlackLedgerTickNewsNotificationBatchReceipt batch = await service.NotifyTickNewsAsync(
                CreateTickEvent(),
                dryRun: false,
                policyOverride: null,
                CancellationToken.None);

            Assert.Equal("suppressed_disabled", batch.Status);
            Assert.Single(batch.Receipts);
            Assert.Equal("suppressed_disabled", batch.Receipts[0].Status);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task BlackLedgerTickNews_privacy_gate_blocks_private_data()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            using var http = new HttpClient(new CapturingHandler(new List<CapturedRequest>(), HttpStatusCode.OK, """{"target_ref":"ea-delivery-2"}"""));
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED"] = "true",
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"] = BlackLedgerNewsRecipientResolver.SubscribedOrOnlyUserPreviewFallbackPolicy,
            });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            _ = accounts.EnsureUserWithStatus("subject.ledger.one", "Ledger One", "ledger-one@example.com").User;
            BlackLedgerTickNewsNotificationService service = new(
                http,
                store,
                configuration,
                new BlackLedgerNewsRecipientResolver(store, configuration),
                NullLogger<BlackLedgerTickNewsNotificationService>.Instance);

            BlackLedgerTickNewsNotificationBatchReceipt batch = await service.NotifyTickNewsAsync(
                CreateTickEvent(publicSummary: "private_campaign pressure leaked"),
                dryRun: false,
                policyOverride: null,
                CancellationToken.None);

            Assert.Equal("suppressed_privacy_failed", batch.Status);
            Assert.Single(batch.Receipts);
            Assert.Equal("suppressed_privacy_failed", batch.Receipts[0].Status);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task BlackLedgerTickNews_idempotency_prevents_duplicate_send_and_preseeded_turn_one_can_build_catchup_email()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            var requests = new List<CapturedRequest>();
            using var http = new HttpClient(new CapturingHandler(requests, HttpStatusCode.OK, """{"target_ref":"ea-delivery-2"}"""));
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED"] = "true",
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"] = BlackLedgerNewsRecipientResolver.SubscribedOrOnlyUserPreviewFallbackPolicy,
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN"] = "ea-token",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID"] = "principal-1",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID"] = "binding-1",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_BASE_URL"] = "https://ea.test",
                ["CHUMMER_BLACK_LEDGER_NEWS_HASH_SALT"] = "salt-1",
            });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            _ = accounts.EnsureUserWithStatus("subject.ledger.one", "Ledger One", "ledger-one@example.com").User;

            BlackLedgerTickNewsNotificationService service = new(
                http,
                store,
                configuration,
                new BlackLedgerNewsRecipientResolver(store, configuration),
                NullLogger<BlackLedgerTickNewsNotificationService>.Instance);

            BlackLedgerWorldTickNewsEvent seeded = service.BuildSeededWorldEvent("emerald-sprawl-prelude", 1, "https://chummer.run")
                ?? throw new InvalidOperationException("expected preseeded turn-one event");
            Assert.Equal(1, seeded.ToTurn);
            Assert.Equal("ledger_tick_0001_preseeded", seeded.TickReceiptId);

            BlackLedgerTickNewsNotificationBatchReceipt first = await service.NotifyTickNewsAsync(seeded, false, null, CancellationToken.None);
            BlackLedgerTickNewsNotificationBatchReceipt second = await service.NotifyTickNewsAsync(seeded, false, null, CancellationToken.None);

            Assert.Equal("sent", first.Status);
            Assert.True(second.Duplicate);
            Assert.Equal("duplicate", second.Status);
            Assert.Single(requests);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task BlackLedgerTickNews_accepts_delivery_id_from_output_json()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            var requests = new List<CapturedRequest>();
            using var http = new HttpClient(new CapturingHandler(requests, HttpStatusCode.OK, """{"output_json":{"delivery_id":"ea-delivery-output-json"}}"""));
            IConfiguration configuration = BuildConfiguration(tempRoot, new Dictionary<string, string?>
            {
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_ENABLED"] = "true",
                ["CHUMMER_BLACK_LEDGER_NEWS_EMAIL_POLICY"] = BlackLedgerNewsRecipientResolver.SubscribedOrOnlyUserPreviewFallbackPolicy,
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_API_TOKEN"] = "ea-token",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_PRINCIPAL_ID"] = "principal-1",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_BINDING_ID"] = "binding-1",
                ["CHUMMER_BLACK_LEDGER_NEWS_EA_BASE_URL"] = "https://ea.test",
            });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            _ = accounts.EnsureUserWithStatus("subject.ledger.one", "Ledger One", "ledger-one@example.com").User;

            BlackLedgerTickNewsNotificationService service = new(
                http,
                store,
                configuration,
                new BlackLedgerNewsRecipientResolver(store, configuration),
                NullLogger<BlackLedgerTickNewsNotificationService>.Instance);

            BlackLedgerTickNewsNotificationBatchReceipt batch = await service.NotifyTickNewsAsync(CreateTickEvent(), false, null, CancellationToken.None);

            Assert.Equal("sent", batch.Status);
            Assert.Single(batch.Receipts);
            Assert.Equal("ea-delivery-output-json", batch.Receipts[0].DeliveryRef);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    private static BlackLedgerWorldTickNewsEvent CreateTickEvent(string publicSummary = "Debt heat moved, but the lane stayed public-safe.")
        => new(
            WorldId: "emerald-sprawl-prelude",
            WorldName: "Emerald Sprawl: First Pressure",
            FromTurn: 0,
            ToTurn: 1,
            TickReceiptId: "ledger_tick_0001_preseeded",
            NewsId: "news_0001",
            PublicHeadline: "Black Ledger turn 1: The city is moving",
            PublicSummary: publicSummary,
            PublicHighlights: ["Rust Bazaar pressure rose."],
            LedgerUrl: "https://chummer.run/ledger?turn=1",
            DispatchUrl: "https://chummer.run/ledger/dispatches/ledger_dispatch_emerald-sprawl-prelude_turn_0001",
            TickReceiptUrl: "https://chummer.run/ledger/closeouts",
            OccurredAtUtc: DateTimeOffset.UtcNow);

    private static IConfiguration BuildConfiguration(string tempRoot, IReadOnlyDictionary<string, string?> extra)
    {
        Dictionary<string, string?> values = new(extra, StringComparer.OrdinalIgnoreCase)
        {
            ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(tempRoot, "community-store.json")
        };
        return new ConfigurationBuilder()
            .AddInMemoryCollection(values)
            .Build();
    }

    private static string CreateTempRoot()
    {
        string tempRoot = Path.Combine(Path.GetTempPath(), "black-ledger-tick-news-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(tempRoot);
        return tempRoot;
    }

    private static void DeleteTempRoot(string tempRoot)
    {
        if (Directory.Exists(tempRoot))
        {
            Directory.Delete(tempRoot, recursive: true);
        }
    }

    private sealed record CapturedRequest(string Url, string Body);

    private sealed class CapturingHandler(
        List<CapturedRequest> requests,
        HttpStatusCode statusCode,
        string responseBody) : HttpMessageHandler
    {
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            string body = request.Content is null
                ? string.Empty
                : await request.Content.ReadAsStringAsync(cancellationToken);
            requests.Add(new CapturedRequest(request.RequestUri!.ToString(), body));
            return new HttpResponseMessage(statusCode)
            {
                Content = new StringContent(responseBody)
            };
        }
    }
}
