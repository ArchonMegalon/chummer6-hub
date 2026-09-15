using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Chummer.Run.Contracts.Identity;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Primitives;
using Xunit;

namespace Chummer.Tests;

public sealed class HubSessionAccountAdmissionServiceTests
{
    private const string Token = "admission-secret-sentinel_123";
    private const string Subject = "subject.admission";
    private const string Session = "session.admission";
    private static readonly DateTimeOffset Baseline = new(2030, 1, 2, 3, 4, 5, TimeSpan.Zero);

    [Fact]
    public void DependencyInjectionUsesABoundedClientWithoutRedirectsCookiesOrTransportLogging()
    {
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddSingleton<IConfiguration>(new ConfigurationBuilder().Build());
        services.AddHubAccountsAndCommunityContext();
        using ServiceProvider provider = services.BuildServiceProvider();
        using HttpClient client = provider.GetRequiredService<IHttpClientFactory>()
            .CreateClient(nameof(HubSessionAccountAdmissionService));
        HttpMessageHandler handler = provider.GetRequiredService<IHttpMessageHandlerFactory>()
            .CreateHandler(nameof(HubSessionAccountAdmissionService));

        Assert.Equal(TimeSpan.FromSeconds(10), client.Timeout);
        while (handler is DelegatingHandler delegating)
        {
            Assert.DoesNotContain("Logging", handler.GetType().Name, StringComparison.Ordinal);
            handler = Assert.IsAssignableFrom<HttpMessageHandler>(delegating.InnerHandler);
        }
        SocketsHttpHandler primary = Assert.IsType<SocketsHttpHandler>(handler);
        Assert.False(primary.AllowAutoRedirect);
        Assert.False(primary.UseCookies);
        Assert.Equal(TimeSpan.FromSeconds(5), primary.ConnectTimeout);
        Assert.Equal(16, primary.MaxResponseHeadersLength);
    }

    [Fact]
    public async Task EveryAdmissionIntrospectsAgainAndReturnsOnlyTheExistingAccountObservation()
    {
        using var fixture = new Fixture();
        StoreSnapshot before = fixture.Snapshot();

        HubSessionAccountObservation first = await fixture.Admit();
        fixture.Clock.Advance(TimeSpan.FromSeconds(1));
        HubSessionAccountObservation second = await fixture.Admit();

        Assert.Equal(fixture.User!.UserId, first.UserId);
        Assert.Equal(Subject, first.SubjectId);
        Assert.Equal(Session, first.SessionId);
        Assert.Equal(Baseline, first.ObservedAtUtc);
        Assert.Equal(Baseline.AddHours(1), first.ExpiresAtUtc);
        Assert.Equal(Baseline.AddSeconds(1), second.ObservedAtUtc);
        Assert.Equal(2, fixture.Handler.Calls);
        Assert.All(fixture.Handler.Tokens, token => Assert.Equal(Token, token));
        Assert.Equal(
            new[] { "ExpiresAtUtc", "ObservedAtUtc", "SessionId", "SubjectId", "UserId" },
            typeof(HubSessionAccountObservation).GetProperties().Select(property => property.Name).Order());
        Assert.DoesNotContain(Token, JsonSerializer.Serialize(first), StringComparison.Ordinal);
        fixture.AssertUnchanged(before);
    }

    [Fact]
    public async Task RevocationImmediatelyRejectsTheSamePreviouslyAdmittedRequest()
    {
        using var fixture = new Fixture();
        await fixture.Admit();
        fixture.Handler.Respond = (_, _) => Task.FromResult(Json(
            "{\"active\":false,\"subjectId\":null,\"sessionId\":null,\"expiresAtUtc\":null}"));

        await fixture.Deny(StatusCodes.Status401Unauthorized);

        Assert.Equal(2, fixture.Handler.Calls);
    }

