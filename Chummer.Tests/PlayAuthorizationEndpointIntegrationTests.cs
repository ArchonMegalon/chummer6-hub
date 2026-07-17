using System.Net;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Contracts;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Xunit;

namespace Chummer.Tests;

public sealed class PlayAuthorizationEndpointIntegrationTests
{
    private const string GameMasterToken = "gm-access-token";
    private const string PlayerToken = "player-access-token";
    private const string IntruderToken = "intruder-access-token";
    private const string GameMasterSubject = "subject.gm";
    private const string PlayerSubject = "subject.player";
    private const string IntruderSubject = "subject.intruder";
    private const string GameMasterUserId = "gm-user";
    private const string PlayerUserId = "player-user";
    private const string InternalKey = "A7vN3_mQ9-xR2kL8pT5wY1cD6sF4hJ0zB7uE3iO9nM2qS8gK5rV1xC6aP4tW0";
    private const string DeviceThumbprint = "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd";
    private static readonly DateTimeOffset BaselineUtc = new(2026, 7, 14, 10, 0, 0, TimeSpan.Zero);

    [Fact]
    public void ActivationIsTestOnlyRequiresStrongConfigurationAndHoldsOneProcessLease()
    {
        IConfiguration disabled = Configuration(enabled: false, path: Path.GetTempFileName());
        PlayAuthorizationApiPolicy.ValidateStartup(disabled, new TestEnvironment(Environments.Production));

        IConfiguration missingWriter = Configuration(enabled: true, path: Path.GetTempFileName(), writerMode: null);
        Assert.Throws<InvalidOperationException>(() => PlayAuthorizationApiPolicy.ValidateStartup(
            missingWriter,
            new TestEnvironment(PlayAuthorizationApiPolicy.TestEnvironmentName)));

        IConfiguration weakKey = Configuration(enabled: true, path: Path.GetTempFileName(), internalKey: "change-me");
        Assert.Throws<InvalidOperationException>(() => PlayAuthorizationApiPolicy.ValidateStartup(
            weakKey,
            new TestEnvironment(PlayAuthorizationApiPolicy.TestEnvironmentName)));

        IConfiguration enabled = Configuration(enabled: true, path: Path.GetTempFileName());
        PlayAuthorizationApiPolicy.ValidateStartup(
            enabled,
            new TestEnvironment(PlayAuthorizationApiPolicy.TestEnvironmentName));
        Assert.Throws<InvalidOperationException>(() => PlayAuthorizationApiPolicy.ValidateStartup(
            enabled,
            new TestEnvironment(Environments.Development)));
        Assert.Throws<InvalidOperationException>(() => PlayAuthorizationApiPolicy.ValidateStartup(
            enabled,
            new TestEnvironment(Environments.Production)));

        string root = Path.Combine(Path.GetTempPath(), $"chummer-play-lease-{Guid.NewGuid():N}");
        Directory.CreateDirectory(root);
        try
        {
            IConfiguration leaseConfiguration = Configuration(
                enabled: true,
                path: Path.Combine(root, "community.json"));
            using ServiceProvider first = LeaseProvider(leaseConfiguration);
            using ServiceProvider second = LeaseProvider(leaseConfiguration);
            _ = first.GetRequiredService<PlayAuthorizationProcessLease>();
            Assert.Throws<InvalidOperationException>(() =>
                second.GetRequiredService<PlayAuthorizationProcessLease>());

            first.Dispose();
            using ServiceProvider successor = LeaseProvider(leaseConfiguration);
            _ = successor.GetRequiredService<PlayAuthorizationProcessLease>();
        }
        finally
        {
            Directory.Delete(root, recursive: true);
        }
    }

    [Fact]
    public async Task DefaultOffIsUniform404NoStoreBeforeAuthRateLimitOrStoreWork()
    {
        await using TestPlayApp fixture = await TestPlayApp.StartAsync(enabled: false);
        using HttpClient client = fixture.CreateClient();

        using HttpResponseMessage account = await client.PostAsJsonAsync(
            "/api/v1/accounts/me/play/sessions",
            SessionRequest("session-off"));
        using HttpRequestMessage internalRequest = new(HttpMethod.Post, "/api/internal/play/grants/grant-off/introspect")
        {
            Content = JsonContent.Create(GrantRequest("secret-off"))
        };
        internalRequest.Headers.TryAddWithoutValidation(PlayAuthorizationApiPolicy.InternalApiKeyHeader, InternalKey);
        using HttpResponseMessage internalResponse = await client.SendAsync(internalRequest);
        using HttpResponseMessage head = await client.SendAsync(
            new HttpRequestMessage(HttpMethod.Head, "/api/v1/accounts/me/play/sessions"));

        foreach (HttpResponseMessage response in new[] { account, internalResponse, head })
        {
            Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
            AssertNoStore(response);
            Assert.Equal(string.Empty, await response.Content.ReadAsStringAsync());
        }

        Assert.False(File.Exists(fixture.StoragePath));
    }

