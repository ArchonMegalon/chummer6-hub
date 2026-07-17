using Chummer.Run.Api.Services.Community;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace Chummer.Tests;

public sealed class HorizonCapabilityServiceTests
{
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
