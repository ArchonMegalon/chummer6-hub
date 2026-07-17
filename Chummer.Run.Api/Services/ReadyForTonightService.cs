using System.Text.Json;

namespace Chummer.Run.Api.Services;

public sealed class ReadyForTonightService
{
    private static readonly IReadOnlyList<ReadyRoleVerdict> RoleVerdicts =
    [
        new(
            RoleId: "player",
            RoleLabel: "Player",
            Status: "warning",
            StatusLabel: "Ready with one blocker",
            Summary: "Starter runner packet is usable now, but the first session still expects a quick legality and gear check before dice hit the table.",
            BlockingReasons:
            [
                "Confirm one starter loadout that matches your table role.",
                "Carry the session file or mobile setup before you leave Downloads."
            ],
            ChangedSinceLastSession:
            [
                "Turn-0 loadouts now include a short legal-baseline checklist.",
                "The player file now names the next join and support steps clearly."
            ],
            FixNowActions:
            [
                new ReadyAction("Download player packet", "/ready/packet/player.md", "primary"),
                new ReadyAction("Open mage starter loadout", "/ready/loadout/mage.json", "secondary"),
                new ReadyAction("Open mobile setup", "/ready/handoff/mobile.json", "ghost")
            ],
            NextBestScreen: "/mobile",
            ProofReceipts:
            [
                "/ready/packet/player.json",
                "/ready/loadout/mage.json",
                "/ready/handoff/mobile.json"
            ]),
        new(
            RoleId: "gm",
            RoleLabel: "GM",
            Status: "warning",
            StatusLabel: "Prep packet ready",
            Summary: "The GM file, roster check, and export path are ready now, while the full deep workbench stays in the desktop app.",
            BlockingReasons:
            [
                "Confirm roster and opposition summary before opening the table.",
                "Export or print the prep file before session start."
            ],
            ChangedSinceLastSession:
            [
                "GM prep now includes a short preflight checklist and export path.",
                "Run file links stay clear instead of falling back to vague route text."
            ],
            FixNowActions:
            [
                new ReadyAction("Download GM packet", "/ready/packet/gm.md", "primary"),
                new ReadyAction("Download GM packet JSON", "/ready/packet/gm.json", "secondary"),
                new ReadyAction("Open support", "/help", "ghost")
            ],
            NextBestScreen: "/ledger/dispatches",
            ProofReceipts:
            [
                "/ready/packet/gm.json",
                "/ready/loadout/street-samurai.json"
            ]),
        new(
            RoleId: "organizer",
            RoleLabel: "Organizer",
            Status: "ready",
            StatusLabel: "Publishable public-run packet",
            Summary: "Safety, quickstart, and public-run setup stay limited and readable without exposing private account or campaign data.",
            BlockingReasons:
            [
                "None on the public-safe starter packet."
            ],
            ChangedSinceLastSession:
            [
                "Organizer file now points at participation and moderation follow-up clearly.",
                "The same Chummer file now carries the mobile setup path."
            ],
            FixNowActions:
            [
                new ReadyAction("Download organizer packet", "/ready/packet/organizer.md", "primary"),
                new ReadyAction("Open participate", "/participate", "secondary"),
                new ReadyAction("Open continuity", "/play/continuity", "ghost")
            ],
            NextBestScreen: "/participate",
            ProofReceipts:
            [
                "/ready/packet/organizer.json",
                "/ready/handoff/mobile.json"
            ])
    ];

    private static readonly IReadOnlyList<ReadyRoleKit> RoleKits =
    [
        new(
            KitId: "street-samurai",
            RoleLane: "Player",
            Label: "Street Samurai starter",
            Summary: "Combat-ready starter with ammo, armor, medkit, and a short legality checklist.",
            DownloadHref: "/ready/loadout/street-samurai.json",
            Highlights:
            [
                "Armor and medkit included",
                "One ammo and backup weapon reminder",
                "Session-start legality check"
            ]),
        new(
            KitId: "mage",
            RoleLane: "Player",
            Label: "Mage starter",
            Summary: "Awakened starter with focus, drain, and quick spell readiness cues for tonight.",
            DownloadHref: "/ready/loadout/mage.json",
            Highlights:
            [
                "Drain and focus reminder",
                "Spell visibility checklist",
                "Join/run next step stays attached"
            ]),
        new(
            KitId: "gm-quickstart",
            RoleLane: "GM",
            Label: "GM quickstart kit",
            Summary: "Roster, consequences, and packet export checklist for the fastest honest start.",
            DownloadHref: "/ready/loadout/gm-quickstart.json",
            Highlights:
            [
                "Roster completeness",
                "Consequence and reward sweep",
                "Export before the table starts"
            ])
    ];

