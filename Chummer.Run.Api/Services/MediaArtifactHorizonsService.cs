using System.Text.Json;
using Chummer.Run.Api.Services.Community;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services;

public sealed class MediaArtifactHorizonsService
{
    private const string DefaultRunsiteTourHref = "https://my.matterport.com/show/?m=ax2JhiPGk5P";
    private const string DefaultRunsiteTourLabel = "3D Tour";
    private const string DefaultRunsiteTourActionLabel = "Open 3D Tour";
    private const bool DefaultRunsiteTourOpenInNewTab = true;
    private const string DefaultPropertyquarryTourHref = "https://my.matterport.com/show/?m=ax2JhiPGk5P";
    private const string DefaultPropertyquarryTourLabel = "3D Tour";
    private const string DefaultPropertyquarryTourActionLabel = "Open 3D Tour";
    private const bool DefaultPropertyquarryTourOpenInNewTab = true;

    private static readonly IReadOnlyList<MediaArtifactDocument> JackpointBriefings =
    [
        new(
            "emerald-sprawl-briefing",
            "Emerald Sprawl briefing",
            "Player-safe mission brief with objective posture, pressure line, and provenance-safe dossier framing.",
            "/jackpoint/briefings/emerald-sprawl-briefing.md",
            "/jackpoint/briefings/emerald-sprawl-briefing.json",
            ["Objective pressure", "Contact posture", "No GM-private spoilers"],
            "Dossier",
            TourHref: "/media/horizons/jackpoint-90s-deepdive.mp4",
            TourLabel: "Briefing Video",
            TourActionHref: "/jackpoint/briefings/emerald-sprawl-briefing/video",
            TourActionLabel: "Open Briefing Video",
            TourActionOpenInNewTab: false),
        new(
            "dockyard-contact-dossier",
            "Dockyard contact dossier",
            "Short dossier card for a contact lane with bounded trust notes and follow-up hooks.",
            "/jackpoint/briefings/dockyard-contact-dossier.md",
            "/jackpoint/briefings/dockyard-contact-dossier.json",
            ["Dossier card", "Player-safe contact notes", "Follow-up hook"],
            "Dossier",
            TourHref: "/media/horizons/jackpoint-90s-deepdive.mp4",
            TourLabel: "Briefing Video",
            TourActionHref: "/jackpoint/briefings/dockyard-contact-dossier/video",
            TourActionLabel: "Open Briefing Video",
            TourActionOpenInNewTab: false)
    ];

    private static readonly IReadOnlyList<MediaArtifactDocument> BaseRunsitePacks =
    [
        new(
            "redmond-dockyard-pack",
            "Redmond dockyard pack",
            "Runsite packet with entry vectors, heat clocks, and exit posture kept in one handoff.",
            "/runsites/packs/redmond-dockyard-pack.md",
            "/runsites/packs/redmond-dockyard-pack.json",
            ["Entry vectors", "Threat clocks", "Exit posture"],
            "Research Lab"),
        new(
            "everett-switchyard-pack",
            "Everett switchyard pack",
            "Spatial-prep packet for switchyard pressure with player-safe lane separation.",
            "/runsites/packs/everett-switchyard-pack.md",
            "/runsites/packs/everett-switchyard-pack.json",
            ["Site card", "Pressure lane", "Player-safe split"],
            "Office Building")
    ];

    private static readonly IReadOnlyList<MediaArtifactDocument> BasePropertyquarryProperties =
    [
        new(
            "northbound-research-lab",
            "Northbound research lab",
            "Player-safe property packet for a high-security lab run.",
            "/propertyquarry/properties/northbound-research-lab.md",
            "/propertyquarry/properties/northbound-research-lab.json",
            ["High-security lab", "Containment lanes", "GM-safe environmental notes"],
            "Research Lab"),
        new(
            "shoreline-automation-factory",
            "Shoreline automation factory",
            "Player-safe property packet for automation plant prep and social dynamics.",
            "/propertyquarry/properties/shoreline-automation-factory.md",
            "/propertyquarry/properties/shoreline-automation-factory.json",
            ["Factory layout", "Security zones", "Player-safe continuity notes"],
            "Factory"),
        new(
            "eastriver-office-hub",
            "Eastriver office hub",
            "Player-safe property packet for executive office scenarios and controlled entrances.",
            "/propertyquarry/properties/eastriver-office-hub.md",
            "/propertyquarry/properties/eastriver-office-hub.json",
            ["Reception flow", "Office movement", "Authority handoff"],
            "Office Building")
    ];

