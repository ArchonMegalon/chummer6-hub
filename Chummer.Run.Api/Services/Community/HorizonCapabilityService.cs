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
            InternalProviderLane: "MarkupGo / Documentation.AI",
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
            HorizonId: "origin-dossier",
            CapabilityId: "origin-dossier-media",
            ArtifactKind: "dossier_media",
            PublicLabel: "Dossier Media",
            CapabilitySlot: "approved_origin_media",
            InternalProviderLane: "First Book ai / MarkupGo / vidBoard / Soundmadeseen",
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
            capability.CostClass);
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
    bool Enabled = true);

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
    string CostClass);
