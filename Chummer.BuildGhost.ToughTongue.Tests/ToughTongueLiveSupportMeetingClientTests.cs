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
        ScriptedHandler handler = new((_, _) => throw new AssertFailedException("Network must not be called."));
        ToughTongueLiveSupportMeetingClient client = Client(handler, new Dictionary<string, string?>());

        BuildGhostToughTongueMeetingBotResult result = await client.ScheduleAsync(Command(), CancellationToken.None);

        Assert.IsFalse(result.Success);
        Assert.AreEqual("tough-tongue-meeting-bot-configuration-invalid", result.OutcomeCode);
        Assert.IsEmpty(handler.Requests);
    }

    [TestMethod]
    [DataRow("zoom", "https://zoom.us/j/123456789")]
    [DataRow("teams", "https://teams.microsoft.com/l/meetup-join/19%3ameeting_example")]
    public async Task Official_v2_schedule_then_immediate_join_poll_maps_zoom_and_teams(
        string provider,
        string joinUrl)
    {
        BuildGhostToughTongueMeetingBotCommand command = Command(provider, joinUrl);
        ScriptedHandler handler = new((_, call) => call switch
        {
            1 => JsonResponse(ListResponse()),
            2 => JsonResponse(ScheduleResponse()),
            3 => JsonResponse(ListResponse(BotRecord(command, status: "in_call_recording", joined: true))),
            _ => throw new AssertFailedException("Unexpected provider call.")
        });

        BuildGhostToughTongueMeetingBotResult result = await Client(handler, ValidConfiguration())
            .ScheduleAsync(command, CancellationToken.None);

        Assert.IsTrue(result.Success);
        Assert.IsFalse(result.ReconciliationRequired);
        Assert.AreEqual("joined", result.OutcomeCode);
        Assert.AreEqual(1, result.BotCount);
        Assert.AreEqual("in_call_recording", result.LifecycleStatus);
        Assert.AreEqual(Digest("account"), result.AccountScopeRefDigest);
        Assert.AreEqual(Digest("0123456789abcdef01234567"), result.ScenarioRefDigest);
        Assert.AreEqual(ToughTongueBuildGhostPersonaIds.StockDefaultAvatar, result.AvatarAlias);
        Assert.AreEqual(Digest("avatar-binding"), result.AvatarBindingDigest);
        Assert.IsTrue(result.BotRefDigest.StartsWith("sha256:", StringComparison.Ordinal));
        Assert.IsTrue(result.SessionRefDigest.StartsWith("sha256:", StringComparison.Ordinal));
        Assert.IsTrue(result.ProviderResponseDigest.StartsWith("sha256:", StringComparison.Ordinal));
        Assert.IsTrue(result.JoinReceiptDigest.StartsWith("sha256:", StringComparison.Ordinal));

        Assert.HasCount(3, handler.Requests);
        Assert.AreEqual(HttpMethod.Get, handler.Requests[0].Method);
        Assert.AreEqual(
            "https://api.toughtongueai.com/api/public/v2/meeting-bots?scenario_id=0123456789abcdef01234567&page=1&limit=50",
            handler.Requests[0].Uri.AbsoluteUri);
        RequestSnapshot scheduled = handler.Requests[1];
        Assert.AreEqual(HttpMethod.Post, scheduled.Method);
        Assert.AreEqual("https://api.toughtongueai.com/api/public/v2/meeting-bots", scheduled.Uri.AbsoluteUri);
        Assert.AreEqual("Bearer", scheduled.AuthorizationScheme);
        Assert.AreEqual("test-meeting-bot-credential", scheduled.AuthorizationParameter);
        Assert.AreEqual("no-store", scheduled.CacheControl);
        Assert.AreEqual("idempotency-live-1", scheduled.IdempotencyKey);
        using JsonDocument body = JsonDocument.Parse(scheduled.Body);
        Assert.AreEqual(4, body.RootElement.EnumerateObject().Count());
        Assert.AreEqual("0123456789abcdef01234567", body.RootElement.GetProperty("scenario_id").GetString());
        Assert.AreEqual(command.JoinUrl.AbsoluteUri, body.RootElement.GetProperty("meeting_url").GetString());
        Assert.AreEqual(provider, body.RootElement.GetProperty("meeting_provider").GetString());
        Assert.AreEqual("Chummer Live Support", body.RootElement.GetProperty("bot_name").GetString());
        Assert.IsFalse(body.RootElement.TryGetProperty("scheduled_ts", out _));
        Assert.IsFalse(body.RootElement.TryGetProperty("account_scope_ref_digest", out _));
        Assert.IsFalse(body.RootElement.TryGetProperty("avatar_binding_digest", out _));

        string serialized = JsonSerializer.Serialize(result);
        Assert.IsFalse(serialized.Contains("bot-1", StringComparison.Ordinal));
        Assert.IsFalse(serialized.Contains("session-1", StringComparison.Ordinal));
        Assert.IsFalse(serialized.Contains(joinUrl, StringComparison.Ordinal));
    }

    [TestMethod]
    public async Task Existing_joined_bot_is_reconciled_without_duplicate_schedule()
    {
        BuildGhostToughTongueMeetingBotCommand command = Command();
        ScriptedHandler handler = new((_, call) => call == 1
            ? JsonResponse(ListResponse(BotRecord(command, status: "in_call_recording", joined: true)))
            : throw new AssertFailedException("A reconciled bot must not be scheduled again."));

        BuildGhostToughTongueMeetingBotResult result = await Client(handler, ValidConfiguration())
            .ScheduleAsync(command, CancellationToken.None);

        Assert.IsTrue(result.Success);
        Assert.HasCount(1, handler.Requests);
        Assert.AreEqual(HttpMethod.Get, handler.Requests.Single().Method);
    }

    [TestMethod]
    [DataRow("failed", "tough-tongue-meeting-bot-failed", false)]
    [DataRow("call_ended", "tough-tongue-meeting-bot-call-ended-before-ready", false)]
    [DataRow("done", "tough-tongue-meeting-bot-call-ended-before-ready", false)]
    [DataRow("scheduled", "tough-tongue-meeting-bot-join-timeout", true)]
    [DataRow("in_call_recording", "tough-tongue-meeting-bot-join-timeout", true)]
    public async Task Failed_or_unjoined_bot_never_becomes_ready(
        string status,
        string expectedOutcome,
        bool expectedReconciliation)
    {
        BuildGhostToughTongueMeetingBotCommand command = Command();
        ScriptedHandler handler = new((_, call) => call switch
        {
            1 => JsonResponse(ListResponse()),
            2 => JsonResponse(ScheduleResponse()),
            _ => JsonResponse(ListResponse(BotRecord(command, status, joined: false)))
        });

        BuildGhostToughTongueMeetingBotResult result = await Client(handler, ValidConfiguration())
            .ScheduleAsync(command, CancellationToken.None);

        Assert.IsFalse(result.Success);
        Assert.AreEqual(expectedOutcome, result.OutcomeCode);
        Assert.AreEqual(expectedReconciliation, result.ReconciliationRequired);
        Assert.HasCount(expectedReconciliation ? 4 : 3, handler.Requests);
    }

    [TestMethod]
    [DataRow("account")]
    [DataRow("scenario")]
    [DataRow("avatar")]
    public async Task Command_authority_mismatch_fails_before_network(string mismatch)
    {
        BuildGhostToughTongueMeetingBotCommand command = Command();
        command = mismatch switch
        {
            "account" => command with { AccountScopeRefDigest = Digest("other-account") },
            "scenario" => command with { ScenarioRefDigest = Digest("other-scenario") },
            "avatar" => command with { AvatarBindingDigest = Digest("other-avatar") },
            _ => throw new AssertFailedException("Unexpected mismatch.")
        };
        ScriptedHandler handler = new((_, _) => throw new AssertFailedException("Network must not be called."));

        BuildGhostToughTongueMeetingBotResult result = await Client(handler, ValidConfiguration())
            .ScheduleAsync(command, CancellationToken.None);

        Assert.IsFalse(result.Success);
        Assert.AreEqual("tough-tongue-meeting-bot-configuration-invalid", result.OutcomeCode);
        Assert.IsEmpty(handler.Requests);
    }

    [TestMethod]
    [DataRow("provider")]
    [DataRow("link")]
    [DataRow("scenario")]
    public async Task Polled_bot_with_wrong_provider_link_or_scenario_is_rejected(string mismatch)
    {
        BuildGhostToughTongueMeetingBotCommand command = Command();
        Dictionary<string, object?> wrong = BotRecord(command, status: "in_call_recording", joined: true);
        wrong[mismatch switch
        {
            "provider" => "meeting_provider",
            "link" => "meeting_url",
            "scenario" => "scenario_id",
            _ => throw new AssertFailedException("Unexpected mismatch.")
        }] = mismatch switch
        {
            "provider" => "teams",
            "link" => "https://zoom.us/j/987654321",
            "scenario" => "fedcba9876543210fedcba98",
            _ => string.Empty
        };
        ScriptedHandler handler = new((_, call) => call switch
        {
            1 => JsonResponse(ListResponse()),
            2 => JsonResponse(ScheduleResponse()),
            3 => JsonResponse(ListResponse(wrong)),
            _ => throw new AssertFailedException("Unexpected provider call.")
        });

        BuildGhostToughTongueMeetingBotResult result = await Client(handler, ValidConfiguration())
            .ScheduleAsync(command, CancellationToken.None);

        Assert.IsFalse(result.Success);
        Assert.IsTrue(result.ReconciliationRequired);
        Assert.AreEqual("tough-tongue-meeting-bot-authority-binding-invalid", result.OutcomeCode);
    }

    [TestMethod]
    public async Task Multiple_matching_bots_fail_closed_without_scheduling_another()
    {
        BuildGhostToughTongueMeetingBotCommand command = Command();
        Dictionary<string, object?> second = BotRecord(command, status: "scheduled", joined: false);
        second["id"] = "bot-2";
        second["session_id"] = "session-2";
        ScriptedHandler handler = new((_, call) => call == 1
            ? JsonResponse(ListResponse(
                BotRecord(command, status: "scheduled", joined: false),
                second))
            : throw new AssertFailedException("An ambiguous list must not schedule another bot."));

        BuildGhostToughTongueMeetingBotResult result = await Client(handler, ValidConfiguration())
            .ScheduleAsync(command, CancellationToken.None);

        Assert.IsFalse(result.Success);
        Assert.IsTrue(result.ReconciliationRequired);
        Assert.AreEqual("tough-tongue-meeting-bot-reconciliation-ambiguous", result.OutcomeCode);
        Assert.HasCount(1, handler.Requests);
    }

    [TestMethod]
    public async Task Duplicate_matching_bots_observed_after_schedule_fail_closed()
    {
        BuildGhostToughTongueMeetingBotCommand command = Command();
        Dictionary<string, object?> second = BotRecord(command, status: "scheduled", joined: false);
        second["id"] = "bot-2";
        second["session_id"] = "session-2";
        ScriptedHandler handler = new((_, call) => call switch
        {
            1 => JsonResponse(ListResponse()),
            2 => JsonResponse(ScheduleResponse()),
            3 => JsonResponse(ListResponse(
                BotRecord(command, status: "scheduled", joined: false),
                second)),
            _ => throw new AssertFailedException("Unexpected provider call.")
        });

        BuildGhostToughTongueMeetingBotResult result = await Client(handler, ValidConfiguration())
            .ScheduleAsync(command, CancellationToken.None);

        Assert.IsFalse(result.Success);
        Assert.IsTrue(result.ReconciliationRequired);
        Assert.AreEqual("tough-tongue-meeting-bot-reconciliation-ambiguous", result.OutcomeCode);
        Assert.HasCount(3, handler.Requests);
    }

    [TestMethod]
    [DataRow(1, true)]
    [DataRow(2, false)]
    public async Task Additional_list_pages_are_rejected_before_scheduling(int totalPages, bool hasNext)
    {
        string response = JsonSerializer.Serialize(new
        {
            success = true,
            bots = Array.Empty<object>(),
            page_meta = new { total_pages = totalPages, has_next = hasNext }
        });
        ScriptedHandler handler = new((_, call) => call == 1
            ? JsonResponse(response)
            : throw new AssertFailedException("An incomplete list must not schedule a bot."));

        BuildGhostToughTongueMeetingBotResult result = await Client(handler, ValidConfiguration())
            .ScheduleAsync(Command(), CancellationToken.None);

        Assert.IsFalse(result.Success);
        Assert.IsTrue(result.ReconciliationRequired);
        Assert.AreEqual("tough-tongue-meeting-bot-list-response-invalid", result.OutcomeCode);
        Assert.HasCount(1, handler.Requests);
    }

    [TestMethod]
    public async Task Ambiguous_transport_failure_is_redacted_and_requires_reconciliation()
    {
        ScriptedHandler handler = new((_, call) => call == 1
            ? JsonResponse(ListResponse())
            : throw new HttpRequestException("credential test-meeting-bot-credential leaked bot-secret-id"));

        BuildGhostToughTongueMeetingBotResult result = await Client(handler, ValidConfiguration())
            .ScheduleAsync(Command(), CancellationToken.None);

        Assert.IsFalse(result.Success);
        Assert.IsTrue(result.ReconciliationRequired);
        Assert.AreEqual("tough-tongue-meeting-bot-transport-failed-redacted", result.OutcomeCode);
        string serialized = JsonSerializer.Serialize(result);
        Assert.IsFalse(serialized.Contains("test-meeting-bot-credential", StringComparison.Ordinal));
        Assert.IsFalse(serialized.Contains("bot-secret-id", StringComparison.Ordinal));
    }

    [TestMethod]
    public async Task Caller_cancellation_during_join_poll_is_propagated()
    {
        using CancellationTokenSource cancellation = new();
        ScriptedHandler handler = new((_, call) => call switch
        {
            1 => JsonResponse(ListResponse()),
            2 => JsonResponse(ScheduleResponse()),
            3 => Cancel(cancellation),
            _ => throw new AssertFailedException("Unexpected provider call.")
        });

        try
        {
            await Client(handler, ValidConfiguration()).ScheduleAsync(Command(), cancellation.Token);
            Assert.Fail("Caller cancellation must be propagated.");
        }
        catch (OperationCanceledException)
        {
            Assert.IsTrue(cancellation.IsCancellationRequested);
            Assert.HasCount(3, handler.Requests);
        }
    }

    private static HttpResponseMessage Cancel(CancellationTokenSource cancellation)
    {
        cancellation.Cancel();
        cancellation.Token.ThrowIfCancellationRequested();
        throw new AssertFailedException("Cancellation did not throw.");
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
            [ToughTongueLiveSupportMeetingClient.BotNameConfigurationKey] = "Chummer Live Support",
            [ToughTongueLiveSupportMeetingClient.PollAttemptsConfigurationKey] = "2",
            [ToughTongueLiveSupportMeetingClient.PollIntervalMillisecondsConfigurationKey] = "1",
            [BuildGhostLiveSupportService.ExpectedAccountScopeDigestKey] = Digest("account"),
            [BuildGhostLiveSupportService.ExpectedAvatarBindingDigestKey] = Digest("avatar-binding")
        };

    private static BuildGhostToughTongueMeetingBotCommand Command(
        string provider = BuildGhostLiveMeetingProviders.Zoom,
        string joinUrl = "https://zoom.us/j/123456789")
        => new(
            "request-live-1",
            provider,
            new Uri(joinUrl, UriKind.Absolute),
            Digest("account"),
            Digest("0123456789abcdef01234567"),
            ToughTongueBuildGhostPersonaIds.StockDefaultAvatar,
            Digest("avatar-binding"),
            "idempotency-live-1");

    private static Dictionary<string, object?> BotRecord(
        BuildGhostToughTongueMeetingBotCommand command,
        string status,
        bool joined)
        => new()
        {
            ["id"] = "bot-1",
            ["status"] = status,
            ["scenario_id"] = "0123456789abcdef01234567",
            ["session_id"] = "session-1",
            ["meeting_url"] = command.JoinUrl.AbsoluteUri,
            ["meeting_provider"] = command.MeetingProvider,
            ["bot_name"] = "Chummer Live Support",
            ["scheduled_ts"] = null,
            ["bot_joined_at"] = joined ? "2026-08-25T01:30:00Z" : null,
            ["created_at"] = "2026-08-25T01:29:00Z",
            ["updated_at"] = "2026-08-25T01:30:00Z",
            ["error_message"] = status == "failed" ? "provider-internal-detail-must-not-escape" : null
        };

    private static string ScheduleResponse()
        => JsonSerializer.Serialize(new
        {
            success = true,
            bots = new[] { new { bot_id = "bot-1", session_id = "session-1" } }
        });

    private static string ListResponse(params object[] bots)
        => JsonSerializer.Serialize(new { success = true, bots });

    private static HttpResponseMessage JsonResponse(string json)
        => new(HttpStatusCode.OK)
        {
            Content = new StringContent(json, Encoding.UTF8, "application/json")
        };

    private static string Digest(string value)
        => $"sha256:{Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant()}";

    private sealed record RequestSnapshot(
        HttpMethod Method,
        Uri Uri,
        string AuthorizationScheme,
        string AuthorizationParameter,
        string CacheControl,
        string IdempotencyKey,
        string Body);

    private sealed class ScriptedHandler(Func<RequestSnapshot, int, HttpResponseMessage> response) : HttpMessageHandler
    {
        public List<RequestSnapshot> Requests { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            string body = request.Content is null
                ? string.Empty
                : await request.Content.ReadAsStringAsync(cancellationToken);
            RequestSnapshot snapshot = new(
                request.Method,
                request.RequestUri ?? throw new AssertFailedException("Request URI is required."),
                request.Headers.Authorization?.Scheme ?? string.Empty,
                request.Headers.Authorization?.Parameter ?? string.Empty,
                request.Headers.CacheControl?.ToString() ?? string.Empty,
                request.Headers.TryGetValues("Idempotency-Key", out IEnumerable<string>? values)
                    ? values.SingleOrDefault() ?? string.Empty
                    : string.Empty,
                body);
            Requests.Add(snapshot);
            return response(snapshot, Requests.Count);
        }
    }
}
