using System.Net;
using System.Text;
using System.Diagnostics;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Caching.Memory;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingParticipateProxyTests : IDisposable
{
    private static readonly string ParticipateSnapshotStorePath = Path.Combine(Path.GetTempPath(), "public-landing-participate-snapshot-store.json");

    public PublicLandingParticipateProxyTests()
        => CleanupDurableState();

    public void Dispose()
        => CleanupDurableState();

    [Fact]
    public async Task ParticipateBoardProxyRedirectsRootBoardRouteToCanonicalParticipateSurface()
    {
        var controller = CreatePublicLandingController(new ThrowingHttpClientFactory());
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.ParticipateBoardProxy(null, CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/participate", redirect.Url);
    }

    [Fact]
    public async Task ParticipateBoardProxyReturnsFirstPartyFallbackWhenHostedBoardShowsProviderError()
    {
        var controller = CreatePublicLandingController(new HostedBoardErrorHttpClientFactory());
        IActionResult result = await controller.ParticipateBoardProxy("posts/mobile-companion", CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        FirstPartyParticipateBoardViewModel model = Assert.IsType<FirstPartyParticipateBoardViewModel>(view.Model);
        Assert.False(model.EmbeddedBoardEnabled);
        Assert.Equal("Board offline right now", model.SyncedLabel);
    }

    [Fact]
    public async Task ParticipatePageRendersChummerShellWithEmbeddedBoardHref()
    {
        var controller = CreatePublicLandingController(new HostedBoardChromeHttpClientFactory());
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.ParticipatePage(CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/PublicLanding/Partizipate.cshtml", view.ViewName);
        FirstPartyParticipateBoardViewModel model = Assert.IsType<FirstPartyParticipateBoardViewModel>(view.Model);
        Assert.Equal("Participate", model.Heading);
        Assert.Equal("Participate", model.Summary);
        Assert.True(model.EmbeddedBoardEnabled);
        Assert.Equal("/participate/board?embed=1", model.EmbeddedBoardHref);
        Assert.Equal("/participate/board", model.DirectBoardHref);
        Assert.DoesNotContain("productlift.dev", model.EmbeddedBoardHref ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task ParticipatePageSkipsPlaceholderHostedBoardCallsInDevelopment()
    {
        var controller = CreatePublicLandingController(
            new SlowHostedBoardPostsHttpClientFactory(),
            webHostEnvironment: new FakeWebHostEnvironment("Development"));
        var stopwatch = Stopwatch.StartNew();

        IActionResult result = await controller.ParticipatePage(CancellationToken.None);

        stopwatch.Stop();
        ViewResult view = Assert.IsType<ViewResult>(result);
        FirstPartyParticipateBoardViewModel model = Assert.IsType<FirstPartyParticipateBoardViewModel>(view.Model);
        Assert.False(model.EmbeddedBoardEnabled);
        Assert.Equal("Offline", model.StatusLabel);
        Assert.Equal("Board offline right now", model.SyncedLabel);
        Assert.True(stopwatch.Elapsed < TimeSpan.FromSeconds(3), $"development placeholder hosted-board fetch should short-circuit, but took {stopwatch.Elapsed}.");
    }

    [Fact]
    public async Task ParticipatePageDoesNotPreflightHostedBoardBeforeRenderingShell()
    {
        var controller = CreatePublicLandingController(new ThrowingHttpClientFactory());
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.ParticipatePage(CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        FirstPartyParticipateBoardViewModel model = Assert.IsType<FirstPartyParticipateBoardViewModel>(view.Model);
        Assert.True(model.EmbeddedBoardEnabled);
        Assert.Equal("Open", model.StatusLabel);
        Assert.Equal("Board is live.", model.SyncedLabel);
        Assert.Equal("/participate/board?embed=1", model.EmbeddedBoardHref);
    }

    [Fact]
    public async Task ParticipateBoardProxyRendersFirstPartyRequestDetailFromBoardJson()
    {
        var controller = CreatePublicLandingController(new HostedBoardPostsHttpClientFactory(), seedParticipateSnapshot: true);
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.ParticipateBoardProxy("p/mobile-companion-app-for-dice-rolling-sq49UU", CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/PublicLanding/ParticipatePost.cshtml", view.ViewName);
        FirstPartyParticipatePostDetailViewModel model = Assert.IsType<FirstPartyParticipatePostDetailViewModel>(view.Model);
        Assert.Equal("Mobile companion app for dice rolling", model.Post.Title);
        Assert.Equal("Open", model.Post.Status);
        Assert.Equal("/participate", model.BackHref);
        Assert.Equal("/login?next=%2Fparticipate%2Fboard%2Fp%2Fmobile-companion-app-for-dice-rolling-sq49UU", model.EntryHref);
        Assert.Contains("Adding notes and follow-up still happen on the board.", model.EntrySummary, StringComparison.Ordinal);
        Assert.StartsWith("Synced ", model.SyncedLabel, StringComparison.Ordinal);
        Assert.Single(model.BodyParagraphs);
    }

    [Fact]
    public async Task ParticipateBoardProviderAssetProxyStreamsWhitelistedProviderAssets()
    {
        var factory = new RecordingAssetHttpClientFactory();
        var controller = CreatePublicLandingController(factory);
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/css";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.ParticipateBoardProviderAssetProxy("media", "branding-stylesheets/theme.css", CancellationToken.None);

        FileContentResult file = Assert.IsType<FileContentResult>(result);
        Assert.Equal("text/css", file.ContentType);
        Assert.Equal("body{}", Encoding.UTF8.GetString(file.FileContents));
        Assert.NotNull(factory.Request);
        Assert.Equal("https://media.productlift.dev/branding-stylesheets/theme.css", factory.Request!.RequestUri!.ToString());
    }

    [Fact]
    public async Task ParticipatePageUsesCanonicalShellWhenHostedBoardChromeIsAvailable()
    {
        var controller = CreatePublicLandingController(new HostedBoardChromeHttpClientFactory(), seedParticipateSnapshot: false);
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.ParticipatePage(CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        FirstPartyParticipateBoardViewModel model = Assert.IsType<FirstPartyParticipateBoardViewModel>(view.Model);
        Assert.Equal("Participate", model.Heading);
        Assert.Equal("Participate", model.Summary);
        Assert.True(model.EmbeddedBoardEnabled);
        Assert.Equal("/participate/board?embed=1", model.EmbeddedBoardHref);
    }

    [Fact]
    public async Task RoadmapPageRendersTheSameHostedProductLiftBoardFrame()
    {
        var controller = CreatePublicLandingController(new HostedBoardChromeHttpClientFactory(), seedParticipateSnapshot: true);
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.RoadmapPage(CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/PublicLanding/Roadmap.cshtml", view.ViewName);
        RoadmapPageViewModel model = Assert.IsType<RoadmapPageViewModel>(view.Model);
        Assert.Equal("/participate/board?embed=1", model.HostedBoardHref);
    }

    [Fact]
    public async Task RoadmapBoardProxyRedirectsRootBoardRouteToParticipateBoard()
    {
        var controller = CreatePublicLandingController(new HostedBoardPostsHttpClientFactory());

        IActionResult result = await controller.RoadmapBoardProxy(null, CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/participate/board", redirect.Url);
    }

    [Fact]
    public async Task RoadmapPageDoesNotPreflightTheHostedBoardBeforeRenderingFrame()
    {
        var controller = CreatePublicLandingController(new ThrowingHttpClientFactory());
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.RoadmapPage(CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/PublicLanding/Roadmap.cshtml", view.ViewName);
        RoadmapPageViewModel model = Assert.IsType<RoadmapPageViewModel>(view.Model);
        Assert.Equal("/participate/board?embed=1", model.HostedBoardHref);
        Assert.True(model.Milestones.Count >= 0);
        Assert.False(string.IsNullOrWhiteSpace(model.PublicRequestSyncedLabel));
    }

    [Fact]
    public async Task RoadmapPageUsesFeedbackBoardWhenDedicatedRoadmapUrlIsMissing()
    {
        var controller = CreatePublicLandingController(new HostedBoardChromeHttpClientFactory(), roadmapUrl: null);
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.RoadmapPage(CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        RoadmapPageViewModel model = Assert.IsType<RoadmapPageViewModel>(view.Model);
        Assert.Equal("/participate/board?embed=1", model.HostedBoardHref);
    }

    [Fact]
    public async Task RoadmapPageStillUsesHostedBoardWhenRoadmapUrlMatchesFeedbackUrl()
    {
        var controller = CreatePublicLandingController(new HostedBoardChromeHttpClientFactory(), roadmapUrl: "https://ideas.example.test/feedback", seedParticipateSnapshot: true);
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.RoadmapPage(CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        RoadmapPageViewModel model = Assert.IsType<RoadmapPageViewModel>(view.Model);
        Assert.Equal("/participate/board?embed=1", model.HostedBoardHref);
    }

    [Fact]
    public async Task ParticipateBoardProxyServesEmbeddedShellForIframeRequests()
    {
        var controller = CreatePublicLandingController(new HostedBoardChromeHttpClientFactory());
        controller.ControllerContext.HttpContext.Request.QueryString = new QueryString("?embed=1");
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.ParticipateBoardProxy(null, CancellationToken.None);

        ContentResult content = Assert.IsType<ContentResult>(result);
        Assert.Equal("text/html; charset=utf-8", content.ContentType);
        Assert.DoesNotContain("What should Chummer do next?", content.Content ?? string.Empty, StringComparison.Ordinal);
        Assert.Contains("What do you want to see next?", content.Content ?? string.Empty, StringComparison.Ordinal);
    }

    [Fact]
    public async Task ParticipateBoardProxyReusesFreshHostedBoardHtmlCache()
    {
        using var cache = new MemoryCache(new MemoryCacheOptions());
        var factory = new CountingHostedBoardChromeHttpClientFactory();
        var firstController = CreatePublicLandingController(factory, hostedBoardHtmlCache: cache);
        firstController.ControllerContext.HttpContext.Request.QueryString = new QueryString("?embed=1");
        firstController.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        firstController.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        firstController.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult firstResult = await firstController.ParticipateBoardProxy(null, CancellationToken.None);

        ContentResult firstContent = Assert.IsType<ContentResult>(firstResult);
        Assert.Equal("miss", firstController.Response.Headers["X-Chummer-Hosted-Board-Cache"].ToString());
        Assert.Equal(1, factory.RequestCount);

        var secondController = CreatePublicLandingController(factory, hostedBoardHtmlCache: cache);
        secondController.ControllerContext.HttpContext.Request.QueryString = new QueryString("?embed=1");
        secondController.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        secondController.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        secondController.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult secondResult = await secondController.ParticipateBoardProxy(null, CancellationToken.None);

        ContentResult secondContent = Assert.IsType<ContentResult>(secondResult);
        Assert.Equal("hit", secondController.Response.Headers["X-Chummer-Hosted-Board-Cache"].ToString());
        Assert.Equal(1, factory.RequestCount);
        Assert.Equal(firstContent.Content, secondContent.Content);
    }

    [Fact]
    public async Task ParticipateBoardProxyKeepsServingWarmCacheWhenUpstreamFails()
    {
        using var cache = new MemoryCache(new MemoryCacheOptions());
        var seedingController = CreatePublicLandingController(new HostedBoardChromeHttpClientFactory(), hostedBoardHtmlCache: cache);
        seedingController.ControllerContext.HttpContext.Request.QueryString = new QueryString("?embed=1");
        seedingController.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        seedingController.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        seedingController.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";
        _ = await seedingController.ParticipateBoardProxy(null, CancellationToken.None);

        var staleController = CreatePublicLandingController(new ThrowingHttpClientFactory(), hostedBoardHtmlCache: cache);
        staleController.ControllerContext.HttpContext.Request.QueryString = new QueryString("?embed=1");
        staleController.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        staleController.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        staleController.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await staleController.ParticipateBoardProxy(null, CancellationToken.None);

        ContentResult content = Assert.IsType<ContentResult>(result);
        Assert.Equal("hit", staleController.Response.Headers["X-Chummer-Hosted-Board-Cache"].ToString());
        Assert.DoesNotContain("What should Chummer do next?", content.Content ?? string.Empty, StringComparison.Ordinal);
        Assert.Contains("What do you want to see next?", content.Content ?? string.Empty, StringComparison.Ordinal);
    }

    [Fact]
    public async Task RoadmapBoardProxyRedirectsEmbeddedRequestsToParticipateBoard()
    {
        var controller = CreatePublicLandingController(new HostedBoardChromeHttpClientFactory());
        controller.ControllerContext.HttpContext.Request.QueryString = new QueryString("?embed=1");
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.RoadmapBoardProxy(null, CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/participate/board?embed=1", redirect.Url);
    }

    [Fact]
    public async Task RoadmapBoardProxyRedirectsNestedEmbeddedRequestsToParticipateBoard()
    {
        var controller = CreatePublicLandingController(new ThrowingHttpClientFactory());
        controller.ControllerContext.HttpContext.Request.QueryString = new QueryString("?embed=1");

        IActionResult result = await controller.RoadmapBoardProxy("posts/mobile-companion", CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/participate/board/posts/mobile-companion?embed=1", redirect.Url);
    }

    [Fact]
    public async Task PartizipateAliasRedirectsToCanonicalParticipateUrl()
    {
        var controller = CreatePublicLandingController(new HostedBoardChromeHttpClientFactory());
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.ParticipateAliasPage(CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/participate", redirect.Url);
    }

    [Fact]
    public async Task PartizipateLegacyAliasEmptyPathRedirectsToCanonicalParticipate()
    {
        var controller = CreatePublicLandingController(new HostedBoardChromeHttpClientFactory());
        controller.ControllerContext.HttpContext.Request.Headers.UserAgent = "xunit";
        controller.ControllerContext.HttpContext.Request.Headers.Accept = "text/html";
        controller.ControllerContext.HttpContext.Request.Headers.AcceptLanguage = "en";

        IActionResult result = await controller.ParticipateBoardProxyLegacyAlias(string.Empty, CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/participate", redirect.Url);
    }

    [Fact]
    public void ParticipateFrameRedirectsToFirstPartyBoardRoute()
    {
        var controller = CreatePublicLandingController(new HostedBoardChromeHttpClientFactory());

        IActionResult result = controller.ParticipateBoardFrame("posts/mobile-companion");

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/participate/board/posts/mobile-companion?embed=1", redirect.Url);
    }

    [Fact]
    public void ParticipateFrameNormalizesProductLiftFeedbackRouteToHostedRoot()
    {
        var controller = CreatePublicLandingController(
            new HostedBoardChromeHttpClientFactory(),
            feedbackUrl: "https://chummer6.productlift.dev/feedback");

        IActionResult result = controller.ParticipateBoardFrame("posts/mobile-companion");

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/participate/board/posts/mobile-companion?embed=1", redirect.Url);
    }

    [Fact]
    public async Task ParticipateBoardRootApiProxyDoesNotForwardChummerCredentials()
    {
        var factory = new RecordingHttpClientFactory();
        var controller = CreatePublicLandingController(factory);
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

    private static ParticipateController CreateParticipateController(IHttpClientFactory httpClientFactory, string? roadmapUrl = "https://ideas.example.test/roadmap")
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PRODUCTLIFT_FEEDBACK_URL"] = "https://ideas.example.test/feedback",
                ["CHUMMER_PRODUCTLIFT_ROADMAP_URL"] = roadmapUrl,
                ["CHUMMER_PUBLIC_BASE_URL"] = "https://chummer.run",
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root,
                ["CHUMMER_PUBLIC_PARTICIPATE_SNAPSHOT_STORE_PATH"] = ParticipateSnapshotStorePath,
                ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = "/tmp/public-landing-participate-billing-store.json",
                ["CHUMMER_MYFIRSTBOOK_USAGE_STORE_PATH"] = "/tmp/public-landing-participate-myfirstbook-usage-store.json",
                ["CHUMMER_RUNSITE_TOUR_USAGE_STORE_PATH"] = "/tmp/public-landing-participate-runsite-tour-usage-store.json"
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
        return new ParticipateController(
            identity: new HubIdentityClient(new HttpClient(), configuration, NullLogger<HubIdentityClient>.Instance),
            chrome: chrome,
            configuration: configuration,
            logger: NullLogger<ParticipateController>.Instance,
            httpClientFactory: httpClientFactory)
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

    private static PublicLandingController CreatePublicLandingController(
        IHttpClientFactory httpClientFactory,
        string? roadmapUrl = "https://ideas.example.test/roadmap",
        string feedbackUrl = "https://ideas.example.test/feedback",
        IWebHostEnvironment? webHostEnvironment = null,
        bool seedParticipateSnapshot = false,
        IMemoryCache? hostedBoardHtmlCache = null)
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_PRODUCTLIFT_FEEDBACK_URL"] = feedbackUrl,
                ["CHUMMER_PRODUCTLIFT_ROADMAP_URL"] = roadmapUrl,
                ["CHUMMER_PUBLIC_BASE_URL"] = "https://chummer.run",
                ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root,
                ["CHUMMER_PUBLIC_PARTICIPATE_SNAPSHOT_STORE_PATH"] = ParticipateSnapshotStorePath,
                ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = "/tmp/public-landing-participate-billing-store.json",
                ["CHUMMER_MYFIRSTBOOK_USAGE_STORE_PATH"] = "/tmp/public-landing-participate-myfirstbook-usage-store.json",
                ["CHUMMER_RUNSITE_TOUR_USAGE_STORE_PATH"] = "/tmp/public-landing-participate-runsite-tour-usage-store.json"
            })
            .Build();
        var canon = new PublicCanonFileLoader(configuration);
        var chrome = new HubPageChromeService(
            new PublicLandingService(canon, new PublicActionResolver()),
            new PublicNavigationService(canon, new PublicRouteCatalogService(canon)),
            new PublicReleaseManifestService(configuration),
            new ReleaseSelectionService(canon),
            new HttpContextAccessor());
        IWebHostEnvironment environment = webHostEnvironment ?? new FakeWebHostEnvironment("Production");
        var participateStore = new PublicParticipateSnapshotStore(configuration);
        var participateSnapshots = new PublicParticipateSnapshotService(
            participateStore,
            configuration,
            httpClientFactory,
            environment,
            NullLogger<PublicParticipateSnapshotService>.Instance);
        if (seedParticipateSnapshot)
        {
            participateSnapshots.RefreshAsync(CancellationToken.None).GetAwaiter().GetResult();
        }
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
            runsiteTourQuota: BuildRunsiteTourQuota(configuration),
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
            participateSnapshots: participateSnapshots,
            httpClientFactory: httpClientFactory,
            webHostEnvironment: environment,
            logger: NullLogger<PublicLandingController>.Instance,
            hostedBoardHtmlCache: hostedBoardHtmlCache)
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

    private static RunsiteTourQuotaService BuildRunsiteTourQuota(IConfiguration configuration)
    {
        BrilliantDirectoriesBillingService billing = new(
            new BrilliantDirectoriesBillingStore(configuration),
            new MyFirstBookUsageStore(configuration),
            configuration);
        HorizonCapabilityService capabilities = new(configuration);
        HorizonArtifactQuotaService quota = new(new HorizonArtifactUsageStore(configuration), capabilities, billing);
        return new RunsiteTourQuotaService(quota, capabilities);
    }

    private sealed class FakeWebHostEnvironment(string environmentName) : IWebHostEnvironment
    {
        public string EnvironmentName { get; set; } = environmentName;
        public string ApplicationName { get; set; } = "Chummer.Tests";
        public string WebRootPath { get; set; } = RepoPaths.Root;
        public IFileProvider WebRootFileProvider { get; set; } = new NullFileProvider();
        public string ContentRootPath { get; set; } = RepoPaths.Root;
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }

    private static void CleanupDurableState()
    {
        TryDeleteFile(ParticipateSnapshotStorePath);
        TryDeleteFile("/tmp/public-landing-participate-billing-store.json");
        TryDeleteFile("/tmp/public-landing-participate-myfirstbook-usage-store.json");
        TryDeleteFile("/tmp/public-landing-participate-runsite-tour-usage-store.json");
    }

    private static void TryDeleteFile(string path)
    {
        try
        {
            if (File.Exists(path))
            {
                File.Delete(path);
            }
        }
        catch
        {
            // Test cleanup should not hide the actual assertion failure.
        }
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
  <p>Could not load posts. Please try again or contact support@productlift.dev.</p>
  <p>Network error while loading tab configuration. Please check your internet connection and try again.</p>
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
<head>
  <title>What do you want to see next?</title>
  <link rel="preload" href="https://media.productlift.dev/branding-stylesheets/theme.css" as="style" />
  <script>window._themePrimaryUrl = 'https://media.productlift.dev/branding-stylesheets/theme.css';</script>
  <script src="https://cdn.productlift.dev/js/all.js?id=370f0b336fe725b13230"></script>
</head>
<body>
<div id="menubar">
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
</div>
<div id="global_search_mount"></div>
<a class="navbar-brand" href="/participate/board">Chummer.run</a>
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

    private sealed class CountingHostedBoardChromeHttpClientFactory : IHttpClientFactory
    {
        public int RequestCount { get; private set; }

        public HttpClient CreateClient(string name)
            => new(new CountingHostedBoardChromeHandler(this));

        private sealed class CountingHostedBoardChromeHandler(CountingHostedBoardChromeHttpClientFactory owner) : HttpMessageHandler
        {
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            {
                owner.RequestCount += 1;
                const string html = """
<!doctype html>
<html lang="en">
<head>
  <title>What do you want to see next?</title>
  <script src="https://cdn.productlift.dev/js/all.js?id=370f0b336fe725b13230"></script>
</head>
<body>
<main><h1>What do you want to see next?</h1></main>
</body>
</html>
""";
                return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent(html, Encoding.UTF8, "text/html")
                });
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

    private sealed class SlowHostedBoardPostsHttpClientFactory : IHttpClientFactory
    {
        public HttpClient CreateClient(string name)
            => new(new SlowHostedBoardPostsHandler());

        private sealed class SlowHostedBoardPostsHandler : HttpMessageHandler
        {
            protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            {
                await Task.Delay(TimeSpan.FromSeconds(5), cancellationToken);
                return new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent("{}", Encoding.UTF8, "application/json")
                };
            }
        }
    }

    private sealed class RecordingAssetHttpClientFactory : IHttpClientFactory
    {
        public HttpRequestMessage? Request { get; private set; }

        public HttpClient CreateClient(string name)
            => new(new RecordingAssetHandler(this));

        private sealed class RecordingAssetHandler(RecordingAssetHttpClientFactory owner) : HttpMessageHandler
        {
            protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            {
                owner.Request = request;
                var response = new HttpResponseMessage(HttpStatusCode.OK)
                {
                    Content = new StringContent("body{}", Encoding.UTF8, "text/css")
                };
                return Task.FromResult(response);
            }
        }
    }
}
