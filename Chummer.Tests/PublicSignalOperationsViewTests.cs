using Xunit;
using Chummer.Run.Api.Controllers;
using System.Reflection;

namespace Chummer.Tests;

public sealed class PublicSignalOperationsViewTests
{
    [Fact]
    public void FeedbackKeepsHostedOperationsOffThePublicPage()
    {
        string feedbackViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Feedback.cshtml");
        string participateViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Partizipate.cshtml");

        Assert.False(File.Exists(feedbackViewPath));
        string participateView = File.ReadAllText(participateViewPath);

        Assert.Contains("partizipate-board", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("participate-hosted__frame", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("First-party page", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("var signalOperations = Model.SignalOperations;", participateView, StringComparison.Ordinal);
        Assert.DoesNotContain("_PublicSignalOperationsPacket", participateView, StringComparison.Ordinal);
    }

    [Fact]
    public void SharedOperationsPartialSurfacesHostedReadinessWebhookAndSortingBoard()
    {
        string partialPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_PublicSignalOperationsPacket.cshtml");
        string partial = File.ReadAllText(partialPath);

        Assert.Contains("@model PublicSignalOperationsPacketViewModel", partial, StringComparison.Ordinal);
        Assert.Contains("Public loop status", partial, StringComparison.Ordinal);
        Assert.Contains("Keep signal, planning, shipped updates, and private help on separate pages.", partial, StringComparison.Ordinal);
        Assert.Contains("Feedback sorting", partial, StringComparison.Ordinal);
        Assert.Contains("Public feedback stays easy to sort.", partial, StringComparison.Ordinal);
        Assert.Contains("Open roadmap", partial, StringComparison.Ordinal);
        Assert.Contains("Open changelog", partial, StringComparison.Ordinal);
        Assert.Contains("Open Help", partial, StringComparison.Ordinal);
        Assert.Contains("Public feedback", partial, StringComparison.Ordinal);
        Assert.Contains("Chummer follow-up is not visible here yet.", partial, StringComparison.Ordinal);
        Assert.Contains("Model.CategoryCount", partial, StringComparison.Ordinal);
        Assert.Contains("Model.MisrouteLikelyCount", partial, StringComparison.Ordinal);
        Assert.Contains("Model.CloseoutDispatchSentCount", partial, StringComparison.Ordinal);
        Assert.Contains("Model.CloseoutQueueReadyCount", partial, StringComparison.Ordinal);
        Assert.Contains("Model.JourneyReceiptCount", partial, StringComparison.Ordinal);
    }

    [Fact]
    public void DetailViewSurfacesFeedbackActivityWithoutInternalCloseoutCopy()
    {
        string detailViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "FeedbackOperationsDetail.cshtml");
        string detailView = File.ReadAllText(detailViewPath);

        Assert.Contains("@model PublicSignalOperationsDetailPageViewModel", detailView, StringComparison.Ordinal);
        Assert.Contains("surface-participate surface-minimal", detailView, StringComparison.Ordinal);
        Assert.Contains("Download details", detailView, StringComparison.Ordinal);
        Assert.Contains("Download summary", detailView, StringComparison.Ordinal);
        Assert.Contains("aria-label=\"Overview\"", detailView, StringComparison.Ordinal);
        Assert.Contains("Activity", detailView, StringComparison.Ordinal);
        Assert.Contains("Original update", detailView, StringComparison.Ordinal);
        Assert.Contains("Saved views", detailView, StringComparison.Ordinal);
        Assert.Contains("Current view", detailView, StringComparison.Ordinal);
        Assert.Contains("Open details", detailView, StringComparison.Ordinal);
        Assert.Contains("The first update anchors this page.", detailView, StringComparison.Ordinal);
        Assert.Contains("Open related details", detailView, StringComparison.Ordinal);
        Assert.Contains("SourceDetailActionLabel", detailView, StringComparison.Ordinal);
        Assert.Contains("sourceReceipt.HotFilterLabel", detailView, StringComparison.Ordinal);
        Assert.Contains("receipt.SourceHotFilterLabel", detailView, StringComparison.Ordinal);
        Assert.Contains("receipt.SourceHotFilterSummary", detailView, StringComparison.Ordinal);
        Assert.Contains("detail.DetailKindLabel", detailView, StringComparison.Ordinal);
        Assert.Contains("detail.FilterLabel", detailView, StringComparison.Ordinal);
        Assert.Contains("savedPivots", detailView, StringComparison.Ordinal);
        Assert.Contains("Find another update", detailView, StringComparison.Ordinal);
        Assert.Contains("PublicFeedbackText(sourceReceipt.StatusLabel)", detailView, StringComparison.Ordinal);
        Assert.Contains("PublicFeedbackText(receipt.RouteKind)", detailView, StringComparison.Ordinal);
        Assert.Contains("Delivery · @PublicFeedbackText(receipt.DeliveryState)", detailView, StringComparison.Ordinal);
        Assert.Contains("Message update · @PublicFeedbackText(receipt.DeliveryState)", detailView, StringComparison.Ordinal);
        Assert.Contains("PublicFeedbackText(receipt.QueueLane)", detailView, StringComparison.Ordinal);
        Assert.Contains("PublicFeedbackText(receipt.ProviderState)", detailView, StringComparison.Ordinal);
        Assert.Contains("PublicFeedbackText(receipt.IdentityMatchMode)", detailView, StringComparison.Ordinal);
        Assert.Contains("PublicFeedbackText(thread.QueueStatusLabel)", detailView, StringComparison.Ordinal);
        Assert.DoesNotContain("<h3>Closeout", detailView, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("support boundary", detailView, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("closeout eligibility", detailView, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("closeout status", detailView, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("queue status stay clear", detailView, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("No public outcome claim", detailView, StringComparison.Ordinal);
        Assert.DoesNotContain("Drilldown summary", detailView, StringComparison.Ordinal);
        Assert.DoesNotContain("Download item JSON", detailView, StringComparison.Ordinal);
        Assert.DoesNotContain("Download message JSON", detailView, StringComparison.Ordinal);
        Assert.DoesNotContain("Open filter JSON", detailView, StringComparison.Ordinal);
    }

    [Fact]
    public void LookupViewSurfacesSearchControlsAndPrivateFeedbackResults()
    {
        string lookupViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "FeedbackOperationsLookup.cshtml");
        string lookupView = File.ReadAllText(lookupViewPath);

        Assert.Contains("@model PublicSignalOperationsLookupPageViewModel", lookupView, StringComparison.Ordinal);
        Assert.Contains("Search feedback", lookupView, StringComparison.Ordinal);
        Assert.Contains("Private details stay private", lookupView, StringComparison.Ordinal);
        Assert.DoesNotContain("bounded", lookupView, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Open JSON", lookupView, StringComparison.Ordinal);
        Assert.Contains("Results", lookupView, StringComparison.Ordinal);
        Assert.Contains("Items and threads", lookupView, StringComparison.Ordinal);
        Assert.Contains("Filter:", lookupView, StringComparison.Ordinal);
        Assert.Contains("result.FilterKey", lookupView, StringComparison.Ordinal);
        Assert.Contains("result.FilterLabel", lookupView, StringComparison.Ordinal);
        Assert.Contains("result.MatchReason", lookupView, StringComparison.Ordinal);
    }

    [Fact]
    public void ControllerAndParticipateModelCarryOptionalOperationsPacket()
    {
        string controllerPath = RepoPaths.FromRoot("Chummer.Run.Api", "Controllers", "PublicLandingController.cs");
        string viewModelPath = RepoPaths.FromRoot("Chummer.Run.Api", "ViewModels", "SiteViewModels.cs");
        string serviceCollectionPath = RepoPaths.FromRoot("Chummer.Run.Api", "ServiceCollectionBoundedContextExtensions.cs");

        string controller = File.ReadAllText(controllerPath);
        string viewModels = File.ReadAllText(viewModelPath);
        string serviceCollection = File.ReadAllText(serviceCollectionPath);

        Assert.Contains("private readonly PublicSignalOperationsService _signalOperations;", controller, StringComparison.Ordinal);
        Assert.Contains("BuildOptionalSignalOperationsPacket()", controller, StringComparison.Ordinal);
        Assert.Contains("ResolveProductLiftHostedBoardHref()", controller, StringComparison.Ordinal);
        Assert.Contains("ResolveProductLiftHostedBoardUri()", controller, StringComparison.Ordinal);
        Assert.Contains("ResolveParticipateBoardHomeHref()", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/participate/board\")]", controller, StringComparison.Ordinal);
        Assert.Contains("ParticipateBoardProxy", controller, StringComparison.Ordinal);
        Assert.Contains("RewriteParticipateBoardHtml", controller, StringComparison.Ordinal);
        Assert.Contains("data-chummer-home-link-patch", controller, StringComparison.Ordinal);
        Assert.Contains("brand.setAttribute('href', '__CHUMMER_PUBLIC_HOME_HREF__')", controller, StringComparison.Ordinal);
        Assert.Contains("brand.setAttribute('target', '_top')", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"/feedback/providers/productlift/webhook\")]", controller, StringComparison.Ordinal);
        Assert.Contains("ReceiveProductLiftWebhook", controller, StringComparison.Ordinal);
        Assert.Contains("PublicSignalOperationsService.WebhookSecretHeader", controller, StringComparison.Ordinal);
        Assert.Contains("_signalOperations.RecordWebhook(payload)", controller, StringComparison.Ordinal);
        Assert.DoesNotContain("string.Equals(suppliedSecret, configuredSecret, StringComparison.Ordinal)", controller, StringComparison.Ordinal);
        Assert.Contains("FixedTimeEquals(suppliedSecret.Trim(), configuredSecret)", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/feedback/operations\")]", controller, StringComparison.Ordinal);
        Assert.Contains("FeedbackOperationsArtifact()", controller, StringComparison.Ordinal);
        Assert.Contains("_signalOperations.LoadArtifactJson()", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/feedback/operations/lookup\")]", controller, StringComparison.Ordinal);
        Assert.Contains("FeedbackOperationsLookupPage", controller, StringComparison.Ordinal);
        Assert.Contains("_signalOperations.BuildLookup(q, scope)", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/api/v1/public/feedback/operations/lookup\")]", controller, StringComparison.Ordinal);
        Assert.Contains("_signalOperations.LoadLookupJson(q, scope)", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/feedback/operations/source/{sourceReceiptId}\")]", controller, StringComparison.Ordinal);
        Assert.Contains("FeedbackOperationsSourceDetailPage", controller, StringComparison.Ordinal);
        Assert.Contains("_signalOperations.BuildSourceReceiptDetail(sourceReceiptId, filter)", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/api/v1/public/feedback/operations/source/{sourceReceiptId}\")]", controller, StringComparison.Ordinal);
        Assert.Contains("_signalOperations.LoadSourceReceiptDetailJson(sourceReceiptId, filter)", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/feedback/operations/thread/{dispatchReceiptId}\")]", controller, StringComparison.Ordinal);
        Assert.Contains("FeedbackOperationsThreadDetailPage", controller, StringComparison.Ordinal);
        Assert.Contains("_signalOperations.BuildRecipientThreadDetail(dispatchReceiptId, filter)", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpGet(\"/api/v1/public/feedback/operations/thread/{dispatchReceiptId}\")]", controller, StringComparison.Ordinal);
        Assert.Contains("_signalOperations.LoadRecipientThreadDetailJson(dispatchReceiptId, filter)", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"/feedback/operations/reconcile\")]", controller, StringComparison.Ordinal);
        Assert.Contains("ReconcileFeedbackOperations()", controller, StringComparison.Ordinal);
        Assert.Contains("PublicSignalOperationsService.OperationsSecretHeader", controller, StringComparison.Ordinal);
        Assert.Contains("_signalOperations.ReconcilePendingCloseouts()", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"/feedback/operations/recover\")]", controller, StringComparison.Ordinal);
        Assert.Contains("RecoverFeedbackOperations()", controller, StringComparison.Ordinal);
        Assert.Contains("_signalOperations.RecoverDispatchOutcomes()", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"/feedback/providers/delivery/outcome\")]", controller, StringComparison.Ordinal);
        Assert.Contains("ReceiveDeliveryOutcome", controller, StringComparison.Ordinal);
        Assert.Contains("_signalOperations.RecordDeliveryOutcome(payload)", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"/feedback/providers/emailit/webhook\")]", controller, StringComparison.Ordinal);
        Assert.Contains("ReceiveEmailitDeliveryOutcome", controller, StringComparison.Ordinal);
        Assert.Contains("PublicSignalOperationsService.EmailitWebhookSecretHeader", controller, StringComparison.Ordinal);
        Assert.Contains("_signalOperations.RecordDeliveryOutcome(\"emailit\", payload)", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"/feedback/providers/ea/delivery/webhook\")]", controller, StringComparison.Ordinal);
        Assert.Contains("ReceiveEaDeliveryOutcome", controller, StringComparison.Ordinal);
        Assert.Contains("PublicSignalOperationsService.EaDeliveryWebhookSecretHeader", controller, StringComparison.Ordinal);
        Assert.Contains("_signalOperations.RecordDeliveryOutcome(\"ea\", payload)", controller, StringComparison.Ordinal);
        Assert.Contains("PublicSignalOperationsPacketViewModel? SignalOperations = null", viewModels, StringComparison.Ordinal);
        Assert.Contains("PublicSignalDeliveryOutcomeIngressViewModel", viewModels, StringComparison.Ordinal);
        Assert.Contains("PublicSignalWebhookReceiptViewModel", viewModels, StringComparison.Ordinal);
        Assert.Contains("PublicSignalRoutingReceiptViewModel", viewModels, StringComparison.Ordinal);
        Assert.Contains("PublicSignalCloseoutDeliveryReceiptViewModel", viewModels, StringComparison.Ordinal);
        Assert.Contains("PublicSignalCloseoutQueueReceiptViewModel", viewModels, StringComparison.Ordinal);
        Assert.Contains("PublicSignalCloseoutDispatchReceiptViewModel", viewModels, StringComparison.Ordinal);
        Assert.Contains("PublicSignalJourneyReceiptViewModel", viewModels, StringComparison.Ordinal);
        Assert.Contains("PublicSignalDeliveryOutcomeReceiptViewModel", viewModels, StringComparison.Ordinal);
        Assert.Contains("PublicSignalRecipientThreadViewModel", viewModels, StringComparison.Ordinal);
        Assert.Contains("PublicSignalOperationsDetailViewModel", viewModels, StringComparison.Ordinal);
        Assert.Contains("PublicSignalOperationsDetailPivotViewModel", viewModels, StringComparison.Ordinal);
        Assert.Contains("PublicSignalOperationsDetailPageViewModel", viewModels, StringComparison.Ordinal);
        Assert.Contains("PublicSignalOperationsLookupResultViewModel", viewModels, StringComparison.Ordinal);
        Assert.Contains("PublicSignalOperationsLookupViewModel", viewModels, StringComparison.Ordinal);
        Assert.Contains("PublicSignalOperationsLookupPageViewModel", viewModels, StringComparison.Ordinal);
        Assert.Contains("string ArtifactHref", viewModels, StringComparison.Ordinal);
        Assert.Contains("string HotFilterKey", viewModels, StringComparison.Ordinal);
        Assert.Contains("string HotFilterSummary", viewModels, StringComparison.Ordinal);
        Assert.Contains("string SourceHotFilterKey", viewModels, StringComparison.Ordinal);
        Assert.Contains("string SourceHotFilterSummary", viewModels, StringComparison.Ordinal);
        Assert.Contains("string FilterLabel", viewModels, StringComparison.Ordinal);
        Assert.Contains("string FilterKey", viewModels, StringComparison.Ordinal);
        Assert.Contains("IReadOnlyList<PublicSignalOperationsDetailPivotViewModel> SavedPivots", viewModels, StringComparison.Ordinal);
        Assert.Contains("string IdentityMatchMode", viewModels, StringComparison.Ordinal);
        Assert.Contains("PublicSignalReconcileRunReceiptViewModel", viewModels, StringComparison.Ordinal);
        Assert.Contains("services.AddSingleton<PublicSignalOperationsService>();", serviceCollection, StringComparison.Ordinal);
        Assert.Contains("services.AddHostedService<PublicSignalRetryExpiryWorker>();", serviceCollection, StringComparison.Ordinal);
    }

    [Fact]
    public void ParticipateBoardHtmlRewriteInjectsHomeLinkPatchAndKeepsBoardLocal()
    {
        MethodInfo? method = typeof(PublicLandingController).GetMethod(
            "RewriteParticipateBoardHtml",
            BindingFlags.Static | BindingFlags.NonPublic);

        Assert.NotNull(method);

        const string html = """
<!doctype html>
<html>
<head><title>Board</title></head>
<link rel="preload" href="https://media.productlift.dev/branding-stylesheets/theme.css" as="style">
<script src="https://cdn.productlift.dev/js/all.js"></script>
<body>
  <header>
    <a class="brand-link" href="/">Chummer</a>
    <a href="https://app.productlift.dev/login">Log in</a>
    <a href="https://app.productlift.dev/signup">Sign up</a>
  </header>
  <main>
    <a href="/roadmap">Roadmap</a>
    <img src="/assets/poster.png" alt="Poster" />
  </main>
</body>
</html>
""";

        string rewritten = (string)method!.Invoke(
            null,
            [html, new Uri("https://chummer6.productlift.dev/feedback"), "https://chummer.run/", "/account/billing/supporter/start"])!;

        Assert.Contains("<base href=\"/participate/board/\" />", rewritten, StringComparison.Ordinal);
        Assert.Contains("href=\"/participate/board/roadmap\"", rewritten, StringComparison.Ordinal);
        Assert.Contains("src=\"/participate/board/assets/poster.png\"", rewritten, StringComparison.Ordinal);
        Assert.Contains("https://media.productlift.dev/branding-stylesheets/theme.css", rewritten, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("https://cdn.productlift.dev/js/all.js", rewritten, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("https://media.chummer", rewritten, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("https://cdn.chummer", rewritten, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("data-chummer-home-link-patch", rewritten, StringComparison.Ordinal);
        Assert.Contains("data-chummer-board-failure-patch", rewritten, StringComparison.Ordinal);
        Assert.Contains("polishVisibleCopy", rewritten, StringComparison.Ordinal);
        Assert.Contains(@"\bAI-powered\b", rewritten, StringComparison.Ordinal);
        Assert.Contains(@"\bAutomatically generate\b", rewritten, StringComparison.Ordinal);
        Assert.Contains("something went wrong on our side", rewritten, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("could not load posts", rewritten, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("network error while loading tab configuration", rewritten, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("data-chummer-board-failure", rewritten, StringComparison.Ordinal);
        Assert.Contains("The board is unavailable", rewritten, StringComparison.Ordinal);
        Assert.Contains("Try again shortly.", rewritten, StringComparison.Ordinal);
        Assert.DoesNotContain("data-chummer-board-rail", rewritten, StringComparison.Ordinal);
        Assert.DoesNotContain("href=\"/account/billing/supporter/start\"", rewritten, StringComparison.Ordinal);
        Assert.DoesNotContain("Support Chummer", rewritten, StringComparison.Ordinal);
        Assert.Contains("node.style.display = 'none';", rewritten, StringComparison.Ordinal);
        Assert.Contains("new MutationObserver", rewritten, StringComparison.Ordinal);
        Assert.Contains("removeHostedAuth", rewritten, StringComparison.Ordinal);
        Assert.Contains("authObserver.observe(document.documentElement", rewritten, StringComparison.Ordinal);
        Assert.Contains("node.remove()", rewritten, StringComparison.Ordinal);
        Assert.Contains("brand.setAttribute('href', 'https://chummer.run/')", rewritten, StringComparison.Ordinal);
        Assert.DoesNotContain("support@productlift.dev", rewritten, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(">ProductLift<", rewritten, StringComparison.OrdinalIgnoreCase);
        Assert.Contains(">Chummer</a>", rewritten, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("productlift.dev/login", rewritten, StringComparison.Ordinal);
        Assert.DoesNotContain("productlift.dev/signup", rewritten, StringComparison.Ordinal);
        Assert.DoesNotContain(">Log in</a>", rewritten, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain(">Sign up</a>", rewritten, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("menubar_login", rewritten, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("menubar_signup", rewritten, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("Powered by ProductLift", rewritten, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("name=\"generator\"", rewritten, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("brand.setAttribute('target', '_top')", rewritten, StringComparison.Ordinal);
    }

    [Fact]
    public void ParticipateBoardHtmlRewriteSkipsSupporterLinkWhenBillingUnavailable()
    {
        MethodInfo? method = typeof(PublicLandingController).GetMethod(
            "RewriteParticipateBoardHtml",
            BindingFlags.Static | BindingFlags.NonPublic);

        Assert.NotNull(method);

        const string html = """
<!doctype html>
<html>
<head><title>Board</title></head>
<body><main>board</main></body>
</html>
""";

        string rewritten = (string)method!.Invoke(
            null,
            [html, new Uri("https://chummer6.productlift.dev/feedback"), "https://chummer.run/", null])!;

        Assert.DoesNotContain("href=\"/account/billing/supporter/start\"", rewritten, StringComparison.Ordinal);
        Assert.DoesNotContain("Support Chummer", rewritten, StringComparison.Ordinal);
        Assert.DoesNotContain("Requests, votes, and shipped work.", rewritten, StringComparison.Ordinal);
    }
}
