using Chummer.Run.AI.Services.Session;

namespace RunServicesVerification;

internal static class RelayVerification
{
    public static async Task RunAsync()
    {
        var ledger = new SessionLedgerService();
        var timestamp = DateTimeOffset.Parse("2026-03-09T12:00:00+00:00");
        var canonical = new SessionEventEnvelope(
            SessionId: "session-ops",
            SceneId: "scene-redmond",
            EventType: "initiative-pass-started",
            Payload: "{\"pass\":1}",
            AtUtc: timestamp.AddMinutes(2),
            EventId: "evt-b",
            SceneRevision: "scene-redmond:r3",
            IdempotencyKey: "relay:002");

        var merge = await ledger.MergeEventsAsync(
        [
            canonical,
            new SessionEventEnvelope(
                SessionId: "session-ops",
                SceneId: "scene-redmond",
                EventType: "status-effect-applied",
                Payload: "{\"target\":\"npc-1\"}",
                AtUtc: timestamp,
                EventId: "evt-a",
                SceneRevision: "scene-redmond:r3",
                IdempotencyKey: "relay:001"),
            new SessionEventEnvelope(
                SessionId: "session-ops",
                SceneId: "scene-redmond",
                EventType: "duplicate",
                Payload: "{\"ignored\":true}",
                AtUtc: timestamp.AddMinutes(5),
                EventId: "evt-a",
                SceneRevision: "scene-redmond:r3",
                IdempotencyKey: "relay:001"),
            new SessionEventEnvelope(
                SessionId: "session-ops",
                SceneId: "scene-puyallup",
                EventType: "wrong-scene",
                Payload: "{}",
                AtUtc: timestamp,
                EventId: "evt-z",
                SceneRevision: "scene-puyallup:r1",
                IdempotencyKey: "relay:other"),
            new SessionEventEnvelope(
                SessionId: "session-ops",
                SceneId: "scene-redmond",
                EventType: "missing-id",
                Payload: "{}",
                AtUtc: timestamp,
                EventId: string.Empty,
                SceneRevision: "scene-redmond:r3",
                IdempotencyKey: "relay:empty")
        ]);

        VerificationAssert.Equal("session_events_vnext", merge.Diagnostics.ContractFamily, "Relay diagnostics should report the canonical family.");
        VerificationAssert.Equal(2, merge.AcceptedEvents, "Relay should accept only canonical same-scene events with ids.");
        VerificationAssert.Equal(1, merge.DuplicateEvents, "Relay should report duplicate event ids.");
        VerificationAssert.Equal(2, merge.IgnoredEvents, "Relay should ignore mismatched-scene and missing-id events.");
        VerificationAssert.True(merge.Diagnostics.Converged, "Relay should converge when all same-scene events were either accepted or deduped.");
        VerificationAssert.Equal("session_events_vnext", merge.Projection.ContractFamily, "Projection should keep the canonical relay family.");
        VerificationAssert.Equal(2, merge.Projection.Events.Count, "Projection should contain only the accepted events.");
        VerificationAssert.Equal("evt-a", merge.Projection.Events[0].EventId, "Projection should sort accepted events by timestamp.");
        VerificationAssert.Equal("evt-b", merge.Projection.Events[1].EventId, "Projection should preserve later accepted events.");
        VerificationAssert.Equal("scene-redmond:r3", merge.Projection.Events[1].SceneRevision!, "Overlay conversions should preserve scene revision.");

        var projection = ledger.GetProjection("session-ops", "scene-redmond");
        VerificationAssert.Equal(merge.Projection.ProjectionFingerprint, projection.ProjectionFingerprint, "Projection reads should stay stable after merge.");
    }
}
