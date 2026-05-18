using Xunit;

namespace Chummer.Tests;

public sealed class FeedbackOperatingLoopViewTests
{
    [Fact]
    public void FeedbackPageProjectsMilestonesRoadmapAndShippedProofIntoOneOperatingLoop()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Feedback.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("A public signal should enter one loop and leave with an evidence-backed closeout.", view, StringComparison.Ordinal);
        Assert.Contains("var signalLoop = Model.SignalLoop;", view, StringComparison.Ordinal);
        Assert.Contains("Signal loop snapshot", view, StringComparison.Ordinal);
        Assert.Contains("@signalLoop.OpenMilestoneCount", view, StringComparison.Ordinal);
        Assert.Contains("Open milestone ledger", view, StringComparison.Ordinal);
        Assert.Contains("Browse roadmap", view, StringComparison.Ordinal);
        Assert.Contains("Open changelog", view, StringComparison.Ordinal);
        Assert.Contains("This page stays public-facing on purpose.", view, StringComparison.Ordinal);
        Assert.DoesNotContain("_PublicSignalOperationsPacket", view, StringComparison.Ordinal);
        Assert.DoesNotContain("_PublicSignalProjectionPacket", view, StringComparison.Ordinal);
        Assert.DoesNotContain("How this board is handled", view, StringComparison.Ordinal);
    }

    [Fact]
    public void ParticipatePageUsesTheSameLiveLoopDataInsteadOfStayingAStaticCommunityExplainer()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Participation is easier to trust when the public loop points at live milestones, named horizons, and proof-backed closeout.", view, StringComparison.Ordinal);
        Assert.Contains("var signalLoop = Model.SignalLoop;", view, StringComparison.Ordinal);
        Assert.Contains("Participation loop snapshot", view, StringComparison.Ordinal);
        Assert.Contains("@signalLoop.OpenMilestoneCount", view, StringComparison.Ordinal);
        Assert.Contains("Open milestone ledger", view, StringComparison.Ordinal);
        Assert.Contains("Browse horizons", view, StringComparison.Ordinal);
        Assert.Contains("Open shipped updates", view, StringComparison.Ordinal);
    }

    [Fact]
    public void RoadmapAndChangelogRoutesReuseTheSharedSignalLoopSnapshotForCrossRailHandoff()
    {
        string roadmapViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Roadmap.cshtml");
        string changelogViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Changelog.cshtml");

        string roadmapView = File.ReadAllText(roadmapViewPath);
        string changelogView = File.ReadAllText(changelogViewPath);

        Assert.Contains("var signalLoop = Model.SignalLoop;", roadmapView, StringComparison.Ordinal);
        Assert.Contains("Page handoff", roadmapView, StringComparison.Ordinal);
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
        Assert.Contains("PublicSignalLoopSnapshotViewModel SignalLoop", viewModels, StringComparison.Ordinal);
        Assert.Contains("int OpenMilestoneCount", viewModels, StringComparison.Ordinal);
        Assert.Contains("IReadOnlyList<ProgramMilestoneSummaryViewModel> MilestoneFollowUp", viewModels, StringComparison.Ordinal);
        Assert.Contains("IReadOnlyList<ResolvedPublicCardViewModel> RoadmapFollowUp", viewModels, StringComparison.Ordinal);
        Assert.Contains("IReadOnlyList<ResolvedPublicCardViewModel> ShippedFollowUp", viewModels, StringComparison.Ordinal);
    }
}
