using Xunit;

namespace Chummer.Tests;

public sealed class PublicSignalOperationsViewTests
{
    [Fact]
    public void FeedbackKeepsHostedOperationsOffThePublicPage()
    {
        string feedbackViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Feedback.cshtml");
        string feedbackView = File.ReadAllText(feedbackViewPath);

        Assert.Contains("Public feedback should start in one place", feedbackView, StringComparison.Ordinal);
        Assert.DoesNotContain("var signalOperations = Model.SignalOperations;", feedbackView, StringComparison.Ordinal);
        Assert.DoesNotContain("_PublicSignalOperationsPacket", feedbackView, StringComparison.Ordinal);
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
        Assert.Contains("Open private support", partial, StringComparison.Ordinal);
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
        Assert.Contains("Download item details", detailView, StringComparison.Ordinal);
        Assert.Contains("Download activity summary", detailView, StringComparison.Ordinal);
        Assert.Contains("Activity summary", detailView, StringComparison.Ordinal);
        Assert.Contains("Activity", detailView, StringComparison.Ordinal);
        Assert.Contains("Original item", detailView, StringComparison.Ordinal);
        Assert.Contains("Saved filters", detailView, StringComparison.Ordinal);
        Assert.Contains("Current filter", detailView, StringComparison.Ordinal);
        Assert.Contains("Open filter details", detailView, StringComparison.Ordinal);
        Assert.Contains("Download message details", detailView, StringComparison.Ordinal);
        Assert.Contains("Download related details", detailView, StringComparison.Ordinal);
        Assert.Contains("Open thread details", detailView, StringComparison.Ordinal);
        Assert.Contains("Open related details", detailView, StringComparison.Ordinal);
        Assert.Contains("SourceDetailActionLabel", detailView, StringComparison.Ordinal);
        Assert.Contains("sourceReceipt.HotFilterLabel", detailView, StringComparison.Ordinal);
        Assert.Contains("receipt.SourceHotFilterLabel", detailView, StringComparison.Ordinal);
        Assert.Contains("receipt.SourceHotFilterSummary", detailView, StringComparison.Ordinal);
        Assert.Contains("detail.DetailKindLabel", detailView, StringComparison.Ordinal);
        Assert.Contains("detail.FilterLabel", detailView, StringComparison.Ordinal);
        Assert.Contains("savedPivots", detailView, StringComparison.Ordinal);
        Assert.Contains("Search another item", detailView, StringComparison.Ordinal);
        Assert.Contains("PublicFeedbackText(sourceReceipt.StatusLabel)", detailView, StringComparison.Ordinal);
        Assert.Contains("PublicFeedbackText(receipt.RouteKind)", detailView, StringComparison.Ordinal);
        Assert.Contains("Resolution @PublicFeedbackText(receipt.DeliveryState)", detailView, StringComparison.Ordinal);
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
        Assert.DoesNotContain("Download item data", detailView, StringComparison.Ordinal);
        Assert.DoesNotContain("Download thread data", detailView, StringComparison.Ordinal);
        Assert.DoesNotContain("Download related data", detailView, StringComparison.Ordinal);
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
        Assert.Contains("Open lookup data", lookupView, StringComparison.Ordinal);
        Assert.Contains("Lookup results", lookupView, StringComparison.Ordinal);
        Assert.Contains("Items and threads", lookupView, StringComparison.Ordinal);
        Assert.Contains("Context filter:", lookupView, StringComparison.Ordinal);
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
        Assert.Contains("SignalOperations: signalOperations", controller, StringComparison.Ordinal);
        Assert.Contains("[HttpPost(\"/feedback/providers/productlift/webhook\")]", controller, StringComparison.Ordinal);
        Assert.Contains("ReceiveProductLiftWebhook", controller, StringComparison.Ordinal);
        Assert.Contains("PublicSignalOperationsService.WebhookSecretHeader", controller, StringComparison.Ordinal);
        Assert.Contains("_signalOperations.RecordWebhook(payload)", controller, StringComparison.Ordinal);
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
}