    private static readonly IReadOnlyList<MediaArtifactDocument> RunbookPrimers =
    [
        new(
            "new-runner-primer",
            "New runner primer",
            "Human-readable first-session primer that points at ready rails, continuity, and support without dumping rules text.",
            "/runbook/primers/new-runner-primer.md",
            "/runbook/primers/new-runner-primer.json",
            ["First-session primer", "Ready rail", "Support rail"],
            "Primer",
            TourHref: "/media/horizons/runbook-press-90s-deepdive.mp4",
            TourLabel: "Primer Export",
            TourActionHref: "/runbook/primers/new-runner-primer/export",
            TourActionLabel: "Export Primer",
            TourActionOpenInNewTab: false),
        new(
            "gm-first-night-primer",
            "GM first-night primer",
            "GM-first packet for table-open sequencing, consequences, and next-screen posture.",
            "/runbook/primers/gm-first-night-primer.md",
            "/runbook/primers/gm-first-night-primer.json",
            ["Table-open sequence", "Consequence sweep", "Next-screen posture"],
            "Primer",
            TourHref: "/media/horizons/runbook-press-90s-deepdive.mp4",
            TourLabel: "Primer Export",
            TourActionHref: "/runbook/primers/gm-first-night-primer/export",
            TourActionLabel: "Export Primer",
            TourActionOpenInNewTab: false)
    ];

    private readonly IReadOnlyList<MediaArtifactDocument> _runsitePacks;
    private readonly IReadOnlyList<MediaArtifactDocument> _propertyquarryProperties;
    private readonly HorizonCapabilityService? _capabilities;

    public MediaArtifactHorizonsService(IConfiguration? configuration = null, HorizonCapabilityService? capabilities = null)
    {
        _capabilities = capabilities;

        string resolvedRunsiteTourHref = ResolveRunsiteTourHref(configuration);
        string resolvedRunsiteTourLabel = ResolveRunsiteTourLabel(configuration);
        string resolvedRunsiteTourActionLabel = ResolveRunsiteTourActionLabel(configuration, resolvedRunsiteTourLabel);
        bool resolvedRunsiteTourOpenInNewTab = ResolveRunsiteTourOpenInNewTab(configuration);
        string resolvedPropertyquarryTourHref = ResolvePropertyquarryTourHref(configuration);
        string resolvedPropertyquarryTourLabel = ResolvePropertyquarryTourLabel(configuration);
        string resolvedPropertyquarryTourActionLabel = ResolvePropertyquarryTourActionLabel(configuration, resolvedPropertyquarryTourLabel);
        bool resolvedPropertyquarryTourOpenInNewTab = ResolvePropertyquarryTourOpenInNewTab(configuration);

        _runsitePacks = BaseRunsitePacks
            .Select(item => item with
            {
                TourHref = resolvedRunsiteTourHref,
                TourLabel = resolvedRunsiteTourLabel,
                TourActionHref = $"/runsites/packs/{item.Id}/tour",
                TourActionLabel = resolvedRunsiteTourActionLabel,
                TourActionOpenInNewTab = false,
                TourOpenInNewTab = resolvedRunsiteTourOpenInNewTab
            })
            .ToArray();

        _propertyquarryProperties = BasePropertyquarryProperties
            .Select(item => item with
            {
                TourHref = resolvedPropertyquarryTourHref,
                TourLabel = resolvedPropertyquarryTourLabel,
                TourActionHref = $"/propertyquarry/properties/{item.Id}/tour",
                TourActionLabel = resolvedPropertyquarryTourActionLabel,
                TourActionOpenInNewTab = false,
                TourOpenInNewTab = resolvedPropertyquarryTourOpenInNewTab
            })
            .ToArray();
    }

