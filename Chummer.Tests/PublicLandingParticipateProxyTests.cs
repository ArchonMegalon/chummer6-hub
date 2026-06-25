using System.Net;
using System.Text;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.ViewModels;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
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
        Assert.Contains("The board is unavailable", content.Content ?? string.Empty, StringComparison.Ordinal);
        Assert.Contains("href=\"/roadmap\"", content.Content ?? string.Empty, StringComparison.Ordinal);
        Assert.DoesNotContain("Unexpected server error", content.Content ?? string.Empty, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("ProductLift", content.Content ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task ParticipateBoardProxyReturnsFirstPartyFallbackWhenHostedBoardShowsProviderError()
    {
        var controller = CreateController(new HostedBoardErrorHttpClientFactory());
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.ParticipateBoardProxy(null, CancellationToken.None);

        ContentResult content = Assert.IsType<ContentResult>(result);
        Assert.Equal("text/html; charset=utf-8", content.ContentType);
        Assert.Contains("The board is unavailable", content.Content ?? string.Empty, StringComparison.Ordinal);
        Assert.Contains("Use Support for account, install, or private details.", content.Content ?? string.Empty, StringComparison.Ordinal);
        Assert.DoesNotContain("Could not load posts", content.Content ?? string.Empty, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("support@productlift.dev", content.Content ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task ParticipateBoardProxyRemovesHostedProviderAuthAndSearchChrome()
    {
        var controller = CreateController(new HostedBoardChromeHttpClientFactory());
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.ParticipateBoardProxy(null, CancellationToken.None);

        ContentResult content = Assert.IsType<ContentResult>(result);
        string html = content.Content ?? string.Empty;
        Assert.Contains("Participate - Chummer.run", html, StringComparison.Ordinal);
        Assert.Contains("What should Chummer do next?", html, StringComparison.Ordinal);
        Assert.Contains("Short requests, clear bugs, useful ideas.", html, StringComparison.Ordinal);
        Assert.DoesNotContain("Chummer Participate", html, StringComparison.Ordinal);
        Assert.DoesNotContain("<title>What do you want to see next?", html, StringComparison.Ordinal);
        Assert.DoesNotContain("content=\"Tell us how we could make Chummer6 more useful to you\"", html, StringComparison.Ordinal);
        Assert.DoesNotContain("global-search-trigger", html, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(">Ctrl K<", html, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(">Search<", html, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(">Sign up<", html, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(">Log in<", html, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("menubar_signup", html, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("menubar_login", html, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("id=\"imageModal\"", html, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("&times;", html, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task ParticipatePageRendersFirstPartyBoardWithoutHostedIframe()
    {
        var controller = CreateController(new HostedBoardPostsHttpClientFactory());
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.ParticipatePage(CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/PublicLanding/Partizipate.cshtml", view.ViewName);
        FirstPartyParticipateBoardViewModel model = Assert.IsType<FirstPartyParticipateBoardViewModel>(view.Model);
        Assert.True(model.LoadedFromBoard);
        Assert.Equal("/participate", model.RetryHref);
        Assert.Equal("Participate", model.Heading);
        Assert.Equal("Live requests", model.StatusLabel);
        Assert.Equal(1, model.TotalRequestCount);
        Assert.StartsWith("Synced ", model.SyncedLabel, StringComparison.Ordinal);
        FirstPartyParticipatePostViewModel post = Assert.Single(model.Posts);
        Assert.Equal("Mobile companion app for dice rolling", post.Title);
        Assert.DoesNotContain("AI-powered", post.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task PartizipateAliasRendersFirstPartyBoardAtTypoUrl()
    {
        var controller = CreateController(new HostedBoardPostsHttpClientFactory());
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.ParticipateAliasPage(CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/PublicLanding/Partizipate.cshtml", view.ViewName);
        FirstPartyParticipateBoardViewModel model = Assert.IsType<FirstPartyParticipateBoardViewModel>(view.Model);
        Assert.True(model.LoadedFromBoard);
        Assert.Equal("/partizipate", model.RetryHref);
        Assert.Equal("Participate", model.Heading);
        Assert.Equal("Live requests", model.StatusLabel);
        Assert.Equal(1, model.TotalRequestCount);
        Assert.StartsWith("Synced ", model.SyncedLabel, StringComparison.Ordinal);
        FirstPartyParticipatePostViewModel post = Assert.Single(model.Posts);
        Assert.Equal("Mobile companion app for dice rolling", post.Title);
        Assert.Equal("Open", post.Status);
        Assert.Equal("Request", post.Category);
        Assert.DoesNotContain("AI-powered", post.Summary, StringComparison.OrdinalIgnoreCase);
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
                ["CHUMMER_PUBLIC_BASE_URL"] = "https://chummer.run",
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root
            })
            .Build();
        var canon = new PublicCanonFileLoader(configuration);
        var chrome = new HubPageChromeService(
            new PublicLandingService(canon, new PublicActionResolver()),
            new PublicNavigationService(canon, new PublicRouteCatalogService(canon)),
            new PublicReleaseManifestService(configuration),
            new ReleaseSelectionService(canon),
            new HttpContextAccessor());
        var services = new ServiceCollection();
        services.AddControllersWithViews();
        return new PublicLandingController(
            landing: null!,
            flipLinkDocumentPortal: null!,
            flagshipCoverage: null!,
            releases: null!,
            campaignOsProof: null!,
            releaseSelection: null!,
            actions: null!,
            accounts: null!,
            identity: new HubIdentityClient(new HttpClient(), configuration, NullLogger<HubIdentityClient>.Instance),
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
            chrome: chrome,
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
                HttpContext = new DefaultHttpContext
                {
                    RequestServices = services.BuildServiceProvider()
                }
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

    private sealed class HostedBoardErrorHttpClientFactory : IHttpClientFactory
    {
        public HttpClient CreateClient(string name)
            => new(new HostedBoardErrorHandler());

        private sealed class HostedBoardErrorHandler : HttpMessageHandler
        {
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            {
                const string html = """
<!doctype html>
<html lang="en">
<body>
<main>
  <h1>Something went wrong on our side.</h1>
  <p>Could not load posts. Please try again or contact support@example.invalid.</p>
</main>
</body>
</html>
""";
                var response = new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(html, Encoding.UTF8, "text/html")
                };
                return Task.FromResult(response);
            }
        }
    }

    private sealed class HostedBoardChromeHttpClientFactory : IHttpClientFactory
    {
        public HttpClient CreateClient(string name)
            => new(new HostedBoardChromeHandler());

        private sealed class HostedBoardChromeHandler : HttpMessageHandler
        {
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            {
                const string html = """
<!doctype html>
<html lang="en">
<head><title>What do you want to see next?</title></head>
<body>
<nav>
  <ul class="navbar-nav navbar-right ml-auto align-items-center">
    <li class="nav-item mr-2 d-none d-md-block">
      <a class="nav-link p-0" href="#" id="global-search-trigger">
        <span class="global-search-trigger-btn">
          <span>Search</span>
          <kbd class="global-search-trigger-kbd">Ctrl K</kbd>
        </span>
      </a>
    </li>
    <li class="nav-item mr-2 d-block d-md-none">
      <a class="nav-link" href="#" id="global-search-trigger-mobile">Search</a>
    </li>
    <li class="nav-item pl-0">
      <a class="nav-link pl-0" href="/register" rel="nofollow" id="menubar_signup" title="Sign up">Sign up</a>
    </li>
    <li class="nav-item">
      <a class="nav-link" href="/login" rel="nofollow" id="menubar_login" title="Log in">Log in</a>
    </li>
  </ul>
</nav>
<main><h1>What do you want to see next?</h1></main>
<div class="modal fade" id="imageModal" tabindex="-1" role="dialog" aria-hidden="true">
  <div class="modal-dialog modal-xl">
    <div class="modal-content">
      <div class="modal-header border-0 pb-0">
        <button type="button" class="close" data-dismiss="modal" aria-label="Close">
          <span aria-hidden="true">&times;</span>
        </button>
      </div>
      <div class="modal-body text-center p-0">
        <img class="img-fluid" src="" id="modalImage" style="cursor: pointer;">
      </div>
    </div>
  </div>
</div>
</body>
</html>
""";
                var response = new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(html, Encoding.UTF8, "text/html")
                };
                return Task.FromResult(response);
            }
        }
    }

    private sealed class HostedBoardPostsHttpClientFactory : IHttpClientFactory
    {
        public HttpClient CreateClient(string name)
            => new(new HostedBoardPostsHandler());

        private sealed class HostedBoardPostsHandler : HttpMessageHandler
        {
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            {
                const string json = """
{
  "data": [
    {
      "id": "sq49UU",
      "title": "Mobile companion app for dice rolling",
      "description_short": "Quick access app for rolling dice pools and checking modifiers without opening laptop at the table.",
      "votes_count": 8,
      "comments_count": 0,
      "updated_at": "2026-04-22T21:10:23.000000Z",
      "status": { "name": "Gathering votes" },
      "category": null
    }
  ],
  "hasMore": false,
  "total": 1
}
""";
                var response = new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(json, Encoding.UTF8, "application/json")
                };
                return Task.FromResult(response);
            }
        }
    }
}
