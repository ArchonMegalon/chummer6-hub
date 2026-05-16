using System.Text.Json;

namespace Chummer.Run.Api.Services;

public sealed class MediaArtifactHorizonsService
{
    private static readonly IReadOnlyList<MediaArtifactDocument> JackpointBriefings =
    [
        new(
            "emerald-sprawl-briefing",
            "Emerald Sprawl briefing",
            "Player-safe mission brief with objective posture, pressure line, and provenance-safe dossier framing.",
            "/jackpoint/briefings/emerald-sprawl-briefing.md",
            "/jackpoint/briefings/emerald-sprawl-briefing.json",
            ["Objective pressure", "Contact posture", "No GM-private spoilers"]),
        new(
            "dockyard-contact-dossier",
            "Dockyard contact dossier",
            "Short dossier card for a contact lane with bounded trust notes and follow-up hooks.",
            "/jackpoint/briefings/dockyard-contact-dossier.md",
            "/jackpoint/briefings/dockyard-contact-dossier.json",
            ["Dossier card", "Player-safe contact notes", "Follow-up hook"])
    ];

    private static readonly IReadOnlyList<MediaArtifactDocument> RunsitePacks =
    [
        new(
            "redmond-dockyard-pack",
            "Redmond dockyard pack",
            "Runsite packet with entry vectors, heat clocks, and exit posture kept in one handoff.",
            "/runsites/packs/redmond-dockyard-pack.md",
            "/runsites/packs/redmond-dockyard-pack.json",
            ["Entry vectors", "Threat clocks", "Exit posture"]),
        new(
            "everett-switchyard-pack",
            "Everett switchyard pack",
            "Spatial-prep packet for switchyard pressure with player-safe lane separation.",
            "/runsites/packs/everett-switchyard-pack.md",
            "/runsites/packs/everett-switchyard-pack.json",
            ["Site card", "Pressure lane", "Player-safe split"])
    ];

    private static readonly IReadOnlyList<MediaArtifactDocument> RunbookPrimers =
    [
        new(
            "new-runner-primer",
            "New runner primer",
            "Human-readable first-session primer that points at ready rails, continuity, and support without dumping rules text.",
            "/runbook/primers/new-runner-primer.md",
            "/runbook/primers/new-runner-primer.json",
            ["First-session primer", "Ready rail", "Support rail"]),
        new(
            "gm-first-night-primer",
            "GM first-night primer",
            "GM-first packet for table-open sequencing, consequences, and next-screen posture.",
            "/runbook/primers/gm-first-night-primer.md",
            "/runbook/primers/gm-first-night-primer.json",
            ["Table-open sequence", "Consequence sweep", "Next-screen posture"])
    ];

    public IReadOnlyList<MediaArtifactDocument> ListJackpointBriefings() => JackpointBriefings;
    public IReadOnlyList<MediaArtifactDocument> ListRunsitePacks() => RunsitePacks;
    public IReadOnlyList<MediaArtifactDocument> ListRunbookPrimers() => RunbookPrimers;

    public MediaArtifactDocument GetJackpointBriefing(string id) => GetById(JackpointBriefings, id, "JACKPOINT briefing");
    public MediaArtifactDocument GetRunsitePack(string id) => GetById(RunsitePacks, id, "RUNSITE pack");
    public MediaArtifactDocument GetRunbookPrimer(string id) => GetById(RunbookPrimers, id, "RUNBOOK primer");

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
                boundary,
                status = "live",
                generated_at_utc = DateTimeOffset.UtcNow
            },
            new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });

    private static MediaArtifactDocument GetById(IReadOnlyList<MediaArtifactDocument> documents, string id, string label)
        => documents.FirstOrDefault(item => string.Equals(item.Id, id?.Trim(), StringComparison.OrdinalIgnoreCase))
            ?? throw new KeyNotFoundException($"Unknown {label} '{id}'.");
}

public sealed record MediaArtifactDocument(
    string Id,
    string Label,
    string Summary,
    string MarkdownRoute,
    string JsonRoute,
    IReadOnlyList<string> Highlights);
