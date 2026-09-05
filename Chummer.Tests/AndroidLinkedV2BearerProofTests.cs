using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.InstallLinking;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class AndroidLinkedV2BearerProofTests
{
    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("Basic token-android-v2")]
    [InlineData("Bearer")]
    [InlineData("Bearer token-android-v2 extra")]
    public async Task V2_rejects_absent_or_malformed_bearer(string? authorization)
    {
        using Fixture fixture = new();
        SignedRequest signed = fixture.Sign(
            "/api/v2/android/linked/groups",
            "{\"installationId\":\"android-v2\"}");
        DefaultHttpContext context = signed.CreateContext();
        if (authorization is null)
        {
            context.Request.Headers.Remove("Authorization");
        }
        else
        {
            context.Request.Headers["Authorization"] = authorization;
        }
        bool dispatched = false;

        await fixture.InvokeAsync(context, _ => dispatched = true);

        Assert.False(dispatched);
        Assert.Equal(StatusCodes.Status401Unauthorized, context.Response.StatusCode);
        Assert.DoesNotContain(Fixture.AccessToken, await ReadResponseAsync(context), StringComparison.Ordinal);
    }

    [Fact]
    public async Task V2_rejects_access_token_anywhere_in_body_and_redacts_logs_and_response()
    {
        using Fixture fixture = new();
        const string leakedSecret = "body-secret-that-must-never-be-logged";
        SignedRequest signed = fixture.Sign(
            "/api/v2/android/linked/groups",
            $"{{\"installationId\":\"android-v2\",\"nested\":{{\"accessToken\":\"{leakedSecret}\"}}}}");
        DefaultHttpContext context = signed.CreateContext();
        bool dispatched = false;

        await fixture.InvokeAsync(context, _ => dispatched = true);

        Assert.False(dispatched);
        Assert.Equal(StatusCodes.Status400BadRequest, context.Response.StatusCode);
        string observed = string.Join('\n', fixture.Logger.Messages.Append(await ReadResponseAsync(context)));
        Assert.DoesNotContain(leakedSecret, observed, StringComparison.Ordinal);
        Assert.DoesNotContain(Fixture.AccessToken, observed, StringComparison.Ordinal);
        Assert.DoesNotContain(signed.Signature, observed, StringComparison.Ordinal);
    }

    [Fact]
    public async Task V2_proof_rejects_endpoint_and_grant_substitution_and_replay()
    {
        using Fixture fixture = new();
        SignedRequest signed = fixture.Sign(
            "/api/v2/android/linked/groups",
            "{\"installationId\":\"android-v2\"}");
        int dispatches = 0;

        DefaultHttpContext accepted = signed.CreateContext();
        await fixture.InvokeAsync(accepted, _ => dispatches++);
        Assert.Equal(StatusCodes.Status204NoContent, accepted.Response.StatusCode);

        DefaultHttpContext replay = signed.CreateContext();
        await fixture.InvokeAsync(replay, _ => dispatches++);
        Assert.Equal(StatusCodes.Status409Conflict, replay.Response.StatusCode);

        DefaultHttpContext endpointSubstitution = signed.CreateContext();
        endpointSubstitution.Request.Path = "/api/v2/android/linked/groups/create";
        await fixture.InvokeAsync(endpointSubstitution, _ => dispatches++);
        Assert.Equal(StatusCodes.Status401Unauthorized, endpointSubstitution.Response.StatusCode);

        SignedRequest fresh = fixture.Sign(
            "/api/v2/android/linked/groups",
            "{\"installationId\":\"android-v2\"}");
        DefaultHttpContext grantSubstitution = fresh.CreateContext();
        grantSubstitution.Request.Headers[AndroidLinkedV2RequestProof.GrantHeader] = "grant-another-install";
        await fixture.InvokeAsync(grantSubstitution, _ => dispatches++);
        Assert.Equal(StatusCodes.Status401Unauthorized, grantSubstitution.Response.StatusCode);

        Assert.Equal(1, dispatches);
    }

    [Fact]
    public async Task V2_proof_binds_exact_body_and_rejects_query_substitution()
    {
        using Fixture fixture = new();
        SignedRequest signed = fixture.Sign(
            "/api/v2/android/linked/groups",
            "{\"installationId\":\"android-v2\"}");

        DefaultHttpContext bodySubstitution = signed.CreateContext();
        bodySubstitution.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(
            "{\"installationId\":\"android-v2\",\"extra\":true}"));
        await fixture.InvokeAsync(bodySubstitution, _ => throw new InvalidOperationException("dispatch must not occur"));
        Assert.Equal(StatusCodes.Status401Unauthorized, bodySubstitution.Response.StatusCode);

        SignedRequest fresh = fixture.Sign(
            "/api/v2/android/linked/groups",
            "{\"installationId\":\"android-v2\"}");
        DefaultHttpContext querySubstitution = fresh.CreateContext();
        querySubstitution.Request.QueryString = new QueryString("?grant=another");
        await fixture.InvokeAsync(querySubstitution, _ => throw new InvalidOperationException("dispatch must not occur"));
        Assert.Equal(StatusCodes.Status400BadRequest, querySubstitution.Response.StatusCode);
    }

    [Fact]
    public async Task V1_is_bypassed_but_v1_proof_cannot_authorize_v2()
    {
        using Fixture fixture = new();
        DefaultHttpContext legacy = new();
        legacy.Request.Method = HttpMethods.Post;
        legacy.Request.Path = "/api/v1/android/linked/groups";
        legacy.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(
            $"{{\"installationId\":\"android-v2\",\"accessToken\":\"{Fixture.AccessToken}\"}}"));
        legacy.Response.Body = new MemoryStream();
        bool legacyDispatched = false;

        await fixture.InvokeAsync(legacy, _ => legacyDispatched = true);

        Assert.True(legacyDispatched);
        Assert.Equal(StatusCodes.Status204NoContent, legacy.Response.StatusCode);

        SignedRequest v2 = fixture.Sign(
            "/api/v2/android/linked/groups",
            "{\"installationId\":\"android-v2\"}");
        DefaultHttpContext confused = v2.CreateContext();
        confused.Request.Headers[AndroidLinkedV2RequestProof.SchemeHeader] = "chummer.android.packet.v1";
        bool v2Dispatched = false;

        await fixture.InvokeAsync(confused, _ => v2Dispatched = true);

        Assert.False(v2Dispatched);
        Assert.Equal(StatusCodes.Status401Unauthorized, confused.Response.StatusCode);
    }

    [Fact]
    public async Task Refresh_rotates_bearer_in_authorization_header_without_serializing_it()
    {
        using Fixture fixture = new();
        const string body = "{\"installationId\":\"android-v2\",\"headId\":\"android\",\"applicationVersion\":\"0.1.0-preview.11\",\"channelId\":\"internal\",\"platform\":\"android\",\"architecture\":\"arm64\"}";
        SignedRequest signed = fixture.Sign("/api/v2/install-linking/grants/refresh", body);
        DefaultHttpContext context = signed.CreateContext();
        AndroidLinkedV2GrantRefreshResponse? response = null;

        await fixture.InvokeAsync(context, httpContext =>
        {
            var controller = new InstallLinkingV2Controller(
                fixture.Service,
                fixture.WorkspaceSnapshots,
                fixture.TimeProvider)
            {
                ControllerContext = new ControllerContext { HttpContext = httpContext }
            };
            ActionResult<AndroidLinkedV2GrantRefreshResponse> action = controller.RefreshGrant(
                new AndroidLinkedV2GrantRefreshRequest(
                    "android-v2",
                    "android",
                    "0.1.0-preview.11",
                    "internal",
                    "android",
                    "arm64"));
            response = Assert.IsType<AndroidLinkedV2GrantRefreshResponse>(
                Assert.IsType<OkObjectResult>(action.Result).Value);
        });

        string rotatedAuthorization = context.Response.Headers["Authorization"].ToString();
        Assert.StartsWith("Bearer ", rotatedAuthorization, StringComparison.Ordinal);
        string rotatedToken = rotatedAuthorization["Bearer ".Length..];
        Assert.NotEqual(Fixture.AccessToken, rotatedToken);
        Assert.Equal(response!.Grant.GrantId, context.Response.Headers[AndroidLinkedV2RequestProof.GrantHeader]);
        string responseJson = JsonSerializer.Serialize(response, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        Assert.DoesNotContain(Fixture.AccessToken, responseJson, StringComparison.Ordinal);
        Assert.DoesNotContain(rotatedToken, responseJson, StringComparison.Ordinal);
        Assert.DoesNotContain("accessToken", responseJson, StringComparison.OrdinalIgnoreCase);
        Assert.Null(fixture.Service.ResolveAndroidLinkedV2Grant("android-v2", Fixture.GrantId, Fixture.AccessToken));
        Assert.NotNull(fixture.Service.ResolveAndroidLinkedV2Grant("android-v2", response.Grant.GrantId, rotatedToken));
    }

    [Fact]
    public void V2_request_DTOs_have_no_access_token_member()
    {
        Type[] requestTypes =
        [
            typeof(AndroidLinkedV2GrantRequest),
            typeof(AndroidLinkedV2GroupCreateRequest),
            typeof(AndroidLinkedV2GroupUpdateRequest),
            typeof(AndroidLinkedV2ChronicleDraftRequest),
            typeof(AndroidLinkedV2ChronicleActionRequest),
            typeof(AndroidLinkedV2AccountErasureRequest),
            typeof(AndroidLinkedV2GrantRefreshRequest),
            typeof(AndroidLinkedV2WorkspaceSnapshotUpsertRequest)
        ];

        Assert.All(requestTypes, static type => Assert.DoesNotContain(
            type.GetProperties(),
            static property => property.Name.Contains("AccessToken", StringComparison.OrdinalIgnoreCase)));
    }

    [Fact]
    public void Canonical_payload_is_version_endpoint_grant_and_body_bound_without_a_secret()
    {
        byte[] body = Encoding.UTF8.GetBytes("{\"installationId\":\"android-v2\"}");
        string packetKey = ToBase64Url(Enumerable.Repeat((byte)0x5a, 32).ToArray());
        byte[] canonical = AndroidLinkedV2RequestProof.CreateCanonicalPayload(
            "post",
            "/api/v2/android/linked/groups/Group-A/chronicles",
            "android-v2",
            "grant-android-v2",
            1_788_544_000,
            packetKey,
            body);
        string expectedBodyDigest = Convert.ToHexString(SHA256.HashData(body)).ToLowerInvariant();

        Assert.Equal(
            string.Join('\n',
                "chummer.android.packet.v2",
                "POST",
                "/api/v2/android/linked/groups/Group-A/chronicles",
                "android-v2",
                "grant-android-v2",
                "1788544000",
                packetKey,
                $"sha256:{expectedBodyDigest}"),
            Encoding.UTF8.GetString(canonical));
        Assert.DoesNotContain("grant-secret", Encoding.UTF8.GetString(canonical), StringComparison.Ordinal);
    }

    [Fact]
    public void V2_bootstrap_returns_secret_only_in_response_headers()
    {
        using Fixture fixture = new();
        AndroidInstallLinkProofPollV2Request request = fixture.IssueBootstrapRequest(
            "android-bootstrap-v2",
            useLegacyCanonical: false);
        DefaultHttpContext context = CreateControllerContext(AndroidInstallLinkV2BootstrapProof.Path);
        var controller = new InstallLinkingV2Controller(
            fixture.Service,
            fixture.WorkspaceSnapshots,
            fixture.TimeProvider)
        {
            ControllerContext = new ControllerContext { HttpContext = context }
        };

        ActionResult<AndroidInstallLinkV2ExchangeResponse> action = controller.PollBrowserCallback(request);

        AndroidInstallLinkV2ExchangeResponse response = Assert.IsType<AndroidInstallLinkV2ExchangeResponse>(
            Assert.IsType<OkObjectResult>(action.Result).Value);
        Assert.Single(context.Response.Headers.Authorization);
        string authorization = context.Response.Headers.Authorization.ToString();
        Assert.StartsWith("Bearer ", authorization, StringComparison.Ordinal);
        string issuedToken = authorization["Bearer ".Length..];
        Assert.NotEmpty(issuedToken);
        Assert.Equal(response.Grant.GrantId, Assert.Single(context.Response.Headers[AndroidLinkedV2RequestProof.GrantHeader]));
        string json = JsonSerializer.Serialize(response, new JsonSerializerOptions(JsonSerializerDefaults.Web));
        Assert.DoesNotContain(issuedToken, json, StringComparison.Ordinal);
        Assert.DoesNotContain("accessToken", json, StringComparison.OrdinalIgnoreCase);
        Assert.NotNull(fixture.Service.ResolveAndroidLinkedV2Grant(
            response.Installation.InstallationId,
            response.Grant.GrantId,
            issuedToken));
    }

    [Fact]
    public void Legacy_bootstrap_signature_cannot_authorize_v2_callback_poll()
    {
        using Fixture fixture = new();
        AndroidInstallLinkProofPollV2Request request = fixture.IssueBootstrapRequest(
            "android-bootstrap-confusion",
            useLegacyCanonical: true);
        DefaultHttpContext context = CreateControllerContext(AndroidInstallLinkV2BootstrapProof.Path);
        var controller = new InstallLinkingV2Controller(
            fixture.Service,
            fixture.WorkspaceSnapshots,
            fixture.TimeProvider)
        {
            ControllerContext = new ControllerContext { HttpContext = context }
        };

        ActionResult<AndroidInstallLinkV2ExchangeResponse> action = controller.PollBrowserCallback(request);

        ObjectResult denied = Assert.IsType<ObjectResult>(action.Result);
        Assert.Equal(StatusCodes.Status409Conflict, denied.StatusCode);
        Assert.False(context.Response.Headers.ContainsKey("Authorization"));
        Assert.False(context.Response.Headers.ContainsKey(AndroidLinkedV2RequestProof.GrantHeader));
        Assert.DoesNotContain(request.Signature, JsonSerializer.Serialize(denied.Value), StringComparison.Ordinal);
    }

    [Fact]
    public void Bootstrap_canonical_payload_is_version_and_endpoint_bound()
    {
        var request = new AndroidInstallLinkProofPollV2Request(
            "android-bootstrap-v2",
            "android",
            "0.1.0-preview.11",
            "internal",
            "android",
            "arm64",
            "spki",
            1_788_544_000,
            "0123456789abcdef0123456789abcdef",
            "signature",
            "Pixel");

        Assert.Equal(
            string.Join('\n',
                "chummer.install-link.remote-callback.v2",
                "POST",
                "/api/v2/install-linking/callbacks/poll",
                "android-bootstrap-v2",
                "android",
                "0.1.0-preview.11",
                "internal",
                "android",
                "arm64",
                "1788544000",
                "0123456789abcdef0123456789abcdef",
                "Pixel"),
            Encoding.UTF8.GetString(AndroidInstallLinkV2BootstrapProof.CreateCanonicalPayload(request)));
    }

    private static DefaultHttpContext CreateControllerContext(string path)
    {
        DefaultHttpContext context = new();
        context.Request.Method = HttpMethods.Post;
        context.Request.Path = path;
        context.Response.Body = new MemoryStream();
        return context;
    }

    private static async Task<string> ReadResponseAsync(DefaultHttpContext context)
    {
        context.Response.Body.Position = 0;
        using StreamReader reader = new(context.Response.Body, Encoding.UTF8, leaveOpen: true);
        string content = await reader.ReadToEndAsync();
        context.Response.Body.Position = 0;
        return content;
    }

    private static string ToBase64Url(byte[] bytes)
        => Convert.ToBase64String(bytes)
            .TrimEnd('=')
            .Replace('+', '-')
            .Replace('/', '_');

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;
        private readonly RSA _key = RSA.Create(2048);
        private readonly InstallLinkingStore _store;
        private readonly AndroidLinkedV2ReplayStore _replay = new();

        public Fixture()
        {
            _root = Path.Combine(
                Path.GetTempPath(),
                "chummer-android-linked-v2-tests",
                Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "install-linking-store.json"),
                    ["CHUMMER_INSTALL_LINKED_WORKSPACE_STORE_PATH"] = Path.Combine(_root, "workspace-store.json")
                })
                .Build();
            IDataProtectionProvider protection = DataProtectionProvider.Create(Path.Combine(_root, "keys"));
            _store = new InstallLinkingStore(configuration, protection, NullLogger<InstallLinkingStore>.Instance);
            Service = new InstallLinkingService(_store, configuration);
            WorkspaceSnapshots = new InstallLinkedWorkspaceSnapshotService(
                new InstallLinkedWorkspaceSnapshotStore(configuration));
            TimeProvider = new FixedTimeProvider(DateTimeOffset.UtcNow);

            lock (_store.Gate)
            {
                InstallationGrantDto grant = new(
                    GrantId,
                    "android-v2",
                    InstallationGrantStates.Active,
                    AccessToken,
                    TimeProvider.GetUtcNow().AddMinutes(-1),
                    TimeProvider.GetUtcNow().AddDays(30),
                    "user-v2",
                    "subject-v2");
                _store.InstallationsById["android-v2"] = new ClaimedInstallationDto(
                    InstallationId: "android-v2",
                    ArtifactId: "android-play-app",
                    Channel: "internal",
                    Version: "0.1.0-preview.11",
                    InstallAccessClass: InstallAccessClasses.AccountRequired,
                    Status: ClaimedInstallationStates.Active,
                    CreatedAtUtc: TimeProvider.GetUtcNow().AddDays(-1),
                    UpdatedAtUtc: TimeProvider.GetUtcNow(),
                    UserId: "user-v2",
                    SubjectId: "subject-v2",
                    PublicKey: Convert.ToBase64String(_key.ExportSubjectPublicKeyInfo()),
                    ClaimTicketId: "ticket-android-v2",
                    HeadId: "android",
                    Platform: "android",
                    Arch: "arm64",
                    HostLabel: "Android test",
                    GrantId: GrantId);
                _store.GrantsById[GrantId] = grant;
                _store.PersistLocked();
            }
        }

        public const string GrantId = "grant-android-v2";
        public const string AccessToken = "token-android-v2";
        public InstallLinkingService Service { get; }
        public InstallLinkedWorkspaceSnapshotService WorkspaceSnapshots { get; }
        public TimeProvider TimeProvider { get; }
        public CapturingLogger Logger { get; } = new();

        public SignedRequest Sign(string path, string body)
        {
            string packetKey = ToBase64Url(RandomNumberGenerator.GetBytes(
                AndroidLinkedV2RequestProof.PacketKeyBytes));
            long issued = TimeProvider.GetUtcNow().ToUnixTimeSeconds();
            byte[] bodyBytes = Encoding.UTF8.GetBytes(body);
            byte[] canonical = AndroidLinkedV2RequestProof.CreateCanonicalPayload(
                HttpMethods.Post,
                path,
                "android-v2",
                GrantId,
                issued,
                packetKey,
                bodyBytes);
            byte[] signature = _key.SignData(
                canonical,
                HashAlgorithmName.SHA256,
                RSASignaturePadding.Pkcs1);
            try
            {
                return new SignedRequest(
                    path,
                    bodyBytes,
                    GrantId,
                    AccessToken,
                    packetKey,
                    issued,
                    Convert.ToBase64String(signature));
            }
            finally
            {
                CryptographicOperations.ZeroMemory(canonical);
                CryptographicOperations.ZeroMemory(signature);
            }
        }

        public AndroidInstallLinkProofPollV2Request IssueBootstrapRequest(
            string installationId,
            bool useLegacyCanonical)
        {
            const string headId = "android";
            const string applicationVersion = "0.1.0-preview.11";
            const string channelId = "internal";
            const string platform = "android";
            const string architecture = "arm64";
            const string hostLabel = "Android test";
            string publicKey = Convert.ToBase64String(_key.ExportSubjectPublicKeyInfo());
            Service.IssueBrowserCallback(
                new IssueInstallBrowserCallbackRequestDto(
                    installationId,
                    "android-play-app",
                    applicationVersion,
                    channelId,
                    headId,
                    platform,
                    architecture,
                    "chummer://install-link",
                    publicKey,
                    HostLabel: null,
                    InstallAccessClass: InstallAccessClasses.AccountRequired),
                "user-v2",
                "subject-v2");

            long issued = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            string nonce = ToBase64Url(RandomNumberGenerator.GetBytes(24));
            var unsigned = new AndroidInstallLinkProofPollV2Request(
                installationId,
                headId,
                applicationVersion,
                channelId,
                platform,
                architecture,
                publicKey,
                issued,
                nonce,
                Signature: string.Empty,
                hostLabel);
            byte[] canonical = useLegacyCanonical
                ? Encoding.UTF8.GetBytes(string.Join(
                    '\n',
                    "chummer.install-link.remote-callback.v1",
                    installationId,
                    headId,
                    applicationVersion,
                    channelId,
                    platform,
                    architecture,
                    issued.ToString(System.Globalization.CultureInfo.InvariantCulture),
                    nonce))
                : AndroidInstallLinkV2BootstrapProof.CreateCanonicalPayload(unsigned);
            byte[] signature = _key.SignData(
                canonical,
                HashAlgorithmName.SHA256,
                RSASignaturePadding.Pkcs1);
            try
            {
                return unsigned with { Signature = Convert.ToBase64String(signature) };
            }
            finally
            {
                CryptographicOperations.ZeroMemory(canonical);
                CryptographicOperations.ZeroMemory(signature);
            }
        }

        public async Task InvokeAsync(DefaultHttpContext context, Action<HttpContext> onDispatch)
        {
            var middleware = new AndroidLinkedV2RequestProofMiddleware(
                dispatched =>
                {
                    onDispatch(dispatched);
                    dispatched.Response.StatusCode = StatusCodes.Status204NoContent;
                    return Task.CompletedTask;
                },
                Logger);
            await middleware.InvokeAsync(
                context,
                Service,
                new AndroidLinkedV2RequestProofVerifier(),
                _replay,
                TimeProvider);
        }

        public void Dispose()
        {
            _key.Dispose();
            _store.Dispose();
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }
    }

    private sealed record SignedRequest(
        string Path,
        byte[] Body,
        string GrantId,
        string AccessToken,
        string PacketKey,
        long IssuedAtUnixSeconds,
        string Signature)
    {
        public DefaultHttpContext CreateContext(string? authorization = null)
        {
            DefaultHttpContext context = new();
            context.Request.Method = HttpMethods.Post;
            context.Request.Path = Path;
            context.Request.ContentType = "application/json; charset=utf-8";
            context.Request.ContentLength = Body.Length;
            context.Request.Body = new MemoryStream(Body, writable: false);
            context.Request.Headers["Authorization"] = authorization ?? $"Bearer {AccessToken}";
            context.Request.Headers[AndroidLinkedV2RequestProof.SchemeHeader] = AndroidLinkedV2RequestProof.Scheme;
            context.Request.Headers[AndroidLinkedV2RequestProof.InstallationHeader] = "android-v2";
            context.Request.Headers[AndroidLinkedV2RequestProof.GrantHeader] = GrantId;
            context.Request.Headers[AndroidLinkedV2RequestProof.PacketKeyHeader] = PacketKey;
            context.Request.Headers[AndroidLinkedV2RequestProof.IssuedHeader] =
                IssuedAtUnixSeconds.ToString(System.Globalization.CultureInfo.InvariantCulture);
            context.Request.Headers[AndroidLinkedV2RequestProof.SignatureHeader] = Signature;
            context.Response.Body = new MemoryStream();
            return context;
        }
    }

    private sealed class FixedTimeProvider(DateTimeOffset now) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => now;
    }

    public sealed class CapturingLogger : ILogger<AndroidLinkedV2RequestProofMiddleware>
    {
        public List<string> Messages { get; } = [];

        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

        public bool IsEnabled(LogLevel logLevel) => true;

        public void Log<TState>(
            LogLevel logLevel,
            EventId eventId,
            TState state,
            Exception? exception,
            Func<TState, Exception?, string> formatter)
            => Messages.Add(formatter(state, exception));
    }
}
