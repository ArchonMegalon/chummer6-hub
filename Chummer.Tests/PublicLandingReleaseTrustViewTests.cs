using Xunit;

namespace Chummer.Tests;

public sealed class PublicLandingReleaseTrustViewTests
{
    [Fact]
    public void DownloadsViewKeepsCurrentReleaseKnownIssuesAndInstallHelpVisibleBesidePrimaryCta()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Downloads.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Open current release", view, StringComparison.Ordinal);
        Assert.Contains("@release.KnownIssuesLabel", view, StringComparison.Ordinal);
        Assert.Contains("@release.InstallHelpLabel", view, StringComparison.Ordinal);
        Assert.Contains("Known issues and install help stay nearby. Deeper release evidence lives on the current-release and status surfaces, not in front of the install button.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void LandingViewKeepsOneProofBlockThreeMainJobsAndOneAudienceStrip()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Landing.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("launch-hero", view, StringComparison.Ordinal);
        Assert.Contains("Black Ledger command deck", view, StringComparison.Ordinal);
        Assert.Contains("The city is moving.", view, StringComparison.Ordinal);
        Assert.Contains("workflow-band", view, StringComparison.Ordinal);
        Assert.Contains("flagship-gateway-grid", view, StringComparison.Ordinal);
        Assert.Contains("Open Black Ledger", view, StringComparison.Ordinal);
        Assert.Contains("Download Chummer", view, StringComparison.Ordinal);
        Assert.Contains("Open downloads", view, StringComparison.Ordinal);
        Assert.Contains("Open play shell", view, StringComparison.Ordinal);
        Assert.Contains("Open status", view, StringComparison.Ordinal);
        Assert.Contains("Replay Turn 1", view, StringComparison.Ordinal);
        Assert.DoesNotContain("guestReadableHeroPrimaryHref", view, StringComparison.Ordinal);
        Assert.DoesNotContain("Model.FlagshipCoverage", view, StringComparison.Ordinal);
    }

    [Fact]
    public void DownloadsViewCollapsesOtherPlatformsBeforeAdvancedSupportOnlyRails()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Downloads.cshtml");
        string view = File.ReadAllText(viewPath);

        int platformShelfIndex = view.IndexOf("id=\"platform-shelf\"", StringComparison.Ordinal);
        int advancedAccordionIndex = view.IndexOf("id=\"advanced-downloads\"", StringComparison.Ordinal);

