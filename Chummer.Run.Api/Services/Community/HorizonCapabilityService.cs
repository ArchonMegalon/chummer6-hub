using System.Text.Json.Nodes;
using Chummer.Run.Api.ViewModels;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services.Community;

public sealed class HorizonCapabilityService
{
    private static readonly HorizonCapabilityDefinition[] BuiltInCapabilities =
    [
        new(
            HorizonId: "runsite",
            CapabilityId: "runsite-tour",
            ArtifactKind: "tour",
            PublicLabel: "3D Tour",
            CapabilitySlot: "explorable_location",
            InternalProviderLane: "Crezlo Tours / 3DVista / Matterport",
            FreeWeeklyLimit: 1,
            SupporterWeeklyLimit: 10,
            RequiresAuthentication: true,
            PublicVisible: true,
            EnabledByDefault: true,
            CostClass: "medium"),
        new(
            HorizonId: "runsite",
            CapabilityId: "runsite-map",
            ArtifactKind: "map",
            PublicLabel: "Route Map",
            CapabilitySlot: "location_visualization",
            InternalProviderLane: "AvoMap",
            FreeWeeklyLimit: 1,
            SupporterWeeklyLimit: 10,
            RequiresAuthentication: true,
            PublicVisible: true,
            EnabledByDefault: false,
            CostClass: "low"),
        new(
            HorizonId: "propertyquarry",
            CapabilityId: "propertyquarry-tour",
            ArtifactKind: "tour",
            PublicLabel: "3D Tour",
            CapabilitySlot: "explorable_location",
            InternalProviderLane: "Crezlo Tours / 3DVista / Matterport",
            FreeWeeklyLimit: 1,
            SupporterWeeklyLimit: 10,
            RequiresAuthentication: true,
            PublicVisible: true,
            EnabledByDefault: true,
            CostClass: "medium"),
        new(
            HorizonId: "jackpoint",
            CapabilityId: "jackpoint-briefing-video",
            ArtifactKind: "briefing_video",
            PublicLabel: "Briefing Video",
            CapabilitySlot: "presenter_video",
            InternalProviderLane: "vidBoard",
            FreeWeeklyLimit: 0,
            SupporterWeeklyLimit: 2,
            RequiresAuthentication: true,
            PublicVisible: false,
            EnabledByDefault: false,
            CostClass: "medium"),
        new(
            HorizonId: "runbook-press",
            CapabilityId: "runbook-export",
            ArtifactKind: "document_export",
            PublicLabel: "Formatted Export",
            CapabilitySlot: "document_render",
            InternalProviderLane: "Subscribr.ai / First Book ai / MarkupGo / Documentation.AI",
            FreeWeeklyLimit: 0,
            SupporterWeeklyLimit: 2,
            RequiresAuthentication: true,
            PublicVisible: false,
            EnabledByDefault: false,
            CostClass: "medium"),
        new(
            HorizonId: "karma-forge",
            CapabilityId: "karma-forge-discovery",
            ArtifactKind: "discovery_packet",
            PublicLabel: "Discovery Packet",
            CapabilitySlot: "demand_validation",
            InternalProviderLane: "Icanpreneur / Deftform / MetaSurvey",
            FreeWeeklyLimit: 0,
            SupporterWeeklyLimit: 3,
            RequiresAuthentication: true,
            PublicVisible: false,
            EnabledByDefault: false,
            CostClass: "low"),
        new(
            HorizonId: "table-pulse",
            CapabilityId: "table-pulse-debrief",
            ArtifactKind: "debrief_packet",
            PublicLabel: "Debrief Packet",
            CapabilitySlot: "post_session_coaching",
            InternalProviderLane: "hedy.ai / Nonverbia",
            FreeWeeklyLimit: 0,
            SupporterWeeklyLimit: 2,
            RequiresAuthentication: true,
            PublicVisible: false,
            EnabledByDefault: false,
            CostClass: "medium"),
        new(
            HorizonId: "black-ledger",
            CapabilityId: "black-ledger-digest",
            ArtifactKind: "world_tick_digest",
            PublicLabel: "World Tick Digest",
            CapabilitySlot: "outbound_digest",
            InternalProviderLane: "Emailit / Signitic / vidBoard",
            FreeWeeklyLimit: 0,
            SupporterWeeklyLimit: 2,
            RequiresAuthentication: true,
            PublicVisible: false,
            EnabledByDefault: false,
            CostClass: "medium"),
        new(
            HorizonId: "black-ledger",
            CapabilityId: "black-ledger-newsroom",
            ArtifactKind: "newsroom_bulletin",
            PublicLabel: "Newsroom Bulletin",
            CapabilitySlot: "public_bulletin_media",
            InternalProviderLane: "First-party bulletin media",
            FreeWeeklyLimit: 0,
            SupporterWeeklyLimit: 0,
            RequiresAuthentication: false,
            PublicVisible: true,
            EnabledByDefault: true,
            CostClass: "medium",
            QuotaTracked: false),
        new(
            HorizonId: "black-ledger",
            CapabilityId: "black-ledger-faction-promo",
            ArtifactKind: "faction_promo",
            PublicLabel: "Faction Promo",
            CapabilitySlot: "public_bulletin_media",
            InternalProviderLane: "First-party faction promo media",
            FreeWeeklyLimit: 0,
            SupporterWeeklyLimit: 0,
            RequiresAuthentication: false,
            PublicVisible: true,
            EnabledByDefault: true,
            CostClass: "medium",
            QuotaTracked: false),
        new(
            HorizonId: "runner_passport",
            CapabilityId: "runner_passport-identity-network",
            ArtifactKind: "identity_network",
            PublicLabel: "Identity Network",
            CapabilitySlot: "public_identity_return",
            InternalProviderLane: "First-party runner continuity receipt",
            FreeWeeklyLimit: 0,
            SupporterWeeklyLimit: 0,
            RequiresAuthentication: false,
            PublicVisible: true,
            EnabledByDefault: true,
            CostClass: "low",
            QuotaTracked: false),
        new(
            HorizonId: "signal_deck",
            CapabilityId: "signal_deck-command-network",
            ArtifactKind: "command_network",
            PublicLabel: "Command Network",
            CapabilitySlot: "public_command_pressure",
            InternalProviderLane: "First-party command continuity receipt",
            FreeWeeklyLimit: 0,
            SupporterWeeklyLimit: 0,
            RequiresAuthentication: false,
            PublicVisible: true,
            EnabledByDefault: true,
            CostClass: "low",
            QuotaTracked: false),
        new(
            HorizonId: "living_world",
            CapabilityId: "living_world-watch-network",
            ArtifactKind: "watch_network",
            PublicLabel: "Watch Network",
            CapabilitySlot: "public_world_watch",
            InternalProviderLane: "First-party world watch receipt",
            FreeWeeklyLimit: 0,
            SupporterWeeklyLimit: 0,
            RequiresAuthentication: false,
            PublicVisible: true,
            EnabledByDefault: true,
            CostClass: "low",
            QuotaTracked: false),
        new(
            HorizonId: "community_hub",
            CapabilityId: "community_hub-open-run-network",
            ArtifactKind: "open_run_network",
            PublicLabel: "Open Run Network",
            CapabilitySlot: "public_open_run_board",
            InternalProviderLane: "First-party open-run receipt",
            FreeWeeklyLimit: 0,
            SupporterWeeklyLimit: 0,
            RequiresAuthentication: false,
            PublicVisible: true,
            EnabledByDefault: true,
            CostClass: "low",
            QuotaTracked: false),
        new(
            HorizonId: "creator_os",
            CapabilityId: "creator_os-publication-network",
            ArtifactKind: "publication_network",
            PublicLabel: "Publication Network",
            CapabilitySlot: "public_creator_discovery",
            InternalProviderLane: "First-party publication discovery receipt",
            FreeWeeklyLimit: 0,
            SupporterWeeklyLimit: 0,
            RequiresAuthentication: false,
            PublicVisible: true,
            EnabledByDefault: true,
            CostClass: "low",
            QuotaTracked: false),
        new(
            HorizonId: "origin-dossier",
            CapabilityId: "origin-dossier-premium-authoring",
            ArtifactKind: "premium_authoring_credit",
            PublicLabel: "Premium Authoring Credit",
            CapabilitySlot: "guided_origin_authoring",
            InternalProviderLane: "First Book ai / Chummer OriginBookEngine",
            FreeWeeklyLimit: 1,
            SupporterWeeklyLimit: 2,
            RequiresAuthentication: true,
            PublicVisible: false,
            EnabledByDefault: true,
            CostClass: "high",
            QuotaAuthority: "myfirstbook_monthly",
            AllowanceWindowKind: "monthly",
            EntitlementBasisSuffix: "monthly_origin_authoring_allowance"),
        new(
            HorizonId: "origin-dossier",
            CapabilityId: "origin-dossier-media",
            ArtifactKind: "dossier_media",
            PublicLabel: "Dossier Media",
            CapabilitySlot: "approved_origin_media",
            InternalProviderLane: "Magicfit / Subscribr.ai / First Book ai / MarkupGo / vidBoard / Soundmadeseen",
            FreeWeeklyLimit: 0,
            SupporterWeeklyLimit: 2,
            RequiresAuthentication: true,
            PublicVisible: false,
            EnabledByDefault: false,
            CostClass: "high")
    ];

