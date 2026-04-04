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
                Payload: "Open checklist remains unresolved.",
                AtUtc: baseTime.AddMinutes(20),
                EventId: "evt-general")
        ]);

        OpsBoardProjection projection = service.GetProjection("session_ops", "scene_ops");

        Assert.Equal(4, projection.UnresolvedItems.Count);
        Assert.Equal("ops:evt-seasoncontrols", projection.UnresolvedItems[0].ItemId);
        Assert.Equal("ops:evt-seasonctrl", projection.UnresolvedItems[1].ItemId);
        Assert.Equal("ops:evt-seasoncontrol", projection.UnresolvedItems[2].ItemId);
        Assert.Equal("ops:evt-general", projection.UnresolvedItems[3].ItemId);
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
        GmPrepAssetListResponse eventControlSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event control");
        GmPrepAssetListResponse eventControlsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event controls");
        GmPrepAssetListResponse eventControlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event-control");
        GmPrepAssetListResponse eventCtrlSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event ctrl");
        GmPrepAssetListResponse eventCtrlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "event-ctrl");
        GmPrepAssetListResponse eventOpsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "eventops");
        GmPrepAssetListResponse eventOpMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "eventop");
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
        GmPrepAssetListResponse seasonOpsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "season ops");
        GmPrepAssetListResponse seasonOpsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "season-ops");
        GmPrepAssetListResponse seasonOperationSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "season operation");
        GmPrepAssetListResponse seasonOperationHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "season-operation");
        GmPrepAssetListResponse seasonOperationsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "season operations");
        GmPrepAssetListResponse seasonOperationsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "season-operations");
        GmPrepAssetListResponse seasonControlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "seasoncontrol");
        GmPrepAssetListResponse seasonControlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "seasoncontrols");
        GmPrepAssetListResponse seasonCtrlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "seasonctrl");
        GmPrepAssetListResponse seasonControlSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "season control");
        GmPrepAssetListResponse seasonControlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "season-control");
        GmPrepAssetListResponse leagueOpsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leagueops");
        GmPrepAssetListResponse leagueOpMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leagueop");
        GmPrepAssetListResponse leagueOperationMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leagueoperation");
        GmPrepAssetListResponse leagueOperationsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leagueoperations");
        GmPrepAssetListResponse leagueOpsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league ops");
        GmPrepAssetListResponse leagueOpsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league-ops");
        GmPrepAssetListResponse leagueOperationsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league operations");
        GmPrepAssetListResponse leagueOperationsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league-operations");
        GmPrepAssetListResponse leagueControlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leaguecontrol");
        GmPrepAssetListResponse leagueControlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leaguecontrols");
        GmPrepAssetListResponse leagueCtrlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "leaguectrl");
        GmPrepAssetListResponse leagueControlSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league control");
        GmPrepAssetListResponse leagueControlsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league controls");
        GmPrepAssetListResponse leagueControlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "league-control");
        GmPrepAssetListResponse communityOpsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communityops");
        GmPrepAssetListResponse communityOpMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communityop");
        GmPrepAssetListResponse communityOperationMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communityoperation");
        GmPrepAssetListResponse communityOperationsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communityoperations");
        GmPrepAssetListResponse communityOpsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community ops");
        GmPrepAssetListResponse communityOpsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community-ops");
        GmPrepAssetListResponse communityOperationsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community operations");
        GmPrepAssetListResponse communityOperationsHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community-operations");
        GmPrepAssetListResponse communityControlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communitycontrol");
        GmPrepAssetListResponse communityControlsMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communitycontrols");
        GmPrepAssetListResponse communityCtrlMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "communityctrl");
        GmPrepAssetListResponse communityControlSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community control");
        GmPrepAssetListResponse communityControlsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community controls");
        GmPrepAssetListResponse communityControlHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "community-control");
        GmPrepAssetListResponse rosterMoveMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "rostermove");
        GmPrepAssetListResponse rosterMovesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "rostermoves");
        GmPrepAssetListResponse rosterMoveHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster-move");
        GmPrepAssetListResponse crewMoveMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crewmove");
        GmPrepAssetListResponse crewMovesMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crewmoves");
        GmPrepAssetListResponse crewMoveHyphenMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew-move");
        GmPrepAssetListResponse crewTransferMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crewtransfer");
        GmPrepAssetListResponse crewTransfersMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crewtransfers");
        GmPrepAssetListResponse crewTransfersSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew transfers");
        GmPrepAssetListResponse crewTransferSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew transfer");
        GmPrepAssetListResponse crewHandoffsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew handoffs");
        GmPrepAssetListResponse crewHandoffSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew handoff");
        GmPrepAssetListResponse crewMovesSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew moves");
        GmPrepAssetListResponse crewMoveSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "crew move");
        GmPrepAssetListResponse rosterTransfersSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster transfers");
        GmPrepAssetListResponse rosterTransferSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster transfer");
        GmPrepAssetListResponse rosterHandoffsSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster handoffs");
        GmPrepAssetListResponse rosterHandoffSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster handoff");
        GmPrepAssetListResponse rosterMovesSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster moves");
        GmPrepAssetListResponse rosterMoveSpacedMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "roster move");
        GmPrepAssetListResponse negativeMatches = service.ListPrepAssets(campaignId: "campaign_ops", queryText: "matrixlibrary");

        Assert.Contains(prepLibraryMatches.Items, item => item.AssetId == "prep_library_ops");
        Assert.Contains(eventControlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventControlsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventCtrlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventControlSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventControlsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventControlHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventCtrlSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventCtrlHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventOpsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(eventOpMatches.Items, item => item.AssetId == "event_control_ops");
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
        Assert.Contains(seasonOpsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonOpsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonOperationSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonOperationHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonOperationsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonOperationsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonControlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonControlsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonCtrlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonControlSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(seasonControlHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueOpsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueOpMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueOperationMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueOperationsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueOpsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueOpsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueOperationsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueOperationsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueControlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueControlsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueCtrlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueControlSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueControlsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(leagueControlHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityOpsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityOpMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityOperationMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityOperationsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityOpsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityOpsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityOperationsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityOperationsHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityControlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityControlsMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityCtrlMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityControlSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityControlsSpacedMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(communityControlHyphenMatches.Items, item => item.AssetId == "event_control_ops");
        Assert.Contains(rosterMoveMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterMovesMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterMoveHyphenMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewMoveMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewMovesMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewMoveHyphenMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewTransferMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewTransfersMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewTransfersSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewTransferSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewHandoffsSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewHandoffSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewMovesSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(crewMoveSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterTransfersSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterTransferSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterHandoffsSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterHandoffSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterMovesSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
        Assert.Contains(rosterMoveSpacedMatches.Items, item => item.AssetId == "roster_move_ops");
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
