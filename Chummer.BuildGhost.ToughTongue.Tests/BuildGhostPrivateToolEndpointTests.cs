using Chummer.Run.AI.Controllers;
using Chummer.Run.AI.Security;
using Chummer.Run.AI.Services.BuildGhost;
using Chummer.Run.Contracts.BuildGhost;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using System.Net;
using System.Text;
using System.Text.Json;

namespace Chummer.BuildGhost.ToughTongue.Tests;

[TestClass]
public sealed class BuildGhostPrivateToolEndpointTests
{
    private const string PacketKey = "opaque-packet-access-key-1234567890";
    private const string ProviderPacketKey = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";
    private const string PacketDigest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    private const string ServiceToken = "internal-service-token-1234567890abcdef";

    [TestMethod]
    public async Task Tool_requires_matching_ephemeral_bearer_and_exact_contract_header()
    {
        RecordingAuthority authority = new(PacketJson());
        BuildGhostController controller = Controller(authority);
        BuildGhostPrivateToolRequest request = Request();

        controller.HttpContext.Request.Headers.Authorization = "Bearer wrong-packet-key-123456789012345";
        controller.HttpContext.Request.Headers["X-Chummer-Build-Ghost-Tool-Contract"] = LegacyContractDigest();
        IActionResult wrongBearer = await controller.Tool(request, CancellationToken.None);
        Assert.IsInstanceOfType<UnauthorizedResult>(wrongBearer);

        controller.HttpContext.Request.Headers.Authorization = $"Bearer {PacketKey}";
        controller.HttpContext.Request.Headers["X-Chummer-Build-Ghost-Tool-Contract"] = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
        IActionResult wrongContract = await controller.Tool(request, CancellationToken.None);
        Assert.IsInstanceOfType<UnauthorizedResult>(wrongContract);
        Assert.AreEqual(0, authority.Calls);
    }

    [TestMethod]
    public async Task Tool_returns_only_the_validated_packet_and_marks_it_no_store()
    {
        RecordingAuthority authority = new(PacketJson());
        BuildGhostController controller = Controller(authority);
        Authorize(controller);

        IActionResult result = await controller.Tool(Request(), CancellationToken.None);

        ContentResult content = Assert.IsInstanceOfType<ContentResult>(result);
        Assert.AreEqual(PacketJson(), content.Content);
        Assert.AreEqual("application/json; charset=utf-8", content.ContentType);
        Assert.AreEqual(PacketDigest, controller.HttpContext.Response.Headers["X-Chummer-Build-Ghost-Packet-Digest"].ToString());
        Assert.AreEqual("no-store", controller.HttpContext.Response.Headers.CacheControl.ToString());
        Assert.AreEqual(1, authority.Calls);
        Assert.AreEqual(ContractDigest(), authority.LastContractDigest);
    }

    [TestMethod]
    public async Task Provider_v2_uses_the_canonical_body_key_as_the_only_external_credential()
    {
        RecordingAuthority authority = new(PacketJson());
        BuildGhostController controller = Controller(authority);
        AuthorizeProviderV2(controller);

        IActionResult result = await controller.ProviderToolV2(ProviderRequest(), CancellationToken.None);

        ContentResult content = Assert.IsInstanceOfType<ContentResult>(result);
        Assert.AreEqual(PacketJson(), content.Content);
        Assert.IsFalse(controller.HttpContext.Request.Headers.ContainsKey("Authorization"));
        Assert.IsFalse(controller.HttpContext.Request.Headers.ContainsKey("Cookie"));
        Assert.AreEqual("no-store", controller.HttpContext.Response.Headers.CacheControl.ToString());
        Assert.AreEqual(1, authority.Calls);
        Assert.AreEqual(ContractDigest(), authority.LastContractDigest);
    }