    private readonly IConfiguration _configuration;

    public HorizonCapabilityService(IConfiguration configuration)
    {
        _configuration = configuration;
    }

    public IReadOnlyList<HorizonCapabilityDefinition> ListCapabilities()
        => BuiltInCapabilities
            .Select(ApplyConfiguration)
            .ToArray();

    public HorizonCapabilityDefinition GetCapability(string horizonId, string artifactKindOrCapabilityId)
    {
        string normalizedHorizonId = Clean(horizonId);
        string normalizedSelector = Clean(artifactKindOrCapabilityId);
        return ListCapabilities().FirstOrDefault(item =>
                string.Equals(item.HorizonId, normalizedHorizonId, StringComparison.OrdinalIgnoreCase)
                && (string.Equals(item.ArtifactKind, normalizedSelector, StringComparison.OrdinalIgnoreCase)
                    || string.Equals(item.CapabilityId, normalizedSelector, StringComparison.OrdinalIgnoreCase)))
            ?? throw new KeyNotFoundException($"Unknown horizon capability '{horizonId}/{artifactKindOrCapabilityId}'.");
    }

    public HorizonArtifactSurfaceDefinition GetSurface(string horizonId, string artifactKindOrCapabilityId)
    {
        HorizonCapabilityDefinition capability = GetCapability(horizonId, artifactKindOrCapabilityId);
        return new HorizonArtifactSurfaceDefinition(capability.HorizonId, capability.CapabilityId);
    }

