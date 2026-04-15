using Chummer.Run.Api.Controllers;
using Chummer.Run.Api.Services;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class ArtifactFactoryOrchestrationServiceTests
{
    [Fact]
    public void LaunchJobBuildsReleaseRecipeFromApprovedSourcePacks()
    {
        ArtifactFactoryOrchestrationService service = new();

        ArtifactFactoryJobLaunchResult result = service.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "release",
            RequestedBy: "fleet.release",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "release-pack-20260415",
                    SourcePackKind: "desktop_release",
                    ApprovalState: "approved",
                    ProvenanceRef: "release-channel:preview:run-20260415",
                    EvidenceRefs:
                    [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-macos-arm64",
                        "public-shelf:/downloads/install/avalonia-osx-arm64-installer"
                    ],
                    ReleaseArtifactId: "avalonia-osx-arm64-installer")
            ],
            RequestedFormats: ["preview-card", "caption", "packet"]));

        Assert.Equal("queued", result.State);
        Assert.Equal("release", result.Family);
        Assert.Equal("release-proof-shelf-bundle", result.RecipeId);
        Assert.Equal(["caption", "packet", "preview_card"], result.OutputFormats);
        Assert.Contains("release-pack-20260415", result.SourcePackIds);
        Assert.Contains("/downloads/install/avalonia-osx-arm64-installer", result.PublicProofShelfRefs);
        Assert.Equal("chummer.run.artifact_factory.recipe_job.v1", result.MediaFactoryRequest.ContractName);
        Assert.Contains(result.MediaFactoryRequest.RequiredReceiptRefs, receipt => receipt.StartsWith("promotion:", StringComparison.Ordinal));
        Assert.DoesNotContain(result.MediaFactoryRequest.RequiredReceiptRefs, receipt => receipt.Contains("provider", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void LaunchJobRejectsUnapprovedOneOffSourcePack()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "support",
            RequestedBy: "support.ops",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "case-11709",
                    SourcePackKind: "support_case",
                    ApprovalState: "draft",
                    ProvenanceRef: "support-case:11709")
            ])));

        Assert.Contains("not approved", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobBuildsPublicationProofShelfRoute()
    {
        ArtifactFactoryOrchestrationService service = new();

        ArtifactFactoryJobLaunchResult result = service.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "publication",
            RequestedBy: "creator.ops",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "publication-pack-redmond-brief",
                    SourcePackKind: "creator_publication",
                    ApprovalState: "approved",
                    ProvenanceRef: "publication:redmond-brief:v3",
                    EvidenceRefs: ["publication:redmond-brief:v3", "moderation:approved:redmond-brief"],
                    PublicationId: "redmond-brief")
            ]));

        Assert.Equal("publication-proof-shelf-bundle", result.RecipeId);
        Assert.Contains("/artifacts/publications/redmond-brief", result.PublicProofShelfRefs);
        Assert.Contains(result.RequiredReceiptRefs, receipt => receipt.StartsWith("public-shelf:", StringComparison.Ordinal));
    }

    [Fact]
    public void ControllerLaunchJobRequiresInternalToken()
    {
        InternalArtifactFactoryController controller = BuildController(token: "expected-token");

        ActionResult<ArtifactFactoryJobLaunchResult> result = controller.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "fix",
            RequestedBy: "support.ops",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "fix-pack-11709",
                    SourcePackKind: "fix_receipt",
                    ApprovalState: "approved",
                    ProvenanceRef: "fix:11709",
                    EvidenceRefs: ["fix:11709", "install:preview"])
            ]));

        ObjectResult unauthorized = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, unauthorized.StatusCode);
    }

    [Fact]
    public void ControllerLaunchJobReturnsRecipeJob()
    {
        InternalArtifactFactoryController controller = BuildController(token: "expected-token");
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer expected-token";

        ActionResult<ArtifactFactoryJobLaunchResult> response = controller.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "fix",
            RequestedBy: "support.ops",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "fix-pack-11709",
                    SourcePackKind: "fix_receipt",
                    ApprovalState: "approved",
                    ProvenanceRef: "fix:11709",
                    EvidenceRefs: ["fix:11709", "install:preview"])
            ]));

        OkObjectResult ok = Assert.IsType<OkObjectResult>(response.Result);
        ArtifactFactoryJobLaunchResult result = Assert.IsType<ArtifactFactoryJobLaunchResult>(ok.Value);
        Assert.Equal("fix-followthrough-bundle", result.RecipeId);
    }

    private static InternalArtifactFactoryController BuildController(string token)
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["FLEET_INTERNAL_API_TOKEN"] = token
            })
            .Build();
        var controller = new InternalArtifactFactoryController(new ArtifactFactoryOrchestrationService(), configuration)
        {
            ControllerContext = new ControllerContext
            {
                HttpContext = new DefaultHttpContext()
            }
        };
        return controller;
    }
}