    [TestMethod]
    public async Task Provider_v2_rejects_header_body_ambiguity_query_cookie_and_v1_fallback()
    {
        static async Task AssertRejected(Action<HttpRequest> mutate)
        {
            RecordingAuthority authority = new(PacketJson());
            BuildGhostController controller = Controller(authority);
            AuthorizeProviderV2(controller);
            mutate(controller.HttpContext.Request);

            IActionResult result = await controller.ProviderToolV2(ProviderRequest(), CancellationToken.None);

            Assert.IsInstanceOfType<UnauthorizedResult>(result);
            Assert.AreEqual(0, authority.Calls);
            Assert.AreEqual("no-store", controller.HttpContext.Response.Headers.CacheControl.ToString());
        }

        await AssertRejected(request => request.Headers.Authorization = $"Bearer {ProviderPacketKey}");
        await AssertRejected(request => request.Headers.Authorization = new[] { "Bearer first", "Bearer second" });
        await AssertRejected(request => request.Headers.Cookie = $"packet_access_key={ProviderPacketKey}");
        await AssertRejected(request => request.QueryString = new QueryString($"?packet_access_key={ProviderPacketKey}"));
        await AssertRejected(request => request.Headers.CacheControl = string.Empty);
        await AssertRejected(request =>
        {
            request.Headers.Authorization = $"Bearer {ProviderPacketKey}";
            request.Headers["X-Chummer-Build-Ghost-Tool-Contract"] = LegacyContractDigest();
        });
    }

    [TestMethod]
    public void Provider_v2_requires_exact_schema_and_canonical_32_byte_base64url_key()
    {
        Assert.IsEmpty(BuildGhostPrivateToolAuthorityClient.ValidateProviderRequest(ProviderRequest()));
        BuildGhostPrivateToolProviderRequest[] invalid =
        [
            ProviderRequest() with { Schema = ToughTongueBuildGhostContractVersions.PrivateToolContractV2 },
            ProviderRequest() with { PacketAccessKey = string.Empty },
            ProviderRequest() with { PacketAccessKey = new string('A', 42) },
            ProviderRequest() with { PacketAccessKey = new string('A', 44) },
            ProviderRequest() with { PacketAccessKey = $"{new string('A', 42)}+" },
            ProviderRequest() with { PacketAccessKey = $"{new string('A', 42)}B" }
        ];
        Assert.IsTrue(invalid.All(static request =>
            BuildGhostPrivateToolAuthorityClient.ValidateProviderRequest(request).Count != 0));

        string unknownField = $$"""
            {"schema":"{{ToughTongueBuildGhostContractVersions.PrivateToolRequestV2}}","packet_access_key":"{{ProviderPacketKey}}","packet_digest":"{{PacketDigest}}","locale":"en-US","request_kind":"current-build","question":null,"authorization":"blocked"}
            """;
        Assert.ThrowsExactly<JsonException>(() =>
            JsonSerializer.Deserialize<BuildGhostPrivateToolProviderRequest>(unknownField));
    }

    [TestMethod]
    public async Task Provider_v2_invalid_input_returns_only_fixed_reasons_and_never_the_key()
    {
        RecordingAuthority authority = new(PacketJson());
        BuildGhostController controller = Controller(authority);
        AuthorizeProviderV2(controller);
        const string malformedSecret = "malformed-secret-must-never-be-rendered";

        IActionResult result = await controller.ProviderToolV2(
            ProviderRequest() with { PacketAccessKey = malformedSecret },
            CancellationToken.None);

        BadRequestObjectResult badRequest = Assert.IsInstanceOfType<BadRequestObjectResult>(result);
        string rendered = JsonSerializer.Serialize(badRequest.Value);
        Assert.IsFalse(rendered.Contains(malformedSecret, StringComparison.Ordinal));
        Assert.AreEqual(0, authority.Calls);
    }

    [TestMethod]
    public async Task Mutation_middleware_marks_both_exact_tool_routes_no_store_without_opening_neighbors()
    {
        int calls = 0;
        AiMutationAuthorizationMiddleware middleware = new(_ =>
        {
            calls++;
            return Task.CompletedTask;
        });
        IConfiguration empty = new ConfigurationBuilder().Build();
        DefaultHttpContext provider = new();
        provider.Request.Method = HttpMethods.Post;
        provider.Request.Path = AiMutationAuthorizationMiddleware.BuildGhostPrivateProviderToolPath;

        await middleware.InvokeAsync(provider, empty);

        Assert.AreEqual(1, calls);
        Assert.AreEqual("no-store", provider.Response.Headers.CacheControl.ToString());

        DefaultHttpContext neighbor = new();
        neighbor.Request.Method = HttpMethods.Post;
        neighbor.Request.Path = "/api/v2/ai/build-ghost/explain";
        await middleware.InvokeAsync(neighbor, empty);
        Assert.AreEqual(StatusCodes.Status503ServiceUnavailable, neighbor.Response.StatusCode);
        Assert.AreEqual(1, calls);
    }