    public IReadOnlyList<MediaArtifactDocument> ListJackpointBriefings() => JackpointBriefings;
    public IReadOnlyList<MediaArtifactDocument> ListRunsitePacks() => _runsitePacks;
    public IReadOnlyList<MediaArtifactDocument> ListRunbookPrimers() => RunbookPrimers;
    public IReadOnlyList<MediaArtifactDocument> ListPropertyquarryProperties() => _propertyquarryProperties;

    public MediaArtifactDocument GetJackpointBriefing(string id) => GetById(JackpointBriefings, id, "JACKPOINT briefing");
    public MediaArtifactDocument GetRunsitePack(string id) => GetById(_runsitePacks, id, "RUNSITE pack");
    public MediaArtifactDocument GetRunbookPrimer(string id) => GetById(RunbookPrimers, id, "RUNBOOK primer");
    public MediaArtifactDocument GetPropertyquarryProperty(string id) => GetById(_propertyquarryProperties, id, "PROPERTYQUARRY property");

    public string BuildDocumentMarkdown(MediaArtifactDocument document, string horizonLabel, string boundary)
    {
        var lines = new List<string>
        {
            $"# {document.Label}",
            string.Empty,
            $"Horizon: {horizonLabel}",
            string.Empty,
            document.Summary,
            string.Empty,
            "## Highlights",
            string.Empty
        };
        lines.AddRange(document.Highlights.Select(item => $"- {item}"));
        lines.Add(string.Empty);
        if (!string.IsNullOrWhiteSpace(document.Style))
        {
            lines.Add("## Style");
            lines.Add(string.Empty);
            lines.Add(document.Style);
            lines.Add(string.Empty);
        }

        if (!string.IsNullOrWhiteSpace(document.TourLabel) && !string.IsNullOrWhiteSpace(document.TourHref))
        {
            lines.Add("## 3D Tour");
            lines.Add(string.Empty);
            lines.Add($"{document.TourLabel}: {document.TourHref}");
            lines.Add(string.Empty);
        }

        lines.Add("## Boundary");
        lines.Add(string.Empty);
        lines.Add(boundary);
        lines.Add(string.Empty);
        lines.Add($"JSON route: {document.JsonRoute}");
        return string.Join('\n', lines) + "\n";
    }

