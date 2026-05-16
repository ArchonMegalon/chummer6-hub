using System.Net;
using System.Text.Json;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class ParticipantNotificationTests
{
    [Fact]
    public async Task ParticipantNotification_AccountOpenWithParticipationIntentQueuesMaskedEaPayloadAndStoresReceipt()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            var requests = new List<CapturedRequest>();
            using var http = new HttpClient(new CapturingHandler(requests, HttpStatusCode.OK, """{"target_ref":"ea-delivery-1"}"""));
            IConfiguration configuration = BuildConfiguration(
                tempRoot,
                new Dictionary<string, string?>
                {
                    ["CHUMMER_OPERATOR_PARTICIPATION_NOTIFY_TO"] = "ops@chummer.run",
                    ["CHUMMER_OPERATOR_PARTICIPATION_EA_API_TOKEN"] = "ea-token",
                    ["CHUMMER_OPERATOR_PARTICIPATION_EA_PRINCIPAL_ID"] = "principal-1",
                    ["CHUMMER_OPERATOR_PARTICIPATION_EA_BINDING_ID"] = "binding-1",
                    ["CHUMMER_OPERATOR_PARTICIPATION_EA_BASE_URL"] = "https://ea.test",
                    ["CHUMMER_OPERATOR_PARTICIPATION_HASH_SALT"] = "salt-1",
                });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            HubUserEnsureResult ensured = accounts.EnsureUserWithStatus("subject.google.runner", "Runner Prime", "runner@example.com");
            ParticipationOperatorNotificationService service = new(http, store, configuration, NullLogger<ParticipationOperatorNotificationService>.Instance);

            ParticipationOperatorNotificationReceipt? receipt = await service.NotifyAccountOpenedIfNeededAsync(
                ensured.User,
                ensured.User.Email,
                "/participate/codex",
                authProviderFamily: "google",
                accountCreated: ensured.Created,
                cancellationToken: CancellationToken.None);

            Assert.NotNull(receipt);
            Assert.Equal("participant_account_opened", receipt!.EventType);
            Assert.Equal("guided_contribution", receipt.IntentKind);
            Assert.Equal("/participate/codex", receipt.EntryRoute);
            Assert.Equal("sent", receipt.Status);
            Assert.Equal("google", receipt.AuthProviderFamily);
            Assert.Equal("r***@example.com", receipt.EmailMasked);
            Assert.True(receipt.IsFirstParticipationEvent);
            Assert.Single(service.ListReceiptsForUser(ensured.User.UserId));

            CapturedRequest request = Assert.Single(requests);
            Assert.Equal("https://ea.test/v1/tools/execute", request.Url);
            Assert.Contains("\"tool_name\":\"connector.dispatch\"", request.Body, StringComparison.Ordinal);
            Assert.Contains("\"action_kind\":\"delivery.send\"", request.Body, StringComparison.Ordinal);
            Assert.Contains("\"recipient\":\"ops@chummer.run\"", request.Body, StringComparison.Ordinal);
            Assert.Contains("\"email_masked\":\"r***@example.com\"", request.Body, StringComparison.Ordinal);
            Assert.DoesNotContain("runner@example.com", request.Body, StringComparison.Ordinal);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task ParticipantNotification_FirstActionSuppressesWithoutRecipientAndDuplicateDoesNotResend()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            var requests = new List<CapturedRequest>();
            using var http = new HttpClient(new CapturingHandler(requests, HttpStatusCode.OK, """{"target_ref":"ea-delivery-1"}"""));
            IConfiguration configuration = BuildConfiguration(
                tempRoot,
                new Dictionary<string, string?>
                {
                    ["CHUMMER_OPERATOR_PARTICIPATION_EA_API_TOKEN"] = "ea-token",
                    ["CHUMMER_OPERATOR_PARTICIPATION_EA_PRINCIPAL_ID"] = "principal-1",
                    ["CHUMMER_OPERATOR_PARTICIPATION_EA_BINDING_ID"] = "binding-1",
                    ["CHUMMER_OPERATOR_PARTICIPATION_EA_BASE_URL"] = "https://ea.test",
                });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            HubUserDto user = accounts.EnsureUserWithStatus("subject.email.runner", "Runner Prime", "runner@example.com").User;
            ParticipationOperatorNotificationService service = new(http, store, configuration, NullLogger<ParticipationOperatorNotificationService>.Instance);

            ParticipationOperatorNotificationReceipt? first = await service.NotifyFirstActionIfNeededAsync(
                user,
                user.Email,
                intentKind: "package",
                entryRoute: "/packages/desktop-preview/vote",
                authProviderFamily: "email",
                cancellationToken: CancellationToken.None);
            ParticipationOperatorNotificationReceipt? second = await service.NotifyFirstActionIfNeededAsync(
                user,
                user.Email,
                intentKind: "package",
                entryRoute: "/packages/desktop-preview/vote",
                authProviderFamily: "email",
                cancellationToken: CancellationToken.None);

            Assert.NotNull(first);
            Assert.NotNull(second);
            Assert.Equal("suppressed_recipient_missing", first!.Status);
            Assert.Equal(first.ReceiptId, second!.ReceiptId);
            Assert.Empty(requests);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

    [Fact]
    public async Task ParticipantNotification_EaFailureStaysNonBlockingAndStoresFailedReceipt()
    {
        string tempRoot = CreateTempRoot();
        try
        {
            var requests = new List<CapturedRequest>();
            using var http = new HttpClient(new CapturingHandler(requests, HttpStatusCode.InternalServerError, """{"error":"nope"}"""));
            IConfiguration configuration = BuildConfiguration(
                tempRoot,
                new Dictionary<string, string?>
                {
                    ["CHUMMER_OPERATOR_PARTICIPATION_NOTIFY_TO"] = "ops@chummer.run",
                    ["CHUMMER_OPERATOR_PARTICIPATION_EA_API_TOKEN"] = "ea-token",
                    ["CHUMMER_OPERATOR_PARTICIPATION_EA_PRINCIPAL_ID"] = "principal-1",
                    ["CHUMMER_OPERATOR_PARTICIPATION_EA_BINDING_ID"] = "binding-1",
                    ["CHUMMER_OPERATOR_PARTICIPATION_EA_BASE_URL"] = "https://ea.test",
                });
            CommunityStore store = new(configuration, NullLogger<CommunityStore>.Instance);
            AccountService accounts = new(store);
            HubUserEnsureResult ensured = accounts.EnsureUserWithStatus("subject.email.runner", "Runner Prime", "runner@example.com");
            ParticipationOperatorNotificationService service = new(http, store, configuration, NullLogger<ParticipationOperatorNotificationService>.Instance);

            ParticipationOperatorNotificationReceipt? receipt = await service.NotifyAccountOpenedIfNeededAsync(
                ensured.User,
                ensured.User.Email,
                "/participate/karma-forge",
                authProviderFamily: "email",
                accountCreated: ensured.Created,
                cancellationToken: CancellationToken.None);

            Assert.NotNull(receipt);
            Assert.Equal("failed_delivery", receipt!.Status);
            Assert.Equal("karma_forge", receipt.IntentKind);
            Assert.Single(requests);
        }
        finally
        {
            DeleteTempRoot(tempRoot);
        }
    }

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
        string tempRoot = Path.Combine(Path.GetTempPath(), "participant-notification-tests", Guid.NewGuid().ToString("N"));
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

    private sealed record CapturedRequest(string Url, string Body, IReadOnlyDictionary<string, string> Headers);

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
            requests.Add(new CapturedRequest(
                request.RequestUri!.ToString(),
                body,
                request.Headers.ToDictionary(
                    static item => item.Key,
                    static item => string.Join(",", item.Value),
                    StringComparer.OrdinalIgnoreCase)));

            return new HttpResponseMessage(statusCode)
            {
                Content = new StringContent(responseBody)
            };
        }
    }
}
