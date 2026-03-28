using Chummer.Run.AI.Services.Ops;
using Chummer.Run.AI.Services.Session;
using Chummer.Run.AI.Services.Spider;
using Chummer.Run.Contracts.Ops;

namespace RunServicesVerification;

internal static class OfflineSyncVerification
{
    public static async Task RunAsync()
    {
        var ledger = new SessionLedgerService();
        var outbox = new DeliveryOutboxService();
        var ops = new GmOpsBoardService(ledger, outbox);
        var runtime = new SessionRuntimeBundleService(ledger);
        var sync = new OfflineSyncService(ledger, runtime, ops);

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session-offline",
                SceneId: "scene-kitsap",
                EventType: "alarm-tripped",
                Payload: "{\"zone\":\"A\"}",
                AtUtc: DateTimeOffset.Parse("2026-03-10T10:00:00+00:00"),
                EventId: "evt-001"),
            new SessionEventEnvelope(
                SessionId: "session-offline",
                SceneId: "scene-kitsap",
                EventType: "door-opened",
                Payload: "{\"door\":\"south\"}",
                AtUtc: DateTimeOffset.Parse("2026-03-10T10:01:00+00:00"),
                EventId: "evt-002")
        ]);

        var prep = ops.CreatePrepAsset(new GmPrepAssetCreateRequest(
            CampaignId: "campaign-offline",
            SessionId: "session-offline",
            SceneId: "scene-kitsap",
            Title: "Offline prep",
            Kind: GmPrepAssetKind.Checklist,
            Audience: GmPrepAssetAudience.GameMaster,
            Summary: "portable prep",
            Body: "check ingress points",
            ChecklistItems:
            [
                new GmPrepChecklistItem("check-1", "Ping drones", false)
            ],
            CreatedBy: "gm.ops"));
        var reusableLibraryAsset = ops.CreatePrepAsset(new GmPrepAssetCreateRequest(
            CampaignId: "campaign-offline",
            SessionId: null,
            SceneId: null,
            Title: "Reusable chase ladder",
            Kind: GmPrepAssetKind.Note,
            Audience: GmPrepAssetAudience.GameMaster,
            Summary: "Campaign-level chase beats",
            Body: "Escalate from roadblock to drone tail to full strike-team response.",
            Tags: ["library", "travel"],
            CreatedBy: "gm.ops"));

        var snapshot = sync.CreateSnapshot(new OfflineSyncSnapshotRequest(
            CampaignId: "campaign-offline",
            SessionId: "session-offline",
            SceneId: "scene-kitsap",
            ExportedBy: "gm.ops",
            DeviceId: "tablet-1"));

        VerificationAssert.Equal("offline_sync_snapshot_v1", snapshot.ContractFamily, "Offline snapshots should use canonical family.");
        VerificationAssert.True(snapshot.PrepAssets.Count == 2, "Snapshot should include scene prep plus reusable campaign prep assets.");
        VerificationAssert.True(snapshot.PrepAssets.Any(item => item.AssetId == reusableLibraryAsset.AssetId), "Snapshot should include reusable campaign prep assets for offline library continuity.");
        VerificationAssert.True(snapshot.SessionProjection.Events.Count == 2, "Snapshot should include current ledger events.");

        var reconcile = await sync.ReconcileAsync(new OfflineSyncReconcileRequest(
            Snapshot: snapshot with
            {
                PrepAssets =
                [
                    snapshot.PrepAssets[0] with
                    {
                        UpdatedAtUtc = snapshot.PrepAssets[0].UpdatedAtUtc.AddMinutes(5),
                        Status = "in-progress"
                    }
                ]
            },
            ReconciledBy: "gm.ops",
            LocalPendingEvents:
            [
                new SessionEventEnvelope(
                    SessionId: "session-offline",
                    SceneId: "scene-kitsap",
                    EventType: "alarm-tripped",
                    Payload: "{\"zone\":\"A\"}",
                    AtUtc: DateTimeOffset.Parse("2026-03-10T10:00:00+00:00"),
                    EventId: "evt-001"),
                new SessionEventEnvelope(
                    SessionId: "session-offline",
                    SceneId: "scene-kitsap",
                    EventType: "camera-disabled",
                    Payload: "{\"camera\":\"north\"}",
                    AtUtc: DateTimeOffset.Parse("2026-03-10T10:02:00+00:00"),
                    EventId: "evt-003")
            ],
            LocalPrepAssets:
            [
                snapshot.PrepAssets[0] with
                {
                    AssetId = prep.AssetId,
                    UpdatedAtUtc = snapshot.PrepAssets[0].UpdatedAtUtc.AddMinutes(10),
                    Status = "completed"
                }
            ]));

        VerificationAssert.True(reconcile.SessionMerge.AcceptedEvents >= 1, "Reconcile should import new local session events.");
        VerificationAssert.True(reconcile.SessionMerge.DuplicateEvents >= 1, "Reconcile should deduplicate already-synced session events.");
        VerificationAssert.True(reconcile.PrepSurface.ImportedCount >= 1, "Reconcile should merge prep assets.");
        VerificationAssert.Equal("offline_sync_snapshot_v1", reconcile.ContractFamily, "Reconcile should return canonical offline family.");
    }
}
