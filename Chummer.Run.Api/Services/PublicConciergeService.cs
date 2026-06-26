using System.Text;
using System.Text.Json;
using System.Security.Cryptography;
using System.Net;
using Chummer.Contracts.Receipts;
using Chummer.Run.Api.ViewModels;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.WebUtilities;

namespace Chummer.Run.Api.Services;

public sealed class PublicConciergeService
{
    public const long MaxWebhookBodyBytes = 64 * 1024;
    private const string WorkflowRelativePath = ".codex-design/product/PUBLIC_CONCIERGE_WORKFLOWS.yaml";
    private const string SharedWebhookHeader = "X-Chummer-Concierge-Webhook-Secret";
    internal const int MaxWebhookTokenLength = 128;
    internal const int MaxWebhookSummaryLength = 512;
    private static readonly string[] SupportedLocales = ["en-US", "en", "de-AT", "de"];

    private readonly PublicCanonFileLoader _canon;
    private readonly PublicRouteCatalogService _routes;
    private readonly PublicConciergeStore _store;
    private readonly IConfiguration _configuration;
    private readonly ILogger<PublicConciergeService> _logger;
    private readonly Lazy<PublicConciergeCanonDocument> _document;

    public PublicConciergeService(
        PublicCanonFileLoader canon,
        PublicRouteCatalogService routes,
        PublicConciergeStore store,
        IConfiguration configuration,
        ILogger<PublicConciergeService> logger)
    {
        _canon = canon;
        _routes = routes;
        _store = store;
        _configuration = configuration;
        _logger = logger;
        _document = new Lazy<PublicConciergeCanonDocument>(() => _canon.LoadRequiredYaml<PublicConciergeCanonDocument>(WorkflowRelativePath));
    }

    public PublicConciergePageViewModel BuildPage(
        string surfaceKey,
        SiteChromeViewModel chrome,
        string? requestedLocale,
        string? acceptLanguage,
        string? entryRouteOverride = null,
        string? contextId = null)
    {
        ConciergeSurfaceDefinition surface = ResolveSurface(surfaceKey);
        ConciergeFlowDocument flow = ResolveFlow(surface.FlowId);
        (string locale, bool fallbackUsed) = ResolveLocale(requestedLocale, acceptLanguage);
        bool enabled = IsSurfaceEnabled(surface.ConfigPrefix);
        PublicConciergeWidgetViewModel widget = BuildWidget(surface, enabled);
        string entryRoute = entryRouteOverride ?? surface.EntryRoute;

        PublicConciergeBranchCardViewModel[] branches = flow.Branches
            .Select(branch => BuildBranchCard(surface, branch, chrome.Authenticated, locale, contextId))
            .ToArray();

        TrustPageActionViewModel[] actions =
        [
            new(surface.ReturnActionLabel, entryRoute, "primary"),
            new(surface.SecondaryActionLabel, surface.SecondaryActionHref, "secondary")
        ];

        List<string> proofPoints =
        [
            $"Locale {locale}",
            enabled ? "Kill switch armed but currently enabled" : "Kill switch disabled the optional widget",
            "Chummer path stays visible"
        ];
        proofPoints.AddRange(flow.ProofAnchors?.Select(HumanizeToken) ?? Enumerable.Empty<string>());

        return new PublicConciergePageViewModel(
            Chrome: chrome,
            FlowId: flow.Id,
            Eyebrow: surface.Eyebrow,
            Heading: surface.Heading,
            Intro: surface.Intro,
            EntrySurfaceLabel: HumanizeToken(flow.EntrySurface ?? surface.EntrySurfaceLabel),
            Locale: locale,
            LocaleFallbackUsed: fallbackUsed,
            ProofPoints: proofPoints.Distinct(StringComparer.OrdinalIgnoreCase).ToArray(),
            Branches: branches,
            Actions: actions,
            Widget: widget);
    }

    public ConciergeRedirectResolution ResolveBranchRedirect(
        string surfaceKey,
        string branchId,
        bool authenticated,
        string? requestedLocale,
        string? acceptLanguage,
        string? contextId = null)
    {
        ConciergeSurfaceDefinition surface = ResolveSurface(surfaceKey);
        ConciergeFlowDocument flow = ResolveFlow(surface.FlowId);
        string normalizedBranchId = NormalizeRequiredToken(branchId, "branch id", nameof(branchId));
        ConciergeBranchDocument branch = flow.Branches.FirstOrDefault(candidate => string.Equals(candidate.Id, normalizedBranchId, StringComparison.OrdinalIgnoreCase))
            ?? throw new KeyNotFoundException($"Unknown concierge branch '{branchId}' for '{surfaceKey}'.");
        (string locale, _) = ResolveLocale(requestedLocale, acceptLanguage);

        ConciergeBranchPresentation presentation = ResolveBranchPresentation(surface, branch, authenticated);
        string correlationId = $"concierge-{Guid.NewGuid():N}";
        string receiptId = $"concierge-branch-{Guid.NewGuid():N}";
        string targetHref = ResolveTargetHref(surface, branch, authenticated, locale, correlationId, receiptId, contextId);
        bool external = IsExternalHref(targetHref);

        if (!external)
        {
            _routes.ValidateRouteTarget(targetHref, $"concierge branch '{surfaceKey}:{branch.Id}'");
        }

        PublicConciergeBranchReceipt receipt = new(
            ReceiptId: receiptId,
            SurfaceKey: surface.SurfaceKey,
            FlowId: flow.Id,
            BranchId: branch.Id,
            EntrySurface: flow.EntrySurface ?? surface.EntrySurfaceLabel,
            Locale: locale,
            CorrelationId: correlationId,
            TargetHref: targetHref,
            TargetKind: external ? "external_redirect" : "first_party_redirect",
            RecordedAtUtc: DateTimeOffset.UtcNow,
            Envelope: ReceiptEnvelopeFactory.Runtime(
                receiptKind: "public_concierge_branch",
                ownerScope: "public.concierge",
                exposureClass: ReceiptExposureClasses.PublicSafe,
                evidenceRef: receiptId,
                reviewState: external ? "external_redirect" : "first_party_redirect"));

        lock (_store.Gate)
        {
            _store.BranchReceiptsById[receipt.ReceiptId] = receipt;
            _store.PersistLocked();
        }

        _logger.LogInformation(
            "Recorded concierge branch receipt {ReceiptId} for {SurfaceKey}/{BranchId} -> {TargetHref}.",
            receipt.ReceiptId,
            surface.SurfaceKey,
            branch.Id,
            targetHref);

        return new ConciergeRedirectResolution(
            RedirectHref: targetHref,
            ReceiptId: receiptId,
            CorrelationId: correlationId,
            DestinationLabel: presentation.DestinationLabel);
    }

