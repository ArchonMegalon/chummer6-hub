using System.Text.Json;
using Chummer.Contracts.Receipts;
using Chummer.Hub.Registry.Contracts.InstallLinking;
using Chummer.Run.Api.Services.InstallLinking;

namespace Chummer.Run.Api.Services;

public sealed class NexusPanContinuityService
{
    private static readonly IReadOnlyList<NexusPanReceipt> Receipts =
    [
        new(
            ReceiptId: "nexus_claimed_install_posture",
            Topic: "Claimed install posture",
            Summary: "Shows how claimed installs stay tied to Chummer account truth instead of drifting into screenshots or loose docs.",
            Route: "/play/continuity/history/nexus_claimed_install_posture.json",
            Status: "live",
            Envelope: ReceiptEnvelopeFactory.Runtime(
                receiptKind: "nexus_pan",
                ownerScope: "play.nexus_pan",
                exposureClass: ReceiptExposureClasses.PublicSafe,
                lifecycleState: ReceiptLifecycleStates.Published,
                evidenceRef: "nexus_claimed_install_posture",
                reviewState: "live")),
        new(
            ReceiptId: "nexus_reconnect_handoff",
            Topic: "Reconnect handoff",
            Summary: "Names the next-safe-action handoff when mobile continuity and browser return paths need to survive device drift.",
            Route: "/play/continuity/history/nexus_reconnect_handoff.json",
            Status: "live",
            Envelope: ReceiptEnvelopeFactory.Runtime(
                receiptKind: "nexus_pan",
                ownerScope: "play.nexus_pan",
                exposureClass: ReceiptExposureClasses.PublicSafe,
                lifecycleState: ReceiptLifecycleStates.Published,
                evidenceRef: "nexus_reconnect_handoff",
                reviewState: "live")),
        new(
            ReceiptId: "nexus_runboard_boundary",
            Topic: "Runboard continuity boundary",
            Summary: "Keeps the public lane honest about what it previews and what still belongs on signed-in workspace rails.",
            Route: "/play/continuity/history/nexus_runboard_boundary.json",
            Status: "live",
            Envelope: ReceiptEnvelopeFactory.Runtime(
                receiptKind: "nexus_pan",
                ownerScope: "play.nexus_pan",
                exposureClass: ReceiptExposureClasses.PublicSafe,
                lifecycleState: ReceiptLifecycleStates.Published,
                evidenceRef: "nexus_runboard_boundary",
                reviewState: "live"))
    ];

    private readonly InstallLinkingStore _installLinkingStore;

    public NexusPanContinuityService(InstallLinkingStore installLinkingStore)
    {
        _installLinkingStore = installLinkingStore;
    }

    public IReadOnlyList<NexusPanReceipt> ListReceipts() => Receipts;

    public NexusPanReceipt GetReceipt(string receiptId)
        => Receipts.FirstOrDefault(item => string.Equals(item.ReceiptId, receiptId?.Trim(), StringComparison.OrdinalIgnoreCase))
            ?? throw new KeyNotFoundException($"Unknown NEXUS-PAN receipt '{receiptId}'.");

    public NexusPanPublicSummary BuildPublicSummary()
    {
        lock (_installLinkingStore.Gate)
        {
            DateTimeOffset now = DateTimeOffset.UtcNow;
            ClaimedInstallationDto[] activeInstallations = _installLinkingStore.InstallationsById.Values
                .Where(item => string.Equals(item.Status, ClaimedInstallationStates.Active, StringComparison.OrdinalIgnoreCase))
                .OrderByDescending(static item => item.UpdatedAtUtc)
                .ToArray();
            InstallationGrantDto[] activeGrants = _installLinkingStore.GrantsById.Values
                .Where(item => string.Equals(item.Status, InstallationGrantStates.Active, StringComparison.OrdinalIgnoreCase))
                .Where(item => item.ExpiresAtUtc > now)
                .OrderByDescending(static item => item.IssuedAtUtc)
                .ToArray();
            InstallClaimTicketDto[] pendingTickets = _installLinkingStore.ClaimTicketsById.Values
                .Where(item => string.Equals(item.Status, InstallClaimTicketStates.Pending, StringComparison.OrdinalIgnoreCase))
                .Where(item => item.ExpiresAtUtc > now)
                .OrderByDescending(static item => item.CreatedAtUtc)
                .ToArray();
            InstallBrowserCallbackDto[] pendingCallbacks = _installLinkingStore.BrowserCallbacksById.Values
                .Where(item => string.Equals(item.Status, InstallBrowserCallbackStates.Pending, StringComparison.OrdinalIgnoreCase))
                .Where(item => item.ExpiresAtUtc > now)
                .OrderByDescending(static item => item.CreatedAtUtc)
                .ToArray();

            string[] platforms = activeInstallations
                .Select(item => string.IsNullOrWhiteSpace(item.Platform) ? "unknown" : item.Platform.Trim().ToLowerInvariant())
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .OrderBy(static item => item, StringComparer.OrdinalIgnoreCase)
                .Take(6)
                .ToArray();

            return new NexusPanPublicSummary(
                ActiveInstallationCount: activeInstallations.Length,
                ActiveGrantCount: activeGrants.Length,
                PendingClaimCount: pendingTickets.Length,
                PendingBrowserCallbackCount: pendingCallbacks.Length,
                PlatformLabels: platforms,
                LastUpdatedUtc: activeInstallations.FirstOrDefault()?.UpdatedAtUtc
                    ?? activeGrants.FirstOrDefault()?.IssuedAtUtc
                    ?? pendingTickets.FirstOrDefault()?.CreatedAtUtc
                    ?? pendingCallbacks.FirstOrDefault()?.CreatedAtUtc
                    ?? now);
        }
    }

