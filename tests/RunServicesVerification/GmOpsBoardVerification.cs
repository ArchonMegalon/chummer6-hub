using Chummer.Contracts.Hub;
using Chummer.Run.AI.Services.Ops;
using Chummer.Run.AI.Services.Session;
using Chummer.Run.AI.Services.Spider;
using Chummer.Run.Contracts.Ops;

namespace RunServicesVerification;

internal static class GmOpsBoardVerification
{
    public static async Task RunAsync()
    {
        var ledger = new SessionLedgerService();
        var outbox = new DeliveryOutboxService();
        var ops = new GmOpsBoardService(ledger, outbox);

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_downtown",
                EventType: "objective.unresolved",
                Payload: "Open extraction route for the scientist remains unresolved",
                AtUtc: DateTimeOffset.UtcNow.AddMinutes(-4),
                EventId: "evt_ops_01",
                SceneRevision: "scene_downtown:r3",
                IdempotencyKey: "objective:1"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_downtown",
                EventType: "heat.alert",
                Payload: "Knight Errant heat rising near the loading bay",
                AtUtc: DateTimeOffset.UtcNow.AddMinutes(-2),
                EventId: "evt_ops_02",
                SceneRevision: "scene_downtown:r3",
                IdempotencyKey: "heat:1")
        ]);

        var checklist = ops.CreatePrepAsset(new GmPrepAssetCreateRequest(
            CampaignId: "campaign_ops",
            SessionId: "session_ops",
            SceneId: "scene_downtown",
            Title: "Pre-run checklist",
            Kind: GmPrepAssetKind.Checklist,
            Audience: GmPrepAssetAudience.GameMaster,
            Summary: "GM prep for the lab breach",
            Body: "Confirm approach, fallback van, and comms blackout.",
            Tags: ["prep", "downtown"],
            ChecklistItems:
            [
                new GmPrepChecklistItem("c1", "Confirm fallback van"),
                new GmPrepChecklistItem("c2", "Stage spoofed badges", true)
            ],
            SourceEventIds: ["evt_ops_01"],
            CreatedBy: "gm.ops",
            RuntimeFingerprint: "ops-fingerprint"));

        var reveal = ops.CreatePrepAsset(new GmPrepAssetCreateRequest(
            CampaignId: "campaign_ops",
            SessionId: "session_ops",
            SceneId: "scene_downtown",
            Title: "Player reveal: loading bay pressure",
            Kind: GmPrepAssetKind.RevealSurface,
            Audience: GmPrepAssetAudience.Players,
            Summary: "Pressure doors slam and the bay lights shift to red.",
            Body: "The loading bay seals and an alarm pulse rolls through the room.",
            Tags: ["reveal", "player-safe"],
            SourceEventIds: ["evt_ops_02"],
            CreatedBy: "gm.ops",
            RuntimeFingerprint: "ops-fingerprint"));
        var libraryNote = ops.CreatePrepAsset(new GmPrepAssetCreateRequest(
            CampaignId: "campaign_ops",
            SessionId: null,
            SceneId: null,
            Title: "Reusable threat ladder",
            Kind: GmPrepAssetKind.Note,
            Audience: GmPrepAssetAudience.GameMaster,
            Summary: "Campaign-level fallback escalation beats",
            Body: "Use the Renraku escalation ladder when heat spikes above the current scene plan.",
            Tags: ["library", "reusable"],
            SourceEventIds: Array.Empty<string>(),
            CreatedBy: "gm.ops",
            RuntimeFingerprint: "ops-fingerprint"));
        var governedEncounterPrep = ops.CreatePrepAssetFromProject(new GmPrepAssetCatalogImportRequest(
            CampaignId: "campaign_ops",
            SessionId: "session_ops",
            SceneId: "scene_downtown",
            Project: BuildGovernedEncounterProject(),
            AdditionalTags: ["opposition", "packet"],
            CreatedBy: "gm.ops",
            RuntimeFingerprint: "ops-fingerprint"));
        var governedNpcPackPrep = ops.CreatePrepAssetFromProject(new GmPrepAssetCatalogImportRequest(
            CampaignId: "campaign_ops",
            SessionId: "session_ops",
            SceneId: "scene_downtown",
            Project: BuildGovernedNpcPackProject(),
            AdditionalTags: ["opposition", "roster"],
            CreatedBy: "gm.ops",
            RuntimeFingerprint: "ops-fingerprint"));

        var projection = ops.GetProjection("session_ops", "scene_downtown", "scene_downtown:r3");
        var sceneOnlyAssets = ops.ListPrepAssets(campaignId: "campaign_ops", sessionId: "session_ops", sceneId: "scene_downtown");
        var sceneWithLibrary = ops.ListPrepAssets(
            campaignId: "campaign_ops",
            sessionId: "session_ops",
            sceneId: "scene_downtown",
            includeReusableCampaignAssets: true);
        var reusableLibrarySearch = ops.ListPrepAssets(
            campaignId: "campaign_ops",
            sessionId: "session_ops",
            sceneId: "scene_downtown",
            includeReusableCampaignAssets: true,
            queryText: "reusable threat");
        var checklistSearch = ops.ListPrepAssets(
            campaignId: "campaign_ops",
            sessionId: "session_ops",
            sceneId: "scene_downtown",
            queryText: "spoofed badges");
        var governedEncounterSearch = ops.ListPrepAssets(
            campaignId: "campaign_ops",
            sessionId: "session_ops",
            sceneId: "scene_downtown",
            queryText: "checkpoint scanner");
        var governedRosterSearch = ops.ListPrepAssets(
            campaignId: "campaign_ops",
            sessionId: "session_ops",
            sceneId: "scene_downtown",
            queryText: "security roster");
        var exportedAssets = ops.ExportPortableAssets(
            "campaign_ops",
            "session_ops",
            "scene_downtown",
            includeReusableCampaignAssets: true);
        VerificationAssert.Equal(2, projection.LedgerVersion, "Ops board should project ledger version from the canonical session ledger.");
        VerificationAssert.True(projection.UnresolvedItems.Count >= 2, "Ops board should surface unresolved or heat-bearing items from ledger evidence.");
        VerificationAssert.Equal(2, projection.ChecklistSummary.TotalItems, "Ops board should summarize checklist counts.");
        VerificationAssert.Equal(1, projection.ChecklistSummary.CompletedItems, "Ops board should summarize completed checklist items.");
        VerificationAssert.True(projection.RevealSurfaces.Any(item => item.AssetId == reveal.AssetId), "Ops board should surface reveal assets for player delivery.");
        VerificationAssert.Equal(4, sceneOnlyAssets.TotalCount, "Scene-scoped prep lists should stay focused on direct scene assets by default, including governed packet bindings.");
        VerificationAssert.NotNull(governedEncounterPrep.GovernedProject, "Governed packet prep should carry structured governed-project provenance.");
        VerificationAssert.Equal("renraku-checkpoint", governedEncounterPrep.GovernedProject!.ProjectId, "Governed packet prep should preserve the source project id.");
        VerificationAssert.True(
            governedEncounterPrep.Tags.Contains(HubCatalogItemKinds.EncounterPack, StringComparer.OrdinalIgnoreCase),
            "Governed packet prep should retain the source encounter-pack kind as a searchable tag.");
        VerificationAssert.True(
            governedEncounterPrep.Body.Contains("red-samurai", StringComparison.OrdinalIgnoreCase),
            "Governed packet prep should preserve grounded dependency truth from the imported encounter packet.");
        VerificationAssert.NotNull(governedNpcPackPrep.GovernedProject, "Governed NPC pack prep should carry structured governed-project provenance.");
        VerificationAssert.Equal("renraku-security", governedNpcPackPrep.GovernedProject!.ProjectId, "Governed NPC pack prep should preserve the source project id.");
        VerificationAssert.True(
            governedNpcPackPrep.Tags.Contains(HubCatalogItemKinds.NpcPack, StringComparer.OrdinalIgnoreCase),
            "Governed NPC pack prep should retain the source npc-pack kind as a searchable tag.");
        VerificationAssert.True(
            governedNpcPackPrep.Body.Contains("renraku-spider", StringComparison.OrdinalIgnoreCase),
            "Governed NPC pack prep should preserve grounded dependency truth from the imported NPC pack.");
        VerificationAssert.True(
            sceneWithLibrary.Items.Any(item => item.AssetId == libraryNote.AssetId),
            "Prep lists should optionally include reusable campaign assets that stay compatible with the requested session.");
        VerificationAssert.Equal(1, reusableLibrarySearch.TotalCount, "Prep lists should support reusable library search by title and tag tokens.");
        VerificationAssert.True(
            reusableLibrarySearch.Items.Any(item => item.AssetId == libraryNote.AssetId),
            "Prep list search should return the matching reusable campaign asset.");
        VerificationAssert.Equal(1, checklistSearch.TotalCount, "Prep lists should support search across checklist labels.");
        VerificationAssert.True(
            checklistSearch.Items.Any(item => item.AssetId == checklist.AssetId),
            "Prep list search should return the checklist asset when the label matches the query.");
        VerificationAssert.Equal(1, governedEncounterSearch.TotalCount, "Prep lists should support governed encounter packet search by title and dependency content.");
        VerificationAssert.True(
            governedEncounterSearch.Items.Any(item => item.AssetId == governedEncounterPrep.AssetId),
            "Prep list search should return the governed encounter packet binding.");
        VerificationAssert.Equal(1, governedRosterSearch.TotalCount, "Prep lists should support governed NPC pack search by title and dependency content.");
        VerificationAssert.True(
            governedRosterSearch.Items.Any(item => item.AssetId == governedNpcPackPrep.AssetId),
            "Prep list search should return the governed NPC pack binding.");
        VerificationAssert.True(
            exportedAssets.Any(item => item.AssetId == libraryNote.AssetId),
            "Portable prep export should include reusable campaign assets for GM library continuity.");
        VerificationAssert.True(
            exportedAssets.Any(item => item.AssetId == governedEncounterPrep.AssetId),
            "Portable prep export should include governed packet bindings alongside scene prep.");
        VerificationAssert.True(
            exportedAssets.Any(item => item.AssetId == governedNpcPackPrep.AssetId),
            "Portable prep export should include governed NPC pack bindings alongside scene prep.");

        var updatedChecklist = ops.UpdateChecklist(
            checklist.AssetId,
            new GmPrepChecklistUpdateRequest(
                UpdatedBy: "gm.ops",
                ChecklistItems:
                [
                    new GmPrepChecklistItem("c1", "Confirm fallback van", true),
                    new GmPrepChecklistItem("c2", "Stage spoofed badges", true)
                ]));
        VerificationAssert.NotNull(updatedChecklist, "Checklist updates should return the updated prep asset.");
        VerificationAssert.Equal("completed", updatedChecklist!.Status, "Completed checklists should move to completed status.");

        var blockedReveal = ops.Reveal(
            reveal.AssetId,
            new GmPrepAssetRevealRequest(
                SessionId: "session_ops",
                SceneId: "scene_downtown",
                SceneRevision: "scene_downtown:r3",
                RequestedBy: "gm.ops",
                ApprovalState: "pending"));
        VerificationAssert.Equal("approval-required", blockedReveal.Outcome, "Reveal delivery should stay approval-aware for player-visible surfaces.");

        var deliveredReveal = ops.Reveal(
            reveal.AssetId,
            new GmPrepAssetRevealRequest(
                SessionId: "session_ops",
                SceneId: "scene_downtown",
                SceneRevision: "scene_downtown:r3",
                RequestedBy: "gm.ops",
                ApprovalState: "approved"));
        VerificationAssert.Equal("delivered", deliveredReveal.Outcome, "Approved reveal assets should enqueue player delivery.");
        VerificationAssert.NotNull(deliveredReveal.Message, "Approved reveal delivery should return the outbox message.");
        VerificationAssert.True(
            string.Equals("player-screen", deliveredReveal.Channel, StringComparison.Ordinal),
            "Reveal delivery should default to the player-screen channel.");
    }

    private static HubProjectDetailProjection BuildGovernedEncounterProject() =>
        new(
            Summary: new HubCatalogItem(
                ItemId: "renraku-checkpoint",
                Kind: HubCatalogItemKinds.EncounterPack,
                Title: "Renraku checkpoint",
                Description: "Checkpoint packet with red samurai pressure and matrix overwatch.",
                RulesetId: "sr5",
                Visibility: "public",
                TrustTier: "verified",
                LinkTarget: "/hub/encounters/renraku-checkpoint",
                Version: "1.0.0"),
            OwnerId: "hub:default",
            CatalogKind: "npc-vault",
            PublicationStatus: "published",
            ReviewState: "approved",
            RuntimeFingerprint: "npcvault:renraku-checkpoint:v1",
            OwnerReview: null,
            AggregateReview: null,
            Facts:
            [
                new HubProjectDetailFact("threat", "Threat", "High"),
                new HubProjectDetailFact("scene", "Scene posture", "Checkpoint 12 lockdown with scanner coverage")
            ],
            Dependencies:
            [
                new HubProjectDependency(HubProjectDependencyKinds.IncludesNpcEntry, HubCatalogItemKinds.NpcEntry, "red-samurai", "1.0.0", "lead"),
                new HubProjectDependency(HubProjectDependencyKinds.IncludesNpcEntry, HubCatalogItemKinds.NpcEntry, "renraku-spider", "1.0.0", "matrix-support")
            ],
            Actions:
            [
                new HubProjectAction("clone-encounter-pack", "Clone to Library", HubProjectActionKinds.CloneToLibrary),
                new HubProjectAction("open-encounter-pack", "Open Registry Entry", HubProjectActionKinds.OpenRegistry)
            ]);

    private static HubProjectDetailProjection BuildGovernedNpcPackProject() =>
        new(
            Summary: new HubCatalogItem(
                ItemId: "renraku-security",
                Kind: HubCatalogItemKinds.NpcPack,
                Title: "Renraku security roster",
                Description: "Curated security roster with red samurai pressure and matrix support.",
                RulesetId: "sr5",
                Visibility: "public",
                TrustTier: "verified",
                LinkTarget: "/hub/npc-packs/renraku-security",
                Version: "1.0.0"),
            OwnerId: "hub:default",
            CatalogKind: "npc-vault",
            PublicationStatus: "published",
            ReviewState: "approved",
            RuntimeFingerprint: "npcvault:renraku-security:v1",
            OwnerReview: null,
            AggregateReview: null,
            Facts:
            [
                new HubProjectDetailFact("threat", "Threat", "High"),
                new HubProjectDetailFact("roster", "Roster posture", "Checkpoint-ready security team with matrix support")
            ],
            Dependencies:
            [
                new HubProjectDependency(HubProjectDependencyKinds.IncludesNpcEntry, HubCatalogItemKinds.NpcEntry, "red-samurai", "1.0.0"),
                new HubProjectDependency(HubProjectDependencyKinds.IncludesNpcEntry, HubCatalogItemKinds.NpcEntry, "renraku-spider", "1.0.0")
            ],
            Actions:
            [
                new HubProjectAction("clone-npc-pack", "Clone to Library", HubProjectActionKinds.CloneToLibrary),
                new HubProjectAction("open-npc-pack", "Open Registry Entry", HubProjectActionKinds.OpenRegistry)
            ]);
}