    public ConciergeWebhookResult RecordWebhook(
        string providerKey,
        JsonElement payload,
        IHeaderDictionary headers,
        string? remoteIp)
    {
        if (payload.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("webhook payload must be a JSON object.", nameof(payload));
        }

        string provider = NormalizeRequiredToken(providerKey, "provider", nameof(providerKey));

        string verificationState = VerifyWebhook(provider, headers);
        string flowId = NormalizeOptionalToken(ExtractFirstString(payload, "concierge_flow_id", "flow_id", "flow"), "flow id") ?? "unknown_flow";
        string? branchId = NormalizeOptionalToken(ExtractFirstString(payload, "branch_id", "branch"), "branch id");
        string correlationId = NormalizeOptionalToken(ExtractFirstString(payload, "correlation_id", "session_id", "response_id"), "correlation id")
            ?? $"concierge-{Guid.NewGuid():N}";
        string locale = NormalizeOptionalToken(ExtractFirstString(payload, "locale"), "locale") ?? "en-US";
        string eventType = NormalizeOptionalToken(ExtractFirstString(payload, "event_type", "type", "event"), "event type") ?? "submitted";
        string status = NormalizeOptionalToken(ExtractFirstString(payload, "status", "state"), "status") ?? "received";
        string? providerReceiptId = NormalizeOptionalToken(ExtractFirstString(payload, "provider_receipt_id", "receipt_id", "submission_id", "booking_id", "id", "event_id"), "provider receipt id");
        string summary = NormalizeSummary(
            ExtractFirstString(payload, "summary", "message", "headline")
            ?? $"{HumanizeToken(provider)} {HumanizeToken(eventType)} record captured.");
        string? caseId = NormalizeOptionalToken(ExtractFirstString(payload, "case_id", "support_case_id"), "case id");
        string? bookingId = NormalizeOptionalToken(ExtractFirstString(payload, "booking_id", "appointment_id"), "booking id");
        string? assetRef = NormalizeOptionalToken(ExtractFirstString(payload, "asset_ref", "registry_asset_ref"), "asset reference");
        string? publicationRef = NormalizeOptionalToken(ExtractFirstString(payload, "publication_ref", "registry_publication_ref"), "publication reference");
        string? mediaKind = NormalizeOptionalToken(ExtractFirstString(payload, "media_kind", "response_kind"), "media kind");

        string dedupKey = string.Join(':',
            provider,
            providerReceiptId ?? correlationId,
            flowId,
            branchId ?? eventType);

        PublicConciergeWebhookReceipt receipt;
        string? moderationItemId = null;

        lock (_store.Gate)
        {
            if (_store.WebhookReceiptIdByDedupKey.TryGetValue(dedupKey, out string? existingId)
                && _store.WebhookReceiptsById.TryGetValue(existingId, out PublicConciergeWebhookReceipt? existing))
            {
                return new ConciergeWebhookResult(existing.ReceiptId, verificationState, existing.Summary, null);
            }

            receipt = new PublicConciergeWebhookReceipt(
                ReceiptId: $"concierge-webhook-{Guid.NewGuid():N}",
                ProviderKey: provider,
                FlowId: flowId,
                BranchId: branchId,
                CorrelationId: correlationId,
                Locale: locale,
                EventType: eventType,
                Status: status,
                VerificationState: verificationState,
                ProviderReceiptId: providerReceiptId,
                Summary: summary,
                FirstPartyCaseId: caseId,
                BookingId: bookingId,
                AssetRef: assetRef,
                PublicationRef: publicationRef,
                MediaKind: mediaKind,
                ReceivedAtUtc: DateTimeOffset.UtcNow,
                Metadata: BuildMetadata(remoteIp, flowId, branchId),
                Envelope: ReceiptEnvelopeFactory.Runtime(
                    receiptKind: "public_concierge_webhook",
                    ownerScope: "public.concierge",
                    exposureClass: ReceiptExposureClasses.Internal,
                    evidenceRef: providerReceiptId ?? correlationId,
                    reviewState: verificationState));

            _store.WebhookReceiptsById[receipt.ReceiptId] = receipt;
            _store.WebhookReceiptIdByDedupKey[dedupKey] = receipt.ReceiptId;

            if (ShouldCreateModerationItem(receipt))
            {
                PublicConciergeModerationItem item = new(
                    ItemId: $"concierge-moderation-{Guid.NewGuid():N}",
                    SourceReceiptId: receipt.ReceiptId,
                    CorrelationId: correlationId,
                    Status: "pending_moderation",
                    MediaKind: mediaKind ?? "media_response",
                    Summary: summary,
                    AssetRef: assetRef,
                    PublicationRef: publicationRef,
                    CreatedAtUtc: DateTimeOffset.UtcNow);
                _store.ModerationItemsById[item.ItemId] = item;
                moderationItemId = item.ItemId;
            }

            _store.PersistLocked();
        }

        _logger.LogInformation(
            "Recorded concierge webhook receipt {ReceiptId} for provider {ProviderKey}, flow {FlowId}, branch {BranchId}.",
            receipt.ReceiptId,
            provider,
            flowId,
            branchId ?? "none");

        return new ConciergeWebhookResult(receipt.ReceiptId, verificationState, summary, moderationItemId);
    }

