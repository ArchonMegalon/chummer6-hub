using Chummer.Run.Api.Services.Community;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class HorizonGovernedRenderRequestComposerServiceTests
{
    [Fact]
    public void ComposeAcceptsOriginMediaWithMagicfitPreferredProvider()
    {
        HorizonCapabilityService capabilities = new(new ConfigurationBuilder().Build());
        HorizonCapabilityDefinition capability = capabilities.GetCapability("origin-dossier", "dossier_media");
        HorizonGovernedRenderRequestComposerService service = new();

        HorizonGovernedRenderRequestCompositionResult result = service.Compose(
            capability,
            "origin-dossier:project-varga:cover",
            new HorizonGovernedRenderRequestCreateRequest(
                WorkItemId: "origin-varga-cover",
                RequestedBy: "ea.ops",
                Subject: "Mira Varga dossier cover",
                Audience: "account-owner",
                Locale: "en-US",
                PreferredProvider: "MagicFit",
                TruthRefs:
                [
                    "/artifacts/origin-dossier/project-varga/canon-summary",
                    "origin:project-varga:cover-brief"
                ],
                EvidenceRefs:
                [
                    "review:approved",
                    "provider-pool:magicfit"
                ],
                Artifacts:
                [
                    new HorizonGovernedRenderArtifactSpec(
                        ArtifactId: "cover-main",
                        Role: "cover",
                        Category: "origin-dossier/cover",
                        Payload: "{\"prompt_ref\":\"origin:project-varga:cover-brief\"}",
                        OutputFormat: "png",
                        DeduplicationKey: "origin-varga-cover-main",
                        AspectRatio: "2:3",
                        MaxBytes: 4 * 1024 * 1024,
                        RequiresApproval: true,
                        PersistOnApproval: true)
                ]));

        Assert.True(result.Accepted);
        HorizonGovernedRenderRequestContract contract = Assert.IsType<HorizonGovernedRenderRequestContract>(result.Contract);
        Assert.Equal(HorizonGovernedRenderRequestComposerService.OrchestrationLane, contract.OrchestrationLane);
        Assert.Equal("MagicFit", contract.PreferredProvider);
        Assert.Equal("origin-dossier:project-varga:cover", contract.SourceRef);
        Assert.Contains("origin-dossier:project-varga:cover", contract.TruthRefs);
    }

    [Fact]
    public void ComposeRejectsExternalEvidenceRefs()
    {
        HorizonCapabilityService capabilities = new(new ConfigurationBuilder().Build());
        HorizonCapabilityDefinition capability = capabilities.GetCapability("runsite", "scene_render");
        HorizonGovernedRenderRequestComposerService service = new();

        HorizonGovernedRenderRequestCompositionResult result = service.Compose(
            capability,
            "runsite:redmond-dockyard-pack:segment-a",
            BuildRenderRequest(evidenceRefs: ["https://example.com/provider-owned-proof"]));

        Assert.False(result.Accepted);
        Assert.Contains("governed render evidence refs", result.BlockedReasons);
        Assert.Null(result.Contract);
    }

    [Fact]
    public void BuildRequestStoresGovernedRenderContractForRunsiteSceneRender()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_HORIZON_RUNSITE_CAPABILITY_RUNSITE_SCENE_RENDER_ENABLED"] = "true"
            })
            .Build();
        HorizonCapabilityService capabilities = new(configuration);
        HorizonArtifactRequestService requests = new(capabilities);

        HorizonArtifactRequestReceipt receipt = requests.BuildRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "runsite",
                ArtifactKindOrCapabilityId: "scene_render",
                UserId: "subject.render",
                SourceRef: "runsite:redmond-dockyard-pack:segment-a",
                Visibility: "private",
                ExternalProcessingConsent: true,
                GovernedRenderRequest: BuildRenderRequest()),
            new DateTimeOffset(2026, 6, 30, 10, 0, 0, TimeSpan.Zero));

        Assert.Equal("accepted", receipt.Status);
        HorizonGovernedRenderRequestContract contract = Assert.IsType<HorizonGovernedRenderRequestContract>(receipt.GovernedRenderRequest);
        Assert.Equal("runsite", contract.HorizonId);
        Assert.Equal("runsite-scene-render", contract.CapabilityId);
        Assert.Equal("scene_render", contract.ArtifactKind);
        Assert.Equal("ea_scene_render", contract.CapabilitySlot);
        Assert.Equal("runsite:redmond-dockyard-pack:segment-a", contract.SourceRef);
        Assert.Equal(["route:segment-a", "runsite:redmond-dockyard-pack:segment-a"], contract.TruthRefs);
    }

    [Fact]
    public void BuildRequestBlocksGovernedRenderContractOnNonRenderCapability()
    {
        IConfiguration configuration = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["CHUMMER_HORIZON_RUNSITE_CAPABILITY_RUNSITE_TOUR_ENABLED"] = "true"
            })
            .Build();
        HorizonCapabilityService capabilities = new(configuration);
        HorizonArtifactRequestService requests = new(capabilities);

        HorizonArtifactRequestReceipt receipt = requests.BuildRequest(
            new HorizonArtifactRequestCreateRequest(
                HorizonId: "runsite",
                ArtifactKindOrCapabilityId: "tour",
                UserId: "subject.render",
                SourceRef: "runsite:redmond-dockyard-pack",
                Visibility: "private",
                ExternalProcessingConsent: true,
                GovernedRenderRequest: BuildRenderRequest()),
            new DateTimeOffset(2026, 6, 30, 10, 5, 0, TimeSpan.Zero));

        Assert.Equal("blocked", receipt.Status);
        Assert.Contains("governed render lane", receipt.BlockedReasons);
        Assert.Null(receipt.GovernedRenderRequest);
    }

    private static HorizonGovernedRenderRequestCreateRequest BuildRenderRequest(
        IReadOnlyList<string>? evidenceRefs = null)
        => new(
            WorkItemId: "runsite-redmond-scene-a",
            RequestedBy: "ea.ops",
            Subject: "Redmond dockyard orientation segment A",
            Audience: "players",
            Locale: "en-US",
            PreferredProvider: "MagicAI",
            TruthRefs:
            [
                "route:segment-a"
            ],
            EvidenceRefs: evidenceRefs ??
            [
                "preview-safe:approved",
                "route-summary:redmond-dockyard-pack"
            ],
            Artifacts:
            [
                new HorizonGovernedRenderArtifactSpec(
                    ArtifactId: "segment-a-preview",
                    Role: "route_preview",
                    Category: "runsite/orientation/route-preview",
                    Payload: "{\"prompt_ref\":\"route:segment-a\"}",
                    OutputFormat: "png",
                    DeduplicationKey: "runsite-redmond-segment-a-preview",
                    AspectRatio: "16:9",
                    MaxBytes: 4 * 1024 * 1024),
                new HorizonGovernedRenderArtifactSpec(
                    ArtifactId: "segment-a-host",
                    Role: "host_clip",
                    Category: "runsite/orientation/host-clip",
                    Payload: "{\"script_ref\":\"route:segment-a\"}",
                    OutputFormat: "mp4",
                    DeduplicationKey: "runsite-redmond-segment-a-host",
                    DurationProfile: "short",
                    MaxBytes: 64 * 1024 * 1024,
                    RequiresApproval: true,
                    PersistOnApproval: true)
            ]);
}
