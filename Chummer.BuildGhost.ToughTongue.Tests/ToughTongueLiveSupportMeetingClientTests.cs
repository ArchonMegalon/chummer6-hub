using Chummer.Run.AI.Services.BuildGhost;
using Chummer.Run.Contracts.BuildGhost;
using Microsoft.Extensions.Configuration;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using System.Net;
using System.Text;
using System.Text.Json;

namespace Chummer.BuildGhost.ToughTongue.Tests;

[TestClass]
public sealed class ToughTongueLiveSupportMeetingClientTests
{
    [TestMethod]
    public async Task Missing_private_binding_fails_without_network()
    {
        RecordingHandler handler = new(_ => throw new AssertFailedException("Network must not be called."));
        ToughTongueLiveSupportMeetingClient client = Client(handler, new Dictionary<string, string?>());

        BuildGhostToughTongueMeetingBotResult result = await client.ScheduleAsync(Command(), CancellationToken.None);

        Assert.IsFalse(result.Success);
        Assert.AreEqual("tough-tongue-meeting-bot-configuration-invalid", result.OutcomeCode);
        Assert.AreEqual(0, handler.Calls);
    }

    [TestMethod]
    public async Task Exact_official_schedule_contract_returns_only_digest_bound_identifiers()
    {
        RecordingHandler handler = new(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                "{\"success\":true,\"bots\":[{\"bot_id\":\"bot-1\",\"session_id\":\"session-1\"}]}",
                Encoding.UTF8,
                "application/json")
        });
        ToughTongueLiveSupportMeetingClient client = Client(handler, ValidConfiguration());

        BuildGhostToughTongueMeetingBotResult result = await client.ScheduleAsync(Command(), CancellationToken.None);

        Assert.IsTrue(result.Success);
        Assert.AreEqual("scheduled", result.OutcomeCode);
        Assert.IsTrue(result.BotRefDigest.StartsWith("sha256:", StringComparison.Ordinal));
        Assert.IsTrue(result.SessionRefDigest.StartsWith("sha256:", StringComparison.Ordinal));
        Assert.IsTrue(result.ProviderResponseDigest.StartsWith("sha256:", StringComparison.Ordinal));
        Assert.AreEqual(1, handler.Calls);
        Assert.AreEqual(HttpMethod.Post, handler.Method);
        Assert.AreEqual(
            "https://api.toughtongueai.com/api/public/v2/meeting-bots",
            handler.RequestUri?.AbsoluteUri);
        Assert.AreEqual("Bearer", handler.AuthorizationScheme);
        Assert.AreEqual("test-meeting-bot-credential", handler.AuthorizationParameter);
        Assert.AreEqual("no-store", handler.CacheControl);
        Assert.AreEqual("idempotency-live-1", handler.IdempotencyKey);
        using JsonDocument body = JsonDocument.Parse(handler.Body);
        Assert.AreEqual("0123456789abcdef01234567", body.RootElement.GetProperty("scenario_id").GetString());
        Assert.AreEqual("https://zoom.us/j/123456789", body.RootElement.GetProperty("meeting_url").GetString());
        Assert.AreEqual("zoom", body.RootElement.GetProperty("meeting_provider").GetString());
        Assert.AreEqual("Chummer Live Support", body.RootElement.GetProperty("bot_name").GetString());
        Assert.AreEqual(JsonValueKind.Null, body.RootElement.GetProperty("scheduled_ts").ValueKind);
        Assert.IsFalse(JsonSerializer.Serialize(result).Contains("bot-1", StringComparison.Ordinal));
        Assert.IsFalse(JsonSerializer.Serialize(result).Contains("session-1", StringComparison.Ordinal));
    }

    [TestMethod]
    public async Task Redirect_or_ambiguous_multi_bot_response_is_rejected()
    {
        RecordingHandler redirect = new(_ => new HttpResponseMessage(HttpStatusCode.Redirect)
        {
            Headers = { Location = new Uri("https://attacker.example/collect") }
        });
        BuildGhostToughTongueMeetingBotResult redirected = await Client(redirect, ValidConfiguration())
            .ScheduleAsync(Command(), CancellationToken.None);
        Assert.IsFalse(redirected.Success);
        Assert.IsFalse(redirected.ReconciliationRequired);
        Assert.AreEqual("tough-tongue-meeting-bot-http-302", redirected.OutcomeCode);

        RecordingHandler ambiguous = new(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent(
                "{\"success\":true,\"bots\":[{\"bot_id\":\"bot-1\",\"session_id\":\"session-1\"},{\"bot_id\":\"bot-2\",\"session_id\":\"session-2\"}]}",
                Encoding.UTF8,
                "application/json")
        });
        BuildGhostToughTongueMeetingBotResult multiple = await Client(ambiguous, ValidConfiguration())
            .ScheduleAsync(Command(), CancellationToken.None);
        Assert.IsFalse(multiple.Success);
        Assert.IsTrue(multiple.ReconciliationRequired);
        Assert.AreEqual("tough-tongue-meeting-bot-response-invalid", multiple.OutcomeCode);

        RecordingHandler unavailable = new(_ => new HttpResponseMessage(HttpStatusCode.ServiceUnavailable));
        BuildGhostToughTongueMeetingBotResult serverError = await Client(unavailable, ValidConfiguration())
            .ScheduleAsync(Command(), CancellationToken.None);
        Assert.IsFalse(serverError.Success);
        Assert.IsTrue(serverError.ReconciliationRequired);

        RecordingHandler unexpectedSuccess = new(_ => new HttpResponseMessage(HttpStatusCode.Accepted));
        BuildGhostToughTongueMeetingBotResult accepted = await Client(unexpectedSuccess, ValidConfiguration())
            .ScheduleAsync(Command(), CancellationToken.None);
        Assert.IsFalse(accepted.Success);
        Assert.IsTrue(accepted.ReconciliationRequired);
    }

    private static ToughTongueLiveSupportMeetingClient Client(
        HttpMessageHandler handler,
        IReadOnlyDictionary<string, string?> values)
    {
        HttpClient http = new(handler)
        {
            BaseAddress = new Uri("https://api.toughtongueai.com/api/public/", UriKind.Absolute)
        };
        IConfiguration configuration = new ConfigurationBuilder().AddInMemoryCollection(values).Build();
        return new ToughTongueLiveSupportMeetingClient(http, configuration);
    }

    private static IReadOnlyDictionary<string, string?> ValidConfiguration()
        => new Dictionary<string, string?>
        {
            [ToughTongueLiveSupportMeetingClient.ApiKeyConfigurationKey] = "test-meeting-bot-credential",
            [ToughTongueLiveSupportMeetingClient.ScenarioIdConfigurationKey] = "0123456789abcdef01234567",
            [ToughTongueLiveSupportMeetingClient.BotNameConfigurationKey] = "Chummer Live Support"
        };

    private static BuildGhostToughTongueMeetingBotCommand Command()
        => new(
            "request-live-1",
            BuildGhostLiveMeetingProviders.Zoom,
            new Uri("https://zoom.us/j/123456789", UriKind.Absolute),
            "idempotency-live-1");

    private sealed class RecordingHandler(Func<HttpRequestMessage, HttpResponseMessage> response) : HttpMessageHandler
    {
        public int Calls { get; private set; }
        public HttpMethod? Method { get; private set; }
        public Uri? RequestUri { get; private set; }
        public string AuthorizationScheme { get; private set; } = string.Empty;
        public string AuthorizationParameter { get; private set; } = string.Empty;
        public string CacheControl { get; private set; } = string.Empty;
        public string IdempotencyKey { get; private set; } = string.Empty;
        public string Body { get; private set; } = string.Empty;

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            Calls++;
            Method = request.Method;
            RequestUri = request.RequestUri;
            AuthorizationScheme = request.Headers.Authorization?.Scheme ?? string.Empty;
            AuthorizationParameter = request.Headers.Authorization?.Parameter ?? string.Empty;
            CacheControl = request.Headers.CacheControl?.ToString() ?? string.Empty;
            IdempotencyKey = request.Headers.TryGetValues("Idempotency-Key", out IEnumerable<string>? values)
                ? values.SingleOrDefault() ?? string.Empty
                : string.Empty;
            Body = request.Content is null
                ? string.Empty
                : await request.Content.ReadAsStringAsync(cancellationToken);
            return response(request);
        }
    }
}
