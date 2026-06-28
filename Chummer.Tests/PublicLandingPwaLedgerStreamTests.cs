using System.Net;
using System.Text.Json;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingPwaLedgerStreamTests
{
    private const string LocalAccessToken = "local-pwa-token";
    private const string SubjectId = "subject.pwa-landing";

    [Fact]
    public async Task MobilePwaLedgerStreamReturnsOptInRequired_WhenNoSession()
    {
        using var fixture = new Fixture();
        fixture.SeedSignedUserExperience(blackLedgerNewsEmail: false);
        fixture.Controller.ControllerContext.HttpContext = fixture.CreateHttpContext(includeAuth: false);

        JsonElement payload = await fixture.ReadLedgerPayloadAsync();
        Assert.Equal("mobile_pwa_living_world", payload.GetProperty("mode").GetString());
        Assert.Equal("opt_in_required", payload.GetProperty("status").GetString());
        Assert.Equal("/account", payload.GetProperty("opt_in_route").GetString());
    }

    [Fact]
    public async Task MobilePwaLedgerStreamReturnsLiveWorldAndContinuity_WhenUserIsOptedIn()
    {
        using var fixture = new Fixture();
        fixture.SeedSignedUserExperience(blackLedgerNewsEmail: true, followedWorlds: []);
        fixture.Controller.ControllerContext.HttpContext = fixture.CreateHttpContext(includeAuth: true);

        JsonElement payload = await fixture.ReadLedgerPayloadAsync();
        Assert.Equal("mobile_pwa_living_world", payload.GetProperty("mode").GetString());
        Assert.Equal("live", payload.GetProperty("status").GetString());
        Assert.True(payload.GetProperty("world").TryGetProperty("world_name", out JsonElement _));
        Assert.True(payload.GetProperty("top_districts").GetArrayLength() > 0);
        Assert.True(payload.GetProperty("tracker").TryGetProperty("turn_route", out _));
        JsonElement continuity = payload.GetProperty("continuity");
        Assert.Equal(JsonValueKind.Object, continuity.ValueKind);
        Assert.True(continuity.GetProperty("turn").GetInt32() >= 0);
        Assert.True(continuity.GetProperty("events").GetArrayLength() >= 0);
    }

    [Fact]
    public async Task MobilePwaLedgerStreamReturnsWorldNotFollowed_WhenUserFollowsDifferentWorld()
    {
        using var fixture = new Fixture();
        fixture.SeedSignedUserExperience(blackLedgerNewsEmail: true, followedWorlds: ["other-world"]);
        fixture.Controller.ControllerContext.HttpContext = fixture.CreateHttpContext(includeAuth: true);

        JsonElement payload = await fixture.ReadLedgerPayloadAsync();
        Assert.Equal("mobile_pwa_living_world", payload.GetProperty("mode").GetString());
        Assert.Equal("world_not_followed", payload.GetProperty("status").GetString());
        Assert.Contains("select this world", payload.GetProperty("summary").GetProperty("follow_hint").GetString() ?? string.Empty, StringComparison.OrdinalIgnoreCase);
        Assert.True(payload.GetProperty("followed_worlds").GetArrayLength() > 0);
    }

    private sealed class Fixture : IDisposable
    {
        private readonly string _root;

        public Fixture()
        {
            _root = Path.Combine(Path.GetTempPath(), "chummer-pwa-landing-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_root);

            Configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_LOCAL_E2E_ACCESS_TOKEN"] = LocalAccessToken,
                    ["CHUMMER_LOCAL_E2E_SUBJECT_ID"] = SubjectId,
                    ["CHUMMER_LOCAL_E2E_DISPLAY_NAME"] = "PWA Test User",
                    ["CHUMMER_LOCAL_E2E_EMAIL"] = "pwa-test@example.invalid",
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(_root, "community.json")
                })
                .Build();

            Community = new CommunityStore(Configuration, NullLogger<CommunityStore>.Instance);
            Accounts = new AccountService(Community);
            Experience = new UserExperienceService(Community, Accounts);
            BlackLedgerStats = new BlackLedgerPublicStatsService(Configuration);
            Identity = new HubIdentityClient(new HttpClient(), Configuration, NullLogger<HubIdentityClient>.Instance);
            var serviceCollection = new ServiceCollection();
            serviceCollection.AddControllersWithViews();
            Controller = new PublicLandingController(
                landing: null!,
                flipLinkDocumentPortal: null!,
                flagshipCoverage: null!,
                releases: null!,
                campaignOsProof: null!,
                releaseSelection: null!,
                actions: null!,
                accounts: Accounts,
                identity: Identity,
                links: null!,
                experience: Experience,
                participationNotifications: null!,
                runsiteTourQuota: null!,
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
                blackLedgerStats: BlackLedgerStats,
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
                configuration: Configuration,
                installBootstrapTickets: null!,
                personalizedInstallScripts: null!,
                releaseUploadTickets: null!,
                windowsProofInstallers: null!,
                aurPackages: null!,
                participateSnapshots: null!,
                httpClientFactory: null!,
                webHostEnvironment: new FakeWebHostEnvironment(),
                logger: NullLogger<PublicLandingController>.Instance)
            {
                ControllerContext = new ControllerContext
                {
                    HttpContext = new DefaultHttpContext
                    {
                        RequestServices = serviceCollection.BuildServiceProvider()
                    }
                }
            };
        }

        public IConfiguration Configuration { get; }
        public CommunityStore Community { get; }
        public AccountService Accounts { get; }
        public UserExperienceService Experience { get; }
        public BlackLedgerPublicStatsService BlackLedgerStats { get; }
        public HubIdentityClient Identity { get; }
        public PublicLandingController Controller { get; }

        public void SeedSignedUserExperience(bool blackLedgerNewsEmail, IReadOnlyList<string>? followedWorlds = null)
        {
            _ = Experience.Upsert(new UpsertHubUserExperienceRequest(
                SubjectId,
                BlackLedgerNewsEmail: blackLedgerNewsEmail,
                BlackLedgerWorldsFollowed: followedWorlds));
        }

        public DefaultHttpContext CreateHttpContext(bool includeAuth)
        {
            DefaultHttpContext context = new();
            context.Request.Host = new HostString("localhost");
            context.Connection.RemoteIpAddress = IPAddress.Loopback;
            if (includeAuth)
            {
                context.Request.Headers.Authorization = $"Bearer {LocalAccessToken}";
            }

            return context;
        }

        public async Task<JsonElement> ReadLedgerPayloadAsync()
        {
            IActionResult result = await Controller.MobilePwaLedgerStreamJson(CancellationToken.None);
            ContentResult content = Assert.IsType<ContentResult>(result);
            Assert.False(string.IsNullOrWhiteSpace(content.Content));
            using JsonDocument document = JsonDocument.Parse(content.Content);
            return document.RootElement.Clone();
        }

        public void Dispose()
        {
            if (Directory.Exists(_root))
            {
                Directory.Delete(_root, recursive: true);
            }
        }

        private sealed class FakeWebHostEnvironment : IWebHostEnvironment
        {
            public string EnvironmentName { get; set; } = "Production";
            public string ApplicationName { get; set; } = "Chummer.Tests";
            public string ContentRootPath { get; set; } = RepoPaths.Root;
            public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
            public string WebRootPath { get; set; } = RepoPaths.Root;
            public IFileProvider WebRootFileProvider { get; set; } = new NullFileProvider();
        }
    }
}
