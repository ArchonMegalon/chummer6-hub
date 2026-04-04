using Chummer.Play.Contracts.Relay;
using Chummer.Run.AI.Services.Ops;
using Chummer.Run.AI.Services.Session;
using Chummer.Run.AI.Services.Spider;
using Chummer.Run.Contracts.Ops;
using System.Threading.Tasks;
using Xunit;

namespace Chummer.Tests;

public sealed class GmOpsBoardServiceTests
{
    [Fact]
    public async Task GetProjection_UnresolvedItemsPrioritizeHighSeverityBeforeNewerLowSeverity()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T00:00:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Threat tracker unresolved and still active.",
                AtUtc: baseTime,
                EventId: "evt-high"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist item remains unresolved.",
                AtUtc: baseTime.AddMinutes(10),
                EventId: "evt-low")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-high", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("high", projection.UnresolvedItems[0].Severity);
        Assert.Equal("ops:evt-low", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("low", projection.UnresolvedItems[1].Severity);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsPrioritizeOpsDomainsBeforeNewerGeneralItemsWithinSameSeverity()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T01:00:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open opposition tracker remains unresolved.",
                AtUtc: baseTime,
                EventId: "evt-opposition"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open event control checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(1),
                EventId: "evt-event-control"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open roster movement handoff remains unresolved.",
                AtUtc: baseTime.AddMinutes(2),
                EventId: "evt-roster"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(30),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(4, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-opposition", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-event-control", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("ops:evt-roster", projection.UnresolvedItems[2].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[3].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatPrepLaunchAndTravelPrefetchSignalsAsEventControlDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T02:00:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open prep_launch packet remains unresolved for event lane handoff.",
                AtUtc: baseTime,
                EventId: "evt-prep-launch"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open travel_prefetch request remains unresolved for event controls.",
                AtUtc: baseTime.AddMinutes(1),
                EventId: "evt-travel-prefetch"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(30),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(3, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-travel-prefetch", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-prep-launch", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[2].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatSeasonScheduleSignalsAsEventControlDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T02:30:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open season schedule checkpoint remains unresolved for next launch window.",
                AtUtc: baseTime,
                EventId: "evt-season-schedule"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-season-schedule", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatHostileSignalsAsOppositionDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T03:00:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open hostile window remains unresolved.",
                AtUtc: baseTime,
                EventId: "evt-hostile"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open prep launch packet remains unresolved.",
                AtUtc: baseTime.AddMinutes(1),
                EventId: "evt-event"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(30),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(3, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-hostile", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-event", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[2].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatEncounterSignalsAsOppositionDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T03:20:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open encounter board remains unresolved after enemy rotation.",
                AtUtc: baseTime,
                EventId: "evt-encounter"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open prep launch packet remains unresolved.",
                AtUtc: baseTime.AddMinutes(1),
                EventId: "evt-event"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(30),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(3, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-encounter", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-event", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[2].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatOpforSignalsAsOppositionDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T03:40:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open op-force board remains unresolved after rotation.",
                AtUtc: baseTime,
                EventId: "evt-opfor"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open prep launch packet remains unresolved.",
                AtUtc: baseTime.AddMinutes(1),
                EventId: "evt-event"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(30),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(3, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-opfor", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-event", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[2].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatOpForSignalsAsOppositionDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T03:50:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open op_for board remains unresolved after rotation.",
                AtUtc: baseTime,
                EventId: "evt-op-for"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open prep launch packet remains unresolved.",
                AtUtc: baseTime.AddMinutes(1),
                EventId: "evt-event"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(30),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(3, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-op-for", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-event", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[2].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatOpForcesSignalsAsOppositionDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T03:55:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open op forces board remains unresolved after rotation.",
                AtUtc: baseTime,
                EventId: "evt-op-forces"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open prep launch packet remains unresolved.",
                AtUtc: baseTime.AddMinutes(1),
                EventId: "evt-event"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(30),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(3, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-op-forces", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-event", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[2].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatCrewHandoffSignalsAsRosterMovementDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:00:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open crew handoff queue remains unresolved.",
                AtUtc: baseTime,
                EventId: "evt-crew"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-crew", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatCrewTransferSignalsAsRosterMovementDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:05:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open crewtransfer queue remains unresolved.",
                AtUtc: baseTime,
                EventId: "evt-crewtransfer"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-crewtransfer", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatCrewMoveSignalsAsRosterMovementDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:07:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open crewmove queue remains unresolved.",
                AtUtc: baseTime,
                EventId: "evt-crewmove"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-crewmove", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatCrewSwapSignalsAsRosterMovementDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:08:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open crewswap queue remains unresolved.",
                AtUtc: baseTime,
                EventId: "evt-crewswap"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-crewswap", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatCrewShiftSignalsAsRosterMovementDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:08:30Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open crewshift queue remains unresolved.",
                AtUtc: baseTime,
                EventId: "evt-crewshift"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-crewshift", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatPluralCompactRosterSignalsAsRosterMovementDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:09:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open crewtransfers queue remains unresolved.",
                AtUtc: baseTime,
                EventId: "evt-crewtransfers"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-crewtransfers", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatPrepLibraryPacketSignalsAsPrepLibraryDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:20:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open prep library packet briefing remains unresolved for campaign return lane.",
                AtUtc: baseTime,
                EventId: "evt-prep-library"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-prep-library", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatRecapContinuityShorthandAsPrepLibraryDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:22:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open postsession prep lane remains unresolved before next return checkpoint.",
                AtUtc: baseTime,
                EventId: "evt-postsession"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open post-run prep lane remains unresolved before next return checkpoint.",
                AtUtc: baseTime.AddMinutes(1),
                EventId: "evt-post-run"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open after-action report prep lane remains unresolved before next return checkpoint.",
                AtUtc: baseTime.AddMinutes(2),
                EventId: "evt-after-action-report"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open after-action review prep lane remains unresolved before next return checkpoint.",
                AtUtc: baseTime.AddMinutes(3),
                EventId: "evt-after-action-review"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open postmortem prep lane remains unresolved before next return checkpoint.",
                AtUtc: baseTime.AddMinutes(4),
                EventId: "evt-postmortem"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open debriefing prep lane remains unresolved before next return checkpoint.",
                AtUtc: baseTime.AddMinutes(5),
                EventId: "evt-debriefing"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open debriefed prep lane remains unresolved before next return checkpoint.",
                AtUtc: baseTime.AddMinutes(5).AddSeconds(30),
                EventId: "evt-debriefed"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open de-briefing prep lane remains unresolved before next return checkpoint.",
                AtUtc: baseTime.AddMinutes(5).AddSeconds(40),
                EventId: "evt-de-briefing"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open outbriefed prep lane remains unresolved before next return checkpoint.",
                AtUtc: baseTime.AddMinutes(5).AddSeconds(45),
                EventId: "evt-outbriefed"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open AAR prep lane remains unresolved before next return checkpoint.",
                AtUtc: baseTime.AddMinutes(6),
                EventId: "evt-aar"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open retrospective prep lane remains unresolved before next return checkpoint.",
                AtUtc: baseTime.AddMinutes(7),
                EventId: "evt-retrospective"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open lessons learned prep lane remains unresolved before next return checkpoint.",
                AtUtc: baseTime.AddMinutes(8),
                EventId: "evt-lessons-learned"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(21),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(6, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-lessons-learned", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-retrospective", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("ops:evt-aar", projection.UnresolvedItems[2].ItemId);
        Assert.Contains(projection.UnresolvedItems, item => item.ItemId == "ops:evt-outbriefed");
        Assert.Contains(projection.UnresolvedItems, item => item.ItemId == "ops:evt-debriefed");
        Assert.Contains(projection.UnresolvedItems, item => item.ItemId == "ops:evt-de-briefing");
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatPostGameContinuityShorthandAsPrepLibraryDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:23:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open post-game prep lane remains unresolved before next return checkpoint.",
                AtUtc: baseTime,
                EventId: "evt-post-game"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-post-game", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatHotWashContinuityShorthandAsPrepLibraryDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:23:30Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open hot-wash prep lane remains unresolved before next return checkpoint.",
                AtUtc: baseTime,
                EventId: "evt-hot-wash"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-hot-wash", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatLessonLearntContinuityShorthandAsPrepLibraryDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:24:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open lessons learnt prep lane remains unresolved before next return checkpoint.",
                AtUtc: baseTime,
                EventId: "evt-lessons-learnt"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-lessons-learnt", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatOutBriefContinuityShorthandAsPrepLibraryDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:24:30Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open out-brief prep lane remains unresolved before next return checkpoint.",
                AtUtc: baseTime,
                EventId: "evt-out-brief"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-out-brief", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatDiaryContactsDowntimeReturnSignalsAsContinuityReturnDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:25:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Campaign diary contacts downtime return lane pending for next session reopen.",
                AtUtc: baseTime,
                EventId: "evt-continuity-return"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(15),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-continuity-return", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatDiaryPluralSignalsAsContinuityReturnDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:25:15Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Campaign diaries remain unresolved before next session return checkpoint reopen.",
                AtUtc: baseTime,
                EventId: "evt-diaries"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(15),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-diaries", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatCarryForwardReturnSignalsAsContinuityReturnDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:25:30Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Campaign carry-forward return loop stays active for diary/contact reopen.",
                AtUtc: baseTime,
                EventId: "evt-carry-forward"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(12),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-carry-forward", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatOfflineSafehouseTravelCacheStaleSignalsAsContinuityReturnDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:26:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Campaign mobile safehouse travel cache stale before next session return checkpoint.",
                AtUtc: baseTime,
                EventId: "evt-offline-stale"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(10),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-offline-stale", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatOfflineSyncDriftSignalsAsContinuityReturnDomainWithoutOpenKeyword()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:26:30Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Campaign mobile offline cache sync drift blocks return lane reopen for next checkpoint.",
                AtUtc: baseTime,
                EventId: "evt-sync-drift"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(8),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-sync-drift", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatCompactDomainShorthandAsGovernedOpsDomains()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:40:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open eventcontrol board remains unresolved for seasonops lane.",
                AtUtc: baseTime,
                EventId: "evt-eventcontrol"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open rostermove queue remains unresolved before launch.",
                AtUtc: baseTime.AddMinutes(1),
                EventId: "evt-rostermove"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open preplibrary packet remains unresolved for this session.",
                AtUtc: baseTime.AddMinutes(2),
                EventId: "evt-preplibrary"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(4, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-eventcontrol", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-preplibrary", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("ops:evt-rostermove", projection.UnresolvedItems[2].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[3].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatEventCtrlShorthandAsEventControlDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:45:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open eventctrl board remains unresolved for next season gate.",
                AtUtc: baseTime,
                EventId: "evt-eventctrl"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-eventctrl", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatCtlShorthandAsEventControlDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:45:30Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open eventctls board remains unresolved for next season gate.",
                AtUtc: baseTime,
                EventId: "evt-eventctls"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open seasonctls queue remains unresolved for event-control follow-through.",
                AtUtc: baseTime.AddMinutes(1),
                EventId: "evt-seasonctls"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open gmctls lane remains unresolved before event-control checkpoint.",
                AtUtc: baseTime.AddMinutes(2),
                EventId: "evt-gmctls"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open leaguectls lane remains unresolved before event-control checkpoint.",
                AtUtc: baseTime.AddMinutes(3),
                EventId: "evt-leaguectls"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open communityctls lane remains unresolved before event-control checkpoint.",
                AtUtc: baseTime.AddMinutes(4),
                EventId: "evt-communityctls"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(6, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-communityctls", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-leaguectls", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("ops:evt-gmctls", projection.UnresolvedItems[2].ItemId);
        Assert.Equal("ops:evt-seasonctls", projection.UnresolvedItems[3].ItemId);
        Assert.Equal("ops:evt-eventctls", projection.UnresolvedItems[4].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[5].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatCompactGmCtlShorthandAsEventControlDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:45:45Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open gmctl lane remains unresolved before event-control checkpoint.",
                AtUtc: baseTime,
                EventId: "evt-gmctl"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(2, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-gmctl", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[1].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatSeasonControlShorthandAsEventControlDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:46:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open seasoncontrol board remains unresolved for next checkpoint.",
                AtUtc: baseTime,
                EventId: "evt-seasoncontrol"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open seasonctrl queue remains unresolved for event-control follow-through.",
                AtUtc: baseTime.AddMinutes(1),
                EventId: "evt-seasonctrl"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open seasoncontrols checkpoint remains unresolved before launch.",
                AtUtc: baseTime.AddMinutes(2),
                EventId: "evt-seasoncontrols"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open seasonctrls queue remains unresolved before launch checkpoint.",
                AtUtc: baseTime.AddMinutes(3),
                EventId: "evt-seasonctrls"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(5, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-seasonctrls", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-seasoncontrols", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("ops:evt-seasonctrl", projection.UnresolvedItems[2].ItemId);
        Assert.Equal("ops:evt-seasoncontrol", projection.UnresolvedItems[3].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[4].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatGmOpsShorthandAsEventControlDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:47:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open gmops board remains unresolved before next checkpoint.",
                AtUtc: baseTime,
                EventId: "evt-gmops"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open gmop queue remains unresolved for event-control follow-through.",
                AtUtc: baseTime.AddMinutes(1),
                EventId: "evt-gmop"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open gmcontrol board remains unresolved for event-control follow-through.",
                AtUtc: baseTime.AddMinutes(2),
                EventId: "evt-gmcontrol"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open gmctrl lane remains unresolved before event-control checkpoint.",
                AtUtc: baseTime.AddMinutes(3),
                EventId: "evt-gmctrl"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(5, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-gmctrl", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-gmcontrol", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("ops:evt-gmop", projection.UnresolvedItems[2].ItemId);
        Assert.Equal("ops:evt-gmops", projection.UnresolvedItems[3].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[4].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatGameMasterPacketShorthandAsEventControlDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:47:10Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open gamemasteropspacket remains unresolved before next checkpoint.",
                AtUtc: baseTime,
                EventId: "evt-gamemasterops-packet"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open game master control packet remains unresolved for event lane follow-through.",
                AtUtc: baseTime.AddMinutes(1),
                EventId: "evt-game-master-control-packet"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(3, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-game-master-control-packet", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-gamemasterops-packet", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[2].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatSplitGmOpsShorthandAsEventControlDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:47:30Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open gm ops board remains unresolved before next checkpoint.",
                AtUtc: baseTime,
                EventId: "evt-gm-ops"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open gm-ops queue remains unresolved before event-control handoff.",
                AtUtc: baseTime.AddMinutes(1),
                EventId: "evt-gm-ops-hyphen"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(3, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-gm-ops-hyphen", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-gm-ops", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[2].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatEventOpsShorthandAsEventControlDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:48:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open eventops board remains unresolved before next checkpoint.",
                AtUtc: baseTime,
                EventId: "evt-eventops"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open eventop queue remains unresolved for event-control follow-through.",
                AtUtc: baseTime.AddMinutes(1),
                EventId: "evt-eventop"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(3, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-eventop", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-eventops", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[2].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatLeagueAndCommunityOpsShorthandAsEventControlDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:48:30Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open league ops board remains unresolved before next checkpoint.",
                AtUtc: baseTime,
                EventId: "evt-league-ops"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open community-ops queue remains unresolved for event-control handoff.",
                AtUtc: baseTime.AddMinutes(1),
                EventId: "evt-community-ops"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open league control board remains unresolved before prep launch.",
                AtUtc: baseTime.AddMinutes(2),
                EventId: "evt-league-control"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open community-control queue remains unresolved before recap closeout.",
                AtUtc: baseTime.AddMinutes(3),
                EventId: "evt-community-control"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(5, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-community-control", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-league-control", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("ops:evt-community-ops", projection.UnresolvedItems[2].ItemId);
        Assert.Equal("ops:evt-league-ops", projection.UnresolvedItems[3].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[4].ItemId);
    }

    [Fact]
    public async Task GetProjection_UnresolvedItemsTreatCompactPrepLaunchAndTravelPrefetchShorthandAsEventControlDomain()
    {
        SessionLedgerService ledger = new();
        var service = CreateService(ledger);
        DateTimeOffset baseTime = DateTimeOffset.Parse("2026-04-04T04:50:00Z");

        await ledger.MergeEventsAsync(
        [
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open preplaunch queue remains unresolved before next lane handoff.",
                AtUtc: baseTime,
                EventId: "evt-preplaunch"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open travelprefetch queue remains unresolved for return devices.",
                AtUtc: baseTime.AddMinutes(1),
                EventId: "evt-travelprefetch"),
            new SessionEventEnvelope(
                SessionId: "session_ops",
                SceneId: "scene_ops",
                EventType: "ops.note",
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(3, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-travelprefetch", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-preplaunch", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[2].ItemId);
    }

    [Fact]
    public void ReconcilePortableAssets_SkipsAssets_WhenRequiredAssetFieldsAreMissing()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        var missingCampaign = BuildPortableAsset(
            assetId: "prep_missing_campaign",
            now: now,
            campaignId: " ");
        var missingTitle = BuildPortableAsset(
            assetId: "prep_missing_title",
            now: now.AddMinutes(1),
            title: "");
        var missingBody = BuildPortableAsset(
            assetId: "prep_missing_body",
            now: now.AddMinutes(2),
            body: "   ");

        OfflineSyncSurfaceMergeResult result = service.ReconcilePortableAssets([missingCampaign, missingTitle, missingBody]);

        Assert.Equal(0, result.ImportedCount);
        Assert.Equal(3, result.SkippedCount);
        Assert.Equal(3, result.Conflicts.Count);
        Assert.All(result.Conflicts, conflict =>
        {
            Assert.Equal("ops-prep", conflict.Surface);
            Assert.Equal("invalid-asset-required-fields", conflict.Reason);
            Assert.Equal("skipped-invalid", conflict.Resolution);
        });
        Assert.Null(service.GetPrepAsset("prep_missing_campaign"));
        Assert.Null(service.GetPrepAsset("prep_missing_title"));
        Assert.Null(service.GetPrepAsset("prep_missing_body"));
    }

    [Fact]
    public void ReconcilePortableAssets_DropsGovernedProject_WhenRequiredFieldsAreMissing()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        var asset = new OfflineSyncPrepAsset(
            AssetId: "prep_missing_fields",
            CampaignId: "campaign_ops",
            SessionId: "session_ops",
            SceneId: "scene_ops",
            Title: "Governed packet with sparse provenance",
            Kind: nameof(GmPrepAssetKind.Note),
            Audience: nameof(GmPrepAssetAudience.GameMaster),
            Summary: "Should not keep malformed governed project payload",
            Body: "ops",
            Tags: ["governed-packet"],
            ChecklistItems: Array.Empty<OfflineSyncPrepChecklistItem>(),
            Status: "draft",
            CreatedBy: "gm.ops",
            RuntimeFingerprint: "ops-fingerprint",
            CreatedAtUtc: now.AddMinutes(-5),
            UpdatedAtUtc: now,
            GovernedProject: new OfflineSyncPrepGovernedProjectReference(
                ProjectKind: "npc-pack",
                ProjectId: "renraku-security",
                Title: null!,
                RulesetId: "sr5",
                LinkTarget: " ",
                TrustTier: "verified"));

        OfflineSyncSurfaceMergeResult result = service.ReconcilePortableAssets([asset]);
        GmPrepAssetRecord? stored = service.GetPrepAsset(asset.AssetId);
        Assert.NotNull(stored);

        Assert.Equal(1, result.ImportedCount);
        OfflineSyncConflict conflict = Assert.Single(result.Conflicts);
        Assert.Equal("prep_missing_fields", conflict.EntityId);
        Assert.Equal("invalid-governed-project-required-fields", conflict.Reason);
        Assert.Equal("dropped-governed-project", conflict.Resolution);
        Assert.Null(stored!.GovernedProject);
    }

    [Fact]
    public void ReconcilePortableAssets_NormalizesGovernedProject_WhenFieldsAreComplete()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        var asset = new OfflineSyncPrepAsset(
            AssetId: "prep_complete_fields",
            CampaignId: "campaign_ops",
            SessionId: "session_ops",
            SceneId: "scene_ops",
            Title: "Governed packet with complete provenance",
            Kind: nameof(GmPrepAssetKind.Note),
            Audience: nameof(GmPrepAssetAudience.GameMaster),
            Summary: "Should keep normalized governed project payload",
            Body: "ops",
            Tags: ["governed-packet"],
            ChecklistItems: Array.Empty<OfflineSyncPrepChecklistItem>(),
            Status: "draft",
            CreatedBy: "gm.ops",
            RuntimeFingerprint: "ops-fingerprint",
            CreatedAtUtc: now.AddMinutes(-5),
            UpdatedAtUtc: now,
            GovernedProject: new OfflineSyncPrepGovernedProjectReference(
                ProjectKind: " npc-pack ",
                ProjectId: " renraku-security ",
                Title: " Renraku security roster ",
                RulesetId: " sr5 ",
                LinkTarget: " /hub/npc-packs/renraku-security ",
                TrustTier: " verified ",
                RuntimeFingerprint: " runtime:1 "));

        OfflineSyncSurfaceMergeResult result = service.ReconcilePortableAssets([asset]);
        GmPrepAssetRecord? stored = service.GetPrepAsset(asset.AssetId);
        Assert.NotNull(stored);

        GmPrepAssetGovernedProjectReference? governed = stored!.GovernedProject;
        Assert.NotNull(governed);
        Assert.Empty(result.Conflicts);
        Assert.Equal("npc-pack", governed!.ProjectKind);
        Assert.Equal("renraku-security", governed.ProjectId);
        Assert.Equal("Renraku security roster", governed.Title);
        Assert.Equal("sr5", governed.RulesetId);
        Assert.Equal("/hub/npc-packs/renraku-security", governed.LinkTarget);
        Assert.Equal("verified", governed.TrustTier);
        Assert.Equal("runtime:1", governed.RuntimeFingerprint);
    }

    [Fact]
    public void ReconcilePortableAssets_DropsGovernedProject_WhenProjectKindIsUnsupported()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        var asset = new OfflineSyncPrepAsset(
            AssetId: "prep_unsupported_kind",
            CampaignId: "campaign_ops",
            SessionId: "session_ops",
            SceneId: "scene_ops",
            Title: "Governed packet with unsupported kind",
            Kind: nameof(GmPrepAssetKind.Note),
            Audience: nameof(GmPrepAssetAudience.GameMaster),
            Summary: "Unsupported kind should fail closed.",
            Body: "ops",
            Tags: ["governed-packet"],
            ChecklistItems: Array.Empty<OfflineSyncPrepChecklistItem>(),
            Status: "draft",
            CreatedBy: "gm.ops",
            RuntimeFingerprint: "ops-fingerprint",
            CreatedAtUtc: now.AddMinutes(-5),
            UpdatedAtUtc: now,
            GovernedProject: new OfflineSyncPrepGovernedProjectReference(
                ProjectKind: "run-module",
                ProjectId: "module_01",
                Title: "Run module",
                RulesetId: "sr5",
                LinkTarget: "/hub/run-modules/module_01",
                TrustTier: "verified"));

        OfflineSyncSurfaceMergeResult result = service.ReconcilePortableAssets([asset]);
        GmPrepAssetRecord? stored = service.GetPrepAsset(asset.AssetId);
        Assert.NotNull(stored);
        OfflineSyncConflict conflict = Assert.Single(result.Conflicts);
        Assert.Equal("prep_unsupported_kind", conflict.EntityId);
        Assert.Equal("invalid-governed-project-kind", conflict.Reason);
        Assert.Equal("dropped-governed-project", conflict.Resolution);
        Assert.Null(stored!.GovernedProject);
    }

    [Fact]
    public void ReconcilePortableAssets_UpdatesExistingAsset_WhenRemoteAssetIdHasWhitespace()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        var initial = BuildPortableAsset(
            assetId: "prep_whitespace_id",
            now: now,
            title: "Initial packet");
        var updated = BuildPortableAsset(
            assetId: " prep_whitespace_id ",
            now: now.AddMinutes(2),
            title: "Updated packet");

        OfflineSyncSurfaceMergeResult result = service.ReconcilePortableAssets([initial, updated]);

        Assert.Equal(2, result.ImportedCount);
        Assert.Equal(0, result.SkippedCount);
        GmPrepAssetRecord? stored = service.GetPrepAsset("prep_whitespace_id");
        Assert.NotNull(stored);
        Assert.Equal("Updated packet", stored!.Title);

        GmPrepAssetListResponse listed = service.ListPrepAssets(campaignId: "campaign_ops");
        Assert.Single(listed.Items);
        Assert.Equal("prep_whitespace_id", listed.Items[0].AssetId);
    }

    [Fact]
    public void ListPrepAssets_QuerySupportsCompactShorthandAcrossWhitespaceAndPunctuation()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        OfflineSyncSurfaceMergeResult import = service.ReconcilePortableAssets(
        [
            BuildPortableAsset(
                assetId: "prep_library_ops",
                now: now,
                title: "Prep library packet",
                body: "Bound to GM prep packet lane."),
            BuildPortableAsset(
                assetId: "event_control_ops",
                now: now.AddMinutes(1),
                title: "Event-control board",
                body: "Season operations timeline remains governed."),
            BuildPortableAsset(
                assetId: "roster_move_ops",
                now: now.AddMinutes(2),
                title: "Roster move checklist",
                body: "Crew handoff receipts are attached.")
        ]);

        Assert.Equal(3, import.ImportedCount);
        Assert.Equal(0, import.SkippedCount);
        Assert.Empty(import.Conflicts);

        GmPrepAssetListResponse prepLibraryMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "preplibrary");
        GmPrepAssetListResponse eventControlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "eventcontrol");
        GmPrepAssetListResponse eventControlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "eventcontrols");
        GmPrepAssetListResponse eventCtrlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "eventctrl");
        GmPrepAssetListResponse eventCtrlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "eventctrls");
        GmPrepAssetListResponse eventControlSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event control");
        GmPrepAssetListResponse eventControlsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event controls");
        GmPrepAssetListResponse eventControlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event-control");
        GmPrepAssetListResponse eventCtrlSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event ctrl");
        GmPrepAssetListResponse eventCtrlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event-ctrl");
        GmPrepAssetListResponse eventOpsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "eventops");
        GmPrepAssetListResponse eventOpMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "eventop");
        GmPrepAssetListResponse eventOperationCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "eventoperation");
        GmPrepAssetListResponse eventOperationsCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "eventoperations");
        GmPrepAssetListResponse eventOpsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event ops");
        GmPrepAssetListResponse eventOpsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event-ops");
        GmPrepAssetListResponse eventOperationSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event operation");
        GmPrepAssetListResponse eventOpHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event-op");
        GmPrepAssetListResponse eventOperationHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event-operation");
        GmPrepAssetListResponse eventOperationsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event operations");
        GmPrepAssetListResponse eventOperationsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event-operations");
        GmPrepAssetListResponse gmOpsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gmops");
        GmPrepAssetListResponse gmOpMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gmop");
        GmPrepAssetListResponse gmOpsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gm ops");
        GmPrepAssetListResponse gmOpsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gm-ops");
        GmPrepAssetListResponse gmOperationMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gmoperation");
        GmPrepAssetListResponse gmOperationsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gmoperations");
        GmPrepAssetListResponse gmOperationSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gm operation");
        GmPrepAssetListResponse gmOperationHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gm-operation");
        GmPrepAssetListResponse gmOperationsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gm operations");
        GmPrepAssetListResponse gmOperationsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gm-operations");
        GmPrepAssetListResponse gmControlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gmcontrol");
        GmPrepAssetListResponse gmControlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gmcontrols");
        GmPrepAssetListResponse gmCtrlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gmctrl");
        GmPrepAssetListResponse gmControlSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gm control");
        GmPrepAssetListResponse gmControlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gm-control");
        GmPrepAssetListResponse gmControlsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gm controls");
        GmPrepAssetListResponse gmControlsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gm-controls");
        GmPrepAssetListResponse gmCtrlSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gm ctrl");
        GmPrepAssetListResponse gmCtrlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gm-ctrl");
        GmPrepAssetListResponse seasonOpsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "seasonops");
        GmPrepAssetListResponse seasonOpMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "seasonop");
        GmPrepAssetListResponse seasonOperationCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "seasonoperation");
        GmPrepAssetListResponse seasonOperationsCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "seasonoperations");
        GmPrepAssetListResponse seasonOpsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "season ops");
        GmPrepAssetListResponse seasonOpsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "season-ops");
        GmPrepAssetListResponse seasonOperationSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "season operation");
        GmPrepAssetListResponse seasonOperationHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "season-operation");
        GmPrepAssetListResponse seasonOperationsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "season operations");
        GmPrepAssetListResponse seasonOperationsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "season-operations");
        GmPrepAssetListResponse seasonControlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "seasoncontrol");
        GmPrepAssetListResponse seasonControlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "seasoncontrols");
        GmPrepAssetListResponse seasonCtrlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "seasonctrl");
        GmPrepAssetListResponse seasonCtrlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "seasonctrls");
        GmPrepAssetListResponse seasonControlSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "season control");
        GmPrepAssetListResponse seasonControlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "season-control");
        GmPrepAssetListResponse leagueOpsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leagueops");
        GmPrepAssetListResponse leagueOpMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leagueop");
        GmPrepAssetListResponse leagueOpHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league-op");
        GmPrepAssetListResponse leagueOperationMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leagueoperation");
        GmPrepAssetListResponse leagueOperationsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leagueoperations");
        GmPrepAssetListResponse leagueOpsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league ops");
        GmPrepAssetListResponse leagueOpsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league-ops");
        GmPrepAssetListResponse leagueOperationsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league operations");
        GmPrepAssetListResponse leagueOperationsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league-operations");
        GmPrepAssetListResponse leagueControlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leaguecontrol");
        GmPrepAssetListResponse leagueControlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leaguecontrols");
        GmPrepAssetListResponse leagueCtrlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leaguectrl");
        GmPrepAssetListResponse leagueCtlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leaguectl");
        GmPrepAssetListResponse leagueCtlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leaguectls");
        GmPrepAssetListResponse leagueCtrlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leaguectrls");
        GmPrepAssetListResponse leagueCtlSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league ctl");
        GmPrepAssetListResponse leagueCtlsSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league ctls");
        GmPrepAssetListResponse leagueCtlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league-ctl");
        GmPrepAssetListResponse leagueCtlsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league-ctls");
        GmPrepAssetListResponse leagueControlSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league control");
        GmPrepAssetListResponse leagueControlsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league controls");
        GmPrepAssetListResponse leagueControlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league-control");
        GmPrepAssetListResponse leagueCtrlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league-ctrl");
        GmPrepAssetListResponse communityOpsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communityops");
        GmPrepAssetListResponse communityOpMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communityop");
        GmPrepAssetListResponse communityOpHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community-op");
        GmPrepAssetListResponse communityOperationMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communityoperation");
        GmPrepAssetListResponse communityOperationsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communityoperations");
        GmPrepAssetListResponse communityOpsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community ops");
        GmPrepAssetListResponse communityOpsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community-ops");
        GmPrepAssetListResponse communityOperationsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community operations");
        GmPrepAssetListResponse communityOperationsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community-operations");
        GmPrepAssetListResponse communityControlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communitycontrol");
        GmPrepAssetListResponse communityControlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communitycontrols");
        GmPrepAssetListResponse communityCtrlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communityctrl");
        GmPrepAssetListResponse communityCtlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communityctl");
        GmPrepAssetListResponse communityCtlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communityctls");
        GmPrepAssetListResponse communityCtrlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communityctrls");
        GmPrepAssetListResponse communityCtlSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community ctl");
        GmPrepAssetListResponse communityCtlsSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community ctls");
        GmPrepAssetListResponse communityCtlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community-ctl");
        GmPrepAssetListResponse communityCtlsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community-ctls");
        GmPrepAssetListResponse communityControlSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community control");
        GmPrepAssetListResponse communityControlsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community controls");
        GmPrepAssetListResponse communityControlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community-control");
        GmPrepAssetListResponse communityCtrlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community-ctrl");
        GmPrepAssetListResponse rosterMoveMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "rostermove");
        GmPrepAssetListResponse rosterMovesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "rostermoves");
        GmPrepAssetListResponse rosterMoveHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster-move");
        GmPrepAssetListResponse crewMoveMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crewmove");
        GmPrepAssetListResponse crewMovesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crewmoves");
        GmPrepAssetListResponse crewShiftMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crewshift");
        GmPrepAssetListResponse crewShiftsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crewshifts");
        GmPrepAssetListResponse crewSwapMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crewswap");
        GmPrepAssetListResponse crewSwapsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crewswaps");
        GmPrepAssetListResponse rosterSwapMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "rosterswap");
        GmPrepAssetListResponse rosterSwapsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "rosterswaps");
        GmPrepAssetListResponse rosterShiftMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "rostershift");
        GmPrepAssetListResponse rosterShiftsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "rostershifts");
        GmPrepAssetListResponse crewMovementMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crewmovement");
        GmPrepAssetListResponse crewMovementsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crewmovements");
        GmPrepAssetListResponse crewMoveHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew-move");
        GmPrepAssetListResponse crewShiftHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew-shift");
        GmPrepAssetListResponse crewMovementHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew-movement");
        GmPrepAssetListResponse crewTransferMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crewtransfer");
        GmPrepAssetListResponse crewTransfersMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crewtransfers");
        GmPrepAssetListResponse crewTransfersSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew transfers");
        GmPrepAssetListResponse crewTransferSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew transfer");
        GmPrepAssetListResponse crewHandoffsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew handoffs");
        GmPrepAssetListResponse crewHandoffSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew handoff");
        GmPrepAssetListResponse crewMovesSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew moves");
        GmPrepAssetListResponse crewMoveSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew move");
        GmPrepAssetListResponse crewShiftsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew shifts");
        GmPrepAssetListResponse crewShiftSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew shift");
        GmPrepAssetListResponse rosterTransfersSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster transfers");
        GmPrepAssetListResponse rosterTransferSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster transfer");
        GmPrepAssetListResponse rosterHandoffsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster handoffs");
        GmPrepAssetListResponse rosterHandoffSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster handoff");
        GmPrepAssetListResponse rosterHandoverCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "rosterhandover");
        GmPrepAssetListResponse rosterHandoversCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "rosterhandovers");
        GmPrepAssetListResponse rosterHandoverSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster handover");
        GmPrepAssetListResponse rosterHandoversSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster handovers");
        GmPrepAssetListResponse rosterHandoverHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster-handover");
        GmPrepAssetListResponse rosterHandoversHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster-handovers");
        GmPrepAssetListResponse rosterMovesSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster moves");
        GmPrepAssetListResponse rosterMoveSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster move");
        GmPrepAssetListResponse rosterShiftsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster shifts");
        GmPrepAssetListResponse rosterShiftSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster shift");
        GmPrepAssetListResponse crewMovementSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew movement");
        GmPrepAssetListResponse crewMovementsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew movements");
        GmPrepAssetListResponse rosterMovementCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "rostermovement");
        GmPrepAssetListResponse rosterMovementsCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "rostermovements");
        GmPrepAssetListResponse rosterMovementSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster movement");
        GmPrepAssetListResponse rosterMovementsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster movements");
        GmPrepAssetListResponse rosterMovementHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster-movement");
        GmPrepAssetListResponse packetsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "packets");
        GmPrepAssetListResponse prepPacketsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "prep packets");
        GmPrepAssetListResponse negativeMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "matrixlibrary");

        Assert.Contains(prepLibraryMatches.Items, item => item.AssetId == "prep_library_ops");
        Assert.Contains(eventControlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventControlsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventCtrlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventCtrlsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventControlSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventControlsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventControlHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventCtrlSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventCtrlHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventOpsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventOpMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventOperationCompactMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventOperationsCompactMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventOpsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventOpsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventOperationSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventOpHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventOperationHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventOperationsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventOperationsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmOpsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmOpMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmOpsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmOpsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmOperationMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmOperationsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmOperationSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmOperationHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmOperationsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmOperationsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmControlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmControlsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmCtrlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmControlSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmControlHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmControlsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmControlsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmCtrlSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(gmCtrlHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonOpsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonOpMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonOperationCompactMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonOperationsCompactMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonOpsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonOpsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonOperationSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonOperationHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonOperationsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonOperationsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonControlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonControlsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonCtrlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonCtrlsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonControlSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonControlHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueOpsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueOpMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueOpHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueOperationMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueOperationsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueOpsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueOpsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueOperationsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueOperationsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueControlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueControlsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueCtrlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueCtlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueCtlsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueCtrlsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueCtlSplitMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueCtlsSplitMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueCtlHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueCtlsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueControlSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueControlsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueControlHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueCtrlHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityOpsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityOpMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityOpHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityOperationMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityOperationsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityOpsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityOpsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityOperationsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityOperationsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityControlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityControlsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityCtrlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityCtlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityCtlsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityCtrlsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityCtlSplitMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityCtlsSplitMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityCtlHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityCtlsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityControlSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityControlsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityControlHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityCtrlHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(rosterMoveMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterMovesMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterMoveHyphenMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewMoveMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewMovesMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewShiftMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewShiftsMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewSwapMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewSwapsMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterSwapMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterSwapsMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterShiftMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterShiftsMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewMovementMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewMovementsMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewMoveHyphenMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewShiftHyphenMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewMovementHyphenMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewTransferMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewTransfersMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewTransfersSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewTransferSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewHandoffsSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewHandoffSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewMovesSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewMoveSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewShiftsSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewShiftSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterTransfersSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterTransferSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterHandoffsSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterHandoffSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterHandoverCompactMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterHandoversCompactMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterHandoverSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterHandoversSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterHandoverHyphenMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterHandoversHyphenMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterMovesSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterMoveSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterShiftsSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterShiftSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewMovementSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewMovementsSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterMovementCompactMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterMovementsCompactMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterMovementSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterMovementsSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterMovementHyphenMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(packetsMatches.Items, item => item.AssetId == "prep_library_ops");
        Assert.Contains(prepPacketsMatches.Items, item => item.AssetId == "prep_library_ops");
        Assert.Empty(negativeMatches.Items);
    }

    [Fact]
    public void ListPrepAssets_QuerySupportsCtlShorthand()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        OfflineSyncSurfaceMergeResult import = service.ReconcilePortableAssets(
        [
            BuildPortableAsset(
                assetId: "event_ctl_ops",
                now: now,
                title: "Event control board",
                body: "Season operations timeline remains governed.")
        ]);

        Assert.Equal(1, import.ImportedCount);
        Assert.Equal(0, import.SkippedCount);
        Assert.Empty(import.Conflicts);

        GmPrepAssetListResponse eventCtlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "eventctl");
        GmPrepAssetListResponse eventCtlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "eventctls");
        GmPrepAssetListResponse eventCtlsSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event ctls");
        GmPrepAssetListResponse eventCtlsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event-ctls");
        GmPrepAssetListResponse seasonCtlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "seasonctl");
        GmPrepAssetListResponse seasonCtlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "seasonctls");
        GmPrepAssetListResponse seasonCtlsSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "season ctls");
        GmPrepAssetListResponse seasonCtlsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "season-ctls");
        GmPrepAssetListResponse gmCtlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gmctl");
        GmPrepAssetListResponse gmCtlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gmctls");
        GmPrepAssetListResponse gmCtlSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gm ctl");
        GmPrepAssetListResponse gmCtlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gm-ctl");
        GmPrepAssetListResponse gmCtlsSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gm ctls");
        GmPrepAssetListResponse gmCtlsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gm-ctls");
        GmPrepAssetListResponse leagueCtlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leaguectl");
        GmPrepAssetListResponse leagueCtlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leaguectls");
        GmPrepAssetListResponse leagueCtlSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league ctl");
        GmPrepAssetListResponse leagueCtlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league-ctl");
        GmPrepAssetListResponse communityCtlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communityctl");
        GmPrepAssetListResponse communityCtlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communityctls");
        GmPrepAssetListResponse communityCtlSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community ctl");
        GmPrepAssetListResponse communityCtlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community-ctl");
        GmPrepAssetListResponse negativeMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "matrixctl");

        Assert.Contains(eventCtlMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(eventCtlsMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(eventCtlsSplitMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(eventCtlsHyphenMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(seasonCtlMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(seasonCtlsMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(seasonCtlsSplitMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(seasonCtlsHyphenMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(gmCtlMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(gmCtlsMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(gmCtlSplitMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(gmCtlHyphenMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(gmCtlsSplitMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(gmCtlsHyphenMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(leagueCtlMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(leagueCtlsMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(leagueCtlSplitMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(leagueCtlHyphenMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(communityCtlMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(communityCtlsMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(communityCtlSplitMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Contains(communityCtlHyphenMatches.Items, item => item.AssetId == "event_ctl_ops");
        Assert.Empty(negativeMatches.Items);
    }

    [Fact]
    public void ListPrepAssets_QuerySupportsSessionLogPluralShorthandAcrossWhitespaceAndPunctuation()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        OfflineSyncSurfaceMergeResult import = service.ReconcilePortableAssets(
        [
            BuildPortableAsset(
                assetId: "session_log_ops",
                now: now,
                title: "Session log continuity packet",
                body: "Session log continuity remains governed for return and diary review.")
        ]);

        Assert.Equal(1, import.ImportedCount);
        Assert.Equal(0, import.SkippedCount);
        Assert.Empty(import.Conflicts);

        GmPrepAssetListResponse compactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "sessionlog");
        GmPrepAssetListResponse compactPluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "sessionlogs");
        GmPrepAssetListResponse splitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "session log");
        GmPrepAssetListResponse splitPluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "session logs");
        GmPrepAssetListResponse hyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "session-log");
        GmPrepAssetListResponse hyphenPluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "session-logs");
        GmPrepAssetListResponse negativeMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "matrixlogs");

        Assert.Contains(compactMatches.Items, item => item.AssetId == "session_log_ops");
        Assert.Contains(compactPluralMatches.Items, item => item.AssetId == "session_log_ops");
        Assert.Contains(splitMatches.Items, item => item.AssetId == "session_log_ops");
        Assert.Contains(splitPluralMatches.Items, item => item.AssetId == "session_log_ops");
        Assert.Contains(hyphenMatches.Items, item => item.AssetId == "session_log_ops");
        Assert.Contains(hyphenPluralMatches.Items, item => item.AssetId == "session_log_ops");
        Assert.Empty(negativeMatches.Items);
    }

    [Fact]
    public void ListPrepAssets_QuerySupportsContinuityPluralShorthand()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        OfflineSyncSurfaceMergeResult import = service.ReconcilePortableAssets(
        [
            BuildPortableAsset(
                assetId: "continuity_plural_ops",
                now: now,
                title: "Diary downtime aftermath continuity packet",
                body: "Diary journal downtime aftermath recap return memory archive history timeline ledger lifestyle license SIN heat faction connection relationship continuity remains governed for next-session return.")
        ]);

        Assert.Equal(1, import.ImportedCount);
        Assert.Equal(0, import.SkippedCount);
        Assert.Empty(import.Conflicts);

        GmPrepAssetListResponse diariesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "diaries");
        GmPrepAssetListResponse journalsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "journals");
        GmPrepAssetListResponse downtimesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "downtimes");
        GmPrepAssetListResponse aftermathsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "aftermaths");
        GmPrepAssetListResponse debriefMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "debrief");
        GmPrepAssetListResponse debriefsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "debriefs");
        GmPrepAssetListResponse debriefedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "debriefed");
        GmPrepAssetListResponse debriefingMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "debriefing");
        GmPrepAssetListResponse debriefingsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "debriefings");
        GmPrepAssetListResponse deBriefSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "de brief");
        GmPrepAssetListResponse deBriefsSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "de briefs");
        GmPrepAssetListResponse deBriefedSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "de briefed");
        GmPrepAssetListResponse deBriefingSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "de briefing");
        GmPrepAssetListResponse deBriefingsSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "de briefings");
        GmPrepAssetListResponse deBriefHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "de-brief");
        GmPrepAssetListResponse deBriefsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "de-briefs");
        GmPrepAssetListResponse deBriefedHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "de-briefed");
        GmPrepAssetListResponse deBriefingHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "de-briefing");
        GmPrepAssetListResponse deBriefingsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "de-briefings");
        GmPrepAssetListResponse outbriefMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "outbrief");
        GmPrepAssetListResponse outbriefsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "outbriefs");
        GmPrepAssetListResponse outbriefedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "outbriefed");
        GmPrepAssetListResponse outbriefingMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "outbriefing");
        GmPrepAssetListResponse outbriefingsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "outbriefings");
        GmPrepAssetListResponse outBriefSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "out brief");
        GmPrepAssetListResponse outBriefsSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "out briefs");
        GmPrepAssetListResponse outBriefedSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "out briefed");
        GmPrepAssetListResponse outBriefingSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "out briefing");
        GmPrepAssetListResponse outBriefingsSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "out briefings");
        GmPrepAssetListResponse outBriefHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "out-brief");
        GmPrepAssetListResponse outBriefsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "out-briefs");
        GmPrepAssetListResponse outBriefedHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "out-briefed");
        GmPrepAssetListResponse outBriefingHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "out-briefing");
        GmPrepAssetListResponse outBriefingsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "out-briefings");
        GmPrepAssetListResponse postmortemMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "postmortem");
        GmPrepAssetListResponse postmortemsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "postmortems");
        GmPrepAssetListResponse postMortemSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "post mortem");
        GmPrepAssetListResponse postMortemsSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "post mortems");
        GmPrepAssetListResponse postMortemHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "post-mortem");
        GmPrepAssetListResponse postMortemsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "post-mortems");
        GmPrepAssetListResponse postsessionMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "postsession");
        GmPrepAssetListResponse postSessionSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "post session");
        GmPrepAssetListResponse postSessionHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "post-session");
        GmPrepAssetListResponse postrunMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "postrun");
        GmPrepAssetListResponse postRunSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "post run");
        GmPrepAssetListResponse postRunHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "post-run");
        GmPrepAssetListResponse postgameMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "postgame");
        GmPrepAssetListResponse postgamesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "postgames");
        GmPrepAssetListResponse postGameSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "post game");
        GmPrepAssetListResponse postGamesSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "post games");
        GmPrepAssetListResponse postGameHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "post-game");
        GmPrepAssetListResponse postGamesHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "post-games");
        GmPrepAssetListResponse afterActionCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "afteraction");
        GmPrepAssetListResponse afterActionsCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "afteractions");
        GmPrepAssetListResponse afterActionReportCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "afteractionreport");
        GmPrepAssetListResponse afterActionReportsCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "afteractionreports");
        GmPrepAssetListResponse afterActionReviewCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "afteractionreview");
        GmPrepAssetListResponse afterActionReviewsCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "afteractionreviews");
        GmPrepAssetListResponse afterActionSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "after action");
        GmPrepAssetListResponse afterActionsSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "after actions");
        GmPrepAssetListResponse afterActionReportSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "after action report");
        GmPrepAssetListResponse afterActionReportsSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "after action reports");
        GmPrepAssetListResponse afterActionReviewSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "after action review");
        GmPrepAssetListResponse afterActionReviewsSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "after action reviews");
        GmPrepAssetListResponse afterActionHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "after-action");
        GmPrepAssetListResponse afterActionsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "after-actions");
        GmPrepAssetListResponse afterActionReportHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "after-action report");
        GmPrepAssetListResponse afterActionReportsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "after-action reports");
        GmPrepAssetListResponse afterActionReviewHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "after-action review");
        GmPrepAssetListResponse afterActionReviewsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "after-action reviews");
        GmPrepAssetListResponse aarMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "aar");
        GmPrepAssetListResponse aarsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "aars");
        GmPrepAssetListResponse retroMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "retro");
        GmPrepAssetListResponse retrosMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "retros");
        GmPrepAssetListResponse retrospectiveMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "retrospective");
        GmPrepAssetListResponse retrospectivesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "retrospectives");
        GmPrepAssetListResponse hotWashCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "hotwash");
        GmPrepAssetListResponse hotWashesCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "hotwashes");
        GmPrepAssetListResponse hotWashSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "hot wash");
        GmPrepAssetListResponse hotWashesSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "hot washes");
        GmPrepAssetListResponse hotWashHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "hot-wash");
        GmPrepAssetListResponse hotWashesHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "hot-washes");
        GmPrepAssetListResponse lessonLearnedCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "lessonlearned");
        GmPrepAssetListResponse lessonsLearnedCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "lessonslearned");
        GmPrepAssetListResponse lessonLearntCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "lessonlearnt");
        GmPrepAssetListResponse lessonsLearntCompactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "lessonslearnt");
        GmPrepAssetListResponse lessonLearnedSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "lesson learned");
        GmPrepAssetListResponse lessonsLearnedSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "lessons learned");
        GmPrepAssetListResponse lessonLearntSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "lesson learnt");
        GmPrepAssetListResponse lessonsLearntSplitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "lessons learnt");
        GmPrepAssetListResponse lessonLearnedHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "lesson-learned");
        GmPrepAssetListResponse lessonsLearnedHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "lessons-learned");
        GmPrepAssetListResponse lessonLearntHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "lesson-learnt");
        GmPrepAssetListResponse lessonsLearntHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "lessons-learnt");
        GmPrepAssetListResponse recapsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "recaps");
        GmPrepAssetListResponse returnsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "returns");
        GmPrepAssetListResponse memoriesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "memories");
        GmPrepAssetListResponse archivesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "archives");
        GmPrepAssetListResponse historiesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "histories");
        GmPrepAssetListResponse timelinesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "timelines");
        GmPrepAssetListResponse ledgersMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "ledgers");
        GmPrepAssetListResponse lifestyleMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "lifestyle");
        GmPrepAssetListResponse lifestylesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "lifestyles");
        GmPrepAssetListResponse licenseMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "license");
        GmPrepAssetListResponse licensesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "licenses");
        GmPrepAssetListResponse licencesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "licences");
        GmPrepAssetListResponse sinMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "sin");
        GmPrepAssetListResponse sinsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "sins");
        GmPrepAssetListResponse heatsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "heats");
        GmPrepAssetListResponse factionsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "factions");
        GmPrepAssetListResponse contactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "contact");
        GmPrepAssetListResponse contactsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "contacts");
        GmPrepAssetListResponse connectionsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "connections");
        GmPrepAssetListResponse relationshipMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "relationship");
        GmPrepAssetListResponse relationshipsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "relationships");
        GmPrepAssetListResponse negativeMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "matrixaftermaths");

        Assert.Contains(diariesMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(journalsMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(downtimesMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(aftermathsMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(debriefMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(debriefsMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(debriefedMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(debriefingMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(debriefingsMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(deBriefSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(deBriefsSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(deBriefedSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(deBriefingSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(deBriefingsSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(deBriefHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(deBriefsHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(deBriefedHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(deBriefingHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(deBriefingsHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(outbriefMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(outbriefsMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(outbriefedMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(outbriefingMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(outbriefingsMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(outBriefSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(outBriefsSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(outBriefedSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(outBriefingSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(outBriefingsSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(outBriefHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(outBriefsHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(outBriefedHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(outBriefingHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(outBriefingsHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(postmortemMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(postmortemsMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(postMortemSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(postMortemsSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(postMortemHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(postMortemsHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(postsessionMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(postSessionSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(postSessionHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(postrunMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(postRunSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(postRunHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(postgameMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(postgamesMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(postGameSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(postGamesSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(postGameHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(postGamesHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(afterActionCompactMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(afterActionsCompactMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(afterActionReportCompactMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(afterActionReportsCompactMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(afterActionReviewCompactMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(afterActionReviewsCompactMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(afterActionSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(afterActionsSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(afterActionReportSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(afterActionReportsSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(afterActionReviewSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(afterActionReviewsSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(afterActionHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(afterActionsHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(afterActionReportHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(afterActionReportsHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(afterActionReviewHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(afterActionReviewsHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(aarMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(aarsMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(retroMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(retrosMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(retrospectiveMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(retrospectivesMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(hotWashCompactMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(hotWashesCompactMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(hotWashSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(hotWashesSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(hotWashHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(hotWashesHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(lessonLearnedCompactMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(lessonsLearnedCompactMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(lessonLearntCompactMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(lessonsLearntCompactMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(lessonLearnedSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(lessonsLearnedSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(lessonLearntSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(lessonsLearntSplitMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(lessonLearnedHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(lessonsLearnedHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(lessonLearntHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(lessonsLearntHyphenMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(recapsMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(returnsMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(memoriesMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(archivesMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(historiesMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(timelinesMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(ledgersMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(lifestyleMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(lifestylesMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(licenseMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(licensesMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(licencesMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(sinMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(sinsMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(heatsMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(factionsMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(contactMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(contactsMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(connectionsMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(relationshipMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Contains(relationshipsMatches.Items, item => item.AssetId == "continuity_plural_ops");
        Assert.Empty(negativeMatches.Items);
    }

    [Fact]
    public void ListPrepAssets_QueryCollapsesContactHeatAndDiaryMutationShorthand()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        OfflineSyncSurfaceMergeResult import = service.ReconcilePortableAssets(
        [
            BuildPortableAsset(
                assetId: "continuity_mutation_ops",
                now: now,
                title: "Diary, contacts, connection, and heat return packet",
                body: "Relationship continuity remains governed on the same next-session return lane with a shared connection signal.")
        ]);

        Assert.Equal(1, import.ImportedCount);
        Assert.Equal(0, import.SkippedCount);
        Assert.Empty(import.Conflicts);

        GmPrepAssetListResponse contactUpdatesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "contact updates");
        GmPrepAssetListResponse contactsChangedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "contacts changed");
        GmPrepAssetListResponse compactContactUpdatesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "contactupdates");
        GmPrepAssetListResponse compactContactsChangedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "contactschanged");
        GmPrepAssetListResponse heatChangesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "heat changes");
        GmPrepAssetListResponse compactHeatChangesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "heatchanges");
        GmPrepAssetListResponse diaryUpdateMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "diary update");
        GmPrepAssetListResponse diariesUpdatesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "diaries updates");
        GmPrepAssetListResponse compactDiaryUpdatesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "diaryupdates");
        GmPrepAssetListResponse compactSessionLogUpdatesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "sessionlogupdates");
        GmPrepAssetListResponse negativeMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "matrix updates");
        GmPrepAssetListResponse compactNegativeMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "matrixupdates");

        Assert.Contains(contactUpdatesMatches.Items, item => item.AssetId == "continuity_mutation_ops");
        Assert.Contains(contactsChangedMatches.Items, item => item.AssetId == "continuity_mutation_ops");
        Assert.Contains(compactContactUpdatesMatches.Items, item => item.AssetId == "continuity_mutation_ops");
        Assert.Contains(compactContactsChangedMatches.Items, item => item.AssetId == "continuity_mutation_ops");
        Assert.Contains(heatChangesMatches.Items, item => item.AssetId == "continuity_mutation_ops");
        Assert.Contains(compactHeatChangesMatches.Items, item => item.AssetId == "continuity_mutation_ops");
        Assert.Contains(diaryUpdateMatches.Items, item => item.AssetId == "continuity_mutation_ops");
        Assert.Contains(diariesUpdatesMatches.Items, item => item.AssetId == "continuity_mutation_ops");
        Assert.Contains(compactDiaryUpdatesMatches.Items, item => item.AssetId == "continuity_mutation_ops");
        Assert.Contains(compactSessionLogUpdatesMatches.Items, item => item.AssetId == "continuity_mutation_ops");
        Assert.Empty(negativeMatches.Items);
        Assert.Empty(compactNegativeMatches.Items);
    }

    [Fact]
    public void ListPrepAssets_QueryCollapsesTravelOfflineReadinessShorthand()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        OfflineSyncSurfaceMergeResult import = service.ReconcilePortableAssets(
        [
            BuildPortableAsset(
                assetId: "travel_readiness_ops",
                now: now,
                title: "Travel prefetch readiness packet",
                body: "Safehouse travel prefetch remains governed with offline continuity receipts.")
        ]);

        Assert.Equal(1, import.ImportedCount);
        Assert.Equal(0, import.SkippedCount);
        Assert.Empty(import.Conflicts);

        GmPrepAssetListResponse offlineReadinessMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "offline readiness");
        GmPrepAssetListResponse compactOfflineReadinessMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "offlinereadiness");
        GmPrepAssetListResponse hyphenOfflineReadinessMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "off-line readiness");
        GmPrepAssetListResponse travelCacheMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "travel cache");
        GmPrepAssetListResponse compactTravelCacheMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "travelcache");
        GmPrepAssetListResponse safehouseStaleCacheMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "safehouse stale cache");
        GmPrepAssetListResponse compactSafehouseReadinessMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "safehousereadiness");
        GmPrepAssetListResponse splitSafehouseReadinessMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "safe house readiness");
        GmPrepAssetListResponse hyphenSafehouseCacheMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "safe-house cache");
        GmPrepAssetListResponse pluralSafehousesCacheMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "safehouses caches");
        GmPrepAssetListResponse pluralTravelsCacheMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "travels caches");
        GmPrepAssetListResponse pluralOfflinesReadinessMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "offlines readinesses");
        GmPrepAssetListResponse mobileOfflineReadinessMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "mobile offline readiness");
        GmPrepAssetListResponse compactMobileOfflineReadinessMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "mobileofflinereadiness");
        GmPrepAssetListResponse compactPluralMobileOfflinesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "mobileofflines");
        GmPrepAssetListResponse mobileHyphenOfflineReadinessMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "mobile off-line readiness");
        GmPrepAssetListResponse mobileTravelCacheMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "mobile travel cache");
        GmPrepAssetListResponse compactMobileTravelCacheMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "mobiletravelcache");
        GmPrepAssetListResponse compactPluralMobileTravelCachesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "mobiletravelcaches");
        GmPrepAssetListResponse mobileSafehouseReadinessMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "mobile safehouse readiness");
        GmPrepAssetListResponse compactMobileSafehouseReadinessMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "mobilesafehousereadiness");
        GmPrepAssetListResponse compactPluralMobileSafehouseReadinessesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "mobilesafehousereadinesses");
        GmPrepAssetListResponse mobileSplitSafehouseCacheMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "mobile safe house cache");
        GmPrepAssetListResponse mobileSafehouseCacheMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "mobile safehouse cache");
        GmPrepAssetListResponse compactMobileSafehouseCacheMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "mobilesafehousecache");
        GmPrepAssetListResponse compactPluralMobileSafehousesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "mobilesafehouses");
        GmPrepAssetListResponse compactPluralMobileSafehouseCachesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "mobilesafehousecaches");
        GmPrepAssetListResponse negativeReadinessMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "matrix readiness");
        GmPrepAssetListResponse negativeCacheMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "matrix cache");
        GmPrepAssetListResponse negativeMobileMatrixCacheMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "mobile matrix cache");

        Assert.Contains(offlineReadinessMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(compactOfflineReadinessMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(hyphenOfflineReadinessMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(travelCacheMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(compactTravelCacheMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(safehouseStaleCacheMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(compactSafehouseReadinessMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(splitSafehouseReadinessMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(hyphenSafehouseCacheMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(pluralSafehousesCacheMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(pluralTravelsCacheMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(pluralOfflinesReadinessMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(mobileOfflineReadinessMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(compactMobileOfflineReadinessMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(compactPluralMobileOfflinesMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(mobileHyphenOfflineReadinessMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(mobileTravelCacheMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(compactMobileTravelCacheMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(compactPluralMobileTravelCachesMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(mobileSafehouseReadinessMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(compactMobileSafehouseReadinessMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(compactPluralMobileSafehouseReadinessesMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(mobileSplitSafehouseCacheMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(mobileSafehouseCacheMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(compactMobileSafehouseCacheMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(compactPluralMobileSafehousesMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Contains(compactPluralMobileSafehouseCachesMatches.Items, item => item.AssetId == "travel_readiness_ops");
        Assert.Empty(negativeReadinessMatches.Items);
        Assert.Empty(negativeCacheMatches.Items);
        Assert.Empty(negativeMobileMatrixCacheMatches.Items);
    }

    [Fact]
    public void ListPrepAssets_QuerySupportsGameMasterOpsShorthandAcrossWhitespaceAndPunctuation()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        OfflineSyncSurfaceMergeResult import = service.ReconcilePortableAssets(
        [
            BuildPortableAsset(
                assetId: "event_control_gamemaster_ops",
                now: now,
                title: "Game-master event control board",
                body: "Game-master operations stay governed on the season event-control lane.")
        ]);

        Assert.Equal(1, import.ImportedCount);
        Assert.Equal(0, import.SkippedCount);
        Assert.Empty(import.Conflicts);

        GmPrepAssetListResponse gameMasterOpsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "game master ops");
        GmPrepAssetListResponse gameMasterOpsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "game-master-ops");
        GmPrepAssetListResponse compactGameMasterOpsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gamemasterops");
        GmPrepAssetListResponse gameMasterOperationMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "game master operation");
        GmPrepAssetListResponse compactGameMasterOperationMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gamemasteroperation");
        GmPrepAssetListResponse gameMasterControlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "game master control");
        GmPrepAssetListResponse compactGameMasterControlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gamemastercontrol");
        GmPrepAssetListResponse gameMasterCtrlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "game master ctrl");
        GmPrepAssetListResponse compactGameMasterCtrlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "gamemasterctrl");
        GmPrepAssetListResponse negativeMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "matrix master ops");

        Assert.Contains(gameMasterOpsMatches.Items, item => item.AssetId == "event_control_gamemaster_ops");
        Assert.Contains(gameMasterOpsHyphenMatches.Items, item => item.AssetId == "event_control_gamemaster_ops");
        Assert.Contains(compactGameMasterOpsMatches.Items, item => item.AssetId == "event_control_gamemaster_ops");
        Assert.Contains(gameMasterOperationMatches.Items, item => item.AssetId == "event_control_gamemaster_ops");
        Assert.Contains(compactGameMasterOperationMatches.Items, item => item.AssetId == "event_control_gamemaster_ops");
        Assert.Contains(gameMasterControlMatches.Items, item => item.AssetId == "event_control_gamemaster_ops");
        Assert.Contains(compactGameMasterControlMatches.Items, item => item.AssetId == "event_control_gamemaster_ops");
        Assert.Contains(gameMasterCtrlMatches.Items, item => item.AssetId == "event_control_gamemaster_ops");
        Assert.Contains(compactGameMasterCtrlMatches.Items, item => item.AssetId == "event_control_gamemaster_ops");
        Assert.Empty(negativeMatches.Items);
    }

    [Fact]
    public void ListPrepAssets_QuerySupportsNextSessionReturnLoopPluralShorthandAcrossWhitespaceAndPunctuation()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        OfflineSyncSurfaceMergeResult import = service.ReconcilePortableAssets(
        [
            BuildPortableAsset(
                assetId: "return_loop_ops",
                now: now,
                title: "Next-session return loop packet",
                body: "Next-session return loop remains governed across downtime recap and memory carry-forward.")
        ]);

        Assert.Equal(1, import.ImportedCount);
        Assert.Equal(0, import.SkippedCount);
        Assert.Empty(import.Conflicts);

        GmPrepAssetListResponse nextSessionMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "nextsession");
        GmPrepAssetListResponse nextSessionPluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "nextsessions");
        GmPrepAssetListResponse nextSessionReturnMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "nextsessionreturn");
        GmPrepAssetListResponse nextSessionReturnPluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "nextsessionreturns");
        GmPrepAssetListResponse nextSessionReturnLoopMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "nextsessionreturnloop");
        GmPrepAssetListResponse nextSessionReturnLoopPluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "nextsessionreturnloops");
        GmPrepAssetListResponse nextSessionReturnLaneMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "nextsessionreturnlane");
        GmPrepAssetListResponse nextSessionReturnLanePluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "nextsessionreturnlanes");
        GmPrepAssetListResponse nextSessionLoopMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "nextsessionloop");
        GmPrepAssetListResponse nextSessionLoopPluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "nextsessionloops");
        GmPrepAssetListResponse sessionReturnMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "sessionreturn");
        GmPrepAssetListResponse sessionReturnPluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "sessionreturns");
        GmPrepAssetListResponse sessionReturnLoopMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "sessionreturnloop");
        GmPrepAssetListResponse sessionReturnLoopPluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "sessionreturnloops");
        GmPrepAssetListResponse sessionReturnLaneMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "sessionreturnlane");
        GmPrepAssetListResponse sessionReturnLanePluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "sessionreturnlanes");
        GmPrepAssetListResponse returnLoopMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "returnloop");
        GmPrepAssetListResponse returnLoopPluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "returnloops");
        GmPrepAssetListResponse returnLaneMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "returnlane");
        GmPrepAssetListResponse returnLanePluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "returnlanes");
        GmPrepAssetListResponse hyphenNextSessionMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "next-session");
        GmPrepAssetListResponse splitNextSessionMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "next session");
        GmPrepAssetListResponse hyphenNextSessionReturnMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "next-session-return");
        GmPrepAssetListResponse splitNextSessionReturnMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "next session return");
        GmPrepAssetListResponse hyphenSessionReturnMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "session-return");
        GmPrepAssetListResponse splitSessionReturnMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "session return");
        GmPrepAssetListResponse splitSessionReturnPluralLoopMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "session return loops");
        GmPrepAssetListResponse hyphenSessionReturnPluralLoopMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "session-return-loops");
        GmPrepAssetListResponse splitSessionReturnLaneMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "session return lane");
        GmPrepAssetListResponse splitSessionReturnLanePluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "session return lanes");
        GmPrepAssetListResponse hyphenSessionReturnLaneMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "session-return-lane");
        GmPrepAssetListResponse hyphenSessionReturnLanePluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "session-return-lanes");
        GmPrepAssetListResponse hyphenReturnLoopMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "return-loop");
        GmPrepAssetListResponse splitReturnLoopMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "return loop");
        GmPrepAssetListResponse splitReturnPluralLoopMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "return loops");
        GmPrepAssetListResponse hyphenReturnPluralLoopMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "return-loops");
        GmPrepAssetListResponse splitReturnLaneMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "return lane");
        GmPrepAssetListResponse splitReturnLanePluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "return lanes");
        GmPrepAssetListResponse hyphenReturnLaneMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "return-lane");
        GmPrepAssetListResponse hyphenReturnLanePluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "return-lanes");
        GmPrepAssetListResponse splitNextSessionReturnPluralLoopMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "next session return loops");
        GmPrepAssetListResponse hyphenNextSessionReturnPluralLoopMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "next-session-return-loops");
        GmPrepAssetListResponse splitNextSessionReturnLanePluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "next session return lanes");
        GmPrepAssetListResponse hyphenNextSessionReturnLanePluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "next-session-return-lanes");
        GmPrepAssetListResponse splitNextSessionsReturnPluralLoopMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "next sessions return loops");
        GmPrepAssetListResponse hyphenNextSessionsReturnPluralLoopMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "next-sessions-return-loops");
        GmPrepAssetListResponse splitNextSessionsReturnLanePluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "next sessions return lanes");
        GmPrepAssetListResponse hyphenNextSessionsReturnLanePluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "next-sessions-return-lanes");
        GmPrepAssetListResponse negativeMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "matrixloop");
        GmPrepAssetListResponse laneNegativeMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "matrixlane");

        Assert.Contains(nextSessionMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(nextSessionPluralMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(nextSessionReturnMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(nextSessionReturnPluralMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(nextSessionReturnLoopMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(nextSessionReturnLoopPluralMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(nextSessionReturnLaneMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(nextSessionReturnLanePluralMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(nextSessionLoopMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(nextSessionLoopPluralMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(sessionReturnMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(sessionReturnPluralMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(sessionReturnLoopMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(sessionReturnLoopPluralMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(sessionReturnLaneMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(sessionReturnLanePluralMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(returnLoopMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(returnLoopPluralMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(returnLaneMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(returnLanePluralMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(hyphenNextSessionMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(splitNextSessionMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(hyphenNextSessionReturnMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(splitNextSessionReturnMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(hyphenSessionReturnMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(splitSessionReturnMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(splitSessionReturnPluralLoopMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(hyphenSessionReturnPluralLoopMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(splitSessionReturnLaneMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(splitSessionReturnLanePluralMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(hyphenSessionReturnLaneMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(hyphenSessionReturnLanePluralMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(hyphenReturnLoopMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(splitReturnLoopMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(splitReturnPluralLoopMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(hyphenReturnPluralLoopMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(splitReturnLaneMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(splitReturnLanePluralMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(hyphenReturnLaneMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(hyphenReturnLanePluralMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(splitNextSessionReturnPluralLoopMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(hyphenNextSessionReturnPluralLoopMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(splitNextSessionReturnLanePluralMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(hyphenNextSessionReturnLanePluralMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(splitNextSessionsReturnPluralLoopMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(hyphenNextSessionsReturnPluralLoopMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(splitNextSessionsReturnLanePluralMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Contains(hyphenNextSessionsReturnLanePluralMatches.Items, item => item.AssetId == "return_loop_ops");
        Assert.Empty(negativeMatches.Items);
        Assert.Empty(laneNegativeMatches.Items);
    }

    [Fact]
    public void ListPrepAssets_QuerySupportsCompactCampaignAftermathAndDowntimeReturnShorthand()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        OfflineSyncSurfaceMergeResult import = service.ReconcilePortableAssets(
        [
            BuildPortableAsset(
                assetId: "aftermath_return_ops",
                now: now,
                title: "Campaign aftermath and downtime return packet",
                body: "Campaign return loop stays governed across aftermath, downtime, and recap follow-through.")
        ]);

        Assert.Equal(1, import.ImportedCount);
        Assert.Equal(0, import.SkippedCount);
        Assert.Empty(import.Conflicts);

        GmPrepAssetListResponse aftermathReturnMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "aftermathreturn");
        GmPrepAssetListResponse aftermathReturnPluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "aftermathreturns");
        GmPrepAssetListResponse aftermathReturnLoopMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "aftermathreturnloop");
        GmPrepAssetListResponse downtimeReturnMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "downtimereturn");
        GmPrepAssetListResponse downtimeReturnLoopMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "downtimereturnloop");
        GmPrepAssetListResponse campaignReturnMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "campaignreturn");
        GmPrepAssetListResponse campaignReturnLoopMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "campaignreturnloop");
        GmPrepAssetListResponse campaignReturnLaneMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "campaignreturnlane");
        GmPrepAssetListResponse negativeCampaignMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "matrixcampaignreturn");
        GmPrepAssetListResponse negativeAftermathMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "matrixaftermathreturn");

        Assert.Contains(aftermathReturnMatches.Items, item => item.AssetId == "aftermath_return_ops");
        Assert.Contains(aftermathReturnPluralMatches.Items, item => item.AssetId == "aftermath_return_ops");
        Assert.Contains(aftermathReturnLoopMatches.Items, item => item.AssetId == "aftermath_return_ops");
        Assert.Contains(downtimeReturnMatches.Items, item => item.AssetId == "aftermath_return_ops");
        Assert.Contains(downtimeReturnLoopMatches.Items, item => item.AssetId == "aftermath_return_ops");
        Assert.Contains(campaignReturnMatches.Items, item => item.AssetId == "aftermath_return_ops");
        Assert.Contains(campaignReturnLoopMatches.Items, item => item.AssetId == "aftermath_return_ops");
        Assert.Contains(campaignReturnLaneMatches.Items, item => item.AssetId == "aftermath_return_ops");
        Assert.Empty(negativeCampaignMatches.Items);
        Assert.Empty(negativeAftermathMatches.Items);
    }

    [Fact]
    public void ListPrepAssets_QuerySupportsOpForShorthandAcrossWhitespaceAndPunctuation()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        OfflineSyncSurfaceMergeResult import = service.ReconcilePortableAssets(
        [
            BuildPortableAsset(
                assetId: "opfor_ops",
                now: now,
                title: "Opposition opfor packet",
                body: "Opfor opposition lane remains governed for launch and return continuity.")
        ]);

        Assert.Equal(1, import.ImportedCount);
        Assert.Equal(0, import.SkippedCount);
        Assert.Empty(import.Conflicts);

        GmPrepAssetListResponse compactMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "opfor");
        GmPrepAssetListResponse compactForceMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "opforce");
        GmPrepAssetListResponse hyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "op-force");
        GmPrepAssetListResponse splitMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "op force");
        GmPrepAssetListResponse splitShortMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "op for");
        GmPrepAssetListResponse compactForcesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "opforces");
        GmPrepAssetListResponse compactPluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "opfors");
        GmPrepAssetListResponse pluralMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "oppositions");
        GmPrepAssetListResponse oppositionWindowMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "oppositionwindow");
        GmPrepAssetListResponse oppositionWindowsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "oppositionwindows");
        GmPrepAssetListResponse oppositionControlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "oppositioncontrol");
        GmPrepAssetListResponse oppositionControlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "oppositioncontrols");
        GmPrepAssetListResponse negativeMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "matrixforce");

        Assert.Contains(compactMatches.Items, item => item.AssetId == "opfor_ops");
        Assert.Contains(compactForceMatches.Items, item => item.AssetId == "opfor_ops");
        Assert.Contains(hyphenMatches.Items, item => item.AssetId == "opfor_ops");
        Assert.Contains(splitMatches.Items, item => item.AssetId == "opfor_ops");
        Assert.Contains(splitShortMatches.Items, item => item.AssetId == "opfor_ops");
        Assert.Contains(compactForcesMatches.Items, item => item.AssetId == "opfor_ops");
        Assert.Contains(compactPluralMatches.Items, item => item.AssetId == "opfor_ops");
        Assert.Contains(pluralMatches.Items, item => item.AssetId == "opfor_ops");
        Assert.Contains(oppositionWindowMatches.Items, item => item.AssetId == "opfor_ops");
        Assert.Contains(oppositionWindowsMatches.Items, item => item.AssetId == "opfor_ops");
        Assert.Contains(oppositionControlMatches.Items, item => item.AssetId == "opfor_ops");
        Assert.Contains(oppositionControlsMatches.Items, item => item.AssetId == "opfor_ops");
        Assert.Empty(negativeMatches.Items);
    }

    [Fact]
    public void ReconcilePortableAssets_SkipsAssets_WhenIncomingPayloadContainsAmbiguousDuplicateAssetVersions()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        var first = BuildPortableAsset(
            assetId: "prep_duplicate_asset",
            now: now,
            title: "First payload title");
        var second = BuildPortableAsset(
            assetId: " prep_duplicate_asset ",
            now: now,
            title: "Second payload title");

        OfflineSyncSurfaceMergeResult result = service.ReconcilePortableAssets([first, second]);

        Assert.Equal(0, result.ImportedCount);
        Assert.Equal(2, result.SkippedCount);
        Assert.Equal(2, result.Conflicts.Count);
        Assert.All(result.Conflicts, conflict =>
        {
            Assert.Equal("prep_duplicate_asset", conflict.EntityId);
            Assert.Equal("duplicate-asset-id-ambiguous", conflict.Reason);
            Assert.Equal("skipped-invalid", conflict.Resolution);
            Assert.Equal(now.ToUnixTimeSeconds().ToString(), conflict.LocalFingerprint);
            Assert.Equal("conflicting-payload", conflict.RemoteFingerprint);
        });
        Assert.Null(service.GetPrepAsset("prep_duplicate_asset"));
    }

    [Fact]
    public void ReconcilePortableAssets_KeepsExistingAsset_WhenIncomingPayloadContainsAmbiguousDuplicateAssetVersions()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        OfflineSyncSurfaceMergeResult seedResult = service.ReconcilePortableAssets(
        [
            BuildPortableAsset(
                assetId: "prep_duplicate_asset_existing",
                now: now,
                title: "Seed title")
        ]);
        Assert.Equal(1, seedResult.ImportedCount);

        var duplicateOne = BuildPortableAsset(
            assetId: "prep_duplicate_asset_existing",
            now: now.AddMinutes(3),
            title: "Duplicate update one");
        var duplicateTwo = BuildPortableAsset(
            assetId: " prep_duplicate_asset_existing ",
            now: now.AddMinutes(3),
            title: "Duplicate update two");

        OfflineSyncSurfaceMergeResult result = service.ReconcilePortableAssets([duplicateOne, duplicateTwo]);

        Assert.Equal(0, result.ImportedCount);
        Assert.Equal(2, result.SkippedCount);
        Assert.Equal(2, result.Conflicts.Count);
        Assert.All(result.Conflicts, conflict =>
        {
            Assert.Equal("prep_duplicate_asset_existing", conflict.EntityId);
            Assert.Equal("duplicate-asset-id-ambiguous", conflict.Reason);
            Assert.Equal("skipped-invalid", conflict.Resolution);
            Assert.Equal(now.AddMinutes(3).ToUnixTimeSeconds().ToString(), conflict.LocalFingerprint);
            Assert.Equal("conflicting-payload", conflict.RemoteFingerprint);
        });

        GmPrepAssetRecord? stored = service.GetPrepAsset("prep_duplicate_asset_existing");
        Assert.NotNull(stored);
        Assert.Equal("Seed title", stored!.Title);
    }

    [Fact]
    public void ReconcilePortableAssets_DeduplicatesIdenticalDuplicateAssetVersions_WhenImportingNewAsset()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        var first = BuildPortableAsset(
            assetId: "prep_duplicate_identical",
            now: now,
            title: "Portable duplicate");
        var second = BuildPortableAsset(
            assetId: " prep_duplicate_identical ",
            now: now,
            title: "Portable duplicate");

        OfflineSyncSurfaceMergeResult result = service.ReconcilePortableAssets([first, second]);

        Assert.Equal(1, result.ImportedCount);
        Assert.Equal(0, result.SkippedCount);
        Assert.Empty(result.Conflicts);
        GmPrepAssetRecord? stored = service.GetPrepAsset("prep_duplicate_identical");
        Assert.NotNull(stored);
        Assert.Equal("Portable duplicate", stored!.Title);
    }

    [Fact]
    public void ReconcilePortableAssets_DeduplicatesIdenticalDuplicateAssetVersions_WhenUpdatingExistingAsset()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        OfflineSyncSurfaceMergeResult seedResult = service.ReconcilePortableAssets(
        [
            BuildPortableAsset(
                assetId: "prep_duplicate_identical_existing",
                now: now,
                title: "Seed title")
        ]);
        Assert.Equal(1, seedResult.ImportedCount);

        var updated = BuildPortableAsset(
            assetId: "prep_duplicate_identical_existing",
            now: now.AddMinutes(3),
            title: "Updated title");
        var duplicate = BuildPortableAsset(
            assetId: " prep_duplicate_identical_existing ",
            now: now.AddMinutes(3),
            title: "Updated title");

        OfflineSyncSurfaceMergeResult result = service.ReconcilePortableAssets([updated, duplicate]);

        Assert.Equal(1, result.ImportedCount);
        Assert.Equal(0, result.SkippedCount);
        Assert.Empty(result.Conflicts);
        GmPrepAssetRecord? stored = service.GetPrepAsset("prep_duplicate_identical_existing");
        Assert.NotNull(stored);
        Assert.Equal("Updated title", stored!.Title);
    }

    [Fact]
    public void ReconcilePortableAssets_KeepsLocalAsset_WhenCampaignDoesNotMatchExistingAsset()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        var local = BuildPortableAsset(
            assetId: "prep_campaign_guard",
            now: now,
            campaignId: "campaign_alpha",
            title: "Alpha prep");
        var remoteCollision = BuildPortableAsset(
            assetId: "prep_campaign_guard",
            now: now.AddMinutes(2),
            campaignId: "campaign_beta",
            title: "Beta prep takeover");

        OfflineSyncSurfaceMergeResult result = service.ReconcilePortableAssets([local, remoteCollision]);

        Assert.Equal(1, result.ImportedCount);
        Assert.Equal(1, result.SkippedCount);
        OfflineSyncConflict conflict = Assert.Single(result.Conflicts);
        Assert.Equal("prep_campaign_guard", conflict.EntityId);
        Assert.Equal("campaign-mismatch", conflict.Reason);
        Assert.Equal("kept-local", conflict.Resolution);
        Assert.Equal("campaign_alpha", conflict.LocalFingerprint);
        Assert.Equal("campaign_beta", conflict.RemoteFingerprint);

        GmPrepAssetRecord? stored = service.GetPrepAsset("prep_campaign_guard");
        Assert.NotNull(stored);
        Assert.Equal("campaign_alpha", stored!.CampaignId);
        Assert.Equal("Alpha prep", stored.Title);
    }

    [Fact]
    public void ReconcilePortableAssets_SkipsAssets_WhenKindAudienceOrStatusIsInvalid()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        var invalidKind = BuildPortableAsset(
            assetId: "prep_invalid_kind",
            now: now) with
        {
            Kind = "not-a-kind"
        };
        var invalidAudience = BuildPortableAsset(
            assetId: "prep_invalid_audience",
            now: now.AddMinutes(1)) with
        {
            Audience = "not-an-audience"
        };
        var invalidStatus = BuildPortableAsset(
            assetId: "prep_invalid_status",
            now: now.AddMinutes(2)) with
        {
            Status = "not-a-status"
        };
        var blankStatus = BuildPortableAsset(
            assetId: "prep_blank_status",
            now: now.AddMinutes(3)) with
        {
            Status = " "
        };

        OfflineSyncSurfaceMergeResult result = service.ReconcilePortableAssets([invalidKind, invalidAudience, invalidStatus, blankStatus]);

        Assert.Equal(0, result.ImportedCount);
        Assert.Equal(4, result.SkippedCount);
        Assert.Contains(result.Conflicts, conflict => conflict.EntityId == "prep_invalid_kind" && conflict.Reason == "invalid-asset-kind");
        Assert.Contains(result.Conflicts, conflict => conflict.EntityId == "prep_invalid_audience" && conflict.Reason == "invalid-asset-audience");
        Assert.Contains(result.Conflicts, conflict => conflict.EntityId == "prep_invalid_status" && conflict.Reason == "invalid-asset-status");
        Assert.Contains(result.Conflicts, conflict => conflict.EntityId == "prep_blank_status" && conflict.Reason == "invalid-asset-status");
        Assert.Null(service.GetPrepAsset("prep_invalid_kind"));
        Assert.Null(service.GetPrepAsset("prep_invalid_audience"));
        Assert.Null(service.GetPrepAsset("prep_invalid_status"));
        Assert.Null(service.GetPrepAsset("prep_blank_status"));
    }

    [Fact]
    public void ReconcilePortableAssets_NormalizesKnownStatuses_ToCanonicalValues()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        var asset = BuildPortableAsset(
            assetId: "prep_status_normalized",
            now: now) with
        {
            Status = " ReVeAled ",
            RevealCount = 1,
            LastRevealedAtUtc = now.AddSeconds(-5),
            LastRevealChannel = "gm-ops"
        };

        OfflineSyncSurfaceMergeResult result = service.ReconcilePortableAssets([asset]);

        Assert.Equal(1, result.ImportedCount);
        Assert.Equal(0, result.SkippedCount);
        Assert.Empty(result.Conflicts);
        GmPrepAssetRecord? stored = service.GetPrepAsset("prep_status_normalized");
        Assert.NotNull(stored);
        Assert.Equal("revealed", stored!.Status);
    }

    [Fact]
    public void ReconcilePortableAssets_SkipsAssets_WhenTimelineIsInvalid()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        var updatedBeforeCreated = BuildPortableAsset(
            assetId: "prep_invalid_timeline",
            now: now) with
        {
            CreatedAtUtc = now,
            UpdatedAtUtc = now.AddMinutes(-1)
        };
        var revealAfterUpdated = BuildPortableAsset(
            assetId: "prep_invalid_reveal_time",
            now: now.AddMinutes(5)) with
        {
            LastRevealedAtUtc = now.AddMinutes(6)
        };
        var negativeRevealCount = BuildPortableAsset(
            assetId: "prep_invalid_reveal_count",
            now: now.AddMinutes(8)) with
        {
            RevealCount = -1
        };
        var revealMetadataWithoutCount = BuildPortableAsset(
            assetId: "prep_invalid_reveal_state_no_count",
            now: now.AddMinutes(11)) with
        {
            LastRevealedAtUtc = now.AddMinutes(10),
            LastRevealChannel = "gm-ops",
            RevealCount = 0
        };
        var revealCountWithoutTimestamp = BuildPortableAsset(
            assetId: "prep_invalid_reveal_state_no_timestamp",
            now: now.AddMinutes(14)) with
        {
            LastRevealedAtUtc = null,
            LastRevealChannel = "gm-ops",
            RevealCount = 2
        };
        var revealCountWithoutChannel = BuildPortableAsset(
            assetId: "prep_invalid_reveal_state_no_channel",
            now: now.AddMinutes(17)) with
        {
            LastRevealedAtUtc = now.AddMinutes(16),
            LastRevealChannel = " ",
            RevealCount = 2
        };

        OfflineSyncSurfaceMergeResult result = service.ReconcilePortableAssets(
        [
            updatedBeforeCreated,
            revealAfterUpdated,
            negativeRevealCount,
            revealMetadataWithoutCount,
            revealCountWithoutTimestamp,
            revealCountWithoutChannel
        ]);

        Assert.Equal(0, result.ImportedCount);
        Assert.Equal(6, result.SkippedCount);
        Assert.Contains(result.Conflicts, conflict => conflict.EntityId == "prep_invalid_timeline" && conflict.Reason == "invalid-asset-timeline");
        Assert.Contains(result.Conflicts, conflict => conflict.EntityId == "prep_invalid_reveal_time" && conflict.Reason == "invalid-asset-reveal-timestamp");
        Assert.Contains(result.Conflicts, conflict => conflict.EntityId == "prep_invalid_reveal_count" && conflict.Reason == "invalid-asset-reveal-count");
        Assert.Contains(result.Conflicts, conflict => conflict.EntityId == "prep_invalid_reveal_state_no_count" && conflict.Reason == "invalid-asset-reveal-state");
        Assert.Contains(result.Conflicts, conflict => conflict.EntityId == "prep_invalid_reveal_state_no_timestamp" && conflict.Reason == "invalid-asset-reveal-state");
        Assert.Contains(result.Conflicts, conflict => conflict.EntityId == "prep_invalid_reveal_state_no_channel" && conflict.Reason == "invalid-asset-reveal-state");
        Assert.Null(service.GetPrepAsset("prep_invalid_timeline"));
        Assert.Null(service.GetPrepAsset("prep_invalid_reveal_time"));
        Assert.Null(service.GetPrepAsset("prep_invalid_reveal_count"));
        Assert.Null(service.GetPrepAsset("prep_invalid_reveal_state_no_count"));
        Assert.Null(service.GetPrepAsset("prep_invalid_reveal_state_no_timestamp"));
        Assert.Null(service.GetPrepAsset("prep_invalid_reveal_state_no_channel"));
    }

    [Fact]
    public void ReconcilePortableAssets_SkipsAssets_WhenRevealedStatusLacksRevealProvenance()
    {
        var service = CreateService();
        var now = DateTimeOffset.UtcNow;
        var revealedWithoutProof = BuildPortableAsset(
            assetId: "prep_revealed_without_proof",
            now: now) with
        {
            Status = "revealed",
            RevealCount = 0,
            LastRevealedAtUtc = null,
            LastRevealChannel = null
        };

        OfflineSyncSurfaceMergeResult result = service.ReconcilePortableAssets([revealedWithoutProof]);

        Assert.Equal(0, result.ImportedCount);
        Assert.Equal(1, result.SkippedCount);
        OfflineSyncConflict conflict = Assert.Single(result.Conflicts);
        Assert.Equal("prep_revealed_without_proof", conflict.EntityId);
        Assert.Equal("invalid-asset-reveal-status", conflict.Reason);
        Assert.Equal("skipped-invalid", conflict.Resolution);
        Assert.Null(service.GetPrepAsset("prep_revealed_without_proof"));
    }

    private static GmOpsBoardService CreateService()
        => CreateService(new SessionLedgerService());

    private static GmOpsBoardService CreateService(SessionLedgerService ledger)
        => new(ledger, new DeliveryOutboxService());

    private static OfflineSyncPrepAsset BuildPortableAsset(
        string assetId,
        DateTimeOffset now,
        string campaignId = "campaign_ops",
        string title = "Portable prep asset",
        string body = "portable body") =>
        new(
            AssetId: assetId,
            CampaignId: campaignId,
            SessionId: "session_ops",
            SceneId: "scene_ops",
            Title: title,
            Kind: nameof(GmPrepAssetKind.Note),
            Audience: nameof(GmPrepAssetAudience.GameMaster),
            Summary: "portable",
            Body: body,
            Tags: ["portable"],
            ChecklistItems: Array.Empty<OfflineSyncPrepChecklistItem>(),
            Status: "draft",
            CreatedBy: "gm.ops",
            RuntimeFingerprint: "ops-fingerprint",
            CreatedAtUtc: now.AddMinutes(-5),
            UpdatedAtUtc: now);
}
