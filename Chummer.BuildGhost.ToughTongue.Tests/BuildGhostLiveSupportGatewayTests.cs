using Chummer.Run.Api.Services.KarmaForge;
using Chummer.Run.Contracts.BuildGhost;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.FileProviders;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace Chummer.BuildGhost.ToughTongue.Tests;

[TestClass]
public sealed class BuildGhostLiveSupportGatewayTests
{
    private const string Token = "0123456789abcdef0123456789abcdef";

    [TestMethod]
    public async Task Missing_configuration_returns_Rook_fallback_without_network()
    {
        RecordingHandler handler = new();
        BuildGhostLiveSupportGateway gateway = Create(handler, []);

        BuildGhostSupportExperienceProjection experience =
            await gateway.GetExperienceAsync(CancellationToken.None);

        Assert.AreEqual(0, handler.Calls);
        Assert.AreEqual(BuildGhostSupportChannelKinds.RookVidBoard, experience.DefaultSupport.ChannelKind);
        Assert.IsFalse(experience.LiveSupport.RequestAvailable);
    }

    [TestMethod]
    public async Task Experience_call_uses_server_side_bearer_and_accepts_exact_contract()
    {
        using TestWebRoot webRoot = TestWebRoot.Create();
        byte[] media = Encoding.UTF8.GetBytes("approved-rook-vidboard-media");
        webRoot.Write("media/support/rook.mp4", media);
        BuildGhostSupportExperienceProjection expected = new(
            ToughTongueBuildGhostContractVersions.SupportExperienceV1,
            DefaultSupport(Digest(media)),
            new BuildGhostLiveSupportCapabilityProjection(
                BuildGhostSupportChannelKinds.LivePhotorealMeeting,
                true,
                [BuildGhostLiveMeetingProviders.Zoom],
                "photorealistic-provider-managed",
                true,
                []));
        RecordingHandler handler = new()
        {
            Response = JsonResponse(expected)
        };
        BuildGhostLiveSupportGateway gateway = Create(handler, Configuration(), webRoot.Path);

        BuildGhostSupportExperienceProjection result =
            await gateway.GetExperienceAsync(CancellationToken.None);

        Assert.IsTrue(result.LiveSupport.RequestAvailable);
        Assert.AreEqual(1, handler.Calls);
        Assert.AreEqual(new Uri("https://ai.internal/api/v1/ai/build-ghost/support-experience"), handler.LastUri);
        Assert.AreEqual("Bearer", handler.LastAuthorization?.Scheme);
        Assert.AreEqual(Token, handler.LastAuthorization?.Parameter);
    }

    [TestMethod]
    public async Task Malformed_nested_experience_returns_Rook_fallback()
    {
        RecordingHandler handler = new()
        {
            Response = JsonResponse(new
            {
                schema = ToughTongueBuildGhostContractVersions.SupportExperienceV1,
                defaultSupport = (object?)null,
                liveSupport = (object?)null
            })
        };
        BuildGhostLiveSupportGateway gateway = Create(handler, Configuration());

        BuildGhostSupportExperienceProjection result =
            await gateway.GetExperienceAsync(CancellationToken.None);

        Assert.AreEqual(1, handler.Calls);
        Assert.AreEqual(BuildGhostSupportChannelKinds.RookVidBoard, result.DefaultSupport.ChannelKind);
        Assert.IsFalse(result.LiveSupport.RequestAvailable);
        CollectionAssert.Contains(
            result.LiveSupport.BlockingReasons.ToArray(),
            "live-support-ai-experience-invalid");
    }

    [TestMethod]
    public async Task Missing_or_mismatched_Hub_media_bytes_fall_back_to_text_without_disabling_live_support()
    {
        using TestWebRoot webRoot = TestWebRoot.Create();
        BuildGhostSupportExperienceProjection expected = new(
            ToughTongueBuildGhostContractVersions.SupportExperienceV1,
            DefaultSupport(Digest(Encoding.UTF8.GetBytes("approved-but-not-delivered"))),
            new BuildGhostLiveSupportCapabilityProjection(
                BuildGhostSupportChannelKinds.LivePhotorealMeeting,
                true,
                [BuildGhostLiveMeetingProviders.Zoom],
                "photorealistic-provider-managed",
                true,
                []));
        RecordingHandler handler = new() { Response = JsonResponse(expected) };
        BuildGhostLiveSupportGateway gateway = Create(handler, Configuration(), webRoot.Path);

        BuildGhostSupportExperienceProjection result =
            await gateway.GetExperienceAsync(CancellationToken.None);

        Assert.IsFalse(result.DefaultSupport.PreRenderedVideoReady);
        Assert.IsNull(result.DefaultSupport.PreRenderedVideoHref);
        Assert.IsTrue(result.LiveSupport.RequestAvailable);
        CollectionAssert.Contains(
            result.DefaultSupport.BlockingReasons.ToArray(),
            "rook-vidboard-hub-media-bytes-unverified");
    }

