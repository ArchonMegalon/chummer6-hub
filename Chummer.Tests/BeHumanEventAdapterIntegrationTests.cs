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
    public void ParticipatePageModelCarriesBeHumanEventAdapterPanel()
    {
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");
        string viewModels = File.ReadAllText(viewModelPath);

        Assert.Contains("BeHumanEventAdapterPanelViewModel? BeHumanEventAdapter = null", viewModels, StringComparison.Ordinal);
        Assert.Contains("public sealed record BeHumanEventAdapterPanelViewModel(", viewModels, StringComparison.Ordinal);
        Assert.Contains("IReadOnlyList<string> AllowedEventFamilies", viewModels, StringComparison.Ordinal);
        Assert.Contains("IReadOnlyList<string> ForbiddenTruthDomains", viewModels, StringComparison.Ordinal);
    }

    [Fact]
    public void ParticipatePageShowsFailClosedBeHumanBoundaryInsteadOfTreatingProviderAsTruth()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml");

        string controller = File.ReadAllText(controllerPath);
        string view = File.ReadAllText(viewPath);

        Assert.Contains("BeHumanEventAdapterPostureService", controller, StringComparison.Ordinal);
        Assert.Contains("BuildBeHumanEventAdapterPanel()", controller, StringComparison.Ordinal);
        Assert.Contains("BeHumanEventAdapter: BuildBeHumanEventAdapterPanel()", controller, StringComparison.Ordinal);
        Assert.Contains("BeHuman can help host public community events, but it does not decide the product.", view, StringComparison.Ordinal);
        Assert.Contains("Capacity stays unclaimed until Chummer confirms it.", view, StringComparison.Ordinal);
        Assert.Contains("Chummer keeps the authority", view, StringComparison.Ordinal);
    }
}
