using System.Diagnostics;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.InstallLinking;
using Chummer.Run.Api.ViewModels;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Controllers;
using Microsoft.AspNetCore.Routing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingMobileProjectionFallbackTests
{
    [Fact]
    public async Task MobileRoleProjectionPage_UsesRoleAwareGuestPrimaryAction_WhenPlayShellProxyIsUnavailable()
    {
        using var fixture = new Fixture();

        ViewResult view = await fixture.RenderMobileRoleAsync("gm");

        MobileProjectionPageViewModel model = Assert.IsType<MobileProjectionPageViewModel>(view.Model);
        Assert.Equal("Sign in for GM", model.PrimaryAction.Label);
        Assert.Equal("/login?next=%2Fmobile%2Fgm", model.PrimaryAction.Href);
        Assert.Equal("primary", model.PrimaryAction.Tone);
        Assert.Equal("gm", model.InstallRoleKey);
        Assert.Equal("Install Chummer GM Companion", model.DocumentTitle);
        Assert.Equal("/manifest.gm.webmanifest", model.ManifestHref);
    }

    [Theory]
    [InlineData("?role=gm&token=must-not-survive", "/mobile/gm")]
    [InlineData("?role=GameMaster&session=must-not-survive", "/mobile/gm")]
    [InlineData("?role=spectator&invite=must-not-survive", "/mobile/observer")]
    [InlineData("?role=runner&utm_source=must-not-survive", "/mobile/player")]
    [InlineData("?role=admin&secret=must-not-survive", "/mobile/player")]
    [InlineData("?role=gm&role=observer&secret=must-not-survive", "/mobile/player")]
    [InlineData("?access_token=must-not-survive", "/mobile/player")]
    public async Task PlayProjectionPage_UsesRequestQueryAndEmitsOnlyQueryFreeTemporaryCanonicalRedirect(
        string requestQuery,
        string expectedLocation)
    {
        using var fixture = new Fixture();

        (int statusCode, string location) = await fixture.RequestPlayRedirectAsync(requestQuery);

        Assert.Equal(StatusCodes.Status302Found, statusCode);
        Assert.Equal(expectedLocation, location);
        Assert.DoesNotContain('?', location);
        Assert.DoesNotContain("must-not-survive", location, StringComparison.Ordinal);
        Assert.Equal("private, no-store, no-cache, max-age=0", fixture.Controller.Response.Headers.CacheControl);
        Assert.Equal("no-referrer", fixture.Controller.Response.Headers["Referrer-Policy"]);
        Assert.Equal("nosniff", fixture.Controller.Response.Headers["X-Content-Type-Options"]);
        Assert.Contains("connect-src 'none'", fixture.Controller.Response.Headers["Content-Security-Policy"].ToString());
    }

    [Fact]
    public async Task PublicRoleAliases_UseTheSamePrivateFragmentClearingRedirectFallback()
    {
        using var fixture = new Fixture();
        (Func<IActionResult> Action, string Target)[] aliases =
        [
            (fixture.Controller.PlayerProjectionAlias, "/mobile/player#"),
            (fixture.Controller.GmProjectionAlias, "/mobile/gm#"),
            (fixture.Controller.ObserverProjectionAlias, "/mobile/observer#")
        ];

        foreach ((Func<IActionResult> action, string target) in aliases)
        {
            fixture.Controller.Request.QueryString = new QueryString(
                "?sessionId=must-not-survive&deviceId=must-not-survive");
            fixture.Controller.Response.StatusCode = StatusCodes.Status200OK;
            fixture.Controller.Response.Headers.Clear();

            RedirectResult redirect = Assert.IsType<RedirectResult>(action());
            await redirect.ExecuteResultAsync(fixture.Controller.ControllerContext);

            Assert.Equal(StatusCodes.Status302Found, fixture.Controller.Response.StatusCode);
            Assert.Equal(target, fixture.Controller.Response.Headers.Location.ToString());
            Assert.DoesNotContain("must-not-survive", fixture.Controller.Response.Headers.Location.ToString());
            Assert.Equal("private, no-store, no-cache, max-age=0", fixture.Controller.Response.Headers.CacheControl);
            Assert.Equal("no-cache", fixture.Controller.Response.Headers.Pragma);
            Assert.Equal("0", fixture.Controller.Response.Headers.Expires);
            Assert.Equal("no-referrer", fixture.Controller.Response.Headers["Referrer-Policy"]);
        }
    }

    [Theory]
    [InlineData("player", "Keep your runner ready at the table.", "Your character is not embedded", "grants no seat", "/mobile/player")]
    [InlineData("gm", "Stage the table without exposing Game Master controls.", "Hidden notes never belong", "grants no Game Master authority", "/mobile/gm")]
    [InlineData("observer", "Follow the table without gaining control.", "Observation does not make private table data public", "grants no table visibility", "/mobile/observer")]
    public async Task MobileRoleProjectionPage_UsesMateriallyDistinctClosedRoleProfile(
        string role,
        string purpose,
        string privacy,
        string authority,
        string target)
    {
        using var fixture = new Fixture();

        ViewResult view = await fixture.RenderMobileRoleAsync(role);
        MobileProjectionPageViewModel model = Assert.IsType<MobileProjectionPageViewModel>(view.Model);

        Assert.Equal(role, model.RoleProfile.RoleKey);
        Assert.Equal(purpose, model.RoleProfile.PurposeHeading);
        Assert.Contains(privacy, model.RoleProfile.PrivacyHeading, StringComparison.Ordinal);
        Assert.Contains(authority, model.RoleProfile.AuthorityHeading, StringComparison.Ordinal);
        Assert.Equal(target, model.RoleProfile.InstallTargetPath);
        Assert.Equal(3, model.RoleProfile.Capabilities.Count);
        Assert.All(model.RoleProfile.Capabilities, capability => Assert.False(string.IsNullOrWhiteSpace(capability.Summary)));
    }

    [Theory]
    [InlineData("player", "Keep your runner ready at the table.", "Runner readiness", "/mobile/player", "Stage the table without exposing Game Master controls.")]
    [InlineData("gm", "Stage the table without exposing Game Master controls.", "Scene pacing", "/mobile/gm", "Follow the table without gaining control.")]
    [InlineData("observer", "Follow the table without gaining control.", "Read-mostly return", "/mobile/observer", "Keep your runner ready at the table.")]
    public async Task MobileRoleProjectionPage_RendersDistinctEncodedRoleOutput(
        string role,
        string expectedPurpose,
        string expectedCapability,
        string expectedTarget,
        string forbiddenOtherRolePurpose)
    {
        using var fixture = new Fixture();

        string html = await fixture.RenderMobileRoleHtmlAsync(role);

        Assert.Contains($"data-install-role=\"{role}\"", html, StringComparison.Ordinal);
        Assert.Contains(expectedPurpose, html, StringComparison.Ordinal);
        Assert.Contains(expectedCapability, html, StringComparison.Ordinal);
        Assert.Contains($"data-mobile-app-path=\"{expectedTarget}\"", html, StringComparison.Ordinal);
        Assert.Contains($"href=\"{expectedTarget}\"", html, StringComparison.Ordinal);
        Assert.Contains("data-mobile-app-inline-qr", html, StringComparison.Ordinal);
        Assert.Contains($"data-role-privacy-warning=\"{role}\"", html, StringComparison.Ordinal);
        Assert.Contains($"data-role-authority-warning=\"{role}\"", html, StringComparison.Ordinal);
        Assert.DoesNotContain(forbiddenOtherRolePurpose, html, StringComparison.Ordinal);
        Assert.DoesNotContain("mobile-turn-companion.js", html, StringComparison.Ordinal);
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;
        private readonly ServiceProvider _services;

        public Fixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "chummer-mobile-projection-fallback-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);

            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root,
                    ["CHUMMER_PUBLIC_BASE_URL"] = "https://chummer.run",
                    [PublicCanonicalOriginPolicy.CanonicalOriginConfigurationKey] = "https://chummer.run",
                    [PublicCanonicalOriginPolicy.AllowedHostsConfigurationKey] = "chummer.run",
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(_root, "install-linking-store.json")
                })
                .Build();

            var canon = new PublicCanonFileLoader(Configuration);
            var routeCatalog = new PublicRouteCatalogService(canon);
            var landing = new PublicLandingService(canon, new PublicActionResolver());
            var navigation = new PublicNavigationService(canon, routeCatalog);
            var releases = new PublicReleaseManifestService(Configuration);
            var releaseSelection = new ReleaseSelectionService(canon);
            var httpContextAccessor = new HttpContextAccessor();
            var chrome = new HubPageChromeService(landing, navigation, releases, releaseSelection, httpContextAccessor);
            var weeklyPulse = new WeeklyProductPulseArtifactService(Configuration, NullLogger<WeeklyProductPulseArtifactService>.Instance);
            var trustPulse = new PublicTrustPulseService(weeklyPulse, Configuration, NullLogger<PublicTrustPulseService>.Instance);
            var installLinkingStore = new InstallLinkingStore(
                Configuration,
                DataProtectionProvider.Create(Path.Combine(_root, "install-linking-keys")),
                NullLogger<InstallLinkingStore>.Instance);
            var nexusPan = new NexusPanContinuityService(installLinkingStore);
            var identity = new HubIdentityClient(new HttpClient(), Configuration, NullLogger<HubIdentityClient>.Instance);

            var webHostEnvironment = new FakeWebHostEnvironment();
            var publicOrigin = PublicCanonicalOriginPolicy.Create(Configuration, webHostEnvironment);
            var services = new ServiceCollection();
            services.AddSingleton<IConfiguration>(Configuration);
            services.AddSingleton<IWebHostEnvironment>(webHostEnvironment);
            services.AddSingleton<IHostEnvironment>(webHostEnvironment);
            services.AddSingleton(publicOrigin);
            services.AddLogging();
            services.AddSingleton<DiagnosticListener>(_ => new DiagnosticListener("Microsoft.AspNetCore"));
            services.AddSingleton<DiagnosticSource>(provider => provider.GetRequiredService<DiagnosticListener>());
            services.AddControllersWithViews()
                .AddApplicationPart(typeof(PublicLandingController).Assembly);
            _services = services.BuildServiceProvider();
            var httpContext = new DefaultHttpContext
            {
                RequestServices = _services
            };
            httpContext.Request.Host = new HostString("chummer.run");
            httpContext.Request.Scheme = "https";
            httpContext.Request.Headers.UserAgent = "xunit";
            httpContextAccessor.HttpContext = httpContext;

            Controller = new PublicLandingController(
                landing: landing,
                flipLinkDocumentPortal: null!,
                flagshipCoverage: null!,
                releases: releases,
                campaignOsProof: null!,
                releaseSelection: releaseSelection,
                actions: null!,
                accounts: null!,
                identity: identity,
                links: null!,
                experience: null!,
                participationNotifications: null!,
                runsiteTourQuota: null!,
                installLinking: null!,
                campaignSpine: null!,
                workspaceServerPlane: null!,
                readyForTonight: null!,
                knowledgeFabric: null!,
                nexusPan: nexusPan,
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
                trustPulse: trustPulse,
                signedInTrustStatus: null!,
                supportCases: null!,
                supportPresentation: null!,
                configuration: Configuration,
                installBootstrapTickets: null!,
                personalizedInstallScripts: null!,
                releaseUploadTickets: null!,
                windowsProofInstallers: null!,
                aurPackages: null!,
                participateSnapshots: null!,
                httpClientFactory: null!,
                webHostEnvironment: webHostEnvironment,
                logger: NullLogger<PublicLandingController>.Instance)
            {
                ControllerContext = new ControllerContext
                {
                    HttpContext = httpContext,
                    RouteData = new RouteData(),
                    ActionDescriptor = new ControllerActionDescriptor()
                }
            };
        }

        public IConfiguration Configuration { get; }
        public PublicLandingController Controller { get; }

        public async Task<ViewResult> RenderMobileRoleAsync(string role)
        {
            IActionResult result = await Controller.MobileRoleProjectionPage(role, CancellationToken.None);
            ViewResult view = Assert.IsType<ViewResult>(result);
            Assert.Equal("~/Views/PublicLanding/MobileProjection.cshtml", view.ViewName);
            return view;
        }

        public async Task<string> RenderMobileRoleHtmlAsync(string role)
        {
            ViewResult view = await RenderMobileRoleAsync(role);
            await using var body = new MemoryStream();
            Controller.Response.Body = body;
            await view.ExecuteResultAsync(Controller.ControllerContext);
            body.Position = 0;
            using var reader = new StreamReader(body);
            return await reader.ReadToEndAsync();
        }

        public async Task<(int StatusCode, string Location)> RequestPlayRedirectAsync(string queryString)
        {
            Controller.Request.QueryString = new QueryString(queryString);
            Controller.Response.StatusCode = StatusCodes.Status200OK;
            Controller.Response.Headers.Clear();
            IActionResult result = Controller.PlayProjectionPage();
            RedirectResult redirect = Assert.IsType<RedirectResult>(result);
            Assert.False(redirect.Permanent);
            Assert.False(redirect.PreserveMethod);
            await redirect.ExecuteResultAsync(Controller.ControllerContext);
            return (
                Controller.Response.StatusCode,
                Controller.Response.Headers.Location.ToString());
        }

        public void Dispose()
        {
            _services.Dispose();
            try
            {
                if (Directory.Exists(_root))
                {
                    Directory.Delete(_root, recursive: true);
                }
            }
            catch
            {
                // Cleanup should not hide assertion failures.
            }
        }
    }

    private sealed class FakeWebHostEnvironment : IWebHostEnvironment
    {
        public string EnvironmentName { get; set; } = "Production";
        public string ApplicationName { get; set; } = "Chummer.Tests";
        public string WebRootPath { get; set; } = RepoPaths.Root;
        public IFileProvider WebRootFileProvider { get; set; } = new NullFileProvider();
        public string ContentRootPath { get; set; } = RepoPaths.Root;
        public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
    }
}