    private ConciergeFlowDocument ResolveFlow(string flowId)
        => (_document.Value.Flows ?? new List<ConciergeFlowDocument>())
            .FirstOrDefault(flow => string.Equals(flow.Id, flowId, StringComparison.OrdinalIgnoreCase))
            ?? throw new InvalidOperationException($"Public concierge flow '{flowId}' is missing from canon.");

    private ConciergeSurfaceDefinition ResolveSurface(string surfaceKey)
    {
        string normalized = NormalizeRequiredToken(surfaceKey, "surfaceKey", nameof(surfaceKey));

        return normalized switch
        {
            "downloads" => new ConciergeSurfaceDefinition(
                SurfaceKey: normalized,
                ConfigPrefix: "DOWNLOADS",
                FlowId: "downloads_concierge",
                Eyebrow: "Setup help",
                Heading: "Get Chummer installed.",
                Intro: "Use the direct download first. If setup is still blocked, send the platform, build, and what happened.",
                EntrySurfaceLabel: "downloads",
                EntryRoute: "/downloads",
                ReturnActionLabel: "Back to downloads",
                SecondaryActionLabel: "Open help",
                SecondaryActionHref: "/help"),
            "now" => new ConciergeSurfaceDefinition(
                SurfaceKey: normalized,
                ConfigPrefix: "NOW",
                FlowId: "release_concierge",
                Eyebrow: "Release help",
                Heading: "Check what changed or get update help.",
                Intro: "Read the current notes first. If an update fails, send the platform, build, and error.",
                EntrySurfaceLabel: "now",
                EntryRoute: "/now",
                ReturnActionLabel: "Back to current release",
                SecondaryActionLabel: "Open changelog",
                SecondaryActionHref: "/changelog"),
            "contact" => new ConciergeSurfaceDefinition(
                SurfaceKey: normalized,
                ConfigPrefix: "CONTACT",
                FlowId: "support_entry_concierge",
                Eyebrow: "Help routing",
                Heading: "Choose the right help path.",
                Intro: "Public ideas, private support, and account return are separate. Pick the one that matches the problem.",
                EntrySurfaceLabel: "contact",
                EntryRoute: "/contact",
                ReturnActionLabel: "Back to contact",
                SecondaryActionLabel: "Open feedback",
                SecondaryActionHref: "/feedback"),
            "campaign-invite" => new ConciergeSurfaceDefinition(
                SurfaceKey: normalized,
                ConfigPrefix: "INVITE",
                FlowId: "campaign_invite_concierge",
                Eyebrow: "Campaign invite",
                Heading: "Continue the invite, review the primer, or ask for session-zero help.",
                Intro: "Invite routing, primer context, and session-zero help stay here. This page does not replace account identity, support, or campaign state.",
                EntrySurfaceLabel: "invite page",
                EntryRoute: "/signup",
                ReturnActionLabel: "Continue the invite",
                SecondaryActionLabel: "Open help",
                SecondaryActionHref: "/help"),
            "creator-publication" => new ConciergeSurfaceDefinition(
                SurfaceKey: normalized,
                ConfigPrefix: "CREATOR",
                FlowId: "creator_consult_concierge",
                Eyebrow: "Creator concierge",
                Heading: "Choose the next creator step without losing publication history.",
                Intro: "This wrapper keeps publication discovery, creator consult routing, and reviewed intake separated from installs, support, and account status.",
                EntrySurfaceLabel: "creator publication",
                EntryRoute: "/artifacts",
                ReturnActionLabel: "Back to publication",
                SecondaryActionLabel: "Open publications",
                SecondaryActionHref: "/artifacts"),
            "testimonials" => new ConciergeSurfaceDefinition(
                SurfaceKey: normalized,
                ConfigPrefix: "TESTIMONIALS",
                FlowId: "testimonial_capture",
                Eyebrow: "Public feedback",
                Heading: "Leave a moderated public note without confusing it for support or a product decision.",
                Intro: "This wrapper keeps testimonials optional, moderated, and Chummer-owned. It never replaces support intake, account recovery, or publication approval.",
                EntrySurfaceLabel: "testimonial capture",
                EntryRoute: "/feedback",
                ReturnActionLabel: "Back to feedback",
                SecondaryActionLabel: "Open publications",
                SecondaryActionHref: "/artifacts"),
            _ => throw new KeyNotFoundException($"Unknown concierge surface '{surfaceKey}'.")
        };
    }