    [Fact]
    public async Task LoopbackHostAndDevelopmentIdentitySettingsStillRequireFreshIntrospection()
    {
        using var fixture = new Fixture(settings: new Dictionary<string, string?>
        {
            ["CHUMMER_LOCAL_E2E_ACCESS_TOKEN"] = Token,
            ["CHUMMER_LOCAL_E2E_SUBJECT_ID"] = "subject.seeded.admin",
            ["CHUMMER_LOCAL_E2E_DISPLAY_NAME"] = "Seeded administrator",
            ["CHUMMER_LOCAL_E2E_ROLES"] = "admin",
            ["CHUMMER_IDENTITY_SUBJECT_CACHE_SECONDS"] = "300"
        });
        fixture.Request.Host = new HostString("localhost");
        fixture.Request.HttpContext.Connection.RemoteIpAddress = IPAddress.Loopback;
        fixture.Request.Headers.Cookie = $"{HubBrowserAuthConstants.AccessTokenCookieName}={Token}; "
            + $"{HubBrowserAuthConstants.SubjectHintCookieName}=subject.seeded.admin";

        HubSessionAccountObservation observation = await fixture.Admit();

        Assert.Equal(Subject, observation.SubjectId);
        Assert.Equal(1, fixture.Handler.Calls);

        fixture.Handler.Respond = (_, _) => Task.FromResult(Json(
            "{\"active\":false,\"subjectId\":null,\"sessionId\":null,\"expiresAtUtc\":null}"));
        await fixture.Deny(StatusCodes.Status401Unauthorized);
        Assert.Equal(2, fixture.Handler.Calls);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task PrimaryAndSecondaryPrincipalMappingsUseTheSameExistingCanonicalAccount(bool secondary)
    {
        using var fixture = new Fixture();
        string introspectedSubject = secondary ? "subject.secondary" : Subject.ToUpperInvariant();
        if (secondary)
        {
            HubUserDto linked = fixture.User! with { LinkedPrincipals = [Subject, introspectedSubject] };
            fixture.Store.UsersById[linked.UserId] = linked;
            fixture.Store.UserIdBySubjectId[introspectedSubject] = linked.UserId;
            fixture.Persist();
        }
        fixture.Handler.Respond = (_, _) => Task.FromResult(Json(ValidJson(subject: introspectedSubject)));
        StoreSnapshot before = fixture.Snapshot();

        HubSessionAccountObservation observation = await fixture.Admit();

        Assert.Equal(fixture.User!.UserId, observation.UserId);
        Assert.Equal(introspectedSubject, observation.SubjectId);
        fixture.AssertUnchanged(before);
    }

    [Fact]
    public async Task OrdinaryProfileAndGroupUpdatesBetweenAdmissionsPreserveTheAccountId()
    {
        using var fixture = new Fixture();
        HubSessionAccountObservation first = await fixture.Admit();
        var accounts = new AccountService(fixture.Store);
        accounts.UpsertProfile(new UpsertHubUserProfileRequest(Subject, DisplayName: "Updated Runner"));
        HubUserDto updated = accounts.UpdateGroupMemberships(fixture.User!.UserId, ["group.updated"]);
        Assert.NotSame(fixture.User, updated);
        Assert.Equal("Updated Runner", updated.DisplayName);
        Assert.Equal("group.updated", Assert.Single(updated.GroupIds));
        StoreSnapshot beforeSecondAdmission = fixture.Snapshot();

        HubSessionAccountObservation second = await fixture.Admit();

        Assert.Equal(first.UserId, second.UserId);
        Assert.Equal(2, fixture.Handler.Calls);
        fixture.AssertUnchanged(beforeSecondAdmission);
    }

    [Fact]
    public async Task MissingAccountDoesNotCreateOrUpdateAnAccount()
    {
        using var fixture = new Fixture(seedAccount: false);

        await fixture.Deny(StatusCodes.Status403Forbidden);

        Assert.Empty(fixture.Store.UsersById);
        Assert.Empty(fixture.Store.UserIdBySubjectId);
        Assert.False(File.Exists(fixture.Store.StoragePath));
    }

    [Fact]
    public async Task DeletedAccountIsNotRecreatedFromAStillActiveIdentitySession()
    {
        using var fixture = new Fixture();
        await fixture.Admit();
        fixture.Store.UsersById.Clear();
        fixture.Store.UserIdBySubjectId.Clear();
        fixture.Persist();

        await fixture.Deny(StatusCodes.Status403Forbidden);

        Assert.Empty(fixture.Store.UsersById);
        Assert.Equal(2, fixture.Handler.Calls);
    }

    [Theory]
    [InlineData("unrelated_subject")]
    [InlineData("dangling_index")]
    [InlineData("mismatched_canonical_id")]
    [InlineData("empty_user_id")]
    public async Task InconsistentAccountMappingsFailClosedWithoutRepairingStorage(string inconsistency)
    {
        using var fixture = new Fixture();
        switch (inconsistency)
        {
            case "unrelated_subject":
                fixture.Store.UsersById[fixture.User!.UserId] = fixture.User with
                {
                    SubjectId = "subject.other",
                    LinkedPrincipals = ["subject.other"]
                };
                break;
            case "dangling_index":
                fixture.Store.UserIdBySubjectId[Subject] = "usr-missing";
                break;
            case "mismatched_canonical_id":
                fixture.Store.UsersById[fixture.User!.UserId] = fixture.User with { UserId = "usr-other" };
                break;
            case "empty_user_id":
                fixture.Store.UsersById[fixture.User!.UserId] = fixture.User with { UserId = "" };
                break;
        }

        await fixture.Deny(StatusCodes.Status403Forbidden);
    }

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("Basic admission-secret-sentinel_123")]
    [InlineData("Bearer")]
    [InlineData("Bearer ")]
    [InlineData(" Bearer token")]
    [InlineData("Bearer  token")]
    [InlineData("Bearer\ttoken")]
    [InlineData("Bearer token ")]
    [InlineData("Bearer tok en")]
    [InlineData("Bearer tok\nen")]
    [InlineData("Bearer tok\ren")]
    [InlineData("Bearer token,second")]
    [InlineData("Bearer tokén")]
    [InlineData("Bearer token?query")]
    [InlineData("Bearer =")]
    [InlineData("Bearer to=ken")]
    public async Task MissingOrMalformedAuthorizationCannotReachIdentity(string? authorization)
    {
        using var fixture = new Fixture();
        fixture.Request.Headers.Remove("Authorization");
        fixture.Request.Headers.Cookie = $"{HubBrowserAuthConstants.SubjectHintCookieName}={Subject}; "
            + $"{HubBrowserAuthConstants.AccessTokenCookieName}={Token}";
        fixture.Request.QueryString = new QueryString("?subjectId=subject.admission&access_token=" + Token);
        if (authorization is not null)
        {
            fixture.Request.Headers.Authorization = authorization;
        }

        await fixture.Deny(StatusCodes.Status401Unauthorized);

        Assert.Equal(0, fixture.Handler.Calls);
    }

