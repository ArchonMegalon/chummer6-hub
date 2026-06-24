using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Billing;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
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
        Assert.Contains("same product", page.Summary, StringComparison.OrdinalIgnoreCase);
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
        Assert.Contains("do not unlock extra features yet", supporter.Summary, StringComparison.OrdinalIgnoreCase);
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
        BrilliantDirectoriesBillingService service = new(new BrilliantDirectoriesBillingStore(configuration), configuration);

        BrilliantDirectoriesBillingUnavailableException ex = Assert.Throws<BrilliantDirectoriesBillingUnavailableException>(() =>
            service.CreateSupporterCheckout(new BrilliantDirectoriesCheckoutRequest("user-a", null)));

        Assert.Contains("must be configured", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void BillingPageReturnsServiceUnavailableInsteadOfThrowingWhenConfigurationIsMissing()
    {
        string root = Path.Combine(Path.GetTempPath(), "chummer-bd-tests", Guid.NewGuid().ToString("N"));
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(root, "bd.json")
            })
            .Build();
        BrilliantDirectoriesBillingService service = new(new BrilliantDirectoriesBillingStore(configuration), configuration);
        BrilliantDirectoriesBillingController controller = new(service)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };

        IActionResult result = controller.BillingPage();

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
        BrilliantDirectoriesBillingService service = new(new BrilliantDirectoriesBillingStore(configuration), configuration);
        BrilliantDirectoriesBillingController controller = new(service);

        ActionResult<BrilliantDirectoriesBillingPageDto> result = controller.BillingProjection();

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, problem.StatusCode);
    }

    [Fact]
    public void SupporterCheckoutFormReturnsServiceUnavailableWhenConfigurationIsMissing()
    {
        string root = Path.Combine(Path.GetTempPath(), "chummer-bd-tests", Guid.NewGuid().ToString("N"));
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(root, "bd.json")
            })
            .Build();
        BrilliantDirectoriesBillingService service = new(new BrilliantDirectoriesBillingStore(configuration), configuration);
        BrilliantDirectoriesBillingController controller = new(service);

        IActionResult result = controller.StartSupporterCheckout(new BrilliantDirectoriesCheckoutRequest("user-a", "runner@example.com"));

        ObjectResult problem = Assert.IsType<ObjectResult>(result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, problem.StatusCode);
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
        BrilliantDirectoriesBillingService service = new(new BrilliantDirectoriesBillingStore(configuration), configuration);
        BrilliantDirectoriesBillingController controller = new(service);

        ActionResult<BrilliantDirectoriesCheckoutResponseDto> result = controller.StartSupporterCheckoutApi(
            new BrilliantDirectoriesCheckoutRequest("user-a", "runner@example.com"));

        ObjectResult problem = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status503ServiceUnavailable, problem.StatusCode);
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
        BrilliantDirectoriesBillingService service = new(new BrilliantDirectoriesBillingStore(configuration), configuration);

        BrilliantDirectoriesBillingUnavailableException ex = Assert.Throws<BrilliantDirectoriesBillingUnavailableException>(() =>
            service.CreateSupporterCheckout(new BrilliantDirectoriesCheckoutRequest("user-a", null)));

        Assert.Contains("temporarily unavailable", ex.Message, StringComparison.OrdinalIgnoreCase);
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
                ["CHUMMER_BRILLIANT_DIRECTORIES_BILLING_STORE_PATH"] = Path.Combine(root, "bd.json")
            })
            .Build();
        BrilliantDirectoriesBillingStore store = new(configuration);
        return new BrilliantDirectoriesBillingService(store, configuration);
    }
}