    [TestMethod]
    public void Tool_request_schema_rejects_unknown_fields_and_invalid_request_kinds()
    {
        string json = $$"""
            {"packet_access_key":"{{PacketKey}}","packet_digest":"{{PacketDigest}}","locale":"en-US","request_kind":"current-build","question":null,"unexpected":"blocked"}
            """;
        Assert.ThrowsExactly<JsonException>(() => JsonSerializer.Deserialize<BuildGhostPrivateToolRequest>(json));

        IReadOnlyList<string> reasons = BuildGhostPrivateToolAuthorityClient.ValidateRequest(Request() with
        {
            RequestKind = "invented-kind"
        });
        CollectionAssert.Contains(reasons.ToArray(), "request-kind-unsupported");
    }

    [TestMethod]
    public async Task Authority_client_forwards_no_question_and_uses_separate_service_auth()
    {
        RecordingHandler handler = new(Response(PacketJson()));
        BuildGhostPrivateToolAuthorityClient client = Client(handler);

        string packet = await client.ResolveAsync(Request() with { Question = "Do not forward this question." }, ContractDigest(), CancellationToken.None);

        Assert.AreEqual(PacketJson(), packet);
        Assert.AreEqual("Bearer", handler.AuthorizationScheme);
        Assert.AreEqual(ServiceToken, handler.AuthorizationParameter);
        Assert.AreEqual(ContractDigest(), handler.ContractHeader);
        Assert.IsFalse(handler.Body.Contains("question", StringComparison.OrdinalIgnoreCase));
        StringAssert.Contains(handler.Body, "packet_access_key", StringComparison.Ordinal);
    }

    [TestMethod]
    public void Authority_client_typed_http_registration_resolves_the_production_constructor()
    {
        ServiceCollection services = new();
        services.AddSingleton<IConfiguration>(Configuration());
        services.AddHttpClient<IBuildGhostPrivateToolAuthorityClient, BuildGhostPrivateToolAuthorityClient>();

        using ServiceProvider provider = services.BuildServiceProvider();

        Assert.IsInstanceOfType<BuildGhostPrivateToolAuthorityClient>(
            provider.GetRequiredService<IBuildGhostPrivateToolAuthorityClient>());
    }

    [TestMethod]
    public async Task Authority_client_rejects_schema_digest_locale_and_private_payload_drift()
    {
        string[] invalidPackets =
        [
            PacketJson(schema: "invented.schema"),
            PacketJson(digest: "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"),
            PacketJson(locale: "de-DE"),
            PacketJson(extraProperty: "\"rawXml\":\"<character/>\"")
        ];

        string[] expectedReasons =
        [
            "private-tool-packet-schema-invalid",
            "private-tool-packet-digest-drift",
            "private-tool-packet-locale-drift",
            "private-tool-packet-privacy-rejected"
        ];

        for (int index = 0; index < invalidPackets.Length; index++)
        {
            BuildGhostPrivateToolAuthorityClient client = Client(new RecordingHandler(Response(invalidPackets[index])));
            BuildGhostPrivateToolResolutionException exception = await Assert.ThrowsExactlyAsync<BuildGhostPrivateToolResolutionException>(
                () => client.ResolveAsync(Request(), ContractDigest(), CancellationToken.None));
            Assert.AreEqual(expectedReasons[index], exception.Reason);
        }
    }

    [TestMethod]
    public async Task Authority_client_rejects_timeout_and_oversized_packets()
    {
        BuildGhostPrivateToolAuthorityClient timeoutClient = Client(new RecordingHandler(
            _ => throw new TaskCanceledException("simulated timeout")));
        BuildGhostPrivateToolResolutionException timeout = await Assert.ThrowsExactlyAsync<BuildGhostPrivateToolResolutionException>(
            () => timeoutClient.ResolveAsync(Request(), ContractDigest(), CancellationToken.None));
        Assert.AreEqual("private-tool-authority-timeout", timeout.Reason);
        Assert.AreEqual(StatusCodes.Status504GatewayTimeout, timeout.StatusCode);

        string oversized = PacketJson(extraProperty: $"\"padding\":\"{new string('x', 15_000)}\"");
        BuildGhostPrivateToolAuthorityClient sizeClient = Client(new RecordingHandler(Response(oversized)));
        BuildGhostPrivateToolResolutionException size = await Assert.ThrowsExactlyAsync<BuildGhostPrivateToolResolutionException>(
            () => sizeClient.ResolveAsync(Request(), ContractDigest(), CancellationToken.None));
        Assert.AreEqual("private-tool-response-too-large", size.Reason);
    }