    private PublicConciergeBranchCardViewModel BuildBranchCard(
        ConciergeSurfaceDefinition surface,
        ConciergeBranchDocument branch,
        bool authenticated,
        string locale,
        string? contextId)
    {
        ConciergeBranchPresentation presentation = ResolveBranchPresentation(surface, branch, authenticated);
        string actionHref = BuildBranchRoute(surface.SurfaceKey, branch.Id, locale, contextId);
        return new PublicConciergeBranchCardViewModel(
            BranchId: branch.Id,
            Title: presentation.Title,
            Summary: presentation.Summary,
            ActionHref: actionHref,
            ActionLabel: presentation.ActionLabel,
            Tone: presentation.Tone,
            DestinationLabel: presentation.DestinationLabel);
    }

    private ConciergeBranchPresentation ResolveBranchPresentation(
        ConciergeSurfaceDefinition surface,
        ConciergeBranchDocument branch,
        bool authenticated)
    {
        return (surface.SurfaceKey, branch.Id) switch
        {
            ("downloads", "download_now") => new ConciergeBranchPresentation(
                "Download now",
                "Start with the current installer for your platform.",
                "Open downloads",
                "primary",
                "Download"),
            ("downloads", "platform_help") => new ConciergeBranchPresentation(
                "Which platform should I pick?",
                "Compare Windows, Linux, and macOS availability.",
                "Compare platforms",
                "secondary",
                "Platforms"),
            ("downloads", "setup_help") => new ConciergeBranchPresentation(
                "I need setup help",
                "Send setup details if the installer still fails.",
                "Send setup issue",
                "ghost",
                "Setup help"),
            ("downloads", "unresolved_setup_issue") => new ConciergeBranchPresentation(
                "Setup is still blocked",
                "Send setup context so support can reproduce the problem asynchronously.",
                "Send setup issue",
                "ghost",
                "Support follow-up"),
            ("now", "watch_whats_new") => new ConciergeBranchPresentation(
                "Watch what changed",
                "Open the short release overview.",
                "Open what changed",
                "primary",
                "Release overview"),
            ("now", "read_notes") => new ConciergeBranchPresentation(
                "Read the release notes",
                "Use the plain-text version before updating.",
                "Read release notes",
                "secondary",
                "Release notes"),
            ("now", "update_help") => new ConciergeBranchPresentation(
                "I need update help",
                "Send update details if the app does not update cleanly.",
                "Send update issue",
                "ghost",
                "Update help"),
            ("now", "book_help") => new ConciergeBranchPresentation(
                "Update is still blocked",
                "Send update context so support can reproduce the problem asynchronously.",
                "Send update issue",
                "ghost",
                "Support follow-up"),
            ("contact", "public_feedback") => new ConciergeBranchPresentation(
                "This can stay public",
                "Use the public feedback path for safe feedback, feature demand, and non-sensitive public bugs.",
                "Open feedback",
                "primary",
                "Public feedback"),
            ("contact", "private_support") => new ConciergeBranchPresentation(
                "This needs private support",
                "Keep logs, account detail, and support history on the private support path.",
                "Open private support",
                "secondary",
                "Private support"),
            ("contact", "install_continuity") => new ConciergeBranchPresentation(
                "I need account return",
                authenticated
                    ? "Open Devices and access so the affected install stays attached to the same return path."
                    : "Open Downloads first, then attach the installed copy when you are ready for account return.",
                authenticated ? "Open devices and access" : "Open downloads",
                "ghost",
                authenticated ? "Account return" : "Downloads"),
            ("contact", "human_help") => new ConciergeBranchPresentation(
                "I am still blocked",
                "Send a private support note with the details needed to reproduce the problem.",
                "Send support issue",
                "ghost",
                "Support follow-up"),
            ("campaign-invite", "continue_join") => new ConciergeBranchPresentation(
                "Continue the invite",
                authenticated
                    ? "Stay signed in so the join code remains attached to your account and return path."
                    : "Claim your copy only when you are ready to continue the invite and keep the return path attached.",
                authenticated ? "Open invite tools" : "Claim your copy",
                "primary",
                authenticated ? "Signed-in invite follow-through" : "Account entry"),
            ("campaign-invite", "watch_primer") => new ConciergeBranchPresentation(
                "Watch the primer",
                "Open the invite primer page when a short orientation is the fastest way to reduce friction before the first session.",
                "Open primer guide",
                "secondary",
                "Invite primer"),
            ("campaign-invite", "open_primer_packet") => new ConciergeBranchPresentation(
                "Open the primer packet",
                "Stay on the same invite primer page when you want expectations, a prep list, and calmer next steps.",
                "Open primer packet",
                "ghost",
                "Invite primer"),
            ("campaign-invite", "ask_questions") => new ConciergeBranchPresentation(
                "Ask questions first",
                "Route into structured invite and onboarding help before this becomes a support or install problem.",
                "Open invite help",
                "ghost",
                "Structured help or approved intake"),
            ("campaign-invite", "session_zero_call") => new ConciergeBranchPresentation(
                "Request session-zero help",
                "Request session-zero or onboarding help without turning booking into the campaign record.",
                "Request session-zero help",
                "ghost",
                "Session-zero support"),
            ("creator-publication", "how_publishing_works") => new ConciergeBranchPresentation(
                "How publishing works",
                "Stay on the creator publication page when you want the history, lineage, and discovery status before you ask for help.",
                "Open creator discovery",
                "primary",
                "Creator discovery"),
            ("creator-publication", "book_consult") => new ConciergeBranchPresentation(
                "Book a creator consult",
                "Request a short consult without making booking the source for publication status.",
                "Request creator consult",
                "secondary",
                "Creator consult"),
            ("creator-publication", "submit_interest") => new ConciergeBranchPresentation(
                "Submit creator interest",
                "Open reviewed intake when the next step is a creator submission, not a support case or install question.",
                "Open creator intake",
                "ghost",
                "Structured help or approved intake"),
            ("creator-publication", "open_creator_packet") => new ConciergeBranchPresentation(
                "Open the creator packet",
                "Return to the publication detail page when you want to inspect the packet, status, or history again.",
                "Back to publication",
                "ghost",
                "Publication history"),
            ("testimonials", "video_review") => new ConciergeBranchPresentation(
                "Leave a video note",
                "Use the moderated public feedback path when you want to share a public story without turning it into support.",
                "Open video note",
                "primary",
                "Moderated public feedback"),
            ("testimonials", "audio_review") => new ConciergeBranchPresentation(
                "Leave an audio note",
                "Use the same moderation path when audio is enough and the note should be reviewed before publication.",
                "Open audio note",
                "secondary",
                "Moderated public feedback"),
            ("testimonials", "quick_rating") => new ConciergeBranchPresentation(
                "Leave a quick rating",
                "Use the public feedback path when a lightweight note is enough and no media upload is needed.",
                "Open feedback",
                "ghost",
                "Public signal route"),
            _ => new ConciergeBranchPresentation(
                HumanizeToken(branch.Id),
                $"Follow the {HumanizeToken(branch.Target ?? "next step")} path from this page.",
                "Continue",
                "secondary",
                "Next step")
        };
    }

