using System.Net;
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
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PRODUCTLIFT_FEEDBACK_URL"] = "https://ideas.example.test/feedback",
                ["CHUMMER_PUBLIC_BASE_URL"] = "https://chummer.run"
            })
            .Build();
        var controller = new PublicLandingController(
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
            httpClientFactory: new ThrowingHttpClientFactory(),
            webHostEnvironment: null!,
            logger: NullLogger<PublicLandingController>.Instance)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
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
}
