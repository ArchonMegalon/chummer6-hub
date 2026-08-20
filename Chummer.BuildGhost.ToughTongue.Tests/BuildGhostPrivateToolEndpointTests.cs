using Chummer.Run.AI.Controllers;
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
    private const string PacketDigest = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    private const string ServiceToken = "internal-service-token-1234567890abcdef";

    [TestMethod]
    public async Task Tool_requires_matching_ephemeral_bearer_and_exact_contract_header()
    {
        RecordingAuthority authority = new(PacketJson());
        BuildGhostController controller = Controller(authority);
        BuildGhostPrivateToolRequest request = Request();

        controller.HttpContext.Request.Headers.Authorization = "Bearer wrong-packet-key-123456789012345";
        controller.HttpContext.Request.Headers["X-Chummer-Build-Ghost-Tool-Contract"] = ContractDigest();
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

        BuildGhostController controller = Controller(new ThrowingAuthority(gone));
        Authorize(controller);
        IActionResult result = await controller.Tool(Request(), CancellationToken.None);
        ObjectResult problem = Assert.IsInstanceOfType<ObjectResult>(result);
        Assert.AreEqual(StatusCodes.Status410Gone, problem.StatusCode);
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
        controller.HttpContext.Request.Headers["X-Chummer-Build-Ghost-Tool-Contract"] = ContractDigest();
    }

    private static BuildGhostPrivateToolAuthorityClient Client(HttpMessageHandler handler)
        => new(new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(120) }, Configuration());

    private static IConfiguration Configuration()
        => new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            [BuildGhostPrivateToolDeploymentContract.EndpointConfigurationKey] = "https://canary.chummer.run/api/v1/ai/build-ghost/tool",
            [BuildGhostPrivateToolDeploymentContract.AudienceConfigurationKey] = "build-ghost-private-tool",
            [BuildGhostPrivateToolDeploymentContract.RemoteExecutionConfigurationKey] = "false",
            [BuildGhostPrivateToolAuthorityClient.AuthorityEndpointConfigurationKey] = "https://canary.chummer.run/api/internal/build-ghost/tool/resolve",
            [BuildGhostPrivateToolAuthorityClient.ServiceTokenConfigurationKey] = ServiceToken
        }).Build();

    private static string ContractDigest()
        => BuildGhostPrivateToolDeploymentContract.FromConfiguration(Configuration()).Package!.Tool.ContractDigest;

    private static BuildGhostPrivateToolRequest Request()
        => new(PacketKey, PacketDigest, "en-US", "current-build", "What should I improve?");

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

        public Task<string> ResolveAsync(BuildGhostPrivateToolRequest request, string toolContractDigest, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            Calls++;
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