    [Fact]
    public async Task AccountBoundaryRejectsAnonymousWrongSubjectAndRoleEscalationWithoutOracle()
    {
        await using TestPlayApp fixture = await TestPlayApp.StartAsync(enabled: true);
        using HttpClient client = fixture.CreateClient();
        string csrf = await fixture.GetAntiforgeryTokenAsync(client);

        using HttpResponseMessage anonymous = await fixture.SendAccountAsync(
            client,
            HttpMethod.Post,
            "/api/v1/accounts/me/play/sessions",
            SessionRequest("session-auth"),
            bearer: null,
            idempotencyKey: "anonymous-create-1",
            csrf);
        Assert.Equal(HttpStatusCode.Unauthorized, anonymous.StatusCode);

        using HttpResponseMessage intruder = await fixture.SendAccountAsync(
            client,
            HttpMethod.Post,
            "/api/v1/accounts/me/play/sessions",
            SessionRequest("session-intruder"),
            IntruderToken,
            "intruder-create-1",
            csrf);
        Assert.Equal(HttpStatusCode.NotFound, intruder.StatusCode);

        using HttpResponseMessage created = await fixture.SendAccountAsync(
            client,
            HttpMethod.Post,
            "/api/v1/accounts/me/play/sessions",
            SessionRequest("session-auth"),
            GameMasterToken,
            "gm-create-auth-1",
            csrf);
        Assert.Equal(HttpStatusCode.Created, created.StatusCode);

        using HttpResponseMessage targetEscalation = await fixture.SendAccountAsync(
            client,
            HttpMethod.Post,
            "/api/v1/accounts/me/play/sessions/session-auth/participants",
            new AddPlayParticipantRequest(PlayerUserId, PlaySessionRoles.GameMaster),
            GameMasterToken,
            "gm-escalate-target-1",
            csrf);
        using HttpResponseMessage actorEscalation = await fixture.SendAccountAsync(
            client,
            HttpMethod.Post,
            "/api/v1/accounts/me/play/sessions/session-auth/invites",
            new IssuePlayInviteRequest(PlayerUserId, PlaySessionRoles.Player),
            PlayerToken,
            "player-escalate-1",
            csrf);

        Assert.Equal(HttpStatusCode.NotFound, targetEscalation.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, actorEscalation.StatusCode);
        Assert.Equal(
            await targetEscalation.Content.ReadAsStringAsync(),
            await actorEscalation.Content.ReadAsStringAsync());
        AssertNoStore(targetEscalation);
        AssertNoStore(actorEscalation);
    }

