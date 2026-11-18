using Chummer.Run.AI.Services.BuildGhost;
using Chummer.Run.Contracts.BuildGhost;
using Microsoft.Extensions.Configuration;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace Chummer.BuildGhost.ToughTongue.Tests;

[TestClass]
public sealed class ChummerMeetingLinkBrokerClientTests
{
    private const string Token = "0123456789abcdef0123456789abcdef";

    [TestMethod]
    public async Task Missing_configuration_never_calls_network()
    {
        RecordingHandler handler = new();
        ChummerMeetingLinkBrokerClient client = new(
            new HttpClient(handler),
            new ConfigurationBuilder().AddInMemoryCollection([]).Build());

        BuildGhostMeetingLinkProvisioningResult result =
            await client.CreateAsync(Command(), CancellationToken.None);

        Assert.IsFalse(result.Success);
        Assert.AreEqual(0, handler.Calls);
        Assert.IsNotEmpty(client.BlockingReasons);
    }

    [TestMethod]
    public async Task Create_uses_internal_bearer_and_idempotency_and_returns_bounded_provider_data()
    {
        RecordingHandler handler = new()
        {
            Response = JsonResponse(HttpStatusCode.Created, new
            {
                success = true,
                meetingProvider = "zoom",
                meetingId = "meeting-123",
                cancellationHandle = "cancel-123",
                joinUrl = "https://chummer.zoom.us/j/123?pwd=opaque",
                startsAtUtc = "2026-08-25T00:00:00Z",
                expiresAtUtc = "2026-08-25T00:45:00Z"
            })
        };
        HttpClient http = new(handler)
        {
            BaseAddress = new Uri("https://meetings.internal/", UriKind.Absolute)
        };
        ChummerMeetingLinkBrokerClient client = new(http, Configuration());

        BuildGhostMeetingLinkProvisioningResult result =
            await client.CreateAsync(Command(), CancellationToken.None);

        Assert.IsTrue(result.Success);
        Assert.AreEqual(new Uri("https://chummer.zoom.us/j/123?pwd=opaque"), result.JoinUrl);
        Assert.AreEqual("cancel-123", result.CancellationHandle);
        Assert.AreEqual("Bearer", handler.Authorization?.Scheme);
        Assert.AreEqual(Token, handler.Authorization?.Parameter);
        Assert.AreEqual("idempotency-123", handler.IdempotencyKey);
        Assert.AreEqual(new Uri("https://meetings.internal/api/v1/meetings"), handler.RequestUri);
    }

    [TestMethod]
    public async Task Server_error_or_invalid_success_requires_reconciliation()
    {
        RecordingHandler unavailable = new()
        {
            Response = new HttpResponseMessage(HttpStatusCode.ServiceUnavailable)
        };
        ChummerMeetingLinkBrokerClient unavailableClient = new(
            new HttpClient(unavailable) { BaseAddress = new Uri("https://meetings.internal/") },
            Configuration());

        BuildGhostMeetingLinkProvisioningResult serverError =
            await unavailableClient.CreateAsync(Command(), CancellationToken.None);

        RecordingHandler malformed = new()
        {
            Response = JsonResponse(HttpStatusCode.Created, new { success = true })
        };
        ChummerMeetingLinkBrokerClient malformedClient = new(
            new HttpClient(malformed) { BaseAddress = new Uri("https://meetings.internal/") },
            Configuration());
        BuildGhostMeetingLinkProvisioningResult invalidSuccess =
            await malformedClient.CreateAsync(Command(), CancellationToken.None);

        RecordingHandler unexpectedSuccess = new()
        {
            Response = new HttpResponseMessage(HttpStatusCode.Accepted)
        };
        ChummerMeetingLinkBrokerClient unexpectedSuccessClient = new(
            new HttpClient(unexpectedSuccess) { BaseAddress = new Uri("https://meetings.internal/") },
            Configuration());
        BuildGhostMeetingLinkProvisioningResult accepted =
            await unexpectedSuccessClient.CreateAsync(Command(), CancellationToken.None);

        Assert.IsFalse(serverError.Success);
        Assert.IsTrue(serverError.ReconciliationRequired);
        Assert.IsFalse(invalidSuccess.Success);
        Assert.IsTrue(invalidSuccess.ReconciliationRequired);
        Assert.IsFalse(accepted.Success);
        Assert.IsTrue(accepted.ReconciliationRequired);
    }

    private static BuildGhostMeetingLinkProvisioningCommand Command()
        => new(
            "request-123",
            "sha256:" + new string('a', 64),
            BuildGhostLiveMeetingProviders.Zoom,
            "en-US",
            30,
            "idempotency-123");

    private static IConfiguration Configuration()
        => new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            [ChummerMeetingLinkBrokerClient.ApiTokenConfigurationKey] = Token
        }).Build();

    private static HttpResponseMessage JsonResponse(HttpStatusCode status, object value)
        => new(status)
        {
            Content = new StringContent(
                JsonSerializer.Serialize(value, new JsonSerializerOptions(JsonSerializerDefaults.Web)),
                Encoding.UTF8,
                "application/json")
        };

    private sealed class RecordingHandler : HttpMessageHandler
    {
        public int Calls { get; private set; }
        public Uri? RequestUri { get; private set; }
        public AuthenticationHeaderValue? Authorization { get; private set; }
        public string? IdempotencyKey { get; private set; }
        public HttpResponseMessage Response { get; init; } = new(HttpStatusCode.ServiceUnavailable);

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            Calls++;
            RequestUri = request.RequestUri;
            Authorization = request.Headers.Authorization;
            IdempotencyKey = request.Headers.TryGetValues("Idempotency-Key", out IEnumerable<string>? values)
                ? values.Single()
                : null;
            return Task.FromResult(Response);
        }
    }
}