    public string BuildIndexJson()
    {
        NexusPanPublicSummary summary = BuildPublicSummary();
        return JsonSerializer.Serialize(
            new
            {
                receipts = Receipts.Select(item => new
                {
                    item.ReceiptId,
                    item.Topic,
                    item.Summary,
                    item.Route,
                    item.Status
                }).ToArray(),
                summary = BuildSummaryPayload(summary),
                boundary = "Public continuity stays aggregate and preview-safe. Private device history, account detail, and workspace continuity stay on account paths.",
                generated_at_utc = DateTimeOffset.UtcNow
            },
            new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });
    }

    public string BuildReceiptJson(string receiptId)
    {
        NexusPanReceipt receipt = GetReceipt(receiptId);
        NexusPanPublicSummary summary = BuildPublicSummary();
        var payload = new
        {
            receipt.ReceiptId,
            receipt.Topic,
            receipt.Summary,
            receipt.Status,
            proof_kind = "continuity_public_safe_receipt",
            aggregate_posture = BuildSummaryPayload(summary),
            detail = BuildReceiptDetail(receipt.ReceiptId, summary),
            generated_at_utc = DateTimeOffset.UtcNow
        };

        return JsonSerializer.Serialize(payload, new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });
    }

    public string BuildMobilePwaJson()
    {
        NexusPanPublicSummary summary = BuildPublicSummary();
        var payload = new
        {
            mode = "nexus_pan_mobile_pwa",
            status = "live",
            summary = "Mobile and PWA continuity keeps claimed installs, reconnect posture, and next-safe-action rails visible without pretending the public lane is a private device console.",
            install_route = "/downloads",
            continuity_route = "/play/continuity",
            receipt_index_route = "/play/continuity/history",
            claimed_installations = summary.ActiveInstallationCount,
            active_grants = summary.ActiveGrantCount,
            pending_claims = summary.PendingClaimCount,
            pending_browser_callbacks = summary.PendingBrowserCallbackCount,
            platform_labels = summary.PlatformLabels,
            boundaries = new[]
            {
                "No private device history on the public route.",
                "No provider-owned continuity truth.",
                "Runboard continuity detail stays signed-in."
            },
            generated_at_utc = DateTimeOffset.UtcNow
        };

        return JsonSerializer.Serialize(payload, new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });
    }

    private static object BuildSummaryPayload(NexusPanPublicSummary summary)
        => new
        {
            active_installation_count = summary.ActiveInstallationCount,
            active_grant_count = summary.ActiveGrantCount,
            pending_claim_count = summary.PendingClaimCount,
            pending_browser_callback_count = summary.PendingBrowserCallbackCount,
            platform_labels = summary.PlatformLabels,
            last_updated_utc = summary.LastUpdatedUtc
        };

    private static object BuildReceiptDetail(string receiptId, NexusPanPublicSummary summary)
        => receiptId switch
        {
            "nexus_claimed_install_posture" => new
            {
                bounded_summary = "Claimed installs are real, account-linked, and countable on first-party storage.",
                continuity_factors = new[] { "claimed_installations", "active_grants", "platform_labels" },
                observed_counts = new
                {
                    summary.ActiveInstallationCount,
                    summary.ActiveGrantCount
                }
            },
            "nexus_reconnect_handoff" => new
            {
                bounded_summary = "Reconnect posture stays visible through pending claim and browser callback rails instead of dissolving into generic help copy.",
                continuity_factors = new[] { "pending_claims", "pending_browser_callbacks", "downloads_boundary" },
                observed_counts = new
                {
                    summary.PendingClaimCount,
                    summary.PendingBrowserCallbackCount
                }
            },
            _ => new
            {
                bounded_summary = "Public continuity previews the job while signed-in workspace rails own the deeper runboard state.",
                continuity_factors = new[] { "public_preview", "signed_in_boundary", "runboard_continuity" },
                route_boundary = "/api/v1/community/me/workspaces/{workspaceId}/runboard-continuity"
            }
        };
}

public sealed record NexusPanReceipt(
    string ReceiptId,
    string Topic,
    string Summary,
    string Route,
    string Status,
    ReceiptEnvelope? Envelope = null);

public sealed record NexusPanPublicSummary(
    int ActiveInstallationCount,
    int ActiveGrantCount,
    int PendingClaimCount,
    int PendingBrowserCallbackCount,
    IReadOnlyList<string> PlatformLabels,
    DateTimeOffset LastUpdatedUtc);