    [TestMethod]
    public async Task Authority_budget_covers_slow_body_streaming_and_preserves_caller_cancellation()
    {
        HttpResponseMessage slowResponse = new(HttpStatusCode.OK)
        {
            Content = new StreamContent(new SlowReadStream(TimeSpan.FromSeconds(5)))
        };
        slowResponse.Headers.TryAddWithoutValidation("X-Chummer-Build-Ghost-Packet-Digest", PacketDigest);
        BuildGhostPrivateToolAuthorityClient budgeted = new(
            new HttpClient(new RecordingHandler(slowResponse)) { Timeout = Timeout.InfiniteTimeSpan },
            Configuration(),
            TimeSpan.FromMilliseconds(25));

        BuildGhostPrivateToolResolutionException timeout = await Assert.ThrowsExactlyAsync<BuildGhostPrivateToolResolutionException>(
            () => budgeted.ResolveAsync(Request(), ContractDigest(), CancellationToken.None));
        Assert.AreEqual("private-tool-authority-timeout", timeout.Reason);
        Assert.AreEqual(StatusCodes.Status504GatewayTimeout, timeout.StatusCode);

        HttpResponseMessage callerCancelledResponse = new(HttpStatusCode.OK)
        {
            Content = new StreamContent(new SlowReadStream(TimeSpan.FromSeconds(5)))
        };
        callerCancelledResponse.Headers.TryAddWithoutValidation("X-Chummer-Build-Ghost-Packet-Digest", PacketDigest);
        BuildGhostPrivateToolAuthorityClient callerCancelled = new(
            new HttpClient(new RecordingHandler(callerCancelledResponse)) { Timeout = Timeout.InfiniteTimeSpan },
            Configuration(),
            TimeSpan.FromSeconds(1));
        using CancellationTokenSource caller = new(TimeSpan.FromMilliseconds(25));

        await Assert.ThrowsAsync<OperationCanceledException>(
            () => callerCancelled.ResolveAsync(Request(), ContractDigest(), caller.Token));
    }

    [TestMethod]
    public async Task Authority_client_rejects_duplicate_digest_headers_without_throwing_sequence_errors()
    {
        HttpResponseMessage response = new(HttpStatusCode.OK)
        {
            Content = new StringContent(PacketJson(), Encoding.UTF8, "application/json")
        };
        response.Headers.TryAddWithoutValidation(
            "X-Chummer-Build-Ghost-Packet-Digest",
            new[] { PacketDigest, PacketDigest });
        BuildGhostPrivateToolAuthorityClient client = Client(new RecordingHandler(response));

        BuildGhostPrivateToolResolutionException exception = await Assert.ThrowsExactlyAsync<BuildGhostPrivateToolResolutionException>(
            () => client.ResolveAsync(Request(), ContractDigest(), CancellationToken.None));

        Assert.AreEqual("private-tool-packet-digest-header-invalid", exception.Reason);
        Assert.AreEqual(StatusCodes.Status502BadGateway, exception.StatusCode);
    }

    [TestMethod]
    public async Task Authority_gone_maps_to_external_gone()
    {
        BuildGhostPrivateToolAuthorityClient client = Client(new RecordingHandler(new HttpResponseMessage(HttpStatusCode.Gone)));
        BuildGhostPrivateToolResolutionException gone = await Assert.ThrowsExactlyAsync<BuildGhostPrivateToolResolutionException>(
            () => client.ResolveAsync(Request(), ContractDigest(), CancellationToken.None));
        Assert.AreEqual(StatusCodes.Status410Gone, gone.StatusCode);
        Assert.AreEqual("private-tool-authority-rejected", gone.Reason);

        BuildGhostController controller = Controller(new ThrowingAuthority(gone));
        Authorize(controller);
        IActionResult result = await controller.Tool(Request(), CancellationToken.None);
        ObjectResult problem = Assert.IsInstanceOfType<ObjectResult>(result);
        Assert.AreEqual(StatusCodes.Status410Gone, problem.StatusCode);

        BuildGhostController providerController = Controller(new ThrowingAuthority(gone));
        AuthorizeProviderV2(providerController);
        IActionResult providerReplay = await providerController.ProviderToolV2(
            ProviderRequest(),
            CancellationToken.None);
        ObjectResult providerProblem = Assert.IsInstanceOfType<ObjectResult>(providerReplay);
        Assert.AreEqual(StatusCodes.Status410Gone, providerProblem.StatusCode);
        Assert.AreEqual("no-store", providerController.HttpContext.Response.Headers.CacheControl.ToString());
    }