        Assert.Contains("<summary>Other supported platforms</summary>", view, StringComparison.Ordinal);
        Assert.Contains("Main platform downloads", view, StringComparison.Ordinal);
        Assert.Contains("Windows verification and support path", view, StringComparison.Ordinal);
        Assert.True(platformShelfIndex >= 0, "platform shelf should stay visible on the main downloads page");
        Assert.True(advancedAccordionIndex >= 0, "advanced accordion should still exist for manual and support-directed downloads");
        Assert.True(platformShelfIndex < advancedAccordionIndex, "platform shelf should appear before the advanced accordion");
    }

    [Fact]
    public void DownloadsViewKeepsInstallContinuityTruthBesideTheRecommendedShelf()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Downloads.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("recommended-download__trustrail", view, StringComparison.Ordinal);
        Assert.Contains("The same build for everyone", view, StringComparison.Ordinal);
        Assert.Contains("Link this copy on first launch", view, StringComparison.Ordinal);
        Assert.Contains("Devices and access stay calm", view, StringComparison.Ordinal);
        Assert.Contains("Release notes, known issues, and requirements", view, StringComparison.Ordinal);
        Assert.Contains("Open current release", view, StringComparison.Ordinal);
        Assert.DoesNotContain("@Model.FlagshipCoverage.Eyebrow", view, StringComparison.Ordinal);
        Assert.DoesNotContain("id=\"downloads-@card.Id.Replace('_', '-')\"", view, StringComparison.Ordinal);
    }

    [Fact]
    public void DownloadDispatchFallbackKeepsReleaseProofAndRecoveryTrustOnSameRail()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "DownloadDispatch.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("href=\"/now\">What works today</a>", view, StringComparison.Ordinal);
        Assert.Contains("@Model.HelpLabel", view, StringComparison.Ordinal);
        Assert.Contains("Status, known issues, and install help stay on one release page so recovery never depends on stale page copy.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void DownloadDispatchViewUsesTheSharedRouteChoiceShellInsteadOfReadingLikeAnIsolatedInstallerTrap()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "DownloadDispatch.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Keep install handoff, platform choice, release proof, and recovery on separate pages.", view, StringComparison.Ordinal);
        Assert.Contains("route-choice-grid", view, StringComparison.Ordinal);
        Assert.Contains("Return to downloads when the job is choosing a platform or installer shape", view, StringComparison.Ordinal);
        Assert.Contains("Open Devices and access only when this copy needs relink or reclaim help", view, StringComparison.Ordinal);
        Assert.Contains("Open what works today when the question is current proof, not this device handoff", view, StringComparison.Ordinal);
        Assert.Contains("Leave the handoff for tracked support or help as soon as the problem becomes recovery-bound", view, StringComparison.Ordinal);
        Assert.Contains("Use this page to finish one install handoff, then move to the page that owns the next job.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void ParticipatePageKeepsPublicCodexInvitationGenericWhileDeepAuthFlowNamesProvider()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml");
        string consoleViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "CodexParticipation", "Console.cshtml");
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "CodexParticipationController.cs");

        string view = File.ReadAllText(viewPath);
        string consoleView = File.ReadAllText(consoleViewPath);
        string controller = File.ReadAllText(controllerPath);

        Assert.Contains("Signed-in participation", view, StringComparison.Ordinal);
        Assert.Contains("/auth/google/start?next=%2Fparticipate%2Fcodex", view, StringComparison.Ordinal);
        Assert.Contains("guided contribution tools tied to your account", view, StringComparison.Ordinal);
        Assert.DoesNotContain("OpenAI account in ChatGPT", view, StringComparison.Ordinal);
        Assert.Contains("OpenAI account in ChatGPT", consoleView, StringComparison.Ordinal);
        Assert.Contains("authorize with your OpenAI account in ChatGPT", controller, StringComparison.Ordinal);
        Assert.Contains("Public Codex contribution code", consoleView, StringComparison.Ordinal);
        Assert.Contains("counts the tokens used through it", consoleView, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicProductLiftFallbackRoutesStayHonestAcrossFeedbackRoadmapAndShippedProof()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string feedbackViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Feedback.cshtml");
        string roadmapViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Roadmap.cshtml");
        string changelogViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Changelog.cshtml");

        string controller = File.ReadAllText(controllerPath);
        string feedbackView = File.ReadAllText(feedbackViewPath);
        string roadmapView = File.ReadAllText(roadmapViewPath);
        string changelogView = File.ReadAllText(changelogViewPath);

        Assert.Contains("return View(\"~/Views/PublicLanding/Feedback.cshtml\", model);", controller, StringComparison.Ordinal);
        Assert.Contains("return View(\"~/Views/PublicLanding/Changelog.cshtml\", model);", controller, StringComparison.Ordinal);
        Assert.Contains("BuildParticipatePageModel(", controller, StringComparison.Ordinal);
        Assert.Contains("BuildNowPageModel(", controller, StringComparison.Ordinal);
        Assert.Contains("return View(\"~/Views/PublicLanding/Roadmap.cshtml\", model);", controller, StringComparison.Ordinal);
        Assert.Contains("BuildRoadmapMilestones()", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("Redirect(\"/horizons?source=roadmap#public-roadmap-projection\")", controller, StringComparison.Ordinal);
        Assert.Contains("route-anchor-target", feedbackView, StringComparison.Ordinal);
        Assert.Contains("route-anchor-target", roadmapView, StringComparison.Ordinal);
        Assert.Contains("route-anchor-target", changelogView, StringComparison.Ordinal);
        Assert.Contains("These first-party pages keep feedback visible and easy to follow without bouncing people across aliases or private support paths.", feedbackView, StringComparison.Ordinal);
        Assert.Contains("Safe public signal", feedbackView, StringComparison.Ordinal);
        Assert.Contains("What looks likely next, and what is still only planned", roadmapView, StringComparison.Ordinal);
        Assert.Contains("Milestone ledger", roadmapView, StringComparison.Ordinal);
        Assert.Contains("Shipped updates with proof you can verify", changelogView, StringComparison.Ordinal);
        Assert.Contains("status-decision-strip", changelogView, StringComparison.Ordinal);
    }

    [Fact]
    public void ProductStoryViewFramesTablePainAndContinuityBeforeRoleTaxonomy()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "ProductStory.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("story-pain-grid", view, StringComparison.Ordinal);
        Assert.Contains("A character and campaign companion.", view, StringComparison.Ordinal);
        Assert.Contains("Players, GMs, and returning groups.", view, StringComparison.Ordinal);
        Assert.Contains("Check what works now before you assume.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void StatusPageUsesTheSharedRouteChoiceShellInsteadOfOnlyAFlatSummaryTable()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Status.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Install or update from the downloads page", view, StringComparison.Ordinal);
        Assert.Contains("route-choice-grid", view, StringComparison.Ordinal);
        Assert.Contains("Open the larger machine picture only when the short status line is not enough", view, StringComparison.Ordinal);
        Assert.Contains("Use what works today when the question is proof, not packaging", view, StringComparison.Ordinal);
        Assert.Contains("Leave status for first-party help as soon as the issue becomes private", view, StringComparison.Ordinal);
        Assert.Contains("status-decision-strip", view, StringComparison.Ordinal);
        Assert.Contains("Signed-in return", view, StringComparison.Ordinal);
        Assert.Contains("ContextualPreviewHref(choice.Href)", view, StringComparison.Ordinal);
    }

    [Fact]
    public void HorizonsPageUsesTheSharedRouteChoiceAndDecisionShellInsteadOfOnlyLongscrollBands()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Horizons.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("trust-page-hero", view, StringComparison.Ordinal);
        Assert.Contains("status-decision-strip", view, StringComparison.Ordinal);
        Assert.Contains("route-choice-grid", view, StringComparison.Ordinal);
        Assert.Contains("Compare with live proof instead of treating a horizon as already shipped", view, StringComparison.Ordinal);
        Assert.Contains("The milestone roadmap lives on a separate page", view, StringComparison.Ordinal);
        Assert.Contains("Use public feedback when a future idea matches real user pain", view, StringComparison.Ordinal);
        Assert.Contains("Use horizons to understand the future, then move to the page that owns the present-tense job.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void KarmaForgeViewUsesTheSharedRouteChoiceShellInsteadOfActingLikeADiscoveryDeadEnd()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "KarmaForge.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Keep intake, roadmap, continuity, and support on separate pages.", view, StringComparison.Ordinal);
        Assert.Contains("route-choice-grid", view, StringComparison.Ordinal);
        Assert.Contains("Stay on this page when the job is turning table pain into a Chummer-owned packet", view, StringComparison.Ordinal);
        Assert.Contains("Return to participate when the question is broader public discovery, not this intake packet", view, StringComparison.Ordinal);
        Assert.Contains("Create the account only when you want packet history and follow-through in one place", view, StringComparison.Ordinal);
        Assert.Contains("Leave KARMA FORGE for normal support as soon as the issue is no longer discovery work", view, StringComparison.Ordinal);
        Assert.Contains("The loop is visible before any rules work starts.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void KarmaForgeControllerAndServicesWireThePublicIntakeAndReceiptRoutes()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string servicesPath = RepoPaths.FromRoot("Chummer.Run.Api", "ServiceCollectionBoundedContextExtensions.cs");

        string controller = File.ReadAllText(controllerPath);
        string services = File.ReadAllText(servicesPath);

        Assert.Contains("KarmaForgeDiscoveryService", services, StringComparison.Ordinal);
        Assert.Contains("KarmaForgeStore", services, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/participate/karma-forge\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"/participate/karma-forge\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/participate/karma-forge/submitted/{submissionId}\")]", controller, StringComparison.Ordinal);
        Assert.Contains("KarmaForgeSubmitted.cshtml", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void BuildGhostConciergeViewUsesTheSharedParticipationDecisionShell()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "BuildGhostConcierge.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Build Ghost operating split", view, StringComparison.Ordinal);
        Assert.Contains("status-decision-strip", view, StringComparison.Ordinal);
        Assert.Contains("route-choice-grid", view, StringComparison.Ordinal);
        Assert.Contains("The experiment should leave behind receipts, not vibes.", view, StringComparison.Ordinal);
        Assert.Contains("Use the public tools to guide the experiment, not to own it.", view, StringComparison.Ordinal);
        Assert.Contains("Signed-in ALICE", view, StringComparison.Ordinal);
        Assert.Contains("The real compare bench is now a named account lane.", view, StringComparison.Ordinal);
        Assert.Contains("@signedInBench.EntryLabel", view, StringComparison.Ordinal);
        Assert.Contains("Open lead build handoff", view, StringComparison.Ordinal);
    }

    [Fact]
    public void ParticipateViewLinksToTheBuildGhostConciergeWithoutClaimingToolTruth()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("ALICE build ghosts", view, StringComparison.Ordinal);
        Assert.Contains("Open Build Ghost concierge", view, StringComparison.Ordinal);
        Assert.Contains("The actual Build Ghost compare and apply truth still stays inside first-party Chummer runtime and receipts.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void BuildGhostConciergeControllerAndServicesWireTheBoundedRoute()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string accountsControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");
        string campaignSpineControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "CampaignSpineController.cs");
        string servicesPath = RepoPaths.FromRoot("Chummer.Run.Api", "ServiceCollectionBoundedContextExtensions.cs");

        string controller = File.ReadAllText(controllerPath);
        string accountsController = File.ReadAllText(accountsControllerPath);
        string campaignSpineController = File.ReadAllText(campaignSpineControllerPath);
        string services = File.ReadAllText(servicesPath);

        Assert.Contains("BuildGhostConciergeService", services, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/participate/build-ghosts\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/participate/build-ghosts.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/alice\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/alice/receipts/build-ghost.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("BuildGhostConcierge.cshtml", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/alice\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/alice/{handoffId}\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/alice/open\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/build-handoffs\")]", campaignSpineController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/build-handoffs/{handoffId}\")]", campaignSpineController, StringComparison.Ordinal);
    }

    [Fact]
    public void BuildGhostConciergeKeepsTheClientFeedbackLoopVisible()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "BuildGhostConcierge.cshtml");
        string servicePath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "KarmaForge", "BuildGhostConciergeService.cs");

        string view = File.ReadAllText(viewPath);
        string service = File.ReadAllText(servicePath);

        Assert.Contains("Feedback loop", view, StringComparison.Ordinal);
        Assert.Contains("Open Build Ghost report", view, StringComparison.Ordinal);
        Assert.Contains("Open public feedback", view, StringComparison.Ordinal);
        Assert.Contains("/contact?kind=bug_report", service, StringComparison.Ordinal);
        Assert.Contains("/feedback?topic=build-ghosts", service, StringComparison.Ordinal);
    }

    [Fact]
    public void TablePulseRouteUsesTheSharedTrustShellInsteadOfLegacyRedirectOnly()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string legacyControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "LegacySurfaceRedirectController.cs");

        string controller = File.ReadAllText(controllerPath);
        string legacyController = File.ReadAllText(legacyControllerPath);

        Assert.Contains("[HttpGet(\"/table-pulse\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/table-pulse/receipts/live-and-aftermath.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("heading: \"TABLE PULSE\"", controller, StringComparison.Ordinal);
        Assert.Contains("TABLE PULSE is now a real product surface, not just a redirect.", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("[HttpGet(\"/table-pulse\")]", legacyController, StringComparison.Ordinal);
    }

    [Fact]
    public void DocumentPortalUsesNamedPublicRoutesAndKeepsFlipLinkAsViewerBoundaryOnly()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string servicesPath = RepoPaths.FromRoot("Chummer.Run.Api", "ServiceCollectionBoundedContextExtensions.cs");
        string controller = File.ReadAllText(controllerPath);
        string services = File.ReadAllText(servicesPath);

        Assert.Contains("FlipLinkDocumentPortalService", services, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/docs\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/docs/{slug}\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/docs/{slug}/receipts/publication.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/docs/embed/{slug}\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/docs/{slug}/download.pdf\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/docs/category/{category}\")]", controller, StringComparison.Ordinal);
        Assert.Contains("TryBuildPublicationReceipt", controller, StringComparison.Ordinal);
        Assert.Contains("TryBuildPdfArtifact", controller, StringComparison.Ordinal);
        Assert.Contains("heading: \"Document Portal\"", controller, StringComparison.Ordinal);
        Assert.Contains("title: document.Title", controller, StringComparison.Ordinal);
        Assert.Contains("heading: document.Title", controller, StringComparison.Ordinal);
        Assert.Contains("FlipLink is the planned viewer layer", controller, StringComparison.Ordinal);
        Assert.Contains("Chummer owns the source document, version, access policy, and safety boundary.", controller, StringComparison.Ordinal);
        Assert.Contains("This document is generated and owned by Chummer. FlipLink is the viewer.", controller, StringComparison.Ordinal);
        Assert.Contains("Download PDF", controller, StringComparison.Ordinal);
        Assert.Contains("heading: \"Quickstart embed boundary\"", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void CommunityHubUsesNamedPublicReceiptAndSignedInBoardRoutes()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string accountsControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");
        string campaignSpineControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "CampaignSpineController.cs");

        string controller = File.ReadAllText(controllerPath);
        string accountsController = File.ReadAllText(accountsControllerPath);
        string campaignSpineController = File.ReadAllText(campaignSpineControllerPath);

        Assert.Contains("[HttpGet(\"/community\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/community/receipts/open-run-network.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("Community Hub now ships a real first-party open-run network", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/community\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/community/open\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/open-runs\")]", campaignSpineController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/open-runs/{openRunId}\")]", campaignSpineController, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"me/workspaces/{workspaceId}/open-runs\")]", campaignSpineController, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"me/open-runs/{openRunId}/schedule\")]", campaignSpineController, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"me/open-runs/{openRunId}/meeting-handoff\")]", campaignSpineController, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"me/open-runs/{openRunId}/closeout\")]", campaignSpineController, StringComparison.Ordinal);
    }

    [Fact]
    public void CreatorOsUsesNamedPublicReceiptAndSignedInPublicationDeskRoutes()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string accountsControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");

        string controller = File.ReadAllText(controllerPath);
        string accountsController = File.ReadAllText(accountsControllerPath);

        Assert.Contains("[HttpGet(\"/creator\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/creator/receipts/publication-network.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("Creator OS now ships a real first-party publication network", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/creator\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/creator/open\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/creator/{publicationId}\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/artifacts/publications/{publicationId}\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/api/v1/public/artifacts/publications/{publicationId}\")]", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void JackpointUsesNamedPublicReceiptAndSignedInPublicationRoutes()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string accountsControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");
        string campaignSpineControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "CampaignSpineController.cs");

        string controller = File.ReadAllText(controllerPath);
        string accountsController = File.ReadAllText(accountsControllerPath);
        string campaignSpineController = File.ReadAllText(campaignSpineControllerPath);

        Assert.Contains("[HttpGet(\"/jackpoint\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/jackpoint/receipts/briefing-network.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("JACKPOINT now ships a real first-party briefing network", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/jackpoint\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/jackpoint/open\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/jackpoint/{publicationId}\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/publications\")]", campaignSpineController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/publications/{publicationId}\")]", campaignSpineController, StringComparison.Ordinal);
    }

    [Fact]
    public void RunsiteUsesNamedPublicReceiptAndSignedInPrepRoutes()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string accountsControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");
        string campaignSpineControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "CampaignSpineController.cs");

        string controller = File.ReadAllText(controllerPath);
        string accountsController = File.ReadAllText(accountsControllerPath);
        string campaignSpineController = File.ReadAllText(campaignSpineControllerPath);

        Assert.Contains("[HttpGet(\"/runsites\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/runsites/receipts/prep-network.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("RUNSITE now ships as a real prep network", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/runsites\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/runsites/open\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/runsites/{workspaceId}\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/workspace-digests\")]", campaignSpineController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/runs\")]", campaignSpineController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/runs/{runId}\")]", campaignSpineController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/workspaces/{workspaceId}/prep-library\")]", campaignSpineController, StringComparison.Ordinal);
    }

    [Fact]
    public void RunControlUsesNamedPublicReceiptSignedInDeskAndTypedControlRoutes()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string accountsControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");
        string campaignSpineControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "CampaignSpineController.cs");

        string controller = File.ReadAllText(controllerPath);
        string accountsController = File.ReadAllText(accountsControllerPath);
        string campaignSpineController = File.ReadAllText(campaignSpineControllerPath);

        Assert.Contains("[HttpGet(\"/run-control\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/roadmap/run-control\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/run-control/receipts/control-network.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/run-control/packets/{packetId}.md\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/run-control/packets/{packetId}.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("RUN CONTROL now ships a real first-party GM operations lane", controller, StringComparison.Ordinal);
        Assert.Contains("IsKnownRunControlPacketId", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/run-control\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/run-control/open\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/run-control/{runId}\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/run-control/dashboard\")]", campaignSpineController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/run-control/runs/{runId}\")]", campaignSpineController, StringComparison.Ordinal);
    }

    [Fact]
    public void RunnerPassportUsesNamedPublicReceiptAndSignedInContinuityRoutes()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string accountsControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");

        string controller = File.ReadAllText(controllerPath);
        string accountsController = File.ReadAllText(accountsControllerPath);

        Assert.Contains("[HttpGet(\"/passport\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/passport/receipts/identity-network.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("Runner Passport now ships a real first-party continuity lane", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/passport\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/passport/open\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("/account/ledger/notifications", controller, StringComparison.Ordinal);
        Assert.Contains("/account/work#aftermath-packages", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void QuicksilverUsesNamedPublicReceiptSignedInCommandDeckAndTypedJumpRoutes()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string accountsControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");
        string campaignSpineControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "CampaignSpineController.cs");

        string controller = File.ReadAllText(controllerPath);
        string accountsController = File.ReadAllText(accountsControllerPath);
        string campaignSpineController = File.ReadAllText(campaignSpineControllerPath);

        Assert.Contains("[HttpGet(\"/quicksilver\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/roadmap/quicksilver\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/quicksilver/receipts/command-network.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/quicksilver/packets/{packetId}.md\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/quicksilver/packets/{packetId}.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("Quicksilver now ships a real first-party command deck", controller, StringComparison.Ordinal);
        Assert.Contains("IsKnownQuicksilverPacketId", controller, StringComparison.Ordinal);
        Assert.Contains("return NotFound();", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/quicksilver\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/quicksilver/open\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/quicksilver/{focus}\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/quicksilver/command-deck\")]", campaignSpineController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/quicksilver/jump-targets\")]", campaignSpineController, StringComparison.Ordinal);
    }

    [Fact]
    public void AnarchyUsesNamedRuntimeReceiptAndShippedRulesLightLanguage()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Anarchy.cshtml");

        string controller = File.ReadAllText(controllerPath);
        string view = File.ReadAllText(viewPath);

        Assert.Contains("[HttpGet(\"/anarchy/receipts/runtime.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("A shipped rules-light lane for mobile play, dispatches, faction consequence, and fast continuity.", controller, StringComparison.Ordinal);
        Assert.Contains("VerdictLabel: \"Shipped rules-light lane\"", controller, StringComparison.Ordinal);
        Assert.Contains("Shipped rules-light lane for Black Ledger, dispatches, and mobile play.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void GhostwireUsesNamedReplayReceiptAndShippedPacketLanguage()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string controller = File.ReadAllText(controllerPath);

        Assert.Contains("[HttpGet(\"/ghostwire\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/roadmap/ghostwire\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/ghostwire/receipts/replay-network.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("GHOSTWIRE now ships first-party after-action packet rails", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void LedgerControllerUsesBoardLanguageForDeterministicTurnTwo()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string controller = File.ReadAllText(controllerPath);

        Assert.Contains("This deterministic turn-two board shows how AI interim stewards stay bounded", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("This deterministic turn-two preview shows how AI interim stewards stay bounded", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void FeatureDetailViewUsesTheSharedRouteChoiceShellAndExitRailInsteadOfStoppingAtHeroAndFamilyPartial()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "FeatureDetail.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Keep feature detail, proof, installs, and help on their own pages.", view, StringComparison.Ordinal);
        Assert.Contains("route-choice-grid", view, StringComparison.Ordinal);
        Assert.Contains("Compare with live proof instead of treating a horizon as already shipped", view, StringComparison.Ordinal);
        Assert.Contains("Use downloads when the question becomes install or update posture", view, StringComparison.Ordinal);
        Assert.Contains("Leave feature detail for first-party help as soon as the issue becomes support or recovery", view, StringComparison.Ordinal);
        Assert.Contains("Use the feature detail to answer one question, then move to the page that owns the next job.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AuthEntryViewShowsConcreteContinuityValueBeforeProviderChoice()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Auth", "Entry.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("auth-value-strip", view, StringComparison.Ordinal);
        Assert.Contains("Linked installs", view, StringComparison.Ordinal);
        Assert.Contains("Devices and access", view, StringComparison.Ordinal);
        Assert.Contains("The binary stays the same for everyone.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void AuthEntryViewKeepsGoogleCtaOnInstallerReturnPath()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AuthController.cs");
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Auth", "Entry.cshtml");
        string controller = File.ReadAllText(controllerPath);
        string view = File.ReadAllText(viewPath);

        Assert.Contains("GoogleStartHref: $\"/auth/google/start?next={Uri.EscapeDataString(nextPath)}\"", controller, StringComparison.Ordinal);
        Assert.Contains("Model.NextPath.StartsWith(\"/downloads\"", view, StringComparison.Ordinal);
        Assert.Contains("href=\"@Model.GoogleStartHref\"", view, StringComparison.Ordinal);
        Assert.Contains("Continue with Google", view, StringComparison.Ordinal);
        Assert.Contains("After verification you return to @nextTarget.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void LayoutLoadsClickRankOnlyWhenExplicitlyConfiguredWithoutCacheBusting()
    {
        string layoutPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml");
        string layout = File.ReadAllText(layoutPath);

        Assert.Contains("navigator.globalPrivacyControl === true", layout, StringComparison.Ordinal);
        Assert.Contains("requestIdleCallback", layout, StringComparison.Ordinal);
        Assert.DoesNotContain("87b16b25-a599-41f5-80e4-43c4433975d5", layout, StringComparison.Ordinal);
        Assert.DoesNotContain("new Date().getTime()", layout, StringComparison.Ordinal);
        Assert.Contains("data-clickrank-ai='seo'", layout, StringComparison.Ordinal);
    }

    [Fact]
    public void LayoutAndSiteScriptWireTheCompactNavigationInsteadOfLeavingDeadToggleHooks()
    {
        string layoutPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml");
        string scriptPath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "js", "site.js");
        string cssPath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "css", "site.css");

        string layout = File.ReadAllText(layoutPath);
        string script = File.ReadAllText(scriptPath);
        string css = File.ReadAllText(cssPath);

        Assert.Contains("data-nav-toggle", layout, StringComparison.Ordinal);
        Assert.Contains("data-nav-panel", layout, StringComparison.Ordinal);
        Assert.Contains("site-nav-panel", layout, StringComparison.Ordinal);
        Assert.Contains("chrome.PublicSignalNavigation", layout, StringComparison.Ordinal);
        Assert.Contains("Help", layout, StringComparison.Ordinal);
        Assert.Contains("Account", layout, StringComparison.Ordinal);
        Assert.Contains("closeNavPanel", script, StringComparison.Ordinal);
        Assert.Contains("nav-sheet-open", script, StringComparison.Ordinal);
        Assert.Contains("event.key === \"Escape\"", script, StringComparison.Ordinal);
        Assert.Contains("body.nav-sheet-open", css, StringComparison.Ordinal);
        Assert.Contains(".site-nav__toggle", css, StringComparison.Ordinal);
    }

    [Fact]
    public void LayoutKeepsQuickActionsInHeaderAndFooterInsteadOfAStickyBottomBanner()
    {
        string layoutPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml");
        string layout = File.ReadAllText(layoutPath);

        Assert.DoesNotContain("bottomQuickAction", layout, StringComparison.Ordinal);
        Assert.DoesNotContain("site-bottom-cta", layout, StringComparison.Ordinal);
        Assert.Contains("Shadowrun character and campaign companion", layout, StringComparison.Ordinal);
    }

    [Fact]
    public void ContactSupportPageSteersSafePublicFeedbackToFixerBoardBeforePrivateIntake()
    {
        string trustViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml");
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");

        string trustView = File.ReadAllText(trustViewPath);
        string controller = File.ReadAllText(controllerPath);

        Assert.Contains("Safe public feedback should start on the public feedback page", trustView, StringComparison.Ordinal);
        Assert.Contains("Href: \"/feedback\"", trustView, StringComparison.Ordinal);
        Assert.Contains("Label: \"Open feedback\"", trustView, StringComparison.Ordinal);
        Assert.Contains("string.Equals(Model.PageId, \"contact\"", trustView, StringComparison.Ordinal);
        Assert.Contains("Safe public feedback should start on the public feedback page. Choose this form only when the issue needs private or account-linked follow-up.", trustView, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicationViewsShowReviewRequiredRouteLabelsWhenDesktopProofCoverageIsMissing()
    {
        string publicationViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "PublicCreatorPublication.cshtml");
        string shelfViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Shelf.cshtml");

        string publicationView = File.ReadAllText(publicationViewPath);
        string shelfView = File.ReadAllText(shelfViewPath);

        Assert.Contains("Model.TrustPulse?.MissingDesktopClientCoverage == true", publicationView, StringComparison.Ordinal);
        Assert.Contains("Review-required state", publicationView, StringComparison.Ordinal);
        Assert.Contains("Model.TrustPulse?.MissingDesktopClientCoverage == true", shelfView, StringComparison.Ordinal);
        Assert.Contains("review-required", shelfView, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicCreatorPublicationViewUsesTheSharedRouteChoiceShellWithoutPretendingToBeTheInstallRail()
    {
        string publicationViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "PublicCreatorPublication.cshtml");
        string publicationView = File.ReadAllText(publicationViewPath);

        Assert.Contains("Choose discovery, downloads, signed-in continuity, or help on purpose.", publicationView, StringComparison.Ordinal);
        Assert.Contains("route-choice-grid", publicationView, StringComparison.Ordinal);
        Assert.Contains("Stay in the proof gallery when the job is proof, provenance, or comparison", publicationView, StringComparison.Ordinal);
        Assert.Contains("Leave this page when the next job is installing the product", publicationView, StringComparison.Ordinal);
        Assert.Contains("Use this page to inspect the publication, then move to the page that owns the next job.", publicationView, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicLandingControllerFailClosesExchangeAndOutputRoutesWithoutCurrentRouteReceipt()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string localProofServicePath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "LocalReleaseProofArtifactService.cs");
        string controller = File.ReadAllText(controllerPath);
        string localProofService = File.ReadAllText(localProofServicePath);

        Assert.Contains("LocalProofReceiptMatch? routeReceipt = routeLookup.ReceiptMatch;", controller, StringComparison.Ordinal);
        Assert.Contains("if (routeReceipt is null)", controller, StringComparison.Ordinal);
        Assert.Contains("return new RouteClaimStatus(\"bounded_failure\", missingReceiptReason);", controller, StringComparison.Ordinal);
        Assert.Contains("downloadReceiptId = dispatch.Receipt.ReceiptId", controller, StringComparison.Ordinal);
        Assert.Contains("claimTicketId = dispatch.ClaimTicket.TicketId", controller, StringComparison.Ordinal);
        Assert.Contains("BuildRouteReceiptPayload(routeLookup.ReceiptMatch)", controller, StringComparison.Ordinal);
        Assert.Contains("No current local release-proof receipt is attached to this install recovery exchange route", controller, StringComparison.Ordinal);
        Assert.Contains("No current local release-proof receipt is attached to this release-bundle route or format.", controller, StringComparison.Ordinal);
        Assert.Contains("No current local release-proof receipt is attached to the public creator-publication detail route.", controller, StringComparison.Ordinal);
        Assert.Contains("ResolvePublicRouteClaimStatus(", controller, StringComparison.Ordinal);
        Assert.Contains("Current direct route receipt is attached, but parity claims stay review-required because", controller, StringComparison.Ordinal);
        Assert.Contains("public-shelf:/artifacts/publications/{publicationId}", controller, StringComparison.Ordinal);
        Assert.Contains("CHUMMER_HUB_LOCAL_RELEASE_PROOF_FILE", localProofService, StringComparison.Ordinal);
        Assert.Contains(".codex-studio/published/HUB_LOCAL_RELEASE_PROOF.generated.json", localProofService, StringComparison.Ordinal);
    }

    [Fact]
    public void LayoutFooterKeepsPublicProofAndHelpLinksWithoutCanonDisclosureChrome()
    {
        string layoutPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml");

        string layout = File.ReadAllText(layoutPath);

        Assert.Contains("Use <a class=\"quiet-link\" href=\"/downloads\">Get Chummer</a> for the acquisition path, <a class=\"quiet-link\" href=\"/now\">what works today</a> for current proof, and <a class=\"quiet-link\" href=\"/status\">status</a> for cautions.", layout, StringComparison.Ordinal);
        Assert.DoesNotContain("@chrome.FooterCanonicalSource", layout, StringComparison.Ordinal);
        Assert.DoesNotContain("@chrome.FooterGeneratedNote", layout, StringComparison.Ordinal);
        Assert.DoesNotContain("Truth boundary", layout, StringComparison.Ordinal);
    }

    [Fact]
    public void LayoutUsesCanonPublicSignalNavigationForFixerBoardRoadmapAndChangelogLinks()
    {
        string layoutPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml");
        string navigationServicePath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "PublicNavigationService.cs");
        string chromeServicePath = RepoPaths.FromRoot("Chummer.Run.Api", "Services", "HubPageChromeService.cs");
        string cssPath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "css", "site.css");

        string layout = File.ReadAllText(layoutPath);
        string navigationService = File.ReadAllText(navigationServicePath);
        string chromeService = File.ReadAllText(chromeServicePath);
        string css = File.ReadAllText(cssPath);

        Assert.Contains("chrome.PublicSignalNavigation", layout, StringComparison.Ordinal);
        Assert.Contains("isPublicSignalCurrent", layout, StringComparison.Ordinal);
        Assert.Contains("\"/feedback\" => normalizedCurrentPath is \"/feedback\"", layout, StringComparison.Ordinal);
        Assert.Contains("\"/changelog\" => normalizedCurrentPath is \"/changelog\"", layout, StringComparison.Ordinal);
        Assert.Contains("chrome.PublicSignalNavigation", layout, StringComparison.Ordinal);
        Assert.Contains("PublicSignal: BuildLinks(document.PublicSignalNav, \"public signal navigation\")", navigationService, StringComparison.Ordinal);
        Assert.Contains("PublicSignalNavigation: nav.PublicSignal", chromeService, StringComparison.Ordinal);
        Assert.Contains(".site-footer__current", css, StringComparison.Ordinal);
    }

    [Fact]
    public void LegacyProductLiftAliasCopyNowPointsBackToDedicatedFirstPartyRoutes()
    {
        string participateViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml");
        string horizonsViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Horizons.cshtml");
        string nowViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Now.cshtml");
        string feedbackViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Feedback.cshtml");

        string participateView = File.ReadAllText(participateViewPath);
        string horizonsView = File.ReadAllText(horizonsViewPath);
        string nowView = File.ReadAllText(nowViewPath);
        string feedbackView = File.ReadAllText(feedbackViewPath);

        Assert.Contains("You followed a legacy feedback handoff", participateView, StringComparison.Ordinal);
        Assert.Contains("The current public signal page lives on <code class=\"mono-receipt\">/feedback</code>", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("feedback returns here, roadmap resolves through Horizons, and shipped closeout resolves through What works today.", participateView, StringComparison.Ordinal);
        Assert.Contains("You followed a legacy roadmap handoff", horizonsView, StringComparison.Ordinal);
        Assert.Contains("The milestone-backed public roadmap now lives on <code class=\"mono-receipt\">/roadmap</code>", horizonsView, StringComparison.Ordinal);
        Assert.DoesNotContain("/participate?source=feedback#public-feedback", horizonsView, StringComparison.Ordinal);
        Assert.Contains("You followed a legacy shipped handoff", nowView, StringComparison.Ordinal);
        Assert.Contains("The shipped update stream now lives on <code class=\"mono-receipt\">/changelog</code>", nowView, StringComparison.Ordinal);
        Assert.DoesNotContain("/participate?source=feedback#public-feedback", nowView, StringComparison.Ordinal);
        Assert.Contains("Create the account when you want signal, installs, support, and roadmap follow-up to return to one place.", feedbackView, StringComparison.Ordinal);
        Assert.Contains("Truth stays split on purpose", feedbackView, StringComparison.Ordinal);
    }

    [Fact]
    public void LayoutUsesContextualCurrentRouteMatchingForDetailAndSubmissionPages()
    {
        string layoutPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml");
        string layout = File.ReadAllText(layoutPath);

        Assert.Contains("isContextualRouteCurrent", layout, StringComparison.Ordinal);
        Assert.Contains("normalizedCurrentPath.StartsWith(\"/roadmap/\"", layout, StringComparison.Ordinal);
        Assert.Contains("normalizedCurrentPath.StartsWith(\"/artifacts/\"", layout, StringComparison.Ordinal);
        Assert.Contains("normalizedCurrentPath.StartsWith(\"/participate/\"", layout, StringComparison.Ordinal);
        Assert.Contains("normalizedCurrentPath.StartsWith(\"/contact/\"", layout, StringComparison.Ordinal);
        Assert.Contains("<span class=\"site-footer__current\">@link.Label</span>", layout, StringComparison.Ordinal);
    }

    [Fact]
    public void StickyMobileQuickActionBannerIsGoneFromTheSharedPublicShell()
    {
        string layoutPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml");
        string scriptPath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "js", "site.js");

        string layout = File.ReadAllText(layoutPath);
        string script = File.ReadAllText(scriptPath);

        Assert.DoesNotContain("data-bottom-cta-key=\"@routeKey\"", layout, StringComparison.Ordinal);
        Assert.DoesNotContain("data-bottom-cta-dismiss", layout, StringComparison.Ordinal);
        Assert.DoesNotContain("chummer.bottom_cta.dismissed_routes", script, StringComparison.Ordinal);
        Assert.DoesNotContain("bottomCta.hidden = true", script, StringComparison.Ordinal);
    }

    [Fact]
    public void OnrampUsesNamedPublicReceiptSignedInDeskAndTypedStarterRecoveryRoutes()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string accountsControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");
        string campaignSpineControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "CampaignSpineController.cs");

        string controller = File.ReadAllText(controllerPath);
        string accountsController = File.ReadAllText(accountsControllerPath);
        string campaignSpineController = File.ReadAllText(campaignSpineControllerPath);

        Assert.Contains("[HttpGet(\"/onramp\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/onramp/receipts/guided-starter.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/onramp/packets/{packetId}.md\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/onramp/packets/{packetId}.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("BuildOnrampPageModel", controller, StringComparison.Ordinal);
        Assert.Contains("BuildOnrampReceipt", controller, StringComparison.Ordinal);
        Assert.Contains("IsKnownOnrampPacketId", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/onramp\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/onramp/open\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/onramp/starter\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/onramp/dashboard\")]", campaignSpineController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/onramp/starter\")]", campaignSpineController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/onramp/recovery\")]", campaignSpineController, StringComparison.Ordinal);
    }

    [Fact]
    public void EditionStudioUsesNamedPublicReceiptSignedInDeskAndTypedEditionHeadRoutes()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string accountsControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");
        string campaignSpineControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "CampaignSpineController.cs");

        string controller = File.ReadAllText(controllerPath);
        string accountsController = File.ReadAllText(accountsControllerPath);
        string campaignSpineController = File.ReadAllText(campaignSpineControllerPath);

        Assert.Contains("[HttpGet(\"/edition-studio\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/edition-studio/receipts/ruleset-heads.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/edition-studio/packets/{packetId}.md\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/edition-studio/packets/{packetId}.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("BuildEditionStudioPageModel", controller, StringComparison.Ordinal);
        Assert.Contains("BuildEditionStudioReceipt", controller, StringComparison.Ordinal);
        Assert.Contains("IsKnownEditionStudioPacketId", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/edition-studio\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/edition-studio/open\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/edition-studio/{edition}\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/edition-studio/heads\")]", campaignSpineController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/edition-studio/heads/{edition}\")]", campaignSpineController, StringComparison.Ordinal);
    }

    [Fact]
    public void LocalCoProcessorUsesNamedPublicReceiptSignedInDeskAndTypedPolicyRoutes()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string accountsControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "AccountsController.cs");
        string campaignSpineControllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "CampaignSpineController.cs");

        string controller = File.ReadAllText(controllerPath);
        string accountsController = File.ReadAllText(accountsControllerPath);
        string campaignSpineController = File.ReadAllText(campaignSpineControllerPath);

        Assert.Contains("[HttpGet(\"/local-co-processor\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/roadmap/local-co-processor\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/local-co-processor/receipts/optional-acceleration.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/local-co-processor/packets/{packetId}.md\")]", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/local-co-processor/packets/{packetId}.json\")]", controller, StringComparison.Ordinal);
        Assert.Contains("LOCAL CO-PROCESSOR now ships a bounded first-party optional-acceleration lane", controller, StringComparison.Ordinal);
        Assert.Contains("IsKnownLocalCoProcessorPacketId", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/local-co-processor\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/local-co-processor/open\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/account/local-co-processor/{profile}\")]", accountsController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/local-co-processor/capabilities\")]", campaignSpineController, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"me/local-co-processor/policy\")]", campaignSpineController, StringComparison.Ordinal);
    }
}