    [Fact]
    public async Task MultipleAuthorizationValuesCannotReachIdentity()
    {
        using var fixture = new Fixture();
        fixture.Request.Headers.Authorization = new StringValues(["Bearer " + Token, "Bearer another"]);

        await fixture.Deny(StatusCodes.Status401Unauthorized);

        Assert.Equal(0, fixture.Handler.Calls);
    }

    [Fact]
    public async Task OverlongBearerCannotReachIdentity()
    {
        using var fixture = new Fixture();
        fixture.Request.Headers.Authorization = "Bearer " + new string('a', 513);

        await fixture.Deny(StatusCodes.Status401Unauthorized);

        Assert.Equal(0, fixture.Handler.Calls);
    }

    [Theory]
    [InlineData("bEaReR", "aAZ09-._~+/==")]
    [InlineData("Bearer", "maximum")]
    public async Task ValidBearerAlphabetAndMaximumLengthAreForwardedExactly(string scheme, string token)
    {
        using var fixture = new Fixture();
        string value = token == "maximum" ? new string('a', 512) : token;
        fixture.Request.Headers.Authorization = scheme + " " + value;

        await fixture.Admit();

        Assert.Equal(value, Assert.Single(fixture.Handler.Tokens));
    }

    [Theory]
    [InlineData(204)]
    [InlineData(301)]
    [InlineData(401)]
    [InlineData(403)]
    [InlineData(429)]
    [InlineData(500)]
    [InlineData(503)]
    public async Task NonSuccessIdentityStatusFailsAsUnavailableWithoutEchoingItsBody(int status)
    {
        using var fixture = new Fixture();
        fixture.Handler.Respond = (_, _) => Task.FromResult(new HttpResponseMessage((HttpStatusCode)status)
        {
            Content = new StringContent("upstream-secret-sentinel " + Token)
        });

        int expectedStatus = status is 401 or 403
            ? StatusCodes.Status401Unauthorized
            : StatusCodes.Status503ServiceUnavailable;
        HubRequestAuthException failure = await fixture.Deny(expectedStatus);

        Assert.DoesNotContain("upstream-secret-sentinel", failure.ToString(), StringComparison.Ordinal);
        fixture.AssertNoSecrets("upstream-secret-sentinel");
    }