    [TestMethod]
    public async Task Authority_binding_conflict_stays_conflict_and_never_falls_back_to_legacy_resolution()
    {
        BuildGhostPrivateToolAuthorityClient client = Client(new RecordingHandler(
            new HttpResponseMessage(HttpStatusCode.Conflict)));
        BuildGhostPrivateToolResolutionException conflict =
            await Assert.ThrowsExactlyAsync<BuildGhostPrivateToolResolutionException>(
                () => client.ResolveAsync(
                    new BuildGhostPrivateToolRequest(
                        ProviderPacketKey,
                        PacketDigest,
                        "en-US",
                        "current-build",
                        null),
                    ContractDigest(),
                    CancellationToken.None));
        Assert.AreEqual(StatusCodes.Status409Conflict, conflict.StatusCode);

        RecordingAuthority authority = new(PacketJson());
        BuildGhostController wrongContractController = Controller(authority);
        AuthorizeProviderV2(wrongContractController);
        wrongContractController.HttpContext.Request.Headers["X-Chummer-Build-Ghost-Tool-Contract"] =
            LegacyContractDigest();
        IActionResult noFallback = await wrongContractController.ProviderToolV2(
            ProviderRequest(),
            CancellationToken.None);
        Assert.IsInstanceOfType<UnauthorizedResult>(noFallback);
        Assert.AreEqual(0, authority.Calls);
    }

    private static BuildGhostController Controller(IBuildGhostPrivateToolAuthorityClient authority)
    {
        BuildGhostController controller = new(
            new NeverRemoteAdapter(),
            new StaticReleaseRegistry(),
            authority,
            NullLogger<BuildGhostController>.Instance,
            Configuration());
        controller.ControllerContext = new ControllerContext { HttpContext = new DefaultHttpContext() };
        return controller;
    }

    private static void Authorize(BuildGhostController controller)
    {
        controller.HttpContext.Request.Headers.Authorization = $"Bearer {PacketKey}";
        controller.HttpContext.Request.Headers["X-Chummer-Build-Ghost-Tool-Contract"] = LegacyContractDigest();
    }

    private static void AuthorizeProviderV2(BuildGhostController controller)
    {
        controller.HttpContext.Request.Headers.CacheControl = "no-store";
        controller.HttpContext.Request.Headers["X-Chummer-Build-Ghost-Tool-Contract"] = ContractDigest();
    }

