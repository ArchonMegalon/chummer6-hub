using Xunit;

namespace Chummer.Tests;

public sealed class GmSessionVenueIntegrationTests
{
    [Fact]
    public void GmSessionVenueRoutesArePresentAndFailClosed()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "GmSessionVenueController.cs");
        string landingControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string servicePath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "Community", "GmSessionVenueService.cs");
        string adapterPath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "Community", "IGmSessionVenueAdapter.cs");
        string venueViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "GmSessionVenue.cshtml");

        string controller = File.ReadAllText(controllerPath);
        string landingController = File.ReadAllText(landingControllerPath);
        string service = File.ReadAllText(servicePath);
        string adapter = File.ReadAllText(adapterPath);
        string venueView = File.ReadAllText(venueViewPath);

        Assert.Contains(@"[Route(""api/v1/account/campaigns/{campaignId}/sessions/{sessionId}/venue"")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"manual-link\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"behuman\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"closeout\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/community/runs/{runId}/venue\")]", landingController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/campaigns/{campaignId}/sessions/{sessionId}/venue\")]", landingController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/campaigns/{campaignId}/sessions/{sessionId}/venue/manage\")]", landingController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/campaigns/{campaignId}/sessions/{sessionId}/venue/closeout\")]", landingController, StringComparison.Ordinal);
        Assert.Contains("return View(\"~/Views/PublicLanding/GmSessionVenue.cshtml\", model);", landingController, StringComparison.Ordinal);
        Assert.Contains("Live room integration unavailable. Paste your external room link manually or use another provider.", landingController, StringComparison.Ordinal);
        Assert.Contains("Create BeHuman venue is unavailable until a verified adapter transport base URL exists.", adapter, StringComparison.Ordinal);
        Assert.Contains("venue_url host is not an allowed BeHuman domain.", adapter, StringComparison.Ordinal);
        Assert.Contains("venue_url may not include suspicious query payloads.", adapter, StringComparison.Ordinal);
        Assert.Contains("adapter_create_mode", service, StringComparison.Ordinal);
        Assert.Contains("Current account must be an owner, organizer, admin, manager, or gm to manage this venue.", service, StringComparison.Ordinal);
        Assert.Contains("Copy invite link", venueView, StringComparison.Ordinal);
        Assert.Contains("Join live room", venueView, StringComparison.Ordinal);
        Assert.Contains("Attendance sync", venueView, StringComparison.Ordinal);
        Assert.Contains("Create BeHuman room unavailable", venueView, StringComparison.Ordinal);
        Assert.Contains("Provider create available", venueView, StringComparison.Ordinal);
        Assert.Contains("Create mode stays hidden or unavailable until provider verification and transport are both real.", venueView, StringComparison.Ordinal);
    }
}
