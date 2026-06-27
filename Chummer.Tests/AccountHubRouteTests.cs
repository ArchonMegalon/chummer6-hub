using System.Net;
using System.Net.Http.Headers;
using Chummer.Run.Api;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Billing;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Xunit;

namespace Chummer.Tests;

public sealed class AccountHubRouteTests
{
    [Fact]
    public async Task AccountRootShowsMinimalHubForSignedInUser()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage(null, null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Hub.cshtml", view.ViewName);
        AccountHubPageViewModel model = Assert.IsType<AccountHubPageViewModel>(view.Model);
        Assert.Equal("Account", model.Chrome.Title);
        Assert.Equal("Use this page for installs, membership, and support.", model.Heading);
        Assert.Equal("Open Chummer for actual character work. Stay here for recovery, billing, and help.", model.Summary);
        Assert.Equal("Free", model.MembershipLabel);
        Assert.Equal("Same app. Supporter only changes the monthly Origin Book limit.", model.MembershipSummary);
        Assert.Equal("1 of 1 Origin Book left this month.", model.BookQuotaSummary);
        Assert.Equal(4, model.Cards.Count);
        Assert.Equal("Downloads and linked copies", model.Cards[0].Title);
        Assert.Equal("Membership", model.Cards[1].Title);
        Assert.Equal("Private help", model.Cards[2].Title);
        Assert.Equal("Runners and groups", model.Cards[3].Title);
    }

    [Fact]
    public async Task AccountRootReflectsSupporterOriginAllowanceFromSharedQuota()
    {
        using var fixture = AccountHubRouteFixture.Create();
        fixture.Billing.SyncMember(
            new BrilliantDirectoriesMemberSyncRequest(
                UserId: "subject.account-hub-route",
                MemberId: "supporter-membership",
                Email: "account.runner@example.invalid",
                PlanKey: "supporter",
                PlanName: "Supporter",
                MembershipStatus: "active",
                SupporterActive: true,
                ObservedAtUtc: new DateTimeOffset(2026, 6, 26, 12, 0, 0, TimeSpan.Zero)),
            "sync-secret");
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage(null, null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        AccountHubPageViewModel model = Assert.IsType<AccountHubPageViewModel>(view.Model);
        Assert.Equal("Supporter", model.MembershipLabel);
        Assert.Equal("Supporter adds one extra Origin Book each month.", model.MembershipSummary);
        Assert.Equal("2 of 2 Origin Books left this month.", model.BookQuotaSummary);
    }

    [Fact]
    public async Task AccountProfileRouteRedirectsToAccountHub()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage("profile", null, CancellationToken.None);

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/account", redirect.Url);
    }

    [Fact]
    public async Task AccountAccessRouteShowsMinimalSectionPage()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage("access", null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Section.cshtml", view.ViewName);
        AccountSectionPageViewModel model = Assert.IsType<AccountSectionPageViewModel>(view.Model);
        Assert.Equal("Installs", model.Eyebrow);
        Assert.Equal("Downloads, installs, and recovery.", model.Heading);
        Assert.Equal(3, model.Cards.Count);
        Assert.Equal("Current downloads", model.Cards[0].Title);
        Assert.Equal("Linked copies", model.Cards[1].Title);
        Assert.Equal("Recovery and relink", model.Cards[2].Title);
    }

    [Fact]
    public async Task AccountWorkRouteShowsMinimalSectionPage()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage("work", null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Section.cshtml", view.ViewName);
        AccountSectionPageViewModel model = Assert.IsType<AccountSectionPageViewModel>(view.Model);
        Assert.Equal("Campaigns", model.Eyebrow);
        Assert.Equal("Runners and groups.", model.Heading);
        Assert.Equal(3, model.Cards.Count);
    }

    [Fact]
    public async Task AccountParticipationRouteShowsMinimalSectionPage()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage("participation", null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Section.cshtml", view.ViewName);
        AccountSectionPageViewModel model = Assert.IsType<AccountSectionPageViewModel>(view.Model);
        Assert.Equal("Participation", model.Eyebrow);
        Assert.Equal("Feedback and roadmap.", model.Heading);
        Assert.Equal(3, model.Cards.Count);
        Assert.Equal("Feedback and roadmap", model.Cards[0].Title);
        Assert.Equal("Membership", model.Cards[1].Title);
    }

    [Fact]
    public async Task AccountSupportRouteKeepsLegacyDetailedSurface()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage("support", null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Support.cshtml", view.ViewName);
        Assert.IsType<AccountPageViewModel>(view.Model);
    }