    private string ResolveTargetHref(
        ConciergeSurfaceDefinition surface,
        ConciergeBranchDocument branch,
        bool authenticated,
        string locale,
        string correlationId,
        string receiptId,
        string? contextId)
    {
        string? overrideUrl = GetSurfaceConfig(surface.ConfigPrefix, $"BRANCH_{NormalizeEnvToken(branch.Id)}_URL");
        string targetHref = overrideUrl ?? ResolveDefaultTargetHref(surface, branch, authenticated, contextId);

        Dictionary<string, string?> query = new(StringComparer.OrdinalIgnoreCase)
        {
            ["concierge_flow_id"] = surface.FlowId,
            ["concierge_receipt_id"] = receiptId,
            ["correlation_id"] = correlationId,
            ["locale"] = locale
        };
        if (!string.IsNullOrWhiteSpace(contextId))
        {
            query[string.Equals(surface.SurfaceKey, "campaign-invite", StringComparison.OrdinalIgnoreCase)
                ? "invite_code"
                : "publication_id"] = contextId;
        }

        return QueryHelpers.AddQueryString(targetHref, query);
    }

    private static string ResolveDefaultTargetHref(
        ConciergeSurfaceDefinition surface,
        ConciergeBranchDocument branch,
        bool authenticated,
        string? contextId)
    {
        return (surface.SurfaceKey, branch.Id) switch
        {
            ("downloads", "download_now") => "/downloads#recommended-download",
            ("downloads", "platform_help") => "/downloads#platform-shelf",
            ("downloads", "setup_help") => "/contact?kind=install_help&title=Setup%20help&summary=Need%20setup%20help#support-intake",
            ("downloads", "unresolved_setup_issue") => "/contact?kind=install_help&title=Setup%20is%20still%20blocked&summary=Setup%20still%20fails%20after%20using%20the%20current%20installer#support-intake",
            ("now", "watch_whats_new") => "/changelog",
            ("now", "read_notes") => "/now#public-shipped-closeout",
            ("now", "update_help") => "/contact?kind=install_update&title=Need%20update%20help&summary=Need%20update%20help#support-intake",
            ("now", "book_help") => "/contact?kind=install_update&title=Update%20is%20still%20blocked&summary=Update%20still%20fails%20after%20using%20the%20current%20build#support-intake",
            ("contact", "public_feedback") => "/feedback",
            ("contact", "private_support") => "/contact#support-intake",
            ("contact", "install_continuity") => authenticated ? "/account/access" : "/downloads",
            ("contact", "human_help") => "/contact?kind=install_help&title=Still%20blocked&summary=Need%20private%20support%20follow-up#support-intake",
            ("campaign-invite", "continue_join") => authenticated
                ? "/account/work#community-op-invites"
                : BuildInviteContinuationRoute(contextId),
            ("campaign-invite", "watch_primer") => BuildInvitePrimerHref("video", contextId),
            ("campaign-invite", "open_primer_packet") => BuildInvitePrimerHref("packet", contextId),
            ("campaign-invite", "ask_questions") => "/contact?kind=campaign_invite&title=Need%20campaign%20invite%20help&summary=Need%20invite%20or%20primer%20follow-up#support-intake",
            ("campaign-invite", "session_zero_call") => "/contact?kind=session_zero&title=Request%20session%20zero%20help&summary=Need%20a%20short%20session%20zero%20or%20invite%20briefing#support-intake",
            ("creator-publication", "how_publishing_works") => "/artifacts#public-shared-publications",
            ("creator-publication", "book_consult") => "/contact?kind=creator_consult&title=Need%20creator%20consult&summary=Request%20a%20creator%20consult#support-intake",
            ("creator-publication", "submit_interest") => "/contact?kind=creator_interest&title=Submit%20creator%20interest&summary=Need%20creator%20follow-up#support-intake",
            ("creator-publication", "open_creator_packet") => string.IsNullOrWhiteSpace(contextId)
                ? "/artifacts#public-shared-publications"
                : $"/artifacts/publications/{Uri.EscapeDataString(contextId)}",
            ("testimonials", "video_review") => "/contact?kind=public_note&title=Share%20video%20note&summary=Want%20to%20leave%20a%20moderated%20video%20testimonial#support-intake",
            ("testimonials", "audio_review") => "/contact?kind=public_note&title=Share%20audio%20note&summary=Want%20to%20leave%20a%20moderated%20audio%20testimonial#support-intake",
            ("testimonials", "quick_rating") => "/feedback",
            _ => surface.EntryRoute
        };
    }