    [Theory]
    [InlineData("not JSON admission-secret-sentinel_123")]
    [InlineData("null")]
    [InlineData("[]")]
    [InlineData("{\"active\":\"true\"}")]
    public async Task MalformedJsonOrAmbiguousActiveFieldsFailClosed(string body)
    {
        using var fixture = new Fixture();
        fixture.Handler.Respond = (_, _) => Task.FromResult(Json(body));

        await fixture.Deny(StatusCodes.Status503ServiceUnavailable);
    }

    [Fact]
    public async Task UnknownMemberInAnOtherwiseValidIdentityResponseIsRejected()
    {
        using var fixture = new Fixture();
        JsonObject body = JsonNode.Parse(ValidJson())!.AsObject();
        body["unknownMember"] = "unknown-member-secret " + Token;
        fixture.Handler.Respond = (_, _) => Task.FromResult(Json(body.ToJsonString()));

        HubRequestAuthException failure = await fixture.Deny(StatusCodes.Status503ServiceUnavailable);

        Assert.DoesNotContain("unknown-member-secret", failure.ToString(), StringComparison.Ordinal);
        fixture.AssertNoSecrets("unknown-member-secret");
    }

    [Theory]
    [InlineData("not an absolute endpoint")]
    [InlineData("https://identity.example.invalid?unexpected=query")]
    [InlineData("https://user:admission-secret-sentinel_123@identity.example.invalid")]
    public async Task InvalidIdentityEndpointConfigurationNeverReachesTheNetwork(string endpoint)
    {
        using var fixture = new Fixture(settings: new Dictionary<string, string?>
        {
            ["IDENTITY_SERVICE_BASE_URL"] = endpoint
        });

        await fixture.Deny(StatusCodes.Status503ServiceUnavailable);

        Assert.Equal(0, fixture.Handler.Calls);
    }

    [Theory]
    [InlineData("active")]
    [InlineData("subjectId")]
    [InlineData("sessionId")]
    [InlineData("expiresAtUtc")]
    [InlineData("roles")]
    public async Task DuplicateKnownJsonMembersAreRejectedCaseInsensitively(string member)
    {
        using var fixture = new Fixture();
        string body = ValidJson();
        string duplicateValue = JsonNode.Parse(body)![member]!.ToJsonString();
        body = body[..^1] + ",\"" + member.ToUpperInvariant() + "\":" + duplicateValue + "}";
        fixture.Handler.Respond = (_, _) => Task.FromResult(Json(body));

        await fixture.Deny(StatusCodes.Status503ServiceUnavailable);
    }

    [Theory]
    [InlineData("active", false)]
    [InlineData("subjectId", false)]
    [InlineData("sessionId", false)]
    [InlineData("expiresAtUtc", false)]
    [InlineData("subjectId", true)]
    [InlineData("sessionId", true)]
    [InlineData("expiresAtUtc", true)]
    public async Task MissingRequiredMembersAndNullSessionValuesFailClosed(string member, bool presentNull)
    {
        using var fixture = new Fixture();
        JsonObject body = JsonNode.Parse(ValidJson())!.AsObject();
        if (presentNull)
        {
            body[member] = null;
        }
        else
        {
            body.Remove(member);
        }
        fixture.Handler.Respond = (_, _) => Task.FromResult(Json(body.ToJsonString()));

        await fixture.Deny(presentNull ? StatusCodes.Status401Unauthorized : StatusCodes.Status503ServiceUnavailable);
    }

    [Theory]
    [InlineData("subjectId", "42")]
    [InlineData("sessionId", "[]")]
    [InlineData("expiresAtUtc", "{}")]
    [InlineData("roles", "{}")]
    [InlineData("roles", "[42]")]
    public async Task KnownJsonMembersWithWrongTypesAreRejected(string member, string replacementJson)
    {
        using var fixture = new Fixture();
        JsonObject body = JsonNode.Parse(ValidJson())!.AsObject();
        body[member] = JsonNode.Parse(replacementJson);
        fixture.Handler.Respond = (_, _) => Task.FromResult(Json(body.ToJsonString()));

        await fixture.Deny(StatusCodes.Status503ServiceUnavailable);
    }