    [TestMethod]
    public async Task Ready_session_with_lookalike_host_is_rejected_and_link_is_not_returned()
    {
        BuildGhostLiveSupportRequest request = Request();
        BuildGhostLiveSupportSessionProjection unsafeSession = new(
            ToughTongueBuildGhostContractVersions.LiveSupportSessionV1,
            request.RequestId,
            BuildGhostSupportChannelKinds.LivePhotorealMeeting,
            BuildGhostLiveSupportStatuses.Ready,
            BuildGhostLiveMeetingProviders.Zoom,
            new Uri("https://zoom.us.attacker.example/j/123"),
            request.RequestedAtUtc.AddMinutes(30),
            ToughTongueBuildGhostPersonaIds.StockDefaultAvatar,
            "photorealistic-provider-managed",
            true,
            true,
            request.DisclosureVersion,
            request.DisclosureDigest,
            Digest(),
            Digest(),
            Digest(),
            Digest(),
            request.RequestedAtUtc,
            request.RequestedAtUtc,
            DefaultSupport(),
            []);
        RecordingHandler handler = new()
        {
            Response = JsonResponse(unsafeSession)
        };
        BuildGhostLiveSupportGateway gateway = Create(handler, Configuration());

        BuildGhostLiveSupportSessionProjection result =
            await gateway.RequestAsync(request, CancellationToken.None);

        Assert.AreEqual(BuildGhostLiveSupportStatuses.Unavailable, result.Status);
        Assert.IsNull(result.JoinUrl);
        CollectionAssert.Contains(result.BlockingReasons.ToArray(), "live-support-ai-session-invalid");
    }

    [TestMethod]
    public async Task Session_with_stale_disclosure_authority_is_rejected_at_the_BFF_boundary()
    {
        BuildGhostLiveSupportRequest request = Request();
        BuildGhostLiveSupportSessionProjection stale = new(
            ToughTongueBuildGhostContractVersions.LiveSupportSessionV1,
            request.RequestId,
            BuildGhostSupportChannelKinds.LivePhotorealMeeting,
            BuildGhostLiveSupportStatuses.Ready,
            request.MeetingProvider,
            new Uri("https://zoom.us/j/123456789"),
            request.RequestedAtUtc.AddMinutes(30),
            ToughTongueBuildGhostPersonaIds.StockDefaultAvatar,
            "photorealistic-provider-managed",
            true,
            true,
            "chummer.build_ghost.live_support_disclosure.stale",
            Digest(),
            Digest(),
            Digest(),
            Digest(),
            Digest(),
            request.RequestedAtUtc,
            request.RequestedAtUtc,
            DefaultSupport(),
            []);
        RecordingHandler handler = new() { Response = JsonResponse(stale) };
        BuildGhostLiveSupportGateway gateway = Create(handler, Configuration());

        BuildGhostLiveSupportSessionProjection requested =
            await gateway.RequestAsync(request, CancellationToken.None);
        BuildGhostLiveSupportSessionProjection? status = await gateway.GetSessionAsync(
            new BuildGhostLiveSupportStatusRequest(
                ToughTongueBuildGhostContractVersions.LiveSupportStatusRequestV1,
                request.OwnerScopeHash,
                request.RequestId,
                request.WorkspaceId,
                request.SourceDigest),
            CancellationToken.None);

        Assert.AreEqual(BuildGhostLiveSupportStatuses.Unavailable, requested.Status);
        Assert.IsNull(requested.JoinUrl);
        Assert.IsNull(status);
    }

