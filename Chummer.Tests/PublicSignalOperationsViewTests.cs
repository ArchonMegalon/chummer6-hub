using Xunit;

namespace Chummer.Tests;

public sealed class PublicSignalOperationsViewTests
{
    [Fact]
    public void FeedbackCarriesTheHostedPromotionAndTaxonomyPacket()
    {
        string feedbackViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "Feedback.cshtml");
        string feedbackView = File.ReadAllText(feedbackViewPath);

        Assert.Contains("var signalOperations = Model.SignalOperations;", feedbackView, StringComparison.Ordinal);
        Assert.Contains("@await Html.PartialAsync(\"~/Views/Shared/_PublicSignalOperationsPacket.cshtml\", signalOperations)", feedbackView, StringComparison.Ordinal);
    }

    [Fact]
    public void SharedOperationsPartialSurfacesHostedReadinessWebhookAndRoutingBoard()
    {
        string partialPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "Shared", "_PublicSignalOperationsPacket.cshtml");
        string partial = File.ReadAllText(partialPath);

        Assert.Contains("@model PublicSignalOperationsPacketViewModel", partial, StringComparison.Ordinal);
        Assert.Contains("Hosted route promotion", partial, StringComparison.Ordinal);
        Assert.Contains("Ingress and closeout", partial, StringComparison.Ordinal);
        Assert.Contains("Category routing", partial, StringComparison.Ordinal);
        Assert.Contains("Provider receipts", partial, StringComparison.Ordinal);
        Assert.Contains("Routing receipts", partial, StringComparison.Ordinal);
        Assert.Contains("Closeout follow-up", partial, StringComparison.Ordinal);
        Assert.Contains("Routing board", partial, StringComparison.Ordinal);
        Assert.Contains("Inspect hosted route", partial, StringComparison.Ordinal);
        Assert.Contains("Outbound delivery", partial, StringComparison.Ordinal);
        Assert.Contains("Journey writeback", partial, StringComparison.Ordinal);
        Assert.Contains("Replay and backfill", partial, StringComparison.Ordinal);
        Assert.Contains("Delivery recovery", partial, StringComparison.Ordinal);
        Assert.Contains("Provider outcome callbacks", partial, StringComparison.Ordinal);
        Assert.Contains("Recipient closeout threads", partial, StringComparison.Ordinal);
        Assert.Contains("Provider-auth ingress", partial, StringComparison.Ordinal);
        Assert.Contains("Open thread detail", partial, StringComparison.Ordinal);
        Assert.Contains("Open source detail", partial, StringComparison.Ordinal);
        Assert.Contains("Operator lookup", partial, StringComparison.Ordinal);
        Assert.Contains("Open bounded lookup", partial, StringComparison.Ordinal);
        Assert.Contains("Browse recent drilldowns", partial, StringComparison.Ordinal);
        Assert.Contains("Model.RecipientProjectionStatusLabel", partial, StringComparison.Ordinal);
        Assert.Contains("Model.ProjectedRecipientCount", partial, StringComparison.Ordinal);
        Assert.Contains("Model.ProjectionSourceRef", partial, StringComparison.Ordinal);
        Assert.Contains("Model.ConsentSourceRef", partial, StringComparison.Ordinal);
        Assert.Contains("Model.QueueStatusLabel", partial, StringComparison.Ordinal);
        Assert.Contains("Model.GovernorStatusLabel", partial, StringComparison.Ordinal);
        Assert.Contains("Model.ReleaseProofStatusLabel", partial, StringComparison.Ordinal);
        Assert.Contains("Model.ReleaseProofRoute", partial, StringComparison.Ordinal);
        Assert.Contains("Open follow settings", partial, StringComparison.Ordinal);
        Assert.Contains("receipt.DeliveryState", partial, StringComparison.Ordinal);
        Assert.Contains("receipt.TemplateId", partial, StringComparison.Ordinal);
        Assert.Contains("receipt.ConsentSourceRef", partial, StringComparison.Ordinal);
        Assert.Contains("Outbox candidates", partial, StringComparison.Ordinal);
        Assert.Contains("receipt.DispatchTool", partial, StringComparison.Ordinal);
        Assert.Contains("receipt.DispatchAction", partial, StringComparison.Ordinal);
        Assert.Contains("receipt.JourneyEventKey", partial, StringComparison.Ordinal);
        Assert.Contains("Model.CloseoutDispatchSentCount", partial, StringComparison.Ordinal);
        Assert.Contains("Model.JourneyReceiptCount", partial, StringComparison.Ordinal);
        Assert.Contains("Model.ReplayCandidateCount", partial, StringComparison.Ordinal);
        Assert.Contains("Model.ReconcileRunCount", partial, StringComparison.Ordinal);
        Assert.Contains("Model.DeliveryRecoveryCandidateCount", partial, StringComparison.Ordinal);
        Assert.Contains("Model.SuppressedDispatchCount", partial, StringComparison.Ordinal);
        Assert.Contains("Model.DeliveryOutcomeReceiptCount", partial, StringComparison.Ordinal);
        Assert.Contains("Model.AutomaticRetryPendingCount", partial, StringComparison.Ordinal);
        Assert.Contains("Model.RetryExpiryCandidateCount", partial, StringComparison.Ordinal);
        Assert.Contains("Model.RetryExpiryRunCount", partial, StringComparison.Ordinal);
        Assert.Contains("recentRetryExpiryRuns", partial, StringComparison.Ordinal);
        Assert.Contains("deliveryOutcomeIngresses", partial, StringComparison.Ordinal);
        Assert.Contains("recentDeliveryOutcomes", partial, StringComparison.Ordinal);
        Assert.Contains("recentRecipientThreads", partial, StringComparison.Ordinal);
        Assert.Contains("ResolveDispatchContextFilterKey", partial, StringComparison.Ordinal);
        Assert.Contains("ResolveThreadContextFilterKey", partial, StringComparison.Ordinal);
        Assert.Contains("ResolveOutcomeContextFilterKey", partial, StringComparison.Ordinal);
        Assert.Contains("ThreadDetailHref", partial, StringComparison.Ordinal);
        Assert.Contains("SourceDetailHref", partial, StringComparison.Ordinal);
        Assert.Contains("receipt.HotFilterLabel", partial, StringComparison.Ordinal);
        Assert.Contains("receipt.HotFilterSummary", partial, StringComparison.Ordinal);
        Assert.Contains("thread.QueueStatusLabel", partial, StringComparison.Ordinal);
        Assert.Contains("thread.DispatchStatusLabel", partial, StringComparison.Ordinal);
        Assert.Contains("thread.OutcomeIdentityMatchMode", partial, StringComparison.Ordinal);
        Assert.Contains("thread.JourneyEventKey", partial, StringComparison.Ordinal);
        Assert.Contains("receipt.ProviderState", partial, StringComparison.Ordinal);
        Assert.Contains("receipt.ProviderMessageId", partial, StringComparison.Ordinal);
        Assert.Contains("receipt.IdentityMatchMode", partial, StringComparison.Ordinal);
        Assert.Contains("receipt.AddressHash", partial, StringComparison.Ordinal);
        Assert.Contains("receipt.GovernorDecisionRef", partial, StringComparison.Ordinal);
        Assert.Contains("receipt.LastRecoveryStatus", partial, StringComparison.Ordinal);
        Assert.Contains("receipt.LastProviderState", partial, StringComparison.Ordinal);
        Assert.Contains("receipt.NextAutomaticRetryAtUtc", partial, StringComparison.Ordinal);
        Assert.Contains("receipt.LastOutcomeAtUtc", partial, StringComparison.Ordinal);
        Assert.Contains("run.RunReceiptId", partial, StringComparison.Ordinal);
        Assert.Contains("No public send claim", partial, StringComparison.Ordinal);
        Assert.Contains("No public journey claim", partial, StringComparison.Ordinal);
        Assert.Contains("No public outcome claim", partial, StringComparison.Ordinal);
        Assert.Contains("Ready for Hub outbox", partial, StringComparison.Ordinal);
        Assert.Contains("Automatic retry expiry", partial, StringComparison.Ordinal);
        Assert.Contains("No public send claim", partial, StringComparison.Ordinal);
        Assert.Contains("Recipient projection pending", partial, StringComparison.Ordinal);
        Assert.Contains("No public delivery claim", partial, StringComparison.Ordinal);
    }

    [Fact]
    public void DrilldownViewSurfacesDetailArtifactsAndBoundedTimelineSections()
    {
        string detailViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "FeedbackOperationsDetail.cshtml");
        string detailView = File.ReadAllText(detailViewPath);

        Assert.Contains("@model PublicSignalOperationsDetailPageViewModel", detailView, StringComparison.Ordinal);
        Assert.Contains("Open detail artifact", detailView, StringComparison.Ordinal);
        Assert.Contains("Open aggregate artifact", detailView, StringComparison.Ordinal);
        Assert.Contains("Recipient threads", detailView, StringComparison.Ordinal);
        Assert.Contains("Dispatch receipts", detailView, StringComparison.Ordinal);
        Assert.Contains("Provider callbacks", detailView, StringComparison.Ordinal);
        Assert.Contains("Journey writeback", detailView, StringComparison.Ordinal);
        Assert.Contains("Saved pivots", detailView, StringComparison.Ordinal);
        Assert.Contains("Current filter", detailView, StringComparison.Ordinal);
        Assert.Contains("Open pivot artifact", detailView, StringComparison.Ordinal);
        Assert.Contains("Open thread artifact", detailView, StringComparison.Ordinal);
        Assert.Contains("Open source artifact", detailView, StringComparison.Ordinal);
        Assert.Contains("Open thread drilldown", detailView, StringComparison.Ordinal);
        Assert.Contains("Open source drilldown", detailView, StringComparison.Ordinal);
        Assert.Contains("detail.DetailKindLabel", detailView, StringComparison.Ordinal);
        Assert.Contains("detail.FilterLabel", detailView, StringComparison.Ordinal);
        Assert.Contains("detail.SavedPivots", detailView, StringComparison.Ordinal);
        Assert.Contains("Search another bounded drilldown", detailView, StringComparison.Ordinal);
    }

    [Fact]
    public void LookupViewSurfacesSearchControlsAndBoundedResults()
    {
        string lookupViewPath = RepoPaths.FromRoot("Chummer.Run.Api", "Views", "PublicLanding", "FeedbackOperationsLookup.cshtml");
        string lookupView = File.ReadAllText(lookupViewPath);

        Assert.Contains("@model PublicSignalOperationsLookupPageViewModel", lookupView, StringComparison.Ordinal);
        Assert.Contains("Open bounded lookup", lookupView, StringComparison.Ordinal);
        Assert.Contains("Open lookup artifact", lookupView, StringComparison.Ordinal);
        Assert.Contains("Lookup results", lookupView, StringComparison.Ordinal);
        Assert.Contains("Sources and threads", lookupView, StringComparison.Ordinal);
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
        Assert.Contains("string FilterLabel", viewModels, StringComparison.Ordinal);
        Assert.Contains("string FilterKey", viewModels, StringComparison.Ordinal);
        Assert.Contains("IReadOnlyList<PublicSignalOperationsDetailPivotViewModel> SavedPivots", viewModels, StringComparison.Ordinal);
        Assert.Contains("string IdentityMatchMode", viewModels, StringComparison.Ordinal);
        Assert.Contains("PublicSignalReconcileRunReceiptViewModel", viewModels, StringComparison.Ordinal);
        Assert.Contains("services.AddSingleton<PublicSignalOperationsService>();", serviceCollection, StringComparison.Ordinal);
        Assert.Contains("services.AddHostedService<PublicSignalRetryExpiryWorker>();", serviceCollection, StringComparison.Ordinal);
    }
}
