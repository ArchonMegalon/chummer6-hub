using System.Text.Json;
using System.Text.Json.Nodes;
using Chummer.Run.Api.Services.Community;
using Microsoft.Extensions.Configuration;

namespace Chummer.Run.Api.Services;

public sealed class MediaArtifactHorizonsService
{
    private const string DefaultMatterportTourHref = "https://my.matterport.com/show/?m=ax2JhiPGk5P";
    private const string DefaultFactoryMatterportTourHref = "https://my.matterport.com/show/?m=ax2JhiPGk5P&play=1";
    private const string DefaultThreeDvVistaTourHref = "https://www.3dvista.com/samples/new_york_loft.html";
    private const string DefaultRunsiteTourHref = DefaultMatterportTourHref;
    private const string DefaultRunsiteTourLabel = "3D Tour";
    private const string DefaultRunsiteTourActionLabel = "Open 3D Tour";
    private const string DefaultPropertyquarryTourHref = DefaultMatterportTourHref;
    private const string DefaultPropertyquarryTourLabel = "3D Tour";
    private const string DefaultPropertyquarryTourActionLabel = "Open 3D Tour";
    private static readonly IReadOnlyDictionary<string, SpatialTourStyleDefaults> DefaultSpatialTourStyles =
        new Dictionary<string, SpatialTourStyleDefaults>(StringComparer.OrdinalIgnoreCase)
        {
            ["ResearchLab"] = new(
                DisplayStyle: "Research Lab",
                PreferredProvider: "matterport",
                MatterportHref: DefaultMatterportTourHref,
                ThreeDvVistaHref: DefaultThreeDvVistaTourHref),
            ["Factory"] = new(
                DisplayStyle: "Factory",
                PreferredProvider: "matterport",
                MatterportHref: DefaultFactoryMatterportTourHref,
                ThreeDvVistaHref: DefaultThreeDvVistaTourHref),
            ["OfficeBuilding"] = new(
                DisplayStyle: "Office Building",
                PreferredProvider: "3dvista",
                MatterportHref: DefaultMatterportTourHref,
                ThreeDvVistaHref: DefaultThreeDvVistaTourHref)
        };
    private static readonly IReadOnlyDictionary<string, MediaArtifactSurfaceDefinition> SurfaceDefinitions =
        new Dictionary<string, MediaArtifactSurfaceDefinition>(StringComparer.OrdinalIgnoreCase)
        {
            ["jackpoint"] = new("jackpoint", "jackpoint-briefing-video"),
            ["origin-dossier"] = new("origin-dossier", "origin-dossier-media"),
            ["propertyquarry"] = new("propertyquarry", "propertyquarry-tour"),
            ["runbook-press"] = new("runbook-press", "runbook-export"),
            ["runsite"] = new("runsite", "runsite-tour")
        };

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
            TourHref: "/jackpoint/briefings/emerald-sprawl-briefing/video",
            TourLabel: "Briefing Video",
            TourOpenInNewTab: false,
            TourActionHref: "/jackpoint/briefings/emerald-sprawl-briefing/video",
            TourActionLabel: "Open Briefing Video",
            TourActionOpenInNewTab: false,
            DispatchTargetHref: "/media/horizons/jackpoint-90s-deepdive.mp4"),
        new(
            "dockyard-contact-dossier",
            "Dockyard contact dossier",
            "Short dossier card for a contact lane with bounded trust notes and follow-up hooks.",
            "/jackpoint/briefings/dockyard-contact-dossier.md",
            "/jackpoint/briefings/dockyard-contact-dossier.json",
            ["Dossier card", "Player-safe contact notes", "Follow-up hook"],
            "Dossier",
            TourHref: "/jackpoint/briefings/dockyard-contact-dossier/video",
            TourLabel: "Briefing Video",
            TourOpenInNewTab: false,
            TourActionHref: "/jackpoint/briefings/dockyard-contact-dossier/video",
            TourActionLabel: "Open Briefing Video",
            TourActionOpenInNewTab: false,
            DispatchTargetHref: "/media/horizons/jackpoint-90s-deepdive.mp4")
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
            TourHref: "/runbook/primers/new-runner-primer/export",
            TourLabel: "Primer Export",
            TourOpenInNewTab: false,
            TourActionHref: "/runbook/primers/new-runner-primer/export",
            TourActionLabel: "Export Primer",
            TourActionOpenInNewTab: false,
            DispatchTargetHref: "/media/horizons/runbook-press-90s-deepdive.mp4"),
        new(
            "gm-first-night-primer",
            "GM first-night primer",
            "GM-first packet for table-open sequencing, consequences, and next-screen posture.",
            "/runbook/primers/gm-first-night-primer.md",
            "/runbook/primers/gm-first-night-primer.json",
            ["Table-open sequence", "Consequence sweep", "Next-screen posture"],
            "Primer",
            TourHref: "/runbook/primers/gm-first-night-primer/export",
            TourLabel: "Primer Export",
            TourOpenInNewTab: false,
            TourActionHref: "/runbook/primers/gm-first-night-primer/export",
            TourActionLabel: "Export Primer",
            TourActionOpenInNewTab: false,
            DispatchTargetHref: "/media/horizons/runbook-press-90s-deepdive.mp4")
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
        bool useBuiltInRunsiteStyleDefaults = string.Equals(resolvedRunsiteTourHref, DefaultRunsiteTourHref, StringComparison.Ordinal);
        string resolvedPropertyquarryTourHref = ResolvePropertyquarryTourHref(configuration);
        string resolvedPropertyquarryTourLabel = ResolvePropertyquarryTourLabel(configuration);
        string resolvedPropertyquarryTourActionLabel = ResolvePropertyquarryTourActionLabel(configuration, resolvedPropertyquarryTourLabel);
        bool useBuiltInPropertyquarryStyleDefaults = string.Equals(resolvedPropertyquarryTourHref, DefaultPropertyquarryTourHref, StringComparison.Ordinal);

        _runsitePacks = BaseRunsitePacks
            .Select(item =>
            {
                SpatialTourResolution tour = ResolveSpatialTour(
                    configuration,
                    item.Style,
                    resolvedRunsiteTourHref,
                    resolvedRunsiteTourLabel,
                    resolvedRunsiteTourActionLabel,
                    useBuiltInRunsiteStyleDefaults);
                return item with
                {
                    TourLabel = tour.Label,
                    TourHref = $"/runsites/packs/{item.Id}/tour",
                    TourActionHref = $"/runsites/packs/{item.Id}/tour",
                    TourActionLabel = tour.ActionLabel,
                    TourActionOpenInNewTab = false,
                    TourOpenInNewTab = false,
                    DispatchTargetHref = tour.DispatchTargetHref
                };
            })
            .ToArray();

        _propertyquarryProperties = BasePropertyquarryProperties
            .Select(item =>
            {
                SpatialTourResolution tour = ResolveSpatialTour(
                    configuration,
                    item.Style,
                    resolvedPropertyquarryTourHref,
                    resolvedPropertyquarryTourLabel,
                    resolvedPropertyquarryTourActionLabel,
                    useBuiltInPropertyquarryStyleDefaults);
                return item with
                {
                    TourLabel = tour.Label,
                    TourHref = $"/propertyquarry/properties/{item.Id}/tour",
                    TourActionHref = $"/propertyquarry/properties/{item.Id}/tour",
                    TourActionLabel = tour.ActionLabel,
                    TourActionOpenInNewTab = false,
                    TourOpenInNewTab = false,
                    DispatchTargetHref = tour.DispatchTargetHref
                };
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
    public MediaArtifactSurfaceDefinition GetSurface(string horizonId)
    {
        string normalizedHorizonId = NormalizeHorizonId(horizonId);
        return SurfaceDefinitions.TryGetValue(normalizedHorizonId, out MediaArtifactSurfaceDefinition? surface)
            ? surface
            : throw new KeyNotFoundException($"Unknown media artifact horizon '{horizonId}'.");
    }

    public string BuildSourceRef(MediaArtifactSurfaceDefinition surface, string sourceId)
        => $"{surface.HorizonId}:{sourceId.Trim()}";

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
        => BuildDocumentJson(document, GetSurface(horizonId), boundary);

    public string BuildDocumentJson(MediaArtifactDocument document, MediaArtifactSurfaceDefinition surface, string boundary)
        => JsonSerializer.Serialize(
            new
            {
                horizon_id = surface.HorizonId,
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
                shared_artifacts = BuildSharedArtifactRoutes(surface),
                artifact_capability = BuildPublicArtifactCapability(surface, document),
                boundary,
                status = "live",
                generated_at_utc = DateTimeOffset.UtcNow
            },
            new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });

    private JsonObject? BuildSharedArtifactRoutes(MediaArtifactSurfaceDefinition surface)
    {
        if (_capabilities is null)
        {
            return null;
        }

        return _capabilities.BuildSharedArtifactSurfaceRoutesJsonNode(surface.HorizonId, surface.CapabilityId);
    }

    private JsonObject? BuildPublicArtifactCapability(MediaArtifactSurfaceDefinition surface, MediaArtifactDocument document)
    {
        if (_capabilities is null)
        {
            return null;
        }

        return _capabilities.BuildPublicCapabilityJsonNode(
            surface.HorizonId,
            surface.CapabilityId,
            $"{surface.HorizonId}:{document.Id}");
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

    private static SpatialTourResolution ResolveSpatialTour(
        IConfiguration? configuration,
        string? style,
        string fallbackHref,
        string fallbackLabel,
        string fallbackActionLabel,
        bool useBuiltInStyleDefaults)
    {
        string? styleToken = NormalizeStyleToken(style);
        if (string.IsNullOrWhiteSpace(styleToken))
        {
            return new SpatialTourResolution(fallbackHref, fallbackLabel, fallbackActionLabel);
        }

        SpatialTourStyleDefaults? defaults = null;
        if (useBuiltInStyleDefaults)
        {
            DefaultSpatialTourStyles.TryGetValue(styleToken, out defaults);
        }
        string? matterportHref = FirstConfiguredValue(
            configuration?[$"SpatialTours:Styles:{styleToken}:MatterportHref"],
            configuration?[$"SpatialTours:Styles:{styleToken}:MatterportViewerHref"],
            defaults?.MatterportHref);
        string? threeDvVistaHref = FirstConfiguredValue(
            configuration?[$"SpatialTours:Styles:{styleToken}:ThreeDvVistaHref"],
            configuration?[$"SpatialTours:Styles:{styleToken}:3DVistaHref"],
            configuration?[$"SpatialTours:Styles:{styleToken}:ThreeDvVistaViewerHref"],
            configuration?[$"SpatialTours:Styles:{styleToken}:3DVistaViewerHref"],
            defaults?.ThreeDvVistaHref);
        string? preferredProvider = FirstConfiguredValue(
            configuration?[$"SpatialTours:Styles:{styleToken}:PreferredProvider"],
            configuration?["SpatialTours:ProviderPreference"],
            defaults?.PreferredProvider);
        string dispatchTargetHref = ResolveSpatialTourDispatchTarget(preferredProvider, matterportHref, threeDvVistaHref) ?? fallbackHref;
        string label = FirstConfiguredValue(
            configuration?[$"SpatialTours:Styles:{styleToken}:Label"],
            configuration?[$"SpatialTours:Styles:{styleToken}:TourLabel"])
            ?? fallbackLabel;
        string actionLabel = ResolveSpatialTourActionLabel(
            configuredActionLabel: FirstConfiguredValue(
                configuration?[$"SpatialTours:Styles:{styleToken}:ActionLabel"],
                configuration?[$"SpatialTours:Styles:{styleToken}:OpenLabel"],
                configuration?[$"SpatialTours:Styles:{styleToken}:ButtonLabel"]),
            resolvedLabel: label,
            fallbackLabel: fallbackLabel,
            fallbackActionLabel: fallbackActionLabel);
        return new SpatialTourResolution(dispatchTargetHref, label, actionLabel);
    }

    private static string ResolveSpatialTourActionLabel(
        string? configuredActionLabel,
        string resolvedLabel,
        string fallbackLabel,
        string fallbackActionLabel)
    {
        if (!string.IsNullOrWhiteSpace(configuredActionLabel))
        {
            return configuredActionLabel.Trim();
        }

        return string.Equals(resolvedLabel, fallbackLabel, StringComparison.Ordinal)
            ? fallbackActionLabel
            : $"Open {resolvedLabel}";
    }

    private static string? ResolveSpatialTourDispatchTarget(string? preferredProvider, string? matterportHref, string? threeDvVistaHref)
    {
        string providerToken = NormalizeProviderToken(preferredProvider);
        return providerToken switch
        {
            "3dvista" or "threedvista" => FirstConfiguredValue(threeDvVistaHref, matterportHref),
            "matterport" => FirstConfiguredValue(matterportHref, threeDvVistaHref),
            _ => FirstConfiguredValue(matterportHref, threeDvVistaHref)
        };
    }

    private static string? NormalizeStyleToken(string? style)
        => string.IsNullOrWhiteSpace(style)
            ? null
            : new string(style.Where(char.IsLetterOrDigit).ToArray());

    private static string NormalizeProviderToken(string? provider)
        => string.IsNullOrWhiteSpace(provider)
            ? string.Empty
            : new string(provider.Where(char.IsLetterOrDigit).ToArray()).ToLowerInvariant();

    private static string? FirstConfiguredValue(params string?[] values)
        => values
            .Select(static item => string.IsNullOrWhiteSpace(item) ? null : item.Trim())
            .FirstOrDefault(static item => item is not null);
}

internal sealed record SpatialTourStyleDefaults(
    string DisplayStyle,
    string PreferredProvider,
    string? MatterportHref,
    string? ThreeDvVistaHref);

internal sealed record SpatialTourResolution(
    string DispatchTargetHref,
    string Label,
    string ActionLabel);

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
    bool TourActionOpenInNewTab = false,
    string? DispatchTargetHref = null);

public sealed record MediaArtifactSurfaceDefinition(
    string HorizonId,
    string CapabilityId);