    [Fact]
    public async Task AccountWorkDetailRouteKeepsLegacyDetailedSurface()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage("work", null, CancellationToken.None, workspaceId: "workspace-demo", runId: null, handoffId: null, entryId: null, publicationId: null, prepQuery: null);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Account.cshtml", view.ViewName);
        Assert.IsType<AccountPageViewModel>(view.Model);
    }

    [Fact]
    public async Task AccountSupportDetailRouteKeepsLegacyDetailedSurface()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();

        IActionResult result = await controller.AccountPage("support", "case-demo", CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Account.cshtml", view.ViewName);
        Assert.IsType<AccountPageViewModel>(view.Model);
    }

    [Fact]
    public async Task AccountWorkEditionQueryKeepsLegacyDetailedSurface()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();
        controller.ControllerContext.HttpContext.Request.QueryString = new QueryString("?edition=sr6");

        IActionResult result = await controller.AccountPage("work", null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Account.cshtml", view.ViewName);
        Assert.IsType<AccountPageViewModel>(view.Model);
    }

    [Fact]
    public async Task AccountAccessLocalCoProcessorQueryKeepsLegacyDetailedSurface()
    {
        using var fixture = AccountHubRouteFixture.Create();
        AccountsController controller = fixture.CreateController();
        controller.ControllerContext.HttpContext.Request.QueryString = new QueryString("?localCoProcessor=paranoid");

        IActionResult result = await controller.AccountPage("access", null, CancellationToken.None);

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal("~/Views/Accounts/Account.cshtml", view.ViewName);
        Assert.IsType<AccountPageViewModel>(view.Model);
    }

    private sealed class AccountHubRouteFixture : IDisposable
    {
        private const string AccessToken = "account-hub-route-token";
        private readonly ServiceProvider _provider;

        private AccountHubRouteFixture(string root, ServiceProvider provider)
        {
            Root = root;
            _provider = provider;
        }

        public string Root { get; }
        public BrilliantDirectoriesBillingService Billing => _provider.GetRequiredService<BrilliantDirectoriesBillingService>();

        public static AccountHubRouteFixture Create()
        {
            string root = Path.Combine(Path.GetTempPath(), "chummer-account-hub-route-tests", Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(root);
            IConfiguration configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(root, "community.json"),
                    ["CHUMMER_INSTALL_LINKING_STORE_PATH"] = Path.Combine(root, "install-linking.json"),
                    ["CHUMMER_SUPPORT_STORE_PATH"] = Path.Combine(root, "support.json"),
                    ["CHUMMER_PUBLIC_CONCIERGE_STORE_PATH"] = Path.Combine(root, "public-concierge.json"),
                    ["CHUMMER_KARMA_FORGE_STORE_PATH"] = Path.Combine(root, "karma-forge.json"),
                    ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(root, "bd-billing.json"),
                    ["CHUMMER_MYFIRSTBOOK_USAGE_STORE_PATH"] = Path.Combine(root, "myfirstbook-usage.json"),
                    ["CHUMMER_BILLING_SYNC_SECRET"] = "sync-secret",
                    ["BRILLIANT_DIRECTORIES_SYNC_SECRET"] = "sync-secret",
                    ["BRILLIANT_DIRECTORIES_SUPPORTER_PLAN_URL"] = "https://billing.example.test/supporter",
                    ["CHUMMER_PAYFUNNELS_BILLING_STORE_PATH"] = Path.Combine(root, "payfunnels-billing.json"),
                    ["CHUMMER_PUBLIC_BASE_URL"] = "https://chummer.run",
                    ["CHUMMER_LOCAL_E2E_ACCESS_TOKEN"] = AccessToken,
                    ["CHUMMER_LOCAL_E2E_SUBJECT_ID"] = "subject.account-hub-route",
                    ["CHUMMER_LOCAL_E2E_DISPLAY_NAME"] = "Account Runner",
                    ["CHUMMER_LOCAL_E2E_EMAIL"] = "account.runner@example.invalid",
                    ["IDENTITY_SERVICE_BASE_URL"] = "https://identity.example.test"
                })
                .Build();

            ServiceCollection services = new();
            services.AddSingleton(configuration);
            services.AddSingleton<IHostEnvironment>(new TestHostEnvironment(root));
            services.AddLogging();
            services.AddControllersWithViews();
            services.AddDataProtection().PersistKeysToFileSystem(new DirectoryInfo(Path.Combine(root, "data-protection-keys")));
            services
                .AddHubPublicGuideContext()
                .AddHubAccountsAndCommunityContext()
                .AddHubCampaignSpineContext()
                .AddHubControlAndSupportContext()
                .AddHubInstallAndOrchestrationAdapters();
            return new AccountHubRouteFixture(root, services.BuildServiceProvider());
        }

        public AccountsController CreateController(bool authenticated = true)
        {
            AccountsController controller = ActivatorUtilities.CreateInstance<AccountsController>(_provider);
            DefaultHttpContext httpContext = new()
            {
                RequestServices = _provider
            };
            httpContext.Request.Host = new HostString("localhost");
            httpContext.Connection.RemoteIpAddress = IPAddress.Loopback;
            if (authenticated)
            {
                httpContext.Request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", AccessToken).ToString();
            }

            controller.ControllerContext = new ControllerContext
            {
                HttpContext = httpContext
            };
            return controller;
        }

        public void Dispose()
        {
            _provider.Dispose();
            if (Directory.Exists(Root))
            {
                Directory.Delete(Root, recursive: true);
            }
        }

        private sealed class TestHostEnvironment(string contentRootPath) : IHostEnvironment
        {
            public string EnvironmentName { get; set; } = Environments.Development;
            public string ApplicationName { get; set; } = "Chummer.Tests";
            public string ContentRootPath { get; set; } = contentRootPath;
            public IFileProvider ContentRootFileProvider { get; set; } = new PhysicalFileProvider(contentRootPath);
        }
    }
}
