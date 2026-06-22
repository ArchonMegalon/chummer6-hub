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
        Assert.Contains("Open page", partial, StringComparison.Ordinal);
        Assert.Contains("@Model.CoreRule", partial, StringComparison.Ordinal);
        Assert.Contains("Limits", partial, StringComparison.Ordinal);
        Assert.Contains("Public note", partial, StringComparison.Ordinal);
        Assert.Contains("Review", partial, StringComparison.Ordinal);
        Assert.Contains("Context", partial, StringComparison.Ordinal);
        Assert.Contains("Planning and shipped updates stay separate from public feedback.", partial, StringComparison.Ordinal);
        Assert.DoesNotContain("Open first-party fallback", partial, StringComparison.Ordinal);
        Assert.DoesNotContain("Boundary conditions", partial, StringComparison.Ordinal);
        Assert.DoesNotContain("sourceReceipts", partial, StringComparison.Ordinal);
        Assert.DoesNotContain("canonicalSources", partial, StringComparison.Ordinal);
        Assert.DoesNotContain("journeyProofEvents", partial, StringComparison.Ordinal);
    }

    [Fact]
    public void FeedbackRoadmapAndChangelogRoutesCarryTheSharedProjectionPacketWithoutForcingOperationalCopyEverywhere()
    {
        string feedbackViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Feedback.cshtml");
        string participateViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml");
        string roadmapViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Roadmap.cshtml");
        string changelogViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Changelog.cshtml");

        Assert.False(File.Exists(feedbackViewPath));
        string participateView = File.ReadAllText(participateViewPath);
        string roadmapView = File.ReadAllText(roadmapViewPath);
        string changelogView = File.ReadAllText(changelogViewPath);

        Assert.DoesNotContain("var signalProjection = Model.SignalProjection;", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("var signalProjection = Model.SignalProjection;", roadmapView, StringComparison.Ordinal);
        Assert.Contains("var signalProjection = Model.SignalProjection;", changelogView, StringComparison.Ordinal);
        Assert.DoesNotContain("_PublicSignalProjectionPacket", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("_PublicSignalProjectionPacket", roadmapView, StringComparison.Ordinal);
        Assert.Contains("milestoneFollowUp", changelogView, StringComparison.Ordinal);
        Assert.DoesNotContain("@await Html.PartialAsync(\"~/Views/Shared/_PublicSignalProjectionPacket.cshtml\", signalProjection)", changelogView, StringComparison.Ordinal);
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
