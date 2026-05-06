using Xunit;

namespace Chummer.Tests;

public sealed class PublicSignalProjectionBridgeViewTests
{
    [Fact]
    public void SharedProjectionPacketPartialCarriesFallbackCoreRuleAndCloseoutGuardrails()
    {
        string partialPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_PublicSignalProjectionPacket.cshtml");
        string partial = File.ReadAllText(partialPath);

        Assert.Contains("@model PublicSignalProjectionPacketViewModel", partial, StringComparison.Ordinal);
        Assert.Contains("Open first-party fallback", partial, StringComparison.Ordinal);
        Assert.Contains("@Model.CoreRule", partial, StringComparison.Ordinal);
        Assert.Contains("Boundary conditions", partial, StringComparison.Ordinal);
        Assert.Contains("Required public warning", partial, StringComparison.Ordinal);
        Assert.Contains("First board set", partial, StringComparison.Ordinal);
        Assert.Contains("Canonical sources", partial, StringComparison.Ordinal);
        Assert.Contains("Shipped closeout gate", partial, StringComparison.Ordinal);
    }

    [Fact]
    public void FeedbackRoadmapAndChangelogRoutesRenderTheSharedProjectionPacket()
    {
        string feedbackViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Feedback.cshtml");
        string roadmapViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Roadmap.cshtml");
        string changelogViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Changelog.cshtml");

        string feedbackView = File.ReadAllText(feedbackViewPath);
        string roadmapView = File.ReadAllText(roadmapViewPath);
        string changelogView = File.ReadAllText(changelogViewPath);

        Assert.Contains("var signalProjection = Model.SignalProjection;", feedbackView, StringComparison.Ordinal);
        Assert.Contains("var signalProjection = Model.SignalProjection;", roadmapView, StringComparison.Ordinal);
        Assert.Contains("var signalProjection = Model.SignalProjection;", changelogView, StringComparison.Ordinal);
        Assert.Contains("@await Html.PartialAsync(\"~/Views/Shared/_PublicSignalProjectionPacket.cshtml\", signalProjection)", feedbackView, StringComparison.Ordinal);
        Assert.Contains("@await Html.PartialAsync(\"~/Views/Shared/_PublicSignalProjectionPacket.cshtml\", signalProjection)", roadmapView, StringComparison.Ordinal);
        Assert.Contains("@await Html.PartialAsync(\"~/Views/Shared/_PublicSignalProjectionPacket.cshtml\", signalProjection)", changelogView, StringComparison.Ordinal);
    }

    [Fact]
    public void ControllerAndPageModelsCarryOptionalProjectionPacketsForTheHostedSignalRoutes()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");

        string controller = File.ReadAllText(controllerPath);
        string viewModels = File.ReadAllText(viewModelPath);

        Assert.Contains("private readonly PublicSignalProjectionService _signalProjection;", controller, StringComparison.Ordinal);
        Assert.Contains("BuildOptionalSignalProjectionPacket(currentPath)", controller, StringComparison.Ordinal);
        Assert.Contains("return _signalProjection.BuildPacket(currentPath);", controller, StringComparison.Ordinal);
        Assert.Contains("SignalProjection: signalProjection", controller, StringComparison.Ordinal);
        Assert.Contains("PublicSignalProjectionPacketViewModel? SignalProjection = null", viewModels, StringComparison.Ordinal);
    }
}