    public string BuildSourceRef(string horizonId, string artifactKindOrCapabilityId, string sourceId)
        => BuildSourceRef(GetSurface(horizonId, artifactKindOrCapabilityId), sourceId);

    public string BuildSourceRef(HorizonArtifactSurfaceDefinition surface, string sourceId)
    {
        string normalizedSourceId = Clean(sourceId);
        return string.IsNullOrWhiteSpace(normalizedSourceId)
            ? surface.HorizonId
            : $"{surface.HorizonId}:{normalizedSourceId}";
    }

    public HorizonCapabilityHealthSnapshot GetHealth(string horizonId, string artifactKindOrCapabilityId, bool publicSafe = false)
    {
        HorizonCapabilityDefinition capability = GetCapability(horizonId, artifactKindOrCapabilityId);
        string status = capability.Enabled ? "available" : "disabled";
        return new HorizonCapabilityHealthSnapshot(
            capability.HorizonId,
            capability.CapabilityId,
            capability.ArtifactKind,
            capability.PublicLabel,
            capability.CapabilitySlot,
            status,
            publicSafe ? null : capability.InternalProviderLane,
            capability.RequiresAuthentication,
            capability.PublicVisible,
            capability.FreeWeeklyLimit,
            capability.SupporterWeeklyLimit,
            capability.CostClass,
            capability.QuotaTracked,
            capability.AllowanceWindowKind);
    }