    private PublicConciergeWidgetViewModel BuildWidget(ConciergeSurfaceDefinition surface, bool enabled)
    {
        if (!enabled)
        {
            return new PublicConciergeWidgetViewModel(
                StatusLabel: "Disabled by kill switch",
                Summary: "This public surface is using the direct Chummer path right now. The supported links below remain the source.");
        }

        string? iframeHref = GetSurfaceConfig(surface.ConfigPrefix, "WIDGET_URL");
        if (string.IsNullOrWhiteSpace(iframeHref))
        {
            return new PublicConciergeWidgetViewModel(
                StatusLabel: "Chummer path only",
                Summary: "No optional guided widget is configured on this host, so the wrapper stays fully inside Chummer.");
        }

        if (!Uri.TryCreate(iframeHref, UriKind.Absolute, out Uri? widgetUri))
        {
            return new PublicConciergeWidgetViewModel(
                StatusLabel: "Direct Chummer path",
                Summary: "The optional guided widget is unavailable on this host, so the Chummer branch cards below stay active.");
        }

        string origin = $"{widgetUri.Scheme}://{widgetUri.Host}{(widgetUri.IsDefaultPort ? string.Empty : $":{widgetUri.Port}")}";
        StringBuilder policy = new();
        policy.Append("default-src 'self'; ");
        policy.Append("base-uri 'self'; ");
        policy.Append("frame-ancestors 'self'; ");
        policy.Append("img-src 'self' data: https:; ");
        policy.Append("style-src 'self' 'unsafe-inline'; ");
        policy.Append("script-src 'self' 'unsafe-inline'; ");
        policy.Append($"frame-src 'self' {origin}; ");
        policy.Append($"connect-src 'self' {origin}; ");
        policy.Append($"form-action 'self' {origin};");

        return new PublicConciergeWidgetViewModel(
            StatusLabel: "Optional guided widget live",
            Summary: "The embedded guide is optional, kill-switchable, and backed by the same Chummer links shown underneath it.",
            IframeHref: iframeHref,
            HostLabel: widgetUri.Host,
            ContentSecurityPolicy: policy.ToString());
    }

    private string VerifyWebhook(string provider, IHeaderDictionary headers)
    {
        string? configuredSecret = _configuration[$"CHUMMER_PUBLIC_CONCIERGE_PROVIDER_{NormalizeEnvToken(provider)}_WEBHOOK_SECRET"];
        if (string.IsNullOrWhiteSpace(configuredSecret))
        {
            throw new InvalidOperationException("Concierge webhook adapter is not configured.");
        }

        string? headerValue = headers[SharedWebhookHeader].FirstOrDefault();
        if (!FixedTimeEquals(headerValue?.Trim() ?? string.Empty, configuredSecret.Trim()))
        {
            throw new UnauthorizedAccessException("Webhook secret mismatch.");
        }

        return "verified";
    }

    private static bool FixedTimeEquals(string left, string right)
    {
        ReadOnlySpan<byte> leftBytes = Encoding.UTF8.GetBytes(left);
        ReadOnlySpan<byte> rightBytes = Encoding.UTF8.GetBytes(right);
        return leftBytes.Length == rightBytes.Length && CryptographicOperations.FixedTimeEquals(leftBytes, rightBytes);
    }

    private bool IsSurfaceEnabled(string configPrefix)
    {
        bool globalEnabled = GetBool("CHUMMER_PUBLIC_CONCIERGE_ENABLED", defaultValue: true);
        if (!globalEnabled)
        {
            return false;
        }

        return GetBool($"CHUMMER_PUBLIC_CONCIERGE_{configPrefix}_ENABLED", defaultValue: true);
    }

    private bool GetBool(string key, bool defaultValue)
    {
        string? configured = _configuration[key];
        return bool.TryParse(configured, out bool parsed) ? parsed : defaultValue;
    }

