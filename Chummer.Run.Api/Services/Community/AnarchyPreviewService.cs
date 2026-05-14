using System.Text.Json;
using Chummer.Run.Api.ViewModels;

namespace Chummer.Run.Api.Services.Community;

public sealed class AnarchyPreviewService
{
    public const string RulesetId = "shadowrun_anarchy";

    private readonly BlackLedgerDispatchService _dispatches;

    public AnarchyPreviewService(BlackLedgerDispatchService dispatches)
    {
        _dispatches = dispatches;
    }

    public AnarchyRunnerProfileViewModel LoadFeaturedProfile()
        => new(
            RunnerId: "anarchy_runner_emerald_sprawl_switchback",
            Handle: "Switchback",
            Concept: "Dockside courier who turned faction heat, route memory, and too many favors into a survivable day job.",
            MetatypeOrIdentityTag: "Human courier",
            ArchetypeTags: ["courier", "face-adjacent", "route memory", "ghostline runner"],
            NarrativeCues: ["talk first", "keep exits mapped", "never carry the only copy"],
            Capabilities: ["fast exfiltration", "social cover", "street routing", "quiet logistics"],
            ShadowAmps: ["Reflex splice", "Signal ghosting", "Cargo scramble"],
            GearTags: ["fold scooter", "burner link", "microdrone lookout"],
            Contacts: ["Ashline archivist", "Neon Docks loader chief", "Ghostline rumor broker"],
            Complications: ["Debt Heat 3", "Ghostline favor marker", "old dock-camera footage still exists"],
            FactionLinks: ["Ashline Circle", "Neon Docks Union"],
            DebtHeat: "3 / rising",
            LedgerFlags: ["public_safe_preview", "faction_linked", "dispatch_ready"],
            Notes: "This is a rules-light preview sheet for fast table continuity, mobile play, and Black Ledger consequence tracking.",
            RulesetId: RulesetId,
            VerdictLabel: "Playable preview",
            PostureLabel: "Rules-light narrative lane");

    public IReadOnlyList<AnarchyLedgerStatViewModel> BuildLedgerStats()
        => [
            new("Narrative pressure", "High", "Ashline paperwork pressure and Neon Docks cargo drift both touch the same courier lane."),
            new("Faction scene heat", "2 active fronts", "Current movement links Switchback to Ashline Circle and Neon Docks Union."),
            new("Complication flags", "3", "Debt, favors, and visible route history stay explicit in the profile."),
            new("Shadow Amp pressure", "1 watched lane", "Signal ghosting is useful enough to create package and dispatch pressure."),
            new("Chaos index", "Contained", "The profile is story-forward without outranking the bounded tick receipts.")
        ];

    public IReadOnlyList<BlackLedgerDispatchViewModel> ListDispatches()
        => _dispatches.ListPublishedDispatches(1).Take(3).ToArray();

    public AnarchyExplainReceiptViewModel BuildExplainReceipt()
        => new(
            ReceiptId: "anarchy_preview_receipt_turn1",
            SourceReceiptId: "ledger_tick_0001_preseeded",
            RulesetId: RulesetId,
            Status: "preview_receipt_backed",
            ProvenanceNotes:
            [
                "Facts come from the public-safe World Tick receipt and published Black Ledger dispatches.",
                "No sourcebook text is embedded in the route, export, or profile sheet.",
                "The lane is a dedicated ruleset preview, not an SR5 or SR6 toggle."
            ],
            CreatedAtUtc: DateTimeOffset.UtcNow.ToString("O"));

    public string BuildExportJson()
    {
        var profile = LoadFeaturedProfile();
        var packet = new Dictionary<string, object?>
        {
            ["ruleset_id"] = profile.RulesetId,
            ["verdict_label"] = profile.VerdictLabel,
            ["runner_id"] = profile.RunnerId,
            ["handle"] = profile.Handle,
            ["concept"] = profile.Concept,
            ["metatype_or_identity_tag"] = profile.MetatypeOrIdentityTag,
            ["archetype_tags"] = profile.ArchetypeTags,
            ["narrative_cues"] = profile.NarrativeCues,
            ["capabilities"] = profile.Capabilities,
            ["shadow_amps"] = profile.ShadowAmps,
            ["gear_tags"] = profile.GearTags,
            ["contacts"] = profile.Contacts,
            ["complications"] = profile.Complications,
            ["faction_links"] = profile.FactionLinks,
            ["debt_heat"] = profile.DebtHeat,
            ["ledger_flags"] = profile.LedgerFlags,
            ["notes"] = profile.Notes,
            ["source_receipt_id"] = "ledger_tick_0001_preseeded",
            ["generated_by"] = "chummer_first_party_preview",
            ["created_at_utc"] = DateTimeOffset.UtcNow.ToString("O")
        };
        return JsonSerializer.Serialize(packet, new JsonSerializerOptions { WriteIndented = true });
    }
}