    [Theory]
    [InlineData("subjectId", "")]
    [InlineData("subjectId", " subject.admission")]
    [InlineData("subjectId", "subject. admission")]
    [InlineData("subjectId", "subject.admission\n")]
    [InlineData("sessionId", "")]
    [InlineData("sessionId", "session. admission")]
    [InlineData("sessionId", "session.admission\u0000")]
    public async Task InvalidSubjectAndSessionIdentifiersAreNeverAdmitted(string member, string value)
    {
        using var fixture = new Fixture();
        JsonObject body = JsonNode.Parse(ValidJson())!.AsObject();
        body[member] = value;
        fixture.Handler.Respond = (_, _) => Task.FromResult(Json(body.ToJsonString()));

        await fixture.Deny(StatusCodes.Status401Unauthorized);
    }

    [Theory]
    [InlineData("subjectId", false)]
    [InlineData("sessionId", false)]
    [InlineData("subjectId", true)]
    [InlineData("sessionId", true)]
    public async Task IdentifierLimitsApplyToUtf8Bytes(string member, bool multibyte)
    {
        using var fixture = new Fixture();
        JsonObject body = JsonNode.Parse(ValidJson())!.AsObject();
        body[member] = multibyte ? new string('é', 65) : new string('a', 129);
        fixture.Handler.Respond = (_, _) => Task.FromResult(Json(body.ToJsonString()));

        await fixture.Deny(StatusCodes.Status401Unauthorized);
    }

    [Theory]
    [InlineData(-1)]
    [InlineData(0)]
    public async Task ExpiredOrExactlyExpiringIdentitySessionsAreRejected(int secondsFromNow)
    {
        using var fixture = new Fixture();
        fixture.Handler.Respond = (_, _) => Task.FromResult(Json(ValidJson(expires: Baseline.AddSeconds(secondsFromNow))));

        await fixture.Deny(StatusCodes.Status401Unauthorized);
    }

    [Fact]
    public async Task IdentitySessionExpiringWhileResponseIsAwaitedIsRejected()
    {
        using var fixture = new Fixture();
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var response = new TaskCompletionSource<HttpResponseMessage>(TaskCreationOptions.RunContinuationsAsynchronously);
        fixture.Handler.Respond = (_, _) =>
        {
            started.SetResult();
            return response.Task;
        };
        StoreSnapshot before = fixture.Snapshot();
        Task<HubSessionAccountObservation> pending = fixture.Admit();
        await started.Task;
        fixture.Clock.Advance(TimeSpan.FromHours(1));
        response.SetResult(Json(ValidJson()));

        HubRequestAuthException failure = await Assert.ThrowsAsync<HubRequestAuthException>(() => pending);

        Assert.Equal(StatusCodes.Status401Unauthorized, failure.StatusCode);
        fixture.AssertUnchanged(before);
    }

    [Fact]
    public async Task IdentitySessionExpiringDuringBodyReadIsRejected()
    {
        using var fixture = new Fixture();
        var stream = new CountingReadStream(Encoding.UTF8.GetBytes(ValidJson()),
            () => fixture.Clock.Advance(TimeSpan.FromHours(1)));
        fixture.Handler.Respond = (_, _) => Task.FromResult(StreamJson(stream));

        await fixture.Deny(StatusCodes.Status401Unauthorized);

        Assert.True(stream.BytesRead > 0);
    }

    [Fact]
    public async Task ExpiryIsRecheckedAfterReadingTheExistingAccount()
    {
        using var fixture = new Fixture();
        fixture.Clock.BeforeRead = read =>
        {
            if (read == 2)
            {
                fixture.Clock.Advance(TimeSpan.FromHours(1));
            }
        };

        await fixture.Deny(StatusCodes.Status401Unauthorized);

        Assert.Equal(2, fixture.Clock.Reads);
    }