    private static BuildGhostLiveSupportGateway Create(
        RecordingHandler handler,
        IEnumerable<KeyValuePair<string, string?>> configuration,
        string? webRootPath = null)
    {
        HttpClient client = new(handler, disposeHandler: false);
        return new BuildGhostLiveSupportGateway(
            new StaticHttpClientFactory(client),
            new ConfigurationBuilder().AddInMemoryCollection(configuration).Build(),
            new StaticWebHostEnvironment(webRootPath ?? string.Empty));
    }

    private static IEnumerable<KeyValuePair<string, string?>> Configuration()
        => new Dictionary<string, string?>
        {
            [BuildGhostLiveSupportGateway.BaseUrlConfigurationKey] = "https://ai.internal/",
            [BuildGhostLiveSupportGateway.PrimaryTokenConfigurationKey] = Token
        };

    private static BuildGhostLiveSupportRequest Request()
        => new(
            ToughTongueBuildGhostContractVersions.LiveSupportRequestV1,
            "live-request-1",
            Digest(),
            "workspace-1",
            1,
            Digest(),
            "en-US",
            BuildGhostLiveMeetingProviders.Zoom,
            true,
            true,
            BuildGhostLiveSupportDisclosureContract.CurrentVersion,
            BuildGhostLiveSupportDisclosureContract.ComputeDigest(),
            30,
            "idempotency-1",
            DateTimeOffset.Parse("2026-08-25T00:00:00Z"));

    private static BuildGhostDefaultSupportProjection DefaultSupport(string? digest = null)
        => new(
            BuildGhostSupportChannelKinds.RookVidBoard,
            ToughTongueBuildGhostPersonaIds.Rook,
            ToughTongueBuildGhostPersonaIds.RookAvatar,
            ToughTongueBuildGhostPersonaIds.RookVidBoardSupport,
            "/media/support/rook.mp4",
            digest ?? Digest(),
            true,
            "ready",
            "Rook remains available.",
            []);

    private static string Digest() => "sha256:" + new string('a', 64);

    private static string Digest(ReadOnlySpan<byte> value)
        => $"sha256:{Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(value)).ToLowerInvariant()}";

    private static HttpResponseMessage JsonResponse<T>(T value)
        => new(HttpStatusCode.OK)
        {
            Content = new StringContent(
                JsonSerializer.Serialize(value, new JsonSerializerOptions(JsonSerializerDefaults.Web)),
                Encoding.UTF8,
                "application/json")
        };

    private sealed class StaticHttpClientFactory(HttpClient client) : IHttpClientFactory
    {
        public HttpClient CreateClient(string name) => client;
    }

    private sealed class StaticWebHostEnvironment(string webRootPath) : IWebHostEnvironment
    {
        public string ApplicationName { get; set; } = "Chummer.BuildGhost.ToughTongue.Tests";
        public IFileProvider WebRootFileProvider { get; set; } = new NullFileProvider();
        public string WebRootPath { get; set; } = webRootPath;
        public string EnvironmentName { get; set; } = "Test";
        public string ContentRootPath { get; set; } = webRootPath;
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }

    private sealed class TestWebRoot : IDisposable
    {
        private TestWebRoot(string path) => Path = path;

        public string Path { get; }

        public static TestWebRoot Create()
        {
            string path = System.IO.Path.Combine(
                System.IO.Path.GetTempPath(),
                $"chummer-live-support-web-root-{Guid.NewGuid():N}");
            Directory.CreateDirectory(path);
            return new TestWebRoot(path);
        }

        public void Write(string relativePath, byte[] content)
        {
            string path = System.IO.Path.Combine(Path, relativePath.Replace('/', System.IO.Path.DirectorySeparatorChar));
            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(path)!);
            File.WriteAllBytes(path, content);
        }

        public void Dispose()
        {
            if (Directory.Exists(Path))
            {
                Directory.Delete(Path, recursive: true);
            }
        }
    }

    private sealed class RecordingHandler : HttpMessageHandler
    {
        public int Calls { get; private set; }
        public Uri? LastUri { get; private set; }
        public AuthenticationHeaderValue? LastAuthorization { get; private set; }
        public HttpResponseMessage Response { get; init; } = new(HttpStatusCode.ServiceUnavailable);

        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
        {
            Calls++;
            LastUri = request.RequestUri;
            LastAuthorization = request.Headers.Authorization;
            return Task.FromResult(Response);
        }
    }
}