    private static readonly IReadOnlyList<ReadyPacketAsset> PacketAssets =
    [
        new("player", "Player packet", "Printable player-safe session file with join, loadout, and support steps.", "/ready/packet/player.md", "/ready/packet/player.json"),
        new("gm", "GM packet", "Prep packet with roster, opposition, and export-safe session notes.", "/ready/packet/gm.md", "/ready/packet/gm.json"),
        new("organizer", "Organizer packet", "Public-run file with safety, publication, and moderation notes.", "/ready/packet/organizer.md", "/ready/packet/organizer.json")
    ];

    public IReadOnlyList<ReadyRoleVerdict> ListRoleVerdicts() => RoleVerdicts;

    public IReadOnlyList<ReadyRoleKit> ListRoleKits() => RoleKits;

    public IReadOnlyList<ReadyPacketAsset> ListPacketAssets() => PacketAssets;

    public ReadyRoleVerdict GetRoleVerdict(string role)
        => RoleVerdicts.FirstOrDefault(item => string.Equals(item.RoleId, Normalize(role), StringComparison.OrdinalIgnoreCase))
            ?? RoleVerdicts[0];

    public ReadyRoleKit GetRoleKit(string kitId)
        => RoleKits.FirstOrDefault(item => string.Equals(item.KitId, Normalize(kitId), StringComparison.OrdinalIgnoreCase))
            ?? throw new KeyNotFoundException($"Unknown ready-for-tonight kit '{kitId}'.");

    public ReadyPacketAsset GetPacketAsset(string role)
        => PacketAssets.FirstOrDefault(item => string.Equals(item.RoleId, Normalize(role), StringComparison.OrdinalIgnoreCase))
            ?? throw new KeyNotFoundException($"Unknown ready-for-tonight role '{role}'.");

    public string BuildPacketMarkdown(string role)
    {
        ReadyRoleVerdict verdict = GetRoleVerdict(role);
        ReadyPacketAsset packet = GetPacketAsset(role);
        var lines = new List<string>
        {
            $"# {packet.Label}",
            string.Empty,
            $"Status: {verdict.StatusLabel}",
            string.Empty,
            packet.Summary,
            string.Empty,
            "## Blocking reasons",
            string.Empty
        };

        lines.AddRange(verdict.BlockingReasons.Select(item => $"- {item}"));
        lines.Add(string.Empty);
        lines.Add("## Fix now");
        lines.Add(string.Empty);
        lines.AddRange(verdict.FixNowActions.Select(item => $"- {item.Label}: {item.Href}"));
        lines.Add(string.Empty);
        lines.Add("## Changed since last session");
        lines.Add(string.Empty);
        lines.AddRange(verdict.ChangedSinceLastSession.Select(item => $"- {item}"));
        lines.Add(string.Empty);
        lines.Add($"Next best screen: {verdict.NextBestScreen}");
        lines.Add(string.Empty);
        lines.Add("Details:");
        lines.AddRange(verdict.ProofReceipts.Select(item => $"- {item}"));

        return string.Join('\n', lines) + "\n";
    }