    [Theory]
    [InlineData("application/json")]
    [InlineData("application/identity+json")]
    public async Task SupportedJsonMediaTypesAndOptionalRolesDoNotRequireAProfileFetch(string mediaType)
    {
        using var fixture = new Fixture();
        JsonObject body = JsonNode.Parse(ValidJson())!.AsObject();
        body.Remove("roles");
        fixture.Handler.Respond = (_, _) => Task.FromResult(Json(body.ToJsonString(), mediaType));

        await fixture.Admit();

        Assert.Equal(1, fixture.Handler.Calls);
    }

    [Theory]
    [InlineData("text/plain")]
    [InlineData("text/html")]
    [InlineData("text/json")]
    public async Task UnexpectedContentTypesAreRejected(string mediaType)
    {
        using var fixture = new Fixture();
        fixture.Handler.Respond = (_, _) => Task.FromResult(Json(ValidJson(), mediaType));

        await fixture.Deny(StatusCodes.Status503ServiceUnavailable);
    }

    [Fact]
    public async Task EncodedIdentityResponseIsRejected()
    {
        using var fixture = new Fixture();
        fixture.Handler.Respond = (_, _) =>
        {
            HttpResponseMessage response = Json(ValidJson());
            response.Content.Headers.ContentEncoding.Add("gzip");
            return Task.FromResult(response);
        };

        await fixture.Deny(StatusCodes.Status503ServiceUnavailable);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task OversizedIdentityBodyIsRejectedWithABoundedRead(bool declaredLength)
    {
        using var fixture = new Fixture();
        var stream = new CountingReadStream(Encoding.UTF8.GetBytes(new string(' ', 131072)));
        fixture.Handler.Respond = (_, _) =>
        {
            HttpResponseMessage response = StreamJson(stream);
            if (declaredLength)
            {
                response.Content.Headers.ContentLength = 131072;
            }
            return Task.FromResult(response);
        };

        await fixture.Deny(StatusCodes.Status503ServiceUnavailable);

        Assert.InRange(stream.BytesRead, 0, 65537);
        if (!declaredLength)
        {
            Assert.Equal(65537, stream.BytesRead);
        }
    }

    [Fact]
    public async Task ChunkedJsonBodyAtTheExactByteLimitRemainsAdmissible()
    {
        using var fixture = new Fixture();
        string body = ValidJson();
        int remaining = 65536 - Encoding.UTF8.GetByteCount(body);
        var stream = new CountingReadStream(Encoding.UTF8.GetBytes(body + new string(' ', remaining)));
        fixture.Handler.Respond = (_, _) => Task.FromResult(StreamJson(stream));

        await fixture.Admit();

        Assert.Equal(65536, stream.BytesRead);
    }

    [Fact]
    public async Task StalledResponseBodyIsCanceledByTheRealAdmissionDeadline()
    {
        using var fixture = new Fixture();
        var stream = new CountingReadStream([], stallUntilCancellation: true);
        fixture.Handler.Respond = (_, _) => Task.FromResult(StreamJson(stream));
        var elapsed = System.Diagnostics.Stopwatch.StartNew();

        await fixture.Deny(StatusCodes.Status503ServiceUnavailable).WaitAsync(TimeSpan.FromSeconds(30));

        Assert.True(stream.ObservedCancellation);
        Assert.Equal(0, stream.BytesRead);
        Assert.True(elapsed.Elapsed >= TimeSpan.FromSeconds(9));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task TransportFailureAndUpstreamCancellationExposeNoCredentialOrExceptionDetails(bool timeout)
    {
        using var fixture = new Fixture();
        fixture.Handler.Respond = (_, _) => throw (timeout
            ? new TaskCanceledException("transport-secret-sentinel " + Token)
            : new HttpRequestException("transport-secret-sentinel " + Token));

        HubRequestAuthException failure = await fixture.Deny(StatusCodes.Status503ServiceUnavailable);

        Assert.Null(failure.InnerException);
        Assert.DoesNotContain("transport-secret-sentinel", failure.ToString(), StringComparison.Ordinal);
        fixture.AssertNoSecrets("transport-secret-sentinel");
    }

    [Fact]
    public async Task CallerCancellationPropagatesWithoutRetainingAnUpstreamSecretException()
    {
        using var fixture = new Fixture();
        using var cancellation = new CancellationTokenSource();
        fixture.Handler.Respond = (_, _) =>
        {
            cancellation.Cancel();
            throw new OperationCanceledException("cancel-secret-sentinel " + Token, cancellation.Token);
        };
        StoreSnapshot before = fixture.Snapshot();

        OperationCanceledException failure = await Assert.ThrowsAnyAsync<OperationCanceledException>(
            () => fixture.Service.RequireAccountAsync(fixture.Request, cancellation.Token));

        Assert.Null(failure.InnerException);
        Assert.DoesNotContain(Token, failure.ToString(), StringComparison.Ordinal);
        Assert.DoesNotContain("cancel-secret-sentinel", failure.ToString(), StringComparison.Ordinal);
        fixture.AssertNoSecrets("cancel-secret-sentinel");
        fixture.AssertUnchanged(before);
    }

    private static string ValidJson(string subject = Subject, DateTimeOffset? expires = null)
        => JsonSerializer.Serialize(new IdentityIntrospectionResponse(
            Active: true,
            SessionId: Session,
            SubjectId: subject,
            Roles: ["player"],
            ExpiresAtUtc: expires ?? Baseline.AddHours(1)), new JsonSerializerOptions(JsonSerializerDefaults.Web));

    private static HttpResponseMessage Json(string body, string mediaType = "application/json")
        => new(HttpStatusCode.OK) { Content = new StringContent(body, Encoding.UTF8, mediaType) };

    private static HttpResponseMessage StreamJson(Stream stream)
    {
        var content = new StreamContent(stream);
        content.Headers.ContentType = new MediaTypeHeaderValue("application/json");
        return new HttpResponseMessage(HttpStatusCode.OK) { Content = content };
    }

    private sealed record StoreSnapshot(byte[]? Bytes, string Accounts, string Mappings, string[] Files);

    private sealed class Fixture : IDisposable
    {
        private readonly string _directory = Path.Combine(Path.GetTempPath(), "hub-admission-tests", Guid.NewGuid().ToString("N"));
        private readonly HttpClient _http;

        public Fixture(bool seedAccount = true, Dictionary<string, string?>? settings = null)
        {
            Directory.CreateDirectory(_directory);
            var configurationValues = new Dictionary<string, string?>
            {
                ["IDENTITY_SERVICE_BASE_URL"] = "https://identity.example.invalid",
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_directory, "community.json")
            };
            foreach ((string key, string? value) in settings ?? [])
            {
                configurationValues[key] = value;
            }
            IConfiguration configuration = new ConfigurationBuilder().AddInMemoryCollection(configurationValues).Build();
            Store = new CommunityStore(configuration, NullLogger<CommunityStore>.Instance);
            var accounts = new AccountService(Store);
            User = seedAccount ? accounts.EnsureUser(Subject, "Existing Runner", "runner@example.invalid") : null;
            Handler = new IdentityHandler();
            _http = new HttpClient(Handler);
            Service = new HubSessionAccountAdmissionService(_http, configuration, accounts, Clock, Logger);
            Request = new DefaultHttpContext().Request;
            Request.Host = new HostString("chummer.run");
            Request.Headers.Authorization = "Bearer " + Token;
        }

        public CommunityStore Store { get; }
        public HubUserDto? User { get; }
        public IdentityHandler Handler { get; }
        public ManualTimeProvider Clock { get; } = new(Baseline);
        public CapturingLogger Logger { get; } = new();
        public HubSessionAccountAdmissionService Service { get; }
        public HttpRequest Request { get; }

        public Task<HubSessionAccountObservation> Admit()
            => Service.RequireAccountAsync(Request, CancellationToken.None);

        public async Task<HubRequestAuthException> Deny(int statusCode)
        {
            StoreSnapshot before = Snapshot();
            HubRequestAuthException failure = await Assert.ThrowsAsync<HubRequestAuthException>(Admit);
            Assert.Equal(statusCode, failure.StatusCode);
            Assert.Null(failure.InnerException);
            Assert.DoesNotContain(Token, failure.ToString(), StringComparison.Ordinal);
            AssertNoSecrets();
            AssertUnchanged(before);
            return failure;
        }

        public void Persist()
        {
            lock (Store.Gate)
            {
                Store.PersistLocked();
            }
        }

        public StoreSnapshot Snapshot()
            => new(
                File.Exists(Store.StoragePath) ? File.ReadAllBytes(Store.StoragePath) : null,
                JsonSerializer.Serialize(Store.UsersById),
                JsonSerializer.Serialize(Store.UserIdBySubjectId),
                Directory.GetFiles(_directory).Order().ToArray());

        public void AssertUnchanged(StoreSnapshot before)
        {
            StoreSnapshot after = Snapshot();
            Assert.Equal(before.Bytes, after.Bytes);
            Assert.Equal(before.Accounts, after.Accounts);
            Assert.Equal(before.Mappings, after.Mappings);
            Assert.Equal(before.Files, after.Files);
        }

        public void AssertNoSecrets(string? extra = null)
        {
            Assert.DoesNotContain(Token, Logger.Text, StringComparison.Ordinal);
            if (extra is not null)
            {
                Assert.DoesNotContain(extra, Logger.Text, StringComparison.Ordinal);
            }
        }

        public void Dispose()
        {
            _http.Dispose();
            Directory.Delete(_directory, recursive: true);
        }
    }

    private sealed class IdentityHandler : HttpMessageHandler
    {
        public int Calls { get; private set; }
        public List<string> Tokens { get; } = [];
        public Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> Respond { get; set; }
            = (_, _) => Task.FromResult(Json(ValidJson()));

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Calls++;
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("https://identity.example.invalid/api/v1/identity/introspect", request.RequestUri?.AbsoluteUri);
            Assert.NotNull(request.Content);
            IdentityIntrospectionRequest? body = JsonSerializer.Deserialize<IdentityIntrospectionRequest>(
                await request.Content.ReadAsStringAsync(cancellationToken),
                new JsonSerializerOptions(JsonSerializerDefaults.Web));
            Tokens.Add(Assert.IsType<IdentityIntrospectionRequest>(body).AccessToken);
            return await Respond(request, cancellationToken);
        }
    }

