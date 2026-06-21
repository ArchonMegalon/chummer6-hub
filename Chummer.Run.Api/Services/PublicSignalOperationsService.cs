using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Net.Http.Json;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;
using Chummer.Run.Contracts.Community;
using Microsoft.Extensions.Logging;
using System.Net.Http.Headers;
using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace Chummer.Run.Api.Services;

public sealed class PublicSignalOperationsService
{
    private const string TaxonomyRelativePath = "products/chummer/PUBLIC_FEEDBACK_TAXONOMY.yaml";
    private const string OutboundRegistryRelativePath = "products/chummer/OUTBOUND_NOTIFICATION_TEMPLATE_REGISTRY.yaml";
    private const string WebhookSecretConfigKey = "CHUMMER_PRODUCTLIFT_WEBHOOK_SECRET";
    private const string WebhookSecretHeaderName = "X-ProductLift-Webhook-Secret";
    private const string EmailitWebhookSecretConfigKey = "CHUMMER_PRODUCTLIFT_EMAILIT_WEBHOOK_SECRET";
    private const string EmailitWebhookSecretHeaderName = "X-Emailit-Webhook-Secret";
    private const string EaDeliveryWebhookSecretConfigKey = "CHUMMER_PRODUCTLIFT_EA_DELIVERY_WEBHOOK_SECRET";
    private const string EaDeliveryWebhookSecretHeaderName = "X-Chummer-EA-Webhook-Secret";
    private const string OperationsSecretConfigKey = "CHUMMER_PRODUCTLIFT_OPERATIONS_SECRET";
    private const string OperationsSecretHeaderName = "X-Chummer-Operations-Secret";
    private const string ProductLiftCloseoutEmailEnabledConfigKey = "CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAIL_ENABLED";
    private const string ProductLiftCloseoutEmailApiKeyConfigKey = "CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_API_KEY";
    private const string ProductLiftCloseoutEaApiTokenConfigKey = "CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_API_TOKEN";
    private const string ProductLiftCloseoutEaPrincipalIdConfigKey = "CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_PRINCIPAL_ID";
    private const string ProductLiftCloseoutEaBindingIdConfigKey = "CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BINDING_ID";
    private const string ProductLiftCloseoutEaBaseUrlConfigKey = "CHUMMER_PRODUCTLIFT_CLOSEOUT_EA_BASE_URL";
    private const string ProductLiftCloseoutEmailitBaseUrlConfigKey = "CHUMMER_PRODUCTLIFT_CLOSEOUT_EMAILIT_BASE_URL";
    private const string ProductLiftCloseoutPublicBaseUrlConfigKey = "CHUMMER_PRODUCTLIFT_CLOSEOUT_PUBLIC_BASE_URL";
    private const string ProductLiftCloseoutFromEmailConfigKey = "CHUMMER_PRODUCTLIFT_CLOSEOUT_FROM_EMAIL";
    private const string ProductLiftCloseoutFromNameConfigKey = "CHUMMER_PRODUCTLIFT_CLOSEOUT_FROM_NAME";
    private const string ProductLiftCloseoutReplyToConfigKey = "CHUMMER_PRODUCTLIFT_CLOSEOUT_REPLY_TO";
    private const string ProductLiftCloseoutGovernorApprovedConfigKey = "CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_APPROVED";
    private const string ProductLiftCloseoutGovernorDecisionRefConfigKey = "CHUMMER_PRODUCTLIFT_CLOSEOUT_GOVERNOR_DECISION_REF";
    private const string ProductLiftCloseoutRecipientProjectionEnabledConfigKey = "CHUMMER_PRODUCTLIFT_CLOSEOUT_RECIPIENT_PROJECTION_ENABLED";
    private const string ProductLiftCloseoutProjectionOwnerConfigKey = "CHUMMER_PRODUCTLIFT_CLOSEOUT_PROJECTION_OWNER";
    private const string ProductLiftCloseoutConsentBasisConfigKey = "CHUMMER_PRODUCTLIFT_CLOSEOUT_CONSENT_BASIS";
    private const string ProductLiftCloseoutFollowSettingsPathConfigKey = "CHUMMER_PRODUCTLIFT_CLOSEOUT_FOLLOW_SETTINGS_PATH";
    private const string DefaultEaBaseUrl = "http://127.0.0.1:8090";
    private const string DefaultEmailitBaseUrl = "https://api.emailit.com/v2";
    private const string DefaultPublicBaseUrl = "https://chummer.run";
    private const string DefaultFromEmail = "wageslave@chummer.run";
    private const string DefaultFromName = "Wageslave";
    private const string DefaultReplyTo = "support@chummer.run";
    private const string ExpectedProjectionOwner = "chummer6-hub";
    private const string DefaultFollowSettingsPath = "/account/participation";
    private const string DefaultProjectionSourceRef = "hub_follow_horizons:verified_email";
    private const string DefaultConsentSourceRef = "hub_preferences:follow_horizons";
    private const string DefaultGovernorDecisionSourceRef = "product_governor";
    private const string CloseoutProofRoute = "/changelog";
    private const string ConnectorDispatchToolName = "connector.dispatch";
    private const string ConnectorDispatchActionName = "delivery.send";
    private const string VoterNotifiedJourneyEventKey = "voter_notified";
    private const string EmailChannel = "email";
    private const string EmailitProvider = "emailit";
    private const string ProductLiftCloseoutTemplateId = "productlift_voter_shipped";
    private const string ProductLiftCloseoutTemplateVersion = "1";
    private const int MaxStoredReceipts = 200;
    private static readonly string[] ProductLiftRoutePaths = ["/feedback", "/roadmap", "/changelog"];
    private static readonly string[] PublicWebhookRoutes =
    [
        "/feedback/providers/productlift/webhook",
        "/api/v1/public/feedback/providers/productlift/webhook"
    ];
    private static readonly string[] PublicReconcileRoutes =
    [
        "/feedback/operations/reconcile",
        "/api/v1/public/feedback/operations/reconcile"
    ];
    private static readonly string[] PublicRecoveryRoutes =
    [
        "/feedback/operations/recover",
        "/api/v1/public/feedback/operations/recover"
    ];
    private static readonly string[] PublicDeliveryOutcomeRoutes =
    [
        "/feedback/providers/delivery/outcome",
        "/api/v1/public/feedback/providers/delivery/outcome"
    ];
    private static readonly string[] PublicEmailitDeliveryOutcomeRoutes =
    [
        "/feedback/providers/emailit/webhook",
        "/api/v1/public/feedback/providers/emailit/webhook"
    ];
    private static readonly string[] PublicEaDeliveryOutcomeRoutes =
    [
        "/feedback/providers/ea/delivery/webhook",
        "/api/v1/public/feedback/providers/ea/delivery/webhook"
    ];
    private static readonly IDeserializer Deserializer = new DeserializerBuilder()
        .WithNamingConvention(UnderscoredNamingConvention.Instance)
        .IgnoreUnmatchedProperties()
        .Build();
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    private readonly PublicCanonFileLoader _canon;
    private readonly IConfiguration _configuration;
    private readonly CommunityStore _communityStore;
    private readonly LocalReleaseProofArtifactService _localReleaseProof;
    private readonly IHttpClientFactory? _httpClientFactory;
    private readonly ILogger<PublicSignalOperationsService> _logger;
    private readonly string _storagePath;
    private readonly object _gate = new();
    private readonly List<ProductLiftWebhookReceiptState> _receipts = [];
    private readonly Dictionary<string, string> _receiptIdByDedupKey = new(StringComparer.OrdinalIgnoreCase);
    private readonly List<ProductLiftRoutingReceiptState> _routingReceipts = [];
    private readonly Dictionary<string, string> _routingReceiptIdByDedupKey = new(StringComparer.OrdinalIgnoreCase);
    private readonly List<ProductLiftCloseoutDeliveryReceiptState> _closeoutReceipts = [];
    private readonly Dictionary<string, string> _closeoutReceiptIdByDedupKey = new(StringComparer.OrdinalIgnoreCase);
    private readonly List<ProductLiftCloseoutDispatchReceiptState> _dispatchReceipts = [];
    private readonly Dictionary<string, string> _dispatchReceiptIdByDedupKey = new(StringComparer.OrdinalIgnoreCase);
    private readonly List<ProductLiftJourneyReceiptState> _journeyReceipts = [];
    private readonly Dictionary<string, string> _journeyReceiptIdByDedupKey = new(StringComparer.OrdinalIgnoreCase);
    private readonly List<ProductLiftDeliveryOutcomeReceiptState> _deliveryOutcomeReceipts = [];
    private readonly Dictionary<string, string> _deliveryOutcomeReceiptIdByDedupKey = new(StringComparer.OrdinalIgnoreCase);
    private readonly List<ProductLiftReconcileRunReceiptState> _reconcileRuns = [];

    public PublicSignalOperationsService(
        PublicCanonFileLoader canon,
        IConfiguration configuration,
        CommunityStore communityStore,
        ILogger<PublicSignalOperationsService> logger,
        IHttpClientFactory? httpClientFactory = null)
    {
        _canon = canon;
        _configuration = configuration;
        _communityStore = communityStore;
        _localReleaseProof = new LocalReleaseProofArtifactService(configuration);
        _httpClientFactory = httpClientFactory;
        _logger = logger;
        _storagePath = ResolveStoragePath(configuration);
        Load();
    }

    public PublicSignalOperationsPacketViewModel BuildPacket()
    {
        OperationsCanonDocument canonDocument = LoadOperationsCanon();
        CloseoutRuntimeReadiness readiness = BuildCloseoutRuntimeReadiness();
        CloseoutQueueSnapshot queueSnapshot = BuildQueueSnapshot(canonDocument, readiness);
        DispatchReceiptSnapshot dispatchSnapshot = BuildDispatchSnapshot();
        JourneyReceiptSnapshot journeySnapshot = BuildJourneySnapshot();
        DeliveryOutcomeSnapshot outcomeSnapshot = BuildDeliveryOutcomeSnapshot();
        RecipientThreadSnapshot recipientThreadSnapshot = BuildRecipientThreadSnapshot(canonDocument, readiness);
        ReconcileRunSnapshot reconcileSnapshot = BuildReconcileSnapshot(canonDocument, readiness);
        DispatchRecoverySnapshot recoverySnapshot = BuildDispatchRecoverySnapshot();
        RetryExpirySweepSnapshot retryExpirySnapshot = BuildRetryExpirySweepSnapshot();
        var deliveryOutcomeIngresses = BuildDeliveryOutcomeIngresses();
        var hostedRoutes = BuildHostedRoutes();
        var configuredHostedRoutes = hostedRoutes.Where(static route => !string.IsNullOrWhiteSpace(route.HostedHref)).ToArray();
        bool hostedProjectionReady = configuredHostedRoutes.Length == ProductLiftRoutePaths.Length
            && configuredHostedRoutes.All(static route => string.Equals(route.StatusLabel, "Configured", StringComparison.Ordinal));
        string hostedDomainLabel = ResolveHostedDomainLabel(configuredHostedRoutes);
        string hostedProjectionSummary = BuildHostedProjectionSummary(hostedRoutes, hostedProjectionReady, hostedDomainLabel);
        WebhookReceiptSnapshot receiptSnapshot = BuildReceiptSnapshot();
        bool webhookConfigured = !string.IsNullOrWhiteSpace(_configuration[WebhookSecretConfigKey]);

        var categories = (canonDocument.Taxonomy.Categories ?? new List<PublicFeedbackCategoryDocument>())
            .Select(BuildCategory)
            .ToArray();
        int misrouteLikelyCount = categories.Count(static category => category.SupportMisrouteLikely);
        int privacySensitiveCount = categories.Count(static category => category.PrivacySensitive);

        return new PublicSignalOperationsPacketViewModel(
            Eyebrow: "Hosted promotion seam",
            Heading: "Promotion, webhook intake, and category routing stay explicit before the hosted board becomes default.",
            Summary: "The public signal lane remains first-party until the hosted board split, receipt intake, and closeout follow-up path are configured on this instance. Taxonomy still comes from Chummer-owned canon either way.",
            HostedDomainLabel: hostedDomainLabel,
            HostedProjectionSummary: hostedProjectionSummary,
            HostedProjectionReady: hostedProjectionReady,
            WebhookStatusLabel: ResolveWebhookStatusLabel(webhookConfigured, receiptSnapshot.ReceiptCount),
            WebhookSummary: BuildWebhookSummary(webhookConfigured, receiptSnapshot),
            VoterCloseoutStatusLabel: canonDocument.CloseoutFamilyReady ? "Closeout mail canonized" : "Closeout mail pending",
            VoterCloseoutSummary: canonDocument.CloseoutFamilyReady
                ? "The outbound notification registry already reserves a Chummer-owned product feedback closeout family, so voter follow-up can stay first-party even after hosted-board promotion."
                : "Voter closeout remains blocked until a Chummer-owned outbound notification family exists for hosted-board shipped follow-up.",
            RecipientProjectionOwner: readiness.ProjectionOwner,
            FollowSettingsPath: readiness.FollowSettingsPath,
            RecipientProjectionStatusLabel: readiness.ProjectionStatusLabel,
            RecipientProjectionSummary: readiness.ProjectionSummary,
            ProjectionSourceRef: readiness.ProjectionSourceRef,
            ProjectedRecipientCount: readiness.ProjectedRecipientCount,
            ConsentStatusLabel: readiness.ConsentStatusLabel,
            ConsentSummary: readiness.ConsentSummary,
            ConsentSourceRef: readiness.ConsentSourceRef,
            QueueStatusLabel: readiness.QueueStatusLabel,
            QueueSummary: readiness.QueueSummary,
            GovernorStatusLabel: readiness.GovernorStatusLabel,
            GovernorSummary: readiness.GovernorSummary,
            GovernorDecisionRef: readiness.GovernorDecisionRef,
            ReleaseProofStatusLabel: readiness.ReleaseProofStatusLabel,
            ReleaseProofSummary: readiness.ReleaseProofSummary,
            ReleaseProofRoute: readiness.ReleaseProofRoute,
            ReleaseProofReceiptId: readiness.ReleaseProofReceiptId,
            ReceiptCount: receiptSnapshot.ReceiptCount,
            CloseoutReceiptCount: receiptSnapshot.CloseoutReceiptCount,
            LastReceiptAtUtc: receiptSnapshot.LastReceiptAtUtc,
            RoutingReceiptCount: receiptSnapshot.RoutingReceiptCount,
            ModerationReceiptCount: receiptSnapshot.ModerationReceiptCount,
            CloseoutDeliveryReceiptCount: receiptSnapshot.CloseoutDeliveryReceiptCount,
            CloseoutDeliveryCandidateCount: receiptSnapshot.CloseoutDeliveryCandidateCount,
            CloseoutQueueReceiptCount: queueSnapshot.ReceiptCount,
            CloseoutQueueReadyCount: queueSnapshot.ReadyCount,
            CloseoutDispatchReceiptCount: dispatchSnapshot.ReceiptCount,
            CloseoutDispatchSentCount: dispatchSnapshot.SentCount,
            JourneyReceiptCount: journeySnapshot.ReceiptCount,
            DeliveryOutcomeReceiptCount: outcomeSnapshot.ReceiptCount,
            AutomaticRetryPendingCount: outcomeSnapshot.AutomaticRetryPendingCount,
            LastDeliveryOutcomeAtUtc: outcomeSnapshot.LastReceiptAtUtc,
            ReplayCandidateCount: reconcileSnapshot.ReplayCandidateCount,
            ReconcileRunCount: reconcileSnapshot.RunCount,
            LastReconcileAtUtc: reconcileSnapshot.LastRunAtUtc,
            DeliveryRecoveryCandidateCount: recoverySnapshot.RecoveryCandidateCount,
            SuppressedDispatchCount: recoverySnapshot.SuppressedDispatchCount,
            DeliveryRecoveryRunCount: recoverySnapshot.RunCount,
            LastDeliveryRecoveryAtUtc: recoverySnapshot.LastRunAtUtc,
            RetryExpiryCandidateCount: retryExpirySnapshot.CandidateCount,
            RetryExpiryRunCount: retryExpirySnapshot.RunCount,
            LastRetryExpiryAtUtc: retryExpirySnapshot.LastRunAtUtc,
            CategoryCount: categories.Length,
            MisrouteLikelyCount: misrouteLikelyCount,
            PrivacySensitiveCount: privacySensitiveCount,
            HostedRoutes: hostedRoutes,
            DeliveryOutcomeIngresses: deliveryOutcomeIngresses,
            Categories: categories,
            RecentReceipts: receiptSnapshot.RecentReceipts,
            RecentRoutingReceipts: receiptSnapshot.RecentRoutingReceipts,
            RecentCloseoutReceipts: receiptSnapshot.RecentCloseoutReceipts,
            RecentQueueReceipts: queueSnapshot.RecentReceipts,
            RecentDispatchReceipts: dispatchSnapshot.RecentReceipts,
            RecentJourneyReceipts: journeySnapshot.RecentReceipts,
            RecentDeliveryOutcomes: outcomeSnapshot.RecentReceipts,
            RecentRecipientThreads: recipientThreadSnapshot.RecentThreads,
            RecentReconcileRuns: reconcileSnapshot.RecentRuns,
            RecentRecoveryRuns: recoverySnapshot.RecentRuns,
            RecentRetryExpiryRuns: retryExpirySnapshot.RecentRuns,
            Rules: (canonDocument.Taxonomy.Rules ?? new List<string>())
                .Where(static item => !string.IsNullOrWhiteSpace(item))
                .ToArray());
    }

