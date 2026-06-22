using Xunit;

namespace Chummer.Tests;

public sealed class BeHumanEventAdapterIntegrationTests
{
    [Fact]
    public void ServiceCollectionRegistersBeHumanPostureServiceForPublicGuideContext()
    {
        string serviceCollectionPath = RepoPaths.FromRoot("Chummer.Run.Api", "ServiceCollectionBoundedContextExtensions.cs");
        string serviceCollection = File.ReadAllText(serviceCollectionPath);

        Assert.Contains("services.AddSingleton<BeHumanEventAdapterPostureService>();", serviceCollection, StringComparison.Ordinal);
    }

    [Fact]
    public void BeHumanEventAdapterPanelModelIsNotPartOfTheDeletedPublicParticipatePage()
    {
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");
        string viewModels = File.ReadAllText(viewModelPath);

        Assert.Contains("public sealed record BeHumanEventAdapterPanelViewModel(", viewModels, StringComparison.Ordinal);
        Assert.Contains("IReadOnlyList<string> AllowedEventFamilies", viewModels, StringComparison.Ordinal);
        Assert.Contains("IReadOnlyList<string> ForbiddenTruthDomains", viewModels, StringComparison.Ordinal);
        Assert.DoesNotContain("BeHumanEventAdapterPanelViewModel? BeHumanEventAdapter = null", viewModels, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicParticipateViewNoLongerCarriesProviderBoundaryCopy()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml");

        string controller = File.ReadAllText(controllerPath);
        string view = File.ReadAllText(viewPath);

        Assert.Contains("BeHumanEventAdapterPostureService", controller, StringComparison.Ordinal);
        Assert.True(File.Exists(viewPath));
        Assert.DoesNotContain("BeHuman", view, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("provider boundary", view, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("BuildParticipatePageModel(", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("BeHumanEventAdapter: BuildBeHumanEventAdapterPanel()", controller, StringComparison.Ordinal);
    }
}
