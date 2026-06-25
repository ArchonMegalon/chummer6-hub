using System.Net.Http.Headers;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Api.Services;
using Chummer.Run.Contracts.Billing;
using Chummer.Run.Contracts.Community;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Xunit;

namespace Chummer.Tests;

public sealed class BrilliantDirectoriesBillingTests
{
    [Fact]
    public void BillingPageUsesFreeAndSupporterWithoutFeatureSplit()
    {
        BrilliantDirectoriesBillingService service = CreateService();

        BrilliantDirectoriesBillingPageDto page = service.GetPage();

        Assert.Equal("Brilliant Directories", page.Provider);
        Assert.Equal("brilliant_directories", page.ProviderKey);
        Assert.Contains("same Chummer app", page.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Equal(1, page.MyFirstBookQuotaPolicy.FreeMonthlyBooks);
        Assert.Equal(2, page.MyFirstBookQuotaPolicy.SupporterMonthlyBooks);
        Assert.False(page.Capabilities.StoresTenantCredentials);
        Assert.False(page.Capabilities.GrantsPremiumFeatures);
        Assert.Equal("signed_membership_snapshot", page.Capabilities.SyncMode);
        Assert.Contains("supporter", page.Capabilities.SupportedPlanKeys);
        Assert.Contains("active", page.Capabilities.SupportedMembershipStatuses);
        Assert.Equal(2, page.Plans.Count);
        BillingPlanCardDto free = Assert.Single(page.Plans, item => item.PlanKey == BrilliantDirectoriesBillingConstants.FreePlanKey);
        BillingPlanCardDto supporter = Assert.Single(page.Plans, item => item.PlanKey == BrilliantDirectoriesBillingConstants.SupporterPlanKey);
        Assert.True(free.IsDefault);
        Assert.False(free.IsSupporter);
        Assert.True(supporter.IsSupporter);
        Assert.False(supporter.UnlocksProductFeatures);
        Assert.Equal("supporter_membership_marker", supporter.EntitlementEffect);
        Assert.Contains("1 Origin Book per month", free.Included);
        Assert.Contains("2 Origin Books per month", supporter.Included);
        Assert.Contains("app stays the same", supporter.Summary, StringComparison.OrdinalIgnoreCase);
        Assert.Single(free.ExampleStoryBooks);
        Assert.Equal("Origin Dossier", free.ExampleStoryBooks[0].Edition);
        Assert.Contains("Debt Before Dawn", free.ExampleStoryBooks[0].Title, StringComparison.Ordinal);
        Assert.Equal(2, supporter.ExampleStoryBooks.Count);
        Assert.Contains("Narrative Origin", supporter.ExampleStoryBooks[0].Edition, StringComparison.Ordinal);
        Assert.Contains("Runner Memoir", supporter.ExampleStoryBooks[1].Edition, StringComparison.Ordinal);
    }

    [Fact]
    public void MembershipViewKeepsBillingCopyFirstParty()
    {
        string view = File.ReadAllText(RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Billing", "Membership.cshtml"));

        Assert.Contains("Same app for everyone.", view, StringComparison.Ordinal);
        Assert.Contains("Origin books: Free 1/month. Supporter 2/month.", view, StringComparison.Ordinal);
        Assert.Contains("Required to continue", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Required for checkout", view, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Brilliant", view, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Directories", view, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("external billing", view, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("hosted billing", view, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Premium", view, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Upgrade", view, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void MyFirstBookQuotaDefaultsToFreeAllowance()
    {
        BrilliantDirectoriesBillingService service = CreateService();

        MyFirstBookQuotaSnapshotDto quota = service.GetMyFirstBookQuota("user-free", new DateTimeOffset(2026, 6, 24, 12, 0, 0, TimeSpan.Zero));

        Assert.Equal("free", quota.PlanKey);
        Assert.Equal(1, quota.MonthlyLimit);
        Assert.Equal(0, quota.MonthlyUsed);
        Assert.Equal(1, quota.MonthlyRemaining);
    }

    [Fact]
    public void MyFirstBookQuotaUsesSupporterAllowanceAndFailsClosedAfterSecondBook()
    {
        BrilliantDirectoriesBillingService service = CreateService();
        service.SyncMember(
            new BrilliantDirectoriesMemberSyncRequest(
                UserId: "user-a",
                MemberId: "bd-42",
                Email: "runner@example.com",
                PlanKey: "supporter",
                PlanName: "Supporter",
                MembershipStatus: "active",
                SupporterActive: true,
                ObservedAtUtc: new DateTimeOffset(2026, 6, 24, 10, 0, 0, TimeSpan.Zero)),
            "sync-secret");

        DateTimeOffset now = new(2026, 6, 24, 12, 0, 0, TimeSpan.Zero);
        MyFirstBookQuotaConsumeResultDto first = service.ConsumeMyFirstBookQuota("user-a", now);
        MyFirstBookQuotaConsumeResultDto second = service.ConsumeMyFirstBookQuota("user-a", now);

        Assert.Equal(1, first.Quota.MonthlyRemaining);
        Assert.Equal(0, second.Quota.MonthlyRemaining);
        Assert.Equal(2, second.Quota.MonthlyUsed);

        InvalidOperationException ex = Assert.Throws<InvalidOperationException>(() =>
            service.ConsumeMyFirstBookQuota("user-a", now));
        Assert.Contains("Monthly MyFirstBook allowance is exhausted", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void MyFirstBookQuotaCanAttachLifetimeSupporterByEmailBeforeHubUserExists()
    {
        BrilliantDirectoriesBillingService service = CreateService();
        service.SyncMember(
            new BrilliantDirectoriesMemberSyncRequest(
                UserId: "email:joschi.grey@posteo.de",
                MemberId: "manual-lifetime-joschi-grey-posteo-de",
                Email: "joschi.grey@posteo.de",
                PlanKey: "supporter",
                PlanName: "Supporter",
                MembershipStatus: "lifetime",
                SupporterActive: true,
                ObservedAtUtc: new DateTimeOffset(2026, 6, 25, 12, 0, 0, TimeSpan.Zero)),
            "sync-secret");

        DateTimeOffset now = new(2026, 6, 25, 12, 30, 0, TimeSpan.Zero);
        MyFirstBookQuotaSnapshotDto quota = service.GetMyFirstBookQuota("usr-created-later", now, "JOSCHI.GREY@POSTEO.DE");
        MyFirstBookQuotaConsumeResultDto first = service.ConsumeMyFirstBookQuota("usr-created-later", now, "joschi.grey@posteo.de");
        MyFirstBookQuotaConsumeResultDto second = service.ConsumeMyFirstBookQuota("usr-created-later", now, "joschi.grey@posteo.de");

        Assert.Equal("supporter", quota.PlanKey);
        Assert.True(quota.SupporterActive);
        Assert.Equal(2, quota.MonthlyLimit);
        Assert.Equal(1, first.Quota.MonthlyRemaining);
        Assert.Equal(0, second.Quota.MonthlyRemaining);
    }

    [Fact]
    public async Task BillingPagePreviewCarriesCurrentMyFirstBookQuota()
    {
        BrilliantDirectoriesBillingService service = CreateService();
        (BrilliantDirectoriesBillingController controller, HubUserDto user) = CreateAuthenticatedController(service, email: "runner@example.com");
        service.SyncMember(
            new BrilliantDirectoriesMemberSyncRequest(
                UserId: user.UserId,
                MemberId: "bd-42",
                Email: "runner@example.com",
                PlanKey: "supporter",
                PlanName: "Supporter",
                MembershipStatus: "active",
                SupporterActive: true,
                ObservedAtUtc: new DateTimeOffset(2026, 6, 24, 10, 0, 0, TimeSpan.Zero)),
            "sync-secret");
        service.ConsumeMyFirstBookQuota(user.UserId, new DateTimeOffset(2026, 6, 24, 12, 0, 0, TimeSpan.Zero));

        IActionResult result = await controller.BillingPage("ignored-user", "ignored@example.com");

        ViewResult view = Assert.IsType<ViewResult>(result);
        BillingMembershipPageViewModel model = Assert.IsType<BillingMembershipPageViewModel>(view.Model);
        Assert.Equal(user.UserId, model.UserId);
        Assert.NotNull(model.CurrentMyFirstBookQuota);
        Assert.Equal(2, model.CurrentMyFirstBookQuota!.MonthlyLimit);
        Assert.Equal(1, model.CurrentMyFirstBookQuota.MonthlyUsed);
        Assert.Equal(1, model.CurrentMyFirstBookQuota.MonthlyRemaining);
        Assert.NotNull(model.FreePlan);
        Assert.NotNull(model.SupporterPlan);
        Assert.Single(model.FreePlan!.ExampleStoryBooks);
        Assert.Equal(2, model.SupporterPlan!.ExampleStoryBooks.Count);
        Assert.Contains("Origin Dossier", model.FreePlan.ExampleStoryBooks[0].Edition, StringComparison.Ordinal);
        Assert.Contains("Runner Memoir", model.SupporterPlan.ExampleStoryBooks[1].Edition, StringComparison.Ordinal);
    }

    [Fact]
    public void DirectMyFirstBookQuotaApisRequireBillingSecretAndReturnQuotaOnlyWhenAuthorized()
    {
        BrilliantDirectoriesBillingService service = CreateService();
        BrilliantDirectoriesBillingController controller = new(service)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        service.ConsumeMyFirstBookQuota("user-a", new DateTimeOffset(2026, 6, 24, 12, 0, 0, TimeSpan.Zero));

        ActionResult<MyFirstBookQuotaSnapshotDto> unauthorizedLookup = controller.MyFirstBookQuota("user-a");
        ActionResult<MyFirstBookQuotaConsumeResultDto> unauthorizedConsume = controller.ConsumeMyFirstBookQuota("user-a");

        Assert.Equal(StatusCodes.Status401Unauthorized, Assert.IsType<ObjectResult>(unauthorizedLookup.Result).StatusCode);
        Assert.Equal(StatusCodes.Status401Unauthorized, Assert.IsType<ObjectResult>(unauthorizedConsume.Result).StatusCode);

        controller.ControllerContext.HttpContext.Request.Headers["X-Chummer-Billing-Secret"] = "sync-secret";
        ActionResult<MyFirstBookQuotaSnapshotDto> authorizedLookup = controller.MyFirstBookQuota("user-a");
        MyFirstBookQuotaSnapshotDto quota = Assert.IsType<MyFirstBookQuotaSnapshotDto>(Assert.IsType<OkObjectResult>(authorizedLookup.Result).Value);
        Assert.Equal(1, quota.MonthlyUsed);

        ActionResult<MyFirstBookQuotaConsumeResultDto> exhausted = controller.ConsumeMyFirstBookQuota("user-a");
        ObjectResult problem = Assert.IsType<ObjectResult>(exhausted.Result);
        Assert.Equal(StatusCodes.Status429TooManyRequests, problem.StatusCode);
    }

    [Fact]
    public async Task SignedInMyFirstBookQuotaEndpointReturnsCurrentUserQuota()
    {
        BrilliantDirectoriesBillingService service = CreateService();
        (BrilliantDirectoriesBillingController controller, HubUserDto user) = CreateAuthenticatedController(service, email: "runner@example.com");

        ActionResult<MyFirstBookQuotaSnapshotDto> result = await controller.MyFirstBookQuotaForCurrentUser();

        MyFirstBookQuotaSnapshotDto quota = Assert.IsType<MyFirstBookQuotaSnapshotDto>(Assert.IsType<OkObjectResult>(result.Result).Value);
        Assert.Equal(user.UserId, quota.UserId);
        Assert.Equal("free", quota.PlanKey);
        Assert.Equal(1, quota.MonthlyLimit);
        Assert.Equal(1, quota.MonthlyRemaining);
    }

    [Fact]
    public async Task SignedInMyFirstBookConsumeEndpointUsesCurrentUserAllowance()
    {
        BrilliantDirectoriesBillingService service = CreateService();
        (BrilliantDirectoriesBillingController controller, HubUserDto user) = CreateAuthenticatedController(service, email: "runner@example.com");
        service.SyncMember(
            new BrilliantDirectoriesMemberSyncRequest(
                UserId: user.UserId,
                MemberId: "bd-42",
                Email: "runner@example.com",
                PlanKey: "supporter",
                PlanName: "Supporter",
                MembershipStatus: "active",
                SupporterActive: true,
                ObservedAtUtc: new DateTimeOffset(2026, 6, 24, 10, 0, 0, TimeSpan.Zero)),
            "sync-secret");

        ActionResult<MyFirstBookQuotaConsumeResultDto> first = await controller.ConsumeMyFirstBookQuotaForCurrentUser();
        ActionResult<MyFirstBookQuotaConsumeResultDto> second = await controller.ConsumeMyFirstBookQuotaForCurrentUser();
        ActionResult<MyFirstBookQuotaConsumeResultDto> third = await controller.ConsumeMyFirstBookQuotaForCurrentUser();

        MyFirstBookQuotaConsumeResultDto firstPayload = Assert.IsType<MyFirstBookQuotaConsumeResultDto>(Assert.IsType<OkObjectResult>(first.Result).Value);
        MyFirstBookQuotaConsumeResultDto secondPayload = Assert.IsType<MyFirstBookQuotaConsumeResultDto>(Assert.IsType<OkObjectResult>(second.Result).Value);
        ObjectResult thirdProblem = Assert.IsType<ObjectResult>(third.Result);

        Assert.Equal(1, firstPayload.Quota.MonthlyRemaining);
        Assert.Equal(0, secondPayload.Quota.MonthlyRemaining);
        Assert.Equal(StatusCodes.Status429TooManyRequests, thirdProblem.StatusCode);
    }

    [Fact]
    public async Task SignedInMyFirstBookEndpointsReturnUnauthorizedWhenNoSessionExists()
    {
        BrilliantDirectoriesBillingService service = CreateService();
        BrilliantDirectoriesBillingController controller = new(service)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        ActionResult<MyFirstBookQuotaSnapshotDto> quota = await controller.MyFirstBookQuotaForCurrentUser();
        ActionResult<MyFirstBookQuotaConsumeResultDto> consume = await controller.ConsumeMyFirstBookQuotaForCurrentUser();

        Assert.Equal(StatusCodes.Status401Unauthorized, Assert.IsType<ObjectResult>(quota.Result).StatusCode);
        Assert.Equal(StatusCodes.Status401Unauthorized, Assert.IsType<ObjectResult>(consume.Result).StatusCode);
    }

    [Fact]
    public void SupporterCheckoutUsesConfiguredBrilliantDirectoriesUrl()
    {
        BrilliantDirectoriesBillingService service = CreateService();

        BrilliantDirectoriesCheckoutResponseDto checkout = service.CreateSupporterCheckout(
            new BrilliantDirectoriesCheckoutRequest("user-a", "runner@example.com"));

        Assert.Equal("supporter", checkout.PlanKey);
        Assert.Contains("billing.example.test/supporter", checkout.CheckoutUrl, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("existing=1&external_user=user-a", checkout.CheckoutUrl, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("contact=runner%40example.com", checkout.CheckoutUrl, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("membership_plan=supporter", checkout.CheckoutUrl, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void SyncStoresLatestMemberSnapshot()
    {
        BrilliantDirectoriesBillingService service = CreateService();

        BrilliantDirectoriesSyncResultDto result = service.SyncMember(
            new BrilliantDirectoriesMemberSyncRequest(
                UserId: "user-a",
                MemberId: "bd-42",
                Email: "runner@example.com",
                PlanKey: "supporter",
                PlanName: "Supporter",
                MembershipStatus: "active",
                SupporterActive: true,
                ObservedAtUtc: new DateTimeOffset(2026, 6, 23, 10, 0, 0, TimeSpan.Zero)),
            "sync-secret");

        BrilliantDirectoriesMemberSnapshotDto? snapshot = service.GetAccount("user-a");
        Assert.NotNull(snapshot);
        Assert.Equal("synced", result.Status);
        Assert.Equal("brilliant_directories", result.ProviderKey);
        Assert.Equal("supporter", snapshot!.PlanKey);
        Assert.Equal("Supporter", snapshot.PlanName);
        Assert.Equal("active", snapshot.MembershipStatus);
        Assert.True(snapshot.SupporterActive);
        Assert.Equal("runner@example.com", snapshot.Email);
    }

    [Fact]
    public void SyncRequiresMatchingSecret()
    {
        BrilliantDirectoriesBillingService service = CreateService();

        UnauthorizedAccessException ex = Assert.Throws<UnauthorizedAccessException>(() =>
            service.SyncMember(
                new BrilliantDirectoriesMemberSyncRequest(
                    UserId: "user-a",
                    MemberId: null,
                    Email: null,
                    PlanKey: "free",
                    PlanName: "Free",
                    MembershipStatus: "active",
                    SupporterActive: false,
                    ObservedAtUtc: DateTimeOffset.UtcNow),
                "wrong"));

        Assert.Contains("secret", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void SyncRejectsUnsupportedMembershipStatus()
    {
        BrilliantDirectoriesBillingService service = CreateService();

        InvalidOperationException ex = Assert.Throws<InvalidOperationException>(() =>
            service.SyncMember(
                new BrilliantDirectoriesMemberSyncRequest(
                    UserId: "user-a",
                    MemberId: null,
                    Email: null,
                    PlanKey: "supporter",
                    PlanName: "Supporter",
                    MembershipStatus: "trialing",
                    SupporterActive: true,
                    ObservedAtUtc: DateTimeOffset.UtcNow),
                "sync-secret"));

        Assert.Contains("Unsupported membership status", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void SyncRejectsContradictorySupporterState()
    {
        BrilliantDirectoriesBillingService service = CreateService();

        InvalidOperationException ex = Assert.Throws<InvalidOperationException>(() =>
            service.SyncMember(
                new BrilliantDirectoriesMemberSyncRequest(
                    UserId: "user-a",
                    MemberId: "bd-42",
                    Email: "runner@example.com",
                    PlanKey: "supporter",
                    PlanName: "Supporter",
                    MembershipStatus: "canceled",
                    SupporterActive: true,
                    ObservedAtUtc: DateTimeOffset.UtcNow),
                "sync-secret"));

        Assert.Contains("ambiguous provider membership state", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void MissingSupporterCheckoutUrlFailsClosed()
    {
        string root = Path.Combine(Path.GetTempPath(), "chummer-bd-tests", Guid.NewGuid().ToString("N"));
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["BRILLIANT_DIRECTORIES_SYNC_SECRET"] = "sync-secret",
                ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(root, "bd.json")
            })
            .Build();
        BrilliantDirectoriesBillingService service = new(new BrilliantDirectoriesBillingStore(configuration), new MyFirstBookUsageStore(configuration), configuration);

        BrilliantDirectoriesBillingUnavailableException ex = Assert.Throws<BrilliantDirectoriesBillingUnavailableException>(() =>
            service.CreateSupporterCheckout(new BrilliantDirectoriesCheckoutRequest("user-a", null)));

        Assert.Contains("must be configured", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public async Task BillingPageWithoutAttachedUserRedirectsToFirstPartySignIn()
    {
        BrilliantDirectoriesBillingService service = CreateService();
        BrilliantDirectoriesBillingController controller = new(service)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        IActionResult result = await controller.BillingPage();

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/auth/google/start?next=%2Faccount%2Fbilling", redirect.Url);
    }

    [Fact]
    public async Task BillingPageRequiresSignInBeforeRenderingUnavailableProviderState()
    {
        string root = Path.Combine(Path.GetTempPath(), "chummer-bd-tests", Guid.NewGuid().ToString("N"));
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(root, "bd.json")
            })
            .Build();
        BrilliantDirectoriesBillingService service = new(new BrilliantDirectoriesBillingStore(configuration), new MyFirstBookUsageStore(configuration), configuration);
        BrilliantDirectoriesBillingController controller = new(service)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        IActionResult result = await controller.BillingPage("user-a", "runner@example.com");

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/auth/google/start?next=%2Faccount%2Fbilling", redirect.Url);
    }

    [Fact]
    public async Task SignedInBillingPageReturnsServiceUnavailableInsteadOfThrowingWhenConfigurationIsMissing()
    {
        string root = Path.Combine(Path.GetTempPath(), "chummer-bd-tests", Guid.NewGuid().ToString("N"));
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(root, "bd.json")
            })
            .Build();
        BrilliantDirectoriesBillingService service = new(new BrilliantDirectoriesBillingStore(configuration), new MyFirstBookUsageStore(configuration), configuration);
        (BrilliantDirectoriesBillingController controller, _) = CreateAuthenticatedController(service, email: "runner@example.com");

        IActionResult result = await controller.BillingPage("ignored-user", "ignored@example.com");

        ViewResult view = Assert.IsType<ViewResult>(result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, controller.Response.StatusCode);
        BillingMembershipPageViewModel model = Assert.IsType<BillingMembershipPageViewModel>(view.Model);
        Assert.True(model.Unavailable);
        Assert.Contains("temporarily unavailable", model.Heading, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Unexpected server error", model.Summary, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void BillingProjectionReturnsServiceUnavailableProblemWhenConfigurationIsMissing()
    {
        string root = Path.Combine(Path.GetTempPath(), "chummer-bd-tests", Guid.NewGuid().ToString("N"));
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(root, "bd.json")
            })
            .Build();
        BrilliantDirectoriesBillingService service = new(new BrilliantDirectoriesBillingStore(configuration), new MyFirstBookUsageStore(configuration), configuration);
        BrilliantDirectoriesBillingController controller = new(service);

        ActionResult<BrilliantDirectoriesBillingPageDto> result = controller.BillingProjection();

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, problem.StatusCode);
    }

    [Fact]
    public async Task SupporterCheckoutFormReturnsServiceUnavailableWhenConfigurationIsMissing()
    {
        string root = Path.Combine(Path.GetTempPath(), "chummer-bd-tests", Guid.NewGuid().ToString("N"));
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(root, "bd.json")
            })
            .Build();
        BrilliantDirectoriesBillingService service = new(new BrilliantDirectoriesBillingStore(configuration), new MyFirstBookUsageStore(configuration), configuration);
        BrilliantDirectoriesBillingController controller = new(service);

        IActionResult result = await controller.StartSupporterCheckout(new BrilliantDirectoriesCheckoutRequest("user-a", "runner@example.com"));

        ObjectResult problem = Assert.IsType<ObjectResult>(result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, problem.StatusCode);
    }

    [Fact]
    public async Task SupporterCheckoutWithoutAttachedUserRedirectsToFirstPartySignIn()
    {
        BrilliantDirectoriesBillingService service = CreateService();
        BrilliantDirectoriesBillingController controller = new(service)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        IActionResult result = await controller.StartSupporterCheckout(new BrilliantDirectoriesCheckoutRequest("", "runner@example.com"));

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/auth/google/start?next=%2Faccount%2Fbilling", redirect.Url);
    }

    [Fact]
    public async Task DirectSupporterCheckoutWithoutAttachedUserRedirectsToFirstPartySignIn()
    {
        BrilliantDirectoriesBillingService service = CreateService();
        BrilliantDirectoriesBillingController controller = new(service)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        IActionResult result = await controller.StartSupporterCheckoutDirect();

        RedirectResult redirect = Assert.IsType<RedirectResult>(result);
        Assert.Equal("/auth/google/start?next=%2Faccount%2Fbilling%2Fsupporter%2Fstart", redirect.Url);
    }

    [Fact]
    public void SupporterCheckoutApiReturnsServiceUnavailableWhenConfigurationIsMissing()
    {
        string root = Path.Combine(Path.GetTempPath(), "chummer-bd-tests", Guid.NewGuid().ToString("N"));
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(root, "bd.json")
            })
            .Build();
        BrilliantDirectoriesBillingService service = new(new BrilliantDirectoriesBillingStore(configuration), new MyFirstBookUsageStore(configuration), configuration);
        BrilliantDirectoriesBillingController controller = new(service)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        controller.ControllerContext.HttpContext.Request.Headers["X-Chummer-Billing-Secret"] = "sync-secret";

        ActionResult<BrilliantDirectoriesCheckoutResponseDto> result = controller.StartSupporterCheckoutApi(
            new BrilliantDirectoriesCheckoutRequest("user-a", "runner@example.com"));

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, problem.StatusCode);
    }

    [Fact]
    public void SupporterCheckoutApiRequiresMatchingBillingSecret()
    {
        BrilliantDirectoriesBillingService service = CreateService();
        BrilliantDirectoriesBillingController controller = new(service)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        ActionResult<BrilliantDirectoriesCheckoutResponseDto> unauthorized = controller.StartSupporterCheckoutApi(
            new BrilliantDirectoriesCheckoutRequest("user-a", "runner@example.com"));
        Assert.Equal(StatusCodes.Status401Unauthorized, Assert.IsType<ObjectResult>(unauthorized.Result).StatusCode);

        controller.ControllerContext.HttpContext.Request.Headers["X-Chummer-Billing-Secret"] = "sync-secret";
        ActionResult<BrilliantDirectoriesCheckoutResponseDto> authorized = controller.StartSupporterCheckoutApi(
            new BrilliantDirectoriesCheckoutRequest("user-a", "runner@example.com"));
        BrilliantDirectoriesCheckoutResponseDto checkout = Assert.IsType<BrilliantDirectoriesCheckoutResponseDto>(Assert.IsType<OkObjectResult>(authorized.Result).Value);
        Assert.Contains("billing.example.test/supporter", checkout.CheckoutUrl, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void AccountLookupRequiresMatchingSecret()
    {
        BrilliantDirectoriesBillingService service = CreateService();
        service.SyncMember(
            new BrilliantDirectoriesMemberSyncRequest(
                UserId: "user-a",
                MemberId: "bd-42",
                Email: "runner@example.com",
                PlanKey: "supporter",
                PlanName: "Supporter",
                MembershipStatus: "active",
                SupporterActive: true,
                ObservedAtUtc: new DateTimeOffset(2026, 6, 23, 10, 0, 0, TimeSpan.Zero)),
            "sync-secret");

        BrilliantDirectoriesBillingController controller = new(service)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        ActionResult<BrilliantDirectoriesMemberSnapshotDto> unauthorized = controller.Account("user-a");
        ObjectResult unauthorizedResult = Assert.IsType<ObjectResult>(unauthorized.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, unauthorizedResult.StatusCode);

        controller.ControllerContext.HttpContext.Request.Headers["X-Chummer-Billing-Secret"] = "sync-secret";
        ActionResult<BrilliantDirectoriesMemberSnapshotDto> authorized = controller.Account("user-a");
        OkObjectResult ok = Assert.IsType<OkObjectResult>(authorized.Result);
        BrilliantDirectoriesMemberSnapshotDto snapshot = Assert.IsType<BrilliantDirectoriesMemberSnapshotDto>(ok.Value);
        Assert.Equal("user-a", snapshot.UserId);
    }

    [Fact]
    public void SupporterCheckoutUrlMisconfigurationFailsAsProviderUnavailable()
    {
        string root = Path.Combine(Path.GetTempPath(), "chummer-bd-tests", Guid.NewGuid().ToString("N"));
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["BRILLIANT_DIRECTORIES_SUPPORTER_PLAN_URL"] = "http://billing.example.test/supporter",
                ["BRILLIANT_DIRECTORIES_SYNC_SECRET"] = "sync-secret",
                ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(root, "bd.json")
            })
            .Build();
        BrilliantDirectoriesBillingService service = new(new BrilliantDirectoriesBillingStore(configuration), new MyFirstBookUsageStore(configuration), configuration);

        BrilliantDirectoriesBillingUnavailableException ex = Assert.Throws<BrilliantDirectoriesBillingUnavailableException>(() =>
            service.CreateSupporterCheckout(new BrilliantDirectoriesCheckoutRequest("user-a", null)));

        Assert.Contains("unavailable", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    private static BrilliantDirectoriesBillingService CreateService()
    {
        string root = Path.Combine(Path.GetTempPath(), "chummer-bd-tests", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["BRILLIANT_DIRECTORIES_FREE_PLAN_URL"] = "https://billing.example.test/free",
                ["BRILLIANT_DIRECTORIES_SUPPORTER_PLAN_URL"] = "https://billing.example.test/supporter?existing=1",
                ["BRILLIANT_DIRECTORIES_MEMBER_PORTAL_URL"] = "https://billing.example.test/portal",
                ["BRILLIANT_DIRECTORIES_CHECKOUT_USER_ID_PARAMETER"] = "external_user",
                ["BRILLIANT_DIRECTORIES_CHECKOUT_EMAIL_PARAMETER"] = "contact",
                ["BRILLIANT_DIRECTORIES_CHECKOUT_PLAN_PARAMETER"] = "membership_plan",
                ["BRILLIANT_DIRECTORIES_SYNC_SECRET"] = "sync-secret",
                ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(root, "bd.json"),
                ["CHUMMER_MYFIRSTBOOK_USAGE_STORE_PATH"] = Path.Combine(root, "myfirstbook.json")
            })
            .Build();
        BrilliantDirectoriesBillingStore store = new(configuration);
        MyFirstBookUsageStore usageStore = new(configuration);
        return new BrilliantDirectoriesBillingService(store, usageStore, configuration);
    }

    private static (BrilliantDirectoriesBillingController Controller, HubUserDto User) CreateAuthenticatedController(
        BrilliantDirectoriesBillingService service,
        string email)
    {
        string root = Path.Combine(Path.GetTempPath(), "chummer-bd-tests", Guid.NewGuid().ToString("N"));
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_COMMUNITY_STORE_PATH"] = Path.Combine(root, "community.json"),
                ["IDENTITY_SERVICE_BASE_URL"] = "https://identity.example.test"
            })
            .Build();
        CommunityStore communityStore = new(configuration, NullLogger<CommunityStore>.Instance);
        AccountService accounts = new(communityStore);
        HubIdentitySubjectCache cache = new();
        const string accessToken = "test-access-token";
        cache.Set(
            "https://identity.example.test",
            accessToken,
            new AuthenticatedHubSubject(
                SubjectId: "sub-auth",
                DisplayName: "Runner",
                Email: email,
                Roles: Array.Empty<string>(),
                AccessToken: accessToken),
            TimeSpan.FromMinutes(5));
        HubIdentityClient identity = new(new HttpClient(), configuration, NullLogger<HubIdentityClient>.Instance, cache);

        DefaultHttpContext httpContext = new();
        httpContext.Request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", accessToken).ToString();

        accounts.EnsureUser("sub-auth", "Runner", email);
        HubUserDto? ensured = accounts.GetBySubject("sub-auth");
        Assert.NotNull(ensured);
        BrilliantDirectoriesBillingController controller = new(service, identity, accounts)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = httpContext
            }
        };

        return (controller, ensured!);
    }
}