    public string BuildPacketJson(string role)
        => JsonSerializer.Serialize(
            new
            {
                verdict = GetRoleVerdict(role),
                packet = GetPacketAsset(role),
                generated_at_utc = DateTimeOffset.UtcNow
            },
            new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });

    public string BuildLoadoutJson(string kitId)
    {
        ReadyRoleKit kit = GetRoleKit(kitId);
        var payload = new
        {
            kit.KitId,
            kit.RoleLane,
            kit.Label,
            kit.Summary,
            highlights = kit.Highlights,
            generated_at_utc = DateTimeOffset.UtcNow
        };

        return JsonSerializer.Serialize(payload, new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });
    }

    public string BuildMobileHandoffJson()
        => JsonSerializer.Serialize(
            new
            {
                mode = "ready_for_tonight",
                status = "ready",
                summary = "Use the same first-party handoff on mobile so the starter packet, join rail, and recovery/support routes stay attached.",
                next_best_screen = "/mobile",
                install_route = "/downloads",
                continuity_route = "/play/continuity",
                pwa_route = "/mobile",
                frontdoor_launch_route = "/mobile/player",
                playtime_tools = new[]
                {
                    new
                    {
                        id = "inventory",
                        label = "Inventory",
                        summary = "Keep table-facing gear and carried items visible during play without opening the full builder."
                    },
                    new
                    {
                        id = "health",
                        label = "Health",
                        summary = "Track damage and recovery cues as session notes, not as automatic rules decisions."
                    },
                    new
                    {
                        id = "ammo",
                        label = "Ammo",
                        summary = "Keep ammunition and reload reminders close to the play screen."
                    },
                    new
                    {
                        id = "modifiers",
                        label = "Modifiers",
                        summary = "Surface current table modifiers and GM notes before a roll."
                    },
                    new
                    {
                        id = "quick_rolls",
                        label = "Quick rolls and odds",
                        summary = "Show quick dice entry and chance framing for playtime checks without replacing GM authority."
                    },
                    new
                    {
                        id = "living_world",
                        label = "Opt-in living world",
                        summary = "Black Ledger heat and turn updates stay gated behind account opt-in and followed-world selection."
                    }
                },
                boundaries = new[]
                {
                    "The mobile shell supports playtime tracking; character building stays before or after the session.",
                    "Black Ledger live detail requires account opt-in and followed-world selection.",
                    "GM remains final authority for modifiers, dice calls, and table consequences."
                },
                role_routes = new[]
                {
                    new
                    {
                        role = "Player",
                        mode = "player",
                        route = "/mobile/player",
                        manifest_path = "/manifest.player.webmanifest",
                        manifest_id = "/mobile/player",
                        manifest_start_url = "/mobile/player",
                        session_handoff_route_template = "/mobile/player?sessionId={sessionId}&role=Player",
                        frontdoor_default = true
                    },
                    new
                    {
                        role = "GameMaster",
                        mode = "gm",
                        route = "/mobile/gm",
                        manifest_path = "/manifest.gm.webmanifest",
                        manifest_id = "/mobile/gm",
                        manifest_start_url = "/mobile/gm",
                        session_handoff_route_template = "/mobile/gm?sessionId={sessionId}&role=GameMaster",
                        frontdoor_default = false
                    }
                },
                packet_routes = PacketAssets.Select(item => new { item.RoleId, markdown = item.MarkdownHref, json = item.JsonHref }).ToArray(),
                generated_at_utc = DateTimeOffset.UtcNow
            },
            new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true });

    private static string Normalize(string? value)
        => value?.Trim().ToLowerInvariant() ?? string.Empty;
}

public sealed record ReadyAction(
    string Label,
    string Href,
    string Tone);

public sealed record ReadyRoleVerdict(
    string RoleId,
    string RoleLabel,
    string Status,
    string StatusLabel,
    string Summary,
    IReadOnlyList<string> BlockingReasons,
    IReadOnlyList<string> ChangedSinceLastSession,
    IReadOnlyList<ReadyAction> FixNowActions,
    string NextBestScreen,
    IReadOnlyList<string> ProofReceipts);

public sealed record ReadyRoleKit(
    string KitId,
    string RoleLane,
    string Label,
    string Summary,
    string DownloadHref,
    IReadOnlyList<string> Highlights);

public sealed record ReadyPacketAsset(
    string RoleId,
    string Label,
    string Summary,
    string MarkdownHref,
    string JsonHref);