    private string? GetSurfaceConfig(string configPrefix, string suffix)
        => _configuration[$"CHUMMER_PUBLIC_CONCIERGE_{configPrefix}_{suffix}"];

    private static bool ShouldCreateModerationItem(PublicConciergeWebhookReceipt receipt)
        => string.Equals(receipt.FlowId, "testimonial_capture", StringComparison.OrdinalIgnoreCase)
           || receipt.MediaKind is not null
           || receipt.AssetRef is not null
           || receipt.PublicationRef is not null;

    private static IReadOnlyDictionary<string, string> BuildMetadata(string? remoteIp, string flowId, string? branchId)
    {
        Dictionary<string, string> metadata = new(StringComparer.OrdinalIgnoreCase)
        {
            ["flow_id"] = flowId
        };

        if (!string.IsNullOrWhiteSpace(branchId))
        {
            metadata["branch_id"] = branchId!;
        }

        if (TryNormalizeIpAddress(remoteIp, out string? normalizedIp))
        {
            metadata["remote_ip"] = normalizedIp!;
        }

        return metadata;
    }

    private static bool TryNormalizeIpAddress(string? remoteIp, out string? normalizedIp)
    {
        normalizedIp = NormalizeOptionalToken(remoteIp, "remote ip");
        if (normalizedIp is null)
        {
            return false;
        }

        if (!IPAddress.TryParse(normalizedIp, out IPAddress? parsed))
        {
            normalizedIp = null;
            return false;
        }

        normalizedIp = parsed.ToString();
        return true;
    }

    private static bool IsExternalHref(string href)
        => Uri.TryCreate(href, UriKind.Absolute, out _);

    private static string BuildBranchRoute(string surfaceKey, string branchId, string locale, string? contextId)
    {
        string basePath = surfaceKey switch
        {
            "campaign-invite" => $"/join/concierge/{Uri.EscapeDataString(branchId)}",
            "creator-publication" => string.IsNullOrWhiteSpace(contextId)
                ? $"/artifacts/creator/concierge/{Uri.EscapeDataString(branchId)}"
                : $"/artifacts/publications/{Uri.EscapeDataString(contextId)}/concierge/{Uri.EscapeDataString(branchId)}",
            "testimonials" => $"/testimonials/concierge/{Uri.EscapeDataString(branchId)}",
            _ => $"/{surfaceKey}/concierge/{Uri.EscapeDataString(branchId)}"
        };

        Dictionary<string, string?> query = new(StringComparer.OrdinalIgnoreCase)
        {
            ["locale"] = locale
        };
        if (!string.IsNullOrWhiteSpace(contextId) && !string.Equals(surfaceKey, "creator-publication", StringComparison.OrdinalIgnoreCase))
        {
            query[string.Equals(surfaceKey, "campaign-invite", StringComparison.OrdinalIgnoreCase)
                ? "code"
                : "publicationId"] = contextId;
        }

        return QueryHelpers.AddQueryString(basePath, query);
    }

    private static string BuildInviteContinuationRoute(string? inviteCode)
    {
        Dictionary<string, string?> nextQuery = new(StringComparer.OrdinalIgnoreCase);
        if (!string.IsNullOrWhiteSpace(inviteCode))
        {
            nextQuery["code"] = inviteCode;
        }

        string next = nextQuery.Count == 0
            ? "/join/concierge"
            : QueryHelpers.AddQueryString("/join/concierge", nextQuery);
        return "/signup?next=" + Uri.EscapeDataString(next);
    }

    private static string BuildInvitePrimerHref(string mode, string? inviteCode)
    {
        Dictionary<string, string?> query = new(StringComparer.OrdinalIgnoreCase)
        {
            ["mode"] = mode
        };
        if (!string.IsNullOrWhiteSpace(inviteCode))
        {
            query["code"] = inviteCode;
        }

        return QueryHelpers.AddQueryString("/join/primer", query);
    }

    private static (string Locale, bool FallbackUsed) ResolveLocale(string? requestedLocale, string? acceptLanguage)
    {
        string? direct = NormalizeLocale(requestedLocale);
        if (direct is not null)
        {
            return (direct, false);
        }

        if (!string.IsNullOrWhiteSpace(acceptLanguage))
        {
            foreach (string segment in acceptLanguage.Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            {
                string candidate = segment.Split(';', StringSplitOptions.TrimEntries)[0];
                string? normalized = NormalizeLocale(candidate);
                if (normalized is not null)
                {
                    return (normalized, false);
                }
            }
        }

        return ("en-US", true);
    }

    private static string? NormalizeLocale(string? value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string trimmed = value.Trim();
        string? direct = SupportedLocales.FirstOrDefault(candidate => string.Equals(candidate, trimmed, StringComparison.OrdinalIgnoreCase));
        if (direct is not null)
        {
            return direct;
        }

        string[] normalizedParts = trimmed.Split('-', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
        if (normalizedParts.Length == 1)
        {
            return SupportedLocales.FirstOrDefault(candidate => candidate.StartsWith($"{normalizedParts[0]}-", StringComparison.OrdinalIgnoreCase))
                ?? SupportedLocales.FirstOrDefault(candidate => string.Equals(candidate, normalizedParts[0], StringComparison.OrdinalIgnoreCase));
        }

        return null;
    }

    private static string? ExtractFirstString(JsonElement element, params string[] propertyNames)
    {
        if (element.ValueKind != JsonValueKind.Object)
        {
            return null;
        }

        foreach (string propertyName in propertyNames)
        {
            if (!TryGetProperty(element, propertyName, out JsonElement value))
            {
                continue;
            }

            if (value.ValueKind == JsonValueKind.String)
            {
                return value.GetString();
            }

            if (value.ValueKind is JsonValueKind.Number or JsonValueKind.True or JsonValueKind.False)
            {
                return value.ToString();
            }
        }

        return null;
    }

    private static bool TryGetProperty(JsonElement element, string propertyName, out JsonElement value)
    {
        foreach (JsonProperty property in element.EnumerateObject())
        {
            if (string.Equals(property.Name, propertyName, StringComparison.OrdinalIgnoreCase))
            {
                value = property.Value;
                return true;
            }
        }

        value = default;
        return false;
    }

    private static string NormalizeRequiredToken(string? value, string label, string? paramName = null)
        => NormalizeOptionalToken(value, label)
            ?? throw new ArgumentException($"{label} is required.", paramName ?? label);

    private static string? NormalizeOptionalToken(string? value, string label)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return null;
        }

        string normalized = value.Trim();
        if (normalized.Length > MaxWebhookTokenLength)
        {
            throw new ArgumentException($"{label} must be {MaxWebhookTokenLength} characters or fewer.", label);
        }

        return normalized;
    }

