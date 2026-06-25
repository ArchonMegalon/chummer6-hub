using System.Net;
using System.Text;
using Chummer.Run.Api.Controllers;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingParticipateProxyTests
{
    [Fact]
    public async Task ParticipateBoardProxyReturnsFirstPartyFallbackWhenUpstreamIsUnavailable()
    {
        var controller = CreateController(new ThrowingHttpClientFactory());
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.ParticipateBoardProxy(null, CancellationToken.None);

        ContentResult content = Assert.IsType<ContentResult>(result);
        Assert.Equal("text/html; charset=utf-8", content.ContentType);
        Assert.Contains("Public board temporarily unavailable", content.Content ?? string.Empty, StringComparison.Ordinal);
        Assert.Contains("href=\"/roadmap\"", content.Content ?? string.Empty, StringComparison.Ordinal);
        Assert.DoesNotContain("Unexpected server error", content.Content ?? string.Empty, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("ProductLift", content.Content ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task ParticipateBoardRootApiProxyDoesNotForwardChummerCredentials()
    {
        var factory = new RecordingHttpClientFactory();
        var controller = CreateController(factory);
        HttpRequest request = controller.ControllerContext.HttpContext.Request;
        request.Method = HttpMethods.Get;
        request.Headers.UserAgent = "xunit";
        request.Headers.Accept = "application/json";
        request.Headers.AcceptLanguage = "en";
        request.Headers.Cookie = "chummer_session=secret";
        request.Headers.Authorization = "Bearer chummer-secret";
        request.Headers["X-Requested-With"] = "XMLHttpRequest";
        request.Headers["X-CSRF-TOKEN"] = "public-board-token";

        IActionResult result = await controller.ParticipateBoardRootHttpApiProxy("tabs/feedback/fetch", CancellationToken.None);

        FileContentResult file = Assert.IsType<FileContentResult>(result);
        Assert.Equal("application/json", file.ContentType);
        Assert.Equal("{\"ok\":true}", Encoding.UTF8.GetString(file.FileContents));
        Assert.NotNull(factory.Request);
        Assert.Equal("https://ideas.example.test/http_api/tabs/feedback/fetch", factory.Request!.RequestUri!.ToString());
        Assert.False(factory.Request.Headers.Contains("Cookie"));
        Assert.False(factory.Request.Headers.Contains("Authorization"));
        Assert.Contains("XMLHttpRequest", factory.Request.Headers.GetValues("X-Requested-With"));
        Assert.Contains("public-board-token", factory.Request.Headers.GetValues("X-CSRF-TOKEN"));
        Assert.False(controller.Response.Headers.ContainsKey("Set-Cookie"));
    }

    private static PublicLandingController CreateController(IHttpClientFactory httpClientFactory)
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PRODUCTLIFT_FEEDBACK_URL"] = "https://ideas.example.test/feedback",
                ["CHUMMER_PUBLIC_BASE_URL"] = "https://chummer.run"
            })
            .Build();
        return new PublicLandingController(
            landing: null!,
            flipLinkDocumentPortal: null!,
            flagshipCoverage: null!,
            releases: null!,
            campaignOsProof: null!,
            releaseSelection: null!,
            actions: null!,
            accounts: null!,
            identity: null!,
            links: null!,
            experience: null!,
            participationNotifications: null!,
            installLinking: null!,
            campaignSpine: null!,
            workspaceServerPlane: null!,
            readyForTonight: null!,
            knowledgeFabric: null!,
            nexusPan: null!,
            mediaHorizons: null!,
            communityCreatorHorizons: null!,
            waveEightHorizons: null!,
            karmaForge: null!,
            buildGhostConcierge: null!,
            blackLedgerStats: null!,
            blackLedgerDispatches: null!,
            blackLedgerTickNews: null!,
            blackLedgerFactions: null!,
            blackLedgerAdvisories: null!,
            blackLedgerBriefings: null!,
            beHumanEventAdapterPosture: null!,
            gmSessionVenues: null!,
            anarchyPreview: null!,
            packageCatalog: null!,
            publicCreatorDiscovery: null!,
            chrome: null!,
            trustContent: null!,
            privacyBoundaries: null!,
            signalProjection: null!,
            signalOperations: null!,
            trustPulse: null!,
            signedInTrustStatus: null!,
            supportCases: null!,
            supportPresentation: null!,
            configuration: configuration,
            installBootstrapTickets: null!,
            personalizedInstallScripts: null!,
            releaseUploadTickets: null!,
            windowsProofInstallers: null!,
            aurPackages: null!,
            httpClientFactory: httpClientFactory,
            webHostEnvironment: null!,
            logger: NullLogger<PublicLandingController>.Instance)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
    }

    private sealed class ThrowingHttpClientFactory : IHttpClientFactory
    {
        public HttpClient CreateClient(string name)
            => new(new ThrowingHandler());
    }

    private sealed class ThrowingHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => throw new HttpRequestException("upstream unavailable", null, HttpStatusCode.BadGateway);
    }

    private sealed class RecordingHttpClientFactory : IHttpClientFactory
    {
        public HttpRequestMessage? Request { get; private set; }

        public HttpClient CreateClient(string name)
            => new(new RecordingHandler(this));

        private sealed class RecordingHandler(RecordingHttpClientFactory owner) : HttpMessageHandler
        {
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            {
                owner.Request = request;
                var response = new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent("{\"ok\":true}", Encoding.UTF8, "application/json")
                };
                response.Headers.TryAddWithoutValidation("Set-Cookie", "provider_session=bad");
                return Task.FromResult(response);
            }
        }
    }
}
