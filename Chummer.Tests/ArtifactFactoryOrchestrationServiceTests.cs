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
    public void ListRecipesPublishesApprovedSourcePackContractsForEveryFamily()
    {
        ArtifactFactoryOrchestrationService service = new();

        ArtifactFactoryRecipeCatalogResult catalog = service.ListRecipes();

        Assert.Equal("chummer.run.artifact_factory.recipe_job.v1", catalog.ContractName);
        Assert.Equal("2026-04-15", catalog.RecipeVersion);
        Assert.Equal(["fix", "publication", "release", "support"], catalog.Recipes.Select(recipe => recipe.Family).ToArray());
        Assert.Contains(catalog.Recipes, recipe =>
            string.Equals(recipe.Family, "release", StringComparison.Ordinal)
            && string.Equals(recipe.RecipeId, "release-proof-shelf-bundle", StringComparison.Ordinal)
            && recipe.AllowedSourceKinds.Contains("desktop_release")
            && recipe.RequiredReceiptPrefixes.Contains("public-shelf")
            && recipe.DefaultFormats.Contains("preview_card")
            && recipe.AllowedFormats.Contains("short_video")
            && string.Equals(recipe.RequiredAnchorDescription, "a release artifact id or public proof shelf ref", StringComparison.Ordinal));
        Assert.Contains(catalog.Recipes, recipe =>
            string.Equals(recipe.Family, "support", StringComparison.Ordinal)
            && recipe.AllowedSourceKinds.Contains("support_case")
            && recipe.RequiredReceiptPrefixes.Contains("privacy"));
        Assert.Contains(catalog.Recipes, recipe =>
            string.Equals(recipe.Family, "publication", StringComparison.Ordinal)
            && recipe.AllowedSourceKinds.Contains("creator_publication")
            && recipe.RequiredReceiptPrefixes.Contains("moderation"));
    }

    [Fact]
    public void SharedReleaseBundleFormatsStayAlignedWithReleaseRecipeCatalog()
    {
        ArtifactFactoryOrchestrationService service = new();

        ArtifactFactoryRecipeCatalogResult catalog = service.ListRecipes();
        ArtifactFactoryRecipeDefinition releaseRecipe = Assert.Single(
            catalog.Recipes,
            recipe => string.Equals(recipe.Family, "release", StringComparison.Ordinal));

        Assert.Equal(
            releaseRecipe.AllowedFormats.Order(StringComparer.OrdinalIgnoreCase).ToArray(),
            ArtifactFactoryOrchestrationService.GetReleaseBundleFormats());
    }

    [Fact]
    public void GetAllowedFormatsRejectsUnsupportedRecipeFamily()
    {
        InvalidDataException ex = Assert.Throws<InvalidDataException>(
            () => ArtifactFactoryOrchestrationService.GetAllowedFormats("operator"));

        Assert.Contains("not supported", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("operator", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

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
        Assert.Contains("/artifacts/release-bundles/avalonia-osx-arm64-installer", result.PublicProofShelfRefs);
        Assert.Contains("/artifacts/release-bundles/avalonia-osx-arm64-installer", result.MediaFactoryRequest.PublicProofShelfRefs);
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
    public void LaunchSourcePackBatchReturnsRecipeContractMetadata()
    {
        ArtifactFactoryOrchestrationService service = new();

        ArtifactFactoryJobBatchLaunchResult result = service.LaunchSourcePackBatch(new ArtifactFactorySourcePackBatchLaunchRequest(
            BatchId: "next90-m107-artifact-factory-wave",
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
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer"
                    ],
                    ReleaseArtifactId: "avalonia-linux-x64-installer")
            ],
            RequiredFamilies: ["release"]));

        Assert.Equal("chummer.run.artifact_factory.recipe_job.v1", result.ContractName);
        Assert.Equal("2026-04-15", result.RecipeVersion);
        Assert.Equal(["release-proof-shelf-bundle"], result.RecipeIds);
    }

    [Fact]
    public void LaunchSourcePackBatchBuildsCampaignColdOpenAndMissionBriefingRequests()
    {
        ArtifactFactoryOrchestrationService service = new();

        ArtifactFactoryJobBatchLaunchResult result = service.LaunchSourcePackBatch(new ArtifactFactorySourcePackBatchLaunchRequest(
            BatchId: "next90-m108-campaign-briefing-wave",
            RequestedBy: "campaign.ops",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "campaign-primer-redmond-01",
                    SourcePackKind: "campaign_primer",
                    ApprovalState: "approved",
                    ProvenanceRef: "campaign:redmond-01:primer:v2",
                    EvidenceRefs:
                    [
                        "campaign:redmond-01",
                        "primer:approved:redmond-01",
                        "audience:players",
                        "locale:de-AT"
                    ],
                    CampaignId: "redmond-01",
                    Audience: "players,gm",
                    Locale: "de-AT"),
                new ApprovedArtifactSourcePack(
                    SourcePackId: "mission-pack-arcology-01",
                    SourcePackKind: "mission_pack",
                    ApprovalState: "approved",
                    ProvenanceRef: "mission:arcology-01:briefing:v1",
                    EvidenceRefs:
                    [
                        "mission:arcology-01",
                        "briefing:approved:arcology-01",
                        "audience:players",
                        "locale:de-AT"
                    ],
                    MissionId: "arcology-01",
                    Audience: "players",
                    Locale: "de-AT")
            ],
            Audience: "players",
            Locale: "de-AT",
            RequiredFamilies: ["campaign_cold_open", "mission_briefing"]));

        Assert.Equal("queued", result.State);
        Assert.Equal(["campaign_cold_open", "mission_briefing"], result.RequiredFamilies);
        Assert.Equal(["campaign-cold-open-bundle", "mission-briefing-reel"], result.RecipeIds);
        Assert.Contains(result.Jobs, job =>
            string.Equals(job.Family, "campaign_cold_open", StringComparison.Ordinal)
            && string.Equals(job.Audience, "players", StringComparison.Ordinal)
            && string.Equals(job.Locale, "de-AT", StringComparison.Ordinal)
            && job.RequiredReceiptRefs.Contains("audience:players")
            && job.RequiredReceiptRefs.Contains("locale:de-AT")
            && job.PublicProofShelfRefs.Contains("/artifacts/campaigns/redmond-01/cold-open")
            && job.MediaFactoryRequest.ApprovedSourcePacks.Any(pack =>
                string.Equals(pack.CampaignId, "redmond-01", StringComparison.Ordinal)
                && string.Equals(pack.Audience, "players,gm", StringComparison.Ordinal)
                && string.Equals(pack.Locale, "de-AT", StringComparison.Ordinal)));
        Assert.Contains(result.Jobs, job =>
            string.Equals(job.Family, "mission_briefing", StringComparison.Ordinal)
            && string.Equals(job.Audience, "players", StringComparison.Ordinal)
            && string.Equals(job.Locale, "de-AT", StringComparison.Ordinal)
            && job.RequiredReceiptRefs.Contains("audience:players")
            && job.RequiredReceiptRefs.Contains("locale:de-AT")
            && job.PublicProofShelfRefs.Contains("/artifacts/missions/arcology-01/briefing")
            && job.MediaFactoryRequest.ApprovedSourcePacks.Any(pack =>
                string.Equals(pack.MissionId, "arcology-01", StringComparison.Ordinal)
                && string.Equals(pack.Audience, "players", StringComparison.Ordinal)
                && string.Equals(pack.Locale, "de-AT", StringComparison.Ordinal)));
        Assert.Contains(result.MediaFactoryRequests, request =>
            string.Equals(request.RecipeId, "campaign-cold-open-bundle", StringComparison.Ordinal)
            && request.RequiredReceiptRefs.Contains("audience:players")
            && request.RequiredReceiptRefs.Contains("locale:de-AT")
            && request.OutputBindings.Any(binding =>
                string.Equals(binding.PublicRef, "/artifacts/campaigns/redmond-01/cold-open/preview_card", StringComparison.Ordinal)));
        Assert.Contains(result.MediaFactoryRequests, request =>
            string.Equals(request.RecipeId, "mission-briefing-reel", StringComparison.Ordinal)
            && request.RequiredReceiptRefs.Contains("audience:players")
            && request.RequiredReceiptRefs.Contains("locale:de-AT")
            && request.OutputBindings.Any(binding =>
                string.Equals(binding.PublicRef, "/artifacts/missions/arcology-01/briefing/preview_card", StringComparison.Ordinal)));
    }

    [Fact]
    public void LaunchSourcePackBatchRejectsCampaignBriefingLocaleDrift()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchSourcePackBatch(new ArtifactFactorySourcePackBatchLaunchRequest(
            BatchId: "next90-m108-campaign-briefing-wave",
            RequestedBy: "campaign.ops",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "campaign-primer-redmond-01",
                    SourcePackKind: "campaign_primer",
                    ApprovalState: "approved",
                    ProvenanceRef: "campaign:redmond-01:primer:v2",
                    EvidenceRefs:
                    [
                        "campaign:redmond-01",
                        "primer:approved:redmond-01",
                        "audience:players",
                        "locale:de-AT"
                    ],
                    CampaignId: "redmond-01",
                    Audience: "players",
                    Locale: "de-AT")
            ],
            Audience: "players",
            Locale: "fr-FR",
            RequiredFamilies: ["campaign_cold_open"])));

        Assert.Contains("locale 'de-AT' does not match requested locale 'fr-FR'", ex.Message, StringComparison.Ordinal);
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
    public void LaunchJobRejectsExternalAbsoluteEvidenceRefs()
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
                    ApprovalState: "approved",
                    ProvenanceRef: "support-case:11709",
                    EvidenceRefs:
                    [
                        "support:11709",
                        "privacy:bounded",
                        "https://provider.example/artifacts/case-11709",
                        "install:preview"
                    ],
                    SupportCaseId: "11709")
            ])));

        Assert.Contains("external absolute URI", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("one-off provider flows", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobRejectsNonHttpUriLikeEvidenceRefs()
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
                        "s3://artifact-provider/rendered/redmond-brief",
                        "public-shelf:/artifacts/publications/redmond-brief"
                    ],
                    PublicationId: "redmond-brief")
            ])));

        Assert.Contains("external absolute URI", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("approved source-pack receipts", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobRejectsUriLikeProvenanceRefs()
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
                    ApprovalState: "approved",
                    ProvenanceRef: "file:///tmp/provider-rendered-case-11709",
                    EvidenceRefs: ["support:11709", "privacy:bounded", "install:preview"],
                    SupportCaseId: "11709")
            ])));

        Assert.Contains("external absolute URI", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("provenanceRef", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobRejectsDuplicateSourcePackIds()
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
                        "public-shelf:/downloads/install/avalonia-osx-arm64-installer"
                    ],
                    ReleaseArtifactId: "avalonia-osx-arm64-installer"),
                new ApprovedArtifactSourcePack(
                    SourcePackId: "release-pack-20260415",
                    SourcePackKind: "release_evidence",
                    ApprovalState: "approved",
                    ProvenanceRef: "release-evidence:preview:run-20260415",
                    EvidenceRefs:
                    [
                        "release:duplicate-evidence",
                        "promotion:startup-smoke:avalonia-macos-arm64",
                        "public-shelf:/downloads/install/avalonia-osx-arm64-installer"
                    ],
                    PublicShelfRef: "/downloads/install/avalonia-osx-arm64-installer")
            ])));

        Assert.Contains("duplicate source pack id", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("not allowed", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobRejectsWhitespacePaddedDuplicateSourcePackIds()
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
                        "public-shelf:/downloads/install/avalonia-osx-arm64-installer"
                    ],
                    ReleaseArtifactId: "avalonia-osx-arm64-installer"),
                new ApprovedArtifactSourcePack(
                    SourcePackId: "  release-pack-20260415  ",
                    SourcePackKind: "release_evidence",
                    ApprovalState: "approved",
                    ProvenanceRef: "release-evidence:preview:run-20260415",
                    EvidenceRefs:
                    [
                        "release:duplicate-evidence",
                        "promotion:startup-smoke:avalonia-macos-arm64",
                        "public-shelf:/downloads/install/avalonia-osx-arm64-installer"
                    ],
                    PublicShelfRef: "/downloads/install/avalonia-osx-arm64-installer")
            ])));

        Assert.Contains("duplicate source pack id", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("release-pack-20260415", ex.Message, StringComparison.OrdinalIgnoreCase);
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
    public void ControllerListRecipesRequiresInternalToken()
    {
        InternalArtifactFactoryController controller = BuildController(token: "expected-token");

        ActionResult<ArtifactFactoryRecipeCatalogResult> result = controller.ListRecipes();

        ObjectResult unauthorized = Assert.IsType<ObjectResult>(result.Result);
        Assert.Equal(StatusCodes.Status401Unauthorized, unauthorized.StatusCode);
    }

    [Fact]
    public void ControllerListRecipesReturnsApprovedRecipeCatalog()
    {
        InternalArtifactFactoryController controller = BuildController(token: "expected-token");
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer expected-token";

        ActionResult<ArtifactFactoryRecipeCatalogResult> response = controller.ListRecipes();

        OkObjectResult ok = Assert.IsType<OkObjectResult>(response.Result);
        ArtifactFactoryRecipeCatalogResult catalog = Assert.IsType<ArtifactFactoryRecipeCatalogResult>(ok.Value);
        Assert.Contains(catalog.Recipes, recipe =>
            string.Equals(recipe.Family, "fix", StringComparison.Ordinal)
            && string.Equals(recipe.RecipeId, "fix-followthrough-bundle", StringComparison.Ordinal)
            && recipe.RequiredReceiptPrefixes.Contains("support"));
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
    public void LaunchJobBindsReleaseOutputsToApprovedPublicShelfRefWhenArtifactIdIsAbsent()
    {
        ArtifactFactoryOrchestrationService service = new();

        ArtifactFactoryJobLaunchResult result = service.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "release",
            RequestedBy: "fleet.release",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "release-shelf-pack-20260415",
                    SourcePackKind: "release_evidence",
                    ApprovalState: "approved",
                    ProvenanceRef: "release-channel:preview:run-20260415",
                    EvidenceRefs:
                    [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/artifacts/release-bundles/current-preview-build"
                    ],
                    PublicShelfRef: "/artifacts/release-bundles/current-preview-build")
            ],
            RequestedFormats: ["preview-card"]));

        Assert.Contains("/artifacts/release-bundles/current-preview-build", result.PublicProofShelfRefs);
        Assert.Contains(result.OutputBindings, binding =>
            string.Equals(binding.PublicRef, "/artifacts/release-bundles/current-preview-build/preview_card", StringComparison.Ordinal)
            && string.Equals(binding.ReceiptRef, $"artifact-factory:{result.JobId}:preview_card", StringComparison.Ordinal));
        Assert.DoesNotContain(result.OutputBindings, binding =>
            binding.PublicRef.Contains("/release-bundles/current-preview-build/bundles/", StringComparison.Ordinal));
        Assert.Contains(result.MediaFactoryRequest.ApprovedSourcePacks, pack =>
            string.Equals(pack.PublicShelfRef, "/artifacts/release-bundles/current-preview-build", StringComparison.Ordinal));
    }

    [Fact]
    public void LaunchJobBindsReleaseDownloadShelfAnchorToReleaseBundleShelf()
    {
        ArtifactFactoryOrchestrationService service = new();

        ArtifactFactoryJobLaunchResult result = service.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "release",
            RequestedBy: "fleet.release",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "release-download-shelf-pack-20260415",
                    SourcePackKind: "release_evidence",
                    ApprovalState: "approved",
                    ProvenanceRef: "release-channel:preview:run-20260415",
                    EvidenceRefs:
                    [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer"
                    ],
                    PublicShelfRef: "/downloads/install/avalonia-linux-x64-installer")
            ],
            RequestedFormats: ["packet"]));

        Assert.Contains("/downloads/install/avalonia-linux-x64-installer", result.PublicProofShelfRefs);
        Assert.Contains("/artifacts/release-bundles/avalonia-linux-x64-installer", result.PublicProofShelfRefs);
        Assert.Contains("/artifacts/release-bundles/avalonia-linux-x64-installer", result.MediaFactoryRequest.PublicProofShelfRefs);
        Assert.Contains(result.OutputBindings, binding =>
            string.Equals(binding.PublicRef, "/artifacts/release-bundles/avalonia-linux-x64-installer/packet", StringComparison.Ordinal)
            && string.Equals(binding.ReceiptRef, $"artifact-factory:{result.JobId}:packet", StringComparison.Ordinal));
        Assert.DoesNotContain(result.OutputBindings, binding =>
            binding.PublicRef.StartsWith("/downloads/install/", StringComparison.OrdinalIgnoreCase));
    }

    [Fact]
    public void LaunchJobBindsPublicationOutputsToApprovedPublicShelfRefWhenPublicationIdIsAbsent()
    {
        ArtifactFactoryOrchestrationService service = new();

        ArtifactFactoryJobLaunchResult result = service.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "publication",
            RequestedBy: "creator.ops",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "publication-shelf-redmond-brief",
                    SourcePackKind: "publication",
                    ApprovalState: "approved",
                    ProvenanceRef: "publication:redmond-brief:v3",
                    EvidenceRefs:
                    [
                        "publication:redmond-brief:v3",
                        "moderation:approved:redmond-brief",
                        "public-shelf:/artifacts/publications/redmond-brief"
                    ],
                    PublicShelfRef: "/artifacts/publications/redmond-brief")
            ],
            RequestedFormats: ["caption"]));

        Assert.Contains("/artifacts/publications/redmond-brief", result.PublicProofShelfRefs);
        Assert.Contains(result.OutputBindings, binding =>
            string.Equals(binding.PublicRef, "/artifacts/publications/redmond-brief/bundles/caption", StringComparison.Ordinal)
            && string.Equals(binding.ReceiptRef, $"artifact-factory:{result.JobId}:caption", StringComparison.Ordinal));
        Assert.Contains(result.MediaFactoryRequest.ApprovedSourcePacks, pack =>
            string.Equals(pack.PublicShelfRef, "/artifacts/publications/redmond-brief", StringComparison.Ordinal));
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

        Assert.Contains("provider-specific outputFormat", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("provider_render_script", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("one-off provider flows", ex.Message, StringComparison.OrdinalIgnoreCase);
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
    public void LaunchJobRejectsProviderSpecificSlashEvidenceRefs()
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
                        "heygen/render/redmond-brief",
                        "public-shelf:/artifacts/publications/redmond-brief"
                    ],
                    PublicationId: "redmond-brief")
            ])));

        Assert.Contains("provider-specific evidenceRef", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("one-off provider flows", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobRejectsProviderSpecificTokenizedSourcePackIds()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "release",
            RequestedBy: "fleet.release",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "release-heygen-render-pack",
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
            ])));

        Assert.Contains("provider-specific sourcePackId", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("one-off provider flows", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobRejectsProviderSpecificRequestedByTokens()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "publication",
            RequestedBy: "heygen.ops",
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
            ])));

        Assert.Contains("provider-specific requestedBy", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("approved source-pack receipts", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobRejectsExternalPublicShelfRefs()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "release",
            RequestedBy: "fleet.release",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "release-pack-20260415",
                    SourcePackKind: "release_evidence",
                    ApprovalState: "approved",
                    ProvenanceRef: "release-channel:preview:run-20260415",
                    EvidenceRefs:
                    [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-macos-arm64",
                        "public-shelf:https://vendor.example/rendered/preview"
                    ],
                    PublicShelfRef: "https://vendor.example/rendered/preview")
            ])));

        Assert.Contains("non-local public proof shelf", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Chummer public proof shelf", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobRejectsExternalPublicShelfEvidenceRefs()
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
                        "public-shelf:https://vendor.example/rendered/publication"
                    ],
                    PublicationId: "redmond-brief")
            ])));

        Assert.Contains("non-local public proof shelf", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("evidenceRef", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobRejectsProviderSpecificPublicShelfEvidenceRefs()
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
                        "public-shelf:/artifacts/publications/heygen"
                    ],
                    PublicationId: "redmond-brief")
            ])));

        Assert.Contains("provider-specific evidenceRef", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("approved source-pack receipts", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobRejectsCrossRecipePublicShelfRefs()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "release",
            RequestedBy: "fleet.release",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "release-pack-20260415",
                    SourcePackKind: "release_evidence",
                    ApprovalState: "approved",
                    ProvenanceRef: "release-channel:preview:run-20260415",
                    EvidenceRefs:
                    [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/account/support/11709"
                    ],
                    PublicShelfRef: "/account/support/11709")
            ])));

        Assert.Contains("outside recipe release shelf routes", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("approved release, support, fix, or publication shelves", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobRejectsCrossRecipePublicShelfEvidenceRefs()
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
                        "public-shelf:/artifacts/release-bundles/current-preview-build"
                    ],
                    PublicationId: "redmond-brief")
            ])));

        Assert.Contains("outside recipe publication shelf routes", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("evidenceRef", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobRejectsUnsafePublicShelfRefs()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchJob(new ArtifactFactoryJobLaunchRequest(
            Family: "release",
            RequestedBy: "fleet.release",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "release-pack-20260415",
                    SourcePackKind: "release_evidence",
                    ApprovalState: "approved",
                    ProvenanceRef: "release-channel:preview:run-20260415",
                    EvidenceRefs:
                    [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/artifacts/release-bundles/../support-packets/11709"
                    ],
                    PublicShelfRef: "/artifacts/release-bundles/../support-packets/11709")
            ])));

        Assert.Contains("unsafe public proof shelf", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("traversal", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobRejectsUnsafePublicShelfEvidenceRefs()
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
                        "public-shelf:/artifacts/publications/redmond-brief?provider=one-off"
                    ],
                    PublicationId: "redmond-brief")
            ])));

        Assert.Contains("unsafe public proof shelf", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("query strings or fragments", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("evidenceRef", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobRejectsUnsafeReleaseArtifactPathIds()
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
                        "public-shelf:/downloads/install/avalonia-osx-arm64-installer"
                    ],
                    ReleaseArtifactId: "../avalonia-osx-arm64-installer")
            ])));

        Assert.Contains("unsafe releaseArtifactId", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("stable public proof shelf segments", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobRejectsEncodedSeparatorInPublicationPathIds()
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
                    PublicationId: "redmond%2Fbrief")
            ])));

        Assert.Contains("unsafe publicationId", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("encoded path separators", ex.Message, StringComparison.OrdinalIgnoreCase);
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
        Assert.Contains("/account/fix-followthrough/11709", fix.PublicProofShelfRefs);
        Assert.Contains(fix.MediaFactoryRequest.ApprovedSourcePacks, pack => string.Equals(pack.SupportCaseId, "11709", StringComparison.Ordinal));
        Assert.Contains("/account/support/11709", fix.MediaFactoryRequest.PublicProofShelfRefs);
        Assert.Contains("/account/fix-followthrough/11709", fix.MediaFactoryRequest.PublicProofShelfRefs);
        Assert.Contains(support.OutputBindings, binding =>
            string.Equals(binding.PublicRef, "/account/support-packets/11709/packet", StringComparison.Ordinal)
            && string.Equals(binding.ReceiptRef, $"artifact-factory:{support.JobId}:packet", StringComparison.Ordinal));
        Assert.Contains(fix.OutputBindings, binding =>
            string.Equals(binding.PublicRef, "/account/fix-followthrough/11709/packet", StringComparison.Ordinal)
            && string.Equals(binding.ReceiptRef, $"artifact-factory:{fix.JobId}:packet", StringComparison.Ordinal));
    }

    [Fact]
    public void LaunchJobBatchDefaultsToCompleteSuccessorRecipeSet()
    {
        ArtifactFactoryOrchestrationService service = new();

        ArtifactFactoryJobBatchLaunchResult result = service.LaunchJobs(new ArtifactFactoryJobBatchLaunchRequest(
            BatchId: "next90-m107-artifact-factory-wave",
            RequestedBy: "fleet.release",
            Jobs:
            [
                new ArtifactFactoryJobLaunchRequest(
                    Family: "release",
                    RequestedBy: "",
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
                                "promotion:startup-smoke:avalonia-linux-x64",
                                "public-shelf:/downloads/install/avalonia-linux-x64-installer"
                            ],
                            ReleaseArtifactId: "avalonia-linux-x64-installer")
                    ],
                    RequestedFormats: ["packet"]),
                new ArtifactFactoryJobLaunchRequest(
                    Family: "fix",
                    RequestedBy: "fleet.release",
                    SourcePacks:
                    [
                        new ApprovedArtifactSourcePack(
                            SourcePackId: "fix-pack-11709",
                            SourcePackKind: "fix_receipt",
                            ApprovalState: "approved",
                            ProvenanceRef: "fix:11709",
                            EvidenceRefs: ["fix:11709", "install:preview", "support:11709"],
                            SupportCaseId: "11709")
                    ],
                    RequestedFormats: ["packet"]),
                new ArtifactFactoryJobLaunchRequest(
                    Family: "support",
                    RequestedBy: "fleet.release",
                    SourcePacks:
                    [
                        new ApprovedArtifactSourcePack(
                            SourcePackId: "support-pack-11709",
                            SourcePackKind: "support_case",
                            ApprovalState: "approved",
                            ProvenanceRef: "support-case:11709",
                            EvidenceRefs: ["support:11709", "privacy:redacted", "install:preview"],
                            SupportCaseId: "11709")
                    ],
                    RequestedFormats: ["packet"]),
                new ArtifactFactoryJobLaunchRequest(
                    Family: "publication",
                    RequestedBy: "fleet.release",
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
                    RequestedFormats: ["packet"])
            ]));

        Assert.Equal("queued", result.State);
        Assert.Equal(4, result.JobCount);
        Assert.Equal(["fix", "publication", "release", "support"], result.RequiredFamilies);
        Assert.Equal(["fix", "publication", "release", "support"], result.Families);
        Assert.Equal(
            ["fix-followthrough-bundle", "publication-proof-shelf-bundle", "release-proof-shelf-bundle", "support-case-proof-packet"],
            result.RecipeIds);
        Assert.Contains("/artifacts/release-bundles/avalonia-linux-x64-installer", result.PublicProofShelfRefs);
        Assert.Contains("/account/fix-followthrough/11709", result.PublicProofShelfRefs);
        Assert.Contains("/account/support-packets/11709", result.PublicProofShelfRefs);
        Assert.Contains("/artifacts/publications/redmond-brief/bundles", result.PublicProofShelfRefs);
        Assert.All(result.MediaFactoryRequests, request =>
            Assert.Equal("chummer.run.artifact_factory.recipe_job.v1", request.ContractName));
    }

    [Fact]
    public void LaunchJobBatchRejectsPartialWaveWhenRequiredFamiliesAreOmitted()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchJobs(new ArtifactFactoryJobBatchLaunchRequest(
            BatchId: "next90-m107-artifact-factory-partial",
            RequestedBy: "fleet.release",
            Jobs:
            [
                new ArtifactFactoryJobLaunchRequest(
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
                                "promotion:startup-smoke:avalonia-linux-x64",
                                "public-shelf:/downloads/install/avalonia-linux-x64-installer"
                            ],
                            ReleaseArtifactId: "avalonia-linux-x64-installer")
                    ])
            ])));

        Assert.Contains("missing required recipe family job(s)", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("fix", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("publication", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("support", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchJobBatchRejectsExplicitBlankRequiredFamilies()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchJobs(new ArtifactFactoryJobBatchLaunchRequest(
            BatchId: "next90-m107-artifact-factory-blank-families",
            RequestedBy: "fleet.release",
            Jobs:
            [
                new ArtifactFactoryJobLaunchRequest(
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
                                "promotion:startup-smoke:avalonia-linux-x64",
                                "public-shelf:/downloads/install/avalonia-linux-x64-installer"
                            ],
                            ReleaseArtifactId: "avalonia-linux-x64-installer")
                    ])
            ],
            RequiredFamilies: [" ", ""])));

        Assert.Contains("required recipe families cannot be empty", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchSourcePackBatchRejectsMissingBatchIdBeforeSourcePackSelection()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchSourcePackBatch(new ArtifactFactorySourcePackBatchLaunchRequest(
            BatchId: "",
            RequestedBy: "fleet.release",
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
            RequiredFamilies: ["release"])));

        Assert.Contains("source-pack batchId is required", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchSourcePackBatchBuildsRequiredRecipeJobsFromApprovedSourcePacks()
    {
        ArtifactFactoryOrchestrationService service = new();

        ArtifactFactoryJobBatchLaunchResult result = service.LaunchSourcePackBatch(new ArtifactFactorySourcePackBatchLaunchRequest(
            BatchId: "next90-m107-source-pack-wave",
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
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer"
                    ],
                    ReleaseArtifactId: "avalonia-linux-x64-installer"),
                new ApprovedArtifactSourcePack(
                    SourcePackId: "fix-pack-11709",
                    SourcePackKind: "fix_receipt",
                    ApprovalState: "approved",
                    ProvenanceRef: "fix:11709",
                    EvidenceRefs: ["fix:11709", "install:preview", "support:11709"],
                    SupportCaseId: "11709"),
                new ApprovedArtifactSourcePack(
                    SourcePackId: "support-pack-11709",
                    SourcePackKind: "support_case",
                    ApprovalState: "approved",
                    ProvenanceRef: "support-case:11709",
                    EvidenceRefs: ["support:11709", "privacy:redacted", "install:preview"],
                    SupportCaseId: "11709"),
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
            RequestedFormats:
            [
                new ArtifactFactoryFamilyFormatOverride("release", ["packet"]),
                new ArtifactFactoryFamilyFormatOverride("publication", ["caption"])
            ],
            RequiredFamilies: ["release", "fix", "support", "publication"]));

        Assert.Equal("queued", result.State);
        Assert.Equal("next90-m107-source-pack-wave", result.BatchId);
        Assert.Equal(4, result.JobCount);
        Assert.Equal(["fix", "publication", "release", "support"], result.Families);
        Assert.Equal(["fix", "publication", "release", "support"], result.RequiredFamilies);
        Assert.Contains(result.Jobs, job =>
            string.Equals(job.Family, "release", StringComparison.Ordinal)
            && job.OutputFormats.SequenceEqual(["packet"])
            && job.PublicProofShelfRefs.Contains("/artifacts/release-bundles/avalonia-linux-x64-installer"));
        Assert.Contains(result.Jobs, job =>
            string.Equals(job.Family, "publication", StringComparison.Ordinal)
            && job.OutputFormats.SequenceEqual(["caption"])
            && job.PublicProofShelfRefs.Contains("/artifacts/publications/redmond-brief/bundles"));
        Assert.Contains(result.Jobs, job =>
            string.Equals(job.Family, "fix", StringComparison.Ordinal)
            && job.PublicProofShelfRefs.Contains("/account/fix-followthrough/11709"));
        Assert.Contains(result.Jobs, job =>
            string.Equals(job.Family, "support", StringComparison.Ordinal)
            && job.PublicProofShelfRefs.Contains("/account/support-packets/11709"));
        Assert.All(result.MediaFactoryRequests, request =>
            Assert.Equal("chummer.run.artifact_factory.recipe_job.v1", request.ContractName));
    }

    [Fact]
    public void LaunchSourcePackBatchInfersLaunchableFamiliesWhenRequiredFamiliesAreOmitted()
    {
        ArtifactFactoryOrchestrationService service = new();

        ArtifactFactoryJobBatchLaunchResult result = service.LaunchSourcePackBatch(new ArtifactFactorySourcePackBatchLaunchRequest(
            BatchId: "next90-m107-source-pack-inferred",
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
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer"
                    ],
                    ReleaseArtifactId: "avalonia-linux-x64-installer"),
                new ApprovedArtifactSourcePack(
                    SourcePackId: "support-pack-11709",
                    SourcePackKind: "support_case",
                    ApprovalState: "approved",
                    ProvenanceRef: "support-case:11709",
                    EvidenceRefs: ["support:11709", "privacy:redacted", "install:preview"],
                    SupportCaseId: "11709")
            ]));

        Assert.Equal(["release", "support"], result.RequiredFamilies);
        Assert.Equal(["release", "support"], result.Families);
        Assert.DoesNotContain("publication", result.RequiredFamilies);
        Assert.DoesNotContain("fix", result.RequiredFamilies);
        Assert.Contains(result.Jobs, job => string.Equals(job.Family, "release", StringComparison.Ordinal));
        Assert.Contains(result.Jobs, job => string.Equals(job.Family, "support", StringComparison.Ordinal));
        Assert.DoesNotContain(result.Jobs, job => string.Equals(job.Family, "fix", StringComparison.Ordinal));
    }

    [Fact]
    public void LaunchSourcePackBatchRejectsFormatOverridesOutsideRequiredFamilies()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchSourcePackBatch(new ArtifactFactorySourcePackBatchLaunchRequest(
            BatchId: "next90-m107-source-pack-format-drift",
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
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer"
                    ],
                    ReleaseArtifactId: "avalonia-linux-x64-installer"),
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
            RequestedFormats:
            [
                new ArtifactFactoryFamilyFormatOverride("release", ["packet"]),
                new ArtifactFactoryFamilyFormatOverride("publication", ["caption"])
            ],
            RequiredFamilies: ["release"])));

        Assert.Contains("requested formats for family/families not required", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("publication", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchSourcePackBatchRejectsEmptyRequestedFormatOverride()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchSourcePackBatch(new ArtifactFactorySourcePackBatchLaunchRequest(
            BatchId: "next90-m107-source-pack-empty-format-override",
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
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer"
                    ],
                    ReleaseArtifactId: "avalonia-linux-x64-installer")
            ],
            RequestedFormats:
            [
                new ArtifactFactoryFamilyFormatOverride("release", [])
            ],
            RequiredFamilies: ["release"])));

        Assert.Contains("requested formats for recipe family 'release' must include at least one format", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchSourcePackBatchRejectsNullRequestedFormatOverrideList()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchSourcePackBatch(new ArtifactFactorySourcePackBatchLaunchRequest(
            BatchId: "next90-m107-source-pack-null-format-override",
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
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer"
                    ],
                    ReleaseArtifactId: "avalonia-linux-x64-installer")
            ],
            RequestedFormats:
            [
                new ArtifactFactoryFamilyFormatOverride("release", null!)
            ],
            RequiredFamilies: ["release"])));

        Assert.Contains("requested formats for recipe family 'release' must include at least one format", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchSourcePackBatchRejectsDuplicatePackIdsBeforeFamilySelection()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchSourcePackBatch(new ArtifactFactorySourcePackBatchLaunchRequest(
            BatchId: "next90-m107-source-pack-duplicate",
            RequestedBy: "fleet.release",
            SourcePacks:
            [
                new ApprovedArtifactSourcePack(
                    SourcePackId: "shared-pack-20260415",
                    SourcePackKind: "desktop_release",
                    ApprovalState: "approved",
                    ProvenanceRef: "release-channel:preview:run-20260415",
                    EvidenceRefs:
                    [
                        "release:run-20260415",
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer"
                    ],
                    ReleaseArtifactId: "avalonia-linux-x64-installer"),
                new ApprovedArtifactSourcePack(
                    SourcePackId: " shared-pack-20260415 ",
                    SourcePackKind: "support_case",
                    ApprovalState: "approved",
                    ProvenanceRef: "support-case:11709",
                    EvidenceRefs: ["support:11709", "privacy:redacted", "install:preview"],
                    SupportCaseId: "11709")
            ],
            RequiredFamilies: ["release", "support"])));

        Assert.Contains("duplicate source pack id", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("source-pack batch", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("shared-pack-20260415", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void LaunchSourcePackBatchRejectsProviderRefsBeforeFamilySelection()
    {
        ArtifactFactoryOrchestrationService service = new();

        InvalidDataException ex = Assert.Throws<InvalidDataException>(() => service.LaunchSourcePackBatch(new ArtifactFactorySourcePackBatchLaunchRequest(
            BatchId: "next90-m107-source-pack-provider-ref",
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
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer"
                    ],
                    ReleaseArtifactId: "avalonia-linux-x64-installer"),
                new ApprovedArtifactSourcePack(
                    SourcePackId: "publication-pack-redmond-brief",
                    SourcePackKind: "creator_publication",
                    ApprovalState: "approved",
                    ProvenanceRef: "publication:redmond-brief:v3",
                    EvidenceRefs:
                    [
                        "publication:redmond-brief:v3",
                        "moderation:approved:redmond-brief",
                        "provider:one-off-render:heygen",
                        "public-shelf:/artifacts/publications/redmond-brief"
                    ],
                    PublicationId: "redmond-brief")
            ],
            RequiredFamilies: ["release"])));

        Assert.Contains("provider-specific evidenceRef", ex.Message, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("one-off provider flows", ex.Message, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void ControllerLaunchSourcePackBatchReturnsRecipeJobs()
    {
        InternalArtifactFactoryController controller = BuildController(token: "expected-token");
        controller.ControllerContext.HttpContext.Request.Headers.Authorization = "Bearer expected-token";

        ActionResult<ArtifactFactoryJobBatchLaunchResult> response = controller.LaunchSourcePackBatch(new ArtifactFactorySourcePackBatchLaunchRequest(
            BatchId: "next90-m107-source-pack-controller",
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
                        "promotion:startup-smoke:avalonia-linux-x64",
                        "public-shelf:/downloads/install/avalonia-linux-x64-installer"
                    ],
                    ReleaseArtifactId: "avalonia-linux-x64-installer")
            ],
            RequiredFamilies: ["release"]));

        OkObjectResult ok = Assert.IsType<OkObjectResult>(response.Result);
        ArtifactFactoryJobBatchLaunchResult result = Assert.IsType<ArtifactFactoryJobBatchLaunchResult>(ok.Value);
        Assert.Equal("next90-m107-source-pack-controller", result.BatchId);
        Assert.Equal(["release"], result.RequiredFamilies);
        Assert.Equal(["release-proof-shelf-bundle"], result.RecipeIds);
        Assert.Contains("/artifacts/release-bundles/avalonia-linux-x64-installer", result.PublicProofShelfRefs);
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
