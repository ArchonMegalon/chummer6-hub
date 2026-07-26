using System.Net;
using System.Text.Json;
using Chummer.Run.Api;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.PublicSurface;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicReleaseContractHttpIntegrationTests
{
    [Theory]
    [InlineData("/api/v1/public/release-truth")]
    [InlineData("/api/public/release-truth")]
    [InlineData("/api/v1/public/release-truth/g/generation-a")]
    [InlineData("/api/public/release-truth/g/generation-a")]
    public async Task ReleaseTruthAliasesServeGetAndZeroBodyHeadWithNoStoreHeaders(
        string path)
    {
        await using TestApp app = await TestApp.StartAsync();
        using HttpClient client = app.CreateClient();

        using HttpResponseMessage get = await client.GetAsync(path);
        Assert.Equal(HttpStatusCode.OK, get.StatusCode);
        using JsonDocument body = JsonDocument.Parse(
            await get.Content.ReadAsByteArrayAsync());
        Assert.Equal(
            "stable_ready",
            body.RootElement.GetProperty("releaseDecisionStatus").GetString());
        AssertNoStoreHeaders(get);
        Assert.True(get.Headers.Contains(
            PublicReleaseTruthProjectionMiddleware.ProjectionHeaderName));

        using var headRequest = new HttpRequestMessage(HttpMethod.Head, path);
        using HttpResponseMessage head = await client.SendAsync(headRequest);
        Assert.Equal(HttpStatusCode.OK, head.StatusCode);
        Assert.Empty(await head.Content.ReadAsByteArrayAsync());
        AssertNoStoreHeaders(head);
        Assert.True(head.Headers.Contains(
            PublicReleaseTruthProjectionMiddleware.ProjectionHeaderName));
    }

    [Theory]
    [InlineData("/api/v1/public/release-truth?cache=no")]
    [InlineData("/API/v1/public/release-truth")]
    [InlineData("/api/v1/public/release-truth/g/generation-a?cache=no")]
    public async Task ReleaseTruthAliasesRejectQueryAndCaseVariants(
        string target)
    {
        await using TestApp app = await TestApp.StartAsync();
        using HttpClient client = app.CreateClient();

        using HttpResponseMessage response = await client.GetAsync(target);

        Assert.Equal(HttpStatusCode.NotFound, response.StatusCode);
    }

    [Theory]
    [InlineData(
        "/api/v1/public/release-truth",
        "/api/v1/public/%72elease-truth",
        false)]
    [InlineData(
        "/api/v1/public/release-truth",
        "/api/v1/public/ignored/%2e%2e/release-truth",
        false)]
    [InlineData(
        "/api/v1/public/release-truth/g/generation-a",
        "/api/v1/public/release-truth/g/generation%2da",
        true)]
    public void ReleaseTruthControllerRejectsEncodedAndTraversalRawTargets(
        string path,
        string rawTarget,
        bool generationBound)
    {
        PublicReleaseTruthProjectionDto projection = BuildProjection();
        var controller = new PublicReleaseTruthController(
            new FixedProjection(projection));
        var context = new DefaultHttpContext();
        context.Request.Method = HttpMethods.Get;
        context.Request.Path = path;
        context.Features.Get<IHttpRequestFeature>()!.RawTarget = rawTarget;
        controller.ControllerContext =
            new ControllerContext { HttpContext = context };

        IActionResult result = generationBound
            ? controller.GetGeneration("generation-a")
            : controller.Get();

        Assert.IsType<NotFoundResult>(result);
        Assert.Equal(
            "private, no-store, max-age=0",
            context.Response.Headers.CacheControl.ToString());
    }

    [Theory]
    [InlineData(
        "/downloads/g/generation-a/files/chummer+setup.exe",
        "/downloads/g/generation-a/files/chummer+setup.exe",
        "chummer+setup.exe",
        true)]
    [InlineData(
        "/downloads/g/generation-a/files/chummer+setup.exe",
        "/downloads/g/generation-a/files/chummer%2Bsetup.exe",
        "chummer+setup.exe",
        false)]
    [InlineData(
        "/downloads/g/generation-a/files/chummer..setup.exe",
        "/downloads/g/generation-a/files/chummer..setup.exe",
        "chummer..setup.exe",
        false)]
    [InlineData(
        "/downloads/g/generation-a/files/nested/setup.exe",
        "/downloads/g/generation-a/files/nested/setup.exe",
        "nested/setup.exe",
        false)]
    public void GenerationFileContractRequiresExactPortableRawTarget(
        string path,
        string rawTarget,
        string fileName,
        bool expected)
    {
        var context = new DefaultHttpContext();
        context.Request.Method = HttpMethods.Get;
        context.Request.Path = path;
        context.Features.Get<IHttpRequestFeature>()!.RawTarget = rawTarget;

        Assert.Equal(
            expected,
            PublicReleaseContractRequestPolicy
                .IsCanonicalGenerationFileRequest(
                    context.Request,
                    "generation-a",
                    fileName));
    }

    private static void AssertNoStoreHeaders(HttpResponseMessage response)
    {
        Assert.True(response.Headers.CacheControl?.Private);
        Assert.True(response.Headers.CacheControl?.NoStore);
        Assert.Equal(
            TimeSpan.Zero,
            response.Headers.CacheControl?.MaxAge);
        Assert.Equal(
            "no-store, max-age=0",
            Assert.Single(response.Headers.GetValues("CDN-Cache-Control")));
        Assert.Equal(
            "no-store, max-age=0",
            Assert.Single(response.Headers.GetValues(
                "Cloudflare-CDN-Cache-Control")));
        Assert.Equal(
            "no-store",
            Assert.Single(response.Headers.GetValues("Surrogate-Control")));
        Assert.Equal(
            "no-cache",
            Assert.Single(response.Headers.GetValues("Pragma")));
    }

    private sealed class TestApp(
        WebApplication application,
        string root) : IAsyncDisposable
    {
        public static async Task<TestApp> StartAsync()
        {
            string root = Path.Combine(
                Path.GetTempPath(),
                "public-release-contract-http-tests",
                Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            WebApplicationBuilder builder = WebApplication.CreateBuilder();
            builder.WebHost.ConfigureKestrel(
                options => options.Listen(IPAddress.Loopback, 0));
            builder.Configuration.AddInMemoryCollection(
                new Dictionary<string, string?>
                {
                    ["CHUMMER_DOWNLOADS_SOURCE_ROOT"] =
                        Path.Combine(root, "downloads")
                });
            builder.Services
                .AddControllers()
                .AddApplicationPart(
                    typeof(PublicReleaseTruthController).Assembly);
            builder.Services.AddSingleton<IReleaseTruthProjection>(
                new FixedProjection(BuildProjection()));
            builder.Services.AddSingleton(
                static provider => new ReleaseBundlePromotionService(
                    provider.GetRequiredService<IConfiguration>(),
                    NullLogger<ReleaseBundlePromotionService>.Instance,
                    promotionCheckpoint: null));
            builder.Services.AddSingleton<ReleaseShelfGenerationStore>();

            WebApplication app = builder.Build();
            app.Use((context, next) =>
                PublicReleaseResponseCachePolicy.InvokeNoStoreBoundaryAsync(
                    context,
                    next,
                    requiresNoStore: true));
            app.UseRouting();
            app.UseMiddleware<PublicReleaseTruthProjectionMiddleware>();
            app.MapControllers();
            try
            {
                await app.StartAsync();
                return new TestApp(app, root);
            }
            catch
            {
                await app.DisposeAsync();
                Directory.Delete(root, recursive: true);
                throw;
            }
        }

        public HttpClient CreateClient()
        {
            IServer server =
                application.Services.GetRequiredService<IServer>();
            IServerAddressesFeature addresses = server.Features
                .Get<IServerAddressesFeature>()
                ?? throw new InvalidOperationException(
                    "Kestrel did not expose a bound address.");
            return new HttpClient
            {
                BaseAddress = new Uri(addresses.Addresses.Single())
            };
        }

        public async ValueTask DisposeAsync()
        {
            await application.StopAsync();
            await application.DisposeAsync();
            if (Directory.Exists(root))
            {
                Directory.Delete(root, recursive: true);
            }
        }
    }

    private sealed class FixedProjection(
        PublicReleaseTruthProjectionDto projection)
        : IReleaseTruthProjection
    {
        private static readonly string AuthoritySha256 = new('d', 64);

        public PublicReleaseTruthCapture CaptureWithAuthority()
            => new(projection, AuthoritySha256);

        public PublicReleaseTruthCapture CaptureGenerationWithAuthority(
            string generationId)
            => new(projection, AuthoritySha256);

        public PublicReleaseTruthProjectionDto Capture() => projection;

        public PublicReleaseTruthProjectionDto CaptureGeneration(
            string generationId)
            => projection;

        public PublicReleaseTruthProjectionDto Project(
            PublicReleaseManifestDto manifest,
            string? immutableManifestSha256,
            ReadOnlyMemory<byte>? immutableAuthorityManifestBytes)
            => projection;
    }

    private static PublicReleaseTruthProjectionDto BuildProjection()
        => new(
            ContractName: PublicReleaseTruthProjectionDto.Schema,
            ReleaseVersion: "run-test",
            Channel: "stable",
            ReleaseStatus: "published",
            RolloutState: "public_stable",
            SupportabilityState: "gold_supported",
            AvailablePlatforms: ["windows"],
            PrimaryHeadByPlatform: new Dictionary<string, string>(
                StringComparer.Ordinal)
            {
                ["windows"] = "avalonia"
            },
            ArtifactCount: 1,
            DownloadAccessPosture: "open_public",
            KnownIssueSummary: string.Empty,
            ManifestSha256: new string('a', 64),
            RegistryCommit: new string('b', 40),
            ReleaseDecisionStatus: "stable_ready",
            ReleaseDecisionSha256: new string('c', 64));
}