    private sealed class ManualTimeProvider(DateTimeOffset now) : TimeProvider
    {
        private DateTimeOffset _now = now;
        public int Reads { get; private set; }
        public Action<int>? BeforeRead { get; set; }
        public override DateTimeOffset GetUtcNow()
        {
            BeforeRead?.Invoke(++Reads);
            return _now;
        }
        public void Advance(TimeSpan duration) => _now += duration;
    }

    private sealed class CapturingLogger : ILogger<HubSessionAccountAdmissionService>
    {
        private readonly StringBuilder _text = new();
        public string Text => _text.ToString();
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;
        public bool IsEnabled(LogLevel logLevel) => true;
        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception,
            Func<TState, Exception?, string> formatter)
        {
            _text.AppendLine(formatter(state, exception));
            if (exception is not null)
            {
                _text.AppendLine(exception.ToString());
            }
        }
    }

    private sealed class CountingReadStream(
        byte[] bytes,
        Action? beforeFirstRead = null,
        bool stallUntilCancellation = false) : Stream
    {
        private int _position;
        private bool _started;
        public int BytesRead => _position;
        public bool ObservedCancellation { get; private set; }
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override void Flush() { }
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        public override int Read(byte[] buffer, int offset, int count) => Read(buffer.AsSpan(offset, count));

        public override int Read(Span<byte> buffer)
        {
            if (!_started)
            {
                _started = true;
                beforeFirstRead?.Invoke();
            }
            int count = Math.Min(buffer.Length, bytes.Length - _position);
            bytes.AsSpan(_position, count).CopyTo(buffer);
            _position += count;
            return count;
        }

        public override async Task<int> ReadAsync(byte[] buffer, int offset, int count, CancellationToken cancellationToken)
        {
            if (stallUntilCancellation)
            {
                await WaitForCancellation(cancellationToken);
            }
            cancellationToken.ThrowIfCancellationRequested();
            return Read(buffer, offset, count);
        }

        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
        {
            if (stallUntilCancellation)
            {
                await WaitForCancellation(cancellationToken);
            }
            cancellationToken.ThrowIfCancellationRequested();
            return Read(buffer.Span);
        }

        private async Task WaitForCancellation(CancellationToken cancellationToken)
        {
            try
            {
                await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
            }
            finally
            {
                ObservedCancellation = cancellationToken.IsCancellationRequested;
            }
        }
    }
}