    private static BuildGhostPrivateToolAuthorityClient Client(HttpMessageHandler handler)
        => new(new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(120) }, Configuration());

    private static IConfiguration Configuration()
        => new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            [BuildGhostPrivateToolDeploymentContract.EndpointConfigurationKey] = "https://canary.chummer.run/api/v2/ai/build-ghost/tool",
            [BuildGhostPrivateToolDeploymentContract.AudienceConfigurationKey] = "build-ghost-private-tool",
            [BuildGhostPrivateToolDeploymentContract.TransportModeConfigurationKey] = BuildGhostPrivateToolDeploymentContract.ProviderBodyKeyV2TransportMode,
            [BuildGhostPrivateToolDeploymentContract.RemoteExecutionConfigurationKey] = "false",
            [BuildGhostPrivateToolAuthorityClient.AuthorityEndpointConfigurationKey] = "https://canary.chummer.run/api/internal/build-ghost/tool/resolve",
            [BuildGhostPrivateToolAuthorityClient.ServiceTokenConfigurationKey] = ServiceToken
        }).Build();

    private static string ContractDigest()
        => BuildGhostPrivateToolDeploymentContract.FromConfiguration(Configuration()).Package!.Tool.ContractDigest;

    private static string LegacyContractDigest()
        => BuildGhostPrivateToolDeploymentContract.Create(
            new Uri("https://canary.chummer.run/api/v1/ai/build-ghost/tool"),
            "build-ghost-private-tool").Tool.ContractDigest;

    private static BuildGhostPrivateToolRequest Request()
        => new(PacketKey, PacketDigest, "en-US", "current-build", "What should I improve?");

    private static BuildGhostPrivateToolProviderRequest ProviderRequest()
        => new(
            ToughTongueBuildGhostContractVersions.PrivateToolRequestV2,
            ProviderPacketKey,
            PacketDigest,
            "en-US",
            "current-build",
            "What should I improve?");

    private static string PacketJson(
        string schema = ToughTongueBuildGhostContractVersions.AnalysisV1,
        string digest = PacketDigest,
        string locale = "en-US",
        string? extraProperty = null)
        => $"{{\"schema\":\"{schema}\",\"packetDigest\":\"{digest}\",\"locale\":\"{locale}\"{(extraProperty is null ? string.Empty : $",{extraProperty}")}}}";

    private static HttpResponseMessage Response(string json)
    {
        HttpResponseMessage response = new(HttpStatusCode.OK)
        {
            Content = new StringContent(json, Encoding.UTF8, "application/json")
        };
        response.Headers.TryAddWithoutValidation("X-Chummer-Build-Ghost-Packet-Digest", PacketDigest);
        return response;
    }

    private sealed class RecordingAuthority(string response) : IBuildGhostPrivateToolAuthorityClient
    {
        public int Calls { get; private set; }
        public string LastContractDigest { get; private set; } = string.Empty;

        public Task<string> ResolveAsync(BuildGhostPrivateToolRequest request, string toolContractDigest, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Calls++;
            LastContractDigest = toolContractDigest;
            return Task.FromResult(response);
        }
    }

    private sealed class ThrowingAuthority(BuildGhostPrivateToolResolutionException exception) : IBuildGhostPrivateToolAuthorityClient
    {
        public Task<string> ResolveAsync(BuildGhostPrivateToolRequest request, string toolContractDigest, CancellationToken cancellationToken)
            => throw exception;
    }

    private sealed class NeverRemoteAdapter : IToughTongueBuildGhostAdapter
    {
        public Task<ToughTongueBuildGhostResult> ExplainAsync(ToughTongueBuildGhostRequest request, CancellationToken cancellationToken)
            => throw new AssertFailedException("Legacy explanation path must not be called.");
    }

    private sealed class StaticReleaseRegistry : IBuildGhostPersonaReleaseRegistry
    {
        public BuildGhostPersonaReleaseProjection ResolveRook()
            => new(ToughTongueBuildGhostPersonaIds.Rook, ToughTongueBuildGhostPersonaIds.RookAvatar,
                ToughTongueBuildGhostPersonaIds.RookVoice, "approved", "disabled", true, false,
                "localized-deterministic-text-only", []);
    }

    private sealed class RecordingHandler : HttpMessageHandler
    {
        private readonly Func<HttpRequestMessage, HttpResponseMessage> response;

        public RecordingHandler(HttpResponseMessage response) : this(_ => response) { }
        public RecordingHandler(Func<HttpRequestMessage, HttpResponseMessage> response) => this.response = response;

        public string AuthorizationScheme { get; private set; } = string.Empty;
        public string AuthorizationParameter { get; private set; } = string.Empty;
        public string ContractHeader { get; private set; } = string.Empty;
        public string Body { get; private set; } = string.Empty;

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            AuthorizationScheme = request.Headers.Authorization?.Scheme ?? string.Empty;
            AuthorizationParameter = request.Headers.Authorization?.Parameter ?? string.Empty;
            ContractHeader = request.Headers.TryGetValues("X-Chummer-Build-Ghost-Tool-Contract", out IEnumerable<string>? values)
                ? values.Single()
                : string.Empty;
            Body = request.Content is null ? string.Empty : await request.Content.ReadAsStringAsync(cancellationToken);
            return response(request);
        }
    }

    private sealed class SlowReadStream(TimeSpan delay) : Stream
    {
        public override bool CanRead => true;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }

        public override void Flush() { }
        public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();

        public override async ValueTask<int> ReadAsync(Memory<byte> buffer, CancellationToken cancellationToken = default)
        {
            await Task.Delay(delay, cancellationToken);
            return 0;
        }
    }
}