    public string BuildDocumentJson(MediaArtifactDocument document, string horizonId, string boundary)
        => JsonSerializer.Serialize(
            new
            {
                horizon_id = horizonId,
                document.Id,
                document.Label,
                document.Summary,
                document.MarkdownRoute,
                document.JsonRoute,
                highlights = document.Highlights,
                style = document.Style,
                tour_href = document.TourHref,
                tour_label = document.TourLabel,
                tour_open_in_new_tab = document.TourOpenInNewTab,
                tour_action_href = document.TourActionHref,
                tour_action_label = document.TourActionLabel,
                tour_action_open_in_new_tab = document.TourActionOpenInNewTab,
                artifact_capability = BuildPublicArtifactCapability(horizonId, document),
                boundary,
                status = "live",
                generated_at_utc = DateTimeOffset.UtcNow
            },
            new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });

    private object? BuildPublicArtifactCapability(string horizonId, MediaArtifactDocument document)
    {
        if (_capabilities is null || !TryResolveArtifactKind(horizonId, out string normalizedHorizonId, out string artifactKind))
        {
            return null;
        }

        HorizonCapabilityHealthSnapshot health = _capabilities.GetHealth(normalizedHorizonId, artifactKind, publicSafe: true);
        return new
        {
            horizon_id = health.HorizonId,
            capability_id = health.CapabilityId,
            artifact_kind = health.ArtifactKind,
            public_label = health.PublicLabel,
            capability_slot = health.CapabilitySlot,
            status = health.Status,
            request_supported = string.Equals(health.Status, "available", StringComparison.OrdinalIgnoreCase),
            requires_authentication = health.RequiresAuthentication,
            public_visible = health.PublicVisible,
            source_ref = $"{health.HorizonId}:{document.Id}",
            visibility = "public_safe"
        };
    }

    private static bool TryResolveArtifactKind(string horizonId, out string normalizedHorizonId, out string artifactKind)
    {
        normalizedHorizonId = NormalizeHorizonId(horizonId);
        artifactKind = normalizedHorizonId switch
        {
            "propertyquarry" => "tour",
            "jackpoint" => "briefing_video",
            "runbook-press" => "document_export",
            "runsite" => "tour",
            _ => string.Empty
        };
        return !string.IsNullOrWhiteSpace(artifactKind);
    }

    private static string NormalizeHorizonId(string horizonId)
        => string.Equals(horizonId, "runbook_press", StringComparison.OrdinalIgnoreCase)
            ? "runbook-press"
            : horizonId.Trim();

    private static MediaArtifactDocument GetById(IReadOnlyList<MediaArtifactDocument> documents, string id, string label)
        => documents.FirstOrDefault(item => string.Equals(item.Id, id?.Trim(), StringComparison.OrdinalIgnoreCase))
            ?? throw new KeyNotFoundException($"Unknown {label} '{id}'.");

    private static string ResolveRunsiteTourHref(IConfiguration? configuration)
        => FirstConfiguredValue(
            configuration?["RunsiteTour:Href"],
            configuration?["RunsiteTour:SourceHref"])
            ?? DefaultRunsiteTourHref;

    private static string ResolveRunsiteTourLabel(IConfiguration? configuration)
        => FirstConfiguredValue(
            configuration?["RunsiteTour:Label"],
            configuration?["RunsiteTour:SourceLabel"])
            ?? DefaultRunsiteTourLabel;

    private static string ResolveRunsiteTourActionLabel(IConfiguration? configuration, string fallbackLabel)
    {
        string? configuredActionLabel = FirstConfiguredValue(
            configuration?["RunsiteTour:ActionLabel"],
            configuration?["RunsiteTour:OpenLabel"],
            configuration?["RunsiteTour:ButtonLabel"]);
        return configuredActionLabel ?? $"Open {fallbackLabel}";
    }

    private static string ResolvePropertyquarryTourHref(IConfiguration? configuration)
        => FirstConfiguredValue(
            configuration?["PropertyquarryTour:Href"],
            configuration?["PropertyquarryTour:SourceHref"])
            ?? DefaultPropertyquarryTourHref;

    private static string ResolvePropertyquarryTourLabel(IConfiguration? configuration)
        => FirstConfiguredValue(
            configuration?["PropertyquarryTour:Label"],
            configuration?["PropertyquarryTour:SourceLabel"])
            ?? DefaultPropertyquarryTourLabel;

    private static string ResolvePropertyquarryTourActionLabel(IConfiguration? configuration, string fallbackLabel)
    {
        string? configuredActionLabel = FirstConfiguredValue(
            configuration?["PropertyquarryTour:ActionLabel"],
            configuration?["PropertyquarryTour:OpenLabel"],
            configuration?["PropertyquarryTour:ButtonLabel"]);
        return configuredActionLabel ?? $"Open {fallbackLabel}";
    }

    private static bool ResolvePropertyquarryTourOpenInNewTab(IConfiguration? configuration)
        => bool.TryParse(FirstConfiguredValue(
                configuration?["PropertyquarryTour:OpenInNewTab"],
                configuration?["PropertyquarryTour:SourceOpenInNewTab"]),
            out bool openInNewTab)
            ? openInNewTab
            : DefaultPropertyquarryTourOpenInNewTab;

    private static bool ResolveRunsiteTourOpenInNewTab(IConfiguration? configuration)
        => bool.TryParse(FirstConfiguredValue(
                configuration?["RunsiteTour:OpenInNewTab"],
                configuration?["RunsiteTour:SourceOpenInNewTab"]),
            out bool openInNewTab)
            ? openInNewTab
            : DefaultRunsiteTourOpenInNewTab;

    private static string? FirstConfiguredValue(params string?[] values)
        => values
            .Select(static item => string.IsNullOrWhiteSpace(item) ? null : item.Trim())
            .FirstOrDefault(static item => item is not null);
}

public sealed record MediaArtifactDocument(
    string Id,
    string Label,
    string Summary,
    string MarkdownRoute,
    string JsonRoute,
    IReadOnlyList<string> Highlights,
    string? Style = null,
    string? TourHref = null,
    string? TourLabel = null,
    bool TourOpenInNewTab = true,
    string? TourActionHref = null,
    string? TourActionLabel = null,
    bool TourActionOpenInNewTab = false);
