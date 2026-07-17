using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Chummer.Run.Api.Services.Community;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class PropertyquarryApartmentVideoArtifactRequestBridgeServiceTests
{
    [Fact]
    public void BridgeServiceComposesSharedPropertyquarryApartmentVideoArtifactRequest()
    {
        PropertyquarryApartmentVideoArtifactRequestBridgeService service = new(new MediaArtifactHorizonsService());

        PropertyquarryApartmentVideoArtifactRequestBridgePayload result = service.Compose(BuildRequest(consumeQuota: false));

        Assert.Equal("propertyquarry", result.ArtifactRequest.HorizonId);
        Assert.Equal("propertyquarry-apartment-video", result.ArtifactRequest.ArtifactKindOrCapabilityId);
        Assert.Equal("private", result.ArtifactRequest.Visibility);
        Assert.Equal("propertyquarry:apartment-video:northbound-research-lab:northbound-apartment-video", result.ArtifactRequest.SourceRef);
        HorizonGovernedRenderRequestCreateRequest governed = Assert.IsType<HorizonGovernedRenderRequestCreateRequest>(result.ArtifactRequest.GovernedRenderRequest);
        IReadOnlyList<string> truthRefs = Assert.IsAssignableFrom<IReadOnlyList<string>>(governed.TruthRefs);
        IReadOnlyList<string> evidenceRefs = Assert.IsAssignableFrom<IReadOnlyList<string>>(governed.EvidenceRefs);
        IReadOnlyList<HorizonGovernedRenderArtifactSpec> artifacts = Assert.IsAssignableFrom<IReadOnlyList<HorizonGovernedRenderArtifactSpec>>(governed.Artifacts);
        Assert.Equal("magicai", governed.PreferredProvider);
        Assert.Equal("Northbound research lab apartment video", governed.Subject);
        Assert.Contains("/propertyquarry/properties/northbound-research-lab.md", truthRefs);
        Assert.Contains("/propertyquarry/properties/northbound-research-lab.json", truthRefs);
        Assert.Contains("propertyquarry:northbound-research-lab", truthRefs);
        Assert.Contains("propertyquarry:property-packet:northbound-research-lab", evidenceRefs);
        Assert.Contains("propertyquarry:style:research-lab", evidenceRefs);
        HorizonGovernedRenderArtifactSpec artifact = Assert.Single(artifacts);
        Assert.Equal("walkthrough", artifact.ArtifactId);
        Assert.Equal("walkthrough", artifact.Role);
        Assert.Equal("propertyquarry/apartment-video/walkthrough", artifact.Category);
        Assert.Equal("northbound-apartment-video:walkthrough", artifact.DeduplicationKey);
        Assert.Equal("16:9", artifact.AspectRatio);
        Assert.Equal("short", artifact.DurationProfile);
    }

    [Fact]
    public void InternalControllerReturnsSharedPropertyquarryArtifactRequestWhenAuthorized()
    {
        InternalPropertyquarryApartmentVideoController controller = BuildController(expectedToken: "approved-token");
        controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer approved-token";

        ActionResult<PropertyquarryApartmentVideoArtifactRequestBridgeResult> response = controller.ComposeArtifactRequest(BuildRequest(consumeQuota: false));

        OkObjectResult ok = Assert.IsType<OkObjectResult>(response.Result);
        PropertyquarryApartmentVideoArtifactRequestBridgeResult payload = Assert.IsType<PropertyquarryApartmentVideoArtifactRequestBridgeResult>(ok.Value);
        Assert.Equal(StatusCodes.Status200OK, ok.StatusCode);
        Assert.Equal("accepted", payload.ArtifactRequestReceipt.Status);
        Assert.Equal("propertyquarry-apartment-video", payload.ArtifactRequestReceipt.CapabilityId);
        Assert.NotNull(payload.ArtifactRequestReceipt.GovernedRenderRequest);
        Assert.Equal("northbound-research-lab", payload.Payload.Property.Id);
    }

    [Fact]
    public void InternalControllerRejectsUnauthorizedApartmentVideoArtifactRequest()
    {
        InternalPropertyquarryApartmentVideoController controller = BuildController(expectedToken: "approved-token");
        controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };

        ActionResult<PropertyquarryApartmentVideoArtifactRequestBridgeResult> response = controller.ComposeArtifactRequest(BuildRequest(consumeQuota: false));

        ObjectResult denied = Assert.IsType<ObjectResult>(response.Result);
        ProblemDetails details = Assert.IsType<ProblemDetails>(denied.Value);
        Assert.Equal(StatusCodes.Status401Unauthorized, denied.StatusCode);
        Assert.Equal("PROPERTYQUARRY apartment video authorization required", details.Title);
        Assert.Contains("authorization is required", details.Detail ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    private static InternalPropertyquarryApartmentVideoController BuildController(string expectedToken)
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["FLEET_INTERNAL_API_TOKEN"] = expectedToken,
                ["CHUMMER_HORIZON_PROPERTYQUARRY_CAPABILITY_PROPERTYQUARRY_APARTMENT_VIDEO_ENABLED"] = "true"
            })
            .Build();
        HorizonCapabilityService capabilities = new(configuration);
        HorizonArtifactRequestService artifactRequests = new(capabilities);
        PropertyquarryApartmentVideoArtifactRequestBridgeService bridge = new(new MediaArtifactHorizonsService());
        return new InternalPropertyquarryApartmentVideoController(
            bridge,
            artifactRequests,
            configuration);
    }

    private static PropertyquarryApartmentVideoArtifactRequestBridgeRequest BuildRequest(bool consumeQuota)
        => new(
            UserId: "subject.propertyquarry",
            PropertyId: "northbound-research-lab",
            WorkItemId: "northbound-apartment-video",
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
            ConsumeQuota: consumeQuota);
}