    public PublicHorizonCapabilityViewModel BuildPublicCapabilityViewModel(
        string horizonId,
        string artifactKindOrCapabilityId,
        string sourceRef,
        string visibility = "public_safe")
    {
        HorizonCapabilityHealthSnapshot health = GetHealth(horizonId, artifactKindOrCapabilityId, publicSafe: true);
        return new PublicHorizonCapabilityViewModel(
            HorizonId: health.HorizonId,
            CapabilityId: health.CapabilityId,
            ArtifactKind: health.ArtifactKind,
            PublicLabel: health.PublicLabel,
            CapabilitySlot: health.CapabilitySlot,
            Status: health.Status,
            RequestSupported: string.Equals(health.Status, "available", StringComparison.OrdinalIgnoreCase),
            RequiresAuthentication: health.RequiresAuthentication,
            PublicVisible: health.PublicVisible,
            QuotaTracked: health.QuotaTracked,
            AllowanceWindowKind: health.AllowanceWindowKind,
            SourceRef: sourceRef,
            Visibility: visibility);
    }

    public JsonObject BuildPublicCapabilityJsonNode(
        string horizonId,
        string artifactKindOrCapabilityId,
        string sourceRef,
        string visibility = "public_safe")
    {
        PublicHorizonCapabilityViewModel capability = BuildPublicCapabilityViewModel(
            horizonId,
            artifactKindOrCapabilityId,
            sourceRef,
            visibility);
        return new JsonObject
        {
            ["horizon_id"] = capability.HorizonId,
            ["capability_id"] = capability.CapabilityId,
            ["artifact_kind"] = capability.ArtifactKind,
            ["public_label"] = capability.PublicLabel,
            ["capability_slot"] = capability.CapabilitySlot,
            ["status"] = capability.Status,
            ["request_supported"] = capability.RequestSupported,
            ["requires_authentication"] = capability.RequiresAuthentication,
            ["public_visible"] = capability.PublicVisible,
            ["quota_tracked"] = capability.QuotaTracked,
            ["allowance_window_kind"] = capability.AllowanceWindowKind,
            ["source_ref"] = capability.SourceRef,
            ["visibility"] = capability.Visibility
        };
    }

    public SharedArtifactSurfaceRoutesViewModel BuildSharedArtifactSurfaceRoutesViewModel(
        string horizonId,
        string artifactKindOrCapabilityId)
    {
        HorizonCapabilityDefinition capability = GetCapability(horizonId, artifactKindOrCapabilityId);
        string encodedHorizonId = Uri.EscapeDataString(capability.HorizonId);
        string encodedCapabilityId = Uri.EscapeDataString(capability.CapabilityId);
        bool publicReceiptEligible = capability.PublicVisible && !capability.RequiresAuthentication;
        return new SharedArtifactSurfaceRoutesViewModel(
            PublicCapabilityCatalogHref: "/api/v1/public/horizons/capabilities",
            PublicCapabilityHealthHref: capability.PublicVisible
                ? $"/api/v1/public/horizons/capabilities?horizonId={encodedHorizonId}&artifactKindOrCapabilityId={encodedCapabilityId}"
                : null,
            PublicRequestReceiptDetailHrefTemplate: publicReceiptEligible
                ? "/api/v1/public/horizons/artifact-requests/{requestId}"
                : null,
            SignedInCapabilityCatalogHref: capability.RequiresAuthentication
                ? $"/api/v1/horizons/capabilities/me?horizonId={encodedHorizonId}&artifactKindOrCapabilityId={encodedCapabilityId}"
                : null,
            SignedInQuotaCatalogHref: capability.RequiresAuthentication && capability.QuotaTracked
                ? $"/api/v1/horizons/quotas/me?horizonId={encodedHorizonId}&artifactKindOrCapabilityId={encodedCapabilityId}"
                : null,
            SignedInRequestCreateHref: capability.RequiresAuthentication || publicReceiptEligible
                ? "/api/v1/horizons/artifact-requests/me"
                : null,
            SignedInRequestReceiptHref: capability.RequiresAuthentication || publicReceiptEligible
                ? $"/api/v1/horizons/artifact-requests/me?horizonId={encodedHorizonId}&artifactKindOrCapabilityId={encodedCapabilityId}"
                : null,
            SignedInRequestReceiptDetailHrefTemplate: capability.RequiresAuthentication || publicReceiptEligible
                ? "/api/v1/horizons/artifact-requests/me/{requestId}"
                : null);
    }

