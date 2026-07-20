using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class HorizonCapabilityServiceTests
{
    [Fact]
    public void PublicRequestSupportFailsClosedUntilOperationalReadinessIsVerified()
    {
        HorizonCapabilityService capabilities = new(new ConfigurationBuilder().Build());

        PublicHorizonCapabilityViewModel publicCapability = capabilities.BuildPublicCapabilityViewModel(
            "runbook-press",
            "runbook-export",
            "runbook-press:new-runner-primer");
        SharedArtifactSurfaceRoutesViewModel routes = capabilities.BuildSharedArtifactSurfaceRoutesViewModel(
            "runbook-press",
            "runbook-export");

        Assert.Equal("configured", publicCapability.Status);
        Assert.True(publicCapability.ConfigurationEnabled);
        Assert.Equal("unverified", publicCapability.OperationalReadiness);
        Assert.False(publicCapability.RequestSupported);
        Assert.Equal("runbook-press:new-runner-primer", publicCapability.SourceRef);
        Assert.Equal("/api/v1/horizons/artifact-requests/me", routes.SignedInRequestCreateHref);
    }

    [Theory]
    [InlineData("runbook-press", "runbook-export", "Markdown")]
    [InlineData("karma-forge", "karma-forge-discovery", "discovery packet")]
    public void FirstPartyTerminalCapabilitiesAreEnabledAndQuotaBoundByDefault(
        string horizonId,
        string capabilityId,
        string expectedLaneFragment)
    {
        HorizonCapabilityService capabilities = new(new ConfigurationBuilder().Build());

        HorizonCapabilityHealthSnapshot health = capabilities.GetHealth(
            horizonId,
            capabilityId,
            publicSafe: false);

        Assert.Equal("configured", health.Status);
        Assert.True(health.ConfigurationEnabled);
        Assert.Equal("unverified", health.OperationalReadiness);
        Assert.True(health.PublicVisible);
        Assert.True(health.RequiresAuthentication);
        Assert.True(health.QuotaTracked);
        Assert.True(health.FreeWeeklyLimit > 0);
        Assert.Contains("first-party", health.InternalProviderLane, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(expectedLaneFragment, health.InternalProviderLane, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RunsiteSceneRenderCapabilityIsInternalEaSkillBacked()
    {
        HorizonCapabilityService capabilities = new(new ConfigurationBuilder().Build());

        HorizonCapabilityHealthSnapshot internalHealth = capabilities.GetHealth("runsite", "scene_render", publicSafe: false);
        HorizonCapabilityHealthSnapshot publicSafeHealth = capabilities.GetHealth("runsite", "scene_render", publicSafe: true);

        Assert.Equal("runsite-scene-render", internalHealth.CapabilityId);
        Assert.Equal("scene_render", internalHealth.ArtifactKind);
        Assert.Equal("ea_scene_render", internalHealth.CapabilitySlot);
        Assert.Equal("disabled", internalHealth.Status);
        Assert.False(internalHealth.ConfigurationEnabled);
        Assert.Equal("unverified", internalHealth.OperationalReadiness);
        Assert.True(internalHealth.RequiresAuthentication);
        Assert.False(internalHealth.PublicVisible);
        Assert.Contains("EA scene render skill", internalHealth.InternalProviderLane, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("MagicAI", internalHealth.InternalProviderLane, StringComparison.OrdinalIgnoreCase);
        Assert.Null(publicSafeHealth.InternalProviderLane);
    }

    [Fact]
    public void PropertyquarryApartmentVideoCapabilityIsInternalEaSkillBacked()
    {
        HorizonCapabilityService capabilities = new(new ConfigurationBuilder().Build());

        HorizonCapabilityHealthSnapshot internalHealth = capabilities.GetHealth("propertyquarry", "apartment_video", publicSafe: false);
        HorizonCapabilityHealthSnapshot publicSafeHealth = capabilities.GetHealth("propertyquarry", "apartment_video", publicSafe: true);

        Assert.Equal("propertyquarry-apartment-video", internalHealth.CapabilityId);
        Assert.Equal("apartment_video", internalHealth.ArtifactKind);
        Assert.Equal("property_video_render", internalHealth.CapabilitySlot);
        Assert.Equal("disabled", internalHealth.Status);
        Assert.False(internalHealth.ConfigurationEnabled);
        Assert.Equal("unverified", internalHealth.OperationalReadiness);
        Assert.True(internalHealth.RequiresAuthentication);
        Assert.False(internalHealth.PublicVisible);
        Assert.Contains("EA property video skill", internalHealth.InternalProviderLane, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("MagicAI", internalHealth.InternalProviderLane, StringComparison.OrdinalIgnoreCase);
        Assert.Null(publicSafeHealth.InternalProviderLane);
    }

    [Fact]
    public void SharedEaGovernedRenderLaneCoversRunsitePropertyquarryAndOriginMedia()
    {
        HorizonCapabilityService capabilities = new(new ConfigurationBuilder().Build());

        HorizonCapabilityDefinition runsite = capabilities.GetCapability("runsite", "scene_render");
        HorizonCapabilityDefinition propertyquarry = capabilities.GetCapability("propertyquarry", "apartment_video");
        HorizonCapabilityDefinition origin = capabilities.GetCapability("origin-dossier", "dossier_media");

        Assert.Equal(HorizonGovernedRenderRequestComposerService.OrchestrationLane, runsite.OrchestrationLane);
        Assert.Equal(HorizonGovernedRenderRequestComposerService.OrchestrationLane, propertyquarry.OrchestrationLane);
        Assert.Equal(HorizonGovernedRenderRequestComposerService.OrchestrationLane, origin.OrchestrationLane);
        Assert.Contains("Magicfit", origin.InternalProviderLane, StringComparison.OrdinalIgnoreCase);
    }
}