    public PublicSignalOperationsDetailViewModel? BuildSourceReceiptDetail(string sourceReceiptId, string? filter = null)
    {
        string? normalizedSourceReceiptId = NormalizeOptional(sourceReceiptId);
        if (normalizedSourceReceiptId is null)
        {
            return null;
        }

        string normalizedFilter = NormalizeDetailFilter(filter);
        OperationsCanonDocument canonDocument = LoadOperationsCanon();
        CloseoutRuntimeReadiness readiness = BuildCloseoutRuntimeReadiness();

        lock (_gate)
        {
            ProductLiftWebhookReceiptState? sourceReceipt = _receipts
                .FirstOrDefault(receipt => string.Equals(receipt.ReceiptId, normalizedSourceReceiptId, StringComparison.OrdinalIgnoreCase));
            if (sourceReceipt is null)
            {
                return null;
            }

            ProductLiftCloseoutDispatchReceiptState[] dispatchStates = _dispatchReceipts
                .Where(receipt => string.Equals(receipt.SourceReceiptId, normalizedSourceReceiptId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(GetRecipientThreadLastTouchedAtUtc)
                .ToArray();
            HashSet<string> dispatchReceiptIds = dispatchStates
                .Select(static receipt => receipt.ReceiptId)
                .ToHashSet(StringComparer.OrdinalIgnoreCase);
            HashSet<string> dispatchReceiptIdsWithOutcomes = _deliveryOutcomeReceipts
                .Where(receipt => dispatchReceiptIds.Contains(receipt.DispatchReceiptId))
                .Select(static receipt => receipt.DispatchReceiptId)
                .ToHashSet(StringComparer.OrdinalIgnoreCase);
            ProductLiftCloseoutDispatchReceiptState[] filteredDispatchStates = dispatchStates
                .Where(receipt => MatchesDetailFilter(
                    receipt,
                    dispatchReceiptIdsWithOutcomes.Contains(receipt.ReceiptId),
                    normalizedFilter))
                .ToArray();
            HashSet<string> filteredDispatchReceiptIds = filteredDispatchStates
                .Select(static receipt => receipt.ReceiptId)
                .ToHashSet(StringComparer.OrdinalIgnoreCase);
            HashSet<string> filteredJourneyScopeKeys = filteredDispatchStates
                .Select(static receipt => BuildJourneyScopeKey(receipt.GovernorDecisionRef, receipt.ReleaseProofReceiptId))
                .ToHashSet(StringComparer.OrdinalIgnoreCase);
            string sourceDetailBaseHref = $"/feedback/operations/source/{Uri.EscapeDataString(sourceReceipt.ReceiptId)}";
            string sourceDetailArtifactBaseHref = $"/api/v1/public/feedback/operations/source/{Uri.EscapeDataString(sourceReceipt.ReceiptId)}";
            PublicSignalOperationsDetailPivotViewModel[] savedPivots = BuildDetailPivots(
                dispatchStates,
                dispatchReceiptIdsWithOutcomes,
                sourceDetailBaseHref,
                sourceDetailArtifactBaseHref,
                normalizedFilter);

            PublicSignalRoutingReceiptViewModel[] routingReceipts = _routingReceipts
                .Where(receipt => string.Equals(receipt.SourceReceiptId, normalizedSourceReceiptId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .Select(BuildRoutingReceiptViewModel)
                .ToArray();
            PublicSignalCloseoutDeliveryReceiptViewModel[] closeoutReceipts = _closeoutReceipts
                .Where(receipt => string.Equals(receipt.SourceReceiptId, normalizedSourceReceiptId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .Select(BuildCloseoutDeliveryReceiptViewModel)
                .ToArray();
            PublicSignalCloseoutQueueReceiptViewModel[] queueReceipts = sourceReceipt.CloseoutCandidate
                ? [BuildCloseoutQueueReceipt(sourceReceipt, canonDocument, readiness)]
                : Array.Empty<PublicSignalCloseoutQueueReceiptViewModel>();
            PublicSignalRecipientThreadViewModel[] recipientThreads = filteredDispatchStates
                .Select(receipt => BuildRecipientThread(receipt, canonDocument, readiness))
                .ToArray();
            PublicSignalCloseoutDispatchReceiptViewModel[] dispatchReceipts = filteredDispatchStates
                .Select(BuildDispatchReceiptViewModel)
                .ToArray();
            PublicSignalDeliveryOutcomeReceiptViewModel[] deliveryOutcomes = _deliveryOutcomeReceipts
                .Where(receipt =>
                    string.Equals(receipt.SourceReceiptId, normalizedSourceReceiptId, StringComparison.OrdinalIgnoreCase)
                    && filteredDispatchReceiptIds.Contains(receipt.DispatchReceiptId))
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .Select(BuildDeliveryOutcomeReceiptViewModel)
                .ToArray();
            PublicSignalJourneyReceiptViewModel[] journeyReceipts = _journeyReceipts
                .Where(receipt =>
                    string.Equals(receipt.SourceReceiptId, normalizedSourceReceiptId, StringComparison.OrdinalIgnoreCase)
                    && filteredJourneyScopeKeys.Contains(BuildJourneyScopeKey(receipt.GovernorDecisionRef, receipt.ReleaseProofReceiptId)))
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .Select(BuildJourneyReceiptViewModel)
                .ToArray();
            string summary = BuildSourceReceiptDetailSummary(sourceReceipt, recipientThreads.Length, deliveryOutcomes.Length, journeyReceipts.Length);
            if (!string.Equals(normalizedFilter, "all", StringComparison.Ordinal))
            {
                summary = $"Showing {recipientThreads.Length} of {dispatchStates.Length} {ResolveDetailFilterLabel(normalizedFilter).ToLowerInvariant()}. {summary}";
            }

            return new PublicSignalOperationsDetailViewModel(
                DetailKindLabel: "Source record drilldown",
                DetailKeyLabel: "Source record",
                DetailKey: sourceReceipt.ReceiptId,
                Eyebrow: "Feedback operations detail",
                Heading: $"{NormalizeOptional(sourceReceipt.ItemReference) ?? sourceReceipt.ReceiptId} source record",
                Summary: summary,
                FilterKey: normalizedFilter,
                FilterLabel: ResolveDetailFilterLabel(normalizedFilter),
                FilterApplied: !string.Equals(normalizedFilter, "all", StringComparison.Ordinal),
                BackHref: "/feedback",
                BackLabel: "Back to feedback",
                AggregateArtifactHref: "/feedback/operations",
                DetailArtifactHref: AppendDetailFilter(sourceDetailArtifactBaseHref, normalizedFilter),
                RelatedHref: null,
                RelatedLabel: null,
                SavedPivots: savedPivots,
                SourceReceipt: BuildWebhookReceiptViewModel(sourceReceipt),
                RoutingReceipts: routingReceipts,
                CloseoutReceipts: closeoutReceipts,
                QueueReceipts: queueReceipts,
                RecipientThreads: recipientThreads,
                DispatchReceipts: dispatchReceipts,
                DeliveryOutcomes: deliveryOutcomes,
                JourneyReceipts: journeyReceipts);
        }
    }

    public PublicSignalOperationsDetailViewModel? BuildRecipientThreadDetail(string dispatchReceiptId, string? filter = null)
    {
        string? normalizedDispatchReceiptId = NormalizeOptional(dispatchReceiptId);
        if (normalizedDispatchReceiptId is null)
        {
            return null;
        }

        string normalizedFilter = NormalizeDetailFilter(filter);
        OperationsCanonDocument canonDocument = LoadOperationsCanon();
        CloseoutRuntimeReadiness readiness = BuildCloseoutRuntimeReadiness();

        lock (_gate)
        {
            ProductLiftCloseoutDispatchReceiptState? dispatchReceipt = _dispatchReceipts
                .FirstOrDefault(receipt => string.Equals(receipt.ReceiptId, normalizedDispatchReceiptId, StringComparison.OrdinalIgnoreCase));
            if (dispatchReceipt is null)
            {
                return null;
            }

            ProductLiftCloseoutDispatchReceiptState[] siblingDispatchStates = _dispatchReceipts
                .Where(receipt => string.Equals(receipt.SourceReceiptId, dispatchReceipt.SourceReceiptId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(GetRecipientThreadLastTouchedAtUtc)
                .ToArray();
            HashSet<string> siblingDispatchReceiptIds = siblingDispatchStates
                .Select(static receipt => receipt.ReceiptId)
                .ToHashSet(StringComparer.OrdinalIgnoreCase);
            HashSet<string> siblingDispatchReceiptIdsWithOutcomes = _deliveryOutcomeReceipts
                .Where(receipt => siblingDispatchReceiptIds.Contains(receipt.DispatchReceiptId))
                .Select(static receipt => receipt.DispatchReceiptId)
                .ToHashSet(StringComparer.OrdinalIgnoreCase);
            ProductLiftWebhookReceiptState? sourceReceipt = _receipts
                .FirstOrDefault(receipt => string.Equals(receipt.ReceiptId, dispatchReceipt.SourceReceiptId, StringComparison.OrdinalIgnoreCase));
            SourceHotFilterSummary sourceHotFilter = ResolveSourceHotFilter(dispatchReceipt.SourceReceiptId);
            string sourceDetailBaseHref = $"/feedback/operations/source/{Uri.EscapeDataString(dispatchReceipt.SourceReceiptId)}";
            string threadDetailArtifactBaseHref = $"/api/v1/public/feedback/operations/thread/{Uri.EscapeDataString(dispatchReceipt.ReceiptId)}";
            PublicSignalOperationsDetailPivotViewModel[] savedPivots = BuildDetailPivots(
                siblingDispatchStates,
                siblingDispatchReceiptIdsWithOutcomes,
                sourceDetailBaseHref,
                $"/api/v1/public/feedback/operations/source/{Uri.EscapeDataString(dispatchReceipt.SourceReceiptId)}",
                normalizedFilter);
            PublicSignalWebhookReceiptViewModel? sourceView = sourceReceipt is null ? null : BuildWebhookReceiptViewModel(sourceReceipt);
            PublicSignalRoutingReceiptViewModel[] routingReceipts = sourceReceipt is null
                ? Array.Empty<PublicSignalRoutingReceiptViewModel>()
                : _routingReceipts
                    .Where(receipt => string.Equals(receipt.SourceReceiptId, dispatchReceipt.SourceReceiptId, StringComparison.OrdinalIgnoreCase))
                    .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                    .Select(BuildRoutingReceiptViewModel)
                    .ToArray();
            PublicSignalCloseoutDeliveryReceiptViewModel[] closeoutReceipts = sourceReceipt is null
                ? Array.Empty<PublicSignalCloseoutDeliveryReceiptViewModel>()
                : _closeoutReceipts
                    .Where(receipt => string.Equals(receipt.SourceReceiptId, dispatchReceipt.SourceReceiptId, StringComparison.OrdinalIgnoreCase))
                    .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                    .Select(BuildCloseoutDeliveryReceiptViewModel)
                    .ToArray();
            PublicSignalCloseoutQueueReceiptViewModel[] queueReceipts = sourceReceipt is not null && sourceReceipt.CloseoutCandidate
                ? [BuildCloseoutQueueReceipt(sourceReceipt, canonDocument, readiness)]
                : Array.Empty<PublicSignalCloseoutQueueReceiptViewModel>();
            PublicSignalRecipientThreadViewModel thread = BuildRecipientThread(dispatchReceipt, canonDocument, readiness);
            PublicSignalDeliveryOutcomeReceiptViewModel[] deliveryOutcomes = _deliveryOutcomeReceipts
                .Where(receipt => string.Equals(receipt.DispatchReceiptId, dispatchReceipt.ReceiptId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .Select(BuildDeliveryOutcomeReceiptViewModel)
                .ToArray();
            PublicSignalJourneyReceiptViewModel[] journeyReceipts = _journeyReceipts
                .Where(receipt =>
                    string.Equals(receipt.SourceReceiptId, dispatchReceipt.SourceReceiptId, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(receipt.GovernorDecisionRef, dispatchReceipt.GovernorDecisionRef, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(receipt.ReleaseProofReceiptId, dispatchReceipt.ReleaseProofReceiptId, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .Select(BuildJourneyReceiptViewModel)
                .ToArray();
            string summary = BuildRecipientThreadDetailSummary(thread, deliveryOutcomes.Length, journeyReceipts.Length);
            if (!string.Equals(normalizedFilter, "all", StringComparison.Ordinal))
            {
                summary = $"{summary} Source pivot is currently set to {ResolveDetailFilterLabel(normalizedFilter).ToLowerInvariant()}.";
            }

            return new PublicSignalOperationsDetailViewModel(
                DetailKindLabel: "Recipient thread drilldown",
                DetailKeyLabel: "Dispatch receipt",
                DetailKey: dispatchReceipt.ReceiptId,
                Eyebrow: "Feedback operations detail",
                Heading: $"{dispatchReceipt.RecipientRef} closeout thread",
                Summary: summary,
                FilterKey: normalizedFilter,
                FilterLabel: ResolveDetailFilterLabel(normalizedFilter),
                FilterApplied: !string.Equals(normalizedFilter, "all", StringComparison.Ordinal),
                BackHref: "/feedback",
                BackLabel: "Back to feedback",
                AggregateArtifactHref: "/feedback/operations",
                DetailArtifactHref: AppendDetailFilter(threadDetailArtifactBaseHref, normalizedFilter),
                RelatedHref: AppendDetailFilter(
                    sourceDetailBaseHref,
                    string.Equals(normalizedFilter, "all", StringComparison.Ordinal)
                        ? sourceHotFilter.FilterKey
                        : normalizedFilter),
                RelatedLabel: !string.Equals(normalizedFilter, "all", StringComparison.Ordinal)
                    ? "Open source drilldown with the same filter"
                    : !string.Equals(sourceHotFilter.FilterKey, "all", StringComparison.Ordinal)
                        ? $"Open {sourceHotFilter.FilterLabel.ToLowerInvariant()}"
                        : "Open source receipt drilldown",
                SavedPivots: savedPivots,
                SourceReceipt: sourceView,
                RoutingReceipts: routingReceipts,
                CloseoutReceipts: closeoutReceipts,
                QueueReceipts: queueReceipts,
                RecipientThreads: [thread],
                DispatchReceipts: [BuildDispatchReceiptViewModel(dispatchReceipt)],
                DeliveryOutcomes: deliveryOutcomes,
                JourneyReceipts: journeyReceipts);
        }
    }

    public string? LoadSourceReceiptDetailJson(string sourceReceiptId, string? filter = null)
    {
        PublicSignalOperationsDetailViewModel? detail = BuildSourceReceiptDetail(sourceReceiptId, filter);
        return detail is null
            ? null
            : JsonSerializer.Serialize(detail, JsonOptions);
    }

    public string? LoadRecipientThreadDetailJson(string dispatchReceiptId, string? filter = null)
    {
        PublicSignalOperationsDetailViewModel? detail = BuildRecipientThreadDetail(dispatchReceiptId, filter);
        return detail is null
            ? null
            : JsonSerializer.Serialize(detail, JsonOptions);
    }

    public PublicSignalOperationsLookupViewModel BuildLookup(string? query, string? scope)
    {
        string normalizedScope = NormalizeLookupScope(scope);
        string normalizedQuery = NormalizeOptional(query) ?? string.Empty;
        string[] tokens = TokenizeLookupQuery(normalizedQuery);
        bool queryProvided = tokens.Length > 0;
        OperationsCanonDocument canonDocument = LoadOperationsCanon();
        CloseoutRuntimeReadiness readiness = BuildCloseoutRuntimeReadiness();

        lock (_gate)
        {
            List<PublicSignalOperationsLookupResultViewModel> results = [];
            if (!string.Equals(normalizedScope, "thread", StringComparison.Ordinal))
            {
                results.AddRange(_receipts
                    .Select(receipt => BuildSourceLookupResult(receipt, tokens, canonDocument, readiness))
                    .Where(static result => result is not null)
                    .Cast<PublicSignalOperationsLookupResultViewModel>());
            }

            if (!string.Equals(normalizedScope, "source", StringComparison.Ordinal))
            {
                results.AddRange(_dispatchReceipts
                    .Select(receipt => BuildThreadLookupResult(receipt, tokens, canonDocument, readiness))
                    .Where(static result => result is not null)
                    .Cast<PublicSignalOperationsLookupResultViewModel>());
            }

            PublicSignalOperationsLookupResultViewModel[] ordered = results
                .OrderByDescending(static result => result.LastTouchedAtUtc)
                .ThenBy(static result => result.ResultKindLabel, StringComparer.OrdinalIgnoreCase)
                .ThenBy(static result => result.Key, StringComparer.OrdinalIgnoreCase)
                .Take(12)
                .ToArray();

            return new PublicSignalOperationsLookupViewModel(
                Query: normalizedQuery,
                Scope: normalizedScope,
                ScopeLabel: ResolveLookupScopeLabel(normalizedScope),
                QueryProvided: queryProvided,
                Eyebrow: "Activity lookup",
                Heading: queryProvided ? "Search source records and recipient threads" : "Recent source records and recipient threads",
                Summary: BuildLookupSummary(normalizedQuery, normalizedScope, queryProvided, ordered.Length),
                ResultCount: ordered.Length,
                Results: ordered);
        }
    }

    public string LoadLookupJson(string? query, string? scope)
        => JsonSerializer.Serialize(BuildLookup(query, scope), JsonOptions);

    public PublicSignalWebhookAckResponse RecordWebhook(JsonElement payload)
    {
        if (payload.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("productlift webhook payload must be a JSON object.");
        }

        OperationsCanonDocument canonDocument = LoadOperationsCanon();
        CloseoutRuntimeReadiness readiness = BuildCloseoutRuntimeReadiness();
        JsonElement envelope = ExtractEnvelope(payload);
        JsonElement item = ExtractPrimaryItem(envelope);
        string serializedPayload = JsonSerializer.Serialize(payload);
        string payloadSha256 = ComputeSha256Hex(serializedPayload);
        string providerEventId = NormalizeOptional(
                TryReadString(payload, "event_id", "eventId", "webhook_id", "id")
                ?? TryReadString(envelope, "event_id", "eventId", "webhook_id", "id"))
            ?? $"sha256:{payloadSha256[..12]}";
        string eventType = NormalizeOptional(
                TryReadString(payload, "type", "event", "action")
                ?? TryReadString(envelope, "type", "event", "action"))
            ?? "unknown";
        string boardLabel = ResolveEntityLabel(item, envelope, payload, fallback: "Unassigned board", "board", "project", "space");
        string categoryLabel = ResolveEntityLabel(item, envelope, payload, fallback: "Unclassified", "category", "bucket", "group");
        string itemReference = ResolveItemReference(item, envelope, payload, providerEventId);
        string statusLabel = ResolveStatusLabel(item, envelope, payload, eventType);
        string actionLabel = ResolveActionLabel(eventType, statusLabel);
        bool closeoutCandidate = IsCloseoutCandidate(eventType, statusLabel);
        MatchedFeedbackCategory matchedCategory = ResolveMatchedCategory(item, envelope, payload, categoryLabel, canonDocument.Taxonomy.Categories);
        bool voterNotificationAllowed = TryReadBoolean(item, "voter_notification_allowed", "notify_voters", "send_notifications", "notification_allowed")
            ?? TryReadBoolean(envelope, "voter_notification_allowed", "notify_voters", "send_notifications", "notification_allowed")
            ?? TryReadBoolean(payload, "voter_notification_allowed", "notify_voters", "send_notifications", "notification_allowed")
            ?? false;
        DateTimeOffset receivedAtUtc = DateTimeOffset.UtcNow;
        DateTimeOffset? providerOccurredAtUtc = TryReadDateTimeOffset(item, "occurred_at", "updated_at", "created_at", "timestamp")
            ?? TryReadDateTimeOffset(envelope, "occurred_at", "updated_at", "created_at", "timestamp")
            ?? TryReadDateTimeOffset(payload, "occurred_at", "updated_at", "created_at", "timestamp");
        string dedupKey = BuildDedupKey(providerEventId, eventType, itemReference, payloadSha256);
        ProductLiftWebhookReceiptState? createdReceipt = null;
        bool closeoutRecorded = false;
        PublicSignalWebhookAckResponse response;

        lock (_gate)
        {
            if (_receiptIdByDedupKey.TryGetValue(dedupKey, out string? existingReceiptId))
            {
                ProductLiftWebhookReceiptState existingReceipt = _receipts.First(receipt => string.Equals(receipt.ReceiptId, existingReceiptId, StringComparison.OrdinalIgnoreCase));
                response = new PublicSignalWebhookAckResponse(
                    Provider: "productlift",
                    Status: "duplicate",
                    Duplicate: true,
                    RecordedEvents: 0,
                    ReceiptId: existingReceiptId,
                    EventType: eventType,
                    ReceivedAtUtc: receivedAtUtc,
                    RoutingReceiptRecorded: FindRoutingReceiptCount(existingReceipt.ReceiptId) > 0,
                    CloseoutReceiptRecorded: FindCloseoutReceiptCount(existingReceipt.ReceiptId) > 0);
                return response;
            }

            ProductLiftWebhookReceiptState receipt = new(
                ReceiptId: $"plrcpt_{Guid.NewGuid():N}",
                DedupKey: dedupKey,
                ProviderEventId: providerEventId,
                EventType: eventType,
                ActionLabel: actionLabel,
                StatusLabel: statusLabel,
                BoardLabel: boardLabel,
                CategoryLabel: categoryLabel,
                ItemReference: itemReference,
                CloseoutCandidate: closeoutCandidate,
                VoterNotificationAllowed: voterNotificationAllowed,
                PayloadSha256: payloadSha256,
                ReceivedAtUtc: receivedAtUtc,
                ProviderOccurredAtUtc: providerOccurredAtUtc);

            _receipts.Add(receipt);
            _receiptIdByDedupKey[dedupKey] = receipt.ReceiptId;
            bool routingRecorded = TryAppendRoutingReceiptLocked(receipt, matchedCategory, receivedAtUtc);
            closeoutRecorded = TryAppendCloseoutReceiptLocked(receipt, matchedCategory, canonDocument, readiness, receivedAtUtc);
            TrimReceiptsLocked();
            PersistLocked();
            createdReceipt = receipt;
            response = new PublicSignalWebhookAckResponse(
                Provider: "productlift",
                Status: closeoutCandidate ? "recorded_closeout_candidate" : "recorded",
                Duplicate: false,
                RecordedEvents: 1,
                ReceiptId: receipt.ReceiptId,
                EventType: eventType,
                ReceivedAtUtc: receivedAtUtc,
                RoutingReceiptRecorded: routingRecorded,
                CloseoutReceiptRecorded: closeoutRecorded);
        }

        if (createdReceipt is not null && closeoutRecorded)
        {
            TryMaterializeCloseoutDispatch(createdReceipt, canonDocument, readiness);
        }

        return response;
    }

    public PublicSignalOperationsReconcileResponse ReconcilePendingCloseouts()
    {
        OperationsCanonDocument canonDocument = LoadOperationsCanon();
        CloseoutRuntimeReadiness readiness = BuildCloseoutRuntimeReadiness();
        List<ProductLiftWebhookReceiptState> sourceReceipts;
        lock (_gate)
        {
            sourceReceipts = _receipts
                .Where(static receipt => receipt.CloseoutCandidate)
                .OrderBy(static receipt => receipt.ReceivedAtUtc)
                .ToList();
        }

        int totalCandidates = sourceReceipts.Count;
        int readyCandidates = 0;
        int replayCandidates = 0;
        int dispatchBefore;
        int journeyBefore;
        lock (_gate)
        {
            dispatchBefore = _dispatchReceipts.Count;
            journeyBefore = _journeyReceipts.Count;
        }

        foreach (ProductLiftWebhookReceiptState sourceReceipt in sourceReceipts)
        {
            PublicSignalCloseoutQueueReceiptViewModel candidate = BuildCloseoutQueueReceipt(sourceReceipt, canonDocument, readiness);
            if (!candidate.ReadyForOutbox)
            {
                continue;
            }

            readyCandidates++;
            if (!NeedsDispatchReplay(sourceReceipt, readiness, canonDocument))
            {
                continue;
            }

            replayCandidates++;
            TryMaterializeCloseoutDispatch(sourceReceipt, canonDocument, readiness, allowCurrentAudienceFallback: false);
        }

        int dispatchAfter;
        int journeyAfter;
        lock (_gate)
        {
            dispatchAfter = _dispatchReceipts.Count;
            journeyAfter = _journeyReceipts.Count;
        }

        int dispatchCreated = Math.Max(0, dispatchAfter - dispatchBefore);
        int journeysRecorded = Math.Max(0, journeyAfter - journeyBefore);
        string status = replayCandidates == 0
            ? "noop"
            : dispatchCreated > 0 || journeysRecorded > 0
                ? "replayed"
                : "ready_without_new_receipts";
        DateTimeOffset recordedAtUtc = DateTimeOffset.UtcNow;
        ProductLiftReconcileRunReceiptState runReceipt = RecordReconcileRun(
            status,
            totalCandidates,
            readyCandidates,
            replayCandidates,
            dispatchCreated,
            journeysRecorded,
            recordedAtUtc);

        return new PublicSignalOperationsReconcileResponse(
            Provider: "productlift",
            Status: status,
            CandidateReceiptCount: totalCandidates,
            ReadyCandidateCount: readyCandidates,
            ReplayCandidateCount: replayCandidates,
            DispatchReceiptsCreated: dispatchCreated,
            JourneyReceiptsRecorded: journeysRecorded,
            RunReceiptId: runReceipt.RunReceiptId,
            RecordedAtUtc: recordedAtUtc);
    }

    public PublicSignalOperationsRecoveryResponse RecoverDispatchOutcomes()
    {
        List<DispatchRecoveryCandidate> candidates = BuildDispatchRecoveryCandidates(expiredRetryWindowOnly: false);
        int candidateCount = candidates.Count;
        int recoveredCount = 0;
        int suppressedCount = 0;
        int blockedCount = 0;

        foreach (DispatchRecoveryCandidate candidate in candidates)
        {
            DispatchRecoveryOutcome outcome = RecoverDispatchCandidate(candidate);
            switch (outcome)
            {
                case DispatchRecoveryOutcome.Recovered:
                    recoveredCount++;
                    break;
                case DispatchRecoveryOutcome.Suppressed:
                    suppressedCount++;
                    break;
                default:
                    blockedCount++;
                    break;
            }
        }

        string status = recoveredCount > 0
            ? "recovered"
            : suppressedCount > 0 && blockedCount == 0
                ? "suppressed_only"
                : candidateCount == 0
                    ? "noop"
                    : "blocked";
        DateTimeOffset recordedAtUtc = DateTimeOffset.UtcNow;
        ProductLiftReconcileRunReceiptState runReceipt = RecordDispatchRecoveryRun(
            "dispatch_recovery",
            status,
            candidateCount,
            recoveredCount,
            suppressedCount,
            blockedCount,
            recordedAtUtc);

        return new PublicSignalOperationsRecoveryResponse(
            Provider: "productlift",
            Status: status,
            CandidateReceiptCount: candidateCount,
            RecoveredReceiptCount: recoveredCount,
            SuppressedReceiptCount: suppressedCount,
            BlockedReceiptCount: blockedCount,
            RunReceiptId: runReceipt.RunReceiptId,
            RecordedAtUtc: recordedAtUtc);
    }

    public PublicSignalOperationsRecoveryResponse RecoverExpiredRetryWindows()
    {
        List<DispatchRecoveryCandidate> candidates = BuildDispatchRecoveryCandidates(expiredRetryWindowOnly: true);
        int candidateCount = candidates.Count;
        int recoveredCount = 0;
        int suppressedCount = 0;
        int blockedCount = 0;

        foreach (DispatchRecoveryCandidate candidate in candidates)
        {
            DispatchRecoveryOutcome outcome = RecoverDispatchCandidate(candidate);
            switch (outcome)
            {
                case DispatchRecoveryOutcome.Recovered:
                    recoveredCount++;
                    break;
                case DispatchRecoveryOutcome.Suppressed:
                    suppressedCount++;
                    break;
                default:
                    blockedCount++;
                    break;
            }
        }

        string status = recoveredCount > 0
            ? "recovered"
            : suppressedCount > 0 && blockedCount == 0
                ? "suppressed_only"
                : candidateCount == 0
                    ? "noop"
                    : "blocked";
        DateTimeOffset recordedAtUtc = DateTimeOffset.UtcNow;
        ProductLiftReconcileRunReceiptState runReceipt = RecordDispatchRecoveryRun(
            "retry_expiry",
            status,
            candidateCount,
            recoveredCount,
            suppressedCount,
            blockedCount,
            recordedAtUtc);

        return new PublicSignalOperationsRecoveryResponse(
            Provider: "productlift",
            Status: status,
            CandidateReceiptCount: candidateCount,
            RecoveredReceiptCount: recoveredCount,
            SuppressedReceiptCount: suppressedCount,
            BlockedReceiptCount: blockedCount,
            RunReceiptId: runReceipt.RunReceiptId,
            RecordedAtUtc: recordedAtUtc);
    }

    public PublicSignalDeliveryOutcomeAckResponse RecordDeliveryOutcome(JsonElement payload)
        => RecordDeliveryOutcome(providerHint: null, payload);

    public PublicSignalDeliveryOutcomeAckResponse RecordDeliveryOutcome(string? providerHint, JsonElement payload)
    {
        if (payload.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("delivery outcome payload must be a JSON object.");
        }

        JsonElement envelope = ExtractEnvelope(payload);
        JsonElement primary = ExtractPrimaryItem(envelope);
        string serializedPayload = JsonSerializer.Serialize(payload);
        string payloadSha256 = ComputeSha256Hex(serializedPayload);
        string providerKey = ResolveDeliveryOutcomeProviderKey(providerHint, primary, envelope, payload);
        string provider = ResolveDeliveryOutcomeProviderLabel(providerKey);
        string outcomeEventId = NormalizeOptional(
                TryReadString(payload, "event_id", "eventId", "outcome_id", "outcomeId", "id")
                ?? TryReadString(envelope, "event_id", "eventId", "outcome_id", "outcomeId", "id")
                ?? TryReadString(primary, "event_id", "eventId", "outcome_id", "outcomeId", "id"))
            ?? $"sha256:{payloadSha256[..12]}";
        string deliveryId = ResolveDeliveryOutcomeDeliveryId(providerKey, primary, envelope, payload);
        string? providerMessageId = ResolveDeliveryOutcomeProviderMessageId(providerKey, primary, envelope, payload);
        string? sourceReceiptId = ResolveDeliveryOutcomeSourceReceiptId(primary, envelope, payload);
        string? recipientRef = ResolveDeliveryOutcomeRecipientRef(primary, envelope, payload);
        string? recipientEmail = ResolveDeliveryOutcomeRecipientEmail(primary, envelope, payload);
        string? addressHash = string.IsNullOrWhiteSpace(recipientEmail)
            ? null
            : ComputeSha256Hex(recipientEmail.Trim().ToLowerInvariant());
        string providerState = ResolveDeliveryOutcomeState(providerKey, primary, envelope, payload);
        string? reason = NormalizeOptional(
            TryReadString(primary, "reason", "error", "detail", "description")
            ?? TryReadString(envelope, "reason", "error", "detail", "description")
            ?? TryReadString(payload, "reason", "error", "detail", "description"));
        int? retryInSeconds = TryReadInt32(primary, "retry_in_seconds", "retryInSeconds", "next_retry_seconds", "nextRetrySeconds")
            ?? TryReadInt32(envelope, "retry_in_seconds", "retryInSeconds", "next_retry_seconds", "nextRetrySeconds")
            ?? TryReadInt32(payload, "retry_in_seconds", "retryInSeconds", "next_retry_seconds", "nextRetrySeconds");
        DateTimeOffset receivedAtUtc = DateTimeOffset.UtcNow;
        DateTimeOffset occurredAtUtc = TryReadDateTimeOffset(primary, "occurred_at", "timestamp", "created_at", "updated_at")
            ?? TryReadDateTimeOffset(envelope, "occurred_at", "timestamp", "created_at", "updated_at")
            ?? TryReadDateTimeOffset(payload, "occurred_at", "timestamp", "created_at", "updated_at")
            ?? receivedAtUtc;
        DateTimeOffset? retryAtUtc = TryReadDateTimeOffset(primary, "retry_at", "next_retry_at", "retryAfterAt")
            ?? TryReadDateTimeOffset(envelope, "retry_at", "next_retry_at", "retryAfterAt")
            ?? TryReadDateTimeOffset(payload, "retry_at", "next_retry_at", "retryAfterAt");
        if (retryAtUtc is null && retryInSeconds is > 0)
        {
            retryAtUtc = receivedAtUtc.AddSeconds(retryInSeconds.Value);
        }
        string dedupState = ResolveDeliveryOutcomeDispatchState(providerState, reason, retryAtUtc);

        ProductLiftDeliveryOutcomeReceiptState? storedReceipt = null;
        ProductLiftCloseoutDispatchReceiptState? updatedDispatch = null;
        ProductLiftWebhookReceiptState? matchedSourceReceipt = null;
        bool duplicate = false;
        bool shouldPersistDispatchOnly = false;

        lock (_gate)
        {
            DeliveryOutcomeDispatchIdentityMatch? matchedDispatchIdentity = FindDispatchReceiptByOutcomeIdentityLocked(
                deliveryId,
                providerMessageId,
                sourceReceiptId,
                recipientRef,
                addressHash);
            ProductLiftCloseoutDispatchReceiptState? matchedDispatch = matchedDispatchIdentity?.Receipt;
            string dedupKey = BuildDeliveryOutcomeDedupKey(
                outcomeEventId,
                provider,
                deliveryId,
                dedupState,
                payloadSha256,
                matchedDispatch?.ReceiptId);

            if (_deliveryOutcomeReceiptIdByDedupKey.TryGetValue(dedupKey, out string? existingId))
            {
                duplicate = true;
                storedReceipt = _deliveryOutcomeReceipts.First(receipt => string.Equals(receipt.ReceiptId, existingId, StringComparison.OrdinalIgnoreCase));
                if (matchedDispatch is not null)
                {
                    ProductLiftCloseoutDispatchReceiptState duplicateUpdatedDispatch = ApplyDeliveryOutcomeToDispatchLocked(matchedDispatch, providerState, providerMessageId, reason, retryAtUtc, receivedAtUtc);
                    if (duplicateUpdatedDispatch != matchedDispatch)
                    {
                        updatedDispatch = duplicateUpdatedDispatch;
                        matchedSourceReceipt = _receipts.FirstOrDefault(receipt => string.Equals(receipt.ReceiptId, duplicateUpdatedDispatch.SourceReceiptId, StringComparison.OrdinalIgnoreCase));
                        shouldPersistDispatchOnly = true;
                    }
                }
            }
            else
            {
                matchedSourceReceipt = matchedDispatch is null
                    ? null
                    : _receipts.FirstOrDefault(receipt => string.Equals(receipt.ReceiptId, matchedDispatch.SourceReceiptId, StringComparison.OrdinalIgnoreCase));
                updatedDispatch = matchedDispatch is null
                    ? null
                    : ApplyDeliveryOutcomeToDispatchLocked(matchedDispatch, providerState, providerMessageId, reason, retryAtUtc, receivedAtUtc);
                string dispatchReceiptId = updatedDispatch?.ReceiptId ?? matchedDispatch?.ReceiptId ?? "unmatched";
                string resolvedSourceReceiptId = updatedDispatch?.SourceReceiptId ?? matchedDispatch?.SourceReceiptId ?? "unmatched";
                string statusLabel = ResolveDeliveryOutcomeStatusLabel(providerState, updatedDispatch is not null, reason);
                string summary = BuildDeliveryOutcomeSummary(provider, providerState, dispatchReceiptId, reason, retryAtUtc);
                ProductLiftDeliveryOutcomeReceiptState receipt = new(
                    ReceiptId: $"ploutcome_{Guid.NewGuid():N}",
                    DedupKey: dedupKey,
                    OutcomeEventId: outcomeEventId,
                    Provider: provider,
                    DispatchReceiptId: dispatchReceiptId,
                    SourceReceiptId: resolvedSourceReceiptId,
                    DeliveryId: deliveryId,
                    ProviderMessageId: providerMessageId,
                    RecipientRef: matchedDispatch?.RecipientRef ?? NormalizeOptional(recipientRef) ?? "unmatched",
                    AddressHash: matchedDispatch?.AddressHash ?? NormalizeOptional(addressHash) ?? "unknown",
                    IdentityMatchMode: matchedDispatchIdentity?.MatchMode ?? "unmatched",
                    ProviderState: providerState,
                    StatusLabel: statusLabel,
                    SuppressionCheck: updatedDispatch?.SuppressionCheck ?? ResolveSuppressionCheck(reason, hasDeliveryId: !string.Equals(deliveryId, "delivery-pending", StringComparison.OrdinalIgnoreCase)),
                    RetryAtUtc: retryAtUtc,
                    Summary: summary,
                    Reason: reason,
                    PayloadSha256: payloadSha256,
                    PublicClaimAllowed: false,
                    OccurredAtUtc: occurredAtUtc,
                    RecordedAtUtc: receivedAtUtc);
                _deliveryOutcomeReceipts.Add(receipt);
                _deliveryOutcomeReceipts.Sort(static (left, right) => right.RecordedAtUtc.CompareTo(left.RecordedAtUtc));
                _deliveryOutcomeReceiptIdByDedupKey[dedupKey] = receipt.ReceiptId;
                TrimReceiptsLocked();
                PersistLocked();
                storedReceipt = receipt;
            }

            if (duplicate && shouldPersistDispatchOnly)
            {
                TrimReceiptsLocked();
                PersistLocked();
            }
        }

        if (!duplicate && updatedDispatch is not null && matchedSourceReceipt is not null
            && string.Equals(updatedDispatch.DeliveryState, "sent", StringComparison.OrdinalIgnoreCase))
        {
            TryAppendJourneyReceiptIfDispatchComplete(
                matchedSourceReceipt,
                updatedDispatch.GovernorDecisionRef,
                updatedDispatch.ReleaseProofReceiptId);
        }

        return new PublicSignalDeliveryOutcomeAckResponse(
            Provider: provider,
            Status: duplicate ? "duplicate" : "recorded",
            Duplicate: duplicate,
            ReceiptId: storedReceipt?.ReceiptId ?? "unmatched",
            DispatchReceiptId: updatedDispatch?.ReceiptId ?? storedReceipt?.DispatchReceiptId ?? "unmatched",
            DeliveryId: deliveryId,
            ProviderState: providerState,
            RecordedAtUtc: receivedAtUtc);
    }

    public string LoadArtifactJson()
    {
        var packet = BuildPacket();
        JsonObject artifact = new()
        {
            ["contractName"] = "chummer.public_signal_operations",
            ["generatedAtUtc"] = DateTimeOffset.UtcNow,
            ["eyebrow"] = SanitizePublicArtifactText(packet.Eyebrow),
            ["heading"] = SanitizePublicArtifactText(packet.Heading),
            ["summary"] = SanitizePublicArtifactText(packet.Summary),
            ["hostedDomainLabel"] = packet.HostedDomainLabel,
            ["hostedProjectionReady"] = packet.HostedProjectionReady,
            ["hostedProjectionSummary"] = SanitizePublicArtifactText(packet.HostedProjectionSummary),
            ["intakeStatusLabel"] = SanitizePublicArtifactText(packet.WebhookStatusLabel),
            ["intakeSummary"] = SanitizePublicArtifactText(packet.WebhookSummary),
            ["closeoutStatusLabel"] = SanitizePublicArtifactText(packet.VoterCloseoutStatusLabel),
            ["closeoutSummary"] = SanitizePublicArtifactText(packet.VoterCloseoutSummary),
            ["followSettingsPath"] = packet.FollowSettingsPath,
            ["recipientProjectionStatusLabel"] = SanitizePublicArtifactText(packet.RecipientProjectionStatusLabel),
            ["recipientProjectionSummary"] = SanitizePublicArtifactText(packet.RecipientProjectionSummary),
            ["consentStatusLabel"] = SanitizePublicArtifactText(packet.ConsentStatusLabel),
            ["consentSummary"] = SanitizePublicArtifactText(packet.ConsentSummary),
            ["queueStatusLabel"] = SanitizePublicArtifactText(packet.QueueStatusLabel),
            ["queueSummary"] = SanitizePublicArtifactText(packet.QueueSummary),
            ["decisionStatusLabel"] = SanitizePublicArtifactText(packet.GovernorStatusLabel),
            ["decisionSummary"] = SanitizePublicArtifactText(packet.GovernorSummary),
            ["releaseProofStatusLabel"] = SanitizePublicArtifactText(packet.ReleaseProofStatusLabel),
            ["releaseProofSummary"] = SanitizePublicArtifactText(packet.ReleaseProofSummary),
            ["releaseProofRoute"] = packet.ReleaseProofRoute,
            ["releaseProofReceiptId"] = packet.ReleaseProofReceiptId,
            ["counts"] = new JsonObject
            {
                ["categoryCount"] = packet.CategoryCount,
                ["receiptCount"] = packet.ReceiptCount,
                ["routingReceiptCount"] = packet.RoutingReceiptCount,
                ["closeoutReceiptCount"] = packet.CloseoutReceiptCount,
                ["journeyReceiptCount"] = packet.JourneyReceiptCount,
                ["deliveryOutcomeReceiptCount"] = packet.DeliveryOutcomeReceiptCount,
                ["projectedRecipientCount"] = packet.ProjectedRecipientCount,
                ["replayCandidateCount"] = packet.ReplayCandidateCount,
                ["reconcileRunCount"] = packet.ReconcileRunCount,
                ["deliveryRecoveryCandidateCount"] = packet.DeliveryRecoveryCandidateCount,
                ["retryExpiryCandidateCount"] = packet.RetryExpiryCandidateCount
            }
        };
        return artifact.ToJsonString(JsonOptions);
    }

    private static string SanitizePublicArtifactText(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return string.Empty;
        }

        return value
            .Replace("Webhook", "Intake", StringComparison.OrdinalIgnoreCase)
            .Replace("Product Governor", "governed product decision", StringComparison.OrdinalIgnoreCase)
            .Replace("ProductLift", "public feedback board", StringComparison.OrdinalIgnoreCase)
            .Replace("Emailit", "delivery adapter", StringComparison.OrdinalIgnoreCase)
            .Replace("operator", "review", StringComparison.OrdinalIgnoreCase)
            .Replace("provider", "delivery", StringComparison.OrdinalIgnoreCase)
            .Replace("callback", "outcome update", StringComparison.OrdinalIgnoreCase);
    }

    public static string WebhookSecretHeader => WebhookSecretHeaderName;

    public static string EmailitWebhookSecretHeader => EmailitWebhookSecretHeaderName;

    public static string EaDeliveryWebhookSecretHeader => EaDeliveryWebhookSecretHeaderName;

    public static string OperationsSecretHeader => OperationsSecretHeaderName;

    private CloseoutRuntimeReadiness BuildCloseoutRuntimeReadiness()
    {
        CloseoutAudienceSnapshot audience = BuildCloseoutAudienceSnapshot();
        string projectionOwner = NormalizeOptional(_configuration[ProductLiftCloseoutProjectionOwnerConfigKey]) ?? ExpectedProjectionOwner;
        bool ownerReady = string.Equals(projectionOwner, ExpectedProjectionOwner, StringComparison.OrdinalIgnoreCase);
        bool projectionEnabled = bool.TryParse(_configuration[ProductLiftCloseoutRecipientProjectionEnabledConfigKey], out bool enabled) && enabled;
        string followSettingsPath = NormalizeOptional(_configuration[ProductLiftCloseoutFollowSettingsPathConfigKey]) ?? DefaultFollowSettingsPath;
        bool consentConfigured = !string.IsNullOrWhiteSpace(NormalizeOptional(_configuration[ProductLiftCloseoutConsentBasisConfigKey]));
        bool queueConfigured = !string.IsNullOrWhiteSpace(_configuration[ProductLiftCloseoutEaApiTokenConfigKey])
            && !string.IsNullOrWhiteSpace(_configuration[ProductLiftCloseoutEaPrincipalIdConfigKey])
            && !string.IsNullOrWhiteSpace(_configuration[ProductLiftCloseoutEaBindingIdConfigKey]);
        bool governorApproved = bool.TryParse(_configuration[ProductLiftCloseoutGovernorApprovedConfigKey], out bool approved) && approved;
        string? governorDecisionRef = NormalizeOptional(_configuration[ProductLiftCloseoutGovernorDecisionRefConfigKey]);
        bool governorReady = governorApproved && !string.IsNullOrWhiteSpace(governorDecisionRef);
        LocalReleaseProofLookupResult proofLookup = _localReleaseProof.FindReceipt(CloseoutProofRoute);
        LocalProofReceiptMatch? proofReceipt = proofLookup.ReceiptMatch;
        bool releaseProofReady = proofReceipt is not null && string.IsNullOrWhiteSpace(proofLookup.CurrentnessFailureReason);

        string projectionStatusLabel;
        string projectionSummary;
        if (!ownerReady)
        {
            projectionStatusLabel = "Ownership blocked";
            projectionSummary = $"Closeout recipients must stay first-party. This instance is pointed at '{projectionOwner}' instead of '{ExpectedProjectionOwner}', so no account follower mapping can be used.";
        }
        else if (!projectionEnabled)
        {
            projectionStatusLabel = "Recipient list pending";
            projectionSummary = $"Recipient matching is still missing. The user return path should stay on {followSettingsPath} until that mapping exists.";
        }
        else if (audience.ProjectedRecipientCount == 0)
        {
            projectionStatusLabel = "No eligible followers";
            projectionSummary = $"Recipient matching is enabled, but no account followers currently have roadmap updates enabled. The return path stays on {followSettingsPath} until at least one first-party follower qualifies.";
        }
        else
        {
            projectionStatusLabel = "Recipient list ready";
            projectionSummary = $"First-party recipient matching is enabled for public closeout. {audience.ProjectedRecipientCount} account follower{(audience.ProjectedRecipientCount == 1 ? string.Empty : "s")} currently qualify through follow settings, and external recipient lists stay out of first-party storage.";
        }

        string consentStatusLabel;
        string consentSummary;
        if (!ownerReady || !projectionEnabled)
        {
            consentStatusLabel = "Consent basis pending";
            consentSummary = "Recipient matching must come first. Once the follower mapping is first-party, it still needs a first-party consent or transactional-basis record before delivery can be attempted.";
        }
        else if (audience.ProjectedRecipientCount == 0)
        {
            consentStatusLabel = "Consent source idle";
            consentSummary = "The consent source is defined, but no account followers currently qualify for public closeout through first-party follow settings.";
        }
        else if (!consentConfigured)
        {
            consentStatusLabel = "Consent basis pending";
            consentSummary = "The recipient path exists, but this instance still lacks the configured first-party consent basis for public closeout follow-up.";
        }
        else
        {
            consentStatusLabel = "Consent basis configured";
            consentSummary = $"A first-party consent or transactional-basis reference is configured for public closeout, and {audience.ProjectedRecipientCount} projected follower{(audience.ProjectedRecipientCount == 1 ? string.Empty : "s")} currently have the required first-party follow setting plus confirmed email link.";
        }

        string queueStatusLabel;
        string queueSummary;
        if (!ownerReady || !projectionEnabled || audience.ProjectedRecipientCount == 0 || !consentConfigured)
        {
            queueStatusLabel = "Queue blocked";
            queueSummary = "The outbox stays blocked until recipient mapping and consent basis are ready for public closeout.";
        }
        else if (!queueConfigured)
        {
            queueStatusLabel = "Queue adapter pending";
            queueSummary = "Recipient and consent checks are ready, but the delivery queue connection for public closeout is still missing its principal, binding, or API token on this instance.";
        }
        else
        {
            queueStatusLabel = "Queue adapter configured";
            queueSummary = "This instance can send a public closeout candidate to the delivery queue once release status and closeout approval say the message should exist.";
        }

        string governorStatusLabel;
        string governorSummary;
        if (!governorReady)
        {
            governorStatusLabel = "Governor approval pending";
            governorSummary = "A reviewed product decision reference is still required before any shipped public item can create a first-party outbox candidate.";
        }
        else
        {
            governorStatusLabel = "Governor approval configured";
            governorSummary = $"Public closeout may cite reviewed product decision {governorDecisionRef} before any outbound send is claimed.";
        }

        string releaseProofStatusLabel;
        string releaseProofSummary;
        if (!string.IsNullOrWhiteSpace(proofLookup.CurrentnessFailureReason))
        {
            releaseProofStatusLabel = "Release status stale";
            releaseProofSummary = $"Outbox creation stays blocked because {proofLookup.CurrentnessFailureReason!.Trim().TrimEnd('.')} for {CloseoutProofRoute}.";
        }
        else if (proofReceipt is null)
        {
            releaseProofStatusLabel = "Release status pending";
            releaseProofSummary = $"Outbox creation stays blocked until {CloseoutProofRoute} has a current first-party release status record.";
        }
        else
        {
            releaseProofStatusLabel = "Release status current";
            releaseProofSummary = $"Current release status covers {proofReceipt.MatchedRoute} through record {proofReceipt.ReceiptId} in package {proofReceipt.PackageId}.";
        }

        return new CloseoutRuntimeReadiness(
            ProjectionOwner: projectionOwner,
            FollowSettingsPath: followSettingsPath,
            OwnerReady: ownerReady,
            ProjectionConfigured: projectionEnabled,
            ProjectionSourceRef: audience.ProjectionSourceRef,
            ProjectedRecipientCount: audience.ProjectedRecipientCount,
            Recipients: audience.Recipients,
            ConsentConfigured: consentConfigured,
            ConsentSourceRef: audience.ConsentSourceRef,
            QueueConfigured: queueConfigured,
            GovernorApproved: governorReady,
            GovernorDecisionRef: governorDecisionRef,
            ReleaseProofReady: releaseProofReady,
            ReleaseProofRoute: CloseoutProofRoute,
            ReleaseProofReceiptId: proofReceipt?.ReceiptId,
            ProjectionStatusLabel: projectionStatusLabel,
            ProjectionSummary: projectionSummary,
            ConsentStatusLabel: consentStatusLabel,
            ConsentSummary: consentSummary,
            QueueStatusLabel: queueStatusLabel,
            QueueSummary: queueSummary,
            GovernorStatusLabel: governorStatusLabel,
            GovernorSummary: governorSummary,
            ReleaseProofStatusLabel: releaseProofStatusLabel,
            ReleaseProofSummary: releaseProofSummary);
    }

    private CloseoutAudienceSnapshot BuildCloseoutAudienceSnapshot()
    {
        lock (_communityStore.Gate)
        {
            Dictionary<string, string> verifiedEmailByUserId = _communityStore.LinkedIdentities
                .Where(static link =>
                    string.Equals(link.Provider, "email", StringComparison.OrdinalIgnoreCase)
                    && string.Equals(link.Status, "verified", StringComparison.OrdinalIgnoreCase))
                .Where(static link => !string.IsNullOrWhiteSpace(link.UserId))
                .OrderByDescending(static link => link.VerifiedAtUtc ?? link.UpdatedAtUtc)
                .GroupBy(static link => link.UserId, StringComparer.OrdinalIgnoreCase)
                .ToDictionary(
                    static group => group.Key,
                    static group => group
                        .Select(link => NormalizeOptional(link.DisplayLabel))
                        .FirstOrDefault(static value => !string.IsNullOrWhiteSpace(value))
                        ?? string.Empty,
                    StringComparer.OrdinalIgnoreCase);

            List<ProjectedCloseoutRecipient> recipients = _communityStore.UserExperienceByUserId.Values
                .Where(experience =>
                    experience.FollowHorizons
                    && verifiedEmailByUserId.TryGetValue(experience.UserId, out string? email)
                    && !string.IsNullOrWhiteSpace(email)
                    && _communityStore.UsersById.TryGetValue(experience.UserId, out _))
                .Select(experience =>
                {
                    HubUserDto user = _communityStore.UsersById[experience.UserId];
                    string email = verifiedEmailByUserId[experience.UserId];
                    return new ProjectedCloseoutRecipient(
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        Email: email,
                        AddressHash: ComputeSha256Hex(email.Trim().ToLowerInvariant()));
                })
                .OrderBy(static recipient => recipient.UserId, StringComparer.OrdinalIgnoreCase)
                .ToList();

            return new CloseoutAudienceSnapshot(
                ProjectionSourceRef: DefaultProjectionSourceRef,
                ConsentSourceRef: DefaultConsentSourceRef,
                ProjectedRecipientCount: recipients.Count,
                Recipients: recipients);
        }
    }

    private IReadOnlyList<PublicSignalHostedRouteViewModel> BuildHostedRoutes()
    {
        return
        [
            BuildHostedRoute("Feedback", "/feedback", _configuration["CHUMMER_PRODUCTLIFT_FEEDBACK_URL"]),
            BuildHostedRoute("Roadmap", "/roadmap", _configuration["CHUMMER_PRODUCTLIFT_ROADMAP_URL"]),
            BuildHostedRoute("Changelog", "/changelog", _configuration["CHUMMER_PRODUCTLIFT_CHANGELOG_URL"])
        ];
    }

    private IReadOnlyList<PublicSignalDeliveryOutcomeIngressViewModel> BuildDeliveryOutcomeIngresses()
    {
        string? emailitSecret = NormalizeOptional(_configuration[EmailitWebhookSecretConfigKey]);
        string? eaSecret = NormalizeOptional(_configuration[EaDeliveryWebhookSecretConfigKey]);
        string? genericSecret = NormalizeOptional(_configuration[OperationsSecretConfigKey]);
        string[] publicDeliveryRoutes =
        [
            "/feedback/providers/delivery/webhook",
            "/api/v1/public/feedback/providers/delivery/webhook"
        ];
        string[] publicOutboxRoutes =
        [
            "/feedback/providers/outbox/webhook",
            "/api/v1/public/feedback/providers/outbox/webhook"
        ];
        string[] publicFallbackRoutes =
        [
            "/feedback/providers/delivery/outcome",
            "/api/v1/public/feedback/providers/delivery/outcome"
        ];

        return
        [
            new PublicSignalDeliveryOutcomeIngressViewModel(
                Label: "Delivery callback ingress",
                ProviderKey: "emailit",
                StatusLabel: emailitSecret is null ? "Pending" : "Configured",
                Summary: emailitSecret is null
                    ? "Delivery callback setup is still blocked on this instance, so delivered, bounced, complained, and suppressed events cannot yet return through the first-party ingress."
                    : "Delivery callback setup is configured. Public closeout mail can now return through the first-party ingress with delivered, soft-bounce, hard-bounce, complaint, and suppression normalization.",
                SecretHeader: "X-Delivery-Webhook-Secret",
                Routes: publicDeliveryRoutes),
            new PublicSignalDeliveryOutcomeIngressViewModel(
                Label: "EA delivery ingress",
                ProviderKey: "ea",
                StatusLabel: eaSecret is null ? "Pending" : "Configured",
                Summary: eaSecret is null
                    ? "The outbox callback setup is still blocked on this instance, so retry, dead-letter, and bounded delivery-failure events cannot yet return through the first-party ingress."
                    : "The outbox callback setup is configured. Public closeout delivery state can now return through the first-party ingress with retry-window and dead-letter normalization.",
                SecretHeader: "X-Outbox-Webhook-Secret",
                Routes: publicOutboxRoutes),
            new PublicSignalDeliveryOutcomeIngressViewModel(
                Label: "Compatibility fallback",
                ProviderKey: "generic",
                StatusLabel: genericSecret is null ? "Pending" : "Configured",
                Summary: genericSecret is null
                    ? "The generic delivery outcome fallback remains disabled on this instance. The dedicated delivery and outbox ingress routes should remain the normal path."
                    : "The generic operations-secret outcome route remains available as a bounded compatibility fallback, but the dedicated delivery and outbox ingress routes should carry the normal callback traffic.",
                SecretHeader: "X-Feedback-Operations-Secret",
                Routes: publicFallbackRoutes)
        ];
    }

    private WebhookReceiptSnapshot BuildReceiptSnapshot()
    {
        lock (_gate)
        {
            PublicSignalWebhookReceiptViewModel[] recentReceipts = _receipts
                .OrderByDescending(static receipt => receipt.ReceivedAtUtc)
                .Take(6)
                .Select(BuildWebhookReceiptViewModel)
                .ToArray();
            PublicSignalRoutingReceiptViewModel[] recentRoutingReceipts = _routingReceipts
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .Take(6)
                .Select(BuildRoutingReceiptViewModel)
                .ToArray();
            PublicSignalCloseoutDeliveryReceiptViewModel[] recentCloseoutReceipts = _closeoutReceipts
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .Take(6)
                .Select(BuildCloseoutDeliveryReceiptViewModel)
                .ToArray();

            return new WebhookReceiptSnapshot(
                ReceiptCount: _receipts.Count,
                CloseoutReceiptCount: _receipts.Count(static receipt => receipt.CloseoutCandidate),
                LastReceiptAtUtc: _receipts.Count == 0 ? null : _receipts.Max(static receipt => receipt.ReceivedAtUtc),
                RoutingReceiptCount: _routingReceipts.Count,
                ModerationReceiptCount: _routingReceipts.Count(static receipt => string.Equals(receipt.RouteKind, "moderation_review", StringComparison.Ordinal)),
                CloseoutDeliveryReceiptCount: _closeoutReceipts.Count,
                CloseoutDeliveryCandidateCount: _closeoutReceipts.Count(static receipt => receipt.DeliveryCandidate),
                RecentReceipts: recentReceipts,
                RecentRoutingReceipts: recentRoutingReceipts,
                RecentCloseoutReceipts: recentCloseoutReceipts);
        }
    }

    private CloseoutQueueSnapshot BuildQueueSnapshot(
        OperationsCanonDocument canonDocument,
        CloseoutRuntimeReadiness readiness)
    {
        lock (_gate)
        {
            PublicSignalCloseoutQueueReceiptViewModel[] allReceipts = _receipts
                .Where(static receipt => receipt.CloseoutCandidate)
                .OrderByDescending(static receipt => receipt.ReceivedAtUtc)
                .Select(receipt => BuildCloseoutQueueReceipt(receipt, canonDocument, readiness))
                .ToArray();
            PublicSignalCloseoutQueueReceiptViewModel[] recentReceipts = allReceipts
                .Take(6)
                .ToArray();

            return new CloseoutQueueSnapshot(
                ReceiptCount: allReceipts.Length,
                ReadyCount: allReceipts.Count(static receipt => receipt.ReadyForOutbox),
                RecentReceipts: recentReceipts);
        }
    }

    private DispatchReceiptSnapshot BuildDispatchSnapshot()
    {
        lock (_gate)
        {
            PublicSignalCloseoutDispatchReceiptViewModel[] recentReceipts = _dispatchReceipts
                .OrderByDescending(static receipt => receipt.RequestedAtUtc)
                .Take(6)
                .Select(static receipt => new PublicSignalCloseoutDispatchReceiptViewModel(
                    ReceiptId: receipt.ReceiptId,
                    SourceReceiptId: receipt.SourceReceiptId,
                    StatusLabel: receipt.StatusLabel,
                    DeliveryState: receipt.DeliveryState,
                    DeliveryId: receipt.DeliveryId,
                    ProviderMessageId: receipt.ProviderMessageId,
                    TemplateId: receipt.TemplateId,
                    TemplateVersion: receipt.TemplateVersion,
                    RecipientRef: receipt.RecipientRef,
                    AddressHash: receipt.AddressHash,
                    ConsentSourceRef: receipt.ConsentSourceRef,
                    SuppressionCheck: receipt.SuppressionCheck,
                    GovernorDecisionRef: receipt.GovernorDecisionRef,
                    ReleaseProofReceiptId: receipt.ReleaseProofReceiptId,
                    IdempotencyKey: receipt.IdempotencyKey,
                    Summary: receipt.Summary,
                    Error: receipt.Error,
                    PublicClaimAllowed: receipt.PublicClaimAllowed,
                    RecoveryAttemptCount: receipt.RecoveryAttemptCount,
                    LastRecoveryStatus: receipt.LastRecoveryStatus,
                    LastProviderState: receipt.LastProviderState,
                    NextAutomaticRetryAtUtc: receipt.NextAutomaticRetryAtUtc,
                    LastOutcomeAtUtc: receipt.LastOutcomeAtUtc,
                    RequestedAtUtc: receipt.RequestedAtUtc,
                    AcceptedAtUtc: receipt.AcceptedAtUtc,
                    LastRecoveryAtUtc: receipt.LastRecoveryAtUtc))
                .ToArray();

            return new DispatchReceiptSnapshot(
                ReceiptCount: _dispatchReceipts.Count,
                SentCount: _dispatchReceipts.Count(static receipt => string.Equals(receipt.DeliveryState, "sent", StringComparison.OrdinalIgnoreCase)),
                RecentReceipts: recentReceipts);
        }
    }

    private JourneyReceiptSnapshot BuildJourneySnapshot()
    {
        lock (_gate)
        {
            PublicSignalJourneyReceiptViewModel[] recentReceipts = _journeyReceipts
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .Take(6)
                .Select(BuildJourneyReceiptViewModel)
                .ToArray();

            return new JourneyReceiptSnapshot(
                ReceiptCount: _journeyReceipts.Count,
                RecentReceipts: recentReceipts);
        }
    }

    private DeliveryOutcomeSnapshot BuildDeliveryOutcomeSnapshot()
    {
        lock (_gate)
        {
            PublicSignalDeliveryOutcomeReceiptViewModel[] recentReceipts = _deliveryOutcomeReceipts
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .Take(6)
                .Select(static receipt => new PublicSignalDeliveryOutcomeReceiptViewModel(
                    ReceiptId: receipt.ReceiptId,
                    OutcomeEventId: receipt.OutcomeEventId,
                    Provider: receipt.Provider,
                    DispatchReceiptId: receipt.DispatchReceiptId,
                    SourceReceiptId: receipt.SourceReceiptId,
                    DeliveryId: receipt.DeliveryId,
                    ProviderMessageId: receipt.ProviderMessageId,
                    RecipientRef: receipt.RecipientRef,
                    AddressHash: receipt.AddressHash,
                    IdentityMatchMode: receipt.IdentityMatchMode,
                    ProviderState: receipt.ProviderState,
                    StatusLabel: receipt.StatusLabel,
                    SuppressionCheck: receipt.SuppressionCheck,
                    RetryAtUtc: receipt.RetryAtUtc,
                    Summary: receipt.Summary,
                    Reason: receipt.Reason,
                    PublicClaimAllowed: receipt.PublicClaimAllowed,
                    OccurredAtUtc: receipt.OccurredAtUtc,
                    RecordedAtUtc: receipt.RecordedAtUtc))
                .ToArray();

            return new DeliveryOutcomeSnapshot(
                ReceiptCount: _deliveryOutcomeReceipts.Count,
                AutomaticRetryPendingCount: _deliveryOutcomeReceipts.Count(static receipt =>
                    receipt.RetryAtUtc is not null
                    && receipt.RetryAtUtc > DateTimeOffset.UtcNow
                    && !string.Equals(receipt.SuppressionCheck, "suppressed", StringComparison.OrdinalIgnoreCase)),
                LastReceiptAtUtc: _deliveryOutcomeReceipts.Count == 0 ? null : _deliveryOutcomeReceipts.Max(static receipt => receipt.RecordedAtUtc),
                RecentReceipts: recentReceipts);
        }
    }

    private RecipientThreadSnapshot BuildRecipientThreadSnapshot(
        OperationsCanonDocument canonDocument,
        CloseoutRuntimeReadiness readiness)
    {
        lock (_gate)
        {
            PublicSignalRecipientThreadViewModel[] recentThreads = _dispatchReceipts
                .OrderByDescending(GetRecipientThreadLastTouchedAtUtc)
                .Take(6)
                .Select(receipt => BuildRecipientThread(receipt, canonDocument, readiness))
                .ToArray();

            return new RecipientThreadSnapshot(recentThreads);
        }
    }

    private ReconcileRunSnapshot BuildReconcileSnapshot(
        OperationsCanonDocument canonDocument,
        CloseoutRuntimeReadiness readiness)
    {
        lock (_gate)
        {
            int replayCandidateCount = _receipts.Count(receipt =>
                receipt.CloseoutCandidate
                && NeedsDispatchReplayLocked(receipt, readiness, canonDocument));
            PublicSignalReconcileRunReceiptViewModel[] recentRuns = _reconcileRuns
                .Where(static run => string.Equals(run.RunKind, "replay", StringComparison.Ordinal))
                .OrderByDescending(static run => run.RecordedAtUtc)
                .Take(6)
                .Select(static run => new PublicSignalReconcileRunReceiptViewModel(
                    RunReceiptId: run.RunReceiptId,
                    Status: run.Status,
                    CandidateReceiptCount: run.CandidateReceiptCount,
                    ReadyCandidateCount: run.ReadyCandidateCount,
                    ReplayCandidateCount: run.ReplayCandidateCount,
                    DispatchReceiptsCreated: run.DispatchReceiptsCreated,
                    JourneyReceiptsRecorded: run.JourneyReceiptsRecorded,
                    Summary: run.Summary,
                    RecordedAtUtc: run.RecordedAtUtc))
                .ToArray();

            return new ReconcileRunSnapshot(
                ReplayCandidateCount: replayCandidateCount,
                RunCount: _reconcileRuns.Count(static run => string.Equals(run.RunKind, "replay", StringComparison.Ordinal)),
                LastRunAtUtc: _reconcileRuns
                    .Where(static run => string.Equals(run.RunKind, "replay", StringComparison.Ordinal))
                    .Select(static run => (DateTimeOffset?)run.RecordedAtUtc)
                    .Max(),
                RecentRuns: recentRuns);
        }
    }

    private DispatchRecoverySnapshot BuildDispatchRecoverySnapshot()
    {
        lock (_gate)
        {
            int recoveryCandidateCount = _dispatchReceipts.Count(static receipt =>
                (string.Equals(receipt.DeliveryState, "accepted", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(receipt.DeliveryState, "failed", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(receipt.DeliveryState, "retrying", StringComparison.OrdinalIgnoreCase))
                && !string.Equals(receipt.SuppressionCheck, "suppressed", StringComparison.OrdinalIgnoreCase)
                && (receipt.NextAutomaticRetryAtUtc is null || receipt.NextAutomaticRetryAtUtc <= DateTimeOffset.UtcNow)
                && !string.Equals(receipt.DeliveryId, "delivery-pending", StringComparison.OrdinalIgnoreCase));
            int suppressedDispatchCount = _dispatchReceipts.Count(static receipt =>
                string.Equals(receipt.SuppressionCheck, "suppressed", StringComparison.OrdinalIgnoreCase)
                && !string.Equals(receipt.DeliveryState, "sent", StringComparison.OrdinalIgnoreCase));
            PublicSignalReconcileRunReceiptViewModel[] recentRuns = _reconcileRuns
                .Where(static run => string.Equals(run.RunKind, "dispatch_recovery", StringComparison.Ordinal))
                .OrderByDescending(static run => run.RecordedAtUtc)
                .Take(6)
                .Select(static run => new PublicSignalReconcileRunReceiptViewModel(
                    RunReceiptId: run.RunReceiptId,
                    Status: run.Status,
                    CandidateReceiptCount: run.CandidateReceiptCount,
                    ReadyCandidateCount: run.ReadyCandidateCount,
                    ReplayCandidateCount: run.ReplayCandidateCount,
                    DispatchReceiptsCreated: run.DispatchReceiptsCreated,
                    JourneyReceiptsRecorded: run.JourneyReceiptsRecorded,
                    Summary: run.Summary,
                    RecordedAtUtc: run.RecordedAtUtc))
                .ToArray();

            return new DispatchRecoverySnapshot(
                RecoveryCandidateCount: recoveryCandidateCount,
                SuppressedDispatchCount: suppressedDispatchCount,
                RunCount: _reconcileRuns.Count(static run => string.Equals(run.RunKind, "dispatch_recovery", StringComparison.Ordinal)),
                LastRunAtUtc: _reconcileRuns
                    .Where(static run => string.Equals(run.RunKind, "dispatch_recovery", StringComparison.Ordinal))
                    .Select(static run => (DateTimeOffset?)run.RecordedAtUtc)
                    .Max(),
                RecentRuns: recentRuns);
        }
    }

    private RetryExpirySweepSnapshot BuildRetryExpirySweepSnapshot()
    {
        lock (_gate)
        {
            int candidateCount = _dispatchReceipts.Count(static receipt =>
                string.Equals(receipt.DeliveryState, "retrying", StringComparison.OrdinalIgnoreCase)
                && !string.Equals(receipt.SuppressionCheck, "suppressed", StringComparison.OrdinalIgnoreCase)
                && receipt.NextAutomaticRetryAtUtc is not null
                && receipt.NextAutomaticRetryAtUtc <= DateTimeOffset.UtcNow
                && !string.Equals(receipt.DeliveryId, "delivery-pending", StringComparison.OrdinalIgnoreCase));
            PublicSignalReconcileRunReceiptViewModel[] recentRuns = _reconcileRuns
                .Where(static run => string.Equals(run.RunKind, "retry_expiry", StringComparison.Ordinal))
                .OrderByDescending(static run => run.RecordedAtUtc)
                .Take(6)
                .Select(static run => new PublicSignalReconcileRunReceiptViewModel(
                    RunReceiptId: run.RunReceiptId,
                    Status: run.Status,
                    CandidateReceiptCount: run.CandidateReceiptCount,
                    ReadyCandidateCount: run.ReadyCandidateCount,
                    ReplayCandidateCount: run.ReplayCandidateCount,
                    DispatchReceiptsCreated: run.DispatchReceiptsCreated,
                    JourneyReceiptsRecorded: run.JourneyReceiptsRecorded,
                    Summary: run.Summary,
                    RecordedAtUtc: run.RecordedAtUtc))
                .ToArray();

            return new RetryExpirySweepSnapshot(
                CandidateCount: candidateCount,
                RunCount: _reconcileRuns.Count(static run => string.Equals(run.RunKind, "retry_expiry", StringComparison.Ordinal)),
                LastRunAtUtc: _reconcileRuns
                    .Where(static run => string.Equals(run.RunKind, "retry_expiry", StringComparison.Ordinal))
                    .Select(static run => (DateTimeOffset?)run.RecordedAtUtc)
                    .Max(),
                RecentRuns: recentRuns);
        }
    }

    private object[] LoadRecentReceiptArtifactRows()
    {
        lock (_gate)
        {
            return _receipts
                .OrderByDescending(static receipt => receipt.ReceivedAtUtc)
                .Take(12)
                .Select(static receipt => new
                {
                    receipt.ReceiptId,
                    receipt.ProviderEventId,
                    receipt.EventType,
                    receipt.ActionLabel,
                    receipt.StatusLabel,
                    receipt.BoardLabel,
                    receipt.CategoryLabel,
                    receipt.ItemReference,
                    receipt.CloseoutCandidate,
                    receipt.VoterNotificationAllowed,
                    receipt.PayloadSha256,
                    receipt.ReceivedAtUtc,
                    receipt.ProviderOccurredAtUtc
                })
                .Cast<object>()
                .ToArray();
        }
    }

    private object[] LoadRecentDispatchReceiptArtifactRows()
    {
        lock (_gate)
        {
            return _dispatchReceipts
                .OrderByDescending(static receipt => receipt.RequestedAtUtc)
                .Take(12)
                .Select(static receipt => new
                {
                    receipt.ReceiptId,
                    receipt.SourceReceiptId,
                    receipt.StatusLabel,
                    receipt.DeliveryState,
                    receipt.DeliveryId,
                    receipt.ProviderMessageId,
                    receipt.TemplateId,
                    receipt.TemplateVersion,
                    receipt.RecipientRef,
                    receipt.AddressHash,
                    receipt.ConsentSourceRef,
                    receipt.SuppressionCheck,
                    receipt.GovernorDecisionRef,
                    receipt.ReleaseProofReceiptId,
                    receipt.IdempotencyKey,
                    receipt.Summary,
                    receipt.Error,
                    receipt.PublicClaimAllowed,
                    receipt.RecoveryAttemptCount,
                    receipt.LastRecoveryStatus,
                    receipt.LastProviderState,
                    receipt.NextAutomaticRetryAtUtc,
                    receipt.LastOutcomeAtUtc,
                    receipt.RequestedAtUtc,
                    receipt.AcceptedAtUtc,
                    receipt.LastRecoveryAtUtc
                })
                .Cast<object>()
                .ToArray();
        }
    }

    private object[] LoadRecentJourneyReceiptArtifactRows()
    {
        lock (_gate)
        {
            return _journeyReceipts
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .Take(12)
                .Select(receipt =>
                {
                    SourceHotFilterSummary hotFilter = ResolveSourceHotFilter(receipt.SourceReceiptId);
                    return new
                {
                    receipt.ReceiptId,
                    receipt.SourceReceiptId,
                    receipt.EventKey,
                    receipt.StatusLabel,
                    receipt.GovernorDecisionRef,
                    receipt.ReleaseProofReceiptId,
                    receipt.RecipientCount,
                    receipt.SentCount,
                    receipt.Summary,
                    receipt.PublicClaimAllowed,
                    SourceHotFilterKey = hotFilter.FilterKey,
                    SourceHotFilterLabel = hotFilter.FilterLabel,
                    SourceHotFilterCount = hotFilter.Count,
                    SourceHotFilterSummary = hotFilter.Summary,
                    receipt.RecordedAtUtc
                };
                })
                .Cast<object>()
                .ToArray();
        }
    }

    private object[] LoadRecentDeliveryOutcomeArtifactRows()
    {
        lock (_gate)
        {
            return _deliveryOutcomeReceipts
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .Take(12)
                .Select(static receipt => new
                {
                    receipt.ReceiptId,
                    receipt.OutcomeEventId,
                    receipt.Provider,
                    receipt.DispatchReceiptId,
                    receipt.SourceReceiptId,
                    receipt.DeliveryId,
                    receipt.ProviderMessageId,
                    receipt.RecipientRef,
                    receipt.AddressHash,
                    receipt.IdentityMatchMode,
                    receipt.ProviderState,
                    receipt.StatusLabel,
                    receipt.SuppressionCheck,
                    receipt.RetryAtUtc,
                    receipt.Summary,
                    receipt.Reason,
                    receipt.PayloadSha256,
                    receipt.PublicClaimAllowed,
                    receipt.OccurredAtUtc,
                    receipt.RecordedAtUtc
                })
                .Cast<object>()
                .ToArray();
        }
    }

    private DateTimeOffset GetRecipientThreadLastTouchedAtUtc(ProductLiftCloseoutDispatchReceiptState receipt)
    {
        ProductLiftDeliveryOutcomeReceiptState? outcome = _deliveryOutcomeReceipts
            .Where(item => string.Equals(item.DispatchReceiptId, receipt.ReceiptId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.RecordedAtUtc)
            .FirstOrDefault();
        ProductLiftJourneyReceiptState? journey = _journeyReceipts
            .Where(item =>
                string.Equals(item.SourceReceiptId, receipt.SourceReceiptId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.GovernorDecisionRef, receipt.GovernorDecisionRef, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.ReleaseProofReceiptId, receipt.ReleaseProofReceiptId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.RecordedAtUtc)
            .FirstOrDefault();

        DateTimeOffset lastTouchedAtUtc = receipt.RequestedAtUtc;
        if (receipt.LastOutcomeAtUtc is { } lastOutcomeAtUtc && lastOutcomeAtUtc > lastTouchedAtUtc)
        {
            lastTouchedAtUtc = lastOutcomeAtUtc;
        }

        if (outcome is not null && outcome.RecordedAtUtc > lastTouchedAtUtc)
        {
            lastTouchedAtUtc = outcome.RecordedAtUtc;
        }

        if (journey is not null && journey.RecordedAtUtc > lastTouchedAtUtc)
        {
            lastTouchedAtUtc = journey.RecordedAtUtc;
        }

        return lastTouchedAtUtc;
    }

    private PublicSignalRecipientThreadViewModel BuildRecipientThread(
        ProductLiftCloseoutDispatchReceiptState dispatchReceipt,
        OperationsCanonDocument canonDocument,
        CloseoutRuntimeReadiness readiness)
    {
        ProductLiftWebhookReceiptState? sourceReceipt = _receipts
            .FirstOrDefault(item => string.Equals(item.ReceiptId, dispatchReceipt.SourceReceiptId, StringComparison.OrdinalIgnoreCase));
        PublicSignalCloseoutQueueReceiptViewModel? queueReceipt = sourceReceipt is null
            ? null
            : BuildCloseoutQueueReceipt(sourceReceipt, canonDocument, readiness);
        ProductLiftDeliveryOutcomeReceiptState? outcomeReceipt = _deliveryOutcomeReceipts
            .Where(item => string.Equals(item.DispatchReceiptId, dispatchReceipt.ReceiptId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.RecordedAtUtc)
            .FirstOrDefault();
        ProductLiftJourneyReceiptState? journeyReceipt = _journeyReceipts
            .Where(item =>
                string.Equals(item.SourceReceiptId, dispatchReceipt.SourceReceiptId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.GovernorDecisionRef, dispatchReceipt.GovernorDecisionRef, StringComparison.OrdinalIgnoreCase)
                && string.Equals(item.ReleaseProofReceiptId, dispatchReceipt.ReleaseProofReceiptId, StringComparison.OrdinalIgnoreCase))
            .OrderByDescending(static item => item.RecordedAtUtc)
            .FirstOrDefault();
        string sourceLabel = BuildRecipientThreadSourceLabel(sourceReceipt);
        string currentStageLabel = journeyReceipt is not null
            ? journeyReceipt.StatusLabel
            : outcomeReceipt?.StatusLabel
                ?? dispatchReceipt.StatusLabel;
        DateTimeOffset lastTouchedAtUtc = GetRecipientThreadLastTouchedAtUtc(dispatchReceipt);

        return new PublicSignalRecipientThreadViewModel(
            RecipientRef: dispatchReceipt.RecipientRef,
            AddressHash: dispatchReceipt.AddressHash,
            SourceReceiptId: dispatchReceipt.SourceReceiptId,
            SourceLabel: sourceLabel,
            CurrentStageLabel: currentStageLabel,
            Summary: BuildRecipientThreadSummary(dispatchReceipt, queueReceipt, outcomeReceipt, journeyReceipt),
            QueueReceiptId: queueReceipt?.ReceiptId ?? "queue-unavailable",
            QueueState: queueReceipt?.QueueState ?? "unavailable",
            QueueStatusLabel: queueReceipt?.StatusLabel ?? "Queue view unavailable",
            QueueRecordedAtUtc: queueReceipt?.RecordedAtUtc ?? dispatchReceipt.RequestedAtUtc,
            DispatchReceiptId: dispatchReceipt.ReceiptId,
            DispatchState: dispatchReceipt.DeliveryState,
            DispatchStatusLabel: dispatchReceipt.StatusLabel,
            DispatchRequestedAtUtc: dispatchReceipt.RequestedAtUtc,
            OutcomeReceiptId: outcomeReceipt?.ReceiptId,
            OutcomeStatusLabel: outcomeReceipt?.StatusLabel,
            OutcomeProvider: outcomeReceipt?.Provider,
            OutcomeProviderState: outcomeReceipt?.ProviderState,
            OutcomeIdentityMatchMode: outcomeReceipt?.IdentityMatchMode,
            OutcomeRecordedAtUtc: outcomeReceipt?.RecordedAtUtc,
            JourneyReceiptId: journeyReceipt?.ReceiptId,
            JourneyStatusLabel: journeyReceipt?.StatusLabel,
            JourneyEventKey: journeyReceipt?.EventKey,
            JourneyRecordedAtUtc: journeyReceipt?.RecordedAtUtc,
            LastTouchedAtUtc: lastTouchedAtUtc,
            PublicClaimAllowed: false);
    }

    private static string BuildRecipientThreadSourceLabel(ProductLiftWebhookReceiptState? sourceReceipt)
    {
        if (sourceReceipt is null)
        {
            return "Unknown source receipt";
        }

        string itemReference = NormalizeOptional(sourceReceipt.ItemReference) ?? sourceReceipt.ReceiptId;
        string categoryLabel = NormalizeOptional(sourceReceipt.CategoryLabel) ?? "Uncategorized";
        return $"{categoryLabel} · {itemReference}";
    }

    private static string BuildRecipientThreadSummary(
        ProductLiftCloseoutDispatchReceiptState dispatchReceipt,
        PublicSignalCloseoutQueueReceiptViewModel? queueReceipt,
        ProductLiftDeliveryOutcomeReceiptState? outcomeReceipt,
        ProductLiftJourneyReceiptState? journeyReceipt)
    {
        string queueSummary = queueReceipt is null
            ? "queue view unavailable"
            : $"queue {queueReceipt.StatusLabel.ToLowerInvariant()}";
        string dispatchSummary = $"dispatch {dispatchReceipt.StatusLabel.ToLowerInvariant()}";

        if (journeyReceipt is not null)
        {
            string outcomeSummary = outcomeReceipt is null
                ? dispatchSummary
                : $"{outcomeReceipt.Provider} {outcomeReceipt.StatusLabel.ToLowerInvariant()}";
            return $"{queueSummary}, {dispatchSummary}, {outcomeSummary}, and {journeyReceipt.EventKey} evidence are now joined for {dispatchReceipt.RecipientRef}.";
        }

        if (outcomeReceipt is not null)
        {
            return $"{queueSummary}, {dispatchSummary}, and {outcomeReceipt.Provider} {outcomeReceipt.StatusLabel.ToLowerInvariant()} are now joined for {dispatchReceipt.RecipientRef}.";
        }

        return $"{queueSummary} and {dispatchSummary} are the current bounded closeout states for {dispatchReceipt.RecipientRef}.";
    }

    private static string BuildSourceReceiptDetailSummary(
        ProductLiftWebhookReceiptState sourceReceipt,
        int threadCount,
        int outcomeCount,
        int journeyCount)
    {
        string itemReference = NormalizeOptional(sourceReceipt.ItemReference) ?? sourceReceipt.ReceiptId;
        string categoryLabel = NormalizeOptional(sourceReceipt.CategoryLabel) ?? "Uncategorized";
        return $"{categoryLabel} signal {itemReference} currently spans {threadCount} bounded recipient thread{(threadCount == 1 ? string.Empty : "s")}, {outcomeCount} delivery update{(outcomeCount == 1 ? string.Empty : "s")}, and {journeyCount} journey receipt{(journeyCount == 1 ? string.Empty : "s")}.";
    }

    private static string BuildRecipientThreadDetailSummary(
        PublicSignalRecipientThreadViewModel thread,
        int outcomeCount,
        int journeyCount)
    {
        return $"{thread.SourceLabel} currently resolves through {thread.DispatchStatusLabel.ToLowerInvariant()} for {thread.RecipientRef}, with {outcomeCount} delivery update{(outcomeCount == 1 ? string.Empty : "s")} and {journeyCount} journey receipt{(journeyCount == 1 ? string.Empty : "s")} on the bounded closeout timeline.";
    }

    private static string NormalizeDetailFilter(string? filter)
    {
        string normalized = NormalizeToken(filter);
        return normalized switch
        {
            "sent" => "sent",
            "retrying" => "retrying",
            "suppressed" => "suppressed",
            "callback_pending" => "callback_pending",
            _ => "all"
        };
    }

    private static string ResolveDetailFilterLabel(string filterKey)
        => filterKey switch
        {
            "sent" => "Sent threads",
            "retrying" => "Retrying threads",
            "suppressed" => "Suppressed threads",
            "callback_pending" => "Callback-pending threads",
            _ => "All threads"
        };

    private static string ResolveDetailFilterSummary(string filterKey)
        => filterKey switch
        {
            "sent" => "Focus on recipient threads that already reached a first-party sent state.",
            "retrying" => "Focus on retry holds and recovery candidates still waiting for another bounded delivery attempt.",
            "suppressed" => "Focus on recipients held back by suppression, bounce, or explicit no-send status.",
            "callback_pending" => "Focus on outbound attempts that still do not have a bounded delivery update receipt.",
            _ => "Reopen the full bounded recipient list for this source receipt."
        };

    private sealed record SourceHotFilterSummary(
        string FilterKey,
        string FilterLabel,
        int Count,
        string Summary);

    private static string AppendDetailFilter(string baseHref, string filterKey)
        => string.Equals(filterKey, "all", StringComparison.Ordinal)
            ? baseHref
            : $"{baseHref}?filter={Uri.EscapeDataString(filterKey)}";

    private static string BuildJourneyScopeKey(string governorDecisionRef, string releaseProofReceiptId)
        => $"{governorDecisionRef}|{releaseProofReceiptId}";

    private static bool MatchesDetailFilter(
        ProductLiftCloseoutDispatchReceiptState receipt,
        bool hasOutcomeReceipt,
        string filterKey)
    {
        return filterKey switch
        {
            "sent" => hasOutcomeReceipt
                && string.Equals(receipt.DeliveryState, "sent", StringComparison.OrdinalIgnoreCase),
            "retrying" => string.Equals(receipt.DeliveryState, "retrying", StringComparison.OrdinalIgnoreCase)
                && !string.Equals(receipt.SuppressionCheck, "suppressed", StringComparison.OrdinalIgnoreCase),
            "suppressed" => string.Equals(receipt.SuppressionCheck, "suppressed", StringComparison.OrdinalIgnoreCase)
                || string.Equals(receipt.DeliveryState, "suppressed", StringComparison.OrdinalIgnoreCase),
            "callback_pending" => !hasOutcomeReceipt
                && !string.Equals(receipt.DeliveryState, "retrying", StringComparison.OrdinalIgnoreCase)
                && !string.Equals(receipt.SuppressionCheck, "suppressed", StringComparison.OrdinalIgnoreCase),
            _ => true
        };
    }

    private static PublicSignalOperationsDetailPivotViewModel BuildDetailPivot(
        string filterKey,
        int count,
        string baseHref,
        string artifactBaseHref,
        string currentFilter)
        => new(
            Key: filterKey,
            Label: ResolveDetailFilterLabel(filterKey),
            Summary: ResolveDetailFilterSummary(filterKey),
            Count: count,
            Href: AppendDetailFilter(baseHref, filterKey),
            ArtifactHref: AppendDetailFilter(artifactBaseHref, filterKey),
            Current: string.Equals(filterKey, currentFilter, StringComparison.Ordinal));

    private static PublicSignalOperationsDetailPivotViewModel[] BuildDetailPivots(
        IReadOnlyList<ProductLiftCloseoutDispatchReceiptState> dispatchStates,
        IReadOnlySet<string> dispatchReceiptIdsWithOutcomes,
        string baseHref,
        string artifactBaseHref,
        string currentFilter)
    {
        return
        [
            BuildDetailPivot("all", dispatchStates.Count, baseHref, artifactBaseHref, currentFilter),
            BuildDetailPivot(
                "retrying",
                dispatchStates.Count(receipt => MatchesDetailFilter(receipt, dispatchReceiptIdsWithOutcomes.Contains(receipt.ReceiptId), "retrying")),
                baseHref,
                artifactBaseHref,
                currentFilter),
            BuildDetailPivot(
                "suppressed",
                dispatchStates.Count(receipt => MatchesDetailFilter(receipt, dispatchReceiptIdsWithOutcomes.Contains(receipt.ReceiptId), "suppressed")),
                baseHref,
                artifactBaseHref,
                currentFilter),
            BuildDetailPivot(
                "sent",
                dispatchStates.Count(receipt => MatchesDetailFilter(receipt, dispatchReceiptIdsWithOutcomes.Contains(receipt.ReceiptId), "sent")),
                baseHref,
                artifactBaseHref,
                currentFilter),
            BuildDetailPivot(
                "callback_pending",
                dispatchStates.Count(receipt => MatchesDetailFilter(receipt, dispatchReceiptIdsWithOutcomes.Contains(receipt.ReceiptId), "callback_pending")),
                baseHref,
                artifactBaseHref,
                currentFilter)
        ];
    }

    private static string ResolveDetailFilterKeyForDispatch(
        ProductLiftCloseoutDispatchReceiptState receipt,
        bool hasOutcomeReceipt)
    {
        foreach (string filterKey in new[] { "sent", "retrying", "suppressed", "callback_pending" })
        {
            if (MatchesDetailFilter(receipt, hasOutcomeReceipt, filterKey))
            {
                return filterKey;
            }
        }

        return "all";
    }

    private SourceHotFilterSummary ResolveSourceHotFilter(ProductLiftWebhookReceiptState sourceReceipt)
        => ResolveSourceHotFilter(sourceReceipt.ReceiptId);

    private SourceHotFilterSummary ResolveSourceHotFilter(string sourceReceiptId)
    {
        string? normalizedSourceReceiptId = NormalizeOptional(sourceReceiptId);
        if (normalizedSourceReceiptId is null)
        {
            return new SourceHotFilterSummary(
                FilterKey: "all",
                FilterLabel: ResolveDetailFilterLabel("all"),
                Count: 0,
                Summary: "No bounded recipient threads exist under this source receipt yet.");
        }

        ProductLiftCloseoutDispatchReceiptState[] dispatchStates = _dispatchReceipts
            .Where(receipt => string.Equals(receipt.SourceReceiptId, normalizedSourceReceiptId, StringComparison.OrdinalIgnoreCase))
            .ToArray();
        if (dispatchStates.Length == 0)
        {
            return new SourceHotFilterSummary(
                FilterKey: "all",
                FilterLabel: ResolveDetailFilterLabel("all"),
                Count: 0,
                Summary: "No bounded recipient threads exist under this source receipt yet.");
        }

        HashSet<string> dispatchReceiptIdsWithOutcomes = _deliveryOutcomeReceipts
            .Where(receipt => string.Equals(receipt.SourceReceiptId, normalizedSourceReceiptId, StringComparison.OrdinalIgnoreCase))
            .Select(static receipt => receipt.DispatchReceiptId)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        foreach (string filterKey in new[] { "retrying", "suppressed", "callback_pending", "sent" })
        {
            int count = dispatchStates.Count(receipt => MatchesDetailFilter(receipt, dispatchReceiptIdsWithOutcomes.Contains(receipt.ReceiptId), filterKey));
            if (count > 0)
            {
                return new SourceHotFilterSummary(
                    FilterKey: filterKey,
                    FilterLabel: ResolveDetailFilterLabel(filterKey),
                    Count: count,
                    Summary: $"{count} {ResolveDetailFilterLabel(filterKey).ToLowerInvariant()} currently lead this source receipt.");
            }
        }

        return new SourceHotFilterSummary(
            FilterKey: "all",
            FilterLabel: ResolveDetailFilterLabel("all"),
            Count: dispatchStates.Length,
            Summary: $"{dispatchStates.Length} bounded recipient thread{(dispatchStates.Length == 1 ? string.Empty : "s")} currently sit under this source receipt.");
    }

    private PublicSignalOperationsLookupResultViewModel? BuildSourceLookupResult(
        ProductLiftWebhookReceiptState sourceReceipt,
        string[] tokens,
        OperationsCanonDocument canonDocument,
        CloseoutRuntimeReadiness readiness)
    {
        string matchReason = ResolveLookupMatchReason(
            tokens,
            ("Source record id", sourceReceipt.ReceiptId),
            ("Provider event id", sourceReceipt.ProviderEventId),
            ("Item reference", sourceReceipt.ItemReference),
            ("Category label", sourceReceipt.CategoryLabel),
            ("Board label", sourceReceipt.BoardLabel),
            ("Event type", sourceReceipt.EventType),
            ("Action label", sourceReceipt.ActionLabel));
        if (matchReason.Length == 0)
        {
            return null;
        }

        ProductLiftCloseoutDispatchReceiptState[] dispatchStates = _dispatchReceipts
            .Where(receipt => string.Equals(receipt.SourceReceiptId, sourceReceipt.ReceiptId, StringComparison.OrdinalIgnoreCase))
            .ToArray();
        int outcomeCount = _deliveryOutcomeReceipts.Count(receipt =>
            string.Equals(receipt.SourceReceiptId, sourceReceipt.ReceiptId, StringComparison.OrdinalIgnoreCase));
        int journeyCount = _journeyReceipts.Count(receipt =>
            string.Equals(receipt.SourceReceiptId, sourceReceipt.ReceiptId, StringComparison.OrdinalIgnoreCase));
        SourceHotFilterSummary hotFilter = ResolveSourceHotFilter(sourceReceipt);
        DateTimeOffset lastTouchedAtUtc = sourceReceipt.ReceivedAtUtc;
        if (dispatchStates.Length > 0)
        {
            DateTimeOffset dispatchLastTouchedAtUtc = dispatchStates.Max(GetRecipientThreadLastTouchedAtUtc);
            if (dispatchLastTouchedAtUtc > lastTouchedAtUtc)
            {
                lastTouchedAtUtc = dispatchLastTouchedAtUtc;
            }
        }

        return new PublicSignalOperationsLookupResultViewModel(
            ResultKindLabel: "Source record",
            MatchReason: matchReason,
            KeyLabel: "Source record",
            Key: sourceReceipt.ReceiptId,
            Heading: $"{NormalizeOptional(sourceReceipt.CategoryLabel) ?? "Uncategorized"} · {NormalizeOptional(sourceReceipt.ItemReference) ?? sourceReceipt.ReceiptId}",
            Summary: BuildSourceReceiptDetailSummary(sourceReceipt, dispatchStates.Length, outcomeCount, journeyCount),
            FilterKey: hotFilter.FilterKey,
            FilterLabel: hotFilter.FilterLabel,
            Href: AppendDetailFilter($"/feedback/operations/source/{Uri.EscapeDataString(sourceReceipt.ReceiptId)}", hotFilter.FilterKey),
            ArtifactHref: AppendDetailFilter($"/api/v1/public/feedback/operations/source/{Uri.EscapeDataString(sourceReceipt.ReceiptId)}", hotFilter.FilterKey),
            LastTouchedAtUtc: lastTouchedAtUtc);
    }

    private PublicSignalOperationsLookupResultViewModel? BuildThreadLookupResult(
        ProductLiftCloseoutDispatchReceiptState dispatchReceipt,
        string[] tokens,
        OperationsCanonDocument canonDocument,
        CloseoutRuntimeReadiness readiness)
    {
        ProductLiftWebhookReceiptState? sourceReceipt = _receipts
            .FirstOrDefault(receipt => string.Equals(receipt.ReceiptId, dispatchReceipt.SourceReceiptId, StringComparison.OrdinalIgnoreCase));
        string matchReason = ResolveLookupMatchReason(
            tokens,
            ("Dispatch receipt id", dispatchReceipt.ReceiptId),
            ("Source record id", dispatchReceipt.SourceReceiptId),
            ("Recipient ref", dispatchReceipt.RecipientRef),
            ("Address hash", dispatchReceipt.AddressHash),
            ("Delivery id", dispatchReceipt.DeliveryId),
            ("Provider message id", dispatchReceipt.ProviderMessageId),
            ("Template id", dispatchReceipt.TemplateId),
            ("Source item reference", sourceReceipt?.ItemReference),
            ("Source category label", sourceReceipt?.CategoryLabel));
        if (matchReason.Length == 0)
        {
            return null;
        }

        PublicSignalRecipientThreadViewModel thread = BuildRecipientThread(dispatchReceipt, canonDocument, readiness);
        int outcomeCount = _deliveryOutcomeReceipts.Count(receipt =>
            string.Equals(receipt.DispatchReceiptId, dispatchReceipt.ReceiptId, StringComparison.OrdinalIgnoreCase));
        int journeyCount = _journeyReceipts.Count(receipt =>
            string.Equals(receipt.SourceReceiptId, dispatchReceipt.SourceReceiptId, StringComparison.OrdinalIgnoreCase)
            && string.Equals(receipt.GovernorDecisionRef, dispatchReceipt.GovernorDecisionRef, StringComparison.OrdinalIgnoreCase)
            && string.Equals(receipt.ReleaseProofReceiptId, dispatchReceipt.ReleaseProofReceiptId, StringComparison.OrdinalIgnoreCase));
        string filterKey = ResolveDetailFilterKeyForDispatch(dispatchReceipt, outcomeCount > 0);
        string detailHref = AppendDetailFilter($"/feedback/operations/thread/{Uri.EscapeDataString(dispatchReceipt.ReceiptId)}", filterKey);
        string artifactHref = AppendDetailFilter($"/api/v1/public/feedback/operations/thread/{Uri.EscapeDataString(dispatchReceipt.ReceiptId)}", filterKey);

        return new PublicSignalOperationsLookupResultViewModel(
            ResultKindLabel: "Recipient thread",
            MatchReason: matchReason,
            KeyLabel: "Dispatch receipt",
            Key: dispatchReceipt.ReceiptId,
            Heading: $"{dispatchReceipt.RecipientRef} · {dispatchReceipt.TemplateId}",
            Summary: BuildRecipientThreadDetailSummary(thread, outcomeCount, journeyCount),
            FilterKey: filterKey,
            FilterLabel: ResolveDetailFilterLabel(filterKey),
            Href: detailHref,
            ArtifactHref: artifactHref,
            LastTouchedAtUtc: thread.LastTouchedAtUtc);
    }

    private static string NormalizeLookupScope(string? scope)
    {
        string normalized = NormalizeToken(scope);
        return normalized switch
        {
            "source" => "source",
            "thread" => "thread",
            _ => "all"
        };
    }

    private static string ResolveLookupScopeLabel(string scope)
        => scope switch
        {
            "source" => "Source records only",
            "thread" => "Recipient threads only",
            _ => "Sources and threads"
        };

    private static string[] TokenizeLookupQuery(string query)
        => string.IsNullOrWhiteSpace(query)
            ? Array.Empty<string>()
            : query
                .Split([' ', '\t', '\r', '\n', ','], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                .Select(static token => token.Trim())
                .Where(static token => token.Length > 0)
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray();

    private static string ResolveLookupMatchReason(string[] tokens, params (string Label, string? Value)[] fields)
    {
        if (tokens.Length == 0)
        {
            return "Recent activity";
        }

        string combined = string.Join(' ', fields
            .Select(static field => NormalizeOptional(field.Value))
            .Where(static value => !string.IsNullOrWhiteSpace(value)));
        if (tokens.Any(token => combined.IndexOf(token, StringComparison.OrdinalIgnoreCase) < 0))
        {
            return string.Empty;
        }

        foreach ((string label, string? value) in fields)
        {
            if (string.IsNullOrWhiteSpace(value))
            {
                continue;
            }

            if (tokens.Any(token => value.IndexOf(token, StringComparison.OrdinalIgnoreCase) >= 0))
            {
                return label;
            }
        }

        return "Combined match";
    }

    private static string BuildLookupSummary(string query, string scope, bool queryProvided, int resultCount)
    {
        string subject = scope switch
        {
            "source" => "source record",
            "thread" => "recipient thread",
            _ => "activity item"
        };
        if (!queryProvided)
        {
            return $"Showing the most recent {subject}{(resultCount == 1 ? string.Empty : "s")} so people can open the right source or follow-up timeline without scanning the full feedback list.";
        }

        return resultCount == 0
            ? $"No {subject} matched '{query}'. Try a source record id, dispatch id, recipient, delivery id, delivery message id, or item reference."
            : $"Found {resultCount} matching {subject}{(resultCount == 1 ? string.Empty : "s")} for '{query}'.";
    }

    private PublicSignalWebhookReceiptViewModel BuildWebhookReceiptViewModel(ProductLiftWebhookReceiptState receipt)
    {
        SourceHotFilterSummary hotFilter = ResolveSourceHotFilter(receipt);
        return new PublicSignalWebhookReceiptViewModel(
            ReceiptId: receipt.ReceiptId,
            ProviderEventId: receipt.ProviderEventId,
            EventType: receipt.EventType,
            ActionLabel: receipt.ActionLabel,
            StatusLabel: receipt.StatusLabel,
            BoardLabel: receipt.BoardLabel,
            CategoryLabel: receipt.CategoryLabel,
            ItemReference: receipt.ItemReference,
            CloseoutCandidate: receipt.CloseoutCandidate,
            VoterNotificationAllowed: receipt.VoterNotificationAllowed,
            HotFilterKey: hotFilter.FilterKey,
            HotFilterLabel: hotFilter.FilterLabel,
            HotFilterCount: hotFilter.Count,
            HotFilterSummary: hotFilter.Summary,
            PayloadSha256: receipt.PayloadSha256,
            ReceivedAtUtc: receipt.ReceivedAtUtc,
            ProviderOccurredAtUtc: receipt.ProviderOccurredAtUtc);
    }

    private PublicSignalRoutingReceiptViewModel BuildRoutingReceiptViewModel(ProductLiftRoutingReceiptState receipt)
    {
        SourceHotFilterSummary hotFilter = ResolveSourceHotFilter(receipt.SourceReceiptId);
        return new(
            ReceiptId: receipt.ReceiptId,
            SourceReceiptId: receipt.SourceReceiptId,
            RouteKind: receipt.RouteKind,
            StatusLabel: receipt.StatusLabel,
            TargetPath: receipt.TargetPath,
            Summary: receipt.Summary,
            SourceHotFilterKey: hotFilter.FilterKey,
            SourceHotFilterLabel: hotFilter.FilterLabel,
            SourceHotFilterCount: hotFilter.Count,
            SourceHotFilterSummary: hotFilter.Summary,
            RecordedAtUtc: receipt.RecordedAtUtc);
    }

    private PublicSignalCloseoutDeliveryReceiptViewModel BuildCloseoutDeliveryReceiptViewModel(ProductLiftCloseoutDeliveryReceiptState receipt)
    {
        SourceHotFilterSummary hotFilter = ResolveSourceHotFilter(receipt.SourceReceiptId);
        return new(
            ReceiptId: receipt.ReceiptId,
            SourceReceiptId: receipt.SourceReceiptId,
            StatusLabel: receipt.StatusLabel,
            DeliveryState: receipt.DeliveryState,
            DeliveryLane: receipt.DeliveryLane,
            TemplateId: receipt.TemplateId,
            RecipientScopeRef: receipt.RecipientScopeRef,
            RecipientScopeCount: receipt.RecipientScopeCount,
            ConsentSourceRef: receipt.ConsentSourceRef,
            DeliveryReason: receipt.DeliveryReason,
            Summary: receipt.Summary,
            VoterNotificationAllowed: receipt.VoterNotificationAllowed,
            PublicClaimAllowed: receipt.PublicClaimAllowed,
            SourceHotFilterKey: hotFilter.FilterKey,
            SourceHotFilterLabel: hotFilter.FilterLabel,
            SourceHotFilterCount: hotFilter.Count,
            SourceHotFilterSummary: hotFilter.Summary,
            RecordedAtUtc: receipt.RecordedAtUtc);
    }

    private static PublicSignalCloseoutDispatchReceiptViewModel BuildDispatchReceiptViewModel(ProductLiftCloseoutDispatchReceiptState receipt)
        => new(
            ReceiptId: receipt.ReceiptId,
            SourceReceiptId: receipt.SourceReceiptId,
            StatusLabel: receipt.StatusLabel,
            DeliveryState: receipt.DeliveryState,
            DeliveryId: receipt.DeliveryId,
            ProviderMessageId: receipt.ProviderMessageId,
            TemplateId: receipt.TemplateId,
            TemplateVersion: receipt.TemplateVersion,
            RecipientRef: receipt.RecipientRef,
            AddressHash: receipt.AddressHash,
            ConsentSourceRef: receipt.ConsentSourceRef,
            SuppressionCheck: receipt.SuppressionCheck,
            GovernorDecisionRef: receipt.GovernorDecisionRef,
            ReleaseProofReceiptId: receipt.ReleaseProofReceiptId,
            IdempotencyKey: receipt.IdempotencyKey,
            Summary: receipt.Summary,
            Error: receipt.Error,
            PublicClaimAllowed: receipt.PublicClaimAllowed,
            RecoveryAttemptCount: receipt.RecoveryAttemptCount,
            LastRecoveryStatus: receipt.LastRecoveryStatus,
            LastProviderState: receipt.LastProviderState,
            NextAutomaticRetryAtUtc: receipt.NextAutomaticRetryAtUtc,
            LastOutcomeAtUtc: receipt.LastOutcomeAtUtc,
            RequestedAtUtc: receipt.RequestedAtUtc,
            AcceptedAtUtc: receipt.AcceptedAtUtc,
            LastRecoveryAtUtc: receipt.LastRecoveryAtUtc);

    private PublicSignalJourneyReceiptViewModel BuildJourneyReceiptViewModel(ProductLiftJourneyReceiptState receipt)
    {
        SourceHotFilterSummary hotFilter = ResolveSourceHotFilter(receipt.SourceReceiptId);
        return new(
            ReceiptId: receipt.ReceiptId,
            SourceReceiptId: receipt.SourceReceiptId,
            EventKey: receipt.EventKey,
            StatusLabel: receipt.StatusLabel,
            GovernorDecisionRef: receipt.GovernorDecisionRef,
            ReleaseProofReceiptId: receipt.ReleaseProofReceiptId,
            RecipientCount: receipt.RecipientCount,
            SentCount: receipt.SentCount,
            Summary: receipt.Summary,
            PublicClaimAllowed: receipt.PublicClaimAllowed,
            SourceHotFilterKey: hotFilter.FilterKey,
            SourceHotFilterLabel: hotFilter.FilterLabel,
            SourceHotFilterCount: hotFilter.Count,
            SourceHotFilterSummary: hotFilter.Summary,
            RecordedAtUtc: receipt.RecordedAtUtc);
    }

    private static PublicSignalDeliveryOutcomeReceiptViewModel BuildDeliveryOutcomeReceiptViewModel(ProductLiftDeliveryOutcomeReceiptState receipt)
        => new(
            ReceiptId: receipt.ReceiptId,
            OutcomeEventId: receipt.OutcomeEventId,
            Provider: receipt.Provider,
            DispatchReceiptId: receipt.DispatchReceiptId,
            SourceReceiptId: receipt.SourceReceiptId,
            DeliveryId: receipt.DeliveryId,
            ProviderMessageId: receipt.ProviderMessageId,
            RecipientRef: receipt.RecipientRef,
            AddressHash: receipt.AddressHash,
            IdentityMatchMode: receipt.IdentityMatchMode,
            ProviderState: receipt.ProviderState,
            StatusLabel: receipt.StatusLabel,
            SuppressionCheck: receipt.SuppressionCheck,
            RetryAtUtc: receipt.RetryAtUtc,
            Summary: receipt.Summary,
            Reason: receipt.Reason,
            PublicClaimAllowed: receipt.PublicClaimAllowed,
            OccurredAtUtc: receipt.OccurredAtUtc,
            RecordedAtUtc: receipt.RecordedAtUtc);

    private object[] LoadRecentOperationsRunArtifactRows(string runKind)
    {
        lock (_gate)
        {
            return _reconcileRuns
                .Where(run => string.Equals(run.RunKind, runKind, StringComparison.Ordinal))
                .OrderByDescending(static run => run.RecordedAtUtc)
                .Take(12)
                .Select(static run => new
                {
                    run.RunKind,
                    run.RunReceiptId,
                    run.Status,
                    run.CandidateReceiptCount,
                    run.ReadyCandidateCount,
                    run.ReplayCandidateCount,
                    run.DispatchReceiptsCreated,
                    run.JourneyReceiptsRecorded,
                    run.Summary,
                    run.RecordedAtUtc
                })
                .Cast<object>()
                .ToArray();
        }
    }

    private object[] LoadRecentRoutingReceiptArtifactRows()
    {
        lock (_gate)
        {
            return _routingReceipts
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .Take(12)
                .Select(receipt =>
                {
                    SourceHotFilterSummary hotFilter = ResolveSourceHotFilter(receipt.SourceReceiptId);
                    return new
                {
                    receipt.ReceiptId,
                    receipt.SourceReceiptId,
                    receipt.RouteKind,
                    receipt.StatusLabel,
                    receipt.TargetPath,
                    receipt.Summary,
                    SourceHotFilterKey = hotFilter.FilterKey,
                    SourceHotFilterLabel = hotFilter.FilterLabel,
                    SourceHotFilterCount = hotFilter.Count,
                    SourceHotFilterSummary = hotFilter.Summary,
                    receipt.RecordedAtUtc
                };
                })
                .Cast<object>()
                .ToArray();
        }
    }

    private object[] LoadRecentCloseoutReceiptArtifactRows()
    {
        lock (_gate)
        {
            return _closeoutReceipts
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .Take(12)
                .Select(receipt =>
                {
                    SourceHotFilterSummary hotFilter = ResolveSourceHotFilter(receipt.SourceReceiptId);
                    return new
                {
                    receipt.ReceiptId,
                    receipt.SourceReceiptId,
                    receipt.StatusLabel,
                    receipt.DeliveryState,
                    receipt.DeliveryLane,
                    receipt.TemplateId,
                    receipt.RecipientScopeRef,
                    receipt.RecipientScopeCount,
                    receipt.ConsentSourceRef,
                    receipt.DeliveryReason,
                    receipt.Summary,
                    receipt.VoterNotificationAllowed,
                    receipt.DeliveryCandidate,
                    receipt.PublicClaimAllowed,
                    SourceHotFilterKey = hotFilter.FilterKey,
                    SourceHotFilterLabel = hotFilter.FilterLabel,
                    SourceHotFilterCount = hotFilter.Count,
                    SourceHotFilterSummary = hotFilter.Summary,
                    receipt.RecordedAtUtc
                };
                })
                .Cast<object>()
                .ToArray();
        }
    }

    private void PersistLocked()
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_storagePath)!);
        string tempPath = $"{_storagePath}.tmp";
        ProductLiftWebhookReceiptSnapshot snapshot = new(
            WebhookReceipts: _receipts
                .OrderByDescending(static receipt => receipt.ReceivedAtUtc)
                .ToArray(),
            RoutingReceipts: _routingReceipts
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .ToArray(),
            CloseoutReceipts: _closeoutReceipts
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .ToArray(),
            DispatchReceipts: _dispatchReceipts
                .OrderByDescending(static receipt => receipt.RequestedAtUtc)
                .ToArray(),
            JourneyReceipts: _journeyReceipts
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .ToArray(),
            DeliveryOutcomeReceipts: _deliveryOutcomeReceipts
                .OrderByDescending(static receipt => receipt.RecordedAtUtc)
                .ToArray(),
            ReconcileRuns: _reconcileRuns
                .OrderByDescending(static run => run.RecordedAtUtc)
                .ToArray());
        File.WriteAllText(tempPath, JsonSerializer.Serialize(snapshot, JsonOptions));
        File.Move(tempPath, _storagePath, true);
    }

    private void Load()
    {
        lock (_gate)
        {
            if (!File.Exists(_storagePath))
            {
                _logger.LogInformation("PublicSignalOperationsService starting without stored ProductLift webhook receipts at {StoragePath}.", _storagePath);
                return;
            }

            string snapshotJson = File.ReadAllText(_storagePath);
            ProductLiftWebhookReceiptSnapshot snapshot = JsonSerializer.Deserialize<ProductLiftWebhookReceiptSnapshot>(snapshotJson, JsonOptions)
                ?? throw new InvalidOperationException($"Unable to deserialize ProductLift webhook receipt snapshot: {_storagePath}");

            ApplySnapshotLocked(snapshot);
            _logger.LogInformation(
                "PublicSignalOperationsService loaded {ReceiptCount} bounded ProductLift webhook receipts from {StoragePath}.",
                _receipts.Count,
                _storagePath);
        }
    }

    private void ApplySnapshotLocked(ProductLiftWebhookReceiptSnapshot snapshot)
    {
        _receipts.Clear();
        _receiptIdByDedupKey.Clear();
        _routingReceipts.Clear();
        _routingReceiptIdByDedupKey.Clear();
        _closeoutReceipts.Clear();
        _closeoutReceiptIdByDedupKey.Clear();
        _dispatchReceipts.Clear();
        _dispatchReceiptIdByDedupKey.Clear();
        _journeyReceipts.Clear();
        _journeyReceiptIdByDedupKey.Clear();
        _deliveryOutcomeReceipts.Clear();
        _deliveryOutcomeReceiptIdByDedupKey.Clear();
        _reconcileRuns.Clear();

        foreach (ProductLiftWebhookReceiptState receipt in snapshot.WebhookReceipts ?? Array.Empty<ProductLiftWebhookReceiptState>())
        {
            ProductLiftWebhookReceiptState normalized = NormalizeStoredReceipt(receipt);
            if (string.IsNullOrWhiteSpace(normalized.DedupKey))
            {
                continue;
            }

            _receipts.Add(normalized);
            _receiptIdByDedupKey[normalized.DedupKey] = normalized.ReceiptId;
        }

        foreach (ProductLiftRoutingReceiptState receipt in snapshot.RoutingReceipts ?? Array.Empty<ProductLiftRoutingReceiptState>())
        {
            ProductLiftRoutingReceiptState normalized = NormalizeStoredRoutingReceipt(receipt);
            if (string.IsNullOrWhiteSpace(normalized.DedupKey))
            {
                continue;
            }

            _routingReceipts.Add(normalized);
            _routingReceiptIdByDedupKey[normalized.DedupKey] = normalized.ReceiptId;
        }

        foreach (ProductLiftCloseoutDeliveryReceiptState receipt in snapshot.CloseoutReceipts ?? Array.Empty<ProductLiftCloseoutDeliveryReceiptState>())
        {
            ProductLiftCloseoutDeliveryReceiptState normalized = NormalizeStoredCloseoutReceipt(receipt);
            if (string.IsNullOrWhiteSpace(normalized.DedupKey))
            {
                continue;
            }

            _closeoutReceipts.Add(normalized);
            _closeoutReceiptIdByDedupKey[normalized.DedupKey] = normalized.ReceiptId;
        }

        foreach (ProductLiftCloseoutDispatchReceiptState receipt in snapshot.DispatchReceipts ?? Array.Empty<ProductLiftCloseoutDispatchReceiptState>())
        {
            ProductLiftCloseoutDispatchReceiptState normalized = NormalizeStoredDispatchReceipt(receipt);
            if (string.IsNullOrWhiteSpace(normalized.DedupKey))
            {
                continue;
            }

            _dispatchReceipts.Add(normalized);
            _dispatchReceiptIdByDedupKey[normalized.DedupKey] = normalized.ReceiptId;
        }

        foreach (ProductLiftJourneyReceiptState receipt in snapshot.JourneyReceipts ?? Array.Empty<ProductLiftJourneyReceiptState>())
        {
            ProductLiftJourneyReceiptState normalized = NormalizeStoredJourneyReceipt(receipt);
            if (string.IsNullOrWhiteSpace(normalized.DedupKey))
            {
                continue;
            }

            _journeyReceipts.Add(normalized);
            _journeyReceiptIdByDedupKey[normalized.DedupKey] = normalized.ReceiptId;
        }

        foreach (ProductLiftDeliveryOutcomeReceiptState receipt in snapshot.DeliveryOutcomeReceipts ?? Array.Empty<ProductLiftDeliveryOutcomeReceiptState>())
        {
            ProductLiftDeliveryOutcomeReceiptState normalized = NormalizeStoredDeliveryOutcomeReceipt(receipt);
            if (string.IsNullOrWhiteSpace(normalized.DedupKey))
            {
                continue;
            }

            _deliveryOutcomeReceipts.Add(normalized);
            _deliveryOutcomeReceiptIdByDedupKey[normalized.DedupKey] = normalized.ReceiptId;
        }

        foreach (ProductLiftReconcileRunReceiptState run in snapshot.ReconcileRuns ?? Array.Empty<ProductLiftReconcileRunReceiptState>())
        {
            _reconcileRuns.Add(NormalizeStoredReconcileRun(run));
        }

        TrimReceiptsLocked();
    }

    private void TrimReceiptsLocked()
    {
        if (_receipts.Count > MaxStoredReceipts)
        {
            List<ProductLiftWebhookReceiptState> trimmed = _receipts
                .OrderByDescending(static receipt => receipt.ReceivedAtUtc)
                .Take(MaxStoredReceipts)
                .ToList();
            _receipts.Clear();
            _receipts.AddRange(trimmed);
            _receiptIdByDedupKey.Clear();
            foreach (ProductLiftWebhookReceiptState receipt in _receipts)
            {
                _receiptIdByDedupKey[receipt.DedupKey] = receipt.ReceiptId;
            }
        }

        TrimDerivedReceiptsLocked(_routingReceipts, _routingReceiptIdByDedupKey, static receipt => receipt.DedupKey, static receipt => receipt.ReceiptId);
        TrimDerivedReceiptsLocked(_closeoutReceipts, _closeoutReceiptIdByDedupKey, static receipt => receipt.DedupKey, static receipt => receipt.ReceiptId);
        TrimDerivedReceiptsLocked(_dispatchReceipts, _dispatchReceiptIdByDedupKey, static receipt => receipt.DedupKey, static receipt => receipt.ReceiptId);
        TrimDerivedReceiptsLocked(_journeyReceipts, _journeyReceiptIdByDedupKey, static receipt => receipt.DedupKey, static receipt => receipt.ReceiptId);
        TrimDerivedReceiptsLocked(_deliveryOutcomeReceipts, _deliveryOutcomeReceiptIdByDedupKey, static receipt => receipt.DedupKey, static receipt => receipt.ReceiptId);
        TrimOrderedReceiptsLocked(_reconcileRuns);
    }

    private static ProductLiftWebhookReceiptState NormalizeStoredReceipt(ProductLiftWebhookReceiptState receipt)
    {
        string payloadSha256 = NormalizeOptional(receipt.PayloadSha256) ?? "unknown";
        string providerEventId = NormalizeOptional(receipt.ProviderEventId) ?? $"sha256:{payloadSha256[..Math.Min(12, payloadSha256.Length)]}";
        return receipt with
        {
            ReceiptId = NormalizeOptional(receipt.ReceiptId) ?? $"plrcpt_{Guid.NewGuid():N}",
            DedupKey = NormalizeOptional(receipt.DedupKey) ?? BuildDedupKey(providerEventId, receipt.EventType, receipt.ItemReference, payloadSha256),
            ProviderEventId = providerEventId,
            EventType = NormalizeOptional(receipt.EventType) ?? "unknown",
            ActionLabel = NormalizeOptional(receipt.ActionLabel) ?? "Provider event",
            StatusLabel = NormalizeOptional(receipt.StatusLabel) ?? "Unknown",
            BoardLabel = NormalizeOptional(receipt.BoardLabel) ?? "Unassigned board",
            CategoryLabel = NormalizeOptional(receipt.CategoryLabel) ?? "Unclassified",
            ItemReference = NormalizeOptional(receipt.ItemReference) ?? "provider-event-only",
            PayloadSha256 = payloadSha256
        };
    }

    private static ProductLiftRoutingReceiptState NormalizeStoredRoutingReceipt(ProductLiftRoutingReceiptState receipt)
    {
        return receipt with
        {
            ReceiptId = NormalizeOptional(receipt.ReceiptId) ?? $"plroute_{Guid.NewGuid():N}",
            DedupKey = NormalizeOptional(receipt.DedupKey) ?? $"source:{NormalizeOptional(receipt.SourceReceiptId) ?? "unknown"}:{NormalizeOptional(receipt.RouteKind) ?? "routing"}",
            SourceReceiptId = NormalizeOptional(receipt.SourceReceiptId) ?? "unknown",
            RouteKind = NormalizeOptional(receipt.RouteKind) ?? "support_handoff",
            StatusLabel = NormalizeOptional(receipt.StatusLabel) ?? "First-party help handoff",
            TargetPath = NormalizeOptional(receipt.TargetPath) ?? "/help",
            Summary = NormalizeOptional(receipt.Summary) ?? "Public signal was redirected to a calmer first-party boundary."
        };
    }

    private static ProductLiftCloseoutDeliveryReceiptState NormalizeStoredCloseoutReceipt(ProductLiftCloseoutDeliveryReceiptState receipt)
    {
        string statusLabel = NormalizeOptional(receipt.StatusLabel) ?? "Recipient list pending";
        bool deliveryCandidate = receipt.DeliveryCandidate;
        bool voterNotificationAllowed = receipt.VoterNotificationAllowed;
        bool publicClaimAllowed = receipt.PublicClaimAllowed;

        return receipt with
        {
            ReceiptId = NormalizeOptional(receipt.ReceiptId) ?? $"plclose_{Guid.NewGuid():N}",
            DedupKey = NormalizeOptional(receipt.DedupKey) ?? $"source:{NormalizeOptional(receipt.SourceReceiptId) ?? "unknown"}:closeout",
            SourceReceiptId = NormalizeOptional(receipt.SourceReceiptId) ?? "unknown",
            StatusLabel = statusLabel,
            DeliveryState = NormalizeOptional(receipt.DeliveryState) ?? ResolveStoredCloseoutDeliveryState(statusLabel, voterNotificationAllowed),
            DeliveryLane = NormalizeOptional(receipt.DeliveryLane) ?? (deliveryCandidate
                ? "Changelog, release status, then first-party voter closeout"
                : "Changelog first, first-party voter closeout stays blocked"),
            TemplateId = NormalizeOptional(receipt.TemplateId) ?? ResolveStoredCloseoutTemplateId(statusLabel),
            RecipientScopeRef = NormalizeOptional(receipt.RecipientScopeRef) ?? DefaultProjectionSourceRef,
            RecipientScopeCount = Math.Max(0, receipt.RecipientScopeCount),
            ConsentSourceRef = NormalizeOptional(receipt.ConsentSourceRef) ?? DefaultConsentSourceRef,
            DeliveryReason = NormalizeOptional(receipt.DeliveryReason) ?? BuildStoredCloseoutDeliveryReason(statusLabel, voterNotificationAllowed, deliveryCandidate),
            Summary = NormalizeOptional(receipt.Summary) ?? "A shipped ProductLift item created a bounded first-party closeout delivery timeline without claiming an actual send.",
            VoterNotificationAllowed = voterNotificationAllowed,
            PublicClaimAllowed = publicClaimAllowed,
            ProjectedRecipientRefs = receipt.ProjectedRecipientRefs?
                .Where(static recipientRef => !string.IsNullOrWhiteSpace(recipientRef))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .OrderBy(static recipientRef => recipientRef, StringComparer.OrdinalIgnoreCase)
                .ToArray()
                ?? Array.Empty<string>()
        };
    }

    private static ProductLiftCloseoutDispatchReceiptState NormalizeStoredDispatchReceipt(ProductLiftCloseoutDispatchReceiptState receipt)
    {
        return receipt with
        {
            ReceiptId = NormalizeOptional(receipt.ReceiptId) ?? $"plsend_{Guid.NewGuid():N}",
            DedupKey = NormalizeOptional(receipt.DedupKey) ?? $"source:{NormalizeOptional(receipt.SourceReceiptId) ?? "unknown"}:dispatch",
            SourceReceiptId = NormalizeOptional(receipt.SourceReceiptId) ?? "unknown",
            StatusLabel = NormalizeOptional(receipt.StatusLabel) ?? "Send failed",
            DeliveryState = NormalizeOptional(receipt.DeliveryState) ?? "failed",
            DeliveryId = NormalizeOptional(receipt.DeliveryId) ?? "delivery-pending",
            ProviderMessageId = NormalizeOptional(receipt.ProviderMessageId),
            TemplateId = NormalizeOptional(receipt.TemplateId) ?? ProductLiftCloseoutTemplateId,
            TemplateVersion = NormalizeOptional(receipt.TemplateVersion) ?? ProductLiftCloseoutTemplateVersion,
            RecipientRef = NormalizeOptional(receipt.RecipientRef) ?? "unknown",
            AddressHash = NormalizeOptional(receipt.AddressHash) ?? "unknown",
            ConsentSourceRef = NormalizeOptional(receipt.ConsentSourceRef) ?? DefaultConsentSourceRef,
            SuppressionCheck = NormalizeOptional(receipt.SuppressionCheck) ?? "passed",
            GovernorDecisionRef = NormalizeOptional(receipt.GovernorDecisionRef) ?? DefaultGovernorDecisionSourceRef,
            ReleaseProofReceiptId = NormalizeOptional(receipt.ReleaseProofReceiptId) ?? "proof-pending",
            IdempotencyKey = NormalizeOptional(receipt.IdempotencyKey) ?? "unknown",
            Summary = NormalizeOptional(receipt.Summary) ?? "A bounded ProductLift closeout dispatch receipt was stored.",
            Error = NormalizeOptional(receipt.Error),
            RecoveryAttemptCount = Math.Max(0, receipt.RecoveryAttemptCount),
            LastRecoveryStatus = NormalizeOptional(receipt.LastRecoveryStatus),
            LastProviderState = NormalizeOptional(receipt.LastProviderState),
            NextAutomaticRetryAtUtc = receipt.NextAutomaticRetryAtUtc,
            LastOutcomeAtUtc = receipt.LastOutcomeAtUtc,
            LastRecoveryAtUtc = receipt.LastRecoveryAtUtc
        };
    }

    private static ProductLiftJourneyReceiptState NormalizeStoredJourneyReceipt(ProductLiftJourneyReceiptState receipt)
    {
        return receipt with
        {
            ReceiptId = NormalizeOptional(receipt.ReceiptId) ?? $"pljourney_{Guid.NewGuid():N}",
            DedupKey = NormalizeOptional(receipt.DedupKey) ?? $"source:{NormalizeOptional(receipt.SourceReceiptId) ?? "unknown"}:event:{NormalizeOptional(receipt.EventKey) ?? VoterNotifiedJourneyEventKey}",
            SourceReceiptId = NormalizeOptional(receipt.SourceReceiptId) ?? "unknown",
            EventKey = NormalizeOptional(receipt.EventKey) ?? VoterNotifiedJourneyEventKey,
            StatusLabel = NormalizeOptional(receipt.StatusLabel) ?? "Recorded",
            GovernorDecisionRef = NormalizeOptional(receipt.GovernorDecisionRef) ?? DefaultGovernorDecisionSourceRef,
            ReleaseProofReceiptId = NormalizeOptional(receipt.ReleaseProofReceiptId) ?? "proof-pending",
            RecipientCount = Math.Max(0, receipt.RecipientCount),
            SentCount = Math.Max(0, receipt.SentCount),
            Summary = NormalizeOptional(receipt.Summary) ?? "A bounded ProductLift journey receipt was stored."
        };
    }

    private static ProductLiftDeliveryOutcomeReceiptState NormalizeStoredDeliveryOutcomeReceipt(ProductLiftDeliveryOutcomeReceiptState receipt)
    {
        return receipt with
        {
            ReceiptId = NormalizeOptional(receipt.ReceiptId) ?? $"ploutcome_{Guid.NewGuid():N}",
            DedupKey = NormalizeOptional(receipt.DedupKey) ?? $"provider:{NormalizeOptional(receipt.Provider) ?? "unknown"}:delivery:{NormalizeOptional(receipt.DeliveryId) ?? "delivery-pending"}:state:{NormalizeOptional(receipt.ProviderState) ?? "unknown"}",
            OutcomeEventId = NormalizeOptional(receipt.OutcomeEventId) ?? "provider-event",
            Provider = NormalizeOptional(receipt.Provider) ?? "unknown",
            DispatchReceiptId = NormalizeOptional(receipt.DispatchReceiptId) ?? "unmatched",
            SourceReceiptId = NormalizeOptional(receipt.SourceReceiptId) ?? "unmatched",
            DeliveryId = NormalizeOptional(receipt.DeliveryId) ?? "delivery-pending",
            ProviderMessageId = NormalizeOptional(receipt.ProviderMessageId),
            RecipientRef = NormalizeOptional(receipt.RecipientRef) ?? "unmatched",
            AddressHash = NormalizeOptional(receipt.AddressHash) ?? "unknown",
            IdentityMatchMode = NormalizeOptional(receipt.IdentityMatchMode) ?? "unmatched",
            ProviderState = NormalizeOptional(receipt.ProviderState) ?? "unknown",
            StatusLabel = NormalizeOptional(receipt.StatusLabel) ?? "Provider callback recorded",
            SuppressionCheck = NormalizeOptional(receipt.SuppressionCheck) ?? "passed",
            RetryAtUtc = receipt.RetryAtUtc,
            Summary = NormalizeOptional(receipt.Summary) ?? "A bounded provider delivery outcome callback was recorded.",
            Reason = NormalizeOptional(receipt.Reason),
            PayloadSha256 = NormalizeOptional(receipt.PayloadSha256) ?? "unknown",
            PublicClaimAllowed = receipt.PublicClaimAllowed,
            OccurredAtUtc = receipt.OccurredAtUtc == default ? receipt.RecordedAtUtc : receipt.OccurredAtUtc,
            RecordedAtUtc = receipt.RecordedAtUtc == default ? DateTimeOffset.UtcNow : receipt.RecordedAtUtc
        };
    }

    private static ProductLiftReconcileRunReceiptState NormalizeStoredReconcileRun(ProductLiftReconcileRunReceiptState run)
    {
        return run with
        {
            RunReceiptId = NormalizeOptional(run.RunReceiptId) ?? $"plreconcile_{Guid.NewGuid():N}",
            RunKind = NormalizeOptional(run.RunKind) ?? "replay",
            Status = NormalizeOptional(run.Status) ?? "noop",
            CandidateReceiptCount = Math.Max(0, run.CandidateReceiptCount),
            ReadyCandidateCount = Math.Max(0, run.ReadyCandidateCount),
            ReplayCandidateCount = Math.Max(0, run.ReplayCandidateCount),
            DispatchReceiptsCreated = Math.Max(0, run.DispatchReceiptsCreated),
            JourneyReceiptsRecorded = Math.Max(0, run.JourneyReceiptsRecorded),
            Summary = NormalizeOptional(run.Summary) ?? "A bounded ProductLift replay run was recorded."
        };
    }

    private static void TrimDerivedReceiptsLocked<TReceipt>(
        List<TReceipt> receipts,
        Dictionary<string, string> receiptIdsByDedupKey,
        Func<TReceipt, string> dedupKeySelector,
        Func<TReceipt, string> receiptIdSelector)
    {
        if (receipts.Count > MaxStoredReceipts)
        {
            receipts.RemoveRange(MaxStoredReceipts, receipts.Count - MaxStoredReceipts);
        }

        receiptIdsByDedupKey.Clear();
        foreach (TReceipt receipt in receipts)
        {
            receiptIdsByDedupKey[dedupKeySelector(receipt)] = receiptIdSelector(receipt);
        }
    }

    private static void TrimOrderedReceiptsLocked<TReceipt>(List<TReceipt> receipts)
    {
        if (receipts.Count > MaxStoredReceipts)
        {
            receipts.RemoveRange(MaxStoredReceipts, receipts.Count - MaxStoredReceipts);
        }
    }

    private bool TryAppendRoutingReceiptLocked(
        ProductLiftWebhookReceiptState sourceReceipt,
        MatchedFeedbackCategory category,
        DateTimeOffset recordedAtUtc)
    {
        ProductLiftRoutingReceiptState? candidate = BuildRoutingReceipt(sourceReceipt, category, recordedAtUtc);
        if (candidate is null)
        {
            return false;
        }

        if (_routingReceiptIdByDedupKey.ContainsKey(candidate.DedupKey))
        {
            return false;
        }

        _routingReceipts.Add(candidate);
        _routingReceiptIdByDedupKey[candidate.DedupKey] = candidate.ReceiptId;
        _routingReceipts.Sort(static (left, right) => right.RecordedAtUtc.CompareTo(left.RecordedAtUtc));
        return true;
    }

    private bool TryAppendCloseoutReceiptLocked(
        ProductLiftWebhookReceiptState sourceReceipt,
        MatchedFeedbackCategory category,
        OperationsCanonDocument canonDocument,
        CloseoutRuntimeReadiness readiness,
        DateTimeOffset recordedAtUtc)
    {
        ProductLiftCloseoutDeliveryReceiptState? candidate = BuildCloseoutReceipt(sourceReceipt, category, canonDocument, readiness, recordedAtUtc);
        if (candidate is null)
        {
            return false;
        }

        if (_closeoutReceiptIdByDedupKey.ContainsKey(candidate.DedupKey))
        {
            return false;
        }

        _closeoutReceipts.Add(candidate);
        _closeoutReceiptIdByDedupKey[candidate.DedupKey] = candidate.ReceiptId;
        _closeoutReceipts.Sort(static (left, right) => right.RecordedAtUtc.CompareTo(left.RecordedAtUtc));
        return true;
    }

    private int FindRoutingReceiptCount(string sourceReceiptId)
        => _routingReceipts.Count(receipt => string.Equals(receipt.SourceReceiptId, sourceReceiptId, StringComparison.OrdinalIgnoreCase));

    private int FindCloseoutReceiptCount(string sourceReceiptId)
        => _closeoutReceipts.Count(receipt => string.Equals(receipt.SourceReceiptId, sourceReceiptId, StringComparison.OrdinalIgnoreCase));

    private ProductLiftRoutingReceiptState? BuildRoutingReceipt(
        ProductLiftWebhookReceiptState sourceReceipt,
        MatchedFeedbackCategory category,
        DateTimeOffset recordedAtUtc)
    {
        if (!category.SupportMisrouteLikely && !category.PrivacySensitive)
        {
            return null;
        }

        string routeKind;
        string statusLabel;
        string targetPath;
        if (category.PrivacySensitive)
        {
            routeKind = "moderation_review";
            statusLabel = category.SupportMisrouteLikely ? "Moderation and help handoff" : "Moderation review required";
            targetPath = "/contact#support-intake";
        }
        else
        {
            routeKind = "support_handoff";
            statusLabel = "First-party help handoff";
            targetPath = ResolveSupportTargetPath(category);
        }

        return new ProductLiftRoutingReceiptState(
            ReceiptId: $"plroute_{Guid.NewGuid():N}",
            DedupKey: $"source:{sourceReceipt.ReceiptId}:{routeKind}",
            SourceReceiptId: sourceReceipt.ReceiptId,
            RouteKind: routeKind,
            StatusLabel: statusLabel,
            TargetPath: targetPath,
            Summary: BuildRoutingSummary(sourceReceipt, category, targetPath),
            RecordedAtUtc: recordedAtUtc);
    }

    private ProductLiftCloseoutDeliveryReceiptState? BuildCloseoutReceipt(
        ProductLiftWebhookReceiptState sourceReceipt,
        MatchedFeedbackCategory category,
        OperationsCanonDocument canonDocument,
        CloseoutRuntimeReadiness readiness,
        DateTimeOffset recordedAtUtc)
    {
        if (!sourceReceipt.CloseoutCandidate)
        {
            return null;
        }

        bool deliveryAdapterConfigured = HasCloseoutDeliveryAdapterConfigured();
        bool deliveryCandidate = canonDocument.CloseoutFamilyReady
            && sourceReceipt.VoterNotificationAllowed
            && deliveryAdapterConfigured;
        deliveryCandidate = deliveryCandidate
            && readiness.OwnerReady
            && readiness.ProjectionConfigured
            && readiness.ProjectedRecipientCount > 0
            && readiness.ConsentConfigured
            && readiness.QueueConfigured;
        string deliveryState = ResolveCloseoutDeliveryState(
            canonDocument.CloseoutFamilyReady,
            sourceReceipt.VoterNotificationAllowed);
        string statusLabel = ResolveCloseoutDeliveryStatusLabel(
            canonDocument.CloseoutFamilyReady,
            sourceReceipt.VoterNotificationAllowed,
            deliveryAdapterConfigured,
            readiness.OwnerReady,
            readiness.ProjectionConfigured,
            readiness.ProjectedRecipientCount,
            readiness.ConsentConfigured,
            readiness.QueueConfigured);
        string templateId = canonDocument.CloseoutFamilyReady
            ? "productlift_voter_shipped"
            : "unassigned";
        string deliveryReason = BuildCloseoutDeliveryReason(
            sourceReceipt,
            canonDocument.CloseoutFamilyReady,
            deliveryAdapterConfigured,
            readiness);

        return new ProductLiftCloseoutDeliveryReceiptState(
            ReceiptId: $"plclose_{Guid.NewGuid():N}",
            DedupKey: $"source:{sourceReceipt.ReceiptId}:closeout",
            SourceReceiptId: sourceReceipt.ReceiptId,
            StatusLabel: statusLabel,
            DeliveryState: deliveryState,
            DeliveryLane: deliveryCandidate
                ? "Changelog, release status, then first-party voter closeout"
                : "Changelog first, first-party voter closeout stays blocked",
            TemplateId: templateId,
            RecipientScopeRef: readiness.ProjectionSourceRef,
            RecipientScopeCount: readiness.ProjectedRecipientCount,
            ConsentSourceRef: readiness.ConsentSourceRef,
            DeliveryReason: deliveryReason,
            Summary: BuildCloseoutSummary(sourceReceipt, category, canonDocument.CloseoutFamilyReady, deliveryAdapterConfigured),
            VoterNotificationAllowed: sourceReceipt.VoterNotificationAllowed,
            DeliveryCandidate: deliveryCandidate,
            PublicClaimAllowed: false,
            ProjectedRecipientRefs: readiness.Recipients
                .Select(static recipient => recipient.UserId)
                .Where(static recipientRef => !string.IsNullOrWhiteSpace(recipientRef))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .OrderBy(static recipientRef => recipientRef, StringComparer.OrdinalIgnoreCase)
                .ToArray(),
            RecordedAtUtc: recordedAtUtc);
    }

    private PublicSignalCloseoutQueueReceiptViewModel BuildCloseoutQueueReceipt(
        ProductLiftWebhookReceiptState sourceReceipt,
        OperationsCanonDocument canonDocument,
        CloseoutRuntimeReadiness readiness)
    {
        SourceHotFilterSummary hotFilter = ResolveSourceHotFilter(sourceReceipt);
        bool deliveryAdapterConfigured = HasCloseoutDeliveryAdapterConfigured();
        bool readyForOutbox = canonDocument.CloseoutFamilyReady
            && sourceReceipt.VoterNotificationAllowed
            && deliveryAdapterConfigured
            && readiness.OwnerReady
            && readiness.ProjectionConfigured
            && readiness.ProjectedRecipientCount > 0
            && readiness.ConsentConfigured
            && readiness.QueueConfigured
            && readiness.GovernorApproved
            && readiness.ReleaseProofReady;
        string statusLabel = ResolveCloseoutQueueStatusLabel(
            canonDocument.CloseoutFamilyReady,
            sourceReceipt.VoterNotificationAllowed,
            deliveryAdapterConfigured,
            readiness);
        string queueReason = BuildCloseoutQueueReason(
            sourceReceipt,
            canonDocument.CloseoutFamilyReady,
            deliveryAdapterConfigured,
            readiness,
            readyForOutbox);

        return new PublicSignalCloseoutQueueReceiptViewModel(
            ReceiptId: BuildCloseoutQueueReceiptId(sourceReceipt, readiness, statusLabel),
            SourceReceiptId: sourceReceipt.ReceiptId,
            StatusLabel: statusLabel,
            QueueState: readyForOutbox ? "ready" : "blocked",
            QueueLane: "First-party outbox candidate, connector.dispatch, then voter_notified journey record",
            DispatchTool: ConnectorDispatchToolName,
            DispatchAction: ConnectorDispatchActionName,
            JourneyEventKey: VoterNotifiedJourneyEventKey,
            GovernorDecisionRef: readiness.GovernorDecisionRef,
            ReleaseProofRoute: readiness.ReleaseProofRoute,
            ReleaseProofReceiptId: readiness.ReleaseProofReceiptId,
            QueueReason: queueReason,
            Summary: BuildCloseoutQueueSummary(sourceReceipt, readiness, readyForOutbox),
            ReadyForOutbox: readyForOutbox,
            PublicClaimAllowed: false,
            SourceHotFilterKey: hotFilter.FilterKey,
            SourceHotFilterLabel: hotFilter.FilterLabel,
            SourceHotFilterCount: hotFilter.Count,
            SourceHotFilterSummary: hotFilter.Summary,
            RecordedAtUtc: sourceReceipt.ReceivedAtUtc);
    }

    private void TryMaterializeCloseoutDispatch(
        ProductLiftWebhookReceiptState sourceReceipt,
        OperationsCanonDocument canonDocument,
        CloseoutRuntimeReadiness readiness,
        bool allowCurrentAudienceFallback = true)
    {
        PublicSignalCloseoutQueueReceiptViewModel candidate = BuildCloseoutQueueReceipt(sourceReceipt, canonDocument, readiness);
        if (!candidate.ReadyForOutbox)
        {
            return;
        }

        string? governorDecisionRef = NormalizeOptional(readiness.GovernorDecisionRef);
        string? releaseProofReceiptId = NormalizeOptional(readiness.ReleaseProofReceiptId);
        if (governorDecisionRef is null || releaseProofReceiptId is null)
        {
            return;
        }

        List<ProjectedCloseoutRecipient> recipients = ResolveDispatchRecipients(sourceReceipt, readiness, allowCurrentAudienceFallback);
        if (recipients.Count == 0)
        {
            return;
        }

        List<ProductLiftCloseoutDispatchReceiptState> sentReceipts = [];
        foreach (ProjectedCloseoutRecipient recipient in recipients)
        {
            ProductLiftCloseoutDispatchReceiptState? existing = FindDispatchReceipt(sourceReceipt.ReceiptId, recipient.UserId, governorDecisionRef, releaseProofReceiptId);
            if (existing is not null)
            {
                if (string.Equals(existing.DeliveryState, "sent", StringComparison.OrdinalIgnoreCase))
                {
                    sentReceipts.Add(existing);
                }

                continue;
            }

            ProductLiftCloseoutDispatchReceiptState created = MaterializeDispatchReceipt(
                sourceReceipt,
                recipient,
                readiness,
                governorDecisionRef,
                releaseProofReceiptId);

            if (string.Equals(created.DeliveryState, "sent", StringComparison.OrdinalIgnoreCase))
            {
                sentReceipts.Add(created);
            }
        }

        if (sentReceipts.Count == recipients.Count && recipients.Count > 0)
        {
            TryAppendJourneyReceipt(sourceReceipt, governorDecisionRef, releaseProofReceiptId, recipients.Count, sentReceipts.Count);
        }
    }

    private ProductLiftCloseoutDeliveryReceiptState? FindCloseoutReceipt(string sourceReceiptId)
    {
        lock (_gate)
        {
            return FindCloseoutReceiptLocked(sourceReceiptId);
        }
    }

    private ProductLiftCloseoutDeliveryReceiptState? FindCloseoutReceiptLocked(string sourceReceiptId)
        => _closeoutReceipts.FirstOrDefault(receipt => string.Equals(receipt.SourceReceiptId, sourceReceiptId, StringComparison.OrdinalIgnoreCase));

    private List<ProjectedCloseoutRecipient> ResolveDispatchRecipients(
        ProductLiftWebhookReceiptState sourceReceipt,
        CloseoutRuntimeReadiness readiness,
        bool allowCurrentAudienceFallback)
    {
        ProductLiftCloseoutDeliveryReceiptState? closeoutReceipt = FindCloseoutReceipt(sourceReceipt.ReceiptId);
        List<ProjectedCloseoutRecipient> storedRecipients = ResolveStoredRecipientAudience(closeoutReceipt);
        if (storedRecipients.Count > 0)
        {
            return storedRecipients;
        }

        return allowCurrentAudienceFallback
            ? readiness.Recipients
                .OrderBy(static recipient => recipient.UserId, StringComparer.OrdinalIgnoreCase)
                .ToList()
            : [];
    }

    private List<ProjectedCloseoutRecipient> ResolveStoredRecipientAudience(ProductLiftCloseoutDeliveryReceiptState? closeoutReceipt)
    {
        string[] storedRecipientRefs = closeoutReceipt?.ProjectedRecipientRefs?
            .Where(static recipientRef => !string.IsNullOrWhiteSpace(recipientRef))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray()
            ?? Array.Empty<string>();
        if (storedRecipientRefs.Length == 0)
        {
            return [];
        }

        lock (_communityStore.Gate)
        {
            Dictionary<string, string> verifiedEmailByUserId = _communityStore.LinkedIdentities
                .Where(static link =>
                    string.Equals(link.Provider, "email", StringComparison.OrdinalIgnoreCase)
                    && string.Equals(link.Status, "verified", StringComparison.OrdinalIgnoreCase))
                .Where(static link => !string.IsNullOrWhiteSpace(link.UserId))
                .OrderByDescending(static link => link.VerifiedAtUtc ?? link.UpdatedAtUtc)
                .GroupBy(static link => link.UserId, StringComparer.OrdinalIgnoreCase)
                .ToDictionary(
                    static group => group.Key,
                    static group => group
                        .Select(link => NormalizeOptional(link.DisplayLabel))
                        .FirstOrDefault(static value => !string.IsNullOrWhiteSpace(value))
                        ?? string.Empty,
                    StringComparer.OrdinalIgnoreCase);

            List<ProjectedCloseoutRecipient> recipients = storedRecipientRefs
                .Where(recipientRef =>
                    verifiedEmailByUserId.TryGetValue(recipientRef, out string? email)
                    && !string.IsNullOrWhiteSpace(email)
                    && _communityStore.UsersById.TryGetValue(recipientRef, out _))
                .Select(recipientRef =>
                {
                    HubUserDto user = _communityStore.UsersById[recipientRef];
                    string email = verifiedEmailByUserId[recipientRef];
                    return new ProjectedCloseoutRecipient(
                        UserId: user.UserId,
                        SubjectId: user.SubjectId,
                        Email: email,
                        AddressHash: ComputeSha256Hex(email.Trim().ToLowerInvariant()));
                })
                .OrderBy(static recipient => recipient.UserId, StringComparer.OrdinalIgnoreCase)
                .ToList();

            return recipients;
        }
    }

    private bool NeedsDispatchReplay(
        ProductLiftWebhookReceiptState sourceReceipt,
        CloseoutRuntimeReadiness readiness,
        OperationsCanonDocument canonDocument)
    {
        lock (_gate)
        {
            return NeedsDispatchReplayLocked(sourceReceipt, readiness, canonDocument);
        }
    }

    private bool NeedsDispatchReplayLocked(
        ProductLiftWebhookReceiptState sourceReceipt,
        CloseoutRuntimeReadiness readiness,
        OperationsCanonDocument canonDocument)
    {
        PublicSignalCloseoutQueueReceiptViewModel candidate = BuildCloseoutQueueReceipt(sourceReceipt, canonDocument, readiness);
        if (!candidate.ReadyForOutbox)
        {
            return false;
        }

        string? governorDecisionRef = NormalizeOptional(readiness.GovernorDecisionRef);
        string? releaseProofReceiptId = NormalizeOptional(readiness.ReleaseProofReceiptId);
        if (governorDecisionRef is null || releaseProofReceiptId is null)
        {
            return false;
        }

        List<ProjectedCloseoutRecipient> recipients = ResolveStoredRecipientAudience(FindCloseoutReceiptLocked(sourceReceipt.ReceiptId));
        if (recipients.Count == 0)
        {
            return false;
        }

        foreach (ProjectedCloseoutRecipient recipient in recipients)
        {
            string dispatchDedupKey = BuildDispatchDedupKey(sourceReceipt.ReceiptId, recipient.UserId, governorDecisionRef, releaseProofReceiptId);
            if (!_dispatchReceiptIdByDedupKey.TryGetValue(dispatchDedupKey, out string? dispatchReceiptId))
            {
                return true;
            }

            ProductLiftCloseoutDispatchReceiptState? dispatchReceipt = _dispatchReceipts
                .FirstOrDefault(item => string.Equals(item.ReceiptId, dispatchReceiptId, StringComparison.OrdinalIgnoreCase));
            if (dispatchReceipt is null)
            {
                return true;
            }

            if (!string.Equals(dispatchReceipt.DeliveryState, "sent", StringComparison.OrdinalIgnoreCase))
            {
                return false;
            }
        }

        string journeyDedupKey = $"source:{sourceReceipt.ReceiptId}:event:{VoterNotifiedJourneyEventKey}:decision:{governorDecisionRef}:proof:{releaseProofReceiptId}";
        return !_journeyReceiptIdByDedupKey.ContainsKey(journeyDedupKey);
    }

    private ProductLiftCloseoutDispatchReceiptState MaterializeDispatchReceipt(
        ProductLiftWebhookReceiptState sourceReceipt,
        ProjectedCloseoutRecipient recipient,
        CloseoutRuntimeReadiness readiness,
        string governorDecisionRef,
        string releaseProofReceiptId)
    {
        string receiptId = $"plsend_{Guid.NewGuid():N}";
        string dedupKey = BuildDispatchDedupKey(sourceReceipt.ReceiptId, recipient.UserId, governorDecisionRef, releaseProofReceiptId);
        string subject = BuildCloseoutSubject(sourceReceipt);
        string content = BuildCloseoutContent(sourceReceipt, readiness, governorDecisionRef, releaseProofReceiptId);
        string idempotencyKey = BuildCloseoutIdempotencyKey(sourceReceipt, recipient, governorDecisionRef, releaseProofReceiptId);
        DateTimeOffset requestedAtUtc = DateTimeOffset.UtcNow;

        string? deliveryId = null;
        string? providerMessageId = null;
        string deliveryState = "failed";
        string statusLabel = "Send failed";
        string summary;
        string? error = null;
        DateTimeOffset? acceptedAtUtc = null;
        string suppressionCheck = "passed";

        try
        {
            deliveryId = QueueCloseoutDelivery(
                recipient,
                sourceReceipt,
                subject,
                content,
                readiness,
                governorDecisionRef,
                releaseProofReceiptId,
                idempotencyKey);
            providerMessageId = SendCloseoutEmail(
                recipient,
                sourceReceipt,
                subject,
                content,
                idempotencyKey,
                deliveryId);
            acceptedAtUtc = DateTimeOffset.UtcNow;

            try
            {
                MarkCloseoutSent(deliveryId, recipient, sourceReceipt, subject, providerMessageId);
                deliveryState = "sent";
                statusLabel = "Sent";
                summary = $"Hub queued and marked sent a bounded ProductLift closeout for {recipient.UserId} from source receipt {sourceReceipt.ReceiptId}.";
            }
            catch (Exception ex)
            {
                error = Truncate(ex.Message, 600);
                deliveryState = "accepted";
                statusLabel = "Provider accepted";
                summary = $"Emailit accepted a bounded ProductLift closeout for {recipient.UserId}, but Hub could not finish the outbox sent receipt.";
                suppressionCheck = "passed";
            }
        }
        catch (Exception ex)
        {
            error = Truncate(ex.Message, 600);
            suppressionCheck = ResolveSuppressionCheck(error, !string.IsNullOrWhiteSpace(deliveryId));
            summary = $"Hub could not complete the bounded ProductLift closeout send for {recipient.UserId} from source receipt {sourceReceipt.ReceiptId}.";
            if (!string.IsNullOrWhiteSpace(deliveryId))
            {
                TryMarkCloseoutFailed(deliveryId, error);
            }
        }

        ProductLiftCloseoutDispatchReceiptState receipt = new(
            ReceiptId: receiptId,
            DedupKey: dedupKey,
            SourceReceiptId: sourceReceipt.ReceiptId,
            StatusLabel: statusLabel,
            DeliveryState: deliveryState,
            DeliveryId: deliveryId ?? "delivery-pending",
            ProviderMessageId: providerMessageId,
            TemplateId: ProductLiftCloseoutTemplateId,
            TemplateVersion: ProductLiftCloseoutTemplateVersion,
            RecipientRef: recipient.UserId,
            AddressHash: recipient.AddressHash,
            ConsentSourceRef: readiness.ConsentSourceRef,
            SuppressionCheck: suppressionCheck,
            GovernorDecisionRef: governorDecisionRef,
            ReleaseProofReceiptId: releaseProofReceiptId,
            IdempotencyKey: idempotencyKey,
            Summary: summary,
            Error: error,
            PublicClaimAllowed: false,
            RecoveryAttemptCount: 0,
            LastRecoveryStatus: null,
            LastProviderState: null,
            NextAutomaticRetryAtUtc: null,
            LastOutcomeAtUtc: null,
            RequestedAtUtc: requestedAtUtc,
            AcceptedAtUtc: acceptedAtUtc,
            LastRecoveryAtUtc: null);

        lock (_gate)
        {
            if (_dispatchReceiptIdByDedupKey.ContainsKey(dedupKey))
            {
                string existingId = _dispatchReceiptIdByDedupKey[dedupKey];
                return _dispatchReceipts.First(item => string.Equals(item.ReceiptId, existingId, StringComparison.OrdinalIgnoreCase));
            }

            _dispatchReceipts.Add(receipt);
            _dispatchReceipts.Sort(static (left, right) => right.RequestedAtUtc.CompareTo(left.RequestedAtUtc));
            _dispatchReceiptIdByDedupKey[dedupKey] = receipt.ReceiptId;
            TrimReceiptsLocked();
            PersistLocked();
        }

        return receipt;
    }

    private ProductLiftCloseoutDispatchReceiptState? FindDispatchReceipt(
        string sourceReceiptId,
        string recipientRef,
        string governorDecisionRef,
        string releaseProofReceiptId)
    {
        string dedupKey = BuildDispatchDedupKey(sourceReceiptId, recipientRef, governorDecisionRef, releaseProofReceiptId);
        lock (_gate)
        {
            if (!_dispatchReceiptIdByDedupKey.TryGetValue(dedupKey, out string? receiptId))
            {
                return null;
            }

            return _dispatchReceipts.FirstOrDefault(item => string.Equals(item.ReceiptId, receiptId, StringComparison.OrdinalIgnoreCase));
        }
    }

    private void TryAppendJourneyReceipt(
        ProductLiftWebhookReceiptState sourceReceipt,
        string governorDecisionRef,
        string releaseProofReceiptId,
        int recipientCount,
        int sentCount)
    {
        string dedupKey = $"source:{sourceReceipt.ReceiptId}:event:{VoterNotifiedJourneyEventKey}:decision:{governorDecisionRef}:proof:{releaseProofReceiptId}";
        lock (_gate)
        {
            if (_journeyReceiptIdByDedupKey.ContainsKey(dedupKey))
            {
                return;
            }

            ProductLiftJourneyReceiptState receipt = new(
                ReceiptId: $"pljourney_{Guid.NewGuid():N}",
                DedupKey: dedupKey,
                SourceReceiptId: sourceReceipt.ReceiptId,
                EventKey: VoterNotifiedJourneyEventKey,
                StatusLabel: "Recorded",
                GovernorDecisionRef: governorDecisionRef,
                ReleaseProofReceiptId: releaseProofReceiptId,
                RecipientCount: recipientCount,
                SentCount: sentCount,
                Summary: $"Hub wrote a bounded {VoterNotifiedJourneyEventKey} journey receipt from ProductLift source receipt {sourceReceipt.ReceiptId} after {sentCount} of {recipientCount} first-party closeout send(s) completed.",
                PublicClaimAllowed: false,
                RecordedAtUtc: DateTimeOffset.UtcNow);
            _journeyReceipts.Add(receipt);
            _journeyReceipts.Sort(static (left, right) => right.RecordedAtUtc.CompareTo(left.RecordedAtUtc));
            _journeyReceiptIdByDedupKey[dedupKey] = receipt.ReceiptId;
            TrimReceiptsLocked();
            PersistLocked();
        }
    }

    private ProductLiftReconcileRunReceiptState RecordReconcileRun(
        string status,
        int candidateReceiptCount,
        int readyCandidateCount,
        int replayCandidateCount,
        int dispatchReceiptsCreated,
        int journeyReceiptsRecorded,
        DateTimeOffset recordedAtUtc)
    {
        string summary = status switch
        {
            "replayed" => $"Replay materialized {dispatchReceiptsCreated} bounded closeout dispatch update(s) and {journeyReceiptsRecorded} journey update(s) from {replayCandidateCount} ready ProductLift source item(s).",
            "ready_without_new_receipts" => $"Replay inspected {replayCandidateCount} ready ProductLift source item(s), but no new bounded dispatch or journey updates were needed.",
            _ => $"Replay found no ready ProductLift closeout source items that still needed bounded dispatch materialization."
        };
        ProductLiftReconcileRunReceiptState run = new(
            RunReceiptId: $"plreconcile_{Guid.NewGuid():N}",
            RunKind: "replay",
            Status: status,
            CandidateReceiptCount: candidateReceiptCount,
            ReadyCandidateCount: readyCandidateCount,
            ReplayCandidateCount: replayCandidateCount,
            DispatchReceiptsCreated: dispatchReceiptsCreated,
            JourneyReceiptsRecorded: journeyReceiptsRecorded,
            Summary: summary,
            RecordedAtUtc: recordedAtUtc);

        lock (_gate)
        {
            _reconcileRuns.Add(run);
            _reconcileRuns.Sort(static (left, right) => right.RecordedAtUtc.CompareTo(left.RecordedAtUtc));
            TrimReceiptsLocked();
            PersistLocked();
        }

        return run;
    }

    private ProductLiftReconcileRunReceiptState RecordDispatchRecoveryRun(
        string runKind,
        string status,
        int candidateReceiptCount,
        int recoveredReceiptCount,
        int suppressedReceiptCount,
        int blockedReceiptCount,
        DateTimeOffset recordedAtUtc)
    {
        bool retryExpiryRun = string.Equals(runKind, "retry_expiry", StringComparison.Ordinal);
        string subjectLabel = retryExpiryRun ? "Automatic retry expiry sweep" : "Dispatch recovery";
        string summary = status switch
        {
            "recovered" => $"{subjectLabel} finalized {recoveredReceiptCount} bounded closeout receipt(s), held {suppressedReceiptCount} under suppression, and left {blockedReceiptCount} blocked.",
            "suppressed_only" => $"{subjectLabel} found only suppression-held ProductLift closeout receipt(s); {suppressedReceiptCount} stayed out of retry.",
            "blocked" => $"{subjectLabel} inspected {candidateReceiptCount} candidate receipt(s), but none could be finalized without broadening the bounded delivery contract.",
            _ => retryExpiryRun
                ? "Automatic retry expiry sweep found no bounded provider retry hold whose window had expired."
                : "Dispatch recovery found no bounded closeout delivery receipt that still needed recovery work."
        };
        ProductLiftReconcileRunReceiptState run = new(
            RunReceiptId: $"plrecover_{Guid.NewGuid():N}",
            RunKind: runKind,
            Status: status,
            CandidateReceiptCount: candidateReceiptCount,
            ReadyCandidateCount: recoveredReceiptCount,
            ReplayCandidateCount: suppressedReceiptCount,
            DispatchReceiptsCreated: recoveredReceiptCount,
            JourneyReceiptsRecorded: blockedReceiptCount,
            Summary: summary,
            RecordedAtUtc: recordedAtUtc);

        lock (_gate)
        {
            _reconcileRuns.Add(run);
            _reconcileRuns.Sort(static (left, right) => right.RecordedAtUtc.CompareTo(left.RecordedAtUtc));
            TrimReceiptsLocked();
            PersistLocked();
        }

        return run;
    }

    private List<DispatchRecoveryCandidate> BuildDispatchRecoveryCandidates(bool expiredRetryWindowOnly)
    {
        List<DispatchRecoveryCandidate> candidates = [];
        DateTimeOffset now = DateTimeOffset.UtcNow;
        lock (_gate)
        {
            foreach (ProductLiftCloseoutDispatchReceiptState receipt in _dispatchReceipts
                         .OrderBy(static item => item.RequestedAtUtc))
            {
                if (string.Equals(receipt.DeliveryState, "sent", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                ProductLiftWebhookReceiptState? sourceReceipt = _receipts
                    .FirstOrDefault(item => string.Equals(item.ReceiptId, receipt.SourceReceiptId, StringComparison.OrdinalIgnoreCase));
                if (sourceReceipt is null)
                {
                    continue;
                }

                if (string.Equals(receipt.SuppressionCheck, "suppressed", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                bool retryWindowExpired = receipt.NextAutomaticRetryAtUtc is not null && receipt.NextAutomaticRetryAtUtc <= now;
                if (expiredRetryWindowOnly && !retryWindowExpired)
                {
                    continue;
                }

                if (string.Equals(receipt.DeliveryState, "accepted", StringComparison.OrdinalIgnoreCase))
                {
                    if (receipt.NextAutomaticRetryAtUtc is not null && receipt.NextAutomaticRetryAtUtc > now)
                    {
                        continue;
                    }

                    candidates.Add(new DispatchRecoveryCandidate(receipt, sourceReceipt, Recipient: null, Mode: "mark_sent"));
                    continue;
                }

                if (!string.Equals(receipt.DeliveryState, "failed", StringComparison.OrdinalIgnoreCase)
                    && !string.Equals(receipt.DeliveryState, "retrying", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(receipt.DeliveryId, "delivery-pending", StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                if (receipt.NextAutomaticRetryAtUtc is not null && receipt.NextAutomaticRetryAtUtc > now)
                {
                    continue;
                }

                ProjectedCloseoutRecipient? recipient = ResolveStoredRecipientAudience(FindCloseoutReceiptLocked(sourceReceipt.ReceiptId))
                    .FirstOrDefault(item => string.Equals(item.UserId, receipt.RecipientRef, StringComparison.OrdinalIgnoreCase));
                candidates.Add(new DispatchRecoveryCandidate(receipt, sourceReceipt, recipient, recipient is null ? "blocked" : "retry_send"));
            }
        }

        return candidates;
    }

    private DispatchRecoveryOutcome RecoverDispatchCandidate(DispatchRecoveryCandidate candidate)
    {
        return candidate.Mode switch
        {
            "suppressed" => UpdateRecoveryBlocked(candidate.Receipt, "Suppressed hold", "suppressed_hold") is not null
                ? DispatchRecoveryOutcome.Suppressed
                : DispatchRecoveryOutcome.Blocked,
            "mark_sent" => RecoverAcceptedDispatch(candidate),
            "retry_send" => RecoverFailedDispatch(candidate),
            _ => UpdateRecoveryBlocked(candidate.Receipt, "Recipient resolution blocked", "blocked") is not null
                ? DispatchRecoveryOutcome.Blocked
                : DispatchRecoveryOutcome.Blocked
        };
    }

    private DispatchRecoveryOutcome RecoverAcceptedDispatch(DispatchRecoveryCandidate candidate)
    {
        try
        {
            MarkCloseoutSentFromStoredDispatch(candidate.Receipt, candidate.SourceReceipt);
            DateTimeOffset recoveredAtUtc = DateTimeOffset.UtcNow;
            UpdateDispatchReceipt(candidate.Receipt.ReceiptId, existing => existing with
            {
                StatusLabel = "Sent after recovery",
                DeliveryState = "sent",
                ProviderMessageId = NormalizeOptional(existing.ProviderMessageId) ?? existing.DeliveryId,
                Summary = $"Dispatch recovery finished the first-party outbox sent record for {existing.RecipientRef} from source record {existing.SourceReceiptId}.",
                Error = null,
                SuppressionCheck = "passed",
                RecoveryAttemptCount = existing.RecoveryAttemptCount + 1,
                LastRecoveryStatus = "sent_mark_recovered",
                LastRecoveryAtUtc = recoveredAtUtc,
                AcceptedAtUtc = existing.AcceptedAtUtc ?? recoveredAtUtc
            });
            TryAppendJourneyReceiptIfDispatchComplete(
                candidate.SourceReceipt,
                candidate.Receipt.GovernorDecisionRef,
                candidate.Receipt.ReleaseProofReceiptId);
            return DispatchRecoveryOutcome.Recovered;
        }
        catch (Exception ex)
        {
            UpdateDispatchReceipt(candidate.Receipt.ReceiptId, existing => existing with
            {
                Error = Truncate(ex.Message, 600),
                RecoveryAttemptCount = existing.RecoveryAttemptCount + 1,
                LastRecoveryStatus = "mark_sent_failed",
                LastRecoveryAtUtc = DateTimeOffset.UtcNow
            });
            return DispatchRecoveryOutcome.Blocked;
        }
    }

    private DispatchRecoveryOutcome RecoverFailedDispatch(DispatchRecoveryCandidate candidate)
    {
        if (candidate.Recipient is null)
        {
            UpdateRecoveryBlocked(candidate.Receipt, "Recipient resolution blocked", "recipient_missing");
            return DispatchRecoveryOutcome.Blocked;
        }

        try
        {
            string subject = BuildCloseoutSubject(candidate.SourceReceipt);
            string content = BuildCloseoutContent(
                candidate.SourceReceipt,
                ResolveCurrentFollowSettingsPath(),
                candidate.Receipt.GovernorDecisionRef,
                candidate.Receipt.ReleaseProofReceiptId);
            string providerMessageId = SendCloseoutEmail(
                candidate.Recipient,
                candidate.SourceReceipt,
                subject,
                content,
                candidate.Receipt.IdempotencyKey,
                candidate.Receipt.DeliveryId);
            MarkCloseoutSentFromStoredDispatch(candidate.Receipt, candidate.SourceReceipt, providerMessageId);
            DateTimeOffset recoveredAtUtc = DateTimeOffset.UtcNow;
            UpdateDispatchReceipt(candidate.Receipt.ReceiptId, existing => existing with
            {
                StatusLabel = "Sent after recovery",
                DeliveryState = "sent",
                ProviderMessageId = providerMessageId,
                Summary = $"Dispatch recovery retried the bounded ProductLift closeout for {existing.RecipientRef} and completed the first-party outbox sent record.",
                Error = null,
                SuppressionCheck = "passed",
                RecoveryAttemptCount = existing.RecoveryAttemptCount + 1,
                LastRecoveryStatus = "retry_sent",
                LastRecoveryAtUtc = recoveredAtUtc,
                AcceptedAtUtc = existing.AcceptedAtUtc ?? recoveredAtUtc
            });
            TryAppendJourneyReceiptIfDispatchComplete(
                candidate.SourceReceipt,
                candidate.Receipt.GovernorDecisionRef,
                candidate.Receipt.ReleaseProofReceiptId);
            return DispatchRecoveryOutcome.Recovered;
        }
        catch (Exception ex)
        {
            string error = Truncate(ex.Message, 600);
            string suppressionCheck = ResolveSuppressionCheck(error, hasDeliveryId: true);
            UpdateDispatchReceipt(candidate.Receipt.ReceiptId, existing => existing with
            {
                Error = error,
                SuppressionCheck = suppressionCheck,
                RecoveryAttemptCount = existing.RecoveryAttemptCount + 1,
                LastRecoveryStatus = string.Equals(suppressionCheck, "suppressed", StringComparison.OrdinalIgnoreCase)
                    ? "suppressed_during_retry"
                    : "retry_failed",
                LastRecoveryAtUtc = DateTimeOffset.UtcNow
            });
            return string.Equals(suppressionCheck, "suppressed", StringComparison.OrdinalIgnoreCase)
                ? DispatchRecoveryOutcome.Suppressed
                : DispatchRecoveryOutcome.Blocked;
        }
    }

    private ProductLiftCloseoutDispatchReceiptState? UpdateRecoveryBlocked(
        ProductLiftCloseoutDispatchReceiptState receipt,
        string summaryLabel,
        string recoveryStatus)
        => UpdateDispatchReceipt(receipt.ReceiptId, existing => existing with
        {
            Summary = $"{summaryLabel}. The bounded ProductLift closeout receipt for {existing.RecipientRef} remains out of automatic recovery.",
            RecoveryAttemptCount = existing.RecoveryAttemptCount + 1,
            LastRecoveryStatus = recoveryStatus,
            LastRecoveryAtUtc = DateTimeOffset.UtcNow
        });

    private void TryAppendJourneyReceiptIfDispatchComplete(
        ProductLiftWebhookReceiptState sourceReceipt,
        string governorDecisionRef,
        string releaseProofReceiptId)
    {
        ProductLiftCloseoutDeliveryReceiptState? closeoutReceipt = FindCloseoutReceipt(sourceReceipt.ReceiptId);
        List<string> recipientRefs = closeoutReceipt?.ProjectedRecipientRefs?
            .Where(static recipientRef => !string.IsNullOrWhiteSpace(recipientRef))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList()
            ?? [];
        if (recipientRefs.Count == 0)
        {
            return;
        }

        lock (_gate)
        {
            List<ProductLiftCloseoutDispatchReceiptState> matchingReceipts = recipientRefs
                .Select(recipientRef => _dispatchReceipts.FirstOrDefault(dispatch =>
                    string.Equals(dispatch.SourceReceiptId, sourceReceipt.ReceiptId, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(dispatch.RecipientRef, recipientRef, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(dispatch.GovernorDecisionRef, governorDecisionRef, StringComparison.OrdinalIgnoreCase)
                    && string.Equals(dispatch.ReleaseProofReceiptId, releaseProofReceiptId, StringComparison.OrdinalIgnoreCase)))
                .Where(static dispatch => dispatch is not null)
                .Cast<ProductLiftCloseoutDispatchReceiptState>()
                .ToList();
            if (matchingReceipts.Count != recipientRefs.Count
                || matchingReceipts.Any(dispatch => !string.Equals(dispatch.DeliveryState, "sent", StringComparison.OrdinalIgnoreCase)))
            {
                return;
            }
        }

        TryAppendJourneyReceipt(sourceReceipt, governorDecisionRef, releaseProofReceiptId, recipientRefs.Count, recipientRefs.Count);
    }

    private DeliveryOutcomeDispatchIdentityMatch? FindDispatchReceiptByOutcomeIdentityLocked(
        string deliveryId,
        string? providerMessageId,
        string? sourceReceiptId,
        string? recipientRef,
        string? addressHash)
    {
        ProductLiftCloseoutDispatchReceiptState? matched = !string.Equals(deliveryId, "delivery-pending", StringComparison.OrdinalIgnoreCase)
            ? _dispatchReceipts.FirstOrDefault(receipt =>
                string.Equals(receipt.DeliveryId, deliveryId, StringComparison.OrdinalIgnoreCase))
            : null;
        if (matched is not null)
        {
            return new DeliveryOutcomeDispatchIdentityMatch(matched, "delivery_id");
        }

        if (!string.IsNullOrWhiteSpace(providerMessageId))
        {
            matched = _dispatchReceipts.FirstOrDefault(receipt =>
                string.Equals(receipt.ProviderMessageId, providerMessageId, StringComparison.OrdinalIgnoreCase));
            if (matched is not null)
            {
                return new DeliveryOutcomeDispatchIdentityMatch(matched, "provider_message_id");
            }
        }

        if (!string.IsNullOrWhiteSpace(sourceReceiptId) && !string.IsNullOrWhiteSpace(recipientRef))
        {
            matched = _dispatchReceipts.FirstOrDefault(receipt =>
                string.Equals(receipt.SourceReceiptId, sourceReceiptId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(receipt.RecipientRef, recipientRef, StringComparison.OrdinalIgnoreCase));
            if (matched is not null)
            {
                return new DeliveryOutcomeDispatchIdentityMatch(matched, "source_receipt_recipient_ref");
            }
        }

        if (!string.IsNullOrWhiteSpace(sourceReceiptId) && !string.IsNullOrWhiteSpace(addressHash))
        {
            matched = _dispatchReceipts.FirstOrDefault(receipt =>
                string.Equals(receipt.SourceReceiptId, sourceReceiptId, StringComparison.OrdinalIgnoreCase)
                && string.Equals(receipt.AddressHash, addressHash, StringComparison.OrdinalIgnoreCase));
            if (matched is not null)
            {
                return new DeliveryOutcomeDispatchIdentityMatch(matched, "source_receipt_address_hash");
            }
        }

        if (!string.IsNullOrWhiteSpace(sourceReceiptId))
        {
            ProductLiftCloseoutDispatchReceiptState[] candidates = _dispatchReceipts
                .Where(receipt => string.Equals(receipt.SourceReceiptId, sourceReceiptId, StringComparison.OrdinalIgnoreCase))
                .ToArray();
            if (candidates.Length == 1)
            {
                return new DeliveryOutcomeDispatchIdentityMatch(candidates[0], "source_receipt_unique_dispatch");
            }
        }

        return null;
    }

    private ProductLiftCloseoutDispatchReceiptState ApplyDeliveryOutcomeToDispatchLocked(
        ProductLiftCloseoutDispatchReceiptState receipt,
        string providerState,
        string? providerMessageId,
        string? reason,
        DateTimeOffset? retryAtUtc,
        DateTimeOffset recordedAtUtc)
    {
        string normalizedState = NormalizeToken(providerState);
        string currentState = NormalizeToken(receipt.DeliveryState);
        if (IsProviderSentState(normalizedState))
        {
            ProductLiftCloseoutDispatchReceiptState candidate = receipt with
            {
                StatusLabel = "Provider confirmed sent",
                DeliveryState = "sent",
                ProviderMessageId = NormalizeOptional(providerMessageId) ?? receipt.ProviderMessageId ?? receipt.DeliveryId,
                SuppressionCheck = "passed",
                Summary = $"Provider callback confirmed the bounded closeout delivery for {receipt.RecipientRef}.",
                Error = null,
                LastRecoveryStatus = "provider_confirmed_sent",
                LastProviderState = providerState,
                NextAutomaticRetryAtUtc = null,
                AcceptedAtUtc = receipt.AcceptedAtUtc ?? recordedAtUtc,
                LastRecoveryAtUtc = recordedAtUtc,
                LastOutcomeAtUtc = recordedAtUtc
            };
            return ApplyDispatchOutcomeCandidateLocked(receipt, candidate, currentState, "sent", recordedAtUtc);
        }

        if (IsProviderSuppressedState(normalizedState, reason))
        {
            ProductLiftCloseoutDispatchReceiptState candidate = receipt with
            {
                StatusLabel = "Suppressed by provider",
                DeliveryState = "suppressed",
                ProviderMessageId = NormalizeOptional(providerMessageId) ?? receipt.ProviderMessageId,
                SuppressionCheck = "suppressed",
                Summary = $"Provider callback held the bounded closeout delivery for {receipt.RecipientRef} under suppression.",
                Error = NormalizeOptional(reason) ?? receipt.Error,
                LastRecoveryStatus = "provider_suppressed",
                LastProviderState = providerState,
                NextAutomaticRetryAtUtc = null,
                LastRecoveryAtUtc = recordedAtUtc,
                LastOutcomeAtUtc = recordedAtUtc
            };
            return ApplyDispatchOutcomeCandidateLocked(receipt, candidate, currentState, "suppressed", recordedAtUtc);
        }

        if (IsProviderRetryState(normalizedState, retryAtUtc, reason))
        {
            ProductLiftCloseoutDispatchReceiptState candidate = receipt with
            {
                StatusLabel = "Provider retry scheduled",
                DeliveryState = "retrying",
                ProviderMessageId = NormalizeOptional(providerMessageId) ?? receipt.ProviderMessageId,
                SuppressionCheck = "retryable",
                Summary = $"Provider callback kept the bounded closeout delivery for {receipt.RecipientRef} on an automatic retry rail.",
                Error = NormalizeOptional(reason) ?? receipt.Error,
                LastRecoveryStatus = "provider_retry_scheduled",
                LastProviderState = providerState,
                NextAutomaticRetryAtUtc = retryAtUtc,
                LastRecoveryAtUtc = recordedAtUtc,
                LastOutcomeAtUtc = recordedAtUtc
            };
            return ApplyDispatchOutcomeCandidateLocked(receipt, candidate, currentState, "retrying", recordedAtUtc);
        }

        if (IsProviderAcceptedState(normalizedState))
        {
            ProductLiftCloseoutDispatchReceiptState candidate = receipt with
            {
                StatusLabel = "Provider accepted",
                DeliveryState = "accepted",
                ProviderMessageId = NormalizeOptional(providerMessageId) ?? receipt.ProviderMessageId,
                Summary = $"Provider callback confirmed acceptance for the bounded closeout delivery for {receipt.RecipientRef}.",
                Error = NormalizeOptional(reason) ?? receipt.Error,
                LastRecoveryStatus = "provider_confirmed_accepted",
                LastProviderState = providerState,
                NextAutomaticRetryAtUtc = null,
                AcceptedAtUtc = receipt.AcceptedAtUtc ?? recordedAtUtc,
                LastRecoveryAtUtc = recordedAtUtc,
                LastOutcomeAtUtc = recordedAtUtc
            };
            return ApplyDispatchOutcomeCandidateLocked(receipt, candidate, currentState, "accepted", recordedAtUtc);
        }

        string suppressionCheck = ResolveSuppressionCheck(reason, hasDeliveryId: !string.Equals(receipt.DeliveryId, "delivery-pending", StringComparison.OrdinalIgnoreCase));
        ProductLiftCloseoutDispatchReceiptState failedCandidate = receipt with
        {
            StatusLabel = "Provider reported failure",
            DeliveryState = "failed",
            ProviderMessageId = NormalizeOptional(providerMessageId) ?? receipt.ProviderMessageId,
            SuppressionCheck = suppressionCheck,
            Summary = $"Provider callback reported a bounded closeout delivery failure for {receipt.RecipientRef}.",
            Error = NormalizeOptional(reason) ?? receipt.Error,
            LastRecoveryStatus = "provider_failed",
            LastProviderState = providerState,
            NextAutomaticRetryAtUtc = retryAtUtc,
            LastRecoveryAtUtc = recordedAtUtc,
            LastOutcomeAtUtc = recordedAtUtc
        };
        return ApplyDispatchOutcomeCandidateLocked(receipt, failedCandidate, currentState, "failed", recordedAtUtc);
    }

    private ProductLiftCloseoutDispatchReceiptState ApplyDispatchOutcomeCandidateLocked(
        ProductLiftCloseoutDispatchReceiptState original,
        ProductLiftCloseoutDispatchReceiptState candidate,
        string currentState,
        string candidateState,
        DateTimeOffset recordedAtUtc)
    {
        bool shouldAdvance = GetDispatchStateRank(candidateState) >= GetDispatchStateRank(currentState);
        ProductLiftCloseoutDispatchReceiptState updated = shouldAdvance
            ? candidate
            : original with
            {
                ProviderMessageId = NormalizeOptional(candidate.ProviderMessageId) ?? original.ProviderMessageId,
                LastRecoveryStatus = "provider_callback_stale",
                LastRecoveryAtUtc = recordedAtUtc,
                LastOutcomeAtUtc = recordedAtUtc
            };

        int index = _dispatchReceipts.FindIndex(item => string.Equals(item.ReceiptId, original.ReceiptId, StringComparison.OrdinalIgnoreCase));
        if (index >= 0)
        {
            _dispatchReceipts[index] = updated;
            _dispatchReceipts.Sort(static (left, right) => right.RequestedAtUtc.CompareTo(left.RequestedAtUtc));
        }

        return updated;
    }

    private string QueueCloseoutDelivery(
        ProjectedCloseoutRecipient recipient,
        ProductLiftWebhookReceiptState sourceReceipt,
        string subject,
        string content,
        CloseoutRuntimeReadiness readiness,
        string governorDecisionRef,
        string releaseProofReceiptId,
        string idempotencyKey)
    {
        Dictionary<string, object> metadata = new(StringComparer.OrdinalIgnoreCase)
        {
            ["template_id"] = ProductLiftCloseoutTemplateId,
            ["template_version"] = ProductLiftCloseoutTemplateVersion,
            ["source_receipt_id"] = sourceReceipt.ReceiptId,
            ["product_signal_event_type"] = sourceReceipt.EventType,
            ["board_label"] = sourceReceipt.BoardLabel,
            ["category_label"] = sourceReceipt.CategoryLabel,
            ["item_reference"] = sourceReceipt.ItemReference,
            ["governor_decision_ref"] = governorDecisionRef,
            ["release_proof_route"] = readiness.ReleaseProofRoute,
            ["release_proof_receipt_id"] = releaseProofReceiptId,
            ["journey_event_key"] = VoterNotifiedJourneyEventKey,
            ["follow_settings_path"] = readiness.FollowSettingsPath,
            ["from_email"] = ResolveFromEmail(),
            ["from_name"] = ResolveFromName(),
            ["reply_to"] = ResolveReplyTo()
        };

        object payload = new
        {
            tool_name = ConnectorDispatchToolName,
            action_kind = ConnectorDispatchActionName,
            payload_json = new
            {
                principal_id = ResolveEaPrincipalId(),
                binding_id = ResolveEaBindingId(),
                channel = EmailChannel,
                recipient = recipient.Email,
                subject,
                content,
                metadata,
                idempotency_key = idempotencyKey
            }
        };

        JsonObject response = SendJson(
            method: HttpMethod.Post,
            url: $"{ResolveEaBaseUrl()}/v1/tools/execute",
            payload: payload,
            bearerToken: ResolveEaApiToken(),
            principalId: ResolveEaPrincipalId());
        string deliveryId = response["target_ref"]?.GetValue<string>()
            ?? response["output_json"]?["delivery_id"]?.GetValue<string>()
            ?? string.Empty;
        if (string.IsNullOrWhiteSpace(deliveryId))
        {
            throw new InvalidOperationException("connector_dispatch_missing_delivery_id");
        }

        return deliveryId;
    }

    private string SendCloseoutEmail(
        ProjectedCloseoutRecipient recipient,
        ProductLiftWebhookReceiptState sourceReceipt,
        string subject,
        string content,
        string idempotencyKey,
        string deliveryId)
    {
        object payload = new
        {
            from = $"{ResolveFromName()} <{ResolveFromEmail()}>",
            to = recipient.Email,
            subject,
            text = content,
            html = $"<pre>{EscapeHtml(content)}</pre>",
            reply_to = ResolveReplyTo(),
            tracking = false,
            meta = new Dictionary<string, object>(StringComparer.OrdinalIgnoreCase)
            {
                ["delivery_id"] = deliveryId,
                ["source_receipt_id"] = sourceReceipt.ReceiptId,
                ["journey_event_key"] = VoterNotifiedJourneyEventKey,
                ["template_id"] = ProductLiftCloseoutTemplateId,
                ["template_version"] = ProductLiftCloseoutTemplateVersion
            }
        };

        JsonObject response = SendJson(
            method: HttpMethod.Post,
            url: $"{ResolveEmailitBaseUrl()}/emails",
            payload: payload,
            bearerToken: ResolveEmailitApiKey(),
            principalId: null,
            idempotencyKey: idempotencyKey);
        return response["id"]?.GetValue<string>()
            ?? response["data"]?["id"]?.GetValue<string>()
            ?? deliveryId;
    }

    private void MarkCloseoutSent(
        string deliveryId,
        ProjectedCloseoutRecipient recipient,
        ProductLiftWebhookReceiptState sourceReceipt,
        string subject,
        string providerMessageId)
    {
        object payload = new
        {
            receipt_json = new
            {
                transport = EmailitProvider,
                provider = EmailitProvider,
                state = "sent",
                delivery_id = deliveryId,
                source_receipt_id = sourceReceipt.ReceiptId,
                recipient_ref = recipient.UserId,
                address_hash = recipient.AddressHash,
                subject,
                provider_message_id = providerMessageId,
                template_id = ProductLiftCloseoutTemplateId,
                template_version = ProductLiftCloseoutTemplateVersion
            }
        };

        SendJson(
            method: HttpMethod.Post,
            url: $"{ResolveEaBaseUrl()}/v1/delivery/outbox/{Uri.EscapeDataString(deliveryId)}/sent",
            payload: payload,
            bearerToken: ResolveEaApiToken(),
            principalId: ResolveEaPrincipalId());
    }

    private void MarkCloseoutSentFromStoredDispatch(
        ProductLiftCloseoutDispatchReceiptState receipt,
        ProductLiftWebhookReceiptState sourceReceipt,
        string? providerMessageIdOverride = null)
    {
        object payload = new
        {
            receipt_json = new
            {
                transport = EmailitProvider,
                provider = EmailitProvider,
                state = "sent",
                delivery_id = receipt.DeliveryId,
                source_receipt_id = sourceReceipt.ReceiptId,
                recipient_ref = receipt.RecipientRef,
                address_hash = receipt.AddressHash,
                subject = BuildCloseoutSubject(sourceReceipt),
                provider_message_id = NormalizeOptional(providerMessageIdOverride) ?? NormalizeOptional(receipt.ProviderMessageId) ?? receipt.DeliveryId,
                template_id = receipt.TemplateId,
                template_version = receipt.TemplateVersion
            }
        };

        SendJson(
            method: HttpMethod.Post,
            url: $"{ResolveEaBaseUrl()}/v1/delivery/outbox/{Uri.EscapeDataString(receipt.DeliveryId)}/sent",
            payload: payload,
            bearerToken: ResolveEaApiToken(),
            principalId: ResolveEaPrincipalId());
    }

    private void TryMarkCloseoutFailed(string deliveryId, string error)
    {
        try
        {
            SendJson(
                method: HttpMethod.Post,
                url: $"{ResolveEaBaseUrl()}/v1/delivery/outbox/{Uri.EscapeDataString(deliveryId)}/failed",
                payload: new
                {
                    error = Truncate(error, 1000),
                    retry_in_seconds = 60,
                    dead_letter = false
                },
                bearerToken: ResolveEaApiToken(),
                principalId: ResolveEaPrincipalId());
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to mark ProductLift closeout delivery {DeliveryId} as failed.", deliveryId);
        }
    }

    private JsonObject SendJson(
        HttpMethod method,
        string url,
        object payload,
        string bearerToken,
        string? principalId,
        string? idempotencyKey = null)
    {
        using HttpClient httpClient = CreateHttpClient();
        using HttpRequestMessage request = new(method, url);
        request.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        if (!string.IsNullOrWhiteSpace(bearerToken))
        {
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", bearerToken);
        }

        if (!string.IsNullOrWhiteSpace(principalId))
        {
            request.Headers.Add("x-ea-principal-id", principalId);
        }

        if (!string.IsNullOrWhiteSpace(idempotencyKey))
        {
            request.Headers.Add("Idempotency-Key", idempotencyKey);
        }

        request.Content = JsonContent.Create(payload);
        using HttpResponseMessage response = httpClient.SendAsync(request).GetAwaiter().GetResult();
        string body = response.Content.ReadAsStringAsync().GetAwaiter().GetResult();
        if (!response.IsSuccessStatusCode)
        {
            throw new InvalidOperationException($"{(int)response.StatusCode}:{Truncate(body, 600)}");
        }

        if (string.IsNullOrWhiteSpace(body))
        {
            return new JsonObject();
        }

        return JsonNode.Parse(body)?.AsObject() ?? new JsonObject();
    }

    private HttpClient CreateHttpClient()
        => _httpClientFactory?.CreateClient(nameof(PublicSignalOperationsService)) ?? new HttpClient();

    private string BuildCloseoutSubject(ProductLiftWebhookReceiptState sourceReceipt)
        => $"Chummer shipped: {sourceReceipt.ItemReference}";

    private string BuildCloseoutContent(
        ProductLiftWebhookReceiptState sourceReceipt,
        CloseoutRuntimeReadiness readiness,
        string governorDecisionRef,
        string releaseProofReceiptId)
        => BuildCloseoutContent(
            sourceReceipt,
            readiness.FollowSettingsPath,
            governorDecisionRef,
            releaseProofReceiptId);

    private string BuildCloseoutContent(
        ProductLiftWebhookReceiptState sourceReceipt,
        string followSettingsPath,
        string governorDecisionRef,
        string releaseProofReceiptId)
        => string.Join(
            "\n",
            new[]
            {
                "A Chummer item you followed is now shipped.",
                $"Board: {sourceReceipt.BoardLabel}",
                $"Category: {sourceReceipt.CategoryLabel}",
                $"Item: {sourceReceipt.ItemReference}",
                "",
                $"Changelog: {ResolvePublicBaseUrl()}{CloseoutProofRoute}",
                $"Follow settings: {ResolvePublicBaseUrl()}{followSettingsPath}",
                $"Governor decision: {governorDecisionRef}",
                $"Release status record: {releaseProofReceiptId}",
                "",
                "This notice stays first-party and bounded to shipped status, follow settings, and the first-party notification timeline."
            });

    private string ResolveCurrentFollowSettingsPath()
        => NormalizeOptional(_configuration[ProductLiftCloseoutFollowSettingsPathConfigKey]) ?? DefaultFollowSettingsPath;

    private ProductLiftCloseoutDispatchReceiptState? UpdateDispatchReceipt(
        string receiptId,
        Func<ProductLiftCloseoutDispatchReceiptState, ProductLiftCloseoutDispatchReceiptState> update)
    {
        lock (_gate)
        {
            int index = _dispatchReceipts.FindIndex(item => string.Equals(item.ReceiptId, receiptId, StringComparison.OrdinalIgnoreCase));
            if (index < 0)
            {
                return null;
            }

            ProductLiftCloseoutDispatchReceiptState updated = update(_dispatchReceipts[index]);
            _dispatchReceipts[index] = updated;
            _dispatchReceipts.Sort(static (left, right) => right.RequestedAtUtc.CompareTo(left.RequestedAtUtc));
            TrimReceiptsLocked();
            PersistLocked();
            return updated;
        }
    }

    private static string ResolveSuppressionCheck(string? error, bool hasDeliveryId)
    {
        string normalized = NormalizeOptional(error)?.ToLowerInvariant() ?? string.Empty;
        if (LooksLikeRetryableBounce(normalized)
            || normalized.Contains("temporary", StringComparison.Ordinal)
            || normalized.Contains("transient", StringComparison.Ordinal)
            || normalized.Contains("retry later", StringComparison.Ordinal)
            || normalized.Contains("mailbox full", StringComparison.Ordinal))
        {
            return "retryable";
        }

        if (normalized.Contains("suppressed", StringComparison.Ordinal)
            || normalized.Contains("unsubscribe", StringComparison.Ordinal)
            || normalized.Contains("unsubscribed", StringComparison.Ordinal)
            || LooksLikeSuppressionBounce(normalized)
            || normalized.Contains("blocklist", StringComparison.Ordinal)
            || normalized.Contains("blacklist", StringComparison.Ordinal)
            || normalized.Contains("invalid recipient", StringComparison.Ordinal)
            || normalized.Contains("410:", StringComparison.Ordinal)
            || normalized.Contains("422:", StringComparison.Ordinal))
        {
            return "suppressed";
        }

        return hasDeliveryId ? "retryable" : "manual_review";
    }

    private string BuildCloseoutIdempotencyKey(
        ProductLiftWebhookReceiptState sourceReceipt,
        ProjectedCloseoutRecipient recipient,
        string governorDecisionRef,
        string releaseProofReceiptId)
        => ComputeSha256Hex($"{sourceReceipt.ReceiptId}|{recipient.UserId}|{governorDecisionRef}|{releaseProofReceiptId}|{ProductLiftCloseoutTemplateId}");

    private static string BuildDispatchDedupKey(
        string sourceReceiptId,
        string recipientRef,
        string governorDecisionRef,
        string releaseProofReceiptId)
        => $"source:{sourceReceiptId}:recipient:{recipientRef}:decision:{governorDecisionRef}:proof:{releaseProofReceiptId}";

    private string ResolveEaApiToken()
        => (_configuration[ProductLiftCloseoutEaApiTokenConfigKey] ?? string.Empty).Trim();

    private string ResolveEaPrincipalId()
        => (_configuration[ProductLiftCloseoutEaPrincipalIdConfigKey] ?? string.Empty).Trim();

    private string ResolveEaBindingId()
        => (_configuration[ProductLiftCloseoutEaBindingIdConfigKey] ?? string.Empty).Trim();

    private string ResolveEmailitApiKey()
        => (_configuration[ProductLiftCloseoutEmailApiKeyConfigKey] ?? string.Empty).Trim();

    private string ResolveEaBaseUrl()
        => NormalizeOptional(_configuration[ProductLiftCloseoutEaBaseUrlConfigKey])
            ?? NormalizeOptional(_configuration["CHUMMER_SUPPORT_PROGRESS_EMAIL_EA_BASE_URL"])
            ?? DefaultEaBaseUrl;

    private string ResolveEmailitBaseUrl()
        => NormalizeOptional(_configuration[ProductLiftCloseoutEmailitBaseUrlConfigKey])
            ?? NormalizeOptional(_configuration["CHUMMER_SUPPORT_PROGRESS_EMAIL_EMAILIT_BASE_URL"])
            ?? DefaultEmailitBaseUrl;

    private string ResolvePublicBaseUrl()
        => NormalizeOptional(_configuration[ProductLiftCloseoutPublicBaseUrlConfigKey])
            ?? NormalizeOptional(_configuration["CHUMMER_SUPPORT_PROGRESS_EMAIL_PUBLIC_BASE_URL"])
            ?? DefaultPublicBaseUrl;

    private string ResolveFromEmail()
        => NormalizeOptional(_configuration[ProductLiftCloseoutFromEmailConfigKey])
            ?? DefaultFromEmail;

    private string ResolveFromName()
        => NormalizeOptional(_configuration[ProductLiftCloseoutFromNameConfigKey])
            ?? DefaultFromName;

    private string ResolveReplyTo()
        => NormalizeOptional(_configuration[ProductLiftCloseoutReplyToConfigKey])
            ?? DefaultReplyTo;

    private static string EscapeHtml(string value)
        => value
            .Replace("&", "&amp;", StringComparison.Ordinal)
            .Replace("<", "&lt;", StringComparison.Ordinal)
            .Replace(">", "&gt;", StringComparison.Ordinal)
            .Replace("\"", "&quot;", StringComparison.Ordinal);

    private static string Truncate(string value, int maxLength)
        => value.Length <= maxLength ? value : value[..maxLength];

    private OperationsCanonDocument LoadOperationsCanon()
    {
        var taxonomy = Deserializer.Deserialize<PublicFeedbackTaxonomyDocument>(_canon.LoadRequiredText(TaxonomyRelativePath))
            ?? throw new InvalidOperationException($"canon file '{TaxonomyRelativePath}' could not be deserialized.");
        var outboundRegistry = Deserializer.Deserialize<OutboundNotificationTemplateRegistryDocument>(_canon.LoadRequiredText(OutboundRegistryRelativePath))
            ?? throw new InvalidOperationException($"canon file '{OutboundRegistryRelativePath}' could not be deserialized.");
        bool closeoutFamilyReady = (outboundRegistry.Families ?? new List<OutboundNotificationTemplateFamilyDocument>())
            .FirstOrDefault(static family => string.Equals(family.Key, "product_feedback_closeout", StringComparison.Ordinal))?.Examples?.Contains("productlift_voter_shipped", StringComparer.Ordinal) == true;

        return new OperationsCanonDocument(taxonomy, closeoutFamilyReady);
    }

    private bool HasCloseoutDeliveryAdapterConfigured()
    {
        string? explicitEnabled = NormalizeOptional(_configuration[ProductLiftCloseoutEmailEnabledConfigKey]);
        if (bool.TryParse(explicitEnabled, out bool enabled) && !enabled)
        {
            return false;
        }

        return !string.IsNullOrWhiteSpace(_configuration[ProductLiftCloseoutEmailApiKeyConfigKey])
            || !string.IsNullOrWhiteSpace(_configuration["CHUMMER_SUPPORT_PROGRESS_EMAIL_EMAILIT_API_KEY"]);
    }

    private static string ResolveCloseoutQueueStatusLabel(
        bool closeoutFamilyReady,
        bool voterNotificationAllowed,
        bool deliveryAdapterConfigured,
        CloseoutRuntimeReadiness readiness)
    {
        if (!closeoutFamilyReady)
        {
            return "Canon pending";
        }

        if (!voterNotificationAllowed)
        {
            return "Notification blocked";
        }

        if (!deliveryAdapterConfigured)
        {
            return "Delivery adapter pending";
        }

        if (!readiness.OwnerReady)
        {
            return "Ownership blocked";
        }

        if (!readiness.ProjectionConfigured)
        {
            return "Recipient list pending";
        }

        if (readiness.ProjectedRecipientCount <= 0)
        {
            return "No eligible followers";
        }

        if (!readiness.ConsentConfigured)
        {
            return "Consent basis pending";
        }

        if (!readiness.QueueConfigured)
        {
            return "Queue adapter pending";
        }

        if (!readiness.GovernorApproved)
        {
            return "Governor approval pending";
        }

        return readiness.ReleaseProofReady
            ? "Outbox candidate ready"
            : readiness.ReleaseProofStatusLabel;
    }

    private static string BuildCloseoutQueueReason(
        ProductLiftWebhookReceiptState sourceReceipt,
        bool closeoutFamilyReady,
        bool deliveryAdapterConfigured,
        CloseoutRuntimeReadiness readiness,
        bool readyForOutbox)
    {
        if (!closeoutFamilyReady)
        {
            return "The Chummer-owned closeout template family is not canonized yet.";
        }

        if (!sourceReceipt.VoterNotificationAllowed)
        {
            return "ProductLift does not currently allow voter notification for this item.";
        }

        if (!deliveryAdapterConfigured)
        {
            return "No first-party Emailit adapter is configured on this instance yet.";
        }

        if (!readiness.OwnerReady)
        {
            return "Recipient matching must stay first-party before any outbox candidate can be created.";
        }

        if (!readiness.ProjectionConfigured)
        {
            return "Recipient matching is still required before a shipped ProductLift item can become an outbox candidate.";
        }

        if (readiness.ProjectedRecipientCount <= 0)
        {
            return "No account followers currently have roadmap updates enabled for this outbox path.";
        }

        if (!readiness.ConsentConfigured)
        {
            return "A first-party consent or transactional-basis record is still required for ProductLift closeout.";
        }

        if (!readiness.QueueConfigured)
        {
            return "Recipient matching and consent are ready, but the delivery queue connection is still unconfigured.";
        }

        if (!readiness.GovernorApproved)
        {
            return "The product governor has not published a bounded closeout decision ref for this shipped ProductLift item yet.";
        }

        if (!readiness.ReleaseProofReady)
        {
            return readiness.ReleaseProofStatusLabel switch
            {
                "Release status stale" => "The release status for /changelog is stale, so voter closeout cannot be queued yet.",
                _ => "The public changelog route still lacks a current first-party release status record."
            };
        }

        return readyForOutbox
            ? "Governor approval, release status, recipient matching, consent, and delivery queue are all ready. This candidate can move into the first-party outbox without claiming the mail already sent."
            : "The outbox candidate remains blocked until the remaining closeout prerequisites are restored.";
    }

    private static string BuildCloseoutQueueSummary(
        ProductLiftWebhookReceiptState sourceReceipt,
        CloseoutRuntimeReadiness readiness,
        bool readyForOutbox)
    {
        if (!readyForOutbox)
        {
            return $"Webhook event {sourceReceipt.ReceiptId} stays on the bounded closeout path, but the outbox candidate is still blocked until governor approval and current changelog status line up with the existing delivery prerequisites.";
        }

        string decisionRef = NormalizeOptional(readiness.GovernorDecisionRef) ?? DefaultGovernorDecisionSourceRef;
        string releaseRecord = NormalizeOptional(readiness.ReleaseProofReceiptId) ?? "current-status";
        return $"Webhook event {sourceReceipt.ReceiptId} now has governor decision {decisionRef} plus current {readiness.ReleaseProofRoute} status record {releaseRecord}, so it can create a bounded outbox candidate for voter closeout without treating delivery state as notification truth.";
    }

    private static string BuildCloseoutQueueReceiptId(
        ProductLiftWebhookReceiptState sourceReceipt,
        CloseoutRuntimeReadiness readiness,
        string statusLabel)
    {
        string seed = string.Join(
            '|',
            sourceReceipt.ReceiptId,
            NormalizeOptional(readiness.GovernorDecisionRef) ?? "pending",
            NormalizeOptional(readiness.ReleaseProofReceiptId) ?? "proof-pending",
            statusLabel);
        string hash = ComputeSha256Hex(seed);
        return $"plqueue_{hash[..16]}";
    }

    private static string ResolveCloseoutDeliveryStatusLabel(
        bool closeoutFamilyReady,
        bool voterNotificationAllowed,
        bool deliveryAdapterConfigured,
        bool ownerReady,
        bool projectionConfigured,
        int projectedRecipientCount,
        bool consentConfigured,
        bool queueConfigured)
    {
        if (!closeoutFamilyReady)
        {
            return "Canon pending";
        }

        if (!voterNotificationAllowed)
        {
            return "Notification blocked";
        }

        if (!deliveryAdapterConfigured)
        {
            return "Delivery adapter pending";
        }

        if (!ownerReady)
        {
            return "Ownership blocked";
        }

        if (!projectionConfigured)
        {
            return "Recipient list pending";
        }

        if (projectedRecipientCount <= 0)
        {
            return "No eligible followers";
        }

        if (!consentConfigured)
        {
            return "Consent basis pending";
        }

        return queueConfigured
            ? "Delivery candidate"
            : "Queue adapter pending";
    }

    private static string ResolveCloseoutDeliveryState(
        bool closeoutFamilyReady,
        bool voterNotificationAllowed)
    {
        if (!voterNotificationAllowed)
        {
            return "suppressed";
        }

        return closeoutFamilyReady
            ? "deferred"
            : "deferred";
    }

    private static string ResolveStoredCloseoutDeliveryState(string statusLabel, bool voterNotificationAllowed)
    {
        if (!voterNotificationAllowed || string.Equals(statusLabel, "Notification blocked", StringComparison.OrdinalIgnoreCase))
        {
            return "suppressed";
        }

        return "deferred";
    }

    private static string ResolveStoredCloseoutTemplateId(string statusLabel)
        => string.Equals(statusLabel, "Canon pending", StringComparison.OrdinalIgnoreCase)
            ? "unassigned"
            : "productlift_voter_shipped";

    private static string BuildStoredCloseoutDeliveryReason(string statusLabel, bool voterNotificationAllowed, bool deliveryCandidate)
    {
        if (string.Equals(statusLabel, "Canon pending", StringComparison.OrdinalIgnoreCase))
        {
            return "The Chummer-owned closeout template family is not canonized yet.";
        }

        if (!voterNotificationAllowed || string.Equals(statusLabel, "Notification blocked", StringComparison.OrdinalIgnoreCase))
        {
            return "ProductLift does not currently allow voter notification for this item.";
        }

        if (string.Equals(statusLabel, "Delivery adapter pending", StringComparison.OrdinalIgnoreCase))
        {
            return "No first-party Emailit adapter is configured on this instance yet.";
        }

        if (string.Equals(statusLabel, "Ownership blocked", StringComparison.OrdinalIgnoreCase))
        {
            return "Recipient matching must stay first-party before ProductLift closeout can move toward delivery.";
        }

        if (string.Equals(statusLabel, "Recipient list pending", StringComparison.OrdinalIgnoreCase))
        {
            return "Recipient matching is still required before any voter-closeout send can be claimed.";
        }

        if (string.Equals(statusLabel, "No eligible followers", StringComparison.OrdinalIgnoreCase))
        {
            return "No account followers currently have roadmap updates enabled for this closeout path.";
        }

        if (string.Equals(statusLabel, "Consent basis pending", StringComparison.OrdinalIgnoreCase))
        {
            return "A first-party consent or transactional-basis record is still required for ProductLift closeout.";
        }

        if (string.Equals(statusLabel, "Queue adapter pending", StringComparison.OrdinalIgnoreCase))
        {
            return "Recipient matching and consent are ready, but the delivery queue connection is still unconfigured.";
        }

        return deliveryCandidate
            ? "Template, recipient list, consent basis, and queue are ready, but release status and closeout approval still gate any actual send."
            : "First-party closeout is deferred until the remaining delivery prerequisites are restored.";
    }

    private static string ResolveSupportTargetPath(MatchedFeedbackCategory category)
        => string.Equals(category.Key, "desktop_and_install", StringComparison.OrdinalIgnoreCase)
            ? "/help#install-update"
            : "/help#support";

    private static string BuildRoutingSummary(
        ProductLiftWebhookReceiptState sourceReceipt,
        MatchedFeedbackCategory category,
        string targetPath)
    {
        if (category.PrivacySensitive)
        {
            return $"{category.Label} can drift into private table detail, so webhook event {sourceReceipt.ReceiptId} was bounded into a moderation-first Chummer route at {targetPath} instead of staying a public vote thread.";
        }

        return $"{category.Label} is a likely support misroute, so webhook event {sourceReceipt.ReceiptId} now points back to {targetPath} instead of being treated as standalone roadmap authority.";
    }

    private static string BuildCloseoutSummary(
        ProductLiftWebhookReceiptState sourceReceipt,
        MatchedFeedbackCategory category,
        bool closeoutFamilyReady,
        bool deliveryAdapterConfigured)
    {
        if (!closeoutFamilyReady)
        {
            return $"Webhook event {sourceReceipt.ReceiptId} marked {category.Label} as a shipped-closeout candidate, but Chummer still lacks the canonized outbound closeout family required before first-party follow-up can exist.";
        }

        if (!sourceReceipt.VoterNotificationAllowed)
        {
            return $"Webhook event {sourceReceipt.ReceiptId} marked {category.Label} shipped, but ProductLift does not allow voter notification on this item yet, so first-party follow-up stays blocked.";
        }

        if (!deliveryAdapterConfigured)
        {
            return $"Webhook event {sourceReceipt.ReceiptId} created a bounded first-party closeout candidate for {category.Label}, but the outbound delivery adapter is not configured on this instance yet.";
        }

        return $"Webhook event {sourceReceipt.ReceiptId} created a bounded first-party closeout timeline for {category.Label}. Template and adapter readiness are in place, but recipient matching, consent basis, and release, route, guide, or file status are still required before any outbound follow-up can be claimed.";
    }

    private static string BuildCloseoutDeliveryReason(
        ProductLiftWebhookReceiptState sourceReceipt,
        bool closeoutFamilyReady,
        bool deliveryAdapterConfigured,
        CloseoutRuntimeReadiness readiness)
    {
        if (!closeoutFamilyReady)
        {
            return "The Chummer-owned closeout template family is not canonized yet.";
        }

        if (!sourceReceipt.VoterNotificationAllowed)
        {
            return "ProductLift does not currently allow voter notification for this item.";
        }

        if (!deliveryAdapterConfigured)
        {
            return "No first-party Emailit adapter is configured on this instance yet.";
        }

        if (!readiness.OwnerReady)
        {
            return "Recipient matching must stay first-party before ProductLift closeout can move toward delivery.";
        }

        if (!readiness.ProjectionConfigured)
        {
            return "Recipient matching is still required before any voter-closeout send can be claimed.";
        }

        if (readiness.ProjectedRecipientCount <= 0)
        {
            return "No account followers currently have roadmap updates enabled for this closeout path.";
        }

        if (!readiness.ConsentConfigured)
        {
            return "A first-party consent or transactional-basis record is still required for ProductLift closeout.";
        }

        if (!readiness.QueueConfigured)
        {
            return "Recipient matching and consent are ready, but the delivery queue connection is still unconfigured.";
        }

        return "Template, recipient list, consent basis, and queue are ready, but release status and closeout approval still gate any actual send.";
    }

    private static MatchedFeedbackCategory ResolveMatchedCategory(
        JsonElement item,
        JsonElement envelope,
        JsonElement payload,
        string fallbackLabel,
        IReadOnlyList<PublicFeedbackCategoryDocument>? categories)
    {
        HashSet<string> matchTokens = [];
        AddCategoryMatchTokens(matchTokens, item);
        AddCategoryMatchTokens(matchTokens, envelope);
        AddCategoryMatchTokens(matchTokens, payload);

        foreach (PublicFeedbackCategoryDocument category in categories ?? Array.Empty<PublicFeedbackCategoryDocument>())
        {
            if (matchTokens.Contains(BuildCategoryMatchToken(category.Key))
                || matchTokens.Contains(BuildCategoryMatchToken(category.Label)))
            {
                return new MatchedFeedbackCategory(
                    Key: NormalizeOptional(category.Key),
                    Label: HumanizeLabel(category.Label, fallbackLabel),
                    OwnerRepo: NormalizeOptional(category.OwnerRepo) ?? "unknown",
                    SupportMisrouteLikely: category.SupportMisrouteLikely,
                    PrivacySensitive: category.PrivacySensitive);
            }
        }

        return new MatchedFeedbackCategory(
            Key: null,
            Label: fallbackLabel,
            OwnerRepo: "unknown",
            SupportMisrouteLikely: false,
            PrivacySensitive: false);
    }

    private static void AddCategoryMatchTokens(HashSet<string> tokens, JsonElement source)
    {
        foreach (string name in new[] { "category", "bucket", "group" })
        {
            if (TryReadObject(source, out JsonElement nested, name))
            {
                AddIfPresent(tokens, TryReadString(nested, "key", "slug", "id", "name", "label", "title"));
            }

            AddIfPresent(tokens, TryReadString(source, name));
        }

        static void AddIfPresent(HashSet<string> tokens, string? value)
        {
            string token = BuildCategoryMatchToken(value);
            if (!string.IsNullOrWhiteSpace(token))
            {
                tokens.Add(token);
            }
        }
    }

    private static string BuildCategoryMatchToken(string? value)
    {
        string? normalized = NormalizeOptional(value);
        if (normalized is null)
        {
            return string.Empty;
        }

        StringBuilder builder = new(normalized.Length);
        bool previousUnderscore = false;
        foreach (char character in normalized.ToLowerInvariant())
        {
            if (char.IsLetterOrDigit(character))
            {
                builder.Append(character);
                previousUnderscore = false;
                continue;
            }

            if (!previousUnderscore)
            {
                builder.Append('_');
                previousUnderscore = true;
            }
        }

        return builder.ToString().Trim('_');
    }

    private static string ResolveWebhookStatusLabel(bool webhookConfigured, int receiptCount)
    {
        if (!webhookConfigured)
        {
            return receiptCount > 0 ? "Webhook drifted" : "Webhook pending";
        }

        return receiptCount > 0 ? "Webhook live" : "Webhook configured";
    }

    private static string BuildWebhookSummary(bool webhookConfigured, WebhookReceiptSnapshot snapshot)
    {
        if (!webhookConfigured)
        {
            return snapshot.ReceiptCount > 0
                ? "Bounded public-feedback receipt history exists, but the callback secret is missing on this instance now. The first-party adapter cannot safely accept new hosted callbacks until the secret is restored."
                : "Hosted feedback callback setup is not configured here yet, so hosted records cannot write back to the first-party loop on this instance.";
        }

        if (snapshot.ReceiptCount == 0)
        {
            return "Hosted feedback callback setup is configured here, so hosted records can return through a Chummer-owned adapter as soon as the public board starts posting callbacks.";
        }

        string lastReceipt = snapshot.LastReceiptAtUtc?.ToString("yyyy-MM-dd HH:mm 'UTC'") ?? "an unknown time";
        return $"The first-party adapter has materialized {snapshot.ReceiptCount} bounded hosted-feedback callback receipt{(snapshot.ReceiptCount == 1 ? string.Empty : "s")} so far, with the latest at {lastReceipt}. Only board/category/item metadata, timestamps, and payload hashes are retained.";
    }

    private static PublicSignalHostedRouteViewModel BuildHostedRoute(string label, string publicPath, string? configuredUrl)
    {
        if (string.IsNullOrWhiteSpace(configuredUrl))
        {
            return new PublicSignalHostedRouteViewModel(
                Label: label,
                PublicPath: publicPath,
                HostedHref: null,
                StatusLabel: "First-party only",
                Summary: $"{publicPath} remains the customer-facing default on this instance because no hosted public-board URL is configured for {label.ToLowerInvariant()}.");
        }

        if (!Uri.TryCreate(configuredUrl, UriKind.Absolute, out Uri? uri) || !string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase))
        {
            return new PublicSignalHostedRouteViewModel(
                Label: label,
                PublicPath: publicPath,
                HostedHref: configuredUrl.Trim(),
                StatusLabel: "Misconfigured",
                Summary: $"{label} has a configured hosted URL, but it is not a valid HTTPS public route, so {publicPath} must stay first-party.");
        }

        return new PublicSignalHostedRouteViewModel(
            Label: label,
            PublicPath: publicPath,
            HostedHref: configuredUrl.Trim(),
            StatusLabel: "Configured",
            Summary: $"{label} can promote to {uri.Host} once the hosted public-board path is approved, while {publicPath} remains the bounded first-party fallback.");
    }

    private static string ResolveHostedDomainLabel(IReadOnlyList<PublicSignalHostedRouteViewModel> routes)
    {
        string[] hosts = routes
            .Select(static route =>
            {
                if (string.IsNullOrWhiteSpace(route.HostedHref) || !Uri.TryCreate(route.HostedHref, UriKind.Absolute, out Uri? uri))
                {
                    return null;
                }

                return uri.Host;
            })
            .OfType<string>()
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();

        return hosts.Length switch
        {
            0 => "No hosted public-board domain configured",
            1 => hosts[0]!,
            _ => string.Join(" / ", hosts)
        };
    }

    private static string BuildHostedProjectionSummary(
        IReadOnlyList<PublicSignalHostedRouteViewModel> hostedRoutes,
        bool hostedProjectionReady,
        string hostedDomainLabel)
    {
        int configuredCount = hostedRoutes.Count(static route => string.Equals(route.StatusLabel, "Configured", StringComparison.Ordinal));
        int misconfiguredCount = hostedRoutes.Count(static route => string.Equals(route.StatusLabel, "Misconfigured", StringComparison.Ordinal));

        if (hostedProjectionReady)
        {
            return $"All three hosted public-board routes are configured on {hostedDomainLabel}, so this instance is ready for a bounded domain split without losing the first-party fallbacks.";
        }

        if (misconfiguredCount > 0)
        {
            return $"{misconfiguredCount} hosted public-board route value(s) are misconfigured, so the first-party feedback family must stay default until the domain split is corrected.";
        }

        return configuredCount == 0
            ? "No hosted public-board routes are configured here yet, so the first-party Fixer Board, roadmap, and changelog stay authoritative for public navigation."
            : $"{configuredCount} of {ProductLiftRoutePaths.Length} hosted public-board routes are configured. Promotion stays blocked until the full domain split is complete and consistent.";
    }

    private static PublicSignalCategoryRoutingViewModel BuildCategory(PublicFeedbackCategoryDocument category)
    {
        string label = RequireText(category.Label, "public feedback category label");
        string ownerRepo = RequireText(category.OwnerRepo, $"public feedback category '{category.Key}' owner_repo");
        string followUpLane = BuildFollowUpLane(category);
        string summary = BuildCategorySummary(category, label);

        return new PublicSignalCategoryRoutingViewModel(
            Label: label,
            OwnerRepo: ownerRepo,
            FollowUpLane: followUpLane,
            Summary: summary,
            SupportMisrouteLikely: category.SupportMisrouteLikely,
            PrivacySensitive: category.PrivacySensitive);
    }

    private static string BuildFollowUpLane(PublicFeedbackCategoryDocument category)
    {
        if (!string.IsNullOrWhiteSpace(category.OptimizationLane))
        {
            return HumanizeToken(category.OptimizationLane, "Optimization");
        }

        string discoveryLane = NormalizeToken(category.DiscoveryLane);
        return discoveryLane switch
        {
            "" or "none" => "First-party board only",
            "public_signal" => "Board-native public signal review",
            "public_signal_plus_structured_intake" => "Public signal plus structured intake",
            "public_signal_plus_guided_follow_up" => "Public signal plus guided follow-up",
            "public_signal_plus_survey" => "Public signal plus survey follow-up",
            "guided_follow_up" => "Guided follow-up",
            _ => HumanizeToken(category.DiscoveryLane, "Discovery follow-up")
        };
    }

    private static string BuildCategorySummary(PublicFeedbackCategoryDocument category, string label)
    {
        List<string> segments = [$"{label} routes through {BuildFollowUpLane(category).ToLowerInvariant()}."];

        if (category.SupportMisrouteLikely)
        {
            segments.Add("This category is likely to attract install, crash, or account misroutes that belong on Help instead of the public board.");
        }

        if (category.PrivacySensitive)
        {
            segments.Add("Posts here may drift into privacy-sensitive table detail and should stay tightly moderated.");
        }

        return string.Join(" ", segments);
    }

    private static string ResolveEmailitOutcomeState(JsonElement primary, JsonElement envelope, JsonElement payload)
    {
        string eventType = NormalizeToken(
            TryReadString(payload, "type", "event", "event_type", "eventType")
            ?? TryReadString(envelope, "type", "event", "event_type", "eventType")
            ?? TryReadString(primary, "type", "event", "event_type", "eventType"));
        string rawState = NormalizeToken(
            TryReadString(primary, "state", "status")
            ?? TryReadString(envelope, "state", "status")
            ?? TryReadString(payload, "state", "status"));
        string bounceClass = NormalizeToken(
            TryReadString(primary, "bounce_type", "bounceType", "bounce_class", "bounceClass", "classification")
            ?? TryReadString(envelope, "bounce_type", "bounceType", "bounce_class", "bounceClass", "classification")
            ?? TryReadString(payload, "bounce_type", "bounceType", "bounce_class", "bounceClass", "classification"));
        string reason = NormalizeToken(
            TryReadString(primary, "reason", "error", "detail", "description")
            ?? TryReadString(envelope, "reason", "error", "detail", "description")
            ?? TryReadString(payload, "reason", "error", "detail", "description"));
        string candidate = string.IsNullOrWhiteSpace(rawState) ? eventType : rawState;

        if (candidate.Contains("delivered", StringComparison.Ordinal))
        {
            return "Delivered";
        }

        if (candidate.Contains("accepted", StringComparison.Ordinal) || candidate.Contains("queued", StringComparison.Ordinal))
        {
            return "Accepted";
        }

        if (candidate.Contains("complained", StringComparison.Ordinal))
        {
            return "Complained";
        }

        if (candidate.Contains("suppressed", StringComparison.Ordinal) || candidate.Contains("unsubscribe", StringComparison.Ordinal))
        {
            return "Suppressed";
        }

        if (candidate.Contains("bounce", StringComparison.Ordinal))
        {
            if (bounceClass.Contains("soft", StringComparison.Ordinal) || LooksLikeRetryableBounce(reason))
            {
                return "Soft bounced";
            }

            return "Hard bounced";
        }

        if (candidate.Contains("failed", StringComparison.Ordinal) && LooksLikeRetryableBounce(reason))
        {
            return "Retrying";
        }

        return HumanizeLabel(
            TryReadString(primary, "state", "status", "event", "event_type", "eventType", "type")
            ?? TryReadString(envelope, "state", "status", "event", "event_type", "eventType", "type")
            ?? TryReadString(payload, "state", "status", "event", "event_type", "eventType", "type"),
            "Unknown");
    }

    private static string ResolveEaOutcomeState(JsonElement primary, JsonElement envelope, JsonElement payload)
    {
        string candidate = NormalizeToken(
            TryReadString(primary, "state", "status", "delivery_state", "deliveryState", "event", "event_type", "eventType", "type")
            ?? TryReadString(envelope, "state", "status", "delivery_state", "deliveryState", "event", "event_type", "eventType", "type")
            ?? TryReadString(payload, "state", "status", "delivery_state", "deliveryState", "event", "event_type", "eventType", "type"));
        string reason = NormalizeToken(
            TryReadString(primary, "reason", "error", "detail", "description")
            ?? TryReadString(envelope, "reason", "error", "detail", "description")
            ?? TryReadString(payload, "reason", "error", "detail", "description"));
        bool deadLetter = TryReadBoolean(primary, "dead_letter", "deadLetter")
            ?? TryReadBoolean(envelope, "dead_letter", "deadLetter")
            ?? TryReadBoolean(payload, "dead_letter", "deadLetter")
            ?? false;
        int? retryInSeconds = TryReadInt32(primary, "retry_in_seconds", "retryInSeconds")
            ?? TryReadInt32(envelope, "retry_in_seconds", "retryInSeconds")
            ?? TryReadInt32(payload, "retry_in_seconds", "retryInSeconds");

        if (candidate is "sent" or "delivered" or "completed" or "success"
            || candidate.Contains("sent", StringComparison.Ordinal)
            || candidate.Contains("delivered", StringComparison.Ordinal))
        {
            return "Delivered";
        }

        if (candidate is "accepted" or "queued" or "processing"
            || candidate.Contains("accepted", StringComparison.Ordinal)
            || candidate.Contains("queued", StringComparison.Ordinal)
            || candidate.Contains("processing", StringComparison.Ordinal))
        {
            return "Accepted";
        }

        if (deadLetter && (LooksLikeSuppressionBounce(reason) || candidate.Contains("suppressed", StringComparison.Ordinal)))
        {
            return "Suppressed";
        }

        if (!deadLetter && (retryInSeconds is > 0 || candidate.Contains("retry", StringComparison.Ordinal) || candidate.Contains("deferred", StringComparison.Ordinal)))
        {
            return "Retrying";
        }

        if (candidate.Contains("failed", StringComparison.Ordinal) && LooksLikeRetryableBounce(reason))
        {
            return "Retrying";
        }

        if (candidate.Contains("suppressed", StringComparison.Ordinal))
        {
            return "Suppressed";
        }

        return HumanizeLabel(
            TryReadString(primary, "state", "status", "delivery_state", "deliveryState", "event", "event_type", "eventType", "type")
            ?? TryReadString(envelope, "state", "status", "delivery_state", "deliveryState", "event", "event_type", "eventType", "type")
            ?? TryReadString(payload, "state", "status", "delivery_state", "deliveryState", "event", "event_type", "eventType", "type"),
            "Unknown");
    }

    private static bool LooksLikeRetryableBounce(string? value)
    {
        string normalized = NormalizeToken(value);
        return normalized.Contains("soft", StringComparison.Ordinal)
            || normalized.Contains("temporary", StringComparison.Ordinal)
            || normalized.Contains("transient", StringComparison.Ordinal)
            || normalized.Contains("mailbox full", StringComparison.Ordinal)
            || normalized.Contains("rate limit", StringComparison.Ordinal)
            || normalized.Contains("throttle", StringComparison.Ordinal)
            || normalized.Contains("retry", StringComparison.Ordinal)
            || normalized.Contains("deferred", StringComparison.Ordinal);
    }

    private static bool LooksLikeSuppressionBounce(string? value)
    {
        string normalized = NormalizeToken(value);
        return normalized.Contains("hard", StringComparison.Ordinal)
            || normalized.Contains("bounce", StringComparison.Ordinal)
            || normalized.Contains("invalid recipient", StringComparison.Ordinal)
            || normalized.Contains("unknown user", StringComparison.Ordinal)
            || normalized.Contains("complaint", StringComparison.Ordinal)
            || normalized.Contains("spam", StringComparison.Ordinal);
    }

    private static int GetDispatchStateRank(string? state)
    {
        return NormalizeToken(state) switch
        {
            "accepted" => 1,
            "failed" => 2,
            "retrying" => 3,
            "suppressed" => 4,
            "sent" => 5,
            _ => 0
        };
    }

    private static JsonElement ExtractEnvelope(JsonElement payload)
    {
        if (TryReadObject(payload, out JsonElement data, "data"))
        {
            return data;
        }

        return payload;
    }

    private static JsonElement ExtractPrimaryItem(JsonElement envelope)
    {
        if (TryReadObject(envelope, out JsonElement item, "item", "idea", "entry", "record", "post"))
        {
            return item;
        }

        return envelope;
    }

    private static string ResolveDeliveryOutcomeProviderKey(
        string? providerHint,
        JsonElement primary,
        JsonElement envelope,
        JsonElement payload)
    {
        string normalizedHint = NormalizeToken(providerHint);
        if (!string.IsNullOrWhiteSpace(normalizedHint))
        {
            return normalizedHint switch
            {
                "emailit" or "emailit_api" => "emailit",
                "ea" or "connector_dispatch" or "connector.dispatch" => "ea",
                _ => normalizedHint
            };
        }

        string normalizedPayloadProvider = NormalizeToken(
            TryReadString(primary, "provider", "source", "transport")
            ?? TryReadString(envelope, "provider", "source", "transport")
            ?? TryReadString(payload, "provider", "source", "transport"));
        if (normalizedPayloadProvider is "emailit" or "emailit_api")
        {
            return "emailit";
        }

        if (normalizedPayloadProvider is "ea" or "connector_dispatch" or "connector.dispatch")
        {
            return "ea";
        }

        string normalizedEvent = NormalizeToken(
            TryReadString(payload, "type", "event", "event_type", "eventType")
            ?? TryReadString(envelope, "type", "event", "event_type", "eventType")
            ?? TryReadString(primary, "type", "event", "event_type", "eventType"));
        if (normalizedEvent.StartsWith("email", StringComparison.Ordinal))
        {
            return "emailit";
        }

        if (normalizedEvent.Contains("delivery", StringComparison.Ordinal) || normalizedEvent.Contains("outbox", StringComparison.Ordinal))
        {
            return "ea";
        }

        return string.IsNullOrWhiteSpace(normalizedPayloadProvider) ? "unknown" : normalizedPayloadProvider;
    }

    private static string ResolveDeliveryOutcomeProviderLabel(string providerKey)
        => providerKey switch
        {
            "emailit" => "Emailit",
            "ea" => "EA",
            _ => HumanizeLabel(providerKey, "Unknown provider")
        };

    private static string ResolveDeliveryOutcomeState(
        string providerKey,
        JsonElement primary,
        JsonElement envelope,
        JsonElement payload)
    {
        return providerKey switch
        {
            "emailit" => ResolveEmailitOutcomeState(primary, envelope, payload),
            "ea" => ResolveEaOutcomeState(primary, envelope, payload),
            _ => HumanizeLabel(
                TryReadString(primary, "state", "status", "event", "event_type", "eventType", "type")
                ?? TryReadString(envelope, "state", "status", "event", "event_type", "eventType", "type")
                ?? TryReadString(payload, "state", "status", "event", "event_type", "eventType", "type"),
                "Unknown")
        };
    }

    private static string BuildDeliveryOutcomeDedupKey(
        string outcomeEventId,
        string provider,
        string deliveryId,
        string providerState,
        string payloadSha256,
        string? dispatchReceiptId = null)
    {
        string normalizedDispatchReceiptId = NormalizeToken(dispatchReceiptId);
        if (!string.IsNullOrWhiteSpace(normalizedDispatchReceiptId))
        {
            return string.Join(
                ':',
                "dispatch",
                normalizedDispatchReceiptId,
                "state",
                NormalizeToken(providerState));
        }

        return string.Join(
            ':',
            "provider",
            NormalizeToken(provider),
            "delivery",
            NormalizeToken(deliveryId),
            "state",
            NormalizeToken(providerState),
            "event",
            NormalizeToken(outcomeEventId),
            payloadSha256[..Math.Min(12, payloadSha256.Length)]);
    }

    private static string ResolveDeliveryOutcomeDeliveryId(
        string providerKey,
        JsonElement primary,
        JsonElement envelope,
        JsonElement payload)
    {
        string? direct = NormalizeOptional(
            TryReadString(primary, "delivery_id", "deliveryId", "target_ref", "targetRef")
            ?? TryReadString(envelope, "delivery_id", "deliveryId", "target_ref", "targetRef")
            ?? TryReadString(payload, "delivery_id", "deliveryId", "target_ref", "targetRef"));
        if (!string.IsNullOrWhiteSpace(direct))
        {
            return direct;
        }

        if (TryReadObject(primary, out JsonElement primaryMeta, "meta") || TryReadObject(envelope, out primaryMeta, "meta") || TryReadObject(payload, out primaryMeta, "meta"))
        {
            direct = NormalizeOptional(TryReadString(primaryMeta, "delivery_id", "deliveryId", "target_ref", "targetRef"));
            if (!string.IsNullOrWhiteSpace(direct))
            {
                return direct;
            }
        }

        return providerKey == "emailit"
            ? "delivery-pending"
            : NormalizeOptional(direct) ?? "delivery-pending";
    }

    private static string? ResolveDeliveryOutcomeProviderMessageId(
        string providerKey,
        JsonElement primary,
        JsonElement envelope,
        JsonElement payload)
    {
        string? explicitValue = NormalizeOptional(
            TryReadString(primary, "provider_message_id", "providerMessageId", "message_id", "messageId")
            ?? TryReadString(envelope, "provider_message_id", "providerMessageId", "message_id", "messageId")
            ?? TryReadString(payload, "provider_message_id", "providerMessageId", "message_id", "messageId"));
        if (!string.IsNullOrWhiteSpace(explicitValue))
        {
            return explicitValue;
        }

        if (providerKey == "emailit")
        {
            return NormalizeOptional(
                TryReadString(primary, "id")
                ?? TryReadString(envelope, "id")
                ?? TryReadString(payload, "id"));
        }

        if (TryReadObject(primary, out JsonElement primaryMeta, "meta") || TryReadObject(envelope, out primaryMeta, "meta") || TryReadObject(payload, out primaryMeta, "meta"))
        {
            explicitValue = NormalizeOptional(TryReadString(primaryMeta, "provider_message_id", "providerMessageId", "message_id", "messageId"));
        }

        return explicitValue;
    }

    private static string? ResolveDeliveryOutcomeSourceReceiptId(JsonElement primary, JsonElement envelope, JsonElement payload)
    {
        string? explicitValue = NormalizeOptional(
            TryReadString(primary, "source_receipt_id", "sourceReceiptId")
            ?? TryReadString(envelope, "source_receipt_id", "sourceReceiptId")
            ?? TryReadString(payload, "source_receipt_id", "sourceReceiptId"));
        if (!string.IsNullOrWhiteSpace(explicitValue))
        {
            return explicitValue;
        }

        if (TryReadObject(primary, out JsonElement primaryMeta, "meta") || TryReadObject(envelope, out primaryMeta, "meta") || TryReadObject(payload, out primaryMeta, "meta"))
        {
            return NormalizeOptional(TryReadString(primaryMeta, "source_receipt_id", "sourceReceiptId"));
        }

        return null;
    }

    private static string? ResolveDeliveryOutcomeRecipientRef(JsonElement primary, JsonElement envelope, JsonElement payload)
    {
        string? explicitValue = NormalizeOptional(
            TryReadString(primary, "recipient_ref", "recipientRef")
            ?? TryReadString(envelope, "recipient_ref", "recipientRef")
            ?? TryReadString(payload, "recipient_ref", "recipientRef"));
        if (!string.IsNullOrWhiteSpace(explicitValue))
        {
            return explicitValue;
        }

        if (TryReadObject(primary, out JsonElement primaryMeta, "meta") || TryReadObject(envelope, out primaryMeta, "meta") || TryReadObject(payload, out primaryMeta, "meta"))
        {
            return NormalizeOptional(TryReadString(primaryMeta, "recipient_ref", "recipientRef"));
        }

        return null;
    }

    private static string? ResolveDeliveryOutcomeRecipientEmail(JsonElement primary, JsonElement envelope, JsonElement payload)
    {
        string? direct = NormalizeOptional(
            TryReadString(primary, "to", "email", "recipient")
            ?? TryReadString(envelope, "to", "email", "recipient")
            ?? TryReadString(payload, "to", "email", "recipient"));
        if (!string.IsNullOrWhiteSpace(direct))
        {
            return direct;
        }

        if (TryReadObject(primary, out JsonElement primaryMeta, "meta") || TryReadObject(envelope, out primaryMeta, "meta") || TryReadObject(payload, out primaryMeta, "meta"))
        {
            direct = NormalizeOptional(TryReadString(primaryMeta, "to", "email", "recipient"));
            if (!string.IsNullOrWhiteSpace(direct))
            {
                return direct;
            }
        }

        if (primary.TryGetProperty("recipients", out JsonElement recipients) && recipients.ValueKind == JsonValueKind.Array)
        {
            foreach (JsonElement item in recipients.EnumerateArray())
            {
                direct = NormalizeOptional(TryReadString(item, "email", "to", "recipient"));
                if (!string.IsNullOrWhiteSpace(direct))
                {
                    return direct;
                }
            }
        }

        return null;
    }

    private static string ResolveDeliveryOutcomeStatusLabel(string providerState, bool matchedDispatch, string? reason)
    {
        string normalized = NormalizeToken(providerState);
        if (!matchedDispatch)
        {
            return "Unmatched delivery update";
        }

        if (IsProviderSentState(normalized))
        {
            return "Provider confirmed sent";
        }

        if (IsProviderSuppressedState(normalized, reason))
        {
            return "Provider suppression";
        }

        if (IsProviderRetryState(normalized, retryAtUtc: null, reason))
        {
            return "Provider retry scheduled";
        }

        if (IsProviderAcceptedState(normalized))
        {
            return "Provider accepted";
        }

        return "Provider failure";
    }

    private static string BuildDeliveryOutcomeSummary(
        string provider,
        string providerState,
        string dispatchReceiptId,
        string? reason,
        DateTimeOffset? retryAtUtc)
    {
        string suffix = retryAtUtc is { } scheduledAt
            ? $" Next provider retry is scheduled for {scheduledAt:yyyy-MM-dd HH:mm 'UTC'}."
            : string.Empty;
        string reasonText = !string.IsNullOrWhiteSpace(reason) ? $" {reason.Trim()}" : string.Empty;
        return $"{provider} reported '{providerState}' for bounded dispatch receipt {dispatchReceiptId}.{reasonText}{suffix}".Trim();
    }

    private static bool IsProviderSentState(string normalizedState)
        => normalizedState is "sent" or "delivered" or "completed" or "success";

    private static bool IsProviderAcceptedState(string normalizedState)
        => normalizedState is "accepted" or "queued" or "processing";

    private static string ResolveDeliveryOutcomeDispatchState(string providerState, string? reason, DateTimeOffset? retryAtUtc)
    {
        string normalizedState = NormalizeToken(providerState);
        if (IsProviderSentState(normalizedState))
        {
            return "sent";
        }

        if (IsProviderSuppressedState(normalizedState, reason))
        {
            return "suppressed";
        }

        if (IsProviderRetryState(normalizedState, retryAtUtc, reason))
        {
            return "retrying";
        }

        if (IsProviderAcceptedState(normalizedState))
        {
            return "accepted";
        }

        return "failed";
    }

    private static bool IsProviderRetryState(string normalizedState, DateTimeOffset? retryAtUtc, string? reason)
        => normalizedState is "retrying" or "deferred" or "throttled" or "temporary failure" or "temporary_failure" or "soft bounced" or "soft_bounced"
            || retryAtUtc is not null
            || LooksLikeRetryableBounce(reason);

    private static bool IsProviderSuppressedState(string normalizedState, string? reason)
    {
        if (normalizedState is "suppressed" or "hard bounced" or "hard_bounced" or "dropped" or "complained" or "unsubscribed" or "blocked")
        {
            return true;
        }

        if (normalizedState is "bounced")
        {
            return !LooksLikeRetryableBounce(reason);
        }

        string normalizedReason = NormalizeToken(reason);
        return normalizedReason.Contains("suppressed", StringComparison.Ordinal)
            || LooksLikeSuppressionBounce(normalizedReason)
            || normalizedReason.Contains("unsubscribe", StringComparison.Ordinal)
            || normalizedReason.Contains("complaint", StringComparison.Ordinal);
    }

    private static string ResolveEntityLabel(JsonElement primary, JsonElement secondary, JsonElement payload, string fallback, params string[] objectNames)
    {
        foreach (JsonElement source in new[] { primary, secondary, payload })
        {
            foreach (string objectName in objectNames)
            {
                if (TryReadObject(source, out JsonElement nested, objectName))
                {
                    string? nestedLabel = TryReadString(nested, "label", "name", "title", "slug", "key");
                    if (!string.IsNullOrWhiteSpace(nestedLabel))
                    {
                        return HumanizeLabel(nestedLabel, fallback);
                    }
                }

                string? flatLabel = TryReadString(source, objectName);
                if (!string.IsNullOrWhiteSpace(flatLabel))
                {
                    return HumanizeLabel(flatLabel, fallback);
                }
            }
        }

        return fallback;
    }

    private static string ResolveItemReference(JsonElement item, JsonElement envelope, JsonElement payload, string providerEventId)
    {
        string? candidate = TryReadString(item, "slug", "public_id", "publicId", "id", "key")
            ?? TryReadString(envelope, "slug", "public_id", "publicId", "id", "key")
            ?? TryReadString(payload, "item_id", "itemId");
        string? number = TryReadString(item, "number") ?? TryReadString(envelope, "number");

        if (!string.IsNullOrWhiteSpace(number) && !string.IsNullOrWhiteSpace(candidate))
        {
            return $"#{number.Trim()} · {candidate.Trim()}";
        }

        if (!string.IsNullOrWhiteSpace(number))
        {
            return $"#{number.Trim()}";
        }

        return NormalizeOptional(candidate) ?? $"provider-event:{providerEventId}";
    }

    private static string ResolveStatusLabel(JsonElement item, JsonElement envelope, JsonElement payload, string eventType)
    {
        if (TryReadObject(item, out JsonElement nestedStatus, "status", "state", "stage")
            && !string.IsNullOrWhiteSpace(TryReadString(nestedStatus, "label", "name", "title", "slug", "key")))
        {
            return HumanizeLabel(TryReadString(nestedStatus, "label", "name", "title", "slug", "key"), "Unknown");
        }

        string? status = TryReadString(item, "status", "state", "stage")
            ?? TryReadString(envelope, "status", "state", "stage")
            ?? TryReadString(payload, "status", "state", "stage");
        if (!string.IsNullOrWhiteSpace(status))
        {
            return HumanizeLabel(status, "Unknown");
        }

        return eventType.Contains("ship", StringComparison.OrdinalIgnoreCase)
            ? "Shipped"
            : "Unknown";
    }

    private static string ResolveActionLabel(string eventType, string statusLabel)
    {
        string normalizedEventType = NormalizeToken(eventType);
        if (normalizedEventType.Contains("ship", StringComparison.OrdinalIgnoreCase))
        {
            return "Shipped closeout";
        }

        if (normalizedEventType.Contains("status", StringComparison.OrdinalIgnoreCase))
        {
            return $"Status changed to {statusLabel.ToLowerInvariant()}";
        }

        if (normalizedEventType.Contains("vote", StringComparison.OrdinalIgnoreCase))
        {
            return "Vote activity";
        }

        if (normalizedEventType.Contains("comment", StringComparison.OrdinalIgnoreCase))
        {
            return "Comment activity";
        }

        if (normalizedEventType.Contains("create", StringComparison.OrdinalIgnoreCase))
        {
            return "Idea created";
        }

        if (normalizedEventType.Contains("update", StringComparison.OrdinalIgnoreCase))
        {
            return "Idea updated";
        }

        return HumanizeToken(eventType, "Provider event");
    }

    private static bool IsCloseoutCandidate(string eventType, string statusLabel)
        => string.Equals(statusLabel, "Shipped", StringComparison.OrdinalIgnoreCase)
           || eventType.Contains("ship", StringComparison.OrdinalIgnoreCase)
           || eventType.Contains("changelog", StringComparison.OrdinalIgnoreCase);

    private static string BuildDedupKey(string providerEventId, string eventType, string itemReference, string payloadSha256)
    {
        if (!providerEventId.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase))
        {
            return $"provider:{providerEventId.Trim()}";
        }

        return $"fallback:{NormalizeOptional(eventType) ?? "unknown"}:{NormalizeOptional(itemReference) ?? "provider-event-only"}:{payloadSha256}";
    }

    private static string ComputeSha256Hex(string value)
        => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    private static bool TryReadObject(JsonElement element, out JsonElement value, params string[] propertyNames)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            foreach (string propertyName in propertyNames)
            {
                foreach (JsonProperty property in element.EnumerateObject())
                {
                    if (!string.Equals(property.Name, propertyName, StringComparison.OrdinalIgnoreCase))
                    {
                        continue;
                    }

                    if (property.Value.ValueKind == JsonValueKind.Object)
                    {
                        value = property.Value;
                        return true;
                    }
                }
            }
        }

        value = default;
        return false;
    }

    private static string? TryReadString(JsonElement element, params string[] propertyNames)
    {
        if (element.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        foreach (string propertyName in propertyNames)
        {
            foreach (JsonProperty property in element.EnumerateObject())
            {
                if (!string.Equals(property.Name, propertyName, StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                return property.Value.ValueKind switch
                {
                    JsonValueKind.String => NormalizeOptional(property.Value.GetString()),
                    JsonValueKind.Number or JsonValueKind.True or JsonValueKind.False => property.Value.ToString(),
                    _ => null
                };
            }
        }

        return null;
    }

    private static bool? TryReadBoolean(JsonElement element, params string[] propertyNames)
    {
        if (element.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        foreach (string propertyName in propertyNames)
        {
            foreach (JsonProperty property in element.EnumerateObject())
            {
                if (!string.Equals(property.Name, propertyName, StringComparison.OrdinalIgnoreCase))
                {
                    continue;
                }

                return property.Value.ValueKind switch
                {
                    JsonValueKind.True => true,
                    JsonValueKind.False => false,
                    JsonValueKind.String when bool.TryParse(property.Value.GetString(), out bool parsed) => parsed,
                    _ => null
                };
            }
        }

        return null;
    }

    private static int? TryReadInt32(JsonElement element, params string[] propertyNames)
    {
        string? candidate = TryReadString(element, propertyNames);
        return int.TryParse(candidate, out int parsed) ? parsed : null;
    }

    private static DateTimeOffset? TryReadDateTimeOffset(JsonElement element, params string[] propertyNames)
    {
        string? candidate = TryReadString(element, propertyNames);
        return DateTimeOffset.TryParse(candidate, out DateTimeOffset parsed) ? parsed : null;
    }

    private static string HumanizeLabel(string? value, string fallback)
    {
        string? normalized = NormalizeOptional(value);
        if (normalized is null)
        {
            return fallback;
        }

        if (normalized.Contains(' ') && normalized.Any(char.IsLetter))
        {
            return normalized;
        }

        return HumanizeToken(normalized, fallback);
    }

    private static string? NormalizeOptional(string? value)
        => string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private static string NormalizeToken(string? value)
        => string.IsNullOrWhiteSpace(value) ? string.Empty : value.Trim().ToLowerInvariant();

    private static string HumanizeToken(string? value, string fallback)
        => string.IsNullOrWhiteSpace(value)
            ? fallback
            : System.Globalization.CultureInfo.InvariantCulture.TextInfo.ToTitleCase(value.Replace('_', ' ').Replace('-', ' '));

    private static string RequireText(string? value, string description)
        => string.IsNullOrWhiteSpace(value)
            ? throw new InvalidOperationException($"{description} is missing.")
            : value.Trim();

    private static string ResolveStoragePath(IConfiguration configuration)
    {
        string? configured = configuration["CHUMMER_PRODUCTLIFT_OPERATIONS_STORE_PATH"] ?? configuration["ProductLift:OperationsStorePath"];
        if (!string.IsNullOrWhiteSpace(configured))
        {
            return Path.GetFullPath(configured);
        }

        return Path.Combine(Path.GetTempPath(), "chummer6-hub", "productlift-operations-store.json");
    }

    private sealed class PublicFeedbackTaxonomyDocument
    {
        public List<PublicFeedbackCategoryDocument>? Categories { get; init; }
        public List<string>? Rules { get; init; }
    }

    private sealed class PublicFeedbackCategoryDocument
    {
        public string? Key { get; init; }
        public string? Label { get; init; }
        public string? OwnerRepo { get; init; }
        public bool SupportMisrouteLikely { get; init; }
        public bool PrivacySensitive { get; init; }
        public string? DiscoveryLane { get; init; }
        public string? OptimizationLane { get; init; }
    }

    private sealed class OutboundNotificationTemplateRegistryDocument
    {
        public List<OutboundNotificationTemplateFamilyDocument>? Families { get; init; }
    }

    private sealed class OutboundNotificationTemplateFamilyDocument
    {
        public string? Key { get; init; }
        public List<string>? Examples { get; init; }
    }

    private sealed record OperationsCanonDocument(
        PublicFeedbackTaxonomyDocument Taxonomy,
        bool CloseoutFamilyReady);

    private sealed record MatchedFeedbackCategory(
        string? Key,
        string Label,
        string OwnerRepo,
        bool SupportMisrouteLikely,
        bool PrivacySensitive);

    private sealed record CloseoutRuntimeReadiness(
        string ProjectionOwner,
        string FollowSettingsPath,
        bool OwnerReady,
        bool ProjectionConfigured,
        string ProjectionSourceRef,
        int ProjectedRecipientCount,
        IReadOnlyList<ProjectedCloseoutRecipient> Recipients,
        bool ConsentConfigured,
        string ConsentSourceRef,
        bool QueueConfigured,
        bool GovernorApproved,
        string? GovernorDecisionRef,
        bool ReleaseProofReady,
        string ReleaseProofRoute,
        string? ReleaseProofReceiptId,
        string ProjectionStatusLabel,
        string ProjectionSummary,
        string ConsentStatusLabel,
        string ConsentSummary,
        string QueueStatusLabel,
        string QueueSummary,
        string GovernorStatusLabel,
        string GovernorSummary,
        string ReleaseProofStatusLabel,
        string ReleaseProofSummary);

    private sealed record CloseoutAudienceSnapshot(
        string ProjectionSourceRef,
        string ConsentSourceRef,
        int ProjectedRecipientCount,
        IReadOnlyList<ProjectedCloseoutRecipient> Recipients);

    private sealed record ProjectedCloseoutRecipient(
        string UserId,
        string SubjectId,
        string Email,
        string AddressHash);

    private sealed record WebhookReceiptSnapshot(
        int ReceiptCount,
        int CloseoutReceiptCount,
        DateTimeOffset? LastReceiptAtUtc,
        int RoutingReceiptCount,
        int ModerationReceiptCount,
        int CloseoutDeliveryReceiptCount,
        int CloseoutDeliveryCandidateCount,
        IReadOnlyList<PublicSignalWebhookReceiptViewModel> RecentReceipts,
        IReadOnlyList<PublicSignalRoutingReceiptViewModel> RecentRoutingReceipts,
        IReadOnlyList<PublicSignalCloseoutDeliveryReceiptViewModel> RecentCloseoutReceipts);

    private sealed record CloseoutQueueSnapshot(
        int ReceiptCount,
        int ReadyCount,
        IReadOnlyList<PublicSignalCloseoutQueueReceiptViewModel> RecentReceipts);

    private sealed record DispatchReceiptSnapshot(
        int ReceiptCount,
        int SentCount,
        IReadOnlyList<PublicSignalCloseoutDispatchReceiptViewModel> RecentReceipts);

    private sealed record JourneyReceiptSnapshot(
        int ReceiptCount,
        IReadOnlyList<PublicSignalJourneyReceiptViewModel> RecentReceipts);

    private sealed record DeliveryOutcomeSnapshot(
        int ReceiptCount,
        int AutomaticRetryPendingCount,
        DateTimeOffset? LastReceiptAtUtc,
        IReadOnlyList<PublicSignalDeliveryOutcomeReceiptViewModel> RecentReceipts);

    private sealed record RecipientThreadSnapshot(
        IReadOnlyList<PublicSignalRecipientThreadViewModel> RecentThreads);

    private sealed record ReconcileRunSnapshot(
        int ReplayCandidateCount,
        int RunCount,
        DateTimeOffset? LastRunAtUtc,
        IReadOnlyList<PublicSignalReconcileRunReceiptViewModel> RecentRuns);

    private sealed record DispatchRecoverySnapshot(
        int RecoveryCandidateCount,
        int SuppressedDispatchCount,
        int RunCount,
        DateTimeOffset? LastRunAtUtc,
        IReadOnlyList<PublicSignalReconcileRunReceiptViewModel> RecentRuns);

    private sealed record RetryExpirySweepSnapshot(
        int CandidateCount,
        int RunCount,
        DateTimeOffset? LastRunAtUtc,
        IReadOnlyList<PublicSignalReconcileRunReceiptViewModel> RecentRuns);

    private sealed record ProductLiftWebhookReceiptSnapshot(
        IReadOnlyList<ProductLiftWebhookReceiptState>? WebhookReceipts,
        IReadOnlyList<ProductLiftRoutingReceiptState>? RoutingReceipts,
        IReadOnlyList<ProductLiftCloseoutDeliveryReceiptState>? CloseoutReceipts,
        IReadOnlyList<ProductLiftCloseoutDispatchReceiptState>? DispatchReceipts,
        IReadOnlyList<ProductLiftJourneyReceiptState>? JourneyReceipts,
        IReadOnlyList<ProductLiftDeliveryOutcomeReceiptState>? DeliveryOutcomeReceipts,
        IReadOnlyList<ProductLiftReconcileRunReceiptState>? ReconcileRuns);

    private sealed record ProductLiftWebhookReceiptState(
        string ReceiptId,
        string DedupKey,
        string ProviderEventId,
        string EventType,
        string ActionLabel,
        string StatusLabel,
        string BoardLabel,
        string CategoryLabel,
        string ItemReference,
        bool CloseoutCandidate,
        bool VoterNotificationAllowed,
        string PayloadSha256,
        DateTimeOffset ReceivedAtUtc,
        DateTimeOffset? ProviderOccurredAtUtc);

    private sealed record ProductLiftRoutingReceiptState(
        string ReceiptId,
        string DedupKey,
        string SourceReceiptId,
        string RouteKind,
        string StatusLabel,
        string TargetPath,
        string Summary,
        DateTimeOffset RecordedAtUtc);

    private sealed record ProductLiftCloseoutDeliveryReceiptState(
        string ReceiptId,
        string DedupKey,
        string SourceReceiptId,
        string StatusLabel,
        string DeliveryState,
        string DeliveryLane,
        string TemplateId,
        string RecipientScopeRef,
        int RecipientScopeCount,
        string ConsentSourceRef,
        string DeliveryReason,
        string Summary,
        bool VoterNotificationAllowed,
        bool DeliveryCandidate,
        bool PublicClaimAllowed,
        IReadOnlyList<string>? ProjectedRecipientRefs,
        DateTimeOffset RecordedAtUtc);

    private sealed record ProductLiftCloseoutDispatchReceiptState(
        string ReceiptId,
        string DedupKey,
        string SourceReceiptId,
        string StatusLabel,
        string DeliveryState,
        string DeliveryId,
        string? ProviderMessageId,
        string TemplateId,
        string TemplateVersion,
        string RecipientRef,
        string AddressHash,
        string ConsentSourceRef,
        string SuppressionCheck,
        string GovernorDecisionRef,
        string ReleaseProofReceiptId,
        string IdempotencyKey,
        string Summary,
        string? Error,
        bool PublicClaimAllowed,
        int RecoveryAttemptCount,
        string? LastRecoveryStatus,
        string? LastProviderState,
        DateTimeOffset? NextAutomaticRetryAtUtc,
        DateTimeOffset? LastOutcomeAtUtc,
        DateTimeOffset RequestedAtUtc,
        DateTimeOffset? AcceptedAtUtc,
        DateTimeOffset? LastRecoveryAtUtc);

    private sealed record ProductLiftJourneyReceiptState(
        string ReceiptId,
        string DedupKey,
        string SourceReceiptId,
        string EventKey,
        string StatusLabel,
        string GovernorDecisionRef,
        string ReleaseProofReceiptId,
        int RecipientCount,
        int SentCount,
        string Summary,
        bool PublicClaimAllowed,
        DateTimeOffset RecordedAtUtc);

    private sealed record ProductLiftDeliveryOutcomeReceiptState(
        string ReceiptId,
        string DedupKey,
        string OutcomeEventId,
        string Provider,
        string DispatchReceiptId,
        string SourceReceiptId,
        string DeliveryId,
        string? ProviderMessageId,
        string RecipientRef,
        string AddressHash,
        string IdentityMatchMode,
        string ProviderState,
        string StatusLabel,
        string SuppressionCheck,
        DateTimeOffset? RetryAtUtc,
        string Summary,
        string? Reason,
        string PayloadSha256,
        bool PublicClaimAllowed,
        DateTimeOffset OccurredAtUtc,
        DateTimeOffset RecordedAtUtc);

    private sealed record ProductLiftReconcileRunReceiptState(
        string RunReceiptId,
        string RunKind,
        string Status,
        int CandidateReceiptCount,
        int ReadyCandidateCount,
        int ReplayCandidateCount,
        int DispatchReceiptsCreated,
        int JourneyReceiptsRecorded,
        string Summary,
        DateTimeOffset RecordedAtUtc);

    private sealed record DispatchRecoveryCandidate(
        ProductLiftCloseoutDispatchReceiptState Receipt,
        ProductLiftWebhookReceiptState SourceReceipt,
        ProjectedCloseoutRecipient? Recipient,
        string Mode);

    private sealed record DeliveryOutcomeDispatchIdentityMatch(
        ProductLiftCloseoutDispatchReceiptState Receipt,
        string MatchMode);

    private enum DispatchRecoveryOutcome
    {
        Recovered,
        Suppressed,
        Blocked
    }
}

public sealed record PublicSignalWebhookAckResponse(
    string Provider,
    string Status,
    bool Duplicate,
    int RecordedEvents,
    string ReceiptId,
    string EventType,
    DateTimeOffset ReceivedAtUtc,
    bool RoutingReceiptRecorded,
    bool CloseoutReceiptRecorded);

public sealed record PublicSignalOperationsReconcileResponse(
    string Provider,
    string Status,
    int CandidateReceiptCount,
    int ReadyCandidateCount,
    int ReplayCandidateCount,
    int DispatchReceiptsCreated,
    int JourneyReceiptsRecorded,
    string RunReceiptId,
    DateTimeOffset RecordedAtUtc);

public sealed record PublicSignalOperationsRecoveryResponse(
    string Provider,
    string Status,
    int CandidateReceiptCount,
    int RecoveredReceiptCount,
    int SuppressedReceiptCount,
    int BlockedReceiptCount,
    string RunReceiptId,
    DateTimeOffset RecordedAtUtc);

public sealed record PublicSignalDeliveryOutcomeAckResponse(
    string Provider,
    string Status,
    bool Duplicate,
    string ReceiptId,
    string DispatchReceiptId,
    string DeliveryId,
    string ProviderState,
    DateTimeOffset RecordedAtUtc);
