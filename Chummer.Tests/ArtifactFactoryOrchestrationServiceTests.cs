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
        Assert.Contains(result.OutputBindings, binding =>
            string.Equals(binding.Format, "preview_card", StringComparison.Ordinal)
            && string.Equals(binding.PublicRef, "/artifacts/release-bundles/avalonia-osx-arm64-installer/preview_card", StringComparison.Ordinal)
            && string.Equals(binding.ReceiptRef, $"artifact-factory:{result.JobId}:preview_card", StringComparison.Ordinal));
        Assert.Equal("chummer.run.artifact_factory.recipe_job.v1", result.MediaFactoryRequest.ContractName);
        Assert.Equal(result.OutputBindings, result.MediaFactoryRequest.OutputBindings);
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
                    ProvenanceRef: "support-case:11709",
                    SupportCaseId: "11709")
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
                    EvidenceRefs:
                    [
                        "publication:redmond-brief:v3",
                        "moderation:approved:redmond-brief",
                        "public-shelf:/artifacts/publications/redmond-brief"
                    ],
                    PublicationId: "redmond-brief")
            ]));

        Assert.Equal("publication-proof-shelf-bundle", result.RecipeId);
        Assert.Contains("/artifacts/publications/redmond-brief", result.PublicProofShelfRefs);
        Assert.Contains(result.OutputBindings, binding =>
            string.Equals(binding.Format, "caption", StringComparison.Ordinal)
            && string.Equals(binding.PublicRef, "/artifacts/publications/redmond-brief/bundles/caption", StringComparison.Ordinal)
            && string.Equals(binding.PublicationId, "redmond-brief", StringComparison.Ordinal));
        Assert.Contains(result.RequiredReceiptRefs, receipt => receipt.StartsWith("public-shelf:", StringComparison.Ordinal));
    }

    [Fact]
    public void LaunchJobBindsOutputsToApprovedAnchoredPackWhenSourcePacksAreMixed()
    {
        ArtifactFactoryOrchestrationService service = new();

        ArtifactFactoryJobLaunchResult result = service.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "release",
            RequestedBy: "fleet.release",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "aaa-evidence-pack",
                    SourcePackKind: "release_evidence",
                    ApprovalState: "approved",
                    ProvenanceRef: "release-evidence:preview:run-20260415",
                    EvidenceRefs:
                    [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-macos-arm64",
                        "public-shelf:/downloads/install/avalonia-osx-arm64-installer"
                    ],
                    PublicShelfRef: "/downloads/install/avalonia-osx-arm64-installer"),
                new ApprovedArtifactSourcePack(
                    SourcePackId: "zzz-release-artifact-pack",
                    SourcePackKind: "desktop_release",
                    ApprovalState: "approved",
                    ProvenanceRef: "release-channel:preview:run-20260415",
                    EvidenceRefs:
                    [
                        "release:artifact:avalonia-osx-arm64-installer",
                        "promotion:channel:preview",
                        "public-shelf:/downloads/install/avalonia-osx-arm64-installer"
                    ],
                    ReleaseArtifactId: "avalonia-osx-arm64-installer")
            ],
            RequestedFormats: ["packet"]));

        Assert.Contains(result.OutputBindings, binding =>
            string.Equals(binding.PublicRef, "/artifacts/release-bundles/avalonia-osx-arm64-installer/packet", StringComparison.Ordinal)
            && string.Equals(binding.ReleaseArtifactId, "avalonia-osx-arm64-installer", StringComparison.Ordinal));
        Assert.DoesNotContain(result.OutputBindings, binding =>
            binding.PublicRef.Contains(result.JobId, StringComparison.Ordinal));
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
                    EvidenceRefs: ["fix:11709", "install:preview", "support:11709"],
                    SupportCaseId: "11709")
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
                    EvidenceRefs: ["fix:11709", "install:preview", "support:11709"],
                    SupportCaseId: "11709")
            ]));

        OkObjectResult ok = Assert.IsType<OkObjectResult>(response.Result);
        ArtifactFactoryJobLaunchResult result = Assert.IsType<ArtifactFactoryJobLaunchResult>(ok.Value);
        Assert.Equal("fix-followthrough-bundle", result.RecipeId);
    }

    [Fact]
    public void LaunchJobRequiresShelfBindableRecipeAnchors()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "release",
            RequestedBy: "fleet.release",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "release-evidence-only",
                    SourcePackKind: "release_evidence",
                    ApprovalState: "approved",
                    ProvenanceRef: "release-channel:preview:run-20260415",
                    EvidenceRefs: ["release:run-20260415", "promotion:startup-smoke"])
            ])));

        Assert.Contains("release artifact id or public proof shelf ref", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobRejectsProviderSpecificOutputFormats()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "publication",
            RequestedBy: "creator.ops",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "publication-pack-redmond-brief",
                    SourcePackKind: "creator_publication",
                    ApprovalState: "approved",
                    ProvenanceRef: "publication:redmond-brief:v3",
                    EvidenceRefs:
                    [
                        "publication:redmond-brief:v3",
                        "moderation:approved:redmond-brief",
                        "public-shelf:/artifacts/publications/redmond-brief"
                    ],
                    PublicationId: "redmond-brief")
            ],
            RequestedFormats: ["preview-card", "provider-render-script"])));

        Assert.Contains("does not allow output format", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("provider_render_script", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobRejectsProviderSpecificEvidenceRefs()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchJob(new ArtifactFactoryJobLaunchRequest(
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
                        "provider:one-off-render:runway",
                        "public-shelf:/downloads/install/avalonia-osx-arm64-installer"
                    ],
                    ReleaseArtifactId: "avalonia-osx-arm64-installer")
            ])));

        Assert.Contains("provider-specific evidenceRef", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("approved source-pack receipts", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("one-off provider flows", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobRejectsRecipeWhenApprovedPackLacksRequiredReceiptEvidence()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "release",
            RequestedBy: "fleet.release",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "release-pack-20260415",
                    SourcePackKind: "desktop_release",
                    ApprovalState: "approved",
                    ProvenanceRef: "release-channel:preview:run-20260415",
                    EvidenceRefs: ["release:run-20260415", "public-shelf:/downloads/install/avalonia-osx-arm64-installer"],
                    ReleaseArtifactId: "avalonia-osx-arm64-installer")
            ])));

        Assert.Contains("requires approved source-pack receipt evidence", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("promotion", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("pending-receipt", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobBuildsSupportAndFixJobsFromAnchoredApprovedPacks()
    {
        ArtifactFactoryOrchestrationService service = new();

        ArtifactFactoryJobLaunchResult support = service.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "support",
            RequestedBy: "support.ops",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "support-pack-11709",
                    SourcePackKind: "support_case",
                    ApprovalState: "approved",
                    ProvenanceRef: "support-case:11709",
                    EvidenceRefs: ["support:11709", "privacy:redacted", "install:preview"],
                    SupportCaseId: "11709")
            ]));
        ArtifactFactoryJobLaunchResult fix = service.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "fix",
            RequestedBy: "support.ops",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "fix-pack-11709",
                    SourcePackKind: "fix_receipt",
                    ApprovalState: "approved",
                    ProvenanceRef: "fix:11709",
                    EvidenceRefs: ["fix:11709", "install:preview", "support:11709"],
                    SupportCaseId: "11709")
            ]));

        Assert.Equal("support-case-proof-packet", support.RecipeId);
        Assert.Equal(["audio", "caption", "packet", "preview_card"], support.OutputFormats);
        Assert.Contains("/account/support/11709", support.PublicProofShelfRefs);
        Assert.Equal("fix-followthrough-bundle", fix.RecipeId);
        Assert.Contains("/account/support/11709", fix.PublicProofShelfRefs);
        Assert.Contains(fix.MediaFactoryRequest.ApprovedSourcePacks, pack => string.Equals(pack.SupportCaseId, "11709", StringComparison.Ordinal));
        Assert.Contains("/account/support/11709", fix.MediaFactoryRequest.PublicProofShelfRefs);
        Assert.Contains(support.OutputBindings, binding =>
            string.Equals(binding.PublicRef, "/account/support-packets/11709/packet", StringComparison.Ordinal)
            && string.Equals(binding.ReceiptRef, $"artifact-factory:{support.JobId}:packet", StringComparison.Ordinal));
        Assert.Contains(fix.OutputBindings, binding =>
            string.Equals(binding.PublicRef, "/account/fix-followthrough/11709/packet", StringComparison.Ordinal)
            && string.Equals(binding.ReceiptRef, $"artifact-factory:{fix.JobId}:packet", StringComparison.Ordinal));
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
