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

        var projection = ops.GetProjection("session_ops", "scene_downtown", "scene_downtown:r3");
        VerificationAssert.Equal(2, projection.LedgerVersion, "Ops board should project ledger version from the canonical session ledger.");
        VerificationAssert.True(projection.UnresolvedItems.Count >= 2, "Ops board should surface unresolved or heat-bearing items from ledger evidence.");
        VerificationAssert.Equal(2, projection.ChecklistSummary.TotalItems, "Ops board should summarize checklist counts.");
        VerificationAssert.Equal(1, projection.ChecklistSummary.CompletedItems, "Ops board should summarize completed checklist items.");
        VerificationAssert.True(projection.RevealSurfaces.Any(item => item.AssetId == reveal.AssetId), "Ops board should surface reveal assets for player delivery.");

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
}