    [Fact]
    public async Task HappyFlowUsesDedicatedServiceKeyRevalidatesRefreshAndProjectsDtosOnly()
    {
        await using TestPlayApp fixture = await TestPlayApp.StartAsync(enabled: true);
        using HttpClient client = fixture.CreateClient();
        string csrf = await fixture.GetAntiforgeryTokenAsync(client);

        await CreateSessionAndPlayerAsync(fixture, client, csrf, "session-happy");
        (string inviteId, string inviteSecret) = await IssueInviteAsync(
            fixture,
            client,
            csrf,
            "session-happy",
            "issue-happy-1");
        (string exchangeId, string exchangeSecret, string redeemBody) = await RedeemInviteAsync(
            fixture,
            client,
            csrf,
            "session-happy",
            inviteId,
            inviteSecret,
            "redeem-happy-1");

        using HttpResponseMessage bearerOnly = await fixture.SendInternalAsync(
            client,
            $"/api/internal/play/exchanges/{exchangeId}/consume",
            ConsumeRequest("session-happy", exchangeSecret),
            idempotencyKey: "consume-bearer-only",
            serviceKey: null,
            bearer: InternalKey);
        using HttpResponseMessage wrongKey = await fixture.SendInternalAsync(
            client,
            $"/api/internal/play/exchanges/{exchangeId}/consume",
            ConsumeRequest("session-happy", exchangeSecret),
            idempotencyKey: "consume-wrong-key",
            serviceKey: new string('z', 64));
        Assert.Equal(HttpStatusCode.Unauthorized, bearerOnly.StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, wrongKey.StatusCode);

        using HttpResponseMessage consumed = await fixture.SendInternalAsync(
            client,
            $"/api/internal/play/exchanges/{exchangeId}/consume",
            ConsumeRequest("session-happy", exchangeSecret),
            idempotencyKey: "consume-happy-1",
            serviceKey: InternalKey);
        string consumedBody = await ReadSuccessAsync(consumed, HttpStatusCode.Created);
        (string grantId, string grantSecret) = ReadIdAndSecret(consumedBody, "grantId");

        using HttpResponseMessage introspected = await fixture.SendInternalAsync(
            client,
            $"/api/internal/play/grants/{grantId}/introspect",
            GrantRequest(grantSecret, "session-happy"),
            idempotencyKey: null,
            serviceKey: InternalKey);
        string introspectedBody = await ReadSuccessAsync(introspected, HttpStatusCode.OK);

        using HttpResponseMessage refreshed = await fixture.SendInternalAsync(
            client,
            $"/api/internal/play/grants/{grantId}/refresh",
            new RefreshPlayGrantRequest(
                "session-happy",
                PlayerUserId,
                PlaySessionRoles.Player,
                grantSecret,
                DeviceThumbprint,
                300),
            idempotencyKey: "refresh-happy-1",
            serviceKey: InternalKey);
        string refreshedBody = await ReadSuccessAsync(refreshed, HttpStatusCode.OK);
        (_, string refreshedSecret) = ReadIdAndSecret(refreshedBody, "grantId");
        Assert.NotEqual(grantSecret, refreshedSecret);

        using HttpResponseMessage oldSecret = await fixture.SendInternalAsync(
            client,
            $"/api/internal/play/grants/{grantId}/introspect",
            GrantRequest(grantSecret, "session-happy"),
            idempotencyKey: null,
            serviceKey: InternalKey);
        using HttpResponseMessage newSecret = await fixture.SendInternalAsync(
            client,
            $"/api/internal/play/grants/{grantId}/introspect",
            GrantRequest(refreshedSecret, "session-happy"),
            idempotencyKey: null,
            serviceKey: InternalKey);
        Assert.Equal(HttpStatusCode.NotFound, oldSecret.StatusCode);
        Assert.Equal(HttpStatusCode.OK, newSecret.StatusCode);

        using HttpResponseMessage crossSession = await fixture.SendAccountAsync(
            client,
            HttpMethod.Delete,
            $"/api/v1/accounts/me/play/sessions/session-other/grants/{grantId}",
            body: null,
            GameMasterToken,
            "cross-session-revoke-1",
            csrf);
        Assert.Equal(HttpStatusCode.NotFound, crossSession.StatusCode);

        foreach (string body in new[] { redeemBody, consumedBody, introspectedBody, refreshedBody })
        {
            Assert.DoesNotContain("secretHash", body, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("authorizationVersion", body, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("sourceKind", body, StringComparison.OrdinalIgnoreCase);
            Assert.DoesNotContain("deviceThumbprint", body, StringComparison.OrdinalIgnoreCase);
        }

        string persisted = await File.ReadAllTextAsync(fixture.StoragePath);
        Assert.DoesNotContain(inviteSecret, persisted, StringComparison.Ordinal);
        Assert.DoesNotContain(exchangeSecret, persisted, StringComparison.Ordinal);
        Assert.DoesNotContain(grantSecret, persisted, StringComparison.Ordinal);
        Assert.DoesNotContain(refreshedSecret, persisted, StringComparison.Ordinal);
        Assert.DoesNotContain(InternalKey, persisted, StringComparison.Ordinal);
    }

    [Fact]
    public async Task ReplayExpiryAndPersistenceRollbackAreFailClosedAndRetryable()
    {
        await using TestPlayApp fixture = await TestPlayApp.StartAsync(enabled: true);
        using HttpClient client = fixture.CreateClient();
        string csrf = await fixture.GetAntiforgeryTokenAsync(client);
        await CreateSessionAndPlayerAsync(fixture, client, csrf, "session-failure");

        (string inviteId, string inviteSecret) = await IssueInviteAsync(
            fixture,
            client,
            csrf,
            "session-failure",
            "issue-replay-1");
        _ = await RedeemInviteAsync(
            fixture,
            client,
            csrf,
            "session-failure",
            inviteId,
            inviteSecret,
            "redeem-replay-1");
        using HttpResponseMessage replay = await fixture.SendAccountAsync(
            client,
            HttpMethod.Post,
            $"/api/v1/accounts/me/play/invites/{inviteId}/redeem",
            RedeemRequest("session-failure", inviteSecret),
            PlayerToken,
            "redeem-replay-2",
            csrf);
        Assert.Equal(HttpStatusCode.Conflict, replay.StatusCode);

        (string rollbackInviteId, string rollbackSecret) = await IssueInviteAsync(
            fixture,
            client,
            csrf,
            "session-failure",
            "issue-rollback-1");
        fixture.Persistence.ThrowAfterPersist = true;
        using HttpResponseMessage failed = await fixture.SendAccountAsync(
            client,
            HttpMethod.Post,
            $"/api/v1/accounts/me/play/invites/{rollbackInviteId}/redeem",
            RedeemRequest("session-failure", rollbackSecret),
            PlayerToken,
            "redeem-rollback-1",
            csrf);
        Assert.Equal(HttpStatusCode.ServiceUnavailable, failed.StatusCode);

        fixture.Persistence.ThrowAfterPersist = false;
        using HttpResponseMessage retried = await fixture.SendAccountAsync(
            client,
            HttpMethod.Post,
            $"/api/v1/accounts/me/play/invites/{rollbackInviteId}/redeem",
            RedeemRequest("session-failure", rollbackSecret, exchangeLifetimeSeconds: 10),
            PlayerToken,
            "redeem-rollback-1",
            csrf);
        string retryBody = await ReadSuccessAsync(retried, HttpStatusCode.Created);
        (string exchangeId, string exchangeSecret) = ReadIdAndSecret(retryBody, "exchangeId");

        fixture.Time.Advance(TimeSpan.FromSeconds(10));
        using HttpResponseMessage expired = await fixture.SendInternalAsync(
            client,
            $"/api/internal/play/exchanges/{exchangeId}/consume",
            ConsumeRequest("session-failure", exchangeSecret),
            idempotencyKey: "consume-expired-1",
            serviceKey: InternalKey);
        Assert.Equal(HttpStatusCode.Gone, expired.StatusCode);
    }

    [Fact]
    public async Task PlayLimiterRunsBeforeIdentityAndReturnsNoStore()
    {
        await using TestPlayApp fixture = await TestPlayApp.StartAsync(enabled: true);
        using HttpClient client = fixture.CreateClient();
        string csrf = await fixture.GetAntiforgeryTokenAsync(client);

        for (int index = 0; index < 30; index++)
        {
            using HttpResponseMessage response = await fixture.SendAccountAsync(
                client,
                HttpMethod.Post,
                "/api/v1/accounts/me/play/sessions",
                SessionRequest($"session-limit-{index}"),
                bearer: null,
                idempotencyKey: $"limit-request-{index:D2}",
                csrf);
            Assert.Equal(HttpStatusCode.Unauthorized, response.StatusCode);
        }

        using HttpResponseMessage limited = await fixture.SendAccountAsync(
            client,
            HttpMethod.Post,
            "/api/v1/accounts/me/play/sessions",
            SessionRequest("session-limit-final"),
            bearer: null,
            idempotencyKey: "limit-request-final",
            csrf);
        Assert.Equal(HttpStatusCode.TooManyRequests, limited.StatusCode);
        AssertNoStore(limited);
    }

    [Fact]
    public async Task IdempotencyCoordinatorExpiresSecretsRejectsFingerprintReuseAndEvictsFailures()
    {
        ManualTimeProvider time = new(BaselineUtc);
        using PlayAuthorizationIdempotencyCoordinator coordinator = new(time);
        string firstFingerprint = PlayAuthorizationIdempotencyCoordinator.Fingerprint("first-body");
        string secondFingerprint = PlayAuthorizationIdempotencyCoordinator.Fingerprint("second-body");
        int executions = 0;

        PlayAuthorizationIdempotencyOutcome first = await coordinator.ExecuteAsync(
            "account:create-session",
            "bounded-idempotency-key",
            firstFingerprint,
            () => Task.FromResult(new PlayAuthorizationHttpEnvelope(
                StatusCodes.Status201Created,
                new { Secret = $"secret-{++executions}" })));
        PlayAuthorizationIdempotencyOutcome replay = await coordinator.ExecuteAsync(
            "account:create-session",
            "bounded-idempotency-key",
            firstFingerprint,
            () => Task.FromResult(new PlayAuthorizationHttpEnvelope(
                StatusCodes.Status201Created,
                new { Secret = $"secret-{++executions}" })));
        PlayAuthorizationIdempotencyOutcome conflict = await coordinator.ExecuteAsync(
            "account:create-session",
            "bounded-idempotency-key",
            secondFingerprint,
            () => Task.FromResult(new PlayAuthorizationHttpEnvelope(
                StatusCodes.Status201Created,
                new { Secret = $"secret-{++executions}" })));

        Assert.Equal(1, executions);
        Assert.Same(first.Response, replay.Response);
        Assert.True(conflict.FingerprintConflict);
        Assert.Null(conflict.Response);

        time.Advance(TimeSpan.FromMinutes(3));
        PlayAuthorizationIdempotencyOutcome afterExpiry = await coordinator.ExecuteAsync(
            "account:create-session",
            "bounded-idempotency-key",
            firstFingerprint,
            () => Task.FromResult(new PlayAuthorizationHttpEnvelope(
                StatusCodes.Status201Created,
                new { Secret = $"secret-{++executions}" })));
        Assert.Equal(2, executions);
        Assert.NotSame(first.Response, afterExpiry.Response);

        PlayAuthorizationIdempotencyOutcome failed = await coordinator.ExecuteAsync(
            "account:redeem",
            "retryable-failure-key",
            firstFingerprint,
            () => Task.FromResult(new PlayAuthorizationHttpEnvelope(
                StatusCodes.Status503ServiceUnavailable,
                null)));
        PlayAuthorizationIdempotencyOutcome retried = await coordinator.ExecuteAsync(
            "account:redeem",
            "retryable-failure-key",
            firstFingerprint,
            () => Task.FromResult(new PlayAuthorizationHttpEnvelope(
                StatusCodes.Status201Created,
                null)));
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, failed.Response?.StatusCode);
        Assert.Equal(StatusCodes.Status201Created, retried.Response?.StatusCode);
    }

    [Fact]
    public async Task IdempotencyCoordinatorAndLimiterFailClosedAtTheirBounds()
    {
        ManualTimeProvider time = new(BaselineUtc);
        using PlayAuthorizationIdempotencyCoordinator coordinator = new(time);
        string fingerprint = PlayAuthorizationIdempotencyCoordinator.Fingerprint("bounded-body");
        for (int index = 0; index < 1024; index++)
        {
            PlayAuthorizationIdempotencyOutcome accepted = await coordinator.ExecuteAsync(
                "account:bounded",
                $"bounded-key-{index:D4}",
                fingerprint,
                () => Task.FromResult(new PlayAuthorizationHttpEnvelope(
                    StatusCodes.Status201Created,
                    null)));
            Assert.False(accepted.CapacityExceeded);
        }

        PlayAuthorizationIdempotencyOutcome rejected = await coordinator.ExecuteAsync(
            "account:bounded",
            "bounded-key-overflow",
            fingerprint,
            () => Task.FromResult(new PlayAuthorizationHttpEnvelope(
                StatusCodes.Status201Created,
                null)));
        Assert.True(rejected.CapacityExceeded);
        Assert.Null(rejected.Response);

        using PlayAuthorizationRequestLimiter limiter = new(time);
        DefaultHttpContext context = new();
        context.Connection.RemoteIpAddress = IPAddress.Loopback;
        for (int index = 0; index < 30; index++)
        {
            Assert.True(limiter.TryAcquire(context, internalRequest: false));
        }

        Assert.False(limiter.TryAcquire(context, internalRequest: false));
        time.Advance(TimeSpan.FromMinutes(1));
        Assert.True(limiter.TryAcquire(context, internalRequest: false));

        time.Advance(TimeSpan.FromMinutes(-1));
        for (int index = 1; index < 30; index++)
        {
            Assert.True(limiter.TryAcquire(context, internalRequest: false));
        }

        Assert.False(limiter.TryAcquire(context, internalRequest: false));
    }

    private static async Task CreateSessionAndPlayerAsync(
        TestPlayApp fixture,
        HttpClient client,
        string csrf,
        string sessionId)
    {
        using HttpResponseMessage created = await fixture.SendAccountAsync(
            client,
            HttpMethod.Post,
            "/api/v1/accounts/me/play/sessions",
            SessionRequest(sessionId),
            GameMasterToken,
            $"create-{sessionId}",
            csrf);
        _ = await ReadSuccessAsync(created, HttpStatusCode.Created);

        using HttpResponseMessage participant = await fixture.SendAccountAsync(
            client,
            HttpMethod.Post,
            $"/api/v1/accounts/me/play/sessions/{sessionId}/participants",
            new AddPlayParticipantRequest(PlayerUserId, PlaySessionRoles.Player),
            GameMasterToken,
            $"participant-{sessionId}",
            csrf);
        _ = await ReadSuccessAsync(participant, HttpStatusCode.Created);
    }

    private static async Task<(string InviteId, string Secret)> IssueInviteAsync(
        TestPlayApp fixture,
        HttpClient client,
        string csrf,
        string sessionId,
        string idempotencyKey)
    {
        using HttpResponseMessage response = await fixture.SendAccountAsync(
            client,
            HttpMethod.Post,
            $"/api/v1/accounts/me/play/sessions/{sessionId}/invites",
            new IssuePlayInviteRequest(PlayerUserId, PlaySessionRoles.Player, 60),
            GameMasterToken,
            idempotencyKey,
            csrf);
        return ReadIdAndSecret(await ReadSuccessAsync(response, HttpStatusCode.Created), "inviteId");
    }

    private static async Task<(string ExchangeId, string Secret, string Body)> RedeemInviteAsync(
        TestPlayApp fixture,
        HttpClient client,
        string csrf,
        string sessionId,
        string inviteId,
        string inviteSecret,
        string idempotencyKey)
    {
        using HttpResponseMessage response = await fixture.SendAccountAsync(
            client,
            HttpMethod.Post,
            $"/api/v1/accounts/me/play/invites/{inviteId}/redeem",
            RedeemRequest(sessionId, inviteSecret),
            PlayerToken,
            idempotencyKey,
            csrf);
        string body = await ReadSuccessAsync(response, HttpStatusCode.Created);
        (string id, string secret) = ReadIdAndSecret(body, "exchangeId");
        return (id, secret, body);
    }

    private static CreatePlaySessionRequest SessionRequest(string sessionId)
        => new(sessionId, "campaign-1", "run-1", "group-1");

    private static RedeemPlayInviteRequest RedeemRequest(
        string sessionId,
        string secret,
        int exchangeLifetimeSeconds = 90)
        => new(sessionId, secret, PlaySessionRoles.Player, DeviceThumbprint, exchangeLifetimeSeconds);

    private static ConsumePlayExchangeRequest ConsumeRequest(string sessionId, string secret)
        => new(
            sessionId,
            PlayerUserId,
            PlaySessionRoles.Player,
            secret,
            DeviceThumbprint,
            300,
            3600);

    private static IntrospectPlayGrantRequest GrantRequest(string secret, string sessionId = "session-off")
        => new(sessionId, PlayerUserId, PlaySessionRoles.Player, secret, DeviceThumbprint);

    private static async Task<string> ReadSuccessAsync(HttpResponseMessage response, HttpStatusCode expected)
    {
        string body = await response.Content.ReadAsStringAsync();
        Assert.Equal(expected, response.StatusCode);
        return body;
    }

    private static (string Id, string Secret) ReadIdAndSecret(string body, string idProperty)
    {
        using JsonDocument document = JsonDocument.Parse(body);
        return (
            document.RootElement.GetProperty(idProperty).GetString()!,
            document.RootElement.GetProperty("secret").GetString()!);
    }

    private static void AssertNoStore(HttpResponseMessage response)
        => Assert.Contains(
            "no-store",
            response.Headers.CacheControl?.ToString() ?? string.Empty,
            StringComparison.OrdinalIgnoreCase);

    private static IConfiguration Configuration(
        bool enabled,
        string path,
        string? writerMode = PlayAuthorizationApiPolicy.SupportedWriterMode,
        string? internalKey = InternalKey)
        => new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                [PlayAuthorizationApiPolicy.FeatureConfigurationKey] = enabled ? "true" : "false",
                [PlayAuthorizationApiPolicy.WriterModeConfigurationKey] = writerMode,
                [PlayAuthorizationApiPolicy.InternalApiKeyConfigurationKey] = internalKey,
                ["CHUMMER_COMMUNITY_STORE_PATH"] = path
            })
            .Build();

    private static ServiceProvider LeaseProvider(IConfiguration configuration)
    {
        ServiceCollection services = new();
        services.AddSingleton(configuration);
        services.AddPlayAuthorizationProcessLease();
        return services.BuildServiceProvider();
    }

    private sealed class TogglePersistence : IPlaySessionAuthorizationPersistence
    {
        public bool ThrowAfterPersist { get; set; }

        public void PersistLocked(CommunityStore store)
        {
            store.PersistLocked();
            if (ThrowAfterPersist)
            {
                throw new IOException("injected Play authorization persistence failure");
            }
        }
    }

    private sealed class ManualTimeProvider(DateTimeOffset initialUtc) : TimeProvider
    {
        private DateTimeOffset _utcNow = initialUtc;
        private long _timestamp;

        public override DateTimeOffset GetUtcNow() => _utcNow;
        public override long GetTimestamp() => _timestamp;
        public override long TimestampFrequency => TimeSpan.TicksPerSecond;

        public void Advance(TimeSpan duration)
        {
            _utcNow = _utcNow.Add(duration);
            _timestamp = checked(_timestamp + duration.Ticks);
        }
    }

    private sealed class TestEnvironment(string environmentName) : IHostEnvironment
    {
        public string EnvironmentName { get; set; } = environmentName;
        public string ApplicationName { get; set; } = "Chummer.Tests";
        public string ContentRootPath { get; set; } = AppContext.BaseDirectory;
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }

    private sealed class TestPlayApp : IAsyncDisposable
    {
        private readonly WebApplication _app;
        private readonly string _root;

        private TestPlayApp(
            WebApplication app,
            string root,
            string storagePath,
            ManualTimeProvider time,
            TogglePersistence persistence)
        {
            _app = app;
            _root = root;
            StoragePath = storagePath;
            Time = time;
            Persistence = persistence;
        }

        public string StoragePath { get; }
        public ManualTimeProvider Time { get; }
        public TogglePersistence Persistence { get; }

        public static async Task<TestPlayApp> StartAsync(bool enabled)
        {
            string root = Path.Combine(Path.GetTempPath(), $"chummer-play-http-{Guid.NewGuid():N}");
            string storagePath = Path.Combine(root, "community.json");
            Directory.CreateDirectory(root);

            WebApplicationBuilder builder = WebApplication.CreateBuilder(new WebApplicationOptions
            {
                EnvironmentName = PlayAuthorizationApiPolicy.TestEnvironmentName
            });
            builder.WebHost.ConfigureKestrel(options => options.Listen(IPAddress.Loopback, 0));
            builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?>
            {
                [PlayAuthorizationApiPolicy.FeatureConfigurationKey] = enabled ? "true" : "false",
                [PlayAuthorizationApiPolicy.WriterModeConfigurationKey] = enabled
                    ? PlayAuthorizationApiPolicy.SupportedWriterMode
                    : null,
                [PlayAuthorizationApiPolicy.InternalApiKeyConfigurationKey] = enabled ? InternalKey : null,
                ["CHUMMER_COMMUNITY_STORE_PATH"] = storagePath,
                ["IDENTITY_SERVICE_BASE_URL"] = "http://identity.test"
            });
            PlayAuthorizationApiPolicy.ValidateStartup(builder.Configuration, builder.Environment);

            ManualTimeProvider time = new(BaselineUtc);
            TogglePersistence persistence = new();
            builder.Services.AddPlayAuthorizationProcessLease();
            builder.Services
                .AddControllersWithViews()
                .AddApplicationPart(typeof(PlayAuthorizationAccountController).Assembly);
            builder.Services.AddAuthorization();
            builder.Services.AddAntiforgery(options => options.HeaderName = "X-CSRF-TOKEN");
            builder.Services.AddDataProtection()
                .SetApplicationName("Chummer.PlayAuthorization.HttpIntegrationTests")
                .PersistKeysToFileSystem(new DirectoryInfo(Path.Combine(root, "keys")));
            builder.Services.AddSingleton<TimeProvider>(time);
            builder.Services.AddSingleton(persistence);
            builder.Services.AddSingleton<IPlaySessionAuthorizationPersistence>(persistence);
            builder.Services.AddSingleton<CommunityStore>();
            builder.Services.AddSingleton<PlaySessionAuthorizationService>();
            builder.Services.AddSingleton<PlayAuthorizationIdempotencyCoordinator>();
            builder.Services.AddSingleton<PlayAuthorizationApiPolicy>();
            builder.Services.AddSingleton<PlayAuthorizationRequestLimiter>();
            builder.Services.AddSingleton<AccountService>();
            builder.Services.AddSingleton<HubIdentitySubjectCache>();
            builder.Services.AddHttpClient<HubIdentityClient>();

            WebApplication app = builder.Build();
            app.UseRouting();
            app.UsePlayAuthorizationApiGate();
            app.UseAuthorization();
            app.UseAntiforgery();
            app.MapGet("/_test/antiforgery", (HttpContext context, IAntiforgery antiforgery) =>
            {
                AntiforgeryTokenSet tokens = antiforgery.GetAndStoreTokens(context);
                return Results.Json(new { token = tokens.RequestToken });
            });
            app.MapControllers();

            try
            {
                if (enabled)
                {
                    _ = app.Services.GetRequiredService<PlayAuthorizationProcessLease>();
                    Seed(app.Services);
                }

                await app.StartAsync();
                return new TestPlayApp(app, root, storagePath, time, persistence);
            }
            catch
            {
                await app.DisposeAsync();
                if (Directory.Exists(root))
                {
                    Directory.Delete(root, recursive: true);
                }

                throw;
            }
        }

        public HttpClient CreateClient()
        {
            IServer server = _app.Services.GetRequiredService<IServer>();
            IServerAddressesFeature addresses = server.Features.Get<IServerAddressesFeature>()
                ?? throw new InvalidOperationException("Kestrel did not expose a bound address.");
            return new HttpClient(new HttpClientHandler
            {
                CookieContainer = new CookieContainer(),
                UseCookies = true
            })
            {
                BaseAddress = new Uri(addresses.Addresses.Single())
            };
        }

        public async Task<string> GetAntiforgeryTokenAsync(HttpClient client)
        {
            using HttpResponseMessage response = await client.GetAsync("/_test/antiforgery");
            response.EnsureSuccessStatusCode();
            using JsonDocument document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
            return document.RootElement.GetProperty("token").GetString()!;
        }

        public Task<HttpResponseMessage> SendAccountAsync(
            HttpClient client,
            HttpMethod method,
            string path,
            object? body,
            string? bearer,
            string idempotencyKey,
            string csrf)
        {
            HttpRequestMessage request = new(method, path);
            if (body is not null)
            {
                request.Content = JsonContent.Create(body);
            }

            if (bearer is not null)
            {
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", bearer);
            }

            request.Headers.TryAddWithoutValidation("Idempotency-Key", idempotencyKey);
            request.Headers.TryAddWithoutValidation("X-CSRF-TOKEN", csrf);
            return client.SendAsync(request);
        }

        public Task<HttpResponseMessage> SendInternalAsync(
            HttpClient client,
            string path,
            object body,
            string? idempotencyKey,
            string? serviceKey,
            string? bearer = null)
        {
            HttpRequestMessage request = new(HttpMethod.Post, path)
            {
                Content = JsonContent.Create(body)
            };
            if (idempotencyKey is not null)
            {
                request.Headers.TryAddWithoutValidation("Idempotency-Key", idempotencyKey);
            }

            if (serviceKey is not null)
            {
                request.Headers.TryAddWithoutValidation(PlayAuthorizationApiPolicy.InternalApiKeyHeader, serviceKey);
            }

            if (bearer is not null)
            {
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", bearer);
            }

            return client.SendAsync(request);
        }

        public async ValueTask DisposeAsync()
        {
            await _app.StopAsync();
            await _app.DisposeAsync();
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }

        private static void Seed(IServiceProvider services)
        {
            CommunityStore store = services.GetRequiredService<CommunityStore>();
            HubIdentitySubjectCache cache = services.GetRequiredService<HubIdentitySubjectCache>();
            lock (store.Gate)
            {
                AddUser(store, GameMasterUserId, GameMasterSubject, "Game Master", "gm", "gm@example.invalid");
                AddUser(store, PlayerUserId, PlayerSubject, "Player", "player", "player@example.invalid");
                GroupDto group = new(
                    GroupId: "group-1",
                    GroupType: "campaign",
                    Name: "Play HTTP Group",
                    Visibility: "private",
                    OwnerUserId: GameMasterUserId,
                    Capabilities: [],
                    Memberships: [],
                    CreatedAtUtc: BaselineUtc,
                    UpdatedAtUtc: BaselineUtc);
                CampaignProjection campaign = new(
                    CampaignId: "campaign-1",
                    GroupId: group.GroupId,
                    Name: "Play HTTP Campaign",
                    Status: "active",
                    Visibility: "private",
                    Summary: "HTTP integration campaign",
                    RuleEnvironment: new RuleEnvironmentRef(
                        "rules-1",
                        "campaign",
                        "rules-v1",
                        "approved",
                        [],
                        [],
                        []),
                    ActiveRunId: "run-1",
                    CrewIds: ["crew-1"],
                    DossierIds: [],
                    RunIds: ["run-1"],
                    LatestContinuity: null,
                    CreatedAtUtc: BaselineUtc,
                    UpdatedAtUtc: BaselineUtc);
                RunProjection run = new(
                    RunId: "run-1",
                    CampaignId: campaign.CampaignId,
                    Title: "Play HTTP Run",
                    Status: "active",
                    Summary: "HTTP integration run",
                    ActiveSceneId: null,
                    Objectives: [],
                    Scenes: [],
                    LatestContinuity: null,
                    CreatedAtUtc: BaselineUtc,
                    UpdatedAtUtc: BaselineUtc);
                CrewProjection crew = new(
                    CrewId: "crew-1",
                    Name: "Play HTTP Crew",
                    Visibility: "private",
                    GroupId: group.GroupId,
                    CampaignId: campaign.CampaignId,
                    Members:
                    [
                        new CrewAssignmentProjection(
                            PlayerUserId,
                            "dossier-1",
                            "runner",
                            "available",
                            BaselineUtc)
                    ],
                    CreatedAtUtc: BaselineUtc,
                    UpdatedAtUtc: BaselineUtc);
                store.GroupsById[group.GroupId] = group;
                store.CampaignSpinesById[campaign.CampaignId] = campaign;
                store.RunsById[run.RunId] = run;
                store.CrewsById[crew.CrewId] = crew;
                store.PersistLocked();
            }

            cache.Set(
                "http://identity.test",
                GameMasterToken,
                new AuthenticatedHubSubject(
                    GameMasterSubject,
                    "Game Master",
                    "gm@example.invalid",
                    ["gm"],
                    GameMasterToken),
                TimeSpan.FromHours(1));
            cache.Set(
                "http://identity.test",
                PlayerToken,
                new AuthenticatedHubSubject(
                    PlayerSubject,
                    "Player",
                    "player@example.invalid",
                    ["player"],
                    PlayerToken),
                TimeSpan.FromHours(1));
            cache.Set(
                "http://identity.test",
                IntruderToken,
                new AuthenticatedHubSubject(
                    IntruderSubject,
                    "Intruder",
                    "intruder@example.invalid",
                    ["player"],
                    IntruderToken),
                TimeSpan.FromHours(1));
        }

        private static void AddUser(
            CommunityStore store,
            string userId,
            string subjectId,
            string displayName,
            string handle,
            string email)
        {
            HubUserDto user = new(
                UserId: userId,
                SubjectId: subjectId,
                DisplayName: displayName,
                Handle: handle,
                Visibility: "private",
                Timezone: "UTC",
                CountryCode: string.Empty,
                LinkedPrincipals: [subjectId],
                GroupIds: ["group-1"],
                CreatedAtUtc: BaselineUtc,
                UpdatedAtUtc: BaselineUtc)
            {
                Email = email
            };
            store.UsersById[user.UserId] = user;
            store.UserIdBySubjectId[user.SubjectId] = user.UserId;
        }
    }
}