    private static string NormalizeSummary(string value)
    {
        string normalized = value.Trim();
        if (normalized.Length == 0)
        {
            throw new ArgumentException("summary is required.", nameof(value));
        }

        if (normalized.Length > MaxWebhookSummaryLength)
        {
            throw new ArgumentException($"summary must be {MaxWebhookSummaryLength} characters or fewer.", nameof(value));
        }

        return normalized;
    }

    private static string NormalizeEnvToken(string value)
        => value.Replace("-", "_", StringComparison.Ordinal)
            .Replace(' ', '_')
            .ToUpperInvariant();

    private static string HumanizeToken(string value)
        => string.IsNullOrWhiteSpace(value)
            ? "Current"
            : string.Join(' ', value
                .Split(['_', '-'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                .Select(static part => char.ToUpperInvariant(part[0]) + part[1..].ToLowerInvariant()));
}

public sealed record ConciergeRedirectResolution(
    string RedirectHref,
    string ReceiptId,
    string CorrelationId,
    string DestinationLabel);

public sealed record ConciergeWebhookResult(
    string ReceiptId,
    string VerificationState,
    string Summary,
    string? ModerationItemId);

internal sealed record ConciergeSurfaceDefinition(
    string SurfaceKey,
    string ConfigPrefix,
    string FlowId,
    string Eyebrow,
    string Heading,
    string Intro,
    string EntrySurfaceLabel,
    string EntryRoute,
    string ReturnActionLabel,
    string SecondaryActionLabel,
    string SecondaryActionHref);

internal sealed record ConciergeBranchPresentation(
    string Title,
    string Summary,
    string ActionLabel,
    string Tone,
    string DestinationLabel);

internal sealed class PublicConciergeCanonDocument
{
    public string? Product { get; init; }
    public string? Surface { get; init; }
    public int Version { get; init; }
    public string? Purpose { get; init; }
    public ConciergeDefaultsDocument? Defaults { get; init; }
    public List<ConciergeFlowDocument>? Flows { get; init; }
}

internal sealed class ConciergeFlowDocument
{
    public string Id { get; init; } = string.Empty;
    public string? Audience { get; init; }
    public string? EntrySurface { get; init; }
    public string? WidgetGoal { get; init; }
    public List<ConciergeBranchDocument> Branches { get; init; } = [];
    public List<string>? ProofAnchors { get; init; }
    public ConciergeFlowPostureDocument? Posture { get; init; }
}

internal sealed class ConciergeBranchDocument
{
    public string Id { get; init; } = string.Empty;
    public string? Target { get; init; }
}

internal sealed class ConciergeDefaultsDocument
{
    public string? Owner { get; init; }
    public string? RenderOwner { get; init; }
    public string? RegistryOwner { get; init; }
    public string? WidgetLane { get; init; }
    public string? BookingLane { get; init; }
    public string? IntakeLane { get; init; }
    public string? LongFormVideoLane { get; init; }
    public string? PacketLane { get; init; }
    public string? PreviewLane { get; init; }
    public string? SurveyLane { get; init; }
    public List<string>? ApprovalLane { get; init; }
    public List<string>? PublicOnlyWidgetSurfaces { get; init; }
    public List<string>? HardForbiddenSurfaces { get; init; }
    public List<string>? RequiredControls { get; init; }
    public ConciergePostureTaxonomyDocument? PostureTaxonomy { get; init; }
    public List<string>? ForbiddenClaims { get; init; }
    public List<string>? ReceiptFields { get; init; }
}

internal sealed class ConciergeFlowPostureDocument
{
    public string? WidgetSurfacePosture { get; init; }
    public string? FixedRouteTarget { get; init; }
    public List<string>? FallbackRouteTargets { get; init; }
    public List<string>? RecoveryRouteTargets { get; init; }
    public List<string>? CopyRequirements { get; init; }
}

internal sealed class ConciergePostureTaxonomyDocument
{
    public string? Fixed { get; init; }
    public string? Preview { get; init; }
    public string? Fallback { get; init; }
    public string? Recovery { get; init; }
}