    public JsonObject BuildSharedArtifactSurfaceRoutesJsonNode(string horizonId, string artifactKindOrCapabilityId)
    {
        SharedArtifactSurfaceRoutesViewModel routes = BuildSharedArtifactSurfaceRoutesViewModel(horizonId, artifactKindOrCapabilityId);
        return new JsonObject
        {
            ["public_capability_catalog_href"] = routes.PublicCapabilityCatalogHref,
            ["public_capability_health_href"] = routes.PublicCapabilityHealthHref,
            ["public_request_receipt_detail_href_template"] = routes.PublicRequestReceiptDetailHrefTemplate,
            ["signed_in_capability_catalog_href"] = routes.SignedInCapabilityCatalogHref,
            ["signed_in_quota_catalog_href"] = routes.SignedInQuotaCatalogHref,
            ["signed_in_request_create_href"] = routes.SignedInRequestCreateHref,
            ["signed_in_request_receipt_href"] = routes.SignedInRequestReceiptHref,
            ["signed_in_request_receipt_detail_href_template"] = routes.SignedInRequestReceiptDetailHrefTemplate
        };
    }

    private HorizonCapabilityDefinition ApplyConfiguration(HorizonCapabilityDefinition capability)
    {
        string prefix = $"HorizonCapabilities:{capability.HorizonId}:{capability.CapabilityId}";
        string envPrefix = $"CHUMMER_HORIZON_{NormalizeEnvToken(capability.HorizonId)}_CAPABILITY_{NormalizeEnvToken(capability.CapabilityId)}";
        bool enabled = ReadBool($"{prefix}:Enabled", $"{envPrefix}_ENABLED", capability.EnabledByDefault);
        int freeWeeklyLimit = ReadPositiveInt($"{prefix}:FreeWeeklyLimit", $"{envPrefix}_FREE_WEEKLY_LIMIT", capability.FreeWeeklyLimit);
        int supporterWeeklyLimit = ReadPositiveInt($"{prefix}:SupporterWeeklyLimit", $"{envPrefix}_SUPPORTER_WEEKLY_LIMIT", capability.SupporterWeeklyLimit);
        return capability with
        {
            Enabled = enabled,
            FreeWeeklyLimit = freeWeeklyLimit,
            SupporterWeeklyLimit = supporterWeeklyLimit
        };
    }

    private bool ReadBool(string configKey, string envKey, bool fallback)
        => bool.TryParse(_configuration[envKey] ?? _configuration[configKey], out bool configured)
            ? configured
            : fallback;

    private int ReadPositiveInt(string configKey, string envKey, int fallback)
        => int.TryParse(_configuration[envKey] ?? _configuration[configKey], out int configured) && configured >= 0
            ? configured
            : fallback;

    private static string Clean(string? value)
        => string.IsNullOrWhiteSpace(value) ? string.Empty : value.Trim();

    private static string NormalizeEnvToken(string value)
        => new(value.Select(static c => char.IsLetterOrDigit(c) ? char.ToUpperInvariant(c) : '_').ToArray());
}

public sealed record HorizonCapabilityDefinition(
    string HorizonId,
    string CapabilityId,
    string ArtifactKind,
    string PublicLabel,
    string CapabilitySlot,
    string InternalProviderLane,
    int FreeWeeklyLimit,
    int SupporterWeeklyLimit,
    bool RequiresAuthentication,
    bool PublicVisible,
    bool EnabledByDefault,
    string CostClass,
    bool Enabled = true,
    bool QuotaTracked = true,
    string QuotaAuthority = "supporter_weekly",
    string AllowanceWindowKind = "weekly",
    string EntitlementBasisSuffix = "weekly_allowance",
    string EntitlementScope = "account");

public sealed record HorizonArtifactSurfaceDefinition(
    string HorizonId,
    string CapabilityId);

public sealed record HorizonCapabilityHealthSnapshot(
    string HorizonId,
    string CapabilityId,
    string ArtifactKind,
    string PublicLabel,
    string CapabilitySlot,
    string Status,
    string? InternalProviderLane,
    bool RequiresAuthentication,
    bool PublicVisible,
    int FreeWeeklyLimit,
    int SupporterWeeklyLimit,
    string CostClass,
    bool QuotaTracked,
    string AllowanceWindowKind);
