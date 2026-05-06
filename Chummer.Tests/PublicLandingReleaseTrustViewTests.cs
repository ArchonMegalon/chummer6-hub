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
    public void LandingViewProjectsCanonStartTrustAndRoleSectionsInsteadOfStoppingAtHeroAndReleaseProof()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Landing.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("Section(\"start_here\")", view, StringComparison.Ordinal);
        Assert.Contains("Section(\"why_trust_it\")", view, StringComparison.Ordinal);
        Assert.Contains("Section(\"choose_your_lane\")", view, StringComparison.Ordinal);
        Assert.Contains("Model.TrustPillars", view, StringComparison.Ordinal);
        Assert.Contains("Model.Lanes", view, StringComparison.Ordinal);
        Assert.Contains("workflow-band", view, StringComparison.Ordinal);
        Assert.Contains("trust-claims", view, StringComparison.Ordinal);
        Assert.Contains("route-choice-grid", view, StringComparison.Ordinal);
        Assert.Contains("PublicSurfaceStatus.AudienceLabel", view, StringComparison.Ordinal);
        Assert.Contains("hero-installrail", view, StringComparison.Ordinal);
        Assert.Contains("continuity-band", view, StringComparison.Ordinal);
        Assert.Contains("future-strip", view, StringComparison.Ordinal);
        Assert.Contains("Model.FlagshipCoverage", view, StringComparison.Ordinal);
        Assert.Contains("Whole-product frontier", view, StringComparison.Ordinal);
        Assert.Contains("Hub truth, mobile continuity, and shared flagship polish stay visible together.", view, StringComparison.Ordinal);
        Assert.Contains("Account-aware install handoff", view, StringComparison.Ordinal);
        Assert.Contains("Devices and access", view, StringComparison.Ordinal);
    }

    [Fact]
    public void DownloadsViewKeepsMainPlatformShelfVisibleBeforeAdvancedAccordion()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Downloads.cshtml");
        string view = File.ReadAllText(viewPath);

        int platformShelfIndex = view.IndexOf("id=\"platform-shelf\"", StringComparison.Ordinal);
        int advancedAccordionIndex = view.IndexOf("id=\"advanced-downloads\"", StringComparison.Ordinal);

        Assert.Contains("Main platform downloads", view, StringComparison.Ordinal);
        Assert.Contains("Windows verification and support rail", view, StringComparison.Ordinal);
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
        Assert.Contains("Guest or link this copy", view, StringComparison.Ordinal);
        Assert.Contains("Devices and access stay calm", view, StringComparison.Ordinal);
        Assert.Contains("The install shelf stays tied to the rest of the product.", view, StringComparison.Ordinal);
        Assert.Contains("downloads-hub-and-registry", view, StringComparison.Ordinal);
        Assert.Contains("downloads-mobile-play-shell", view, StringComparison.Ordinal);
        Assert.Contains("downloads-ui-kit-and-flagship-polish", view, StringComparison.Ordinal);
    }

    [Fact]
    public void DownloadDispatchFallbackKeepsReleaseProofAndRecoveryTrustOnSameRail()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "DownloadDispatch.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("href=\"/now\">What works today</a>", view, StringComparison.Ordinal);
        Assert.Contains("@Model.HelpLabel", view, StringComparison.Ordinal);
        Assert.Contains("Status, known issues, and install help stay on one release rail so recovery never depends on stale page copy.", view, StringComparison.Ordinal);
    }

    [Fact]
    public void ParticipatePagePromotesCodexAuthorizationThroughOpenAiAccountFlow()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Participate.cshtml");
        string consoleViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "CodexParticipation", "Console.cshtml");
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "CodexParticipationController.cs");

        string view = File.ReadAllText(viewPath);
        string consoleView = File.ReadAllText(consoleViewPath);
        string controller = File.ReadAllText(controllerPath);

        Assert.Contains("Authorize Codex access", view, StringComparison.Ordinal);
        Assert.Contains("/auth/google/start?next=%2Fparticipate%2Fcodex", view, StringComparison.Ordinal);
        Assert.Contains("OpenAI account in ChatGPT", view, StringComparison.Ordinal);
        Assert.Contains("OpenAI account in ChatGPT", consoleView, StringComparison.Ordinal);
        Assert.Contains("authorize with your OpenAI account in ChatGPT", controller, StringComparison.Ordinal);
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
        Assert.DoesNotContain("Redirect(\"/horizons?productlift=roadmap#productlift-roadmap-projection\")", controller, StringComparison.Ordinal);
        Assert.Contains("route-anchor-target", feedbackView, StringComparison.Ordinal);
        Assert.Contains("route-anchor-target", roadmapView, StringComparison.Ordinal);
        Assert.Contains("route-anchor-target", changelogView, StringComparison.Ordinal);
        Assert.Contains("Public ideas, votes, and safe public bugs on one first-party signal rail", feedbackView, StringComparison.Ordinal);
        Assert.Contains("Safe public signal", feedbackView, StringComparison.Ordinal);
        Assert.Contains("Milestones and public direction on one route", roadmapView, StringComparison.Ordinal);
        Assert.Contains("Milestone ledger", roadmapView, StringComparison.Ordinal);
        Assert.Contains("Shipped closeout with user-available proof", changelogView, StringComparison.Ordinal);
        Assert.Contains("status-decision-strip", changelogView, StringComparison.Ordinal);
    }

    [Fact]
    public void ProductStoryViewFramesTablePainAndContinuityBeforeRoleTaxonomy()
    {
        string viewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "ProductStory.cshtml");
        string view = File.ReadAllText(viewPath);

        Assert.Contains("story-pain-grid", view, StringComparison.Ordinal);
        Assert.Contains("Mystery math is expensive", view, StringComparison.Ordinal);
        Assert.Contains("Campaign return should not depend on memory", view, StringComparison.Ordinal);
        Assert.Contains("Account value starts small and useful", view, StringComparison.Ordinal);
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
        Assert.Contains("data-nav-sheet", layout, StringComparison.Ordinal);
        Assert.Contains("Compact navigation", layout, StringComparison.Ordinal);
        Assert.Contains("Help and legal", layout, StringComparison.Ordinal);
        Assert.Contains("closeNavSheet", script, StringComparison.Ordinal);
        Assert.Contains("nav-sheet-open", script, StringComparison.Ordinal);
        Assert.Contains("event.key === \"Escape\"", script, StringComparison.Ordinal);
        Assert.Contains("body.nav-sheet-open", css, StringComparison.Ordinal);
        Assert.Contains(".site-nav__toggle", css, StringComparison.Ordinal);
    }

    [Fact]
    public void LayoutUsesRouteAwareBottomQuickActionsInsteadOfGenericInstallCopyEverywhere()
    {
        string layoutPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml");
        string layout = File.ReadAllText(layoutPath);

        Assert.Contains("bottomQuickAction = (\"Public signal\", \"Open Fixer Board\", \"/feedback\")", layout, StringComparison.Ordinal);
        Assert.Contains("bottomQuickAction = (\"Projected movement\", \"Open roadmap\", \"/roadmap\")", layout, StringComparison.Ordinal);
        Assert.Contains("bottomQuickAction = (\"Need help\", \"Open support\", \"/contact#support-intake\")", layout, StringComparison.Ordinal);
        Assert.Contains("bottomQuickAction = (\"Reality check\", \"Open what works today\", \"/now\")", layout, StringComparison.Ordinal);
        Assert.Contains("@bottomQuickAction.Value.Eyebrow", layout, StringComparison.Ordinal);
        Assert.Contains("@bottomQuickAction.Value.Href", layout, StringComparison.Ordinal);
    }

    [Fact]
    public void ContactSupportPageSteersSafePublicFeedbackToFixerBoardBeforePrivateIntake()
    {
        string trustViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "TrustPage.cshtml");
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");

        string trustView = File.ReadAllText(trustViewPath);
        string controller = File.ReadAllText(controllerPath);

        Assert.Contains("Safe public feedback should start on Fixer Board", trustView, StringComparison.Ordinal);
        Assert.Contains("Href: \"/feedback\"", trustView, StringComparison.Ordinal);
        Assert.Contains("Label: \"Open Fixer Board\"", trustView, StringComparison.Ordinal);
        Assert.Contains("string.Equals(Model.PageId, \"contact\"", trustView, StringComparison.Ordinal);
        Assert.Contains("Safe public feedback should start on Fixer Board. Choose this form only when the issue needs private or account-linked follow-up.", controller, StringComparison.Ordinal);
    }

    [Fact]
    public void PublicationViewsShowReviewRequiredRouteLabelsWhenDesktopProofCoverageIsMissing()
    {
        string publicationViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "PublicCreatorPublication.cshtml");
        string shelfViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Shelf.cshtml");

        string publicationView = File.ReadAllText(publicationViewPath);
        string shelfView = File.ReadAllText(shelfViewPath);

        Assert.Contains("Model.TrustPulse?.MissingDesktopClientCoverage == true", publicationView, StringComparison.Ordinal);
        Assert.Contains("Review-required route", publicationView, StringComparison.Ordinal);
        Assert.Contains("_PublicTrustPulsePanel.cshtml", publicationView, StringComparison.Ordinal);
        Assert.Contains("Model.TrustPulse?.MissingDesktopClientCoverage == true", shelfView, StringComparison.Ordinal);
        Assert.Contains("Review-required route", shelfView, StringComparison.Ordinal);
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
    public void LayoutFooterSurfacesCanonSourceProjectionAndTruthBoundary()
    {
        string layoutPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml");
        string cssPath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "css", "site.css");

        string layout = File.ReadAllText(layoutPath);
        string css = File.ReadAllText(cssPath);

        Assert.Contains("@chrome.FooterCanonicalSource", layout, StringComparison.Ordinal);
        Assert.Contains("@chrome.FooterGeneratedNote", layout, StringComparison.Ordinal);
        Assert.Contains("First-party truth stays on <a class=\"quiet-link\" href=\"/now\">what works today</a> and <a class=\"quiet-link\" href=\"/status\">status</a>.", layout, StringComparison.Ordinal);
        Assert.Contains("Truth boundary", layout, StringComparison.Ordinal);
        Assert.Contains(".site-footer__meta-label", css, StringComparison.Ordinal);
        Assert.Contains(".site-footer__provenance", css, StringComparison.Ordinal);
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
        Assert.Contains("Public loop", layout, StringComparison.Ordinal);
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
        Assert.Contains("The current public signal rail lives on <code class=\"mono-receipt\">/feedback</code>", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("feedback returns here, roadmap resolves through Horizons, and shipped closeout resolves through What works today.", participateView, StringComparison.Ordinal);
        Assert.Contains("You followed a legacy roadmap handoff", horizonsView, StringComparison.Ordinal);
        Assert.Contains("The milestone-backed public roadmap now lives on <code class=\"mono-receipt\">/roadmap</code>", horizonsView, StringComparison.Ordinal);
        Assert.DoesNotContain("/participate?productlift=feedback#productlift-feedback", horizonsView, StringComparison.Ordinal);
        Assert.Contains("You followed a legacy shipped handoff", nowView, StringComparison.Ordinal);
        Assert.Contains("The dedicated shipped-closeout rail now lives on <code class=\"mono-receipt\">/changelog</code>", nowView, StringComparison.Ordinal);
        Assert.DoesNotContain("/participate?productlift=feedback#productlift-feedback", nowView, StringComparison.Ordinal);
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
    public void StickyMobileQuickActionCanBeDismissedPerRouteInSessionStorage()
    {
        string layoutPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_Layout.cshtml");
        string scriptPath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "js", "site.js");
        string cssPath = RepoPaths.FromRoot("Chummer.Run.Api", "wwwroot", "css", "site.css");

        string layout = File.ReadAllText(layoutPath);
        string script = File.ReadAllText(scriptPath);
        string css = File.ReadAllText(cssPath);

        Assert.Contains("data-bottom-cta-key=\"@routeKey\"", layout, StringComparison.Ordinal);
        Assert.Contains("data-bottom-cta-dismiss", layout, StringComparison.Ordinal);
        Assert.Contains("chummer.bottom_cta.dismissed_routes", script, StringComparison.Ordinal);
        Assert.Contains("window.sessionStorage.setItem", script, StringComparison.Ordinal);
        Assert.Contains("bottomCta.hidden = true", script, StringComparison.Ordinal);
        Assert.Contains(".site-bottom-cta__dismiss", css, StringComparison.Ordinal);
    }
}
