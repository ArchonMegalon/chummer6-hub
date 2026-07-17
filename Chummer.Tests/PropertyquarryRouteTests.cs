using System.Net;
using System.Net.Http.Headers;
using System.Text.Json;
using Chummer.Run.Api;
using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Xunit;

namespace Chummer.Tests;

public sealed class PropertyquarryRouteTests
{
    [Fact]
    public async Task PropertyquarryAccountRoutesRequireAuthentication()
    {
        using var fixture = PropertyquarryRouteFixture.Create();
        AccountsController controller = fixture.CreateAccountsController(authenticated: false);

        IActionResult desk = await controller.PropertyquarryDeskPage(CancellationToken.None);
        RedirectResult deskRedirect = Assert.IsType<RedirectResult>(desk);
        Assert.Equal("/login?next=%2Faccount%2Fpropertyquarry", deskRedirect.Url);

        IActionResult detail = await controller.PropertyquarryPropertyPage("northbound-research-lab", CancellationToken.None);
        RedirectResult detailRedirect = Assert.IsType<RedirectResult>(detail);
        Assert.Equal("/login?next=%2Faccount%2Fpropertyquarry%2Fnorthbound-research-lab", detailRedirect.Url);
    }

    [Fact]
    public async Task PropertyquarryAccountRoutesResolveToSignedInPrepSearchPaths()
    {
        using var fixture = PropertyquarryRouteFixture.Create();
        AccountsController controller = fixture.CreateAccountsController();

        IActionResult desk = await controller.PropertyquarryDeskPage(CancellationToken.None);
        RedirectResult deskRedirect = Assert.IsType<RedirectResult>(desk);
        Assert.Equal("/account/propertyquarry/northbound-research-lab", deskRedirect.Url);

        IActionResult detail = await controller.PropertyquarryPropertyPage("northbound-research-lab", CancellationToken.None);
        RedirectResult detailRedirect = Assert.IsType<RedirectResult>(detail);
        Assert.StartsWith("/account/campaigns/", detailRedirect.Url, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=Northbound%20research%20lab", detailRedirect.Url, StringComparison.Ordinal);
    }

    [Fact]
    public async Task PropertyquarryCampaignSpineApisRequireAuthentication()
    {
        using var fixture = PropertyquarryRouteFixture.Create();
        CampaignSpineController controller = fixture.CreateCampaignSpineController(authenticated: false);

        ActionResult<object> workspace = await controller.GetMyPropertyquarryWorkspace("northbound-research-lab", CancellationToken.None);
        ObjectResult workspaceProblem = Assert.IsType<ObjectResult>(workspace.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, workspaceProblem.StatusCode);

        ActionResult<object> continuity = await controller.GetMyPropertyquarryContinuity("northbound-research-lab", CancellationToken.None);
        ObjectResult continuityProblem = Assert.IsType<ObjectResult>(continuity.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, continuityProblem.StatusCode);

        ActionResult<PropertyquarryApartmentVideoArtifactRequestBridgeResult> apartmentVideo = await controller.CreateMyPropertyquarryApartmentVideoRequest(
            "northbound-research-lab",
            new PropertyquarryApartmentVideoRequest(
                Artifacts:
                [
                    new PropertyquarryApartmentVideoArtifactRenderRequest(
                        Role: "walkthrough",
                        Payload: "{\"prompt_ref\":\"propertyquarry:northbound-research-lab\"}",
                        OutputFormat: "mp4")
                ],
                ConsumeQuota: false),
            CancellationToken.None);
        ObjectResult apartmentVideoProblem = Assert.IsType<ObjectResult>(apartmentVideo.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, apartmentVideoProblem.StatusCode);
    }

    [Fact]
    public async Task PropertyquarryCampaignSpineApisReturnFirstPartyPrepDescriptors()
    {
        using var fixture = PropertyquarryRouteFixture.Create();
        CampaignSpineController controller = fixture.CreateCampaignSpineController();

        ActionResult<object> workspaceResult = await controller.GetMyPropertyquarryWorkspace("northbound-research-lab", CancellationToken.None);
        JsonElement workspace = ParsePayload(Assert.IsType<OkObjectResult>(workspaceResult.Result).Value);
        Assert.Equal("propertyquarry", workspace.GetProperty("horizon").GetString());
        Assert.Equal("shipped_mvp", workspace.GetProperty("status").GetString());
        Assert.Equal("northbound-research-lab", workspace.GetProperty("property").GetProperty("id").GetString());
        Assert.Equal("Northbound research lab", workspace.GetProperty("property").GetProperty("label").GetString());
        Assert.Equal("/account/propertyquarry/northbound-research-lab", workspace.GetProperty("property").GetProperty("accountHref").GetString());
        string? workspacePrepSearchHref = workspace.GetProperty("property").GetProperty("prepSearchAccountHref").GetString();
        Assert.NotNull(workspacePrepSearchHref);
        Assert.StartsWith("/account/campaigns/", workspacePrepSearchHref, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=Northbound%20research%20lab", workspacePrepSearchHref, StringComparison.Ordinal);
        Assert.Equal("/account/propertyquarry", workspace.GetProperty("routes").GetProperty("accountEntryHref").GetString());
        Assert.Equal("/account/propertyquarry/open", workspace.GetProperty("routes").GetProperty("accountRedirectHref").GetString());
        Assert.Equal("/api/v1/campaign-spine/me/property-continuity/{propertyId}", workspace.GetProperty("routes").GetProperty("continuityApiHrefTemplate").GetString());
        Assert.Equal("/api/v1/campaign-spine/me/property-workspaces/{propertyId}/apartment-video", workspace.GetProperty("routes").GetProperty("apartmentVideoRequestApiHrefTemplate").GetString());
        JsonElement apartmentVideo = workspace.GetProperty("apartmentVideo");
        Assert.Equal("/api/v1/campaign-spine/me/property-workspaces/northbound-research-lab/apartment-video", apartmentVideo.GetProperty("requestApiHref").GetString());
        Assert.Equal("/api/v1/horizons/artifact-requests/me", apartmentVideo.GetProperty("sharedArtifacts").GetProperty("signedInRequestCreateHref").GetString());
        Assert.Equal("/api/v1/horizons/artifact-requests/me?horizonId=propertyquarry&artifactKindOrCapabilityId=propertyquarry-apartment-video", apartmentVideo.GetProperty("sharedArtifacts").GetProperty("signedInRequestReceiptHref").GetString());
        Assert.Equal("propertyquarry-apartment-video", apartmentVideo.GetProperty("artifactCapability").GetProperty("capabilityId").GetString());
        Assert.Equal("propertyquarry:northbound-research-lab", apartmentVideo.GetProperty("artifactCapability").GetProperty("sourceRef").GetString());
        Assert.Equal("private", apartmentVideo.GetProperty("artifactCapability").GetProperty("visibility").GetString());
        JsonElement selectedWorkspace = workspace.GetProperty("selectedWorkspace");
        Assert.Equal(JsonValueKind.Object, selectedWorkspace.ValueKind);
        Assert.StartsWith("/account/campaigns/", selectedWorkspace.GetProperty("accountHref").GetString(), StringComparison.Ordinal);
        Assert.Contains("?prepQuery=Northbound%20research%20lab", selectedWorkspace.GetProperty("accountHref").GetString(), StringComparison.Ordinal);
        Assert.Contains("?queryText=Northbound%20research%20lab", selectedWorkspace.GetProperty("prepLibraryApiHref").GetString(), StringComparison.Ordinal);

        ActionResult<object> continuityResult = await controller.GetMyPropertyquarryContinuity("northbound-research-lab", CancellationToken.None);
        JsonElement continuity = ParsePayload(Assert.IsType<OkObjectResult>(continuityResult.Result).Value);
        Assert.Equal("propertyquarry", continuity.GetProperty("horizon").GetString());
        string? continuityPrepSearchHref = continuity.GetProperty("property").GetProperty("prepSearchAccountHref").GetString();
        Assert.NotNull(continuityPrepSearchHref);
        Assert.StartsWith("/account/campaigns/", continuityPrepSearchHref, StringComparison.Ordinal);
        Assert.Contains("?prepQuery=Northbound%20research%20lab", continuityPrepSearchHref, StringComparison.Ordinal);
        Assert.True(continuity.GetProperty("continuity").GetProperty("workspaceAvailable").GetBoolean());
        Assert.Equal("Northbound research lab", continuity.GetProperty("continuity").GetProperty("searchQuery").GetString());
        Assert.StartsWith("/account/campaigns/", continuity.GetProperty("continuity").GetProperty("workspaceAccountHref").GetString(), StringComparison.Ordinal);
        Assert.Contains("?prepQuery=Northbound%20research%20lab", continuity.GetProperty("continuity").GetProperty("workspaceAccountHref").GetString(), StringComparison.Ordinal);
        Assert.Contains("?queryText=Northbound%20research%20lab", continuity.GetProperty("continuity").GetProperty("prepLibraryApiHref").GetString(), StringComparison.Ordinal);
        Assert.Equal("propertyquarry-apartment-video", continuity.GetProperty("apartmentVideo").GetProperty("artifactCapability").GetProperty("capabilityId").GetString());
        Assert.Equal("not_exposed", continuity.GetProperty("boundary").GetProperty("providerTruth").GetString());
    }

    [Fact]
    public async Task PropertyquarryApartmentVideoRequestReturnsGovernedReceiptWithoutQuotaBurn()
    {
        using var fixture = PropertyquarryRouteFixture.Create();
        CampaignSpineController controller = fixture.CreateCampaignSpineController();

        ActionResult<PropertyquarryApartmentVideoArtifactRequestBridgeResult> result = await controller.CreateMyPropertyquarryApartmentVideoRequest(
            "northbound-research-lab",
            new PropertyquarryApartmentVideoRequest(
                Artifacts:
                [
                    new PropertyquarryApartmentVideoArtifactRenderRequest(
                        Role: "walkthrough",
                        Payload: "{\"prompt_ref\":\"propertyquarry:northbound-research-lab\"}",
                        OutputFormat: "mp4",
                        AspectRatio: "16:9",
                        DurationProfile: "short",
                        MaxBytes: 64 * 1024 * 1024)
                ],
                ConsumeQuota: false),
            CancellationToken.None);

        OkObjectResult ok = Assert.IsType<OkObjectResult>(result.Result);
        PropertyquarryApartmentVideoArtifactRequestBridgeResult payload = Assert.IsType<PropertyquarryApartmentVideoArtifactRequestBridgeResult>(ok.Value);
        Assert.Equal(StatusCodes.Status200OK, ok.StatusCode);
        Assert.Equal("accepted", payload.ArtifactRequestReceipt.Status);
        Assert.Equal("propertyquarry-apartment-video", payload.ArtifactRequestReceipt.CapabilityId);
        Assert.Equal("propertyquarry:apartment-video:northbound-research-lab:northbound-research-lab-apartment-video", payload.ArtifactRequestReceipt.SourceRef);
        Assert.NotNull(payload.ArtifactRequestReceipt.GovernedRenderRequest);
        Assert.Equal("northbound-research-lab", payload.Payload.Property.Id);
        Assert.False(payload.Payload.ConsumeQuota);
    }

    [Fact]
    public async Task PropertyquarryRoutesReturnNotFoundForUnknownProperty()
    {
        using var fixture = PropertyquarryRouteFixture.Create();
        AccountsController accountController = fixture.CreateAccountsController();
        CampaignSpineController campaignController = fixture.CreateCampaignSpineController();

        Assert.IsType<NotFoundResult>(await accountController.PropertyquarryPropertyPage("unknown-property", CancellationToken.None));
        Assert.IsType<NotFoundResult>((await campaignController.GetMyPropertyquarryWorkspace("unknown-property", CancellationToken.None)).Result);
        Assert.IsType<NotFoundResult>((await campaignController.GetMyPropertyquarryContinuity("unknown-property", CancellationToken.None)).Result);
    }

    private static JsonElement ParsePayload(object? payload)
    {
        using JsonDocument document = JsonDocument.Parse(JsonSerializer.Serialize(payload, new JsonSerializerOptions(JsonSerializerDefaults.Web)));
        return document.RootElement.Clone();
    }

    private sealed class PropertyquarryRouteFixture : IDisposable
    {
        private const string AccessToken = "propertyquarry-route-token";
        private readonly ServiceProvider _provider;

        private PropertyquarryRouteFixture(string root, ServiceProvider provider)
        {
            Root = root;
            _provider = provider;
        }

        public string Root { get; }

        public static PropertyquarryRouteFixture Create()
        {
            string root = Path.Combine(Path.GetTempPath(), "chummer-propertyquarry-route-tests", Guid.NewGuid().ToString("N"));
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
                    ["CHUMMER_PAYFUNNELS_BILLING_STORE_PATH"] = Path.Combine(root, "payfunnels-billing.json"),
                    ["CHUMMER_HORIZON_ARTIFACT_REQUEST_RECEIPT_STORE_PATH"] = Path.Combine(root, "horizon-artifact-request-receipts.json"),
                    ["CHUMMER_PUBLIC_CANON_ROOT"] = RepoPaths.Root,
                    ["CHUMMER_PUBLIC_BASE_URL"] = "https://chummer.run",
                    ["CHUMMER_HORIZON_PROPERTYQUARRY_CAPABILITY_PROPERTYQUARRY_APARTMENT_VIDEO_ENABLED"] = "true",
                    ["CHUMMER_LOCAL_E2E_ACCESS_TOKEN"] = AccessToken,
                    ["CHUMMER_LOCAL_E2E_SUBJECT_ID"] = "subject.propertyquarry-route",
                    ["CHUMMER_LOCAL_E2E_DISPLAY_NAME"] = "Property GM",
                    ["CHUMMER_LOCAL_E2E_EMAIL"] = "property.gm@example.invalid",
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
            return new PropertyquarryRouteFixture(root, services.BuildServiceProvider());
        }

        public AccountsController CreateAccountsController(bool authenticated = true)
        {
            AccountsController controller = ActivatorUtilities.CreateInstance<AccountsController>(_provider);
            controller.ControllerContext = new ControllerContext
            {
                HttpContext = BuildHttpContext(authenticated)
            };
            return controller;
        }

        public CampaignSpineController CreateCampaignSpineController(bool authenticated = true)
        {
            CampaignSpineController controller = ActivatorUtilities.CreateInstance<CampaignSpineController>(_provider);
            controller.ControllerContext = new ControllerContext
            {
                HttpContext = BuildHttpContext(authenticated)
            };
            return controller;
        }

        private DefaultHttpContext BuildHttpContext(bool authenticated)
        {
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

            return httpContext;
        }

        public void Dispose()
        {
            _provider.Dispose();
            if (Directory.Exists(Root))
            {
                Directory.Delete(Root, recursive: true);
            }
        }
    }

    private sealed class TestHostEnvironment : IHostEnvironment
    {
        public TestHostEnvironment(string root)
        {
            ContentRootPath = root;
            ContentRootFileProvider = new PhysicalFileProvider(root);
        }

        public string EnvironmentName { get; set; } = Environments.Development;

        public string ApplicationName { get; set; } = "Chummer.Tests";

        public string ContentRootPath { get; set; }

        public IFileProvider ContentRootFileProvider { get; set; }
    }
}
