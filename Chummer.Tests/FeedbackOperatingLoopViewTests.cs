using Chummer.Run.Api.Services;
using Xunit;

namespace Chummer.Tests;

public sealed class FeedbackOperatingLoopViewTests
{
    [Fact]
    public void PublicFeedbackRedirectsToFirstPartyParticipatePage()
    {
        string feedbackViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Feedback.cshtml");
        string participateViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml");
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string controller = File.ReadAllText(controllerPath);
        string participateView = File.ReadAllText(participateViewPath);

        Assert.False(File.Exists(feedbackViewPath));
        Assert.True(File.Exists(participateViewPath));
        Assert.DoesNotContain("DefaultProductLiftFeedbackUrl", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("https://chummer6.productlift.dev", controller, StringComparison.Ordinal);
        Assert.Contains("public IActionResult FeedbackPage()", controller, StringComparison.Ordinal);
        Assert.Contains("public async Task<IActionResult> ParticipatePage", controller, StringComparison.Ordinal);
        Assert.Contains("=> Redirect(\"/participate\");", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("BuildParticipatePageModel(", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("return View(\"~/Views/PublicLanding/Feedback.cshtml\"", controller, StringComparison.Ordinal);
        Assert.Contains("return View(\"~/Views/PublicLanding/Participate.cshtml\"", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("ExternalBoardUrl", controller, StringComparison.Ordinal);
        Assert.Contains("participate-toolbar", participateView, StringComparison.Ordinal);
        Assert.Contains("Add feature or bug", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("First-party page", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("ProductLift", participateView, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void RoadmapAndChangelogRoutesReuseTheSharedSignalLoopSnapshotForRelatedPages()
    {
        string roadmapViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Roadmap.cshtml");
        string changelogViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Changelog.cshtml");

        string roadmapView = File.ReadAllText(roadmapViewPath);
        string changelogView = File.ReadAllText(changelogViewPath);

        Assert.Contains("var signalLoop = Model.SignalLoop;", roadmapView, StringComparison.Ordinal);
        Assert.Contains("Related pages", roadmapView, StringComparison.Ordinal);
        Assert.Contains("Open changelog", roadmapView, StringComparison.Ordinal);
        Assert.Contains("@signalLoop.FollowSettingsHref", roadmapView, StringComparison.Ordinal);
        Assert.Contains("var signalLoop = Model.SignalLoop;", changelogView, StringComparison.Ordinal);
        Assert.Contains("Loop return", changelogView, StringComparison.Ordinal);
        Assert.Contains("Browse roadmap", changelogView, StringComparison.Ordinal);
        Assert.Contains("@signalLoop.FollowSettingsHref", changelogView, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicSignalLoopSnapshotIsSharedAcrossParticipateRoadmapAndNowFamilyModels()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");

        string controller = File.ReadAllText(controllerPath);
        string viewModels = File.ReadAllText(viewModelPath);

        Assert.Contains("BuildPublicSignalLoopSnapshot(", controller, StringComparison.Ordinal);
        Assert.Contains("_landing.CardsForBucket(surface, \"coming_next\")", controller, StringComparison.Ordinal);
        Assert.Contains("_landing.CardsForBucket(surface, \"whats_real_now\")", controller, StringComparison.Ordinal);
        Assert.Contains("Where(static card => PublicSurfaceStatus.IsAvailableToday(card.Badge))", controller, StringComparison.Ordinal);
        Assert.Contains("SignalLoop: signalLoop", controller, StringComparison.Ordinal);
        Assert.Contains("public sealed record PublicSignalLoopSnapshotViewModel(", viewModels, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("public sealed record NowPageViewModel(", viewModels, StringComparison.Ordinal);
        Assert.Contains("public sealed record RoadmapPageViewModel(", viewModels, StringComparison.Ordinal);
        Assert.Contains("int OpenMilestoneCount", viewModels, StringComparison.Ordinal);
        Assert.Contains("IReadOnlyList<ProgramMilestoneSummaryViewModel> MilestoneFollowUp", viewModels, StringComparison.Ordinal);
        Assert.Contains("IReadOnlyList<ResolvedPublicCardViewModel> RoadmapFollowUp", viewModels, StringComparison.Ordinal);
        Assert.Contains("IReadOnlyList<ResolvedPublicCardViewModel> ShippedFollowUp", viewModels, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicAudienceLabelsUseMaintainerLanguageInsteadOfOperatorLanguage()
    {
        Assert.Equal("Maintainers", PublicSurfaceStatus.AudienceLabel("operator"));
        Assert.Equal("Maintainers", PublicSurfaceStatus.AudienceLabel("community_operator"));
    }
}
