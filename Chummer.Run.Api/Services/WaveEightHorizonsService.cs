using System.Text.Json;
using Chummer.Campaign.Contracts;
using Chummer.Run.Api.Services.Community;
using Chummer.Run.Api.ViewModels;

namespace Chummer.Run.Api.Services;

public sealed class WaveEightHorizonsService
{
    private static readonly IReadOnlyList<WaveEightDocument> GhostwireDocuments =
    [
        new(
            "replay_timeline",
            "Replay timeline",
            "Receipt-backed replay packet that keeps the order of consequences, reports, and visible return-state changes explicit.",
            "/ghostwire/after-action/replay_timeline.md",
            "/ghostwire/after-action/replay_timeline.json",
            ["Receipt-backed replay", "Consequence order", "No transcript leak"]),
        new(
            "after_action_report",
            "After-action report",
            "Public-safe after-action packet showing what changed and what the next safe action is.",
            "/ghostwire/after-action/after_action_report.md",
            "/ghostwire/after-action/after_action_report.json",
            ["After-action packet", "Next safe action", "Public-safe recap"]),
        new(
            "consequence_chain",
            "Consequence chain",
            "How replay packets carry forward consequence and return-lane pressure without inventing unsupported fiction.",
            "/ghostwire/after-action/consequence_chain.md",
            "/ghostwire/after-action/consequence_chain.json",
            ["Consequence chain", "Carry-forward", "First-party receipts"])
    ];

    private readonly CommunityStore _communityStore;
    private readonly AnarchyPreviewService _anarchyPreview;

    public WaveEightHorizonsService(CommunityStore communityStore, AnarchyPreviewService anarchyPreview)
    {
        _communityStore = communityStore;
        _anarchyPreview = anarchyPreview;
    }

    public IReadOnlyList<WaveEightDocument> ListGhostwireDocuments() => GhostwireDocuments;

    public WaveEightDocument GetGhostwireDocument(string id)
        => GhostwireDocuments.FirstOrDefault(item => string.Equals(item.Id, id?.Trim(), StringComparison.OrdinalIgnoreCase))
            ?? throw new KeyNotFoundException($"Unknown GHOSTWIRE packet '{id}'.");

    public GhostwirePublicSummary BuildGhostwireSummary()
    {
        lock (_communityStore.Gate)
        {
            AftermathRecapPackageProjection[] packages = _communityStore.AftermathPackages
                .OrderByDescending(static item => item.GeneratedAtUtc)
                .Take(8)
                .ToArray();
            int afterActionCount = packages.Count(item => string.Equals(item.PackageKind, "after_action_report", StringComparison.OrdinalIgnoreCase));
            int replayCount = packages.Count(item => string.Equals(item.PackageKind, "replay_timeline", StringComparison.OrdinalIgnoreCase));
            int downtimeCount = packages.Count(item => string.Equals(item.PackageKind, "downtime_brief", StringComparison.OrdinalIgnoreCase));
            return new GhostwirePublicSummary(packages, afterActionCount, replayCount, downtimeCount);
        }
    }

    public string BuildGhostwireMarkdown(string id)
    {
        WaveEightDocument document = GetGhostwireDocument(id);
        GhostwirePublicSummary summary = BuildGhostwireSummary();
        List<string> lines =
        [
            $"# {document.Label}",
            string.Empty,
            document.Summary,
            string.Empty,
            "## Current public-safe posture",
            string.Empty,
            $"- Total aftermath packets on record: {summary.Packages.Count}",
            $"- After-action reports: {summary.AfterActionCount}",
            $"- Replay timelines: {summary.ReplayCount}",
            $"- Downtime briefs: {summary.DowntimeCount}",
            string.Empty,
            "## Boundary",
            string.Empty,
            BuildGhostwireBoundary(id),
            string.Empty
        ];

        if (summary.Packages.Count > 0)
        {
            lines.Add("## Current packet sample");
            lines.Add(string.Empty);
            lines.AddRange(summary.Packages.Take(4).Select(item => $"- {item.Title}: {item.PackageKind} | {item.Summary}"));
            lines.Add(string.Empty);
        }

        lines.Add($"JSON route: {document.JsonRoute}");
        return string.Join('\n', lines) + "\n";
    }

    public string BuildGhostwireJson(string id)
    {
        WaveEightDocument document = GetGhostwireDocument(id);
        GhostwirePublicSummary summary = BuildGhostwireSummary();
        object payload = new
        {
            document.Id,
            document.Label,
            document.Summary,
            status = "live",
            counts = new
            {
                packages = summary.Packages.Count,
                summary.AfterActionCount,
                summary.ReplayCount,
                summary.DowntimeCount
            },
            packets = summary.Packages.Select(item => new
            {
                item.PackageId,
                item.Title,
                item.PackageKind,
                item.Summary,
                item.EvidenceLines,
                item.ProvenanceSummary,
                item.AuditSummary
            }).ToArray(),
            boundary = BuildGhostwireBoundary(id),
            generated_at_utc = DateTimeOffset.UtcNow
        };

        return JsonSerializer.Serialize(payload, new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });
    }

    public string BuildAnarchyExportJson() => _anarchyPreview.BuildExportJson();

    public string BuildAnarchyExplainJson()
    {
        AnarchyExplainReceiptViewModel receipt = _anarchyPreview.BuildExplainReceipt();
        return JsonSerializer.Serialize(
            new
            {
                receipt.ReceiptId,
                receipt.SourceReceiptId,
                receipt.RulesetId,
                receipt.Status,
                receipt.ProvenanceNotes,
                receipt.CreatedAtUtc,
                state = "shipped_mvp",
                boundary = "Dedicated ruleset lane only. No sourcebook-text-complete claim and no dense-builder parity claim."
            },
            new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });
    }

    public string BuildFoundryParkedJson()
        => JsonSerializer.Serialize(
            new
            {
                horizon_id = "foundry_handoff",
                route = "/exports/foundry",
                state = "honestly_parked",
                status = "parked",
                reason = "Governed Foundry handoff is intentionally parked until first-party export truth, map metadata transport, and moderation-safe packet authority are proven together.",
                non_claims = new[]
                {
                    "No shipped public Foundry packet lane is claimed.",
                    "No public map authority is claimed.",
                    "No third-party VTT becomes Chummer truth."
                },
                generated_at_utc = DateTimeOffset.UtcNow
            },
            new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });

    private static string BuildGhostwireBoundary(string id)
        => id switch
        {
            "replay_timeline" => "Replay stays receipt-backed and public-safe. It does not expose private transcript detail or retrospective invention.",
            "after_action_report" => "After-action packets can summarize what changed and what comes next, but private table notes stay signed-in.",
            _ => "Consequence carry-forward stays bounded to first-party package truth instead of speculative narrative reconstruction."
        };
}

public sealed record WaveEightDocument(
    string Id,
    string Label,
    string Summary,
    string MarkdownRoute,
    string JsonRoute,
    IReadOnlyList<string> Highlights);

public sealed record GhostwirePublicSummary(
    IReadOnlyList<AftermathRecapPackageProjection> Packages,
    int AfterActionCount,
    int ReplayCount,
    int DowntimeCount);
